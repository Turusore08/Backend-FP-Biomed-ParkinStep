from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application runtime configuration loaded strictly from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: Literal["development", "staging", "production", "test"] = "development"
    app_name: str = "ParkinStep Companion API"
    app_version: str = "1.0.0"
    database_url: str = Field(..., min_length=1)
    jwt_secret_key: str = Field(..., min_length=32)
    jwt_algorithm: str = "HS256"
    jwt_access_token_ttl_sec: int = Field(default=900, ge=60, le=86400)
    jwt_refresh_token_ttl_days: int = Field(default=30, ge=1, le=365)
    auth_login_rate_limit_max_attempts: int = Field(default=10, ge=1, le=1000)
    auth_login_rate_limit_window_sec: int = Field(default=60, ge=1, le=3600)
    idempotency_ttl_hours: int = Field(default=168, ge=1, le=8760)
    ota_app_key: str = ""
    model_cdn_base_url: str = "https://models.parkinstep.example.org/bundles"
    max_video_upload_bytes: int = Field(default=31_457_280, ge=1024, le=104_857_600)
    video_temp_dir: str | None = None
    cloud_fallback_onnx_path: str | None = None
    cors_allowed_origins: list[str] = Field(default_factory=lambda: ["http://localhost:3000"])
    log_level: str = "INFO"

    @field_validator("jwt_secret_key")
    @classmethod
    def validate_secret_length(cls, value: str) -> str:
        if len(value.strip()) < 32:
            raise ValueError("JWT_SECRET_KEY must be at least 32 characters.")
        return value

    @model_validator(mode="after")
    def reject_placeholder_secret_in_production(self) -> "Settings":
        if self.app_env == "production" and self.jwt_secret_key.startswith("CHANGE_ME"):
            raise ValueError("Placeholder JWT_SECRET_KEY is forbidden in production.")
        return self


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return cached runtime settings loaded from environment."""
    return Settings()
