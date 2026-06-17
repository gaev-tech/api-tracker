"""`clite get <noun>` — чтение задач, команд, проектов, лога."""

from __future__ import annotations

from typing import Annotated

import typer

from clite.client import APIError
from clite.commands._shared import (
    FieldsOpt,
    OutputOpt,
    client,
    emit,
    handle_api_error,
    parse_fields,
)

app = typer.Typer(no_args_is_help=True, help="Чтение данных")

_DEFAULT_TASK_FIELDS = ["id", "title", "description_md"]
_DEFAULT_TEAM_FIELDS = ["id", "name"]
_DEFAULT_PROJECT_FIELDS = ["id", "name"]
_DEFAULT_AUTOMATION_FIELDS = ["id", "name", "trigger_type", "action_type"]
_DEFAULT_SECRET_FIELDS = ["id", "name", "created_at"]


@app.command("tasks")
def tasks(
    filter: Annotated[str | None, typer.Option("--filter", "-f", help="RSQL")] = None,
    cursor: Annotated[str | None, typer.Option("--cursor")] = None,
    limit: Annotated[int, typer.Option("--limit", min=1, max=200)] = 50,
    output: OutputOpt = "auto",
    fields: FieldsOpt = None,
) -> None:
    """Список задач с RSQL-фильтром (PRD §7.1)."""
    params: dict[str, object] = {"limit": limit}
    if filter:
        params["filter"] = filter
    if cursor:
        params["cursor"] = cursor
    with client() as c:
        try:
            result = c.get("/v1/tasks", params=params)
        except APIError as e:
            handle_api_error(e)
            return
    emit(result, output, fields=parse_fields(fields) or _DEFAULT_TASK_FIELDS)


@app.command("teams")
def teams(
    output: OutputOpt = "auto",
    fields: FieldsOpt = None,
) -> None:
    """Список моих команд."""
    with client() as c:
        try:
            result = c.get("/v1/teams")
        except APIError as e:
            handle_api_error(e)
            return
    emit(result, output, fields=parse_fields(fields) or _DEFAULT_TEAM_FIELDS)


@app.command("team")
def team(
    key: Annotated[str, typer.Argument(help="SHA1-ключ команды (или префикс)")],
    output: OutputOpt = "auto",
    fields: FieldsOpt = None,
) -> None:
    """Одна команда: имя + участники + перм-флаги."""
    with client() as c:
        try:
            result = c.get(f"/v1/teams/{key}")
        except APIError as e:
            handle_api_error(e)
            return
    emit(result, output, fields=parse_fields(fields) or _DEFAULT_TEAM_FIELDS)


@app.command("projects")
def projects(
    output: OutputOpt = "auto",
    fields: FieldsOpt = None,
) -> None:
    """Список моих проектов."""
    with client() as c:
        try:
            result = c.get("/v1/projects")
        except APIError as e:
            handle_api_error(e)
            return
    emit(result, output, fields=parse_fields(fields) or _DEFAULT_PROJECT_FIELDS)


@app.command("project")
def project(
    key: Annotated[str, typer.Argument(help="SHA1-ключ проекта (или префикс)")],
    output: OutputOpt = "auto",
    fields: FieldsOpt = None,
) -> None:
    """Один проект: имя + участники + task_ids."""
    with client() as c:
        try:
            result = c.get(f"/v1/projects/{key}")
        except APIError as e:
            handle_api_error(e)
            return
    emit(result, output, fields=parse_fields(fields) or _DEFAULT_PROJECT_FIELDS)


@app.command("automations")
def automations(
    project_key: Annotated[
        str,
        typer.Option("--project", "-p", help="SHA1-ключ проекта (или префикс)"),
    ],
    output: OutputOpt = "auto",
    fields: FieldsOpt = None,
) -> None:
    """Список автоматизаций проекта (PRD §8)."""
    with client() as c:
        try:
            result = c.get("/v1/automations", params={"project_id": project_key})
        except APIError as e:
            handle_api_error(e)
            return
    emit(result, output, fields=parse_fields(fields) or _DEFAULT_AUTOMATION_FIELDS)


@app.command("automation")
def automation(
    key: Annotated[str, typer.Argument(help="SHA1-ключ автоматизации (или префикс)")],
    output: OutputOpt = "auto",
    fields: FieldsOpt = None,
) -> None:
    """Одна автоматизация: trigger_config + action_config."""
    with client() as c:
        try:
            result = c.get(f"/v1/automations/{key}")
        except APIError as e:
            handle_api_error(e)
            return
    emit(result, output, fields=parse_fields(fields) or _DEFAULT_AUTOMATION_FIELDS)


@app.command("secrets")
def secrets(
    project_key: Annotated[
        str,
        typer.Option("--project", "-p", help="SHA1-ключ проекта (или префикс)"),
    ],
    output: OutputOpt = "auto",
    fields: FieldsOpt = None,
) -> None:
    """Список секретов проекта (имена БЕЗ значений, ARCH §13.2)."""
    with client() as c:
        try:
            result = c.get(f"/v1/projects/{project_key}/secrets")
        except APIError as e:
            handle_api_error(e)
            return
    emit(result, output, fields=parse_fields(fields) or _DEFAULT_SECRET_FIELDS)


@app.command("log")
def log(
    task: Annotated[
        str | None,
        typer.Option("--task", help="SHA1-ключ задачи (или префикс)"),
    ] = None,
    user: Annotated[
        str | None,
        typer.Option("--user", help="Email пользователя или 'me'"),
    ] = None,
    cursor: Annotated[str | None, typer.Option("--cursor")] = None,
    output: OutputOpt = "auto",
    fields: FieldsOpt = None,
) -> None:
    """История событий: ровно один из --task или --user."""
    if (task is None) == (user is None):
        print("provide exactly one of --task or --user", flush=True)
        raise typer.Exit(2)
    params: dict[str, object] = {}
    if task is not None:
        params["task_id"] = task
    else:
        params["user_id"] = user
    if cursor:
        params["cursor"] = cursor
    with client() as c:
        try:
            result = c.get("/v1/history", params=params)
        except APIError as e:
            handle_api_error(e)
            return
    emit(result, output, fields=parse_fields(fields))
