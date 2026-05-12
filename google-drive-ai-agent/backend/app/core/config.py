"""Application configuration loaded from environment variables."""

from functools import lru_cache
from pathlib import Path
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central settings for the FastAPI application and agent."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    openai_api_key: str = Field(..., alias="OPENAI_API_KEY")
    google_service_account_file: str = Field(
        ...,
        alias="GOOGLE_SERVICE_ACCOUNT_FILE",
        description="Path to the service account JSON key file.",
    )
    google_drive_folder_id: str = Field(
        ...,
        alias="GOOGLE_DRIVE_FOLDER_ID",
        description="Drive folder ID to scope all searches.",
    )

    openai_model: str = Field(default="gpt-4o-mini", alias="OPENAI_MODEL")
    cors_origins: str = Field(
        default="http://localhost:8501,http://127.0.0.1:8501",
        alias="CORS_ORIGINS",
    )
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    drive_page_size: int = Field(default=25, alias="DRIVE_PAGE_SIZE")
    enable_semantic_rerank: bool = Field(
        default=True,
        alias="ENABLE_SEMANTIC_RERANK",
        description="Re-rank Drive results by embedding similarity to the user query.",
    )
    backend_public_url: str = Field(
        default="http://localhost:8000",
        alias="BACKEND_PUBLIC_URL",
    )

    @property
    def service_account_path(self) -> Path:
        return Path(self.google_service_account_file).expanduser().resolve()

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    """Return cached settings instance."""
    return Settings()


def clear_settings_cache() -> None:
    """Clear settings cache (useful in tests)."""
    get_settings.cache_clear()
