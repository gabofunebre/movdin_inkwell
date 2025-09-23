import os
import sys
from pathlib import Path

import pytest
from fastapi import HTTPException, status

BASE_DIR = Path(__file__).resolve().parents[1]
APP_DIR = BASE_DIR / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

os.environ.setdefault("DATABASE_URL", "sqlite+pysqlite:///:memory:")
os.environ.setdefault("DB_SCHEMA", "")

from routes.accounts import account_balance  # noqa: E402


class DummySession:
    def get(self, model, ident):
        return None

    def execute(self, *args, **kwargs):  # pragma: no cover - should not be called
        raise AssertionError("execute should not be called when account is missing")


def test_account_balance_returns_404_for_missing_account():
    dummy_db = DummySession()

    with pytest.raises(HTTPException) as exc_info:
        account_balance(account_id=999, to_date=None, db=dummy_db)

    assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND
    assert exc_info.value.detail == "Account not found"
