"""clite task — массовые мутации: create bulk/batch, update bulk/batch.

Single-task create/update, get и list удалены из CLI (M2.28, M2.29). Чтение
задач выполняется через docs-client / API напрямую.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Annotated

import typer

from clite.client import APIError, Client
from clite.config import load_config
from clite.output import OutputFormat, emit

app = typer.Typer(
    no_args_is_help=True,
    help="Массовые мутации задач: create bulk/batch, update bulk/batch.",
)

create_app = typer.Typer(
    no_args_is_help=True, help="Массовое создание задач (bulk / batch)"
)
app.add_typer(create_app, name="create")

update_app = typer.Typer(
    no_args_is_help=True, help="Массовое обновление задач (bulk / batch)"
)
app.add_typer(update_app, name="update")


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
    """`--set field=value` → dict для patch."""
    patch: dict[str, object] = {}
    for pair in set_pairs:
        if "=" not in pair:
            print(f"--set value must be field=value (got {pair!r})", file=sys.stderr)
            raise typer.Exit(2)
        k, v = pair.split("=", 1)
        if k == "labels":
            patch[k] = v.split(",") if v else []
        else:
            patch[k] = v
    return patch


def _load_items(data: str | None, file: Path | None) -> list[object]:
    """Загрузить JSON-массив либо из inline-аргумента, либо из --file."""
    if data and file is not None:
        print("provide either inline JSON or --file, not both", file=sys.stderr)
        raise typer.Exit(2)
    if not data and file is None:
        print(
            "provide inline JSON array or --file <path>",
            file=sys.stderr,
        )
        raise typer.Exit(2)
    if file is not None:
        if not file.exists():
            print(f"file not found: {file}", file=sys.stderr)
            raise typer.Exit(2)
        raw = file.read_text()
    else:
        assert data is not None
        raw = data
    try:
        items = json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"invalid JSON: {e}", file=sys.stderr)
        raise typer.Exit(2) from e
    if not isinstance(items, list):
        print("JSON root must be array", file=sys.stderr)
        raise typer.Exit(2)
    return items


# === task create bulk | task create batch ===


@create_app.command("bulk")
def create_bulk(
    data: Annotated[
        str | None,
        typer.Argument(help="Inline JSON-массив задач (или используйте --file)"),
    ] = None,
    file: Annotated[
        Path | None,
        typer.Option("--file", "-f", help="Путь к JSON-файлу с массивом задач"),
    ] = None,
    output: Annotated[OutputFormat, typer.Option("--output", "-o")] = "auto",
) -> None:
    """Массовое создание из JSON-массива (partial success, PRD §7.2.1)."""
    items = _load_items(data, file)
    with _client() as c:
        try:
            result = c.post("/v1/tasks/bulk-create", json={"items": items})
        except APIError as e:
            _handle_api_error(e)
            return
    emit(result, output)


@create_app.command("batch")
def create_batch(
    data: Annotated[
        str | None,
        typer.Argument(help="Inline JSON-массив задач (или используйте --file)"),
    ] = None,
    file: Annotated[
        Path | None,
        typer.Option("--file", "-f", help="Путь к JSON-файлу с массивом задач"),
    ] = None,
    output: Annotated[OutputFormat, typer.Option("--output", "-o")] = "auto",
) -> None:
    """Атомарное массовое создание (всё-или-ничего, PRD §7.3.1)."""
    items = _load_items(data, file)
    with _client() as c:
        try:
            result = c.post("/v1/tasks/batch-create", json={"items": items})
        except APIError as e:
            _handle_api_error(e)
            return
    emit(result, output)


# === task update bulk | task update batch ===


@update_app.command("bulk")
def update_bulk(
    filter: Annotated[str, typer.Option("--filter", "-f", help="RSQL")],
    set_pairs: Annotated[
        list[str], typer.Option("--set", "-s", help="field=value")
    ] = None,  # type: ignore[assignment]
    output: Annotated[OutputFormat, typer.Option("--output", "-o")] = "auto",
) -> None:
    """Bulk-обновление по фильтру (partial success, PRD §7.2.1)."""
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


@update_app.command("batch")
def update_batch(
    filter: Annotated[str, typer.Option("--filter", "-f", help="RSQL")],
    set_pairs: Annotated[
        list[str], typer.Option("--set", "-s", help="field=value")
    ] = None,  # type: ignore[assignment]
    output: Annotated[OutputFormat, typer.Option("--output", "-o")] = "auto",
) -> None:
    """Атомарное обновление по фильтру (всё-или-ничего, PRD §7.3.1)."""
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
