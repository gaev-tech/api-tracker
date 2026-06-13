"""clite login / logout / whoami (terminal-only auth flow)."""

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


@app.command("login")
def login(
    email: Annotated[
        str | None,
        typer.Option("--email", "-e", help="Если не задан — спросит интерактивно"),
    ] = None,
    code: Annotated[
        str | None,
        typer.Option(
            "--code",
            "-c",
            help="Magic-code (для скриптов и e2e); пропускает интерактивный prompt",
        ),
    ] = None,
) -> None:
    """Magic-code login через email. Открытая регистрация."""
    if email is None:
        email = typer.prompt("Email")
    email = email.strip().lower()

    if code is None:
        print(f"Отправляю magic-code на {email}...", file=sys.stderr)
        try:
            r = httpx.post(
                f"{_auth_base()}/magic/start",
                json={"email": email, "intent": "cli"},
                timeout=30,
            )
        except httpx.HTTPError as e:
            print(f"connection failed: {e}", file=sys.stderr)
            raise typer.Exit(1) from e

        if r.status_code >= 400:
            print(f"magic/start failed: {r.status_code} {r.text}", file=sys.stderr)
            raise typer.Exit(1)

        print(f"✉ Код отправлен на {email}.", file=sys.stderr)
        code = typer.prompt("Code").strip()
    else:
        code = code.strip()

    try:
        r = httpx.post(
            f"{_auth_base()}/magic/verify",
            json={"token": code, "intent": "cli"},
            timeout=30,
        )
    except httpx.HTTPError as e:
        print(f"connection failed: {e}", file=sys.stderr)
        raise typer.Exit(1) from e

    if r.status_code >= 400:
        try:
            detail = r.json().get("detail", r.text)
        except Exception:
            detail = r.text
        print(f"login failed: {detail}", file=sys.stderr)
        raise typer.Exit(1)

    body = r.json()
    creds = Credentials(
        access_token=body["access_token"],
        refresh_token=body["refresh_token"],
        user_email=body["user_email"],
        expires_at=int(time.time()) + int(body["expires_in"]),
    )
    save_credentials(creds)
    print(f"✓ Logged in as {creds.user_email}", file=sys.stderr)


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
        status = "valid" if remaining > 0 else "expired"
        print(f"{email}  (access token {status}, {max(remaining, 0)}s remaining)")
    else:
        print(email)
