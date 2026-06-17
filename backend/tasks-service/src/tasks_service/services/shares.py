"""Шаринг задачи пользователям и командам (PRD §6.2, §6.7)."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from tasks_service.models import (
    Task,
    TaskPermission,
    TaskTeamShare,
    TaskUserShare,
    Team,
    User,
)
from tasks_service.services.audit import record_audit
from tasks_service.services.perms import (
    ALL_TASK_PERMS,
    effective_task_perms,
    is_team_member,
)


class ShareError(Exception):
    pass


class TaskNotFound(ShareError):
    pass


class TeamNotFound(ShareError):
    pass


class PermissionDenied(ShareError):
    pass


class CannotGrantAboveSelf(ShareError):
    pass


_VALID_TASK_PERMS: set[str] = set(ALL_TASK_PERMS)


def _check_within_self(target_perms: list[str], own_perms: set[str]) -> None:
    extras = set(target_perms) - own_perms
    if extras:
        raise CannotGrantAboveSelf(f"cannot grant perms above own: {sorted(extras)}")


async def _get_task(session: AsyncSession, task_id: str) -> Task:
    result = await session.execute(select(Task).where(Task.id == task_id))
    task = result.scalar_one_or_none()
    if task is None:
        raise TaskNotFound(str(task_id))
    return task


async def set_user_share(
    session: AsyncSession,
    *,
    current: User,
    task_id: str,
    target_user_id: str,
    perms: list[str],
) -> None:
    """PUT — установить разрешения пользователя на задачу. Пустой массив = удаление."""
    task = await _get_task(session, task_id)
    own = await effective_task_perms(session, user=current, task_id=task.id)

    # Self-revoke (PRD §7.8.1) — без проверки SHARE-перм.
    if current.id == target_user_id and not perms:
        existing = await session.execute(
            select(TaskUserShare).where(
                TaskUserShare.task_id == task.id,
                TaskUserShare.user_id == target_user_id,
            )
        )
        record = existing.scalar_one_or_none()
        if record is not None:
            await session.delete(record)
            await session.flush()
            await record_audit(
                session,
                actor_user_id=current.id,
                target_type="task",
                target_id=task.id,
                event_type="task.share_self_revoked",
                payload={"user_id": str(target_user_id)},
            )
            await _maybe_cascade_delete_task(session, task)
        return

    # Иначе требуется SHARE-перм.
    if TaskPermission.SHARE.value not in own:
        raise PermissionDenied(f"missing task permission: {TaskPermission.SHARE.value}")
    _check_within_self(perms, own)

    invalid = [p for p in perms if p not in _VALID_TASK_PERMS]
    if invalid:
        raise ShareError(f"unknown task permissions: {invalid}")

    if not perms:
        # Удаление чужого участника.
        existing = await session.execute(
            select(TaskUserShare).where(
                TaskUserShare.task_id == task.id,
                TaskUserShare.user_id == target_user_id,
            )
        )
        record = existing.scalar_one_or_none()
        if record is None:
            return
        await session.delete(record)
        await session.flush()
        await record_audit(
            session,
            actor_user_id=current.id,
            target_type="task",
            target_id=task.id,
            event_type="task.user_unshared",
            payload={"user_id": str(target_user_id)},
        )
        await _maybe_cascade_delete_task(session, task)
        return

    # Tariff: pre-check `task_shares` адресата если это новый INSERT
    # (tariff.md §4.2.6, IPLAN §7.2.4.1).
    existing = await session.execute(
        select(TaskUserShare).where(
            TaskUserShare.task_id == task.id,
            TaskUserShare.user_id == target_user_id,
        )
    )
    if existing.scalar_one_or_none() is None:
        from tasks_service.services.tariff_enforcement import check_tariff_limit

        await check_tariff_limit(session, user_id=target_user_id, metric="task_shares")
    # Upsert.
    stmt = (
        pg_insert(TaskUserShare)
        .values(task_id=task.id, user_id=target_user_id, perms=perms)
        .on_conflict_do_update(
            index_elements=["task_id", "user_id"], set_={"perms": perms}
        )
    )
    await session.execute(stmt)
    await session.flush()
    await record_audit(
        session,
        actor_user_id=current.id,
        target_type="task",
        target_id=task.id,
        event_type="task.user_shared",
        payload={"user_id": str(target_user_id), "perms": perms},
    )


async def set_team_share(
    session: AsyncSession,
    *,
    current: User,
    task_id: str,
    target_team_id: str,
    perms: list[str],
) -> None:
    """Шарить команде можно только если шарящий сам член этой команды (PRD §6.7.1)."""
    task = await _get_task(session, task_id)
    own = await effective_task_perms(session, user=current, task_id=task.id)

    if TaskPermission.SHARE.value not in own:
        raise PermissionDenied(f"missing task permission: {TaskPermission.SHARE.value}")
    _check_within_self(perms, own)

    if perms:
        if not await is_team_member(
            session, user_id=current.id, team_id=target_team_id
        ):
            raise PermissionDenied("must be a member of the team to share with it")

    # Проверяем существование команды.
    team = (
        await session.execute(select(Team).where(Team.id == target_team_id))
    ).scalar_one_or_none()
    if team is None:
        raise TeamNotFound(str(target_team_id))

    invalid = [p for p in perms if p not in _VALID_TASK_PERMS]
    if invalid:
        raise ShareError(f"unknown task permissions: {invalid}")

    if not perms:
        existing = await session.execute(
            select(TaskTeamShare).where(
                TaskTeamShare.task_id == task.id,
                TaskTeamShare.team_id == target_team_id,
            )
        )
        record = existing.scalar_one_or_none()
        if record is None:
            return
        await session.delete(record)
        await session.flush()
        await record_audit(
            session,
            actor_user_id=current.id,
            target_type="task",
            target_id=task.id,
            event_type="task.team_unshared",
            payload={"team_id": str(target_team_id)},
        )
        await _maybe_cascade_delete_task(session, task)
        return

    stmt = (
        pg_insert(TaskTeamShare)
        .values(task_id=task.id, team_id=target_team_id, perms=perms)
        .on_conflict_do_update(
            index_elements=["task_id", "team_id"], set_={"perms": perms}
        )
    )
    await session.execute(stmt)
    await session.flush()
    await record_audit(
        session,
        actor_user_id=current.id,
        target_type="task",
        target_id=task.id,
        event_type="task.team_shared",
        payload={"team_id": str(target_team_id), "perms": perms},
    )


async def _maybe_cascade_delete_task(session: AsyncSession, task: Task) -> None:
    """Удаляем задачу, если не осталось ни одного user/team share и проектов
    (PRD §6.1.5-6.1.6)."""
    # В AUTH_MODE=disabled SOLO_USER неявно владеет — не удаляем.
    from tasks_service.config import settings
    from tasks_service.models import ProjectTask

    if settings.auth_mode == "disabled":
        return

    user_shares = await session.execute(
        select(TaskUserShare.user_id).where(TaskUserShare.task_id == task.id).limit(1)
    )
    team_shares = await session.execute(
        select(TaskTeamShare.team_id).where(TaskTeamShare.task_id == task.id).limit(1)
    )
    project_tasks = await session.execute(
        select(ProjectTask.project_id).where(ProjectTask.task_id == task.id).limit(1)
    )
    if (
        user_shares.first() is None
        and team_shares.first() is None
        and project_tasks.first() is None
    ):
        await session.delete(task)
        await session.flush()


async def list_user_shares(
    session: AsyncSession, *, task_id: str
) -> list[TaskUserShare]:
    result = await session.execute(
        select(TaskUserShare)
        .where(TaskUserShare.task_id == task_id)
        .order_by(TaskUserShare.user_id)
    )
    return list(result.scalars().all())


async def list_team_shares(
    session: AsyncSession, *, task_id: str
) -> list[TaskTeamShare]:
    result = await session.execute(
        select(TaskTeamShare)
        .where(TaskTeamShare.task_id == task_id)
        .order_by(TaskTeamShare.team_id)
    )
    return list(result.scalars().all())


async def add_creator_share(
    session: AsyncSession, *, task_id: str, creator_id: str
) -> None:
    """Имплицитный user-share при создании задачи — creator получает все task-perms.

    Обеспечивает anchor-rule (PRD §6.6) автоматически в случае, когда явных
    project/share-параметров в запросе не было.

    Tariff: pre-check `task_shares` создателя (tariff.md §4.2.5 — для каждого
    `user_shares[i]`, включая создателя по PRD §6.6.1.2). Если запись уже
    существует, проверка не нужна (on_conflict_do_nothing → no-op INSERT).
    """
    existing = await session.execute(
        select(TaskUserShare).where(
            TaskUserShare.task_id == task_id,
            TaskUserShare.user_id == creator_id,
        )
    )
    if existing.scalar_one_or_none() is None:
        from tasks_service.services.tariff_enforcement import check_tariff_limit

        await check_tariff_limit(session, user_id=creator_id, metric="task_shares")
    stmt = (
        pg_insert(TaskUserShare)
        .values(task_id=task_id, user_id=creator_id, perms=ALL_TASK_PERMS)
        .on_conflict_do_nothing()
    )
    await session.execute(stmt)
    await session.flush()
