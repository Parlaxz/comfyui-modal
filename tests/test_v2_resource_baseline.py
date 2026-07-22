"""Focused tests for V2 resource defaults, host-memory reporting, identity hashing."""

from __future__ import annotations

import os
import platform
import unittest
import io
from unittest.mock import patch

from gpu_catalog import (
    DEFAULT_GPU,
    V2_DEFAULT_GPU,
    DEFAULT_GPU_FALLBACKS,
    parse_gpu_request,
)
from comfymodal_runtime.modal_app import (
    _parse_memory_mb,
    _report_host_memory,
    _resolve_cgroup_v2_base,
    _resource_identity,
    _register_remote_entrypoint,
    ModalRuntimeSpec,
    MIN_CONTAINERS,
    SCALEDOWN_WINDOW,
    _V2_DEPLOYMENT_COMBINED_HASH,
)
from comfymodal_runtime.contracts import stable_hash


class TestV2Defaults(unittest.TestCase):
    """Stable V2 resource defaults."""

    def test_default_gpu_is_rtx_pro_6000(self):
        self.assertEqual(V2_DEFAULT_GPU, "RTX-PRO-6000")

    def test_default_gpu_fallbacks_empty(self):
        self.assertEqual(DEFAULT_GPU_FALLBACKS, ())

    def test_parse_gpu_request_defaults_to_single_string(self):
        saved = os.environ.pop("COMFYMODAL_V2_GPU", None)
        saved_fb = os.environ.pop("COMFYMODAL_V2_GPU_FALLBACKS", None)
        try:
            result = parse_gpu_request()
            self.assertIsInstance(result, tuple)
            self.assertEqual(len(result), 1)
            self.assertEqual(result[0], "RTX-PRO-6000")
        finally:
            if saved is not None:
                os.environ["COMFYMODAL_V2_GPU"] = saved
            if saved_fb is not None:
                os.environ["COMFYMODAL_V2_GPU_FALLBACKS"] = saved_fb

    def test_parse_gpu_request_empty_fallback_yields_single_string(self):
        saved = os.environ.pop("COMFYMODAL_V2_GPU", None)
        os.environ["COMFYMODAL_V2_GPU_FALLBACKS"] = ""
        try:
            result = parse_gpu_request()
            self.assertIsInstance(result, tuple)
            self.assertEqual(len(result), 1)
            self.assertEqual(result[0], "RTX-PRO-6000")
        finally:
            if saved is not None:
                os.environ["COMFYMODAL_V2_GPU"] = saved
            os.environ.pop("COMFYMODAL_V2_GPU_FALLBACKS", None)

    def test_parse_gpu_request_explicit_fallbacks_preserved(self):
        saved = os.environ.pop("COMFYMODAL_V2_GPU", None)
        os.environ["COMFYMODAL_V2_GPU_FALLBACKS"] = "A100-80GB,H100"
        try:
            result = parse_gpu_request()
            self.assertEqual(len(result), 3)
            self.assertEqual(result[0], "RTX-PRO-6000")
            self.assertIn("A100-80GB", result)
            self.assertIn("H100", result)
        finally:
            if saved is not None:
                os.environ["COMFYMODAL_V2_GPU"] = saved
            os.environ.pop("COMFYMODAL_V2_GPU_FALLBACKS", None)

    def test_parse_gpu_request_explicit_fallbacks_ordered_list(self):
        saved = os.environ.pop("COMFYMODAL_V2_GPU", None)
        os.environ["COMFYMODAL_V2_GPU_FALLBACKS"] = "L40S,T4"
        try:
            result = parse_gpu_request()
            self.assertEqual(len(result), 3)
            self.assertEqual(result[0], "RTX-PRO-6000")
            self.assertEqual(result[1], "L40S")
            self.assertEqual(result[2], "T4")
        finally:
            if saved is not None:
                os.environ["COMFYMODAL_V2_GPU"] = saved
            os.environ.pop("COMFYMODAL_V2_GPU_FALLBACKS", None)

    def test_min_containers_zero(self):
        self.assertEqual(MIN_CONTAINERS, 0)

    def test_scaledown_window_four(self):
        self.assertEqual(SCALEDOWN_WINDOW, 4)

    def test_memory_default_is_24576(self):
        saved = os.environ.pop("COMFYMODAL_V2_MEMORY_MB", None)
        try:
            mem = _parse_memory_mb()
            self.assertEqual(mem, 24576)
        finally:
            if saved is not None:
                os.environ["COMFYMODAL_V2_MEMORY_MB"] = saved

    def test_memory_env_override(self):
        saved = os.environ.get("COMFYMODAL_V2_MEMORY_MB")
        os.environ["COMFYMODAL_V2_MEMORY_MB"] = "32768"
        try:
            mem = _parse_memory_mb()
            self.assertEqual(mem, 32768)
        finally:
            if saved is not None:
                os.environ["COMFYMODAL_V2_MEMORY_MB"] = saved
            else:
                os.environ.pop("COMFYMODAL_V2_MEMORY_MB", None)

    def test_empty_memory_override_uses_new_default(self):
        saved = os.environ.get("COMFYMODAL_V2_MEMORY_MB")
        os.environ["COMFYMODAL_V2_MEMORY_MB"] = ""
        try:
            self.assertEqual(_parse_memory_mb(), 24576)
        finally:
            if saved is not None:
                os.environ["COMFYMODAL_V2_MEMORY_MB"] = saved
            else:
                os.environ.pop("COMFYMODAL_V2_MEMORY_MB", None)

    def test_modal_runtime_spec_has_no_hard_memory_limit(self):
        spec = ModalRuntimeSpec()
        self.assertEqual(spec.memory, 24576)
        self.assertIsInstance(spec.memory, int)

    def test_modal_binding_uses_string_for_single_gpu_and_integer_memory(self):
        class FakeApp:
            def __init__(self):
                self.kwargs = None

            def cls(self, **kwargs):
                self.kwargs = kwargs
                return lambda cls: cls

        class FakeModal:
            @staticmethod
            def concurrent(**kwargs):
                return lambda cls: cls

        app = FakeApp()
        resources = {
            "app": app,
            "models_volume": object(),
            "custom_nodes_volume": object(),
            "runtime_state_volume": object(),
        }
        spec = ModalRuntimeSpec(gpu=("RTX-PRO-6000",), memory=24576)
        with patch("comfymodal_runtime.modal_app._modal", FakeModal()), patch(
            "comfymodal_runtime.modal_app._build_decorated_v2_class",
            return_value=object,
        ):
            _register_remote_entrypoint(resources, spec)
        self.assertEqual(app.kwargs["gpu"], "RTX-PRO-6000")
        self.assertIsInstance(app.kwargs["memory"], int)
        self.assertEqual(app.kwargs["memory"], 24576)
        self.assertEqual(app.kwargs["min_containers"], 0)
        self.assertEqual(app.kwargs["scaledown_window"], 4)

    def test_modal_binding_preserves_ordered_fallback_list(self):
        class FakeApp:
            def __init__(self):
                self.kwargs = None

            def cls(self, **kwargs):
                self.kwargs = kwargs
                return lambda cls: cls

        class FakeModal:
            @staticmethod
            def concurrent(**kwargs):
                return lambda cls: cls

        app = FakeApp()
        resources = {
            "app": app,
            "models_volume": object(),
            "custom_nodes_volume": object(),
            "runtime_state_volume": object(),
        }
        spec = ModalRuntimeSpec(
            gpu=("RTX-PRO-6000", "A100-80GB", "A100-40GB"),
            memory=24576,
        )
        with patch("comfymodal_runtime.modal_app._modal", FakeModal()), patch(
            "comfymodal_runtime.modal_app._build_decorated_v2_class",
            return_value=object,
        ):
            _register_remote_entrypoint(resources, spec)
        self.assertEqual(
            app.kwargs["gpu"],
            ["RTX-PRO-6000", "A100-80GB", "A100-40GB"],
        )


class TestCgroupV2PathResolution(unittest.TestCase):
    """Cgroup v2 base resolution via /proc/self/mountinfo and /proc/self/cgroup."""

    @staticmethod
    def _open_files(files):
        def open_file(path, *args, **kwargs):
            if path not in files:
                raise FileNotFoundError(path)
            return io.StringIO(files[path])

        return open_file

    def test_resolve_valid_mount_and_cgroup_files(self):
        files = {
            "/mountinfo": "36 29 0:32 / /custom\\040cgroup rw,relatime - cgroup2 cgroup rw\n",
            "/cgroup": "0::/user.slice/job\n",
        }
        with patch("builtins.open", side_effect=self._open_files(files)):
            self.assertEqual(
                _resolve_cgroup_v2_base("/mountinfo", "/cgroup"),
                "/custom cgroup/user.slice/job",
            )

    def test_resolve_missing_files_is_unavailable(self):
        with patch("builtins.open", side_effect=FileNotFoundError):
            self.assertIsNone(_resolve_cgroup_v2_base("/missing", "/missing"))

    def test_resolve_malformed_files_is_unavailable(self):
        files = {"/mountinfo": "not mountinfo\n", "/cgroup": "0::relative\n"}
        with patch("builtins.open", side_effect=self._open_files(files)):
            self.assertIsNone(_resolve_cgroup_v2_base("/mountinfo", "/cgroup"))

    def test_resolve_root_cgroup(self):
        files = {
            "/mountinfo": "36 29 0:32 / /custom/cgroup rw - cgroup2 cgroup rw\n",
            "/cgroup": "0::/\n",
        }
        with patch("builtins.open", side_effect=self._open_files(files)):
            self.assertEqual(
                _resolve_cgroup_v2_base("/mountinfo", "/cgroup"),
                "/custom/cgroup",
            )


class TestHostMemoryReporting(unittest.TestCase):
    """Host memory instrumentation — never fails, always returns dict with status."""

    def test_returns_dict_with_stage(self):
        result = _report_host_memory("test_stage")
        self.assertIsInstance(result, dict)
        self.assertEqual(result.get("stage"), "test_stage")

    def test_always_has_status(self):
        result = _report_host_memory("test")
        self.assertIn("status", result)

    def test_never_raises(self):
        try:
            _report_host_memory("safe")
        except Exception as exc:
            self.fail(f"_report_host_memory raised: {exc}")

    def test_status_is_ok(self):
        result = _report_host_memory("check")
        self.assertEqual(result.get("status"), "ok")

    def test_contains_process_maxrss_mib(self):
        result = _report_host_memory("rss_test")
        # process_maxrss_mib is only present on platforms with resource.getrusage
        if "process_maxrss_mib" in result:
            self.assertTrue(
                isinstance(result["process_maxrss_mib"], float)
                or result["process_maxrss_mib"] == "absent"
            )

    def test_absent_for_unavailable_memory_counters(self):
        result = _report_host_memory("absent_check")
        for key in (
            "memory.current",
            "memory.peak",
            "memory.max",
            "memory.events",
            "current_mib",
            "peak_mib",
            "limit_mib",
        ):
            self.assertIn(key, result)
            self.assertEqual(result[key], "absent")

    def test_contains_oom_count_or_absent(self):
        result = _report_host_memory("oom_test")
        val = result["oom_count"]
        self.assertTrue(isinstance(val, int) or val == "absent")

    def test_valid_memory_counters_are_emitted(self):
        with patch("comfymodal_runtime.modal_app.platform.system", return_value="Linux"), \
             patch("comfymodal_runtime.modal_app._resolve_cgroup_v2_base", return_value="/fake/cgroup"), \
             patch(
                 "comfymodal_runtime.modal_app._read_cgroup_v2_memory",
                 side_effect=lambda path: {
                     "memory.current": 2 * 1024 * 1024,
                     "memory.peak": 4 * 1024 * 1024,
                     "memory.max": 8 * 1024 * 1024,
                 }.get(os.path.basename(path)),
             ), \
             patch(
                 "builtins.open",
                 side_effect=lambda path, *args, **kwargs: io.StringIO(
                     "oom 2\noom_kill 1\n" if path.endswith("memory.events") else "VmRSS: 1024 kB\n"
                 ),
             ):
            result = _report_host_memory("valid")
        self.assertEqual(result["memory.current"], 2 * 1024 * 1024)
        self.assertEqual(result["memory.peak"], 4 * 1024 * 1024)
        self.assertEqual(result["memory.max"], 8 * 1024 * 1024)
        self.assertEqual(result["memory.events"], {"oom": 2, "oom_kill": 1})
        self.assertEqual(result["current_mib"], 2.0)
        self.assertEqual(result["limit_mib"], 8.0)
        self.assertEqual(result["oom_count"], 2)
        self.assertEqual(result["oom_kill_count"], 1)

    def test_unlimited_memory_limit_is_absent(self):
        with patch("comfymodal_runtime.modal_app.platform.system", return_value="Linux"), \
             patch("comfymodal_runtime.modal_app._resolve_cgroup_v2_base", return_value="/fake/cgroup"), \
             patch(
                 "comfymodal_runtime.modal_app._read_cgroup_v2_memory",
                 side_effect=lambda path: "max" if path.endswith("memory.max") else None,
             ), \
             patch("builtins.open", side_effect=FileNotFoundError):
            result = _report_host_memory("unlimited")
        self.assertEqual(result["memory.max"], "max")
        self.assertEqual(result["limit_mib"], "absent")

    def test_malformed_memory_files_are_absent_and_safe(self):
        with patch("comfymodal_runtime.modal_app.platform.system", return_value="Linux"), \
             patch("comfymodal_runtime.modal_app._resolve_cgroup_v2_base", return_value="/fake/cgroup"), \
             patch(
                 "comfymodal_runtime.modal_app._read_cgroup_v2_memory",
                 return_value=None,
             ), \
             patch("builtins.open", return_value=io.StringIO("oom not-a-number\n")):
            result = _report_host_memory("malformed")
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["memory.current"], "absent")
        self.assertEqual(result["memory.max"], "absent")
        self.assertEqual(result["memory.events"], "absent")
        self.assertEqual(result["oom_count"], "absent")


class TestIdentityHashing(unittest.TestCase):
    """Deployment-identity hashing for single-GPU and list GPU configs."""

    def test_single_gpu_resource_identity_has_string_gpu(self):
        spec = ModalRuntimeSpec()
        identity = _resource_identity(spec)
        gpu_val = identity.get("gpu", [])
        self.assertIsInstance(gpu_val, list)
        self.assertEqual(len(gpu_val), 1)
        self.assertEqual(gpu_val[0], "RTX-PRO-6000")

    def test_stable_hash_deterministic_for_same_gpu(self):
        h1 = stable_hash(["RTX-PRO-6000"])
        h2 = stable_hash(["RTX-PRO-6000"])
        self.assertEqual(h1, h2)

    def test_stable_hash_deterministic_for_gpu_list(self):
        h1 = stable_hash(["RTX-PRO-6000", "A100-80GB", "H100"])
        h2 = stable_hash(["RTX-PRO-6000", "A100-80GB", "H100"])
        self.assertEqual(h1, h2)

    def test_stable_hash_differs_for_different_gpu_configs(self):
        h_single = stable_hash(["RTX-PRO-6000"])
        h_list = stable_hash(["RTX-PRO-6000", "A100-80GB"])
        self.assertNotEqual(h_single, h_list)

    def test_stable_hash_differs_for_different_order(self):
        h1 = stable_hash(["A100-80GB", "H100"])
        h2 = stable_hash(["H100", "A100-80GB"])
        self.assertNotEqual(h1, h2)

    def test_v2_deployment_combined_hash_initialized(self):
        self.assertIsInstance(_V2_DEPLOYMENT_COMBINED_HASH, str)


class TestModalRuntimeSpec(unittest.TestCase):
    """ModalRuntimeSpec carries correct default values."""

    def test_default_gpu_is_tuple_with_single_entry(self):
        spec = ModalRuntimeSpec()
        self.assertIsInstance(spec.gpu, tuple)
        self.assertEqual(len(spec.gpu), 1)
        self.assertEqual(spec.gpu[0], "RTX-PRO-6000")

    def test_default_cpu(self):
        spec = ModalRuntimeSpec()
        self.assertEqual(spec.cpu, 4)

    def test_default_min_containers(self):
        spec = ModalRuntimeSpec()
        self.assertEqual(spec.min_containers, 0)

    def test_default_scaledown_window(self):
        spec = ModalRuntimeSpec()
        self.assertEqual(spec.scaledown_window, 4)

    def test_default_timeout(self):
        spec = ModalRuntimeSpec()
        self.assertEqual(spec.timeout, 3600)

    def test_default_target_inputs(self):
        spec = ModalRuntimeSpec()
        self.assertEqual(spec.target_inputs, 1)

    def test_default_max_inputs(self):
        spec = ModalRuntimeSpec()
        self.assertEqual(spec.max_inputs, 1)

    def test_default_memory_snapshot_enabled(self):
        spec = ModalRuntimeSpec()
        self.assertTrue(spec.enable_memory_snapshot)

    def test_no_hard_memory_limit_in_identity(self):
        spec = ModalRuntimeSpec()
        identity = _resource_identity(spec)
        self.assertIn("memory_mb", identity)
        self.assertIsInstance(identity["memory_mb"], int)
        self.assertEqual(identity["memory_mb"], 24576)
        # Verify no memory-limit tuple is present
        for key in identity:
            self.assertFalse(
                isinstance(identity[key], tuple) and len(identity[key]) == 2,
                f"found unexpected tuple value in identity key '{key}'",
            )


if __name__ == "__main__":
    unittest.main()
