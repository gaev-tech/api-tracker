"""Запуск auth-service: HTTP (uvicorn) + gRPC параллельно."""

import asyncio

import uvicorn

from auth_service.bootstrap import run_migrations
from auth_service.grpc_server import GRPC_PORT, run_grpc_forever


async def _serve() -> None:
    config = uvicorn.Config(
        "auth_service.main:create_app",
        factory=True,
        host="0.0.0.0",  # noqa: S104 — bind all внутри контейнера
        port=8000,
        log_level="info",
    )
    server = uvicorn.Server(config)
    # Lifespan для FastAPI прокинет run_migrations (см. main.py),
    # но __main__ ВНЕ Uvicorn — миграции уже запустим тут заранее, чтобы
    # gRPC мог стартовать сразу после.
    run_migrations()
    grpc_task = asyncio.create_task(run_grpc_forever(GRPC_PORT))
    try:
        await server.serve()
    finally:
        grpc_task.cancel()
        try:
            await grpc_task
        except asyncio.CancelledError:
            pass


def main() -> None:
    asyncio.run(_serve())


if __name__ == "__main__":
    main()
