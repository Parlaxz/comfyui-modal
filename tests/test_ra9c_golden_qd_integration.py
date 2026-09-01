"""Offline integration contracts for the RA9C Golden QD wiring."""

from __future__ import annotations

import ast
import asyncio
import importlib.util
import sys
from pathlib import Path

import pytest


MODULE_PATH = Path(__file__).resolve().parents[1] / "comfymodal_runtime" / "golden_serial.py"
WORKTREE_ROOT = MODULE_PATH.parents[1]
if str(WORKTREE_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKTREE_ROOT))


def _load_module():
    spec = importlib.util.spec_from_file_location("golden_serial_under_test", MODULE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules.setdefault("golden_serial_under_test", module)
    spec.loader.exec_module(module)
    return module


gs = _load_module()


def _request():
    return gs.GoldenRequest("request", {"1": {"class_type": "LoadImage", "inputs": {}}})


def test_selector_is_independent_of_stage_diagnostics_and_emits_run_identity_evidence(monkeypatch):
    monkeypatch.delenv(gs.GOLDEN_STAGE_DIAGNOSTICS_ENV, raising=False)
    monkeypatch.setenv(gs.GOLDEN_QD_TRANSPORT_ENV, " DISPATCHER ")

    assert gs.golden_qd_transport_arm() == "dispatcher"
    session = gs.GoldenSession(_request(), volume=object())

    assert session.qd_transport_arm == "dispatcher"
    assert session.run_identity["qd_transport_arm"] == "dispatcher"
    payload = session.recorder.to_json_dict()
    assert payload["run_identity"]["qd_transport_arm"] == "dispatcher"
    assert any(
        event["name"] == "golden_qd_transport_selector"
        and event["fields"]["arm"] == "dispatcher"
        for event in payload["events"]
    )


@pytest.mark.parametrize("raw, expected", [(None, "legacy"), ("", "legacy"), ("legacy", "legacy")])
def test_selector_normalizes_legacy_without_bookkeeping(monkeypatch, raw, expected):
    if raw is None:
        monkeypatch.delenv(gs.GOLDEN_QD_TRANSPORT_ENV, raising=False)
    else:
        monkeypatch.setenv(gs.GOLDEN_QD_TRANSPORT_ENV, raw)
    monkeypatch.setenv(gs.GOLDEN_STAGE_DIAGNOSTICS_ENV, "1")

    assert gs.golden_qd_transport_arm() == expected
    session = gs.GoldenSession(_request(), volume=object())
    assert session.run_identity["qd_transport_arm"] == expected


@pytest.mark.parametrize("raw", [None, "legacy"])
def test_legacy_read_path_remains_control_branch_without_cuda(monkeypatch, raw):
    if raw is None:
        monkeypatch.delenv(gs.GOLDEN_QD_TRANSPORT_ENV, raising=False)
    else:
        monkeypatch.setenv(gs.GOLDEN_QD_TRANSPORT_ENV, raw)
    called = []

    def forbidden_dispatcher(*args, **kwargs):
        called.append((args, kwargs))
        return {"status": "unexpected"}

    monkeypatch.setattr(gs, "_read_file_qd_gpu_dispatcher", forbidden_dispatcher)
    monkeypatch.setattr(gs.torch.cuda, "is_available", lambda: False)

    with pytest.raises(RuntimeError, match="cuda_unavailable"):
        gs.read_file_qd_gpu("unused.safetensors", role="clip")
    assert called == []

    source = MODULE_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)
    fn = next(
        node for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "read_file_qd_gpu"
    )
    assert any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "golden_qd_transport_arm"
        for node in ast.walk(fn)
    )


def test_dispatcher_branch_calls_adapter_with_original_arguments(monkeypatch):
    monkeypatch.setenv(gs.GOLDEN_QD_TRANSPORT_ENV, "dispatcher")
    calls = []
    sentinel = {"status": "sentinel"}

    def adapter(*args, **kwargs):
        calls.append((args, kwargs))
        return sentinel

    monkeypatch.setattr(gs, "_read_file_qd_gpu_dispatcher", adapter)
    result = gs.read_file_qd_gpu(
        "checkpoint.safetensors",
        role="clip",
        device="cuda:7",
        qd=9,
        block_bytes=123,
        diagnostics=False,
    )

    assert result is sentinel
    assert calls == [
        (("checkpoint.safetensors",), {
            "role": "clip",
            "device": "cuda:7",
            "qd": 9,
            "block_bytes": 123,
            "diagnostics": False,
        })
    ]


def test_dispatcher_adapter_uses_direct_readinto_transport_seam_without_payload_materialization():
    source = MODULE_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)
    fn = next(
        node for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef)
        and node.name == "_read_file_qd_gpu_dispatcher"
    )

    calls = [
        node for node in ast.walk(fn)
        if isinstance(node, ast.Call)
    ]
    assert any(
        isinstance(node.func, ast.Attribute)
        and node.func.attr == "create_transport"
        for node in calls
    )
    assert any(
        isinstance(node.func, ast.Attribute)
        and node.func.attr == "CudaTransferBackend"
        for node in calls
    )
    assert any(
        isinstance(node, ast.FunctionDef)
        and node.name == "readinto"
        for node in ast.walk(fn)
    )
    assert not any(
        isinstance(node, ast.Name) and node.id == "_qd_gpu_worker"
        for node in ast.walk(fn)
    )
    assert not any(
        isinstance(node.func, ast.Name)
        and node.func.id in {"bytearray", "bytes"}
        for node in calls
    )


def test_dispatcher_telemetry_classifies_direct_read_and_queue_planes_truthfully():
    diagnostics = gs.build_qd_transport_diagnostics({
        "execution_arm": "dispatcher",
        "bytes_read": 42,
        "source_read_count": 1,
        "source_reads": {
            "wall_ns": 21,
            "per_read": {
                "percentiles_ns": {
                    "p50_ns": 3,
                    "p90_ns": 5,
                    "p99_ns": 7,
                },
                "max_ns": 9,
            },
        },
        "cpu_to_pinned_staging": {"bytes": 42, "duration_ns": 0},
        "staging": {"allocated_bytes": 128, "memory_kind": "pinned"},
        "lease_wait": {"wait_ns": 11, "wait_count": 1},
        "ready_backpressure": {"wait_ns": 13, "wait_count": 1},
        "h2d_submit_wall": {"wall_ns": 17},
        "h2d_event_poll": {"status": "OBSERVED", "wall_ns": 19, "poll_count": 2},
        "h2d_event_completion_latency_ms": 2.5,
        "allocation_pinning": {"status": "OBSERVED", "allocation_ns": 29, "pinned": True},
        "producer_qd_occupancy": {"max_depth": 4, "fraction_time_at_target": 0.5},
        "free_ready_depth": {"minimum_free_slots": 1, "ready_queue_depth_at_end": 0},
        "exact_reconciliation": {"ok": True, "planned_bytes": 42},
        "final_drain": {"wall_ns": 23},
    })

    assert diagnostics["cpu_to_pinned_staging"]["status"] == "NOT RUN"
    assert diagnostics["pinned_slot_wait"]["status"] == "NOT RUN"
    assert diagnostics["source_reads"]["per_read"]["percentiles_ns"]["p90_ns"] == 5
    assert diagnostics["source_read_wall_ns"] == 21
    assert diagnostics["source_bytes"] == 42
    assert diagnostics["source_read_count"] == 1
    assert diagnostics["h2d_submit_wall"]["wall_ns"] == 17
    assert diagnostics["allocation_pinning"] == {
        "status": "OBSERVED",
        "allocation_ns": 29,
        "pinned": True,
    }
    assert diagnostics["h2d_event_poll"]["wall_ns"] == 19
    assert diagnostics["h2d_event_wait"]["status"] == "NOT RUN"
    assert diagnostics["h2d_event_completion"]["latency_ms"] == 2.5
    assert diagnostics["producer_qd_occupancy"]["max_depth"] == 4
    assert diagnostics["free_ready_depth"]["minimum_free_slots"] == 1
    assert diagnostics["exact_reconciliation"]["planned_bytes"] == 42
    assert diagnostics["final_drain"]["wall_ns"] == 23


def test_dispatcher_partial_reap_telemetry_does_not_fabricate_wall_time():
    diagnostics = gs.build_qd_transport_diagnostics({
        "execution_arm": "dispatcher",
        "dispatcher_telemetry": {"dispatcher_reap_count": 2},
    })

    assert diagnostics["h2d_event_poll"] == {
        "status": "OBSERVED",
        "wall_ns": None,
        "wall_ms": None,
        "poll_count": 2,
        "timing_scope": "TOTAL dispatcher event polling/reap",
    }


def test_legacy_qd_diagnostics_report_positioned_reads_and_bounded_percentiles():
    telemetry = gs._SourceTelemetry(2)
    clock = iter((100, 150, 300, 450))
    original_clock = gs.time.perf_counter_ns
    gs.time.perf_counter_ns = lambda: next(clock)
    try:
        first = telemetry.before(0)
        telemetry.after(0, first, 10)
        second = telemetry.before(1)
        telemetry.after(1, second, 20)
    finally:
        gs.time.perf_counter_ns = original_clock

    snapshot = telemetry.snapshot()
    source = gs._read_duration_summary(snapshot)
    diagnostics = gs.build_qd_transport_diagnostics({
        "execution_arm": "legacy",
        "source_read_count": snapshot["read_count"],
        "bytes_read": snapshot["read_bytes"],
        "source_reads": {
            "wall_ns": snapshot["latest_end_ns"] - snapshot["earliest_start_ns"],
            "bytes": snapshot["read_bytes"],
            "read_count": snapshot["read_count"],
            "per_read": source,
        },
        "pinned_slot_wait": {"wait_ns": 7, "wait_count": 1},
        "h2d_submit_wall": {"wall_ns": 11},
        "h2d_event_wait": {"wait_ns": 13, "wait_count": 1},
        "final_drain": {"wall_ns": 17},
        "allocation_pinning": {"allocation_ns": 19, "pinned": True},
    })

    assert diagnostics["source_bytes"] == 30
    assert diagnostics["source_read_count"] == 2
    assert diagnostics["source_reads"]["wall_ns"] == 350
    assert diagnostics["source_reads"]["per_read"]["percentiles_ns"] == {
        "p50_ns": 100,
        "p90_ns": 140,
        "p95_ns": 145,
        "p99_ns": 149,
    }
    assert diagnostics["source_reads"]["per_read"]["max_ns"] == 150
    assert diagnostics["pinned_slot_wait"]["wait_ns"] == 7
    assert diagnostics["h2d_submit_wall"]["wall_ns"] == 11
    assert diagnostics["h2d_event_wait"]["wait_ns"] == 13
    assert diagnostics["final_drain"]["wall_ns"] == 17
    assert diagnostics["allocation_pinning"]["pinned"] is True


def test_dispatcher_direct_read_does_not_report_a_separate_cpu_copy():
    diagnostics = gs.build_qd_transport_diagnostics({
        "execution_arm": "dispatcher",
        "bytes_read": 42,
        "pinned_bytes": 0,
        "cpu_to_pinned_staging": {"bytes": 42, "duration_ns": 0},
        "staging": {"allocated_bytes": 128, "memory_kind": "pinned"},
        "allocation_pinning": {"status": "OBSERVED", "allocated_bytes": 128, "pinned": True},
    })

    assert diagnostics["cpu_to_pinned_staging"]["status"] == "NOT RUN"
    assert diagnostics["allocation_pinning"]["status"] == "OBSERVED"
    assert diagnostics["pinned_slot_wait"]["status"] == "NOT RUN"
    assert diagnostics["post_transport_construction_adoption"]["status"] == "NOT RUN"


def test_register_qd_owner_is_immediately_visible_and_deduplicated(monkeypatch):
    monkeypatch.delenv(gs.GOLDEN_QD_TRANSPORT_ENV, raising=False)
    session = gs.GoldenSession(_request(), volume=object())
    owner = gs.GoldenQDOwner(object(), [object()], "cpu", "clip")
    other_owner = gs.GoldenQDOwner(object(), [object()], "cpu", "vae")

    session.register_qd_owner(owner)
    session.register_qd_owner(other_owner)
    session.register_qd_owner(owner)

    assert session.qd_transaction_owners == [owner, other_owner]


def test_teardown_releases_earlier_clip_transaction_without_clip_owners(monkeypatch):
    monkeypatch.delenv(gs.GOLDEN_QD_TRANSPORT_ENV, raising=False)
    session = gs.GoldenSession(_request(), volume=object())
    owner = gs.GoldenQDOwner(object(), [object()], "cpu", "clip")
    releases = []

    def release_staging():
        releases.append(True)

    monkeypatch.setattr(owner, "release_staging", release_staging)
    session.register_qd_owner(owner)
    del session.clip_owners

    asyncio.run(gs.golden_teardown(session))
    assert len(releases) == 1


def test_run_identity_and_transaction_registry_are_request_local(monkeypatch):
    monkeypatch.setenv(gs.GOLDEN_QD_TRANSPORT_ENV, "dispatcher")
    first = gs.GoldenSession(_request(), volume=object())
    second = gs.GoldenSession(_request(), volume=object())
    owner = gs.GoldenQDOwner(object(), [], "cpu", "clip")

    first.register_qd_owner(owner)

    assert first.run_identity is not second.run_identity
    assert first.run_identity["qd_transport_arm"] == "dispatcher"
    assert second.run_identity["qd_transport_arm"] == "dispatcher"
    assert first.qd_transaction_owners == [owner]
    assert second.qd_transaction_owners == []


def test_frozen_session_arm_wins_over_mid_request_environment_change(monkeypatch):
    monkeypatch.setenv(gs.GOLDEN_QD_TRANSPORT_ENV, "dispatcher")
    session = gs.GoldenSession(_request(), volume=object())
    monkeypatch.setenv(gs.GOLDEN_QD_TRANSPORT_ENV, "legacy")

    assert gs.golden_qd_transport_arm() == "legacy"
    assert gs.golden_qd_transport_arm(session.qd_transport_arm) == "dispatcher"


def test_stage_failure_preserves_wrapped_transport_telemetry():
    recorder = gs.GoldenTelemetryRecorder()
    recorder.begin_stage("golden_clip_load")
    error = RuntimeError("wrapped transport failure")
    setattr(error, "telemetry", {"h2d_completed_count": 3})
    setattr(error, "transport_failure", {"primary_error": "OSError: source failed"})

    recorder.fail_stage("golden_clip_load", error)

    interval = next(
        stage for stage in recorder.to_json_dict()["stages"] if stage["name"] == "golden_clip_load"
    )
    assert interval["details"]["transport_telemetry"] == {"h2d_completed_count": 3}
    assert interval["details"]["transport_failure"] == {
        "primary_error": "OSError: source failed"
    }
