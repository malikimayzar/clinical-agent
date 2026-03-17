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
    db_status = "connected"
    total_runs = 0
    conn = None
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) as count FROM runs WHERE status IN ('success', 'done')")
        row = cur.fetchone()
        cur.close()
        total_runs = row["count"] if row else 0
    except Exception as e:
        db_status = f"db_error: {str(e)}"
    finally:
        if conn: conn.close()
        
    return {
        "status": "ok",
        "service": "clinical-agent",
        "database": db_status,
        "total_runs": total_runs,
        "timestamp": datetime.utcnow().isoformat(),
    }

@app.get("/runs")
def get_runs(limit: int = 10):
    conn = None
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
        return {"runs": [dict(r) for r in rows], "count": len(rows)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if conn:
            conn.close()

@app.get("/claims")
def get_claims(limit: int = 20, status: Optional[str] = None):
    conn = None
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
        return {"claims": [dict(r) for r in rows], "count": len(rows)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if conn:
            conn.close()

@app.get("/conflicts")
def get_conflicts(limit: int = 20, severity: Optional[str] = None):
    conn = None
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
        return {"conflicts": [dict(r) for r in rows], "count": len(rows)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if conn:
            conn.close()

@app.get("/stats")
def get_stats():
    conn = None
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("""
            SELECT
                (SELECT COUNT(*) FROM runs WHERE status IN ('success', 'done')) as total_runs,
                (SELECT COUNT(*) FROM claims) as total_claims,
                (SELECT COUNT(*) FROM claims WHERE status = 'CONFLICT') as total_conflicts,
                (SELECT COUNT(*) FROM claims WHERE severity = 'critical') as critical_conflicts,
                (SELECT AVG(faithfulness_score) FROM claims WHERE faithfulness_score IS NOT NULL) as avg_faithfulness,
                (SELECT MAX(started_at) FROM runs WHERE status IN ('success', 'done')) as last_run
        """)
        result = cur.fetchone()
        cur.close()
        
        # Cast ke dict secara eksplisit
        stats = dict(result) if result else {}
        return {"stats": stats}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if conn: conn.close()

@app.get("/papers")
def get_papers(limit: int = 20, processed: Optional[bool] = None):
    conn = None
    try:
        conn = get_db()
        cur = conn.cursor()
        if processed is not None:
            cur.execute("""
                SELECT paper_id, arxiv_id, title, abstract,
                       authors, date, source, processed
                FROM papers
                WHERE processed = %s
                ORDER BY date DESC
                LIMIT %s
            """, (processed, limit))
        else:
            cur.execute("""
                SELECT paper_id, arxiv_id, title, abstract,
                       authors, date, source, processed
                FROM papers
                ORDER BY date DESC
                LIMIT %s
            """, (limit,))
        rows = cur.fetchall()
        cur.close()
        return {"papers": [dict(r) for r in rows], "count": len(rows)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if conn: conn.close()


@app.get("/papers/{paper_id}")
def get_paper(paper_id: str):
    conn = None
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("""
            SELECT p.paper_id, p.arxiv_id, p.title, p.abstract,
                   p.authors, p.date, p.source, p.processed,
                   COUNT(c.claim_id) as total_claims,
                   COUNT(CASE WHEN c.status = 'CONFLICT' THEN 1 END) as conflict_claims
            FROM papers p
            LEFT JOIN claims c ON p.paper_id = c.paper_id
            WHERE p.paper_id = %s OR p.arxiv_id = %s
            GROUP BY p.paper_id
        """, (paper_id, paper_id))
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Paper not found")

        cur.execute("""
            SELECT claim_id, text, confidence, faithfulness_score,
                   topic_tags, status, severity, created_at
            FROM claims
            WHERE paper_id = %s
            ORDER BY created_at DESC
        """, (row["paper_id"],))
        claims = cur.fetchall()
        cur.close()

        result = dict(row)
        result["claims"] = [dict(c) for c in claims]
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if conn: conn.close()

@app.get("/runs/{run_id}")
def get_run(run_id: str):
    conn = None
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("""
            SELECT run_id, started_at, finished_at, status,
                   papers_processed, claims_extracted, conflicts_found
            FROM runs
            WHERE run_id = %s
        """, (run_id,))
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Run not found")

        # Fetch audit log for this run
        cur.execute("""
            SELECT al.log_id, al.node, al.action, al.score,
                   al.label, al.created_at,
                   c.text as claim_text, p.title as paper_title
            FROM audit_log al
            LEFT JOIN claims c ON al.claim_id = c.claim_id
            LEFT JOIN papers p ON al.paper_id = p.paper_id
            WHERE al.run_id = %s
            ORDER BY al.created_at ASC
        """, (run_id,))
        logs = cur.fetchall()
        cur.close()

        result = dict(row)
        result["audit_log"] = [dict(l) for l in logs]
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if conn: conn.close()

@app.get("/runs/{run_id}/claims")
def get_run_claims(run_id: str, status: Optional[str] = None):
    """Get all claims extracted during a specific run via audit_log"""
    conn = None
    try:
        conn = get_db()
        cur = conn.cursor()
        if status:
            cur.execute("""
                SELECT DISTINCT c.claim_id, c.text, c.confidence,
                       c.faithfulness_score, c.topic_tags,
                       c.status, c.severity, c.created_at,
                       p.title as paper_title, p.arxiv_id
                FROM audit_log al
                JOIN claims c ON al.claim_id = c.claim_id
                LEFT JOIN papers p ON al.paper_id = p.paper_id
                WHERE al.run_id = %s AND c.status = %s
                ORDER BY c.created_at DESC
            """, (run_id, status.upper()))
        else:
            cur.execute("""
                SELECT DISTINCT c.claim_id, c.text, c.confidence,
                       c.faithfulness_score, c.topic_tags,
                       c.status, c.severity, c.created_at,
                       p.title as paper_title, p.arxiv_id
                FROM audit_log al
                JOIN claims c ON al.claim_id = c.claim_id
                LEFT JOIN papers p ON al.paper_id = p.paper_id
                WHERE al.run_id = %s
                ORDER BY c.created_at DESC
            """, (run_id,))
        rows = cur.fetchall()
        cur.close()
        return {"claims": [dict(r) for r in rows], "count": len(rows)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if conn: conn.close()