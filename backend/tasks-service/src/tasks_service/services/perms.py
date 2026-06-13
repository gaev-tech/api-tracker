"""Effective permissions для задачи (PRD §6.2).

Реализованы оба пути по PRD §6.2.1:
- Path A: прямой шаринг — TaskUserShare + TaskTeamShare через
  членство в командах.
- Path B: членство в проектах — ProjectUserMember +
  ProjectTeamMember для проектов, в которых лежит задача
  (project-perms включают task-perms, см. PRD §6.5.5).

В AUTH_MODE=disabled SOLO_USER получает все task-perms (M1
совместимость).
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from tasks_service.config import settings
from tasks_service.models import (
    ProjectTask,
    ProjectTeamMember,
    ProjectUserMember,
    TaskPermission,
    TaskTeamShare,
    TaskUserShare,
    TeamMember,
    User,
)

ALL_TASK_PERMS: list[str] = sorted(p.value for p in TaskPermission)
_TASK_PERMS_SET: set[str] = set(ALL_TASK_PERMS)


async def _user_team_ids(session: AsyncSession, user_id: UUID) -> list[UUID]:
    result = await session.execute(select(TeamMember.team_id).where(TeamMember.user_id == user_id))
    return list(result.scalars().all())


async def effective_task_perms(session: AsyncSession, *, user: User, task_id: UUID) -> set[str]:
    """Возвращает множество перм-флагов, действующих у user на task = union(A, B).

    В AUTH_MODE=disabled SOLO_USER → все task-perms.
    """
    if settings.auth_mode == "disabled":
        return set(ALL_TASK_PERMS)

    perms: set[str] = set()
    user_team_ids = await _user_team_ids(session, user.id)

    # === Path A: прямой шаринг ===
    user_share = await session.execute(
        select(TaskUserShare.perms).where(
            TaskUserShare.task_id == task_id, TaskUserShare.user_id == user.id
        )
    )
    for row in user_share:
        perms.update(row.perms)

    if user_team_ids:
        team_share = await session.execute(
            select(TaskTeamShare.perms).where(
                TaskTeamShare.task_id == task_id,
                TaskTeamShare.team_id.in_(user_team_ids),
            )
        )
        for row in team_share:
            perms.update(row.perms)

    # === Path B: через проекты ===
    project_ids_result = await session.execute(
        select(ProjectTask.project_id).where(ProjectTask.task_id == task_id)
    )
    project_ids = list(project_ids_result.scalars().all())
    if project_ids:
        # User-membership.
        pum_rows = await session.execute(
            select(ProjectUserMember.perms).where(
                ProjectUserMember.project_id.in_(project_ids),
                ProjectUserMember.user_id == user.id,
            )
        )
        for row in pum_rows:
            # Из всех перм проекта берём только task-флаги.
            perms.update(p for p in row.perms if p in _TASK_PERMS_SET)

        # Team-membership внутри проекта.
        if user_team_ids:
            ptm_rows = await session.execute(
                select(ProjectTeamMember.perms).where(
                    ProjectTeamMember.project_id.in_(project_ids),
                    ProjectTeamMember.team_id.in_(user_team_ids),
                )
            )
            for row in ptm_rows:
                perms.update(p for p in row.perms if p in _TASK_PERMS_SET)

    return perms


async def filter_visible_task_ids(
    session: AsyncSession, *, user: User, task_ids: list[UUID]
) -> set[UUID]:
    """Возвращает подмножество task_ids, в которых у user есть ≥1 перм.

    Оптимизация: один SQL вместо N effective_task_perms.
    В AUTH_MODE=disabled возвращает все.
    """
    if not task_ids:
        return set()
    if settings.auth_mode == "disabled":
        return set(task_ids)

    visible: set[UUID] = set()
    user_team_ids = await _user_team_ids(session, user.id)

    # Path A user-share.
    us = await session.execute(
        select(TaskUserShare.task_id).where(
            TaskUserShare.task_id.in_(task_ids), TaskUserShare.user_id == user.id
        )
    )
    visible.update(us.scalars().all())

    # Path A team-share.
    if user_team_ids:
        ts = await session.execute(
            select(TaskTeamShare.task_id).where(
                TaskTeamShare.task_id.in_(task_ids),
                TaskTeamShare.team_id.in_(user_team_ids),
            )
        )
        visible.update(ts.scalars().all())

    # Path B через проекты.
    not_visible = set(task_ids) - visible
    if not_visible:
        # Какие проекты содержат эти задачи?
        proj_rows = await session.execute(
            select(ProjectTask.task_id, ProjectTask.project_id).where(
                ProjectTask.task_id.in_(not_visible)
            )
        )
        task_to_projects: dict[UUID, list[UUID]] = {}
        for row in proj_rows:
            task_to_projects.setdefault(row.task_id, []).append(row.project_id)

        all_project_ids = [pid for pids in task_to_projects.values() for pid in pids]
        if all_project_ids:
            visible_projects: set[UUID] = set()
            pum = await session.execute(
                select(ProjectUserMember.project_id).where(
                    ProjectUserMember.project_id.in_(all_project_ids),
                    ProjectUserMember.user_id == user.id,
                )
            )
            visible_projects.update(pum.scalars().all())
            if user_team_ids:
                ptm = await session.execute(
                    select(ProjectTeamMember.project_id).where(
                        ProjectTeamMember.project_id.in_(all_project_ids),
                        ProjectTeamMember.team_id.in_(user_team_ids),
                    )
                )
                visible_projects.update(ptm.scalars().all())

            for tid, pids in task_to_projects.items():
                if any(pid in visible_projects for pid in pids):
                    visible.add(tid)

    return visible


async def is_team_member(session: AsyncSession, *, user_id: UUID, team_id: UUID) -> bool:
    result = await session.execute(
        select(TeamMember.user_id).where(
            TeamMember.team_id == team_id, TeamMember.user_id == user_id
        )
    )
    return result.scalar_one_or_none() is not None
