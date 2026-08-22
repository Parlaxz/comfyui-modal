"""E30 CLIP cold-I/O: genuine queue-depth (QD) source reader.

Why this module exists
----------------------
The E28 production CLIP loader is fastsafetensors ``SafeTensorsFileLoader``
(nogds pread path) with ``max_threads=8`` / ``max_copy_block_size=64 MiB`` /
``bbuf_size_kb=512 MiB``.  The installed C++ source proves that
``nogds_file_reader.submit_read`` keeps ONE std::thread per slot and JOINS
the previous thread in that slot before launching the next read (ext.cpp
``submit_read``: ``t->join(); delete(t); t = new std::thread(...)``).  So
``max_threads`` is the number of round-robin single-flight slots, NOT a
queue depth: at any instant there is exactly one outstanding read per
slot, and the reads in a slot are fully serialized.  Thread count is not
queue depth — this is the E27 finding this module exists to exploit.

E27 (V2_BATCH_E27_FIVE_TARGET_CRITICAL_PATH_FORENSICS.md §5.5) measured a
REAL queued-pread source experiment on qwen_3_4b.safetensors (~8.045 GB
data, 398 BF16 tensors):

    QD1 / 32 MiB  ≈   7.68 GB/s  (1047 ms)
    QD2 / 32 MiB  ≈  19.96 GB/s  ( 403 ms)
    QD4 / 32 MiB  ≈  42.03 GB/s  ( 191 ms, 30 ms CPU)
    QD8 / 64 MiB  ≈  45.00 GB/s  ( 179 ms, 220 ms CPU)

The E27 mechanism (``unet_qd_probe.run_qd_config``): ``qd`` worker threads,
each with its OWN pinned/bytearray buffer, reading DISJOINT static segments
of the file data section in ``block``-sized iterations via 32 MiB
``os.preadv`` syscalls (``_preadv_fill`` short-read retry loop); per-block
timings; wall = join of all workers; GB/s = bytes / wall.  Source-only
timing, H2D excluded (the separate ``gpu_transfer_phase`` measured
storage->pinned->async H2D combined).  This module reproduces that exact
mechanism and adds a bounded pinned->async-H2D stage into ONE contiguous
GPU destination buffer (the final resident buffer — no second copy), plus
exact SafeTensors header-driven range planning so reads are tensor-aligned.

Gate
----
Everything is behind ``COMFYMODAL_V2_CLIP_QD_READER`` (default OFF).  When
OFF: no read, no thread, no allocation, no CUDA touch, no import-time
side effect — every entry point returns ``{"status": "disabled"}`` before
opening the file or touching torch.

Integration state (E30 re-anchor, 2026-08-19): the production call site
IS live — ``speculative_clip_hydration._run_speculative_read`` selects
``clip_qd_load`` vs ``_fastsafe_load`` on the flag (uncommitted working
tree).  The demand-time hydrator's own ``_fastsafe_load`` fallback stays
unchanged for flag-OFF runs and for speculative-lane misses/failures.

Flag lifecycle (E30; see the batch report §17): all five flags are
consumed at restore (module import / speculative-lane start) and are baked
into the container through the modal_app ``_runtime_env`` passthrough, so
changing any of them requires a REDEPLOY.  They are not request-time
overridable.  Under the v2ctl control plane they should be registered with
``consumed_at = module_import|restore`` and ``change_requires = deploy``.

Launch policy (Phase 4)
-----------------------
The reader NEVER decides when to start.  The caller supplies a launch
policy (``restore_earliest`` / ``after_restore_sensitive_phase`` /
``after_cuda_restore`` / ``method_entry``), which is validated and recorded
in telemetry.  The future remote A/B (ARM A: current restore-time start;
ARM B: delayed until a proven safe restore boundary) is a caller-side
decision expressed through this parameter.

Telemetry (Phase 5)
-------------------
Compact aggregates are emitted as ``clip_qd_*`` trace events; per-block
detail is stored in ``stats["blocks"]`` and optionally written to a JSON
artifact (``COMFYMODAL_V2_CLIP_QD_ARTIFACT``).

GPU copy timing uses paired CUDA events for each staging slot.  The aggregate
``h2d.h2d_device_ms`` is the maximum available per-copy device duration (the
CUDA critical-path copy duration), not a sum or host issue time.  The host
``QD_H2D_ISSUE_TO_FINAL_COMPLETE_MS`` metric remains the host issue-to-final
completion boundary.  Event timing is best-effort: if a CUDA event does not
provide ``elapsed_time``, the device duration fields remain ``None``.
"""

from __future__ import annotations

import json
import math
import os
import threading
import time
from typing import Any, Optional

import torch

from comfymodal_runtime.env import env_flag
from . import clean_lane

# ── Gate / configuration ──────────────────────────────────────────────────

ENABLE_FLAG = "COMFYMODAL_V2_CLIP_QD_READER"
LAUNCH_POLICY_ENV = "COMFYMODAL_V2_CLIP_QD_LAUNCH_POLICY"
ARTIFACT_ENV = "COMFYMODAL_V2_CLIP_QD_ARTIFACT"
QD_ENV = "COMFYMODAL_V2_CLIP_QD_QD"
BLOCK_MIB_ENV = "COMFYMODAL_V2_CLIP_QD_BLOCK_MIB"

DEFAULT_QD = 4
DEFAULT_BLOCK_MIB = 32

LAUNCH_POLICIES = (
    "restore_earliest",
    "after_restore_sensitive_phase",
    "after_cuda_restore",
    "method_entry",
    "clean_lane_post_restore",
)

# Phase 5 telemetry event names (E29's canonical tracer can consume these).
EVT_SUBMIT_START = "clip_qd_source_submit_start"
EVT_SUBMIT_END = "clip_qd_source_submit_end"
EVT_READ_BEGIN = "clip_qd_read_begin"
EVT_READ_END = "clip_qd_read_end"
EVT_FIRST_COMPLETION = "clip_qd_source_first_completion"
EVT_LAST_COMPLETION = "clip_qd_source_last_completion"
EVT_BUFFER_WAIT = "clip_qd_buffer_wait"
EVT_COPY_START = "clip_qd_copy_to_device_start"
EVT_COPY_END = "clip_qd_copy_to_device_end"
EVT_DEVICE_READY = "clip_qd_device_ready"
EVT_OWNER_CREATED = "clip_qd_owner_created"
EVT_SPEC_RECORD_PUBLISH = "clip_qd_spec_record_publish"
EVT_TAKE = "clip_qd_take"
EVT_BIND = "clip_qd_bind"
EVT_OWNER_RETAINED = "clip_qd_owner_retained"

_VERIFY_COLLECT_LIMIT = 256 * 1024 * 1024  # collect_bytes honored below this
_STEADY_TAIL_FRAC = 0.10  # drop first/last 10% of block GB/s samples

CANONICAL_METRIC_KEYS = (
    "CUDA_READINESS_WAIT_MS",
    "QD_SOURCE_IO_WALL_MS",
    "QD_SOURCE_GBPS",
    "QD_MAX_SOURCE_IO_INFLIGHT",
    "QD_H2D_ISSUE_TO_FINAL_COMPLETE_MS",
    "QD_SOURCE_TO_GPU_READY_MS",
)

_TORCH_DTYPE = {
    "F32": torch.float32,
    "F16": torch.float16,
    "BF16": torch.bfloat16,
    "F64": torch.float64,
    "I64": torch.int64,
    "I32": torch.int32,
    "I16": torch.int16,
    "I8": torch.int8,
    "U8": torch.uint8,
    "U16": torch.uint16,
    "U32": torch.uint32,
    "U64": torch.uint64,
    "BOOL": torch.bool,
}

# ── Gate / config helpers ─────────────────────────────────────────────────


def clip_qd_reader_enabled() -> bool:
    """True only when ``COMFYMODAL_V2_CLIP_QD_READER`` is explicitly truthy."""
    return env_flag(ENABLE_FLAG)


def _env_int(name: str, default: int, lo: int, hi: int) -> int:
    try:
        raw = os.environ.get(name, "").strip()
        if raw:
            value = int(raw)
            if lo <= value <= hi:
                return value
    except Exception:
        pass
    return default


def _effective_qd(qd: Optional[int]) -> int:
    return _env_int(QD_ENV, DEFAULT_QD, 1, 32) if qd is None else max(1, min(32, int(qd)))


def _effective_block_bytes(block_mib: Optional[int]) -> int:
    mib = _env_int(BLOCK_MIB_ENV, DEFAULT_BLOCK_MIB, 1, 4096)
    if block_mib is not None:
        mib = max(1, min(4096, int(block_mib)))
    return mib * 1024 * 1024


def _effective_artifact_path(explicit: Optional[str]) -> str:
    if explicit:
        return str(explicit)
    return str(os.environ.get(ARTIFACT_ENV, "") or "").strip()


def validate_launch_policy(policy: str) -> str:
    """Return *policy* when it is a known launch policy, else raise
    ValueError.  The reader never chooses a policy itself."""
    policy = str(policy or "").strip()
    if policy not in LAUNCH_POLICIES:
        raise ValueError(f"unknown launch policy {policy!r}; expected one of {LAUNCH_POLICIES}")
    return policy


def resolve_launch_policy() -> str:
    """Caller-side helper: the launch policy from the environment, defaulting
    to ``restore_earliest`` (current production behavior)."""
    raw = os.environ.get(LAUNCH_POLICY_ENV, "").strip()
    if raw in LAUNCH_POLICIES:
        return raw
    return "restore_earliest"


def qd_config() -> dict[str, Any]:
    """Current effective configuration (telemetry/identity; never mutates)."""
    return {
        "enabled": clip_qd_reader_enabled(),
        "qd": _effective_qd(None),
        "block_bytes": _effective_block_bytes(None),
        "block_mib": _effective_block_bytes(None) // (1024 * 1024),
        "syscall_mode": _syscall_mode(),
        "launch_policy": resolve_launch_policy(),
        "artifact_path": _effective_artifact_path(None),
    }


def emit_qd_event(trace: Any, name: str, **metadata: Any) -> None:
    """Emit one ``clip_qd_*`` event on a trace-like (``.emit(name, phase=,
    metadata=)``).  Never raises.  Provided so the integration layer
    (speculative take/bind/owner-retain points) uses the exact event names
    without importing heavy machinery."""
    if trace is None:
        return
    try:
        trace.emit(name, phase="execution", metadata=dict(metadata))
    except Exception:
        pass


def ledger_event(name: str, **metadata: Any) -> None:
    """Record one E30 event on E29's canonical ledger (when available).

    E29 owns the canonical timeline; E30 only STAMPS its boundary events
    (``clip_qd_*``, EVT_* names) on the shared monotonic axis so the serial
    ledger can attribute the source->GPU-ready interval without a competing
    timeline engine.  Gated on the ledger module's own flag, never raises.
    """
    try:
        from .critical_path_ledger import record_event as _record

        _record(name, metadata=dict(metadata) or None)
    except Exception:
        pass


# ── Syscall layer ─────────────────────────────────────────────────────────


def _syscall_mode() -> str:
    if hasattr(os, "preadv"):
        return "preadv"
    if hasattr(os, "pread"):
        return "pread"
    return "lseek_read"


def _read_at(fd: int, mv: Any, offset: int) -> int:
    """Fill ``mv`` fully from absolute file ``offset``.  Uses os.preadv when
    available (E27 mechanism), else os.pread, else per-worker lseek+read
    (Windows fallback — workers use their own fd).  Returns bytes read."""
    total = 0
    n = 0
    if hasattr(os, "preadv"):
        while total < len(mv):
            n = int(os.preadv(fd, [mv[total:]], int(offset) + total))
            if n <= 0:
                break
            total += n
    elif hasattr(os, "pread"):
        while total < len(mv):
            data = os.pread(fd, len(mv) - total, int(offset) + total)
            n = len(data)
            if n <= 0:
                break
            mv[total : total + n] = data
            total += n
    else:
        while total < len(mv):
            os.lseek(fd, int(offset) + total, os.SEEK_SET)
            data = os.read(fd, len(mv) - total)
            n = len(data)
            if n <= 0:
                break
            mv[total : total + n] = data
            total += n
    return total


# ── Header / range planning (exact SafeTensors semantics) ─────────────────


def parse_safetensors_header(path: str) -> dict[str, Any]:
    """Read the 8-byte length + JSON header; validate offsets.  Returns
    ``{"status": "ok", header, data_start, total_data_bytes, tensor_count,
    size_bytes}`` or ``{"status": "error", reason}``."""
    out: dict[str, Any] = {"status": "error", "path": str(path)}
    try:
        size = int(os.path.getsize(path))
        if size < 8:
            return {**out, "reason": "truncated_header"}
        with open(path, "rb") as fh:
            raw = fh.read(8)
        if len(raw) < 8:
            return {**out, "reason": "truncated_header"}
        header_len = int.from_bytes(raw, "little")
        if header_len <= 0 or header_len > size - 8:
            return {**out, "reason": f"invalid_header_len:{header_len}"}
        with open(path, "rb") as fh:
            fh.seek(8)
            hb = fh.read(header_len)
        header = json.loads(hb.decode("utf-8"))
        if not isinstance(header, dict):
            return {**out, "reason": "header_not_object"}
        data_start = 8 + header_len
        data_bytes = size - data_start
        if data_bytes <= 0:
            return {**out, "reason": "no_tensor_data"}
        ranges: list[tuple[int, int, str]] = []
        count = 0
        for key, info in header.items():
            if key == "__metadata__":
                continue
            if not isinstance(info, dict):
                return {**out, "reason": f"tensor_entry_not_dict:{key}"}
            offs = info.get("data_offsets")
            if not isinstance(offs, (list, tuple)) or len(offs) != 2:
                return {**out, "reason": f"bad_data_offsets:{key}"}
            if any(isinstance(value, bool) or not isinstance(value, int) for value in offs):
                return {**out, "reason": f"non_integer_offsets:{key}"}
            try:
                start, end = int(offs[0]), int(offs[1])
            except Exception:
                return {**out, "reason": f"non_integer_offsets:{key}"}
            if start < 0 or end < start:
                return {**out, "reason": f"negative_or_inverted_range:{key}"}
            dtype_name = str(info.get("dtype", ""))
            dtype = _TORCH_DTYPE.get(dtype_name)
            if dtype is None:
                return {**out, "reason": f"unsupported_dtype:{key}:{dtype_name}"}
            shape = info.get("shape")
            if not isinstance(shape, (list, tuple)):
                return {**out, "reason": f"bad_shape:{key}"}
            if any(isinstance(dim, bool) or not isinstance(dim, int) for dim in shape):
                return {**out, "reason": f"non_integer_shape:{key}"}
            try:
                shape_values = [int(dim) for dim in shape]
            except Exception:
                return {**out, "reason": f"non_integer_shape:{key}"}
            if any(dim < 0 for dim in shape_values):
                return {**out, "reason": f"negative_shape:{key}"}
            expected = int(math.prod(shape_values)) * int(dtype.itemsize)
            length = end - start
            if length != expected:
                return {**out, "reason": f"dtype_shape_size_mismatch:{key}:{length}!={expected}"}
            ranges.append((start, end, str(key)))
            count += 1
        if not ranges:
            return {**out, "reason": "no_tensor_data"}
        expect = 0
        for start, end, key in sorted(ranges):
            if end > data_bytes:
                return {**out, "reason": f"range_out_of_bounds:{key}"}
            if start != expect:
                return {**out, "reason": f"non_contiguous_data_ranges:{key}:expected={expect}:got={start}"}
            expect = end
        if expect != data_bytes:
            return {**out, "reason": f"data_section_end_mismatch:{expect}!={data_bytes}"}
        return {
            **out,
            "status": "ok",
            "header": header,
            "data_start": int(data_start),
            "total_data_bytes": int(data_bytes),
            "tensor_count": int(count),
            "size_bytes": int(size),
        }
    except Exception as exc:
        return {**out, "reason": f"{type(exc).__name__}: {str(exc)[:120]}"}


def partition_coverage(ranges: list, total: int) -> tuple[bool, str]:
    """Validate that *ranges* (relative [start, end)) exactly cover
    [0, total): sorted starts at 0, contiguous, final end == total, no
    overlap.  Same contract as the C9 probe."""
    if not ranges:
        return (total == 0), "empty"
    rs = sorted((int(s), int(e)) for s, e in ranges)
    expect = 0
    for s, e in rs:
        if s != expect:
            return False, f"gap_or_overlap at {s} (expected {expect})"
        if e < s:
            return False, f"inverted_range {s}..{e}"
        expect = e
    if expect != int(total):
        return False, f"end {expect} != total {total}"
    return True, "ok"


def build_block_items(
    header: dict, data_start: int, block_bytes: int
) -> tuple[list, list, dict]:
    """Tensor-aligned block plan over the file data section.

    Returns ``(items, tensor_map, cov)``:

      * ``items`` — ``(abs_start, length)`` in file order, each wholly inside
        ONE tensor and <= block_bytes; together they exactly cover the data
        section (no gaps, no overlap, no missing tail).
      * ``tensor_map`` — ``(key, dtype, shape, rel_start, length)`` in file
        order (rel_start is relative to the data section).
      * ``cov`` — coverage proof dict.
    """
    block_bytes = max(1, int(block_bytes))
    items: list[tuple[int, int]] = []
    tensor_map: list[tuple[str, str, list, int, int]] = []
    total = 0
    for key, info in header.items():
        if key == "__metadata__":
            continue
        offs = info.get("data_offsets") or [0, 0]
        rel_start = int(offs[0])
        length = int(offs[1]) - int(offs[0])
        if length <= 0:
            continue
        dtype = str(info.get("dtype", ""))
        shape = [int(d) for d in (info.get("shape") or [])]
        tensor_map.append((str(key), dtype, shape, rel_start, length))
        total += length
        abs_start = data_start + rel_start
        off = 0
        while off < length:
            ln = min(block_bytes, length - off)
            items.append((abs_start + off, ln))
            off += ln
    rel_ranges = [(s - data_start, s + ln - data_start) for s, ln in items]
    ok, reason = partition_coverage(rel_ranges, total)
    cov = {"ok": ok, "reason": reason, "total_data_bytes": total}
    return items, tensor_map, cov


def build_header_tensor_map(header: dict) -> list[tuple[str, str, list, int, int]]:
    """Build the tensor view map without coupling it to source scheduling."""
    tensor_map: list[tuple[str, str, list, int, int]] = []
    for key, info in header.items():
        if key == "__metadata__":
            continue
        offs = info.get("data_offsets") or [0, 0]
        start = int(offs[0])
        length = int(offs[1]) - start
        if length <= 0:
            continue
        tensor_map.append((
            str(key), str(info.get("dtype", "")),
            [int(d) for d in (info.get("shape") or [])], start, length,
        ))
    return tensor_map


def plan_raw_source_regions(
    data_start: int, total_data_bytes: int, block_bytes: int, qd: int,
) -> list[list[tuple[int, int]]]:
    """Return exactly *qd* static, forward-only raw DATA SECTION regions."""
    data_start = int(data_start)
    total_data_bytes = int(total_data_bytes)
    block_bytes = max(1, int(block_bytes))
    qd = max(1, int(qd))
    if data_start < 0 or total_data_bytes < 0:
        raise ValueError("invalid data section")
    blocks = [
        (data_start + off, min(block_bytes, total_data_bytes - off))
        for off in range(0, total_data_bytes, block_bytes)
    ]
    regions: list[list[tuple[int, int]]] = []
    base, extra = divmod(len(blocks), qd)
    cursor = 0
    for worker in range(qd):
        count = base + (1 if worker < extra else 0)
        regions.append(blocks[cursor : cursor + count])
        cursor += count
    return regions


def build_raw_source_plan(
    data_start: int, total_data_bytes: int, block_bytes: int, qd: int,
) -> list[list[tuple[int, int]]]:
    return plan_raw_source_regions(data_start, total_data_bytes, block_bytes, qd)


def plan_static_raw_regions(
    data_start: int, total_data_bytes: int, block_bytes: int, qd: int,
) -> list[list[tuple[int, int]]]:
    return plan_raw_source_regions(data_start, total_data_bytes, block_bytes, qd)


def verify_tensors_against_map(sd: dict, tensor_map: list) -> dict[str, Any]:
    """Shape/dtype/byte-size parity of *sd* tensors against the header-derived
    tensor_map.  Returns ``{ok, checked, mismatches}``."""
    mismatches: list[str] = []
    checked = 0
    for key, dtype_str, shape, rel_start, length in tensor_map:
        t = sd.get(key)
        if t is None:
            mismatches.append(f"{key}:missing")
            continue
        checked += 1
        if list(t.shape) != shape:
            mismatches.append(f"{key}:shape {list(t.shape)} != {shape}")
        expected_dt = _TORCH_DTYPE.get(dtype_str)
        if expected_dt is not None and t.dtype != expected_dt:
            mismatches.append(f"{key}:dtype {t.dtype} != {expected_dt}")
        if int(t.numel() * t.element_size()) != int(length):
            mismatches.append(f"{key}:bytes {int(t.numel() * t.element_size())} != {int(length)}")
    return {"ok": not mismatches, "checked": checked, "mismatches": mismatches[:8]}


def sample_hash_of_tensors(sd: dict, seg: int = 262144) -> str:
    """Deterministic bounded sha256 over per-key byte samples in sorted key
    order (head+tail *seg* bytes of the flattened uint8 view).  CUDA tensors
    are sliced on device, only samples copied to CPU."""
    try:
        import hashlib

        h = hashlib.sha256()
        for key in sorted(sd):
            h.update(str(key).encode("utf-8"))
            t = sd[key]
            c = t.detach().contiguous().reshape(-1).view(torch.uint8)
            if c.device.type != "cpu":
                c = c.cpu()
            n = c.numel()
            if n <= 0:
                continue
            if n <= 2 * seg:
                h.update(c.numpy().tobytes())
            else:
                h.update(c[:seg].numpy().tobytes())
                h.update(c[-seg:].numpy().tobytes())
        return h.hexdigest()
    except Exception:
        return ""


# ── Reader state (queue-depth proof) ──────────────────────────────────────


class _StaticReaderState:
    def __init__(self, regions: list[list[tuple[int, int]]]):
        self.regions = regions
        self._lock = threading.Lock()
        self.records: list[dict] = []
        self.errors: list[str] = []
        self.submitted = 0
        self.completed = 0
        # This is observed source-read depth, not the size of the plan.  Keep
        # the running value as submitted-completed so telemetry can prove
        # actual backpressure without treating planned work as queued work.
        self.outstanding = 0
        self.max_outstanding = 0
        self.buffer_pool_wait_ms = 0.0
        # ``records`` is the completion ledger.  Keep worker-local bookkeeping
        # beside it so artifact reconciliation never has to infer ownership
        # from the source-read telemetry (which is intentionally source-only).
        self._worker_counts = {
            worker_id: {"submitted": 0, "completed": 0, "record_bytes": 0}
            for worker_id in range(len(regions))
        }
        self._worker_finalization: dict[int, dict[str, Any]] = {}

    @property
    def planned_items(self) -> list[tuple[int, int]]:
        return [item for region in self.regions for item in region]

    def record(self, record: dict) -> None:
        with self._lock:
            self.records.append(record)
            self.completed += 1
            self.outstanding = self.submitted - self.completed
            worker_id = record.get("worker_id")
            if worker_id is not None:
                worker_id = int(worker_id)
                worker = self._worker_counts.setdefault(
                    worker_id, {"submitted": 0, "completed": 0, "record_bytes": 0}
                )
                worker["completed"] += 1
                worker["record_bytes"] += int(record.get("read_len", record.get("len", 0)))

    @property
    def queue_backlog_max(self) -> int:
        """Compatibility name for the observed peak outstanding depth."""
        return self.max_outstanding

    def submit(self, worker_id: Optional[int] = None) -> None:
        with self._lock:
            self.submitted += 1
            self.outstanding = self.submitted - self.completed
            self.max_outstanding = max(self.max_outstanding, self.outstanding)
            if worker_id is not None:
                worker = self._worker_counts.setdefault(
                    int(worker_id), {"submitted": 0, "completed": 0, "record_bytes": 0}
                )
                worker["submitted"] += 1

    def finalize_worker(self, worker_id: int) -> None:
        """Publish the worker's terminal completion snapshot.

        This is bookkeeping only.  It does not create or alter a read/H2D
        record; it makes the terminal per-worker count auditable after joins.
        """
        with self._lock:
            worker_id = int(worker_id)
            counts = self._worker_counts.setdefault(
                worker_id, {"submitted": 0, "completed": 0, "record_bytes": 0}
            )
            self._worker_finalization[worker_id] = {
                "finalized": True,
                "submitted_count": int(counts["submitted"]),
                "record_count": int(counts["completed"]),
                "record_bytes": int(counts["record_bytes"]),
            }

    def worker_finalization_snapshot(self) -> dict[str, dict[str, Any]]:
        with self._lock:
            return {
                str(worker_id): dict(item)
                for worker_id, item in self._worker_finalization.items()
            }

    def error(self, worker_id: int, exc: BaseException) -> None:
        with self._lock:
            self.errors.append(
                f"worker={worker_id}:{type(exc).__name__}:{str(exc)[:160]}"
            )

    def add_buffer_wait(self, ms: float) -> None:
        with self._lock:
            self.buffer_pool_wait_ms += float(ms)


class _SourceTelemetry:
    def __init__(self, qd: int):
        self._lock = threading.Lock()
        self.inflight = 0
        self.max_inflight = 0
        self.earliest_start_ns: Optional[int] = None
        self.latest_end_ns: Optional[int] = None
        self.per_worker = {
            i: {
                "read_count": 0, "read_bytes": 0,
                "first_start_ns": None, "last_end_ns": None,
            }
            for i in range(int(qd))
        }

    def before(self, worker_id: int) -> int:
        now = time.perf_counter_ns()
        with self._lock:
            self.inflight += 1
            self.max_inflight = max(self.max_inflight, self.inflight)
            self.earliest_start_ns = (
                now if self.earliest_start_ns is None
                else min(self.earliest_start_ns, now)
            )
            worker = self.per_worker[int(worker_id)]
            if worker["first_start_ns"] is None:
                worker["first_start_ns"] = now
        return now

    def after(self, worker_id: int, started_ns: int, read_bytes: int) -> int:
        now = time.perf_counter_ns()
        with self._lock:
            self.inflight -= 1
            self.latest_end_ns = now if self.latest_end_ns is None else max(self.latest_end_ns, now)
            worker = self.per_worker[int(worker_id)]
            worker["read_count"] += 1
            worker["read_bytes"] += int(read_bytes)
            worker["last_end_ns"] = now
        return now

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            workers = {}
            for worker_id, item in self.per_worker.items():
                workers[str(worker_id)] = dict(item)
            return {
                "inflight": self.inflight,
                "max_inflight": self.max_inflight,
                "earliest_start_ns": self.earliest_start_ns,
                "latest_end_ns": self.latest_end_ns,
                "per_worker": workers,
            }


def _timed_read_at(
    fd: int, mv: Any, offset: int, worker_id: int, telemetry: _SourceTelemetry,
) -> tuple[int, int, int]:
    started = telemetry.before(worker_id)
    try:
        got = int(_read_at(fd, mv, offset))
    except BaseException:
        telemetry.after(worker_id, started, 0)
        raise
    ended = telemetry.after(worker_id, started, got)
    return got, started, ended


def _steady_state_gbps(records: list[dict]) -> Optional[float]:
    vals = [float(r["gbps"]) for r in records if r.get("gbps", 0) > 0]
    if len(vals) < 8:
        return None
    vals = sorted(vals)
    lo = max(0, int(len(vals) * _STEADY_TAIL_FRAC))
    hi = min(len(vals), int(len(vals) * (1.0 - _STEADY_TAIL_FRAC)))
    mid = vals[lo:hi]
    if not mid:
        return None
    return round(sorted(mid)[len(mid) // 2], 4)


def _thread_cpu_ms() -> Optional[float]:
    """Sum of utime+stime over /proc/self/task (Linux); None elsewhere."""
    try:
        tids = os.listdir("/proc/self/task")
        clk = float(os.sysconf(os.sysconf_names["SC_CLK_TCK"]))
        total = 0
        for tid in tids:
            try:
                with open(f"/proc/self/task/{tid}/stat", "r", encoding="utf-8") as fh:
                    parts = fh.read().rsplit(")", 1)[-1].split()
                total += int(parts[11]) + int(parts[12])
            except Exception:
                continue
        return round(total * (1000.0 / clk), 2)
    except Exception:
        return None


def _rss_mb() -> Optional[float]:
    try:
        import psutil

        return float(psutil.Process().memory_info().rss) / 1048576.0
    except Exception:
        return None


# ── Stats / telemetry ─────────────────────────────────────────────────────


def _new_stats(*, qd: int, block_bytes: int, file_bytes: int, n_ranges: int,
               launch_policy: str, syscall_mode: str) -> dict[str, Any]:
    return {
        "kind": "clip_qd_read",
        "status": "running",
        "configured_qd": qd,
        "observed_max_outstanding": 0,
        # None means no observed queue depth has been finalized yet.  A
        # planned block count is never used as a queue-depth substitute.
        "queue_backlog_max": None,
        "block_bytes": int(block_bytes),
        "file_bytes": int(file_bytes),
        "planned_bytes": int(file_bytes),
        "bytes_read": 0,
        "h2d_submitted_bytes": 0,
        "h2d_completed_bytes": 0,
        "n_ranges": int(n_ranges),
        "planned_block_count": int(n_ranges),
        "submitted_block_count": 0,
        "completed_block_count": 0,
        "h2d_completed_block_count": 0,
        "submit_count": 0,
        "completion_count": 0,
        "first_completion_latency_ms": None,
        "tail_completion_latency_ms": None,
        "total_source_wall_ms": None,
        "total_source_wall_ms_deprecated_compat_alias": None,
        "total_source_wall_ms_semantics": "deprecated_compatibility_alias_of_qd_source_io_wall_ms",
        "qd_source_io_wall_ms": None,
        "qd_source_io_wall_ns": None,
        "qd_source_gbps": None,
        "qd_max_source_io_inflight": 0,
        "qd_h2d_issue_to_final_complete_ms": None,
        "qd_source_to_gpu_ready_ms": None,
        "cuda_readiness_wait_ms": None,
        "CUDA_READINESS_WAIT_MS": None,
        "QD_SOURCE_IO_WALL_MS": None,
        "QD_SOURCE_GBPS": None,
        "QD_MAX_SOURCE_IO_INFLIGHT": 0,
        "QD_H2D_ISSUE_TO_FINAL_COMPLETE_MS": None,
        "QD_SOURCE_TO_GPU_READY_MS": None,
        "metrics": {key: None for key in CANONICAL_METRIC_KEYS},
        "source_io_inflight": 0,
        "source_io": {"per_worker": {}},
        "per_worker_source_io": {},
        "record_reconciliation": {
            "ok": False,
            "reason": "not_finalized",
            "authoritative_record_source": "state.records",
            "authoritative_record_count": 0,
            "per_worker": {},
        },
        "byte_reconciliation": {},
        "coverage": {"ok": False, "reason": "not_validated"},
        "aggregate_gbps": None,
        "steady_state_gbps": None,
        "thread_cpu_ms": None,
        "process_cpu_ms": None,
        "buffer_pool_wait_ms": 0.0,
        "per_read_errors": 0,
        "syscall_mode": str(syscall_mode),
        "launch_policy": str(launch_policy),
        "h2d": {
            "copy_count": 0,
            "submitted_bytes": 0,
            "completed_bytes": 0,
            "h2d_host_issue_total_ms": 0.0,
            "h2d_host_issue_max_ms": 0.0,
            "h2d_device_ms": None,
            "h2d_device_ms_semantics": "max_per_copy_cuda_event_duration_critical_path",
            "pinned_bytes": 0,
            "gpu_bytes": 0,
        },
        "memory": {
            "rss_delta_mb": None,
            "cuda_alloc_delta_bytes": None,
        },
        "fallback": {
            "pin_fallback": 0,
            "alignment_tensor_count": 0,
            "alignment_extra_source_bytes": 0,
            "disabled": False,
        },
        "blocks": [],
        "source_identity": None,
        "source_errors": [],
    }


def _sync_canonical_metrics(stats: dict) -> None:
    values = {
        "CUDA_READINESS_WAIT_MS": stats.get("cuda_readiness_wait_ms"),
        "QD_SOURCE_IO_WALL_MS": stats.get("qd_source_io_wall_ms"),
        "QD_SOURCE_GBPS": stats.get("qd_source_gbps"),
        "QD_MAX_SOURCE_IO_INFLIGHT": stats.get("qd_max_source_io_inflight"),
        "QD_H2D_ISSUE_TO_FINAL_COMPLETE_MS": stats.get("qd_h2d_issue_to_final_complete_ms"),
        "QD_SOURCE_TO_GPU_READY_MS": stats.get("qd_source_to_gpu_ready_ms"),
    }
    stats.update(values)
    stats["metrics"] = dict(values)


def _reconcile_worker_records(
    records: list[dict], source: Optional[dict], state: Any,
) -> dict[str, Any]:
    """Reconcile the completion ledger with source-read telemetry.

    ``state.records`` is the authoritative completion ledger: it is the same
    list used for ``completion_count``, byte validation, and H2D finalization.
    ``_SourceTelemetry.after`` is deliberately narrower and only accounts for
    source-read callbacks.  Therefore a difference is reported as an explicit
    excluded count, never silently folded into ``read_count``.  A source count
    or byte total greater than the authoritative ledger cannot be reconciled
    and is marked invalid (callers fail closed).
    """
    records_by_worker: dict[str, list[dict]] = {}
    for record in records:
        worker_id = record.get("worker_id")
        if worker_id is None:
            return {
                "ok": False,
                "reason": "record_missing_worker_id",
                "authoritative_record_source": "state.records",
                "authoritative_record_count": len(records),
                "per_worker": {},
            }
        key = str(int(worker_id))
        records_by_worker.setdefault(key, []).append(record)

    source_workers = (source or {}).get("per_worker", {}) if source is not None else {}
    finalization = getattr(state, "worker_finalization_snapshot", lambda: {})()
    worker_ids = sorted(
        set(records_by_worker) | set(source_workers) | set(finalization),
        key=lambda value: int(value),
    )
    per_worker: dict[str, dict[str, Any]] = {}
    excluded_total = 0
    excluded_bytes_total = 0
    source_count_total = 0
    source_bytes_total = 0
    record_bytes_total = 0
    reasons: list[str] = []

    for worker_id in worker_ids:
        worker_records = records_by_worker.get(worker_id, [])
        record_count = len(worker_records)
        record_bytes = sum(
            int(record.get("read_len", record.get("len", 0)))
            for record in worker_records
        )
        observed = source_workers.get(worker_id, {})
        source_count = None if source is None else int(observed.get("read_count", 0))
        source_bytes = None if source is None else int(observed.get("read_bytes", 0))
        final = finalization.get(worker_id)

        excluded_count = None
        excluded_bytes = None
        if source is not None:
            if source_count > record_count or source_bytes > record_bytes:
                reasons.append(
                    f"worker={worker_id}:source_exceeds_records"
                )
            else:
                excluded_count = record_count - source_count
                excluded_bytes = record_bytes - source_bytes
                excluded_total += excluded_count
                excluded_bytes_total += excluded_bytes
                source_count_total += source_count
                source_bytes_total += source_bytes

        finalization_ok = final is None or (
            int(final.get("record_count", -1)) == record_count
            and int(final.get("record_bytes", -1)) == record_bytes
        )
        if not finalization_ok:
            reasons.append(f"worker={worker_id}:finalization_mismatch")

        per_worker[worker_id] = {
            # These are all tied to the same authoritative state.records list.
            "record_count": record_count,
            "completion_count": record_count,
            "completion_record_count": record_count,
            "record_bytes": record_bytes,
            "completion_record_bytes": record_bytes,
            # Source counters retain their original meaning and are not
            # backfilled from completion records.
            "read_count": source_count,
            "read_bytes": source_bytes,
            "source_read_count": source_count,
            "source_read_bytes": source_bytes,
            "excluded_from_source_read_counters": {
                "record_count": excluded_count,
                "completion_record_count": excluded_count,
                "bytes": excluded_bytes,
                "semantics": (
                    "authoritative completion records without a matching "
                    "_SourceTelemetry.after observation; not additional reads"
                    if source is not None else
                    "source-read counters were not collected; no exclusion inferred"
                ),
            },
            "finalization": {
                "observed": final is not None,
                "record_count": None if final is None else int(final.get("record_count", 0)),
                "record_bytes": None if final is None else int(final.get("record_bytes", 0)),
                "matches_authoritative_records": finalization_ok,
            },
        }
        record_bytes_total += record_bytes

    source_available = source is not None
    return {
        "ok": not reasons,
        "reason": "ok" if not reasons else ";".join(reasons),
        "authoritative_record_source": "state.records",
        "authoritative_record_count": len(records),
        "authoritative_completion_record_count": len(records),
        "authoritative_record_bytes": record_bytes_total,
        "authoritative_completion_record_bytes": record_bytes_total,
        "source_read_count": source_count_total if source_available else None,
        "source_read_bytes": source_bytes_total if source_available else None,
        "excluded_from_source_read_counters": {
            "record_count": excluded_total if source_available else None,
            "completion_record_count": excluded_total if source_available else None,
            "bytes": excluded_bytes_total if source_available else None,
            "semantics": (
                "difference from state.records; source-read counters are never "
                "fabricated from completion records"
                if source_available else
                "source-read counters unavailable; completion records remain authoritative"
            ),
        },
        "per_worker": per_worker,
    }


def _finalize_stats(stats: dict, state: Any, wall_ms: float,
                    process_cpu_ms: float, telemetry: Optional[_SourceTelemetry] = None,
                    ready_ns: Optional[int] = None, cuda_wait_ms: Optional[float] = None) -> None:
    records = list(getattr(state, "records", getattr(state, "block_records", [])))
    errors = list(getattr(state, "errors", []))
    stats["source_errors"] = errors
    stats["per_read_errors"] = max(int(stats.get("per_read_errors", 0)), len(errors))
    stats["status"] = "ok" if stats["per_read_errors"] == 0 and not errors else "read_errors"
    stats["observed_max_outstanding"] = (
        telemetry.max_inflight if telemetry is not None else getattr(state, "max_outstanding", 0)
    )
    planned_count = len(getattr(state, "planned_items", []))
    submitted_count = int(getattr(state, "submitted", 0))
    completed_count = len(records)
    h2d_completed_count = sum(
        1 for r in records
        if int(r.get("h2d_completed_bytes", 0)) == int(r.get("planned_len", 0))
        and int(r.get("planned_len", 0)) > 0
    )
    stats["planned_block_count"] = planned_count
    stats["submitted_block_count"] = submitted_count
    stats["completed_block_count"] = completed_count
    stats["h2d_completed_block_count"] = h2d_completed_count
    # ``planned_count`` is the total amount of work, not queue depth.  Use the
    # observed submitted-minus-completed peak when available; otherwise make
    # the absence of evidence explicit instead of fabricating a value.
    queue_depth = getattr(state, "max_outstanding", None)
    stats["queue_backlog_max"] = None if queue_depth is None else int(queue_depth)
    stats["submit_count"] = submitted_count
    stats["completion_count"] = completed_count
    stats["bytes_read"] = sum(int(r.get("read_len", r.get("len", 0))) for r in records)
    stats["h2d_submitted_bytes"] = sum(int(r.get("h2d_submitted_bytes", 0)) for r in records)
    stats["h2d_completed_bytes"] = sum(int(r.get("h2d_completed_bytes", 0)) for r in records)
    stats["h2d"]["submitted_bytes"] = stats["h2d_submitted_bytes"]
    stats["h2d"]["completed_bytes"] = stats["h2d_completed_bytes"]
    device_durations = [
        float(r["h2d_device_ms"])
        for r in records
        if r.get("h2d_device_ms") is not None
    ]
    # This is the maximum per-copy CUDA duration, a critical-path statistic;
    # it is intentionally not the sum of overlapping copies.
    stats["h2d"]["h2d_device_ms"] = (
        round(max(device_durations), 4) if device_durations else None
    )
    stats["buffer_pool_wait_ms"] = round(
        getattr(state, "buffer_pool_wait_ms", getattr(state, "buffer_wait_ms_total", 0.0)), 4
    )
    source = telemetry.snapshot() if telemetry is not None else None
    if source is not None:
        stats["source_io"] = source
        stats["per_worker_source_io"] = source["per_worker"]
        stats["source_io_inflight"] = source["inflight"]
        stats["qd_max_source_io_inflight"] = source["max_inflight"]
        start_ns, end_ns = source["earliest_start_ns"], source["latest_end_ns"]
        source_wall = ((end_ns - start_ns) / 1_000_000) if start_ns is not None and end_ns is not None else 0.0
        stats["qd_source_io_wall_ns"] = (
            None if start_ns is None or end_ns is None else int(end_ns - start_ns)
        )
        stats["qd_source_io_wall_ms"] = round(source_wall, 4)
        stats["total_source_wall_ms"] = round(source_wall, 4)
        stats["total_source_wall_ms_deprecated_compat_alias"] = stats["total_source_wall_ms"]
        stats["qd_source_gbps"] = round(
            stats["bytes_read"] / (source_wall * 1e6) if source_wall > 0 else 0.0, 4
        )
        stats["aggregate_gbps"] = stats["qd_source_gbps"]
        ends = [int(r["source_end_ns"]) for r in records if r.get("source_end_ns")]
        if ends and source["earliest_start_ns"] is not None:
            stats["first_completion_latency_ms"] = round(
                (min(ends) - source["earliest_start_ns"]) / 1_000_000, 4
            )
            stats["tail_completion_latency_ms"] = round(
                (max(ends) - min(ends)) / 1_000_000, 4
            )
    else:
        stats["total_source_wall_ms"] = round(wall_ms, 4)
        stats["total_source_wall_ms_deprecated_compat_alias"] = stats["total_source_wall_ms"]
        stats["qd_source_io_wall_ms"] = round(wall_ms, 4)
        stats["qd_source_gbps"] = round(
            stats["bytes_read"] / (wall_ms * 1e6) if wall_ms > 0 else 0.0, 4
        )
        stats["aggregate_gbps"] = stats["qd_source_gbps"]
    reconciliation = _reconcile_worker_records(records, source, state)
    stats["record_reconciliation"] = reconciliation
    # Keep the compact source-I/O view backwards compatible while exposing the
    # authoritative completion count beside each worker's read counters.
    for worker_id, item in reconciliation["per_worker"].items():
        stats["per_worker_source_io"].setdefault(worker_id, {}).update(item)
        if source is not None:
            source["per_worker"].setdefault(worker_id, {}).update(item)
    if not reconciliation["ok"]:
        stats["status"] = "error"
        stats["error"] = reconciliation["reason"]
    stats["steady_state_gbps"] = _steady_state_gbps(records)
    stats["cuda_readiness_wait_ms"] = cuda_wait_ms
    if ready_ns is not None and source is not None and source["earliest_start_ns"] is not None:
        stats["qd_source_to_gpu_ready_ms"] = round(
            (ready_ns - source["earliest_start_ns"]) / 1_000_000, 4
        )
    stats["thread_cpu_ms"] = _thread_cpu_ms()
    stats["process_cpu_ms"] = round(process_cpu_ms, 2)
    stats["blocks"] = records
    stats["byte_reconciliation"] = {
        "planned": stats["planned_bytes"],
        "read": stats["bytes_read"],
        "h2d_submitted": stats["h2d_submitted_bytes"],
        "h2d_completed": stats["h2d_completed_bytes"],
    }
    _sync_canonical_metrics(stats)


def _print_summary(stats: dict, path: str) -> None:
    try:
        print(
            "[v2.clip_qd] summary=" + json.dumps(
                {
                    k: stats.get(k)
                    for k in (
                        "status", "configured_qd", "observed_max_outstanding",
                        "block_bytes", "file_bytes", "n_ranges", "submit_count",
                        "planned_block_count", "submitted_block_count",
                        "completed_block_count", "completion_count", "first_completion_latency_ms",
                        "tail_completion_latency_ms", "qd_source_io_wall_ms",
                        "qd_source_gbps", "qd_max_source_io_inflight",
                        "qd_source_to_gpu_ready_ms", "aggregate_gbps",
                        "steady_state_gbps", "thread_cpu_ms",
                        "process_cpu_ms", "buffer_pool_wait_ms", "per_read_errors",
                        "syscall_mode", "launch_policy",
                    )
                },
                separators=(",", ":"), sort_keys=True,
            ) + f" path={os.path.basename(str(path))}",
            flush=True,
        )
    except Exception:
        pass


def _write_artifact(artifact_path: str, payload: dict) -> None:
    if not artifact_path:
        return
    try:
        with open(artifact_path, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, default=str, indent=1)
    except Exception:
        pass


# ── CPU source reader (E27 mechanism, no CUDA) ────────────────────────────


def _validate_static_records(
    records: list[dict], planned: list[tuple[int, int]], data_start: int,
    total: int, *, gpu: bool,
) -> tuple[bool, str]:
    expected = sorted((int(off), int(ln)) for off, ln in planned)
    actual = sorted((int(r.get("off", -1)), int(r.get("planned_len", -1))) for r in records)
    if len(records) != len(planned) or actual != expected:
        return False, f"block_count_or_identity:{len(records)}:{len(planned)}"
    rel = [(off - int(data_start), off - int(data_start) + ln) for off, ln in expected]
    ok, reason = partition_coverage(rel, int(total))
    if not ok:
        return False, reason
    if any(int(r.get("read_len", r.get("len", 0))) != int(r["planned_len"]) for r in records):
        return False, "read_bytes_reconciliation"
    if gpu and any(int(r.get("h2d_submitted_bytes", 0)) != int(r["planned_len"]) for r in records):
        return False, "h2d_submitted_reconciliation"
    if gpu and any(int(r.get("h2d_completed_bytes", 0)) != int(r["planned_len"]) for r in records):
        return False, "h2d_completed_reconciliation"
    return True, "ok"


def _static_cpu_worker(
    state: _StaticReaderState, slot: bytearray, fd: int, worker_id: int,
    telemetry: _SourceTelemetry,
) -> None:
    try:
        for abs_start, ln in state.regions[worker_id]:
            b0 = time.perf_counter()
            state.submit(worker_id)
            got, started, ended = _timed_read_at(
                fd, memoryview(slot)[:ln], abs_start, worker_id, telemetry
            )
            read_ms = (time.perf_counter() - b0) * 1000.0
            state.record({
                "worker_id": worker_id, "off": int(abs_start),
                "planned_len": int(ln), "read_len": int(got),
                "len": int(got), "source_start_ns": started,
                "source_end_ns": ended, "wall_ms": round(read_ms, 4),
                "gbps": round(got / (read_ms * 1e6) if read_ms > 0 else 0.0, 4),
                "h2d_submitted_bytes": 0, "h2d_completed_bytes": 0,
                "error": None if got == ln else f"short_read got={got} want={ln}",
            })
            if got != ln:
                state.error(worker_id, RuntimeError(f"short_read got={got} want={ln}"))
    except BaseException as exc:
        state.error(worker_id, exc)
    finally:
        state.finalize_worker(worker_id)


def read_file_qd(
    path: str,
    *,
    qd: Optional[int] = None,
    block_mib: Optional[int] = None,
    trace: Any = None,
    launch_policy: str = "method_entry",
    artifact_path: Optional[str] = None,
    collect_bytes: bool = False,
) -> dict[str, Any]:
    """Read the raw safetensors DATA SECTION with static QD workers."""
    if not clip_qd_reader_enabled():
        return {"status": "disabled", "reason": f"{ENABLE_FLAG} not set"}
    qd = _effective_qd(qd)
    block_bytes = _effective_block_bytes(block_mib)
    policy = validate_launch_policy(launch_policy)
    artifact = _effective_artifact_path(artifact_path)
    parsed = parse_safetensors_header(path)
    if parsed.get("status") != "ok":
        return {"status": "error", "reason": parsed.get("reason", "header_unavailable")}
    header, data_start, total = parsed["header"], parsed["data_start"], parsed["total_data_bytes"]
    tensor_map = build_header_tensor_map(header)
    regions = plan_raw_source_regions(data_start, total, block_bytes, qd)
    items = [item for region in regions for item in region]
    cov_ok, cov_reason = partition_coverage(
        [(off - data_start, off - data_start + ln) for off, ln in items], int(total)
    )
    if not cov_ok:
        return {"status": "error", "reason": f"coverage: {cov_reason}"}
    stats = _new_stats(
        qd=qd, block_bytes=block_bytes, file_bytes=int(total),
        n_ranges=len(items), launch_policy=policy, syscall_mode=_syscall_mode(),
    )
    try:
        _st = os.stat(path)
        stats["source_identity"] = {
            "device": getattr(_st, "st_dev", None),
            "inode": getattr(_st, "st_ino", None),
            "size_bytes": int(_st.st_size),
            "mtime_ns": getattr(_st, "st_mtime_ns", None),
        }
    except OSError:
        stats["source_identity"] = None
    clean_lane.mark_qd_start(trace, path=str(path))
    emit_qd_event(trace, EVT_SUBMIT_START, path=str(path), file_bytes=int(total),
                  qd=qd, block_bytes=block_bytes, n_ranges=len(items),
                  launch_policy=policy, syscall_mode=_syscall_mode())
    ledger_event(EVT_SUBMIT_START, path=str(path), file_bytes=int(total),
                 qd=qd, block_bytes=block_bytes, n_ranges=len(items),
                 launch_policy=policy, syscall_mode=_syscall_mode())
    t_cpu0 = time.process_time()
    state = _StaticReaderState(regions)
    telemetry = _SourceTelemetry(qd)
    fds = []
    threads = []
    try:
        flags = os.O_RDONLY | getattr(os, "O_BINARY", 0)
        fds = [os.open(path, flags) for _ in range(qd)]
        slots = [bytearray(block_bytes) for _ in range(qd)]
        for i in range(qd):
            t = threading.Thread(
                target=_static_cpu_worker, args=(state, slots[i], fds[i], i, telemetry),
                daemon=True, name=f"comfymodal-clip-qd-cpu-{i}",
            )
            threads.append(t)
        emit_qd_event(trace, EVT_READ_BEGIN, n_ranges=len(items))
        t_wall0 = time.perf_counter()
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        wall_ms = (time.perf_counter() - t_wall0) * 1000.0
        emit_qd_event(trace, EVT_READ_END, completed=state.completed)
        _finalize_stats(stats, state, wall_ms, (time.process_time() - t_cpu0) * 1000.0, telemetry)
        valid, reason = _validate_static_records(
            state.records, items, data_start, total, gpu=False
        )
        stats["coverage"] = {"ok": valid, "reason": reason}
        if (
            state.errors
            or not valid
            or not stats["record_reconciliation"].get("ok", False)
            or stats["bytes_read"] != int(total)
        ):
            stats["status"] = "error"
            stats["error"] = (
                ";".join(state.errors)
                or stats["record_reconciliation"].get("reason")
                or reason
            )
            return {"status": "error", "reason": stats["error"], "stats": stats}
        # Optional bounded byte collection for local verification.
        collected: dict[int, bytes] = {}
        if collect_bytes and int(total) <= _VERIFY_COLLECT_LIMIT:
            with open(path, "rb") as fh:
                for rec in state.records:
                    off = int(rec["off"])
                    ln = int(rec["len"])
                    fh.seek(off)
                    collected[off] = fh.read(ln)
    except Exception as exc:
        stats["status"] = "error"
        stats["error"] = f"{type(exc).__name__}: {str(exc)[:160]}"
        return {"status": "error", "reason": stats["error"], "stats": stats}
    finally:
        for fd in fds:
            try:
                os.close(fd)
            except Exception:
                pass
    emit_qd_event(trace, EVT_FIRST_COMPLETION,
                  latency_ms=stats["first_completion_latency_ms"])
    emit_qd_event(trace, EVT_LAST_COMPLETION,
                  wall_ms=stats["total_source_wall_ms"],
                  latency_ms=stats["tail_completion_latency_ms"])
    emit_qd_event(trace, EVT_SUBMIT_END, wall_ms=stats["total_source_wall_ms"])
    ledger_event(EVT_FIRST_COMPLETION,
                 latency_ms=stats["first_completion_latency_ms"])
    ledger_event(EVT_LAST_COMPLETION,
                 wall_ms=stats["total_source_wall_ms"],
                 latency_ms=stats["tail_completion_latency_ms"])
    ledger_event(EVT_SUBMIT_END, wall_ms=stats["total_source_wall_ms"])
    ledger_event(
        "clip_qd_stats",
        configured_qd=stats["configured_qd"],
        observed_max_outstanding=stats["observed_max_outstanding"],
        bytes_read=stats["bytes_read"],
        file_bytes=stats["file_bytes"],
        total_source_wall_ms=stats["total_source_wall_ms"],
        aggregate_gbps=stats["aggregate_gbps"],
        steady_state_gbps=stats["steady_state_gbps"],
        buffer_pool_wait_ms=stats["buffer_pool_wait_ms"],
        submit_count=stats["submit_count"],
        completion_count=stats["completion_count"],
        per_read_errors=stats["per_read_errors"],
        launch_policy=stats["launch_policy"],
        syscall_mode=stats["syscall_mode"],
    )
    _write_artifact(artifact, {"stats": stats, "path": str(path)})
    _print_summary(stats, path)
    if collect_bytes and int(total) <= _VERIFY_COLLECT_LIMIT:
        return {"status": "ok", "stats": stats, "tensor_map": tensor_map,
                "bytes": collected}
    return {"status": "ok", "stats": stats, "tensor_map": tensor_map}


# ── GPU pipeline (queued source -> bounded pinned -> async H2D) ───────────


class QdGpuOwner:
    """Owner of the contiguous GPU destination buffer + pinned staging slots.

    Tensors returned by :func:`read_file_qd_gpu` are zero-copy views over
    ``_gpu_buf``; they are only valid while this owner is alive.  ``close()``
    is idempotent and safe only after every view is dead — the same lifetime
    contract as the fastsafetensors FilesBufferOnDevice owner."""

    __slots__ = ("_gpu_buf", "_slots", "_keys", "closed", "device")

    def __init__(self, gpu_buf: Any, slots: list, device: str):
        self._gpu_buf = gpu_buf
        self._slots = slots
        self._keys: list = []
        self.device = str(device)
        self.closed = False

    @property
    def gpu_buf(self) -> Any:
        return self._gpu_buf

    def release_storage(self, *, purge_allocator: bool = False) -> None:
        """Release backing storage without purging the CUDA allocator.

        ``purge_allocator`` is accepted for the common source-owner protocol,
        but the actual allocator purge remains owned by
        :meth:`purge_allocator` so the successful E31 retirement path can
        explicitly request a no-purge release.
        """
        if purge_allocator:
            self.purge_allocator()
            return
        if self.closed:
            return
        self.closed = True
        try:
            del self._slots[:]
        except Exception:
            pass
        self._slots = []
        self._gpu_buf = None

    def purge_allocator(self) -> None:
        if clean_lane.enabled():
            clean_lane.forbidden_activity("allocator_purge")
            self.release_storage()
            return
        self.release_storage()
        try:
            torch.cuda.empty_cache()
        except Exception:
            pass

    def close(self) -> None:
        self.release_storage()


def _wait_event_host(event: Any) -> float:
    if event is None:
        raise RuntimeError("missing_completion_event")
    started = time.perf_counter()
    query = getattr(event, "query", None)
    complete = bool(query()) if callable(query) else False
    if not complete:
        sync = getattr(event, "synchronize", None)
        if not callable(sync):
            raise RuntimeError("completion_event_not_waitable")
        sync()
        if callable(query) and not bool(query()):
            raise RuntimeError("incomplete_completion_event")
    return (time.perf_counter() - started) * 1000.0


def _event_pair(events: Any) -> tuple[Any, Any]:
    """Return ``(start, end)`` while accepting the legacy single-event form."""
    if isinstance(events, (tuple, list)) and len(events) == 2:
        return events[0], events[1]
    return None, events


def _event_elapsed_ms(events: Any) -> Optional[float]:
    """Best-effort CUDA-event duration; unavailable timing is not fatal."""
    start, end = _event_pair(events)
    if start is None or end is None:
        return None
    elapsed = getattr(start, "elapsed_time", None)
    if not callable(elapsed):
        return None
    try:
        value = float(elapsed(end))
    except Exception:
        return None
    return round(value, 4) if math.isfinite(value) and value >= 0.0 else None


def _mark_h2d_complete(record: dict, events: Any) -> None:
    record["h2d_completed_bytes"] = int(record["planned_len"])
    device_ms = _event_elapsed_ms(events)
    if device_ms is not None:
        record["h2d_device_ms"] = device_ms


def _new_cuda_event_pair() -> tuple[Any, Any]:
    """Create the stable untimed completion event used for slot reuse.

    Timing-capable events can abort some restored CUDA runtimes during event
    construction/recording.  QD correctness depends on completion ordering,
    not per-copy timing; device duration therefore remains an optional metric
    and safely falls back to ``None``.
    """
    if clean_lane.enabled():
        # CLEAN_LANE requires a paired host-issue/CUDA-event proof.  If the
        # runtime cannot create timing events the lane fails closed rather than
        # silently downgrading to an un-timed proof.
        return (
            torch.cuda.Event(enable_timing=True),
            torch.cuda.Event(enable_timing=True),
        )
    return (None, torch.cuda.Event(enable_timing=False))


def _static_gpu_worker(
    state: _StaticReaderState, slots: list[Any], slot_pinned: list[bool], events: list[Any], gpu_buf: Any,
    data_start: int, fd: int, worker_id: int, telemetry: _SourceTelemetry,
    stats: dict, h2d_max: list[float], trace: Any = None,
) -> None:
    slot_records: list[Optional[dict]] = [None, None]
    try:
        for index, (abs_start, ln) in enumerate(state.regions[worker_id]):
            slot_index = index % 2
            previous = slot_records[slot_index]
            wait_ms = 0.0
            if previous is not None:
                _, end_event = _event_pair(events[slot_index])
                wait_ms = _wait_event_host(end_event)
                _mark_h2d_complete(previous, events[slot_index])
                state.add_buffer_wait(wait_ms)
                if wait_ms > 0:
                    emit_qd_event(trace, EVT_BUFFER_WAIT, off=int(abs_start), len=int(ln), wait_ms=round(wait_ms, 4))
            rel = int(abs_start) - int(data_start)
            if rel < 0 or rel + int(ln) > int(gpu_buf.numel()):
                raise RuntimeError(f"destination_slice_out_of_range:{rel}:{ln}")
            b0 = time.perf_counter()
            state.submit(worker_id)
            got, started, ended = _timed_read_at(
                fd, memoryview(slots[slot_index].numpy())[:ln], abs_start,
                worker_id, telemetry,
            )
            read_ms = (time.perf_counter() - b0) * 1000.0
            record = {
                "worker_id": worker_id, "off": int(abs_start),
                "planned_len": int(ln), "read_len": int(got), "len": int(got),
                "source_start_ns": started, "source_end_ns": ended,
                "wall_ms": round(read_ms, 4),
                "gbps": round(got / (read_ms * 1e6) if read_ms > 0 else 0.0, 4),
                "h2d_submitted_bytes": 0, "h2d_completed_bytes": 0,
                "h2d_device_ms": None,
                "slot_index": slot_index, "h2d_issue_ms": 0.0, "slot_wait_ms": round(wait_ms, 4),
                "error": None,
            }
            state.record(record)
            if got != ln:
                record["error"] = f"short_read got={got} want={ln}"
                state.error(worker_id, RuntimeError(record["error"]))
                continue
            i0 = time.perf_counter()
            issue_start_ns = time.perf_counter_ns()
            start_event, end_event = _event_pair(events[slot_index])
            try:
                # Record the timing start immediately before the asynchronous
                # copy.  A timing-only failure is tolerated; the end event is
                # still the completion event protecting slot reuse.
                if start_event is not None:
                    try:
                        start_event.record()
                    except Exception:
                        start_event = None
                gpu_buf[rel : rel + ln].copy_(
                    slots[slot_index][:ln], non_blocking=bool(slot_pinned[slot_index])
                )
                end_event.record()
            except BaseException as exc:
                record["error"] = f"h2d_failed:{type(exc).__name__}"
                state.error(worker_id, exc)
                continue
            issue_ms = (time.perf_counter() - i0) * 1000.0
            record["h2d_issue_ms"] = round(issue_ms, 4)
            record["h2d_issue_start_ns"] = issue_start_ns
            record["h2d_submitted_bytes"] = int(ln)
            slot_records[slot_index] = record
            with state._lock:
                stats["h2d"]["copy_count"] += 1
                stats["h2d"]["h2d_host_issue_total_ms"] += issue_ms
                h2d_max[0] = max(h2d_max[0], issue_ms)
    except BaseException as exc:
        state.error(worker_id, exc)
    finally:
        state.finalize_worker(worker_id)


def _fallback_aligned_tensor_from_gpu(
    gpu_buf: Any, dtype_str: str, shape: list, rel_start: int, length: int,
    device: str,
) -> Any:
    dt = _TORCH_DTYPE.get(dtype_str)
    if dt is None:
        raise RuntimeError(f"unsupported dtype {dtype_str}")
    dst = torch.empty(tuple(shape), dtype=dt, device=device)
    dst.view(torch.uint8).copy_(gpu_buf[int(rel_start) : int(rel_start) + int(length)])
    return dst


def read_file_qd_gpu(
    path: str,
    *,
    qd: Optional[int] = None,
    block_mib: Optional[int] = None,
    device: Optional[str] = None,
    trace: Any = None,
    launch_policy: str = "method_entry",
    artifact_path: Optional[str] = None,
) -> dict[str, Any]:
    """Full E30 pipeline: static raw queued pread -> bounded pinned
    staging (qd * 2 x block_bytes) -> async non-blocking H2D into ONE contiguous
    GPU destination buffer -> zero-copy per-tensor views.

    Returns ``{"status": "ok", sd, owner, stats, tensor_map}``.  ``sd``
    values are views over the owner's GPU buffer (zero-copy; owner MUST
    outlive them).  On any failure every resource is released and a
    ``RuntimeError`` is raised — the caller falls back to the existing
    production path unchanged.  Gate OFF -> immediate disabled dict, no
    thread, no allocation, no CUDA touch.
    """
    if not clip_qd_reader_enabled():
        return {"status": "disabled", "reason": f"{ENABLE_FLAG} not set"}
    qd = _effective_qd(qd)
    block_bytes = _effective_block_bytes(block_mib)
    policy = validate_launch_policy(launch_policy)
    artifact = _effective_artifact_path(artifact_path)
    if not torch.cuda.is_available():
        return {"status": "error", "reason": "cuda_unavailable"}
    dev = device or f"cuda:{torch.cuda.current_device()}"
    parsed = parse_safetensors_header(path)
    if parsed.get("status") != "ok":
        return {"status": "error", "reason": parsed.get("reason", "header_unavailable")}
    header, data_start, total = parsed["header"], parsed["data_start"], parsed["total_data_bytes"]
    tensor_map = build_header_tensor_map(header)
    regions = plan_raw_source_regions(data_start, total, block_bytes, qd)
    items = [item for region in regions for item in region]
    cov_ok, cov_reason = partition_coverage(
        [(off - data_start, off - data_start + ln) for off, ln in items], int(total)
    )
    if not cov_ok:
        return {"status": "error", "reason": f"coverage: {cov_reason}"}
    stats = _new_stats(
        qd=qd, block_bytes=block_bytes, file_bytes=int(total),
        n_ranges=len(items), launch_policy=policy, syscall_mode=_syscall_mode(),
    )
    stats["h2d"]["pinned_bytes"] = qd * 2 * block_bytes
    stats["h2d"]["gpu_bytes"] = int(total)
    try:
        _st = os.stat(path)
        stats["source_identity"] = {
            "device": getattr(_st, "st_dev", None),
            "inode": getattr(_st, "st_ino", None),
            "size_bytes": int(_st.st_size),
            "mtime_ns": getattr(_st, "st_mtime_ns", None),
        }
    except OSError:
        stats["source_identity"] = None
    # This is the concrete source-read boundary.  Keep it after planning and
    # source identity capture, but before submit/allocation activity, so the
    # clean-lane interval is measured from an observed seam rather than
    # inferred from a later completion event.
    clean_lane.mark_qd_start(trace, path=str(path))
    rss_before = _rss_mb()
    cuda_before = int(torch.cuda.memory_allocated())
    owner: Optional[QdGpuOwner] = None
    fds: list[int] = []
    emit_qd_event(trace, EVT_SUBMIT_START, path=str(path), file_bytes=int(total),
                  qd=qd, block_bytes=block_bytes, n_ranges=len(items),
                  launch_policy=policy, syscall_mode=_syscall_mode(),
                  device=str(dev))
    ledger_event(EVT_SUBMIT_START, path=str(path), file_bytes=int(total),
                 qd=qd, block_bytes=block_bytes, n_ranges=len(items),
                 launch_policy=policy, syscall_mode=_syscall_mode(),
                 device=str(dev))
    try:
        gpu_buf = torch.empty(int(total), dtype=torch.uint8, device=dev)
        slots: list[list[Any]] = []
        slot_pinned: list[list[bool]] = []
        evs: list[list[Any]] = []
        for _ in range(qd):
            worker_slots = []
            worker_pinned = []
            worker_events = []
            for _slot in range(2):
                try:
                    slot = torch.empty(block_bytes, dtype=torch.uint8, pin_memory=True)
                    worker_slots.append(slot)
                    worker_pinned.append(bool(getattr(slot, "is_pinned", lambda: False)()))
                except Exception:
                    stats["fallback"]["pin_fallback"] += 1
                    slot = torch.empty(block_bytes, dtype=torch.uint8)
                    worker_slots.append(slot)
                    worker_pinned.append(False)
                # Keep one completion event per slot while pairing it with a
                # timing start event.  Untimed fallback preserves the old
                # completion/queue semantics when elapsed timing is absent.
                worker_events.append(_new_cuda_event_pair())
            slots.append(worker_slots)
            slot_pinned.append(worker_pinned)
            evs.append(worker_events)
        stats["h2d"]["pinned_bytes"] = sum(
            block_bytes for worker in slot_pinned for pinned in worker if pinned
        )
        ev_start = ev_end = None
        state = _StaticReaderState(regions)
        telemetry = _SourceTelemetry(qd)
        h2d_max: list[float] = [0.0]
        flags = os.O_RDONLY | getattr(os, "O_BINARY", 0)
        fds = [os.open(path, flags) for _ in range(qd)]
        threads = []
        for i in range(qd):
            t = threading.Thread(
                target=_static_gpu_worker,
                args=(state, slots[i], slot_pinned[i], evs[i], gpu_buf, data_start,
                      fds[i], i, telemetry, stats, h2d_max, trace),
                daemon=True, name=f"comfymodal-clip-qd-gpu-{i}",
            )
            threads.append(t)
        emit_qd_event(trace, EVT_COPY_START, pinned_bytes=stats["h2d"]["pinned_bytes"],
                      gpu_bytes=int(total))
        ledger_event(EVT_COPY_START, pinned_bytes=stats["h2d"]["pinned_bytes"],
                     gpu_bytes=int(total))
        emit_qd_event(trace, EVT_READ_BEGIN, n_ranges=len(items))
        t_wall0 = time.perf_counter()
        t_cpu0 = time.process_time()
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        source_wall_ms = (time.perf_counter() - t_wall0) * 1000.0
        emit_qd_event(trace, EVT_READ_END, completed=state.completed)
        source_valid, source_reason = _validate_static_records(
            state.records, items, data_start, total, gpu=False
        )
        _finalize_stats(
            stats, state, source_wall_ms, (time.process_time() - t_cpu0) * 1000.0,
            telemetry, None, 0.0,
        )
        emit_qd_event(trace, EVT_FIRST_COMPLETION,
                      latency_ms=stats["first_completion_latency_ms"])
        emit_qd_event(trace, EVT_LAST_COMPLETION,
                      wall_ms=stats["qd_source_io_wall_ms"],
                      latency_ms=stats["tail_completion_latency_ms"])
        ledger_event(EVT_FIRST_COMPLETION,
                     latency_ms=stats["first_completion_latency_ms"])
        ledger_event(EVT_LAST_COMPLETION,
                     wall_ms=stats["qd_source_io_wall_ms"],
                     latency_ms=stats["tail_completion_latency_ms"])
        emit_qd_event(trace, EVT_SUBMIT_END, wall_ms=stats["qd_source_io_wall_ms"])
        ledger_event(EVT_SUBMIT_END, wall_ms=stats["qd_source_io_wall_ms"])
        waited_events: set[int] = set()
        for record in state.records:
            if not record.get("h2d_submitted_bytes") or record.get("h2d_completed_bytes"):
                continue
            event = evs[int(record["worker_id"])][int(record["slot_index"])]
            if id(event) not in waited_events:
                try:
                    _, end_event = _event_pair(event)
                    _wait_event_host(end_event)
                    for outstanding in state.records:
                        if (
                            outstanding.get("worker_id") == record.get("worker_id")
                            and outstanding.get("slot_index") == record.get("slot_index")
                            and outstanding.get("h2d_submitted_bytes")
                            and not outstanding.get("h2d_completed_bytes")
                        ):
                            _mark_h2d_complete(outstanding, event)
                except BaseException as exc:
                    state.error(int(record["worker_id"]), exc)
                waited_events.add(id(event))
        final_complete_ns = time.perf_counter_ns()
        _finalize_stats(
            stats, state, source_wall_ms, (time.process_time() - t_cpu0) * 1000.0,
            telemetry, final_complete_ns, 0.0,
        )
        valid, reason = _validate_static_records(
            state.records, items, data_start, total, gpu=True
        )
        stats["coverage"] = {"ok": valid, "reason": reason}
        if (
            state.errors
            or not source_valid
            or not valid
            or not stats["record_reconciliation"].get("ok", False)
            or stats["bytes_read"] != int(total)
        ):
            raise RuntimeError(
                ";".join(state.errors)
                or stats["record_reconciliation"].get("reason")
                or source_reason
                or reason
            )
        issue_starts = [int(r["h2d_issue_start_ns"]) for r in state.records if r.get("h2d_submitted_bytes")]
        if issue_starts:
            stats["qd_h2d_issue_to_final_complete_ms"] = round(
                (final_complete_ns - min(issue_starts)) / 1_000_000, 4
            )
        _sync_canonical_metrics(stats)
        stats["h2d"]["h2d_host_issue_max_ms"] = round(h2d_max[0], 4)
        stats["memory"]["rss_delta_mb"] = (
            None if rss_before is None else round((_rss_mb() or rss_before) - rss_before, 3)
        )
        try:
            stats["memory"]["cuda_alloc_delta_bytes"] = max(
                int(torch.cuda.memory_allocated()) - cuda_before, 0)
        except Exception:
            pass
        emit_qd_event(trace, EVT_COPY_END, h2d_device_ms=stats["h2d"]["h2d_device_ms"],
                      h2d_host_issue_total_ms=stats["h2d"]["h2d_host_issue_total_ms"])
        ledger_event(EVT_COPY_END, h2d_device_ms=stats["h2d"]["h2d_device_ms"],
                     h2d_host_issue_total_ms=stats["h2d"]["h2d_host_issue_total_ms"])
        ledger_event(
            "clip_qd_stats",
            configured_qd=stats["configured_qd"],
            observed_max_outstanding=stats["observed_max_outstanding"],
            bytes_read=stats["bytes_read"],
            file_bytes=stats["file_bytes"],
            total_source_wall_ms=stats["total_source_wall_ms"],
            aggregate_gbps=stats["aggregate_gbps"],
            steady_state_gbps=stats["steady_state_gbps"],
            buffer_pool_wait_ms=stats["buffer_pool_wait_ms"],
            submit_count=stats["submit_count"],
            completion_count=stats["completion_count"],
            per_read_errors=stats["per_read_errors"],
            launch_policy=stats["launch_policy"],
            syscall_mode=stats["syscall_mode"],
        )
        # Zero-copy views (alignment-checked; rare misalignment falls back).
        sd: dict[str, Any] = {}
        for key, dtype_str, shape, rel_start, length in tensor_map:
            dt = _TORCH_DTYPE.get(dtype_str)
            if dt is None:
                raise RuntimeError(f"unsupported dtype {dtype_str} for {key}")
            elem = int(dt.itemsize)
            if (
                int(rel_start) % elem == 0
                and int(length) % elem == 0
                and int(length) == int(math.prod(shape)) * elem
            ):
                try:
                    sd[key] = gpu_buf[rel_start : rel_start + length].view(dt).view(tuple(shape))
                    continue
                except Exception:
                    pass
            stats["fallback"]["alignment_tensor_count"] += 1
            stats["fallback"]["alignment_extra_source_bytes"] += int(length)
            sd[key] = _fallback_aligned_tensor_from_gpu(
                gpu_buf, dtype_str, shape, rel_start, length, dev)
        if stats["per_read_errors"]:
            raise RuntimeError("publication_validation_failed")
        owner = QdGpuOwner(gpu_buf, [slot for worker in slots for slot in worker], dev)
        stats["status"] = "ok"
        emit_qd_event(trace, EVT_OWNER_CREATED, gpu_bytes=int(total),
                      pinned_bytes=stats["h2d"]["pinned_bytes"], tensor_count=len(sd))
        emit_qd_event(trace, EVT_DEVICE_READY, wall_ms=stats["qd_source_to_gpu_ready_ms"],
                      aggregate_gbps=stats["aggregate_gbps"],
                      h2d_device_ms=stats["h2d"]["h2d_device_ms"])
        ledger_event(EVT_DEVICE_READY, wall_ms=stats["qd_source_to_gpu_ready_ms"],
                     aggregate_gbps=stats["aggregate_gbps"],
                     h2d_device_ms=stats["h2d"]["h2d_device_ms"])
        clean_lane.mark_qd_ready(trace, stats, path=str(path), owner=owner)
        ledger_event(EVT_OWNER_CREATED, gpu_bytes=int(total),
                     pinned_bytes=stats["h2d"]["pinned_bytes"], tensor_count=len(sd))
        _write_artifact(artifact, {"stats": stats, "path": str(path)})
        _print_summary(stats, path)
        return {"status": "ok", "sd": sd, "owner": owner, "stats": stats,
                "tensor_map": tensor_map}
    except Exception as exc:
        if owner is not None:
            try:
                owner.release_storage()
            except Exception:
                pass
        stats["status"] = "error"
        stats["error"] = f"{type(exc).__name__}: {str(exc)[:160]}"
        _write_artifact(artifact, {"stats": stats, "path": str(path)})
        raise RuntimeError(stats["error"]) from exc
    finally:
        for fd in fds:
            try:
                os.close(fd)
            except Exception:
                pass


# ── Integration seam (Phase 3/4) ──────────────────────────────────────────
# The speculative lane (speculative_clip_hydration._run_speculative_read) and
# the demand hydrator (clip_fast_hydration_wiring._fastsafe_load) share the
# SAME loader contract: ``(sd, loader, fb)`` where ``loader`` is a
# close()-able owner.  ``clip_qd_load`` exposes the E30 pipeline in that
# exact shape (loader == the QdGpuOwner).  The speculative lane's seam IS
# APPLIED (flag-gated; E30 re-anchor 2026-08-19); the demand hydrator's own
# ``_fastsafe_load`` fallback stays unchanged for flag-OFF runs and for
# speculative-lane misses/failures.


class _QdLoaderFacade:
    """``close()``-compatible loader facade (mirrors the fastsafetensors
    loader the lane expects to close).  Closing the facade closes the QD
    owner — only safe when every tensor view is dead, same as
    FilesBufferOnDevice."""

    __slots__ = ("owner", "closed")

    def __init__(self, owner: QdGpuOwner):
        self.owner = owner
        self.closed = False

    def close(self) -> None:
        if self.closed:
            return
        self.closed = True
        try:
            self.owner.close()
        except Exception:
            pass

    def release_storage(self, *, purge_allocator: bool = False) -> None:
        self.owner.release_storage(purge_allocator=purge_allocator)
        self.closed = True

    def purge_allocator(self) -> None:
        self.owner.purge_allocator()
        self.closed = True

    def get_keys(self) -> list:
        return list(getattr(self.owner, "_keys", []))


def clip_qd_load(
    path: str,
    *,
    qd: Optional[int] = None,
    block_mib: Optional[int] = None,
    trace: Any = None,
    launch_policy: str = "method_entry",
    artifact_path: Optional[str] = None,
) -> tuple[dict, Any, Any]:
    """E30 drop-in for ``_fastsafe_load``: returns ``(sd, loader, fb)``.

    ``loader`` is a close()-compatible facade over the QdGpuOwner; ``fb`` is
    the owner itself (kept for parity with the existing ``(loader, fb)``
    owner tuples the lane stores).  Gate OFF raises ``RuntimeError`` (the
    caller's existing try/except falls back to the normal read, unchanged).
    Emits the E30 take/bind/owner-retained events at the integration points.
    """
    # Comfy's caller may execute this loader inside inference_mode().  QD
    # publication must produce ordinary mutable tensors because the later
    # assign=True bind updates parameter storage in-place.  Keep only the QD
    # allocation/read/publication boundary outside inference mode; this does
    # not clone the state or change the owner/zero-copy lifetime contract.
    with torch.inference_mode(False):
        result = read_file_qd_gpu(
            path, qd=qd, block_mib=block_mib, trace=trace,
            launch_policy=launch_policy, artifact_path=artifact_path,
        )
    if result.get("status") != "ok":
        raise RuntimeError(result.get("reason", "clip_qd_load_failed"))
    sd = result["sd"]
    owner = result["owner"]
    setattr(owner, "_keys", list(sd.keys()))
    loader = _QdLoaderFacade(owner)
    emit_qd_event(trace, EVT_SPEC_RECORD_PUBLISH, path=str(path),
                  tensor_count=len(sd), qd=result["stats"]["configured_qd"],
                  wall_ms=result["stats"]["total_source_wall_ms"])
    emit_qd_event(trace, EVT_TAKE, path=str(path), taken=True,
                  source_side=True)
    emit_qd_event(trace, EVT_BIND, path=str(path), tensor_count=len(sd),
                  device=str(getattr(owner, "device", "")), source_side=True)
    emit_qd_event(trace, EVT_OWNER_RETAINED, path=str(path), source_side=True)
    # E29-ledger ingestion for the ownership contract (canonical axis).
    ledger_event(EVT_SPEC_RECORD_PUBLISH, path=str(path),
                 tensor_count=len(sd), qd=result["stats"]["configured_qd"],
                 wall_ms=result["stats"]["total_source_wall_ms"])
    ledger_event(EVT_TAKE, path=str(path), taken=True, source_side=True)
    ledger_event(EVT_BIND, path=str(path), tensor_count=len(sd),
                 device=str(getattr(owner, "device", "")), source_side=True)
    ledger_event(EVT_OWNER_RETAINED, path=str(path), source_side=True)
    return sd, loader, owner
