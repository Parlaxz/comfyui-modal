"""FAST_UNIT: durable run-evidence infrastructure.

Covers the four durable-evidence seams:

* durable remote-execution log write/read roundtrip (modal_app evidence
  section, exercised with fakes);
* early local manifest lifecycle (running -> timeout leaves a discoverable
  manifest containing the request id);
* run/request-scoped cancel resolution (syntactic, mocked transport —
  never ``modal app stop``);
* compiler-cache metadata snapshot/diff on fake trees.

Dependency-free: stdlib + pytest plus the unwired modules only
(``tools.v2_control.run_lifecycle``,
``comfymodal_runtime.compiler_cache``,
``comfymodal_runtime.runtime_state``).  No torch / Comfy / Modal /
modal_app imports at module scope (modal_app is on the FAST_UNIT
heavy-import guard, so its evidence seam is verified by AST
source-contract plus exec of the extracted self-contained section with
injected fakes, matching the repo's existing audit-test style).
"""

from __future__ import annotations

import ast
import asyncio
import json
import os
import sys
import time as _time_mod
from collections.abc import Mapping
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

pytestmark = pytest.mark.fast_unit

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.v2_control import run_lifecycle as lifecycle  # noqa: E402
from comfymodal_runtime import compiler_cache as compiler_cache  # noqa: E402
from comfymodal_runtime.runtime_state import FakeVolume  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]
MODAL_APP_PATH = REPO_ROOT / "comfymodal_runtime" / "modal_app.py"
RUN_LIFECYCLE_PATH = (
    REPO_ROOT / "tools" / "v2_control" / "run_lifecycle.py"
)

EVIDENCE_SECTION_START = "# \u2500\u2500 Durable run evidence (request-scoped, volume-backed) \u2500\u2500"
EVIDENCE_SECTION_END = "def _ensure_custom_nodes_compat_symlink() -> None:"

FIXED_TS = 1700000000.0


# ---------------------------------------------------------------------------
# modal_app evidence section: extraction helpers (AST + exec, no import)
# ---------------------------------------------------------------------------


def _modal_app_source() -> str:
    return MODAL_APP_PATH.read_text(encoding="utf-8")


def _evidence_section_source() -> str:
    source = _modal_app_source()
    start = source.index(EVIDENCE_SECTION_START)
    end = source.index(EVIDENCE_SECTION_END)
    assert start < end, "evidence section markers out of order"
    return source[start:end]


def _exec_evidence_section() -> dict[str, Any]:
    """Exec the self-contained evidence section with injected stdlib names."""
    import asyncio as _asyncio
    import json as _json
    import os as _os
    import time as _time

    namespace: dict[str, Any] = {
        "json": _json,
        "os": _os,
        "time": _time,
        "asyncio": _asyncio,
        "Mapping": Mapping,
        "Any": Any,
        "RUNTIME_STATE_PATH": "/mnt/test-state",
    }
    exec(compile(_evidence_section_source(), "modal_app_evidence", "exec"),
         namespace)
    return namespace


def _function_defs(source: str, name: str) -> list[Any]:
    tree = ast.parse(source)
    return [node for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == name]


def _recorded_event_types(source: str, func_name: str) -> set[str]:
    """Event-type string literals passed to record_run_evidence_event."""
    found: set[str] = set()
    for func in _function_defs(source, func_name):
        for node in ast.walk(func):
            if not isinstance(node, ast.Call):
                continue
            target = node.func
            if not (isinstance(target, ast.Name)
                    and target.id == "record_run_evidence_event"):
                continue
            if len(node.args) >= 2 and isinstance(node.args[1], ast.Constant):
                found.add(str(node.args[1].value))
    return found


def _calls_in_finally(source: str, func_name: str, call_name: str) -> bool:
    """True when *call_name* is invoked inside a finally of *func_name*."""
    for func in _function_defs(source, func_name):
        for node in ast.walk(func):
            if not isinstance(node, ast.Try) or not node.finalbody:
                continue
            for child in ast.walk(ast.Module(body=node.finalbody, type_ignores=[])):
                if isinstance(child, ast.Call):
                    target = child.func
                    if isinstance(target, ast.Name) and target.id == call_name:
                        return True
    return False


class TestEvidenceSectionContract:
    def test_section_markers_and_names_present(self) -> None:
        source = _modal_app_source()
        for name in (
            "RUN_EVIDENCE_SCHEMA_VERSION",
            "RUN_EVIDENCE_DIRNAME",
            "RUN_EVIDENCE_EVENT_TYPES",
            "run_evidence_relpath",
            "record_run_evidence_event",
            "read_run_evidence_events",
            "flush_run_evidence",
        ):
            assert name in source, name
        # Persistent volume mount identity (already-mounted runtime-state
        # volume; no new volume introduced by this work).
        assert 'RUNTIME_STATE_PATH = "/mnt/comfymodal_runtime_state"' in source

    def test_allowlist_is_exactly_lifecycle_compiler_modelload(self) -> None:
        helpers = _exec_evidence_section()
        assert helpers["RUN_EVIDENCE_EVENT_TYPES"] == frozenset({
            "request_start", "request_terminal",
            "compile_finalize", "model_load",
        })

    def test_record_allows_listed_rejects_profiler_and_oversize(self) -> None:
        helpers = _exec_evidence_section()
        record = helpers["record_run_evidence_event"]
        buffers: dict[str, list[dict[str, Any]]] = {}
        for event_type in ("request_start", "request_terminal",
                           "compile_finalize", "model_load"):
            assert record("req-1", event_type, {"ok": True},
                          _buffers=buffers, _time=lambda: FIXED_TS) is True
        # Profiler/trace output can never land here (not allowlisted).
        assert record("req-1", "profiler_chunk", {"frames": []},
                      _buffers=buffers, _time=lambda: FIXED_TS) is False
        assert record("req-1", "trace", {"spans": []},
                      _buffers=buffers, _time=lambda: FIXED_TS) is False
        # Oversize single event is refused, never partially stored.
        assert record("req-1", "model_load", {"blob": "x" * 5000},
                      _buffers=buffers, _time=lambda: FIXED_TS) is False
        assert len(buffers["req-1"]) == 4

    def test_record_redacts_sensitive_keys_and_never_raises(self) -> None:
        helpers = _exec_evidence_section()
        record = helpers["record_run_evidence_event"]
        buffers: dict[str, list[dict[str, Any]]] = {}
        assert record("req-2", "request_start",
                      {"prompt": "secret hello", "latency_ms": 3},
                      _buffers=buffers, _time=lambda: FIXED_TS) is True
        fields = buffers["req-2"][0]["fields"]
        assert fields["prompt"] == "<redacted>"
        assert fields["latency_ms"] == 3
        # Garbage inputs degrade to False, never raise.
        assert record(None, "request_start", object(), _buffers=buffers) in (True, False)
        assert record("req-2", "bogus_type", {}, _buffers=buffers) is False

    def test_record_buffer_is_bounded(self) -> None:
        helpers = _exec_evidence_section()
        record = helpers["record_run_evidence_event"]
        limit = helpers["RUN_EVIDENCE_MAX_EVENTS_PER_REQUEST"]
        buffers: dict[str, list[dict[str, Any]]] = {}
        accepted = sum(
            1 for _ in range(limit + 10)
            if record("req-3", "request_start", {},
                       _buffers=buffers, _time=lambda: FIXED_TS)
        )
        assert accepted == limit

    def test_flush_write_read_roundtrip_with_fake_volume(self) -> None:
        helpers = _exec_evidence_section()
        record = helpers["record_run_evidence_event"]
        flush = helpers["flush_run_evidence"]
        read = helpers["read_run_evidence_events"]
        buffers: dict[str, list[dict[str, Any]]] = {}
        volume = FakeVolume()
        assert record("req-9", "request_start", {},
                      _buffers=buffers, _time=lambda: FIXED_TS) is True
        assert record("req-9", "model_load", {"restore_session_id": "s-1"},
                      _buffers=buffers, _time=lambda: FIXED_TS) is True
        assert record("req-9", "compile_finalize", {"released": "True"},
                      _buffers=buffers, _time=lambda: FIXED_TS) is True
        assert record("req-9", "request_terminal", {"terminal_status": "result"},
                      _buffers=buffers, _time=lambda: FIXED_TS) is True
        outcome = asyncio.run(
            flush("req-9", "completed", _buffers=buffers,
                  _volume=volume, _time=lambda: FIXED_TS)
        )
        assert outcome["flushed"] is True
        assert outcome["event_count"] == 4
        assert volume.write_count == 1
        assert volume.commit_count == 1
        # Buffer drains only on success.
        assert "req-9" not in buffers
        events = read("req-9", _volume=volume)
        assert [item["type"] for item in events] == [
            "request_start", "model_load", "compile_finalize",
            "request_terminal", "request_flush",
        ]
        assert all(item["request_id"] == "req-9" for item in events)
        assert events[-1]["fields"]["outcome"] == "completed"
        assert events[-1]["fields"]["event_count"] == 4
        assert events[1]["fields"]["restore_session_id"] == "s-1"

    def test_flush_without_volume_keeps_events_for_later_boundary(self) -> None:
        helpers = _exec_evidence_section()
        record = helpers["record_run_evidence_event"]
        flush = helpers["flush_run_evidence"]
        read = helpers["read_run_evidence_events"]
        buffers: dict[str, list[dict[str, Any]]] = {}
        assert record("req-7", "request_start", {},
                      _buffers=buffers, _time=lambda: FIXED_TS) is True
        missed = asyncio.run(
            flush("req-7", "completed", _buffers=buffers, _resources={})
        )
        assert missed["flushed"] is False
        assert missed["reason"] == "no_volume"
        assert len(buffers["req-7"]) == 1  # retained, still bounded
        volume = FakeVolume()
        later = asyncio.run(
            flush("req-7", "completed", _buffers=buffers, _volume=volume)
        )
        assert later["flushed"] is True
        assert [item["type"] for item in read("req-7", _volume=volume)][0] == "request_start"

    def test_read_empty_and_missing_never_raise(self) -> None:
        helpers = _exec_evidence_section()
        read = helpers["read_run_evidence_events"]
        assert read("nope", _volume=FakeVolume()) == []
        assert read("nope", _resources={}) == []

    def test_flush_runs_in_request_finally_not_on_hot_path(self) -> None:
        source = _modal_app_source()
        assert _calls_in_finally(source, "run_plan_stream", "flush_run_evidence")
        recorded = (_recorded_event_types(source, "run_plan_stream")
                    | _recorded_event_types(source, "_execute_v2_prompt_executor"))
        assert {"request_start", "request_terminal",
                "compile_finalize", "model_load"} <= recorded

    def test_compile_wiring_still_finalizes_with_record(self) -> None:
        """The ON_DETACH finalize call is preserved (release semantics kept)."""
        source = _modal_app_source()
        found_finalize = False
        found_record = False
        for func in _function_defs(source, "_execute_v2_prompt_executor"):
            for node in ast.walk(func):
                if not isinstance(node, ast.Call):
                    continue
                target = node.func
                if not isinstance(target, ast.Name):
                    continue
                if target.id == "_finalize_request_compile_scope":
                    found_finalize = True
                if target.id == "record_run_evidence_event":
                    found_record = True
        assert found_finalize and found_record


# ---------------------------------------------------------------------------
# Early local manifest lifecycle
# ---------------------------------------------------------------------------


def _write_running_manifest(repo: Path, **overrides: Any) -> Path:
    params: dict[str, Any] = {
        "profile": "ideogram4_h100_20261015",
        "invocation_id": "inv-test-001",
        "target": {"app": "ideogram4-h100-profile-20261015",
                   "class": "ModalRuntimeEntrypointV2",
                   "method": "run_plan_stream"},
        "deploy_fingerprint": "deploy-fp-1",
        "workspace_id": "ws-1",
        "environment": "(default)",
        "workflow_selection": {"active": True,
                               "workflow_id": "wf_81513286bb304e9f"},
        "supervisor": {"script": "supervisor.py", "pid": 4242},
        "backend_command": "run_v2_single.bat",
    }
    params.update(overrides)
    return lifecycle.write_early_run_manifest(repo, **params)


class TestEarlyManifestLifecycle:
    def test_running_manifest_carries_required_identity(self, tmp_path: Path) -> None:
        path = _write_running_manifest(tmp_path)
        doc = lifecycle.read_run_manifest(path)
        assert doc is not None
        assert doc["status"] == lifecycle.STATUS_RUNNING
        assert doc["request_id"] == ""
        assert doc["profile"] == "ideogram4_h100_20261015"
        assert doc["invocation_id"] == "inv-test-001"
        assert doc["deployment"]["app"] == "ideogram4-h100-profile-20261015"
        assert doc["deployment"]["deploy_fingerprint"] == "deploy-fp-1"
        assert doc["workflow_selection"]["workflow_id"] == "wf_81513286bb304e9f"
        assert doc["supervisor"] == {"script": "supervisor.py", "pid": 4242}
        assert "created_at" in doc and "updated_at" in doc

    def test_timeout_leaves_discoverable_manifest_with_request_id(
        self, tmp_path: Path
    ) -> None:
        """A timeout MUST leave a discoverable manifest with the request id."""
        path = _write_running_manifest(tmp_path)
        updated = lifecycle.update_run_manifest(
            path, status=lifecycle.STATUS_TIMEOUT, request_id="req-timeout-9",
            error="BackendError: backend run timed out after 180s",
        )
        assert updated is not None
        assert updated["status"] == lifecycle.STATUS_TIMEOUT
        assert updated["request_id"] == "req-timeout-9"
        found = lifecycle.find_manifest_for_request(tmp_path, "req-timeout-9")
        assert found is not None
        found_path, found_doc = found
        assert found_path == path
        assert found_doc["status"] == lifecycle.STATUS_TIMEOUT
        assert "timed out" in found_doc["error"]

    def test_terminal_status_never_downgraded_to_running(
        self, tmp_path: Path
    ) -> None:
        path = _write_running_manifest(tmp_path)
        lifecycle.update_run_manifest(path, status=lifecycle.STATUS_TIMEOUT,
                                      request_id="req-1")
        kept = lifecycle.update_run_manifest(path, status=lifecycle.STATUS_RUNNING)
        assert kept is not None
        assert kept["status"] == lifecycle.STATUS_TIMEOUT
        assert kept["request_id"] == "req-1"

    def test_completion_points_at_final_manifest(self, tmp_path: Path) -> None:
        path = _write_running_manifest(tmp_path)
        lifecycle.update_run_manifest(path, status=lifecycle.STATUS_RUNNING,
                                      request_id="req-2")
        done = lifecycle.update_run_manifest(
            path, status=lifecycle.STATUS_COMPLETED, request_id="req-2",
            final_manifest=str(tmp_path / "run_final.json"),
        )
        assert done is not None
        assert done["status"] == lifecycle.STATUS_COMPLETED
        assert done["final_manifest"].endswith("run_final.json")

    def test_atomic_write_leaves_no_tmp_files(self, tmp_path: Path) -> None:
        path = _write_running_manifest(tmp_path)
        lifecycle.update_run_manifest(path, status=lifecycle.STATUS_COMPLETED,
                                      request_id="req-3")
        leftovers = [p for p in path.parent.iterdir() if ".tmp." in p.name]
        assert leftovers == []

    def test_find_running_manifests_filters(self, tmp_path: Path) -> None:
        first = _write_running_manifest(tmp_path, invocation_id="inv-a")
        _write_running_manifest(tmp_path, invocation_id="inv-b",
                                profile="other-profile")
        lifecycle.update_run_manifest(first, status=lifecycle.STATUS_COMPLETED,
                                      request_id="req-a")
        running = lifecycle.find_running_manifests(tmp_path)
        assert len(running) == 1
        assert running[0][1]["invocation_id"] == "inv-b"
        assert lifecycle.find_running_manifests(
            tmp_path, profile="other-profile")[0][1]["invocation_id"] == "inv-b"
        assert lifecycle.find_running_manifests(
            tmp_path, invocation_id="inv-b")[0][1]["profile"] == "other-profile"

    def test_extract_request_id_shapes(self) -> None:
        assert lifecycle.extract_request_id("request_id=req-abc-123\n") == "req-abc-123"
        assert lifecycle.extract_request_id('{"request_id": "req-x"}') == "req-x"
        assert lifecycle.extract_request_id("REQUEST_ID: req-y;") == "req-y;"
        assert lifecycle.extract_request_id("") == ""
        assert lifecycle.extract_request_id(None) == ""
        assert lifecycle.extract_request_id("no id here") == ""


# ---------------------------------------------------------------------------
# Run-scoped cancellation (syntactic, mocked transport)
# ---------------------------------------------------------------------------


class _SyncTransport:
    def __init__(self, state: str = "pending") -> None:
        self.calls: list[tuple[str, str]] = []
        self._state = state

    def cancel_attempt(self, request_id: str, reason: str = "") -> SimpleNamespace:
        self.calls.append((request_id, reason))
        return SimpleNamespace(state=self._state, detail="put ok",
                               confirmed=(self._state == "confirmed"))


class _AsyncTransport:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    async def cancel_attempt(self, request_id: str, reason: str = "") -> dict:
        self.calls.append((request_id, reason))
        return {"state": "confirmed", "detail": "remote cancelled event"}


class TestRunScopedCancel:
    def test_prefers_live_transport_with_exact_request_id(self) -> None:
        transport = _SyncTransport()
        verdict = lifecycle.request_run_cancel(
            "req-cancel-1", reason="supervisor_timeout", transport=transport)
        assert verdict == {"outcome": "pending", "via": "transport",
                           "detail": "put ok"}
        assert transport.calls == [("req-cancel-1", "supervisor_timeout")]

    def test_drives_async_transport_to_completion(self) -> None:
        transport = _AsyncTransport()
        verdict = lifecycle.request_run_cancel(
            "req-cancel-2", reason="operator_cancel", transport=transport)
        assert verdict["outcome"] == "confirmed"
        assert verdict["via"] == "transport"
        assert transport.calls == [("req-cancel-2", "operator_cancel")]

    def test_transport_failure_is_truthful_unavailable(self) -> None:
        class _Boom:
            def cancel_attempt(self, request_id: str, reason: str = "") -> None:
                raise RuntimeError("channel down")

        verdict = lifecycle.request_run_cancel("req-x", transport=_Boom())
        assert verdict["outcome"] == "unavailable"
        assert "channel down" in verdict["detail"]

    def test_queue_put_delivers_primitive_to_request_partition(self) -> None:
        sent: list[tuple[dict, str]] = []

        def _put(message: dict, partition: str) -> bool:
            sent.append((message, partition))
            return True

        verdict = lifecycle.request_run_cancel(
            "req-q-1", reason="supervisor_timeout", queue_put=_put)
        assert verdict["outcome"] == "pending"
        assert verdict["via"] == "control_queue"
        assert sent == [({"type": "cancel", "partition": "req-q-1",
                          "reason": "supervisor_timeout"}, "req-q-1")]

    def test_queue_put_failure_is_unavailable(self) -> None:
        def _put(message: dict, partition: str) -> bool:
            raise RuntimeError("queue missing")

        verdict = lifecycle.request_run_cancel("req-q-2", queue_put=_put)
        assert verdict["outcome"] == "unavailable"
        assert verdict["via"] == "none"

    def test_no_channel_is_unavailable(self) -> None:
        verdict = lifecycle.request_run_cancel("req-q-3")
        assert verdict["outcome"] == "unavailable"
        assert verdict["via"] == "none"

    def test_empty_request_id_is_unavailable(self) -> None:
        assert lifecycle.request_run_cancel("")["outcome"] == "unavailable"

    def test_terminal_manifest_short_circuits_without_channel_use(
        self,
    ) -> None:
        transport = _SyncTransport()
        verdict = lifecycle.request_run_cancel(
            "req-done", transport=transport, manifest_status="completed")
        assert verdict["outcome"] == "completed_before_cancel"
        assert transport.calls == []

    def test_timeout_status_still_attempts_cancel(self) -> None:
        transport = _SyncTransport()
        verdict = lifecycle.request_run_cancel(
            "req-t", transport=transport, manifest_status="timeout")
        assert verdict["outcome"] == "pending"
        assert transport.calls == [("req-t", "")]

    def test_cancel_message_matches_transport_primitive(self) -> None:
        assert lifecycle.build_cancel_message("req-1", "r") == {
            "type": "cancel", "partition": "req-1", "reason": "r"}

    def test_control_queue_name_default_and_override(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("COMFYMODAL_V2_CONTROL_QUEUE", raising=False)
        assert lifecycle.control_queue_name() == "comfymodal-v2-control"
        assert lifecycle.control_queue_name({}) == "comfymodal-v2-control"
        assert lifecycle.control_queue_name(
            {"COMFYMODAL_V2_CONTROL_QUEUE": "custom-q"}) == "custom-q"

    def test_module_has_no_app_wide_stop_or_delete_path(self) -> None:
        source = RUN_LIFECYCLE_PATH.read_text(encoding="utf-8")
        assert '"app", "stop"' not in source
        assert '"app", "delete"' not in source
        assert "FunctionCall" not in source
        assert "subprocess" not in source

    def test_dry_run_plan_is_pure_and_run_scoped(self) -> None:
        plan = lifecycle.describe_cancel_plan(
            "req-plan-1", reason="supervisor_timeout",
            manifest_status="running", queue_name="comfymodal-v2-control")
        assert plan["request_id"] == "req-plan-1"
        assert plan["partition"] == "req-plan-1"
        assert json.loads(plan["message"]) == {
            "type": "cancel", "partition": "req-plan-1",
            "reason": "supervisor_timeout"}
        assert "stop" in plan["never"] and "delete" in plan["never"]


# ---------------------------------------------------------------------------
# Compiler-cache metadata snapshots on fake trees
# ---------------------------------------------------------------------------


def _make_cache_tree(root: Path, namespace: str,
                     files: dict[str, tuple[bytes, float]]) -> Path:
    base = root / namespace
    for rel, (data, mtime) in files.items():
        target = base / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        os.utime(target, (mtime, mtime))
    return base


class TestCacheMetadataSnapshot:
    def test_snapshot_counts_sizes_and_latest_mtime(self, tmp_path: Path) -> None:
        _make_cache_tree(tmp_path, "ns1", {
            "inductor/a.bin": (b"0123456789", 1700000001.0),
            "inductor/sub/b.bin": (b"01234567890123456789", 1700000003.0),
            "triton/c.bin": (b"12345", 1700000002.0),
        })
        snap = compiler_cache.snapshot_cache_metadata("ns1", root=str(tmp_path))
        assert snap["namespace"] == "ns1"
        assert snap["namespace_exists"] is True
        assert snap["scanned_ok"] is True
        assert snap["artifact_count"] == 3
        assert snap["total_bytes"] == 35
        assert snap["latest_mtime"] == 1700000003.0
        assert snap["dirs"]["inductor_dir"].endswith("inductor")
        assert snap["dirs"]["triton_dir"].endswith("triton")

    def test_snapshot_missing_namespace_degrades_to_zeros(
        self, tmp_path: Path
    ) -> None:
        snap = compiler_cache.snapshot_cache_metadata("absent", root=str(tmp_path))
        assert snap["namespace_exists"] is False
        assert snap["scanned_ok"] is False
        assert snap["artifact_count"] == 0
        assert snap["total_bytes"] == 0
        assert snap["latest_mtime"] == 0.0

    def test_snapshot_rejects_empty_namespace(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError):
            compiler_cache.snapshot_cache_metadata("", root=str(tmp_path))

    def test_snapshot_skips_symlinks(self, tmp_path: Path) -> None:
        _make_cache_tree(tmp_path, "ns2", {
            "inductor/real.bin": (b"0123456789", 1700000001.0),
        })
        link = tmp_path / "ns2" / "inductor" / "link.bin"
        try:
            os.symlink(tmp_path / "ns2" / "inductor" / "real.bin", link)
        except OSError:
            pytest.skip("symlinks unavailable in this environment")
        snap = compiler_cache.snapshot_cache_metadata("ns2", root=str(tmp_path))
        assert snap["artifact_count"] == 1
        assert snap["total_bytes"] == 10

    def test_diff_reports_deltas(self, tmp_path: Path) -> None:
        _make_cache_tree(tmp_path, "ns3", {
            "inductor/a.bin": (b"0123456789", 1700000001.0),
        })
        before = compiler_cache.snapshot_cache_metadata("ns3", root=str(tmp_path))
        _make_cache_tree(tmp_path, "ns3", {
            "triton/b.bin": (b"01234567890123456789", 1700000005.0),
        })
        after = compiler_cache.snapshot_cache_metadata("ns3", root=str(tmp_path))
        diff = compiler_cache.diff_cache_snapshots(before, after)
        assert diff["comparable"] is True
        assert diff["namespace"] == "ns3"
        assert diff["artifact_delta"] == 1
        assert diff["total_bytes_delta"] == 20
        assert diff["mtime_advanced"] is True

    def test_diff_rejects_mismatched_and_bad_inputs(self) -> None:
        good = {"namespace": "a", "artifact_count": 1, "total_bytes": 10,
                "latest_mtime": 5.0}
        other = dict(good, namespace="b")
        assert compiler_cache.diff_cache_snapshots(good, other)[  # noqa: E501
            "comparable"] is False
        assert compiler_cache.diff_cache_snapshots(None, good)[
            "comparable"] is False
        assert compiler_cache.diff_cache_snapshots(good, "nope")[  # type: ignore[arg-type]
            "comparable"] is False
        same = compiler_cache.diff_cache_snapshots(good, dict(good))
        assert same["comparable"] is True
        assert same["artifact_delta"] == 0
        assert same["mtime_advanced"] is False
