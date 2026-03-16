import os
from datetime import datetime
from agents.state import AgentState

def generate_report_node(state: AgentState) -> AgentState:
    print("\n[OK] [report_generator] Generating report...")
    now      = datetime.now().strftime("%Y-%m-%d %H:%M")
    conflicts = state.get("conflicts", [])
    claims    = state.get("valid_claims", [])

    report = f"""# clinical-agent Daily Report
**Run ID:** {state['run_id']}
**Date:** {now}

## Summary
- Papers processed : {state.get('papers_processed', 0)}
- Claims extracted : {state.get('claims_extracted', 0)}
- Conflicts found  : {state.get('conflicts_found', 0)}

## Conflicts
"""
    if conflicts:
        for c in conflicts:
            report += f"- [{c.get('severity','?').upper()}] {c['text']}\n"
    else:
        report += "_No conflicts detected._\n"

    report += "\n## All Claims\n"
    for c in claims:
        report += f"- [{c.get('status','?')}] {c['text']}\n"

    os.makedirs("reports", exist_ok=True)
    path = f"reports/report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
    with open(path, "w") as f:
        f.write(report)

    print(f"   [OK] Report saved: {path}")
    return {**state, "status": "done", "report_path": path}