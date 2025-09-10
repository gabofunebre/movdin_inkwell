from datetime import date
from decimal import Decimal

from pydantic import BaseModel
from config.constants import Currency, InvoiceType

class AccountIn(BaseModel):
    name: str
    opening_balance: Decimal = 0
    currency: Currency
    color: str = "#000000"
    is_active: bool = True

class AccountOut(AccountIn):
    id: int
    class Config:
        from_attributes = True

class TransactionCreate(BaseModel):
    account_id: int
    date: date
    description: str = ""
    amount: Decimal
    notes: str = ""


class TransactionOut(BaseModel):
    id: int
    account_id: int
    date: date
    description: str
    amount: Decimal
    notes: str

    class Config:
        from_attributes = True


class TransactionWithBalance(TransactionOut):
    running_balance: Decimal


class InvoiceCreate(BaseModel):
    account_id: int
    date: date
    description: str = ""
    amount: Decimal
    type: InvoiceType


class InvoiceOut(BaseModel):
    id: int
    account_id: int
    date: date
    description: str
    amount: Decimal
    type: InvoiceType

    class Config:
        from_attributes = True


class FrequentIn(BaseModel):
    description: str


class FrequentOut(FrequentIn):
    id: int

    class Config:
        from_attributes = True


class AccountBalance(BaseModel):
    account_id: int
    name: str
    currency: Currency
    balance: Decimal
    color: str


class BalanceOut(BaseModel):
    balance: Decimal
