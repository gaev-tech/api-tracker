from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from auth_service.ids import user_id_for
from auth_service.models import User


async def get_or_create_user(session: AsyncSession, email: str) -> User:
    """Идемпотентный поиск/создание пользователя по email (PRD §10.4)."""
    email = email.strip().lower()
    result = await session.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    if user is not None:
        return user
    user = User(id=user_id_for(email), email=email)
    session.add(user)
    await session.flush()
    return user


async def get_user_by_email(session: AsyncSession, email: str) -> User | None:
    result = await session.execute(select(User).where(User.email == email.lower()))
    return result.scalar_one_or_none()


async def get_user_by_id(session: AsyncSession, user_id: str) -> User | None:
    result = await session.execute(select(User).where(User.id == user_id))
    return result.scalar_one_or_none()
