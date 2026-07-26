"use client";

import { useEffect, useState } from "react";
import { toast } from "sonner";
import { AppShell } from "@/components/layout";
import { api, currentMonth, fmt, tagClass, type Account, type Category, type Transaction } from "@/lib/api";

export default function ExpensesPage() {
  const [txs, setTxs] = useState<Transaction[]>([]);
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [categories, setCategories] = useState<Category[]>([]);
  const [filter, setFilter] = useState("");
  const [search, setSearch] = useState("");
  const [form, setForm] = useState({ type: "expense", amount: "68", category_id: "", account_id: "", note: "午餐" });

  const load = () => {
    const params: Record<string, string> = { limit: "50" };
    if (filter) params.type = filter;
    if (search) params.search = search;
    Promise.all([api.transactions(params), api.accounts(), api.categories()])
      .then(([t, a, c]) => { setTxs(t); setAccounts(a); setCategories(c); })
      .catch((e) => toast.error(e.message));
  };

  useEffect(() => { load(); }, [filter, search]);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      await api.createTransaction({
        type: form.type,
        amount: parseFloat(form.amount),
        date: new Date().toISOString().slice(0, 10),
        account_id: form.account_id || accounts[0]?.id,
        category_id: form.category_id || undefined,
        note: form.note,
        merchant: form.note,
      });
      toast.success(`已记录：${form.note} -¥${form.amount}`);
      load();
    } catch (err) {
      toast.error(String(err));
    }
  };

  const handleImport = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file || !accounts[0]) return;
    try {
      const result = await api.importCsv(file, "csv", accounts[0].id);
      toast.success(`导入 ${result.imported} 条，跳过 ${result.skipped} 条重复`);
      load();
    } catch (err) {
      toast.error(String(err));
    }
  };

  return (
    <AppShell title="生活开支" subtitle="管理日常流水、分类、账户和导入记录">
      <div className="flex items-center justify-between gap-3 mb-3.5 flex-wrap">
        <div className="inline-flex min-h-[38px] p-[3px] border border-[var(--line)] rounded-lg bg-[var(--surface-soft)]">
          {["", "expense", "income"].map((t) => (
            <button key={t} className={`px-3 min-w-16 border-0 rounded-md bg-transparent cursor-pointer ${filter === t ? "bg-white shadow-sm" : "text-[var(--muted)]"}`} onClick={() => setFilter(t)}>
              {t === "" ? "全部" : t === "expense" ? "支出" : "收入"}
            </button>
          ))}
        </div>
        <input className="field max-w-xs" placeholder="搜索商户或备注" value={search} onChange={(e) => setSearch(e.target.value)} />
      </div>

      <div className="grid gap-4" style={{ gridTemplateColumns: "1.45fr 0.75fr" }}>
        <article className="card overflow-x-auto">
          <div className="flex justify-between p-4 pb-0">
            <h3 className="m-0 text-[15px]">生活开支流水</h3>
            <span className="text-xs text-[var(--muted)]">最近 {txs.length} 笔</span>
          </div>
          <table className="w-full min-w-[720px] border-collapse">
            <thead>
              <tr className="text-[var(--muted)] text-xs">
                {["日期", "商户", "分类", "账户", "金额"].map((h) => (
                  <th key={h} className="p-3 text-left border-b border-[var(--line)]">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {txs.length === 0 ? (
                <tr>
                  <td colSpan={5} className="p-8 text-center text-[var(--muted)]">
                    {filter === "expense"
                      ? "暂无支出流水。若有定期账单，可在总览落账或手动记一笔。"
                      : filter === "income"
                        ? "暂无收入流水"
                        : "暂无流水记录"}
                  </td>
                </tr>
              ) : (
                txs.map((t) => (
                  <tr key={t.id} className="border-b border-[var(--line)]">
                    <td className="p-3">{t.date.slice(5)}</td>
                    <td className="p-3">{t.merchant || t.note || "-"}</td>
                    <td className="p-3"><span className={tagClass("amber")}>{t.category_name || "-"}</span></td>
                    <td className="p-3">{t.account_name || "-"}</td>
                    <td className={`p-3 text-right font-bold amount-value ${t.type === "income" ? "text-[var(--green)]" : "text-[var(--red)]"}`}>
                      {t.type === "income" ? "+" : "-"}{fmt(t.amount)}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </article>

        <aside className="card p-4">
          <h3 className="m-0 mb-4 text-[15px]">快速记账</h3>
          <form className="grid grid-cols-2 gap-2.5" onSubmit={submit}>
            <label className="text-sm">类型
              <select className="field mt-1" value={form.type} onChange={(e) => setForm({ ...form, type: e.target.value })}>
                <option value="expense">支出</option>
                <option value="income">收入</option>
              </select>
            </label>
            <label className="text-sm">金额
              <input className="field mt-1" type="number" value={form.amount} onChange={(e) => setForm({ ...form, amount: e.target.value })} />
            </label>
            <label className="text-sm">分类
              <select className="field mt-1" value={form.category_id} onChange={(e) => setForm({ ...form, category_id: e.target.value })}>
                <option value="">选择分类</option>
                {categories.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
              </select>
            </label>
            <label className="text-sm">账户
              <select className="field mt-1" value={form.account_id} onChange={(e) => setForm({ ...form, account_id: e.target.value })}>
                {accounts.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}
              </select>
            </label>
            <label className="text-sm col-span-2">备注
              <input className="field mt-1" value={form.note} onChange={(e) => setForm({ ...form, note: e.target.value })} />
            </label>
            <button type="submit" className="btn btn-primary col-span-2">保存记录</button>
          </form>
        </aside>
      </div>

      <article className="card p-4 mt-4">
        <h3 className="m-0 mb-2 text-[15px]">文件导入</h3>
        <p className="text-xs text-[var(--muted)] mb-3">CSV / Excel / 支付平台账单</p>
        <label className="flex flex-col items-center justify-center p-8 border-2 border-dashed border-[var(--line)] rounded-lg cursor-pointer hover:border-[var(--green)]">
          <strong>拖入或选择账单文件</strong>
          <span className="text-xs text-[var(--muted)] mt-1">支持支付宝、微信及通用 CSV 格式</span>
          <input type="file" accept=".csv" className="hidden" onChange={handleImport} />
        </label>
      </article>
    </AppShell>
  );
}
