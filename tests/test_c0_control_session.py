from __future__ import annotations

import re
import threading
from types import SimpleNamespace

import pytest

import comfymodal_runtime.golden_io_process_v2 as c0_io
from comfymodal_runtime.golden_io_process_v2 import (
    _C0_CHILD_SOURCE,
    _C0_WINDOW_TRACE_LIMIT,
    C0ControlLayout,
    C0FillRequest,
    C0ProtocolError,
    C0StageReader,
    C0SourceSession,
    reconcile_destination_coverage,
)
from comfymodal_runtime.golden_qd_transport import (
    FakeBackend,
    GoldenQDTransport,
    SourceRange,
    StagingPool,
    TransportConfig,
)
from tools.benchmark_v2_direct import _golden_p1_request_pairing


pytestmark = pytest.mark.fast_unit


def _request(request_id: int, producer_id: int = 0) -> C0FillRequest:
    return C0FillRequest(
        request_id=request_id,
        arena_epoch=7,
        role="clip",
        source="/tmp/checkpoint.safetensors",
        slot_index=request_id % 4,
        slot_generation=1,
        source_offset=request_id * 8,
        destination_offset=request_id * 8,
        length=8,
        producer_id=producer_id,
    )


def _ready(session: C0SourceSession, ticket) -> None:
    request = C0ControlLayout.read_request(session.shm.buf, ticket.lane)
    C0ControlLayout.write_response(
        session.shm.buf,
        ticket.lane,
        ticket.sequence,
        {
            "op": "ready",
            "request_id": request["request_id"],
            "arena_epoch": request["arena_epoch"],
            "slot_index": request["slot_index"],
            "slot_generation": request["slot_generation"],
            "returned_bytes": request["length"],
        },
    )


class _TraceLeaseReader:
    child_owned_physical_reads = True

    def __init__(self):
        self.traces = []

    def readinto(self, target, offset, producer_id=None):
        return len(target)

    def readinto_lease(self, lease, target, offset, producer_id=None):
        self.traces.append(lease._c0_window_trace)
        return len(target)


def _trace_config(**kwargs):
    values = dict(queue_depth=2, block_bytes=8, staging_slots=4, producer_workers=2)
    values.update(kwargs)
    return TransportConfig(**values)


def test_control_descriptor_crc_and_stale_identity_fail_closed():
    session = C0SourceSession(arena_epoch=7, child_alive=lambda: True)
    try:
        ticket = session.submit(_request(1))
        assert C0ControlLayout.request_crc_valid(session.shm.buf, ticket.lane)
        base = C0ControlLayout.lane_offset(ticket.lane)
        assert C0ControlLayout._U64.unpack_from(session.shm.buf, base + 8)[0] == 0
        C0ControlLayout._U64.pack_into(session.shm.buf, base + 24, 999)
        assert not C0ControlLayout.request_crc_valid(session.shm.buf, ticket.lane)
    finally:
        session.close()


def test_four_sticky_lanes_steal_and_reuse_only_after_consume():
    session = C0SourceSession(arena_epoch=7, child_alive=lambda: True)
    try:
        tickets = [session.submit(_request(i + 1, producer_id=0)) for i in range(4)]
        assert [ticket.lane for ticket in tickets] == [0, 1, 2, 3]
        with pytest.raises(C0ProtocolError, match="no_free_lane"):
            session.submit(_request(5), timeout_s=0.001)
        _ready(session, tickets[0])
        with pytest.raises(C0ProtocolError, match="consume_before_done"):
            # The descriptor is DONE, but this assertion is intentionally made
            # against a different sequence and proves reuse is ticket-gated.
            session.consume(type(tickets[0])(tickets[0].lane, tickets[0].sequence + 1, tickets[0].request_id))
        session.consume(tickets[0])
        stolen = session.submit(_request(6, producer_id=0), timeout_s=0.1)
        assert stolen.lane == 0
    finally:
        session.close()


def test_payload_metadata_is_complete_before_done_publication():
    session = C0SourceSession(arena_epoch=7, child_alive=lambda: True)
    try:
        ticket = session.submit(_request(1))
        _ready(session, ticket)
        base = C0ControlLayout.lane_offset(ticket.lane)
        assert C0ControlLayout._U32.unpack_from(session.shm.buf, base + 16)[0] == C0ControlLayout.STATE_DONE
        assert C0ControlLayout.response_crc_valid(session.shm.buf, ticket.lane)
        response = C0ControlLayout.read_response(session.shm.buf, ticket.lane)
        assert response["returned_bytes"] == 8
    finally:
        session.close()


def test_control_response_preserves_child_phases_and_trace_lifecycle(monkeypatch):
    monkeypatch.setenv("COMFYMODAL_GOLDEN_C0_WINDOW_TRACE", "1")
    assert C0ControlLayout._RESPONSE.size <= 384
    session = C0SourceSession(arena_epoch=7, child_alive=lambda: True)
    trace = {}
    try:
        ticket = session.submit(_request(1), trace=trace)
        request = C0ControlLayout.read_request(session.shm.buf, ticket.lane)
        C0ControlLayout.write_response(
            session.shm.buf,
            ticket.lane,
            ticket.sequence,
            {
                "op": "ready",
                "request_id": request["request_id"],
                "arena_epoch": request["arena_epoch"],
                "slot_index": request["slot_index"],
                "slot_generation": request["slot_generation"],
                "returned_bytes": request["length"],
                "source_engine": "mmap_fresh",
                "reader_pid": 123,
                "reader_index": 2,
                "mmap_map_ns": 11,
                "mmap_memcpy_ns": 22,
                "mmap_munmap_ns": 33,
                "mmap_launch_gap_wait_ns": 44,
                "mmap_pipe_rtt_ns": 55,
                "mmap_minflt": 66,
                "mmap_majflt": 7,
                 "mmap_ru_utime_ns": 88,
                 "mmap_ru_stime_ns": 89,
                 "mmap_sched_run_ns": 90,
                 "mmap_sched_wait_ns": 99,
                 "mmap_cpu_utime_ns": 91,
                 "mmap_cpu_stime_ns": 92,
                 "mmap_sched_run_delta_ns": 93,
                 "mmap_sched_wait_delta_ns": 94,
                 "mmap_start_ns": 1001,
                 "mmap_end_ns": 1002,
                 "memcpy_start_ns": 1002,
                 "memcpy_end_ns": 1003,
                 "munmap_start_ns": 1004,
                 "munmap_end_ns": 1005,
             },
         )
        response = session.wait(ticket, timeout_s=0.1, trace=trace)
        assert response["source_engine"] == "mmap_fresh"
        assert response["reader_pid"] == 123
        assert response["mmap_map_ns"] == 11
        assert response["mmap_memcpy_ns"] == 22
        assert response["mmap_munmap_ns"] == 33
        assert response["mmap_pipe_rtt_ns"] == 55
        assert response["mmap_majflt"] == 7
        assert response["mmap_ru_utime_ns"] == 88
        assert response["mmap_ru_stime_ns"] == 89
        assert response["mmap_sched_run_ns"] == 90
        assert response["mmap_sched_wait_ns"] == 99
        assert response["mmap_cpu_utime_ns"] == 91
        assert response["mmap_cpu_stime_ns"] == 92
        assert response["mmap_sched_run_delta_ns"] == 93
        assert response["mmap_sched_wait_delta_ns"] == 94
        assert response["mmap_start_ns"] == 1001
        assert response["mmap_end_ns"] == 1002
        assert response["memcpy_start_ns"] == 1002
        assert response["memcpy_end_ns"] == 1003
        assert response["munmap_start_ns"] == 1004
        assert response["munmap_end_ns"] == 1005
        assert response["source_range"] == [8, 16]
        for name in (
            "mmap_start_ns", "mmap_end_ns", "memcpy_start_ns", "memcpy_end_ns",
            "munmap_start_ns", "munmap_end_ns",
        ):
            assert trace[name] == response[name]
        for name in (
            "mmap_cpu_utime_ns", "mmap_cpu_stime_ns",
            "mmap_sched_run_delta_ns", "mmap_sched_wait_delta_ns",
        ):
            assert trace[name] == response[name]
        assert all(trace.get(name) for name in ("control_submit_ns", "control_enqueue_ns", "reply_observed_ns"))
        assert session.outstanding == 1
        assert session.peak_outstanding == 1
        session.consume(ticket, trace=trace)
        assert trace.get("control_consume_ns")
        assert session.outstanding == 0
    finally:
        session.close()


def test_control_protocol_version_matches_child_and_response_fits_descriptor():
    match = re.search(r"^CONTROL_VERSION = (\d+)$", _C0_CHILD_SOURCE, re.MULTILINE)
    assert match is not None
    assert int(match.group(1)) == C0ControlLayout.VERSION
    assert C0ControlLayout.VERSION == 3
    assert 'CONTROL_RESPONSE = struct.Struct("<QQQQQIIIQQIIII" + "Q" * 31)' in _C0_CHILD_SOURCE
    assert 256 + C0ControlLayout._RESPONSE.size <= C0ControlLayout.DESCRIPTOR_BYTES


def test_mmap_delta_fields_are_present_in_child_and_parent_telemetry_paths():
    fields = (
        "mmap_cpu_utime_ns", "mmap_cpu_stime_ns",
        "mmap_sched_run_delta_ns", "mmap_sched_wait_delta_ns",
    )
    for field in fields:
        assert field in _C0_CHILD_SOURCE
    before = _C0_CHILD_SOURCE.index("cpu_before_utime_ns")
    operation = _C0_CHILD_SOURCE.index("_mmap_libc.mmap(", before)
    after = _C0_CHILD_SOURCE.index("cpu_after_utime_ns", operation)
    assert before < operation < after
    reader = _trace_reader(enabled=False)
    reader._record_fill_telemetry(
        producer_id=0,
        length=8,
        first_fill=True,
        reply={
            "source_engine": "mmap_fresh",
            "reader_pid": 12,
            "copy_start_ns": 10,
            "copy_end_ns": 20,
            "returned_bytes": 8,
            "source_range": [0, 8],
            **{field: index + 1 for index, field in enumerate(fields)},
        },
    )
    record = reader._mmap_read_records[0]
    assert {field: record[field] for field in fields} == {
        field: index + 1 for index, field in enumerate(fields)
    }


def _trace_reader(*, enabled: bool | None) -> C0StageReader:
    ring_values = dict(
        _req_cond=threading.Condition(),
        private_split_io=False,
        source_volume_v1=False,
        preadv_sickness_diag=False,
    )
    if enabled is not None:
        ring_values["_window_trace_enabled"] = enabled
    ring = SimpleNamespace(**ring_values)
    return C0StageReader(ring, role="clip", pool=object(), source="/tmp/model.safetensors")


def test_window_trace_append_drop_is_bounded_under_concurrency():
    reader = _trace_reader(enabled=True)
    workers = 16
    per_worker = (_C0_WINDOW_TRACE_LIMIT // workers) + 32
    total = workers * per_worker

    def append(worker_id):
        for index in range(per_worker):
            reader._store_window_trace({"worker": worker_id, "index": index})

    threads = [threading.Thread(target=append, args=(worker_id,)) for worker_id in range(workers)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    records, dropped = reader.window_trace_snapshot()
    assert len(records) <= _C0_WINDOW_TRACE_LIMIT
    assert len(records) + dropped == total


def test_window_trace_selector_is_cached_and_off_does_not_store(monkeypatch):
    calls = []
    monkeypatch.setattr(c0_io, "c0_window_trace_enabled", lambda: calls.append(True) or False)
    reader = _trace_reader(enabled=None)
    assert calls == [True]
    assert reader._window_trace_enabled is False

    monkeypatch.setattr(c0_io, "c0_window_trace_enabled", lambda: pytest.fail("parsed per fill"))
    reader._store_window_trace({"should": "not be retained"})
    assert reader.window_trace_snapshot() == ([], 0)


def test_mmap_phase_timestamps_bound_only_production_munmap():
    start = _C0_CHILD_SOURCE.index("            munmap_start_ns = time.monotonic_ns()")
    call = _C0_CHILD_SOURCE.index("            _mmap_libc.munmap(win, window_len)", start)
    end = _C0_CHILD_SOURCE.index("            munmap_end_ns = time.monotonic_ns()", call)
    assert start < call < end
    assert '"mmap_munmap_ns": int(max(0, munmap_end_ns - munmap_start_ns))' in _C0_CHILD_SOURCE
    assert '"mmap_frozen_unmap_ns": frozen_unmap_ns' in _C0_CHILD_SOURCE


def test_c0_window_trace_claim_ordinals_and_first_flags(monkeypatch):
    monkeypatch.setenv("COMFYMODAL_GOLDEN_C0_WINDOW_TRACE", "1")
    source = _TraceLeaseReader()
    transport = GoldenQDTransport(_trace_config(), FakeBackend())
    transport.execute([SourceRange(i * 8, 8, i * 8, i) for i in range(16)], source)

    traces = [trace for trace in source.traces if isinstance(trace, dict)]
    assert len(traces) == 16
    assert sorted(trace["operation_ordinal"] for trace in traces) == list(range(16))
    assert {trace["ordinal"] for trace in traces} == set(range(16))
    assert sum(trace["is_model_first_operation"] for trace in traces) == 1
    assert sum(trace["is_reader_first_operation"] for trace in traces) == 2
    for trace in traces:
        ordinal = trace["operation_ordinal"]
        assert trace["reader_count"] == trace["reader_ordinal"] + 1
        assert trace["reader_operation_count"] == trace["reader_ordinal"] + 1
        assert trace["model"] == trace["role"]
        assert trace["reader"] == trace["producer_id"]
        assert trace["lane"] == trace["producer_id"]
        assert trace["is_first_4"] is (ordinal < 4)
        assert trace["is_first_8"] is (ordinal < 8)
        assert trace["is_first_16"] is (ordinal < 16)
        assert trace["work_available_ns"] <= trace["reader_claim_ns"]
        assert trace["source_offset"] % 8 == 0
        assert trace["length"] == 8
    by_reader = {}
    for trace in traces:
        by_reader.setdefault(trace["producer_id"], []).append(trace)
    for reader_traces in by_reader.values():
        assert all(trace["next_work_visible_ns"] is not None for trace in reader_traces[:-1])
        assert reader_traces[-1]["next_work_visible_ns"] is None


def test_c0_window_trace_is_off_without_changing_source_work(monkeypatch):
    monkeypatch.delenv("COMFYMODAL_GOLDEN_C0_WINDOW_TRACE", raising=False)
    source = _TraceLeaseReader()
    transport = GoldenQDTransport(_trace_config(staging_slots=2), FakeBackend())
    result = transport.execute([SourceRange(0, 8), SourceRange(8, 8)], source)

    assert result.completed_bytes == 16
    assert source.traces == [None, None]


def test_c0_window_trace_fill_id_does_not_pollute_golden_request_pairing(monkeypatch):
    monkeypatch.setenv("COMFYMODAL_GOLDEN_C0_WINDOW_TRACE", "1")

    class _Ring:
        _window_trace_enabled = True
        _req_cond = threading.Condition()
        _next_request_id = 0
        epoch = 7
        slot_bytes = 8
        slot_fills = [0]
        fill_submit_mono_ns = {}
        fill_ready_mono_ns = {}
        private_split_io = False
        source_volume_v1 = False
        preadv_sickness_diag = False

        def slot_base_address(self, _slot_index):
            return 0

        def fill(self, request, *, trace):
            assert trace["fill_request_id"] == request.request_id
            return {}

    pool = StagingPool(slots=1, block_bytes=8, capacity_class="test")
    lease = pool.acquire(declared_range=SourceRange(0, 8), producer_id=0)
    reader = C0StageReader(
        _Ring(), role="clip", pool=pool, source="/tmp/model.safetensors"
    )
    monkeypatch.setattr(c0_io, "_lease_target_address", lambda _target: 0)

    reader.readinto_lease(lease, bytearray(8), 0, producer_id=0)
    pool.return_lease(lease)
    records, dropped = reader.window_trace_snapshot()

    assert dropped == 0
    assert len(records) == 1
    assert records[0]["fill_request_id"] == 1
    assert "request_id" not in records[0]

    events = [{
        "request_id": "golden-request",
        "source_detail": {"window_trace": records},
    }]
    paired, status, observed = _golden_p1_request_pairing(
        events, "golden-request", "invocation"
    )
    assert paired is True
    assert status == "paired"
    assert observed["request_id"] == ["golden-request"]


def test_child_error_and_exact_coverage_are_not_downgraded():
    session = C0SourceSession(arena_epoch=7, child_alive=lambda: True)
    try:
        ticket = session.submit(_request(1))
        request = C0ControlLayout.read_request(session.shm.buf, ticket.lane)
        C0ControlLayout.write_response(
            session.shm.buf,
            ticket.lane,
            ticket.sequence,
            {
                "op": "error",
                "request_id": request["request_id"],
                "arena_epoch": request["arena_epoch"],
                "slot_index": request["slot_index"],
                "slot_generation": request["slot_generation"],
                "returned_bytes": 0,
                "error": "child_failed",
            },
        )
        with pytest.raises(C0ProtocolError, match="child_failed"):
            session.wait(ticket, timeout_s=0.1)
        assert reconcile_destination_coverage([(0, 8), (8, 16)], 16)["ok"]
        assert not reconcile_destination_coverage([(0, 8), (9, 16)], 16)["ok"]
    finally:
        session.close()
