"""REST-эндпоинты секретов проекта (M3.3, PRD §8.7, ARCH §13).

POST  /v1/projects/{pid}/secrets       — set (create or overwrite by name)
GET   /v1/projects/{pid}/secrets       — list (names without values)
DELETE /v1/projects/{pid}/secrets/{sid} — delete
"""

from __future__ import annotations

from typing import Annotated, NoReturn

from fastapi import APIRouter, Body, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field

from tasks_service.deps import CurrentUserDep, SessionDep
from tasks_service.models import Project, ProjectSecret
from tasks_service.schemas import SecretRead
from tasks_service.services.crypto import CryptoError
from tasks_service.services.prefix_lookup import resolve_prefix
from tasks_service.services.secrets import (
    SecretError,
    SecretNotFound,
    SecretPermissionDenied,
    delete_secret,
    list_secrets,
    set_secret,
)

router = APIRouter(prefix="/v1/projects/{project_id}/secrets", tags=["secrets"])


class SecretSetRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Annotated[str, Field(min_length=1, max_length=200)]
    value: Annotated[str, Field(min_length=1)]


async def _resolve_project_key(session: SessionDep, key: str) -> str:
    return await resolve_prefix(
        session, id_column=Project.id, discriminator_column=Project.name, key=key
    )


async def _resolve_secret_key(session: SessionDep, key: str) -> str:
    return await resolve_prefix(
        session,
        id_column=ProjectSecret.id,
        discriminator_column=ProjectSecret.name,
        key=key,
    )


def _handle_error(e: Exception) -> NoReturn:
    if isinstance(e, SecretNotFound):
        raise HTTPException(status_code=404, detail=str(e))
    if isinstance(e, SecretPermissionDenied):
        raise HTTPException(status_code=403, detail=str(e))
    if isinstance(e, CryptoError):
        raise HTTPException(status_code=500, detail=f"crypto: {e}")
    if isinstance(e, SecretError):
        raise HTTPException(status_code=400, detail=str(e))
    raise HTTPException(status_code=500, detail=str(e))


@router.post("", response_model=SecretRead, status_code=status.HTTP_201_CREATED)
async def set_(
    project_id: str,
    payload: Annotated[SecretSetRequest, Body()],
    session: SessionDep,
    user: CurrentUserDep,
) -> SecretRead:
    pid = await _resolve_project_key(session, project_id)
    try:
        secret = await set_secret(
            session,
            current=user,
            project_id=pid,
            name=payload.name,
            value=payload.value,
        )
    except (SecretError, CryptoError) as e:
        _handle_error(e)
    return SecretRead.model_validate(secret)


@router.get("", response_model=list[SecretRead])
async def list_for_project(
    project_id: str, session: SessionDep, user: CurrentUserDep
) -> list[SecretRead]:
    pid = await _resolve_project_key(session, project_id)
    try:
        secrets = await list_secrets(session, current=user, project_id=pid)
    except SecretError as e:
        _handle_error(e)
    return [SecretRead.model_validate(s) for s in secrets]


@router.delete("/{secret_id}", status_code=204)
async def delete(
    project_id: str,
    secret_id: str,
    session: SessionDep,
    user: CurrentUserDep,
) -> None:
    # project_id — для URL-симметрии; авторизация — по secret.project_id.
    await _resolve_project_key(session, project_id)
    sid = await _resolve_secret_key(session, secret_id)
    try:
        await delete_secret(session, current=user, secret_id=sid)
    except SecretError as e:
        _handle_error(e)
