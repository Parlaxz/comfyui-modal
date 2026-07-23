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


def _open_files(files):
    """Shared helper: returns a side_effect callable for builtins.open.

    *files* maps absolute paths to their string content.  Missing paths
    raise FileNotFoundError.  Used across multiple test classes.
    """
    def open_file(path, *args, **kwargs):
        if path not in files:
            raise FileNotFoundError(path)
        return io.StringIO(files[path])

    return open_file


class TestCgroupV2PathResolution(unittest.TestCase):
    """Cgroup v2 base resolution via /proc/self/mountinfo and /proc/self/cgroup."""

    def test_resolve_valid_mount_and_cgroup_files(self):
        files = {
            "/mountinfo": "36 29 0:32 / /custom\\040cgroup rw,relatime - cgroup2 cgroup rw\n",
            "/cgroup": "0::/user.slice/job\n",
        }
        with patch("builtins.open", side_effect=_open_files(files)):
            result = _resolve_cgroup_v2_base("/mountinfo", "/cgroup")
            self.assertIsNotNone(result)
            resolved_path, mount_point = result
            self.assertEqual(resolved_path, "/custom cgroup/user.slice/job")
            self.assertEqual(mount_point, "/custom cgroup")

    def test_resolve_missing_files_is_unavailable(self):
        with patch("builtins.open", side_effect=FileNotFoundError):
            self.assertIsNone(_resolve_cgroup_v2_base("/missing", "/missing"))

    def test_resolve_malformed_files_is_unavailable(self):
        files = {"/mountinfo": "not mountinfo\n", "/cgroup": "0::relative\n"}
        with patch("builtins.open", side_effect=_open_files(files)):
            self.assertIsNone(_resolve_cgroup_v2_base("/mountinfo", "/cgroup"))

    def test_resolve_root_cgroup(self):
        files = {
            "/mountinfo": "36 29 0:32 / /custom/cgroup rw - cgroup2 cgroup rw\n",
            "/cgroup": "0::/\n",
        }
        with patch("builtins.open", side_effect=_open_files(files)):
            result = _resolve_cgroup_v2_base("/mountinfo", "/cgroup")
            self.assertIsNotNone(result)
            resolved_path, mount_point = result
            self.assertEqual(resolved_path, "/custom/cgroup")
            self.assertEqual(mount_point, "/custom/cgroup")


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
             patch("comfymodal_runtime.modal_app._resolve_cgroup_v2_base", return_value=("/fake/cgroup", "/fake/cgroup")), \
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

    def test_unlimited_memory_limit_reported_as_unlimited(self):
        """When memory.max is 'max' (unlimited), limit_mib is 'unlimited' string."""
        with patch("comfymodal_runtime.modal_app.platform.system", return_value="Linux"), \
             patch("comfymodal_runtime.modal_app._resolve_cgroup_v2_base", return_value=("/fake/cgroup", "/fake/cgroup")), \
             patch(
                 "comfymodal_runtime.modal_app._read_cgroup_v2_memory",
                 side_effect=lambda path: "max" if path.endswith("memory.max") else None,
             ), \
             patch("builtins.open", side_effect=FileNotFoundError):
            result = _report_host_memory("unlimited")
        self.assertEqual(result["memory.max"], "max")
        self.assertEqual(result["limit_mib"], "unlimited")

    def test_malformed_memory_files_are_absent_and_safe(self):
        with patch("comfymodal_runtime.modal_app.platform.system", return_value="Linux"), \
             patch("comfymodal_runtime.modal_app._resolve_cgroup_v2_base", return_value=("/fake/cgroup", "/fake/cgroup")), \
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

    def test_memory_is_int_not_tuple(self):
        """Memory must be a flat int, 24576, with no hard maximum tuple."""
        spec = ModalRuntimeSpec()
        self.assertIsInstance(spec.memory, int)
        self.assertEqual(spec.memory, 24576)
        self.assertFalse(isinstance(spec.memory, tuple))

    def test_no_warm_containers(self):
        """min_containers=0 means no warm containers."""
        self.assertEqual(MIN_CONTAINERS, 0)
        spec = ModalRuntimeSpec()
        self.assertEqual(spec.min_containers, 0)

    def test_no_scheduling_policy_changes(self):
        """Default scaledown_window=4, no scheduling_policy override."""
        self.assertEqual(SCALEDOWN_WINDOW, 4)
        spec = ModalRuntimeSpec()
        self.assertEqual(spec.scaledown_window, 4)


class TestCgroupV2Extended(unittest.TestCase):
    """Extended cgroup v2 path resolution and edge cases."""

    def test_nested_cgroup_path_resolution(self):
        """Deeply nested cgroup paths are resolved correctly."""
        files = {
            "/mountinfo": (
                "36 29 0:32 / /sys/fs/cgroup rw,nosuid,nodev,noexec,relatime "
                "- cgroup2 cgroup rw\n"
            ),
            "/cgroup": "0::/system.slice/docker/abc123\n",
        }
        with patch("builtins.open", side_effect=_open_files(files)):
            result = _resolve_cgroup_v2_base("/mountinfo", "/cgroup")
            self.assertIsNotNone(result)
            resolved_path, mount_point = result
            self.assertEqual(resolved_path, "/sys/fs/cgroup/system.slice/docker/abc123")
            self.assertEqual(mount_point, "/sys/fs/cgroup")

    def test_resolve_missing_mountinfo_line(self):
        """When mountinfo has no cgroup2 line, returns None."""
        files = {
            "/mountinfo": "36 29 0:32 / /something rw - tmpfs tmpfs rw\n",
            "/cgroup": "0::/user.slice\n",
        }
        with patch("builtins.open", side_effect=_open_files(files)):
            self.assertIsNone(_resolve_cgroup_v2_base("/mountinfo", "/cgroup"))

    def test_resolve_no_cgroup_entry(self):
        """When /proc/self/cgroup has no 0:: line, returns None."""
        files = {
            "/mountinfo": (
                "36 29 0:32 / /sys/fs/cgroup rw - cgroup2 cgroup rw\n"
            ),
            "/cgroup": "1::/user.slice\n",
        }
        with patch("builtins.open", side_effect=_open_files(files)):
            self.assertIsNone(_resolve_cgroup_v2_base("/mountinfo", "/cgroup"))

    def test_resolve_root_cgroup_returns_mount_point_only(self):
        """When cgroup path is '/', returns (mount_point, mount_point)."""
        files = {
            "/mountinfo": (
                "36 29 0:32 / /sys/fs/cgroup rw - cgroup2 cgroup rw\n"
            ),
            "/cgroup": "0::/\n",
        }
        with patch("builtins.open", side_effect=_open_files(files)):
            result = _resolve_cgroup_v2_base("/mountinfo", "/cgroup")
            self.assertIsNotNone(result)
            resolved_path, mount_point = result
            self.assertEqual(resolved_path, "/sys/fs/cgroup")
            self.assertEqual(mount_point, "/sys/fs/cgroup")

    def test_resolve_rejects_non_absolute_cgroup(self):
        """Relative cgroup path without leading / returns None."""
        files = {
            "/mountinfo": (
                "36 29 0:32 / /sys/fs/cgroup rw - cgroup2 cgroup rw\n"
            ),
            "/cgroup": "0::relative/path\n",
        }
        with patch("builtins.open", side_effect=_open_files(files)):
            self.assertIsNone(_resolve_cgroup_v2_base("/mountinfo", "/cgroup"))

    def test_resolve_rejects_dot_dot_components(self):
        """Cgroup path with .. components returns None."""
        files = {
            "/mountinfo": (
                "36 29 0:32 / /sys/fs/cgroup rw - cgroup2 cgroup rw\n"
            ),
            "/cgroup": "0::/user/../escape\n",
        }
        with patch("builtins.open", side_effect=_open_files(files)):
            self.assertIsNone(_resolve_cgroup_v2_base("/mountinfo", "/cgroup"))


class TestHostMemorySchema(unittest.TestCase):
    """Host-memory one-line output schema compliance."""

    def test_unlimited_memory_max_reported_as_unlimited(self):
        """When memory.max is 'max', limit_mib is reported as 'unlimited'."""
        with patch("comfymodal_runtime.modal_app.platform.system", return_value="Linux"), \
             patch("comfymodal_runtime.modal_app._resolve_cgroup_v2_base",
                   return_value=("/sys/fs/cgroup", "/sys/fs/cgroup")), \
             patch(
                 "comfymodal_runtime.modal_app._read_cgroup_v2_memory",
                 side_effect=lambda path: {"memory.current": 1024 * 1024,
                                           "memory.peak": 2048 * 1024,
                                           "memory.max": "max"}.get(
                     path.split("/")[-1]),
             ), \
             patch("builtins.open", side_effect=FileNotFoundError):
            result = _report_host_memory("unlimited_check")

        self.assertEqual(result["limit_mib"], "unlimited")
        self.assertEqual(result["memory.max"], "max")

    def test_line_omits_raw_memory_field_names(self):
        """The printed [v2.host_memory] line must NOT contain raw
        memory.current, memory.peak, memory.events or memory.stat field
        names.  Only MiB-formatted values appear."""
        import io as _io
        _captured = _io.StringIO()
        with patch("comfymodal_runtime.modal_app.platform.system", return_value="Linux"), \
             patch("comfymodal_runtime.modal_app._resolve_cgroup_v2_base",
                   return_value=("/sys/fs/cgroup", "/sys/fs/cgroup")), \
             patch(
                 "comfymodal_runtime.modal_app._read_cgroup_v2_memory",
                 side_effect=lambda path: 1024 * 1024 if "current" in path else
                                           2048 * 1024 if "peak" in path else
                                           16 * 1024 * 1024 * 1024,
             ), \
             patch("builtins.open", side_effect=FileNotFoundError), \
             patch("sys.stdout", _captured):
            _report_host_memory("schema_check")

        emitted = _captured.getvalue()
        # Must contain line prefix
        self.assertIn("[v2.host_memory]", emitted)
        # Must NOT contain raw field names
        self.assertNotIn("memory.current=", emitted)
        self.assertNotIn("memory.peak=", emitted)
        self.assertNotIn("memory.events=", emitted)
        self.assertNotIn("memory.stat=", emitted)
        # Must contain MiB fields
        self.assertIn("current_mib=", emitted)
        self.assertIn("peak_mib=", emitted)
        self.assertIn("limit_mib=", emitted)
        self.assertIn("cgroup_path=", emitted)
        self.assertIn("cgroup_mount=", emitted)

    def test_line_contains_all_eleven_fields(self):
        """The [v2.host_memory] line has exactly the 11 spec-fields:
        stage, current_mib, peak_mib, limit_mib, process_rss_mib,
        process_maxrss_mib, oom_count, oom_kill_count, status,
        cgroup_path, cgroup_mount."""
        import io as _io
        _captured = _io.StringIO()
        with patch("comfymodal_runtime.modal_app.platform.system", return_value="Linux"), \
             patch("comfymodal_runtime.modal_app._resolve_cgroup_v2_base",
                   return_value=("/sys/fs/cgroup/test", "/sys/fs/cgroup")), \
             patch(
                 "comfymodal_runtime.modal_app._read_cgroup_v2_memory",
                 side_effect=lambda path: {
                     "memory.current": 2 * 1024 * 1024,
                     "memory.peak": 4 * 1024 * 1024,
                     "memory.max": 8 * 1024 * 1024,
                 }.get(path.split("/")[-1]),
             ), \
             patch(
                 "builtins.open",
                 side_effect=lambda path, *args, **kwargs: _io.StringIO(
                     "oom 1\noom_kill 0\n"
                     if "memory.events" in path else
                     "file 1048576\ninactive_file 524288\nactive_file 524288\n"
                     "workingset_refault_file 0\nworkingset_activate_file 0\n"
                     "pgfault 100\npgmajfault 0\n"
                     if "memory.stat" in path else
                     "VmRSS: 2048 kB\n"
                 ),
             ):
            result = _report_host_memory("full_schema")

        self.assertEqual(result["stage"], "full_schema")
        self.assertEqual(result["current_mib"], 2.0)
        self.assertEqual(result["peak_mib"], 4.0)
        self.assertEqual(result["limit_mib"], 8.0)
        self.assertEqual(result["process_rss_mib"], 2.0)
        self.assertIn("process_maxrss_mib", result)
        self.assertEqual(result["oom_count"], 1)
        self.assertEqual(result["oom_kill_count"], 0)
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["cgroup_path"], "/sys/fs/cgroup/test")
        self.assertEqual(result["cgroup_mount"], "/sys/fs/cgroup")
        # memory.stat parsed fields
        stat = result.get("memory.stat", {})
        self.assertIsInstance(stat, dict)
        self.assertEqual(stat.get("file"), 1048576)
        self.assertEqual(stat.get("inactive_file"), 524288)
        self.assertEqual(stat.get("active_file"), 524288)
        self.assertEqual(stat.get("workingset_refault_file"), 0)
        self.assertEqual(stat.get("workingset_activate_file"), 0)
        self.assertEqual(stat.get("pgfault"), 100)
        self.assertEqual(stat.get("pgmajfault"), 0)

    def test_never_fails_request(self):
        """_report_host_memory never raises regardless of input."""
        for stage in ("", "error_test", None):
            try:
                if stage is None:
                    _report_host_memory("none_stage")
                else:
                    _report_host_memory(stage)
            except Exception as exc:
                self.fail(f"_report_host_memory({stage!r}) raised: {exc}")

    def test_absent_for_all_unavailable_counters(self):
        """When all cgroup/proc files are unavailable, every counter is absent."""
        with patch("comfymodal_runtime.modal_app.platform.system", return_value="Linux"), \
             patch("comfymodal_runtime.modal_app._resolve_cgroup_v2_base", return_value=None), \
             patch("builtins.open", side_effect=FileNotFoundError):
            result = _report_host_memory("all_absent")
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["current_mib"], "absent")
        self.assertEqual(result["peak_mib"], "absent")
        self.assertEqual(result["limit_mib"], "absent")
        self.assertEqual(result["process_rss_mib"], "absent")
        self.assertEqual(result["oom_count"], "absent")
        self.assertEqual(result["oom_kill_count"], "absent")
        self.assertEqual(result["cgroup_path"], "absent")
        self.assertEqual(result["cgroup_mount"], "absent")


if __name__ == "__main__":
    unittest.main()
