from datetime import date
from typing import Optional
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, joinedload

from database import get_db
from logging_config import logger
from models import Account, Category, Transaction, TxSource, TxType
from schemas import TransactionCreate, TransactionOut
from services.finance import apply_transaction_to_balance

router = APIRouter(prefix="/api/transactions", tags=["transactions"])


def _to_out(tx: Transaction) -> TransactionOut:
    return TransactionOut(
        id=tx.id,
        type=tx.type,
        amount=tx.amount,
        date=tx.date,
        account_id=tx.account_id,
        category_id=tx.category_id,
        merchant=tx.merchant,
        note=tx.note,
        source=tx.source,
        transfer_pair_id=tx.transfer_pair_id,
        created_at=tx.created_at,
        account_name=tx.account.name if tx.account else None,
        category_name=tx.category.name if tx.category else None,
    )


@router.get("", response_model=list[TransactionOut])
def list_transactions(
    db: Session = Depends(get_db),
    type: Optional[TxType] = None,
    category_id: Optional[UUID] = None,
    search: Optional[str] = None,
    limit: int = Query(50, le=200),
):
    q = db.query(Transaction).options(joinedload(Transaction.account), joinedload(Transaction.category))
    if type:
        q = q.filter(Transaction.type == type)
    if category_id:
        q = q.filter(Transaction.category_id == category_id)
    if search:
        q = q.filter(
            (Transaction.merchant.ilike(f"%{search}%")) | (Transaction.note.ilike(f"%{search}%"))
        )
    txs = q.order_by(Transaction.date.desc(), Transaction.created_at.desc()).limit(limit).all()
    return [_to_out(t) for t in txs]


@router.post("", response_model=TransactionOut, status_code=201)
def create_transaction(data: TransactionCreate, db: Session = Depends(get_db)):
    account = db.query(Account).filter(Account.id == data.account_id).first()
    if not account:
        raise HTTPException(404, "账户不存在")

    if data.type == TxType.transfer:
        if not data.to_account_id:
            raise HTTPException(400, "转账需要目标账户 to_account_id")
        to_account = db.query(Account).filter(Account.id == data.to_account_id).first()
        if not to_account:
            raise HTTPException(404, "目标账户不存在")
        pair_id = uuid4()
        out_tx = Transaction(
            type=TxType.transfer,
            amount=data.amount,
            date=data.date,
            account_id=data.account_id,
            note=data.note or "转出",
            source=data.source,
            transfer_pair_id=pair_id,
        )
        in_tx = Transaction(
            type=TxType.transfer,
            amount=data.amount,
            date=data.date,
            account_id=data.to_account_id,
            note=data.note or "转入",
            source=data.source,
            transfer_pair_id=pair_id,
        )
        db.add(out_tx)
        db.add(in_tx)
        apply_transaction_to_balance(db, data.account_id, TxType.expense, data.amount)
        apply_transaction_to_balance(db, data.to_account_id, TxType.income, data.amount)
        db.commit()
        db.refresh(out_tx)
        out_tx.account = account
        logger.info("创建转账 pair=%s amount=%s", pair_id, data.amount)
        return _to_out(out_tx)

    tx = Transaction(**data.model_dump(exclude={"to_account_id"}))
    db.add(tx)
    apply_transaction_to_balance(db, data.account_id, data.type, data.amount)
    db.commit()
    db.refresh(tx)
    tx.account = account
    if data.category_id:
        tx.category = db.query(Category).filter(Category.id == data.category_id).first()
    logger.info("创建流水 id=%s type=%s amount=%s", tx.id, tx.type, tx.amount)
    return _to_out(tx)


@router.delete("/{tx_id}", status_code=204)
def delete_transaction(tx_id: UUID, db: Session = Depends(get_db)):
    tx = db.query(Transaction).filter(Transaction.id == tx_id).first()
    if not tx:
        raise HTTPException(404, "流水不存在")
    reverse_type = TxType.income if tx.type == TxType.expense else TxType.expense
    if tx.type != TxType.transfer:
        apply_transaction_to_balance(db, tx.account_id, reverse_type, tx.amount)
    db.delete(tx)
    db.commit()
