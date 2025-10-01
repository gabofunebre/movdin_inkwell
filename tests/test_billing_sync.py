import os
import sys
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi import HTTPException, status
from sqlalchemy import select

BASE_DIR = Path(__file__).resolve().parents[1]
APP_DIR = BASE_DIR / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

os.environ.setdefault("DATABASE_URL", "sqlite+pysqlite:///:memory:")
os.environ.setdefault("DB_SCHEMA", "")

import httpx  # noqa: E402
from config import db  # noqa: E402
from config.constants import Currency  # noqa: E402
from models import Account, Transaction  # noqa: E402
from routes import transactions as transactions_module  # noqa: E402
from routes.transactions import sync_billing_transactions  # noqa: E402


@pytest.fixture(autouse=True)
def setup_database():
    db.Base.metadata.drop_all(bind=db.engine, checkfirst=True)
    db.Base.metadata.create_all(bind=db.engine, checkfirst=True)
    yield
    db.Base.metadata.drop_all(bind=db.engine, checkfirst=True)


class DummyResponse:
    def __init__(self, status_code: int, payload: dict):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload


def _build_transaction_event(event: str, transaction_id: int, payload: dict | None) -> dict:
    data = {
        "id": transaction_id,
        "event": event,
        "occurred_at": "2024-01-04T10:00:00Z",
        "transaction_id": transaction_id,
    }
    if payload is not None:
        data["transaction"] = payload
    return data


def test_sync_billing_transactions_applies_events_and_acknowledges_checkpoint(monkeypatch):
    os.environ["FACTURACION_RUTA_DATA"] = "https://facturacion.example/api/movimientos_cuenta_facturada"
    os.environ["BILLING_API_KEY"] = "secret"

    get_calls: list[dict] = []

    def fake_get(url, params=None, headers=None, timeout=None):
        get_calls.append(
            {
                "url": url,
                "params": params,
                "headers": headers,
                "timeout": timeout,
            }
        )
        assert headers == {"X-API-Key": "secret"}
        expected_feed_url = os.environ["FACTURACION_RUTA_DATA"].rstrip("/")
        assert url == expected_feed_url
        assert params == {"limit": 3, "changes_limit": 3, "changes_since": 850}
        return DummyResponse(
            200,
            {
                "transactions": [
                    {
                        "id": 501,
                        "date": "2024-01-03",
                        "amount": "150.50",
                        "description": "Alta",
                        "notes": "Creado",
                    },
                    {
                        "id": 600,
                        "date": "2024-01-02",
                        "amount": "200.00",
                        "description": "Actualizada",
                        "notes": "Modificada",
                    },
                ],
                "transaction_events": [
                    _build_transaction_event(
                        "created",
                        501,
                        {
                            "id": 501,
                            "date": "2024-01-03",
                            "amount": "150.50",
                            "description": "Alta",
                            "notes": "Creado",
                        },
                    ),
                    _build_transaction_event(
                        "updated",
                        600,
                        {
                            "id": 600,
                            "date": "2024-01-02",
                            "amount": "200.00",
                            "description": "Actualizada",
                            "notes": "Modificada",
                        },
                    ),
                    _build_transaction_event("deleted", 700, None),
                ],
                "transactions_checkpoint_id": 903,
                "last_confirmed_transaction_id": 850,
                "has_more_transactions": False,
                "changes": [
                    {
                        "id": 905,
                        "movement_id": 1,
                        "event": "created",
                        "payload": {"id": 1},
                    }
                ],
                "changes_checkpoint_id": 905,
                "last_confirmed_change_id": 903,
                "has_more_changes": False,
            },
        )

    monkeypatch.setattr(httpx, "get", fake_get)

    ack_calls: dict = {}

    def fake_post(url, json, headers, timeout):
        ack_calls.update(
            {
                "url": url,
                "json": json,
                "headers": headers,
                "timeout": timeout,
            }
        )
        expected_feed_url = os.environ["FACTURACION_RUTA_DATA"].rstrip("/")
        assert url == expected_feed_url
        return DummyResponse(
            200,
            {
                "last_transaction_id": 903,
                "last_change_id": 905,
                "transactions_updated_at": "2024-01-04T10:00:00Z",
                "changes_updated_at": "2024-01-04T11:00:00Z",
            },
        )

    monkeypatch.setattr(httpx, "post", fake_post)

    with db.SessionLocal() as session:
        account = Account(
            name="Cuenta facturación",
            opening_balance=Decimal("0"),
            currency=Currency.ARS,
            color="#000000",
            is_active=True,
            is_billing=True,
        )
        session.add(account)
        session.flush()

        account.billing_last_transactions_confirmed_id = 845
        account.billing_last_changes_confirmed_id = 850

        session.add_all(
            [
                Transaction(
                    account_id=account.id,
                    date=date(2024, 1, 1),
                    description="Original",
                    amount=Decimal("100.00"),
                    notes="",
                    billing_transaction_id=600,
                ),
                Transaction(
                    account_id=account.id,
                    date=date(2024, 1, 1),
                    description="A borrar",
                    amount=Decimal("50.00"),
                    notes="",
                    billing_transaction_id=700,
                ),
            ]
        )
        session.commit()

        result = sync_billing_transactions(limit=3, db=session)

        created_tx = session.scalar(
            select(Transaction).where(Transaction.billing_transaction_id == 501)
        )
        assert created_tx is not None
        assert created_tx.description == "Alta"
        assert created_tx.amount == Decimal("150.50")
        assert created_tx.notes == "Creado"

        updated_tx = session.scalar(
            select(Transaction).where(Transaction.billing_transaction_id == 600)
        )
        assert updated_tx is not None
        assert updated_tx.description == "Actualizada"
        assert updated_tx.amount == Decimal("200.00")
        assert updated_tx.notes == "Modificada"

        deleted_tx = session.scalar(
            select(Transaction).where(Transaction.billing_transaction_id == 700)
        )
        assert deleted_tx is None

        session.refresh(account)
        assert account.billing_last_transactions_checkpoint_id == 903
        assert account.billing_last_transactions_confirmed_id == 903
        assert account.billing_last_changes_checkpoint_id == 905
        assert account.billing_last_changes_confirmed_id == 905
        synced_at = account.billing_synced_at
        assert synced_at is not None
        if synced_at.tzinfo is None:
            synced_at = synced_at.replace(tzinfo=timezone.utc)
        else:
            synced_at = synced_at.astimezone(timezone.utc)
        assert synced_at == datetime(2024, 1, 4, 11, 0, tzinfo=timezone.utc)

        assert result["nuevos"] == 1
        assert result["modificados"] == 1
        assert result["eliminados"] == 1
        assert (
            result["message"]
            == "Se sincronizaron 1 movimiento nuevo, 1 movimiento modificado, 1 movimiento eliminado."
        )

    assert get_calls
    assert get_calls[0]["params"] == {"limit": 3, "changes_limit": 3, "changes_since": 850}
    assert ack_calls["json"] == {
        "movements_checkpoint_id": 903,
        "changes_checkpoint_id": 905,
    }


def test_sync_billing_transactions_handles_created_then_updated_in_same_batch(monkeypatch):
    os.environ["FACTURACION_RUTA_DATA"] = "https://facturacion.example/api/movimientos_cuenta_facturada"
    os.environ["BILLING_API_KEY"] = "secret"

    def fake_get(url, params=None, headers=None, timeout=None):
        assert headers == {"X-API-Key": "secret"}
        return DummyResponse(
            200,
            {
                "transactions": [],
                "transaction_events": [
                    _build_transaction_event(
                        "created",
                        3000,
                        {
                            "id": 3000,
                            "date": "2024-06-01",
                            "amount": "75.00",
                            "description": "Movimiento creado",
                            "notes": "Inicial",
                        },
                    ),
                    _build_transaction_event(
                        "updated",
                        3000,
                        {
                            "id": 3000,
                            "date": "2024-06-02",
                            "amount": "80.00",
                            "description": "Movimiento actualizado",
                            "notes": "Actualizado",
                        },
                    ),
                ],
                "transactions_checkpoint_id": None,
                "last_confirmed_transaction_id": None,
                "changes": [],
                "changes_checkpoint_id": None,
                "last_confirmed_change_id": None,
            },
        )

    monkeypatch.setattr(httpx, "get", fake_get)
    monkeypatch.setattr(httpx, "post", lambda *_args, **_kwargs: DummyResponse(200, {}))

    with db.SessionLocal() as session:
        account = Account(
            name="Cuenta facturación",
            opening_balance=Decimal("0"),
            currency=Currency.ARS,
            color="#000000",
            is_active=True,
            is_billing=True,
        )
        session.add(account)
        session.commit()

        result = sync_billing_transactions(limit=2, db=session)

        stored_tx = session.scalar(
            select(Transaction).where(Transaction.billing_transaction_id == 3000)
        )
        assert stored_tx is not None
        assert stored_tx.date == date(2024, 6, 2)
        assert stored_tx.amount == Decimal("80.00")
        assert stored_tx.description == "Movimiento actualizado"
        assert stored_tx.notes == "Actualizado"

        assert result["nuevos"] == 1
        assert result["modificados"] == 1


def test_sync_billing_transactions_does_not_ack_when_commit_fails(monkeypatch):
    os.environ["FACTURACION_RUTA_DATA"] = "https://facturacion.example/api/movimientos_cuenta_facturada"
    os.environ["BILLING_API_KEY"] = "secret"

    def fake_get(url, params=None, headers=None, timeout=None):
        assert headers == {"X-API-Key": "secret"}
        return DummyResponse(
            200,
            {
                "transactions": [
                    {
                        "id": 1001,
                        "date": "2024-05-01",
                        "amount": "10.00",
                        "description": "Nuevo",
                        "notes": "",
                    }
                ],
                "transaction_events": [
                    _build_transaction_event(
                        "created",
                        1001,
                        {
                            "id": 1001,
                            "date": "2024-05-01",
                            "amount": "10.00",
                            "description": "Nuevo",
                            "notes": "",
                        },
                    )
                ],
                "transactions_checkpoint_id": 1001,
                "last_confirmed_transaction_id": None,
                "changes": [],
                "changes_checkpoint_id": None,
                "last_confirmed_change_id": None,
            },
        )

    monkeypatch.setattr(httpx, "get", fake_get)

    ack_called = False

    def fake_ack(*args, **kwargs):
        nonlocal ack_called
        ack_called = True
        return {}

    monkeypatch.setattr(
        transactions_module,
        "_acknowledge_billing_checkpoint",
        fake_ack,
    )

    with db.SessionLocal() as session:
        account = Account(
            name="Cuenta facturación",
            opening_balance=Decimal("0"),
            currency=Currency.ARS,
            color="#000000",
            is_active=True,
            is_billing=True,
        )
        session.add(account)
        session.commit()

        original_commit = session.commit

        def failing_commit():
            from sqlalchemy.exc import IntegrityError

            raise IntegrityError("SYNC", {}, Exception("fail"))

        monkeypatch.setattr(session, "commit", failing_commit)

        with pytest.raises(HTTPException) as exc_info:
            sync_billing_transactions(limit=1, db=session)

        assert exc_info.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert not ack_called

        monkeypatch.setattr(session, "commit", original_commit)

        session.refresh(account)
        assert account.billing_last_transactions_checkpoint_id is None
        assert account.billing_last_transactions_confirmed_id is None
        assert account.billing_last_changes_checkpoint_id is None
        assert account.billing_last_changes_confirmed_id is None


def test_sync_billing_transactions_keeps_events_when_ack_fails(monkeypatch):
    os.environ["FACTURACION_RUTA_DATA"] = "https://facturacion.example/api/movimientos_cuenta_facturada"
    os.environ["BILLING_API_KEY"] = "secret"

    def fake_get(url, params=None, headers=None, timeout=None):
        assert headers == {"X-API-Key": "secret"}
        return DummyResponse(
            200,
            {
                "transactions": [],
                "transaction_events": [
                    _build_transaction_event(
                        "created",
                        2001,
                        {
                            "id": 2001,
                            "date": "2024-05-02",
                            "amount": "120.00",
                            "description": "Nuevo movimiento",
                            "notes": "",
                        },
                    )
                ],
                "transactions_checkpoint_id": 2001,
                "last_confirmed_transaction_id": 1500,
                "changes": [],
                "changes_checkpoint_id": None,
                "last_confirmed_change_id": None,
            },
        )

    monkeypatch.setattr(httpx, "get", fake_get)

    def failing_ack(*_args, **_kwargs):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="ack failed",
        )

    monkeypatch.setattr(
        transactions_module,
        "_acknowledge_billing_checkpoint",
        failing_ack,
    )

    with db.SessionLocal() as session:
        account = Account(
            name="Cuenta facturación",
            opening_balance=Decimal("0"),
            currency=Currency.ARS,
            color="#000000",
            is_active=True,
            is_billing=True,
        )
        session.add(account)
        session.commit()

        with pytest.raises(HTTPException) as exc_info:
            sync_billing_transactions(limit=1, db=session)

        assert exc_info.value.status_code == status.HTTP_502_BAD_GATEWAY

        stored_tx = session.scalar(
            select(Transaction).where(Transaction.billing_transaction_id == 2001)
        )
        assert stored_tx is not None

        session.refresh(account)
        assert account.billing_last_transactions_checkpoint_id is None
        assert account.billing_last_transactions_confirmed_id == 1500
        assert account.billing_last_changes_checkpoint_id is None
        assert account.billing_last_changes_confirmed_id is None


def test_sync_billing_transactions_preserves_existing_notes_when_missing(monkeypatch):
    os.environ["FACTURACION_RUTA_DATA"] = "https://facturacion.example/api/movimientos_cuenta_facturada"
    os.environ["BILLING_API_KEY"] = "secret"

    def fake_get(url, params=None, headers=None, timeout=None):
        assert headers == {"X-API-Key": "secret"}
        return DummyResponse(
            200,
            {
                "transactions": [],
                "transaction_events": [
                    _build_transaction_event(
                        "updated",
                        800,
                        {
                            "id": 800,
                            "date": "2024-03-10",
                            "amount": "45.67",
                            "description": "Generado",
                        },
                    )
                ],
                "transactions_checkpoint_id": 921,
                "last_confirmed_transaction_id": 910,
                "changes": [],
                "changes_checkpoint_id": 0,
                "last_confirmed_change_id": 0,
            },
        )

    monkeypatch.setattr(httpx, "get", fake_get)
    monkeypatch.setattr(httpx, "post", lambda *_args, **_kwargs: DummyResponse(200, {}))

    with db.SessionLocal() as session:
        account = Account(
            name="Cuenta facturación",
            opening_balance=Decimal("0"),
            currency=Currency.ARS,
            color="#000000",
            is_active=True,
            is_billing=True,
        )
        session.add(account)
        session.flush()

        session.add(
            Transaction(
                account_id=account.id,
                date=date(2024, 3, 1),
                description="Previo",
                amount=Decimal("45.67"),
                notes="Notas previas",
                billing_transaction_id=800,
            )
        )
        session.commit()

        result = sync_billing_transactions(limit=1, db=session)

        updated_tx = session.scalar(
            select(Transaction).where(Transaction.billing_transaction_id == 800)
        )
        assert updated_tx is not None
        assert updated_tx.description == "Generado"
        assert updated_tx.notes == "Notas previas"
        assert result["modificados"] == 1


def test_sync_billing_transactions_requires_description(monkeypatch):
    os.environ["FACTURACION_RUTA_DATA"] = "https://facturacion.example/api/movimientos_cuenta_facturada"
    os.environ["BILLING_API_KEY"] = "secret"

    def fake_get(url, params=None, headers=None, timeout=None):
        assert headers == {"X-API-Key": "secret"}
        return DummyResponse(
            200,
            {
                "transactions": [],
                "transaction_events": [
                    _build_transaction_event(
                        "created",
                        900,
                        {
                            "id": 900,
                            "date": "2024-04-01",
                            "amount": "99.99",
                        },
                    )
                ],
                "transactions_checkpoint_id": 930,
                "last_confirmed_transaction_id": 920,
                "changes": [],
                "changes_checkpoint_id": 0,
                "last_confirmed_change_id": 0,
            },
        )

    monkeypatch.setattr(httpx, "get", fake_get)
    monkeypatch.setattr(httpx, "post", lambda *_args, **_kwargs: DummyResponse(200, {}))

    with db.SessionLocal() as session:
        account = Account(
            name="Cuenta facturación",
            opening_balance=Decimal("0"),
            currency=Currency.ARS,
            color="#000000",
            is_active=True,
            is_billing=True,
        )
        session.add(account)
        session.commit()

        with pytest.raises(HTTPException) as exc_info:
            sync_billing_transactions(limit=1, db=session)

        assert exc_info.value.status_code == status.HTTP_502_BAD_GATEWAY


def test_sync_billing_transactions_fails_when_deleting_missing_transaction(monkeypatch):
    os.environ["FACTURACION_RUTA_DATA"] = "https://facturacion.example/api/movimientos_cuenta_facturada"
    os.environ["BILLING_API_KEY"] = "secret"

    def fake_get(url, params=None, headers=None, timeout=None):
        assert headers == {"X-API-Key": "secret"}
        return DummyResponse(
            200,
            {
                "transactions": [],
                "transaction_events": [
                    _build_transaction_event("deleted", 1234, None)
                ],
                "transactions_checkpoint_id": 910,
                "last_confirmed_transaction_id": 900,
                "changes": [],
                "changes_checkpoint_id": 910,
                "last_confirmed_change_id": 900,
            },
        )

    monkeypatch.setattr(httpx, "get", fake_get)
    monkeypatch.setattr(
        httpx,
        "post",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("ack no esperado")),
    )

    with db.SessionLocal() as session:
        account = Account(
            name="Cuenta facturación",
            opening_balance=Decimal("0"),
            currency=Currency.ARS,
            color="#000000",
            is_active=True,
            is_billing=True,
        )
        account.billing_last_transactions_checkpoint_id = 800
        session.add(account)
        session.commit()

        with pytest.raises(HTTPException) as exc_info:
            sync_billing_transactions(limit=100, db=session)

        assert exc_info.value.status_code == status.HTTP_502_BAD_GATEWAY

        session.refresh(account)
        assert account.billing_last_transactions_checkpoint_id == 800
        assert account.billing_last_transactions_confirmed_id is None


def test_sync_billing_transactions_requires_billing_account(monkeypatch):
    os.environ["FACTURACION_RUTA_DATA"] = "https://facturacion.example/api/movimientos_cuenta_facturada"
    os.environ["BILLING_API_KEY"] = "secret"

    monkeypatch.setattr(
        httpx,
        "get",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("GET no esperado")),
    )

    with db.SessionLocal() as session:
        with pytest.raises(HTTPException) as exc_info:
            sync_billing_transactions(limit=1, db=session)

        assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND
