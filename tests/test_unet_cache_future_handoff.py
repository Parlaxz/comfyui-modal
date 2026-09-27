"""Focused tests for UNET cache future-handoff rules (Requirement B).

Requirement: at future_exists=1 graph-demand path:
- Await existing future exactly once.
- Success: publish/confirm object cache and return the exact completed
  object immediately, never normal loader.
- Failure/cancel: safely remove only matching failed future entry under
  existing locking semantics, emit concise diagnostic
  '[unet_loader_cache] future_handoff=failed fallback_normal_load=1',
  permit exactly one normal fallback.
- Success diagnostic:
  '[unet_loader_cache] future_handoff=success returned_future_object=1'.

Test design: uses real Thread futures in _actual_load_futures so
_consume_actual_load_future runs its real logic (pop, join, check).
The object cache is initially empty; the future thread or the fallback
loader publishes the object.
"""

from __future__ import annotations

import os
import sys
import tempfile
import threading
import time
import types
import unittest
from pathlib import Path
from unittest.mock import patch

from tests.test_comfyapp_runtime_state import load_module


def _make_publishing_thread(cache: dict, key, sentinel) -> threading.Thread:
    """Return a running thread that publishes sentinel to cache[key]
    after a brief delay.  The delay lets the loader's top-of-function
    cache check see MISS, so the future-consumption path is exercised.
    The caller (e.g. _consume_actual_load_future) will join the thread
    and find the published object."""
    def _publish():
        time.sleep(0.02)  # < 20ms — brief enough for test speed, long enough
                          # for the loader's initial cache check to miss
        cache[key] = sentinel
    t = threading.Thread(target=_publish, daemon=True)
    t.start()
    # Do NOT join — let the consumer (_consume_actual_load_future) join.
    return t


class TestUnetCacheFutureHandoff(unittest.TestCase):
    """Future handoff tests using real Thread futures with real consumption.

    Uses an integer loader call count (self._loader_call_count) instead
    of a bool flag, so assertions can test exactly 0 or exactly 1."""

    def setUp(self):
        module = load_module()
        self.module = module
        self.mixin = module._ComfyAPIMixin()
        self.mixin._unet_object_cache = {}
        self.mixin._unet_cache_hits = 0
        self.mixin._unet_cache_misses = 0
        self.mixin._model_cpu_cache = {}
        self.mixin._actual_load_futures = {}
        self.mixin._actual_load_future_meta = {}
        self.mixin._actual_load_owner_thread = {}
        self.mixin._original_loaders_store = {}
        self.mixin._unet_load_diagnostics = {}
        self.mixin._actual_load_future_errors = {}
        self.mixin._actual_load_locks = {}
        self.mixin._restore_timing = None
        # Integer loader call count (not bool) — assert exactly 0 or 1
        self._loader_call_count = 0

    def _stub_env(self, test_path: str):
        """Stub folder_paths and nodes, return (key, sentinel).

        The object cache is intentionally NOT pre-populated here so
        the future-consumption path is exercised.
        """
        sentinel = object()
        key = self.mixin._unet_cache_key(test_path, "default")
        # NOT putting in object cache — future thread will publish.

        folder_paths_stub = types.ModuleType("folder_paths")
        folder_paths_stub.get_full_path = lambda folder, name: (
            test_path if folder == "unet" else ""
        )

        nodes_stub = types.ModuleType("nodes")

        class FakeUNETLoader:
            pass

        def _fake_load(self_node, **kwargs):
            self._loader_call_count += 1
            result_obj = object()  # different from sentinel
            return (result_obj,)

        FakeUNETLoader.load_unet = _fake_load
        nodes_stub.NODE_CLASS_MAPPINGS = {"UNETLoader": FakeUNETLoader}

        original_fp = self.module.sys.modules.get("folder_paths")
        original_nodes = self.module.sys.modules.get("nodes")
        self.module.sys.modules["folder_paths"] = folder_paths_stub
        self.module.sys.modules["nodes"] = nodes_stub

        self.addCleanup(lambda: self._restore_modules(original_fp, original_nodes))
        return key, sentinel

    def _restore_modules(self, original_fp, original_nodes):
        if original_fp is not None:
            self.module.sys.modules["folder_paths"] = original_fp
        else:
            self.module.sys.modules.pop("folder_paths", None)
        if original_nodes is not None:
            self.module.sys.modules["nodes"] = original_nodes
        else:
            self.module.sys.modules.pop("nodes", None)

    def _add_publishing_future(self, key, sentinel, status="completed"):
        """Add a future whose thread publishes sentinel to the object cache
        then completes.  The thread already finished (started+joined in
        helper) so _consume_actual_load_future will find a completed thread."""
        thread = _make_publishing_thread(self.mixin._unet_object_cache, key, sentinel)
        self.mixin._actual_load_futures[key] = thread
        self.mixin._actual_load_future_meta[key] = {
            "source": "restore_background_unet",
            "status": status,
        }

    def _add_non_publishing_future(self, key, status="failed"):
        """Add a future that completed but did NOT publish to object cache."""
        thread = threading.Thread(target=lambda: None, daemon=True)
        thread.start()
        thread.join(timeout=5)
        self.mixin._actual_load_futures[key] = thread
        self.mixin._actual_load_future_meta[key] = {
            "source": "restore_background_unet",
            "status": status,
        }

    def _patch_loader(self):
        """Apply the UNET loader patch and return the patched class."""
        self.mixin._patch_unet_loader_cache()
        return self.module.sys.modules["nodes"].NODE_CLASS_MAPPINGS["UNETLoader"]

    # ── Success: future consumed + cache populated by thread → immediate return ──

    def test_future_handoff_success_returns_cached_object(self):
        """Future consumed + cache hit → return cached object immediately,
        normal loader count 0."""
        with tempfile.TemporaryDirectory() as tmp:
            test_path = Path(tmp, "test-unet.safetensors")
            test_path.write_text("dummy")
            key, sentinel = self._stub_env(str(test_path))
            # Future thread publishes sentinel to cache
            self._add_publishing_future(key, sentinel)

            cls = self._patch_loader()
            result = cls().load_unet(
                unet_name="test-unet.safetensors",
                weight_dtype="default",
            )
            self.assertIs(result[0], sentinel,
                          "must return the exact object published by future")
            self.assertEqual(
                self.mixin._unet_cache_hits, 1,
                "cache hits must increment on future handoff",
            )
            self.assertEqual(
                self._loader_call_count, 0,
                "original loader must NOT be called on future success (count 0)",
            )
            # Future must have been removed after consumption
            self.assertNotIn(key, self.mixin._actual_load_futures,
                             "future must be removed after consumption")

    # ── Failure: future consumed but object not in cache / meta says failed ──

    def test_future_handoff_failure_falls_to_normal_load(self):
        """Future consumed but failed meta → fallback to normal load,
        original loader called exactly once, future entry removed."""
        with tempfile.TemporaryDirectory() as tmp:
            test_path = Path(tmp, "test-unet-fail.safetensors")
            test_path.write_text("dummy")
            key = self.mixin._unet_cache_key(str(test_path), "default")
            self._stub_env(str(test_path))

            # Add a non-publishing future marked as failed
            self._add_non_publishing_future(key, status="failed")

            cls = self._patch_loader()
            result = cls().load_unet(
                unet_name="test-unet-fail.safetensors",
                weight_dtype="default",
            )
            # Must have called original loader exactly once (fallback)
            self.assertEqual(
                self._loader_call_count, 1,
                "original loader must be called exactly once on future failure",
            )
            self.assertEqual(
                self.mixin._unet_cache_misses, 1,
                "cache misses must increment on fallback",
            )
            # Future entry removed after consumption
            self.assertNotIn(key, self.mixin._actual_load_futures,
                             "failed future must be removed after consumption")

    # ── Concurrent: both callers get the cached sentinel ──────────────────

    def test_concurrent_graph_demands_share_delayed_future(self):
        """Two concurrent graph demands for the same UNET: an in-flight
        delayed-publishing future exists.  One consumer joins the future
        and returns the sentinel; the other finds the sentinel in cache
        (published after the first consumer completed the future).
        BOTH get the same sentinel, normal loader count 0.

        This tests the ACTUAL concurrent handoff path — the object cache
        starts empty and only the future-consumption populates it.
        """
        with tempfile.TemporaryDirectory() as tmp:
            test_path = Path(tmp, "test-unet-shared-delayed.safetensors")
            test_path.write_text("dummy")
            key, sentinel = self._stub_env(str(test_path))
            # Delayed-publishing future — cache starts empty
            thread = _make_publishing_thread(
                self.mixin._unet_object_cache, key, sentinel
            )
            self.mixin._actual_load_futures[key] = thread
            self.mixin._actual_load_future_meta[key] = {
                "source": "restore_background_unet",
                "status": "completed",
            }
            # Object cache is deliberately EMPTY — the future has not
            # published yet (thread sleeps for 20ms).

            cls = self._patch_loader()
            results: list = []
            errors: list = []

            def _load():
                try:
                    r = cls().load_unet(
                        unet_name="test-unet-shared-delayed.safetensors",
                        weight_dtype="default",
                    )
                    results.append(r)
                except Exception as e:
                    errors.append(e)

            t1 = threading.Thread(target=_load, daemon=True)
            t2 = threading.Thread(target=_load, daemon=True)
            t1.start()
            t2.start()
            t1.join(timeout=10)
            t2.join(timeout=10)

            if errors:
                raise errors[0]

            self.assertEqual(len(results), 2,
                             "both threads must produce a result")
            # BOTH must get the sentinel object
            self.assertIs(
                results[0][0], sentinel,
                "first consumer must get the cached sentinel",
            )
            self.assertIs(
                results[1][0], sentinel,
                "second consumer must ALSO get the cached sentinel",
            )
            # Normal loader must NOT be called (count 0, not bool)
            self.assertEqual(
                self._loader_call_count, 0,
                "original loader must NOT be called under concurrent success",
            )

    # ── Failure under concurrent demand ───────────────────────────────────

    def test_concurrent_failure_falls_back_exactly_once(self):
        """Two concurrent callers, failed non-publishing future:
        first consumer falls to normal load (which populates cache),
        second consumer finds cache.  Exactly one normal load.
        Both results reference the SAME fallback-published object.
        Future entry removed."""
        with tempfile.TemporaryDirectory() as tmp:
            test_path = Path(tmp, "test-unet-fail-concurrent.safetensors")
            test_path.write_text("dummy")
            key = self.mixin._unet_cache_key(str(test_path), "default")
            sentinel = object()  # The fallback object
            self._stub_env(str(test_path))

            # Override the fake load to publish the sentinel to object cache
            # and track the count
            original_fake = self.module.sys.modules["nodes"].NODE_CLASS_MAPPINGS["UNETLoader"].load_unet

            def _fake_load_with_publish(self_node, **kwargs):
                self._loader_call_count += 1
                # Block briefly so the second thread has time to reach the
                # contention point (lock acquisition).  With the serializing
                # fix the second thread will block on the per-key lock; without
                # it the second thread would also pass the recheck and load.
                time.sleep(0.05)
                # Publish a known sentinel to cache so both callers get it
                self.mixin._unet_object_cache[key] = sentinel
                return (sentinel,)

            self.module.sys.modules["nodes"].NODE_CLASS_MAPPINGS["UNETLoader"].load_unet = _fake_load_with_publish  # type: ignore[method-assign]

            # Set up the _actual_load_locks that the new locked fallback needs
            import threading as _th
            self.mixin._actual_load_locks[key] = _th.Lock()

            # Non-publishing failed future
            self._add_non_publishing_future(key, status="failed")

            cls = self._patch_loader()
            results: list = []
            errors: list = []

            def _load():
                try:
                    r = cls().load_unet(
                        unet_name="test-unet-fail-concurrent.safetensors",
                        weight_dtype="default",
                    )
                    results.append(r)
                except Exception as e:
                    errors.append(e)

            t1 = threading.Thread(target=_load, daemon=True)
            t2 = threading.Thread(target=_load, daemon=True)
            t1.start()
            t2.start()
            t1.join(timeout=10)
            t2.join(timeout=10)

            if errors:
                raise errors[0]

            self.assertEqual(len(results), 2,
                             "both threads must produce a result on failure path")
            # Exactly one normal load, not two
            self.assertEqual(
                self._loader_call_count, 1,
                "original loader must be called exactly once under concurrent failure",
            )
            # Both results reference the SAME fallback-published object
            self.assertIs(
                results[0][0], sentinel,
                "first consumer must get the fallback-published sentinel",
            )
            self.assertIs(
                results[1][0], sentinel,
                "second consumer must ALSO get the fallback-published sentinel",
            )
            # Future entry is removed
            self.assertNotIn(key, self.mixin._actual_load_futures,
                             "future entry must be removed after consumption")


if __name__ == "__main__":
    unittest.main()
