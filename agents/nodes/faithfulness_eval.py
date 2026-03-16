from __future__ import annotations
import numpy as np
import time
from agents.state import AgentState

EMBED_MODEL  = "sentence-transformers/all-MiniLM-L6-v2"
THRESHOLD    = 0.55

_embedder = None

def _get_embedder():
    global _embedder
    if _embedder is None:
        from sentence_transformers import SentenceTransformer
        print("   [EMBED] Loading sentence-transformers model (once)...")
        import os
        os.environ["TRANSFORMERS_OFFLINE"] = "1"
        _embedder = SentenceTransformer(EMBED_MODEL, cache_folder=None)
        print("   [EMBED] Model loaded [OK]")
    return _embedder


def _cosine_sim(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    a_n = a / (np.linalg.norm(a, axis=1, keepdims=True) + 1e-10)
    b_n = b / (np.linalg.norm(b, axis=1, keepdims=True) + 1e-10)
    return np.dot(a_n, b_n.T)


def _split_spans(text: str) -> list[str]:
    import re
    spans = re.split(r'(?<=[.!?])\s+', text.strip())
    return [s.strip() for s in spans if len(s.strip().split()) >= 3][:5]


def faithfulness_eval_node(state: AgentState) -> AgentState:
    print("\n[OK] [faithfulness_eval] Evaluating claims (sentence-transformers)...")

    claims = state.get("valid_claims", [])
    if not claims:
        return {**state, "valid_claims": []}

    t0 = time.perf_counter()

    embedder            = _get_embedder()
    claim_texts         = [c["text"] for c in claims]
    abstracts           = [c.get("abstract", "") for c in claims]
    all_spans_per_claim = [_split_spans(a) for a in abstracts]

    # Flatten semua teks — satu batch encode
    all_texts    = claim_texts.copy()
    span_offsets = []
    for spans in all_spans_per_claim:
        start = len(all_texts)
        all_texts.extend(spans)
        span_offsets.append((start, len(all_texts)))

    n_spans = len(all_texts) - len(claims)
    print(f"   [EMBED] {len(all_texts)} texts ({len(claims)} claims + {n_spans} spans)...")

    # Single batch encode — sentence-transformers handle batching internally
    all_embs = embedder.encode(
        all_texts,
        batch_size=32,
        show_progress_bar=False,
        convert_to_numpy=True,
    )
    embed_ms = (time.perf_counter() - t0) * 1000
    print(f"   [EMBED] Done in {embed_ms:.0f}ms")

    # Score tiap claim
    evaluated = []
    for i, claim in enumerate(claims):
        claim_emb  = all_embs[i:i+1]
        start, end = span_offsets[i]

        if end > start:
            span_embs  = all_embs[start:end]
            sims       = _cosine_sim(claim_emb, span_embs)[0]
            best_score = float(sims.max())
        else:
            best_score = 0.5

        supported = best_score >= THRESHOLD
        claim = {**claim,
            "faithfulness_score": round(best_score, 4),
            "has_failure":        not supported,
        }
        icon = "[OK]" if supported else "[WARNING]"
        print(f"   {icon} score={best_score:.2f} | {claim['text'][:50]}...")
        evaluated.append(claim)

    total_ms = (time.perf_counter() - t0) * 1000
    passed   = [c for c in evaluated if c.get("faithfulness_score", 0) >= 0.5]
    print(f"   Passed: {len(passed)}/{len(evaluated)} | Total: {total_ms:.0f}ms")

    return {**state, "valid_claims": passed}
