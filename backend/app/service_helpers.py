"""Small helper functions shared by the service layer.

Why this file exists
--------------------
The *service layer* (``service.py``) contains business rules: "is this game in
the user's library?", "should we send an email?".  Sometimes two service
modules need the same tiny utility.  Putting that utility here avoids *circular
imports* — when file A imports file B and file B imports file A, Python cannot
load either file.

This module stays deliberately small: no database access, no HTTP calls, just
pure string parsing helpers that both ``PriceService`` and other code can share.
"""

from __future__ import annotations

from backend.app.ps_store import extract_product_ref, normalize_locale


def normalize_product_lookup(product_ref: str, locale: str | None) -> tuple[str, str]:
    """Turn a user-typed product reference into a clean ``(product_id, locale)`` pair.

    PlayStation Store links and search boxes accept many formats: a bare product
    ID like ``UP0001-CUSA12345_00-...``, a full URL, or an ID plus a separate
    locale argument.  This function normalizes all of those into two strings the
    rest of the app can rely on.

    Args:
        product_ref: Whatever the user typed — URL, slug, or product ID.
        locale: Optional region code (e.g. ``"en-us"``).  When omitted, we try
            to detect the locale from ``product_ref`` itself.

    Returns:
        A 2-tuple ``(product_id, locale)`` ready for database lookups.

    Example (conceptual)::

        normalize_product_lookup("https://store.playstation.com/.../10001234", None)
        # -> ("10001234", "en-us")
    """
    # Step 1: pull a product ID (and maybe a locale) out of the raw string.
    product_id, detected_locale = extract_product_ref(product_ref)
    # Step 2: pick the best locale — explicit argument wins, then detected, then default.
    return product_id, normalize_locale(locale or detected_locale or "en-us")
