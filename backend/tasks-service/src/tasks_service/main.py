import asyncio
import logging
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
from tasks_service.routers.internal import router as internal_router
from tasks_service.routers.projects import router as projects_router
from tasks_service.routers.secrets import router as secrets_router
from tasks_service.routers.shares import router as shares_router
from tasks_service.routers.tasks import router as tasks_router
from tasks_service.routers.teams import router as teams_router
from tasks_service.services.cron_scheduler import CronManager
from tasks_service.services.prefix_lookup import (
    AmbiguousPrefix,
    PrefixNotFound,
    PrefixTooShort,
)
from tasks_service.services.reactive_matcher import run_reactive_matcher
from tasks_service.services.tariff_enforcement import TariffLimitExceeded
from tasks_service.services.webhook_outbox import run_outbox_worker

_log = logging.getLogger(__name__)

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
    # M3 фоновые подсистемы (ARCH §14): reactive_matcher, webhook_outbox,
    # cron_scheduler. Запускаются как asyncio-таски в lifespan.
    stop_event = asyncio.Event()
    sm = get_sessionmaker()
    cron_mgr = CronManager(sessionmaker=sm)
    await cron_mgr.start()
    # CronManager сам синкается через PostgreSQL jobstore (ARCH §11.3.1);
    # отдельная reload-таска больше не нужна — CRUD автоматизаций обязан
    # вызывать `CronManager.add_or_update_cron` / `remove_cron` точечно.
    bg_tasks = [
        asyncio.create_task(
            run_reactive_matcher(sm, stop_event=stop_event),
            name="reactive_matcher",
        ),
        asyncio.create_task(
            run_outbox_worker(sm, stop_event=stop_event),
            name="webhook_outbox",
        ),
    ]
    try:
        yield
    finally:
        stop_event.set()
        for task in bg_tasks:
            try:
                await asyncio.wait_for(task, timeout=5.0)
            except (TimeoutError, asyncio.CancelledError):
                task.cancel()
            except Exception as e:
                _log.warning("background task %s exited: %s", task.get_name(), e)
        await cron_mgr.shutdown()
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
    app.include_router(internal_router)

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

    @app.exception_handler(TariffLimitExceeded)
    async def _tariff_limit_exceeded(
        _req: Request, exc: TariffLimitExceeded
    ) -> JSONResponse:
        # tariff.md §17.1.1: error code tariff_limit_exceeded, поля subject_email,
        # metric, limit. Возвращаем как HTTP 400 — CLI распознаёт по error_code.
        return JSONResponse(
            status_code=400,
            content={
                "detail": "tariff_limit_exceeded",
                "error_code": "tariff_limit_exceeded",
                "subject_email": exc.subject_email,
                "metric": exc.metric,
                "limit": exc.limit,
            },
        )

    return app


app = create_app()
