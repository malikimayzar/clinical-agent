import json
import re
from ollama import Client
from agents.state import AgentState

client = Client()

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

def try_extract(paper: dict, model: str) -> list:
    try:
        response = client.chat(
            model=model,
            messages=[{"role": "user", "content": build_prompt(paper["abstract"])}],
            options={"temperature": 0.1}
        )
        # Fix bug: handle None content
        content = response.message.content
        if not content:
            print(f"      ⚠️  {model} returned empty response")
            return []

        raw     = content.strip()
        cleaned = clean_json(raw)
        claims  = json.loads(cleaned)

        valid = []
        for c in claims:
            if isinstance(c, dict) and "text" in c:
                if "confidence" not in c:
                    c["confidence"] = 0.8
                if "topic_tags" not in c:
                    c["topic_tags"] = []
                valid.append(c)
        return valid

    except Exception as e:
        print(f"      ⚠️  {model} failed: {e}")
        return []

def extract_claims_node(state: AgentState) -> AgentState:
    print("\n🔍 [claim_extractor] Extracting claims...")
    all_claims  = []
    retry_count = state.get("retry_count", 0)

    for paper in state["papers"]:
        print(f"   📝 {paper['title'][:55]}...")
        claims = try_extract(paper, model="phi3:mini")

        if not claims:
            print(f"      🔄 Retry with mistral...")
            claims = try_extract(paper, model="mistral")

        if claims:
            for c in claims:
                c["paper_id"]    = paper["arxiv_id"]
                c["paper_title"] = paper["title"]
                c["abstract"]    = paper["abstract"]
            all_claims.extend(claims)
            print(f"      ✅ {len(claims)} claims")
        else:
            print(f"      ⚠️  Failed after retry, skip")
            retry_count += 1

    valid = [c for c in all_claims if c.get("confidence", 0) >= 0.6]
    print(f"\n   Total: {len(all_claims)} | Valid: {len(valid)}")

    return {
        **state,
        "raw_claims":       all_claims,
        "valid_claims":     valid,
        "claims_extracted": len(valid),
        "retry_count":      retry_count
    }
