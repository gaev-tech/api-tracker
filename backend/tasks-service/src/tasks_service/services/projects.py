"""Сервис проектов: CRUD, members (user/team), project_tasks (PRD §6.5, §5.1.4)."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from tasks_service.models import (
    Project,
    ProjectPermission,
    ProjectTask,
    ProjectTeamMember,
    ProjectUserMember,
    TaskPermission,
    TeamMember,
    User,
)
from tasks_service.services.audit import record_audit


class ProjectError(Exception):
    pass


class ProjectNotFound(ProjectError):
    pass


class PermissionDenied(ProjectError):
    pass


class CannotGrantAboveSelf(ProjectError):
    pass


# Какие perms-строки валидны для project_user_members.perms.
_VALID_PROJECT_PERMS: set[str] = {p.value for p in ProjectPermission} | {
    p.value for p in TaskPermission
}


def _check_within_self(target_perms: list[str], own_perms: list[str]) -> None:
    extras = set(target_perms) - set(own_perms)
    if extras:
        raise CannotGrantAboveSelf(f"cannot grant perms above own: {sorted(extras)}")


def _require_perm(member: ProjectUserMember | None, perm: ProjectPermission) -> None:
    if member is None or perm.value not in member.perms:
        raise PermissionDenied(f"missing project permission: {perm.value}")


async def _get_project(session: AsyncSession, project_id: UUID) -> Project:
    result = await session.execute(select(Project).where(Project.id == project_id))
    p = result.scalar_one_or_none()
    if p is None:
        raise ProjectNotFound(str(project_id))
    return p


async def _get_user_member(
    session: AsyncSession, project_id: UUID, user_id: UUID
) -> ProjectUserMember | None:
    result = await session.execute(
        select(ProjectUserMember).where(
            ProjectUserMember.project_id == project_id,
            ProjectUserMember.user_id == user_id,
        )
    )
    return result.scalar_one_or_none()


async def _get_team_member(
    session: AsyncSession, project_id: UUID, team_id: UUID
) -> ProjectTeamMember | None:
    result = await session.execute(
        select(ProjectTeamMember).where(
            ProjectTeamMember.project_id == project_id,
            ProjectTeamMember.team_id == team_id,
        )
    )
    return result.scalar_one_or_none()


async def create_project(session: AsyncSession, *, creator: User, name: str) -> Project:
    """Создаёт проект; создатель — единственный участник со всеми правами
    (project- + task-уровневыми)."""
    if not name.strip():
        raise ProjectError("project name cannot be empty")
    project = Project(name=name.strip())
    session.add(project)
    await session.flush()
    full_perms = sorted(_VALID_PROJECT_PERMS)
    session.add(ProjectUserMember(project_id=project.id, user_id=creator.id, perms=full_perms))
    await session.flush()
    await record_audit(
        session,
        actor_user_id=creator.id,
        target_type="project",
        target_id=project.id,
        event_type="project.created",
        payload={"name": project.name},
    )
    return project


async def get_project(session: AsyncSession, *, current: User, project_id: UUID) -> Project:
    project = await _get_project(session, project_id)
    member = await _get_user_member(session, project.id, current.id)
    if member is None or not member.perms:
        raise PermissionDenied("not a member of project")
    return project


async def update_name(
    session: AsyncSession, *, current: User, project_id: UUID, new_name: str
) -> Project:
    project = await _get_project(session, project_id)
    member = await _get_user_member(session, project.id, current.id)
    _require_perm(member, ProjectPermission.EDIT_PROJECT_NAME)
    if not new_name.strip():
        raise ProjectError("project name cannot be empty")
    old = project.name
    project.name = new_name.strip()
    await session.flush()
    await record_audit(
        session,
        actor_user_id=current.id,
        target_type="project",
        target_id=project.id,
        event_type="project.renamed",
        payload={"old": old, "new": project.name},
    )
    return project


async def set_user_member(
    session: AsyncSession,
    *,
    current: User,
    project_id: UUID,
    target_user_id: UUID,
    perms: list[str],
) -> ProjectUserMember | None:
    """Add/edit/remove participant пользователя по правилам PRD §6.1.7 и §6.5.2."""
    project = await _get_project(session, project_id)
    current_member = await _get_user_member(session, project.id, current.id)
    if current.id == target_user_id:
        if perms:
            _check_within_self(perms, current_member.perms if current_member else [])
    else:
        _require_perm(current_member, ProjectPermission.MANAGE_MEMBER_PERMISSIONS)
        _check_within_self(perms, current_member.perms if current_member else [])

    invalid = [p for p in perms if p not in _VALID_PROJECT_PERMS]
    if invalid:
        raise ProjectError(f"unknown project permissions: {invalid}")

    if not perms:
        existing = await _get_user_member(session, project.id, target_user_id)
        if existing is None:
            return None
        await session.delete(existing)
        await session.flush()
        await record_audit(
            session,
            actor_user_id=current.id,
            target_type="project",
            target_id=project.id,
            event_type="project.user_removed",
            payload={"user_id": str(target_user_id)},
        )
        await _maybe_cascade_delete(session, project)
        return None

    stmt = (
        pg_insert(ProjectUserMember)
        .values(project_id=project.id, user_id=target_user_id, perms=perms)
        .on_conflict_do_update(index_elements=["project_id", "user_id"], set_={"perms": perms})
        .returning(ProjectUserMember)
    )
    result = await session.execute(stmt)
    member = result.scalar_one()
    await session.flush()
    await record_audit(
        session,
        actor_user_id=current.id,
        target_type="project",
        target_id=project.id,
        event_type="project.user_set",
        payload={"user_id": str(target_user_id), "perms": perms},
    )
    return member


async def set_team_member(
    session: AsyncSession,
    *,
    current: User,
    project_id: UUID,
    target_team_id: UUID,
    perms: list[str],
) -> ProjectTeamMember | None:
    """Установить разрешения команды в проекте. Шарящий должен сам быть в команде
    (PRD §6.7.2)."""
    project = await _get_project(session, project_id)
    current_member = await _get_user_member(session, project.id, current.id)
    _require_perm(current_member, ProjectPermission.MANAGE_MEMBER_PERMISSIONS)
    _check_within_self(perms, current_member.perms if current_member else [])

    if perms:
        # Шарить команде можно, только будучи её членом (PRD §6.7.2).
        in_team = await session.execute(
            select(TeamMember.user_id).where(
                TeamMember.team_id == target_team_id, TeamMember.user_id == current.id
            )
        )
        if in_team.scalar_one_or_none() is None:
            raise PermissionDenied("must be a member of the team to share with it")

    invalid = [p for p in perms if p not in _VALID_PROJECT_PERMS]
    if invalid:
        raise ProjectError(f"unknown project permissions: {invalid}")

    if not perms:
        existing = await _get_team_member(session, project.id, target_team_id)
        if existing is None:
            return None
        await session.delete(existing)
        await session.flush()
        await record_audit(
            session,
            actor_user_id=current.id,
            target_type="project",
            target_id=project.id,
            event_type="project.team_removed",
            payload={"team_id": str(target_team_id)},
        )
        await _maybe_cascade_delete(session, project)
        return None

    stmt = (
        pg_insert(ProjectTeamMember)
        .values(project_id=project.id, team_id=target_team_id, perms=perms)
        .on_conflict_do_update(index_elements=["project_id", "team_id"], set_={"perms": perms})
        .returning(ProjectTeamMember)
    )
    result = await session.execute(stmt)
    member = result.scalar_one()
    await session.flush()
    await record_audit(
        session,
        actor_user_id=current.id,
        target_type="project",
        target_id=project.id,
        event_type="project.team_set",
        payload={"team_id": str(target_team_id), "perms": perms},
    )
    return member


async def add_task_to_project(
    session: AsyncSession, *, current: User, project_id: UUID, task_id: UUID
) -> None:
    """Добавить задачу в проект. Требует manage_projects на проекте (PRD §6.5.5)."""
    project = await _get_project(session, project_id)
    member = await _get_user_member(session, project.id, current.id)
    if member is None or TaskPermission.MANAGE_PROJECTS.value not in member.perms:
        raise PermissionDenied(
            f"missing project permission: {TaskPermission.MANAGE_PROJECTS.value}"
        )
    stmt = (
        pg_insert(ProjectTask)
        .values(project_id=project.id, task_id=task_id)
        .on_conflict_do_nothing()
    )
    await session.execute(stmt)
    await session.flush()
    await record_audit(
        session,
        actor_user_id=current.id,
        target_type="project",
        target_id=project.id,
        event_type="project.task_added",
        payload={"task_id": str(task_id)},
    )


async def remove_task_from_project(
    session: AsyncSession, *, current: User, project_id: UUID, task_id: UUID
) -> None:
    project = await _get_project(session, project_id)
    member = await _get_user_member(session, project.id, current.id)
    if member is None or TaskPermission.MANAGE_PROJECTS.value not in member.perms:
        raise PermissionDenied(
            f"missing project permission: {TaskPermission.MANAGE_PROJECTS.value}"
        )
    result = await session.execute(
        select(ProjectTask).where(
            ProjectTask.project_id == project.id, ProjectTask.task_id == task_id
        )
    )
    existing = result.scalar_one_or_none()
    if existing is None:
        return
    await session.delete(existing)
    await session.flush()
    await record_audit(
        session,
        actor_user_id=current.id,
        target_type="project",
        target_id=project.id,
        event_type="project.task_removed",
        payload={"task_id": str(task_id)},
    )


async def list_user_members(session: AsyncSession, *, project_id: UUID) -> list[ProjectUserMember]:
    result = await session.execute(
        select(ProjectUserMember)
        .where(ProjectUserMember.project_id == project_id)
        .order_by(ProjectUserMember.user_id)
    )
    return list(result.scalars().all())


async def list_team_members(session: AsyncSession, *, project_id: UUID) -> list[ProjectTeamMember]:
    result = await session.execute(
        select(ProjectTeamMember)
        .where(ProjectTeamMember.project_id == project_id)
        .order_by(ProjectTeamMember.team_id)
    )
    return list(result.scalars().all())


async def list_project_tasks(session: AsyncSession, *, project_id: UUID) -> list[UUID]:
    result = await session.execute(
        select(ProjectTask.task_id).where(ProjectTask.project_id == project_id)
    )
    return list(result.scalars().all())


async def _maybe_cascade_delete(session: AsyncSession, project: Project) -> None:
    """Удаляем проект, если не осталось ни одного user-участника или team-участника
    (PRD §6.1.6).
    """
    users_left = await session.execute(
        select(ProjectUserMember.user_id).where(ProjectUserMember.project_id == project.id).limit(1)
    )
    teams_left = await session.execute(
        select(ProjectTeamMember.team_id).where(ProjectTeamMember.project_id == project.id).limit(1)
    )
    if users_left.first() is None and teams_left.first() is None:
        await session.delete(project)
        await session.flush()
