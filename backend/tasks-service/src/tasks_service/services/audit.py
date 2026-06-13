from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from tasks_service.models import AuditEvent


async def record_audit(
    session: AsyncSession,
    actor_user_id: UUID,
    target_type: str,
    target_id: UUID,
    event_type: str,
    payload: dict[str, object] | None = None,
) -> None:
    """Записывает событие в audit_events в той же транзакции (architecture.md §10.1)."""
    event = AuditEvent(
        actor_user_id=actor_user_id,
        target_type=target_type,
        target_id=target_id,
        event_type=event_type,
        payload=payload or {},
    )
    session.add(event)
    await session.flush()
