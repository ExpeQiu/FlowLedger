from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from models import Holding
from schemas import HoldingCreate, HoldingOut, HoldingUpdate, PortfolioSummary
from services.finance import get_portfolio_summary

router = APIRouter(prefix="/api/holdings", tags=["holdings"])


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


@router.get("", response_model=list[HoldingOut])
def list_holdings(db: Session = Depends(get_db)):
    return [_holding_out(h) for h in db.query(Holding).all()]


@router.get("/summary", response_model=PortfolioSummary)
def portfolio_summary(db: Session = Depends(get_db)):
    return get_portfolio_summary(db)


@router.post("", response_model=HoldingOut, status_code=201)
def create_holding(data: HoldingCreate, db: Session = Depends(get_db)):
    h = Holding(**data.model_dump())
    db.add(h)
    db.commit()
    db.refresh(h)
    return _holding_out(h)


@router.patch("/{holding_id}", response_model=HoldingOut)
def update_holding(holding_id: UUID, data: HoldingUpdate, db: Session = Depends(get_db)):
    h = db.query(Holding).filter(Holding.id == holding_id).first()
    if not h:
        raise HTTPException(404, "持仓不存在")
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(h, k, v)
    db.commit()
    db.refresh(h)
    return _holding_out(h)


@router.delete("/{holding_id}", status_code=204)
def delete_holding(holding_id: UUID, db: Session = Depends(get_db)):
    h = db.query(Holding).filter(Holding.id == holding_id).first()
    if not h:
        raise HTTPException(404, "持仓不存在")
    db.delete(h)
    db.commit()
