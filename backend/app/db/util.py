"""Database helpers shared across repositories."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import inspect
from sqlalchemy.engine.row import RowMapping
from sqlalchemy.orm import DeclarativeBase


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _flatten_row_mapping(mapping: RowMapping | Any) -> dict[str, Any]:
    """Expand ORM entities inside a SQLAlchemy row mapping into plain columns."""
    row: dict[str, Any] = {}
    items = mapping.items() if isinstance(mapping, RowMapping) else mapping._mapping.items()
    for key, value in items:
        if isinstance(value, DeclarativeBase):
            for col in inspect(value).mapper.column_attrs:
                row[col.key] = getattr(value, col.key)
        else:
            row[key] = value
    return row


def as_dict(obj: Any) -> dict | None:
    """Convert an ORM instance or row mapping to a plain dict."""
    if obj is None:
        return None
    if isinstance(obj, dict):
        return obj
    if isinstance(obj, RowMapping):
        return _flatten_row_mapping(obj)
    if hasattr(obj, "_mapping"):
        return _flatten_row_mapping(obj)
    if isinstance(obj, DeclarativeBase):
        return {col.key: getattr(obj, col.key) for col in inspect(obj).mapper.column_attrs}
    return dict(obj)
