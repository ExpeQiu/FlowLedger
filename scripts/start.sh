#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

mkdir -p logs .pids
source "$ROOT/scripts/lib/pg.sh"

UID_NUM="$(id -u)"
DOMAIN="gui/${UID_NUM}"
API_LABEL="com.flowledger.api"
WEB_LABEL="com.flowledger.web"

log() {
  echo "[start] $(date '+%Y-%m-%d %H:%M:%S') $*"
}

free_port() {
  local port="$1"
  local pids
  pids="$(lsof -tiTCP:"$port" -sTCP:LISTEN 2>/dev/null || true)"
  if [ -n "$pids" ]; then
    log "释放端口 $port (pids: $pids)"
    # shellcheck disable=SC2086
    kill $pids 2>/dev/null || true
    sleep 1
    pids="$(lsof -tiTCP:"$port" -sTCP:LISTEN 2>/dev/null || true)"
    if [ -n "$pids" ]; then
      # shellcheck disable=SC2086
      kill -9 $pids 2>/dev/null || true
    fi
  fi
}

wait_http() {
  local url="$1"
  local name="$2"
  local max="${3:-30}"
  local i
  for i in $(seq 1 "$max"); do
    if curl -sf "$url" >/dev/null 2>&1; then
      log "$name 就绪 (${i}s) $url"
      return 0
    fi
    sleep 1
  done
  log "ERROR: $name 在 ${max}s 内未就绪: $url"
  return 1
}

agents_installed() {
  [ -f "$HOME/Library/LaunchAgents/${API_LABEL}.plist" ] \
    && [ -f "$HOME/Library/LaunchAgents/${WEB_LABEL}.plist" ]
}

if [ ! -f .env ]; then
  cp .env.example .env
  log "已从 .env.example 创建 .env"
fi

set -a
# shellcheck disable=SC1091
source .env
set +a

if [ ! -d api/.venv ]; then
  log "创建 Python 虚拟环境..."
  if command -v uv >/dev/null 2>&1; then
    uv venv --python 3.11 api/.venv
    uv pip install -r api/requirements.txt --python api/.venv/bin/python
  else
    PYTHON_BIN=""
    for py in python3.12 python3.11 python3; do
      if command -v "$py" >/dev/null 2>&1; then
        PYTHON_BIN="$py"
        break
      fi
    done
    "$PYTHON_BIN" -m venv api/.venv
    api/.venv/bin/pip install -q -r api/requirements.txt
  fi
fi

log "检查本地 PostgreSQL（优先）..."
if ! pg_ensure_local; then
  if [ "${USE_DOCKER_PG:-0}" = "1" ] && docker info >/dev/null 2>&1; then
    log "回退到 Docker PostgreSQL (USE_DOCKER_PG=1)..."
    docker compose up -d postgres
    for i in $(seq 1 30); do
      if docker compose exec -T postgres pg_isready -U flowledger -d flowledger >/dev/null 2>&1; then
        break
      fi
      sleep 1
    done
  else
    log "启动失败：请确保本地 PostgreSQL 已运行"
    echo "  1. brew services start postgresql@15"
    echo "  2. 或设置 USE_DOCKER_PG=1 使用 Docker"
    exit 1
  fi
fi

log "运行数据库迁移..."
cd api && ../api/.venv/bin/alembic upgrade head && ../api/.venv/bin/python seed.py
cd "$ROOT"

if [ ! -d web/node_modules ]; then
  log "安装 Web 依赖..."
  cd web && npm install
  cd "$ROOT"
fi

API_PORT="${API_PORT:-9011}"
WEB_PORT="${WEB_PORT:-5011}"

# 若已安装 KeepAlive 启动项：交由 launchd 托管
if agents_installed; then
  log "检测到 LaunchAgent，经由 launchd 启动（KeepAlive）..."
  # 先 bootout 再 bootstrap，避免残留状态
  launchctl bootout "${DOMAIN}/${API_LABEL}" 2>/dev/null || true
  launchctl bootout "${DOMAIN}/${WEB_LABEL}" 2>/dev/null || true
  free_port "$API_PORT"
  free_port "$WEB_PORT"
  launchctl bootstrap "$DOMAIN" "$HOME/Library/LaunchAgents/${API_LABEL}.plist" 2>/dev/null \
    || launchctl enable "${DOMAIN}/${API_LABEL}" 2>/dev/null || true
  launchctl bootstrap "$DOMAIN" "$HOME/Library/LaunchAgents/${WEB_LABEL}.plist" 2>/dev/null \
    || launchctl enable "${DOMAIN}/${WEB_LABEL}" 2>/dev/null || true
  launchctl kickstart -k "${DOMAIN}/${API_LABEL}"
  launchctl kickstart -k "${DOMAIN}/${WEB_LABEL}"

  if ! wait_http "http://127.0.0.1:$API_PORT/health" "API" 45; then
    log "查看日志: logs/daemon-api.log logs/launchd-api.err.log"
    exit 1
  fi
  if ! wait_http "http://127.0.0.1:$WEB_PORT/" "Web" 60; then
    log "查看日志: logs/daemon-web.log logs/launchd-web.err.log"
    exit 1
  fi

  echo ""
  log "FlowLedger 已启动（launchd KeepAlive）"
  echo "  数据库: postgresql://localhost:5432/flowledger"
  echo "  Web:    http://localhost:$WEB_PORT"
  echo "  API:    http://localhost:$API_PORT"
  echo "  Docs:   http://localhost:$API_PORT/docs"
  echo "  日志:   logs/daemon-api.log  logs/daemon-web.log"
  exit 0
fi

# 未安装启动项：手动后台启动（开发兜底）
for pidfile in .pids/api.pid .pids/web.pid; do
  if [ -f "$pidfile" ]; then
    pid=$(cat "$pidfile")
    kill "$pid" 2>/dev/null || true
    pkill -P "$pid" 2>/dev/null || true
    rm -f "$pidfile"
  fi
done
pkill -f "$ROOT/api/.venv/bin/uvicorn main:app" 2>/dev/null || true
pkill -f "$ROOT/web/node_modules/.bin/next" 2>/dev/null || true
pkill -f "$ROOT/web/node_modules/next/dist/bin/next" 2>/dev/null || true
free_port "$API_PORT"
free_port "$WEB_PORT"

log "未检测到 LaunchAgent，使用手动后台启动..."
log "（建议执行 ./scripts/install-autostart.sh 启用登录自启 + 崩溃拉起）"

log "启动 FastAPI (port $API_PORT)..."
(
  cd "$ROOT/api"
  nohup ../api/.venv/bin/uvicorn main:app --host 127.0.0.1 --port "$API_PORT" --reload \
    >> "$ROOT/logs/api.log" 2>&1 &
  echo $! > "$ROOT/.pids/api.pid"
)

log "启动 Next.js (port $WEB_PORT)..."
(
  cd "$ROOT/web"
  nohup npm run dev -- -p "$WEB_PORT" >> "$ROOT/logs/web.log" 2>&1 &
  echo $! > "$ROOT/.pids/web.pid"
)

if ! wait_http "http://127.0.0.1:$API_PORT/health" "API" 30; then
  log "查看日志: logs/api.log"
  exit 1
fi
if ! wait_http "http://127.0.0.1:$WEB_PORT/" "Web" 45; then
  log "查看日志: logs/web.log"
  exit 1
fi

echo ""
log "FlowLedger 已启动（本地手动模式）"
echo "  数据库: postgresql://localhost:5432/flowledger"
echo "  Web:    http://localhost:$WEB_PORT"
echo "  API:    http://localhost:$API_PORT"
echo "  Docs:   http://localhost:$API_PORT/docs"
echo "  日志:   logs/api.log  logs/web.log"
