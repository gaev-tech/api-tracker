from datetime import UTC, datetime
from enum import StrEnum

from sqlalchemy import (
    ARRAY,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


_SID = 40  # SHA1 hex (PRD §5.2.6, ARCH §3.5.0)


class TaskStatus(StrEnum):
    OPEN = "open"
    DONE = "done"
    ARCHIVED = "archived"


# === Permission catalogues (PRD §6.3-6.5) ===


class TaskPermission(StrEnum):
    """Гранулярные флаги доступа к задаче (PRD §6.3)."""

    EDIT_TITLE = "edit_title"
    EDIT_DESCRIPTION = "edit_description"
    EDIT_LABELS = "edit_labels"
    EDIT_BLOCKERS = "edit_blockers"
    EDIT_STATUS = "edit_status"
    EDIT_ASSIGNEE = "edit_assignee"
    MANAGE_PROJECTS = "manage_projects"
    SHARE = "share"


class TeamPermission(StrEnum):
    """Разрешения в контексте команды (PRD §6.4)."""

    EDIT_TEAM_NAME = "edit_team_name"
    MANAGE_MEMBER_PERMISSIONS = "manage_member_permissions"


class ProjectPermission(StrEnum):
    """Project-уровневые разрешения (PRD §6.5.1-§6.5.4).

    В проекте также действуют все task-уровневые перм-флаги — они хранятся в
    том же массиве perms на ProjectUserMember/ProjectTeamMember и применяются
    ко всем задачам проекта (PRD §6.5.5).
    """

    EDIT_PROJECT_NAME = "edit_project_name"
    MANAGE_MEMBER_PERMISSIONS = "manage_member_permissions"
    MANAGE_AUTOMATIONS = "manage_automations"
    MANAGE_SECRETS = "manage_secrets"


def _utcnow() -> datetime:
    return datetime.now(UTC)


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(_SID), primary_key=True)
    email: Mapped[str] = mapped_column(
        String(320), unique=True, index=True, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[str] = mapped_column(String(_SID), primary_key=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description_md: Mapped[str] = mapped_column(Text, default="", nullable=False)
    labels: Mapped[list[str]] = mapped_column(
        ARRAY(String(100)), default=list, nullable=False
    )
    status: Mapped[TaskStatus] = mapped_column(
        String(20), default=TaskStatus.OPEN, nullable=False
    )
    assignee_id: Mapped[str] = mapped_column(
        String(_SID),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False, index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )

    blockers: Mapped[list["TaskBlocker"]] = relationship(
        "TaskBlocker",
        foreign_keys="TaskBlocker.task_id",
        cascade="all, delete-orphan",
        back_populates="task",
    )

    __table_args__ = (Index("ix_tasks_status_created_at", "status", "created_at"),)


class TaskBlocker(Base):
    __tablename__ = "task_blockers"

    task_id: Mapped[str] = mapped_column(
        String(_SID),
        ForeignKey("tasks.id", ondelete="CASCADE"),
        primary_key=True,
    )
    blocked_by_task_id: Mapped[str] = mapped_column(
        String(_SID),
        ForeignKey("tasks.id", ondelete="CASCADE"),
        primary_key=True,
    )

    task: Mapped[Task] = relationship(
        "Task", foreign_keys=[task_id], back_populates="blockers"
    )


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[str] = mapped_column(String(_SID), primary_key=True)
    actor_user_id: Mapped[str] = mapped_column(
        String(_SID),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    target_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    target_id: Mapped[str] = mapped_column(String(_SID), nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    payload: Mapped[dict[str, object]] = mapped_column(
        JSONB, default=dict, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False, index=True
    )

    __table_args__ = (
        Index("ix_audit_events_target", "target_type", "target_id", "created_at"),
    )


# === Sharing / membership tables (M2) ===


class Team(Base):
    """Команда — именованный набор пользователей (PRD §5.1.3)."""

    __tablename__ = "teams"

    id: Mapped[str] = mapped_column(String(_SID), primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )


class TeamMember(Base):
    """Член команды с набором разрешений (PRD §6.4)."""

    __tablename__ = "team_members"

    team_id: Mapped[str] = mapped_column(
        String(_SID),
        ForeignKey("teams.id", ondelete="CASCADE"),
        primary_key=True,
    )
    user_id: Mapped[str] = mapped_column(
        String(_SID),
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    perms: Mapped[list[str]] = mapped_column(
        ARRAY(String(50)), default=list, nullable=False, server_default="{}"
    )


class Project(Base):
    """Проект — коллекция задач + участники (PRD §5.1.4)."""

    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String(_SID), primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )


class ProjectUserMember(Base):
    """Пользователь — участник проекта (PRD §6.5)."""

    __tablename__ = "project_user_members"

    project_id: Mapped[str] = mapped_column(
        String(_SID),
        ForeignKey("projects.id", ondelete="CASCADE"),
        primary_key=True,
    )
    user_id: Mapped[str] = mapped_column(
        String(_SID),
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    perms: Mapped[list[str]] = mapped_column(
        ARRAY(String(50)), default=list, nullable=False, server_default="{}"
    )


class ProjectTeamMember(Base):
    """Команда — участник проекта."""

    __tablename__ = "project_team_members"

    project_id: Mapped[str] = mapped_column(
        String(_SID),
        ForeignKey("projects.id", ondelete="CASCADE"),
        primary_key=True,
    )
    team_id: Mapped[str] = mapped_column(
        String(_SID),
        ForeignKey("teams.id", ondelete="CASCADE"),
        primary_key=True,
    )
    perms: Mapped[list[str]] = mapped_column(
        ARRAY(String(50)), default=list, nullable=False, server_default="{}"
    )


class ProjectTask(Base):
    """Задача в проекте (PRD §5.1.4)."""

    __tablename__ = "project_tasks"

    project_id: Mapped[str] = mapped_column(
        String(_SID),
        ForeignKey("projects.id", ondelete="CASCADE"),
        primary_key=True,
    )
    task_id: Mapped[str] = mapped_column(
        String(_SID),
        ForeignKey("tasks.id", ondelete="CASCADE"),
        primary_key=True,
    )


class TaskUserShare(Base):
    """Прямой шаринг задачи пользователю (PRD §6.2.1.1, Path A user-share)."""

    __tablename__ = "task_user_shares"

    task_id: Mapped[str] = mapped_column(
        String(_SID),
        ForeignKey("tasks.id", ondelete="CASCADE"),
        primary_key=True,
    )
    user_id: Mapped[str] = mapped_column(
        String(_SID),
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    perms: Mapped[list[str]] = mapped_column(
        ARRAY(String(50)), default=list, nullable=False, server_default="{}"
    )


class TaskTeamShare(Base):
    """Прямой шаринг задачи команде (PRD §6.2.1.1, Path A team-share)."""

    __tablename__ = "task_team_shares"

    task_id: Mapped[str] = mapped_column(
        String(_SID),
        ForeignKey("tasks.id", ondelete="CASCADE"),
        primary_key=True,
    )
    team_id: Mapped[str] = mapped_column(
        String(_SID),
        ForeignKey("teams.id", ondelete="CASCADE"),
        primary_key=True,
    )
    perms: Mapped[list[str]] = mapped_column(
        ARRAY(String(50)), default=list, nullable=False, server_default="{}"
    )


# === Automations / secrets / event-log / webhook-outbox (M3) ===


class AutomationTriggerType(StrEnum):
    """Тип триггера автоматизации (PRD §8.4)."""

    EVENT = "event"
    CRON = "cron"


class AutomationActionType(StrEnum):
    """Тип действия автоматизации (PRD §8.5)."""

    WEBHOOK = "webhook"
    SYSTEM_METHOD = "system_method"


class WebhookOutboxStatus(StrEnum):
    """Статус записи в очереди webhook-доставки (PRD §8.6, ARCH §12)."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    SENT = "sent"
    DEAD_LETTER = "dead_letter"


class Automation(Base):
    """Автоматизация проекта (PRD §5.1.5, §8, ARCH §3.5.12, §11)."""

    __tablename__ = "automations"

    id: Mapped[str] = mapped_column(String(_SID), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        String(_SID),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    trigger_type: Mapped[AutomationTriggerType] = mapped_column(
        String(20), nullable=False
    )
    trigger_config: Mapped[dict[str, object]] = mapped_column(
        JSONB, default=dict, nullable=False
    )
    action_type: Mapped[AutomationActionType] = mapped_column(
        String(20), nullable=False
    )
    action_config: Mapped[dict[str, object]] = mapped_column(
        JSONB, default=dict, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )


class ProjectSecret(Base):
    """Зашифрованный секрет проекта (PRD §5.1.6, §8.7, ARCH §3.5.13, §13)."""

    __tablename__ = "project_secrets"

    id: Mapped[str] = mapped_column(String(_SID), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        String(_SID),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    value_encrypted: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )

    __table_args__ = (
        UniqueConstraint("project_id", "name", name="uq_project_secrets_project_name"),
    )


class EventLog(Base):
    """Журнал событий мутаций задач для reactive matcher (ARCH §3.5.15, §11.2)."""

    __tablename__ = "event_log"

    id: Mapped[str] = mapped_column(String(_SID), primary_key=True)
    source_task_id: Mapped[str] = mapped_column(
        String(_SID),
        ForeignKey("tasks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    payload: Mapped[dict[str, object]] = mapped_column(
        JSONB, default=dict, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False, index=True
    )
    processed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    __table_args__ = (Index("ix_event_log_unprocessed", "processed_at", "created_at"),)


class WebhookOutbox(Base):
    """Очередь доставки webhook-действий с retry (ARCH §3.5.16, §12)."""

    __tablename__ = "webhook_outbox"

    id: Mapped[str] = mapped_column(String(_SID), primary_key=True)
    automation_id: Mapped[str] = mapped_column(
        String(_SID),
        ForeignKey("automations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    attempt: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    scheduled_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False, index=True
    )
    status: Mapped[WebhookOutboxStatus] = mapped_column(
        String(20),
        default=WebhookOutboxStatus.PENDING,
        nullable=False,
    )
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    payload: Mapped[dict[str, object]] = mapped_column(
        JSONB, default=dict, nullable=False
    )

    __table_args__ = (Index("ix_webhook_outbox_ready", "status", "scheduled_at"),)
