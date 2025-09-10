from datetime import date
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from config.db import get_db
from models import Invoice
from schemas import InvoiceCreate, InvoiceOut

router = APIRouter(prefix="/invoices")


@router.post("", response_model=InvoiceOut)
def create_invoice(payload: InvoiceCreate, db: Session = Depends(get_db)):
    if payload.date > date.today():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No se permiten fechas futuras",
        )
    inv = Invoice(**payload.dict())
    db.add(inv)
    db.commit()
    db.refresh(inv)
    return inv


@router.get("", response_model=List[InvoiceOut])
def list_invoices(limit: int = 50, offset: int = 0, db: Session = Depends(get_db)):
    stmt = (
        select(Invoice)
        .order_by(Invoice.date.desc(), Invoice.id.desc())
        .limit(limit)
        .offset(offset)
    )
    rows = db.scalars(stmt).all()
    return rows
