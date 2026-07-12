from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from database import get_db
from models import Budget, Category, Transaction, TxType
from schemas import BudgetCreate, BudgetOut
from services.finance import _month_range

router = APIRouter(prefix="/api/budgets", tags=["budgets"])


def _budget_out(b: Budget, db: Session) -> BudgetOut:
    start, end = _month_range(b.period)
    spent = (
        db.query(func.coalesce(func.sum(Transaction.amount), 0))
        .filter(
            Transaction.category_id == b.category_id,
            Transaction.type == TxType.expense,
            Transaction.date >= start,
            Transaction.date <= end,
        )
        .scalar()
        or 0
    )
    usage = float(spent / b.amount * 100) if b.amount else 0
    return BudgetOut(
        id=b.id,
        category_id=b.category_id,
        period=b.period,
        amount=b.amount,
        alert_threshold=b.alert_threshold,
        category_name=b.category.name if b.category else None,
        spent=spent,
        usage_pct=round(usage, 1),
    )


@router.get("", response_model=list[BudgetOut])
def list_budgets(period: str | None = None, db: Session = Depends(get_db)):
    q = db.query(Budget).options(joinedload(Budget.category))
    if period:
        q = q.filter(Budget.period == period)
    budgets = q.order_by(Budget.period.desc()).all()
    return [_budget_out(b, db) for b in budgets]


@router.get("/status", response_model=list[BudgetOut])
def budget_status(month: str, db: Session = Depends(get_db)):
    return list_budgets(period=month, db=db)


@router.post("", response_model=BudgetOut, status_code=201)
def create_budget(data: BudgetCreate, db: Session = Depends(get_db)):
    cat = db.query(Category).filter(Category.id == data.category_id).first()
    if not cat:
        raise HTTPException(404, "分类不存在")
    budget = Budget(**data.model_dump())
    db.add(budget)
    db.commit()
    db.refresh(budget)
    budget.category = cat
    return _budget_out(budget, db)


@router.delete("/{budget_id}", status_code=204)
def delete_budget(budget_id: UUID, db: Session = Depends(get_db)):
    b = db.query(Budget).filter(Budget.id == budget_id).first()
    if not b:
        raise HTTPException(404, "预算不存在")
    db.delete(b)
    db.commit()
