"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Toaster } from "sonner";

const NAV = [
  { href: "/", label: "总览", panel: "overview" },
  { href: "/expenses", label: "开支", panel: "expenses" },
  { href: "/investments", label: "投资", panel: "investments" },
  { href: "/budgets", label: "预算", panel: "budgets" },
  { href: "/accounts", label: "账户", panel: "accounts" },
  { href: "/cli", label: "CLI", panel: "cli" },
  { href: "/dimensions", label: "扩展", panel: "dimensions" },
];

export function Sidebar() {
  const pathname = usePathname();
  return (
    <aside
      className="sticky top-0 h-screen border-r border-[var(--line)] bg-white/85 backdrop-blur-[18px] p-[22px_16px]"
      style={{ width: "var(--sidebar)" }}
    >
      <div className="flex items-center gap-3 px-2 pb-[22px]">
        <div className="grid place-items-center w-[38px] h-[38px] rounded-lg bg-[var(--ink)] text-white font-extrabold">¥</div>
        <div>
          <h1 className="m-0 text-[17px] leading-tight font-semibold">FlowLedger</h1>
          <span className="block mt-[3px] text-[var(--muted)] text-xs">个人财务管理系统</span>
        </div>
      </div>
      <nav className="grid gap-1.5">
        {NAV.map((item) => {
          const active = pathname === item.href;
          return (
            <Link
              key={item.href}
              href={item.href}
              className={`flex items-center gap-2.5 w-full min-h-[42px] px-3 rounded-lg border text-left no-underline transition-colors ${
                active
                  ? "border-[var(--line)] bg-[var(--ink)] text-white"
                  : "border-transparent text-[var(--muted)] hover:bg-[var(--surface-soft)] hover:text-[var(--ink)]"
              }`}
            >
              {item.label}
            </Link>
          );
        })}
      </nav>
      <div className="absolute right-4 bottom-[18px] left-4 p-3.5 border border-[var(--line)] rounded-lg bg-[var(--surface-soft)]">
        <strong className="block mb-1.5 text-[13px]">本地数据源</strong>
        <code className="block overflow-hidden text-[var(--muted)] text-xs text-ellipsis whitespace-nowrap">
          postgresql://localhost:5432/flowledger
        </code>
      </div>
    </aside>
  );
}

export function Topbar({
  title,
  subtitle,
  actions,
}: {
  title: string;
  subtitle: string;
  actions?: React.ReactNode;
}) {
  return (
    <header className="sticky top-0 z-10 flex items-center justify-between gap-4 min-h-[72px] px-7 py-3.5 border-b border-[var(--line)] bg-[var(--bg)]/85 backdrop-blur-[18px]">
      <div>
        <h2 className="m-0 text-[22px] leading-tight">{title}</h2>
        <p className="mt-1 mb-0 text-[var(--muted)] text-[13px]">{subtitle}</p>
      </div>
      {actions && <div className="flex items-center gap-2 flex-wrap justify-end">{actions}</div>}
    </header>
  );
}

export function AppShell({
  title,
  subtitle,
  actions,
  children,
}: {
  title: string;
  subtitle: string;
  actions?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <div className="grid min-h-screen" style={{ gridTemplateColumns: "var(--sidebar) 1fr" }}>
      <Sidebar />
      <main className="min-w-0">
        <Topbar title={title} subtitle={subtitle} actions={actions} />
        <div className="w-full max-w-[1440px] mx-auto px-7 py-6 pb-10">{children}</div>
      </main>
      <Toaster position="bottom-right" richColors />
    </div>
  );
}

export function MetricCard({
  label,
  sub,
  value,
  delta,
  deltaVariant = "green",
}: {
  label: string;
  sub: string;
  value: string;
  delta?: string;
  deltaVariant?: "green" | "warn" | "danger";
}) {
  const deltaColors = {
    green: "bg-[var(--green-soft)] text-[var(--green)]",
    warn: "bg-[var(--amber-soft)] text-[var(--amber)]",
    danger: "bg-[var(--red-soft)] text-[var(--red)]",
  };
  return (
    <article className="card p-4">
      <div className="flex items-center justify-between text-[var(--muted)] text-[13px]">
        <span>{label}</span>
        <span>{sub}</span>
      </div>
      <div className="mt-3.5 text-[25px] font-bold leading-tight amount-value">{value}</div>
      {delta && (
        <div className={`inline-flex items-center gap-1 mt-2.5 px-2 py-1 rounded-full text-xs font-semibold ${deltaColors[deltaVariant]}`}>
          {delta}
        </div>
      )}
    </article>
  );
}

export function BudgetProgress({
  name,
  spent,
  budget,
  usagePct,
}: {
  name: string;
  spent: number;
  budget: number;
  usagePct: number;
}) {
  const color = usagePct >= 80 ? "var(--red)" : usagePct >= 60 ? "var(--amber)" : "var(--green)";
  return (
    <div className="mb-3">
      <div className="flex justify-between mb-1.5 text-sm">
        <strong>{name}</strong>
        <span className="text-[var(--muted)]">{fmt(spent)} / {fmt(budget)}</span>
      </div>
      <div className="progress-bar">
        <span style={{ width: `${Math.min(usagePct, 100)}%`, background: color }} />
      </div>
    </div>
  );
}

function fmt(n: number) {
  return "¥" + n.toLocaleString("zh-CN");
}
