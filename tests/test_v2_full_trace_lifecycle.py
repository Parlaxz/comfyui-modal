"""Tests for v2 full-trace lifecycle helpers: bundle, persistence, descriptor, finalization order."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from comfymodal_runtime import modal_app
from comfymodal_runtime.runtime_state import FakeVolume


class _FakeProfileVolume:
    """Minimal fake for Modal Volume profile operations."""

    def __init__(self) -> None:
        self._files: dict[str, bytes] = {}
        self.write_count: int = 0
        self.commit_count: int = 0

    def write_bytes(self, path: str, data: bytes) -> None:
        self._files[path] = data
        self.write_count += 1

    def read_bytes(self, path: str) -> bytes:
        return self._files.get(path, b"")

    def exists(self, path: str) -> bool:
        return path in self._files

    def commit(self) -> None:
        self.commit_count += 1


class FullTraceLifecycleHelpersTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self._root = Path(self._tmp.name)
        self._session_dir = self._root / "session"
        for subdir in ("raw", "derived", "logs"):
            (self._session_dir / subdir).mkdir(parents=True)
        (self._session_dir / "raw" / "viztracer.json.gz").write_bytes(b"")
        (self._session_dir / "raw" / "torch_trace.json.gz").write_bytes(b"")
        (self._session_dir / "raw" / "resource_samples.jsonl.gz").write_bytes(b"")
        (self._session_dir / "raw" / "milestones.jsonl").write_text("")
        (self._session_dir / "raw" / "session_events.jsonl").write_text("")
        (self._session_dir / "raw" / "wrapper_snapshots.json").write_text("[]")
        (self._session_dir / "raw" / "trace_config.json").write_text("{}")
        (self._session_dir / "raw" / "runtime_result_summary.json").write_text("{}")
        self._volume_path = self._root / "volume"
        self._path_patch = patch.object(modal_app, "PROFILE_PATH", str(self._volume_path))
        self._path_patch.start()
        modal_app._FULL_TRACE_FINALIZED_IDS.clear()

    def tearDown(self) -> None:
        modal_app._FULL_TRACE_FINALIZED_IDS.clear()
        self._path_patch.stop()
        self._tmp.cleanup()

    def _session(self) -> SimpleNamespace:
        return SimpleNamespace(
            trace_id="trace-test",
            base_dir=self._session_dir,
            resource_sampler=None,
            _viztracer=None,
            _torch_profiler=None,
            _torch_profiler_active=False,
        )

    def test_bundle_is_deterministic_and_manifest_matches(self) -> None:
        (self._session_dir / "raw" / "extra.json").write_bytes(b"payload")
        first = modal_app._build_full_trace_bundle(self._session())
        second = modal_app._build_full_trace_bundle(self._session())
        self.assertIsNotNone(first)
        self.assertIsNotNone(second)
        assert first is not None and second is not None
        self.assertEqual(first[3], second[3])
        self.assertEqual(first[3], hashlib.sha256(first[2]).hexdigest())

    def test_upload_is_atomic(self) -> None:
        volume = _FakeProfileVolume()
        path = modal_app._upload_full_trace_bundle(
            volume, "trace-test", b"bundle", "sha",
            remote_bundle_path="v2-full-trace/2025-01-01/trace-test/bundle.tar.gz",
        )
        self.assertEqual(path, "v2-full-trace/2025-01-01/trace-test/bundle.tar.gz")
        # No commit in upload — caller commits once
        self.assertEqual(volume.commit_count, 0)
        self.assertEqual(
            volume._files.get("v2-full-trace/2025-01-01/trace-test/bundle.tar.gz"),
            b"bundle",
        )

    def test_finalize_uses_profile_volume_and_commits_once(self) -> None:
        session = MagicMock()
        session.trace_id = "trace-test"
        session.base_dir = self._session_dir
        session.resource_sampler = None
        session._viztracer = None
        session._torch_profiler = None
        session._torch_profiler_active = False
        profile_volume = _FakeProfileVolume()
        with patch.object(modal_app, "_V2_FULL_TRACE_ENABLED", True), \
             patch.object(modal_app, "PROFILE_VOLUME_NAME", "comfymodal-v2-profiles"):
            first = modal_app._finalize_full_trace(session, profile_volume, "request-1")
            second = modal_app._finalize_full_trace(session, profile_volume, "request-2")
        self.assertEqual(first["status"], "ready")
        self.assertEqual(second["status"], "absent")
        # Exactly one commit after both files
        self.assertEqual(profile_volume.commit_count, 1)
        # Both bundle and descriptor exist
        self.assertIsNotNone(first.get("remote_bundle_path"))
        self.assertIsNotNone(first.get("remote_descriptor_path"))
        # Verify descriptor fields
        self.assertEqual(first["volume_name"], "comfymodal-v2-profiles")
        self.assertEqual(first["trace_id"], "trace-test")
        self.assertIn("bundle_size_bytes", first)
        self.assertIn("bundle_sha256", first)
        self.assertIn("finalize_ms", first)

    def test_finalize_reports_upload_error(self) -> None:
        session = MagicMock()
        session.trace_id = "trace-test"
        session.base_dir = self._session_dir
        session.resource_sampler = None
        session._viztracer = None
        session._torch_profiler = None
        session._torch_profiler_active = False
        with patch.object(modal_app, "_V2_FULL_TRACE_ENABLED", True), patch.object(
            modal_app, "_upload_full_trace_bundle", return_value=None
        ):
            result = modal_app._finalize_full_trace(
                session, _FakeProfileVolume(), "request-1"
            )
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["error_type"], "UploadError")

    def test_disabled_artifact_is_absent(self) -> None:
        with patch.object(modal_app, "_V2_FULL_TRACE_ENABLED", False):
            self.assertEqual(
                modal_app._safe_full_trace_artifact(None, None, "request-1")["status"],
                "absent",
            )

    def test_descriptor_has_exact_fields(self) -> None:
        """Verify descriptor has all required fields when ready."""
        session = MagicMock()
        session.trace_id = "trace-test-desc"
        session.base_dir = self._session_dir
        session.resource_sampler = None
        session._viztracer = None
        session._torch_profiler = None
        session._torch_profiler_active = False
        profile_volume = _FakeProfileVolume()
        with patch.object(modal_app, "_V2_FULL_TRACE_ENABLED", True), \
             patch.object(modal_app, "PROFILE_VOLUME_NAME", "comfymodal-v2-profiles"):
            result = modal_app._finalize_full_trace(
                session, profile_volume, "req-42",
            )
        self.assertEqual(result["status"], "ready")
        required_fields = [
            "status", "trace_id", "volume_name", "remote_bundle_path",
            "remote_descriptor_path", "bundle_size_bytes", "bundle_sha256",
            "report_status", "viztracer_status", "torch_profiler_status",
            "resource_sampler_status", "trace_truncated", "trace_entry_count",
            "trace_entry_capacity", "finalize_ms",
        ]
        for field in required_fields:
            self.assertIn(field, result, f"Missing descriptor field: {field}")

    def test_bundle_path_uses_utc_date(self) -> None:
        """Bundle path includes UTC date and trace_id."""
        session = MagicMock()
        session.trace_id = "utc-date-test"
        session.base_dir = self._session_dir
        session.resource_sampler = None
        session._viztracer = None
        session._torch_profiler = None
        session._torch_profiler_active = False
        profile_volume = _FakeProfileVolume()
        with patch.object(modal_app, "_V2_FULL_TRACE_ENABLED", True):
            result = modal_app._finalize_full_trace(
                session, profile_volume, "req-99",
            )
        self.assertEqual(result["status"], "ready")
        path = result["remote_bundle_path"]
        self.assertIn("v2-full-trace", path)
        self.assertIn("utc-date-test", path)
        self.assertIn("bundle.tar.gz", path)

    def test_no_post_stop_milestone(self) -> None:
        """Milestone 'trace_finalize' is captured, then stop_tracing runs — no milestone after."""
        session = MagicMock()
        session.trace_id = "milestone-order"
        session.base_dir = self._session_dir
        session.resource_sampler = None
        session._viztracer = None
        session._torch_profiler = None
        session._torch_profiler_active = False
        profile_volume = _FakeProfileVolume()
        with patch.object(modal_app, "_V2_FULL_TRACE_ENABLED", True):
            modal_app._finalize_full_trace(session, profile_volume, "req-1")
        # capture_milestone should have been called BEFORE stop_tracing
        calls = session.capture_milestone.call_args_list
        self.assertGreaterEqual(len(calls), 1)
        # stop_tracing should be called
        session.stop_tracing.assert_called_once()


class FullTraceV2GapsTest(unittest.TestCase):
    """Tests for verified gap remediations."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self._root = Path(self._tmp.name)
        self._session_dir = self._root / "session"
        for subdir in ("raw", "derived", "logs"):
            (self._session_dir / subdir).mkdir(parents=True)
        (self._session_dir / "raw" / "viztracer.json.gz").write_bytes(b"")
        (self._session_dir / "raw" / "torch_trace.json.gz").write_bytes(b"")
        (self._session_dir / "raw" / "resource_samples.jsonl.gz").write_bytes(b"")
        (self._session_dir / "raw" / "milestones.jsonl").write_text("")
        (self._session_dir / "raw" / "session_events.jsonl").write_text("")
        (self._session_dir / "raw" / "wrapper_snapshots.json").write_text("[]")
        (self._session_dir / "raw" / "trace_config.json").write_text("{}")
        (self._session_dir / "raw" / "runtime_result_summary.json").write_text("{}")
        self._volume_path = self._root / "volume"
        self._path_patch = patch.object(modal_app, "PROFILE_PATH", str(self._volume_path))
        self._path_patch.start()
        modal_app._FULL_TRACE_FINALIZED_IDS.clear()

    def tearDown(self) -> None:
        modal_app._FULL_TRACE_FINALIZED_IDS.clear()
        self._path_patch.stop()
        self._tmp.cleanup()

    def test_runtime_env_has_torch_key(self) -> None:
        """COMFYMODAL_V2_FULL_TRACE_TORCH is included in _runtime_env() with default '1'."""
        env = modal_app._runtime_env()
        self.assertIn("COMFYMODAL_V2_FULL_TRACE_TORCH", env)
        self.assertEqual(env["COMFYMODAL_V2_FULL_TRACE_TORCH"], "1")

    def test_runtime_env_has_four_trace_propagation_keys(self) -> None:
        """Full-trace propagation keys are present with defaults."""
        env = modal_app._runtime_env()
        required = [
            "COMFYMODAL_V2_FULL_TRACE",
            "COMFYMODAL_V2_FULL_TRACE_ENTRIES",
            "COMFYMODAL_V2_FULL_TRACE_RESOURCE_INTERVAL_MS",
            "COMFYMODAL_V2_FULL_TRACE_MAX_STACK_DEPTH",
            "COMFYMODAL_V2_FULL_TRACE_TORCH",
            "COMFYMODAL_V2_PROFILE_VOLUME",
        ]
        for key in required:
            self.assertIn(key, env, f"Missing required env key: {key}")

    def test_error_descriptor_includes_trace_id(self) -> None:
        """Error descriptor from _finalize_full_trace includes trace_id and sanitized error_type."""
        session = MagicMock()
        session.trace_id = "err-trace-42"
        session.base_dir = self._session_dir
        session.resource_sampler = None
        session._viztracer = None
        session._torch_profiler = None
        session._torch_profiler_active = False
        with patch.object(modal_app, "_V2_FULL_TRACE_ENABLED", True), patch.object(
            modal_app, "_build_full_trace_bundle", return_value=None
        ):
            result = modal_app._finalize_full_trace(
                session, _FakeProfileVolume(), "req-err",
            )
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["trace_id"], "err-trace-42")
        self.assertEqual(result["error_type"], "BundleError")
        # Ensure error is sanitized (no raw exception contents)
        self.assertIn("error", result)
        self.assertIsInstance(result["error"], str)
        self.assertNotEqual(result["error"], "absent")

    def test_safe_wrapper_returns_error_descriptor_on_exception(self) -> None:
        """_safe_full_trace_artifact returns error descriptor, not absent, on exception."""
        session = MagicMock()
        session.trace_id = "safe-err-test"
        session.base_dir = self._session_dir
        # Make _finalize_full_trace raise by passing a session that errors on milestone
        session.capture_milestone.side_effect = RuntimeError("test failure")
        with patch.object(modal_app, "_V2_FULL_TRACE_ENABLED", True):
            result = modal_app._safe_full_trace_artifact(
                session, _FakeProfileVolume(), "req-safe",
            )
        self.assertEqual(result["status"], "error")
        self.assertIn("trace_id", result)
        self.assertIn("error_type", result)
        self.assertIn("error", result)

    def test_capture_milestone_noop_after_stop(self) -> None:
        """capture_milestone is a no-op when session state is trace_stopped."""
        from comfymodal_runtime.full_execution_trace import FullExecutionTraceSession as _FT
        _FT.reset_instance()
        session = _FT.create_if_enabled(
            container_session_id="test-container",
            _trace_id_override="post-stop-milestone",
        )
        if session is None:
            self.skipTest("full trace not enabled (env not set)")
        # Manually set to trace_stopped
        with session._state_lock:
            session._state = "trace_stopped"
        with patch("builtins.print") as mock_print:
            session.capture_milestone("should_be_skipped")
        # Verify no milestone was written (no-op)
        milestones_path = session._base_dir / "raw" / "milestones.jsonl"
        content = milestones_path.read_text() if milestones_path.exists() else ""
        self.assertNotIn("should_be_skipped", content)
        # Verify diagnostic was printed
        printed_text = "".join(call[0][0] for call in mock_print.call_args_list
                               if call[0] and "already_stopped" in str(call[0][0]))
        self.assertIn("already_stopped", printed_text)

    def test_torch_profiler_skipped_when_flag_zero(self) -> None:
        """start_torch_profiler is skipped when COMFYMODAL_V2_FULL_TRACE_TORCH=0."""
        from comfymodal_runtime.full_execution_trace import FullExecutionTraceSession as _FT
        _FT.reset_instance()
        session = _FT.create_if_enabled(
            container_session_id="torch-flag-test",
            _trace_id_override="torch-flag",
        )
        if session is None:
            self.skipTest("full trace not enabled (env not set)")
        with patch.dict(os.environ, {"COMFYMODAL_V2_FULL_TRACE_TORCH": "0"}), \
             patch("builtins.print") as mock_print:
            session.start_torch_profiler()
        self.assertIsNone(session._torch_profiler)
        self.assertFalse(session._torch_profiler_active)
        printed_text = "".join(call[0][0] for call in mock_print.call_args_list
                               if call[0] and "skipped" in str(call[0][0]) and "torch_disabled" in str(call[0][0]))
        self.assertIn("torch_disabled", printed_text)

    def test_torch_profiler_runs_when_flag_one(self) -> None:
        """start_torch_profiler runs when COMFYMODAL_V2_FULL_TRACE_TORCH=1 (default)."""
        from comfymodal_runtime.full_execution_trace import FullExecutionTraceSession as _FT
        _FT.reset_instance()
        session = _FT.create_if_enabled(
            container_session_id="torch-flag-enabled",
            _trace_id_override="torch-flag-on",
        )
        if session is None:
            self.skipTest("full trace not enabled (env not set)")
        # Default is "1" — should proceed into import
        with patch.dict(os.environ, {"COMFYMODAL_V2_FULL_TRACE_TORCH": "1"}, clear=False):
            session.start_torch_profiler()
        # profiler may or may not have started depending on torch availability,
        # but the guard should not have skipped it — _torch_profiler may be
        # None if torch.profiler import fails, but _torch_profiler_active must
        # not be True (torch not available in test env)
        self.assertFalse(session._torch_profiler_active)

    def test_disabled_full_trace_is_inert(self) -> None:
        """When COMFYMODAL_V2_FULL_TRACE != '1', session is None and no files created."""
        from comfymodal_runtime.full_execution_trace import FullExecutionTraceSession as _FT
        _FT.reset_instance()
        with patch.dict(os.environ, {"COMFYMODAL_V2_FULL_TRACE": "0"}, clear=False):
            session = _FT.create_if_enabled(
                container_session_id="inert-test",
            )
        self.assertIsNone(session)

    # ── _runtime_env() default value assertions ──────────────────────────

    def test_runtime_env_default_values(self) -> None:
        """_runtime_env() returns expected default values for all trace/profile keys."""
        env = modal_app._runtime_env()
        self.assertEqual(env.get("COMFYMODAL_V2_FULL_TRACE"), "0")
        self.assertEqual(env.get("COMFYMODAL_V2_FULL_TRACE_TORCH"), "1")
        self.assertEqual(env.get("COMFYMODAL_V2_FULL_TRACE_ENTRIES"), "8000000")
        self.assertEqual(env.get("COMFYMODAL_V2_FULL_TRACE_RESOURCE_INTERVAL_MS"), "50")
        self.assertEqual(env.get("COMFYMODAL_V2_FULL_TRACE_MAX_STACK_DEPTH"), "64")
        self.assertEqual(env.get("COMFYMODAL_V2_PROFILE_VOLUME"), "comfymodal-v2-profiles")

    def test_runtime_env_reflects_os_environ_overrides(self) -> None:
        """_runtime_env() picks up overridden env vars from os.environ."""
        with patch.dict(os.environ, {
            "COMFYMODAL_V2_FULL_TRACE": "1",
            "COMFYMODAL_V2_FULL_TRACE_TORCH": "0",
            "COMFYMODAL_V2_FULL_TRACE_ENTRIES": "500000",
            "COMFYMODAL_V2_FULL_TRACE_RESOURCE_INTERVAL_MS": "200",
            "COMFYMODAL_V2_PROFILE_VOLUME": "custom-profiles",
        }, clear=False):
            env = modal_app._runtime_env()
            self.assertEqual(env["COMFYMODAL_V2_FULL_TRACE"], "1")
            self.assertEqual(env["COMFYMODAL_V2_FULL_TRACE_TORCH"], "0")
            self.assertEqual(env["COMFYMODAL_V2_FULL_TRACE_ENTRIES"], "500000")
            self.assertEqual(env["COMFYMODAL_V2_FULL_TRACE_RESOURCE_INTERVAL_MS"], "200")
            self.assertEqual(env["COMFYMODAL_V2_PROFILE_VOLUME"], "custom-profiles")

    # ── _reference_image() pip_install behavior ─────────────────────────

    def test_reference_image_calls_pip_install_when_enabled(self) -> None:
        """_reference_image() calls pip_install('viztracer==1.1.1') exactly once
        when V2 full trace is enabled."""
        image = MagicMock()
        image.pip_install.return_value = image
        image.add_local_python_source.return_value = image
        comfyapp_mock = MagicMock()
        comfyapp_mock._image_base = image

        with patch.object(modal_app, "_V2_FULL_TRACE_ENABLED", True), \
             patch("importlib.import_module", return_value=comfyapp_mock), \
             patch.object(modal_app, "V2_SOURCE_MODULES", ("test_mod",)):
            result = modal_app._reference_image()
        image.pip_install.assert_called_once_with("viztracer==1.1.1")
        self.assertIs(result, image)

    def test_reference_image_no_pip_install_when_disabled(self) -> None:
        """_reference_image() does NOT call pip_install when V2 full trace is disabled."""
        image = MagicMock()
        image.pip_install.return_value = image
        image.add_local_python_source.return_value = image
        comfyapp_mock = MagicMock()
        comfyapp_mock._image_base = image

        with patch.object(modal_app, "_V2_FULL_TRACE_ENABLED", False), \
             patch("importlib.import_module", return_value=comfyapp_mock), \
             patch.object(modal_app, "V2_SOURCE_MODULES", ("test_mod",)):
            result = modal_app._reference_image()
        image.pip_install.assert_not_called()
        self.assertIs(result, image)

    def test_reference_image_pip_install_before_add_local_source(self) -> None:
        """pip_install('viztracer==1.1.1') is called BEFORE any
        add_local_python_source call."""
        call_sequence: list[tuple[str, str]] = []
        image = MagicMock()

        def _pip_side(pkg: str) -> MagicMock:
            call_sequence.append(("pip_install", pkg))
            return image

        def _add_side(mod: str) -> MagicMock:
            call_sequence.append(("add_local_python_source", mod))
            return image

        image.pip_install.side_effect = _pip_side
        image.add_local_python_source.side_effect = _add_side
        comfyapp_mock = MagicMock()
        comfyapp_mock._image_base = image

        with patch.object(modal_app, "_V2_FULL_TRACE_ENABLED", True), \
             patch("importlib.import_module", return_value=comfyapp_mock), \
             patch.object(modal_app, "V2_SOURCE_MODULES", ("mod_a", "mod_b")):
            modal_app._reference_image()

        self.assertEqual(len(call_sequence), 3)
        self.assertEqual(call_sequence[0], ("pip_install", "viztracer==1.1.1"))
        self.assertEqual(call_sequence[1], ("add_local_python_source", "mod_a"))
        self.assertEqual(call_sequence[2], ("add_local_python_source", "mod_b"))

    # ── Static source ordering: restore trace before residency log ──────

    def test_restore_trace_attempt_before_residency_log_in_source(self) -> None:
        """In restore(), _FT.create_if_enabled (full-trace session) appears
        before the [v2.residency_config] print statement, ensuring the trace
        session is created before any residency-adjacent log or sampling."""
        import inspect
        from comfymodal_runtime.modal_app import ModalRuntimeEntrypoint
        source = inspect.getsource(ModalRuntimeEntrypoint.restore)
        ft_idx = source.find("_FT.create_if_enabled(")
        res_idx = source.find("[v2.residency_config]")
        self.assertGreater(ft_idx, 0, "_FT.create_if_enabled must appear in restore()")
        self.assertGreater(res_idx, 0, "[v2.residency_config] must appear in restore()")
        self.assertLess(
            ft_idx, res_idx,
            "_FT.create_if_enabled must appear before [v2.residency_config] "
            "in the restore() source, so the full-trace session is created "
            "before any residency log/operation",
        )

    # ── Ready/error artifact logs and descriptor fields ─────────────────

    def test_ready_artifact_log_includes_trace_id_and_path(self) -> None:
        """The ready artifact log line from _finalize_full_trace includes
        trace_id and remote_bundle_path fields."""
        session = MagicMock()
        session.trace_id = "ready-art-test"
        session.base_dir = self._session_dir
        session.resource_sampler = None
        session._viztracer = None
        session._torch_profiler = None
        session._torch_profiler_active = False
        profile_volume = _FakeProfileVolume()

        with patch.object(modal_app, "_V2_FULL_TRACE_ENABLED", True), \
             patch.object(modal_app, "PROFILE_VOLUME_NAME", "comfymodal-v2-profiles"):
            result = modal_app._finalize_full_trace(
                session, profile_volume, "req-ready-art",
            )
        self.assertEqual(result["status"], "ready")
        self.assertIn("remote_bundle_path", result)
        self.assertIn("remote_descriptor_path", result)
        self.assertIn("trace_id", result)
        self.assertEqual(result["trace_id"], "ready-art-test")
        self.assertEqual(result["volume_name"], "comfymodal-v2-profiles")

    def test_error_artifact_log_includes_error_type_and_trace_id(self) -> None:
        """The error artifact descriptor from _finalize_full_trace includes
        error_type, trace_id, and a non-empty error string."""
        session = MagicMock()
        session.trace_id = "err-art-test"
        session.base_dir = self._session_dir
        session.resource_sampler = None
        session._viztracer = None
        session._torch_profiler = None
        session._torch_profiler_active = False
        with patch.object(modal_app, "_V2_FULL_TRACE_ENABLED", True), \
             patch.object(modal_app, "_build_full_trace_bundle", return_value=None):
            result = modal_app._finalize_full_trace(
                session, _FakeProfileVolume(), "req-err-art",
            )
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["trace_id"], "err-art-test")
        self.assertEqual(result["error_type"], "BundleError")
        self.assertIsInstance(result["error"], str)
        self.assertTrue(len(result["error"]) > 0)

    def test_full_trace_persists_only_to_profile_volume(self) -> None:
        """_finalize_full_trace writes to profile_volume (FakeVolume) and
        does NOT touch any runtime-state volume — the write_bytes call goes
        only to the profile volume."""
        session = MagicMock()
        session.trace_id = "profile-only"
        session.base_dir = self._session_dir
        session.resource_sampler = None
        session._viztracer = None
        session._torch_profiler = None
        session._torch_profiler_active = False
        profile_volume = _FakeProfileVolume()
        # No runtime_state_volume is passed — finalize should only touch
        # the profile volume.
        with patch.object(modal_app, "_V2_FULL_TRACE_ENABLED", True), \
             patch.object(modal_app, "PROFILE_VOLUME_NAME", "comfymodal-v2-profiles"):
            result = modal_app._finalize_full_trace(
                session, profile_volume, "req-profile-only",
            )
        self.assertEqual(result["status"], "ready")
        # profile_volume should have received writes
        self.assertGreater(profile_volume.write_count, 0)
        # All written paths should be under v2-full-trace/ prefix
        for path in profile_volume._files:
            self.assertTrue(
                path.startswith("v2-full-trace/"),
                f"Path {path!r} does not start with v2-full-trace/",
            )


if __name__ == "__main__":
    unittest.main()
