"""REST-эндпоинты проектов (M2.7, PRD §6.5)."""

from uuid import UUID

from fastapi import APIRouter, HTTPException, status
from pydantic import EmailStr
from sqlalchemy import select

from tasks_service.deps import CurrentUserDep, SessionDep
from tasks_service.models import Project, Team, User
from tasks_service.schemas import (
    ProjectCreateRequest,
    ProjectMemberSetRequest,
    ProjectRead,
    ProjectTeamMemberRead,
    ProjectUpdateRequest,
    ProjectUserMemberRead,
)
from tasks_service.services.projects import (
    CannotGrantAboveSelf,
    PermissionDenied,
    ProjectError,
    ProjectNotFound,
    add_task_to_project,
    create_project,
    get_project,
    list_project_tasks,
    list_team_members,
    list_user_members,
    remove_task_from_project,
    set_team_member,
    set_user_member,
    update_name,
)
from tasks_service.user_resolver import ensure_user, resolve_email_to_user_id_via_grpc

router = APIRouter(prefix="/v1/projects", tags=["projects"])


def _handle_error(e: Exception) -> None:
    if isinstance(e, ProjectNotFound):
        raise HTTPException(status_code=404, detail=str(e))
    if isinstance(e, PermissionDenied | CannotGrantAboveSelf):
        raise HTTPException(status_code=403, detail=str(e))
    if isinstance(e, ProjectError):
        raise HTTPException(status_code=400, detail=str(e))


async def _to_read(session: SessionDep, project_id: UUID) -> ProjectRead:
    project = (await session.execute(select(Project).where(Project.id == project_id))).scalar_one()
    u_members = await list_user_members(session, project_id=project_id)
    t_members = await list_team_members(session, project_id=project_id)
    task_ids = await list_project_tasks(session, project_id=project_id)

    user_email_by_id: dict[UUID, str] = {}
    if u_members:
        user_rows = await session.execute(
            select(User).where(User.id.in_([m.user_id for m in u_members]))
        )
        user_email_by_id = {u.id: u.email for u in user_rows.scalars().all()}

    team_name_by_id: dict[UUID, str] = {}
    if t_members:
        team_rows = await session.execute(
            select(Team).where(Team.id.in_([m.team_id for m in t_members]))
        )
        team_name_by_id = {t.id: t.name for t in team_rows.scalars().all()}

    return ProjectRead(
        id=project.id,
        name=project.name,
        created_at=project.created_at,
        user_members=[
            ProjectUserMemberRead(
                user_email=user_email_by_id.get(m.user_id, ""), perms=list(m.perms)
            )
            for m in u_members
        ],
        team_members=[
            ProjectTeamMemberRead(
                team_id=m.team_id,
                team_name=team_name_by_id.get(m.team_id, ""),
                perms=list(m.perms),
            )
            for m in t_members
        ],
        task_ids=task_ids,
    )


@router.post("", response_model=ProjectRead, status_code=status.HTTP_201_CREATED)
async def create(
    payload: ProjectCreateRequest, session: SessionDep, user: CurrentUserDep
) -> ProjectRead:
    try:
        p = await create_project(session, creator=user, name=payload.name)
    except ProjectError as e:
        _handle_error(e)
        raise
    return await _to_read(session, p.id)


@router.get("/{project_id}", response_model=ProjectRead)
async def get(project_id: UUID, session: SessionDep, user: CurrentUserDep) -> ProjectRead:
    try:
        await get_project(session, current=user, project_id=project_id)
    except ProjectError as e:
        _handle_error(e)
        raise
    return await _to_read(session, project_id)


@router.patch("/{project_id}", response_model=ProjectRead)
async def patch_name(
    project_id: UUID,
    payload: ProjectUpdateRequest,
    session: SessionDep,
    user: CurrentUserDep,
) -> ProjectRead:
    try:
        await update_name(session, current=user, project_id=project_id, new_name=payload.name)
    except ProjectError as e:
        _handle_error(e)
        raise
    return await _to_read(session, project_id)


@router.put("/{project_id}/members/users/{email}", response_model=ProjectRead | None)
async def put_user_member(
    project_id: UUID,
    email: EmailStr,
    payload: ProjectMemberSetRequest,
    session: SessionDep,
    user: CurrentUserDep,
) -> ProjectRead | None:
    target_uid = await resolve_email_to_user_id_via_grpc(str(email))
    if target_uid is None:
        raise HTTPException(status_code=404, detail=f"user not found: {email}")
    await ensure_user(session, user_id=target_uid, email=str(email).lower())
    try:
        await set_user_member(
            session,
            current=user,
            project_id=project_id,
            target_user_id=target_uid,
            perms=payload.perms,
        )
    except ProjectError as e:
        _handle_error(e)
        raise
    p = (
        await session.execute(select(Project).where(Project.id == project_id))
    ).scalar_one_or_none()
    if p is None:
        return None
    return await _to_read(session, project_id)


@router.put("/{project_id}/members/teams/{team_id}", response_model=ProjectRead | None)
async def put_team_member(
    project_id: UUID,
    team_id: UUID,
    payload: ProjectMemberSetRequest,
    session: SessionDep,
    user: CurrentUserDep,
) -> ProjectRead | None:
    try:
        await set_team_member(
            session,
            current=user,
            project_id=project_id,
            target_team_id=team_id,
            perms=payload.perms,
        )
    except ProjectError as e:
        _handle_error(e)
        raise
    p = (
        await session.execute(select(Project).where(Project.id == project_id))
    ).scalar_one_or_none()
    if p is None:
        return None
    return await _to_read(session, project_id)


@router.delete("/{project_id}/members/me", response_model=ProjectRead | None)
async def leave(project_id: UUID, session: SessionDep, user: CurrentUserDep) -> ProjectRead | None:
    """Self-revoke (PRD §7.8.3)."""
    try:
        await set_user_member(
            session,
            current=user,
            project_id=project_id,
            target_user_id=user.id,
            perms=[],
        )
    except ProjectError as e:
        _handle_error(e)
        raise
    p = (
        await session.execute(select(Project).where(Project.id == project_id))
    ).scalar_one_or_none()
    if p is None:
        return None
    return await _to_read(session, project_id)


@router.post("/{project_id}/tasks/{task_id}", status_code=204)
async def add_task(
    project_id: UUID,
    task_id: UUID,
    session: SessionDep,
    user: CurrentUserDep,
) -> None:
    try:
        await add_task_to_project(session, current=user, project_id=project_id, task_id=task_id)
    except ProjectError as e:
        _handle_error(e)
        raise


@router.delete("/{project_id}/tasks/{task_id}", status_code=204)
async def remove_task(
    project_id: UUID,
    task_id: UUID,
    session: SessionDep,
    user: CurrentUserDep,
) -> None:
    try:
        await remove_task_from_project(
            session, current=user, project_id=project_id, task_id=task_id
        )
    except ProjectError as e:
        _handle_error(e)
        raise
