"""Cron-scheduler через APScheduler с PostgreSQL jobstore (ARCH §11.3).

При старте tasks-svc загружает все automations с trigger_type=cron и регистрирует
job-ы. Job при срабатывании ставит action в очередь (или исполняет system_method).

NB: используем `AsyncIOScheduler` с in-memory jobstore по умолчанию для простоты;
синхронизация с DB происходит периодически через `_reload_jobs`. Полная замена
на PostgreSQL-jobstore APScheduler'a — отдельный шаг (ARCH §11.3.1), требует
синхронных запросов к БД, отложено до M3+.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable, Coroutine
from datetime import UTC, datetime
from typing import Any

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from tasks_service.models import Automation, AutomationTriggerType
from tasks_service.services.jinja_render import (
    RenderError,
    render_cron_context,
)
from tasks_service.services.reactive_matcher import execute_automation
from tasks_service.services.secrets import resolve_secrets_for_project
from tasks_service.services.webhook_outbox import enqueue_webhook

_log = logging.getLogger(__name__)

# Перезагружаем job-ы из БД с этим интервалом (чтобы CRUD автоматизаций отражался).
_RELOAD_INTERVAL_SECONDS = 60.0


def _parse_cron(expr: str) -> CronTrigger:
    parts = expr.strip().split()
    if len(parts) == 5:
        return CronTrigger(
            minute=parts[0],
            hour=parts[1],
            day=parts[2],
            month=parts[3],
            day_of_week=parts[4],
        )
    if len(parts) == 6:
        return CronTrigger(
            second=parts[0],
            minute=parts[1],
            hour=parts[2],
            day=parts[3],
            month=parts[4],
            day_of_week=parts[5],
        )
    raise ValueError(f"invalid cron expression: {expr!r}")


async def _fire_cron_automation(
    sessionmaker: async_sessionmaker[AsyncSession], automation_id: str
) -> None:
    """Job callback: подгружает свежую копию автоматизации и исполняет action."""
    async with sessionmaker() as session:
        result = await session.execute(
            select(Automation).where(Automation.id == automation_id)
        )
        automation = result.scalar_one_or_none()
        if automation is None:
            return
        secrets = await resolve_secrets_for_project(
            session, project_id=automation.project_id
        )
        cfg = automation.action_config
        if not isinstance(cfg, dict):
            await session.commit()
            return

        # Cron-контекст: { now, query(rsql), secrets } (ARCH §11.5.2).
        # Реальный query() сейчас не подсунем синхронно в Jinja — оставим
        # как noop, возвращающий пустой list; реализация — отдельный шаг.
        def _query(_rsql: str) -> list[dict[str, Any]]:
            return []

        now_iso = datetime.now(UTC).isoformat()
        if str(automation.action_type) == "webhook":
            url = str(cfg.get("url", ""))
            body_tmpl = str(cfg.get("body", ""))
            headers_raw = cfg.get("headers", {})
            if not url:
                await session.commit()
                return
            try:
                body = render_cron_context(
                    body_tmpl, now=now_iso, query=_query, secrets=secrets
                )
            except RenderError as e:
                _log.warning("cron render failed for %s: %s", automation.id, e)
                await session.commit()
                return
            headers: dict[str, str] = {}
            if isinstance(headers_raw, dict):
                for k, v in headers_raw.items():
                    try:
                        headers[str(k)] = render_cron_context(
                            str(v), now=now_iso, query=_query, secrets=secrets
                        )
                    except RenderError as e:
                        _log.warning("cron render header %s: %s", k, e)
                        await session.commit()
                        return
            await enqueue_webhook(
                session,
                automation_id=automation.id,
                url=url,
                headers=headers,
                body=body,
            )
            await session.commit()
            return
        # system_method — execute_automation покрывает оба варианта; task=None.
        await execute_automation(session, automation=automation, task=None, event=None)
        await session.commit()


class CronManager:
    """Управляет AsyncIOScheduler-ом и периодическим reload-ом jobs из БД."""

    def __init__(
        self,
        *,
        sessionmaker: async_sessionmaker[AsyncSession],
        scheduler_factory: Callable[[], AsyncIOScheduler] | None = None,
    ) -> None:
        self._sm = sessionmaker
        self._sched: AsyncIOScheduler | None = None
        self._registered: dict[str, str] = {}  # automation_id -> cron string
        self._scheduler_factory = scheduler_factory or AsyncIOScheduler

    async def start(self) -> None:
        self._sched = self._scheduler_factory()
        self._sched.start()
        await self._reload_jobs()

    async def shutdown(self) -> None:
        if self._sched is not None:
            self._sched.shutdown(wait=False)
            self._sched = None

    async def _reload_jobs(self) -> None:
        if self._sched is None:
            return
        async with self._sm() as session:
            result = await session.execute(
                select(Automation).where(
                    Automation.trigger_type == AutomationTriggerType.CRON
                )
            )
            automations = list(result.scalars().all())
        seen: set[str] = set()
        for a in automations:
            seen.add(a.id)
            cfg = a.trigger_config
            if not isinstance(cfg, dict):
                continue
            cron = cfg.get("cron")
            if not isinstance(cron, str):
                continue
            current = self._registered.get(a.id)
            if current == cron:
                continue
            # Перерегистрация.
            if current is not None:
                try:
                    self._sched.remove_job(a.id)
                except Exception as e:
                    _log.debug("cron remove_job %s: %s", a.id, e)
            try:
                trigger = _parse_cron(cron)
            except ValueError as e:
                _log.warning("cron parse failed for %s: %s", a.id, e)
                continue
            self._sched.add_job(
                _job_wrapper,
                trigger=trigger,
                args=[self._sm, a.id],
                id=a.id,
                replace_existing=True,
            )
            self._registered[a.id] = cron
        # Удалим job-ы, которых больше нет в БД.
        for aid in list(self._registered.keys()):
            if aid not in seen:
                try:
                    self._sched.remove_job(aid)
                except Exception as e:
                    _log.debug("cron remove_job %s: %s", aid, e)
                self._registered.pop(aid, None)

    async def run_reload_loop(self, *, stop_event: asyncio.Event) -> None:
        while not stop_event.is_set():
            try:
                await asyncio.wait_for(
                    stop_event.wait(), timeout=_RELOAD_INTERVAL_SECONDS
                )
            except TimeoutError:
                pass
            if stop_event.is_set():
                break
            try:
                await self._reload_jobs()
            except Exception as e:
                _log.exception("cron reload failed: %s", e)


def _job_wrapper(
    sm: async_sessionmaker[AsyncSession], automation_id: str
) -> Coroutine[Any, Any, None]:
    """APScheduler-callable обёртка над async-функцией."""
    return _fire_cron_automation(sm, automation_id)
