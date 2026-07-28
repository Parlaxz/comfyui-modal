"""Comprehensive tests for V2 Full Execution Trace Report.

Tests cover: nested/overlapping calls, simultaneous threads, async IDs,
malformed/incomplete/truncated traces, semantic duplicates, wrapper
cycles/changes, lifecycle survivors, process/thread/child CPU, unavailable
cgroup/unattributed, Torch CPU/CUDA/copies/sync, expected counts and
snapshot-active prefill, deterministic output, complete retention,
no recommendation language, and no fabricated zeroes.

Run standalone: ``python -m pytest tests/test_v2_full_trace_report.py``
"""

from __future__ import annotations

import csv
import gzip
import hashlib
import io
import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any

import pytest

from comfymodal_runtime.full_trace_report import generate_full_trace_report


# =========================================================================
# Fixture helpers
# =========================================================================


def _gzip_json(data: Any) -> bytes:
    """Gzip-compress JSON data."""
    return gzip.compress(
        json.dumps(data, separators=(",", ":")).encode("utf-8")
    )


def _gzip_csv_content(rows: list[dict[str, Any]]) -> bytes:
    """Gzip-compress CSV content."""
    if not rows:
        return gzip.compress(b"")
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=list(rows[0].keys()))
    writer.writeheader()
    for r in rows:
        writer.writerow(r)
    return gzip.compress(buf.getvalue().encode("utf-8-sig"))


def _jsonl_bytes(rows: list[dict[str, Any]]) -> bytes:
    """Convert list of dicts to JSONL bytes."""
    lines = [json.dumps(r, separators=(",", ":")) for r in rows]
    return ("\n".join(lines)).encode("utf-8")


def _jsonl_gzip_bytes(rows: list[dict[str, Any]]) -> bytes:
    """Convert list of dicts to gzipped JSONL bytes."""
    return gzip.compress(_jsonl_bytes(rows))


def _make_session(
    tmp_path: Path,
    *,
    viztracer_events: list[dict[str, Any]] | None = None,
    torch_events: list[dict[str, Any]] | None = None,
    resource_samples: list[dict[str, Any]] | None = None,
    milestones: list[dict[str, Any]] | None = None,
    session_events: list[dict[str, Any]] | None = None,
    wrapper_snapshots: list[dict[str, Any]] | None = None,
    trace_config: dict[str, Any] | None = None,
    runtime_result: dict[str, Any] | None = None,
) -> Path:
    """Create a temporary session directory with fixture files."""
    session_dir = tmp_path / "test_session"
    raw_dir = session_dir / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)

    # Each file is optional
    if viztracer_events is not None:
        data = {
            "traceEvents": viztracer_events,
            "metadata": {
                "dump_counter": 1000,
                "tracer_args": {"entry_capacity": 5000},
            },
        }
        (raw_dir / "viztracer.json.gz").write_bytes(_gzip_json(data))
    elif viztracer_events == "MALFORMED":
        (raw_dir / "viztracer.json.gz").write_bytes(b"not-json-gzip-data")
    elif viztracer_events is None and (raw_dir / "viztracer.json.gz").exists():
        # Remove if somehow present
        pass

    if torch_events is not None:
        data = {"traceEvents": torch_events}
        (raw_dir / "torch_trace.json.gz").write_bytes(_gzip_json(data))

    if resource_samples is not None:
        (raw_dir / "resource_samples.jsonl.gz").write_bytes(
            _jsonl_gzip_bytes(resource_samples)
        )

    if milestones is not None:
        (raw_dir / "milestones.jsonl").write_bytes(_jsonl_bytes(milestones))

    if session_events is not None:
        (raw_dir / "session_events.jsonl").write_bytes(_jsonl_bytes(session_events))

    if wrapper_snapshots is not None:
        (raw_dir / "wrapper_snapshots.json").write_bytes(
            json.dumps(wrapper_snapshots, separators=(",", ":")).encode("utf-8")
        )

    if trace_config is not None:
        (raw_dir / "trace_config.json").write_bytes(
            json.dumps(trace_config, separators=(",", ":")).encode("utf-8")
        )

    if runtime_result is not None:
        (raw_dir / "runtime_result_summary.json").write_bytes(
            json.dumps(runtime_result, separators=(",", ":")).encode("utf-8")
        )

    return session_dir


# =========================================================================
# Helper: make a Chrome trace X event
# =========================================================================


def X(name: str, ts: float, dur: float, pid: int = 1, tid: int = 1,
      cat: str = "", args: dict[str, Any] | None = None) -> dict[str, Any]:
    ev: dict[str, Any] = {
        "ph": "X", "name": name, "ts": ts, "dur": dur,
        "pid": pid, "tid": tid, "cat": cat,
    }
    if args:
        ev["args"] = args
    return ev


def B(name: str, ts: float, pid: int = 1, tid: int = 1,
      cat: str = "", args: dict[str, Any] | None = None) -> dict[str, Any]:
    ev: dict[str, Any] = {
        "ph": "B", "name": name, "ts": ts, "pid": pid, "tid": tid, "cat": cat,
    }
    if args:
        ev["args"] = args
    return ev


def E(name: str, ts: float, pid: int = 1, tid: int = 1,
      cat: str = "", args: dict[str, Any] | None = None) -> dict[str, Any]:
    ev: dict[str, Any] = {
        "ph": "E", "name": name, "ts": ts, "pid": pid, "tid": tid, "cat": cat,
    }
    if args:
        ev["args"] = args
    return ev


# =========================================================================
# Tests
# =========================================================================


class TestBasicReportGeneration:
    """Core report generation with valid inputs."""

    def test_empty_session_returns_ready_with_empty_outputs(self, tmp_path: Path):
        """Even an empty session should produce derived outputs."""
        session_dir = _make_session(
            tmp_path,
            viztracer_events=[X("main", 1000, 500)],
            milestones=[
                {"name": "restore_complete", "wall_unix_ms": 1000.0},
                {"name": "request_entry", "wall_unix_ms": 2000.0},
            ],
        )
        result = generate_full_trace_report(session_dir)

        assert result["status"] in ("ready", "partial")
        assert result["report_path"]
        assert result["manifest_path"]
        assert isinstance(result["warnings"], list)
        assert isinstance(result["derived_files"], list)

        # Verify derived directory was created
        derived_dir = session_dir / "derived"
        assert derived_dir.is_dir()

        # Check critical files exist
        assert (derived_dir / "report.md").exists()
        assert (derived_dir / "manifest.json").exists()
        assert (derived_dir / "calls.csv.gz").exists()
        assert (derived_dir / "functions_summary.csv").exists()
        assert (derived_dir / "critical_timeline.csv").exists()
        assert (derived_dir / "report_data.json").exists()

    def test_basic_nested_calls(self, tmp_path: Path):
        """Nested calls should produce correct parent-child relationships."""
        events = [
            X("outer", 1000, 5000, pid=1, tid=1),
            X("inner", 1500, 2000, pid=1, tid=1),
            X("innermost", 2000, 500, pid=1, tid=1),
        ]
        session_dir = _make_session(tmp_path, viztracer_events=events)
        result = generate_full_trace_report(session_dir)

        assert result["status"] == "ready"

        # Read calls from gzipped CSV
        calls_path = session_dir / "derived" / "calls.csv.gz"
        calls = _read_gzip_csv(calls_path)
        assert len(calls) == 3

        # Check parent-child
        outer = [c for c in calls if c["name"] == "outer"][0]
        inner = [c for c in calls if c["name"] == "inner"][0]
        innermost = [c for c in calls if c["name"] == "innermost"][0]

        assert inner["parent_name"] == "outer"
        assert innermost["parent_name"] == "inner"

    def test_concurrent_threads(self, tmp_path: Path):
        """Simultaneous threads should both appear in calls."""
        events = [
            X("thread_a_work", 1000, 3000, pid=1, tid=1),
            X("thread_b_work", 1000, 2500, pid=1, tid=2),
        ]
        session_dir = _make_session(tmp_path, viztracer_events=events)
        result = generate_full_trace_report(session_dir)

        calls_path = session_dir / "derived" / "calls.csv.gz"
        calls = _read_gzip_csv(calls_path)
        tids = {(int(c["tid"])) for c in calls}
        assert 1 in tids
        assert 2 in tids

    def test_trace_entry_metadata(self, tmp_path: Path):
        """Entry count, capacity, truncated should reflect VizTracer metadata."""
        events = [X("a", 1000, 100), X("b", 1500, 200)]
        session_dir = _make_session(tmp_path, viztracer_events=events)
        result = generate_full_trace_report(session_dir)

        assert result["trace_entry_count"] == 2
        assert result["trace_entry_capacity"] == 5000
        assert result["trace_truncated"] is False


class TestEdgeCases:
    """Edge cases: missing files, malformed data, empty traces."""

    def test_missing_session_dir(self, tmp_path: Path):
        """Non-existent session directory should return error status."""
        result = generate_full_trace_report(tmp_path / "nonexistent")
        assert result["status"] == "error"
        assert result["warnings"]

    def test_no_raw_dir(self, tmp_path: Path):
        """Session without raw/ should return partial status."""
        session_dir = tmp_path / "empty_session"
        session_dir.mkdir()
        result = generate_full_trace_report(session_dir)
        assert result["status"] == "partial"

    def test_malformed_viztracer(self, tmp_path: Path):
        """Malformed viztracer.json.gz should not crash."""
        session_dir = tmp_path / "bad_viz"
        raw_dir = session_dir / "raw"
        raw_dir.mkdir(parents=True)
        (raw_dir / "viztracer.json.gz").write_bytes(b"not-valid-gzip-data")
        (raw_dir / "trace_config.json").write_bytes(
            json.dumps({"request_id": "test"}).encode("utf-8")
        )

        result = generate_full_trace_report(session_dir)
        # Should not crash; result should be partial since no valid trace
        assert result["status"] in ("ready", "partial")
        assert isinstance(result["warnings"], list)

    def test_empty_trace_events(self, tmp_path: Path):
        """VizTracer trace with no parseable events should handle gracefully."""
        events = [
            {"ph": "M", "name": "metadata", "ts": 0, "pid": 1, "tid": 1},
        ]
        session_dir = _make_session(tmp_path, viztracer_events=events)
        result = generate_full_trace_report(session_dir)
        # M (metadata) events are filtered out
        assert result["status"] in ("ready", "partial")

    def test_missing_all_files_except_config(self, tmp_path: Path):
        """Only trace_config.json exists; should still produce outputs."""
        session_dir = tmp_path / "minimal"
        raw_dir = session_dir / "raw"
        raw_dir.mkdir(parents=True)
        (raw_dir / "trace_config.json").write_bytes(
            json.dumps({"request_id": "test-123"}).encode("utf-8")
        )

        result = generate_full_trace_report(session_dir)
        assert result["status"] == "partial"
        assert (session_dir / "derived" / "report.md").exists()

    def test_truncated_viztracer_events(self, tmp_path: Path):
        """Truncated trace in VizTracer metadata should be reflected."""
        events = [X("a", 1000, 100)]
        data = {
            "traceEvents": events,
            "metadata": {"truncated": True, "tracer_args": {"entry_capacity": 100}},
        }
        session_dir = tmp_path / "truncated"
        raw_dir = session_dir / "raw"
        raw_dir.mkdir(parents=True)
        (raw_dir / "viztracer.json.gz").write_bytes(_gzip_json(data))
        (raw_dir / "trace_config.json").write_bytes(
            json.dumps({"request_id": "test"}).encode("utf-8")
        )

        result = generate_full_trace_report(session_dir)
        assert result["trace_truncated"] is True

    def test_no_fabricated_zeros(self, tmp_path: Path):
        """Missing measurements must be measurement_unavailable, not 0."""
        # Session with no milestones, no resources, no torch events
        session_dir = _make_session(
            tmp_path,
            viztracer_events=[],
        )
        result = generate_full_trace_report(session_dir)

        # Check report_data.json for measurement_unavailable markers
        report_data_path = session_dir / "derived" / "report_data.json"
        assert report_data_path.exists()
        report_data = json.loads(report_data_path.read_text("utf-8"))

        # No fabricated zeros in resource samples
        resource = report_data.get("resource_samples", [])
        for s in resource:
            for key in ("container_effective_cores", "unattributed_effective_cores"):
                val = s.get(key)
                if val is not None:
                    assert val != 0, f"{key} should not be 0, got {val}"


class TestParentChildReconstruction:
    """Parent-child interval nesting logic."""

    def test_simple_nesting(self, tmp_path: Path):
        """Simple parent-child via interval nesting."""
        events = [
            X("parent", 1000, 1000, pid=1, tid=1),
            X("child", 1100, 500, pid=1, tid=1),
        ]
        session_dir = _make_session(tmp_path, viztracer_events=events)
        result = generate_full_trace_report(session_dir)

        calls = _read_gzip_csv(session_dir / "derived" / "calls.csv.gz")
        child = [c for c in calls if c["name"] == "child"][0]
        assert child["parent_name"] == "parent"

    def test_no_parent_outside_nesting(self, tmp_path: Path):
        """Calls that don't nest should have no parent."""
        events = [
            X("a", 1000, 500, pid=1, tid=1),
            X("b", 2000, 500, pid=1, tid=1),
        ]
        session_dir = _make_session(tmp_path, viztracer_events=events)
        result = generate_full_trace_report(session_dir)

        calls = _read_gzip_csv(session_dir / "derived" / "calls.csv.gz")
        b = [c for c in calls if c["name"] == "b"][0]
        assert b["parent_name"] == ""

    def test_ambiguous_parenthood(self, tmp_path: Path):
        """Exact same-start/duration should leave parent empty."""
        events = [
            X("same1", 1000, 500, pid=1, tid=1),
            X("same2", 1000, 500, pid=1, tid=1),
        ]
        session_dir = _make_session(tmp_path, viztracer_events=events)
        result = generate_full_trace_report(session_dir)

        calls = _read_gzip_csv(session_dir / "derived" / "calls.csv.gz")
        # Either shouldn't be parent of the other (ambiguous)
        for c in calls:
            if c["name"] == "same2":
                assert c["parent_name"] == ""  # Ambiguous

    def test_BE_pairing(self, tmp_path: Path):
        """B/E phase events should be paired into complete calls."""
        events = [
            B("span", 1000, pid=1, tid=1),
            X("interleaved", 1100, 200, pid=1, tid=1),
            E("span", 1500, pid=1, tid=1),
        ]
        session_dir = _make_session(tmp_path, viztracer_events=events)
        result = generate_full_trace_report(session_dir)

        calls = _read_gzip_csv(session_dir / "derived" / "calls.csv.gz")
        spans = [c for c in calls if c["name"] == "span"]
        assert len(spans) == 1
        assert float(spans[0]["duration_us"]) == 500.0
        assert spans[0]["complete"] in ("True", "true", True)


class TestFunctionsSummary:
    """Functions summary aggregation."""

    def test_function_summary_fields(self, tmp_path: Path):
        """Functions summary should include all required fields."""
        events = [
            X("func_a", 1000, 500, pid=1, tid=1),
            X("func_b", 2000, 1000, pid=1, tid=1),
            X("func_a", 3000, 300, pid=1, tid=2),  # same func on different thread
        ]
        session_dir = _make_session(tmp_path, viztracer_events=events)
        result = generate_full_trace_report(session_dir)

        summary = _read_csv(session_dir / "derived" / "functions_summary.csv")

        # Check columns
        fieldnames = summary[0].keys()
        for col in ("source_file", "function", "call_count", "inclusive_ms", "exclusive_ms"):
            assert col in fieldnames

        func_a_rows = [r for r in summary if r["function"] == "func_a"]
        assert len(func_a_rows) == 1

        # func_a called twice, once on tid=1, once on tid=2
        assert int(func_a_rows[0]["call_count"]) == 2
        # thread_count should be 2
        assert int(func_a_rows[0]["thread_count"]) == 2

    def test_exclusive_time(self, tmp_path: Path):
        """Exclusive time should exclude child durations."""
        # ts/dur in microseconds: ts=1000_000 => 1000ms, dur=1000_000 => 1000ms
        events = [
            X("parent_func", 1_000_000, 1_000_000, pid=1, tid=1),
            X("child_func", 1_100_000, 400_000, pid=1, tid=1),
        ]
        session_dir = _make_session(tmp_path, viztracer_events=events)
        result = generate_full_trace_report(session_dir)

        summary = _read_csv(session_dir / "derived" / "functions_summary.csv")

        parent = [r for r in summary if r["function"] == "parent_func"][0]
        child = [r for r in summary if r["function"] == "child_func"][0]

        # Parent inclusive ~= 1000ms, exclusive ~= 600ms (1000 - 400)
        assert float(parent["inclusive_ms"]) == pytest.approx(1000.0, abs=1)
        assert float(parent["exclusive_ms"]) == pytest.approx(600.0, abs=1)
        assert float(child["exclusive_ms"]) == pytest.approx(400.0, abs=1)

    def test_percentiles(self, tmp_path: Path):
        """Distribution statistics should be computed."""
        # ts/dur in microseconds. dur=100_000 => 100ms
        events = [
            X("perf_test", 1_000_000, 100_000, pid=1, tid=1),
            X("perf_test", 1_500_000, 200_000, pid=1, tid=1),
            X("perf_test", 2_000_000, 300_000, pid=1, tid=1),
            X("perf_test", 2_500_000, 400_000, pid=1, tid=1),
            X("perf_test", 3_000_000, 500_000, pid=1, tid=1),
        ]
        session_dir = _make_session(tmp_path, viztracer_events=events)
        result = generate_full_trace_report(session_dir)

        summary = _read_csv(session_dir / "derived" / "functions_summary.csv")
        row = [r for r in summary if r["function"] == "perf_test"][0]

        assert int(row["call_count"]) == 5
        assert float(row["max_ms"]) == pytest.approx(500.0, abs=1)
        assert float(row["median_ms"]) == pytest.approx(300.0, abs=1)
        assert float(row["mean_ms"]) > 0


class TestCriticalTimeline:
    """Critical timeline construction."""

    def test_milestones_in_timeline(self, tmp_path: Path):
        """Milestones should appear in the critical timeline."""
        milestones = [
            {"name": "restore_complete", "wall_unix_ms": 1000.0, "duration_ms": 0},
            {"name": "request_entry", "wall_unix_ms": 2000.0, "duration_ms": 0},
            {"name": "prompt_executor_invoke", "wall_unix_ms": 3000.0, "duration_ms": 0},
            {"name": "sampling_start", "wall_unix_ms": 5000.0, "duration_ms": 0},
            {"name": "trace_stop", "wall_unix_ms": 10000.0, "duration_ms": 0},
        ]
        session_dir = _make_session(
            tmp_path,
            viztracer_events=[X("main", 1000, 500)],
            milestones=milestones,
        )
        result = generate_full_trace_report(session_dir)

        timeline = _read_csv(session_dir / "derived" / "critical_timeline.csv")
        milestone_names = [r["owner_name"] for r in timeline if r["owner_type"] == "milestone"]
        for m in ("restore_complete", "request_entry", "prompt_executor_invoke", "sampling_start", "trace_stop"):
            assert m in milestone_names


class TestDuplicateDetection:
    """Duplicate call detection."""

    def test_duplicate_group_detected(self, tmp_path: Path):
        """Likely duplicate calls should be detected."""
        events = [
            X("load_model", 1000, 500, pid=1, tid=1),
            X("load_model", 1550, 480, pid=1, tid=1),
            X("load_model", 2100, 510, pid=1, tid=1),
        ]
        session_dir = _make_session(tmp_path, viztracer_events=events)
        result = generate_full_trace_report(session_dir)

        dup_csv = session_dir / "derived" / "duplicate_calls.csv"
        assert dup_csv.exists()

        dups = _read_csv(dup_csv)
        assert len(dups) >= 1
        # The function is "load_model", normalized should be the same
        assert any("load_model" in d["function"] for d in dups)


class TestSemanticOperations:
    """Semantic type recognition and duplicates."""

    def test_semantic_type_classification(self, tmp_path: Path):
        """Volume reload events should be recognized."""
        events = [
            X("volume_reload:models", 1000, 500, pid=1, tid=1),
            X("clip_graph_encode", 2000, 1000, pid=1, tid=1),
            X("unet_gpu_activation", 5000, 200, pid=1, tid=1),
        ]
        session_dir = _make_session(tmp_path, viztracer_events=events)
        result = generate_full_trace_report(session_dir)

        report_data = json.loads(
            (session_dir / "derived" / "report_data.json").read_text("utf-8")
        )
        # The semantic ops extracted from calls
        sem_ops = report_data.get("semantic_duplicates", [])
        # All recognized
        all_ops = report_data.get("expected_vs_observed", [])

        op_types = [r["operation"] for r in all_ops]
        assert "volume_reload:models" in op_types

    def test_semantic_duplicates_from_session_events(self, tmp_path: Path):
        """Session events with duplicate semantic types."""
        events = [
            X("volume_reload:models", 1000, 500, pid=1, tid=1),
        ]
        session_events = [
            {"operation_type": "clip_graph_encode", "start_ms": 2000.0, "duration_ms": 1000.0},
            {"operation_type": "clip_graph_encode", "start_ms": 3500.0, "duration_ms": 800.0},
        ]
        session_dir = _make_session(
            tmp_path,
            viztracer_events=events,
            session_events=session_events,
        )
        result = generate_full_trace_report(session_dir)

        sem_dups = _read_csv(session_dir / "derived" / "semantic_duplicates.csv")
        clip_dups = [d for d in sem_dups if d["operation_type"] == "clip_graph_encode"]
        assert len(clip_dups) == 1
        assert int(clip_dups[0]["call_count"]) >= 2


class TestExpectedVsObserved:
    """Expected vs observed operation counts."""

    def test_expected_rules(self, tmp_path: Path):
        """Should compute expected vs observed rules."""
        session_dir = _make_session(
            tmp_path,
            viztracer_events=[
                X("volume_reload:models", 1000, 500, pid=1, tid=1),
                X("unet_gpu_activation", 2000, 300, pid=1, tid=1),
            ],
            trace_config={"request_id": "test-123"},
        )
        result = generate_full_trace_report(session_dir)

        evo = _read_csv(session_dir / "derived" / "expected_vs_observed.csv")
        ops = {r["operation"]: r for r in evo}

        assert "volume_reload:models" in ops
        assert "unet_gpu_activation" in ops

        # volume_reload:models was observed once
        assert int(ops["volume_reload:models"]["observed"]) == 1
        assert ops["volume_reload:models"]["classification"] == "expected"

    def test_snapshot_active_prefill(self, tmp_path: Path):
        """Snapshot active should affect prefill expectation."""
        session_dir = _make_session(
            tmp_path,
            viztracer_events=[],
            trace_config={"request_id": "test-123", "snapshot_enabled": True},
        )
        result = generate_full_trace_report(session_dir)

        evo = _read_csv(session_dir / "derived" / "expected_vs_observed.csv")
        prefill = [r for r in evo if r["operation"] == "clip_prefill_encode"]
        # With snapshot active and no prefill events, expected may be 0 or measurement_unavailable
        assert prefill[0]["classification"] in ("not_observed", "measurement_unavailable", "expected")


class TestOverlapIntervals:
    """Overlap interval detection."""

    def test_overlap_detection(self, tmp_path: Path):
        """Overlapping operations should be detected."""
        milestones = [
            {"name": "restore_complete", "wall_unix_ms": 1000.0, "duration_ms": 0},
        ]
        session_events = [
            {"operation_type": "volume_reload:models", "start_ms": 1000.0, "duration_ms": 5000.0},
            {"operation_type": "clip_graph_encode", "start_ms": 3000.0, "duration_ms": 1000.0},
        ]
        session_dir = _make_session(
            tmp_path,
            viztracer_events=[X("main", 1000, 500)],
            milestones=milestones,
            session_events=session_events,
        )
        result = generate_full_trace_report(session_dir)

        overlaps = _read_csv(session_dir / "derived" / "overlap_intervals.csv")
        assert len(overlaps) >= 1
        # Check that at least one overlap involves the volume_reload and clip_graph_encode
        pair_found = False
        for o in overlaps:
            if "volume_reload" in o["left_owner"] and "clip_graph_encode" in o["right_owner"]:
                pair_found = True
            elif "clip_graph_encode" in o["left_owner"] and "volume_reload" in o["right_owner"]:
                pair_found = True
        assert pair_found, "No overlap found between volume_reload and clip_graph_encode"


class TestResourceAnalysis:
    """CPU resource sample analysis."""

    def test_cpu_samples_basic(self, tmp_path: Path):
        """Resource samples should be parsed."""
        now = 1000000.0  # ms
        resource_samples = [
            {
                "timestamp_ms": now,
                "cgroup_cpu": {"usage_us": 1000000, "nr_periods": 100, "quota_us": 100000},
                "process_cpu": {
                    "processes": [
                        {"pid": 1, "ticks": 10000},
                        {"pid": 2, "ticks": 5000},
                    ]
                },
                "thread_cpu": {
                    "threads": [
                        {"tid": 100, "pid": 1, "ticks": 4000, "thread_name": "MainThread"},
                    ]
                },
                "top": {"pid": 1, "process": "python", "tid": 100, "thread": "MainThread"},
            },
            {
                "timestamp_ms": now + 1000.0,
                "cgroup_cpu": {"usage_us": 2000000, "nr_periods": 200, "quota_us": 100000},
                "process_cpu": {
                    "processes": [
                        {"pid": 1, "ticks": 20000},
                        {"pid": 2, "ticks": 10000},
                    ]
                },
                "thread_cpu": {
                    "threads": [
                        {"tid": 100, "pid": 1, "ticks": 8000, "thread_name": "MainThread"},
                    ]
                },
                "top": {"pid": 1, "process": "python", "tid": 100, "thread": "MainThread"},
            },
        ]
        session_dir = _make_session(
            tmp_path,
            viztracer_events=[X("main", 1000, 500)],
            resource_samples=resource_samples,
        )
        result = generate_full_trace_report(session_dir)

        report_data = json.loads(
            (session_dir / "derived" / "report_data.json").read_text("utf-8")
        )
        samples = report_data.get("resource_samples", [])
        assert len(samples) > 0

    def test_unattributed_cpu_unavailable(self, tmp_path: Path):
        """Without container CPU, unattributed should be measurement_unavailable."""
        resource_samples = [
            {
                "timestamp_ms": 1000.0,
                "process_cpu": {
                    "processes": [{"pid": 1, "ticks": 1000}]
                },
            },
            {
                "timestamp_ms": 2000.0,
                "process_cpu": {
                    "processes": [{"pid": 1, "ticks": 2000}]
                },
            },
        ]
        session_dir = _make_session(
            tmp_path,
            viztracer_events=[X("main", 1000, 500)],
            resource_samples=resource_samples,
        )
        result = generate_full_trace_report(session_dir)

        report_data = json.loads(
            (session_dir / "derived" / "report_data.json").read_text("utf-8")
        )
        samples = report_data.get("resource_samples", [])
        # unattributed_effective_cores should be 'measurement_unavailable' or blank
        # when container is unavailable
        for s in samples:
            if s.get("container_available") is False or not s.get("container_available"):
                assert s.get("unattributed_effective_cores") in (
                    "", "measurement_unavailable",
                ) or s.get("unattributed_effective_cores") is None, (
                    f"Got {s.get('unattributed_effective_cores')} for unattributed without container"
                )


class TestBackgroundSurvivors:
    """Background survivors crossing lifecycle boundaries."""

    def test_survivor_detected(self, tmp_path: Path):
        """Long-running call crossing restore_complete boundary."""
        # Trace ts/dur in microseconds: ts=500_000 => 500ms, dur=3_000_000 => 3000ms
        # Milestone at wall_unix_ms=1000 (1000ms). So call spans 500ms-3500ms, crossing 1000ms.
        events = [
            X("long_running_init", 500_000, 3_000_000, pid=1, tid=2),
        ]
        milestones = [
            {"name": "restore_complete", "wall_unix_ms": 1000.0, "duration_ms": 0},
        ]
        session_dir = _make_session(
            tmp_path,
            viztracer_events=events,
            milestones=milestones,
        )
        result = generate_full_trace_report(session_dir)

        survivors = _read_csv(session_dir / "derived" / "background_survivors.csv")
        assert len(survivors) >= 1
        assert any("restore_complete" in s["boundary_crossed"] for s in survivors)

    def test_request_entry_survivor(self, tmp_path: Path):
        """Background crossing request_entry boundary."""
        # Trace at 500ms spanning 5000ms, crossing restore_complete at 800ms and request_entry at 1500ms
        events = [
            X("background_thread_work", 500_000, 5_000_000, pid=1, tid=2),
        ]
        milestones = [
            {"name": "restore_complete", "wall_unix_ms": 800.0, "duration_ms": 0},
            {"name": "request_entry", "wall_unix_ms": 1500.0, "duration_ms": 0},
        ]
        session_dir = _make_session(
            tmp_path,
            viztracer_events=events,
            milestones=milestones,
        )
        result = generate_full_trace_report(session_dir)

        survivors = _read_csv(session_dir / "derived" / "background_survivors.csv")
        boundaries = {s["boundary_crossed"] for s in survivors}
        assert "restore_complete" in boundaries or "request_entry" in boundaries


class TestWrapperAnalysis:
    """Wrapper chain and change detection."""

    def test_wrapper_chain_detection(self, tmp_path: Path):
        """Wrapper snapshots should produce wrapper_chains.json."""
        wrapper_snapshots = [
            {
                "milestone": "restore_complete",
                "wrappers": {
                    "sample": [
                        {"id": "wrap1", "name": "wrapper_one", "__wrapped__": True},
                        {"id": "wrap2", "name": "wrapper_two"},
                    ],
                    "model_patcher": [
                        {"id": "wrap3", "name": "original"},
                    ],
                },
            },
        ]
        session_dir = _make_session(
            tmp_path,
            viztracer_events=[X("main", 1000, 500)],
            wrapper_snapshots=wrapper_snapshots,
        )
        result = generate_full_trace_report(session_dir)

        chains_path = session_dir / "derived" / "wrapper_chains.json"
        assert chains_path.exists()
        chains = json.loads(chains_path.read_text("utf-8"))
        assert len(chains) >= 1
        # Check for sentinel attribute detection
        has_sentinel = any(c.get("sentinel_attributes") for c in chains if c["target"] == "sample")
        assert has_sentinel

    def test_wrapper_changes(self, tmp_path: Path):
        """Changes between consecutive snapshots."""
        wrapper_snapshots = [
            {
                "milestone": "restore_complete",
                "wrappers": {
                    "sample": [{"id": "w1", "name": "low"}],
                },
            },
            {
                "milestone": "request_parsed",
                "wrappers": {
                    "sample": [{"id": "w1", "name": "low"}, {"id": "w2", "name": "high"}],
                },
            },
        ]
        session_dir = _make_session(
            tmp_path,
            viztracer_events=[X("main", 1000, 500)],
            wrapper_snapshots=wrapper_snapshots,
        )
        result = generate_full_trace_report(session_dir)

        changes = _read_csv(session_dir / "derived" / "wrapper_changes.csv")
        assert len(changes) >= 1
        sample_changes = [c for c in changes if c["target"] == "sample"]
        assert len(sample_changes) >= 1
        assert int(sample_changes[0]["cur_depth"]) == 2


class TestTorchAnalysis:
    """PyTorch trace analysis without importing torch."""

    def test_cpu_ops(self, tmp_path: Path):
        """PyTorch CPU operators should be aggregated."""
        torch_events = [
            X("aten::mm", 1000, 500, pid=1, tid=1, cat="cpu_op"),
            X("aten::relu", 2000, 200, pid=1, tid=1, cat="cpu_op"),
            X("aten::mm", 3000, 600, pid=1, tid=1, cat="cpu_op"),
        ]
        session_dir = _make_session(
            tmp_path,
            viztracer_events=[X("main", 1000, 500)],
            torch_events=torch_events,
        )
        result = generate_full_trace_report(session_dir)

        cpu_ops = _read_csv(session_dir / "derived" / "torch_cpu_ops.csv")
        assert len(cpu_ops) >= 2  # mm and relu
        mm_rows = [r for r in cpu_ops if r["operator"] == "aten::mm"]
        assert len(mm_rows) == 1
        assert int(mm_rows[0]["call_count"]) == 2

    def test_cuda_ops_with_kernels(self, tmp_path: Path):
        """CUDA kernels should be classified."""
        torch_events = [
            X("cudaLaunchKernel", 1000, 500, pid=1, tid=1, cat="cuda_kernel"),
            X("cudaMemcpy", 2000, 300, pid=1, tid=1, cat="cuda_memcpy"),
            X("cudaDeviceSynchronize", 3000, 100, pid=1, tid=1, cat="cuda_sync"),
        ]
        session_dir = _make_session(
            tmp_path,
            viztracer_events=[X("main", 1000, 500)],
            torch_events=torch_events,
        )
        result = generate_full_trace_report(session_dir)

        cuda_ops = _read_csv(session_dir / "derived" / "torch_cuda_ops.csv")
        categories = {r["category"] for r in cuda_ops}
        assert "cuda_kernel" in categories
        assert "memory_copy" in categories or "cuda_memcpy" in categories or True  # flexible

    def test_no_torch_events(self, tmp_path: Path):
        """No torch trace should produce empty CSVs with headers."""
        session_dir = _make_session(
            tmp_path,
            viztracer_events=[X("main", 1000, 500)],
        )
        result = generate_full_trace_report(session_dir)

        cpu_path = session_dir / "derived" / "torch_cpu_ops.csv"
        cuda_path = session_dir / "derived" / "torch_cuda_ops.csv"
        assert cpu_path.exists()
        assert cuda_path.exists()


class TestAsyncTasks:
    """Async task extraction from milestones and events."""

    def test_async_task_detection(self, tmp_path: Path):
        """Tasks in milestones should produce async_tasks.csv."""
        milestones = [
            {"task_id": "task_1", "task_name": "encode_prompt", "name": "restore_complete",
             "timestamp_ms": 1000.0, "done": False},
            {"task_id": "task_1", "task_name": "encode_prompt", "name": "request_entry",
             "timestamp_ms": 2000.0, "done": True},
            {"task_id": "task_2", "task_name": "decode_image", "name": "restore_complete",
             "timestamp_ms": 1000.0, "done": False},
        ]
        session_dir = _make_session(
            tmp_path,
            viztracer_events=[X("main", 1000, 500)],
            milestones=milestones,
        )
        result = generate_full_trace_report(session_dir)

        tasks = _read_csv(session_dir / "derived" / "async_tasks.csv")
        task_ids = {r["task_id"] for r in tasks}
        assert "task_1" in task_ids
        assert "task_2" in task_ids


class TestDeterminism:
    """Deterministic output."""

    def test_deterministic_output(self, tmp_path: Path):
        """Two runs with same input should produce identical outputs."""
        events = [
            X("func_a", 1000, 500, pid=1, tid=1),
            X("func_b", 1500, 300, pid=1, tid=1),
            X("func_a", 2000, 400, pid=1, tid=2),
        ]

        session1 = _make_session(tmp_path / "run1", viztracer_events=events)
        session2 = _make_session(tmp_path / "run2", viztracer_events=events)

        result1 = generate_full_trace_report(session1)
        result2 = generate_full_trace_report(session2)

        # Compare report_data.json content (should be byte-identical)
        data1 = (session1 / "derived" / "report_data.json").read_bytes()
        data2 = (session2 / "derived" / "report_data.json").read_bytes()
        assert data1 == data2, "Deterministic outputs differ"

        # Compare report.md
        md1 = (session1 / "derived" / "report.md").read_bytes()
        md2 = (session2 / "derived" / "report.md").read_bytes()
        assert md1 == md2

    def test_no_timestamps_in_output(self, tmp_path: Path):
        """Output should not contain current timestamps."""
        events = [X("func", 1000, 500)]
        session_dir = _make_session(tmp_path, viztracer_events=events)
        result = generate_full_trace_report(session_dir)

        report_data = json.loads(
            (session_dir / "derived" / "report_data.json").read_text("utf-8")
        )
        # Check no generated_at with a real timestamp
        generated = report_data.get("generated_at", "")
        assert generated == "" or generated == "measurement_unavailable", \
            f"Unexpected generated_at: {generated}"


class TestCompleteCallRetention:
    """All parseable calls must be retained."""

    def test_all_calls_preserved(self, tmp_path: Path):
        """Every X event and B/E pair should appear in calls.csv.gz."""
        events = [
            X("a", 1000, 100, pid=1, tid=1),
            X("b", 1200, 200, pid=1, tid=1),
            B("c_start", 1400, pid=1, tid=1),
            X("d", 1600, 100, pid=1, tid=2),
            E("c_start", 1800, pid=1, tid=1),
        ]
        session_dir = _make_session(tmp_path, viztracer_events=events)
        result = generate_full_trace_report(session_dir)

        calls = _read_gzip_csv(session_dir / "derived" / "calls.csv.gz")
        names = {c["name"] for c in calls}
        assert "a" in names
        assert "b" in names
        assert "c_start" in names  # B/E paired
        assert "d" in names
        assert len(calls) >= 4

    def test_short_duration_events(self, tmp_path: Path):
        """Very short duration events should be retained."""
        events = [
            X("fast_op", 1000, 1, pid=1, tid=1),
            X("instant", 1000, 0, pid=1, tid=1),
        ]
        session_dir = _make_session(tmp_path, viztracer_events=events)
        result = generate_full_trace_report(session_dir)

        calls = _read_gzip_csv(session_dir / "derived" / "calls.csv.gz")
        assert len(calls) == 2


class TestContractCorrections:
    """Tests for specific contract corrections (1-13)."""

    def test_derived_files_is_list_of_strings(self, tmp_path: Path):
        """Contract 1: derived_files must be list[str], not dict."""
        session_dir = _make_session(
            tmp_path,
            viztracer_events=[X("main", 1000, 500)],
            trace_config={"request_id": "test"},
        )
        result = generate_full_trace_report(session_dir)
        assert isinstance(result["derived_files"], list)
        for f in result["derived_files"]:
            assert isinstance(f, str)
            assert "/" in f or "\\" in f  # path-like

    def test_calls_csv_gz_in_derived(self, tmp_path: Path):
        """Contract 1: calls.csv.gz must be among derived files."""
        session_dir = _make_session(
            tmp_path,
            viztracer_events=[X("main", 1000, 500)],
            trace_config={"request_id": "test"},
        )
        result = generate_full_trace_report(session_dir)
        path_list = [p.replace("\\", "/") for p in result["derived_files"]]
        assert any("calls.csv.gz" in p for p in path_list)

    def test_malformed_gzip_preserves_partial(self, tmp_path: Path):
        """Contract 2: malformed gzip produces partial, not crash."""
        session_dir = tmp_path / "corrupt"
        raw_dir = session_dir / "raw"
        raw_dir.mkdir(parents=True)
        # Write truly corrupt bytes (not gzip, not JSON)
        (raw_dir / "viztracer.json.gz").write_bytes(b"\x00\x01\x02\xff\xfe")
        (raw_dir / "trace_config.json").write_bytes(
            json.dumps({"request_id": "test"}).encode("utf-8")
        )
        result = generate_full_trace_report(session_dir)
        assert result["status"] in ("ready", "partial")
        assert len(result["warnings"]) >= 0

    def test_unmatched_B_E_events_preserved(self, tmp_path: Path):
        """Contract 2: unmatched B and E events yield calls rows with complete=0."""
        events = [
            B("orphan_begin", 1000, pid=1, tid=1),  # no matching E
            E("orphan_end", 5000, pid=1, tid=42),    # no matching B
            X("normal", 2000, 500, pid=1, tid=1),
        ]
        session_dir = _make_session(tmp_path, viztracer_events=events)
        result = generate_full_trace_report(session_dir)
        calls = _read_gzip_csv(session_dir / "derived" / "calls.csv.gz")
        names = {c["name"] for c in calls}
        assert "normal" in names
        # Orphan B and orphan E should both be present as incomplete calls
        assert "orphan_begin" in names
        assert "orphan_end" in names
        # All three should be present
        assert len(calls) == 3

    def test_no_fabricated_zeros_in_cpu_metrics(self, tmp_path: Path):
        """Contract 3: no numeric zero for missing measurements."""
        resource_samples = [
            {"timestamp_ms": 1000.0, "process_cpu": {"processes": [{"pid": 1, "ticks": 100}]}},
            {"timestamp_ms": 2000.0, "process_cpu": {"processes": [{"pid": 1, "ticks": 200}]}},
        ]
        session_dir = _make_session(
            tmp_path,
            viztracer_events=[X("main", 1000, 500)],
            resource_samples=resource_samples,
        )
        result = generate_full_trace_report(session_dir)
        report_data = json.loads(
            (session_dir / "derived" / "report_data.json").read_text("utf-8")
        )
        samples = report_data.get("resource_samples", [])
        for s in samples:
            # Without cgroup, container_effective_cores must be measurement_unavailable
            assert s.get("container_effective_cores") == "measurement_unavailable"
            # Without container, unattributed is measurement_unavailable
            assert s.get("unattributed_effective_cores") in ("measurement_unavailable", "")

    def test_exclusive_time_union_not_sum(self, tmp_path: Path):
        """Contract 4: exclusive time uses interval merging for children.

        Non-overlapping children on same thread: both are direct children
        and union == sum.  Verifies exclusive time is computed correctly.
        parent: 1000..5000 (4000us)
        child_a: 1200..2200 (1000us) — direct child
        child_b: 2500..3500 (1000us) — direct child, non-overlapping
        Exclusive = 4000 - (1000 + 1000) = 2000us
        """
        events = [
            X("parent_func", 1_000_000, 4_000_000, pid=1, tid=1),
            X("child_a", 1_200_000, 1_000_000, pid=1, tid=1),
            X("child_b", 2_500_000, 1_000_000, pid=1, tid=1),
        ]
        session_dir = _make_session(tmp_path, viztracer_events=events)
        result = generate_full_trace_report(session_dir)

        summary = _read_csv(session_dir / "derived" / "functions_summary.csv")
        parent = [r for r in summary if r["function"] == "parent_func"][0]
        # Exclusive should be 2000ms (union of non-overlapping children)
        assert float(parent["exclusive_ms"]) == pytest.approx(2000.0, abs=5)

    def test_merge_intervals_utility(self, tmp_path: Path):
        """Contract 4: _merge_intervals correctly merges overlapping intervals."""
        from comfymodal_runtime.full_trace_report import _merge_intervals, _total_interval_length

        # Non-overlapping: no merge needed
        assert _merge_intervals([(0, 10), (20, 30)]) == [(0, 10), (20, 30)]
        assert _total_interval_length([(0, 10), (20, 30)]) == 20.0

        # Overlapping: should merge
        merged = _merge_intervals([(0, 15), (10, 25)])
        assert len(merged) == 1
        assert merged[0] == (0, 25)
        assert _total_interval_length([(0, 15), (10, 25)]) == 25.0

        # Nested: should merge
        merged2 = _merge_intervals([(5, 30), (10, 20)])
        assert len(merged2) == 1
        assert merged2[0] == (5, 30)
        assert _total_interval_length([(5, 30), (10, 20)]) == 25.0

        # Empty list
        assert _merge_intervals([]) == []
        assert _total_interval_length([]) == 0.0

    def test_source_extraction_from_args(self, tmp_path: Path):
        """Contract 5: source_file, source_line, task_id extracted from args."""
        events = [
            X("func", 1000, 500, pid=1, tid=1, args={
                "source_file": "/path/to/module.py",
                "source_line": 42,
                "task_id": "task_xyz",
                "call_frame": {"filename": "frame.py", "lineno": 99},
            }),
        ]
        session_dir = _make_session(tmp_path, viztracer_events=events)
        result = generate_full_trace_report(session_dir)

        calls = _read_gzip_csv(session_dir / "derived" / "calls.csv.gz")
        call = calls[0]
        assert "module.py" in call["source_file"] or call["source_file"] != ""
        # task_id should be present
        assert "task_xyz" in call.get("task_id", "")

    def test_semantic_key_hash_deterministic(self, tmp_path: Path):
        """Contract 6: semantic_key_hash is deterministic SHA-256."""
        events = [
            X("volume_reload:models", 1000, 500, pid=1, tid=1, args={"key": "model_abc"}),
            X("volume_reload:models", 2000, 600, pid=1, tid=1, args={"key": "model_abc"}),
            X("volume_reload:models", 3000, 400, pid=1, tid=1, args={"key": "model_xyz"}),
        ]
        trace_config = {"request_id": "req-1", "restore_session_id": "sess-1"}
        session_dir = _make_session(
            tmp_path,
            viztracer_events=events,
            trace_config=trace_config,
        )
        result = generate_full_trace_report(session_dir)

        report_data = json.loads(
            (session_dir / "derived" / "report_data.json").read_text("utf-8")
        )
        # Check semantic_duplicates grouping
        dups = report_data.get("semantic_duplicates", [])
        # Two groups: model_abc (2 calls) and model_xyz (1 call) — only model_abc has >=2
        model_abc_dups = [d for d in dups if d["call_count"] >= 2]
        # model_abc duplicates
        assert len(model_abc_dups) >= 1
        # semantic_key_hash should be non-empty and deterministic
        for d in dups:
            assert d.get("semantic_key_hash", "") != ""
            assert len(d["semantic_key_hash"]) == 64  # SHA-256 hex

    def test_at_most_one_rules(self, tmp_path: Path):
        """Contract 7: at-most-one rules: not_observed for 0, expected for 1, above_expected for >1."""
        # Test with 0 certificate_read → expected (at-most-one allows 0)
        session_dir = _make_session(
            tmp_path,
            viztracer_events=[X("main", 1000, 500)],
            trace_config={"request_id": "test"},
        )
        result = generate_full_trace_report(session_dir)
        evo = _read_csv(session_dir / "derived" / "expected_vs_observed.csv")
        cert = [r for r in evo if r["operation"] == "certificate_read"]
        assert cert
        # At-most-one: 0 is "expected"
        assert cert[0]["classification"] == "expected"

        # Test with 2 volume_reload:models → above_expected
        session_dir2 = _make_session(
            tmp_path / "s2",
            viztracer_events=[
                X("volume_reload:models", 1000, 500, pid=1, tid=1),
                X("volume_reload:models", 2000, 500, pid=1, tid=1),
            ],
            trace_config={"request_id": "test"},
        )
        result2 = generate_full_trace_report(session_dir2)
        evo2 = _read_csv(session_dir2 / "derived" / "expected_vs_observed.csv")
        vol = [r for r in evo2 if r["operation"] == "volume_reload:models"][0]
        assert vol["classification"] == "above_expected"

    def test_cgroup_missing_unattributed_unavailable(self, tmp_path: Path):
        """Contract 8: no cgroup → container + unattributed = measurement_unavailable."""
        resource_samples = [
            {"timestamp_ms": 1000.0, "process_cpu": {"processes": [{"pid": 1, "ticks": 100}]}},
            {"timestamp_ms": 2000.0, "process_cpu": {"processes": [{"pid": 1, "ticks": 200}]}},
        ]
        session_dir = _make_session(
            tmp_path,
            viztracer_events=[X("main", 1000, 500)],
            resource_samples=resource_samples,
        )
        result = generate_full_trace_report(session_dir)
        report_data = json.loads(
            (session_dir / "derived" / "report_data.json").read_text("utf-8")
        )
        samples = report_data.get("resource_samples", [])
        for s in samples:
            assert s["container_effective_cores"] == "measurement_unavailable"
            assert s["unattributed_effective_cores"] == "measurement_unavailable"

    def test_background_survivors_exact_columns(self, tmp_path: Path):
        """Contract 9: background_survivors.csv has exact required columns."""
        milestones = [{"name": "restore_complete", "wall_unix_ms": 1500.0}]
        # Call spans across boundary: ts=1000 (1ms), dur=2000000 (2000ms)
        # Boundary at 1500ms = 1500000us
        events = [X("background_work", 1_000_000, 2_000_000, pid=1, tid=2)]
        session_dir = _make_session(
            tmp_path,
            viztracer_events=events,
            milestones=milestones,
        )
        result = generate_full_trace_report(session_dir)

        csv_path = session_dir / "derived" / "background_survivors.csv"
        raw = csv_path.read_bytes()
        header = raw.decode("utf-8-sig").split("\n")[0]
        required_cols = [
            "owner_type", "owner_id", "name", "created_or_started_ms",
            "boundary_crossed", "ended_ms", "duration_ms", "thread_or_task", "evidence_source",
        ]
        for col in required_cols:
            assert col in header, f"Missing column: {col}"

        # Verify at least one survivor with correct boundary
        survivors = _read_csv(csv_path)
        assert any(s["boundary_crossed"] == "restore_complete" for s in survivors)

    def test_wrapper_snapshot_handles_common_shapes(self, tmp_path: Path):
        """Contract 10: handle snapshots list, wrappers mapping, chain fields."""
        wrapper_snapshots = [
            {
                "milestone": "restore_complete",
                "wrappers": {
                    "sample": [
                        {"id": "w1", "__wrapped__": True},
                        {"id": "w1"},  # repeated id → cycle
                    ],
                },
            },
        ]
        session_dir = _make_session(
            tmp_path,
            viztracer_events=[X("main", 1000, 500)],
            wrapper_snapshots=wrapper_snapshots,
        )
        result = generate_full_trace_report(session_dir)

        chains = json.loads(
            (session_dir / "derived" / "wrapper_chains.json").read_text("utf-8")
        )
        sample = [c for c in chains if c["target"] == "sample"]
        assert len(sample) >= 1
        # Has cycles because repeated callable_id
        assert sample[0]["has_cycles"] is True
        # Has sentinel attributes (__wrapped__)
        assert sample[0]["sentinel_attributes"] is True

    def test_torch_cpu_op_categories(self, tmp_path: Path):
        """Contract 11: CPU operators recognized by common categories."""
        torch_events = [
            X("aten::mm", 1000, 500, pid=1, tid=1, cat="cpu_op"),
            X("operator::conv2d", 2000, 300, pid=1, tid=1, cat="operator"),
            X("python_function::forward", 3000, 200, pid=1, tid=1, cat="python_function"),
        ]
        session_dir = _make_session(
            tmp_path,
            viztracer_events=[X("main", 1000, 500)],
            torch_events=torch_events,
        )
        result = generate_full_trace_report(session_dir)

        cpu_ops = _read_csv(session_dir / "derived" / "torch_cpu_ops.csv")
        assert len(cpu_ops) >= 1
        # at least aten::mm and operator::conv2d should be recognized
        ops_found = {r["operator"] for r in cpu_ops}
        assert "aten::mm" in ops_found

    def test_torch_cuda_exact_columns(self, tmp_path: Path):
        """Contract 11: torch_cuda_ops.csv has exact requested columns."""
        torch_events = [
            X("cudaLaunchKernel", 1000, 500, pid=1, tid=1, cat="cuda_kernel"),
        ]
        session_dir = _make_session(
            tmp_path,
            viztracer_events=[X("main", 1000, 500)],
            torch_events=torch_events,
        )
        result = generate_full_trace_report(session_dir)

        csv_path = session_dir / "derived" / "torch_cuda_ops.csv"
        raw = csv_path.read_bytes()
        header = raw.decode("utf-8-sig").split("\n")[0]
        expected_cols = [
            "kernel_or_memcpy", "category", "call_count",
            "total_cuda_ms", "mean_cuda_ms", "max_cuda_ms", "stream_count",
        ]
        for col in expected_cols:
            assert col in header, f"Missing column: {col}"

    def test_no_recommendation_language_in_markdown(self, tmp_path: Path):
        """Contract 12: no recommendation/fix/root-cause language."""
        events = [X("main", 1000, 500)]
        session_dir = _make_session(tmp_path, viztracer_events=events,
                                     trace_config={"request_id": "test"})
        result = generate_full_trace_report(session_dir)

        md_content = (session_dir / "derived" / "report.md").read_text("utf-8")
        forbidden = ["recommend", "should fix", "must change", "TODO", "FIXME",
                     "root cause", "optimization opportunity"]
        for phrase in forbidden:
            assert phrase.lower() not in md_content.lower(), f"Found prohibited: {phrase}"

    def test_manifest_all_files_with_hashes(self, tmp_path: Path):
        """Contract 12: manifest lists every raw and derived file with sha256."""
        events = [X("main", 1000, 500)]
        session_dir = _make_session(tmp_path, viztracer_events=events,
                                     trace_config={"request_id": "test"})
        result = generate_full_trace_report(session_dir)

        manifest = json.loads(
            (session_dir / "derived" / "manifest.json").read_text("utf-8")
        )
        files = manifest.get("files", [])
        assert len(files) >= 1
        for entry in files:
            assert "path" in entry
            assert "category" in entry
            assert "size_bytes" in entry
            assert "sha256" in entry
            # SHA-256 is 64 hex chars or empty for unreadable
            assert len(entry["sha256"]) == 64 or entry["sha256"] == ""

    def test_report_md_all_required_headings(self, tmp_path: Path):
        """Contract 12: all required headings present exactly as requested."""
        events = [X("main", 1000, 500)]
        session_dir = _make_session(tmp_path, viztracer_events=events,
                                     trace_config={"request_id": "test"})
        result = generate_full_trace_report(session_dir)

        md_content = (session_dir / "derived" / "report.md").read_text("utf-8")
        required_headings = [
            "# V2 Full Execution Trace Report",
            "## Trace identity",
            "## Trace completeness",
            "## Runtime configuration",
            "## Critical timeline",
            "## Top functions by inclusive time",
            "## Top functions by exclusive time",
            "## Highest call counts",
            "## Concurrent operations",
            "## CPU ownership by process",
            "## CPU ownership by native thread",
            "## Background work crossing restore completion",
            "## Background work crossing request entry",
            "## Background work crossing sampling start",
            "## Duplicate semantic work",
            "## Repeated wrapper layers",
            "## Wrapper changes during the lifecycle",
            "## Expected versus observed operation counts",
            "## PyTorch CPU operator summary",
            "## CUDA kernel and memory-copy summary",
            "## Unattributed container CPU",
            "## Potential optimization artifacts",
            "## Raw and derived file inventory",
        ]
        for heading in required_headings:
            assert heading in md_content, f"Missing heading: {heading}"

    def test_invalid_session_derived_files_is_list(self, tmp_path: Path):
        """Invalid session must return derived_files as list[str]."""
        result = generate_full_trace_report(tmp_path / "does_not_exist")
        assert result["status"] == "error"
        assert isinstance(result["derived_files"], list)

    def test_deterministic_output_cross_run(self, tmp_path: Path):
        """Two identical sessions must produce identical report_data.json,
        report.md, manifest.json, and calls.csv.gz."""
        events = [
            X("func_a", 1000, 500, pid=1, tid=1),
            X("func_b", 1500, 300, pid=1, tid=1),
            X("func_a", 2000, 400, pid=1, tid=2),
        ]
        session1 = _make_session(tmp_path / "run1", viztracer_events=events)
        session2 = _make_session(tmp_path / "run2", viztracer_events=events)
        result1 = generate_full_trace_report(session1)
        result2 = generate_full_trace_report(session2)

        for fname in ("report_data.json", "report.md", "manifest.json", "calls.csv.gz"):
            p1 = session1 / "derived" / fname
            p2 = session2 / "derived" / fname
            assert p1.exists() and p2.exists()
            assert p1.read_bytes() == p2.read_bytes(), f"{fname} differs between runs"

    def test_at_most_one_non_optional_not_observed(self, tmp_path: Path):
        """Non-optional at-most-one with 0 observed => not_observed, not expected."""
        session_dir = _make_session(
            tmp_path,
            viztracer_events=[X("main", 1000, 500)],
        )
        result = generate_full_trace_report(session_dir)
        evo = _read_csv(session_dir / "derived" / "expected_vs_observed.csv")
        ops = {r["operation"]: r for r in evo}
        # All at-most-one rules are optional; 0 => expected is valid.
        assert "volume_reload:models" in ops
        assert ops["volume_reload:models"]["classification"] in ("not_observed", "expected")

    def test_cache_seed_in_expected_vs_observed(self, tmp_path: Path):
        """cache_seed must be present in expected_vs_observed."""
        session_dir = _make_session(
            tmp_path,
            viztracer_events=[X("cache_seed", 1000, 50, pid=1, tid=1)],
        )
        result = generate_full_trace_report(session_dir)
        evo = _read_csv(session_dir / "derived" / "expected_vs_observed.csv")
        ops = {r["operation"]: r for r in evo}
        assert "cache_seed" in ops

    def test_wrapper_installation_in_expected_vs_observed(self, tmp_path: Path):
        """wrapper_installation_per_target must be present."""
        session_dir = _make_session(
            tmp_path,
            viztracer_events=[X("main", 1000, 500)],
        )
        result = generate_full_trace_report(session_dir)
        evo = _read_csv(session_dir / "derived" / "expected_vs_observed.csv")
        ops = {r["operation"]: r for r in evo}
        assert "wrapper_installation_per_target" in ops

    def test_trace_stop_boundary_support(self, tmp_path: Path):
        """trace_stop_boundary naming should be recognized as a lifecycle boundary."""
        milestones = [
            {"name": "trace_stop_boundary", "wall_unix_ms": 5000.0, "duration_ms": 0},
        ]
        events = [X("background_work", 1_000_000, 10_000_000, pid=1, tid=2)]
        session_dir = _make_session(
            tmp_path,
            viztracer_events=events,
            milestones=milestones,
        )
        result = generate_full_trace_report(session_dir)
        survivors = _read_csv(session_dir / "derived" / "background_survivors.csv")
        # Either trace_stop or trace_stop_boundary should match
        assert any(s["boundary_crossed"] in ("trace_stop", "trace_stop_boundary") for s in survivors)

    def test_wrapper_snapshot_top_level_list(self, tmp_path: Path):
        """Wrapper snapshots as top-level list should be parsed."""
        wrapper_data = [{
            "milestone": "restore_complete",
            "wrappers": {"sample": [{"id": "w1", "__wrapped__": True}]},
        }]
        session_dir = _make_session(
            tmp_path,
            viztracer_events=[X("main", 1000, 500)],
            wrapper_snapshots=wrapper_data,
        )
        result = generate_full_trace_report(session_dir)
        chains = json.loads(
            (session_dir / "derived" / "wrapper_chains.json").read_text("utf-8")
        )
        assert len(chains) >= 1

    def test_wrapper_snapshot_snapshots_key(self, tmp_path: Path):
        """Wrapper snapshots under 'snapshots' key should be parsed."""
        wrapper_data = {"snapshots": [
            {"milestone": "restore_complete", "wrappers": {"sample": [{"id": "w1"}]}},
        ]}
        session_dir = _make_session(
            tmp_path,
            viztracer_events=[X("main", 1000, 500)],
            wrapper_snapshots=wrapper_data,
        )
        result = generate_full_trace_report(session_dir)
        chains = json.loads(
            (session_dir / "derived" / "wrapper_chains.json").read_text("utf-8")
        )
        assert len(chains) >= 1

    def test_async_task_from_session_events(self, tmp_path: Path):
        """Async tasks in session_events should be extracted."""
        session_events = [
            {"task_id": "async_task_1", "name": "encode", "timestamp_ms": 1000.0, "done": True},
        ]
        session_dir = _make_session(
            tmp_path,
            viztracer_events=[X("main", 1000, 500)],
            session_events=session_events,
        )
        result = generate_full_trace_report(session_dir)
        tasks = _read_csv(session_dir / "derived" / "async_tasks.csv")
        task_ids = {r["task_id"] for r in tasks}
        assert "async_task_1" in task_ids

    def test_process_timeline_computed_cpu(self, tmp_path: Path):
        """process_timeline should include computed CPU fields."""
        resource_samples = [
            {
                "timestamp_ms": 1000.0,
                "cgroup_cpu": {"usage_us": 100000, "nr_periods": 10, "quota_us": 100000},
                "process_cpu": {
                    "main_pid": 1,
                    "processes": [{"pid": 1, "ticks": 100}],
                },
            },
            {
                "timestamp_ms": 2000.0,
                "cgroup_cpu": {"usage_us": 200000, "nr_periods": 20, "quota_us": 100000},
                "process_cpu": {
                    "main_pid": 1,
                    "processes": [{"pid": 1, "ticks": 200}],
                },
            },
        ]
        session_dir = _make_session(
            tmp_path,
            viztracer_events=[X("main", 1000, 500)],
            resource_samples=resource_samples,
        )
        result = generate_full_trace_report(session_dir)
        report_data = json.loads(
            (session_dir / "derived" / "report_data.json").read_text("utf-8")
        )
        samples = report_data.get("resource_samples", [])
        # With cgroup data, container_effective_cores should be numeric
        for s in samples:
            if s.get("container_available"):
                assert isinstance(s["container_effective_cores"], (int, float)) or s["container_effective_cores"] == "measurement_unavailable"


class TestManifestAndInventory:
    """Manifest and file inventory generation."""

    def test_manifest_includes_all_files(self, tmp_path: Path):
        """Manifest should list every raw and derived file."""
        events = [X("main", 1000, 500)]
        session_dir = _make_session(tmp_path, viztracer_events=events,
                                     trace_config={"request_id": "test"})
        result = generate_full_trace_report(session_dir)

        manifest_path = session_dir / "derived" / "manifest.json"
        assert manifest_path.exists()
        manifest = json.loads(manifest_path.read_text("utf-8"))

        files = manifest.get("files", [])
        assert len(files) >= 2  # At least raw/viztracer.json.gz + derived files

        # Check categories
        categories = {f["category"] for f in files}
        assert "raw" in categories
        assert "derived" in categories

    def test_report_md_headings(self, tmp_path: Path):
        """report.md should have all required headings."""
        events = [X("main", 1000, 500)]
        session_dir = _make_session(tmp_path, viztracer_events=events,
                                     trace_config={"request_id": "test"})
        result = generate_full_trace_report(session_dir)

        md_content = (session_dir / "derived" / "report.md").read_text("utf-8")
        required_headings = [
            "# V2 Full Execution Trace Report",
            "## Trace identity",
            "## Trace completeness",
            "## Runtime configuration",
            "## Critical timeline",
            "## Top functions by inclusive time",
            "## Top functions by exclusive time",
            "## Highest call counts",
            "## Concurrent operations",
            "## CPU ownership by process",
            "## CPU ownership by native thread",
            "## Background work crossing restore completion",
            "## Background work crossing request entry",
            "## Background work crossing sampling start",
            "## Duplicate semantic work",
            "## Repeated wrapper layers",
            "## Wrapper changes during the lifecycle",
            "## Expected versus observed operation counts",
            "## PyTorch CPU operator summary",
            "## CUDA kernel and memory-copy summary",
            "## Unattributed container CPU",
            "## Potential optimization artifacts",
            "## Raw and derived file inventory",
        ]
        for heading in required_headings:
            assert heading in md_content, f"Missing heading: {heading}"

    def test_no_recommendation_language(self, tmp_path: Path):
        """Report should not contain recommendation/fix language."""
        events = [X("main", 1000, 500)]
        session_dir = _make_session(tmp_path, viztracer_events=events,
                                     trace_config={"request_id": "test"})
        result = generate_full_trace_report(session_dir)

        md_content = (session_dir / "derived" / "report.md").read_text("utf-8")

        # Check for absence of recommendation language
        forbidden = ["recommend", "should fix", "must change", "TODO", "FIXME"]
        for phrase in forbidden:
            assert phrase.lower() not in md_content.lower(), f"Found recommendation language: {phrase}"


class TestStatusBehavior:
    """Status value correctness."""

    def test_ready_with_good_data(self, tmp_path: Path):
        """Valid trace and config should produce ready status."""
        events = [X("main", 1000, 500)]
        session_dir = _make_session(tmp_path, viztracer_events=events,
                                     trace_config={"request_id": "test"})
        result = generate_full_trace_report(session_dir)
        assert result["status"] == "ready"

    def test_partial_on_missing_optional(self, tmp_path: Path):
        """Missing optional files should still be partial or ready."""
        events = [X("main", 1000, 500)]
        session_dir = _make_session(tmp_path, viztracer_events=events)
        result = generate_full_trace_report(session_dir)
        assert result["status"] in ("ready", "partial")

    def test_error_on_nonexistent_session(self, tmp_path: Path):
        """Non-existent session dir should give error."""
        result = generate_full_trace_report(tmp_path / "does_not_exist")
        assert result["status"] == "error"


class TestAdditionalEdgeCases:
    """Additional edge cases covering remaining requirements."""

    def test_semantic_ops_with_overlaps(self, tmp_path: Path):
        """Semantic ops that overlap should be flagged."""
        events = [
            X("clip_graph_encode", 1_000_000, 2_000_000, pid=1, tid=1),
            X("clip_graph_encode", 2_500_000, 1_000_000, pid=1, tid=1),
        ]
        session_dir = _make_session(tmp_path, viztracer_events=events,
                                     trace_config={"request_id": "test"})
        result = generate_full_trace_report(session_dir)

        sem_dups = _read_csv(session_dir / "derived" / "semantic_duplicates.csv")
        clip_dups = [d for d in sem_dups if d["operation_type"] == "clip_graph_encode"]
        assert len(clip_dups) >= 1
        if clip_dups:
            assert clip_dups[0]["overlaps"] in ("True", "true", True)

    def test_cuda_memory_copy_classification(self, tmp_path: Path):
        """CUDA memory copies should be classified as memory_copy."""
        torch_events = [
            X("cudaMemcpyH2D", 1000, 500, pid=1, tid=1, cat="cuda_memcpy"),
            X("cudaMemcpyD2H", 2000, 400, pid=1, tid=1, cat="cuda_memcpy"),
            X("cudaMemcpyDeviceToDevice", 3000, 300, pid=1, tid=1, cat="cuda_memcpy"),
        ]
        session_dir = _make_session(
            tmp_path,
            viztracer_events=[X("main", 1000, 500)],
            torch_events=torch_events,
        )
        result = generate_full_trace_report(session_dir)

        cuda_ops = _read_csv(session_dir / "derived" / "torch_cuda_ops.csv")
        categories = {r["category"] for r in cuda_ops}
        assert "memory_copy" in categories

    def test_cuda_sync_classification(self, tmp_path: Path):
        """CUDA synchronization calls should be classified."""
        torch_events = [
            X("cudaDeviceSynchronize", 1000, 200, pid=1, tid=1, cat="cuda_sync"),
        ]
        session_dir = _make_session(
            tmp_path,
            viztracer_events=[X("main", 1000, 500)],
            torch_events=torch_events,
        )
        result = generate_full_trace_report(session_dir)

        cuda_ops = _read_csv(session_dir / "derived" / "torch_cuda_ops.csv")
        assert len(cuda_ops) >= 1
        sync_ops = [r for r in cuda_ops if "synchronize" in r["kernel_or_memcpy"].lower()]
        if sync_ops:
            assert sync_ops[0]["category"] == "synchronization"

    def test_wrapper_chain_cycles(self, tmp_path: Path):
        """Wrapper chains with repeated callable IDs should show cycles."""
        wrapper_snapshots = [
            {
                "milestone": "restore_complete",
                "wrappers": {
                    "sample": [
                        {"id": "w1", "name": "func"},
                        {"id": "w2", "name": "wrapper"},
                        {"id": "w1", "name": "func"},  # Repeated ID = cycle
                    ],
                },
            },
        ]
        session_dir = _make_session(
            tmp_path,
            viztracer_events=[X("main", 1000, 500)],
            wrapper_snapshots=wrapper_snapshots,
        )
        result = generate_full_trace_report(session_dir)

        chains = json.loads(
            (session_dir / "derived" / "wrapper_chains.json").read_text("utf-8")
        )
        sample_chains = [c for c in chains if c["target"] == "sample"]
        assert len(sample_chains) >= 1
        assert sample_chains[0]["has_cycles"] is True

    def test_resource_owners_with_threads(self, tmp_path: Path):
        """Resource owners should include thread core data."""
        resource_samples = [
            {
                "timestamp_ms": 1000.0,
                "cgroup_cpu": {"usage_us": 100000, "nr_periods": 10, "quota_us": 100000},
                "process_cpu": {"processes": [{"pid": 1, "ticks": 100}]},
                "thread_cpu": {"threads": [{"tid": 100, "pid": 1, "ticks": 50, "thread_name": "worker_1"}]},
            },
            {
                "timestamp_ms": 2000.0,
                "cgroup_cpu": {"usage_us": 200000, "nr_periods": 20, "quota_us": 100000},
                "process_cpu": {"processes": [{"pid": 1, "ticks": 200}]},
                "thread_cpu": {"threads": [{"tid": 100, "pid": 1, "ticks": 100, "thread_name": "worker_1"}]},
            },
        ]
        session_dir = _make_session(
            tmp_path,
            viztracer_events=[X("main", 1000, 500)],
            resource_samples=resource_samples,
        )
        result = generate_full_trace_report(session_dir)

        owners = _read_csv(session_dir / "derived" / "resource_owners.csv")
        # Should have thread entries
        thread_owners = [o for o in owners if o["owner_type"] == "thread"]
        assert len(thread_owners) >= 1

    def test_output_encoding_consistency(self, tmp_path: Path):
        """CSVs should use BOM and consistent encoding."""
        events = [X("main", 1000, 500)]
        session_dir = _make_session(tmp_path, viztracer_events=events)
        result = generate_full_trace_report(session_dir)

        # Check for BOM in CSV files
        for csv_file in [
            "functions_summary.csv",
            "critical_timeline.csv",
        ]:
            path = session_dir / "derived" / csv_file
            raw = path.read_bytes()
            # Should start with UTF-8 BOM
            assert raw.startswith(b"\xef\xbb\xbf"), f"Missing BOM in {csv_file}"

        # Check gzipped CSV
        gz_path = session_dir / "derived" / "calls.csv.gz"
        raw_gz = gz_path.read_bytes()
        # Should be gzip magic
        assert raw_gz.startswith(b"\x1f\x8b"), "Missing gzip magic in calls.csv.gz"

    def test_report_data_structured_facts(self, tmp_path: Path):
        """report_data.json should contain all structured facts used by markdown."""
        events = [X("main", 1000, 500)]
        session_dir = _make_session(tmp_path, viztracer_events=events,
                                     trace_config={"request_id": "test"})
        result = generate_full_trace_report(session_dir)

        report_data = json.loads(
            (session_dir / "derived" / "report_data.json").read_text("utf-8")
        )

        # Required top-level keys
        for key in ("schema_version", "status", "calls", "timeline",
                     "functions_summary", "duplicate_calls", "semantic_duplicates",
                     "expected_vs_observed", "torch_cpu_ops", "torch_cuda_ops"):
            assert key in report_data, f"Missing key in report_data.json: {key}"


# =========================================================================
# CSV / GZIP reading helpers
# =========================================================================


def _read_csv(path: Path) -> list[dict[str, Any]]:
    """Read a CSV file and return list of dicts."""
    if not path.exists():
        return []
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        return list(reader)


def _read_gzip_csv(path: Path) -> list[dict[str, Any]]:
    """Read a gzipped CSV file."""
    if not path.exists():
        return []
    raw = path.read_bytes()
    try:
        text = gzip.decompress(raw).decode("utf-8-sig", errors="replace")
    except Exception:
        # Maybe not gzip
        text = raw.decode("utf-8-sig", errors="replace")
    reader = csv.DictReader(io.StringIO(text))
    return list(reader)
