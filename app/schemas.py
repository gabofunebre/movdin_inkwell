from datetime import date
from decimal import Decimal
from typing import List

from pydantic import BaseModel
from config.constants import Currency

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


class TaxIn(BaseModel):
    name: str
    rate: Decimal


class TaxOut(TaxIn):
    id: int
    class Config:
        from_attributes = True


class AccountTaxUpdate(BaseModel):
    tax_ids: List[int]

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
