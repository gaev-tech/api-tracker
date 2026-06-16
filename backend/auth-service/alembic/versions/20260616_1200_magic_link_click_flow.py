"""magic-link click flow — drop intent, add session/confirmed/delivered cols

Revision ID: 20260616_1200
Revises: 20260613_1200
Create Date: 2026-06-16 12:00:00

ARCH §3.6.2, §4.2.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260616_1200"
down_revision: str | None = "20260613_1200"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Включить pgcrypto для gen_random_uuid() — нужен только для backfill
    # существующих строк; новые поставляем явно с серверной стороны.
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")

    op.add_column(
        "magic_tokens",
        sa.Column(
            "login_session_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
    )
    op.execute(
        "UPDATE magic_tokens SET login_session_id = gen_random_uuid() "
        "WHERE login_session_id IS NULL"
    )
    op.alter_column(
        "magic_tokens",
        "login_session_id",
        existing_type=postgresql.UUID(as_uuid=True),
        nullable=False,
    )
    op.create_unique_constraint(
        "uq_magic_tokens_login_session_id", "magic_tokens", ["login_session_id"]
    )

    op.add_column(
        "magic_tokens",
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
    )
    # delivered_at — внутренний маркер однократной выдачи (ARCH §4.2.4.2).
    op.add_column(
        "magic_tokens",
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.drop_column("magic_tokens", "intent")


def downgrade() -> None:
    op.add_column(
        "magic_tokens",
        sa.Column("intent", sa.String(20), nullable=True),
    )
    op.execute("UPDATE magic_tokens SET intent = 'cli' WHERE intent IS NULL")
    op.alter_column(
        "magic_tokens", "intent", existing_type=sa.String(20), nullable=False
    )
    op.drop_column("magic_tokens", "delivered_at")
    op.drop_column("magic_tokens", "confirmed_at")
    op.drop_constraint(
        "uq_magic_tokens_login_session_id", "magic_tokens", type_="unique"
    )
    op.drop_column("magic_tokens", "login_session_id")
