"""TC 8.x — clite share. См. specs/cli-test-cases.md §8.

В AUTH_MODE=disabled позитивные share-set кейсы требуют gRPC резолва target email
к auth-svc — в текущем harness он недоступен. Здесь покрыт smoke на `share list`
для новой задачи; остальные кейсы скипаются и покрываются отдельной сессией с
AUTH_MODE=jwt + auth-svc.
"""

from __future__ import annotations

import json

import pytest


def test_TC_8_share_list_anchor_for_new_task(clite):
    """Smoke — у только что созданной задачи в user_shares лежит anchor-share
    создателя (PRD §6.6), team_shares пуст.
    """
    t = clite(["task", "create", "--title", "TC-8-share-target", "--output", "json"])
    task_id = json.loads(t.stdout)["id"]

    r = clite(["share", "list", task_id, "--output", "json"])
    assert r.returncode == 0, r.stderr
    data = json.loads(r.stdout)
    user_shares = data.get("user_shares", [])
    assert len(user_shares) == 1
    assert user_shares[0]["user_email"] == "solo@local"
    assert data.get("team_shares", []) == []


@pytest.mark.skip(reason="требует AUTH_MODE=jwt + auth-svc: gRPC резолв target email")
def test_TC_8_1_1_share_user_set_positive() -> None:
    """8.1.1 — `share user set --email --perms edit_title,edit_status` → exit 0."""


@pytest.mark.skip(reason="требует второго пользователя без права share")
def test_TC_8_2_1_share_user_set_without_share_perm() -> None:
    """8.2.1 — без права share на задаче → exit 4."""


@pytest.mark.skip(
    reason="требует AUTH_MODE=jwt + auth-svc для granter с меньшими правами"
)
def test_TC_8_2_2_share_grant_above_self() -> None:
    """8.2.2 — `--perms` выше своих → exit 4."""


@pytest.mark.skip(reason="требует AUTH_MODE=jwt + auth-svc: team-share через gRPC")
def test_TC_8_3_1_share_team_set_own_team() -> None:
    """8.3.1 — шаринг команде, в которой я состою → exit 0."""


@pytest.mark.skip(reason="требует второго пользователя в чужой команде")
def test_TC_8_4_1_share_team_set_foreign_team() -> None:
    """8.4.1 — шаринг команде, в которой я НЕ состою → exit 4 (PRD §6.7.1)."""


@pytest.mark.skip(reason="требует второго пользователя для self-revoke")
def test_TC_8_5_1_share_user_remove_self() -> None:
    """8.5.1 — `share user remove --self` → exit 0."""
