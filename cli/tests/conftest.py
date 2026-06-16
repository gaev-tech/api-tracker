"""E2E test harness: postgres testcontainer + tasks-svc subprocess + clite invocation.

Coverage map: `specs/cli-test-cases.md` — каждый тест в `e2e/` ссылается на TC-номер
в имени (`test_TC_<section>_<n>_*`); CI step `cli-cases-coverage` (M2.16) сверяет.

Nginx-stub: clite ожидает upstream под /api/* (prod: nginx стрипает /api перед
tasks-svc, см. deploy/nginx/conf.d/apitracker.ru.conf). В harness'е роль nginx
играет лёгкий stdlib-прокси (_NginxStub) — стрипает /api и форвардит на tasks-svc.
"""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from collections.abc import Iterator
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import httpx
import pytest
from testcontainers.postgres import PostgresContainer

REPO_ROOT = Path(__file__).resolve().parents[2]
TASKS_SVC_SRC = REPO_ROOT / "backend" / "tasks-service"


def _docker_available() -> bool:
    try:
        import docker  # type: ignore[import-untyped]

        docker.from_env().ping()
        return True
    except Exception:
        return False


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


@dataclass(frozen=True)
class TasksSvcHandle:
    base_url: str
    process: subprocess.Popen[bytes]


@dataclass(frozen=True)
class NginxStubHandle:
    base_url: str
    server: ThreadingHTTPServer
    thread: threading.Thread


def _make_nginx_stub(upstream: str) -> NginxStubHandle:
    """HTTP proxy: стрипает префикс /api и форвардит на upstream (tasks-svc).

    Mirrors deploy/nginx/conf.d/apitracker.ru.conf — `/api/v1/*` → `/v1/*`.
    """

    class _Handler(BaseHTTPRequestHandler):
        def _forward(self) -> None:
            path = self.path
            if path.startswith("/api/"):
                path = path[len("/api") :]
            url = upstream.rstrip("/") + path
            length = int(self.headers.get("Content-Length", "0"))
            body = self.rfile.read(length) if length else None
            req = urllib.request.Request(url, data=body, method=self.command)
            for header, value in self.headers.items():
                lower = header.lower()
                if lower in ("host", "content-length", "connection"):
                    continue
                req.add_header(header, value)
            try:
                resp = urllib.request.urlopen(req, timeout=30)
                status = resp.status
                data = resp.read()
                resp_headers = resp.headers
            except urllib.error.HTTPError as e:
                status = e.code
                data = e.read()
                resp_headers = e.headers
            self.send_response(status)
            for header, value in resp_headers.items():
                if header.lower() in (
                    "transfer-encoding",
                    "connection",
                    "content-encoding",
                    "content-length",
                ):
                    continue
                self.send_header(header, value)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        do_GET = _forward
        do_POST = _forward
        do_PUT = _forward
        do_PATCH = _forward
        do_DELETE = _forward
        do_HEAD = _forward
        do_OPTIONS = _forward

        def log_message(self, format: str, *args: object) -> None:
            return

    port = _free_port()
    server = ThreadingHTTPServer(("127.0.0.1", port), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return NginxStubHandle(
        base_url=f"http://127.0.0.1:{port}", server=server, thread=thread
    )


@pytest.fixture(scope="session")
def postgres_dsn() -> Iterator[str]:
    """Поднимает postgres testcontainer и возвращает DSN."""
    if not _docker_available():
        pytest.skip("Docker daemon недоступен — нужен для testcontainers postgres")
    with PostgresContainer("postgres:16-alpine", driver=None) as pg:
        host = pg.get_container_host_ip()
        port = pg.get_exposed_port(5432)
        dsn = f"postgresql+asyncpg://test:test@{host}:{port}/test"
        os.environ["_PG_HOST"] = host
        os.environ["_PG_PORT"] = str(port)
        yield dsn


@pytest.fixture(scope="session")
def tasks_svc(postgres_dsn: str) -> Iterator[TasksSvcHandle]:
    """Запускает tasks-svc subprocess'ом в AUTH_MODE=disabled."""
    port = _free_port()
    env = os.environ.copy()
    # alembic запускается subprocess'ом из bootstrap.run_migrations через
    # shutil.which("alembic") — нужно убедиться, что bin venv'а в PATH.
    venv_bin = os.path.dirname(sys.executable)
    env["PATH"] = f"{venv_bin}{os.pathsep}{env.get('PATH', '')}"
    env.update(
        {
            "DATABASE_URL": postgres_dsn,
            "AUTH_MODE": "disabled",
            "SOLO_USER_EMAIL": "solo@local",
            "PYTHONUNBUFFERED": "1",
        }
    )
    # Override hardcoded port via uvicorn CLI.
    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "tasks_service.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--log-level",
            "warning",
        ],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=str(TASKS_SVC_SRC),
    )
    base_url = f"http://127.0.0.1:{port}"
    deadline = time.time() + 30
    last_err: Exception | None = None
    while time.time() < deadline:
        if proc.poll() is not None:
            stderr = proc.stderr.read().decode() if proc.stderr else ""
            raise RuntimeError(f"tasks-svc died:\n{stderr}")
        try:
            r = httpx.get(f"{base_url}/healthz", timeout=1.0)
            if r.status_code == 200:
                break
        except httpx.HTTPError as e:
            last_err = e
        time.sleep(0.3)
    else:
        proc.terminate()
        raise RuntimeError(f"tasks-svc not ready in 30s: {last_err}")

    try:
        yield TasksSvcHandle(base_url=base_url, process=proc)
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


@pytest.fixture(scope="session")
def nginx_stub(tasks_svc: TasksSvcHandle) -> Iterator[NginxStubHandle]:
    """Stdlib HTTP proxy: /api/* → tasks-svc/*. Заменяет nginx в e2e harness'е."""
    stub = _make_nginx_stub(tasks_svc.base_url)
    try:
        yield stub
    finally:
        stub.server.shutdown()
        stub.server.server_close()


@pytest.fixture
def clite_env_offline(tmp_path: Path) -> dict[str, str]:
    """Окружение clite без поднятого tasks-svc — для TC, проверяющих локальное поведение
    (logout/whoami без credentials и т.п.)."""
    home = tmp_path / "home"
    cfg_dir = home / ".config" / "clite"
    cfg_dir.mkdir(parents=True)
    (cfg_dir / "config.yaml").write_text("api_url: http://127.0.0.1:1\n")
    env = os.environ.copy()
    env["HOME"] = str(home)
    return env


@pytest.fixture
def clite_env(nginx_stub: NginxStubHandle, tmp_path: Path) -> dict[str, str]:
    """Окружение для запуска clite в подпроцессе против nginx-stub→tasks-svc.

    Создаёт временный HOME/.config/clite/config.yaml с api_url = nginx-stub
    (clite добавляет /api префикс — стрипается прокси и форвардится в tasks-svc).
    """
    home = tmp_path / "home"
    cfg_dir = home / ".config" / "clite"
    cfg_dir.mkdir(parents=True)
    (cfg_dir / "config.yaml").write_text(f"api_url: {nginx_stub.base_url}\n")
    env = os.environ.copy()
    env["HOME"] = str(home)
    return env


def run_clite(
    args: list[str], env: dict[str, str], stdin: str = ""
) -> subprocess.CompletedProcess[str]:
    """Запускает `python -m clite <args>` и возвращает CompletedProcess.

    Не raises на non-zero exit — тест сам проверяет returncode.
    """
    return subprocess.run(
        [sys.executable, "-m", "clite", *args],
        env=env,
        input=stdin,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )


@pytest.fixture
def clite(clite_env: dict[str, str]):
    """Удобная обёртка: clite(['task', 'list']) → CompletedProcess (с tasks-svc)."""

    def _run(args: list[str], stdin: str = "") -> subprocess.CompletedProcess[str]:
        return run_clite(args, clite_env, stdin)

    return _run


@pytest.fixture
def clite_offline(clite_env_offline: dict[str, str]):
    """Обёртка для тестов без tasks-svc (логаут/whoami без credentials)."""

    def _run(args: list[str], stdin: str = "") -> subprocess.CompletedProcess[str]:
        return run_clite(args, clite_env_offline, stdin)

    return _run


@pytest.fixture
def mk_task(clite, nginx_stub):
    """Создать одну задачу через bulk-create и вернуть её dict (M2.28+M2.29).

    CLI не имеет read-команд для задач (get/list/--filter удалены в M2.29).
    Для теста-удобства после создания дёргаем GET /v1/tasks/{id} напрямую
    через nginx-stub.
    """
    import json as _json
    import urllib.request

    def _make(title: str, **extra: object) -> dict:
        item = {"title": title, **extra}
        r = clite(
            ["create", "tasks", "--bulk", _json.dumps([item]), "--output", "json"]
        )
        assert r.returncode == 0, r.stderr
        result = _json.loads(r.stdout)["results"][0]
        assert result["status"] == "ok", result
        task_id = result["task_id"]
        with urllib.request.urlopen(
            f"{nginx_stub.base_url}/api/v1/tasks/{task_id}"
        ) as resp:
            return _json.loads(resp.read())

    return _make
