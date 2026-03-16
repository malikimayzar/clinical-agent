from agents.state import AgentState
from integrations.rag_research import retrieve_similar, health_check

def compare_claims_node(state: AgentState) -> AgentState:
    print("\n[claim_comparator] Comparing claims vs knowledge base...")

    if not health_check():
        print("   [WARNING] rag-research offline, skipping comparison")
        fallback = []
        for claim in state["valid_claims"]:
            fallback.append({
                **claim,
                "similar_chunks":   [],
                "has_similar":      False,
                "similarity_score": 0.0,
            })
        return {**state, "compared_claims": fallback}

    print("   [OK] rag-research online, comparing...")
    compared = []

    for claim in state["valid_claims"]:
        results = retrieve_similar(claim["text"], top_k=3, method="hybrid")
        chunks = []
        for r in results:
            chunks.append({
                "text":     r.get("text", ""),
                "score":    float(r.get("score", 0.0)),
                "chunk_id": r.get("chunk_id", ""),
            })

        similarity_score = max((c["score"] for c in chunks), default=0.0)

        compared.append({
            **claim,
            "similar_chunks":   chunks,
            "has_similar":      len(chunks) > 0,
            "similarity_score": similarity_score,
        })

        status = f"{len(chunks)} similar" if chunks else "no match"
        print(f"   [FIND] [{status}] {claim['text'][:55]}...")

    print(f"\n   Total compared: {len(compared)} claims")
    return {**state, "compared_claims": compared}