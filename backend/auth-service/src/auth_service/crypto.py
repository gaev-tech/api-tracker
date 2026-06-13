"""Криптографические хелперы: токены, хеши, RSA-ключи для JWT."""

from __future__ import annotations

import base64
import hashlib
import secrets
from functools import lru_cache

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey, RSAPublicKey

from auth_service.config import settings


def generate_opaque_token(num_bytes: int = 32) -> str:
    """Случайный URL-safe токен в base64-url без padding."""
    return secrets.token_urlsafe(num_bytes)


def hash_token(token: str) -> str:
    """SHA-256 hex от plaintext-токена для безопасного хранения в БД."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def generate_user_code() -> str:
    """6-значный человекочитаемый код типа ABCD-1234 для device-flow."""
    alphabet = "ABCDEFGHJKLMNPQRSTVWXYZ23456789"  # без O,0,I,1,U
    return "-".join("".join(secrets.choice(alphabet) for _ in range(4)) for _ in range(2))


def _generate_ephemeral_keypair() -> tuple[bytes, bytes]:
    """Сгенерировать пару RSA-ключей; для dev-окружения без JWT_*_B64 в env."""
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    priv_pem = private.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    pub_pem = private.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return priv_pem, pub_pem


@lru_cache(maxsize=1)
def get_private_key() -> RSAPrivateKey:
    if settings.jwt_private_key_b64:
        pem = base64.b64decode(settings.jwt_private_key_b64)
    else:
        # dev fallback: сгенерировать ephemeral на время процесса.
        pem, _ = _generate_ephemeral_keypair()
    key = serialization.load_pem_private_key(pem, password=None)
    if not isinstance(key, RSAPrivateKey):
        raise RuntimeError("JWT_PRIVATE_KEY_B64 is not an RSA private key")
    return key


@lru_cache(maxsize=1)
def get_public_key() -> RSAPublicKey:
    if settings.jwt_public_key_b64:
        pem = base64.b64decode(settings.jwt_public_key_b64)
        key = serialization.load_pem_public_key(pem)
        if not isinstance(key, RSAPublicKey):
            raise RuntimeError("JWT_PUBLIC_KEY_B64 is not an RSA public key")
        return key
    return get_private_key().public_key()


def export_public_key_pem() -> str:
    pem = get_public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return pem.decode("utf-8")
