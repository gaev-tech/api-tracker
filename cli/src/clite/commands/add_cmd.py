"""`clite add member <key> --email|--team --perm ...` — добавить/изменить
участника команды или проекта. Автодетект team vs project по ключу.
"""

from __future__ import annotations

import sys
from typing import Annotated

import typer

from clite.client import APIError, Client
from clite.commands._shared import OutputOpt, client, emit

app = typer.Typer(no_args_is_help=True, help="Добавить участника")


@app.command("member")
def member(
    container_key: Annotated[
        str,
        typer.Argument(help="SHA1-ключ команды или проекта (или префикс) — автодетект"),
    ],
    email: Annotated[
        str | None,
        typer.Option("--email", "-e", help="Email пользователя"),
    ] = None,
    team_key: Annotated[
        str | None,
        typer.Option("--team", help="SHA1-ключ команды (только для проектов)"),
    ] = None,
    perm: Annotated[
        list[str],
        typer.Option(
            "--perm",
            "-p",
            help="Перм-флаг (повторно); пустой список = удалить участника",
        ),
    ] = None,  # type: ignore[assignment]
    output: OutputOpt = "auto",
) -> None:
    """Добавить/изменить участника команды или проекта.

    Эквивалентен PUT в `/v1/teams/{key}/members/{email}` либо
    `/v1/projects/{key}/members/users/{email}` (или `.../members/teams/{team}`
    для добавления команды в проект).
    """
    if (email is None) == (team_key is None):
        print("provide exactly one of --email or --team", file=sys.stderr)
        raise typer.Exit(2)
    perms = list(perm or [])

    with client() as c:
        if email is not None:
            # Пробуем сначала проект, затем команду.
            ok, result = _try_handle(
                c, f"/v1/projects/{container_key}/members/users/{email}", perms
            )
            if not ok:
                ok, result = _try_handle(
                    c, f"/v1/teams/{container_key}/members/{email}", perms
                )
            if not ok:
                print(
                    f"container not found: {container_key} (не команда и не проект)",
                    file=sys.stderr,
                )
                raise typer.Exit(1)
        else:
            # --team T в --team-projects only.
            assert team_key is not None
            ok, result = _try_handle(
                c,
                f"/v1/projects/{container_key}/members/teams/{team_key}",
                perms,
            )
            if not ok:
                print(
                    f"project not found: {container_key} "
                    "(--team поддерживается только проектами)",
                    file=sys.stderr,
                )
                raise typer.Exit(1)
    emit(result, output)


def _try_handle(c: Client, path: str, perms: list[str]) -> tuple[bool, object]:
    """PUT с обработкой 401/403/прочих; возвращает (ok, result|None) только для 404."""
    try:
        return True, c.request("PUT", path, json={"perms": perms})
    except APIError as e:
        if e.status_code == 404:
            return False, None
        print(e.args[0], file=sys.stderr)
        if e.status_code == 401:
            raise typer.Exit(3) from e
        if e.status_code == 403:
            raise typer.Exit(4) from e
        raise typer.Exit(1) from e
