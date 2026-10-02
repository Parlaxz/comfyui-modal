"""Cached snapshot of what the Modal app has installed.

One CPU-only ``get_volume_status`` round trip answers both halves of the
dependency question (volume models + volume custom-node packs). The snapshot
is cached for a short TTL and dropped the moment anything mutates a volume,
so a report is one cheap call in steady state and never stale after an action.
"""

from __future__ import annotations

import asyncio
import inspect
import time
from collections.abc import Awaitable, Callable
from typing import Any


TTL_S = 30.0

_snapshot: dict[str, Any] | None = None
_snapshot_mono = 0.0
_generation = 0
_lock = asyncio.Lock()


async def _default_fetch() -> dict[str, Any]:
    """Fetch lazily so this module never imports the plugin entrypoint."""
    from modal_client import get_sync_status

    return await get_sync_status()


_fetch: Callable[[], Awaitable[Any]] = _default_fetch


def set_fetch(fn: Callable[[], Awaitable[Any]]) -> None:
    """Replace the remote fetcher, primarily for tests without Modal."""
    global _fetch
    _fetch = fn
    invalidate()


def invalidate() -> None:
    """Drop the cached remote snapshot after a volume mutation."""
    global _snapshot, _snapshot_mono, _generation
    _snapshot = None
    _snapshot_mono = 0.0
    _generation += 1


def current() -> dict[str, Any] | None:
    """Last successful snapshot, or ``None``. Synchronous; never fetches.

    Lets synchronous readers (version-state derivation, the workflow run gate)
    share the same remote truth an async route already paid for, without
    putting a Modal round trip on their critical path. A stale snapshot is
    better than none here: it is a cache, and its age is bounded by ``TTL_S``
    and reset by every mutation.
    """
    return _snapshot


async def get_inventory(*, ttl_s: float = TTL_S) -> dict[str, Any] | None:
    """Return a cached remote inventory, never propagating fetch failures."""
    global _snapshot, _snapshot_mono
    try:
        ttl = float(ttl_s)
        now = time.monotonic()
        if _snapshot is not None and ttl > 0 and now - _snapshot_mono < ttl:
            return _snapshot

        async with _lock:
            now = time.monotonic()
            if _snapshot is not None and ttl > 0 and now - _snapshot_mono < ttl:
                return _snapshot
            generation = _generation
            fetched = _fetch()
            if inspect.isawaitable(fetched):
                fetched = await fetched
            if not isinstance(fetched, dict):
                return None
            if generation == _generation:
                _snapshot = fetched
                _snapshot_mono = time.monotonic()
            return fetched
    except Exception:
        return None
