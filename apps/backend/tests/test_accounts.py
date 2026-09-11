import asyncio
import os
from collections.abc import AsyncIterator

import pytest
from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from teacher_workspace.auth import hash_token
from teacher_workspace.auth_limits import consume_auth_budget
from teacher_workspace.config import Settings, get_settings
from teacher_workspace.db import get_session
from teacher_workspace.main import app
from teacher_workspace.models import AuditLog, Base, User

ORIGIN = {"Origin": "http://test"}
PASSWORD = "fictional-strong-password"


@pytest.fixture
async def accounts() -> AsyncIterator[
    tuple[AsyncClient, async_sessionmaker[AsyncSession], Settings]
]:
    url = os.environ.get("ACCOUNT_TEST_DATABASE_URL", "sqlite+aiosqlite:///:memory:")
    if url.startswith("postgresql"):
        assert make_url(url).database == "teacher_accounts_test", (
            "Only isolated test database allowed"
        )
    engine = create_async_engine(url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    if url.startswith("sqlite"):
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

    async def sessions() -> AsyncIterator[AsyncSession]:
        async with factory() as session:
            yield session

    settings = Settings(
        _env_file=None,
        registration_enabled=True,
        session_secret="fictional-secret-for-account-tests-only",
        trusted_origins=["http://test"],
        ai_provider="mock",
    )
    app.dependency_overrides[get_session] = sessions
    app.dependency_overrides[get_settings] = lambda: settings
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            yield client, factory, settings
    finally:
        app.dependency_overrides.clear()
        if url.startswith("postgresql"):
            async with engine.begin() as connection:
                await connection.execute(text("TRUNCATE users, auth_rate_limits CASCADE"))
        await engine.dispose()


async def register(client: AsyncClient, username: str = "fictional-teacher") -> str:
    response = await client.post(
        "/api/v1/auth/register",
        headers=ORIGIN,
        json={
            "username": username,
            "password": PASSWORD,
            "password_confirmation": PASSWORD,
        },
    )
    assert response.status_code == 201, response.text
    return str(response.json()["recovery_code"])


async def login(client: AsyncClient, password: str = PASSWORD) -> dict[str, str]:
    response = await client.post(
        "/api/v1/auth/login",
        headers=ORIGIN,
        json={
            "username": "fictional-teacher",
            "password": password,
        },
    )
    assert response.status_code == 200, response.text
    return {**ORIGIN, "X-CSRF-Token": client.cookies["teacher_workspace_session_csrf"]}


@pytest.mark.asyncio
async def test_registration_hashes_secrets_and_preserves_independent_users(accounts):
    client, factory, settings = accounts
    code = await register(client)
    await register(client, "fictional-other")
    async with factory() as session:
        users = list(await session.scalars(select(User)))
        assert len(users) == 2 and all(user.is_active for user in users)
        user = next(user for user in users if user.username == "fictional-teacher")
        assert user.password_hash.startswith("$argon2id$")
        assert user.recovery_code_hash == hash_token(code)
        assert not user.ai_access_enabled
        audits = list(await session.scalars(select(AuditLog)))
        assert all(PASSWORD not in str(row.change_summary) for row in audits)
        assert all(code not in str(row.change_summary) for row in audits)
    response = await client.post(
        "/api/v1/auth/register",
        headers=ORIGIN,
        json={
            "username": "fictional-teacher",
            "password": PASSWORD,
            "password_confirmation": PASSWORD,
        },
    )
    assert response.status_code == 409
    settings.registration_enabled = False
    assert (await client.get("/api/v1/auth/registration")).json() == {"enabled": False}
    response = await client.post(
        "/api/v1/auth/register",
        headers=ORIGIN,
        json={
            "username": "fictional-third",
            "password": PASSWORD,
            "password_confirmation": PASSWORD,
        },
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_invalid_registration_never_echoes_password(accounts):
    client, _, _ = accounts
    response = await client.post(
        "/api/v1/auth/register",
        headers=ORIGIN,
        json={
            "username": "fictional-teacher",
            "password": PASSWORD,
            "password_confirmation": "mismatch",
        },
    )
    assert response.status_code == 422
    assert PASSWORD not in response.text and "mismatch" not in response.text
    response = await client.post(
        "/api/v1/auth/register",
        headers={"Origin": "https://evil.invalid"},
        json={
            "username": "fictional-teacher",
            "password": PASSWORD,
            "password_confirmation": PASSWORD,
        },
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_password_change_revokes_all_sessions_without_deleting_student(accounts):
    client, _, _ = accounts
    await register(client)
    headers = await login(client)
    student = await client.post(
        "/api/v1/students", headers=headers, json={"display_name": "虚构安全学生"}
    )
    assert student.status_code == 201
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as second:
        await login(second)
        assert len((await client.get("/api/v1/auth/sessions")).json()) == 2
        response = await client.post(
            "/api/v1/auth/password",
            headers=headers,
            json={
                "current_password": PASSWORD,
                "new_password": "fictional-new-password",
            },
        )
        assert response.status_code == 204, response.text
        assert (await client.get("/api/v1/auth/me")).status_code == 401
        assert (await second.get("/api/v1/auth/me")).status_code == 401
        await login(second, "fictional-new-password")
        assert (await second.get("/api/v1/students")).json()[0]["id"] == student.json()["id"]


@pytest.mark.asyncio
async def test_recovery_is_single_use_and_rotation_invalidates_old_code(accounts):
    client, _, _ = accounts
    old_code = await register(client)
    headers = await login(client)
    response = await client.post(
        "/api/v1/auth/recovery-code", headers=headers, json={"current_password": PASSWORD}
    )
    assert response.status_code == 200
    code = response.json()["recovery_code"]
    payload = {
        "username": "fictional-teacher",
        "recovery_code": old_code,
        "new_password": "fictional-recovered-password",
    }
    assert (
        await client.post("/api/v1/auth/reset-password", headers=ORIGIN, json=payload)
    ).status_code == 400
    payload["recovery_code"] = code
    assert (
        await client.post("/api/v1/auth/reset-password", headers=ORIGIN, json=payload)
    ).status_code == 204
    assert (await client.get("/api/v1/auth/me")).status_code == 401
    assert (
        await client.post("/api/v1/auth/reset-password", headers=ORIGIN, json=payload)
    ).status_code == 400
    await login(client, "fictional-recovered-password")


@pytest.mark.asyncio
async def test_revoke_others_and_registration_budget(accounts):
    client, _, settings = accounts
    settings.registration_limit_per_hour = 1
    await register(client)
    response = await client.post(
        "/api/v1/auth/register",
        headers=ORIGIN,
        json={
            "username": "fictional-next",
            "password": PASSWORD,
            "password_confirmation": PASSWORD,
        },
    )
    assert response.status_code == 429 and "retry-after" in response.headers
    headers = await login(client)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as second:
        await login(second)
        assert (await client.post("/api/v1/auth/sessions/revoke-others")).status_code == 403
        assert (
            await client.post("/api/v1/auth/sessions/revoke-others", headers=headers)
        ).status_code == 204
        assert (await client.get("/api/v1/auth/me")).status_code == 200
        assert (await second.get("/api/v1/auth/me")).status_code == 401


@pytest.mark.asyncio
async def test_budget_survives_new_database_session(accounts):
    _, factory, _ = accounts
    async with factory() as first:
        await consume_auth_budget(first, "fictional-durable-limit", limit=1, seconds=3600)
    async with factory() as second:
        with pytest.raises(HTTPException) as caught:
            await consume_auth_budget(second, "fictional-durable-limit", limit=1, seconds=3600)
        assert caught.value.status_code == 429


@pytest.mark.asyncio
@pytest.mark.skipif(
    not os.environ.get("ACCOUNT_TEST_DATABASE_URL"), reason="Requires isolated PostgreSQL"
)
async def test_concurrent_duplicate_registration_is_atomic(accounts):
    client, factory, _ = accounts
    payload = {
        "username": "fictional-race",
        "password": PASSWORD,
        "password_confirmation": PASSWORD,
    }
    replies = await asyncio.gather(
        *[client.post("/api/v1/auth/register", headers=ORIGIN, json=payload) for _ in range(2)]
    )
    assert sorted(response.status_code for response in replies) == [201, 409]
    async with factory() as session:
        assert len(list(await session.scalars(select(User)))) == 1
        assert len(list(await session.scalars(select(AuditLog)))) == 1
