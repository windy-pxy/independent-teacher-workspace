"""Run tenant isolation tests against a migrated disposable PostgreSQL database."""

import os
import secrets
import subprocess
import sys
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def start_services(env: dict[str, str]) -> tuple[list[subprocess.Popen[bytes]], list[object]]:
    logs = ROOT / "var/validation"
    logs.mkdir(parents=True, exist_ok=True)
    handles = [
        (logs / "m3-api.log").open("ab"),
        (logs / "m3-web.log").open("ab"),
    ]
    python = (
        ROOT / "apps/backend/.venv/Scripts/python.exe"
        if os.name == "nt"
        else ROOT / "apps/backend/.venv/bin/python"
    )
    processes = [
        subprocess.Popen(
            [str(python), "-m", "uvicorn", "teacher_workspace.main:app", "--host", "127.0.0.1", "--port", "8102"],
            cwd=ROOT,
            env=env,
            stdout=handles[0],
            stderr=subprocess.STDOUT,
        ),
        subprocess.Popen(
            ["node", str(ROOT / "apps/web/node_modules/next/dist/bin/next"), "dev", "--hostname", "127.0.0.1", "--port", "3102"],
            cwd=ROOT / "apps/web",
            env=env,
            stdout=handles[1],
            stderr=subprocess.STDOUT,
        ),
    ]
    for url in ("http://127.0.0.1:8102/health/ready", "http://127.0.0.1:3102/register"):
        for _ in range(60):
            if any(process.poll() is not None for process in processes):
                raise RuntimeError("M3 validation service exited; inspect var/validation logs")
            try:
                from urllib.request import urlopen

                with urlopen(url, timeout=3) as response:
                    if response.status == 200:
                        break
            except OSError:
                time.sleep(1)
        else:
            raise RuntimeError("M3 validation service readiness timeout")
    return processes, handles


def stop_services(processes: list[subprocess.Popen[bytes]], handles: list[object]) -> None:
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
    for handle in handles:
        handle.close()  # type: ignore[attr-defined]


def browser_check(env: dict[str, str]) -> None:
    env.update(
        {
            "REGISTRATION_ENABLED": "true",
            "TRUSTED_ORIGINS": "http://127.0.0.1:3102",
            "TRUSTED_HOSTS": "127.0.0.1,localhost",
            "API_INTERNAL_URL": "http://127.0.0.1:8102",
            "SESSION_COOKIE_SECURE": "false",
            "SESSION_SECRET": secrets.token_urlsafe(40),
            "LOCAL_STORAGE_ROOT": str(ROOT / "var/validation/m3-storage"),
            "APP_ENV": "test",
        }
    )
    processes, handles = start_services(env)
    try:
        subprocess.run(
            ["node", "scripts/validate_multitenant_browser.cjs", "--setup"],
            cwd=ROOT,
            env=env,
            check=True,
        )
    finally:
        stop_services(processes, handles)
    # Keep PostgreSQL running while restarting both application processes.
    processes, handles = start_services(env)
    try:
        subprocess.run(
            ["node", "scripts/validate_multitenant_browser.cjs", "--persist"],
            cwd=ROOT,
            env=env,
            check=True,
        )
    finally:
        stop_services(processes, handles)


def main() -> None:
    name = f"teacher-multitenant-validation-{uuid.uuid4().hex[:10]}"
    env = os.environ.copy()
    env.update(
        {
            "POSTGRES_PASSWORD": secrets.token_urlsafe(32),
            "PYTHONPATH": str(ROOT / "apps/backend/src"),
            "AI_PROVIDER": "mock",
            "VISION_AI_PROVIDER": "mock",
        }
    )
    created = False
    try:
        subprocess.run(
            [
                "docker", "run", "--detach", "--rm", "--name", name,
                "--label", "teacher.validation=multitenant", "--publish", "127.0.0.1::5432",
                "--env", "POSTGRES_PASSWORD", "--env", "POSTGRES_DB=teacher_multitenant_test",
                "postgres:17-alpine",
            ],
            env=env,
            check=True,
            capture_output=True,
        )
        created = True
        for _ in range(30):
            ready = subprocess.run(
                ["docker", "exec", name, "pg_isready", "-U", "postgres"],
                capture_output=True,
                check=False,
            )
            if ready.returncode == 0:
                break
            time.sleep(1)
        else:
            raise RuntimeError("Isolated PostgreSQL did not become ready")
        port = subprocess.check_output(["docker", "port", name, "5432/tcp"], text=True).strip().split(":")[-1]
        url = f"postgresql+asyncpg://postgres:{env['POSTGRES_PASSWORD']}@127.0.0.1:{port}/teacher_multitenant_test"
        env["DATABASE_URL"] = url
        env["MULTITENANT_TEST_DATABASE_URL"] = url
        uv = ["uv", "run", "--project", "apps/backend", "--no-sync"]
        migration = uv + ["alembic", "-c", "apps/backend/alembic.ini"]
        for operation in (["upgrade", "head"], ["downgrade", "-1"], ["upgrade", "head"], ["check"]):
            subprocess.run(migration + operation, cwd=ROOT, env=env, check=True)
        subprocess.run(
            uv + ["pytest", "apps/backend/tests/test_multi_tenant_isolation.py", "-q"],
            cwd=ROOT,
            env=env,
            check=True,
        )
        if "--browser" in sys.argv:
            browser_check(env)
        print("PASS: PostgreSQL migrations and full two-teacher isolation test")
    finally:
        if created:
            subprocess.run(["docker", "stop", name], check=True, capture_output=True)


if __name__ == "__main__":
    main()
