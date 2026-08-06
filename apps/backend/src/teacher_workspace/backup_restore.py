from __future__ import annotations

import argparse
import hashlib
import json
import os
import secrets
import shutil
import subprocess
import sys
import tarfile
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

SCHEMA_VERSION = 1
DATABASE_ARCHIVE = "database.dump"
STORAGE_ARCHIVE = "storage.tar.gz"
ENCRYPTED_SUFFIX = ".enc"
CONTAINER_BACKUP_DIR = "/tmp/teacher-workspace-backup"
POSTGRES_RESTORE_IMAGE = (
    "postgres:17-alpine@sha256:742f40ea20b9ff2ff31db5458d127452988a2164df9e17441e191f3b72252193"
)
ENCRYPTION_MAGIC = b"TWBKUP01"
SALT_BYTES = 16
NONCE_BYTES = 12
TAG_BYTES = 16
ENCRYPTION_ITERATIONS = 600_000
FILE_CHUNK_BYTES = 1024 * 1024


class BackupError(RuntimeError):
    pass


def run(
    command: list[str],
    *,
    capture: bool = False,
    env: dict[str, str] | None = None,
) -> str:
    completed = subprocess.run(
        command,
        check=False,
        text=True,
        capture_output=capture,
        env=env,
    )
    if completed.returncode != 0:
        stderr = completed.stderr.strip() if capture else ""
        raise BackupError(
            f"Command failed with exit code {completed.returncode}: {command[0]}"
            + (f" ({stderr})" if stderr else "")
        )
    return completed.stdout.strip() if capture else ""


def compose(files: list[Path], *arguments: str, capture: bool = False) -> str:
    command = ["docker", "compose"]
    for file in files:
        command.extend(["-f", str(file)])
    command.extend(arguments)
    return run(command, capture=capture)


def utc_timestamp() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def ensure_safe_child(parent: Path, child: Path) -> None:
    resolved_parent = parent.resolve()
    resolved_child = child.resolve()
    if resolved_child == resolved_parent or resolved_parent not in resolved_child.parents:
        raise BackupError(f"Unsafe path outside backup root: {resolved_child}")


def remove_temporary_directory(parent: Path, child: Path) -> None:
    ensure_safe_child(parent, child)
    if not child.name.startswith((".creating-", ".restore-", ".drill-")):
        raise BackupError(f"Refusing to remove unexpected directory: {child}")
    shutil.rmtree(child, ignore_errors=True)


def require_tools(*names: str) -> None:
    missing = [name for name in names if shutil.which(name) is None]
    if missing:
        raise BackupError(f"Required command is not available: {', '.join(missing)}")


def file_record(path: Path) -> dict[str, Any]:
    return {"name": path.name, "size": path.stat().st_size, "sha256": sha256_file(path)}


def encryption_password() -> str:
    password = os.environ.get("BACKUP_ENCRYPTION_PASSWORD", "")
    if len(password) < 16:
        raise BackupError(
            "BACKUP_ENCRYPTION_PASSWORD must contain at least 16 characters "
            "when encryption is enabled"
        )
    return password


def derive_encryption_key(password: str, salt: bytes) -> bytes:
    return PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=ENCRYPTION_ITERATIONS,
    ).derive(password.encode("utf-8"))


def encrypt_file(path: Path) -> Path:
    password = encryption_password()
    encrypted = path.with_name(path.name + ENCRYPTED_SUFFIX)
    salt = secrets.token_bytes(SALT_BYTES)
    nonce = secrets.token_bytes(NONCE_BYTES)
    encryptor = Cipher(
        algorithms.AES(derive_encryption_key(password, salt)), modes.GCM(nonce)
    ).encryptor()
    encryptor.authenticate_additional_data(ENCRYPTION_MAGIC)
    try:
        with path.open("rb") as source, encrypted.open("wb") as destination:
            destination.write(ENCRYPTION_MAGIC)
            destination.write(salt)
            destination.write(nonce)
            for chunk in iter(lambda: source.read(FILE_CHUNK_BYTES), b""):
                destination.write(encryptor.update(chunk))
            destination.write(encryptor.finalize())
            destination.write(encryptor.tag)
        path.unlink()
    except Exception:
        encrypted.unlink(missing_ok=True)
        raise
    return encrypted


def decrypt_file(path: Path, output: Path) -> None:
    password = encryption_password()
    minimum_size = len(ENCRYPTION_MAGIC) + SALT_BYTES + NONCE_BYTES + TAG_BYTES
    if path.stat().st_size < minimum_size:
        raise BackupError("Encrypted backup file is truncated")
    try:
        with path.open("rb") as source:
            magic = source.read(len(ENCRYPTION_MAGIC))
            if magic != ENCRYPTION_MAGIC:
                raise BackupError("Encrypted backup file header is invalid")
            salt = source.read(SALT_BYTES)
            nonce = source.read(NONCE_BYTES)
            ciphertext_bytes = path.stat().st_size - minimum_size
            source.seek(-TAG_BYTES, os.SEEK_END)
            tag = source.read(TAG_BYTES)
            source.seek(len(ENCRYPTION_MAGIC) + SALT_BYTES + NONCE_BYTES)
            decryptor = Cipher(
                algorithms.AES(derive_encryption_key(password, salt)),
                modes.GCM(nonce, tag),
            ).decryptor()
            decryptor.authenticate_additional_data(ENCRYPTION_MAGIC)
            remaining = ciphertext_bytes
            with output.open("wb") as destination:
                while remaining:
                    chunk = source.read(min(FILE_CHUNK_BYTES, remaining))
                    if not chunk:
                        raise BackupError("Encrypted backup ciphertext is truncated")
                    remaining -= len(chunk)
                    destination.write(decryptor.update(chunk))
                destination.write(decryptor.finalize())
    except InvalidTag as exc:
        output.unlink(missing_ok=True)
        raise BackupError("Backup password is incorrect or encrypted data was modified") from exc
    except Exception:
        output.unlink(missing_ok=True)
        raise


def create_backup(
    output_root: Path,
    compose_files: list[Path],
    *,
    encrypt: bool,
) -> Path:
    require_tools("docker", "git")
    output_root = output_root.resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    backup_id = f"{utc_timestamp()}-{uuid.uuid4().hex[:8]}"
    temporary = output_root / f".creating-{backup_id}"
    destination = output_root / backup_id
    ensure_safe_child(output_root, temporary)
    ensure_safe_child(output_root, destination)
    if temporary.exists() or destination.exists():
        raise BackupError(f"Backup destination already exists: {destination}")
    temporary.mkdir()

    db_container_file = f"{CONTAINER_BACKUP_DIR}-{backup_id}.dump"
    storage_container_file = f"{CONTAINER_BACKUP_DIR}-{backup_id}.tar.gz"
    try:
        compose_files = [path.resolve() for path in compose_files]
        if not compose(compose_files, "ps", "-q", "db", capture=True):
            raise BackupError("Database service is not running")
        if not compose(compose_files, "ps", "-q", "api", capture=True):
            raise BackupError("API service is not running")

        compose(
            compose_files,
            "exec",
            "-T",
            "db",
            "sh",
            "-c",
            f'pg_dump --format=custom --no-owner --no-acl -U "$POSTGRES_USER" '
            f'-d "$POSTGRES_DB" -f "{db_container_file}"',
        )
        compose(
            compose_files,
            "cp",
            f"db:{db_container_file}",
            str(temporary / DATABASE_ARCHIVE),
        )
        compose(
            compose_files,
            "exec",
            "-T",
            "api",
            "tar",
            "-C",
            "/app/var/storage",
            "-czf",
            storage_container_file,
            ".",
        )
        compose(
            compose_files,
            "cp",
            f"api:{storage_container_file}",
            str(temporary / STORAGE_ARCHIVE),
        )

        migration = compose(
            compose_files,
            "exec",
            "-T",
            "db",
            "sh",
            "-c",
            'psql -At -U "$POSTGRES_USER" -d "$POSTGRES_DB" '
            "-c 'SELECT version_num FROM alembic_version'",
            capture=True,
        )
        commit = run(["git", "rev-parse", "HEAD"], capture=True)
        database_path = temporary / DATABASE_ARCHIVE
        storage_path = temporary / STORAGE_ARCHIVE
        if encrypt:
            database_path = encrypt_file(database_path)
            storage_path = encrypt_file(storage_path)

        manifest = {
            "schema_version": SCHEMA_VERSION,
            "backup_id": backup_id,
            "created_at": datetime.now(UTC).isoformat(),
            "application_commit": commit,
            "database_migration": migration,
            "encrypted": encrypt,
            "encryption": (
                {
                    "algorithm": "AES-256-GCM",
                    "key_derivation": "PBKDF2-HMAC-SHA256",
                    "iterations": ENCRYPTION_ITERATIONS,
                }
                if encrypt
                else None
            ),
            "files": {
                "database": file_record(database_path),
                "storage": file_record(storage_path),
            },
        }
        (temporary / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        temporary.rename(destination)
        return destination
    except Exception:
        remove_temporary_directory(output_root, temporary)
        raise
    finally:
        for service, path in (("db", db_container_file), ("api", storage_container_file)):
            try:
                compose(compose_files, "exec", "-T", service, "rm", "-f", path)
            except Exception:
                pass


def load_and_verify_manifest(backup_dir: Path) -> dict[str, Any]:
    backup_dir = backup_dir.resolve()
    manifest_path = backup_dir / "manifest.json"
    if not manifest_path.is_file():
        raise BackupError("Backup manifest.json is missing")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise BackupError("Backup manifest is invalid") from exc
    if manifest.get("schema_version") != SCHEMA_VERSION:
        raise BackupError("Unsupported backup schema version")
    if manifest.get("backup_id") != backup_dir.name:
        raise BackupError("Backup directory name does not match manifest backup_id")
    files = manifest.get("files")
    if not isinstance(files, dict):
        raise BackupError("Backup manifest file list is invalid")
    for logical_name in ("database", "storage"):
        record = files.get(logical_name)
        if not isinstance(record, dict):
            raise BackupError(f"Backup manifest is missing {logical_name}")
        filename = record.get("name")
        if not isinstance(filename, str) or Path(filename).name != filename:
            raise BackupError(f"Unsafe backup filename for {logical_name}")
        path = backup_dir / filename
        if not path.is_file():
            raise BackupError(f"Backup file is missing: {filename}")
        if path.stat().st_size != record.get("size") or sha256_file(path) != record.get(
            "sha256"
        ):
            raise BackupError(f"Backup checksum mismatch: {filename}")
    return manifest


def materialize_archives(
    backup_dir: Path, manifest: dict[str, Any], temporary: Path
) -> tuple[Path, Path]:
    temporary.mkdir(parents=True, exist_ok=False)
    files = manifest["files"]
    database_source = backup_dir / files["database"]["name"]
    storage_source = backup_dir / files["storage"]["name"]
    database_target = temporary / DATABASE_ARCHIVE
    storage_target = temporary / STORAGE_ARCHIVE
    if manifest.get("encrypted"):
        decrypt_file(database_source, database_target)
        decrypt_file(storage_source, storage_target)
    else:
        shutil.copy2(database_source, database_target)
        shutil.copy2(storage_source, storage_target)
    return database_target, storage_target


def validate_storage_archive(path: Path) -> int:
    with tarfile.open(path, "r:gz") as archive:
        members = archive.getmembers()
        for member in members:
            normalized = PurePosixPath(member.name)
            if normalized.is_absolute() or ".." in normalized.parts:
                raise BackupError(f"Unsafe path in storage archive: {member.name}")
            if member.issym() or member.islnk():
                raise BackupError(f"Links are not allowed in storage archive: {member.name}")
        return sum(1 for member in members if member.isfile())


def drill_backup(backup_dir: Path) -> dict[str, Any]:
    require_tools("docker")
    backup_dir = backup_dir.resolve()
    manifest = load_and_verify_manifest(backup_dir)
    temporary = backup_dir.parent / f".drill-{uuid.uuid4().hex}"
    ensure_safe_child(backup_dir.parent, temporary)
    container_name = f"teacher-workspace-restore-drill-{uuid.uuid4().hex[:12]}"
    password = secrets.token_urlsafe(24)
    environment = os.environ.copy()
    environment["POSTGRES_PASSWORD"] = password
    try:
        database_archive, storage_archive = materialize_archives(
            backup_dir, manifest, temporary
        )
        storage_file_count = validate_storage_archive(storage_archive)
        run(
            [
                "docker",
                "run",
                "-d",
                "--name",
                container_name,
                "--env",
                "POSTGRES_PASSWORD",
                "--env",
                "POSTGRES_USER=restore_drill",
                "--env",
                "POSTGRES_DB=restore_drill",
                POSTGRES_RESTORE_IMAGE,
            ],
            env=environment,
        )
        for _ in range(30):
            ready = subprocess.run(
                ["docker", "exec", container_name, "pg_isready", "-U", "restore_drill"],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            if ready.returncode == 0:
                break
            time.sleep(1)
        else:
            raise BackupError("Temporary restore database did not become ready")
        run(["docker", "cp", str(database_archive), f"{container_name}:/tmp/database.dump"])
        run(
            [
                "docker",
                "exec",
                container_name,
                "pg_restore",
                "--no-owner",
                "--no-acl",
                "-U",
                "restore_drill",
                "-d",
                "restore_drill",
                "/tmp/database.dump",
            ]
        )
        migration = run(
            [
                "docker",
                "exec",
                container_name,
                "psql",
                "-At",
                "-U",
                "restore_drill",
                "-d",
                "restore_drill",
                "-c",
                "SELECT version_num FROM alembic_version",
            ],
            capture=True,
        )
        table_count = int(
            run(
                [
                    "docker",
                    "exec",
                    container_name,
                    "psql",
                    "-At",
                    "-U",
                    "restore_drill",
                    "-d",
                    "restore_drill",
                    "-c",
                    "SELECT count(*) FROM pg_tables WHERE schemaname='public'",
                ],
                capture=True,
            )
        )
        if migration != manifest.get("database_migration"):
            raise BackupError("Restored migration does not match backup manifest")
        if table_count < 1:
            raise BackupError("Restored database does not contain application tables")
        return {
            "backup_id": manifest["backup_id"],
            "database_migration": migration,
            "database_table_count": table_count,
            "storage_file_count": storage_file_count,
            "status": "ok",
        }
    finally:
        subprocess.run(
            ["docker", "rm", "-f", container_name],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        if temporary.exists():
            remove_temporary_directory(backup_dir.parent, temporary)


def restore_backup(
    backup_dir: Path,
    compose_files: list[Path],
    *,
    confirm_backup_id: str,
    replace_current_data: bool,
    safety_output_root: Path,
) -> None:
    require_tools("docker", "git")
    backup_dir = backup_dir.resolve()
    manifest = load_and_verify_manifest(backup_dir)
    if confirm_backup_id != manifest["backup_id"] or not replace_current_data:
        raise BackupError(
            "Restore requires both --confirm-backup-id matching the manifest and "
            "--replace-current-data"
        )
    safety_backup = create_backup(
        safety_output_root,
        compose_files,
        encrypt=bool(os.environ.get("BACKUP_ENCRYPTION_PASSWORD")),
    )
    print(f"Created automatic pre-restore safety backup: {safety_backup}")
    temporary = backup_dir.parent / f".restore-{uuid.uuid4().hex}"
    ensure_safe_child(backup_dir.parent, temporary)
    restore_container = f"teacher-workspace-storage-restore-{uuid.uuid4().hex[:12]}"
    try:
        database_archive, storage_archive = materialize_archives(
            backup_dir, manifest, temporary
        )
        validate_storage_archive(storage_archive)
        api_container = compose(compose_files, "ps", "-q", "api", capture=True)
        if not api_container:
            raise BackupError("API container is unavailable for storage volume discovery")
        storage_volume = run(
            [
                "docker",
                "inspect",
                "--format",
                "{{range .Mounts}}{{if eq .Destination \"/app/var/storage\"}}"
                "{{.Name}}{{end}}{{end}}",
                api_container,
            ],
            capture=True,
        )
        if not storage_volume or not all(
            character.isalnum() or character in "_.-" for character in storage_volume
        ):
            raise BackupError("Could not resolve a safe application storage volume name")

        compose(compose_files, "stop", "web", "worker", "api")
        compose(
            compose_files,
            "cp",
            str(database_archive),
            "db:/tmp/teacher-workspace-restore.dump",
        )
        compose(
            compose_files,
            "exec",
            "-T",
            "db",
            "sh",
            "-c",
            'pg_restore --clean --if-exists --no-owner --no-acl -U "$POSTGRES_USER" '
            '-d "$POSTGRES_DB" /tmp/teacher-workspace-restore.dump',
        )

        run(
            [
                "docker",
                "create",
                "--name",
                restore_container,
                "--volume",
                f"{storage_volume}:/app/var/storage",
                "teacher-workspace-backend:local",
                "sh",
                "-c",
                "find /app/var/storage -mindepth 1 -maxdepth 1 -exec rm -rf -- {} + "
                "&& tar -C /app/var/storage -xzf /tmp/storage.tar.gz",
            ]
        )
        run(["docker", "cp", str(storage_archive), f"{restore_container}:/tmp/storage.tar.gz"])
        run(["docker", "start", "--attach", restore_container])
        run(["docker", "rm", restore_container])
        compose(
            compose_files,
            "exec",
            "-T",
            "db",
            "rm",
            "-f",
            "/tmp/teacher-workspace-restore.dump",
        )
        compose(compose_files, "up", "-d")
    finally:
        subprocess.run(
            ["docker", "rm", "-f", restore_container],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        if temporary.exists():
            remove_temporary_directory(backup_dir.parent, temporary)


def compose_paths(values: list[str]) -> list[Path]:
    paths = [Path(value).resolve() for value in values]
    missing = [str(path) for path in paths if not path.is_file()]
    if missing:
        raise BackupError(f"Compose file does not exist: {', '.join(missing)}")
    return paths


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description="独立教师工作台备份与恢复工具")
    root.add_argument(
        "--compose-file",
        action="append",
        default=None,
        help="Compose file; may be supplied more than once (default: compose.yaml)",
    )
    commands = root.add_subparsers(dest="command", required=True)

    create = commands.add_parser("create", help="Create a database and storage backup")
    create.add_argument("--output-dir", default="var/backups")
    create.add_argument("--encrypt", action="store_true")

    verify = commands.add_parser("verify", help="Verify manifest size and SHA-256 checksums")
    verify.add_argument("backup_dir")

    drill = commands.add_parser(
        "drill", help="Restore into an isolated temporary PostgreSQL container"
    )
    drill.add_argument("backup_dir")

    restore = commands.add_parser(
        "restore", help="Replace the current Compose database and storage"
    )
    restore.add_argument("backup_dir")
    restore.add_argument("--confirm-backup-id", required=True)
    restore.add_argument("--replace-current-data", action="store_true")
    restore.add_argument("--safety-output-dir", default="var/backups/pre-restore")
    return root


def main() -> int:
    arguments = parser().parse_args()
    files = compose_paths(arguments.compose_file or ["compose.yaml"])
    try:
        if arguments.command == "create":
            destination = create_backup(
                Path(arguments.output_dir), files, encrypt=arguments.encrypt
            )
            print(destination)
        elif arguments.command == "verify":
            manifest = load_and_verify_manifest(Path(arguments.backup_dir))
            print(json.dumps({"backup_id": manifest["backup_id"], "status": "ok"}))
        elif arguments.command == "drill":
            print(json.dumps(drill_backup(Path(arguments.backup_dir)), ensure_ascii=False))
        elif arguments.command == "restore":
            restore_backup(
                Path(arguments.backup_dir),
                files,
                confirm_backup_id=arguments.confirm_backup_id,
                replace_current_data=arguments.replace_current_data,
                safety_output_root=Path(arguments.safety_output_dir),
            )
            print(json.dumps({"backup_id": arguments.confirm_backup_id, "status": "restored"}))
        return 0
    except BackupError as exc:
        print(f"backup error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
