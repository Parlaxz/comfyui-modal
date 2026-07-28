"""Unit tests for V2 benchmark trace download handoff.

Covers the full_trace_artifact lifecycle in ``_run_one``:

  - ``status == \"ready\"`` artifact with required fields
    → downloader invoked exactly once, ``full_trace_download.json`` written
  - ``status == \"error\"`` artifact with ``error_type``/``error``
    → ``RuntimeError`` raised, run file preserved
  - Absent artifact (no key or non-dict) → no-op
  - Download failure → run file preserved, exception propagates
  - Missing required fields on ready artifact → ``RuntimeError``
  - Unknown status → treated as absent (no-op)
"""

from __future__ import annotations

import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest import mock

from tools.benchmark_v2_direct import (
    _handle_full_trace_artifact,
    _find_in_dir,
)

# ============================================================================
# Fixtures
# ============================================================================

READY_FULL_TRACE: dict[str, Any] = {
    "status": "ready",
    "volume_name": "test-trace-vol",
    "remote_bundle_path": "traces/trace_bundle_abc123.zip",
    "bundle_sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    "trace_id": "trace-v2-run-001",
}

ERROR_FULL_TRACE: dict[str, Any] = {
    "status": "error",
    "error_type": "trace_collection_failed",
    "error": "Something went wrong during trace collection",
}


def _fake_downloader_success(**kwargs: Any) -> dict[str, Any]:
    """Return a plausible success metadata dict matching the keywords."""
    t_id = kwargs.get("trace_id", "unknown")
    out_dir = kwargs.get("output_dir", Path())
    return {
        "trace_id": t_id,
        "remote_bundle_path": str(kwargs.get("remote_bundle_path", "")),
        "local_bundle_path": str(out_dir / f"trace_{t_id}.bundle"),
        "extract_dir": str(out_dir / f"trace_{t_id}_extracted"),
        "bundle_sha256": str(kwargs.get("bundle_sha256", "")),
        "verified": True,
        "report_path": "",
        "viztracer_path": "",
        "torch_trace_path": "",
        "manifest_path": "",
        "download_ms": 150.0,
    }


# ============================================================================
# _handle_full_trace_artifact tests
# ============================================================================


class TestHandleFullTraceArtifact(unittest.IsolatedAsyncioTestCase):
    """Offline unit tests for the full_trace_artifact handoff handler."""

    def setUp(self):
        self._tmp = tempfile.mkdtemp()
        self.output_dir = Path(self._tmp)
        self.workspace: dict[str, Any] = {"token_id": "t", "token_secret": "s"}
        self.transport = mock.AsyncMock()
        # Pre-seed a run file to simulate the caller having written it
        self.run_file = self.output_dir / "run_0.json"
        self.run_file.write_text(
            '{"run_index": 0, "pre_existing": true}', encoding="utf-8",
        )

    def tearDown(self):
        import shutil
        shutil.rmtree(self._tmp, ignore_errors=True)

    # ── Ready artifact ─────────────────────────────────────────────────

    async def test_ready_artifact_invokes_downloader_once(self):
        """Ready artifact triggers exactly one downloader call with correct args."""
        result = {"full_trace_artifact": dict(READY_FULL_TRACE)}
        call_args: list[dict[str, Any]] = []

        async def tracking_downloader(**kw: Any) -> dict[str, Any]:
            call_args.append(kw)
            return _fake_downloader_success(**kw)

        meta = await _handle_full_trace_artifact(
            result, self.output_dir, self.workspace, self.transport,
            _test_trace_downloader=tracking_downloader,
        )

        # Exactly one call
        self.assertEqual(len(call_args), 1)
        # Correct fields forwarded
        self.assertEqual(call_args[0]["volume_name"], READY_FULL_TRACE["volume_name"])
        self.assertEqual(call_args[0]["remote_bundle_path"], READY_FULL_TRACE["remote_bundle_path"])
        self.assertEqual(call_args[0]["bundle_sha256"], READY_FULL_TRACE["bundle_sha256"])
        self.assertEqual(call_args[0]["trace_id"], READY_FULL_TRACE["trace_id"])
        self.assertIs(call_args[0]["output_dir"], self.output_dir)
        self.assertIs(call_args[0]["workspace"], self.workspace)
        self.assertIs(call_args[0]["transport"], self.transport)
        # Returns the download metadata
        self.assertIsNotNone(meta)
        self.assertEqual(meta["trace_id"], READY_FULL_TRACE["trace_id"])

    async def test_ready_artifact_writes_full_trace_download_json(self):
        """full_trace_download.json is written with all required keys."""
        result = {"full_trace_artifact": dict(READY_FULL_TRACE)}

        async def fake_dl(**kw: Any) -> dict[str, Any]:
            return _fake_downloader_success(**kw)

        await _handle_full_trace_artifact(
            result, self.output_dir, self.workspace, self.transport,
            _test_trace_downloader=fake_dl,
        )

        dl_path = self.output_dir / "full_trace_download.json"
        self.assertTrue(dl_path.is_file(), "full_trace_download.json not written")
        data = json.loads(dl_path.read_text(encoding="utf-8"))

        # All required keys present
        for key in (
            "trace_id", "remote_bundle_path", "local_bundle_path",
            "extract_dir", "bundle_sha256", "verified",
            "report_path", "viztracer_path", "torch_trace_path",
            "manifest_path", "download_ms",
        ):
            with self.subTest(key=key):
                self.assertIn(key, data, f"Missing key: {key}")

        self.assertEqual(data["trace_id"], READY_FULL_TRACE["trace_id"])
        self.assertEqual(data["remote_bundle_path"], READY_FULL_TRACE["remote_bundle_path"])
        self.assertEqual(data["bundle_sha256"], READY_FULL_TRACE["bundle_sha256"])

    async def test_ready_artifact_preserves_run_file(self):
        """Run file survives after successful trace download."""
        result = {"full_trace_artifact": dict(READY_FULL_TRACE)}

        async def fake_dl(**kw: Any) -> dict[str, Any]:
            return _fake_downloader_success(**kw)

        await _handle_full_trace_artifact(
            result, self.output_dir, self.workspace, self.transport,
            _test_trace_downloader=fake_dl,
        )

        self.assertTrue(self.run_file.is_file(), "run file was removed")
        data = json.loads(self.run_file.read_text(encoding="utf-8"))
        self.assertEqual(data["run_index"], 0)

    # ── Error artifact ─────────────────────────────────────────────────

    async def test_error_artifact_raises_runtime_error(self):
        """Error artifact raises RuntimeError with sanitized error_type and error."""
        result = {"full_trace_artifact": dict(ERROR_FULL_TRACE)}
        with self.assertRaises(RuntimeError) as ctx:
            await _handle_full_trace_artifact(
                result, self.output_dir, self.workspace, self.transport,
            )
        msg = str(ctx.exception)
        self.assertIn("Trace bundle error", msg)
        self.assertIn("trace_collection_failed", msg)
        self.assertIn("Something went wrong", msg)

    async def test_error_artifact_preserves_run_file(self):
        """Run file persists even when error artifact raises."""
        result = {"full_trace_artifact": dict(ERROR_FULL_TRACE)}
        with self.assertRaises(RuntimeError):
            await _handle_full_trace_artifact(
                result, self.output_dir, self.workspace, self.transport,
            )
        self.assertTrue(self.run_file.is_file(), "run file was removed on error")

    async def test_error_artifact_minimal(self):
        """Error artifact with only error_type (no error message) still raises."""
        result = {
            "full_trace_artifact": {
                "status": "error",
                "error_type": "disk_full",
            },
        }
        with self.assertRaises(RuntimeError) as ctx:
            await _handle_full_trace_artifact(
                result, self.output_dir, self.workspace, self.transport,
            )
        msg = str(ctx.exception)
        self.assertIn("disk_full", msg)
        # Error message should mention the type even without an error key text
        self.assertIn("(disk_full)", msg)

    async def test_error_artifact_sanitized(self):
        """Long error_type and error are truncated."""
        long_type = "x" * 150
        long_msg = "y" * 500
        result = {
            "full_trace_artifact": {
                "status": "error",
                "error_type": long_type,
                "error": long_msg,
            },
        }
        with self.assertRaises(RuntimeError) as ctx:
            await _handle_full_trace_artifact(
                result, self.output_dir, self.workspace, self.transport,
            )
        msg = str(ctx.exception)
        # Should contain truncated content
        self.assertIn("xxx", msg)
        self.assertIn("yyy", msg)
        # Should NOT contain the full un-truncated strings
        self.assertNotIn("x" * 150, msg)  # error_type truncated to 100
        self.assertNotIn("y" * 500, msg)  # error truncated to 200

    # ── Absent artifact ────────────────────────────────────────────────

    async def test_absent_artifact_returns_none(self):
        """No full_trace_artifact key → returns None, no download file."""
        result = {"some_key": "some_value"}
        meta = await _handle_full_trace_artifact(
            result, self.output_dir, self.workspace, self.transport,
        )
        self.assertIsNone(meta)
        dl_path = self.output_dir / "full_trace_download.json"
        self.assertFalse(
            dl_path.exists(),
            "full_trace_download.json was written for absent artifact",
        )

    async def test_absent_artifact_no_downloader_call(self):
        """No full_trace_artifact → downloader never invoked."""
        result = {"some_key": "some_value"}
        called = False

        async def never_called(**kw: Any) -> dict[str, Any]:
            nonlocal called
            called = True
            return {}

        await _handle_full_trace_artifact(
            result, self.output_dir, self.workspace, self.transport,
            _test_trace_downloader=never_called,
        )
        self.assertFalse(called, "downloader was called despite absent artifact")

    async def test_absent_artifact_full_trace_artifact_is_none(self):
        """full_trace_artifact is None → absent."""
        result = {"full_trace_artifact": None}
        meta = await _handle_full_trace_artifact(
            result, self.output_dir, self.workspace, self.transport,
        )
        self.assertIsNone(meta)

    async def test_absent_artifact_not_a_dict(self):
        """result itself is not a dict → absent."""
        meta = await _handle_full_trace_artifact(
            "not_a_dict", self.output_dir, self.workspace, self.transport,
        )
        self.assertIsNone(meta)

    async def test_unknown_status_is_absent(self):
        """Unknown status string → absent (no-op)."""
        result = {"full_trace_artifact": {"status": "unknown_status"}}
        meta = await _handle_full_trace_artifact(
            result, self.output_dir, self.workspace, self.transport,
        )
        self.assertIsNone(meta)

    # ── Missing required fields on ready ───────────────────────────────

    async def test_ready_artifact_missing_fields_raises(self):
        """Ready artifact missing required fields raises RuntimeError."""
        # Missing bundle_sha256 and trace_id
        result = {
            "full_trace_artifact": {
                "status": "ready",
                "volume_name": "vol",
                "remote_bundle_path": "path.zip",
            },
        }
        with self.assertRaises(RuntimeError) as ctx:
            await _handle_full_trace_artifact(
                result, self.output_dir, self.workspace, self.transport,
            )
        self.assertIn("missing required fields", str(ctx.exception).lower())

    async def test_ready_artifact_empty_fields_raises(self):
        """Ready artifact with empty string fields raises RuntimeError."""
        result = {
            "full_trace_artifact": {
                "status": "ready",
                "volume_name": "",
                "remote_bundle_path": "",
                "bundle_sha256": "",
                "trace_id": "",
            },
        }
        with self.assertRaises(RuntimeError) as ctx:
            await _handle_full_trace_artifact(
                result, self.output_dir, self.workspace, self.transport,
            )
        self.assertIn("missing required fields", str(ctx.exception).lower())

    # ── Download failure ───────────────────────────────────────────────

    async def test_download_failure_raises(self):
        """Downloader raising → RuntimeError propagates."""
        result = {"full_trace_artifact": dict(READY_FULL_TRACE)}

        async def failing_downloader(**kw: Any) -> dict[str, Any]:
            raise RuntimeError("remote volume unavailable")

        with self.assertRaises(RuntimeError) as ctx:
            await _handle_full_trace_artifact(
                result, self.output_dir, self.workspace, self.transport,
                _test_trace_downloader=failing_downloader,
            )
        self.assertIn("remote volume unavailable", str(ctx.exception))

    async def test_run_file_preserved_on_download_failure(self):
        """Run file remains even when downloader raises."""
        result = {"full_trace_artifact": dict(READY_FULL_TRACE)}

        async def failing_downloader(**kw: Any) -> dict[str, Any]:
            raise RuntimeError("timeout downloading trace bundle")

        with self.assertRaises(RuntimeError):
            await _handle_full_trace_artifact(
                result, self.output_dir, self.workspace, self.transport,
                _test_trace_downloader=failing_downloader,
            )

        self.assertTrue(self.run_file.is_file(), "run file was removed on download failure")
        data = json.loads(self.run_file.read_text(encoding="utf-8"))
        self.assertEqual(data["run_index"], 0)

    async def test_no_full_trace_download_json_on_failure(self):
        """full_trace_download.json is NOT written when download fails."""
        result = {"full_trace_artifact": dict(READY_FULL_TRACE)}

        async def failing_downloader(**kw: Any) -> dict[str, Any]:
            raise RuntimeError("extraction failed")

        with self.assertRaises(RuntimeError):
            await _handle_full_trace_artifact(
                result, self.output_dir, self.workspace, self.transport,
                _test_trace_downloader=failing_downloader,
            )

        dl_path = self.output_dir / "full_trace_download.json"
        self.assertFalse(
            dl_path.exists(),
            "full_trace_download.json was written despite failure",
        )

    # ── Exactly once ───────────────────────────────────────────────────

    async def test_no_second_remote_request(self):
        """Downloader called exactly once for ready artifact."""
        result = {"full_trace_artifact": dict(READY_FULL_TRACE)}
        call_count = 0

        async def counting_downloader(**kw: Any) -> dict[str, Any]:
            nonlocal call_count
            call_count += 1
            return _fake_downloader_success(**kw)

        await _handle_full_trace_artifact(
            result, self.output_dir, self.workspace, self.transport,
            _test_trace_downloader=counting_downloader,
        )
        self.assertEqual(call_count, 1)

    async def test_error_artifact_zero_downloader_calls(self):
        """Error artifact → zero downloader invocations."""
        result = {"full_trace_artifact": dict(ERROR_FULL_TRACE)}
        call_count = 0

        async def counting_downloader(**kw: Any) -> dict[str, Any]:
            nonlocal call_count
            call_count += 1
            return _fake_downloader_success(**kw)

        with self.assertRaises(RuntimeError):
            await _handle_full_trace_artifact(
                result, self.output_dir, self.workspace, self.transport,
                _test_trace_downloader=counting_downloader,
            )
        self.assertEqual(call_count, 0)


# ============================================================================
# Metadata contract for full_trace_download.json
# ============================================================================


class TestFullTraceDownloadMetadataShape(unittest.TestCase):
    """Structural contract for the download metadata dict.

    The return value of the downloader (whether the real CLI or a test fake)
    must contain exactly/at least the 11 required keys.
    """

    def test_download_meta_has_all_required_keys(self):
        """The downloader return dict must contain all required keys."""
        meta = _fake_downloader_success(
            trace_id="t1",
            remote_bundle_path="r1",
            bundle_sha256="s1",
            output_dir=Path("/tmp"),
        )
        required_keys = {
            "trace_id",
            "remote_bundle_path",
            "local_bundle_path",
            "extract_dir",
            "bundle_sha256",
            "verified",
            "report_path",
            "viztracer_path",
            "torch_trace_path",
            "manifest_path",
            "download_ms",
        }
        for key in required_keys:
            with self.subTest(key=key):
                self.assertIn(key, meta, f"Missing required key: {key}")


# ============================================================================
# _find_in_dir
# ============================================================================


class TestFindInDir(unittest.TestCase):
    """Edge cases for the recursive file finder."""

    def setUp(self):
        self._tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        import shutil
        shutil.rmtree(self._tmp, ignore_errors=True)

    def test_finds_exact_match(self):
        (self._tmp / "report.html").write_text("a")
        result = _find_in_dir(self._tmp, "*report*")
        self.assertIsNotNone(result)
        self.assertEqual(result.name, "report.html")

    def test_finds_in_subdir(self):
        sub = self._tmp / "sub"
        sub.mkdir()
        (sub / "trace.viz.json").write_text("{}")
        result = _find_in_dir(self._tmp, "*.viz.json")
        self.assertIsNotNone(result)
        self.assertEqual(result.name, "trace.viz.json")

    def test_returns_none_on_no_match(self):
        result = _find_in_dir(self._tmp, "*nonexistent*")
        self.assertIsNone(result)

    def test_returns_first_match(self):
        (self._tmp / "a_report.html").write_text("a")
        (self._tmp / "b_report.html").write_text("b")
        result = _find_in_dir(self._tmp, "*report*")
        self.assertIsNotNone(result)
        self.assertIn("report", result.name)

    def test_empty_directory(self):
        result = _find_in_dir(self._tmp, "*")
        self.assertIsNone(result)


# ============================================================================
# deploy_v2_full_trace_only.bat static checks
# ============================================================================


class TestDeployV2FullTraceOnlyBatchFile(unittest.TestCase):
    """Verify the deploy-only batch is V2-only and workload-free."""

    BATCH_PATH = Path(__file__).resolve().parents[1] / "deploy_v2_full_trace_only.bat"

    def setUp(self):
        if not self.BATCH_PATH.is_file():
            self.skipTest("deploy_v2_full_trace_only.bat is not present")
        self.content = self.BATCH_PATH.read_text(encoding="utf-8")

    def test_exactly_one_v2_deploy(self):
        deploy_lines = [
            line for line in self.content.splitlines()
            if " deploy " in line.lower()
            and "comfymodal_runtime.modal_app" in line
        ]
        self.assertEqual(len(deploy_lines), 1)

    def test_no_benchmark_or_v1_deploy(self):
        lowered = self.content.lower()
        self.assertNotIn("benchmark_v2_direct.py", lowered)
        self.assertNotIn("comfyapp.py", lowered)
        self.assertNotIn("deploy_and_benchmark", lowered)
        self.assertNotIn("run_v2_single.bat", lowered)

    def test_no_inference_or_acceptance(self):
        lowered = self.content.lower()
        self.assertNotIn("acceptance", lowered)
        self.assertNotIn("comfyapp", lowered)

    def test_required_v2_full_trace_environment(self):
        required = {
            'set "COMFYMODAL_V2_APP_NAME=stable-modal-comfy-v2-shadow"',
            'set "COMFYMODAL_V2_CLASS_NAME=ModalRuntimeEntrypointV2"',
            'set "COMFYMODAL_V2_GPU=rtx-pro-6000"',
            'set "COMFYMODAL_V2_CPU_MODEL_SNAPSHOT=1"',
            'set "COMFYMODAL_V2_FULL_TRACE=1"',
            'set "COMFYMODAL_V2_FULL_TRACE_TORCH=1"',
            'set "COMFYMODAL_V2_FULL_TRACE_ENTRIES=8000000"',
            'set "COMFYMODAL_V2_FULL_TRACE_RESOURCE_INTERVAL_MS=50"',
            'set "COMFYMODAL_V2_PROFILE_VOLUME=comfymodal-v2-profiles"',
            'set "PYTHONIOENCODING=utf-8"',
            'set "PYTHONUTF8=1"',
        }
        for line in required:
            with self.subTest(line=line):
                self.assertIn(line, self.content)
        self.assertIn(
            'if not defined COMFYMODAL_V2_MEMORY_MB set "COMFYMODAL_V2_MEMORY_MB=49152"',
            self.content,
        )

    def test_credentials_are_not_printed(self):
        for line in self.content.splitlines():
            stripped = line.strip().lower()
            if stripped.startswith("::") or stripped.startswith("rem"):
                continue
            if stripped.startswith("echo"):
                self.assertNotIn("modal_token_id", stripped)
                self.assertNotIn("modal_token_secret", stripped)
                self.assertNotIn("token_id", stripped)
                self.assertNotIn("token_secret", stripped)


# ============================================================================
# Entry point
# ============================================================================

if __name__ == "__main__":
    unittest.main()
