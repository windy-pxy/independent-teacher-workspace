from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

SCRIPT_PATH = Path(__file__).resolve().parents[3] / "scripts" / "rotate_local_secrets.py"
SCRIPT_SPEC = importlib.util.spec_from_file_location("rotate_local_secrets", SCRIPT_PATH)
assert SCRIPT_SPEC is not None and SCRIPT_SPEC.loader is not None
rotate_local_secrets = importlib.util.module_from_spec(SCRIPT_SPEC)
sys.modules[SCRIPT_SPEC.name] = rotate_local_secrets
SCRIPT_SPEC.loader.exec_module(rotate_local_secrets)

SAMPLE_ENV = """POSTGRES_DB=teacher_workspace
POSTGRES_USER=teacher_workspace
POSTGRES_PASSWORD=old-safe-password-1234
DATABASE_URL=postgresql+asyncpg://teacher_workspace:old-safe-password-1234@localhost:5432/teacher_workspace
SESSION_SECRET=old-session-secret-that-is-long-enough-for-tests
AI_PROVIDER=deepseek
VISION_AI_PROVIDER=qwen
DEEPSEEK_API_KEY=fictional-deepseek-key
QWEN_API_KEY=fictional-qwen-key
"""


def configure_paths(monkeypatch: pytest.MonkeyPatch, root: Path) -> Path:
    env_path = root / ".env"
    env_path.write_text(SAMPLE_ENV, encoding="utf-8")
    monkeypatch.setattr(rotate_local_secrets, "ROOT", root)
    monkeypatch.setattr(rotate_local_secrets, "ENV_PATH", env_path)
    monkeypatch.setattr(rotate_local_secrets, "TEMP_PATH", root / ".env.rotate.tmp")
    return env_path


def test_rotation_updates_credentials_and_disables_ai(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    env_path = configure_paths(monkeypatch, tmp_path)
    password_changes: list[tuple[str, str]] = []
    commands: list[list[str]] = []
    monkeypatch.setattr(
        rotate_local_secrets,
        "_set_database_password",
        lambda role, password: password_changes.append((role, password)),
    )
    monkeypatch.setattr(
        rotate_local_secrets,
        "_run",
        lambda command, **_kwargs: commands.append(command),
    )

    rotate_local_secrets.rotate(disable_ai=True)

    updated = env_path.read_text(encoding="utf-8")
    new_password = rotate_local_secrets._read_value(updated, "POSTGRES_PASSWORD")
    new_session_secret = rotate_local_secrets._read_value(updated, "SESSION_SECRET")
    assert len(new_password) == 64
    assert len(new_session_secret) == 96
    assert new_password in rotate_local_secrets._read_value(updated, "DATABASE_URL")
    assert rotate_local_secrets._read_value(updated, "AI_PROVIDER") == "mock"
    assert rotate_local_secrets._read_value(updated, "VISION_AI_PROVIDER") == "mock"
    assert rotate_local_secrets._read_value(updated, "DEEPSEEK_API_KEY") == ""
    assert rotate_local_secrets._read_value(updated, "QWEN_API_KEY") == ""
    assert password_changes == [("teacher_workspace", new_password)]
    assert any("migrate" in command for command in commands)


def test_rotation_restores_env_and_database_password_on_restart_failure(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    env_path = configure_paths(monkeypatch, tmp_path)
    password_changes: list[tuple[str, str]] = []
    monkeypatch.setattr(
        rotate_local_secrets,
        "_set_database_password",
        lambda role, password: password_changes.append((role, password)),
    )

    def fail_restart(_command: list[str], **_kwargs: object) -> None:
        raise rotate_local_secrets.RotationError("fictional restart failure")

    monkeypatch.setattr(rotate_local_secrets, "_run", fail_restart)

    with pytest.raises(rotate_local_secrets.RotationError, match="fictional restart"):
        rotate_local_secrets.rotate(disable_ai=True)

    assert env_path.read_text(encoding="utf-8") == SAMPLE_ENV
    assert len(password_changes) == 2
    assert password_changes[0][1] != password_changes[1][1]
    assert password_changes[1] == ("teacher_workspace", "old-safe-password-1234")
