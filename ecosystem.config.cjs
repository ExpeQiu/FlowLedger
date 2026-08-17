/**
 * PM2 · FlowLedger（API + Web）
 * 环境变量由 deploy 脚本 source /opt/flowledger/.env 后注入。
 */
module.exports = {
  apps: [
    {
      name: "flowledger-api",
      cwd: __dirname + "/api",
      script: ".venv/bin/uvicorn",
      args: "main:app --host 0.0.0.0 --port 9011",
      interpreter: "none",
      instances: 1,
      autorestart: true,
      watch: false,
      max_memory_restart: "256M",
      env: {
        PYTHONUNBUFFERED: "1",
      },
      error_file: "../logs/pm2-api-error.log",
      out_file: "../logs/pm2-api-out.log",
      log_date_format: "YYYY-MM-DD HH:mm:ss",
      merge_logs: true,
    },
    {
      name: "flowledger-web",
      cwd: __dirname + "/web",
      script: "node_modules/next/dist/bin/next",
      args: "start -p 8900",
      instances: 1,
      autorestart: true,
      watch: false,
      max_memory_restart: "512M",
      env: {
        NODE_ENV: "production",
        NODE_OPTIONS: "--max-old-space-size=512",
        PORT: 8900,
        API_INTERNAL_URL: "http://127.0.0.1:9011",
      },
      error_file: "../logs/pm2-web-error.log",
      out_file: "../logs/pm2-web-out.log",
      log_date_format: "YYYY-MM-DD HH:mm:ss",
      merge_logs: true,
    },
  ],
};
