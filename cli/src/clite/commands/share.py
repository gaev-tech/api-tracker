"""clite share — управление шарингом задачи."""

from __future__ import annotations

import sys
from typing import Annotated
from uuid import UUID

import typer

from clite.client import APIError, Client
from clite.config import load_config
from clite.output import OutputFormat, emit, parse_fields

FieldsOpt = Annotated[
    str | None,
    typer.Option("--fields", help="Только эти поля через запятую (PRD §7.9)"),
]

app = typer.Typer(no_args_is_help=True, help="Шаринг задачи пользователям и командам")
user_app = typer.Typer(no_args_is_help=True, help="Шаринг с пользователями")
team_app = typer.Typer(no_args_is_help=True, help="Шаринг с командами")
app.add_typer(user_app, name="user")
app.add_typer(team_app, name="team")


def _client() -> Client:
    return Client(load_config())


def _handle(e: APIError) -> None:
    print(e.args[0], file=sys.stderr)
    if e.status_code == 401:
        raise typer.Exit(3)
    if e.status_code == 403:
        raise typer.Exit(4)
    raise typer.Exit(1)


@app.command("list")
def list_shares(
    task_id: Annotated[UUID, typer.Argument()],
    output: Annotated[OutputFormat, typer.Option("--output", "-o")] = "auto",
    fields: FieldsOpt = None,
) -> None:
    with _client() as c:
        try:
            r = c.get(f"/v1/tasks/{task_id}/share")
        except APIError as e:
            _handle(e)
            return
    emit(r, output, fields=parse_fields(fields))


@user_app.command("set")
def user_set(
    task_id: Annotated[UUID, typer.Argument()],
    email: Annotated[str, typer.Option("--email", "-e")],
    perm: Annotated[list[str], typer.Option("--perm", "-p")] = None,  # type: ignore[assignment]
    output: Annotated[OutputFormat, typer.Option("--output", "-o")] = "auto",
) -> None:
    """Установить разрешения пользователя на задачу."""
    with _client() as c:
        try:
            r = c.request(
                "PUT",
                f"/v1/tasks/{task_id}/share/users/{email}",
                json={"perms": list(perm or [])},
            )
        except APIError as e:
            _handle(e)
            return
    emit(r, output)


@user_app.command("remove")
def user_remove(
    task_id: Annotated[UUID, typer.Argument()],
    email: Annotated[
        str, typer.Option("--email", "-e", help="Email или 'me' для self-revoke")
    ],
    output: Annotated[OutputFormat, typer.Option("--output", "-o")] = "auto",
) -> None:
    """Убрать пользователя из shares (PRD §7.8.1 для 'me')."""
    with _client() as c:
        try:
            if email == "me":
                r = c.request("DELETE", f"/v1/tasks/{task_id}/share/users/me")
            else:
                r = c.request(
                    "PUT",
                    f"/v1/tasks/{task_id}/share/users/{email}",
                    json={"perms": []},
                )
        except APIError as e:
            _handle(e)
            return
    emit(r, output)


@team_app.command("set")
def team_set(
    task_id: Annotated[UUID, typer.Argument()],
    team_id: Annotated[UUID, typer.Option("--team")],
    perm: Annotated[list[str], typer.Option("--perm", "-p")] = None,  # type: ignore[assignment]
    output: Annotated[OutputFormat, typer.Option("--output", "-o")] = "auto",
) -> None:
    """Установить разрешения команды на задачу (PRD §6.7.1 — должны быть в команде)."""
    with _client() as c:
        try:
            r = c.request(
                "PUT",
                f"/v1/tasks/{task_id}/share/teams/{team_id}",
                json={"perms": list(perm or [])},
            )
        except APIError as e:
            _handle(e)
            return
    emit(r, output)


@team_app.command("remove")
def team_remove(
    task_id: Annotated[UUID, typer.Argument()],
    team_id: Annotated[UUID, typer.Option("--team")],
    output: Annotated[OutputFormat, typer.Option("--output", "-o")] = "auto",
) -> None:
    with _client() as c:
        try:
            r = c.request(
                "PUT",
                f"/v1/tasks/{task_id}/share/teams/{team_id}",
                json={"perms": []},
            )
        except APIError as e:
            _handle(e)
            return
    emit(r, output)
