"""Сервис tasks — CRUD + bulk + batch (architecture.md §9)."""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import and_, delete, or_, select, tuple_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from tasks_service.cursor import CursorError, decode_cursor, encode_cursor
from tasks_service.deps import resolve_email_to_user_id
from tasks_service.ids import new_task_id
from tasks_service.models import Task, TaskBlocker, User
from tasks_service.rsql.fields import (
    FieldSpec,
    FieldType,
    RSQLContext,
    build_sqlalchemy_filter,
)
from tasks_service.rsql.parser import RSQLError
from tasks_service.schemas import (
    BulkCreateResultItem,
    BulkResultItem,
    TaskCreate,
    TaskRead,
    TaskUpdate,
)
from tasks_service.services.audit import record_audit

DEFAULT_LIMIT = 50
MAX_LIMIT = 200
MAX_MATCHES = 10_000  # architecture.md §9.3


class TooManyMatches(Exception):
    """Фильтр выбрал более MAX_MATCHES задач."""


class TaskNotFound(Exception):
    pass


class ValidationFailed(Exception):
    pass


def _task_field_specs() -> list[FieldSpec]:
    return [
        FieldSpec("id", Task.id, FieldType.SHA1_KEY),
        FieldSpec("title", Task.title, FieldType.STRING),
        FieldSpec("status", Task.status, FieldType.STRING),
        FieldSpec("labels", Task.labels, FieldType.STRING_ARRAY),
        FieldSpec("assignee", Task.assignee_id, FieldType.USER_EMAIL),
        FieldSpec("created_at", Task.created_at, FieldType.DATETIME),
    ]


async def _to_read(
    session: AsyncSession, task: Task, assignee_email_cache: dict[str, str]
) -> TaskRead:
    if task.assignee_id not in assignee_email_cache:
        result = await session.execute(
            select(User.email).where(User.id == task.assignee_id)
        )
        assignee_email_cache[task.assignee_id] = result.scalar_one_or_none() or ""

    return TaskRead(
        id=task.id,
        title=task.title,
        description_md=task.description_md,
        labels=list(task.labels),
        status=task.status,
        assignee_email=assignee_email_cache[task.assignee_id],
        blocked_by=[b.blocked_by_task_id for b in task.blockers],
        created_at=task.created_at,
        updated_at=task.updated_at,
    )


async def _resolve_email_sync(session: AsyncSession, email: str) -> str | None:
    return await resolve_email_to_user_id(session, email)


async def _build_rsql_filter(
    session: AsyncSession, filter_str: str, current_email: str
) -> object:
    cache: dict[str, str | None] = {}

    def resolve(email: str) -> str | None:
        if email in cache:
            return cache[email]
        # Sync wrapper — RSQL builder синхронный. Используем pre-cache (см. вызов).
        raise RSQLError(f"unresolved email {email}")

    # Заранее извлекаем все email из RSQL и резолвим их.
    # Простой подход: после первого парс-прохода пробежимся ещё раз.
    # Альтернатива: pre-resolve current email + me-литерал.
    resolved: dict[str, str | None] = {
        current_email: await _resolve_email_sync(session, current_email)
    }

    def sync_resolve(email: str) -> str | None:
        if email not in resolved:
            raise RSQLError(
                f"email {email!r} cannot be resolved synchronously in RSQL; "
                "currently only `me` literal is supported in M1"
            )
        return resolved[email]

    ctx = RSQLContext(
        current_user_email=current_email, resolve_email_to_user_id=sync_resolve
    )
    return build_sqlalchemy_filter(filter_str, _task_field_specs(), ctx)


async def list_tasks(
    session: AsyncSession,
    *,
    current_user: User,
    filter_str: str | None = None,
    cursor: str | None = None,
    limit: int = DEFAULT_LIMIT,
) -> tuple[list[TaskRead], str | None]:
    """Возвращает страницу задач, видимых пользователю (effective_task_perms > 0)."""
    from tasks_service.services.perms import filter_visible_task_ids

    if limit < 1 or limit > MAX_LIMIT:
        raise ValueError(f"limit must be in 1..{MAX_LIMIT}")
    stmt = (
        select(Task)
        .options(selectinload(Task.blockers))
        .order_by(Task.created_at, Task.id)
    )
    if filter_str:
        try:
            where = await _build_rsql_filter(session, filter_str, current_user.email)
            stmt = stmt.where(where)  # type: ignore[arg-type]
        except RSQLError:
            raise
    if cursor:
        try:
            ts, item_id = decode_cursor(cursor)
        except CursorError:
            raise
        stmt = stmt.where(
            or_(Task.created_at > ts, and_(Task.created_at == ts, Task.id > item_id))
        )
    # Берём с запасом, чтобы после фильтрации видимости остался полный limit.
    stmt = stmt.limit((limit + 1) * 3 if limit < 100 else limit + 50)
    result = await session.execute(stmt)
    rows = list(result.scalars().all())

    # Фильтр видимости (effective_task_perms > 0).
    visible_ids = await filter_visible_task_ids(
        session, user=current_user, task_ids=[t.id for t in rows]
    )
    visible_rows = [t for t in rows if t.id in visible_ids][: limit + 1]

    has_next = len(visible_rows) > limit
    items = visible_rows[:limit]
    cache: dict[str, str] = {}
    out = [await _to_read(session, t, cache) for t in items]
    next_cursor = (
        encode_cursor(items[-1].created_at, items[-1].id)
        if has_next and items
        else None
    )
    return out, next_cursor


async def get_task(
    session: AsyncSession,
    task_id: str,
    *,
    current_user: User | None = None,
) -> TaskRead:
    stmt = select(Task).options(selectinload(Task.blockers)).where(Task.id == task_id)
    result = await session.execute(stmt)
    task = result.scalar_one_or_none()
    if task is None:
        raise TaskNotFound(str(task_id))
    if current_user is not None:
        from tasks_service.services.perms import effective_task_perms

        perms = await effective_task_perms(session, user=current_user, task_id=task.id)
        if not perms:
            raise TaskNotFound(str(task_id))
    cache: dict[str, str] = {}
    return await _to_read(session, task, cache)


async def _verify_blockers_exist(
    session: AsyncSession, blocker_ids: Sequence[str]
) -> None:
    if not blocker_ids:
        return
    result = await session.execute(select(Task.id).where(Task.id.in_(blocker_ids)))
    found = set(result.scalars().all())
    missing = set(blocker_ids) - found
    if missing:
        raise TaskNotFound(f"blocker task(s) not found: {sorted(missing)}")


async def create_task(
    session: AsyncSession,
    *,
    current_user: User,
    payload: TaskCreate,
) -> TaskRead:
    await _verify_blockers_exist(session, payload.blocked_by)

    task = Task(
        id=new_task_id(payload.title, payload.description_md),
        title=payload.title,
        description_md=payload.description_md,
        labels=payload.labels,
        status=payload.status,
        assignee_id=current_user.id,
    )
    session.add(task)
    await session.flush()
    for bid in payload.blocked_by:
        session.add(TaskBlocker(task_id=task.id, blocked_by_task_id=bid))
    await session.flush()
    await record_audit(
        session,
        actor_user_id=current_user.id,
        target_type="task",
        target_id=task.id,
        event_type="task.created",
        payload={
            "title": payload.title,
            "labels": payload.labels,
            "status": str(payload.status),
        },
    )
    # Implicit user-share создателю (anchor-rule, PRD §6.6).
    from tasks_service.services.shares import add_creator_share

    await add_creator_share(session, task_id=task.id, creator_id=current_user.id)
    await session.refresh(task, ["blockers"])
    cache: dict[str, str] = {}
    return await _to_read(session, task, cache)


async def _apply_patch(
    session: AsyncSession,
    task: Task,
    patch: TaskUpdate,
    current_user: User,
) -> TaskRead:
    diff: dict[str, object] = {}
    if patch.title is not None and patch.title != task.title:
        diff["title"] = {"old": task.title, "new": patch.title}
        task.title = patch.title
    if patch.description_md is not None and patch.description_md != task.description_md:
        diff["description_md"] = "changed"
        task.description_md = patch.description_md
    if patch.labels is not None:
        if set(patch.labels) != set(task.labels):
            diff["labels"] = {"old": list(task.labels), "new": patch.labels}
            task.labels = patch.labels
    elif patch.add_labels or patch.remove_labels:
        labels = set(task.labels)
        if patch.add_labels:
            labels.update(patch.add_labels)
        if patch.remove_labels:
            labels.difference_update(patch.remove_labels)
        new_list = sorted(labels)
        if new_list != sorted(task.labels):
            diff["labels"] = {"old": list(task.labels), "new": new_list}
            task.labels = new_list
    if patch.status is not None and patch.status != task.status:
        diff["status"] = {"old": str(task.status), "new": str(patch.status)}
        task.status = patch.status

    if patch.add_blockers:
        await _verify_blockers_exist(session, patch.add_blockers)
        existing = {b.blocked_by_task_id for b in task.blockers}
        added: list[str] = []
        for bid in patch.add_blockers:
            if bid not in existing and bid != task.id:
                session.add(TaskBlocker(task_id=task.id, blocked_by_task_id=bid))
                added.append(str(bid))
        if added:
            diff["add_blockers"] = added
    if patch.remove_blockers:
        await session.execute(
            delete(TaskBlocker).where(
                tuple_(TaskBlocker.task_id, TaskBlocker.blocked_by_task_id).in_(
                    [(task.id, b) for b in patch.remove_blockers]
                )
            )
        )
        diff["remove_blockers"] = [str(b) for b in patch.remove_blockers]

    if diff:
        await session.flush()
        await record_audit(
            session,
            actor_user_id=current_user.id,
            target_type="task",
            target_id=task.id,
            event_type="task.updated",
            payload={"diff": diff},
        )
    await session.refresh(task, ["blockers"])
    cache: dict[str, str] = {}
    return await _to_read(session, task, cache)


async def update_task(
    session: AsyncSession,
    *,
    current_user: User,
    task_id: str,
    patch: TaskUpdate,
) -> TaskRead:
    stmt = select(Task).options(selectinload(Task.blockers)).where(Task.id == task_id)
    result = await session.execute(stmt)
    task = result.scalar_one_or_none()
    if task is None:
        raise TaskNotFound(str(task_id))
    return await _apply_patch(session, task, patch, current_user)


async def _select_filtered_ids(
    session: AsyncSession, filter_str: str, current_email: str
) -> list[str]:
    where = await _build_rsql_filter(session, filter_str, current_email)
    stmt = (
        select(Task.id)
        .where(where)  # type: ignore[arg-type]
        .order_by(Task.created_at, Task.id)
        .limit(MAX_MATCHES + 1)
    )
    result = await session.execute(stmt)
    ids = list(result.scalars().all())
    if len(ids) > MAX_MATCHES:
        raise TooManyMatches(f"too many matches: > {MAX_MATCHES}")
    return ids


async def bulk_update(
    session: AsyncSession,
    *,
    current_user: User,
    filter_str: str,
    patch: TaskUpdate,
) -> tuple[list[BulkResultItem], int, int]:
    ids = await _select_filtered_ids(session, filter_str, current_user.email)
    results: list[BulkResultItem] = []
    succeeded = 0
    for tid in ids:
        # Каждая задача — своя savepoint, чтобы ошибка одной не откатывала остальные.
        sp = await session.begin_nested()
        try:
            stmt = (
                select(Task).options(selectinload(Task.blockers)).where(Task.id == tid)
            )
            row = await session.execute(stmt)
            t = row.scalar_one_or_none()
            if t is None:
                await sp.rollback()
                results.append(BulkResultItem(task_id=tid, status="not_found"))
                continue
            await _apply_patch(session, t, patch, current_user)
            await sp.commit()
            results.append(BulkResultItem(task_id=tid, status="ok"))
            succeeded += 1
        except (TaskNotFound, ValidationFailed, ValueError, IntegrityError) as e:
            await sp.rollback()
            results.append(
                BulkResultItem(task_id=tid, status="validation_failed", error=str(e))
            )
    return results, len(ids), succeeded


async def batch_update(
    session: AsyncSession,
    *,
    current_user: User,
    filter_str: str,
    patch: TaskUpdate,
) -> int:
    ids = await _select_filtered_ids(session, filter_str, current_user.email)
    for tid in ids:
        stmt = select(Task).options(selectinload(Task.blockers)).where(Task.id == tid)
        row = await session.execute(stmt)
        t = row.scalar_one_or_none()
        if t is None:
            raise TaskNotFound(str(tid))
        await _apply_patch(session, t, patch, current_user)
    return len(ids)


async def bulk_create(
    session: AsyncSession,
    *,
    current_user: User,
    items: Sequence[TaskCreate],
) -> list[BulkCreateResultItem]:
    results: list[BulkCreateResultItem] = []
    for idx, payload in enumerate(items):
        sp = await session.begin_nested()
        try:
            t = await create_task(session, current_user=current_user, payload=payload)
            await sp.commit()
            results.append(BulkCreateResultItem(index=idx, status="ok", task_id=t.id))
        except (TaskNotFound, ValueError, IntegrityError) as e:
            await sp.rollback()
            results.append(
                BulkCreateResultItem(
                    index=idx, status="validation_failed", error=str(e)
                )
            )
    return results


async def batch_create(
    session: AsyncSession,
    *,
    current_user: User,
    items: Sequence[TaskCreate],
) -> list[str]:
    ids: list[str] = []
    for payload in items:
        t = await create_task(session, current_user=current_user, payload=payload)
        ids.append(t.id)
    return ids
