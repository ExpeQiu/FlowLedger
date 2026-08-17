#!/usr/bin/env bash
# launchd KeepAlive · API 前台进程（由 launchd 托管，崩溃自动拉起）
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

export PATH="/opt/homebrew/bin:/opt/homebrew/sbin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:${PATH:-}"

mkdir -p logs
LOG="$ROOT/logs/daemon-api.log"
API_PORT="${API_PORT:-9011}"
UVICORN="$ROOT/api/.venv/bin/uvicorn"
MAX_WAIT=120

log() {
  echo "$(date '+%Y-%m-%d %H:%M:%S') [daemon-api] $*" | tee -a "$LOG"
}

log "starting ROOT=$ROOT port=$API_PORT"

if [ -f "$ROOT/.env" ]; then
  set -a
  # shellcheck disable=SC1091
  source "$ROOT/.env"
  set +a
fi
API_PORT="${API_PORT:-9011}"

# 等待 PostgreSQL
for i in $(seq 1 "$MAX_WAIT"); do
  if command -v pg_isready >/dev/null 2>&1 && pg_isready -h "${PG_HOST:-localhost}" -p "${PG_PORT:-5432}" -q 2>/dev/null; then
    log "PostgreSQL 就绪 (${i}s)"
    break
  fi
  if [ "$i" -eq "$MAX_WAIT" ]; then
    log "ERROR: PostgreSQL 在 ${MAX_WAIT}s 内未就绪"
    exit 1
  fi
  sleep 1
done

# 等待 venv
for i in $(seq 1 "$MAX_WAIT"); do
  if [ -x "$UVICORN" ]; then
    break
  fi
  if [ "$i" -eq "$MAX_WAIT" ]; then
    log "ERROR: uvicorn 不存在: $UVICORN"
    exit 78
  fi
  sleep 1
done

# 迁移（幂等）
log "alembic upgrade head"
(
  cd "$ROOT/api"
  ../api/.venv/bin/alembic upgrade head
  ../api/.venv/bin/python seed.py
) >>"$LOG" 2>&1 || {
  log "ERROR: 迁移/种子失败，见 $LOG"
  exit 1
}

log "exec uvicorn :$API_PORT"
cd "$ROOT/api"
exec "$UVICORN" main:app --host 127.0.0.1 --port "$API_PORT"
