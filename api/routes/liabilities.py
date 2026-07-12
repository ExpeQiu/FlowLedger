from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from models import Liability
from schemas import LiabilityCreate, LiabilityOut

router = APIRouter(prefix="/api/liabilities", tags=["liabilities"])


@router.get("", response_model=list[LiabilityOut])
def list_liabilities(db: Session = Depends(get_db)):
    return db.query(Liability).order_by(Liability.due_date).all()


@router.post("", response_model=LiabilityOut, status_code=201)
def create_liability(data: LiabilityCreate, db: Session = Depends(get_db)):
    item = Liability(**data.model_dump())
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@router.patch("/{liability_id}", response_model=LiabilityOut)
def update_liability(liability_id: UUID, data: LiabilityCreate, db: Session = Depends(get_db)):
    item = db.query(Liability).filter(Liability.id == liability_id).first()
    if not item:
        raise HTTPException(404, "负债不存在")
    for k, v in data.model_dump().items():
        setattr(item, k, v)
    db.commit()
    db.refresh(item)
    return item


@router.delete("/{liability_id}", status_code=204)
def delete_liability(liability_id: UUID, db: Session = Depends(get_db)):
    item = db.query(Liability).filter(Liability.id == liability_id).first()
    if not item:
        raise HTTPException(404, "负债不存在")
    db.delete(item)
    db.commit()
