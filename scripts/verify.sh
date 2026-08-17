#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
source "$ROOT/scripts/lib/pg.sh"

if [ -f .env ]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

# 云端：/opt/flowledger/.env 或 DEPLOY_ENV=cloud
IS_CLOUD=0
if [ "${DEPLOY_ENV:-}" = "cloud" ] || [ -f /opt/flowledger/.env ] || [ "$(uname -s)" = "Linux" ]; then
  if [ -f /opt/flowledger/.env ] || [ "${DEPLOY_ENV:-}" = "cloud" ]; then
    IS_CLOUD=1
  fi
fi

API_PORT="${API_PORT:-9011}"
if [ "$IS_CLOUD" -eq 1 ]; then
  WEB_PORT="${WEB_PORT:-8900}"
  PG_HOST="${PG_HOST:-127.0.0.1}"
  # 从 deploy/.env.pg 注入 psql 密码
  if [ -f "$ROOT/deploy/.env.pg" ]; then
    # shellcheck disable=SC1091
    set -a && source "$ROOT/deploy/.env.pg" && set +a
    export PGPASSWORD="${POSTGRES_PASSWORD:-${PGPASSWORD:-}}"
  fi
else
  WEB_PORT="${WEB_PORT:-5011}"
fi

PASS=0
FAIL=0

check() {
  if eval "$2"; then
    echo "  ✓ $1"
    PASS=$((PASS + 1))
  else
    echo "  ✗ $1"
    FAIL=$((FAIL + 1))
  fi
}

if [ "$IS_CLOUD" -eq 1 ]; then
  echo "=== FlowLedger 验证（云端 · 共用 stock-pg）==="
  check "stock-pg 容器运行" "docker exec stock-pg pg_isready -U stock -d invest >/dev/null 2>&1"
  check "flowledger 库可连接" "PGPASSWORD=\"\${PGPASSWORD:-}\" psql -h 127.0.0.1 -p 5432 -U flowledger -d flowledger -c 'SELECT 1' >/dev/null 2>&1 || pg_connect"
  check "PM2 flowledger-api" "pm2 describe flowledger-api 2>/dev/null | grep -q online"
  check "PM2 flowledger-web" "pm2 describe flowledger-web 2>/dev/null | grep -q online"
  check "cron /etc/cron.d/flowledger" "test -f /etc/cron.d/flowledger"
else
  echo "=== FlowLedger 验证（本地优先）==="
  check "本地 PostgreSQL 运行" "pg_local_ready"
  check "本地 PostgreSQL 可连接" "pg_connect"
fi

TABLES="accounts categories transactions budgets holdings liabilities goals recurring_bills rules import_jobs"
for t in $TABLES; do
  if [ "$IS_CLOUD" -eq 1 ]; then
    check "表 $t 存在" "psql -h 127.0.0.1 -U flowledger -d flowledger -tAc \"SELECT 1 FROM information_schema.tables WHERE table_name='$t'\" 2>/dev/null | grep -q 1 || pg_psql -tAc \"SELECT 1 FROM information_schema.tables WHERE table_name='$t'\" 2>/dev/null | grep -q 1"
  else
    check "表 $t 存在" "pg_psql -tAc \"SELECT 1 FROM information_schema.tables WHERE table_name='$t'\" 2>/dev/null | grep -q 1"
  fi
done

check "API health" "curl -sf http://127.0.0.1:$API_PORT/health | grep -q ok"
check "Dashboard API" "curl -sf 'http://127.0.0.1:$API_PORT/api/dashboard' | grep -q net_worth"
check "转账明细 API" "curl -sf 'http://127.0.0.1:$API_PORT/api/transactions/transfers' | grep -q '\\['"
check "投资组合 API" "curl -sf 'http://127.0.0.1:$API_PORT/api/holdings/summary' | grep -q total_value"
check "投资账户校验" "curl -sf 'http://127.0.0.1:$API_PORT/api/holdings/validate' | grep -q '\"ok\"'"
check "投资账户校验通过" "curl -sf 'http://127.0.0.1:$API_PORT/api/holdings/validate' | grep -q '\"ok\":true'"
check "Web 可访问" "curl -sf -o /dev/null -w '%{http_code}' http://127.0.0.1:$WEB_PORT | grep -q 200"

# 净资产未重复计入持仓；与 Σ账户余额（信用卡镜像去重后）对齐
if curl -sf "http://127.0.0.1:$API_PORT/api/dashboard" >/tmp/fl_dash.json 2>/dev/null \
  && curl -sf "http://127.0.0.1:$API_PORT/api/holdings/summary" >/tmp/fl_holdings.json 2>/dev/null \
  && curl -sf "http://127.0.0.1:$API_PORT/api/accounts" >/tmp/fl_accounts.json 2>/dev/null \
  && curl -sf "http://127.0.0.1:$API_PORT/api/accounts/net-worth" >/tmp/fl_nw.json 2>/dev/null; then
  check "净资产未叠加持仓" "python3 - <<'PY'
import json
dash = json.load(open('/tmp/fl_dash.json'))
holdings = json.load(open('/tmp/fl_holdings.json'))
accounts = json.load(open('/tmp/fl_accounts.json'))
nw_api = json.load(open('/tmp/fl_nw.json'))
acc_sum = sum(float(a['balance']) for a in accounts)
nw = float(dash['net_worth'])
nw2 = float(nw_api['net_worth'])
hv = float(holdings.get('holdings_value') or 0)
tv = float(holdings.get('total_value') or 0)
cash = float(holdings.get('cash_balance') or 0)
assert abs(nw - nw2) < 0.02, f'dashboard/net-worth 不一致 {nw} vs {nw2}'
# 允许信用卡镜像后 nw≈acc_sum；严禁 nw≈acc_sum+holdings
assert abs(nw - (acc_sum + hv)) > max(hv * 0.5, 1) or hv < 1, '疑似重复计入持仓'
assert abs(tv - (hv + cash)) < 1.0, f'total={tv} hv={hv} cash={cash}'
invest = [a for a in accounts if a.get('is_invest')]
for a in invest:
    assert a.get('holdings_mv') is not None and a.get('cash') is not None
    assert abs(float(a['balance']) - float(a['holdings_mv']) - float(a['cash'])) < 0.02
# 本月支出 = 已记账 + 待落账定期
booked = float(dash.get('expense_booked') or 0)
pending = float(dash.get('expense_recurring_pending') or 0)
exp = float(dash['monthly_expense'])
assert abs(exp - (booked + pending)) < 0.02, f'支出口径不一致 {exp} != {booked}+{pending}'
print('ok')
PY
"
fi

# 定期账单字段存在
check "Dashboard 支出口径字段" "curl -sf 'http://127.0.0.1:$API_PORT/api/dashboard' | grep -q expense_recurring_pending"

echo ""
echo "通过: $PASS  失败: $FAIL"
[ "$FAIL" -eq 0 ]
