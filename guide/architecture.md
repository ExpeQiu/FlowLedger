# FlowLedger 架构文档

## 概述

FlowLedger 是本地优先的个人财务管理系统，数据存储在 PostgreSQL，通过 FastAPI 统一 API 为 Web 和 CLI 提供服务。

## 技术栈

- **Web**: Next.js 15 + TypeScript + Tailwind CSS
- **API**: FastAPI + Pydantic + SQLAlchemy
- **数据库**: PostgreSQL（本地安装，默认 localhost:5432）
- **迁移**: Alembic
- **CLI**: Python Typer

## 数据模型

核心表：`accounts`, `categories`, `transactions`, `budgets`, `holdings`

扩展表：`liabilities`, `recurring_bills`, `rules`, `goals`, `import_jobs`

## API 端点

| 端点 | 说明 |
|------|------|
| GET /health | 健康检查 |
| GET /api/dashboard | 总览聚合 |
| CRUD /api/accounts | 账户 |
| CRUD /api/transactions | 流水 |
| CRUD /api/budgets | 预算 |
| CRUD /api/holdings | 持仓 |
| CRUD /api/liabilities | 负债 |
| CRUD /api/goals | 财务目标 |
| CRUD /api/rules | 自动分类规则 |
| POST /api/import/csv | 账单导入 |
| GET /api/reports/monthly | 月报 |
| GET /api/reports/cashflow | 现金流预测 |

## CLI 命令

```bash
finance today
finance add expense --amount 68 --category 餐饮 --note 午餐
finance import csv file.csv --source alipay
finance budget status --month 2026-07
finance portfolio summary --as-of today
finance export report --format xlsx --month 2026-07
```

## 启动（本地优先）

**前置条件**：本地 PostgreSQL 已安装并运行。

```bash
# macOS 示例
brew install postgresql@15
brew services start postgresql@15

# 初始化项目
cp .env.example .env
chmod +x scripts/*.sh
./scripts/start.sh    # 自动检测本地 PG、迁移、启动 API + Web
./scripts/verify.sh
```

`start.sh` 默认连接 `postgresql://localhost:5432/flowledger`。若库不存在，会尝试用 `postgres` 超级用户自动创建。

可选 Docker 回退：`USE_DOCKER_PG=1 ./scripts/start.sh`

## 备份

```bash
./scripts/backup.sh
```
