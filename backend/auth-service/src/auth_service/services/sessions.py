"""Создание refresh-сессии и подписание access-token (architecture.md §4.5, §4.6)."""

from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from auth_service.config import settings
from auth_service.crypto import generate_opaque_token, hash_token
from auth_service.jwt_signer import sign_access_token
from auth_service.models import RefreshToken, Session, SessionKind, User


async def create_session(
    session: AsyncSession,
    *,
    user: User,
    kind: SessionKind,
    label: str = "",
    user_agent: str = "",
) -> tuple[str, str, int]:
    """Создаёт refresh+session, подписывает access. Возвращает (access, refresh, ttl_sec)."""
    refresh_plain = generate_opaque_token(32)
    refresh = RefreshToken(
        token_hash=hash_token(refresh_plain),
        user_id=user.id,
        kind=kind,
        label=label,
        expires_at=datetime.now(UTC) + timedelta(seconds=settings.refresh_token_ttl_seconds),
    )
    session.add(refresh)
    await session.flush()
    sess = Session(refresh_token_id=refresh.id, user_agent=user_agent)
    session.add(sess)
    await session.flush()
    access, _exp = sign_access_token(user.id, user.email)
    return access, refresh_plain, settings.access_token_ttl_seconds
