"""Unit-тесты для webhook outbox retry/backoff (PRD §8.6, ARCH §12.4).

Покрывают:
- attempt инкрементируется на каждой неудачной попытке;
- scheduled_at сдвигается по схеме 1с/5с/30с/2мин/10мин;
- после 5-го отказа status='dead_letter';
- 4xx ответы сразу переводят в dead_letter (без retry);
- 2xx ответы → status='sent', last_error очищен.

Тесты unit-уровня — без Postgres/Docker. Используем подмену `_process_one`
вход в виде живого WebhookOutbox-объекта (instance модели, не привязанный
к сессии) и мок-сессии с no-op `flush()`.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from tasks_service.models import WebhookOutbox, WebhookOutboxStatus
from tasks_service.services.webhook_outbox import (
    _BACKOFF_SECONDS,
    _MAX_ATTEMPTS,
    _process_one,
)


def _make_rec(attempt: int = 1) -> WebhookOutbox:
    """Свежий WebhookOutbox — не привязан к сессии, поля проставлены явно."""
    return WebhookOutbox(
        id="rec1",
        automation_id="aut1",
        attempt=attempt,
        scheduled_at=datetime.now(UTC),
        status=WebhookOutboxStatus.IN_PROGRESS,
        last_error=None,
        payload={"url": "http://example.com/hook", "headers": {}, "body": "ok"},
    )


def _mock_session() -> MagicMock:
    session = MagicMock()
    session.flush = AsyncMock(return_value=None)
    return session


def _mock_http_responding(status_code: int, text: str = "") -> MagicMock:
    """httpx.AsyncClient.post → response с заданным status_code."""
    response = MagicMock(spec=httpx.Response)
    response.status_code = status_code
    response.text = text
    http = MagicMock()
    http.post = AsyncMock(return_value=response)
    return http


def _mock_http_raising(exc: BaseException) -> MagicMock:
    """httpx.AsyncClient.post → raise (network error)."""
    http = MagicMock()
    http.post = AsyncMock(side_effect=exc)
    return http


@pytest.mark.asyncio
async def test_2xx_sets_sent() -> None:
    rec = _make_rec()
    http = _mock_http_responding(200, "ok")
    await _process_one(_mock_session(), rec, http=http)
    assert rec.status == WebhookOutboxStatus.SENT
    assert rec.last_error is None


@pytest.mark.asyncio
async def test_4xx_sets_dead_letter_without_retry() -> None:
    rec = _make_rec(attempt=1)
    http = _mock_http_responding(400, "bad request")
    await _process_one(_mock_session(), rec, http=http)
    assert rec.status == WebhookOutboxStatus.DEAD_LETTER
    assert rec.attempt == 1  # не инкрементировался — 4xx не ретраим
    assert rec.last_error is not None
    assert "400" in rec.last_error


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "current_attempt,expected_delay",
    [
        (1, _BACKOFF_SECONDS[0]),  # 1с
        (2, _BACKOFF_SECONDS[1]),  # 5с
        (3, _BACKOFF_SECONDS[2]),  # 30с
        (4, _BACKOFF_SECONDS[3]),  # 120с
    ],
)
async def test_5xx_backoff_schedule_matches_spec(
    current_attempt: int, expected_delay: int
) -> None:
    """attempt 1..4 → retry с backoff 1с/5с/30с/2мин/10мин (последний для 5)."""
    rec = _make_rec(attempt=current_attempt)
    before = datetime.now(UTC)
    http = _mock_http_responding(500, "server error")
    await _process_one(_mock_session(), rec, http=http)
    # Ретрай: status=PENDING, attempt инкрементирован, scheduled_at сдвинут.
    assert rec.status == WebhookOutboxStatus.PENDING
    assert rec.attempt == current_attempt + 1
    actual_delay = (rec.scheduled_at - before).total_seconds()
    # Допуск ± 1с (datetime.now вызывался дважды; backoff неинтерактивный).
    assert abs(actual_delay - expected_delay) < 1.5, (
        f"attempt={current_attempt}: expected ~{expected_delay}s, got {actual_delay}s"
    )
    assert rec.last_error is not None and "500" in rec.last_error


@pytest.mark.asyncio
async def test_5xx_on_attempt_5_goes_to_dead_letter() -> None:
    """attempt=_MAX_ATTEMPTS (5) → следующий fail должен дать dead_letter."""
    rec = _make_rec(attempt=_MAX_ATTEMPTS)
    http = _mock_http_responding(500, "still down")
    await _process_one(_mock_session(), rec, http=http)
    assert rec.status == WebhookOutboxStatus.DEAD_LETTER
    assert rec.attempt == _MAX_ATTEMPTS  # не инкрементируется при переходе в dead
    assert rec.last_error is not None and "500" in rec.last_error


@pytest.mark.asyncio
async def test_network_error_treated_as_retry() -> None:
    """ConnectError/timeout → retry с backoff, как 5xx."""
    rec = _make_rec(attempt=1)
    http = _mock_http_raising(httpx.ConnectError("connection refused"))
    await _process_one(_mock_session(), rec, http=http)
    assert rec.status == WebhookOutboxStatus.PENDING
    assert rec.attempt == 2
    assert rec.last_error is not None and "network" in rec.last_error


@pytest.mark.asyncio
async def test_full_failure_chain_through_5_attempts() -> None:
    """Цикл из 5 failure-ответов: attempts 1→2→3→4→5→dead_letter."""
    rec = _make_rec(attempt=1)
    http = _mock_http_responding(503, "down")
    session = _mock_session()
    expected_states: list[tuple[int, WebhookOutboxStatus, Any]] = [
        (2, WebhookOutboxStatus.PENDING, _BACKOFF_SECONDS[0]),
        (3, WebhookOutboxStatus.PENDING, _BACKOFF_SECONDS[1]),
        (4, WebhookOutboxStatus.PENDING, _BACKOFF_SECONDS[2]),
        (5, WebhookOutboxStatus.PENDING, _BACKOFF_SECONDS[3]),
        (5, WebhookOutboxStatus.DEAD_LETTER, None),
    ]
    for expected_attempt, expected_status, expected_delay in expected_states:
        before = datetime.now(UTC)
        await _process_one(session, rec, http=http)
        assert rec.attempt == expected_attempt, (
            f"after iter: expected attempt={expected_attempt}, got {rec.attempt}"
        )
        assert rec.status == expected_status, (
            f"after iter: expected status={expected_status}, got {rec.status}"
        )
        if expected_delay is not None:
            delta = (rec.scheduled_at - before).total_seconds()
            assert abs(delta - expected_delay) < 1.5
            # Сбрасываем status и продвигаемся на следующий тик — имитируем
            # выбор записи воркером через scheduled_at.
            rec.status = WebhookOutboxStatus.IN_PROGRESS
            rec.scheduled_at = datetime.now(UTC) - timedelta(seconds=1)
