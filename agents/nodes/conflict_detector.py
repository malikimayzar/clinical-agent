from agents.state import AgentState

def detect_conflict_node(state: AgentState) -> AgentState:
    print("\n[WARNING]  [conflict_detector] Detecting conflicts...")
    conflicts = []
    labeled   = []

    claims = state.get("compared_claims", state.get("valid_claims", []))

    for claim in claims:
        similar = claim.get("similar_chunks", [])
        has_similar = claim.get("has_similar", False)

        if not has_similar or not similar:
            # Tidak ada di knowledge base → klaim baru
            claim["status"] = "NEW"
        else:
            scores = [s.get("score", 0) for s in similar]
            max_score = max(scores) if scores else 0

            if max_score >= 0.75:
                claim["status"] = "CONFIRMED"
            elif max_score >= 0.4:
                claim["status"] = "CONFLICT"
                claim["severity"] = "minor"
                conflicts.append(claim)
            else:
                claim["status"] = "NEW"

        labeled.append(claim)
        print(f"   {claim['status']:10} | {claim['text'][:60]}...")

    print(f"\n   Conflicts found: {len(conflicts)}")
    return {
        **state,
        "valid_claims":   labeled,
        "conflicts":      conflicts,
        "conflicts_found": len(conflicts)
    }
