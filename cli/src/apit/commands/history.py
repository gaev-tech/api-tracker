"""apit history — история событий."""

import sys
from typing import Annotated
from uuid import UUID

import typer

from apit.client import APIError, Client
from apit.config import load_config
from apit.output import OutputFormat, emit

app = typer.Typer(no_args_is_help=True, help="История изменений")


@app.command("task")
def task_history(
    task_id: Annotated[UUID, typer.Argument()],
    cursor: Annotated[str | None, typer.Option("--cursor")] = None,
    output: Annotated[OutputFormat, typer.Option("--output", "-o")] = "auto",
) -> None:
    """История событий по задаче."""
    params: dict[str, object] = {"task_id": str(task_id)}
    if cursor:
        params["cursor"] = cursor
    with Client(load_config()) as c:
        try:
            result = c.get("/v1/history", params=params)
        except APIError as e:
            print(e.args[0], file=sys.stderr)
            if e.status_code == 401:
                raise typer.Exit(3) from e
            if e.status_code == 403:
                raise typer.Exit(4) from e
            raise typer.Exit(1) from e
    emit(result, output)
