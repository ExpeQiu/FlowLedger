#!/usr/bin/env bash
# 备份 PostgreSQL 数据库（本地优先）
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
source "$ROOT/scripts/lib/pg.sh"

BACKUP_DIR="$ROOT/backups"
mkdir -p "$BACKUP_DIR"

TIMESTAMP=$(date +%Y%m%d_%H%M%S)
FILE="$BACKUP_DIR/flowledger_$TIMESTAMP.sql"

if pg_connect; then
  pg_dump_local "$FILE"
  echo "备份完成（本地 PG）: $FILE"
elif [ "${USE_DOCKER_PG:-0}" = "1" ] && docker compose exec -T postgres pg_isready -U flowledger >/dev/null 2>&1; then
  docker compose exec -T postgres pg_dump -U flowledger flowledger > "$FILE"
  echo "备份完成（Docker PG）: $FILE"
else
  echo "备份失败：本地 PostgreSQL 不可连接"
  exit 1
fi
