from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from config.db import get_db
from models import Tax
from schemas import TaxIn, TaxOut

router = APIRouter(prefix="/taxes")


@router.post("", response_model=TaxOut)
def create_tax(payload: TaxIn, db: Session = Depends(get_db)):
    existing = db.scalar(select(Tax).where(Tax.name == payload.name))
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Tax name already exists",
        )
    tax = Tax(**payload.dict())
    db.add(tax)
    db.commit()
    db.refresh(tax)
    return tax


@router.get("", response_model=List[TaxOut])
def list_taxes(db: Session = Depends(get_db)):
    rows = db.scalars(select(Tax).order_by(Tax.name)).all()
    return rows


@router.put("/{tax_id}", response_model=TaxOut)
def update_tax(tax_id: int, payload: TaxIn, db: Session = Depends(get_db)):
    tax = db.get(Tax, tax_id)
    if not tax:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tax not found")
    existing = db.scalar(select(Tax).where(Tax.name == payload.name, Tax.id != tax_id))
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Tax name already exists",
        )
    for field, value in payload.dict().items():
        setattr(tax, field, value)
    db.commit()
    db.refresh(tax)
    return tax


@router.delete("/{tax_id}")
def delete_tax(tax_id: int, db: Session = Depends(get_db)):
    tax = db.get(Tax, tax_id)
    if not tax:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tax not found")
    db.delete(tax)
    db.commit()
    return {"ok": True}
