"use client";

import { useEffect, useState } from "react";
import { toast } from "sonner";
import { AppShell, MetricCard } from "@/components/layout";
import { api, fmt, type Account, type Liability } from "@/lib/api";

const ACCOUNT_TYPES = ["cash", "bank", "credit", "alipay", "wechat", "broker", "fund"];
const LIABILITY_TYPES = ["credit_card", "mortgage", "loan", "installment"];

export default function AccountsPage() {
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [liabilities, setLiabilities] = useState<Liability[]>([]);
  const [accForm, setAccForm] = useState({ name: "", type: "bank", balance: "0" });
  const [liaForm, setLiaForm] = useState({ name: "", type: "credit_card", principal: "0", min_payment: "0", due_date: "" });

  const load = () => {
    api.accounts().then(setAccounts).catch((e) => toast.error(e.message));
    api.liabilities().then(setLiabilities).catch(() => {});
  };

  useEffect(() => { load(); }, []);

  const totalAssets = accounts.reduce((s, a) => s + Number(a.balance), 0);
  const totalLiabilities = liabilities.reduce((s, l) => s + Number(l.principal), 0);

  const createAccount = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      await api.createAccount({ name: accForm.name, type: accForm.type, balance: parseFloat(accForm.balance) });
      toast.success("账户已创建");
      setAccForm({ name: "", type: "bank", balance: "0" });
      load();
    } catch (err) { toast.error(String(err)); }
  };

  const createLiability = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      await api.createLiability({
        name: liaForm.name,
        type: liaForm.type,
        principal: parseFloat(liaForm.principal),
        min_payment: parseFloat(liaForm.min_payment) || undefined,
        due_date: liaForm.due_date || undefined,
      });
      toast.success("负债已记录");
      load();
    } catch (err) { toast.error(String(err)); }
  };

  return (
    <AppShell title="账户与负债" subtitle="管理现金、银行卡、信用卡及负债">
      <div className="grid grid-cols-3 gap-4 mb-4">
        <MetricCard label="总资产" sub="账户余额" value={fmt(totalAssets)} />
        <MetricCard label="总负债" sub="待还" value={fmt(totalLiabilities)} deltaVariant="danger" delta="需关注" />
        <MetricCard label="净资产" sub="资产-负债" value={fmt(totalAssets - totalLiabilities)} />
      </div>

      <div className="grid gap-4" style={{ gridTemplateColumns: "1fr 1fr" }}>
        <article className="card p-4">
          <h3 className="m-0 mb-4 text-[15px]">账户列表</h3>
          {accounts.map((a) => (
            <div key={a.id} className="flex justify-between py-2 border-b border-[var(--line)]">
              <div><strong>{a.name}</strong><div className="text-xs text-[var(--muted)]">{a.type}</div></div>
              <span className="font-bold amount-value">{fmt(a.balance)}</span>
            </div>
          ))}
          <form className="grid gap-2 mt-4" onSubmit={createAccount}>
            <input className="field" placeholder="账户名称" value={accForm.name} onChange={(e) => setAccForm({ ...accForm, name: e.target.value })} required />
            <select className="field" value={accForm.type} onChange={(e) => setAccForm({ ...accForm, type: e.target.value })}>
              {ACCOUNT_TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
            </select>
            <input className="field" type="number" placeholder="余额" value={accForm.balance} onChange={(e) => setAccForm({ ...accForm, balance: e.target.value })} />
            <button type="submit" className="btn btn-primary">添加账户</button>
          </form>
        </article>

        <article className="card p-4">
          <h3 className="m-0 mb-4 text-[15px]">负债管理</h3>
          {liabilities.map((l) => (
            <div key={l.id} className="py-2 border-b border-[var(--line)]">
              <div className="flex justify-between">
                <strong>{l.name}</strong>
                <span className="text-[var(--red)] font-bold amount-value">{fmt(l.principal)}</span>
              </div>
              <div className="text-xs text-[var(--muted)]">
                {l.type} {l.due_date && `· 还款日 ${l.due_date}`} {l.min_payment && `· 最低还款 ¥${l.min_payment}`}
              </div>
            </div>
          ))}
          <form className="grid gap-2 mt-4" onSubmit={createLiability}>
            <input className="field" placeholder="负债名称" value={liaForm.name} onChange={(e) => setLiaForm({ ...liaForm, name: e.target.value })} required />
            <select className="field" value={liaForm.type} onChange={(e) => setLiaForm({ ...liaForm, type: e.target.value })}>
              {LIABILITY_TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
            </select>
            <input className="field" type="number" placeholder="本金" value={liaForm.principal} onChange={(e) => setLiaForm({ ...liaForm, principal: e.target.value })} />
            <input className="field" type="date" value={liaForm.due_date} onChange={(e) => setLiaForm({ ...liaForm, due_date: e.target.value })} />
            <button type="submit" className="btn btn-primary">添加负债</button>
          </form>
        </article>
      </div>
    </AppShell>
  );
}
