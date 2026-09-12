from __future__ import annotations

import json

from pydantic import ValidationError

from teacher_workspace.config import Settings


def main() -> None:
    try:
        settings = Settings()
    except ValidationError as exc:
        safe_errors = [
            {"field": ".".join(str(part) for part in error["loc"]), "message": error["msg"]}
            for error in exc.errors(include_input=False, include_url=False)
        ]
        raise SystemExit(
            "生产配置检查失败：" + json.dumps(safe_errors, ensure_ascii=False)
        ) from None
    if settings.app_env != "production":
        raise SystemExit("生产配置检查失败：APP_ENV 必须为 production")
    print(
        json.dumps(
            {
                "status": "ok",
                "app_domain": settings.app_domain,
                "trusted_origins": settings.trusted_origins,
                "trusted_hosts": settings.trusted_hosts,
                "secure_cookie": settings.session_cookie_secure,
                "storage_backend": settings.storage_backend,
                "ai_provider": settings.ai_provider,
                "vision_ai_provider": settings.vision_ai_provider,
                "registration_enabled": settings.registration_enabled,
                "registration_invite_required": settings.registration_invite_required,
                "user_upload_quota_bytes": settings.user_upload_quota_bytes,
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
