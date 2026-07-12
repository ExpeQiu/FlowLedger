"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { toast } from "sonner";
import { AppShell, MetricCard, BudgetProgress } from "@/components/layout";
import { api, currentMonth, fmt, type Dashboard } from "@/lib/api";
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Legend } from "recharts";

export default function DashboardPage() {
  const [data, setData] = useState<Dashboard | null>(null);
  const [hideAmounts, setHideAmounts] = useState(false);
  const month = currentMonth();

  useEffect(() => {
    api.dashboard(month).then(setData).catch((e) => toast.error(e.message));
  }, [month]);

  const actions = (
    <>
      <Link href="/expenses" className="btn no-underline">导入</Link>
      <Link href="/expenses" className="btn btn-primary no-underline">记一笔</Link>
      <button className="btn btn-icon" title="隐藏金额" onClick={() => setHideAmounts(!hideAmounts)}>👁</button>
    </>
  );

  if (!data) {
    return (
      <AppShell title="财务总览" subtitle={`${month} · 加载中...`} actions={actions}>
        <p className="text-[var(--muted)]">加载中...</p>
      </AppShell>
    );
  }

  return (
    <div className={hideAmounts ? "hide-amounts" : ""}>
      <AppShell
        title="财务总览"
        subtitle={`${month} · 个人资产、支出、投资和预算的统一视图`}
        actions={actions}
      >
        <div className="grid grid-cols-4 gap-4">
          <MetricCard label="净资产" sub="当前" value={fmt(data.net_worth)} delta="+2.8%" />
          <MetricCard label="本月支出" sub="已发生" value={fmt(data.monthly_expense)} delta={`预算 ${data.budget_usage_pct}%`} deltaVariant="warn" />
          <MetricCard label="投资收益" sub="近 30 天" value={fmt(data.investment_return)} delta="+1.6%" />
          <MetricCard label="现金流" sub="本月" value={fmt(data.cash_flow)} delta="健康" />
        </div>

        <div className="grid gap-4 mt-4" style={{ gridTemplateColumns: "1.45fr 0.75fr" }}>
          <article className="card p-4">
            <h3 className="m-0 mb-4 text-[15px]">收入与支出趋势</h3>
            <ResponsiveContainer width="100%" height={250}>
              <BarChart data={data.trends}>
                <XAxis dataKey="month" tick={{ fontSize: 11 }} />
                <YAxis tick={{ fontSize: 11 }} />
                <Tooltip formatter={(v) => fmt(Number(v))} />
                <Legend />
                <Bar dataKey="income" name="收入" fill="var(--green)" radius={[4, 4, 0, 0]} />
                <Bar dataKey="expense" name="支出" fill="var(--blue)" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </article>

          <article className="card p-4">
            <h3 className="m-0 mb-4 text-[15px]">预算使用率</h3>
            {data.budget_by_category.map((b) => (
              <BudgetProgress key={b.category} name={b.category} spent={Number(b.spent)} budget={Number(b.budget)} usagePct={b.usage_pct} />
            ))}
          </article>
        </div>

        <div className="grid grid-cols-3 gap-4 mt-4">
          <article className="card p-4">
            <h3 className="m-0 mb-3 text-[15px]">近期提醒</h3>
            {data.alerts.map((a, i) => (
              <div key={i} className="py-2 border-b border-[var(--line)] last:border-0">
                <time className="text-xs text-[var(--muted)]">{a.date}</time>
                <div><strong className="text-sm">{a.title}</strong></div>
                <span className="text-xs text-[var(--muted)]">{a.detail}</span>
              </div>
            ))}
          </article>

          <article className="card p-4">
            <h3 className="m-0 mb-3 text-[15px]">资产分布</h3>
            <div className="grid grid-cols-2 gap-2">
              {data.asset_distribution.map((a) => (
                <div key={a.name} className="p-3 border border-[var(--line)] rounded-lg bg-white">
                  <strong className="text-sm">{a.name}</strong>
                  <div className="text-lg font-bold">{a.pct}%</div>
                  <small className="text-[var(--muted)] amount-value">{fmt(a.value)}</small>
                </div>
              ))}
            </div>
          </article>

          <article className="card p-4">
            <h3 className="m-0 mb-3 text-[15px]">CLI 快捷入口</h3>
            {["finance today", `finance budget status --month ${month}`].map((cmd) => (
              <div key={cmd} className="flex items-center justify-between py-2 border-b border-[var(--line)] last:border-0">
                <code className="text-xs">{cmd}</code>
                <button className="btn text-xs" onClick={() => { navigator.clipboard.writeText(cmd); toast.success("已复制"); }}>复制</button>
              </div>
            ))}
          </article>
        </div>
      </AppShell>
    </div>
  );
}
