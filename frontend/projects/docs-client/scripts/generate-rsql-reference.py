"""Build-time generator for RSQL reference (ARCH §16.5.2, IPLAN §6.2.2.2).

Strategy:
  1. If contracts/openapi/tasks.json contains x-rsql-fields markers per path,
     parse them out (preferred — single source of truth).
  2. Otherwise fall back to a hardcoded mirror of services/tasks._task_field_specs
     and the (currently smaller) history field set. Mark output `fallback=true`
     so the page can show a banner.

Output: frontend/projects/docs-client/src/assets/rsql-reference.json
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

THIS = Path(__file__).resolve()
DOCS_CLIENT_DIR = THIS.parent.parent
REPO_ROOT = DOCS_CLIENT_DIR.parents[2]
OPENAPI_PATH = REPO_ROOT / "contracts" / "openapi" / "tasks.json"
OUT_PATH = DOCS_CLIENT_DIR / "src" / "assets" / "rsql-reference.json"


# Hardcoded fallback — must mirror:
#   backend/tasks-service/src/tasks_service/services/tasks.py::_task_field_specs
#   backend/tasks-service/src/tasks_service/services/query_resolver.py::_task_field_specs
# Regenerate from OpenAPI once x-rsql-fields markers are added (ARCH §8.3).
FALLBACK_FIELDS_BY_ENTITY: dict[str, list[dict[str, str]]] = {
    "task": [
        {"name": "id", "type": "sha1_key", "note": "Task id; 4..40 hex."},
        {"name": "title", "type": "string", "note": "Verbatim match."},
        {"name": "status", "type": "string", "note": "open | done (PRD §5.1)."},
        {"name": "labels", "type": "string_array", "note": "=in= / =out= only."},
        {
            "name": "assignee",
            "type": "user_email",
            "note": "Accepts `me` literal (PRD §5.4).",
        },
        {"name": "created_at", "type": "datetime", "note": "ISO-8601 string."},
    ],
    "history": [
        {"name": "task_id", "type": "sha1_key", "note": "History row's task."},
        {"name": "actor", "type": "user_email", "note": "Who made the change."},
        {"name": "action", "type": "string", "note": "created | updated | …"},
        {"name": "happened_at", "type": "datetime", "note": "ISO-8601."},
    ],
}

OPERATORS: list[dict[str, str]] = [
    {"op": "==", "kind": "comparison", "applies": "string, int, datetime, sha1_key, user_email", "note": "Strict equality."},
    {"op": "!=", "kind": "comparison", "applies": "string, int, datetime, sha1_key, user_email", "note": "Strict non-equality."},
    {"op": "=gt=", "kind": "comparison", "applies": "int, datetime", "note": "Greater than."},
    {"op": "=ge=", "kind": "comparison", "applies": "int, datetime", "note": "Greater or equal."},
    {"op": "=lt=", "kind": "comparison", "applies": "int, datetime", "note": "Less than."},
    {"op": "=le=", "kind": "comparison", "applies": "int, datetime", "note": "Less or equal."},
    {"op": "=in=(a,b,…)", "kind": "set", "applies": "string, int, sha1_key, user_email, string_array", "note": "Value is one of."},
    {"op": "=out=(a,b,…)", "kind": "set", "applies": "string, int, sha1_key, user_email, string_array", "note": "Value is none of."},
    {"op": ";", "kind": "logic", "applies": "any", "note": "Logical AND (higher precedence)."},
    {"op": ",", "kind": "logic", "applies": "any", "note": "Logical OR."},
    {"op": "(…)", "kind": "logic", "applies": "any", "note": "Grouping."},
]

EXAMPLES: list[dict[str, str]] = [
    {
        "expr": 'status=="open";assignee==me',
        "note": "Open tasks assigned to current user (TC §3.3.1).",
    },
    {
        "expr": 'labels=in=(backend,urgent)',
        "note": "Has any of these labels (TC §3.3.3).",
    },
    {
        "expr": 'created_at=ge=2026-01-01T00:00:00',
        "note": "Created on or after the date.",
    },
    {
        "expr": 'status=="open",assignee==me',
        "note": "OR: open OR mine (less common, but supported).",
    },
    {
        "expr": '(status=="open";labels=in=(urgent)),assignee==me',
        "note": "Grouping with mixed AND/OR.",
    },
]


def _try_openapi() -> tuple[dict[str, list[dict[str, str]]], bool]:
    """Returns (fields_by_entity, used_openapi).

    used_openapi=False means the result is the hardcoded fallback.
    """
    if not OPENAPI_PATH.exists():
        return FALLBACK_FIELDS_BY_ENTITY, False
    try:
        data = json.loads(OPENAPI_PATH.read_text())
    except Exception as e:  # noqa: BLE001
        print(f"[rsql] failed to parse {OPENAPI_PATH}: {e}", file=sys.stderr)
        return FALLBACK_FIELDS_BY_ENTITY, False

    fields_by_entity: dict[str, list[dict[str, str]]] = {}
    paths = data.get("paths") or {}
    for path, methods in paths.items():
        for method, op in (methods or {}).items():
            if not isinstance(op, dict):
                continue
            x = op.get("x-rsql-fields")
            if not isinstance(x, dict):
                continue
            entity = x.get("entity")
            fields = x.get("fields")
            if not entity or not isinstance(fields, list):
                continue
            fields_by_entity.setdefault(entity, [])
            for f in fields:
                if isinstance(f, dict) and "name" in f and "type" in f:
                    fields_by_entity[entity].append(
                        {
                            "name": str(f["name"]),
                            "type": str(f["type"]),
                            "note": str(f.get("note", "")),
                        }
                    )
    if not fields_by_entity:
        return FALLBACK_FIELDS_BY_ENTITY, False
    return fields_by_entity, True


def main() -> None:
    fields, from_openapi = _try_openapi()
    payload: dict[str, Any] = {
        "generator": "generate-rsql-reference.py",
        "source": "contracts/openapi/tasks.json#x-rsql-fields"
        if from_openapi
        else "fallback (hardcoded, regenerate via openapi)",
        "fallback": not from_openapi,
        "operators": OPERATORS,
        "fields_by_entity": fields,
        "examples": EXAMPLES,
    }
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
    suffix = "(from openapi)" if from_openapi else "(fallback)"
    total_fields = sum(len(v) for v in fields.values())
    print(
        f"wrote {OUT_PATH} {suffix}: "
        f"{len(fields)} entities, {total_fields} fields, "
        f"{len(OPERATORS)} operators"
    )


if __name__ == "__main__":
    main()
