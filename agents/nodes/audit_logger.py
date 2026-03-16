from agents.state import AgentState
from db.connection import SessionLocal
from sqlalchemy import text

def audit_log_node(state: AgentState) -> AgentState:
    print("\n[OK] [audit_logger] Saving to database...")
    db = SessionLocal()
    claims = state.get("compared_claims", [])

    try:
        logged = 0
        for claim in claims:
            db.execute(text("""
                INSERT INTO audit_log (run_id, node, action, score, label)
                VALUES (:run_id, :node, :action, :score, :label)
            """), {
                "run_id": state["run_id"],
                "node":   "audit_logger",
                "action": f"claim: {claim['text'][:100]}",
                "score":  claim.get("faithfulness_score",
                          claim.get("score", 0.0)),
                "label":  claim.get("label", "UNCERTAIN"),
            })
            logged += 1

        db.commit()
        print(f"   [OK] {logged} claims logged")

    except Exception as e:
        print(f"   [WARNING]  DB error: {e}")
        db.rollback()
    finally:
        db.close()
    return state