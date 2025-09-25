from collections.abc import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from config.constants import DEFAULT_RETAINED_TAX_TYPES
from models import RetainedTaxType


def ensure_default_retained_tax_types(
    db: Session, defaults: Iterable[str] = DEFAULT_RETAINED_TAX_TYPES
) -> None:
    """Ensure the configured default retained tax types exist in the database."""

    existing = {
        name
        for (name,) in db.execute(select(RetainedTaxType.name))
    }
    missing = [name for name in defaults if name not in existing]
    if not missing:
        return

    for name in missing:
        db.add(RetainedTaxType(name=name))

    db.commit()
