"""Резолвер cron-trigger `query(rsql)` Jinja-функции (ARCH §11.5.2).

Cron-Jinja-контекст содержит callable `query(rsql) → list[dict]`. Для
event-trigger контекст задаётся самой задачей, у cron-trigger нет «инициатора»
запроса — actor выбирается детерминированно: первый участник проекта с
`manage_automations` (тот же выбор, что для system_method actor'а в
reactive_matcher; см. PRD §6.5.3 и ARCH §11.4.6).

`query()` — sync-callable, вызывается из Jinja-render (sync API jinja2).
Чтобы не тянуть asyncio внутрь шаблона, мы выполняем RSQL+SELECT синхронно
через тот же jinja-render asyncio-loop: `resolve_cron_query` возвращает
зависимый от данных callable, который перед вызовом render-а уже знает actor
и sessionmaker. Внутри callable — `asyncio.run` не годится (мы внутри активного
loop'а), потому исполнение делается через `loop.run_until_complete` неприменимо
тоже; используем приём «pre-materialize»: callable перехватывает rsql,
складывает в очередь, после render проверяем — но это сложно.

Проще: вызовы `query()` из Jinja делаются изнутри cron job-callback'а, который
уже внутри asyncio. Мы запускаем jinja-render в той же coroutine, поэтому
доступа к event loop у нас нет — render синхронен. Решение: выполняем все
ожидаемые запросы заранее? Шаблон сам решает, какие RSQL'и вызвать, заранее
неизвестно.

Финальное решение: callable использует `sync` engine SQLAlchemy через
отдельную sync-сессию (psycopg2). Это полностью изолировано от async-event
loop и работает прямо изнутри sync Jinja-render. См. ARCH §3.7
(sync-sessionmaker для миграций / outbox / cron).
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from sqlalchemy import create_engine, select
from sqlalchemy.engine import Engine
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from tasks_service.config import settings
from tasks_service.models import ProjectUserMember, Task, User
from tasks_service.rsql.fields import (
    FieldSpec,
    FieldType,
    RSQLContext,
    build_sqlalchemy_filter,
)
from tasks_service.rsql.parser import RSQLError

_log = logging.getLogger(__name__)


# Sync-движок для cron query(): ленивая инициализация, переиспользуется
# между вызовами. Используем тот же sync DSN, что и Alembic.
_sync_engine: Engine | None = None


def _get_sync_engine() -> Engine:
    global _sync_engine
    if _sync_engine is None:
        _sync_engine = create_engine(settings.alembic_url, future=True)
    return _sync_engine


def _task_field_specs() -> list[FieldSpec]:
    """Дублирует services/tasks._task_field_specs (см. ARCH §8).

    Поля RSQL для cron-query — те же, что у `clite get tasks --filter`.
    Дублирование оправдано тем, что сервисный модуль работает с asyncSession,
    а здесь нужен идентичный whitelist для sync-сессии.
    """
    return [
        FieldSpec("id", Task.id, FieldType.SHA1_KEY),
        FieldSpec("title", Task.title, FieldType.STRING),
        FieldSpec("status", Task.status, FieldType.STRING),
        FieldSpec("labels", Task.labels, FieldType.STRING_ARRAY),
        FieldSpec("assignee", Task.assignee_id, FieldType.USER_EMAIL),
        FieldSpec("created_at", Task.created_at, FieldType.DATETIME),
    ]


async def _resolve_actor(session: AsyncSession, *, project_id: str) -> User | None:
    """Тот же детерминированный выбор, что у reactive_matcher._resolve_owner."""
    result = await session.execute(
        select(ProjectUserMember)
        .where(ProjectUserMember.project_id == project_id)
        .order_by(ProjectUserMember.user_id)
    )
    for member in result.scalars().all():
        if "manage_automations" in member.perms:
            user_result = await session.execute(
                select(User).where(User.id == member.user_id)
            )
            return user_result.scalar_one_or_none()
    return None


def _build_filter_sync(
    sync_session: Session, *, filter_str: str, actor_email: str, actor_id: str
) -> object:
    """Sync-аналог services/tasks._build_rsql_filter (для cron-query)."""
    # Здесь нам нужно резолвить только `me` литерал — для cron'а это actor.
    cache: dict[str, str | None] = {actor_email: actor_id}

    def sync_resolve(email: str) -> str | None:
        if email in cache:
            return cache[email]
        # Любые email кроме actor резолвим через sync-запрос.
        result = sync_session.execute(select(User).where(User.email == email))
        u = result.scalar_one_or_none()
        cache[email] = u.id if u else None
        return cache[email]

    ctx = RSQLContext(
        current_user_email=actor_email, resolve_email_to_user_id=sync_resolve
    )
    return build_sqlalchemy_filter(filter_str, _task_field_specs(), ctx)


def _task_to_dict(t: Task, assignee_email: str) -> dict[str, Any]:
    return {
        "id": t.id,
        "title": t.title,
        "description_md": t.description_md,
        "labels": list(t.labels),
        "status": str(t.status),
        "assignee_email": assignee_email,
        "created_at": t.created_at.isoformat() if t.created_at else None,
        "updated_at": t.updated_at.isoformat() if t.updated_at else None,
    }


async def resolve_cron_query(
    session: AsyncSession, *, project_id: str
) -> Callable[[str], list[dict[str, Any]]]:
    """Построить sync-callable `query(rsql)` для cron Jinja-контекста.

    Actor резолвится один раз заранее (см. модуль-docstring). Возвращённая
    функция открывает sync-сессию sqlalchemy и выполняет SELECT по
    RSQL-фильтру; ошибки RSQL логируются и возвращают пустой список —
    шаблон при этом не падает (StrictUndefined ловит только undefined-переменные,
    а query вернёт `[]`).
    """
    actor = await _resolve_actor(session, project_id=project_id)
    if actor is None:
        _log.warning(
            "cron query: no project member with manage_automations for %s",
            project_id,
        )

        def _empty(_rsql: str) -> list[dict[str, Any]]:
            return []

        return _empty

    actor_id = actor.id
    actor_email = actor.email

    def query(rsql: str) -> list[dict[str, Any]]:
        engine = _get_sync_engine()
        with Session(engine, future=True) as sync_session:
            try:
                where = _build_filter_sync(
                    sync_session,
                    filter_str=rsql,
                    actor_email=actor_email,
                    actor_id=actor_id,
                )
            except RSQLError as e:
                _log.warning("cron query: bad RSQL %r: %s", rsql, e)
                return []
            stmt = (
                select(Task)
                .where(where)  # type: ignore[arg-type]
                .order_by(Task.created_at, Task.id)
                .limit(1000)
            )
            rows = list(sync_session.execute(stmt).scalars().all())
            # Гидрация assignee_email одним запросом.
            assignee_ids = {r.assignee_id for r in rows}
            email_map: dict[str, str] = {}
            if assignee_ids:
                pairs = sync_session.execute(
                    select(User.id, User.email).where(User.id.in_(assignee_ids))
                ).all()
                for uid, email in pairs:
                    email_map[uid] = email
            return [_task_to_dict(t, email_map.get(t.assignee_id, "")) for t in rows]

    return query
