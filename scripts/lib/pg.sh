#!/usr/bin/env bash
# PostgreSQL 本地优先工具函数
set -euo pipefail

PG_HOST="${PG_HOST:-localhost}"
PG_PORT="${PG_PORT:-5432}"
PG_USER="${PG_USER:-flowledger}"
PG_DB="${PG_DB:-flowledger}"
PG_SUPERUSER="${PG_SUPERUSER:-postgres}"

_find_psql() {
  if command -v psql >/dev/null 2>&1; then
    command -v psql
    return
  fi
  for p in /opt/homebrew/opt/postgresql@16/bin/psql /opt/homebrew/opt/postgresql@15/bin/psql /opt/homebrew/bin/psql; do
    if [ -x "$p" ]; then
      echo "$p"
      return
    fi
  done
  return 1
}

PSQL="$(_find_psql || true)"

pg_local_ready() {
  command -v pg_isready >/dev/null 2>&1 && pg_isready -h "$PG_HOST" -p "$PG_PORT" -q
}

pg_connect() {
  [ -n "$PSQL" ] && "$PSQL" -h "$PG_HOST" -p "$PG_PORT" -U "$PG_USER" -d "$PG_DB" -c "SELECT 1" >/dev/null 2>&1
}

pg_super_connect() {
  [ -n "$PSQL" ] && "$PSQL" -h "$PG_HOST" -p "$PG_PORT" -U "$PG_SUPERUSER" -d postgres -c "SELECT 1" >/dev/null 2>&1
}

pg_init_local() {
  if ! pg_super_connect; then
    echo "[pg] 无法以超级用户 $PG_SUPERUSER 连接，请手动创建数据库："
    echo "      CREATE USER flowledger WITH PASSWORD 'flowledger';"
    echo "      CREATE DATABASE flowledger OWNER flowledger;"
    return 1
  fi
  echo "[pg] 初始化本地数据库 $PG_DB ..."
  "$PSQL" -h "$PG_HOST" -p "$PG_PORT" -U "$PG_SUPERUSER" -d postgres -v ON_ERROR_STOP=1 <<SQL
DO \$\$ BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '$PG_USER') THEN
    CREATE USER $PG_USER WITH PASSWORD 'flowledger';
  END IF;
END \$\$;
SELECT 'CREATE DATABASE $PG_DB OWNER $PG_USER'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = '$PG_DB')\gexec
GRANT ALL PRIVILEGES ON DATABASE $PG_DB TO $PG_USER;
SQL
}

pg_ensure_local() {
  if ! pg_local_ready; then
    echo "[pg] 本地 PostgreSQL 未运行 ($PG_HOST:$PG_PORT)"
    echo "[pg] 请先启动本地 PG，例如: brew services start postgresql@15"
    return 1
  fi
  if ! pg_connect; then
    pg_init_local || return 1
    sleep 1
    pg_connect || { echo "[pg] 仍无法连接 $PG_USER@$PG_DB"; return 1; }
  fi
  echo "[pg] 本地 PostgreSQL 就绪: $PG_USER@$PG_HOST:$PG_PORT/$PG_DB"
}

pg_psql() {
  "$PSQL" -h "$PG_HOST" -p "$PG_PORT" -U "$PG_USER" -d "$PG_DB" "$@"
}

pg_dump_local() {
  local outfile="$1"
  if command -v pg_dump >/dev/null 2>&1; then
    pg_dump -h "$PG_HOST" -p "$PG_PORT" -U "$PG_USER" "$PG_DB" > "$outfile"
  elif [ -n "$PSQL" ]; then
    local pg_dump_bin
    pg_dump_bin="$(dirname "$PSQL")/pg_dump"
    "$pg_dump_bin" -h "$PG_HOST" -p "$PG_PORT" -U "$PG_USER" "$PG_DB" > "$outfile"
  else
    return 1
  fi
}
