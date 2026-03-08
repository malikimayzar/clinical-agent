from agents.state import AgentState

def detect_conflict_node(state: AgentState) -> AgentState:
    print("\n⚠️  [conflict_detector] Detecting conflicts...")
    conflicts = []
    labeled   = []

    for claim in state.get("compared_claims", state.get("valid_claims", [])):
        similar = claim.get("similar_chunks", [])
        if not similar:
            claim["status"] = "NEW"
        elif any(s.get("score", 0) > 0.85 for s in similar):
            claim["status"] = "CONFIRMED"
        elif any(s.get("score", 0) > 0.5 for s in similar):
            claim["status"] = "CONFLICT"
            claim["severity"] = "minor"
            conflicts.append(claim)
        else:
            claim["status"] = "UNCERTAIN"
        labeled.append(claim)
        print(f"   {claim['status']:10} | {claim['text'][:60]}...")

    print(f"   Conflicts found: {len(conflicts)}")
    return {**state, "valid_claims": labeled,
            "conflicts": conflicts, "conflicts_found": len(conflicts)}
