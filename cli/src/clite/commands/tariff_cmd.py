"""`clite tariff` — show / catalog (M5 — Free only).

См. tariff.md §15.1–§15.2, IPLAN §7.2.6.

Команды:
- `tariff show`     — текущее состояние тарифа (Bearer auth).
- `tariff catalog`  — каталог тарифов (public, без auth).

Команды `tariff upgrade/cancel/payments/payment-method/--include-frozen`
не реализуются в M5 — они для M6 (платные тарифы и ЮКасса; tariff.md
§15.3–§15.8, §15.15).
"""

from __future__ import annotations

import sys

import httpx
import typer

from clite.client import APIError
from clite.commands._shared import (
    FieldsOpt,
    OutputOpt,
    client,
    handle_api_error,
    parse_fields,
)
from clite.config import load_config
from clite.output import emit

app = typer.Typer(no_args_is_help=True, help="Тариф (M5 — Free)")

# Дефолтные поля (tariff.md §15.10 для show, §15.11 для catalog) — урезаны
# до M5-набора (без auto_renew/pro_bank_days/payment_method_*).
_DEFAULT_SHOW_FIELDS = [
    "tariff",
    "usage_task_shares",
    "limit_task_shares",
    "usage_projects",
    "limit_projects",
    "usage_teams",
    "limit_teams",
]
_DEFAULT_CATALOG_FIELDS = ["tier", "task_shares", "projects", "teams"]


@app.command("show")
def show(
    output: OutputOpt = "auto",
    fields: FieldsOpt = None,
) -> None:
    """Состояние тарифа текущего пользователя (Bearer auth)."""
    with client() as c:
        try:
            result = c.get("/auth/me/tariff")
        except APIError as e:
            handle_api_error(e)
            return
    emit(result, output, fields=parse_fields(fields) or _DEFAULT_SHOW_FIELDS)


@app.command("catalog")
def catalog(
    output: OutputOpt = "auto",
    fields: FieldsOpt = None,
) -> None:
    """Каталог тарифов (public, без auth)."""
    cfg = load_config()
    url = f"{cfg.base_url}/api/auth/tariff/catalog"
    try:
        resp = httpx.get(url, timeout=30)
    except httpx.HTTPError as e:
        print(f"connection failed: {e}", file=sys.stderr)
        raise typer.Exit(1) from e
    if resp.status_code >= 400:
        print(f"catalog failed: {resp.status_code}", file=sys.stderr)
        raise typer.Exit(1)
    body = resp.json()
    # Сервер возвращает {entries: [...]}; рендерим entries как список.
    entries = body.get("entries", []) if isinstance(body, dict) else body
    emit(entries, output, fields=parse_fields(fields) or _DEFAULT_CATALOG_FIELDS)
