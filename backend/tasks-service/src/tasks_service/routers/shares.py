"""Share-эндпоинты задачи (M2.7c, PRD §6.2, §6.7)."""

from typing import NoReturn

from fastapi import APIRouter, HTTPException
from pydantic import EmailStr
from sqlalchemy import select

from tasks_service.deps import CurrentUserDep, SessionDep
from tasks_service.models import Task, Team, User
from tasks_service.schemas import (
    ShareSetRequest,
    TaskSharesRead,
    TaskShareTeamRead,
    TaskShareUserRead,
)
from tasks_service.services.prefix_lookup import resolve_prefix
from tasks_service.services.shares import (
    CannotGrantAboveSelf,
    PermissionDenied,
    ShareError,
    TaskNotFound,
    TeamNotFound,
    list_team_shares,
    list_user_shares,
    set_team_share,
    set_user_share,
)
from tasks_service.user_resolver import ensure_user, resolve_email_to_user_id_via_grpc

router = APIRouter(prefix="/v1/tasks/{task_id}/share", tags=["shares"])


def _handle_error(e: Exception) -> NoReturn:
    if isinstance(e, TaskNotFound | TeamNotFound):
        raise HTTPException(status_code=404, detail=str(e))
    if isinstance(e, PermissionDenied | CannotGrantAboveSelf):
        raise HTTPException(status_code=403, detail=str(e))
    if isinstance(e, ShareError):
        raise HTTPException(status_code=400, detail=str(e))
    raise HTTPException(status_code=500, detail=str(e))


async def _read_shares(session: SessionDep, task_id: str) -> TaskSharesRead:
    u_shares = await list_user_shares(session, task_id=task_id)
    t_shares = await list_team_shares(session, task_id=task_id)
    user_email_by_id: dict[str, str] = {}
    if u_shares:
        user_rows = await session.execute(
            select(User).where(User.id.in_([s.user_id for s in u_shares]))
        )
        user_email_by_id = {u.id: u.email for u in user_rows.scalars().all()}
    team_name_by_id: dict[str, str] = {}
    if t_shares:
        team_rows = await session.execute(
            select(Team).where(Team.id.in_([s.team_id for s in t_shares]))
        )
        team_name_by_id = {t.id: t.name for t in team_rows.scalars().all()}
    return TaskSharesRead(
        user_shares=[
            TaskShareUserRead(
                user_email=user_email_by_id.get(s.user_id, ""), perms=list(s.perms)
            )
            for s in u_shares
        ],
        team_shares=[
            TaskShareTeamRead(
                team_id=s.team_id,
                team_name=team_name_by_id.get(s.team_id, ""),
                perms=list(s.perms),
            )
            for s in t_shares
        ],
    )


async def _resolve_task_key(session: SessionDep, key: str) -> str:
    return await resolve_prefix(
        session, id_column=Task.id, discriminator_column=Task.title, key=key
    )


async def _resolve_team_key(session: SessionDep, key: str) -> str:
    return await resolve_prefix(
        session, id_column=Team.id, discriminator_column=Team.name, key=key
    )


@router.get("", response_model=TaskSharesRead)
async def list_shares(
    task_id: str,
    session: SessionDep,
    user: CurrentUserDep,
) -> TaskSharesRead:
    task_id = await _resolve_task_key(session, task_id)
    return await _read_shares(session, task_id)


@router.put("/users/{email}", response_model=TaskSharesRead)
async def put_user_share(
    task_id: str,
    email: EmailStr,
    payload: ShareSetRequest,
    session: SessionDep,
    user: CurrentUserDep,
) -> TaskSharesRead:
    task_id = await _resolve_task_key(session, task_id)
    target_uid = await resolve_email_to_user_id_via_grpc(str(email))
    if target_uid is None:
        raise HTTPException(status_code=404, detail=f"user not found: {email}")
    await ensure_user(session, user_id=target_uid, email=str(email).lower())
    try:
        await set_user_share(
            session,
            current=user,
            task_id=task_id,
            target_user_id=target_uid,
            perms=payload.perms,
        )
    except ShareError as e:
        _handle_error(e)
    return await _read_shares(session, task_id)


@router.delete("/users/me", response_model=TaskSharesRead)
async def self_revoke(
    task_id: str, session: SessionDep, user: CurrentUserDep
) -> TaskSharesRead:
    """Self-revoke (PRD §7.8.1)."""
    task_id = await _resolve_task_key(session, task_id)
    try:
        await set_user_share(
            session, current=user, task_id=task_id, target_user_id=user.id, perms=[]
        )
    except ShareError as e:
        _handle_error(e)
    return await _read_shares(session, task_id)


@router.put("/teams/{team_id}", response_model=TaskSharesRead)
async def put_team_share(
    task_id: str,
    team_id: str,
    payload: ShareSetRequest,
    session: SessionDep,
    user: CurrentUserDep,
) -> TaskSharesRead:
    task_id = await _resolve_task_key(session, task_id)
    team_id = await _resolve_team_key(session, team_id)
    try:
        await set_team_share(
            session,
            current=user,
            task_id=task_id,
            target_team_id=team_id,
            perms=payload.perms,
        )
    except ShareError as e:
        _handle_error(e)
    return await _read_shares(session, task_id)
