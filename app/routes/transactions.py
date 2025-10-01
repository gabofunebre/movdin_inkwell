import os
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import List

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from config.db import get_db
from models import Account, Transaction
from auth import require_admin
from schemas import TransactionCreate, TransactionOut

router = APIRouter(prefix="/transactions")


def _has_non_empty_string(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


@router.post("", response_model=TransactionOut)
def create_tx(payload: TransactionCreate, db: Session = Depends(get_db)):
    if payload.date > date.today():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No se permiten fechas futuras",
        )
    account = db.get(Account, payload.account_id)
    if not account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Cuenta no encontrada",
        )
    if account.is_billing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No se permiten movimientos manuales para la cuenta de facturación",
        )
    tx = Transaction(**payload.dict())
    db.add(tx)
    db.commit()
    db.refresh(tx)
    return tx


@router.get("", response_model=List[TransactionOut])
def list_transactions(limit: int = 50, offset: int = 0, db: Session = Depends(get_db)):
    stmt = (
        select(Transaction)
        .order_by(Transaction.date.desc(), Transaction.id.desc())
        .limit(limit)
        .offset(offset)
    )
    rows = db.scalars(stmt).all()
    return rows


@router.put("/{tx_id}", response_model=TransactionOut, dependencies=[Depends(require_admin)])
def update_tx(tx_id: int, payload: TransactionCreate, db: Session = Depends(get_db)):
    tx = db.get(Transaction, tx_id)
    if not tx:
        raise HTTPException(status_code=404, detail="Movimiento no encontrado")
    if payload.date > date.today():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No se permiten fechas futuras",
        )
    for field, value in payload.dict().items():
        setattr(tx, field, value)
    db.add(tx)
    db.commit()
    db.refresh(tx)
    return tx


@router.delete("/{tx_id}", status_code=204, dependencies=[Depends(require_admin)])
def delete_tx(tx_id: int, db: Session = Depends(get_db)):
    tx = db.get(Transaction, tx_id)
    if tx:
        db.delete(tx)
        db.commit()
    return Response(status_code=204)


@router.post("/billing/sync")
def sync_billing_transactions(limit: int = 100, db: Session = Depends(get_db)):
    billing_account = db.scalar(select(Account).where(Account.is_billing == True))
    if not billing_account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No hay una cuenta de facturación configurada",
        )

    base_url = os.getenv("FACTURACION_RUTA_DATA")
    api_key = os.getenv("BILLING_API_KEY")
    if not base_url:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="FACTURACION_RUTA_DATA no está configurado",
        )
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="BILLING_API_KEY no está configurado",
        )

    feed_url = _build_billing_feed_url(base_url)
    ack_url = _build_billing_ack_url(base_url)
    headers = {"X-API-Key": api_key}
    transactions_limit = max(1, min(limit or 100, 500))
    changes_limit = transactions_limit
    changes_since = billing_account.billing_last_changes_confirmed_id

    (
        transaction_events,
        remote_changes,
        transactions_checkpoint,
        transactions_confirmed,
        changes_checkpoint,
        changes_confirmed,
    ) = _fetch_billing_feed(
        feed_url,
        headers,
        transactions_limit,
        changes_limit,
        changes_since,
    )

    counters = {"created": 0, "updated": 0, "deleted": 0}

    now = datetime.now(timezone.utc)
    if transactions_confirmed is not None:
        billing_account.billing_last_transactions_confirmed_id = transactions_confirmed
    if changes_confirmed is not None:
        billing_account.billing_last_changes_confirmed_id = changes_confirmed

    staged_transactions: dict[int, Transaction] = {}

    try:
        for change in transaction_events:
            if not isinstance(change, dict):
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail="Evento inválido recibido desde facturación",
                )

            event = (change.get("event") or "").lower()
            if event not in counters:
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail="Evento desconocido recibido desde facturación",
                )

            payload = change.get("transaction")
            remote_id = _parse_remote_identifier(
                change.get("transaction_id"), "transaction_id"
            )
            if remote_id is None and isinstance(payload, dict):
                remote_id = _parse_remote_identifier(payload.get("id"), "transaction.id")
            if remote_id is None:
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail="Movimiento recibido sin identificador válido",
                )

            existing_tx = staged_transactions.get(remote_id)
            if existing_tx is None:
                existing_tx = db.scalar(
                    select(Transaction)
                    .where(Transaction.account_id == billing_account.id)
                    .where(Transaction.billing_transaction_id == remote_id)
                )
                if existing_tx is not None:
                    staged_transactions[remote_id] = existing_tx

            if event == "deleted":
                if not existing_tx:
                    raise HTTPException(
                        status_code=status.HTTP_502_BAD_GATEWAY,
                        detail=(
                            "Se recibió un evento de eliminación para un movimiento"
                            " inexistente"
                        ),
                    )
                db.delete(existing_tx)
                staged_transactions.pop(remote_id, None)
            else:
                if not isinstance(payload, dict):
                    raise HTTPException(
                        status_code=status.HTTP_502_BAD_GATEWAY,
                        detail="Formato de evento inválido desde facturación",
                    )

                tx_date = _parse_remote_date(payload.get("date"), remote_id)
                amount = _parse_remote_amount(payload.get("amount"), remote_id)

                description_source = payload.get("description")
                if _has_non_empty_string(description_source):
                    description = description_source.strip()
                elif existing_tx and existing_tx.description is not None:
                    description = existing_tx.description
                else:
                    raise HTTPException(
                        status_code=status.HTTP_502_BAD_GATEWAY,
                        detail=(
                            "Descripción faltante para el movimiento recibido"
                        ),
                    )

                notes_source = payload.get("notes")
                if _has_non_empty_string(notes_source):
                    notes = notes_source
                elif existing_tx and existing_tx.notes is not None:
                    notes = existing_tx.notes
                else:
                    notes = ""

                if existing_tx:
                    existing_tx.date = tx_date
                    existing_tx.amount = amount
                    existing_tx.description = description
                    existing_tx.notes = notes
                    db.add(existing_tx)
                else:
                    new_tx = Transaction(
                        account_id=billing_account.id,
                        date=tx_date,
                        description=description,
                        amount=amount,
                        notes=notes,
                        billing_transaction_id=remote_id,
                    )
                    db.add(new_tx)
                    staged_transactions[remote_id] = new_tx

            counters[event] += 1

        # Procesamos los cambios de exportación sólo para confirmar checkpoints
        for change in remote_changes:
            if not isinstance(change, dict):
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail="Cambio inválido recibido desde facturación",
                )

        db.commit()
    except HTTPException:
        db.rollback()
        raise
    except Exception as exc:  # pragma: no cover - defensive
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="No se pudieron guardar los movimientos de facturación",
        ) from exc

    ack_data: dict = {}
    pending_transactions_checkpoint = transactions_checkpoint
    pending_changes_checkpoint = changes_checkpoint

    if (
        pending_transactions_checkpoint is not None
        or pending_changes_checkpoint is not None
    ):
        ack_data = _acknowledge_billing_checkpoint(
            ack_url,
            headers,
            pending_transactions_checkpoint,
            pending_changes_checkpoint,
        )

    last_transaction = None
    last_change = None
    if ack_data:
        last_transaction = _parse_remote_identifier(
            ack_data.get("last_transaction_id"), "last_transaction_id"
        )
        last_change = _parse_remote_identifier(
            ack_data.get("last_change_id"), "last_change_id"
        )

    if last_transaction is None:
        last_transaction = transactions_confirmed
    if last_change is None:
        last_change = changes_confirmed

    timestamps = []
    if ack_data:
        timestamps.extend(
            [
                _parse_remote_timestamp(ack_data.get("transactions_updated_at")),
                _parse_remote_timestamp(ack_data.get("changes_updated_at")),
            ]
        )
    parsed_updates = [ts for ts in timestamps if ts is not None]
    if parsed_updates:
        billing_account.billing_synced_at = max(parsed_updates)
    else:
        billing_account.billing_synced_at = now

    if pending_transactions_checkpoint is not None:
        billing_account.billing_last_transactions_checkpoint_id = (
            pending_transactions_checkpoint
        )
    if last_transaction is not None:
        billing_account.billing_last_transactions_confirmed_id = last_transaction
    if pending_changes_checkpoint is not None:
        billing_account.billing_last_changes_checkpoint_id = pending_changes_checkpoint
    if last_change is not None:
        billing_account.billing_last_changes_confirmed_id = last_change

    try:
        db.commit()
    except HTTPException:
        db.rollback()
        raise
    except Exception as exc:  # pragma: no cover - defensive
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="No se pudieron guardar la confirmación de facturación",
        ) from exc

    message = _build_sync_summary(
        counters["created"], counters["updated"], counters["deleted"]
    )

    response_payload = {
        "nuevos": counters["created"],
        "modificados": counters["updated"],
        "eliminados": counters["deleted"],
        "transactions_checkpoint_id": billing_account.billing_last_transactions_checkpoint_id,
        "transactions_confirmed_id": billing_account.billing_last_transactions_confirmed_id,
        "changes_checkpoint_id": billing_account.billing_last_changes_checkpoint_id,
        "changes_confirmed_id": billing_account.billing_last_changes_confirmed_id,
        "synced_at": billing_account.billing_synced_at.isoformat()
        if billing_account.billing_synced_at
        else None,
        "message": message,
    }
    response_payload["checkpoint_id"] = response_payload["transactions_checkpoint_id"]
    response_payload["last_confirmed_id"] = response_payload["transactions_confirmed_id"]
    return response_payload


def _build_billing_feed_url(base_url: str) -> str:
    return base_url.rstrip("/")


def _build_billing_ack_url(base_url: str) -> str:
    return _build_billing_feed_url(base_url)


def _fetch_billing_feed(
    endpoint: str,
    headers: dict[str, str],
    transactions_limit: int,
    changes_limit: int,
    changes_since: int | None,
) -> tuple[
    list[dict],
    list[dict],
    int | None,
    int | None,
    int | None,
    int | None,
]:
    params: dict[str, object] = {
        "limit": transactions_limit,
        "changes_limit": changes_limit,
    }
    if changes_since is not None:
        params["changes_since"] = changes_since
    try:
        response = httpx.get(
            endpoint,
            params=params,
            headers=headers,
            timeout=30.0,
        )
    except HTTPException:
        raise
    except httpx.RequestError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="No se pudo conectar con el servicio de facturación",
        ) from exc

    payload = _handle_billing_response(response)

    transactions = payload.get("transactions") or []
    if not isinstance(transactions, list):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Respuesta inválida del servicio de facturación",
        )

    transaction_events = payload.get("transaction_events") or []
    if not isinstance(transaction_events, list):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Respuesta inválida del servicio de facturación",
        )

    changes = payload.get("changes") or []
    if not isinstance(changes, list):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Respuesta inválida del servicio de facturación",
        )

    snapshots_by_id: dict[int, dict] = {}
    for snapshot in transactions:
        if not isinstance(snapshot, dict):
            continue
        snapshot_id = _parse_remote_identifier(
            snapshot.get("id"), "transactions[].id"
        )
        if snapshot_id is not None:
            snapshots_by_id[snapshot_id] = snapshot

    for event in transaction_events:
        if not isinstance(event, dict):
            continue
        event_id = _parse_remote_identifier(
            event.get("transaction_id"), "transaction_events[].transaction_id"
        )
        if event_id is not None and event.get("transaction") is None:
            snapshot = snapshots_by_id.get(event_id)
            if snapshot is not None:
                event["transaction"] = snapshot

    transactions_checkpoint = _parse_remote_identifier(
        payload.get("transactions_checkpoint_id"), "transactions_checkpoint_id"
    )
    transactions_confirmed = _parse_remote_identifier(
        payload.get("last_confirmed_transaction_id"), "last_confirmed_transaction_id"
    )
    changes_checkpoint = _parse_remote_identifier(
        payload.get("changes_checkpoint_id"), "changes_checkpoint_id"
    )
    changes_confirmed = _parse_remote_identifier(
        payload.get("last_confirmed_change_id"), "last_confirmed_change_id"
    )

    return (
        transaction_events,
        changes,
        transactions_checkpoint,
        transactions_confirmed,
        changes_checkpoint,
        changes_confirmed,
    )


def _handle_billing_response(response: httpx.Response) -> dict:
    if response.status_code == status.HTTP_403_FORBIDDEN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acceso denegado por el servicio de facturación",
        )
    if response.status_code == status.HTTP_404_NOT_FOUND:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="El servicio de facturación no encontró movimientos para la cuenta configurada",
        )
    if response.status_code >= 400:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=_extract_remote_error(response),
        )
    try:
        payload = response.json()
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Respuesta inválida del servicio de facturación",
        ) from exc
    if not isinstance(payload, dict):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Respuesta inválida del servicio de facturación",
        )
    return payload


def _extract_remote_error(response: httpx.Response) -> str:
    try:
        data = response.json()
    except ValueError:
        return f"Error del servicio de facturación ({response.status_code})"
    if isinstance(data, dict):
        for key in ("detail", "message", "error"):
            value = data.get(key)
            if isinstance(value, str) and value:
                return value
    return f"Error del servicio de facturación ({response.status_code})"


def _acknowledge_billing_checkpoint(
    endpoint: str,
    headers: dict[str, str],
    transactions_checkpoint: int | None,
    changes_checkpoint: int | None,
) -> dict:
    payload: dict[str, int] = {}
    if transactions_checkpoint is not None:
        payload["movements_checkpoint_id"] = transactions_checkpoint
    if changes_checkpoint is not None:
        payload["changes_checkpoint_id"] = changes_checkpoint
    if not payload:
        return {}
    try:
        response = httpx.post(
            endpoint,
            json=payload,
            headers=headers,
            timeout=30.0,
        )
    except httpx.RequestError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="No se pudo confirmar el checkpoint de facturación",
        ) from exc
    return _handle_billing_response(response)
def _parse_remote_date(value: object, remote_id: int) -> date:
    if not value:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Fecha faltante para el movimiento {remote_id}",
        )
    if isinstance(value, str):
        cleaned = value.strip()
        try:
            if "T" in cleaned:
                cleaned = cleaned.replace("Z", "+00:00")
                return datetime.fromisoformat(cleaned).date()
            return date.fromisoformat(cleaned)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Fecha inválida para el movimiento {remote_id}",
            ) from exc
    raise HTTPException(
        status_code=status.HTTP_502_BAD_GATEWAY,
        detail=f"Fecha inválida para el movimiento {remote_id}",
    )


def _parse_remote_amount(value: object, remote_id: int) -> Decimal:
    if value is None:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Monto faltante para el movimiento {remote_id}",
        )
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Monto inválido para el movimiento {remote_id}",
        ) from exc
    return amount


def _parse_remote_identifier(value: object, field_name: str) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Valor inválido para {field_name} en la respuesta de facturación",
        ) from exc


def _parse_remote_timestamp(value: object) -> datetime | None:
    if not value:
        return None
    if not isinstance(value, str):
        return None
    cleaned = value.strip()
    if not cleaned:
        return None
    if cleaned.endswith("Z"):
        cleaned = cleaned[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(cleaned)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _build_sync_summary(created: int, updated: int, deleted: int) -> str:
    if not any((created, updated, deleted)):
        return "No se registraron cambios de facturación."

    parts: list[str] = []
    if created:
        parts.append(
            "1 movimiento nuevo" if created == 1 else f"{created} movimientos nuevos"
        )
    if updated:
        parts.append(
            "1 movimiento modificado"
            if updated == 1
            else f"{updated} movimientos modificados"
        )
    if deleted:
        parts.append(
            "1 movimiento eliminado"
            if deleted == 1
            else f"{deleted} movimientos eliminados"
        )

    joined = ", ".join(parts)
    return f"Se sincronizaron {joined}."
