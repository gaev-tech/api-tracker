"""TC 4.x — clite get log (verb-first, v2.0.0)."""

from __future__ import annotations

import json

import pytest


def test_TC_4_3_1_log_me_empty_ok(clite):
    """4.3.1 — `get log --user me` → exit 0, страница (может быть пустой)."""
    r = clite(["get", "log", "--user", "me", "--output", "json"])
    assert r.returncode == 0, r.stderr
    data = json.loads(r.stdout)
    assert "items" in data and isinstance(data["items"], list)


def test_TC_4_3_1_log_me_records_after_actions(clite, mk_task):
    """4.3.1 — после действий в log --user me появляются события."""
    mk_task("TC-4.3.1-event")
    r = clite(["get", "log", "--user", "me", "--output", "json"])
    assert r.returncode == 0, r.stderr
    assert len(json.loads(r.stdout)["items"]) >= 1


def test_TC_4_3_1_log_self_email_via_cache(clite):
    r = clite(["get", "log", "--user", "solo@local", "--output", "json"])
    assert r.returncode == 0, r.stderr


@pytest.mark.skip(reason="требует AUTH_MODE=jwt + auth-svc")
def test_TC_4_3_2_log_other_user_visibility_filter() -> None:
    """4.3.2 — события другого пользователя, только видимые."""


@pytest.mark.skip(reason="требует AUTH_MODE=jwt + auth-svc")
def test_TC_4_4_1_log_unknown_email_returns_exit_1() -> None:
    """4.4.1 — email несуществующего пользователя → exit 1."""
