"""JWT issuance и верификация RS256 (architecture.md §4.5)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import jwt

from auth_service.config import settings
from auth_service.crypto import get_private_key, get_public_key


def sign_access_token(user_id: UUID, email: str) -> tuple[str, datetime]:
    """Подписать access-token; возвращает (token, expires_at)."""
    now = datetime.now(UTC)
    exp = now.timestamp() + settings.access_token_ttl_seconds
    claims: dict[str, Any] = {
        "sub": str(user_id),
        "email": email,
        "iat": int(now.timestamp()),
        "exp": int(exp),
        "iss": settings.jwt_issuer,
    }
    # PyJWT принимает крипто-ключ объекта, не PEM-bytes — это работает.
    token = jwt.encode(claims, get_private_key(), algorithm="RS256")
    return token, datetime.fromtimestamp(exp, tz=UTC)


def verify_access_token(token: str) -> dict[str, Any]:
    """Распарсить и проверить access-token; возвращает claims."""
    return jwt.decode(
        token,
        get_public_key(),
        algorithms=["RS256"],
        issuer=settings.jwt_issuer,
    )
