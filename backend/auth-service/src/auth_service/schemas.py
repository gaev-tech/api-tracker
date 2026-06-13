from pydantic import BaseModel, ConfigDict, EmailStr

from auth_service.models import MagicTokenIntent


class MagicStartRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr
    intent: MagicTokenIntent = MagicTokenIntent.BROWSER


class MagicStartResponse(BaseModel):
    sent: bool
    email: str


class MagicVerifyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    token: str
    intent: MagicTokenIntent = MagicTokenIntent.BROWSER


class SessionTokens(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "Bearer"  # noqa: S105 — OAuth-стандартное значение, не пароль
    expires_in: int


class MagicVerifyResponse(SessionTokens):
    user_email: str
