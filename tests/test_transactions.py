import os
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Optional

import pytest
from fastapi import HTTPException, status
from sqlalchemy import delete

BASE_DIR = Path(__file__).resolve().parents[1]
APP_DIR = BASE_DIR / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

os.environ.setdefault("DATABASE_URL", "sqlite+pysqlite:///:memory:")
os.environ.setdefault("DB_SCHEMA", "")

from config.constants import Currency  # noqa: E402
from config.db import SessionLocal, init_db  # noqa: E402
from models import Account, Transaction  # noqa: E402
from routes.transactions import create_tx, list_transactions, update_tx  # noqa: E402
from schemas import TransactionCreate  # noqa: E402


class DummyAccount:
    def __init__(self, account_id: int, is_billing: bool) -> None:
        self.id = account_id
        self.is_billing = is_billing


class DummySession:
    def __init__(self, account: Optional[DummyAccount]) -> None:
        self._account = account

    def get(self, model, ident):
        if self._account and ident == self._account.id:
            return self._account
        return None

    def add(self, *_args, **_kwargs):  # pragma: no cover - should not be called
        raise AssertionError("add should not be invoked for billing accounts")

    def commit(self):  # pragma: no cover - should not be called
        raise AssertionError("commit should not be invoked for billing accounts")

    def refresh(self, *_args, **_kwargs):  # pragma: no cover - should not be called
        raise AssertionError("refresh should not be invoked for billing accounts")


def test_create_tx_rejects_billing_account():
    dummy_account = DummyAccount(account_id=1, is_billing=True)
    dummy_db = DummySession(dummy_account)
    payload = TransactionCreate(
        account_id=1,
        date=date.today(),
        description="",
        amount=Decimal("10"),
        notes="",
    )

    with pytest.raises(HTTPException) as exc_info:
        create_tx(payload=payload, db=dummy_db)

    assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST
    assert (
        exc_info.value.detail
        == "No se permiten movimientos manuales para la cuenta de facturación"
    )


@pytest.fixture
def db_session():
    init_db()
    with SessionLocal() as session:
        session.execute(delete(Transaction))
        session.execute(delete(Account))
        session.commit()
        yield session
        session.execute(delete(Transaction))
        session.execute(delete(Account))
        session.commit()


def _create_account(session, name: str) -> Account:
    account = Account(name=name, currency=Currency.ARS, opening_balance=Decimal("0"))
    session.add(account)
    session.commit()
    session.refresh(account)
    return account


def _create_transaction(
    session,
    account: Account,
    *,
    tx_date: date,
    description: str,
    amount: Decimal,
    notes: str = "",
) -> Transaction:
    transaction = Transaction(
        account_id=account.id,
        date=tx_date,
        description=description,
        amount=amount,
        notes=notes,
    )
    session.add(transaction)
    session.commit()
    session.refresh(transaction)
    return transaction


def test_list_transactions_filters_and_paginates(db_session):
    account_a = _create_account(db_session, "Cuenta Pagos")
    account_b = _create_account(db_session, "Cuenta Otros")

    newer = _create_transaction(
        db_session,
        account_a,
        tx_date=date(2023, 5, 10),
        description="Pago alquiler",
        amount=Decimal("-500"),
        notes="Mayo",
    )
    _create_transaction(
        db_session,
        account_a,
        tx_date=date(2023, 5, 8),
        description="Pago proveedor",
        amount=Decimal("-200"),
        notes="insumos",
    )
    _create_transaction(
        db_session,
        account_a,
        tx_date=date(2023, 5, 5),
        description="Cobro cliente",
        amount=Decimal("1000"),
    )
    _create_transaction(
        db_session,
        account_b,
        tx_date=date(2023, 5, 9),
        description="Pago externo",
        amount=Decimal("-50"),
    )

    result = list_transactions(
        limit=1,
        offset=0,
        search="PAGO",
        start_date=date(2023, 5, 1),
        end_date=date(2023, 5, 31),
        account_id=account_a.id,
        db=db_session,
    )

    assert result.limit == 1
    assert result.offset == 0
    assert result.total == 2
    assert result.has_more is True
    assert len(result.items) == 1
    assert result.items[0].id == newer.id


def test_list_transactions_respects_offset_metadata(db_session):
    account = _create_account(db_session, "Cuenta Paginacion")
    _create_transaction(
        db_session,
        account,
        tx_date=date(2023, 6, 10),
        description="Pago alquiler",
        amount=Decimal("-500"),
    )
    second = _create_transaction(
        db_session,
        account,
        tx_date=date(2023, 6, 8),
        description="Pago proveedor",
        amount=Decimal("-200"),
    )
    third = _create_transaction(
        db_session,
        account,
        tx_date=date(2023, 6, 5),
        description="Cobro cliente",
        amount=Decimal("1000"),
    )

    result = list_transactions(
        limit=2,
        offset=1,
        account_id=account.id,
        db=db_session,
    )

    assert result.limit == 2
    assert result.offset == 1
    assert result.total == 3
    assert result.has_more is False
    descriptions = [item.description for item in result.items]
    assert descriptions == [second.description, third.description]


def test_update_tx_restricts_billing_fields(db_session):
    billing_account = Account(
        name="Cuenta facturación",
        currency=Currency.ARS,
        opening_balance=Decimal("0"),
        is_billing=True,
    )
    db_session.add(billing_account)
    db_session.commit()
    db_session.refresh(billing_account)

    other_account = _create_account(db_session, "Cuenta secundaria")

    original_amount = Decimal("123.45")
    tx = _create_transaction(
        db_session,
        billing_account,
        tx_date=date(2024, 1, 10),
        description="Descripción original",
        amount=original_amount,
        notes="Notas originales",
    )

    payload = TransactionCreate(
        account_id=other_account.id,
        date=tx.date,
        description="Concepto editado",
        amount=Decimal("999.99"),
        notes="Intento cambiar notas",
    )

    updated = update_tx(tx_id=tx.id, payload=payload, db=db_session)

    assert updated.description == "Concepto editado"
    assert updated.amount == original_amount
    assert updated.account_id == billing_account.id
    assert updated.notes == "Notas originales"

    db_session.refresh(tx)
    assert tx.description == "Concepto editado"
    assert tx.amount == original_amount
    assert tx.account_id == billing_account.id
    assert tx.notes == "Notas originales"
