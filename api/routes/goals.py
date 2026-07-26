from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload

from database import get_db
from logging_config import logger
from models import Category, Goal, RecurringBill, Rule
from schemas import (
    GoalCreate,
    GoalOut,
    GoalUpdate,
    RecurringBillCreate,
    RecurringBillOut,
    RuleCreate,
    RuleOut,
)

router = APIRouter(prefix="/api/goals", tags=["goals"])


@router.get("", response_model=list[GoalOut])
def list_goals(db: Session = Depends(get_db)):
    goals = db.query(Goal).all()
    result = []
    for g in goals:
        pct = float(g.current_amount / g.target_amount * 100) if g.target_amount else 0
        result.append(
            GoalOut(
                id=g.id,
                name=g.name,
                target_amount=g.target_amount,
                current_amount=g.current_amount,
                deadline=g.deadline,
                note=g.note,
                progress_pct=round(pct, 1),
            )
        )
    return result


@router.post("", response_model=GoalOut, status_code=201)
def create_goal(data: GoalCreate, db: Session = Depends(get_db)):
    g = Goal(**data.model_dump())
    db.add(g)
    db.commit()
    db.refresh(g)
    pct = float(g.current_amount / g.target_amount * 100) if g.target_amount else 0
    return GoalOut(**{**g.__dict__, "progress_pct": round(pct, 1)})


@router.patch("/{goal_id}", response_model=GoalOut)
def update_goal(goal_id: UUID, data: GoalUpdate, db: Session = Depends(get_db)):
    g = db.query(Goal).filter(Goal.id == goal_id).first()
    if not g:
        raise HTTPException(404, "目标不存在")
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(g, k, v)
    db.commit()
    db.refresh(g)
    pct = float(g.current_amount / g.target_amount * 100) if g.target_amount else 0
    return GoalOut(
        id=g.id,
        name=g.name,
        target_amount=g.target_amount,
        current_amount=g.current_amount,
        deadline=g.deadline,
        note=g.note,
        progress_pct=round(pct, 1),
    )


bills_router = APIRouter(prefix="/api/recurring-bills", tags=["recurring-bills"])


@bills_router.get("", response_model=list[RecurringBillOut])
def list_bills(db: Session = Depends(get_db)):
    return db.query(RecurringBill).order_by(RecurringBill.next_due).all()


@bills_router.post("", response_model=RecurringBillOut, status_code=201)
def create_bill(data: RecurringBillCreate, db: Session = Depends(get_db)):
    b = RecurringBill(**data.model_dump())
    db.add(b)
    db.commit()
    db.refresh(b)
    return b


@bills_router.post("/materialize")
def materialize_bills(
    month: Optional[str] = None,
    adjust_balance: bool = False,
    db: Session = Depends(get_db),
):
    """将指定月份定期账单落成支出流水（默认不改账户余额）。"""
    from datetime import date as _date

    from services.finance import materialize_recurring_for_month

    target = month or _date.today().strftime("%Y-%m")
    logger.info("API 落账定期账单 month=%s adjust_balance=%s", target, adjust_balance)
    return materialize_recurring_for_month(db, target, adjust_balance=adjust_balance)


rules_router = APIRouter(prefix="/api/rules", tags=["rules"])


@rules_router.get("", response_model=list[RuleOut])
def list_rules(db: Session = Depends(get_db)):
    rules = db.query(Rule).options(joinedload(Rule.category)).order_by(Rule.priority.desc()).all()
    return [
        RuleOut(
            id=r.id,
            pattern=r.pattern,
            category_id=r.category_id,
            priority=r.priority,
            is_active=r.is_active,
            category_name=r.category.name if hasattr(r, "category") and r.category else None,
        )
        for r in rules
    ]


@rules_router.post("", response_model=RuleOut, status_code=201)
def create_rule(data: RuleCreate, db: Session = Depends(get_db)):
    cat = db.query(Category).filter(Category.id == data.category_id).first()
    if not cat:
        raise HTTPException(404, "分类不存在")
    r = Rule(**data.model_dump())
    db.add(r)
    db.commit()
    db.refresh(r)
    return RuleOut(
        id=r.id,
        pattern=r.pattern,
        category_id=r.category_id,
        priority=r.priority,
        is_active=r.is_active,
        category_name=cat.name,
    )
