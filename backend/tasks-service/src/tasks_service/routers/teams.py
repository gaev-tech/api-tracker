"""REST-эндпоинты команд (M2.7, PRD §6.4)."""

from typing import NoReturn
from uuid import UUID

from fastapi import APIRouter, HTTPException, status
from pydantic import EmailStr
from sqlalchemy import select

from tasks_service.deps import CurrentUserDep, SessionDep
from tasks_service.models import User
from tasks_service.schemas import (
    TeamCreateRequest,
    TeamMemberRead,
    TeamMemberSetRequest,
    TeamRead,
    TeamUpdateRequest,
)
from tasks_service.services.teams import (
    CannotGrantAboveSelf,
    PermissionDenied,
    TeamError,
    TeamNotFound,
    create_team,
    get_team,
    list_members,
    list_teams_for_user,
    set_member_permissions,
    update_name,
)
from tasks_service.user_resolver import ensure_user, resolve_email_to_user_id_via_grpc

router = APIRouter(prefix="/v1/teams", tags=["teams"])


def _handle_team_error(e: Exception) -> NoReturn:
    if isinstance(e, TeamNotFound):
        raise HTTPException(status_code=404, detail=str(e))
    if isinstance(e, PermissionDenied | CannotGrantAboveSelf):
        raise HTTPException(status_code=403, detail=str(e))
    if isinstance(e, TeamError):
        raise HTTPException(status_code=400, detail=str(e))
    raise HTTPException(status_code=500, detail=str(e))


async def _team_to_read(session: SessionDep, team_id: UUID) -> TeamRead:
    from tasks_service.models import Team

    team_row = (
        await session.execute(select(Team).where(Team.id == team_id))
    ).scalar_one()
    members = await list_members(session, team_id=team_id)
    if not members:
        return TeamRead(
            id=team_row.id, name=team_row.name, created_at=team_row.created_at
        )
    user_ids = [m.user_id for m in members]
    user_rows = await session.execute(select(User).where(User.id.in_(user_ids)))
    id_to_email = {u.id: u.email for u in user_rows.scalars().all()}
    return TeamRead(
        id=team_row.id,
        name=team_row.name,
        created_at=team_row.created_at,
        members=[
            TeamMemberRead(
                user_email=id_to_email.get(m.user_id, ""), perms=list(m.perms)
            )
            for m in members
        ],
    )


@router.post("", response_model=TeamRead, status_code=status.HTTP_201_CREATED)
async def create(
    payload: TeamCreateRequest, session: SessionDep, user: CurrentUserDep
) -> TeamRead:
    try:
        team = await create_team(session, creator=user, name=payload.name)
    except TeamError as e:
        _handle_team_error(e)
    return await _team_to_read(session, team.id)


@router.get("", response_model=list[TeamRead])
async def list_teams(session: SessionDep, user: CurrentUserDep) -> list[TeamRead]:
    """Все команды текущего пользователя (PRD §6.1.8 — read неявное)."""
    teams = await list_teams_for_user(session, user=user)
    return [await _team_to_read(session, t.id) for t in teams]


@router.get("/{team_id}", response_model=TeamRead)
async def get(team_id: UUID, session: SessionDep, user: CurrentUserDep) -> TeamRead:
    try:
        await get_team(session, current=user, team_id=team_id)
    except TeamError as e:
        _handle_team_error(e)
    return await _team_to_read(session, team_id)


@router.patch("/{team_id}", response_model=TeamRead)
async def patch_name(
    team_id: UUID,
    payload: TeamUpdateRequest,
    session: SessionDep,
    user: CurrentUserDep,
) -> TeamRead:
    try:
        await update_name(session, current=user, team_id=team_id, new_name=payload.name)
    except TeamError as e:
        _handle_team_error(e)
    return await _team_to_read(session, team_id)


@router.put("/{team_id}/members/{email}", response_model=TeamRead)
async def set_member(
    team_id: UUID,
    email: EmailStr,
    payload: TeamMemberSetRequest,
    session: SessionDep,
    user: CurrentUserDep,
) -> TeamRead:
    """Установить разрешения участника по email. Пустой массив = удалить."""
    target_uid = await resolve_email_to_user_id_via_grpc(str(email))
    if target_uid is None:
        raise HTTPException(status_code=404, detail=f"user not found: {email}")
    # Гарантируем что target есть в локальной tasks.users (для FK).
    await ensure_user(session, user_id=target_uid, email=str(email).lower())
    try:
        await set_member_permissions(
            session,
            current=user,
            team_id=team_id,
            target_user_id=target_uid,
            perms=payload.perms,
        )
    except TeamError as e:
        _handle_team_error(e)
    return await _team_to_read(session, team_id)


@router.delete("/{team_id}/members/me", response_model=TeamRead | None)
async def leave(
    team_id: UUID, session: SessionDep, user: CurrentUserDep
) -> TeamRead | None:
    """Self-revoke (PRD §7.8.2). Всегда доступно текущему пользователю."""
    try:
        await set_member_permissions(
            session, current=user, team_id=team_id, target_user_id=user.id, perms=[]
        )
    except TeamError as e:
        _handle_team_error(e)
    # После leave команда может быть удалена (последний участник); вернём 204-like.
    from tasks_service.models import Team

    team = (
        await session.execute(select(Team).where(Team.id == team_id))
    ).scalar_one_or_none()
    if team is None:
        return None
    return await _team_to_read(session, team_id)


@router.get("/{team_id}/members", response_model=list[TeamMemberRead])
async def list_team_members(
    team_id: UUID, session: SessionDep, user: CurrentUserDep
) -> list[TeamMemberRead]:
    try:
        await get_team(session, current=user, team_id=team_id)
    except TeamError as e:
        _handle_team_error(e)
    members = await list_members(session, team_id=team_id)
    user_rows = await session.execute(
        select(User).where(User.id.in_([m.user_id for m in members]))
    )
    id_to_email = {u.id: u.email for u in user_rows.scalars().all()}
    return [
        TeamMemberRead(user_email=id_to_email.get(m.user_id, ""), perms=list(m.perms))
        for m in members
    ]
