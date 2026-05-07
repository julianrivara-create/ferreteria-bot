#!/usr/bin/env bash
# Restart the ferreteria training dashboard.
# Kills any running instance and relaunches it in the background.

set -e

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

LOG_FILE="${FERRETERIA_LOG:-/tmp/ferreteria_server.log}"

echo "[restart-dashboard] killing previous instances..."
pkill -f "python.*app.py" 2>/dev/null || true
pkill -f "flask" 2>/dev/null || true
sleep 1

echo "[restart-dashboard] starting new instance..."
set -a
source .env
set +a
PYTHONPATH="$REPO_ROOT" nohup python3 app/app.py > "$LOG_FILE" 2>&1 &
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
