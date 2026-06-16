"""`clite create <noun>` — создание задач (bulk/batch), команды, проекта."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from clite.client import APIError
from clite.commands._shared import (
    OutputOpt,
    client,
    emit,
    handle_api_error,
    load_items,
    require_one_semantic,
)

app = typer.Typer(no_args_is_help=True, help="Создание сущностей")


@app.command("tasks")
def tasks(
    data: Annotated[
        str | None,
        typer.Argument(help="Inline JSON-массив задач (или используйте --file)"),
    ] = None,
    file: Annotated[
        Path | None,
        typer.Option("--file", help="Путь к JSON или CSV (определяется по расширению)"),
    ] = None,
    bulk: Annotated[
        bool, typer.Option("--bulk", help="Partial success (PRD §7.2.1)")
    ] = False,
    batch: Annotated[
        bool, typer.Option("--batch", help="Атомарно (PRD §7.3.1)")
    ] = False,
    output: OutputOpt = "auto",
) -> None:
    """Массовое создание задач. Требуется ровно один из --bulk или --batch."""
    semantic = require_one_semantic(bulk, batch)
    items = load_items(data, file)
    endpoint = f"/v1/tasks/{semantic}-create"
    with client() as c:
        try:
            result = c.post(endpoint, json={"items": items})
        except APIError as e:
            handle_api_error(e)
            return
    emit(result, output)


@app.command("team")
def team(
    name: Annotated[str, typer.Option("--name", "-n", help="Имя команды")],
    output: OutputOpt = "auto",
) -> None:
    """Создать команду; создатель — единственный участник со всеми правами."""
    with client() as c:
        try:
            result = c.post("/v1/teams", json={"name": name})
        except APIError as e:
            handle_api_error(e)
            return
    emit(result, output)


@app.command("project")
def project(
    name: Annotated[str, typer.Option("--name", "-n", help="Имя проекта")],
    output: OutputOpt = "auto",
) -> None:
    """Создать проект; создатель получает все project + task perms."""
    with client() as c:
        try:
            result = c.post("/v1/projects", json={"name": name})
        except APIError as e:
            handle_api_error(e)
            return
    emit(result, output)
