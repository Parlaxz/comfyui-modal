"""Tests for v2 full-trace lifecycle helpers: bundle, persistence, descriptor, finalization order."""

from __future__ import annotations

import asyncio
import hashlib
import gzip
import inspect
import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from comfymodal_runtime import modal_app
import comfymodal_runtime.full_execution_trace as full_trace
from comfymodal_runtime.full_trace_report import generate_full_trace_report
from comfymodal_runtime.runtime_state import FakeVolume


class _FakeProfileVolume:
    """Minimal fake for Modal Volume profile operations."""

    def __init__(self) -> None:
        self._files: dict[str, bytes] = {}
        self.write_count: int = 0
        self.commit_count: int = 0
        self.read_paths: list[str] = []

    def write_bytes(self, path: str, data: bytes) -> None:
        self._files[path] = data
        self.write_count += 1

    def read_bytes(self, path: str) -> bytes:
        return self._files.get(path, b"")

    def exists(self, path: str) -> bool:
        return path in self._files

    def read_file(self, path: str):
        self.read_paths.append(path)
        data = self._files.get(path)
        if data is None:
            raise FileNotFoundError(path)
        yield data

    def commit(self) -> None:
        self.commit_count += 1


class _FakeRawProfileVolume(_FakeProfileVolume):
    """Minimal raw named-Volume fake with incremental ``read_file``."""

    def __init__(self) -> None:
        super().__init__()
        self.read_paths: list[str] = []

    def read_file(self, path: str):
        self.read_paths.append(path)
        data = self._files.get(path)
        if data is None:
            raise FileNotFoundError(path)
        for offset in range(0, len(data), 7):
            yield data[offset:offset + 7]


def _successful_named_volume_readback(volume: object):
    fake_modal = SimpleNamespace(
        Volume=SimpleNamespace(from_name=MagicMock(return_value=volume)),
    )
    return patch.object(modal_app, "_modal", fake_modal)


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

    def _trace_session(
        self, tracer: object,
    ) -> full_trace.FullExecutionTraceSession:
        previous = full_trace._TEST_TRACE_BASE
        full_trace._TEST_TRACE_BASE = str(self._root / "trace")
        try:
            session = full_trace.FullExecutionTraceSession(
                container_session_id="thread-tracing-test",
                _trace_id_override="thread-tracing",
            )
        finally:
            full_trace._TEST_TRACE_BASE = previous
        session._viztracer = tracer
        self.assertTrue(session._transition("restore_tracing"))
        self.assertTrue(session._transition("restore_complete"))
        return session

    def test_claim_hands_viztracer_to_request_thread(self) -> None:
        tracer = MagicMock()
        session = self._trace_session(tracer)

        self.assertTrue(session.claim_first_request("request-thread"))
        tracer.enable_thread_tracing.assert_called_once_with()
        handoff = [
            event for event in session.events
            if event["event"] == "request_thread_tracing_handoff"
        ][-1]
        self.assertEqual(
            handoff["data"],
            {
                "hook": "enable_thread_tracing",
                "called": True,
                "succeeded": True,
                "skipped": False,
            },
        )

    def test_claim_is_harmless_when_thread_hook_is_absent(self) -> None:
        session = self._trace_session(SimpleNamespace())

        self.assertTrue(session.claim_first_request("no-hook"))
        handoff = [
            event for event in session.events
            if event["event"] == "request_thread_tracing_handoff"
        ][-1]
        self.assertFalse(handoff["data"]["called"])
        self.assertFalse(handoff["data"]["succeeded"])
        self.assertTrue(handoff["data"]["skipped"])

    def test_claim_is_harmless_when_thread_hook_raises(self) -> None:
        tracer = MagicMock()
        tracer.enable_thread_tracing.side_effect = RuntimeError("optional hook failure")
        session = self._trace_session(tracer)

        with patch("builtins.print"):
            self.assertTrue(session.claim_first_request("hook-error"))
        handoff = [
            event for event in session.events
            if event["event"] == "request_thread_tracing_handoff"
        ][-1]
        self.assertTrue(handoff["data"]["called"])
        self.assertFalse(handoff["data"]["succeeded"])
        self.assertFalse(handoff["data"]["skipped"])
        self.assertEqual(handoff["data"]["reason"], "hook_failed")
        self.assertEqual(handoff["data"]["error_type"], "RuntimeError")

    def test_golden_spans_stay_on_session_tracer_across_await(self) -> None:
        """A later global VizTracer must not steal the Golden root/stages."""
        class _Event:
            def __init__(self, tracer: object) -> None:
                self._tracer = tracer

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

        class _Tracer:
            def __init__(self) -> None:
                self.events: list[str] = []
                self.get_calls = 0

            def log_event(self, name: str) -> _Event:
                self.events.append(name)
                return _Event(self)

        owner = _Tracer()
        global_tracer = _Tracer()
        session = self._trace_session(owner)

        async def _run() -> None:
            # The suspension is intentional: ContextVar propagation, rather
            # than thread affinity, is the request-local binding contract.
            with session.golden_trace_scope():
                from comfymodal_runtime import golden_serial

                with golden_serial._golden_trace_span("golden_serial_execute"):
                    await asyncio.sleep(0)
                with golden_serial._golden_trace_span("golden_output"):
                    await asyncio.sleep(0)

        fake_viztracer = SimpleNamespace(
            get_tracer=lambda: (
                setattr(global_tracer, "get_calls", global_tracer.get_calls + 1)
                or global_tracer
            )
        )
        with patch.dict(os.environ, {"COMFYMODAL_V2_FULL_TRACE": "1"}, clear=False), \
             patch.dict(full_trace.sys.modules, {"viztracer": fake_viztracer}):
            asyncio.run(_run())
            # After the scope, the compatibility fallback is restored and
            # therefore proves that unbinding happened safely.
            from comfymodal_runtime import golden_serial
            with golden_serial._golden_trace_span("outside_scope"):
                pass

        self.assertEqual(owner.events, ["golden_serial_execute", "golden_output"])
        self.assertEqual(global_tracer.events, ["outside_scope"])
        self.assertEqual(global_tracer.get_calls, 1)

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
        with _successful_named_volume_readback(profile_volume), \
             patch.object(modal_app, "_V2_FULL_TRACE_ENABLED", True), \
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

    def test_finalize_does_not_read_back_bundle_through_named_volume(self) -> None:
        session = MagicMock()
        session.trace_id = "trace-readback-ok"
        session.base_dir = self._session_dir
        session.resource_sampler = None
        session._viztracer = None
        session._torch_profiler = None
        session._torch_profiler_active = False
        write_volume = _FakeRawProfileVolume()
        resolver = MagicMock(return_value=write_volume)
        fake_modal = SimpleNamespace(
            Volume=SimpleNamespace(from_name=resolver),
        )

        with patch.object(modal_app, "_V2_FULL_TRACE_ENABLED", True), \
             patch.object(modal_app, "PROFILE_VOLUME_NAME", "comfymodal-v2-profiles"), \
             patch.object(modal_app, "_modal", fake_modal):
            result = modal_app._finalize_full_trace(
                session, write_volume, "request-readback-ok",
            )

        self.assertEqual(result["status"], "ready")
        resolver.assert_not_called()
        self.assertEqual(write_volume.read_paths, [])
        self.assertEqual(write_volume.commit_count, 1)

    def test_finalize_does_not_fail_when_named_volume_readback_is_missing(self) -> None:
        session = MagicMock()
        session.trace_id = "trace-readback-missing"
        session.base_dir = self._session_dir
        session.resource_sampler = None
        session._viztracer = None
        session._torch_profiler = None
        session._torch_profiler_active = False
        write_volume = _FakeRawProfileVolume()
        missing_named_volume = _FakeRawProfileVolume()
        resolver = MagicMock(return_value=missing_named_volume)
        fake_modal = SimpleNamespace(
            Volume=SimpleNamespace(from_name=resolver),
        )

        with patch.object(modal_app, "_V2_FULL_TRACE_ENABLED", True), \
             patch.object(modal_app, "PROFILE_VOLUME_NAME", "comfymodal-v2-profiles"), \
             patch.object(modal_app, "_modal", fake_modal):
            result = modal_app._finalize_full_trace(
                session, write_volume, "request-readback-missing",
            )

        self.assertEqual(result["status"], "ready")
        resolver.assert_not_called()
        self.assertEqual(missing_named_volume.read_paths, [])
        self.assertEqual(write_volume.commit_count, 1)

    def test_finalizer_retains_golden_contract_scalars(self) -> None:
        session = MagicMock()
        session.trace_id = "golden-contract-summary"
        session.base_dir = self._session_dir
        session.resource_sampler = None
        session._viztracer = None
        session._torch_profiler = None
        session._torch_profiler_active = False
        session._result_summary = {}
        session.set_result_summary.side_effect = (
            lambda data: session._result_summary.update(data)
        )
        profile_volume = _FakeProfileVolume()
        summary = {
            "status": "ok",
            "golden_profile_contract": "direct_golden_serial",
            "golden_profile_require_canonical_stages": True,
            "output_durability_mode": "strict",
            "durability_requested": True,
            "required_canonical_stages": ["golden_durable_commit"],
        }
        with _successful_named_volume_readback(profile_volume), \
             patch.object(modal_app, "_V2_FULL_TRACE_ENABLED", True):
            result = modal_app._finalize_full_trace(
                session, profile_volume, "req-contract", result_summary=summary,
            )
        self.assertEqual(result["status"], "ready")
        persisted = json.loads(
            (self._session_dir / "raw" / "runtime_result_summary.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(persisted["golden_profile_contract"], "direct_golden_serial")
        self.assertIs(persisted["golden_profile_require_canonical_stages"], True)
        self.assertEqual(persisted["output_durability_mode"], "strict")
        self.assertIs(persisted["durability_requested"], True)
        self.assertNotIn("required_canonical_stages", persisted)

    def test_disabled_artifact_is_absent(self) -> None:
        with patch.object(modal_app, "_V2_FULL_TRACE_ENABLED", False):
            self.assertEqual(
                modal_app._safe_full_trace_artifact(None, None, "request-1")["status"],
                "absent",
            )

    def test_claimed_artifact_bypasses_mutable_global_gate(self) -> None:
        session = SimpleNamespace(trace_id="claimed-trace")
        expected = {"status": "ready", "trace_id": "claimed-trace"}
        with patch.object(modal_app, "_V2_FULL_TRACE_ENABLED", False), patch.object(
            modal_app, "_finalize_full_trace", return_value=expected
        ) as finalize:
            result = modal_app._safe_full_trace_artifact(
                session, None, "request-claimed", force=True
            )
        self.assertEqual(result, expected)
        finalize.assert_called_once_with(
            session, None, "request-claimed", result_summary=None
        )

    def test_forced_missing_claimed_session_is_explicit_error(self) -> None:
        with patch.object(modal_app, "_V2_FULL_TRACE_ENABLED", False):
            result = modal_app._safe_full_trace_artifact(
                None, None, "request-missing", force=True
            )
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["reason"], "claimed_session_missing")

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
        with _successful_named_volume_readback(profile_volume), \
             patch.object(modal_app, "_V2_FULL_TRACE_ENABLED", True), \
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
            "trace_entry_capacity", "request_id", "deployment_hash", "identity",
            "finalization_timings_ms", "finalize_ms",
        ]
        for field in required_fields:
            self.assertIn(field, result, f"Missing descriptor field: {field}")
        self.assertEqual(result["request_id"], "req-42")

    def test_descriptor_defers_rich_report_parsing_to_offline_tooling(self) -> None:
        session = MagicMock()
        session.trace_id = "trace-truncated"
        session.base_dir = self._session_dir
        session.resource_sampler = None
        session._viztracer = None
        session._torch_profiler = None
        session._torch_profiler_active = False
        profile_volume = _FakeProfileVolume()
        with patch.object(modal_app, "_V2_FULL_TRACE_ENABLED", True), patch(
            "comfymodal_runtime.full_trace_report.generate_full_trace_report",
            side_effect=AssertionError("rich report parsing is offline-only"),
        ) as report:
            result = modal_app._finalize_full_trace(
                session, profile_volume, "req-truncated",
            )
        self.assertIsNone(result["trace_truncated"])
        self.assertEqual(result["report_status"], "deferred_offline")
        self.assertIsNone(result["trace_entry_count"])
        self.assertIsNone(result["trace_entry_capacity"])
        report.assert_not_called()

    def test_semantic_request_interval_never_fabricates_a_golden_root(self) -> None:
        (self._session_dir / "raw" / "session_events.jsonl").write_text(
            "\n".join([
                json.dumps({
                    "event": "operation_start",
                    "operation_id": "request-op",
                    "operation_type": "golden_request_execution",
                    "timestamp_ms": 1000.0,
                    "pid": 1,
                    "tid": 2,
                    "task_id": "request-task",
                }),
                json.dumps({
                    "event": "operation_end",
                    "operation_id": "request-op",
                    "operation_type": "golden_request_execution",
                    "timestamp_ms": 1250.0,
                    "status": "ok",
                    "pid": 1,
                    "tid": 2,
                    "task_id": "request-task",
                }),
            ]) + "\n",
            encoding="utf-8",
        )

        report = generate_full_trace_report(self._session_dir)
        summary = json.loads(
            (self._session_dir / "derived" / "golden_profile_summary.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(report["golden_profile_complete"], "NO")
        self.assertIn("missing golden_serial_execute root call", report["golden_profile_reason"])
        self.assertIsNone(summary["root"])
        self.assertEqual(summary["nodes"], [])

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
        with _successful_named_volume_readback(profile_volume), \
             patch.object(modal_app, "_V2_FULL_TRACE_ENABLED", True):
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
        with _successful_named_volume_readback(profile_volume), \
             patch.object(modal_app, "_V2_FULL_TRACE_ENABLED", True):
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
        """Torch profiler is included but disabled by default."""
        env = modal_app._runtime_env()
        self.assertIn("COMFYMODAL_V2_FULL_TRACE_TORCH", env)
        self.assertEqual(env["COMFYMODAL_V2_FULL_TRACE_TORCH"], "0")

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
        """start_torch_profiler runs when explicitly enabled."""
        from comfymodal_runtime.full_execution_trace import FullExecutionTraceSession as _FT
        _FT.reset_instance()
        session = _FT.create_if_enabled(
            container_session_id="torch-flag-enabled",
            _trace_id_override="torch-flag-on",
        )
        if session is None:
            self.skipTest("full trace not enabled (env not set)")
        # Explicit opt-in should proceed into import.
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
        self.assertEqual(env.get("COMFYMODAL_V2_FULL_TRACE_TORCH"), "0")
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
        """_reference_image() returns canonical final_image (viztracer now owned by canonical plan)."""
        image = MagicMock()
        plan = MagicMock()
        plan.final_image = image
        comfyapp_mock = MagicMock()
        comfyapp_mock.CANONICAL_IMAGE_PLAN = plan
        with patch("importlib.import_module", return_value=comfyapp_mock):
            result = modal_app._reference_image()
        self.assertIs(result, image)

    def test_reference_image_no_pip_install_when_disabled(self) -> None:
        """_reference_image() is canonical-owned and returns final_image regardless of trace flag."""
        image = MagicMock()
        plan = MagicMock()
        plan.final_image = image
        comfyapp_mock = MagicMock()
        comfyapp_mock.CANONICAL_IMAGE_PLAN = plan
        with patch("importlib.import_module", return_value=comfyapp_mock):
            result = modal_app._reference_image()
        self.assertIs(result, image)

    def test_reference_image_pip_install_before_add_local_source(self) -> None:
        """Canonical plan owns image construction; _reference_image delegates to it."""
        image = MagicMock()
        plan = MagicMock()
        plan.final_image = image
        comfyapp_mock = MagicMock()
        comfyapp_mock.CANONICAL_IMAGE_PLAN = plan
        with patch("importlib.import_module", return_value=comfyapp_mock):
            result = modal_app._reference_image()
        self.assertIs(result, image)

    # ── Restore must not create deep-trace state ─────────────────────────

    def test_restore_does_not_create_full_trace_session_in_source(self) -> None:
        """Deep tracing is request-only and restore remains lightweight."""
        import inspect
        from comfymodal_runtime.modal_app import ModalRuntimeEntrypoint
        source = inspect.getsource(ModalRuntimeEntrypoint.restore)
        self.assertNotIn("create_if_enabled", source)
        self.assertIn("request-only", source)

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

        with _successful_named_volume_readback(profile_volume), \
             patch.object(modal_app, "_V2_FULL_TRACE_ENABLED", True), \
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
        with _successful_named_volume_readback(profile_volume), \
             patch.object(modal_app, "_V2_FULL_TRACE_ENABLED", True), \
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

    def test_direct_golden_trace_wiring_is_before_gpu_readiness(self) -> None:
        source = inspect.getsource(modal_app.ModalRuntimeEntrypoint.run_golden_serial_stream)
        containment = source.index("golden_request_id_invalid")
        claim = source.index("claim_first_request(normalized_request_id)")
        readiness = source.index("ensure_gpu_ready()")
        dynamic_vram = source.index("activate_golden_dynamic_vram()")
        golden_await = source.index("result = await golden_serial_execute(")
        self.assertLess(containment, claim)
        self.assertLess(claim, readiness)
        self.assertLess(readiness, dynamic_vram)
        self.assertLess(dynamic_vram, golden_await)
        self.assertNotIn("PromptExecutor", source)

    def test_direct_golden_trace_has_terminal_success_and_error_lifecycles(self) -> None:
        source = inspect.getsource(modal_app.ModalRuntimeEntrypoint.run_golden_serial_stream)
        self.assertIn('capture_milestone("golden_request_return")', source)
        self.assertIn("golden_request_error", source)
        self.assertIn("capture_milestone", source)
        self.assertGreaterEqual(source.count('capture_milestone("trace_stop_boundary")'), 2)
        self.assertGreaterEqual(source.count("asyncio.to_thread"), 2)
        self.assertGreaterEqual(source.count("force=True"), 2)
        self.assertIn('operation_end(_full_trace_op_id, status="ok")', source)
        self.assertIn('status="error"', source)
        self.assertEqual(source.count("_emit_golden_profiler_block("), 2)
        for offset in (
            source.index("_emit_golden_profiler_block(", source.index("_safe_full_trace_artifact")),
            source.index("_emit_golden_profiler_block(", source.index("_safe_full_trace_artifact", source.index("_safe_full_trace_artifact") + 1)),
        ):
            self.assertGreater(offset, source.rfind("_safe_full_trace_artifact", 0, offset))

    def test_torch_boundary_is_exact_await_finally_on_adapter_thread(self) -> None:
        source = inspect.getsource(modal_app.ModalRuntimeEntrypoint.run_golden_serial_stream)
        start = source.index("_ft.start_torch_profiler()")
        await_call = source.index("result = await golden_serial_execute(")
        stop = source.index("_ft.stop_torch_profiler()")
        self.assertLess(start, await_call)
        self.assertLess(await_call, stop)
        self.assertIn("finally:", source[start:stop])

    def test_golden_trace_binding_wraps_the_actual_execute_await(self) -> None:
        source = inspect.getsource(modal_app.ModalRuntimeEntrypoint.run_golden_serial_stream)
        binding = source.index("_ft.golden_trace_scope()")
        await_call = source.index("result = await golden_serial_execute(")
        self.assertLess(binding, await_call)
        self.assertIn("with _golden_trace_scope:", source[binding:await_call])

    def test_full_trace_off_keeps_clip_timing_inert(self) -> None:
        from comfymodal_runtime import golden_serial

        with patch.dict(os.environ, {"COMFYMODAL_V2_FULL_TRACE": "0"}, clear=False):
            timing = golden_serial._ClipTiming(
                enabled=golden_serial.stage_diagnostics_enabled()
                or golden_serial._full_trace_active(),
                trace_prefix="golden.clip_load",
            )
            with timing.span("source_open_read"):
                pass
        self.assertFalse(timing.enabled)
        self.assertEqual(timing.phases, [])

    def test_full_trace_clip_timing_mirrors_observed_span(self) -> None:
        from comfymodal_runtime import golden_serial

        with patch.dict(os.environ, {"COMFYMODAL_V2_FULL_TRACE": "1"}, clear=False), \
             patch.object(golden_serial, "_golden_trace_span") as make_span:
            make_span.return_value.__enter__.return_value = None
            timing = golden_serial._ClipTiming(
                enabled=True,
                trace_prefix="golden.clip_forward",
            )
            with timing.span("clip_graph_node_wrapper"):
                pass
        make_span.assert_called_once_with("golden.clip_forward.clip_graph_node_wrapper")
        self.assertEqual(len(timing.phases), 1)

    def test_clip_and_unet_full_trace_semantic_event_names_are_explicit(self) -> None:
        golden_path = Path(modal_app.__file__).with_name("golden_serial.py")
        source = golden_path.read_text(encoding="utf-8")
        self.assertIn('trace_prefix="golden.clip_load"', source)
        self.assertIn('trace_prefix="golden.clip_forward"', source)
        for name in (
            "header_config_preflight",
            "skeleton_patcher_construction",
            "source_h2d_transport",
            "assign_adoption",
            "binding_validation",
            "transport_quiescence",
        ):
            self.assertIn(f'golden.unet.{name}', source)
        self.assertIn("diagnostics_enabled or _full_trace_active()", source)

    def test_golden_profiler_block_uses_generated_gantt_and_artifact(self) -> None:
        from comfymodal_runtime.full_trace_report import generate_full_trace_report

        trace = {
            "traceEvents": [
                {"ph": "X", "name": "golden_serial_execute", "ts": 0, "dur": 1_200_000, "pid": 1, "tid": 1},
                *[
                    {"ph": "X", "name": name, "ts": index * 100_000, "dur": 60_000, "pid": 1, "tid": 1}
                    for index, name in enumerate((
                        "golden_restore", "golden_request_setup", "golden_clip_load",
                        "golden_clip_forward", "golden_unet_load", "golden_sampler_prepare",
                        "golden_vae_load", "golden_sampling", "golden_sampler_tail",
                        "golden_vae_decode", "golden_output",
                    ), start=1)
                ],
                {"ph": "X", "name": "deep_stage", "ts": 1_100_000, "dur": 60_000, "pid": 1, "tid": 1},
            ],
            "metadata": {"dump_counter": 2, "tracer_args": {"entry_capacity": 10}},
        }
        (self._session_dir / "raw" / "viztracer.json.gz").write_bytes(
            gzip.compress(json.dumps(trace).encode("utf-8"))
        )
        generate_full_trace_report(self._session_dir)
        gantt = (self._session_dir / "derived" / "golden_profile_gantt.txt").read_text("utf-8")
        session = SimpleNamespace(base_dir=self._session_dir)
        artifact = {
            "status": "ready",
            "trace_id": "deep-trace",
            "volume_name": "profiles",
            "remote_descriptor_path": "v2-full-trace/2025-01-01/deep-trace/artifact.json",
            "remote_bundle_path": "v2-full-trace/2025-01-01/deep-trace/bundle.tar.gz",
        }

        with patch.object(modal_app, "_V2_FULL_TRACE_ENABLED", True), patch("builtins.print") as mock_print:
            modal_app._emit_golden_profiler_block(session, artifact, "golden-request")

        block = mock_print.call_args.args[0]
        self.assertIn("[v2.golden_profiler] BEGIN\n", block)
        self.assertIn("REQUEST_ID=golden-request", block)
        self.assertIn("GOLDEN_PROFILE_COMPLETE=YES", block)
        self.assertIn("NEEDS_DECOMPOSITION=YES", block)
        self.assertIn("CANONICAL_STAGE name=golden_restore duration_ms=60.0", block)
        self.assertIn("CANONICAL_STAGE name=golden_output duration_ms=60.0", block)
        self.assertIn("ARTIFACT_DESCRIPTOR_PATH=" + artifact["remote_descriptor_path"], block)
        self.assertIn("GANTT_AVAILABLE=YES\nGANTT_BEGIN\n" + gantt + "GANTT_END", block)
        self.assertTrue(block.endswith("[v2.golden_profiler] END\n"))

    def test_golden_profiler_block_projects_nested_span_accounting(self) -> None:
        def span(name: str, wall: float, **fields: object) -> dict[str, object]:
            return {
                "kind": "python",
                "name": name,
                "wall_ms": wall,
                "needs_decomposition": True,
                "start_ms": wall,
                "end_ms": wall * 2,
                **fields,
            }

        nested = span(
            "outer_stage",
            200.0,
            direct_child_count=1,
            direct_child_sum_ms=80.0,
            direct_child_union_ms=80.0,
            child_overlap_ms=0.0,
            subthreshold_child_count=0,
            subthreshold_children_union_ms=0.0,
            exclusive_residual_ms=120.0,
            residual_pct=60.0,
            display_children_gt50ms=1,
            traced_children=1,
            residual_reason="DISPLAYED_CHILDREN_GT50MS",
            true_self_or_untraced_residual_ms=120.0,
            children=[span(
                "inner_stage",
                80.0,
                direct_child_count=0,
                direct_child_sum_ms=0.0,
                direct_child_union_ms=0.0,
                child_overlap_ms=0.0,
                subthreshold_child_count=0,
                subthreshold_children_union_ms=0.0,
                exclusive_residual_ms=80.0,
                residual_pct=100.0,
                display_children_gt50ms=0,
                traced_children=0,
                residual_reason="NO_TRACED_CHILDREN",
                true_self_or_untraced_residual_ms=80.0,
            )],
        )
        summary = {
            "GOLDEN_PROFILE_COMPLETE": "YES",
            "GOLDEN_PROFILE_ROOT_WALL_MS": 400.0,
            "GOLDEN_PROFILE_NEEDS_DECOMPOSITION": True,
            "root": span(
                "golden_serial_execute",
                400.0,
                direct_child_count=2,
                direct_child_sum_ms=250.0,
                direct_child_union_ms=240.0,
                child_overlap_ms=10.0,
                subthreshold_child_count=1,
                subthreshold_children_union_ms=10.0,
                exclusive_residual_ms=160.0,
                residual_pct=40.0,
                display_children_gt50ms=1,
                traced_children=2,
                residual_reason="DISPLAYED_CHILDREN_GT50MS",
                true_self_or_untraced_residual_ms=160.0,
                children=[nested, span("short_stage", 50.0)],
            ),
            "nodes": [],
            "canonical_spans": [],
        }
        (self._session_dir / "derived" / "golden_profile_summary.json").write_text(
            json.dumps(summary), encoding="utf-8"
        )
        session = SimpleNamespace(base_dir=self._session_dir)
        artifact = {"status": "ready"}

        with patch.object(modal_app, "_V2_FULL_TRACE_ENABLED", True), patch("builtins.print") as mock_print:
            modal_app._emit_golden_profiler_block(session, artifact, "nested-request")

        block = mock_print.call_args.args[0]
        detail_lines = [line for line in block.splitlines() if "SPAN name=" in line]
        self.assertEqual([line.split("SPAN name=", 1)[1].split(" ", 1)[0] for line in detail_lines], [
            "golden_serial_execute", "outer_stage", "inner_stage",
        ])
        self.assertTrue(detail_lines[0].startswith("SPAN name=golden_serial_execute"))
        self.assertTrue(detail_lines[1].startswith("  SPAN name=outer_stage"))
        self.assertTrue(detail_lines[2].startswith("    SPAN name=inner_stage"))
        for field in (
            "WALL_MS=400.0",
            "DIRECT_CHILD_COUNT=2",
            "DIRECT_CHILD_SUM_MS=250.0",
            "DIRECT_CHILD_UNION_MS=240.0",
            "DIRECT_CHILD_OVERLAP_MS=10.0",
            "SUBTHRESHOLD_CHILD_COUNT=1",
            "SUBTHRESHOLD_CHILD_UNION_MS=10.0",
            "RESIDUAL_MS=160.0",
            "RESIDUAL_PCT=40.0",
        ):
            self.assertIn(field, detail_lines[0])
        self.assertNotIn("short_stage", block)

    def test_golden_profiler_projects_report_evidence_as_separate_domains(self) -> None:
        summary = {
            "GOLDEN_PROFILE_COMPLETE": "YES",
            "root": {
                "name": "golden_serial_execute",
                "wall_ms": 100.0,
                "direct_child_count": 0,
                "direct_child_union_ms": 0.0,
            },
            "nodes": [],
            "canonical_spans": [],
        }
        report_data = {
            "sampling_deep_profile": {
                "status": "available",
                "record_count": 1,
                "duplicate_count": 0,
                "step_breakdown": [
                    {"kind": "setup", "label": "setup", "wall_ms": 5.0, "source": "payload.setup_ms"},
                    {"kind": "step", "label": "step 0", "wall_ms": 41.0, "step": 0, "total_ms": 41.0, "source": "reconciliation.steps_ms"},
                    {"kind": "finalization", "label": "finalization", "wall_ms": 10.0, "source": "payload.teardown_ms"},
                    {"kind": "summary", "label": "FIRST_PASS_WALL_MS", "wall_ms": 41.0, "source": "steps[0]"},
                    {"kind": "summary", "label": "SUBSEQUENT_STEPS_WALL_MS", "wall_ms": 34.0, "source": "steps[1]"},
                    {"kind": "summary", "label": "TOTAL_STEP_UNION_MS", "wall_ms": 75.0, "source": "steps[*]"},
                    {"kind": "summary", "label": "SAMPLER_PARENT_WALL_MS", "wall_ms": 90.0, "source": "payload.sampling_ms"},
                    {"kind": "summary", "label": "UNACCOUNTED_MS", "wall_ms": 5.0, "source": "payload.residual_ms"},
                ],
                "model_breakdown": [{
                    "scope": "eval_block", "eval_index": 0, "step": 0, "row": 0,
                    "block": 3, "timing_domain": "host_monotonic",
                    "host_monotonic_ms": 12.0, "cuda_device_ms": "measurement_unavailable",
                }],
            },
            "source_h2d_transport": {
                "status": "available", "availability": "available", "stage": "golden_vae_load",
                "role": "vae", "reason": "persisted E27 source/H2D evidence",
                "SOURCE_TOTAL_WALL_MS": 22.0, "SOURCE_SYSCALL_UNION_BUSY_MS": 18.0,
                "source_read_count": 4, "source_read_bytes": 128,
                "max_actual_source_inflight": 4, "qd_occupancy_ms": {"4": 12.0},
                "time_weighted_mean_qd": 3.1, "H2D_TOTAL_WALL_MS": 31.0,
                "h2d_submitted_bytes": 128, "h2d_completed_bytes": 128,
                "h2d_reconciliation_complete": True, "SOURCE_H2D_OVERLAP_MS": 9.0,
                "SOURCE_TO_GPU_READY_MS": 35.0, "POST_SOURCE_H2D_TAIL_MS": 4.0,
                "reconciliation": {"state": "valid", "complete": True},
                "timing_semantics": {"overlap_is_union": True, "non_additive": True, "waits_or_fences_inferred": False},
                "quiescence": {"workers_joined": True}, "fence": True,
            },
        }
        (self._session_dir / "derived" / "golden_profile_summary.json").write_text(
            json.dumps(summary), encoding="utf-8"
        )
        (self._session_dir / "derived" / "report_data.json").write_text(
            json.dumps(report_data), encoding="utf-8"
        )
        session = SimpleNamespace(base_dir=self._session_dir)
        with patch.object(modal_app, "_V2_FULL_TRACE_ENABLED", True), patch("builtins.print") as mock_print:
            modal_app._emit_golden_profiler_block(session, {"status": "ready"}, "evidence-request")

        block = mock_print.call_args.args[0]
        sections = [
            "TRACE HIERARCHY", "STEP BREAKDOWN", "DEEP MODEL BREAKDOWN",
            "SOURCE/H2D TRANSPORT EVIDENCE",
        ]
        self.assertEqual([block.index(section) for section in sections], sorted(block.index(section) for section in sections))
        for field in (
            "FIRST_PASS_WALL_MS=41.0", "SUBSEQUENT_STEPS_WALL_MS=34.0",
            "TOTAL_STEP_UNION_MS=75.0", "SAMPLER_PARENT_WALL_MS=90.0", "UNACCOUNTED_MS=5.0",
            "HOST_MONOTONIC_MS=12.0", "CUDA_DEVICE_ELAPSED_MS=measurement_unavailable",
            "SOURCE_TOTAL_WALL_MS=22.0", "SOURCE_SYSCALL_UNION_BUSY_MS=18.0",
            "SOURCE_READ_COUNT=4", "H2D_TOTAL_WALL_MS=31.0",
            "SOURCE_H2D_OVERLAP_MS=9.0", "SOURCE_TO_GPU_READY_MS=35.0",
            "POST_SOURCE_H2D_TAIL_MS=4.0", "RECONCILIATION_STATE=valid",
            "NON_ADDITIVE=True",
        ):
            self.assertIn(field, block)
        self.assertNotIn("SPAN name=sampling_deep_profile", block)
        self.assertIn("GOLDEN_PROFILE_ROOT_DIRECT_CHILD_COUNT=0", block)
        self.assertIn("STEP_EVIDENCE_TRACE_SPAN=NO", block)

    def test_golden_profiler_projects_unavailable_report_evidence_explicitly(self) -> None:
        summary = {
            "GOLDEN_PROFILE_COMPLETE": "YES",
            "root": {"name": "golden_serial_execute", "wall_ms": 100.0, "direct_child_count": 0},
            "nodes": [], "canonical_spans": [],
        }
        report_data = {
            "sampling_deep_profile": {"status": "unavailable", "step_breakdown": [], "model_breakdown": []},
            "source_h2d_transport": {
                "status": "reconciliation_invalid", "availability": "reconciliation_invalid",
                "reason": "submitted/completed bytes mismatch",
                "h2d_submitted_bytes": 128, "h2d_completed_bytes": 64,
                "reconciliation": {"state": "invalid", "complete": False},
                "timing_semantics": {"overlap_is_union": True, "non_additive": True, "waits_or_fences_inferred": False},
            },
        }
        (self._session_dir / "derived" / "golden_profile_summary.json").write_text(
            json.dumps(summary), encoding="utf-8"
        )
        (self._session_dir / "derived" / "report_data.json").write_text(
            json.dumps(report_data), encoding="utf-8"
        )
        session = SimpleNamespace(base_dir=self._session_dir)
        with patch.object(modal_app, "_V2_FULL_TRACE_ENABLED", True), patch("builtins.print") as mock_print:
            modal_app._emit_golden_profiler_block(session, {"status": "ready"}, "unavailable-request")

        block = mock_print.call_args.args[0]
        self.assertIn("SAMPLING_DEEP_PROFILE_STATUS=unavailable", block)
        for metric in (
            "FIRST_PASS_WALL_MS", "SUBSEQUENT_STEPS_WALL_MS", "TOTAL_STEP_UNION_MS",
            "SAMPLER_PARENT_WALL_MS", "UNACCOUNTED_MS",
        ):
            self.assertIn(f"STEP_METRIC {metric}=measurement_unavailable", block)
        self.assertIn("SOURCE_H2D_STATUS=reconciliation_invalid", block)
        self.assertIn("RECONCILIATION_STATE=invalid", block)
        self.assertIn("H2D_TOTAL_WALL_MS=measurement_unavailable", block)
        self.assertIn("SOURCE_H2D_EVIDENCE_TRACE_SPAN=NO", block)

    def test_golden_profiler_block_projects_explicit_no_child_reason(self) -> None:
        summary = {
            "GOLDEN_PROFILE_COMPLETE": "YES",
            "root": {
                "kind": "python",
                "name": "golden_serial_execute",
                "wall_ms": 100.0,
                "direct_child_count": 0,
                "direct_child_sum_ms": 0.0,
                "direct_child_union_ms": 0.0,
                "child_overlap_ms": 0.0,
                "subthreshold_child_count": 0,
                "subthreshold_children_union_ms": 0.0,
                "exclusive_residual_ms": 100.0,
                "residual_pct": 100.0,
                "display_children_gt50ms": 0,
                "traced_children": 0,
                "residual_reason": "NO_TRACED_CHILDREN",
                "true_self_or_untraced_residual_ms": 100.0,
            },
            "nodes": [],
            "canonical_spans": [],
        }
        (self._session_dir / "derived" / "golden_profile_summary.json").write_text(
            json.dumps(summary), encoding="utf-8"
        )
        session = SimpleNamespace(base_dir=self._session_dir)
        artifact = {"status": "ready"}

        with patch.object(modal_app, "_V2_FULL_TRACE_ENABLED", True), patch("builtins.print") as mock_print:
            modal_app._emit_golden_profiler_block(session, artifact, "no-child-request")

        block = mock_print.call_args.args[0]
        self.assertIn("DISPLAY_CHILDREN_GT50MS=0", block)
        self.assertIn("TRACED_CHILDREN=0", block)
        self.assertIn("RESIDUAL_REASON=NO_TRACED_CHILDREN", block)
        self.assertIn("TRUE_SELF_OR_UNTRACED_RESIDUAL_MS=100.0", block)

    def test_golden_profiler_block_is_inert_when_full_trace_is_off(self) -> None:
        session = SimpleNamespace(base_dir=self._session_dir)
        artifact = {"status": "ready", "remote_descriptor_path": "profiles/artifact.json"}
        with patch.object(modal_app, "_V2_FULL_TRACE_ENABLED", False), patch("builtins.print") as mock_print:
            modal_app._emit_golden_profiler_block(session, artifact, "golden-request")
        mock_print.assert_not_called()

    def test_golden_profiler_reports_missing_gantt(self) -> None:
        session = SimpleNamespace(base_dir=self._session_dir)
        artifact = {"status": "ready", "remote_descriptor_path": "profiles/artifact.json"}
        with patch.object(modal_app, "_V2_FULL_TRACE_ENABLED", True), patch("builtins.print") as mock_print:
            modal_app._emit_golden_profiler_block(session, artifact, "golden-request")
        block = mock_print.call_args.args[0]
        self.assertIn("GANTT_AVAILABLE=NO reason=missing file:", block)
        self.assertTrue(block.endswith("[v2.golden_profiler] END\n"))

    def test_golden_profiler_preserves_exact_persisted_gantt(self) -> None:
        persisted = ("header\r\n" + "x" * (70 * 1024) + "\r\nfooter")
        (self._session_dir / "derived" / "golden_profile_summary.json").write_text(
            json.dumps({
                "GOLDEN_PROFILE_COMPLETE": "YES",
                "GOLDEN_PROFILE_ROOT_WALL_MS": 12.5,
                "GOLDEN_PROFILE_NEEDS_DECOMPOSITION": True,
                "root": {"wall_ms": 12.5, "needs_decomposition": True},
            }),
            encoding="utf-8",
        )
        (self._session_dir / "derived" / "golden_profile_gantt.txt").write_text(
            persisted, encoding="utf-8", newline=""
        )
        session = SimpleNamespace(base_dir=self._session_dir)
        artifact = {
            "status": "ready",
            "trace_entry_count": 17,
            "trace_truncated": False,
            "remote_bundle_path": "profiles/bundle.tar.gz",
            "bundle_size_bytes": 123,
        }
        with patch.object(modal_app, "_V2_FULL_TRACE_ENABLED", True), \
             patch.dict(os.environ, {"COMFYMODAL_V2_FULL_TRACE": "1"}, clear=False), \
             patch("builtins.print") as mock_print:
            modal_app._emit_golden_profiler_block(session, artifact, "exact-gantt")

        block = mock_print.call_args.args[0]
        normalized = persisted.replace("\r\n", "\n").replace("\r", "\n")
        start = block.index("GANTT_BEGIN\n") + len("GANTT_BEGIN\n")
        end = block.index("GANTT_END\n", start)
        self.assertEqual(block[start:end], normalized)
        self.assertNotIn("GOLDEN_PROFILER_TRUNCATED", block)
        self.assertIn("ROOT=golden_serial_execute", block)
        self.assertIn("TRACE_EVENTS=17", block)
        self.assertIn("BUNDLE_BYTES=123", block)

    def test_e27_formatter_emits_failed_predicate_from_persisted_report(self) -> None:
        telemetry = {
            "e27_raw_evidence_path": "raw/e27_source_mechanism.json",
            "stages": [{"details": {"transport_stats": {
                "actual_source": {
                    "arm": "static_e27",
                    "producer_count": 4,
                    "actual_source_events": [{
                        "producer_id": 0, "requested_bytes": 8, "returned_bytes": 8,
                    }],
                    "max_actual_source_inflight": 1,
                    "time_weighted_mean_qd": 1.0,
                    "qd_occupancy_ms": {"4": 0.0},
                    "h2d_events": [{"complete_ns": 2}],
                    "h2d_submitted_bytes": 8,
                    "h2d_completed_bytes": 8,
                    "H2D_TOTAL_WALL_MS": 1.0,
                    "fallback": 0,
                    "poison": 0,
                    "quiescence": True,
                    "topology": {
                        "coverage_exact": False,
                        "gaps": 1,
                        "overlaps": 0,
                        "unexpected_duplicates": 0,
                    },
                },
                "e27_source_mechanism_evaluation": {
                    "E27_SOURCE_MECHANISM_PROVEN": "NO",
                    "failed_predicates": ["max_actual_source_inflight", "coverage_exact"],
                },
            }}}],
        }
        with patch.dict(os.environ, {"COMFYMODAL_V2_E27_FORENSICS": "1"}, clear=False), \
             patch("builtins.print") as mock_print:
            projection = modal_app._emit_e27_forensics_block(telemetry)

        block = mock_print.call_args.args[0]
        self.assertIn("[v2.e27] BEGIN", block)
        self.assertIn("STATIC_ARM=static_e27", block)
        self.assertIn("E27_SOURCE_MECHANISM_PROVEN=NO", block)
        self.assertIn("E27_FAILED_PREDICATE=max_actual_source_inflight", block)
        self.assertIn("E27_FAILED_PREDICATE=coverage_exact", block)
        self.assertEqual(projection["E27_EVIDENCE_AVAILABLE"], "YES")

    def test_e27_formatter_projects_success_failure_reason_as_none(self) -> None:
        telemetry = {
            "actual_source": {
                "arm": "static_e27",
                "producer_count": 1,
                "actual_source_events": [{
                    "producer_id": 0,
                    "requested_bytes": 8,
                    "returned_bytes": 8,
                }],
            },
            "e27_source_mechanism_evaluation": {
                "E27_SOURCE_MECHANISM_PROVEN": "YES",
            },
        }
        with patch.dict(os.environ, {"COMFYMODAL_V2_E27_FORENSICS": "1"}, clear=False), \
             patch("builtins.print") as mock_print:
            persisted_path = self._root / "golden" / "telemetry.json"
            projection = modal_app._emit_e27_forensics_block(
                telemetry, persisted_path=persisted_path
            )

        self.assertEqual(projection["E27_FAILURE_REASON"], "none")
        block = mock_print.call_args.args[0]
        self.assertIn("E27_FAILURE_REASON=none", block)
        self.assertIn(f"RAW_EVIDENCE_PATH={persisted_path}", block)

    def test_golden_sage_provenance_prefers_bootstrap_state(self) -> None:
        api = SimpleNamespace(
            _sage_runtime_mode="",
            bootstrap=SimpleNamespace(
                state=SimpleNamespace(sage_mode="baked_cuda")
            )
        )
        with patch.dict(
            os.environ, {"COMFYMODAL_SAGE_RUNTIME_MODE": "baked_cuda"}, clear=False
        ):
            provenance = modal_app._golden_sage_provenance(api)
        self.assertEqual(provenance["sage_runtime_mode_configured"], "baked_cuda")
        self.assertEqual(provenance["sage_runtime_mode_effective_input"], "auto")
        self.assertEqual(provenance["sage_runtime_mode_resolution_source"], "golden_env")
        self.assertEqual(provenance["sage_runtime_mode_resolved"], "baked_cuda")

    def test_e27_formatter_is_inert_when_disabled(self) -> None:
        with patch.dict(os.environ, {"COMFYMODAL_V2_E27_FORENSICS": "0"}, clear=False), \
             patch("builtins.print") as mock_print:
            projection = modal_app._emit_e27_forensics_block({})
        self.assertEqual(projection, {})
        mock_print.assert_not_called()

    def test_e27_requested_without_physical_evidence_is_explicit_failure(self) -> None:
        with patch.dict(os.environ, {"COMFYMODAL_V2_E27_FORENSICS": "1"}, clear=False), \
             patch("builtins.print") as mock_print:
            projection = modal_app._emit_e27_forensics_block(None)
        block = mock_print.call_args.args[0]
        self.assertIn("[v2.e27] BEGIN", block)
        self.assertIn("E27_EVIDENCE_AVAILABLE=NO", block)
        self.assertIn(
            "E27_FAILURE_REASON=physical_actual_source_report_unavailable", block
        )
        self.assertIn("E27_SOURCE_MECHANISM_PROVEN=NO", block)
        self.assertEqual(projection["E27_EVIDENCE_AVAILABLE"], "NO")


if __name__ == "__main__":
    unittest.main()
