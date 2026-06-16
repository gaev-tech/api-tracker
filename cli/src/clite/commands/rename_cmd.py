"""`clite rename <noun>` — переименование команды/проекта."""

from __future__ import annotations

from typing import Annotated

import typer

from clite.client import APIError
from clite.commands._shared import OutputOpt, client, emit, handle_api_error

app = typer.Typer(no_args_is_help=True, help="Переименование сущностей")


@app.command("team")
def team(
    key: Annotated[str, typer.Argument(help="SHA1-ключ команды (или префикс)")],
    new_name: Annotated[str, typer.Option("--to", help="Новое имя")],
    output: OutputOpt = "auto",
) -> None:
    """Переименовать команду (требуется perm `edit_team_name`)."""
    with client() as c:
        try:
            result = c.patch(f"/v1/teams/{key}", json={"name": new_name})
        except APIError as e:
            handle_api_error(e)
            return
    emit(result, output)


@app.command("project")
def project(
    key: Annotated[str, typer.Argument(help="SHA1-ключ проекта (или префикс)")],
    new_name: Annotated[str, typer.Option("--to", help="Новое имя")],
    output: OutputOpt = "auto",
) -> None:
    """Переименовать проект (требуется perm `edit_project_name`)."""
    with client() as c:
        try:
            result = c.patch(f"/v1/projects/{key}", json={"name": new_name})
        except APIError as e:
            handle_api_error(e)
            return
    emit(result, output)
