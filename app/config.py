from functools import lru_cache

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


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()