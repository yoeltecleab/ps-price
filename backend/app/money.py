"""Utilities for parsing and formatting monetary values.

**Why store prices as integer cents?**

Floating-point numbers (``19.99`` as a ``float``) can introduce tiny rounding
errors.  Storing **cents** as integers (``1999``) keeps comparisons exact —
critical when deciding if a price dropped below a user's target.

**What ``money_to_cents`` handles**

Real-world price strings are messy:

- ``"$19.99"`` — currency symbol + decimals
- ``"19,99 €"`` — European comma decimal separator
- ``"1.299,00"`` — thousands dot + decimal comma
- ``"Free"`` / ``"Included"`` — treated as zero cents

The function uses ``Decimal`` (not ``float``) for accurate arithmetic when
multiplying by 100.

**``format_cents``**

The reverse operation for display — turns ``1999`` + ``"USD"`` into
``"$19.99"``.  We use a small prefix map instead of a full i18n library to
keep the project lightweight.
"""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP


# Words that mean "zero dollars" in store UIs.
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
    # bool is a subclass of int in Python — exclude it explicitly.
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

    # Regex finds the first number-like substring in the text.
    match = re.search(r"[-+]?\d[\d\s,]*(?:[.,]\d{1,2})?", normalized)
    if not match:
        return None

    number = match.group(0).replace(" ", "")
    # Disambiguate 1,234.56 (US) vs 1.234,56 (EU) by looking at the last separator.
    if "," in number and "." in number:
        if number.rfind(",") > number.rfind("."):
            number = number.replace(".", "").replace(",", ".")
        else:
            number = number.replace(",", "")
    elif "," in number:
        integer, _, decimal = number.rpartition(",")
        number = f"{integer}.{decimal}" if len(decimal) in (1, 2) else number.replace(",", "")

    try:
        # quantize(..., ROUND_HALF_UP) matches common retail rounding rules.
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
    # Lightweight currency symbol map — not a full locale-aware formatter.
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
    """Return integer discount percentage when original price exceeds current.

    Example: was 4000¢ ($40), now 2000¢ ($20) → ``50`` percent off.
    Returns ``None`` when there is no meaningful discount to show.
    """
    if current_cents is None or original_cents is None or original_cents <= current_cents:
        return None
    return int(round((original_cents - current_cents) / original_cents * 100))
