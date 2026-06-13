"""CLI handoff REST endpoints (architecture.md §4.3, §4.4, §4.6)."""

from fastapi import APIRouter, HTTPException, Request

from auth_service.auth_dep import AuthenticatedUserDep
from auth_service.deps import SessionDep
from auth_service.models import SessionKind
from auth_service.schemas import (
    CliCodeRequest,
    CliCodeResponse,
    CliExchangeRequest,
    CliRefreshRequest,
    DeviceApproveRequest,
    DevicePollRequest,
    DeviceStartResponse,
    SessionTokens,
)
from auth_service.services.cli_handoff import (
    AuthorizationPending,
    HandoffError,
    approve_device,
    exchange_cli_code,
    issue_cli_code,
    poll_device,
    start_device_flow,
)
from auth_service.services.refresh import RefreshError, rotate_refresh
from auth_service.services.sessions import create_session
from auth_service.services.users import get_user_by_id

router = APIRouter(prefix="/auth/cli", tags=["cli-handoff"])


# === Pattern A: local-callback / PKCE ===


@router.post("/code", response_model=CliCodeResponse)
async def issue_code(
    payload: CliCodeRequest,
    session: SessionDep,
    user: AuthenticatedUserDep,
) -> CliCodeResponse:
    """Auth-client после успешного логина и пользовательского подтверждения
    обменивает (state, code_challenge) на одноразовый code, привязанный к user.
    """
    try:
        code = await issue_cli_code(
            session,
            user_id=user.id,
            state=payload.state,
            code_challenge=payload.code_challenge,
        )
    except HandoffError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return CliCodeResponse(code=code)


@router.post("/exchange", response_model=SessionTokens)
async def exchange_code(
    payload: CliExchangeRequest, session: SessionDep, request: Request
) -> SessionTokens:
    """CLI обменивает code+code_verifier на access+refresh токены."""
    try:
        user_id = await exchange_cli_code(
            session, code=payload.code, code_verifier=payload.code_verifier
        )
    except HandoffError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    user = await get_user_by_id(session, user_id)
    if user is None:
        raise HTTPException(status_code=400, detail="user not found")
    access, refresh, ttl = await create_session(
        session,
        user=user,
        kind=SessionKind.CLI,
        user_agent=request.headers.get("user-agent", "")[:500],
    )
    return SessionTokens(access_token=access, refresh_token=refresh, expires_in=ttl)


# === Pattern B: device code ===


@router.post("/device-start", response_model=DeviceStartResponse)
async def device_start(session: SessionDep) -> DeviceStartResponse:
    data = await start_device_flow(session)
    return DeviceStartResponse(**data)  # type: ignore[arg-type]


@router.post("/device-approve")
async def device_approve(
    payload: DeviceApproveRequest, session: SessionDep, user: AuthenticatedUserDep
) -> dict[str, bool]:
    try:
        await approve_device(session, user_code=payload.user_code, user_id=user.id)
    except HandoffError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return {"ok": True}


@router.post("/device-poll", response_model=SessionTokens)
async def device_poll(
    payload: DevicePollRequest, session: SessionDep, request: Request
) -> SessionTokens:
    try:
        user_id = await poll_device(session, device_code=payload.device_code)
    except AuthorizationPending as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except HandoffError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    user = await get_user_by_id(session, user_id)
    if user is None:
        raise HTTPException(status_code=400, detail="user not found")
    access, refresh, ttl = await create_session(
        session,
        user=user,
        kind=SessionKind.CLI,
        user_agent=request.headers.get("user-agent", "")[:500],
    )
    return SessionTokens(access_token=access, refresh_token=refresh, expires_in=ttl)


# === Refresh flow (CLI) ===


@router.post("/refresh", response_model=SessionTokens)
async def refresh(
    payload: CliRefreshRequest, session: SessionDep, request: Request
) -> SessionTokens:
    try:
        access, refresh_new, ttl = await rotate_refresh(
            session,
            refresh_plain=payload.refresh_token,
            user_agent=request.headers.get("user-agent", "")[:500],
        )
    except RefreshError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return SessionTokens(access_token=access, refresh_token=refresh_new, expires_in=ttl)
