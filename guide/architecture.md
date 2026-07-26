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

### 投资账户语义

- `accounts.type` 为 `broker` / `fund` 时，`balance` = **账户总资产**（闲置现金 + 持仓市值）
- `holdings` 为该账户下的证券明细；市值之和不得超过账户余额
- 净资产 = Σ账户余额 − 未在账户中体现的负债（**不再叠加** holdings）
- 信用卡若同时以 `accounts(type=credit)` 负余额与 `liabilities` 记录，计算净资产时去重
- 持仓增删改价会按市值差额回写投资账户 `balance`（闲置现金相对不变）

### 投资数据链路

```mermaid
flowchart LR
  InvestDB[(invest.lcteam<br/>positions / snapshots)] -->|sync-from-invest| Svc[finance 聚合与校验]
  FLDB[(flowledger<br/>accounts / holdings)] --> Svc
  Svc --> AccAPI["/api/accounts"]
  Svc --> HolAPI["/api/holdings/summary"]
  Svc --> Dash["/api/dashboard"]
  AccAPI --> WebAcc[账户页]
  HolAPI --> WebInv[投资页]
  Dash --> WebHome[总览]
```

权威源：`invest.lcteam.position_snapshots` + `positions(account_type=real)`。  
同步命令：`./scripts/sync-invest.sh` 或 `POST /api/holdings/sync-from-invest`。

## API 端点

| 端点 | 说明 |
|------|------|
| GET /health | 健康检查 |
| GET /api/dashboard | 总览聚合 |
| CRUD /api/accounts | 账户（投资账户含 holdings_mv/cash 拆分） |
| GET /api/accounts/net-worth | 净资产（与 Dashboard 同口径） |
| CRUD /api/transactions | 流水 |
| CRUD /api/budgets | 预算 |
| CRUD /api/holdings | 持仓 |
| GET /api/holdings/summary | 投资组合（含现金拆分） |
| GET /api/holdings/daily-pnl | 指定月每日收益波动（invest snapshots） |
| GET /api/holdings/validate | 投资账户与持仓一致性校验 |
| POST /api/holdings/sync-from-invest | 从 invest.lcteam 同步真实持仓 |
| CRUD /api/liabilities | 负债 |
| CRUD /api/goals | 财务目标 |
| GET/POST /api/recurring-bills | 定期账单 |
| POST /api/recurring-bills/materialize | 将指定月定期账单落成支出流水（默认不改余额） |
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
