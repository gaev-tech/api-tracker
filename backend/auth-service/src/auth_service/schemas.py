from pydantic import BaseModel, ConfigDict, EmailStr, Field

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


class CliCodeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    state: str = Field(min_length=8, max_length=128)
    code_challenge: str = Field(min_length=8, max_length=128)


class CliCodeResponse(BaseModel):
    code: str


class CliExchangeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    code_verifier: str = Field(min_length=8, max_length=128)


class DeviceStartResponse(BaseModel):
    device_code: str
    user_code: str
    verification_url: str
    interval: int
    expires_in: int


class DeviceApproveRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_code: str = Field(min_length=8, max_length=20)


class DevicePollRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    device_code: str


class CliRefreshRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    refresh_token: str
