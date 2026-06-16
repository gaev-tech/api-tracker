"""FastAPI-зависимости: session, current_user_email."""

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from tasks_service.config import settings
from tasks_service.db import get_sessionmaker
from tasks_service.jwt_verifier import JWTError, verify_access_token
from tasks_service.models import User
from tasks_service.user_resolver import ensure_user


async def get_db() -> AsyncIterator[AsyncSession]:
    sm = get_sessionmaker()
    async with sm() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


SessionDep = Annotated[AsyncSession, Depends(get_db)]


async def _get_user_from_solo_mode(session: AsyncSession, request: Request) -> User:
    result = await session.execute(
        select(User).where(User.email == settings.solo_user_email)
    )
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=500, detail="solo user not bootstrapped")
    request.state.user_id = user.id
    return user


async def _get_user_from_jwt(session: AsyncSession, request: Request) -> User:
    auth_header = request.headers.get("authorization", "")
    if not auth_header.lower().startswith("bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="bearer token required"
        )
    token = auth_header[7:].strip()
    try:
        claims = await verify_access_token(token)
    except JWTError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail=f"invalid token: {e}"
        ) from e
    sub = claims.get("sub")
    email = claims.get("email")
    if not sub or not email:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="missing sub/email claims"
        )
    if not isinstance(sub, str) or len(sub) != 40:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid sub claim"
        )

    user = await ensure_user(session, user_id=sub, email=email)
    request.state.user_id = user.id
    return user


async def get_current_user(
    request: Request,
    session: SessionDep,
) -> User:
    """В M0/M1 (AUTH_MODE=disabled) — всегда возвращает SOLO_USER.
    В M2+ (AUTH_MODE=jwt) — валидирует JWT, upsert-ит юзера в tasks.users.
    """
    if settings.auth_mode == "disabled":
        return await _get_user_from_solo_mode(session, request)
    if settings.auth_mode == "jwt":
        return await _get_user_from_jwt(session, request)
    raise HTTPException(
        status_code=500, detail=f"unknown AUTH_MODE: {settings.auth_mode}"
    )


CurrentUserDep = Annotated[User, Depends(get_current_user)]


async def resolve_email_to_user_id(session: AsyncSession, email: str) -> str | None:
    result = await session.execute(select(User.id).where(User.email == email.lower()))
    return result.scalar_one_or_none()
