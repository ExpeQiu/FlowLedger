#!/usr/bin/env bash
# materialize-due-bills.sh — 自动落账到期的定期账单
#
# 流程：
#   1. 调 POST /api/recurring-bills/materialize-due（只处理 auto_create=true）
#   2. 若有新建流水，触发 Mac → 云端库推送（保持双库一致）
#
# 说明：
#   - 真源 = Mac 本地 PostgreSQL；云端为副本，由 push-db-to-cloud.sh 同步
#   - 幂等：同月同账户同金额同商户已有流水会跳过，不会重复出账
#   - 按 next_due 精确到日：1 号的账单 1 号出，10 号的养老金 10 号出
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

LOG_DIR="$ROOT/logs"
mkdir -p "$LOG_DIR"
LOG="$LOG_DIR/materialize-due-bills.log"

API_URL="${FLOWLEDGER_API_URL:-http://127.0.0.1:9011}"

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG"; }

log "════════════════════════════════════════"
log "  定期账单自动落账启动"

# 等 API 就绪（最多 60s）
for i in $(seq 1 30); do
  if curl -fsS -o /dev/null "${API_URL}/health" 2>/dev/null; then
    break
  fi
  sleep 2
done

if ! curl -fsS -o /dev/null "${API_URL}/health" 2>/dev/null; then
  log "✗ API 未就绪 ${API_URL}，跳过本次落账"
  exit 1
fi

RESULT=$(curl -fsS -X POST "${API_URL}/api/recurring-bills/materialize-due" 2>&1)
RC=$?
if [[ $RC -ne 0 ]]; then
  log "✗ 落账失败 rc=${RC}: ${RESULT}"
  exit 1
fi

log "✓ 落账结果: ${RESULT}"

CREATED=$(printf '%s' "$RESULT" | python3 -c "import sys,json; print(json.load(sys.stdin).get('created',0))" 2>/dev/null || echo 0)

if [[ "$CREATED" -gt 0 ]]; then
  log "▶ 新增 ${CREATED} 笔，触发云端同步"
  if bash "$ROOT/scripts/deploy/push-db-to-cloud.sh" >>"$LOG" 2>&1; then
    log "✓ 云端同步完成"
  else
    log "⚠️ 云端同步失败（下次定时推送会补上）"
  fi
else
  log "↷ 无新增账单，无需同步"
fi

log "════════════════════════════════════════"
exit 0
