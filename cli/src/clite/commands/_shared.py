"""Разделяемые хелперы для verb-first команд (v2.0.0)."""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path
from typing import Annotated

import typer

from clite.client import APIError, Client
from clite.config import load_config
from clite.output import OutputFormat
from clite.output import emit as emit
from clite.output import parse_fields as parse_fields

# Поля, кодируемые как ;-separated в CSV-ячейках.
_ARRAY_FIELDS = {"labels", "projects", "blocked_by"}


def client() -> Client:
    return Client(load_config())


def handle_api_error(e: APIError) -> None:
    print(e.args[0], file=sys.stderr)
    if e.status_code == 401:
        raise typer.Exit(3)
    if e.status_code == 403:
        raise typer.Exit(4)
    raise typer.Exit(1)


def parse_set_pairs(set_pairs: list[str]) -> dict[str, object]:
    """`--set field=value` → dict для patch. Массивы (labels, projects,
    blocked_by, add_labels, remove_labels, add_blockers, remove_blockers)
    делятся по запятой."""
    patch: dict[str, object] = {}
    array_keys = _ARRAY_FIELDS | {
        "add_labels",
        "remove_labels",
        "add_blockers",
        "remove_blockers",
    }
    for pair in set_pairs:
        if "=" not in pair:
            print(f"--set value must be field=value (got {pair!r})", file=sys.stderr)
            raise typer.Exit(2)
        k, v = pair.split("=", 1)
        if k in array_keys:
            patch[k] = [x for x in v.split(",") if x] if v else []
        else:
            patch[k] = v
    return patch


def load_items(data: str | None, file: Path | None) -> list[object]:
    """Загрузить JSON-массив либо CSV (по расширению) из inline-аргумента или --file."""
    if data and file is not None:
        print("provide either inline data or --file, not both", file=sys.stderr)
        raise typer.Exit(2)
    if not data and file is None:
        print("provide inline JSON array or --file <path>", file=sys.stderr)
        raise typer.Exit(2)
    if file is not None:
        if not file.exists():
            print(f"file not found: {file}", file=sys.stderr)
            raise typer.Exit(2)
        if file.suffix.lower() == ".csv":
            return _load_csv(file)
        return _load_json(file.read_text())
    assert data is not None
    return _load_json(data)


def _load_json(raw: str) -> list[object]:
    try:
        items = json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"invalid JSON: {e}", file=sys.stderr)
        raise typer.Exit(2) from e
    if not isinstance(items, list):
        print("JSON root must be array", file=sys.stderr)
        raise typer.Exit(2)
    return items


def _load_csv(file: Path) -> list[object]:
    """CSV → list[dict]. Массивы (labels, projects, blocked_by) кодируются
    `;`-separated в ячейке."""
    items: list[object] = []
    with file.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            item: dict[str, object] = {}
            for k, v in row.items():
                if v is None or v == "":
                    continue
                if k in _ARRAY_FIELDS:
                    item[k] = [x.strip() for x in v.split(";") if x.strip()]
                else:
                    item[k] = v
            items.append(item)
    return items


def require_one_semantic(bulk: bool, batch: bool) -> str:
    """Ровно один из --bulk/--batch. Возвращает 'bulk' или 'batch'."""
    if bulk == batch:
        print("provide exactly one of --bulk or --batch", file=sys.stderr)
        raise typer.Exit(2)
    return "bulk" if bulk else "batch"


# Общие Annotated-типы для повторяющихся опций.

FieldsOpt = Annotated[
    str | None,
    typer.Option("--fields", help="Только эти поля через запятую (PRD §7.9)"),
]
OutputOpt = Annotated[OutputFormat, typer.Option("--output", "-o")]
