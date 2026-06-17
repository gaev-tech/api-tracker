from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from importlib.metadata import version as _pkg_version

from fastapi import FastAPI
from pydantic import BaseModel

from auth_service.bootstrap import run_migrations
from auth_service.db import dispose_engine
from auth_service.routers.cli import router as cli_router
from auth_service.routers.magic import router as magic_router
from auth_service.routers.tariff import router as tariff_router

VERSION = _pkg_version("auth-service")


class HealthResponse(BaseModel):
    status: str
    version: str


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    # Миграции уже запущены в __main__._serve() до старта uvicorn,
    # чтобы gRPC мог стартовать сразу. Но при with_lifespan=True
    # (запуск через uvicorn auth_service.main:app) нужно подстраховаться.
    run_migrations()
    yield
    await dispose_engine()


def create_app(*, with_lifespan: bool = True) -> FastAPI:
    app = FastAPI(
        title="api-tracker auth-service",
        version=VERSION,
        docs_url="/docs",
        openapi_url="/openapi.json",
        lifespan=lifespan if with_lifespan else None,
    )

    @app.get("/healthz", response_model=HealthResponse, tags=["meta"])
    async def healthz() -> HealthResponse:
        return HealthResponse(status="ok", version=VERSION)

    app.include_router(magic_router)
    app.include_router(cli_router)
    app.include_router(tariff_router)
    return app


app = create_app()
