from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    database_url: str = Field(
        default="postgresql+asyncpg://postgres:postgres@localhost:5432/auth",
        description="async DSN, схема postgresql+asyncpg",
    )
    sync_database_url: str = Field(
        default="",
        description="sync DSN для Alembic; вычисляется из database_url если пуст",
    )
    public_base_url: str = Field(
        default="https://apitracker.ru",
        description="префикс для magic-link и cli handoff URL",
    )
    smtp_host: str = Field(default="")
    smtp_port: int = Field(default=587)
    smtp_user: str = Field(default="")
    smtp_password: str = Field(default="")
    smtp_from: str = Field(default="noreply@apitracker.ru")

    magic_token_ttl_seconds: int = Field(
        default=900, description="TTL magic-link токена, 15 мин"
    )
    access_token_ttl_seconds: int = Field(
        default=3600, description="JWT access TTL, 1 час"
    )
    refresh_token_ttl_seconds: int = Field(
        default=30 * 24 * 3600, description="refresh TTL, 30 дней"
    )
    cli_code_ttl_seconds: int = Field(
        default=300, description="CLI handoff code TTL, 5 мин"
    )
    device_code_ttl_seconds: int = Field(
        default=900, description="device code TTL, 15 мин"
    )

    jwt_private_key_b64: str = Field(
        default="", description="RS256 приватный ключ, base64"
    )
    jwt_public_key_b64: str = Field(
        default="", description="RS256 публичный ключ, base64"
    )
    jwt_issuer: str = Field(default="apitracker.ru")

    tasks_service_url: str = Field(
        default="http://tasks-svc:8080",
        description=(
            "Внутренний HTTP-адрес tasks-svc для M5 tariff usage_* (через "
            "/v1/internal/membership-counts/{user_id})."
        ),
    )
    internal_service_token: str = Field(
        default="",
        description="Shared secret для inter-service вызовов (см. tasks-svc).",
    )

    @property
    def alembic_url(self) -> str:
        if self.sync_database_url:
            return self.sync_database_url
        return self.database_url.replace(
            "postgresql+asyncpg://", "postgresql+psycopg2://"
        )


settings = Settings()
