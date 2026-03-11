from agents.state import AgentState
from integrations.rag_research import retrieve_similar, health_check

def compare_claims_node(state: AgentState) -> AgentState:
    print("\n[REPEAT] [claim_comparator] Comparing claims vs knowledge base...")

    # Cek health dulu
    if not health_check():
        print("   [WARNING]  rag-research offline, skipping comparison")
        return {**state, "compared_claims": state["valid_claims"]}

    print("   [OK] rag-research online, comparing...")
    compared = []
    for claim in state["valid_claims"]:
        results = retrieve_similar(claim["text"], top_k=3, method="hybrid")
        claim["similar_chunks"] = results
        claim["has_similar"]    = len(results) > 0
        compared.append(claim)

        status = f"{len(results)} similar" if results else "no match"
        print(f"   [FIND] [{status}] {claim['text'][:55]}...")

    print(f"\n   Total compared: {len(compared)} claims")
    return {**state, "compared_claims": compared}
