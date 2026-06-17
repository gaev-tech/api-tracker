"""Tariff limit enforcement в tasks-svc (tariff.md §4, IPLAN §7.2.4).

Pre-check `tariff_limit_exceeded` перед INSERT'ом permission-записи во всех
точках tariff.md §4.2:
- team create: проверяется teams создателя.
- team share user add: проверяется teams приглашаемого.
- project create: проверяется projects создателя.
- project share user add: проверяется projects приглашаемого.
- task create (через user_shares[i]): проверяется task_shares каждого
  упомянутого пользователя, включая создателя (PRD §6.6.1.2).
- task share user add: проверяется task_shares адресата.

Лимиты получаются через gRPC AuthService.GetUserLimits с in-process кешем
TTL 5мин (IPLAN §7.2.4.2). В M5 значения статичны (200/3/3) — кеш формальный,
структура нужна для M6.

Атомарность limit-check + INSERT в одной транзакции (tariff.md §4.5, §18.5);
текущая (READ COMMITTED) изоляция и единый session обеспечивают консистентный
снимок при одновременных INSERT — допустимо для M5 (advisory-lock — M6).
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Final

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from tasks_service.grpc_client import get_auth_stub
from tasks_service.models import (
    ProjectUserMember,
    TaskUserShare,
    TeamMember,
    User,
)

_log = logging.getLogger(__name__)

_CACHE_TTL_SECONDS: Final[float] = 300.0


class TariffLimitExceeded(Exception):
    """tariff.md §17.1.1 — поля subject_email, metric, limit."""

    def __init__(self, *, subject_email: str, metric: str, limit: int | None) -> None:
        self.subject_email = subject_email
        self.metric = metric
        self.limit = limit
        super().__init__(
            f"tariff_limit_exceeded: {metric} for {subject_email} (limit={limit})"
        )


@dataclass(slots=True)
class _Limits:
    task_shares: int
    projects: int
    teams: int


_cache: dict[str, tuple[float, _Limits]] = {}


async def _get_user_limits(user_id: str) -> _Limits:
    """gRPC GetUserLimits с in-process кешем (TTL 5мин)."""
    now = time.monotonic()
    cached = _cache.get(user_id)
    if cached is not None and (now - cached[0]) < _CACHE_TTL_SECONDS:
        return cached[1]
    # Avoid circular imports: import auth_pb2 only when needed.
    from auth.v1 import auth_pb2

    stub = get_auth_stub()
    try:
        resp = await stub.GetUserLimits(auth_pb2.GetUserLimitsRequest(user_id=user_id))
    except Exception as e:  # grpc.RpcError — широкий, фолбэк на Free.
        _log.warning(
            "GetUserLimits failed for %s: %s; falling back to Free", user_id, e
        )
        # Локальный fallback на Free-каталог (tariff.md §2.5).
        limits = _Limits(task_shares=200, projects=3, teams=3)
    else:
        limits = _Limits(
            task_shares=int(resp.task_shares),
            projects=int(resp.projects),
            teams=int(resp.teams),
        )
    _cache[user_id] = (now, limits)
    return limits


def clear_cache() -> None:
    """Тестовый/админский reset кеша."""
    _cache.clear()


async def _count_task_shares(session: AsyncSession, user_id: str) -> int:
    return int(
        await session.scalar(
            select(func.count())
            .select_from(TaskUserShare)
            .where(TaskUserShare.user_id == user_id)
        )
        or 0
    )


async def _count_projects(session: AsyncSession, user_id: str) -> int:
    return int(
        await session.scalar(
            select(func.count())
            .select_from(ProjectUserMember)
            .where(ProjectUserMember.user_id == user_id)
        )
        or 0
    )


async def _count_teams(session: AsyncSession, user_id: str) -> int:
    return int(
        await session.scalar(
            select(func.count())
            .select_from(TeamMember)
            .where(TeamMember.user_id == user_id)
        )
        or 0
    )


async def _user_email(session: AsyncSession, user_id: str) -> str:
    result = await session.execute(select(User.email).where(User.id == user_id))
    return str(result.scalar_one_or_none() or user_id)


async def check_tariff_limit(
    session: AsyncSession,
    *,
    user_id: str,
    metric: str,
    increment: int = 1,
) -> None:
    """Бросает TariffLimitExceeded если usage+increment > limit.

    Args:
        session: открытая AsyncSession; чтения counts работают в той же
            транзакции, что и последующий INSERT — это даёт консистентный
            снимок для M5 (см. модуль-docstring).
        user_id: SHA1-hex id адресата операции (tariff.md §4.2 — лимит
            проверяется на адресате, не на инициаторе).
        metric: 'task_shares' | 'projects' | 'teams'.
        increment: 1 для одиночной записи; >1 для bulk-вставки одного и того
            же пользователя (например, task с user_shares[]=[U,U] — нереально,
            но API оставляет).
    """
    limits = await _get_user_limits(user_id)
    if metric == "task_shares":
        usage = await _count_task_shares(session, user_id)
        limit: int | None = limits.task_shares
    elif metric == "projects":
        usage = await _count_projects(session, user_id)
        limit = limits.projects
    elif metric == "teams":
        usage = await _count_teams(session, user_id)
        limit = limits.teams
    else:
        raise ValueError(f"unknown metric: {metric!r}")
    # M5: лимиты всегда конечные. M6: limit может быть отрицательным как маркер
    # unlimited — заменим на None ниже.
    effective_limit: int | None = limit
    if effective_limit is None:
        return  # unlimited
    if usage + increment > effective_limit:
        email = await _user_email(session, user_id)
        raise TariffLimitExceeded(
            subject_email=email, metric=metric, limit=effective_limit
        )
