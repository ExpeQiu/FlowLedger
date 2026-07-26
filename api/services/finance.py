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
    AccountType,
    BillFrequency,
    Budget,
    Category,
    CategoryType,
    Goal,
    Holding,
    HoldingType,
    Liability,
    LiabilityType,
    RecurringBill,
    Transaction,
    TxSource,
    TxType,
)
from schemas import (
    AlertItem,
    AssetItem,
    BudgetCategoryItem,
    CashFlowForecast,
    DashboardOut,
    HoldingOut,
    InvestAccountCheck,
    InvestValidationOut,
    MonthlyReport,
    PortfolioSummary,
    TrendItem,
)

# 投资类账户：balance = 账户总资产（闲置现金 + 持仓市值），持仓表为明细，不可再叠加计入净资产
INVEST_ACCOUNT_TYPES = {AccountType.broker, AccountType.fund}
# 允许账户余额与「持仓市值」之间的合理差额（闲置现金）；余额低于持仓市值超过该阈值则告警
HOLDINGS_OVER_BALANCE_TOLERANCE = Decimal("1.00")


def _month_range(period: str) -> tuple[date, date]:
    year, month = map(int, period.split("-"))
    last_day = monthrange(year, month)[1]
    return date(year, month, 1), date(year, month, last_day)


def _add_months(d: date, months: int) -> date:
    y = d.year + (d.month - 1 + months) // 12
    m = (d.month - 1 + months) % 12 + 1
    return date(y, m, min(d.day, monthrange(y, m)[1]))


def materialize_recurring_for_month(
    db: Session,
    month: str,
    *,
    adjust_balance: bool = False,
) -> dict:
    """
    将指定月份的定期账单落成支出流水。
    默认不改账户余额（余额通常已反映扣款）；仅补齐 transactions 供收支统计。
    """
    start, end = _month_range(month)
    created = 0
    skipped = 0
    bills = db.query(RecurringBill).order_by(RecurringBill.next_due).all()
    logger.info(
        "开始落账定期账单 month=%s bills=%s adjust_balance=%s",
        month,
        len(bills),
        adjust_balance,
    )

    for bill in bills:
        if bill.frequency != BillFrequency.monthly:
            logger.info("暂不支持非月频账单，跳过 bill=%s freq=%s", bill.name, bill.frequency.value)
            skipped += 1
            continue
        if not bill.account_id:
            logger.warning("定期账单缺少账户，跳过 bill=%s id=%s", bill.name, bill.id)
            skipped += 1
            continue

        tx_date = date(start.year, start.month, min(bill.next_due.day, end.day))
        exists = (
            db.query(Transaction)
            .filter(
                Transaction.type == TxType.expense,
                Transaction.account_id == bill.account_id,
                Transaction.amount == bill.amount,
                Transaction.merchant == bill.name,
                Transaction.date >= start,
                Transaction.date <= end,
            )
            .first()
        )
        if exists:
            logger.info("定期账单本月已有流水，跳过 bill=%s tx_id=%s", bill.name, exists.id)
            skipped += 1
            continue

        tx = Transaction(
            type=TxType.expense,
            amount=bill.amount,
            date=tx_date,
            account_id=bill.account_id,
            category_id=bill.category_id,
            merchant=bill.name,
            note=bill.note or f"定期账单 {month}",
            source=TxSource.rule,
        )
        db.add(tx)
        if adjust_balance:
            apply_transaction_to_balance(db, bill.account_id, TxType.expense, bill.amount)
        created += 1
        logger.info(
            "落账定期支出 bill=%s amount=%s date=%s account_id=%s",
            bill.name,
            bill.amount,
            tx_date,
            bill.account_id,
        )

        # next_due 仍落在本月（含过期未滚动）时推进到下一周期
        if start <= bill.next_due <= end:
            before = bill.next_due
            bill.next_due = _add_months(bill.next_due, 1)
            logger.info("推进定期账单 next_due bill=%s %s -> %s", bill.name, before, bill.next_due)

    db.commit()
    logger.info("定期账单落账完成 month=%s created=%s skipped=%s", month, created, skipped)
    return {"month": month, "created": created, "skipped": skipped, "adjust_balance": adjust_balance}


def _holding_market_value(h: Holding) -> Decimal:
    return h.quantity * h.current_price


def _holdings_mv_by_account(db: Session) -> dict:
    """按账户汇总持仓市值。"""
    rows = (
        db.query(
            Holding.account_id,
            func.coalesce(func.sum(Holding.quantity * Holding.current_price), 0),
        )
        .group_by(Holding.account_id)
        .all()
    )
    return {account_id: Decimal(str(mv)) for account_id, mv in rows}


def _mirrored_credit_debt(db: Session) -> Decimal:
    """信用卡若同时记在 accounts(负数) 与 liabilities，只扣一次。"""
    credit_account_debt = Decimal("0")
    for acc in db.query(Account).filter(Account.type == AccountType.credit).all():
        if acc.balance < 0:
            credit_account_debt += -acc.balance

    credit_liability = (
        db.query(func.coalesce(func.sum(Liability.principal), 0))
        .filter(Liability.type == LiabilityType.credit_card)
        .scalar()
        or Decimal("0")
    )
    return min(Decimal(str(credit_liability)), credit_account_debt)


def compute_net_worth(db: Session) -> Decimal:
    """
    净资产 = Σ账户余额 − 未在账户中体现的负债。
    投资账户余额已含持仓市值，不再叠加 holdings。
    """
    account_total = db.query(func.coalesce(func.sum(Account.balance), 0)).scalar() or Decimal("0")
    liability_total = db.query(func.coalesce(func.sum(Liability.principal), 0)).scalar() or Decimal("0")
    mirrored = _mirrored_credit_debt(db)
    net = Decimal(str(account_total)) - (Decimal(str(liability_total)) - mirrored)
    logger.info(
        "净资产计算 account_total=%s liability_total=%s mirrored_credit=%s net_worth=%s",
        account_total,
        liability_total,
        mirrored,
        net,
    )
    return net


def validate_invest_accounts(db: Session) -> InvestValidationOut:
    """校验投资账户余额与持仓市值的一致性。"""
    mv_by_account = _holdings_mv_by_account(db)
    accounts = (
        db.query(Account)
        .filter(Account.type.in_(list(INVEST_ACCOUNT_TYPES)))
        .order_by(Account.name)
        .all()
    )
    checks: list[InvestAccountCheck] = []
    ok = True

    for acc in accounts:
        holdings_mv = mv_by_account.get(acc.id, Decimal("0"))
        cash = acc.balance - holdings_mv
        issues: list[str] = []
        if holdings_mv > acc.balance + HOLDINGS_OVER_BALANCE_TOLERANCE:
            issues.append(
                f"持仓市值 {holdings_mv} 超过账户余额 {acc.balance}，差额 {holdings_mv - acc.balance}"
            )
            ok = False
            logger.warning("投资账户校验失败 account=%s id=%s: %s", acc.name, acc.id, issues[-1])
        else:
            logger.info(
                "投资账户校验通过 account=%s balance=%s holdings_mv=%s cash=%s",
                acc.name,
                acc.balance,
                holdings_mv,
                cash,
            )
        checks.append(
            InvestAccountCheck(
                account_id=acc.id,
                account_name=acc.name,
                account_type=acc.type.value,
                balance=acc.balance,
                holdings_mv=holdings_mv,
                cash=cash,
                ok=len(issues) == 0,
                issues=issues,
            )
        )

    orphan_holdings = (
        db.query(func.count(Holding.id))
        .outerjoin(Account, Holding.account_id == Account.id)
        .filter(Account.id.is_(None))
        .scalar()
        or 0
    )
    if orphan_holdings:
        ok = False
        logger.warning("存在无归属账户的持仓 orphan_count=%s", orphan_holdings)

    return InvestValidationOut(ok=ok, accounts=checks, orphan_holdings=int(orphan_holdings))


def enrich_account_out(db: Session, account: Account) -> "AccountOut":
    """账户输出；投资账户附带持仓市值/闲置现金拆分。"""
    from schemas import AccountOut

    base = AccountOut.model_validate(account)
    if account.type not in INVEST_ACCOUNT_TYPES:
        return base
    holdings_mv = _holdings_mv_by_account(db).get(account.id, Decimal("0"))
    cash = account.balance - holdings_mv
    count = db.query(func.count(Holding.id)).filter(Holding.account_id == account.id).scalar() or 0
    ok = holdings_mv <= account.balance + HOLDINGS_OVER_BALANCE_TOLERANCE
    return base.model_copy(
        update={
            "is_invest": True,
            "holdings_mv": holdings_mv,
            "cash": cash,
            "holdings_count": int(count),
            "invest_ok": ok,
        }
    )


def adjust_invest_balance_by_mv_delta(db: Session, account_id: UUID, mv_delta: Decimal) -> None:
    """
    持仓市值变动时同步账户总资产。
    约定：改仓/改价只动 balance，闲置现金 = balance - holdings_mv 保持不变（相对变动）。
    """
    if mv_delta == 0:
        return
    account = db.query(Account).filter(Account.id == account_id).first()
    if not account:
        return
    if account.type not in INVEST_ACCOUNT_TYPES:
        logger.warning("非投资账户忽略持仓市值同步 account_id=%s", account_id)
        return
    before = account.balance
    account.balance = Decimal(str(account.balance)) + Decimal(str(mv_delta))
    logger.info(
        "投资账户余额随持仓同步 account=%s delta=%s balance %s -> %s",
        account.name,
        mv_delta,
        before,
        account.balance,
    )
    db.flush()


def compute_import_hash(tx_date: date, amount: Decimal, merchant: str, account_id: UUID) -> str:
    raw = f"{tx_date.isoformat()}|{amount}|{merchant}|{account_id}"
    return hashlib.sha256(raw.encode()).hexdigest()


def apply_transaction_to_balance(db: Session, account_id: UUID, tx_type: TxType, amount: Decimal, sign: int = 1):
    account = db.query(Account).filter(Account.id == account_id).first()
    if not account:
        return
    # 投资账户：收支/转入转出视为闲置现金变动，同步增减总资产
    if tx_type == TxType.income:
        account.balance += amount * sign
    elif tx_type == TxType.expense:
        account.balance -= amount * sign
    db.flush()
    if account.type in INVEST_ACCOUNT_TYPES:
        logger.info(
            "投资账户流水影响余额 account=%s type=%s amount=%s sign=%s balance=%s",
            account.name,
            tx_type.value,
            amount,
            sign,
            account.balance,
        )


def get_dashboard(db: Session, month: str) -> DashboardOut:
    start, end = _month_range(month)
    logger.info("计算 Dashboard 聚合 month=%s", month)

    validation = validate_invest_accounts(db)
    if not validation.ok:
        logger.warning("Dashboard 聚合前投资账户校验未通过 issues=%s", validation.model_dump())

    net_worth = compute_net_worth(db)
    mv_by_account = _holdings_mv_by_account(db)
    holding_total = sum(mv_by_account.values(), Decimal("0"))

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

    invest_cash = Decimal("0")
    for acc in db.query(Account).filter(Account.type.in_(list(INVEST_ACCOUNT_TYPES))).all():
        invest_cash += max(acc.balance - mv_by_account.get(acc.id, Decimal("0")), Decimal("0"))

    liquid_cash = Decimal("0")
    for acc in db.query(Account).filter(~Account.type.in_(list(INVEST_ACCOUNT_TYPES))).all():
        if acc.type == AccountType.credit:
            continue
        liquid_cash += acc.balance

    cash_value = liquid_cash + invest_cash
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
    fund_value = Decimal(str(fund_value))
    stock_value = Decimal(str(stock_value))
    other_value = holding_total - fund_value - stock_value
    total_assets = cash_value + fund_value + stock_value + other_value
    asset_dist: list[AssetItem] = []
    if total_assets > 0:
        for name, val in [("现金", cash_value), ("基金", fund_value), ("股票", stock_value), ("其他", other_value)]:
            if val == 0:
                continue
            asset_dist.append(AssetItem(name=name, value=val, pct=round(float(val / total_assets * 100), 1)))

    investment_return = Decimal("0")
    for h in db.query(Holding).all():
        investment_return += (h.current_price - h.cost_price) * h.quantity
    logger.info("投资浮盈(未实现) investment_return=%s", investment_return)

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
    """投资组合：总资产 = 投资账户余额合计（持仓市值 + 闲置现金）。"""
    validation = validate_invest_accounts(db)
    holdings = db.query(Holding).all()
    holdings_value = Decimal("0")
    total_cost = Decimal("0")
    holding_outs: list[HoldingOut] = []

    for h in holdings:
        mv = _holding_market_value(h)
        cost = h.quantity * h.cost_price
        holdings_value += mv
        total_cost += cost
        profit_pct = float((h.current_price - h.cost_price) / h.cost_price * 100) if h.cost_price else 0
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

    cash_balance = sum((c.cash for c in validation.accounts), Decimal("0"))
    invest_account_total = sum((c.balance for c in validation.accounts), Decimal("0"))
    total_value = invest_account_total if validation.accounts else holdings_value + max(cash_balance, Decimal("0"))

    profit = holdings_value - total_cost
    profit_pct = float(profit / total_cost * 100) if total_cost else 0
    max_concentration = 0.0
    if total_value and holdings:
        max_mv = max(_holding_market_value(h) for h in holdings)
        max_concentration = float(max_mv / total_value * 100)

    type_targets: dict[str, Decimal] = {}
    type_actual: dict[str, Decimal] = {}
    for h in holdings:
        mv = _holding_market_value(h)
        type_actual[h.type.value] = type_actual.get(h.type.value, Decimal("0")) + mv
        if h.target_pct:
            type_targets[h.type.value] = type_targets.get(h.type.value, Decimal("0")) + h.target_pct
    if cash_balance > 0:
        type_actual["cash"] = type_actual.get("cash", Decimal("0")) + cash_balance

    rebalance = []
    for t, actual_val in type_actual.items():
        actual_pct = float(actual_val / total_value * 100) if total_value else 0
        target_pct = float(type_targets.get(t, Decimal("0")))
        rebalance.append({"type": t, "actual_pct": round(actual_pct, 1), "target_pct": round(target_pct, 1)})

    logger.info(
        "投资组合汇总 total=%s holdings=%s cash=%s profit=%s validation_ok=%s",
        total_value,
        holdings_value,
        cash_balance,
        profit,
        validation.ok,
    )

    return PortfolioSummary(
        total_value=total_value,
        holdings_value=holdings_value,
        cash_balance=cash_balance,
        total_cost=total_cost,
        profit=profit,
        profit_pct=round(profit_pct, 1),
        annualized_return=7.4,
        max_concentration=round(max_concentration, 1),
        holdings=holding_outs,
        rebalance=rebalance,
        validation_ok=validation.ok,
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
