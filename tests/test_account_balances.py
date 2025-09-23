import os
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest


# Ensure application modules are importable during tests
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))

os.environ.setdefault("DATABASE_URL", "sqlite+pysqlite:///:memory:")
os.environ.setdefault("DB_SCHEMA", "")

from config import db  # noqa: E402  # pylint: disable=wrong-import-position
from config.constants import Currency, InvoiceType  # noqa: E402
from models import Account, Invoice, Transaction  # noqa: E402
from routes.accounts import account_balances  # noqa: E402


@pytest.fixture(autouse=True)
def setup_database():
    """Reset the database before each test."""

    db.Base.metadata.drop_all(bind=db.engine, checkfirst=True)
    db.Base.metadata.create_all(bind=db.engine, checkfirst=True)
    yield
    db.Base.metadata.drop_all(bind=db.engine, checkfirst=True)


def test_account_balances_excludes_future_invoices():
    cutoff = date(2023, 6, 30)
    future = date(2023, 7, 31)

    with db.SessionLocal() as session:
        account = Account(
            name="Billing",
            opening_balance=Decimal("0"),
            currency=Currency.ARS,
            color="#000000",
            is_active=True,
            is_billing=True,
        )
        session.add(account)
        session.flush()
        account_id = account.id

        session.add_all(
            [
                Transaction(
                    account_id=account_id,
                    date=date(2023, 6, 1),
                    description="Before cutoff",
                    amount=Decimal("100.00"),
                    notes="",
                ),
                Transaction(
                    account_id=account_id,
                    date=date(2023, 7, 1),
                    description="After cutoff",
                    amount=Decimal("200.00"),
                    notes="",
                ),
            ]
        )

        session.add_all(
            [
                Invoice(
                    account_id=account_id,
                    date=date(2023, 5, 15),
                    description="Purchase before cutoff",
                    number="P-1",
                    amount=Decimal("1000.00"),
                    iva_amount=Decimal("50.00"),
                    percepciones=Decimal("10.00"),
                    type=InvoiceType.PURCHASE,
                ),
                Invoice(
                    account_id=account_id,
                    date=date(2023, 6, 20),
                    description="Sale before cutoff",
                    number="S-1",
                    amount=Decimal("500.00"),
                    iva_amount=Decimal("30.00"),
                    iibb_amount=Decimal("20.00"),
                    type=InvoiceType.SALE,
                ),
                Invoice(
                    account_id=account_id,
                    date=date(2023, 7, 5),
                    description="Purchase after cutoff",
                    number="P-2",
                    amount=Decimal("800.00"),
                    iva_amount=Decimal("40.00"),
                    percepciones=Decimal("15.00"),
                    type=InvoiceType.PURCHASE,
                ),
                Invoice(
                    account_id=account_id,
                    date=date(2023, 7, 10),
                    description="Sale after cutoff",
                    number="S-2",
                    amount=Decimal("900.00"),
                    iva_amount=Decimal("99.00"),
                    iibb_amount=Decimal("77.00"),
                    type=InvoiceType.SALE,
                ),
            ]
        )

        session.commit()

        balances = account_balances(to_date=cutoff, db=session)
        assert len(balances) == 1
        assert balances[0].balance == Decimal("110.00")

        future_balances = account_balances(to_date=future, db=session)
        assert len(future_balances) == 1
        assert future_balances[0].balance == Decimal("189.00")
