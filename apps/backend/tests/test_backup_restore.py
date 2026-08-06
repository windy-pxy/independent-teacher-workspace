from __future__ import annotations

import hashlib
import json
import tarfile
from pathlib import Path

import pytest

from teacher_workspace.backup_restore import (
    BackupError,
    decrypt_file,
    encrypt_file,
    load_and_verify_manifest,
    validate_storage_archive,
)


def write_backup(tmp_path: Path) -> Path:
    backup = tmp_path / "20260805T120000Z-deadbeef"
    backup.mkdir()
    database = backup / "database.dump"
    database.write_bytes(b"fictional-postgres-backup")
    storage = backup / "storage.tar.gz"
    source = tmp_path / "fictional.txt"
    source.write_text("虚构学生资料", encoding="utf-8")
    with tarfile.open(storage, "w:gz") as archive:
        archive.add(source, arcname="materials/fictional.txt")
    files = {}
    for name, path in (("database", database), ("storage", storage)):
        files[name] = {
            "name": path.name,
            "size": path.stat().st_size,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }
    (backup / "manifest.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "backup_id": backup.name,
                "encrypted": False,
                "files": files,
            }
        ),
        encoding="utf-8",
    )
    return backup


def test_manifest_and_storage_archive_are_verified(tmp_path: Path) -> None:
    backup = write_backup(tmp_path)
    manifest = load_and_verify_manifest(backup)
    assert manifest["backup_id"] == backup.name
    assert validate_storage_archive(backup / "storage.tar.gz") == 1


def test_tampered_backup_is_rejected(tmp_path: Path) -> None:
    backup = write_backup(tmp_path)
    (backup / "database.dump").write_bytes(b"tampered")
    with pytest.raises(BackupError, match="checksum mismatch"):
        load_and_verify_manifest(backup)


def test_storage_archive_path_traversal_is_rejected(tmp_path: Path) -> None:
    archive_path = tmp_path / "unsafe.tar.gz"
    source = tmp_path / "source.txt"
    source.write_text("not real data", encoding="utf-8")
    with tarfile.open(archive_path, "w:gz") as archive:
        archive.add(source, arcname="../escape.txt")
    with pytest.raises(BackupError, match="Unsafe path"):
        validate_storage_archive(archive_path)


def test_encrypted_backup_round_trip_and_wrong_password(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "database.dump"
    source.write_bytes(b"fictional backup bytes" * 100)
    monkeypatch.setenv("BACKUP_ENCRYPTION_PASSWORD", "test-only-password-with-32-characters")
    encrypted = encrypt_file(source)
    assert encrypted.read_bytes().startswith(b"TWBKUP01")
    restored = tmp_path / "restored.dump"
    decrypt_file(encrypted, restored)
    assert restored.read_bytes() == b"fictional backup bytes" * 100

    monkeypatch.setenv("BACKUP_ENCRYPTION_PASSWORD", "wrong-test-password-with-32-characters")
    with pytest.raises(BackupError, match="incorrect|modified"):
        decrypt_file(encrypted, tmp_path / "wrong.dump")
