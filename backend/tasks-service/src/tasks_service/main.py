from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from importlib.metadata import version as _pkg_version

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from tasks_service.bootstrap import ensure_solo_user, run_migrations
from tasks_service.config import settings
from tasks_service.db import dispose_engine, get_sessionmaker
from tasks_service.grpc_client import close_channel
from tasks_service.routers.automations import router as automations_router
from tasks_service.routers.projects import router as projects_router
from tasks_service.routers.secrets import router as secrets_router
from tasks_service.routers.shares import router as shares_router
from tasks_service.routers.tasks import router as tasks_router
from tasks_service.routers.teams import router as teams_router
from tasks_service.services.prefix_lookup import (
    AmbiguousPrefix,
    PrefixNotFound,
    PrefixTooShort,
)

VERSION = _pkg_version("tasks-service")


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
        version=VERSION,
        docs_url="/docs",
        openapi_url="/openapi.json",
        lifespan=lifespan if with_lifespan else None,
    )

    @app.get("/healthz", response_model=HealthResponse, tags=["meta"])
    async def healthz() -> HealthResponse:
        return HealthResponse(status="ok", version=VERSION)

    @app.get("/v1/ping", response_model=PingResponse, tags=["meta"])
    async def ping() -> PingResponse:
        return PingResponse(message="pong")

    app.include_router(tasks_router)
    app.include_router(teams_router)
    app.include_router(projects_router)
    app.include_router(shares_router)
    app.include_router(automations_router)
    app.include_router(secrets_router)

    # PRD §5.2.7 prefix-lookup exceptions → HTTP.
    @app.exception_handler(PrefixTooShort)
    async def _prefix_too_short(_req: Request, _exc: PrefixTooShort) -> JSONResponse:
        return JSONResponse(status_code=400, content={"detail": "prefix_too_short"})

    @app.exception_handler(AmbiguousPrefix)
    async def _ambiguous_prefix(_req: Request, exc: AmbiguousPrefix) -> JSONResponse:
        return JSONResponse(
            status_code=409,
            content={
                "detail": "ambiguous_prefix",
                "candidates": [
                    {"id": cid, "discriminator": d} for cid, d in exc.candidates
                ],
            },
        )

    @app.exception_handler(PrefixNotFound)
    async def _prefix_not_found(_req: Request, _exc: PrefixNotFound) -> JSONResponse:
        return JSONResponse(status_code=404, content={"detail": "not_found"})

    return app


app = create_app()
