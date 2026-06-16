"""Тесты magic-link click flow (ARCH §4.2)."""

from unittest.mock import patch

import pytest
from httpx import AsyncClient

from auth_service.config import settings

pytestmark = pytest.mark.asyncio(loop_scope="session")


_SENT_EMAILS: list[tuple[str, str, str]] = []


async def _fake_send(to: str, subject: str, body: str) -> None:
    _SENT_EMAILS.append((to, subject, body))


def _extract_token(body: str) -> str:
    """Из тела письма достать plaintext-токен (URL: …/magic/confirm?token=<t>)."""
    for line in body.splitlines():
        if "token=" in line:
            return line.split("token=", 1)[1].split("&")[0].strip()
    raise AssertionError("token not found in email body")


@pytest.fixture(autouse=True)
def clear_email_log() -> None:
    _SENT_EMAILS.clear()


async def test_magic_start_creates_token_and_returns_session_id(
    client: AsyncClient,
) -> None:
    with patch("auth_service.routers.magic.send_email", new=_fake_send):
        r = await client.post("/auth/magic/start", json={"email": "user@example.com"})
    assert r.status_code == 202, r.text
    body = r.json()
    assert body["email"] == "user@example.com"
    assert body["login_session_id"]
    assert body["expires_in"] > 0
    assert len(_SENT_EMAILS) == 1


async def test_magic_start_500_when_smtp_not_configured(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """ARCH §4.2.1.1: пустой SMTP_HOST → 500 без записи токена в БД."""
    monkeypatch.setattr(settings, "smtp_host", "")
    r = await client.post("/auth/magic/start", json={"email": "x@example.com"})
    assert r.status_code == 500
    assert r.json()["detail"] == "email_delivery_not_configured"


async def test_magic_confirm_marks_token_and_creates_user(
    client: AsyncClient,
) -> None:
    """ARCH §4.2.3: клик по ссылке → HTML 200 и user в БД."""
    with patch("auth_service.routers.magic.send_email", new=_fake_send):
        await client.post("/auth/magic/start", json={"email": "click@example.com"})
    token = _extract_token(_SENT_EMAILS[-1][2])
    r = await client.get(f"/auth/magic/confirm?token={token}")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
    assert "Сессия подтверждена" in r.text


async def test_magic_confirm_invalid_token_returns_410(client: AsyncClient) -> None:
    r = await client.get("/auth/magic/confirm?token=garbage")
    assert r.status_code == 410
    assert "Ссылка истекла" in r.text


async def test_magic_confirm_second_click_returns_410(
    client: AsyncClient,
) -> None:
    """Повторный клик по той же ссылке → 410 (token already used)."""
    with patch("auth_service.routers.magic.send_email", new=_fake_send):
        await client.post("/auth/magic/start", json={"email": "twice@example.com"})
    token = _extract_token(_SENT_EMAILS[-1][2])
    first = await client.get(f"/auth/magic/confirm?token={token}")
    assert first.status_code == 200
    second = await client.get(f"/auth/magic/confirm?token={token}")
    assert second.status_code == 410


async def test_magic_poll_pending_then_delivered(client: AsyncClient) -> None:
    """ARCH §4.2.4.1 / §4.2.4.2 — pending до клика, 200 после."""
    with patch("auth_service.routers.magic.send_email", new=_fake_send):
        start = await client.post(
            "/auth/magic/start", json={"email": "poll@example.com"}
        )
    session_id = start.json()["login_session_id"]
    token = _extract_token(_SENT_EMAILS[-1][2])

    pending = await client.get(f"/auth/magic/poll/{session_id}")
    assert pending.status_code == 202
    assert pending.json()["status"] == "pending"

    await client.get(f"/auth/magic/confirm?token={token}")

    delivered = await client.get(f"/auth/magic/poll/{session_id}")
    assert delivered.status_code == 200, delivered.text
    body = delivered.json()
    assert body["user_email"] == "poll@example.com"
    assert body["access_token"] and body["refresh_token"]
    assert body["expires_in"] > 0

    # Повторный poll после выдачи → 410 (ARCH §4.2.4.2 "Возврат однократный").
    again = await client.get(f"/auth/magic/poll/{session_id}")
    assert again.status_code == 410


async def test_magic_poll_unknown_session_returns_404(client: AsyncClient) -> None:
    r = await client.get("/auth/magic/poll/11111111-1111-1111-1111-111111111111")
    assert r.status_code == 404
