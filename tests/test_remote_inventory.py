"""Tests for the cached remote inventory (remote_inventory.py).

The inventory is one CPU-only ``get_volume_status`` round trip shared by the
dependency report, so the contract that matters is: one call in steady state,
a fresh call after anything mutates a volume, and a silent fall back to
local-only truth when Modal is unreachable. The fetcher is swappable so no
test needs a live Modal app.
"""

from __future__ import annotations

import asyncio
import unittest

import pytest

from tests import _test_env  # noqa: F401  (hide real ComfyUI from sys.path)

import remote_inventory

pytestmark = pytest.mark.fast_unit


def _payload(tag: str = "v1") -> dict:
    return {
        "models": [{"folder": "checkpoints", "name": f"{tag}.safetensors", "size": 2048}],
        "custom_nodes": ["ComfyUI-KJNodes"],
    }


_DEFAULT = object()


class RemoteInventoryTestCase(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        # Module-level state is process wide; reset it so each test starts cold
        # and so no snapshot leaks between tests or into other suites.
        self._saved_fetch = remote_inventory._fetch
        remote_inventory._snapshot = None
        remote_inventory._snapshot_mono = 0.0
        remote_inventory._generation = 0

    def tearDown(self) -> None:
        remote_inventory._fetch = self._saved_fetch
        remote_inventory._snapshot = None
        remote_inventory._snapshot_mono = 0.0
        remote_inventory._generation = 0

    def _counting_fetch(self, result=_DEFAULT, raises: bool = False):
        calls: list[int] = []

        async def _fetch():
            calls.append(1)
            if raises:
                raise RuntimeError("modal unreachable")
            return _payload() if result is _DEFAULT else result

        remote_inventory._fetch = _fetch
        return calls

    # ── caching ──────────────────────────────────────────────────────────

    async def test_second_call_is_served_from_cache(self):
        calls = self._counting_fetch()

        first = await remote_inventory.get_inventory()
        second = await remote_inventory.get_inventory()

        self.assertEqual(len(calls), 1)
        self.assertIs(first, second)
        self.assertEqual((second or {}).get("custom_nodes"), ["ComfyUI-KJNodes"])

    async def test_expired_ttl_refetches(self):
        calls = self._counting_fetch()

        await remote_inventory.get_inventory()
        # ttl_s=0 disables the fresh-window check entirely, so the next call
        # must go back to Modal rather than serve a stale snapshot.
        await remote_inventory.get_inventory(ttl_s=0.0)

        self.assertEqual(len(calls), 2)

    async def test_invalidate_drops_the_snapshot(self):
        calls = self._counting_fetch()

        await remote_inventory.get_inventory()
        remote_inventory.invalidate()
        await remote_inventory.get_inventory()

        self.assertEqual(len(calls), 2)

    async def test_set_fetch_invalidates_so_stale_truth_is_never_reused(self):
        calls = self._counting_fetch()
        await remote_inventory.get_inventory()

        async def _other():
            calls.append(1)
            return _payload("v2")

        remote_inventory.set_fetch(_other)
        result = await remote_inventory.get_inventory()

        self.assertEqual(len(calls), 2)
        self.assertEqual((result or {}).get("models", [{}])[0].get("name"), "v2.safetensors")

    # ── single flight ────────────────────────────────────────────────────

    async def test_concurrent_callers_share_one_round_trip(self):
        calls = self._counting_fetch()

        results = await asyncio.gather(
            *(remote_inventory.get_inventory() for _ in range(8))
        )

        self.assertEqual(len(calls), 1)
        for result in results:
            self.assertEqual(result, _payload())

    # ── failure handling ─────────────────────────────────────────────────

    async def test_fetch_failure_returns_none_and_is_not_cached(self):
        calls = self._counting_fetch(raises=True)

        self.assertIsNone(await remote_inventory.get_inventory())
        self.assertIsNone(await remote_inventory.get_inventory())

        # Never cached, so a recovered Modal is picked up on the next request
        # instead of the report staying blind until restart.
        self.assertEqual(len(calls), 2)

    async def test_non_dict_payload_returns_none(self):
        for junk in (None, [], "garbage", 7):
            remote_inventory.invalidate()
            self._counting_fetch(result=junk)
            self.assertIsNone(await remote_inventory.get_inventory(), junk)

    async def test_failure_never_serves_a_stale_snapshot(self):
        # A refresh that fails falls back to local-only truth rather than
        # reporting an inventory that may no longer exist. The report shows no
        # error, so this is the conservative, auditable choice: the caller gets
        # None and the resolver's local path runs.
        calls = self._counting_fetch()
        await remote_inventory.get_inventory()

        async def _boom():
            calls.append(1)
            raise RuntimeError("modal unreachable")

        remote_inventory._fetch = _boom
        self.assertIsNone(await remote_inventory.get_inventory(ttl_s=0.0))

    async def test_sync_fetch_callable_is_awaited(self):
        # A fetcher that returns a plain dict (not a coroutine) is still valid;
        # a sync callable returning an awaitable must also be awaited.
        remote_inventory._fetch = lambda: _payload("sync")
        names = [(await remote_inventory.get_inventory()) or {}]
        self.assertEqual(names[0].get("models", [{}])[0].get("name"), "sync.safetensors")


if __name__ == "__main__":
    unittest.main()
