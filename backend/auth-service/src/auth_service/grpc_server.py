"""gRPC server для auth-service (architecture.md §6).

Сервис: AuthService с RPC GetUserByEmail, GetUsersByIds, GetJWKS.
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from uuid import UUID

import grpc

_GEN_PATH = os.path.join(os.path.dirname(__file__), "generated")
if _GEN_PATH not in sys.path:
    sys.path.insert(0, _GEN_PATH)

from auth.v1 import auth_pb2, auth_pb2_grpc  # noqa: E402

from auth_service.crypto import export_public_key_pem  # noqa: E402
from auth_service.db import get_sessionmaker  # noqa: E402
from auth_service.services.users import get_user_by_email, get_user_by_id  # noqa: E402

logger = logging.getLogger(__name__)

GRPC_PORT = 50051


class AuthServiceServicer(auth_pb2_grpc.AuthServiceServicer):  # type: ignore[misc]
    async def GetUserByEmail(
        self, request: auth_pb2.GetUserByEmailRequest, context: grpc.aio.ServicerContext
    ) -> auth_pb2.User:
        sm = get_sessionmaker()
        async with sm() as session:
            user = await get_user_by_email(session, request.email.lower())
        if user is None:
            await context.abort(
                grpc.StatusCode.NOT_FOUND, f"user not found: {request.email}"
            )
            raise AssertionError("unreachable")  # для mypy после abort
        return auth_pb2.User(
            id=str(user.id), email=user.email, created_at=user.created_at.isoformat()
        )

    async def GetUsersByIds(
        self, request: auth_pb2.GetUsersByIdsRequest, context: grpc.aio.ServicerContext
    ) -> auth_pb2.GetUsersByIdsResponse:
        sm = get_sessionmaker()
        out: list[auth_pb2.User] = []
        async with sm() as session:
            for id_str in request.ids:
                try:
                    uid = UUID(id_str)
                except ValueError:
                    continue
                user = await get_user_by_id(session, uid)
                if user is not None:
                    out.append(
                        auth_pb2.User(
                            id=str(user.id),
                            email=user.email,
                            created_at=user.created_at.isoformat(),
                        )
                    )
        return auth_pb2.GetUsersByIdsResponse(users=out)

    async def GetJWKS(
        self, request: auth_pb2.GetJWKSRequest, context: grpc.aio.ServicerContext
    ) -> auth_pb2.GetJWKSResponse:
        return auth_pb2.GetJWKSResponse(public_key_pem=export_public_key_pem())


async def start_grpc_server(port: int = GRPC_PORT) -> grpc.aio.Server:
    server = grpc.aio.server()
    auth_pb2_grpc.add_AuthServiceServicer_to_server(AuthServiceServicer(), server)
    server.add_insecure_port(f"0.0.0.0:{port}")
    await server.start()
    logger.info("gRPC server started on :%d", port)
    return server


async def run_grpc_forever(port: int = GRPC_PORT) -> None:
    server = await start_grpc_server(port)
    try:
        await server.wait_for_termination()
    except asyncio.CancelledError:
        await server.stop(grace=5)
        raise
