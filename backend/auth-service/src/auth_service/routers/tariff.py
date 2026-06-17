"""REST-эндпоинты тарифа (M5 — Free only).

См. tariff.md §15.1–§15.2, §16.2.1–§16.2.2; IPLAN §7.2.2.

Эндпоинты:
- `GET /api/auth/tariff/catalog` — public (без auth), список тарифов
  (в M5 — только Free).
- `GET /api/auth/me/tariff` — Bearer, состояние тарифа текущего пользователя:
  tariff, usage_*, limit_*.
"""

from __future__ import annotations

import logging

import httpx
from fastapi import APIRouter, HTTPException

from auth_service.auth_dep import AuthenticatedUserDep
from auth_service.config import settings
from auth_service.schemas import TariffCatalog, TariffCatalogEntry, TariffState
from auth_service.services.tariff import (
    FREE_PROJECTS,
    FREE_TASK_SHARES,
    FREE_TEAMS,
    get_user_limits,
)

_log = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["tariff"])


@router.get("/tariff/catalog", response_model=TariffCatalog)
async def get_catalog() -> TariffCatalog:
    """Каталог тарифов; public (tariff.md §16.2.1).

    M5: только Free. Pro/Max добавятся в M6 (IPLAN §8.2.2).
    """
    return TariffCatalog(
        entries=[
            TariffCatalogEntry(
                tier="free",
                task_shares=FREE_TASK_SHARES,
                projects=FREE_PROJECTS,
                teams=FREE_TEAMS,
            ),
        ],
    )


async def _fetch_membership_counts(user_id: str) -> tuple[int, int, int]:
    """Спросить tasks-svc о счётчиках permission-записей пользователя.

    M5-deferred fallback: при недоступности tasks-svc возвращаем (0,0,0)
    и логируем — `tariff show` не падает, но usage_* будут нулевыми.
    """
    url = f"{settings.tasks_service_url}/v1/internal/membership-counts/{user_id}"
    headers: dict[str, str] = {}
    if settings.internal_service_token:
        headers["X-Internal-Token"] = settings.internal_service_token
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(url, headers=headers)
        if resp.status_code != 200:
            _log.warning(
                "tasks-svc membership-counts returned %d for %s: %s",
                resp.status_code,
                user_id,
                resp.text[:200],
            )
            return (0, 0, 0)
        body = resp.json()
        return (
            int(body.get("task_shares", 0)),
            int(body.get("projects", 0)),
            int(body.get("teams", 0)),
        )
    except (httpx.HTTPError, ValueError) as e:
        _log.warning("tasks-svc membership-counts failed for %s: %s", user_id, e)
        return (0, 0, 0)


@router.get("/me/tariff", response_model=TariffState)
async def get_me_tariff(user: AuthenticatedUserDep) -> TariffState:
    """Состояние тарифа текущего пользователя (tariff.md §16.2.2)."""
    task_shares_limit, projects_limit, teams_limit = get_user_limits(user.tariff)
    usage_task_shares, usage_projects, usage_teams = await _fetch_membership_counts(
        user.id
    )
    return TariffState(
        tariff=user.tariff,
        usage_task_shares=usage_task_shares,
        limit_task_shares=task_shares_limit,
        usage_projects=usage_projects,
        limit_projects=projects_limit,
        usage_teams=usage_teams,
        limit_teams=teams_limit,
    )


# Reference imports kept for tooling
_ = HTTPException
