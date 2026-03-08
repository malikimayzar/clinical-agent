import json
from ollama import Client
from agents.state import AgentState

client = Client()

PROMPT = """Extract 3-5 atomic factual claims from this abstract.
Return ONLY valid JSON array:
[{{"text": "claim", "confidence": 0.9, "topic_tags": ["tag"]}}]

Abstract: {abstract}"""

def extract_claims_node(state: AgentState) -> AgentState:
    print("\n🔍 [claim_extractor] Extracting claims...")
    all_claims = []
    retry_count = state.get("retry_count", 0)

    for paper in state["papers"]:
        print(f"   📝 {paper['title'][:50]}...")
        try:
            response = client.chat(
                model="phi3:mini",
                messages=[{"role": "user", "content": PROMPT.format(abstract=paper["abstract"])}]
            )
            raw = response.message.content.strip()
            if "```" in raw:
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
            claims = json.loads(raw)
            for c in claims:
                c["paper_id"]    = paper["arxiv_id"]
                c["paper_title"] = paper["title"]
                c["abstract"]    = paper["abstract"]
            all_claims.extend(claims)
            print(f"      ✅ {len(claims)} claims")
        except Exception as e:
            print(f"      ⚠️  Failed: {e}")
            retry_count += 1

    valid = [c for c in all_claims if c.get("confidence", 0) >= 0.6]
    print(f"   Total: {len(all_claims)} | Valid: {len(valid)}")
    return {**state, "raw_claims": all_claims, "valid_claims": valid,
            "claims_extracted": len(valid), "retry_count": retry_count}
