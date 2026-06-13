from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import ARRAY, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


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

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description_md: Mapped[str] = mapped_column(Text, default="", nullable=False)
    labels: Mapped[list[str]] = mapped_column(ARRAY(String(100)), default=list, nullable=False)
    status: Mapped[TaskStatus] = mapped_column(String(20), default=TaskStatus.OPEN, nullable=False)
    assignee_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
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

    task_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("tasks.id", ondelete="CASCADE"), primary_key=True
    )
    blocked_by_task_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("tasks.id", ondelete="CASCADE"), primary_key=True
    )

    task: Mapped[Task] = relationship("Task", foreign_keys=[task_id], back_populates="blockers")


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    actor_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    target_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    target_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    payload: Mapped[dict[str, object]] = mapped_column(JSONB, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False, index=True
    )

    __table_args__ = (Index("ix_audit_events_target", "target_type", "target_id", "created_at"),)


# === Sharing / membership tables (M2) ===


class Team(Base):
    """Команда — именованный набор пользователей (PRD §5.1.3)."""

    __tablename__ = "teams"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )


class TeamMember(Base):
    """Член команды с набором разрешений (PRD §6.4)."""

    __tablename__ = "team_members"

    team_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("teams.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    perms: Mapped[list[str]] = mapped_column(
        ARRAY(String(50)), default=list, nullable=False, server_default="{}"
    )


class Project(Base):
    """Проект — коллекция задач + участники (PRD §5.1.4)."""

    __tablename__ = "projects"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )


class ProjectUserMember(Base):
    """Пользователь — участник проекта (PRD §6.5)."""

    __tablename__ = "project_user_members"

    project_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    perms: Mapped[list[str]] = mapped_column(
        ARRAY(String(50)), default=list, nullable=False, server_default="{}"
    )


class ProjectTeamMember(Base):
    """Команда — участник проекта."""

    __tablename__ = "project_team_members"

    project_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), primary_key=True
    )
    team_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("teams.id", ondelete="CASCADE"), primary_key=True
    )
    perms: Mapped[list[str]] = mapped_column(
        ARRAY(String(50)), default=list, nullable=False, server_default="{}"
    )


class ProjectTask(Base):
    """Задача в проекте (PRD §5.1.4)."""

    __tablename__ = "project_tasks"

    project_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), primary_key=True
    )
    task_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("tasks.id", ondelete="CASCADE"), primary_key=True
    )


class TaskUserShare(Base):
    """Прямой шаринг задачи пользователю (PRD §6.2.1.1, Path A user-share)."""

    __tablename__ = "task_user_shares"

    task_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("tasks.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    perms: Mapped[list[str]] = mapped_column(
        ARRAY(String(50)), default=list, nullable=False, server_default="{}"
    )


class TaskTeamShare(Base):
    """Прямой шаринг задачи команде (PRD §6.2.1.1, Path A team-share)."""

    __tablename__ = "task_team_shares"

    task_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("tasks.id", ondelete="CASCADE"), primary_key=True
    )
    team_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("teams.id", ondelete="CASCADE"), primary_key=True
    )
    perms: Mapped[list[str]] = mapped_column(
        ARRAY(String(50)), default=list, nullable=False, server_default="{}"
    )
