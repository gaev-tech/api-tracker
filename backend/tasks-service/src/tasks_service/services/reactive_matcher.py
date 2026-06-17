"""Reactive matcher — фоновая asyncio-таска (ARCH §11.2).

Цикл:
1. `SELECT * FROM event_log WHERE processed_at IS NULL
    FOR UPDATE SKIP LOCKED LIMIT N`.
2. Для каждой записи: подтянуть automations с trigger_type=event,
   project_id IN (проекты задачи), event_type == event.event_type.
3. Проверить RSQL trigger_config.filter против Task.
4. Совпавшие автоматизации:
   - action_type=webhook → отрендерить body и положить в webhook_outbox.
   - action_type=system_method → исполнить прямо здесь.
5. Event.processed_at = now().
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from tasks_service.models import (
    Automation,
    AutomationActionType,
    AutomationTriggerType,
    EventLog,
    ProjectTask,
    ProjectUserMember,
    Task,
    User,
)
from tasks_service.rsql.fields import RSQLContext, build_sqlalchemy_filter
from tasks_service.services.jinja_render import RenderError, render_event_context
from tasks_service.services.secrets import resolve_secrets_for_project
from tasks_service.services.system_methods import (
    MethodNotAllowed,
    SystemMethodError,
    execute_system_method,
)
from tasks_service.services.webhook_outbox import enqueue_webhook

_log = logging.getLogger(__name__)

_BATCH_SIZE = 32
_IDLE_INTERVAL_SECONDS = 2.0


async def _task_to_dict(session: AsyncSession, task: Task) -> dict[str, Any]:
    """Минимальная сериализация Task для Jinja-контекста."""
    return {
        "id": task.id,
        "title": task.title,
        "description_md": task.description_md,
        "labels": list(task.labels),
        "status": str(task.status),
        "assignee_id": task.assignee_id,
        "created_at": task.created_at.isoformat() if task.created_at else None,
        "updated_at": task.updated_at.isoformat() if task.updated_at else None,
    }


async def _rsql_matches_task(
    session: AsyncSession, *, filter_str: str, task: Task
) -> bool:
    """Проверить RSQL-фильтр против конкретной задачи."""
    if not filter_str.strip():
        return True
    from tasks_service.services.tasks import _task_field_specs

    ctx = RSQLContext(
        current_user_email="",
        resolve_email_to_user_id=lambda _e: None,
    )
    try:
        where = build_sqlalchemy_filter(filter_str, _task_field_specs(), ctx)
    except Exception as e:  # RSQLError, ValueError, ...
        _log.warning("reactive_matcher: bad RSQL %r: %s", filter_str, e)
        return False
    stmt = select(Task.id).where(Task.id == task.id).where(where)
    result = await session.execute(stmt)
    return result.scalar_one_or_none() is not None


async def _resolve_owner(session: AsyncSession, *, project_id: str) -> User | None:
    """Выбрать первого участника проекта с MANAGE_AUTOMATIONS как actor для
    system_method (PRD §6.5.3). Простая стратегия для MVP — детерминированно
    берём минимального по user_id."""
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


async def _project_ids_for_task(session: AsyncSession, *, task_id: str) -> list[str]:
    result = await session.execute(
        select(ProjectTask.project_id).where(ProjectTask.task_id == task_id)
    )
    return list(result.scalars().all())


async def _find_matching_automations(
    session: AsyncSession,
    *,
    event_type: str,
    project_ids: list[str],
    task: Task,
) -> list[Automation]:
    if not project_ids:
        return []
    result = await session.execute(
        select(Automation).where(
            and_(
                Automation.trigger_type == AutomationTriggerType.EVENT,
                Automation.project_id.in_(project_ids),
            )
        )
    )
    out: list[Automation] = []
    for a in result.scalars().all():
        cfg = a.trigger_config
        if not isinstance(cfg, dict):
            continue
        cfg_event_type = cfg.get("event_type")
        if cfg_event_type != event_type:
            continue
        flt = cfg.get("filter") or ""
        if not isinstance(flt, str):
            continue
        if await _rsql_matches_task(session, filter_str=flt, task=task):
            out.append(a)
    return out


async def execute_automation(
    session: AsyncSession,
    *,
    automation: Automation,
    task: Task | None,
    event: dict[str, Any] | None,
) -> dict[str, Any]:
    """Исполнить action автоматизации.

    Используется и reactive_matcher'ом (event-trigger), и CLI run-now (без event).
    Возвращает результат (для логирования / отображения в run-now).
    """
    secrets = await resolve_secrets_for_project(
        session, project_id=automation.project_id
    )
    cfg = automation.action_config
    if not isinstance(cfg, dict):
        return {"status": "skipped", "reason": "invalid action_config"}
    if automation.action_type == AutomationActionType.WEBHOOK:
        url = str(cfg.get("url", ""))
        headers_raw = cfg.get("headers", {})
        body_tmpl = str(cfg.get("body", ""))
        if not url:
            return {"status": "skipped", "reason": "empty url"}
        task_ctx = await _task_to_dict(session, task) if task is not None else {}
        try:
            body = render_event_context(
                body_tmpl,
                task=task_ctx,
                event=event or {},
                secrets=secrets,
            )
        except RenderError as e:
            return {"status": "render_failed", "error": str(e)}
        # headers тоже могут содержать Jinja-переменные.
        headers: dict[str, str] = {}
        if isinstance(headers_raw, dict):
            for k, v in headers_raw.items():
                try:
                    headers[str(k)] = render_event_context(
                        str(v),
                        task=task_ctx,
                        event=event or {},
                        secrets=secrets,
                    )
                except RenderError as e:
                    return {"status": "render_failed", "error": str(e)}
        await enqueue_webhook(
            session,
            automation_id=automation.id,
            url=url,
            headers=headers,
            body=body,
        )
        return {"status": "enqueued", "url": url}
    if automation.action_type == AutomationActionType.SYSTEM_METHOD:
        method = str(cfg.get("method", ""))
        args_tmpl = cfg.get("args", {})
        # args тоже могут содержать Jinja-шаблоны в значениях. Простая стратегия:
        # рендерим строковые значения сверху, остальное передаём как есть.
        task_ctx = await _task_to_dict(session, task) if task is not None else {}
        rendered_args: dict[str, Any] = {}
        if isinstance(args_tmpl, dict):
            for k, v in args_tmpl.items():
                if isinstance(v, str):
                    try:
                        rendered_args[str(k)] = render_event_context(
                            v, task=task_ctx, event=event or {}, secrets=secrets
                        )
                    except RenderError as e:
                        return {"status": "render_failed", "error": str(e)}
                else:
                    rendered_args[str(k)] = v
        actor = await _resolve_owner(session, project_id=automation.project_id)
        if actor is None:
            return {
                "status": "skipped",
                "reason": "no project member with manage_automations",
            }
        try:
            result = await execute_system_method(
                session, actor=actor, method=method, args=rendered_args
            )
        except MethodNotAllowed as e:
            return {"status": "method_not_allowed", "error": str(e)}
        except SystemMethodError as e:
            return {"status": "method_error", "error": str(e)}
        return {"status": "ok", "result": result}
    return {"status": "skipped", "reason": "unknown action_type"}


async def _process_event(session: AsyncSession, event: EventLog) -> None:
    task_result = await session.execute(
        select(Task).where(Task.id == event.source_task_id)
    )
    task = task_result.scalar_one_or_none()
    if task is None:
        event.processed_at = datetime.now(UTC)
        return
    project_ids = await _project_ids_for_task(session, task_id=task.id)
    automations = await _find_matching_automations(
        session,
        event_type=event.event_type,
        project_ids=project_ids,
        task=task,
    )
    payload_dict = event.payload if isinstance(event.payload, dict) else {}
    event_dict: dict[str, Any] = {
        "id": event.id,
        "event_type": event.event_type,
        "payload": payload_dict,
        "created_at": event.created_at.isoformat() if event.created_at else None,
    }
    for automation in automations:
        try:
            await execute_automation(
                session, automation=automation, task=task, event=event_dict
            )
        except Exception as e:
            _log.exception(
                "reactive_matcher: automation %s failed: %s", automation.id, e
            )
    event.processed_at = datetime.now(UTC)


async def _drain_once(sessionmaker: async_sessionmaker[AsyncSession]) -> int:
    async with sessionmaker() as session:
        stmt = (
            select(EventLog)
            .where(or_(EventLog.processed_at.is_(None)))
            .order_by(EventLog.created_at)
            .limit(_BATCH_SIZE)
            .with_for_update(skip_locked=True)
        )
        result = await session.execute(stmt)
        events = list(result.scalars().all())
        if not events:
            await session.commit()
            return 0
        for event in events:
            try:
                await _process_event(session, event)
            except Exception as e:
                _log.exception(
                    "reactive_matcher: failed to process event %s: %s", event.id, e
                )
                event.processed_at = datetime.now(UTC)
        await session.commit()
        return len(events)


async def run_reactive_matcher(
    sessionmaker: async_sessionmaker[AsyncSession],
    *,
    stop_event: asyncio.Event,
) -> None:
    """Главный цикл reactive matcher. Останавливается по stop_event."""
    while not stop_event.is_set():
        try:
            processed = await _drain_once(sessionmaker)
        except Exception as e:
            _log.exception("reactive_matcher tick failed: %s", e)
            processed = 0
        if processed == 0:
            try:
                await asyncio.wait_for(
                    stop_event.wait(), timeout=_IDLE_INTERVAL_SECONDS
                )
            except TimeoutError:
                pass
