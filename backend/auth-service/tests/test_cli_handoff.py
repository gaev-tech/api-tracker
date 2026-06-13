"""Тесты CLI handoff: Pattern A (PKCE), Pattern B (device code), refresh."""

import base64
import hashlib
import secrets
from unittest.mock import patch

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio(loop_scope="session")

_SENT_EMAILS: list[tuple[str, str, str]] = []


async def _fake_send(to: str, subject: str, body: str) -> None:
    _SENT_EMAILS.append((to, subject, body))


def _extract_token(body: str) -> str:
    for line in body.splitlines():
        if "token=" in line:
            return line.split("token=", 1)[1].split("&")[0]
    raise AssertionError("token not found")


@pytest.fixture(autouse=True)
def clear_email_log() -> None:
    _SENT_EMAILS.clear()


async def _bootstrap_session(client: AsyncClient, email: str) -> dict[str, str]:
    """Создаёт пользователя через magic-link и возвращает access+refresh."""
    with patch("auth_service.routers.magic.send_email", new=_fake_send):
        await client.post(
            "/auth/magic/start", json={"email": email, "intent": "browser"}
        )
    token = _extract_token(_SENT_EMAILS[-1][2])
    r = await client.post(
        "/auth/magic/verify", json={"token": token, "intent": "browser"}
    )
    return r.json()


def _make_pkce_pair() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(48)
    challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode("utf-8")).digest())
        .decode()
        .rstrip("=")
    )
    return verifier, challenge


# === Pattern A — PKCE ===


async def test_cli_code_requires_bearer(client: AsyncClient) -> None:
    r = await client.post(
        "/auth/cli/code", json={"state": "S" * 16, "code_challenge": "C" * 32}
    )
    assert r.status_code == 401


async def test_cli_pkce_full_flow(client: AsyncClient) -> None:
    tokens = await _bootstrap_session(client, "pkce-user@example.com")
    state = secrets.token_urlsafe(24)
    verifier, challenge = _make_pkce_pair()

    r = await client.post(
        "/auth/cli/code",
        json={"state": state, "code_challenge": challenge},
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )
    assert r.status_code == 200, r.text
    code = r.json()["code"]

    r2 = await client.post(
        "/auth/cli/exchange", json={"code": code, "code_verifier": verifier}
    )
    assert r2.status_code == 200, r2.text
    body = r2.json()
    assert body["access_token"] and body["refresh_token"]


async def test_cli_exchange_wrong_verifier(client: AsyncClient) -> None:
    tokens = await _bootstrap_session(client, "wrong-verifier@example.com")
    state = secrets.token_urlsafe(24)
    _verifier, challenge = _make_pkce_pair()

    code = (
        await client.post(
            "/auth/cli/code",
            json={"state": state, "code_challenge": challenge},
            headers={"Authorization": f"Bearer {tokens['access_token']}"},
        )
    ).json()["code"]

    r = await client.post(
        "/auth/cli/exchange",
        json={"code": code, "code_verifier": "wrong-verifier-12345678"},
    )
    assert r.status_code == 400


async def test_cli_code_reused_state_used(client: AsyncClient) -> None:
    tokens = await _bootstrap_session(client, "reuse@example.com")
    state = secrets.token_urlsafe(24)
    verifier, challenge = _make_pkce_pair()

    code = (
        await client.post(
            "/auth/cli/code",
            json={"state": state, "code_challenge": challenge},
            headers={"Authorization": f"Bearer {tokens['access_token']}"},
        )
    ).json()["code"]
    await client.post(
        "/auth/cli/exchange", json={"code": code, "code_verifier": verifier}
    )
    r = await client.post(
        "/auth/cli/exchange", json={"code": code, "code_verifier": verifier}
    )
    assert r.status_code == 400


# === Pattern B — device code ===


async def test_device_flow(client: AsyncClient) -> None:
    tokens = await _bootstrap_session(client, "device@example.com")
    r = await client.post("/auth/cli/device-start")
    assert r.status_code == 200
    start = r.json()
    assert start["user_code"] and start["device_code"]

    # До approve poll возвращает 400 authorization_pending.
    pending = await client.post(
        "/auth/cli/device-poll", json={"device_code": start["device_code"]}
    )
    assert pending.status_code == 400
    assert "authorization_pending" in pending.json()["detail"]

    # Approve под Bearer.
    approve = await client.post(
        "/auth/cli/device-approve",
        json={"user_code": start["user_code"]},
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )
    assert approve.status_code == 200

    # Теперь poll возвращает токены.
    poll = await client.post(
        "/auth/cli/device-poll", json={"device_code": start["device_code"]}
    )
    assert poll.status_code == 200, poll.text
    assert poll.json()["access_token"]


# === Refresh ===


async def test_refresh_rotates(client: AsyncClient) -> None:
    tokens = await _bootstrap_session(client, "refresh@example.com")
    r = await client.post(
        "/auth/cli/refresh", json={"refresh_token": tokens["refresh_token"]}
    )
    assert r.status_code == 200
    new = r.json()
    assert new["refresh_token"] != tokens["refresh_token"]
    # Старый refresh больше не валиден.
    r2 = await client.post(
        "/auth/cli/refresh", json={"refresh_token": tokens["refresh_token"]}
    )
    assert r2.status_code == 400


async def test_refresh_invalid(client: AsyncClient) -> None:
    r = await client.post("/auth/cli/refresh", json={"refresh_token": "garbage"})
    assert r.status_code == 400
