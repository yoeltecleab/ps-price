"""Unified database connection wrapper for SQLite and PostgreSQL."""

from __future__ import annotations

import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from backend.app.config import Settings
from backend.app.db.dialect import adapt_sql, maybe_add_returning_id, split_sql_script


class ExecResult:
    """Cursor-like result with a portable ``lastrowid``."""

    def __init__(self, cursor: Any, *, inserted_id: int | None = None):
        self._cursor = cursor
        self.lastrowid = inserted_id
        if self.lastrowid is None:
            self.lastrowid = getattr(cursor, "lastrowid", None)

    def fetchone(self):
        return self._cursor.fetchone()

    def fetchall(self):
        return self._cursor.fetchall()

    def __iter__(self):
        return iter(self._cursor)

    @property
    def rowcount(self) -> int:
        return self._cursor.rowcount


class DbConnection:
    """Dialect-aware connection exposing a sqlite-like ``execute`` API."""

    def __init__(self, raw_conn: Any, *, dialect: str):
        self._conn = raw_conn
        self.dialect = dialect

    def execute(self, sql: str, params: tuple | list = ()) -> ExecResult:
        adapted = adapt_sql(sql, self.dialect)
        adapted = maybe_add_returning_id(adapted, self.dialect)
        if self.dialect == "postgresql":
            cursor = self._conn.execute(adapted, params)
            inserted_id = None
            if "RETURNING" in adapted.upper():
                row = cursor.fetchone()
                if row is not None:
                    inserted_id = row.id if hasattr(row, "id") else row[0]
            return ExecResult(cursor, inserted_id=inserted_id)
        cursor = self._conn.execute(adapted, params)
        inserted_id = None
        if "RETURNING" in adapted.upper():
            row = cursor.fetchone()
            if row is not None:
                inserted_id = row[0]
        return ExecResult(cursor, inserted_id=inserted_id)

    def commit(self) -> None:
        self._conn.commit()

    def executescript(self, script: str) -> None:
        if self.dialect == "sqlite":
            self._conn.executescript(script)
            return
        for statement in split_sql_script(script):
            self.execute(statement)


class Database:
    """Thread-safe database helper supporting SQLite files or PostgreSQL URLs."""

    def __init__(self, path: str | None = None, *, url: str | None = None):
        if bool(path) == bool(url):
            raise ValueError("provide exactly one of path= or url=")
        self.dialect = "postgresql" if url else "sqlite"
        self.path = Path(path) if path else None
        self.url = url
        self._lock = threading.RLock()

    @property
    def backend(self) -> str:
        return self.dialect

    @contextmanager
    def connect(self) -> Iterator[DbConnection]:
        if self.dialect == "postgresql":
            import psycopg
            from psycopg.rows import namedtuple_row

            raw = psycopg.connect(self.url, row_factory=namedtuple_row)
            try:
                yield DbConnection(raw, dialect=self.dialect)
                raw.commit()
            finally:
                raw.close()
            return

        assert self.path is not None
        self.path.parent.mkdir(parents=True, exist_ok=True)
        raw = sqlite3.connect(self.path, timeout=30, check_same_thread=False)
        raw.row_factory = sqlite3.Row
        raw.execute("PRAGMA foreign_keys = ON")
        raw.execute("PRAGMA journal_mode = WAL")
        try:
            yield DbConnection(raw, dialect=self.dialect)
            raw.commit()
        finally:
            raw.close()

    def migrate(self) -> None:
        from backend.app.db.migrations import run_migrations

        run_migrations(self)


def create_database(settings: Settings) -> Database:
    """Build a Database from application settings."""
    if settings.database_url:
        return Database(url=settings.database_url)
    return Database(path=settings.database_path)
