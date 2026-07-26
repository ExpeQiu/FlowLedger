#!/usr/bin/env bash
# 从 invest.lcteam 同步真实持仓到 flowledger
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [ -f .env ]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi
API_PORT="${API_PORT:-9011}"

echo "=== 同步 invest → flowledger ==="
if curl -sf "http://127.0.0.1:$API_PORT/health" >/dev/null 2>&1; then
  curl -sf -X POST "http://127.0.0.1:$API_PORT/api/holdings/sync-from-invest" | python3 -m json.tool
else
  echo "API 未运行，改用本地脚本同步..."
  cd "$ROOT/api"
  ../api/.venv/bin/python - <<'PY'
from database import SessionLocal
from services.invest_sync import sync_invest_to_flowledger
from services.finance import validate_invest_accounts
import json

db = SessionLocal()
try:
    result = sync_invest_to_flowledger(db)
    v = validate_invest_accounts(db)
    result["validation_ok"] = v.ok
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
finally:
    db.close()
PY
fi
