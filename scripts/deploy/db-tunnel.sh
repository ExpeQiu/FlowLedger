#!/usr/bin/env bash
# Mac 侧：SSH 本地转发，把云端 127.0.0.1:5432 映射到本机本地端口
# 用于 push-db-to-cloud（写 flowledger）或调试读 invest
#
# 用法:
#   bash scripts/deploy/db-tunnel.sh          # 前台
#   bash scripts/deploy/db-tunnel.sh -d       # 后台
#   bash scripts/deploy/db-tunnel.sh --stop
set -euo pipefail

HOST="${DEPLOY_HOST:-120.25.145.131}"
LOCAL_PORT="${FLOWLEDGER_TUNNEL_LOCAL_PORT:-15433}"
REMOTE_PORT=5432
# PID 文件固定放 /tmp：launchd 与交互 shell 的 TMPDIR 不同（launchd 无 TMPDIR 或为
# /var/folders/...），用 TMPDIR 会导致 --stop 在另一个上下文找不到 PID 文件、杀不掉隧道
PID_FILE="${FLOWLEDGER_TUNNEL_PID_FILE:-/tmp/flowledger-db-tunnel.pid}"

stop_tunnel() {
  if [[ -f "$PID_FILE" ]]; then
    kill "$(cat "$PID_FILE")" 2>/dev/null || true
    rm -f "$PID_FILE"
    echo "[tunnel] 已停止"
  else
    pkill -f "ssh.*-L ${LOCAL_PORT}:127.0.0.1:${REMOTE_PORT}.*${HOST}" 2>/dev/null || true
    echo "[tunnel] 已尝试清理"
  fi
}

if [[ "${1:-}" == "--stop" ]]; then
  stop_tunnel
  exit 0
fi

if lsof -iTCP:"$LOCAL_PORT" -sTCP:LISTEN >/dev/null 2>&1; then
  echo "[tunnel] 本机 :${LOCAL_PORT} 已在监听，跳过"
  exit 0
fi

ARGS=(-N -L "${LOCAL_PORT}:127.0.0.1:${REMOTE_PORT}" -o ExitOnForwardFailure=yes -o ServerAliveInterval=30 -o BatchMode=yes "root@${HOST}")

if [[ "${1:-}" == "-d" || "${1:-}" == "--daemon" ]]; then
  # 用 ssh -f（认证并绑定端口成功后才后台化）替代 ssh &，修两个问题：
  #   1) ssh & 会继承 stdout/stderr → 调用方管道永不 EOF
  #      （2026-11-12 实测：push-db-to-cloud.sh | tail 挂死 10 分钟不退）
  #   2) 两个实例并发时，守卫检查到端口空闲 → 双双启动 → 后启动者
  #      报 "Address already in use" 且覆盖 PID 文件（err 日志刷屏的根因）
  #      ssh -f 只有绑定成功才后台化，失败则直接退出并返回非 0
  ssh -f "${ARGS[@]}" </dev/null >/dev/null 2>"${TMPDIR:-/tmp}/flowledger-db-tunnel.err"
  sleep 1
  # 以"真正持有监听 socket 的进程"为准：ssh -f 会 fork，父进程很快退出，
  # pgrep 抓到的是短命父进程 → PID 文件记错 → --stop 杀不掉、留下僵尸隧道占端口
  TUNNEL_PID="$(lsof -nP -iTCP:"${LOCAL_PORT}" -sTCP:LISTEN -t 2>/dev/null | head -1 || true)"
  if [[ -z "$TUNNEL_PID" ]]; then
    TUNNEL_PID="$(pgrep -f "ssh .*-L ${LOCAL_PORT}:127.0.0.1:${REMOTE_PORT}" 2>/dev/null | head -1 || true)"
  fi
  if [[ -z "$TUNNEL_PID" ]]; then
    echo "[tunnel] ✗ 启动失败，详见 ${TMPDIR:-/tmp}/flowledger-db-tunnel.err" >&2
    exit 1
  fi
  echo "$TUNNEL_PID" > "$PID_FILE"
  echo "[tunnel] 后台 PID=${TUNNEL_PID} · 127.0.0.1:${LOCAL_PORT} → ${HOST}:${REMOTE_PORT}"
else
  echo "[tunnel] 前台转发 127.0.0.1:${LOCAL_PORT} → ${HOST}:${REMOTE_PORT}（Ctrl+C 结束）"
  exec ssh "${ARGS[@]}"
fi
