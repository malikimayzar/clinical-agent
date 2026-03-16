import os
import httpx
from datetime import datetime
from agents.state import AgentState
from dotenv import load_dotenv

load_dotenv()

SLACK_WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL", "")
ALERT_SEVERITIES = {"critical", "major"}
SEVERITY_EMOJI = {
    "critical": "[WARNING]",
    "major":    "[ERROR]",
    "minor":    "[MINOR]",
}

def _send_slack(payload: dict) -> bool:
    if not SLACK_WEBHOOK_URL:
        print("   [WARNING] SLACK_WEBHOOK_URL tidak ditemukan di .env, skip alert")
        return False
    try:
        response = httpx.post(
            SLACK_WEBHOOK_URL,
            json=payload,
            timeout=10,
        )
        return response.status_code == 200
    except Exception as e:
        print(f"   [WARNING] Slack request failed: {e}")
        return False

def _build_conflict_payload(conflicts: list, run_id: str) -> dict:
    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    blocks = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": f"[OK] clinical-agent — Conflict Alert",
                "emoji": True,
            }
        },
        {
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "text": f"*Run ID:*\n`{run_id[:8]}`"},
                {"type": "mrkdwn", "text": f"*Time:*\n{now}"},
                {"type": "mrkdwn", "text": f"*Conflicts:*\n{len(conflicts)} ditemukan"},
            ]
        },
        {"type": "divider"},
    ]
    
    for i, conflict in enumerate(conflicts[:5]):   
        severity = conflict.get("severity", "minor")
        emoji    = SEVERITY_EMOJI.get(severity, "[WARNING]")
        score    = conflict.get("score", 0.0)
        method   = conflict.get("method", "?")
        text     = conflict.get("text", "")[:200]
        paper    = conflict.get("paper_title", "Unknown paper")[:80]

        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    f"{emoji} *[{severity.upper()}]* score=`{score:.3f}` method=`{method}`\n"
                    f"*Claim:* {text}\n"
                    f"*Paper:* _{paper}_"
                )
            }
        })

    if len(conflicts) > 5:
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"_... dan {len(conflicts) - 5} konflik lainnya. Cek report untuk detail lengkap._"
            }
        })

    blocks.append({"type": "divider"})
    blocks.append({
        "type": "context",
        "elements": [{
            "type": "mrkdwn",
            "text": "clinical-agent v2 · Python + Rust + Go + LangGraph · Zero Budget"
        }]
    })
    return {"blocks": blocks}

def _build_summary_payload(run_id: str, summary: dict) -> dict:
    now      = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    new      = summary.get("NEW", 0)
    confirmed = summary.get("CONFIRMED", 0)
    conflict = summary.get("CONFLICT", 0)
    uncertain = summary.get("UNCERTAIN", 0)
    total    = new + confirmed + conflict + uncertain
    status_emoji = "[OK]" if conflict == 0 else "[WARNING]"

    return {
        "blocks": [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (
                        f"{status_emoji} *clinical-agent run selesai* · {now}\n"
                        f"`{run_id[:8]}` · {total} claims · "
                        f"NEW={new} CONFIRMED={confirmed} "
                        f"CONFLICT={conflict} UNCERTAIN={uncertain}"
                    )
                }
            }
        ]
    }

def alert_node(state: AgentState) -> AgentState:
    print("\n[alert_node] Checking conflicts for alert...")

    conflicts = state.get("conflicts", [])
    summary   = state.get("conflict_summary", {})
    run_id    = state.get("run_id", "unknown")

    if not SLACK_WEBHOOK_URL:
        print("   [WARNING] SLACK_WEBHOOK_URL tidak di-.env, skip semua alert")
        return state
    
    summary_payload = _build_summary_payload(run_id, summary)
    ok = _send_slack(summary_payload)
    print(f"   [{'OK' if ok else 'WARNING'}] Summary alert {'terkirim' if ok else 'gagal'}")
    
    high_priority = [
        c for c in conflicts
        if c.get("severity") in ALERT_SEVERITIES
    ]

    if high_priority:
        conflict_payload = _build_conflict_payload(high_priority, run_id)
        ok2 = _send_slack(conflict_payload)
        print(
            f"   [{'OK' if ok2 else 'WARNING'}] Conflict alert "
            f"({len(high_priority)} critical/major) {'terkirim' if ok2 else 'gagal'}"
        )
    else:
        print(f"   [OK] Tidak ada critical/major conflict, skip conflict alert")
    return state