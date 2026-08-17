#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

UID_NUM="$(id -u)"
DOMAIN="gui/${UID_NUM}"

if [ -f .env ]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi
API_PORT="${API_PORT:-9011}"
WEB_PORT="${WEB_PORT:-5011}"

# KeepAlive 下必须先 bootout，否则杀进程会被立刻拉起
for label in com.flowledger.api com.flowledger.web com.flowledger.start; do
  if launchctl print "${DOMAIN}/${label}" >/dev/null 2>&1; then
    launchctl bootout "${DOMAIN}/${label}" 2>/dev/null || true
    echo "[stop] 已卸下 LaunchAgent $label"
  fi
done

for pidfile in .pids/api.pid .pids/web.pid; do
  if [ -f "$pidfile" ]; then
    pid=$(cat "$pidfile")
    if kill -0 "$pid" 2>/dev/null; then
      kill "$pid" 2>/dev/null || true
      pkill -P "$pid" 2>/dev/null || true
      echo "[stop] 已停止进程 $pid"
    fi
    rm -f "$pidfile"
  fi
done

pkill -f "$ROOT/api/.venv/bin/uvicorn main:app" 2>/dev/null || true
pkill -f "$ROOT/web/node_modules/.bin/next" 2>/dev/null || true
pkill -f "$ROOT/web/node_modules/next/dist/bin/next" 2>/dev/null || true

for port in "$API_PORT" "$WEB_PORT"; do
  pids="$(lsof -tiTCP:"$port" -sTCP:LISTEN 2>/dev/null || true)"
  if [ -n "$pids" ]; then
    echo "[stop] 释放端口 $port (pids: $pids)"
    # shellcheck disable=SC2086
    kill $pids 2>/dev/null || true
    sleep 1
    pids="$(lsof -tiTCP:"$port" -sTCP:LISTEN 2>/dev/null || true)"
    if [ -n "$pids" ]; then
      # shellcheck disable=SC2086
      kill -9 $pids 2>/dev/null || true
    fi
  fi
done

docker compose stop postgres 2>/dev/null || true
echo "[stop] FlowLedger 已停止（plist 仍保留，可用 start.sh / 下次登录再拉起）"
