#!/usr/bin/env bash
# 兼容旧 oneshot 入口：转发到 KeepAlive 安装/拉起
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LOG="$ROOT/logs/autostart.log"
mkdir -p "$ROOT/logs"

log() {
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG"
}

export PATH="/opt/homebrew/bin:/opt/homebrew/sbin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:${PATH:-}"

log "autostart: 转发到 install-autostart（KeepAlive）"
if "$ROOT/scripts/install-autostart.sh" >>"$LOG" 2>&1; then
  log "autostart 完成"
else
  log "ERROR: install-autostart 失败"
  exit 1
fi
