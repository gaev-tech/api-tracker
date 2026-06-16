"""TC 5.x — clite account login / logout / me. См. specs/cli-test-cases.md §5.

M2.29: команды переименованы в `clite account login/logout/me` (раньше
flat login/logout/whoami).
"""

from __future__ import annotations


def test_TC_5_3_2_logout_idempotent_without_credentials(clite_offline):
    """5.3.2 — `clite account logout` без credentials → exit 0."""
    r = clite_offline(["account", "logout"])
    assert r.returncode == 0
    assert "Не были залогинены" in r.stderr or "already" in r.stderr.lower()


def test_TC_5_5_1_me_without_credentials(clite_offline):
    """5.5.1 — `clite account me` без credentials → exit 3."""
    r = clite_offline(["account", "me"])
    assert r.returncode == 3
    assert "залогинены" in r.stderr.lower() or "authenticated" in r.stderr.lower()
