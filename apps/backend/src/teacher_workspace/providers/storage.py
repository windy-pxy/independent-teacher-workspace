from __future__ import annotations

import asyncio
import re
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import quote

import httpx

from teacher_workspace.config import Settings


class StorageProvider(Protocol):
    async def save(self, object_key: str, content: bytes) -> None: ...

    async def read(self, object_key: str) -> bytes: ...

    async def delete(self, object_key: str) -> None: ...

    async def temporary_url(self, object_key: str, expires_seconds: int = 300) -> str: ...


class StorageProviderError(RuntimeError):
    pass


def validate_object_key(object_key: str) -> str:
    if (
        not object_key
        or len(object_key) > 1024
        or "\\" in object_key
        or "//" in object_key
        or object_key.startswith("/")
        or object_key.endswith("/")
    ):
        raise ValueError("Invalid storage object key")
    parts = object_key.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise ValueError("Invalid storage object key")
    return object_key


class LocalStorageProvider:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()

    def _safe_path(self, object_key: str) -> Path:
        validate_object_key(object_key)
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


class SupabaseStorageProvider:
    def __init__(
        self,
        url: str,
        service_role_key: str,
        bucket: str,
        *,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        if not url.startswith("https://"):
            raise ValueError("Supabase URL must use HTTPS")
        if not service_role_key:
            raise ValueError("Supabase service role key is required")
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", bucket):
            raise ValueError("Invalid Supabase storage bucket")
        self.project_url = url.rstrip("/")
        self.api_url = f"{self.project_url}/storage/v1"
        self.bucket = bucket
        self.headers = {
            "apikey": service_role_key,
            "Authorization": f"Bearer {service_role_key}",
        }
        self.client = client

    def _encoded_key(self, object_key: str) -> str:
        return "/".join(
            quote(part, safe="") for part in validate_object_key(object_key).split("/")
        )

    async def _request(
        self,
        method: str,
        url: str,
        *,
        content: bytes | None = None,
        json: Any = None,
        headers: dict[str, str] | None = None,
    ) -> httpx.Response:
        if self.client is not None:
            return await self.client.request(
                method, url, content=content, json=json, headers=headers
            )
        async with httpx.AsyncClient(timeout=30) as client:
            return await client.request(method, url, content=content, json=json, headers=headers)

    @staticmethod
    def _require_success(response: httpx.Response, expected: set[int]) -> None:
        if response.status_code not in expected:
            raise StorageProviderError(
                f"Supabase Storage request failed with status {response.status_code}"
            )

    async def save(self, object_key: str, content: bytes) -> None:
        encoded = self._encoded_key(object_key)
        response = await self._request(
            "POST",
            f"{self.api_url}/object/{self.bucket}/{encoded}",
            content=content,
            headers={
                **self.headers,
                "Content-Type": "application/octet-stream",
                "x-upsert": "false",
            },
        )
        self._require_success(response, {200, 201})

    async def read(self, object_key: str) -> bytes:
        encoded = self._encoded_key(object_key)
        response = await self._request(
            "GET",
            f"{self.api_url}/object/authenticated/{self.bucket}/{encoded}",
            headers=self.headers,
        )
        self._require_success(response, {200})
        return response.content

    async def delete(self, object_key: str) -> None:
        validate_object_key(object_key)
        response = await self._request(
            "DELETE",
            f"{self.api_url}/object/{self.bucket}",
            json={"prefixes": [object_key]},
            headers=self.headers,
        )
        self._require_success(response, {200})

    async def temporary_url(self, object_key: str, expires_seconds: int = 300) -> str:
        encoded = self._encoded_key(object_key)
        if not 1 <= expires_seconds <= 3600:
            raise ValueError("Signed URL expiry must be between 1 and 3600 seconds")
        response = await self._request(
            "POST",
            f"{self.api_url}/object/sign/{self.bucket}/{encoded}",
            json={"expiresIn": expires_seconds},
            headers=self.headers,
        )
        self._require_success(response, {200})
        payload = response.json()
        signed = payload.get("signedURL") or payload.get("signedUrl")
        if not isinstance(signed, str) or not signed:
            raise StorageProviderError("Supabase Storage returned an invalid signed URL")
        if signed.startswith("https://"):
            return signed
        if signed.startswith("/storage/v1/"):
            return f"{self.project_url}{signed}"
        return f"{self.api_url}/{signed.lstrip('/')}"


def create_storage_provider(settings: Settings) -> StorageProvider:
    if settings.storage_backend == "local":
        return LocalStorageProvider(settings.local_storage_root)
    if settings.storage_backend == "supabase":
        if not settings.supabase_url or not settings.supabase_service_role_key:
            raise RuntimeError("Supabase storage configuration is incomplete")
        return SupabaseStorageProvider(
            settings.supabase_url,
            settings.supabase_service_role_key,
            settings.supabase_storage_bucket,
        )
    raise RuntimeError(f"Unsupported storage backend: {settings.storage_backend}")
