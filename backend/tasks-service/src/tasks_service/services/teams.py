"""Сервис команд: create, get, update_name, member set/remove (PRD §6.4, §6.1)."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from tasks_service.models import Team, TeamMember, TeamPermission, User
from tasks_service.services.audit import record_audit


class TeamError(Exception):
    pass


class TeamNotFound(TeamError):
    pass


class PermissionDenied(TeamError):
    pass


class CannotGrantAboveSelf(TeamError):
    pass


# --- helpers ---


async def _get_member(
    session: AsyncSession, team_id: str, user_id: str
) -> TeamMember | None:
    result = await session.execute(
        select(TeamMember).where(
            TeamMember.team_id == team_id, TeamMember.user_id == user_id
        )
    )
    return result.scalar_one_or_none()


async def _get_team(session: AsyncSession, team_id: str) -> Team:
    result = await session.execute(select(Team).where(Team.id == team_id))
    team = result.scalar_one_or_none()
    if team is None:
        raise TeamNotFound(str(team_id))
    return team


def _require_perm(member: TeamMember | None, perm: TeamPermission) -> None:
    if member is None or perm.value not in member.perms:
        raise PermissionDenied(f"missing team permission: {perm.value}")


# --- public API ---


async def create_team(session: AsyncSession, *, creator: User, name: str) -> Team:
    """Создаёт команду; создатель — единственный участник со всеми правами.

    Tariff: pre-check `teams` создателя (tariff.md §4.2.1, IPLAN §7.2.4.1).
    """
    from tasks_service.ids import new_team_id
    from tasks_service.services.tariff_enforcement import check_tariff_limit

    if not name.strip():
        raise TeamError("team name cannot be empty")
    clean_name = name.strip()
    await check_tariff_limit(session, user_id=creator.id, metric="teams")
    team = Team(id=new_team_id(clean_name), name=clean_name)
    session.add(team)
    await session.flush()
    full_perms = [p.value for p in TeamPermission]
    session.add(TeamMember(team_id=team.id, user_id=creator.id, perms=full_perms))
    await session.flush()
    await record_audit(
        session,
        actor_user_id=creator.id,
        target_type="team",
        target_id=team.id,
        event_type="team.created",
        payload={"name": team.name},
    )
    return team


async def get_team(session: AsyncSession, *, current: User, team_id: str) -> Team:
    """Доступно при наличии ≥1 разрешения (PRD §6.1.8 — read неявное)."""
    team = await _get_team(session, team_id)
    member = await _get_member(session, team.id, current.id)
    if member is None or not member.perms:
        raise PermissionDenied("not a member of team")
    return team


async def update_name(
    session: AsyncSession, *, current: User, team_id: str, new_name: str
) -> Team:
    team = await _get_team(session, team_id)
    member = await _get_member(session, team.id, current.id)
    _require_perm(member, TeamPermission.EDIT_TEAM_NAME)
    if not new_name.strip():
        raise TeamError("team name cannot be empty")
    old = team.name
    team.name = new_name.strip()
    await session.flush()
    await record_audit(
        session,
        actor_user_id=current.id,
        target_type="team",
        target_id=team.id,
        event_type="team.renamed",
        payload={"old": old, "new": team.name},
    )
    return team


async def set_member_permissions(
    session: AsyncSession,
    *,
    current: User,
    team_id: str,
    target_user_id: str,
    perms: list[str],
) -> TeamMember | None:
    """Устанавливает разрешения участника. Пустой список = удаление участника.

    Правило share-not-above-self (PRD §6.1.7) — нельзя дать больше, чем имеешь.
    """
    team = await _get_team(session, team_id)
    current_member = await _get_member(session, team.id, current.id)
    # Self-revoke — всегда доступен; иначе требуется manage_member_permissions.
    if current.id == target_user_id:
        if perms:
            # Менять свои собственные права — тоже регулируется правилом не-выше-себя.
            _check_within_self(perms, current_member.perms if current_member else [])
    else:
        _require_perm(current_member, TeamPermission.MANAGE_MEMBER_PERMISSIONS)
        _check_within_self(perms, current_member.perms if current_member else [])

    # Валидация — все perms должны быть из enum.
    valid = {p.value for p in TeamPermission}
    invalid = [p for p in perms if p not in valid]
    if invalid:
        raise TeamError(f"unknown team permissions: {invalid}")

    if not perms:
        # Удаление участника (PRD §6.1.3).
        existing = await _get_member(session, team.id, target_user_id)
        if existing is None:
            return None
        await session.delete(existing)
        await session.flush()
        await record_audit(
            session,
            actor_user_id=current.id,
            target_type="team",
            target_id=team.id,
            event_type="team.member_removed",
            payload={"user_id": str(target_user_id)},
        )
        # Каскад lifecycle: если команда осталась без участников — удалить.
        any_left = await session.execute(
            select(TeamMember.user_id).where(TeamMember.team_id == team.id).limit(1)
        )
        if any_left.first() is None:
            await session.delete(team)
            await session.flush()
        return None

    # Tariff: pre-check `teams` адресата если это новый INSERT
    # (tariff.md §4.2.2, IPLAN §7.2.4.1). Существующая запись (perms update)
    # лимита не трогает.
    existing = await _get_member(session, team.id, target_user_id)
    if existing is None:
        from tasks_service.services.tariff_enforcement import check_tariff_limit

        await check_tariff_limit(session, user_id=target_user_id, metric="teams")
    # Upsert.
    stmt = (
        pg_insert(TeamMember)
        .values(team_id=team.id, user_id=target_user_id, perms=perms)
        .on_conflict_do_update(
            index_elements=["team_id", "user_id"], set_={"perms": perms}
        )
        .returning(TeamMember)
    )
    result = await session.execute(stmt)
    member = result.scalar_one()
    await session.flush()
    await record_audit(
        session,
        actor_user_id=current.id,
        target_type="team",
        target_id=team.id,
        event_type="team.member_set",
        payload={"user_id": str(target_user_id), "perms": perms},
    )
    return member


def _check_within_self(target_perms: list[str], own_perms: list[str]) -> None:
    own = set(own_perms)
    target_set = set(target_perms)
    extras = target_set - own
    if extras:
        raise CannotGrantAboveSelf(f"cannot grant perms above own: {sorted(extras)}")


async def list_members(session: AsyncSession, *, team_id: str) -> list[TeamMember]:
    result = await session.execute(
        select(TeamMember)
        .where(TeamMember.team_id == team_id)
        .order_by(TeamMember.user_id)
    )
    return list(result.scalars().all())


async def list_teams_for_user(session: AsyncSession, *, user: User) -> list[Team]:
    """Все команды, в которых current user — участник (≥1 разрешение)."""
    member_team_ids = await session.execute(
        select(TeamMember.team_id).where(TeamMember.user_id == user.id)
    )
    team_ids = list(member_team_ids.scalars().all())
    if not team_ids:
        return []
    result = await session.execute(
        select(Team).where(Team.id.in_(team_ids)).order_by(Team.created_at, Team.id)
    )
    return list(result.scalars().all())
