"""clite project — CRUD проектов."""

from __future__ import annotations

import sys
from typing import Annotated
from uuid import UUID

import typer

from clite.client import APIError, Client
from clite.config import load_config
from clite.output import OutputFormat, emit

app = typer.Typer(no_args_is_help=True, help="Управление проектами")
member_app = typer.Typer(no_args_is_help=True, help="Управление участниками проекта")
task_app = typer.Typer(no_args_is_help=True, help="Управление задачами в проекте")
app.add_typer(member_app, name="member")
app.add_typer(task_app, name="task")


def _client() -> Client:
    return Client(load_config())


def _handle(e: APIError) -> None:
    print(e.args[0], file=sys.stderr)
    if e.status_code == 401:
        raise typer.Exit(3)
    if e.status_code == 403:
        raise typer.Exit(4)
    raise typer.Exit(1)


@app.command("create")
def create(
    name: Annotated[str, typer.Option("--name", "-n")],
    output: Annotated[OutputFormat, typer.Option("--output", "-o")] = "auto",
) -> None:
    with _client() as c:
        try:
            r = c.post("/v1/projects", json={"name": name})
        except APIError as e:
            _handle(e)
            return
    emit(r, output)


@app.command("list")
def list_projects(
    output: Annotated[OutputFormat, typer.Option("--output", "-o")] = "auto",
) -> None:
    """Список проектов текущего пользователя."""
    with _client() as c:
        try:
            r = c.get("/v1/projects")
        except APIError as e:
            _handle(e)
            return
    emit(r, output)


@app.command("get")
def get_project(
    project_id: Annotated[UUID, typer.Argument()],
    output: Annotated[OutputFormat, typer.Option("--output", "-o")] = "auto",
) -> None:
    with _client() as c:
        try:
            r = c.get(f"/v1/projects/{project_id}")
        except APIError as e:
            _handle(e)
            return
    emit(r, output)


@app.command("update")
def update_project(
    project_id: Annotated[UUID, typer.Argument()],
    name: Annotated[str, typer.Option("--name", "-n")],
    output: Annotated[OutputFormat, typer.Option("--output", "-o")] = "auto",
) -> None:
    with _client() as c:
        try:
            r = c.patch(f"/v1/projects/{project_id}", json={"name": name})
        except APIError as e:
            _handle(e)
            return
    emit(r, output)


@app.command("leave")
def leave(
    project_id: Annotated[UUID, typer.Argument()],
    output: Annotated[OutputFormat, typer.Option("--output", "-o")] = "auto",
) -> None:
    """Self-revoke из проекта (PRD §7.8.3)."""
    with _client() as c:
        try:
            r = c.request("DELETE", f"/v1/projects/{project_id}/members/me")
        except APIError as e:
            _handle(e)
            return
    emit(r, output)


# --- members ---


@member_app.command("set")
def member_set(
    project_id: Annotated[UUID, typer.Argument()],
    email: Annotated[str, typer.Option("--email", "-e")],
    perm: Annotated[
        list[str],
        typer.Option("--perm", "-p", help="project- или task-уровневый флаг"),
    ] = None,  # type: ignore[assignment]
    output: Annotated[OutputFormat, typer.Option("--output", "-o")] = "auto",
) -> None:
    """Установить разрешения пользователя в проекте."""
    perms = list(perm or [])
    with _client() as c:
        try:
            r = c.request(
                "PUT",
                f"/v1/projects/{project_id}/members/users/{email}",
                json={"perms": perms},
            )
        except APIError as e:
            _handle(e)
            return
    emit(r, output)


@member_app.command("remove")
def member_remove(
    project_id: Annotated[UUID, typer.Argument()],
    email: Annotated[str, typer.Option("--email", "-e")],
    output: Annotated[OutputFormat, typer.Option("--output", "-o")] = "auto",
) -> None:
    with _client() as c:
        try:
            r = c.request(
                "PUT",
                f"/v1/projects/{project_id}/members/users/{email}",
                json={"perms": []},
            )
        except APIError as e:
            _handle(e)
            return
    emit(r, output)


@member_app.command("team-set")
def member_team_set(
    project_id: Annotated[UUID, typer.Argument()],
    team_id: Annotated[UUID, typer.Option("--team")],
    perm: Annotated[list[str], typer.Option("--perm", "-p")] = None,  # type: ignore[assignment]
    output: Annotated[OutputFormat, typer.Option("--output", "-o")] = "auto",
) -> None:
    """Установить разрешения команды в проекте."""
    perms = list(perm or [])
    with _client() as c:
        try:
            r = c.request(
                "PUT",
                f"/v1/projects/{project_id}/members/teams/{team_id}",
                json={"perms": perms},
            )
        except APIError as e:
            _handle(e)
            return
    emit(r, output)


@member_app.command("team-remove")
def member_team_remove(
    project_id: Annotated[UUID, typer.Argument()],
    team_id: Annotated[UUID, typer.Option("--team")],
    output: Annotated[OutputFormat, typer.Option("--output", "-o")] = "auto",
) -> None:
    with _client() as c:
        try:
            r = c.request(
                "PUT",
                f"/v1/projects/{project_id}/members/teams/{team_id}",
                json={"perms": []},
            )
        except APIError as e:
            _handle(e)
            return
    emit(r, output)


# --- project tasks ---


@task_app.command("add")
def task_add(
    project_id: Annotated[UUID, typer.Argument()],
    task_id: Annotated[UUID, typer.Option("--task")],
) -> None:
    """Добавить задачу в проект."""
    with _client() as c:
        try:
            c.post(f"/v1/projects/{project_id}/tasks/{task_id}")
        except APIError as e:
            _handle(e)
            return
    print("✓ added", file=sys.stderr)


@task_app.command("remove")
def task_remove(
    project_id: Annotated[UUID, typer.Argument()],
    task_id: Annotated[UUID, typer.Option("--task")],
) -> None:
    """Убрать задачу из проекта."""
    with _client() as c:
        try:
            c.request("DELETE", f"/v1/projects/{project_id}/tasks/{task_id}")
        except APIError as e:
            _handle(e)
            return
    print("✓ removed", file=sys.stderr)
