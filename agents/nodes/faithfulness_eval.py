from agents.state import AgentState
from integrations.llm_eval import evaluate_claim

def faithfulness_eval_node(state: AgentState) -> AgentState:
    print("\n🔬 [faithfulness_eval] Evaluating claims...")
    evaluated = []
    for claim in state.get("valid_claims", []):
        claim = evaluate_claim(claim)
        icon  = "✅" if not claim.get("has_failure") else "⚠️ "
        print(f"   {icon} score={claim.get('faithfulness_score', 0):.2f} | {claim['text'][:50]}...")
        evaluated.append(claim)
    passed = [c for c in evaluated if c.get("faithfulness_score", 0) >= 0.5]
    print(f"   Passed: {len(passed)}/{len(evaluated)}")
    return {**state, "valid_claims": passed}
