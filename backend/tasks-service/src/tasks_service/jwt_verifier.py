"""Верификация access-JWT через JWKS кеш (architecture.md §4.5, §6.3)."""

from typing import Any

import jwt

from tasks_service.config import settings
from tasks_service.jwks_cache import get_public_key


class JWTError(Exception):
    pass


async def verify_access_token(token: str) -> dict[str, Any]:
    """Проверяет JWT через закешированный публичный ключ.

    При истечении/ротации ключа автоматически refresh-ит кеш и повторяет
    верификацию один раз.
    """
    try:
        key = await get_public_key()
        return jwt.decode(token, key, algorithms=["RS256"], issuer=settings.jwt_issuer)
    except jwt.InvalidSignatureError:
        key = await get_public_key(force_refresh=True)
        try:
            return jwt.decode(token, key, algorithms=["RS256"], issuer=settings.jwt_issuer)
        except jwt.PyJWTError as e:
            raise JWTError(str(e)) from e
    except jwt.PyJWTError as e:
        raise JWTError(str(e)) from e
