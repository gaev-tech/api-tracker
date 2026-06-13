from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from tasks_service.cursor import decode_cursor, encode_cursor
from tasks_service.models import AuditEvent, User

HISTORY_LIMIT = 50  # фиксированный лимит, architecture.md §10.4


async def _hydrate_actors(session: AsyncSession, events: Sequence[AuditEvent]) -> dict[UUID, str]:
    actor_ids = {e.actor_user_id for e in events}
    if not actor_ids:
        return {}
    result = await session.execute(select(User.id, User.email).where(User.id.in_(actor_ids)))
    return {row.id: row.email for row in result.all()}


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
            or_(AuditEvent.created_at < ts, and_(AuditEvent.created_at == ts, AuditEvent.id < eid))
        )
    stmt = stmt.limit(HISTORY_LIMIT + 1)
    result = await session.execute(stmt)
    rows = list(result.scalars().all())

    has_next = len(rows) > HISTORY_LIMIT
    items = rows[:HISTORY_LIMIT]
    actor_emails = await _hydrate_actors(session, items)

    out = [
        {
            "id": e.id,
            "actor_email": actor_emails.get(e.actor_user_id, ""),
            "target_type": e.target_type,
            "target_id": e.target_id,
            "event_type": e.event_type,
            "payload": e.payload,
            "created_at": e.created_at,
        }
        for e in items
    ]
    next_cursor = encode_cursor(items[-1].created_at, items[-1].id) if has_next and items else None
    return out, next_cursor
