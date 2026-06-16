"""Magic-link click-flow REST endpoints (architecture.md §4.2)."""

from uuid import UUID

from fastapi import APIRouter, HTTPException, Request, Response, status
from fastapi.responses import HTMLResponse

from auth_service.config import settings
from auth_service.deps import SessionDep
from auth_service.email_sender import magic_link_email_body, send_email
from auth_service.schemas import (
    MagicPollDelivered,
    MagicPollPending,
    MagicStartRequest,
    MagicStartResponse,
)
from auth_service.services.magic import (
    MagicTokenError,
    build_magic_link,
    confirm_magic_token,
    issue_magic_token,
    poll_login_session,
)

router = APIRouter(prefix="/auth", tags=["auth"])


_CONFIRM_OK_HTML = """<!doctype html>
<html lang="ru"><head><meta charset="utf-8"><title>apitracker.ru</title></head>
<body style="font-family:system-ui,sans-serif;max-width:480px;margin:4rem auto;
text-align:center"><h1>✓ Сессия подтверждена</h1>
<p>Вернитесь в терминал — CLI завершит вход автоматически.</p>
</body></html>"""


_CONFIRM_EXPIRED_HTML = """<!doctype html>
<html lang="ru"><head><meta charset="utf-8"><title>apitracker.ru</title></head>
<body style="font-family:system-ui,sans-serif;max-width:480px;margin:4rem auto;
text-align:center"><h1>Ссылка истекла</h1>
<p>Запустите <code>clite login</code> повторно.</p>
</body></html>"""


@router.post(
    "/magic/start",
    response_model=MagicStartResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def magic_start(
    payload: MagicStartRequest, session: SessionDep
) -> MagicStartResponse:
    """ARCH §4.2.1 — выпустить magic-link, отправить письмо, вернуть session_id."""
    # ARCH §4.2.1.1: fail-fast при пустом SMTP_HOST, до записи токена в БД.
    if not settings.smtp_host:
        raise HTTPException(status_code=500, detail="email_delivery_not_configured")
    email = str(payload.email).lower()
    token, login_session_id = await issue_magic_token(session, email=email)
    link = build_magic_link(token)
    await send_email(
        to=email,
        subject="apitracker.ru — вход по ссылке",
        body=magic_link_email_body(link),
    )
    return MagicStartResponse(
        login_session_id=login_session_id,
        email=email,
        expires_in=settings.magic_token_ttl_seconds,
    )


@router.get("/magic/confirm")
async def magic_confirm(token: str, session: SessionDep) -> HTMLResponse:
    """ARCH §4.2.3 — клик по ссылке из email; отдаёт HTML 200 либо 410."""
    try:
        await confirm_magic_token(session, token=token)
    except MagicTokenError:
        return HTMLResponse(content=_CONFIRM_EXPIRED_HTML, status_code=410)
    return HTMLResponse(content=_CONFIRM_OK_HTML, status_code=200)


@router.get("/magic/poll/{login_session_id}")
async def magic_poll(
    login_session_id: UUID, session: SessionDep, request: Request, response: Response
) -> MagicPollPending | MagicPollDelivered:
    """ARCH §4.2.4 — long-poll, CLI вызывает в цикле."""
    user_agent = request.headers.get("user-agent", "")[:500]
    try:
        result = await poll_login_session(
            session, login_session_id=login_session_id, user_agent=user_agent
        )
    except MagicTokenError as e:
        msg = str(e)
        if msg == "not_found":
            raise HTTPException(status_code=404, detail="not_found") from e
        # expired или already_delivered → 410
        raise HTTPException(status_code=410, detail=msg) from e
    if result is None:
        response.status_code = status.HTTP_202_ACCEPTED
        return MagicPollPending()
    access, refresh, ttl, email = result
    return MagicPollDelivered(
        access_token=access,
        refresh_token=refresh,
        expires_in=ttl,
        user_email=email,
    )
