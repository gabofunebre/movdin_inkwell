import os
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Optional

import pytest
from fastapi import HTTPException, status

BASE_DIR = Path(__file__).resolve().parents[1]
APP_DIR = BASE_DIR / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

os.environ.setdefault("DATABASE_URL", "sqlite+pysqlite:///:memory:")
os.environ.setdefault("DB_SCHEMA", "")

from routes.transactions import create_tx  # noqa: E402
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
