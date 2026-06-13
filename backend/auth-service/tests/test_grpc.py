"""gRPC server: smoke и интеграционные тесты."""

import pytest

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def test_import_servicer() -> None:
    """grpc_server модуль импортируется без ошибок (sys.path injection работает)."""
    from auth_service.grpc_server import AuthServiceServicer, start_grpc_server

    assert AuthServiceServicer is not None
    assert callable(start_grpc_server)


async def test_jwks_returns_pem() -> None:
    """GetJWKS возвращает валидный PEM публичного ключа."""
    import grpc
    from auth.v1 import auth_pb2, auth_pb2_grpc

    from auth_service.grpc_server import start_grpc_server

    server = await start_grpc_server(port=0)
    port = (
        next(
            int(s.split(":")[-1])
            for s in dir(server)
            if False  # порт получаем иначе
        )
        if False
        else None
    )

    # grpc.aio.server.add_insecure_port возвращает выделенный порт; запрашиваем заново.
    # Простой обход: пересоздать с фиксированным портом (для тестов).
    await server.stop(grace=0)

    import socket

    sock = socket.socket()
    sock.bind(("", 0))
    port = sock.getsockname()[1]
    sock.close()

    server = await start_grpc_server(port=port)
    try:
        channel = grpc.aio.insecure_channel(f"localhost:{port}")
        stub = auth_pb2_grpc.AuthServiceStub(channel)
        resp = await stub.GetJWKS(auth_pb2.GetJWKSRequest())
        assert "BEGIN PUBLIC KEY" in resp.public_key_pem
        await channel.close()
    finally:
        await server.stop(grace=0)
