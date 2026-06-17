"""`clite run <noun>` — immediate trigger автоматизации (M3+, TC §9.3)."""

from __future__ import annotations

from typing import Annotated

import typer

from clite.client import APIError
from clite.commands._shared import OutputOpt, client, emit, handle_api_error

app = typer.Typer(no_args_is_help=True, help="Запуск (immediate trigger)")


@app.command("automation")
def automation(
    key: Annotated[str, typer.Argument(help="SHA1-ключ автоматизации (или префикс)")],
    output: OutputOpt = "auto",
) -> None:
    """Запустить action автоматизации немедленно (TC §9.3.1)."""
    with client() as c:
        try:
            result = c.post(f"/v1/automations/{key}/run")
        except APIError as e:
            handle_api_error(e)
            return
    emit(result, output)
