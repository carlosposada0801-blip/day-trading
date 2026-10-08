import time
from typing import Any, Awaitable, Callable

_store: dict[str, tuple[float, Any]] = {}


async def cached(key: str, ttl: int, fn: Callable[[], Awaitable[Any]]) -> Any:
    """Return a cached value for `key`, recomputing it once older than `ttl` seconds."""
    hit = _store.get(key)
    if hit and time.monotonic() - hit[0] < ttl:
        return hit[1]
    value = await fn()
    _store[key] = (time.monotonic(), value)
    return value


def clear() -> None:
    _store.clear()
