from datetime import date
from decimal import Decimal
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from auth import require_admin
from config.db import get_db
from models import RetentionCertificate
from schemas import RetentionCertificateCreate, RetentionCertificateOut

router = APIRouter(prefix="/retention-certificates")


@router.post("", response_model=RetentionCertificateOut)
def create_certificate(
    payload: RetentionCertificateCreate, db: Session = Depends(get_db)
):
    if payload.date > date.today():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No se permiten fechas futuras",
        )
    amount = abs(payload.amount).quantize(Decimal("0.01"))
    cert = RetentionCertificate(
        number=payload.number,
        date=payload.date,
        invoice_reference=payload.invoice_reference,
        concept=payload.concept,
        amount=amount,
    )
    db.add(cert)
    db.commit()
    db.refresh(cert)
    return cert


@router.get("", response_model=List[RetentionCertificateOut])
def list_certificates(
    limit: int = 100, offset: int = 0, db: Session = Depends(get_db)
):
    stmt = (
        select(RetentionCertificate)
        .order_by(RetentionCertificate.date.desc(), RetentionCertificate.id.desc())
        .limit(limit)
        .offset(offset)
    )
    return db.scalars(stmt).all()


@router.put(
    "/{certificate_id}",
    response_model=RetentionCertificateOut,
    dependencies=[Depends(require_admin)],
)
def update_certificate(
    certificate_id: int,
    payload: RetentionCertificateCreate,
    db: Session = Depends(get_db),
):
    cert = db.get(RetentionCertificate, certificate_id)
    if not cert:
        raise HTTPException(status_code=404, detail="Certificado no encontrado")
    if payload.date > date.today():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No se permiten fechas futuras",
        )
    amount = abs(payload.amount).quantize(Decimal("0.01"))
    cert.number = payload.number
    cert.date = payload.date
    cert.invoice_reference = payload.invoice_reference
    cert.concept = payload.concept
    cert.amount = amount
    db.add(cert)
    db.commit()
    db.refresh(cert)
    return cert


@router.delete(
    "/{certificate_id}",
    status_code=204,
    dependencies=[Depends(require_admin)],
)
def delete_certificate(certificate_id: int, db: Session = Depends(get_db)):
    cert = db.get(RetentionCertificate, certificate_id)
    if cert:
        db.delete(cert)
        db.commit()
    return Response(status_code=204)
