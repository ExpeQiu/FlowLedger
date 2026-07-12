"use client";

import { useEffect, useState } from "react";
import { toast } from "sonner";
import { AppShell, BudgetProgress } from "@/components/layout";
import { api, currentMonth, type Budget, type Category } from "@/lib/api";

export default function BudgetsPage() {
  const [budgets, setBudgets] = useState<Budget[]>([]);
  const [categories, setCategories] = useState<Category[]>([]);
  const [form, setForm] = useState({ category_id: "", period: currentMonth(), amount: "3000", alert_threshold: 80 });
  const month = currentMonth();

  const load = () => {
    api.budgets(month).then(setBudgets).catch((e) => toast.error(e.message));
    api.categories().then(setCategories).catch(() => {});
  };

  useEffect(() => { load(); }, [month]);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      await api.createBudget({
        category_id: form.category_id,
        period: form.period,
        amount: parseFloat(form.amount),
        alert_threshold: form.alert_threshold,
      });
      toast.success("预算已保存");
      load();
    } catch (err) {
      toast.error(String(err));
    }
  };

  return (
    <AppShell title="预算管理" subtitle="按月设置分类预算并跟踪使用率">
      <div className="grid gap-4" style={{ gridTemplateColumns: "1.45fr 0.75fr" }}>
        <article className="card p-4">
          <div className="flex justify-between mb-4">
            <h3 className="m-0 text-[15px]">月度预算</h3>
            <span className="text-xs text-[var(--muted)]">{month}</span>
          </div>
          {budgets.map((b) => (
            <BudgetProgress
              key={b.id}
              name={b.category_name || "?"}
              spent={Number(b.spent || 0)}
              budget={Number(b.amount)}
              usagePct={b.usage_pct || 0}
            />
          ))}
        </article>

        <aside className="card p-4">
          <h3 className="m-0 mb-4 text-[15px]">新建预算</h3>
          <form className="grid grid-cols-2 gap-2.5" onSubmit={submit}>
            <label className="text-sm col-span-2">周期
              <input className="field mt-1" value={form.period} onChange={(e) => setForm({ ...form, period: e.target.value })} placeholder="2026-07" />
            </label>
            <label className="text-sm col-span-2">分类
              <select className="field mt-1" value={form.category_id} onChange={(e) => setForm({ ...form, category_id: e.target.value })} required>
                <option value="">选择分类</option>
                {categories.filter((c) => c.type === "expense").map((c) => (
                  <option key={c.id} value={c.id}>{c.name}</option>
                ))}
              </select>
            </label>
            <label className="text-sm col-span-2">预算金额
              <input className="field mt-1" type="number" value={form.amount} onChange={(e) => setForm({ ...form, amount: e.target.value })} />
            </label>
            <label className="text-sm col-span-2">提醒阈值 {form.alert_threshold}%
              <input className="field mt-1" type="range" min={50} max={100} value={form.alert_threshold} onChange={(e) => setForm({ ...form, alert_threshold: parseInt(e.target.value) })} />
            </label>
            <button type="submit" className="btn btn-primary col-span-2">保存预算</button>
          </form>
        </aside>
      </div>
    </AppShell>
  );
}
