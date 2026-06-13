"""initial schema — users, magic_tokens, refresh_tokens, sessions, cli_auth_codes, device_codes

Revision ID: 20260613_1200
Revises:
Create Date: 2026-06-13 12:00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260613_1200"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    op.create_table(
        "magic_tokens",
        sa.Column("token_hash", sa.String(128), primary_key=True),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("intent", sa.String(20), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_magic_tokens_email", "magic_tokens", ["email"])
    op.create_index("ix_magic_tokens_email_expires", "magic_tokens", ["email", "expires_at"])

    op.create_table(
        "refresh_tokens",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("token_hash", sa.String(128), nullable=False),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("label", sa.String(200), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_refresh_tokens_token_hash", "refresh_tokens", ["token_hash"], unique=True)
    op.create_index("ix_refresh_tokens_user_revoked", "refresh_tokens", ["user_id", "revoked_at"])

    op.create_table(
        "sessions",
        sa.Column(
            "refresh_token_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("refresh_tokens.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("user_agent", sa.String(500), nullable=False, server_default=""),
    )

    op.create_table(
        "cli_auth_codes",
        sa.Column("state", sa.String(128), primary_key=True),
        sa.Column("code_challenge", sa.String(128), nullable=False),
        sa.Column("code_hash", sa.String(128), nullable=True),
        sa.Column("code_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_cli_auth_codes_code_hash", "cli_auth_codes", ["code_hash"], unique=True
    )

    op.create_table(
        "device_codes",
        sa.Column("device_code", sa.String(128), primary_key=True),
        sa.Column("user_code", sa.String(20), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_device_codes_user_code", "device_codes", ["user_code"], unique=True)


def downgrade() -> None:
    op.drop_table("device_codes")
    op.drop_table("cli_auth_codes")
    op.drop_table("sessions")
    op.drop_table("refresh_tokens")
    op.drop_table("magic_tokens")
    op.drop_table("users")
