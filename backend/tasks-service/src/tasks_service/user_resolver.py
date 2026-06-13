"""Резолвинг email ↔ user_id через gRPC к auth-svc + локальный кеш в tasks.users."""

from __future__ import annotations

import os
import sys
from uuid import UUID

import grpc
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

_GEN_PATH = os.path.join(os.path.dirname(__file__), "generated")
if _GEN_PATH not in sys.path:
    sys.path.insert(0, _GEN_PATH)

from auth.v1 import auth_pb2  # noqa: E402

from tasks_service.grpc_client import get_auth_stub  # noqa: E402
from tasks_service.models import User  # noqa: E402


async def ensure_user(session: AsyncSession, *, user_id: UUID, email: str) -> User:
    """Идемпотентный upsert в tasks.users; вызывается при JWT-валидации."""
    stmt = (
        pg_insert(User)
        .values(id=user_id, email=email)
        .on_conflict_do_update(index_elements=["id"], set_={"email": email})
        .returning(User)
    )
    result = await session.execute(stmt)
    user = result.scalar_one()
    await session.flush()
    return user


async def resolve_email_to_user_id_via_grpc(email: str) -> UUID | None:
    """gRPC GetUserByEmail — возвращает UUID или None если NOT_FOUND."""
    stub = get_auth_stub()
    try:
        response = await stub.GetUserByEmail(
            auth_pb2.GetUserByEmailRequest(email=email.lower())
        )
    except grpc.RpcError as e:
        if hasattr(e, "code") and e.code() == grpc.StatusCode.NOT_FOUND:
            return None
        raise
    return UUID(response.id)


async def resolve_and_cache_email(session: AsyncSession, email: str) -> UUID | None:
    """Резолв email→user_id с локальным кешем + gRPC fallback.

    Стратегия:
    1) Look up в tasks.users.
    2) Если нет — gRPC GetUserByEmail.
    3) Если найден — кешируем в tasks.users.
    """
    result = await session.execute(select(User).where(User.email == email.lower()))
    user = result.scalar_one_or_none()
    if user is not None:
        return user.id

    uid = await resolve_email_to_user_id_via_grpc(email)
    if uid is None:
        return None
    await ensure_user(session, user_id=uid, email=email.lower())
    return uid
