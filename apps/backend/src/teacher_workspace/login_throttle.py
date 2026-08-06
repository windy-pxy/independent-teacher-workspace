from __future__ import annotations

import asyncio
import hashlib
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field


@dataclass
class LoginAttemptWindow:
    failures: deque[float] = field(default_factory=deque)
    locked_until: float = 0


class LoginThrottle:
    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self.clock = clock
        self._attempts: dict[str, LoginAttemptWindow] = {}
        self._lock = asyncio.Lock()

    @staticmethod
    def _key(username: str) -> str:
        return hashlib.sha256(username.strip().casefold().encode("utf-8")).hexdigest()

    async def retry_after(self, username: str, window_seconds: int) -> int:
        now = self.clock()
        key = self._key(username)
        async with self._lock:
            window = self._attempts.get(key)
            if window is None:
                return 0
            self._prune(window, now, window_seconds)
            if window.locked_until <= now:
                if not window.failures:
                    self._attempts.pop(key, None)
                return 0
            return max(1, int(window.locked_until - now + 0.999))

    async def failure(
        self,
        username: str,
        *,
        max_failures: int,
        window_seconds: int,
        lock_seconds: int,
    ) -> int:
        now = self.clock()
        key = self._key(username)
        async with self._lock:
            window = self._attempts.setdefault(key, LoginAttemptWindow())
            self._prune(window, now, window_seconds)
            window.failures.append(now)
            if len(window.failures) >= max_failures:
                window.locked_until = now + lock_seconds
                return lock_seconds
            return 0

    async def success(self, username: str) -> None:
        async with self._lock:
            self._attempts.pop(self._key(username), None)

    @staticmethod
    def _prune(window: LoginAttemptWindow, now: float, window_seconds: int) -> None:
        cutoff = now - window_seconds
        while window.failures and window.failures[0] <= cutoff:
            window.failures.popleft()

