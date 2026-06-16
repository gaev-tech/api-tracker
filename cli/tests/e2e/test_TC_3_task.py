"""TC 3.x — clite task. См. specs/cli-test-cases.md §3."""

from __future__ import annotations

import json
import re

KEY_RE = re.compile(r"[0-9a-f]{40}")


def test_TC_3_1_1_minimal_task_create(clite):
    """3.1.1 — `clite task create --title "T1"` → exit 0, stdout содержит UUID."""
    r = clite(["task", "create", "--title", "TC-3.1.1", "--output", "json"])
    assert r.returncode == 0, r.stderr
    data = json.loads(r.stdout)
    assert "id" in data
    assert KEY_RE.fullmatch(data["id"])
    assert data["title"] == "TC-3.1.1"
    assert data["status"] == "open"


def test_TC_3_1_2_create_with_description(clite):
    """3.1.2 — `--title --description` → БД: description_md установлен."""
    r = clite(
        [
            "task",
            "create",
            "--title",
            "TC-3.1.2",
            "--description",
            "## Hello",
            "--output",
            "json",
        ]
    )
    assert r.returncode == 0, r.stderr
    data = json.loads(r.stdout)
    assert data["description_md"] == "## Hello"


def test_TC_3_1_3_create_with_labels(clite):
    """3.1.3 — `--label bug --label urgent` → labels = ["bug", "urgent"]."""
    r = clite(
        [
            "task",
            "create",
            "--title",
            "TC-3.1.3",
            "--label",
            "bug",
            "--label",
            "urgent",
            "--output",
            "json",
        ]
    )
    assert r.returncode == 0, r.stderr
    data = json.loads(r.stdout)
    assert sorted(data["labels"]) == ["bug", "urgent"]


def test_TC_3_3_1_list_default_sort(clite):
    """3.3.1 — `clite task list` → задачи отсортированы по created_at asc."""
    # Создаём 3 задачи последовательно.
    titles = ["TC-3.3.1-a", "TC-3.3.1-b", "TC-3.3.1-c"]
    for t in titles:
        clite(["task", "create", "--title", t])

    r = clite(["task", "list", "--output", "json"])
    assert r.returncode == 0, r.stderr
    data = json.loads(r.stdout)
    items = data["items"]
    listed_titles = [t["title"] for t in items if t["title"] in titles]
    assert listed_titles == titles  # порядок создания == порядок в списке


def test_TC_3_3_2_list_filter_by_status(clite):
    """3.3.2 — `--filter status==open` → только open."""
    clite(["task", "create", "--title", "TC-3.3.2-open"])
    create_done = clite(
        ["task", "create", "--title", "TC-3.3.2-done", "--status", "done"]
    )
    assert create_done.returncode == 0, create_done.stderr

    r = clite(["task", "list", "--filter", "status==open", "--output", "json"])
    assert r.returncode == 0, r.stderr
    data = json.loads(r.stdout)
    statuses = {t["status"] for t in data["items"]}
    assert statuses == {"open"} or statuses == set()


def test_TC_3_3_8_list_fields(clite):
    """3.3.8 — `--fields id,title,status` → json только с этими тремя колонками."""
    clite(["task", "create", "--title", "TC-3.3.8"])
    r = clite(
        [
            "task",
            "list",
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


def test_TC_3_5_3_get_fields(clite):
    """3.5.3 — `task get <id> --fields id,title` → в выводе только id и title."""
    created = clite(["task", "create", "--title", "TC-3.5.3", "--output", "json"])
    task_id = json.loads(created.stdout)["id"]
    r = clite(["task", "get", task_id, "--fields", "id,title", "--output", "json"])
    assert r.returncode == 0, r.stderr
    data = json.loads(r.stdout)
    assert set(data.keys()) == {"id", "title"}
    assert data["id"] == task_id and data["title"] == "TC-3.5.3"
