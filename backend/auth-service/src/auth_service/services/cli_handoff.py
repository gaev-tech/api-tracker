"""CLI handoff: Pattern A (local callback) и Pattern B (device code).

См. architecture.md §4.3, §4.4.
"""

from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from auth_service.config import settings
from auth_service.crypto import generate_opaque_token, generate_user_code, hash_token
from auth_service.models import CliAuthCode, DeviceCode


class HandoffError(Exception):
    """Базовая ошибка handoff (mismatched state, expired, used и т.п.)."""


class AuthorizationPending(HandoffError):
    """Device-code ещё не approved пользователем."""


# === Pattern A: local-callback / PKCE ===


async def issue_cli_code(
    session: AsyncSession,
    *,
    user_id: UUID,
    state: str,
    code_challenge: str,
) -> str:
    """Создаёт single-use code, привязанный к user_id и code_challenge."""
    code_plain = generate_opaque_token(32)
    record = await _get_or_create_state(session, state, code_challenge)
    record.code_hash = hash_token(code_plain)
    record.user_id = user_id
    await session.flush()
    return code_plain


async def _get_or_create_state(
    session: AsyncSession, state: str, code_challenge: str
) -> CliAuthCode:
    result = await session.execute(select(CliAuthCode).where(CliAuthCode.state == state))
    existing = result.scalar_one_or_none()
    if existing is not None:
        if existing.code_used_at is not None:
            raise HandoffError("state already used")
        if existing.code_challenge != code_challenge:
            raise HandoffError("code_challenge mismatch")
        return existing
    record = CliAuthCode(
        state=state,
        code_challenge=code_challenge,
        expires_at=datetime.now(UTC) + timedelta(seconds=settings.cli_code_ttl_seconds),
    )
    session.add(record)
    await session.flush()
    return record


async def exchange_cli_code(
    session: AsyncSession,
    *,
    code: str,
    code_verifier: str,
) -> UUID:
    """Возвращает user_id, если code+verifier валидны и не использованы."""
    import base64
    import hashlib

    expected = (
        base64.urlsafe_b64encode(hashlib.sha256(code_verifier.encode("utf-8")).digest())
        .decode()
        .rstrip("=")
    )

    code_h = hash_token(code)
    result = await session.execute(select(CliAuthCode).where(CliAuthCode.code_hash == code_h))
    record = result.scalar_one_or_none()
    if record is None:
        raise HandoffError("code not found")
    if record.code_used_at is not None:
        raise HandoffError("code already used")
    if record.expires_at < datetime.now(UTC):
        raise HandoffError("code expired")
    if record.user_id is None:
        raise HandoffError("code not bound to user")
    if record.code_challenge != expected:
        raise HandoffError("code_verifier mismatch")

    record.code_used_at = datetime.now(UTC)
    await session.flush()
    return record.user_id


# === Pattern B: device code ===


async def start_device_flow(session: AsyncSession) -> dict[str, object]:
    """Создаёт device_code+user_code, возвращает что нужно показать CLI."""
    device_plain = generate_opaque_token(32)
    user_code = generate_user_code()
    record = DeviceCode(
        device_code=device_plain,
        user_code=user_code,
        expires_at=datetime.now(UTC) + timedelta(seconds=settings.device_code_ttl_seconds),
    )
    session.add(record)
    await session.flush()
    return {
        "device_code": device_plain,
        "user_code": user_code,
        "verification_url": f"{settings.public_base_url.rstrip('/')}/auth/device",
        "interval": 5,
        "expires_in": settings.device_code_ttl_seconds,
    }


async def approve_device(session: AsyncSession, *, user_code: str, user_id: UUID) -> None:
    """Помечает device_code как approved (вызывается из auth-client под Bearer)."""
    result = await session.execute(select(DeviceCode).where(DeviceCode.user_code == user_code))
    record = result.scalar_one_or_none()
    if record is None:
        raise HandoffError("user_code not found")
    if record.expires_at < datetime.now(UTC):
        raise HandoffError("user_code expired")
    if record.approved_at is not None:
        raise HandoffError("user_code already approved")
    record.user_id = user_id
    record.approved_at = datetime.now(UTC)
    await session.flush()


async def poll_device(session: AsyncSession, *, device_code: str) -> UUID:
    """Если device-code approved — возвращает user_id; иначе raise."""
    result = await session.execute(select(DeviceCode).where(DeviceCode.device_code == device_code))
    record = result.scalar_one_or_none()
    if record is None:
        raise HandoffError("device_code not found")
    if record.expires_at < datetime.now(UTC):
        raise HandoffError("device_code expired")
    if record.approved_at is None or record.user_id is None:
        raise AuthorizationPending("authorization_pending")
    # one-shot: после успешного poll помечаем expired, чтобы повторно не использовалось.
    record.expires_at = datetime.now(UTC)
    await session.flush()
    return record.user_id
