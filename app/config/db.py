from sqlalchemy import MetaData, create_engine, text
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
            conn.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{SCHEMA_NAME}"'))

    Base.metadata.create_all(bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
