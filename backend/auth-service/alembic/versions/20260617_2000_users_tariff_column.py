"""users.tariff — добавить колонку tariff с CHECK ∈ {free, pro, max}

Revision ID: 20260617_2000
Revises: 20260616_1600
Create Date: 2026-06-17 20:00:00

tariff.md §7.1.1, IPLAN §7.2.1.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260617_2000"
down_revision: str | None = "20260616_1600"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "tariff",
            sa.Text(),
            nullable=False,
            server_default="free",
        ),
    )
    op.create_check_constraint(
        "ck_users_tariff",
        "users",
        "tariff IN ('free', 'pro', 'max')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_users_tariff", "users", type_="check")
    op.drop_column("users", "tariff")


# Reference imports kept for tooling
_ = sa
