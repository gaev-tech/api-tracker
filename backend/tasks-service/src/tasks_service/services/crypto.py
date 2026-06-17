"""AES-256-GCM шифрование для project_secrets (ARCH §13.1).

Формат блоба: 12-байтный nonce || ciphertext || 16-байтный tag (auth-tag интегрирован
в `AESGCM.encrypt` после ciphertext'а).
"""

from __future__ import annotations

import base64
import hashlib
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from tasks_service.config import settings

_KEY_LEN = 32  # AES-256
_NONCE_LEN = 12


class CryptoError(Exception):
    pass


def _get_master_key() -> bytes:
    """Извлечь и валидировать MASTER_SECRET_KEY (32 байта base64).

    В dev-режиме (AUTH_MODE=disabled) допускается пустой ключ — в этом случае
    он детерминированно выводится из solo_user_email через SHA256. Это нужно
    только для тестов и локального запуска.
    """
    raw = settings.master_secret_key.strip()
    if not raw:
        if settings.auth_mode != "disabled":
            raise CryptoError(
                "MASTER_SECRET_KEY must be set (32-byte base64) in jwt mode"
            )
        # Dev-режим: детерминированный ключ из solo_user_email.
        return hashlib.sha256(f"clite-dev-{settings.solo_user_email}".encode()).digest()
    try:
        key = base64.b64decode(raw, validate=True)
    except (ValueError, TypeError) as e:
        raise CryptoError(f"MASTER_SECRET_KEY is not valid base64: {e}") from e
    if len(key) != _KEY_LEN:
        raise CryptoError(
            f"MASTER_SECRET_KEY must decode to {_KEY_LEN} bytes (got {len(key)})"
        )
    return key


def encrypt(plaintext: str) -> bytes:
    """Зашифровать строку → bytes (nonce || ciphertext+tag)."""
    key = _get_master_key()
    aesgcm = AESGCM(key)
    nonce = os.urandom(_NONCE_LEN)
    ct = aesgcm.encrypt(nonce, plaintext.encode("utf-8"), associated_data=None)
    return nonce + ct


def decrypt(blob: bytes) -> str:
    """Расшифровать bytes (nonce || ciphertext+tag) → строка."""
    if len(blob) < _NONCE_LEN + 16:
        raise CryptoError("ciphertext blob is too short")
    key = _get_master_key()
    aesgcm = AESGCM(key)
    nonce, ct = blob[:_NONCE_LEN], blob[_NONCE_LEN:]
    try:
        plaintext = aesgcm.decrypt(nonce, ct, associated_data=None)
    except Exception as e:
        raise CryptoError(f"decryption failed: {e}") from e
    return plaintext.decode("utf-8")
