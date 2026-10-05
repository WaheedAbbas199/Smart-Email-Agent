"""Application configuration loaded from environment variables / .env."""
from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=(".env", "../.env"), extra="ignore")

    app_env: Literal["development", "production", "test"] = "development"
    database_url: str = "sqlite:///./smart_email.db"

    # LLM
    llm_provider: Literal["auto", "gemini", "mock"] = "auto"
    gemini_api_key: str | None = None
    gemini_model: str ="gemini-3.8-flash"
    llm_timeout_seconds: float = 30.0
    llm_max_retries: int = 2

    # Email source
    demo_mode: bool = False
    max_email_chars: int = 8000

    # Google OAuth (Gmail)
    google_client_id: str | None = None
    google_client_secret: str | None = None
    google_redirect_uri: str = "http://localhost:8000/api/auth/google/callback"
    token_encryption_key: str | None = None  # Fernet key

    # HTTP
    cors_origins: str = "http://localhost:8000,http://127.0.0.1:8000"
    rate_limit_per_minute: int = 120

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
