"""Event dispatcher для reactive automations (ARCH §11.2).

В той же транзакции, что и мутация задачи, пишет запись в `event_log`.
Reactive matcher (services/reactive_matcher.py) затем подбирает её по trigger_type=event
автоматизациям с совпадающим event_type.

Каталог event_type фиксируется здесь (PRD §8.4.3, ARCH §11):
- task.created
- task.updated
- task.status_changed       (выделенное событие при изменении status)
- task.assigned             (выделенное событие при изменении assignee)
- task.labeled              (выделенное при изменении labels)
- task.deleted              (если когда-либо появится hard-delete)
"""

from __future__ import annotations

import time
from hashlib import sha1
from typing import Final

from sqlalchemy.ext.asyncio import AsyncSession

from tasks_service.models import EventLog

# Каноничный каталог event_type. CLI / docs-client могут использовать как
# источник для валидации trigger_config.event_type.
EVENT_TASK_CREATED: Final[str] = "task.created"
EVENT_TASK_UPDATED: Final[str] = "task.updated"
EVENT_TASK_STATUS_CHANGED: Final[str] = "task.status_changed"
EVENT_TASK_ASSIGNED: Final[str] = "task.assigned"
EVENT_TASK_LABELED: Final[str] = "task.labeled"
EVENT_TASK_DELETED: Final[str] = "task.deleted"

EVENT_CATALOG: Final[frozenset[str]] = frozenset(
    {
        EVENT_TASK_CREATED,
        EVENT_TASK_UPDATED,
        EVENT_TASK_STATUS_CHANGED,
        EVENT_TASK_ASSIGNED,
        EVENT_TASK_LABELED,
        EVENT_TASK_DELETED,
    }
)


def _event_id(source_task_id: str, event_type: str) -> str:
    raw = "\n".join([source_task_id, event_type, str(time.time_ns())])
    return sha1(raw.encode("utf-8"), usedforsecurity=False).hexdigest()


async def record_event(
    session: AsyncSession,
    *,
    source_task_id: str,
    event_type: str,
    payload: dict[str, object] | None = None,
) -> EventLog:
    """Записывает событие в event_log в той же транзакции (ARCH §11.2.1).

    Не валидирует event_type против каталога — позволяет добавлять кастомные
    типы из расширений (PRD §8.4.3). reactive_matcher отфильтрует по точному
    совпадению с trigger_config.event_type.
    """
    event = EventLog(
        id=_event_id(source_task_id, event_type),
        source_task_id=source_task_id,
        event_type=event_type,
        payload=payload or {},
    )
    session.add(event)
    await session.flush()
    return event
