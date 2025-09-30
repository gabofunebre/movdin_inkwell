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

    changes_url = _build_billing_changes_url(base_url)
    ack_url = _build_billing_ack_url(base_url)
    headers = {"X-API-Key": api_key}
    page_size = max(1, min(limit or 100, 500))

    since = billing_account.billing_last_checkpoint_id
    (
        remote_changes,
        latest_checkpoint,
        last_confirmed,
    ) = _fetch_billing_changes(changes_url, headers, page_size, since)

    counters = {"created": 0, "updated": 0, "deleted": 0}

    now = datetime.now(timezone.utc)
    billing_account.billing_last_checkpoint_id = latest_checkpoint
    if last_confirmed is not None:
        billing_account.billing_last_confirmed_id = last_confirmed
    billing_account.billing_synced_at = now

    try:
        for change in remote_changes:
            event = (change.get("event") or "").lower()
            if event not in counters:
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail="Evento desconocido recibido desde facturación",
                )

            payload = change.get("transaction")
            if not isinstance(payload, dict):
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail="Formato de evento inválido desde facturación",
                )

            remote_id = _parse_remote_identifier(
                payload.get("id"), "transaction.id"
            )
            if remote_id is None:
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail="Movimiento recibido sin identificador válido",
                )

            existing_tx = db.scalar(
                select(Transaction)
                .where(Transaction.account_id == billing_account.id)
                .where(Transaction.billing_transaction_id == remote_id)
            )

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
            else:
                tx_date = _parse_remote_date(payload.get("date"), remote_id)
                amount = _parse_remote_amount(payload.get("amount"), remote_id)
                description = (payload.get("description") or "").strip()
                notes = payload.get("notes") or ""

                if event == "updated" and not existing_tx:
                    raise HTTPException(
                        status_code=status.HTTP_502_BAD_GATEWAY,
                        detail=(
                            "Se recibió un evento de actualización para un movimiento"
                            " inexistente"
                        ),
                    )

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

            counters[event] += 1

        ack_data = None
        if latest_checkpoint is not None:
            ack_data = _acknowledge_billing_checkpoint(
                ack_url, headers, latest_checkpoint
            )
            ack_confirmed = _parse_remote_identifier(
                ack_data.get("last_confirmed_id"), "last_confirmed_id"
            )
            if ack_confirmed is None:
                ack_confirmed = _parse_remote_identifier(
                    ack_data.get("last_transaction_id"), "last_transaction_id"
                )
            if ack_confirmed is not None:
                billing_account.billing_last_confirmed_id = ack_confirmed
            updated_at = ack_data.get("updated_at") if ack_data else None
            parsed_updated = (
                _parse_remote_timestamp(updated_at) if updated_at else None
            )
            if parsed_updated:
                billing_account.billing_synced_at = parsed_updated

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

    message = _build_sync_summary(
        counters["created"], counters["updated"], counters["deleted"]
    )

    return {
        "nuevos": counters["created"],
        "modificados": counters["updated"],
        "eliminados": counters["deleted"],
        "checkpoint_id": billing_account.billing_last_checkpoint_id,
        "last_confirmed_id": billing_account.billing_last_confirmed_id,
        "synced_at": billing_account.billing_synced_at.isoformat()
        if billing_account.billing_synced_at
        else None,
        "message": message,
    }


def _build_billing_changes_url(base_url: str) -> str:
    trimmed = base_url.rstrip("/")
    return f"{trimmed}/movimientos_exportables/cambios"


def _build_billing_ack_url(base_url: str) -> str:
    return f"{_build_billing_changes_url(base_url)}/ack"


def _fetch_billing_changes(
    endpoint: str,
    headers: dict[str, str],
    limit: int,
    since: int | None,
) -> tuple[list[dict], int | None, int | None]:
    all_changes: list[dict] = []
    latest_checkpoint: int | None = since
    last_confirmed: int | None = None
    cursor = since
    try:
        with httpx.Client(timeout=30.0) as client:
            while True:
                params = {"limit": limit}
                if cursor is not None:
                    params["since"] = cursor
                response = client.get(endpoint, params=params, headers=headers)
                payload = _handle_billing_response(response)
                changes = payload.get("changes") or []
                if not isinstance(changes, list):
                    raise HTTPException(
                        status_code=status.HTTP_502_BAD_GATEWAY,
                        detail="Respuesta inválida del servicio de facturación",
                    )
                all_changes.extend(changes)

                checkpoint_value = _parse_remote_identifier(
                    payload.get("checkpoint_id"), "checkpoint_id"
                )
                if checkpoint_value is not None:
                    latest_checkpoint = checkpoint_value

                confirmed_value = _parse_remote_identifier(
                    payload.get("last_confirmed_id"), "last_confirmed_id"
                )
                if confirmed_value is not None:
                    last_confirmed = confirmed_value

                if not payload.get("has_more"):
                    break
                cursor = checkpoint_value
                if cursor is None:
                    break
    except HTTPException:
        raise
    except httpx.RequestError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="No se pudo conectar con el servicio de facturación",
        ) from exc

    return all_changes, latest_checkpoint, last_confirmed


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
    endpoint: str, headers: dict[str, str], checkpoint_id: int
) -> dict:
    try:
        response = httpx.post(
            endpoint,
            json={"checkpoint_id": checkpoint_id},
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
