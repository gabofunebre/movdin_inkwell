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
        table_names = set(inspector.get_table_names(schema=schema))

        if "invoices" in table_names:
            columns = {
                col["name"] for col in inspector.get_columns("invoices", schema=schema)
            }
            table = _qualified_table("invoices")
            if "percepciones" not in columns:
                if "retenciones" in columns:
                    conn.execute(
                        text(
                            f"ALTER TABLE {table} RENAME COLUMN retenciones TO percepciones"
                        )
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

        if "retention_certificates" in table_names:
            columns = {
                col["name"]
                for col in inspector.get_columns("retention_certificates", schema=schema)
            }
            table = _qualified_table("retention_certificates")
            type_table = _qualified_table("retained_tax_types")
            if "retained_tax_type_id" not in columns:
                if engine.dialect.name == "postgresql":
                    conn.execute(
                        text(
                            f"ALTER TABLE {table} "
                            f"ADD COLUMN retained_tax_type_id INTEGER REFERENCES {type_table}(id)"
                        )
                    )
                else:
                    conn.execute(
                        text(
                            f"ALTER TABLE {table} ADD COLUMN retained_tax_type_id INTEGER"
                        )
                    )

                default_name = "Sin especificar"
                names: set[str] = set()
                if "concept" in columns:
                    results = conn.execute(
                        text(f"SELECT DISTINCT concept FROM {table}")
                    ).all()
                    for (concept,) in results:
                        cleaned = (concept or "").strip()
                        if not cleaned:
                            cleaned = default_name
                        names.add(cleaned)

                if not names:
                    count = conn.execute(
                        text(f"SELECT COUNT(*) FROM {table}")
                    ).scalar_one()
                    if count:
                        names.add(default_name)

                if names:
                    existing_names = {
                        row[0]
                        for row in conn.execute(
                            text(f"SELECT name FROM {type_table}")
                        ).all()
                    }
                    missing = names - existing_names
                    for name in sorted(missing):
                        conn.execute(
                            text(f"INSERT INTO {type_table} (name) VALUES (:name)"),
                            {"name": name},
                        )

                    type_map = {
                        row[1]: row[0]
                        for row in conn.execute(
                            text(f"SELECT id, name FROM {type_table}")
                        ).all()
                    }

                    if "concept" in columns:
                        rows = conn.execute(
                            text(f"SELECT id, concept FROM {table}")
                        ).all()
                        for cert_id, concept in rows:
                            cleaned = (concept or "").strip()
                            if not cleaned:
                                cleaned = default_name
                            type_id = type_map.get(cleaned)
                            if type_id is not None:
                                conn.execute(
                                    text(
                                        f"UPDATE {table} "
                                        "SET retained_tax_type_id = :type_id "
                                        "WHERE id = :cert_id"
                                    ),
                                    {"type_id": type_id, "cert_id": cert_id},
                                )
                    else:
                        default_id = type_map.get(default_name)
                        if default_id is not None:
                            conn.execute(
                                text(
                                    f"UPDATE {table} SET retained_tax_type_id = :type_id"
                                ),
                                {"type_id": default_id},
                            )

                null_count = conn.execute(
                    text(
                        f"SELECT COUNT(*) FROM {table} "
                        "WHERE retained_tax_type_id IS NULL"
                    )
                ).scalar_one()
                if null_count == 0 and engine.dialect.name == "postgresql":
                    conn.execute(
                        text(
                            f"ALTER TABLE {table} "
                            "ALTER COLUMN retained_tax_type_id SET NOT NULL"
                        )
                    )

        if "accounts" in table_names:
            columns = {
                col["name"] for col in inspector.get_columns("accounts", schema=schema)
            }
            table = _qualified_table("accounts")
            if "billing_last_checkpoint_id" not in columns:
                col_type = "BIGINT" if engine.dialect.name == "postgresql" else "INTEGER"
                conn.execute(
                    text(
                        f"ALTER TABLE {table} "
                        f"ADD COLUMN billing_last_checkpoint_id {col_type}"
                    )
                )
            if "billing_last_confirmed_id" not in columns:
                col_type = "BIGINT" if engine.dialect.name == "postgresql" else "INTEGER"
                conn.execute(
                    text(
                        f"ALTER TABLE {table} "
                        f"ADD COLUMN billing_last_confirmed_id {col_type}"
                    )
                )
            if "billing_synced_at" not in columns:
                if engine.dialect.name == "postgresql":
                    conn.execute(
                        text(
                            f"ALTER TABLE {table} "
                            "ADD COLUMN billing_synced_at TIMESTAMPTZ"
                        )
                    )
                else:
                    conn.execute(
                        text(
                            f"ALTER TABLE {table} "
                            "ADD COLUMN billing_synced_at DATETIME"
                        )
                    )

        if "transactions" in table_names:
            columns = {
                col["name"]
                for col in inspector.get_columns("transactions", schema=schema)
            }
            table = _qualified_table("transactions")
            if "billing_transaction_id" not in columns:
                col_type = "BIGINT" if engine.dialect.name == "postgresql" else "INTEGER"
                conn.execute(
                    text(
                        f"ALTER TABLE {table} "
                        f"ADD COLUMN billing_transaction_id {col_type}"
                    )
                )
            indexes = {
                idx["name"] for idx in inspector.get_indexes("transactions", schema=schema)
            }
            index_name = "ux_transactions_billing_transaction_id"
            if index_name not in indexes:
                if engine.dialect.name == "postgresql":
                    conn.execute(
                        text(
                            f"CREATE UNIQUE INDEX {index_name} "
                            f"ON {table}(billing_transaction_id) "
                            "WHERE billing_transaction_id IS NOT NULL"
                        )
                    )
                else:
                    conn.execute(
                        text(
                            f"CREATE UNIQUE INDEX IF NOT EXISTS {index_name} "
                            f"ON {table}(billing_transaction_id) "
                            "WHERE billing_transaction_id IS NOT NULL"
                        )
                    )


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
