from __future__ import annotations

import asyncio
import random
from typing import Awaitable, Callable, TypeVar

from ..errors import LLMError

T = TypeVar("T")


async def retry_async(
    fn: Callable[[], Awaitable[T]],
    *,
    attempts: int = 5,
    base: float = 1.0,
    cap: float = 30.0,
    on_retry: Callable[..., None] | None = None,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> T:
    """Exponential backoff with jitter; honours Retry-After when the provider sends it."""
    for attempt in range(1, attempts + 1):
        try:
            return await fn()
        except LLMError as exc:
            if not exc.retryable or attempt == attempts:
                raise
            if exc.retry_after is not None:
                delay = min(cap, max(0.0, exc.retry_after))
            else:
                delay = min(cap, base * 2 ** (attempt - 1)) * (0.5 + random.random() / 2)
            if on_retry:
                on_retry(attempt=attempt, delay=delay, error=str(exc))
            await sleep(delay)
    raise AssertionError("unreachable")
