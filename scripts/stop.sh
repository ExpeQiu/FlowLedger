#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

for pidfile in .pids/api.pid .pids/web.pid; do
  if [ -f "$pidfile" ]; then
    pid=$(cat "$pidfile")
    if kill -0 "$pid" 2>/dev/null; then
      kill "$pid" 2>/dev/null || true
      echo "[stop] 已停止进程 $pid"
    fi
    rm -f "$pidfile"
  fi
done

docker compose stop postgres 2>/dev/null || true
echo "[stop] FlowLedger 已停止"
