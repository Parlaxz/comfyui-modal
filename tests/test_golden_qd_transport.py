import json
import threading
import time

import pytest

from comfymodal_runtime.golden_qd_transport import (
    BackingOwner,
    DEFAULT_BLOCK_BYTES,
    DEFAULT_QUEUE_DEPTH,
    DEFAULT_STAGING_SLOTS,
    EventStatus,
    FakeBackend,
    FakeSource,
    GoldenQDTransport,
    LeaseError,
    OutputViewSpec,
    PoolPoisonedError,
    ReadyRecord,
    SourceRange,
    SlotState,
    StagingPool,
    TransportConfig,
    TransportFailure,
    create_transport,
    map_output_views,
    normalize_transport_arm,
    prove_backing_survives_stage_release,
)


def small_config(**kwargs):
    values = dict(queue_depth=4, block_bytes=8, staging_slots=8, producer_workers=4)
    values.update(kwargs)
    return TransportConfig(**values)


def test_qd4_defaults_and_explicit_validation():
    config = TransportConfig()
    assert (config.queue_depth, config.block_bytes, config.staging_slots) == (
        DEFAULT_QUEUE_DEPTH,
        DEFAULT_BLOCK_BYTES,
        DEFAULT_STAGING_SLOTS,
    )
    with pytest.raises(ValueError):
        TransportConfig(queue_depth=5, staging_slots=4)
    with pytest.raises(ValueError):
        TransportConfig(block_bytes=0)


def test_selector_is_explicit_and_independent_of_diagnostics(monkeypatch):
    monkeypatch.setenv("COMFYMODAL_GOLDEN_STAGE_DIAGNOSTICS", "not-an-arm")
    monkeypatch.setenv("COMFYMODAL_GOLDEN_QD_TRANSPORT", "dispatcher")
    assert normalize_transport_arm() == "dispatcher"
    assert create_transport("legacy", config=small_config()).arm == "legacy"
    with pytest.raises(ValueError):
        normalize_transport_arm("r41")


def test_generation_identity_wrong_pool_double_return_and_capacity_class():
    first_pool = StagingPool(slots=1, block_bytes=8, capacity_class="a")
    second_pool = StagingPool(slots=1, block_bytes=8, capacity_class="a")
    lease = first_pool.acquire()
    first_pool.return_lease(lease)
    with pytest.raises(LeaseError):
        first_pool.return_lease(lease)
    newer = first_pool.acquire()
    with pytest.raises(LeaseError):
        first_pool.return_lease(lease)
    with pytest.raises(LeaseError):
        second_pool.return_lease(newer)
    with pytest.raises(LeaseError):
        first_pool.acquire("b")
    first_pool.return_lease(newer)


def test_reuse_before_completion_proof_is_rejected():
    pool = StagingPool(slots=1, block_bytes=8)
    backend = FakeBackend(h2d_delay_polls=100)
    transport = GoldenQDTransport(small_config(queue_depth=1, staging_slots=1), backend)
    transport.start()
    lease = transport.acquire()
    lease.fill(b"payload")
    transport.publish(lease, ReadyRecord(0, 0, 7))
    with pytest.raises(LeaseError):
        pool.return_lease(lease)
    transport.cancel()
    assert transport.snapshot_quiescence()


def test_concurrent_source_reads_and_qd_four_under_slow_h2d():
    data = bytes(range(64))
    source = FakeSource(data)
    backend = FakeBackend(h2d_delay_polls=8)
    transport = GoldenQDTransport(small_config(), backend)
    ranges = [SourceRange(i * 8, 8, i * 8, i) for i in range(8)]
    result = transport.execute(ranges, source.read, output_size=64)
    assert result.output == data
    assert max(result.telemetry["target_qd_depth_samples"]) <= 4
    assert max(result.telemetry["target_qd_depth_samples"]) == 4
    assert result.telemetry["h2d_submitted_bytes"] == result.telemetry["h2d_completed_bytes"] == 64
    assert result.telemetry["h2d_submitted_count"] == 8
    assert result.telemetry["h2d_completed_count"] == 8


def test_dispatcher_can_leave_cuda_destination_unmaterialized():
    destination = bytearray()
    backend = FakeBackend(destination=destination)
    transport = GoldenQDTransport(small_config(queue_depth=1, staging_slots=1), backend)

    result = transport.execute(
        [SourceRange(0, 4, 0)],
        lambda offset, length: b"data",
        destination_size=4,
        materialize_output=False,
    )

    assert result.output is None
    assert bytes(destination) == b"data"


def test_source_qd_four_is_time_weighted_independently_of_slow_h2d():
    started = threading.Barrier(4)

    def blocked_reader(offset, length):
        started.wait(timeout=1)
        time.sleep(0.05)
        return b"x" * length

    transport = GoldenQDTransport(
        small_config(queue_depth=4, producer_workers=4),
        FakeBackend(h2d_delay_polls=8),
    )

    result = transport.execute([SourceRange(i * 8, 8, i * 8, i) for i in range(4)], blocked_reader)

    telemetry = result.telemetry
    assert telemetry["source_qd_target"] == 4
    assert max(telemetry["source_qd_depth_samples"]) == 4
    assert telemetry["source_qd_depth"] == 0
    assert telemetry["h2d_inflight_depth_samples"]
    assert telemetry["fraction_time_at_target_source_qd"] > 0.4, (
        telemetry["fraction_time_at_target_source_qd"],
        telemetry["source_qd_timeline"],
    )
    assert telemetry["target_qd_occupancy_fraction"] == telemetry["fraction_time_at_target_source_qd"]


def test_source_qd_interval_closes_when_reader_raises():
    def failing_reader(offset, length):
        raise OSError("blocked source failed")

    transport = GoldenQDTransport(small_config(queue_depth=4, producer_workers=4), FakeBackend())
    with pytest.raises(TransportFailure) as caught:
        transport.execute([SourceRange(0, 4)], failing_reader)

    telemetry = caught.value.telemetry
    assert isinstance(caught.value.primary_error, OSError)
    assert telemetry["source_qd_depth"] == 0
    assert telemetry["source_qd_depth_samples"][-1] == 0
    assert telemetry["source_qd_timeline"][-1]["depth"] == 0


def test_normal_producer_completion_is_not_limited_by_cleanup_timeout():
    transport = GoldenQDTransport(
        small_config(queue_depth=1, staging_slots=1, producer_workers=1, cleanup_timeout=1.0),
        FakeBackend(),
    )

    def slow_reader(offset, length):
        time.sleep(1.05)
        return b"data"

    result = transport.execute([SourceRange(0, 4)], slow_reader, output_size=4)

    assert result.output == b"data"


def test_ready_queue_is_bounded_and_backpressure_is_counted():
    source = FakeSource(b"a" * 32)
    transport = GoldenQDTransport(
        small_config(queue_depth=1, staging_slots=2, ready_queue_capacity=1, producer_workers=2),
        FakeBackend(h2d_delay_polls=12),
    )
    result = transport.execute([SourceRange(i * 8, 8, i * 8, i) for i in range(4)], source.read)
    assert result.telemetry["ready_queue_block_count"] > 0
    assert result.telemetry["ready_queue_depth"] == 0


def test_uncertain_completion_poison_is_fail_closed():
    transport = GoldenQDTransport(small_config(queue_depth=1, staging_slots=1), FakeBackend(event_uncertain=True))
    with pytest.raises(TransportFailure) as caught:
        transport.execute([SourceRange(0, 4)], lambda offset, length: b"data")
    assert "uncertain" in str(caught.value.primary_error).lower()
    assert transport.pool.poisoned
    with pytest.raises(PoolPoisonedError):
        transport.pool.acquire()


def test_cancellation_drains_pending_event_and_returns_slot():
    backend = FakeBackend(h2d_delay_polls=100)
    transport = GoldenQDTransport(small_config(queue_depth=1, staging_slots=1), backend)
    transport.start()
    lease = transport.acquire()
    lease.fill(b"data")
    transport.publish(lease, ReadyRecord(0, 0, 4))
    deadline = time.monotonic() + 1
    while not backend.submissions and time.monotonic() < deadline:
        time.sleep(0.001)
    transport.cancel()
    assert transport.pool.states() == (SlotState.FREE,)
    assert transport.snapshot_quiescence()


def test_worker_error_is_primary_over_dispatcher_cancellation_error():
    transport = GoldenQDTransport(small_config(queue_depth=1, staging_slots=1), FakeBackend(h2d_delay_polls=10))

    def reader(offset, length):
        raise OSError("source is primary")

    with pytest.raises(TransportFailure) as caught:
        transport.execute([SourceRange(0, 4)], reader)
    assert isinstance(caught.value.primary_error, OSError)
    assert "source is primary" in str(caught.value)


def test_dispatcher_error_is_typed_and_poisoned():
    transport = GoldenQDTransport(
        small_config(queue_depth=1, staging_slots=1),
        FakeBackend(fail_submit=RuntimeError("submit failed")),
    )
    with pytest.raises(TransportFailure) as caught:
        transport.execute([SourceRange(0, 4)], lambda offset, length: b"data")
    assert "submit failed" in str(caught.value.primary_error)
    assert transport.pool.poisoned


def test_exact_coverage_no_duplicate_or_missing_source_range():
    source = FakeSource(b"abcdefgh")
    transport = GoldenQDTransport(small_config(queue_depth=2, staging_slots=2), FakeBackend())
    result = transport.execute([SourceRange(0, 4, 4, "a"), SourceRange(4, 4, 0, "b")], source.read, output_size=8)
    assert result.output == b"efghabcd"
    assert sorted(source.calls) == [(0, 4), (4, 4)]
    with pytest.raises(Exception):
        transport = GoldenQDTransport(small_config(), FakeBackend())
        transport.execute([SourceRange(0, 4), SourceRange(2, 4)], lambda o, n: b"x" * n)


def test_short_read_retry_is_exact_and_not_a_fallback():
    source = FakeSource(b"abcdefgh", short_reads=3)
    transport = GoldenQDTransport(small_config(queue_depth=1, staging_slots=1, read_retries=3), FakeBackend())
    result = transport.execute([SourceRange(0, 8)], source.read, output_size=8)
    assert result.output == b"abcdefgh"
    assert result.telemetry["source_bytes"] == 8
    assert result.telemetry["source_read_count"] == 3


def test_output_views_and_backing_lifetime_are_independent_of_staging():
    owner = BackingOwner(b"abcdefgh", identity="model")
    views = map_output_views(owner, [OutputViewSpec("left", 1, 3, "u8"), OutputViewSpec("right", 5, 2)])
    pool = StagingPool(slots=1, block_bytes=4)
    lease = pool.acquire()
    lease.fill(b"work")
    pool.return_lease(lease)
    assert bytes(views["left"]) == b"bcd"
    assert bytes(views["right"]) == b"fg"
    assert prove_backing_survives_stage_release()


def test_telemetry_is_json_safe_and_contains_total_partial_fields():
    transport = GoldenQDTransport(small_config(queue_depth=1, staging_slots=1), FakeBackend())
    result = transport.execute(
        [SourceRange(0, 4)],
        lambda offset, length: b"data",
        owner=object(),
        adoption=object(),
        owner_count={"count": 1},
        adoption_result={"status": "caller-supplied"},
    )
    encoded = json.dumps(result.to_dict())
    assert encoded
    assert result.telemetry["timing_scope"]["total_entry_to_return_wall_ms"] == "TOTAL"
    assert result.telemetry["final_drain_wall_ms"] >= 0
    assert result.telemetry["owner_count"] == {"count": 1}
    assert result.telemetry["adoption_result"] == {"status": "caller-supplied"}
    for name in (
        "fallback_count",
        "fallback_reason",
        "execution_arm",
        "source_open_count",
        "duplicate_read_count",
        "source_qd_depth_samples",
        "source_qd_timeline",
        "h2d_inflight_depth_samples",
    ):
        assert name in result.telemetry


def test_snapshot_quiescence_rejects_live_dispatcher_and_slot():
    transport = GoldenQDTransport(small_config(queue_depth=1, staging_slots=1), FakeBackend(h2d_delay_polls=10))
    transport.start()
    with pytest.raises(Exception):
        transport.snapshot_quiescence()
    lease = transport.acquire()
    with pytest.raises(Exception):
        transport.snapshot_quiescence()
    transport.pool.return_lease(lease)
    transport.cancel()
    assert transport.snapshot_quiescence()


def test_dispatcher_requires_explicit_backend_and_legacy_is_only_an_adapter():
    with pytest.raises(ValueError):
        GoldenQDTransport(small_config())
    with pytest.raises(ValueError):
        create_transport("dispatcher", config=small_config())
    legacy = create_transport("legacy", config=small_config())
    assert getattr(legacy, "available") is True
    assert legacy.dispatcher is None
    with pytest.raises(Exception, match="legacy"):
        legacy.execute([], lambda offset, length: b"")


def test_raw_buffer_escape_and_retired_generation_are_not_writable():
    pool = StagingPool(slots=1, block_bytes=8)
    old = pool.acquire()
    old.fill(b"old")
    pool.return_lease(old)
    with pytest.raises(LeaseError):
        _ = old.buffer
    newer = pool.acquire()
    with pytest.raises(LeaseError):
        old.fill(b"stale")
    newer.fill(b"new")
    pool.return_lease(newer)


def test_destination_collision_and_exact_destination_coverage_fail_closed():
    ranges = [SourceRange(0, 4, 0, "a"), SourceRange(4, 4, 2, "b")]
    with pytest.raises(Exception, match="destination"):
        GoldenQDTransport(small_config(), FakeBackend()).execute(ranges, lambda o, n: b"data", destination_size=8)
    with pytest.raises(Exception, match="exactly cover"):
        GoldenQDTransport(small_config(), FakeBackend()).execute([SourceRange(0, 4, 0)], lambda o, n: b"data", destination_size=8)


class _NeverSettles(FakeBackend):
    def cancel_event(self, event):
        raise RuntimeError("cancel failed")

    def poll_event(self, event):
        self.poll_count += 1
        return EventStatus.PENDING


class _BlockingSubmit(FakeBackend):
    def __init__(self):
        super().__init__()
        self.entered = threading.Event()
        self.release = threading.Event()

    def submit_h2d(self, source, destination_offset):
        self.entered.set()
        self.release.wait(timeout=2)
        return super().submit_h2d(source, destination_offset)


def test_bounded_drain_accounts_for_ready_to_inflight_handoff():
    backend = _BlockingSubmit()
    transport = GoldenQDTransport(
        small_config(queue_depth=1, staging_slots=1, cleanup_timeout=0.05), backend
    )
    transport.start()
    lease = transport.acquire()
    lease.fill(b"data")
    transport.publish(lease, ReadyRecord(0, 0, 4))
    assert backend.entered.wait(timeout=1)

    transport.cancel(timeout=0.01)
    assert transport.dispatcher is not None
    assert transport.dispatcher._handoff == {}
    assert transport.pool.poisoned

    backend.release.set()
    deadline = time.monotonic() + 1
    while transport.dispatcher._thread is not None and transport.dispatcher._thread.is_alive():
        if time.monotonic() >= deadline:
            pytest.fail("dispatcher did not stop after bounded handoff cleanup")
        time.sleep(0.001)
    assert transport.snapshot_quiescence()


def test_cancel_cleanup_is_bounded_and_poisoned_when_event_is_uncertain():
    backend = _NeverSettles(h2d_delay_polls=100)
    transport = GoldenQDTransport(
        small_config(queue_depth=1, staging_slots=1, producer_workers=1, cancellation_poll_limit=2, cleanup_timeout=0.2),
        backend,
    )

    transport.start()
    lease = transport.acquire()
    lease.fill(b"data")
    transport.publish(lease, ReadyRecord(0, 0, 4))
    deadline = time.monotonic() + 1
    while not backend.submissions and time.monotonic() < deadline:
        time.sleep(0.001)
    transport.cancel()
    assert transport.pool.poisoned
    assert transport.snapshot_quiescence()


def test_explicit_cancel_always_returns_typed_cancelled_failure():
    transport = GoldenQDTransport(small_config(queue_depth=1, staging_slots=1), FakeBackend())

    def reader(offset, length):
        transport.cancel()
        return b"data"

    with pytest.raises(TransportFailure) as caught:
        transport.execute([SourceRange(0, 4)], reader)
    assert caught.value.cancelled is True


def test_abort_cleanup_has_one_bounded_deadline_without_stale_lease_secondary():
    started = threading.Event()
    release = threading.Event()
    outcome = []
    transport = GoldenQDTransport(
        small_config(queue_depth=1, staging_slots=1, producer_workers=1, cleanup_timeout=0.05),
        FakeBackend(),
    )

    def blocked_reader(offset, length):
        started.set()
        release.wait(timeout=1)
        return b"data"

    def run():
        try:
            transport.execute([SourceRange(0, 4)], blocked_reader)
        except TransportFailure as exc:
            outcome.append(exc)

    thread = threading.Thread(target=run)
    thread.start()
    assert started.wait(timeout=1)
    began = time.monotonic()
    transport.cancel()
    elapsed = time.monotonic() - began
    thread.join(timeout=1)

    assert elapsed < 0.2
    assert not thread.is_alive()
    assert outcome and outcome[0].cancelled is True
    assert all("stale lease generation" not in str(error).lower() for error in outcome[0].secondary_errors)
    release.set()
