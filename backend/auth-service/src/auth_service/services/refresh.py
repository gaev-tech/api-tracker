"""Rotate refresh-token (architecture.md §4.6)."""

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from auth_service.crypto import hash_token
from auth_service.models import RefreshToken, User
from auth_service.services.sessions import create_session


class RefreshError(Exception):
    pass


async def rotate_refresh(
    session: AsyncSession, *, refresh_plain: str, user_agent: str = ""
) -> tuple[str, str, int]:
    """Заменяет refresh-token на новый, возвращает (access, refresh, ttl)."""
    th = hash_token(refresh_plain)
    result = await session.execute(
        select(RefreshToken).where(RefreshToken.token_hash == th)
    )
    token = result.scalar_one_or_none()
    if token is None:
        raise RefreshError("refresh token not found")
    now = datetime.now(UTC)
    if token.revoked_at is not None:
        raise RefreshError("refresh token revoked")
    if token.expires_at < now:
        raise RefreshError("refresh token expired")
    token.revoked_at = now

    user_result = await session.execute(select(User).where(User.id == token.user_id))
    user = user_result.scalar_one_or_none()
    if user is None:
        raise RefreshError("user not found")

    return await create_session(
        session, user=user, kind=token.kind, label=token.label, user_agent=user_agent
    )
