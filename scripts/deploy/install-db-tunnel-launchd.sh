#!/usr/bin/env bash
# 安装 Mac 隧道保活 LaunchAgent（登录后每 5 分钟检查 :15433）
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
LABEL="com.flowledger.db-tunnel"
PLIST="$HOME/Library/LaunchAgents/${LABEL}.plist"
TUNNEL="$ROOT/scripts/deploy/db-tunnel.sh"

chmod +x "$TUNNEL"
mkdir -p "$ROOT/logs"

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
    <string>${TUNNEL}</string>
    <string>-d</string>
  </array>
  <key>RunAtLoad</key>
  <true/>
  <key>StartInterval</key>
  <integer>300</integer>
  <key>StandardOutPath</key>
  <string>${ROOT}/logs/db-tunnel-launchd.log</string>
  <key>StandardErrorPath</key>
  <string>${ROOT}/logs/db-tunnel-launchd-err.log</string>
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
bash "$TUNNEL" -d

echo "[db-tunnel] 已安装: $PLIST"
echo "[db-tunnel] 每 300s 检查 :15433；手动: bash $TUNNEL -d"
