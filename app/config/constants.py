from enum import Enum


class Currency(str, Enum):
    ARS = "ARS"
    USD = "USD"


class InvoiceType(str, Enum):
    PURCHASE = "purchase"
    SALE = "sale"


CURRENCY_SYMBOLS = {
    Currency.ARS: "$",
    Currency.USD: "u$s",
}

