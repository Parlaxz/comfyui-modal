"""Split the 64 MiB source copy into its source side and its destination side.

Phase-1 diagnostics proved the pathological copy is CPU-bound inside the
``libc.memmove`` (``wall/cpu`` ~1.07, zero majflt, zero inblock, zero context
switches), and proved that under gVisor those zero counters are
NON-AUTHORITATIVE for ruling out backing-page work.  So the next question is
not "which syscall fixes it" but "which side of the copy is slow".

This module answers that with a 2x2 design over the two halves of the copy:

===========  ==============================  ==============================
arm          source                          destination
===========  ==============================  ==============================
``A``        whole-file MAP_PRIVATE mmap     pinned shared arena (production)
``B``        whole-file MAP_PRIVATE mmap     ordinary anonymous RAM
``C``        ordinary anonymous RAM          pinned shared arena (production)
``D``        ordinary anonymous RAM          ordinary anonymous RAM
===========  ==============================  ==============================

``A`` is the production control.  ``B`` removes the pinned arena, ``C`` removes
the mapped file, ``D`` removes both.  ``A`` pathological with ``B`` healthy
implicates the pinned arena; ``A`` pathological with ``C`` healthy implicates
the mapped source; all four pathological implicates the host.

Fidelity rules this module deliberately holds to:

* the copy kernel is the production one.  ``golden_source_threads.execute_block``
  does the slot claim, the 4 ms pacer, the whole-file mapping address
  arithmetic, the ``libc.memmove`` and the Phase-1 per-copy probe, and this
  module runs it through the production reader loop.  Nothing here re-implements
  the copy with Python slicing or ``bytes`` assignment;
* the geometry is the production geometry.  16 slots of exactly 64 MiB
  (``golden_source_threads.SLOT_COUNT`` / ``SLOT_BYTES``) and four reader threads
  (``READER_COUNT``).  The anonymous arms use the same 1 GiB destination and the
  same 64 MiB block size, so the only variable is *which* memory is on each side;
* the pinned destination is the production destination.  Same POSIX
  ``shared_memory.SharedMemory`` allocation, same ``cudaHostRegister`` with flags
  0, same pre-H2D lifetime.  Anonymous destinations get no registration at all;
* everything anonymous is pre-touched with a native ``memset`` before timing, so
  an anonymous arm cannot be "slow" merely because its pages were not resident;
* source offsets, slot assignment, copy ordinal and reader identity are recorded
  for every copy so slot identity and offset identity stay separable afterwards.

This is an opt-in diagnostic.  With ``COMFYMODAL_GOLDEN_SOURCE_COPY_ISOLATION``
unset it performs no work, allocates nothing, and changes no production
behaviour.
"""

from __future__ import annotations

import ctypes
import dataclasses
import hashlib
import mmap as _mmap
import os
import statistics
import threading
import time
from multiprocessing import shared_memory
from typing import Any, Iterable, Mapping, Sequence

from . import golden_source_threads as gsrc
from .source_copy_probe import SENTINEL, SourceCopyProbe

EXPERIMENT_ENV = "COMFYMODAL_GOLDEN_SOURCE_COPY_ISOLATION"
ARM_ENV = "COMFYMODAL_GOLDEN_SOURCE_COPY_ISOLATION_ARM"
COPIES_ENV = "COMFYMODAL_GOLDEN_SOURCE_COPY_ISOLATION_COPIES"
MODEL_ENV = "COMFYMODAL_GOLDEN_SOURCE_COPY_ISOLATION_MODEL"
ANON_GIB_ENV = "COMFYMODAL_GOLDEN_SOURCE_COPY_ISOLATION_ANON_GIB"

ARMS = ("A", "B", "C", "D")
# 128 timed copies is the floor; 256 is the default because a pathological copy
# is rare (65 of 3040 in the Phase-1 cohort) and a small sample would simply
# miss it.  Copies are split across four readers, so 256 copies is 64 per reader.
DEFAULT_COPIES = 256
MINIMUM_COPIES = 128
MODEL_KEYS = ("unet", "clip", "vae")
# The anonymous arms do not need the model's 12 GiB of distinct source offsets to
# answer the question being asked -- they need *resident anonymous* pages on the
# source side -- and allocating 12 GiB of anonymous RAM next to a 1 GiB pinned
# arena in a 24 GiB container risks an OOM that would destroy the observation.
# The working-set sizes are reported explicitly so the asymmetry is visible.
DEFAULT_ANON_SOURCE_GIB = 4
MINIMUM_ANON_SOURCE_GIB = 1

ARM_LAYOUT: dict[str, dict[str, Any]] = {
    "A": {
        "source": "model_mmap",
        "destination": "pinned_shared_arena",
        "variants": ("concurrent4",),
        "summary": "production control: whole mmap -> pinned shared arena",
    },
    "B": {
        "source": "model_mmap",
        "destination": "anonymous",
        "variants": ("concurrent4",),
        "summary": "source test: whole mmap -> anonymous RAM (no pinned arena)",
    },
    "C": {
        "source": "anonymous",
        "destination": "pinned_shared_arena",
        "variants": ("single", "concurrent4"),
        "summary": "destination test: anonymous RAM -> pinned shared arena",
    },
    "D": {
        "source": "anonymous",
        "destination": "anonymous",
        "variants": ("single", "concurrent4"),
        "summary": "host control: anonymous RAM -> anonymous RAM",
    },
}

VARIANT_READERS = {"single": 1, "concurrent4": gsrc.READER_COUNT}

# Never let a diagnostic wedge a real request: a bounded wall budget per variant.
VARIANT_TIMEOUT_S = 900.0
COPY_TIMEOUT_S = 120.0

_MIB = 1024 * 1024
_GIB = 1024 * 1024 * 1024
# cudaHostRegisterDefault; matches golden_io_process_v2._CUDA_HOST_REGISTER_DEFAULT.
_CUDA_HOST_REGISTER_DEFAULT = 0

_TRUE = {"1", "true", "yes", "on"}


def _env_flag(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in _TRUE


def enabled(value: Any = None) -> bool:
    selected = os.environ.get(EXPERIMENT_ENV) if value is None else value
    return str(selected or "").strip().lower() in _TRUE


def selected_arm(value: Any = None) -> str:
    """Return the explicitly selected arm, failing closed on anything else."""
    selected = os.environ.get(ARM_ENV, "A") if value is None else value
    arm = str(selected or "").strip().upper()
    if arm not in ARMS:
        raise ValueError(f"unsupported_source_copy_isolation_arm:{selected!r}")
    return arm


def resolve_copies(value: Any = None) -> int:
    raw = os.environ.get(COPIES_ENV) if value is None else value
    try:
        copies = int(str(raw).strip() or DEFAULT_COPIES)
    except (TypeError, ValueError):
        return DEFAULT_COPIES
    if copies < MINIMUM_COPIES:
        raise ValueError(f"source_copy_isolation_copies_below_minimum:{copies}")
    return copies


def resolve_model_key(value: Any = None) -> str:
    raw = os.environ.get(MODEL_ENV, "unet") if value is None else value
    key = str(raw or "").strip().lower()
    if key not in MODEL_KEYS:
        raise ValueError(f"unsupported_source_copy_isolation_model:{raw!r}")
    return key


def resolve_anon_source_bytes(value: Any = None) -> int:
    raw = os.environ.get(ANON_GIB_ENV) if value is None else value
    try:
        gib = int(str(raw).strip() or DEFAULT_ANON_SOURCE_GIB)
    except (TypeError, ValueError):
        gib = DEFAULT_ANON_SOURCE_GIB
    if gib < MINIMUM_ANON_SOURCE_GIB:
        raise ValueError(f"source_copy_isolation_anon_gib_below_minimum:{gib}")
    return gib * _GIB


# ── arm description ──────────────────────────────────────────────────────

def arm_layout(arm: str) -> dict[str, Any]:
    key = str(arm or "").strip().upper()
    if key not in ARM_LAYOUT:
        raise ValueError(f"unsupported_source_copy_isolation_arm:{arm!r}")
    return dict(ARM_LAYOUT[key])


# ── memory construction ──────────────────────────────────────────────────

def _anonymous_buffer(size_bytes: int, fill: int = 0xA5) -> tuple[Any, int]:
    """Allocate anonymous RAM, make it resident, and return (buffer, address).

    The ``memset`` is a real native write, not a read, so every page is
    allocated.  A read-only residency check would leave the zero page mapped and
    the arm would then measure page-fault cost rather than copy cost.  The fill
    is a non-zero byte so the write is observable: a caller can read the whole
    range back and prove that every byte -- and therefore every page -- was
    touched before timing began.
    """
    size = int(size_bytes)
    if size <= 0:
        raise ValueError("anonymous_buffer_size_must_be_positive")
    mapping = _mmap.mmap(-1, size)
    view = memoryview(mapping)
    address = int(ctypes.addressof(ctypes.c_char.from_buffer(view)))
    ctypes.memset(address, int(fill), size)
    return view, address


def _release_anonymous(buffer: Any) -> None:
    try:
        buffer.release()
    except Exception:
        pass


class PinnedSharedArena:
    """The production destination: POSIX shared memory, cudaHostRegister'ed once.

    Identical construction to ``golden_io_process_v2.SharedArenaRing.ensure``:
    ``shared_memory.SharedMemory(create=True)`` sized to the full 16 x 64 MiB
    arena, then a single ``cudaHostRegister`` over the whole mapping with flags
    0.  No prefault memset is applied, because production explicitly rejected
    prefault (registration is the population step) and this arm exists to
    reproduce production, not to improve on it.
    """

    def __init__(self) -> None:
        self.shm = shared_memory.SharedMemory(create=True, size=gsrc.ARENA_BYTES)
        self.buffer = self.shm.buf
        self.address = int(ctypes.addressof(ctypes.c_char.from_buffer(self.buffer)))
        self.register_rc: int | None = None
        self.register_ms: float | None = None
        self.notes: list[str] = []

    def register(self) -> "PinnedSharedArena":
        import torch  # noqa: PLC0415 - imported only when an arm needs CUDA

        cudart = torch.cuda.cudart()
        handle = getattr(cudart, "cudaHostRegister", None)
        if not callable(handle):
            raise RuntimeError("cudaHostRegister_unavailable")
        started = time.perf_counter()
        self.register_rc = int(handle(self.address, gsrc.ARENA_BYTES, _CUDA_HOST_REGISTER_DEFAULT))
        self.register_ms = round((time.perf_counter() - started) * 1000.0, 4)
        if self.register_rc != 0:
            raise RuntimeError(f"cudaHostRegister_failed:{self.register_rc}")
        self.notes.append("registered_like_production")
        return self

    def evidence(self) -> dict[str, Any]:
        return {
            "kind": "pinned_shared_arena",
            "backing": "posix_shared_memory",
            "name": str(self.shm.name),
            "bytes": int(gsrc.ARENA_BYTES),
            "address": int(self.address),
            "cuda_host_registered": self.register_rc == 0,
            "cuda_host_register_flags": _CUDA_HOST_REGISTER_DEFAULT,
            "cuda_host_register_ms": self.register_ms,
            "prefault_applied": False,
            "notes": list(self.notes),
        }

    def close(self) -> None:
        try:
            self.buffer.release()
        except Exception:
            pass
        try:
            self.shm.close()
            self.shm.unlink()
        except Exception:
            pass


def _anonymous_destination_evidence(buffer: Any, address: int) -> dict[str, Any]:
    """Evidence for the unregistered destination.

    The mirror image of :meth:`PinnedSharedArena.evidence`: same 1 GiB size and
    same 16 x 64 MiB slot geometry, no shared-memory object, no
    ``cudaHostRegister``, and residency established by an explicit native write
    instead of by registration.
    """
    return {
        "kind": "anonymous",
        "backing": "anonymous_mmap",
        "bytes": int(gsrc.ARENA_BYTES),
        "address": int(address),
        "cuda_host_registered": False,
        "prefault_applied": True,
        "notes": ["native_memset_pretouch"],
    }


def _residency(address: int, length: int, *, max_pages: int = 65536) -> float | None:
    """Best-effort resident fraction.  Never faulting, never authoritative."""
    if address <= 0 or length <= 0:
        return None
    try:
        page = int(os.sysconf("SC_PAGE_SIZE"))
        libc = ctypes.CDLL(None, use_errno=True)
        libc.mincore.restype = ctypes.c_int
        libc.mincore.argtypes = [
            ctypes.c_void_p, ctypes.c_size_t, ctypes.POINTER(ctypes.c_ubyte),
        ]
        start = address & ~(page - 1)
        end = (address + length + page - 1) & ~(page - 1)
        total = (end - start) // page
        if total <= 0:
            return None
        stride = max(1, total // max_pages)
        sampled = list(range(0, total, stride))[:max_pages]
        resident = 0
        for index in sampled:
            vector = (ctypes.c_ubyte * 1)()
            if libc.mincore(
                ctypes.c_void_p(start + index * page), ctypes.c_size_t(page), vector
            ) != 0:
                return None
            resident += 1 if vector[0] & 1 else 0
        return round(resident / len(sampled), 6)
    except Exception:
        return None


# ── plan construction ────────────────────────────────────────────────────

def file_block_ranges(size_bytes: int, *, block_bytes: int = gsrc.SLOT_BYTES) -> list[tuple[int, int, int, None]]:
    """The 64 MiB block list production installs for one model generation."""
    total = int(size_bytes)
    if total <= 0:
        raise ValueError("empty_source_file")
    ranges: list[tuple[int, int, int, None]] = []
    offset = 0
    while offset < total:
        length = min(int(block_bytes), total - offset)
        ranges.append((offset, length, offset, None))
        offset += length
    return ranges


def repeated_plan_ranges(
    size_bytes: int, copies: int, *, block_bytes: int = gsrc.SLOT_BYTES
) -> tuple[tuple[int, int, int, None], ...]:
    """Extend the file block list until it holds exactly ``copies`` ranges.

    A 12 GiB UNET is only 184 blocks, so a 256-copy arm needs the block list
    walked more than once.  The *source* offsets therefore repeat, which is
    exactly what STEP 10 asks to be able to correlate on, and the destination
    offsets stay gap-free so the list still describes one contiguous logical
    destination of ``copies * block_bytes`` bytes.
    """
    blocks = file_block_ranges(size_bytes, block_bytes=block_bytes)
    if not blocks:
        raise ValueError("empty_source_file")
    wanted = int(copies)
    if wanted <= 0:
        raise ValueError("copy_count_must_be_positive")
    plan: list[tuple[int, int, int, None]] = []
    cursor = 0
    while len(plan) < wanted:
        for source_offset, length, _destination_offset, record_id in blocks:
            if len(plan) >= wanted:
                break
            plan.append((source_offset, length, cursor, record_id))
            cursor += length
    return tuple(plan)


def _plan(
    *,
    generation: int,
    path: str,
    identity: Sequence[int],
    ranges: Sequence[tuple[int, int, int, int | None]],
    map_address: int,
    map_length: int,
) -> gsrc._ChildPlan:
    """Assemble the production plan dataclass for one experiment generation.

    ``mmap_lifecycle`` is always ``"whole"`` because that is the production
    lifecycle on this profile: one whole-file ``MAP_PRIVATE`` mapping, opened
    once per generation, with no per-block ``mmap``/``munmap`` syscall.  The
    experiment never exercises the ``fresh`` lifecycle, so a ``fresh`` result can
    never be confused with a production one.
    """
    return gsrc._ChildPlan(
        generation=int(generation),
        path=str(path),
        identity=tuple(int(value) for value in identity),
        destination_size=sum(int(item[1]) for item in ranges),
        mmap_lifecycle="whole",
        ranges=tuple(tuple(item) for item in ranges),
        fd=-1,
        map_address=int(map_address),
        map_length=int(map_length),
        plan_install_ns=time.monotonic_ns(),
    )


class _InProcessLock:
    """The control lock, minus the ``flock``.

    ``_FileLock`` is POSIX-``flock`` only, and the experiment runs in the same
    address space as its readers, so a plain mutex is the whole requirement.
    Slot state transitions are still single-writer and still happen outside the
    copy, exactly as in production.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()

    def __enter__(self) -> "_InProcessLock":
        self._lock.acquire()
        return self

    def __exit__(self, *_args: Any) -> None:
        self._lock.release()


class _Failure:
    """Reader-side failure sink: records the message and marks the control block.

    Mirrors ``_child_main.fail_control`` so a failing reader is visible in the
    shared header rather than only in this process's memory.
    """

    def __init__(self, lock: Any, control: Any) -> None:
        self._lock = lock
        self._control = control
        self.messages: list[str] = []

    def __call__(self, message: str) -> None:
        self.messages.append(str(message))
        try:
            with self._lock:
                values = list(gsrc._read_header(self._control))
                values[10] = int(values[10]) + 1
                gsrc._write_header_all(self._control, values)
                gsrc._write_error(self._control, str(message))
        except BaseException:
            pass


def _release_ready_slot(control: Any, lock: Any, slot_index: int, generation: int) -> bool:
    """Return one READY slot the way the H2D dispatcher does after completion.

    The two production transitions (``READY -> IN_FLIGHT -> FREE``) are performed
    in one lock acquisition because there is no real H2D here; the state machine
    and the free-mask/counter bookkeeping are the production ones.
    """
    with lock:
        header = gsrc._read_header(control)
        current = gsrc._slot(control, int(slot_index))
        if int(current[0]) != gsrc.READY or int(current[1]) != int(generation):
            return False
        values = list(header)
        gsrc._put_slot(control, int(slot_index), (
            gsrc.IN_FLIGHT, current[1], current[2], current[3], current[4],
            current[5], current[6], 0,
        ))
        values[8] = max(0, values[8] - 1)
        values[11] = int(values[11]) & ~(1 << int(slot_index))
        gsrc._write_header_all(control, values)
        # Completion proven: the slot becomes FREE and capacity is announced.
        gsrc._put_slot(control, int(slot_index), (
            gsrc.FREE, current[1], current[2], current[3], current[4],
            current[5], current[6], time.monotonic_ns(),
        ))
        values[9] += 1
        values[11] = int(values[11]) | (1 << int(slot_index))
        gsrc._write_header_all(control, values)
        gsrc._bump_counter(control, 5)
    return True


def _read_operations(control: Any, lock: Any, generation: int) -> list[dict[str, Any]]:
    with lock:
        counters = gsrc.COUNTERS.unpack_from(control, gsrc.COUNTER_OFFSET)
    records: list[dict[str, Any]] = []
    for index in range(min(int(counters[6]), gsrc.MAX_OPS)):
        raw = gsrc.OP.unpack_from(control, gsrc.OP_OFFSET + index * gsrc.OP.size)
        record: dict[str, Any] = dict(zip(gsrc.OP_FIELDS, raw))
        if int(record["generation"]) != int(generation):
            continue
        records.append(record)
    return records


def _run_variant(
    *,
    variant: str,
    plan: gsrc._ChildPlan,
    arena_buffer: Any,
    reader_count: int,
    copies: int,
) -> dict[str, Any]:
    """Run one arm variant through the production reader loop and copy kernel."""
    readers = int(reader_count)
    if readers < 1:
        raise ValueError("reader_count_must_be_positive")

    control = gsrc.new_control_buffer()
    lock = _InProcessLock()

    failure = _Failure(lock, control)
    fatal: list[str] = []
    stop = threading.Event()
    capacity = threading.Semaphore(0)
    pacer = gsrc.GlobalSourcePacer()
    ready_queue: list[tuple[int, int]] = []
    ready_lock = threading.Lock()
    ready_signal = threading.Event()
    holder: dict[str, Any] = {"plan": plan}

    def emit(message: Mapping[str, Any]) -> None:
        if message.get("op") != "READY_BLOCK":
            return
        with ready_lock:
            ready_queue.append((int(message["slot_index"]), int(message["generation"])))
        ready_signal.set()

    def wake(timeout_s: float) -> bool:
        return bool(capacity.acquire(timeout=max(0.0, float(timeout_s))))

    def current_plan() -> Any:
        return holder["plan"]

    def adopt_shared_plan() -> Any:
        return holder["plan"]

    with lock:
        gsrc.install_generation_header(control, int(plan.generation), plan)

    threads = [
        threading.Thread(
            target=gsrc._run_reader_loop,
            args=(index,),
            kwargs={
                "arena_buf": arena_buffer,
                "control_buf": control,
                "lock": lock,
                "pacer": pacer,
                "plan_getter": current_plan,
                "refresh_plan": adopt_shared_plan,
                "wake": wake,
                "stop": stop,
                "fatal": fatal,
                "fail_control": failure,
                "emit": emit,
                "page_size": gsrc._PAGE_SIZE,
            },
            name=f"src-iso-{variant}-{index}",
            daemon=True,
        )
        for index in range(readers)
    ]
    started_ns = time.monotonic_ns()
    for thread in threads:
        thread.start()

    published = 0
    deadline = time.monotonic() + VARIANT_TIMEOUT_S
    timed_out = False
    try:
        while published < int(copies):
            if fatal or failure.messages:
                break
            if time.monotonic() > deadline:
                timed_out = True
                break
            ready_signal.wait(timeout=0.25)
            ready_signal.clear()
            with ready_lock:
                pending, ready_queue[:] = list(ready_queue), []
            for slot_index, generation in pending:
                if _release_ready_slot(control, lock, slot_index, generation):
                    published += 1
                    for _ in range(readers):
                        capacity.release()
                if published >= int(copies):
                    break
    finally:
        stop.set()
        for _ in range(readers * 2 + 2):
            capacity.release()
        for thread in threads:
            thread.join(timeout=30.0)
    ended_ns = time.monotonic_ns()

    records = _read_operations(control, lock, int(plan.generation))
    quiescent = False
    try:
        with lock:
            quiescent = int(gsrc._read_header(control)[11]) == gsrc.FREE_MASK
    except BaseException:
        quiescent = False
    return {
        "variant": str(variant),
        "reader_count": readers,
        "requested_copies": int(copies),
        "published_copies": int(published),
        "recorded_copies": len(records),
        "started_monotonic_ns": started_ns,
        "ended_monotonic_ns": ended_ns,
        "wall_ms": (ended_ns - started_ns) / 1e6,
        "timed_out": bool(timed_out),
        "fatal": list(fatal),
        "failure_messages": list(failure.messages),
        "slots_quiescent": bool(quiescent),
        "pacer_gap_ns": int(gsrc.PACER_GAP_NS),
        "records": records,
    }


# ── per-copy projection ──────────────────────────────────────────────────

def project_copy(record: Mapping[str, Any]) -> dict[str, Any]:
    """Turn one raw operation record into the reported per-copy evidence row."""
    wall_ns = int(record.get("copy_wall_ns") or 0)
    before = int(record.get("thread_cpu_ns_before", SENTINEL))
    after = int(record.get("thread_cpu_ns_after", SENTINEL))
    if before == SENTINEL or after == SENTINEL or after < before:
        cpu_ns = None
    else:
        cpu_ns = after - before
    wall_ms = wall_ns / 1e6
    cpu_ms = None if cpu_ns is None else cpu_ns / 1e6
    ratio = None
    if cpu_ns:
        ratio = wall_ns / float(cpu_ns)
    slot = int(record.get("slot_index", -1))
    # An out-of-range slot has no byte offset in the arena.  Reporting
    # slot * SLOT_BYTES anyway would invent an address that does not exist and
    # would silently corrupt any slot-identity correlation built on top of it.
    slot_offset = slot * gsrc.SLOT_BYTES if 0 <= slot < gsrc.SLOT_COUNT else None
    return {
        "reader": int(record.get("reader_id", -1)),
        "thread": int(record.get("thread_id", -1)),
        "copy_ordinal": int(record.get("ordinal", -1)),
        "source_offset": int(record.get("source_offset", -1)),
        "nbytes": int(record.get("nbytes", 0)),
        "dest_slot": slot,
        "dest_byte_offset": slot_offset,
        "wall_ms": round(wall_ms, 4),
        "thread_cpu_ms": None if cpu_ms is None else round(cpu_ms, 4),
        "wall_cpu_ratio": None if ratio is None else round(ratio, 4),
        "minflt_delta": _delta(record.get("minflt_delta")),
        "majflt_delta": _delta(record.get("majflt_delta")),
        "inblock_delta": _delta(record.get("inblock_delta")),
        "nvcsw_delta": _delta(record.get("nvcsw_delta")),
        "nivcsw_delta": _delta(record.get("nivcsw_delta")),
        "start_cpu": _delta(record.get("start_cpu")),
        "end_cpu": _delta(record.get("end_cpu")),
        "memcpy_start_ns": int(record.get("memcpy_start_ns") or 0),
    }


def _delta(value: Any) -> int | None:
    number = int(value)
    return None if number == SENTINEL else number


# ── statistics ───────────────────────────────────────────────────────────

def _percentile(values: Sequence[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = fraction * (len(ordered) - 1)
    low = int(position)
    high = min(low + 1, len(ordered) - 1)
    weight = position - low
    return ordered[low] * (1.0 - weight) + ordered[high] * weight


def describe(values: Iterable[Any]) -> dict[str, Any]:
    """min/p50/p90/p95/p99/max/mean/sd/cv for one measured series."""
    numbers = [float(value) for value in values if value is not None]
    if not numbers:
        return {"count": 0, "min": None, "p50": None, "p90": None, "p95": None,
                "p99": None, "max": None, "mean": None, "sd": None, "cv": None}
    mean = statistics.fmean(numbers)
    sd = statistics.stdev(numbers) if len(numbers) > 1 else 0.0
    return {
        "count": len(numbers),
        "min": round(min(numbers), 4),
        "p50": round(_percentile(numbers, 0.50) or 0.0, 4),
        "p90": round(_percentile(numbers, 0.90) or 0.0, 4),
        "p95": round(_percentile(numbers, 0.95) or 0.0, 4),
        "p99": round(_percentile(numbers, 0.99) or 0.0, 4),
        "max": round(max(numbers), 4),
        "mean": round(mean, 4),
        "sd": round(sd, 4),
        "cv": round(sd / mean, 6) if mean else None,
    }


STALL_THRESHOLDS_MS = (100, 250, 500, 1000)


def summarize_copies(copies: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Distribution, threshold counts and the twenty slowest copies."""
    wall = [item.get("wall_ms") for item in copies]
    cpu = [item.get("thread_cpu_ms") for item in copies]
    ratio = [item.get("wall_cpu_ratio") for item in copies]
    slowest = sorted(
        (dict(item) for item in copies),
        key=lambda item: float(item.get("wall_ms") or 0.0),
        reverse=True,
    )[:20]
    return {
        "count": len(copies),
        "wall_ms": describe(wall),
        "thread_cpu_ms": describe(cpu),
        "wall_cpu_ratio": describe(ratio),
        "over_thresholds": {
            f">{threshold}ms": sum(
                1 for item in copies
                if float(item.get("wall_ms") or 0.0) > float(threshold)
            )
            for threshold in STALL_THRESHOLDS_MS
        },
        "slowest": slowest,
        "distinct_source_offsets": len({item.get("source_offset") for item in copies}),
        "distinct_dest_slots": len({item.get("dest_slot") for item in copies}),
        "distinct_readers": len({item.get("reader") for item in copies}),
    }


# ── runtime identity ─────────────────────────────────────────────────────

_ENV_IDENTITY_KEYS = (
    "COMFYMODAL_V2_APP_NAME",
    "COMFYMODAL_V2_GPU",
    "COMFYMODAL_V2_MEMORY_MB",
    "COMFYMODAL_GOLDEN_C0_MMAP_LIFECYCLE",
    "COMFYMODAL_GOLDEN_C0_SOURCE_WORKER_KIND",
    "COMFYMODAL_GOLDEN_SOURCE_COPY_PROBE",
    EXPERIMENT_ENV,
    ARM_ENV,
    COPIES_ENV,
    MODEL_ENV,
    ANON_GIB_ENV,
    "MODAL_ENVIRONMENT",
    "MODAL_CLOUD_PROVIDER",
    "MODAL_REGION_ID",
    "MODAL_WORKSPACE_ID",
)


def runtime_identity() -> dict[str, Any]:
    """Deployment/request identity plus a hash of this module's own source."""
    identity: dict[str, Any] = {
        "env": {key: os.environ.get(key) for key in _ENV_IDENTITY_KEYS},
        "region": "reported_only" if os.environ.get("MODAL_REGION_ID") else "unavailable",
        "pid": os.getpid(),
    }
    try:
        with open(os.path.abspath(__file__), "rb") as handle:
            identity["module_sha256"] = hashlib.sha256(handle.read()).hexdigest()
    except BaseException:
        identity["module_sha256"] = None
    return identity


def host_facts(arena_name: str | None = None) -> dict[str, Any]:
    """Best-effort host placement.  Unavailable fields stay None, never inferred."""
    try:
        from .source_latency_telemetry import collect_placement_telemetry

        placement: Any = collect_placement_telemetry(
            arena_name=arena_name, arena_bytes=gsrc.ARENA_BYTES
        )
    except BaseException as exc:
        placement = {"status": "error", "error": f"{type(exc).__name__}: {exc}"}
    return {
        "placement": placement,
        "cpu_count": os.cpu_count(),
        "cpu_affinity_count": _affinity_count(),
        "loadavg": _loadavg(),
        "numa": "not_inferred",
    }


def _affinity_count() -> int | None:
    getter = getattr(os, "sched_getaffinity", None)
    if not callable(getter):
        return None
    try:
        return len(getter(0))
    except Exception:
        return None


def _loadavg() -> list[float] | None:
    try:
        return [round(value, 4) for value in os.getloadavg()]
    except Exception:
        return None


# ── arm runner ───────────────────────────────────────────────────────────

def _model_mmap_source(path: str, copies: int) -> dict[str, Any]:
    """Establish the production whole-file mapping through the production code.

    ``gsrc.build_plan(open_source=True)`` is what opens the descriptor and
    establishes the single ``MAP_PRIVATE`` whole-file mapping in production, so
    the experiment calls it rather than opening its own mapping.  Only the range
    list is then extended, via ``dataclasses.replace``, to hold exactly ``copies``
    ranges; the descriptor, mapping address and mapping length are the ones
    production would have used.
    """
    stat = os.stat(path)
    identity = (int(stat.st_dev), int(stat.st_ino), int(stat.st_size), int(stat.st_mtime_ns))
    block_ranges = file_block_ranges(stat.st_size)
    message = {
        "generation": 1,
        "path": os.path.abspath(path),
        "identity": list(identity),
        "destination_size": int(stat.st_size),
        "mmap_lifecycle": "whole",
        "ranges": [
            {
                "source_offset": item[0], "length": item[1],
                "destination_offset": item[2], "record_id": item[3],
            }
            for item in block_ranges
        ],
    }
    base = gsrc.build_plan(message, open_source=True)
    if not base.map_address:
        raise RuntimeError("source_copy_isolation_whole_mapping_absent")
    extended = repeated_plan_ranges(int(stat.st_size), copies)
    plan = dataclasses.replace(
        base,
        ranges=extended,
        destination_size=sum(int(item[1]) for item in extended),
    )
    return {
        "kind": "model_mmap",
        "path": os.path.abspath(path),
        "file_bytes": int(stat.st_size),
        "distinct_blocks": len(block_ranges),
        "map_address": int(base.map_address),
        "map_length": int(base.map_length),
        "mmap_lifecycle": "whole",
        "fd": int(base.fd),
        "plan": plan,
        "residency_first_block": _residency(plan.map_address, min(gsrc.SLOT_BYTES, plan.map_length)),
        "notes": [
            "mapping_established_by_golden_source_threads.build_plan",
            "range_list_extended_to_reach_copy_count",
        ],
    }


def _anonymous_source(copies: int, source_bytes: int) -> dict[str, Any]:
    buffer, address = _anonymous_buffer(int(source_bytes))
    blocks = max(1, int(source_bytes) // gsrc.SLOT_BYTES)
    ranges = []
    cursor = 0
    while len(ranges) < int(copies):
        for index in range(blocks):
            if len(ranges) >= int(copies):
                break
            source_offset = index * gsrc.SLOT_BYTES
            ranges.append((source_offset, gsrc.SLOT_BYTES, cursor, None))
            cursor += gsrc.SLOT_BYTES
    plan = _plan(
        generation=1,
        path="<anonymous-experiment-source>",
        identity=(0, 0, int(source_bytes), 0),
        ranges=ranges,
        map_address=address,
        map_length=int(source_bytes),
    )
    return {
        "kind": "anonymous",
        "source_bytes": int(source_bytes),
        "distinct_blocks": blocks,
        "map_address": int(address),
        "map_length": int(source_bytes),
        "mmap_lifecycle": "whole",
        "plan": plan,
        "residency_first_block": _residency(address, min(gsrc.SLOT_BYTES, int(source_bytes))),
        "buffer": buffer,
        "notes": ["native_memset_pretouch", "no_file_backing"],
    }


def run_arm(
    arm: str,
    *,
    model_paths: Mapping[str, str],
    copies: int | None = None,
    model_key: str | None = None,
    anon_source_bytes: int | None = None,
) -> dict[str, Any]:
    """Run exactly one arm and return its complete, self-describing evidence."""
    layout = arm_layout(arm)
    arm_name = str(arm).strip().upper()
    key = resolve_model_key(model_key)
    wanted_copies = resolve_copies(copies)
    gsrc._init_native()
    # The per-copy probe is the Phase-1 measurement, taken around the same
    # native memmove, so the arms are directly comparable with the Phase-1
    # cohort.  Enabled explicitly rather than inherited from the environment.
    gsrc._PROBE = SourceCopyProbe(enabled=True)

    report: dict[str, Any] = {
        "experiment": "source_copy_isolation",
        "arm": arm_name,
        "arm_layout": layout,
        "model_key": key,
        "requested_copies": wanted_copies,
        "geometry": {
            "slot_count": gsrc.SLOT_COUNT,
            "slot_bytes": gsrc.SLOT_BYTES,
            "arena_bytes": gsrc.ARENA_BYTES,
            "production_reader_count": gsrc.READER_COUNT,
            "pacer_gap_ns": gsrc.PACER_GAP_NS,
            "memmove": "libc.memmove via golden_source_threads._MAPPER",
            "copy_kernel": "golden_source_threads.execute_block",
            "reader_loop": "golden_source_threads._run_reader_loop",
            "probe": "comfymodal_runtime.source_copy_probe.SourceCopyProbe(enabled=True)",
            "mincore_pretouch_probe": "best_effort_only",
        },
        "identity": runtime_identity(),
        "status": "error",
        "variants": [],
    }

    source_path = str(model_paths.get(key) or "")
    if not source_path:
        report["error"] = f"model_path_absent:{key}"
        return report
    if not os.path.isfile(source_path):
        report["error"] = f"model_file_absent:{source_path}"
        return report

    source_buffer: Any = None
    source: dict[str, Any] | None = None
    arena: PinnedSharedArena | None = None
    destination_buffer: Any = None
    destination_address = 0
    try:
        if layout["source"] == "model_mmap":
            source = _model_mmap_source(source_path, wanted_copies)
        else:
            source = _anonymous_source(
                wanted_copies, resolve_anon_source_bytes(anon_source_bytes)
            )
            source_buffer = source.pop("buffer")

        if layout["destination"] == "pinned_shared_arena":
            arena = PinnedSharedArena().register()
            destination_buffer = arena.buffer
            destination_address = arena.address
            destination = arena.evidence()
        else:
            destination_buffer, destination_address = _anonymous_buffer(gsrc.ARENA_BYTES)
            destination = _anonymous_destination_evidence(
                destination_buffer, destination_address
            )

        source_evidence = {key: value for key, value in source.items() if key != "plan"}
        source_evidence["residency_arena_fraction"] = _residency(
            destination_address, gsrc.ARENA_BYTES
        )
        report["source"] = source_evidence
        report["destination"] = destination
        report["host"] = host_facts(
            arena.shm.name if arena is not None else None
        )
        report["pinned_register_used"] = arena is not None

        plan = source["plan"]
        completed = 0
        for variant in layout["variants"]:
            variant_result = _run_variant(
                variant=variant,
                plan=dataclasses.replace(plan),
                arena_buffer=destination_buffer,
                reader_count=VARIANT_READERS[variant],
                copies=wanted_copies,
            )
            copies_rows = [project_copy(item) for item in variant_result.pop("records")]
            variant_result["copies"] = copies_rows
            variant_result["summary"] = summarize_copies(copies_rows)
            variant_result["complete"] = bool(
                variant_result["recorded_copies"] >= wanted_copies
                and not variant_result["timed_out"]
                and not variant_result["failure_messages"]
                and not variant_result["fatal"]
                and variant_result["slots_quiescent"]
            )
            completed += 1 if variant_result["complete"] else 0
            report["variants"].append(variant_result)
        report["variants_expected"] = len(layout["variants"])
        report["variants_complete"] = completed
        report["status"] = "ok" if completed == len(layout["variants"]) else "incomplete"
    except BaseException as exc:
        report["error"] = f"{type(exc).__name__}: {exc}"[:600]
        report["status"] = "error"
    finally:
        gsrc.retire_plan(source.get("plan") if isinstance(source, dict) else None)
        if source_buffer is not None:
            _release_anonymous(source_buffer)
        if arena is not None:
            arena.close()
        elif destination_buffer is not None:
            _release_anonymous(destination_buffer)
    return report


def run_from_session(session: Any) -> dict[str, Any]:
    """Hook entry: resolve the arm from the environment and run it once."""
    if not enabled():
        return {"status": "disabled"}
    model_paths = dict(getattr(session, "model_paths", {}) or {})
    arm = selected_arm()
    try:
        report = run_arm(arm, model_paths=model_paths)
    except BaseException as exc:  # noqa: BLE001 - a diagnostic never fails a request
        report = {
            "experiment": "source_copy_isolation",
            "arm": arm,
            "status": "error",
            "error": f"{type(exc).__name__}: {exc}"[:600],
            "identity": runtime_identity(),
        }
    print(
        "[v2.source_copy_isolation] "
        f"arm={report.get('arm')} status={report.get('status')} "
        + ", ".join(
            f"{item.get('variant')}:{item.get('summary', {}).get('wall_ms', {}).get('p50')}"
            f"/{item.get('summary', {}).get('wall_ms', {}).get('max')}"
            for item in report.get("variants") or []
        ),
        flush=True,
    )
    return report


__all__ = [
    "ANON_GIB_ENV",
    "ARM_ENV",
    "ARMS",
    "ARM_LAYOUT",
    "COPIES_ENV",
    "DEFAULT_COPIES",
    "EXPERIMENT_ENV",
    "MODEL_ENV",
    "MODEL_KEYS",
    "STALL_THRESHOLDS_MS",
    "VARIANT_READERS",
    "PinnedSharedArena",
    "arm_layout",
    "describe",
    "enabled",
    "file_block_ranges",
    "host_facts",
    "project_copy",
    "repeated_plan_ranges",
    "resolve_anon_source_bytes",
    "resolve_copies",
    "resolve_model_key",
    "run_arm",
    "run_from_session",
    "runtime_identity",
    "selected_arm",
    "summarize_copies",
]