"""TC 3.x — clite task. См. specs/cli-test-cases.md §3.

M2.28: single-create / single-update удалены. Все мутации — через
`task create bulk/batch` и `task update bulk/batch`. Просмотр одной задачи —
через `task --filter 'id==<prefix>'`.
"""

from __future__ import annotations

import json
import re

KEY_RE = re.compile(r"[0-9a-f]{40}")


def test_TC_3_1_1_minimal_task_create(clite):
    """3.1.1 — `task create bulk '[{...}]'` → exit 0; в результате task_id (SHA1)."""
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


def test_TC_3_1_2_create_with_description(clite, mk_task):
    """3.1.2 — `bulk` с description → задача создана с этим описанием."""
    t = mk_task("TC-3.1.2", description_md="## Hello")
    # mk_task возвращает только id,title,status,description_md,labels.
    assert t["description_md"] == "## Hello"


def test_TC_3_1_3_create_with_labels(clite, mk_task):
    """3.1.3 — labels через bulk-create."""
    t = mk_task("TC-3.1.3", labels=["bug", "urgent"])
    assert sorted(t["labels"]) == ["bug", "urgent"]


def test_TC_3_3_1_list_default_sort(clite, mk_task):
    """3.3.1 — `clite task` (default callback) → задачи по created_at asc."""
    titles = ["TC-3.3.1-a", "TC-3.3.1-b", "TC-3.3.1-c"]
    for t in titles:
        mk_task(t)
    r = clite(["task", "--output", "json"])
    assert r.returncode == 0, r.stderr
    data = json.loads(r.stdout)
    listed_titles = [t["title"] for t in data["items"] if t["title"] in titles]
    assert listed_titles == titles


def test_TC_3_3_2_list_filter_by_status(clite, mk_task):
    """3.3.2 — `--filter status==open` → только open."""
    mk_task("TC-3.3.2-open")
    mk_task("TC-3.3.2-done", status="done")
    r = clite(
        [
            "task",
            "--filter",
            "status==open",
            "--fields",
            "id,status",
            "--output",
            "json",
        ]
    )
    assert r.returncode == 0, r.stderr
    data = json.loads(r.stdout)
    statuses = {t["status"] for t in data["items"]}
    assert statuses == {"open"} or statuses == set()


def test_TC_3_3_8_list_fields(clite, mk_task):
    """3.3.8 — `--fields id,title,status` → json только с этими тремя колонками."""
    mk_task("TC-3.3.8")
    r = clite(
        [
            "task",
            "--filter",
            'title=="TC-3.3.8"',
            "--fields",
            "id,title,status",
            "--output",
            "json",
        ]
    )
    assert r.returncode == 0, r.stderr
    data = json.loads(r.stdout)
    assert data["items"], "должна найтись задача TC-3.3.8"
    for item in data["items"]:
        assert set(item.keys()) == {"id", "title", "status"}


def test_TC_3_5_3_get_via_filter_prefix(clite, mk_task):
    """3.5.3 — get одной задачи через `task --filter 'id==<prefix>'` (M2.28)."""
    t = mk_task("TC-3.5.3")
    prefix = t["id"][:10]
    r = clite(
        [
            "task",
            "--filter",
            f"id=={prefix}",
            "--fields",
            "id,title",
            "--output",
            "json",
        ]
    )
    assert r.returncode == 0, r.stderr
    data = json.loads(r.stdout)
    matches = [it for it in data["items"] if it["id"] == t["id"]]
    assert len(matches) == 1
    assert matches[0]["title"] == "TC-3.5.3"
