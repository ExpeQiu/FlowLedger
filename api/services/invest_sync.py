"""从 invest 同步真实持仓到 flowledger。

权威源与 stock 看板一致（hermesbrain）：
- holdings_snapshots → 账户总资产 / 现金 / 持仓市值 / 日收益
- holdings_detail → 持仓明细
来源优先级：manual > pg-1615 > openclaw-launchd。
hermesbrain 不可用时回退 lcteam.position_snapshots + positions(account_type=real)。
"""

from __future__ import annotations

from calendar import monthrange
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from config import settings
from logging_config import logger
from models import Account, AccountType, Holding, HoldingType

# 与 stock/lib/queries/holdings.ts 同源排序
_SOURCE_RANK = """
CASE source
  WHEN 'manual' THEN 1
  WHEN 'pg-1615' THEN 2
  WHEN 'openclaw-launchd' THEN 3
  ELSE 4
END
"""

_LATEST_HERMES_SQL = f"""
WITH ranked AS (
  SELECT
    id,
    (snap_time AT TIME ZONE 'Asia/Shanghai')::date AS snapshot_date,
    snap_time, source, total_asset, cash,
    COALESCE(position_value, position_val) AS position_value,
    position_pct AS position_ratio,
    daily_pnl, daily_pnl_pct,
    ROW_NUMBER() OVER (
      PARTITION BY (snap_time AT TIME ZONE 'Asia/Shanghai')::date
      ORDER BY {_SOURCE_RANK}, id DESC
    ) AS rn
  FROM hermesbrain.holdings_snapshots
)
SELECT id, snapshot_date, snap_time, source, total_asset, cash,
       position_value, position_ratio, daily_pnl, daily_pnl_pct
FROM ranked
WHERE rn = 1
ORDER BY snapshot_date DESC, id DESC
LIMIT 1
"""

_HERMES_DETAIL_SQL = """
SELECT code AS stock_code, name AS stock_name, quantity,
       cost_basis, latest_price, market_value, profit_loss, profit_loss_pct
FROM hermesbrain.holdings_detail
WHERE snapshot_id = :sid
ORDER BY market_value DESC NULLS LAST
"""

_MONTHLY_HERMES_SQL = f"""
WITH ranked AS (
  SELECT
    (snap_time AT TIME ZONE 'Asia/Shanghai')::date AS snapshot_date,
    daily_pnl, daily_pnl_pct, total_asset,
    ROW_NUMBER() OVER (
      PARTITION BY (snap_time AT TIME ZONE 'Asia/Shanghai')::date
      ORDER BY {_SOURCE_RANK}, id DESC
    ) AS rn
  FROM hermesbrain.holdings_snapshots
  WHERE (snap_time AT TIME ZONE 'Asia/Shanghai')::date >= :start
    AND (snap_time AT TIME ZONE 'Asia/Shanghai')::date <= :end
    AND is_reused = false
)
SELECT snapshot_date, daily_pnl, daily_pnl_pct, total_asset
FROM ranked
WHERE rn = 1
ORDER BY snapshot_date ASC
"""


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


def _unit_cost(cost_basis: Any, quantity: Decimal, latest_price: Decimal) -> Decimal:
    """hermesbrain.cost_basis 现为单价；若明显是总成本则折成单价。"""
    cost = _d(cost_basis)
    if quantity <= 0:
        return cost
    if latest_price > 0 and cost > latest_price * Decimal("20"):
        return cost / quantity
    return cost


def _invest_engine(invest_url: str | None = None) -> Engine:
    return create_engine(invest_url or settings.invest_database_url, pool_pre_ping=True)


def _normalize_hermes_positions(rows: list[Any]) -> list[dict[str, Any]]:
    positions: list[dict[str, Any]] = []
    for r in rows:
        row = dict(r)
        qty = _d(row.get("quantity"))
        price = _d(row.get("latest_price"))
        mv = _d(row.get("market_value"))
        if price <= 0 and qty > 0 and mv > 0:
            price = mv / qty
        code = str(row.get("stock_code") or "").strip()
        name = str(row.get("stock_name") or code).strip()
        positions.append(
            {
                "stock_code": code,
                "stock_name": name,
                "quantity": qty,
                "cost_price": _unit_cost(row.get("cost_basis"), qty, price),
                "current_price": price,
                "market_value": mv,
                "profit_loss": _d(row.get("profit_loss")),
                "profit_loss_pct": _d(row.get("profit_loss_pct")),
                "category": None,
            }
        )
    return positions


def _fetch_latest_hermes(engine: Engine) -> dict[str, Any] | None:
    with engine.connect() as conn:
        snap = conn.execute(text(_LATEST_HERMES_SQL)).mappings().first()
        if not snap:
            return None
        rows = conn.execute(text(_HERMES_DETAIL_SQL), {"sid": snap["id"]}).mappings().all()
    positions = _normalize_hermes_positions(rows)
    snap_date = snap["snapshot_date"]
    logger.info(
        "拉取 hermesbrain 持仓 id=%s source=%s snapshot=%s total_asset=%s cash=%s position_value=%s count=%s",
        snap["id"],
        snap["source"],
        snap_date,
        snap["total_asset"],
        snap["cash"],
        snap["position_value"],
        len(positions),
    )
    return {
        "snapshot_date": str(snap_date),
        "snapshot_id": int(snap["id"]),
        "source": str(snap["source"] or ""),
        "schema": "hermesbrain",
        "total_asset": _d(snap["total_asset"]),
        "cash": _d(snap["cash"]),
        "position_value": _d(snap["position_value"]),
        "position_ratio": _d(snap["position_ratio"]),
        "daily_pnl": _d(snap["daily_pnl"]),
        "daily_pnl_pct": _d(snap["daily_pnl_pct"]),
        "positions": positions,
    }


def _fetch_latest_lcteam(engine: Engine) -> dict[str, Any]:
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
        "回退 lcteam 持仓 snapshot=%s total_asset=%s cash=%s position_value=%s count=%s",
        snap_date,
        snap["total_asset"],
        snap["cash"],
        snap["position_value"],
        len(positions),
    )
    return {
        "snapshot_date": str(snap_date),
        "snapshot_id": None,
        "source": "lcteam",
        "schema": "lcteam",
        "total_asset": _d(snap["total_asset"]),
        "cash": _d(snap["cash"]),
        "position_value": _d(snap["position_value"]),
        "position_ratio": _d(snap["position_ratio"]),
        "daily_pnl": _d(snap["daily_pnl"]),
        "daily_pnl_pct": _d(snap["daily_pnl_pct"]),
        "positions": positions,
    }


def fetch_latest_real_portfolio(invest_url: str | None = None) -> dict[str, Any]:
    engine = _invest_engine(invest_url)
    try:
        try:
            portfolio = _fetch_latest_hermes(engine)
        except Exception as e:
            logger.warning("hermesbrain 持仓读取失败，回退 lcteam: %s", e)
            portfolio = None
        if portfolio:
            return portfolio
        logger.warning("hermesbrain.holdings_snapshots 无数据，回退 lcteam")
        return _fetch_latest_lcteam(engine)
    finally:
        engine.dispose()


def _month_bounds(month: str) -> tuple[date, date]:
    """解析 YYYY-MM，返回当月起止日期。"""
    try:
        y, m = month.split("-")
        year, mon = int(y), int(m)
        if mon < 1 or mon > 12:
            raise ValueError
        start = date(year, mon, 1)
        last = monthrange(year, mon)[1]
        end = date(year, mon, last)
        return start, end
    except Exception as e:
        raise ValueError(f"无效月份格式: {month}，期望 YYYY-MM") from e


_TRADING_DAY_CACHE: dict[str, set[date]] = {}


def _trading_days(start: date, end: date) -> set[date]:
    """获取 [start, end] 区间内的 A 股交易日集合（AKShare 交易日历，缓存到内存）。"""
    key = f"{start.year:04d}-{start.month:02d}"
    if key in _TRADING_DAY_CACHE:
        cached = _TRADING_DAY_CACHE[key]
        return {d for d in cached if start <= d <= end}
    try:
        import akshare as ak  # type: ignore
        df = ak.tool_trade_date_hist_sina()
        days: set[date] = set()
        for _, row in df.iterrows():
            td = row["trade_date"]
            days.add(td if hasattr(td, "year") else date.fromisoformat(str(td)))
        _TRADING_DAY_CACHE[key] = days
        logger.info("交易日历缓存 key=%s days=%s", key, len(days))
        return {d for d in days if start <= d <= end}
    except Exception as e:
        logger.warning("AKShare 交易日历获取失败，回退到全量包含: %s", e)
        return {start + timedelta(days=_) for _ in range((end - start).days + 1)}


def _monthly_from_rows(month: str, rows: list[Any]) -> dict[str, Any]:
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


def fetch_monthly_daily_pnl(month: str | None = None, invest_url: str | None = None) -> dict[str, Any]:
    """指定月每日收益。优先 hermesbrain 快照（与 stock 同源优先级），否则 lcteam。"""
    if not month:
        today = date.today()
        month = f"{today.year:04d}-{today.month:02d}"
    start, end = _month_bounds(month)
    trading_days = _trading_days(start, end)
    engine = _invest_engine(invest_url)
    try:
        try:
            with engine.connect() as conn:
                rows = conn.execute(
                    text(_MONTHLY_HERMES_SQL), {"start": start, "end": end}
                ).mappings().all()
            if rows:
                logger.info("月度每日收益源=hermesbrain month=%s", month)
                rows = [r for r in rows if r["snapshot_date"] in trading_days]
                return _monthly_from_rows(month, rows)
            logger.warning("hermesbrain 本月无快照 month=%s，回退 lcteam", month)
        except Exception as e:
            logger.warning("hermesbrain 月度收益读取失败，回退 lcteam: %s", e)

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
        rows = [r for r in rows if r["snapshot_date"] in trading_days]
        return _monthly_from_rows(month, rows)
    finally:
        engine.dispose()


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

    total_asset = portfolio["total_asset"]
    snap_cash = portfolio["cash"]
    implied_cash = total_asset - holdings_mv
    if abs(implied_cash - snap_cash) > Decimal("1"):
        logger.warning(
            "快照现金与推算现金不一致 snap_cash=%s implied=%s holdings_mv=%s total=%s source=%s",
            snap_cash,
            implied_cash,
            holdings_mv,
            total_asset,
            portfolio.get("source"),
        )

    before = account.balance
    account.balance = total_asset
    db.commit()
    db.refresh(account)

    result = {
        "ok": True,
        "snapshot_date": portfolio["snapshot_date"],
        "snapshot_id": portfolio.get("snapshot_id"),
        "source": portfolio.get("source"),
        "schema": portfolio.get("schema"),
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
        "投资同步完成 schema=%s source=%s date=%s balance %s -> %s holdings %s -> %s cash=%s",
        portfolio.get("schema"),
        portfolio.get("source"),
        portfolio["snapshot_date"],
        before,
        account.balance,
        old_count,
        created,
        snap_cash,
    )
    return result
