"""TC 7.x — clite project. См. specs/cli-test-cases.md §7.

В AUTH_MODE=disabled позитивные single-user кейсы проверяются полностью;
permission-denied и member-set чужому email требуют auth-svc через gRPC и
покрываются отдельной сессией с AUTH_MODE=jwt.
"""

from __future__ import annotations

import json
import re

import pytest

KEY_RE = re.compile(r"[0-9a-f]{40}")


def test_TC_7_1_1_project_create_returns_uuid(clite):
    """7.1.1 — `project create --name P1` → exit 0, UUID; создатель — единственный
    участник со всеми правами (PRD §6.5).
    """
    r = clite(["project", "create", "--name", "TC-7.1.1", "--output", "json"])
    assert r.returncode == 0, r.stderr
    data = json.loads(r.stdout)
    assert KEY_RE.fullmatch(data["id"])
    assert data["name"] == "TC-7.1.1"


def test_TC_7_3_1_project_task_add(clite):
    """7.3.1 — `project task add` при manage_projects → exit 0; задача в task_ids
    проекта.
    """
    p = clite(["project", "create", "--name", "TC-7.3.1-proj", "--output", "json"])
    project_id = json.loads(p.stdout)["id"]
    t = clite(["task", "create", "--title", "TC-7.3.1-task", "--output", "json"])
    task_id = json.loads(t.stdout)["id"]

    add = clite(["project", "task", "add", project_id, "--task", task_id])
    assert add.returncode == 0, add.stderr

    got = clite(
        ["project", "get", project_id, "--fields", "id,task_ids", "--output", "json"]
    )
    assert got.returncode == 0, got.stderr
    data = json.loads(got.stdout)
    assert task_id in data.get("task_ids", [])


def test_TC_7_3_2_project_task_remove(clite):
    """7.3.2 — `project task remove` → exit 0; задача исчезает из task_ids."""
    p = clite(["project", "create", "--name", "TC-7.3.2-proj", "--output", "json"])
    project_id = json.loads(p.stdout)["id"]
    t = clite(["task", "create", "--title", "TC-7.3.2-task", "--output", "json"])
    task_id = json.loads(t.stdout)["id"]

    clite(["project", "task", "add", project_id, "--task", task_id])
    rm = clite(["project", "task", "remove", project_id, "--task", task_id])
    assert rm.returncode == 0, rm.stderr

    got = clite(
        ["project", "get", project_id, "--fields", "id,task_ids", "--output", "json"]
    )
    data = json.loads(got.stdout)
    assert task_id not in data.get("task_ids", [])


def test_TC_7_5_1_project_leave_self_revoke(clite):
    """7.5.1 — `project leave` единственного участника → exit 0; повторный `project get`
    возвращает 404 (cascade-delete, PRD §6.1.6 распространяется на проекты).
    """
    p = clite(["project", "create", "--name", "TC-7.5.1", "--output", "json"])
    project_id = json.loads(p.stdout)["id"]

    leave = clite(["project", "leave", project_id, "--output", "json"])
    assert leave.returncode == 0, leave.stderr


@pytest.mark.skip(reason="требует AUTH_MODE=jwt + auth-svc: gRPC резолв email→user_id")
def test_TC_7_2_1_project_member_set_positive() -> None:
    """7.2.1 — добавление с непустыми правами → exit 0."""


@pytest.mark.skip(reason="требует второго пользователя без manage_member_permissions")
def test_TC_7_2_2_project_member_set_no_permission() -> None:
    """7.2.2 — без manage_member_permissions → exit 4."""


@pytest.mark.skip(reason="требует второго пользователя с меньшими правами")
def test_TC_7_2_3_project_grant_above_self() -> None:
    """7.2.3 — `--perms` выше своих → exit 4."""


@pytest.mark.skip(reason="требует второго пользователя без manage_projects")
def test_TC_7_4_1_project_task_add_without_permission() -> None:
    """7.4.1 — без manage_projects → exit 4."""
