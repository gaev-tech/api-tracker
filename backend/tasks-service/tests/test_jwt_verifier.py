"""Тесты JWT-верификатора с мок JWKS."""

from datetime import UTC, datetime, timedelta
from unittest.mock import patch
from uuid import uuid4

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

pytestmark = pytest.mark.asyncio(loop_scope="session")


def _make_keypair() -> tuple[bytes, rsa.RSAPrivateKey]:
    priv = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pub_pem = priv.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return pub_pem, priv


def _sign(priv: rsa.RSAPrivateKey, **overrides: object) -> str:
    now = int(datetime.now(UTC).timestamp())
    claims: dict[str, object] = {
        "sub": str(uuid4()),
        "email": "user@example.com",
        "iat": now,
        "exp": now + 3600,
        "iss": "apitracker.ru",
    }
    claims.update(overrides)
    return jwt.encode(claims, priv, algorithm="RS256")


async def test_verify_valid_token() -> None:
    from tasks_service.jwks_cache import clear_cache
    from tasks_service.jwt_verifier import verify_access_token

    pub_pem, priv = _make_keypair()
    pub_key = serialization.load_pem_public_key(pub_pem)

    clear_cache()
    with patch("tasks_service.jwt_verifier.get_public_key", return_value=pub_key):
        token = _sign(priv)
        claims = await verify_access_token(token)
    assert claims["email"] == "user@example.com"
    clear_cache()


async def test_verify_invalid_signature() -> None:
    from tasks_service.jwks_cache import clear_cache
    from tasks_service.jwt_verifier import JWTError, verify_access_token

    pub_pem, _ = _make_keypair()
    _, priv_other = _make_keypair()
    pub_key = serialization.load_pem_public_key(pub_pem)

    clear_cache()
    with patch("tasks_service.jwt_verifier.get_public_key", return_value=pub_key):
        token = _sign(priv_other)
        with pytest.raises(JWTError):
            await verify_access_token(token)
    clear_cache()


async def test_verify_expired() -> None:
    from tasks_service.jwks_cache import clear_cache
    from tasks_service.jwt_verifier import JWTError, verify_access_token

    pub_pem, priv = _make_keypair()
    pub_key = serialization.load_pem_public_key(pub_pem)

    clear_cache()
    with patch("tasks_service.jwt_verifier.get_public_key", return_value=pub_key):
        past = int((datetime.now(UTC) - timedelta(hours=2)).timestamp())
        token = _sign(priv, iat=past, exp=past + 60)
        with pytest.raises(JWTError):
            await verify_access_token(token)
    clear_cache()
