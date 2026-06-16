"""sha1 user ids — users.id and FKs become CHAR(40) SHA1(email)

Revision ID: 20260616_1600
Revises: 20260616_1200
Create Date: 2026-06-16 16:00:00

ARCH §3.5.0, §3.7, PRD §5.2.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260616_1600"
down_revision: str | None = "20260616_1200"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")

    # users: добавляем id_new = SHA1(email).
    op.execute("ALTER TABLE users ADD COLUMN id_new VARCHAR(40)")
    op.execute("UPDATE users SET id_new = encode(digest(lower(email), 'sha1'), 'hex')")
    op.execute("ALTER TABLE users ALTER COLUMN id_new SET NOT NULL")

    # Каждое FK-таблица: перевод user_id на новые значения.
    for tbl in ("refresh_tokens", "cli_auth_codes", "device_codes"):
        op.execute(f"ALTER TABLE {tbl} ADD COLUMN user_id_new VARCHAR(40)")
        op.execute(
            f"UPDATE {tbl} t SET user_id_new = u.id_new "  # noqa: S608
            "FROM users u WHERE t.user_id = u.id"
        )

    # cli_auth_codes/device_codes: user_id NULLABLE, после копирования может быть NULL.
    op.execute("ALTER TABLE refresh_tokens ALTER COLUMN user_id_new SET NOT NULL")

    # Дропаем FK-констрейнты и старые колонки.
    for tbl, fk_name in (
        ("refresh_tokens", "refresh_tokens_user_id_fkey"),
        ("cli_auth_codes", "cli_auth_codes_user_id_fkey"),
        ("device_codes", "device_codes_user_id_fkey"),
    ):
        op.execute(f"ALTER TABLE {tbl} DROP CONSTRAINT IF EXISTS {fk_name}")
        op.execute(f"ALTER TABLE {tbl} DROP COLUMN user_id")
        op.execute(f"ALTER TABLE {tbl} RENAME COLUMN user_id_new TO user_id")

    # users: меняем PK с UUID id на CHAR(40) id_new.
    op.execute("ALTER TABLE users DROP CONSTRAINT users_pkey")
    op.execute("ALTER TABLE users DROP COLUMN id")
    op.execute("ALTER TABLE users RENAME COLUMN id_new TO id")
    op.execute("ALTER TABLE users ADD PRIMARY KEY (id)")

    # Восстанавливаем FK.
    op.create_foreign_key(
        "refresh_tokens_user_id_fkey",
        "refresh_tokens",
        "users",
        ["user_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "cli_auth_codes_user_id_fkey",
        "cli_auth_codes",
        "users",
        ["user_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "device_codes_user_id_fkey",
        "device_codes",
        "users",
        ["user_id"],
        ["id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    # Одноразовая миграция — даунгрейд не поддерживается.
    raise NotImplementedError(
        "sha1 user-id migration is one-way (PRD §5.2, ARCH §3.7.4)"
    )


# Reference imports kept for tooling
_ = sa
