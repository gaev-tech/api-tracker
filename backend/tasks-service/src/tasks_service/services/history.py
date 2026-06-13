from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from tasks_service.cursor import decode_cursor, encode_cursor
from tasks_service.models import AuditEvent, User
from tasks_service.services.perms import filter_visible_task_ids

HISTORY_LIMIT = 50  # фиксированный лимит, architecture.md §10.4


async def _hydrate_actors(
    session: AsyncSession, events: Sequence[AuditEvent]
) -> dict[UUID, str]:
    actor_ids = {e.actor_user_id for e in events}
    if not actor_ids:
        return {}
    result = await session.execute(
        select(User.id, User.email).where(User.id.in_(actor_ids))
    )
    return {row.id: row.email for row in result.all()}


def _event_to_dict(e: AuditEvent, actor_emails: dict[UUID, str]) -> dict[str, object]:
    return {
        "id": e.id,
        "actor_email": actor_emails.get(e.actor_user_id, ""),
        "target_type": e.target_type,
        "target_id": e.target_id,
        "event_type": e.event_type,
        "payload": e.payload,
        "created_at": e.created_at,
    }


async def list_history_for_task(
    session: AsyncSession,
    task_id: UUID,
    cursor: str | None = None,
) -> tuple[list[dict[str, object]], str | None]:
    stmt = (
        select(AuditEvent)
        .where(AuditEvent.target_type == "task", AuditEvent.target_id == task_id)
        .order_by(AuditEvent.created_at.desc(), AuditEvent.id.desc())
    )
    if cursor:
        ts, eid = decode_cursor(cursor)
        stmt = stmt.where(
            or_(
                AuditEvent.created_at < ts,
                and_(AuditEvent.created_at == ts, AuditEvent.id < eid),
            )
        )
    stmt = stmt.limit(HISTORY_LIMIT + 1)
    result = await session.execute(stmt)
    rows = list(result.scalars().all())

    has_next = len(rows) > HISTORY_LIMIT
    items = rows[:HISTORY_LIMIT]
    actor_emails = await _hydrate_actors(session, items)

    out = [_event_to_dict(e, actor_emails) for e in items]
    next_cursor = (
        encode_cursor(items[-1].created_at, items[-1].id)
        if has_next and items
        else None
    )
    return out, next_cursor


async def list_history_for_user(
    session: AsyncSession,
    *,
    requester: User,
    target_user_id: UUID,
    cursor: str | None = None,
) -> tuple[list[dict[str, object]], str | None]:
    """История действий пользователя с фильтрацией по видимости (ARCH §10.2.2).

    - Если requester == target — все события без фильтрации.
    - Иначе возвращаем только события, цель которых доступна requester
      по эффективным правам (effective_task_perms > 0 для target_type='task').
      События с target_type team/project/etc — пока не фильтруются (M2: только task).
    """
    own_history = requester.id == target_user_id

    # Сначала достаём pageful + запас (limit*3) — потом фильтруем видимость.
    base_limit = HISTORY_LIMIT * 3 if not own_history else HISTORY_LIMIT + 1
    stmt = (
        select(AuditEvent)
        .where(AuditEvent.actor_user_id == target_user_id)
        .order_by(AuditEvent.created_at.desc(), AuditEvent.id.desc())
    )
    if cursor:
        ts, eid = decode_cursor(cursor)
        stmt = stmt.where(
            or_(
                AuditEvent.created_at < ts,
                and_(AuditEvent.created_at == ts, AuditEvent.id < eid),
            )
        )
    stmt = stmt.limit(base_limit)
    result = await session.execute(stmt)
    candidates = list(result.scalars().all())

    if own_history:
        visible = candidates[: HISTORY_LIMIT + 1]
    else:
        # Фильтр видимости для task-target.
        task_targets = [e.target_id for e in candidates if e.target_type == "task"]
        visible_task_ids = await filter_visible_task_ids(
            session, user=requester, task_ids=task_targets
        )
        visible = []
        for e in candidates:
            if e.target_type == "task":
                if e.target_id in visible_task_ids:
                    visible.append(e)
            # Не-task события (team/project и т.п.) в M2 — пока скрываем
            # для чужой истории (until добавим explicit project/team visibility).
            if len(visible) > HISTORY_LIMIT:
                break

    has_next = len(visible) > HISTORY_LIMIT
    items = visible[:HISTORY_LIMIT]
    actor_emails = await _hydrate_actors(session, items)
    out = [_event_to_dict(e, actor_emails) for e in items]
    next_cursor = (
        encode_cursor(items[-1].created_at, items[-1].id)
        if has_next and items
        else None
    )
    return out, next_cursor
