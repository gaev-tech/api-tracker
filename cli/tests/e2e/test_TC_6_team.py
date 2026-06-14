"""TC 6.x — clite team. См. specs/cli-test-cases.md §6.

AUTH_MODE=disabled — мульти-юзер кейсы (member set чужому email, permission-denied)
требуют auth-svc через gRPC и покрываются отдельной сессией с AUTH_MODE=jwt.
"""

from __future__ import annotations

import json
import re

import pytest

UUID_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")


def test_TC_6_1_1_team_create_returns_uuid_and_creator_perms(clite):
    """6.1.1 — `team create --name X` → exit 0, UUID; создатель — единственный
    участник с правами edit_team_name + manage_member_permissions (PRD §6.4).
    """
    r = clite(["team", "create", "--name", "TC-6.1.1", "--output", "json"])
    assert r.returncode == 0, r.stderr
    data = json.loads(r.stdout)
    assert UUID_RE.fullmatch(data["id"])
    assert data["name"] == "TC-6.1.1"
    members = data.get("members", [])
    assert len(members) == 1
    perms = set(members[0]["perms"])
    assert "edit_team_name" in perms
    assert "manage_member_permissions" in perms


def test_TC_6_1_1_team_appears_in_list(clite):
    """6.1.1 — созданная команда видна в `team list` для создателя (PRD §6.1.8)."""
    create = clite(["team", "create", "--name", "TC-6-list", "--output", "json"])
    assert create.returncode == 0, create.stderr
    team_id = json.loads(create.stdout)["id"]

    lst = clite(["team", "list", "--output", "json"])
    assert lst.returncode == 0, lst.stderr
    ids = [t["id"] for t in json.loads(lst.stdout)]
    assert team_id in ids


def test_TC_6_4_1_team_leave_last_member_cascade_delete(clite):
    """6.4.1 + 6.4.2 — единственный участник `team leave` → команда удалена
    (cascade, PRD §6.1.6). GET после leave → 404.
    """
    create = clite(["team", "create", "--name", "TC-6.4-leave", "--output", "json"])
    team_id = json.loads(create.stdout)["id"]

    leave = clite(["team", "leave", team_id, "--output", "json"])
    assert leave.returncode == 0, leave.stderr

    got = clite(["team", "get", team_id, "--output", "json"])
    assert got.returncode == 1, got.stderr


@pytest.mark.skip(reason="требует AUTH_MODE=jwt + auth-svc: gRPC резолв email→user_id")
def test_TC_6_2_1_team_member_set_positive() -> None:
    """6.2.1 — добавление участника по email с правами."""


@pytest.mark.skip(reason="требует второго пользователя без manage_member_permissions")
def test_TC_6_3_1_team_member_set_without_permission() -> None:
    """6.3.1 — без manage_member_permissions → exit 4."""


@pytest.mark.skip(reason="требует второго пользователя с меньшими правами")
def test_TC_6_3_2_team_grant_above_self() -> None:
    """6.3.2 — `--perms` выше своих → exit 4 (cannot grant above self)."""
