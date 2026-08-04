from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_env: str = "development"
    app_name: str = "独立教师工作台"
    app_timezone: str = "Asia/Shanghai"
    app_currency: str = "CNY"
    log_level: str = "INFO"
    database_url: str = (
        "postgresql+asyncpg://teacher_workspace:change-me-local-only@localhost:5432/"
        "teacher_workspace"
    )
    trusted_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["http://localhost:3000"]
    )
    session_secret: str = "development-only-replace-me-with-32-characters"
    session_cookie_name: str = "teacher_workspace_session"
    session_cookie_secure: bool = False
    session_ttl_hours: int = 168
    storage_backend: str = "local"
    local_storage_root: Path = Path("var/storage")
    max_upload_bytes: int = 20 * 1024 * 1024
    allowed_upload_mime_types: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: [
            "application/pdf",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "image/jpeg",
            "image/png",
            "text/plain",
        ]
    )
    ai_provider: Literal["mock", "openai", "deepseek"] = "mock"
    openai_api_key: str | None = None
    openai_model: str | None = None
    deepseek_api_key: str | None = None
    deepseek_model: str | None = None
    deepseek_base_url: str = "https://api.deepseek.com"
    ai_temperature: float | None = None
    ai_max_output_tokens: int = 8192
    worker_id: str = "local-worker"
    worker_poll_seconds: float = 2.0
    job_lease_seconds: int = 60
    job_max_attempts: int = 3

    @field_validator("trusted_origins", "allowed_upload_mime_types", mode="before")
    @classmethod
    def parse_comma_separated(cls, value: object) -> object:
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @field_validator("session_secret")
    @classmethod
    def validate_session_secret(cls, value: str) -> str:
        if len(value) < 32:
            raise ValueError("SESSION_SECRET must contain at least 32 characters")
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
