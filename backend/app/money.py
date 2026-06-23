"""Utilities for parsing and formatting monetary values.

This module contains helpers to convert a variety of price strings
(localized formatting, decimals, and textual values like "Free") into
integer cents and to format cents back into simple display strings.
"""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP


ZERO_PRICE_WORDS = {"free", "included"}


def money_to_cents(value: object) -> int | None:
    """Convert a price-like object to integer cents.

    Accepts ints, floats, Decimal and strings. The string parser is
    tolerant of common localized formats (commas/periods used as
    thousand/decimal separators). Returns None when the input cannot be
    interpreted as a monetary amount.
    """
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int((Decimal(str(value)) * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    if isinstance(value, Decimal):
        return int((value * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    if not isinstance(value, str):
        return None

    normalized = value.strip()
    if not normalized:
        return None
    if normalized.casefold() in ZERO_PRICE_WORDS:
        return 0

    match = re.search(r"[-+]?\d[\d\s,]*(?:[.,]\d{1,2})?", normalized)
    if not match:
        return None

    number = match.group(0).replace(" ", "")
    if "," in number and "." in number:
        if number.rfind(",") > number.rfind("."):
            number = number.replace(".", "").replace(",", ".")
        else:
            number = number.replace(",", "")
    elif "," in number:
        integer, _, decimal = number.rpartition(",")
        number = f"{integer}.{decimal}" if len(decimal) in (1, 2) else number.replace(",", "")

    try:
        return int((Decimal(number) * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    except InvalidOperation:
        return None


def format_cents(cents: int | None, currency: str | None) -> str | None:
    """Format integer cents into a simple human-readable string.

    The function uses a small set of currency prefixes rather than a
    full internationalization library to keep the project lightweight.
    Returns None when cents is None.
    """
    if cents is None:
        return None
    if cents == 0:
        return "Free"
    amount = Decimal(cents) / Decimal(100)
    prefix = {
        "USD": "$",
        "CAD": "CA$",
        "AUD": "A$",
        "GBP": "GBP ",
        "EUR": "EUR ",
        "JPY": "JPY ",
    }.get(currency or "", "")
    return f"{prefix}{amount:.2f}"


def currency_for_locale(locale: str) -> str | None:
    """Infer a likely currency code from a locale string like 'en-us'.

    The mapping is intentionally small; callers should treat the result
    as a best-effort hint rather than authoritative.
    """
    country = locale.split("-")[-1].upper()
    return {
        "US": "USD",
        "CA": "CAD",
        "GB": "GBP",
        "AU": "AUD",
        "NZ": "NZD",
        "JP": "JPY",
        "DE": "EUR",
        "FR": "EUR",
        "ES": "EUR",
        "IT": "EUR",
        "NL": "EUR",
        "BE": "EUR",
        "IE": "EUR",
        "PT": "EUR",
        "AT": "EUR",
        "FI": "EUR",
    }.get(country)


def discount_percent(current_cents: int | None, original_cents: int | None) -> int | None:
    """Return integer discount percentage when original price exceeds current."""
    if current_cents is None or original_cents is None or original_cents <= current_cents:
        return None
    return int(round((original_cents - current_cents) / original_cents * 100))
