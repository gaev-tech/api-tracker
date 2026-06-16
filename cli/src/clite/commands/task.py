"""clite task — CRUD, bulk, batch для задач."""

from __future__ import annotations

import json
import sys
from pathlib import Path
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

app = typer.Typer(no_args_is_help=True, help="Управление задачами")


def _client() -> Client:
    return Client(load_config())


def _handle_api_error(e: APIError) -> None:
    print(e.args[0], file=sys.stderr)
    if e.status_code == 401:
        raise typer.Exit(3)
    if e.status_code == 403:
        raise typer.Exit(4)
    raise typer.Exit(1)


def _parse_set_pairs(set_pairs: list[str]) -> dict[str, object]:
    """`--set field=value` пары → dict для patch."""
    patch: dict[str, object] = {}
    for pair in set_pairs:
        if "=" not in pair:
            print(f"--set value must be field=value (got {pair!r})", file=sys.stderr)
            raise typer.Exit(2)
        k, v = pair.split("=", 1)
        # Простое приведение типов для известных полей.
        if k == "labels":
            patch[k] = v.split(",") if v else []
        elif k in ("title", "description_md", "status"):
            patch[k] = v
        else:
            patch[k] = v
    return patch


@app.command("create")
def create(
    title: Annotated[
        str | None, typer.Option("--title", help="Название задачи")
    ] = None,
    description: Annotated[str, typer.Option("--description", "-d")] = "",
    label: Annotated[
        list[str], typer.Option("--label", help="Метка (повторно)")
    ] = None,  # type: ignore[assignment]
    status: Annotated[
        str, typer.Option("--status", help="open|done|archived")
    ] = "open",
    blocked_by: Annotated[
        list[str], typer.Option("--blocked-by", help="UUID блокирующих задач")
    ] = None,  # type: ignore[assignment]
    stdin_json: Annotated[
        bool, typer.Option("--stdin", "-", help="Читать JSON из stdin")
    ] = False,
    output: Annotated[OutputFormat, typer.Option("--output", "-o")] = "auto",
) -> None:
    """Создать новую задачу. Минимум: --title."""
    if stdin_json:
        try:
            payload = json.loads(sys.stdin.read())
        except json.JSONDecodeError as e:
            print(f"invalid JSON: {e}", file=sys.stderr)
            raise typer.Exit(2) from e
    else:
        if not title:
            print("title required (--title)", file=sys.stderr)
            raise typer.Exit(2)
        payload = {
            "title": title,
            "description_md": description,
            "labels": list(label or []),
            "status": status,
            "blocked_by": list(blocked_by or []),
        }
    with _client() as c:
        try:
            result = c.post("/v1/tasks", json=payload)
        except APIError as e:
            _handle_api_error(e)
            return
    emit(result, output)


@app.command("list")
def list_tasks(
    filter: Annotated[str | None, typer.Option("--filter", "-f", help="RSQL")] = None,
    cursor: Annotated[str | None, typer.Option("--cursor")] = None,
    limit: Annotated[int, typer.Option("--limit", min=1, max=200)] = 50,
    output: Annotated[OutputFormat, typer.Option("--output", "-o")] = "auto",
    fields: FieldsOpt = None,
) -> None:
    """Список задач с RSQL-фильтром и курсорной пагинацией."""
    params: dict[str, object] = {"limit": limit}
    if filter:
        params["filter"] = filter
    if cursor:
        params["cursor"] = cursor
    with _client() as c:
        try:
            result = c.get("/v1/tasks", params=params)
        except APIError as e:
            _handle_api_error(e)
            return
    emit(result, output, fields=parse_fields(fields))


@app.command("get")
def get_task(
    task_id: Annotated[UUID, typer.Argument()],
    output: Annotated[OutputFormat, typer.Option("--output", "-o")] = "auto",
    fields: FieldsOpt = None,
) -> None:
    """Получить задачу по UUID."""
    with _client() as c:
        try:
            result = c.get(f"/v1/tasks/{task_id}")
        except APIError as e:
            _handle_api_error(e)
            return
    emit(result, output, fields=parse_fields(fields))


@app.command("update")
def update_task(
    task_id: Annotated[UUID, typer.Argument()],
    title: Annotated[str | None, typer.Option("--title")] = None,
    description: Annotated[str | None, typer.Option("--description", "-d")] = None,
    status: Annotated[str | None, typer.Option("--status")] = None,
    add_label: Annotated[list[str], typer.Option("--add-label")] = None,  # type: ignore[assignment]
    remove_label: Annotated[list[str], typer.Option("--remove-label")] = None,  # type: ignore[assignment]
    add_blocker: Annotated[list[str], typer.Option("--add-blocker")] = None,  # type: ignore[assignment]
    remove_blocker: Annotated[list[str], typer.Option("--remove-blocker")] = None,  # type: ignore[assignment]
    output: Annotated[OutputFormat, typer.Option("--output", "-o")] = "auto",
) -> None:
    """Обновить поля задачи."""
    patch: dict[str, object] = {}
    if title is not None:
        patch["title"] = title
    if description is not None:
        patch["description_md"] = description
    if status is not None:
        patch["status"] = status
    if add_label:
        patch["add_labels"] = add_label
    if remove_label:
        patch["remove_labels"] = remove_label
    if add_blocker:
        patch["add_blockers"] = add_blocker
    if remove_blocker:
        patch["remove_blockers"] = remove_blocker
    if not patch:
        print("no fields to update", file=sys.stderr)
        raise typer.Exit(2)
    with _client() as c:
        try:
            result = c.patch(f"/v1/tasks/{task_id}", json=patch)
        except APIError as e:
            _handle_api_error(e)
            return
    emit(result, output)


@app.command("bulk-update")
def bulk_update_cmd(
    filter: Annotated[str, typer.Option("--filter", "-f", help="RSQL")],
    set_pairs: Annotated[
        list[str], typer.Option("--set", "-s", help="field=value")
    ] = None,  # type: ignore[assignment]
    output: Annotated[OutputFormat, typer.Option("--output", "-o")] = "auto",
) -> None:
    """Bulk-обновление по фильтру (partial success)."""
    if not set_pairs:
        print("at least one --set field=value required", file=sys.stderr)
        raise typer.Exit(2)
    patch = _parse_set_pairs(set_pairs)
    with _client() as c:
        try:
            result = c.post(
                "/v1/tasks/bulk-update",
                params={"filter": filter},
                json={"patch": patch},
            )
        except APIError as e:
            _handle_api_error(e)
            return
    emit(result, output)


@app.command("batch-update")
def batch_update_cmd(
    filter: Annotated[str, typer.Option("--filter", "-f", help="RSQL")],
    set_pairs: Annotated[
        list[str], typer.Option("--set", "-s", help="field=value")
    ] = None,  # type: ignore[assignment]
    output: Annotated[OutputFormat, typer.Option("--output", "-o")] = "auto",
) -> None:
    """Атомарное обновление по фильтру (всё-или-ничего)."""
    if not set_pairs:
        print("at least one --set field=value required", file=sys.stderr)
        raise typer.Exit(2)
    patch = _parse_set_pairs(set_pairs)
    with _client() as c:
        try:
            result = c.post(
                "/v1/tasks/batch-update",
                params={"filter": filter},
                json={"patch": patch},
            )
        except APIError as e:
            _handle_api_error(e)
            return
    emit(result, output)


@app.command("bulk-create")
def bulk_create_cmd(
    from_file: Annotated[
        Path, typer.Option("--from", help="JSON-файл со списком задач")
    ],
    output: Annotated[OutputFormat, typer.Option("--output", "-o")] = "auto",
) -> None:
    """Массовое создание задач из JSON-массива (partial success)."""
    if not from_file.exists():
        print(f"file not found: {from_file}", file=sys.stderr)
        raise typer.Exit(2)
    try:
        items = json.loads(from_file.read_text())
    except json.JSONDecodeError as e:
        print(f"invalid JSON: {e}", file=sys.stderr)
        raise typer.Exit(2) from e
    if not isinstance(items, list):
        print("JSON root must be array", file=sys.stderr)
        raise typer.Exit(2)
    with _client() as c:
        try:
            result = c.post("/v1/tasks/bulk-create", json={"items": items})
        except APIError as e:
            _handle_api_error(e)
            return
    emit(result, output)


@app.command("batch-create")
def batch_create_cmd(
    from_file: Annotated[
        Path, typer.Option("--from", help="JSON-файл со списком задач")
    ],
    output: Annotated[OutputFormat, typer.Option("--output", "-o")] = "auto",
) -> None:
    """Атомарное массовое создание задач."""
    if not from_file.exists():
        print(f"file not found: {from_file}", file=sys.stderr)
        raise typer.Exit(2)
    try:
        items = json.loads(from_file.read_text())
    except json.JSONDecodeError as e:
        print(f"invalid JSON: {e}", file=sys.stderr)
        raise typer.Exit(2) from e
    with _client() as c:
        try:
            result = c.post("/v1/tasks/batch-create", json={"items": items})
        except APIError as e:
            _handle_api_error(e)
            return
    emit(result, output)
