import time
from hashlib import sha1

from sqlalchemy.ext.asyncio import AsyncSession

from tasks_service.models import AuditEvent


def _audit_id(actor: str, target_type: str, target_id: str, event_type: str) -> str:
    raw = "\n".join([actor, target_type, target_id, event_type, str(time.time_ns())])
    return sha1(raw.encode("utf-8"), usedforsecurity=False).hexdigest()


async def record_audit(
    session: AsyncSession,
    actor_user_id: str,
    target_type: str,
    target_id: str,
    event_type: str,
    payload: dict[str, object] | None = None,
) -> None:
    """Записывает событие в audit_events в той же транзакции (architecture.md §10.1)."""
    event = AuditEvent(
        id=_audit_id(actor_user_id, target_type, target_id, event_type),
        actor_user_id=actor_user_id,
        target_type=target_type,
        target_id=target_id,
        event_type=event_type,
        payload=payload or {},
    )
    session.add(event)
    await session.flush()
