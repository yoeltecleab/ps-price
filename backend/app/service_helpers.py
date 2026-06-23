"""Small helpers shared by the service layer without circular imports."""

from __future__ import annotations

from backend.app.ps_store import extract_product_ref, normalize_locale


def normalize_product_lookup(product_ref: str, locale: str | None) -> tuple[str, str]:
    product_id, detected_locale = extract_product_ref(product_ref)
    return product_id, normalize_locale(locale or detected_locale or "en-us")
