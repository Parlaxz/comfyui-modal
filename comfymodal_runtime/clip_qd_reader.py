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
        total = 0
        count = 0
        for key, info in header.items():
            if key == "__metadata__":
                continue
            if not isinstance(info, dict):
                return {**out, "reason": f"tensor_entry_not_dict:{key}"}
            offs = info.get("data_offsets")
            if not isinstance(offs, (list, tuple)) or len(offs) != 2:
                return {**out, "reason": f"bad_data_offsets:{key}"}
            length = int(offs[1]) - int(offs[0])
            if length < 0 or int(offs[0]) < 0:
                return {**out, "reason": f"negative_range:{key}"}
            total += length
            count += 1
        if total <= 0:
            return {**out, "reason": "no_tensor_data"}
        return {
            **out,
            "status": "ok",
            "header": header,
            "data_start": int(data_start),
            "total_data_bytes": int(total),
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


class _ReaderState:
    """Shared work queue + outstanding-read accounting.

    ``outstanding`` counts ranges pulled-but-not-completed; its running max
    is the observed queue depth (the telemetry proof that the configured QD
    was actually reached).  ``queue_backlog_max`` is the deepest remaining
    queue seen by any puller."""

    def __init__(self, items: list):
        self._lock = threading.Lock()
        self._items = list(items)
        self.outstanding = 0
        self.completed = 0
        self.submitted = 0
        self.max_outstanding = 0
        self.queue_backlog_max = len(self._items)
        self.first_completion_mono: Optional[int] = None
        self.last_completion_mono: Optional[int] = None
        self.t_start_mono = time.monotonic_ns()
        self.block_records: list[dict] = []
        self.buffer_wait_ms_total = 0.0

    def pull(self) -> Optional[tuple[int, int]]:
        with self._lock:
            if not self._items:
                return None
            item = self._items.pop()
            self.outstanding += 1
            self.submitted += 1
            self.max_outstanding = max(self.max_outstanding, self.outstanding)
            self.queue_backlog_max = max(self.queue_backlog_max, len(self._items))
            return item

    def complete(self, record: dict) -> None:
        with self._lock:
            self.outstanding -= 1
            self.completed += 1
            now = time.monotonic_ns()
            if self.first_completion_mono is None:
                self.first_completion_mono = now
            self.last_completion_mono = now
            self.block_records.append(record)

    def add_buffer_wait(self, ms: float) -> None:
        with self._lock:
            self.buffer_wait_ms_total += ms


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
        "queue_backlog_max": 0,
        "block_bytes": int(block_bytes),
        "file_bytes": int(file_bytes),
        "bytes_read": 0,
        "n_ranges": int(n_ranges),
        "submit_count": 0,
        "completion_count": 0,
        "first_completion_latency_ms": None,
        "tail_completion_latency_ms": None,
        "total_source_wall_ms": None,
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
            "h2d_host_issue_total_ms": 0.0,
            "h2d_host_issue_max_ms": 0.0,
            "h2d_device_ms": None,
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
    }


def _finalize_stats(stats: dict, state: _ReaderState, wall_ms: float,
                    process_cpu_ms: float) -> None:
    stats["status"] = "ok" if stats["per_read_errors"] == 0 else "read_errors"
    stats["observed_max_outstanding"] = state.max_outstanding
    stats["queue_backlog_max"] = state.queue_backlog_max
    stats["submit_count"] = state.submitted
    stats["completion_count"] = state.completed
    stats["bytes_read"] = sum(int(r.get("len", 0)) for r in state.block_records)
    stats["buffer_pool_wait_ms"] = round(state.buffer_wait_ms_total, 4)
    stats["total_source_wall_ms"] = round(wall_ms, 4)
    stats["aggregate_gbps"] = round(
        stats["file_bytes"] / (wall_ms * 1e6) if wall_ms > 0 else 0.0, 4
    )
    stats["steady_state_gbps"] = _steady_state_gbps(state.block_records)
    if state.first_completion_mono is not None:
        stats["first_completion_latency_ms"] = round(
            (state.first_completion_mono - state.t_start_mono) / 1_000_000, 4
        )
    if state.first_completion_mono is not None and state.last_completion_mono is not None:
        stats["tail_completion_latency_ms"] = round(
            (state.last_completion_mono - state.first_completion_mono) / 1_000_000, 4
        )
    stats["thread_cpu_ms"] = _thread_cpu_ms()
    stats["process_cpu_ms"] = round(process_cpu_ms, 2)
    stats["blocks"] = state.block_records


def _print_summary(stats: dict, path: str) -> None:
    try:
        print(
            "[v2.clip_qd] summary=" + json.dumps(
                {
                    k: stats.get(k)
                    for k in (
                        "status", "configured_qd", "observed_max_outstanding",
                        "block_bytes", "file_bytes", "n_ranges", "submit_count",
                        "completion_count", "first_completion_latency_ms",
                        "tail_completion_latency_ms", "total_source_wall_ms",
                        "aggregate_gbps", "steady_state_gbps", "thread_cpu_ms",
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


def _cpu_worker(path: str, state: _ReaderState, slot: bytearray, fd: int) -> None:
    while True:
        item = state.pull()
        if item is None:
            return
        abs_start, ln = item
        b0 = time.perf_counter()
        got = _read_at(fd, memoryview(slot)[:ln], abs_start)
        wall_ms = (time.perf_counter() - b0) * 1000.0
        state.complete({
            "off": int(abs_start),
            "len": int(got),
            "wall_ms": round(wall_ms, 4),
            "gbps": round(got / (wall_ms * 1e6) if wall_ms > 0 else 0.0, 4),
            "error": None if got == ln else f"short_read got={got} want={ln}",
        })


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
    """E27-mechanism CPU source read: *qd* worker threads, per-worker
    buffers, tensor-aligned blocks, preadv/pread/lseek syscalls.

    Returns ``{"status": "ok", stats, tensor_map}`` (or a
    ``{"status": "disabled"|"error", reason}`` dict).  Source-only — no CUDA,
    no H2D.  When the gate is OFF this returns before touching the file.
    """
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
    items, tensor_map, cov = build_block_items(header, data_start, block_bytes)
    if not cov["ok"]:
        return {"status": "error", "reason": f"coverage: {cov['reason']}"}
    stats = _new_stats(
        qd=qd, block_bytes=block_bytes, file_bytes=int(total),
        n_ranges=len(items), launch_policy=policy, syscall_mode=_syscall_mode(),
    )
    emit_qd_event(trace, EVT_SUBMIT_START, path=str(path), file_bytes=int(total),
                  qd=qd, block_bytes=block_bytes, n_ranges=len(items),
                  launch_policy=policy, syscall_mode=_syscall_mode())
    ledger_event(EVT_SUBMIT_START, path=str(path), file_bytes=int(total),
                 qd=qd, block_bytes=block_bytes, n_ranges=len(items),
                 launch_policy=policy, syscall_mode=_syscall_mode())
    t_cpu0 = time.process_time()
    state = _ReaderState(items)
    fds = []
    threads = []
    try:
        flags = os.O_RDONLY | getattr(os, "O_BINARY", 0)
        fds = [os.open(path, flags) for _ in range(qd)]
        slots = [bytearray(block_bytes) for _ in range(qd)]
        for i in range(qd):
            t = threading.Thread(
                target=_cpu_worker, args=(path, state, slots[i], fds[i]),
                daemon=True, name=f"comfymodal-clip-qd-cpu-{i}",
            )
            threads.append(t)
        t_wall0 = time.perf_counter()
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        wall_ms = (time.perf_counter() - t_wall0) * 1000.0
        _finalize_stats(stats, state, wall_ms, (time.process_time() - t_cpu0) * 1000.0)
        # Optional bounded byte collection for local verification.
        collected: dict[int, bytes] = {}
        if collect_bytes and int(total) <= _VERIFY_COLLECT_LIMIT:
            with open(path, "rb") as fh:
                for rec in state.block_records:
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
    emit_qd_event(trace, EVT_READ_BEGIN, n_ranges=len(items))
    emit_qd_event(trace, EVT_READ_END, completed=stats["completion_count"])
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

    def close(self) -> None:
        if self.closed:
            return
        self.closed = True
        try:
            del self._slots[:]
        except Exception:
            pass
        self._slots = []
        self._gpu_buf = None
        try:
            torch.cuda.empty_cache()
        except Exception:
            pass


def _gpu_worker(path: str, state: _ReaderState, slot: Any, slot_ev: Any,
                gpu_buf: Any, data_start: int, fd: int, stats: dict,
                h2d_max: list, trace: Any = None) -> None:
    while True:
        item = state.pull()
        if item is None:
            return
        abs_start, ln = item
        rel = int(abs_start) - int(data_start)
        wait_ms = 0.0
        if slot_ev is not None:
            w0 = time.perf_counter()
            try:
                slot_ev.wait()
            except Exception:
                pass
            wait_ms = (time.perf_counter() - w0) * 1000.0
            if wait_ms > 1.0:
                emit_qd_event(
                    trace, EVT_BUFFER_WAIT,
                    off=int(abs_start), len=int(ln),
                    wait_ms=round(wait_ms, 4),
                    slot_wait_ms=round(wait_ms, 4),
                )
                ledger_event(
                    EVT_BUFFER_WAIT,
                    off=int(abs_start), len=int(ln),
                    wait_ms=round(wait_ms, 4),
                )
        if wait_ms > 0:
            state.add_buffer_wait(wait_ms)
        b0 = time.perf_counter()
        mv = memoryview(slot.numpy())[:ln]
        got = _read_at(fd, mv, abs_start)
        read_ms = (time.perf_counter() - b0) * 1000.0
        if got != ln:
            stats["per_read_errors"] += 1
            state.complete({
                "off": int(abs_start), "len": int(got),
                "wall_ms": round(read_ms, 4),
                "gbps": 0.0,
                "error": f"short_read got={got} want={ln}",
            })
            continue
        i0 = time.perf_counter()
        try:
            gpu_buf[rel : rel + ln].copy_(slot[:ln], non_blocking=True)
        except Exception as exc:
            stats["per_read_errors"] += 1
            state.complete({
                "off": int(abs_start), "len": int(ln),
                "wall_ms": round(read_ms, 4), "gbps": 0.0,
                "error": f"h2d_failed:{type(exc).__name__}",
            })
            continue
        issue_ms = (time.perf_counter() - i0) * 1000.0
        if slot_ev is not None:
            try:
                slot_ev.record()
            except Exception:
                pass
        stats["h2d"]["copy_count"] += 1
        stats["h2d"]["h2d_host_issue_total_ms"] += issue_ms
        if issue_ms > h2d_max[0]:
            h2d_max[0] = issue_ms
        state.complete({
            "off": int(abs_start), "len": int(got),
            "wall_ms": round(read_ms, 4),
            "gbps": round(got / (read_ms * 1e6) if read_ms > 0 else 0.0, 4),
            "h2d_issue_ms": round(issue_ms, 4),
            "slot_wait_ms": round(wait_ms, 4),
            "error": None,
        })


def _fallback_aligned_tensor_read(path: str, key: str, dtype_str: str,
                                  shape: list, rel_start: int, length: int,
                                  device: str) -> Any:
    """Misaligned-tensor fallback: re-read the tensor's exact bytes from the
    file into a fresh pinned buffer and copy into a fresh GPU tensor.  Rare
    (standard safetensors writers 8-byte align), exact, and counted in
    ``stats["fallback"]``."""
    dt = _TORCH_DTYPE.get(dtype_str)
    if dt is None:
        raise RuntimeError(f"unsupported dtype {dtype_str} for {key}")
    tmp = torch.empty(length, dtype=torch.uint8, pin_memory=True)
    try:
        flags = os.O_RDONLY | getattr(os, "O_BINARY", 0)
        with os.fdopen(os.open(path, flags), "rb") as fh:
            # Read the absolute file range.
            abs_start = _absolute_of(path, rel_start)
            fh.seek(abs_start)
            buf = fh.read(length)
        tmp_view = memoryview(tmp.numpy())
        tmp_view[:] = buf
    finally:
        pass
    dst = torch.empty(tuple(shape), dtype=dt, device=device)
    dst.copy_(tmp[:length].view(dt).view(shape), non_blocking=True)
    return dst


def _absolute_of(path: str, rel_start: int) -> int:
    parsed = parse_safetensors_header(path)
    return int(parsed["data_start"]) + int(rel_start)


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
    """Full E30 pipeline: tensor-aligned queued pread -> bounded pinned
    staging (qd x block_bytes) -> async non-blocking H2D into ONE contiguous
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
    items, tensor_map, cov = build_block_items(header, data_start, block_bytes)
    if not cov["ok"]:
        return {"status": "error", "reason": f"coverage: {cov['reason']}"}
    stats = _new_stats(
        qd=qd, block_bytes=block_bytes, file_bytes=int(total),
        n_ranges=len(items), launch_policy=policy, syscall_mode=_syscall_mode(),
    )
    stats["h2d"]["pinned_bytes"] = qd * block_bytes
    stats["h2d"]["gpu_bytes"] = int(total)
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
        slots: list[Any] = []
        evs: list[Any] = []
        for _ in range(qd):
            try:
                slot = torch.empty(block_bytes, dtype=torch.uint8, pin_memory=True)
            except Exception:
                stats["fallback"]["pin_fallback"] += 1
                slot = torch.empty(block_bytes, dtype=torch.uint8)
            slots.append(slot)
            try:
                evs.append(torch.cuda.Event(enable_timing=False))
            except Exception:
                evs.append(None)
        try:
            ev_start = torch.cuda.Event(enable_timing=True)
            ev_end = torch.cuda.Event(enable_timing=True)
        except Exception:
            ev_start = ev_end = None
        state = _ReaderState(items)
        h2d_max: list[float] = [0.0]
        flags = os.O_RDONLY | getattr(os, "O_BINARY", 0)
        fds = [os.open(path, flags) for _ in range(qd)]
        threads = []
        for i in range(qd):
            t = threading.Thread(
                target=_gpu_worker,
                args=(path, state, slots[i], evs[i], gpu_buf, data_start,
                      fds[i], stats, h2d_max, trace),
                daemon=True, name=f"comfymodal-clip-qd-gpu-{i}",
            )
            threads.append(t)
        emit_qd_event(trace, EVT_COPY_START, pinned_bytes=qd * block_bytes,
                      gpu_bytes=int(total))
        ledger_event(EVT_COPY_START, pinned_bytes=qd * block_bytes,
                     gpu_bytes=int(total))
        t_wall0 = time.perf_counter()
        t_cpu0 = time.process_time()
        if ev_start is not None:
            ev_start.record()
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        if ev_end is not None:
            ev_end.record()
        torch.cuda.synchronize()
        wall_ms = (time.perf_counter() - t_wall0) * 1000.0
        _finalize_stats(stats, state, wall_ms, (time.process_time() - t_cpu0) * 1000.0)
        stats["h2d"]["h2d_host_issue_max_ms"] = round(h2d_max[0], 4)
        if ev_start is not None and ev_end is not None:
            try:
                stats["h2d"]["h2d_device_ms"] = round(
                    float(ev_start.elapsed_time(ev_end)), 4)
            except Exception:
                pass
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
            sd[key] = _fallback_aligned_tensor_read(
                path, key, dtype_str, shape, rel_start, length, dev)
        owner = QdGpuOwner(gpu_buf, slots, dev)
        stats["status"] = "ok" if stats["per_read_errors"] == 0 else "read_errors"
        emit_qd_event(trace, EVT_OWNER_CREATED, gpu_bytes=int(total),
                      pinned_bytes=qd * block_bytes, tensor_count=len(sd))
        emit_qd_event(trace, EVT_DEVICE_READY, wall_ms=stats["total_source_wall_ms"],
                      aggregate_gbps=stats["aggregate_gbps"],
                      h2d_device_ms=stats["h2d"]["h2d_device_ms"])
        ledger_event(EVT_DEVICE_READY, wall_ms=stats["total_source_wall_ms"],
                     aggregate_gbps=stats["aggregate_gbps"],
                     h2d_device_ms=stats["h2d"]["h2d_device_ms"])
        ledger_event(EVT_OWNER_CREATED, gpu_bytes=int(total),
                     pinned_bytes=qd * block_bytes, tensor_count=len(sd))
        emit_qd_event(trace, EVT_READ_BEGIN, n_ranges=len(items))
        emit_qd_event(trace, EVT_READ_END, completed=stats["completion_count"])
        emit_qd_event(trace, EVT_FIRST_COMPLETION,
                      latency_ms=stats["first_completion_latency_ms"])
        ledger_event(EVT_FIRST_COMPLETION,
                     latency_ms=stats["first_completion_latency_ms"])
        emit_qd_event(trace, EVT_LAST_COMPLETION,
                      wall_ms=stats["total_source_wall_ms"])
        ledger_event(EVT_LAST_COMPLETION,
                     wall_ms=stats["total_source_wall_ms"])
        emit_qd_event(trace, EVT_SUBMIT_END, wall_ms=stats["total_source_wall_ms"])
        ledger_event(EVT_SUBMIT_END, wall_ms=stats["total_source_wall_ms"])
        _write_artifact(artifact, {"stats": stats, "path": str(path)})
        _print_summary(stats, path)
        return {"status": "ok", "sd": sd, "owner": owner, "stats": stats,
                "tensor_map": tensor_map}
    except Exception as exc:
        if owner is not None:
            try:
                owner.close()
            except Exception:
                pass
        stats["status"] = "error"
        stats["error"] = f"{type(exc).__name__}: {str(exc)[:160]}"
        _write_artifact(artifact, {"stats": stats, "path": str(path)})
        try:
            torch.cuda.empty_cache()
        except Exception:
            pass
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
