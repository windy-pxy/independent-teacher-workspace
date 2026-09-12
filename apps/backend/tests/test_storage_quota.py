import asyncio
import os
import uuid

import pytest
from fastapi import HTTPException
from sqlalchemy import delete
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from teacher_workspace.config import Settings
from teacher_workspace.models import UploadedMaterial, User
from teacher_workspace.storage_quota import ensure_upload_capacity


@pytest.mark.asyncio
async def test_postgres_serializes_concurrent_upload_quota_reservations() -> None:
    url = os.environ.get("STORAGE_QUOTA_TEST_DATABASE_URL")
    if not url:
        pytest.skip("requires isolated PostgreSQL validation database")
    assert make_url(url).database == "teacher_multitenant_test"
    engine = create_async_engine(url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    user_id = uuid.uuid4()
    async with factory() as session, session.begin():
        session.add(
            User(
                id=user_id,
                username=f"fictional-storage-{user_id.hex[:10]}",
                password_hash="fictional-not-a-login-hash",
            )
        )
    settings = Settings(
        _env_file=None,
        session_secret="fictional-storage-quota-secret-value",
        max_upload_bytes=10,
        user_upload_quota_bytes=15,
    )

    async def reserve(index: int) -> bool:
        async with factory() as session, session.begin():
            try:
                await ensure_upload_capacity(session, user_id, 6, settings)
            except HTTPException as exc:
                assert exc.status_code == 413
                return False
            session.add(
                UploadedMaterial(
                    owner_user_id=user_id,
                    purpose="OTHER_REFERENCE",
                    display_name=f"虚构并发资料-{index}.txt",
                    object_key=f"fictional/{user_id}/{index}.txt",
                    mime_type="text/plain",
                    size_bytes=6,
                    sha256=f"{index:064x}",
                    processing_status="READY",
                )
            )
            return True

    results = await asyncio.gather(*(reserve(index) for index in range(10)))
    assert results.count(True) == 2
    assert results.count(False) == 8
    async with factory() as session, session.begin():
        await session.execute(delete(User).where(User.id == user_id))
    await engine.dispose()
