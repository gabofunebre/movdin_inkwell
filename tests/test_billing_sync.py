import os
import sys
from datetime import date
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


class DummyHttpxClient:
    def __init__(self, responses):
        self._responses = iter(responses)
        self.calls = []

    def get(self, url, params=None, headers=None):
        self.calls.append({"url": url, "params": params, "headers": headers})
        status_code, payload = next(self._responses)
        return DummyResponse(status_code, payload)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):  # pragma: no cover - no cleanup needed
        return False


def test_sync_billing_transactions_applies_events_and_acknowledges_checkpoint(monkeypatch):
    os.environ["FACTURACION_RUTA_DATA"] = "https://facturacion.example/api"
    os.environ["BILLING_API_KEY"] = "secret"

    responses = [
        (
            200,
            {
                "changes": [
                    {
                        "id": 901,
                        "movement_id": 501,
                        "event": "created",
                        "occurred_at": "2024-01-03T10:00:00.000000+00:00",
                        "payload": {
                            "id": 501,
                            "date": "2024-01-03",
                            "amount": "150.50",
                            "description": "Alta",
                            "notes": "Creado",
                        },
                    },
                    {
                        "id": 902,
                        "movement_id": 600,
                        "event": "updated",
                        "occurred_at": "2024-01-03T11:00:00.000000+00:00",
                        "payload": {
                            "id": 600,
                            "date": "2024-01-02",
                            "amount": "200.00",
                            "description": "Actualizada",
                            "notes": "Modificada",
                            "previous_description": "Original",
                        },
                    },
                    {
                        "id": 903,
                        "movement_id": 700,
                        "event": "deleted",
                        "occurred_at": "2024-01-03T12:00:00.000000+00:00",
                        "payload": {
                            "id": 700,
                            "description": "A borrar",
                            "deleted": True,
                        },
                    },
                ],
                "checkpoint_id": 903,
                "last_confirmed_id": 850,
                "has_more": False,
            },
        )
    ]

    dummy_client = DummyHttpxClient(responses)

    def client_factory(*_args, **_kwargs):
        return dummy_client

    monkeypatch.setattr(httpx, "Client", client_factory)

    ack_calls = {}

    def fake_post(url, json, headers, timeout):
        ack_calls.update({
            "url": url,
            "json": json,
            "headers": headers,
            "timeout": timeout,
        })
        return DummyResponse(
            200,
            {
                "last_change_id": 903,
                "updated_at": "2024-01-04T10:00:00Z",
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

        account.billing_last_confirmed_id = 850

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

        result = sync_billing_transactions(limit=2, db=session)

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
        assert account.billing_last_checkpoint_id == 903
        assert account.billing_last_confirmed_id == 903
        synced_at = account.billing_synced_at
        assert synced_at is not None
        assert synced_at.isoformat().startswith("2024-01-04T10:00:00")

        assert result["nuevos"] == 1
        assert result["modificados"] == 1
        assert result["eliminados"] == 1
        assert (
            result["message"]
            == "Se sincronizaron 1 movimiento nuevo, 1 movimiento modificado, 1 movimiento eliminado."
        )

    assert dummy_client.calls
    assert dummy_client.calls[0]["params"] == {"limit": 2, "since": 850}
    assert ack_calls["json"] == {"checkpoint_id": 903}
    assert ack_calls["url"].endswith("/movimientos_exportables/cambios/ack")


def test_sync_billing_transactions_fetches_missing_fields(monkeypatch):
    os.environ["FACTURACION_RUTA_DATA"] = "https://facturacion.example/api"
    os.environ["BILLING_API_KEY"] = "secret"

    responses = [
        (
            200,
            {
                "changes": [
                    {
                        "id": 905,
                        "movement_id": 501,
                        "event": "created",
                        "occurred_at": "2024-02-01T09:00:00.000000+00:00",
                        "payload": {
                            "id": 501,
                            "description": "Solo descripción",
                        },
                    }
                ],
                "checkpoint_id": 905,
                "last_confirmed_id": 900,
                "has_more": False,
            },
        )
    ]

    dummy_client = DummyHttpxClient(responses)
    monkeypatch.setattr(httpx, "Client", lambda *_args, **_kwargs: dummy_client)

    detail_calls: list[dict] = []

    def fake_get(url, headers=None, timeout=None):
        detail_calls.append({"url": url, "headers": headers, "timeout": timeout})
        return DummyResponse(
            200,
            {
                "transaction": {
                    "id": 501,
                    "date": "2024-02-01",
                    "amount": "123.45",
                    "description": "Solo descripción",
                }
            },
        )

    monkeypatch.setattr(httpx, "get", fake_get)

    def fake_post(url, json, headers, timeout):
        return DummyResponse(200, {"last_change_id": 905})

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
        session.commit()

        result = sync_billing_transactions(limit=10, db=session)

        created_tx = session.scalar(
            select(Transaction).where(Transaction.billing_transaction_id == 501)
        )
        assert created_tx is not None
        assert created_tx.date == date(2024, 2, 1)
        assert created_tx.amount == Decimal("123.45")
        assert created_tx.description == "Solo descripción"

        assert result["nuevos"] == 1
        session.refresh(account)
        assert account.billing_last_checkpoint_id == 905
        assert account.billing_last_confirmed_id == 905

    assert detail_calls
    assert detail_calls[0]["url"].endswith("/movimientos_exportables/501")
    assert detail_calls[0]["headers"] == {"X-API-Key": "secret"}


def test_sync_billing_transactions_uses_detail_notes_and_preserves_existing(monkeypatch):
    os.environ["FACTURACION_RUTA_DATA"] = "https://facturacion.example/api"
    os.environ["BILLING_API_KEY"] = "secret"

    responses = [
        (
            200,
            {
                "changes": [
                    {
                        "id": 920,
                        "movement_id": 800,
                        "event": "created",
                        "occurred_at": "2024-03-10T09:00:00.000000+00:00",
                        "payload": {
                            "id": 800,
                            "date": "2024-03-10",
                            "amount": "45.67",
                            "description": "Generado sin notas",
                        },
                    },
                    {
                        "id": 921,
                        "movement_id": 801,
                        "event": "updated",
                        "occurred_at": "2024-03-10T10:00:00.000000+00:00",
                        "payload": {
                            "id": 801,
                            "date": "2024-03-09",
                            "amount": "89.10",
                            "description": "Cambio sin notas",
                        },
                    },
                ],
                "checkpoint_id": 921,
                "last_confirmed_id": 910,
                "has_more": False,
            },
        )
    ]

    dummy_client = DummyHttpxClient(responses)
    monkeypatch.setattr(httpx, "Client", lambda *_args, **_kwargs: dummy_client)

    detail_calls: list[dict] = []

    def fake_get(url, headers=None, timeout=None):
        detail_calls.append({"url": url, "headers": headers, "timeout": timeout})
        if url.endswith("/800"):
            return DummyResponse(
                200,
                {
                    "transaction": {
                        "id": 800,
                        "date": "2024-03-10",
                        "amount": "45.67",
                        "description": "Generado sin notas",
                        "notes": "Notas del detalle",
                    }
                },
            )
        if url.endswith("/801"):
            return DummyResponse(
                200,
                {
                    "transaction": {
                        "id": 801,
                        "date": "2024-03-09",
                        "amount": "89.10",
                        "description": "Cambio sin notas",
                    }
                },
            )
        raise AssertionError("detalle inesperado")

    monkeypatch.setattr(httpx, "get", fake_get)
    monkeypatch.setattr(httpx, "post", lambda *_args, **_kwargs: DummyResponse(200, {"last_change_id": 921}))

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
                amount=Decimal("89.10"),
                notes="Notas previas",
                billing_transaction_id=801,
            )
        )
        session.commit()

        result = sync_billing_transactions(limit=5, db=session)

        created_tx = session.scalar(
            select(Transaction).where(Transaction.billing_transaction_id == 800)
        )
        assert created_tx is not None
        assert created_tx.notes == "Notas del detalle"
        assert created_tx.description == "Generado sin notas"

        updated_tx = session.scalar(
            select(Transaction).where(Transaction.billing_transaction_id == 801)
        )
        assert updated_tx is not None
        assert updated_tx.description == "Cambio sin notas"
        assert updated_tx.notes == "Notas previas"

        assert result["nuevos"] == 1
        assert result["modificados"] == 1

    assert len(detail_calls) == 2
    assert detail_calls[0]["headers"] == {"X-API-Key": "secret"}
    assert detail_calls[1]["headers"] == {"X-API-Key": "secret"}

def test_sync_billing_transactions_fails_when_deleting_missing_transaction(monkeypatch):
    os.environ["FACTURACION_RUTA_DATA"] = "https://facturacion.example/api"
    os.environ["BILLING_API_KEY"] = "secret"

    responses = [
        (
            200,
            {
                "changes": [
                    {
                        "id": 910,
                        "movement_id": 1234,
                        "event": "deleted",
                        "occurred_at": "2024-01-05T08:00:00.000000+00:00",
                        "payload": {
                            "id": 1234,
                            "description": "Desconocido",
                            "deleted": True,
                        },
                    }
                ],
                "checkpoint_id": 910,
                "last_confirmed_id": 900,
                "has_more": False,
            },
        )
    ]

    dummy_client = DummyHttpxClient(responses)
    monkeypatch.setattr(httpx, "Client", lambda *_args, **_kwargs: dummy_client)
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
            billing_last_checkpoint_id=800,
        )
        session.add(account)
        session.commit()

        with pytest.raises(HTTPException) as exc_info:
            sync_billing_transactions(limit=100, db=session)

        assert exc_info.value.status_code == status.HTTP_502_BAD_GATEWAY

        session.refresh(account)
        assert account.billing_last_checkpoint_id == 800
        assert account.billing_last_confirmed_id is None

    assert dummy_client.calls
