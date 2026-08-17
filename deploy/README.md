# FlowLedger 部署说明

云端**不**单独起 PostgreSQL 容器，复用 `/opt/stock` 的 `stock-pg`（`127.0.0.1:5432`）。

- 库隔离：同实例、不同 database（`invest` / `flowledger`）
- 一键部署：`bash scripts/deploy/deploy-aliyun.sh`
- 凭据模板：`.env.pg.example`（真密不入库）
