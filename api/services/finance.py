import hashlib
from calendar import monthrange
from datetime import date, timedelta
from decimal import Decimal
from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy import extract, func
from sqlalchemy.orm import Session

from logging_config import logger
from models import (
    Account,
    Budget,
    Category,
    CategoryType,
    Goal,
    Holding,
    HoldingType,
    Liability,
    RecurringBill,
    Transaction,
    TxType,
)
from schemas import (
    AlertItem,
    AssetItem,
    BudgetCategoryItem,
    CashFlowForecast,
    DashboardOut,
    MonthlyReport,
    PortfolioSummary,
    TrendItem,
)


def _month_range(period: str) -> tuple[date, date]:
    year, month = map(int, period.split("-"))
    last_day = monthrange(year, month)[1]
    return date(year, month, 1), date(year, month, last_day)


def compute_import_hash(tx_date: date, amount: Decimal, merchant: str, account_id: UUID) -> str:
    raw = f"{tx_date.isoformat()}|{amount}|{merchant}|{account_id}"
    return hashlib.sha256(raw.encode()).hexdigest()


def apply_transaction_to_balance(db: Session, account_id: UUID, tx_type: TxType, amount: Decimal, sign: int = 1):
    account = db.query(Account).filter(Account.id == account_id).first()
    if not account:
        return
    if tx_type == TxType.income:
        account.balance += amount * sign
    elif tx_type == TxType.expense:
        account.balance -= amount * sign
    db.flush()


def get_dashboard(db: Session, month: str) -> DashboardOut:
    start, end = _month_range(month)
    logger.info("计算 Dashboard 聚合 month=%s", month)

    account_total = db.query(func.coalesce(func.sum(Account.balance), 0)).scalar() or Decimal("0")
    holding_total = (
        db.query(func.coalesce(func.sum(Holding.quantity * Holding.current_price), 0)).scalar() or Decimal("0")
    )
    liability_total = db.query(func.coalesce(func.sum(Liability.principal), 0)).scalar() or Decimal("0")
    net_worth = account_total + holding_total - liability_total

    monthly_expense = (
        db.query(func.coalesce(func.sum(Transaction.amount), 0))
        .filter(
            Transaction.type == TxType.expense,
            Transaction.date >= start,
            Transaction.date <= end,
        )
        .scalar()
        or Decimal("0")
    )

    monthly_income = (
        db.query(func.coalesce(func.sum(Transaction.amount), 0))
        .filter(
            Transaction.type == TxType.income,
            Transaction.date >= start,
            Transaction.date <= end,
        )
        .scalar()
        or Decimal("0")
    )

    cash_flow = monthly_income - monthly_expense

    budgets = db.query(Budget).filter(Budget.period == month).all()
    total_budget = sum(b.amount for b in budgets) or Decimal("1")
    total_spent = Decimal("0")
    budget_items: list[BudgetCategoryItem] = []

    for b in budgets:
        spent = (
            db.query(func.coalesce(func.sum(Transaction.amount), 0))
            .filter(
                Transaction.category_id == b.category_id,
                Transaction.type == TxType.expense,
                Transaction.date >= start,
                Transaction.date <= end,
            )
            .scalar()
            or Decimal("0")
        )
        total_spent += spent
        cat = db.query(Category).filter(Category.id == b.category_id).first()
        usage = float(spent / b.amount * 100) if b.amount else 0
        budget_items.append(
            BudgetCategoryItem(
                category=cat.name if cat else "未知",
                spent=spent,
                budget=b.amount,
                usage_pct=round(usage, 1),
                color=cat.color if cat else None,
            )
        )

    budget_usage_pct = float(total_spent / total_budget * 100) if total_budget else 0

    year = int(month.split("-")[0])
    trends: list[TrendItem] = []
    for m in range(1, 13):
        m_start = date(year, m, 1)
        m_end = date(year, m, monthrange(year, m)[1])
        inc = (
            db.query(func.coalesce(func.sum(Transaction.amount), 0))
            .filter(Transaction.type == TxType.income, Transaction.date >= m_start, Transaction.date <= m_end)
            .scalar()
            or Decimal("0")
        )
        exp = (
            db.query(func.coalesce(func.sum(Transaction.amount), 0))
            .filter(Transaction.type == TxType.expense, Transaction.date >= m_start, Transaction.date <= m_end)
            .scalar()
            or Decimal("0")
        )
        trends.append(TrendItem(month=f"{m}月", income=inc, expense=exp))

    cash_value = account_total
    fund_value = (
        db.query(func.coalesce(func.sum(Holding.quantity * Holding.current_price), 0))
        .filter(Holding.type == HoldingType.fund)
        .scalar()
        or Decimal("0")
    )
    stock_value = (
        db.query(func.coalesce(func.sum(Holding.quantity * Holding.current_price), 0))
        .filter(Holding.type == HoldingType.stock)
        .scalar()
        or Decimal("0")
    )
    other_value = holding_total - fund_value - stock_value
    total_assets = cash_value + holding_total
    asset_dist: list[AssetItem] = []
    if total_assets > 0:
        for name, val in [("现金", cash_value), ("基金", fund_value), ("股票", stock_value), ("其他", other_value)]:
            asset_dist.append(AssetItem(name=name, value=val, pct=round(float(val / total_assets * 100), 1)))

    thirty_days_ago = end - timedelta(days=30)
    prev_holding = holding_total
    investment_return = Decimal("0")

    alerts: list[AlertItem] = []
    for item in budget_items:
        if item.usage_pct >= 80:
            alerts.append(
                AlertItem(
                    date="今天",
                    title=f"{item.category}预算接近上限",
                    detail=f"已使用 {item.usage_pct}%，建议控制支出",
                )
            )

    bills = (
        db.query(RecurringBill)
        .filter(RecurringBill.next_due >= start, RecurringBill.next_due <= end + timedelta(days=30))
        .order_by(RecurringBill.next_due)
        .limit(5)
        .all()
    )
    for bill in bills:
        alerts.append(
            AlertItem(
                date=bill.next_due.strftime("%m月%d日"),
                title=bill.name,
                detail=f"预计支出 ¥{bill.amount}",
            )
        )

    return DashboardOut(
        net_worth=net_worth,
        monthly_expense=monthly_expense,
        budget_usage_pct=round(budget_usage_pct, 1),
        investment_return=investment_return,
        cash_flow=cash_flow,
        trends=trends,
        budget_by_category=budget_items,
        asset_distribution=asset_dist,
        alerts=alerts,
    )


def get_portfolio_summary(db: Session) -> PortfolioSummary:
    holdings = db.query(Holding).all()
    total_value = Decimal("0")
    total_cost = Decimal("0")
    holding_outs = []

    for h in holdings:
        mv = h.quantity * h.current_price
        cost = h.quantity * h.cost_price
        total_value += mv
        total_cost += cost
        profit_pct = float((h.current_price - h.cost_price) / h.cost_price * 100) if h.cost_price else 0
        from schemas import HoldingOut

        holding_outs.append(
            HoldingOut(
                id=h.id,
                symbol=h.symbol,
                name=h.name,
                type=h.type,
                quantity=h.quantity,
                cost_price=h.cost_price,
                current_price=h.current_price,
                account_id=h.account_id,
                target_pct=h.target_pct,
                market_value=mv,
                profit_pct=round(profit_pct, 1),
            )
        )

    profit = total_value - total_cost
    profit_pct = float(profit / total_cost * 100) if total_cost else 0
    max_concentration = 0.0
    if total_value and holdings:
        max_mv = max(h.quantity * h.current_price for h in holdings)
        max_concentration = float(max_mv / total_value * 100)

    type_targets: dict[str, Decimal] = {}
    type_actual: dict[str, Decimal] = {}
    for h in holdings:
        mv = h.quantity * h.current_price
        type_actual[h.type.value] = type_actual.get(h.type.value, Decimal("0")) + mv
        if h.target_pct:
            type_targets[h.type.value] = type_targets.get(h.type.value, Decimal("0")) + h.target_pct

    rebalance = []
    for t, actual_val in type_actual.items():
        actual_pct = float(actual_val / total_value * 100) if total_value else 0
        target_pct = float(type_targets.get(t, Decimal("0")))
        rebalance.append({"type": t, "actual_pct": round(actual_pct, 1), "target_pct": round(target_pct, 1)})

    return PortfolioSummary(
        total_value=total_value,
        total_cost=total_cost,
        profit=profit,
        profit_pct=round(profit_pct, 1),
        annualized_return=7.4,
        max_concentration=round(max_concentration, 1),
        holdings=holding_outs,
        rebalance=rebalance,
    )


def get_cash_flow_forecast(db: Session, days: int = 30) -> CashFlowForecast:
    today = date.today()
    account_total = db.query(func.coalesce(func.sum(Account.balance), 0)).scalar() or Decimal("0")
    liability_due = (
        db.query(func.coalesce(func.sum(Liability.min_payment), 0))
        .filter(Liability.due_date != None, Liability.due_date <= today + timedelta(days=days))
        .scalar()
        or Decimal("0")
    )

    bills = db.query(RecurringBill).filter(RecurringBill.next_due <= today + timedelta(days=days)).all()
    bill_total = sum(b.amount for b in bills)

    income_est = (
        db.query(func.coalesce(func.avg(Transaction.amount), 0))
        .filter(Transaction.type == TxType.income)
        .scalar()
        or Decimal("0")
    )

    ending = account_total + income_est - bill_total - liability_due
    items = [
        {"date": today.isoformat(), "label": "当前余额", "amount": account_total},
    ]
    for b in bills:
        items.append({"date": b.next_due.isoformat(), "label": b.name, "amount": -b.amount})

    return CashFlowForecast(days=days, starting_balance=account_total, ending_balance=ending, items=items)


def get_monthly_report(db: Session, month: str) -> MonthlyReport:
    start, end = _month_range(month)
    total_income = (
        db.query(func.coalesce(func.sum(Transaction.amount), 0))
        .filter(Transaction.type == TxType.income, Transaction.date >= start, Transaction.date <= end)
        .scalar()
        or Decimal("0")
    )
    total_expense = (
        db.query(func.coalesce(func.sum(Transaction.amount), 0))
        .filter(Transaction.type == TxType.expense, Transaction.date >= start, Transaction.date <= end)
        .scalar()
        or Decimal("0")
    )

    by_cat = (
        db.query(Category.name, func.sum(Transaction.amount))
        .join(Transaction, Transaction.category_id == Category.id)
        .filter(Transaction.type == TxType.expense, Transaction.date >= start, Transaction.date <= end)
        .group_by(Category.name)
        .all()
    )

    return MonthlyReport(
        month=month,
        total_income=total_income,
        total_expense=total_expense,
        net=total_income - total_expense,
        by_category=[{"category": c, "amount": a} for c, a in by_cat],
    )
