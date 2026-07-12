"use client";

import { toast } from "sonner";
import { AppShell } from "@/components/layout";

const COMMANDS = [
  "finance today",
  "finance add expense --amount 68 --category 餐饮 --note 午餐",
  "finance import csv ~/Downloads/alipay.csv --source alipay",
  "finance budget status --month 2026-07",
  "finance portfolio summary --as-of today",
  "finance export report --format xlsx --month 2026-07",
];

export default function CliPage() {
  return (
    <AppShell title="CLI 接入" subtitle="为快速记账、批量导入和自动化报表保留命令行入口">
      <div className="grid gap-4" style={{ gridTemplateColumns: "1fr 1fr" }}>
        <article className="card p-4">
          <h3 className="m-0 mb-4 text-[15px]">CLI 命令设计</h3>
          {COMMANDS.map((cmd) => (
            <div key={cmd} className="flex items-center justify-between py-2 border-b border-[var(--line)]">
              <code className="text-xs">{cmd}</code>
              <button className="btn text-xs" onClick={() => { navigator.clipboard.writeText(cmd); toast.success("已复制"); }}>复制</button>
            </div>
          ))}
        </article>

        <article className="card p-4">
          <h3 className="m-0 mb-4 text-[15px]">接入策略</h3>
          {[
            { time: "入口", title: "Web 管理主流程", detail: "浏览器承担分类、对账、预算调整和投资复盘" },
            { time: "自动化", title: "CLI 批处理", detail: "导入文件、快速记账、生成报表、脚本化查询" },
            { time: "数据", title: "共享本地 API", detail: "Web 与 CLI 访问同一套数据模型和校验规则" },
          ].map((item) => (
            <div key={item.time} className="py-3 border-b border-[var(--line)]">
              <time className="text-xs text-[var(--muted)]">{item.time}</time>
              <div><strong>{item.title}</strong></div>
              <span className="text-xs text-[var(--muted)]">{item.detail}</span>
            </div>
          ))}
          <div className="mt-4 p-3 bg-[var(--surface-soft)] rounded-lg text-sm">
            <strong>使用方式</strong>
            <pre className="text-xs mt-2 whitespace-pre-wrap">{`cd cli
pip install -r requirements.txt
python -m finance today`}</pre>
          </div>
        </article>
      </div>
    </AppShell>
  );
}
