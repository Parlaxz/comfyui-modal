from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from comfymodal_runtime import modal_app
from comfymodal_runtime.runtime_state import FakeVolume


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
        self._path_patch = patch.object(modal_app, "RUNTIME_STATE_PATH", str(self._volume_path))
        self._path_patch.start()
        modal_app._FULL_TRACE_FINALIZED_IDS.clear()

    def tearDown(self) -> None:
        modal_app._FULL_TRACE_FINALIZED_IDS.clear()
        self._path_patch.stop()
        self._tmp.cleanup()

    def _session(self) -> SimpleNamespace:
        return SimpleNamespace(trace_id="trace-test", base_dir=self._session_dir)

    def test_bundle_is_deterministic_and_manifest_matches(self) -> None:
        (self._session_dir / "raw" / "extra.json").write_bytes(b"payload")
        first = modal_app._build_full_trace_bundle(self._session())
        second = modal_app._build_full_trace_bundle(self._session())
        self.assertIsNotNone(first)
        self.assertIsNotNone(second)
        assert first is not None and second is not None
        self.assertEqual(first[3], second[3])
        self.assertEqual(first[3], hashlib.sha256(first[2]).hexdigest())

    def test_upload_is_atomic_and_commits_once(self) -> None:
        volume = FakeVolume()
        path = modal_app._upload_full_trace_bundle(volume, "trace-test", b"bundle", "sha")
        self.assertEqual(path, "full_trace/trace-test/bundle.tar.gz")
        self.assertEqual(volume.commit_count, 1)
        self.assertEqual(
            (self._volume_path / "full_trace" / "trace-test" / "bundle.tar.gz").read_bytes(),
            b"bundle",
        )

    def test_finalize_returns_ready_and_is_idempotent(self) -> None:
        session = MagicMock()
        session.trace_id = "trace-test"
        session.base_dir = self._session_dir
        volume = FakeVolume()
        with patch.object(modal_app, "_V2_FULL_TRACE_ENABLED", True):
            first = modal_app._finalize_full_trace(session, volume, "request-1")
            second = modal_app._finalize_full_trace(session, volume, "request-2")
        self.assertEqual(first["status"], "ready")
        self.assertEqual(second["status"], "absent")
        session.stop_tracing.assert_called_once()
        self.assertEqual(volume.commit_count, 1)

    def test_finalize_reports_upload_error(self) -> None:
        session = MagicMock()
        session.trace_id = "trace-test"
        session.base_dir = self._session_dir
        with patch.object(modal_app, "_V2_FULL_TRACE_ENABLED", True), patch.object(
            modal_app, "_upload_full_trace_bundle", return_value=None
        ):
            result = modal_app._finalize_full_trace(session, FakeVolume(), "request-1")
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["error_type"], "UploadError")

    def test_disabled_artifact_is_absent(self) -> None:
        with patch.object(modal_app, "_V2_FULL_TRACE_ENABLED", False):
            self.assertEqual(
                modal_app._safe_full_trace_artifact(None, None, "request-1")["status"],
                "absent",
            )


if __name__ == "__main__":
    unittest.main()
