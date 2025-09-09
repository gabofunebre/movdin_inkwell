from datetime import datetime, date
from decimal import Decimal

from sqlalchemy import (
    Integer,
    String,
    Numeric,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Text,
    func,
    Enum as SqlEnum,
    Index,
    CheckConstraint,
    Table,
    Column,
)

from sqlalchemy.orm import Mapped, mapped_column, relationship
from config.db import Base
from config.constants import Currency


account_tax_table = Table(
    "account_taxes",
    Base.metadata,
    Column("account_id", ForeignKey("accounts.id"), primary_key=True),
    Column("tax_id", ForeignKey("taxes.id"), primary_key=True),
)

class Account(Base):
    __tablename__ = "accounts"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    opening_balance: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    currency: Mapped[Currency] = mapped_column(SqlEnum(Currency), nullable=False)
    color: Mapped[str] = mapped_column(String(7), default="#000000")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    transactions = relationship("Transaction", back_populates="account")
    taxes = relationship("Tax", secondary=account_tax_table, back_populates="accounts")


class Transaction(Base):
    __tablename__ = "transactions"
    __table_args__ = (
        Index("ix_transactions_account_date_id", "account_id", "date", "id"),
        CheckConstraint("amount <> 0", name="ck_transactions_amount_nonzero"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    date: Mapped[date] = mapped_column(Date, nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    notes: Mapped[str] = mapped_column(Text, default="")
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    account = relationship("Account", back_populates="transactions")


class FrequentTransaction(Base):
    __tablename__ = "frequent_transactions"
    id: Mapped[int] = mapped_column(primary_key=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

class Tax(Base):
    __tablename__ = "taxes"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    rate: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    accounts = relationship("Account", secondary=account_tax_table, back_populates="taxes")
