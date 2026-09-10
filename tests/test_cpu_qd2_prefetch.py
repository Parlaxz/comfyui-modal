from __future__ import annotations

import json
import inspect
import os
import threading
import time

import pytest

from comfymodal_runtime import golden_serial as gs


pytestmark = pytest.mark.fast_unit


def _fixture(tmp_path):
    payload = b"abcdefgh"
    header = {"weight": {"dtype": "U8", "shape": [len(payload)], "data_offsets": [0, len(payload)]}}
    encoded = json.dumps(header, separators=(",", ":")).encode("utf-8")
    path = tmp_path / "clip.safetensors"
    path.write_bytes(len(encoded).to_bytes(8, "little") + encoded + payload)
    parsed = gs.parse_safetensors_header(str(path))
    layout = gs.FrozenClipSourceLayout(
        path=str(path), file_size_bytes=parsed["size_bytes"], data_start=parsed["data_start"],
        total_data_bytes=parsed["total_data_bytes"], header=parsed["header"],
        tensor_map=tuple(gs.build_header_tensor_map(parsed["header"])),
        regions=tuple(tuple(r) for r in gs.plan_source_regions(parsed["data_start"], parsed["total_data_bytes"], 4, 2)),
        qd=2, block_bytes=4,
    )
    return path, layout, payload


def _preadv_for(path, payload, *, short=False, gate=None, fail_offset=None):
    source = path.read_bytes()
    calls: list[tuple[int, int]] = []
    lock = threading.Lock()
    short_offsets: set[int] = set()

    def fake(fd, vectors, offset):
        offset = int(offset)
        if gate is not None and offset == gate[0]:
            gate[1].set()
            gate[2].wait(timeout=2)
        if fail_offset is not None and offset == fail_offset:
            return 0
        data = source[offset:offset + len(vectors[0])]
        count = len(data)
        if short and offset not in short_offsets and count > 1:
            count //= 2
            short_offsets.add(offset)
        vectors[0][:count] = data[:count]
        with lock:
            calls.append((offset, count))
        return count

    return fake, calls


def test_qd2_geometry_is_128m_and_contiguous_half_owned():
    extent = gs.CPU_QD2_SOURCE_EXTENT_BYTES
    regions = gs.plan_source_regions(100, extent * 59 + 126090240, extent, 2)
    assert len(regions) == 2
    assert all(regions)
    assert sum(len(region) for region in regions) == 60
    assert len(regions[0]) == 30
    assert len(regions[1]) == 30
    assert regions[0][-1][0] + regions[0][-1][1] == regions[1][0][0]


def test_qd2_source_and_h2d_geometry_are_independent():
    total = 128 * 1024 * 1024 * 2
    source = gs.plan_source_regions(0, total, 128 * 1024 * 1024, 2)
    h2d = gs.plan_source_regions(0, total, 32 * 1024 * 1024, 2)
    assert [length for _start, length in source[0] + source[1]] == [
        128 * 1024 * 1024,
        128 * 1024 * 1024,
    ]
    assert len(h2d[0] + h2d[1]) == 8
    assert all(length == 32 * 1024 * 1024 for region in h2d for _start, length in region)
    assert gs.partition_coverage(
        [(start, start + length) for region in h2d for start, length in region], total
    )[0]


def test_h2d_enqueue_boundary_is_after_copy_and_event_queueing():
    source = inspect.getsource(gs._qd_gpu_worker)
    copy_position = source.index("gpu_buf[rel : rel + ln].copy_")
    event_position = source.index("event.record()", copy_position)
    enqueue_position = source.index("cpu_prefetch_ticket.mark_h2d_enqueue(", event_position)
    assert copy_position < event_position < enqueue_position


def test_two_real_workers_preadv_exact_coverage_and_cleanup(tmp_path, monkeypatch):
    path, layout, payload = _fixture(tmp_path)
    fake, calls = _preadv_for(path, payload)
    monkeypatch.setattr(os, "preadv", fake, raising=False)
    ticket = gs.CpuRawPrefetchTicket(layout)
    ticket.start()
    ticket.join()
    telemetry = ticket.telemetry()
    assert telemetry["source_owner_count"] == 1
    assert telemetry["source_lifecycle_count"] == 1
    assert telemetry["worker_count"] == 2
    assert telemetry["worker_extents"] == {"0": 1, "1": 1}
    assert telemetry["worker_bytes"] == {"0": 4, "1": 4}
    assert telemetry["ready_bytes_total"] == len(payload)
    assert telemetry["contiguous_prefix_bytes"] == len(payload)
    assert telemetry["ready_extent_count"] == 2
    assert telemetry["source_provenance"] == "actual_os_preadv"
    assert telemetry["expected_h2d_count"] == 1
    assert telemetry["expected_h2d_ranges"] == [[0, len(payload)]]
    assert telemetry["syscall_count"] == len(calls) == 2
    assert telemetry["syscall_bytes"] == len(payload)
    assert sorted((r["offset"], r["bytes"]) for r in telemetry["syscall_records"]) == [(layout.data_start, 4), (layout.data_start + 4, 4)]
    assert telemetry["ready_intervals"] == [(0, 4), (4, 8)]
    assert bytes(ticket.read_range(0, len(payload))) == payload
    ticket.close()
    assert ticket.telemetry()["raw_backing_released"] is True
    assert not any(t.is_alive() for t in ticket._threads)


def test_out_of_order_extent_readiness_never_exposes_gap(tmp_path, monkeypatch):
    path, layout, payload = _fixture(tmp_path)
    started = threading.Event()
    release = threading.Event()
    fake, _calls = _preadv_for(path, payload, gate=(layout.data_start, started, release))
    monkeypatch.setattr(os, "preadv", fake, raising=False)
    ticket = gs.CpuRawPrefetchTicket(layout)
    ticket.start()
    assert started.wait(timeout=2)
    # Worker 1 owns the second extent and may publish out of order.
    assert bytes(ticket.read_range(4, 4)) == payload[4:]
    result: list[bytes] = []
    reader = threading.Thread(target=lambda: result.append(bytes(ticket.read_range(0, 8))))
    reader.start()
    time.sleep(0.02)
    assert reader.is_alive()
    release.set()
    reader.join(timeout=2)
    ticket.join()
    assert result == [payload]
    assert ticket.telemetry()["contiguous_prefix_bytes"] == len(payload)
    events = ticket.events
    source_complete = next(event for event in events if event["name"] == "CPU_PREFETCH_SOURCE_COMPLETE")
    worker_ends = [event for event in events if "SOURCE_WORKER_" in event["name"] and event["name"].endswith("_END")]
    assert len(worker_ends) == 2
    assert max(event["monotonic_ns"] for event in worker_ends) <= source_complete["monotonic_ns"]
    assert events.index(worker_ends[0]) < events.index(source_complete)
    assert events.index(worker_ends[1]) < events.index(source_complete)
    ticket.close()


def test_lifecycle_events_snapshot_source_state_before_later_completion(tmp_path):
    _path, layout, _payload = _fixture(tmp_path)
    ticket = gs.CpuRawPrefetchTicket(layout)

    # H2D_START is deliberately emitted before the source completion marker.
    # The later final-state counters must not be projected backward into it.
    ticket.mark_h2d_start()
    with ticket._condition:
        ticket._bytes_read = layout.total_data_bytes
        ticket._bytes_available = layout.total_data_bytes
        ticket._contiguous_prefix_bytes = layout.total_data_bytes
        ticket._ready_intervals = [(0, layout.total_data_bytes)]
        ticket._worker_bytes = {0: layout.total_data_bytes, 1: 0}
        ticket._worker_extents = {0: 1, 1: 0}
        ticket._complete = True
    ticket.event("CPU_PREFETCH_SOURCE_COMPLETE")

    events = ticket.events
    h2d = next(event for event in events if event["name"] == "H2D_START")
    complete = next(event for event in events if event["name"] == "CPU_PREFETCH_SOURCE_COMPLETE")
    h2d_source = h2d["fields"]["source_snapshot"]
    complete_source = complete["fields"]["source_snapshot"]

    assert events.index(h2d) < events.index(complete)
    assert h2d["monotonic_ns"] <= complete["monotonic_ns"]
    assert h2d_source["source_complete"] is False
    assert h2d_source["ready_bytes_total"] == 0
    assert h2d_source["contiguous_prefix_bytes"] == 0
    assert h2d_source["ready_extent_count"] == 0
    assert complete_source["source_complete"] is True
    assert complete_source["ready_bytes_total"] == layout.total_data_bytes
    assert complete_source["source_complete_monotonic_ns"] == complete["monotonic_ns"]

    telemetry = ticket.telemetry()
    assert telemetry["ready_bytes_total"] == layout.total_data_bytes
    assert telemetry["ready_bytes_total_at_h2d_start"] == 0
    assert telemetry["contiguous_prefix_bytes_at_h2d_start"] == 0


def test_event_source_snapshot_is_not_mutated_by_event_or_counter_mutation(tmp_path):
    _path, layout, _payload = _fixture(tmp_path)
    ticket = gs.CpuRawPrefetchTicket(layout)
    ticket.mark_h2d_start()
    first = next(event for event in ticket.events if event["name"] == "H2D_START")
    original = json.loads(json.dumps(first["fields"]["source_snapshot"]))

    # Mutating both the ticket and a caller-owned events copy cannot alter the
    # source state captured with the original lifecycle event.
    first["fields"]["source_snapshot"]["worker_bytes"]["0"] = 999
    with ticket._condition:
        ticket._bytes_read = layout.total_data_bytes
        ticket._contiguous_prefix_bytes = layout.total_data_bytes
        ticket._ready_intervals = [(0, layout.total_data_bytes)]
        ticket._worker_bytes = {0: layout.total_data_bytes, 1: 0}
    current = next(event for event in ticket.events if event["name"] == "H2D_START")

    assert original["ready_bytes_total"] == 0
    assert original["worker_bytes"] == {"0": 0, "1": 0}
    assert current["fields"]["source_snapshot"]["ready_bytes_total"] == 0
    assert current["fields"]["source_snapshot"]["worker_bytes"] == {"0": 0, "1": 0}


def test_short_read_retries_are_exact_and_proven(tmp_path, monkeypatch):
    path, layout, payload = _fixture(tmp_path)
    fake, calls = _preadv_for(path, payload, short=True)
    monkeypatch.setattr(os, "preadv", fake, raising=False)
    ticket = gs.CpuRawPrefetchTicket(layout)
    ticket.start()
    ticket.join()
    telemetry = ticket.telemetry()
    assert telemetry["source_provenance"] == "actual_os_preadv"
    assert telemetry["short_read_retries"] == 4
    assert telemetry["syscall_count"] == len(calls) == 6
    assert telemetry["syscall_bytes"] == len(payload)
    ticket.close()


def test_short_read_zero_fails_closed_and_releases_backing(tmp_path, monkeypatch):
    path, layout, _payload = _fixture(tmp_path)
    fake, _calls = _preadv_for(path, b"", fail_offset=layout.data_start)
    monkeypatch.setattr(os, "preadv", fake, raising=False)
    ticket = gs.CpuRawPrefetchTicket(layout)
    ticket.start()
    with pytest.raises(RuntimeError, match="cpu_prefetch_source_failed"):
        ticket.join()
    assert ticket.telemetry()["raw_backing_released"] is True
    assert not any(t.is_alive() for t in ticket._threads)


def test_missing_preadv_fails_closed_without_fallback(tmp_path, monkeypatch):
    _path, layout, _payload = _fixture(tmp_path)
    monkeypatch.delattr(os, "preadv", raising=False)
    ticket = gs.CpuRawPrefetchTicket(layout)
    with pytest.raises(RuntimeError, match="preadv_unavailable"):
        ticket.start()
    assert ticket.telemetry()["raw_backing_released"] is True
    assert ticket._threads == []


def test_request_selector_and_transport_contracts():
    request = gs.GoldenRequest("r", {})
    assert request.cpu_qd2_prefetch is False
    assert request.deep_trace_level == "off"


def test_qd2_telemetry_projection_names_boundaries_and_invariants():
    telemetry = {
        "total_bytes": 8,
        "logical_extent_count": 2,
        "expected_h2d_ranges": [[0, 4], [4, 8]],
        "h2d_enqueue_records": [
            {"extent_id": "0:0", "relative_start": 0, "length": 4, "monotonic_ns": 150},
            {"extent_id": "1:0", "relative_start": 4, "length": 4, "monotonic_ns": 260},
        ],
        "h2d_completion_records": [
            {"extent_id": "0:0", "relative_start": 0, "length": 4, "monotonic_ns": 220},
            {"extent_id": "1:0", "relative_start": 4, "length": 4, "monotonic_ns": 320},
        ],
        "ready_bytes_total_at_h2d_start": 4,
        "ready_extent_count_at_h2d_start": 1,
        "h2d_outstanding": 0,
        "h2d_finalized": True,
    }
    events = [
        {"name": "CPU_PREFETCH_START", "monotonic_ns": 100, "wall_ns": 1000, "fields": {}},
        {"name": "CPU_PREFETCH_FIRST_EXTENT", "monotonic_ns": 120, "wall_ns": 1020, "fields": {}},
        {
            "name": "H2D_START", "monotonic_ns": 150, "wall_ns": 1050,
            "fields": {"source_completed_before_h2d": False},
        },
        {"name": "CPU_PREFETCH_SOURCE_COMPLETE", "monotonic_ns": 250, "wall_ns": 1150, "fields": {}},
        {"name": "CLIP_GPU_READY", "monotonic_ns": 340, "wall_ns": 1240, "fields": {}},
    ]

    projected = gs.project_cpu_qd2_telemetry(telemetry, events=events)

    assert projected["qd2_source_start_monotonic_ns"] == 100
    assert projected["qd2_first_extent_ready_monotonic_ns"] == 120
    assert projected["qd2_first_h2d_enqueue_monotonic_ns"] == 150
    assert projected["qd2_first_h2d_completion_monotonic_ns"] == 220
    assert projected["qd2_source_completion_monotonic_ns"] == 250
    assert projected["qd2_final_h2d_enqueue_monotonic_ns"] == 260
    assert projected["qd2_final_h2d_completion_monotonic_ns"] == 320
    assert projected["qd2_load_ready_monotonic_ns"] == 340
    assert projected["qd2_exact_copied_coverage"]["ok"] is True
    assert projected["qd2_duplicate_range_status"] == "none"
    assert projected["qd2_missing_range_status"] == "none"
    assert projected["qd2_bytes_ready_at_first_h2d"] == 4
    assert projected["qd2_extents_ready_at_first_h2d"] == 1
    assert projected["qd2_h2d_before_source_complete"] is True
    assert projected["qd2_source_duration_ns"] == 150
    assert projected["qd2_h2d_active_wall_ns"] == 130
    assert projected["qd2_h2d_envelope_wall_ns"] == 170
    assert projected["qd2_source_h2d_overlap_wall_ns"] == 70
    assert projected["qd2_exposed_h2d_after_source_completion_ns"] == 60
    assert projected["qd2_no_outstanding_h2d_at_finalization"] is True
    json.dumps(projected)


def test_qd2_projection_reports_duplicate_and_missing_ranges():
    projected = gs.project_cpu_qd2_telemetry(
        {
            "total_bytes": 8,
            "logical_extent_count": 2,
            "expected_h2d_ranges": [[0, 4], [4, 8]],
            "h2d_enqueue_records": [],
            "h2d_completion_records": [
                {"relative_start": 0, "length": 4, "monotonic_ns": 10},
                {"relative_start": 0, "length": 4, "monotonic_ns": 11},
            ],
            "h2d_outstanding": 1,
            "h2d_finalized": False,
        }
    )
    assert projected["qd2_exact_copied_coverage"]["ok"] is False
    assert projected["qd2_duplicate_range_status"] == "present"
    assert projected["qd2_missing_range_status"] == "present"
    assert projected["qd2_no_outstanding_h2d_at_finalization"] is False


@pytest.mark.parametrize(
    "telemetry",
    [
        {
            "h2d_completion_records": [],
        },
        {
            "expected_h2d_ranges": [[0, 4]],
            "h2d_completion_records": [{"relative_start": 0, "length": "4"}],
        },
    ],
)
def test_qd2_projection_fails_closed_on_absent_or_malformed_coverage(telemetry):
    projected = gs.project_cpu_qd2_telemetry(telemetry)
    assert projected["qd2_exact_copied_coverage"]["ok"] is False
