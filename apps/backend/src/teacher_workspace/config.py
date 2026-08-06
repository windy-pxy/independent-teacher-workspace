import re
from functools import lru_cache
from ipaddress import ip_address
from pathlib import Path
from typing import Annotated, Literal
from urllib.parse import urlsplit

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_env: Literal["development", "test", "production"] = "development"
    app_name: str = "独立教师工作台"
    app_timezone: str = "Asia/Shanghai"
    app_currency: str = "CNY"
    app_domain: str = "teacher.example.invalid"
    log_level: str = "INFO"
    database_url: str = (
        "postgresql+asyncpg://teacher_workspace:change-me-local-only@localhost:5432/"
        "teacher_workspace"
    )
    trusted_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["http://localhost:3000"]
    )
    trusted_hosts: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["localhost", "127.0.0.1", "test", "testserver", "api"]
    )
    session_secret: str = "development-only-replace-me-with-32-characters"
    session_cookie_name: str = "teacher_workspace_session"
    session_cookie_secure: bool = False
    session_ttl_hours: int = 168
    login_max_failures: int = Field(default=5, ge=3, le=20)
    login_window_seconds: int = Field(default=900, ge=60, le=86400)
    login_lock_seconds: int = Field(default=900, ge=60, le=86400)
    storage_backend: Literal["local", "supabase"] = "local"
    local_storage_root: Path = Path("var/storage")
    supabase_url: str | None = None
    supabase_service_role_key: str | None = None
    supabase_storage_bucket: str = "teacher-workspace"
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
    vision_ai_provider: Literal["mock", "openai"] = "mock"
    vision_openai_model: str | None = None
    ai_temperature: float | None = None
    ai_max_output_tokens: int = 8192
    worker_id: str = "local-worker"
    worker_poll_seconds: float = 2.0
    job_lease_seconds: int = 60
    job_max_attempts: int = 3

    @field_validator(
        "trusted_origins", "trusted_hosts", "allowed_upload_mime_types", mode="before"
    )
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

    @model_validator(mode="after")
    def validate_production_security(self) -> "Settings":
        if self.app_env != "production":
            return self
        placeholder_secrets = {
            "development-only-replace-me-with-32-characters",
            "replace-with-at-least-32-random-characters",
        }
        if self.session_secret in placeholder_secrets or len(self.session_secret) < 48:
            raise ValueError("Production SESSION_SECRET must not use a documented placeholder")
        if not self.session_cookie_secure:
            raise ValueError("SESSION_COOKIE_SECURE must be true in production")
        if not self.trusted_origins or any(
            not origin.startswith("https://") for origin in self.trusted_origins
        ):
            raise ValueError("Production TRUSTED_ORIGINS must contain HTTPS origins only")
        if not self.trusted_hosts or "*" in self.trusted_hosts:
            raise ValueError("Production TRUSTED_HOSTS must be explicit")
        domain_is_ip = False
        try:
            ip_address(self.app_domain)
            domain_is_ip = True
        except ValueError:
            pass
        if (
            self.app_domain in {"localhost", "teacher.example.invalid"}
            or domain_is_ip
            or not all(
                re.fullmatch(r"[A-Za-z0-9-]{1,63}", label)
                and not label.startswith("-")
                and not label.endswith("-")
                for label in self.app_domain.split(".")
            )
            or f"https://{self.app_domain}" not in self.trusted_origins
        ):
            raise ValueError(
                "Production APP_DOMAIN must be a real hostname included in TRUSTED_ORIGINS"
            )
        database_password = urlsplit(self.database_url).password or ""
        if "change-me-local-only" in self.database_url or len(database_password) < 16:
            raise ValueError("Production DATABASE_URL must use a strong non-placeholder password")
        if self.storage_backend == "supabase" and (
            not self.supabase_url
            or not self.supabase_url.startswith("https://")
            or not self.supabase_service_role_key
        ):
            raise ValueError(
                "Supabase storage requires HTTPS SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY"
            )
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
