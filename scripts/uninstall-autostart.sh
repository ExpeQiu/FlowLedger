#!/usr/bin/env bash
set -euo pipefail

LABEL="com.flowledger.start"
PLIST_DST="$HOME/Library/LaunchAgents/${LABEL}.plist"
UID_NUM="$(id -u)"

if [ -f "$PLIST_DST" ]; then
  launchctl bootout "gui/${UID_NUM}" "$PLIST_DST" 2>/dev/null || true
  rm -f "$PLIST_DST"
  echo "[uninstall-autostart] 已移除 LaunchAgent"
else
  echo "[uninstall-autostart] 未找到已安装的 LaunchAgent"
fi
