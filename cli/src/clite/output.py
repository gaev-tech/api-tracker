"""Форматирование вывода: table (TTY) / json (pipe)."""

import json
import sys
from typing import Literal

from rich.console import Console
from rich.table import Table

OutputFormat = Literal["table", "json", "auto"]


def _default_format() -> Literal["table", "json"]:
    return "table" if sys.stdout.isatty() else "json"


def emit(data: object, fmt: OutputFormat) -> None:
    if fmt == "auto":
        fmt = _default_format()
    if fmt == "json":
        print(json.dumps(data, indent=2, default=str, ensure_ascii=False))
        return
    if isinstance(data, list):
        emit_table(data)
    elif isinstance(data, dict):
        if "items" in data and isinstance(data["items"], list):
            emit_table(data["items"])
            if data.get("next_cursor"):
                print(f"\nnext_cursor: {data['next_cursor']}")
        else:
            emit_object(data)
    else:
        print(data)


def emit_table(rows: list[object]) -> None:
    if not rows:
        print("(empty)")
        return
    if not isinstance(rows[0], dict):
        for r in rows:
            print(r)
        return
    columns = list(rows[0].keys())
    table = Table(show_lines=False)
    for col in columns:
        table.add_column(col)
    for row in rows:
        if not isinstance(row, dict):
            continue
        table.add_row(*[_render_cell(row.get(c)) for c in columns])
    Console().print(table)


def emit_object(obj: dict[str, object]) -> None:
    table = Table(show_header=False, show_lines=False)
    table.add_column("key", style="bold")
    table.add_column("value")
    for k, v in obj.items():
        table.add_row(k, _render_cell(v))
    Console().print(table)


def _render_cell(value: object) -> str:
    if value is None:
        return "-"
    if isinstance(value, list):
        return ", ".join(str(x) for x in value)
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False, default=str)
    return str(value)
