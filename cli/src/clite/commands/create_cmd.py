"""`clite create <noun>` — создание задач (bulk/batch), команды, проекта,
автоматизации, секрета."""

from __future__ import annotations

import json as _json
import sys
from pathlib import Path
from typing import Annotated

import typer

from clite.client import APIError
from clite.commands._shared import (
    OutputOpt,
    client,
    emit,
    handle_api_error,
    load_items,
    require_one_semantic,
)

app = typer.Typer(no_args_is_help=True, help="Создание сущностей")


@app.command("tasks")
def tasks(
    data: Annotated[
        str | None,
        typer.Argument(help="Inline JSON-массив задач (или используйте --file)"),
    ] = None,
    file: Annotated[
        Path | None,
        typer.Option("--file", help="Путь к JSON или CSV (определяется по расширению)"),
    ] = None,
    bulk: Annotated[
        bool, typer.Option("--bulk", help="Partial success (PRD §7.2.1)")
    ] = False,
    batch: Annotated[
        bool, typer.Option("--batch", help="Атомарно (PRD §7.3.1)")
    ] = False,
    output: OutputOpt = "auto",
) -> None:
    """Массовое создание задач. Требуется ровно один из --bulk или --batch."""
    semantic = require_one_semantic(bulk, batch)
    items = load_items(data, file)
    endpoint = f"/v1/tasks/{semantic}-create"
    with client() as c:
        try:
            result = c.post(endpoint, json={"items": items})
        except APIError as e:
            handle_api_error(e)
            return
    emit(result, output)


@app.command("team")
def team(
    name: Annotated[str, typer.Option("--name", "-n", help="Имя команды")],
    output: OutputOpt = "auto",
) -> None:
    """Создать команду; создатель — единственный участник со всеми правами."""
    with client() as c:
        try:
            result = c.post("/v1/teams", json={"name": name})
        except APIError as e:
            handle_api_error(e)
            return
    emit(result, output)


@app.command("project")
def project(
    name: Annotated[str, typer.Option("--name", "-n", help="Имя проекта")],
    output: OutputOpt = "auto",
) -> None:
    """Создать проект; создатель получает все project + task perms."""
    with client() as c:
        try:
            result = c.post("/v1/projects", json={"name": name})
        except APIError as e:
            handle_api_error(e)
            return
    emit(result, output)


@app.command("automation")
def automation(
    project_key: Annotated[
        str,
        typer.Option("--project", "-p", help="SHA1-ключ проекта (или префикс)"),
    ],
    name: Annotated[str, typer.Option("--name", "-n", help="Имя автоматизации")],
    trigger_type: Annotated[
        str,
        typer.Option(
            "--trigger-type", help="event | cron (PRD §8.4)", case_sensitive=False
        ),
    ],
    trigger_config: Annotated[
        str,
        typer.Option(
            "--trigger-config",
            help="JSON: {event_type, filter} для event | {cron} для cron",
        ),
    ],
    action_type: Annotated[
        str,
        typer.Option(
            "--action-type",
            help="webhook | system_method (PRD §8.5)",
            case_sensitive=False,
        ),
    ],
    action_config: Annotated[
        str,
        typer.Option(
            "--action-config",
            help=(
                "JSON: {url, headers, body} для webhook | "
                "{method, args} для system_method"
            ),
        ),
    ],
    output: OutputOpt = "auto",
) -> None:
    """Создать автоматизацию проекта (PRD §8, ARCH §11)."""
    try:
        trig_cfg = _json.loads(trigger_config)
    except _json.JSONDecodeError as e:
        print(f"invalid --trigger-config JSON: {e}", file=sys.stderr)
        raise typer.Exit(2) from e
    try:
        act_cfg = _json.loads(action_config)
    except _json.JSONDecodeError as e:
        print(f"invalid --action-config JSON: {e}", file=sys.stderr)
        raise typer.Exit(2) from e
    payload = {
        "project_id": project_key,
        "name": name,
        "trigger_type": trigger_type.lower(),
        "trigger_config": trig_cfg,
        "action_type": action_type.lower(),
        "action_config": act_cfg,
    }
    with client() as c:
        try:
            result = c.post("/v1/automations", json=payload)
        except APIError as e:
            handle_api_error(e)
            return
    emit(result, output)


@app.command("secret")
def secret(
    project_key: Annotated[
        str,
        typer.Option("--project", "-p", help="SHA1-ключ проекта (или префикс)"),
    ],
    name: Annotated[str, typer.Option("--name", "-n", help="Имя секрета")],
    value: Annotated[str, typer.Option("--value", "-v", help="Значение")],
    output: OutputOpt = "auto",
) -> None:
    """Создать или перезаписать секрет проекта (PRD §8.7, ARCH §13)."""
    with client() as c:
        try:
            result = c.post(
                f"/v1/projects/{project_key}/secrets",
                json={"name": name, "value": value},
            )
        except APIError as e:
            handle_api_error(e)
            return
    emit(result, output)
