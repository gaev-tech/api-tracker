"""TC 5.x — clite login / logout / whoami. См. specs/cli-test-cases.md §5.

В AUTH_MODE=disabled (текущий harness) клиент работает без credentials
(SOLO_USER подставляется на стороне tasks-svc). Тесты §5 проверяют
clite-локальные хендлеры (logout/whoami без сети), полный login flow
требует auth-svc и тестируется в отдельной session с AUTH_MODE=jwt.
"""

from __future__ import annotations


def test_TC_5_3_2_logout_idempotent_without_credentials(clite_offline):
    """5.3.2 — `clite logout` без credentials → exit 0, stderr `Не были залогинены`."""
    r = clite_offline(["logout"])
    assert r.returncode == 0
    assert "Не были залогинены" in r.stderr or "already" in r.stderr.lower()


def test_TC_5_5_1_whoami_without_credentials(clite_offline):
    """5.5.1 — `clite whoami` без credentials → exit 3."""
    r = clite_offline(["whoami"])
    assert r.returncode == 3
    assert "залогинены" in r.stderr.lower() or "authenticated" in r.stderr.lower()
