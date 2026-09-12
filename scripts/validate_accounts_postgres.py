"""Run account tests against migrated disposable PostgreSQL, never the user's database."""

import os
import secrets
import subprocess
import sys
import time
import uuid
from pathlib import Path
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]


def browser_check(env: dict[str, str]) -> None:
    """Only disposable DB is passed to these loopback services."""
    env.update({
        "REGISTRATION_ENABLED": "true",
        "TRUSTED_ORIGINS": "http://127.0.0.1:3101",
        "TRUSTED_HOSTS": "127.0.0.1,localhost",
        "API_INTERNAL_URL": "http://127.0.0.1:8101",
        "SESSION_COOKIE_SECURE": "false",
        "SESSION_SECRET": secrets.token_urlsafe(40),
        "LOCAL_STORAGE_ROOT": str(ROOT / "var/validation/account-storage"),
        "APP_ENV": "test",
    })
    logs = ROOT / "var/validation"
    logs.mkdir(parents=True, exist_ok=True)
    processes: list[subprocess.Popen[bytes]] = []
    with (logs / "account-api.log").open("wb") as api_log, (logs / "account-web.log").open("wb") as web_log:
        try:
            processes.append(subprocess.Popen([
                str(ROOT / "apps/backend/.venv/Scripts/python.exe") if os.name == "nt" else str(ROOT / "apps/backend/.venv/bin/python"),
                "-m", "uvicorn", "teacher_workspace.main:app", "--host", "127.0.0.1", "--port", "8101",
            ], cwd=ROOT, env=env, stdout=api_log, stderr=subprocess.STDOUT))
            processes.append(subprocess.Popen([
                "node", str(ROOT / "apps/web/node_modules/next/dist/bin/next"), "dev", "--hostname", "127.0.0.1", "--port", "3101",
            ], cwd=ROOT / "apps/web", env=env, stdout=web_log, stderr=subprocess.STDOUT))
            for url in ("http://127.0.0.1:8101/health/ready", "http://127.0.0.1:3101/register"):
                for _ in range(60):
                    if any(process.poll() is not None for process in processes):
                        raise RuntimeError("Validation service exited; inspect var/validation logs")
                    try:
                        with urlopen(url, timeout=3) as response:
                            if response.status == 200:
                                break
                    except OSError:
                        time.sleep(1)
                else:
                    raise RuntimeError("Validation service readiness timeout")
            subprocess.run(["node", "scripts/validate_accounts_browser.cjs"], cwd=ROOT, env=env, check=True)
        finally:
            for process in reversed(processes):
                if process.poll() is None:
                    if os.name == "nt":
                        subprocess.run(
                            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                            capture_output=True,
                            check=False,
                        )
                    else:
                        process.terminate()
                    process.wait(timeout=15)


def main() -> None:
    name = f"teacher-accounts-validation-{uuid.uuid4().hex[:10]}"
    env = os.environ.copy()
    env.update({
        "POSTGRES_PASSWORD": secrets.token_urlsafe(32),
        "PYTHONPATH": str(ROOT / "apps/backend/src"),
        "AI_PROVIDER": "mock",
        "VISION_AI_PROVIDER": "mock",
    })
    created = False
    try:
        subprocess.run([
            "docker", "run", "--detach", "--rm", "--name", name,
            "--label", "teacher.validation=accounts", "--publish", "127.0.0.1::5432",
            "--env", "POSTGRES_PASSWORD", "--env", "POSTGRES_DB=teacher_accounts_test",
            "postgres:17-alpine",
        ], env=env, check=True, capture_output=True)
        created = True
        for _ in range(30):
            result = subprocess.run(
                ["docker", "exec", name, "pg_isready", "-U", "postgres"],
                capture_output=True,
                check=False,
            )
            if result.returncode == 0:
                break
            time.sleep(1)
        else:
            raise RuntimeError("Isolated PostgreSQL did not become ready")
        port = subprocess.check_output(["docker", "port", name, "5432/tcp"], text=True).strip().split(":")[-1]
        env["DATABASE_URL"] = f"postgresql+asyncpg://postgres:{env['POSTGRES_PASSWORD']}@127.0.0.1:{port}/teacher_accounts_test"
        env["ACCOUNT_TEST_DATABASE_URL"] = env["DATABASE_URL"]
        uv = ["uv", "run", "--project", "apps/backend", "--no-sync"]
        migration = uv + ["alembic", "-c", "apps/backend/alembic.ini"]
        for operation in (["upgrade", "head"], ["downgrade", "-1"], ["upgrade", "head"], ["check"]):
            subprocess.run(migration + operation, cwd=ROOT, env=env, check=True)
        subprocess.run(uv + ["pytest", "apps/backend/tests/test_accounts.py", "-q"], cwd=ROOT, env=env, check=True)
        if "--browser" in sys.argv:
            browser_check(env)
        print("PASS: PostgreSQL upgrade/downgrade/upgrade/check and account API tests")
    finally:
        if created:
            subprocess.run(["docker", "stop", name], check=True, capture_output=True)


if __name__ == "__main__":
    main()
