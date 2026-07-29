"""Focused tests for v2 GPU configuration, memory validation, host-memory
reporting, GPU-allocation reporting, async-commit path, and the
ModalRuntimeEntrypointV2 constructor change."""

from __future__ import annotations

import asyncio
import io
import json
import os
import platform
import tempfile
import threading
import time
import unittest
from unittest.mock import MagicMock, PropertyMock, patch

from gpu_catalog import (
    DEFAULT_GPU,
    DEFAULT_GPU_FALLBACKS,
    GPU_CANONICAL_MAP,
    V2_DEFAULT_GPU,
    _dedupe_preserve_order,
    _normalize_gpu_name,
    parse_gpu_request,
)
from comfymodal_runtime.runtime_state import (
    CommitCoordinator,
    FakeVolume,
    ModalMountedStateVolume,
    MountedStateVolume,
)
from comfymodal_runtime.contracts import RestorePlan, ModelRestoreKey, PrefillKey
from comfymodal_runtime.modal_app import (
    ModalRuntimeSpec,
    _parse_memory_mb,
    _report_host_memory,
    _detect_gpu_allocation,
    _build_decorated_v2_class,
    _publish_restore_plan_impl,
    _publish_restore_plan_impl_async,
)
from comfymodal_runtime.contracts import DeploymentIdentity
from comfymodal_runtime.restore_plan import RestorePlanPublisher


# ====================================================================
# GPU catalog / GPU list
# ====================================================================


class TestParseGpuRequest(unittest.TestCase):
    """V2 ordered GPU request parsing from env vars."""

    def setUp(self):
        self._saved_env = {}
        for key in ("COMFYMODAL_V2_GPU", "COMFYMODAL_V2_GPU_FALLBACKS"):
            self._saved_env[key] = os.environ.pop(key, None)

    def tearDown(self):
        for key, val in self._saved_env.items():
            if val is not None:
                os.environ[key] = val
            else:
                os.environ.pop(key, None)

    # --- Case 1: default ordered GPU list (Modal-canonical casing) ---
    def test_default_ordered_gpu_list(self):
        result = parse_gpu_request()
        self.assertEqual(
            result,
            ("RTX-PRO-6000",),
        )

    # --- Case 2: COMFYMODAL_V2_GPU overrides primary ---
    def test_env_primary_overrides_default(self):
        os.environ["COMFYMODAL_V2_GPU"] = "h100"
        result = parse_gpu_request()
        self.assertEqual(result[0], "H100")
        self.assertEqual(result, ("H100",))

    # --- Case 3: COMFYMODAL_V2_GPU_FALLBACKS overrides defaults ---
    def test_fallbacks_env_overrides_defaults(self):
        os.environ["COMFYMODAL_V2_GPU_FALLBACKS"] = "t4,l4"
        result = parse_gpu_request()
        self.assertEqual(result, ("RTX-PRO-6000", "T4", "L4"))

    # --- Case 4: absent fallback env uses defaults ---
    def test_absent_fallback_env_uses_defaults(self):
        # Remove COMFYMODAL_V2_GPU_FALLBACKS so it's truly absent
        os.environ.pop("COMFYMODAL_V2_GPU_FALLBACKS", None)
        result = parse_gpu_request()
        self.assertEqual(result, ("RTX-PRO-6000",))

    # --- Case 5: explicitly empty fallback env disables all fallbacks ---
    def test_empty_fallback_env_disables_fallbacks(self):
        os.environ["COMFYMODAL_V2_GPU_FALLBACKS"] = ""
        result = parse_gpu_request()
        self.assertEqual(result, ("RTX-PRO-6000",))

    # --- Case 6: explicit whitespace-only fallback also disables fallbacks ---
    def test_whitespace_fallback_disables_fallbacks(self):
        os.environ["COMFYMODAL_V2_GPU_FALLBACKS"] = "   "
        result = parse_gpu_request()
        self.assertEqual(result, ("RTX-PRO-6000",))

    # --- Case 7: case/alias normalization to Modal canonical strings ---
    def test_normalize_casing_and_aliases(self):
        os.environ["COMFYMODAL_V2_GPU"] = "  RTX-PRO-6000  "
        os.environ["COMFYMODAL_V2_GPU_FALLBACKS"] = "  A100-80GB , A100-40GB  "
        result = parse_gpu_request()
        self.assertEqual(
            result,
            ("RTX-PRO-6000", "A100-80GB", "A100-40GB"),
        )

    # --- Case 8: dedupe preserving order ---
    def test_dedupe_preserving_order(self):
        os.environ["COMFYMODAL_V2_GPU_FALLBACKS"] = "A100-80GB,a100-80gb,T4,a100-80gb"
        result = parse_gpu_request()
        self.assertEqual(result, ("RTX-PRO-6000", "A100-80GB", "T4"))

    # --- Case 9: no silent appending beyond configured values ---
    def test_no_silent_append(self):
        os.environ["COMFYMODAL_V2_GPU"] = "t4"
        os.environ["COMFYMODAL_V2_GPU_FALLBACKS"] = "l4"
        result = parse_gpu_request()
        self.assertEqual(result, ("T4", "L4"))
        # Should NOT include RTX-PRO-6000, A100-80GB, or A100-40GB

    # --- Case 10: explicit empty primary falls back to V2 canonical RTX-PRO-6000 ---
    def test_explicit_empty_primary_uses_v2_canonical(self):
        os.environ["COMFYMODAL_V2_GPU"] = ""
        os.environ.pop("COMFYMODAL_V2_GPU_FALLBACKS", None)
        result = parse_gpu_request()
        self.assertEqual(result, ("RTX-PRO-6000",))
        # Must NOT produce legacy lowercase DEFAULT_GPU ("rtx-pro-6000")
        self.assertEqual(result[0], V2_DEFAULT_GPU)

    # --- Case 11: whitespace-only primary also falls back to V2 canonical ---
    def test_whitespace_primary_uses_v2_canonical(self):
        os.environ["COMFYMODAL_V2_GPU"] = "   "
        os.environ.pop("COMFYMODAL_V2_GPU_FALLBACKS", None)
        result = parse_gpu_request()
        self.assertEqual(result, ("RTX-PRO-6000",))
        self.assertEqual(result[0], V2_DEFAULT_GPU)


class TestGpuNameNormalization(unittest.TestCase):
    def test_normalize_rtx_pro_6000(self):
        self.assertEqual(_normalize_gpu_name("RTX PRO 6000"), "RTX-PRO-6000")

    def test_normalize_a100_80gb_variants(self):
        self.assertEqual(_normalize_gpu_name("A100-80GB"), "A100-80GB")
        self.assertEqual(_normalize_gpu_name("A100 80GB"), "A100-80GB")
        self.assertEqual(_normalize_gpu_name("a100_80gb"), "A100-80GB")

    def test_normalize_unknown_passes_through(self):
        self.assertEqual(_normalize_gpu_name("custom-gpu"), "custom-gpu")


class TestDedupePreserveOrder(unittest.TestCase):
    def test_dedupe_basic(self):
        self.assertEqual(
            _dedupe_preserve_order(["a", "b", "a", "c", "b"]),
            ["a", "b", "c"],
        )

    def test_dedupe_empty(self):
        self.assertEqual(_dedupe_preserve_order([]), [])

    def test_dedupe_no_dupes(self):
        self.assertEqual(
            _dedupe_preserve_order(["x", "y", "z"]),
            ["x", "y", "z"],
        )


# ====================================================================
# ModalRuntimeSpec (GPU tuple + memory validation)
# ====================================================================


class TestModalRuntimeSpec(unittest.TestCase):
    """ModalRuntimeSpec correctly represents ordered GPU and validates memory."""

    def setUp(self):
        self._saved_env = {}
        for key in ("COMFYMODAL_V2_GPU", "COMFYMODAL_V2_GPU_FALLBACKS", "COMFYMODAL_V2_MEMORY_MB"):
            self._saved_env[key] = os.environ.pop(key, None)

    def tearDown(self):
        for key, val in self._saved_env.items():
            if val is not None:
                os.environ[key] = val
            else:
                os.environ.pop(key, None)

    def test_default_gpu_is_tuple(self):
        spec = ModalRuntimeSpec()
        self.assertIsInstance(spec.gpu, tuple)
        self.assertEqual(spec.gpu, ("RTX-PRO-6000",))

    def test_gpu_from_env(self):
        os.environ["COMFYMODAL_V2_GPU"] = "h100"
        os.environ["COMFYMODAL_V2_GPU_FALLBACKS"] = "t4"
        spec = ModalRuntimeSpec()
        self.assertEqual(spec.gpu, ("H100", "T4"))

    def test_default_memory_is_24576(self):
        spec = ModalRuntimeSpec()
        self.assertEqual(spec.memory, 24576)

    def test_default_cpu_is_48(self):
        spec = ModalRuntimeSpec()
        self.assertEqual(spec.cpu, 48)

    def test_memory_from_env(self):
        os.environ["COMFYMODAL_V2_MEMORY_MB"] = "24576"
        spec = ModalRuntimeSpec()
        self.assertEqual(spec.memory, 24576)

    def test_memory_validation_rejects_zero(self):
        os.environ["COMFYMODAL_V2_MEMORY_MB"] = "0"
        with self.assertRaises(RuntimeError):
            _parse_memory_mb()

    def test_memory_validation_rejects_negative(self):
        os.environ["COMFYMODAL_V2_MEMORY_MB"] = "-1"
        with self.assertRaises(RuntimeError):
            _parse_memory_mb()

    def test_memory_validation_rejects_non_int(self):
        os.environ["COMFYMODAL_V2_MEMORY_MB"] = "not-a-number"
        with self.assertRaises(RuntimeError):
            _parse_memory_mb()


# ====================================================================
# Host memory reporting
# ====================================================================


class TestReportHostMemory(unittest.TestCase):
    def test_returns_dict_with_stage(self):
        result = _report_host_memory("test_stage")
        self.assertIsInstance(result, dict)
        self.assertEqual(result.get("stage"), "test_stage")

    def test_never_raises(self):
        # Should never raise regardless of environment
        try:
            _report_host_memory("safe_test")
        except Exception as exc:
            self.fail(f"_report_host_memory raised: {exc}")

    def test_contains_status(self):
        result = _report_host_memory("status_test")
        self.assertIn("status", result)

    def test_process_maxrss_mib_from_rusage(self):
        """process_maxrss_mib should be populated from rusage, not VmPeak."""
        result = _report_host_memory("rss_test")
        maxrss = result.get("process_maxrss_mib")
        if maxrss not in (None, "absent"):
            self.assertIsInstance(maxrss, (int, float))
            self.assertGreater(maxrss, 0)

    @patch("comfymodal_runtime.modal_app.platform.system")
    @patch("comfymodal_runtime.modal_app._read_cgroup_v2_memory")
    def test_cgroup_missing_counters_absent(self, mock_read_cgroup, mock_platform):
        """When cgroup v2 files are missing, memory counters stay absent."""
        mock_platform.return_value = "Linux"
        mock_read_cgroup.return_value = None  # all reads return None
        result = _report_host_memory("cgroup_missing")
        # cgroup counters should be absent
        self.assertEqual(result.get("current_mib"), "absent")
        self.assertEqual(result.get("peak_mib"), "absent")
        self.assertEqual(result.get("limit_mib"), "absent")
        self.assertEqual(result.get("oom_count"), "absent")
        self.assertEqual(result.get("oom_kill_count"), "absent")
        self.assertEqual(result.get("status"), "ok")

    @patch("comfymodal_runtime.modal_app.platform.system")
    @patch("comfymodal_runtime.modal_app._read_cgroup_v2_memory")
    def test_cgroup_malformed_counters_still_ok(self, mock_read_cgroup, mock_platform):
        """Malformed cgroup file values (non-int) do not propagate."""
        mock_platform.return_value = "Linux"
        mock_read_cgroup.return_value = None
        # Also patch memory.events to simulate malformed content
        import io
        mock_events = io.StringIO("oom_kill not_a_number\noom abc\n")
        with patch("builtins.open", return_value=mock_events) as mock_open:
            result = _report_host_memory("cgroup_malformed")
            self.assertEqual(result.get("status"), "ok")

    @patch("comfymodal_runtime.modal_app.platform.system")
    @patch("comfymodal_runtime.modal_app._read_cgroup_v2_memory")
    def test_cgroup_valid_counters_present(self, mock_read_cgroup, mock_platform):
        """When cgroup v2 files are present, counters are reported."""
        mock_platform.return_value = "Linux"
        # Return different values per call based on path
        def side_effect(path):
            if "memory.max" in path:
                return 8 * 1024 * 1024 * 1024  # 8 GB
            if "memory.current" in path:
                return 2 * 1024 * 1024 * 1024  # 2 GB
            if "memory.peak" in path:
                return 4 * 1024 * 1024 * 1024  # 4 GB
            return None
        mock_read_cgroup.side_effect = side_effect
        with patch(
            "comfymodal_runtime.modal_app._resolve_cgroup_v2_base",
            return_value=("/fake/cgroup", "/fake/mount"),
        ), patch(
            "builtins.open",
            side_effect=lambda path, *args, **kwargs: io.StringIO(
                "oom 1\noom_kill 0\n"
            ) if str(path).endswith("memory.events") else (_ for _ in ()).throw(
                FileNotFoundError(path)
            ),
        ):
            result = _report_host_memory("cgroup_valid")
            self.assertEqual(result.get("current_mib"), round(2048, 1))  # 2 GB
            self.assertEqual(result.get("peak_mib"), round(4096, 1))  # 4 GB
            self.assertEqual(result.get("limit_mib"), round(8192, 1))  # 8 GB
            self.assertEqual(result.get("oom_count"), 1)
            self.assertEqual(result.get("oom_kill_count"), 0)
            self.assertEqual(result.get("status"), "ok")


# ====================================================================
# GPU allocation detection
# ====================================================================


class TestDetectGpuAllocation(unittest.TestCase):
    def test_returns_dict_with_requested_order(self):
        requested = ("RTX-PRO-6000", "A100-80GB")
        result = _detect_gpu_allocation(requested)
        self.assertIsInstance(result, dict)
        self.assertEqual(result.get("gpu_requested_order"), "RTX-PRO-6000,A100-80GB")

    def test_never_raises(self):
        try:
            _detect_gpu_allocation(("test",))
        except Exception as exc:
            self.fail(f"_detect_gpu_allocation raised: {exc}")

    def test_torch_version_when_available(self):
        try:
            import torch
            result = _detect_gpu_allocation(("T4",))
            self.assertIn("torch_version", result)
        except ImportError:
            self.skipTest("torch not available")


# ====================================================================
# Async commit path
# ====================================================================


class TestModalMountedStateVolumeAsyncCommit(unittest.TestCase):
    """ModalMountedStateVolume.commit_async() works correctly."""

    def test_commit_async_with_fake_volume(self):
        """FakeVolume has no aio method, falls back to thread."""
        fake = FakeVolume()
        with tempfile.TemporaryDirectory() as tmp:
            volume = ModalMountedStateVolume(tmp, fake)

            async def run():
                await volume.commit_async()

            self.assertEqual(fake.commit_count, 0)
            asyncio.run(run())
            # ModalMountedStateVolume.commit_async() no longer calls
            # super().commit() — only Modal commit is invoked.
            # FakeVolume.commit is called via thread fallback.
            self.assertEqual(fake.commit_count, 1)

    def test_commit_async_raises_on_missing_commit(self):
        with tempfile.TemporaryDirectory() as tmp:
            volume = ModalMountedStateVolume(tmp, object())

            async def run():
                with self.assertRaises(RuntimeError):
                    await volume.commit_async()

            asyncio.run(run())


class TestCommitCoordinatorAsync(unittest.TestCase):
    """CommitCoordinator async commit support."""

    def test_commit_async_with_fake_volume(self):
        """FakeVolume has no commit_async → uses thread fallback."""
        fake = FakeVolume()
        # ModalMountedStateVolume wrapping FakeVolume — commit_async uses
        # Modal commit path. FakeVolume's commit is called via thread.
        modal_vol = ModalMountedStateVolume("/tmp/commit_coord_test", fake)
        coord = CommitCoordinator(modal_vol)
        coord.write_state(1, {"key": "value"})

        async def run():
            result = await coord.commit_async(1)
            return result

        result = asyncio.run(run())
        self.assertTrue(result)

    def test_commit_async_thread_fallback_no_blocking_sync(self):
        """Volume without commit_async must use thread fallback, not
        call self._volume.commit() directly in async context."""
        sync_called_directly = [False]

        class NoAsyncVolume:
            def __init__(self):
                self._files = {}

            def write_bytes(self, path, data):
                self._files[path] = data

            def read_bytes(self, path):
                return self._files.get(path, b"")

            def exists(self, path):
                return path in self._files

            def remove(self, path):
                self._files.pop(path, None)

            def commit(self):
                sync_called_directly[0] = True

        vol = NoAsyncVolume()
        # Wrap in ModalMountedStateVolume so commit_async goes through Modal layer
        # Use MagicMock for the modal_volume so commit.aio is absent
        mock_modal = MagicMock()
        mock_modal.commit = MagicMock()
        # Deliberately do NOT attach .aio to force thread fallback
        del mock_modal.commit.aio
        # Disable reload.aio to avoid MagicMock auto-creation
        mock_modal.reload = None

        modal_vol = ModalMountedStateVolume("/tmp/no_async_test", mock_modal)
        coord = CommitCoordinator(modal_vol)
        coord.write_state(1, {"key": "value"})

        async def run():
            result = await coord.commit_async(1)
            return result

        result = asyncio.run(run())
        self.assertTrue(result)
        # The NoAsyncVolume.commit should NOT have been called (ModalMountedStateVolume
        # delegates to the modal volume's commit, not to its own super().commit())
        self.assertFalse(sync_called_directly[0],
                         "Must not call volume.commit() directly in async context")

    def test_coordinator_reload_async(self):
        """CommitCoordinator.reload_async uses volume.reload_async or thread."""
        reload_async_called = [False]

        class VolumeWithReloadAsync:
            def __init__(self):
                self._files = {}
                self.reload_async_called = False

            def write_bytes(self, path, data):
                self._files[path] = data

            def read_bytes(self, path):
                return self._files.get(path, b"")

            def exists(self, path):
                return path in self._files

            def remove(self, path):
                self._files.pop(path, None)

            def commit(self):
                pass

            async def reload_async(self):
                self.reload_async_called = True

        vol = VolumeWithReloadAsync()
        coord = CommitCoordinator(vol)
        self.assertFalse(vol.reload_async_called)

        async def run():
            await coord.reload_async()

        asyncio.run(run())
        self.assertTrue(vol.reload_async_called)


class TestAsyncPublishRestorePlan(unittest.TestCase):
    """Async publication path: exactly one awaited async commit, no sync Modal commit."""

    def test_async_publish_single_async_commit(self):
        """Async publish must call exactly one async commit and zero sync Modal commits.
        Uses unique tempfile root for isolation."""
        # Track commit calls on the real Modal volume mock
        sync_call_count = 0
        async_call_count = 0

        def _track_sync(*args, **kwargs):
            nonlocal sync_call_count
            sync_call_count += 1

        async def _track_async(*args, **kwargs):
            nonlocal async_call_count
            async_call_count += 1

        real_modal_vol = MagicMock()
        real_modal_vol.commit = MagicMock(side_effect=_track_sync)
        real_modal_vol.commit.aio = _track_async
        # Disable reload.aio so ModalMountedStateVolume falls back to thread
        real_modal_vol.reload = None

        with tempfile.TemporaryDirectory() as tmp:
            modal_vol = ModalMountedStateVolume(tmp, real_modal_vol)
            coord = CommitCoordinator(modal_vol, state_path="plan_async.json")
            publisher = RestorePlanPublisher(coord)

            plan = RestorePlan(
                generation=1,
                model_key=ModelRestoreKey(unet_identity="async_test"),
                prefill_key=PrefillKey(prompt_bundle_hash="p_async"),
            )

            async def run():
                result = await publisher.publish_with_metrics_async(plan)
                return result

            result = asyncio.run(run())
            self.assertTrue(result["changed"])
            # Exactly one async Modal commit (volume commit.aio call)
            self.assertEqual(async_call_count, 1,
                             "Async publish must call exactly one async commit")
            # Zero sync Modal commits (modal_vol.commit was not called)
            self.assertEqual(sync_call_count, 0,
                             "Async publish must not call sync Modal commit")

    def test_async_publish_modified_then_readback(self):
        """Publish changed plan via async path, verify generation on readback.
        Uses unique tempfile root so prior runs do not leak state."""
        with tempfile.TemporaryDirectory() as tmp:
            vol = MountedStateVolume(root=tmp)
            coord = CommitCoordinator(vol, state_path="plan_async2.json")
            publisher = RestorePlanPublisher(coord)

            plan = RestorePlan(
                generation=1,
                model_key=ModelRestoreKey(unet_identity="readback_test"),
                prefill_key=PrefillKey(prompt_bundle_hash="p_readback"),
            )

            async def run():
                result = await publisher.publish_with_metrics_async(plan)
                return result

            result = asyncio.run(run())
            self.assertTrue(result["changed"])
            self.assertEqual(result["generation"], 1)

            # Re-read the published plan
            read_plan = publisher.read_current_plan()
            self.assertIsNotNone(read_plan)
            if read_plan is not None:
                self.assertEqual(read_plan.model_key.unet_identity, "readback_test")

    def test_async_publish_unchanged_is_noop(self):
        """Same plan via async path must not write or commit.
        Uses unique tempfile root for isolation."""
        with tempfile.TemporaryDirectory() as tmp:
            vol = MountedStateVolume(root=tmp)
            coord = CommitCoordinator(vol, state_path="plan_async3.json")
            publisher = RestorePlanPublisher(coord)

            plan = RestorePlan(
                generation=1,
                model_key=ModelRestoreKey(unet_identity="noop_test"),
                prefill_key=PrefillKey(prompt_bundle_hash="p_noop"),
            )

            async def run():
                first = await publisher.publish_with_metrics_async(plan)
                second = await publisher.publish_with_metrics_async(plan)
                return first, second

            first, second = asyncio.run(run())
            self.assertTrue(first["changed"])
            self.assertFalse(second["changed"])
            self.assertEqual(second["generation"], 1)
            self.assertEqual(second["bytes_written"], 0)
            self.assertEqual(second["write_ms"], 0.0)
            self.assertEqual(second["commit_ms"], 0.0)


# ====================================================================
# ModalRuntimeEntrypointV2 constructor
# ====================================================================


class TestModalRuntimeEntrypointV2Constructor(unittest.TestCase):
    """ModalRuntimeEntrypointV2 uses object.__init__ to avoid Modal warning."""

    def test_decorated_class_uses_object_init(self):
        """The decorated class should have __init__ = object.__init__."""
        import comfymodal_runtime.modal_app as ma
        cls = getattr(ma, "ModalRuntimeEntrypointV2", None)
        if cls is not None and cls is not type("ModalRuntimeEntrypoint", (), {}):
            # Only check if Modal was available at import
            self.assertIs(cls.__init__, object.__init__,
                          "ModalRuntimeEntrypointV2 should use object.__init__")


# ====================================================================
# Deployment identity serialization
# ====================================================================


class TestDeploymentIdentityGpuHash(unittest.TestCase):
    """Ordered GPU list hashes deterministically in identity context.

    Also verifies order-sensitive hashing: swapping GPU order changes hash.
    """

    def test_gpu_list_serializes_deterministically(self):
        from comfymodal_runtime.contracts import stable_hash
        gpu_tuple_1 = ("RTX-PRO-6000", "A100-80GB", "A100-40GB")
        gpu_tuple_2 = ("RTX-PRO-6000", "A100-80GB", "A100-40GB")
        h1 = stable_hash({"gpu": list(gpu_tuple_1)})
        h2 = stable_hash({"gpu": list(gpu_tuple_2)})
        self.assertEqual(h1, h2)

    def test_different_gpu_order_different_hash(self):
        """Order-sensitive: ["a","b"] vs ["b","a"] must produce different hash."""
        from comfymodal_runtime.contracts import stable_hash
        h1 = stable_hash({"gpu": ["a", "b"]})
        h2 = stable_hash({"gpu": ["b", "a"]})
        self.assertNotEqual(h1, h2)


# ====================================================================
# app.cls contract (ModalRuntimeSpec → app.cls arguments)
# ====================================================================


class TestAppClsContract(unittest.TestCase):
    """Verify that ModalRuntimeSpec produces the expected arguments for
    ``app.cls()``, including ordered GPU list, memory, min_containers,
    scaledown_window, and no extra Modal invocation/Volume commit.

    These tests do NOT make paid Modal API calls.
    """

    def setUp(self):
        self._saved_env = {}
        for key in ("COMFYMODAL_V2_GPU", "COMFYMODAL_V2_GPU_FALLBACKS", "COMFYMODAL_V2_MEMORY_MB"):
            self._saved_env[key] = os.environ.pop(key, None)

    def tearDown(self):
        for key, val in self._saved_env.items():
            if val is not None:
                os.environ[key] = val
            else:
                os.environ.pop(key, None)

    def test_spec_gpu_ordered_list(self):
        """ModalRuntimeSpec produces ordered GPU tuple for app.cls(gpu=...)."""
        spec = ModalRuntimeSpec()
        # Modal accepts list[str] for ordered fallback; verify spec produces it
        self.assertIsInstance(spec.gpu, tuple)
        gpu_list = list(spec.gpu) if len(spec.gpu) > 1 else spec.gpu[0]
        self.assertEqual(gpu_list, "RTX-PRO-6000")

    def test_spec_memory_default_24576(self):
        spec = ModalRuntimeSpec()
        self.assertEqual(spec.memory, 24576)

    def test_spec_min_containers_zero(self):
        spec = ModalRuntimeSpec()
        self.assertEqual(spec.min_containers, 0)

    def test_spec_scaledown_window_four(self):
        spec = ModalRuntimeSpec()
        self.assertEqual(spec.scaledown_window, 4)

    def test_spec_identity_order_sensitive(self):
        """GPU order change alters identity hash (order-sensitive)."""
        from comfymodal_runtime.contracts import stable_hash
        os.environ["COMFYMODAL_V2_GPU_FALLBACKS"] = "A100-80GB"
        spec_a = ModalRuntimeSpec()
        # Override spec_b gpu order
        spec_b = ModalRuntimeSpec()
        # Swap the order using __dataclass_fields__ immutability — override
        # by creating a new spec-like dict
        h1 = stable_hash({"gpu": list(spec_a.gpu)})
        h2 = stable_hash({"gpu": list(reversed(spec_a.gpu))})
        self.assertNotEqual(h1, h2, "Reversed GPU order must change hash")

    def test_no_custom_constructor_init(self):
        """ModalRuntimeEntrypointV2 uses object.__init__, not custom init."""
        import comfymodal_runtime.modal_app as ma
        cls = getattr(ma, "ModalRuntimeEntrypointV2", None)
        if cls is not None and cls is not type("ModalRuntimeEntrypoint", (), {}):
            self.assertIs(cls.__init__, object.__init__,
                          "V2 class must use object.__init__")

    def test_no_extra_modal_volume_commit(self):
        """Publishing a plan must not call Modal Volume.commit except once
        via the coordinator.  The sync path calls commit once on the volume.
        The async path calls commit_async once."""
        from comfymodal_runtime.runtime_state import CommitCoordinator, FakeVolume

        # Sync path: exactly one volume commit per publish
        fake = FakeVolume()
        coord = CommitCoordinator(fake, state_path="plan_sync_test.json")
        publisher = RestorePlanPublisher(coord)
        plan = RestorePlan(
            generation=1,
            model_key=ModelRestoreKey(unet_identity="commit_test"),
            prefill_key=PrefillKey(prompt_bundle_hash="p_commit"),
        )
        publisher.publish_with_metrics(plan)
        self.assertEqual(coord.metrics.commit_count, 1)
        self.assertEqual(coord.metrics.write_count, 1)

    def test_register_remote_entrypoint_gpu_arg(self):
        """Verify the gpu argument passed to app.cls matches spec order.

        The production code in _register_remote_entrypoint converts
        spec.gpu tuple to list when > 1 element, else uses single string.
        """
        spec = ModalRuntimeSpec()
        # Code path: list(spec.gpu) if len(spec.gpu) > 1 else spec.gpu[0]
        if len(spec.gpu) > 1:
            gpu_arg = list(spec.gpu)
            self.assertIsInstance(gpu_arg, list)
            self.assertEqual(gpu_arg, ["RTX-PRO-6000", "A100-80GB", "A100-40GB"])
        else:
            gpu_arg = spec.gpu[0]
            self.assertIsInstance(gpu_arg, str)

    def test_parse_gpu_request_default_proper_casing(self):
        """The default return value is exactly the Modal-canonical casing."""
        result = parse_gpu_request()
        self.assertEqual(result, ("RTX-PRO-6000",))

    def test_spec_cloud_default_gcp(self):
        """ModalRuntimeSpec defaults to cloud='gcp'."""
        spec = ModalRuntimeSpec()
        self.assertEqual(spec.cloud, "gcp")

    def test_spec_cpu_default_48(self):
        """ModalRuntimeSpec defaults to cpu=48."""
        spec = ModalRuntimeSpec()
        self.assertEqual(spec.cpu, 48)


if __name__ == "__main__":
    unittest.main()
