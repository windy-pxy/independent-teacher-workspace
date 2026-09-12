from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

FORBIDDEN_NAMES = {".env", "id_rsa", "id_ed25519"}
FORBIDDEN_SUFFIXES = {".pem", ".key", ".dump", ".sql", ".sqlite", ".sqlite3", ".docx", ".xlsx"}
FORBIDDEN_ROOT_DIRECTORIES = {"backups", "exports", "logs", "uploads", "var"}
SECRET_PATTERNS = [
    re.compile(rb"-----BEGIN (?:RSA |OPENSSH |EC )?PRIVATE KEY-----"),
    re.compile(rb"\bgh[opusr]_[A-Za-z0-9]{20,}\b"),
    re.compile(rb"\bsk-[A-Za-z0-9_-]{20,}\b"),
]
ACTION_PATTERN = re.compile(r"^\s*-?\s*uses:\s*[^@\s]+@([^\s#]+)", re.MULTILINE)
PRODUCTION_HARDENED_SERVICES = ("migrate", "api", "worker", "web", "caddy")


class SecurityCheckError(RuntimeError):
    pass


def repository_root() -> Path:
    return Path(__file__).resolve().parents[4]


def tracked_files(root: Path) -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
        cwd=root,
        check=True,
        capture_output=True,
    )
    return [root / item.decode("utf-8") for item in result.stdout.split(b"\0") if item]


def check_production_compose_hardening(root: Path) -> list[str]:
    path = root / "compose.production.yaml"
    text = path.read_text(encoding="utf-8")
    failures: list[str] = []
    anchor = text.split("services:", maxsplit=1)[0]
    for required in (
        "read_only: true",
        "no-new-privileges:true",
        "cap_drop:",
        "- ALL",
        "pids_limit: 256",
    ):
        if required not in anchor:
            failures.append(f"production runtime hardening is missing: {required}")
    for service in PRODUCTION_HARDENED_SERVICES:
        match = re.search(
            rf"(?ms)^  {re.escape(service)}:\s*\n(.*?)(?=^  [a-z][a-z0-9_-]*:\s*$|\Z)",
            text,
        )
        if not match or "<<: *production-runtime" not in match.group(1):
            failures.append(f"production service is not hardened: {service}")
    caddy = re.search(r"(?ms)^  caddy:\s*\n(.*?)(?=^volumes:|\Z)", text)
    if not caddy or "NET_BIND_SERVICE" not in caddy.group(1):
        failures.append("production Caddy lacks the minimal port-binding capability")
    return failures


def check_repository(root: Path) -> dict[str, int | str]:
    files = tracked_files(root)
    failures: list[str] = []
    scanned = 0
    for path in files:
        relative = path.relative_to(root)
        if relative.name in FORBIDDEN_NAMES or (
            relative.name.startswith(".env.") and relative.name != ".env.example"
        ):
            failures.append(f"forbidden environment file: {relative}")
        if relative.suffix.casefold() in FORBIDDEN_SUFFIXES:
            failures.append(f"forbidden generated/private artifact: {relative}")
        if relative.parts[0].casefold() in FORBIDDEN_ROOT_DIRECTORIES:
            failures.append(f"forbidden runtime directory: {relative}")
        if not path.is_file() or path.stat().st_size > 2 * 1024 * 1024:
            continue
        content = path.read_bytes()
        scanned += 1
        if any(pattern.search(content) for pattern in SECRET_PATTERNS):
            failures.append(f"credential-like content: {relative}")

    workflow_count = 0
    for workflow in (root / ".github" / "workflows").glob("*.y*ml"):
        text = workflow.read_text(encoding="utf-8")
        for reference in ACTION_PATTERN.findall(text):
            workflow_count += 1
            if not re.fullmatch(r"[0-9a-fA-F]{40}", reference):
                failures.append(
                    f"GitHub Action is not pinned to a full commit SHA: "
                    f"{workflow.relative_to(root)}@{reference}"
                )

    gitignore = (root / ".gitignore").read_text(encoding="utf-8")
    for required in (".env", "backups/", "*.dump", "*.key", "var/"):
        if required not in gitignore:
            failures.append(f".gitignore is missing required pattern: {required}")
    failures.extend(check_production_compose_hardening(root))
    if failures:
        raise SecurityCheckError("; ".join(failures))
    return {
        "status": "ok",
        "tracked_files": len(files),
        "content_files_scanned": scanned,
        "pinned_actions": workflow_count,
    }


def main() -> None:
    try:
        result = check_repository(repository_root())
    except SecurityCheckError as exc:
        raise SystemExit(f"安全静态检查失败：{exc}") from None
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
