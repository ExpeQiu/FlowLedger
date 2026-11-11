#!/usr/bin/env bash
# push-db-to-cloud.sh — 将本机 flowledger 推送到云端共用 stock-pg 的 flowledger 库
# 真源：Mac 本地 PostgreSQL；云端为副本
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
LOG_DIR="$ROOT/logs"
mkdir -p "$LOG_DIR"
LOG="$LOG_DIR/push-db-to-cloud.log"
LOCK_DIR="$LOG_DIR/push-db-to-cloud.lockdir"
STAMP="$(date '+%Y%m%d-%H%M%S')"
DUMP="/tmp/flowledger-push-$STAMP.sql"
STRIPPED="/tmp/flowledger-push-$STAMP.pg16.sql"
DRY=0
[[ "${1:-}" == "--dry-run" ]] && DRY=1

log() { echo "[$(date '+%H:%M:%S')] $*" | tee -a "$LOG"; }

release_lock() { rm -rf "$LOCK_DIR" 2>/dev/null || true; }
cleanup() {
  rm -f "$DUMP" "$STRIPPED" 2>/dev/null || true
  release_lock
}
trap cleanup EXIT

# macOS 无 flock：目录锁。上一趟仍在跑则跳过，死锁可回收
if ! mkdir "$LOCK_DIR" 2>/dev/null; then
  old_pid="$(cat "$LOCK_DIR/pid" 2>/dev/null || true)"
  if [[ -n "${old_pid}" ]] && kill -0 "${old_pid}" 2>/dev/null; then
    log "↷ 已有推送在跑 pid=${old_pid}，跳过 $STAMP"
    trap - EXIT
    exit 0
  fi
  log "warn: stale lock, retry"
  rm -rf "$LOCK_DIR"
  if ! mkdir "$LOCK_DIR" 2>/dev/null; then
    log "↷ 无法取得锁，跳过 $STAMP"
    trap - EXIT
    exit 0
  fi
fi
echo $$ >"$LOCK_DIR/pid"

# shellcheck disable=SC1091
[[ -f "$ROOT/.env.cloud.local" ]] && set -a && source "$ROOT/.env.cloud.local" && set +a
# shellcheck disable=SC1091
[[ -f "$ROOT/.env" ]] && set -a && source "$ROOT/.env" && set +a

LOCAL_URL="${LOCAL_DATABASE_URL:-${DATABASE_URL:-postgresql://flowledger:flowledger@127.0.0.1:5432/flowledger}}"
CLOUD_URL="${CLOUD_DATABASE_URL:-}"
if [[ -z "$CLOUD_URL" ]]; then
  log "✗ 缺少 CLOUD_DATABASE_URL（写在 .env.cloud.local）"
  exit 1
fi

LOCAL_PORT="${FLOWLEDGER_TUNNEL_LOCAL_PORT:-15433}"

log "════════════════════════════════════════"
log "  Mac → 云 flowledger 推送 · $STAMP"
log "════════════════════════════════════════"

log "▶ 确保隧道 :${LOCAL_PORT}"
bash "$ROOT/scripts/deploy/db-tunnel.sh" -d

if ! pg_isready -h 127.0.0.1 -p 5432 >/dev/null 2>&1; then
  log "✗ 本机 PostgreSQL 未响应"
  exit 1
fi

log "▶ pg_dump flowledger"
pg_dump -Fp --no-owner --no-acl --clean --if-exists "$LOCAL_URL" -f "$DUMP"
python3 "$ROOT/scripts/deploy/strip-pg18-dump.py" "$DUMP" "$STRIPPED"
log "✓ dump $(wc -c <"$STRIPPED" | tr -d ' ') bytes"

if [[ "$DRY" -eq 1 ]]; then
  log "↷ dry-run"
  exit 0
fi

log "▶ 恢复到云端（单事务，失败则回滚）"
set +e
psql "$CLOUD_URL" -v ON_ERROR_STOP=1 --single-transaction -f "$STRIPPED" >>"$LOG" 2>&1
RC=$?
set -e
if [[ "$RC" -ne 0 ]]; then
  log "✗ 恢复失败 rc=$RC，详见 $LOG"
  exit 1
fi
log "✓ 云端恢复完成"
log "════════════════════════════════════════"
log "  推送成功"
log "════════════════════════════════════════"
