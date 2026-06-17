"""Webhook outbox worker (ARCH §12, PRD §8.6).

Фоновая asyncio-таска:
1. `SELECT * FROM webhook_outbox WHERE status='pending' AND scheduled_at <= now()
    FOR UPDATE SKIP LOCKED LIMIT N`.
2. HTTP POST с pre-рендеренным body (рендер делается уже на этапе постановки в очередь).
3. На 2xx → status='sent'.
4. На 5xx / network-error → backoff (1с, 5с, 30с, 2мин, 10мин), attempt += 1.
5. После 5 неуспешных попыток → status='dead_letter' (PRD §8.6.1).
"""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import UTC, datetime, timedelta
from hashlib import sha1
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from tasks_service.models import WebhookOutbox, WebhookOutboxStatus

_log = logging.getLogger(__name__)

# Backoff по попыткам (PRD §8.6.1, ARCH §12.4). attempt=1 — первая попытка.
# Время задержки используется при scheduling следующей попытки.
_BACKOFF_SECONDS: tuple[int, ...] = (1, 5, 30, 120, 600)
_MAX_ATTEMPTS = 5

# Сколько записей берём за один тик.
_BATCH_SIZE = 16

# Интервал между пустыми пробуждениями.
_IDLE_INTERVAL_SECONDS = 5.0


def _outbox_id(automation_id: str) -> str:
    raw = f"{automation_id}\n{time.time_ns()}"
    return sha1(raw.encode("utf-8"), usedforsecurity=False).hexdigest()


async def enqueue_webhook(
    session: AsyncSession,
    *,
    automation_id: str,
    url: str,
    headers: dict[str, str],
    body: str,
    scheduled_at: datetime | None = None,
) -> WebhookOutbox:
    """Поставить webhook-отправку в очередь.

    body и headers — уже отрендеренные строки. Рендер делается до постановки
    в очередь, чтобы при ретраях не повторять рендер (и не зависеть от состояния
    задачи на момент ретрая).
    """
    payload: dict[str, Any] = {"url": url, "headers": headers, "body": body}
    rec = WebhookOutbox(
        id=_outbox_id(automation_id),
        automation_id=automation_id,
        attempt=1,
        scheduled_at=scheduled_at or datetime.now(UTC),
        status=WebhookOutboxStatus.PENDING,
        payload=payload,
    )
    session.add(rec)
    await session.flush()
    return rec


async def _process_one(
    session: AsyncSession, rec: WebhookOutbox, *, http: httpx.AsyncClient
) -> None:
    """Попытка отправить одну запись. Caller контролирует commit/rollback."""
    payload = rec.payload
    url = str(payload.get("url", ""))
    headers_raw = payload.get("headers", {})
    headers: dict[str, str] = {}
    if isinstance(headers_raw, dict):
        for k, v in headers_raw.items():
            headers[str(k)] = str(v)
    body = str(payload.get("body", ""))
    try:
        response = await http.post(
            url, content=body.encode("utf-8"), headers=headers, timeout=30.0
        )
        if 200 <= response.status_code < 300:
            rec.status = WebhookOutboxStatus.SENT
            rec.last_error = None
            await session.flush()
            return
        # 4xx — не ретраим (клиентская ошибка); 5xx — ретраим.
        if 400 <= response.status_code < 500:
            rec.status = WebhookOutboxStatus.DEAD_LETTER
            rec.last_error = f"http {response.status_code}: {response.text[:500]}"
            await session.flush()
            return
        err = f"http {response.status_code}: {response.text[:500]}"
    except httpx.HTTPError as e:
        err = f"network: {e}"
    # Ретрай: переходим в PENDING с увеличенным attempt и scheduled_at.
    if rec.attempt >= _MAX_ATTEMPTS:
        rec.status = WebhookOutboxStatus.DEAD_LETTER
        rec.last_error = err
        await session.flush()
        return
    delay = _BACKOFF_SECONDS[min(rec.attempt - 1, len(_BACKOFF_SECONDS) - 1)]
    rec.attempt = rec.attempt + 1
    rec.scheduled_at = datetime.now(UTC) + timedelta(seconds=delay)
    rec.status = WebhookOutboxStatus.PENDING
    rec.last_error = err
    await session.flush()


async def _drain_once(
    sessionmaker: async_sessionmaker[AsyncSession], *, http: httpx.AsyncClient
) -> int:
    """Один тик: попытаться обработать до _BATCH_SIZE записей.

    Возвращает число обработанных записей. Используем
    FOR UPDATE SKIP LOCKED, чтобы несколько реплик не конфликтовали.
    """
    async with sessionmaker() as session:
        now = datetime.now(UTC)
        stmt = (
            select(WebhookOutbox)
            .where(
                WebhookOutbox.status == WebhookOutboxStatus.PENDING,
                WebhookOutbox.scheduled_at <= now,
            )
            .order_by(WebhookOutbox.scheduled_at)
            .limit(_BATCH_SIZE)
            .with_for_update(skip_locked=True)
        )
        result = await session.execute(stmt)
        records = list(result.scalars().all())
        if not records:
            await session.commit()
            return 0
        # Помечаем как in_progress, чтобы не подобрать второй раз внутри транзакции.
        for rec in records:
            rec.status = WebhookOutboxStatus.IN_PROGRESS
        await session.flush()
        for rec in records:
            try:
                await _process_one(session, rec, http=http)
            except Exception as e:
                _log.exception("webhook outbox: unexpected error: %s", e)
                rec.status = WebhookOutboxStatus.PENDING
                rec.last_error = f"worker exception: {e}"
                if rec.attempt < _MAX_ATTEMPTS:
                    delay = _BACKOFF_SECONDS[
                        min(rec.attempt - 1, len(_BACKOFF_SECONDS) - 1)
                    ]
                    rec.attempt = rec.attempt + 1
                    rec.scheduled_at = datetime.now(UTC) + timedelta(seconds=delay)
                else:
                    rec.status = WebhookOutboxStatus.DEAD_LETTER
        await session.commit()
        return len(records)


async def run_outbox_worker(
    sessionmaker: async_sessionmaker[AsyncSession],
    *,
    stop_event: asyncio.Event,
) -> None:
    """Главный цикл фонового воркера. Останавливается по stop_event."""
    async with httpx.AsyncClient() as http:
        while not stop_event.is_set():
            try:
                processed = await _drain_once(sessionmaker, http=http)
            except Exception as e:
                _log.exception("webhook outbox tick failed: %s", e)
                processed = 0
            if processed == 0:
                try:
                    await asyncio.wait_for(
                        stop_event.wait(), timeout=_IDLE_INTERVAL_SECONDS
                    )
                except TimeoutError:
                    pass
