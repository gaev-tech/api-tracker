from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

_USER_ID_LEN = 40  # SHA1 hex (ARCH §3.5.0)


class Base(DeclarativeBase):
    pass


class SessionKind(StrEnum):
    BROWSER = "browser"
    CLI = "cli"


def _utcnow() -> datetime:
    return datetime.now(UTC)


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(_USER_ID_LEN), primary_key=True)
    email: Mapped[str] = mapped_column(
        String(320), unique=True, index=True, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )


class MagicToken(Base):
    """architecture.md §3.6.2 — magic-link click flow.

    Колонки:
        token_hash         — hash(plaintext-token из URL)
        email              — для кого выписан
        login_session_id   — внешний идентификатор сессии входа, по нему
                             CLI делает long-poll (ARCH §4.2.4)
        expires_at         — TTL 15 мин (ARCH §4.2.1)
        confirmed_at       — момент клика по ссылке (ARCH §4.2.3)
        delivered_at       — момент первой 200-выдачи на poll (ARCH §4.2.4.2)
    """

    __tablename__ = "magic_tokens"

    token_hash: Mapped[str] = mapped_column(String(128), primary_key=True)
    email: Mapped[str] = mapped_column(String(320), nullable=False, index=True)
    login_session_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), nullable=False, unique=True, default=uuid4
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    confirmed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    delivered_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )

    __table_args__ = (Index("ix_magic_tokens_email_expires", "email", "expires_at"),)


class RefreshToken(Base):
    """architecture.md §3.6.3 — refresh_tokens.

    Хранится hash (refresh token обрабатывается opaque-строкой, в БД hex SHA256).
    Поля по ARCH: id, user_id, kind, label, created_at, revoked_at, expires_at.
    """

    __tablename__ = "refresh_tokens"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    token_hash: Mapped[str] = mapped_column(
        String(128), unique=True, index=True, nullable=False
    )
    user_id: Mapped[str] = mapped_column(
        String(_USER_ID_LEN),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    kind: Mapped[SessionKind] = mapped_column(String(20), nullable=False)
    label: Mapped[str] = mapped_column(String(200), default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    __table_args__ = (Index("ix_refresh_tokens_user_revoked", "user_id", "revoked_at"),)


class Session(Base):
    """architecture.md §3.6.4 — sessions(refresh_token_id, last_seen_at, user_agent)."""

    __tablename__ = "sessions"

    refresh_token_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("refresh_tokens.id", ondelete="CASCADE"),
        primary_key=True,
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    user_agent: Mapped[str] = mapped_column(String(500), default="", nullable=False)


class CliAuthCode(Base):
    """architecture.md §3.6.5 — cli_auth_codes.

    Используется в Pattern A (local callback): браузер генерит code,
    CLI обменивает code+code_verifier на токены (PKCE).
    """

    __tablename__ = "cli_auth_codes"

    state: Mapped[str] = mapped_column(String(128), primary_key=True)
    code_challenge: Mapped[str] = mapped_column(String(128), nullable=False)
    code_hash: Mapped[str | None] = mapped_column(
        String(128), nullable=True, unique=True
    )
    code_used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    user_id: Mapped[str | None] = mapped_column(
        String(_USER_ID_LEN),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )


class DeviceCode(Base):
    """architecture.md §3.6.6 — device_codes.

    Pattern B (device-code fallback): CLI получает device_code+user_code,
    пользователь approves в браузере, CLI poll-ит и получает токен.
    """

    __tablename__ = "device_codes"

    device_code: Mapped[str] = mapped_column(String(128), primary_key=True)
    user_code: Mapped[str] = mapped_column(
        String(20), unique=True, index=True, nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    user_id: Mapped[str | None] = mapped_column(
        String(_USER_ID_LEN),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=True,
    )
    approved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
