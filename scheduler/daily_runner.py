from __future__ import annotations
import argparse
import logging
import signal
import sys
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.events import EVENT_JOB_EXECUTED, EVENT_JOB_ERROR
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("daily_runner")

# DB helpers 
def get_db_conn():
    import psycopg2
    import os
    return psycopg2.connect(
        host=os.getenv("POSTGRES_HOST", "localhost"),
        port=int(os.getenv("POSTGRES_PORT", 5432)),
        dbname=os.getenv("POSTGRES_DB", "clinical_agent"),
        user=os.getenv("POSTGRES_USER", "maliki"),
        password=os.getenv("POSTGRES_PASSWORD", "localdev123"),
    )

def get_last_run_time() -> datetime | None:
    try:
        conn = get_db_conn()
        cur = conn.cursor()
        cur.execute("""
            SELECT started_at FROM runs
            WHERE status = 'done'
            ORDER BY started_at DESC
            LIMIT 1
        """)
        row = cur.fetchone()
        cur.close()
        conn.close()
        if row:
            dt = row[0]
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
    except Exception as e:
        logger.warning("Gagal cek last run: %s", e)
    return None

def log_run_start(run_id: str) -> None:
    try:
        conn = get_db_conn()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO runs (run_id, status, started_at, papers_processed,
                              claims_extracted, conflicts_found, errors)
            VALUES (%s, 'running', %s, 0, 0, 0, '[]'::jsonb)
            ON CONFLICT (run_id) DO NOTHING
        """, (run_id, datetime.now(timezone.utc)))
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        logger.warning("Gagal log run start: %s", e)

def log_run_end(run_id: str, result: dict) -> None:
    try:
        import json
        conn = get_db_conn()
        cur = conn.cursor()
        cur.execute("""
            UPDATE runs SET
                status            = %s,
                finished_at       = %s,
                papers_processed  = %s,
                claims_extracted  = %s,
                conflicts_found   = %s,
                errors            = %s::jsonb
            WHERE run_id = %s
        """, (
            result.get("status", "success"),
            datetime.now(timezone.utc),
            result.get("papers_processed", 0),
            result.get("claims_extracted", 0),
            result.get("conflicts_found", 0),
            json.dumps(result.get("errors", [])),
            run_id,
        ))
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        logger.warning("Gagal log run end: %s", e)

# Core pipeline runner 
def run_pipeline() -> dict:
    """Jalankan satu siklus clinical-agent pipeline."""
    run_id = str(uuid.uuid4())
    started_at = datetime.now(timezone.utc).isoformat()

    logger.info("=" * 60)
    logger.info("  clinical-agent daily run started")
    logger.info("  run_id  : %s", run_id)
    logger.info("  time    : %s", started_at)
    logger.info("=" * 60)

    log_run_start(run_id)

    # Metrics: catat waktu mulai 
    from monitoring.metrics import (
        record_run_start,
        record_run_end,
        record_claims,
        record_conflicts,
        push_metrics,
    )
    _metrics_start = record_run_start()
    _success = False

    try:
        from agents.graph import build_graph

        agent = build_graph()
        result = agent.invoke({
            "run_id":           run_id,
            "started_at":       started_at,
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
            "status":           "running",
        })

        logger.info("=" * 60)
        logger.info("  Run selesai")
        logger.info("  Status          : %s", result.get("status"))
        logger.info("  Papers          : %s", result.get("papers_processed"))
        logger.info("  Claims          : %s", result.get("claims_extracted"))
        logger.info("  Conflicts       : %s", result.get("conflicts_found"))
        logger.info("  Report          : %s", result.get("report_path"))
        logger.info("=" * 60)

        log_run_end(run_id, result)

        # Metrics: record hasil run 
        record_claims(
            n_claims=result.get("claims_extracted", 0),
            n_papers=result.get("papers_processed", 0),
        )
        record_conflicts(result.get("conflicts", []))
        _success = result.get("status") == "done"
        return result

    except Exception as e:
        logger.error("Pipeline error: %s", e, exc_info=True)
        error_result = {
            "run_id":           run_id,
            "status":           "error",
            "papers_processed": 0,
            "claims_extracted": 0,
            "conflicts_found":  0,
            "errors":           [str(e)],
        }
        log_run_end(run_id, error_result)
        return error_result

    finally:
        record_run_end(_metrics_start, _success)
        push_metrics(run_id=run_id)

# Missed run recovery 
def check_missed_run() -> bool:
    now = datetime.now(timezone.utc)
    last_run = get_last_run_time()
    today_run = now.replace(hour=2, minute=0, second=0, microsecond=0)
    if now < today_run:
        expected_last = today_run - timedelta(days=1)
    else:
        expected_last = today_run

    if last_run is None:
        logger.info("[RECOVERY] Belum pernah run, jalankan sekarang")
        return True

    if last_run < expected_last:
        delta = now - last_run
        logger.info(
            "[RECOVERY] Last run: %s (%.1f jam lalu) — missed run detected, jalankan sekarang",
            last_run.strftime("%Y-%m-%d %H:%M UTC"),
            delta.total_seconds() / 3600,
        )
        return True

    logger.info(
        "[OK] Last run: %s — tidak ada missed run",
        last_run.strftime("%Y-%m-%d %H:%M UTC"),
    )
    return False

# Scheduler event listeners 
def on_job_executed(event):
    logger.info("[SCHEDULER] Job selesai — next run: 02:00 UTC besok")

def on_job_error(event):
    logger.error("[SCHEDULER] Job error: %s", event.exception)

# Entry point 
def main():
    parser = argparse.ArgumentParser(description="clinical-agent daily scheduler")
    parser.add_argument(
        "--run-now",
        action="store_true",
        help="Langsung jalankan pipeline sekali tanpa scheduler",
    )
    parser.add_argument(
        "--skip-recovery",
        action="store_true",
        help="Skip missed run recovery check saat startup",
    )
    args = parser.parse_args()

    # Mode: run-now 
    if args.run_now:
        logger.info("[MANUAL] Run-now mode triggered")
        result = run_pipeline()
        status = result.get("status", "unknown")
        conflicts = result.get("conflicts_found", 0)
        print(f"\nStatus: {status} | Conflicts: {conflicts}")
        sys.exit(0 if status == "done" else 1)

    # Mode: scheduler
    logger.info("[SCHEDULER] Starting clinical-agent daily scheduler...")
    logger.info("[SCHEDULER] Scheduled: 02:00 UTC setiap hari")

    # Missed run recovery
    if not args.skip_recovery:
        if check_missed_run():
            logger.info("[RECOVERY] Menjalankan missed run...")
            run_pipeline()

    # Setup APScheduler
    scheduler = BlockingScheduler(timezone="UTC")
    scheduler.add_job(
        run_pipeline,
        trigger=CronTrigger(hour=2, minute=0, timezone="UTC"),
        id="daily_clinical_run",
        name="clinical-agent daily pipeline",
        max_instances=1,
        misfire_grace_time=3600,
        coalesce=True,
    )

    scheduler.add_listener(on_job_executed, EVENT_JOB_EXECUTED)
    scheduler.add_listener(on_job_error, EVENT_JOB_ERROR)

    def shutdown(signum, frame):
        logger.info("[SCHEDULER] Shutting down gracefully...")
        scheduler.shutdown(wait=False)
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    scheduler.start()

if __name__ == "__main__":
    main()