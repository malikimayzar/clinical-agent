from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional
import psycopg2
import psycopg2.extras
import os
from datetime import datetime

app = FastAPI(
    title="clinical-agent API",
    description="Autonomous medical literature monitor — conflict detection & claim tracking",
    version="3.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

def get_db():
    return psycopg2.connect(
        host=os.getenv("POSTGRES_HOST"),
        port=int(os.getenv("POSTGRES_PORT", 6543)),
        dbname=os.getenv("POSTGRES_DB", "postgres"),
        user=os.getenv("POSTGRES_USER"),
        password=os.getenv("POSTGRES_PASSWORD"),
        cursor_factory=psycopg2.extras.RealDictCursor,
    )


@app.get("/")
def root():
    return {
        "service": "clinical-agent",
        "version": "3.0.0",
        "status": "running",
        "docs": "/docs",
        "stack": "Python + Rust + Go + LangGraph",
    }


@app.get("/health")
def health():
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) as runs FROM runs WHERE status = 'done'")
        row = cur.fetchone()
        cur.close()
        conn.close()
        return {
            "status": "ok",
            "service": "clinical-agent",
            "total_runs": row["count"],
            "timestamp": datetime.utcnow().isoformat(),
        }
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))

@app.get("/runs")
def get_runs(limit: int = 10):
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("""
            SELECT run_id, started_at, finished_at, status,
                   papers_processed, claims_extracted, conflicts_found
            FROM runs
            ORDER BY started_at DESC
            LIMIT %s
        """, (limit,))
        rows = cur.fetchall()
        cur.close()
        conn.close()
        return {"runs": [dict(r) for r in rows], "count": len(rows)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/claims")
def get_claims(limit: int = 20, status: Optional[str] = None):
    try:
        conn = get_db()
        cur = conn.cursor()
        if status:
            cur.execute("""
                SELECT claim_id, text, confidence, faithfulness_score,
                       topic_tags, status, severity, created_at
                FROM claims
                WHERE status = %s
                ORDER BY created_at DESC
                LIMIT %s
            """, (status.upper(), limit))
        else:
            cur.execute("""
                SELECT claim_id, text, confidence, faithfulness_score,
                       topic_tags, status, severity, created_at
                FROM claims
                ORDER BY created_at DESC
                LIMIT %s
            """, (limit,))
        rows = cur.fetchall()
        cur.close()
        conn.close()
        return {"claims": [dict(r) for r in rows], "count": len(rows)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/conflicts")
def get_conflicts(limit: int = 20, severity: Optional[str] = None):
    try:
        conn = get_db()
        cur = conn.cursor()
        if severity:
            cur.execute("""
                SELECT claim_id, text, confidence, faithfulness_score,
                       severity, created_at
                FROM claims
                WHERE status = 'CONFLICT' AND severity = %s
                ORDER BY created_at DESC
                LIMIT %s
            """, (severity.lower(), limit))
        else:
            cur.execute("""
                SELECT claim_id, text, confidence, faithfulness_score,
                       severity, created_at
                FROM claims
                WHERE status = 'CONFLICT'
                ORDER BY created_at DESC
                LIMIT %s
            """, (limit,))
        rows = cur.fetchall()
        cur.close()
        conn.close()
        return {"conflicts": [dict(r) for r in rows], "count": len(rows)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/stats")
def get_stats():
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("""
            SELECT
                (SELECT COUNT(*) FROM runs WHERE status = 'done') as total_runs,
                (SELECT COUNT(*) FROM claims) as total_claims,
                (SELECT COUNT(*) FROM claims WHERE status = 'CONFLICT') as total_conflicts,
                (SELECT COUNT(*) FROM claims WHERE severity = 'critical') as critical_conflicts,
                (SELECT AVG(faithfulness_score) FROM claims WHERE faithfulness_score IS NOT NULL) as avg_faithfulness,
                (SELECT MAX(started_at) FROM runs WHERE status = 'done') as last_run
        """)
        result = cur.fetchone()
        stats = dict(result) if result else {}
        cur.close()
        conn.close()
        return {"stats": stats}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))