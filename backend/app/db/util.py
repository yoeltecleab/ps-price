"""Database helpers shared across repositories."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import inspect
from sqlalchemy.orm import DeclarativeBase


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


def as_dict(obj: Any) -> dict | None:
    """Convert an ORM instance or row mapping to a plain dict."""
    if obj is None:
        return None
    if isinstance(obj, dict):
        return obj
    if hasattr(obj, "_mapping"):
        return dict(obj._mapping)
    if isinstance(obj, DeclarativeBase):
        return {col.key: getattr(obj, col.key) for col in inspect(obj).mapper.column_attrs}
    return dict(obj)
