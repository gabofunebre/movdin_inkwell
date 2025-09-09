from datetime import date
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from config.db import get_db
from models import Transaction
from schemas import TransactionCreate, TransactionOut

router = APIRouter(prefix="/transactions")


@router.post("", response_model=TransactionOut)
def create_tx(payload: TransactionCreate, db: Session = Depends(get_db)):
    if payload.date > date.today():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No se permiten fechas futuras",
        )
    tx = Transaction(**payload.dict())
    db.add(tx)
    db.commit()
    db.refresh(tx)
    return tx


@router.get("", response_model=List[TransactionOut])
def list_transactions(limit: int = 50, offset: int = 0, db: Session = Depends(get_db)):
    stmt = (
        select(Transaction)
        .order_by(Transaction.date.desc(), Transaction.id.desc())
        .limit(limit)
        .offset(offset)
    )
    rows = db.scalars(stmt).all()
    return rows
