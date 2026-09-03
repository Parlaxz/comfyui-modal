import json
import copy
import threading

import pytest

from comfymodal_runtime.e27_source_mechanism import (
    ActualSourceTelemetry,
    evaluate_e27_source_mechanism,
)
from comfymodal_runtime.golden_qd_transport import (
    FakeBackend,
    GoldenQDTransport,
    SourceRange,
    TransportConfig,
    evaluate_e27_source_mechanism as transport_evaluate_e27_source_mechanism,
)


def _telemetry(*, expected=(0, 16), regions=None):
    return ActualSourceTelemetry(
        regions=regions or ((0, 4), (4, 8), (8, 12), (12, 16)),
        expected_ranges=(expected,),
        expected_destination_ranges=(expected,),
        expected_h2d_bytes=16,
    )


def test_transport_exposes_canonical_e27_evaluator():
    """Golden serial's transport seam must expose the canonical evaluator."""
    assert transport_evaluate_e27_source_mechanism is evaluate_e27_source_mechanism


def _read(t, producer, offset, timestamp, retry=0, returned=4):
    call = t.syscall_enter(producer, offset, 4, retry_number=retry,
                           destination_offset=offset, timestamp_ns=timestamp)
    t.syscall_exit(call, returned, timestamp_ns=timestamp + 1)


def _checkpoint(phase, **overrides):
    evidence = {
        "checkpoint": phase,
        "phase": phase,
        "live_source_workers": 0,
        "live_source_readers": 1 if phase != "final_completion" else 0,
        "live_dispatcher": 0 if phase in ("bind", "final_completion") else 1,
        "live_slots": 0 if phase in ("bind", "final_completion") else 1,
        "actual_syscalls_in_flight": 0,
        "queued_ready_blocks": 0 if phase != "source_completion" else 1,
        "free_buffers": 8 if phase != "source_completion" else 7,
        "h2ds_in_flight": 0,
        "unreaped_events": 0,
        "outstanding_futures": 0,
        "fallback": 0,
        "poison": 0,
        "reconciliation_state": phase == "final_completion",
        "ownership_quiescent": phase == "final_completion",
    }
    evidence.update(overrides)
    return evidence


def _finish(t):
    tokens = [t.record_h2d_submit(4, timestamp_ns=30 + n) for n in range(4)]
    for n, token in enumerate(tokens):
        t.record_h2d_complete(token, timestamp_ns=40 + n)
    if not t.report().get("quiescence_checkpoints"):
        t.record_quiescence_checkpoint(_checkpoint("bind"))
    t.record_quiescence_checkpoint(_checkpoint("source_completion"))
    t.record_quiescence_checkpoint(_checkpoint("final_completion"))


def _valid_evaluator_report():
    t = _telemetry()
    t.mark_physical_syscall_provenance("test.fixture.physical_syscall")
    t.record_quiescence_checkpoint(_checkpoint("bind"))
    calls = [
        t.syscall_enter(producer, producer * 4, 4,
                        destination_offset=producer * 4,
                        timestamp_ns=producer + 1)
        for producer in range(4)
    ]
    for producer, call in enumerate(calls):
        t.syscall_exit(call, 4, timestamp_ns=20 + producer)
    _finish(t)
    return t.report()


def test_true_concurrent_qd4_has_actual_syscall_events_and_occupancy():
    t = _telemetry()
    t.mark_physical_syscall_provenance("test.fixture.physical_syscall")
    barrier = threading.Barrier(4)

    def worker(producer):
        call = t.syscall_enter(producer, producer * 4, 4,
                               destination_offset=producer * 4,
                               timestamp_ns=producer + 1)
        barrier.wait()
        t.syscall_exit(call, 4, timestamp_ns=20 + producer)

    threads = [threading.Thread(target=worker, args=(producer,)) for producer in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    report = t.report()
    assert report["max_actual_source_inflight"] == 4
    assert report["actual_source_inflight"] == 0
    assert len(report["actual_source_events"]) == 4
    assert report["qd_occupancy_ms"]["4"] > 0
    assert report["SOURCE_TOTAL_WALL_MS"] == 22 / 1e6


def test_serial_four_workers_does_not_claim_qd4():
    t = _telemetry()
    for producer in range(4):
        _read(t, producer, producer * 4, producer * 10 + 1)
    report = t.report()
    assert report["max_actual_source_inflight"] == 1
    assert report["qd_occupancy_ms"]["4"] == 0


def test_qd1_boundary_reads_and_empty_trailing_regions_are_deterministic():
    t = _telemetry(expected=(0, 5), regions=((0, 2), (2, 4), (4, 5), (5, 5)))
    for producer, offset, count in ((0, 0, 2), (1, 2, 2), (2, 4, 1)):
        call = t.syscall_enter(producer, offset, count,
                               destination_offset=offset,
                               timestamp_ns=producer * 10 + 1)
        t.syscall_exit(call, count, timestamp_ns=producer * 10 + 6)
    report = t.report()
    assert report["max_actual_source_inflight"] == 1
    assert report["qd_occupancy_ms"]["1"] == 15 / 1e6
    assert report["producer_report"]["3"]["bytes"] == 0
    assert report["topology"]["coverage_exact"] is True


def test_short_read_retry_is_not_a_duplicate_and_reconciles_offsets():
    t = _telemetry(expected=(0, 4), regions=((0, 4), (4, 4), (4, 4), (4, 4)))
    first = t.syscall_enter(0, 0, 4, retry_number=0,
                            destination_offset=0, timestamp_ns=1)
    t.syscall_exit(first, 2, timestamp_ns=2)
    second = t.syscall_enter(0, 2, 2, retry_number=1,
                             destination_offset=2, timestamp_ns=3)
    t.syscall_exit(second, 2, timestamp_ns=4)
    assert t.report()["topology"]["unexpected_duplicates"] == 0
    assert t.report()["topology"]["coverage_exact"] is True


@pytest.mark.parametrize(
    "events, expected_failed",
    [
        ([(0, 0, 4, 0), (0, 0, 4, 0)], "unexpected_duplicates"),
        ([(0, 0, 4, 0), (0, 3, 1, 1)], "overlaps"),
        ([(0, 0, 2, 0)], "gaps"),
    ],
)
def test_duplicate_overlap_and_gap_are_provenance_failures(events, expected_failed):
    t = _telemetry(expected=(0, 4), regions=((0, 4), (4, 4), (4, 4), (4, 4)))
    for producer, offset, count, retry in events:
        call = t.syscall_enter(producer, offset, count, retry_number=retry,
                               destination_offset=offset,
                               timestamp_ns=1 + offset + retry)
        t.syscall_exit(call, count, timestamp_ns=2 + offset + retry)
    assert t.report()["topology"][expected_failed] != 0


def test_h2d_overlap_and_post_source_tail_are_independent_metrics():
    t = _telemetry()
    for producer in range(4):
        _read(t, producer, producer * 4, producer + 1)
    tokens = [t.record_h2d_submit(4, timestamp_ns=2 + n) for n in range(4)]
    for n, token in enumerate(tokens):
        t.record_h2d_complete(token, timestamp_ns=30 + n)
    report = t.report()
    assert report["SOURCE_H2D_OVERLAP_MS"] > 0
    assert report["POST_SOURCE_H2D_TAIL_MS"] > 0
    assert report["H2D_TOTAL_WALL_MS"] == 31 / 1e6


def test_quiescence_missing_state_fails_closed_and_complete_fixture_proves():
    t = _telemetry()
    t.mark_physical_syscall_provenance("test.fixture.physical_syscall")
    calls = [
        t.syscall_enter(producer, producer * 4, 4,
                        destination_offset=producer * 4,
                        timestamp_ns=producer + 1)
        for producer in range(4)
    ]
    for producer, call in enumerate(calls):
        t.syscall_exit(call, 4, timestamp_ns=20 + producer)
    _finish(t)
    result = evaluate_e27_source_mechanism(t)
    assert result["proven"] is True
    assert result["emitted_line"] == "E27_SOURCE_MECHANISM_PROVEN=YES"
    assert result["failed_predicates"] == []
    encoded = json.dumps(result)
    assert "E27_SOURCE_MECHANISM_PROVEN" in encoded

    missing = evaluate_e27_source_mechanism(t.report() | {"quiescence_checkpoints": None})
    assert missing["proven"] is False
    assert "quiescence_checkpoint_history" in missing["failed_predicates"]


def test_quiescence_checkpoint_history_is_deep_copied():
    t = _telemetry()
    evidence = _checkpoint("bind", free_buffers=3)
    t.record_quiescence_checkpoint(evidence)
    evidence["free_buffers"] = 99
    report = t.report()
    assert report["quiescence_checkpoints"][0]["free_buffers"] == 3
    report["quiescence_checkpoints"][0]["free_buffers"] = 77
    assert t.report()["quiescence_checkpoints"][0]["free_buffers"] == 3


def test_contradictory_checkpoint_history_names_fail_closed():
    report = copy.deepcopy(_valid_evaluator_report())
    report["quiescence_checkpoints"][1]["phase"] = "final_completion"
    result = evaluate_e27_source_mechanism(report)
    assert result["proven"] is False
    assert "checkpoint_fields" in result["failed_predicates"]
    assert "quiescence_checkpoint_history" in result["failed_predicates"]


def test_report_summaries_cannot_replace_checkpoint_history():
    report = copy.deepcopy(_valid_evaluator_report())
    report["quiescence_evidence"]["ownership_quiescent"] = False
    report["quiescence"] = False
    report["topology"] = {"coverage_exact": False}
    report["h2d_reconciliation_complete"] = False
    report["dispatcher_control"]["h2d_completed_bytes"] = 0
    result = evaluate_e27_source_mechanism(report)
    assert result["proven"] is True


@pytest.mark.parametrize("mutate", [
    lambda report: report.update(actual_source_events=[]),
    lambda report: report["actual_source_transitions"].__setitem__(0, {"timestamp_ns": 1, "delta": 2, "depth": 1, "producer_id": 0}),
    lambda report: report["qd_occupancy_ms"].__setitem__("4", report["qd_occupancy_ms"]["4"] + 1),
    lambda report: report["h2d_events"][0].update(complete_ns=None),
    lambda report: report["quiescence_checkpoints"][-1].update(h2ds_in_flight=1),
    lambda report: report.update(physical_syscall_provenance=None),
    lambda report: report["quiescence_checkpoints"][-1].update(ownership_quiescent=False),
])
def test_adversarial_raw_evidence_cannot_be_replaced_by_fake_summaries(mutate):
    report = copy.deepcopy(_valid_evaluator_report())
    mutate(report)
    result = evaluate_e27_source_mechanism(report)
    assert result["proven"] is False
    assert result["E27_SOURCE_MECHANISM_PROVEN"] == "NO"
    assert result["failed_predicates"]


def test_unmarked_reader_adapter_is_not_physical_e27_proof():
    report = _valid_evaluator_report()
    report["physical_syscall_provenance"] = None
    result = evaluate_e27_source_mechanism(report)
    assert result["proven"] is False
    assert "actual_syscall_qd_telemetry_complete" in result["failed_predicates"]


@pytest.mark.parametrize("field", ["live_source_workers", "unreaped_events", "fallback", "poison"])
def test_quiescence_leaks_and_degraded_states_fail_closed(field):
    t = _telemetry()
    for producer in range(4):
        _read(t, producer, producer * 4, producer + 1)
    _finish(t)
    report = t.report()
    report["quiescence_checkpoints"][-1][field] = 1
    assert evaluate_e27_source_mechanism(report)["proven"] is False


def test_real_positioned_reader_adapter_captures_syscall_boundary():
    class Reader:
        def readinto(self, target, offset, producer_id):
            target[:2] = b"ok"
            return 2

    t = _telemetry(expected=(0, 2), regions=((0, 2), (2, 2), (2, 2), (2, 2)))
    target = bytearray(2)
    t.mark_physical_syscall_provenance("test.fixture.physical_syscall")
    assert t.readinto(Reader(), target, 0, 2, producer_id=0, destination_offset=0) == 2
    event = t.events[0]
    assert event.requested_bytes == event.returned_bytes == 2
    assert event.syscall_exit_monotonic_ns >= event.syscall_enter_monotonic_ns


def test_static_transport_persists_actual_source_and_dispatcher_control_fields():
    class Reader:
        def __init__(self, data):
            self.data = data

        def readinto(self, target, offset, producer_id=None):
            count = min(len(target), len(self.data) - offset)
            target[:count] = self.data[offset:offset + count]
            return count

    data = bytes(range(16))
    result = GoldenQDTransport(
        TransportConfig(queue_depth=4, block_bytes=4, staging_slots=8),
        FakeBackend(), arm="static_e27",
    ).execute([SourceRange(0, len(data), 0)], Reader(data), output_size=len(data))
    assert result.output == data
    assert len(result.telemetry["source_syscall_events"]) == 4
    assert result.telemetry["SOURCE_TOTAL_WALL_MS"] is not None
    assert result.telemetry["actual_source"]["dispatcher_control"]["h2d_reconciliation_complete"] is True
    assert result.telemetry["quiescence_evidence"]["actual_syscalls_in_flight"] == 0
