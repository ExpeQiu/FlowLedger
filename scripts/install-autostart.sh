#!/usr/bin/env bash
# 安装 macOS LaunchAgent（登录自启 + KeepAlive 崩溃自动拉起）
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
UID_NUM="$(id -u)"
DOMAIN="gui/${UID_NUM}"
LAUNCH_AGENTS="$HOME/Library/LaunchAgents"

API_LABEL="com.flowledger.api"
WEB_LABEL="com.flowledger.web"
OLD_LABEL="com.flowledger.start"

chmod +x \
  "$ROOT/scripts/daemon-api.sh" \
  "$ROOT/scripts/daemon-web.sh" \
  "$ROOT/scripts/start.sh" \
  "$ROOT/scripts/stop.sh" \
  "$ROOT/scripts/autostart.sh"

mkdir -p "$LAUNCH_AGENTS" "$ROOT/logs" "$ROOT/.pids"

if [ -f "$ROOT/.env" ]; then
  set -a
  # shellcheck disable=SC1091
  source "$ROOT/.env"
  set +a
fi
API_PORT="${API_PORT:-9011}"
WEB_PORT="${WEB_PORT:-5011}"

bootout_label() {
  local label="$1"
  launchctl bootout "${DOMAIN}/${label}" 2>/dev/null || true
  launchctl bootout "$DOMAIN" "$LAUNCH_AGENTS/${label}.plist" 2>/dev/null || true
}

# 卸旧 oneshot + 现有 KeepAlive
for label in "$OLD_LABEL" "$API_LABEL" "$WEB_LABEL"; do
  bootout_label "$label"
done
rm -f "$LAUNCH_AGENTS/${OLD_LABEL}.plist"

# 释放端口，避免旧 nohup 进程占位
for port in "$API_PORT" "$WEB_PORT"; do
  pids="$(lsof -tiTCP:"$port" -sTCP:LISTEN 2>/dev/null || true)"
  if [ -n "$pids" ]; then
    echo "[install-autostart] 释放端口 $port (pids: $pids)"
    # shellcheck disable=SC2086
    kill $pids 2>/dev/null || true
    sleep 1
    pids="$(lsof -tiTCP:"$port" -sTCP:LISTEN 2>/dev/null || true)"
    if [ -n "$pids" ]; then
      # shellcheck disable=SC2086
      kill -9 $pids 2>/dev/null || true
    fi
  fi
done
pkill -f "$ROOT/api/.venv/bin/uvicorn main:app" 2>/dev/null || true
pkill -f "$ROOT/web/node_modules/.bin/next" 2>/dev/null || true
pkill -f "$ROOT/web/node_modules/next/dist/bin/next" 2>/dev/null || true

write_plist() {
  local label="$1"
  local src="$ROOT/scripts/launchd/${label}.plist"
  local dst="$LAUNCH_AGENTS/${label}.plist"
  sed \
    -e "s|__FLOWLEDGER_ROOT__|$ROOT|g" \
    -e "s|__FLOWLEDGER_HOME__|$HOME|g" \
    -e "s|__FLOWLEDGER_API_PORT__|$API_PORT|g" \
    -e "s|__FLOWLEDGER_WEB_PORT__|$WEB_PORT|g" \
    "$src" > "$dst"
}

write_plist "$API_LABEL"
write_plist "$WEB_LABEL"

launchctl bootstrap "$DOMAIN" "$LAUNCH_AGENTS/${API_LABEL}.plist"
launchctl bootstrap "$DOMAIN" "$LAUNCH_AGENTS/${WEB_LABEL}.plist"
launchctl enable "${DOMAIN}/${API_LABEL}" 2>/dev/null || true
launchctl enable "${DOMAIN}/${WEB_LABEL}" 2>/dev/null || true
launchctl kickstart -k "${DOMAIN}/${API_LABEL}"
launchctl kickstart -k "${DOMAIN}/${WEB_LABEL}"

echo "[install-autostart] 已安装 KeepAlive LaunchAgent"
echo "  API:  $LAUNCH_AGENTS/${API_LABEL}.plist"
echo "  Web:  $LAUNCH_AGENTS/${WEB_LABEL}.plist"
echo "  日志: $ROOT/logs/daemon-api.log  $ROOT/logs/daemon-web.log"
echo "  卸载: $ROOT/scripts/uninstall-autostart.sh"

ok=0
for i in $(seq 1 60); do
  if curl -sf --max-time 2 "http://127.0.0.1:$API_PORT/health" >/dev/null 2>&1 \
    && curl -sf --max-time 2 "http://127.0.0.1:$WEB_PORT/" >/dev/null 2>&1; then
    ok=1
    break
  fi
  sleep 1
done

if [ "$ok" -eq 1 ]; then
  echo "[install-autostart] 服务就绪  Web=http://127.0.0.1:$WEB_PORT  API=http://127.0.0.1:$API_PORT"
else
  echo "[install-autostart] WARN: 启动超时，查看日志:"
  tail -20 "$ROOT/logs/daemon-api.log" 2>/dev/null || true
  tail -20 "$ROOT/logs/launchd-api.err.log" 2>/dev/null || true
  tail -20 "$ROOT/logs/daemon-web.log" 2>/dev/null || true
  exit 1
fi
