#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

mkdir -p logs .pids
source "$ROOT/scripts/lib/pg.sh"

if [ ! -f .env ]; then
  cp .env.example .env
  echo "[start] 已从 .env.example 创建 .env"
fi

# 加载环境变量
set -a
# shellcheck disable=SC1091
source .env
set +a

if [ ! -d api/.venv ]; then
  echo "[start] 创建 Python 虚拟环境..."
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

echo "[start] 检查本地 PostgreSQL（优先）..."
if ! pg_ensure_local; then
  if [ "${USE_DOCKER_PG:-0}" = "1" ] && docker info >/dev/null 2>&1; then
    echo "[start] 回退到 Docker PostgreSQL (USE_DOCKER_PG=1)..."
    docker compose up -d postgres
    for i in $(seq 1 30); do
      if docker compose exec -T postgres pg_isready -U flowledger -d flowledger >/dev/null 2>&1; then
        break
      fi
      sleep 1
    done
  else
    echo "[start] 启动失败：请确保本地 PostgreSQL 已运行"
    echo "  1. brew services start postgresql@15"
    echo "  2. 或设置 USE_DOCKER_PG=1 使用 Docker"
    exit 1
  fi
fi

echo "[start] 运行数据库迁移..."
cd api && ../api/.venv/bin/alembic upgrade head && ../api/.venv/bin/python seed.py
cd "$ROOT"

if [ ! -d web/node_modules ]; then
  echo "[start] 安装 Web 依赖..."
  cd web && npm install
  cd "$ROOT"
fi

# 停止已有进程
for pidfile in .pids/api.pid .pids/web.pid; do
  if [ -f "$pidfile" ]; then
    pid=$(cat "$pidfile")
    kill "$pid" 2>/dev/null || true
    rm -f "$pidfile"
  fi
done

echo "[start] 启动 FastAPI (port 8000)..."
cd api && ../api/.venv/bin/uvicorn main:app --host 127.0.0.1 --port 8000 --reload > "$ROOT/logs/api.log" 2>&1 &
echo $! > "$ROOT/.pids/api.pid"

echo "[start] 启动 Next.js (port 3000)..."
cd web && npm run dev > "$ROOT/logs/web.log" 2>&1 &
echo $! > "$ROOT/.pids/web.pid"

sleep 3
echo ""
echo "[start] FlowLedger 已启动（本地模式）"
echo "  数据库: postgresql://localhost:5432/flowledger"
echo "  Web:    http://localhost:3000"
echo "  API:    http://localhost:8000"
echo "  Docs:   http://localhost:8000/docs"
echo "  日志:   logs/api.log  logs/web.log"
