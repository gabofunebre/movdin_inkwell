from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from config.db import get_db
from models import FrequentTransaction
from schemas import FrequentIn, FrequentOut

router = APIRouter(prefix="/frequents")


@router.post("", response_model=FrequentOut)
def create_frequent(payload: FrequentIn, db: Session = Depends(get_db)):
    freq = FrequentTransaction(**payload.dict())
    db.add(freq)
    db.commit()
    db.refresh(freq)
    return freq


@router.get("", response_model=List[FrequentOut])
def list_frequents(db: Session = Depends(get_db)):
    rows = db.scalars(
        select(FrequentTransaction).order_by(FrequentTransaction.description)
    ).all()
    return rows


@router.put("/{freq_id}", response_model=FrequentOut)
def update_frequent(freq_id: int, payload: FrequentIn, db: Session = Depends(get_db)):
    freq = db.get(FrequentTransaction, freq_id)
    if not freq:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Frecuente no encontrado",
        )
    for field, value in payload.dict().items():
        setattr(freq, field, value)
    db.commit()
    db.refresh(freq)
    return freq


@router.delete("/{freq_id}")
def delete_frequent(freq_id: int, db: Session = Depends(get_db)):
    freq = db.get(FrequentTransaction, freq_id)
    if not freq:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Frecuente no encontrado",
        )
    db.delete(freq)
    db.commit()
    return {"ok": True}
