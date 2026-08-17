#!/usr/bin/env bash
# 卸载 FlowLedger macOS LaunchAgent
set -euo pipefail

UID_NUM="$(id -u)"
DOMAIN="gui/${UID_NUM}"
LAUNCH_AGENTS="$HOME/Library/LaunchAgents"

bootout_label() {
  local label="$1"
  launchctl bootout "${DOMAIN}/${label}" 2>/dev/null || true
  launchctl bootout "$DOMAIN" "$LAUNCH_AGENTS/${label}.plist" 2>/dev/null || true
  rm -f "$LAUNCH_AGENTS/${label}.plist"
}

removed=0
for label in com.flowledger.api com.flowledger.web com.flowledger.start; do
  if [ -f "$LAUNCH_AGENTS/${label}.plist" ] || launchctl print "${DOMAIN}/${label}" >/dev/null 2>&1; then
    bootout_label "$label"
    removed=1
    echo "[uninstall-autostart] 已移除 $label"
  fi
done

if [ "$removed" -eq 0 ]; then
  echo "[uninstall-autostart] 未找到已安装的 LaunchAgent"
fi
