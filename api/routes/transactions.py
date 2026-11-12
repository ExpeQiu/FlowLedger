from collections import defaultdict
from datetime import date, datetime, time
from typing import Optional
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, joinedload

from database import get_db
from logging_config import logger
from models import Account, Category, Transaction, TxSource, TxType
from schemas import TransactionCreate, TransactionOut, TransferOut
from services.finance import (
    TRANSFER_IN_MARK,
    TRANSFER_OUT_MARK,
    apply_transaction_to_balance,
)

router = APIRouter(prefix="/api/transactions", tags=["transactions"])
# 历史数据常把账户间划拨记成 expense+income，备注含这些关键词时参与识别
_LEGACY_TRANSFER_HINTS = ("转账", "转出", "转入")


def _to_out(tx: Transaction) -> TransactionOut:
    # 历史数据可能缺少 source/created_at（列可空），序列化前兜底，避免开支页整表 500
    source = tx.source or TxSource.manual
    created_at = tx.created_at
    if created_at is None:
        created_at = datetime.combine(tx.date, time.min) if tx.date else datetime.utcnow()
        logger.warning(
            "流水缺 created_at，已用业务日期兜底 id=%s date=%s",
            tx.id,
            tx.date,
        )
    if tx.source is None:
        logger.warning("流水缺 source，已按 manual 输出 id=%s", tx.id)
    return TransactionOut(
        id=tx.id,
        type=tx.type,
        amount=tx.amount,
        date=tx.date,
        account_id=tx.account_id,
        category_id=tx.category_id,
        merchant=tx.merchant,
        note=tx.note,
        source=source,
        transfer_pair_id=tx.transfer_pair_id,
        created_at=created_at,
        account_name=tx.account.name if tx.account else None,
        category_name=tx.category.name if tx.category else None,
    )


def _transfer_user_note(note: str | None) -> str | None:
    """去掉转出/转入前缀，还原用户备注。"""
    if not note:
        return None
    text = note.strip()
    for prefix in ("转出 · ", "转入 · ", "转出", "转入"):
        if text.startswith(prefix):
            rest = text[len(prefix):].strip(" ·")
            return rest or None
    return text


def _split_transfer_legs(legs: list[Transaction]) -> tuple[Transaction, Transaction]:
    """从配对流水中识别转出/转入腿。"""
    by_mark = {t.merchant: t for t in legs if t.merchant in (TRANSFER_OUT_MARK, TRANSFER_IN_MARK)}
    if TRANSFER_OUT_MARK in by_mark and TRANSFER_IN_MARK in by_mark:
        return by_mark[TRANSFER_OUT_MARK], by_mark[TRANSFER_IN_MARK]

    out_legs = [t for t in legs if (t.note or "").startswith("转出")]
    in_legs = [t for t in legs if (t.note or "").startswith("转入")]
    if len(out_legs) == 1 and len(in_legs) == 1:
        return out_legs[0], in_legs[0]

    # 历史数据：按创建时间 / id 兜底（创建时先写出再写入）
    ordered = sorted(legs, key=lambda t: (t.created_at or datetime.min, str(t.id)))
    logger.warning(
        "转账方向无法从 merchant/note 判定，按创建顺序兜底 pair=%s",
        legs[0].transfer_pair_id,
    )
    return ordered[0], ordered[1]


def _looks_like_transfer_note(note: str | None) -> bool:
    if not note:
        return False
    text = note.strip()
    return any(hint in text for hint in _LEGACY_TRANSFER_HINTS)


def _infer_legacy_transfer_pairs(db: Session) -> list[tuple[Transaction, Transaction]]:
    """识别「同日同额同备注」的 expense+income 历史划拨。"""
    txs = (
        db.query(Transaction)
        .options(joinedload(Transaction.account))
        .filter(
            Transaction.type.in_([TxType.expense, TxType.income]),
            Transaction.transfer_pair_id.is_(None),
        )
        .all()
    )
    candidates = [t for t in txs if _looks_like_transfer_note(t.note)]
    groups: dict[tuple, list[Transaction]] = defaultdict(list)
    for t in candidates:
        groups[(t.date, t.amount, (t.note or "").strip())].append(t)

    pairs: list[tuple[Transaction, Transaction]] = []
    for legs in groups.values():
        outs = sorted(
            [t for t in legs if t.type == TxType.expense],
            key=lambda t: (t.created_at or datetime.min, str(t.id)),
        )
        inns = sorted(
            [t for t in legs if t.type == TxType.income],
            key=lambda t: (t.created_at or datetime.min, str(t.id)),
        )
        used_in: set[UUID] = set()
        for out_tx in outs:
            for in_tx in inns:
                if in_tx.id in used_in or in_tx.account_id == out_tx.account_id:
                    continue
                pairs.append((out_tx, in_tx))
                used_in.add(in_tx.id)
                break
    return pairs


def _normalize_legacy_transfers(db: Session) -> int:
    """把历史 expense/income 划拨落成正式 transfer 配对（不改余额，仅改类型与标记）。"""
    pairs = _infer_legacy_transfer_pairs(db)
    if not pairs:
        return 0
    for out_tx, in_tx in pairs:
        pair_id = uuid4()
        user_note = ((out_tx.note or in_tx.note or "").strip())
        out_tx.type = TxType.transfer
        in_tx.type = TxType.transfer
        out_tx.transfer_pair_id = pair_id
        in_tx.transfer_pair_id = pair_id
        out_tx.merchant = TRANSFER_OUT_MARK
        in_tx.merchant = TRANSFER_IN_MARK
        out_tx.note = f"转出 · {user_note}" if user_note else "转出"
        in_tx.note = f"转入 · {user_note}" if user_note else "转入"
        logger.info(
            "规范化历史转账 pair=%s amount=%s from=%s to=%s note=%s",
            pair_id,
            out_tx.amount,
            out_tx.account.name if out_tx.account else out_tx.account_id,
            in_tx.account.name if in_tx.account else in_tx.account_id,
            user_note,
        )
    db.commit()
    logger.info("历史转账规范化完成 pairs=%s", len(pairs))
    return len(pairs)


def _transfer_out_from_legs(out_tx: Transaction, in_tx: Transaction, pair_id: UUID) -> TransferOut:
    created_at = out_tx.created_at or in_tx.created_at
    if created_at is None:
        created_at = datetime.combine(out_tx.date, time.min) if out_tx.date else datetime.utcnow()
    return TransferOut(
        transfer_pair_id=pair_id,
        date=out_tx.date,
        amount=out_tx.amount,
        from_account_id=out_tx.account_id,
        from_account_name=out_tx.account.name if out_tx.account else "未知账户",
        to_account_id=in_tx.account_id,
        to_account_name=in_tx.account.name if in_tx.account else "未知账户",
        note=_transfer_user_note(out_tx.note) or _transfer_user_note(in_tx.note),
        source=out_tx.source or in_tx.source or TxSource.manual,
        created_at=created_at,
        out_tx_id=out_tx.id,
        in_tx_id=in_tx.id,
    )


@router.get("", response_model=list[TransactionOut])
def list_transactions(
    db: Session = Depends(get_db),
    type: Optional[TxType] = None,
    category_id: Optional[UUID] = None,
    account_id: Optional[UUID] = None,
    search: Optional[str] = None,
    start: Optional[date] = None,
    end: Optional[date] = None,
    limit: int = Query(50, le=200),
):
    # 先把历史 expense+income 划拨归一为 transfer，避免开支页误展示
    migrated = _normalize_legacy_transfers(db)
    if migrated:
        logger.info("list_transactions 已迁移历史划拨 pairs=%s", migrated)

    q = db.query(Transaction).options(joinedload(Transaction.account), joinedload(Transaction.category))
    if type:
        q = q.filter(Transaction.type == type)
    else:
        # 开支页「全部」只含收支；转账仅走 /transfers（账户页）
        q = q.filter(Transaction.type != TxType.transfer)
    if category_id:
        q = q.filter(Transaction.category_id == category_id)
    if account_id:
        q = q.filter(Transaction.account_id == account_id)
    if search:
        q = q.filter(
            (Transaction.merchant.ilike(f"%{search}%")) | (Transaction.note.ilike(f"%{search}%"))
        )
    if start:
        q = q.filter(Transaction.date >= start)
    if end:
        q = q.filter(Transaction.date <= end)
    txs = q.order_by(Transaction.date.desc(), Transaction.created_at.desc()).limit(limit).all()
    logger.info(
        "查询流水 count=%s type=%s account_id=%s exclude_transfer=%s",
        len(txs),
        type.value if type else "all_non_transfer",
        account_id,
        type is None,
    )
    return [_to_out(t) for t in txs]


@router.get("/transfers", response_model=list[TransferOut])
def list_transfers(
    db: Session = Depends(get_db),
    account_id: Optional[UUID] = None,
    limit: int = Query(50, le=200),
):
    """返回配对后的转账明细（一笔一行：转出账户 → 转入账户）。

    会先把历史 expense+income 划拨规范化为 transfer，再统一返回。
    """
    migrated = _normalize_legacy_transfers(db)
    if migrated:
        logger.info("list_transfers 已迁移历史划拨 pairs=%s", migrated)

    q = (
        db.query(Transaction)
        .options(joinedload(Transaction.account))
        .filter(Transaction.type == TxType.transfer, Transaction.transfer_pair_id.isnot(None))
    )
    if account_id:
        # 先找出涉及该账户的 pair，再取完整双腿
        pair_ids = [
            row[0]
            for row in db.query(Transaction.transfer_pair_id)
            .filter(
                Transaction.type == TxType.transfer,
                Transaction.account_id == account_id,
                Transaction.transfer_pair_id.isnot(None),
            )
            .distinct()
            .all()
        ]
        if not pair_ids:
            logger.info("转账列表为空 account_id=%s", account_id)
            return []
        q = q.filter(Transaction.transfer_pair_id.in_(pair_ids))

    txs = q.order_by(Transaction.date.desc(), Transaction.created_at.desc()).all()
    pairs: dict[UUID, list[Transaction]] = {}
    for tx in txs:
        pairs.setdefault(tx.transfer_pair_id, []).append(tx)

    results: list[TransferOut] = []
    for pair_id, legs in pairs.items():
        if len(legs) < 2:
            logger.warning("转账配对不完整 pair=%s legs=%s", pair_id, len(legs))
            continue
        if len(legs) > 2:
            logger.warning("转账配对异常多腿 pair=%s legs=%s，仅取前两腿", pair_id, len(legs))
            legs = sorted(legs, key=lambda t: (t.created_at or datetime.min, str(t.id)))[:2]
        out_tx, in_tx = _split_transfer_legs(legs)
        results.append(_transfer_out_from_legs(out_tx, in_tx, pair_id))

    results.sort(key=lambda r: (r.date, r.created_at), reverse=True)
    results = results[:limit]
    logger.info("查询转账记录 count=%s account_id=%s", len(results), account_id)
    return results


@router.post("", response_model=TransactionOut, status_code=201)
def create_transaction(data: TransactionCreate, db: Session = Depends(get_db)):
    account = db.query(Account).filter(Account.id == data.account_id).first()
    if not account:
        raise HTTPException(404, "账户不存在")

    if data.type == TxType.transfer:
        if not data.to_account_id:
            raise HTTPException(400, "转账需要目标账户 to_account_id")
        if data.to_account_id == data.account_id:
            raise HTTPException(400, "转出与转入账户不能相同")
        to_account = db.query(Account).filter(Account.id == data.to_account_id).first()
        if not to_account:
            raise HTTPException(404, "目标账户不存在")
        pair_id = uuid4()
        user_note = (data.note or "").strip()
        out_note = f"转出 · {user_note}" if user_note else "转出"
        in_note = f"转入 · {user_note}" if user_note else "转入"
        out_tx = Transaction(
            type=TxType.transfer,
            amount=data.amount,
            date=data.date,
            account_id=data.account_id,
            note=out_note,
            merchant=TRANSFER_OUT_MARK,
            source=data.source,
            transfer_pair_id=pair_id,
        )
        in_tx = Transaction(
            type=TxType.transfer,
            amount=data.amount,
            date=data.date,
            account_id=data.to_account_id,
            note=in_note,
            merchant=TRANSFER_IN_MARK,
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
        logger.info(
            "创建转账 pair=%s amount=%s from=%s to=%s",
            pair_id,
            data.amount,
            account.name,
            to_account.name,
        )
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
