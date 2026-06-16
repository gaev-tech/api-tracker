"""clite history — история событий."""

import sys
from typing import Annotated

import typer

from clite.client import APIError, Client
from clite.config import load_config
from clite.output import OutputFormat, emit, parse_fields

FieldsOpt = Annotated[
    str | None,
    typer.Option("--fields", help="Только эти поля через запятую (PRD §7.9)"),
]

app = typer.Typer(no_args_is_help=True, help="История изменений")


def _handle(e: APIError) -> None:
    print(e.args[0], file=sys.stderr)
    if e.status_code == 401:
        raise typer.Exit(3) from e
    if e.status_code == 403:
        raise typer.Exit(4) from e
    raise typer.Exit(1) from e


@app.command("task")
def task_history(
    task_id: Annotated[str, typer.Argument()],
    cursor: Annotated[str | None, typer.Option("--cursor")] = None,
    output: Annotated[OutputFormat, typer.Option("--output", "-o")] = "auto",
    fields: FieldsOpt = None,
) -> None:
    """История событий по задаче."""
    params: dict[str, object] = {"task_id": str(task_id)}
    if cursor:
        params["cursor"] = cursor
    with Client(load_config()) as c:
        try:
            result = c.get("/v1/history", params=params)
        except APIError as e:
            _handle(e)
            return
    emit(result, output, fields=parse_fields(fields))


@app.command("user")
def user_history(
    email: Annotated[
        str,
        typer.Argument(help="Email пользователя или 'me' для собственной истории"),
    ],
    cursor: Annotated[str | None, typer.Option("--cursor")] = None,
    output: Annotated[OutputFormat, typer.Option("--output", "-o")] = "auto",
    fields: FieldsOpt = None,
) -> None:
    """История действий пользователя с проверкой видимости (ARCH §10.2.2)."""
    params: dict[str, object] = {"user_id": email}
    if cursor:
        params["cursor"] = cursor
    with Client(load_config()) as c:
        try:
            result = c.get("/v1/history", params=params)
        except APIError as e:
            _handle(e)
            return
    emit(result, output, fields=parse_fields(fields))
