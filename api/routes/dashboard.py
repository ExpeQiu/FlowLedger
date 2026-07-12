from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from database import get_db
from schemas import DashboardOut
from services.finance import get_dashboard

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("", response_model=DashboardOut)
def dashboard(month: str | None = None, db: Session = Depends(get_db)):
    from datetime import date

    if not month:
        today = date.today()
        month = f"{today.year}-{today.month:02d}"
    return get_dashboard(db, month)
