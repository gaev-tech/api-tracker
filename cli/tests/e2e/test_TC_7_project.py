"""TC 7.x — clite create/get/rename/leave project (verb-first, v2.0.0)."""

from __future__ import annotations

import json
import re

import pytest

KEY_RE = re.compile(r"[0-9a-f]{40}")


def test_TC_7_1_1_project_create_returns_key(clite):
    """7.1.1 — `create project --name P` → exit 0, SHA1-ключ."""
    r = clite(["create", "project", "--name", "TC-7.1.1", "--output", "json"])
    assert r.returncode == 0, r.stderr
    data = json.loads(r.stdout)
    assert KEY_RE.fullmatch(data["id"])
    assert data["name"] == "TC-7.1.1"


def test_TC_7_3_1_attach_task_to_project_via_update(clite, mk_task):
    """7.3.1 — привязка задачи к проекту через `update tasks --set projects=K`."""
    p = clite(["create", "project", "--name", "TC-7.3.1-proj", "--output", "json"])
    project_id = json.loads(p.stdout)["id"]
    t = mk_task("TC-7.3.1-task")
    task_id = t["id"]

    upd = clite(
        [
            "update",
            "tasks",
            "--bulk",
            "--filter",
            f"id=={task_id[:10]}",
            "--set",
            f"projects={project_id}",
            "--output",
            "json",
        ]
    )
    assert upd.returncode == 0, upd.stderr
    assert json.loads(upd.stdout)["succeeded"] == 1

    got = clite(
        ["get", "project", project_id, "--fields", "id,task_ids", "--output", "json"]
    )
    assert got.returncode == 0, got.stderr
    assert task_id in json.loads(got.stdout).get("task_ids", [])


def test_TC_7_3_2_detach_task_via_update_empty_projects(clite, mk_task):
    """7.3.2 — отвязка через `update tasks --set projects=` (пустой список)."""
    p = clite(["create", "project", "--name", "TC-7.3.2-proj", "--output", "json"])
    project_id = json.loads(p.stdout)["id"]
    t = mk_task("TC-7.3.2-task")
    task_id = t["id"]

    clite(
        [
            "update",
            "tasks",
            "--bulk",
            "--filter",
            f"id=={task_id[:10]}",
            "--set",
            f"projects={project_id}",
        ]
    )
    # Теперь отвязать
    rm = clite(
        [
            "update",
            "tasks",
            "--bulk",
            "--filter",
            f"id=={task_id[:10]}",
            "--set",
            "projects=",
            "--output",
            "json",
        ]
    )
    assert rm.returncode == 0, rm.stderr

    got = clite(
        ["get", "project", project_id, "--fields", "id,task_ids", "--output", "json"]
    )
    assert task_id not in json.loads(got.stdout).get("task_ids", [])


def test_TC_7_5_1_project_leave_self_revoke(clite):
    """7.5.1 — `leave project` единственного участника → exit 0."""
    p = clite(["create", "project", "--name", "TC-7.5.1", "--output", "json"])
    project_id = json.loads(p.stdout)["id"]
    lv = clite(["leave", "project", project_id, "--output", "json"])
    assert lv.returncode == 0, lv.stderr


@pytest.mark.skip(reason="требует AUTH_MODE=jwt + auth-svc")
def test_TC_7_2_1_add_member_to_project() -> None:
    """7.2.1 — `add member <project> --email E --perm P`."""


@pytest.mark.skip(reason="требует второго пользователя")
def test_TC_7_2_2_add_member_without_permission() -> None:
    """7.2.2 — без manage_member_permissions → exit 4."""
