const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:9011";

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...options?.headers,
    },
    cache: "no-store",
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`API ${res.status}: ${text}`);
  }
  if (res.status === 204) return undefined as T;
  return res.json();
}

export const api = {
  dashboard: (month?: string) =>
    request<Dashboard>(`/api/dashboard${month ? `?month=${month}` : ""}`),
  accounts: () => request<Account[]>("/api/accounts"),
  accountsNetWorth: () => request<{ net_worth: number }>("/api/accounts/net-worth"),
  createAccount: (data: Partial<Account>) =>
    request<Account>("/api/accounts", { method: "POST", body: JSON.stringify(data) }),
  deleteAccount: (id: string) =>
    request<void>(`/api/accounts/${id}`, { method: "DELETE" }),
  categories: () => request<Category[]>("/api/categories"),
  transactions: (params?: Record<string, string>) => {
    const q = params ? "?" + new URLSearchParams(params).toString() : "";
    return request<Transaction[]>(`/api/transactions${q}`);
  },
  transfers: (params?: Record<string, string>) => {
    const q = params ? "?" + new URLSearchParams(params).toString() : "";
    return request<Transfer[]>(`/api/transactions/transfers${q}`);
  },
  createTransaction: (data: Record<string, unknown>) =>
    request<Transaction>("/api/transactions", { method: "POST", body: JSON.stringify(data) }),
  budgets: (period?: string) =>
    request<Budget[]>(`/api/budgets${period ? `?period=${period}` : ""}`),
  createBudget: (data: Record<string, unknown>) =>
    request<Budget>("/api/budgets", { method: "POST", body: JSON.stringify(data) }),
  holdings: () => request<Holding[]>("/api/holdings"),
  portfolioSummary: () => request<PortfolioSummary>("/api/holdings/summary"),
  dailyPnl: (month?: string) =>
    request<MonthlyDailyPnl>(`/api/holdings/daily-pnl${month ? `?month=${month}` : ""}`),
  validateInvestAccounts: () => request<InvestValidation>("/api/holdings/validate"),
  syncFromInvest: () =>
    request<Record<string, unknown>>("/api/holdings/sync-from-invest", { method: "POST" }),
  createHolding: (data: Record<string, unknown>) =>
    request<Holding>("/api/holdings", { method: "POST", body: JSON.stringify(data) }),
  liabilities: () => request<Liability[]>("/api/liabilities"),
  createLiability: (data: Record<string, unknown>) =>
    request<Liability>("/api/liabilities", { method: "POST", body: JSON.stringify(data) }),
  goals: () => request<Goal[]>("/api/goals"),
  createGoal: (data: Record<string, unknown>) =>
    request<Goal>("/api/goals", { method: "POST", body: JSON.stringify(data) }),
  recurringBills: () => request<RecurringBill[]>("/api/recurring-bills"),
  materializeRecurring: (month?: string, adjustBalance = false) => {
    const params = new URLSearchParams();
    if (month) params.set("month", month);
    if (adjustBalance) params.set("adjust_balance", "true");
    const q = params.toString() ? `?${params}` : "";
    return request<{ month: string; created: number; skipped: number; adjust_balance: boolean }>(
      `/api/recurring-bills/materialize${q}`,
      { method: "POST" },
    );
  },
  rules: () => request<Rule[]>("/api/rules"),
  createRule: (data: Record<string, unknown>) =>
    request<Rule>("/api/rules", { method: "POST", body: JSON.stringify(data) }),
  monthlyReport: (month?: string) =>
    request<MonthlyReport>(`/api/reports/monthly${month ? `?month=${month}` : ""}`),
  cashflow: (days = 30) => request<CashFlowForecast>(`/api/reports/cashflow?days=${days}`),
  importCsv: async (file: File, source: string, accountId: string) => {
    const form = new FormData();
    form.append("file", file);
    form.append("source", source);
    form.append("account_id", accountId);
    const res = await fetch(`${API_URL}/api/import/csv`, { method: "POST", body: form });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  },
};

export interface Dashboard {
  net_worth: number;
  monthly_expense: number;
  expense_booked?: number;
  expense_recurring_pending?: number;
  budget_usage_pct: number;
  investment_return: number;
  cash_flow: number;
  trends: { month: string; income: number; expense: number }[];
  budget_by_category: { category: string; spent: number; budget: number; usage_pct: number; color?: string }[];
  asset_distribution: { name: string; value: number; pct: number }[];
  alerts: { date: string; title: string; detail: string }[];
}

export interface Account {
  id: string;
  name: string;
  type: string;
  balance: number;
  currency: string;
  is_invest?: boolean;
  holdings_mv?: number;
  cash?: number;
  holdings_count?: number;
  invest_ok?: boolean;
}

export interface Category {
  id: string;
  name: string;
  type: string;
  color?: string;
}

export interface Transaction {
  id: string;
  type: string;
  amount: number;
  date: string;
  account_id: string;
  category_id?: string;
  merchant?: string;
  note?: string;
  transfer_pair_id?: string;
  account_name?: string;
  category_name?: string;
}

export interface Transfer {
  transfer_pair_id: string;
  date: string;
  amount: number;
  from_account_id: string;
  from_account_name: string;
  to_account_id: string;
  to_account_name: string;
  note?: string;
  source: string;
  created_at: string;
  out_tx_id: string;
  in_tx_id: string;
}

export interface Budget {
  id: string;
  category_id: string;
  period: string;
  amount: number;
  alert_threshold: number;
  category_name?: string;
  spent?: number;
  usage_pct?: number;
}

export interface Holding {
  id: string;
  symbol: string;
  name: string;
  type: string;
  quantity: number;
  cost_price: number;
  current_price: number;
  market_value?: number;
  profit_pct?: number;
}

export interface PortfolioSummary {
  total_value: number;
  holdings_value?: number;
  cash_balance?: number;
  total_cost: number;
  profit: number;
  profit_pct: number;
  annualized_return: number;
  max_concentration: number;
  holdings: Holding[];
  rebalance: { type: string; actual_pct: number; target_pct: number }[];
  validation_ok?: boolean;
}

export interface MonthlyDailyPnl {
  month: string;
  days: {
    date: string;
    day: string;
    daily_pnl: number;
    daily_pnl_pct: number;
    total_asset: number;
  }[];
  total_pnl: number;
  up_days: number;
  down_days: number;
}

export interface InvestValidation {
  ok: boolean;
  orphan_holdings: number;
  accounts: {
    account_id: string;
    account_name: string;
    account_type: string;
    balance: number;
    holdings_mv: number;
    cash: number;
    ok: boolean;
    issues: string[];
  }[];
}

export interface Liability {
  id: string;
  name: string;
  type: string;
  principal: number;
  interest_rate?: number;
  due_date?: string;
  min_payment?: number;
}

export interface Goal {
  id: string;
  name: string;
  target_amount: number;
  current_amount: number;
  deadline?: string;
  progress_pct?: number;
}

export interface RecurringBill {
  id: string;
  name: string;
  amount: number;
  frequency: string;
  next_due: string;
}

export interface Rule {
  id: string;
  pattern: string;
  category_id: string;
  category_name?: string;
  priority: number;
  is_active: boolean;
}

export interface MonthlyReport {
  month: string;
  total_income: number;
  total_expense: number;
  net: number;
  by_category: { category: string; amount: number }[];
}

export interface CashFlowForecast {
  days: number;
  starting_balance: number;
  ending_balance: number;
  items: { date: string; label: string; amount: number }[];
}

export function fmt(n: number | string) {
  const v = typeof n === "string" ? parseFloat(n) : n;
  return "¥" + v.toLocaleString("zh-CN", { minimumFractionDigits: 0, maximumFractionDigits: 2 });
}

export function currentMonth() {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}

export function tagClass(color?: string) {
  const map: Record<string, string> = {
    green: "tag-green", blue: "tag-blue", amber: "tag-amber", red: "tag-red", violet: "tag-violet",
  };
  return `tag ${map[color || ""] || ""}`;
}
