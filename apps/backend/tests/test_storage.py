from pathlib import Path

import httpx
import pytest

from teacher_workspace.providers.storage import (
    LocalStorageProvider,
    StorageProviderError,
    SupabaseStorageProvider,
)


@pytest.mark.asyncio
async def test_local_storage_rejects_path_traversal(tmp_path: Path) -> None:
    storage = LocalStorageProvider(tmp_path)
    with pytest.raises(ValueError, match="object key"):
        await storage.save("../secret.txt", b"nope")


@pytest.mark.asyncio
async def test_local_storage_round_trip(tmp_path: Path) -> None:
    storage = LocalStorageProvider(tmp_path)
    await storage.save("fake-student/example.txt", b"safe fixture")
    assert await storage.read("fake-student/example.txt") == b"safe fixture"
    await storage.delete("fake-student/example.txt")
    assert not (tmp_path / "fake-student/example.txt").exists()


@pytest.mark.asyncio
async def test_supabase_storage_uses_server_credentials_and_private_endpoints() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path.endswith("/object/sign/private/materials/test file.png"):
            return httpx.Response(200, json={"signedURL": "/storage/v1/object/sign/example"})
        if "/object/authenticated/" in request.url.path:
            return httpx.Response(200, content=b"fictional-image")
        return httpx.Response(200, json={})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = SupabaseStorageProvider(
            "https://project.supabase.co",
            "service-role-test-only",
            "private",
            client=client,
        )
        await provider.save("materials/test file.png", b"fictional-image")
        assert await provider.read("materials/test file.png") == b"fictional-image"
        assert (
            await provider.temporary_url("materials/test file.png", 60)
            == "https://project.supabase.co/storage/v1/object/sign/example"
        )
        await provider.delete("materials/test file.png")

    assert [request.method for request in requests] == ["POST", "GET", "POST", "DELETE"]
    assert all(
        request.headers["authorization"] == "Bearer service-role-test-only"
        for request in requests
    )
    assert not any("service-role-test-only" in str(request.url) for request in requests)


@pytest.mark.asyncio
async def test_supabase_storage_rejects_unsafe_keys_and_sanitizes_errors() -> None:
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda _: httpx.Response(503, text="sensitive upstream body")
        )
    ) as client:
        provider = SupabaseStorageProvider(
            "https://project.supabase.co",
            "service-role-test-only",
            "private",
            client=client,
        )
        with pytest.raises(ValueError, match="object key"):
            await provider.read("../escape")
        with pytest.raises(StorageProviderError, match="status 503") as error:
            await provider.read("safe/file.png")
        assert "sensitive upstream body" not in str(error.value)
