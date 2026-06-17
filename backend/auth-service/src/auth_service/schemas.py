from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class MagicStartRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr


class MagicStartResponse(BaseModel):
    """ARCH §4.2.1 — start magic-link flow, return long-poll session id."""

    login_session_id: UUID
    email: str
    expires_in: int


class SessionTokens(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "Bearer"  # noqa: S105 — OAuth-стандартное значение, не пароль
    expires_in: int


class MagicPollPending(BaseModel):
    """ARCH §4.2.4.1 — пользователь ещё не кликнул по ссылке."""

    status: str = "pending"


class MagicPollDelivered(SessionTokens):
    """ARCH §4.2.4.2 — токены отдаются однократно при первом 200."""

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


# === tariff (M5 — Free only; tariff.md §15.1, §16.2) ===


class TariffCatalogEntry(BaseModel):
    """Одна строка каталога тарифов (tariff.md §2).

    В M5 каталог содержит только Free; `monthly_rub`/`annual_rub` отсутствуют.
    `null` в `task_shares`/`projects`/`teams` (M6 unlimited) — здесь невозможен.
    """

    tier: str
    task_shares: int | None
    projects: int | None
    teams: int | None


class TariffCatalog(BaseModel):
    entries: list[TariffCatalogEntry]


class TariffState(BaseModel):
    """Состояние тарифа текущего пользователя (tariff.md §15.10, M5-вариант).

    M5: только tariff + usage_*/limit_* для трёх метрик. Поля
    `auto_renew`, `tariff_until`, `pro_bank_days`, `payment_method_*` — M6
    (tariff.md §15.10.1, §15.10.5; IPLAN §7.2.2.3).
    """

    tariff: str
    usage_task_shares: int
    limit_task_shares: int | None
    usage_projects: int
    limit_projects: int | None
    usage_teams: int
    limit_teams: int | None
