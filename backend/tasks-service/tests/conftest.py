"""Pytest-фикстуры для интеграционных тестов tasks-svc."""

from collections.abc import AsyncIterator, Iterator
from typing import cast

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

try:
    from testcontainers.postgres import PostgresContainer

    _TESTCONTAINERS_AVAILABLE = True
except ImportError:
    _TESTCONTAINERS_AVAILABLE = False
    PostgresContainer = None  # type: ignore[assignment,misc]

from tasks_service.deps import get_db
from tasks_service.main import create_app
from tasks_service.models import Base, User


def _docker_available() -> bool:
    """Проверка наличия запущенного Docker daemon."""
    try:
        import docker
    except ImportError:
        return False
    try:
        docker.from_env().ping()
        return True
    except Exception:
        return False


@pytest.fixture(scope="session")
def postgres_container() -> Iterator[PostgresContainer]:
    if not _TESTCONTAINERS_AVAILABLE or not _docker_available():
        pytest.skip("Docker not running — integration tests skipped (locally)")
    container = PostgresContainer("postgres:16-alpine", driver="asyncpg")
    container.start()
    yield container
    container.stop()


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def engine(postgres_container: PostgresContainer) -> AsyncIterator[AsyncEngine]:
    url = postgres_container.get_connection_url()
    eng = create_async_engine(url, echo=False, poolclass=NullPool)
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture(loop_scope="session")
async def session(engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    sm = async_sessionmaker(engine, expire_on_commit=False)
    # Очищаем таблицы перед каждым тестом, чтобы тесты были независимы.
    async with engine.begin() as conn:
        for tbl in reversed(Base.metadata.sorted_tables):
            await conn.execute(tbl.delete())
    async with sm() as s:
        yield s


@pytest_asyncio.fixture(loop_scope="session")
async def solo_user(session: AsyncSession) -> User:
    user = User(email="solo@test")
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


@pytest_asyncio.fixture(loop_scope="session")
async def app(engine: AsyncEngine, solo_user: User) -> AsyncIterator[FastAPI]:
    # Lifespan не нужен — миграции не запускаем, схему создали через metadata.create_all.
    application = create_app(with_lifespan=False)

    sm = async_sessionmaker(engine, expire_on_commit=False)

    async def _override_db() -> AsyncIterator[AsyncSession]:
        async with sm() as s:
            try:
                yield s
                await s.commit()
            except Exception:
                await s.rollback()
                raise

    application.dependency_overrides[get_db] = _override_db
    yield application


@pytest_asyncio.fixture(loop_scope="session")
async def client(
    app: FastAPI, solo_user: User, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[httpx.AsyncClient]:
    # Подменяем email SOLO_USER в settings, чтобы get_current_user находил тестового user.
    from tasks_service.config import settings

    monkeypatch.setattr(settings, "solo_user_email", solo_user.email)

    transport = httpx.ASGITransport(app=cast(httpx.AsyncBaseTransport, app))  # type: ignore[arg-type]
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
