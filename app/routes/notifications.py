"""Notification endpoints implementing the shared protocol."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from sqlalchemy import and_, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from auth import get_current_user
from config.db import get_db
from models import Notification, NotificationStatus
from schemas import (
    NotificationAck,
    NotificationListResponse,
    NotificationOut,
    NotificationPayload,
)
from services.notifications import (
    ALLOWED_SOURCE_APPS,
    decode_cursor,
    encode_cursor,
    inbound_rate_limiter,
    require_shared_secret,
    validate_timestamp,
    verify_signature,
)

router = APIRouter(prefix="/notificaciones", tags=["notifications"])


def _ensure_user(user) -> None:
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="No autorizado")


def _normalize_datetime(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


@router.get("", response_model=NotificationListResponse)
def list_notifications(
    status_filter: str = Query("unread", alias="status"),
    since: datetime | None = Query(None),
    topic: str | None = Query(None),
    type_filter: str | None = Query(None, alias="type"),
    limit: int = Query(50, ge=1, le=100),
    cursor: str | None = Query(None),
    include: str | None = Query(None),
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
) -> NotificationListResponse:
    _ensure_user(user)

    filters = []

    if status_filter == "unread":
        filters.append(Notification.status == NotificationStatus.UNREAD)
    elif status_filter == "read":
        filters.append(Notification.status == NotificationStatus.READ)
    elif status_filter != "all":
        raise HTTPException(status_code=400, detail="Parámetro status inválido")

    if since is not None:
        filters.append(Notification.occurred_at >= _normalize_datetime(since))

    if topic:
        filters.append(Notification.topic == topic)

    if type_filter:
        filters.append(Notification.type == type_filter)

    query = (
        select(Notification)
        .where(*filters)
        .order_by(Notification.occurred_at.desc(), Notification.id.desc())
    )

    if cursor:
        try:
            cursor_occurred_at, cursor_id = decode_cursor(cursor)
        except Exception as exc:  # pragma: no cover - invalid cursor branch
            raise HTTPException(status_code=400, detail="Cursor inválido") from exc
        query = query.where(
            or_(
                Notification.occurred_at < cursor_occurred_at,
                and_(
                    Notification.occurred_at == cursor_occurred_at,
                    Notification.id < cursor_id,
                ),
            )
        )

    stmt = query.limit(limit + 1)
    items = db.execute(stmt).scalars().all()
    has_more = len(items) > limit
    items = items[:limit]

    next_cursor: Optional[str] = None
    if has_more and items:
        last_item = items[-1]
        next_cursor = encode_cursor(last_item.occurred_at, last_item.id)

    include_flags = {flag.strip() for flag in include.split(",") if flag} if include else set()

    unread_count: Optional[int] = None
    if "unread_count" in include_flags:
        count_stmt = select(func.count()).select_from(Notification).where(*filters)
        unread_count = db.execute(count_stmt).scalar_one()

    return NotificationListResponse(
        items=[NotificationOut.model_validate(item) for item in items],
        cursor=next_cursor,
        unread_count=unread_count,
    )


@router.post("", status_code=status.HTTP_202_ACCEPTED)
async def create_or_ack_notification(
    request: Request, db: Session = Depends(get_db), user=Depends(get_current_user)
):
    body_bytes = await request.body()
    content_type = request.headers.get("content-type", "")
    if "application/json" not in content_type.lower():
        raise HTTPException(status_code=415, detail="Content-Type inválido")

    try:
        raw_text = body_bytes.decode("utf-8") if body_bytes else "{}"
        payload = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="JSON inválido") from exc

    signature = request.headers.get("X-Signature")

    if signature:
        timestamp_header = request.headers.get("X-Timestamp")
        idempotency_key = request.headers.get("X-Idempotency-Key")
        source_app = request.headers.get("X-Source-App")

        if not (timestamp_header and idempotency_key and source_app):
            raise HTTPException(status_code=400, detail="Headers faltantes")

        if source_app not in ALLOWED_SOURCE_APPS:
            raise HTTPException(status_code=401, detail="Source app inválida")

        try:
            validate_timestamp(timestamp_header)
        except ValueError as exc:
            raise HTTPException(status_code=401, detail="Timestamp inválido") from exc

        if not inbound_rate_limiter.check_and_increment(source_app):
            raise HTTPException(status_code=429, detail="Rate limit excedido")

        secret = require_shared_secret()
        if not verify_signature(secret, timestamp_header, body_bytes, signature):
            raise HTTPException(status_code=401, detail="Firma inválida")

        try:
            UUID(idempotency_key)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="Idempotency key inválida") from exc

        existing = (
            db.execute(
                select(Notification).where(Notification.idempotency_key == idempotency_key)
            )
            .scalars()
            .first()
        )
        if existing:
            return JSONResponse(
                status_code=status.HTTP_202_ACCEPTED,
                content={"status": "accepted", "id": str(existing.id), "dedup": True},
            )

        try:
            payload_model = NotificationPayload.model_validate(payload)
        except ValidationError as exc:
            raise HTTPException(status_code=422, detail=exc.errors()) from exc

        notification = Notification(
            type=payload_model.type,
            title=payload_model.title,
            body=payload_model.body,
            deeplink=payload_model.deeplink,
            topic=payload_model.topic,
            priority=payload_model.priority,
            occurred_at=_normalize_datetime(payload_model.occurred_at),
            status=NotificationStatus.UNREAD,
            variables=payload_model.variables,
            idempotency_key=idempotency_key,
            source_app=source_app,
        )
        db.add(notification)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            existing = (
                db.execute(
                    select(Notification).where(Notification.idempotency_key == idempotency_key)
                )
                .scalars()
                .first()
            )
            if existing:
                return JSONResponse(
                    status_code=status.HTTP_202_ACCEPTED,
                    content={"status": "accepted", "id": str(existing.id), "dedup": True},
                )
            raise

        db.refresh(notification)
        return JSONResponse(
            status_code=status.HTTP_202_ACCEPTED,
            content={"status": "accepted", "id": str(notification.id), "dedup": False},
        )

    if isinstance(payload, dict) and payload.get("action") == "ack":
        _ensure_user(user)
        try:
            ack = NotificationAck.model_validate(payload)
        except ValidationError as exc:
            raise HTTPException(status_code=400, detail="Payload inválido") from exc

        try:
            notification_id = UUID(ack.id)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="ID inválido") from exc

        notification = db.get(Notification, notification_id)
        if not notification:
            raise HTTPException(status_code=404, detail="Notificación no encontrada")

        if notification.status != NotificationStatus.READ or notification.read_at is None:
            notification.status = NotificationStatus.READ
            notification.read_at = datetime.now(timezone.utc)
            db.add(notification)
            db.commit()

        return JSONResponse(status_code=status.HTTP_200_OK, content={"status": "ok"})

    raise HTTPException(status_code=400, detail="Operación no soportada")
