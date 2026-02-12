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
from models import Account, BillingTransactionSyncState, Transaction  # noqa: E402
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
        assert updated_tx.description == "Original"
        assert updated_tx.amount == Decimal("200.00")
        assert updated_tx.notes == "Modificada"

        deleted_tx = session.scalar(
            select(Transaction).where(Transaction.billing_transaction_id == 700)
        )
        assert deleted_tx is None

        created_state = session.get(BillingTransactionSyncState, 501)
        assert created_state is not None
        assert created_state.exportable_movement_id is None
        assert created_state.is_custom_inkwell is False
        assert created_state.status == "unavailable"

        updated_state = session.get(BillingTransactionSyncState, 600)
        assert updated_state is not None
        assert updated_state.status == "unavailable"

        deleted_state = session.get(BillingTransactionSyncState, 700)
        assert deleted_state is not None
        assert deleted_state.status == "unavailable"

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


def test_sync_billing_transactions_handles_create_update_delete_sequence(monkeypatch):
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
                        4000,
                        {
                            "id": 4000,
                            "date": "2024-06-10",
                            "amount": "90.00",
                            "description": "Movimiento creado",
                            "notes": "Inicial",
                        },
                    ),
                    _build_transaction_event(
                        "updated",
                        4000,
                        {
                            "id": 4000,
                            "date": "2024-06-11",
                            "amount": "95.00",
                            "description": "Movimiento actualizado",
                            "notes": "Actualizado",
                        },
                    ),
                    _build_transaction_event("deleted", 4000, None),
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

        result = sync_billing_transactions(limit=3, db=session)

        stored_tx = session.scalar(
            select(Transaction).where(Transaction.billing_transaction_id == 4000)
        )
        assert stored_tx is None
        assert result["nuevos"] == 1
        assert result["modificados"] == 1
        assert result["eliminados"] == 1


def test_sync_billing_transactions_ignores_events_after_delete(monkeypatch):
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
                        4100,
                        {
                            "id": 4100,
                            "date": "2024-06-15",
                            "amount": "120.00",
                            "description": "Movimiento creado",
                            "notes": "Inicial",
                        },
                    ),
                    _build_transaction_event("deleted", 4100, None),
                    _build_transaction_event(
                        "updated",
                        4100,
                        {
                            "id": 4100,
                            "date": "2024-06-16",
                            "amount": "130.00",
                            "description": "Movimiento resucitado",
                            "notes": "Ignorar",
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

        result = sync_billing_transactions(limit=3, db=session)

        stored_tx = session.scalar(
            select(Transaction).where(Transaction.billing_transaction_id == 4100)
        )
        assert stored_tx is None
        assert result["nuevos"] == 1
        assert result["modificados"] == 0
        assert result["eliminados"] == 1


def test_sync_billing_transactions_applies_last_update_for_existing(monkeypatch):
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
                        4200,
                        {
                            "id": 4200,
                            "date": "2024-06-20",
                            "amount": "60.00",
                            "description": "Primer update",
                            "notes": "Paso 1",
                        },
                    ),
                    _build_transaction_event(
                        "updated",
                        4200,
                        {
                            "id": 4200,
                            "date": "2024-06-21",
                            "amount": "65.00",
                            "description": "Último update",
                            "notes": "Paso final",
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
        session.flush()

        existing_tx = Transaction(
            account_id=account.id,
            date=date(2024, 6, 19),
            description="Original",
            amount=Decimal("55.00"),
            notes="Previo",
            billing_transaction_id=4200,
        )
        session.add(existing_tx)
        session.commit()

        result = sync_billing_transactions(limit=2, db=session)

        updated_tx = session.scalar(
            select(Transaction).where(Transaction.billing_transaction_id == 4200)
        )
        assert updated_tx is not None
        assert updated_tx.date == date(2024, 6, 21)
        assert updated_tx.amount == Decimal("65.00")
        assert updated_tx.description == "Original"
        assert updated_tx.notes == "Paso final"

        assert result["nuevos"] == 0
        assert result["modificados"] == 2
        assert result["eliminados"] == 0


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
        assert updated_tx.description == "Previo"
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


def test_sync_billing_transactions_is_idempotent_for_repeated_event_batch(monkeypatch):
    os.environ["FACTURACION_RUTA_DATA"] = "https://facturacion.example/api/movimientos_cuenta_facturada"
    os.environ["BILLING_API_KEY"] = "secret"

    def fake_get(url, params=None, headers=None, timeout=None):
        assert headers == {"X-API-Key": "secret"}
        return DummyResponse(
            200,
            {
                "transactions": [],
                "transaction_events": [
                    {
                        "id": 700,
                        "event": "created",
                        "transaction_id": 6600,
                        "transaction": {
                            "id": 6600,
                            "date": "2024-07-10",
                            "amount": "21.00",
                            "description": "Creado",
                            "notes": "",
                            "exportable_movement_id": 500,
                            "is_custom_inkwell": False,
                        },
                    },
                    {
                        "id": 701,
                        "event": "updated",
                        "transaction_id": 6600,
                        "transaction": {
                            "id": 6600,
                            "date": "2024-07-11",
                            "amount": "22.00",
                            "description": "Actualizado",
                            "notes": "",
                            "exportable_movement_id": None,
                            "is_custom_inkwell": False,
                        },
                    },
                    _build_transaction_event("deleted", 6600, None),
                ],
                "transactions_checkpoint_id": 910,
                "last_confirmed_transaction_id": 900,
                "changes": [],
                "changes_checkpoint_id": 910,
                "last_confirmed_change_id": 900,
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

        first = sync_billing_transactions(limit=100, db=session)
        state_after_first = session.get(BillingTransactionSyncState, 6600)
        tx_after_first = session.scalar(select(Transaction).where(Transaction.billing_transaction_id == 6600))

        second = sync_billing_transactions(limit=100, db=session)
        state_after_second = session.get(BillingTransactionSyncState, 6600)
        tx_after_second = session.scalar(select(Transaction).where(Transaction.billing_transaction_id == 6600))

        assert tx_after_first is None
        assert tx_after_second is None
        assert state_after_first is not None
        assert state_after_second is not None
        assert first["transactions_checkpoint_id"] == second["transactions_checkpoint_id"]
        assert first["transactions_confirmed_id"] == second["transactions_confirmed_id"]
        assert state_after_first.status == state_after_second.status == "unavailable"
        assert state_after_first.updated_at_event_id == state_after_second.updated_at_event_id == 6600


def test_sync_billing_transactions_fails_when_deleting_missing_transaction(monkeypatch):
    os.environ["FACTURACION_RUTA_DATA"] = "https://facturacion.example/api/movimientos_cuenta_facturada"
    os.environ["BILLING_API_KEY"] = "secret"

    ack_called = False
    commits_seen = 0

    def fake_get(url, params=None, headers=None, timeout=None):
        assert headers == {"X-API-Key": "secret"}
        return DummyResponse(
            200,
            {
                "transactions": [],
                "transaction_events": [_build_transaction_event("deleted", 1234, None)],
                "transactions_checkpoint_id": 910,
                "last_confirmed_transaction_id": 900,
                "changes": [],
                "changes_checkpoint_id": 910,
                "last_confirmed_change_id": 900,
            },
        )

    monkeypatch.setattr(httpx, "get", fake_get)

    def fake_ack(*_args, **_kwargs):
        nonlocal ack_called
        assert commits_seen >= 1
        ack_called = True
        return {}

    monkeypatch.setattr(transactions_module, "_acknowledge_billing_checkpoint", fake_ack)

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

        def tracked_commit():
            nonlocal commits_seen
            commits_seen += 1
            return original_commit()

        monkeypatch.setattr(session, "commit", tracked_commit)

        result = sync_billing_transactions(limit=100, db=session)

        assert ack_called
        assert result["nuevos"] == 0
        assert result["modificados"] == 0
        assert result["eliminados"] == 0

        stored_tx = session.scalar(select(Transaction).where(Transaction.billing_transaction_id == 1234))
        assert stored_tx is None

        state = session.get(BillingTransactionSyncState, 1234)
        assert state is not None
        assert state.status == "unavailable"
        assert state.updated_at_event_id == 1234


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

def test_sync_billing_transactions_created_event_marks_transaction_available(monkeypatch):
    os.environ["FACTURACION_RUTA_DATA"] = "https://facturacion.example/api/movimientos_cuenta_facturada"
    os.environ["BILLING_API_KEY"] = "secret"

    def fake_get(url, params=None, headers=None, timeout=None):
        assert headers == {"X-API-Key": "secret"}
        return DummyResponse(
            200,
            {
                "transactions": [],
                "transaction_events": [
                    {
                        "id": 100,
                        "event": "created",
                        "transaction_id": 5500,
                        "transaction": {
                            "id": 5500,
                            "date": "2024-07-01",
                            "amount": "15.00",
                            "description": "Creado",
                            "notes": "",
                            "exportable_movement_id": 880,
                            "is_custom_inkwell": False,
                        },
                    }
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

        sync_billing_transactions(limit=1, db=session)

        state = session.get(BillingTransactionSyncState, 5500)
        assert state is not None
        assert state.exportable_movement_id == 880
        assert state.status == "available"


def test_sync_billing_transactions_created_updated_keeps_available_when_exportable(monkeypatch):
    os.environ["FACTURACION_RUTA_DATA"] = "https://facturacion.example/api/movimientos_cuenta_facturada"
    os.environ["BILLING_API_KEY"] = "secret"

    def fake_get(url, params=None, headers=None, timeout=None):
        assert headers == {"X-API-Key": "secret"}
        return DummyResponse(
            200,
            {
                "transactions": [],
                "transaction_events": [
                    {
                        "id": 100,
                        "event": "created",
                        "transaction_id": 5500,
                        "transaction": {
                            "id": 5500,
                            "date": "2024-07-01",
                            "amount": "15.00",
                            "description": "Creado",
                            "notes": "",
                            "exportable_movement_id": 880,
                            "is_custom_inkwell": False,
                        },
                    },
                    {
                        "id": 101,
                        "event": "updated",
                        "transaction_id": 5500,
                        "transaction": {
                            "id": 5500,
                            "date": "2024-07-02",
                            "amount": "16.00",
                            "description": "Update",
                            "notes": "",
                            "exportable_movement_id": 990,
                            "is_custom_inkwell": False,
                        },
                    },
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

        state = session.get(BillingTransactionSyncState, 5500)
        assert state is not None
        assert state.exportable_movement_id == 990
        assert state.status == "available"
        assert state.updated_at_event_id == 101
        assert result["nuevos"] == 1
        assert result["modificados"] == 1


def test_sync_billing_transactions_created_updated_without_exportable_becomes_unavailable(monkeypatch):
    os.environ["FACTURACION_RUTA_DATA"] = "https://facturacion.example/api/movimientos_cuenta_facturada"
    os.environ["BILLING_API_KEY"] = "secret"

    def fake_get(url, params=None, headers=None, timeout=None):
        assert headers == {"X-API-Key": "secret"}
        return DummyResponse(
            200,
            {
                "transactions": [],
                "transaction_events": [
                    {
                        "id": 100,
                        "event": "created",
                        "transaction_id": 5500,
                        "transaction": {
                            "id": 5500,
                            "date": "2024-07-01",
                            "amount": "15.00",
                            "description": "Creado",
                            "notes": "",
                            "exportable_movement_id": 880,
                            "is_custom_inkwell": False,
                        },
                    },
                    {
                        "id": 101,
                        "event": "updated",
                        "transaction_id": 5500,
                        "transaction": {
                            "id": 5500,
                            "date": "2024-07-02",
                            "amount": "16.00",
                            "description": "Update",
                            "notes": "",
                            "exportable_movement_id": None,
                            "is_custom_inkwell": False,
                        },
                    },
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

        sync_billing_transactions(limit=2, db=session)

        state = session.get(BillingTransactionSyncState, 5500)
        assert state is not None
        assert state.exportable_movement_id is None
        assert state.status == "unavailable"


def test_sync_billing_transactions_created_deleted_becomes_unavailable(monkeypatch):
    os.environ["FACTURACION_RUTA_DATA"] = "https://facturacion.example/api/movimientos_cuenta_facturada"
    os.environ["BILLING_API_KEY"] = "secret"

    def fake_get(url, params=None, headers=None, timeout=None):
        assert headers == {"X-API-Key": "secret"}
        return DummyResponse(
            200,
            {
                "transactions": [],
                "transaction_events": [
                    {
                        "id": 100,
                        "event": "created",
                        "transaction_id": 5500,
                        "transaction": {
                            "id": 5500,
                            "date": "2024-07-01",
                            "amount": "15.00",
                            "description": "Creado",
                            "notes": "",
                            "exportable_movement_id": 880,
                            "is_custom_inkwell": False,
                        },
                    },
                    _build_transaction_event("deleted", 5500, None),
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

        sync_billing_transactions(limit=2, db=session)

        state = session.get(BillingTransactionSyncState, 5500)
        assert state is not None
        assert state.status == "unavailable"
        tx = session.scalar(select(Transaction).where(Transaction.billing_transaction_id == 5500))
        assert tx is None


def test_sync_billing_transactions_marks_unavailable_for_custom_inkwell(monkeypatch):
    os.environ["FACTURACION_RUTA_DATA"] = "https://facturacion.example/api/movimientos_cuenta_facturada"
    os.environ["BILLING_API_KEY"] = "secret"

    def fake_get(url, params=None, headers=None, timeout=None):
        assert headers == {"X-API-Key": "secret"}
        return DummyResponse(
            200,
            {
                "transactions": [],
                "transaction_events": [
                    {
                        "id": 300,
                        "event": "created",
                        "transaction_id": 5600,
                        "transaction": {
                            "id": 5600,
                            "date": "2024-07-03",
                            "amount": "20.00",
                            "description": "Custom IW",
                            "notes": "",
                            "exportable_movement_id": 990,
                            "is_custom_inkwell": True,
                        },
                    }
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

        sync_billing_transactions(limit=1, db=session)

        state = session.get(BillingTransactionSyncState, 5600)
        assert state is not None
        assert state.exportable_movement_id == 990
        assert state.is_custom_inkwell is True
        assert state.status == "unavailable"
