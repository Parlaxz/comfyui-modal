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
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "clip.safetensors"
            path.write_bytes(b"x")
            with patch.object(module, "_resolve_preload_mode", return_value="clip_only"):
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
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "clip.safetensors"
            path.write_bytes(b"x")
            timer = threading.Timer(1.2, release.set)
            timer.start()
            try:
                with (
                    patch.object(module, "PRELOAD_OUTLIER_ABORT_SECONDS", 0.01),
                    patch.object(module, "_resolve_preload_mode", return_value="clip_only"),
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
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "clip.safetensors"
            path.write_bytes(b"x")
            with patch.object(module, "_resolve_preload_mode", return_value="clip_only"):
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
