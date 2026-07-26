#!/usr/bin/env bash
# 安装 macOS LaunchAgent，登录后自动启动 FlowLedger
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LABEL="com.flowledger.start"
PLIST_SRC="$ROOT/scripts/launchd/${LABEL}.plist"
PLIST_DST="$HOME/Library/LaunchAgents/${LABEL}.plist"
UID_NUM="$(id -u)"

chmod +x "$ROOT/scripts/autostart.sh" "$ROOT/scripts/start.sh" "$ROOT/scripts/stop.sh"

mkdir -p "$HOME/Library/LaunchAgents" "$ROOT/logs"

# 写入 plist（替换项目路径）
sed "s|__FLOWLEDGER_ROOT__|$ROOT|g" "$PLIST_SRC" > "$PLIST_DST"

# 若已加载则先卸载
launchctl bootout "gui/${UID_NUM}" "$PLIST_DST" 2>/dev/null || true

launchctl bootstrap "gui/${UID_NUM}" "$PLIST_DST"
launchctl enable "gui/${UID_NUM}/${LABEL}" 2>/dev/null || true

echo "[install-autostart] 已安装 LaunchAgent"
echo "  plist: $PLIST_DST"
echo "  日志:  $ROOT/logs/autostart.log"
echo ""
echo "验证: launchctl print gui/${UID_NUM}/${LABEL}"
echo "卸载: $ROOT/scripts/uninstall-autostart.sh"
