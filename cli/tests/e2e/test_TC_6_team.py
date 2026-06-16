"""TC 6.x — clite create/get/leave team (verb-first, v2.0.0)."""

from __future__ import annotations

import json
import re

import pytest

KEY_RE = re.compile(r"[0-9a-f]{40}")


def test_TC_6_1_1_team_create_returns_key_and_creator_perms(clite):
    """6.1.1 — `create team --name X` → exit 0; creator — единственный участник
    с edit_team_name + manage_member_permissions (PRD §6.4).
    """
    r = clite(["create", "team", "--name", "TC-6.1.1", "--output", "json"])
    assert r.returncode == 0, r.stderr
    data = json.loads(r.stdout)
    assert KEY_RE.fullmatch(data["id"])
    assert data["name"] == "TC-6.1.1"
    members = data.get("members", [])
    assert len(members) == 1
    perms = set(members[0]["perms"])
    assert "edit_team_name" in perms
    assert "manage_member_permissions" in perms


def test_TC_6_1_1_team_appears_in_list(clite):
    """6.1.1 — созданная команда видна в `get teams` (PRD §6.1.8)."""
    cr = clite(["create", "team", "--name", "TC-6-list", "--output", "json"])
    team_id = json.loads(cr.stdout)["id"]
    ls = clite(["get", "teams", "--output", "json"])
    assert ls.returncode == 0, ls.stderr
    ids = [t["id"] for t in json.loads(ls.stdout)]
    assert team_id in ids


def test_TC_6_4_1_team_leave_last_member_cascade_delete(clite):
    """6.4.1+6.4.2 — leave последнего участника → команда удалена; get → 404."""
    cr = clite(["create", "team", "--name", "TC-6.4-leave", "--output", "json"])
    team_id = json.loads(cr.stdout)["id"]
    lv = clite(["leave", "team", team_id, "--output", "json"])
    assert lv.returncode == 0, lv.stderr
    got = clite(["get", "team", team_id, "--output", "json"])
    assert got.returncode == 1, got.stderr


@pytest.mark.skip(reason="требует AUTH_MODE=jwt + auth-svc: gRPC резолв email→user_id")
def test_TC_6_2_1_add_member_to_team_positive() -> None:
    """6.2.1 — `add member <team> --email E --perm P`."""


@pytest.mark.skip(reason="требует второго пользователя")
def test_TC_6_3_1_add_member_without_permission() -> None:
    """6.3.1 — без manage_member_permissions → exit 4."""


@pytest.mark.skip(reason="требует второго пользователя")
def test_TC_6_3_2_grant_above_self() -> None:
    """6.3.2 — `--perm` выше своих → exit 4."""
