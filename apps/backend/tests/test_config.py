import pytest
from pydantic import ValidationError

from teacher_workspace.config import Settings


def test_comma_separated_environment_lists(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TRUSTED_ORIGINS", "http://localhost:3000,https://teacher.example")
    monkeypatch.setenv("ALLOWED_UPLOAD_MIME_TYPES", "application/pdf,image/png")
    monkeypatch.setenv("TRUSTED_HOSTS", "localhost,api")
    settings = Settings(session_secret="x" * 32)
    assert settings.trusted_origins == ["http://localhost:3000", "https://teacher.example"]
    assert settings.allowed_upload_mime_types == ["application/pdf", "image/png"]
    assert settings.trusted_hosts == ["localhost", "api"]


def test_short_session_secret_is_rejected() -> None:
    with pytest.raises(ValidationError, match="at least 32"):
        Settings(session_secret="too-short")


def test_ai_provider_is_restricted_to_supported_adapters() -> None:
    with pytest.raises(ValidationError):
        Settings(session_secret="x" * 32, ai_provider="unknown")  # type: ignore[arg-type]


def test_vision_provider_is_restricted_to_supported_adapters() -> None:
    with pytest.raises(ValidationError):
        Settings(  # type: ignore[arg-type]
            session_secret="x" * 32, vision_ai_provider="unknown"
        )


def test_qwen_base_url_requires_https() -> None:
    with pytest.raises(ValidationError, match="HTTPS"):
        Settings(session_secret="x" * 32, qwen_base_url="http://example.test/v1")


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"session_secret": "development-only-replace-me-with-32-characters"}, "placeholder"),
        ({"session_cookie_secure": False}, "SESSION_COOKIE_SECURE"),
        ({"trusted_origins": ["http://teacher.example"]}, "HTTPS"),
        ({"trusted_hosts": ["*"]}, "explicit"),
        (
            {"database_url": "postgresql+asyncpg://teacher_workspace:change-me-local-only@db/app"},
            "non-placeholder password",
        ),
    ],
)
def test_production_rejects_insecure_configuration(
    overrides: dict[str, object], message: str
) -> None:
    values: dict[str, object] = {
        "app_env": "production",
        "app_domain": "teacher.example",
        "session_secret": "p" * 48,
        "session_cookie_secure": True,
        "trusted_origins": ["https://teacher.example"],
        "trusted_hosts": ["api"],
        "database_url": "postgresql+asyncpg://teacher_workspace:strong-password-1@db/app",
    }
    values.update(overrides)
    with pytest.raises(ValidationError, match=message):
        Settings(**values)  # type: ignore[arg-type]


def test_valid_production_configuration_is_accepted() -> None:
    settings = Settings(
        app_env="production",
        app_domain="teacher.example",
        session_secret="p" * 48,
        session_cookie_secure=True,
        trusted_origins=["https://teacher.example"],
        trusted_hosts=["api"],
        database_url="postgresql+asyncpg://teacher_workspace:strong-password-1@db/app",
    )
    assert settings.app_env == "production"


def test_public_registration_requires_operator_contact_in_production() -> None:
    with pytest.raises(ValidationError, match="SUPPORT_CONTACT"):
        Settings(
            app_env="production",
            app_domain="teacher.example",
            session_secret="p" * 48,
            session_cookie_secure=True,
            trusted_origins=["https://teacher.example"],
            trusted_hosts=["api"],
            database_url="postgresql+asyncpg://teacher_workspace:strong-password-1@db/app",
            registration_enabled=True,
        )
    settings = Settings(
        app_env="production",
        app_domain="teacher.example",
        session_secret="p" * 48,
        session_cookie_secure=True,
        trusted_origins=["https://teacher.example"],
        trusted_hosts=["api"],
        database_url="postgresql+asyncpg://teacher_workspace:strong-password-1@db/app",
        registration_enabled=True,
        registration_invite_required=True,
        support_contact="support@real-domain.cn",
    )
    assert settings.registration_enabled


def test_production_registration_must_be_invitation_only() -> None:
    with pytest.raises(ValidationError, match="invitation code"):
        Settings(
            app_env="production",
            app_domain="teacher.example",
            session_secret="p" * 48,
            session_cookie_secure=True,
            trusted_origins=["https://teacher.example"],
            trusted_hosts=["api"],
            database_url="postgresql+asyncpg://teacher_workspace:strong-password-1@db/app",
            registration_enabled=True,
            registration_invite_required=False,
            support_contact="support@real-domain.cn",
        )


def test_user_upload_quota_cannot_be_smaller_than_one_file() -> None:
    with pytest.raises(ValidationError, match="USER_UPLOAD_QUOTA_BYTES"):
        Settings(session_secret="x" * 32, max_upload_bytes=100, user_upload_quota_bytes=99)


def test_production_supabase_storage_requires_server_credentials() -> None:
    with pytest.raises(ValidationError, match="Supabase storage"):
        Settings(
            app_env="production",
            app_domain="teacher.example",
            session_secret="p" * 48,
            session_cookie_secure=True,
            trusted_origins=["https://teacher.example"],
            trusted_hosts=["api"],
            database_url="postgresql+asyncpg://teacher_workspace:strong-password-1@db/app",
            storage_backend="supabase",
        )
