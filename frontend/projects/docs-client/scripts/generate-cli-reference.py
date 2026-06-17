"""Build-time generator for CLI reference (ARCH §16.5.1, IPLAN §6.2.2.1).

Introspects the `clite` typer app and dumps a JSON catalog of every command,
its options, positional args, and short description.

Output: frontend/projects/docs-client/src/assets/cli-reference.json
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

THIS = Path(__file__).resolve()
DOCS_CLIENT_DIR = THIS.parent.parent  # …/frontend/projects/docs-client
REPO_ROOT = DOCS_CLIENT_DIR.parents[2]
CLI_SRC = REPO_ROOT / "cli" / "src"
OUT_PATH = DOCS_CLIENT_DIR / "src" / "assets" / "cli-reference.json"


def _ensure_cli_importable() -> None:
    if str(CLI_SRC) not in sys.path:
        sys.path.insert(0, str(CLI_SRC))


def _serialize_option(opt: Any) -> dict[str, Any]:
    return {
        "names": list(getattr(opt, "opts", [])),
        "secondary_names": list(getattr(opt, "secondary_opts", [])),
        "type": getattr(getattr(opt, "type", None), "name", str(getattr(opt, "type", ""))),
        "required": bool(getattr(opt, "required", False)),
        "default": _safe_default(getattr(opt, "default", None)),
        "help": (getattr(opt, "help", "") or "").strip(),
        "multiple": bool(getattr(opt, "multiple", False)),
        "is_flag": bool(getattr(opt, "is_flag", False)),
    }


def _serialize_argument(arg: Any) -> dict[str, Any]:
    return {
        "name": getattr(arg, "name", ""),
        "type": getattr(getattr(arg, "type", None), "name", str(getattr(arg, "type", ""))),
        "required": bool(getattr(arg, "required", False)),
        "nargs": int(getattr(arg, "nargs", 1)),
    }


def _is_option(param: Any) -> bool:
    # Typer uses TyperOption / TyperArgument subclasses of internal click;
    # duck-type on attribute name to avoid version-mismatch isinstance failures.
    return type(param).__name__.lower().endswith("option")


def _is_argument(param: Any) -> bool:
    return type(param).__name__.lower().endswith("argument")


def _safe_default(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (str, int, float, bool, list, dict)):
        return value
    return str(value)


def _walk(
    cmd: Any,
    path: list[str],
    out: list[dict[str, Any]],
) -> None:
    sub_commands: dict[str, Any] = getattr(cmd, "commands", {}) or {}
    is_group = bool(sub_commands)
    options: list[dict[str, Any]] = []
    arguments: list[dict[str, Any]] = []
    for param in getattr(cmd, "params", []) or []:
        if _is_option(param):
            # skip auto-added typer completion options at root
            opts_list = list(getattr(param, "opts", []))
            if any(
                n in ("--install-completion", "--show-completion") for n in opts_list
            ):
                continue
            options.append(_serialize_option(param))
        elif _is_argument(param):
            arguments.append(_serialize_argument(param))
    summary = ""
    if cmd.help:
        summary = cmd.help.strip().splitlines()[0]
    elif cmd.short_help:
        summary = cmd.short_help.strip()

    out.append(
        {
            "path": " ".join(path) if path else "",
            "name": cmd.name or "",
            "summary": summary,
            "description": (cmd.help or "").strip(),
            "is_group": is_group,
            "options": options,
            "arguments": arguments,
            "examples": _examples_for(path),
        }
    )

    for sub_name, sub in sub_commands.items():
        _walk(sub, [*path, sub_name], out)


def _examples_for(path: list[str]) -> list[dict[str, str]]:
    """Hand-curated runnable examples per command path.

    Keep this short and aligned with cli-test-cases.md so the docs stay honest.
    """
    p = " ".join(path)
    examples: dict[str, list[dict[str, str]]] = {
        "login": [{"cmd": "clite login --email me@example.org", "note": "Magic-link login (TC §5)."}],
        "me": [{"cmd": "clite me", "note": "Print current credentials."}],
        "get tasks": [
            {"cmd": 'clite get tasks --filter \'status=="open";assignee==me\'', "note": "RSQL filter (TC §3)."},
            {"cmd": "clite get tasks --fields id,title,status", "note": "Trim columns."},
        ],
        "get log": [
            {"cmd": "clite get log --task abc1234", "note": "History of one task (TC §4)."},
            {"cmd": "clite get log --user me@example.org", "note": "Audit log per user."},
        ],
        "create tasks": [
            {
                "cmd": "clite create tasks --bulk \'[{\"title\":\"first\"},{\"title\":\"second\"}]\'",
                "note": "Bulk create.",
            },
        ],
        "update tasks": [
            {
                "cmd": "clite update tasks --filter 'status==\"open\"' --batch '{\"status\":\"done\"}'",
                "note": "Batch update by RSQL (TC §3.4).",
            },
        ],
        "create automation": [
            {
                "cmd": "clite create automation --project P --name daily-digest --trigger cron:'0 9 * * *' --action 'tasks.list'",
                "note": "Cron automation (TC §9).",
            },
        ],
        "run automation": [
            {"cmd": "clite run automation <id>", "note": "Fire immediately (TC §9.3.1)."},
        ],
        "tariff show": [{"cmd": "clite tariff show", "note": "Show current tariff state."}],
        "tariff catalog": [{"cmd": "clite tariff catalog", "note": "List all tariffs."}],
    }
    return examples.get(p, [])


def main() -> None:
    _ensure_cli_importable()
    from typer.main import get_command  # type: ignore[import-untyped]

    from clite.__main__ import app as typer_app

    root_cmd = get_command(typer_app)
    catalog: list[dict[str, Any]] = []
    sub_commands: dict[str, Any] = getattr(root_cmd, "commands", {}) or {}
    for name, sub in sub_commands.items():
        _walk(sub, [name], catalog)
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "generator": "generate-cli-reference.py",
        "source": "cli.__main__:app",
        "commands": catalog,
    }
    OUT_PATH.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
    leaf_count = sum(1 for c in catalog if not c["is_group"])
    print(f"wrote {OUT_PATH} ({len(catalog)} entries, {leaf_count} leaf commands)")


if __name__ == "__main__":
    main()
