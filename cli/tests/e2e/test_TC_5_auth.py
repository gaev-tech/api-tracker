"""TC 5.x — clite login / logout / me (top-level, v2.0.0)."""

from __future__ import annotations


def test_TC_5_3_2_logout_idempotent_without_credentials(clite_offline):
    """5.3.2 — `clite logout` без credentials → exit 0."""
    r = clite_offline(["logout"])
    assert r.returncode == 0
    assert "Не были залогинены" in r.stderr or "already" in r.stderr.lower()


def test_TC_5_5_1_me_without_credentials(clite_offline):
    """5.5.1 — `clite me` без credentials → exit 3."""
    r = clite_offline(["me"])
    assert r.returncode == 3
    assert "залогинены" in r.stderr.lower() or "authenticated" in r.stderr.lower()
