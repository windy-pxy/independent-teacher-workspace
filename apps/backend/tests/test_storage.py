from pathlib import Path

import pytest

from teacher_workspace.providers.storage import LocalStorageProvider


@pytest.mark.asyncio
async def test_local_storage_rejects_path_traversal(tmp_path: Path) -> None:
    storage = LocalStorageProvider(tmp_path)
    with pytest.raises(ValueError, match="escapes storage root"):
        await storage.save("../secret.txt", b"nope")


@pytest.mark.asyncio
async def test_local_storage_round_trip(tmp_path: Path) -> None:
    storage = LocalStorageProvider(tmp_path)
    await storage.save("fake-student/example.txt", b"safe fixture")
    assert await storage.read("fake-student/example.txt") == b"safe fixture"
    await storage.delete("fake-student/example.txt")
    assert not (tmp_path / "fake-student/example.txt").exists()
