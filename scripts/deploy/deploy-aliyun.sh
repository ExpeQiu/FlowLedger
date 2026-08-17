#!/usr/bin/env bash
# deploy-aliyun.sh — 部署 FlowLedger 到阿里云 120（共用 stock-pg + PM2）
# 用法:
#   export DEPLOY_HOST=120.25.145.131
#   bash scripts/deploy/deploy-aliyun.sh
# 可选: SKIP_DB=1 SKIP_SYNC_INSTALL=1 SKIP_BUILD=1 FORCE_DB_RESTORE=1 DUMP_FILE=/path.sql
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

HOST="${DEPLOY_HOST:-120.25.145.131}"
REMOTE_USER="${DEPLOY_USER:-root}"
REMOTE="${REMOTE_USER}@${HOST}"
REMOTE_DIR="${DEPLOY_DIR:-/opt/flowledger}"
SSH=(ssh -o BatchMode=yes -o StrictHostKeyChecking=accept-new)
SCP=(scp -o BatchMode=yes -o StrictHostKeyChecking=accept-new)
RSYNC=(rsync -az --delete
  --exclude node_modules
  --exclude .next
  --exclude .git
  --exclude logs
  --exclude .pids
  --exclude .venv
  --exclude 'api/.venv'
  --exclude 'cli/.venv'
  --exclude '.env'
  --exclude '.env.cloud.local'
  --exclude 'deploy/.env.pg'
  --exclude 'backups'
  --exclude '*.dump'
  --exclude '*.sql'
)

API_PORT="${API_PORT:-9011}"
WEB_PORT="${WEB_PORT:-8900}"
PG_PASS_DIR="/tmp/flowledger-deploy"
PG_PASS_FILE="${PG_PASS_FILE:-$PG_PASS_DIR/pg_pass.txt}"

log() { echo "[$(date '+%H:%M:%S')] $*"; }
remote() { "${SSH[@]}" "$REMOTE" "$@"; }

log "════════════════════════════════════════"
log "  FlowLedger → ${REMOTE}:${REMOTE_DIR}"
log "════════════════════════════════════════"

# 0. 连通性
remote "echo ok && hostname" >/dev/null
log "✓ SSH ${HOST}"

# 1. 远端目录与基础包
log "▶ 远端基础依赖"
remote "bash -s" <<EOS
set -euo pipefail
export PATH="/root/.local/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
mkdir -p ${REMOTE_DIR}/logs ${REMOTE_DIR}/deploy ${REMOTE_DIR}/api ${REMOTE_DIR}/web

# Node / PM2（与 stock 共用）
if ! command -v node >/dev/null 2>&1; then
  echo "✗ 未安装 Node，请先部署 stock 或安装 Node 20+"
  exit 1
fi
if ! command -v pm2 >/dev/null 2>&1; then
  npm install -g pm2
fi

# uv + Python 3.11 venv
if [[ ! -x ${REMOTE_DIR}/api/.venv/bin/python ]]; then
  if ! command -v uv >/dev/null 2>&1; then
    curl -LsSf https://astral.sh/uv/install.sh | sh
  fi
  export PATH="/root/.local/bin:\$PATH"
  uv python install 3.11
  uv venv ${REMOTE_DIR}/api/.venv --python 3.11
fi
export PATH="/root/.local/bin:\$PATH"

# psql / rsync
if ! command -v psql >/dev/null 2>&1; then
  yum install -y postgresql 2>&1 | tail -5 || true
fi
if ! command -v rsync >/dev/null 2>&1; then
  yum install -y rsync 2>&1 | tail -5 || true
fi

# 防火墙放行业务端口
if command -v firewall-cmd >/dev/null 2>&1; then
  firewall-cmd --permanent --add-port=${WEB_PORT}/tcp 2>/dev/null || true
  firewall-cmd --permanent --add-port=${API_PORT}/tcp 2>/dev/null || true
  firewall-cmd --reload 2>/dev/null || true
fi
EOS
log "✓ 依赖就绪"

# 2. 同步代码
log "▶ rsync 代码"
"${RSYNC[@]}" "$ROOT/" "${REMOTE}:${REMOTE_DIR}/"
log "✓ 代码已同步"

# 3. 共用 stock-pg：建库 + 可选恢复
if [[ "${SKIP_DB:-0}" != "1" ]]; then
  log "▶ 检测共用 stock-pg"
  if ! remote "docker exec stock-pg pg_isready -U stock -d invest" >/dev/null 2>&1; then
    log "✗ stock-pg 未就绪。请先部署 stock 的 Docker PG，勿再起第二套容器。"
    exit 1
  fi
  log "✓ stock-pg healthy"

  mkdir -p "$PG_PASS_DIR"
  if [[ ! -f "$PG_PASS_FILE" ]]; then
    openssl rand -hex 12 > "$PG_PASS_FILE"
  fi
  FL_PASS="$(cat "$PG_PASS_FILE")"
  # URL 编码密码
  ENC_PASS=$(python3 -c "import urllib.parse; print(urllib.parse.quote('''${FL_PASS}''', safe=''))")

  # stock 密码（读 invest）
  STOCK_PASS=$(remote "grep '^POSTGRES_PASSWORD=' /opt/stock/deploy/.env.pg | cut -d= -f2-" || true)
  if [[ -z "$STOCK_PASS" ]]; then
    log "✗ 无法读取 /opt/stock/deploy/.env.pg"
    exit 1
  fi
  ENC_STOCK=$(python3 -c "import urllib.parse; print(urllib.parse.quote('''${STOCK_PASS}''', safe=''))")

  # 写远端 flowledger 凭据
  remote "cat > ${REMOTE_DIR}/deploy/.env.pg" <<EOF
POSTGRES_USER=flowledger
POSTGRES_PASSWORD=${FL_PASS}
POSTGRES_DB=flowledger
SHARED_PG_CONTAINER=stock-pg
EOF
  remote "chmod 600 ${REMOTE_DIR}/deploy/.env.pg"

  log "▶ CREATE DATABASE/USER flowledger（幂等）"
  # 经容器内 stock 超级用户建角色/库（避免嵌套 heredoc 转义问题）
  remote "STOCK_PASS=\$(grep '^POSTGRES_PASSWORD=' /opt/stock/deploy/.env.pg | cut -d= -f2-)
docker exec -e PGPASSWORD=\"\$STOCK_PASS\" stock-pg psql -U stock -d postgres -tAc \"SELECT 1 FROM pg_roles WHERE rolname='flowledger'\" | grep -q 1 \\
  && docker exec -e PGPASSWORD=\"\$STOCK_PASS\" stock-pg psql -U stock -d postgres -c \"ALTER ROLE flowledger WITH PASSWORD '${FL_PASS}';\" \\
  || docker exec -e PGPASSWORD=\"\$STOCK_PASS\" stock-pg psql -U stock -d postgres -c \"CREATE ROLE flowledger LOGIN PASSWORD '${FL_PASS}';\"
docker exec -e PGPASSWORD=\"\$STOCK_PASS\" stock-pg psql -U stock -d postgres -tAc \"SELECT 1 FROM pg_database WHERE datname='flowledger'\" | grep -q 1 \\
  || docker exec -e PGPASSWORD=\"\$STOCK_PASS\" stock-pg psql -U stock -d postgres -c \"CREATE DATABASE flowledger OWNER flowledger;\"
docker exec -e PGPASSWORD=\"\$STOCK_PASS\" stock-pg psql -U stock -d postgres -c \"GRANT ALL PRIVILEGES ON DATABASE flowledger TO flowledger;\"
docker exec -e PGPASSWORD=\"\$STOCK_PASS\" stock-pg psql -U stock -d flowledger -c \"GRANT ALL ON SCHEMA public TO flowledger; ALTER SCHEMA public OWNER TO flowledger;\""
  log "✓ flowledger 库就绪"

  DUMP_FILE="${DUMP_FILE:-}"
  if [[ -z "$DUMP_FILE" ]]; then
    if [[ -f /tmp/flowledger-deploy/flowledger.sql ]]; then
      DUMP_FILE=/tmp/flowledger-deploy/flowledger.sql
    fi
  fi

  HAS_TBL=$(remote "PGPASSWORD=${FL_PASS} psql -h 127.0.0.1 -U flowledger -d flowledger -t -A -c \"SELECT count(*) FROM information_schema.tables WHERE table_schema='public' AND table_type='BASE TABLE';\"" || echo 0)
  if [[ -f "$DUMP_FILE" ]]; then
    if [[ "${FORCE_DB_RESTORE:-0}" == "1" || "$HAS_TBL" == "0" ]]; then
      log "▶ 恢复 dump → flowledger"
      STRIPPED="/tmp/flowledger-deploy/flowledger.pg16.sql"
      mkdir -p /tmp/flowledger-deploy
      python3 "$ROOT/scripts/deploy/strip-pg18-dump.py" "$DUMP_FILE" "$STRIPPED"
      "${SCP[@]}" "$STRIPPED" "${REMOTE}:/tmp/flowledger.sql"
      remote "docker cp /tmp/flowledger.sql stock-pg:/tmp/flowledger.sql"
      remote "docker exec -e PGPASSWORD=${FL_PASS} stock-pg psql -U flowledger -d flowledger -v ON_ERROR_STOP=0 -f /tmp/flowledger.sql" || true
      remote "rm -f /tmp/flowledger.sql; docker exec stock-pg rm -f /tmp/flowledger.sql"
      log "✓ dump 已恢复"
    else
      log "↷ 库已有 ${HAS_TBL} 张表，跳过 restore（FORCE_DB_RESTORE=1 可强制）"
    fi
  else
    log "⚠ 无 dump 文件，将靠 alembic + seed 初始化"
  fi

  # 写远端 .env
  remote "cat > ${REMOTE_DIR}/.env" <<EOF
DATABASE_URL=postgresql://flowledger:${ENC_PASS}@127.0.0.1:5432/flowledger
PG_HOST=127.0.0.1
PG_PORT=5432
PG_USER=flowledger
PG_DB=flowledger
PG_SUPERUSER=stock
INVEST_DATABASE_URL=postgresql://stock:${ENC_STOCK}@127.0.0.1:5432/invest
API_PORT=${API_PORT}
WEB_PORT=${WEB_PORT}
API_URL=http://${HOST}:${WEB_PORT}
WEB_URL=http://${HOST}:${WEB_PORT}
NEXT_PUBLIC_API_URL=http://${HOST}:${WEB_PORT}
LOG_LEVEL=INFO
DEPLOY_ENV=cloud
TZ=Asia/Shanghai
API_INTERNAL_URL=http://127.0.0.1:${API_PORT}
EOF
  remote "chmod 600 ${REMOTE_DIR}/.env"
  log "✓ .env 已写入"

  # 本机 .env.cloud.local（gitignore）
  cat > "$ROOT/.env.cloud.local" <<EOF
# 由 deploy-aliyun.sh 生成 · 勿提交
DEPLOY_HOST=${HOST}
DEPLOY_DIR=${REMOTE_DIR}
CLOUD_DATABASE_URL=postgresql://flowledger:${ENC_PASS}@127.0.0.1:15433/flowledger
FLOWLEDGER_TUNNEL_LOCAL_PORT=15433
EOF
  chmod 600 "$ROOT/.env.cloud.local"
  log "✓ 本机 .env.cloud.local"
else
  log "↷ 跳过 DB · 仍刷新公网 URL + INVEST 凭据（stock 密码可能轮换）"
  remote "bash -s" <<EOF
set -euo pipefail
ENV=${REMOTE_DIR}/.env
STOCK_ENV=/opt/stock/deploy/.env.pg
if [[ -f "\$ENV" ]]; then
  sed -i "s|^NEXT_PUBLIC_API_URL=.*|NEXT_PUBLIC_API_URL=http://${HOST}:${WEB_PORT}|" "\$ENV"
  sed -i "s|^API_URL=.*|API_URL=http://${HOST}:${WEB_PORT}|" "\$ENV"
  sed -i "s|^WEB_URL=.*|WEB_URL=http://${HOST}:${WEB_PORT}|" "\$ENV"
  grep -q '^API_INTERNAL_URL=' "\$ENV" || echo "API_INTERNAL_URL=http://127.0.0.1:${API_PORT}" >> "\$ENV"
  if [[ -f "\$STOCK_ENV" ]]; then
    STOCK_PASS=\$(grep '^POSTGRES_PASSWORD=' "\$STOCK_ENV" | cut -d= -f2-)
    ENC_STOCK=\$(python3 -c "import urllib.parse,sys; print(urllib.parse.quote(sys.argv[1], safe=''))" "\$STOCK_PASS")
    if grep -q '^INVEST_DATABASE_URL=' "\$ENV"; then
      sed -i "s|^INVEST_DATABASE_URL=.*|INVEST_DATABASE_URL=postgresql://stock:\${ENC_STOCK}@127.0.0.1:5432/invest|" "\$ENV"
    else
      echo "INVEST_DATABASE_URL=postgresql://stock:\${ENC_STOCK}@127.0.0.1:5432/invest" >> "\$ENV"
    fi
    echo "[deploy] INVEST_DATABASE_URL 已对齐 stock 密码"
  fi
fi
EOF
fi

# 4. Python 依赖 + 迁移
log "▶ API venv + alembic"
remote "bash -s" <<EOF
set -euo pipefail
export PATH="/root/.local/bin:\$PATH"
cd ${REMOTE_DIR}
set -a && source .env && set +a
uv pip install -q --python api/.venv -i https://mirrors.aliyun.com/pypi/simple/ --trusted-host mirrors.aliyun.com -r api/requirements.txt
cd api
../api/.venv/bin/alembic upgrade head
../api/.venv/bin/python seed.py || true
EOF
log "✓ 迁移完成"

# 5. Web build
if [[ "${SKIP_BUILD:-0}" != "1" ]]; then
  log "▶ npm ci && build"
  remote "bash -s" <<EOF
set -euo pipefail
cd ${REMOTE_DIR}/web
set -a && source ${REMOTE_DIR}/.env && set +a
npm ci
NODE_OPTIONS=--max-old-space-size=512 NEXT_PUBLIC_API_URL="\$NEXT_PUBLIC_API_URL" npm run build
EOF
  log "✓ build 完成"
fi

# 6. PM2
log "▶ PM2 启动"
remote "bash -s" <<EOF
set -euo pipefail
cd ${REMOTE_DIR}
mkdir -p logs
set -a && source .env && set +a
export NEXT_PUBLIC_API_URL="\$NEXT_PUBLIC_API_URL"
for name in flowledger-api flowledger-web; do
  pm2 describe "\$name" >/dev/null 2>&1 && pm2 delete "\$name" || true
done
pm2 start ecosystem.config.cjs --update-env
pm2 save
# 开机自启（忽略已配置时的提示）
pm2 startup systemd -u root --hp /root >/tmp/pm2-startup.out 2>&1 || true
if grep -q 'sudo env' /tmp/pm2-startup.out 2>/dev/null; then
  grep 'sudo env' /tmp/pm2-startup.out | bash || true
fi
EOF
log "✓ PM2 online"

# 7. cron
if [[ "${SKIP_SYNC_INSTALL:-0}" != "1" ]]; then
  log "▶ 安装 Linux cron"
  remote "bash ${REMOTE_DIR}/scripts/deploy/install-linux-cron.sh"
fi

# 8. 健康探测
log "▶ 健康探测"
sleep 4
remote "curl -sf -m 15 http://127.0.0.1:${API_PORT}/health || true"
remote "curl -sI -m 15 http://127.0.0.1:${WEB_PORT}/ | head -5 || true"
curl -sf -m 15 "http://${HOST}:${API_PORT}/health" && echo "" || log "⚠ 公网 ${API_PORT} 可能未在安全组放行"
curl -sI -m 15 "http://${HOST}:${WEB_PORT}/" | head -5 || log "⚠ 公网 ${WEB_PORT} 可能未在安全组放行"

log "════════════════════════════════════════"
log "  完成 · Web http://${HOST}:${WEB_PORT}"
log "  API  http://${HOST}:${API_PORT}/health"
log "  远端: ${REMOTE_DIR}"
log "  PG 密码(本机): ${PG_PASS_FILE}"
log "  共用: stock-pg · 库 flowledger"
log "════════════════════════════════════════"
