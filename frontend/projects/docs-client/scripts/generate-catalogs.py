"""Build-time generator for the event-type and system-method catalogs
(ARCH §16.5.3, §16.5.4; IPLAN §6.2.2.3, §6.2.2.4).

Parses:
  - backend/tasks-service/src/tasks_service/services/events.py
    → EVENT_CATALOG (frozenset of event-type names)
  - backend/tasks-service/src/tasks_service/services/system_methods.py
    → whitelisted method names from the dispatcher's if-chain.

Outputs:
  - assets/event-catalog.json
  - assets/system-methods.json
"""

from __future__ import annotations

import ast
import json
import re
from pathlib import Path
from typing import Any

THIS = Path(__file__).resolve()
DOCS_CLIENT_DIR = THIS.parent.parent
REPO_ROOT = DOCS_CLIENT_DIR.parents[2]
TASKS_SVC_SRC = (
    REPO_ROOT / "backend" / "tasks-service" / "src" / "tasks_service"
)
EVENTS_FILE = TASKS_SVC_SRC / "services" / "events.py"
SYSMETH_FILE = TASKS_SVC_SRC / "services" / "system_methods.py"

EVENT_OUT = DOCS_CLIENT_DIR / "src" / "assets" / "event-catalog.json"
SYSMETH_OUT = DOCS_CLIENT_DIR / "src" / "assets" / "system-methods.json"


EVENT_NOTES: dict[str, str] = {
    "task.created": "Emitted right after a bulk-create commits each task.",
    "task.updated": "Generic update — any field changed (PRD §7.1).",
    "task.status_changed": "Dedicated event when `status` is among the changed fields.",
    "task.assigned": "Dedicated event when `assignee` is among the changed fields.",
    "task.labeled": "Dedicated event when `labels` are among the changed fields.",
    "task.deleted": "Reserved for future hard-delete (not yet emitted).",
}


SYSTEM_METHOD_NOTES: dict[str, dict[str, Any]] = {
    "tasks.list": {
        "summary": "List tasks matching an RSQL filter, with optional limit.",
        "args": [
            {"name": "filter", "type": "string", "required": False},
            {"name": "limit", "type": "int", "required": False, "default": 50},
        ],
        "returns": "{ tasks: list[Task], next_cursor: string|null }",
    },
    "tasks.create": {
        "summary": "Create exactly one task (thin wrapper over bulk_create[0]).",
        "args": [
            {"name": "payload", "type": "TaskCreate", "required": True},
        ],
        "returns": "{ task: Task }",
    },
    "tasks.bulk_update": {
        "summary": "Apply the same patch to every task matching the RSQL filter.",
        "args": [
            {"name": "filter", "type": "string", "required": True},
            {"name": "patch", "type": "TaskUpdate", "required": True},
        ],
        "returns": "{ affected: int, task_ids: list[string] }",
    },
    "tasks.batch_update": {
        "summary": "Atomic update for tasks; raises if any fails its permission check.",
        "args": [
            {"name": "filter", "type": "string", "required": True},
            {"name": "patch", "type": "TaskUpdate", "required": True},
        ],
        "returns": "{ affected: int }",
    },
    "tasks.share": {
        "summary": "Grant direct task perms to a user or team.",
        "args": [
            {"name": "task_id", "type": "sha1_key", "required": True},
            {"name": "user_email", "type": "user_email", "required": False},
            {"name": "team_id", "type": "sha1_key", "required": False},
            {"name": "perms", "type": "list[string]", "required": True},
        ],
        "returns": "{ ok: bool }",
    },
}


def _extract_event_catalog() -> list[str]:
    if not EVENTS_FILE.exists():
        return list(EVENT_NOTES.keys())
    tree = ast.parse(EVENTS_FILE.read_text())
    constants: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            value = node.value
            if isinstance(value, ast.Constant) and isinstance(value.value, str):
                constants[node.target.id] = value.value
        elif isinstance(node, ast.Assign):
            for tgt in node.targets:
                if (
                    isinstance(tgt, ast.Name)
                    and isinstance(node.value, ast.Constant)
                    and isinstance(node.value.value, str)
                ):
                    constants[tgt.id] = node.value.value
    # Pick names that start with EVENT_, preserve source order
    return [v for k, v in constants.items() if k.startswith("EVENT_")]


def _extract_system_methods() -> list[str]:
    if not SYSMETH_FILE.exists():
        return list(SYSTEM_METHOD_NOTES.keys())
    text = SYSMETH_FILE.read_text()
    # Look for: if method == "tasks.list":
    pattern = re.compile(r'method\s*==\s*"([a-zA-Z0-9_.]+)"')
    names: list[str] = []
    seen: set[str] = set()
    for match in pattern.finditer(text):
        name = match.group(1)
        if name in seen:
            continue
        seen.add(name)
        names.append(name)
    return names


def _build_event_catalog() -> dict[str, Any]:
    names = _extract_event_catalog()
    items = []
    for name in names:
        items.append(
            {
                "type": name,
                "note": EVENT_NOTES.get(name, ""),
            }
        )
    return {
        "generator": "generate-catalogs.py",
        "source": "backend/tasks-service/src/tasks_service/services/events.py",
        "items": items,
    }


def _build_system_methods_catalog() -> dict[str, Any]:
    names = _extract_system_methods()
    items = []
    for name in names:
        spec = SYSTEM_METHOD_NOTES.get(name, {})
        items.append(
            {
                "name": name,
                "summary": spec.get("summary", ""),
                "args": spec.get("args", []),
                "returns": spec.get("returns", ""),
            }
        )
    return {
        "generator": "generate-catalogs.py",
        "source": "backend/tasks-service/src/tasks_service/services/system_methods.py",
        "items": items,
    }


def main() -> None:
    events = _build_event_catalog()
    sysmeth = _build_system_methods_catalog()
    EVENT_OUT.parent.mkdir(parents=True, exist_ok=True)
    EVENT_OUT.write_text(json.dumps(events, indent=2, ensure_ascii=False) + "\n")
    SYSMETH_OUT.write_text(json.dumps(sysmeth, indent=2, ensure_ascii=False) + "\n")
    print(
        f"wrote {EVENT_OUT.name} ({len(events['items'])} events), "
        f"{SYSMETH_OUT.name} ({len(sysmeth['items'])} system methods)"
    )


if __name__ == "__main__":
    main()
