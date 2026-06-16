"""TC 3.x — clite create/update/get tasks (verb-first, v2.0.0)."""

from __future__ import annotations

import json
import re

KEY_RE = re.compile(r"[0-9a-f]{40}")


def test_TC_3_1_1_minimal_task_create(clite):
    """3.1.1 — `create tasks --bulk '[{...}]'` → exit 0; task_id (SHA1)."""
    r = clite(
        [
            "create",
            "tasks",
            "--bulk",
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
    t = mk_task("TC-3.1.2", description_md="## Hello")
    assert t["description_md"] == "## Hello"


def test_TC_3_1_3_create_with_labels(mk_task):
    t = mk_task("TC-3.1.3", labels=["bug", "urgent"])
    assert sorted(t["labels"]) == ["bug", "urgent"]


def test_TC_3_3_1_get_tasks_default_sort(clite, mk_task):
    """3.3.1 — `get tasks` → задачи отсортированы по created_at asc."""
    titles = ["TC-3.3.1-a", "TC-3.3.1-b", "TC-3.3.1-c"]
    for t in titles:
        mk_task(t)
    r = clite(["get", "tasks", "--output", "json"])
    assert r.returncode == 0, r.stderr
    listed = [t["title"] for t in json.loads(r.stdout)["items"] if t["title"] in titles]
    assert listed == titles


def test_TC_3_3_2_get_tasks_filter_status(clite, mk_task):
    mk_task("TC-3.3.2-open")
    mk_task("TC-3.3.2-done", status="done")
    r = clite(
        [
            "get",
            "tasks",
            "--filter",
            "status==open",
            "--fields",
            "id,status",
            "--output",
            "json",
        ]
    )
    assert r.returncode == 0, r.stderr
    statuses = {t["status"] for t in json.loads(r.stdout)["items"]}
    assert statuses == {"open"} or statuses == set()


def test_TC_3_3_8_get_tasks_fields(clite, mk_task):
    mk_task("TC-3.3.8")
    r = clite(
        [
            "get",
            "tasks",
            "--filter",
            'title=="TC-3.3.8"',
            "--fields",
            "id,title,status",
            "--output",
            "json",
        ]
    )
    assert r.returncode == 0, r.stderr
    items = json.loads(r.stdout)["items"]
    assert items
    for item in items:
        assert set(item.keys()) == {"id", "title", "status"}


def test_TC_3_update_tasks_bulk_by_id_prefix(clite, mk_task):
    """update tasks --bulk --filter id==<prefix> --set status=done — заменяет
    single-task update."""
    t = mk_task("TC-3.update")
    prefix = t["id"][:10]
    r = clite(
        [
            "update",
            "tasks",
            "--bulk",
            "--filter",
            f"id=={prefix}",
            "--set",
            "status=done",
            "--output",
            "json",
        ]
    )
    assert r.returncode == 0, r.stderr
    assert json.loads(r.stdout)["succeeded"] == 1
