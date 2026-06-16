from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator

from tasks_service.models import TaskStatus

# SHA1 hex (PRD §5.2.6), либо префикс ≥4 hex-символов (PRD §5.2.7).
EntityKey = Annotated[
    str,
    Field(
        min_length=4,
        max_length=40,
        pattern=r"^[0-9a-f]+$",
        description="SHA1 key or unique prefix (PRD §5.2)",
    ),
]


class TaskCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: Annotated[str, Field(min_length=1, max_length=500)]
    description_md: str = ""
    labels: list[Annotated[str, Field(min_length=1, max_length=100)]] = Field(
        default_factory=list
    )
    status: TaskStatus = TaskStatus.OPEN
    blocked_by: list[EntityKey] = Field(default_factory=list)

    @field_validator("labels")
    @classmethod
    def _labels_unique(cls, v: list[str]) -> list[str]:
        if len(set(v)) != len(v):
            raise ValueError("duplicate label")
        return v


class TaskUpdate(BaseModel):
    """Patch — все поля опциональны."""

    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, min_length=1, max_length=500)
    description_md: str | None = None
    labels: list[str] | None = None
    status: TaskStatus | None = None
    add_labels: list[str] | None = None
    remove_labels: list[str] | None = None
    add_blockers: list[EntityKey] | None = None
    remove_blockers: list[EntityKey] | None = None


class TaskRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    title: str
    description_md: str
    labels: list[str]
    status: TaskStatus
    assignee_email: str
    blocked_by: list[str] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class TaskListPage(BaseModel):
    items: list[TaskRead]
    next_cursor: str | None = None


class BulkPatchRequest(BaseModel):
    """Один патч применяется ко всем совпавшим задачам (architecture.md §9)."""

    model_config = ConfigDict(extra="forbid")

    patch: TaskUpdate


class BulkResultItem(BaseModel):
    task_id: str
    status: str  # "ok" | "forbidden" | "validation_failed" | "not_found"
    error: str | None = None


class BulkResult(BaseModel):
    results: list[BulkResultItem]
    total: int
    succeeded: int


class BatchResult(BaseModel):
    affected: int


class BulkCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[TaskCreate]


class BulkCreateResultItem(BaseModel):
    index: int
    status: str
    task_id: str | None = None
    error: str | None = None


class BulkCreateResult(BaseModel):
    results: list[BulkCreateResultItem]


class BatchCreateResult(BaseModel):
    task_ids: list[str]


class HistoryEvent(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    actor_email: str
    target_type: str
    target_id: str
    event_type: str
    payload: dict[str, object]
    created_at: datetime


class HistoryPage(BaseModel):
    items: list[HistoryEvent]
    next_cursor: str | None = None


class ErrorResponse(BaseModel):
    error: str
    detail: str | None = None


# === Team CRUD (M2.7) ===


class TeamCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Annotated[str, Field(min_length=1, max_length=200)]


class TeamUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Annotated[str, Field(min_length=1, max_length=200)]


class TeamMemberSetRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    perms: list[str] = Field(default_factory=list)


class TeamMemberRead(BaseModel):
    user_email: str
    perms: list[str]


class TeamRead(BaseModel):
    id: str
    name: str
    created_at: datetime
    members: list[TeamMemberRead] = Field(default_factory=list)


# === Project CRUD (M2.7) ===


class ProjectCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Annotated[str, Field(min_length=1, max_length=200)]


class ProjectUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Annotated[str, Field(min_length=1, max_length=200)]


class ProjectMemberSetRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    perms: list[str] = Field(default_factory=list)


class ProjectUserMemberRead(BaseModel):
    user_email: str
    perms: list[str]


class ProjectTeamMemberRead(BaseModel):
    team_id: str
    team_name: str
    perms: list[str]


class ProjectRead(BaseModel):
    id: str
    name: str
    created_at: datetime
    user_members: list[ProjectUserMemberRead] = Field(default_factory=list)
    team_members: list[ProjectTeamMemberRead] = Field(default_factory=list)
    task_ids: list[str] = Field(default_factory=list)


# === Task shares (M2.7c) ===


class ShareSetRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    perms: list[str] = Field(default_factory=list)


class TaskShareUserRead(BaseModel):
    user_email: str
    perms: list[str]


class TaskShareTeamRead(BaseModel):
    team_id: str
    team_name: str
    perms: list[str]


class TaskSharesRead(BaseModel):
    user_shares: list[TaskShareUserRead] = Field(default_factory=list)
    team_shares: list[TaskShareTeamRead] = Field(default_factory=list)
