"""Regression test for sync/async cache compatibility in get_input_data.

Tests that ``execution.get_input_data()`` does not receive unresolved
coroutines when a custom-node compatibility wrapper passes an async
cache object as the ``execution_list`` parameter.

Pattern tested:
  OutputCacheCompat.get_cache() calls self._cache.get() (async) without
  await → returns coroutine → get_input_data() accesses .outputs →
  AttributeError + RuntimeWarning.
"""
import asyncio
import unittest
import warnings


class _FakeCacheEntry:
    outputs: list

    def __init__(self, outputs):
        self.outputs = outputs
        self.ui = {}


class _AsyncCache:
    """Mimics``HierarchicalCache`` — async get(), sync get_local()."""

    def __init__(self, data=None):
        self._cache = dict(data or {})

    async def get(self, node_id):
        return self._cache.get(node_id)

    def get_local(self, node_id):
        return self._cache.get(node_id)

    def get_cache(self, node_id, _to_id=None):
        # Bug: calls async get() without await
        return self.get(node_id)


class _OutputCacheCompat:
    """Replicates the exact compat wrapper from capture.py."""

    def __init__(self, cache):
        self._cache = cache

    def get_output_cache(self, input_unique_id, unique_id=None):
        if hasattr(self._cache, "get"):
            return self._cache.get(input_unique_id)
        return getattr(self._cache, "outputs", {}).get(input_unique_id, None)

    def get(self, input_unique_id):
        if hasattr(self._cache, "get"):
            return self._cache.get(input_unique_id)
        return getattr(self._cache, "outputs", {}).get(input_unique_id, None)

    def get_cache(self, input_unique_id, unique_id=None):
        if hasattr(self._cache, "get_cache"):
            return self._cache.get_cache(input_unique_id, unique_id)
        return self.get_output_cache(input_unique_id, unique_id)


def _safe_wrap_execution_list(execution_list):
    """The wrapper logic from the comfyapp.py patch (extracted for testing)."""
    if execution_list is not None and hasattr(execution_list, 'get_cache'):

        class _SafeExecutionListWrapper:
            __slots__ = ('__wrapped',)

            def __init__(self, wrapped):
                self.__wrapped = wrapped

            def get_cache(self, from_id, to_id):
                result = self.__wrapped.get_cache(from_id, to_id)
                if asyncio.iscoroutine(result):
                    try:
                        result.close()
                    except Exception:
                        pass
                    if hasattr(self.__wrapped, 'get_local'):
                        return self.__wrapped.get_local(from_id)
                    if (hasattr(self.__wrapped, '_cache')
                            and hasattr(self.__wrapped._cache, 'get_local')):
                        return self.__wrapped._cache.get_local(from_id)
                    return None
                return result

            def __getattr__(self, name):
                return getattr(self.__wrapped, name)

        execution_list = _SafeExecutionListWrapper(execution_list)

    return execution_list


class SyncCacheCompatTests(unittest.TestCase):

    def test_async_cache_get_returns_usable_result_via_get_local_fallback(self):
        """When get_cache() returns a coroutine, fall back to get_local()."""
        cache = _AsyncCache({"node_1": _FakeCacheEntry(outputs=["result"])})
        compat = _OutputCacheCompat(cache)

        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            raw = compat.get_cache("node_1")
            self.assertTrue(
                asyncio.iscoroutine(raw),
                "Sanity: get_cache() should return a coroutine (the bug)",
            )
            raw.close()  # suppress "never awaited" GC warning

        wrapped = _safe_wrap_execution_list(compat)
        result = wrapped.get_cache("node_1", "caller_1")
        self.assertIsNotNone(result)
        self.assertFalse(asyncio.iscoroutine(result))
        self.assertEqual(result.outputs, ["result"])

    def test_missing_node_returns_none_not_coroutine(self):
        """When node is not cached, wrapper returns None without leaking a coroutine."""
        cache = _AsyncCache({})
        compat = _OutputCacheCompat(cache)

        wrapped = _safe_wrap_execution_list(compat)
        result = wrapped.get_cache("missing_node", "caller_1")
        self.assertIsNone(result)

    def test_no_never_awaited_warning(self):
        """The wrapper must not emit 'coroutine was never awaited' warnings."""
        cache = _AsyncCache({"node_1": _FakeCacheEntry(outputs=["ok"])})
        compat = _OutputCacheCompat(cache)
        wrapped = _safe_wrap_execution_list(compat)

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            result = wrapped.get_cache("node_1", "caller_1")

        self.assertIsNotNone(result)
        never_awaited = [
            x for x in w
            if "never awaited" in str(x.message).lower()
        ]
        self.assertEqual(
            len(never_awaited), 0,
            f"Should not emit 'never awaited' warning, got: {never_awaited}",
        )

    def test_async_cache_without_get_local_falls_back_to_none(self):
        """If get_local() is unavailable, treat coroutine return as cache miss."""

        class _CacheNoGetLocal:
            """Async cache without a sync get_local() fallback."""

            def __init__(self, data=None):
                self._cache = dict(data or {})

            async def get(self, node_id):
                return self._cache.get(node_id)

            def get_cache(self, node_id, _to_id=None):
                return self.get(node_id)

        cache = _CacheNoGetLocal(
            {"node_1": _FakeCacheEntry(outputs=["result"])}
        )
        compat = _OutputCacheCompat(cache)

        wrapped = _safe_wrap_execution_list(compat)
        result = wrapped.get_cache("node_1", "caller_1")
        # Without get_local, we can't resolve the coroutine — expect None
        self.assertIsNone(result)

    def test_sync_cache_unchanged(self):
        """A sync-only cache that returns resolved values should not be affected."""
        class SyncCache:
            def __init__(self):
                self._cache = {"node_1": _FakeCacheEntry(outputs=["sync_result"])}

            def get_cache(self, from_id, to_id=None):
                return self._cache.get(from_id)

        cache = SyncCache()
        wrapped = _safe_wrap_execution_list(cache)
        result = wrapped.get_cache("node_1", "caller_1")
        self.assertIsNotNone(result)
        self.assertFalse(asyncio.iscoroutine(result))
        self.assertEqual(result.outputs, ["sync_result"])

    def test_none_execution_list_passthrough(self):
        self.assertIsNone(_safe_wrap_execution_list(None))

    def test_execution_list_without_get_cache_passthrough(self):
        plain_obj = object()
        self.assertIs(plain_obj, _safe_wrap_execution_list(plain_obj))


if __name__ == "__main__":
    unittest.main()
