#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
source "$ROOT/scripts/lib/pg.sh"

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

check "API health" "curl -sf http://localhost:8000/health | grep -q ok"
check "Dashboard API" "curl -sf 'http://localhost:8000/api/dashboard' | grep -q net_worth"
check "Web 可访问" "curl -sf -o /dev/null -w '%{http_code}' http://localhost:3000 | grep -q 200"

echo ""
echo "通过: $PASS  失败: $FAIL"
[ "$FAIL" -eq 0 ]
