from datetime import date
from decimal import Decimal
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from config.db import get_db
from config.constants import InvoiceType
from models import Invoice
from auth import require_admin
from schemas import InvoiceCreate, InvoiceOut

router = APIRouter(prefix="/invoices")


@router.post("", response_model=InvoiceOut)
def create_invoice(payload: InvoiceCreate, db: Session = Depends(get_db)):
    if payload.date > date.today():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No se permiten fechas futuras",
        )
    if payload.iva_amount is not None:
        iva_amount = abs(payload.iva_amount).quantize(Decimal("0.01"))
    else:
        iva_amount = (payload.amount * payload.iva_percent / Decimal("100")).quantize(
            Decimal("0.01")
        )
    if payload.type == InvoiceType.SALE:
        iibb_percent = payload.iibb_percent
        if payload.iibb_amount is not None:
            iibb_amount = abs(payload.iibb_amount).quantize(Decimal("0.01"))
        else:
            iibb_base = payload.amount + iva_amount
            iibb_amount = (iibb_base * iibb_percent / Decimal("100")).quantize(
                Decimal("0.01")
            )
    else:
        iibb_percent = Decimal("0")
        iibb_amount = (
            abs(payload.iibb_amount).quantize(Decimal("0.01"))
            if payload.iibb_amount is not None
            else Decimal("0")
        )
    if payload.retenciones is not None:
        retenciones = abs(payload.retenciones).quantize(Decimal("0.01"))
    else:
        retenciones = Decimal("0")
    if payload.type == InvoiceType.SALE:
        retenciones = Decimal("0")
    inv = Invoice(
        account_id=payload.account_id,
        date=payload.date,
        description=payload.description,
        number=payload.number,
        amount=payload.amount,
        iva_percent=payload.iva_percent,
        iva_amount=iva_amount,
        iibb_percent=iibb_percent,
        iibb_amount=iibb_amount,
        retenciones=retenciones,
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


@router.put("/{invoice_id}", response_model=InvoiceOut, dependencies=[Depends(require_admin)])
def update_invoice(invoice_id: int, payload: InvoiceCreate, db: Session = Depends(get_db)):
    inv = db.get(Invoice, invoice_id)
    if not inv:
        raise HTTPException(status_code=404, detail="Factura no encontrada")
    if payload.date > date.today():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No se permiten fechas futuras")
    if payload.iva_amount is not None:
        iva_amount = abs(payload.iva_amount).quantize(Decimal("0.01"))
    else:
        iva_amount = (payload.amount * payload.iva_percent / Decimal("100")).quantize(
            Decimal("0.01")
        )
    if payload.type == InvoiceType.SALE:
        iibb_percent = payload.iibb_percent
        if payload.iibb_amount is not None:
            iibb_amount = abs(payload.iibb_amount).quantize(Decimal("0.01"))
        else:
            iibb_base = payload.amount + iva_amount
            iibb_amount = (iibb_base * iibb_percent / Decimal("100")).quantize(
                Decimal("0.01")
            )
    else:
        iibb_percent = Decimal("0")
        iibb_amount = (
            abs(payload.iibb_amount).quantize(Decimal("0.01"))
            if payload.iibb_amount is not None
            else Decimal("0")
        )
    if payload.retenciones is not None:
        retenciones = abs(payload.retenciones).quantize(Decimal("0.01"))
    else:
        retenciones = Decimal("0")
    if payload.type == InvoiceType.SALE:
        retenciones = Decimal("0")
    for field in [
        "account_id",
        "date",
        "description",
        "number",
        "amount",
        "iva_percent",
        "type",
    ]:
        setattr(inv, field, getattr(payload, field))
    inv.iva_amount = iva_amount
    inv.iibb_percent = iibb_percent
    inv.iibb_amount = iibb_amount
    inv.retenciones = retenciones
    db.add(inv)
    db.commit()
    db.refresh(inv)
    return inv


@router.delete("/{invoice_id}", status_code=204, dependencies=[Depends(require_admin)])
def delete_invoice(invoice_id: int, db: Session = Depends(get_db)):
    inv = db.get(Invoice, invoice_id)
    if inv:
        db.delete(inv)
        db.commit()
    return Response(status_code=204)
