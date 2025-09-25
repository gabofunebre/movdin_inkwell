from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from auth import require_admin
from config.db import get_db
from config.constants import DEFAULT_RETAINED_TAX_TYPES
from models import RetainedTaxType, RetentionCertificate
from schemas import RetainedTaxTypeCreate, RetainedTaxTypeOut

router = APIRouter(prefix="/retained-tax-types")

PROTECTED_TAX_NAMES = set(DEFAULT_RETAINED_TAX_TYPES)


def _ensure_not_protected(tax_type: RetainedTaxType) -> None:
    if tax_type.name in PROTECTED_TAX_NAMES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No se puede modificar ni eliminar un impuesto retenido predeterminado",
        )


@router.post(
    "",
    response_model=RetainedTaxTypeOut,
    dependencies=[Depends(require_admin)],
)
def create_retained_tax_type(
    payload: RetainedTaxTypeCreate, db: Session = Depends(get_db)
):
    tax_type = RetainedTaxType(name=payload.name)
    db.add(tax_type)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El impuesto retenido ya existe",
        )
    db.refresh(tax_type)
    return tax_type


@router.get("", response_model=List[RetainedTaxTypeOut])
def list_retained_tax_types(db: Session = Depends(get_db)):
    stmt = select(RetainedTaxType).order_by(RetainedTaxType.name)
    return db.scalars(stmt).all()


@router.put(
    "/{type_id}",
    response_model=RetainedTaxTypeOut,
    dependencies=[Depends(require_admin)],
)
def update_retained_tax_type(
    type_id: int, payload: RetainedTaxTypeCreate, db: Session = Depends(get_db)
):
    tax_type = db.get(RetainedTaxType, type_id)
    if not tax_type:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Impuesto retenido no encontrado",
        )
    _ensure_not_protected(tax_type)
    tax_type.name = payload.name
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El impuesto retenido ya existe",
        )
    db.refresh(tax_type)
    return tax_type


@router.delete(
    "/{type_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_admin)],
)
def delete_retained_tax_type(type_id: int, db: Session = Depends(get_db)):
    tax_type = db.get(RetainedTaxType, type_id)
    if not tax_type:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Impuesto retenido no encontrado",
        )
    _ensure_not_protected(tax_type)
    in_use = db.scalar(
        select(func.count())
        .select_from(RetentionCertificate)
        .where(RetentionCertificate.retained_tax_type_id == type_id)
    )
    if in_use:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No se puede eliminar un impuesto retenido en uso",
        )
    db.delete(tax_type)
    db.commit()
