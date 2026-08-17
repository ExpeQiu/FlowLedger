"""种子数据：默认分类、账户、示例流水"""

from datetime import date
from decimal import Decimal

from database import SessionLocal
from logging_config import logger
from models import (
    Account,
    AccountType,
    Budget,
    Category,
    CategoryType,
    Goal,
    Holding,
    HoldingType,
    Liability,
    LiabilityType,
    RecurringBill,
    BillFrequency,
    Rule,
    Transaction,
    TxSource,
    TxType,
)


def seed():
    db = SessionLocal()
    try:
        if db.query(Category).count() > 0:
            logger.info("种子数据已存在，跳过")
            return

        categories = [
            Category(name="餐饮", type=CategoryType.expense, color="amber"),
            Category(name="住房", type=CategoryType.expense, color="green"),
            Category(name="交通", type=CategoryType.expense, color="blue"),
            Category(name="购物", type=CategoryType.expense, color="violet"),
            Category(name="健康", type=CategoryType.expense, color="violet"),
            Category(name="收入", type=CategoryType.income, color="green"),
        ]
        db.add_all(categories)
        db.flush()

        accounts = [
            Account(name="工商储蓄卡", type=AccountType.bank, balance=Decimal("150000")),
            Account(name="招商信用卡", type=AccountType.credit, balance=Decimal("-8500")),
            Account(name="支付宝", type=AccountType.alipay, balance=Decimal("5000")),
            Account(name="微信支付", type=AccountType.wechat, balance=Decimal("2000")),
            # balance = 持仓市值 321285 + 闲置现金 30000
            Account(name="券商账户", type=AccountType.broker, balance=Decimal("351285")),
        ]
        db.add_all(accounts)
        db.flush()

        cat_map = {c.name: c for c in categories}
        acc_map = {a.name: a for a in accounts}
        today = date.today()
        period = f"{today.year}-{today.month:02d}"

        txs = [
            Transaction(type=TxType.expense, amount=Decimal("286.40"), date=today, account_id=acc_map["招商信用卡"].id, category_id=cat_map["餐饮"].id, merchant="Ole 超市", source=TxSource.manual),
            Transaction(type=TxType.expense, amount=Decimal("7.00"), date=today, account_id=acc_map["支付宝"].id, category_id=cat_map["交通"].id, merchant="地铁通勤", source=TxSource.manual),
            Transaction(type=TxType.expense, amount=Decimal("7300.00"), date=date(today.year, today.month, max(1, today.day - 1)), account_id=acc_map["工商储蓄卡"].id, category_id=cat_map["住房"].id, merchant="房租", source=TxSource.manual),
            Transaction(type=TxType.income, amount=Decimal("31600.00"), date=date(today.year, today.month, max(1, today.day - 1)), account_id=acc_map["工商储蓄卡"].id, category_id=cat_map["收入"].id, merchant="工资", source=TxSource.manual),
            Transaction(type=TxType.expense, amount=Decimal("399.00"), date=date(today.year, today.month, max(1, today.day - 2)), account_id=acc_map["招商信用卡"].id, category_id=cat_map["健康"].id, merchant="健身房", source=TxSource.manual),
            Transaction(type=TxType.expense, amount=Decimal("32.00"), date=date(today.year, today.month, max(1, today.day - 3)), account_id=acc_map["微信支付"].id, category_id=cat_map["餐饮"].id, merchant="咖啡", source=TxSource.manual),
        ]
        db.add_all(txs)

        budgets = [
            Budget(category_id=cat_map["餐饮"].id, period=period, amount=Decimal("6000"), alert_threshold=80),
            Budget(category_id=cat_map["住房"].id, period=period, amount=Decimal("12000"), alert_threshold=80),
            Budget(category_id=cat_map["交通"].id, period=period, amount=Decimal("2000"), alert_threshold=80),
            Budget(category_id=cat_map["购物"].id, period=period, amount=Decimal("3000"), alert_threshold=80),
        ]
        db.add_all(budgets)

        holdings = [
            Holding(symbol="510300", name="沪深300 ETF", type=HoldingType.fund, quantity=Decimal("38000"), cost_price=Decimal("4.92"), current_price=Decimal("5.32"), account_id=acc_map["券商账户"].id, target_pct=Decimal("60")),
            Holding(symbol="513100", name="纳斯达克100 ETF", type=HoldingType.fund, quantity=Decimal("12500"), cost_price=Decimal("1.36"), current_price=Decimal("1.53"), account_id=acc_map["券商账户"].id, target_pct=Decimal("25")),
            Holding(symbol="CASH", name="现金货币基金", type=HoldingType.cash, quantity=Decimal("100000"), cost_price=Decimal("1"), current_price=Decimal("1"), account_id=acc_map["券商账户"].id, target_pct=Decimal("15")),
        ]
        db.add_all(holdings)

        db.add(Liability(name="招商信用卡", type=LiabilityType.credit_card, principal=Decimal("8500"), due_date=date(today.year, today.month, 25), min_payment=Decimal("850")))

        db.add(RecurringBill(name="房租", amount=Decimal("7300"), frequency=BillFrequency.monthly, next_due=date(today.year, today.month, 15), category_id=cat_map["住房"].id, account_id=acc_map["工商储蓄卡"].id))
        db.add(RecurringBill(name="基金定投", amount=Decimal("3000"), frequency=BillFrequency.monthly, next_due=date(today.year, today.month, 18), account_id=acc_map["券商账户"].id))

        db.add(Goal(name="应急金", target_amount=Decimal("100000"), current_amount=Decimal("65000")))
        db.add(Goal(name="旅行基金", target_amount=Decimal("20000"), current_amount=Decimal("8000")))

        rules = [
            Rule(pattern="星巴克", category_id=cat_map["餐饮"].id, priority=10),
            Rule(pattern="地铁", category_id=cat_map["交通"].id, priority=10),
            Rule(pattern="超市", category_id=cat_map["购物"].id, priority=5),
            Rule(pattern="工资", category_id=cat_map["收入"].id, priority=10),
        ]
        db.add_all(rules)

        db.commit()
        logger.info("种子数据写入完成")
    finally:
        db.close()


if __name__ == "__main__":
    seed()
