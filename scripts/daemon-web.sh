#!/usr/bin/env bash
# launchd KeepAlive · Web 前台进程（由 launchd 托管，崩溃自动拉起）
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

export PATH="/opt/homebrew/bin:/opt/homebrew/sbin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:${PATH:-}"

mkdir -p logs
LOG="$ROOT/logs/daemon-web.log"
WEB_PORT="${WEB_PORT:-5011}"
NEXT_JS="$ROOT/web/node_modules/next/dist/bin/next"
NODE_BIN="$(command -v node || true)"
MAX_WAIT=120

log() {
  echo "$(date '+%Y-%m-%d %H:%M:%S') [daemon-web] $*" | tee -a "$LOG"
}

log "starting ROOT=$ROOT port=$WEB_PORT"

if [ -f "$ROOT/.env" ]; then
  set -a
  # shellcheck disable=SC1091
  source "$ROOT/.env"
  set +a
fi
WEB_PORT="${WEB_PORT:-5011}"

if [ -z "$NODE_BIN" ]; then
  for p in /opt/homebrew/bin/node /usr/local/bin/node; do
    if [ -x "$p" ]; then
      NODE_BIN="$p"
      break
    fi
  done
fi

for i in $(seq 1 "$MAX_WAIT"); do
  if [ -f "$NEXT_JS" ] && [ -n "$NODE_BIN" ] && [ -x "$NODE_BIN" ]; then
    break
  fi
  if [ "$i" -eq "$MAX_WAIT" ]; then
    log "ERROR: next/node 未就绪 next=$NEXT_JS node=$NODE_BIN"
    exit 78
  fi
  sleep 1
done

# 等 API 端口，避免首页首屏全失败
API_PORT="${API_PORT:-9011}"
for i in $(seq 1 60); do
  if curl -sf "http://127.0.0.1:$API_PORT/health" >/dev/null 2>&1; then
    log "API 已就绪 (${i}s)"
    break
  fi
  sleep 1
done

log "exec next dev :$WEB_PORT"
cd "$ROOT/web"
exec "$NODE_BIN" "$NEXT_JS" dev -p "$WEB_PORT" -H 127.0.0.1
