"""Offline proof that Golden source telemetry is attached to physical reads."""

from __future__ import annotations

import threading

import pytest

from comfymodal_runtime import golden_serial as gs
from comfymodal_runtime.e27_source_mechanism import ActualSourceTelemetry


def _telemetry() -> ActualSourceTelemetry:
    return ActualSourceTelemetry(
        regions=((0, 4), (4, 8), (8, 12), (12, 16)),
        expected_ranges=((0, 16),),
    )


def test_preadv_events_are_one_per_physical_syscall_and_capture_retries(monkeypatch):
    telemetry = _telemetry()
    barrier = threading.Barrier(4)
    calls: dict[int, int] = {}
    lock = threading.Lock()

    def fake_preadv(_fd, buffers, offset):
        view = buffers[0]
        with lock:
            attempt = calls.get(offset - (offset % 4), 0)
            calls[offset - (offset % 4)] = attempt + 1
        if attempt == 0:
            count = 2
            view[:count] = bytes((offset + n) % 256 for n in range(count))
            barrier.wait()
        else:
            count = len(view)
            view[:count] = bytes((offset + n) % 256 for n in range(count))
        return count

    monkeypatch.setattr(gs.os, "preadv", fake_preadv, raising=False)

    def worker(producer_id: int):
        target = bytearray(4)
        assert gs._read_at(
            producer_id,
            memoryview(target),
            producer_id * 4,
            actual_source=telemetry,
            producer_id=producer_id,
            destination_offset=producer_id * 4,
        ) == 4

    threads = [threading.Thread(target=worker, args=(producer,)) for producer in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    report = telemetry.report()
    events = report["actual_source_events"]
    assert len(events) == 8
    assert report["actual_source_inflight"] == 0
    assert report["max_actual_source_inflight"] == 4
    assert {event["retry_number"] for event in events} == {0, 1}
    assert sum(event["short_read"] for event in events) == 4
    assert {event["producer_id"] for event in events} == {0, 1, 2, 3}
    assert {event["region_id"] for event in events} == {0, 1, 2, 3}
    assert all(event["requested_bytes"] >= event["returned_bytes"] for event in events)
    assert all(
        event["syscall_exit_monotonic_ns"] >= event["syscall_enter_monotonic_ns"]
        for event in events
    )


def test_serial_physical_reads_do_not_claim_qd4(monkeypatch):
    telemetry = _telemetry()

    def fake_preadv(_fd, buffers, offset):
        view = buffers[0]
        view[:] = bytes((offset + n) % 256 for n in range(len(view)))
        return len(view)

    monkeypatch.setattr(gs.os, "preadv", fake_preadv, raising=False)
    for producer_id in range(4):
        target = bytearray(4)
        assert gs._read_at(
            producer_id,
            memoryview(target),
            producer_id * 4,
            actual_source=telemetry,
            producer_id=producer_id,
            destination_offset=producer_id * 4,
        ) == 4

    report = telemetry.report()
    assert len(report["actual_source_events"]) == 4
    assert report["max_actual_source_inflight"] == 1
    assert report["qd_occupancy_ms"]["4"] == 0


def test_physical_read_exception_closes_actual_source_transition(monkeypatch):
    telemetry = _telemetry()

    def fail_preadv(_fd, _buffers, _offset):
        raise OSError("synthetic source failure")

    monkeypatch.setattr(gs.os, "preadv", fail_preadv, raising=False)
    with pytest.raises(OSError, match="synthetic source failure"):
        gs._read_at(
            0,
            memoryview(bytearray(4)),
            0,
            actual_source=telemetry,
            producer_id=0,
        )

    report = telemetry.report()
    assert report["actual_source_inflight"] == 0
    assert len(report["actual_source_events"]) == 1
    assert report["actual_source_events"][0]["error"] == "synthetic source failure"
