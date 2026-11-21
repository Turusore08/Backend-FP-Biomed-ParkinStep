import asyncio
import math
import time
from collections import defaultdict, deque


class InMemorySlidingWindowRateLimiter:
    """Async-safe sliding-window rate limiter for authentication endpoints."""

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._buckets: dict[str, deque[float]] = defaultdict(deque)

    async def check_and_consume(
        self,
        key: str,
        max_attempts: int,
        window_sec: int,
    ) -> tuple[bool, int]:
        now = time.monotonic()
        cutoff = now - window_sec
        async with self._lock:
            bucket = self._buckets[key]
            while bucket and bucket[0] <= cutoff:
                bucket.popleft()

            if len(bucket) >= max_attempts:
                retry_after = max(1, math.ceil(window_sec - (now - bucket[0])))
                return False, retry_after

            bucket.append(now)
            return True, 0
