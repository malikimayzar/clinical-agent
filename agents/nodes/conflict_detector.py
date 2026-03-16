from __future__ import annotations
import logging
import time
import os
import asyncio
import aiohttp
from agents.state import AgentState

logger = logging.getLogger(__name__)

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL   = "llama-3.3-70b-versatile"

ENTAILMENT_THRESHOLD     = 0.85
CONTRADICTION_THRESHOLD  = 0.70
RULE_CONFIRMED_THRESHOLD = 0.75
RULE_CONFLICT_THRESHOLD  = 0.40

# DeBERTa fallback cache
_nli_model     = None
_nli_tokenizer = None

# Prompt 
def _build_nli_prompt(claim: str, kb_texts: list[str]) -> str:
    kb_str = "\n".join(f"- {t[:300]}" for t in kb_texts[:3])
    return f"""You are a medical claim conflict detector.

Given a NEW CLAIM and EXISTING KNOWLEDGE BASE entries, classify the relationship.

NEW CLAIM:
{claim}

KNOWLEDGE BASE:
{kb_str}

Classify as exactly one of:
- CONFLICT_CRITICAL  (direct contradiction, score > 0.90)
- CONFLICT_MAJOR     (significant contradiction, score 0.70-0.90)
- CONFLICT_MINOR     (minor contradiction, score 0.50-0.70)
- CONFIRMED          (supported by KB)
- UNCERTAIN          (unclear relationship)
- NEW                (not related to KB)

Reply with ONLY this JSON (no markdown, no explanation):
{{"label": "CONFLICT_CRITICAL", "score": 0.95, "reason": "one sentence"}}"""

#  Groq NLI 
async def _groq_nli_one(
    session: aiohttp.ClientSession,
    claim_text: str,
    kb_texts: list[str],
) -> dict | None:
    if not GROQ_API_KEY or not kb_texts:
        return None
    try:
        payload = {
            "model": GROQ_MODEL,
            "messages": [{"role": "user", "content": _build_nli_prompt(claim_text, kb_texts)}],
            "temperature": 0.0,
            "max_tokens": 100,
        }
        async with session.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {GROQ_API_KEY}",
                     "Content-Type": "application/json"},
            json=payload,
            timeout=aiohttp.ClientTimeout(total=30),
        ) as res:
            if res.status != 200:
                return None
            data    = await res.json()
            content = data["choices"][0]["message"]["content"].strip()

            # Parse JSON response
            import json, re
            content = re.sub(r"```(?:json)?", "", content).strip()
            parsed  = json.loads(content)
            raw_label = parsed.get("label", "NEW").upper()
            score     = float(parsed.get("score", 0.5))

            # Normalize label
            if raw_label == "CONFLICT_CRITICAL":
                return {"label": "CONFLICT", "severity": "critical",
                        "score": score, "method": "groq_nli"}
            elif raw_label == "CONFLICT_MAJOR":
                return {"label": "CONFLICT", "severity": "major",
                        "score": score, "method": "groq_nli"}
            elif raw_label == "CONFLICT_MINOR":
                return {"label": "CONFLICT", "severity": "minor",
                        "score": score, "method": "groq_nli"}
            elif raw_label == "CONFIRMED":
                return {"label": "CONFIRMED", "severity": None,
                        "score": score, "method": "groq_nli"}
            elif raw_label == "UNCERTAIN":
                return {"label": "UNCERTAIN", "severity": None,
                        "score": score, "method": "groq_nli"}
            else:
                return {"label": "NEW", "severity": None,
                        "score": score, "method": "groq_nli"}

    except Exception as e:
        logger.warning("[NLI-Groq] error: %s", e)
        return None

async def _groq_nli_all(claims_with_kb: list[tuple[str, list[str]]]) -> list[dict | None]:
    """Parallel Groq NLI untuk semua claims sekaligus."""
    async with aiohttp.ClientSession() as session:
        tasks = [_groq_nli_one(session, claim, kb) for claim, kb in claims_with_kb]
        return await asyncio.gather(*tasks)


# ── DeBERTa fallback (per-claim) ──────────────────────────────────────────────
def _load_nli_model():
    global _nli_model, _nli_tokenizer
    if _nli_model is not None:
        return _nli_model, _nli_tokenizer
    try:
        import torch
        from transformers import AutoTokenizer, AutoModelForSequenceClassification
        model_name = "cross-encoder/nli-deberta-v3-small"
        _nli_tokenizer = AutoTokenizer.from_pretrained(model_name)
        _nli_model     = AutoModelForSequenceClassification.from_pretrained(model_name)
        _nli_model.eval()
    except Exception as exc:
        logger.warning("[NLI] Gagal load DeBERTa: %s", exc)
        _nli_model = _nli_tokenizer = None
    return _nli_model, _nli_tokenizer

def _deberta_nli_one(claim_text: str, kb_texts: list[str]) -> dict | None:
    import torch

    res = _load_nli_model()
    if res is None:
        logger.error("[NLI] Gagal memuat model/tokenizer")
        return None
    model, tokenizer = res

    if model is None or tokenizer is None or not kb_texts:
        logger.warning(f"[NLI] Inisialisasi gagal. Model: {type(model)}, Tokenizer: {type(tokenizer)}")
        return None

    try:
        premises = [kb[:512] for kb in kb_texts[:3]]
        hypotheses = [claim_text] * len(premises)
        inputs = tokenizer(premises, hypotheses, return_tensors="pt",
                           truncation=True, max_length=256, padding=True)
        with torch.no_grad():
            logits = model(**inputs).logits
        probs = torch.softmax(logits, dim=-1)
        bc = probs[:, 0].max().item()
        be = probs[:, 1].max().item()
        if be >= ENTAILMENT_THRESHOLD:
            return {"label": "CONFIRMED", "severity": None, "score": be, "method": "deberta"}
        if bc >= CONTRADICTION_THRESHOLD:
            sev = "critical" if bc > 0.90 else "major" if bc > 0.70 else "minor"
            return {"label": "CONFLICT", "severity": sev, "score": bc, "method": "deberta"}
        label = "UNCERTAIN" if (be > 0.3 or bc > 0.3) else "NEW"
        return {"label": label, "severity": None, "score": max(be, bc), "method": "deberta"}
    except Exception as exc:
        logger.warning("[NLI] DeBERTa error: %s", exc)
        return None


# ── Rule-based fallback 
def _rule_based_classify(similarity_score: float) -> dict:
    if similarity_score >= RULE_CONFIRMED_THRESHOLD:
        return {"label": "CONFIRMED", "severity": None,
                "score": similarity_score, "method": "rule_based"}
    if similarity_score >= RULE_CONFLICT_THRESHOLD:
        return {"label": "CONFLICT", "severity": "major",
                "score": similarity_score, "method": "rule_based"}
    return {"label": "NEW", "severity": None,
            "score": similarity_score, "method": "rule_based"}


# ── Main node ─────────────────────────────────────────────────────────────────

def detect_conflict_node(state: AgentState) -> AgentState:
    print("\n[conflict_detector] Detecting conflicts (Groq NLI parallel)...")

    compared = state.get("compared_claims", [])
    labeled  = []
    conflicts = []
    summary  = {"NEW": 0, "CONFIRMED": 0, "CONFLICT": 0, "UNCERTAIN": 0}

    # ── Prepare input ─────────────────────────────────────────────────────────
    claims_with_kb = [
        (c.get("text", "").strip(),
         [x["text"] for x in c.get("similar_chunks", []) if x.get("text")])
        for c in compared
    ]

    # ── Parallel Groq NLI ─────────────────────────────────────────────────────
    t0 = time.perf_counter()
    groq_results = asyncio.run(_groq_nli_all(claims_with_kb))
    elapsed_ms   = (time.perf_counter() - t0) * 1000
    print(f"   [GROQ-NLI] {len(compared)} claims parallel | {elapsed_ms:.0f}ms total | {elapsed_ms/len(compared):.0f}ms/claim")

    # ── Assemble — fallback per claim kalau Groq gagal ────────────────────────
    for i, claim in enumerate(compared):
        result = groq_results[i]

        if result is None:
            kb_texts = claims_with_kb[i][1]
            result   = _deberta_nli_one(claim.get("text", ""), kb_texts)

        if result is None:
            result = _rule_based_classify(float(claim.get("similarity_score", 0.0)))

        labeled_claim = {**claim,
            "label":    result["label"],
            "severity": result["severity"],
            "score":    round(result["score"], 4),
            "method":   result["method"],
        }
        labeled.append(labeled_claim)
        summary[result["label"]] = summary.get(result["label"], 0) + 1
        if result["label"] == "CONFLICT":
            conflicts.append(labeled_claim)

    methods  = "+".join(sorted(set(c["method"] for c in labeled)))
    print(f"   Method  : {methods.upper()}")
    print(f"   NEW={summary['NEW']}  CONFIRMED={summary['CONFIRMED']}  "
          f"CONFLICT={summary['CONFLICT']}  UNCERTAIN={summary['UNCERTAIN']}")

    if conflicts:
        print(f"\n   [WARNING]  {len(conflicts)} CONFLICT(s) ditemukan:")
        for c in conflicts:
            print(f"      [{c.get('severity','?').upper()}] score={c['score']:.3f} | {c['text'][:75]}...")
    else:
        print("   [OK] Tidak ada konflik ditemukan")

    return {**state,
        "compared_claims": labeled,
        "conflicts":       conflicts,
        "conflicts_found": len(conflicts),
    }
