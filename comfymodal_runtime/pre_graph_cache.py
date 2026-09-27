"""E25 pre-graph exact-identity cache (fail-closed).

Cache for pure, request-reusable pre-graph derivations whose INPUTS are
stable across requests with the same workflow/model/runtime identity:

  * ``request_model_key`` / ``request_prefill_key`` / ``request_model_spec``
    (``derive_model_key`` / ``derive_prefill_key`` / ``build_restore_model_spec``)
  * request snapshot-seed payload (``build_invocation_seed_payload``)

The identity key deliberately contains every input that can affect the
derived value.  Request-specific inputs (seed, prompt text, conditioning,
request IDs) are never part of the key and are never cached.

Fail-closed semantics: a cache entry is used ONLY when the caller passes the
exact identity key that was used to store it, and only for PURE derivations
(no hydration of mutable container state — hydration stays on the caller
thread).  Any exception during lookup returns ``None`` (miss), never raising.
"""

from __future__ import annotations

import threading
from typing import Any, Callable, Optional


class PreGraphCache:
    """Thread-safe exact-identity cache for pure pre-graph derivations."""

    def __init__(self, max_entries: int = 16) -> None:
        self._lock = threading.Lock()
        self._max_entries = max_entries
        self._entries: dict[str, tuple[Any, int]] = {}  # key -> (value, seq)
        self._seq = 0

    def _evict_locked(self) -> None:
        # Simple LRU via insertion sequence; bounded, best-effort.
        while len(self._entries) > self._max_entries:
            oldest_key = min(self._entries, key=lambda k: self._entries[k][1])
            del self._entries[oldest_key]

    def get(self, key: str) -> Any:
        """Return the cached value for *key*, or None on miss/error."""
        if not key:
            return None
        try:
            with self._lock:
                entry = self._entries.get(key)
                if entry is None:
                    return None
                self._seq += 1
                self._entries[key] = (entry[0], self._seq)
                return entry[0]
        except Exception:
            return None

    def put(self, key: str, value: Any) -> None:
        """Store *value* under *key* (never raises)."""
        if not key or value is None:
            return
        try:
            with self._lock:
                self._seq += 1
                self._entries[key] = (value, self._seq)
                self._evict_locked()
        except Exception:
            pass

    def clear(self) -> None:
        try:
            with self._lock:
                self._entries.clear()
        except Exception:
            pass

    def __len__(self) -> int:
        try:
            with self._lock:
                return len(self._entries)
        except Exception:
            return 0


# Module-level singleton.  The container runs at most one request at a time,
# so a single cache is correct; it is bounded and cleared on identity change.
_CACHE = PreGraphCache()


def get_pre_graph_cache() -> PreGraphCache:
    """Return the module-level pre-graph cache (thread-safe)."""
    return _CACHE


def with_cache(
    cache: PreGraphCache,
    key: str,
    compute: Callable[[], Any],
) -> Any:
    """Compute-or-reuse a PURE derivation guarded by an exact identity key.

    Returns the cached value on exact-key hit; otherwise computes via
    *compute*, stores under *key*, and returns the fresh value.  Never
    raises for cache reasons; a raising *compute* propagates so the
    caller's existing fail-closed path is unchanged.
    """
    if not key:
        return compute()
    hit = cache.get(key)
    if hit is not None:
        return hit
    value = compute()
    if value is not None:
        cache.put(key, value)
    return value
