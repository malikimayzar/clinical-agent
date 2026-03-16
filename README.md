# clinical-agent

> Autonomous medical literature monitor — fetches ArXiv papers daily, extracts clinical claims, detects contradictions using NLI, and alerts researchers via Slack.

**Stack:** Python · Rust · Go · LangGraph · PostgreSQL  
**Budget:** Zero (all free-tier services)  
**Status:** Production-ready, running autonomously at 02:00 UTC daily

---

## The Problem

Medical researchers spend 10–20 hours per week manually reviewing new papers to track whether existing clinical claims have been confirmed, contradicted, or updated. This process is slow, error-prone, and doesn't scale.

## What clinical-agent Does

1. **Fetches** 5–10 new ArXiv medical papers every day via parallel async requests
2. **Extracts** 3–5 factual claims per paper using Groq LLaMA 3.3 70B
3. **Compares** claims against a 3,245-chunk knowledge base (BM25 + dense hybrid)
4. **Detects** contradictions using Groq NLI (parallel, 42ms/claim)
5. **Alerts** via Slack with severity classification (critical/major/minor)
6. **Logs** everything to PostgreSQL with full audit trail

---

## Architecture

```
ArXiv API
    ↓
paper_monitor → claim_extractor → compare_claims → detect_conflict
                     ↑                                    ↓
              Rust claim-parser                    Groq NLI parallel
              (actix-web :8002)                         ↓
                                                    alert_node → Slack
                                                        ↓
                                               faithfulness_eval
                                               (sentence-transformers)
                                                        ↓
                                                   audit_log → PostgreSQL
                                                        ↓
                                                 generate_report → .md
```

**Polyglot design:**

| Language | Layer | Role |
|----------|-------|------|
| Python | Orchestration | LangGraph pipeline, LLM calls, scheduler |
| Rust | Performance | claim-parser microservice (actix-web) |
| Go | Networking | arxiv-research-assistant (external repo) |
| SQL | Data | PostgreSQL 16 + pgvector |

---

## Benchmark Results

All benchmarks run on WSL2, CPU-only, no GPU.

### Extraction Layer (Rust claim-parser)

| Mode | Papers | Time |
|------|--------|------|
| Sequential Python baseline | 5 | ~58 min |
| **Parallel Rust async** | 5 | **963ms** |

**Speedup: ~3,600x** — Rust JSON parse+validate: <1ms per claim.

### Conflict Detection (Groq NLI)

| Mode | Claims | Time | Per Claim |
|------|--------|------|-----------|
| DeBERTa CPU baseline | 16 | 292,122ms | 18,258ms |
| **Groq NLI parallel** | 16 | **672ms** | **42ms** |

**Speedup: 435x**

### Faithfulness Evaluation (sentence-transformers)

| Mode | Texts | Time |
|------|-------|------|
| Ollama sequential baseline | ~90 | ~4 min |
| **sentence-transformers offline** | 90 | **5.3s** |

**Speedup: ~45x**

### End-to-End Pipeline

| Node | Time |
|------|------|
| fetch_papers | ~30s (ArXiv rate limit) |
| extract_claims | 963ms |
| compare_claims | ~3s |
| detect_conflict | 672ms |
| faithfulness_eval | 5.3s |
| audit_log | 203ms |
| generate_report | 9ms |
| **Total** | **~40s** (from ~65 min) |

**Overall pipeline speedup: ~97x**

---

## Services

```
:8001  rag-research       — BM25 + dense hybrid KB (Docker)
:8002  claim-parser       — Rust actix-web NLI service
:5432  PostgreSQL 16      — audit log, runs table (Docker)
:9091  Pushgateway        — Prometheus metrics receiver
:9090  Prometheus         — metrics storage
:3000  Grafana            — pipeline monitoring dashboard
```

---

## Quick Start

### Prerequisites

- Python 3.12+
- Rust 1.93+
- Docker + Docker Compose
- Groq API key (free at console.groq.com)
- Slack webhook URL

### Setup

```bash
# Clone
git clone https://github.com/malikimayzar/clinical-agent
cd clinical-agent

# Python deps
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Build Rust claim-parser
cd rust/claim-parser && cargo build --release && cd ../..

# Environment
cp .env.example .env
# Edit .env — tambahkan GROQ_API_KEY dan SLACK_WEBHOOK_URL

# Start semua services
bash start.sh
```

### Run Manual

```bash
python scheduler/daily_runner.py --run-now
```

### Scheduler (autonomous)

```bash
# Jalan otomatis 02:00 UTC setiap hari
python scheduler/daily_runner.py
```

---

## Environment Variables

```env
GROQ_API_KEY=            # Groq API key (required)
SLACK_WEBHOOK_URL=        # Slack incoming webhook (required)
POSTGRES_HOST=localhost
POSTGRES_DB=clinical_agent
POSTGRES_USER=maliki
POSTGRES_PASSWORD=
LANGCHAIN_API_KEY=        # LangSmith tracing (optional)
LANGCHAIN_TRACING_V2=true
LANGCHAIN_PROJECT=clinical-agent
TRANSFORMERS_OFFLINE=1    # Force local model, no HF Hub check
```

---

## Project Structure

```
clinical-agent/
├── agents/
│   ├── graph.py              # LangGraph StateGraph, 8 nodes
│   ├── state.py              # AgentState TypedDict
│   └── nodes/
│       ├── paper_monitor.py      # ArXiv fetch
│       ├── claim_extractor.py    # Groq + Rust parallel extraction
│       ├── claim_comparator.py   # RAG retrieval
│       ├── conflict_detector.py  # Groq NLI parallel
│       ├── alert_node.py         # Slack alert
│       ├── faithfulness_eval.py  # sentence-transformers
│       ├── audit_logger.py       # PostgreSQL logging
│       └── report_generator.py   # Markdown report
├── rust/
│   └── claim-parser/         # Rust actix-web microservice
│       ├── src/main.rs
│       ├── Cargo.toml
│       └── BENCHMARK.md
├── integrations/
│   ├── arxiv_service.py      # ArXiv + Go service client
│   ├── llm_eval.py           # FaithfulnessEvaluator wrapper
│   ├── rag_research.py       # KB retrieval client
│   └── mcp_gateway.py        # MCP tool gateway
├── monitoring/
│   ├── metrics.py            # Prometheus push metrics
│   ├── prometheus.yml        # Scrape config
│   └── grafana/              # Dashboard provisioning
├── scheduler/
│   └── daily_runner.py       # APScheduler + missed run recovery
├── db/
│   ├── schema.sql            # PostgreSQL schema
│   └── connection.py
├── docker-compose.yml        # PostgreSQL + rag-research
├── docker-compose.monitoring.yml  # Pushgateway + Prometheus + Grafana
└── start.sh                  # One-command boot semua services
```

---

## Monitoring

Grafana dashboard tersedia di `http://localhost:3000` (admin/clinical2026) setelah `bash start.sh`.

Dashboard mencakup:
- Pipeline runs (success/failure)
- Node latency P95 per LangGraph node
- Claims extracted & conflicts found per run
- Faithfulness score distribution
- Critical conflict history

---

## Knowledge Base

3,245 chunks dari 14 medical papers (Tier 1–3) covering:
- Mental health & depression treatment
- Alzheimer's disease subtypes
- Cancer immunotherapy
- Drug-drug interaction prediction
- COVID-19 treatment evidence
- Antibiotic resistance

---

## Roadmap

- [x] M1–M2: LangGraph 8-node pipeline
- [x] M3: NLI conflict detection
- [x] M5: Slack alert + KB medical
- [x] M7: APScheduler autonomous
- [x] M8: LangSmith + Grafana monitoring
- [x] M3–M4: Rust claim-parser (parallel async)
- [ ] M6: Rust similarity-engine
- [ ] M9: Rust PDF report exporter (Typst)
- [ ] M10: FastAPI REST + React dashboard
- [ ] M12: Deploy Render.com + demo video

---

## Related Repos

| Repo | Language | Role |
|------|----------|------|
| [rag-research](https://github.com/malikimayzar/rag-research) | Python | BM25+dense hybrid KB |
| [llm-eval-framework](https://github.com/malikimayzar/llm-eval-framework) | Python | Faithfulness evaluator |
| [arxiv-research-assistant](https://github.com/malikimayzar/arxiv-research-assistant) | Go+Python | Paper fetcher |
| [mcp-gateway](https://github.com/malikimayzar/mcp-gateway) | Go | LLM orchestration |

---

*Maliki Mayzar · clinical-agent v3.0 · Python + Rust + Go + LangGraph · Zero Budget. Full Power.*