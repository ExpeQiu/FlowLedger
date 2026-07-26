"""从 invest.lcteam 同步真实持仓到 flowledger。

权威源（见 Macmin2-POSTGRES_DB 文档）：
- invest.lcteam.position_snapshots → 账户总资产 / 现金 / 持仓市值
- invest.lcteam.positions (account_type=real) → 持仓明细
"""

from __future__ import annotations

from calendar import monthrange
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from config import settings
from logging_config import logger
from models import Account, AccountType, Holding, HoldingType


def _holding_type(code: str, category: str | None) -> HoldingType:
    c = (category or "").lower()
    if c in {"fund", "etf", "cash"}:
        return HoldingType.cash if c == "cash" else HoldingType.fund
    # A 股 ETF/场内基金常见代码前缀
    if code.startswith(("51", "56", "58", "15", "16", "18")):
        return HoldingType.fund
    return HoldingType.stock


def _d(v: Any) -> Decimal:
    if v is None:
        return Decimal("0")
    return Decimal(str(v))


def fetch_latest_real_portfolio(invest_url: str | None = None) -> dict[str, Any]:
    url = invest_url or settings.invest_database_url
    engine = create_engine(url, pool_pre_ping=True)
    with engine.connect() as conn:
        snap = conn.execute(
            text(
                """
                SELECT snapshot_date, total_asset, cash, position_value, position_ratio,
                       daily_pnl, daily_pnl_pct
                FROM lcteam.position_snapshots
                ORDER BY snapshot_date DESC, created_at DESC
                LIMIT 1
                """
            )
        ).mappings().first()
        if not snap:
            raise RuntimeError("invest.lcteam.position_snapshots 无数据")

        snap_date = snap["snapshot_date"]
        rows = conn.execute(
            text(
                """
                SELECT stock_code, stock_name, quantity, cost_price, current_price,
                       market_value, profit_loss, profit_loss_pct, category
                FROM lcteam.positions
                WHERE account_type = 'real' AND snapshot_date = :d
                ORDER BY market_value DESC NULLS LAST
                """
            ),
            {"d": snap_date},
        ).mappings().all()

    positions = [dict(r) for r in rows]
    logger.info(
        "拉取 invest 持仓 snapshot=%s total_asset=%s cash=%s position_value=%s count=%s",
        snap_date,
        snap["total_asset"],
        snap["cash"],
        snap["position_value"],
        len(positions),
    )
    return {
        "snapshot_date": str(snap_date),
        "total_asset": _d(snap["total_asset"]),
        "cash": _d(snap["cash"]),
        "position_value": _d(snap["position_value"]),
        "position_ratio": _d(snap["position_ratio"]),
        "daily_pnl": _d(snap["daily_pnl"]),
        "daily_pnl_pct": _d(snap["daily_pnl_pct"]),
        "positions": positions,
    }


def _month_bounds(month: str) -> tuple[date, date]:
    """解析 YYYY-MM，返回 [start, end) 日期区间。"""
    try:
        y, m = month.split("-")
        year, mon = int(y), int(m)
        if mon < 1 or mon > 12:
            raise ValueError
        start = date(year, mon, 1)
        last = monthrange(year, mon)[1]
        # end 为下月 1 日语义：用当月最后一天 + 过滤用 <= last
        end = date(year, mon, last)
        return start, end
    except Exception as e:
        raise ValueError(f"无效月份格式: {month}，期望 YYYY-MM") from e


def fetch_monthly_daily_pnl(month: str | None = None, invest_url: str | None = None) -> dict[str, Any]:
    """从 invest.lcteam.position_snapshots 拉取指定月每日收益波动。

    同一 snapshot_date 多条时取 created_at 最新一条。
    """
    if not month:
        today = date.today()
        month = f"{today.year:04d}-{today.month:02d}"
    start, end = _month_bounds(month)
    url = invest_url or settings.invest_database_url
    engine = create_engine(url, pool_pre_ping=True)
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                """
                SELECT snapshot_date, daily_pnl, daily_pnl_pct, total_asset
                FROM (
                    SELECT DISTINCT ON (snapshot_date)
                           snapshot_date, daily_pnl, daily_pnl_pct, total_asset, created_at
                    FROM lcteam.position_snapshots
                    WHERE snapshot_date >= :start AND snapshot_date <= :end
                    ORDER BY snapshot_date ASC, created_at DESC
                ) t
                ORDER BY snapshot_date ASC
                """
            ),
            {"start": start, "end": end},
        ).mappings().all()

    days: list[dict[str, Any]] = []
    for r in rows:
        d = r["snapshot_date"]
        day_label = d.strftime("%m-%d") if hasattr(d, "strftime") else str(d)[5:10]
        days.append(
            {
                "date": str(d),
                "day": day_label,
                "daily_pnl": float(_d(r["daily_pnl"])),
                "daily_pnl_pct": float(_d(r["daily_pnl_pct"])),
                "total_asset": float(_d(r["total_asset"])),
            }
        )

    total_pnl = sum(x["daily_pnl"] for x in days)
    up_days = sum(1 for x in days if x["daily_pnl"] > 0)
    down_days = sum(1 for x in days if x["daily_pnl"] < 0)
    logger.info(
        "月度每日收益 month=%s days=%s total_pnl=%s up=%s down=%s",
        month,
        len(days),
        round(total_pnl, 2),
        up_days,
        down_days,
    )
    return {
        "month": month,
        "days": days,
        "total_pnl": round(total_pnl, 2),
        "up_days": up_days,
        "down_days": down_days,
    }


def ensure_invest_account(db: Session, name: str = "投资账户") -> Account:
    acc = (
        db.query(Account)
        .filter(Account.type == AccountType.broker)
        .order_by(Account.created_at)
        .first()
    )
    if acc:
        if acc.name != name:
            logger.info("沿用既有券商账户 id=%s name=%s", acc.id, acc.name)
        return acc
    acc = Account(name=name, type=AccountType.broker, balance=Decimal("0"), currency="CNY")
    db.add(acc)
    db.flush()
    logger.info("创建投资账户 id=%s name=%s", acc.id, acc.name)
    return acc


def sync_invest_to_flowledger(db: Session, invest_url: str | None = None) -> dict[str, Any]:
    """用 invest 最新真实持仓覆盖 flowledger 投资账户与 holdings。"""
    portfolio = fetch_latest_real_portfolio(invest_url)
    account = ensure_invest_account(db)

    old_count = db.query(Holding).filter(Holding.account_id == account.id).count()
    db.query(Holding).filter(Holding.account_id == account.id).delete()

    created = 0
    holdings_mv = Decimal("0")
    for p in portfolio["positions"]:
        code = str(p["stock_code"]).strip()
        name = str(p["stock_name"]).strip()
        qty = _d(p["quantity"])
        cost = _d(p["cost_price"])
        price = _d(p["current_price"])
        if qty <= 0:
            continue
        h = Holding(
            symbol=code[:20],
            name=name[:100],
            type=_holding_type(code, p.get("category")),
            quantity=qty,
            cost_price=cost,
            current_price=price,
            account_id=account.id,
            target_pct=None,
        )
        db.add(h)
        created += 1
        holdings_mv += qty * price

    # 权威总资产来自快照；闲置现金 = total_asset - 持仓市值（与快照 cash 交叉校验）
    total_asset = portfolio["total_asset"]
    snap_cash = portfolio["cash"]
    implied_cash = total_asset - holdings_mv
    if abs(implied_cash - snap_cash) > Decimal("1"):
        logger.warning(
            "快照现金与推算现金不一致 snap_cash=%s implied=%s holdings_mv=%s total=%s",
            snap_cash,
            implied_cash,
            holdings_mv,
            total_asset,
        )

    before = account.balance
    account.balance = total_asset
    db.commit()
    db.refresh(account)

    result = {
        "ok": True,
        "snapshot_date": portfolio["snapshot_date"],
        "account_id": str(account.id),
        "account_name": account.name,
        "balance_before": str(before),
        "balance_after": str(account.balance),
        "total_asset": str(total_asset),
        "cash": str(snap_cash),
        "position_value": str(portfolio["position_value"]),
        "holdings_mv": str(holdings_mv),
        "daily_pnl": str(portfolio["daily_pnl"]),
        "removed_holdings": old_count,
        "created_holdings": created,
        "positions": [
            {
                "symbol": str(p["stock_code"]),
                "name": str(p["stock_name"]),
                "quantity": str(p["quantity"]),
                "cost_price": str(p["cost_price"]),
                "current_price": str(p["current_price"]),
                "market_value": str(p["market_value"]),
            }
            for p in portfolio["positions"]
        ],
    }
    logger.info(
        "投资同步完成 date=%s balance %s -> %s holdings %s -> %s cash=%s",
        portfolio["snapshot_date"],
        before,
        account.balance,
        old_count,
        created,
        snap_cash,
    )
    return result
