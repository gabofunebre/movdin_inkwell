from enum import Enum


class Currency(str, Enum):
    ARS = "ARS"
    USD = "USD"


CURRENCY_SYMBOLS = {
    Currency.ARS: "$",
    Currency.USD: "u$s",
}
