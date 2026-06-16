"""Magic-link: issue (start) / confirm (click) / poll (CLI).

architecture.md §4.2 — magic-link click flow.
"""

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from auth_service.config import settings
from auth_service.crypto import generate_opaque_token, hash_token
from auth_service.models import MagicToken, SessionKind, User
from auth_service.services.sessions import create_session
from auth_service.services.users import get_or_create_user


class MagicTokenError(Exception):
    """Невалидный / истёкший / повторный magic-token (или сессия)."""


async def issue_magic_token(session: AsyncSession, *, email: str) -> tuple[str, UUID]:
    """Создаёт magic-token + login_session_id, возвращает (plaintext, session_id).

    Plaintext token уходит в URL-ссылке письма; session_id — клиенту для poll.
    """
    token = generate_opaque_token(32)
    login_session_id = uuid4()
    record = MagicToken(
        token_hash=hash_token(token),
        email=email.lower(),
        login_session_id=login_session_id,
        expires_at=datetime.now(UTC)
        + timedelta(seconds=settings.magic_token_ttl_seconds),
    )
    session.add(record)
    await session.flush()
    return token, login_session_id


def build_magic_link(token: str) -> str:
    base = settings.public_base_url.rstrip("/")
    return f"{base}/api/auth/magic/confirm?token={token}"


async def confirm_magic_token(session: AsyncSession, *, token: str) -> str:
    """Помечает токен подтверждённым; создаёт user если нет; возвращает email.

    ARCH §4.2.3.
    """
    th = hash_token(token)
    result = await session.execute(
        select(MagicToken).where(MagicToken.token_hash == th)
    )
    record = result.scalar_one_or_none()
    if record is None:
        raise MagicTokenError("token not found")
    now = datetime.now(UTC)
    if record.confirmed_at is not None:
        raise MagicTokenError("token already used")
    if record.expires_at < now:
        raise MagicTokenError("token expired")
    record.confirmed_at = now
    await get_or_create_user(session, email=record.email)
    await session.flush()
    return record.email


async def poll_login_session(
    session: AsyncSession, *, login_session_id: UUID, user_agent: str
) -> tuple[str, str, int, str] | None:
    """ARCH §4.2.4 — long-poll по login_session_id.

    Возвращает (access, refresh, ttl, email) если пользователь только что
    кликнул (первый успешный poll); None если ещё ждём подтверждения.
    Бросает MagicTokenError("expired") если истёк до клика, либо
    MagicTokenError("not_found") / MagicTokenError("already_delivered").
    """
    result = await session.execute(
        select(MagicToken)
        .where(MagicToken.login_session_id == login_session_id)
        .with_for_update()
    )
    record = result.scalar_one_or_none()
    if record is None:
        raise MagicTokenError("not_found")
    now = datetime.now(UTC)
    if record.delivered_at is not None:
        raise MagicTokenError("already_delivered")
    if record.confirmed_at is None:
        if record.expires_at < now:
            raise MagicTokenError("expired")
        return None
    # confirmed_at установлен, delivered_at пуст — выдаём токены однократно.
    user_result = await session.execute(select(User).where(User.email == record.email))
    user = user_result.scalar_one()
    access, refresh, ttl = await create_session(
        session, user=user, kind=SessionKind.CLI, user_agent=user_agent
    )
    record.delivered_at = now
    await session.flush()
    return access, refresh, ttl, user.email
