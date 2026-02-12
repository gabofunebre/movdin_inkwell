from datetime import datetime, date
import uuid
from enum import Enum
from typing import Any
from decimal import Decimal

from sqlalchemy import (
    Integer,
    BigInteger,
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
    JSON,
    UniqueConstraint,
    Uuid,
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
    billing_last_transactions_checkpoint_id: Mapped[int | None] = mapped_column(
        "billing_last_checkpoint_id", BigInteger, nullable=True
    )
    billing_last_transactions_confirmed_id: Mapped[int | None] = mapped_column(
        "billing_last_confirmed_id", BigInteger, nullable=True
    )
    billing_last_changes_checkpoint_id: Mapped[int | None] = mapped_column(
        BigInteger, nullable=True
    )
    billing_last_changes_confirmed_id: Mapped[int | None] = mapped_column(
        BigInteger, nullable=True
    )
    billing_synced_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    transactions = relationship("Transaction", back_populates="account")
    invoices = relationship("Invoice", back_populates="account")

    @property
    def billing_last_checkpoint_id(self) -> int | None:
        return self.billing_last_transactions_checkpoint_id

    @billing_last_checkpoint_id.setter
    def billing_last_checkpoint_id(self, value: int | None) -> None:
        self.billing_last_transactions_checkpoint_id = value

    @property
    def billing_last_confirmed_id(self) -> int | None:
        return self.billing_last_transactions_confirmed_id

    @billing_last_confirmed_id.setter
    def billing_last_confirmed_id(self, value: int | None) -> None:
        self.billing_last_transactions_confirmed_id = value


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
    billing_transaction_id: Mapped[int | None] = mapped_column(
        BigInteger, unique=True, nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    account = relationship("Account", back_populates="transactions")


class BillingTransactionSyncState(Base):
    __tablename__ = "billing_transaction_sync_states"
    __table_args__ = (
        Index("ix_billing_tx_sync_status", "status"),
    )

    transaction_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    exportable_movement_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    is_custom_inkwell: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="unavailable")
    updated_at_event_id: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


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
    percepciones: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    type: Mapped[InvoiceType] = mapped_column(SqlEnum(InvoiceType), nullable=False)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    account = relationship("Account", back_populates="invoices")


class RetainedTaxType(Base):
    __tablename__ = "retained_tax_types"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    certificates = relationship(
        "RetentionCertificate", back_populates="retained_tax_type"
    )


class RetentionCertificate(Base):
    __tablename__ = "retention_certificates"
    __table_args__ = (
        Index(
            "ix_retention_certificates_date_id",
            "date",
            "id",
        ),
        CheckConstraint(
            "amount <> 0", name="ck_retention_certificates_amount_nonzero"
        ),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    number: Mapped[str] = mapped_column(String(50), nullable=False)
    date: Mapped[date] = mapped_column(Date, nullable=False)
    invoice_reference: Mapped[str] = mapped_column(String(50), nullable=False)
    retained_tax_type_id: Mapped[int] = mapped_column(
        ForeignKey("retained_tax_types.id"),
        nullable=False,
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    retained_tax_type = relationship(
        "RetainedTaxType", back_populates="certificates"
    )


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


class NotificationPriority(str, Enum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"


class NotificationStatus(str, Enum):
    UNREAD = "unread"
    READ = "read"


class Notification(Base):
    __tablename__ = "notifications"
    __table_args__ = (
        Index("ix_notifications_status_occurred_at", "status", "occurred_at"),
        UniqueConstraint("idempotency_key", name="uq_notifications_idempotency"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    type: Mapped[str] = mapped_column(String(255), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    deeplink: Mapped[str | None] = mapped_column(String(500), nullable=True)
    topic: Mapped[str | None] = mapped_column(String(120), nullable=True)
    priority: Mapped[NotificationPriority] = mapped_column(
        SqlEnum(NotificationPriority),
        default=NotificationPriority.NORMAL,
        nullable=False,
    )
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[NotificationStatus] = mapped_column(
        SqlEnum(NotificationStatus),
        default=NotificationStatus.UNREAD,
        nullable=False,
    )
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    idempotency_key: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    variables: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    source_app: Mapped[str] = mapped_column(String(50), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
