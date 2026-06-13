"""gRPC-клиент к auth-service для JWKS и user-резолва (architecture.md §6)."""

from __future__ import annotations

import os
import sys
from functools import lru_cache

import grpc

_GEN_PATH = os.path.join(os.path.dirname(__file__), "generated")
if _GEN_PATH not in sys.path:
    sys.path.insert(0, _GEN_PATH)

from auth.v1 import auth_pb2_grpc  # noqa: E402

from tasks_service.config import settings  # noqa: E402


@lru_cache(maxsize=1)
def _get_channel() -> grpc.aio.Channel:
    return grpc.aio.insecure_channel(settings.auth_grpc_host)


def get_auth_stub() -> auth_pb2_grpc.AuthServiceStub:
    return auth_pb2_grpc.AuthServiceStub(_get_channel())


async def close_channel() -> None:
    """Вызывается в lifespan при shutdown."""
    ch = _get_channel()
    await ch.close()
    _get_channel.cache_clear()
