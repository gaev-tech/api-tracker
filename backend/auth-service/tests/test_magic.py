"""Тесты magic-link flow (M2.2)."""

from unittest.mock import patch

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from auth_service.models import MagicToken

pytestmark = pytest.mark.asyncio


_SENT_EMAILS: list[tuple[str, str, str]] = []


async def _fake_send(to: str, subject: str, body: str) -> None:
    _SENT_EMAILS.append((to, subject, body))


def _extract_token(body: str) -> str:
    for line in body.splitlines():
        if "token=" in line:
            return line.split("token=", 1)[1].split("&")[0]
    raise AssertionError("token not found in email body")


@pytest.fixture(autouse=True)
def clear_email_log() -> None:
    _SENT_EMAILS.clear()


async def test_magic_start_creates_token(client: AsyncClient) -> None:
    with patch("auth_service.routers.magic.send_email", new=_fake_send):
        r = await client.post(
            "/auth/magic/start", json={"email": "user@example.com", "intent": "browser"}
        )
    assert r.status_code == 202
    body = r.json()
    assert body["sent"] is True and body["email"] == "user@example.com"
    assert len(_SENT_EMAILS) == 1


async def test_magic_verify_creates_user_and_returns_tokens(client: AsyncClient) -> None:
    with patch("auth_service.routers.magic.send_email", new=_fake_send):
        await client.post(
            "/auth/magic/start", json={"email": "new@example.com", "intent": "browser"}
        )
    token = _extract_token(_SENT_EMAILS[-1][2])

    r = await client.post("/auth/magic/verify", json={"token": token, "intent": "browser"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["user_email"] == "new@example.com"
    assert body["access_token"] and body["refresh_token"]
    assert body["token_type"] == "Bearer" and body["expires_in"] > 0


async def test_magic_verify_invalid_token(client: AsyncClient) -> None:
    r = await client.post("/auth/magic/verify", json={"token": "garbage", "intent": "browser"})
    assert r.status_code == 400


async def test_magic_verify_intent_mismatch(client: AsyncClient) -> None:
    with patch("auth_service.routers.magic.send_email", new=_fake_send):
        await client.post("/auth/magic/start", json={"email": "x@example.com", "intent": "browser"})
    token = _extract_token(_SENT_EMAILS[-1][2])
    r = await client.post("/auth/magic/verify", json={"token": token, "intent": "cli"})
    assert r.status_code == 400


async def test_magic_verify_marks_used(client: AsyncClient, session: AsyncSession) -> None:
    with patch("auth_service.routers.magic.send_email", new=_fake_send):
        await client.post(
            "/auth/magic/start", json={"email": "used@example.com", "intent": "browser"}
        )
    token = _extract_token(_SENT_EMAILS[-1][2])
    await client.post("/auth/magic/verify", json={"token": token, "intent": "browser"})

    # Повторная верификация должна провалиться.
    r2 = await client.post("/auth/magic/verify", json={"token": token, "intent": "browser"})
    assert r2.status_code == 400

    # В БД used_at установлен.
    result = await session.execute(select(MagicToken))
    records = result.scalars().all()
    assert any(r.used_at is not None for r in records)
