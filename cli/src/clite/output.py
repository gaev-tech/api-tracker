"""Форматирование вывода: построчно (TTY) / json (pipe)."""

import json
import sys
from typing import Literal

OutputFormat = Literal["table", "json", "auto"]


def _default_format() -> Literal["table", "json"]:
    return "table" if sys.stdout.isatty() else "json"


def parse_fields(value: str | None) -> list[str] | None:
    """Разобрать значение --fields ("a,b,c") в список имён полей.

    Пустая строка / None → None (рендерить дефолтный набор), PRD §7.9.
    """
    if not value:
        return None
    return [s.strip() for s in value.split(",") if s.strip()]


def _filter_dict(d: dict[str, object], fields: list[str]) -> dict[str, object]:
    return {k: d[k] for k in fields if k in d}


def _apply_fields(data: object, fields: list[str] | None) -> object:
    """Если задан fields — оставить только эти ключи (PRD §7.9.2).
    Сервер всегда возвращает полный объект, фильтрация только на рендере."""
    if not fields:
        return data
    if isinstance(data, list):
        return [_filter_dict(x, fields) if isinstance(x, dict) else x for x in data]
    if isinstance(data, dict):
        if "items" in data and isinstance(data["items"], list):
            return {
                **{k: v for k, v in data.items() if k != "items"},
                "items": [
                    _filter_dict(x, fields) if isinstance(x, dict) else x
                    for x in data["items"]
                ],
            }
        return _filter_dict(data, fields)
    return data


def emit(data: object, fmt: OutputFormat, fields: list[str] | None = None) -> None:
    data = _apply_fields(data, fields)
    if fmt == "auto":
        fmt = _default_format()
    if fmt == "json":
        print(json.dumps(data, indent=2, default=str, ensure_ascii=False))
        return
    if isinstance(data, list):
        emit_items(data)
    elif isinstance(data, dict):
        if "items" in data and isinstance(data["items"], list):
            emit_items(data["items"])
            if data.get("next_cursor"):
                print(f"\nnext_cursor: {data['next_cursor']}")
        else:
            emit_items([data])
    else:
        print(data)


def emit_items(items: list[object]) -> None:
    """Каждый элемент рендерится построчно `key: value`; пустая строка
    между элементами. Пустой список → "(empty)"."""
    if not items:
        print("(empty)")
        return
    for i, item in enumerate(items):
        if i > 0:
            print()
        if not isinstance(item, dict):
            print(item)
            continue
        for k, v in item.items():
            print(f"{k}: {_render_cell(v)}")


def _render_cell(value: object) -> str:
    if value is None:
        return "-"
    if isinstance(value, list):
        return ", ".join(str(x) for x in value)
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False, default=str)
    return str(value)
