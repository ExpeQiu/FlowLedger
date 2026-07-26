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
API_PORT="${API_PORT:-9011}"
WEB_PORT="${WEB_PORT:-5011}"

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

echo "=== FlowLedger 验证（本地优先）==="

check "本地 PostgreSQL 运行" "pg_local_ready"
check "本地 PostgreSQL 可连接" "pg_connect"

TABLES="accounts categories transactions budgets holdings liabilities goals recurring_bills rules import_jobs"
for t in $TABLES; do
  check "表 $t 存在" "pg_psql -tAc \"SELECT 1 FROM information_schema.tables WHERE table_name='$t'\" 2>/dev/null | grep -q 1"
done

check "API health" "curl -sf http://localhost:$API_PORT/health | grep -q ok"
check "Dashboard API" "curl -sf 'http://localhost:$API_PORT/api/dashboard' | grep -q net_worth"
check "投资组合 API" "curl -sf 'http://localhost:$API_PORT/api/holdings/summary' | grep -q total_value"
check "投资账户校验" "curl -sf 'http://localhost:$API_PORT/api/holdings/validate' | grep -q '\"ok\"'"
check "投资账户校验通过" "curl -sf 'http://localhost:$API_PORT/api/holdings/validate' | grep -q '\"ok\":true'"
check "Web 可访问" "curl -sf -o /dev/null -w '%{http_code}' http://localhost:$WEB_PORT | grep -q 200"

# 净资产未重复计入持仓；与 Σ账户余额（信用卡镜像去重后）对齐
if curl -sf "http://localhost:$API_PORT/api/dashboard" >/tmp/fl_dash.json 2>/dev/null \
  && curl -sf "http://localhost:$API_PORT/api/holdings/summary" >/tmp/fl_holdings.json 2>/dev/null \
  && curl -sf "http://localhost:$API_PORT/api/accounts" >/tmp/fl_accounts.json 2>/dev/null \
  && curl -sf "http://localhost:$API_PORT/api/accounts/net-worth" >/tmp/fl_nw.json 2>/dev/null; then
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
print('ok')
PY
"
fi

echo ""
echo "通过: $PASS  失败: $FAIL"
[ "$FAIL" -eq 0 ]
