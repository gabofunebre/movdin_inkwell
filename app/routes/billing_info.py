from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from auth import require_api_key
from config.db import get_db
from models import Account, Invoice, RetentionCertificate
from schemas import BillingInfoOut

router = APIRouter()


@router.get(
    "/facturacion-info",
    response_model=BillingInfoOut,
    dependencies=[Depends(require_api_key)],
)
def billing_info(db: Session = Depends(get_db)):
    acc = db.scalar(select(Account).where(Account.is_billing == True))
    if not acc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Billing account not found")
    invoices = list(
        db.scalars(
            select(Invoice)
            .where(Invoice.account_id == acc.id)
            .order_by(Invoice.date, Invoice.id)
        )
    )
    certificates = list(
        db.scalars(
            select(RetentionCertificate)
            .options(selectinload(RetentionCertificate.retained_tax_type))
            .order_by(RetentionCertificate.date, RetentionCertificate.id)
        )
    )
    return BillingInfoOut(invoices=invoices, retention_certificates=certificates)
