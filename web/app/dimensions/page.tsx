"use client";

import { useEffect, useState } from "react";
import { toast } from "sonner";
import { AppShell, MetricCard } from "@/components/layout";
import { api, fmt, type CashFlowForecast, type Goal, type Rule } from "@/lib/api";

const DIMENSIONS = [
  { title: "账户管理", desc: "现金、银行卡、信用卡、支付宝、微信、券商账户、基金账户。这是所有流水和资产的基础。" },
  { title: "负债管理", desc: "信用卡账单、房贷、消费贷、借款、分期。展示总负债、还款日、利息、最低还款风险。" },
  { title: "现金流预测", desc: "根据工资、房租、信用卡还款、定投、订阅服务，预测未来 30/90 天现金余额。" },
  { title: "财务目标", desc: "应急金、买房首付、旅行基金、年度储蓄目标。可以和预算联动。" },
  { title: "账单与订阅管理", desc: "房租、保险、会员、云服务、电话费、贷款还款。适合提醒和自动生成流水。" },
  { title: "报表分析", desc: "月报、年报、分类趋势、同比/环比、异常支出。" },
  { title: "规则与自动分类", desc: "星巴克→餐饮，地铁→交通，工资→收入。文件导入后自动分类。" },
  { title: "数据安全与备份", desc: "本地加密、导出、备份、恢复、敏感字段隐藏。" },
];

export default function DimensionsPage() {
  const [goals, setGoals] = useState<Goal[]>([]);
  const [rules, setRules] = useState<Rule[]>([]);
  const [forecast, setForecast] = useState<CashFlowForecast | null>(null);
  const [ruleForm, setRuleForm] = useState({ pattern: "", category_id: "" });
  const [categories, setCategories] = useState<{ id: string; name: string }[]>([]);

  useEffect(() => {
    api.goals().then(setGoals).catch(() => {});
    api.rules().then(setRules).catch(() => {});
    api.cashflow(30).then(setForecast).catch(() => {});
    api.categories().then(setCategories).catch(() => {});
  }, []);

  const addRule = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      await api.createRule({ pattern: ruleForm.pattern, category_id: ruleForm.category_id });
      toast.success("规则已添加");
      api.rules().then(setRules);
    } catch (err) { toast.error(String(err)); }
  };

  return (
    <AppShell title="推荐增加的维度" subtitle="账户、负债、现金流、目标、订阅、报表、规则和安全能力">
      <div className="grid grid-cols-4 gap-3 mb-6">
        {["先补账户与负债", "再做现金流预测", "接入规则自动化", "沉淀复盘与安全"].map((s, i) => (
          <div key={s} className="card p-3">
            <span className="inline-flex w-6 h-6 items-center justify-center rounded-full bg-[var(--ink)] text-white text-xs font-bold">{i + 1}</span>
            <strong className="block mt-2 text-sm">{s}</strong>
          </div>
        ))}
      </div>

      {forecast && (
        <div className="grid grid-cols-3 gap-4 mb-6">
          <MetricCard label="当前余额" sub="预测起点" value={fmt(forecast.starting_balance)} />
          <MetricCard label={`${forecast.days}天后余额`} sub="预测" value={fmt(forecast.ending_balance)} />
          <MetricCard label="财务目标" sub={`${goals.length} 个`} value={goals.length ? `${goals[0].progress_pct}%` : "-"} delta={goals[0]?.name} />
        </div>
      )}

      <div className="grid grid-cols-2 gap-3 mb-6">
        {DIMENSIONS.map((d) => (
          <article key={d.title} className="card p-4">
            <h3 className="m-0 mb-2 text-[15px]">{d.title}</h3>
            <p className="m-0 text-sm text-[var(--muted)]">{d.desc}</p>
          </article>
        ))}
      </div>

      <div className="grid gap-4" style={{ gridTemplateColumns: "1fr 1fr" }}>
        <article className="card p-4">
          <h3 className="m-0 mb-3 text-[15px]">财务目标</h3>
          {goals.map((g) => (
            <div key={g.id} className="mb-3">
              <div className="flex justify-between text-sm"><strong>{g.name}</strong><span>{g.progress_pct}%</span></div>
              <div className="progress-bar mt-1"><span style={{ width: `${g.progress_pct}%`, background: "var(--green)" }} /></div>
              <div className="text-xs text-[var(--muted)]">{fmt(g.current_amount)} / {fmt(g.target_amount)}</div>
            </div>
          ))}
        </article>

        <article className="card p-4">
          <h3 className="m-0 mb-3 text-[15px]">自动分类规则</h3>
          {rules.map((r) => (
            <div key={r.id} className="text-sm py-1 border-b border-[var(--line)]">
              <code>{r.pattern}</code> → {r.category_name}
            </div>
          ))}
          <form className="grid gap-2 mt-3" onSubmit={addRule}>
            <input className="field" placeholder="匹配关键词" value={ruleForm.pattern} onChange={(e) => setRuleForm({ ...ruleForm, pattern: e.target.value })} required />
            <select className="field" value={ruleForm.category_id} onChange={(e) => setRuleForm({ ...ruleForm, category_id: e.target.value })} required>
              <option value="">选择分类</option>
              {categories.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
            </select>
            <button type="submit" className="btn btn-primary">添加规则</button>
          </form>
        </article>
      </div>
    </AppShell>
  );
}
