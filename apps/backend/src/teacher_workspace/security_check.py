from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

FORBIDDEN_NAMES = {".env", "id_rsa", "id_ed25519"}
FORBIDDEN_SUFFIXES = {".pem", ".key", ".dump", ".sql", ".sqlite", ".sqlite3", ".docx", ".xlsx"}
FORBIDDEN_PARTS = {"backups", "exports", "logs", "uploads", "var"}
SECRET_PATTERNS = [
    re.compile(rb"-----BEGIN (?:RSA |OPENSSH |EC )?PRIVATE KEY-----"),
    re.compile(rb"\bgh[opusr]_[A-Za-z0-9]{20,}\b"),
    re.compile(rb"\bsk-[A-Za-z0-9_-]{20,}\b"),
]
ACTION_PATTERN = re.compile(r"^\s*-?\s*uses:\s*[^@\s]+@([^\s#]+)", re.MULTILINE)


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


def check_repository(root: Path) -> dict[str, int | str]:
    files = tracked_files(root)
    failures: list[str] = []
    scanned = 0
    for path in files:
        relative = path.relative_to(root)
        lowered_parts = {part.casefold() for part in relative.parts}
        if relative.name in FORBIDDEN_NAMES or (
            relative.name.startswith(".env.") and relative.name != ".env.example"
        ):
            failures.append(f"forbidden environment file: {relative}")
        if relative.suffix.casefold() in FORBIDDEN_SUFFIXES:
            failures.append(f"forbidden generated/private artifact: {relative}")
        if lowered_parts & FORBIDDEN_PARTS:
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
