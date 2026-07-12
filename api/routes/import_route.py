import csv
import io
from datetime import datetime
from decimal import Decimal, InvalidOperation
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from database import get_db
from logging_config import logger
from models import Account, Category, ImportJob, ImportStatus, Rule, Transaction, TxSource, TxType
from schemas import ImportPreviewOut, ImportPreviewRow, ImportResultOut
from services.finance import compute_import_hash

router = APIRouter(prefix="/api/import", tags=["import"])

ALIPAY_HEADERS = {"交易时间", "交易对方", "金额", "收/支", "商品说明"}
WECHAT_HEADERS = {"交易时间", "交易类型", "交易对方", "金额(元)", "支付方式"}


def _parse_amount(val: str) -> Decimal:
    val = val.replace("¥", "").replace(",", "").strip()
    return Decimal(val)


def _match_category(db: Session, merchant: str) -> str | None:
    rules = db.query(Rule).filter(Rule.is_active == True).order_by(Rule.priority.desc()).all()
    for rule in rules:
        if rule.pattern.lower() in (merchant or "").lower():
            cat = db.query(Category).filter(Category.id == rule.category_id).first()
            return cat.name if cat else None
    return None


def _parse_csv_content(content: str, source: str) -> list[dict]:
    reader = csv.DictReader(io.StringIO(content))
    rows = []
    headers = set(reader.fieldnames or [])

    for row in reader:
        try:
            if source == "alipay" or ALIPAY_HEADERS.issubset(headers):
                tx_date = datetime.strptime(row.get("交易时间", "")[:10], "%Y-%m-%d").date()
                merchant = row.get("交易对方", "")
                amount = _parse_amount(row.get("金额", "0"))
                direction = row.get("收/支", "")
                note = row.get("商品说明", "")
                if "支" in direction:
                    amount = abs(amount)
                else:
                    amount = -abs(amount)
                rows.append({"date": tx_date, "amount": abs(amount), "merchant": merchant, "note": note, "is_expense": "支" in direction})
            elif source == "wechat" or "金额(元)" in headers:
                tx_date = datetime.strptime(row.get("交易时间", "")[:10], "%Y-%m-%d").date()
                merchant = row.get("交易对方", "")
                amount = _parse_amount(row.get("金额(元)", row.get("金额", "0")))
                tx_type = row.get("交易类型", "")
                note = row.get("商品", row.get("商品说明", ""))
                is_expense = "支出" in tx_type or amount > 0
                rows.append({"date": tx_date, "amount": abs(amount), "merchant": merchant, "note": note, "is_expense": is_expense})
            else:
                date_key = next((k for k in row if "date" in k.lower() or "日期" in k or "时间" in k), None)
                amount_key = next((k for k in row if "amount" in k.lower() or "金额" in k), None)
                merchant_key = next((k for k in row if "merchant" in k.lower() or "对方" in k or "商户" in k), None)
                if not date_key or not amount_key:
                    continue
                tx_date = datetime.strptime(row[date_key][:10].replace("/", "-"), "%Y-%m-%d").date()
                amount = _parse_amount(row[amount_key])
                merchant = row.get(merchant_key, "") if merchant_key else ""
                rows.append({"date": tx_date, "amount": abs(amount), "merchant": merchant, "note": "", "is_expense": True})
        except (ValueError, InvalidOperation, KeyError) as e:
            logger.warning("跳过无效行: %s", e)
            continue
    return rows


@router.post("/preview", response_model=ImportPreviewOut)
async def preview_import(
    file: UploadFile = File(...),
    source: str = Form("csv"),
    account_id: str = Form(...),
    db: Session = Depends(get_db),
):
    content = (await file.read()).decode("utf-8-sig")
    parsed = _parse_csv_content(content, source)
    aid = UUID(account_id)
    preview_rows = []
    dup_count = 0

    for row in parsed:
        ih = compute_import_hash(row["date"], row["amount"], row.get("merchant", ""), aid)
        exists = db.query(Transaction).filter(Transaction.import_hash == ih).first() is not None
        if exists:
            dup_count += 1
        cat_name = _match_category(db, row.get("merchant", ""))
        preview_rows.append(
            ImportPreviewRow(
                date=row["date"],
                amount=row["amount"],
                merchant=row.get("merchant"),
                note=row.get("note"),
                category_name=cat_name,
                is_duplicate=exists,
            )
        )

    return ImportPreviewOut(rows=preview_rows[:100], total=len(preview_rows), duplicates=dup_count)


@router.post("/csv", response_model=ImportResultOut)
async def import_csv(
    file: UploadFile = File(...),
    source: str = Form("csv"),
    account_id: str = Form(...),
    db: Session = Depends(get_db),
):
    account = db.query(Account).filter(Account.id == UUID(account_id)).first()
    if not account:
        raise HTTPException(404, "账户不存在")

    job = ImportJob(filename=file.filename or "unknown", source=source, status=ImportStatus.processing)
    db.add(job)
    db.commit()

    content = (await file.read()).decode("utf-8-sig")
    parsed = _parse_csv_content(content, source)
    job.total_rows = len(parsed)
    imported = 0
    skipped = 0

    for row in parsed:
        ih = compute_import_hash(row["date"], row["amount"], row.get("merchant", ""), account.id)
        if db.query(Transaction).filter(Transaction.import_hash == ih).first():
            skipped += 1
            continue

        cat_name = _match_category(db, row.get("merchant", ""))
        category_id = None
        if cat_name:
            cat = db.query(Category).filter(Category.name == cat_name).first()
            category_id = cat.id if cat else None

        tx_type = TxType.expense if row.get("is_expense", True) else TxType.income
        tx = Transaction(
            type=tx_type,
            amount=row["amount"],
            date=row["date"],
            account_id=account.id,
            category_id=category_id,
            merchant=row.get("merchant"),
            note=row.get("note"),
            source=TxSource.import_,
            import_hash=ih,
        )
        db.add(tx)
        from services.finance import apply_transaction_to_balance

        apply_transaction_to_balance(db, account.id, tx_type, row["amount"])
        imported += 1

    job.imported_rows = imported
    job.skipped_rows = skipped
    job.status = ImportStatus.completed
    db.commit()
    logger.info("导入完成 job=%s imported=%s skipped=%s", job.id, imported, skipped)
    return ImportResultOut(job_id=job.id, imported=imported, skipped=skipped, status=job.status)
