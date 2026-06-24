"""SQLAlchemy engine, session factory, and application database handle."""

from __future__ import annotations

import threading
from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from backend.app.config import Settings
from backend.app.db.base import Base


class Database:
    """Thread-safe PostgreSQL database access via SQLAlchemy sessions."""

    def __init__(self, url: str):
        self.url = url
        self.engine: Engine = create_engine(
            url,
            pool_pre_ping=True,
            future=True,
        )
        self._session_factory = sessionmaker(
            bind=self.engine,
            autoflush=False,
            autocommit=False,
            expire_on_commit=False,
        )
        self._lock = threading.RLock()

    @property
    def dialect(self) -> str:
        return self.engine.dialect.name

    @property
    def backend(self) -> str:
        return self.dialect

    def migrate(self) -> None:
        """Apply schema via Alembic (upgrade to head)."""
        from alembic import command
        from alembic.config import Config
        from pathlib import Path

        base_dir = Path(__file__).resolve().parents[2]
        ini_path = base_dir / "alembic.ini"
        alembic_cfg = Config(str(ini_path))
        alembic_cfg.set_main_option("script_location", str(base_dir / "alembic"))
        alembic_cfg.set_main_option("sqlalchemy.url", self.url)
        command.upgrade(alembic_cfg, "head")

    def create_all(self) -> None:
        """Create tables from ORM metadata (used in tests)."""
        with self.engine.begin() as conn:
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS citext"))
        Base.metadata.create_all(self.engine)

    def drop_all(self) -> None:
        Base.metadata.drop_all(self.engine)

    @contextmanager
    def session(self) -> Iterator[Session]:
        with self._lock:
            db_session = self._session_factory()
            try:
                yield db_session
                db_session.commit()
            except Exception:
                db_session.rollback()
                raise
            finally:
                db_session.close()


def create_database(settings: Settings) -> Database:
    return Database(settings.database_url)


def row_to_dict(row) -> dict | None:
    from backend.app.db.util import as_dict

    return as_dict(row)
