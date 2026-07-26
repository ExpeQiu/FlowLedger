from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from logging_config import logger
from models import Account, Holding
from schemas import AccountCreate, AccountOut, AccountUpdate
from services.finance import compute_net_worth, enrich_account_out

router = APIRouter(prefix="/api/accounts", tags=["accounts"])


@router.get("", response_model=list[AccountOut])
def list_accounts(db: Session = Depends(get_db)):
    accounts = db.query(Account).order_by(Account.created_at).all()
    return [enrich_account_out(db, a) for a in accounts]


@router.get("/net-worth")
def accounts_net_worth(db: Session = Depends(get_db)):
    """与 Dashboard 同一口径的净资产，供账户页对齐。"""
    value = compute_net_worth(db)
    return {"net_worth": value}


@router.post("", response_model=AccountOut, status_code=201)
def create_account(data: AccountCreate, db: Session = Depends(get_db)):
    account = Account(**data.model_dump())
    db.add(account)
    db.commit()
    db.refresh(account)
    logger.info("创建账户 id=%s name=%s type=%s", account.id, account.name, account.type.value)
    return enrich_account_out(db, account)


@router.get("/{account_id}", response_model=AccountOut)
def get_account(account_id: UUID, db: Session = Depends(get_db)):
    account = db.query(Account).filter(Account.id == account_id).first()
    if not account:
        raise HTTPException(404, "账户不存在")
    return enrich_account_out(db, account)


@router.patch("/{account_id}", response_model=AccountOut)
def update_account(account_id: UUID, data: AccountUpdate, db: Session = Depends(get_db)):
    account = db.query(Account).filter(Account.id == account_id).first()
    if not account:
        raise HTTPException(404, "账户不存在")
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(account, k, v)
    db.commit()
    db.refresh(account)
    logger.info("更新账户 id=%s name=%s balance=%s", account.id, account.name, account.balance)
    return enrich_account_out(db, account)


@router.delete("/{account_id}", status_code=204)
def delete_account(account_id: UUID, db: Session = Depends(get_db)):
    account = db.query(Account).filter(Account.id == account_id).first()
    if not account:
        raise HTTPException(404, "账户不存在")
    holding_count = db.query(Holding).filter(Holding.account_id == account_id).count()
    if holding_count:
        raise HTTPException(400, f"账户下仍有 {holding_count} 条持仓，请先删除持仓")
    db.delete(account)
    db.commit()
    logger.info("删除账户 id=%s name=%s", account_id, account.name)
