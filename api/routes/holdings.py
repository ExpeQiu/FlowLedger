from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from logging_config import logger
from models import Account, AccountType, Holding
from schemas import (
    HoldingCreate,
    HoldingOut,
    HoldingUpdate,
    InvestValidationOut,
    MonthlyDailyPnlOut,
    PortfolioSummary,
)
from services.finance import (
    adjust_invest_balance_by_mv_delta,
    get_portfolio_summary,
    validate_invest_accounts,
)
from services.invest_sync import fetch_monthly_daily_pnl, sync_invest_to_flowledger

router = APIRouter(prefix="/api/holdings", tags=["holdings"])

INVEST_TYPES = {AccountType.broker, AccountType.fund}


def _holding_out(h: Holding) -> HoldingOut:
    mv = h.quantity * h.current_price
    profit_pct = float((h.current_price - h.cost_price) / h.cost_price * 100) if h.cost_price else 0
    return HoldingOut(
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


def _mv(quantity: Decimal, price: Decimal) -> Decimal:
    return Decimal(str(quantity)) * Decimal(str(price))


@router.get("", response_model=list[HoldingOut])
def list_holdings(db: Session = Depends(get_db)):
    return [_holding_out(h) for h in db.query(Holding).all()]


@router.get("/summary", response_model=PortfolioSummary)
def portfolio_summary(db: Session = Depends(get_db)):
    return get_portfolio_summary(db)


@router.get("/daily-pnl", response_model=MonthlyDailyPnlOut)
def monthly_daily_pnl(month: str | None = None):
    """本月（或指定月）每日收益波动，数据来自 invest.hermesbrain.holdings_snapshots。"""
    try:
        return fetch_monthly_daily_pnl(month)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    except Exception as e:
        logger.exception("拉取月度每日收益失败 month=%s: %s", month, e)
        raise HTTPException(500, f"拉取月度每日收益失败: {e}") from e


@router.get("/validate", response_model=InvestValidationOut)
def validate_holdings(db: Session = Depends(get_db)):
    result = validate_invest_accounts(db)
    logger.info("投资账户校验接口 ok=%s accounts=%s", result.ok, len(result.accounts))
    return result


@router.post("/sync-from-invest")
def sync_from_invest(db: Session = Depends(get_db)):
    """从 invest.hermesbrain 同步真实持仓与账户总资产（与 stock 看板同源）。"""
    try:
        result = sync_invest_to_flowledger(db)
    except Exception as e:
        logger.exception("投资同步失败: %s", e)
        raise HTTPException(500, f"投资同步失败: {e}") from e
    validation = validate_invest_accounts(db)
    result["validation_ok"] = validation.ok
    result["validation"] = validation.model_dump(mode="json")
    return result


@router.post("", response_model=HoldingOut, status_code=201)
def create_holding(data: HoldingCreate, db: Session = Depends(get_db)):
    account = db.query(Account).filter(Account.id == data.account_id).first()
    if not account:
        raise HTTPException(404, "账户不存在")
    if account.type not in INVEST_TYPES:
        raise HTTPException(400, "持仓只能挂在券商/基金等投资账户上")
    h = Holding(**data.model_dump())
    db.add(h)
    db.flush()
    adjust_invest_balance_by_mv_delta(db, h.account_id, _mv(h.quantity, h.current_price))
    db.commit()
    db.refresh(h)
    logger.info("创建持仓 id=%s symbol=%s account=%s mv=%s", h.id, h.symbol, account.name, _mv(h.quantity, h.current_price))
    return _holding_out(h)


@router.patch("/{holding_id}", response_model=HoldingOut)
def update_holding(holding_id: UUID, data: HoldingUpdate, db: Session = Depends(get_db)):
    h = db.query(Holding).filter(Holding.id == holding_id).first()
    if not h:
        raise HTTPException(404, "持仓不存在")
    old_mv = _mv(h.quantity, h.current_price)
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(h, k, v)
    new_mv = _mv(h.quantity, h.current_price)
    adjust_invest_balance_by_mv_delta(db, h.account_id, new_mv - old_mv)
    db.commit()
    db.refresh(h)
    logger.info("更新持仓 id=%s symbol=%s mv %s -> %s", h.id, h.symbol, old_mv, new_mv)
    return _holding_out(h)


@router.delete("/{holding_id}", status_code=204)
def delete_holding(holding_id: UUID, db: Session = Depends(get_db)):
    h = db.query(Holding).filter(Holding.id == holding_id).first()
    if not h:
        raise HTTPException(404, "持仓不存在")
    mv = _mv(h.quantity, h.current_price)
    account_id = h.account_id
    db.delete(h)
    adjust_invest_balance_by_mv_delta(db, account_id, -mv)
    db.commit()
    logger.info("删除持仓 id=%s mv=%s", holding_id, mv)
