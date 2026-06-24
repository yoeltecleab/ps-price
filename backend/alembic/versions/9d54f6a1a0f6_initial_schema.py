"""initial schema

Revision ID: 9d54f6a1a0f6
Revises:
Create Date: 2026-06-24 14:46:13.365803

Greenfield initial migration: create all tables from ORM metadata.
(citext extension is created in alembic/env.py before migrations run.)
"""

from typing import Sequence, Union

from alembic import op

revision: str = "9d54f6a1a0f6"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    from backend.app.db import models  # noqa: F401
    from backend.app.db.base import Base

    Base.metadata.create_all(bind=op.get_bind())


def downgrade() -> None:
    from backend.app.db import models  # noqa: F401
    from backend.app.db.base import Base

    Base.metadata.drop_all(bind=op.get_bind())
