"""TC 3.x — clite task. См. specs/cli-test-cases.md §3.

M2.28: single-create / single-update удалены.
M2.29: task get/list/--filter удалены — CLI только пишет (bulk/batch),
read доступен через docs-client / API напрямую (см. fixture mk_task).
"""

from __future__ import annotations

import json
import re

KEY_RE = re.compile(r"[0-9a-f]{40}")


def test_TC_3_1_1_minimal_task_create(clite):
    """3.1.1 — `task create bulk '[{...}]'` → exit 0; task_id (SHA1) в результате."""
    r = clite(
        [
            "task",
            "create",
            "bulk",
            json.dumps([{"title": "TC-3.1.1"}]),
            "--output",
            "json",
        ]
    )
    assert r.returncode == 0, r.stderr
    data = json.loads(r.stdout)
    result = data["results"][0]
    assert result["status"] == "ok"
    assert KEY_RE.fullmatch(result["task_id"])


def test_TC_3_1_2_create_with_description(mk_task):
    """3.1.2 — bulk-create с description."""
    t = mk_task("TC-3.1.2", description_md="## Hello")
    assert t["description_md"] == "## Hello"


def test_TC_3_1_3_create_with_labels(mk_task):
    """3.1.3 — labels через bulk-create."""
    t = mk_task("TC-3.1.3", labels=["bug", "urgent"])
    assert sorted(t["labels"]) == ["bug", "urgent"]
