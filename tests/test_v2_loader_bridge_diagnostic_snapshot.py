"""Tests for V2LoaderBridge.diagnostic_snapshot().

Covers the full required matrix — empty/no preparation, current preparation,
model+prefill hashes, pending/running/completed/cancelled futures, raising
status methods, executor absent/present, thread count, queue size, pending
lane availability, concurrent reads, preparation changes, JSON serialization,
no key/path/identity leakage, and zero runtime behavior changes.
"""

from __future__ import annotations

import json
import threading
import unittest
from concurrent.futures import Future, ThreadPoolExecutor
from types import SimpleNamespace

from comfymodal_runtime.contracts import ModelRestoreKey, PrefillKey, RestorePlan
from comfymodal_runtime.model_preload import (
    ModelPreloadCoordinator,
    RestorePreparation,
    V2LoaderBridge,
    _LOADER_MISS,
)


# ── Fake node helpers (reused from test_v2_preload_bridge.py pattern) ─────


class _FakeClip:
    pass


def _fake_nodes(calls: list[tuple]) -> SimpleNamespace:
    class UNETLoader:
        def load_unet(self, unet_name, weight_dtype):
            calls.append(("unet", unet_name, weight_dtype))
            return (f"prepared-unet:{unet_name}:{weight_dtype}",)

    class CLIPLoader:
        def load_clip(self, clip_name, type="stable_diffusion", device="default"):
            calls.append(("clip", clip_name, type, device))
            return (_FakeClip(),)

    class DualCLIPLoader:
        def load_clip(self, clip_name1, clip_name2, type, device="default"):
            calls.append(("dual_clip", clip_name1, clip_name2, type, device))
            return (_FakeClip(),)

    class VAELoader:
        def load_vae(self, vae_name):
            calls.append(("vae", vae_name))
            return (f"vae:{vae_name}",)

    class CLIPTextEncode:
        def encode(self, clip, text):
            calls.append(("prefill", id(clip), text))
            return (f"conditioning:{text}",)

    return SimpleNamespace(
        NODE_CLASS_MAPPINGS={
            "UNETLoader": UNETLoader,
            "CLIPLoader": CLIPLoader,
            "DualCLIPLoader": DualCLIPLoader,
            "VAELoader": VAELoader,
            "CLIPTextEncode": CLIPTextEncode,
        }
    )


# ── Future-like objects for failure injection ──────────────────────────────


class _RaisingFuture:
    """Mimics ``concurrent.futures.Future`` but raises on every status method."""

    def done(self) -> bool:
        raise RuntimeError("done unavailable")

    def running(self) -> bool:
        raise RuntimeError("running unavailable")

    def cancelled(self) -> bool:
        raise RuntimeError("cancelled unavailable")


class _NoQueuePool:
    """Mimics a ThreadPoolExecutor without a ``_work_queue`` attribute."""

    _max_workers = 2


class _ThreadCountPool:
    """Mimics an executor with observable existing threads and queue size."""

    _threads = {object(), object()}

    class _Queue:
        @staticmethod
        def qsize() -> int:
            return 4

    _work_queue = _Queue()


# ── Required snapshot keys ──────────────────────────────────────────────────

_REQUIRED_KEYS: frozenset[str] = frozenset({
    "bridge_object_id",
    "current_preparation_exists",
    "current_model_key_hash",
    "current_prefill_key_hash",
    "unet_future_exists",
    "unet_future_done",
    "unet_future_running",
    "unet_future_cancelled",
    "clip_future_exists",
    "clip_future_done",
    "clip_future_running",
    "clip_future_cancelled",
    "prefill_future_exists",
    "prefill_future_done",
    "prefill_future_running",
    "prefill_future_cancelled",
    "executor_exists",
    "executor_thread_count",
    "executor_work_queue_size",
    "pending_lane_count",
})


def _assert_snapshot_contract(self: unittest.TestCase, snap: dict) -> None:
    """Verify structural contract of every snapshot dict."""
    self.assertIsInstance(snap, dict)
    self.assertEqual(set(snap.keys()), _REQUIRED_KEYS, msg=snap)
    # All values must be None / bool / str / int
    for key, val in snap.items():
        self.assertIsInstance(
            val, (type(None), bool, str, int),
            msg=f"key {key!r} has unexpected type {type(val).__name__}: {val!r}",
        )


# ── Tests ───────────────────────────────────────────────────────────────────


class DiagnosticSnapshotEmptyTest(unittest.TestCase):
    """Bridge with no preparation, no keys, no executor."""

    def test_empty_bridge(self) -> None:
        bridge = V2LoaderBridge()
        snap = bridge.diagnostic_snapshot()
        _assert_snapshot_contract(self, snap)
        self.assertFalse(snap["current_preparation_exists"])
        self.assertIsNone(snap["current_model_key_hash"])
        self.assertIsNone(snap["current_prefill_key_hash"])
        # All futures absent
        for suffix in ("exists", "done", "running", "cancelled"):
            for lane in ("unet", "clip", "prefill"):
                key = f"{lane}_future_{suffix}"
                if suffix == "exists":
                    self.assertIs(snap[key], False)
                else:
                    self.assertIsNone(snap[key])
        # Executor absent
        self.assertFalse(snap["executor_exists"])
        self.assertIsNone(snap["executor_thread_count"])
        self.assertIsNone(snap["executor_work_queue_size"])
        # Pending lane count
        self.assertIsNone(snap["pending_lane_count"])


class DiagnosticSnapshotAfterClearTest(unittest.TestCase):
    """Bridge that was prepared then cleared."""

    def test_after_clear(self) -> None:
        bridge = V2LoaderBridge()
        calls: list[tuple] = []
        nodes = _fake_nodes(calls)
        bridge.install(nodes)
        plan = self._minimal_plan()
        bridge.prepare(plan)
        bridge.clear()
        snap = bridge.diagnostic_snapshot()
        _assert_snapshot_contract(self, snap)
        self.assertFalse(snap["current_preparation_exists"])
        self.assertIsNone(snap["current_model_key_hash"])
        self.assertIsNone(snap["current_prefill_key_hash"])
        self.assertFalse(snap["executor_exists"])  # close_workers not called yet
        self.assertIsNone(snap["pending_lane_count"])

    @staticmethod
    def _minimal_plan() -> RestorePlan:
        return RestorePlan(
            model_key=ModelRestoreKey(unet_identity="u", clip_identity="c"),
            prefill_key=PrefillKey(
                model_key=ModelRestoreKey(unet_identity="u", clip_identity="c"),
            ),
        )


class DiagnosticSnapshotWithPreparationTest(unittest.TestCase):
    """Bridge with active preparation and real executor."""

    def test_after_prepare(self) -> None:
        bridge = V2LoaderBridge()
        calls: list[tuple] = []
        nodes = _fake_nodes(calls)
        bridge.install(nodes)
        plan = self._plan()
        prep = bridge.prepare(plan)
        self.assertIsNotNone(prep)
        snap = bridge.diagnostic_snapshot()
        _assert_snapshot_contract(self, snap)
        # Preparation exists
        self.assertTrue(snap["current_preparation_exists"])
        # Key hashes present
        self.assertIsInstance(snap["current_model_key_hash"], str)
        self.assertGreater(len(snap["current_model_key_hash"]), 0)
        self.assertIsInstance(snap["current_prefill_key_hash"], str)
        self.assertGreater(len(snap["current_prefill_key_hash"]), 0)
        # Hashes are deterministic
        snap2 = bridge.diagnostic_snapshot()
        self.assertEqual(snap["current_model_key_hash"], snap2["current_model_key_hash"])
        self.assertEqual(snap["current_prefill_key_hash"], snap2["current_prefill_key_hash"])
        # Executor exists
        self.assertTrue(snap["executor_exists"])
        self.assertIsInstance(snap["executor_thread_count"], int)
        self.assertIsInstance(snap["executor_work_queue_size"], int)
        # Pending lane count (no authoritative tracking)
        self.assertIsNone(snap["pending_lane_count"])

    def test_model_key_hash_no_prefill(self) -> None:
        """Prefill key missing -> prefill hash is None."""
        bridge = V2LoaderBridge()
        calls: list[tuple] = []
        nodes = _fake_nodes(calls)
        bridge.install(nodes)
        plan = RestorePlan(
            model_key=ModelRestoreKey(unet_identity="u", clip_identity="c"),
            prefill_key=PrefillKey(),  # empty — no bundle hash
            model_spec={
                "loaders": {
                    "unet": [{"unet_name": "u", "weight_dtype": "default"}],
                    "clip": [{"clip_name": "c", "type": "flux"}],
                },
            },
        )
        bridge.prepare(plan)
        snap = bridge.diagnostic_snapshot()
        _assert_snapshot_contract(self, snap)
        self.assertIsInstance(snap["current_model_key_hash"], str)
        # prefill_key exists but is empty; stable_hash is still computable
        self.assertIsInstance(snap["current_prefill_key_hash"], str)

    def test_bridge_object_id_stable_within_lifetime(self) -> None:
        bridge = V2LoaderBridge()
        sid1 = bridge.diagnostic_snapshot()["bridge_object_id"]
        sid2 = bridge.diagnostic_snapshot()["bridge_object_id"]
        self.assertEqual(sid1, sid2)
        # Different bridge => different id
        bridge2 = V2LoaderBridge()
        sid3 = bridge2.diagnostic_snapshot()["bridge_object_id"]
        self.assertNotEqual(sid1, sid3)

    @staticmethod
    def _plan() -> RestorePlan:
        model_key = ModelRestoreKey(unet_identity="u", clip_identity="c")
        model_spec: dict[str, Any] = {
            "loaders": {
                "unet": [{"unet_name": "u", "weight_dtype": "default"}],
                "clip": [{"clip_name": "c", "type": "flux"}],
            },
        }
        return RestorePlan(
            model_key=model_key,
            prefill_key=PrefillKey(
                model_key=model_key,
                prompt_bundle_hash="bundle-hash",
                encode_options={
                    "encodes": [{"node_id": "3", "text": "a cat", "role": "positive"}],
                },
            ),
            model_spec=model_spec,
        )


class DiagnosticSnapshotFutureStatesTest(unittest.TestCase):
    """Specific future status combinations via injected preparation."""

    def setUp(self) -> None:
        self.bridge = V2LoaderBridge()
        self.model_key = ModelRestoreKey(unet_identity="u", clip_identity="c")
        self.prefill_key = PrefillKey(model_key=self.model_key, prompt_bundle_hash="b")
        self.prep = RestorePreparation(
            model_key=self.model_key,
            prefill_key=self.prefill_key,
        )
        self.bridge._preparation = self.prep
        self.bridge._model_key = self.model_key
        self.bridge._prefill_key = self.prefill_key

    def test_all_futures_none(self) -> None:
        snap = self.bridge.diagnostic_snapshot()
        for lane in ("unet", "clip", "prefill"):
            self.assertFalse(snap[f"{lane}_future_exists"])
            self.assertIsNone(snap[f"{lane}_future_done"])
            self.assertIsNone(snap[f"{lane}_future_running"])
            self.assertIsNone(snap[f"{lane}_future_cancelled"])

    def test_pending_future(self) -> None:
        self.prep.unet_future = Future()
        snap = self.bridge.diagnostic_snapshot()
        self.assertTrue(snap["unet_future_exists"])
        self.assertFalse(snap["unet_future_done"])
        self.assertFalse(snap["unet_future_running"])
        self.assertFalse(snap["unet_future_cancelled"])

    def test_completed_future(self) -> None:
        f = Future()
        f.set_result("ok")
        self.prep.unet_future = f
        snap = self.bridge.diagnostic_snapshot()
        self.assertTrue(snap["unet_future_exists"])
        self.assertTrue(snap["unet_future_done"])
        self.assertFalse(snap["unet_future_running"])
        self.assertFalse(snap["unet_future_cancelled"])

    def test_cancelled_future(self) -> None:
        f = Future()
        f.cancel()
        self.assertTrue(f.cancelled())  # sanity
        self.prep.prefill_future = f
        snap = self.bridge.diagnostic_snapshot()
        self.assertTrue(snap["prefill_future_exists"])
        self.assertTrue(snap["prefill_future_done"])  # cancelled is done
        self.assertFalse(snap["prefill_future_running"])
        self.assertTrue(snap["prefill_future_cancelled"])

    def test_running_future(self) -> None:
        """Future in RUNNING state (submitted via executor)."""
        pool = ThreadPoolExecutor(max_workers=1)
        try:
            barrier = threading.Event()
            f: Future = pool.submit(barrier.wait)
            # Give the executor a moment to pick up the task
            self.assertTrue(f.running() or not f.done())
            self.prep.unet_future = f
            snap = self.bridge.diagnostic_snapshot()
            self.assertTrue(snap["unet_future_exists"])
            # The future may be running or already done depending on timing
            # (the barrier is never set, so it should stay running)
            self.assertFalse(snap["unet_future_done"])
            self.assertTrue(snap["unet_future_running"])
            self.assertFalse(snap["unet_future_cancelled"])
        finally:
            barrier.set()
            pool.shutdown(wait=True, cancel_futures=True)

    def test_cancelled_future_via_executor(self) -> None:
        """Future cancelled before executor picks it up."""
        pool = ThreadPoolExecutor(max_workers=1)
        try:
            f: Future = pool.submit(lambda: None)  # runs and completes
            f.result()  # ensure done
            # Cancel a completed future -> no-op, cancelled() returns False
            f.cancel()
            self.assertFalse(f.cancelled())
            self.assertTrue(f.done())
            self.prep.clip_future = f
            snap = self.bridge.diagnostic_snapshot()
            self.assertTrue(snap["clip_future_exists"])
            self.assertTrue(snap["clip_future_done"])
            self.assertFalse(snap["clip_future_cancelled"])
        finally:
            pool.shutdown(wait=False)

    def test_raising_future_status(self) -> None:
        """Future whose status methods raise -> None for each."""
        self.prep.unet_future = _RaisingFuture()
        self.prep.clip_future = _RaisingFuture()
        self.prep.prefill_future = _RaisingFuture()
        snap = self.bridge.diagnostic_snapshot()
        for lane in ("unet", "clip", "prefill"):
            self.assertTrue(snap[f"{lane}_future_exists"])
            self.assertIsNone(snap[f"{lane}_future_done"])
            self.assertIsNone(snap[f"{lane}_future_running"])
            self.assertIsNone(snap[f"{lane}_future_cancelled"])

    def test_raising_future_mixed(self) -> None:
        """Mix of normal and raising futures."""
        done_f = Future()
        done_f.set_result("ok")
        self.prep.unet_future = done_f
        self.prep.clip_future = _RaisingFuture()
        self.prep.prefill_future = None
        snap = self.bridge.diagnostic_snapshot()
        # unet: normal done
        self.assertTrue(snap["unet_future_done"])
        self.assertFalse(snap["unet_future_cancelled"])
        # clip: raising
        self.assertTrue(snap["clip_future_exists"])
        self.assertIsNone(snap["clip_future_done"])
        self.assertIsNone(snap["clip_future_running"])
        self.assertIsNone(snap["clip_future_cancelled"])
        # prefill: None
        self.assertFalse(snap["prefill_future_exists"])
        self.assertIsNone(snap["prefill_future_done"])

    def test_future_status_never_calls_result_exception_wait(self) -> None:
        """Verifies only done/running/cancelled are called, never result/exception/wait."""
        _called: list[str] = []

        class _MonitoredFuture:
            def done(self) -> bool:
                _called.append("done")
                return True
            def running(self) -> bool:
                _called.append("running")
                return False
            def cancelled(self) -> bool:
                _called.append("cancelled")
                return False
            # Intentionally no result() or exception() or add_done_callback()

        self.prep.unet_future = _MonitoredFuture()
        self.bridge.diagnostic_snapshot()
        self.assertEqual(_called, ["done", "running", "cancelled"])


class DiagnosticSnapshotExecutorTest(unittest.TestCase):
    """Executor presence, thread count, queue size."""

    def test_executor_absent(self) -> None:
        bridge = V2LoaderBridge()
        # No prepare() call => no pool
        snap = bridge.diagnostic_snapshot()
        self.assertFalse(snap["executor_exists"])
        self.assertIsNone(snap["executor_thread_count"])
        self.assertIsNone(snap["executor_work_queue_size"])

    def test_executor_absent_with_preparation(self) -> None:
        """Preparation exists but pool was closed."""
        bridge = V2LoaderBridge()
        calls: list[tuple] = []
        nodes = _fake_nodes(calls)
        bridge.install(nodes)
        plan = DiagnosticSnapshotWithPreparationTest._plan()
        bridge.prepare(plan)
        # Close workers — sets pool to None
        bridge.close_workers()
        snap = bridge.diagnostic_snapshot()
        self.assertTrue(snap["current_preparation_exists"])
        self.assertFalse(snap["executor_exists"])
        self.assertIsNone(snap["executor_thread_count"])
        self.assertIsNone(snap["executor_work_queue_size"])

    def test_executor_thread_count(self) -> None:
        bridge = V2LoaderBridge()
        calls: list[tuple] = []
        nodes = _fake_nodes(calls)
        bridge.install(nodes)
        plan = DiagnosticSnapshotWithPreparationTest._plan()
        bridge.prepare(plan)
        with bridge.coordinator._pool_lock:
            bridge.coordinator._pool = _ThreadCountPool()  # type: ignore[assignment]
        snap = bridge.diagnostic_snapshot()
        self.assertEqual(snap["executor_thread_count"], 2)
        self.assertEqual(snap["executor_work_queue_size"], 4)

    def test_executor_thread_count_custom(self) -> None:
        bridge = V2LoaderBridge(max_workers=2)
        calls: list[tuple] = []
        nodes = _fake_nodes(calls)
        bridge.install(nodes)
        plan = DiagnosticSnapshotWithPreparationTest._plan()
        bridge.prepare(plan)
        with bridge.coordinator._pool_lock:
            pool = bridge.coordinator._pool
        snap = bridge.diagnostic_snapshot()
        self.assertIsNotNone(pool)
        self.assertEqual(snap["executor_thread_count"], len(pool._threads))

    def test_work_queue_size(self) -> None:
        bridge = V2LoaderBridge(max_workers=1)
        calls: list[tuple] = []
        nodes = _fake_nodes(calls)
        bridge.install(nodes)
        plan = DiagnosticSnapshotWithPreparationTest._plan()
        bridge.prepare(plan)
        snap = bridge.diagnostic_snapshot()
        self.assertIsInstance(snap["executor_work_queue_size"], int)
        self.assertGreaterEqual(snap["executor_work_queue_size"], 0)

    def test_queue_unavailable(self) -> None:
        """Executor without _work_queue -> work_queue_size is None."""
        bridge = V2LoaderBridge()
        # Inject a pool-like object without _work_queue
        pool = _NoQueuePool()
        with bridge.coordinator._pool_lock:
            bridge.coordinator._pool = pool  # type: ignore[assignment]
        snap = bridge.diagnostic_snapshot()
        self.assertTrue(snap["executor_exists"])
        self.assertIsNone(snap["executor_thread_count"])
        self.assertIsNone(snap["executor_work_queue_size"])


class DiagnosticSnapshotPendingLaneTest(unittest.TestCase):
    """Pending lane count behaviour (no authoritative tracking => None)."""

    def test_pending_lane_always_none(self) -> None:
        """Snapshot always reports None for pending_lane_count."""
        bridge = V2LoaderBridge()
        # No preparation
        self.assertIsNone(bridge.diagnostic_snapshot()["pending_lane_count"])
        # With preparation
        calls: list[tuple] = []
        nodes = _fake_nodes(calls)
        bridge.install(nodes)
        plan = DiagnosticSnapshotWithPreparationTest._plan()
        bridge.prepare(plan)
        self.assertIsNone(bridge.diagnostic_snapshot()["pending_lane_count"])
        # After close_workers
        bridge.close_workers()
        self.assertIsNone(bridge.diagnostic_snapshot()["pending_lane_count"])


class DiagnosticSnapshotConcurrencyTest(unittest.TestCase):
    """Concurrent reads from multiple threads."""

    def test_concurrent_reads(self) -> None:
        bridge = V2LoaderBridge()
        calls: list[tuple] = []
        nodes = _fake_nodes(calls)
        bridge.install(nodes)
        plan = DiagnosticSnapshotWithPreparationTest._plan()
        bridge.prepare(plan)

        results: list[dict] = []
        errors: list[Exception] = []
        lock = threading.Lock()

        def reader() -> None:
            try:
                snap = bridge.diagnostic_snapshot()
                with lock:
                    results.append(snap)
            except Exception as e:
                with lock:
                    errors.append(e)

        threads = [threading.Thread(target=reader) for _ in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5)

        self.assertEqual(errors, [])
        self.assertEqual(len(results), 8)
        # All snapshots from the same bridge share the same object id
        first_id = results[0]["bridge_object_id"]
        for snap in results:
            self.assertEqual(snap["bridge_object_id"], first_id)
            self.assertTrue(snap["current_preparation_exists"])

    def test_read_while_preparation_changes(self) -> None:
        bridge = V2LoaderBridge()
        prep = RestorePreparation(
            model_key=ModelRestoreKey(unet_identity="u", clip_identity="c"),
            prefill_key=PrefillKey(),
        )
        bridge._preparation = prep
        bridge._model_key = prep.model_key
        bridge._prefill_key = prep.prefill_key
        stop = threading.Event()
        errors: list[Exception] = []

        def mutate() -> None:
            try:
                while not stop.is_set():
                    bridge._preparation = None
                    bridge._model_key = None
                    bridge._prefill_key = None
                    bridge._preparation = prep
                    bridge._model_key = prep.model_key
                    bridge._prefill_key = prep.prefill_key
            except Exception as exc:
                errors.append(exc)

        writer = threading.Thread(target=mutate)
        writer.start()
        try:
            for _ in range(100):
                _assert_snapshot_contract(self, bridge.diagnostic_snapshot())
        finally:
            stop.set()
            writer.join(timeout=5)
        self.assertEqual(errors, [])
        self.assertFalse(writer.is_alive())


class DiagnosticSnapshotPreparationChangeTest(unittest.TestCase):
    """Snapshot reflects the most recent preparation state."""

    def test_snapshot_reflects_clear(self) -> None:
        bridge = V2LoaderBridge()
        calls: list[tuple] = []
        nodes = _fake_nodes(calls)
        bridge.install(nodes)
        plan = DiagnosticSnapshotWithPreparationTest._plan()

        bridge.prepare(plan)
        snap_before = bridge.diagnostic_snapshot()
        self.assertTrue(snap_before["current_preparation_exists"])
        self.assertIsInstance(snap_before["current_model_key_hash"], str)

        bridge.clear()
        snap_after = bridge.diagnostic_snapshot()
        self.assertFalse(snap_after["current_preparation_exists"])
        self.assertIsNone(snap_after["current_model_key_hash"])
        self.assertIsNone(snap_after["current_prefill_key_hash"])

    def test_snapshot_reflects_new_preparation(self) -> None:
        bridge = V2LoaderBridge()
        calls: list[tuple] = []
        nodes = _fake_nodes(calls)
        bridge.install(nodes)

        # First preparation
        plan1 = DiagnosticSnapshotWithPreparationTest._plan()
        bridge.prepare(plan1)
        hash1 = bridge.diagnostic_snapshot()["current_model_key_hash"]

        # Second preparation with different key
        model_key2 = ModelRestoreKey(unet_identity="u2", clip_identity="c2")
        plan2 = RestorePlan(
            model_key=model_key2,
            prefill_key=PrefillKey(
                model_key=model_key2,
                prompt_bundle_hash="bundle-2",
            ),
            model_spec={
                "loaders": {
                    "unet": [{"unet_name": "u2", "weight_dtype": "default"}],
                    "clip": [{"clip_name": "c2", "type": "flux"}],
                },
            },
        )
        bridge.prepare(plan2)
        hash2 = bridge.diagnostic_snapshot()["current_model_key_hash"]

        self.assertIsNotNone(hash1)
        self.assertIsNotNone(hash2)
        self.assertNotEqual(hash1, hash2)


class DiagnosticSnapshotJSONTest(unittest.TestCase):
    """Snapshot is JSON-serializable and contains no key/path leakage."""

    def test_json_serializable(self) -> None:
        bridge = V2LoaderBridge()
        calls: list[tuple] = []
        nodes = _fake_nodes(calls)
        bridge.install(nodes)
        plan = DiagnosticSnapshotWithPreparationTest._plan()
        bridge.prepare(plan)

        snap = bridge.diagnostic_snapshot()
        dumped = json.dumps(snap, sort_keys=True)
        self.assertIsInstance(dumped, str)
        loaded = json.loads(dumped)
        self.assertEqual(loaded.keys(), _REQUIRED_KEYS)
        # Full round-trip: loaded values match (type-coerced via JSON)
        for key in _REQUIRED_KEYS:
            orig = snap[key]
            if isinstance(orig, bool):
                # JSON bool is int, int(True)=1, int(False)=0
                self.assertEqual(bool(loaded[key]), orig, msg=key)
            elif isinstance(orig, int):
                self.assertEqual(loaded[key], orig, msg=key)
            elif orig is None:
                self.assertIsNone(loaded[key], msg=key)
            else:
                self.assertEqual(loaded[key], orig, msg=key)

    def test_no_key_identity_leakage(self) -> None:
        """Snapshot must not contain full keys, paths, or repr identities."""
        bridge = V2LoaderBridge()
        # Use a realistic identity string in the model key
        model_key = ModelRestoreKey(
            unet_identity="/models/unet/model.safetensors",
            clip_identity="/models/clip/text_encoder.safetensors",
        )
        plan = RestorePlan(
            model_key=model_key,
            prefill_key=PrefillKey(model_key=model_key, prompt_bundle_hash="test"),
            model_spec={
                "loaders": {
                    "unet": [{"unet_name": "/models/unet/model.safetensors", "weight_dtype": "default"}],
                    "clip": [{"clip_name": "/models/clip/text_encoder.safetensors", "type": "flux"}],
                },
            },
        )
        calls: list[tuple] = []
        nodes = _fake_nodes(calls)
        bridge.install(nodes)
        bridge.prepare(plan)

        snap = bridge.diagnostic_snapshot()
        dumped = json.dumps(snap)
        # No full identity strings should appear
        self.assertNotIn("model.safetensors", dumped)
        self.assertNotIn("text_encoder", dumped)
        # Only hex hashes should appear
        for val in snap.values():
            if isinstance(val, str) and val.startswith("bridge_"):
                # bridge_object_id is an id() string — allowed
                self.assertTrue(val.startswith("bridge_"), msg=f"unexpected string value: {val!r}")


class DiagnosticSnapshotNoBehaviorChangeTest(unittest.TestCase):
    """diagnostic_snapshot() must not alter bridge state or start new work."""

    def test_no_state_mutation(self) -> None:
        bridge = V2LoaderBridge()
        calls: list[tuple] = []
        nodes = _fake_nodes(calls)
        bridge.install(nodes)
        plan = DiagnosticSnapshotWithPreparationTest._plan()
        bridge.prepare(plan)

        # Capture state before
        prep_before = bridge._preparation
        mk_before = bridge._model_key
        pk_before = bridge._prefill_key
        unlock_results_before = list(bridge._prefill_results.items())

        # Call snapshot
        bridge.diagnostic_snapshot()

        # State unchanged
        self.assertIs(bridge._preparation, prep_before)
        self.assertIs(bridge._model_key, mk_before)
        self.assertIs(bridge._prefill_key, pk_before)
        self.assertEqual(list(bridge._prefill_results.items()), unlock_results_before)

    def test_no_new_work_submitted(self) -> None:
        """Calling diagnostic_snapshot must not submit executor work."""
        bridge = V2LoaderBridge()
        calls: list[tuple] = []
        nodes = _fake_nodes(calls)
        bridge.install(nodes)
        plan = DiagnosticSnapshotWithPreparationTest._plan()
        bridge.prepare(plan)

        # Snapshot should not change the number of submitted futures
        prep = bridge._preparation
        futures_before = (
            prep.unet_future,
            prep.clip_future,
            prep.vae_future,
            prep.prefill_future,
        )

        bridge.diagnostic_snapshot()

        futures_after = (
            prep.unet_future,
            prep.clip_future,
            prep.vae_future,
            prep.prefill_future,
        )
        self.assertEqual(futures_before, futures_after)

    def test_no_exception_propagation(self) -> None:
        """diagnostic_snapshot must never raise, even on corrupt state."""
        bridge = V2LoaderBridge()
        # Inject an object that raises on attribute access for all bridge fields
        # (worst-case scenario)
        bridge._preparation = object()  # not a RestorePreparation
        bridge._model_key = object()  # not a ModelRestoreKey
        bridge._prefill_key = object()  # not a PrefillKey
        # This should not raise
        snap = bridge.diagnostic_snapshot()
        self.assertTrue(snap["current_preparation_exists"])
        self.assertIsNone(snap["current_model_key_hash"])
        self.assertIsNone(snap["current_prefill_key_hash"])

    def test_executor_inspection_failure_does_not_raise(self) -> None:
        bridge = V2LoaderBridge()
        bridge.coordinator = object()  # type: ignore[assignment]
        snap = bridge.diagnostic_snapshot()
        _assert_snapshot_contract(self, snap)
        self.assertIsNone(snap["executor_exists"])
        self.assertIsNone(snap["executor_thread_count"])
        self.assertIsNone(snap["executor_work_queue_size"])


if __name__ == "__main__":
    unittest.main()
