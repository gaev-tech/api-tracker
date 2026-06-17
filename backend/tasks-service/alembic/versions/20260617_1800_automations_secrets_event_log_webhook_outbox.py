"""automations, project_secrets, event_log, webhook_outbox (M3.1)

Revision ID: 20260617_1800
Revises: 20260616_1700
Create Date: 2026-06-17 18:00:00

ARCH §3.5.12–§3.5.16. id-колонки — CHAR(40) SHA1 (PRD §5.2.6).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260617_1800"
down_revision: str | None = "20260616_1700"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "automations",
        sa.Column("id", sa.CHAR(40), primary_key=True),
        sa.Column(
            "project_id",
            sa.CHAR(40),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("trigger_type", sa.String(20), nullable=False),
        sa.Column(
            "trigger_config",
            postgresql.JSONB,
            nullable=False,
            server_default="{}",
        ),
        sa.Column("action_type", sa.String(20), nullable=False),
        sa.Column(
            "action_config",
            postgresql.JSONB,
            nullable=False,
            server_default="{}",
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_automations_project_id", "automations", ["project_id"])

    op.create_table(
        "project_secrets",
        sa.Column("id", sa.CHAR(40), primary_key=True),
        sa.Column(
            "project_id",
            sa.CHAR(40),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("value_encrypted", sa.LargeBinary, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "project_id", "name", name="uq_project_secrets_project_name"
        ),
    )
    op.create_index("ix_project_secrets_project_id", "project_secrets", ["project_id"])

    op.create_table(
        "event_log",
        sa.Column("id", sa.CHAR(40), primary_key=True),
        sa.Column(
            "source_task_id",
            sa.CHAR(40),
            sa.ForeignKey("tasks.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("event_type", sa.String(100), nullable=False),
        sa.Column(
            "payload",
            postgresql.JSONB,
            nullable=False,
            server_default="{}",
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_event_log_source_task_id", "event_log", ["source_task_id"])
    op.create_index("ix_event_log_created_at", "event_log", ["created_at"])
    op.create_index(
        "ix_event_log_unprocessed", "event_log", ["processed_at", "created_at"]
    )

    op.create_table(
        "webhook_outbox",
        sa.Column("id", sa.CHAR(40), primary_key=True),
        sa.Column(
            "automation_id",
            sa.CHAR(40),
            sa.ForeignKey("automations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("attempt", sa.Integer, nullable=False, server_default=sa.text("1")),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "status",
            sa.String(20),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("last_error", sa.Text, nullable=True),
        sa.Column(
            "payload",
            postgresql.JSONB,
            nullable=False,
            server_default="{}",
        ),
    )
    op.create_index(
        "ix_webhook_outbox_automation_id", "webhook_outbox", ["automation_id"]
    )
    op.create_index(
        "ix_webhook_outbox_scheduled_at", "webhook_outbox", ["scheduled_at"]
    )
    op.create_index(
        "ix_webhook_outbox_ready", "webhook_outbox", ["status", "scheduled_at"]
    )


def downgrade() -> None:
    op.drop_table("webhook_outbox")
    op.drop_table("event_log")
    op.drop_table("project_secrets")
    op.drop_table("automations")
