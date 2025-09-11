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
)

from sqlalchemy.orm import Mapped, mapped_column, relationship
from config.db import Base
from config.constants import Currency, InvoiceType

class Account(Base):
    __tablename__ = "accounts"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    opening_balance: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    currency: Mapped[Currency] = mapped_column(SqlEnum(Currency), nullable=False)
    color: Mapped[str] = mapped_column(String(7), default="#000000")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_billing: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    transactions = relationship("Transaction", back_populates="account")
    invoices = relationship("Invoice", back_populates="account")


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


class Invoice(Base):
    __tablename__ = "invoices"
    __table_args__ = (
        Index("ix_invoices_account_date_id", "account_id", "date", "id"),
        CheckConstraint("amount <> 0", name="ck_invoices_amount_nonzero"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    date: Mapped[date] = mapped_column(Date, nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    number: Mapped[str] = mapped_column(String(50), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    iva_percent: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=21)
    iva_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    iibb_percent: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=3)
    iibb_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    type: Mapped[InvoiceType] = mapped_column(SqlEnum(InvoiceType), nullable=False)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    account = relationship("Account", back_populates="invoices")


class FrequentTransaction(Base):
    __tablename__ = "frequent_transactions"
    id: Mapped[int] = mapped_column(primary_key=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class User(Base):
    """Application users for authentication and authorization."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    email: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

