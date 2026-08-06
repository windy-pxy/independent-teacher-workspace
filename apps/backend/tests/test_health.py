import pytest
from httpx import ASGITransport, AsyncClient

from teacher_workspace.health import database_readiness
from teacher_workspace.main import app


async def ready_database() -> dict[str, str]:
    return {"database": "ok", "migration": "phase0_foundation"}


@pytest.mark.asyncio
async def test_live_health() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/health/live")
    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "api",
        "database": None,
        "migration": None,
    }
    assert response.headers["X-Request-ID"]
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["Referrer-Policy"] == "same-origin"
    assert response.headers["Cache-Control"] == "no-store"


@pytest.mark.asyncio
async def test_ready_health() -> None:
    app.dependency_overrides[database_readiness] = ready_database
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/health/ready")
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 200
    assert response.json()["database"] == "ok"


@pytest.mark.asyncio
async def test_unsafe_request_id_is_not_reflected() -> None:
    unsafe = "bad request id !"
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/health/live", headers={"X-Request-ID": unsafe})
    assert response.status_code == 200
    assert response.headers["X-Request-ID"] != unsafe
