import asyncio
import json
import os
import sys
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete

BASE_DIR = Path(__file__).resolve().parents[1]
APP_DIR = BASE_DIR / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

os.environ.setdefault("DATABASE_URL", "sqlite+pysqlite:///:memory:")
os.environ.setdefault("DB_SCHEMA", "")
os.environ.setdefault("NOTIF_SHARED_SECRET", "test-secret")
os.environ.setdefault("NOTIF_SOURCE_APP", "app-a")
os.environ.setdefault("PEER_BASE_URL", "https://peer.example.com")

from auth import hash_password  # noqa: E402
from config.db import SessionLocal  # noqa: E402
from main import app  # noqa: E402
from models import (  # noqa: E402
    Notification,
    NotificationPriority,
    NotificationStatus,
    User,
)
from services.notifications import (  # noqa: E402
    compute_signature,
    require_shared_secret,
    send_notification,
)


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        with SessionLocal() as session:
            session.execute(delete(Notification))
            session.execute(delete(User))
            session.commit()
        yield test_client
        with SessionLocal() as session:
            session.execute(delete(Notification))
            session.execute(delete(User))
            session.commit()


def _prepare_signed_headers(
    body: dict[str, object], *, idempotency_key: str, timestamp: str
) -> tuple[dict[str, str], str]:
    body_text = json.dumps(body, separators=(",", ":"), ensure_ascii=False)
    signature = compute_signature(require_shared_secret(), timestamp, body_text.encode("utf-8"))
    return {
        "Content-Type": "application/json",
        "X-Timestamp": timestamp,
        "X-Idempotency-Key": idempotency_key,
        "X-Source-App": "app-b",
        "X-Signature": signature,
    }, body_text


def _create_user(username: str, password: str) -> User:
    with SessionLocal() as session:
        user = User(
            username=username,
            email=f"{username}@example.com",
            password_hash=hash_password(password),
            is_active=True,
        )
        session.add(user)
        session.commit()
        session.refresh(user)
        return user


def _get_notification(notification_id: uuid.UUID) -> Notification:
    with SessionLocal() as session:
        notification = session.get(Notification, notification_id)
        assert notification is not None
        return notification


def test_inbound_notification_is_persisted(client):
    payload = {
        "type": "ventas.presupuesto_creado.v1",
        "occurred_at": datetime.now(timezone.utc).isoformat(),
        "title": "Nuevo presupuesto",
        "body": "Se creó un presupuesto",
        "topic": "ventas",
    }
    idempotency_key = str(uuid.uuid4())
    timestamp = str(int(time.time()))
    headers, body_text = _prepare_signed_headers(payload, idempotency_key=idempotency_key, timestamp=timestamp)

    response = client.post("/notificaciones", data=body_text, headers=headers)
    assert response.status_code == 202
    data = response.json()
    assert data["status"] == "accepted"
    assert data["dedup"] is False

    stored = _get_notification(uuid.UUID(data["id"]))
    assert stored.type == payload["type"]
    assert stored.topic == "ventas"
    assert stored.status == NotificationStatus.UNREAD
    assert stored.idempotency_key == idempotency_key
    assert stored.source_app == "app-b"


def test_inbound_notification_is_idempotent(client):
    payload = {
        "type": "ventas.presupuesto_creado.v1",
        "occurred_at": datetime.now(timezone.utc).isoformat(),
        "title": "Nuevo presupuesto",
        "body": "Se creó un presupuesto",
    }
    idempotency_key = str(uuid.uuid4())
    timestamp = str(int(time.time()))
    headers, body_text = _prepare_signed_headers(payload, idempotency_key=idempotency_key, timestamp=timestamp)

    first = client.post("/notificaciones", data=body_text, headers=headers)
    assert first.status_code == 202
    second = client.post("/notificaciones", data=body_text, headers=headers)
    assert second.status_code == 202
    assert second.json()["dedup"] is True


def test_inbound_notification_validates_signature(client):
    payload = {
        "type": "ventas.presupuesto_creado.v1",
        "occurred_at": datetime.now(timezone.utc).isoformat(),
        "title": "Nuevo presupuesto",
        "body": "Se creó un presupuesto",
    }
    idempotency_key = str(uuid.uuid4())
    timestamp = str(int(time.time()))
    _, body_text = _prepare_signed_headers(payload, idempotency_key=idempotency_key, timestamp=timestamp)
    headers = {
        "Content-Type": "application/json",
        "X-Timestamp": timestamp,
        "X-Idempotency-Key": idempotency_key,
        "X-Source-App": "app-b",
        "X-Signature": "sha256=invalid",
    }

    response = client.post("/notificaciones", data=body_text, headers=headers)
    assert response.status_code == 401
    assert response.json()["detail"] == "Firma inválida"


def test_inbound_notification_rejects_old_timestamp(client):
    payload = {
        "type": "ventas.presupuesto_creado.v1",
        "occurred_at": datetime.now(timezone.utc).isoformat(),
        "title": "Nuevo presupuesto",
        "body": "Se creó un presupuesto",
    }
    idempotency_key = str(uuid.uuid4())
    timestamp = str(int(time.time()) - 1000)
    headers, body_text = _prepare_signed_headers(payload, idempotency_key=idempotency_key, timestamp=timestamp)

    response = client.post("/notificaciones", data=body_text, headers=headers)
    assert response.status_code == 401
    assert response.json()["detail"] == "Timestamp inválido"


def test_acknowledge_notification_marks_as_read(client):
    payload = {
        "type": "ventas.presupuesto_creado.v1",
        "occurred_at": datetime.now(timezone.utc).isoformat(),
        "title": "Nuevo presupuesto",
        "body": "Se creó un presupuesto",
    }
    idempotency_key = str(uuid.uuid4())
    timestamp = str(int(time.time()))
    headers, body_text = _prepare_signed_headers(payload, idempotency_key=idempotency_key, timestamp=timestamp)
    response = client.post("/notificaciones", data=body_text, headers=headers)
    notification_id = response.json()["id"]

    username = "testuser"
    password = "secret"
    _create_user(username, password)
    login = client.post("/login", data={"username": username, "password": password}, follow_redirects=False)
    assert login.status_code == 302

    ack_response = client.post("/notificaciones", json={"action": "ack", "id": notification_id})
    assert ack_response.status_code == 200
    assert ack_response.json() == {"status": "ok"}

    stored = _get_notification(uuid.UUID(notification_id))
    assert stored.status == NotificationStatus.READ
    assert stored.read_at is not None


def test_list_notifications_supports_filters_and_pagination(client):
    now = datetime.now(timezone.utc)
    notifications = [
        Notification(
            type="ventas.presupuesto_creado.v1",
            title="N1",
            body="Body",
            occurred_at=now - timedelta(minutes=1),
            topic="ventas",
            priority=NotificationPriority.NORMAL,
            idempotency_key=str(uuid.uuid4()),
            source_app="app-b",
        ),
        Notification(
            type="ventas.presupuesto_creado.v1",
            title="N2",
            body="Body",
            occurred_at=now - timedelta(minutes=2),
            topic="ventas",
            priority=NotificationPriority.HIGH,
            status=NotificationStatus.READ,
            read_at=now - timedelta(minutes=1),
            idempotency_key=str(uuid.uuid4()),
            source_app="app-b",
        ),
        Notification(
            type="ventas.presupuesto_creado.v1",
            title="N4",
            body="Body",
            occurred_at=now - timedelta(minutes=3),
            topic="ventas",
            idempotency_key=str(uuid.uuid4()),
            source_app="app-b",
        ),
        Notification(
            type="ventas.factura_emitida.v1",
            title="N3",
            body="Body",
            occurred_at=now,
            topic="facturacion",
            idempotency_key=str(uuid.uuid4()),
            source_app="app-b",
        ),
    ]
    with SessionLocal() as session:
        session.execute(delete(Notification))
        for item in notifications:
            session.add(item)
        session.commit()

    username = "viewer"
    password = "secret"
    _create_user(username, password)
    login = client.post("/login", data={"username": username, "password": password}, follow_redirects=False)
    assert login.status_code == 302

    response = client.get("/notificaciones", params={"limit": 2, "include": "unread_count"})
    assert response.status_code == 200
    data = response.json()
    assert len(data["items"]) == 2
    assert data["unread_count"] == 3
    assert data["items"][0]["occurred_at"] >= data["items"][1]["occurred_at"]
    assert data["cursor"] is not None

    next_page = client.get(
        "/notificaciones",
        params={"limit": 2, "cursor": data["cursor"], "status": "all", "topic": "ventas"},
    )
    assert next_page.status_code == 200
    next_data = next_page.json()
    assert all(item["topic"] == "ventas" for item in next_data["items"])


def test_send_notification_builds_signed_request():
    captured: dict[str, object] = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["headers"] = request.headers
        captured["body"] = request.content
        return httpx.Response(202, json={"status": "accepted"})

    transport = httpx.MockTransport(handler)
    async def _run() -> None:
        async with httpx.AsyncClient(transport=transport) as http_client:
            response = await send_notification(
                {"type": "ventas.presupuesto_creado.v1", "title": "Hola", "body": "Mensaje"},
                client=http_client,
            )
        captured["status"] = response.status_code

    asyncio.run(_run())
    assert captured["status"] == 202

    assert captured["url"] == "https://peer.example.com/notificaciones"
    headers: httpx.Headers = captured["headers"]  # type: ignore[assignment]
    assert headers.get("content-type") == "application/json"
    idempotency_key = headers.get("x-idempotency-key")
    assert idempotency_key is not None
    uuid.UUID(idempotency_key)
    secret = require_shared_secret()
    timestamp = headers.get("x-timestamp")
    assert timestamp is not None
    expected_signature = compute_signature(secret, timestamp, captured["body"])
    assert headers.get("x-signature") == expected_signature

    payload = json.loads(captured["body"].decode("utf-8"))
    assert "occurred_at" in payload
