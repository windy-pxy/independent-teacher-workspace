from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Protocol

from teacher_workspace.config import Settings


class StorageProvider(Protocol):
    async def save(self, object_key: str, content: bytes) -> None: ...

    async def read(self, object_key: str) -> bytes: ...

    async def delete(self, object_key: str) -> None: ...

    async def temporary_url(self, object_key: str, expires_seconds: int = 300) -> str: ...


class LocalStorageProvider:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()

    def _safe_path(self, object_key: str) -> Path:
        candidate = (self.root / object_key).resolve()
        if candidate != self.root and self.root not in candidate.parents:
            raise ValueError("Object key escapes storage root")
        return candidate

    async def save(self, object_key: str, content: bytes) -> None:
        path = self._safe_path(object_key)
        await asyncio.to_thread(path.parent.mkdir, parents=True, exist_ok=True)
        await asyncio.to_thread(path.write_bytes, content)

    async def read(self, object_key: str) -> bytes:
        return await asyncio.to_thread(self._safe_path(object_key).read_bytes)

    async def delete(self, object_key: str) -> None:
        await asyncio.to_thread(self._safe_path(object_key).unlink, missing_ok=True)

    async def temporary_url(self, object_key: str, expires_seconds: int = 300) -> str:
        del expires_seconds
        return self._safe_path(object_key).as_uri()


def create_storage_provider(settings: Settings) -> StorageProvider:
    if settings.storage_backend == "local":
        return LocalStorageProvider(settings.local_storage_root)
    raise RuntimeError(f"Unsupported storage backend: {settings.storage_backend}")
