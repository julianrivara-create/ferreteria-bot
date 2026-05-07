#!/usr/bin/env bash
# Restart the ferreteria training dashboard.
# Finds the process listening on port 5001 (most reliable) and replaces it.

set -e

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

LOG_FILE="${FERRETERIA_LOG:-/tmp/ferreteria_server.log}"

EXISTING_PID=$(lsof -ti :5001 2>/dev/null || true)
if [ -n "$EXISTING_PID" ]; then
    echo "[restart-dashboard] killing PID=$EXISTING_PID on port 5001..."
    kill "$EXISTING_PID" 2>/dev/null || true
    sleep 1
    if kill -0 "$EXISTING_PID" 2>/dev/null; then
        kill -9 "$EXISTING_PID" 2>/dev/null || true
        sleep 1
    fi
fi

echo "[restart-dashboard] starting new instance..."
set -a
source .env
set +a
PYTHONPATH="$REPO_ROOT" nohup python3 -c "from app.main import create_app; app = create_app(); app.run(host='0.0.0.0', port=5001)" > "$LOG_FILE" 2>&1 &
NEW_PID=$!
echo "[restart-dashboard] launched PID=$NEW_PID, logs at $LOG_FILE"

sleep 3
if curl -fs http://localhost:5001/health > /dev/null 2>&1; then
    echo "[restart-dashboard] healthy"
    exit 0
else
    echo "[restart-dashboard] health check FAILED; check $LOG_FILE"
    tail -20 "$LOG_FILE"
    exit 1
fi
