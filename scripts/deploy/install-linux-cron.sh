#!/usr/bin/env bash
# 云端：持仓从同机 invest 同步 + 小时级 verify（不外采）
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
mkdir -p "$ROOT/logs"

WRAPPER="$ROOT/scripts/deploy/run-with-env.sh"
cat > "$WRAPPER" <<EOF
#!/usr/bin/env bash
set -euo pipefail
ROOT="$ROOT"
cd "\$ROOT"
set -a
[[ -f "\$ROOT/.env" ]] && source "\$ROOT/.env"
set +a
export DEPLOY_ENV=cloud
export PATH="/root/.local/bin:/usr/local/bin:/usr/bin:/bin:\$PATH"
exec "\$@"
EOF
chmod +x "$WRAPPER"

CRON_FILE="/etc/cron.d/flowledger"
cat > "$CRON_FILE" <<EOF
# FlowLedger · 云端派生任务（invest 真源 = Mac 经 stock 推送）
SHELL=/bin/bash
PATH=/usr/local/bin:/usr/bin:/bin
TZ=Asia/Shanghai

# 每 30 分钟：同机 invest → flowledger holdings
*/30 * * * * root $WRAPPER bash $ROOT/scripts/sync-invest.sh >>$ROOT/logs/sync-invest-cron.log 2>&1

# 健康巡检每小时
20 * * * * root $WRAPPER bash $ROOT/scripts/verify.sh >>$ROOT/logs/verify-cron.log 2>&1
EOF
chmod 644 "$CRON_FILE"

systemctl enable crond 2>/dev/null || systemctl enable cron 2>/dev/null || true
systemctl restart crond 2>/dev/null || systemctl restart cron 2>/dev/null || true

echo "[linux-cron] 已安装: $CRON_FILE"
cat "$CRON_FILE"
