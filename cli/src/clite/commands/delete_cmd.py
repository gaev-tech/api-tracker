"""`clite delete <noun>` — удаление автоматизаций и секретов (M3+)."""

from __future__ import annotations

import sys
from typing import Annotated

import typer

from clite.client import APIError
from clite.commands._shared import OutputOpt, client, emit, handle_api_error

app = typer.Typer(no_args_is_help=True, help="Удаление сущностей")


@app.command("automation")
def automation(
    key: Annotated[str, typer.Argument(help="SHA1-ключ автоматизации (или префикс)")],
    output: OutputOpt = "auto",
) -> None:
    """Удалить автоматизацию (TC §9.4)."""
    with client() as c:
        try:
            result = c.request("DELETE", f"/v1/automations/{key}")
        except APIError as e:
            handle_api_error(e)
            return
    emit(result, output)


@app.command("secret")
def secret(
    key: Annotated[str, typer.Argument(help="SHA1-ключ секрета (или префикс)")],
    project_key: Annotated[
        str,
        typer.Option("--project", "-p", help="SHA1-ключ проекта (или префикс)"),
    ],
    output: OutputOpt = "auto",
) -> None:
    """Удалить секрет проекта (TC §10.4)."""
    if not project_key:
        print("provide --project <key>", file=sys.stderr)
        raise typer.Exit(2)
    with client() as c:
        try:
            result = c.request("DELETE", f"/v1/projects/{project_key}/secrets/{key}")
        except APIError as e:
            handle_api_error(e)
            return
    emit(result, output)
