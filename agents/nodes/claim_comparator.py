from agents.state import AgentState
from integrations.rag_research import retrieve_similar, health_check

def compare_claims_node(state: AgentState) -> AgentState:
    print("\n🔄 [claim_comparator] Comparing claims vs knowledge base...")
    rag_available = health_check()
    if not rag_available:
        print("   ⚠️  rag-research offline, skipping comparison")
        return {**state, "compared_claims": state["valid_claims"]}

    compared = []
    for claim in state["valid_claims"]:
        results = retrieve_similar(claim["text"], top_k=3, method="hybrid")
        claim["similar_chunks"] = results
        claim["has_similar"]    = len(results) > 0
        compared.append(claim)
        print(f"   🔍 {len(results)} similar found for: {claim['text'][:50]}...")

    return {**state, "compared_claims": compared}
