"""`clite update <noun>` — массовое обновление по фильтру."""

from __future__ import annotations

from typing import Annotated

import typer

from clite.client import APIError
from clite.commands._shared import (
    OutputOpt,
    client,
    emit,
    handle_api_error,
    parse_set_pairs,
    require_one_semantic,
)

app = typer.Typer(no_args_is_help=True, help="Массовое обновление")


@app.command("tasks")
def tasks(
    filter: Annotated[str, typer.Option("--filter", "-f", help="RSQL")],
    set_pairs: Annotated[
        list[str], typer.Option("--set", "-s", help="field=value")
    ] = None,  # type: ignore[assignment]
    bulk: Annotated[
        bool, typer.Option("--bulk", help="Partial success (PRD §7.2.1)")
    ] = False,
    batch: Annotated[
        bool, typer.Option("--batch", help="Атомарно (PRD §7.3.1)")
    ] = False,
    output: OutputOpt = "auto",
) -> None:
    """Массовое обновление по RSQL-фильтру. Ровно один из --bulk или --batch.

    --set поля: title, description_md, status, assignee, labels (csv),
    projects (csv), add_labels, remove_labels, add_blockers, remove_blockers.
    """
    semantic = require_one_semantic(bulk, batch)
    if not set_pairs:
        print("at least one --set field=value required", flush=True)
        raise typer.Exit(2)
    patch = parse_set_pairs(set_pairs)
    endpoint = f"/v1/tasks/{semantic}-update"
    with client() as c:
        try:
            result = c.post(endpoint, params={"filter": filter}, json={"patch": patch})
        except APIError as e:
            handle_api_error(e)
            return
    emit(result, output)
