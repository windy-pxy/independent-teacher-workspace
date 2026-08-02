import pytest
from pydantic import ValidationError

from teacher_workspace.config import Settings


def test_comma_separated_environment_lists(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TRUSTED_ORIGINS", "http://localhost:3000,https://teacher.example")
    monkeypatch.setenv("ALLOWED_UPLOAD_MIME_TYPES", "application/pdf,image/png")
    settings = Settings(session_secret="x" * 32)
    assert settings.trusted_origins == ["http://localhost:3000", "https://teacher.example"]
    assert settings.allowed_upload_mime_types == ["application/pdf", "image/png"]


def test_short_session_secret_is_rejected() -> None:
    with pytest.raises(ValidationError, match="at least 32"):
        Settings(session_secret="too-short")
