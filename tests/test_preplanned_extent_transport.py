from __future__ import annotations

import threading
import time

import pytest

from comfymodal_runtime.golden_qd_transport import (
    EventStatus,
    ExtentTransportError,
    FakeBackend,
    PreplannedExtentTransport,
    SourceRange,
    TransportConfig,
    plan_preplanned_extents,
    validate_preplanned_extents,
)
from comfymodal_runtime import preplanned_extent_transport as transport_module


def test_planner_uses_independent_source_block_and_h2d_extent():
    extents = plan_preplanned_extents(20, 6, 10)
    assert [extent.length for extent in extents] == [10, 10]
    assert [read.length for read in extents[0].reads] == [6, 4]
    assert validate_preplanned_extents(extents, 20) == (True, "ok")


def test_planner_preserves_partial_final_extent_without_gaps_or_overlap():
    extents = plan_preplanned_extents(23, 8, 10)
    assert [extent.length for extent in extents] == [10, 10, 3]
    assert validate_preplanned_extents(extents, 23) == (True, "ok")
    assert [read.destination_offset for extent in extents for read in extent.reads] == [0, 8, 10, 18, 20]


def test_validation_accepts_explicit_nonzero_source_and_destination_bases():
    extents = plan_preplanned_extents(
        12, 5, 8, source_offset=100, destination_offset=40
    )
    assert validate_preplanned_extents(
        extents, 12, source_offset=100, destination_offset=40
    ) == (True, "ok")
    assert validate_preplanned_extents(extents, 12) == (
        False,
        "read_destination_mismatch",
    )


def test_validation_rejects_read_with_wrong_destination_even_when_each_side_covers():
    extents = list(plan_preplanned_extents(8, 4, 8))
    reads = list(extents[0].reads)
    reads[0] = reads[0].__class__(0, 4, 4, 0, 0)
    extents[0] = extents[0].__class__(0, 0, 8, tuple(reads))
    assert validate_preplanned_extents(extents, 8) == (
        False,
        "read_destination_mismatch",
    )


def test_transport_rejects_undersized_extent_buffers():
    transport = PreplannedExtentTransport(
        source_qd=1,
        source_block_bytes=4,
        h2d_copy_bytes=8,
        h2d_inflight_depth=1,
        source_capacity=1,
        buffers=[bytearray(7)],
    )
    with pytest.raises(ExtentTransportError, match="extent_buffer_capacity"):
        transport.execute(
            plan_preplanned_extents(8, 4, 8),
            lambda offset, length: b"x" * length,
            FakeBackend(),
            total_bytes=8,
        )


def test_pipeline_records_authoritative_h2d_submit_and_completion_observer():
    class Observer:
        def __init__(self):
            self.events = {}

        def record_h2d_submit(self, nbytes, *, timestamp_ns):
            token = len(self.events) + 1
            self.events[token] = [nbytes, timestamp_ns, None]
            return token

        def record_h2d_complete(self, token, *, timestamp_ns):
            self.events[token][2] = timestamp_ns

    observer = Observer()
    result = PreplannedExtentTransport(
        source_qd=1,
        source_block_bytes=4,
        h2d_copy_bytes=8,
        h2d_inflight_depth=1,
        source_capacity=1,
        buffers=[bytearray(8)],
    ).execute(
        plan_preplanned_extents(8, 4, 8),
        lambda offset, length: b"x" * length,
        FakeBackend(),
        total_bytes=8,
        h2d_observer=observer,
    )
    telemetry = result["telemetry"]
    assert telemetry["h2d_submit_count"] == telemetry["h2d_completion_count"] == 1
    assert telemetry["h2d_submitted_bytes"] == telemetry["h2d_completed_bytes"] == 8
    assert len(observer.events) == 1 and observer.events[1][2] is not None


def test_transport_bounds_join_when_h2d_never_completes():
    transport = PreplannedExtentTransport(
        source_qd=1,
        source_block_bytes=4,
        h2d_copy_bytes=8,
        h2d_inflight_depth=1,
        source_capacity=1,
        buffers=[bytearray(8)],
        cleanup_timeout=0.05,
    )
    started = time.monotonic()
    with pytest.raises(ExtentTransportError, match="join_timeout"):
        transport.execute(
            plan_preplanned_extents(8, 4, 8),
            lambda offset, length: b"x" * length,
            FakeBackend(event_uncertain=True),
            total_bytes=8,
        )
    assert time.monotonic() - started < 1


def test_configured_knobs_do_not_implicitly_control_one_another():
    config = TransportConfig(
        source_qd=8,
        source_block_bytes=32,
        h2d_copy_bytes=256,
        h2d_inflight_depth=1,
        source_capacity=2,
    )
    assert (config.source_qd, config.source_block_bytes) == (8, 32)
    assert (config.h2d_copy_bytes, config.h2d_inflight_depth) == (256, 1)
    assert config.source_capacity == 2


def test_source_qd_is_independent_of_h2d_depth_and_slots_are_reused():
    data = bytes(range(60))
    backend = FakeBackend(h2d_delay_polls=3)
    transport = PreplannedExtentTransport(
        source_qd=8,
        source_block_bytes=5,
        h2d_copy_bytes=10,
        h2d_inflight_depth=1,
        source_capacity=2,
        buffers=[bytearray(10)],
    )
    extents = plan_preplanned_extents(60, 5, 10)
    result = transport.execute(extents, lambda offset, length: data[offset : offset + length], backend, total_bytes=60)
    assert result["output"] == data
    telemetry = result["telemetry"]
    assert telemetry["configured_source_qd"] == 8
    assert telemetry["configured_h2d_inflight_depth"] == 1
    assert telemetry["achieved_h2d_inflight_depth_max"] == 1
    assert telemetry["extent_slot_count"] == 1
    assert telemetry["h2d_copy_count"] == 6
    assert telemetry["h2d_copy_bytes"] == 60
    assert telemetry["configured_source_qd"] == 8
    assert telemetry["configured_source_capacity"] == 2
    assert telemetry["source_capacity_semantics"] == "buffering_work_capacity_only"
    assert telemetry["cpu_allocation"]["cpu_request"] == telemetry["cpu_request"]
    assert telemetry["post_hoc_aggregation"] is False
    assert [event[1] for event in backend.submissions] == [10] * 6


def test_exact_physical_read_telemetry_records_requested_and_returned_bytes():
    data = b"abcdefghij"
    calls = []

    def reader(offset, length):
        calls.append((offset, length))
        return data[offset : offset + min(length, 3)]

    transport = PreplannedExtentTransport(
        source_qd=2,
        source_block_bytes=4,
        h2d_copy_bytes=8,
        h2d_inflight_depth=2,
        source_capacity=2,
        buffers=[bytearray(8), bytearray(8)],
    )
    result = transport.execute(
        plan_preplanned_extents(10, 4, 8), reader, FakeBackend(), total_bytes=10
    )
    events = result["telemetry"]["physical_reads"]
    assert calls == [(0, 4), (3, 1), (4, 4), (7, 1), (8, 2)]
    assert [(event["requested_bytes"], event["returned_bytes"]) for event in events] == [
        (4, 3), (1, 1), (4, 3), (1, 1), (2, 2)
    ]
    assert result["telemetry"]["source_requested_bytes"] == 12
    assert result["telemetry"]["source_returned_bytes"] == 10


def test_achieved_qd_is_time_weighted_over_active_interval_including_qd0():
    telemetry = transport_module._PipelineTelemetry(8, 4, 8, 1, 8)
    timestamps = iter((100, 110, 130, 160, 200, 260))

    original = transport_module.time.monotonic_ns
    transport_module.time.monotonic_ns = lambda: next(timestamps)
    try:
        telemetry.source_transition(1, 0)   # 100: QD 0 -> 1
        telemetry.source_transition(1, 1)   # 110: QD 1 -> 2
        telemetry.source_transition(-1, 1)  # 130: QD 2 -> 1
        telemetry.source_transition(-1, 0)  # 160: QD 1 -> 0
        telemetry.source_transition(1, 0)   # 200: QD 0 -> 1
        telemetry.source_transition(-1, 0)  # 260: QD 1 -> 0
    finally:
        transport_module.time.monotonic_ns = original

    report = telemetry.snapshot()
    # Integral = 1*10 + 2*20 + 1*30 + 0*40 + 1*60 = 140;
    # active wall = 260 - 100 = 160.
    assert report["achieved_source_qd_mean"] == 140 / 160
    assert report["achieved_source_qd_max"] == 2
    assert report["source_active_interval_start_ns"] == 100
    assert report["source_active_interval_end_ns"] == 260
    assert report["source_active_wall_ns"] == 160
    assert report["qd_occupancy_ns"] == {
        str(depth): value for depth, value in {0: 40, 1: 100, 2: 20, 3: 0,
                                                4: 0, 5: 0, 6: 0, 7: 0, 8: 0}.items()
    }
    assert report["qd_occupancy_ms"]["0"] == 40 / 1e6


def test_pipeline_retains_worker_busy_time_and_physical_intervals():
    data = b"abcdefgh"
    result = PreplannedExtentTransport(
        source_qd=2,
        source_block_bytes=4,
        h2d_copy_bytes=8,
        h2d_inflight_depth=1,
        source_capacity=8,
        buffers=[bytearray(8)],
        metadata={"physical_read_provenance": "golden_serial._read_at"},
    ).execute_source_only(
        plan_preplanned_extents(len(data), 4, 8),
        lambda offset, length: data[offset:offset + length],
        total_bytes=len(data),
    )
    telemetry = result["telemetry"]
    assert telemetry["source_worker_busy_ns"] >= 0
    assert telemetry["source_worker_busy_ms"] >= 0
    assert telemetry["physical_read_provenance"] == "golden_serial._read_at"
    assert telemetry["physical_reads"]
    assert all(
        event["syscall_exit_monotonic_ns"] >= event["syscall_enter_monotonic_ns"]
        and event["requested_bytes"] >= event["returned_bytes"]
        and event["physical_provenance"] == "golden_serial._read_at"
        for event in telemetry["physical_reads"]
    )


def test_ready_extent_waits_for_all_source_regions_before_one_h2d_submission():
    entered = threading.Event()
    release = threading.Event()

    def reader(offset, length):
        if offset == 0:
            entered.set()
            release.wait(timeout=1)
        return bytes([offset]) * length

    transport = PreplannedExtentTransport(
        source_qd=2,
        source_block_bytes=4,
        h2d_copy_bytes=8,
        h2d_inflight_depth=1,
        source_capacity=2,
        buffers=[bytearray(8)],
    )
    backend = FakeBackend()
    output = []

    def run():
        output.append(transport.execute(plan_preplanned_extents(8, 4, 8), reader, backend, total_bytes=8))

    thread = threading.Thread(target=run)
    thread.start()
    assert entered.wait(timeout=1)
    time.sleep(0.01)
    assert backend.submissions == []
    release.set()
    thread.join(timeout=1)
    assert not thread.is_alive()
    assert output[0]["telemetry"]["h2d_copy_count"] == 1
