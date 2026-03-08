from agents.state import AgentState
from db.connection import SessionLocal
from sqlalchemy import text

def audit_log_node(state: AgentState) -> AgentState:
    print("\n📝 [audit_logger] Saving to database...")
    db = SessionLocal()
    try:
        for claim in state.get("valid_claims", []):
            db.execute(text("""
                INSERT INTO audit_log (run_id, node, action, score, label)
                VALUES (:run_id, :node, :action, :score, :label)
            """), {
                "run_id": state["run_id"],
                "node":   "audit_logger",
                "action": f"claim: {claim['text'][:100]}",
                "score":  claim.get("faithfulness_score", 0),
                "label":  claim.get("status", "UNCERTAIN"),
            })
        db.commit()
        print(f"   ✅ {len(state.get('valid_claims', []))} claims logged")
    except Exception as e:
        print(f"   ⚠️  DB error: {e}")
        db.rollback()
    finally:
        db.close()
    return state
