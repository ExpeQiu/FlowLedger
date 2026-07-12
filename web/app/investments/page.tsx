"use client";

import { useEffect, useState } from "react";
import { toast } from "sonner";
import { AppShell, MetricCard, BudgetProgress } from "@/components/layout";
import { api, fmt, tagClass, type PortfolioSummary } from "@/lib/api";

export default function InvestmentsPage() {
  const [data, setData] = useState<PortfolioSummary | null>(null);

  useEffect(() => {
    api.portfolioSummary().then(setData).catch((e) => toast.error(e.message));
  }, []);

  if (!data) {
    return <AppShell title="投资管理" subtitle="加载中..."><p>加载中...</p></AppShell>;
  }

  return (
    <AppShell title="投资管理" subtitle="查看持仓、收益、配置和再平衡建议">
      <div className="grid grid-cols-4 gap-4">
        <MetricCard label="投资资产" sub="当前" value={fmt(data.total_value)} delta={`+${data.profit_pct}%`} />
        <MetricCard label="持仓成本" sub="累计" value={fmt(data.total_cost)} delta={`浮盈 ${fmt(data.profit)}`} />
        <MetricCard label="年化收益" sub="估算" value={`${data.annualized_return}%`} delta="跑赢基准" />
        <MetricCard label="风险集中度" sub="单一资产" value={`${data.max_concentration}%`} deltaVariant={data.max_concentration > 20 ? "warn" : "green"} delta={data.max_concentration > 20 ? "需关注" : "正常"} />
      </div>

      <div className="grid gap-4 mt-4" style={{ gridTemplateColumns: "1.45fr 0.75fr" }}>
        <article className="card p-4">
          <h3 className="m-0 mb-4 text-[15px]">持仓列表</h3>
          {data.holdings.map((h) => (
            <div key={h.id} className="flex items-center justify-between py-3 border-b border-[var(--line)] last:border-0">
              <div>
                <strong>{h.name}</strong>
                <div className="text-xs text-[var(--muted)]">{h.type} · {h.quantity} 份 · 成本 ¥{h.cost_price}</div>
              </div>
              <span className={tagClass((h.profit_pct || 0) >= 0 ? "green" : "red")}>
                {(h.profit_pct || 0) >= 0 ? "+" : ""}{h.profit_pct}%
              </span>
            </div>
          ))}
        </article>

        <article className="card p-4">
          <h3 className="m-0 mb-4 text-[15px]">再平衡建议</h3>
          {data.rebalance.map((r) => (
            <BudgetProgress key={r.type} name={r.type} spent={r.actual_pct} budget={100} usagePct={r.actual_pct} />
          ))}
          {data.rebalance.map((r) => (
            <div key={r.type + "-t"} className="text-xs text-[var(--muted)] mb-2">
              {r.type}: 当前 {r.actual_pct}% / 目标 {r.target_pct}%
            </div>
          ))}
        </article>
      </div>
    </AppShell>
  );
}
