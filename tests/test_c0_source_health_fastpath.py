"""wait_ready health-check lock fast path.

``wait_ready`` used to take the authoritative process-shared control lock on
every blocking iteration purely to read the shared failure counter, while the
source workers needed that same lock to claim slots and publish READY.  The
production-008 exhaustive profile attributed 443.6 ms to ``_check_child`` over
313 calls, of which 429.2 ms was ``_FileLock.__enter__``.

The fast path keeps ``poll()`` (child liveness) and relies on the pipe for the
``fatal`` operation and EOF.  These tests pin that this stays fail-closed: every
authoritative path still holds the lock, and a shared failure with a live child
is still reported.
"""

from __future__ import annotations

import pytest

from comfymodal_runtime import golden_source_threads as source

pytestmark = pytest.mark.fast_unit


class _CountingLock:
    """Stand-in for the process-shared flock that records acquisitions."""

    def __init__(self) -> None:
        self.entered = 0

    def __enter__(self):
        self.entered += 1
        return self

    def __exit__(self, *_args):
        return False


class _FakeSharedMemory:
    def __init__(self, buf: bytearray):
        self.buf = buf
        self.name = "fake-control"


class _FakeProc:
    """A child that is alive until ``exit_code`` is set."""

    def __init__(self, exit_code=None):
        self.exit_code = exit_code
        self.stdin = None
        self.stdout = None

    def poll(self):
        return self.exit_code


def _manager(buf: bytearray, lock) -> source.SourceThreadProcess:
    manager = source.SourceThreadProcess.__new__(source.SourceThreadProcess)
    manager.control = _FakeSharedMemory(buf)  # type: ignore[assignment]
    manager._lock = lock  # type: ignore[assignment]
    manager.telemetry = {}
    manager._proc = None
    manager._planned_generation = 7
    manager._planned_records = {}
    manager._pending_ready = []
    return manager  # type: ignore[return-value]


def _buffer() -> bytearray:
    return source.new_control_buffer()


def _set_failure(buf: bytearray, message: str) -> None:
    values = list(source._read_header(buf))
    values[10] = int(values[10]) + 1
    source._write_header_all(buf, values)
    source._write_error(buf, message)


def _publish_ready(buf: bytearray, slot_index: int = 0, *, generation: int = 7, range_index: int = 0) -> None:
    source._put_slot(
        buf, slot_index,
        (source.READY, generation, range_index, 0, 0, 16, 123, 0),
    )


# â”€â”€ hot-path proof â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


def test_healthy_blocking_wait_takes_no_health_check_lock():
    """The hot path must not acquire the authoritative lock per iteration."""
    buf = _buffer()
    lock = _CountingLock()
    manager = _manager(buf, lock)
    manager._proc = _FakeProc(exit_code=None)  # type: ignore[assignment]

    before = lock.entered
    for _ in range(50):
        manager._poll_child()

    assert lock.entered == before


def test_authoritative_check_still_takes_the_lock_exactly_once():
    buf = _buffer()
    lock = _CountingLock()
    manager = _manager(buf, lock)
    manager._proc = _FakeProc(exit_code=None)  # type: ignore[assignment]

    before = lock.entered
    manager._check_child()
    assert lock.entered == before + 1


def test_healthy_wait_ready_does_not_lock_between_iterations():
    """wait_ready takes the lock once up front, then only via recovery.

    Three TELEMETRY messages force three loop iterations before the READY, so
    this discriminates: the old code acquired the health-check lock on every
    iteration (4 acquisitions here), the fast path takes 2 in total.
    """
    buf = _buffer()
    lock = _CountingLock()
    manager = _manager(buf, lock)
    manager._proc = _FakeProc(exit_code=None)  # type: ignore[assignment]

    values = list(source._read_header(buf))
    values[5] = 7
    source._write_header_all(buf, values)
    _publish_ready(buf)

    messages = [
        {"op": "TELEMETRY", "telemetry": {"a": 1}},
        {"op": "TELEMETRY", "telemetry": {"a": 2}},
        {"op": "TELEMETRY", "telemetry": {"a": 3}},
        {"op": "READY_BLOCK", "slot_index": 0, "generation": 7},
    ]
    manager._read_message = lambda _t: messages.pop(0)  # type: ignore[method-assign]

    before = lock.entered
    record = manager.wait_ready(timeout_s=5.0)

    assert record is not None
    assert len(messages) == 0  # all three telemetry messages were consumed
    # Entry check + READY token resolution.  Not one acquisition per iteration.
    assert lock.entered == before + 2


# â”€â”€ child process exit â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


def test_child_process_exit_is_detected_on_the_fast_path():
    buf = _buffer()
    manager = _manager(buf, _CountingLock())
    manager._proc = _FakeProc(exit_code=1)  # type: ignore[assignment]

    with pytest.raises(source.SourceProtocolError, match="source_process_exited"):
        manager._poll_child()

    with pytest.raises(source.SourceProtocolError, match="source_process_exited"):
        manager._check_child()


def test_child_process_exit_is_detected_before_wait_ready_blocks():
    buf = _buffer()
    manager = _manager(buf, _CountingLock())
    manager._proc = _FakeProc(exit_code=9)  # type: ignore[assignment]

    with pytest.raises(source.SourceProtocolError, match="source_process_exited"):
        manager.wait_ready(timeout_s=1.0)


# â”€â”€ explicit fatal message â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


def test_fatal_message_still_raises_from_wait_ready():
    buf = _buffer()
    manager = _manager(buf, _CountingLock())
    manager._proc = _FakeProc(exit_code=None)  # type: ignore[assignment]
    manager._read_message = lambda _t: {"op": "fatal", "error": "reader_boom"}  # type: ignore[method-assign]

    with pytest.raises(source.SourceProtocolError, match="reader_boom"):
        manager.wait_ready(timeout_s=1.0)


# â”€â”€ shared header error with a still-live child â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


def test_shared_header_error_with_live_child_is_still_reported():
    """``header[10]`` is the detail channel; it must not be skipped."""
    buf = _buffer()
    lock = _CountingLock()
    manager = _manager(buf, lock)
    manager._proc = _FakeProc(exit_code=None)  # type: ignore[assignment]
    _set_failure(buf, "reader_exploded")

    with pytest.raises(source.SourceProtocolError, match="source_thread_failed:reader_exploded"):
        manager._check_child()


def test_wait_ready_entry_check_reports_a_failure_that_already_happened():
    """A pre-existing failure is reported with detail, not as a timeout."""
    buf = _buffer()
    manager = _manager(buf, _CountingLock())
    manager._proc = _FakeProc(exit_code=None)  # type: ignore[assignment]
    _set_failure(buf, "late_failure")

    with pytest.raises(source.SourceProtocolError, match="source_thread_failed:late_failure"):
        manager.wait_ready(timeout_s=1.0)


def test_timeout_path_performs_the_authoritative_check():
    """Timeout recovery must still inspect shared state under the lock."""
    buf = _buffer()
    lock = _CountingLock()
    manager = _manager(buf, lock)
    manager._proc = _FakeProc(exit_code=None)  # type: ignore[assignment]
    manager._read_message = lambda _t: None  # type: ignore[method-assign]

    before = lock.entered
    assert manager.wait_ready(timeout_s=0.01) is None

    # entry check + timeout recovery check + table recovery
    assert lock.entered >= before + 3


# â”€â”€ dropped / coalesced doorbell recovery â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


def test_dropped_doorbell_is_recovered_from_the_slot_table():
    buf = _buffer()
    values = list(source._read_header(buf))
    values[5] = 7
    source._write_header_all(buf, values)
    _publish_ready(buf)

    manager = _manager(buf, _CountingLock())
    manager._proc = _FakeProc(exit_code=None)  # type: ignore[assignment]
    manager._read_message = lambda _t: None  # type: ignore[method-assign]

    record = manager.wait_ready(timeout_s=0.05)
    assert record is not None
    assert record.slot_index == 0


def test_coalesced_doorbell_that_resolves_to_nothing_still_recovers():
    buf = _buffer()
    values = list(source._read_header(buf))
    values[5] = 7
    source._write_header_all(buf, values)
    _publish_ready(buf)

    manager = _manager(buf, _CountingLock())
    manager._proc = _FakeProc(exit_code=None)  # type: ignore[assignment]
    # A doorbell for a slot that is not READY resolves to None; the table is
    # re-read so the owned READY block is not orphaned.
    manager._read_message = lambda _t: {"op": "READY_BLOCK", "slot_index": 3, "generation": 7}  # type: ignore[method-assign]

    record = manager.wait_ready(timeout_s=0.05)
    assert record is not None
    assert record.slot_index == 0


# â”€â”€ generations â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


def test_stale_ready_generation_cannot_be_claimed():
    buf = _buffer()
    values = list(source._read_header(buf))
    values[5] = 7
    source._write_header_all(buf, values)
    _publish_ready(buf, generation=7)

    manager = _manager(buf, _CountingLock())
    record = source.ReadyRecord(0, 7, 0, 0, 16, 0, 0, 123, None, 7)
    assert manager.claim_ready(record) is record

    # The slot is now IN_FLIGHT under generation 7; a stale token must fail.
    stale = source.ReadyRecord(0, 6, 0, 0, 16, 0, 0, 123, None, 7)
    with pytest.raises(source.SourceProtocolError, match="stale_ready_generation"):
        manager.claim_ready(stale)


def test_stale_plan_generation_cannot_be_claimed():
    buf = _buffer()
    values = list(source._read_header(buf))
    values[5] = 8
    source._write_header_all(buf, values)
    _publish_ready(buf)

    manager = _manager(buf, _CountingLock())
    record = source.ReadyRecord(0, 7, 0, 0, 16, 0, 0, 123, None, 7)
    with pytest.raises(source.SourceProtocolError, match="stale_ready_plan_generation"):
        manager.claim_ready(record)


def test_stale_release_generation_is_rejected():
    buf = _buffer()
    values = list(source._read_header(buf))
    values[5] = 7
    source._write_header_all(buf, values)
    _publish_ready(buf)
    manager = _manager(buf, _CountingLock())
    record = manager.claim_ready(source.ReadyRecord(0, 7, 0, 0, 16, 0, 0, 123, None, 7))

    stale = source.ReadyRecord(0, 6, 0, 0, 16, 0, 0, 123, None, 7)
    with pytest.raises(source.SourceProtocolError, match="stale_release_generation"):
        manager.release_slot(stale)
    # The real token still releases cleanly.
    manager.release_slot(record)


# â”€â”€ ownership / H2D gating â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


def test_no_double_release_and_no_orphan_ready_slot():
    buf = _buffer()
    values = list(source._read_header(buf))
    values[5] = 7
    source._write_header_all(buf, values)
    _publish_ready(buf)
    manager = _manager(buf, _CountingLock())
    record = manager.claim_ready(source.ReadyRecord(0, 7, 0, 0, 16, 0, 0, 123, None, 7))

    manager.release_slot(record)
    # The slot is FREE again; releasing the same token twice must not succeed.
    with pytest.raises(source.SourceProtocolError, match="release_without_completion_ownership"):
        manager.release_slot(record)


def test_slot_cannot_be_released_before_h2d_completion_ownership():
    """An unclaimed slot can never be released, so no early free happens."""
    buf = _buffer()
    values = list(source._read_header(buf))
    values[5] = 7
    source._write_header_all(buf, values)
    _publish_ready(buf)
    manager = _manager(buf, _CountingLock())

    # Never claimed -> not IN_FLIGHT.
    with pytest.raises(source.SourceProtocolError, match="release_without_completion_ownership"):
        manager.release_slot(source.ReadyRecord(0, 7, 0, 0, 16, 0, 0, 123, None, 7))


def test_claim_marks_in_flight_before_any_release_is_possible():
    buf = _buffer()
    values = list(source._read_header(buf))
    values[5] = 7
    source._write_header_all(buf, values)
    _publish_ready(buf)
    manager = _manager(buf, _CountingLock())
    record = manager.claim_ready(source.ReadyRecord(0, 7, 0, 0, 16, 0, 0, 123, None, 7))

    state = source._slot(buf, 0)[0]
    assert state == source.IN_FLIGHT
    # While IN_FLIGHT it is owned, so recovery must not hand it to anyone else.
    assert manager._recover_ready_from_table() is None
    manager.release_slot(record)
    assert source._slot(buf, 0)[0] == source.FREE
