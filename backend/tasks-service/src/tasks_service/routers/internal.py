"""Internal service-to-service endpoints (M5 tariff usage_*).

Эти эндпоинты НЕ предназначены для CLI/UI. Они вызываются auth-svc
для расчёта `tariff show` usage_*-полей (tariff.md §15.10). Защищаются
shared secret через заголовок `X-Internal-Token`.

В проде должны быть закрыты на сетевом уровне (only-internal network); токен
служит вторым уровнем защиты от случайных публичных запросов.
"""

from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select

from tasks_service.config import settings
from tasks_service.deps import SessionDep
from tasks_service.models import ProjectUserMember, TaskUserShare, TeamMember

router = APIRouter(prefix="/v1/internal", tags=["internal"])


class MembershipCounts(BaseModel):
    """Счётчики permission-записей пользователя (tariff.md §3)."""

    task_shares: int
    projects: int
    teams: int


def _check_internal_token(token: str | None) -> None:
    expected = settings.internal_service_token
    if not expected:
        # Dev/test-режим — проверка отключена.
        return
    if token != expected:
        raise HTTPException(status_code=403, detail="invalid internal token")


@router.get(
    "/membership-counts/{user_id}",
    response_model=MembershipCounts,
)
async def get_membership_counts(
    user_id: str,
    session: SessionDep,
    x_internal_token: str | None = Header(default=None, alias="X-Internal-Token"),
) -> MembershipCounts:
    """Активные permission-записи пользователя по трём tariff-метрикам.

    Frozen-фильтрация (tariff.md §3.1–3.3 `frozen=false`) добавится в M6;
    в M5 колонки `frozen` ещё нет — считаем все записи.
    """
    _check_internal_token(x_internal_token)
    task_shares = await session.scalar(
        select(func.count())
        .select_from(TaskUserShare)
        .where(TaskUserShare.user_id == user_id)
    )
    projects = await session.scalar(
        select(func.count())
        .select_from(ProjectUserMember)
        .where(ProjectUserMember.user_id == user_id)
    )
    teams = await session.scalar(
        select(func.count())
        .select_from(TeamMember)
        .where(TeamMember.user_id == user_id)
    )
    return MembershipCounts(
        task_shares=int(task_shares or 0),
        projects=int(projects or 0),
        teams=int(teams or 0),
    )
