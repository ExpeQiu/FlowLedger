#!/usr/bin/env bash
# 安装 Mac→云 flowledger 整库推送 LaunchAgent
# 默认：08:40 / 13:00 / 21:00（流水记账节奏；推送脚本内 flock 防并发）
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
LABEL="com.flowledger.push-db-cloud"
PLIST="$HOME/Library/LaunchAgents/${LABEL}.plist"
PUSH="$ROOT/scripts/deploy/push-db-to-cloud.sh"
TUNNEL_INSTALL="$ROOT/scripts/deploy/install-db-tunnel-launchd.sh"

chmod +x "$PUSH" "$ROOT/scripts/deploy/db-tunnel.sh"
mkdir -p "$ROOT/logs"

if [[ ! -f "$ROOT/.env.cloud.local" ]]; then
  echo "[push-db-cloud] ✗ 缺少 .env.cloud.local（先跑一次 deploy-aliyun.sh 或手写 CLOUD_DATABASE_URL）"
  exit 1
fi

# 隧道保活一并装上
bash "$TUNNEL_INSTALL"

INTERVALS=$(cat <<'XML'
  <array>
    <dict><key>Hour</key><integer>8</integer><key>Minute</key><integer>40</integer></dict>
    <dict><key>Hour</key><integer>13</integer><key>Minute</key><integer>0</integer></dict>
    <dict><key>Hour</key><integer>21</integer><key>Minute</key><integer>0</integer></dict>
  </array>
XML
)

cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>${LABEL}</string>
  <key>ProgramArguments</key>
  <array>
    <string>/bin/bash</string>
    <string>${PUSH}</string>
  </array>
  <key>RunAtLoad</key>
  <false/>
  <key>StartCalendarInterval</key>
${INTERVALS}
  <key>StandardOutPath</key>
  <string>${ROOT}/logs/push-db-cloud-launchd.log</string>
  <key>StandardErrorPath</key>
  <string>${ROOT}/logs/push-db-cloud-launchd-err.log</string>
  <key>EnvironmentVariables</key>
  <dict>
    <key>PATH</key>
    <string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin</string>
    <key>HOME</key>
    <string>${HOME}</string>
  </dict>
</dict>
</plist>
EOF

launchctl bootout "gui/$(id -u)/${LABEL}" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$PLIST"

echo "[push-db-cloud] 已安装: $PLIST"
echo "[push-db-cloud] 日程: 08:40 / 13:00 / 21:00"
echo "[push-db-cloud] 手动: bash $PUSH"
echo "[push-db-cloud] 日志: $ROOT/logs/push-db-to-cloud.log"
echo "[push-db-cloud] 卸载: launchctl bootout gui/\$(id -u)/${LABEL} && rm -f $PLIST"
