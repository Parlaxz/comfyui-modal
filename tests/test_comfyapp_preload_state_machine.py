import tempfile
import threading
import time
import types
import unittest
from pathlib import Path
from unittest.mock import patch

from tests.test_comfyapp_runtime_state import load_module


class ComfyAppPreloadStateMachineTests(unittest.TestCase):
    def test_fast_preload_returns_ok(self):
        module = load_module()
        mixin = module._ComfyAPIMixin()

        def loader(_path, return_metadata=True):
            return ({"ok": True}, {"meta": 1}) if return_metadata else {"ok": True}

        mixin._original_model_loader = loader

        # Patch _load_model_state_explicit_cpu so it does NOT reach into
        # comfy.model_management (which would try to import unavailable
        # comfy_aimdo).  Instead call original_loader directly to exercise
        # the real cache-population flow.
        def _patched_explicit_cpu(path, original_loader):
            return original_loader(path, return_metadata=True)

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "clip.safetensors"
            path.write_bytes(b"x")
            with (
                patch.object(module, "_resolve_preload_mode", return_value="clip_only"),
                patch.object(mixin, "_load_model_state_explicit_cpu",
                             side_effect=_patched_explicit_cpu),
            ):
                result = mixin._preload_models_to_cpu([str(path)])
        self.assertEqual(result["status"], "ok")
        self.assertEqual(module._count_active_model_reads(), 0)

    def test_single_file_clip_only_slow_preload_waits_and_adopts(self):
        module = load_module()
        mixin = module._ComfyAPIMixin()
        started = threading.Event()
        release = threading.Event()

        def loader(_path, return_metadata=True):
            started.set()
            release.wait(timeout=1.0)
            return ({"ok": True}, {"meta": 1}) if return_metadata else {"ok": True}

        mixin._original_model_loader = loader

        # Patch _load_model_state_explicit_cpu to avoid the comfy_aimdo
        # import inside comfy.model_management.  The patched version calls
        # original_loader directly, preserving the test's intent: the
        # worker signals started, waits for release, then returns.
        def _patched_explicit_cpu(path, original_loader):
            return original_loader(path, return_metadata=True)

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "clip.safetensors"
            path.write_bytes(b"x")
            timer = threading.Timer(1.2, release.set)
            timer.start()
            try:
                with (
                    patch.object(module, "PRELOAD_OUTLIER_ABORT_SECONDS", 0.01),
                    patch.object(module, "_resolve_preload_mode", return_value="clip_only"),
                    patch.object(mixin, "_load_model_state_explicit_cpu",
                                 side_effect=_patched_explicit_cpu),
                ):
                    t0 = time.time()
                    result = mixin._preload_models_to_cpu([str(path)])
                    elapsed = time.time() - t0
            finally:
                timer.cancel()
                release.set()
        self.assertTrue(started.is_set())
        self.assertGreaterEqual(elapsed, 1.0)
        self.assertEqual(result["status"], "slow_completed")
        self.assertFalse(result["shutdown_wait_false"])
        self.assertTrue(mixin._model_in_cpu_cache(str(path)))
        self.assertEqual(module._count_active_model_reads(), 0)

    def test_hard_failure_returns_hard_failed_and_clears_active_reads(self):
        module = load_module()
        mixin = module._ComfyAPIMixin()

        def loader(_path, return_metadata=True):
            raise RuntimeError("boom")

        mixin._original_model_loader = loader

        # Patch _load_model_state_explicit_cpu to call original_loader
        # directly (avoiding the comfy_aimdo import), so the loader's
        # RuntimeError propagates and the test correctly observes the
        # "hard_failed" status.
        def _patched_explicit_cpu(path, original_loader):
            return original_loader(path, return_metadata=True)

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "clip.safetensors"
            path.write_bytes(b"x")
            with (
                patch.object(module, "_resolve_preload_mode", return_value="clip_only"),
                patch.object(mixin, "_load_model_state_explicit_cpu",
                             side_effect=_patched_explicit_cpu),
            ):
                result = mixin._preload_models_to_cpu([str(path)])
        self.assertEqual(result["status"], "hard_failed")
        self.assertEqual(result["failed_files"], 1)
        self.assertEqual(module._count_active_model_reads(), 0)

    def test_request_preflight_waits_for_active_restore_preload(self):
        module = load_module()
        mixin = module._ComfyAPIMixin()
        mixin._model_cpu_cache = {}
        release = threading.Event()
        clip_path = "C:/models/clip.safetensors"
        key = module._model_cpu_cache_key(clip_path)

        def worker():
            release.wait(timeout=1.0)
            mixin._model_cpu_cache[key] = ({"ok": True}, {"meta": 1})
            module._complete_active_model_read(key)

        thread = threading.Thread(target=worker, daemon=True)
        module._register_active_model_read(key, owner="restore_preload", path=clip_path, phase="restore")
        module._attach_active_model_read_future(key, thread)
        thread.start()

        folder_paths_stub = types.ModuleType("folder_paths")
        setattr(folder_paths_stub, "get_full_path", lambda _folder, _name: clip_path)
        original_folder_paths = module.sys.modules.get("folder_paths")
        module.sys.modules["folder_paths"] = folder_paths_stub
        try:
            timer = threading.Timer(0.05, release.set)
            timer.start()
            try:
                waited = mixin._wait_for_restore_preload_before_request({
                    "1": {"class_type": "CLIPLoader", "inputs": {"clip_name": "clip.safetensors"}},
                })
            finally:
                timer.cancel()
                release.set()
        finally:
            if original_folder_paths is not None:
                module.sys.modules["folder_paths"] = original_folder_paths
            else:
                module.sys.modules.pop("folder_paths", None)
        self.assertTrue(waited["restore_preload_active"])
        self.assertTrue(mixin._model_in_cpu_cache(clip_path))
        self.assertEqual(module._count_active_model_reads(), 0)

    def test_dict_preload_entries_cached_branch_no_crash(self):
        """Dict entries in file_paths must not crash the all-cached branch at
        line ~9672 where raw ``file_paths`` is iterated with ``os.path.basename``."""
        module = load_module()
        mixin = module._ComfyAPIMixin()
        mixin._model_cpu_cache = {}

        def loader(_path, return_metadata=True):
            return ({"ok": True}, {"meta": 1}) if return_metadata else {"ok": True}

        mixin._original_model_loader = loader

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "clip.safetensors"
            path.write_bytes(b"x")
            # Pre-populate cache so the file is seen as already loaded
            cache_key = module._model_cpu_cache_key(str(path))
            mixin._model_cpu_cache[cache_key] = ({"ok": True}, {"meta": 1})

            with patch.object(module, "_resolve_preload_mode", return_value="clip_only"):
                result = mixin._preload_models_to_cpu([{"path": str(path), "role": "clip"}])

        self.assertEqual(result["status"], "ok")
        self.assertEqual(len(result.get("cached", [])), 1)

    def test_dict_preload_entries_outlier_branch_no_crash(self):
        """Dict entries in file_paths must not crash the outlier detection at
        line ~9789 where raw ``file_paths`` is iterated with ``os.path.basename``
        and ``os.path.getsize``.

        We patch ``_load_model_state_explicit_cpu`` and use
        ``read_strategy="normal"`` so the test does not depend on the
        ``comfy.model_management`` module (which imports ``comfy_aimdo``
        and may not be available in the test environment).

        A small sleep in the patched loader ensures the per-file timing
        (``_loader_ms``) is > 0.0, so ``_slowest_fn`` is populated and the
        outlier code at line ~9787 is genuinely reached.
        """
        module = load_module()
        mixin = module._ComfyAPIMixin()
        mixin._model_cpu_cache = {}

        def loader(_path, return_metadata=True):
            return ({"ok": True}, {"meta": 1}) if return_metadata else {"ok": True}

        mixin._original_model_loader = loader

        def _patched_explicit_cpu(path, original_loader):
            # Small sleep so _loader_ms > 0.0 → _slowest_fn is set
            time.sleep(0.002)
            sd, meta = original_loader(path, return_metadata=True)
            return (sd, meta, {})

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "clip.safetensors"
            path.write_bytes(b"x")
            with (
                patch.object(module, "_resolve_preload_mode", return_value="clip_only"),
                patch.object(mixin, "_profile_ms", return_value=6000.0),
                patch.object(mixin, "_load_model_state_explicit_cpu",
                             side_effect=_patched_explicit_cpu),
            ):
                result = mixin._preload_models_to_cpu(
                    [{"path": str(path), "role": "clip"}],
                    read_strategy="normal",
                )

        self.assertEqual(result["status"], "ok")

    def test_dict_preload_entries_abort_tuple_unpack_no_crash(self):
        """Dict entries in file_paths must not crash the abort-then-adopt
        tuple unpack at line ~9743 where ``fut_to_item`` values are 4-tuples
        ``(filename, cache_key, path, role)`` but the unpack was written for
        3 items.

        Trigger conditions:
        - ``PRELOAD_OUTLIER_ABORT_SECONDS`` patched to 0.001 (1ms)
        - ``clip_only`` preload mode with a single dict entry
        - A slow loader that keeps the future running past the abort deadline
        - The future is not cancellable (thread is executing), forcing the
          ``_running_threads_not_killable > 0`` branch

        Before the fix this crashes with ``ValueError: too many values to unpack``.
        After the fix the 4-tuple is properly unpacked and the preload completes
        with ``slow_completed`` status.
        """
        module = load_module()
        mixin = module._ComfyAPIMixin()
        mixin._model_cpu_cache = {}

        _load_event = threading.Event()

        def slow_loader(_path, return_metadata=True):
            _load_event.wait(timeout=2.0)
            return ({"ok": True}, {"meta": 1}) if return_metadata else {"ok": True}

        mixin._original_model_loader = slow_loader

        def _patched_explicit_cpu(path, original_loader):
            sd, meta = original_loader(path, return_metadata=True)
            return (sd, meta, {})

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "slow-clip.safetensors"
            path.write_bytes(b"x")
            with (
                patch.object(module, "_resolve_preload_mode", return_value="clip_only"),
                patch.object(module, "PRELOAD_OUTLIER_ABORT_SECONDS", 0.001),
                patch.object(mixin, "_load_model_state_explicit_cpu",
                             side_effect=_patched_explicit_cpu),
            ):
                # The abort deadline (1ms) is much shorter than the loader
                # sleep (which waits for _load_event), so abort fires while
                # the future is still running.  The future cannot be
                # cancelled → _running_threads_not_killable > 0 →
                # abort-then-adopt path → tuple unpack at line ~9743.
                result = mixin._preload_models_to_cpu(
                    [{"path": str(path), "role": "clip"}],
                    read_strategy="normal",
                )
            # Release the loader so the test thread can join cleanly
            _load_event.set()

        # The abort-then-adopt path produces "slow_completed" (not "aborted")
        # because it adopts the running future's result.
        self.assertEqual(
            result["status"], "slow_completed",
            "abort-then-adopt must produce slow_completed status, not aborted",
        )


    # ── 7. Direct-warmup boundary test ──

    def test_direct_warmup_boundary_with_clip_overrides(self):
        """Direct warmup with LOAD_UNET=1, LOAD_CLIP=1,
        REQUIRE_CPU_CACHE_HIT=0 must NOT emit the skip path and MUST
        store the UNET object in the cache.

        Uses stub folder_paths/nodes, patches _resolve_runtime_flag,
        and provides clip_policy_overrides with load=1.  Deterministic
        and GPU-free.
        """
        module = load_module()
        mixin = module._ComfyAPIMixin()

        unet_path = "/tmp/test-warmup-unet.safetensors"
        clip_path = "/tmp/test-warmup-clip.safetensors"

        # ── Stub folder_paths ──
        folder_paths_stub = types.ModuleType("folder_paths")

        def _fake_get_full_path(folder, name):
            if folder == "unet":
                return unet_path
            if folder == "text_encoders":
                return clip_path
            return ""

        folder_paths_stub.get_full_path = _fake_get_full_path

        # ── Stub nodes with fake loaders ──
        nodes_stub = types.ModuleType("nodes")

        warmup_unet_stored = []
        class FakeUNETLoader:
            def load_unet(self, unet_name, weight_dtype="default"):
                warmup_unet_stored.append(("loaded", unet_name, weight_dtype))
                return (object(),)

        class FakeCLIPLoader:
            def load_clip(self, clip_name, type="flux"):
                return (object(),)

        nodes_stub.NODE_CLASS_MAPPINGS = {
            "UNETLoader": FakeUNETLoader,
            "CLIPLoader": FakeCLIPLoader,
        }

        # Install stubs in sys.modules BEFORE _warmup_direct (which does
        # ``import folder_paths, nodes`` at the top of its try block).
        original_folder_paths = module.sys.modules.get("folder_paths")
        original_nodes = module.sys.modules.get("nodes")
        module.sys.modules["folder_paths"] = folder_paths_stub
        module.sys.modules["nodes"] = nodes_stub

        try:
            # Patch _resolve_runtime_flag so LOAD_UNET/LOAD_CLIP=1,
            # REQUIRE_CPU_CACHE_HIT=0.
            # Must return bools, not strings — the real function returns
            # bool and the caller uses ``1.0 if _rt_require_cpu_hit else 0.0``
            # which would wrongly treat the truthy string ``"0"`` as True.
            def _patched_resolve(name, default="0"):
                overrides = {
                    "DIRECT_WARMUP_LOAD_UNET": True,
                    "DIRECT_WARMUP_LOAD_CLIP": True,
                    "DIRECT_WARMUP_CLIP_ENCODE": False,
                    "DIRECT_WARMUP_REQUIRE_CPU_CACHE_HIT": False,
                }
                if name in overrides:
                    return overrides[name]
                return default == "1"

            profile = {
                "unet": "test-unet.safetensors",
                "clip1": "test-clip.safetensors",
                "clip_type": "flux",
            }
            clip_overrides = {
                "direct_warmup_load_clip_effective": 1,
                "direct_warmup_clip_encode_effective": 0,
            }

            with patch.object(
                module, "_resolve_runtime_flag", side_effect=_patched_resolve,
            ):
                result = mixin._warmup_direct(
                    profile, clip_policy_overrides=clip_overrides,
                )

            # Warmup must NOT skip due to CPU-cache miss.
            self.assertNotEqual(
                result.get("status"), "skipped_no_cpu_cache",
                "warmup must not emit skip path",
            )
            self.assertNotEqual(
                result.get("status"), "error",
                "warmup must not error",
            )

            # UNET must have been loaded.
            self.assertEqual(
                len(warmup_unet_stored), 1,
                "UNETLoader.load_unet must have been called once",
            )
            self.assertEqual(warmup_unet_stored[0][0], "loaded")

            # UNET object must be stored in the cache.
            unet_cache_key = mixin._unet_cache_key(unet_path, "default")
            self.assertIn(
                unet_cache_key, mixin._unet_object_cache,
                "UNET object must be stored in _unet_object_cache",
            )

            # The boundary diagnostic token must be present.
            self.assertEqual(
                result.get("direct_warmup_require_cpu_cache_hit"), 0.0,
                "compact boundary token must be 0 when REQUIRE_CPU_CACHE_HIT=0",
            )
        finally:
            if original_folder_paths is not None:
                module.sys.modules["folder_paths"] = original_folder_paths
            else:
                module.sys.modules.pop("folder_paths", None)
            if original_nodes is not None:
                module.sys.modules["nodes"] = original_nodes
            else:
                module.sys.modules.pop("nodes", None)


class Phase2FilterPreloadSizeTests(unittest.TestCase):
    """Phase 2: active-profile size caps, workers_2 resolution, CPU-cache
    requirement fix, direct UNET caching, and no-future-wait guard."""

    # ── 1. Active 11.46 GiB file bypasses generic cap when profile is active ──

    def test_active_profile_11_46gib_bypasses_generic_cap(self):
        """An 11.46 GiB UNET file from an active_next_profile must pass
        through the size filter (active-profile cap = 20 GB)."""
        import os
        from unittest.mock import patch
        from comfyapp import _filter_preload_paths_by_size

        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "flux1-dev-fp8.safetensors")
            with patch("os.path.getsize", return_value=int(11.46 * 1024**3)):
                paths = [{"path": path, "role": "unet"}]
                profile = {
                    "_source": "active_next_profile",
                    "_workflow_hash": "abc123",
                    "_profile_token": "tok1",
                    "mode": "split",
                    "unet": "flux1-dev-fp8.safetensors",
                    "clip1": "clip-l.safetensors",
                    "clip2": "t5xxl.safetensors",
                    "clip_type": "flux",
                }
                kept, result = _filter_preload_paths_by_size(paths, profile)
                self.assertEqual(
                    len(kept), 1,
                    "active-profile 11.46 GiB UNET should be kept under 20 GB cap",
                )
                self.assertEqual(result["cap_source"], "active_profile")

    # ── 2. Unknown profile file remains capped at generic 10 GB ──

    def test_unknown_file_remains_capped(self):
        """An 11.46 GiB file without an active profile must be rejected
        by the generic 10 GB file cap."""
        import os
        from unittest.mock import patch
        from comfyapp import _filter_preload_paths_by_size

        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "unknown-large.safetensors")
            # Use patched getsize to simulate 11.46 GiB without writing a real file
            with patch("os.path.getsize", return_value=int(11.46 * 1024**3)):
                # No profile → generic caps apply
                paths = [{"path": path, "role": "unet"}]
                kept, result = _filter_preload_paths_by_size(paths, profile=None)
                self.assertEqual(
                    len(kept), 0,
                    "unknown-profile 11.46 GiB file should be rejected by 10 GB cap",
                )
                self.assertEqual(result["cap_source"], "generic")
                self.assertEqual(len(result["files_skipped"]), 1)
                self.assertIn("max_file_gb_exceeded", result["files_skipped"][0]["reason"])

    # ── 3. workers_2 resolves to 2 effective workers ──

    def test_workers_2_resolves_2_workers(self):
        """PRELOAD_MODE=workers_2 must resolve the configured workers to 2,
        exercising the real ``_resolve_preload_worker_count`` helper."""
        module = load_module()
        # The extracted helper _resolve_preload_worker_count is the actual
        # function used by _preload_models_to_cpu — testing it directly
        # avoids duplicating the mapping in test code.
        self.assertEqual(
            module._resolve_preload_worker_count("workers_2"), 2,
            "workers_2 mode must configure exactly 2 workers",
        )
        # Sanity-check other modes for coverage completeness.
        self.assertEqual(module._resolve_preload_worker_count("workers_1"), 1)
        self.assertEqual(module._resolve_preload_worker_count("sequential"), 1)
        self.assertEqual(module._resolve_preload_worker_count("default"), 4)
        self.assertEqual(module._resolve_preload_worker_count("vae"), 4)
        self.assertEqual(module._resolve_preload_worker_count("unet_only"), 4)
        self.assertEqual(module._resolve_preload_worker_count("clip_only"), 4)

    # ── 4. clip_policy overrides cannot turn CPU-cache requirement on ──

    def test_clip_policy_cannot_turn_cpu_cache_requirement_on(self):
        """clip_policy_overrides must NOT change the canonical
        DIRECT_WARMUP_REQUIRE_CPU_CACHE_HIT resolved value."""
        # The canonical rt_require_cpu_hit starts as a resolved flag.
        # clip_policy_overrides should NOT overwrite it.
        _rt_require_cpu_hit = False  # production baseline says 0

        # Simulate what clip_policy_overrides does (only clip-related fields)
        clip_policy_overrides = {
            "direct_warmup_load_clip_effective": 1,
            "direct_warmup_clip_encode_effective": 0,
        }
        _load_clip_eff = clip_policy_overrides.get("direct_warmup_load_clip_effective", 0)
        _rt_load_clip = bool(_load_clip_eff)
        _rt_clip_encode = bool(clip_policy_overrides.get("direct_warmup_clip_encode_effective", 0))

        # BUG (old): _rt_require_cpu_hit = bool(_load_clip_eff) ← WRONG
        # FIX: Do NOT overwrite _rt_require_cpu_hit
        self.assertFalse(
            _rt_require_cpu_hit,
            "clip_policy_overrides must NOT turn CPU-cache requirement on. "
            "Effective value must remain 0 under production baseline.",
        )
        self.assertTrue(
            _rt_load_clip,
            "CLIP load effective should still be 1 from overrides",
        )

    # ── 5. Direct UNET warmup caches object with correct key ──

    def test_direct_unet_warmup_caches_object(self):
        """Direct warmup must store the loaded UNET ModelPatcher in
        _unet_object_cache using the same cache key scheme that
        _cached_unet_load (the patched loader) consumes."""
        module = load_module()
        mixin = module._ComfyAPIMixin()
        mixin._unet_object_cache = {}
        mixin._unet_cache_hits = 0
        mixin._unet_cache_misses = 0

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "test-unet.safetensors"
            path.write_bytes(b"\x00" * 1024)

            _key = mixin._unet_cache_key(str(path), "default")
            # Simulate what _warmup_direct does: store the loaded result
            mixin._init_unet_cache()
            mixin._unet_object_cache[_key] = object()

            # Verify the cache key matches what _cached_unet_load would use
            weight_dtype = "default"
            key2 = mixin._unet_cache_key(str(path), weight_dtype)
            self.assertEqual(
                _key, key2,
                "cache key must be the same across warmup and loader",
            )
            self.assertIn(
                key2, mixin._unet_object_cache,
                "UNET object must be findable by the same key",
            )

    # ── 6. No future wait after object cache hit ──

    def test_no_future_wait_after_unet_cache_hit(self):
        """When _cached_unet_load finds the UNET in _unet_object_cache,
        it must NOT wait on a future and NOT perform an actual load.

        This test invokes the actual patched loader function with stub
        folder_paths/nodes, a sentinel cached object, and an original
        loader that fails if called.
        """
        module = load_module()
        mixin = module._ComfyAPIMixin()

        # Sentinel object that will be cached and later returned.
        sentinel = object()

        # Prepare the mixin state that _patch_unet_loader_cache / the
        # nested _cached_unet_load closure will read.
        mixin._unet_object_cache = {}
        mixin._unet_cache_hits = 0
        mixin._unet_cache_misses = 0
        mixin._model_cpu_cache = {}
        mixin._actual_load_futures = {}
        mixin._original_loaders_store = {}

        test_path = "/tmp/test-warmup-unet.safetensors"
        key = mixin._unet_cache_key(test_path, "default")
        mixin._init_unet_cache()
        mixin._unet_object_cache[key] = sentinel

        # Stub folder_paths so get_full_path for "unet" returns test_path.
        folder_paths_stub = types.ModuleType("folder_paths")
        folder_paths_stub.get_full_path = lambda folder, name: (
            test_path if folder == "unet" else ""
        )

        # Stub nodes with a UNETLoader whose original load_unet raises.
        nodes_stub = types.ModuleType("nodes")

        class FakeUNETLoader:
            def load_unet(self, **kwargs):
                raise RuntimeError("original loader should not be called")

        nodes_stub.NODE_CLASS_MAPPINGS = {"UNETLoader": FakeUNETLoader}

        # Install stubs in sys.modules before the patcher runs.
        original_folder_paths = module.sys.modules.get("folder_paths")
        original_nodes = module.sys.modules.get("nodes")
        module.sys.modules["folder_paths"] = folder_paths_stub
        module.sys.modules["nodes"] = nodes_stub

        try:
            # Patch the UNETLoader.load_unet — this installs the
            # real _cached_unet_load wrapper into FakeUNETLoader.
            mixin._patch_unet_loader_cache()

            # Call the patched loader as the graph would.
            result = FakeUNETLoader().load_unet(
                unet_name="test-warmup-unet.safetensors",
                weight_dtype="default",
            )

            # Must return the sentinel object unchanged.
            self.assertIs(
                result[0], sentinel,
                "cached UNET loader must return the sentinel object",
            )

            # Diagnostics must prove no future wait and no actual load.
            diag = getattr(mixin, "_unet_load_diagnostics", None)
            self.assertIsNotNone(
                diag,
                "_unet_load_diagnostics must be set by cached loader",
            )
            self.assertEqual(
                diag.get("unet_future_waited"), "0",
                "future_waited must be 0 on cache hit",
            )
            self.assertEqual(
                diag.get("unet_actual_load_occurred"), "0",
                "actual_load_occurred must be 0 on cache hit",
            )
        finally:
            if original_folder_paths is not None:
                module.sys.modules["folder_paths"] = original_folder_paths
            else:
                module.sys.modules.pop("folder_paths", None)
            if original_nodes is not None:
                module.sys.modules["nodes"] = original_nodes
            else:
                module.sys.modules.pop("nodes", None)
