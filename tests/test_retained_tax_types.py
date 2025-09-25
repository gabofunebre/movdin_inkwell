import os
import sys
from pathlib import Path

import pytest
from fastapi import HTTPException, status
from sqlalchemy import delete, func, select

BASE_DIR = Path(__file__).resolve().parents[1]
APP_DIR = BASE_DIR / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

os.environ.setdefault("DATABASE_URL", "sqlite+pysqlite:///:memory:")
os.environ.setdefault("DB_SCHEMA", "")

from config.constants import DEFAULT_RETAINED_TAX_TYPES  # noqa: E402
from config.db import SessionLocal, init_db  # noqa: E402
from models import RetainedTaxType  # noqa: E402
from routes.retained_taxes import (  # noqa: E402
    delete_retained_tax_type,
    update_retained_tax_type,
)
from schemas import RetainedTaxTypeCreate  # noqa: E402
from services.retained_taxes import ensure_default_retained_tax_types  # noqa: E402


def _reset_tax_types() -> None:
    with SessionLocal() as session:
        session.execute(delete(RetainedTaxType))
        session.commit()


def _ensure_defaults() -> None:
    with SessionLocal() as session:
        ensure_default_retained_tax_types(session)


def test_default_retained_tax_types_are_seeded() -> None:
    init_db()
    _reset_tax_types()
    _ensure_defaults()

    with SessionLocal() as session:
        rows = session.execute(select(RetainedTaxType.name)).all()
        names = {name for (name,) in rows}

    for expected in DEFAULT_RETAINED_TAX_TYPES:
        assert expected in names


def test_seeding_is_idempotent() -> None:
    init_db()
    _reset_tax_types()
    _ensure_defaults()
    _ensure_defaults()

    with SessionLocal() as session:
        count = session.execute(
            select(func.count()).select_from(RetainedTaxType)
        ).scalar_one()

    assert count == len(DEFAULT_RETAINED_TAX_TYPES)


def test_cannot_update_protected_tax_type() -> None:
    init_db()
    _reset_tax_types()
    _ensure_defaults()

    with SessionLocal() as session:
        tax = session.execute(
            select(RetainedTaxType).where(RetainedTaxType.name == "IVA")
        ).scalar_one()

        with pytest.raises(HTTPException) as exc_info:
            update_retained_tax_type(
                tax.id,
                RetainedTaxTypeCreate(name="Nuevo IVA"),
                session,
            )

    assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST
    assert (
        exc_info.value.detail
        == "No se puede modificar ni eliminar un impuesto retenido predeterminado"
    )


def test_cannot_delete_protected_tax_type() -> None:
    init_db()
    _reset_tax_types()
    _ensure_defaults()

    with SessionLocal() as session:
        tax = session.execute(
            select(RetainedTaxType).where(RetainedTaxType.name == "Ganancias")
        ).scalar_one()

        with pytest.raises(HTTPException) as exc_info:
            delete_retained_tax_type(tax.id, session)

    assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST
    assert (
        exc_info.value.detail
        == "No se puede modificar ni eliminar un impuesto retenido predeterminado"
    )
