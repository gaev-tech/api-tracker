"""Cron-scheduler через APScheduler с PostgreSQL jobstore (ARCH §11.3).

При старте tasks-svc загружает все automations с trigger_type=cron и регистрирует
job-ы. Job при срабатывании ставит action в очередь (или исполняет system_method).

Реализация (M3.13):
- AsyncIOScheduler с `SQLAlchemyJobStore` поверх sync-DSN, вычисленного из
  существующего async `database_url` (см. `settings.alembic_url`).
- Job-callback — sync функция, которая шлёт coroutine в основной asyncio-loop
  через `asyncio.run_coroutine_threadsafe` (APScheduler гоняет job-ы в своём
  executor'е; для AsyncIOScheduler в текущей версии это main loop, но мы явно
  захватываем loop при start() — это рабочий паттерн для смешанного исполнения).
- Job-ы хранятся в PostgreSQL — выживают рестарт tasks-svc, синхронизируются
  между репликами без периодического reload. CRUD автоматизаций инкрементально
  отражается через add/modify/remove job; для непредвиденных рассогласований
  (например, ручное создание автоматизации напрямую в БД) оставляем
  идемпотентный `_reload_jobs`, который теперь дёргается только при старте
  и через CRUD-обёртки.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from tasks_service.config import settings
from tasks_service.models import Automation, AutomationTriggerType
from tasks_service.services.jinja_render import (
    RenderError,
    render_cron_context,
)
from tasks_service.services.reactive_matcher import execute_automation
from tasks_service.services.secrets import resolve_secrets_for_project
from tasks_service.services.webhook_outbox import enqueue_webhook

_log = logging.getLogger(__name__)


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
        # как noop, возвращающий пустой list; реализация — M3.14.
        def query(_rsql: str) -> list[dict[str, Any]]:
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
                    body_tmpl, now=now_iso, query=query, secrets=secrets
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
                            str(v), now=now_iso, query=query, secrets=secrets
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


def _job_async(automation_id: str) -> None:
    """Entrypoint, под которым APScheduler регистрирует job.

    Не имеет состояния — резолвит активный `CronManager` через модуль-глобал и
    шлёт coroutine в его loop. Это позволяет SQLAlchemyJobStore сериализовать
    job по qualname без захвата замыканий.
    """
    mgr = _ACTIVE_MANAGER
    if mgr is None or mgr._loop is None:
        _log.warning("cron job fired but CronManager not running")
        return
    coro = _fire_cron_automation(mgr._sm, automation_id)
    asyncio.run_coroutine_threadsafe(coro, mgr._loop)


# Активный CronManager (модуль-глобал, чтобы APScheduler мог сериализовать
# `_job_async` по qualname, не захватывая объект в замыкание).
_ACTIVE_MANAGER: CronManager | None = None


class CronManager:
    """AsyncIOScheduler с PostgreSQL jobstore (ARCH §11.3.1).

    PostgreSQL jobstore требует sync DSN — берём `settings.alembic_url`
    (тот же sync-движок, что использует Alembic; psycopg2-driver).
    """

    def __init__(
        self,
        *,
        sessionmaker: async_sessionmaker[AsyncSession],
        scheduler_factory: Callable[[], AsyncIOScheduler] | None = None,
    ) -> None:
        self._sm = sessionmaker
        self._sched: AsyncIOScheduler | None = None
        self._scheduler_factory = scheduler_factory
        self._loop: asyncio.AbstractEventLoop | None = None

    def _default_scheduler(self) -> AsyncIOScheduler:
        jobstore = SQLAlchemyJobStore(url=settings.alembic_url)
        return AsyncIOScheduler(jobstores={"default": jobstore})

    async def start(self) -> None:
        global _ACTIVE_MANAGER
        self._loop = asyncio.get_running_loop()
        if self._scheduler_factory is not None:
            self._sched = self._scheduler_factory()
        else:
            self._sched = self._default_scheduler()
        self._sched.start()
        _ACTIVE_MANAGER = self
        await self._reload_jobs()

    async def shutdown(self) -> None:
        global _ACTIVE_MANAGER
        if self._sched is not None:
            self._sched.shutdown(wait=False)
            self._sched = None
        _ACTIVE_MANAGER = None
        self._loop = None

    async def _reload_jobs(self) -> None:
        """Синхронизация in-DB job-ов APScheduler с automations таблицей.

        Идемпотентно: для каждой cron-автоматизации добавляет job если его нет,
        обновляет trigger если изменился, удаляет job если автоматизация
        пропала. Вызывается на старте; в дальнейшем CRUD-обёртки для
        автоматизаций должны точечно вызывать `add_or_update_job` / `remove_job`.
        """
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
            try:
                trigger = _parse_cron(cron)
            except ValueError as e:
                _log.warning("cron parse failed for %s: %s", a.id, e)
                continue
            self._sched.add_job(
                _job_async,
                trigger=trigger,
                args=[a.id],
                id=a.id,
                replace_existing=True,
            )
        # Удалим job-ы, которых больше нет в БД.
        existing_ids = {j.id for j in self._sched.get_jobs()}
        for aid in existing_ids - seen:
            try:
                self._sched.remove_job(aid)
            except Exception as e:  # APScheduler не имеет узкого исключения
                _log.debug("cron remove_job %s: %s", aid, e)

    # Public API для CRUD-обёрток автоматизаций (M3.10+ wiring может быть
    # подключён позднее; сейчас CRUD дёргает _reload_jobs через scheduled trigger).

    def add_or_update_cron(self, automation_id: str, cron_expr: str) -> None:
        if self._sched is None:
            return
        try:
            trigger = _parse_cron(cron_expr)
        except ValueError as e:
            _log.warning("cron parse failed for %s: %s", automation_id, e)
            return
        self._sched.add_job(
            _job_async,
            trigger=trigger,
            args=[automation_id],
            id=automation_id,
            replace_existing=True,
        )

    def remove_cron(self, automation_id: str) -> None:
        if self._sched is None:
            return
        try:
            self._sched.remove_job(automation_id)
        except Exception as e:
            _log.debug("cron remove_job %s: %s", automation_id, e)
