"""Effective permissions для задачи (PRD §6.2).

В M2.7c реализован только Path A (прямой шаринг — user-share +
team-share-через-членство). Path B (через проекты) — M2.8.

В AUTH_MODE=disabled SOLO_USER получает все task-perms (M1
совместимость).
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from tasks_service.config import settings
from tasks_service.models import (
    TaskPermission,
    TaskTeamShare,
    TaskUserShare,
    TeamMember,
    User,
)

ALL_TASK_PERMS: list[str] = sorted(p.value for p in TaskPermission)


async def effective_task_perms(session: AsyncSession, *, user: User, task_id: UUID) -> set[str]:
    """Возвращает множество перм-флагов, действующих у user на task.

    В AUTH_MODE=disabled SOLO_USER → все task-perms.
    """
    if settings.auth_mode == "disabled":
        return set(ALL_TASK_PERMS)

    perms: set[str] = set()

    # Direct user-share.
    user_share = await session.execute(
        select(TaskUserShare.perms).where(
            TaskUserShare.task_id == task_id, TaskUserShare.user_id == user.id
        )
    )
    for row in user_share:
        perms.update(row.perms)

    # Через членство в командах (Path A team-share).
    user_team_ids_result = await session.execute(
        select(TeamMember.team_id).where(TeamMember.user_id == user.id)
    )
    user_team_ids = list(user_team_ids_result.scalars().all())
    if user_team_ids:
        team_share = await session.execute(
            select(TaskTeamShare.perms).where(
                TaskTeamShare.task_id == task_id,
                TaskTeamShare.team_id.in_(user_team_ids),
            )
        )
        for row in team_share:
            perms.update(row.perms)

    return perms


async def is_team_member(session: AsyncSession, *, user_id: UUID, team_id: UUID) -> bool:
    result = await session.execute(
        select(TeamMember.user_id).where(
            TeamMember.team_id == team_id, TeamMember.user_id == user_id
        )
    )
    return result.scalar_one_or_none() is not None
