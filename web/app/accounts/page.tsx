"use client";

import { useEffect, useState } from "react";
import { toast } from "sonner";
import { AppShell, MetricCard } from "@/components/layout";
import { api, fmt, type Account, type Liability, type Transfer } from "@/lib/api";

const ACCOUNT_TYPES = ["cash", "bank", "credit", "alipay", "wechat", "broker", "fund"];
const LIABILITY_TYPES = ["credit_card", "mortgage", "loan", "installment"];
const TYPE_LABEL: Record<string, string> = {
  cash: "现金", bank: "银行", credit: "信用卡", alipay: "支付宝", wechat: "微信",
  broker: "券商", fund: "基金账户",
};
const SOURCE_LABEL: Record<string, string> = {
  manual: "手动",
  csv: "导入",
  alipay: "支付宝",
  wechat: "微信",
  rule: "规则",
};

export default function AccountsPage() {
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [liabilities, setLiabilities] = useState<Liability[]>([]);
  const [transfers, setTransfers] = useState<Transfer[]>([]);
  const [netWorth, setNetWorth] = useState<number | null>(null);
  const [filterAccountId, setFilterAccountId] = useState("");
  const [accForm, setAccForm] = useState({ name: "", type: "bank", balance: "0" });
  const [liaForm, setLiaForm] = useState({ name: "", type: "credit_card", principal: "0", min_payment: "0", due_date: "" });
  const [txForm, setTxForm] = useState({
    from_account_id: "",
    to_account_id: "",
    amount: "",
    date: new Date().toISOString().slice(0, 10),
    note: "",
  });

  const load = () => {
    api.accounts().then(setAccounts).catch((e) => toast.error(e.message));
    api.liabilities().then(setLiabilities).catch(() => {});
    api.accountsNetWorth().then((r) => setNetWorth(Number(r.net_worth))).catch(() => setNetWorth(null));
    const params: Record<string, string> = { limit: "100" };
    if (filterAccountId) params.account_id = filterAccountId;
    api.transfers(params)
      .then(setTransfers)
      .catch((e) => {
        console.error("[accounts] 加载转账记录失败", e);
        toast.error(e.message);
      });
  };

  useEffect(() => { load(); }, [filterAccountId]);

  const totalAssets = accounts.reduce((s, a) => s + Number(a.balance), 0);
  const totalLiabilities = liabilities.reduce((s, l) => s + Number(l.principal), 0);
  const investAccounts = accounts.filter((a) => a.is_invest);

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

  const createTransfer = async (e: React.FormEvent) => {
    e.preventDefault();
    const fromId = txForm.from_account_id || accounts[0]?.id;
    const toId = txForm.to_account_id || accounts[1]?.id;
    if (!fromId || !toId) {
      toast.error("请先创建至少两个账户");
      return;
    }
    if (fromId === toId) {
      toast.error("转出与转入账户不能相同");
      return;
    }
    try {
      await api.createTransaction({
        type: "transfer",
        amount: parseFloat(txForm.amount),
        date: txForm.date,
        account_id: fromId,
        to_account_id: toId,
        note: txForm.note || undefined,
      });
      toast.success("转账已记录");
      setTxForm({
        from_account_id: fromId,
        to_account_id: toId,
        amount: "",
        date: new Date().toISOString().slice(0, 10),
        note: "",
      });
      load();
    } catch (err) {
      console.error("[accounts] 创建转账失败", err);
      toast.error(String(err));
    }
  };

  return (
    <AppShell title="账户与负债" subtitle="投资账户余额 = 持仓市值 + 闲置现金">
      <div className="grid grid-cols-3 gap-4 mb-4">
        <MetricCard label="账户合计" sub="含投资总资产" value={fmt(totalAssets)} />
        <MetricCard label="总负债" sub="待还" value={fmt(totalLiabilities)} deltaVariant="danger" delta="需关注" />
        <MetricCard label="净资产" sub="与总览同口径" value={fmt(netWorth ?? totalAssets)} />
      </div>

      {investAccounts.length > 0 && (
        <article className="card p-4 mb-4">
          <h3 className="m-0 mb-4 text-[15px]">投资账户拆分</h3>
          {investAccounts.map((a) => (
            <div key={a.id} className="py-3 border-b border-[var(--line)] last:border-0">
              <div className="flex justify-between mb-1">
                <strong>{a.name}</strong>
                <span className="font-bold amount-value">{fmt(a.balance)}</span>
              </div>
              <div className="text-xs text-[var(--muted)] flex gap-4 flex-wrap">
                <span>持仓市值 {fmt(a.holdings_mv ?? 0)}</span>
                <span>闲置现金 {fmt(a.cash ?? 0)}</span>
                <span>{a.holdings_count ?? 0} 只标的</span>
                {a.invest_ok === false && <span className="text-[var(--red)]">余额与持仓不一致</span>}
              </div>
            </div>
          ))}
        </article>
      )}

      <div className="grid gap-4" style={{ gridTemplateColumns: "1fr 1fr" }}>
        <article className="card p-4">
          <h3 className="m-0 mb-4 text-[15px]">账户列表</h3>
          {accounts.map((a) => (
            <div key={a.id} className="flex justify-between py-2 border-b border-[var(--line)]">
              <div>
                <strong>{a.name}</strong>
                <div className="text-xs text-[var(--muted)]">
                  {TYPE_LABEL[a.type] || a.type}
                  {a.is_invest ? " · 总资产" : ""}
                </div>
              </div>
              <span className="font-bold amount-value">{fmt(a.balance)}</span>
            </div>
          ))}
          <form className="grid gap-2 mt-4" onSubmit={createAccount}>
            <input className="field" placeholder="账户名称" value={accForm.name} onChange={(e) => setAccForm({ ...accForm, name: e.target.value })} required />
            <select className="field" value={accForm.type} onChange={(e) => setAccForm({ ...accForm, type: e.target.value })}>
              {ACCOUNT_TYPES.map((t) => <option key={t} value={t}>{TYPE_LABEL[t] || t}</option>)}
            </select>
            <input className="field" type="number" placeholder={accForm.type === "broker" || accForm.type === "fund" ? "总资产（现金+持仓）" : "余额"} value={accForm.balance} onChange={(e) => setAccForm({ ...accForm, balance: e.target.value })} />
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

      <div className="grid gap-4 mt-4" style={{ gridTemplateColumns: "1.45fr 0.75fr" }}>
        <article className="card overflow-x-auto">
          <div className="flex justify-between items-center gap-3 p-4 pb-0 flex-wrap">
            <div>
              <h3 className="m-0 text-[15px]">转账记录</h3>
              <p className="m-0 mt-1 text-xs text-[var(--muted)]">按配对展示：转出账户 → 转入账户</p>
            </div>
            <div className="flex items-center gap-2">
              <select
                className="field max-w-[180px]"
                value={filterAccountId}
                onChange={(e) => setFilterAccountId(e.target.value)}
              >
                <option value="">全部账户</option>
                {accounts.map((a) => (
                  <option key={a.id} value={a.id}>{a.name}</option>
                ))}
              </select>
              <span className="text-xs text-[var(--muted)] whitespace-nowrap">共 {transfers.length} 笔</span>
            </div>
          </div>
          <table className="w-full min-w-[720px] border-collapse">
            <thead>
              <tr className="text-[var(--muted)] text-xs">
                {["日期", "转出", "转入", "金额", "备注", "来源"].map((h) => (
                  <th key={h} className="p-3 text-left border-b border-[var(--line)]">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {transfers.length === 0 ? (
                <tr>
                  <td colSpan={6} className="p-8 text-center text-[var(--muted)]">
                    暂无转账记录，可在右侧发起账户间转账
                  </td>
                </tr>
              ) : (
                transfers.map((t) => (
                  <tr key={t.transfer_pair_id} className="border-b border-[var(--line)]">
                    <td className="p-3 whitespace-nowrap">{t.date}</td>
                    <td className="p-3">{t.from_account_name}</td>
                    <td className="p-3">{t.to_account_name}</td>
                    <td className="p-3 text-right font-bold amount-value">{fmt(t.amount)}</td>
                    <td className="p-3 text-[var(--muted)]">{t.note || "-"}</td>
                    <td className="p-3 text-xs text-[var(--muted)]">{SOURCE_LABEL[t.source] || t.source}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </article>

        <aside className="card p-4">
          <h3 className="m-0 mb-4 text-[15px]">发起转账</h3>
          <form className="grid gap-2.5" onSubmit={createTransfer}>
            <label className="text-sm">转出账户
              <select
                className="field mt-1"
                value={txForm.from_account_id}
                onChange={(e) => setTxForm({ ...txForm, from_account_id: e.target.value })}
                required
              >
                <option value="">选择账户</option>
                {accounts.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}
              </select>
            </label>
            <label className="text-sm">转入账户
              <select
                className="field mt-1"
                value={txForm.to_account_id}
                onChange={(e) => setTxForm({ ...txForm, to_account_id: e.target.value })}
                required
              >
                <option value="">选择账户</option>
                {accounts.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}
              </select>
            </label>
            <label className="text-sm">金额
              <input
                className="field mt-1"
                type="number"
                min="0.01"
                step="0.01"
                value={txForm.amount}
                onChange={(e) => setTxForm({ ...txForm, amount: e.target.value })}
                required
              />
            </label>
            <label className="text-sm">日期
              <input
                className="field mt-1"
                type="date"
                value={txForm.date}
                onChange={(e) => setTxForm({ ...txForm, date: e.target.value })}
                required
              />
            </label>
            <label className="text-sm">备注
              <input
                className="field mt-1"
                placeholder="可选"
                value={txForm.note}
                onChange={(e) => setTxForm({ ...txForm, note: e.target.value })}
              />
            </label>
            <button type="submit" className="btn btn-primary" disabled={accounts.length < 2}>
              确认转账
            </button>
          </form>
        </aside>
      </div>
    </AppShell>
  );
}
