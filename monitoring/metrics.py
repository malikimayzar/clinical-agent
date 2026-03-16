import time
import os
from typing import Optional
from contextlib import contextmanager
from prometheus_client import (
    CollectorRegistry,
    Gauge,
    Counter,
    Histogram,
    push_to_gateway,
)

PUSHGATEWAY_URL = os.getenv("PUSHGATEWAY_URL", "localhost:9091")
JOB_NAME = "clinical_agent"

registry = CollectorRegistry()

NODE_LATENCY = Histogram(
    "clinical_agent_node_latency_seconds",
    "Latency per LangGraph node dalam detik",
    labelnames=["node_name"],
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0, 120.0],
    registry=registry,
)

PIPELINE_RUNS_TOTAL = Counter(
    "clinical_agent_pipeline_runs_total",
    "Total pipeline runs",
    labelnames=["status"],
    registry=registry,
)

CLAIMS_EXTRACTED = Gauge(
    "clinical_agent_claims_extracted",
    "Jumlah claims yang diekstrak pada run terakhir",
    registry=registry,
)

CONFLICTS_FOUND = Gauge(
    "clinical_agent_conflicts_found",
    "Jumlah conflicts yang ditemukan pada run terakhir",
    labelnames=["severity"],
    registry=registry,
)

PAPERS_PROCESSED = Gauge(
    "clinical_agent_papers_processed",
    "Jumlah papers yang diproses pada run terakhir",
    registry=registry,
)

FAITHFULNESS_SCORE = Histogram(
    "clinical_agent_faithfulness_score",
    "Distribusi faithfulness score per claim",
    buckets=[0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0],
    registry=registry,
)

FAITHFULNESS_PASSED = Gauge(
    "clinical_agent_faithfulness_passed",
    "Jumlah claims yang passed faithfulness eval",
    registry=registry,
)

FAITHFULNESS_FAILED = Gauge(
    "clinical_agent_faithfulness_failed",
    "Jumlah claims yang failed faithfulness eval",
    registry=registry,
)

PIPELINE_DURATION = Gauge(
    "clinical_agent_pipeline_duration_seconds",
    "Total durasi pipeline run dalam detik",
    registry=registry,
)

LLM_CALLS_TOTAL = Counter(
    "clinical_agent_llm_calls_total",
    "Total LLM API calls ke Groq",
    labelnames=["model", "status"],
    registry=registry,
)

@contextmanager
def time_node(node_name: str):
    start = time.perf_counter()
    try:
        yield
    finally:
        elapsed = time.perf_counter() - start
        NODE_LATENCY.labels(node_name=node_name).observe(elapsed)

def push_metrics(run_id: Optional[str] = None):
    grouping_key = {"run_id": run_id} if run_id else {}
    try:
        push_to_gateway(
            PUSHGATEWAY_URL,
            job=JOB_NAME,
            registry=registry,
            grouping_key=grouping_key,
        )
        print(f"[metrics] [OK] Pushed ke Pushgateway ({PUSHGATEWAY_URL})")
    except Exception as e:
        print(f"[metrics] [ERROR]  Push gagal (non-fatal): {e}")

def record_run_start() -> float:
    return time.perf_counter()

def record_run_end(start_time: float, success: bool):
    duration = time.perf_counter() - start_time
    PIPELINE_DURATION.set(duration)
    status = "success" if success else "failure"
    PIPELINE_RUNS_TOTAL.labels(status=status).inc()

def record_claims(n_claims: int, n_papers: int):
    CLAIMS_EXTRACTED.set(n_claims)
    PAPERS_PROCESSED.set(n_papers)

def record_conflicts(conflicts: list):
    from collections import Counter as _Counter
    counts = _Counter(c.get("severity", "minor") for c in conflicts)
    for severity in ["critical", "major", "minor"]:
        CONFLICTS_FOUND.labels(severity=severity).set(counts.get(severity, 0))

def record_faithfulness(scores: list):
    passed = sum(1 for s in scores if s > 0.0)
    failed = sum(1 for s in scores if s == 0.0)
    FAITHFULNESS_PASSED.set(passed)
    FAITHFULNESS_FAILED.set(failed)
    for score in scores:
        FAITHFULNESS_SCORE.observe(score)

def record_llm_call(model: str = "llama-3.3-70b-versatile", status: str = "success"):
    LLM_CALLS_TOTAL.labels(model=model, status=status).inc()