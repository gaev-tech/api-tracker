"""Сервис секретов проекта (PRD §5.1.6, §8.7, ARCH §13)."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from tasks_service.ids import new_secret_id
from tasks_service.models import (
    ProjectPermission,
    ProjectSecret,
    ProjectUserMember,
    User,
)
from tasks_service.services.audit import record_audit
from tasks_service.services.crypto import decrypt, encrypt


class SecretError(Exception):
    pass


class SecretNotFound(SecretError):
    pass


class SecretPermissionDenied(SecretError):
    pass


async def _require_manage(
    session: AsyncSession, *, user: User, project_id: str
) -> None:
    """Проверка ProjectPermission.MANAGE_SECRETS у current user в проекте."""
    result = await session.execute(
        select(ProjectUserMember).where(
            ProjectUserMember.project_id == project_id,
            ProjectUserMember.user_id == user.id,
        )
    )
    member = result.scalar_one_or_none()
    if member is None or ProjectPermission.MANAGE_SECRETS.value not in member.perms:
        raise SecretPermissionDenied("missing permission: manage_secrets")


async def set_secret(
    session: AsyncSession,
    *,
    current: User,
    project_id: str,
    name: str,
    value: str,
) -> ProjectSecret:
    """Создать или обновить секрет (upsert на uq (project_id, name))."""
    await _require_manage(session, user=current, project_id=project_id)
    if not name.strip():
        raise SecretError("secret name cannot be empty")
    if not value:
        raise SecretError("secret value cannot be empty")
    enc = encrypt(value)
    sid = new_secret_id(project_id, name.strip())
    stmt = (
        pg_insert(ProjectSecret)
        .values(
            id=sid,
            project_id=project_id,
            name=name.strip(),
            value_encrypted=enc,
        )
        .on_conflict_do_update(
            index_elements=["project_id", "name"],
            set_={"value_encrypted": enc},
        )
        .returning(ProjectSecret)
    )
    result = await session.execute(stmt)
    secret = result.scalar_one()
    await session.flush()
    await record_audit(
        session,
        actor_user_id=current.id,
        target_type="project_secret",
        target_id=secret.id,
        event_type="secret.set",
        payload={"project_id": project_id, "name": secret.name},
    )
    return secret


async def list_secrets(
    session: AsyncSession, *, current: User, project_id: str
) -> list[ProjectSecret]:
    """Список секретов БЕЗ значений (ARCH §13.2)."""
    await _require_manage(session, user=current, project_id=project_id)
    result = await session.execute(
        select(ProjectSecret)
        .where(ProjectSecret.project_id == project_id)
        .order_by(ProjectSecret.name)
    )
    return list(result.scalars().all())


async def get_secret_by_id(
    session: AsyncSession, *, current: User, secret_id: str
) -> ProjectSecret:
    result = await session.execute(
        select(ProjectSecret).where(ProjectSecret.id == secret_id)
    )
    secret = result.scalar_one_or_none()
    if secret is None:
        raise SecretNotFound(secret_id)
    await _require_manage(session, user=current, project_id=secret.project_id)
    return secret


async def delete_secret(
    session: AsyncSession, *, current: User, secret_id: str
) -> None:
    secret = await get_secret_by_id(session, current=current, secret_id=secret_id)
    await session.delete(secret)
    await session.flush()
    await record_audit(
        session,
        actor_user_id=current.id,
        target_type="project_secret",
        target_id=secret_id,
        event_type="secret.deleted",
        payload={"project_id": secret.project_id, "name": secret.name},
    )


async def resolve_secrets_for_project(
    session: AsyncSession, *, project_id: str
) -> dict[str, str]:
    """Загрузить и расшифровать все секреты проекта (только для рендера автоматизаций).

    Не выставляется через REST: вызывается только из reactive_matcher/cron_scheduler
    при подготовке Jinja-контекста (ARCH §13.2, §11.5).
    """
    result = await session.execute(
        select(ProjectSecret).where(ProjectSecret.project_id == project_id)
    )
    out: dict[str, str] = {}
    for s in result.scalars().all():
        out[s.name] = decrypt(s.value_encrypted)
    return out
