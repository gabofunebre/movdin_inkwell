from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from auth import require_api_key
from config.db import get_db
from models import Account
from schemas import AccountOut

router = APIRouter()


@router.get(
    "/facturacion-info",
    response_model=AccountOut,
    dependencies=[Depends(require_api_key)],
)
def billing_info(db: Session = Depends(get_db)):
    acc = db.scalar(select(Account).where(Account.is_billing == True))
    if not acc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Billing account not found")
    return acc
