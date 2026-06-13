from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from pydantic import BaseModel

from tasks_service import __version__
from tasks_service.bootstrap import ensure_solo_user, run_migrations
from tasks_service.config import settings
from tasks_service.db import dispose_engine, get_sessionmaker
from tasks_service.grpc_client import close_channel
from tasks_service.routers.projects import router as projects_router
from tasks_service.routers.tasks import router as tasks_router
from tasks_service.routers.teams import router as teams_router


class HealthResponse(BaseModel):
    status: str
    version: str


class PingResponse(BaseModel):
    message: str


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    run_migrations()
    if settings.auth_mode == "disabled":
        sm = get_sessionmaker()
        async with sm() as session:
            await ensure_solo_user(session)
            await session.commit()
    yield
    await close_channel()
    await dispose_engine()


def create_app(*, with_lifespan: bool = True) -> FastAPI:
    app = FastAPI(
        title="api-tracker tasks-service",
        version=__version__,
        docs_url="/docs",
        openapi_url="/openapi.json",
        lifespan=lifespan if with_lifespan else None,
    )

    @app.get("/healthz", response_model=HealthResponse, tags=["meta"])
    async def healthz() -> HealthResponse:
        return HealthResponse(status="ok", version=__version__)

    @app.get("/v1/ping", response_model=PingResponse, tags=["meta"])
    async def ping() -> PingResponse:
        return PingResponse(message="pong")

    app.include_router(tasks_router)
    app.include_router(teams_router)
    app.include_router(projects_router)
    return app


app = create_app()
