"""Helpers for human-readable PlayStation Store product titles."""

from __future__ import annotations

import re

# Strip internal SKU suffixes like " (007FIRSTLIGHT000)" from display names.
_GAME_CODE_SUFFIX_RE = re.compile(r"\s*\([A-Z0-9_\-]+\)\s*$")


def clean_game_name(name: str) -> str:
    """Remove trailing parenthetical game-code suffixes from a title."""
    cleaned = _GAME_CODE_SUFFIX_RE.sub("", name.strip())
    return cleaned or name.strip()


def infer_edition_name(base_name: str, product_id: str) -> str:
    """Guess an edition label when GraphQL only returns a product id stub."""
    suffix = product_id.rsplit("_", 1)[-1].upper()
    if "DELUXEUPG" in suffix or "UPGRADE" in suffix or suffix.endswith("UPG00"):
        return f"{base_name} - Deluxe Edition Upgrade"
    if "DELUXE" in suffix:
        return f"{base_name} - Deluxe Edition"
    if "ULTIMATE" in suffix:
        return f"{base_name} Ultimate Edition"
    if "STANDARD" in suffix:
        return base_name
    return base_name
