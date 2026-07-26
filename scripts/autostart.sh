#!/usr/bin/env bash
# 开机/登录自启动入口：等待 PostgreSQL 就绪后启动 FlowLedger
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

mkdir -p logs
LOG="$ROOT/logs/autostart.log"

log() {
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG"
}

export PATH="/opt/homebrew/bin:/opt/homebrew/sbin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:${PATH:-}"

log "autostart 开始"

# 等待 PostgreSQL（开机时可能尚未就绪）
MAX_WAIT=120
for i in $(seq 1 "$MAX_WAIT"); do
  if command -v pg_isready >/dev/null 2>&1 && pg_isready -h localhost -p 5432 -q 2>/dev/null; then
    log "PostgreSQL 已就绪 (${i}s)"
    break
  fi
  if [ "$i" -eq "$MAX_WAIT" ]; then
    log "ERROR: PostgreSQL 在 ${MAX_WAIT}s 内未就绪，放弃启动"
    exit 1
  fi
  sleep 1
done

if "$ROOT/scripts/start.sh" >> "$LOG" 2>&1; then
  log "autostart 完成"
else
  log "ERROR: start.sh 失败"
  exit 1
fi
