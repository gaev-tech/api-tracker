"""clite team — CRUD команд."""

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

app = typer.Typer(no_args_is_help=True, help="Управление командами")
member_app = typer.Typer(no_args_is_help=True, help="Управление участниками команды")
app.add_typer(member_app, name="member")


def _client() -> Client:
    return Client(load_config())


def _handle_api_error(e: APIError) -> None:
    print(e.args[0], file=sys.stderr)
    if e.status_code == 401:
        raise typer.Exit(3)
    if e.status_code == 403:
        raise typer.Exit(4)
    raise typer.Exit(1)


@app.command("create")
def create(
    name: Annotated[str, typer.Option("--name", "-n", help="Имя команды")],
    output: Annotated[OutputFormat, typer.Option("--output", "-o")] = "auto",
) -> None:
    with _client() as c:
        try:
            result = c.post("/v1/teams", json={"name": name})
        except APIError as e:
            _handle_api_error(e)
            return
    emit(result, output)


@app.command("list")
def list_teams(
    output: Annotated[OutputFormat, typer.Option("--output", "-o")] = "auto",
    fields: FieldsOpt = None,
) -> None:
    with _client() as c:
        try:
            result = c.get("/v1/teams")
        except APIError as e:
            _handle_api_error(e)
            return
    emit(result, output, fields=parse_fields(fields))


@app.command("get")
def get_team(
    team_id: Annotated[UUID, typer.Argument()],
    output: Annotated[OutputFormat, typer.Option("--output", "-o")] = "auto",
    fields: FieldsOpt = None,
) -> None:
    with _client() as c:
        try:
            result = c.get(f"/v1/teams/{team_id}")
        except APIError as e:
            _handle_api_error(e)
            return
    emit(result, output, fields=parse_fields(fields))


@app.command("update")
def update_team(
    team_id: Annotated[UUID, typer.Argument()],
    name: Annotated[str, typer.Option("--name", "-n")],
    output: Annotated[OutputFormat, typer.Option("--output", "-o")] = "auto",
) -> None:
    """Изменить имя команды."""
    with _client() as c:
        try:
            result = c.patch(f"/v1/teams/{team_id}", json={"name": name})
        except APIError as e:
            _handle_api_error(e)
            return
    emit(result, output)


@app.command("leave")
def leave(
    team_id: Annotated[UUID, typer.Argument()],
    output: Annotated[OutputFormat, typer.Option("--output", "-o")] = "auto",
) -> None:
    """Выйти из команды (self-revoke, PRD §7.8.2)."""
    with _client() as c:
        try:
            result = c.request("DELETE", f"/v1/teams/{team_id}/members/me")
        except APIError as e:
            _handle_api_error(e)
            return
    emit(result, output)


@member_app.command("set")
def member_set(
    team_id: Annotated[UUID, typer.Argument()],
    email: Annotated[str, typer.Option("--email", "-e")],
    perm: Annotated[
        list[str], typer.Option("--perm", "-p", help="Каждый --perm раз = один флаг")
    ] = None,  # type: ignore[assignment]
    output: Annotated[OutputFormat, typer.Option("--output", "-o")] = "auto",
) -> None:
    """Установить разрешения участника. Пустой список = удаление."""
    perms = list(perm or [])
    with _client() as c:
        try:
            result = c.request(
                "PUT",
                f"/v1/teams/{team_id}/members/{email}",
                json={"perms": perms},
            )
        except APIError as e:
            _handle_api_error(e)
            return
    emit(result, output)


@member_app.command("remove")
def member_remove(
    team_id: Annotated[UUID, typer.Argument()],
    email: Annotated[str, typer.Option("--email", "-e")],
    output: Annotated[OutputFormat, typer.Option("--output", "-o")] = "auto",
) -> None:
    """Убрать участника команды (эквивалент `member set --perm <none>`)."""
    with _client() as c:
        try:
            result = c.request(
                "PUT",
                f"/v1/teams/{team_id}/members/{email}",
                json={"perms": []},
            )
        except APIError as e:
            _handle_api_error(e)
            return
    emit(result, output)
