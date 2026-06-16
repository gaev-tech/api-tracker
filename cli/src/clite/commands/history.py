"""clite history — флаговая форма: --task <key> | --user <email>."""

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

app = typer.Typer(
    invoke_without_command=True,
    help="История изменений (--task <key> | --user <email|me>)",
)


def _handle(e: APIError) -> None:
    print(e.args[0], file=sys.stderr)
    if e.status_code == 401:
        raise typer.Exit(3) from e
    if e.status_code == 403:
        raise typer.Exit(4) from e
    raise typer.Exit(1) from e


@app.callback(invoke_without_command=True)
def history(
    ctx: typer.Context,
    task: Annotated[
        str | None,
        typer.Option("--task", help="SHA1-ключ задачи (или префикс)"),
    ] = None,
    user: Annotated[
        str | None,
        typer.Option("--user", help="Email пользователя или 'me'"),
    ] = None,
    cursor: Annotated[str | None, typer.Option("--cursor")] = None,
    output: Annotated[OutputFormat, typer.Option("--output", "-o")] = "auto",
    fields: FieldsOpt = None,
) -> None:
    """Ровно один из --task или --user."""
    if ctx.invoked_subcommand is not None:
        return
    if (task is None) == (user is None):
        print("provide exactly one of --task or --user", file=sys.stderr)
        raise typer.Exit(2)
    params: dict[str, object] = {}
    if task is not None:
        params["task_id"] = task
    else:
        params["user_id"] = user
    if cursor:
        params["cursor"] = cursor
    with Client(load_config()) as c:
        try:
            result = c.get("/v1/history", params=params)
        except APIError as e:
            _handle(e)
            return
    emit(result, output, fields=parse_fields(fields))
