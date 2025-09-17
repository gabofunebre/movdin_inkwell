from sqlalchemy import MetaData, create_engine, text, inspect
from sqlalchemy.orm import DeclarativeBase, sessionmaker

import os

# Prefer ``DATABASE_URL`` and fallback to ``DB_DSN`` for backward compatibility
DB_DSN = os.getenv("DATABASE_URL") or os.getenv("DB_DSN")
if not DB_DSN:
    raise RuntimeError("DATABASE_URL not set")

SCHEMA_NAME = os.getenv("DB_SCHEMA", "movdin")

engine = create_engine(DB_DSN, future=True, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


class Base(DeclarativeBase):
    metadata = MetaData(schema=SCHEMA_NAME)


def init_db() -> None:
    """Create the service schema and tables if they do not exist."""
    import models  # register models

    with engine.begin() as conn:
        if engine.dialect.name == "postgresql":
            conn.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{_quote_identifier(SCHEMA_NAME)}"'))

    Base.metadata.create_all(bind=engine)
    _apply_schema_upgrades()


def _quote_identifier(identifier: str) -> str:
    """Return a double-quoted identifier safe for raw SQL usage."""

    return identifier.replace('"', '""')


def _qualified_table(name: str) -> str:
    """Return a table reference qualified with the configured schema when needed."""

    if engine.dialect.name == "postgresql":
        return f'"{_quote_identifier(SCHEMA_NAME)}"."{_quote_identifier(name)}"'
    return name


def _apply_schema_upgrades() -> None:
    """Apply lightweight schema migrations required by the application."""

    schema = SCHEMA_NAME if engine.dialect.name == "postgresql" else None

    with engine.begin() as conn:
        inspector = inspect(conn)
        if "invoices" not in inspector.get_table_names(schema=schema):
            return

        columns = {col["name"] for col in inspector.get_columns("invoices", schema=schema)}
        table = _qualified_table("invoices")
        if "percepciones" not in columns:
            if "retenciones" in columns:
                conn.execute(
                    text(f"ALTER TABLE {table} RENAME COLUMN retenciones TO percepciones")
                )
            else:
                if engine.dialect.name == "postgresql":
                    conn.execute(
                        text(
                            f"ALTER TABLE {table} "
                            "ADD COLUMN percepciones NUMERIC(12, 2) DEFAULT 0 NOT NULL"
                        )
                    )
                else:
                    conn.execute(
                        text(
                            f"ALTER TABLE {table} "
                            "ADD COLUMN percepciones NUMERIC(12, 2) DEFAULT 0"
                        )
                    )

            conn.execute(
                text(
                    f"UPDATE {table} SET percepciones = 0 "
                    "WHERE percepciones IS NULL"
                )
            )

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
