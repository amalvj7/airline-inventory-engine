from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str
    test_database_url: str | None = None
    log_level: str = "INFO"
    db_echo: bool = False
    db_pool_size: int = 20
    db_max_overflow: int = 10
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    @field_validator("database_url", "test_database_url", mode="before")
    @classmethod
    def _use_psycopg_driver(cls, url: str | None) -> str | None:
        """Managed Postgres hands out ``postgres://`` (a legacy alias SQLAlchemy 2
        dropped) or driverless ``postgresql://`` (which SQLAlchemy resolves to
        psycopg2, not installed). Both must become ``postgresql+psycopg://``."""
        if url is None:
            return url
        for legacy in ("postgres://", "postgresql://"):
            if url.startswith(legacy):
                return "postgresql+psycopg://" + url[len(legacy):]
        return url

    @property
    def cors_origin_list(self) -> list[str]:
        """Comma-separated in the environment; a list for CORSMiddleware.

        Kept as a plain string because pydantic-settings would otherwise expect
        JSON in the env var for a list-typed field.
        """
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()