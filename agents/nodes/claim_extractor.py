import json
import re
import os
import asyncio
import aiohttp
from ollama import Client
from agents.state import AgentState

client = Client()

GROQ_API_KEY      = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL        = "llama-3.3-70b-versatile"
CLAIM_PARSER_URL  = os.getenv("CLAIM_PARSER_URL", "http://localhost:8002")

# Prompt & JSON cleaner
def build_prompt(abstract: str) -> str:
    return (
        "Extract 3-5 factual claims from this abstract.\n"
        "Return ONLY a JSON array like this exact format:\n"
        '[{"text": "claim here", "confidence": 0.9, "topic_tags": ["tag"]}]\n\n'
        f"Abstract:\n{abstract}\n\nJSON:"
    )

def clean_json(raw: str) -> str:
    raw = re.sub(r"```(?:json)?", "", raw).strip()
    start = raw.find("[")
    end   = raw.rfind("]")
    if start != -1 and end != -1:
        raw = raw[start:end+1]
    raw = re.sub(r",\s*]", "]", raw)
    raw = re.sub(r",\s*}", "}", raw)
    raw = re.sub(r'\\(?!["\\/bfnrt])', r'\\\\', raw)
    return raw

def _validate_claims(claims: list) -> list:
    valid = []
    for c in claims:
        if isinstance(c, dict) and "text" in c:
            if "confidence" not in c:
                c["confidence"] = 0.8
            if "topic_tags" not in c:
                c["topic_tags"] = []
            valid.append(c)
    return valid

# Async Rust extractor 
async def extract_one_paper_async(
    session: aiohttp.ClientSession,
    paper: dict,
) -> list:
    """Kirim satu paper ke Rust claim-parser secara async."""
    try:
        payload = {
            "paper_id":      paper.get("arxiv_id", "unknown"),
            "paper_title":   paper["title"],
            "abstract_text": paper["abstract"],
        }
        async with session.post(
            f"{CLAIM_PARSER_URL}/extract",
            json=payload,
            timeout=aiohttp.ClientTimeout(total=90),
        ) as res:
            if res.status != 200:
                print(f"      [WARNING]  Rust parser HTTP {res.status} for {paper['arxiv_id']}")
                return []
            data = await res.json()
            claims   = data.get("claims", [])
            parse_ms = data.get("parse_ms", 0)
            groq_ms  = data.get("groq_ms", 0)
            print(f"   [RUST] {paper['title'][:50]}... | {len(claims)} claims | parse={parse_ms}ms | groq={groq_ms}ms")
            return claims
    except Exception as e:
        print(f"      [WARNING]  Rust async failed for {paper.get('arxiv_id', '?')}: {e}")
        return []

async def extract_all_parallel(papers: list) -> dict:
    """
    Kirim semua papers ke Rust claim-parser secara PARALEL.
    Return dict: arxiv_id → claims
    """
    async with aiohttp.ClientSession() as session:
        tasks = [extract_one_paper_async(session, p) for p in papers]
        results = await asyncio.gather(*tasks, return_exceptions=False)
    return {papers[i].get("arxiv_id", str(i)): results[i] for i in range(len(papers))}


# Fallback: Python Groq 
def try_extract_groq(paper: dict) -> list:
    if not GROQ_API_KEY:
        print("      [WARNING]  GROQ_API_KEY tidak ditemukan, skip Groq fallback")
        return []
    try:
        from groq import Groq
        groq_client = Groq(api_key=GROQ_API_KEY)
        response = groq_client.chat.completions.create(
            model=GROQ_MODEL,
            messages=[{"role": "user", "content": build_prompt(paper["abstract"])}],
            temperature=0.1,
            max_tokens=1024,
        )
        content = response.choices[0].message.content
        if not content:
            return []
        cleaned = clean_json(content.strip())
        claims  = json.loads(cleaned)
        return _validate_claims(claims)
    except Exception as e:
        print(f"      [WARNING]  Groq fallback failed: {e}")
        return []

def try_extract(paper: dict, model: str) -> list:
    try:
        response = client.chat(
            model=model,
            messages=[{"role": "user", "content": build_prompt(paper["abstract"])}],
            options={"temperature": 0.1}
        )
        content = response.message.content
        if not content:
            return []
        cleaned = clean_json(content.strip())
        claims  = json.loads(cleaned)
        return _validate_claims(claims)
    except Exception as e:
        print(f"      [WARNING]  {model} failed: {e}")
        return []

def try_extract_rust(paper: dict) -> list:
    """Sync wrapper — dipakai untuk fallback individual."""
    try:
        import requests
        res = requests.post(
            f"{CLAIM_PARSER_URL}/extract",
            json={
                "paper_id":      paper.get("arxiv_id", "unknown"),
                "paper_title":   paper["title"],
                "abstract_text": paper["abstract"],
            },
            timeout=90,
        )
        if res.status_code != 200:
            return []
        data   = res.json()
        claims = data.get("claims", [])
        print(f"      [RUST] {len(claims)} claims | parse={data.get('parse_ms',0)}ms | groq={data.get('groq_ms',0)}ms")
        return claims
    except Exception as e:
        print(f"      [WARNING]  Rust parser failed: {e}")
        return []


# Main node 
def extract_claims_node(state: AgentState) -> AgentState:
    print("\n[FIND] [claim_extractor] Extracting claims (parallel)...")

    papers      = state["papers"]
    retry_count = state.get("retry_count", 0)
    all_claims  = []

    # Parallel Rust extraction untuk semua papers sekaligus 
    print(f"   [PARALLEL] Sending {len(papers)} papers ke Rust claim-parser...")
    import time
    t0 = time.perf_counter()

    try:
        results_map = asyncio.run(extract_all_parallel(papers))
    except Exception as e:
        print(f"   [WARNING]  Parallel extraction gagal: {e}, fallback ke sequential")
        results_map = {}

    elapsed = (time.perf_counter() - t0) * 1000
    print(f"   [PARALLEL] Selesai dalam {elapsed:.0f}ms (semua {len(papers)} papers)")

    # Kumpulkan hasil, fallback per-paper kalau gagal 
    for paper in papers:
        arxiv_id = paper.get("arxiv_id", "unknown")
        claims   = results_map.get(arxiv_id, [])

        if not claims:
            print(f"   [REPEAT] {paper['title'][:45]}... → fallback Groq Python")
            claims = try_extract_groq(paper)

        if not claims:
            print(f"   [REPEAT] Groq gagal → fallback phi3:mini")
            claims = try_extract(paper, model="phi3:mini")

        if claims:
            for c in claims:
                c["paper_id"]    = arxiv_id
                c["paper_title"] = paper["title"]
                c["abstract"]    = paper["abstract"]
            all_claims.extend(claims)
        else:
            print(f"   [WARNING]  {arxiv_id} gagal semua, skip")
            retry_count += 1

    valid = [c for c in all_claims if c.get("confidence", 0) >= 0.6]
    print(f"\n   Total: {len(all_claims)} | Valid: {len(valid)}")

    return {
        **state,
        "raw_claims":       all_claims,
        "valid_claims":     valid,
        "claims_extracted": len(valid),
        "retry_count":      retry_count,
    }