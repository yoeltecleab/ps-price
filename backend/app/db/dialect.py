"""SQL dialect helpers — adapt SQLite-style queries for PostgreSQL."""

from __future__ import annotations

import re


def adapt_sql(sql: str, dialect: str) -> str:
    """Translate placeholder and SQLite-specific syntax for the target dialect."""
    if dialect == "sqlite":
        return sql

    adapted = sql
    adapted = re.sub(
        r"INSERT\s+OR\s+IGNORE\s+INTO",
        "INSERT INTO",
        adapted,
        flags=re.IGNORECASE,
    )
    upper = adapted.upper()
    if "INSERT INTO USER_LIBRARY" in upper and "ON CONFLICT" not in upper:
        adapted = adapted.rstrip().rstrip(";") + " ON CONFLICT DO NOTHING"
    adapted = re.sub(
        r"(\w+)\s+COLLATE\s+NOCASE",
        r"LOWER(\1)",
        adapted,
        flags=re.IGNORECASE,
    )
    adapted = adapted.replace("?", "%s")
    return adapted


def maybe_add_returning_id(sql: str, dialect: str) -> str:
    """Append ``RETURNING id`` for single-row inserts that need ``lastrowid``."""
    upper = sql.strip().upper()
    if dialect == "sqlite" and "RETURNING" in upper:
        return sql
    if not upper.startswith("INSERT INTO"):
        return sql
    if "RETURNING" in upper:
        return sql
    skip_tables = (
        "INTO USER_LIBRARY",
        "INTO PRICE_HISTORY",
        "INTO CATALOG_META",
    )
    if any(token in upper for token in skip_tables):
        return sql
    return sql.rstrip().rstrip(";") + " RETURNING id"


def split_sql_script(script: str) -> list[str]:
    """Split a SQL script into individual statements (naive, no semicolons in strings)."""
    parts: list[str] = []
    for chunk in script.split(";"):
        statement = chunk.strip()
        if statement:
            parts.append(statement)
    return parts
