"""Исполнитель system_method действий (ARCH §11.4).

Whitelist методов:
- tasks.list(filter: str) -> list[Task]
- tasks.create(payload: dict) -> dict      (single create — обёртка над bulk_create[0])
- tasks.bulk_update(filter: str, patch: dict) -> BulkResult
- tasks.batch_update(filter: str, patch: dict) -> BatchResult
- tasks.share(task_id, user_email|null, team_id|null, perms)

Каждый вызов исполняется от имени `actor: User` — обычно владельца автоматизации
(creator). См. PRD §6.5.3, ARCH §11.4.6 — расширения добавляются отдельным PR.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from tasks_service.models import User
from tasks_service.schemas import TaskCreate, TaskUpdate


class SystemMethodError(Exception):
    pass


class MethodNotAllowed(SystemMethodError):
    pass


async def execute_system_method(
    session: AsyncSession,
    *,
    actor: User,
    method: str,
    args: dict[str, Any],
) -> dict[str, Any]:
    """Исполнить system_method из whitelist.

    Args:
        session: открытая AsyncSession (commit делает caller).
        actor: User от чьего имени выполняется метод (для perm-чеков).
        method: имя из whitelist (tasks.list / tasks.create / ...).
        args: словарь параметров.

    Returns: словарь с результатом (для логирования / отображения в run-now).

    Raises:
        MethodNotAllowed: метод не в whitelist.
        SystemMethodError: ошибка валидации/исполнения.
    """
    if method == "tasks.list":
        return await _tasks_list(session, actor=actor, args=args)
    if method == "tasks.create":
        return await _tasks_create(session, actor=actor, args=args)
    if method == "tasks.bulk_update":
        return await _tasks_bulk_update(session, actor=actor, args=args)
    if method == "tasks.batch_update":
        return await _tasks_batch_update(session, actor=actor, args=args)
    if method == "tasks.share":
        return await _tasks_share(session, actor=actor, args=args)
    raise MethodNotAllowed(f"method not allowed: {method!r}")


async def _tasks_list(
    session: AsyncSession, *, actor: User, args: dict[str, Any]
) -> dict[str, Any]:
    from tasks_service.services.tasks import list_tasks

    filter_str = args.get("filter")
    if filter_str is not None and not isinstance(filter_str, str):
        raise SystemMethodError("tasks.list 'filter' must be a string")
    limit_raw = args.get("limit", 50)
    if not isinstance(limit_raw, int):
        raise SystemMethodError("tasks.list 'limit' must be an int")
    items, next_cursor = await list_tasks(
        session, current_user=actor, filter_str=filter_str, limit=limit_raw
    )
    return {
        "items": [t.model_dump(mode="json") for t in items],
        "next_cursor": next_cursor,
    }


async def _tasks_create(
    session: AsyncSession, *, actor: User, args: dict[str, Any]
) -> dict[str, Any]:
    from tasks_service.services.tasks import create_task

    payload_raw = args.get("payload")
    if not isinstance(payload_raw, dict):
        raise SystemMethodError("tasks.create requires 'payload' object")
    try:
        payload = TaskCreate.model_validate(payload_raw)
    except Exception as e:  # pydantic ValidationError
        raise SystemMethodError(f"invalid task payload: {e}") from e
    task = await create_task(session, current_user=actor, payload=payload)
    return {"task": task.model_dump(mode="json")}


async def _tasks_bulk_update(
    session: AsyncSession, *, actor: User, args: dict[str, Any]
) -> dict[str, Any]:
    from tasks_service.services.tasks import bulk_update

    filter_str = args.get("filter")
    patch_raw = args.get("patch")
    if not isinstance(filter_str, str):
        raise SystemMethodError("tasks.bulk_update 'filter' must be a string")
    if not isinstance(patch_raw, dict):
        raise SystemMethodError("tasks.bulk_update 'patch' must be an object")
    try:
        patch = TaskUpdate.model_validate(patch_raw)
    except Exception as e:
        raise SystemMethodError(f"invalid patch: {e}") from e
    results, total, succeeded = await bulk_update(
        session, current_user=actor, filter_str=filter_str, patch=patch
    )
    return {
        "results": [r.model_dump(mode="json") for r in results],
        "total": total,
        "succeeded": succeeded,
    }


async def _tasks_batch_update(
    session: AsyncSession, *, actor: User, args: dict[str, Any]
) -> dict[str, Any]:
    from tasks_service.services.tasks import batch_update

    filter_str = args.get("filter")
    patch_raw = args.get("patch")
    if not isinstance(filter_str, str):
        raise SystemMethodError("tasks.batch_update 'filter' must be a string")
    if not isinstance(patch_raw, dict):
        raise SystemMethodError("tasks.batch_update 'patch' must be an object")
    try:
        patch = TaskUpdate.model_validate(patch_raw)
    except Exception as e:
        raise SystemMethodError(f"invalid patch: {e}") from e
    affected = await batch_update(
        session, current_user=actor, filter_str=filter_str, patch=patch
    )
    return {"affected": affected}


async def _tasks_share(
    session: AsyncSession, *, actor: User, args: dict[str, Any]
) -> dict[str, Any]:
    from tasks_service.models import Task
    from tasks_service.services.prefix_lookup import resolve_prefix
    from tasks_service.services.shares import set_team_share, set_user_share

    task_id_raw = args.get("task_id")
    user_email = args.get("user_email")
    team_id_raw = args.get("team_id")
    perms = args.get("perms", [])
    if not isinstance(task_id_raw, str):
        raise SystemMethodError("tasks.share 'task_id' must be a string")
    if not isinstance(perms, list):
        raise SystemMethodError("tasks.share 'perms' must be a list")
    if (user_email is None) == (team_id_raw is None):
        raise SystemMethodError(
            "tasks.share requires exactly one of 'user_email' or 'team_id'"
        )
    task_id = await resolve_prefix(
        session, id_column=Task.id, discriminator_column=Task.title, key=task_id_raw
    )
    if user_email is not None:
        if not isinstance(user_email, str):
            raise SystemMethodError("tasks.share 'user_email' must be a string")
        from tasks_service.user_resolver import resolve_email_to_user_id_via_grpc

        target_uid = await resolve_email_to_user_id_via_grpc(user_email)
        if target_uid is None:
            raise SystemMethodError(f"user not found: {user_email}")
        await set_user_share(
            session,
            current=actor,
            task_id=task_id,
            target_user_id=target_uid,
            perms=[str(p) for p in perms],
        )
        return {"task_id": task_id, "user_email": user_email, "perms": perms}
    assert team_id_raw is not None
    if not isinstance(team_id_raw, str):
        raise SystemMethodError("tasks.share 'team_id' must be a string")
    from tasks_service.models import Team

    team_id = await resolve_prefix(
        session, id_column=Team.id, discriminator_column=Team.name, key=team_id_raw
    )
    await set_team_share(
        session,
        current=actor,
        task_id=task_id,
        target_team_id=team_id,
        perms=[str(p) for p in perms],
    )
    return {"task_id": task_id, "team_id": team_id, "perms": perms}
