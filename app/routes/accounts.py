from datetime import date
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import and_, bindparam, func, select
from sqlalchemy.orm import Session

from config.db import get_db
from models import Account, Transaction, Tax
from schemas import (
    AccountBalance,
    AccountIn,
    AccountOut,
    BalanceOut,
    TransactionWithBalance,
    AccountTaxUpdate,
    TaxOut,
)

router = APIRouter(prefix="/accounts")


@router.post("", response_model=AccountOut)
def create_account(payload: AccountIn, db: Session = Depends(get_db)):
    existing = db.scalar(select(Account).where(Account.name == payload.name))
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Account name already exists",
        )
    acc = Account(**payload.dict())
    db.add(acc)
    db.commit()
    db.refresh(acc)
    return acc


@router.get("", response_model=List[AccountOut])
def list_accounts(
    include_inactive: bool = False, db: Session = Depends(get_db)
):
    stmt = select(Account).order_by(Account.name)
    if not include_inactive:
        stmt = stmt.where(Account.is_active == True)
    rows = db.scalars(stmt).all()
    return rows


@router.put("/{account_id}", response_model=AccountOut)
def update_account(account_id: int, payload: AccountIn, db: Session = Depends(get_db)):
    acc = db.get(Account, account_id)
    if not acc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Account not found"
        )
    existing = db.scalar(
        select(Account).where(Account.name == payload.name, Account.id != account_id)
    )
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Account name already exists",
        )
    for field, value in payload.dict().items():
        setattr(acc, field, value)
    db.commit()
    db.refresh(acc)
    return acc


@router.delete("/{account_id}")
def delete_account(account_id: int, db: Session = Depends(get_db)):
    acc = db.get(Account, account_id)
    if not acc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Account not found"
        )
    acc.is_active = False
    db.commit()
    return {"ok": True}


@router.get("/{account_id}/taxes", response_model=List[TaxOut])
def get_account_taxes(account_id: int, db: Session = Depends(get_db)):
    acc = db.get(Account, account_id)
    if not acc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Account not found"
        )
    return acc.taxes


@router.put("/{account_id}/taxes", response_model=List[TaxOut])
def set_account_taxes(account_id: int, payload: AccountTaxUpdate, db: Session = Depends(get_db)):
    acc = db.get(Account, account_id)
    if not acc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Account not found"
        )
    taxes = db.scalars(select(Tax).where(Tax.id.in_(payload.tax_ids))).all()
    acc.taxes = taxes
    db.commit()
    db.refresh(acc)
    return acc.taxes


@router.get("/balances", response_model=List[AccountBalance])
def account_balances(to_date: date | None = None, db: Session = Depends(get_db)):
    to_date = to_date or date.max
    stmt = (
        select(
            Account.id,
            Account.name,
            Account.currency,
            (Account.opening_balance + func.coalesce(func.sum(Transaction.amount), 0)).label(
                "balance"
            ),
            Account.color,
        )
        .select_from(Account)
        .join(
            Transaction,
            and_(
                Transaction.account_id == Account.id,
                Transaction.date <= bindparam("to_date"),
            ),
            isouter=True,
        )
        .where(Account.is_active == True)
        .group_by(
            Account.id,
            Account.name,
            Account.opening_balance,
            Account.currency,
            Account.color,
        )
        .order_by(Account.name)
    )
    rows = db.execute(stmt, {"to_date": to_date}).all()
    return [
        AccountBalance(
            account_id=r.id,
            name=r.name,
            currency=r.currency,
            balance=r.balance,
            color=r.color,
        )
        for r in rows
    ]


@router.get("/{account_id}/balance", response_model=BalanceOut)
def account_balance(account_id: int, to_date: date | None = None, db: Session = Depends(get_db)):
    to_date = to_date or date.max
    stmt = (
        select((Account.opening_balance + func.coalesce(func.sum(Transaction.amount), 0)).label("balance"))
        .select_from(Account)
        .join(
            Transaction,
            and_(
                Transaction.account_id == Account.id,
                Transaction.date <= bindparam("to_date"),
            ),
            isouter=True,
        )
        .where(Account.id == bindparam("account_id"))
        .group_by(Account.id, Account.opening_balance)
    )
    row = db.execute(stmt, {"account_id": account_id, "to_date": to_date}).one()
    return BalanceOut(balance=row.balance)


@router.get("/{account_id}/transactions", response_model=List[TransactionWithBalance])
def account_transactions(
    account_id: int,
    from_: date | None = None,
    to: date | None = None,
    db: Session = Depends(get_db),
):
    stmt = (
        select(
            Transaction.id,
            Transaction.account_id,
            Transaction.date,
            Transaction.description,
            Transaction.amount,
            Transaction.notes,
            func.sum(Transaction.amount)
            .over(
                partition_by=Transaction.account_id,
                order_by=(Transaction.date, Transaction.id),
            )
            .label("running_balance"),
        )
        .where(Transaction.account_id == account_id)
    )
    if from_:
        stmt = stmt.where(Transaction.date >= from_)
    if to:
        stmt = stmt.where(Transaction.date <= to)
    stmt = stmt.order_by(Transaction.date, Transaction.id)
    rows = db.execute(stmt).all()
    return [
        TransactionWithBalance(
            id=r.id,
            account_id=r.account_id,
            date=r.date,
            description=r.description,
            amount=r.amount,
            notes=r.notes,
            running_balance=r.running_balance,
        )
        for r in rows
    ]
