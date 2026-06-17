"""Сервис автоматизаций — CRUD (PRD §8, ARCH §11)."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from tasks_service.ids import new_automation_id
from tasks_service.models import (
    Automation,
    AutomationActionType,
    AutomationTriggerType,
    ProjectPermission,
    ProjectUserMember,
    User,
)
from tasks_service.services.audit import record_audit


class AutomationError(Exception):
    pass


class AutomationNotFound(AutomationError):
    pass


class AutomationPermissionDenied(AutomationError):
    pass


# Whitelist system-методов (ARCH §11.4).
_SYSTEM_METHOD_WHITELIST: frozenset[str] = frozenset(
    {
        "tasks.list",
        "tasks.create",
        "tasks.bulk_update",
        "tasks.batch_update",
        "tasks.share",
    }
)


def system_method_whitelist() -> frozenset[str]:
    return _SYSTEM_METHOD_WHITELIST


async def _require_manage(
    session: AsyncSession, *, user: User, project_id: str
) -> None:
    """Проверка ProjectPermission.MANAGE_AUTOMATIONS у current user в проекте."""
    result = await session.execute(
        select(ProjectUserMember).where(
            ProjectUserMember.project_id == project_id,
            ProjectUserMember.user_id == user.id,
        )
    )
    member = result.scalar_one_or_none()
    if member is None or ProjectPermission.MANAGE_AUTOMATIONS.value not in member.perms:
        raise AutomationPermissionDenied("missing permission: manage_automations")


def _validate_trigger_config(
    trigger_type: AutomationTriggerType, cfg: dict[str, object]
) -> None:
    if trigger_type == AutomationTriggerType.CRON:
        cron = cfg.get("cron")
        if not isinstance(cron, str) or not cron.strip():
            raise AutomationError("cron trigger requires non-empty 'cron'")
        # Базовая sanity-check: 5 полей через пробел.
        parts = cron.split()
        if len(parts) not in (5, 6):
            raise AutomationError(
                f"invalid cron expression (expected 5 or 6 fields): {cron!r}"
            )
    elif trigger_type == AutomationTriggerType.EVENT:
        event_type = cfg.get("event_type")
        if not isinstance(event_type, str) or not event_type.strip():
            raise AutomationError("event trigger requires non-empty 'event_type'")
        # filter — необязателен; если задан, должен быть str.
        flt = cfg.get("filter")
        if flt is not None and not isinstance(flt, str):
            raise AutomationError("event trigger 'filter' must be a string (RSQL)")


def _validate_action_config(
    action_type: AutomationActionType, cfg: dict[str, object]
) -> None:
    if action_type == AutomationActionType.WEBHOOK:
        url = cfg.get("url")
        if not isinstance(url, str) or not url.startswith(("http://", "https://")):
            raise AutomationError("webhook action requires http(s) 'url'")
        headers = cfg.get("headers", {})
        if not isinstance(headers, dict):
            raise AutomationError("webhook 'headers' must be an object")
        body = cfg.get("body", "")
        if not isinstance(body, str):
            raise AutomationError("webhook 'body' must be a string (Jinja template)")
    elif action_type == AutomationActionType.SYSTEM_METHOD:
        method = cfg.get("method")
        if not isinstance(method, str):
            raise AutomationError("system_method action requires string 'method'")
        if method not in _SYSTEM_METHOD_WHITELIST:
            raise AutomationError(
                f"method not allowed: {method!r} "
                f"(whitelist: {sorted(_SYSTEM_METHOD_WHITELIST)})"
            )
        args = cfg.get("args", {})
        if not isinstance(args, dict):
            raise AutomationError("system_method 'args' must be an object")


async def create_automation(
    session: AsyncSession,
    *,
    current: User,
    project_id: str,
    name: str,
    trigger_type: AutomationTriggerType,
    trigger_config: dict[str, object],
    action_type: AutomationActionType,
    action_config: dict[str, object],
) -> Automation:
    await _require_manage(session, user=current, project_id=project_id)
    if not name.strip():
        raise AutomationError("automation name cannot be empty")
    _validate_trigger_config(trigger_type, trigger_config)
    _validate_action_config(action_type, action_config)
    automation = Automation(
        id=new_automation_id(project_id, name),
        project_id=project_id,
        name=name.strip(),
        trigger_type=trigger_type,
        trigger_config=trigger_config,
        action_type=action_type,
        action_config=action_config,
    )
    session.add(automation)
    await session.flush()
    await record_audit(
        session,
        actor_user_id=current.id,
        target_type="automation",
        target_id=automation.id,
        event_type="automation.created",
        payload={
            "project_id": project_id,
            "name": automation.name,
            "trigger_type": str(trigger_type),
            "action_type": str(action_type),
        },
    )
    return automation


async def list_automations(
    session: AsyncSession, *, current: User, project_id: str
) -> list[Automation]:
    await _require_manage(session, user=current, project_id=project_id)
    result = await session.execute(
        select(Automation)
        .where(Automation.project_id == project_id)
        .order_by(Automation.created_at, Automation.id)
    )
    return list(result.scalars().all())


async def get_automation(
    session: AsyncSession, *, current: User, automation_id: str
) -> Automation:
    result = await session.execute(
        select(Automation).where(Automation.id == automation_id)
    )
    automation = result.scalar_one_or_none()
    if automation is None:
        raise AutomationNotFound(automation_id)
    await _require_manage(session, user=current, project_id=automation.project_id)
    return automation


async def update_automation(
    session: AsyncSession,
    *,
    current: User,
    automation_id: str,
    name: str | None = None,
    trigger_config: dict[str, object] | None = None,
    action_config: dict[str, object] | None = None,
) -> Automation:
    automation = await get_automation(
        session, current=current, automation_id=automation_id
    )
    diff: dict[str, object] = {}
    if name is not None and name.strip() and name.strip() != automation.name:
        diff["name"] = {"old": automation.name, "new": name.strip()}
        automation.name = name.strip()
    if trigger_config is not None:
        trigger_type = AutomationTriggerType(automation.trigger_type)
        _validate_trigger_config(trigger_type, trigger_config)
        diff["trigger_config"] = "changed"
        automation.trigger_config = trigger_config
    if action_config is not None:
        action_type = AutomationActionType(automation.action_type)
        _validate_action_config(action_type, action_config)
        diff["action_config"] = "changed"
        automation.action_config = action_config
    if diff:
        await session.flush()
        await record_audit(
            session,
            actor_user_id=current.id,
            target_type="automation",
            target_id=automation.id,
            event_type="automation.updated",
            payload={"diff": diff},
        )
    return automation


async def delete_automation(
    session: AsyncSession, *, current: User, automation_id: str
) -> None:
    automation = await get_automation(
        session, current=current, automation_id=automation_id
    )
    await session.delete(automation)
    await session.flush()
    await record_audit(
        session,
        actor_user_id=current.id,
        target_type="automation",
        target_id=automation_id,
        event_type="automation.deleted",
        payload={"project_id": automation.project_id, "name": automation.name},
    )
