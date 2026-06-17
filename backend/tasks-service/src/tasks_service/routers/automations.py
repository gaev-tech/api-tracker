"""REST-эндпоинты автоматизаций (M3.2, PRD §8, ARCH §11)."""

from __future__ import annotations

from typing import Annotated, NoReturn

from fastapi import APIRouter, HTTPException, Query, status

from tasks_service.deps import CurrentUserDep, SessionDep
from tasks_service.models import Automation, Project
from tasks_service.schemas import (
    AutomationCreateRequest,
    AutomationRead,
    AutomationUpdateRequest,
)
from tasks_service.services.automations import (
    AutomationError,
    AutomationNotFound,
    AutomationPermissionDenied,
    create_automation,
    delete_automation,
    get_automation,
    list_automations,
    update_automation,
)
from tasks_service.services.prefix_lookup import resolve_prefix

router = APIRouter(prefix="/v1/automations", tags=["automations"])


async def _resolve_automation_key(session: SessionDep, key: str) -> str:
    return await resolve_prefix(
        session, id_column=Automation.id, discriminator_column=Automation.name, key=key
    )


async def _resolve_project_key(session: SessionDep, key: str) -> str:
    return await resolve_prefix(
        session, id_column=Project.id, discriminator_column=Project.name, key=key
    )


def _handle_error(e: Exception) -> NoReturn:
    if isinstance(e, AutomationNotFound):
        raise HTTPException(status_code=404, detail=str(e))
    if isinstance(e, AutomationPermissionDenied):
        raise HTTPException(status_code=403, detail=str(e))
    if isinstance(e, AutomationError):
        raise HTTPException(status_code=400, detail=str(e))
    raise HTTPException(status_code=500, detail=str(e))


@router.post("", response_model=AutomationRead, status_code=status.HTTP_201_CREATED)
async def create(
    payload: AutomationCreateRequest,
    session: SessionDep,
    user: CurrentUserDep,
) -> AutomationRead:
    project_id = await _resolve_project_key(session, payload.project_id)
    try:
        automation = await create_automation(
            session,
            current=user,
            project_id=project_id,
            name=payload.name,
            trigger_type=payload.trigger_type,
            trigger_config=payload.trigger_config,
            action_type=payload.action_type,
            action_config=payload.action_config,
        )
    except AutomationError as e:
        _handle_error(e)
    return AutomationRead.model_validate(automation)


@router.get("", response_model=list[AutomationRead])
async def list_for_project(
    session: SessionDep,
    user: CurrentUserDep,
    project_id: Annotated[str, Query(description="SHA1-ключ проекта (или префикс)")],
) -> list[AutomationRead]:
    pid = await _resolve_project_key(session, project_id)
    try:
        automations = await list_automations(session, current=user, project_id=pid)
    except AutomationError as e:
        _handle_error(e)
    return [AutomationRead.model_validate(a) for a in automations]


@router.get("/{automation_id}", response_model=AutomationRead)
async def get(
    automation_id: str, session: SessionDep, user: CurrentUserDep
) -> AutomationRead:
    aid = await _resolve_automation_key(session, automation_id)
    try:
        automation = await get_automation(session, current=user, automation_id=aid)
    except AutomationError as e:
        _handle_error(e)
    return AutomationRead.model_validate(automation)


@router.patch("/{automation_id}", response_model=AutomationRead)
async def patch(
    automation_id: str,
    payload: AutomationUpdateRequest,
    session: SessionDep,
    user: CurrentUserDep,
) -> AutomationRead:
    aid = await _resolve_automation_key(session, automation_id)
    try:
        automation = await update_automation(
            session,
            current=user,
            automation_id=aid,
            name=payload.name,
            trigger_config=payload.trigger_config,
            action_config=payload.action_config,
        )
    except AutomationError as e:
        _handle_error(e)
    return AutomationRead.model_validate(automation)


@router.delete("/{automation_id}", status_code=204)
async def delete(automation_id: str, session: SessionDep, user: CurrentUserDep) -> None:
    aid = await _resolve_automation_key(session, automation_id)
    try:
        await delete_automation(session, current=user, automation_id=aid)
    except AutomationError as e:
        _handle_error(e)
