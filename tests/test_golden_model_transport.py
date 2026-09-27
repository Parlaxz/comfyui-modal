from __future__ import annotations

import ast
import ctypes
import inspect
import json
import struct
import sys
import threading
from types import SimpleNamespace
from collections import OrderedDict

import pytest

from comfymodal_runtime.golden_model_transport import (
    BLOCK_BYTES,
    DESTINATION_ALIGNMENT,
    GpuDestinationPool,
    GoldenModelTransport,
    MIN_LAUNCH_GAP_NS,
    QD,
    STAGING_BYTES,
    _c0_window_trace_enabled,
    c0_source_coverage_proof,
    _destination_reserve_capacities,
    _percentile_summary,
    _sticky_lane_ranges,
    c0_m2_block_plan,
    resolve_c0_transport_geometry,
    summarize_c0_reader,
    summarize_dispatcher,
    _source_gbps,
    M2_SOURCE_CORE_AUTHORITY_SHA1,
    m2_source_core_parity,
    m2_source_core_sha1,
)
from comfymodal_runtime.m2_source_core import (
    _persistent_reader_close_fds,
    _persistent_reader_load,
)
from comfymodal_runtime.golden_qd_transport import SourceRange, StagingPool
from comfymodal_runtime import golden_io_process_v2 as c0
from comfymodal_runtime.golden_io_process_v2 import C0M2Control


pytestmark = pytest.mark.fast_unit


def _write_safetensors(path, key: str, payload: bytes = b"abcd") -> None:
    header = {
        key: {"dtype": "U8", "shape": [len(payload)], "data_offsets": [0, len(payload)]},
    }
    encoded = json.dumps(header, separators=(",", ":")).encode("utf-8")
    path.write_bytes(struct.pack("<Q", len(encoded)) + encoded + payload)


def test_transport_inspects_only_requested_path_and_bounds_layout_cache(tmp_path):
    paths = []
    for index in range(4):
        path = tmp_path / f"model-{index}.safetensors"
        _write_safetensors(path, f"tensor_{index}")
        paths.append(path)

    transport = GoldenModelTransport()
    first = transport.inspect(str(paths[0]))
    assert first.path == str(paths[0].resolve())
    assert list(first.tensor_map[0]) == ["key", "dtype", "shape", "offset", "length"]
    assert len(transport.layout_cache) == 1

    for path in paths[1:]:
        transport.inspect(str(path))
    assert len(transport.layout_cache) == 3
    assert str(paths[0].resolve()) not in transport.layout_cache


def test_models_generation_invalidates_layout_cache_without_recreating_runtime(tmp_path):
    path = tmp_path / "model.safetensors"
    _write_safetensors(path, "tensor")
    transport = GoldenModelTransport()
    transport.inspect(str(path))
    assert transport.layout_cache

    transport.update_models_generation("generation-2")

    assert not transport.layout_cache
    assert transport.lifecycle_telemetry(reused=False)["staging_reused"] is False


def test_transport_load_is_role_neutral_and_path_driven():
    signature = inspect.signature(GoldenModelTransport.load)
    assert tuple(signature.parameters) == ("self", "path")


def test_transport_geometry_is_fixed_to_proven_m2_contract(monkeypatch):
    for key in (
        "COMFYMODAL_GOLDEN_IO_PROCESS_V2_STREAMING",
        "COMFYMODAL_GOLDEN_IO_PROCESS_V2_SOURCE_ENGINE",
        "COMFYMODAL_GOLDEN_IO_PROCESS_V2_SOURCE_GEOMETRY",
    ):
        monkeypatch.delenv(key, raising=False)

    transport = GoldenModelTransport()

    assert (transport.qd, transport.block_bytes, transport.staging_slots) == (
        QD,
        BLOCK_BYTES,
        1,
    )
    assert transport.staging_bytes == STAGING_BYTES == 256 * 1024 * 1024
    assert transport.staging_backing == "anonymous"
    assert transport._c0_enabled is False


def test_c0_streaming_with_exact_window_engine_selects_shared_arena(monkeypatch):
    monkeypatch.setenv("COMFYMODAL_GOLDEN_IO_PROCESS_V2_STREAMING", "1")
    monkeypatch.setenv("COMFYMODAL_GOLDEN_IO_PROCESS_V2", "1")
    monkeypatch.setenv("COMFYMODAL_GOLDEN_IO_PROCESS_V2_SOURCE_ENGINE", "mmap_fresh")
    monkeypatch.setenv("COMFYMODAL_GOLDEN_IO_PROCESS_V2_SOURCE_GEOMETRY", "qd4_64")

    transport = GoldenModelTransport()

    assert transport._c0_enabled is True
    # C0 prepare is a cheap no-op: no fork, no staging build, no CUDA work.
    telemetry = transport.prepare_cpu()
    assert transport._prepared is True
    assert transport.staging is None
    assert transport._children == []
    assert telemetry["transport_runtime_reused"] is False


def test_c0_streaming_without_exact_window_engine_fails_closed(monkeypatch):
    # Half-armed C0 selection must not silently run the M2 execution arm.
    monkeypatch.setenv("COMFYMODAL_GOLDEN_IO_PROCESS_V2_STREAMING", "1")
    monkeypatch.setenv("COMFYMODAL_GOLDEN_IO_PROCESS_V2", "1")
    monkeypatch.delenv("COMFYMODAL_GOLDEN_IO_PROCESS_V2_SOURCE_ENGINE", raising=False)

    with pytest.raises(RuntimeError, match="c0_requires_mmap_fresh_qd4_64"):
        GoldenModelTransport()


def test_c0_model_operation_lock_is_shared_across_transport_instances():
    """A second ring cannot reset the singleton control block mid-load."""
    rings = []
    for _ in range(2):
        ring = object.__new__(c0.SharedArenaRing)
        # Deliberately give each wrapper a different instance lock.  The
        # runtime gate, rather than this field, must provide serialization.
        ring._model_operation_lock = threading.RLock()
        ring._model_operation_depth = 0
        ring._model_operation_owner = None
        rings.append(ring)

    entered = threading.Event()
    release_first = threading.Event()
    active = 0
    active_lock = threading.Lock()
    resets: list[int] = []
    overlap: list[bool] = []

    transports = [GoldenModelTransport(), GoldenModelTransport()]
    for transport, ring in zip(transports, rings):
        transport.prepare_cpu = lambda: None
        transport.initialize_cuda = lambda: None
        transport._c0_runtime = ring

    def body(_path):
        nonlocal active
        with active_lock:
            active += 1
            overlap.append(active > 1)
            resets.append(len(resets) + 1)
            if len(resets) == 1:
                entered.set()
        if len(resets) == 1:
            assert release_first.wait(1.0)
        with active_lock:
            active -= 1
        return object()

    for transport in transports:
        transport._load_c0_sync_body = body

    threads = [threading.Thread(target=transport._load_c0_sync, args=("model",))
               for transport in transports]
    for thread in threads:
        thread.start()
    assert entered.wait(1.0)
    # The second call is blocked before its body can reset model publication
    # counters; releasing the first operation lets it proceed normally.
    assert not any(overlap)
    release_first.set()
    for thread in threads:
        thread.join(1.0)
        assert not thread.is_alive()

    assert resets == [1, 2]
    assert overlap == [False, False]
    assert all(ring._model_operation_depth == 0 for ring in rings)


def test_c0_two_rings_reject_stale_consume_after_global_reset():
    """A late ticket cannot mutate the reset control after the next LOAD."""
    command = c0.C0ModelLoad(
        "model.safetensors", (1, 2, 3, 4), 0, 64 * 1024 * 1024,
        64 * 1024 * 1024, 1, ((0, 1), (1, 1), (1, 1), (1, 1)), 1,
    )
    control = c0.C0M2Control(arena_epoch=1)
    try:
        control.submit(command)
        struct.pack_into(
            "<QQQQQQ", control.buf, control.lane_offset(0), 1, 0, 0, 0,
            64 * 1024 * 1024, 0,
        )
        stale_ticket = control.wait_for_offset(0, 64 * 1024 * 1024, 0)
        struct.pack_into("<I", control.buf, 12, control.STATE_DONE)

        rings = []
        for _ in range(2):
            ring = object.__new__(c0.SharedArenaRing)
            ring._model_operation_lock = threading.RLock()
            ring._model_operation_depth = 0
            ring._model_operation_owner = None
            rings.append(ring)
        transports = [GoldenModelTransport(), GoldenModelTransport()]
        for transport, ring in zip(transports, rings):
            transport.prepare_cpu = lambda: None
            transport.initialize_cuda = lambda: None
            transport._c0_runtime = ring

        first_entered = threading.Event()
        release_first = threading.Event()
        second_entered = threading.Event()
        errors = []

        def first_body(_path):
            first_entered.set()
            assert release_first.wait(1.0)
            control.consume(stale_ticket)
            control.submit(command)
            return object()

        def second_body(_path):
            second_entered.set()
            with pytest.raises(c0.C0ProtocolError, match="stale_generation"):
                control.consume(stale_ticket)
            assert control.publication(0)[:2] == (0, 0)
            return object()

        transports[0]._load_c0_sync_body = first_body
        transports[1]._load_c0_sync_body = second_body

        def invoke(transport):
            try:
                transport._load_c0_sync("model")
            except BaseException as exc:  # pragma: no cover - assertion aid
                errors.append(exc)

        first = threading.Thread(target=invoke, args=(transports[0],))
        second = threading.Thread(target=invoke, args=(transports[1],))
        first.start()
        assert first_entered.wait(1.0)
        second.start()
        assert not second_entered.wait(0.02)
        release_first.set()
        first.join(1.0)
        second.join(1.0)

        assert not first.is_alive()
        assert not second.is_alive()
        assert errors == []
        assert control.current_generation() == 2
        assert control.publication(0)[:2] == (0, 0)
    finally:
        control.close()


def test_c0_model_operation_lock_survives_fail_closed_cleanup():
    ring = object.__new__(c0.SharedArenaRing)
    ring._model_operation_lock = threading.RLock()
    ring._model_operation_depth = 0
    ring._model_operation_owner = None
    transport = GoldenModelTransport()
    transport.prepare_cpu = lambda: None
    transport.initialize_cuda = lambda: None
    transport._c0_runtime = ring
    transport._load_c0_sync_body = lambda _path: (_ for _ in ()).throw(RuntimeError("load failed"))
    observed_depth = []

    def cleanup(_owner, _dispatcher):
        observed_depth.append(ring._model_operation_depth)
        return []

    transport._cleanup_c0_failure = cleanup
    with pytest.raises(RuntimeError, match="load failed"):
        transport._load_c0_sync("model")

    assert observed_depth == [1]
    assert ring._model_operation_depth == 0


def test_c0_stale_complete_selector_without_primary_v2_fails_before_arena(monkeypatch):
    monkeypatch.setenv("COMFYMODAL_GOLDEN_IO_PROCESS_V2_STREAMING", "1")
    monkeypatch.setenv("COMFYMODAL_GOLDEN_IO_PROCESS_V2_SOURCE_ENGINE", "mmap_fresh")
    monkeypatch.setenv("COMFYMODAL_GOLDEN_IO_PROCESS_V2_SOURCE_GEOMETRY", "qd4_64")
    monkeypatch.delenv("COMFYMODAL_GOLDEN_IO_PROCESS_V2", raising=False)

    with pytest.raises(RuntimeError, match="c0_requires_v2"):
        GoldenModelTransport()


def test_shared_arena_resolves_geometry_after_import(monkeypatch):
    from comfymodal_runtime import golden_io_process_v2 as c0

    monkeypatch.setenv("COMFYMODAL_GOLDEN_IO_PROCESS_V2", "1")
    monkeypatch.setenv("COMFYMODAL_GOLDEN_IO_PROCESS_V2_STREAMING", "1")
    monkeypatch.setenv("COMFYMODAL_GOLDEN_IO_PROCESS_V2_SOURCE_ENGINE", "mmap_fresh")
    monkeypatch.setenv("COMFYMODAL_GOLDEN_IO_PROCESS_V2_SOURCE_GEOMETRY", "qd4_64")

    ring = c0.SharedArenaRing()

    assert (ring.slot_count, ring.slot_bytes, ring.source_workers) == (8, BLOCK_BYTES, 4)
    assert ring.source_geometry == "qd4_64"


def test_c0_transport_geometry_defaults_to_qd4_64(monkeypatch):
    monkeypatch.delenv("COMFYMODAL_GOLDEN_C0_TRANSPORT_GEOMETRY", raising=False)

    geo = resolve_c0_transport_geometry()

    assert geo["name"] == "qd4_64"
    assert geo["queue_depth"] == QD == 4
    assert geo["block_bytes"] == BLOCK_BYTES == 64 * 1024 * 1024
    assert geo["producer_workers"] == 4
    assert geo["aggregation_enabled"] is False
    assert geo["required_slot_bytes"] == 64 * 1024 * 1024


def test_c0_transport_geometry_qd2_128(monkeypatch):
    monkeypatch.setenv("COMFYMODAL_GOLDEN_C0_TRANSPORT_GEOMETRY", "qd2_128")

    geo = resolve_c0_transport_geometry()

    assert geo["queue_depth"] == 2
    assert geo["block_bytes"] == 128 * 1024 * 1024
    assert geo["producer_workers"] == 2
    assert geo["required_slot_bytes"] == 128 * 1024 * 1024


def test_c0_transport_geometry_h2d128_keeps_64mib_source_windows(monkeypatch):
    monkeypatch.setenv("COMFYMODAL_GOLDEN_C0_TRANSPORT_GEOMETRY", "qd4_64_h2d128")

    geo = resolve_c0_transport_geometry()

    assert geo["queue_depth"] == 4
    assert geo["block_bytes"] == 64 * 1024 * 1024
    assert geo["aggregation_enabled"] is True
    assert geo["h2d_target_bytes"] == 128 * 1024 * 1024


def test_c0_transport_geometry_qd4_128(monkeypatch):
    monkeypatch.setenv("COMFYMODAL_GOLDEN_C0_TRANSPORT_GEOMETRY", "qd4_128")

    geo = resolve_c0_transport_geometry()

    assert geo["queue_depth"] == 4
    assert geo["block_bytes"] == 128 * 1024 * 1024
    assert geo["producer_workers"] == 4
    assert geo["aggregation_enabled"] is False
    assert geo["required_slot_bytes"] == 128 * 1024 * 1024
    assert geo["capacity_class"] == "c0-qd4-128m"


def test_c0_arena_geometry_qd4_128_keeps_512mib():
    from comfymodal_runtime.golden_io_process_v2 import (
        C0_ARENA_BYTES,
        resolve_c0_geometry,
    )

    resolved = resolve_c0_geometry("qd4_128")

    assert resolved["arena_bytes"] == C0_ARENA_BYTES == 536870912
    assert resolved["slot_bytes"] == 128 * 1024 * 1024
    assert resolved["slot_count"] == 4
    assert resolved["slot_bytes"] * resolved["slot_count"] == 536870912
    assert resolved["source_geometry"] == "qd4_128"


def test_c0_transport_geometry_unknown_fails_closed(monkeypatch):
    monkeypatch.setenv("COMFYMODAL_GOLDEN_C0_TRANSPORT_GEOMETRY", "qd8_256")

    with pytest.raises(ValueError, match="invalid C0 transport geometry"):
        resolve_c0_transport_geometry()


def test_c0_window_trace_defaults_off(monkeypatch):
    monkeypatch.delenv("COMFYMODAL_GOLDEN_C0_WINDOW_TRACE", raising=False)
    assert _c0_window_trace_enabled() is False
    monkeypatch.setenv("COMFYMODAL_GOLDEN_C0_WINDOW_TRACE", "1")
    assert _c0_window_trace_enabled() is True


def test_percentile_summary_math():
    assert _percentile_summary([]) == {"count": 0}
    assert _percentile_summary(["x", None, True]) == {"count": 0}

    summary = _percentile_summary([100_000_000, 200_000_000, 300_000_000, 400_000_000])

    assert summary["count"] == 4
    assert summary["min_ms"] == 100.0
    assert summary["max_ms"] == 400.0
    assert summary["p50_ms"] == pytest.approx(250.0)
    assert summary["mean_ms"] == pytest.approx(250.0)
    assert summary["sum_ms"] == pytest.approx(1000.0)


def test_summarize_c0_reader_tolerates_missing_attributes():
    summary = summarize_c0_reader(object())

    assert summary["fills"] == 0
    assert summary["map"] == {"count": 0}
    assert summary["worst_window"] is None
    assert summary["reader_pids"] == []


def test_summarize_c0_reader_collects_phases_and_worst_window():
    class FakeRing:
        backpressure_block_count = 3
        backpressure_block_ns = 9_000_000
        fills_submitted = 10
        fills_ready = 10

    class FakeReader:
        _ring = FakeRing()
        fills = 4
        fill_wall_ns = 1_000_000_000
        fd_open_count = 1
        fd_reuse_count = 3
        fd_close_count = 0
        _mmap_map_ns = [1_000_000, 2_000_000]
        _mmap_memcpy_ns = [200_000_000, 260_000_000]
        _mmap_munmap_ns = [5_000_000, 7_000_000]
        _mmap_pipe_rtt_ns = [210_000_000, 270_000_000]
        _mmap_gate_wait_ns = [0, 4_000_000]
        _mmap_minflt = [100, 120]
        _mmap_majflt = [0, 2]
        _mmap_reader_pids = {111, 222}
        _mmap_memcpy_first_ns = [200_000_000]
        _mmap_memcpy_reuse_ns = [260_000_000]
        _mmap_map_first_ns = []
        _mmap_map_reuse_ns = []
        _mmap_read_records = [
            {"mmap_op_ns": 100_000_000, "producer_id": 0,
             "source_range": [0, 67108864]},
            {"mmap_op_ns": 300_000_000, "producer_id": 2,
             "source_range": [134217728, 201326592]},
        ]

    summary = summarize_c0_reader(FakeReader())

    assert summary["fills"] == 4
    assert summary["ring_backpressure_blocks"] == 3
    assert summary["memcpy"]["count"] == 2
    assert summary["memcpy"]["max_ms"] == pytest.approx(260.0)
    assert summary["majflt_total"] == 2
    assert summary["reader_pids"] == [111, 222]
    assert summary["worst_window"]["producer_id"] == 2
    assert summary["worst_window"]["source_range"] == [134217728, 201326592]
    assert summary["memcpy_first_ms"] == pytest.approx(200.0)
    assert summary["memcpy_reuse_ms"] == pytest.approx(260.0)


def test_summarize_cpu_windows_reports_deltas():
    from comfymodal_runtime.golden_model_transport import _summarize_cpu_windows

    windows = {
        (66, "mmap_ru_utime_ns"): [1_000_000_000, 1_500_000_000],
        (66, "mmap_sched_wait_ns"): [100_000_000, 130_000_000],
        (67, "mmap_ru_utime_ns"): [2_000_000_000, 2_200_000_000],
        ("bad",): [1, 2],
        (68, "mmap_ru_utime_ns"): ["x", 5],
    }

    summary = _summarize_cpu_windows(windows)

    assert summary["utime_ms"] == pytest.approx(700.0)
    assert summary["stime_ms"] is None
    assert summary["sched_wait_ms"] == pytest.approx(30.0)
    assert summary["per_pid"]["66"]["mmap_ru_utime_ns"] == pytest.approx(500.0)
    assert _summarize_cpu_windows(None)["utime_ms"] is None
    assert _summarize_cpu_windows({})["per_pid"] == {}


def test_arena_ensure_detail_reports_establishment_cost():
    from comfymodal_runtime.golden_model_transport import arena_ensure_detail

    class FakeRuntime:
        size_bytes = 536870912
        slot_count = 8
        slot_bytes = 67108864
        backing_create_ms = 12.5
        register_ms = 44.0
        registered = True
        child_pid = 66
        child_start_ns = 1_000_000_000
        child_ready_ns = 1_300_000_000

    detail = arena_ensure_detail(FakeRuntime())

    assert detail["arena_bytes"] == 536870912
    assert detail["backing_create_ms"] == 12.5
    assert detail["register_ms"] == 44.0
    assert detail["child_startup_ms"] == pytest.approx(300.0)
    assert arena_ensure_detail(None)["arena_bytes"] is None
    assert arena_ensure_detail(object())["child_startup_ms"] is None


def test_summarize_dispatcher_tolerates_missing_telemetry():
    summary = summarize_dispatcher(object())

    assert summary["producer_capacity_block_count"] is None
    assert summary["min_free_slots"] is None
    assert summary["qd_depth_max"] is None
    assert summary["h2d_latency"] == {"count": 0}


def test_source_gbps_uses_only_positive_source_duration_boundary():
    assert _source_gbps(1_000_000_000, 1000.0) == pytest.approx(1.0)
    assert _source_gbps(1_000_000_000, 0.0) is None
    assert _source_gbps(1_000_000_000, None) is None


def test_c0_stage_reader_retains_terminal_child_source_timing_and_clock_domain():
    from comfymodal_runtime.golden_io_process_v2 import C0StageReader

    terminal = {
        "evidence": {
            "reader_aggregate": {
                "source_clock_domain": "child_perf_counter_ns",
                "source_first_enter_ns": 100,
                "source_last_exit_ns": 2100,
                "source_wall_ms": 0.002,
                "source_duration_ms": 0.002,
                "phase_aggregates": {"map": {"count": 1, "sum_ns": 7}},
                "records": [{"reader": 0, "records_digest_sha1": "a" * 40}],
            },
        },
    }
    reader = object.__new__(C0StageReader)
    reader.model_level_m2 = True
    reader._ring = SimpleNamespace(
        wait_for_model_terminal_evidence=lambda timeout_s=5.0: terminal,
    )

    assert reader.refresh_model_terminal_evidence()["evidence"]
    assert reader.child_source_clock_domain == "child_perf_counter_ns"
    assert reader.child_source_first_enter_ns == 100
    assert reader.child_source_last_exit_ns == 2100
    assert reader.child_source_wall_ms == pytest.approx(0.002)
    assert reader.child_source_phase_aggregates["map"]["sum_ns"] == 7
    assert reader.child_source_reader_summaries[0]["records_digest_sha1"] == "a" * 40


def test_c0_identity_is_c0_parallel_not_m2_arm():
    import inspect as _inspect

    source = _inspect.getsource(GoldenModelTransport._load_c0_sync_body)
    assert '"execution_architecture": "c0_parallel"' in source
    assert '"source_engine": "m2_exact_window"' in source
    assert '"c0_arena_bytes"' in source
    assert "m2_mmap_process" not in source
    assert "load_m2_safetensors" not in source
    assert "build_staging" not in source


def _terminal_result_for_layout(layout, *, status="done", exact_once=True):
    expected_bytes = int(layout.data_bytes)
    block_count = (expected_bytes + BLOCK_BYTES - 1) // BLOCK_BYTES
    expected_range = [int(layout.data_start), int(layout.data_start + expected_bytes)]
    reconciliation = {
        "expected_source_ranges": [expected_range],
        "actual_source_ranges": [expected_range],
        "expected_bytes": expected_bytes,
        "read_bytes": expected_bytes,
        "expected_block_count": block_count,
        "read_count": block_count,
        "gap_count": 0,
        "duplicate_count": 0,
        "out_of_range_count": 0,
        "exact_source_ranges": exact_once,
        "exact_once": exact_once,
        "records_digest_sha1": "child-digest",
    }
    aggregate = {
        "records": [{"reader": index, "records_digest_sha1": f"reader-{index}"}
                    for index in range(4)],
        "reconciliation": reconciliation,
    }
    evidence = {
        "status": status,
        "reader_aggregate": aggregate,
        "m2_authority": {
            "expected_sha1": M2_SOURCE_CORE_AUTHORITY_SHA1,
            "observed_sha1": M2_SOURCE_CORE_AUTHORITY_SHA1,
            "imported": True,
        },
    }
    return {
        "ok": status == "done" and exact_once,
        "fail_closed": status != "done" or not exact_once,
        "state": 3 if status == "done" else 4,
        "lifecycle": {"terminal_status": 1 if status == "done" else 2},
        "evidence": evidence,
        "error": None if status == "done" else "child_error",
    }


def test_c0_source_proof_rejects_h2d_or_planned_records_without_terminal_child_evidence(tmp_path):
    path = tmp_path / "model.safetensors"
    _write_safetensors(path, "tensor", b"abcdefgh")
    transport = GoldenModelTransport()
    layout = transport.inspect(str(path))
    source = SimpleNamespace(
        _mmap_read_records=[],
        planned_ranges=[[layout.data_start, layout.data_start + layout.data_bytes]],
        h2d_coverage={"bytes": layout.data_bytes, "blocks": 1},
    )

    proof = c0_source_coverage_proof(source, layout)

    assert proof["reconciled"] is False
    assert proof["reason"] == "child_terminal_evidence_absent"


def test_c0_source_proof_uses_child_aggregate_digest_and_reconciliation(tmp_path):
    path = tmp_path / "model.safetensors"
    _write_safetensors(path, "tensor", b"abcdefgh")
    transport = GoldenModelTransport()
    layout = transport.inspect(str(path))

    proof = c0_source_coverage_proof(
        SimpleNamespace(_mmap_read_records=[]),
        layout,
        _terminal_result_for_layout(layout),
    )

    assert proof["authority"] == "child_reported_source_range/physical"
    assert proof["covers_entire_file_exactly_once"] is True
    assert proof["child_read_count"] == 1
    assert proof["child_read_bytes"] == 8
    assert proof["records_are_bounded_summaries"] is True
    assert proof["records_digest_sha1"] == "child-digest"
    assert proof["proof_source"] == "parent_full_range_validation"
    assert proof["range_list_truncated"] is False
    assert proof["range_digest"] == "child-digest"
    assert proof["raw_range_list_complete"] is True


def test_c0_source_proof_accepts_bounded_exact_child_aggregate(tmp_path):
    path = tmp_path / "model.safetensors"
    _write_safetensors(path, "tensor", b"abcdefgh")
    layout = GoldenModelTransport().inspect(str(path))
    terminal = _terminal_result_for_layout(layout)
    terminal["evidence"]["evidence_truncated"] = True
    # The control-SHM range sample is bounded and may be absent; the child's
    # exact aggregate remains the physical source proof.
    terminal["evidence"]["reader_aggregate"]["reconciliation"]["actual_source_ranges"] = []

    proof = c0_source_coverage_proof(SimpleNamespace(_mmap_read_records=[]), layout, terminal)

    assert proof["covers_entire_file_exactly_once"] is True
    assert proof["proof_source"] == "child_aggregate_reconciliation"
    assert proof["range_list_truncated"] is True
    assert proof["range_digest"] == "child-digest"
    assert proof["raw_range_list_complete"] is False
    assert proof["ranges"] == []


def test_c0_source_proof_rejects_inconsistent_bounded_child_aggregate(tmp_path):
    path = tmp_path / "model.safetensors"
    _write_safetensors(path, "tensor", b"abcdefgh")
    layout = GoldenModelTransport().inspect(str(path))
    terminal = _terminal_result_for_layout(layout)
    terminal["evidence"]["evidence_truncated"] = True
    terminal["evidence"]["reader_aggregate"]["reconciliation"]["read_bytes"] -= 1

    proof = c0_source_coverage_proof(SimpleNamespace(_mmap_read_records=[]), layout, terminal)

    assert proof["reconciled"] is False
    assert proof["reason"] == "child_source_reconciliation_mismatch"
    assert proof["reconciliation"]["reason"] == "child_source_reconciliation_mismatch"


def test_c0_source_proof_authority_mismatch_reason_includes_bounded_child_identity(tmp_path):
    path = tmp_path / "model.safetensors"
    _write_safetensors(path, "tensor", b"abcdefgh")
    layout = GoldenModelTransport().inspect(str(path))
    terminal = _terminal_result_for_layout(layout)
    terminal["evidence"]["m2_authority"].update({
        "expected_sha1": "expected-child-sha1",
        "observed_sha1": "observed-child-sha1",
        "expected_path": "expected-path-" + ("x" * 600),
        "observed_path": "observed-path-" + ("y" * 600),
        "imported": True,
    })

    proof = c0_source_coverage_proof(SimpleNamespace(_mmap_read_records=[]), layout, terminal)

    reason = proof["reason"]
    assert proof["reconciled"] is False
    assert reason.startswith("child_authority_hash_mismatch:")
    assert "expected_sha1=expected-child-sha1" in reason
    assert "observed_sha1=observed-child-sha1" in reason
    assert "expected_path=expected-path-" in reason
    assert "observed_path=observed-path-" in reason
    assert "x" * 600 not in reason
    assert "y" * 600 not in reason
    assert "...<truncated>" in reason
    assert proof["reconciliation"]["reason"] == reason


def test_c0_source_proof_rejects_terminal_child_error(tmp_path):
    path = tmp_path / "model.safetensors"
    _write_safetensors(path, "tensor", b"abcdefgh")
    layout = GoldenModelTransport().inspect(str(path))

    proof = c0_source_coverage_proof(
        SimpleNamespace(_mmap_read_records=[]),
        layout,
        _terminal_result_for_layout(layout, status="error", exact_once=False),
    )

    assert proof["reconciled"] is False
    assert proof["no_fallback"] is False


def test_c0_failure_cleanup_releases_owner_only_after_proven_quiescence(monkeypatch):
    class Owner:
        released = False
        release_count = 0

        def release_storage(self):
            self.released = True
            self.release_count += 1

    class Dispatcher:
        def __init__(self):
            self.cancelled = False
            self._thread = None
            self._queue = []
            self._handoff = {}
            self._uncertain_handoffs = {}
            self._in_flight = {}
            self._late_submissions = {}
            self._unresolved_late_submission_keys = set()
            self.unresolved_late_events = 0
            self.cleanup_errors = ()

        def cancel(self, *, deadline):
            self.cancelled = deadline > 0

        def _cleanup_cancelled(self, deadline):
            assert deadline > 0

    transport = GoldenModelTransport()
    owner = Owner()
    dispatcher = Dispatcher()
    closed = []
    def shutdown():
        closed.append(True)
        transport._c0_shutdown_status = {"resolved": True}
        return transport._c0_shutdown_status

    monkeypatch.setattr(transport, "shutdown", shutdown)

    errors = transport._cleanup_c0_failure(owner, SimpleNamespace(dispatcher=dispatcher))

    assert errors == []
    assert owner.released is True
    assert dispatcher.cancelled is True
    assert closed == [True]
    assert transport._poisoned is True
    assert transport.cleanup_unresolved is False
    assert transport.owner_retained is False
    transport._cleanup_c0_failure(owner, SimpleNamespace(dispatcher=dispatcher))
    assert owner.release_count == 1


def test_c0_failure_cleanup_retains_owner_when_dispatcher_late_work_is_unresolved(monkeypatch):
    class Owner:
        released = False

        def release_storage(self):
            self.released = True

    class Dispatcher:
        _thread = None
        _queue = []
        _handoff = {}
        _uncertain_handoffs = {}
        _in_flight = {}
        _late_submissions = {17: object()}
        _unresolved_late_submission_keys = {17}
        unresolved_late_events = 1
        cleanup_errors = ()

        def cancel(self, *, deadline):
            assert deadline > 0

        def _cleanup_cancelled(self, deadline):
            assert deadline > 0

    transport = GoldenModelTransport()
    owner = Owner()
    dispatcher = Dispatcher()
    monkeypatch.setattr(
        transport,
        "shutdown",
        lambda: {"resolved": True},
    )

    errors = transport._cleanup_c0_failure(owner, SimpleNamespace(dispatcher=dispatcher))

    assert errors
    assert owner.released is False
    assert transport._active_c0_owner is owner
    assert transport._poisoned is True
    assert transport.cleanup_unresolved is True
    assert transport.owner_retained is True
    assert transport._c0_cleanup_diagnostics["dispatcher_resolved"] is False


def test_c0_boundaries_use_monotonic_clock_domain():
    source = inspect.getsource(GoldenModelTransport._load_c0_sync_body)
    assert '"clock_domain": "monotonic_ns"' in source
    assert "started_mono_ns" in source
    assert "started_ns = time.perf_counter_ns()" not in source
    assert "first_source_read_start_mono_ns" in source


def test_m2_authority_mismatch_fails_closed(monkeypatch):
    import comfymodal_runtime.golden_model_transport as module

    monkeypatch.setattr(module, "m2_source_core_sha1", lambda: "not-the-authority")
    with pytest.raises(RuntimeError, match="authority_mismatch"):
        module.m2_source_core_parity()


def test_sticky_lanes_are_contiguous_and_cover_every_block_once():
    ranges = _sticky_lane_ranges(11)

    assert ranges == ((0, 3), (3, 6), (6, 9), (9, 11))
    assert [block for start, end in ranges for block in range(start, end)] == list(range(11))


@pytest.mark.parametrize("total_blocks", range(1, 8))
def test_c0_m2_plan_matches_exact_64m_publications_for_small_models(total_blocks):
    tail = 17
    data_bytes = (total_blocks - 1) * BLOCK_BYTES + tail
    lanes, ranges = c0_m2_block_plan(4096, data_bytes)

    assert lanes == _sticky_lane_ranges(total_blocks, QD)
    assert [(item.record_id, item.source_offset, item.target_offset, item.length)
            for item in ranges] == [
        (block_id, 4096 + block_id * BLOCK_BYTES,
         block_id * BLOCK_BYTES,
         BLOCK_BYTES if block_id < total_blocks - 1 else tail)
        for block_id in range(total_blocks)
    ]
    assert all(
        ranges[start].record_id == start and ranges[end - 1].record_id == end - 1
        for start, end in lanes if start < end
    )


def test_c0_m2_plan_has_no_static_e27_partition_or_aggregation():
    import comfymodal_runtime.golden_qd_transport as qd_transport

    lanes, ranges = c0_m2_block_plan(0, 3 * BLOCK_BYTES + 9)
    config = qd_transport.TransportConfig(
        queue_depth=4, block_bytes=BLOCK_BYTES, staging_slots=8,
        producer_workers=4, aggregation_enabled=False,
        sticky_lane_ranges=lanes,
    )
    transport = qd_transport.GoldenQDTransport(
        config, qd_transport.FakeBackend(), arm=qd_transport.C0_M2_ARM,
    )
    assert transport.arm == qd_transport.C0_M2_ARM
    assert [item.record_id for lane in qd_transport.plan_c0_m2_block_work(
        ranges, lanes, block_bytes=BLOCK_BYTES
    )[1] for item in lane] == list(range(4))


def test_persistent_reader_keeps_frozen_source_ordering_contract():
    source = inspect.getsource(_persistent_reader_load)

    assert "for lane, (start, end) in enumerate(lane_ranges)" in source
    assert "_alloc_gate(" in source
    assert "_MAP_PRIVATE, fd, window_start" in source
    assert "_MAP_POPULATE" not in source
    assert source.index("published.value = sequence + 1") < source.index("_LIBC.munmap")


def test_destination_reserve_uses_three_aligned_generic_capacity_tiers():
    gib = 1024**3
    capacities = _destination_reserve_capacities(80 * gib, 80 * gib)

    assert len(capacities) == 3
    assert capacities[0] > capacities[1] > capacities[2]
    assert all(capacity % DESTINATION_ALIGNMENT == 0 for capacity in capacities)
    assert sum(capacities) <= int(80 * gib * 0.30)


def test_destination_pool_uses_best_fit_and_fresh_lease_wrappers(monkeypatch):
    class FakeTensor:
        def __init__(self, size):
            self.size = size
            self.device = "cuda:0"

    monkeypatch.setattr(
        GpuDestinationPool,
        "_allocate",
        staticmethod(lambda _device, capacity: FakeTensor(capacity)),
    )
    pool = GpuDestinationPool("cuda:0")
    pool.reserve([60, 40, 20])

    medium = pool.acquire(35)
    large = pool.acquire(50)
    small = pool.acquire(10)
    growth = pool.acquire(5)

    assert (medium.capacity_bytes, large.capacity_bytes, small.capacity_bytes) == (40, 60, 20)
    assert medium.reused and large.reused and small.reused
    assert growth.capacity_bytes == 5
    assert growth.reused is False
    medium.release_storage()
    replacement = pool.acquire(30)
    assert replacement is not medium
    assert replacement.capacity_bytes == 40
    assert replacement.reused is True
    assert medium.released is True


def test_prepare_cpu_fails_closed_if_cuda_was_already_initialized(monkeypatch):
    fake_torch = SimpleNamespace(
        cuda=SimpleNamespace(is_initialized=lambda: True),
    )
    monkeypatch.setitem(sys.modules, "torch", fake_torch)
    monkeypatch.setattr("comfymodal_runtime.golden_model_transport.os.name", "posix")
    monkeypatch.setattr(
        "comfymodal_runtime.golden_model_transport.mp.get_all_start_methods",
        lambda: ["fork"],
    )

    with pytest.raises(RuntimeError, match="must_fork_before_cuda"):
        GoldenModelTransport().prepare_cpu()


def test_persistent_reader_fd_cache_closes_fd_from_identity_tuple(monkeypatch):
    closed = []
    monkeypatch.setattr("comfymodal_runtime.m2_source_core.os.close", closed.append)
    cache = OrderedDict({"model.safetensors": (17, (1, 2, 3, 4))})

    _persistent_reader_close_fds(cache)

    assert closed == [17]
    assert not cache


def test_c0_model_command_carries_exact_m2_load_contract():
    from comfymodal_runtime.golden_io_process_v2 import C0ModelLoad, validate_c0_model_load

    command = C0ModelLoad(
        path="/models/model.safetensors",
        identity=(1, 2, 3, 4),
        source_offset=128,
        data_bytes=65 * 1024 * 1024,
        read_bytes=64 * 1024 * 1024,
        total_blocks=2,
        lane_ranges=((0, 1), (1, 1), (1, 1), (1, 2)),
        generation=7,
    )
    validate_c0_model_load(command)
    payload = command.as_dict()
    assert payload["command"] == "LOAD"
    assert payload["read_bytes"] == 64 * 1024 * 1024
    assert payload["total_blocks"] == 2
    assert payload["lane_ranges"] == [[0, 1], [1, 1], [1, 1], [1, 2]]
    assert payload["generation"] == 7


def test_c0_m2_control_has_two_slots_per_lane_and_consumes_only_in_order():
    from comfymodal_runtime.golden_io_process_v2 import C0M2Control, C0ModelLoad

    control = C0M2Control(arena_epoch=1)
    try:
        assert control.SLOTS_PER_LANE == 2
        assert control.LANE_BYTES == 128 * 1024 * 1024
        control.submit(C0ModelLoad(
            "model.safetensors", (1, 2, 3, 4), 0, 64 * 1024 * 1024,
            64 * 1024 * 1024, 1, ((0, 1), (1, 1), (1, 1), (1, 1)), 1,
        ))
        import struct
        base = control.lane_offset(0)
        struct.pack_into("<QQQQQQ", control.buf, base, 1, 0, 0, 0, 64 * 1024 * 1024, 0)
        assert control.wait_for_offset(0, 64 * 1024 * 1024, 0) == (0, 0, 1)
        with pytest.raises(Exception, match="consume_before_publication"):
            control.consume((0, 0, 2))
        control.consume((0, 0, 1))
    finally:
        control.close()


def test_c0_m2_stale_publication_ticket_cannot_consume_new_generation():
    from comfymodal_runtime.golden_io_process_v2 import C0ModelLoad, C0ProtocolError

    control = C0M2Control(arena_epoch=1)
    command = C0ModelLoad(
        "model.safetensors", (1, 2, 3, 4), 0, 64 * 1024 * 1024,
        64 * 1024 * 1024, 1, ((0, 1), (1, 1), (1, 1), (1, 1)), 1,
    )
    try:
        control.submit(command)
        struct.pack_into(
            "<QQQQQQ", control.buf, control.lane_offset(0), 1, 0, 0, 0,
            64 * 1024 * 1024, 0,
        )
        stale_ticket = control.wait_for_offset(0, 64 * 1024 * 1024, 0)
        struct.pack_into("<I", control.buf, 12, control.STATE_DONE)

        # The next generation may reset only after the old H2D ticket is
        # consumed; retain the ticket object to prove stale rejection below.
        control.consume(stale_ticket)
        control.submit(command)
        assert control.current_generation() == 2
        assert control.publication(0)[1] == 0
        with pytest.raises(C0ProtocolError, match="stale_generation"):
            control.consume(stale_ticket)
        assert control.publication(0)[1] == 0
    finally:
        control.close()


def test_c0_m2_submit_waits_for_pending_lane_before_resetting_counters():
    from comfymodal_runtime.golden_io_process_v2 import C0ModelLoad

    control = C0M2Control(arena_epoch=1)
    command = C0ModelLoad(
        "model.safetensors", (1, 2, 3, 4), 0, 64 * 1024 * 1024,
        64 * 1024 * 1024, 1, ((0, 1), (1, 1), (1, 1), (1, 1)), 1,
    )
    try:
        control.submit(command)
        struct.pack_into(
            "<QQQQQQ", control.buf, control.lane_offset(0), 1, 0, 0, 0,
            64 * 1024 * 1024, 0,
        )
        ticket = control.wait_for_offset(0, 64 * 1024 * 1024, 0)
        struct.pack_into("<I", control.buf, 12, control.STATE_DONE)
        started = threading.Event()
        submitted = threading.Event()

        def submit_next():
            started.set()
            control.submit(command, timeout_s=1.0)
            submitted.set()

        thread = threading.Thread(target=submit_next)
        thread.start()
        assert started.wait(1.0)
        assert not submitted.wait(0.02)
        assert control.publication(0)[:2] == (1, 0)
        control.consume(ticket)
        thread.join(1.0)
        assert not thread.is_alive()
        assert submitted.is_set()
        assert control.current_generation() == 2
        assert control.publication(0)[:2] == (0, 0)
    finally:
        control.close()


def test_c0_m2_submit_quiescence_timeout_does_not_reset_counters():
    from comfymodal_runtime.golden_io_process_v2 import C0ModelLoad, C0ProtocolError

    control = C0M2Control(arena_epoch=1)
    command = C0ModelLoad(
        "model.safetensors", (1, 2, 3, 4), 0, 64 * 1024 * 1024,
        64 * 1024 * 1024, 1, ((0, 1), (1, 1), (1, 1), (1, 1)), 1,
    )
    try:
        control.submit(command)
        struct.pack_into(
            "<QQQQQQ", control.buf, control.lane_offset(0), 1, 0, 0, 0,
            64 * 1024 * 1024, 0,
        )
        struct.pack_into("<I", control.buf, 12, control.STATE_DONE)
        with pytest.raises(C0ProtocolError, match=(
            r"c0_model_publication_quiescence_timeout:.*"
            r"lane=0,published=1,consumed=0"
        )):
            control.submit(command, timeout_s=0.001)
        assert control.current_generation() == 1
        assert control.publication(0)[:2] == (1, 0)
    finally:
        control.close()


def test_c0_m2_publication_mutex_blocks_late_consume_during_reset():
    from comfymodal_runtime.golden_io_process_v2 import C0ModelLoad, C0ProtocolError

    control = C0M2Control(arena_epoch=1)
    command = C0ModelLoad(
        "model.safetensors", (1, 2, 3, 4), 0, 64 * 1024 * 1024,
        64 * 1024 * 1024, 1, ((0, 1), (1, 1), (1, 1), (1, 1)), 1,
    )
    try:
        control.submit(command)
        struct.pack_into(
            "<QQQQQQ", control.buf, control.lane_offset(0), 1, 1, 0, 0,
            64 * 1024 * 1024, 0,
        )
        struct.pack_into("<I", control.buf, 12, control.STATE_DONE)
        stale_ticket = c0.C0PublicationTicket(0, 0, 1, control.current_generation())

        reset_entered = threading.Event()
        release_reset = threading.Event()
        consume_finished = threading.Event()
        consume_error = []
        original_reset = control._reset_lane

        def blocked_reset(lane):
            if lane == 0:
                reset_entered.set()
                assert release_reset.wait(1.0)
            original_reset(lane)

        control._reset_lane = blocked_reset

        submit_thread = threading.Thread(target=lambda: control.submit(command, timeout_s=1.0))
        submit_thread.start()
        assert reset_entered.wait(1.0)
        assert struct.unpack_from("<QQ", control.buf, control.lane_offset(0)) == (1, 1)

        def late_consume():
            try:
                control.consume(stale_ticket)
            except C0ProtocolError as exc:
                consume_error.append(str(exc))
            finally:
                consume_finished.set()

        consume_thread = threading.Thread(target=late_consume)
        consume_thread.start()
        assert not consume_finished.wait(0.02)

        release_reset.set()
        submit_thread.join(1.0)
        consume_thread.join(1.0)
        assert not submit_thread.is_alive()
        assert not consume_thread.is_alive()
        assert consume_error == ["c0_model_consume_stale_generation"]
        assert all(control.publication(lane)[:2] == (0, 0)
                   for lane in range(control.LANE_COUNT))
    finally:
        control.close()


def test_m2_shared_array_adapter_writes_control_shm_and_matches_publication_snapshot():
    source = ast.parse(c0._C0_M2_CHILD_SOURCE)
    assert '"slot_off": [MappedU64Array(control_buf' in c0._C0_M2_CHILD_SOURCE
    assert '"slot_len": [MappedU64Array(control_buf' in c0._C0_M2_CHILD_SOURCE
    adapter_node = next(
        node for node in source.body
        if isinstance(node, ast.ClassDef) and node.name == "MappedU64Array"
    )
    namespace = {"struct": struct}
    exec(
        compile(ast.Module(body=[adapter_node], type_ignores=[]), "<m2-shared-array>", "exec"),
        namespace,
    )

    lane = 2
    control = C0M2Control(arena_epoch=1)
    try:
        adapter_type = namespace["MappedU64Array"]
        offsets = adapter_type(
            control.buf, control.slot_off_offset(lane, 0), control.SLOTS_PER_LANE
        )
        lengths = adapter_type(
            control.buf, control.slot_len_offset(lane, 0), control.SLOTS_PER_LANE
        )
        offsets[0], offsets[1] = 64, 128
        lengths[0], lengths[1] = 32, 16
        c0._C0MappedU64(control.buf, control.published_offset(lane)).value = 2

        assert control.publication(lane) == (2, 0, (64, 128), (32, 16))
        assert struct.unpack_from("<QQ", control.buf, control.slot_off_offset(lane, 0)) == (64, 128)
        assert struct.unpack_from("<QQ", control.buf, control.slot_len_offset(lane, 0)) == (32, 16)
    finally:
        control.close()


def _publish_terminal_control_state(control, state, payload, *, error=""):
    raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    assert len(raw) <= control.EVIDENCE_BYTES
    terminal = control.TERMINAL_DONE if state == control.STATE_DONE else control.TERMINAL_ERROR
    struct.pack_into(
        "<8I", control.buf, control.LIFECYCLE_COMMAND_OFFSET,
        control.COMMAND_NONE, control.ACK_NONE, 0, int(state == control.STATE_ERROR),
        control.LANE_COUNT, control.LANE_COUNT, terminal, len(raw),
    )
    error_start = control.LANE_BYTES_OFFSET + control.LANE_COUNT * control.LANE_RECORD_BYTES
    control.buf[error_start:error_start + control.ERROR_BYTES] = b"\0" * control.ERROR_BYTES
    if error:
        encoded = str(error).encode("utf-8")[: control.ERROR_BYTES - 1]
        control.buf[error_start:error_start + len(encoded)] = encoded
    control.buf[control.EVIDENCE_OFFSET:control.EVIDENCE_OFFSET + control.EVIDENCE_BYTES] = b"\0" * control.EVIDENCE_BYTES
    control.buf[control.EVIDENCE_OFFSET:control.EVIDENCE_OFFSET + len(raw)] = raw
    struct.pack_into("<I", control.buf, control.EVIDENCE_LENGTH_OFFSET, len(raw))
    struct.pack_into("<I", control.buf, 12, state)


def test_c0_m2_terminal_evidence_wait_success_and_error():
    payload = {"status": "done", "reader_aggregate": {"reconciliation": {}}}
    control = C0M2Control(arena_epoch=1)
    try:
        _publish_terminal_control_state(control, control.STATE_DONE, payload)
        result = control.wait_for_terminal_evidence(timeout_s=0.01)
        assert result["ok"] is True
        assert result["terminal_evidence"] == payload
        assert result["lifecycle"]["terminal_status"] == control.TERMINAL_DONE
    finally:
        control.close()

    control = C0M2Control(arena_epoch=1)
    try:
        error_payload = {"status": "error", "error": "reader_failed"}
        _publish_terminal_control_state(
            control, control.STATE_ERROR, error_payload, error="reader_failed"
        )
        result = control.wait_for_terminal_evidence(timeout_s=0.01)
        assert result["ok"] is False
        assert result["fail_closed"] is True
        assert result["error"] == "reader_failed"
        assert result["terminal_evidence"] == error_payload
    finally:
        control.close()


@pytest.mark.parametrize("pending_status", ["running", "progress"])
def test_c0_m2_terminal_evidence_waits_through_stale_progress_race(
    monkeypatch, pending_status
):
    control = C0M2Control(arena_epoch=1)
    try:
        _publish_terminal_control_state(
            control,
            control.STATE_DONE,
            {"status": pending_status, "progress": {"stage": "settling"}},
        )
        first_stale_read = threading.Event()
        original_evidence = control.evidence

        def observe_stale_evidence():
            evidence = original_evidence()
            if evidence.get("status") == pending_status:
                first_stale_read.set()
            return evidence

        monkeypatch.setattr(control, "evidence", observe_stale_evidence)

        def publish_final_evidence():
            assert first_stale_read.wait(1.0)
            _publish_terminal_control_state(
                control,
                control.STATE_DONE,
                {"status": "done", "reader_aggregate": {"reconciliation": {}}},
            )

        publisher = threading.Thread(target=publish_final_evidence)
        publisher.start()
        result = control.wait_for_terminal_evidence(timeout_s=0.2)
        publisher.join(1.0)

        assert result["ok"] is True
        assert result["timeout"] is False
        assert result["terminal_evidence"]["status"] == "done"
    finally:
        control.close()


def test_c0_m2_terminal_evidence_pending_race_fails_closed_at_bound():
    control = C0M2Control(arena_epoch=1)
    try:
        _publish_terminal_control_state(
            control,
            control.STATE_DONE,
            {"status": "running", "progress": {"stage": "settling"}},
        )

        result = control.wait_for_terminal_evidence(timeout_s=0.001)

        assert result["ok"] is False
        assert result["timeout"] is True
        assert result["fail_closed"] is True
        assert result["evidence"]["status"] == "running"
    finally:
        control.close()


def test_c0_m2_terminal_evidence_status_mismatch_formats_bounded_diagnostics():
    payload = {
        "status": "error",
        "evidence_truncated": True,
        "warning": "evidence warning " + ("w" * 400),
    }
    control = C0M2Control(arena_epoch=1)
    try:
        _publish_terminal_control_state(
            control,
            control.STATE_DONE,
            payload,
            error="control error " + ("c" * 400),
        )

        result = control.wait_for_terminal_evidence(timeout_s=0.01)

        assert result["ok"] is False
        assert result["fail_closed"] is True
        message = result["error"]
        assert message.startswith("c0_model_terminal_evidence_status_mismatch:")
        assert "state=3" in message
        assert "expected_terminal=1" in message
        assert "lifecycle_terminal_status=1" in message
        assert "evidence_status=error" in message
        assert "evidence_truncated=True" in message
        assert "warning=evidence warning " in message
        assert "control_error=control error " in message
        assert "w" * 161 not in message
        assert "c" * 161 not in message
    finally:
        control.close()


def test_c0_m2_terminal_evidence_wait_times_out_without_terminal_state():
    control = C0M2Control(arena_epoch=1)
    try:
        result = control.wait_for_terminal_evidence(timeout_s=0.001)
        assert result["ok"] is False
        assert result["timeout"] is True
        assert result["fail_closed"] is True
        assert result["error"] == "c0_model_terminal_evidence_timeout"
    finally:
        control.close()


def test_c0_m2_publication_timeout_reports_bounded_lifecycle_diagnostics():
    from comfymodal_runtime.golden_io_process_v2 import C0ModelLoad, C0ProtocolError

    control = C0M2Control(arena_epoch=1)
    try:
        control.submit(C0ModelLoad(
            "model.safetensors", (1, 2, 3, 4), 0, 64 * 1024 * 1024,
            64 * 1024 * 1024, 1, ((0, 1), (1, 1), (1, 1), (1, 1)), 1,
        ))
        _publish_terminal_control_state(
            control,
            control.STATE_ERROR,
            {
                "status": "error",
                "reader_aggregate": {
                    "read_count": 1,
                    "read_bytes": 64 * 1024 * 1024,
                    "records": [{"detail": "x" * 1800}],
                    "reconciliation": {
                        "expected_block_count": 1,
                        "read_count": 1,
                        "read_bytes": 64 * 1024 * 1024,
                        "gap_count": 0,
                        "duplicate_count": 0,
                        "out_of_range_count": 0,
                        "exact_once": True,
                    },
                },
            },
            error="reader_failed:" + ("x" * 1000),
        )
        # Keep the publication wait non-terminal while leaving terminal
        # evidence available for the timeout diagnostic.
        struct.pack_into("<I", control.buf, 12, control.STATE_REQUESTED)

        with pytest.raises(C0ProtocolError) as caught:
            control.wait_for_offset(0, 64 * 1024 * 1024, 0, timeout_s=0)

        message = str(caught.value)
        assert "c0_model_publication_timeout" in message
        assert "state=1" in message
        assert "command=0" in message
        assert "ack=0" in message
        assert "coordinator_alive=0" in message
        assert "failed=1" in message
        assert "readers_reaped=4" in message
        assert "terminal=2" in message
        assert "evidence_length=" in message
        assert "control_error=reader_failed:" in message
        assert "terminal_evidence_status=error" in message
        assert '"read_count":1' in message
        assert '"exact_once":true' in message
        assert "detail" not in message
        assert len(message) < 2048
    finally:
        control.close()


def test_c0_m2_publication_timeout_formats_compact_reader_stage_before_progress():
    payload = {
        "status": "running",
        "progress": {
            "adapter_stages": [{
                "reader": 0,
                "command_sent": True,
                "command_sent_ns": 101,
                "ready_sent": True,
                "ready_sent_ns": 102,
                "load_received": True,
                "load_received_ns": 103,
                "processing": True,
                "processing_ns": 104,
                "load_done_sent": False,
                "error_sent": False,
            }],
        },
    }
    control = C0M2Control(arena_epoch=1)
    try:
        _publish_terminal_control_state(control, control.STATE_ERROR, payload)
        diagnostic = control._publication_timeout_diagnostics()

        reader_stage = diagnostic.index("reader_stage=")
        progress = diagnostic.index("progress=")
        assert reader_stage < progress
        assert '"reader":0' in diagnostic
        assert '"command_sent":true' in diagnostic
        assert '"command_sent_ns":101' in diagnostic
        assert '"ready_sent":true' in diagnostic
        assert '"load_received":true' in diagnostic
        assert '"processing":true' in diagnostic
        assert '"load_done_sent":false' in diagnostic
        assert '"error_sent":false' in diagnostic
        assert '"ready_sent_ns":102' in diagnostic
        assert '"load_received_ns":103' in diagnostic
        assert '"processing_ns":104' in diagnostic
    finally:
        control.close()


def test_c0_m2_publication_timeout_formats_bounded_lane_snapshots():
    control = C0M2Control(arena_epoch=1)
    try:
        for lane in range(control.LANE_COUNT):
            base = control.lane_offset(lane)
            struct.pack_into(
                "<QQQQQQ",
                control.buf,
                base,
                lane + 2,
                lane,
                1000 + lane,
                2000 + lane,
                3000 + lane,
                4000 + lane,
            )
        diagnostic = control._publication_timeout_diagnostics()

        assert diagnostic.count('"pub":') == control.LANE_COUNT
        assert diagnostic.count('"i":') == control.LANE_COUNT
        assert '"con":0,"i":0,"lengths":[3000,4000],"offsets":[1000,2000],"pub":2' in diagnostic
        assert '"length":4000,"offset":2000,"sequence":2,"slot":1' in diagnostic
        assert '"con":3,"i":3,"lengths":[3003,4003],"offsets":[1003,2003],"pub":5' in diagnostic
        assert len(diagnostic) < 4096
    finally:
        control.close()


def test_c0_m2_publication_timeout_formats_progress_summary_before_long_progress():
    payload = {
        "status": "running",
        "progress": {
            "stage": "waiting_load_done",
            "completed": 2,
            "claimed_blocks": 1,
            "owned_blocks": 1,
            "ownership_counts": {"0": 2, "1": 1, "2": 1},
            "total_blocks": 4,
            "current_generation": 9,
            "adapter_stages": [{"reader": index} for index in range(16)],
        },
    }
    control = C0M2Control(arena_epoch=1)
    try:
        _publish_terminal_control_state(control, control.STATE_ERROR, payload)
        diagnostic = control._publication_timeout_diagnostics()

        summary = diagnostic.index("progress_summary=")
        progress = diagnostic.index("progress=")
        assert summary < progress
        assert (
            '"claimed_blocks":1,"completed":2,"generation":9,'
            '"owned_blocks":1,"ownership_counts":{"0":2,"1":1,"2":1},'
            '"stage":"waiting_load_done","total_blocks":4'
        ) in diagnostic
    finally:
        control.close()


def test_c0_m2_heartbeat_and_reader_summary_are_bounded():
    heartbeat_ns = 123456789
    payload = {
        "status": "running",
        "progress_heartbeat_ns": heartbeat_ns,
        "progress": {
            "completed": 2,
            "completed_value": 2,
            "claimed_blocks": 1,
            "owned_blocks": 1,
            "ownership_counts": {"0": 2, "1": 1, "2": 1},
            "total_blocks": 4,
            "current_generation": 9,
            "adapter_stages": [{
                "reader": index,
                "command_sent": True,
                "response_received": index < 2,
                "command_sent_ns": 100 + index,
                "response_received_ns": 200 + index if index < 2 else None,
            } for index in range(C0M2Control.LANE_COUNT)],
        },
        "reader_summary": [
            {"reader": index, "pid": 100 + index, "alive": True, "exitcode": None}
            for index in range(C0M2Control.LANE_COUNT)
        ],
    }
    control = C0M2Control(arena_epoch=1)
    try:
        _publish_terminal_control_state(control, control.STATE_ERROR, payload)
        struct.pack_into(
            "<Q", control.buf, control.PROGRESS_HEARTBEAT_NS_OFFSET, heartbeat_ns
        )
        struct.pack_into("<I", control.buf, 12, control.STATE_RUNNING)

        lifecycle = control.lifecycle()
        evidence = control.evidence()
        diagnostic = control._publication_timeout_diagnostics()

        assert lifecycle["progress_heartbeat_ns"] == heartbeat_ns
        assert len(evidence["reader_summary"]) == control.LANE_COUNT
        assert evidence["progress"]["current_generation"] == 9
        assert lifecycle["evidence_length"] <= control.EVIDENCE_BYTES
        assert f"progress_heartbeat_ns={heartbeat_ns}" in diagnostic
        assert '"completed":2' in diagnostic
        assert "adapter_stages" in diagnostic
        assert "reader_summary=" in diagnostic
        assert len(diagnostic) < 2048
    finally:
        control.close()


def test_c0_m2_stolen_publication_routes_exact_stealer_slot_and_waits_for_h2d():
    from comfymodal_runtime.golden_io_process_v2 import C0M2Control, C0StageReader

    control = C0M2Control(arena_epoch=1)
    pool = StagingPool(slots=8, block_bytes=64, buffers=[bytearray(64) for _ in range(8)])
    item = SourceRange(0, 64, 0, "stolen-block")
    try:
        # The original target-derived slot is 0, but lane 2 (global slot 4)
        # claimed and published the block.
        base = control.lane_offset(2)
        struct.pack_into("<QQQQQQ", control.buf, base, 1, 0, 0, 0, 64, 0)
        reader = object.__new__(C0StageReader)
        reader._ring = SimpleNamespace(
            m2_bridge_enabled=True,
            slot_bytes=64,
            slot_count=8,
            m2_control=control,
            model_publication=lambda destination, length, preferred, **kwargs: control.wait_for_offset(
                destination, length, preferred, **kwargs
            ),
            slot_base_address=lambda slot: ctypes.addressof(
                ctypes.c_char.from_buffer(pool._slots[slot].buffer)
            ),
        )
        reader._pool = pool
        reader.model_level_m2 = True
        reader._publication_lock = threading.Lock()
        reader._publications = {}
        reader.fills = 0
        reader.source_bytes = 0

        # The preferred hook blocks until publication and returns the actual
        # stealer slot, which is the exact slot the dispatcher must acquire.
        assert reader.preferred_slot_index(item) == 4
        lease = pool.acquire(declared_range=item, preferred_slot_index=4)
        assert lease.slot_index == 4

        target = lease._read_target(64)
        assert reader.readinto_lease(lease, target, 0, 0) == 64
        assert control.publication(2)[1] == 0  # H2D has not completed yet.

        control.consume(lease._c0_session_ticket)
        assert control.publication(2)[1] == 1
    finally:
        control.close()


def test_c0_m2_partial_non_aligned_bounded_extent_warns_and_uses_actual_slot():
    from comfymodal_runtime.golden_io_process_v2 import (
        C0M2Control,
        C0ProtocolError,
        C0StageReader,
    )

    control = C0M2Control(arena_epoch=1)
    try:
        # The target is neither slot-aligned nor a full slot.  M2 publishes it
        # in lane 1, slot 0; the returned slot must follow that publication.
        base = control.lane_offset(1)
        struct.pack_into("<QQQQQQ", control.buf, base, 1, 0, 65, 0, 17, 0)
        reader = object.__new__(C0StageReader)
        reader._ring = SimpleNamespace(
            m2_bridge_enabled=True,
            slot_bytes=64,
            slot_count=8,
            model_publication=lambda destination, length, preferred, **kwargs: control.wait_for_offset(
                destination, length, preferred, **kwargs
            ),
        )
        reader.model_level_m2 = True
        reader._publication_lock = threading.Lock()
        reader._publications = {}
        reader.preferred_extent_warnings = []

        item = SourceRange(3, 17, 65, "partial-nonaligned")
        with pytest.warns(RuntimeWarning, match="bounded_partial_or_non_aligned_extent"):
            assert reader.preferred_slot_index(item) == 2
        assert reader.preferred_extent_warnings == [{
            "kind": "c0_model_bounded_partial_or_non_aligned_extent",
            "source_offset": 3,
            "target_offset": 65,
            "length": 17,
            "slot_bytes": 64,
        }]

        with pytest.raises(C0ProtocolError, match="bounded_preferred_slot_extent"):
            reader.preferred_slot_index(
                SimpleNamespace(target_offset=-1, length=17, source_offset=3, record_id="negative")
            )
    finally:
        control.close()


def test_m2_authority_import_hash_and_api_parity_are_explicit():
    assert M2_SOURCE_CORE_AUTHORITY_SHA1 == "00ddc40a3226208c208c93dd03b3d24417c8eb35"
    parity = m2_source_core_parity()
    assert parity["authority_sha1"] == M2_SOURCE_CORE_AUTHORITY_SHA1
    assert parity["loaded_sha1"] == m2_source_core_sha1()
    assert parity["persistent_reader_main"] is True
    assert parity["persistent_reader_load"] is True


def test_c0_m2_child_source_is_cuda_sterile_and_uses_exact_authority_symbols():
    from comfymodal_runtime.golden_io_process_v2 import _C0_M2_CHILD_SOURCE

    assert "import torch" not in _C0_M2_CHILD_SOURCE
    assert "m2_source_core.persistent_reader_main" in _C0_M2_CHILD_SOURCE
    assert "m2_source_core._persistent_reader_load" in _C0_M2_CHILD_SOURCE
    assert "mmap_reader_round_trip" not in _C0_M2_CHILD_SOURCE
