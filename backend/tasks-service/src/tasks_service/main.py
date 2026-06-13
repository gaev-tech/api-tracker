from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from pydantic import BaseModel

from tasks_service import __version__
from tasks_service.bootstrap import ensure_solo_user, run_migrations
from tasks_service.db import dispose_engine, get_sessionmaker
from tasks_service.routers.tasks import router as tasks_router


class HealthResponse(BaseModel):
    status: str
    version: str


class PingResponse(BaseModel):
    message: str


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    run_migrations()
    sm = get_sessionmaker()
    async with sm() as session:
        await ensure_solo_user(session)
        await session.commit()
    yield
    await dispose_engine()


def create_app() -> FastAPI:
    app = FastAPI(
        title="api-tracker tasks-service",
        version=__version__,
        docs_url="/docs",
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )

    @app.get("/healthz", response_model=HealthResponse, tags=["meta"])
    async def healthz() -> HealthResponse:
        return HealthResponse(status="ok", version=__version__)

    @app.get("/v1/ping", response_model=PingResponse, tags=["meta"])
    async def ping() -> PingResponse:
        return PingResponse(message="pong")

    app.include_router(tasks_router)
    return app


app = create_app()
