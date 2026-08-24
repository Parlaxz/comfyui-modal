"""Golden QD4 loader engine — one generic engine for CLIP, UNET, and VAE.

Design invariants (R41):

1. DECOUPLED PLANES.  Source workers and the H2D transfer plane are fully
   decoupled.  A source worker NEVER waits on a CUDA/copy completion event.
   The only legitimate blocking point for a source worker is acquisition of
   a bounded staging slot, which is classified as H2D backpressure and
   measured.  This is the structural fix for the historical failure mode
   where two-slot-per-worker CUDA-event coupling collapsed steady-state
   source queue depth even though peak outstanding reached 4.

2. BOUNDED STAGING.  A finite pinned staging ring (default 8 slots x 32 MiB
   = 256 MiB).  No whole-model pinning, no unbounded queues.

3. OCCUPANCY OVER PEAK.  Telemetry records time-weighted occupancy:
   fraction of wall time at target QD, per-reason below-QD time, free-slot
   minimums, completed-waiting-for-H2D depth, backpressure totals, source
   latency distribution, steady-state GB/s.  ``observed_max_outstanding``
   alone is explicitly insufficient.

4. TRANSACTIONAL / FAIL-CLOSED.  Any worker exception, short read,
   coverage mismatch, or bind validation failure aborts the load, releases
   all resources, and raises a GoldenQDFailure subclass with telemetry
   attached.  Callers classify DEGRADED/FAILED; fallback can never be
   ACCEPTED_NOMINAL (see pipeline.final_status).

5. ROLE GENERICITY.  The engine consumes a RoleManifest (path + layout +
   static QDRangePlan) and a DestinationPlan (contiguous GPU buffer or
   parameter-copy targets).  CLIP/UNET/VAE differ only by manifest and
   destination strategy — never by transport implementation.
"""

from __future__ import annotations

import hashlib
import json
import os
import struct
import sys
import threading
import time
from collections import deque
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

try:  # torch is optional at import time so contracts-only consumers stay light
    import torch
except Exception:  # pragma: no cover - exercised only without torch
    torch = None

from .contracts import (
    BindError,
    BlockPlan,
    CoverageReconciliationError,
    DestinationPlan,
    GoldenQDFailure,
    GoldenQDTelemetry,
    LedgerEventSink,
    LoadResult,
    ModelRole,
    PrepareCommitIdentityError,
    PreparedSource,
    QDDropReason,
    QDRangePlan,
    RoleManifest,
    SafetensorsLayout,
    ShortReadError,
    SourceReadError,
    TensorMapEntry,
    TransferBackend,
    WorkerCrashedError,
)

__all__ = [
    "QD4EngineConfig",
    "parse_safetensors_header",
    "CudaTransferBackend",
    "CpuCopyBackend",
    "GoldenQD4Loader",
]


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class QD4EngineConfig:
    queue_depth: int = 4
    staging_slots: int = 8
    occupancy_sample_ms: float = 1.0
    enable_occupancy_sampler: bool = True
    slot_wait_timeout_s: float = 120.0
    overall_timeout_s: float = 600.0
    #: Optional external gate consulted by the occupancy sampler when
    #: classifying below-QD samples.  When present and it returns False,
    #: the sample is attributed to SCHEDULER_BLOCKED instead of UNEXPLAINED.
    claim_gate: Optional[Callable[[], bool]] = None

    def __post_init__(self) -> None:
        if self.queue_depth < 1:
            raise ValueError("queue_depth must be >= 1")
        if self.staging_slots < self.queue_depth * 2:
            raise ValueError("staging_slots must be >= queue_depth*2 (bounded ring headroom)")
        if self.occupancy_sample_ms <= 0:
            raise ValueError("occupancy_sample_ms must be positive")


# ---------------------------------------------------------------------------
# Static layout parsing (snapshot-resident immutable metadata builder)
# ---------------------------------------------------------------------------


def parse_safetensors_header(path: str) -> SafetensorsLayout:
    """Parse a safetensors file into an immutable SafetensorsLayout."""
    with open(path, "rb") as fh:
        header_len = struct.unpack("<Q", fh.read(8))[0]
        header_json = fh.read(header_len)
    header = json.loads(header_json.decode("utf-8"))
    data_start = 8 + header_len
    file_bytes = os.path.getsize(path)
    entries: List[TensorMapEntry] = []
    for name, meta in header.items():
        if name == "__metadata__":
            continue
        begin, end = meta["data_offsets"]
        entries.append(
            TensorMapEntry(
                name=name,
                dtype=str(meta["dtype"]),
                shape=tuple(int(s) for s in meta["shape"]),
                abs_start=data_start + int(begin),
                abs_end=data_start + int(end),
            )
        )
    entries.sort(key=lambda e: e.abs_start)
    return SafetensorsLayout(
        header_bytes=header_len,
        data_start=data_start,
        file_bytes=file_bytes,
        tensor_map=tuple(entries),
    )


def _proc_io_snapshot() -> Dict[str, Any]:
    """Snapshot /proc/self/io read counters (Linux only; guarded, Windows-safe).

    Returns {"rchar_bytes": int, "read_bytes": int, "method": "proc_io"},
    or zeros with method="unavailable" when /proc is absent or unreadable.
    """
    try:
        counters: Dict[str, int] = {}
        with open("/proc/self/io", "r", encoding="utf-8") as fh:
            for line in fh:
                key, _, value = line.partition(":")
                try:
                    counters[key.strip()] = int(value.strip())
                except ValueError:
                    continue
        return {
            "rchar_bytes": int(counters.get("rchar", 0)),
            "read_bytes": int(counters.get("read_bytes", 0)),
            "method": "proc_io",
        }
    except (OSError, ValueError):
        return {"rchar_bytes": 0, "read_bytes": 0, "method": "unavailable"}


def _residency_delta(before: Dict[str, Any], after: Dict[str, Any]) -> Dict[str, Any]:
    """Bounded residency proof from two /proc/self/io snapshots."""
    if before.get("method") != "proc_io" or after.get("method") != "proc_io":
        return {"rchar_bytes": 0, "read_bytes": 0, "method": "unavailable"}
    return {
        "rchar_bytes": max(0, int(after["rchar_bytes"]) - int(before["rchar_bytes"])),
        "read_bytes": max(0, int(after["read_bytes"]) - int(before["read_bytes"])),
        "method": "proc_io",
    }


def _plan_fingerprint(layout: SafetensorsLayout, block_bytes: int) -> str:
    """Deterministic fingerprint of the range plan rebuilt from ``layout``."""
    rebuilt = QDRangePlan.build(layout, block_bytes)
    digest = hashlib.sha256()
    digest.update(f"block_bytes={block_bytes};data={rebuilt.data_start}-{rebuilt.data_end};".encode("utf-8"))
    for blk in rebuilt.blocks:
        digest.update(f"{blk.index}:{blk.file_start}:{blk.file_end};".encode("utf-8"))
    return digest.hexdigest()


# ---------------------------------------------------------------------------
# Transfer backends
# ---------------------------------------------------------------------------


class _CudaCompletion:
    __slots__ = ("_event",)

    def __init__(self, event: Any) -> None:
        self._event = event

    def query(self) -> bool:
        return bool(self._event.query())

    def wait(self) -> None:
        self._event.synchronize()


class CudaTransferBackend(TransferBackend):
    """Production backend: pinned staging + non_blocking H2D + cuda events."""

    def __init__(self, device: str = "cuda:0") -> None:
        if torch is None or not torch.cuda.is_available():
            raise RuntimeError("CudaTransferBackend requires torch with CUDA")
        self.device = device

    def allocate_staging_slot(self, nbytes: int) -> Any:
        return torch.empty(nbytes, dtype=torch.uint8, pin_memory=True)

    def allocate_destination_buffer(self, nbytes: int) -> Any:
        return torch.empty(nbytes, dtype=torch.uint8, device=self.device)

    def issue_copy(self, src: Any, dst: Any, length: int) -> Any:
        with torch.no_grad():
            dst[:length].copy_(src[:length], non_blocking=True)
        event = torch.cuda.Event()
        event.record()
        return _CudaCompletion(event)

    def synchronize(self) -> None:
        torch.cuda.synchronize()


class _FutureCompletion:
    __slots__ = ("_future",)

    def __init__(self, future: Future) -> None:
        self._future = future

    def query(self) -> bool:
        return self._future.done()

    def wait(self) -> None:
        self._future.result()


class CpuCopyBackend(TransferBackend):
    """Hermetic deterministic CPU backend (no CUDA required).

    Copies execute on an internal thread pool so ``issue_copy`` returns
    immediately — genuinely asynchronous, which lets tests inject slow H2D
    via ``copy_latency_s`` and prove the source plane decoupling.
    """

    def __init__(self, copy_latency_s: Optional[Callable[[int], float]] = None) -> None:
        self._copy_latency_s = copy_latency_s
        self._executor = ThreadPoolExecutor(max_workers=8, thread_name_prefix="golden-cpu-h2d")
        self._pending: List[Future] = []
        self._pending_lock = threading.Lock()

    def allocate_staging_slot(self, nbytes: int) -> Any:
        return torch.empty(nbytes, dtype=torch.uint8)

    def allocate_destination_buffer(self, nbytes: int) -> Any:
        return torch.empty(nbytes, dtype=torch.uint8)

    def issue_copy(self, src: Any, dst: Any, length: int) -> Any:
        src_view = src[:length]
        dst_view = dst[:length]

        def _task() -> None:
            delay = self._copy_latency_s(length) if self._copy_latency_s else 0.0
            if delay:
                time.sleep(delay)
            with torch.no_grad():
                dst_view.copy_(src_view)

        future = self._executor.submit(_task)
        with self._pending_lock:
            self._pending.append(future)
        return _FutureCompletion(future)

    def synchronize(self) -> None:
        with self._pending_lock:
            pending = list(self._pending)
            self._pending.clear()
        for fut in pending:
            fut.result()

    def close(self) -> None:
        self.synchronize()
        self._executor.shutdown(wait=True)


# ---------------------------------------------------------------------------
# Source block reader (positional preadv on POSIX; per-worker handles on Windows)
# ---------------------------------------------------------------------------


class _BlockReader:
    """Thread-safe positional block reads.

    POSIX uses one shared fd with os.preadv (positional => thread-safe).
    Windows lacks preadv/pread, so each worker opens its own raw handle and
    uses seek+readinto under a per-reader lock.
    """

    def __init__(self, path: str) -> None:
        self._path = path
        self._use_preadv = hasattr(os, "preadv")
        self._fd: Optional[int] = None
        self._fh = None
        self._lock = threading.Lock()
        if self._use_preadv:
            self._fd = os.open(path, os.O_RDONLY)
        else:
            self._fh = open(path, "rb", buffering=0)

    def new_worker_view(self) -> "_BlockReader":
        if self._use_preadv:
            return self
        return _BlockReader(self._path)

    def read_into(self, file_offset: int, mv: memoryview, expected: int) -> int:
        if self._use_preadv:
            total = 0
            while total < expected:
                n = os.preadv(self._fd, [mv[total:expected]], file_offset + total)
                if n == 0:
                    break
                total += n
            return total
        with self._lock:
            self._fh.seek(file_offset)
            return self._fh.readinto(mv[:expected]) or 0

    def close(self) -> None:
        if self._fd is not None:
            try:
                os.close(self._fd)
            finally:
                self._fd = None
        if self._fh is not None:
            self._fh.close()
            self._fh = None


def _open_worker_reader(shared: _BlockReader) -> _BlockReader:
    view = shared.new_worker_view()
    return view


# ---------------------------------------------------------------------------
# Bounded staging ring
# ---------------------------------------------------------------------------


class _StagingRing:
    def __init__(self, backend: TransferBackend, slot_count: int, block_bytes: int) -> None:
        self.slots: List[Any] = [backend.allocate_staging_slot(block_bytes) for _ in range(slot_count)]
        self.block_bytes = block_bytes
        self._free: List[int] = list(range(slot_count))
        self._cv = threading.Condition()
        self.backpressure_events = 0
        self.backpressure_wait_ms_total = 0.0
        self._waiting_acquires = 0

    def acquire(self, timeout_s: float) -> int:
        t0 = time.perf_counter()
        with self._cv:
            waited_needed = not self._free
            if waited_needed:
                self._waiting_acquires += 1
            try:
                got = self._cv.wait_for(lambda: bool(self._free), timeout=timeout_s)
                if not got:
                    raise TimeoutError("staging ring exhausted beyond slot_wait_timeout_s")
                idx = self._free.pop()
            finally:
                if waited_needed:
                    self._waiting_acquires -= 1
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        if waited_needed:
            self.backpressure_events += 1
            self.backpressure_wait_ms_total += elapsed_ms
        return idx

    def blocked_waiters(self) -> int:
        """Workers currently blocked waiting for a staging slot."""
        with self._cv:
            return self._waiting_acquires

    def release(self, idx: int) -> None:
        with self._cv:
            self._free.append(idx)
            self._cv.notify()

    def free_count(self) -> int:
        with self._cv:
            return len(self._free)

    def free_count_sample(self) -> int:
        """Lock-free telemetry sample (GIL-atomic len read; best-effort)."""
        return len(self._free)

    def waiting_sample(self) -> int:
        """Lock-free telemetry sample of blocked acquires (best-effort)."""
        return self._waiting_acquires

    def release_everything(self) -> None:
        with self._cv:
            self._free = list(range(len(self.slots)))
            self._cv.notify_all()


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class GoldenQD4Loader:
    """Deterministic QD4 model loader with decoupled source/H2D planes."""

    def __init__(self, config: Optional[QD4EngineConfig] = None, backend: Optional[TransferBackend] = None) -> None:
        self.config = config or QD4EngineConfig()
        self.backend = backend
        # Instrumentation hook: peak heap staging bytes observed by the most
        # recent prepare_source() call (bounded by queue_depth * block_bytes).
        self.last_prepare_peak_heap_bytes = 0

    # -- public entry ------------------------------------------------------

    def load(
        self,
        manifest: RoleManifest,
        destination: DestinationPlan,
        ledger_sink: Optional[LedgerEventSink] = None,
        label: str = "golden_qd",
    ) -> LoadResult:
        cfg = self.config
        plan = manifest.qd_range_plan
        telemetry = GoldenQDTelemetry(
            configured_qd=cfg.queue_depth,
            target_qd=cfg.queue_depth,
            planned_block_count=plan.n_blocks,
            bytes_total=plan.total_bytes,
            staging_slots=cfg.staging_slots,
        )
        emit = ledger_sink.emit if ledger_sink is not None else (lambda *a, **k: None)

        destination.validate(manifest)

        ring = _StagingRing(self.backend, cfg.staging_slots, plan.block_bytes)
        telemetry.pinned_bytes = cfg.staging_slots * plan.block_bytes

        lock = threading.Lock()
        abort = threading.Event()

        blocks: Tuple[BlockPlan, ...] = plan.blocks
        state: Dict[str, Any] = {
            "cursor": 0,
            "reads_started": 0,
            "reads_completed": 0,
            "h2d_submitted": 0,
            "h2d_completed": 0,
            "completed_bytes": 0,
            "ready": deque(),
            "ready_cv": threading.Condition(),
            "inflight": [],
            "latencies_ms": [],
            "first_completion_ns": None,
            "last_completion_ns": None,
            "first_submit_ns": None,
            "worker_exceptions": [],
            "thread_cpu_s": {},
            "max_outstanding": 0,
            "max_ready_depth": 0,
            "max_inflight_depth": 0,
            "h2d_issue_ms_total": 0.0,
            "h2d_issue_ms_max": 0.0,
            "h2d_device_ms_total": 0.0,
            "h2d_start_emitted": False,
            "h2d_end_emitted": False,
            # Exact occupancy timeline: (perf_counter_ns, outstanding_delta,
            # completed_bytes_after) recorded by the threads that CAUSE each
            # transition.  Time-weighted QD occupancy is integrated from this
            # at drain; no sampling thread can starve it.
            "timeline": [],
            # Direct scheduler-denial accounting (worker-measured).
            "gate_wait_ms_total": 0.0,
        }

        shared_reader = _BlockReader(manifest.model_path)
        process_cpu0 = time.process_time()
        submit_wall0 = time.perf_counter_ns()
        errors: List[Exception] = []

        def _emit(name: str, **fields: Any) -> None:
            try:
                emit(f"{label}_{name}", **fields)
            except Exception:
                pass

        def _fail(exc: Exception) -> None:
            if not errors:
                errors.append(exc)
            abort.set()
            with state["ready_cv"]:
                state["ready_cv"].notify_all()

        # -- source worker -------------------------------------------------

        def _source_worker(wid: int) -> None:
            cpu0 = time.thread_time()
            reader = _open_worker_reader(shared_reader)
            try:
                while not abort.is_set():
                    with lock:
                        cursor = state["cursor"]
                        if cursor >= len(blocks):
                            break
                        state["cursor"] = cursor + 1
                        blk = blocks[cursor]
                        # NOTE: reads_started is incremented AFTER slot
                        # acquisition (below) so that "outstanding" counts
                        # only reads actually in flight — a worker blocked
                        # waiting for a bounded staging slot is exactly the
                        # H2D_BACKPRESSURE condition, not source concurrency.

                    # Scheduler-denied issuance: an explicit bounded
                    # resource condition (batch contract).  The wait is
                    # measured directly by the worker and reported as
                    # below-QD scheduler_blocked time.
                    if cfg.claim_gate is not None:
                        gate_t0 = time.perf_counter()
                        while not abort.is_set() and not bool(cfg.claim_gate()):
                            with state["ready_cv"]:
                                state["ready_cv"].wait(timeout=0.002)
                        if abort.is_set():
                            break
                        with lock:
                            state["gate_wait_ms_total"] += (time.perf_counter() - gate_t0) * 1000.0

                    slot = ring.acquire(timeout_s=cfg.slot_wait_timeout_s)
                    mv = memoryview(ring.slots[slot].numpy())
                    with lock:
                        state["reads_started"] += 1
                        started = state["reads_started"]
                        completed_now = state["reads_completed"]
                        state["max_outstanding"] = max(state["max_outstanding"], started - completed_now)
                        state["timeline"].append(
                            (time.perf_counter_ns(), 1, state["completed_bytes"])
                        )

                    t0 = time.perf_counter_ns()
                    try:
                        n = reader.read_into(blk.file_start, mv, blk.length)
                    except Exception:
                        with lock:
                            telemetry.per_read_errors += 1
                        raise
                    lat_ms = (time.perf_counter_ns() - t0) / 1e6
                    if n != blk.length:
                        with lock:
                            telemetry.per_read_errors += 1
                        raise ShortReadError(
                            f"block {blk.index}: read {n} of {blk.length} bytes at offset {blk.file_start}"
                        )

                    now = time.perf_counter_ns()
                    last_done = False
                    with lock:
                        state["reads_completed"] += 1
                        completed_now = state["reads_completed"]
                        state["latencies_ms"].append(lat_ms)
                        state["timeline"].append((now, -1, state["completed_bytes"]))
                        if state["first_completion_ns"] is None:
                            state["first_completion_ns"] = now
                            _emit("source_first_completion", latency_ms=round(lat_ms, 4))
                        state["last_completion_ns"] = now
                        if completed_now == len(blocks):
                            last_done = True
                    if last_done:
                        _emit("source_last_completion", latency_ms=round(lat_ms, 4))
                        _emit("source_complete", blocks=len(blocks))
                    with state["ready_cv"]:
                        state["ready"].append((blk, slot))
                        state["max_ready_depth"] = max(state["max_ready_depth"], len(state["ready"]))
                        state["ready_cv"].notify_all()
                return
            except Exception as exc:  # noqa: BLE001 - fail-closed boundary
                telemetry.worker_exceptions += 1
                _fail(exc)
            finally:
                with lock:
                    state["thread_cpu_s"][f"source_{wid}"] = time.thread_time() - cpu0
                if reader is not shared_reader:
                    reader.close()

        # -- H2D dispatcher -------------------------------------------------

        def _dispatcher() -> None:
            cpu0 = time.thread_time()
            try:
                while True:
                    item = None
                    with state["ready_cv"]:
                        if state["ready"]:
                            item = state["ready"].popleft()
                        elif abort.is_set():
                            break
                        else:
                            state["ready_cv"].wait(timeout=0.02)
                            if state["ready"]:
                                item = state["ready"].popleft()
                    if item is not None:
                        blk, slot = item
                        completions = []
                        for seg in blk.segments:
                            dst_buf = destination.buffers[seg.buffer_index]
                            src_t = ring.slots[slot][seg.src_offset : seg.src_offset + seg.length]
                            dst_t = dst_buf[seg.dest_offset : seg.dest_offset + seg.length]
                            with lock:
                                first_issue = not state["h2d_start_emitted"]
                                state["h2d_start_emitted"] = True
                            if first_issue:
                                _emit("h2d_start")
                            t0 = time.perf_counter()
                            issued_ns = time.perf_counter_ns()
                            comp = self.backend.issue_copy(src_t, dst_t, seg.length)
                            issue_ms = (time.perf_counter() - t0) * 1000.0
                            with lock:
                                state["h2d_issue_ms_total"] += issue_ms
                                state["h2d_issue_ms_max"] = max(state["h2d_issue_ms_max"], issue_ms)
                            completions.append((comp, seg.length, issued_ns))
                        with lock:
                            state["h2d_submitted"] += 1
                            telemetry.h2d_submitted_bytes += blk.length
                            state["inflight"].append((blk, slot, completions))
                            state["max_inflight_depth"] = max(state["max_inflight_depth"], len(state["inflight"]))
                    _reap()
                    with lock:
                        drained = (
                            state["h2d_submitted"] >= len(blocks)
                            and not state["ready"]
                            and not state["inflight"]
                        )
                        end_emitted = state["h2d_end_emitted"]
                        completed_bytes_now = state["completed_bytes"]
                        if drained:
                            state["h2d_end_emitted"] = True
                    if drained:
                        if not end_emitted:
                            _emit("h2d_end", completed_bytes=completed_bytes_now)
                        break
                return
            except Exception as exc:  # noqa: BLE001 - fail-closed boundary
                _fail(exc)
            finally:
                with lock:
                    state["thread_cpu_s"]["h2d_dispatcher"] = time.thread_time() - cpu0

        def _reap() -> None:
            with lock:
                inflight = state["inflight"]
            still = []
            released_any = False
            now_ns = time.perf_counter_ns()
            for blk, slot, completions in inflight:
                pending = []
                bytes_done = 0
                device_ms_delta = 0.0
                complete_block = True
                for comp, length, issued_ns in completions:
                    if comp.query():
                        bytes_done += length
                        # Polling-granularity measure of issue -> first
                        # observed completion for this segment.
                        device_ms_delta += (now_ns - issued_ns) / 1e6
                    else:
                        pending.append((comp, length, issued_ns))
                        complete_block = False
                if complete_block:
                    ring.release(slot)
                    released_any = True
                    with lock:
                        state["h2d_completed"] += 1
                        state["completed_bytes"] += blk.length
                        state["h2d_device_ms_total"] += device_ms_delta
                        telemetry.h2d_completed_bytes += blk.length
                else:
                    still.append((blk, slot, pending))
            if still or released_any:
                with lock:
                    state["inflight"] = still

        # -- occupancy sampler ----------------------------------------------

        # -- exact occupancy accounting (transition timeline) -----------------
        #
        # The occupancy curve is integrated from worker-recorded transitions,
        # NOT from a sampling thread: under CPython's GIL a sampler thread
        # cannot keep cadence against hot workers, which made sampled
        # time-weighted occupancy unreliable.  Every transition is recorded
        # by the thread that causes it, so the integral is exact regardless
        # of scheduling.

        def _integrate_occupancy() -> None:
            timeline = state["timeline"]
            last_ns = state["last_completion_ns"] or submit_wall0
            if not timeline:
                return
            target = cfg.queue_depth
            first_completion_ns = state["first_completion_ns"]

            # Pass 1: last claim transition (delta > 0) bounds the tail.
            last_claim_ns = None
            for ts, delta, _bytes_after in timeline:
                if delta > 0:
                    last_claim_ns = ts

            # Pass 2: integrate the piecewise-constant outstanding curve.
            prev_ns = submit_wall0
            prev_out = 0
            prev_bytes = 0
            at_target_ns = 0
            at_target_bytes = 0
            below: Dict[str, float] = {}
            for ts, delta, bytes_after in timeline:
                dur_ms = max(0.0, (ts - prev_ns) / 1e6)
                if prev_out >= target:
                    at_target_ns += max(0, ts - prev_ns)
                    at_target_bytes += max(0, bytes_after - prev_bytes)
                else:
                    if first_completion_ns is None or prev_ns < first_completion_ns:
                        bucket = "startup_ramp"
                    elif last_claim_ns is not None and prev_ns >= last_claim_ns:
                        bucket = "tail_drain"
                    else:
                        # Mid-load below-target time is attributed from the
                        # direct measurements below (h2d backpressure /
                        # scheduler gate); whatever they do not cover is
                        # folded into unexplained via the residual.
                        bucket = "mid_below"
                    below[bucket] = below.get(bucket, 0.0) + dur_ms
                prev_ns = ts
                prev_out += delta
                prev_bytes = bytes_after
            # Tail interval after the final transition up to last completion.
            tail_dur_ms = max(0.0, (last_ns - prev_ns) / 1e6)
            if prev_out >= target:
                at_target_ns += max(0, last_ns - prev_ns)
                at_target_bytes += max(0, state["completed_bytes"] - prev_bytes)
            else:
                below["tail_drain"] = below.get("tail_drain", 0.0) + tail_dur_ms

            window_ns = max(1, last_ns - submit_wall0)
            telemetry.occupancy_samples = len(timeline) + 1
            telemetry.samples_at_target_qd = int(
                round(len(timeline) * (at_target_ns / window_ns))
            )
            telemetry.fraction_time_at_target_qd = at_target_ns / window_ns
            if at_target_ns > 0:
                telemetry.steady_state_gbps = (at_target_bytes / (at_target_ns / 1e9)) / 1e9

            buckets: Dict[str, float] = dict(telemetry.time_below_qd_ms_by_reason)
            for key in ("startup_ramp", "tail_drain"):
                if below.get(key):
                    buckets[key] = round(buckets.get(key, 0.0) + below[key], 3)
            h2d_bp_ms = ring.backpressure_wait_ms_total
            if h2d_bp_ms > 0:
                buckets["h2d_backpressure"] = round(h2d_bp_ms, 3)
            gate_ms = float(state["gate_wait_ms_total"])
            if gate_ms > 0:
                buckets["scheduler_blocked"] = round(gate_ms, 3)
            total_below_ms = (window_ns / 1e6) * (1.0 - telemetry.fraction_time_at_target_qd)
            accounted = sum(buckets.values())
            residual = max(0.0, total_below_ms - accounted)
            if residual > 0:
                buckets["unexplained"] = round(buckets.get("unexplained", 0.0) + residual, 3)
            telemetry.time_below_qd_ms_by_reason = buckets

        # -- run -------------------------------------------------------------

        threads: List[threading.Thread] = []
        try:
            _emit(
                "submit_start",
                block_bytes=plan.block_bytes,
                device=str(getattr(destination.buffers[0], "device", "cpu")) if destination.buffers else "cpu",
                file_bytes=manifest.layout.file_bytes,
                n_ranges=plan.n_blocks,
                path=manifest.model_path,
                configured_qd=cfg.queue_depth,
                staging_slots=cfg.staging_slots,
            )
            disp_t = threading.Thread(target=_dispatcher, name="golden-h2d", daemon=True)
            disp_t.start()
            threads.append(disp_t)
            for wid in range(cfg.queue_depth):
                t = threading.Thread(target=_source_worker, args=(wid,), name=f"golden-src-{wid}", daemon=True)
                t.start()
                threads.append(t)

            deadline = time.monotonic() + cfg.overall_timeout_s
            # Bound GIL hold times while the engine's threads are running so
            # worker bytecode cannot monopolize the interpreter against the
            # dispatcher (hermetic/local case).  Restored in finally.
            prev_switch_interval = sys.getswitchinterval()
            sys.setswitchinterval(0.001)
            try:
                while not abort.is_set():
                    with lock:
                        finished = state["h2d_submitted"] >= len(blocks) and not state["inflight"]
                    if finished:
                        break
                    if time.monotonic() > deadline:
                        raise WorkerCrashedError(f"load exceeded overall_timeout_s={cfg.overall_timeout_s}")
                    time.sleep(0.002)
            finally:
                sys.setswitchinterval(prev_switch_interval)

            for t in threads:
                t.join(timeout=5.0)

            if errors:
                raise errors[0]

            with lock:
                reads_completed = state["reads_completed"]
                completed_bytes = state["completed_bytes"]
                h2d_completed = state["h2d_completed"]
            if reads_completed != plan.n_blocks or h2d_completed != plan.n_blocks:
                raise CoverageReconciliationError(
                    f"coverage mismatch: reads={reads_completed}/{plan.n_blocks} h2d={h2d_completed}/{plan.n_blocks}"
                )
            if completed_bytes != plan.total_bytes:
                raise CoverageReconciliationError(
                    f"byte mismatch: {completed_bytes} != {plan.total_bytes}"
                )

            last_ns = state["last_completion_ns"] or submit_wall0
            first_ns = state["first_completion_ns"] or submit_wall0
            telemetry.submit_count = plan.n_blocks
            telemetry.completion_count = plan.n_blocks
            telemetry.bytes_read = completed_bytes
            telemetry.source_wall_ms = (last_ns - submit_wall0) / 1e6
            telemetry.first_completion_ms = (first_ns - submit_wall0) / 1e6
            telemetry.last_completion_ms = (last_ns - submit_wall0) / 1e6
            lats = sorted(state["latencies_ms"])
            if lats:
                telemetry.source_latency_p50_ms = _percentile(lats, 50)
                telemetry.source_latency_p90_ms = _percentile(lats, 90)
                telemetry.source_latency_p99_ms = _percentile(lats, 99)
                telemetry.source_latency_max_ms = lats[-1]
            wall_s = telemetry.source_wall_ms / 1000.0
            if wall_s > 0:
                telemetry.aggregate_gbps = (completed_bytes / wall_s) / 1e9
            telemetry.observed_max_outstanding = state["max_outstanding"]
            telemetry.queue_backlog_max = state["max_ready_depth"]
            telemetry.completed_waiting_h2d_max_depth = state["max_inflight_depth"]
            telemetry.h2d_backpressure_events = ring.backpressure_events
            telemetry.h2d_backpressure_ms_total = round(ring.backpressure_wait_ms_total, 3)
            telemetry.h2d_host_issue_ms_total = round(state["h2d_issue_ms_total"], 3)
            telemetry.h2d_host_issue_ms_max = round(state["h2d_issue_ms_max"], 3)
            telemetry.h2d_device_wall_ms = round(state["h2d_device_ms_total"], 3)
            telemetry.thread_cpu_ms = round(sum(state["thread_cpu_s"].values()) * 1000.0, 3)
            telemetry.process_cpu_ms = round((time.process_time() - process_cpu0) * 1000.0, 3)
            _integrate_occupancy()
            telemetry.status = "ok"
            _emit("stats", **telemetry.to_dict())
            _emit("device_ready", aggregate_gbps=telemetry.aggregate_gbps, wall_ms=telemetry.source_wall_ms)
            return LoadResult(role=manifest.role, ok=True, telemetry=telemetry, destination=destination)
        except Exception as exc:
            telemetry.status = "error"
            if isinstance(exc, GoldenQDFailure):
                exc.telemetry = telemetry  # type: ignore[attr-defined]
                raise
            wrapped = WorkerCrashedError(f"{type(exc).__name__}: {exc}")
            wrapped.telemetry = telemetry  # type: ignore[attr-defined]
            raise wrapped from exc
        finally:
            abort.set()
            with state["ready_cv"]:
                state["ready_cv"].notify_all()
            for t in threads:
                if t.is_alive():
                    t.join(timeout=2.0)
            ring.release_everything()
            ring.slots.clear()
            shared_reader.close()

    # -- prepare / commit (R42 two-phase UNET path) --------------------------

    def prepare_source(
        self,
        manifest: RoleManifest,
        *,
        ledger_sink: Optional[LedgerEventSink] = None,
        label: str = "unet_qd",
    ) -> PreparedSource:
        """Storage-side page-cache warming pass (PHASE3, no device work).

        Spawns ``queue_depth`` workers that read ALL planned blocks at QD
        concurrency into a small reusable HEAP bytearray pool (total
        <= queue_depth * block_bytes; plain bytes objects — never pinned or
        CUDA host memory).  Read lengths are validated fail-closed exactly
        like ``load`` and contents are discarded after validation: physical
        reads are issued once here so the commit re-read hits the warm OS
        page cache.
        """
        cfg = self.config
        plan = manifest.qd_range_plan
        blocks: Tuple[BlockPlan, ...] = plan.blocks

        emit = ledger_sink.emit if ledger_sink is not None else (lambda *a, **k: None)

        def _emit(name: str, **fields: Any) -> None:
            try:
                emit(f"{label}_{name}", **fields)
            except Exception:
                pass

        lock = threading.Lock()
        abort = threading.Event()
        errors: List[Exception] = []
        telemetry_errors = [0]
        state: Dict[str, Any] = {
            "cursor": 0,
            "reads_completed": 0,
            "latencies_ms": [],
            "first_completion_ns": None,
            "last_completion_ns": None,
        }

        # Bounded reusable heap pool: at most queue_depth buffers of
        # block_bytes each.  Peak accounting is an instrumentation hook for
        # tests (loader.last_prepare_peak_heap_bytes).
        heap_live_bytes = 0
        heap_peak_bytes = 0
        pool_size = min(cfg.queue_depth, len(blocks))
        free_pool: List[bytearray] = []
        pool_cv = threading.Condition()

        def _pool_acquire() -> bytearray:
            nonlocal heap_live_bytes, heap_peak_bytes
            with pool_cv:
                if free_pool:
                    return free_pool.pop()
                buf = bytearray(plan.block_bytes)
                heap_live_bytes += plan.block_bytes
                heap_peak_bytes = max(heap_peak_bytes, heap_live_bytes)
                return buf

        def _pool_release(buf: bytearray) -> None:
            with pool_cv:
                free_pool.append(buf)

        io_before = _proc_io_snapshot()
        wall0 = time.perf_counter_ns()
        _emit(
            "prepare_start",
            block_bytes=plan.block_bytes,
            n_ranges=plan.n_blocks,
            path=manifest.model_path,
            configured_qd=cfg.queue_depth,
            heap_pool_buffers=pool_size,
        )

        def _prepare_worker(wid: int) -> None:
            reader = _open_worker_reader(shared_reader)
            try:
                while not abort.is_set():
                    with lock:
                        cursor = state["cursor"]
                        if cursor >= len(blocks):
                            break
                        state["cursor"] = cursor + 1
                        blk = blocks[cursor]
                    buf = _pool_acquire()
                    mv = memoryview(buf)
                    t0 = time.perf_counter_ns()
                    try:
                        n = reader.read_into(blk.file_start, mv, blk.length)
                    except Exception:
                        with lock:
                            telemetry_errors[0] += 1
                        raise
                    lat_ms = (time.perf_counter_ns() - t0) / 1e6
                    if n != blk.length:
                        with lock:
                            telemetry_errors[0] += 1
                        raise ShortReadError(
                            f"block {blk.index}: read {n} of {blk.length} bytes at offset {blk.file_start}"
                        )
                    # Contents validated then discarded: the buffer returns
                    # to the pool and nothing is retained.
                    _pool_release(buf)
                    now = time.perf_counter_ns()
                    last_done = False
                    with lock:
                        state["reads_completed"] += 1
                        state["latencies_ms"].append(lat_ms)
                        if state["first_completion_ns"] is None:
                            state["first_completion_ns"] = now
                            _emit("source_first_completion", latency_ms=round(lat_ms, 4))
                        state["last_completion_ns"] = now
                        if state["reads_completed"] == len(blocks):
                            last_done = True
                    if last_done:
                        _emit("source_last_completion", latency_ms=round(lat_ms, 4))
                return
            except Exception as exc:  # noqa: BLE001 - fail-closed boundary
                _fail(exc)
            finally:
                if reader is not shared_reader:
                    reader.close()

        shared_reader = _BlockReader(manifest.model_path)

        def _fail(exc: Exception) -> None:
            if not errors:
                errors.append(exc)
            abort.set()

        threads: List[threading.Thread] = []
        try:
            for wid in range(cfg.queue_depth):
                t = threading.Thread(target=_prepare_worker, args=(wid,), name=f"golden-prep-{wid}", daemon=True)
                t.start()
                threads.append(t)
            deadline = time.monotonic() + cfg.overall_timeout_s
            for t in threads:
                remaining = max(0.0, deadline - time.monotonic())
                t.join(timeout=remaining)
            for t in threads:
                if t.is_alive():
                    raise WorkerCrashedError("prepare_source worker exceeded overall_timeout_s")
        finally:
            abort.set()
            for t in threads:
                if t.is_alive():
                    t.join(timeout=2.0)
            shared_reader.close()

        if errors:
            exc = errors[0]
            if isinstance(exc, GoldenQDFailure):
                raise exc
            raise WorkerCrashedError(f"{type(exc).__name__}: {exc}") from exc

        wall1 = time.perf_counter_ns()
        prep_wall_ms = (wall1 - wall0) / 1e6
        lats = sorted(state["latencies_ms"])
        p50 = _percentile(lats, 50)
        p90 = _percentile(lats, 90)
        p99 = _percentile(lats, 99)
        total_bytes = plan.total_bytes
        aggregate_gbps = ((total_bytes / (prep_wall_ms / 1000.0)) / 1e9) if prep_wall_ms > 0 else 0.0
        residency_proof = _residency_delta(io_before, _proc_io_snapshot())

        self.last_prepare_peak_heap_bytes = heap_peak_bytes
        prepared = PreparedSource(
            role=manifest.role,
            manifest_identity_hash=manifest.identity_hash,
            source_path=manifest.model_path,
            range_plan_fingerprint=_plan_fingerprint(manifest.layout, plan.block_bytes),
            block_count=len(blocks),
            total_bytes=total_bytes,
            prep_wall_ms=round(prep_wall_ms, 3),
            prep_aggregate_gbps=round(aggregate_gbps, 3),
            prep_source_latency_p50_ms=round(p50, 4),
            prep_source_latency_p90_ms=round(p90, 4),
            prep_source_latency_p99_ms=round(p99, 4),
            residency_proof=residency_proof,
            prepared_at_mono_ns=time.monotonic_ns(),
            lifecycle_status="SOURCE_PREPARED",
        )
        _emit(
            "source_last_completion",
            latency_ms=round(state["latencies_ms"][-1], 4) if lats else 0.0,
        )
        _emit(
            "source_prepared",
            fingerprint=prepared.range_plan_fingerprint,
            block_count=prepared.block_count,
            total_bytes=prepared.total_bytes,
            prep_wall_ms=prepared.prep_wall_ms,
            prep_aggregate_gbps=prepared.prep_aggregate_gbps,
            residency_method=residency_proof["method"],
            read_errors=telemetry_errors[0],
            peak_heap_staging_bytes=heap_peak_bytes,
        )
        return prepared

    def commit_to_device(
        self,
        prepared: PreparedSource,
        manifest: RoleManifest,
        destination: DestinationPlan,
        *,
        ledger_sink: Optional[LedgerEventSink] = None,
        label: str = "unet_qd",
    ) -> LoadResult:
        """Consume a PreparedSource and run the standard QD4 load path.

        Identity gate runs BEFORE any I/O: identity hash, role, and the
        range-plan fingerprint rebuilt from the manifest layout must all
        match, and the prepared source must still be SOURCE_PREPARED (the
        CONSUMED transition is atomic; a second commit fails closed).
        """
        expected_fingerprint = _plan_fingerprint(manifest.layout, manifest.qd_range_plan.block_bytes)
        if (
            prepared.manifest_identity_hash != manifest.identity_hash
            or prepared.role != manifest.role
            or prepared.range_plan_fingerprint != expected_fingerprint
        ):
            raise PrepareCommitIdentityError(
                f"prepared source identity mismatch: prepared_role={prepared.role.value} "
                f"manifest_role={manifest.role.value} "
                f"hash_match={prepared.manifest_identity_hash == manifest.identity_hash} "
                f"fingerprint_match={prepared.range_plan_fingerprint == expected_fingerprint}"
            )
        if not prepared.try_consume():
            raise PrepareCommitIdentityError(
                f"prepared source lifecycle is {prepared.lifecycle_status!r}, expected SOURCE_PREPARED"
            )

        emit = ledger_sink.emit if ledger_sink is not None else (lambda *a, **k: None)

        def _emit(name: str, **fields: Any) -> None:
            try:
                emit(f"{label}_{name}", **fields)
            except Exception:
                pass

        _emit(
            "commit_start",
            identity_hash=manifest.identity_hash,
            block_count=prepared.block_count,
            total_bytes=prepared.total_bytes,
        )
        io_before = _proc_io_snapshot()
        result = self.load(manifest, destination, ledger_sink=ledger_sink, label=label)
        io_after = _proc_io_snapshot()
        telemetry = result.telemetry
        if io_after["method"] == "proc_io":
            read_delta = max(0, int(io_after["read_bytes"]) - int(io_before["read_bytes"]))
            telemetry.commit_read_storage_bytes = read_delta
            threshold = 0.10 * max(1, manifest.qd_range_plan.total_bytes)
            telemetry.commit_cache_served = read_delta < threshold
        else:
            telemetry.commit_read_storage_bytes = 0
            telemetry.commit_cache_served = None
        return result


def _percentile(sorted_vals: List[float], pct: float) -> float:
    if not sorted_vals:
        return 0.0
    k = (len(sorted_vals) - 1) * (pct / 100.0)
    f = int(k)
    c = min(f + 1, len(sorted_vals) - 1)
    if f == c:
        return sorted_vals[f]
    return sorted_vals[f] + (sorted_vals[c] - sorted_vals[f]) * (k - f)
