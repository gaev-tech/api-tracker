"""Pytest-фикстуры для интеграционных тестов auth-svc."""

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

from auth_service.config import settings
from auth_service.deps import get_db
from auth_service.main import create_app
from auth_service.models import Base


@pytest.fixture(autouse=True)
def smtp_host_default(monkeypatch: pytest.MonkeyPatch) -> None:
    """Тесты по умолчанию имеют сконфигурированный SMTP_HOST, чтобы /magic/start
    не падал с 500 (ARCH §4.2.1.1). Отдельные тесты могут переопределить."""
    monkeypatch.setattr(settings, "smtp_host", "smtp.test.local")


def _docker_available() -> bool:
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
    async with engine.begin() as conn:
        for tbl in reversed(Base.metadata.sorted_tables):
            await conn.execute(tbl.delete())
    async with sm() as s:
        yield s


@pytest_asyncio.fixture(loop_scope="session")
async def app(engine: AsyncEngine) -> AsyncIterator[FastAPI]:
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
async def client(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=cast(httpx.AsyncBaseTransport, app))  # type: ignore[arg-type]
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
