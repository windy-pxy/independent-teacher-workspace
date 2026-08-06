import pytest

from teacher_workspace.login_throttle import LoginThrottle


@pytest.mark.asyncio
async def test_login_throttle_locks_and_expires_without_storing_username() -> None:
    now = 1000.0
    throttle = LoginThrottle(clock=lambda: now)
    for _ in range(4):
        assert (
            await throttle.failure(
                "fictional-teacher",
                max_failures=5,
                window_seconds=900,
                lock_seconds=300,
            )
            == 0
        )
    assert (
        await throttle.failure(
            "fictional-teacher", max_failures=5, window_seconds=900, lock_seconds=300
        )
        == 300
    )
    assert await throttle.retry_after("fictional-teacher", 900) == 300
    assert "fictional-teacher" not in throttle._attempts

    now += 301
    assert await throttle.retry_after("fictional-teacher", 900) == 0


@pytest.mark.asyncio
async def test_success_clears_failed_login_window() -> None:
    throttle = LoginThrottle(clock=lambda: 1000.0)
    await throttle.failure(
        "fictional-teacher", max_failures=5, window_seconds=900, lock_seconds=300
    )
    await throttle.success("fictional-teacher")
    assert await throttle.retry_after("fictional-teacher", 900) == 0
