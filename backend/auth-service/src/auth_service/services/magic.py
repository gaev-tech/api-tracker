"""Magic-link issue / verify (architecture.md §4.2, PRD §10.2)."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from auth_service.config import settings
from auth_service.crypto import generate_opaque_token, hash_token
from auth_service.models import MagicToken, MagicTokenIntent


class MagicTokenError(Exception):
    """Невалидный/использованный/просроченный magic-token."""


async def issue_magic_token(session: AsyncSession, *, email: str, intent: MagicTokenIntent) -> str:
    """Создаёт magic-token в БД, возвращает plaintext (только для отправки в email)."""
    token = generate_opaque_token(32)
    record = MagicToken(
        token_hash=hash_token(token),
        email=email.lower(),
        intent=intent,
        expires_at=datetime.now(UTC) + timedelta(seconds=settings.magic_token_ttl_seconds),
    )
    session.add(record)
    await session.flush()
    return token


def build_magic_link(token: str, intent: MagicTokenIntent) -> str:
    base = settings.public_base_url.rstrip("/")
    return f"{base}/auth/magic?token={token}&intent={intent.value}"


async def verify_magic_token(session: AsyncSession, *, token: str, intent: MagicTokenIntent) -> str:
    """Возвращает email, если токен валиден. Поднимает MagicTokenError иначе."""
    th = hash_token(token)
    result = await session.execute(select(MagicToken).where(MagicToken.token_hash == th))
    record = result.scalar_one_or_none()
    if record is None:
        raise MagicTokenError("token not found")
    now = datetime.now(UTC)
    if record.used_at is not None:
        raise MagicTokenError("token already used")
    if record.expires_at < now:
        raise MagicTokenError("token expired")
    if record.intent != intent:
        raise MagicTokenError("intent mismatch")
    record.used_at = now
    await session.flush()
    return record.email
