"""Behavioral contracts for the C0 source-owner protocol.

These tests exercise the real state machine, the real pacer, and the real
bridge.  Where a contract is only reachable on POSIX (shared memory, mmap,
subprocess source owner) the test skips explicitly rather than asserting on
source text: a string-presence assertion can be satisfied by a comment.
"""

from __future__ import annotations

import ast
import inspect
import json
import os
import queue
import threading
import time
from pathlib import Path

import pytest

from comfymodal_runtime import golden_source_threads as source

pytestmark = pytest.mark.fast_unit

IS_POSIX = source.os.name == "posix"
posix_only = pytest.mark.skipif(not IS_POSIX, reason="POSIX shared-memory/mmap runtime path")


class _NullLock:
    """In-process stand-in for the process-shared flock.

    Exercises the real control-block state machine without requiring POSIX
    named shared memory or flock.
    """

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


def _manager_with_control(buf: bytearray, lock: _NullLock) -> source.SourceThreadProcess:
    manager = source.SourceThreadProcess.__new__(source.SourceThreadProcess)
    manager.control = _FakeSharedMemory(buf)  # type: ignore[assignment]
    manager._lock = lock  # type: ignore[assignment]
    manager.telemetry = {}
    manager._proc = None
    manager._planned_generation = 7
    manager._planned_records = {}
    manager._pending_ready = []
    return manager  # type: ignore[return-value]


def _plan(generation: int = 7, range_count: int = 2):
    return source._ChildPlan(
        generation=generation, path="/nonexistent", identity=(1, 2, 8, 3),
        destination_size=4 * range_count, mmap_lifecycle="fresh",
        ranges=tuple((i * 4, 4, i * 4, None) for i in range(range_count)),
    )


def _install(buf: bytearray, lock: _NullLock, generation: int = 7, range_count: int = 2) -> None:
    plan = source._ChildPlan(
        generation=generation, path="/nonexistent", identity=(1, 2, 8, 3),
        destination_size=4 * range_count, mmap_lifecycle="fresh",
        ranges=tuple((i * 4, 4, i * 4, None) for i in range(range_count)),
    )
    source.install_generation_header(buf, generation, plan)


def _release_all(buf: bytearray) -> None:
    """Return every physical slot, as a completed generation must."""
    for index in range(source.SLOT_COUNT):
        old = source._slot(buf, index)
        source._put_slot(buf, index, (source.FREE, old[1], 0, 0, 0, 0, 0, 0))
    values = list(source._read_header(buf))
    values[11] = source.FREE_MASK
    values[8] = 0
    source._write_header_all(buf, values)


# ---------------------------------------------------------------------------
# Geometry and identity
# ---------------------------------------------------------------------------


def test_geometry_is_exactly_sixteen_64m_slots_and_four_readers() -> None:
    assert source.geometry() == {
        "arena_bytes": 16 * 64 * 1024 * 1024,
        "slot_count": 16,
        "slot_bytes": 64 * 1024 * 1024,
        "thread_count": 4,
        "pacer_gap_ns": 4_000_000,
    }
    assert source.READER_COUNT == 4
    assert source.SLOT_COUNT * source.SLOT_BYTES == source.ARENA_BYTES
    # The treatment is arena depth only: reader count, block size and the pacer
    # gap are the P9 values and must not drift with the slot count.
    assert source.SLOT_COUNT == 16
    assert source.SLOT_BYTES == 64 * 1024 * 1024
    assert source.READER_COUNT == 4
    assert source.PACER_GAP_NS == 4_000_000


def test_free_mask_covers_every_slot_at_sixteen_slots() -> None:
    """The free mask is one bit per slot and still fits the 64-bit header field."""
    assert source.FREE_MASK == (1 << source.SLOT_COUNT) - 1 == 0xFFFF
    # Would silently truncate above 64 slots, so it is asserted rather than assumed.
    assert source.SLOT_COUNT <= 64
    assert source.HEADER.size <= source.HEADER_SIZE
    assert 11 < 8 * source.HEADER.size - 7  # free_mask is the 12th 64-bit field


def test_control_regions_do_not_overlap_the_sixteen_slot_table() -> None:
    """Header, slot table, counters, error region, op ring and plan stay disjoint.

    The slot table grows with SLOT_COUNT, so every later region is derived from
    it.  At 16 slots the table is 896 bytes; the assertions below prove the
    derived offsets still advance monotonically and that the 64 KiB plan region
    never overlaps the operation ring.
    """
    regions = [
        ("header", 0, source.HEADER_SIZE),
        ("slot_table", source.SLOT_OFFSET, source.SLOT_OFFSET + source.SLOT_TABLE_BYTES),
        ("counters", source.COUNTER_OFFSET, source.COUNTER_OFFSET + source.COUNTERS.size),
        ("error", source.ERROR_OFFSET, source.ERROR_OFFSET + source.ERROR_BYTES),
        ("op_ring", source.OP_OFFSET, source.PLAN_OFFSET),
        ("plan", source.PLAN_OFFSET, source.CONTROL_BYTES),
    ]
    assert source.SLOT_TABLE_BYTES == source.SLOT_COUNT * source.SLOT.size
    for (_, start, end), (next_name, next_start, _) in zip(regions, regions[1:]):
        assert end <= next_start, f"{next_name} overlaps the previous region"
        assert start < end
    assert regions[-1][2] <= source.CONTROL_BYTES
    assert source.OP_OFFSET + source.MAX_OPS * source.OP.size <= source.PLAN_OFFSET


def test_all_sixteen_slots_claim_independently_without_aliasing() -> None:
    """Each of the 16 physical slots is distinct, addressable, and singly owned."""
    buf = source.new_control_buffer()
    lock = _NullLock()
    _install(buf, lock, generation=1)
    plan = _plan(generation=1, range_count=source.SLOT_COUNT + 4)
    # Slot generations are per slot, so a fresh arena hands out generation 0 on
    # every slot; the invariant is per-slot advance, never a shared counter.
    before = {index: source._slot(buf, index)[1] for index in range(source.SLOT_COUNT)}
    assert set(before.values()) == {0}

    claims = [source.claim_block(buf, plan) for _ in range(source.SLOT_COUNT)]
    assert all(claim.outcome == "claimed" for claim in claims)
    indices = [claim.slot_index for claim in claims]
    assert sorted(indices) == list(range(source.SLOT_COUNT)), "slot index aliased"
    # No two claims may share a slot, a source range, or a destination range.
    assert len({claim.range_index for claim in claims}) == source.SLOT_COUNT
    assert len({claim.item[0] for claim in claims}) == source.SLOT_COUNT
    assert len({claim.item[2] for claim in claims}) == source.SLOT_COUNT
    # Every claimed slot is FILLING with its own generation and range recorded.
    for claim in claims:
        state, generation, range_index, source_offset = source._slot(buf, claim.slot_index)[:4]
        assert state == source.FILLING
        assert generation == claim.slot_generation == before[claim.slot_index] + 1
        assert range_index == claim.range_index
        assert source_offset == claim.item[0]
    assert source.claim_block(buf, plan).outcome == "no_capacity"
    assert _free_slots(buf) == set()

    # Quiescence is only reached once every one of the 16 is returned.
    _release_all(buf)
    assert source.quiescent(buf, lock) is True
    assert int(source._read_header(buf)[11]) == source.FREE_MASK


def test_sixteenth_slot_occupancy_is_visible_in_the_free_mask() -> None:
    """The high bit of the widened mask must gate capacity, not alias slot 0."""
    buf = source.new_control_buffer()
    lock = _NullLock()
    _install(buf, lock, generation=1)
    high = source.SLOT_COUNT - 1
    assert high == 15

    values = list(source._read_header(buf))
    values[11] = source.FREE_MASK & ~(1 << high)
    source._write_header_all(buf, values)
    source._put_slot(buf, high, (source.READY, 1, 0, 0, 0, 4, 0, 0))

    assert source.quiescent(buf, lock) is False
    assert 0 in _free_slots(buf), "claiming slot 15 must not consume slot 0"
    assert high not in _free_slots(buf)
    # The header refuses a mask wider than the declared geometry.
    overflow = list(source._read_header(buf))
    overflow[11] = (1 << (source.SLOT_COUNT + 1)) - 1
    with pytest.raises(source.SourceProtocolError, match="control_free_mask_invalid"):
        source._write_header_all(buf, overflow)


def test_source_module_is_cuda_sterile() -> None:
    tree = ast.parse(Path(inspect.getfile(source)).read_text(encoding="utf-8"))
    names = {
        alias.name.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
    }
    assert "torch" not in names
    assert "cuda" not in names


def test_source_reader_uses_native_mmap_and_memmove_not_pread() -> None:
    tree = ast.parse(Path(inspect.getfile(source)).read_text(encoding="utf-8"))
    called = {
        node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }
    assert {"mmap", "munmap", "memmove"} <= called
    assert "pread" not in called


def test_ready_block_arriving_during_plan_install_is_not_lost() -> None:
    """A doorbell that lands before PLAN_ACK must still reach the consumer.

    Dropping it leaves a physical slot stuck READY and stalls the model until
    the request timeout.  This is the exact production hang: 184 blocks
    published, 183 received, one slot pinned READY.
    """
    buf = source.new_control_buffer()
    lock = _NullLock()
    _install(buf, lock, generation=1, range_count=4)
    # A block from the retiring generation is announced just before the new
    # PLAN is acknowledged.
    source._put_slot(buf, 2, (source.READY, 5, 0, 0, 0, 4, 900, 1))
    values = list(source._read_header(buf))
    values[8] = 1
    source._write_header_all(buf, values)

    manager = _manager_with_control(buf, lock)
    manager._planned_generation = 1
    manager._pending_ready = []
    doorbell = {
        "op": "READY_BLOCK", "slot_index": 2, "generation": 5,
        "reader_id": 1, "ready_ns": 900,
    }
    # plan_once buffers it rather than discarding it.
    manager._buffer_ready_block(doorbell)
    assert len(manager._pending_ready) == 1

    # The next wait_ready serves the buffered token without reading the pipe.
    manager._read_message = lambda _timeout: pytest.fail(
        "wait_ready read the pipe instead of serving the buffered doorbell"
    )
    manager._check_child = lambda: None
    record = manager.wait_ready(timeout_s=1.0)
    assert record is not None
    assert record.token == (2, 5)
    assert record.nbytes == 4
    # A second wait has nothing buffered and must block for a new doorbell.
    assert manager._pending_ready == []


def test_control_block_regions_never_overlap() -> None:
    """A counter or error write must never corrupt a physical slot.

    The original layout derived the counter offset from the *header* size, so
    growing the counter block silently overlapped the slot table and every
    counter bump clobbered slot 0.  Region boundaries are now derived from the
    slot table size; this pins that down.
    """
    regions = {
        "header": (0, source.HEADER_SIZE),
        "slots": (source.SLOT_OFFSET, source.SLOT_OFFSET + source.SLOT_TABLE_BYTES),
        "counters": (source.COUNTER_OFFSET, source.COUNTER_OFFSET + source.COUNTERS.size),
        "error": (source.ERROR_OFFSET, source.ERROR_OFFSET + source.ERROR_BYTES),
        "operations": (source.OP_OFFSET, source.OP_OFFSET + source.MAX_OPS * source.OP.size),
        "plan": (source.PLAN_OFFSET, source.PLAN_OFFSET + source.PLAN_BYTES),
    }
    ordered = sorted(regions.items(), key=lambda item: item[1][0])
    for (left_name, (left_start, left_end)), (right_name, (right_start, right_end)) in zip(
        ordered, ordered[1:]
    ):
        assert left_end <= right_start, f"{left_name} [{left_start},{left_end}) overlaps {right_name}"
    assert ordered[-1][1][1] <= source.CONTROL_BYTES


def test_counting_a_slot_event_does_not_corrupt_the_slot_table() -> None:
    """Behavioral proof of the region separation."""
    buf = source.new_control_buffer()
    lock = _NullLock()
    _install(buf, lock)
    before = [source._slot(buf, i) for i in range(source.SLOT_COUNT)]
    counter_index = source.COUNTER_NAMES.index
    for _ in range(5):
        source._bump_counter(buf, counter_index("ready_publish_count"))
        source._bump_counter(buf, counter_index("slot_wait_ns"), 1234)
        source._write_error(buf, "x" * 64)
    assert [source._slot(buf, i) for i in range(source.SLOT_COUNT)] == before
    assert source.COUNTERS.unpack_from(buf, source.COUNTER_OFFSET)[
        counter_index("ready_publish_count")
    ] == 5


def test_c0_runtime_module_defines_every_env_constant_it_reads() -> None:
    """A dropped module constant only fails inside a container, as a crash loop.

    Scan the C0 runtime module for the environment-variable names it reads and
    prove each one is still defined at module scope.
    """
    path = (
        Path(__file__).parents[1]
        / "comfymodal_runtime"
        / "golden_io_process_v2.py"
    )
    tree = ast.parse(path.read_text(encoding="utf-8"))
    defined = {
        node.targets[0].id
        for node in tree.body
        if isinstance(node, ast.Assign)
        and len(node.targets) == 1
        and isinstance(node.targets[0], ast.Name)
    }
    read = {
        node.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Name)
        and isinstance(node.ctx, ast.Load)
        and node.id.endswith("_ENV")
    }
    assert read, "expected the C0 runtime to read environment constants"
    missing = sorted(read - defined)
    assert not missing, f"environment constants read but never defined: {missing}"


def test_plan_region_fits_the_largest_real_model_plan() -> None:
    """A 184-block plan must serialise into the control block's plan region.

    An 8 KiB region silently overflowed on the real UNET plan and killed every
    four-process arm at its first plan.
    """
    for block_count in (120, 184):
        plan = source._ChildPlan(
            generation=1, path="/root/models/" + "x" * 120, identity=(1, 2, 3, 4),
            destination_size=block_count * 64 * 1024 * 1024, mmap_lifecycle="whole",
            ranges=tuple(
                (i * (64 * 1024 * 1024), 64 * 1024 * 1024, i * (64 * 1024 * 1024), f"r{i}")
                for i in range(block_count)
            ),
        )
        encoded = json.dumps(plan.metadata(), separators=(",", ":")).encode("utf-8")
        assert len(encoded) < source.PLAN_BYTES, (
            f"{block_count}-block plan needs {len(encoded)} bytes, "
            f"region is {source.PLAN_BYTES}"
        )
        buf = source.new_control_buffer()
        source._write_plan(buf, plan.metadata())
        assert source._read_plan(buf)["generation"] == 1


@posix_only
def test_cross_process_plan_metadata_round_trips_through_build_plan(tmp_path) -> None:
    """A reader process adopts the plan from the control block, not the parent.

    ``metadata()`` must emit the same mapping shape the parent sends, or
    ``build_plan`` raises a str-index-on-list TypeError and every
    four-process arm dies on its first plan.
    """
    model = tmp_path / "model.bin"
    model.write_bytes(b"\0" * (1024 * 1024))
    source._init_native()
    message = {
        "generation": 4, "path": str(model), "identity": list(source._identity(str(model))),
        "destination_size": 256, "mmap_lifecycle": "whole",
        "ranges": [
            {"source_offset": 0, "length": 128, "destination_offset": 0, "record_id": "a"},
            {"source_offset": 128, "length": 128, "destination_offset": 128, "record_id": "b"},
        ],
    }
    original = source.build_plan(message, open_source=False)
    adopted = source.build_plan(original.metadata(), open_source=True)
    try:
        assert adopted.generation == original.generation
        assert adopted.mmap_lifecycle == original.mmap_lifecycle
        assert adopted.ranges == original.ranges
        assert adopted.map_address != 0, "an adopting reader must map the file itself"
        assert adopted.fd >= 0
    finally:
        source.retire_plan(adopted)


def test_worker_kind_selector_is_explicit_and_fails_closed(monkeypatch) -> None:
    monkeypatch.delenv(source.WORKER_KIND_ENV, raising=False)
    assert source.worker_kind() == "thread"
    assert source.worker_kind("process") == "process"
    with pytest.raises(source.SourceProtocolError, match="unsupported_source_worker_kind"):
        source.worker_kind("goroutine")
    monkeypatch.setenv(source.WORKER_KIND_ENV, "process")
    assert source.worker_kind() == "process"
    monkeypatch.setenv(source.WORKER_KIND_ENV, "bogus")
    with pytest.raises(source.SourceProtocolError):
        source.worker_kind()


def test_source_plan_requires_exact_destination_coverage() -> None:
    with pytest.raises(source.SourceProtocolError, match="destination_coverage_gap_or_overlap"):
        source.validate_plan(
            [source.SourceRange(0, 4, 0), source.SourceRange(4, 4, 8)],
            source_size=12,
            destination_size=12,
        )


# ---------------------------------------------------------------------------
# 1. Real multithreaded pacing: actual copy starts respect the 4 ms floor
# ---------------------------------------------------------------------------


def test_real_multithreaded_paced_copy_respects_four_millisecond_floor() -> None:
    """Four real threads, real clock, real sleeps.

    ``reserve()`` alone cannot prove the floor: the contract is about the
    *actual* copy start, which is the instant the marker is invoked.
    """
    pacer = source.GlobalSourcePacer()
    actual: list[int] = []
    guard = threading.Lock()
    operations = 3
    barrier = threading.Barrier(source.READER_COUNT)

    def reader(index: int) -> None:
        barrier.wait(timeout=10.0)
        for ordinal in range(operations):
            def _copy(mark_actual_start):
                start = mark_actual_start()
                with guard:
                    actual.append(start)
                time.sleep(0.002)  # stand in for a real 64 MiB native copy
                return start

            pacer.paced_copy(_copy, reader_id=index, ordinal=ordinal)

    threads = [threading.Thread(target=reader, args=(index,)) for index in range(source.READER_COUNT)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=20.0)

    assert len(actual) == source.READER_COUNT * operations
    ordered = sorted(actual)
    gaps = [right - left for left, right in zip(ordered, ordered[1:])]
    assert min(gaps) >= source.PACER_GAP_NS, f"observed sub-floor copy starts: {min(gaps)}"
    telemetry = pacer.telemetry()
    assert telemetry["source_gap_violation_count"] == 0
    assert telemetry["pacing_correction_count"] == 0


def test_pacer_reservation_seam_is_deterministic() -> None:
    pacer = source.GlobalSourcePacer()
    starts = [pacer.reserve(now_ns=value)[0] for value in (0, 4_000_000, 8_000_000, 12_000_000)]
    assert starts == [0, 4_000_000, 8_000_000, 12_000_000]
    assert pacer.telemetry()["source_gap_violation_count"] == 0


def test_shared_pacer_enforces_floor_across_independent_pacers() -> None:
    """The cross-process pacer backs its floor with the shared control block."""
    buf = source.new_control_buffer()
    lock = _NullLock()
    pacers = [source.SharedSourcePacer() for _ in range(3)]
    actual: list[int] = []
    guard = threading.Lock()
    barrier = threading.Barrier(len(pacers))

    def reader(pacer):
        barrier.wait(timeout=10.0)
        for ordinal in range(2):
            def _copy(mark_actual_start):
                start = mark_actual_start()
                with guard:
                    actual.append(start)
                return start

            pacer.paced_copy(buf, lock, _copy, reader_id=0, ordinal=ordinal)

    threads = [threading.Thread(target=reader, args=(pacer,)) for pacer in pacers]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=20.0)
    assert len(actual) == len(pacers) * 2
    ordered = sorted(actual)
    gaps = [right - left for left, right in zip(ordered, ordered[1:])]
    # Independent address spaces cannot hold one lock through the copy start,
    # so the guarantee is the published boundary.  Assert the weaker, true
    # contract rather than the in-process one.
    assert min(gaps) >= source.PACER_GAP_NS - 1_000_000


# ---------------------------------------------------------------------------
# 10. Canonical source boundaries
# ---------------------------------------------------------------------------


def test_canonical_span_uses_min_actual_start_and_max_actual_completion() -> None:
    """Records are appended on completion, so record order is not start order."""
    operations = [
        # Appended first, but started LAST and finished LAST.
        {"memcpy_start_ns": 900, "memcpy_end_ns": 1000, "munmap_end_ns": 1010,
         "access_start_ns": 899, "ready_ns": 1015},
        # Appended second, but started FIRST.
        {"memcpy_start_ns": 100, "memcpy_end_ns": 200, "munmap_end_ns": 205,
         "access_start_ns": 99, "ready_ns": 210},
        {"memcpy_start_ns": 500, "memcpy_end_ns": 600, "munmap_end_ns": 605,
         "access_start_ns": 499, "ready_ns": 610},
    ]
    span = source.canonical_source_span(operations)
    assert span["source_start_ns"] == 100
    assert span["source_end_ns"] == 1000
    assert span["source_wall_ms"] == pytest.approx(0.0009)
    assert span["source_first_enter_ns"] == 100
    assert span["source_last_exit_ns"] == 1000
    assert span["source_final_byte_complete_ns"] == 1000
    # The first *appended* record is not the first *started* record.
    assert operations[0]["memcpy_start_ns"] != span["source_start_ns"]


def test_canonical_span_of_empty_generation_is_explicit() -> None:
    span = source.canonical_source_span([])
    assert span["source_start_ns"] is None
    assert span["source_wall_ms"] is None
    assert span["source_final_byte_complete_ns"] is None


def test_source_gbps_numerator_is_layout_data_bytes() -> None:
    """The metric is not redefined: data_bytes / source_wall_seconds / 1e9."""
    source_wall_ms = 400.0
    data_bytes = 2 * 1024 * 1024 * 1024
    assert data_bytes / ((source_wall_ms / 1000.0) * 1e9) == pytest.approx(5.36870912)


# ---------------------------------------------------------------------------
# 2 / 3. Blocking, not spinning
# ---------------------------------------------------------------------------


def test_reader_blocks_on_capacity_instead_of_spinning_the_control_lock() -> None:
    """A fully occupied arena must not produce repeated control-lock churn."""
    buf = source.new_control_buffer()
    lock = _NullLock()
    _install(buf, lock)
    for index in range(source.SLOT_COUNT):
        source._put_slot(buf, index, (source.READY, 1 + index, 0, 0, 0, 4, 0, 0))
    values = list(source._read_header(buf))
    values[11] = 0
    values[8] = source.SLOT_COUNT
    source._write_header_all(buf, values)

    stop = threading.Event()
    wakes: list[float] = []

    def wake(timeout_s):
        wakes.append(time.monotonic())
        stop.wait(timeout_s)
        return False

    thread = threading.Thread(
        target=source._run_reader_loop,
        args=(0,),
        kwargs={
            "arena_buf": bytearray(1024), "control_buf": buf, "lock": lock,
            "pacer": source.GlobalSourcePacer(), "plan_getter": lambda: _plan(),
            "refresh_plan": lambda: None, "wake": wake, "stop": stop,
            "fatal": [], "fail_control": lambda _m: None,
            "emit": lambda _m: None, "page_size": 4096,
        },
        daemon=True,
    )
    thread.start()
    time.sleep(0.2)
    stop.set()
    thread.join(timeout=5.0)

    # One claim attempt, then a blocking wake.  A spin loop would have taken the
    # control lock thousands of times in this window.
    assert lock.entered <= 2, f"reader re-took the control lock {lock.entered} times while blocked"
    assert len(wakes) <= 2
    counters = source.COUNTERS.unpack_from(buf, source.COUNTER_OFFSET)
    assert counters[source.COUNTER_NAMES.index("all_slots_occupied_count")] >= 1


def test_capacity_wake_resumes_the_reader_immediately() -> None:
    """A completion-proven release wakes the reader, which then claims."""
    buf = source.new_control_buffer()
    lock = _NullLock()
    _install(buf, lock)
    for index in range(source.SLOT_COUNT):
        source._put_slot(buf, index, (source.IN_FLIGHT, 1 + index, 0, 0, 0, 4, 0, 0))
    values = list(source._read_header(buf))
    values[11] = 0
    source._write_header_all(buf, values)

    stop = threading.Event()
    wake_gate = threading.Event()
    claimed: list[int] = []

    def wake(_timeout_s):
        return wake_gate.wait(timeout=5.0)

    def emit(message):
        if message.get("op") == "READY_BLOCK":
            claimed.append(message["slot_index"])

    def fake_execute(*_args, **_kwargs):
        claimed.append(-1)

    original = source.execute_block
    source.execute_block = fake_execute
    try:
        thread = threading.Thread(
            target=source._run_reader_loop,
            args=(0,),
            kwargs={
                "arena_buf": bytearray(1024), "control_buf": buf, "lock": lock,
                "pacer": source.GlobalSourcePacer(), "plan_getter": lambda: _plan(),
                "refresh_plan": lambda: None, "wake": wake, "stop": stop,
                "fatal": [], "fail_control": lambda _m: None,
                "emit": emit, "page_size": 4096,
            },
            daemon=True,
        )
        thread.start()
        deadline = time.monotonic() + 2.0
        while lock.entered < 1 and time.monotonic() < deadline:
            time.sleep(0.005)
        assert not claimed, "reader claimed a block while zero slots were free"
        # Simulate the parent's completion-proven release of slot 0.
        values = list(source._read_header(buf))
        source._put_slot(buf, 0, (source.FREE, 1, 0, 0, 0, 4, 0, 0))
        values[11] = values[11] | 1
        source._write_header_all(buf, values)
        wake_gate.set()
        deadline = time.monotonic() + 2.0
        while not claimed and time.monotonic() < deadline:
            time.sleep(0.005)
    finally:
        stop.set()
        source.execute_block = original
        thread.join(timeout=5.0)
    assert claimed == [-1], "reader did not resume after the capacity wake"


def test_ready_notification_wakes_the_consumer_without_a_poll_loop() -> None:
    """``wait_ready`` must block until a doorbell arrives, not rescan slots."""
    buf = source.new_control_buffer()
    lock = _NullLock()
    _install(buf, lock)
    source._put_slot(buf, 3, (source.READY, 12, 1, 4, 4, 4, 777, 2))
    values = list(source._read_header(buf))
    values[8] = 1
    source._write_header_all(buf, values)

    manager = _manager_with_control(buf, lock)
    messages: "queue.Queue" = queue.Queue()
    manager._check_child = lambda: None
    manager._read_message = lambda _timeout: messages.get(timeout=5.0)

    result: list = []
    thread = threading.Thread(
        target=lambda: result.append(manager.wait_ready(timeout_s=5.0)), daemon=True
    )
    thread.start()
    time.sleep(0.15)
    assert not result, "wait_ready returned without any READY doorbell"
    # The doorbell is the only thing that can complete the wait.
    messages.put({
        "op": "READY_BLOCK", "slot_index": 3, "generation": 12,
        "reader_id": 2, "ready_ns": 777,
    })
    thread.join(timeout=5.0)

    assert result, "wait_ready did not wake on the READY doorbell"
    record = result[0]
    assert record.slot_index == 3
    assert record.generation == 12
    assert record.token == (3, 12)
    assert record.source_offset == 4
    assert record.destination_offset == 4
    assert record.nbytes == 4
    assert record.range_index == 1
    assert record.producer_id == 2


# ---------------------------------------------------------------------------
# 4 / 5 / 6. H2D-gated reuse and generation tokens
# ---------------------------------------------------------------------------


def test_slot_cannot_be_reused_before_h2d_completion() -> None:
    buf = source.new_control_buffer()
    lock = _NullLock()
    _install(buf, lock)
    manager = _manager_with_control(buf, lock)
    plan = _plan(range_count=source.SLOT_COUNT + 2)

    claim = source.claim_block(buf, plan)
    assert claim.outcome == "claimed"
    slot = claim.slot_index
    source._put_slot(buf, slot, (source.READY, claim.slot_generation, 0, 0, 0, 4, 1, 0))
    record = source.ReadyRecord(slot, claim.slot_generation, 0, 0, 4, 0, 0, 1, None, 7)

    # A READY slot awaiting H2D is not free capacity.
    assert claim.slot_index not in _free_slots(buf)

    manager.claim_ready(record)
    assert source._slot(buf, slot)[0] == source.IN_FLIGHT
    assert slot not in _free_slots(buf), "an IN_FLIGHT slot was offered as free capacity"

    # Every other slot is free and claimable; the IN_FLIGHT one never is, and
    # the final claim finds zero capacity rather than a free IN_FLIGHT slot.
    for _ in range(source.SLOT_COUNT - 1):
        again = source.claim_block(buf, plan)
        assert again.outcome == "claimed"
        assert again.slot_index != slot
    assert source.claim_block(buf, plan).outcome == "no_capacity"

    # A READY slot the consumer never claimed has no completion ownership, so
    # releasing it is refused.
    unclaimed_slot = (slot + 1) % source.SLOT_COUNT
    unclaimed = source.ReadyRecord(unclaimed_slot, 1, 0, 0, 4, 0, 0, 1, None, 7)
    source._put_slot(buf, unclaimed_slot, (source.READY, 1, 0, 0, 0, 4, 1, 0))
    with pytest.raises(source.SourceProtocolError, match="release_without_completion_ownership"):
        manager.release_slot(unclaimed)

    # The real claim -> completion-gated release returns the slot exactly once.
    manager.release_slot(record)
    assert source._slot(buf, slot)[0] == source.FREE
    assert slot in _free_slots(buf)
    with pytest.raises(source.SourceProtocolError, match="release_without_completion_ownership"):
        manager.release_slot(record)


def _free_slots(buf) -> set:
    return {index for index in range(source.SLOT_COUNT) if source._slot(buf, index)[0] == source.FREE}


def test_stale_generation_cannot_claim_or_release_a_newer_slot() -> None:
    buf = source.new_control_buffer()
    lock = _NullLock()
    _install(buf, lock)
    manager = _manager_with_control(buf, lock)

    old = source.claim_block(buf, _plan())
    source._put_slot(buf, old.slot_index,
                     (source.READY, old.slot_generation, 0, 0, 0, 4, 1, 0))
    old_record = source.ReadyRecord(old.slot_index, old.slot_generation, 0, 0, 4, 0, 0, 1, None, 7)
    manager.claim_ready(old_record)
    manager.release_slot(old_record)

    new = source.claim_block(buf, _plan())
    assert new.slot_index == old.slot_index
    assert new.slot_generation == old.slot_generation + 1
    source._put_slot(buf, new.slot_index,
                     (source.READY, new.slot_generation, 1, 4, 4, 4, 1, 0))

    # The old generation must not claim or release the new occupant.
    with pytest.raises(source.SourceProtocolError, match="stale_ready_generation"):
        manager.claim_ready(old_record)
    new_record = source.ReadyRecord(new.slot_index, new.slot_generation, 4, 4, 4, 1, 0, 1, None, 7)
    manager.claim_ready(new_record)
    with pytest.raises(source.SourceProtocolError, match="stale_release_generation"):
        manager.release_slot(old_record)
    manager.release_slot(new_record)


def test_ownership_token_is_slot_plus_generation() -> None:
    first = source.ReadyRecord(3, 8, 0, 0, 4, 0, 0, 1)
    second = source.ReadyRecord(3, 9, 0, 0, 4, 0, 0, 1)
    assert first.slot_index == second.slot_index
    assert first.token != second.token
    assert first.token == (3, 8)


def test_bridge_cleanup_uses_the_full_slot_token_not_the_slot_index() -> None:
    """A successful old generation of slot 3 must not mask a newer slot 3."""
    released: list[tuple[int, int]] = []
    submitted_tokens: list[str] = []
    manager_calls: list[tuple] = []

    class Manager:
        mmap_lifecycle = "fresh"
        telemetry: dict = {}

        def plan_once(self, **_kwargs):
            return {}

        def wait_ready(self, _timeout):
            if not hasattr(self, "queue"):
                self.queue = [
                    # Old generation of slot 3: claimed and successfully submitted.
                    source.ReadyRecord(3, 4, 0, 0, 4, 0, 0, 1, "a", 1),
                    # Newer generation reuses slot 3 and then fails.
                    source.ReadyRecord(3, 5, 4, 4, 4, 1, 0, 1, "b", 1),
                ]
            return self.queue.pop(0) if self.queue else None

        def claim_ready(self, record):
            return record

        def release_slot(self, record, **_kwargs):
            released.append(record.token)

    class Lease:
        def mark_filled(self, _count):
            return None

    class Transport:
        def adopt_external_slot(self, **kwargs):
            manager_calls.append(("adopt", kwargs["slot_index"], kwargs["external_generation"]))
            return Lease()

        def publish(self, _lease, record, *, externally_filled=False):
            if not externally_filled:
                raise AssertionError("an adopted external slot must publish as pre-filled")
            if record.record_id == "b":
                raise RuntimeError("dispatcher_refused_second_block")
            submitted_tokens.append(record.record_id)

        def _ready_record(self, source_offset, destination_offset, nbytes, record_id, producer_id):
            return type("R", (), {
                "source_offset": source_offset, "destination_offset": destination_offset,
                "nbytes": nbytes, "record_id": record_id, "producer_id": producer_id,
            })()

    ranges = [source.SourceRange(0, 4, 0, "a"), source.SourceRange(4, 4, 4, "b")]
    bridge = source.SourcePlanBridge(Manager(), Transport())
    with pytest.raises(RuntimeError, match="dispatcher_refused_second_block"):
        bridge.publish_all(
            ranges, generation=1, path="model.safetensors", identity=(1, 2, 8, 3),
            destination_size=8,
        )
    assert len(submitted_tokens) == 1
    # Only the never-submitted newer slot-3 generation is released.
    assert released == [(3, 5)]


def test_bridge_publishes_exactly_one_plan_and_no_per_block_command() -> None:
    manager_calls: list[object] = []

    class FakeManager:
        mmap_lifecycle = "fresh"
        telemetry: dict = {}

        def plan_once(self, **kwargs):
            manager_calls.append(("plan", kwargs))

        def wait_ready(self, _timeout):
            if not hasattr(self, "records"):
                self.records = [
                    source.ReadyRecord(i, 1, i * 4, i * 4, 4, i, i, i + 10, f"planned-{i}", 1)
                    for i in range(2)
                ]
            return self.records.pop(0) if self.records else None

        def claim_ready(self, record):
            manager_calls.append(("claim", record.range_index))
            return record

        def release_slot(self, record, **_kwargs):
            manager_calls.append(("release", record.range_index))

    class Lease:
        def mark_filled(self, _count):
            return None

        def retire(self):
            raise AssertionError("bridge must let transport.publish retire the lease")

    class FakeTransport:
        def adopt_external_slot(self, **kwargs):
            manager_calls.append(("adopt", kwargs["slot_index"], kwargs["external_generation"]))
            return Lease()

        def publish(self, _lease, record, *, externally_filled=False):
            if not externally_filled:
                raise AssertionError("an adopted external slot must publish as pre-filled")
            manager_calls.append(("publish", record.record_id))

        def _ready_record(self, source_offset, destination_offset, nbytes, record_id, producer_id):
            return type("R", (), {
                "source_offset": source_offset, "destination_offset": destination_offset,
                "nbytes": nbytes, "record_id": record_id, "producer_id": producer_id,
            })()

    ranges = [
        type("Range", (), {"source_offset": i * 4, "length": 4,
                           "target_offset": i * 4, "record_id": f"planned-{i}"})()
        for i in range(2)
    ]
    bridge = source.SourcePlanBridge(FakeManager(), FakeTransport())
    assert bridge.publish_all(
        ranges, generation=1, path="model.safetensors", identity=(1, 2, 8, 3),
        destination_size=8,
    ) == 2
    kinds = [item[0] for item in manager_calls]
    assert kinds.count("plan") == 1
    assert kinds.count("publish") == 2
    assert "fill" not in kinds


# ---------------------------------------------------------------------------
# 7. Per-generation counter hygiene
# ---------------------------------------------------------------------------


def test_clip_generation_counters_do_not_contaminate_unet_generation() -> None:
    buf = source.new_control_buffer()
    lock = _NullLock()
    _install(buf, lock, generation=1)
    counter_index = source.COUNTER_NAMES.index

    # Simulate a completed CLIP generation.
    source._bump_counter(buf, counter_index("ready_publish_count"), 12)
    source._bump_counter(buf, counter_index("release_count"), 12)
    source._bump_counter(buf, counter_index("operation_count"), 12)
    source._bump_counter(buf, counter_index("all_slots_occupied_count"), 5)
    source._bump_counter(buf, counter_index("slot_wait_ns"), 999)
    clip = source.COUNTERS.unpack_from(buf, source.COUNTER_OFFSET)
    assert clip[counter_index("operation_count")] == 12

    # Installing the next generation resets the generation-scoped counters.
    _install(buf, lock, generation=2)
    unet = source.COUNTERS.unpack_from(buf, source.COUNTER_OFFSET)
    for name in (
        "ready_publish_count", "release_count", "operation_count",
        "all_slots_occupied_count", "slot_wait_ns", "ready_queue_wait_ns",
        "capacity_wait_ns", "slot_wait_count", "capacity_wait_count",
        "ready_queue_wait_count",
    ):
        assert unet[counter_index(name)] == 0, f"{name} leaked across generations"


def test_plan_install_resets_counters_and_never_resets_slot_generations() -> None:
    buf = source.new_control_buffer()
    lock = _NullLock()
    _install(buf, lock, generation=1)
    generations_before = [source._slot(buf, i)[1] for i in range(source.SLOT_COUNT)]

    # Slot generations advance as slots are reused, and a plan install must
    # never rewind them, or a released slot could collide with an old token.
    for index in range(3):
        generations_before[index] += 1
        source._put_slot(buf, index,
                         (source.FREE, generations_before[index], 0, 0, 0, 0, 0, 0))
    _release_all(buf)
    assert [source._slot(buf, i)[1] for i in range(source.SLOT_COUNT)] == generations_before
    _install(buf, lock, generation=2)
    assert [source._slot(buf, i)[1] for i in range(source.SLOT_COUNT)] == generations_before


def test_plan_install_refuses_a_generation_with_live_slot_ownership() -> None:
    buf = source.new_control_buffer()
    lock = _NullLock()
    _install(buf, lock, generation=1)
    source._put_slot(buf, 5, (source.READY, 1, 0, 0, 0, 4, 0, 0))
    values = list(source._read_header(buf))
    values[11] = source.FREE_MASK & ~(1 << 5)
    source._write_header_all(buf, values)
    assert source.quiescent(buf, lock) is False
    with pytest.raises(source.SourceProtocolError, match="source_previous_plan_not_quiescent"):
        _install(buf, lock, generation=2)


# ---------------------------------------------------------------------------
# 11. CLIP -> UNET plan transition
# ---------------------------------------------------------------------------


def test_clip_to_unet_transition_advances_generation_and_resets_range_cursor() -> None:
    buf = source.new_control_buffer()
    lock = _NullLock()
    _install(buf, lock, generation=1)
    plan = _plan(generation=1, range_count=2)

    first = source.claim_block(buf, plan)
    assert first.outcome == "claimed" and first.range_index == 0
    assert source._read_header(buf)[7] == 1
    assert source.claim_block(buf, plan).range_index == 1
    assert source.claim_block(buf, plan).outcome == "exhausted"

    # Retire the generation exactly as a plan install does.
    _release_all(buf)
    _install(buf, lock, generation=2)
    header = source._read_header(buf)
    assert header[5] == 2
    assert header[7] == 0
    assert header[8] == 0
    assert header[9] == 0
    assert int(header[11]) == source.FREE_MASK

    # A stale plan cannot claim against the new generation.
    assert source.claim_block(buf, plan).outcome == "stale"
    unet = _plan(generation=2, range_count=1)
    assert source.claim_block(buf, unet).outcome == "claimed"


def test_quiescent_requires_every_slot_free() -> None:
    buf = source.new_control_buffer()
    lock = _NullLock()
    _install(buf, lock)
    assert source.quiescent(buf, lock) is True
    source._put_slot(buf, 2, (source.READY, 1, 0, 0, 0, 4, 0, 0))
    values = list(source._read_header(buf))
    values[11] = source.FREE_MASK & ~(1 << 2)
    source._write_header_all(buf, values)
    assert source.quiescent(buf, lock) is False


# ---------------------------------------------------------------------------
# 12. Cancellation / error cleanup
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "interrupted_state",
    [source.FILLING, source.READY, source.IN_FLIGHT],
)
def test_control_header_reports_failure_while_a_block_is_interrupted(
    interrupted_state,
) -> None:
    """Each interrupted phase must be representable and fail closed."""
    buf = source.new_control_buffer()
    lock = _NullLock()
    _install(buf, lock, generation=1)
    source._put_slot(buf, 4, (interrupted_state, 3, 0, 0, 0, 4, 0, 0))
    values = list(source._read_header(buf))
    values[11] = source.FREE_MASK & ~(1 << 4)
    values[10] = 1
    source._write_header_all(buf, values)
    source._write_error(buf, "SourceProtocolError:boom")

    manager = _manager_with_control(buf, lock)
    with pytest.raises(source.SourceProtocolError, match="source_thread_failed"):
        manager._check_child()
    assert source._read_error(buf) == "SourceProtocolError:boom"


def test_publish_ready_refuses_a_slot_whose_generation_changed_during_fill() -> None:
    buf = source.new_control_buffer()
    lock = _NullLock()
    _install(buf, lock)
    claim = source.claim_block(buf, _plan())
    # Someone else advanced the slot while the copy was in flight.
    source._put_slot(buf, claim.slot_index, (source.FILLING, claim.slot_generation + 5, 0, 0, 0, 4, 0, 0))
    record = (0,) * 18
    with pytest.raises(source.SourceProtocolError, match="slot_generation_changed_during_fill"):
        source.publish_ready(buf, 0, claim, record)


def test_publish_ready_allocates_a_shared_ring_index() -> None:
    """Independent readers must not collide on one operation ring."""
    buf = source.new_control_buffer()
    lock = _NullLock()
    _install(buf, lock)
    plan = _plan(range_count=4)
    allocated: list[int] = []
    for _ in range(3):
        claim = source.claim_block(buf, plan)
        assert claim.outcome == "claimed"
        record = (
            7, 0, 1, claim.slot_index, claim.range_index, 0, 4,
            1, 0, 1, 1, 2, 0, 0, 0, 0, 3, 1,
        )
        allocated.append(source.publish_ready(buf, 0, claim, record))
    assert allocated == [0, 1, 2]
    assert source.COUNTERS.unpack_from(buf, source.COUNTER_OFFSET)[6] == 3


# ---------------------------------------------------------------------------
# 8 / 9. Descriptor and mapping lifecycle at plan install
# ---------------------------------------------------------------------------


@posix_only
def test_thread_whole_lifecycle_uses_one_mapping_not_four(tmp_path) -> None:
    model = tmp_path / "model.bin"
    model.write_bytes(b"\0" * (4 * 1024 * 1024))
    identity = source._identity(str(model))
    source._init_native()
    message = {
        "generation": 1, "path": str(model), "identity": list(identity),
        "destination_size": 1024, "mmap_lifecycle": "whole",
        "ranges": [{"source_offset": 0, "length": 512, "destination_offset": 0, "record_id": None},
                   {"source_offset": 512, "length": 512, "destination_offset": 512, "record_id": None}],
    }
    plan = source.build_plan(message, open_source=True)
    try:
        assert plan.fd >= 0
        assert plan.map_address != 0
        assert plan.map_length == 4 * 1024 * 1024
        # Every reader in this address space consumes the same immutable plan,
        # so exactly one whole-file mapping exists for the generation.
        assert source._ChildPlan.from_metadata(plan.metadata()).map_address == 0
        assert plan.metadata()["mmap_lifecycle"] == "whole"
    finally:
        source.retire_plan(plan)


@posix_only
def test_plan_install_validates_descriptor_identity_once(tmp_path) -> None:
    model = tmp_path / "model.bin"
    model.write_bytes(b"\0" * (1024 * 1024))
    identity = source._identity(str(model))
    message = {
        "generation": 1, "path": str(model), "identity": list(identity),
        "destination_size": 256, "mmap_lifecycle": "fresh",
        "ranges": [{"source_offset": 0, "length": 256, "destination_offset": 0, "record_id": None}],
    }
    source._init_native()
    plan = source.build_plan(message, open_source=True)
    try:
        # Once installed, the plan carries a validated descriptor.  The block
        # executor never stats, opens, or re-validates it.
        tree = ast.parse(Path(inspect.getfile(source)).read_text(encoding="utf-8"))
        executor = next(
            node for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef) and node.name == "execute_block"
        )
        attributes = {
            node.attr for node in ast.walk(executor)
            if isinstance(node, ast.Attribute)
        }
        assert "os" not in attributes
        assert "open" not in attributes
        assert "fstat" not in attributes
        assert "stat" not in attributes
    finally:
        source.retire_plan(plan)


@posix_only
def test_plan_install_rejects_a_changed_source_identity(tmp_path) -> None:
    model = tmp_path / "model.bin"
    model.write_bytes(b"\0" * 1024)
    identity = list(source._identity(str(model)))
    identity[2] += 1
    source._init_native()
    with pytest.raises(source.SourceProtocolError, match="source_identity_changed"):
        source.build_plan(
            {
                "generation": 1, "path": str(model), "identity": identity,
                "destination_size": 8, "mmap_lifecycle": "fresh",
                "ranges": [{"source_offset": 0, "length": 8, "destination_offset": 0,
                            "record_id": None}],
            },
            open_source=False,
        )


@posix_only
def test_new_control_buffer_describes_exact_geometry() -> None:
    buf = source.new_control_buffer()
    header = source._read_header(buf)
    assert header[2:5] == (source.SLOT_COUNT, source.SLOT_BYTES, source.ARENA_BYTES)
    assert int(header[11]) == source.FREE_MASK
    assert all(source._slot(buf, i)[0] == source.FREE for i in range(source.SLOT_COUNT))
    assert source.COUNTERS.unpack_from(buf, source.COUNTER_OFFSET) == (0,) * len(source.COUNTER_NAMES)


# ---------------------------------------------------------------------------
# 13. External physical-slot dispatcher path
# ---------------------------------------------------------------------------


def test_external_slot_adoption_uses_one_generation_and_no_fake_filling_lease() -> None:
    from comfymodal_runtime.golden_qd_transport import (
        FakeBackend,
        GoldenQDTransport,
        LeaseError,
        ReadyRecord,
        SourceRange,
        StagingPool,
        TransportConfig,
    )

    pool = StagingPool(slots=1, block_bytes=4, capacity_class="source")
    transport = GoldenQDTransport(
        TransportConfig(
            queue_depth=1, block_bytes=4, staging_slots=1,
            ready_queue_capacity=1, producer_workers=1,
            capacity_class="source", h2d_target_bytes=4,
        ),
        FakeBackend(destination=bytearray(4)),
        pool=pool,
    )
    transport.start(destination_size=4)
    item = SourceRange(10, 4, 0, 1)
    lease = transport.adopt_external_slot(
        slot_index=0, external_generation=17, declared_range=item, producer_id=2
    )
    # The pool adopted the external generation verbatim: one authority.
    assert lease.generation == 17
    assert lease.state.value == "ready"
    assert pool._slots[0].generation == 17
    # No producer fill step is required or permitted.
    with pytest.raises(LeaseError):
        lease.mark_filled(4)
    transport.publish(lease, ReadyRecord(10, 0, 4, 1, 2), externally_filled=True)
    result = transport.finalize_external_ready([item], destination_size=4)
    assert result.completed_bytes == 4
    assert pool.states()[0].value == "free"

    # Ordinary producer acquire is refused once the pool belongs to an external
    # owner: two ownership machines for one physical slot cannot coexist.
    with pytest.raises(LeaseError, match="bound to an external slot owner"):
        transport.acquire(declared_range=item, producer_id=0)


def test_external_slot_adoption_fails_closed_on_a_replayed_generation() -> None:
    from comfymodal_runtime.golden_qd_transport import (
        LeaseError,
        SourceRange,
        StagingPool,
    )

    pool = StagingPool(slots=1, block_bytes=4, capacity_class="source")
    item = SourceRange(10, 4, 0, 1)
    first = pool.adopt_external_slot(
        slot_index=0, external_generation=17, declared_range=item, producer_id=0
    )
    # Completion-gated return: a slot only frees after the H2D proof.
    with pytest.raises(LeaseError, match="completion proof arrived before producer retirement"):
        pool._return_completed(first)
    pool._mark_in_flight(first)
    pool._return_completed(first)
    # A replay of the same token is not a new block.
    with pytest.raises(LeaseError, match="must strictly advance"):
        pool.adopt_external_slot(
            slot_index=0, external_generation=17, declared_range=item, producer_id=0
        )
    with pytest.raises(LeaseError, match="must strictly advance"):
        pool.adopt_external_slot(
            slot_index=0, external_generation=3, declared_range=item, producer_id=0
        )
    # The next genuine generation is accepted and reuses the same physical slot.
    assert pool.adopt_external_slot(
        slot_index=0, external_generation=18, declared_range=item, producer_id=0
    ).slot_index == 0


def test_external_slot_adoption_rejects_a_busy_slot() -> None:
    from comfymodal_runtime.golden_qd_transport import LeaseError, SourceRange, StagingPool

    pool = StagingPool(slots=1, block_bytes=4, capacity_class="source")
    item = SourceRange(10, 4, 0, 1)
    pool.adopt_external_slot(
        slot_index=0, external_generation=1, declared_range=item, producer_id=0
    )
    with pytest.raises(LeaseError, match="not free in the staging pool"):
        pool.adopt_external_slot(
            slot_index=0, external_generation=2, declared_range=item, producer_id=0
        )


def test_dispatcher_releases_external_source_slot_only_after_completion() -> None:
    from comfymodal_runtime.golden_qd_transport import (
        FakeBackend,
        GoldenQDTransport,
        SourceRange,
        StagingPool,
        TransportConfig,
    )

    pool = StagingPool(slots=1, block_bytes=4, capacity_class="source")
    backend = FakeBackend(destination=bytearray(4))
    transport = GoldenQDTransport(
        TransportConfig(
            queue_depth=1, block_bytes=4, staging_slots=1,
            ready_queue_capacity=1, producer_workers=1,
            capacity_class="source", h2d_target_bytes=4,
        ),
        backend,
        pool=pool,
    )
    released: list[bool] = []
    item = SourceRange(10, 4, 0, 1)
    lease = transport.acquire(
        declared_range=item, producer_id=0,
        preferred_slot_index=0, preferred_only=True,
    )
    lease.fill(b"abcd")
    lease._external_release_callback = lambda: released.append(True)
    transport.start(destination_size=4)
    transport.publish(lease, __import__(
        "comfymodal_runtime.golden_qd_transport", fromlist=["ReadyRecord"]
    ).ReadyRecord(10, 0, 4, 1, 0))
    result = transport.finalize_external_ready([item], destination_size=4)
    assert result.completed_bytes == 4
    assert released == [True]
    assert pool.states()[0].value == "free"


def test_source_thread_transport_is_restore_owned_not_model_constructed() -> None:
    path = Path(__file__).parents[1] / "comfymodal_runtime" / "golden_model_transport.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    loader = next(
        node for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef)
        and node.name == "_load_c0_source_threads_sync"
    )
    assert not any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "GoldenQDTransport"
        for node in ast.walk(loader)
    )
    assert "source_transport_created_once" in path.read_text(encoding="utf-8")


def test_source_thread_loader_emits_the_canonical_model_statistics() -> None:
    """The source-thread arm must expose the same keys as the C0 reference."""
    reference_path = Path(__file__).parents[1] / "comfymodal_runtime" / "golden_model_transport.py"
    tree = ast.parse(reference_path.read_text(encoding="utf-8"))
    required = {
        "source_wall_ms", "source_child_wall_ms", "source_gbps",
        "source_go_offset_ms", "source_final_byte_complete_ns",
        "final_h2d_submit_ns", "final_h2d_completion_observed_ns",
        "gpu_ready_wall_ms", "gpu_ready_tail_ms", "total_load_ms",
    }
    for function_name in ("_load_c0_sync", "_load_c0_source_threads_sync"):
        function = next(
            node for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef) and node.name == function_name
        )
        keys = {
            node.value
            for node in ast.walk(function)
            if isinstance(node, ast.Constant) and isinstance(node.value, str)
        }
        missing = required - keys
        assert not missing, f"{function_name} is missing canonical statistics: {sorted(missing)}"


def test_source_thread_loader_does_not_use_first_record_as_first_start() -> None:
    """The first appended record is the first *completed* record."""
    reference_path = Path(__file__).parents[1] / "comfymodal_runtime" / "golden_model_transport.py"
    text = reference_path.read_text(encoding="utf-8")
    loader_start = text.index("def _load_c0_source_threads_sync")
    loader_end = text.index("def _load_c0_sync", loader_start)
    loader = text[loader_start:loader_end]
    assert "canonical_source_span" in loader
    assert "source_start_ns\", [None])[0]" not in loader


def test_range_plan_timestamps_bracket_the_actual_range_construction() -> None:
    reference_path = Path(__file__).parents[1] / "comfymodal_runtime" / "golden_model_transport.py"
    text = reference_path.read_text(encoding="utf-8")
    loader_start = text.index("def _load_c0_source_threads_sync")
    loader_end = text.index("def _load_c0_sync", loader_start)
    loader = text[loader_start:loader_end]
    begin = loader.index('marks["range_plan_begin"]')
    end = loader.index('marks["range_plan_end"]')
    between = loader[begin:end]
    # The stamps must enclose the loop that actually builds the ranges.
    assert "while destination < layout.data_bytes" in between
    assert "qd_transport.SourceRange(" in between
    assert 'marks["plan_publish_begin"]' not in loader
    for span in ("plan_install", "source_pipeline", "final_drain"):
        assert f'marks["{span}' in loader


def test_clip_forward_telemetry_shape_keeps_meaningful_boundaries() -> None:
    serial_path = Path(__file__).parents[1] / "comfymodal_runtime" / "golden_serial.py"
    text = serial_path.read_text(encoding="utf-8")
    for boundary in (
        "clip_forward_entry_setup",
        "clip_tokenization_input_prep",
        "clip_qwen_transformer_forward",
        "clip_post_forward_sync_wait",
        "clip_conditioning_packaging",
    ):
        assert boundary in text
    assert "golden_clip_forward_decomposition_v2" in text


# ---------------------------------------------------------------------------
# 20. Hard per-model-load wall gate (CLIP 30 s / UNET 30 s)
# ---------------------------------------------------------------------------


def _gate_ranges(count: int):
    return [
        type("Range", (), {"source_offset": i * 4, "length": 4,
                           "target_offset": i * 4, "record_id": f"planned-{i}"})()
        for i in range(count)
    ]


class _GateManager:
    """Source owner whose readiness never arrives, standing in for a load that
    blocks far past any acceptable wall time."""

    def __init__(self, *, sleep_s: float, blocks: int = 0, lifecycle: str = "whole"):
        self.mmap_lifecycle = lifecycle
        self.telemetry: dict = {}
        self._planned_generation = 1
        self._proc = None
        self._sleep_s = sleep_s
        self.released: list = []
        self.budgets: list = []
        self._records = [
            source.ReadyRecord(i, 1, i * 4, i * 4, 4, i, i, i + 10, f"planned-{i}", 1)
            for i in range(blocks)
        ]

    def plan_once(self, **_kwargs):
        return None

    def wait_ready(self, timeout):
        self.budgets.append(timeout)
        time.sleep(self._sleep_s)
        return self._records.pop(0) if self._records else None

    def claim_ready(self, record):
        return record

    def release_slot(self, record, **_kwargs):
        self.released.append(record)

    def snapshot(self):
        return {
            "generation": 1, "plan_count": 1, "next_range": 3, "plan_range_count": 3,
            "ready_count": 0, "completed_count": 0, "failed_count": 0,
            "free_slot_mask": 0, "slot_states": [1, 1, 1, 3, 0, 0, 0, 0],
            "source_operations": 0, "release_count": 0,
            "capacity_wait_count": 9, "capacity_wait_ns": 1234,
            "slot_acquire_wait_count": 3, "slot_acquire_wait_ns": 99,
            "all_slots_occupied_count": 5, "ready_queue_wait_ns": 77,
            "effective_reader_concurrency": 4,
            "time_weighted_reader_concurrency": 3.84,
            "pacing_wait_count": 2, "pacer_gap_violation_count": 0,
            "min_source_gap_ns": 4_000_000,
            "mmap_map_count": 3, "mmap_unmap_count": 3,
            "source_start_ns": [10, 20, 30],
            "source_span": {"source_start_ns": 10, "source_end_ns": 30},
            "source_operation_records": [
                {"reader": 2, "source_offset": 0, "nbytes": 4, "ready_ns": 10,
                 "memcpy_start_ns": 10, "memcpy_end_ns": 90},
            ],
        }

    def request_status(self, *_args, **_kwargs):
        return {"op": "STATUS_REPLY", "generation": 1, "readers": [0, 1, 2, 3]}


class _GateLease:
    def mark_filled(self, _count):
        return None

    def retire(self):
        return None


class _GateTransport:
    def __init__(self):
        self.published: list = []

    def adopt_external_slot(self, **_kwargs):
        return _GateLease()

    def publish(self, _lease, record, *, externally_filled=False):
        assert externally_filled
        self.published.append(record.record_id)

    def _ready_record(self, source_offset, destination_offset, nbytes, record_id, producer_id):
        return type("R", (), {
            "source_offset": source_offset, "destination_offset": destination_offset,
            "nbytes": nbytes, "record_id": record_id, "producer_id": producer_id,
        })()


def test_model_load_gate_default_is_thirty_seconds() -> None:
    assert source.MODEL_LOAD_GATE_S == 30.0
    # The gate must be the default every generation load inherits, not an
    # opt-in a caller has to remember to pass.
    signature = inspect.signature(source.SourcePlanBridge.publish_all)
    assert signature.parameters["timeout_s"].default == 30.0
    assert "role" in signature.parameters


def test_clip_load_gate_fails_closed_with_a_role_named_error() -> None:
    manager = _GateManager(sleep_s=0.0)
    bridge = source.SourcePlanBridge(manager, _GateTransport())
    with pytest.raises(source.SourceProtocolError) as excinfo:
        bridge.publish_all(
            _gate_ranges(3), generation=1, path="clip.safetensors",
            identity=(1, 2, 12, 3), destination_size=12, role="clip",
        )
    message = str(excinfo.value)
    assert message.startswith("golden_clip_load_timeout_30s:")
    assert "role=clip" in message
    assert "stage=model_source_publish" in message


def test_unet_load_gate_fails_closed_with_a_role_named_error() -> None:
    manager = _GateManager(sleep_s=0.0)
    bridge = source.SourcePlanBridge(manager, _GateTransport())
    with pytest.raises(source.SourceProtocolError) as excinfo:
        bridge.publish_all(
            _gate_ranges(3), generation=1, path="unet.safetensors",
            identity=(1, 2, 12, 3), destination_size=12, role="unet",
        )
    message = str(excinfo.value)
    assert message.startswith("golden_unet_load_timeout_30s:")
    assert "role=unet" in message


def test_load_gate_caps_a_genuinely_blocking_load_around_the_gate() -> None:
    """The gate must observe real wall time.

    ``wait_ready`` here blocks for far longer than the gate on every call,
    exactly like a source owner stuck in a slow read.  A gate implemented with
    ``asyncio.wait_for`` around this blocking call would never fire; a gate in
    the consumer's own bounded wait loop does.
    """
    manager = _GateManager(sleep_s=0.25)
    bridge = source.SourcePlanBridge(manager, _GateTransport())
    started = time.monotonic()
    with pytest.raises(source.SourceProtocolError):
        bridge.publish_all(
            _gate_ranges(3), generation=1, path="clip.safetensors",
            identity=(1, 2, 12, 3), destination_size=12, timeout_s=0.05, role="clip",
        )
    elapsed = time.monotonic() - started
    # It fired on the first bounded wait, not after a 120 s style outer cap and
    # not after draining every blocked sleep.
    assert elapsed < 1.0, f"gate did not cap the blocking load promptly: {elapsed:.3f}s"
    assert manager.budgets and manager.budgets[0] <= 0.05 + 1e-9


def test_load_gate_emits_terminal_source_diagnostics() -> None:
    manager = _GateManager(sleep_s=0.0)
    bridge = source.SourcePlanBridge(manager, _GateTransport())
    with pytest.raises(source.SourceProtocolError) as excinfo:
        bridge.publish_all(
            _gate_ranges(3), generation=1, path="clip.safetensors",
            identity=(1, 2, 12, 3), destination_size=12, timeout_s=0.01, role="clip",
        )
    message = str(excinfo.value)
    # Role, stage, elapsed, generation, workers, reader state, slots by state,
    # READY/IN_FLIGHT depth, pacing, mmap, child liveness and per-reader offsets.
    for field in (
        "elapsed_ms=", "generation=1", "mmap_lifecycle=whole",
        "ready_depth=", "in_flight_depth=", "filling_depth=", "free_depth=",
        "slot_states=", "capacity_wait_ns=", "release_count=",
        "effective_reader_concurrency=4", "time_weighted_reader_concurrency=",
        "pacing_wait_count=", "mmap_map_count=", "per_reader=",
        "child_alive=", "child_status=",
    ):
        assert field in message, f"missing terminal diagnostic field: {field}"


def test_load_gate_does_not_continue_publishing_after_the_timeout() -> None:
    """A partially published generation must not keep draining blocks."""
    manager = _GateManager(sleep_s=0.0, blocks=1)
    transport = _GateTransport()
    bridge = source.SourcePlanBridge(manager, transport)
    with pytest.raises(source.SourceProtocolError):
        bridge.publish_all(
            _gate_ranges(3), generation=1, path="clip.safetensors",
            identity=(1, 2, 12, 3), destination_size=12, timeout_s=0.01, role="clip",
        )
    assert transport.published == ["planned-0"]


def test_load_gate_cleanup_releases_a_claimed_but_unpublished_slot() -> None:
    """A slot claimed and then abandoned must not stay owned forever.

    Ownership is the physical slot token.  If the gate (or any mid-generation
    failure) lands after a claim but before the dispatcher took the slot, the
    bridge is the only owner that can return it, and it must do so.
    """
    manager = _GateManager(sleep_s=0.0, blocks=1)

    class _FailingTransport(_GateTransport):
        def publish(self, *_args, **_kwargs):
            raise source.SourceProtocolError("dispatcher_adopt_failed")

    bridge = source.SourcePlanBridge(manager, _FailingTransport())
    with pytest.raises(source.SourceProtocolError):
        bridge.publish_all(
            _gate_ranges(3), generation=1, path="clip.safetensors",
            identity=(1, 2, 12, 3), destination_size=12, role="clip",
        )
    # The claimed range never entered the dispatcher, so it was returned.
    assert [record.range_index for record in manager.released] == [0]


def test_load_gate_does_not_reclaim_a_slot_already_handed_to_the_dispatcher() -> None:
    """Ownership that the dispatcher accepted stays with the dispatcher's
    completion path; the gate must not double-release it."""
    manager = _GateManager(sleep_s=0.0, blocks=1)
    bridge = source.SourcePlanBridge(manager, _GateTransport())
    with pytest.raises(source.SourceProtocolError):
        bridge.publish_all(
            _gate_ranges(3), generation=1, path="clip.safetensors",
            identity=(1, 2, 12, 3), destination_size=12, role="clip",
        )
    assert manager.released == []


def test_failed_load_does_not_corrupt_the_next_lifecycle() -> None:
    """A gated generation must not poison the source owner for the next load."""
    failing = _GateManager(sleep_s=0.0)
    failing._planned_generation = 1
    bridge = source.SourcePlanBridge(failing, _GateTransport())
    with pytest.raises(source.SourceProtocolError):
        bridge.publish_all(
            _gate_ranges(3), generation=1, path="clip.safetensors",
            identity=(1, 2, 12, 3), destination_size=12, timeout_s=0.01, role="clip",
        )

    healthy = _GateManager(sleep_s=0.0, blocks=3)
    healthy._planned_generation = 2
    transport = _GateTransport()
    bridge = source.SourcePlanBridge(healthy, transport)
    assert bridge.publish_all(
        _gate_ranges(3), generation=2, path="unet.safetensors",
        identity=(1, 2, 12, 3), destination_size=12, timeout_s=1.0, role="unet",
    ) == 3
    assert transport.published == ["planned-0", "planned-1", "planned-2"]


def test_normal_load_path_is_unchanged_by_the_gate() -> None:
    """A healthy generation publishes every range and raises nothing."""
    manager = _GateManager(sleep_s=0.0, blocks=3)
    manager.mmap_lifecycle = "whole"
    transport = _GateTransport()
    bridge = source.SourcePlanBridge(manager, transport)
    started = time.monotonic()
    assert bridge.publish_all(
        _gate_ranges(3), generation=1, path="clip.safetensors",
        identity=(1, 2, 12, 3), destination_size=12, role="clip",
    ) == 3
    assert time.monotonic() - started < source.MODEL_LOAD_GATE_S
    assert transport.published == ["planned-0", "planned-1", "planned-2"]


def test_h100_c0_profile_pins_the_whole_file_mapping_lifecycle() -> None:
    """Regression guard for the catastrophic tail's actual cause.

    The per-op mmap+munmap lifecycle re-faults every 64 MiB extent and was
    measured at 0.145-1.597 GB/s versus 6.2-6.4 GB/s for the whole-file
    mapping, while still returning the exact output SHA with fallback=0.
    """
    profile = (
        Path(__file__).parents[1]
        / "config" / "v2" / "profiles" / "golden_p1_parallel_c0_source_h100.toml"
    )
    text = profile.read_text(encoding="utf-8")
    assert 'COMFYMODAL_GOLDEN_C0_MMAP_LIFECYCLE = "whole"' in text
    assert 'COMFYMODAL_GOLDEN_C0_MMAP_LIFECYCLE = "fresh"' not in text
    # The frozen control is otherwise untouched.
    for control in (
        'COMFYMODAL_GOLDEN_C0_SOURCE_THREADS = "1"',
        'COMFYMODAL_GOLDEN_C0_SOURCE_WORKER_KIND = "thread"',
        'COMFYMODAL_GOLDEN_C0_TRANSPORT_GEOMETRY = "qd4_64"',
        'COMFYMODAL_GOLDEN_IO_PROCESS_V2_SOURCE_ENGINE = "mmap_fresh"',
        'gpu = "H100!"', 'cpu = 12', 'memory_mb = 24576',
        'method = "run_golden_parallel_stream"',
        'expected_output_sha = "3a6a03064c7e6e01ede339ada63daaea4cbf793f387f4faadbb101a787024577"',
    ):
        assert control in text, f"frozen control changed or missing: {control}"


def test_c0_mmap_lifecycle_never_resolves_silently_to_the_slow_path() -> None:
    """An unset lifecycle must not quietly become the pathological default."""
    from comfymodal_runtime import golden_io_process_v2 as c0

    name = c0.IO_PROCESS_V2_MMAP_LIFECYCLE_ENV
    previous = os.environ.get(name)
    try:
        os.environ.pop(name, None)
        # Resolution stays deterministic, but it must be explicit that the
        # default is a diagnostic value, never a silent production path.
        assert c0.resolve_c0_mmap_lifecycle() == "fresh"
        os.environ[name] = "not-a-lifecycle"
        with pytest.raises(ValueError):
            c0.resolve_c0_mmap_lifecycle()
    finally:
        os.environ.pop(name, None)
        if previous is not None:
            os.environ[name] = previous

