#!/bin/bash
echo "Starting clinical-agent services..."

# 1. PostgreSQL
cd /mnt/d/clinical-agent
docker compose up -d postgres
echo "[OK] PostgreSQL started"

# 2. rag-research (terminal terpisah via tmux)
if command -v tmux &> /dev/null; then
    tmux new-session -d -s rag -c /mnt/d/rag-research \
        "source venv/bin/activate && uvicorn api:app --host 0.0.0.0 --port 8001"
    echo "[OK] rag-research started (tmux session: rag)"
else
    cd /mnt/d/rag-research
    source venv/bin/activate
    nohup uvicorn api:app --host 0.0.0.0 --port 8001 > /tmp/rag.log 2>&1 &
    echo "[OK] rag-research started (background, log: /tmp/rag.log)"
fi

# 3. Tunggu semua ready
sleep 15

# 4. Aktifkan venv clinical-agent
cd /mnt/d/clinical-agent
source .venv/bin/activate

# 5. Verifikasi
echo ""
echo "=== Status ==="
curl -s http://localhost:8001/health
echo ""
python3 db/connection.py
echo ""
echo "[OK] Semua ready"