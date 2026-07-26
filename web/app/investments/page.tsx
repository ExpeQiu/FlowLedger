"use client";

import { useEffect, useState } from "react";
import { toast } from "sonner";
import { AppShell, MetricCard, BudgetProgress } from "@/components/layout";
import {
  api,
  currentMonth,
  fmt,
  tagClass,
  type MonthlyDailyPnl,
  type PortfolioSummary,
} from "@/lib/api";
import {
  BarChart,
  Bar,
  Cell,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  ReferenceLine,
} from "recharts";

export default function InvestmentsPage() {
  const [data, setData] = useState<PortfolioSummary | null>(null);
  const [pnl, setPnl] = useState<MonthlyDailyPnl | null>(null);
  const month = currentMonth();

  const load = async () => {
    const [summary, daily] = await Promise.all([
      api.portfolioSummary(),
      api.dailyPnl(month).catch((e) => {
        console.warn("月度每日收益加载失败", e);
        return null;
      }),
    ]);
    setData(summary);
    setPnl(daily);
  };

  useEffect(() => {
    load().catch((e) => toast.error(e.message));
  }, [month]);

  const sync = async () => {
    try {
      const r = await api.syncFromInvest();
      toast.success(`已同步 ${r.snapshot_date} · 总资产 ¥${r.total_asset}`);
      await load();
    } catch (e) {
      toast.error(String(e));
    }
  };

  if (!data) {
    return <AppShell title="投资管理" subtitle="加载中..."><p>加载中...</p></AppShell>;
  }

  const holdingsValue = Number(data.holdings_value ?? 0);
  const cashBalance = Number(data.cash_balance ?? 0);
  const sorted = [...data.holdings].sort(
    (a, b) => Number(b.market_value ?? 0) - Number(a.market_value ?? 0),
  );

  return (
    <AppShell
      title="投资管理"
      subtitle="数据源：invest.lcteam 真实持仓"
      actions={<button className="btn btn-primary" onClick={sync}>同步最新持仓</button>}
    >
      {data.validation_ok === false && (
        <p className="mb-4 text-sm text-[var(--red)]">投资账户余额与持仓市值不一致，请核对数据</p>
      )}
      <div className="grid grid-cols-4 gap-4">
        <MetricCard label="投资总资产" sub="账户合计" value={fmt(data.total_value)} />
        <MetricCard label="持仓市值" sub="证券" value={fmt(holdingsValue)} delta={`成本 ${fmt(data.total_cost)}`} />
        <MetricCard label="闲置现金" sub="可再配置" value={fmt(cashBalance)} />
        <MetricCard
          label="持仓浮盈"
          sub="相对成本"
          value={fmt(data.profit)}
          delta={`${data.profit_pct >= 0 ? "+" : ""}${data.profit_pct}%`}
          deltaVariant={data.profit_pct >= 0 ? "danger" : "green"}
        />
      </div>

      <article className="card p-4 mt-4">
        <div className="flex items-baseline justify-between mb-4 gap-3 flex-wrap">
          <h3 className="m-0 text-[15px]">{month} 每日收益波动</h3>
          {pnl && (
            <div className="text-xs text-[var(--muted)]">
              累计 {fmt(pnl.total_pnl)}
              <span className="mx-2">·</span>
              上涨 {pnl.up_days} 天 / 下跌 {pnl.down_days} 天
            </div>
          )}
        </div>
        {pnl && pnl.days.length > 0 ? (
          <ResponsiveContainer width="100%" height={220}>
            <BarChart data={pnl.days} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
              <XAxis dataKey="day" tick={{ fontSize: 11 }} interval="preserveStartEnd" />
              <YAxis tick={{ fontSize: 11 }} width={56} tickFormatter={(v) => `${v}`} />
              <Tooltip
                formatter={(v, _n, item) => {
                  const pct = item?.payload?.daily_pnl_pct;
                  const pctText = pct != null ? ` (${pct >= 0 ? "+" : ""}${Number(pct).toFixed(2)}%)` : "";
                  return [fmt(Number(v)) + pctText, "日收益"];
                }}
                labelFormatter={(label) => `${month.slice(0, 4)}-${label}`}
              />
              <ReferenceLine y={0} stroke="var(--line)" />
              <Bar dataKey="daily_pnl" name="日收益" radius={[3, 3, 0, 0]}>
                {pnl.days.map((d) => (
                  <Cell
                    key={d.date}
                    fill={d.daily_pnl >= 0 ? "var(--red)" : "var(--green)"}
                  />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        ) : (
          <p className="text-sm text-[var(--muted)] m-0 py-8 text-center">
            暂无本月快照数据，请确认 invest 库已写入 position_snapshots
          </p>
        )}
      </article>

      <div className="grid gap-4 mt-4" style={{ gridTemplateColumns: "1.45fr 0.75fr" }}>
        <article className="card p-4">
          <h3 className="m-0 mb-4 text-[15px]">持仓列表</h3>
          {sorted.map((h) => (
            <div key={h.id} className="flex items-center justify-between py-3 border-b border-[var(--line)] last:border-0">
              <div>
                <strong>{h.name}</strong>
                <div className="text-xs text-[var(--muted)]">
                  {h.symbol} · {h.type} · {h.quantity} 份 · 现价 ¥{h.current_price}
                </div>
              </div>
              <div className="text-right">
                <div className="font-bold amount-value">{fmt(h.market_value ?? 0)}</div>
                <span className={tagClass((h.profit_pct || 0) >= 0 ? "red" : "green")}>
                  {(h.profit_pct || 0) >= 0 ? "+" : ""}{h.profit_pct}%
                </span>
              </div>
            </div>
          ))}
        </article>

        <article className="card p-4">
          <h3 className="m-0 mb-4 text-[15px]">配置占比</h3>
          {data.rebalance.map((r) => (
            <BudgetProgress key={r.type} name={r.type} spent={r.actual_pct} budget={100} usagePct={r.actual_pct} />
          ))}
          {data.rebalance.map((r) => (
            <div key={r.type + "-t"} className="text-xs text-[var(--muted)] mb-2">
              {r.type}: 当前 {r.actual_pct}% / 目标 {r.target_pct}%
            </div>
          ))}
          <div className="text-xs text-[var(--muted)] mt-4">
            集中度 {data.max_concentration}%（单一标的 / 投资总资产）
          </div>
        </article>
      </div>
    </AppShell>
  );
}
