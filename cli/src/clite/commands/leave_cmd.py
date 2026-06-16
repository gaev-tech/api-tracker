"""`clite leave <noun>` — self-revoke из команды или проекта."""

from __future__ import annotations

from typing import Annotated

import typer

from clite.client import APIError
from clite.commands._shared import OutputOpt, client, emit, handle_api_error

app = typer.Typer(no_args_is_help=True, help="Self-revoke (PRD §7.8)")


@app.command("team")
def team(
    key: Annotated[str, typer.Argument(help="SHA1-ключ команды (или префикс)")],
    output: OutputOpt = "auto",
) -> None:
    """Выйти из команды; если был последним — команда удаляется (PRD §6.1.6)."""
    with client() as c:
        try:
            result = c.request("DELETE", f"/v1/teams/{key}/members/me")
        except APIError as e:
            handle_api_error(e)
            return
    emit(result, output)


@app.command("project")
def project(
    key: Annotated[str, typer.Argument(help="SHA1-ключ проекта (или префикс)")],
    output: OutputOpt = "auto",
) -> None:
    """Выйти из проекта (PRD §7.8.3)."""
    with client() as c:
        try:
            result = c.request("DELETE", f"/v1/projects/{key}/members/me")
        except APIError as e:
            handle_api_error(e)
            return
    emit(result, output)
