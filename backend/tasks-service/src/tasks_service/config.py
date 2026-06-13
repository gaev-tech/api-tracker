from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    auth_mode: str = Field(default="disabled", description="disabled (M0-M1) или jwt (M2+)")
    solo_user_email: str = Field(
        default="solo@local", description="email одиночного пользователя в M0-M1"
    )
    database_url: str = Field(
        default="postgresql+asyncpg://tasks_app:postgres@localhost:5432/tasks",
        description="async DSN, схема postgresql+asyncpg",
    )
    sync_database_url: str = Field(
        default="",
        description="sync DSN для Alembic; вычисляется из database_url если пуст",
    )

    @property
    def alembic_url(self) -> str:
        if self.sync_database_url:
            return self.sync_database_url
        return self.database_url.replace("postgresql+asyncpg://", "postgresql+psycopg2://")


settings = Settings()
