#!/bin/bash
echo "Starting clinical-agent services..."

cd /mnt/d/clinical-agent

# PostgreSQL 
docker compose up -d postgres
echo "[OK] PostgreSQL started"

# rag-research 
if command -v tmux &> /dev/null; then
    tmux new-session -d -s rag -c /mnt/d/rag-research \
        "source venv/bin/activate && uvicorn api:app --host 0.0.0.0 --port 8001"
    echo "[OK] rag-research started (tmux session: rag)"
else
    cd /mnt/d/rag-research
    source venv/bin/activate
    nohup uvicorn api:app --host 0.0.0.0 --port 8001 > /tmp/rag.log 2>&1 &
    echo "[OK] rag-research started (background, log: /tmp/rag.log)"
    cd /mnt/d/clinical-agent
fi

# Rust claim-parser 
CLAIM_PARSER=/mnt/d/clinical-agent/rust/claim-parser/target/release/claim_parser
if [ -f "$CLAIM_PARSER" ]; then
    source /mnt/d/clinical-agent/.env 2>/dev/null
    nohup "$CLAIM_PARSER" > /tmp/claim_parser.log 2>&1 &
    echo "[OK] Rust claim-parser started (port 8002, log: /tmp/claim_parser.log)"
else
    echo "[WARN] Rust claim-parser binary tidak ditemukan, skip"
    echo "       Jalankan: cd rust/claim-parser && cargo build --release"
fi

# Monitoring stack (Pushgateway + Prometheus + Grafana) 
if [ -f "/mnt/d/clinical-agent/docker-compose.monitoring.yml" ]; then
    docker compose -f docker-compose.monitoring.yml up -d
    echo "[OK] Monitoring stack started (Grafana: http://localhost:3000)"
else
    echo "[WARN] docker-compose.monitoring.yml tidak ditemukan, skip monitoring"
fi

# Tunggu semua ready 
sleep 15

# Aktifkan venv 
cd /mnt/d/clinical-agent
source .venv/bin/activate

# Verifikasi 
echo ""
echo "=== Status ==="
echo -n "rag-research  (8001): " && curl -s http://localhost:8001/health
echo ""
echo -n "claim-parser  (8002): " && curl -s http://localhost:8002/health
echo ""
echo -n "pushgateway   (9091): " && curl -s -o /dev/null -w "HTTP %{http_code}" http://localhost:9091/-/ready
echo ""
echo -n "grafana       (3000): " && curl -s -o /dev/null -w "HTTP %{http_code}" http://localhost:3000/api/health
echo ""
python3 db/connection.py
echo ""
echo "[OK] Semua ready"