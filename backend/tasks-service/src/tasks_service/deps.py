"""FastAPI-зависимости: session, current_user_email."""

from collections.abc import AsyncIterator
from typing import Annotated
from uuid import UUID

from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from tasks_service.config import settings
from tasks_service.db import get_sessionmaker
from tasks_service.models import User


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


async def get_current_user(
    request: Request,
    session: SessionDep,
) -> User:
    """В M0/M1 (AUTH_MODE=disabled) — всегда возвращает SOLO_USER.
    В M2+ (AUTH_MODE=jwt) — валидирует JWT и возвращает соответствующего пользователя.
    """
    if settings.auth_mode == "disabled":
        result = await session.execute(select(User).where(User.email == settings.solo_user_email))
        user = result.scalar_one_or_none()
        if user is None:
            raise HTTPException(status_code=500, detail="solo user not bootstrapped")
        # Сохраняем в request для удобства downstream обработчиков.
        request.state.user_id = user.id
        return user

    # M2+ — JWT-валидация, заглушка
    raise HTTPException(status_code=501, detail="AUTH_MODE=jwt not implemented in M1")


CurrentUserDep = Annotated[User, Depends(get_current_user)]


async def resolve_email_to_user_id(session: AsyncSession, email: str) -> UUID | None:
    result = await session.execute(select(User.id).where(User.email == email))
    return result.scalar_one_or_none()
