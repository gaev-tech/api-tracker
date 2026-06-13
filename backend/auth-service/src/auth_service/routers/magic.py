"""Magic-link REST endpoints (architecture.md §4.2)."""

from fastapi import APIRouter, HTTPException, Request, status

from auth_service.deps import SessionDep
from auth_service.email_sender import magic_link_email_body, send_email
from auth_service.models import SessionKind
from auth_service.schemas import (
    MagicStartRequest,
    MagicStartResponse,
    MagicVerifyRequest,
    MagicVerifyResponse,
)
from auth_service.services.magic import (
    MagicTokenError,
    build_magic_link,
    issue_magic_token,
    verify_magic_token,
)
from auth_service.services.sessions import create_session
from auth_service.services.users import get_or_create_user

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post(
    "/magic/start",
    response_model=MagicStartResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def magic_start(
    payload: MagicStartRequest, session: SessionDep
) -> MagicStartResponse:
    """Создаёт magic-token и отправляет письмо на email пользователя."""
    email = str(payload.email).lower()
    token = await issue_magic_token(session, email=email, intent=payload.intent)
    link = build_magic_link(token, payload.intent)
    await send_email(
        to=email,
        subject="apitracker.ru — вход по ссылке",
        body=magic_link_email_body(link),
    )
    return MagicStartResponse(sent=True, email=email)


@router.post("/magic/verify", response_model=MagicVerifyResponse)
async def magic_verify(
    payload: MagicVerifyRequest, session: SessionDep, request: Request
) -> MagicVerifyResponse:
    """Верифицирует magic-token, создаёт пользователя если нет, выдаёт сессию."""
    try:
        email = await verify_magic_token(
            session, token=payload.token, intent=payload.intent
        )
    except MagicTokenError as e:
        raise HTTPException(status_code=400, detail=f"invalid magic token: {e}") from e
    user = await get_or_create_user(session, email=email)
    kind = SessionKind.BROWSER if payload.intent.value == "browser" else SessionKind.CLI
    user_agent = request.headers.get("user-agent", "")[:500]
    access, refresh, ttl = await create_session(
        session, user=user, kind=kind, user_agent=user_agent
    )
    return MagicVerifyResponse(
        access_token=access,
        refresh_token=refresh,
        expires_in=ttl,
        user_email=user.email,
    )
