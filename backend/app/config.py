"""Settings, read from the environment (or a .env file in local dev)."""

from functools import lru_cache
from typing import Any

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # --- Storage -----------------------------------------------------------
    database_url: str = "sqlite:///./kaki.db"

    # --- Auth --------------------------------------------------------------
    secret_key: str = "insecure-development-key-do-not-ship"
    access_token_ttl_minutes: int = 30
    refresh_token_ttl_days: int = 30

    # --- Telegram ingestion -------------------------------------------------
    telegram_api_id: int | None = None
    telegram_api_hash: str = ""
    telegram_chat: str = "sg_badminton"
    telegram_topic_id: int | None = None
    telegram_session_path: str = "./data/kaki.session"
    backfill_limit: int = 5000

    # --- Web ---------------------------------------------------------------
    cors_origins: str = "http://localhost:5173"
    environment: str = "development"

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def is_production(self) -> bool:
        return self.environment.lower() in {"production", "prod"}

    @property
    def telegram_configured(self) -> bool:
        return bool(self.telegram_api_id and self.telegram_api_hash)

    @field_validator("telegram_api_id", "telegram_topic_id", mode="before")
    @classmethod
    def _blank_means_unset(cls, value: Any) -> Any:
        """An unfilled line in .env (`TELEGRAM_API_ID=`) arrives as an empty
        string, not as absent. Without this the API refuses to start until you
        have Telegram credentials, which makes it impossible to run the web half
        while you are still setting the other half up."""
        if isinstance(value, str) and not value.strip():
            return None
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
