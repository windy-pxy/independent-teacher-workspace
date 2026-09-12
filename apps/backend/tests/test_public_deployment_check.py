import httpx
import pytest

from teacher_workspace.public_deployment_check import (
    validate_public_url,
    validate_registration,
    validate_security_headers,
)


def test_public_url_requires_real_https_hostname() -> None:
    assert validate_public_url("https://teacher.example.com/") == "https://teacher.example.com"
    for invalid in ("http://teacher.example.com", "https://localhost", "https://127.0.0.1"):
        with pytest.raises(ValueError):
            validate_public_url(invalid)


def test_public_headers_and_invitation_registration_are_checked() -> None:
    headers = httpx.Headers(
        {
            "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
            "Content-Security-Policy": "default-src 'self'",
            "X-Content-Type-Options": "nosniff",
            "X-Frame-Options": "DENY",
            "Referrer-Policy": "same-origin",
        }
    )
    assert validate_security_headers(headers) == []
    assert validate_registration(
        {"enabled": True, "invite_required": True, "support_contact": "owner@example.cn"},
        True,
    ) == []
    assert validate_registration({"enabled": True, "invite_required": False}, True)
