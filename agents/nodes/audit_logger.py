from agents.state import AgentState
from db.connection import SessionLocal
from sqlalchemy import text
import uuid

def audit_log_node(state: AgentState) -> AgentState:
    print("\n[OK] [audit_logger] Saving to database...")
    db = SessionLocal()
    claims = state.get("compared_claims", [])
    try:
        logged = 0
        for claim in claims:
            claim_id = str(uuid.uuid4())
            
            # Insert ke tabel claims
            db.execute(text("""
                INSERT INTO claims (claim_id, text, confidence, faithfulness_score,
                                   topic_tags, status, severity, created_at)
                VALUES (:claim_id, :text, :confidence, :faithfulness_score,
                        :topic_tags, :status, :severity, NOW())
                ON CONFLICT (claim_id) DO NOTHING
            """), {
                "claim_id":          claim_id,
                "text":              claim.get("text", "")[:500],
                "confidence":        claim.get("confidence", 0.8),
                "faithfulness_score": claim.get("faithfulness_score", None),
                "topic_tags":        claim.get("topic_tags", []),
                "status":            claim.get("label", "NEW"),
                "severity":          claim.get("severity", None),
            })

            # Insert ke audit_log
            db.execute(text("""
                INSERT INTO audit_log (run_id, node, action, score, label, claim_id)
                VALUES (:run_id, :node, :action, :score, :label, :claim_id)
            """), {
                "run_id":   state["run_id"],
                "node":     "audit_logger",
                "action":   f"claim: {claim.get('text', '')[:100]}",
                "score":    claim.get("faithfulness_score", claim.get("score", 0.0)),
                "label":    claim.get("label", "UNCERTAIN"),
                "claim_id": claim_id,
            })
            logged += 1

        db.commit()
        print(f"   [OK] {logged} claims logged")
    except Exception as e:
        print(f"   [WARNING] DB error: {e}")
        db.rollback()
    finally:
        db.close()
    return state
