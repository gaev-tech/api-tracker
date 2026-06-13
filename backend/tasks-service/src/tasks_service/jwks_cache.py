"""In-process кеш JWKS-ключей от auth-svc (architecture.md §6.3)."""

from __future__ import annotations

import os
import sys
import time
from dataclasses import dataclass

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPublicKey

_GEN_PATH = os.path.join(os.path.dirname(__file__), "generated")
if _GEN_PATH not in sys.path:
    sys.path.insert(0, _GEN_PATH)

from auth.v1 import auth_pb2  # noqa: E402

from tasks_service.config import settings  # noqa: E402
from tasks_service.grpc_client import get_auth_stub  # noqa: E402


@dataclass
class _Cached:
    pem: str
    public_key: RSAPublicKey
    fetched_at: float


_cache: _Cached | None = None


async def get_public_key(*, force_refresh: bool = False) -> RSAPublicKey:
    """Возвращает публичный ключ для верификации JWT. Лениво загружает по gRPC."""
    global _cache
    now = time.time()
    if (
        not force_refresh
        and _cache is not None
        and now - _cache.fetched_at < settings.jwks_cache_ttl_seconds
    ):
        return _cache.public_key

    stub = get_auth_stub()
    response = await stub.GetJWKS(auth_pb2.GetJWKSRequest())
    pem_bytes = response.public_key_pem.encode("utf-8")
    key = serialization.load_pem_public_key(pem_bytes)
    if not isinstance(key, RSAPublicKey):
        raise RuntimeError("JWKS endpoint returned non-RSA public key")
    _cache = _Cached(pem=response.public_key_pem, public_key=key, fetched_at=now)
    return key


def clear_cache() -> None:
    global _cache
    _cache = None
