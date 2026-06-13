"""Share-эндпоинты задачи (M2.7c, PRD §6.2, §6.7)."""

from uuid import UUID

from fastapi import APIRouter, HTTPException
from pydantic import EmailStr
from sqlalchemy import select

from tasks_service.deps import CurrentUserDep, SessionDep
from tasks_service.models import Team, User
from tasks_service.schemas import (
    ShareSetRequest,
    TaskSharesRead,
    TaskShareTeamRead,
    TaskShareUserRead,
)
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


def _handle_error(e: Exception) -> None:
    if isinstance(e, (TaskNotFound, TeamNotFound)):
        raise HTTPException(status_code=404, detail=str(e))
    if isinstance(e, (PermissionDenied, CannotGrantAboveSelf)):
        raise HTTPException(status_code=403, detail=str(e))
    if isinstance(e, ShareError):
        raise HTTPException(status_code=400, detail=str(e))


async def _read_shares(session: SessionDep, task_id: UUID) -> TaskSharesRead:
    u_shares = await list_user_shares(session, task_id=task_id)
    t_shares = await list_team_shares(session, task_id=task_id)
    user_email_by_id: dict[UUID, str] = {}
    if u_shares:
        user_rows = await session.execute(
            select(User).where(User.id.in_([s.user_id for s in u_shares]))
        )
        user_email_by_id = {u.id: u.email for u in user_rows.scalars().all()}
    team_name_by_id: dict[UUID, str] = {}
    if t_shares:
        team_rows = await session.execute(
            select(Team).where(Team.id.in_([s.team_id for s in t_shares]))
        )
        team_name_by_id = {t.id: t.name for t in team_rows.scalars().all()}
    return TaskSharesRead(
        user_shares=[
            TaskShareUserRead(user_email=user_email_by_id.get(s.user_id, ""), perms=list(s.perms))
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


@router.get("", response_model=TaskSharesRead)
async def list_shares(
    task_id: UUID,
    session: SessionDep,
    user: CurrentUserDep,
) -> TaskSharesRead:
    return await _read_shares(session, task_id)


@router.put("/users/{email}", response_model=TaskSharesRead)
async def put_user_share(
    task_id: UUID,
    email: EmailStr,
    payload: ShareSetRequest,
    session: SessionDep,
    user: CurrentUserDep,
) -> TaskSharesRead:
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
        raise
    return await _read_shares(session, task_id)


@router.delete("/users/me", response_model=TaskSharesRead)
async def self_revoke(task_id: UUID, session: SessionDep, user: CurrentUserDep) -> TaskSharesRead:
    """Self-revoke (PRD §7.8.1)."""
    try:
        await set_user_share(
            session, current=user, task_id=task_id, target_user_id=user.id, perms=[]
        )
    except ShareError as e:
        _handle_error(e)
        raise
    return await _read_shares(session, task_id)


@router.put("/teams/{team_id}", response_model=TaskSharesRead)
async def put_team_share(
    task_id: UUID,
    team_id: UUID,
    payload: ShareSetRequest,
    session: SessionDep,
    user: CurrentUserDep,
) -> TaskSharesRead:
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
        raise
    return await _read_shares(session, task_id)
