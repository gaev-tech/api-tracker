"""clite login / logout / whoami (magic-link click flow, ARCH §4.2)."""

from __future__ import annotations

import sys
import time
from typing import Annotated

import httpx
import typer

from clite.auth import (
    Credentials,
    decode_jwt_claims,
    delete_credentials,
    load_credentials,
    save_credentials,
)
from clite.config import load_config

app = typer.Typer(no_args_is_help=False, help="Аутентификация")


def _auth_base() -> str:
    cfg = load_config()
    return f"{cfg.base_url}/api/auth"


# Backoff между poll-итерациями (ARCH §4.3.1.4).
_POLL_INTERVALS_SECONDS: tuple[float, ...] = (1, 1, 2, 2, 5)
_POLL_STEADY_SECONDS: float = 5.0


def _poll_iteration_delay(iteration: int) -> float:
    if iteration < len(_POLL_INTERVALS_SECONDS):
        return _POLL_INTERVALS_SECONDS[iteration]
    return _POLL_STEADY_SECONDS


@app.command("login")
def login(
    email: Annotated[
        str | None,
        typer.Option("--email", "-e", help="Если не задан — спросит интерактивно"),
    ] = None,
    no_wait: Annotated[
        bool,
        typer.Option(
            "--no-wait",
            help="Не ждать клик: распечатать login_session_id и выйти "
            "(для скриптов/e2e, TC §5.1.3)",
        ),
    ] = False,
) -> None:
    """Magic-link login. Пользователь кликает по ссылке из почты — CLI ждёт.

    ARCH §4.2-§4.3, PRD §10.5.
    """
    if email is None:
        email = typer.prompt("Email")
    email = email.strip().lower()

    print(f"Запрашиваю magic-link для {email}…", file=sys.stderr)
    try:
        r = httpx.post(
            f"{_auth_base()}/magic/start",
            json={"email": email},
            timeout=30,
        )
    except httpx.HTTPError as e:
        print(f"connection failed: {e}", file=sys.stderr)
        raise typer.Exit(1) from e

    if r.status_code >= 400:
        detail = _extract_detail(r)
        if detail == "email_delivery_not_configured":
            print(
                "email delivery not configured on server (ARCH §4.2.1.1)",
                file=sys.stderr,
            )
        else:
            print(f"magic/start failed: {detail}", file=sys.stderr)
        raise typer.Exit(1)

    body = r.json()
    login_session_id = body["login_session_id"]
    expires_in = int(body["expires_in"])

    if no_wait:
        print(login_session_id)
        return

    print(
        f"✉ Link sent to {email}. Click it from your inbox. Waiting…",
        file=sys.stderr,
    )

    creds = _poll_until_confirmed(
        login_session_id=login_session_id, expires_in=expires_in
    )
    save_credentials(creds)
    print("success, press enter to continue")
    try:
        input()
    except (EOFError, KeyboardInterrupt):
        pass


def _poll_until_confirmed(*, login_session_id: str, expires_in: int) -> Credentials:
    url = f"{_auth_base()}/magic/poll/{login_session_id}"
    deadline = time.monotonic() + expires_in
    iteration = 0
    while True:
        delay = _poll_iteration_delay(iteration)
        # Не уйти за deadline впустую — приблизим delay к остатку.
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            print("magic link expired, run clite login again", file=sys.stderr)
            raise typer.Exit(1)
        time.sleep(min(delay, remaining))
        iteration += 1
        try:
            resp = httpx.get(url, timeout=30)
        except httpx.HTTPError as e:
            print(f"connection failed: {e}", file=sys.stderr)
            raise typer.Exit(1) from e
        if resp.status_code == 202:
            continue
        if resp.status_code == 200:
            body = resp.json()
            return Credentials(
                access_token=body["access_token"],
                refresh_token=body["refresh_token"],
                user_email=body["user_email"],
                expires_at=int(time.time()) + int(body["expires_in"]),
            )
        if resp.status_code == 410:
            print("magic link expired, run clite login again", file=sys.stderr)
            raise typer.Exit(1)
        print(
            f"login failed: {resp.status_code} {_extract_detail(resp)}",
            file=sys.stderr,
        )
        raise typer.Exit(1)


def _extract_detail(r: httpx.Response) -> str:
    try:
        body = r.json()
        if isinstance(body, dict) and "detail" in body:
            return str(body["detail"])
    except ValueError:
        pass
    return r.text


@app.command("logout")
def logout() -> None:
    """Удалить локальные credentials. Серверная сессия остаётся (revoke — Post-MVP)."""
    if delete_credentials():
        print("✓ Logged out (local credentials удалены).", file=sys.stderr)
    else:
        print("Не были залогинены.", file=sys.stderr)


@app.command("whoami")
def whoami() -> None:
    """Показать текущего пользователя (по локальным credentials)."""
    creds = load_credentials()
    if creds is None:
        print("Не залогинены. Используйте `clite login`.", file=sys.stderr)
        raise typer.Exit(3)

    claims = decode_jwt_claims(creds.access_token)
    email = claims.get("email") or creds.user_email
    exp = claims.get("exp")
    if isinstance(exp, int):
        remaining = exp - int(time.time())
        status_str = "valid" if remaining > 0 else "expired"
        print(f"{email}  (access token {status_str}, {max(remaining, 0)}s remaining)")
    else:
        print(email)
