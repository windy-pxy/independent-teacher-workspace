"""Rotate local Compose credentials without printing secret values.

This is an operator tool for the default local Compose deployment. It updates the
PostgreSQL role and `.env` together, recreates backend services, and restores the
previous credentials if any step fails.
"""

from __future__ import annotations

import argparse
import re
import secrets
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = ROOT / ".env"
TEMP_PATH = ROOT / ".env.rotate.tmp"


class RotationError(RuntimeError):
    """Raised when credential rotation cannot be completed safely."""


def _read_value(text: str, name: str) -> str:
    match = re.search(rf"(?m)^{re.escape(name)}=(.*)$", text)
    if not match:
        raise RotationError(f"缺少必要配置：{name}")
    return match.group(1).strip()


def _replace_value(text: str, name: str, value: str) -> str:
    updated, count = re.subn(
        rf"(?m)^{re.escape(name)}=.*$",
        lambda _match: f"{name}={value}",
        text,
        count=1,
    )
    if count != 1:
        raise RotationError(f"无法更新必要配置：{name}")
    return updated


def _replace_database_url(text: str, password: str) -> str:
    pattern = re.compile(
        r"(?m)^(DATABASE_URL=postgresql\+asyncpg://[^:\r\n]+:)"
        r"[^@\r\n]+(@[^\r\n]+)$"
    )
    updated, count = pattern.subn(
        lambda match: f"{match.group(1)}{password}{match.group(2)}",
        text,
        count=1,
    )
    if count != 1:
        raise RotationError("DATABASE_URL 格式不受支持，未执行轮换")
    return updated


def _run(command: list[str], *, stdin: str | None = None) -> None:
    result = subprocess.run(
        command,
        cwd=ROOT,
        input=stdin,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise RotationError(f"命令执行失败：{command[0]} {command[1]}")


def _set_database_password(role: str, password: str) -> None:
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", role):
        raise RotationError("POSTGRES_USER 不是安全的数据库角色名")
    _run(
        [
            "docker",
            "compose",
            "exec",
            "-T",
            "db",
            "sh",
            "-c",
            'psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB"',
        ],
        stdin=f'ALTER ROLE "{role}" WITH PASSWORD \'{password}\';\n',
    )


def _restart_backend() -> None:
    _run(["docker", "compose", "up", "--no-deps", "--force-recreate", "migrate"])
    _run(
        [
            "docker",
            "compose",
            "up",
            "-d",
            "--wait",
            "--no-deps",
            "--force-recreate",
            "api",
            "worker",
        ]
    )


def rotate(*, disable_ai: bool) -> None:
    if not ENV_PATH.is_file():
        raise RotationError("未找到 .env")
    original = ENV_PATH.read_text(encoding="utf-8")
    role = _read_value(original, "POSTGRES_USER")
    old_database_password = _read_value(original, "POSTGRES_PASSWORD")
    new_database_password = secrets.token_hex(32)
    new_session_secret = secrets.token_hex(48)

    updated = _replace_value(original, "POSTGRES_PASSWORD", new_database_password)
    updated = _replace_database_url(updated, new_database_password)
    updated = _replace_value(updated, "SESSION_SECRET", new_session_secret)
    if disable_ai:
        updated = _replace_value(updated, "AI_PROVIDER", "mock")
        updated = _replace_value(updated, "VISION_AI_PROVIDER", "mock")
        updated = _replace_value(updated, "DEEPSEEK_API_KEY", "")
        updated = _replace_value(updated, "QWEN_API_KEY", "")

    TEMP_PATH.write_text(updated, encoding="utf-8", newline="")
    database_changed = False
    try:
        _set_database_password(role, new_database_password)
        database_changed = True
        TEMP_PATH.replace(ENV_PATH)
        _restart_backend()
    except Exception:
        if TEMP_PATH.exists():
            TEMP_PATH.unlink()
        ENV_PATH.write_text(original, encoding="utf-8", newline="")
        if database_changed:
            _set_database_password(role, old_database_password)
            try:
                _restart_backend()
            except RotationError:
                # Preserve the original rotation error. The old credentials are
                # restored on disk and in PostgreSQL for manual service recovery.
                pass
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description="安全轮换本地 Compose 凭据")
    parser.add_argument(
        "--confirm",
        required=True,
        choices=["rotate-local-secrets"],
        help="必须明确确认操作范围",
    )
    parser.add_argument(
        "--disable-ai",
        action="store_true",
        help="同时清空 DeepSeek/千问密钥并切换回 Mock",
    )
    args = parser.parse_args()
    try:
        rotate(disable_ai=args.disable_ai)
    except RotationError as exc:
        print(f"credential_rotation=failed ({exc})")
        return 1
    print("credential_rotation=ok")
    if args.disable_ai:
        print("ai_keys_removed=ok")
        print("providers=mock")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
