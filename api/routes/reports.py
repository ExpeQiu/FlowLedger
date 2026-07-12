import io
from datetime import date

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from openpyxl import Workbook
from sqlalchemy.orm import Session

from database import get_db
from logging_config import logger
from schemas import CashFlowForecast, MonthlyReport
from services.finance import get_cash_flow_forecast, get_monthly_report

router = APIRouter(prefix="/api/reports", tags=["reports"])


@router.get("/monthly", response_model=MonthlyReport)
def monthly_report(month: str | None = None, db: Session = Depends(get_db)):
    if not month:
        today = date.today()
        month = f"{today.year}-{today.month:02d}"
    return get_monthly_report(db, month)


@router.get("/cashflow", response_model=CashFlowForecast)
def cashflow_forecast(days: int = 30, db: Session = Depends(get_db)):
    return get_cash_flow_forecast(db, days)


@router.post("/export")
def export_report(month: str, format: str = "xlsx", db: Session = Depends(get_db)):
    report = get_monthly_report(db, month)
    logger.info("导出报表 month=%s format=%s", month, format)

    if format == "xlsx":
        wb = Workbook()
        ws = wb.active
        ws.title = "月报"
        ws.append(["月份", month])
        ws.append(["总收入", float(report.total_income)])
        ws.append(["总支出", float(report.total_expense)])
        ws.append(["净额", float(report.net)])
        ws.append([])
        ws.append(["分类", "金额"])
        for item in report.by_category:
            ws.append([item["category"], float(item["amount"])])
        buf = io.BytesIO()
        wb.save(buf)
        buf.seek(0)
        return StreamingResponse(
            buf,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f"attachment; filename=report-{month}.xlsx"},
        )

    lines = [f"月份,{month}", f"总收入,{report.total_income}", f"总支出,{report.total_expense}"]
    for item in report.by_category:
        lines.append(f"{item['category']},{item['amount']}")
    content = "\n".join(lines)
    return StreamingResponse(
        io.BytesIO(content.encode()),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=report-{month}.csv"},
    )
