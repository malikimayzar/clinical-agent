import uuid
from datetime import datetime
from agents.graph import build_graph

agent = build_graph()

result = agent.invoke({
    "run_id":           str(uuid.uuid4()),
    "started_at":       datetime.now().isoformat(),
    "papers":           [],
    "papers_processed": 0,
    "raw_claims":       [],
    "valid_claims":     [],
    "claims_extracted": 0,
    "compared_claims":  [],
    "conflicts":        [],
    "conflicts_found":  0,
    "retry_count":      0,
    "errors":           [],
    "report_path":      None,
    "status":           "running"
})

print("\n" + "="*50)
print(f"✅ Status   : {result['status']}")
print(f"📄 Papers   : {result['papers_processed']}")
print(f"🔍 Claims   : {result['claims_extracted']}")
print(f"⚠️  Conflicts: {result['conflicts_found']}")
print(f"📊 Report   : {result['report_path']}")