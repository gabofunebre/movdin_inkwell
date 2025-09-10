from datetime import date
from decimal import Decimal
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
    iva_amount = (payload.amount * payload.iva_percent / Decimal("100")).quantize(Decimal("0.01"))
    iibb_base = payload.amount + iva_amount
    iibb_amount = (iibb_base * payload.iibb_percent / Decimal("100")).quantize(Decimal("0.01"))
    inv = Invoice(
        account_id=payload.account_id,
        date=payload.date,
        description=payload.description,
        number=payload.number,
        amount=payload.amount,
        iva_percent=payload.iva_percent,
        iva_amount=iva_amount,
        iibb_percent=payload.iibb_percent,
        iibb_amount=iibb_amount,
        type=payload.type,
    )
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
