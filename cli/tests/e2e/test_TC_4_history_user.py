"""TC 4.3.x / 4.4.x — clite history user. См. specs/cli-test-cases.md §4.3, §4.4.

В AUTH_MODE=disabled (текущий harness) единственный пользователь — solo@local.
Полный мульти-юзер flow тестируется в отдельной session с auth-svc + AUTH_MODE=jwt.
"""

from __future__ import annotations

import json

import pytest


def test_TC_4_3_1_history_user_me_empty_ok(clite):
    """4.3.1 — `clite history user me` → exit 0, страница (может быть пустой)."""
    r = clite(["history", "user", "me", "--output", "json"])
    assert r.returncode == 0, r.stderr
    data = json.loads(r.stdout)
    assert "items" in data
    assert isinstance(data["items"], list)


def test_TC_4_3_1_history_user_me_records_after_actions(clite):
    """4.3.1 — после действий пользователя в `history user me` появляются события."""
    created = clite(["task", "create", "--title", "TC-4.3.1-event", "--output", "json"])
    assert created.returncode == 0, created.stderr

    r = clite(["history", "user", "me", "--output", "json"])
    assert r.returncode == 0, r.stderr
    data = json.loads(r.stdout)
    assert len(data["items"]) >= 1


def test_TC_4_3_1_history_user_self_email_via_cache(clite):
    """4.3.1 (path coverage) — own email вместо `me` → exit 0
    (резолв через локальный кеш tasks.users, без gRPC).
    """
    r = clite(["history", "user", "solo@local", "--output", "json"])
    assert r.returncode == 0, r.stderr
    data = json.loads(r.stdout)
    assert "items" in data


@pytest.mark.skip(
    reason="требует AUTH_MODE=jwt + auth-svc: фильтр видимости (ARCH §10.2.2)"
)
def test_TC_4_3_2_history_other_user_visibility_filter() -> None:
    """4.3.2 — события другого пользователя, только по доступным мне задачам."""


@pytest.mark.skip(
    reason="требует AUTH_MODE=jwt + auth-svc: gRPC GetUserByEmail для NOT_FOUND"
)
def test_TC_4_4_1_history_unknown_email_returns_exit_1() -> None:
    """4.4.1 — email несуществующего пользователя → exit 1."""
