"""Build-time generator for the docs search index (IPLAN §6.2.1, M4.8).

Aggregates the previously-generated JSON catalogs (CLI commands, RSQL fields,
events, system methods) plus a static list of tutorials and reference pages
into one flat array of search items.

Output: frontend/projects/docs-client/src/assets/search-index.json
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

THIS = Path(__file__).resolve()
DOCS_CLIENT_DIR = THIS.parent.parent
ASSETS_DIR = DOCS_CLIENT_DIR / "src" / "assets"
CONTENT_DIR = DOCS_CLIENT_DIR / "src" / "content"

OUT_PATH = ASSETS_DIR / "search-index.json"


STATIC_PAGES: list[dict[str, str]] = [
    {
        "type": "page",
        "name": "Overview",
        "description": "What api-tracker is and how to navigate the docs.",
        "url": "/",
    },
    {
        "type": "page",
        "name": "Quickstart",
        "description": "Install, log in, create a task, read it back. Four steps.",
        "url": "/quickstart",
    },
    {
        "type": "page",
        "name": "Installation",
        "description": "All install channels — available now and coming in M4.B.",
        "url": "/installation",
    },
    {
        "type": "page",
        "name": "CLI Reference",
        "description": "Every clite command, generated from typer introspection.",
        "url": "/cli",
    },
    {
        "type": "page",
        "name": "RSQL Reference",
        "description": "Operators, fields, and examples for the --filter language.",
        "url": "/rsql",
    },
    {
        "type": "page",
        "name": "Events",
        "description": "Catalog of event_type values emitted on task mutations.",
        "url": "/events",
    },
    {
        "type": "page",
        "name": "System Methods",
        "description": "Whitelisted methods callable by automations.",
        "url": "/system-methods",
    },
    {
        "type": "page",
        "name": "Automations",
        "description": "Trigger types, action shape, secret handling.",
        "url": "/automations",
    },
]


TUTORIAL_META: list[dict[str, str]] = [
    {
        "type": "tutorial",
        "name": "Getting Started",
        "slug": "getting-started",
        "description": "Install, log in, create your first task, read history.",
    },
    {
        "type": "tutorial",
        "name": "RSQL primer",
        "slug": "rsql-primer",
        "description": "Operators, logic, per-field examples for the filter language.",
    },
    {
        "type": "tutorial",
        "name": "AI-driven workflow",
        "slug": "ai-driven-workflow",
        "description": "Bulk-create, me literal, batch updates, history-as-audit-trail.",
    },
    {
        "type": "tutorial",
        "name": "Writing automations",
        "slug": "writing-automations",
        "description": "Cron and event triggers, secrets, Jinja templates, debugging.",
    },
]


def _safe_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except Exception:  # noqa: BLE001
        return None


def _slug_for_cli(path: str) -> str:
    return path.replace(" ", "-")


def _build_index() -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []

    # 1. Static pages.
    for p in STATIC_PAGES:
        items.append(
            {
                "type": p["type"],
                "name": p["name"],
                "description": p["description"],
                "url": p["url"],
            }
        )

    # 2. Tutorials.
    for t in TUTORIAL_META:
        items.append(
            {
                "type": t["type"],
                "name": t["name"],
                "description": t["description"],
                "url": f"/tutorials/{t['slug']}",
            }
        )

    # 3. CLI commands.
    cli = _safe_json(ASSETS_DIR / "cli-reference.json")
    if cli:
        for cmd in cli.get("commands", []):
            items.append(
                {
                    "type": "command",
                    "name": f"clite {cmd['path']}",
                    "description": cmd.get("summary") or "",
                    "url": f"/cli/{_slug_for_cli(cmd['path'])}",
                }
            )

    # 4. RSQL fields.
    rsql = _safe_json(ASSETS_DIR / "rsql-reference.json")
    if rsql:
        for entity, fields in (rsql.get("fields_by_entity") or {}).items():
            for f in fields:
                items.append(
                    {
                        "type": "rsql-field",
                        "name": f"{entity}.{f['name']}",
                        "description": f.get("note") or f.get("type", ""),
                        "url": "/rsql",
                    }
                )

    # 5. Events.
    events = _safe_json(ASSETS_DIR / "event-catalog.json")
    if events:
        for item in events.get("items", []):
            items.append(
                {
                    "type": "event",
                    "name": item["type"],
                    "description": item.get("note", ""),
                    "url": "/events",
                }
            )

    # 6. System methods.
    sysmeth = _safe_json(ASSETS_DIR / "system-methods.json")
    if sysmeth:
        for item in sysmeth.get("items", []):
            items.append(
                {
                    "type": "system-method",
                    "name": item["name"],
                    "description": item.get("summary", ""),
                    "url": "/system-methods",
                }
            )

    return items


def main() -> None:
    items = _build_index()
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(
        json.dumps(
            {
                "generator": "generate-search-index.py",
                "items": items,
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n"
    )
    print(f"wrote {OUT_PATH} ({len(items)} items)")


if __name__ == "__main__":
    main()
