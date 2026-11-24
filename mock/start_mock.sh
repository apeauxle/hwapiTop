#!/usr/bin/env bash
# dev helper: (re)start the mock HWiNFO API in the background
set -u
cd "$(dirname "$0")/.."
PORT="${1:-18080}"
if [ -f mock/mock.pid ]; then
    kill "$(cat mock/mock.pid)" 2>/dev/null || true
    sleep 0.3
fi
nohup ./mock/mock_hwinfo.py --port "$PORT" > mock/mock.log 2>&1 &
echo $! > mock/mock.pid
sleep 0.7
if curl -s --max-time 2 "http://127.0.0.1:${PORT}/api/ping" | grep -q '"pong"'; then
    echo "mock up on :${PORT} (pid $(cat mock/mock.pid))"
else
    echo "mock FAILED to start"; tail -5 mock/mock.log; exit 1
fi
