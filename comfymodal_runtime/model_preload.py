"""UNET/CLIP/VAE restore preparation with prefill filtering and execution-phase overlap.

Controls:
  COMFYMODAL_V2_PREFILL_LANES — critical|all|none (default critical)
  COMFYMODAL_V2_PREFILL_WAIT_FOR_UNET — legacy barrier (default off)
  COMFYMODAL_V2_DEEP_MODEL_DIAG=1 — enable deep /proc, faults, open/mmap/safetensors
  COMFYMODAL_V2_PAGE_READINESS_MODE — off (default) | willneed
      Enables the synchronous native page-readiness candidate
      (libc madvise MADV_WILLNEED advisory) immediately before the CLIP
      prefill encode loop and before the first request-scoped graph UNET
      activation.  Off by default so production behavior is unchanged.
      ``status=ok`` reports the advisory was accepted — it does NOT
      guarantee physical pages are resident.
"""

from __future__ import annotations

import enum
import functools
import math
import os
import platform
import threading
import time
import uuid
from contextlib import contextmanager
from contextvars import ContextVar
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from threading import Condition, Event, RLock, Thread
from collections.abc import Mapping
from typing import Any, Callable, Iterator

from .contracts import ModelRestoreKey, PrefillKey, stable_hash
from .env import env_flag
from .clip_conditioning_cache import (
    conditioning_cache_key_summary,
    get_exact_conditioning_cache,
    log_conditioning_cache_decision,
)
from .cpu_snapshot_models import (
    collect_unet_runtime_state,
    page_readiness_mode,
    advise_storage_pages_willneed,
    _PAGE_READINESS_MODE_WILLNEED,
)
from .trace import RuntimeTrace
from .unet_forward_probe import (
    emit_post_load_models_gpu_event,
    install_nextdit_forward_pre_hook,
    register_unet_forward_probe,
    set_unet_gpu_demand_start,
    _has_registered_unet_in_models,
)

# ── Prefill lane mode ─────────────────────────────────────────────────
# Controls which CLIPTextEncode entries are pre-encoded during restore.
#   "critical": only role=positive/negative
#   "all":      encode all entries (previous behavior)
#   "none":     skip prefill entirely
_PREFILL_LANE_MODE: str = os.environ.get(
    "COMFYMODAL_V2_PREFILL_LANES", "critical"
).strip().lower()
# Validate: only "critical", "all", "none" are accepted.  Anything else
# is treated as a safe default ("critical") so that invalid env values
# never bypass the safety gate.
if _PREFILL_LANE_MODE not in ("critical", "all", "none"):
    _PREFILL_LANE_MODE = "critical"
_PREFILL_CRITICAL_ROLES: frozenset[str] = frozenset({"positive", "negative"})

# ── Page-fault delta tracking for model-path instrumentation ─────
# Uses resource.getrusage (RUSAGE_SELF) to measure major/minor page
# faults around actual first access to restored CLIP/UNET CPU state.
# Deliberately wraps the OUTERMOST invocation of each operation so
# inner nested calls do not double-count.

_PAGEFAULT_TRACKING: bool = env_flag("COMFYMODAL_V2_PAGEFAULT_TRACKING", default=True)


@dataclass
class _PageFaultSnapshot:
    """Snapshot of process page-fault counters at a given moment.
    Uses resource.getrusage (Linux-only; returns zeros on other platforms).
    """
    major: int = 0
    minor: int = 0

    @classmethod
    def now(cls) -> "_PageFaultSnapshot":
        try:
            import resource as _r
            ru = _r.getrusage(_r.RUSAGE_SELF)
            return cls(major=ru.ru_majflt, minor=ru.ru_minflt)
        except Exception:
            return cls()


def _pagefault_delta(before: _PageFaultSnapshot, after: _PageFaultSnapshot) -> dict[str, int]:
    """Return major/minor fault deltas from two snapshots."""
    return {
        "major_faults": max(0, after.major - before.major),
        "minor_faults": max(0, after.minor - before.minor),
    }


# ── V2 prefill overlap: wait-for-UNET policy ─────────────────────
# Default behaviour (recommended): prefill waits for CLIP only and
# begins encoding without blocking on UNET.  The UNET restore runs
# in parallel and its GPU commit is serialised through the mutation
# lane — safe because ``load_models_gpu`` acquires the lane before
# touching GPU memory.
#
# Set to ``1`` / ``true`` / ``yes`` to restore the old barrier that
# waits for UNET *before* CLIP, putting 5.7-6.3s Qwen-encode on the
# critical path (useful for debugging or regression isolation).
_V2_PREFILL_WAIT_FOR_UNET: bool = env_flag("COMFYMODAL_V2_PREFILL_WAIT_FOR_UNET")


# ── Canonical lane vocabulary ─────────────────────────────────────────

_LANE_TO_CANONICAL: dict[str, str] = {
    "unet": "UNET",
    "clip": "CLIP",
    "vae": "VAE",
    "prefill": "prefill",
    "execution_prefill": "prefill",
}
"""Maps internal ``_submit`` lane names to canonical identifiers."""

# ── V2 restore correlation identity ──────────────────────────────────
_LATEST_RESTORED_INSTANCE_ID: str = ""
_LATEST_RESTORE_SESSION_ID: str = ""
"""Module-level latest restored_instance_id.  Set by restore() after
snapshot restoration; read by background worker and graph-entry paths."""

_LATEST_RESTORE_RETURN_MARKER: dict[str, Any] | None = None
"""Set immediately before ``restore()`` returns with wall/monotonic time,
both restore IDs, MODAL_TASK_ID, and PID.  Read by ``run_plan_stream`` method
entry for method-entry-gap computation."""

_DIAGNOSTIC_FLAG: bool = env_flag("COMFYMODAL_V2_DEEP_MODEL_DIAG")
"""Controls deep diagnostics (proc/pagefault/open/mmap/safetensors detail).
``False`` by default — when disabled, only lightweight identity, restore
total, CLIP read/ready, background submitted/ready, graph demand/wait,
and method gaps are reported."""

# ── Slow model-read threshold ─────────────────────────────────────────
# When a CLIP load_torch_file or background-UNET active read exceeds this
# wall-time threshold (ms), a detailed ``[v2.slow_model_read]`` diagnostic
# line is emitted with counter deltas, /proc/meminfo, and cgroup stats.
# Invalid/negative/non-finite values fall back safely to 3000.


def _parse_slow_read_threshold() -> float:
    """Parse COMFYMODAL_V2_SLOW_READ_THRESHOLD_MS with safe fallback to 3000."""
    try:
        _val = os.environ.get("COMFYMODAL_V2_SLOW_READ_THRESHOLD_MS", "3000")
        _parsed = float(_val)
        if _parsed >= 0 and math.isfinite(_parsed):
            return _parsed
    except Exception:
        pass
    return 3000.0


_SLOW_READ_THRESHOLD_MS: float = _parse_slow_read_threshold()

# ── Activation diagnostics state ────────────────────────────────────
# Three-function API: begin_activation_diagnostics(request_id) creates a
# state dict, get_activation_diagnostics() returns it, end_activation_diagnostics(token)
# clears it.  Keys: request_id, clip_encode_calls (list), gpu_load_calls (list),
# model_patcher_calls (list), first_forward (dict), residency (dict).
# No tensors/models/paths.

_ACTIVATION_DIAGNOSTIC_STATE: ContextVar[dict[str, Any] | None] = ContextVar(
    "comfymodal_activation_diagnostic_state", default=None
)


def begin_activation_diagnostics(
    request_id: str,
    *,
    cpu_snapshot_active: bool | None = None,
    execution_prefill_scheduled: bool | None = None,
) -> "contextvars.Token":
    """Create and set a fresh activation-diagnostic state dict.
    Returns the ContextVar token for end_activation_diagnostics()."""
    state: dict[str, Any] = {
        "request_id": request_id,
        "clip_encode_calls": [],
        "gpu_load_calls": [],
        "model_patcher_calls": [],
        "first_forward": {},
        "residency": {},
    }
    if cpu_snapshot_active is not None:
        state["cpu_snapshot_active"] = bool(cpu_snapshot_active)
    if execution_prefill_scheduled is not None:
        state["execution_prefill_scheduled"] = bool(execution_prefill_scheduled)
    return _ACTIVATION_DIAGNOSTIC_STATE.set(state)


def get_activation_diagnostics() -> dict[str, Any] | None:
    """Return the current activation-diagnostic state dict or None."""
    return _ACTIVATION_DIAGNOSTIC_STATE.get()


def end_activation_diagnostics(token: "contextvars.Token") -> dict[str, Any]:
    """Reset the ContextVar and return the final state dict (empty dict fallback)."""
    try:
        state = _ACTIVATION_DIAGNOSTIC_STATE.get()
        return state if state is not None else {}
    finally:
        _ACTIVATION_DIAGNOSTIC_STATE.reset(token)


def _record_clip_encode(
    caller: str, clip: Any, text: str, callback: Callable[[], Any],
    *,
    _explicit_state: dict[str, Any] | None = None,
) -> Any:
    """Record a CLIP encode call into activation diagnostics.

    Invokes *callback* in try and records metadata in finally.
    Emits ``clip_encode_diagnostic`` trace event.
    When *_explicit_state* is provided (e.g. from a worker thread where
    ContextVars do not propagate), records into that dict instead of the
    ContextVar state.
    """
    start_wall = time.monotonic_ns()
    start_thread = time.thread_time_ns() if hasattr(time, "thread_time_ns") else 0
    start_process = time.process_time_ns() if hasattr(time, "process_time_ns") else 0
    try:
        result = callback()
        return result
    finally:
        end_wall = time.monotonic_ns()
        end_thread = time.thread_time_ns() if hasattr(time, "thread_time_ns") else 0
        end_process = time.process_time_ns() if hasattr(time, "process_time_ns") else 0
        record = {
            "caller": caller,
            "clip_object_id": str(id(clip)),
            "text_hash": stable_hash(str(text))[:16],
            "text_length": len(str(text)),
            "start_monotonic_ns": start_wall,
            "end_monotonic_ns": end_wall,
            "wall_ms": round((end_wall - start_wall) / 1_000_000, 3),
            "thread_cpu_ms": round((end_thread - start_thread) / 1_000_000, 3),
            "process_cpu_ms": round((end_process - start_process) / 1_000_000, 3),
        }
        if _explicit_state is not None:
            _explicit_state.setdefault("clip_encode_calls", []).append(record)
            _explicit_state["clip_encode_instrumentation_attached"] = True
        else:
            state = _ACTIVATION_DIAGNOSTIC_STATE.get()
            if state is not None:
                state["clip_encode_calls"].append(record)
                state["clip_encode_instrumentation_attached"] = True
        request_trace = _ACTIVE_REQUEST_TRACE.get()
        if request_trace is not None:
            request_trace.emit("clip_encode_diagnostic", phase="execution", metadata=dict(record))


# ── CLIP execution-prefill phase attribution (Phase B diagnostics) ───
# One per-request reconciliation record partitions the prefill worker
# lifetime into non-overlapping stages:
#
#   prefill_total_ms = queue_ms + readiness_ms + encode_ms + completion_ms
#                      + unattributed_ms
#
# ``unattributed_ms`` is the COMPUTED accounting error (never hidden): the
# difference between the measured total and the sum of the measured child
# stages.  A boundary that was never recorded is reported truthfully as
# ``None`` (never silently zeroed) and flips ``reconciliation_status`` to
# ``"incomplete"``.

# ── Event names for the prefill lifecycle (single source of truth) ────
_EVENT_SUBMISSION = "execution_prefill_scheduled"
_EVENT_WORKER_START = "execution_prefill_submitted"
_EVENT_READINESS_START = "execution_prefill_readiness_start"
_EVENT_READINESS_END = "execution_prefill_readiness_end"
_EVENT_ENCODE_START = "execution_prefill_encode_start"
_EVENT_ENCODE_END = "execution_prefill_encode_end"
_EVENT_COMPLETED = "execution_prefill_completed"
_EVENT_FAILED = "execution_prefill_failed"
_EVENT_GRAPH_WAIT_START = "graph_prefill_wait_start"
_EVENT_GRAPH_WAIT_END = "graph_prefill_wait_end"
_EVENT_RECONCILIATION = "clip_prefill_reconciliation"

# ── Event names for synchronous native page-readiness (Phase B candidate) ──
# stage=clip_prefill: emitted between the CLIP readiness wait and the encode
# loop when COMFYMODAL_V2_PAGE_READINESS_MODE=willneed.  stage=unet_activation:
# emitted immediately before the first request-scoped graph load_models_gpu call.
_EVENT_PAGE_READINESS_START = "execution_prefill_page_readiness_start"
_EVENT_PAGE_READINESS_END = "execution_prefill_page_readiness_end"
_EVENT_UNET_PAGE_READINESS = "unet_activation_page_readiness"


def _capture_torch_thread_counts() -> dict[str, Any]:
    """Best-effort torch intraop/interop thread counts (lazy import).

    Returns ``torch_available`` plus intraop/interop counts (None when
    torch is absent or the accessor is unavailable).  Never raises.
    """
    result: dict[str, Any] = {
        "torch_available": False,
        "torch_intraop_threads": None,
        "torch_interop_threads": None,
    }
    try:
        import torch
        result["torch_available"] = True
        result["torch_intraop_threads"] = int(torch.get_num_threads())
        result["torch_interop_threads"] = int(torch.get_num_interop_threads())
    except Exception:
        pass
    return result


def _capture_native_thread_count() -> int | None:
    """Native thread count: ``/proc/self/status Threads:`` on Linux, else
    ``len(threading.enumerate())``.  Never raises."""
    if platform.system() == "Linux":
        try:
            with open("/proc/self/status") as _f:
                for _line in _f:
                    if _line.startswith("Threads:"):
                        return int(_line.split()[1])
        except Exception:
            pass
    try:
        return len(threading.enumerate())
    except Exception:
        return None


def _capture_phase_counters() -> dict[str, Any]:
    """One phase snapshot for prefill attribution.

    Returns a flat JSON-safe dict.  Wall / thread / process clocks and the
    native tid are always present; ``rusage`` (RUSAGE_THREAD, Linux),
    ``io`` (per-tid ``/proc/self/task/<tid>/io``, Linux), ``torch``, and
    ``native_thread_count`` are attempted natively and reported truthfully
    as ``None`` when unavailable.
    """
    return {
        "mono_ns": time.monotonic_ns(),
        "thread_time_ns": time.thread_time_ns() if hasattr(time, "thread_time_ns") else None,
        "process_time_ns": time.process_time_ns() if hasattr(time, "process_time_ns") else None,
        "native_tid": _capture_tid(),
        "native_thread_count": _capture_native_thread_count(),
        "rusage": _capture_rusage_thread_snapshot(),
        "io": _capture_proc_tid_io_snapshot(),
        "torch": _capture_torch_thread_counts(),
    }


def _phase_counter_deltas(
    before: dict[str, Any] | None,
    after: dict[str, Any] | None,
) -> dict[str, Any]:
    """Compute deltas between two ``_capture_phase_counters()`` snapshots.

    Wall and process CPU deltas are valid whenever both snapshots exist.
    Thread-bounded deltas (thread CPU, RUSAGE_THREAD minor/major faults and
    voluntary/involuntary context switches, per-tid io) are only valid when
    the native thread id matches; otherwise they are reported as ``None``
    (truthful, never fabricated).
    """
    if not before or not after:
        return {}
    result: dict[str, Any] = {}
    _same_tid = (
        isinstance(before.get("native_tid"), int)
        and before.get("native_tid") == after.get("native_tid")
    )

    b_mono = before.get("mono_ns")
    a_mono = after.get("mono_ns")
    if isinstance(b_mono, int) and isinstance(a_mono, int):
        result["wall_ms"] = round(max(0, a_mono - b_mono) / 1_000_000, 3)

    b_tt = before.get("thread_time_ns")
    a_tt = after.get("thread_time_ns")
    if _same_tid and isinstance(b_tt, int) and isinstance(a_tt, int):
        result["thread_cpu_ms"] = round(max(0, a_tt - b_tt) / 1_000_000, 3)
    else:
        result["thread_cpu_ms"] = None

    b_pt = before.get("process_time_ns")
    a_pt = after.get("process_time_ns")
    if isinstance(b_pt, int) and isinstance(a_pt, int):
        result["process_cpu_ms"] = round(max(0, a_pt - b_pt) / 1_000_000, 3)
    else:
        result["process_cpu_ms"] = None

    if _same_tid:
        _ru = _compute_rusage_deltas(before.get("rusage"), after.get("rusage"))
        result["minor_faults"] = _ru.get("minflt") if _ru else None
        result["major_faults"] = _ru.get("majflt") if _ru else None
        result["voluntary_context_switches"] = _ru.get("nvcsw") if _ru else None
        result["involuntary_context_switches"] = _ru.get("nivcsw") if _ru else None
        _io = _compute_io_deltas(before.get("io"), after.get("io"))
        result["io_read_bytes"] = _io.get("read_bytes") if _io else None
        result["io_write_bytes"] = _io.get("write_bytes") if _io else None
    else:
        result["minor_faults"] = None
        result["major_faults"] = None
        result["voluntary_context_switches"] = None
        result["involuntary_context_switches"] = None
        result["io_read_bytes"] = None
        result["io_write_bytes"] = None
    return result


def _phase_counter_deltas_from_events(
    before_meta: Mapping[str, Any] | None,
    after_meta: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Compute phase deltas from two event-metadata dicts carrying
    ``counters`` snapshots (as captured by ``_capture_phase_counters()``)."""
    b = (before_meta or {}).get("counters")
    a = (after_meta or {}).get("counters")
    if not isinstance(b, Mapping) or not isinstance(a, Mapping):
        return {}
    return _phase_counter_deltas(dict(b), dict(a))


def _first_event_mono_ns(trace: Any, name: str) -> int | None:
    """Return the monotonic_ns of the first event named *name*, or None."""
    for event in trace.events:
        if event.name == name:
            return event.monotonic_ns
    return None


def _first_event_meta(trace: Any, name: str) -> dict[str, Any] | None:
    """Return the metadata of the first event named *name*, or None."""
    for event in trace.events:
        if event.name == name:
            return dict(event.metadata)
    return None


def _terminal_prefill_event(trace: Any) -> tuple[str, int, dict[str, Any]] | None:
    """Return ``(name, monotonic_ns, metadata)`` of the last terminal prefill
    event (``execution_prefill_completed`` / ``execution_prefill_failed``), or
    None when neither is present.  Latest-by-monotonic wins."""
    best_name: str | None = None
    best_ns = -1
    best_meta: dict[str, Any] = {}
    for event in trace.events:
        if event.name in (_EVENT_COMPLETED, _EVENT_FAILED) and event.monotonic_ns >= best_ns:
            best_name = event.name
            best_ns = event.monotonic_ns
            best_meta = dict(event.metadata)
    if best_name is None:
        return None
    return best_name, best_ns, best_meta


def _bounded_delta_ms(start_ns: int | None, end_ns: int | None) -> float | None:
    """Non-negative ms between two monotonic boundaries, or None when either
    boundary is absent.  Reversed boundaries yield None (never fabricated)."""
    if start_ns is None or end_ns is None:
        return None
    delta = end_ns - start_ns
    if delta < 0:
        return None
    return round(delta / 1_000_000, 3)


def build_clip_prefill_reconciliation(
    trace: Any,
    *,
    outcome: str = "unknown",
    request_id: str = "",
    tolerance_ms: float = 50.0,
) -> dict[str, Any]:
    """Build the per-request CLIP execution-prefill reconciliation record.

    Reads the prefill lifecycle events already emitted on *trace* and
    partitions the worker lifetime into non-overlapping stages:

      queue_ms        submission → worker start       (cross-thread, wall only)
      readiness_ms    readiness_start → readiness_end (model/future readiness)
      page_readiness_ms  page_readiness_start → end  (synchronous native page
                      readiness candidate; only when mode=willneed)
      encode_ms       encode_start → encode_end       (CLIP encode loop)
      completion_ms   encode_end → terminal           (store + finalization)

    ``unattributed_ms = prefill_total_ms - (queue + readiness +
    page_readiness + encode + completion)`` is the COMPUTED accounting
    error — reported explicitly, never hidden.  Missing boundaries are
    ``None`` (truthful) and flip the status to ``"incomplete"``.  When the
    page-readiness candidate is disabled (mode off), ``page_readiness_ms``
    is ``None`` and ``page_readiness_applied`` is False; the stage is then
    excluded from the completeness check so default production runs still
    reconcile as before.  *outcome* describes how the graph consumed the
    result: ``consumed`` / ``fallback_error`` / ``fallback_unavailable``.
    """
    sub_ns = _first_event_mono_ns(trace, _EVENT_SUBMISSION)
    ws_ns = _first_event_mono_ns(trace, _EVENT_WORKER_START)
    rs_ns = _first_event_mono_ns(trace, _EVENT_READINESS_START)
    re_ns = _first_event_mono_ns(trace, _EVENT_READINESS_END)
    prs_ns = _first_event_mono_ns(trace, _EVENT_PAGE_READINESS_START)
    pre_ns = _first_event_mono_ns(trace, _EVENT_PAGE_READINESS_END)
    es_ns = _first_event_mono_ns(trace, _EVENT_ENCODE_START)
    ee_ns = _first_event_mono_ns(trace, _EVENT_ENCODE_END)
    gws_ns = _first_event_mono_ns(trace, _EVENT_GRAPH_WAIT_START)
    gwe_ns = _first_event_mono_ns(trace, _EVENT_GRAPH_WAIT_END)
    terminal = _terminal_prefill_event(trace)

    prefill_total_ms = _bounded_delta_ms(sub_ns, terminal[1] if terminal else None)
    queue_ms = _bounded_delta_ms(sub_ns, ws_ns)
    readiness_ms = _bounded_delta_ms(rs_ns, re_ns)
    page_readiness_applied = prs_ns is not None and pre_ns is not None
    page_readiness_ms = _bounded_delta_ms(prs_ns, pre_ns)
    encode_ms = _bounded_delta_ms(es_ns, ee_ns)
    completion_ms = _bounded_delta_ms(ee_ns, terminal[1] if terminal else None)
    request_wait_ms = _bounded_delta_ms(gws_ns, gwe_ns)

    if page_readiness_applied:
        child_fields = (
            queue_ms, readiness_ms, page_readiness_ms, encode_ms, completion_ms,
        )
    else:
        child_fields = (queue_ms, readiness_ms, encode_ms, completion_ms)
    measured_children_ms: float | None = None
    if all(isinstance(v, (int, float)) for v in child_fields):
        measured_children_ms = round(sum(float(v) for v in child_fields), 3)

    unattributed_ms: float | None = None
    if isinstance(prefill_total_ms, (int, float)) and isinstance(measured_children_ms, (int, float)):
        unattributed_ms = round(prefill_total_ms - measured_children_ms, 3)

    # ── Reconciliation status ─────────────────────────────────────────
    _completeness_fields = [prefill_total_ms, queue_ms, readiness_ms, encode_ms, completion_ms]
    if page_readiness_applied:
        _completeness_fields.append(page_readiness_ms)
    status = "incomplete"
    if all(v is not None for v in _completeness_fields) and isinstance(unattributed_ms, (int, float)):
        if unattributed_ms < -tolerance_ms:
            status = "overlap"
        elif unattributed_ms > tolerance_ms:
            status = "unmeasured_gap"
        else:
            status = "complete"

    # ── Per-phase counter detail (worker thread, truthful None) ───────
    rs_meta = _first_event_meta(trace, _EVENT_READINESS_START)
    re_meta = _first_event_meta(trace, _EVENT_READINESS_END)
    pr_meta = _first_event_meta(trace, _EVENT_PAGE_READINESS_END)
    es_meta = _first_event_meta(trace, _EVENT_ENCODE_START)
    ee_meta = _first_event_meta(trace, _EVENT_ENCODE_END)
    ws_meta = _first_event_meta(trace, _EVENT_WORKER_START)

    readiness = _phase_counter_deltas_from_events(rs_meta, re_meta)
    encode = _phase_counter_deltas_from_events(es_meta, ee_meta)

    page_readiness: dict[str, Any] = {}
    if isinstance(pr_meta, Mapping):
        page_readiness = {
            "mode": pr_meta.get("mode"),
            "status": pr_meta.get("status"),
            "wall_ms": pr_meta.get("wall_ms"),
            "storage_count": pr_meta.get("storage_count"),
            "range_count": pr_meta.get("range_count"),
            "total_bytes": pr_meta.get("total_bytes"),
            "total_pages": pr_meta.get("total_pages"),
            "advised_pages": pr_meta.get("advised_pages"),
            "advised_bytes": pr_meta.get("advised_bytes"),
            "advised_percent": pr_meta.get("advised_percent"),
            "major_faults": pr_meta.get("major_faults"),
            "minor_faults": pr_meta.get("minor_faults"),
            "error_reason": pr_meta.get("error_reason", ""),
        }

    worker_counters: dict[str, Any] = {}
    if isinstance(ws_meta, Mapping):
        _wc = ws_meta.get("counters")
        if isinstance(_wc, Mapping):
            worker_counters = dict(_wc)

    return {
        "request_id": request_id,
        "outcome": outcome,
        "prefill_total_ms": prefill_total_ms,
        "queue_ms": queue_ms,
        "readiness_ms": readiness_ms,
        "page_readiness_ms": page_readiness_ms,
        "page_readiness_applied": page_readiness_applied,
        "encode_ms": encode_ms,
        "completion_ms": completion_ms,
        "request_wait_ms": request_wait_ms,
        "measured_children_ms": measured_children_ms,
        "unattributed_ms": unattributed_ms,
        "reconciliation_status": status,
        "encoded_count": terminal[2].get("encoded_count") if terminal else None,
        "terminal_event": terminal[0] if terminal else None,
        "worker_native_tid": worker_counters.get("native_tid"),
        "worker_native_thread_count": worker_counters.get("native_thread_count"),
        "torch_available": bool((worker_counters.get("torch") or {}).get("torch_available")),
        "torch_intraop_threads": (worker_counters.get("torch") or {}).get("torch_intraop_threads"),
        "torch_interop_threads": (worker_counters.get("torch") or {}).get("torch_interop_threads"),
        "readiness": readiness,
        "encode": encode,
        "page_readiness": page_readiness,
    }


def emit_clip_prefill_reconciliation(
    trace: RuntimeTrace | None,
    *,
    outcome: str,
    request_id: str = "",
) -> dict[str, Any] | None:
    """Emit exactly one ``clip_prefill_reconciliation`` record on *trace*.

    Returns the emitted record dict, or None when *trace* is None.
    """
    if trace is None:
        return None
    record = build_clip_prefill_reconciliation(
        trace, outcome=outcome, request_id=request_id or str(trace.request_id),
    )
    trace.emit(_EVENT_RECONCILIATION, phase="execution", metadata=record)
    return record


# ── Synchronous native page-readiness (Phase B candidate) ──────────────
# Gated by COMFYMODAL_V2_PAGE_READINESS_MODE=willneed (off by default).
# Both helpers are synchronous (never hidden in a future), never schedule
# additional work, never re-encode, and never touch CUDA or mutate models.
# The UNET activation is guarded per-request so a request can never invoke
# the readiness helper twice for the same UNET activation; the guard is
# cleared in existing request cleanup (modal_app request finally block).

# Bounded per-request guard.  An insertion-ordered dict (not a set) so the
# OLDEST claims are evicted first when the bound is reached — the guard can
# never grow without bound even for request ids that bypass the existing
# modal_app request finally-block cleanup.  Membership checks, claim-once
# semantics and normal request cleanup behave exactly as before (clear
# remains the primary cleanup path; the bound is only a safety net).
_UNET_PAGE_READINESS_DONE: dict[str, bool] = {}
_UNET_PAGE_READINESS_LOCK: RLock = RLock()
_UNET_PAGE_READINESS_DONE_MAX = 1024


def _unet_page_readiness_begin(request_id: str) -> bool:
    """Atomically claim the first graph UNET activation for *request_id*.

    Returns True only for the first claim per request; every subsequent
    claim for the same request returns False (a request can never invoke
    the readiness helper twice for the same UNET activation).  Empty
    request ids are never claimed.  The guard map is bounded: when the
    bound is reached the oldest claim is evicted first, so request ids
    that bypass normal request cleanup cannot leak forever."""
    if not request_id:
        return False
    with _UNET_PAGE_READINESS_LOCK:
        if request_id in _UNET_PAGE_READINESS_DONE:
            return False
        _UNET_PAGE_READINESS_DONE[request_id] = True
        if len(_UNET_PAGE_READINESS_DONE) > _UNET_PAGE_READINESS_DONE_MAX:
            _excess = len(_UNET_PAGE_READINESS_DONE) - _UNET_PAGE_READINESS_DONE_MAX
            for _stale in list(_UNET_PAGE_READINESS_DONE.keys())[:_excess]:
                del _UNET_PAGE_READINESS_DONE[_stale]
        return True


def _unet_page_readiness_clear(request_id: str) -> None:
    """Release the per-request UNET page-readiness guard (request cleanup)."""
    if not request_id:
        return
    with _UNET_PAGE_READINESS_LOCK:
        _UNET_PAGE_READINESS_DONE.pop(request_id, None)


def _unet_page_readiness_is_done(request_id: str) -> bool:
    """True when the readiness guard is currently claimed for *request_id*."""
    if not request_id:
        return False
    with _UNET_PAGE_READINESS_LOCK:
        return _UNET_PAGE_READINESS_DONE.get(request_id, False)


def _first_registered_unet_model(models: list[Any]) -> Any | None:
    """Return the first model in *models* that is a registered retained UNET.

    Uses ``resolve_diffusion_model`` + the weak registry lookup so the exact
    retained UNET is targeted (CacheDiT wrappers wrapping the SAME diffusion
    model are still accepted).  Never raises.
    """
    try:
        from .unet_forward_probe import _lookup_entry, resolve_diffusion_model
        for model in models:
            _, dm = resolve_diffusion_model(model)
            if dm is not None and _lookup_entry(dm) is not None:
                return model
    except Exception:
        pass
    return None


def _run_clip_page_readiness(
    clip: Any,
    *,
    trace: RuntimeTrace | None,
    request_id: str,
) -> dict[str, Any] | None:
    """Synchronous native page-readiness for the exact retained CLIP object.

    Called in ``_execution_prefill`` after the CLIP future/readiness wait and
    immediately before the encode loop.  Gated by
    ``COMFYMODAL_V2_PAGE_READINESS_MODE=willneed``; returns None when
    off (no-op, no events emitted).  Emits structured start/end events with
    ``stage=clip_prefill`` and the full readiness evidence (mode, status,
    wall_ms, storage/range/page counts, native fault counters, error
    reason).  Never schedules another future or duplicates the encode.
    ``status=ok`` means the madvise(MADV_WILLNEED) advisory was accepted —
    NOT that the physical pages are resident.
    """
    if page_readiness_mode() != "willneed":
        return None
    if clip is None:
        if trace is not None:
            trace.emit(
                _EVENT_PAGE_READINESS_START, phase="execution",
                metadata={"mode": "willneed", "stage": "clip_prefill",
                          "status": "skip", "reason": "no_clip"},
            )
        return None
    if trace is not None:
        trace.emit(
            _EVENT_PAGE_READINESS_START, phase="execution",
            metadata={"mode": "willneed", "stage": "clip_prefill",
                      "request_id": request_id,
                      "counters": _capture_phase_counters()},
        )
    try:
        result = advise_storage_pages_willneed(clip)
    except Exception as exc:
        result = {
            "status": "error", "mode": "willneed",
            "error_reason": f"{type(exc).__name__}: {str(exc)[:200]}",
        }
    if trace is not None:
        meta: dict[str, Any] = dict(result)
        meta["stage"] = "clip_prefill"
        meta["request_id"] = request_id
        meta["mode"] = "willneed"
        meta["counters"] = _capture_phase_counters()
        trace.emit(_EVENT_PAGE_READINESS_END, phase="execution", metadata=meta)
    return result


def _run_unet_page_readiness(
    unet: Any,
    *,
    trace: RuntimeTrace | None,
    request_id: str,
) -> dict[str, Any] | None:
    """Synchronous native page-readiness for the retained UNET activation.

    Called immediately before the existing original ``load_models_gpu`` call
    for the FIRST request-scoped graph UNET activation only (registered
    retained UNET, request trace, no active model lane).  Never run for
    restore-time background lanes or non-UNET/CLIP calls.  Emits
    ``stage=unet_activation`` readiness evidence.  ``status=ok`` means the
    madvise(MADV_WILLNEED) advisory was accepted — NOT that the physical
    pages are resident.
    """
    if page_readiness_mode() != "willneed":
        return None
    if unet is None:
        return None
    try:
        result = advise_storage_pages_willneed(unet)
    except Exception as exc:
        result = {
            "status": "error", "mode": "willneed",
            "error_reason": f"{type(exc).__name__}: {str(exc)[:200]}",
        }
    if trace is not None:
        meta = dict(result)
        meta["stage"] = "unet_activation"
        meta["request_id"] = request_id
        meta["mode"] = "willneed"
        trace.emit(_EVENT_UNET_PAGE_READINESS, phase="execution", metadata=meta)
    return result


# ── Per-worker lane context (set around worker callback) ─────────────

_ACTIVE_LANE_TRACE: ContextVar["ModelLaneTrace | None"] = ContextVar(
    "comfymodal_active_lane_trace", default=None
)
_ACTIVE_REQUEST_TRACE: ContextVar["RuntimeTrace | None"] = ContextVar(
    "comfymodal_active_request_trace", default=None
)
"""Set to the active ``ModelLaneTrace`` while a worker callback runs.
Reset to ``None`` after the callback completes."""

# ── Background UNET diagnostics store ────────────────────────────────
# Thread-safe mapping from canonical key -> completed RuntimeTrace events
# list for background UNET worker.  Written by the worker thread, read
# (and drained) by the graph cache patcher.
_BG_UNET_DIAG_STORE: dict[str, list] = {}
_BG_UNET_DIAG_LOCK = RLock()

# ── ComfyUI core dispatch wrappers (installed once globally) ─────────
# Wrappers target the *live* module objects already loaded by ComfyUI's
# ``nodes.py`` at startup, resolving via ``sys.modules`` rather than a
# fresh ``import`` (which can fail on optional dependencies such as
# ``comfy_aimdo``).  Each component is tracked independently.

_SENTINEL_READ = "_comfy_modal_read_wrapper"
_SENTINEL_GPU = "_comfy_modal_gpu_wrapper"
_SENTINEL_SD = "_comfy_modal_sd_wrapper"
_SENTINEL_SUBFN = "_comfy_modal_subfn_wrapper"
_SENTINEL_DEEP_ST = "_comfy_modal_deep_st_wrapper"
_SENTINEL_DEEP_TL = "_comfy_modal_deep_tl_wrapper"
_SENTINEL_CLIP = "_comfy_modal_clip_wrapper"
_SENTINEL_CLIP_SUBFN = "_comfy_modal_clip_subfn_wrapper"
_SENTINEL_UNET_SUBFN = "_comfy_modal_unet_subfn_wrapper"
_SENTINEL_SHARED_COQ = "_comfy_modal_shared_convert_old_quants"
_SENTINEL_MODEL_PATCHER = "_comfy_modal_model_patcher_wrapper"
_SENTINEL_MODEL_TO = "_comfy_modal_model_to_wrapper"
_SENTINEL_CLIP_CONSTRUCTOR = "_comfy_modal_clip_constructor_wrapper"
_SENTINEL_CLIP_LOAD_SD = "_comfy_modal_clip_load_sd_wrapper"
_SENTINEL_MODEL_PATCHER_LOAD = "_comfy_modal_model_patcher_load_wrapper"
_SENTINEL_MODEL_PATCHER_LOAD_LIST = "_comfy_modal_model_patcher_load_list_wrapper"
_SENTINEL_MODEL_PATCHER_PATCH_WEIGHT = "_comfy_modal_model_patcher_patch_weight_wrapper"
_SENTINEL_CAST_TO_DEVICE = "_comfy_modal_cast_to_device_wrapper"

_read_wrapper_installed: bool = False
_gpu_wrapper_installed: bool = False
_sd_wrapper_installed: bool = False
_subfn_wrappers_installed: bool = False
_deep_diag_wrappers_installed: bool = False
_clip_wrapper_installed: bool = False
_clip_constructor_wrapper_installed: bool = False
_clip_load_sd_wrapper_installed: bool = False
_wrappers_lock = RLock()

# Reentrancy guards — per-thread via ContextVar default=0.
_torch_file_depth: ContextVar[int] = ContextVar("_torch_file_depth", default=0)
_gpu_depth: ContextVar[int] = ContextVar("_gpu_depth", default=0)
_sd_depth: ContextVar[int] = ContextVar("_sd_depth", default=0)
_deep_st_depth: ContextVar[int] = ContextVar("_deep_st_depth", default=0)
_deep_tl_depth: ContextVar[int] = ContextVar("_deep_tl_depth", default=0)
_clip_depth: ContextVar[int] = ContextVar("_clip_depth", default=0)
_clip_subfn_depth: ContextVar[int] = ContextVar("_clip_subfn_depth", default=0)
_clip_constructor_depth: ContextVar[int] = ContextVar("_clip_constructor_depth", default=0)

# ModelPatcher.load aggregate-timing breakdown contexts
_model_patcher_load_depth: ContextVar[int] = ContextVar("_model_patcher_load_depth", default=0)
# Breakdown accumulator dict set only during outer ModelPatcher.load under request trace.
# Keys: outer_start_ns, outer_thread_start_ns, outer_process_start_ns,
#       load_list_wall_ns, load_list_process_start_ns, load_list_process_end_ns,
#       patch_weight_count, patch_weight_wall_ns, patch_weight_process_ns,
#       cast_count, cast_wall_ns, cast_process_ns
_model_patcher_breakdown: ContextVar[dict | None] = ContextVar("_model_patcher_breakdown", default=None)

# ── Deep-diagnostic target path (thread-local) ──────────────────────
# Set by the background UNET worker before the load body; used by the
# deep diag wrappers to filter: only emit stage events when the current
# thread's *target_path* matches the file being accessed AND deep diag
# is enabled.  Avoids logging unrelated model loads.
_DEEP_TARGET_PATH: ContextVar[str] = ContextVar("_deep_target_path", default="")

# Residual tracking — list of child duration_ms collected during an SD outer call.
_child_durations: ContextVar[list[float] | list[tuple[str, float]] | None] = ContextVar("_child_durations", default=None)

# CLIP CPU prepare child durations.
_clip_cpu_prepare_children: ContextVar[list[tuple[str, float]] | None] = ContextVar("_clip_cpu_prepare_children", default=None)

# GPU request-local invocation count (ContextVar for per-thread safety).
_gpu_request_call_count_var: ContextVar[int] = ContextVar("_gpu_request_call_count", default=0)

# UNET subfn nesting depth — tracks cross-function nesting for non-overlapping measured children.
_unet_subfn_nesting_depth: ContextVar[int] = ContextVar("_unet_subfn_nesting_depth", default=0)

# Accumulator for "not_observed" GPU wrapper calls (no lane/request scope).
_not_observed_gpu_calls: int = 0

# ── Residency sampler callback (request-scoped, separate from activation state) ──
# ContextVar for a callable that _make_gpu_loader_wrapper and unet_forward_probe
# invoke at UNET GPU load before/after and first_unet_forward respectively.
_RESIDENCY_SAMPLER_CALLBACK: ContextVar[Any] = ContextVar(
    "_residency_sampler_callback", default=None
)

def set_residency_sampler_callback(cb: Any) -> None:
    """Set a callable(stage: str, trace: RuntimeTrace | None) -> None for residency sampling."""
    _RESIDENCY_SAMPLER_CALLBACK.set(cb)

def clear_residency_sampler_callback() -> None:
    _RESIDENCY_SAMPLER_CALLBACK.set(None)

# ── Sampler stall watchdog (one-shot, non-destructive) ─────────────────────
# Reads request-time boundaries only (first UNET forward, first completed
# sampler step).  Never blocks, cancels, or mutates sampler execution, and
# never disables CacheDiT.  Each request arms one daemon thread that emits a
# ``[v2.sampler_stall_watchdog]`` diagnostic ONLY when a threshold is missed
# (timeout); normal completion and cancel are silent.  ``cancel()`` finishes
# it on normal completion so nothing keeps the event loop alive.
#
# Exact deadlines (both measured from watchdog arm / sampling start):
#   - 5s  waiting for the first UNET forward
#   - 15s waiting for the first completed sampler step (NOT 5s + 15s)

_SAMPLER_STALL_WATCHDOGS: dict[str, "_SamplerStallWatchdog"] = {}
_SAMPLER_STALL_WATCHDOG_LOCK: RLock = RLock()

# Bounded one-shot stage deadlines: 5s for the first UNET forward, 15s for
# the first completed sampler step (from arm / sampling start).
_SAMPLER_STALL_FIRST_FORWARD_TIMEOUT_S: float = 5.0
_SAMPLER_STALL_FIRST_STEP_TIMEOUT_S: float = 15.0


class _SamplerStallWatchdog:
    """One-shot per-request stall watchdog for first UNET forward + first step.

    ``mark_*`` methods are callable from any thread (forward hooks, sampler
    wrapper).  The daemon thread emits ``[v2.sampler_stall_watchdog]`` only
    when a threshold is missed (status=timeout) and exits; ``cancel()`` wakes
    it promptly on normal completion and is silent.  Non-destructive: no
    sampler/model mutation.
    """

    def __init__(
        self,
        *,
        request_id: str,
        restored_instance_id: str = "",
        sampler_node_id: str = "",
        sampler_class: str = "",
        patcher_object_id: str = "",
        diffusion_model_object_id: str = "",
        unet_object_id: str = "",
    ) -> None:
        self.request_id = request_id
        self.restored_instance_id = restored_instance_id
        self.sampler_node_id = sampler_node_id
        self.sampler_class = sampler_class
        self.patcher_object_id = patcher_object_id
        self.diffusion_model_object_id = diffusion_model_object_id
        self.unet_object_id = unet_object_id
        self._unet_forward_event = Event()
        self._sampler_step_event = Event()
        self._forward_seen = False
        self._step_seen = False
        self._done = False
        self._thread: Thread | None = None
        self._start_mono_ns = time.monotonic_ns()
        self._forward_latency_ms: float | None = None
        self._step_latency_ms: float | None = None

    def _ctx(self) -> str:
        return (
            f"request_id={self.request_id} "
            f"restored_instance_id={self.restored_instance_id or 'absent'} "
            f"sampler_node_id={self.sampler_node_id or 'absent'} "
            f"sampler_class={self.sampler_class or 'absent'} "
            f"patcher_object_id={self.patcher_object_id or 'absent'} "
            f"diffusion_model_object_id={self.diffusion_model_object_id or 'absent'} "
            f"unet_object_id={self.unet_object_id or 'absent'}"
        )

    def update_sampler_identity(
        self,
        *,
        sampler_node_id: str = "",
        sampler_class: str = "",
        patcher_object_id: str = "",
        diffusion_model_object_id: str = "",
    ) -> None:
        """Enrich the watchdog with sampler/node/patcher identity once known
        (typically at sampling_start).  Empty values are ignored."""
        if sampler_node_id:
            self.sampler_node_id = str(sampler_node_id)
        if sampler_class:
            self.sampler_class = str(sampler_class)
        if patcher_object_id:
            self.patcher_object_id = str(patcher_object_id)
        if diffusion_model_object_id:
            self.diffusion_model_object_id = str(diffusion_model_object_id)

    def start(self) -> None:
        if self._thread is not None:
            return
        print(
            f"[v2.sampler_stall_watchdog] stage=armed "
            f"{self._ctx()} "
            f"first_forward_timeout_s={_SAMPLER_STALL_FIRST_FORWARD_TIMEOUT_S} "
            f"first_step_timeout_s={_SAMPLER_STALL_FIRST_STEP_TIMEOUT_S}",
            flush=True,
        )
        self._thread = Thread(
            target=self._run,
            name=f"comfymodal-stall-watchdog-{self.request_id[:16]}",
            daemon=True,
        )
        self._thread.start()

    def mark_first_unet_forward(self) -> None:
        if self._forward_seen:
            return
        self._forward_seen = True
        self._forward_latency_ms = round(
            (time.monotonic_ns() - self._start_mono_ns) / 1_000_000, 3
        )
        self._unet_forward_event.set()

    def mark_first_sampler_step(self) -> None:
        if self._step_seen:
            return
        self._step_seen = True
        self._step_latency_ms = round(
            (time.monotonic_ns() - self._start_mono_ns) / 1_000_000, 3
        )
        self._sampler_step_event.set()

    def cancel(self) -> None:
        """Finish the watchdog on normal completion.  Wakes the daemon thread
        immediately; joins briefly.  Never blocks the caller for long."""
        self._unet_forward_event.set()
        self._sampler_step_event.set()
        self._done = True
        thread = self._thread
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=1.0)

    def _run(self) -> None:
        try:
            # First UNET forward: wait up to exactly 5s from arm.
            got_forward = self._unet_forward_event.wait(
                timeout=_SAMPLER_STALL_FIRST_FORWARD_TIMEOUT_S
            )
            if not got_forward:
                # Threshold missed -> emit exactly one diagnostic record.
                print(
                    f"[v2.sampler_stall_watchdog] stage=first_unet_forward "
                    f"status=timeout {self._ctx()} "
                    f"timeout_s={_SAMPLER_STALL_FIRST_FORWARD_TIMEOUT_S}",
                    flush=True,
                )
            # First completed sampler step: the deadline is exactly 15s from
            # watchdog arm / sampling start — NOT cumulative 5s + 15s.  The
            # remaining budget is recomputed from arm time, so a slow forward
            # stage cannot extend the step deadline.
            _elapsed_s = (time.monotonic_ns() - self._start_mono_ns) / 1_000_000_000.0
            _step_timeout = max(
                0.0, _SAMPLER_STALL_FIRST_STEP_TIMEOUT_S - _elapsed_s
            )
            got_step = self._sampler_step_event.wait(timeout=_step_timeout)
            if not got_step:
                print(
                    f"[v2.sampler_stall_watchdog] stage=first_sampler_step "
                    f"status=timeout {self._ctx()} "
                    f"timeout_s={_SAMPLER_STALL_FIRST_STEP_TIMEOUT_S}",
                    flush=True,
                )
            # Normal completion and cancel are SILENT: no status=ok or
            # status=cancelled records — only missed thresholds diagnose.
        finally:
            with _SAMPLER_STALL_WATCHDOG_LOCK:
                _SAMPLER_STALL_WATCHDOGS.pop(self.request_id, None)


def start_sampler_stall_watchdog(
    *,
    request_id: str,
    restored_instance_id: str = "",
    sampler_node_id: str = "",
    sampler_class: str = "",
    patcher_object_id: str = "",
    diffusion_model_object_id: str = "",
    unet_object_id: str = "",
) -> bool:
    """Arm the one-shot stall watchdog for *request_id*.

    Idempotent per request_id: a second call for the same request returns
    False without arming a duplicate.  Returns True when a new watchdog was
    armed.  Never raises; always spawns a daemon thread that self-terminates.
    """
    try:
        with _SAMPLER_STALL_WATCHDOG_LOCK:
            existing = _SAMPLER_STALL_WATCHDOGS.get(request_id)
            if existing is not None:
                return False
            watchdog = _SamplerStallWatchdog(
                request_id=request_id,
                restored_instance_id=restored_instance_id,
                sampler_node_id=sampler_node_id,
                sampler_class=sampler_class,
                patcher_object_id=patcher_object_id,
                diffusion_model_object_id=diffusion_model_object_id,
                unet_object_id=unet_object_id,
            )
            _SAMPLER_STALL_WATCHDOGS[request_id] = watchdog
        watchdog.start()
        return True
    except Exception:
        return False


def update_sampler_stall_watchdog_identity(
    request_id: str,
    *,
    sampler_node_id: str = "",
    sampler_class: str = "",
    patcher_object_id: str = "",
    diffusion_model_object_id: str = "",
) -> None:
    """Enrich an armed watchdog with sampler/node/patcher identity."""
    with _SAMPLER_STALL_WATCHDOG_LOCK:
        watchdog = _SAMPLER_STALL_WATCHDOGS.get(request_id)
    if watchdog is not None:
        watchdog.update_sampler_identity(
            sampler_node_id=sampler_node_id,
            sampler_class=sampler_class,
            patcher_object_id=patcher_object_id,
            diffusion_model_object_id=diffusion_model_object_id,
        )


def mark_first_unet_forward(request_id: str) -> None:
    """Called by the UNET forward probe on the first CUDA forward."""
    with _SAMPLER_STALL_WATCHDOG_LOCK:
        watchdog = _SAMPLER_STALL_WATCHDOGS.get(request_id)
    if watchdog is not None:
        watchdog.mark_first_unet_forward()


def mark_first_sampler_step(request_id: str) -> None:
    """Called by the SAMPLER_SAMPLE wrapper on the first completed step."""
    with _SAMPLER_STALL_WATCHDOG_LOCK:
        watchdog = _SAMPLER_STALL_WATCHDOGS.get(request_id)
    if watchdog is not None:
        watchdog.mark_first_sampler_step()


def cancel_sampler_stall_watchdog(request_id: str) -> None:
    """Cancel (finish) the watchdog on normal completion.

    Removes the request from the registry and wakes the daemon thread so it
    exits promptly.  Non-blocking to the caller (brief bounded join)."""
    with _SAMPLER_STALL_WATCHDOG_LOCK:
        watchdog = _SAMPLER_STALL_WATCHDOGS.pop(request_id, None)
    if watchdog is not None:
        watchdog.cancel()


# ── Retained UNET object-identity chain ─────────────────────────────────────
# Per-request registry of the exact retained UNET object id at each lifecycle
# stage: snapshot -> bridge -> activation -> cachedit -> sampler.  The LOGICAL
# identity is the resolved diffusion-model object, so ComfyUI's dynamic
# ModelPatcher delegates (re-attach / CacheDiT wrapper re-patches) that wrap
# the SAME diffusion model are still accepted.  A different resolved diffusion
# object (or a missing one on either side) fails closed.

_SNAPSHOT_UNET_CHAIN: dict[str, dict[str, int]] = {}
_SNAPSHOT_UNET_CHAIN_LOCK: RLock = RLock()


def _resolve_logical_unet_identity(unet: Any) -> tuple[int, Any]:
    """Resolve *unet* to ``(patcher_object_id, diffusion_model)``.

    The diffusion model is the stable logical identity across ModelPatcher
    delegates and CacheDiT wrapper/re-attach.  Never raises; falls back to a
    ``(object_id, None)`` pair when the object cannot be resolved.
    """
    obj_id = int(id(unet)) if unet is not None else 0
    dm = None
    if unet is not None:
        try:
            from .unet_forward_probe import resolve_diffusion_model
            _, dm = resolve_diffusion_model(unet)
        except Exception:
            dm = None
    return obj_id, dm


def record_retained_unet_identity(stage: str, unet: Any, request_id: str = "") -> int:
    """Record ``id(unet)`` at *stage* for *request_id*.

    Emits ``[v2.unet_identity_chain]``.  Returns the recorded object id
    (0 when *unet* is None).  Never stores a record under an empty
    request_id — the empty key is never left behind and cleanup always
    removes the actual request key.  Never raises.
    """
    obj_id = int(id(unet)) if unet is not None else 0
    try:
        with _SNAPSHOT_UNET_CHAIN_LOCK:
            if request_id:
                chain = _SNAPSHOT_UNET_CHAIN.setdefault(request_id, {})
                chain[stage] = obj_id
        print(
            f"[v2.unet_identity_chain] stage={stage} "
            f"request_id={request_id or 'absent'} unet_object_id={obj_id}",
            flush=True,
        )
    except Exception:
        pass
    return obj_id


def clear_retained_unet_identity_chain(request_id: str) -> None:
    """Drop the identity chain for *request_id* (end of request).

    An empty request_id is a no-op — it never clears unrelated keys."""
    if not request_id:
        return
    try:
        with _SNAPSHOT_UNET_CHAIN_LOCK:
            _SNAPSHOT_UNET_CHAIN.pop(request_id, "")
    except Exception:
        pass


def verify_retained_unet_identity(
    *,
    stage_a: str,
    unet_a: Any,
    stage_b: str,
    unet_b: Any,
    request_id: str = "",
) -> tuple[bool, str]:
    """Verify the exact LOGICAL retained UNET identity between two stages.

    The logical identity is the resolved diffusion-model object, so
    ModelPatcher delegates and CacheDiT wrapper/re-attach that wrap the SAME
    diffusion model are accepted.  Returns ``(True, "ok")`` when both sides
    resolve to the same non-None diffusion model.  Emits
    ``[v2.unet_identity_chain]`` (patcher + diffusion ids on both sides) and
    raises RuntimeError on any mismatch or missing object — the sampler must
    never receive a different UNET than the one validated, retargeted,
    published, and (optionally) CacheDiT-patched.
    """
    obj_id_a, dm_a = _resolve_logical_unet_identity(unet_a)
    obj_id_b, dm_b = _resolve_logical_unet_identity(unet_b)
    id_a = int(id(dm_a)) if dm_a is not None else 0
    id_b = int(id(dm_b)) if dm_b is not None else 0
    ok = id_a != 0 and id_b != 0 and id_a == id_b
    reason = "ok"
    if not ok:
        if id_a == 0 or id_b == 0:
            reason = "unet_missing"
        else:
            reason = f"identity_mismatch:{id_a}!={id_b}"
    print(
        f"[v2.unet_identity_chain] check=stage_pair stage_a={stage_a} stage_b={stage_b} "
        f"request_id={request_id or 'absent'} "
        f"patcher_a_object_id={obj_id_a} diffusion_a_object_id={id_a} "
        f"patcher_b_object_id={obj_id_b} diffusion_b_object_id={id_b} "
        f"ok={int(ok)} reason={reason}",
        flush=True,
    )
    if not ok:
        raise RuntimeError(
            f"Retained UNET identity mismatch between {stage_a} and {stage_b}: {reason}"
        )
    return (True, "ok")


# ── Production CPU-snapshot request marker ─────────────────────────────────
# Per-request marker set only when a production request binds the CPU
# snapshot WITHOUT the diagnostic UNET bypass.  Used by the sampler wrapper
# to gate fail-closed CPU-residency enforcement to the exact retained
# snapshot/bridge object being sampled.  Normal, CPU-only, dynamic/offload,
# meta/unknown, and bypass paths never set it, so they stay diagnostic-only.

_PRODUCTION_CPU_SNAPSHOT_REQUESTS: set[str] = set()
_PRODUCTION_CPU_SNAPSHOT_REQUESTS_LOCK: RLock = RLock()


def mark_production_cpu_snapshot_request(request_id: str) -> None:
    """Mark *request_id* as bound to the production CPU-snapshot path."""
    if not request_id:
        return
    with _PRODUCTION_CPU_SNAPSHOT_REQUESTS_LOCK:
        _PRODUCTION_CPU_SNAPSHOT_REQUESTS.add(request_id)


def unmark_production_cpu_snapshot_request(request_id: str) -> None:
    """Clear the production CPU-snapshot marker for *request_id*."""
    if not request_id:
        return
    with _PRODUCTION_CPU_SNAPSHOT_REQUESTS_LOCK:
        _PRODUCTION_CPU_SNAPSHOT_REQUESTS.discard(request_id)


def is_production_cpu_snapshot_request(request_id: str) -> bool:
    """True when *request_id* is marked as the production CPU-snapshot path."""
    if not request_id:
        return False
    with _PRODUCTION_CPU_SNAPSHOT_REQUESTS_LOCK:
        return request_id in _PRODUCTION_CPU_SNAPSHOT_REQUESTS


# ── UNET activation boundary diagnostics ───────────────────────────────────
# Authoritative [v2.unet_activation] lines: requested / started / completed /
# failed.  Identifies the retained UNET by object id + model-key identity;
# no tensor contents.


def emit_unet_activation_diagnostic(
    *,
    stage: str,
    request_id: str = "",
    restored_instance_id: str = "",
    unet_object_id: str = "",
    unet_identity: str = "",
    status: str = "",
    reason: str = "",
) -> None:
    """Emit one authoritative ``[v2.unet_activation]`` boundary line."""
    print(
        f"[v2.unet_activation] stage={stage} "
        f"request_id={request_id or 'absent'} "
        f"restored_instance_id={restored_instance_id or 'absent'} "
        f"unet_object_id={unet_object_id or 'absent'} "
        f"unet_identity={unet_identity or 'absent'} "
        f"status={status or 'absent'} "
        f"reason={reason or 'ok'}",
        flush=True,
    )


def _resolve_model_role_for_boundary(model: Any) -> str:
    """Classify a model patcher as UNET / CLIP / VAE / other for boundary
    diagnostics.  Never raises; falls back to the type name."""
    try:
        from .unet_forward_probe import resolve_diffusion_model
        _, dm = resolve_diffusion_model(model)
        if dm is not None:
            return "UNET"
        type_name = type(model).__name__.lower()
        if "clip" in type_name:
            return "CLIP"
        if "vae" in type_name:
            return "VAE"
        return type_name or "other"
    except Exception:
        return "other"

# ── UNET effective-dtype resolver (shared by snapshot and normal paths) ──
# Resolution strategy depends on context:
#
#   1. Normal (GPU) load path — uses the real CUDA hardware via ComfyUI's
#      model_management.unet_dtype() auto-detection.  The "default" string
#      is passed through to UNETLoader.load_unet which leaves model_options
#      empty, letting ComfyUI probe the real GPU.  This works because CUDA
#      is available.
#
#   2. CPU snapshot construction path — there is NO GPU available (Modal's
#      CPU snapshot builder).  CUDA APIs cannot be called.  The effective
#      dtype must be resolved from the *configured* target GPU(s) via the
#      target-GPU policy in gpu_catalog.gpu_supports_bf16().
#
# The resolve_unet_effective_dtype() function accepts an optional
# *target_gpus* parameter.  When provided (snapshot path), it uses
# the pure static lookup.  When absent (normal path), it falls back
# to the real GPU probe path.
#
# DO NOT cache a false CUDA capability result from the CPU snapshot builder.
# DO NOT call torch.cuda.* APIs from code that runs during snapshot
# construction.

# ── CPU-snapshot native-BF16 compute policy ─────────────────────────────
# Contextmanager that temporarily patches comfy.model_management.unet_manual_cast
# during snapshot UNET construction on CPU so native BF16 compute is used.
# Without this patch, unet_manual_cast gets CPU as inference_device and falls
# through to torch.float32, building the model with fp32 compute even though
# weights are bfloat16.
#
# Thread-safety: the dedicated lock is held across the entire patched interval
# (install + yield + restore).  The patched wrapper uses a thread-identity
# ContextVar so unrelated callers on other threads always delegate to the
# original function.

_CPU_SNAPSHOT_UNET_COMPUTE_POLICY_LOCK: RLock = RLock()

_CPU_SNAPSHOT_UNET_POLICY_ACTIVE_THREAD: ContextVar[int] = ContextVar(
    "_cpu_snapshot_unet_policy_active_thread", default=0
)

_CPU_SNAPSHOT_UNET_MANUAL_CAST_OVERRIDE: ContextVar[str] = ContextVar(
    "_cpu_snapshot_unet_manual_cast_override", default=""
)


@contextmanager
def cpu_snapshot_unet_compute_policy(
    *,
    effective_weight_dtype: Any,
    target_gpus: tuple[str, ...],
) -> Iterator[None]:
    import sys as _sys
    import torch as _torch
    import threading
    from gpu_catalog import gpu_supports_bf16

    # Primary GPU semantics: only the first target GPU determines BF16 capability,
    # consistent with resolve_unet_effective_dtype and _resolve_compute_policy.
    _primary_gpu = target_gpus[0] if target_gpus else ""
    _should_patch = (
        effective_weight_dtype is not None
        and effective_weight_dtype == _torch.bfloat16
        and _primary_gpu
        and gpu_supports_bf16(_primary_gpu)
    )

    if not _should_patch:
        yield
        return

    _tid = threading.get_ident()
    _current = _CPU_SNAPSHOT_UNET_POLICY_ACTIVE_THREAD.get()
    if _current != 0 and _current == _tid:
        raise RuntimeError(
            "cpu_snapshot_unet_compute_policy is not reentrant: "
            "a policy context is already active on this thread"
        )

    _mm = None
    _orig_fn = None
    _installed = False
    try:
        with _CPU_SNAPSHOT_UNET_COMPUTE_POLICY_LOCK:
            if _CPU_SNAPSHOT_UNET_POLICY_ACTIVE_THREAD.get() != 0:
                yield
                return

            _mm = _sys.modules.get("comfy.model_management")
            if _mm is None:
                yield
                return

            _orig_fn = getattr(_mm, "unet_manual_cast", None)
            if _orig_fn is None:
                yield
                return

            _CPU_SNAPSHOT_UNET_POLICY_ACTIVE_THREAD.set(_tid)
            _CPU_SNAPSHOT_UNET_MANUAL_CAST_OVERRIDE.set("none")

            def _policy_wrapper(
                weight_dtype: Any,
                inference_device: Any,
                supported_dtypes: list | None = None,
            ) -> Any:
                if _CPU_SNAPSHOT_UNET_POLICY_ACTIVE_THREAD.get() == threading.get_ident():
                    _mode = _CPU_SNAPSHOT_UNET_MANUAL_CAST_OVERRIDE.get()
                    if _mode == "none" and weight_dtype is _torch.bfloat16:
                        return None
                if _orig_fn is not None:
                    if supported_dtypes is not None:
                        return _orig_fn(weight_dtype, inference_device, supported_dtypes)
                    return _orig_fn(weight_dtype, inference_device)
                return None

            setattr(_mm, "unet_manual_cast", _policy_wrapper)
            _installed = True

            # Yield INSIDE the lock — lock covers install + yield + restore
            yield

    finally:
        if _installed and _mm is not None and _orig_fn is not None:
            # Restore under the same lock acquisition; re-read the live
            # module to handle edge cases where model_management was
            # reloaded between yield and finally.
            # ContextVars are reset in a nested try/finally so they are
            # cleared even if the module attribute restore raises.
            with _CPU_SNAPSHOT_UNET_COMPUTE_POLICY_LOCK:
                _CPU_SNAPSHOT_UNET_POLICY_ACTIVE_THREAD.set(0)
                _CPU_SNAPSHOT_UNET_MANUAL_CAST_OVERRIDE.set("")
                _installed = False
                # Restore the original function — if this raises, the
                # ContextVars above have already been reset so subsequent
                # operations are not permanently broken.
                restore_target = _sys.modules.get("comfy.model_management")
                if restore_target is not None:
                    setattr(restore_target, "unet_manual_cast", _orig_fn)


def resolve_unet_effective_dtype(
    weight_dtype_str: str = "default",
    *,
    target_gpus: tuple[str, ...] | None = None,
) -> tuple[Any, str]:
    """Resolve a weight_dtype string to the *effective* torch dtype.

    Returns ``(effective_dtype, resolved_label)`` where *effective_dtype* is
    the ``torch.dtype`` the configured GPU load path would use for this
    string, and *resolved_label* is a short diagnostic label.

    **target_gpus** (tuple of canonical Modal GPU names, optional):
      When provided (CPU snapshot construction), the effective dtype is
      determined from the *configured* target GPU(s) via a pure name-based
      lookup — no CUDA API calls.  The primary (first) GPU in the tuple
      is used.
      When ``None`` (normal runtime path), the function falls through to
      let ComfyUI's normal runtime policy apply (``"default"`` passes
      through as-is, returning ``(None, "default")``).

    Decision order:
      1. CLI flags override everything (``--fp32-unet``, ``--bf16-unet``, …).
      2. Explicit fp8/e4m3fn/e5m2 strings -> corresponding torch dtype.
      3. ``"default"`` with *target_gpus* -> target-GPU policy lookup.
      4. ``"default"`` without *target_gpus* -> ``(None, "default")``
         (let ComfyUI auto-detect at load time).

    Both the snapshot construction path (``_cpu_load_unet``) and the normal
    loader path (``V2LoaderBridge._load_unet``) use this function so they
    cannot drift.

    Returns
    -------
    effective_dtype
        The resolved ``torch.dtype``, or ``None`` for unrecognised strings
        / pass-through values.
    resolved_label
        Short string for diagnostic logging.
    """
    # Import torch lazily — may not be available at parse time in all contexts.
    import torch as _torch
    import comfy.cli_args as _ca

    # 1. CLI flags (work in both normal and CPU-snapshot contexts)
    if getattr(_ca.args, "fp32_unet", False):
        return (_torch.float32, "float32")
    if getattr(_ca.args, "fp64_unet", False):
        return (_torch.float64, "float64")
    if getattr(_ca.args, "bf16_unet", False):
        return (_torch.bfloat16, "bfloat16")
    if getattr(_ca.args, "fp16_unet", False):
        return (_torch.float16, "float16")

    # 2. Explicit fp8 strings (float8 types may not exist in older PyTorch)
    _float8_e4m3fn = getattr(_torch, "float8_e4m3fn", None)
    _float8_e5m2 = getattr(_torch, "float8_e5m2", None)
    if weight_dtype_str in ("fp8_e4m3fn", "fp8_e4m3fn_fast"):
        if _float8_e4m3fn is not None:
            return (_float8_e4m3fn, weight_dtype_str)
        return (None, weight_dtype_str)
    if weight_dtype_str == "fp8_e5m2":
        if _float8_e5m2 is not None:
            return (_float8_e5m2, weight_dtype_str)
        return (None, weight_dtype_str)

    # 3. Recognised non-"default" string without a type override
    if weight_dtype_str != "default":
        return (None, weight_dtype_str)

    # 4. "default" with target_gpus — snapshot construction path.
    #    Use the configured target GPU(s), not the local CUDA state.
    if target_gpus is not None:
        from gpu_catalog import gpu_supports_bf16
        # Use the primary (first) target GPU for capability check
        _primary = target_gpus[0] if target_gpus else ""
        if _primary and gpu_supports_bf16(_primary):
            return (_torch.bfloat16, "bfloat16")
        return (_torch.float32, "float32")

    # 5. "default" without target_gpus — normal runtime path.
    #    Let ComfyUI auto-detect at load time by returning None.
    return (None, "default")

# Submission correlation counter
_SUBMISSION_COUNTER: int = 0
_SUBMISSION_COUNTER_LOCK = RLock()

def _next_submission_id() -> str:
    global _SUBMISSION_COUNTER
    with _SUBMISSION_COUNTER_LOCK:
        _SUBMISSION_COUNTER += 1
        return f"s{_SUBMISSION_COUNTER:04d}"


def _get_live_module(mod_name: str) -> Any | None:
    """Return an already-loaded module from sys.modules (never triggers import)."""
    import sys
    return sys.modules.get(mod_name)


# ── Wrapper factories ───────────────────────────────────────────────


def _make_torch_file_wrapper(original: Callable[..., Any]) -> Callable[..., Any]:
    """Wrap ``comfy.utils.load_torch_file`` to emit ``read_start/read_end``.

    Reentrancy-safe: nested calls from within the same thread do not
    duplicate outer events.
    """

    @functools.wraps(original)
    def wrapper(ckpt, safe_load=False, device=None, return_metadata=False):
        before = _torch_file_depth.get()
        _torch_file_depth.set(before + 1)
        _slow_read_state: _SlowReadBeforeState | None = None
        _slow_ru_before: dict[str, Any] | None = None
        _slow_io_before: dict[str, int] | None = None
        _read_outer_ns: int = 0
        _pf_before: _PageFaultSnapshot | None = None
        if before == 0:
            lane = _ACTIVE_LANE_TRACE.get()
            if lane is not None:
                _read_outer_ns = time.monotonic_ns()
                # Capture page-fault snapshot before actual read (CLIP/UNET page-in)
                if _PAGEFAULT_TRACKING and lane._lane in ("CLIP", "UNET"):
                    _pf_before = _PageFaultSnapshot.now()
                lane.read_start()
                if lane._lane == "CLIP":
                    _slow_read_state = _capture_slow_read_before()
                    _slow_ru_before, _slow_io_before = _collect_rusage_and_io_snapshots()
                if lane._lane == "UNET":
                    lane._trace.emit(
                        "unet_load_torch_file_start",
                        phase=lane._phase,
                        metadata={"lane": lane._lane, "path_hash": stable_hash(str(ckpt))[:16]},
                    )
        try:
            return original(ckpt, safe_load=safe_load, device=device, return_metadata=return_metadata)
        finally:
            after = _torch_file_depth.get()
            _torch_file_depth.set(after - 1)
            if before == 0:
                lane = _ACTIVE_LANE_TRACE.get()
                if lane is not None:
                    lane.read_end()
                    _read_dur_ms = round((time.monotonic_ns() - _read_outer_ns) / 1_000_000, 3) if _read_outer_ns else 0.0
                    lane._on_read_completed(read_duration_ms=_read_dur_ms)
                    if lane._lane == "CLIP" and _slow_read_state is not None:
                        _after_mono = time.monotonic_ns()
                        _after_tt = time.thread_time_ns() if hasattr(time, "thread_time_ns") else None
                        _after_pt = time.process_time_ns() if hasattr(time, "process_time_ns") else None
                        _after_tid = _capture_tid()
                        _elapsed = round((_after_mono - _slow_read_state.mono_ns) / 1_000_000, 3)
                        if _elapsed >= _SLOW_READ_THRESHOLD_MS:
                            _slow_ru_after, _slow_io_after = _collect_rusage_and_io_snapshots()
                            _request_trace = _ACTIVE_REQUEST_TRACE.get()
                            _emit_slow_read_line(
                                owner="CLIP",
                                loader_type="load_torch_file",
                                path_str=str(ckpt) if ckpt else "",
                                request_id=str(_request_trace.request_id) if _request_trace is not None else "",
                                restore_session_id=_LATEST_RESTORE_SESSION_ID,
                                restored_instance_id=_LATEST_RESTORED_INSTANCE_ID,
                                before=_slow_read_state,
                                after_mono_ns=_after_mono,
                                after_thread_time_ns=_after_tt,
                                after_process_time_ns=_after_pt,
                                after_tid=_after_tid,
                                before_rusage=_slow_ru_before,
                                after_rusage=_slow_ru_after,
                                before_io=_slow_io_before,
                                after_io=_slow_io_after,
                            )
                    if lane._lane == "UNET":
                        lane._trace.emit(
                            "unet_load_torch_file_end",
                            phase=lane._phase,
                            metadata={"lane": lane._lane, "path_hash": stable_hash(str(ckpt))[:16]},
                        )
                    # Emit page-fault deltas for CLIP/UNET page-in after first access
                    if _pf_before is not None and lane._lane in ("CLIP", "UNET"):
                        _pf_after = _PageFaultSnapshot.now()
                        _delta = _pagefault_delta(_pf_before, _pf_after)
                        _metric_name = "clip_snapshot_pagein_ms" if lane._lane == "CLIP" else "unet_snapshot_pagein_ms"
                        lane._trace.emit(
                            _metric_name.replace("_ms", ""),
                            phase=lane._phase,
                            metadata={
                                "lane": lane._lane,
                                "major_faults": _delta["major_faults"],
                                "minor_faults": _delta["minor_faults"],
                                "duration_ms": _read_dur_ms if _read_outer_ns else 0.0,
                            },
                        )
    wrapper._comfy_modal_read_wrapper = True  # sentinel for idempotence
    return wrapper


def _make_gpu_loader_wrapper(original: Callable[..., Any]) -> Callable[..., Any]:
    """Wrap ``comfy.model_management.load_models_gpu`` to emit commit events.

    Reentrancy-safe.  Emits ``gpu_lane_wait_start/end`` using the real
    ``_MUTATION_LANE`` (non-zero when contention exists) so Phase-2
    wait durations are truthful.  ``gpu_commit_start/end`` bracket the
    actual call with full metadata (restore IDs, model identity,
    caller classification, wall/thread CPU durations).
    """

    @functools.wraps(original)
    def wrapper(models, memory_required=0, force_patch_weights=False,
                minimum_memory_required=None, force_full_load=False):
        before = _gpu_depth.get()
        _gpu_depth.set(before + 1)
        _graph_start_ns = 0
        _graph_thread_start_ns = None
        _graph_process_start_ns = None
        _caller = "not_observed"
        _wrapper_status = "installed"
        _lane_start_ns = 0
        _lane_thread_start_ns = None
        _model_identity_hash = ""
        _pf_h2d_before: _PageFaultSnapshot | None = None
        _h2d_metric_name: str = ""
        # Activation diagnostics record (captured on outermost entry)
        _gpu_record: dict[str, Any] | None = None
        if before == 0:
            count = _gpu_request_call_count_var.get()
            _gpu_request_call_count_var.set(count + 1)
            lane = _ACTIVE_LANE_TRACE.get()
            request_trace = _ACTIVE_REQUEST_TRACE.get()
            _graph_start_ns = time.monotonic_ns()
            _graph_thread_start_ns = time.thread_time_ns() if hasattr(time, "thread_time_ns") else None
            _graph_process_start_ns = time.process_time_ns() if hasattr(time, "process_time_ns") else None
            # Prepare activation diagnostic record.
            _start_minflt = 0
            _start_majflt = 0
            try:
                try:
                    import resource as _r_gpu
                    _start_ru = _r_gpu.getrusage(_r_gpu.RUSAGE_SELF)
                    _start_minflt = _start_ru.ru_minflt
                    _start_majflt = _start_ru.ru_majflt
                except (ImportError, AttributeError):
                    pass
            except Exception:
                pass
            _gpu_alloc_before = None
            _gpu_reserved_before = None
            try:
                import torch as _torch_gpu
                if _torch_gpu.cuda.is_available():
                    _gpu_alloc_before = int(_torch_gpu.cuda.memory_allocated())
                    _gpu_reserved_before = int(_torch_gpu.cuda.memory_reserved())
            except Exception:
                pass
            _gpu_record = {
                "call_index": _gpu_request_call_count_var.get(),
                "caller": "",
                "model_count": len(models),
                "model_types": [type(model).__module__ + "." + type(model).__qualname__ for model in models],
                "model_object_ids": [str(id(model)) for model in models],
                "contains_registered_unet": int(_has_registered_unet_in_models(models)),
                "gpu_allocated_before": _gpu_alloc_before,
                "gpu_reserved_before": _gpu_reserved_before,
                "start_monotonic_ns": _graph_start_ns,
                "_thread_start_ns": _graph_thread_start_ns,
                "_process_start_ns": _graph_process_start_ns,
                "_minor_faults_before": _start_minflt,
                "_major_faults_before": _start_majflt,
            }
            # Classify the caller BEFORE the entry boundary so the entry line
            # logs the ACTUAL classification, never the pre-classification
            # placeholder ("not_observed"/"pending").
            if lane is not None and lane._lane == "UNET":
                _caller = "background_unet_preparation"
            elif lane is not None and lane._lane == "CLIP":
                _caller = "restore_clip_preparation"
            elif lane is not None and lane._lane == "VAE":
                _caller = "restore_vae_preparation"
            elif lane is None and request_trace is not None:
                try:
                    import inspect as _inspect
                    _frames = " ".join(frame.function.lower() for frame in _inspect.stack(context=0)[:12])
                    if "sampler" in _frames:
                        _caller = "sampler_setup"
                    else:
                        _caller = "graph_model_loading"
                except Exception:
                    _caller = "graph_model_loading"
                _model_identity_hash = stable_hash([type(model).__module__ + "." + type(model).__qualname__ for model in models])[:16]
                request_trace.emit("graph_gpu_load_start", phase="execution", metadata={
                    "model_identity_hash": _model_identity_hash,
                    "memory_required": memory_required,
                    "force_patch_weights": force_patch_weights,
                    "force_full_load": force_full_load,
                    "caller_classification": _caller,
                    "gpu_wrapper_status": _wrapper_status,
                    "gpu_request_invocation_count": _gpu_request_call_count_var.get(),
                    "restore_session_id": _LATEST_RESTORE_SESSION_ID,
                    "restored_instance_id": _LATEST_RESTORED_INSTANCE_ID,
                })
            if lane is None and request_trace is None:
                # Installed wrapper called outside any lane/request scope
                _caller = "not_observed"
                global _not_observed_gpu_calls
                _not_observed_gpu_calls += 1
            # ── Authoritative load_models_gpu boundary: entry ──
            # role/identity/device/memory evidence per model, no tensor contents.
            try:
                _gpu_roles = ",".join(
                    _resolve_model_role_for_boundary(m) for m in models
                )
                print(
                    f"[v2.gpu_load_boundary] event=load_models_gpu_start "
                    f"request_id={str(request_trace.request_id) if request_trace is not None else 'absent'} "
                    f"restored_instance_id={_LATEST_RESTORED_INSTANCE_ID or 'absent'} "
                    f"restore_session_id={_LATEST_RESTORE_SESSION_ID or 'absent'} "
                    f"roles={_gpu_roles} "
                    f"model_count={len(models)} "
                    f"contains_registered_unet={_gpu_record['contains_registered_unet']} "
                    f"caller_classification={_caller} "
                    f"gpu_allocated_before={_gpu_alloc_before if _gpu_alloc_before is not None else 'absent'} "
                    f"gpu_reserved_before={_gpu_reserved_before if _gpu_reserved_before is not None else 'absent'}",
                    flush=True,
                )
            except Exception:
                pass
            # Always-on UNET first-CUDA demand start:
            # Record the monotonic_ns when load_models_gpu is first called
            # for a registered UNET in this request, regardless of lane state.
            # Previously this was inside `elif lane is None` so lane-owned
            # calls (e.g. background restore) or any non-None lane during
            # request execution would skip demand tracking.
            # Must stay inside `if before == 0:` scope.
            if request_trace is not None and _has_registered_unet_in_models(models):
                set_unet_gpu_demand_start(request_trace.request_id, time.monotonic_ns())
                request_trace.emit("unet_gpu_demand_start", metadata={
                    "request_id": request_trace.request_id,
                    "caller_classification": _caller,
                })
            if lane is not None:
                lane._on_gpu_commit_about_to_start()
                _get_mutation_lane().acquire(lane._lane if lane else None)
                lane.gpu_lane_wait_start()
                lane.gpu_lane_wait_end()
                # Capture page-fault snapshot before H2D commit
                if _PAGEFAULT_TRACKING:
                    _pf_h2d_before = _PageFaultSnapshot.now()
                    _h2d_metric_name = "clip_h2d_ms" if lane._lane == "CLIP" else "unet_h2d_ms"
                # Compute metadata for lane-owned commit events
                _lane_start_ns = time.monotonic_ns()
                _lane_thread_start_ns = time.thread_time_ns() if hasattr(time, "thread_time_ns") else None
                _model_identity_hash = stable_hash([type(model).__module__ + "." + type(model).__qualname__ for model in models])[:16]
                lane.gpu_commit_start(
                    request_id=str(request_trace.request_id) if request_trace is not None else "",
                    restore_session_id=_LATEST_RESTORE_SESSION_ID,
                    restored_instance_id=_LATEST_RESTORED_INSTANCE_ID,
                    model_identity_hash=_model_identity_hash,
                    memory_required=memory_required,
                    force_patch_weights=force_patch_weights,
                    force_full_load=force_full_load,
                    caller_classification=_caller,
                    gpu_wrapper_status=_wrapper_status,
                    gpu_request_invocation_count=_gpu_request_call_count_var.get(),
                )
        # ── Residency sampler: unet_gpu_load_before (around first UNET-containing call) ──
        _residency_sampler_fired = False
        if before == 0 and request_trace is not None and _has_registered_unet_in_models(models):
            _res_cb = _RESIDENCY_SAMPLER_CALLBACK.get()
            if _res_cb is not None:
                try:
                    _res_cb("unet_gpu_load_before", request_trace)
                except Exception:
                    pass
                _residency_sampler_fired = True
        # ``force_full_load`` only bypasses ComfyUI's low-VRAM calculation;
        # it does not clear a stale ModelPatcher loaded-byte/device state.
        # For the V2 clip_gpu_ready prefill call, normalize the exact armed
        # CLIP patcher while the existing mutation lane is held, immediately
        # before the real load path.  This keeps the subsequent call a normal
        # ComfyUI load (and therefore preserves the existing fire hook), while
        # preventing a zero-effect load from being mistaken for a GPU transfer.
        if (
            before == 0
            and force_full_load
            and lane is not None
            and getattr(lane, "_lane", "") == "prefill"
            and not _has_registered_unet_in_models(models)
        ):
            _prepare_armed_clip_for_force_load(
                models, request_trace or getattr(lane, "_trace", None),
            )
        # ── Synchronous native page-readiness: first request-scoped graph ──
        # UNET activation only.  Conditions: outermost call (before == 0), a
        # request trace, NO active model lane (never a restore-time background
        # lane), and a registered retained UNET in the model list.  The mode
        # gate runs FIRST so that when the candidate is off (default) nothing
        # is claimed, traversed, or called.  The per-request guard guarantees
        # the readiness helper runs at most once per request for the same UNET
        # activation; it is released in the existing request cleanup
        # (modal_app request finally block).  Gated by
        # COMFYMODAL_V2_PAGE_READINESS_MODE=willneed (off by default);
        # synchronous, never schedules a future or duplicates the transfer.
        if (
            before == 0
            and request_trace is not None
            and lane is None
            and page_readiness_mode() == _PAGE_READINESS_MODE_WILLNEED
            and _has_registered_unet_in_models(models)
        ):
            _pr_request_id = str(request_trace.request_id)
            if _unet_page_readiness_begin(_pr_request_id):
                try:
                    _pr_unet = _first_registered_unet_model(models)
                    if _pr_unet is not None:
                        _run_unet_page_readiness(
                            _pr_unet, trace=request_trace, request_id=_pr_request_id,
                        )
                except Exception:
                    pass
        _diag_ok = False
        try:
            _retval = original(models, memory_required=memory_required,
                               force_patch_weights=force_patch_weights,
                               minimum_memory_required=minimum_memory_required,
                               force_full_load=force_full_load)
            _diag_ok = True
            return _retval
        finally:
            after = _gpu_depth.get()
            _gpu_depth.set(after - 1)
            if before == 0:
                lane = _ACTIVE_LANE_TRACE.get()
                request_trace = _ACTIVE_REQUEST_TRACE.get()
                if lane is not None:
                    _lane_end_ns = time.monotonic_ns()
                    _lane_thread_end_ns = time.thread_time_ns() if hasattr(time, "thread_time_ns") else None
                    # Emit H2D page-fault deltas for lane-owned GPU commits
                    if _pf_h2d_before is not None and _h2d_metric_name:
                        _pf_h2d_after = _PageFaultSnapshot.now()
                        _delta = _pagefault_delta(_pf_h2d_before, _pf_h2d_after)
                        lane._trace.emit(
                            _h2d_metric_name.replace("_ms", ""),
                            phase=lane._phase,
                            metadata={
                                "lane": lane._lane,
                                "major_faults": _delta["major_faults"],
                                "minor_faults": _delta["minor_faults"],
                                "duration_ms": round((_lane_end_ns - _lane_start_ns) / 1_000_000, 3),
                                "caller_classification": _caller,
                            },
                        )
                    lane.gpu_commit_end(
                        host_wall_duration_ms=round((_lane_end_ns - _lane_start_ns) / 1_000_000, 3),
                        thread_cpu_duration_ms=round((_lane_thread_end_ns - _lane_thread_start_ns) / 1_000_000, 3) if _lane_thread_end_ns is not None and _lane_thread_start_ns is not None else None,
                        request_id=str(request_trace.request_id) if request_trace is not None else "",
                        restore_session_id=_LATEST_RESTORE_SESSION_ID,
                        restored_instance_id=_LATEST_RESTORED_INSTANCE_ID,
                        model_identity_hash=_model_identity_hash,
                        memory_required=memory_required,
                        force_patch_weights=force_patch_weights,
                        force_full_load=force_full_load,
                        caller_classification=_caller,
                        gpu_wrapper_status=_wrapper_status,
                        gpu_request_invocation_count=_gpu_request_call_count_var.get(),
                    )
                    _get_mutation_lane().release(lane._lane if lane else None)
                elif request_trace is not None:
                    _thread_end_ns = time.thread_time_ns() if hasattr(time, "thread_time_ns") else None
                    request_trace.emit("graph_gpu_load_end", phase="execution", metadata={
                        "host_wall_duration_ms": round((time.monotonic_ns() - _graph_start_ns) / 1_000_000, 3),
                        "thread_cpu_duration_ms": round((_thread_end_ns - _graph_thread_start_ns) / 1_000_000, 3) if _thread_end_ns is not None and _graph_thread_start_ns is not None else None,
                        "caller_classification": _caller,
                        "gpu_wrapper_status": _wrapper_status,
                        "gpu_request_invocation_count": _gpu_request_call_count_var.get(),
                        "restored_instance_id": _LATEST_RESTORED_INSTANCE_ID,
                        "restore_session_id": _LATEST_RESTORE_SESSION_ID,
                        "model_identity_hash": _model_identity_hash,
                        "memory_required": memory_required,
                        "force_patch_weights": force_patch_weights,
                        "force_full_load": force_full_load,
                    })
                # ── Phase 1A candidate (clip_gpu_ready): fire the armed
                # single-use retained-UNET activation exactly once.  Runs
                # AFTER the qualifying successful CLIP load_models_gpu call
                # returned AND the mutation lane was released above; only
                # outermost prefill-lane calls with the exact armed CLIP
                # patcher and no registered UNET qualify.  Uses the prefill
                # lane trace/request id — never _ACTIVE_REQUEST_TRACE (absent
                # in coordinator threads).
                _maybe_fire_clip_gpu_ready_activation(
                    models=models,
                    lane_trace=lane,
                    load_ok=_diag_ok,
                    gpu_allocated_before=_gpu_alloc_before,
                )
                if _diag_ok:
                    emit_post_load_models_gpu_event(models)
                    # load_models_gpu duration measurement (complementary to the
                    # forward-probe-based unet_first_cuda_op emitted from the
                    # actual diffusion model forward).
                    if _caller in ("graph_model_loading", "sampler_setup"):
                        _op_duration_ms: float | None = None
                        if _lane_start_ns:
                            _op_duration_ms = round((time.monotonic_ns() - _lane_start_ns) / 1_000_000, 3)
                        elif _graph_start_ns:
                            _op_duration_ms = round((time.monotonic_ns() - _graph_start_ns) / 1_000_000, 3)
                        if _op_duration_ms is not None:
                            _rt = _ACTIVE_REQUEST_TRACE.get()
                            if _rt is not None:
                                _rt.emit(
                                    "load_models_gpu_duration",
                                    phase="execution",
                                    metadata={
                                        "caller_classification": _caller,
                                        "duration_ms": _op_duration_ms,
                                        "gpu_request_invocation_count": _gpu_request_call_count_var.get(),
                                        "model_identity_hash": _model_identity_hash,
                                        "memory_required": memory_required,
                                    },
                                )
                # ── Append GPU record to activation diagnostics state ──
                if _gpu_record is not None and _diag_ok:
                    try:
                        try:
                            import resource as _r_end
                            _has_res_end = True
                            _end_ru = _r_end.getrusage(_r_end.RUSAGE_SELF)
                        except ImportError:
                            _has_res_end = False
                            _end_ru = None
                        _end_wall_ns = time.monotonic_ns()
                        _end_thread_ns = time.thread_time_ns() if hasattr(time, "thread_time_ns") else 0
                        _end_process_ns = time.process_time_ns() if hasattr(time, "process_time_ns") else 0
                        # GPU alloc/reserved after
                        _gpu_alloc_after = None
                        _gpu_reserved_after = None
                        try:
                            import torch as _torch_after
                            if _torch_after.cuda.is_available():
                                _gpu_alloc_after = int(_torch_after.cuda.memory_allocated())
                                _gpu_reserved_after = int(_torch_after.cuda.memory_reserved())
                        except Exception:
                            pass
                        _gpu_record["caller"] = _caller
                        _gpu_record["end_monotonic_ns"] = _end_wall_ns
                        _gpu_record["gpu_allocated_after"] = _gpu_alloc_after
                        _gpu_record["gpu_reserved_after"] = _gpu_reserved_after
                        if _end_ru is not None:
                            _end_minflt = _end_ru.ru_minflt
                            _end_majflt = _end_ru.ru_majflt
                        else:
                            _end_minflt = 0
                            _end_majflt = 0
                        _gpu_record["wall_ms"] = round((_end_wall_ns - _gpu_record["start_monotonic_ns"]) / 1_000_000, 3)
                        _process_start = _gpu_record.get("_process_start_ns")
                        _thread_start = _gpu_record.get("_thread_start_ns")
                        _gpu_record["process_cpu_ms"] = round((_end_process_ns - _process_start) / 1_000_000, 3) if _process_start is not None else None
                        _gpu_record["thread_cpu_ms"] = round((_end_thread_ns - _thread_start) / 1_000_000, 3) if _thread_start is not None else None
                        _gpu_record["minor_faults"] = max(0, _end_minflt - _gpu_record.get("_minor_faults_before", 0))
                        _gpu_record["major_faults"] = max(0, _end_majflt - _gpu_record.get("_major_faults_before", 0))
                        _gpu_record["gpu_allocated_delta_bytes"] = (
                            _gpu_alloc_after - _gpu_record["gpu_allocated_before"]
                            if _gpu_alloc_after is not None and _gpu_record.get("gpu_allocated_before") is not None
                            else None
                        )
                        for _k in ("_thread_start_ns", "_process_start_ns", "_minor_faults_before", "_major_faults_before"):
                            _gpu_record.pop(_k, None)
                        _diag_state = _ACTIVATION_DIAGNOSTIC_STATE.get()
                        if _diag_state is not None:
                            _diag_state["gpu_load_calls"].append(dict(_gpu_record))
                        if request_trace is not None:
                            request_trace.emit(
                                "load_models_gpu_diagnostic",
                                phase="execution",
                                metadata=dict(_gpu_record),
                            )
                        # ── Authoritative load_models_gpu boundary: exit ──
                        # Post-load device/cache/memory evidence so activation is
                        # proven by data, not only by fast return.
                        try:
                            _gpu_roles_exit = ",".join(
                                _resolve_model_role_for_boundary(m) for m in models
                            )
                            _gpu_mem_delta = _gpu_record.get("gpu_allocated_delta_bytes")
                            print(
                                f"[v2.gpu_load_boundary] event=load_models_gpu_end "
                                f"request_id={str(request_trace.request_id) if request_trace is not None else 'absent'} "
                                f"restored_instance_id={_LATEST_RESTORED_INSTANCE_ID or 'absent'} "
                                f"restore_session_id={_LATEST_RESTORE_SESSION_ID or 'absent'} "
                                f"roles={_gpu_roles_exit} "
                                f"model_count={len(models)} "
                                f"caller_classification={_caller} "
                                f"wall_ms={_gpu_record.get('wall_ms')} "
                                f"gpu_allocated_after={_gpu_alloc_after if _gpu_alloc_after is not None else 'absent'} "
                                f"gpu_allocated_delta_bytes={_gpu_mem_delta if _gpu_mem_delta is not None else 'absent'}",
                                flush=True,
                            )
                        except Exception:
                            pass
                    except Exception:
                        pass
                # ── Residency sampler: unet_gpu_load_after ──
                if _residency_sampler_fired:
                    _res_cb_after = _RESIDENCY_SAMPLER_CALLBACK.get()
                    if _res_cb_after is not None:
                        try:
                            _res_cb_after("unet_gpu_load_after", request_trace)
                        except Exception:
                            pass
    wrapper._comfy_modal_gpu_wrapper = True
    return wrapper


# ── Deep-diagnostic safetensors/torch.load decomposition wrappers ───
# Only active when:
#   1. _DIAGNOSTIC_FLAG is True
#   2. The calling thread's _DEEP_TARGET_PATH is non-empty AND matches
#      the file being accessed (avoid logging unrelated model loads)
#   3. The active lane trace is UNET
# These are globally installed but filtered by thread-local path, so
# unrelated file activity is never logged.


class _SafeOpenProxy:
    """Delegating proxy for safetensors.safe_open that wraps get_tensor
    for aggregate diagnostics without mutating the native C-extension object.
    _orig_gt(k) is called exactly once per requested tensor key.
    """
    def __init__(self, wrapped, orig_gt, count_agg, bytes_agg):
        object.__setattr__(self, "_wrapped", wrapped)
        object.__setattr__(self, "_orig_gt", orig_gt)
        object.__setattr__(self, "_count_agg", count_agg)
        object.__setattr__(self, "_bytes_agg", bytes_agg)

    def __getattr__(self, name):
        if name == "get_tensor":
            return lambda k: self._proxy_get_tensor(k)
        return getattr(self._wrapped, name)

    def _proxy_get_tensor(self, k):
        lane2 = _ACTIVE_LANE_TRACE.get()
        _start_ns = 0
        if lane2 is not None and lane2._lane == "UNET" and _DIAGNOSTIC_FLAG:
            _start_ns = time.monotonic_ns()
        tensor = self._orig_gt(k)
        if lane2 is not None and lane2._lane == "UNET" and _DIAGNOSTIC_FLAG and _start_ns:
            self._count_agg[0] += 1
            try:
                self._bytes_agg[0] += tensor.numel() * tensor.element_size()
            except Exception:
                pass
        return tensor

    def __enter__(self):
        try:
            return self._wrapped.__enter__()
        except AttributeError:
            return self

    def __exit__(self, *exc):
        lane2 = _ACTIVE_LANE_TRACE.get()
        if lane2 is not None:
            lane2._trace.emit("unet_tensor_materialize_aggregated", phase="restore", metadata={
                "tensor_count": self._count_agg[0],
                "total_bytes": self._bytes_agg[0],
            })
        return self._wrapped.__exit__(*exc) if hasattr(self._wrapped, "__exit__") else None

    def keys(self):
        return self._wrapped.keys()


def _make_safetensors_open_wrapper(original: Callable[..., Any]) -> Callable[..., Any]:
    """Wrap ``safetensors.safe_open`` to emit open/parse/materialize stages.

    Uses a reentrancy guard and thread-local path filtering.  Emits:
    - ``unet_safetensors_open_start/end`` for the ``safe_open()`` call itself
    - ``unet_safetensors_parse_start/end`` for the ``f.keys()`` header parse
    - ``unet_tensor_materialize_start/end`` around ``f.get_tensor()`` calls
    When the safetensors library does not expose separable boundaries, emits
    ``unet_safetensors_load_combined_start/end`` with ``stage_split_available=false``.
    """

    @functools.wraps(original)
    def wrapper(file, framework="pt", device="cpu", **kwargs):
        before = _deep_st_depth.get()
        _deep_st_depth.set(before + 1)
        lane = _ACTIVE_LANE_TRACE.get()
        target_path = _DEEP_TARGET_PATH.get()
        _outer = (before == 0)
        _eligible = (_outer and _DIAGNOSTIC_FLAG and lane is not None
                     and lane._lane == "UNET" and target_path
                     and (isinstance(file, str) and target_path in file))
        _result = None
        if _eligible:
            lane._trace.emit("unet_safetensors_open_start", phase="restore",
                             metadata={"path": str(file)[-80:]})
        try:
            _result = original(file, framework=framework, device=device, **kwargs)
            if _eligible and _outer:
                lane._trace.emit("unet_safetensors_open_end", phase="restore")
                # Check if the safetensors object has separable keys()
                _stage_split = (_result is not None
                                and callable(getattr(_result, "keys", None))
                                and callable(getattr(_result, "get_tensor", None)))
                if _stage_split:
                    lane._trace.emit("unet_safetensors_parse_start", phase="restore")
                    try:
                        _keys = list(_result.keys())
                        lane._trace.emit("unet_safetensors_parse_end", phase="restore",
                                         metadata={"tensor_count": len(_keys),
                                                   "stage_split_available": True})
                    except Exception:
                        lane._trace.emit("unet_safetensors_parse_end", phase="restore",
                                         metadata={"stage_split_available": False})
                    # Return a delegating proxy instead of mutating the native
                    # safe_open object (C-extension — attributes are read-only).
                    _tensor_count_agg = [0]
                    _tensor_bytes_agg = [0]
                    _orig_get_tensor = _result.get_tensor

                    _result = _SafeOpenProxy(_result, _orig_get_tensor,
                                             _tensor_count_agg, _tensor_bytes_agg)
                else:
                    lane._trace.emit("unet_safetensors_load_combined_start", phase="restore",
                                     metadata={"stage_split_available": False})
                    lane._trace.emit("unet_safetensors_load_combined_end", phase="restore")
            return _result
        finally:
            after = _deep_st_depth.get()
            _deep_st_depth.set(after - 1)
    wrapper._comfy_modal_deep_st_wrapper = True
    return wrapper


def _make_torch_load_wrapper(original: Callable[..., Any]) -> Callable[..., Any]:
    """Wrap ``torch.load`` to emit combined load event for non-safetensors files.

    Thread-local path filtering.  Emits ``unet_load_torch_file_start/end``.
    """

    @functools.wraps(original)
    def wrapper(f, map_location=None, weights_only=True, **kwargs):
        before = _deep_tl_depth.get()
        _deep_tl_depth.set(before + 1)
        lane = _ACTIVE_LANE_TRACE.get()
        target_path = _DEEP_TARGET_PATH.get()
        _outer = (before == 0)
        _file_str = str(getattr(f, "name", f)) if not isinstance(f, str) else str(f)
        _eligible = (_outer and _DIAGNOSTIC_FLAG and lane is not None
                     and lane._lane == "UNET" and target_path
                     and target_path in _file_str)
        if _eligible:
            lane._trace.emit("unet_load_torch_file_start", phase="restore",
                             metadata={"path": _file_str[-80:]})
        try:
            return original(f, map_location=map_location, weights_only=weights_only, **kwargs)
        finally:
            after = _deep_tl_depth.get()
            _deep_tl_depth.set(after - 1)
            if _eligible and _outer:
                lane._trace.emit("unet_load_torch_file_end", phase="restore")
    wrapper._comfy_modal_deep_tl_wrapper = True
    return wrapper


def _make_clip_load_wrapper(original):
    import functools as _ft
    @_ft.wraps(original)
    def wrapper(*args, **kwargs):
        before = _clip_depth.get()
        _clip_depth.set(before + 1)
        lane = _ACTIVE_LANE_TRACE.get()
        emit = (before == 0 and lane is not None and lane._lane == "CLIP")
        _outer_start_ns = time.monotonic_ns() if emit else 0
        _prior_children = _clip_cpu_prepare_children.get()
        _result = None
        if emit:
            _clip_cpu_prepare_children.set([])
            lane._trace.emit("clip_load_call_start", phase="restore", metadata={
                "lane": lane._lane,
            })
        try:
            _result = original(*args, **kwargs)
            return _result
        finally:
            after = _clip_depth.get()
            _clip_depth.set(after - 1)
            if emit:
                _outer_dur_ms = round((time.monotonic_ns() - _outer_start_ns) / 1_000_000, 3)
                _children = _clip_cpu_prepare_children.get() or []
                _children_total = round(sum(c[1] for c in _children), 3)
                # Signed residual — allow negative when children exceed total
                _residual = round(_outer_dur_ms - _children_total, 3)
                # Determine status from read count match
                _mismatch = (lane._actual_read_count != lane.expected_read_count
                             if lane.expected_read_count > 0 else False)
                _end_status = "read_count_mismatch" if _mismatch else "ok"
                if _children_total > _outer_dur_ms:
                    _end_status = "overlap_error"
                # ── Cache publication observation ────────────────
                if _result is not None:
                    _patcher = getattr(_result, "patcher", None)
                    if _patcher is not None:
                        _cpi = getattr(_patcher, "cached_patcher_init", None)
                        if _cpi is not None:
                            lane._trace.emit("clip_cache_publish", phase="restore", metadata={
                                "cache_type": "cached_patcher_init",
                                "clip_cpu_prepare_total_ms": _outer_dur_ms,
                            })
                _clip_cpu_prepare_children.set(_prior_children)
                # clip_file_read_total_ms from per-lane read-duration accumulator.
                _clip_read_raw = lane._clip_read_total_ms
                _clip_file_read = round(_clip_read_raw, 3) if _clip_read_raw else None
                _clip_post_read_cpu = (round(max(0.0, _outer_dur_ms - _clip_read_raw), 3)
                                       if _clip_read_raw else None)
                lane._trace.emit("clip_load_call_end", phase="restore", metadata={
                    "lane": lane._lane,
                    "clip_load_call_total_ms": _outer_dur_ms,
                    "clip_file_read_total_ms": _clip_file_read,
                    "clip_post_read_cpu_total_ms": _clip_post_read_cpu,
                    "status": _end_status,
                })
                # post_read_total is None when _on_read_completed never fired
                _post_read_total = _outer_dur_ms if lane._cpu_prepare_started else None
                lane._trace.emit("clip_cpu_prepare_end", phase="restore", metadata={
                    "lane": lane._lane,
                    "clip_cpu_prepare_total_ms": _post_read_total,
                    "children": [(name, dur) for name, dur in _children],
                    "clip_cpu_prepare_measured_children_ms": _children_total,
                    "clip_cpu_prepare_residual_ms": _residual,
                    "clip_file_read_total_ms": _clip_file_read,
                    "status": _end_status,
                })
                # Extract named children from trace events for the summary
                _evts = lane._trace.events
                _named_map: dict[str, float] = {}
                for _ev in _evts:
                    _en = _ev.name
                    _meta = getattr(_ev, "metadata", None) or {}
                    _dur = _meta.get("duration_ms")
                    if _dur is None:
                        continue
                    # Match clip_*_end events, handling double prefix
                    if _en.endswith("_end") and "clip_" in _en:
                        # Extract base name after clip_ prefix(es)
                        _base = _en.replace("clip_clip_", "clip_", 1)
                        if _base.startswith("clip_"):
                            _short = _base[len("clip_"):-len("_end")]
                        else:
                            _short = _base[:-len("_end")]
                        _named_map[_short] = (_named_map.get(_short, 0) or 0) + _dur
                    # Also match clip_clip_ double-prefix (already handled above)
                # Map to named fields
                _known_fields = {
                    "load_text_encoder_state_dicts": "load_text_encoder_state_dicts_ms",
                    "detect_te_model": "detect_te_model_ms",
                    "text_transformers_convert": "state_dict_conversion_ms",
                    "clip_text_transformers_convert": "state_dict_conversion_ms",
                    "constructor": "clip_constructor_ms",
                    "model_patcher_constructor": "model_patcher_ms",
                    "cond_stage_model_init": "cond_stage_model_init_ms",
                    "tokenizer_init": "tokenizer_init_ms",
                    "load_sd_weights": "load_sd_weights_ms",
                }
                _s = lambda k: _named_map.get(k)
                # double-prefix variant also maps to state_dict_conversion
                _sd_contrib = 0.0
                for _k in ("text_transformers_convert", "clip_text_transformers_convert", "convert_old_quants"):
                    _sd_contrib += _named_map.get(_k, 0) or 0
                if _sd_contrib:
                    _named_map["state_dict_conversion"] = _sd_contrib
                # ── Compute constructor residual ────────────────────
                _ctor_ms = _named_map.get("constructor")
                _csm_init = _named_map.get("cond_stage_model_init")
                _tok_init = _named_map.get("tokenizer_init")
                _lsd_w = _named_map.get("load_sd_weights")
                _mp_ms = _named_map.get("model_patcher_constructor")
                _ctor_residual: float | None = None
                if _ctor_ms is not None:
                    _known_ctor = [v for v in (_csm_init, _tok_init, _lsd_w, _mp_ms) if v is not None]
                    _ctor_residual = round(_ctor_ms - sum(_known_ctor), 3) if _known_ctor else None
                _emit_clip_cpu_children_summary(
                    post_read_total_ms=_post_read_total,
                    file_read_total_ms=_clip_file_read,
                    children=_children,
                    load_text_encoder_state_dicts_ms=_named_map.get("load_text_encoder_state_dicts"),
                    detect_te_model_ms=_named_map.get("detect_te_model"),
                    state_dict_conversion_ms=_named_map.get("state_dict_conversion"),
                    clip_constructor_ms=_named_map.get("constructor"),
                    cond_stage_model_init_ms=_named_map.get("cond_stage_model_init"),
                    tokenizer_init_ms=_named_map.get("tokenizer_init"),
                    load_sd_weights_ms=_named_map.get("load_sd_weights"),
                    model_patcher_ms=_named_map.get("model_patcher_constructor"),
                    constructor_residual_ms=_ctor_residual,
                    cache_publish_ms=_named_map.get("cache_publish"),
                    measured_children_ms=_children_total,
                    residual_ms=_residual,
                    status=_end_status,
                )
    wrapper._comfy_modal_clip_wrapper = True
    return wrapper


def _make_clip_subfn_wrapper(short_name, original, category):
    import functools as _ft
    @_ft.wraps(original)
    def wrapper(*args, **kwargs):
        lane = _ACTIVE_LANE_TRACE.get()
        emit = (lane is not None and lane._lane == "CLIP")
        _fn_start_ns = time.monotonic_ns() if emit else 0
        if emit:
            lane._trace.emit("clip_" + short_name + "_start", phase="restore", metadata={"category": category})
        _before_depth = _clip_subfn_depth.get()
        _clip_subfn_depth.set(_before_depth + 1)
        try:
            return original(*args, **kwargs)
        finally:
            _after_depth = _clip_subfn_depth.get()
            _clip_subfn_depth.set(_after_depth - 1)
            if emit:
                _dur_ms = round((time.monotonic_ns() - _fn_start_ns) / 1_000_000, 3)
                lane._trace.emit("clip_" + short_name + "_end", phase="restore", metadata={
                    "category": category, "duration_ms": _dur_ms})
                # Only direct children (depth=0 before call) contribute to measured sum
                if _before_depth == 0:
                    _children = _clip_cpu_prepare_children.get()
                    if _children is not None:
                        _children.append((short_name, _dur_ms))
    setattr(wrapper, _SENTINEL_CLIP_SUBFN, True)
    return wrapper


class _ClipTargetProxy:
    """Shallow proxy around a CLIP target that intercepts ``.clip`` and
    ``.tokenizer`` attribute access, wrapping the retrieved callables with
    timing instrumentation.  All other attribute access passes through to
    the original target unchanged, preserving behavior.

    Only created when a CLIP constructor wrapper is active and the lane
    is CLIP.  A non-functional proxy (``copy.copy`` unavailable) falls
    back to the original target without failing the load.
    """

    def __init__(self, original_target: Any, lane_trace: Any) -> None:
        object.__setattr__(self, "_original_target", original_target)
        # Accept ModelLaneTrace or RuntimeTrace; extract _trace for emit()
        object.__setattr__(self, "_trace",
                           getattr(lane_trace, "_trace", lane_trace))

    def __getattr__(self, name: str) -> Any:
        if name == "clip":
            return self._wrap_clip()
        elif name == "tokenizer":
            return self._wrap_tokenizer()
        return getattr(self._original_target, name)

    def _wrap_clip(self) -> Any:
        orig_clip = self._original_target.clip
        trace = self._trace

        @functools.wraps(orig_clip)
        def _timed_clip(*args: Any, **kwargs: Any) -> Any:
            trace.emit("clip_cond_stage_model_init_start", phase="restore")
            _start_ns = time.monotonic_ns()
            try:
                return orig_clip(*args, **kwargs)
            finally:
                _dur = round((time.monotonic_ns() - _start_ns) / 1_000_000, 3)
                trace.emit("clip_cond_stage_model_init_end", phase="restore",
                           metadata={"duration_ms": _dur})
        return _timed_clip

    def _wrap_tokenizer(self) -> Any:
        orig_tokenizer = self._original_target.tokenizer
        trace = self._trace

        @functools.wraps(orig_tokenizer)
        def _timed_tokenizer(*args: Any, **kwargs: Any) -> Any:
            trace.emit("clip_tokenizer_init_start", phase="restore")
            _start_ns = time.monotonic_ns()
            try:
                return orig_tokenizer(*args, **kwargs)
            finally:
                _dur = round((time.monotonic_ns() - _start_ns) / 1_000_000, 3)
                trace.emit("clip_tokenizer_init_end", phase="restore",
                           metadata={"duration_ms": _dur})
        return _timed_tokenizer


def _make_clip_load_sd_wrapper(original: Callable[..., Any]) -> Callable[..., Any]:
    """Wrap ``comfy.sd.CLIP.load_sd`` with timing instrumentation.

    Only emits ``clip_load_sd_weights_start/end`` events when a CLIP
    constructor wrapper is active (``_clip_constructor_depth > 0``) AND
    the active lane is CLIP.  Outside the constructor, the wrapper
    transparently forwards with zero overhead.

    Sentinel-guarded for idempotent global install.
    """
    import functools as _ft

    @_ft.wraps(original)
    def wrapper(self: Any, sd: Any, full_model: bool = False) -> Any:
        lane = _ACTIVE_LANE_TRACE.get()
        emit = (lane is not None and lane._lane == "CLIP"
                and _clip_constructor_depth.get() > 0)
        _start_ns = time.monotonic_ns() if emit else 0
        if emit:
            lane._trace.emit("clip_load_sd_weights_start", phase="restore")
        try:
            return original(self, sd, full_model=full_model)
        finally:
            if emit:
                _dur = round((time.monotonic_ns() - _start_ns) / 1_000_000, 3)
                lane._trace.emit("clip_load_sd_weights_end", phase="restore",
                                 metadata={"duration_ms": _dur})
    setattr(wrapper, _SENTINEL_CLIP_LOAD_SD, True)
    return wrapper


def _make_clip_constructor_wrapper(original):
    """Wrap ``comfy.sd.CLIP.__init__`` to emit ``clip_constructor_start/end``
    and proxy ``target.clip`` / ``target.tokenizer`` + ``self.load_sd`` for
    truthful live child attribution (``clip_cond_stage_model_init``,
    ``clip_tokenizer_init``, ``clip_load_sd_weights``).

    Only active when ``_ACTIVE_LANE_TRACE`` is set AND the current lane
    is ``CLIP``.  Reentrancy-safe via ``_clip_constructor_depth``.
    Emitted spans are NOT recorded into ``_clip_cpu_prepare_children`` —
    they are nested inside ``load_text_encoder_state_dicts`` which is the
    direct measured owner.
    """
    import functools as _ft

    @_ft.wraps(original)
    def wrapper(self, *args: Any, **kwargs: Any) -> None:
        before = _clip_constructor_depth.get()
        _clip_constructor_depth.set(before + 1)
        lane = _ACTIVE_LANE_TRACE.get()
        emit = (before == 0 and lane is not None and lane._lane == "CLIP")
        _fn_start_ns = time.monotonic_ns() if emit else 0

        if emit:
            # ── Proxy target.clip / target.tokenizer ──────────────
            _original_target = args[0] if args else kwargs.get("target")
            if _original_target is not None:
                try:
                    import copy as _copy
                    _proxy = _ClipTargetProxy(_original_target, lane)
                    if args:
                        _new_args = list(args)
                        _new_args[0] = _proxy
                        args = tuple(_new_args)
                    else:
                        kwargs = dict(kwargs)
                        kwargs["target"] = _proxy
                except Exception:
                    pass  # Fall back to original target without failing
            lane._trace.emit("clip_constructor_start", phase="restore")
        try:
            return original(self, *args, **kwargs)
        finally:
            after = _clip_constructor_depth.get()
            _clip_constructor_depth.set(after - 1)
            if emit:
                _dur_ms = round((time.monotonic_ns() - _fn_start_ns) / 1_000_000, 3)
                lane._trace.emit("clip_constructor_end", phase="restore", metadata={
                    "duration_ms": _dur_ms,
                })
                # NOT recorded into _clip_cpu_prepare_children — nested inside
                # load_text_encoder_state_dicts which is the direct measured owner.
    setattr(wrapper, _SENTINEL_CLIP_CONSTRUCTOR, True)
    return wrapper


# ── Shared convert_old_quants wrapper ───────────────────────────────
# Lane-aware wrapper installed once for comfy.utils.convert_old_quants.
# Emits either clip_convert_old_quants_* or unet_convert_old_quants_*
# depending on the active lane.  Children are recorded into the
# appropriate per-lane list for residual/non-overlap computation.

_shared_convert_old_quants_installed: bool = False


def _make_convert_old_quants_wrapper(original):
    import functools as _ft

    @_ft.wraps(original)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        lane = _ACTIVE_LANE_TRACE.get()
        if lane is None:
            return original(*args, **kwargs)
        _fn_start_ns = time.monotonic_ns()
        if lane._lane == "CLIP":
            lane._trace.emit("clip_convert_old_quants_start", phase="restore", metadata={"category": "utils"})
        elif lane._lane == "UNET":
            lane._trace.emit("unet_convert_old_quants_start", phase="restore", metadata={"category": "utils"})
        try:
            return original(*args, **kwargs)
        finally:
            _dur_ms = round((time.monotonic_ns() - _fn_start_ns) / 1_000_000, 3)
            if lane._lane == "CLIP":
                lane._trace.emit("clip_convert_old_quants_end", phase="restore", metadata={
                    "category": "utils", "duration_ms": _dur_ms})
                # Only direct children (depth=0) contribute to measured sum
                if _clip_subfn_depth.get() == 0:
                    _children = _clip_cpu_prepare_children.get()
                    if _children is not None:
                        _children.append(("convert_old_quants", _dur_ms))
            elif lane._lane == "UNET":
                lane._trace.emit("unet_convert_old_quants_end", phase="restore", metadata={
                    "category": "utils", "duration_ms": _dur_ms})
                # Only direct children (nesting depth 0) contribute to measured sum
                if _unet_subfn_nesting_depth.get() == 0:
                    _children = _child_durations.get()
                    if _children is not None:
                        _children.append(("convert_old_quants", _dur_ms))
    setattr(wrapper, _SENTINEL_SHARED_COQ, True)
    return wrapper


def _install_shared_convert_old_quants_wrapper() -> str:
    """Install lane-aware wrapper on comfy.utils.convert_old_quants once."""
    global _shared_convert_old_quants_installed
    if _shared_convert_old_quants_installed:
        return "already_installed"
    mod = _get_live_module("comfy.utils")
    if mod is None:
        return "unavailable"
    original = getattr(mod, "convert_old_quants", None)
    if not callable(original):
        return "unavailable"
    if getattr(original, _SENTINEL_SHARED_COQ, False):
        _shared_convert_old_quants_installed = True
        return "already_installed"
    with _wrappers_lock:
        if _shared_convert_old_quants_installed:
            return "already_installed"
        if getattr(mod.convert_old_quants, _SENTINEL_SHARED_COQ, False):
            _shared_convert_old_quants_installed = True
            return "already_installed"
        mod.convert_old_quants = _make_convert_old_quants_wrapper(mod.convert_old_quants)
        _shared_convert_old_quants_installed = True
    return "installed"


# ── UNET model construction wrappers ────────────────────────────────
# Wrap ModelPatcher/CoreModelPatcher constructors and model.to() so
# model-construction children are captured in measured_direct_children_ms.


def _make_model_patcher_constructor_wrapper(original):
    """Wrap ``model_patcher.ModelPatcher().__init__`` (or subclass) with lane guard.

    Extends the existing UNET-only instrumentation to also emit named
    ``clip_model_patcher_constructor_start/end`` events when the active
    lane is CLIP.  CLIP-lane spans are NOT recorded into
    ``_clip_cpu_prepare_children`` — they are nested inside
    ``load_text_encoder_state_dicts`` which is the direct measured owner.
    UNET-lane spans are recorded into ``_child_durations`` as before.
    """
    import functools as _ft

    @_ft.wraps(original)
    def wrapper(self, *args: Any, **kwargs: Any) -> None:
        lane = _ACTIVE_LANE_TRACE.get()
        emit_unet = (lane is not None and lane._lane == "UNET")
        emit_clip = (lane is not None and lane._lane == "CLIP")
        _fn_start_ns = time.monotonic_ns() if (emit_unet or emit_clip) else 0
        if emit_unet:
            lane._trace.emit("unet_model_patcher_constructor_start", phase="restore")
        elif emit_clip:
            lane._trace.emit("clip_model_patcher_constructor_start", phase="restore")
        try:
            result = original(self, *args, **kwargs)
            # Install SAMPLER_SAMPLE wrapper via the shared helper.
            # The helper itself emits a concise exception-type line and returns
            # False on failure — never silently swallows installation failure.
            if hasattr(self, "model_options"):
                from comfymodal_runtime.runtime_executor import ensure_sampling_timing_wrapper
                ensure_sampling_timing_wrapper(self)
            # Register every ModelPatcher for UNET first-CUDA timing.
            # Idempotent: duplicate registrations for the same diffusion_model
            # are silently ignored by register_unet_forward_probe.
            try:
                from comfymodal_runtime.unet_forward_probe import register_unet_forward_probe as _reg_unet
                _reg_unet(self, source="model_patcher_constructor")
            except Exception:
                pass
            return result
        finally:
            if emit_unet:
                _dur_ms = round((time.monotonic_ns() - _fn_start_ns) / 1_000_000, 3)
                lane._trace.emit("unet_model_patcher_constructor_end", phase="restore", metadata={
                    "duration_ms": _dur_ms})
                _children = _child_durations.get()
                if _children is not None:
                    _children.append(("model_patcher_constructor", _dur_ms))
            elif emit_clip:
                _dur_ms = round((time.monotonic_ns() - _fn_start_ns) / 1_000_000, 3)
                lane._trace.emit("clip_model_patcher_constructor_end", phase="restore", metadata={
                    "duration_ms": _dur_ms})
                # NOT recorded into _clip_cpu_prepare_children — nested inside
                # load_text_encoder_state_dicts which is the direct measured owner.
    setattr(wrapper, _SENTINEL_MODEL_PATCHER, True)
    return wrapper


def _make_model_to_wrapper(original):
    """Wrap ``model.to(...)`` with UNET-lane guard for direct ownership measurement."""
    import functools as _ft

    @_ft.wraps(original)
    def wrapper(self, *args: Any, **kwargs: Any) -> Any:
        lane = _ACTIVE_LANE_TRACE.get()
        emit = (lane is not None and lane._lane == "UNET")
        _fn_start_ns = time.monotonic_ns() if emit else 0
        if emit:
            lane._trace.emit("unet_model_to_start", phase="restore")
        try:
            return original(self, *args, **kwargs)
        finally:
            if emit:
                _dur_ms = round((time.monotonic_ns() - _fn_start_ns) / 1_000_000, 3)
                lane._trace.emit("unet_model_to_end", phase="restore", metadata={
                    "duration_ms": _dur_ms})
                _children = _child_durations.get()
                if _children is not None:
                    _children.append(("model_to", _dur_ms))
    setattr(wrapper, _SENTINEL_MODEL_TO, True)
    return wrapper


# ── ModelPatcher.load aggregate-timing wrappers (narrow timers) ──────
# Four narrow wrappers installed alongside existing core/model_patcher
# wrappers.  Only active during an active request trace AND outer
# ModelPatcher.load scope.  Produce one summary event on outer exit:
#   model_patcher_load_breakdown
# with wall_ms, thread_cpu_ms, process_cpu_ms for total, plus traversal,
# patch_weight (count/wall/process), cast (count/wall/process), and
# residual wall/process.


def _make_model_patcher_load_breakdown_wrapper(original):
    """Wrap ModelPatcher.load / ModelPatcherDynamic.load with breakdown timing.

    Only emits ``model_patcher_load_breakdown`` when ``_ACTIVE_REQUEST_TRACE``
    is set and this is the outermost invocation.  Sets up a thread-local
    ``_model_patcher_breakdown`` dict consumed by the inner _load_list,
    patch_weight_to_device, and cast_to_device wrappers.
    """
    import functools as _ft

    @_ft.wraps(original)
    def wrapper(self, *args, **kwargs):
        before = _model_patcher_load_depth.get()
        _model_patcher_load_depth.set(before + 1)
        request_trace = _ACTIVE_REQUEST_TRACE.get()
        emit = (before == 0 and request_trace is not None)
        _breakdown = None
        if emit:
            _breakdown = {
                "outer_start_ns": time.monotonic_ns(),
                "outer_thread_start_ns": time.thread_time_ns() if hasattr(time, "thread_time_ns") else None,
                "outer_process_start_ns": time.process_time_ns() if hasattr(time, "process_time_ns") else None,
                "load_list_wall_ns": 0,
                "load_list_process_start_ns": None,
                "load_list_process_end_ns": None,
                "patch_weight_count": 0,
                "patch_weight_wall_ns": 0,
                "patch_weight_process_ns": 0,
                "cast_count": 0,
                "cast_wall_ns": 0,
                "cast_process_ns": 0,
            }
            _model_patcher_breakdown.set(_breakdown)
        try:
            return original(self, *args, **kwargs)
        finally:
            after = _model_patcher_load_depth.get()
            _model_patcher_load_depth.set(after - 1)
            if emit and _breakdown is not None:
                _outer_end_ns = time.monotonic_ns()
                _outer_thread_end_ns = time.thread_time_ns() if hasattr(time, "thread_time_ns") else None
                _outer_process_end_ns = time.process_time_ns() if hasattr(time, "process_time_ns") else None
                _wall_ms = round((_outer_end_ns - _breakdown["outer_start_ns"]) / 1_000_000, 3)
                _thread_ms = round((_outer_thread_end_ns - _breakdown["outer_thread_start_ns"]) / 1_000_000, 3) if _breakdown.get("outer_thread_start_ns") is not None and _outer_thread_end_ns is not None else None
                _process_ms = round((_outer_process_end_ns - _breakdown["outer_process_start_ns"]) / 1_000_000, 3) if _breakdown.get("outer_process_start_ns") is not None and _outer_process_end_ns is not None else None
                # Traversal (_load_list)
                _traversal_wall = round(_breakdown["load_list_wall_ns"] / 1_000_000, 3) if _breakdown["load_list_wall_ns"] else 0.0
                _traversal_process: float | None = None
                if _breakdown["load_list_process_start_ns"] is not None and _breakdown["load_list_process_end_ns"] is not None:
                    _traversal_process = round((_breakdown["load_list_process_end_ns"] - _breakdown["load_list_process_start_ns"]) / 1_000_000, 3)
                # Patch-weight aggregate
                _pw_wall = round(_breakdown["patch_weight_wall_ns"] / 1_000_000, 3) if _breakdown["patch_weight_wall_ns"] else 0.0
                _pw_process: float | None = None
                if _breakdown["patch_weight_process_ns"]:
                    _pw_process = round(_breakdown["patch_weight_process_ns"] / 1_000_000, 3)
                # Cast aggregate
                _cast_wall = round(_breakdown["cast_wall_ns"] / 1_000_000, 3) if _breakdown["cast_wall_ns"] else 0.0
                _cast_process: float | None = None
                if _breakdown["cast_process_ns"]:
                    _cast_process = round(_breakdown["cast_process_ns"] / 1_000_000, 3)
                # Residual
                _residual_wall = round(max(0.0, _wall_ms - _traversal_wall - _pw_wall), 3)
                _residual_process: float | None = None
                if _process_ms is not None and _traversal_process is not None and _pw_process is not None:
                    _residual_process = round(max(0.0, _process_ms - _traversal_process - _pw_process), 3)
                request_trace.emit("model_patcher_load_breakdown", phase="execution", metadata={
                    "request_id": str(request_trace.request_id),
                    "wall_ms": _wall_ms,
                    "thread_cpu_ms": _thread_ms,
                    "process_cpu_ms": _process_ms,
                    "traversal_wall_ms": _traversal_wall,
                    "traversal_process_cpu_ms": _traversal_process,
                    "patch_weight_count": _breakdown["patch_weight_count"],
                    "patch_weight_wall_ms": _pw_wall,
                    "patch_weight_process_cpu_ms": _pw_process,
                    "cast_count": _breakdown["cast_count"],
                    "cast_wall_ms": _cast_wall,
                    "cast_process_cpu_ms": _cast_process,
                    "residual_wall_ms": _residual_wall,
                    "residual_process_cpu_ms": _residual_process,
                })
                _model_patcher_breakdown.set(None)

    setattr(wrapper, _SENTINEL_MODEL_PATCHER_LOAD, True)
    return wrapper


def _make_model_patcher_load_list_breakdown_wrapper(original):
    """Wrap ``ModelPatcher._load_list`` with wall/process timing.

    Only accumulates when ``_model_patcher_breakdown`` is set (inside outer
    ModelPatcher.load under request trace).
    """
    import functools as _ft

    @_ft.wraps(original)
    def wrapper(self, *args, **kwargs):
        _bd = _model_patcher_breakdown.get()
        if _bd is not None:
            _bd["load_list_process_start_ns"] = time.process_time_ns() if hasattr(time, "process_time_ns") else None
            _load_list_start_ns = time.monotonic_ns()
        try:
            return original(self, *args, **kwargs)
        finally:
            if _bd is not None:
                _bd["load_list_wall_ns"] = time.monotonic_ns() - _load_list_start_ns
                _bd["load_list_process_end_ns"] = time.process_time_ns() if hasattr(time, "process_time_ns") else None

    setattr(wrapper, _SENTINEL_MODEL_PATCHER_LOAD_LIST, True)
    return wrapper


def _make_model_patcher_patch_weight_breakdown_wrapper(original):
    """Wrap ``ModelPatcher.patch_weight_to_device`` with count/wall/process aggregation.

    Accumulates into ``_model_patcher_breakdown`` when set (inside outer
    ModelPatcher.load under request trace).
    """
    import functools as _ft

    @_ft.wraps(original)
    def wrapper(self, key, device_to=None, inplace_update=False, return_weight=False, force_cast=False):
        _bd = _model_patcher_breakdown.get()
        if _bd is not None:
            _pw_start = time.monotonic_ns()
            _pw_process_start = time.process_time_ns() if hasattr(time, "process_time_ns") else None
        try:
            return original(self, key, device_to=device_to, inplace_update=inplace_update, return_weight=return_weight, force_cast=force_cast)
        finally:
            if _bd is not None:
                _bd["patch_weight_count"] += 1
                _bd["patch_weight_wall_ns"] += time.monotonic_ns() - _pw_start
                if _pw_process_start is not None:
                    _bd["patch_weight_process_ns"] += time.process_time_ns() - _pw_process_start

    setattr(wrapper, _SENTINEL_MODEL_PATCHER_PATCH_WEIGHT, True)
    return wrapper


def _make_cast_to_device_breakdown_wrapper(original):
    """Wrap ``comfy.model_management.cast_to_device`` with count/wall/process aggregation.

    Only accumulates when ``_model_patcher_breakdown`` is set (inside outer
    ModelPatcher.load under request trace).  Installed on the live
    ``comfy.model_management`` module.
    """
    import functools as _ft

    @_ft.wraps(original)
    def wrapper(tensor, device, dtype, copy=False):
        _bd = _model_patcher_breakdown.get()
        if _bd is not None:
            _cast_start = time.monotonic_ns()
            _cast_process_start = time.process_time_ns() if hasattr(time, "process_time_ns") else None
        try:
            return original(tensor, device, dtype, copy=copy)
        finally:
            if _bd is not None:
                _bd["cast_count"] += 1
                _bd["cast_wall_ns"] += time.monotonic_ns() - _cast_start
                if _cast_process_start is not None:
                    _bd["cast_process_ns"] += time.process_time_ns() - _cast_process_start

    setattr(wrapper, _SENTINEL_CAST_TO_DEVICE, True)
    return wrapper


# ── Model patcher wrapper installer ─────────────────────────────────

_model_patcher_wrappers_installed: bool = False


def _install_model_patcher_wrappers(trace: RuntimeTrace | None = None) -> dict[str, str]:
    """Install constructor and model.to wrappers on live comfy.model_patcher module.

    Targets ModelPatcher and CoreModelPatcher constructors plus model.to().
    Idempotent via per-sentinel flags.
    """
    global _model_patcher_wrappers_installed
    if _model_patcher_wrappers_installed:
        return {}
    result: dict[str, str] = {}
    mp_mod = _get_live_module("comfy.model_patcher")
    if mp_mod is None:
        return {"model_patcher_wrappers": "unavailable"}

    # Wrap ModelPatcher.__init__
    _ModelPatcher_cls = getattr(mp_mod, "ModelPatcher", None)
    if _ModelPatcher_cls is not None:
        _orig_init = getattr(_ModelPatcher_cls, "__init__", None)
        if callable(_orig_init) and not getattr(_orig_init, _SENTINEL_MODEL_PATCHER, False):
            setattr(_ModelPatcher_cls, "__init__", _make_model_patcher_constructor_wrapper(_orig_init))
            result["ModelPatcher.__init__"] = "installed"
        else:
            result["ModelPatcher.__init__"] = "already_installed" if _orig_init else "unavailable"
    else:
        result["ModelPatcher.__init__"] = "unavailable"

    # Wrap CoreModelPatcher.__init__
    _CoreMP_cls = getattr(mp_mod, "CoreModelPatcher", None)
    if _CoreMP_cls is not None:
        _orig_init = getattr(_CoreMP_cls, "__init__", None)
        if callable(_orig_init) and not getattr(_orig_init, _SENTINEL_MODEL_PATCHER, False):
            setattr(_CoreMP_cls, "__init__", _make_model_patcher_constructor_wrapper(_orig_init))
            result["CoreModelPatcher.__init__"] = "installed"
        else:
            result["CoreModelPatcher.__init__"] = "already_installed" if _orig_init else "unavailable"

    # Wrap model.to() — installed on torch.nn.Module so it catches any model.to() call.
    _torch_mod = _get_live_module("torch")
    if _torch_mod is not None:
        _nn_mod = getattr(_torch_mod, "nn", None)
        if _nn_mod is not None:
            _Module_cls = getattr(_nn_mod, "Module", None)
            if _Module_cls is not None:
                _orig_to = getattr(_Module_cls, "to", None)
                if callable(_orig_to) and not getattr(_orig_to, _SENTINEL_MODEL_TO, False):
                    setattr(_Module_cls, "to", _make_model_to_wrapper(_orig_to))
                    result["nn.Module.to"] = "installed"
                else:
                    result["nn.Module.to"] = "already_installed" if _orig_to else "unavailable"

    # Wrap ModelPatcher.load (aggregate-timing breakdown)
    if _ModelPatcher_cls is not None:
        _orig_load = getattr(_ModelPatcher_cls, "load", None)
        if callable(_orig_load) and not getattr(_orig_load, _SENTINEL_MODEL_PATCHER_LOAD, False):
            setattr(_ModelPatcher_cls, "load", _make_model_patcher_load_breakdown_wrapper(_orig_load))
            result["ModelPatcher.load"] = "installed"
        else:
            result["ModelPatcher.load"] = "already_installed" if _orig_load else "unavailable"

    # Wrap ModelPatcherDynamic.load
    _MPDynamic_cls = getattr(mp_mod, "ModelPatcherDynamic", None)
    if _MPDynamic_cls is not None:
        _orig_dyn_load = getattr(_MPDynamic_cls, "load", None)
        if callable(_orig_dyn_load) and not getattr(_orig_dyn_load, _SENTINEL_MODEL_PATCHER_LOAD, False):
            setattr(_MPDynamic_cls, "load", _make_model_patcher_load_breakdown_wrapper(_orig_dyn_load))
            result["ModelPatcherDynamic.load"] = "installed"
        else:
            result["ModelPatcherDynamic.load"] = "already_installed" if _orig_dyn_load else "unavailable"

    # Wrap ModelPatcher._load_list (traversal aggregate)
    if _ModelPatcher_cls is not None:
        _orig_load_list = getattr(_ModelPatcher_cls, "_load_list", None)
        if callable(_orig_load_list) and not getattr(_orig_load_list, _SENTINEL_MODEL_PATCHER_LOAD_LIST, False):
            setattr(_ModelPatcher_cls, "_load_list", _make_model_patcher_load_list_breakdown_wrapper(_orig_load_list))
            result["ModelPatcher._load_list"] = "installed"
        else:
            result["ModelPatcher._load_list"] = "already_installed" if _orig_load_list else "unavailable"

    # Wrap ModelPatcher.patch_weight_to_device (aggregate)
    if _ModelPatcher_cls is not None:
        _orig_pw = getattr(_ModelPatcher_cls, "patch_weight_to_device", None)
        if callable(_orig_pw) and not getattr(_orig_pw, _SENTINEL_MODEL_PATCHER_PATCH_WEIGHT, False):
            setattr(_ModelPatcher_cls, "patch_weight_to_device", _make_model_patcher_patch_weight_breakdown_wrapper(_orig_pw))
            result["ModelPatcher.patch_weight_to_device"] = "installed"
        else:
            result["ModelPatcher.patch_weight_to_device"] = "already_installed" if _orig_pw else "unavailable"

    if trace:
        for comp, status in result.items():
            trace.emit("model_patcher_wrapper_install", phase="restore",
                       metadata={"component": comp, "status": status})
    _model_patcher_wrappers_installed = True
    return result


# ── ModelPatcher load wrappers (idempotent, conditional on symbol presence) ──

# ModelPatcher sentinels — exact names per user contract
_SENTINEL_MODEL_PATCHER_LOAD_DIAG = "_comfy_modal_model_patcher_load_diag"
_SENTINEL_MODEL_PATCHER_LOAD_LIST_DIAG = "_comfy_modal_model_patcher_load_list_diag"
_SENTINEL_PATCH_WEIGHT_DIAG = "_comfy_modal_patch_weight_diag"
_SENTINEL_CAST_TO_DEVICE_DIAG = "_comfy_modal_cast_to_device_diag"
_SENTINEL_MP_LOAD = _SENTINEL_MODEL_PATCHER_LOAD_DIAG
_SENTINEL_MPD_LOAD = _SENTINEL_MODEL_PATCHER_LOAD_DIAG
_SENTINEL_LOAD_LIST = _SENTINEL_MODEL_PATCHER_LOAD_LIST_DIAG
_SENTINEL_PTW_DEVICE = _SENTINEL_PATCH_WEIGHT_DIAG
_SENTINEL_CTD = _SENTINEL_CAST_TO_DEVICE_DIAG

# ModelPatcher scope tracking — one aggregate record per outer load
_MODEL_PATCHER_LOAD_DEPTH: ContextVar[int] = ContextVar(
    "comfymodal_model_patcher_load_depth", default=0
)
_MODEL_PATCHER_BREAKDOWN: ContextVar[dict[str, Any] | None] = ContextVar(
    "comfymodal_model_patcher_breakdown", default=None
)

_mp_load_wrapper_installed: bool = False
_mpd_load_wrapper_installed: bool = False
_load_list_wrapper_installed: bool = False
_ptw_device_wrapper_installed: bool = False
_ctd_wrapper_installed: bool = False

_MP_WRAPPER_LOCK = RLock()


def _make_model_patcher_load_wrapper(original: Callable[..., Any]) -> Callable[..., Any]:
    """Wrap ``ModelPatcher.load`` with outermost aggregate timing.

    Records ``mp_load_start/end`` on the active request trace at outermost
    reentrancy only.  No tensor/model/path storage.  No CUDA synchronize.
    """
    import functools as _ft

    @_ft.wraps(original)
    def wrapper(self, device_to=None, lowvram_model_memory=0, force_patch_weights=False, full_load=False):
        before = getattr(wrapper, "_mp_load_depth", 0)
        setattr(wrapper, "_mp_load_depth", before + 1)
        request_trace = _ACTIVE_REQUEST_TRACE.get()
        _outer = before == 0 and request_trace is not None
        _start_ns = time.monotonic_ns() if _outer else 0
        if _outer:
            request_trace.emit("mp_load_start", phase="execution", metadata={
                "model_type": type(self).__qualname__,
            })
        try:
            return original(self, device_to=device_to, lowvram_model_memory=lowvram_model_memory,
                            force_patch_weights=force_patch_weights, full_load=full_load)
        finally:
            after = getattr(wrapper, "_mp_load_depth", 1)
            setattr(wrapper, "_mp_load_depth", after - 1)
            if _outer:
                _dur = round((time.monotonic_ns() - _start_ns) / 1_000_000, 3)
                request_trace.emit("mp_load_end", phase="execution", metadata={
                    "model_type": type(self).__qualname__,
                    "duration_ms": _dur,
                })
    setattr(wrapper, "_mp_load_depth", 0)
    setattr(wrapper, _SENTINEL_MP_LOAD, True)
    return wrapper


def _make_model_patcher_dynamic_load_wrapper(original: Callable[..., Any]) -> Callable[..., Any]:
    """Wrap ``ModelPatcherDynamic.load`` with outermost aggregate timing."""
    import functools as _ft

    @_ft.wraps(original)
    def wrapper(self, device_to=None, lowvram_model_memory=0, force_patch_weights=False, full_load=False, dirty=False):
        before = getattr(wrapper, "_mpd_load_depth", 0)
        setattr(wrapper, "_mpd_load_depth", before + 1)
        request_trace = _ACTIVE_REQUEST_TRACE.get()
        _outer = before == 0 and request_trace is not None
        _start_ns = time.monotonic_ns() if _outer else 0
        if _outer:
            request_trace.emit("mpd_load_start", phase="execution", metadata={
                "model_type": type(self).__qualname__,
            })
        try:
            return original(self, device_to=device_to, lowvram_model_memory=lowvram_model_memory,
                            force_patch_weights=force_patch_weights, full_load=full_load, dirty=dirty)
        finally:
            after = getattr(wrapper, "_mpd_load_depth", 1)
            setattr(wrapper, "_mpd_load_depth", after - 1)
            if _outer:
                _dur = round((time.monotonic_ns() - _start_ns) / 1_000_000, 3)
                request_trace.emit("mpd_load_end", phase="execution", metadata={
                    "model_type": type(self).__qualname__,
                    "duration_ms": _dur,
                })
    setattr(wrapper, "_mpd_load_depth", 0)
    setattr(wrapper, _SENTINEL_MPD_LOAD, True)
    return wrapper


def _make_load_list_wrapper(original: Callable[..., Any]) -> Callable[..., Any]:
    """Wrap ``ModelPatcher._load_list`` with outermost aggregate timing."""
    import functools as _ft

    @_ft.wraps(original)
    def wrapper(self, for_dynamic=False, default_device=None):
        before = getattr(wrapper, "_load_list_depth", 0)
        setattr(wrapper, "_load_list_depth", before + 1)
        request_trace = _ACTIVE_REQUEST_TRACE.get()
        _outer = before == 0 and request_trace is not None
        _start_ns = time.monotonic_ns() if _outer else 0
        if _outer:
            request_trace.emit("load_list_start", phase="execution", metadata={
                "for_dynamic": for_dynamic,
            })
        try:
            return original(self, for_dynamic=for_dynamic, default_device=default_device)
        finally:
            after = getattr(wrapper, "_load_list_depth", 1)
            setattr(wrapper, "_load_list_depth", after - 1)
            if _outer:
                _dur = round((time.monotonic_ns() - _start_ns) / 1_000_000, 3)
                request_trace.emit("load_list_end", phase="execution", metadata={
                    "duration_ms": _dur,
                })
    setattr(wrapper, "_load_list_depth", 0)
    setattr(wrapper, _SENTINEL_LOAD_LIST, True)
    return wrapper


def _make_patch_weight_to_device_wrapper(original: Callable[..., Any]) -> Callable[..., Any]:
    """Wrap ``ModelPatcher.patch_weight_to_device`` with aggregate timing."""
    import functools as _ft

    @_ft.wraps(original)
    def wrapper(self, key, device_to=None, inplace_update=False, return_weight=False, force_cast=False):
        before = getattr(wrapper, "_ptw_depth", 0)
        setattr(wrapper, "_ptw_depth", before + 1)
        request_trace = _ACTIVE_REQUEST_TRACE.get()
        _outer = before == 0 and request_trace is not None
        _start_ns = time.monotonic_ns() if _outer else 0
        if _outer:
            request_trace.emit("ptw_device_start", phase="execution", metadata={
                "key_hash": stable_hash(str(key))[:16],
            })
        try:
            return original(self, key, device_to=device_to, inplace_update=inplace_update,
                            return_weight=return_weight, force_cast=force_cast)
        finally:
            after = getattr(wrapper, "_ptw_depth", 1)
            setattr(wrapper, "_ptw_depth", after - 1)
            if _outer:
                _dur = round((time.monotonic_ns() - _start_ns) / 1_000_000, 3)
                request_trace.emit("ptw_device_end", phase="execution", metadata={
                    "duration_ms": _dur,
                })
    setattr(wrapper, "_ptw_depth", 0)
    setattr(wrapper, _SENTINEL_PTW_DEVICE, True)
    return wrapper


def _make_cast_to_device_wrapper(original: Callable[..., Any]) -> Callable[..., Any]:
    """Wrap ``ModelPatcher.cast_to_device`` with aggregate timing."""
    import functools as _ft

    @_ft.wraps(original)
    def wrapper(self, device=None, dtype=None, non_blocking=False, copy=False):
        before = getattr(wrapper, "_ctd_depth", 0)
        setattr(wrapper, "_ctd_depth", before + 1)
        request_trace = _ACTIVE_REQUEST_TRACE.get()
        _outer = before == 0 and request_trace is not None
        _start_ns = time.monotonic_ns() if _outer else 0
        if _outer:
            request_trace.emit("ctd_start", phase="execution", metadata={
                "device_str": str(device),
                "dtype_str": str(dtype),
            })
        try:
            return original(self, device=device, dtype=dtype, non_blocking=non_blocking, copy=copy)
        finally:
            after = getattr(wrapper, "_ctd_depth", 1)
            setattr(wrapper, "_ctd_depth", after - 1)
            if _outer:
                _dur = round((time.monotonic_ns() - _start_ns) / 1_000_000, 3)
                request_trace.emit("ctd_end", phase="execution", metadata={
                    "duration_ms": _dur,
                })
    setattr(wrapper, "_ctd_depth", 0)
    setattr(wrapper, _SENTINEL_CTD, True)
    return wrapper


def _make_model_patcher_load_diagnostic_wrapper(original: Callable[..., Any]) -> Callable[..., Any]:
    """Wrap ``ModelPatcher.load`` / ``ModelPatcherDynamic.load`` with outermost
    aggregate diagnostic timing and activation-diagnostic recording.

    Uses ``_MODEL_PATCHER_LOAD_DEPTH`` ContextVar for reentrancy so the same
    factory works for both ``ModelPatcher`` and ``ModelPatcherDynamic``.
    Emits one ``mp_load_start`` / ``mp_load_end`` event pair on the active
    request trace per outermost call.  Records one entry in
    ``_ACTIVATION_DIAGNOSTIC_STATE.model_patcher_calls`` per outermost call.
    No per-weight events.
    """
    import functools as _ft

    @_ft.wraps(original)
    def wrapper(self, *args, **kwargs):
        depth = _MODEL_PATCHER_LOAD_DEPTH.get()
        _MODEL_PATCHER_LOAD_DEPTH.set(depth + 1)
        _outer = depth == 0
        request_trace = _ACTIVE_REQUEST_TRACE.get()
        _start_ns = time.monotonic_ns() if _outer else 0
        if _outer and request_trace is not None:
            request_trace.emit("mp_load_start", phase="execution", metadata={
                "model_type": type(self).__qualname__,
            })
        try:
            return original(self, *args, **kwargs)
        finally:
            _MODEL_PATCHER_LOAD_DEPTH.set(depth)
            if _outer:
                _dur = round((time.monotonic_ns() - _start_ns) / 1_000_000, 3)
                if request_trace is not None:
                    request_trace.emit("mp_load_end", phase="execution", metadata={
                        "model_type": type(self).__qualname__,
                        "duration_ms": _dur,
                    })
                # Record one aggregate entry into activation diagnostics
                _ad_state = _ACTIVATION_DIAGNOSTIC_STATE.get()
                if _ad_state is not None:
                    _mp_calls: list = _ad_state.setdefault("model_patcher_calls", [])
                    _mp_calls.append({
                        "model_type": type(self).__qualname__,
                        "wall_ms": _dur,
                    })
    setattr(wrapper, _SENTINEL_MP_LOAD, True)
    setattr(wrapper, _SENTINEL_MPD_LOAD, True)
    return wrapper


def _make_breakdown_accumulator_wrapper(
    original: Callable[..., Any], *, kind: str
) -> Callable[..., Any]:
    """Accumulate child ModelPatcher timing into the active outer load."""
    import functools as _ft

    @_ft.wraps(original)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        breakdown = _MODEL_PATCHER_BREAKDOWN.get()
        wall_start = time.monotonic_ns() if breakdown is not None else 0
        process_start = (
            time.process_time_ns()
            if breakdown is not None and hasattr(time, "process_time_ns")
            else None
        )
        try:
            return original(*args, **kwargs)
        finally:
            if breakdown is not None:
                wall_ns = max(0, time.monotonic_ns() - wall_start)
                process_ns = (
                    max(0, time.process_time_ns() - process_start)
                    if process_start is not None and hasattr(time, "process_time_ns")
                    else 0
                )
                if kind == "load_list":
                    breakdown["load_list_wall_ns"] += wall_ns
                    breakdown["load_list_process_ns"] += process_ns
                elif kind == "patch_weight":
                    breakdown["patch_weight_count"] += 1
                    breakdown["patch_weight_wall_ns"] += wall_ns
                    breakdown["patch_weight_process_ns"] += process_ns
                elif kind == "cast":
                    breakdown["cast_count"] += 1
                    breakdown["cast_wall_ns"] += wall_ns
                    breakdown["cast_process_ns"] += process_ns

    sentinel = {
        "load_list": _SENTINEL_MODEL_PATCHER_LOAD_LIST_DIAG,
        "patch_weight": _SENTINEL_PATCH_WEIGHT_DIAG,
        "cast": _SENTINEL_CAST_TO_DEVICE_DIAG,
    }.get(kind)
    if sentinel is not None:
        setattr(wrapper, sentinel, True)
    return wrapper


def _install_mp_load_wrappers(trace: RuntimeTrace | None = None) -> dict[str, str]:
    """Install wrappers on ModelPatcher.load / ModelPatcherDynamic.load / etc.

    Conditionally wraps each symbol if present in the live module.
    Idempotent via sentinel flags.  Returns ``{component: status}``.
    """
    global _mp_load_wrapper_installed, _mpd_load_wrapper_installed
    global _load_list_wrapper_installed, _ptw_device_wrapper_installed
    global _ctd_wrapper_installed

    result: dict[str, str] = {}
    if all((_mp_load_wrapper_installed, _mpd_load_wrapper_installed,
            _load_list_wrapper_installed, _ptw_device_wrapper_installed,
            _ctd_wrapper_installed)):
        return result

    mp_mod = _get_live_module("comfy.model_patcher")
    if mp_mod is None:
        return {"ModelPatcher.load": "unavailable"}

    # ── ModelPatcher.load ──
    MP_cls = getattr(mp_mod, "ModelPatcher", None)
    if MP_cls is not None and not _mp_load_wrapper_installed:
        _orig = getattr(MP_cls, "load", None)
        if callable(_orig) and not getattr(_orig, _SENTINEL_MP_LOAD, False):
            setattr(MP_cls, "load", _make_model_patcher_load_diagnostic_wrapper(_orig))
            _mp_load_wrapper_installed = True
            result["ModelPatcher.load"] = "installed"
        else:
            status = "already_installed" if _orig else "unavailable"
            result["ModelPatcher.load"] = status
    elif MP_cls is not None:
        result["ModelPatcher.load"] = "already_installed"

    # ── ModelPatcherDynamic.load (conditionally present) ──
    MPD_cls = getattr(mp_mod, "ModelPatcherDynamic", None)
    if MPD_cls is not None and not _mpd_load_wrapper_installed:
        _orig = getattr(MPD_cls, "load", None)
        if callable(_orig) and not getattr(_orig, _SENTINEL_MPD_LOAD, False):
            setattr(MPD_cls, "load", _make_model_patcher_load_diagnostic_wrapper(_orig))
            _mpd_load_wrapper_installed = True
            result["ModelPatcherDynamic.load"] = "installed"
        else:
            result["ModelPatcherDynamic.load"] = "already_installed" if _orig else "unavailable"
    elif MPD_cls is not None:
        result["ModelPatcherDynamic.load"] = "already_installed"
    else:
        result["ModelPatcherDynamic.load"] = "absent"
        _mpd_load_wrapper_installed = True  # don't retry absent symbol

    # ── _load_list (present on ModelPatcher) ──
    if MP_cls is not None and not _load_list_wrapper_installed:
        _orig = getattr(MP_cls, "_load_list", None)
        if callable(_orig) and not getattr(_orig, _SENTINEL_LOAD_LIST, False):
            setattr(MP_cls, "_load_list", _make_breakdown_accumulator_wrapper(_orig, kind="load_list"))
            _load_list_wrapper_installed = True
            result["_load_list"] = "installed"
        else:
            result["_load_list"] = "already_installed" if _orig else "unavailable"
    elif MP_cls is not None:
        result["_load_list"] = "already_installed"

    # ── patch_weight_to_device ──
    if MP_cls is not None and not _ptw_device_wrapper_installed:
        _orig = getattr(MP_cls, "patch_weight_to_device", None)
        if callable(_orig) and not getattr(_orig, _SENTINEL_PTW_DEVICE, False):
            setattr(MP_cls, "patch_weight_to_device", _make_breakdown_accumulator_wrapper(_orig, kind="patch_weight"))
            _ptw_device_wrapper_installed = True
            result["patch_weight_to_device"] = "installed"
        else:
            result["patch_weight_to_device"] = "already_installed" if _orig else "unavailable"
    elif MP_cls is not None:
        result["patch_weight_to_device"] = "already_installed"

    # ── comfy.model_management.cast_to_device ──
    mm_mod = _get_live_module("comfy.model_management")
    if mm_mod is not None and not _ctd_wrapper_installed:
        _orig = getattr(mm_mod, "cast_to_device", None)
        if callable(_orig) and not getattr(_orig, _SENTINEL_CTD, False):
            setattr(mm_mod, "cast_to_device", _make_breakdown_accumulator_wrapper(_orig, kind="cast"))
            _ctd_wrapper_installed = True
            result["cast_to_device"] = "installed"
        else:
            result["cast_to_device"] = "already_installed" if _orig else "unavailable"
    elif mm_mod is not None:
        result["cast_to_device"] = "already_installed"

    if trace:
        for comp, status in result.items():
            trace.emit("mp_load_wrapper_install", phase="restore",
                       metadata={"component": comp, "status": status})
    return result


# ── (removed) CPU storage registry ──────────────────────────────────
# The _build_cpu_storage_registry / _sample_cpu_storage_mincore /
# _CPU_STORAGE_REGISTRY globals were noncompliant and have been removed.
# Use cpu_snapshot_models.py StorageRegistry / sample_storage_residency
# for identical-ranged page-residency sampling.


def _install_clip_load_sd_wrapper(sd_mod, trace=None):
    """Install CLIP.load_sd wrapper on live comfy.sd.CLIP class.

    Idempotent via sentinel.  Only emits ``clip_load_sd_weights_start/end``
    while a CLIP constructor is active (``_clip_constructor_depth > 0``).
    """
    global _clip_load_sd_wrapper_installed
    if _clip_load_sd_wrapper_installed:
        return "already_installed"
    CLIP_cls = getattr(sd_mod, "CLIP", None)
    if CLIP_cls is None:
        return "unavailable"
    _orig_load_sd = getattr(CLIP_cls, "load_sd", None)
    if not callable(_orig_load_sd):
        return "unavailable"
    if getattr(_orig_load_sd, _SENTINEL_CLIP_LOAD_SD, False):
        _clip_load_sd_wrapper_installed = True
        return "already_installed"
    with _wrappers_lock:
        if _clip_load_sd_wrapper_installed:
            return "already_installed"
        _check_load_sd = getattr(CLIP_cls, "load_sd", None)
        if getattr(_check_load_sd, _SENTINEL_CLIP_LOAD_SD, False):
            _clip_load_sd_wrapper_installed = True
            return "already_installed"
        setattr(CLIP_cls, "load_sd", _make_clip_load_sd_wrapper(_check_load_sd))
        _clip_load_sd_wrapper_installed = True
    if trace:
        trace.emit("clip_load_sd_wrapper_install", phase="restore",
                   metadata={"status": "installed"})
    return "installed"


def _install_clip_constructor_wrapper(sd_mod, trace=None):
    """Install CLIP.__init__ wrapper on live comfy.sd.CLIP class.

    Idempotent via sentinel.  Emits ``clip_constructor_start/end``
    named events that are NOT recorded into ``_clip_cpu_prepare_children``.
    Also installs the load_sd wrapper for child weight-load attribution.
    """
    global _clip_constructor_wrapper_installed
    if _clip_constructor_wrapper_installed:
        return "already_installed"
    CLIP_cls = getattr(sd_mod, "CLIP", None)
    if CLIP_cls is None:
        return "unavailable"
    _orig_init = getattr(CLIP_cls, "__init__", None)
    if not callable(_orig_init):
        return "unavailable"
    if getattr(_orig_init, _SENTINEL_CLIP_CONSTRUCTOR, False):
        _clip_constructor_wrapper_installed = True
        return "already_installed"
    with _wrappers_lock:
        if _clip_constructor_wrapper_installed:
            return "already_installed"
        _check_init = getattr(CLIP_cls, "__init__", None)
        if getattr(_check_init, _SENTINEL_CLIP_CONSTRUCTOR, False):
            _clip_constructor_wrapper_installed = True
            return "already_installed"
        setattr(CLIP_cls, "__init__", _make_clip_constructor_wrapper(_check_init))
        _clip_constructor_wrapper_installed = True
        # Also install load_sd wrapper for child weight-load attribution.
        _install_clip_load_sd_wrapper(sd_mod, trace=trace)
    if trace:
        trace.emit("clip_constructor_wrapper_install", phase="restore",
                   metadata={"status": "installed"})
    return "installed"


def _install_clip_wrapper(trace=None):
    global _clip_wrapper_installed
    if _clip_wrapper_installed:
        return "already_installed"
    sd_mod = _get_live_module("comfy.sd")
    if sd_mod is None:
        return "unavailable"
    original_fn = getattr(sd_mod, "load_clip", None)
    if not callable(original_fn):
        return "unavailable"
    if getattr(original_fn, _SENTINEL_CLIP, False):
        _clip_wrapper_installed = True
        return "already_installed"
    from threading import RLock as _RLock
    _cw_lock = _RLock()
    with _cw_lock:
        if _clip_wrapper_installed:
            return "already_installed"
        if getattr(sd_mod.load_clip, _SENTINEL_CLIP, False):
            _clip_wrapper_installed = True
            return "already_installed"
        sd_mod.load_clip = _make_clip_load_wrapper(sd_mod.load_clip)
        _clip_wrapper_installed = True
        _install_clip_subfn_wrappers(sd_mod)
        _install_clip_constructor_wrapper(sd_mod, trace=trace)
    if trace:
        trace.emit("clip_wrapper_install", phase="restore", metadata={"status": "installed"})
    return "installed"


_CLIP_DECOMPOSE_TARGETS = {
    "detect_te_model": ("comfy.sd", "detect_te_model", "sd"),
    "load_text_encoder_state_dicts": ("comfy.sd", "load_text_encoder_state_dicts", "sd"),
    "clip_text_transformers_convert": ("comfy.utils", "clip_text_transformers_convert", "utils"),
    # NOTE: convert_old_quants is installed via the shared lane-aware
    # _install_shared_convert_old_quants_wrapper so both CLIP and UNET
    # attribution remain active on the same live function.
}


def _install_clip_subfn_wrappers(sd_mod):
    result = {}
    # Install shared lane-aware convert_old_quants wrapper first.
    result["convert_old_quants"] = _install_shared_convert_old_quants_wrapper()
    for short_name, (mod_name, func_name, category) in _CLIP_DECOMPOSE_TARGETS.items():
        mod = _get_live_module(mod_name) if mod_name != "comfy.sd" else sd_mod
        if mod is None:
            result[short_name] = "unavailable"
            continue
        original = getattr(mod, func_name, None)
        if not callable(original):
            result[short_name] = "unavailable"
            continue
        if getattr(original, _SENTINEL_CLIP_SUBFN, False):
            result[short_name] = "already_installed"
            continue
        wrapper = _make_clip_subfn_wrapper(short_name, original, category)
        setattr(wrapper, _SENTINEL_CLIP_SUBFN, True)
        setattr(mod, func_name, wrapper)
        result[short_name] = "installed"
    return result


def _install_deep_diag_wrappers(*, safe_open_fn: Any = None, torch_load_fn: Any = None,
                                 trace: RuntimeTrace | None = None) -> dict[str, str]:
    """Install deep diagnostic wrappers on safetensors.safe_open and torch.load.

    Idempotent via sentinel flags.  Installs the wrapper onto the *live module
    object in sys.modules* so the wrapper intercepts real callers.  Thread-local
    ``_DEEP_TARGET_PATH`` + ``_ACTIVE_LANE_TRACE`` filtering ensures unrelated
    file activity is never logged.

    Returns ``{component: status}`` dict.  Only meaningful when
    ``_DIAGNOSTIC_FLAG`` is True at install time, but the wrappers themselves
    check the flag and path filter at call time.
    """
    global _deep_diag_wrappers_installed
    if _deep_diag_wrappers_installed:
        return {}
    result: dict[str, str] = {}
    if safe_open_fn is not None and callable(safe_open_fn):
        if not getattr(safe_open_fn, _SENTINEL_DEEP_ST, False):
            _wrapped = _make_safetensors_open_wrapper(safe_open_fn)
            # Install onto the live safetensors module in sys.modules
            _st_mod = _get_live_module("safetensors")
            if _st_mod is not None:
                setattr(_st_mod, "safe_open", _wrapped)
                result["safetensors.safe_open"] = "installed"
            else:
                result["safetensors.safe_open"] = "unavailable"
        else:
            result["safetensors.safe_open"] = "already_installed"
    if torch_load_fn is not None and callable(torch_load_fn):
        if not getattr(torch_load_fn, _SENTINEL_DEEP_TL, False):
            _wrapped = _make_torch_load_wrapper(torch_load_fn)
            # Install onto the live torch module in sys.modules
            _torch_mod = _get_live_module("torch")
            if _torch_mod is not None:
                setattr(_torch_mod, "load", _wrapped)
                result["torch.load"] = "installed"
            else:
                result["torch.load"] = "unavailable"
        else:
            result["torch.load"] = "already_installed"
    if trace:
        for comp, status in result.items():
            trace.emit("deep_diag_wrapper_install", phase="restore",
                       metadata={"component": comp, "status": status})
    _deep_diag_wrappers_installed = True
    return result


# ── Independent per-component installation ──────────────────────────


def _install_read_wrapper(*, utils_module: Any, trace: RuntimeTrace | None = None) -> str:
    """Install the ``load_torch_file`` wrapper on *utils_module*.

    Returns status ``"installed"``, ``"already_installed"``, or
    ``"unavailable"``.
    """
    global _read_wrapper_installed
    if _read_wrapper_installed:
        return "already_installed"
    func = getattr(utils_module, "load_torch_file", None)
    if not callable(func):
        return "unavailable"
    if getattr(func, _SENTINEL_READ, False):
        _read_wrapper_installed = True
        return "already_installed"
    with _wrappers_lock:
        if _read_wrapper_installed:
            return "already_installed"
        if getattr(utils_module.load_torch_file, _SENTINEL_READ, False):
            _read_wrapper_installed = True
            return "already_installed"
        utils_module.load_torch_file = _make_torch_file_wrapper(utils_module.load_torch_file)
        _read_wrapper_installed = True
    return "installed"


def _install_gpu_wrapper(*, mm_module: Any, trace: RuntimeTrace | None = None) -> str:
    """Install the ``load_models_gpu`` wrapper on *mm_module*.

    Returns status ``"installed"``, ``"already_installed"``, or
    ``"unavailable"``.
    """
    global _gpu_wrapper_installed
    if _gpu_wrapper_installed:
        return "already_installed"
    func = getattr(mm_module, "load_models_gpu", None)
    if not callable(func):
        return "unavailable"
    if getattr(func, _SENTINEL_GPU, False):
        _gpu_wrapper_installed = True
        return "already_installed"
    with _wrappers_lock:
        if _gpu_wrapper_installed:
            return "already_installed"
        if getattr(mm_module.load_models_gpu, _SENTINEL_GPU, False):
            _gpu_wrapper_installed = True
            return "already_installed"
        mm_module.load_models_gpu = _make_gpu_loader_wrapper(mm_module.load_models_gpu)
        _gpu_wrapper_installed = True
    return "installed"


_cast_to_device_wrapper_installed: bool = False


def _install_cast_to_device_wrapper(*, mm_module: Any, trace: RuntimeTrace | None = None) -> str:
    """Install the ``cast_to_device`` wrapper on *mm_module* (comfy.model_management).

    Idempotent via sentinel.  Wrapper aggregates count + wall/process time
    into ``_model_patcher_breakdown`` when set (inside outer ModelPatcher.load
    under request trace).  Returns status string.
    """
    global _cast_to_device_wrapper_installed
    if _cast_to_device_wrapper_installed:
        return "already_installed"
    func = getattr(mm_module, "cast_to_device", None)
    if not callable(func):
        return "unavailable"
    if getattr(func, _SENTINEL_CAST_TO_DEVICE, False):
        _cast_to_device_wrapper_installed = True
        return "already_installed"
    with _wrappers_lock:
        if _cast_to_device_wrapper_installed:
            return "already_installed"
        if getattr(mm_module.cast_to_device, _SENTINEL_CAST_TO_DEVICE, False):
            _cast_to_device_wrapper_installed = True
            return "already_installed"
        mm_module.cast_to_device = _make_cast_to_device_breakdown_wrapper(mm_module.cast_to_device)
        _cast_to_device_wrapper_installed = True
    return "installed"


def _ensure_core_wrappers(trace: RuntimeTrace | None = None) -> dict[str, str]:
    """Idempotent per-component installation using live modules.

    Resolves ``comfy.utils`` and ``comfy.model_management`` via
    ``sys.modules`` (already loaded by ``nodes.py`` at startup) so that
    optional-dependency import failures in ``comfy.memory_management``
    cannot block the read wrapper.

    Also installs deep-diagnostic wrappers (``safetensors.safe_open``,
    ``torch.load``) when COMFYMODAL_V2_DEEP_MODEL_DIAG=1.  These wrappers
    are globally installed but filtered at call time by thread-local
    ``_DEEP_TARGET_PATH`` so unrelated file activity is never logged.

    Returns a ``{component: status}`` dict suitable for trace diagnostics.
    """
    result: dict[str, str] = {}

    utils_mod = _get_live_module("comfy.utils")
    if utils_mod is not None:
        result["load_torch_file"] = _install_read_wrapper(utils_module=utils_mod, trace=trace)
    else:
        result["load_torch_file"] = "unavailable"

    mm_mod = _get_live_module("comfy.model_management")
    if mm_mod is not None:
        result["load_models_gpu"] = _install_gpu_wrapper(mm_module=mm_mod, trace=trace)
        result["cast_to_device"] = _install_cast_to_device_wrapper(mm_module=mm_mod, trace=trace)
    else:
        result["load_models_gpu"] = "unavailable"
        result["cast_to_device"] = "unavailable"

    result.update(_install_model_patcher_wrappers(trace=trace))

    # ── Install deep diag wrappers (idempotent, path-filtered) ────
    if _DIAGNOSTIC_FLAG:
        import safetensors as _st
        import torch as _torch
        _st_mod = _get_live_module("safetensors")
        _st_open_fn = getattr(_st_mod, "safe_open", None) if _st_mod else None
        _deep_install_result = _install_deep_diag_wrappers(
            safe_open_fn=_st_open_fn,
            torch_load_fn=getattr(_torch, "load", None),
            trace=trace,
        )
        result.update(_deep_install_result)

    # Install CLIP wrapper.
    _clip_result = _install_clip_wrapper(trace=trace)
    result["comfy.sd.load_clip"] = _clip_result

    # Emit diagnostic events when a trace is available.
    if trace is not None:
        for component, status in result.items():
            trace.emit(
                "core_wrapper_install",
                phase="restore",
                metadata={
                    "component": component,
                    "status": status,
                },
            )

    # Install ModelPatcher load wrappers (ModelPatcher.load, _load_list, patch_weight_to_device, cast_to_device).
    _mp_load_result = _install_mp_load_wrappers(trace=trace)
    for comp, status in _mp_load_result.items():
        result[f"mp_load.{comp}"] = status

    # Install NextDiT forward pre-hook for forward-probe diagnostics.
    result["nextdit_forward_pre_hook"] = "installed" if install_nextdit_forward_pre_hook() else "unavailable"

    return result


# ── UNET post-read subfunction wrappers (Section B) ─────────────────
# Installed idempotently on the live sys.modules; skip absent modules
# without breaking loading.  Only active when _ACTIVE_LANE_TRACE is UNET.

_UNET_DECOMPOSE_TARGETS: dict[str, tuple[str, str, str]] = {
    # NOTE: load_diffusion_model_state_dict is handled by a dedicated
    # wrapper (_make_sd_state_dict_wrapper) so it is intentionally absent.
    # NOTE: convert_old_quants is installed via the shared lane-aware
    # _install_shared_convert_old_quants_wrapper so both CLIP and UNET
    # attribution remain active on the same live function.
    "state_dict_prefix_replace": ("comfy.utils", "state_dict_prefix_replace", "utils"),
    "calculate_parameters": ("comfy.utils", "calculate_parameters", "utils"),
    "weight_dtype": ("comfy.utils", "weight_dtype", "utils"),
    "model_config_from_unet": ("comfy.model_detection", "model_config_from_unet", "model_detection"),
    "unet_dtype": ("comfy.model_management", "unet_dtype", "model_management"),
    "unet_manual_cast": ("comfy.model_management", "unet_manual_cast", "model_management"),
    "unet_prefix_from_state_dict": ("comfy.model_detection", "unet_prefix_from_state_dict", "model_detection"),
    "convert_diffusers_mmdit": ("comfy.model_detection", "convert_diffusers_mmdit", "model_detection"),
    "model_config_from_diffusers_unet": ("comfy.model_detection", "model_config_from_diffusers_unet", "model_detection"),
    "unet_to_diffusers": ("comfy.utils", "unet_to_diffusers", "utils"),
    "unet_offload_device": ("comfy.model_management", "unet_offload_device", "model_management"),
}
"""Maps short name -> (module_name, function_name, diagnostic_category)."""


def _install_unet_decompose_wrappers(trace: RuntimeTrace | None = None) -> dict[str, str]:
    """Install UNET post-read decomposition wrappers idempotently.

    Global flag ``_subfn_wrappers_installed`` avoids duplicate trace
    events.  Each wrapper is installed on its live ``sys.modules`` entry
    using a sentinel for idempotence.  If a module or symbol is absent
    the entry is recorded as ``"unavailable"`` and loading continues.
    Returns ``{short_name: status}``.
    """
    global _subfn_wrappers_installed
    if _subfn_wrappers_installed:
        return {}
    result: dict[str, str] = {}
    # Install shared lane-aware convert_old_quants wrapper first.
    result["convert_old_quants"] = _install_shared_convert_old_quants_wrapper()
    # Install model patcher construction wrappers.
    result.update(_install_model_patcher_wrappers(trace=trace))
    for short_name, (mod_name, func_name, category) in _UNET_DECOMPOSE_TARGETS.items():
        mod = _get_live_module(mod_name)
        if mod is None:
            result[short_name] = "unavailable"
            continue
        original = getattr(mod, func_name, None)
        if not callable(original):
            result[short_name] = "unavailable"
            continue
        if getattr(original, _SENTINEL_UNET_SUBFN, False):
            result[short_name] = "already_installed"
            continue
        wrapper = _make_unet_subfn_wrapper(short_name, original, category)
        setattr(wrapper, _SENTINEL_UNET_SUBFN, True)
        setattr(mod, func_name, wrapper)
        result[short_name] = "installed"
    if trace:
        for name, status in result.items():
            trace.emit("unet_decompose_install", phase="restore", metadata={
                "function": name, "status": status,
            })
    _subfn_wrappers_installed = True
    return result


def _make_unet_subfn_wrapper(
    short_name: str,
    original: Callable[..., Any],
    category: str,
) -> Callable[..., Any]:
    """Wrap a UNET post-read subfunction to emit start/end events.

    Only active when ``_ACTIVE_LANE_TRACE`` is set AND the current lane
    is ``UNET``.  Reentrancy-safe via a per-function ContextVar depth
    counter.  Records duration into ``_child_durations`` for residual
    computation by the outer SD state dict wrapper.
    """
    _UNET_SUBFN_DEPTH: ContextVar[int] = ContextVar(f"_sd_depth_{short_name}", default=0)

    @functools.wraps(original)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        before = _UNET_SUBFN_DEPTH.get()
        _UNET_SUBFN_DEPTH.set(before + 1)
        lane = _ACTIVE_LANE_TRACE.get()
        _outer = (before == 0)
        emit = (_outer and lane is not None and lane._lane == "UNET")
        _nest_before = _unet_subfn_nesting_depth.get()
        _unet_subfn_nesting_depth.set(_nest_before + 1)
        _fn_start_ns = time.monotonic_ns() if emit else 0
        if emit:
            lane._trace.emit(f"unet_{short_name}_start", phase="restore", metadata={
                "category": category,
            })
        try:
            result = original(*args, **kwargs)
            if emit and short_name == "model_config_from_unet" and result is not None:
                _instrument_unet_model_config(result, lane)
            return result
        finally:
            after = _UNET_SUBFN_DEPTH.get()
            _UNET_SUBFN_DEPTH.set(after - 1)
            _unet_subfn_nesting_depth.set(_nest_before)
            if emit and _outer:
                _dur_ms = round((time.monotonic_ns() - _fn_start_ns) / 1_000_000, 3)
                lane._trace.emit(f"unet_{short_name}_end", phase="restore", metadata={
                    "category": category,
                    "duration_ms": _dur_ms,
                })
                # Record for outer SD residual computation (only direct children)
                if _nest_before == 0:
                    _children = _child_durations.get()
                    if _children is not None:
                        _children.append((short_name, _dur_ms))
    return wrapper


def _instrument_unet_model_config(model_config: Any, lane: "ModelLaneTrace") -> None:
    get_model = getattr(model_config, "get_model", None)
    if not callable(get_model) or getattr(get_model, _SENTINEL_SUBFN, False):
        return

    @functools.wraps(get_model)
    def wrapped_get_model(*args: Any, **kwargs: Any) -> Any:
        started_ns = time.monotonic_ns()
        lane._trace.emit("unet_model_config_get_model_start", phase="restore")
        _nest_before = _unet_subfn_nesting_depth.get()
        _unet_subfn_nesting_depth.set(_nest_before + 1)
        try:
            model = get_model(*args, **kwargs)
            _instrument_unet_model_weights(model, lane)
            return model
        finally:
            _unet_subfn_nesting_depth.set(_nest_before)
            duration_ms = round((time.monotonic_ns() - started_ns) / 1_000_000, 3)
            lane._trace.emit("unet_model_config_get_model_end", phase="restore", metadata={"duration_ms": duration_ms})
            children = _child_durations.get()
            if _nest_before == 0 and children is not None:
                children.append(("model_config_get_model", duration_ms))

    setattr(wrapped_get_model, _SENTINEL_SUBFN, True)
    try:
        model_config.get_model = wrapped_get_model
    except Exception:
        lane._trace.emit("unet_model_config_get_model_unavailable", phase="restore")


def _instrument_unet_model_weights(model: Any, lane: "ModelLaneTrace") -> None:
    load_weights = getattr(model, "load_model_weights", None)
    if not callable(load_weights) or getattr(load_weights, _SENTINEL_SUBFN, False):
        return

    @functools.wraps(load_weights)
    def wrapped_load_weights(*args: Any, **kwargs: Any) -> Any:
        started_ns = time.monotonic_ns()
        lane._trace.emit("unet_load_model_weights_start", phase="restore")
        _nest_before = _unet_subfn_nesting_depth.get()
        _unet_subfn_nesting_depth.set(_nest_before + 1)
        try:
            return load_weights(*args, **kwargs)
        finally:
            _unet_subfn_nesting_depth.set(_nest_before)
            duration_ms = round((time.monotonic_ns() - started_ns) / 1_000_000, 3)
            lane._trace.emit("unet_load_model_weights_end", phase="restore", metadata={"duration_ms": duration_ms})
            children = _child_durations.get()
            if _nest_before == 0 and children is not None:
                children.append(("load_model_weights", duration_ms))

    setattr(wrapped_load_weights, _SENTINEL_SUBFN, True)
    try:
        model.load_model_weights = wrapped_load_weights
    except Exception:
        lane._trace.emit("unet_load_model_weights_unavailable", phase="restore")


_SD_WRAPPER_INSTANCE: Any = None
"""Holds the ``sd.load_diffusion_model_state_dict`` wrapper to capture
both the full span and the residual computation."""


def _make_sd_state_dict_wrapper(original: Callable[..., Any]) -> Callable[..., Any]:
    """Wrap ``comfy.sd.load_diffusion_model_state_dict`` with UNET-lane guard.

    Emits:
    - ``unet_load_diffusion_model_state_dict_start/end`` span
    - ``unet_post_read_uninstrumented_residual`` with whole/child/residual ms.

    Reentrancy-safe via ``_sd_depth``.  Child durations are accumulated
    in a thread-local list via ``_child_durations``, populated by the
    sub-function wrappers in ``_make_unet_subfn_wrapper``.
    """
    global _SD_WRAPPER_INSTANCE

    @functools.wraps(original)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        before = _sd_depth.get()
        _sd_depth.set(before + 1)
        lane = _ACTIVE_LANE_TRACE.get()
        emit = (before == 0 and lane is not None and lane._lane == "UNET")
        _sd_start_ns = time.monotonic_ns() if emit else 0
        # Set up child duration tracking for this outer invocation.
        _prior_children = _child_durations.get()
        if emit:
            _child_durations.set([])
            lane._trace.emit("unet_load_diffusion_model_state_dict_start", phase="restore")
        try:
            return original(*args, **kwargs)
        finally:
            after = _sd_depth.get()
            _sd_depth.set(after - 1)
            if emit:  # before was 0, so we are the outermost invocation
                _children_raw = _child_durations.get() or []
                # Separate into legacy numeric and named tuples
                _legacy_durs: list[float] = []
                _named_children: list[tuple[str, float]] = []
                for _entry in _children_raw:
                    if isinstance(_entry, tuple):
                        _named_children.append(_entry)
                        _legacy_durs.append(_entry[1])
                    else:
                        _legacy_durs.append(_entry)
                _child_total = round(sum(_legacy_durs), 3)
                _whole_ms = round((time.monotonic_ns() - _sd_start_ns) / 1_000_000, 3)
                # Signed residual — allow negative when children exceed total
                _residual_ms = round(_whole_ms - _child_total, 3)
                _sd_status = "overlap_error" if _residual_ms < 0 else "ok"
                # Restore prior before emitting (children list snapshot taken)
                _child_durations.set(_prior_children)
                lane._trace.emit("unet_load_diffusion_model_state_dict_end", phase="restore", metadata={
                    "duration_ms": _whole_ms,
                    "model_construction_total_ms": _whole_ms,
                    "measured_child_total_ms": _child_total,
                    "measured_direct_children_ms": _child_total,
                    "measured_child_count": len(_named_children),
                    "measured_children": _legacy_durs,
                    "measured_named_children": _named_children,
                    "residual_ms": _residual_ms,
                    "model_construction_residual_ms": _residual_ms,
                    "status": _sd_status,
                    "classification": "residual_not_causal_owner",
                })

    setattr(wrapper, _SENTINEL_SD, True)
    _SD_WRAPPER_INSTANCE = wrapper
    return wrapper


def _install_sd_state_dict_wrapper(trace: RuntimeTrace | None = None) -> str:
    """Install the ``load_diffusion_model_state_dict`` wrapper on
    ``comfy.sd`` (live module in sys.modules).  Idempotent via sentinel."""
    global _sd_wrapper_installed
    if _sd_wrapper_installed:
        return "already_installed"
    mod = _get_live_module("comfy.sd")
    if mod is None:
        return "unavailable"
    original = getattr(mod, "load_diffusion_model_state_dict", None)
    if not callable(original):
        return "unavailable"
    if getattr(original, _SENTINEL_SD, False):
        _sd_wrapper_installed = True
        return "already_installed"
    with _wrappers_lock:
        if _sd_wrapper_installed:
            return "already_installed"
        if getattr(mod.load_diffusion_model_state_dict, _SENTINEL_SD, False):
            _sd_wrapper_installed = True
            return "already_installed"
        mod.load_diffusion_model_state_dict = _make_sd_state_dict_wrapper(
            mod.load_diffusion_model_state_dict
        )
        _sd_wrapper_installed = True
    if trace:
        trace.emit("unet_sd_wrapper_install", phase="restore", metadata={"status": "installed"})
    return "installed"


_UNET_DECOMPOSE_ENSURE_LOCK = RLock()
_unet_decompose_ensure_done: bool = False

def _ensure_unet_decompose_wrappers(trace: RuntimeTrace | None = None) -> dict[str, str]:
    """Install both the SD state dict wrapper and all subfunction wrappers.

    Returns combined ``{short_name: status}`` dict.  Global lock ensures
    exactly one full install attempt across all worker threads.
    """
    global _unet_decompose_ensure_done
    if _unet_decompose_ensure_done:
        return {}
    with _UNET_DECOMPOSE_ENSURE_LOCK:
        if _unet_decompose_ensure_done:
            return {}
        result: dict[str, str] = {}
        result["load_diffusion_model_state_dict"] = _install_sd_state_dict_wrapper(trace=trace)
        subfn_result = _install_unet_decompose_wrappers(trace=trace)
        result.update(subfn_result)
        _unet_decompose_ensure_done = True
        return result


# ── Phase 1-2: state machine and mutation lane ──────────────────────


class ModelLoadState(enum.Enum):
    """Single-flight state for one exact model identity.

    Transitions:
      PENDING → READING → CPU_READY → GPU_COMMITTING → READY
      any → FAILED
    """
    PENDING = "PENDING"
    READING = "READING"
    CPU_READY = "CPU_READY"
    GPU_COMMITTING = "GPU_COMMITTING"
    READY = "READY"
    FAILED = "FAILED"


_MUTATION_LANE_INSTANCE: "MutationLane | None" = None
_MUTATION_LANE_LOCK = RLock()


def _get_mutation_lane() -> "MutationLane":
    """Return the process-singleton mutation lane (lazy-init)."""
    global _MUTATION_LANE_INSTANCE
    if _MUTATION_LANE_INSTANCE is None:
        with _MUTATION_LANE_LOCK:
            if _MUTATION_LANE_INSTANCE is None:
                _MUTATION_LANE_INSTANCE = MutationLane()
    return _MUTATION_LANE_INSTANCE


class MutationLane:
    """FIFO serialization of GPU/cache mutation — does NOT preempt.

    Only one caller may hold the lane at a time.  Acquire blocks until
    the lane is free; release hands ownership to the next waiter (plain
    FIFO, no priority preemption).  Exception-safe via context manager.
    """

    _MUTEX_PRIORITY: dict[str, int] = {
        "UNET": 0, "CLIP": 1, "prefill": 2, "VAE": 3, "sampler": 4,
    }
    # NOTE: _MUTEX_PRIORITY is defined for documentation / forward
    # compatibility only.  The current implementation is plain FIFO —
    # priority does NOT preempt.

    def __init__(self) -> None:
        self._lock = RLock()
        self._owner: str | None = None
        self._cond = Condition(self._lock)

    def acquire(self, owner: str | None, timeout: float | None = None) -> bool:
        """Block until the lane is acquired — plain FIFO, no preemption."""
        if owner is None:
            return True  # no tracking for anonymous callers
        with self._cond:
            while self._owner is not None:
                # Priority: higher-priority waiters can preempt when current
                # owner releases. For now, simple FIFO with priority ordering
                # on acquire.
                if timeout is not None:
                    remaining = timeout
                self._cond.wait(timeout=timeout)
            self._owner = owner
        return True

    def release(self, owner: str | None) -> None:
        """Release the lane.  *owner* must match or be None."""
        if owner is None:
            return
        with self._cond:
            if self._owner == owner:
                self._owner = None
                self._cond.notify_all()

    @property
    def owner(self) -> str | None:
        with self._lock:
            return self._owner

    @contextmanager
    def lane_scope(self, owner: str) -> Iterator[None]:
        """Acquire on enter, release on exit (exception-safe)."""
        self.acquire(owner)
        try:
            yield
        finally:
            self.release(owner)


# ── ModelLaneTrace ───────────────────────────────────────────────────


class ModelLaneTrace:
    """Canonical per-lane event vocabulary for model-loading tracing.

    Provides standardised ``submitted``, ``read_start/read_end``,
    ``cpu_prepare_start/cpu_prepare_end``,
    ``gpu_lane_wait_start/gpu_lane_wait_end``,
    ``gpu_commit_start/gpu_commit_end``, ``ready/failed``, and
    ``graph_demand`` / ``graph_wait_start`` / ``graph_wait_end``
    events for UNET, CLIP, and (future) VAE lanes.

    All existing legacy events continue to be emitted unchanged.
    ``read_start/read_end`` fire from the ``comfy.utils.load_torch_file``
    wrapper.  ``gpu_commit_start/end`` fire from the
    ``comfy.model_management.load_models_gpu`` wrapper.
    ``cpu_prepare_start`` fires after the last expected ``read_end``;
    ``cpu_prepare_end`` fires before ``gpu_commit_start`` or at
    ``ready/failed``, whichever comes first.

    **expected_read_count**
        UNET normally performs one ``load_torch_file`` call (1).
        Single CLIP is 1; DualCLIP is 2.  When the observed read count
        differs from expected, ``cpu_prepare_start`` carries
        ``status="read_count_mismatch"``.

    **UNET-specific stages** (only emitted when ``_lane == "UNET"`` and
    ``_DIAGNOSTIC_FLAG`` is enabled):
        unet_file_stat_start/end, unet_file_open_start/end,
        unet_mmap_create_start/end, unet_load_torch_file_start/end,
        unet_safetensors_open_start/end, unet_safetensors_parse_start/end,
        unet_tensor_materialize_start/end or unet_safetensors_load_combined_start/end.
    """

    def __init__(
        self,
        trace: RuntimeTrace,
        lane: str,
        phase: str = "restore",
        *,
        expected_read_count: int = 1,
    ) -> None:
        self._trace = trace
        self._lane = lane
        self._phase = phase
        self.expected_read_count = max(0, int(expected_read_count))
        self._actual_read_count: int = 0
        self._cpu_prepare_started: bool = False
        self._cpu_prepare_ended: bool = False
        self._gpu_commit_started: bool = False
        # ── Worker queue/publication tracking ────────────────────
        self._submitted_at_ns: int = 0
        self._worker_started_at_ns: int = 0
        self._worker_ended_at_ns: int = 0
        self._cache_publish_started: bool = False
        self._cache_publish_completed: bool = False
        self._done_event_set: bool = False
        # Accumulated CLIP file-read wall time (ms).  Updated by
        # _on_read_completed(read_duration_ms=...) so _make_clip_load_wrapper
        # can avoid an O(n) event scan.  Only meaningful for CLIP lane.
        self._clip_read_total_ms: float = 0.0
        self._clip_read_started_ns: int = 0
        self._clip_pending_read_duration_ms: float | None = None

    # ── Internal lifecycle hooks (called by wrappers) ────────────────

    def _on_read_completed(self, read_duration_ms: float | None = None) -> None:
        """Called by the ``load_torch_file`` wrapper after each read_end.

        *read_duration_ms* — wall-time of the outer read_start..read_end
        interval.  When provided for CLIP lane, accumulated into
        ``_clip_read_total_ms`` so ``_make_clip_load_wrapper`` can avoid
        an O(n) event scan.
        """
        self._actual_read_count += 1
        if self._lane == "CLIP":
            if read_duration_ms is None:
                read_duration_ms = self._clip_pending_read_duration_ms
            self._clip_pending_read_duration_ms = None
            if read_duration_ms is not None:
                self._clip_read_total_ms += read_duration_ms
        if self._actual_read_count >= self.expected_read_count and not self._cpu_prepare_started:
            self._cpu_prepare_started = True
            if self.expected_read_count > 0 and self._actual_read_count != self.expected_read_count:
                self.cpu_prepare_start(status="read_count_mismatch",
                                       expected_read_count=self.expected_read_count,
                                       actual_read_count=self._actual_read_count)
                if self._lane == "CLIP":
                    self._trace.emit("clip_cpu_prepare_start", phase=self._phase, metadata={
                        "lane": self._lane,
                        "expected_read_count": self.expected_read_count,
                        "actual_read_count": self._actual_read_count,
                        "status": "read_count_mismatch",
                    })
            else:
                self.cpu_prepare_start(expected_read_count=self.expected_read_count,
                                       actual_read_count=self._actual_read_count)
                if self._lane == "CLIP":
                    self._trace.emit("clip_cpu_prepare_start", phase=self._phase, metadata={
                        "lane": self._lane,
                        "expected_read_count": self.expected_read_count,
                        "actual_read_count": self._actual_read_count,
                    })

    def _on_gpu_commit_about_to_start(self) -> None:
        """Called by the ``load_models_gpu`` wrapper before commit events."""
        if not self._cpu_prepare_ended:
            self._close_cpu_prepare(status="ok")
        self._gpu_commit_started = True

    def _close_cpu_prepare(self, status: str = "ok") -> None:
        """Emit ``cpu_prepare_end`` if ``cpu_prepare_start`` was emitted."""
        if self._cpu_prepare_started and not self._cpu_prepare_ended:
            self._cpu_prepare_ended = True
            self.cpu_prepare_end(status=status)

    # ── Producer-side lifecycle ──────────────────────────────────────

    def submitted(self, **metadata: Any) -> None:
        self._submitted_at_ns = time.monotonic_ns()
        self._trace.emit("submitted", phase=self._phase, metadata={"lane": self._lane, **metadata})

    def worker_start(self, **metadata: Any) -> None:
        self._worker_started_at_ns = time.monotonic_ns()
        # Capture thread and process CPU start for summary computation
        _tt = time.thread_time_ns() if hasattr(time, "thread_time_ns") else None
        _pt = time.process_time_ns() if hasattr(time, "process_time_ns") else None
        if _tt is not None:
            metadata["thread_time_ns"] = _tt
        if _pt is not None:
            metadata["process_time_ns"] = _pt
        self._trace.emit("background_unet_worker_start", phase=self._phase,
                         metadata={"lane": self._lane, **metadata})

    def worker_end(self, **metadata: Any) -> None:
        self._worker_ended_at_ns = time.monotonic_ns()
        # Capture thread and process CPU end for summary computation
        _tt = time.thread_time_ns() if hasattr(time, "thread_time_ns") else None
        _pt = time.process_time_ns() if hasattr(time, "process_time_ns") else None
        if _tt is not None:
            metadata["thread_time_ns"] = _tt
        if _pt is not None:
            metadata["process_time_ns"] = _pt
        self._trace.emit("background_unet_worker_end", phase=self._phase,
                         metadata={"lane": self._lane, **metadata})

    def worker_failed(self, **metadata: Any) -> None:
        self._trace.emit("background_unet_worker_failed", phase=self._phase,
                         metadata={"lane": self._lane, **metadata})

    def read_start(self, **metadata: Any) -> None:
        if self._lane == "CLIP":
            self._clip_read_started_ns = time.monotonic_ns()
        self._trace.emit("read_start", phase=self._phase, metadata={"lane": self._lane, **metadata})

    def read_end(self, **metadata: Any) -> None:
        if self._lane == "CLIP" and self._clip_read_started_ns:
            ended_ns = time.monotonic_ns()
            self._clip_pending_read_duration_ms = max(
                0.0, (ended_ns - self._clip_read_started_ns) / 1_000_000
            )
            self._clip_read_started_ns = 0
        self._trace.emit("read_end", phase=self._phase, metadata={"lane": self._lane, **metadata})

    def cpu_prepare_start(self, **metadata: Any) -> None:
        self._trace.emit("cpu_prepare_start", phase=self._phase, metadata={"lane": self._lane, **metadata})

    def cpu_prepare_end(self, **metadata: Any) -> None:
        self._trace.emit("cpu_prepare_end", phase=self._phase, metadata={"lane": self._lane, **metadata})

    def gpu_lane_wait_start(self, **metadata: Any) -> None:
        self._trace.emit("gpu_lane_wait_start", phase=self._phase, metadata={
            "lane": self._lane, "status": "unlocked", **metadata})
        # Also emit UNET-specific name
        if self._lane == "UNET":
            self._trace.emit("unet_gpu_lane_wait_start", phase=self._phase, metadata={
                "lane": self._lane, **metadata})

    def gpu_lane_wait_end(self, **metadata: Any) -> None:
        self._trace.emit("gpu_lane_wait_end", phase=self._phase, metadata={
            "lane": self._lane, "status": "unlocked", **metadata})
        if self._lane == "UNET":
            self._trace.emit("unet_gpu_lane_wait_end", phase=self._phase, metadata={
                "lane": self._lane, **metadata})

    def gpu_commit_start(self, **metadata: Any) -> None:
        self._trace.emit("gpu_commit_start", phase=self._phase, metadata={"lane": self._lane, **metadata})
        if self._lane == "UNET":
            self._trace.emit("unet_gpu_commit_start", phase=self._phase, metadata={
                "lane": self._lane, **metadata})

    def gpu_commit_end(self, **metadata: Any) -> None:
        self._trace.emit("gpu_commit_end", phase=self._phase, metadata={"lane": self._lane, **metadata})
        if self._lane == "UNET":
            self._trace.emit("unet_gpu_commit_end", phase=self._phase, metadata={
                "lane": self._lane, **metadata})

    def cache_publish_start(self, **metadata: Any) -> None:
        self._cache_publish_started = True
        self._trace.emit("unet_cache_publish_start", phase=self._phase,
                         metadata={"lane": self._lane, **metadata})

    def cache_object_store(self, **metadata: Any) -> None:
        self._trace.emit("unet_cache_object_store", phase=self._phase,
                         metadata={"lane": self._lane, **metadata})

    def cache_metadata_store(self, **metadata: Any) -> None:
        self._trace.emit("unet_cache_metadata_store", phase=self._phase,
                         metadata={"lane": self._lane, **metadata})

    def done_event_set(self, **metadata: Any) -> None:
        self._done_event_set = True
        self._trace.emit("unet_done_event_set", phase=self._phase,
                         metadata={"lane": self._lane, **metadata})

    def cache_publish_end(self, **metadata: Any) -> None:
        self._cache_publish_completed = True
        self._trace.emit("unet_cache_publish_end", phase=self._phase,
                         metadata={"lane": self._lane, **metadata})

    def ready(self, **metadata: Any) -> None:
        self._close_cpu_prepare(status="ok")
        # Only set ready after cache publication is complete
        self._trace.emit("ready", phase=self._phase, metadata={
            "lane": self._lane,
            "cache_publish_completed": self._cache_publish_completed,
            "done_event_set": self._done_event_set,
            **metadata,
        })

    def failed(self, **metadata: Any) -> None:
        self._close_cpu_prepare(status="error")
        self._trace.emit("failed", phase=self._phase, metadata={"lane": self._lane, **metadata})

    # ── UNET-specific file/safetensors stage methods ────────────────
    # Only meaningful for UNET lane with deep diag enabled.  These
    # mirror the deep diagnostic wrappers above.

    def unet_file_stat(self, **metadata: Any) -> None:
        self._trace.emit("unet_file_stat_start", phase=self._phase, metadata={"lane": self._lane, **metadata})
        self._trace.emit("unet_file_stat_end", phase=self._phase, metadata={"lane": self._lane})

    def unet_file_open(self, **metadata: Any) -> None:
        # INTENTIONALLY UNCALLED — the live safetensors/torch.load
        # implementations do not expose a separable Python-callable
        # file-open boundary.  This method exists only for forward
        # compatibility and the bg_unet_io summary correctly reports
        # it as None/absent.
        self._trace.emit("unet_file_open_start", phase=self._phase, metadata={"lane": self._lane, **metadata})
        self._trace.emit("unet_file_open_end", phase=self._phase, metadata={"lane": self._lane})

    def unet_mmap_create(self, **metadata: Any) -> None:
        self._trace.emit("unet_mmap_create_start", phase=self._phase, metadata={"lane": self._lane, **metadata})
        self._trace.emit("unet_mmap_create_end", phase=self._phase, metadata={"lane": self._lane})

    def unet_load_torch_file(self, **metadata: Any) -> None:
        self._trace.emit("unet_load_torch_file_start", phase=self._phase, metadata={"lane": self._lane, **metadata})
        self._trace.emit("unet_load_torch_file_end", phase=self._phase, metadata={"lane": self._lane})

    def post_load_cleanup(self, **metadata: Any) -> None:
        """Emit a truthful zero-duration post-load cleanup boundary.

        ComfyUI has no separable post-load cleanup call; this method emits
        start/end events at the same instant so the duration is truthfully
        0.0 rather than fabricating elapsed work or inferring it from a
        broad aggregate span.
        """
        _now_ns = time.monotonic_ns()
        self._trace.emit(
            "unet_post_load_cleanup_start", phase=self._phase,
            metadata={"lane": self._lane, **metadata},
        )
        self._trace.emit(
            "unet_post_load_cleanup_end", phase=self._phase,
            metadata={"lane": self._lane, "duration_ms": 0.0, **metadata},
        )

    # ── Consumer-side (graph demand) lifecycle ───────────────────────

    def graph_demand(self, **metadata: Any) -> None:
        self._trace.emit("graph_demand", phase="execution", metadata={"lane": self._lane, **metadata})

    def graph_wait_start(self, **metadata: Any) -> None:
        self._trace.emit("graph_wait_start", phase="execution", metadata={"lane": self._lane, **metadata})

    def graph_wait_end(self, **metadata: Any) -> None:
        self._trace.emit("graph_wait_end", phase="execution", metadata={"lane": self._lane, **metadata})


# ── External (legacy background UNET) lane scope ─────────────────────

@contextmanager
def external_model_lane_scope(
    trace: RuntimeTrace,
    *,
    lane: str = "UNET",
    phase: str = "restore",
    expected_read_count: int = 1,
) -> Iterator[ModelLaneTrace]:
    """Context manager for legacy background UNET thread lane tracing.

    Creates a dedicated ``ModelLaneTrace``, sets ``_ACTIVE_LANE_TRACE``,
    and ensures terminal ``ready()`` or ``failed()`` is emitted exactly
    once.  The *trace* must be a **dedicated** RuntimeTrace (not shared
    with the request/restore trace) — this manager never appends to a
    shared cross-thread list.

    On success the lane's events are stored into the module-level
    ``_BG_UNET_DIAG_STORE`` keyed by ``(lane, diagnostic_id)`` for
    later draining by the graph cache patcher.

    Usage::

        bg_trace = RuntimeTrace(process="remote_background_unet", ...)
        with external_model_lane_scope(bg_trace, lane="UNET", ...) as lane_trace:
            lane_trace.submitted()
            # ... worker body ...
    """
    lane_trace = ModelLaneTrace(trace, lane, phase=phase, expected_read_count=expected_read_count)
    # Emit background_unet_submitted immediately when scope opens
    _canonical_key_str = str(trace._metadata.get("canonical_key", "")) if hasattr(trace, "_metadata") else ""
    _diag_id_val = str(trace._metadata.get("diagnostic_id", "")) if hasattr(trace, "_metadata") else ""
    _resolved_path_val = str(trace._metadata.get("resolved_path", "")) if hasattr(trace, "_metadata") else ""
    lane_trace.submitted(canonical_key=_canonical_key_str, diagnostic_id=_diag_id_val)
    trace.emit("background_unet_submitted", phase=phase, metadata={
        "lane": lane, "canonical_key": _canonical_key_str, "diagnostic_id": _diag_id_val,
        "expected_read_count": expected_read_count,
    })
    # Set path filtering for deep diag wrappers
    _deep_path_token = None
    if _DIAGNOSTIC_FLAG:
        if _resolved_path_val:
            _deep_path_token = _DEEP_TARGET_PATH.set(_resolved_path_val)
    # NOTE: active-read before/after deltas are NOT sampled here.
    # Active-read delta computation is owned entirely by the exact
    # comfyapp _register_active_model_read / _complete_active_model_read
    # interval.  The background worker scope only owns its own
    # deep-diagnostic file-stat / safetensors boundaries.

    # Emit unet_file_stat from actual os.stat of the resolved path
    if _DIAGNOSTIC_FLAG and _resolved_path_val:
        try:
            _st = os.stat(_resolved_path_val)
            lane_trace.unet_file_stat(
                path_hash=_resolved_path_val[-48:],
                size=_st.st_size,
                st_dev=_st.st_dev,
                st_ino=_st.st_ino,
            )
        except OSError:
            lane_trace.unet_file_stat(path_hash=_resolved_path_val[-48:], size=None)

    # Install core dispatch + deep diag wrappers idempotently in the
    # real background worker thread so safetensors/torch.load boundaries
    # are instrumented under COMFYMODAL_V2_DEEP_MODEL_DIAG=1.
    _ensure_core_wrappers(trace=trace)

    # Install UNET decomposition wrappers (model_config_get_model,
    # load_model_weights, model_to, model_patcher_constructor, etc.)
    # idempotently so the background UNET trace emits the full set of
    # model-construction child stages.
    _ensure_unet_decompose_wrappers(trace=trace)

    token = _ACTIVE_LANE_TRACE.set(lane_trace)
    lane_trace.worker_start(canonical_key=_canonical_key_str)
    try:
        yield lane_trace
        lane_trace.worker_end()
        # Post-load cleanup boundary — truthfully 0.0 since ComfyUI has
        # no separable finalization call between model construction and
        # cache publication.  Placed after worker_end so the boundary
        # captures the explicit handoff point; called before ready() so
        # the cleanup stage precedes the terminal ready event.
        lane_trace.post_load_cleanup()
        # ready() is called AFTER cache publication completes — the
        # caller is responsible for calling cache_publish_start(),
        # cache_object_store(), cache_metadata_store(), done_event_set(),
        # cache_publish_end() before this scope exits.
        lane_trace.ready()
    except BaseException as exc:
        lane_trace.worker_end()
        lane_trace.post_load_cleanup(error_category=type(exc).__name__)
        lane_trace.worker_failed(error_category=type(exc).__name__)
        lane_trace.failed(error_category=type(exc).__name__)
        raise
    finally:
        _ACTIVE_LANE_TRACE.reset(token)
        if _deep_path_token is not None:
            _DEEP_TARGET_PATH.reset(_deep_path_token)

        # ── Emit bg_unet summaries from the worker's actual trace ──
        _emit_bg_unet_io_summary(trace, canonical_key=_canonical_key_str, force=True)
        _emit_bg_unet_stages_summary(trace, canonical_key=_canonical_key_str,
                                      weight_dtype=trace._metadata.get("weight_dtype", "") if hasattr(trace, "_metadata") else "",
                                      force=True)

        # Store completed events into the diagnostic store for later
        # draining by graph cache consumer.  Use a composite key that
        # includes diagnostic_id from the trace metadata when available.
        _store_key = f"{lane}:{_diag_id_val}" if _diag_id_val else lane
        with _BG_UNET_DIAG_LOCK:
            # Append (do not overwrite) to avoid losing previously stored events
            _existing = _BG_UNET_DIAG_STORE.setdefault(_store_key, [])
            _existing.extend(trace.events)


# ── Restore-return marker helpers ────────────────────────────────────


def set_restore_return_marker(
    restored_instance_id: str,
    restore_session_id: str,
    legacy_container_session_id: str,
    modal_task_id: str = "",
    pid: int = 0,
) -> None:
    """Set ``_LATEST_RESTORE_RETURN_MARKER`` immediately before restore return."""
    global _LATEST_RESTORE_RETURN_MARKER
    _LATEST_RESTORE_RETURN_MARKER = {
        **_capture_host_info(),
        "wall_unix_ns": int(time.time() * 1_000_000_000),
        "monotonic_ns": time.monotonic_ns(),
        "restored_instance_id": restored_instance_id,
        "restore_session_id": restore_session_id,
        "legacy_container_session_id": legacy_container_session_id,
        "modal_task_id": modal_task_id,
        "pid": pid,
    }


def get_restore_return_marker() -> dict[str, Any] | None:
    marker = _LATEST_RESTORE_RETURN_MARKER
    return dict(marker) if marker else None


def set_model_load_identity(restored_instance_id: str, restore_session_id: str) -> None:
    global _LATEST_RESTORED_INSTANCE_ID, _LATEST_RESTORE_SESSION_ID
    _LATEST_RESTORED_INSTANCE_ID = restored_instance_id
    _LATEST_RESTORE_SESSION_ID = restore_session_id


@contextmanager
def request_execution_trace_scope(trace: RuntimeTrace) -> Iterator[None]:
    _gpu_request_call_count_var.set(0)
    token = _ACTIVE_REQUEST_TRACE.set(trace)
    try:
        yield
    finally:
        _ACTIVE_REQUEST_TRACE.reset(token)


def reset_gpu_call_count() -> None:
    _gpu_request_call_count_var.set(0)


def gpu_wrapper_is_installed() -> bool:
    return _gpu_wrapper_installed


def gpu_call_count() -> int:
    return _gpu_request_call_count_var.get()


def gpu_not_observed_summary() -> dict[str, Any]:
    """Return request-scope GPU wrapper diagnostic summary.

    When a request makes zero ``load_models_gpu`` calls, this accessor
    reports ``caller_classification="not_observed"`` (wrapper installed)
    or ``"wrapper_unavailable"`` (wrapper not installed), together with
    the request ID, wrapper status, and invocation count.

    Preserves the installed/unavailable distinction and request-local
    invocation count.  No side effects on lane/request events.
    """
    wrapper_installed = _gpu_wrapper_installed
    request_id = get_active_request_id()
    cnt = _gpu_request_call_count_var.get()
    if wrapper_installed:
        return {
            "caller_classification": "not_observed" if cnt == 0 else "observed",
            "request_id": request_id,
            "wrapper_status": "installed",
            "count": cnt,
        }
    return {
        "caller_classification": "wrapper_unavailable",
        "request_id": request_id,
        "wrapper_status": "unavailable",
        "count": 0,
    }


def get_active_request_id() -> str:
    trace = _ACTIVE_REQUEST_TRACE.get()
    return str(trace.request_id) if trace is not None else ""


# ── Deep diagnostic helpers (guarded by COMFYMODAL_V2_DEEP_MODEL_DIAG) ──


def _capture_tid() -> int:
    """Return native thread ID (cross-platform)."""
    try:
        import threading
        return threading.get_native_id()
    except Exception:
        return 0


def _capture_host_info() -> dict[str, Any]:
    """Capture hostname, pid, and Linux boot_id when available."""
    info: dict[str, Any] = {
        "pid": os.getpid(),
        "native_tid": _capture_tid(),
        "hostname": platform.node(),
    }
    if platform.system() == "Linux":
        try:
            with open("/proc/sys/kernel/random/boot_id") as _f:
                info["boot_id"] = _f.read().strip()
        except Exception:
            pass
    return info


def _capture_rusage_thread_delta() -> dict[str, Any] | None:
    """Return RUSAGE_THREAD values.  Only on Linux with deep diag enabled."""
    if not _DIAGNOSTIC_FLAG:
        return None
    if platform.system() != "Linux":
        return None
    try:
        import resource
        ru = resource.getrusage(resource.RUSAGE_THREAD)
        return {
            "utime_ms": round(ru.ru_utime * 1000, 3),
            "stime_ms": round(ru.ru_stime * 1000, 3),
            "minflt": ru.ru_minflt,
            "majflt": ru.ru_majflt,
            "inblock": ru.ru_inblock,
            "oublock": ru.ru_oublock,
            "nvcsw": ru.ru_nvcsw,
            "nivcsw": ru.ru_nivcsw,
        }
    except Exception:
        return None


def _capture_rusage_thread_snapshot() -> dict[str, Any] | None:
    """Return a raw RUSAGE_THREAD snapshot for before/after delta computation.
    Requires Linux.  Does NOT require COMFYMODAL_V2_DEEP_MODEL_DIAG.
    Returns flat dict of ints.  The caller must compute deltas externally."""
    if platform.system() != "Linux":
        return None
    try:
        import resource
        ru = resource.getrusage(resource.RUSAGE_THREAD)
        return {
            "utime_us": round(ru.ru_utime * 1_000_000),
            "stime_us": round(ru.ru_stime * 1_000_000),
            "minflt": ru.ru_minflt,
            "majflt": ru.ru_majflt,
            "inblock": ru.ru_inblock,
            "oublock": ru.ru_oublock,
            "nvcsw": ru.ru_nvcsw,
            "nivcsw": ru.ru_nivcsw,
        }
    except Exception:
        return None


def _capture_proc_tid_io_snapshot() -> dict[str, int] | None:
    """Read /proc/self/task/<tid>/io for delta-capable counters.
    Only on Linux with deep diag enabled.  Returns dict of raw ints.
    The caller must compute deltas externally."""
    if not _DIAGNOSTIC_FLAG or platform.system() != "Linux":
        return None
    try:
        tid = _capture_tid()
        with open(f"/proc/self/task/{tid}/io") as _f:
            lines = _f.readlines()
        result: dict[str, int] = {}
        for line in lines:
            for prefix in ("rchar", "wchar", "syscr", "syscw",
                           "read_bytes", "write_bytes", "cancelled_write_bytes"):
                if line.startswith(prefix + ":"):
                    parts = line.strip().split(":")
                    if len(parts) == 2:
                        result[prefix] = int(parts[1].strip())
        return result
    except Exception:
        return None


def classify_active_read_dims(
    *,
    deep_diag: bool,
    before_tid: int | None = None,
    after_tid: int | None = None,
    has_thread_cpu: bool = False,
    has_process_cpu: bool = False,
    has_rusage: bool = False,
    has_io: bool = False,
    has_cgroup: bool = False,
    os_supports_thread_cpu: bool = True,
    os_supports_process_cpu: bool = True,
    os_supports_rusage: bool = True,
    os_supports_io: bool = True,
    os_supports_cgroup: bool = True,
) -> dict[str, str]:
    """Classify per-dimension active-read counter statuses using native thread IDs.

    Each dimension is classified independently.  Missing is not zero: a
    dimension whose before *or* after snapshot is missing gets a string status
    rather than a numeric zero.  A valid zero delta is only possible when both
    snapshots exist.

    Status vocabulary:
      ``available`` — data captured and valid for this dimension.
      ``unsupported`` — deep_diag is disabled; this OS class is not instrumented.
      ``unavailable`` — deep_diag enabled but the OS does not support this
          counter (e.g. ``resource.RUSAGE_THREAD`` on non-Linux).
      ``thread_changed`` — thread-bounded dimension whose before/after
          measurement spans different native threads; delta would be meaningless.
      ``not_observed_in_this_thread`` — deep_diag + same thread, the OS
          supports this counter, but no before-snapshot was captured for
          this dimension in this thread.
      ``no_before_snapshot`` — deep_diag enabled, OS supports, but before
          snapshot was not captured (e.g. late registration).
      ``aggregate_available`` — (cgroup) aggregate memory.stat values
          are present and merged from multiple dimensions.
      ``aggregate_partial`` — (cgroup) some but not all cgroup dimensions
          are available.
      ``aggregate_unavailable`` — (cgroup) no cgroup data at all, preventing
          aggregate status.

    Returns a dict keyed by dimension name with string status values.
    """
    _same_tid: bool = (before_tid is not None and after_tid is not None
                       and before_tid == after_tid)

    # ── Dimension definitions with per-dimension metadata ───────────
    _DIMS: list[tuple[str, bool]] = [
        ("thread_cpu", True),       # thread-bounded
        ("process_cpu", False),     # process-wide (not thread-bounded)
        ("io_deltas", True),        # thread-bounded
        ("page_faults", True),      # thread-bounded (RUSAGE_THREAD minflt/majflt)
        ("block_input", True),      # thread-bounded (RUSAGE_THREAD inblock/oublock)
        ("context_switches", True), # thread-bounded (RUSAGE_THREAD nvcsw/nivcsw)
        ("cgroup_memory", False),   # process-wide cgroup v2 memory.stat
    ]
    # ── Per-dimension data-captured flag mapping ────────────────────
    _HAS_MAP: dict[str, bool] = {
        "thread_cpu": has_thread_cpu,
        "process_cpu": has_process_cpu,
        "io_deltas": has_io,
        "page_faults": has_rusage,
        "block_input": has_rusage,
        "context_switches": has_rusage,
        "cgroup_memory": has_cgroup,
    }
    # ── Per-dimension OS-support flag mapping ───────────────────────
    _OS_SUPPORTS_MAP: dict[str, bool] = {
        "thread_cpu": os_supports_thread_cpu,
        "process_cpu": os_supports_process_cpu,
        "io_deltas": os_supports_io,
        "page_faults": os_supports_rusage,
        "block_input": os_supports_rusage,
        "context_switches": os_supports_rusage,
        "cgroup_memory": os_supports_cgroup,
    }

    result: dict[str, str] = {}
    if not deep_diag:
        for dim, _ in _DIMS:
            result[dim] = "unsupported"
        return result

    for dim, thread_bounded in _DIMS:
        has_data = _HAS_MAP[dim]
        os_supports = _OS_SUPPORTS_MAP[dim]
        if thread_bounded and not _same_tid:
            result[dim] = "thread_changed"
        elif not has_data:
            if not os_supports:
                result[dim] = "unavailable"
            else:
                result[dim] = "not_observed_in_this_thread"
        else:
            result[dim] = "available"

    # ── Cgroup aggregate status ─────────────────────────────────────
    cg_avail = has_cgroup
    if not deep_diag:
        result["cgroup_aggregate"] = "unsupported"
    elif not os_supports_cgroup:
        result["cgroup_aggregate"] = "unavailable"
    elif not cg_avail:
        result["cgroup_aggregate"] = "unavailable"
    else:
        result["cgroup_aggregate"] = "available"
    return result


def _compute_rusage_deltas(before: dict[str, Any] | None, after: dict[str, Any] | None) -> dict[str, Any] | None:
    """Compute rusage deltas (after - before). Both must share the same keys."""
    if not before or not after:
        return None
    result = {}
    for key in before:
        if key in after and isinstance(before[key], (int, float)) and isinstance(after[key], (int, float)):
            result[key] = max(0, after[key] - before[key])
    return result


def _compute_io_deltas(before: dict[str, int] | None, after: dict[str, int] | None) -> dict[str, int] | None:
    """Compute /proc/self/io deltas (after - before)."""
    if not before or not after:
        return None
    result = {}
    for key in before:
        if key in after and isinstance(before[key], int) and isinstance(after[key], int):
            result[key] = max(0, after[key] - before[key])
    return result


def _capture_proc_tid_io() -> dict[str, Any] | None:
    """Read /proc/self/task/<tid>/io for delta-capable counters.
    Only on Linux with deep diag enabled.  Returns raw values (not deltas)."""
    if not _DIAGNOSTIC_FLAG or platform.system() != "Linux":
        return None
    try:
        tid = _capture_tid()
        with open(f"/proc/self/task/{tid}/io") as _f:
            lines = _f.readlines()
        result: dict[str, int] = {}
        for line in lines:
            for prefix in ("rchar", "wchar", "syscr", "syscw",
                           "read_bytes", "write_bytes", "cancelled_write_bytes"):
                if line.startswith(prefix + ":"):
                    parts = line.strip().split(":")
                    if len(parts) == 2:
                        result[prefix] = int(parts[1].strip())
        return result
    except Exception:
        return None


def _capture_file_identity(path: str) -> dict[str, Any]:
    """Capture stat info for the file at *path*: st_dev, st_ino, size, mtime."""
    result: dict[str, Any] = {"path_hash": stable_hash(path or "")}
    if not path:
        return result
    try:
        st = os.stat(path)
        result["st_dev"] = st.st_dev
        result["st_ino"] = st.st_ino
        result["size"] = st.st_size
        result["st_mtime"] = round(st.st_mtime, 3)
        if _DIAGNOSTIC_FLAG and platform.system() == "Linux":
            try:
                # Attempt mount/filesystem identity via stat
                result["st_dev_major"] = os.major(st.st_dev)
                result["st_dev_minor"] = os.minor(st.st_dev)
            except Exception:
                pass
    except OSError:
        pass
    return result


# ── Slow model-read diagnostic helpers (threshold-gated) ──────────────
# Lightweight before-state (only wall/thread/process time + native TID)
# is captured before every CLIP load_torch_file call and every
# background-UNET active read.  Expensive diagnostics (/proc/meminfo,
# cgroup memory.stat) are only collected when elapsed >= threshold.


@dataclass
class _SlowReadBeforeState:
    """Inexpensive before-state captured before a model read.
    No /proc, cgroup, rusage, tensor, or module inspection allowed here."""
    mono_ns: int
    thread_time_ns: int | None
    process_time_ns: int | None
    tid: int


def _capture_slow_read_before() -> _SlowReadBeforeState:
    """Inexpensive before-state capturing only timing + native TID."""
    return _SlowReadBeforeState(
        mono_ns=time.monotonic_ns(),
        thread_time_ns=time.thread_time_ns() if hasattr(time, "thread_time_ns") else None,
        process_time_ns=time.process_time_ns() if hasattr(time, "process_time_ns") else None,
        tid=_capture_tid(),
    )


def _unescape_mountinfo_field(field: str) -> str:
    """Unescape mountinfo(5) escaped characters in a single field.

    Mountinfo encodes spaces as ``\\040``, tabs as ``\\011``, newlines as
    ``\\012``, and backslashes as ``\\134``.  Must unescape backslash first
    to avoid double-unescaping ``\\134040`` → ``\\040`` → `` ``.
    """
    field = field.replace("\\134", "\\")
    field = field.replace("\\011", "\t")
    field = field.replace("\\012", "\n")
    field = field.replace("\\040", " ")
    return field


def _discover_cgroup2_path() -> tuple[str | None, str | None]:
    """Discover the cgroup v2 mount path and the process's cgroup relative path.

    Uses ``/proc/self/mountinfo`` to find the cgroup2 mount point (not assuming
    ``/sys/fs/cgroup``) and ``/proc/self/cgroup`` to find the process's cgroup
    relative path.  Returns ``(mount_point, cgroup_relative_path)`` on success,
    ``(None, None)`` on any error.

    Injectable via ``_read_file_lines`` for testing.
    """
    try:
        # Find cgroup2 mount point
        mount_lines = _read_file_lines("/proc/self/mountinfo")
        mount_point: str | None = None
        for line in mount_lines:
            clean = line.strip()
            # Split on " - " to separate pre-separator fields from fs_type/post fields
            if " - " not in clean:
                continue
            pre_part, post_part = clean.split(" - ", 1)
            pre_parts = pre_part.split()
            post_fields = post_part.split()
            # mountinfo format (pre-separator):
            #   id parent_id major:minor root mount_point options ...
            # root is index 3, mount_point is index 4
            if len(pre_parts) >= 5 and len(post_fields) >= 1:
                fs_type = post_fields[0]
                if fs_type == "cgroup2":
                    raw_root = pre_parts[3]
                    raw_mount = pre_parts[4]
                    # Unescape escaped characters in root and mount_point
                    mount_point = _unescape_mountinfo_field(raw_mount)
                    # Also unescape root for safety (not directly used here)
                    break
        if mount_point is None:
            return None, None

        # Read /proc/self/cgroup for the cgroup relative path
        cgroup_lines = _read_file_lines("/proc/self/cgroup")
        cgroup_rel: str | None = None
        for line in cgroup_lines:
            line = line.strip()
            if not line:
                continue
            # Format: hierarchy-ID:controller-list:cgroup-path
            # For cgroupv2, hierarchy-ID is 0, controller-list is empty
            parts = line.split(":", 2)
            if len(parts) == 3 and parts[0] == "0" and parts[1] == "":
                cgroup_rel = parts[2]
                break
            # Fallback: any line with a path (some systems vary)
            if len(parts) == 3 and parts[1] == "" and parts[2]:
                cgroup_rel = parts[2]

        if cgroup_rel is None:
            # /proc/self/cgroup missing or malformed — nonfatal failure
            return None, None
        if cgroup_rel == "/":
            # Process is in root cgroup — memory.stat at mount_point directly
            return mount_point, ""

        return mount_point, cgroup_rel
    except Exception:
        return None, None


def _resolve_cgroup_memory_stat_path() -> str | None:
    """Resolve the actual path to the cgroup v2 memory.stat file.

    Returns the discovered path or ``None`` when cgroup v2 is unavailable
    or discovery fails.  Uses only the mount point discovered from
    ``/proc/self/mountinfo`` (no hardcoded fallback).
    Guards against relative-path traversal in the cgroup relative path.
    """
    mount_point, cgroup_rel = _discover_cgroup2_path()
    if mount_point is None:
        return None
    # Normalise and validate the cgroup relative path
    rel = cgroup_rel.lstrip("/") if cgroup_rel else ""
    # Prevent relative-path traversal: reject paths containing ".." segments
    if rel:
        _segments = rel.replace("\\", "/").split("/")
        if ".." in _segments:
            return None
        memory_stat_path = os.path.join(mount_point, rel, "memory.stat")
    else:
        memory_stat_path = os.path.join(mount_point, "memory.stat")
    if os.path.isfile(memory_stat_path):
        return memory_stat_path
    return None


def _read_file_lines(path: str) -> list[str]:
    """Read all lines from *path*.  Injectable for testing.

    Returns empty list on any error.
    """
    try:
        with open(path) as _f:
            return _f.readlines()
    except Exception:
        return []


def _parse_memory_stat(content: str) -> dict[str, int]:
    """Parse memory.stat content into a dict of ints.

    Extracts: file, inactive_file, active_file, workingset_refault_file,
    workingset_activate_file, pgfault, pgmajfault.
    """
    result: dict[str, int] = {}
    _TARGET_KEYS = frozenset({
        "file", "inactive_file", "active_file",
        "workingset_refault_file", "workingset_activate_file",
        "pgfault", "pgmajfault",
    })
    for line in content.splitlines():
        parts = line.strip().split()
        if len(parts) == 2 and parts[0] in _TARGET_KEYS:
            try:
                result[parts[0]] = int(parts[1])
            except ValueError:
                pass
    return result


def _read_cgroup_memory_stat() -> dict[str, int] | None:
    """Read cgroup v2 memory.stat using discovered path.

    Uses ``_discover_cgroup2_path`` to find the actual cgroup v2 mount
    and process cgroup.  Returns parsed dict or ``None`` on any error.
    """
    try:
        path = _resolve_cgroup_memory_stat_path()
        if path is None:
            return None
        content_lines = _read_file_lines(path)
        if not content_lines:
            return None
        return _parse_memory_stat("".join(content_lines))
    except Exception:
        return None


def _read_proc_meminfo_cached_available() -> dict[str, int | None] | None:
    """Read Cached and MemAvailable from /proc/meminfo.
    Only called after threshold exceeded.  Returns None on any error."""
    try:
        _cached: int | None = None
        _avail: int | None = None
        with open("/proc/meminfo") as _f:
            for _line in _f:
                if _line.startswith("Cached:"):
                    _cached = int(_line.split()[1])
                elif _line.startswith("MemAvailable:"):
                    _avail = int(_line.split()[1])
        return {"cached_kb": _cached, "mem_available_kb": _avail}
    except Exception:
        return None


def _capture_proc_self_io() -> dict[str, int] | None:
    """Read ``/proc/self/io`` for process-wide ``rchar`` and ``read_bytes``.

    Does NOT require ``COMFYMODAL_V2_DEEP_MODEL_DIAG``.  Returns ``None`` on
    any error or unsupported platform.  Missing files and unsupported platforms
    do not raise.  Unsupported/unavailable counters are represented truthfully,
    never invented zeroes.
    """
    if platform.system() != "Linux":
        return None
    try:
        result: dict[str, int] = {}
        with open("/proc/self/io") as _f:
            for _line in _f:
                for _prefix in ("rchar", "read_bytes"):
                    if _line.startswith(_prefix + ":"):
                        _parts = _line.strip().split(":")
                        if len(_parts) == 2:
                            result[_prefix] = int(_parts[1].strip())
        return result if result else None
    except Exception:
        return None


def _collect_rusage_and_io_snapshots() -> tuple[dict[str, Any] | None, dict[str, int] | None]:
    """Capture RUSAGE_THREAD and /proc/self/io snapshots
    for delta computation.  Dies silently on unsupported platforms."""
    _ru = None
    _io = None
    if platform.system() == "Linux":
        try:
            import resource
            _ru_raw = resource.getrusage(resource.RUSAGE_THREAD)
            _ru = {
                "minflt": _ru_raw.ru_minflt,
                "majflt": _ru_raw.ru_majflt,
                "inblock": _ru_raw.ru_inblock,
                "nvcsw": _ru_raw.ru_nvcsw,
                "nivcsw": _ru_raw.ru_nivcsw,
            }
        except Exception:
            pass
        try:
            _io = _capture_proc_self_io()
        except Exception:
            pass
    return _ru, _io


def _compute_rusage_deltas_simple(before: dict[str, Any] | None,
                                  after: dict[str, Any] | None) -> dict[str, Any] | None:
    """Compute rusage deltas (after - before). Both must share the same keys."""
    if not before or not after:
        return None
    result = {}
    for key in before:
        if key in after and isinstance(before[key], (int, float)) and isinstance(after[key], (int, float)):
            result[key] = max(0, after[key] - before[key])
    return result


def _compute_io_deltas_simple(before: dict[str, int] | None,
                              after: dict[str, int] | None) -> dict[str, int] | None:
    """Compute /proc/self/io deltas (after - before)."""
    if not before or not after:
        return None
    result = {}
    for key in before:
        if key in after and isinstance(before[key], int) and isinstance(after[key], int):
            result[key] = max(0, after[key] - before[key])
    return result


def _emit_slow_read_line(
    *,
    owner: str,
    loader_type: str,
    path_str: str,
    request_id: str,
    restore_session_id: str,
    restored_instance_id: str,
    before: _SlowReadBeforeState,
    after_mono_ns: int,
    after_thread_time_ns: int | None,
    after_process_time_ns: int | None,
    after_tid: int,
    before_rusage: dict[str, Any] | None = None,
    after_rusage: dict[str, Any] | None = None,
    before_io: dict[str, int] | None = None,
    after_io: dict[str, int] | None = None,
    active_read_entry: dict[str, Any] | None = None,
) -> None:
    """Collect all diagnostics and emit exactly one ``[v2.slow_model_read]`` line.
    Called only when elapsed >= threshold.  Missing/unsupported counters use
    ``None`` (printed as ``None``), never invented zeros.

    When *active_read_entry* is provided (UNET path), its pre-computed delta
    fields are used instead of recalculating from before/after snapshots.
    """
    # ── Elapsed wall time ───────────────────────────────────────────
    if active_read_entry is not None:
        elapsed_ms = active_read_entry.get("active_read_wall_ms")
    else:
        elapsed_ms = round((after_mono_ns - before.mono_ns) / 1_000_000, 3)

    # ── Path hash (normalized, never raw user path) ─────────────────
    path_hash = stable_hash(path_str or "")[:16]

    # ── File identity (stat inline) ─────────────────────────────────
    file_size: Any = None
    st_dev: Any = None
    st_ino: Any = None
    if active_read_entry is not None:
        file_size = active_read_entry.get("active_read_file_size")
        st_dev = active_read_entry.get("active_read_st_dev")
        st_ino = active_read_entry.get("active_read_st_ino")
    elif path_str:
        try:
            _st = os.stat(path_str)
            file_size = _st.st_size
            st_dev = _st.st_dev
            st_ino = _st.st_ino
        except OSError:
            pass

    # ── Thread / process CPU ────────────────────────────────────────
    _same_tid = bool(before.tid and before.tid == after_tid)
    _has_thread_cpu = before.thread_time_ns is not None and after_thread_time_ns is not None
    _has_process_cpu = before.process_time_ns is not None and after_process_time_ns is not None

    thread_cpu_ms: Any = None
    if active_read_entry is not None:
        thread_cpu_ms = active_read_entry.get("active_read_thread_cpu_ms")
    elif _has_thread_cpu and _same_tid:
        thread_cpu_ms = round((after_thread_time_ns - before.thread_time_ns) / 1_000_000, 3)

    process_cpu_ms: Any = None
    if active_read_entry is not None:
        process_cpu_ms = active_read_entry.get("active_read_process_cpu_ms")
    elif _has_process_cpu:
        process_cpu_ms = round((after_process_time_ns - before.process_time_ns) / 1_000_000, 3)

    # ── Counter deltas (rusage + io) ────────────────────────────────
    rchar_delta: Any = None
    read_bytes_delta: Any = None
    minor_faults_delta: Any = None
    major_faults_delta: Any = None
    inblock_delta: Any = None
    voluntary_cs_delta: Any = None
    involuntary_cs_delta: Any = None

    if active_read_entry is not None:
        rchar_delta = active_read_entry.get("active_read_rchar_delta")
        read_bytes_delta = active_read_entry.get("active_read_read_bytes_delta")
        major_faults_delta = active_read_entry.get("active_read_major_faults_delta")
        minor_faults_delta = active_read_entry.get("active_read_minor_faults_delta")
        inblock_delta = active_read_entry.get("active_read_inblock_delta")
        voluntary_cs_delta = active_read_entry.get("active_read_voluntary_context_switches_delta")
        involuntary_cs_delta = active_read_entry.get("active_read_involuntary_context_switches_delta")
    elif _same_tid and before_rusage is not None and after_rusage is not None:
        _rd = _compute_rusage_deltas_simple(before_rusage, after_rusage)
        if _rd:
            minor_faults_delta = _rd.get("minflt")
            major_faults_delta = _rd.get("majflt")
            inblock_delta = _rd.get("inblock")
            voluntary_cs_delta = _rd.get("nvcsw")
            involuntary_cs_delta = _rd.get("nivcsw")
    if _same_tid and before_io is not None and after_io is not None:
        _iod = _compute_io_deltas_simple(before_io, after_io)
        if _iod:
            rchar_delta = _iod.get("rchar")
            read_bytes_delta = _iod.get("read_bytes")

    # ── /proc/meminfo (threshold-gated) ─────────────────────────────
    _meminfo = _read_proc_meminfo_cached_available()
    cached_kb: Any = _meminfo.get("cached_kb") if _meminfo else None
    mem_available_kb: Any = _meminfo.get("mem_available_kb") if _meminfo else None

    # ── Cgroup v2 memory.stat (threshold-gated) ──────────────────────
    _cgroup = _read_cgroup_memory_stat()
    memory_file_bytes: Any = _cgroup.get("file") if _cgroup else None
    inactive_file_bytes: Any = _cgroup.get("inactive_file") if _cgroup else None
    active_file_bytes: Any = _cgroup.get("active_file") if _cgroup else None
    workingset_refault_file: Any = _cgroup.get("workingset_refault_file") if _cgroup else None
    workingset_activate_file: Any = _cgroup.get("workingset_activate_file") if _cgroup else None
    pgfault: Any = _cgroup.get("pgfault") if _cgroup else None
    pgmajfault: Any = _cgroup.get("pgmajfault") if _cgroup else None

    # ── Modal identity ──────────────────────────────────────────────
    modal_task_id = os.environ.get("MODAL_TASK_ID", "")
    modal_image_id = os.environ.get("MODAL_IMAGE_ID", "")
    cloud = os.environ.get("MODAL_CLOUD_PROVIDER", "")
    region = os.environ.get("MODAL_REGION", "")

    # ── Per-dimension independent status ────────────────────────────
    # Each dimension is classified independently using classify_active_read_dims.
    _is_linux = platform.system() == "Linux"
    _dim_statuses = classify_active_read_dims(
        deep_diag=True,
        before_tid=before.tid,
        after_tid=after_tid,
        has_thread_cpu=bool(_has_thread_cpu and _same_tid and thread_cpu_ms is not None),
        has_process_cpu=bool(_has_process_cpu and process_cpu_ms is not None),
        has_rusage=bool(_same_tid and any(v is not None for v in (
            minor_faults_delta, major_faults_delta, inblock_delta,
            voluntary_cs_delta, involuntary_cs_delta,
        ))),
        has_io=bool(_same_tid and any(v is not None for v in (
            rchar_delta, read_bytes_delta,
        ))),
        has_cgroup=bool(_cgroup is not None and memory_file_bytes is not None),
        os_supports_thread_cpu=_is_linux,
        os_supports_process_cpu=_is_linux,
        os_supports_rusage=_is_linux,
        os_supports_io=_is_linux,
        os_supports_cgroup=_is_linux,
    )

    # ── Aggregate counter_status (backward-compatible) ──────────────
    _counters_available = {k: v == "available" for k, v in _dim_statuses.items()
                           if k not in ("cgroup_aggregate",)}
    _valid_count = sum(1 for v in _counters_available.values() if v)
    _total_count = len(_counters_available) if _counters_available else 0

    if not _is_linux:
        counter_status: str = "unsupported"
    elif _valid_count == _total_count:
        counter_status = "available"
    elif _valid_count > 0:
        counter_status = "partial"
    else:
        counter_status = "unavailable"

    # ── thread_cpu_ratio and classification ─────────────────────────
    # Ratio = valid thread CPU delta / elapsed wall duration (both in ms).
    # classification: cpu_bound >= 0.80, wait_bound <= 0.20, mixed otherwise,
    # unknown when thread CPU unavailable.
    thread_cpu_ratio: float | str | None = None
    classification: str = "unknown"
    if elapsed_ms is not None and elapsed_ms > 0 and thread_cpu_ms is not None:
        _ratio = thread_cpu_ms / elapsed_ms
        thread_cpu_ratio = round(_ratio, 4)
        if _ratio >= 0.80:
            classification = "cpu_bound"
        elif _ratio <= 0.20:
            classification = "wait_bound"
        else:
            classification = "mixed"
    elif not _dim_statuses.get("thread_cpu", "") == "available":
        classification = "unknown"
    elif elapsed_ms is not None and elapsed_ms > 0 and thread_cpu_ms is not None:
        classification = "unknown"
    else:
        classification = "unknown"

    pid = os.getpid()
    native_thread_id = after_tid

    print(
        f"[v2.slow_model_read] "
        f"owner={owner} "
        f"loader_type={loader_type} "
        f"path_hash={path_hash} "
        f"file_size={file_size} "
        f"st_dev={st_dev} "
        f"st_ino={st_ino} "
        f"request_id={request_id} "
        f"restore_session_id={restore_session_id} "
        f"restored_instance_id={restored_instance_id} "
        f"modal_task_id={modal_task_id} "
        f"modal_image_id={modal_image_id} "
        f"cloud={cloud} "
        f"region={region} "
        f"pid={pid} "
        f"native_thread_id={native_thread_id} "
        f"elapsed_ms={elapsed_ms} "
        f"thread_cpu_ms={thread_cpu_ms} "
        f"process_cpu_ms={process_cpu_ms} "
        f"thread_cpu_ratio={thread_cpu_ratio} "
        f"classification={classification} "
        f"rchar_delta={rchar_delta} "
        f"read_bytes_delta={read_bytes_delta} "
        f"minor_faults_delta={minor_faults_delta} "
        f"major_faults_delta={major_faults_delta} "
        f"inblock_delta={inblock_delta} "
        f"voluntary_cs_delta={voluntary_cs_delta} "
        f"involuntary_cs_delta={involuntary_cs_delta} "
        f"memory_file_bytes={memory_file_bytes} "
        f"inactive_file_bytes={inactive_file_bytes} "
        f"active_file_bytes={active_file_bytes} "
        f"workingset_refault_file={workingset_refault_file} "
        f"workingset_activate_file={workingset_activate_file} "
        f"pgfault={pgfault} "
        f"pgmajfault={pgmajfault} "
        f"cached_kb={cached_kb} "
        f"mem_available_kb={mem_available_kb} "
        f"counter_status={counter_status} "
        f"dim_thread_cpu={_dim_statuses.get('thread_cpu', 'unknown')} "
        f"dim_process_cpu={_dim_statuses.get('process_cpu', 'unknown')} "
        f"dim_io_deltas={_dim_statuses.get('io_deltas', 'unknown')} "
        f"dim_page_faults={_dim_statuses.get('page_faults', 'unknown')} "
        f"dim_block_input={_dim_statuses.get('block_input', 'unknown')} "
        f"dim_context_switches={_dim_statuses.get('context_switches', 'unknown')} "
        f"dim_cgroup_memory={_dim_statuses.get('cgroup_memory', 'unknown')} "
        f"cgroup_aggregate={_dim_statuses.get('cgroup_aggregate', 'unknown')}",
        flush=True,
    )


# ── Background UNET diagnostic helpers ─────────────────────────────


def _make_bg_unet_diag_context(
    *,
    canonical_key: str,
    diagnostic_id: str,
    restored_instance_id: str,
    restore_session_id: str,
    modal_task_id: str = "",
) -> dict[str, Any]:
    """Return a metadata dict shared across all background UNET diagnostic events."""
    return {
        "canonical_key": canonical_key,
        "diagnostic_id": diagnostic_id,
        "restored_instance_id": restored_instance_id,
        "restore_session_id": restore_session_id,
        "modal_task_id": modal_task_id,
        "pid": os.getpid(),
        "native_tid": _capture_tid(),
        "hostname": platform.node(),
    }


# ── Summary emission helpers (one-line compact summaries) ──────────


def _collect_restore_events_for_summary(
    trace: RuntimeTrace,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Scan trace events for restore-breakdown and CLIP-stage timestamps.

    Returns ``(breakdown_dict, clip_stages_dict)``.  Missing stages are
    reported as ``None``; absent lanes as ``"absent"``.
    """
    breakdown: dict[str, Any] = {}
    clip: dict[str, Any] = {}
    # Iterate events and capture timestamps
    for evt in trace.events:
        if evt.name == "v2_bootstrap_restore_start":
            breakdown["bootstrap_start_ns"] = evt.monotonic_ns
        elif evt.name == "v2_bootstrap_restore_end":
            breakdown["bootstrap_end_ns"] = evt.monotonic_ns
        elif evt.name == "v2_unet_cache_patch_start":
            breakdown["unet_cache_patch_start_ns"] = evt.monotonic_ns
        elif evt.name == "v2_unet_cache_patch_end":
            breakdown["unet_cache_patch_end_ns"] = evt.monotonic_ns
        elif evt.name == "v2_clip_prepare_submit_start":
            breakdown["clip_prepare_submit_start_ns"] = evt.monotonic_ns
        elif evt.name == "v2_clip_prepare_submit_end":
            breakdown["clip_prepare_submit_end_ns"] = evt.monotonic_ns
        elif evt.name == "v2_clip_worker_wait_start":
            breakdown["clip_worker_wait_start_ns"] = evt.monotonic_ns
            clip["worker_wait_start_ns"] = evt.monotonic_ns
        elif evt.name == "v2_clip_worker_wait_end":
            breakdown["clip_worker_wait_end_ns"] = evt.monotonic_ns
            clip["worker_wait_end_ns"] = evt.monotonic_ns
        elif evt.name == "v2_clip_ready":
            clip["ready_ns"] = evt.monotonic_ns
        elif evt.name == "v2_unet_spec_extract_start":
            breakdown["unet_spec_extract_start_ns"] = evt.monotonic_ns
        elif evt.name == "v2_unet_spec_extract_end":
            breakdown["unet_spec_extract_end_ns"] = evt.monotonic_ns
        elif evt.name == "v2_background_unet_submit_start":
            breakdown["bg_unet_submit_start_ns"] = evt.monotonic_ns
        elif evt.name == "v2_background_unet_submit_end":
            breakdown["bg_unet_submit_end_ns"] = evt.monotonic_ns
        elif evt.name == "v2_restore_finalize_start":
            breakdown["restore_finalize_start_ns"] = evt.monotonic_ns
        elif evt.name == "v2_restore_finalize_end":
            breakdown["restore_finalize_end_ns"] = evt.monotonic_ns

    # Convert to ms where pairs exist
    result_breakdown: dict[str, Any] = {}
    _PAIRS = [
        ("bootstrap_ms", "bootstrap_start_ns", "bootstrap_end_ns"),
        ("unet_cache_patch_ms", "unet_cache_patch_start_ns", "unet_cache_patch_end_ns"),
        ("clip_prepare_submit_ms", "clip_prepare_submit_start_ns", "clip_prepare_submit_end_ns"),
        ("clip_worker_wait_ms", "clip_worker_wait_start_ns", "clip_worker_wait_end_ns"),
        ("unet_spec_extract_ms", "unet_spec_extract_start_ns", "unet_spec_extract_end_ns"),
        ("bg_unet_submit_ms", "bg_unet_submit_start_ns", "bg_unet_submit_end_ns"),
        ("restore_finalize_ms", "restore_finalize_start_ns", "restore_finalize_end_ns"),
    ]
    for key, start_key, end_key in _PAIRS:
        s = breakdown.get(start_key)
        e = breakdown.get(end_key)
        result_breakdown[key] = round((e - s) / 1_000_000, 3) if (s and e) else None

    # CLIP stages
    result_clip: dict[str, Any] = {
        "worker_queue_ms": None,
        "load_torch_file_ms": None,
        "read_to_ready_ms": None,
        "post_read_cpu_prepare_ms": None,
        "gpu_wait_ms": None,
        "gpu_commit_ms": None,
        "read_end_to_ready_ms": None,
        "worker_total_ms": None,
        "worker_close_wait_ms": result_breakdown.get("clip_worker_wait_ms"),
        "restore_finalization_ms": result_breakdown.get("restore_finalize_ms"),
    }
    for evt in trace.events:
        _meta = evt.metadata if hasattr(evt, "metadata") else {}
        if evt.name == "read_start" and _meta.get("lane") == "CLIP":
            clip["read_start_ns"] = evt.monotonic_ns
        elif evt.name == "read_end" and _meta.get("lane") == "CLIP":
            clip["read_end_ns"] = evt.monotonic_ns
        elif evt.name == "cpu_prepare_start" and _meta.get("lane") == "CLIP":
            clip["cpu_prepare_start_ns"] = evt.monotonic_ns
        elif evt.name == "cpu_prepare_end" and _meta.get("lane") == "CLIP":
            clip["cpu_prepare_end_ns"] = evt.monotonic_ns
        elif evt.name == "gpu_lane_wait_start" and _meta.get("lane") == "CLIP":
            clip["gpu_wait_start_ns"] = evt.monotonic_ns
        elif evt.name == "gpu_lane_wait_end" and _meta.get("lane") == "CLIP":
            clip["gpu_wait_end_ns"] = evt.monotonic_ns
        elif evt.name == "gpu_commit_start" and _meta.get("lane") == "CLIP":
            clip["gpu_commit_start_ns"] = evt.monotonic_ns
        elif evt.name == "gpu_commit_end" and _meta.get("lane") == "CLIP":
            clip["gpu_commit_end_ns"] = evt.monotonic_ns
        elif evt.name == "submitted" and _meta.get("lane") == "CLIP":
            clip["submitted_ns"] = evt.monotonic_ns
        elif evt.name == "preload_worker_started" and _meta.get("lane") == "clip":
            clip["worker_start_ns"] = evt.monotonic_ns
        elif evt.name == "clip_prepare_start":
            clip["worker_body_start_ns"] = evt.monotonic_ns
        elif evt.name == "clip_prepare_end":
            clip["worker_body_end_ns"] = evt.monotonic_ns

    rs = clip.get("read_start_ns")
    re = clip.get("read_end_ns")
    cps = clip.get("cpu_prepare_start_ns")
    cpe = clip.get("cpu_prepare_end_ns")
    gws = clip.get("gpu_wait_start_ns")
    gwe = clip.get("gpu_wait_end_ns")
    gcs = clip.get("gpu_commit_start_ns")
    gce = clip.get("gpu_commit_end_ns")
    rdy = clip.get("ready_ns")
    wws = clip.get("worker_wait_start_ns")
    wwe = clip.get("worker_wait_end_ns")

    if rs and rdy:
        result_clip["read_to_ready_ms"] = round((rdy - rs) / 1_000_000, 3)
    if cps and cpe:
        result_clip["post_read_cpu_prepare_ms"] = round((cpe - cps) / 1_000_000, 3)
    if gws and gwe:
        result_clip["gpu_wait_ms"] = round((gwe - gws) / 1_000_000, 3)
    if gcs and gce:
        result_clip["gpu_commit_ms"] = round((gce - gcs) / 1_000_000, 3)
    if re and rdy:
        result_clip["read_end_to_ready_ms"] = round((rdy - re) / 1_000_000, 3)
    if wws and wwe:
        result_clip["worker_close_wait_ms"] = round((wwe - wws) / 1_000_000, 3)
    if rs and re:
        result_clip["load_torch_file_ms"] = round((re - rs) / 1_000_000, 3)
    if clip.get("submitted_ns") and clip.get("worker_start_ns"):
        result_clip["worker_queue_ms"] = round((clip["worker_start_ns"] - clip["submitted_ns"]) / 1_000_000, 3)
    if clip.get("worker_body_start_ns") and clip.get("worker_body_end_ns"):
        result_clip["worker_total_ms"] = round((clip["worker_body_end_ns"] - clip["worker_body_start_ns"]) / 1_000_000, 3)

    return result_breakdown, result_clip


# ── CLIP CPU children compact summary ────────────────────────────────


def _emit_clip_cpu_children_summary(
    *,
    post_read_total_ms: float | None = None,
    file_read_total_ms: float | None = None,
    children: list[tuple[str, float]] | None = None,
    load_text_encoder_state_dicts_ms: float | None = None,
    detect_te_model_ms: float | None = None,
    state_dict_conversion_ms: float | None = None,
    clip_constructor_ms: float | None = None,
    model_patcher_ms: float | None = None,
    cache_publish_ms: float | None = None,
    cond_stage_model_init_ms: float | None = None,
    tokenizer_init_ms: float | None = None,
    load_sd_weights_ms: float | None = None,
    constructor_residual_ms: float | None = None,
    measured_children_ms: float = 0.0,
    residual_ms: float = 0.0,
    status: str = "ok",
) -> None:
    """Emit a compact [v2.clip_cpu_children] diagnostic line.

    Named stage fields are printed as-is (None when unavailable).
    *children* is rendered as an inline dict for compactness.

    Phase 3 fields:
      cond_stage_model_init_ms — time spent in ``target.clip(...)``
      tokenizer_init_ms — time spent in ``target.tokenizer(...)``
      load_sd_weights_ms — time spent in ``self.load_sd(...)``
      constructor_residual_ms — unattributed time inside CLIP.__init__
        after subtracting known children: clip_constructor_ms minus
        (cond_stage_model_init_ms + tokenizer_init_ms +
         load_sd_weights_ms + model_patcher_ms).  None when
        clip_constructor_ms is unavailable.
    """
    _children_dict: dict[str, float] = {}
    if children:
        for _name, _dur in children:
            _children_dict[_name] = round(_dur, 3)

    print(
        f"[v2.clip_cpu_children] "
        f"post_read_total_ms={post_read_total_ms} "
        f"file_read_total_ms={file_read_total_ms} "
        f"measured_children_ms={measured_children_ms} "
        f"residual_ms={residual_ms} "
        f"load_text_encoder_state_dicts_ms={load_text_encoder_state_dicts_ms} "
        f"detect_te_model_ms={detect_te_model_ms} "
        f"state_dict_conversion_ms={state_dict_conversion_ms} "
        f"clip_constructor_ms={clip_constructor_ms} "
        f"cond_stage_model_init_ms={cond_stage_model_init_ms} "
        f"tokenizer_init_ms={tokenizer_init_ms} "
        f"load_sd_weights_ms={load_sd_weights_ms} "
        f"model_patcher_ms={model_patcher_ms} "
        f"constructor_residual_ms={constructor_residual_ms} "
        f"cache_publish_ms={cache_publish_ms} "
        f"children={_children_dict} "
        f"status={status}",
        flush=True,
    )


# ── Background UNET IO/stages summary emission ──────────────────────


def _emit_bg_unet_io_summary(trace: RuntimeTrace, *, canonical_key: str = "",
                               target_path: str = "", force: bool = False) -> None:
    """Emit a compact [v2.bg_unet_io] line from trace events.

    Summarises file stat, open, mmap, safetensors open/parse/header,
    tensor enumeration, tensor materialization, dtype_conversion,
    state_dict_assembly, model_config, model_construction,
    load_model_weights, post_load_cleanup, cache_publish durations.
    Missing stages → None.  Only emits when deep diag produced
    events or *force* is True.

    Each stage reports wall_ms, thread_cpu_ms, process_cpu_ms,
    thread_cpu_ratio, tensor_count, materialized_bytes, source_dtype,
    and destination_dtype where applicable from trace event metadata.

    NOTE: file_open and mmap_create are always None/absent because the real
    safetensors/torch.load implementations do not expose separable Python-callable
    boundaries for these stages.  They are listed only for forward compatibility
    — do not emit synthetic values.
    """
    if not force and not _DIAGNOSTIC_FLAG:
        return
    stages: dict[str, Any] = {
        "file_stat_ms": None, "file_open_ms": None,
        "mmap_create_ms": None, "safetensors_open_ms": None,
        "safetensors_parse_ms": None, "header_parse_ms": None,
        "tensor_enumeration_ms": None,
        "tensor_materialization_ms": None,
        "dtype_conversion_ms": None,
        "state_dict_assembly_ms": None,
        "model_config_ms": None, "model_construction_ms": None,
        "load_model_weights_ms": None,
        "post_load_cleanup_ms": None, "cache_publish_ms": None,
        "safetensors_combined_ms": None,
        "load_torch_file_ms": None, "stage_split_available": None,
        "wall_ms": None, "thread_cpu_ms": None, "process_cpu_ms": None,
        "thread_cpu_ratio": None,
        "tensor_count": None, "materialized_bytes": None,
        "source_dtype": None, "destination_dtype": None,
    }
    _worker_wall_start_ns = 0
    _worker_wall_end_ns = 0
    _worker_thread_start_ns = 0
    _worker_thread_end_ns = 0
    _worker_proc_start_ns = 0
    _worker_proc_end_ns = 0
    events = trace.events
    for i, evt in enumerate(events):
        _meta = evt.metadata if hasattr(evt, "metadata") else {}
        if evt.name == "background_unet_worker_start":
            _worker_wall_start_ns = evt.monotonic_ns
            _worker_thread_start_ns = _meta.get("thread_time_ns", 0) if _meta else 0
            _worker_proc_start_ns = _meta.get("process_time_ns", 0) if _meta else 0
        elif evt.name == "background_unet_worker_end":
            _worker_wall_end_ns = evt.monotonic_ns
            _worker_thread_end_ns = _meta.get("thread_time_ns", 0) if _meta else 0
            _worker_proc_end_ns = _meta.get("process_time_ns", 0) if _meta else 0
        # unet_file_stat_start -> unet_file_stat_end
        if evt.name == "unet_file_stat_start":
            for j in range(i + 1, min(i + 20, len(events))):
                if events[j].name == "unet_file_stat_end":
                    stages["file_stat_ms"] = round((events[j].monotonic_ns - evt.monotonic_ns) / 1_000_000, 3)
                    break
        elif evt.name == "unet_file_open_start":
            for j in range(i + 1, min(i + 20, len(events))):
                if events[j].name == "unet_file_open_end":
                    stages["file_open_ms"] = round((events[j].monotonic_ns - evt.monotonic_ns) / 1_000_000, 3)
                    break
        elif evt.name == "unet_mmap_create_start":
            for j in range(i + 1, min(i + 20, len(events))):
                if events[j].name == "unet_mmap_create_end":
                    stages["mmap_create_ms"] = round((events[j].monotonic_ns - evt.monotonic_ns) / 1_000_000, 3)
                    break
        elif evt.name == "unet_safetensors_open_start":
            for j in range(i + 1, min(i + 80, len(events))):
                if events[j].name == "unet_safetensors_open_end":
                    stages["safetensors_open_ms"] = round((events[j].monotonic_ns - evt.monotonic_ns) / 1_000_000, 3)
                    break
        elif evt.name == "unet_safetensors_parse_start":
            for j in range(i + 1, min(i + 40, len(events))):
                if events[j].name == "unet_safetensors_parse_end":
                    stages["safetensors_parse_ms"] = round((events[j].monotonic_ns - evt.monotonic_ns) / 1_000_000, 3)
                    stages["stage_split_available"] = _meta.get("stage_split_available", False)
                    stages["tensor_count"] = _meta.get("tensor_count", stages["tensor_count"])
                    break
        elif evt.name == "unet_header_parse_start":
            for j in range(i + 1, min(i + 40, len(events))):
                if events[j].name == "unet_header_parse_end":
                    stages["header_parse_ms"] = round((events[j].monotonic_ns - evt.monotonic_ns) / 1_000_000, 3)
                    stages["source_dtype"] = _meta.get("source_dtype", stages["source_dtype"])
                    stages["destination_dtype"] = _meta.get("destination_dtype", stages["destination_dtype"])
                    break
        elif evt.name == "unet_tensor_enumeration_start":
            for j in range(i + 1, min(i + 200, len(events))):
                if events[j].name == "unet_tensor_enumeration_end":
                    stages["tensor_enumeration_ms"] = round((events[j].monotonic_ns - evt.monotonic_ns) / 1_000_000, 3)
                    stages["tensor_count"] = _meta.get("tensor_count", stages["tensor_count"])
                    break
        elif evt.name == "unet_tensor_materialize_aggregated":
            stages["tensor_count"] = _meta.get("tensor_count", stages["tensor_count"])
            stages["materialized_bytes"] = _meta.get("total_bytes", stages["materialized_bytes"])
        elif evt.name == "unet_tensor_materialize_start":
            for j in range(i + 1, min(i + 200, len(events))):
                if events[j].name == "unet_tensor_materialize_end":
                    _prev = stages.get("tensor_materialization_ms", 0) or 0
                    stages["tensor_materialization_ms"] = round(
                        _prev + (events[j].monotonic_ns - evt.monotonic_ns) / 1_000_000, 3)
                    break
        elif evt.name == "unet_dtype_conversion_start":
            for j in range(i + 1, min(i + 100, len(events))):
                if events[j].name == "unet_dtype_conversion_end":
                    stages["dtype_conversion_ms"] = round((events[j].monotonic_ns - evt.monotonic_ns) / 1_000_000, 3)
                    stages["source_dtype"] = _meta.get("source_dtype", stages["source_dtype"])
                    stages["destination_dtype"] = _meta.get("destination_dtype", stages["destination_dtype"])
                    break
        elif evt.name == "unet_state_dict_assembly_start":
            for j in range(i + 1, min(i + 100, len(events))):
                if events[j].name == "unet_state_dict_assembly_end":
                    stages["state_dict_assembly_ms"] = round((events[j].monotonic_ns - evt.monotonic_ns) / 1_000_000, 3)
                    break
        elif evt.name == "unet_model_config_start":
            for j in range(i + 1, min(i + 100, len(events))):
                if events[j].name == "unet_model_config_end":
                    stages["model_config_ms"] = round((events[j].monotonic_ns - evt.monotonic_ns) / 1_000_000, 3)
                    break
        elif evt.name == "unet_load_diffusion_model_state_dict_start":
            for j in range(i + 1, min(i + 300, len(events))):
                if events[j].name == "unet_load_diffusion_model_state_dict_end":
                    stages["model_construction_ms"] = events[j].metadata.get("duration_ms", 0) if hasattr(events[j], "metadata") else 0
                    break
        elif evt.name == "unet_load_model_weights_end":
            stages["load_model_weights_ms"] = _meta.get("duration_ms", stages["load_model_weights_ms"])
        elif evt.name == "unet_post_load_cleanup_start":
            for j in range(i + 1, min(i + 50, len(events))):
                if events[j].name == "unet_post_load_cleanup_end":
                    stages["post_load_cleanup_ms"] = round((events[j].monotonic_ns - evt.monotonic_ns) / 1_000_000, 3)
                    break
        elif evt.name == "unet_cache_publish_start":
            for j in range(i + 1, min(i + 100, len(events))):
                if events[j].name == "unet_cache_publish_end":
                    stages["cache_publish_ms"] = round((events[j].monotonic_ns - evt.monotonic_ns) / 1_000_000, 3)
                    break
        elif evt.name == "unet_safetensors_load_combined_start":
            for j in range(i + 1, min(i + 200, len(events))):
                if events[j].name == "unet_safetensors_load_combined_end":
                    stages["safetensors_combined_ms"] = round(
                        (events[j].monotonic_ns - evt.monotonic_ns) / 1_000_000, 3)
                    stages["stage_split_available"] = False
                    break
        elif evt.name == "unet_load_torch_file_start":
            for j in range(i + 1, min(i + 200, len(events))):
                if events[j].name == "unet_load_torch_file_end":
                    stages["load_torch_file_ms"] = round(
                        (events[j].monotonic_ns - evt.monotonic_ns) / 1_000_000, 3)
                    break

    # ── Worker wall, thread CPU, process CPU, ratio ─────────────────
    if _worker_wall_start_ns and _worker_wall_end_ns:
        _wall_ms = round((_worker_wall_end_ns - _worker_wall_start_ns) / 1_000_000, 3)
        stages["wall_ms"] = _wall_ms
        if _worker_thread_start_ns and _worker_thread_end_ns:
            _tcpu = round((_worker_thread_end_ns - _worker_thread_start_ns) / 1_000_000, 3)
            stages["thread_cpu_ms"] = _tcpu
            if _wall_ms > 0:
                stages["thread_cpu_ratio"] = round(_tcpu / _wall_ms, 4)
        if _worker_proc_start_ns and _worker_proc_end_ns:
            stages["process_cpu_ms"] = round((_worker_proc_end_ns - _worker_proc_start_ns) / 1_000_000, 3)

    print(
        f"[v2.bg_unet_io] "
        f"file_stat_ms={stages['file_stat_ms']} "
        f"file_open_ms={stages['file_open_ms']} "
        f"mmap_create_ms={stages['mmap_create_ms']} "
        f"safetensors_open_ms={stages['safetensors_open_ms']} "
        f"safetensors_parse_ms={stages['safetensors_parse_ms']} "
        f"header_parse_ms={stages['header_parse_ms']} "
        f"tensor_enumeration_ms={stages['tensor_enumeration_ms']} "
        f"tensor_materialization_ms={stages['tensor_materialization_ms']} "
        f"dtype_conversion_ms={stages['dtype_conversion_ms']} "
        f"state_dict_assembly_ms={stages['state_dict_assembly_ms']} "
        f"model_config_ms={stages['model_config_ms']} "
        f"model_construction_ms={stages['model_construction_ms']} "
        f"load_model_weights_ms={stages['load_model_weights_ms']} "
        f"post_load_cleanup_ms={stages['post_load_cleanup_ms']} "
        f"cache_publish_ms={stages['cache_publish_ms']} "
        f"safetensors_combined_ms={stages['safetensors_combined_ms']} "
        f"load_torch_file_ms={stages['load_torch_file_ms']} "
        f"stage_split_available={stages['stage_split_available']} "
        f"wall_ms={stages['wall_ms']} "
        f"thread_cpu_ms={stages['thread_cpu_ms']} "
        f"process_cpu_ms={stages['process_cpu_ms']} "
        f"thread_cpu_ratio={stages['thread_cpu_ratio']} "
        f"tensor_count={stages['tensor_count']} "
        f"materialized_bytes={stages['materialized_bytes']} "
        f"source_dtype={stages['source_dtype']} "
        f"destination_dtype={stages['destination_dtype']} "
        f"canonical_key={canonical_key[-32:] if canonical_key else ''}",
        flush=True,
    )


def _emit_bg_unet_stages_summary(trace: RuntimeTrace, *, canonical_key: str = "",
                                   weight_dtype: str = "", force: bool = False) -> None:
    """Emit compact [v2.bg_unet_stages] line from trace events.

    Summarises worker queue, model construction subfunction durations, GPU commit,
    and cache publication.  Missing stages → None.
    Zero-valued stages (e.g. post_load_cleanup_ms) are reported as 0.0, not None.
    """
    if not force and not _DIAGNOSTIC_FLAG:
        return
    stages: dict[str, Any] = {
        "submission_to_worker_start_ms": None,
        "worker_wall_ms": None, "worker_thread_cpu_ms": None,
        "model_construction_total_ms": None,
        "measured_direct_children_ms": None,
        "model_construction_residual_ms": None,
        "model_config_get_model_ms": None,
        "load_model_weights_ms": None,
        "load_torch_file_ms": None,
        "convert_old_quants_ms": None,
        "model_patcher_constructor_ms": None,
        "model_to_ms": None,
        "state_dict_prefix_replace_ms": None,
        "post_load_cleanup_ms": None,
        "fast_children_le_1ms": 0.0,
        "gpu_lane_wait_ms": None, "gpu_commit_ms": None,
        "cache_publish_ms": None,
        "background_gpu_transfer_present": False,
        "thread_cpu_ms": None, "process_cpu_ms": None,
        "thread_cpu_ratio": None,
        "weight_dtype": weight_dtype,
    }
    events = trace.events
    _submitted_ns = 0
    _worker_start_ns = 0
    _worker_end_ns = 0
    _worker_thread_start_ns = 0
    _worker_thread_end_ns = 0
    _worker_proc_start_ns = 0
    _worker_proc_end_ns = 0
    _gpu_wait_start = 0
    _gpu_wait_end = 0
    _gpu_commit_start = 0
    _gpu_commit_end = 0
    _cache_pub_start = 0
    _cache_pub_end = 0
    _sd_total = 0.0
    _children_total = 0.0
    _sd_found = False

    for i, evt in enumerate(events):
        _meta = evt.metadata if hasattr(evt, "metadata") else {}
        if evt.name == "background_unet_submitted":
            _submitted_ns = evt.monotonic_ns
        elif evt.name == "background_unet_worker_start":
            _worker_start_ns = evt.monotonic_ns
            _worker_thread_start_ns = _meta.get("thread_time_ns", 0)
            _worker_proc_start_ns = _meta.get("process_time_ns", 0)
        elif evt.name == "background_unet_worker_end":
            _worker_end_ns = evt.monotonic_ns
            _worker_thread_end_ns = _meta.get("thread_time_ns", 0)
            _worker_proc_end_ns = _meta.get("process_time_ns", 0)
        elif evt.name == "unet_gpu_lane_wait_start":
            _gpu_wait_start = evt.monotonic_ns
        elif evt.name == "unet_gpu_lane_wait_end":
            _gpu_wait_end = evt.monotonic_ns
        elif evt.name == "unet_gpu_commit_start":
            _gpu_commit_start = evt.monotonic_ns
        elif evt.name == "unet_gpu_commit_end":
            _gpu_commit_end = evt.monotonic_ns
        elif evt.name == "unet_cache_publish_start":
            _cache_pub_start = evt.monotonic_ns
        elif evt.name == "unet_cache_publish_end":
            _cache_pub_end = evt.monotonic_ns
        elif evt.name == "unet_load_diffusion_model_state_dict_start":
            _sd_start = evt.monotonic_ns
            for j in range(i + 1, min(i + 300, len(events))):
                if events[j].name == "unet_load_diffusion_model_state_dict_end":
                    _sd_found = True
                    _sd_total = events[j].metadata.get("duration_ms", 0) if hasattr(events[j], "metadata") else 0
                    _children_total = events[j].metadata.get("measured_child_total_ms", 0) if hasattr(events[j], "metadata") else 0
                    break
        elif evt.name == "unet_model_config_get_model_end":
            _val = evt.metadata.get("duration_ms")
            if _val is not None:
                stages["model_config_get_model_ms"] = (stages["model_config_get_model_ms"] or 0) + _val
        elif evt.name == "unet_load_model_weights_end":
            _val = evt.metadata.get("duration_ms")
            if _val is not None:
                stages["load_model_weights_ms"] = (stages["load_model_weights_ms"] or 0) + _val
        elif evt.name == "unet_state_dict_prefix_replace_end":
            _val = evt.metadata.get("duration_ms")
            if _val is not None:
                stages["state_dict_prefix_replace_ms"] = (stages["state_dict_prefix_replace_ms"] or 0) + _val
        elif evt.name == "unet_convert_old_quants_end":
            _val = evt.metadata.get("duration_ms")
            if _val is not None:
                stages["convert_old_quants_ms"] = (stages["convert_old_quants_ms"] or 0) + _val
        elif evt.name == "unet_model_patcher_constructor_end":
            _val = evt.metadata.get("duration_ms")
            if _val is not None:
                stages["model_patcher_constructor_ms"] = (stages["model_patcher_constructor_ms"] or 0) + _val
        elif evt.name == "unet_model_to_end":
            _val = evt.metadata.get("duration_ms")
            if _val is not None:
                stages["model_to_ms"] = (stages["model_to_ms"] or 0) + _val
        elif evt.name == "unet_load_torch_file_start":
            for j in range(i + 1, min(i + 200, len(events))):
                if events[j].name == "unet_load_torch_file_end":
                    stages["load_torch_file_ms"] = round(
                        (events[j].monotonic_ns - evt.monotonic_ns) / 1_000_000, 3)
                    break
        elif evt.name == "unet_post_load_cleanup_end":
            _dur = _meta.get("duration_ms")
            if _dur is not None:
                stages["post_load_cleanup_ms"] = round(_dur, 3)

    if _submitted_ns and _worker_start_ns:
        stages["submission_to_worker_start_ms"] = round((_worker_start_ns - _submitted_ns) / 1_000_000, 3)
    if _worker_start_ns and _worker_end_ns:
        _wall_ms = round((_worker_end_ns - _worker_start_ns) / 1_000_000, 3)
        stages["worker_wall_ms"] = _wall_ms
        # Thread CPU from worker_start/end metadata (captured via thread_time_ns)
        if _worker_thread_start_ns and _worker_thread_end_ns:
            _tcpu = round((_worker_thread_end_ns - _worker_thread_start_ns) / 1_000_000, 3)
            stages["thread_cpu_ms"] = _tcpu
            if _wall_ms > 0:
                stages["thread_cpu_ratio"] = round(_tcpu / _wall_ms, 4)
        # Process CPU
        if _worker_proc_start_ns and _worker_proc_end_ns:
            stages["process_cpu_ms"] = round((_worker_proc_end_ns - _worker_proc_start_ns) / 1_000_000, 3)
    if _gpu_wait_start and _gpu_wait_end:
        stages["gpu_lane_wait_ms"] = round((_gpu_wait_end - _gpu_wait_start) / 1_000_000, 3)
        stages["background_gpu_transfer_present"] = True
    if _gpu_commit_start and _gpu_commit_end:
        stages["gpu_commit_ms"] = round((_gpu_commit_end - _gpu_commit_start) / 1_000_000, 3)
        stages["background_gpu_transfer_present"] = True
    if _cache_pub_start and _cache_pub_end:
        stages["cache_publish_ms"] = round((_cache_pub_end - _cache_pub_start) / 1_000_000, 3)

    # Fix falsy-zero bug: when the SD wrapper event was found (even with 0.0),
    # report the literal value; when absent, report None.
    if _sd_found:
        stages["model_construction_total_ms"] = round(_sd_total, 3)
        stages["measured_direct_children_ms"] = round(_children_total, 3)
        stages["model_construction_residual_ms"] = round(_sd_total - _children_total, 3)

    # Separate children >1ms from fast (≤1ms) ones
    _other_named: dict[str, float] = {}
    _fast_total = 0.0
    for _nkey, _nms in (
        ("model_config_get_model", stages["model_config_get_model_ms"]),
        ("load_model_weights", stages["load_model_weights_ms"]),
        ("convert_old_quants", stages["convert_old_quants_ms"]),
        ("state_dict_prefix_replace", stages["state_dict_prefix_replace_ms"]),
        ("model_patcher_constructor", stages["model_patcher_constructor_ms"]),
        ("model_to", stages["model_to_ms"]),
    ):
        if _nms is not None:
            if _nms > 1.0:
                _other_named[_nkey] = round(_nms, 3)
            else:
                _fast_total += _nms
    stages["fast_children_le_1ms"] = round(_fast_total, 3)

    print(
        f"[v2.bg_unet_stages] "
        f"submission_to_worker_start_ms={stages['submission_to_worker_start_ms']} "
        f"worker_wall_ms={stages['worker_wall_ms']} "
        f"model_construction_total_ms={stages['model_construction_total_ms']} "
        f"measured_direct_children_ms={stages['measured_direct_children_ms']} "
        f"model_construction_residual_ms={stages['model_construction_residual_ms']} "
        + " ".join(f"{k}={v}" for k, v in sorted(_other_named.items()))
        + f" gpu_lane_wait_ms={stages['gpu_lane_wait_ms']} "
        f"gpu_commit_ms={stages['gpu_commit_ms']} "
        f"cache_publish_ms={stages['cache_publish_ms']} "
        f"background_gpu_transfer_present={stages['background_gpu_transfer_present']} "
        f"load_torch_file_ms={stages['load_torch_file_ms']} "
        f"post_load_cleanup_ms={stages['post_load_cleanup_ms']} "
        f"thread_cpu_ms={stages['thread_cpu_ms']} "
        f"process_cpu_ms={stages['process_cpu_ms']} "
        f"thread_cpu_ratio={stages['thread_cpu_ratio']} "
        f"fast_children_le_1ms={stages['fast_children_le_1ms']} "
        f"weight_dtype={stages['weight_dtype']} "
        f"canonical_key={canonical_key[-32:] if canonical_key else ''}",
        flush=True,
    )


@dataclass
class PreparationDiagnostics:
    unet_started_at: float = 0.0
    unet_completed_at: float = 0.0
    clip_started_at: float = 0.0
    clip_completed_at: float = 0.0
    vae_started_at: float = 0.0
    vae_completed_at: float = 0.0
    prefill_started_at: float = 0.0
    prefill_completed_at: float = 0.0
    unet_demanded_at: float = 0.0
    clip_demanded_at: float = 0.0
    vae_demanded_at: float = 0.0
    prefill_demanded_at: float = 0.0
    unet_wait_ms: float = 0.0
    clip_wait_ms: float = 0.0
    vae_wait_ms: float = 0.0
    prefill_wait_ms: float = 0.0
    unet_work_completed_before_demand_ms: float = 0.0
    clip_work_completed_before_demand_ms: float = 0.0
    vae_work_completed_before_demand_ms: float = 0.0
    prefill_work_completed_before_demand_ms: float = 0.0
    unet_actual_graph_wait_ms: float = 0.0
    clip_actual_graph_wait_ms: float = 0.0
    vae_actual_graph_wait_ms: float = 0.0
    prefill_actual_graph_wait_ms: float = 0.0
    useful_overlap_ms: float = 0.0
    unused_speculation: bool = False
    unet_error: str = ""
    clip_error: str = ""
    vae_error: str = ""
    prefill_error: str = ""
    prefill_lane_mode: str = ""
    prefill_total_encodes: int = 0
    prefill_skipped_encodes: int = 0
    prefill_skipped_reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        data = dict(self.__dict__)
        for key in (
            "unet_wait_ms", "clip_wait_ms", "vae_wait_ms", "prefill_wait_ms",
            "unet_work_completed_before_demand_ms",
            "clip_work_completed_before_demand_ms",
            "vae_work_completed_before_demand_ms",
            "prefill_work_completed_before_demand_ms",
            "unet_actual_graph_wait_ms",
            "clip_actual_graph_wait_ms",
            "vae_actual_graph_wait_ms",
            "prefill_actual_graph_wait_ms",
            "useful_overlap_ms",
        ):
            data[key] = round(float(data[key]), 3)
        return data


@dataclass
class RestorePreparation:
    model_key: ModelRestoreKey
    prefill_key: PrefillKey
    unet_future: Future[Any] | None = None
    clip_future: Future[Any] | None = None
    vae_future: Future[Any] | None = None
    prefill_future: Future[Any] | None = None
    diagnostics: PreparationDiagnostics = field(default_factory=PreparationDiagnostics)


class ModelPreloadCoordinator:
    """Direct coordinator for restore-time UNET/CLIP/VAE work with mutation lane."""

    def __init__(
        self,
        *,
        unet_loader: Callable[[ModelRestoreKey], Any] | None = None,
        clip_loader: Callable[[ModelRestoreKey], Any] | None = None,
        vae_loader: Callable[[ModelRestoreKey], Any] | None = None,
        prefill_loader: Callable[[PrefillKey, Any], Any] | None = None,
        max_workers: int = 2,
    ) -> None:
        self.unet_loader = unet_loader
        self.clip_loader = clip_loader
        self.vae_loader = vae_loader
        self.prefill_loader = prefill_loader
        self._max_workers = max(1, min(int(max_workers), 3))
        self._pool: ThreadPoolExecutor | None = None
        self._pool_lock = RLock()
        self._active: RestorePreparation | None = None
        self.mutation_lane = _get_mutation_lane()
        # ── Real lane counters (Phase B diagnostics) ──────────────────
        # Tracked alongside the executor without touching scheduling: the
        # pool is the only enqueue point and each submitted task runs and
        # completes exactly once, so these counters mirror the executor's
        # real queue depth / pending lane count.  A dedicated lock keeps
        # worker-thread counter updates independent of ``_pool_lock`` (so a
        # worker finalizing while ``close()`` holds ``_pool_lock`` can never
        # deadlock on pool shutdown).
        self._lane_count_lock = threading.Lock()
        self._queued_count: int = 0   # submitted but not yet picked up
        self._pending_count: int = 0  # submitted but not yet completed

    def queue_depth(self) -> int:
        """Real number of lane tasks submitted but not yet started by a worker."""
        with self._lane_count_lock:
            return self._queued_count

    def pending_lane_count(self) -> int:
        """Real number of lane tasks submitted but not yet completed."""
        with self._lane_count_lock:
            return self._pending_count

    def prepare(
        self,
        model_key: ModelRestoreKey,
        prefill_key: PrefillKey,
        *,
        exact_prefill: bool = True,
        prepare_unet: bool = True,
        prepare_clip: bool = True,
        prepare_vae: bool = True,
        trace: RuntimeTrace | None = None,
        expected_read_counts: dict[str, int] | None = None,
    ) -> RestorePreparation:
        """Start restore preparation.

        Submits UNET, CLIP, and (when requested) VAE preparation to the
        worker pool.  Physical reads and CPU‑side model construction run
        in parallel.  GPU/cache mutations are serialised through the
        coordinator-owned ``mutation_lane``.

        *expected_read_counts* — optional per-lane overrides for the
        number of ``load_torch_file`` calls predicted for that lane.
        """
        preparation = RestorePreparation(model_key=model_key, prefill_key=prefill_key)
        self._active = preparation
        _erc = expected_read_counts or {}

        if prepare_unet and self.unet_loader is not None:
            preparation.unet_future = self._submit("unet", lambda: self.unet_loader(model_key), preparation, trace,
                                                    expected_read_count=_erc.get("unet", 1))
        if prepare_clip and self.clip_loader is not None:
            preparation.clip_future = self._submit("clip", lambda: self.clip_loader(model_key), preparation, trace,
                                                    expected_read_count=_erc.get("clip", 2))
        if prepare_vae and self.vae_loader is not None and model_key.vae_identity:
            preparation.vae_future = self._submit("vae", lambda: self.vae_loader(model_key), preparation, trace,
                                                   expected_read_count=_erc.get("vae", 1))
        if exact_prefill and self.prefill_loader is not None and prefill_key.prompt_bundle_hash:
            def prefill() -> Any:
                clip = self.wait_clip(preparation, trace=trace, demand_source="prefill")
                return self.prefill_loader(prefill_key, clip)
            preparation.prefill_future = self._submit("prefill", prefill, preparation, trace,
                                                      expected_read_count=0)
        else:
            preparation.diagnostics.unused_speculation = bool(exact_prefill and self.prefill_loader is None)
        return preparation

    def extend(
        self,
        preparation: RestorePreparation,
        *,
        prepare_unet: bool = True,
        prepare_vae: bool = True,
        trace: RuntimeTrace | None = None,
    ) -> RestorePreparation:
        """Submit only missing lanes on an existing preparation.

        Never resubmits a lane whose future is already present.  The
        existing preparation (model_key, prefill_key, diagnostics, and
        any completed futures) is kept intact.  The thread pool is
        recreated on demand if it was previously closed via ``close()``.
        """
        if preparation is None:
            raise RuntimeError("cannot extend a None preparation")
        self._active = preparation
        submitted: list[str] = []

        if prepare_unet and preparation.unet_future is None and self.unet_loader is not None:
            preparation.unet_future = self._submit(
                "unet", lambda: self.unet_loader(preparation.model_key),
                preparation, trace,
                expected_read_count=1,
            )
            submitted.append("unet")
        if prepare_vae and preparation.vae_future is None and self.vae_loader is not None:
            if preparation.model_key.vae_identity:
                preparation.vae_future = self._submit(
                    "vae", lambda: self.vae_loader(preparation.model_key),
                    preparation, trace,
                    expected_read_count=1,
                )
                submitted.append("vae")

        if trace and submitted:
            trace.emit(
                "preload_extension_submitted",
                phase="restore",
                metadata={"submitted_lanes": submitted},
            )
        elif trace and not submitted:
            trace.emit(
                "preload_extension_skipped",
                phase="restore",
                metadata={"reason": "all_requested_lanes_already_present"},
            )
        return preparation

    def wait_unet(
        self,
        preparation: RestorePreparation | None = None,
        *,
        trace: RuntimeTrace | None = None,
        demand_source: str = "graph",
    ) -> Any:
        prep = preparation or self._require_active()
        return self._wait(prep, "unet", prep.unet_future, trace, demand_source=demand_source)

    def wait_clip(
        self,
        preparation: RestorePreparation | None = None,
        *,
        trace: RuntimeTrace | None = None,
        demand_source: str = "graph",
    ) -> Any:
        prep = preparation or self._require_active()
        return self._wait(prep, "clip", prep.clip_future, trace, demand_source=demand_source)

    def wait_vae(
        self,
        preparation: RestorePreparation | None = None,
        *,
        trace: RuntimeTrace | None = None,
        demand_source: str = "graph",
    ) -> Any:
        prep = preparation or self._require_active()
        return self._wait(prep, "vae", prep.vae_future, trace, demand_source=demand_source)

    def wait_prefill(self, preparation: RestorePreparation | None = None, *, trace: RuntimeTrace | None = None) -> Any:
        prep = preparation or self._require_active()
        return self._wait(prep, "prefill", prep.prefill_future, trace, demand_source="graph")

    def diagnostics(self, preparation: RestorePreparation | None = None) -> dict[str, Any]:
        return (preparation or self._require_active()).diagnostics.to_dict()

    def schedule_prefill(
        self,
        callback: Callable[[], Any],
        preparation: RestorePreparation | None = None,
        *,
        trace: RuntimeTrace | None = None,
    ) -> Future[Any] | None:
        """Schedule execution-phase prefill work.

        Public API: atomically checks whether
        ``preparation.prefill_future`` is already set and, only when None,
        submits *callback* to the worker pool (idempotent).  The critical
        section is minimised to the check-and-set so the non-reentrant
        thread-pool code path never runs while holding the lock.

        The callback typically waits for UNET and CLIP preparation futures
        before doing GPU work.  Returns the future (new or existing), or
        None when no active preparation exists.
        """
        prep = preparation or self._require_active()
        # Atomic check-and-set — lock scope is minimal, never held across
        # the *submit* call (which itself may try to reacquire the lock
        # via _ensure_pool).
        with self._pool_lock:
            if prep.prefill_future is not None:
                return prep.prefill_future
            prep.prefill_future = self._submit(
                "execution_prefill", callback, prep, trace,
                phase="execution", expected_read_count=0,
            )
            return prep.prefill_future

    def schedule_vae_activation(
        self,
        callback: Callable[[], Any],
        preparation: RestorePreparation | None = None,
        *,
        trace: RuntimeTrace | None = None,
    ) -> Future[Any] | None:
        """Schedule execution-phase VAE activation work (single-flight).

        Public API: atomically checks whether
        ``preparation.vae_future`` is already set and, only when None,
        submits *callback* to the worker pool (idempotent).  The critical
        section is minimised to the check-and-set so the non-reentrant
        thread-pool code path never runs while holding the lock.  No second
        mutation lock/framework is introduced — the callback performs its
        GPU/cache mutation through the existing shared ``mutation_lane``
        (acquired by the existing ``load_models_gpu`` wrapper as owner
        ``VAE`` around the actual load).  The callback typically performs
        the VAE GPU/cache activation.  Returns the future (new or
        existing), or None when no active preparation exists.
        """
        prep = preparation or self._require_active()
        with self._pool_lock:
            if prep.vae_future is not None:
                return prep.vae_future
            prep.vae_future = self._submit(
                "vae", callback, prep, trace,
                phase="execution", expected_read_count=0,
            )
            return prep.vae_future

    def pool_threads_info(self) -> list[dict[str, Any]]:
        """Return list of {native_id, name} for each live pool thread."""
        result: list[dict[str, Any]] = []
        try:
            with self._pool_lock:
                pool = self._pool
            if pool is not None:
                ts = getattr(pool, "_threads", None)
                if ts is not None:
                    for t in list(ts):
                        try:
                            result.append({
                                "native_id": t.native_id,
                                "name": str(t.name)[:40],
                            })
                        except Exception:
                            pass
        except Exception:
            pass
        return result

    def close(self) -> None:
        with self._pool_lock:
            pool = self._pool
            self._pool = None
        if pool is not None:
            pool.shutdown(wait=True, cancel_futures=False)
        # All submitted tasks are terminal after shutdown(wait=True): reset
        # the real lane counters so a later pool recreation starts clean.
        with self._lane_count_lock:
            self._queued_count = 0
            self._pending_count = 0

    def _ensure_pool(self) -> ThreadPoolExecutor:
        with self._pool_lock:
            if self._pool is None:
                self._pool = ThreadPoolExecutor(
                    max_workers=self._max_workers,
                    thread_name_prefix="comfymodal-restore",
                )
            return self._pool

    def _submit(
        self,
        name: str,
        callback: Callable[[], Any],
        preparation: RestorePreparation,
        trace: RuntimeTrace | None,
        *,
        phase: str = "restore",
        diag_name: str | None = None,
        expected_read_count: int = 1,
        submission_id: str = "",
    ) -> Future[Any]:
        # Normalise diagnostic attribute namespace so execution-preﬁll work
        # uses the static *preﬁll_started_at/completed_at/error* ﬁelds.
        effective_diag = diag_name or name
        if effective_diag == "execution_prefill":
            effective_diag = "prefill"

        # Generate submission identity used in both pre- and post-pool events.
        sid = submission_id or _next_submission_id()

        # Build canonical lane trace (additive — existing events unchanged).
        canonical_lane = _LANE_TO_CANONICAL.get(name, name.upper())
        lane_trace: ModelLaneTrace | None = None
        if trace:
            # Real coordinator state at submission (before this task joins
            # the queue) — read-only, never alters scheduling.
            _queue_depth_at_submit = self.queue_depth()
            _pending_at_submit = self.pending_lane_count()
            trace.emit(
                "preload_submitted",
                phase=phase,
                metadata={
                    "lane": name,
                    "submission_id": sid,
                    "queue_depth": _queue_depth_at_submit,
                    "pending_lane_count": _pending_at_submit,
                },
            )
            lane_trace = ModelLaneTrace(
                trace, canonical_lane, phase=phase,
                expected_read_count=expected_read_count,
            )
            lane_trace.submitted()

        # Capture monotonic clock just before pool handoff for queue delay.
        _submit_started_ns = time.monotonic_ns()

        # Track the task in the real lane counters (the pool is the only
        # enqueue point).  Queue/pending decrements happen in run().
        with self._lane_count_lock:
            self._queued_count += 1
            self._pending_count += 1

        def run() -> Any:
            nonlocal callback
            started = time.time()
            _queue_wait_ms = round((time.monotonic_ns() - _submit_started_ns) / 1_000_000, 3)
            setattr(preparation.diagnostics, f"{effective_diag}_started_at", started)
            # ── Real coordinator state at worker start (this task has been
            # picked up, so the queue no longer counts it) ────────────
            with self._lane_count_lock:
                self._queued_count = max(0, self._queued_count - 1)
                _queue_depth_at_worker = self._queued_count
                _pending_at_worker = self._pending_count
            # ── Activate per-worker lane context ────────────────
            ctx_token = None
            if lane_trace is not None:
                ctx_token = _ACTIVE_LANE_TRACE.set(lane_trace)
            try:
                if trace:
                    trace.emit(f"{name}_prepare_start", phase=phase)
                    trace.emit(
                        "preload_worker_started",
                        phase=phase,
                        metadata={
                            "lane": name,
                            "submission_id": sid,
                            "queue_wait_ms": _queue_wait_ms,
                            "queue_depth": _queue_depth_at_worker,
                            "pending_lane_count": _pending_at_worker,
                        },
                    )
                # Install core dispatch wrappers (idempotent per-component,
                # resolves live sys.modules so partial comfy imports cannot
                # block the read wrapper).
                # Skip for execution prefill — wrappers already installed
                # during restore (model-loading lanes).
                if effective_diag != 'prefill':
                    _ensure_core_wrappers(trace=trace)
                # Install UNET post-read decomposition wrappers (Section B).
                # Only active when _ACTIVE_LANE_TRACE is UNET; absent
                # symbols are skipped without breaking loading.
                # UNET-only — execution prefill does not need these.
                if effective_diag == 'unet':
                    _ensure_unet_decompose_wrappers(trace=trace)

                try:
                    result = callback()
                finally:
                    callback = None
                completed = time.time()
                setattr(preparation.diagnostics, f"{effective_diag}_completed_at", completed)
                if trace:
                    trace.emit(f"{name}_prepare_end", phase=phase)
                    trace.emit(
                        "preload_worker_finished",
                        phase=phase,
                        metadata={
                            "lane": name,
                            "worker_duration_ms": round((completed - started) * 1000, 3),
                        },
                    )
                # ── Terminal event (success) ────────────────────
                _worker_dur_ms = round((completed - started) * 1000, 3)
                if lane_trace is not None:
                    lane_trace.ready(
                        worker_duration_ms=_worker_dur_ms,
                    )
                return result
            except Exception as exc:
                completed = time.time()
                setattr(preparation.diagnostics, f"{effective_diag}_error", str(exc))
                setattr(preparation.diagnostics, f"{effective_diag}_completed_at", completed)
                if trace:
                    trace.emit(f"{name}_prepare_end", phase=phase, metadata={"error": str(exc)[:200]})
                    trace.emit(
                        "preload_worker_failed",
                        phase=phase,
                        metadata={
                            "lane": name,
                            "error_category": type(exc).__name__,
                            "worker_duration_ms": round((completed - started) * 1000, 3),
                        },
                    )
                # ── Terminal event (failure) ────────────────────
                _fail_dur_ms = round((completed - started) * 1000, 3)
                if lane_trace is not None:
                    lane_trace.failed(
                        error_category=type(exc).__name__,
                        worker_duration_ms=_fail_dur_ms,
                    )
                raise
            finally:
                if ctx_token is not None:
                    _ACTIVE_LANE_TRACE.reset(ctx_token)
                # Task is terminal: drop it from the real pending count.
                # Uses the dedicated lane-count lock (never ``_pool_lock``)
                # so this can never block pool shutdown in ``close()``.
                with self._lane_count_lock:
                    self._pending_count = max(0, self._pending_count - 1)
        try:
            return self._ensure_pool().submit(run)
        except Exception:
            # The task never reached the pool: release its lane counters.
            with self._lane_count_lock:
                self._queued_count = max(0, self._queued_count - 1)
                self._pending_count = max(0, self._pending_count - 1)
            raise

    def _wait(
        self,
        preparation: RestorePreparation,
        name: str,
        future: Future[Any] | None,
        trace: RuntimeTrace | None,
        *,
        demand_source: str = "graph",
    ) -> Any:
        demanded = time.time()
        if demand_source == "graph":
            setattr(preparation.diagnostics, f"{name}_demanded_at", demanded)
        if future is None:
            return None
        wait_started = time.time()
        wait_phase = "execution" if demand_source in {"graph", "execution_prefill"} else "restore"
        if trace:
            trace.emit(
                f"{name}_wait_start",
                phase=wait_phase,
                metadata={"demand_source": demand_source},
            )
        result = future.result()
        completed = getattr(preparation.diagnostics, f"{name}_completed_at")
        wait_ms = max(0.0, (time.time() - wait_started) * 1000.0)
        completed_before_demand_ms = max(0.0, (demanded - completed) * 1000.0)
        setattr(preparation.diagnostics, f"{name}_wait_ms", wait_ms)
        if demand_source == "graph":
            setattr(preparation.diagnostics, f"{name}_actual_graph_wait_ms", wait_ms)
            setattr(
                preparation.diagnostics,
                f"{name}_work_completed_before_demand_ms",
                completed_before_demand_ms,
            )
        if trace:
            trace.emit(
                f"{name}_wait_end",
                phase=wait_phase,
                metadata={
                    "demand_source": demand_source,
                    "wait_ms": round(wait_ms, 3),
                    "completed_before_demand_ms": round(completed_before_demand_ms, 3),
                },
            )
        if name == "unet":
            clip_start = preparation.diagnostics.clip_started_at
            if clip_start and preparation.diagnostics.unet_completed_at:
                preparation.diagnostics.useful_overlap_ms = max(0.0, (preparation.diagnostics.unet_completed_at - clip_start) * 1000.0)
        return result

    def _require_active(self) -> RestorePreparation:
        if self._active is None:
            raise RuntimeError("no active restore preparation")
        return self._active


_ACTIVE_V2_LOADER_BRIDGE: ContextVar["V2LoaderBridge | None"] = ContextVar(
    "comfymodal_active_v2_loader_bridge",
    default=None,
)
_LOADER_MISS = object()


def current_v2_loader_bridge() -> "V2LoaderBridge | None":
    """Return the bridge active for the current graph-execution context."""
    return _ACTIVE_V2_LOADER_BRIDGE.get()


class V2LoaderBridge:
    """Connect restore preparation to ComfyUI's real loader node methods.

    The bridge wraps the already-loaded node classes instead of replacing
    ComfyUI's loader implementation. A matching prepared result is returned;
    every mismatch, missing plan, or failed future falls through to the
    original loader. The context variable isolates v2 from legacy requests.
    """

    _NODE_METHODS = {
        "UNETLoader": "load_unet",
        "CLIPLoader": "load_clip",
        "DualCLIPLoader": "load_clip",
        "VAELoader": "load_vae",
        "CLIPTextEncode": "encode",
        "VAEDecode": "decode",
    }

    def __init__(self, max_workers: int = 3) -> None:
        self.coordinator = ModelPreloadCoordinator(
            unet_loader=self._load_unet,
            clip_loader=self._load_clip,
            vae_loader=self._load_vae,
            prefill_loader=self._prefill,
            max_workers=max_workers,
        )
        self._nodes: Any | None = None
        self._original_methods: dict[str, Callable[..., Any]] = {}
        self._node_classes: dict[str, Any] = {}
        self._model_key: ModelRestoreKey | None = None
        self._prefill_key: PrefillKey | None = None
        self._model_spec: Mapping[str, Any] = {}
        self._workflow_hash: str = ""
        """Compiled workflow hash captured from the restore plan (exact key
        input for the CLIP conditioning cache)."""
        self._production_options_hash: str = ""
        """Effective production-options hash captured from the restore plan
        (exact key input covering production preset bindings)."""
        self._preparation: RestorePreparation | None = None
        self._trace: RuntimeTrace | None = None
        self._preparation_trace: RuntimeTrace | None = None
        """Snapshot of the trace at ``prepare()`` return for late event drain."""
        self._preparation_event_cursor: int = 0
        """Number of events on ``_preparation_trace`` when ``prepare()`` returned."""
        self._prefill_results: dict[tuple[int, str], Any] = {}
        self._prefill_lock = RLock()
        self._reconciliation_emitted: bool = False
        """True once ``clip_prefill_reconciliation`` has been emitted for the
        current preparation/request (one record per request)."""
        # ── VAE early activation (sampling_end mode) resolution sources ──
        self._exact_vae: Any | None = None
        """Future exact VAE object accepted via ``set_exact_vae()``
        (snapshot/seed-compatible branch).  Takes precedence in
        ``resolve_vae_object``."""
        self._graph_vae_output: Any | None = None
        """Captured graph VAELoader output (first VAELoader result served by
        this bridge for the current request), used as an exact-object source
        in ``resolve_vae_object``.  Reset per ``prepare()``/``clear()``."""
        self._snapshot_loader_outputs: Mapping[str, Any] | None = None

    def install(self, nodes_module: Any | None = None, *, trace: RuntimeTrace | None = None) -> bool:
        """Install wrappers on the live ComfyUI node classes once.

        Also triggers global core dispatch wrapper installation
        (``comfy.utils.load_torch_file`` and
        ``comfy.model_management.load_models_gpu``) because
        ``nodes.py`` has already imported these modules at startup,
        making them resolvable via ``sys.modules``.
        """
        if nodes_module is None:
            import nodes as nodes_module  # type: ignore[no-redef]
        mappings = getattr(nodes_module, "NODE_CLASS_MAPPINGS", {})
        if not isinstance(mappings, Mapping):
            return False
        self._nodes = nodes_module
        # Live comfy modules are already in sys.modules (loaded by nodes.py).
        # Install wrappers here rather than relying on a fresh import which
        # can fail on optional dependencies (e.g. comfy_aimdo).
        _ensure_core_wrappers(trace=trace)
        installed = False
        for class_name, method_name in self._NODE_METHODS.items():
            node_class = mappings.get(class_name)
            method = getattr(node_class, method_name, None) if node_class else None
            if not callable(method):
                continue
            key = f"{class_name}.{method_name}"
            self._node_classes[class_name] = node_class
            if getattr(method, "_comfy_modal_v2_loader_bridge", False):
                original = getattr(method, "_comfy_modal_v2_original", None)
                if callable(original):
                    self._original_methods[key] = original
                continue
            self._original_methods[key] = method
            wrapper = self._make_wrapper(class_name, method_name, method)
            setattr(wrapper, "_comfy_modal_v2_loader_bridge", True)
            setattr(wrapper, "_comfy_modal_v2_original", method)
            setattr(node_class, method_name, wrapper)
            installed = True
        return installed or bool(self._original_methods)

    def prepare(
        self,
        plan: Any,
        *,
        trace: RuntimeTrace | None = None,
        prepare_unet: bool | None = None,
        prepare_clip: bool | None = None,
        prepare_vae: bool | None = None,
    ) -> RestorePreparation | None:
        """Start actual restore-time UNET/CLIP work for one RestorePlan.

        *prepare_unet* / *prepare_clip* / *prepare_vae* — optional per-lane
        overrides.  When ``None`` the value is derived from the plan's model
        key (current behaviour).  Pass ``False`` to skip a lane so the
        original (patched) loader handles it at graph time (e.g. V1-style
        background UNET future).
        """
        self._model_key = plan.model_key
        self._prefill_key = plan.prefill_key
        self._model_spec = plan.model_spec if isinstance(plan.model_spec, Mapping) else {}
        self._workflow_hash = str(
            getattr(plan, "workflow_hash", "") or getattr(plan, "source_workflow_hash", "") or ""
        )
        _exec_options = getattr(plan, "execution_options", None)
        if _exec_options is not None and hasattr(_exec_options, "to_dict"):
            try:
                self._production_options_hash = stable_hash(_exec_options.to_dict())
            except Exception:
                self._production_options_hash = ""
        else:
            self._production_options_hash = ""
        self._trace = trace
        with self._prefill_lock:
            self._prefill_results.clear()
        self._reconciliation_emitted = False
        self._preparation = None
        self._exact_vae = None
        self._snapshot_loader_outputs = None
        # Reset the per-request captured graph VAELoader output so a fresh
        # request never reuses a previous request's captured VAE object.
        self._graph_vae_output = None
        if not self._model_key or not (
            self._model_key.unet_identity or self._model_key.clip_identity
        ):
            if trace:
                trace.emit("preload_schedule_end", phase="restore", metadata={"status": "no_model_key"})
            return None
        self.install(self._nodes, trace=trace)
        # NOTE: when prepare_unet is False (V2 CLIP-only fast path), UNET is
        # owned entirely by the production background cache published during
        # restore.  The V2LoaderBridge intentionally does NOT prepare UNET
        # here; a bridge miss at graph time is expected and non-fatal — the
        # original (patched) loader handles it via _start_production_restore_unet
        # and _cached_unet_load.  See modal_app.py restore() for the fast-path
        # handoff that sets prepare_unet=False.
        prepare_unet = self._resolve_lane_override(
            prepare_unet,
            bool(self._model_key.unet_identity and self._request_list("unet")),
        )
        prepare_clip = self._resolve_lane_override(
            prepare_clip,
            bool(self._model_key.clip_identity and self._request_list("clip")),
        )
        # Restore schedules only UNET and CLIP preparation.  CLIPTextEncode
        # (prefill) is deferred to execution-phase single-flight via
        # schedule_execution_prefill() called after graph_execution_start.
        exact_prefill = False
        if trace:
            trace.emit(
                "preload_schedule_start",
                phase="restore",
                metadata={
                    "unet_identity": self._model_key.unet_identity,
                    "clip_identity": self._model_key.clip_identity,
                    "exact_prefill": exact_prefill,
                    "prefill_deferred_to_execution": True,
                    "prepare_unet": prepare_unet,
                    "prepare_clip": prepare_clip,
                    "prepare_vae": prepare_vae,
                },
            )
        # Derive exact expected read counts from the actual model requests.
        _erc: dict[str, int] = {}
        _erc["unet"] = 1
        _erc["clip"] = self._compute_clip_expected_read_count()
        _erc["vae"] = 1 if self._model_key.vae_identity else 0
        if vae_activation_mode() == _VAE_ACTIVATION_MODE_SAMPLING_END:
            # sampling_end mode: restore/preparation must NOT submit a VAE
            # future.  The VAE GPU activation is scheduled exactly once at
            # the real SAMPLER_SAMPLE sampling_end boundary via
            # schedule_vae_early_activation_at_sampling_end(); the original
            # (patched) graph VAELoader remains the unchanged late fallback.
            prepare_vae = False
        else:
            prepare_vae = self._resolve_lane_override(
                prepare_vae,
                bool(self._model_key.vae_identity and self._request_list("vae")),
            )

        self._preparation = self.coordinator.prepare(
            self._model_key,
            self._prefill_key or PrefillKey(model_key=self._model_key),
            exact_prefill=exact_prefill,
            prepare_unet=prepare_unet,
            prepare_clip=prepare_clip,
            prepare_vae=prepare_vae,
            trace=trace,
            expected_read_counts=_erc,
        )
        if trace:
            trace.emit(
                "preload_schedule_end",
                phase="restore",
                metadata={
                    "status": "started",
                    "unet_future": bool(self._preparation.unet_future),
                    "clip_future": bool(self._preparation.clip_future),
                    "vae_future": bool(self._preparation.vae_future),
                    "prefill_future": bool(self._preparation.prefill_future),
                    "prefill_deferred_to_execution": True,
                },
            )
        # Record trace cursor after all synchronous prepare() events so
        # late worker events (read/cpu/gpu/ready) can be drained into the
        # execution trace without duplicating the restore prefix.
        if trace is not None:
            self._preparation_trace = trace
            self._preparation_event_cursor = len(trace.events)
        return self._preparation

    @contextmanager
    def request_scope(self) -> Iterator[None]:
        """Make this bridge visible only while the v2 graph is executing."""
        token = _ACTIVE_V2_LOADER_BRIDGE.set(self)
        try:
            yield
        finally:
            _ACTIVE_V2_LOADER_BRIDGE.reset(token)

    def diagnostics(self) -> dict[str, Any]:
        if self._preparation is None:
            return {}
        return self.coordinator.diagnostics(self._preparation)

    def diagnostic_snapshot(self) -> dict[str, Any]:
        """Return a read-only diagnostic snapshot of the bridge's current state.

        Returns exactly the documented keys with no extras.  Never raises,
        never logs, never blocks on future results/exceptions/wait, and
        never returns full model keys, paths, or repr identities.
        """
        # Acquire bridge lock once, copy references/scalars, release quickly.
        prep = model_key = prefill_key = coordinator = None
        try:
            with self._prefill_lock:
                prep = self._preparation
                model_key = self._model_key
                prefill_key = self._prefill_key
                coordinator = self.coordinator
        except Exception:
            pass

        # Bridge identity
        bridge_object_id = str(id(self))

        # Preparation exists
        current_preparation_exists = prep is not None

        # Key hashes — compact stable hashes via canonical helper, None when absent.
        try:
            model_key_hash = (
                model_key.stable_hash if model_key is not None else None
            )
            current_model_key_hash = model_key_hash if isinstance(model_key_hash, str) else None
        except Exception:
            current_model_key_hash = None

        try:
            prefill_key_hash = (
                prefill_key.stable_hash if prefill_key is not None else None
            )
            current_prefill_key_hash = prefill_key_hash if isinstance(prefill_key_hash, str) else None
        except Exception:
            current_prefill_key_hash = None

        # ── Future status helper (read-only, no result/exception/wait/cancel) ──
        def _future_status(
            future: Any,
        ) -> tuple[bool, bool | None, bool | None, bool | None]:
            if future is None:
                return (False, None, None, None)
            f_exists = True
            f_done: bool | None = None
            f_running: bool | None = None
            f_cancelled: bool | None = None
            try:
                status = future.done()
                f_done = status if isinstance(status, bool) else None
            except Exception:
                f_done = None
            try:
                status = future.running()
                f_running = status if isinstance(status, bool) else None
            except Exception:
                f_running = None
            try:
                status = future.cancelled()
                f_cancelled = status if isinstance(status, bool) else None
            except Exception:
                f_cancelled = None
            return (f_exists, f_done, f_running, f_cancelled)

        if prep is not None:
            # Access future fields safely — prep may not be a real
            # RestorePreparation (e.g. in corrupt-state scenarios).
            try:
                unet_future = prep.unet_future  # type: ignore[union-attr]
            except Exception:
                unet_future = _LOADER_MISS
            try:
                clip_future = prep.clip_future  # type: ignore[union-attr]
            except Exception:
                clip_future = _LOADER_MISS
            try:
                prefill_future = prep.prefill_future  # type: ignore[union-attr]
            except Exception:
                prefill_future = _LOADER_MISS

            unet_exists, unet_done, unet_running, unet_cancelled = _future_status(
                unet_future if unet_future is not _LOADER_MISS else None
            )
            clip_exists, clip_done, clip_running, clip_cancelled = _future_status(
                clip_future if clip_future is not _LOADER_MISS else None
            )
            prefill_exists, prefill_done, prefill_running, prefill_cancelled = _future_status(
                prefill_future if prefill_future is not _LOADER_MISS else None
            )
        else:
            unet_exists = clip_exists = prefill_exists = False
            unet_done = unet_running = unet_cancelled = None
            clip_done = clip_running = clip_cancelled = None
            prefill_done = prefill_running = prefill_cancelled = None

        # ── Executor state (read-only, via coordinator lock) ─────────────────
        pool = None
        executor_exists: bool | None = None
        try:
            with coordinator._pool_lock:
                pool = coordinator._pool
            executor_exists = pool is not None
        except Exception:
            pass

        if pool is not None:
            try:
                executor_threads = getattr(pool, "_threads")
                executor_thread_count = len(executor_threads)
            except Exception:
                executor_thread_count = None
            try:
                executor_work_queue_size = int(pool._work_queue.qsize())
            except Exception:
                # queue.SimpleQueue has no qsize(); fall back to the real
                # coordinator-tracked queue depth (submitted-not-started).
                executor_work_queue_size = None
                try:
                    if coordinator is not None:
                        executor_work_queue_size = coordinator.queue_depth()
                except Exception:
                    pass
        else:
            executor_thread_count = None
            executor_work_queue_size = None

        # Pending lane count — real tracked count (submitted-not-completed).
        pending_lane_count: int | None = None
        try:
            if coordinator is not None:
                pending_lane_count = coordinator.pending_lane_count()
        except Exception:
            pass

        # Pool threads info from coordinator
        pool_threads = []
        try:
            if coordinator is not None:
                pool_threads = coordinator.pool_threads_info()
        except Exception:
            pass

        return {
            "bridge_object_id": bridge_object_id,
            "current_preparation_exists": current_preparation_exists,
            "current_model_key_hash": current_model_key_hash,
            "current_prefill_key_hash": current_prefill_key_hash,
            "unet_future_exists": unet_exists,
            "unet_future_done": unet_done,
            "unet_future_running": unet_running,
            "unet_future_cancelled": unet_cancelled,
            "clip_future_exists": clip_exists,
            "clip_future_done": clip_done,
            "clip_future_running": clip_running,
            "clip_future_cancelled": clip_cancelled,
            "prefill_future_exists": prefill_exists,
            "prefill_future_done": prefill_done,
            "prefill_future_running": prefill_running,
            "prefill_future_cancelled": prefill_cancelled,
            "executor_exists": executor_exists,
            "executor_thread_count": executor_thread_count,
            "executor_work_queue_size": executor_work_queue_size,
            "pool_threads": pool_threads,
            "pending_lane_count": pending_lane_count,
        }

    def schedule_execution_prefill(
        self,
        *,
        trace: RuntimeTrace | None = None,
        request_id: str = "",
        activation_diagnostic_state: dict[str, Any] | None = None,
    ) -> bool:
        """Schedule execution-phase CLIP prefill single-flight.

        Called after ``graph_execution_start`` in ``_run_in_process``.

        **V2 prefill overlap (default):** waits for the CLIP preparation
        future only, then begins encoding *without* waiting for UNET.
        The UNET restore runs in parallel and its GPU commit is serialised
        through the mutation lane — safe because ``load_models_gpu``
        acquires the lane before touching GPU memory.  This removes
        ~5.7–6.3 s of Qwen-encode from the critical path on cold starts.

        **Legacy barrier (env ``COMFYMODAL_V2_PREFILL_WAIT_FOR_UNET=1``):**
        waits for UNET first (old behaviour), putting the encode on the
        critical path behind UNET.

        Idempotent: subsequent calls are no-ops when
        ``preparation.prefill_future`` is already set.

        Returns True when prefill was scheduled (or was already scheduled),
        False when skipped (lane ``none``, missing preparation, or no
        eligible entries).

        Lane mode (``COMFYMODAL_V2_PREFILL_LANES``):
          * ``critical`` (default): only role=positive/negative entries
          * ``all``: all non-empty-text entries
          * ``none``: hard disable — skip scheduling entirely

        On missing/ineligible plan, no CLIP, failed future, or no matching
        cached result, the graph falls back to the original CLIPTextEncode
        via ``_consume_prefill`` returning ``_LOADER_MISS``.
        """
        lane_mode = _PREFILL_LANE_MODE
        if lane_mode == "none":
            if trace:
                trace.emit("execution_prefill_skip", phase="execution",
                           metadata={"reason": "lane_mode=none"})
            return False

        prep = self._preparation
        if prep is None or self._prefill_key is None:
            if trace:
                trace.emit("execution_prefill_skip", phase="execution",
                           metadata={"reason": "missing_preparation"})
            return False

        if prep.prefill_future is not None:
            if trace:
                trace.emit("execution_prefill_skip", phase="execution",
                           metadata={"reason": "already_scheduled"})
            return True  # already scheduled (from restore or earlier call)

        if not self._prefill_key.prompt_bundle_hash:
            if trace:
                trace.emit("execution_prefill_skip", phase="execution",
                           metadata={"reason": "no_prompt_bundle_hash"})
            return False

        options = self._prefill_key.encode_options
        entries = options.get("encodes", []) if isinstance(options, Mapping) else []
        filtered, skipped_count, skipped_reasons = self._filter_prefill_entries(
            entries, lane_mode
        )

        if not filtered:
            if trace:
                trace.emit("execution_prefill_skip", phase="execution",
                           metadata={"reason": "no_eligible_entries",
                                     "total": len(entries),
                                     "skipped": skipped_count})
            return False

        wait_for_unet = _V2_PREFILL_WAIT_FOR_UNET

        if trace:
            trace.emit("execution_prefill_scheduled", phase="execution",
                       metadata={"filtered_entries": len(filtered),
                                 "total_entries": len(entries),
                                 "lane_mode": lane_mode,
                                 "skipped": skipped_count,
                                 "wait_for_unet": wait_for_unet,
                                 "unet_future_exists": prep.unet_future is not None})

        _request_id = str(
            request_id
            or (trace.request_id if trace is not None else "")
        )
        _worker_state = activation_diagnostic_state
        if _worker_state is None:
            _worker_state = {
                "request_id": _request_id,
                "clip_encode_calls": [],
            }

        def _execution_prefill() -> dict[tuple[int, str], Any] | None:
            """Internal prefill callback — runs in coordinator's worker pool.

            V2 prefill overlap (default): waits for CLIP only, begins
            encoding without blocking on UNET.  Legacy barrier
            (``COMFYMODAL_V2_PREFILL_WAIT_FOR_UNET=1``): waits for UNET
            first (old behaviour).  Populates _prefill_results so graph
            nodes consume them.
            """
            nonlocal wait_for_unet
            if trace:
                trace.emit(_EVENT_WORKER_START, phase="execution",
                           metadata={"lane_mode": lane_mode,
                                     "total_entries": len(entries),
                                     "filtered": len(filtered),
                                     "wait_for_unet": wait_for_unet,
                                     "unet_future_exists": prep.unet_future is not None,
                                     "counters": _capture_phase_counters()})
            # ── Phase B: model-readiness (future/model wait) ────────
            # Snapshot BEFORE the first future wait so readiness_ms spans
            # every pre-encode wait (UNET barrier + CLIP) contiguously.
            _readiness_start = _capture_phase_counters()
            if trace:
                trace.emit(_EVENT_READINESS_START, phase="execution",
                           metadata={"counters": _readiness_start,
                                     "wait_for_unet": wait_for_unet})
            # ── Legacy barrier: wait for UNET before CLIP ──────────
            if wait_for_unet:
                try:
                    if prep.unet_future is not None:
                        self.coordinator.wait_unet(
                            prep,
                            trace=trace,
                            demand_source="execution_prefill",
                        )
                except Exception as exc:
                    if trace:
                        trace.emit(_EVENT_FAILED, phase="execution",
                                   metadata={"error": str(exc)[:200],
                                              "phase": "wait_unet"})
                    return None
            # ── Wait for CLIP ──────────────────────────────────────
            # In default mode this is the only pre-encode wait.
            # In legacy mode UNET has already resolved above.
            try:
                clip = self.coordinator.wait_clip(
                    prep, trace=trace, demand_source="execution_prefill"
                )
            except Exception as exc:
                if trace:
                    trace.emit(_EVENT_FAILED, phase="execution",
                               metadata={"error": str(exc)[:200],
                                          "phase": "wait_clip"})
                return None
            if clip is None:
                if trace:
                    trace.emit(_EVENT_FAILED, phase="execution",
                               metadata={"reason": "no_clip"})
                return None
            _readiness_end = _capture_phase_counters()
            if trace:
                trace.emit(_EVENT_READINESS_END, phase="execution",
                           metadata={"counters": _readiness_end,
                                     "wait_for_unet": wait_for_unet})

            # ── UNET status when prefill is about to start encoding ──
            # Record whether UNET was skipped (no future), pending
            # (future not yet resolved), or already completed — useful
            # for diagnosing overlap in cold-trace analysis.
            if not wait_for_unet:
                unet_skipped = prep.unet_future is None
                unet_pending = (
                    not unet_skipped and not prep.unet_future.done()
                ) if prep.unet_future is not None else False
                if trace:
                    trace.emit("execution_prefill_unet_status",
                               phase="execution",
                               metadata={
                                   "wait_for_unet": False,
                                   "unet_skipped": unet_skipped,
                                   "unet_pending": unet_pending,
                                   "unet_resolved": not unet_skipped and not unet_pending,
                               })

            # ── Phase B: synchronous native page-readiness (candidate) ──
            # Immediately after the CLIP future/readiness wait and directly
            # before the encode loop.  Gated by
            # COMFYMODAL_V2_PAGE_READINESS_MODE=willneed (off by
            # default); no-op otherwise.  Synchronous, never schedules a
            # future, never re-encodes.  Its duration is attributed as an
            # explicit ``page_readiness`` stage in the reconciliation
            # record — never shifted into restore, CLIP future wait, UNET
            # load, sampler wait, or residual.
            _run_clip_page_readiness(clip, trace=trace, request_id=_request_id)

            # ── Phase 1A candidate: early retained-UNET activation ──
            # Hooked at the established real execution-prefill CLIP callback
            # boundary — immediately before the actual prefill encode (never
            # request entry / tokenization / graph fallback / dummy encode).
            # Mode "clip_encode_start" schedules the retained UNET GPU
            # activation once through the coordinator pool; "clip_gpu_ready"
            # instead ARMS a request-scoped single-use trigger that is fired
            # by the GPU loader wrapper hook after the first qualifying
            # successful CLIP load_models_gpu call from the real prefill
            # encode returns and the mutation lane is released; "late"
            # (default) is a no-op that preserves Phase 0 behavior.
            # ── Exact CLIP conditioning cache (opt-in) ──────────────
            # An exact hit serves the completed CPU conditioning directly:
            # zero CLIP GPU loads and zero CLIP encodes.  Because no CLIP
            # encode runs, the retained-UNET activation is scheduled through
            # the existing shared scheduling core with
            # trigger=conditioning_cache_hit instead of waiting for a
            # clip_encode_start/clip_gpu_ready fire event that will not
            # happen.  Every cache failure is a miss (unchanged encode).
            _cc_cache_svc = get_exact_conditioning_cache()
            _cc_miss_entries: list[dict[str, Any]] = list(filtered)
            _cc_hit_results: dict[tuple[int, str], Any] = {}
            _cc_exact_hit = False
            _cc_ctx: dict[str, Any] = {}
            _cc_key_info: dict[str, Any] = {
                "key_hash": "absent",
                "identity_status": "invalid",
                "schema_version": 0,
                "validation_scope": "",
                "missing": "",
            }
            if _cc_cache_svc is not None:
                _cc_ctx = _build_clip_conditioning_cache_context(
                    self, clip=clip, trace=trace, request_id=_request_id,
                )
                _cc_key_info = conditioning_cache_key_summary(_cc_ctx, filtered)
                _cc_hits, _cc_miss_entries, _cc_hit_count, _cc_miss_count = (
                    _cc_cache_svc.lookup_many(_cc_ctx, filtered)
                )
                if trace:
                    trace.emit(
                        "clip_conditioning_cache_lookup",
                        phase="execution",
                        metadata={
                            "hit_count": _cc_hit_count,
                            "miss_count": _cc_miss_count,
                            "entry_count": len(filtered),
                        },
                    )
                for _cc_index, _cc_value in _cc_hits.items():
                    _cc_text = str(filtered[_cc_index].get("text", ""))
                    _cc_hit_results[(id(clip), _cc_text)] = _cc_value
                _cc_exact_hit = bool(filtered) and _cc_miss_count == 0
                if _cc_exact_hit:
                    _schedule_unet_activation_conditioning_cache_hit(
                        self,
                        trace=trace,
                        request_id=_request_id,
                        clip=clip,
                        encode_entries=filtered,
                    )
                    log_conditioning_cache_decision(
                        "exact_hit", key_hash=_cc_key_info["key_hash"],
                        identity_status=_cc_key_info["identity_status"],
                        encode_calls=0,
                        schema_version=_cc_key_info["schema_version"],
                        validation_scope=_cc_key_info["validation_scope"],
                        entries=len(filtered),
                        request_id=_request_id or "absent",
                    )
                    if trace:
                        trace.emit(
                            "clip_conditioning_cache_decision",
                            phase="execution",
                            metadata={
                                "decision": "exact_hit",
                                "key_hash": _cc_key_info["key_hash"],
                                "identity_status": _cc_key_info["identity_status"],
                                "schema_version": _cc_key_info["schema_version"],
                                "validation_scope": _cc_key_info["validation_scope"],
                                "encode_calls": 0,
                                "entry_count": len(filtered),
                            },
                        )
            # The existing activation hooks run only when the encode loop
            # will actually run (miss or partial).  On an exact hit the
            # activation was already scheduled above with
            # trigger=conditioning_cache_hit.
            if not _cc_exact_hit:
                if unet_activation_mode() == _UNET_ACTIVATION_MODE_CLIP_GPU_READY:
                    _armed = _unet_activation_arm(
                        self,
                        trace=trace,
                        request_id=_request_id,
                        clip=clip,
                        encode_entries=_cc_miss_entries or filtered,
                    )
                    if _armed:
                        _clip_patcher = _resolve_clip_patcher(clip)
                        if _clip_patcher is not None:
                            try:
                                _mm_load_models_gpu(
                                    [_clip_patcher], force_full_load=True,
                                )
                            except Exception as _exc:
                                if trace is not None:
                                    trace.emit(
                                        "clip_gpu_ready_force_load_error",
                                        phase="execution",
                                        metadata={
                                            "request_id": _request_id,
                                            "error": str(_exc)[:200],
                                        },
                                    )
                else:
                    clip_encode_start(
                        self,
                        trace=trace,
                        request_id=_request_id,
                        clip=clip,
                        encode_entries=_cc_miss_entries or filtered,
                    )

            # ── Phase B: actual encode (wall / thread / process CPU) ──
            _encode_start = _capture_phase_counters()
            results: dict[tuple[int, str], Any] = dict(_cc_hit_results)
            _cc_stored = 0
            _cc_encode_calls = 0
            if not _cc_exact_hit:
                record_clip_encode_start(_request_id, _encode_start)
                if trace:
                    trace.emit(_EVENT_ENCODE_START, phase="execution",
                               metadata={"counters": _encode_start,
                                         "filtered_entries": len(_cc_miss_entries)})
                for entry in _cc_miss_entries:
                    text = str(entry.get("text", ""))
                    try:
                        result = _record_clip_encode(
                            caller="execution_prefill", clip=clip, text=text,
                            _explicit_state=_worker_state,
                            callback=lambda c=clip, t=text: self._invoke_original(
                                "CLIPTextEncode", {"clip": c, "text": t}
                            ),
                        )
                        _cc_encode_calls += 1
                        results[(id(clip), text)] = result
                        if _cc_cache_svc is not None:
                            if _cc_cache_svc.store_entry(_cc_ctx, entry, result):
                                _cc_stored += 1
                    except Exception as exc:
                        if trace:
                            trace.emit("execution_prefill_encode_error",
                                       phase="execution",
                                       metadata={"error": str(exc)[:200],
                                                 "text_length": len(text)})
            if _cc_stored:
                _cc_stored_key_info = conditioning_cache_key_summary(
                    _cc_ctx, _cc_miss_entries
                )
                log_conditioning_cache_decision(
                    "miss_stored", key_hash=_cc_stored_key_info["key_hash"],
                    identity_status=_cc_stored_key_info["identity_status"],
                    encode_calls=_cc_encode_calls,
                    schema_version=_cc_stored_key_info["schema_version"],
                    validation_scope=_cc_stored_key_info["validation_scope"],
                    stored=_cc_stored,
                    entries=len(filtered),
                    request_id=_request_id or "absent",
                )
                if trace:
                    trace.emit(
                        "clip_conditioning_cache_decision",
                        phase="execution",
                        metadata={
                            "decision": "miss_stored",
                            "key_hash": _cc_stored_key_info["key_hash"],
                            "identity_status": _cc_stored_key_info["identity_status"],
                            "schema_version": _cc_stored_key_info["schema_version"],
                            "validation_scope": _cc_stored_key_info["validation_scope"],
                            "stored_count": _cc_stored,
                            "encode_calls": _cc_encode_calls,
                        },
                    )
            elif _cc_cache_svc is not None and trace:
                trace.emit(
                    "clip_conditioning_cache_decision",
                    phase="execution",
                    metadata={
                        "decision": "miss_not_stored",
                        "encode_calls": _cc_encode_calls,
                        "entry_count": len(_cc_miss_entries),
                        "reason": getattr(_cc_cache_svc, "last_store_reason", ""),
                    },
                )
            # ── Terminal events FIRST, then publish results ──────────────
            # ``_prefill_results`` is published under ``_prefill_lock`` AFTER
            # ``execution_prefill_encode_end``/``execution_prefill_completed``
            # have been emitted.  A graph consumer that finds a published
            # cache hit can therefore never observe the result before the
            # terminal events, so a successful prefill can never emit
            # ``clip_prefill_reconciliation`` ahead of the encode-end/completed
            # boundaries (which would yield a spuriously incomplete record).
            _encode_end = _capture_phase_counters()
            if not _cc_exact_hit:
                record_clip_encode_end(_request_id, _encode_start, _encode_end)
                if trace:
                    trace.emit(_EVENT_ENCODE_END, phase="execution",
                               metadata={"counters": _encode_end,
                                         "encoded_count": _cc_encode_calls})
                    if unet_activation_mode() == _UNET_ACTIVATION_MODE_CLIP_GPU_READY:
                        trace.emit(_EVENT_CLIP_ENCODE_END, phase="execution",
                                   metadata={"counters": _encode_end,
                                             "encoded_count": _cc_encode_calls,
                                             "mode": _UNET_ACTIVATION_MODE_CLIP_GPU_READY,
                                             "request_id": _request_id})

            if trace:
                unet_skipped = prep.unet_future is None
                unet_pending = (
                    not unet_skipped and not prep.unet_future.done()
                ) if prep.unet_future is not None else False
                trace.emit(_EVENT_COMPLETED, phase="execution",
                           metadata={"encoded_count": _cc_encode_calls,
                                     "cache_hit_count": len(_cc_hit_results),
                                     "filtered_entries": len(filtered),
                                     "total_entries": len(entries),
                                     "wait_for_unet": wait_for_unet,
                                     "unet_skipped": unet_skipped,
                                     "unet_pending": unet_pending,
                                     "unet_resolved": not unet_skipped and not unet_pending,
                                     "counters": _encode_end})
            # Store results for graph consumption — last, so any consumer
            # that observes a published result has already seen the terminal
            # events above (cache-hit reconciliation ordering invariant).
            with self._prefill_lock:
                self._prefill_results.update(results)
            return results

        # Use the coordinator's scheduler to submit (idempotent via
        # schedule_prefill checking prefill_future).  The callback waits
        # for CLIP (and optionally UNET when the legacy barrier is active)
        # futures which were submitted during restore.
        # Deadlock analysis (V2 overlap / default):
        #   max_workers=2: UNET (thread A) + CLIP (thread B) compete in
        #     parallel.  Prefill callback waits for CLIP only (default) or
        #     UNET first (legacy).  In default mode the CLIP thread picks
        #     up the callback, resolves immediately (CLIP is already done
        #     or finishes soon), and begins encoding while UNET is still
        #     loading — the mutation lane serialises any GPU commit.
        #   max_workers=1: single thread runs UNET -> CLIP -> prefill
        #     sequentially; both futures complete before prefill starts.
        #   In both cases the preload barrier has NOT been waited yet
        #   (it runs later inside _execute_v2_prompt_executor), but the
        #   callback's direct future.wait() is safe because the futures
        #   were submitted to the same pool and are in-flight or done.
        #   GPU safety: ``load_models_gpu`` wrapper acquires the mutation
        #   lane (priority ``UNET > CLIP > prefill > VAE > sampler``), so
        #   concurrent UNET GPU commits are serialised through the lane.
        self.coordinator.schedule_prefill(_execution_prefill, prep, trace=trace)
        return True

    @staticmethod
    def _resolve_lane_override(override: bool | None, computed: bool) -> bool:
        """Return *override* when not None, else *computed*."""
        return override if override is not None else computed

    def close_workers(self) -> None:
        """Wait for submitted restore futures and shut down the coordinator pool.
        Swallows worker exceptions so existing loader fallback behavior remains.
        The coordinator recreates a pool on the next _submit call."""
        prep = self._preparation
        if prep is not None:
            _cw_start_ns = time.monotonic_ns()
            _present = 0
            _done = 0
            _failed = 0
            for future in (prep.unet_future, prep.clip_future, prep.vae_future):
                if future is not None:
                    _present += 1
                    if future.done():
                        _done += 1
                        if future.exception() is not None:
                            _failed += 1
                    try:
                        future.result()
                    except Exception:
                        _failed += 1
            _cw_wait_ms = round((time.monotonic_ns() - _cw_start_ns) / 1_000_000, 3)
            if self._trace:
                self._trace.emit("close_workers_start", phase="restore", metadata={
                    "present": _present,
                    "done_before_wait": _done,
                    "failed": _failed,
                })
                self._trace.emit("close_workers_end", phase="restore", metadata={
                    "wait_ms": _cw_wait_ms,
                    "present": _present,
                    "done_final": _present,
                })
        self.coordinator.close()

    def extend_preparation(
        self,
        *,
        prepare_unet: bool = True,
        prepare_vae: bool = True,
        trace: RuntimeTrace | None = None,
    ) -> RestorePreparation | None:
        """Extend the current preparation with missing lanes (no clear+re-prepare).

        Delegates to ``ModelPreloadCoordinator.extend()`` which never
        resubmits a lane whose future is already present.  The existing
        ``clip_future`` (submitted during a prior clip-only prepare) is
        preserved, and the thread pool is recreated on demand if it was
        closed.  Returns None when no preparation exists.
        """
        if self._preparation is None or self._model_key is None:
            return None
        if vae_activation_mode() == _VAE_ACTIVATION_MODE_SAMPLING_END:
            # sampling_end mode: never submit a VAE future from extension
            # either — the VAE is activated once at sampling_end.
            prepare_vae = False
        return self.coordinator.extend(
            self._preparation,
            prepare_unet=prepare_unet,
            prepare_vae=prepare_vae,
            trace=trace,
        )

    def _init_ready_preparation(
        self,
        *,
        model_key: ModelRestoreKey,
        prefill_key: PrefillKey,
        model_spec: Mapping[str, Any],
        unet: Any = _LOADER_MISS,
        clip: Any = _LOADER_MISS,
        trace: RuntimeTrace | None = None,
    ) -> RestorePreparation:
        self._model_key = model_key
        self._prefill_key = prefill_key
        self._model_spec = dict(model_spec) if isinstance(model_spec, Mapping) else {}
        self._trace = trace

        if not self.install(self._nodes, trace=trace):
            raise RuntimeError(
                "V2LoaderBridge: install() could not establish "
                "loader wrappers; bridge is not ready to serve snapshot models"
            )

        with self._prefill_lock:
            self._prefill_results.clear()
            self._reconciliation_emitted = False

        prep = RestorePreparation(model_key=model_key, prefill_key=prefill_key)
        _now = time.time()
        # Reset the per-request captured graph VAELoader output so a fresh
        # request never reuses a previous request's captured VAE object.
        self._graph_vae_output = None

        # Set completed futures BEFORE publishing the preparation,
        # so graph-time consumers never observe an incomplete state.
        if unet is not _LOADER_MISS:
            # Register snapshot UNET for first-CUDA timing and install
            # forward pre-hook on its diffusion model.
            register_unet_forward_probe(unet, source="cpu_snapshot")
            unet_future: Future[Any] = Future()
            unet_future.set_result(unet)
            prep.unet_future = unet_future
            prep.diagnostics.unet_started_at = _now
            prep.diagnostics.unet_completed_at = _now

        if clip is not _LOADER_MISS:
            clip_future: Future[Any] = Future()
            clip_future.set_result(clip)
            prep.clip_future = clip_future
            prep.diagnostics.clip_started_at = _now
            prep.diagnostics.clip_completed_at = _now

        # Publish only after all ready futures are assigned.
        self._preparation = prep
        self.coordinator._active = prep

        if trace is not None:
            self._preparation_trace = trace
            self._preparation_event_cursor = len(trace.events)

        return prep

    def use_ready_models(
        self,
        *,
        model_key: ModelRestoreKey,
        prefill_key: PrefillKey,
        model_spec: Mapping[str, Any],
        unet: Any,
        clip: Any,
        trace: RuntimeTrace | None = None,
    ) -> RestorePreparation:
        return self._init_ready_preparation(
            model_key=model_key, prefill_key=prefill_key,
            model_spec=model_spec, unet=unet, clip=clip, trace=trace,
        )

    def use_ready_clip(
        self,
        *,
        model_key: ModelRestoreKey,
        prefill_key: PrefillKey,
        model_spec: Mapping[str, Any],
        clip: Any,
        trace: RuntimeTrace | None = None,
    ) -> RestorePreparation:
        return self._init_ready_preparation(
            model_key=model_key, prefill_key=prefill_key,
            model_spec=model_spec, clip=clip, trace=trace,
        )

    def clear(self) -> None:
        """Disable consumption when a restore has no authoritative plan."""
        self._model_key = None
        self._prefill_key = None
        self._model_spec = {}
        self._preparation = None
        self._trace = None
        self._preparation_trace = None
        self._preparation_event_cursor = 0
        self._exact_vae = None
        self._snapshot_loader_outputs = None
        self._graph_vae_output = None
        self.coordinator._active = None
        with self._prefill_lock:
            self._prefill_results.clear()
            self._reconciliation_emitted = False

    def drain_worker_events(self, target_trace: RuntimeTrace | None = None) -> int:
        """Wait for all preparation futures and drain late events to *target_trace*.

        Restore-time ``prepare()`` returns before background workers finish
        emitting events (``read_start/end``, ``cpu_prepare_*``, ``ready``,
        and graph demand/wait).  This method blocks until every submitted
        future is terminal, then copies new events (those appended after the
        cursor recorded at ``prepare()`` return) from the preparation trace
        into *target_trace*.

        Returns the number of events drained, or 0 if no trace/futures.
        Thread-safe: waits for futures, then drains under no further mutation.
        """
        source = self._preparation_trace
        if source is None or target_trace is None:
            return 0
        prep = self._preparation
        if prep is None:
            return 0
        # Wait for all submitted futures to become terminal.
        for future in (prep.unet_future, prep.clip_future, prep.vae_future, prep.prefill_future):
            if future is not None:
                try:
                    future.result()
                except Exception:
                    pass
        # Drain events appended since the cursor.
        cursor = self._preparation_event_cursor
        all_events = source.events
        if len(all_events) > cursor:
            new_events = all_events[cursor:]
            target_trace.extend(new_events)
            self._preparation_event_cursor = len(all_events)
            return len(new_events)
        return 0

    def _make_wrapper(self, class_name: str, method_name: str, original: Callable[..., Any]) -> Callable[..., Any]:
        if class_name == "UNETLoader":
            def wrapped(node: Any, *args: Any, **kwargs: Any) -> Any:
                active = current_v2_loader_bridge()
                if active is not None:
                    result = active._consume_unet(args, kwargs)
                    if result is not _LOADER_MISS:
                        return result
                return original(node, *args, **kwargs)
        elif class_name in {"CLIPLoader", "DualCLIPLoader"}:
            def wrapped(node: Any, *args: Any, **kwargs: Any) -> Any:
                active = current_v2_loader_bridge()
                if active is not None:
                    result = active._consume_clip(class_name, args, kwargs)
                    if result is not _LOADER_MISS:
                        return result
                return original(node, *args, **kwargs)
        elif class_name == "VAELoader":
            def wrapped(node: Any, *args: Any, **kwargs: Any) -> Any:
                active = current_v2_loader_bridge()
                if active is not None:
                    result = active._consume_vae(args, kwargs)
                    if result is not _LOADER_MISS:
                        # Capture whatever the bridge served so the VAE
                        # resolution adapter can reuse the exact graph VAE
                        # object at the sampling_end boundary.
                        active._capture_graph_vae_output(result)
                        return result
                result = original(node, *args, **kwargs)
                if active is not None:
                    active._capture_graph_vae_output(result)
                return result
        elif class_name == "VAEDecode":
            def wrapped(node: Any, *args: Any, **kwargs: Any) -> Any:
                active = current_v2_loader_bridge()
                if active is not None:
                    # VAEDecode demand join (sampling_end mode): joins the
                    # activation future outside the mutation lane; always
                    # falls through so decode stays in normal graph order.
                    result = active._consume_vae_decode(args, kwargs)
                    if result is not _LOADER_MISS:
                        return result
                return original(node, *args, **kwargs)
        elif class_name == "CLIPTextEncode":
            def wrapped(node: Any, *args: Any, **kwargs: Any) -> Any:
                active = current_v2_loader_bridge()
                if active is not None:
                    _diag_state = _ACTIVATION_DIAGNOSTIC_STATE.get()
                    if _diag_state is not None:
                        _diag_state["clip_encode_instrumentation_attached"] = True
                    result = active._consume_prefill(args, kwargs)
                    if result is not _LOADER_MISS:
                        return result
                # Graph fallback: instrument with caller='graph'
                _clip = kwargs.get("clip", args[0] if args else None)
                _text = str(kwargs.get("text", args[1] if len(args) > 1 else ""))
                if _clip is not None and _text:
                    return _record_clip_encode(
                        caller="graph", clip=_clip, text=_text,
                        callback=lambda: original(node, *args, **kwargs),
                    )
                return original(node, *args, **kwargs)
        else:
            def wrapped(node: Any, *args: Any, **kwargs: Any) -> Any:
                active = current_v2_loader_bridge()
                if active is not None:
                    result = active._consume_prefill(args, kwargs)
                    if result is not _LOADER_MISS:
                        return result
                return original(node, *args, **kwargs)
        return wrapped

    def _request_list(self, bucket: str) -> list[dict[str, Any]]:
        loaders = self._model_spec.get("loaders", self._model_spec)
        values = loaders.get(bucket, []) if isinstance(loaders, Mapping) else []
        return [dict(value) for value in values if isinstance(value, Mapping)]

    def _compute_clip_expected_read_count(self) -> int:
        """Derive the exact expected ``load_torch_file`` count for the CLIP lane.

        CLIPLoader: one read (single ``clip_name``).
        DualCLIPLoader: two reads (``clip_name1`` + ``clip_name2``).
        Falls back to 1 when the request cannot be resolved.
        """
        if not self._model_key or not self._model_key.clip_identity:
            return 1
        request = self._find_request("clip", self._model_key.clip_identity)
        if request is None:
            return 1
        loader_class = str(request.get("loader_class", ""))
        if loader_class == "DualCLIPLoader":
            return 2
        return 1

    def _find_request(self, bucket: str, identity: str) -> dict[str, Any] | None:
        for request in self._request_list(bucket):
            if bucket == "vae":
                vae_name = str(request.get("vae_name", "") or "")
                if identity and identity == vae_name:
                    return request
            values = (
                request.get("unet_name"),
                request.get("clip_name"),
                request.get("clip_name1"),
            )
            if identity and identity in {str(value) for value in values if value}:
                return request
            if bucket == "clip" and request.get("clip_name1") and request.get("clip_name2"):
                if identity == f"{request['clip_name1']}||{request['clip_name2']}":
                    return request
        return None

    def _load_unet(self, model_key: ModelRestoreKey) -> Any:
        request = self._find_request("unet", model_key.unet_identity)
        if request is None:
            raise RuntimeError(f"v2 UNET loader request is absent for {model_key.unet_identity!r}")
        kwargs = {
            "unet_name": request.get("unet_name", model_key.unet_identity),
            "weight_dtype": request.get("weight_dtype", "default"),
        }
        _req_wd = request.get("weight_dtype", "default")
        # Resolve effective dtype for diagnostic logging (shared resolver)
        _eff_dtype, _eff_label = resolve_unet_effective_dtype(_req_wd)
        result = self._invoke_original("UNETLoader", kwargs)
        unet = result[0] if isinstance(result, (tuple, list)) and result else result

        # ── Emit normal_loader_ready state (print + trace) ──────────────
        _normal_state: dict[str, Any] = {}
        try:
            # Safely import model_management for loaded_models comparability
            _mgmt = None
            try:
                import comfy.model_management as _comfy_mm
                _mgmt = _comfy_mm
            except Exception:
                _mgmt = None

            _normal_state = collect_unet_runtime_state(
                unet, model_management=_mgmt,
            )
        except Exception:
            _normal_state = collect_unet_runtime_state(unet, model_management=None)

        try:
            _state_json = __import__("json").dumps(
                _normal_state, default=str, separators=(",", ":"), sort_keys=True,
            )
            print(
                f"[v2.unet_runtime_state] "
                f"stage=normal_loader_ready "
                f"unet_identity={model_key.unet_identity} "
                f"requested_weight_dtype={_req_wd} "
                f"effective_weight_dtype={_eff_label} "
                f"state={_state_json}",
                flush=True,
            )
        except Exception:
            pass

        try:
            # Trace event — prefer request trace, fallback to bridge trace
            _target_trace = _ACTIVE_REQUEST_TRACE.get() or self._trace
            if _target_trace is not None:
                _target_trace.emit(
                    "unet_runtime_state",
                    metadata={
                        "stage": "normal_loader_ready",
                        "unet_identity": model_key.unet_identity,
                        "requested_weight_dtype": _req_wd,
                        "effective_weight_dtype": _eff_label,
                        "request_id": str(getattr(_target_trace, "request_id", None) or ""),
                        "restored_instance_id": _LATEST_RESTORED_INSTANCE_ID,
                        "restore_session_id": _LATEST_RESTORE_SESSION_ID,
                        "state": _normal_state,
                    },
                )
        except Exception:
            pass

        register_unet_forward_probe(unet, source="normal_loader")
        return unet

    def _load_clip(self, model_key: ModelRestoreKey) -> Any:
        request = self._find_request("clip", model_key.clip_identity)
        if request is None:
            raise RuntimeError(f"v2 CLIP loader request is absent for {model_key.clip_identity!r}")
        class_name = str(request.get("loader_class", "CLIPLoader"))
        kwargs = dict(request)
        kwargs.pop("node_id", None)
        kwargs.pop("loader_class", None)
        kwargs.setdefault("type", model_key.clip_type or "stable_diffusion")
        kwargs.setdefault("device", "default")
        result = self._invoke_original(class_name, kwargs)
        return result[0] if isinstance(result, (tuple, list)) and result else result

    def _load_vae(self, model_key: ModelRestoreKey) -> Any:
        request = self._find_request("vae", model_key.vae_identity)
        if request is None:
            raise RuntimeError(f"v2 VAE loader request is absent for {model_key.vae_identity!r}")
        kwargs = {
            "vae_name": request.get("vae_name", model_key.vae_identity),
        }
        result = self._invoke_original("VAELoader", kwargs)
        return result[0] if isinstance(result, (tuple, list)) and result else result

    @staticmethod
    def _filter_prefill_entries(
        entries: list[dict[str, Any]],
        lane_mode: str,
    ) -> tuple[list[dict[str, Any]], int, list[str]]:
        """Filter *entries* according to *lane_mode*.

        Returns ``(filtered, skipped_count, skipped_reasons)``.

        * **critical**: keep entries with a role in ``_PREFILL_CRITICAL_ROLES``
          and non-empty text.
        * **all**: keep everything (non-empty text is still required).
        * **none**: skip everything (return empty).

        Empty-text entries are always skipped regardless of lane mode
        since they produce no useful prefill work.
        """
        if lane_mode == "none":
            return [], len(entries), ["lane_mode=none"]
        kept: list[dict[str, Any]] = []
        skipped = 0
        reasons: list[str] = []
        for entry in entries:
            if not isinstance(entry, Mapping):
                skipped += 1
                reasons.append("non_mapping_entry")
                continue
            text = str(entry.get("text", "") or "")
            if not text:
                skipped += 1
                reasons.append(
                    f"node_id={entry.get('node_id', '?')} empty_text"
                )
                continue
            if lane_mode == "all":
                kept.append(entry)
                continue
            # lane_mode == "critical" (default)
            role = str(entry.get("role", "") or "").lower()
            if role in _PREFILL_CRITICAL_ROLES:
                kept.append(entry)
            else:
                skipped += 1
                reasons.append(
                    f"node_id={entry.get('node_id', '?')} role={role!r}"
                )
        return kept, skipped, reasons

    def _prefill(self, prefill_key: PrefillKey, clip: Any) -> dict[tuple[int, str], Any]:
        lane_mode = _PREFILL_LANE_MODE
        options = prefill_key.encode_options
        entries = options.get("encodes", []) if isinstance(options, Mapping) else []
        results: dict[tuple[int, str], Any] = {}
        filtered, skipped_count, skipped_reasons = self._filter_prefill_entries(
            entries, lane_mode
        )
        for entry in filtered:
            text = str(entry.get("text", ""))
            result = _record_clip_encode(
                caller="execution_prefill", clip=clip, text=text,
                callback=lambda c=clip, t=text: self._invoke_original(
                    "CLIPTextEncode", {"clip": c, "text": t}
                ),
            )
            results[(id(clip), text)] = result
        if self._preparation is not None:
            self._preparation.diagnostics.prefill_lane_mode = lane_mode
            self._preparation.diagnostics.prefill_total_encodes = len(entries)
            self._preparation.diagnostics.prefill_skipped_encodes = skipped_count
            self._preparation.diagnostics.prefill_skipped_reasons = skipped_reasons
        return results

    def _consume_unet(self, args: tuple[Any, ...], kwargs: Mapping[str, Any]) -> Any:
        identity = kwargs.get("unet_name", args[0] if args else "")
        return self._consume_model_impl(
            lane="UNET",
            loader_class="UNETLoader",
            diagnostics_prefix="unet",
            requested_identity=str(identity),
            planned_identity=self._model_key.unet_identity if self._model_key else "",
            wait_fn=self.coordinator.wait_unet,
            demand_metadata={"unet_name": str(identity), "lane": "UNET", "loader_class": "UNETLoader"},
        )

    def _consume_clip(self, class_name: str, args: tuple[Any, ...], kwargs: Mapping[str, Any]) -> Any:
        if class_name == "DualCLIPLoader":
            from .restore_plan import _build_dual_clip_identity
            clip_a = kwargs.get("clip_name1", args[0] if args else "")
            clip_b = kwargs.get("clip_name2", args[1] if len(args) > 1 else "")
            identity = _build_dual_clip_identity(clip_a, clip_b)
        else:
            identity = str(kwargs.get("clip_name", args[0] if args else ""))
        return self._consume_model_impl(
            lane="CLIP",
            loader_class=class_name,
            diagnostics_prefix="clip",
            requested_identity=identity,
            planned_identity=self._model_key.clip_identity if self._model_key else "",
            wait_fn=self.coordinator.wait_clip,
            demand_metadata={"clip_identity": identity},
        )

    def _consume_vae(self, args: tuple[Any, ...], kwargs: Mapping[str, Any]) -> Any:
        identity = str(kwargs.get("vae_name", args[0] if args else ""))
        if vae_activation_mode() == _VAE_ACTIVATION_MODE_SAMPLING_END:
            # sampling_end mode: no VAE future was prepared at restore.
            # Join the sampling_end activation future (when present and
            # terminal-ready) outside the mutation lane; on any absent /
            # failed / invalid / not-ready outcome return _LOADER_MISS so
            # the unchanged original VAELoader path proceeds.
            _outcome = self._join_vae_early_activation(trace=self._trace)
            if _outcome.get("valid") and _outcome.get("vae") is not None:
                return (_outcome["vae"],)
            return _LOADER_MISS
        return self._consume_model_impl(
            lane="VAE",
            loader_class="VAELoader",
            diagnostics_prefix="vae",
            requested_identity=identity,
            planned_identity=self._model_key.vae_identity if self._model_key else "",
            wait_fn=self.coordinator.wait_vae,
            demand_metadata={"vae_name": identity, "lane": "VAE"},
            emit_consumed_on_error=False,
            skip_loader_class=True,
        )

    def _consume_vae_decode(self, args: tuple[Any, ...], kwargs: Mapping[str, Any]) -> Any:
        """VAEDecode demand hook (sampling_end VAE activation join).

        Joins the request's sampling_end VAE activation future OUTSIDE the
        mutation lane and emits the concise consumed line (once per
        request).  Decode itself stays in normal graph order — this hook
        never executes decode and always returns ``_LOADER_MISS`` so the
        original VAEDecode path proceeds unchanged.  In any non-active mode
        this is a no-op.
        """
        if vae_activation_mode() == _VAE_ACTIVATION_MODE_SAMPLING_END:
            self._join_vae_early_activation(trace=self._trace)
        return _LOADER_MISS

    def set_exact_vae(self, vae: Any) -> None:
        """Accept a future exact VAE object (snapshot/seed-compatible branch).

        The exact object takes precedence over the captured graph VAELoader
        output and the original VAELoader fallback in ``resolve_vae_object``.
        """
        self._exact_vae = vae

    def set_snapshot_loader_outputs(self, outputs: Mapping[str, Any] | None) -> None:
        """Accept snapshot/seed loader outputs without owning their lifecycle."""
        self._snapshot_loader_outputs = outputs if isinstance(outputs, Mapping) else None

    def _capture_graph_vae_output(self, result: Any) -> None:
        """Capture the first graph VAELoader output of the current request.

        First capture wins (the workflow's VAELoader node is authoritative);
        a later different VAELoader output is ignored.  Never duplicates
        transfers — the object is only referenced, not re-loaded.
        """
        if self._graph_vae_output is not None:
            return
        _vae = result[0] if isinstance(result, (tuple, list)) and result else result
        if _vae is not None:
            self._graph_vae_output = _vae

    def resolve_vae_object(
        self,
        *,
        trace: RuntimeTrace | None = None,
    ) -> tuple[Any, str]:
        """Resolve the exact VAE object for sampling_end early activation.

        Small VAE-resolution adapter.  Priority:
          1. ``set_exact_vae()`` object (snapshot/seed-compatible inputs).
          2. Snapshot/seed-compatible attributes when the later branch
             provides them — ``getattr(self._cpu_snapshot_models, 'vae',
             None)`` and ``self._snapshot_loader_outputs['vae']`` — both
             absent-safe (the bridge never fabricates a source).
          3. Captured graph VAELoader output of this request.
          4. Existing original VAELoader resolution (``self._load_vae``).

        Returns ``(vae, source)`` or ``(None, "")`` when no resolution is
        possible.  Each source is consulted at most once per call; no VAE
        object/transfer is duplicated.
        """
        _vae = getattr(self, "_exact_vae", None)
        if _vae is not None:
            return _vae, "exact_object"
        try:
            _models = getattr(self, "_cpu_snapshot_models", None)
            _vae = getattr(_models, "vae", None)
            if _vae is not None:
                return _vae, "snapshot_models"
        except Exception:
            pass
        try:
            _outputs = getattr(self, "_snapshot_loader_outputs", None)
            if isinstance(_outputs, Mapping):
                _vae = _outputs.get("vae")
                if _vae is not None:
                    return _vae, "snapshot_loader_outputs"
        except Exception:
            pass
        if self._graph_vae_output is not None:
            return self._graph_vae_output, "graph_vae_loader"
        if self._model_key is not None and getattr(self._model_key, "vae_identity", ""):
            try:
                return self._load_vae(self._model_key), "original_loader"
            except Exception:
                return None, ""
        return None, ""

    def _join_vae_early_activation(
        self,
        *,
        trace: RuntimeTrace | None = None,
    ) -> dict[str, Any]:
        """Join the request's sampling_end VAE activation future at graph
        (VAEDecode/VAELoader) demand.  Runs OUTSIDE the mutation lane.

        Emits the concise ``[v2.vae_early_activation] event=consumed
        join_wait_ms=...`` line exactly once per request (first successful
        ready join wins).  Returns an outcome dict; ``valid=True`` with
        ``vae`` set only when the activation is terminal-ready and
        validated.  Any other outcome lets the caller fall back to the
        unchanged original VAEDecode/loader path.
        """
        if vae_activation_mode() != _VAE_ACTIVATION_MODE_SAMPLING_END:
            return {"scheduled": False, "status": "mode_late", "terminal": False,
                    "valid": False, "reason": "", "join_wait_ms": 0.0, "vae": None}
        _rt = trace or self._trace
        _request_id = str(_rt.request_id) if _rt is not None else ""
        _state = _vae_activation_get(_request_id)
        if _state is None or _state.get("future") is None:
            return {"scheduled": False, "status": "not_scheduled", "terminal": False,
                    "valid": False, "reason": "", "join_wait_ms": 0.0, "vae": None}
        _demand_ns = time.monotonic_ns()
        _state["join_demand_mono_ns"] = _demand_ns
        _future = _state["future"]
        try:
            _future.result()
        except Exception as exc:
            return _vae_activation_fallback(
                _state, _rt, _request_id,
                reason="future_error", error=str(exc)[:200],
                join_wait_ms=round((time.monotonic_ns() - _demand_ns) / 1_000_000, 3),
            )
        _join_wait_ms = round((time.monotonic_ns() - _demand_ns) / 1_000_000, 3)
        _state["join_completed_mono_ns"] = time.monotonic_ns()
        _state["join_wait_ms"] = _join_wait_ms
        with _VAE_ACTIVATION_LOCK:
            _status = _state.get("status", "")
            _terminal = bool(_state.get("terminal", False))
        if _terminal and _status == "ready":
            _valid, _reason, _vae = _validate_vae_early_activation(_state)
            if _valid:
                with _VAE_ACTIVATION_LOCK:
                    _joined = bool(_state.get("joined", False))
                    if not _joined:
                        _state["joined"] = True
                if _rt is not None and not _joined:
                    _rt.emit(_EVENT_VAE_EA_CONSUMED, phase="execution", metadata={
                        "mode": _state.get("mode", ""),
                        "trigger": _state.get("trigger", ""),
                        "request_id": _request_id,
                        "key_hash": _state.get("key_hash", ""),
                        "join_wait_ms": _join_wait_ms,
                        "transfer_count": _state.get("transfer_count", 0),
                        "cache_present": bool(_state.get("cache_present", False)),
                        "vae_object_id": _state.get("vae_object_id", ""),
                        "vae_resolution_source": _state.get("vae_resolution_source", ""),
                        "restored_instance_id": _LATEST_RESTORED_INSTANCE_ID,
                        "restore_session_id": _LATEST_RESTORE_SESSION_ID,
                    })
                if not _joined:
                    print(
                        f"[v2.vae_early_activation] event=consumed "
                        f"request_id={_request_id or 'absent'} mode={_state.get('mode', '')} "
                        f"key_hash={_state.get('key_hash', '')} join_wait_ms={_join_wait_ms} "
                        f"status=ready source={_state.get('vae_resolution_source', '') or 'absent'}",
                        flush=True,
                    )
                return {"scheduled": True, "status": "ready", "terminal": True,
                        "valid": True, "reason": "", "join_wait_ms": _join_wait_ms,
                        "vae": _vae}
            return _vae_activation_fallback(
                _state, _rt, _request_id,
                reason=f"invalid:{_reason}", join_wait_ms=_join_wait_ms,
            )
        if _terminal:
            return _vae_activation_fallback(
                _state, _rt, _request_id,
                reason=str(_state.get("reason", _status) or _status),
                join_wait_ms=_join_wait_ms,
            )
        return _vae_activation_fallback(
            _state, _rt, _request_id, reason="non_terminal", join_wait_ms=_join_wait_ms,
        )

    def _join_unet_early_activation(
        self,
        unet: Any,
        *,
        trace: RuntimeTrace | None = None,
    ) -> dict[str, Any]:
        """Join the request's early UNET activation future at graph/sampler
        demand.

        Emits ``unet_early_activation_graph_demand`` then
        ``graph_join_start`` / ``graph_join_end`` around the join, which
        runs OUTSIDE the mutation lane.  A terminal non-ready outcome
        elects the unchanged late fallback exactly once inside
        ``join_unet_early_activation``."""
        _active = _ACTIVE_REQUEST_TRACE.get()
        _request_id = str(_active.request_id) if _active is not None else ""
        if not _request_id and trace is not None:
            _request_id = str(trace.request_id)
        if not _request_id and self._trace is not None:
            _request_id = str(self._trace.request_id)
        _rt = trace or self._trace
        _mode = unet_activation_mode()
        if (
            _mode not in _UNET_ACTIVATION_MODE_ACTIVE
            and not _unet_cache_hit_activation_pending(_request_id)
        ):
            # Late mode (the default) preserves Phase 0 exactly: the UNET
            # graph consumer must not emit any unet_early_activation_*
            # graph-demand/join markers, perform join helper work, create
            # state, or add a graph wait.  Return immediately BEFORE any
            # marker is emitted.
            return {"scheduled": False, "status": "mode_late", "terminal": False,
                    "valid": False, "reason": "", "join_wait_ms": 0.0}
        if _rt is not None:
            _rt.emit(_EVENT_UNET_EA_GRAPH_DEMAND, phase="execution", metadata={
                "mode": _mode,
                "request_id": _request_id,
                "sampler_patcher_object_id": str(id(unet)) if unet is not None else "",
            })
            _rt.emit(_EVENT_UNET_EA_GRAPH_JOIN_START, phase="execution", metadata={
                "mode": _mode,
                "request_id": _request_id,
                "key_hash": "",
            })
        _outcome = join_unet_early_activation(
            self, unet=unet, trace=_rt, request_id=_request_id,
        )
        if _rt is not None:
            _state = _unet_activation_get(_request_id)
            _rt.emit(_EVENT_UNET_EA_GRAPH_JOIN_END, phase="execution", metadata={
                "mode": _mode,
                "request_id": _request_id,
                "key_hash": (_state or {}).get("key_hash", ""),
                "status": _outcome.get("status", ""),
                "valid": bool(_outcome.get("valid", False)),
                "terminal": bool(_outcome.get("terminal", False)),
                "join_wait_ms": _outcome.get("join_wait_ms", 0.0),
                "sampler_patcher_object_id": str(id(unet)) if unet is not None else "",
            })
        return _outcome

    def _consume_model_impl(
        self,
        *,
        lane: str,
        loader_class: str,
        diagnostics_prefix: str,
        requested_identity: str,
        planned_identity: str,
        wait_fn: Callable[[RestorePreparation], Any],
        demand_metadata: Mapping[str, Any],
        emit_consumed_on_error: bool = True,
        skip_loader_class: bool = False,
    ) -> Any:
        """Shared model-consumption implementation for UNET/CLIP/VAE lanes.

        Each public ``_consume_*`` method extracts the lane-specific identity
        then delegates here.  Parameters map directly to observable event
        differences between lanes — no implicit behaviour.

        *lane*, *loader_class*, *diagnostics_prefix* — lane identity strings.
        *requested_identity* — the identity extracted from the graph call.
        *planned_identity* — the expected identity from ``ModelRestoreKey``.
        *wait_fn* — coordinator method to wait for the prepared future.
        *demand_metadata* — metadata dict for the ``graph_{prefix}_demand`` event
          (unique shape per lane).
        *emit_consumed_on_error* — when True emits ``graph_{prefix}_consumed``
          in the exception path (UNET/CLIP). VAE omits this event on error.
        *skip_loader_class* — when True omits ``loader_class`` from
          ``graph_model_demand``, ``future_failed``, ``future_unavailable``,
          and canonical ``graph_demand`` (VAE divergence).
        """
        key = self._model_key
        preparation = self._preparation

        # --- Missing spec check ---
        if key is None or preparation is None:
            if self._trace:
                self._trace.emit(
                    "request_spec_missing",
                    phase="execution",
                    metadata={
                        "lane": lane,
                        "loader_class": loader_class,
                        "hashed_requested_identity": stable_hash(requested_identity),
                        "terminal_outcome": "fallback_missing_spec",
                    },
                )
                self._trace.emit("original_loader_fallback", phase="execution", metadata={
                    "lane": lane, "reason": "missing_spec",
                })
            return _LOADER_MISS

        # --- Identity mismatch check ---
        if requested_identity != planned_identity:
            if self._trace:
                self._trace.emit(
                    "identity_mismatch",
                    phase="execution",
                    metadata={
                        "lane": lane,
                        "loader_class": loader_class,
                        "hashed_planned_identity": stable_hash(planned_identity),
                        "hashed_requested_identity": stable_hash(requested_identity),
                        "terminal_outcome": "fallback_identity_mismatch",
                    },
                )
                self._trace.emit("original_loader_fallback", phase="execution", metadata={
                    "lane": lane, "reason": "identity_mismatch",
                })
            return _LOADER_MISS

        # --- Graph demand and wait ---
        if self._trace:
            self._trace.emit(f"graph_{diagnostics_prefix}_demand", phase="execution",
                             metadata=dict(demand_metadata))
            model_demand_meta: dict[str, Any] = {"lane": lane}
            if not skip_loader_class:
                model_demand_meta["loader_class"] = loader_class
            self._trace.emit("graph_model_demand", phase="execution", metadata=model_demand_meta)
            self._trace.emit(f"graph_{diagnostics_prefix}_wait_start", phase="execution")
            self._trace.emit("graph_wait_started", phase="execution", metadata={"lane": lane})
            # ── Canonical consumer events (Phase 0, additive) ──
            canonical_demand_meta: dict[str, Any] = {"lane": lane}
            if not skip_loader_class:
                canonical_demand_meta["loader_class"] = loader_class
            self._trace.emit("graph_demand", phase="execution", metadata=canonical_demand_meta)
            self._trace.emit("graph_wait_start", phase="execution", metadata={"lane": lane})
        try:
            result = wait_fn(preparation)
        except Exception as exc:
            if self._trace:
                self._trace.emit(f"graph_{diagnostics_prefix}_wait_end", phase="execution",
                                 metadata={"status": "error"})
                if emit_consumed_on_error:
                    self._trace.emit(f"graph_{diagnostics_prefix}_consumed", phase="execution", metadata={
                        "status": "fallback", "error": str(exc)[:200],
                    })
                self._trace.emit("graph_wait_finished", phase="execution", metadata={
                    "lane": lane, "status": "error",
                })
                ff_meta: dict[str, Any] = {
                    "lane": lane,
                    "error_category": type(exc).__name__,
                    "hashed_planned_identity": stable_hash(planned_identity or ""),
                    "terminal_outcome": "fallback_future_error",
                }
                if not skip_loader_class:
                    ff_meta["loader_class"] = loader_class
                self._trace.emit("future_failed", phase="execution", metadata=ff_meta)
                self._trace.emit("original_loader_fallback", phase="execution", metadata={
                    "lane": lane, "reason": "future_error",
                })
                # ── Canonical consumer end (error) ──
                self._trace.emit("graph_wait_end", phase="execution", metadata={
                    "lane": lane, "status": "error",
                })
            return _LOADER_MISS
        if result is None:
            if self._trace:
                self._trace.emit(f"graph_{diagnostics_prefix}_wait_end", phase="execution",
                                 metadata={"status": "unavailable"})
                self._trace.emit("graph_wait_finished", phase="execution", metadata={
                    "lane": lane, "status": "unavailable",
                })
                fu_meta: dict[str, Any] = {
                    "lane": lane,
                    "hashed_planned_identity": stable_hash(planned_identity or ""),
                    "terminal_outcome": "fallback_unavailable",
                }
                if not skip_loader_class:
                    fu_meta["loader_class"] = loader_class
                self._trace.emit("future_unavailable", phase="execution", metadata=fu_meta)
                self._trace.emit("original_loader_fallback", phase="execution", metadata={
                    "lane": lane, "reason": "result_none",
                })
                # ── Canonical consumer end (unavailable) ──
                self._trace.emit("graph_wait_end", phase="execution", metadata={
                    "lane": lane, "status": "unavailable",
                })
            return _LOADER_MISS
        # ── Phase 1A candidate: join the early retained-UNET activation at
        # graph/sampler demand (OUTSIDE the mutation lane) and validate
        # diffusion identity / residency / cache / dtype / device.  Phase 0
        # control flow is preserved: the retained UNET is still returned and
        # the original sampler load path continues as a cache validation.  A
        # non-ready terminal outcome elects the unchanged late fallback
        # exactly once (atomic, never overwritten).  Late mode remains gated
        # except for a pending exact-cache-hit activation.
        if lane == "UNET" and result is not None:
            _request_trace = self._trace or _ACTIVE_REQUEST_TRACE.get()
            _request_id = str(_request_trace.request_id) if _request_trace is not None else ""
            if (
                unet_activation_mode() in _UNET_ACTIVATION_MODE_ACTIVE
                or _unet_cache_hit_activation_pending(_request_id)
            ):
                self._join_unet_early_activation(result, trace=self._trace)
        if self._trace:
            self._trace.emit(f"graph_{diagnostics_prefix}_wait_end", phase="execution",
                             metadata={"status": "ok"})
            self._trace.emit(f"graph_{diagnostics_prefix}_consumed", phase="execution",
                             metadata={"status": "prepared"})
            self._trace.emit("graph_wait_finished", phase="execution", metadata={
                "lane": lane, "status": "ok",
            })
            # ── Canonical consumer end (success) ──
            self._trace.emit("graph_wait_end", phase="execution", metadata={
                "lane": lane, "status": "ok",
            })
            completed_before = getattr(
                preparation.diagnostics, f"{diagnostics_prefix}_work_completed_before_demand_ms", 0.0
            )
            graph_wait_ms = getattr(
                preparation.diagnostics, f"{diagnostics_prefix}_actual_graph_wait_ms", 0.0
            )
            self._trace.emit(
                "prepared_result_consumed",
                phase="execution",
                metadata={
                    "lane": lane,
                    "loader_class": loader_class,
                    "hashed_planned_identity": stable_hash(planned_identity),
                    "terminal_outcome": "prepared",
                    "completed_before_demand_ms": round(completed_before, 3),
                    "graph_wait_duration_ms": round(graph_wait_ms, 3),
                },
            )
        return (result,)

    def _consume_prefill(self, args: tuple[Any, ...], kwargs: Mapping[str, Any]) -> Any:
        preparation = self._preparation
        # Extract clip/text early so hashed_requested_identity is available
        # for every terminal event without changing preload behavior.
        clip = kwargs.get("clip", args[0] if args else None)
        text = str(kwargs.get("text", args[1] if len(args) > 1 else ""))

        # --- Missing spec check ---
        if preparation is None or self._prefill_key is None or not self._prefill_key.prompt_bundle_hash:
            if self._trace:
                self._trace.emit(
                    "request_spec_missing",
                    phase="execution",
                    metadata={
                        "lane": "prefill",
                        "loader_class": "CLIPTextEncode",
                        "hashed_requested_identity": stable_hash(text) if text else "",
                        "terminal_outcome": "fallback_missing_spec",
                    },
                )
                self._trace.emit("original_loader_fallback", phase="execution", metadata={
                    "lane": "prefill", "reason": "missing_spec",
                })
            return _LOADER_MISS

        if clip is None or not text:
            if self._trace:
                self._trace.emit(
                    "request_spec_missing",
                    phase="execution",
                    metadata={
                        "lane": "prefill",
                        "loader_class": "CLIPTextEncode",
                        "hashed_requested_identity": stable_hash(text) if text else "",
                        "terminal_outcome": "fallback_missing_spec",
                        "reason": "clip_or_text_missing",
                    },
                )
                self._trace.emit("original_loader_fallback", phase="execution", metadata={
                    "lane": "prefill", "reason": "clip_or_text_missing",
                })
            return _LOADER_MISS

        # ── Phase B: one reconciliation record per request ──────────
        # Emitted exactly once (per bridge/request) at the first terminal
        # demand outcome: the prefetched result consumed or fallen back.
        def _emit_reconciliation(outcome: str) -> None:
            if self._reconciliation_emitted:
                return
            with self._prefill_lock:
                if self._reconciliation_emitted:
                    return
                emit_clip_prefill_reconciliation(
                    self._trace,
                    outcome=outcome,
                    request_id=str(self._trace.request_id) if self._trace is not None else "",
                )
                self._reconciliation_emitted = True

        # --- Graph demand and wait ---
        if self._trace:
            self._trace.emit("graph_prefill_demand", phase="execution", metadata={
                "text_length": len(text),
                "lane": "prefill",
                "loader_class": "CLIPTextEncode",
            })
            self._trace.emit("graph_model_demand", phase="execution", metadata={
                "lane": "prefill",
                "loader_class": "CLIPTextEncode",
            })
            self._trace.emit("graph_prefill_wait_start", phase="execution")
            self._trace.emit("graph_wait_started", phase="execution", metadata={"lane": "prefill"})
            # ── Canonical consumer events (Phase 0, additive) ──
            self._trace.emit("graph_demand", phase="execution", metadata={
                "lane": "prefill", "loader_class": "CLIPTextEncode",
            })
            self._trace.emit("graph_wait_start", phase="execution", metadata={"lane": "prefill"})
        try:
            cache_key = (id(clip), text)
            with self._prefill_lock:
                result = self._prefill_results.get(cache_key, _LOADER_MISS)
            if result is _LOADER_MISS:
                # Never hold the cache lock while waiting for the restore
                # future. This keeps parallel CLIPTextEncode nodes from
                # deadlocking and makes the blocking interval measurable.
                values = self.coordinator.wait_prefill(preparation)
                with self._prefill_lock:
                    if isinstance(values, Mapping):
                        self._prefill_results.update(values)
                    result = self._prefill_results.get(cache_key, _LOADER_MISS)
        except Exception as exc:
            if self._trace:
                self._trace.emit("graph_prefill_wait_end", phase="execution", metadata={"status": "error"})
                self._trace.emit("graph_prefill_consumed", phase="execution", metadata={
                    "status": "fallback", "error": str(exc)[:200],
                })
                self._trace.emit("graph_wait_finished", phase="execution", metadata={
                    "lane": "prefill", "status": "error",
                })
                self._trace.emit(
                    "future_failed",
                    phase="execution",
                    metadata={
                        "lane": "prefill",
                        "loader_class": "CLIPTextEncode",
                        "hashed_requested_identity": stable_hash(text),
                        "error_category": type(exc).__name__,
                        "terminal_outcome": "fallback_future_error",
                    },
                )
                self._trace.emit("original_loader_fallback", phase="execution", metadata={
                    "lane": "prefill", "reason": "future_error",
                })
                # ── Canonical consumer end (error) ──
                self._trace.emit("graph_wait_end", phase="execution", metadata={
                    "lane": "prefill", "status": "error",
                })
            _emit_reconciliation("fallback_error")
            return _LOADER_MISS
        if result is _LOADER_MISS:
            if self._trace:
                self._trace.emit("graph_prefill_wait_end", phase="execution", metadata={"status": "unavailable"})
                self._trace.emit("graph_wait_finished", phase="execution", metadata={
                    "lane": "prefill", "status": "unavailable",
                })
                self._trace.emit(
                    "future_unavailable",
                    phase="execution",
                    metadata={
                        "lane": "prefill",
                        "loader_class": "CLIPTextEncode",
                        "hashed_requested_identity": stable_hash(text),
                        "terminal_outcome": "fallback_unavailable",
                    },
                )
                self._trace.emit("original_loader_fallback", phase="execution", metadata={
                    "lane": "prefill", "reason": "future_unavailable",
                })
                # ── Canonical consumer end (unavailable) ──
                self._trace.emit("graph_wait_end", phase="execution", metadata={
                    "lane": "prefill", "status": "unavailable",
                })
            _emit_reconciliation("fallback_unavailable")
            return _LOADER_MISS
        if self._trace:
            self._trace.emit("graph_prefill_wait_end", phase="execution", metadata={"status": "ok"})
            self._trace.emit("graph_prefill_consumed", phase="execution", metadata={"status": "prepared"})
            self._trace.emit("graph_wait_finished", phase="execution", metadata={
                "lane": "prefill", "status": "ok",
            })
            # ── Canonical consumer end (success) ──
            self._trace.emit("graph_wait_end", phase="execution", metadata={
                "lane": "prefill", "status": "ok",
            })
            completed_before = getattr(
                preparation.diagnostics, "prefill_work_completed_before_demand_ms", None
            )
            graph_wait_ms = getattr(
                preparation.diagnostics, "prefill_actual_graph_wait_ms", None
            )
            self._trace.emit(
                "prepared_result_consumed",
                phase="execution",
                metadata={
                    "lane": "prefill",
                    "loader_class": "CLIPTextEncode",
                    "hashed_requested_identity": stable_hash(text),
                    "terminal_outcome": "prepared",
                    "completed_before_demand_ms": round(completed_before, 3) if completed_before is not None else None,
                    "graph_wait_duration_ms": round(graph_wait_ms, 3) if graph_wait_ms is not None else None,
                },
            )
        _emit_reconciliation("consumed")
        return result

    def _invoke_original(self, class_name: str, kwargs: Mapping[str, Any]) -> Any:
        method_name = self._NODE_METHODS[class_name]
        method = self._original_methods.get(f"{class_name}.{method_name}")
        node_class = self._node_classes.get(class_name)
        if not callable(method) or node_class is None:
            if self._trace:
                self._trace.emit("loader_invoke_error", phase="restore", metadata={
                    "lane": class_name,
                    "error": "original_unavailable",
                })
            raise RuntimeError(f"original ComfyUI loader is unavailable: {class_name}.{method_name}")
        _invoke_lane = class_name
        _start_ns = time.monotonic_ns()
        if self._trace:
            self._trace.emit("loader_invoke_start", phase="restore", metadata={
                "lane": _invoke_lane,
                "loader_class": class_name,
            })
        try:
            result = method(node_class(), **dict(kwargs))
            _dur_ms = round((time.monotonic_ns() - _start_ns) / 1_000_000, 3)
            if self._trace:
                self._trace.emit("loader_invoke_end", phase="restore", metadata={
                    "lane": _invoke_lane,
                    "loader_class": class_name,
                    "duration_ms": _dur_ms,
                })
            return result
        except Exception as exc:
            _dur_ms = round((time.monotonic_ns() - _start_ns) / 1_000_000, 3)
            if self._trace:
                self._trace.emit("loader_invoke_error", phase="restore", metadata={
                    "lane": _invoke_lane,
                    "loader_class": class_name,
                    "duration_ms": _dur_ms,
                    "error": str(exc)[:200],
                })
            raise


# ═══════════════════════════════════════════════════════════════════════
# Phase 1A candidate: early retained-UNET activation
# (COMFYMODAL_V2_UNET_ACTIVATION_MODE)
# ═══════════════════════════════════════════════════════════════════════
# Mode "late" (default) preserves Phase 0 behavior exactly: the retained
# UNET is returned at graph/sampler demand and loaded on the critical path.
# The ONLY allowed opt-in values are exactly "clip_encode_start" (the
# original candidate) and "clip_gpu_ready" (V2-only timing candidate) — the
# historical "early" spelling and any other value normalize to "late" so no
# candidate path can activate for them.  In "clip_encode_start" mode the
# retained UNET GPU activation is scheduled once, through the existing
# coordinator pool, at the real execution-prefill CLIP callback boundary
# (immediately before the actual prefill encode) AFTER every eligibility
# condition is proven (execution-prefill caller, mode, production
# CPU-snapshot request marker, exact retained snapshot→bridge identity
# chain, completed retained-UNET future, no same-request/key future, live
# CUDA validity, and safe VRAM for the exact active CLIP + retained UNET).
# The early load overlaps the CLIP encode; the graph demand then joins the
# same future outside the mutation lane and the original sampler load path
# continues as a cache validation.  Any skip/failure/cancellation/invalid
# outcome is made terminal before exactly one caller elects the unchanged
# late fallback.
#
# "clip_gpu_ready" runs the SAME eligibility/identity/VRAM proofs at the
# same pre-encode boundary but only ARMS a request-scoped single-use
# trigger there (no submit).  The retained-UNET activation is scheduled
# exactly once by the existing GPU loader wrapper hook AFTER the first
# qualifying successful CLIP load_models_gpu call from the real prefill
# encode returns and the mutation lane is released (marker order:
# clip_gpu_load_end <= unet_activation_scheduled <=
# unet_activation_load_start < clip_encode_end).

_EVENT_UNET_EA_MODE = "unet_early_activation_mode"
_EVENT_UNET_EA_ELIGIBLE = "unet_early_activation_eligible"
_EVENT_UNET_EA_SCHEDULED = "unet_early_activation_scheduled"
_EVENT_UNET_EA_WORKER_START = "unet_early_activation_worker_start"
_EVENT_UNET_EA_LANE_WAIT_START = "unet_early_activation_lane_wait_start"
_EVENT_UNET_EA_LANE_ACQUIRED = "unet_early_activation_lane_acquired"
_EVENT_UNET_EA_LOAD_START = "unet_early_activation_load_start"
_EVENT_UNET_EA_LOAD_END = "unet_early_activation_load_end"
_EVENT_UNET_EA_COMPLETED = "unet_early_activation_completed"
_EVENT_UNET_EA_SKIPPED = "unet_early_activation_skipped"
_EVENT_UNET_EA_FAILED = "unet_early_activation_failed"
_EVENT_UNET_EA_INVALID = "unet_early_activation_invalid"
_EVENT_UNET_EA_CANCELLED = "unet_early_activation_cancelled"
_EVENT_UNET_EA_GRAPH_DEMAND = "unet_early_activation_graph_demand"
_EVENT_UNET_EA_GRAPH_JOIN_START = "unet_early_activation_graph_join_start"
_EVENT_UNET_EA_GRAPH_JOIN_END = "unet_early_activation_graph_join_end"
_EVENT_UNET_EA_CONSUMED = "unet_early_activation_consumed"
_EVENT_UNET_EA_TERMINAL = "unet_early_activation_terminal"
_EVENT_UNET_EA_FALLBACK = "unet_early_activation_fallback"
_EVENT_UNET_EA_RECONCILIATION = "unet_early_activation_reconciliation"

# ── Concise clip_gpu_ready timing markers ────────────────────────────────
# Required monotonic order (clip_gpu_ready mode only):
#   clip_gpu_load_end <= unet_activation_scheduled <=
#   unet_activation_load_start < clip_encode_end
_EVENT_CLIP_GPU_LOAD_END = "clip_gpu_load_end"
_EVENT_CLIP_GPU_RESIDENT = "clip_gpu_resident"
# Distinct skip event for failed/unsupported residency proof — only a
# PROVEN residency ever emits ``clip_gpu_resident``.
_EVENT_CLIP_GPU_RESIDENCY_SKIP = "clip_gpu_residency_skip"
_EVENT_UNET_ACTIVATION_SCHEDULED = "unet_activation_scheduled"
_EVENT_UNET_ACTIVATION_LOAD_START = "unet_activation_load_start"
_EVENT_CLIP_ENCODE_END = "clip_encode_end"

_UNET_ACTIVATION_MODE_LATE = "late"
_UNET_ACTIVATION_MODE_CLIP_ENCODE_START = "clip_encode_start"
_UNET_ACTIVATION_MODE_CLIP_GPU_READY = "clip_gpu_ready"
_UNET_ACTIVATION_TRIGGER_CACHE_HIT = "conditioning_cache_hit"
# Legacy documented opt-in set (kept for the existing activation tests).
# ``clip_gpu_ready`` is accepted by ``_resolve_unet_activation_mode``
# explicitly below.
_UNET_ACTIVATION_MODE_VALID = frozenset(
    {_UNET_ACTIVATION_MODE_LATE, _UNET_ACTIVATION_MODE_CLIP_ENCODE_START}
)
# Modes that schedule/join the retained-UNET activation future.  Late mode
# is NOT included — it must never create state, join, or add graph waits.
_UNET_ACTIVATION_MODE_ACTIVE = frozenset(
    {_UNET_ACTIVATION_MODE_CLIP_ENCODE_START, _UNET_ACTIVATION_MODE_CLIP_GPU_READY}
)

# Bounded safety margin for the early-activation VRAM pre-check.  The margin
# is never allowed to leave the [min, max] band (never grows with model size).
_EARLY_ACTIVATION_MARGIN_MIN_BYTES = 256 * 1024 * 1024
_EARLY_ACTIVATION_MARGIN_MAX_BYTES = 2 * 1024 * 1024 * 1024
_EARLY_ACTIVATION_MARGIN_RATIO = 0.1


def _resolve_unet_activation_mode(raw: str) -> str:
    """Normalize a ``COMFYMODAL_V2_UNET_ACTIVATION_MODE`` value.

    The ONLY allowed opt-in values are exactly ``"clip_encode_start"`` (the
    original candidate) and ``"clip_gpu_ready"`` (V2-only timing candidate).
    ``"late"`` is the default.  Any other value — including the historical
    ``"early"`` spelling — and the default fall back to ``"late"`` so Phase 0
    behavior is never altered by a typo or an unknown value, and no candidate
    path can activate for ``early``.
    """
    value = str(raw or "").strip().lower()
    if value == _UNET_ACTIVATION_MODE_CLIP_ENCODE_START:
        return _UNET_ACTIVATION_MODE_CLIP_ENCODE_START
    if value == _UNET_ACTIVATION_MODE_CLIP_GPU_READY:
        return _UNET_ACTIVATION_MODE_CLIP_GPU_READY
    if value == _UNET_ACTIVATION_MODE_LATE:
        return _UNET_ACTIVATION_MODE_LATE
    return _UNET_ACTIVATION_MODE_LATE


_UNET_ACTIVATION_MODE: str = _resolve_unet_activation_mode(
    os.environ.get("COMFYMODAL_V2_UNET_ACTIVATION_MODE", _UNET_ACTIVATION_MODE_LATE)
)
_UNET_ACTIVATION_MODE_LOG_EMITTED: bool = False


def unet_activation_mode() -> str:
    """Return the effective UNET activation mode.

    ``"late"`` (default) preserves Phase 0 behavior exactly; the allowed
    opt-in values are ``"clip_encode_start"`` (original candidate) and
    ``"clip_gpu_ready"`` (V2-only timing candidate).  Logs the parsed
    effective mode once per process on first access.
    """
    global _UNET_ACTIVATION_MODE_LOG_EMITTED
    if not _UNET_ACTIVATION_MODE_LOG_EMITTED:
        _UNET_ACTIVATION_MODE_LOG_EMITTED = True
        try:
            print(
                f"[v2.unet_early_activation] event=mode "
                f"mode={_UNET_ACTIVATION_MODE} "
                f"env_raw={os.environ.get('COMFYMODAL_V2_UNET_ACTIVATION_MODE', 'late')} "
                f"restored_instance_id={_LATEST_RESTORED_INSTANCE_ID or 'absent'} "
                f"restore_session_id={_LATEST_RESTORE_SESSION_ID or 'absent'}",
                flush=True,
            )
        except Exception:
            pass
    return _UNET_ACTIVATION_MODE


# ── Request-scoped activation state ─────────────────────────────────────
# One dict per request_id: future / key / trigger / owner / terminal / error
# plus diagnostics.  Bounded (oldest request ids are evicted first) and
# never persisted across restored containers — the key never contains the
# restored identity and the state is dropped by request-end cleanup.

_UNET_ACTIVATION_STATE: dict[str, dict[str, Any]] = {}
_UNET_ACTIVATION_LOCK: RLock = RLock()
_UNET_ACTIVATION_MAX = 128


def _unet_activation_new_state(request_id: str) -> dict[str, Any]:
    return {
        "request_id": request_id,
        "future": None,
        "owner": "clip_encode_start",
        "trigger": "",
        "key": {},
        "key_hash": "",
        "mode": _UNET_ACTIVATION_MODE,
        "status": "idle",
        "terminal": False,
        "cancelled": False,
        "fallback_elected": False,
        "fallback_reason": "",
        "reason": "",
        "error": "",
        "transfer_count": 0,
        "eligible": False,
        "eligibility_reason": "",
        "clip_encode_entries": 0,
        "clip_object_id": "",
        # ── clip_gpu_ready single-use trigger state ───────────────────
        # ``armed`` — a request-scoped single-use trigger has been armed at
        # the pre-encode boundary (eligibility proven, nothing scheduled).
        # ``fired`` — the armed trigger has been claimed exactly once by the
        # GPU loader wrapper hook (armed->scheduled claim is atomic under
        # ``_UNET_ACTIVATION_LOCK``).  ``clip_patcher_object_id`` is the
        # exact armed CLIP patcher identity the firing load must match.
        # The fire-time scheduling references (bridge/prep/model_key/clip/
        # trace) are held only for the lifetime of the request state and are
        # dropped by the existing finalize path — no leaked refs.
        "armed": False,
        "fired": False,
        "clip_patcher_object_id": "",
        "bridge": None,
        "prep": None,
        "model_key": None,
        "clip": None,
        "trace": None,
        "clip_encode_start_mono_ns": 0,
        "clip_encode_end_mono_ns": 0,
        "clip_encode_wall_ms": 0.0,
        "clip_encode_process_cpu_ms": 0.0,
        "clip_encode_thread_cpu_ms": 0.0,
        "submitted_mono_ns": 0,
        "worker_started_mono_ns": 0,
        "terminal_mono_ns": 0,
        "join_demand_mono_ns": 0,
        "join_completed_mono_ns": 0,
        "join_wait_ms": 0.0,
        "lane_wait_ms": 0.0,
        "load_wall_ms": 0.0,
        "load_thread_cpu_ms": None,
        "load_process_cpu_ms": None,
        "gpu_free_bytes": None,
        "gpu_required_bytes": None,
        "safety_margin_bytes": None,
        "gpu_allocated_before": None,
        "gpu_allocated_after": None,
        "gpu_allocated_delta_bytes": None,
        "unet_patcher_object_id": "",
        "unet_diffusion_object_id": "",
        "sampler_patcher_object_id": "",
        "unet_identity_hash": "",
        "clip_retained": False,
        "clip_resident": False,
        "clip_residency_status": "",
        "cache_present": False,
        "diagnostics": {},
    }


def _unet_activation_get(request_id: str) -> dict[str, Any] | None:
    """Return the activation state dict for *request_id* (live reference)."""
    if not request_id:
        return None
    with _UNET_ACTIVATION_LOCK:
        return _UNET_ACTIVATION_STATE.get(request_id)


def _unet_cache_hit_activation_pending(request_id: str) -> bool:
    if not request_id:
        return False
    with _UNET_ACTIVATION_LOCK:
        state = _UNET_ACTIVATION_STATE.get(request_id)
        return bool(
            state is not None
            and state.get("trigger") == _UNET_ACTIVATION_TRIGGER_CACHE_HIT
            and state.get("future") is not None
        )


def _unet_activation_trim() -> None:
    """Evict the OLDEST request ids when the bound is exceeded."""
    with _UNET_ACTIVATION_LOCK:
        if len(_UNET_ACTIVATION_STATE) > _UNET_ACTIVATION_MAX:
            _excess = len(_UNET_ACTIVATION_STATE) - _UNET_ACTIVATION_MAX
            for _stale in list(_UNET_ACTIVATION_STATE.keys())[:_excess]:
                _UNET_ACTIVATION_STATE.pop(_stale, None)


# ── Eligibility proofs (Hard Correction 2) ───────────────────────────────
# Every proof uses existing APIs/state only: the production CPU-snapshot
# request marker, the retained-UNET identity chain recorded during restore
# (``record_retained_unet_identity``), the completed snapshot future, the
# request-scoped activation state, live CUDA validity, and the live VRAM
# helper.  No GPU snapshots and no page-readiness machinery are used.


def _prove_execution_prefill_caller(caller: str) -> tuple[bool, str]:
    """Prove the call originates from the execution-prefill boundary.

    ``clip_encode_start`` is integrated ONLY from the existing
    ``_execution_prefill`` callback (submitted as ``execution_prefill`` lane
    work through the coordinator pool).  When a lane context is visible it
    must be the ``prefill`` lane — a call made from a restore-time
    UNET/CLIP/VAE worker or any other lane fails closed.
    """
    if caller != "execution_prefill":
        return False, "caller_not_execution_prefill"
    lane = _ACTIVE_LANE_TRACE.get()
    if lane is not None and getattr(lane, "_lane", "") != "prefill":
        return False, "caller_lane_not_prefill"
    return True, "ok"


def _prove_unet_identity_chain(request_id: str, unet: Any) -> tuple[bool, str]:
    """Prove the exact retained snapshot→bridge UNET identity chain exists.

    Reuses the existing per-request identity chain recorded by
    ``record_retained_unet_identity`` at restore/request-time activation
    (stages ``snapshot`` and ``bridge``).  For the request chain BOTH the
    snapshot and bridge entries must be present and nonzero, the snapshot
    object id must EQUAL the bridge object id (exact identity equality, not
    mere key presence), and the resolved retained UNET object id must match
    that exact bridge id.  Any missing / mismatched link fails closed.
    Never invents a second registry.
    """
    if not request_id:
        return False, "identity_chain_incomplete"
    with _SNAPSHOT_UNET_CHAIN_LOCK:
        chain = dict(_SNAPSHOT_UNET_CHAIN.get(request_id, {}))
    snap_id = int(chain.get("snapshot", 0) or 0)
    bridge_id = int(chain.get("bridge", 0) or 0)
    if not snap_id or not bridge_id:
        return False, "identity_chain_incomplete"
    if snap_id != bridge_id:
        return False, "snapshot_bridge_identity_mismatch"
    obj_id, _dm = _resolve_logical_unet_identity(unet)
    if obj_id != bridge_id:
        return False, "bridge_unet_identity_mismatch"
    return True, "ok"


def _cuda_environment_valid() -> tuple[bool, str]:
    """Prove the live CUDA environment can perform the GPU activation.

    Requires torch CUDA availability AND a resolvable ComfyUI torch device.
    Never mutates CUDA state.
    """
    try:
        import torch as _torch_cuda
        if not _torch_cuda.cuda.is_available():
            return False, "cuda_unavailable"
        import comfy.model_management as _mm_cuda
        _dev = _mm_cuda.get_torch_device()
        if _dev is None:
            return False, "torch_device_unavailable"
        return True, "ok"
    except Exception as exc:
        return False, f"cuda_probe_error:{type(exc).__name__}"


def _resolve_clip_patcher(clip: Any) -> Any:
    """Return the exact active CLIP patcher object from a CLIP wrapper."""
    if clip is None:
        return None
    _patcher = getattr(clip, "patcher", None)
    if _patcher is None:
        _patcher = getattr(clip, "model", None)
    return _patcher


def _prove_unet_early_activation_eligible(
    bridge: "V2LoaderBridge",
    *,
    request_id: str,
    clip: Any,
    mode: str,
    trigger: str = "clip_encode_start",
) -> tuple[bool, str, dict[str, Any]]:
    """Prove every eligibility condition at the real prefill boundary.

    Returns ``(eligible, reason, evidence)``.  When any proof cannot be made
    the caller MUST emit ``unet_early_activation_eligible`` false and
    ``unet_early_activation_skipped`` with the exact reason and must NOT
    schedule.  Evidence carries the per-condition booleans plus the VRAM
    free/required/margin numbers so the skipped/eligible markers are
    self-contained.  *trigger* names the scheduling mode
    (``"clip_encode_start"`` / ``"clip_gpu_ready"``) for the evidence.
    """
    evidence: dict[str, Any] = {
        "mode": mode,
        "trigger": trigger,
        "request_id": request_id,
        "caller_execution_prefill": False,
        "cpu_snapshot_mode_active": False,
        "identity_chain_proven": False,
        "unet_available": False,
        "no_existing_future": True,
        "cuda_valid": False,
        "vram_safe": False,
        "free_bytes": None,
        "required_bytes": None,
        "margin_bytes": None,
        "clip_retained": False,
        "restored_instance_id": _LATEST_RESTORED_INSTANCE_ID,
        "restore_session_id": _LATEST_RESTORE_SESSION_ID,
    }
    _ok, _reason = _prove_execution_prefill_caller("execution_prefill")
    if not _ok:
        return False, _reason, evidence
    evidence["caller_execution_prefill"] = True

    if not request_id or not is_production_cpu_snapshot_request(request_id):
        return False, "cpu_snapshot_mode_inactive", evidence
    evidence["cpu_snapshot_mode_active"] = True

    prep = getattr(bridge, "_preparation", None)
    model_key = getattr(bridge, "_model_key", None)
    if prep is None or model_key is None:
        return False, "preparation_unavailable", evidence
    if prep.unet_future is None:
        return False, "unet_future_absent", evidence

    # Exact retained snapshot and bridge UNET identities must match.
    # A completed snapshot future is expected for the candidate; the exact
    # retained UNET is required before scheduling so the identity key can be
    # built with REAL patcher/diffusion ids (never blank placeholders).
    if not prep.unet_future.done():
        return False, "unet_future_pending", evidence
    try:
        unet = prep.unet_future.result()
    except Exception:
        return False, "unet_future_failed", evidence
    if unet is None:
        return False, "no_retained_unet", evidence
    evidence["unet_available"] = True
    _ok, _reason = _prove_unet_identity_chain(request_id, unet)
    if not _ok:
        return False, _reason, evidence
    evidence["identity_chain_proven"] = True

    # No same-request/key future may already exist.
    with _UNET_ACTIVATION_LOCK:
        _existing = _UNET_ACTIVATION_STATE.get(request_id)
    if _existing is not None and _existing.get("future") is not None:
        return False, "future_already_scheduled", evidence
    evidence["no_existing_future"] = True

    # CUDA must be valid.
    _ok, _reason = _cuda_environment_valid()
    if not _ok:
        return False, _reason, evidence
    evidence["cuda_valid"] = True

    # Safe VRAM must retain the exact active CLIP plus the retained UNET.
    _load_models: list[Any] = [unet]
    _clip_patcher = _resolve_clip_patcher(clip)
    if _clip_patcher is not None and _clip_patcher is not unet:
        _load_models.append(_clip_patcher)
    _vram = _check_early_activation_vram(_load_models)
    evidence["free_bytes"] = _vram.get("free_bytes")
    evidence["required_bytes"] = _vram.get("required_bytes")
    evidence["margin_bytes"] = _vram.get("margin_bytes")
    evidence["clip_retained"] = bool(_vram.get("clip_retained", False))
    if not _vram.get("ok"):
        return False, str(_vram.get("reason", "vram_insufficient")), evidence
    evidence["vram_safe"] = True
    return True, "ok", evidence


# ── Identity key ─────────────────────────────────────────────────────────


def _unet_activation_modal_hashes() -> dict[str, str]:
    """Best-effort workflow / custom-node / deployment hashes.

    Reads live module state only (never triggers an import) so the key can
    cover deployment identity without coupling model_preload to modal_app.
    """
    result: dict[str, str] = {}
    try:
        import sys as _sys_ma
        _ma = _sys_ma.modules.get("comfymodal_runtime.modal_app")
        if _ma is not None:
            _wf = getattr(_ma, "_V2_WORKFLOW_HASH", None)
            if _wf is not None:
                result["workflow_hash"] = str(_wf.get() or "")
            result["deployment_hash"] = str(
                getattr(_ma, "_V2_DEPLOYMENT_COMBINED_HASH", "") or ""
            )
            _seed = getattr(_ma, "_LATEST_SNAPSHOT_EXECUTION_SEED", None)
            if _seed is not None:
                result["custom_node_generation"] = str(
                    getattr(_seed, "custom_node_generation", "") or ""
                )
    except Exception:
        pass
    return result


def _unet_requested_weight_dtype(bridge: "V2LoaderBridge", model_key: Any) -> str:
    try:
        _req = bridge._find_request("unet", model_key.unet_identity)
        if isinstance(_req, Mapping):
            return str(_req.get("weight_dtype", "") or "")
    except Exception:
        pass
    return ""


def _build_unet_activation_key(
    *,
    mode: str,
    model_key: ModelRestoreKey | None,
    request_id: str,
    unet: Any = None,
    weight_dtype: str = "",
) -> tuple[dict[str, Any], str]:
    """Build the request-scoped identity key for the early activation.

    Covers the underlying diffusion identity, the retained patcher identity,
    workflow/custom-node/deployment hashes (when available), the weight and
    compute dtype, the device, and the mode.  Returns
    ``(components, key_hash)``.
    """
    from .unet_forward_probe import resolve_diffusion_model

    _patcher_id = ""
    _dm_id = ""
    _dm_device = ""
    _compute_dtype = ""
    if unet is not None:
        try:
            _patcher_id = str(id(unet))
        except Exception:
            pass
        try:
            _patcher, _dm = resolve_diffusion_model(unet)
            if _dm is not None:
                _dm_id = str(id(_dm))
                _dm_device = str(getattr(_dm, "current_device", "") or "")
        except Exception:
            pass
        try:
            _md = getattr(unet, "model_dtype", None)
            _compute_dtype = str(_md()) if callable(_md) else ""
        except Exception:
            pass
    _modal = _unet_activation_modal_hashes()
    _device = _dm_device
    if not _device:
        try:
            _dev = getattr(unet, "load_device", None)
            if _dev is not None:
                _device = str(_dev)
        except Exception:
            pass
    if not _device:
        try:
            import comfy.model_management as _mm_ea
            _device = str(_mm_ea.get_torch_device())
        except Exception:
            _device = ""
    components = {
        "mode": mode,
        "request_id": request_id,
        "unet_identity": str(model_key.unet_identity) if model_key is not None else "",
        "unet_patcher_object_id": _patcher_id,
        "unet_diffusion_object_id": _dm_id,
        "workflow_hash": _modal.get("workflow_hash", ""),
        "custom_node_generation": _modal.get("custom_node_generation", ""),
        "deployment_hash": _modal.get("deployment_hash", ""),
        "weight_dtype": weight_dtype,
        "compute_dtype": _compute_dtype,
        "device": _device,
    }
    key_hash = stable_hash(components)[:24]
    return components, key_hash


# ── Live ComfyUI model-management indirections (patchable in tests) ────


def _mm_load_models_gpu(models: list[Any], **kwargs: Any) -> Any:
    """Call the live ComfyUI ``load_models_gpu`` (the original load path)."""
    import comfy.model_management as _mm
    return _mm.load_models_gpu(models, **kwargs)


def _prepare_armed_clip_for_force_load(
    models: list[Any], request_trace: Any,
) -> None:
    """Clear stale state before the V2 prefill CLIP force-load.

    ComfyUI's ``force_full_load`` flag bypasses the low-VRAM sizing branch,
    but ``ModelPatcher.partially_load`` still returns early when its internal
    ``model_loaded_weight_memory`` says the full model is loaded.  A restored
    CLIP can therefore be physically off-device while the patcher metadata
    claims it is resident.  Only the exact request-armed CLIP patcher is
    normalized, and only when the strict read-only proof rejects it.  The
    caller invokes this while the existing GPU mutation lane is held; the
    actual transfer remains the normal wrapped ``load_models_gpu`` path.
    """
    _request_id = str(getattr(request_trace, "request_id", "") or "")
    if not _request_id:
        return
    with _UNET_ACTIVATION_LOCK:
        _state = _UNET_ACTIVATION_STATE.get(_request_id)
        if _state is None or not _state.get("armed", False):
            return
        _armed_id = str(_state.get("clip_patcher_object_id", "") or "")
    if not _armed_id:
        return

    _exact = None
    for _model in models:
        try:
            if str(id(_model)) == _armed_id:
                _exact = _model
                break
            _resolved = _resolve_clip_patcher(_model)
            if _resolved is not None and str(id(_resolved)) == _armed_id:
                _exact = _resolved
                break
        except Exception:
            continue
    if _exact is None:
        return

    _before = _probe_clip_full_cuda_residency(_exact)
    if _before.get("ok", False):
        return

    _unpatch = getattr(_exact, "unpatch_model", None)
    if not callable(_unpatch):
        return
    _offload = getattr(_exact, "offload_device", None)
    _reset_error = ""
    try:
        if _offload is None:
            _unpatch()
        else:
            _unpatch(_offload)
    except TypeError:
        try:
            _unpatch(_offload, unpatch_weights=True)
        except Exception as _exc:
            _reset_error = str(_exc)[:200]
    except Exception as _exc:
        _reset_error = str(_exc)[:200]

    _after_reset = _probe_clip_full_cuda_residency(_exact)
    _direct_model_load = False
    _direct_model_load_error = ""
    # Some restored CLIP patchers retain the stale state across unpatching,
    # or their normal ``load_models_gpu`` call re-enters the stale-state
    # branch.  In that case invoke the exact patcher's own full-load methods
    # while the mutation lane is held.  This is still ComfyUI's model-patcher
    # loading path, but avoids the second metadata-driven early return.
    if not _after_reset.get("ok", False):
        try:
            _load_device = getattr(_exact, "load_device", None)
            _patch_model = getattr(_exact, "patch_model", None)
            _load = getattr(_exact, "load", None)
            if (
                callable(_patch_model)
                and callable(_load)
                and _normalize_cuda_device_key(_load_device) is not None
            ):
                _patch_model(load_weights=False)
                _load(
                    device_to=_load_device,
                    lowvram_model_memory=0,
                    full_load=True,
                )
                _sync_clip_load_device(_exact)
                _direct_model_load = True
        except Exception as _exc:
            _direct_model_load_error = str(_exc)[:200]
    _after_prepare = _probe_clip_full_cuda_residency(_exact)

    if request_trace is not None:
        request_trace.emit(
            "clip_gpu_ready_force_load_reset",
            phase="execution",
            metadata={
                "request_id": _request_id,
                "clip_patcher_object_id": _armed_id,
                "reason": _before.get("reason", "residency_not_proven"),
                "reset_error": _reset_error,
                "direct_model_load": _direct_model_load,
                "direct_model_load_error": _direct_model_load_error,
                "evidence": _before,
                "after_reset_evidence": _after_reset,
                "after_prepare_evidence": _after_prepare,
            },
        )


def _mm_get_free_memory(device: Any) -> int | None:
    try:
        import comfy.model_management as _mm
        _fn = getattr(_mm, "get_free_memory", None)
        if not callable(_fn):
            return None
        _free = _fn(device)
        return int(_free) if _free is not None else None
    except Exception:
        return None


def _mm_extra_reserved_memory() -> int:
    try:
        import comfy.model_management as _mm
        _fn = getattr(_mm, "extra_reserved_memory", None)
        if callable(_fn):
            return int(_fn() or 0)
    except Exception:
        pass
    return 0


def _clip_patcher_in_loaded_models(clip_patcher: Any) -> bool:
    """True when *clip_patcher* is in the real required-loaded cache."""
    if clip_patcher is None:
        return False
    try:
        import comfy.model_management as _mm
        _loaded = getattr(_mm, "current_loaded_models", None)
        if _loaded is None:
            return False
        for _lm in _loaded:
            _m = getattr(_lm, "model", None)
            if _m is not None and _m is clip_patcher:
                return True
    except Exception:
        pass
    return False


def _unet_loaded_bytes(unet: Any) -> int:
    """Return the UNET's loaded (GPU) bytes via its ModelPatcher API."""
    try:
        _fn = getattr(unet, "loaded_size", None)
        if callable(_fn):
            return int(_fn() or 0)
    except Exception:
        pass
    return 0


def _check_early_activation_vram(models: list[Any]) -> dict[str, Any]:
    """Inspect free/required VRAM with a bounded safety margin.

    Never mutates memory or the cache lists.  Returns an outcome dict with
    ``ok`` and, on failure, a structured ``reason`` (skip/fail open).
    ``clip_retained`` reports whether the exact active CLIP patcher is part
    of the requested load (second slot) — the pre-load residency guarantee
    that safe VRAM can retain CLIP + UNET together.
    """
    result: dict[str, Any] = {
        "ok": False,
        "reason": "",
        "free_bytes": None,
        "required_bytes": None,
        "margin_bytes": None,
        "clip_retained": False,
    }
    _required = 0
    _device = None
    for _idx, _m in enumerate(models):
        try:
            _size = int(getattr(_m, "model_size", lambda: 0)() or 0)
        except Exception:
            _size = 0
        _required += _size
        if _idx == 1:
            result["clip_retained"] = True
        _dev = getattr(_m, "load_device", None)
        if _dev is not None:
            _device = _dev
    if _required <= 0:
        result["reason"] = "model_size_unavailable"
        return result
    if _device is None:
        result["reason"] = "device_unavailable"
        return result
    _free = _mm_get_free_memory(_device)
    if _free is None:
        result["reason"] = "vram_unavailable"
        return result
    _required_bytes = int(_required * 1.1) + _mm_extra_reserved_memory()
    _margin = int(
        min(
            _EARLY_ACTIVATION_MARGIN_MAX_BYTES,
            max(
                _EARLY_ACTIVATION_MARGIN_MIN_BYTES,
                _required_bytes * _EARLY_ACTIVATION_MARGIN_RATIO,
            ),
        )
    )
    result["free_bytes"] = int(_free)
    result["required_bytes"] = _required_bytes
    result["margin_bytes"] = _margin
    if int(_free) < _required_bytes + _margin:
        result["reason"] = "vram_insufficient"
        return result
    result["ok"] = True
    return result


def _probe_clip_residency(clip_patcher: Any) -> dict[str, Any]:
    """Post-load residency proof for the exact active CLIP patcher.

    Read-only evidence: model-cache membership and loaded/model bytes when
    the patcher exposes the ModelPatcher API.  Never transfers or mutates
    tensors, never mutates ComfyUI cache lists.
    """
    evidence: dict[str, Any] = {
        "clip_patcher_object_id": str(id(clip_patcher)) if clip_patcher is not None else "",
        "clip_in_model_cache": False,
        "clip_loaded_bytes": None,
        "clip_model_bytes": None,
        "clip_residency_status": "absent",
    }
    if clip_patcher is None:
        return evidence
    try:
        _loaded = _clip_patcher_in_loaded_models(clip_patcher)
        evidence["clip_in_model_cache"] = bool(_loaded)
    except Exception:
        pass
    try:
        _fn = getattr(clip_patcher, "loaded_size", None)
        if callable(_fn):
            evidence["clip_loaded_bytes"] = int(_fn() or 0)
    except Exception:
        pass
    try:
        _fn = getattr(clip_patcher, "model_size", None)
        if callable(_fn):
            evidence["clip_model_bytes"] = int(_fn() or 0)
    except Exception:
        pass
    if evidence["clip_in_model_cache"]:
        _lb = evidence["clip_loaded_bytes"]
        _mb = evidence["clip_model_bytes"]
        if _lb is not None and _mb is not None:
            evidence["clip_residency_status"] = (
                "resident_full" if _lb >= _mb else "resident_partial"
            )
        else:
            evidence["clip_residency_status"] = "resident"
    else:
        evidence["clip_residency_status"] = "not_in_cache"
    return evidence


def _normalize_cuda_device_key(dev: Any) -> tuple[str, int] | None:
    """Normalize a ``torch.device`` or ``cuda[:index]`` string to a CUDA key.

    Returns ``("cuda", index)`` for any CUDA device value — bare ``cuda``
    and ``cuda:0`` normalize to the SAME key (index defaults to 0) so they
    are never a false mismatch — and None for absent/non-CUDA values.
    Never raises.
    """
    if dev is None:
        return None
    _dev_str = ""
    try:
        import torch as _torch_norm
        if isinstance(dev, _torch_norm.device):
            _dev_str = str(dev)
        elif isinstance(dev, str):
            _dev_str = dev
        else:
            _dev_str = str(getattr(dev, "type", "") or "")
    except Exception:
        try:
            _dev_str = str(dev)
        except Exception:
            return None
    _dev_str = _dev_str.strip().lower()
    if _dev_str == "cuda":
        return ("cuda", 0)
    if _dev_str.startswith("cuda:"):
        try:
            _idx = int(_dev_str.split(":", 1)[1])
        except Exception:
            return None
        return ("cuda", _idx)
    return None


def _sync_clip_load_device(clip_patcher: Any) -> dict[str, Any]:
    """Synchronize the CLIP patcher's load device before a residency probe.

    Best-effort CUDA device sync ONLY — never transfers or mutates model
    state and never raises.  Returns structured evidence (``ok``,
    ``reason``, ``device``, ``synchronized``).  When CUDA is unavailable it
    is a no-op with ``reason=cuda_unavailable``.  Synchronizes the patcher's
    CUDA ``load_device`` when present (robustly parsed for ``torch.device``
    or ``cuda[:index]`` strings); otherwise uses the safe
    ``torch.cuda.synchronize()`` current-device fallback.  Must be called
    OUTSIDE ``_UNET_ACTIVATION_LOCK`` — it can block on in-flight CUDA work.
    """
    result: dict[str, Any] = {
        "ok": False,
        "reason": "",
        "device": "",
        "synchronized": False,
    }
    try:
        import torch as _torch_sync
        if not _torch_sync.cuda.is_available():
            result["reason"] = "cuda_unavailable"
            return result
        _dev = None
        try:
            _dev = getattr(clip_patcher, "load_device", None)
        except Exception:
            _dev = None
        if _normalize_cuda_device_key(_dev) is not None:
            try:
                _target = _torch_sync.device(str(_dev))
            except Exception:
                _target = None
            result["device"] = str(_dev)
        else:
            # Safe current-device fallback (None selects the current device).
            _target = None
            try:
                result["device"] = str(_torch_sync.cuda.current_device())
            except Exception:
                result["device"] = "current"
        _torch_sync.cuda.synchronize(_target)
        result["ok"] = True
        result["synchronized"] = True
        return result
    except Exception as exc:
        result["reason"] = f"{type(exc).__name__}: {str(exc)[:200]}"
        return result


def _probe_clip_full_cuda_residency(clip_patcher: Any) -> dict[str, Any]:
    """Full post-load CUDA residency proof for the exact active CLIP patcher.

    Structured read-only evidence: ``ok``, ``reason``, the exact object id,
    exact ``current_loaded_models`` cache membership, loaded/model bytes,
    residency status, and device info.  ``resident_full`` (and ``ok=True``)
    is reported ONLY when ALL of the following hold:

      * the exact patcher is identity-present in ComfyUI's live
        ``current_loaded_models`` cache, and
      * ``loaded_size() >= model_size() > 0``, and
      * the exact patcher's ``load_device`` is present and CUDA — robustly
        parsed for ``torch.device`` or ``cuda[:index]`` strings — for ALL
        patchers (dynamic included); the dynamic exemption applies ONLY to
        ordinary parameter/buffer enumeration (dynamic patchers manage
        weights via vbar/pin state and never require ordinary parameter
        devices), never to proving the CUDA load device, and
      * every parameter and buffer of the patcher's underlying model sits on
        the patcher's CUDA load device — non-dynamic patchers only, and only
        when those collections are available.  Device comparison is
        normalized so ``cuda`` and ``cuda:0`` never mismatch falsely.

    Never transfers or mutates tensors, never mutates cache lists, and
    never raises.  Anything weaker (partial / unknown / absent / off-device)
    is invalid.
    """
    evidence: dict[str, Any] = {
        "ok": False,
        "reason": "no_clip_patcher",
        "clip_patcher_object_id": str(id(clip_patcher)) if clip_patcher is not None else "",
        "clip_in_model_cache": False,
        "cache_membership": "absent",
        "clip_loaded_bytes": None,
        "clip_model_bytes": None,
        "clip_residency_status": "absent",
        "is_dynamic": False,
        "load_device": "",
        "load_device_is_cuda": False,
        "device_check_ok": None,
        "device_mismatch_count": 0,
        "device_check_reason": "",
        "device_info": {},
    }
    if clip_patcher is None:
        return evidence
    try:
        _is_dynamic = bool(
            (getattr(clip_patcher, "is_dynamic", None) or (lambda: False))()
        )
    except Exception:
        _is_dynamic = False
    evidence["is_dynamic"] = bool(_is_dynamic)
    try:
        _load_dev = getattr(clip_patcher, "load_device", None)
    except Exception:
        _load_dev = None
    _load_dev_key = _normalize_cuda_device_key(_load_dev)
    evidence["load_device"] = str(_load_dev) if _load_dev is not None else ""
    evidence["load_device_is_cuda"] = _load_dev_key is not None
    try:
        _in_cache = _clip_patcher_in_loaded_models(clip_patcher)
        evidence["clip_in_model_cache"] = bool(_in_cache)
        evidence["cache_membership"] = "present" if _in_cache else "absent"
    except Exception:
        evidence["cache_membership"] = "unknown"
    try:
        _fn = getattr(clip_patcher, "loaded_size", None)
        if callable(_fn):
            evidence["clip_loaded_bytes"] = int(_fn() or 0)
    except Exception:
        pass
    try:
        _fn = getattr(clip_patcher, "model_size", None)
        if callable(_fn):
            evidence["clip_model_bytes"] = int(_fn() or 0)
    except Exception:
        pass
    _lb = evidence["clip_loaded_bytes"]
    _mb = evidence["clip_model_bytes"]
    _bytes_ok = bool(
        isinstance(_lb, int) and isinstance(_mb, int)
        and _mb > 0 and _lb >= _mb
    )
    # Parameter/buffer device proof — non-dynamic patchers with a CUDA load
    # device only, and only when the collections are available (a failed
    # enumeration means the requirement cannot be assessed and is waived).
    # ``ModelPatcher`` itself is a plain class, so the ordinary parameter
    # and buffer collections come from its underlying ``.model`` module.
    # The CUDA load-device requirement is STRICT for ALL patchers (dynamic
    # included); the dynamic exemption applies ONLY to enumeration below.
    _devices_ok: bool | None = None
    _mismatch = 0
    _dev_reason = ""
    if not evidence["load_device_is_cuda"]:
        # Absent or non-CUDA load device: reject the proof outright.
        _devices_ok = False
        _dev_reason = "load_device_absent" if _load_dev is None else "load_device_not_cuda"
    elif not _is_dynamic:
        _devices_ok = True
        try:
            _target = _load_dev
            _target_key = _normalize_cuda_device_key(_target)
            _module = clip_patcher
            try:
                _under = getattr(clip_patcher, "model", None)
                if _under is not None and hasattr(_under, "parameters"):
                    _module = _under
            except Exception:
                pass
            for _tensors in (_module.parameters(), _module.buffers()):
                for _t in _tensors:
                    # Normalized comparison: ``cuda`` == ``cuda:0``.
                    if _normalize_cuda_device_key(getattr(_t, "device", None)) != _target_key:
                        _mismatch += 1
            if _mismatch:
                _devices_ok = False
                _dev_reason = "parameter_device_mismatch"
        except Exception as exc:
            _devices_ok = None
            _dev_reason = f"{type(exc).__name__}: {str(exc)[:200]}"
    evidence["device_check_ok"] = _devices_ok
    evidence["device_mismatch_count"] = _mismatch
    evidence["device_check_reason"] = _dev_reason
    evidence["device_info"] = {
        "load_device": evidence["load_device"],
        "load_device_is_cuda": evidence["load_device_is_cuda"],
        "is_dynamic": bool(_is_dynamic),
        "parameter_buffer_devices_ok": _devices_ok,
        "device_mismatch_count": _mismatch,
        "device_check_reason": _dev_reason,
    }
    if evidence["clip_in_model_cache"] and _bytes_ok:
        if _devices_ok is False:
            evidence["reason"] = _dev_reason or "parameter_device_mismatch"
            evidence["clip_residency_status"] = "resident_off_device"
        else:
            evidence["ok"] = True
            evidence["reason"] = "ok"
            evidence["clip_residency_status"] = "resident_full"
    elif not evidence["clip_in_model_cache"]:
        evidence["reason"] = "not_in_cache"
        evidence["clip_residency_status"] = "not_in_cache"
    elif not _bytes_ok:
        evidence["reason"] = "bytes_incomplete"
        evidence["clip_residency_status"] = (
            "resident_unknown_bytes"
            if (_mb is None or _lb is None)
            else "resident_partial"
        )
    else:
        evidence["reason"] = "residency_incomplete"
    return evidence


def _gpu_allocated_bytes() -> int | None:
    """Best-effort live CUDA allocated bytes (totals only).  Never raises."""
    try:
        import torch as _torch_gpu_bytes
        if _torch_gpu_bytes.cuda.is_available():
            return int(_torch_gpu_bytes.cuda.memory_allocated())
    except Exception:
        pass
    return None


def _probe_early_activation_evidence(unet: Any) -> dict[str, Any]:
    """Read-only residency/cache/device evidence after the early load.

    Never raises, never transfers or mutates tensors.
    """
    evidence: dict[str, Any] = {
        "residency_status": "unknown",
        "cache_present": False,
        "current_device": "",
        "load_device": "",
    }
    from .unet_forward_probe import resolve_diffusion_model

    _patcher, _dm = resolve_diffusion_model(unet)
    if _dm is not None:
        try:
            evidence["current_device"] = str(getattr(_dm, "current_device", "") or "")
        except Exception:
            pass
        try:
            evidence["load_device"] = str(getattr(_dm, "device", "") or "")
        except Exception:
            pass
    try:
        from .cpu_snapshot_models import prove_unet_gpu_residency
        _res = prove_unet_gpu_residency(unet, request_id="")
        evidence["residency_status"] = _res.get("status", "unknown")
        evidence["gpu_parameter_count"] = _res.get("gpu_parameter_count", 0)
        evidence["parameter_count"] = _res.get("parameter_count", 0)
    except Exception:
        evidence["residency_status"] = "unknown"
    try:
        import comfy.model_management as _mm
        _loaded = getattr(_mm, "current_loaded_models", None)
        if _loaded is not None:
            for _lm in _loaded:
                _m = getattr(_lm, "model", None)
                if _m is not None and _m is unet:
                    evidence["cache_present"] = True
                    break
    except Exception:
        pass
    return evidence


# ── Terminal / marker helpers ───────────────────────────────────────────

_EVENT_UNET_EA_STATUS_MAP: dict[str, str] = {
    "ready": _EVENT_UNET_EA_COMPLETED,
    "skipped": _EVENT_UNET_EA_SKIPPED,
    "failed": _EVENT_UNET_EA_FAILED,
    "invalid": _EVENT_UNET_EA_INVALID,
    "cancelled": _EVENT_UNET_EA_CANCELLED,
}


def _early_activation_base_meta(state: dict[str, Any], request_id: str) -> dict[str, Any]:
    return {
        "mode": state.get("mode", ""),
        "trigger": state.get("trigger", ""),
        "request_id": request_id,
        "key_hash": state.get("key_hash", ""),
        "restored_instance_id": _LATEST_RESTORED_INSTANCE_ID,
        "restore_session_id": _LATEST_RESTORE_SESSION_ID,
        "unet_patcher_object_id": state.get("unet_patcher_object_id", ""),
        "unet_diffusion_object_id": state.get("unet_diffusion_object_id", ""),
        "sampler_patcher_object_id": state.get("sampler_patcher_object_id", ""),
        "clip_object_id": state.get("clip_object_id", ""),
    }


def _early_activation_extra_meta(state: dict[str, Any]) -> dict[str, Any]:
    """Durations / VRAM / GPU-allocation / residency evidence shared by the
    terminal and fallback markers.  All values come from live state."""
    return {
        "submitted_mono_ns": state.get("submitted_mono_ns", 0) or 0,
        "worker_started_mono_ns": state.get("worker_started_mono_ns", 0) or 0,
        "terminal_mono_ns": state.get("terminal_mono_ns", 0) or 0,
        "clip_encode_start_mono_ns": state.get("clip_encode_start_mono_ns", 0) or 0,
        "clip_encode_end_mono_ns": state.get("clip_encode_end_mono_ns", 0) or 0,
        "lane_wait_ms": state.get("lane_wait_ms", 0.0) or 0.0,
        "load_wall_ms": state.get("load_wall_ms", 0.0) or 0.0,
        "load_thread_cpu_ms": state.get("load_thread_cpu_ms"),
        "load_process_cpu_ms": state.get("load_process_cpu_ms"),
        "gpu_free_bytes": state.get("gpu_free_bytes"),
        "gpu_required_bytes": state.get("gpu_required_bytes"),
        "safety_margin_bytes": state.get("safety_margin_bytes"),
        "gpu_allocated_before": state.get("gpu_allocated_before"),
        "gpu_allocated_after": state.get("gpu_allocated_after"),
        "gpu_allocated_delta_bytes": state.get("gpu_allocated_delta_bytes"),
        "clip_retained": bool(state.get("clip_retained", False)),
        "clip_resident": bool(state.get("clip_resident", False)),
        "clip_residency_status": state.get("clip_residency_status", ""),
        "cache_present": bool(state.get("cache_present", False)),
        "transfer_count": state.get("transfer_count", 0),
    }


def _early_activation_terminal(
    state: dict[str, Any],
    trace: RuntimeTrace | None,
    request_id: str,
    *,
    status: str,
    reason: str,
    error: str = "",
    transfer_count: int = 0,
    diagnostics: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Establish the terminal state exactly once and emit the status marker
    plus the generic ``unet_early_activation_terminal`` marker."""
    with _UNET_ACTIVATION_LOCK:
        if not state.get("terminal", False):
            state["terminal"] = True
            state["status"] = status
            state["reason"] = reason
            if error:
                state["error"] = error
            if transfer_count:
                state["transfer_count"] = transfer_count
            state["terminal_mono_ns"] = time.monotonic_ns()
        if diagnostics:
            _diag = state.setdefault("diagnostics", {})
            for _k, _v in dict(diagnostics).items():
                if not isinstance(_v, (bytes, bytearray)):
                    _diag[_k] = _v
    _event = _EVENT_UNET_EA_STATUS_MAP.get(state.get("status", status))
    if trace is not None and _event is not None:
        _meta = _early_activation_base_meta(state, request_id)
        _meta.update({
            "status": state.get("status", status),
            "reason": state.get("reason", reason),
            "error": state.get("error", "") or None,
            "transfer_count": state.get("transfer_count", 0),
        })
        _meta.update(_early_activation_extra_meta(state))
        trace.emit(_event, phase="execution", metadata=_meta)
    if trace is not None:
        _term_meta = _early_activation_base_meta(state, request_id)
        _term_meta.update({
            "status": state.get("status", status),
            "reason": state.get("reason", reason),
            "error": state.get("error", "") or None,
            "transfer_count": state.get("transfer_count", 0),
        })
        _term_meta.update(_early_activation_extra_meta(state))
        trace.emit(_EVENT_UNET_EA_TERMINAL, phase="execution", metadata=_term_meta)
    print(
        f"[v2.unet_early_activation] event=terminal "
        f"trigger={state.get('trigger', '')} status={state.get('status', status)} "
        f"transfer_count={state.get('transfer_count', 0)} "
        f"request_id={request_id or 'absent'} mode={state.get('mode', '')} "
        f"key_hash={state.get('key_hash', '')} "
        f"reason={state.get('reason', reason) or 'ok'} error={state.get('error', '') or 'absent'}",
        flush=True,
    )
    return {
        "status": state.get("status", status),
        "reason": state.get("reason", reason),
        "terminal": True,
    }


def _elect_early_activation_fallback(
    state: dict[str, Any],
    trace: RuntimeTrace | None,
    request_id: str,
    *,
    reason: str,
    error: str = "",
    join_wait_ms: float = 0.0,
) -> dict[str, Any]:
    """Elect the unchanged late fallback exactly once (atomic, never
    overwritten).  Returns an outcome dict with ``valid=False``."""
    with _UNET_ACTIVATION_LOCK:
        _elected = bool(state.get("fallback_elected", False))
        if not _elected:
            state["fallback_elected"] = True
            state["fallback_reason"] = reason
            state["terminal"] = True
            if error:
                state["error"] = error
        _status = state.get("status", "fallback")
        _reason = state.get("fallback_reason", reason)
    if trace is not None and not _elected:
        _meta = _early_activation_base_meta(state, request_id)
        _meta.update({
            "status": _status,
            "reason": _reason,
            "error": error or None,
            "join_wait_ms": round(float(join_wait_ms), 3),
        })
        _meta.update(_early_activation_extra_meta(state))
        trace.emit(_EVENT_UNET_EA_FALLBACK, phase="execution", metadata=_meta)
        _term_meta = _early_activation_base_meta(state, request_id)
        _term_meta.update({
            "status": _status,
            "reason": _reason,
            "error": error or None,
        })
        _term_meta.update(_early_activation_extra_meta(state))
        trace.emit(_EVENT_UNET_EA_TERMINAL, phase="execution", metadata=_term_meta)
        print(
            f"[v2.unet_early_activation] event=fallback "
            f"request_id={request_id or 'absent'} mode={state.get('mode', '')} "
            f"key_hash={state.get('key_hash', '')} reason={_reason} "
            f"error={error or 'absent'} status={_status}",
            flush=True,
        )
    return {
        "scheduled": True,
        "status": _status,
        "terminal": True,
        "valid": False,
        "reason": _reason,
        "join_wait_ms": round(float(join_wait_ms), 3),
    }


# ── Early activation worker ─────────────────────────────────────────────


def _measure_early_activation_lane_wait_ms(
    trace: RuntimeTrace | None,
    *,
    request_id: str,
    wait_start_ns: int | None,
) -> float | None:
    """Measure the truthful mutation-lane wait from existing lane trace events.

    The existing GPU loader wrapper acquires the coordinator-owned mutation
    lane INSIDE ``load_models_gpu`` and emits ``gpu_lane_wait_start`` at the
    instant the lane is actually acquired.  The worker's own
    ``unet_early_activation_lane_wait_start`` marker is emitted immediately
    before the load call, so the interval between the two existing events is
    the truthful lane wait.  Returns None when the wrapper never reported the
    lane acquisition (e.g. a load path that does not emit lane events) — the
    value is never fabricated.  The worker never acquires the mutation lane
    itself, so this cannot deadlock the existing GPU wrapper.
    """
    if trace is None or not wait_start_ns:
        return None
    _wait_ns: int | None = None
    for _event in trace.events:
        if _event.name != "gpu_lane_wait_start":
            continue
        _meta = _event.metadata or {}
        if str(_meta.get("lane", "")) != "UNET_EARLY_ACTIVATION":
            continue
        if _event.monotonic_ns < wait_start_ns:
            continue
        _wait_ns = _event.monotonic_ns - wait_start_ns
        break
    if _wait_ns is None or _wait_ns < 0:
        return None
    return round(_wait_ns / 1_000_000, 3)


def _run_early_unet_activation(
    bridge: "V2LoaderBridge",
    *,
    prep: RestorePreparation,
    trace: RuntimeTrace | None,
    request_id: str,
    state: dict[str, Any],
    clip: Any,
    key_hash: str,
    mode: str,
) -> dict[str, Any]:
    """Early retained-UNET GPU activation worker (coordinator pool).

    Uses the exact retained UNET and the original ComfyUI
    ``load_models_gpu`` / ``LoadedModel.model_load`` path — never transfers
    or mutates ComfyUI cache lists manually.  The existing GPU loader
    wrapper acquires the coordinator-owned mutation lane only around the
    actual load; nothing here holds the lane while queued, validating, or
    running CLIP.  Waits for the retained objects OUTSIDE the lane, emits
    ``lane_wait_start``/``lane_acquired`` and ``load_start``/``load_end``
    around the original load path only.  The exact active CLIP patcher is
    kept resident by loading it alongside through the real required-loaded
    argument/API; the load is skipped when safe residency cannot be
    guaranteed (VRAM) and a post-load CLIP residency proof is recorded.
    Re-checks cancellation immediately before mutation so a finalized
    request never gets an unowned load.  Never applies request-dependent
    sampler patches.
    """
    with _UNET_ACTIVATION_LOCK:
        state["status"] = "running"
        state["worker_started_mono_ns"] = time.monotonic_ns()
    if trace is not None:
        trace.emit(_EVENT_UNET_EA_WORKER_START, phase="execution", metadata={
            "mode": mode,
            "trigger": state.get("trigger", ""),
            "request_id": request_id,
            "key_hash": key_hash,
            "restored_instance_id": _LATEST_RESTORED_INSTANCE_ID,
            "restore_session_id": _LATEST_RESTORE_SESSION_ID,
        })

    # ── Wait for the exact retained UNET (outside the lane) ──────────
    try:
        unet = bridge.coordinator.wait_unet(
            prep, trace=trace, demand_source="execution_prefill"
        )
    except Exception as exc:
        return _early_activation_terminal(
            state, trace, request_id, status="failed",
            reason="unet_future_failed", error=str(exc)[:200],
        )
    if unet is None:
        return _early_activation_terminal(
            state, trace, request_id, status="skipped", reason="no_retained_unet"
        )
    state["unet_patcher_object_id"] = str(id(unet))

    # Request cleanup may have finalized while we waited.
    if state.get("cancelled") or state.get("terminal"):
        return _early_activation_terminal(
            state, trace, request_id, status="cancelled", reason="request_finalized"
        )

    # ── Resolve diffusion identity + dtype/device (outside the lane) ──
    # The activation key was built at scheduling time with the REAL retained
    # patcher/diffusion ids.  If the resolved identity changed between
    # scheduling and the worker (a different retained object surfaced), the
    # activation is rejected — never reuse a key across identity changes.
    from .unet_forward_probe import resolve_diffusion_model

    _patcher, _dm = resolve_diffusion_model(unet)
    _patcher_id = str(id(_patcher)) if _patcher is not None else str(id(unet))
    _dm_id = str(id(_dm)) if _dm is not None else ""
    if _dm is not None:
        state["unet_diffusion_object_id"] = _dm_id
    _expected_patcher = str((state.get("key") or {}).get("unet_patcher_object_id", "") or "")
    _expected_dm = str((state.get("key") or {}).get("unet_diffusion_object_id", "") or "")
    if _expected_patcher and _expected_patcher != _patcher_id:
        return _early_activation_terminal(
            state, trace, request_id, status="invalid",
            reason="identity_changed_patcher",
        )
    if _expected_dm and _expected_dm != _dm_id:
        return _early_activation_terminal(
            state, trace, request_id, status="invalid",
            reason="identity_changed_diffusion",
        )
    _state_key = dict(state.get("key") or {})
    _state_key["unet_patcher_object_id"] = _patcher_id
    _state_key["unet_diffusion_object_id"] = _dm_id
    try:
        _md = getattr(unet, "model_dtype", None)
        if callable(_md):
            _state_key["compute_dtype"] = str(_md() or "")
    except Exception:
        pass
    try:
        _dev = getattr(unet, "load_device", None)
        if _dev is not None:
            _state_key["device"] = str(_dev)
    except Exception:
        pass
    state["key"] = _state_key
    # Recompute the key hash with the resolved identity before publication.
    state["key_hash"] = stable_hash(_state_key)[:24]

    # Protect the exact active CLIP patcher by loading it alongside the UNET
    # through the real required-loaded argument (models list of the original
    # ComfyUI load path).  Never manually transfers tensors or mutates the
    # cache lists.
    _load_models: list[Any] = [unet]
    _clip_patcher = _resolve_clip_patcher(clip)
    if _clip_patcher is not None and _clip_patcher is not unet:
        _load_models.append(_clip_patcher)

    # ── VRAM / residency pre-check (outside the lane) ────────────────
    _vram = _check_early_activation_vram(_load_models)
    state["gpu_free_bytes"] = _vram.get("free_bytes")
    state["gpu_required_bytes"] = _vram.get("required_bytes")
    state["safety_margin_bytes"] = _vram.get("margin_bytes")
    state["clip_retained"] = bool(_vram.get("clip_retained", False))
    if not _vram.get("ok"):
        return _early_activation_terminal(
            state, trace, request_id, status="skipped",
            reason=str(_vram.get("reason", "vram_insufficient")),
            diagnostics=_vram,
        )

    # ── Re-check cancellation IMMEDIATELY before the GPU mutation ────
    # A request finalized between the earlier checks and the mutation must
    # never load unowned.  The lane is acquired by the existing GPU loader
    # wrapper only around the actual load.
    if state.get("cancelled") or state.get("terminal"):
        return _early_activation_terminal(
            state, trace, request_id, status="cancelled", reason="request_finalized"
        )

    # ── Original ComfyUI load path (lane acquired by the existing wrapper) ──
    # lane_wait_start/lane_acquired + load_start/load_end bracket the
    # original load_models_gpu/LoadedModel path only; nothing else holds
    # the lane.
    _loaded_before = _unet_loaded_bytes(unet)
    _gpu_alloc_before = _gpu_allocated_bytes()
    _load_start = _capture_phase_counters()
    # Monotonic boundary of the worker's lane-wait marker — the truthful
    # lane wait is measured against the wrapper's gpu_lane_wait_start below.
    _lane_wait_start_ns = time.monotonic_ns()
    if trace is not None:
        # ── Phase 1A candidate (clip_gpu_ready): concise load-start marker
        # BEFORE the existing load-start/actual load.  The worker acquires
        # the activation lock before this point, so this marker is
        # guaranteed to follow ``unet_activation_scheduled`` (emitted while
        # the scheduler held the same lock).
        if mode == _UNET_ACTIVATION_MODE_CLIP_GPU_READY:
            trace.emit(_EVENT_UNET_ACTIVATION_LOAD_START, phase="execution", metadata={
                "mode": mode,
                "trigger": state.get("trigger", ""),
                "request_id": request_id,
                "key_hash": state.get("key_hash", ""),
            })
        trace.emit(_EVENT_UNET_EA_LANE_WAIT_START, phase="execution", metadata={
            "mode": mode,
            "trigger": state.get("trigger", ""),
            "request_id": request_id,
            "key_hash": state.get("key_hash", ""),
        })
        trace.emit(_EVENT_UNET_EA_LOAD_START, phase="execution", metadata={
            "mode": mode,
            "request_id": request_id,
            "key_hash": state.get("key_hash", ""),
            "model_count": len(_load_models),
        })
    try:
        _mm_load_models_gpu(_load_models)
    except Exception as exc:
        return _early_activation_terminal(
            state, trace, request_id, status="failed",
            reason="load_failed", error=str(exc)[:200],
        )
    _load_end = _capture_phase_counters()
    _deltas = _phase_counter_deltas(_load_start, _load_end)
    state["load_wall_ms"] = _deltas.get("wall_ms", 0.0) or 0.0
    state["load_thread_cpu_ms"] = _deltas.get("thread_cpu_ms")
    state["load_process_cpu_ms"] = _deltas.get("process_cpu_ms")
    state["transfer_count"] = 1 if _unet_loaded_bytes(unet) > _loaded_before else 0
    _gpu_alloc_after = _gpu_allocated_bytes()
    state["gpu_allocated_before"] = _gpu_alloc_before
    state["gpu_allocated_after"] = _gpu_alloc_after
    if _gpu_alloc_before is not None and _gpu_alloc_after is not None:
        state["gpu_allocated_delta_bytes"] = _gpu_alloc_after - _gpu_alloc_before
    # Truthful mutation-lane wait from the existing lane trace events around
    # the load (worker lane_wait_start -> wrapper gpu_lane_wait_start).  The
    # wrapper owns the lane; we never acquire it ourselves, so this cannot
    # deadlock.  None (fake/absent wrapper events) stays 0.0 — never invented.
    state["lane_wait_ms"] = _measure_early_activation_lane_wait_ms(
        trace, request_id=request_id, wait_start_ns=_lane_wait_start_ns,
    ) or 0.0
    if trace is not None:
        trace.emit(_EVENT_UNET_EA_LOAD_END, phase="execution", metadata={
            "mode": mode,
            "request_id": request_id,
            "key_hash": state.get("key_hash", ""),
            "load_wall_ms": state.get("load_wall_ms", 0.0),
            "transfer_count": state.get("transfer_count", 0),
        })
        trace.emit(_EVENT_UNET_EA_LANE_ACQUIRED, phase="execution", metadata={
            "mode": mode,
            "request_id": request_id,
            "key_hash": state.get("key_hash", ""),
            "load_wall_ms": state.get("load_wall_ms", 0.0),
        })

    # ── Terminal validation: UNET residency + cache + CLIP residency ──
    _evidence = _probe_early_activation_evidence(unet)
    state["cache_present"] = bool(_evidence.get("cache_present", False))
    _res_status = _evidence.get("residency_status", "unknown")
    # The retained CLIP patcher was loaded alongside; synchronize its load
    # device OUTSIDE the lock (async loads can still be in flight), then run
    # the exact same strict full-CUDA-residency proof as the fire hook.
    # ``ready`` requires BOTH the post-load sync evidence ``ok`` (a CUDA sync
    # actually ran) AND the strict proof ``ok`` — partial/unknown residency
    # or an absent/non-CUDA load device is invalid.
    _clip_sync = _sync_clip_load_device(_clip_patcher)
    _clip_evidence = _probe_clip_full_cuda_residency(_clip_patcher)
    _clip_evidence["residency_sync"] = _clip_sync
    state["clip_resident"] = bool(
        _clip_sync.get("ok", False) and _clip_evidence.get("ok", False)
    )
    state["clip_residency_status"] = str(_clip_evidence.get("clip_residency_status", "absent"))
    _combined_diag = dict(_evidence)
    _combined_diag["clip_residency"] = _clip_evidence
    if _res_status == "cpu_resident" or not state["cache_present"]:
        return _early_activation_terminal(
            state, trace, request_id, status="invalid",
            reason="residency_not_proven", diagnostics=_combined_diag,
        )
    # The exact active CLIP patcher was requested alongside; full residency
    # proof (exact cache identity + loaded>=model>0 + device placement) is
    # required — a partial/unknown CLIP residency is never ``ready``.
    if state["clip_retained"] and not state["clip_resident"]:
        return _early_activation_terminal(
            state, trace, request_id, status="invalid",
            reason="clip_residency_not_proven", diagnostics=_combined_diag,
        )
    return _early_activation_terminal(
        state, trace, request_id, status="ready", reason="ok",
        transfer_count=state["transfer_count"], diagnostics=_combined_diag,
    )


# ── Public API ──────────────────────────────────────────────────────────


def _unet_activation_submit(
    bridge: "V2LoaderBridge",
    *,
    request_id: str,
    trace: RuntimeTrace | None,
    prep: RestorePreparation,
    model_key: ModelRestoreKey,
    mode: str,
    trigger: str,
    clip: Any,
    encode_entries: list[dict[str, Any]] | int | None,
    key_components: dict[str, Any],
    key_hash: str,
    create_state: bool = True,
    residency_evidence: Mapping[str, Any] | None = None,
) -> bool:
    """Shared coordinator/single-flight scheduling core for the retained-UNET
    activation.

    Used by BOTH the ``clip_encode_start`` boundary hook and the
    ``clip_gpu_ready`` GPU-loader fire hook so both modes schedule through
    the same coordinator ``_submit`` path.  Atomically (under the existing
    activation lock) creates/finds the request state, submits the
    retained-UNET activation worker once through
    ``bridge.coordinator._submit``, records the future, and emits the
    mode-appropriate scheduled marker WHILE HOLDING the lock — so the marker
    is guaranteed to precede any worker-emitted load-start marker
    (monotonic-order invariant).  Single-flight: a state that already has a
    future is never resubmitted.  *create_state* must be False for the fire
    path (``clip_gpu_ready``) so a request whose state was already popped by
    request-end finalize is never re-created / re-scheduled.  Returns True
    when scheduled (or already scheduled), False on submit failure (state
    marked terminal ``failed``) or when *create_state* is False and no state
    exists.  *residency_evidence* (optional, ``clip_gpu_ready`` fire path)
    carries the proven CLIP residency evidence into the concise
    ``unet_activation_scheduled`` marker metadata.
    """
    with _UNET_ACTIVATION_LOCK:
        _state = _UNET_ACTIVATION_STATE.get(request_id)
        if _state is not None and _state.get("future") is not None:
            return True
        if _state is None:
            if not create_state:
                return False
            _state = _unet_activation_new_state(request_id)
            _UNET_ACTIVATION_STATE[request_id] = _state
        _state["owner"] = trigger
        _state["trigger"] = trigger
        _state["mode"] = mode
        _state["eligible"] = True
        _state["eligibility_reason"] = "ok"
        _state["key"] = key_components
        _state["key_hash"] = key_hash
        # clip_encode_start_mono_ns is intentionally NOT set here (scheduling
        # time).  It is recorded at the ACTUAL encode boundary by
        # record_clip_encode_start() in the execution-prefill worker so the
        # waterfall reconciliation measures the real encode start, not the
        # schedule/submit time (submitted_mono_ns stays separate below).
        if isinstance(encode_entries, int):
            _state["clip_encode_entries"] = max(0, encode_entries)
        else:
            _state["clip_encode_entries"] = max(0, len(encode_entries or []))
        _state["clip_object_id"] = str(id(clip)) if clip is not None else ""
        _state["status"] = "scheduled"
        _state["submitted_mono_ns"] = time.monotonic_ns()

        def _worker() -> Any:
            return _run_early_unet_activation(
                bridge,
                prep=prep,
                trace=trace,
                request_id=request_id,
                state=_state,
                clip=clip,
                key_hash=key_hash,
                mode=mode,
            )

        try:
            _future = bridge.coordinator._submit(
                "unet_early_activation", _worker, prep, trace,
                phase="execution", expected_read_count=0,
            )
        except Exception as exc:
            _state["status"] = "failed"
            _state["terminal"] = True
            _state["reason"] = "submit_failed"
            _state["error"] = str(exc)[:200]
            _state["terminal_mono_ns"] = time.monotonic_ns()
            if trace is not None:
                trace.emit(_EVENT_UNET_EA_FAILED, phase="execution", metadata={
                    "mode": mode,
                    "trigger": trigger,
                    "request_id": request_id,
                    "key_hash": key_hash,
                    "reason": "submit_failed",
                    "error": str(exc)[:200],
                })
            return False
        _state["future"] = _future
        # Emit the scheduled marker(s) WHILE HOLDING the lock.  The worker
        # must acquire the same lock before it can emit any load-start
        # marker, so ``unet_activation_scheduled`` is guaranteed to precede
        # ``unet_activation_load_start`` in the trace (reliable monotonic
        # order).  The existing ``unet_early_activation_scheduled`` marker
        # is preserved unchanged.
        if trace is not None:
            _sched_meta = {
                "mode": mode,
                "trigger": trigger,
                "request_id": request_id,
                "key_hash": key_hash,
                "clip_encode_entries": _state.get("clip_encode_entries", 0),
                "unet_patcher_object_id": key_components.get("unet_patcher_object_id", ""),
                "unet_diffusion_object_id": key_components.get("unet_diffusion_object_id", ""),
                "unet_identity_hash": stable_hash(str(model_key.unet_identity))[:16],
                "restored_instance_id": _LATEST_RESTORED_INSTANCE_ID,
                "restore_session_id": _LATEST_RESTORE_SESSION_ID,
            }
            trace.emit(_EVENT_UNET_EA_SCHEDULED, phase="execution", metadata=_sched_meta)
            if mode == _UNET_ACTIVATION_MODE_CLIP_GPU_READY:
                _activation_meta = {
                    "mode": mode,
                    "trigger": trigger,
                    "request_id": request_id,
                    "key_hash": key_hash,
                    "unet_patcher_object_id": key_components.get("unet_patcher_object_id", ""),
                    "unet_diffusion_object_id": key_components.get("unet_diffusion_object_id", ""),
                }
                if residency_evidence is not None:
                    # Proven residency evidence rides the scheduled marker so
                    # the concise clip_gpu_ready timing chain stays
                    # self-contained (existing marker model supports it).
                    _activation_meta["clip_residency_status"] = str(
                        residency_evidence.get("clip_residency_status", "") or ""
                    )
                    _activation_meta["clip_loaded_bytes"] = residency_evidence.get("clip_loaded_bytes")
                    _activation_meta["clip_model_bytes"] = residency_evidence.get("clip_model_bytes")
                trace.emit(_EVENT_UNET_ACTIVATION_SCHEDULED, phase="execution", metadata=_activation_meta)
    _unet_activation_trim()
    print(
        f"[v2.unet_early_activation] event=scheduled "
        f"trigger={trigger} "
        f"request_id={request_id or 'absent'} mode={mode} "
        f"key_hash={key_hash} clip_encode_entries={_state.get('clip_encode_entries', 0)} "
        f"restored_instance_id={_LATEST_RESTORED_INSTANCE_ID or 'absent'} "
        f"restore_session_id={_LATEST_RESTORE_SESSION_ID or 'absent'}",
        flush=True,
    )
    return True


def clip_encode_start(
    bridge: "V2LoaderBridge",
    *,
    trace: RuntimeTrace | None = None,
    request_id: str = "",
    clip: Any = None,
    encode_entries: list[dict[str, Any]] | None = None,
) -> bool:
    """Schedule the early retained-UNET GPU activation once per request.

    Hooked at the established real execution-prefill CLIP callback boundary
    (``_execution_prefill`` — the ONLY integration call) immediately before
    the actual prefill encode, never at request entry / tokenization / graph
    fallback / dummy encode.  Before scheduling, every eligibility condition
    is proven at the boundary (execution-prefill caller, mode
    ``clip_encode_start``, production CPU-snapshot request marker, exact
    retained snapshot→bridge identity chain, completed retained-UNET future,
    no same-request/key future, live CUDA validity, and safe VRAM for the
    exact active CLIP + retained UNET).  Any proof that cannot be made emits
    ``unet_early_activation_eligible`` false and
    ``unet_early_activation_skipped`` with the exact reason and does NOT
    schedule.  Idempotent across positive/negative encodes: the first caller
    claims the request slot and schedules the worker once through the
    existing coordinator pool; every subsequent call joins the same future.
    Mode-gated (default ``"late"`` is a no-op that preserves Phase 0
    behavior; ``"clip_gpu_ready"`` uses the arm/fire path instead of this
    scheduling entry; no candidate path can activate for ``early``).
    Returns True when scheduled (or already scheduled), False when
    late/ineligible.
    """
    mode = unet_activation_mode()
    if mode != _UNET_ACTIVATION_MODE_CLIP_ENCODE_START:
        return False
    if bridge is None:
        return False
    prep = getattr(bridge, "_preparation", None)
    model_key = getattr(bridge, "_model_key", None)
    if prep is None or model_key is None or prep.unet_future is None:
        return False
    _request_id = str(request_id or "")
    if not _request_id and trace is not None:
        _request_id = str(trace.request_id)
    if not _request_id:
        return False
    # Idempotent across positive/negative encodes: a scheduled future for
    # this request is joined, never re-scheduled.
    with _UNET_ACTIVATION_LOCK:
        _existing = _UNET_ACTIVATION_STATE.get(_request_id)
        if _existing is not None and _existing.get("future") is not None:
            return True

    if trace is not None:
        trace.emit(_EVENT_UNET_EA_MODE, phase="execution", metadata={
            "mode": mode,
            "trigger": "clip_encode_start",
            "request_id": _request_id,
            "restored_instance_id": _LATEST_RESTORED_INSTANCE_ID,
            "restore_session_id": _LATEST_RESTORE_SESSION_ID,
        })

    # ── Eligibility gate (Hard Correction 2) ────────────────────────
    _eligible, _reason, _evidence = _prove_unet_early_activation_eligible(
        bridge,
        request_id=_request_id,
        clip=clip,
        mode=mode,
        trigger="clip_encode_start",
    )
    _eligible_meta = dict(_evidence)
    _eligible_meta.update({
        "eligible": bool(_eligible),
        "reason": _reason,
    })
    if trace is not None:
        trace.emit(_EVENT_UNET_EA_ELIGIBLE, phase="execution", metadata=_eligible_meta)
    if not _eligible:
        if trace is not None:
            _skip_meta = {
                "mode": mode,
                "trigger": "clip_encode_start",
                "request_id": _request_id,
                "eligible": False,
                "reason": _reason,
                "restored_instance_id": _LATEST_RESTORED_INSTANCE_ID,
                "restore_session_id": _LATEST_RESTORE_SESSION_ID,
                "free_bytes": _evidence.get("free_bytes"),
                "required_bytes": _evidence.get("required_bytes"),
                "margin_bytes": _evidence.get("margin_bytes"),
            }
            trace.emit(_EVENT_UNET_EA_SKIPPED, phase="execution", metadata=_skip_meta)
        print(
            f"[v2.unet_early_activation] event=skipped "
            f"request_id={_request_id or 'absent'} mode={mode} trigger=clip_encode_start "
            f"reason={_reason} eligible=0",
            flush=True,
        )
        return False

    # ── Key with REAL retained identities (Hard Correction 3) ──────
    # A completed snapshot future is expected for the candidate; the exact
    # retained UNET is resolved here so the key is never built with blank
    # placeholders.
    try:
        _retained_unet = prep.unet_future.result()
    except Exception:
        _retained_unet = None
    _key_components, _key_hash = _build_unet_activation_key(
        mode=mode,
        model_key=model_key,
        request_id=_request_id,
        unet=_retained_unet,
        weight_dtype=_unet_requested_weight_dtype(bridge, model_key),
    )
    return _unet_activation_submit(
        bridge,
        request_id=_request_id, trace=trace, prep=prep, model_key=model_key,
        mode=mode, trigger="clip_encode_start",
        clip=clip, encode_entries=encode_entries,
        key_components=_key_components, key_hash=_key_hash,
    )


def _unet_activation_arm(
    bridge: "V2LoaderBridge",
    *,
    trace: RuntimeTrace | None = None,
    request_id: str = "",
    clip: Any = None,
    encode_entries: list[dict[str, Any]] | None = None,
) -> bool:
    """Arm the request-scoped single-use retained-UNET activation trigger
    (``COMFYMODAL_V2_UNET_ACTIVATION_MODE=clip_gpu_ready``).

    Runs at the established real execution-prefill CLIP callback boundary
    (``_execution_prefill`` — the ONLY integration call) immediately before
    the actual prefill encode.  Performs the SAME eligibility / identity /
    VRAM proofs as ``clip_encode_start`` (execution-prefill caller, mode,
    production CPU-snapshot request marker, exact retained snapshot→bridge
    identity chain, completed retained-UNET future, no same-request/key
    future, live CUDA validity, and safe VRAM for the exact active CLIP +
    retained UNET) but MUST NOT submit or schedule the UNET here.  The
    retained-UNET activation is scheduled later — exactly once — by the
    existing GPU loader wrapper hook when the first qualifying successful
    CLIP ``load_models_gpu`` call from the real prefill encode returns and
    the mutation lane is released.  Idempotent per request: a second arm (or
    an already armed/fired/scheduled state) is a no-op.  Mode-gated
    (``"late"`` and ``"clip_encode_start"`` are no-ops).  Returns True when
    armed (or already armed), False when late/ineligible.
    """
    mode = unet_activation_mode()
    if mode != _UNET_ACTIVATION_MODE_CLIP_GPU_READY:
        return False
    if bridge is None:
        return False
    prep = getattr(bridge, "_preparation", None)
    model_key = getattr(bridge, "_model_key", None)
    if prep is None or model_key is None or prep.unet_future is None:
        return False
    _request_id = str(request_id or "")
    if not _request_id and trace is not None:
        _request_id = str(trace.request_id)
    if not _request_id:
        return False
    # Idempotent: an armed / fired / scheduled trigger is never re-armed.
    with _UNET_ACTIVATION_LOCK:
        _existing = _UNET_ACTIVATION_STATE.get(_request_id)
        if _existing is not None and (
            _existing.get("armed", False)
            or _existing.get("fired", False)
            or _existing.get("future") is not None
        ):
            return True

    if trace is not None:
        trace.emit(_EVENT_UNET_EA_MODE, phase="execution", metadata={
            "mode": mode,
            "trigger": "clip_gpu_ready",
            "request_id": _request_id,
            "restored_instance_id": _LATEST_RESTORED_INSTANCE_ID,
            "restore_session_id": _LATEST_RESTORE_SESSION_ID,
        })

    # ── Eligibility gate (same proofs as clip_encode_start) ─────────
    _eligible, _reason, _evidence = _prove_unet_early_activation_eligible(
        bridge,
        request_id=_request_id,
        clip=clip,
        mode=mode,
        trigger="clip_gpu_ready",
    )
    _eligible_meta = dict(_evidence)
    _eligible_meta.update({
        "eligible": bool(_eligible),
        "reason": _reason,
    })
    if trace is not None:
        trace.emit(_EVENT_UNET_EA_ELIGIBLE, phase="execution", metadata=_eligible_meta)
    if not _eligible:
        if trace is not None:
            _skip_meta = {
                "mode": mode,
                "trigger": "clip_gpu_ready",
                "request_id": _request_id,
                "eligible": False,
                "reason": _reason,
                "restored_instance_id": _LATEST_RESTORED_INSTANCE_ID,
                "restore_session_id": _LATEST_RESTORE_SESSION_ID,
                "free_bytes": _evidence.get("free_bytes"),
                "required_bytes": _evidence.get("required_bytes"),
                "margin_bytes": _evidence.get("margin_bytes"),
            }
            trace.emit(_EVENT_UNET_EA_SKIPPED, phase="execution", metadata=_skip_meta)
        print(
            f"[v2.unet_early_activation] event=skipped "
            f"request_id={_request_id or 'absent'} mode={mode} trigger=clip_gpu_ready "
            f"reason={_reason} eligible=0",
            flush=True,
        )
        return False

    # ── Key with REAL retained identities (same as clip_encode_start) ──
    try:
        _retained_unet = prep.unet_future.result()
    except Exception:
        _retained_unet = None
    _key_components, _key_hash = _build_unet_activation_key(
        mode=mode,
        model_key=model_key,
        request_id=_request_id,
        unet=_retained_unet,
        weight_dtype=_unet_requested_weight_dtype(bridge, model_key),
    )
    _clip_patcher = _resolve_clip_patcher(clip)
    with _UNET_ACTIVATION_LOCK:
        _state = _UNET_ACTIVATION_STATE.get(_request_id)
        if _state is not None and (
            _state.get("armed", False)
            or _state.get("fired", False)
            or _state.get("future") is not None
        ):
            return True
        if _state is None:
            _state = _unet_activation_new_state(_request_id)
            _UNET_ACTIVATION_STATE[_request_id] = _state
        _state["owner"] = "clip_gpu_ready"
        _state["trigger"] = "clip_gpu_ready"
        _state["mode"] = mode
        _state["eligible"] = True
        _state["eligibility_reason"] = "ok"
        _state["key"] = _key_components
        _state["key_hash"] = _key_hash
        _state["clip_encode_entries"] = max(0, len(encode_entries or []))
        _state["clip_object_id"] = str(id(clip)) if clip is not None else ""
        _state["clip_patcher_object_id"] = str(id(_clip_patcher)) if _clip_patcher is not None else ""
        _state["status"] = "armed"
        _state["armed"] = True
        # Fire-time scheduling references (dropped with the request state by
        # the existing finalize path — no leaked refs).
        _state["bridge"] = bridge
        _state["prep"] = prep
        _state["model_key"] = model_key
        _state["clip"] = clip
        _state["trace"] = trace
        _state["encode_entries"] = max(0, len(encode_entries or []))
    return True


def _maybe_fire_clip_gpu_ready_activation(
    *,
    models: list[Any],
    lane_trace: "ModelLaneTrace | None",
    load_ok: bool,
    gpu_allocated_before: int | None = None,
) -> None:
    """clip_gpu_ready fire hook (existing GPU loader wrapper, outermost
    prefill-lane calls only).

    Called after a ``load_models_gpu`` call has returned AND the existing
    mutation lane has been released.  For
    ``COMFYMODAL_V2_UNET_ACTIVATION_MODE=clip_gpu_ready`` it claims the
    request-scoped single-use armed trigger and schedules the existing
    retained-UNET activation through the shared coordinator/single-flight
    path (``_unet_activation_submit``).  Requires: a successful load, the
    outermost prefill-lane call, NO registered UNET in *models*, the exact
    armed CLIP patcher identity present in *models*, and the prefill lane
    trace/request id (never ``_ACTIVE_REQUEST_TRACE`` — absent in
    coordinator threads).

    The claim is PROVEN, not asserted: after the filters the exact armed
    patcher reference is captured under the activation lock WITHOUT setting
    ``fired``, the lock is released, the patcher's load device is
    synchronized OUTSIDE the lock, the post-sync CUDA allocation delta is
    captured against the outer wrapper's ``gpu_allocated_before``
    (``_gpu_alloc_before`` — required for production; optional only for
    compatibility), and full CUDA residency is proven with
    ``_probe_clip_full_cuda_residency``.  Firing additionally requires the
    sync evidence ``ok`` AND a known positive allocation delta — a missing/
    zero/negative delta (zero-effect load) is a skip, never a fire.  On any
    failure a concise ``clip_gpu_residency_skip`` trace/log skip with
    reason/evidence (including before/after/delta) is emitted and the armed
    trigger is never burned (``fired`` stays False); ``clip_gpu_resident``
    is emitted ONLY on proven success.  On proof success the
    ``clip_gpu_resident`` evidence event is emitted BEFORE scheduling, then
    the lock is reacquired and the claim is re-verified (state still exists,
    still armed, not fired, no future, same exact patcher identity) before
    ``fired`` is set and the coordinator refs are captured.  Emits the
    concise ``clip_gpu_load_end`` marker after the lane release and BEFORE
    scheduling (with residency evidence) and never fires for
    ``late``/``clip_encode_start`` modes and never schedules twice.
    """
    if not load_ok:
        return
    if _UNET_ACTIVATION_MODE != _UNET_ACTIVATION_MODE_CLIP_GPU_READY:
        return
    if lane_trace is None or getattr(lane_trace, "_lane", "") != "prefill":
        return
    if _has_registered_unet_in_models(models):
        return
    _trace = getattr(lane_trace, "_trace", None)
    if _trace is None:
        return
    _request_id = str(getattr(_trace, "request_id", "") or "")
    if not _request_id:
        return

    # ── Phase 1: capture the exact armed patcher/state refs (no fire) ──
    # ``fired`` is intentionally NOT set while only holding the lock: the
    # claim is proven outside the lock (sync + full residency) before it is
    # consumed, so a failed proof never burns the armed trigger.
    with _UNET_ACTIVATION_LOCK:
        _state = _UNET_ACTIVATION_STATE.get(_request_id)
        if _state is None or not _state.get("armed", False) or _state.get("fired", False):
            return
        if _state.get("future") is not None:
            return
        # Exact armed CLIP patcher identity must be present in the load list.
        _armed_patcher_id = str(_state.get("clip_patcher_object_id", "") or "")
        if not _armed_patcher_id:
            return
        _exact_patcher = None
        for _m in models:
            try:
                if str(id(_m)) == _armed_patcher_id:
                    _exact_patcher = _m
                    break
                _resolved = _resolve_clip_patcher(_m)
                if _resolved is not None and str(id(_resolved)) == _armed_patcher_id:
                    _exact_patcher = _resolved
                    break
            except Exception:
                continue
        if _exact_patcher is None:
            return
        _mode = _state.get("mode", "")
        _trigger = _state.get("trigger", "clip_gpu_ready")

    # ── Phase 2: prove full CUDA residency OUTSIDE the lock ──────────
    # Sync the patcher's load device first so the probe observes completed
    # GPU work (async loads can still be in flight), capture the post-sync
    # CUDA allocation delta against the outer wrapper's before-snapshot,
    # then run the strict full-residency proof.  Firing requires the sync
    # evidence ``ok`` AND a known positive allocation delta; a failed proof
    # is a skip, never a fire.
    _sync_evidence = _sync_clip_load_device(_exact_patcher)
    _gpu_alloc_after = _gpu_allocated_bytes()
    _gpu_alloc_delta: int | None = None
    if gpu_allocated_before is not None and _gpu_alloc_after is not None:
        _gpu_alloc_delta = _gpu_alloc_after - gpu_allocated_before
    _proof = _probe_clip_full_cuda_residency(_exact_patcher)
    _proof["residency_sync"] = _sync_evidence
    _proof["gpu_allocated_before"] = gpu_allocated_before
    _proof["gpu_allocated_after"] = _gpu_alloc_after
    _proof["gpu_allocated_delta_bytes"] = _gpu_alloc_delta
    _sync_ok = bool(_sync_evidence.get("ok", False))
    _alloc_ok = bool(_gpu_alloc_delta is not None and _gpu_alloc_delta > 0)
    if not (_sync_ok and _alloc_ok and _proof.get("ok", False)):
        if not _sync_ok:
            _reason = str(_sync_evidence.get("reason", "") or "sync_not_ok")
        elif not _alloc_ok:
            _reason = (
                "gpu_alloc_delta_unknown" if _gpu_alloc_delta is None
                else "zero_gpu_alloc_delta"
            )
        else:
            _reason = str(_proof.get("reason", "residency_not_proven") or "residency_not_proven")
        if _trace is not None:
            _trace.emit(_EVENT_CLIP_GPU_RESIDENCY_SKIP, phase="execution", metadata={
                "mode": _mode,
                "trigger": _trigger,
                "request_id": _request_id,
                "status": "skip",
                "reason": _reason,
                "clip_patcher_object_id": _proof.get("clip_patcher_object_id", ""),
                "gpu_allocated_before": gpu_allocated_before,
                "gpu_allocated_after": _gpu_alloc_after,
                "gpu_allocated_delta_bytes": _gpu_alloc_delta,
                "evidence": _proof,
            })
        print(
            f"[v2.clip_gpu_ready] event=clip_gpu_residency_skip "
            f"request_id={_request_id or 'absent'} mode={_mode} trigger={_trigger} "
            f"reason={_reason} resident=0 "
            f"gpu_allocated_before={gpu_allocated_before if gpu_allocated_before is not None else 'absent'} "
            f"gpu_allocated_after={_gpu_alloc_after if _gpu_alloc_after is not None else 'absent'} "
            f"gpu_allocated_delta_bytes={_gpu_alloc_delta if _gpu_alloc_delta is not None else 'absent'}",
            flush=True,
        )
        return

    # ── Phase 3: residency evidence event BEFORE scheduling ──────────
    if _trace is not None:
        _trace.emit(_EVENT_CLIP_GPU_RESIDENT, phase="execution", metadata={
            "mode": _mode,
            "trigger": _trigger,
            "request_id": _request_id,
            "status": "resident_full",
            "reason": "ok",
            "clip_patcher_object_id": _proof.get("clip_patcher_object_id", ""),
            "gpu_allocated_before": gpu_allocated_before,
            "gpu_allocated_after": _gpu_alloc_after,
            "gpu_allocated_delta_bytes": _gpu_alloc_delta,
            "evidence": _proof,
        })
    print(
        f"[v2.clip_gpu_ready] event=clip_gpu_resident "
        f"request_id={_request_id or 'absent'} mode={_mode} trigger={_trigger} "
        f"clip_patcher_object_id={_proof.get('clip_patcher_object_id', '')} "
        f"loaded_bytes={_proof.get('clip_loaded_bytes')} "
        f"model_bytes={_proof.get('clip_model_bytes')} "
        f"gpu_allocated_delta_bytes={_gpu_alloc_delta if _gpu_alloc_delta is not None else 'absent'}",
        flush=True,
    )

    # ── Phase 4: reacquire the lock, re-verify, then claim fired ─────
    with _UNET_ACTIVATION_LOCK:
        _state = _UNET_ACTIVATION_STATE.get(_request_id)
        if _state is None or not _state.get("armed", False) or _state.get("fired", False):
            return
        if _state.get("future") is not None:
            return
        if str(_state.get("clip_patcher_object_id", "") or "") != str(id(_exact_patcher)):
            return
        # Atomic armed→scheduled claim: a second qualifying CLIP load for
        # the same request can never fire again.
        _state["fired"] = True
        _state["clip_residency_status"] = "resident_full"
        _bridge = _state.get("bridge")
        _prep = _state.get("prep")
        _model_key = _state.get("model_key")
        _clip = _state.get("clip")
        _encode_entries = _state.get("encode_entries", 0)
        _key_components = _state.get("key") or {}
        _key_hash = _state.get("key_hash", "")
        _mode = _state.get("mode", "")
        _trigger = _state.get("trigger", "clip_gpu_ready")
    if _bridge is None or _prep is None or _model_key is None:
        return
    # Concise marker AFTER the lane release, BEFORE scheduling, carrying the
    # residency evidence for the load-end marker.
    if _trace is not None:
        _load_end_meta: dict[str, Any] = {
            "mode": _mode,
            "trigger": _trigger,
            "request_id": _request_id,
            "clip_patcher_object_id": _armed_patcher_id,
            "lane": "prefill",
            "clip_residency_status": _proof.get("clip_residency_status", "resident_full"),
            "clip_loaded_bytes": _proof.get("clip_loaded_bytes"),
            "clip_model_bytes": _proof.get("clip_model_bytes"),
            "residency_sync": _sync_evidence,
            "gpu_allocated_before": gpu_allocated_before,
            "gpu_allocated_after": _gpu_alloc_after,
            "gpu_allocated_delta_bytes": _gpu_alloc_delta,
        }
        _trace.emit(_EVENT_CLIP_GPU_LOAD_END, phase="execution", metadata=_load_end_meta)
    _unet_activation_submit(
        _bridge,
        request_id=_request_id, trace=_trace, prep=_prep,
        model_key=_model_key, mode=_mode, trigger=_trigger,
        clip=_clip, encode_entries=_encode_entries,
        key_components=_key_components, key_hash=_key_hash,
        create_state=False,
        residency_evidence=_proof,
    )


# ── Exact CLIP conditioning cache: identity + scheduling helpers ────────
# The exact-conditioning cache reads authoritative identities at the real
# prefill boundary and, on an exact hit, schedules the SAME retained-UNET
# activation through the existing shared scheduling core
# (``_unet_activation_submit``) with ``trigger=conditioning_cache_hit`` —
# never a second activation implementation, and never a wait for the
# clip_gpu_ready fire event that will not happen when no CLIP encode runs.


def _read_models_generation() -> str:
    """Authoritative models-volume generation (weights/content identity)."""
    try:
        import sys as _sys_gen
        _comfyapp = _sys_gen.modules.get("comfyapp")
        if _comfyapp is None:
            return ""
        _fn = getattr(_comfyapp, "_read_models_generation_record", None)
        if callable(_fn):
            return str((_fn() or {}).get("generation", "") or "")
    except Exception:
        pass
    return ""


def _read_custom_nodes_generation() -> str:
    """Authoritative custom-nodes generation (custom-node identity)."""
    try:
        import sys as _sys_cng
        _comfyapp = _sys_cng.modules.get("comfyapp")
        if _comfyapp is None:
            return ""
        _fn = getattr(_comfyapp, "_read_custom_nodes_generation_record", None)
        if callable(_fn):
            return str((_fn() or {}).get("generation", "") or "")
    except Exception:
        pass
    return ""


def _read_effective_options_hash(trace: RuntimeTrace | None) -> str:
    """Read the effective production-options hash published at method entry.

    Falls back to trace metadata; returns '' when unavailable (the cache
    then fails closed rather than keying without preset bindings).
    """
    if trace is not None:
        try:
            for _ev in trace.events:
                _meta = _ev.metadata or {}
                if _ev.name == "remote_method_entry" and _meta.get("effective_options_hash"):
                    return str(_meta["effective_options_hash"])
        except Exception:
            pass
        try:
            _meta_val = (trace._metadata or {}).get("effective_options_hash", "")
            if _meta_val:
                return str(_meta_val)
        except Exception:
            pass
    return ""


def _read_effective_workflow_hash(trace: RuntimeTrace | None) -> str:
    """Read the authoritative request workflow hash from the runtime trace."""
    if trace is None:
        return ""
    try:
        for event in reversed(trace.events):
            metadata = event.metadata or {}
            if event.name in {"remote_method_entry", "method_entry"}:
                value = metadata.get("workflow_hash") or metadata.get("source_workflow_hash")
                if value:
                    return str(value)
    except Exception:
        pass
    try:
        metadata = trace._metadata or {}
        return str(
            metadata.get("workflow_hash")
            or metadata.get("source_workflow_hash")
            or ""
        )
    except Exception:
        return ""


def _clip_cache_tokenizer_identity(clip: Any) -> str:
    tokenizer = getattr(clip, "tokenizer", None)
    if tokenizer is None:
        return ""
    identity: dict[str, Any] = {
        "class": f"{type(tokenizer).__module__}.{type(tokenizer).__qualname__}",
        "options": dict(getattr(clip, "tokenizer_options", {}) or {}),
    }
    for name in ("name_or_path", "vocab_size", "model_max_length"):
        value = getattr(tokenizer, name, None)
        if isinstance(value, (str, int, float, bool)) or value is None:
            identity[name] = value
    try:
        return stable_hash(identity)
    except Exception:
        return ""


def _clip_cache_compute_dtype(clip: Any) -> str:
    for owner in (
        getattr(clip, "patcher", None),
        getattr(clip, "cond_stage_model", None),
    ):
        if owner is None:
            continue
        try:
            value = owner.model_dtype() if callable(getattr(owner, "model_dtype", None)) else getattr(owner, "dtype", None)
            if value is not None:
                return str(value)
        except Exception:
            continue
        for attr_name in ("compute_dtype", "model_compute_dtype", "manual_cast_dtype"):
            try:
                value = getattr(owner, attr_name, None)
                if value is not None:
                    return str(value)
            except Exception:
                continue
        model = getattr(owner, "model", None)
        if model is not None:
            for attr_name in ("compute_dtype", "model_compute_dtype", "manual_cast_dtype", "dtype"):
                try:
                    value = getattr(model, attr_name, None)
                    if value is not None:
                        return str(value)
                except Exception:
                    continue
        try:
            parameters = getattr(owner, "parameters", None)
            parameter = next(iter(parameters())) if callable(parameters) else None
            if parameter is not None:
                return str(parameter.dtype)
        except Exception:
            continue
    return ""


def _build_clip_conditioning_cache_context(
    bridge: "V2LoaderBridge",
    *,
    clip: Any = None,
    trace: RuntimeTrace | None = None,
    request_id: str = "",
) -> dict[str, Any]:
    """Build the shared (non-entry) key context for the exact cache.

    Every conditioning-affecting input available at this boundary is
    included; per-entry fields (text, role, node class) are merged by the
    cache module.  Missing identities fail closed inside the cache module.
    """
    _model_key = getattr(bridge, "_model_key", None)
    ctx: dict[str, Any] = {
        "request_id": str(request_id or ""),
        "clip_identity": "",
        "clip_type": "",
        "loader_class": "",
        "filenames": [],
        "weight_dtype": "",
        "compute_dtype": _clip_cache_compute_dtype(clip),
        "tokenizer_identity": _clip_cache_tokenizer_identity(clip),
        "entry_layer": getattr(clip, "layer_idx", "") if clip is not None else "",
        "entry_skip": getattr(clip, "skip", "") if clip is not None else "",
    }
    if _model_key is not None:
        ctx["clip_identity"] = str(getattr(_model_key, "clip_identity", "") or "")
        ctx["clip_type"] = str(getattr(_model_key, "clip_type", "") or "")
    # CLIP loader identity + weight dtype from the concrete loader request
    # list (base fallback; each entry carries its authoritative values).
    try:
        for _req in bridge._request_list("clip"):
            _lc = str(_req.get("loader_class", "") or "")
            if _lc:
                ctx["loader_class"] = _lc
            _fn = _req.get("clip_name")
            if _fn:
                ctx["filenames"] = [str(_fn)]
            elif _req.get("clip_name1") and _req.get("clip_name2"):
                ctx["filenames"] = [str(_req["clip_name1"]), str(_req["clip_name2"])]
            _wd = str(_req.get("weight_dtype", "") or "")
            if _wd:
                ctx["weight_dtype"] = _wd
            break
    except Exception:
        pass
    _modal_hashes = _unet_activation_modal_hashes()
    _trace_workflow_hash = _read_effective_workflow_hash(trace)
    ctx["model_generation"] = str(
        getattr(_model_key, "model_volume_generation", "") or _read_models_generation() or ""
    )
    ctx["custom_node_generation"] = str(
        _modal_hashes.get("custom_node_generation", "")
        or _read_custom_nodes_generation()
        or ""
    )
    ctx["deployment_hash"] = str(
        _modal_hashes.get("deployment_hash", "")
        or os.environ.get("COMFYMODAL_V2_DEPLOYMENT_COMBINED_HASH", "")
        or ""
    )
    ctx["workflow_hash"] = str(
        _trace_workflow_hash
        or getattr(bridge, "_workflow_hash", "")
        or _modal_hashes.get("workflow_hash", "")
        or ""
    )
    ctx["production_options_hash"] = str(
        _read_effective_options_hash(trace)
        or getattr(bridge, "_production_options_hash", "")
        or ""
    )
    try:
        import torch as _torch
        ctx["torch_version"] = str(_torch.__version__)
        ctx["torch_num_threads"] = int(_torch.get_num_threads())
    except Exception:
        ctx["torch_version"] = ""
        ctx["torch_num_threads"] = 0
    return ctx


def _schedule_unet_activation_conditioning_cache_hit(
    bridge: "V2LoaderBridge",
    *,
    trace: RuntimeTrace | None = None,
    request_id: str = "",
    clip: Any = None,
    encode_entries: list[dict[str, Any]] | None = None,
) -> bool:
    """Schedule the retained-UNET activation on an exact cache hit.

    Uses ONLY the existing eligibility proofs, identity key, and shared
    scheduling core (``_unet_activation_submit``) with
    ``trigger=conditioning_cache_hit``.  A cache hit means no CLIP encode
    and therefore no CLIP GPU load, so the clip_gpu_ready fire event will
    never occur — scheduling directly here avoids waiting for it.  An
    ineligible outcome preserves the normal late-load fallback.
    """
    mode = unet_activation_mode()
    if bridge is None:
        return False
    prep = getattr(bridge, "_preparation", None)
    model_key = getattr(bridge, "_model_key", None)
    if prep is None or model_key is None or prep.unet_future is None:
        return False
    _request_id = str(request_id or "")
    if not _request_id and trace is not None:
        _request_id = str(trace.request_id)
    if not _request_id:
        return False
    with _UNET_ACTIVATION_LOCK:
        _existing = _UNET_ACTIVATION_STATE.get(_request_id)
        if _existing is not None and _existing.get("future") is not None:
            return True
    if trace is not None:
        trace.emit(_EVENT_UNET_EA_MODE, phase="execution", metadata={
            "mode": mode,
            "trigger": _UNET_ACTIVATION_TRIGGER_CACHE_HIT,
            "request_id": _request_id,
            "restored_instance_id": _LATEST_RESTORED_INSTANCE_ID,
            "restore_session_id": _LATEST_RESTORE_SESSION_ID,
        })
    _eligible, _reason, _evidence = _prove_unet_early_activation_eligible(
        bridge,
        request_id=_request_id,
        clip=None,
        mode=mode,
        trigger=_UNET_ACTIVATION_TRIGGER_CACHE_HIT,
    )
    _eligible_meta = dict(_evidence)
    _eligible_meta.update({"eligible": bool(_eligible), "reason": _reason})
    if trace is not None:
        trace.emit(_EVENT_UNET_EA_ELIGIBLE, phase="execution", metadata=_eligible_meta)
    if not _eligible:
        if trace is not None:
            trace.emit(_EVENT_UNET_EA_SKIPPED, phase="execution", metadata={
                "mode": mode,
                "trigger": _UNET_ACTIVATION_TRIGGER_CACHE_HIT,
                "request_id": _request_id,
                "eligible": False,
                "reason": _reason,
                "restored_instance_id": _LATEST_RESTORED_INSTANCE_ID,
                "restore_session_id": _LATEST_RESTORE_SESSION_ID,
            })
        print(
            f"[v2.unet_early_activation] event=skipped "
            f"request_id={_request_id or 'absent'} mode={mode} "
            f"trigger={_UNET_ACTIVATION_TRIGGER_CACHE_HIT} reason={_reason} eligible=0",
            flush=True,
        )
        return False
    try:
        _retained_unet = prep.unet_future.result()
    except Exception:
        _retained_unet = None
    _key_components, _key_hash = _build_unet_activation_key(
        mode=mode,
        model_key=model_key,
        request_id=_request_id,
        unet=_retained_unet,
        weight_dtype=_unet_requested_weight_dtype(bridge, model_key),
    )
    scheduled = _unet_activation_submit(
        bridge,
        request_id=_request_id, trace=trace, prep=prep, model_key=model_key,
        mode=mode, trigger=_UNET_ACTIVATION_TRIGGER_CACHE_HIT,
        clip=None, encode_entries=encode_entries,
        key_components=_key_components, key_hash=_key_hash,
    )
    if scheduled:
        print(
            f"[v2.unet_early_activation] trigger={_UNET_ACTIVATION_TRIGGER_CACHE_HIT}",
            flush=True,
        )
    return scheduled


def record_clip_encode_start(
    request_id: str,
    start_counters: Mapping[str, Any] | None,
) -> None:
    """Record the ACTUAL prefill encode start into the request activation state.

    ``clip_encode_start_mono_ns`` must represent the real encode start
    boundary (captured immediately before the encode loop) — never the
    scheduling time.  The schedule/submit timestamp stays separate in
    ``submitted_mono_ns``.  No-op when no activation state exists (safe when
    no early future was scheduled) or when the counters carry no monotonic
    clock (never fabricated).
    """
    if not request_id:
        return
    _state = _unet_activation_get(request_id)
    if _state is None:
        return
    _mono = int((start_counters or {}).get("mono_ns", 0) or 0)
    if _mono:
        _state["clip_encode_start_mono_ns"] = _mono


def record_clip_encode_end(
    request_id: str,
    start_counters: Mapping[str, Any] | None,
    end_counters: Mapping[str, Any] | None,
) -> None:
    """Record the prefill encode interval into the request activation state."""
    if not request_id:
        return
    _state = _unet_activation_get(request_id)
    if _state is None:
        return
    _deltas = _phase_counter_deltas(dict(start_counters), dict(end_counters))
    _state["clip_encode_end_mono_ns"] = int((end_counters or {}).get("mono_ns", 0) or 0)
    _state["clip_encode_wall_ms"] = float(_deltas.get("wall_ms", 0.0) or 0.0)
    _state["clip_encode_process_cpu_ms"] = float(_deltas.get("process_cpu_ms") or 0.0)
    _state["clip_encode_thread_cpu_ms"] = float(_deltas.get("thread_cpu_ms") or 0.0)


def _validate_early_activated_unet(unet: Any, state: dict[str, Any]) -> tuple[bool, str]:
    """Validate diffusion identity / residency / cache / dtype / device of the
    early-activated retained UNET at graph demand.  The patcher object may
    legitimately differ (CacheDiT wrapper / re-attach) as long as the
    resolved diffusion model matches.  Never raises."""
    from .unet_forward_probe import resolve_diffusion_model

    _patcher, _dm = resolve_diffusion_model(unet)
    if _dm is None:
        return False, "diffusion_missing"
    _key = state.get("key") or {}
    _expected_dm = _key.get("unet_diffusion_object_id", "")
    if _expected_dm and _expected_dm != str(id(_dm)):
        return False, "diffusion_identity_mismatch"
    _evidence = _probe_early_activation_evidence(unet)
    if _evidence.get("residency_status") == "cpu_resident":
        return False, "cpu_resident"
    if not _evidence.get("cache_present"):
        return False, "cache_missing"
    _device = _key.get("device", "")
    if _device:
        _cur = _evidence.get("current_device", "")
        if _cur and str(_cur) not in ("", "absent") and str(_cur) != str(_device):
            return False, "device_mismatch"
    _expected_dtype = _key.get("compute_dtype", "")
    if _expected_dtype:
        try:
            _md = getattr(unet, "model_dtype", None)
            _actual_dtype = str(_md()) if callable(_md) else ""
        except Exception:
            _actual_dtype = ""
        if _actual_dtype and _actual_dtype != _expected_dtype:
            return False, "dtype_mismatch"
    return True, "ok"


def join_unet_early_activation(
    bridge: "V2LoaderBridge",
    *,
    unet: Any,
    trace: RuntimeTrace | None = None,
    request_id: str = "",
) -> dict[str, Any]:
    """Find and join the request's early activation future at graph/sampler
    demand.  Runs OUTSIDE the mutation lane.  Validates diffusion identity,
    residency, cache, dtype and device; on success the original sampler load
    path continues as a cache validation.  On any non-ready terminal outcome
    exactly one caller elects the unchanged late fallback (atomic, never
    overwritten, never racing a pending future — the future is joined to
    terminal before any election).  Mode-gated: only the active modes
    (``clip_encode_start`` / ``clip_gpu_ready``) join the future; an explicit
    ``conditioning_cache_hit`` future is also joined in late mode."""
    _request_id = str(request_id or "")
    if not _request_id and trace is not None:
        _request_id = str(trace.request_id)
    _state = _unet_activation_get(_request_id)
    _cache_hit_pending = bool(
        _state is not None
        and _state.get("trigger") == _UNET_ACTIVATION_TRIGGER_CACHE_HIT
        and _state.get("future") is not None
    )
    if (
        unet_activation_mode() not in _UNET_ACTIVATION_MODE_ACTIVE
        and not _cache_hit_pending
    ):
        return {"scheduled": False, "status": "mode_late", "terminal": False,
                "valid": False, "reason": "", "join_wait_ms": 0.0}
    if _state is None or _state.get("future") is None:
        return {"scheduled": False, "status": "not_scheduled", "terminal": False,
                "valid": False, "reason": "", "join_wait_ms": 0.0}
    _state["sampler_patcher_object_id"] = str(id(unet)) if unet is not None else ""
    _demand_ns = time.monotonic_ns()
    _state["join_demand_mono_ns"] = _demand_ns
    _future = _state["future"]
    try:
        _future.result()
    except Exception as exc:
        with _UNET_ACTIVATION_LOCK:
            _state["terminal"] = True
            _state["status"] = "failed"
            _state["reason"] = "future_error"
            _state["error"] = str(exc)[:200]
            _state["terminal_mono_ns"] = time.monotonic_ns()
        return _elect_early_activation_fallback(
            _state, trace, _request_id,
            reason="future_error", error=str(exc)[:200],
            join_wait_ms=round((time.monotonic_ns() - _demand_ns) / 1_000_000, 3),
        )
    _join_wait_ms = round((time.monotonic_ns() - _demand_ns) / 1_000_000, 3)
    _state["join_completed_mono_ns"] = time.monotonic_ns()
    _state["join_wait_ms"] = _join_wait_ms
    with _UNET_ACTIVATION_LOCK:
        _status = _state.get("status", "")
        _terminal = bool(_state.get("terminal", False))
    if _terminal and _status == "ready":
        _valid, _reason = _validate_early_activated_unet(unet, _state)
        if _valid:
            if trace is not None:
                trace.emit(_EVENT_UNET_EA_CONSUMED, phase="execution", metadata={
                    "mode": _state.get("mode", ""),
                    "request_id": _request_id,
                    "key_hash": _state.get("key_hash", ""),
                    "join_wait_ms": _join_wait_ms,
                    "transfer_count": _state.get("transfer_count", 0),
                    "cache_present": bool(_state.get("cache_present", False)),
                })
            return {"scheduled": True, "status": "ready", "terminal": True,
                    "valid": True, "reason": "", "join_wait_ms": _join_wait_ms}
        return _elect_early_activation_fallback(
            _state, trace, _request_id,
            reason=f"invalid:{_reason}", join_wait_ms=_join_wait_ms,
        )
    if _terminal:
        return _elect_early_activation_fallback(
            _state, trace, _request_id,
            reason=str(_state.get("reason", _status) or _status),
            join_wait_ms=_join_wait_ms,
        )
    return _elect_early_activation_fallback(
        _state, trace, _request_id, reason="non_terminal", join_wait_ms=_join_wait_ms,
    )


def _build_unet_early_activation_reconciliation(state: dict[str, Any]) -> dict[str, Any]:
    """Request-end derived intervals (waterfall arithmetic)."""
    _clip_start = state.get("clip_encode_start_mono_ns") or 0
    _clip_end = state.get("clip_encode_end_mono_ns") or 0
    _act_start = state.get("submitted_mono_ns") or 0
    _act_end = state.get("terminal_mono_ns") or 0
    clip_interval_ms = _bounded_delta_ms(_clip_start or None, _clip_end or None)
    activation_interval_ms = _bounded_delta_ms(_act_start or None, _act_end or None)
    _overlap_ms: float | None = None
    _sequential_ms: float | None = None
    _combined_ms: float | None = None
    _efficiency: float | None = None
    if (
        isinstance(clip_interval_ms, float)
        and isinstance(activation_interval_ms, float)
        and _clip_start and _clip_end and _act_start and _act_end
    ):
        _start = max(_clip_start, _act_start)
        _end = min(_clip_end, _act_end)
        _overlap = max(0, _end - _start)
        _overlap_ms = round(_overlap / 1_000_000, 3)
        _sequential_ms = round(clip_interval_ms + activation_interval_ms, 3)
        _combined_ms = round(max(0.0, _sequential_ms - _overlap_ms), 3)
        if _sequential_ms > 0:
            _efficiency = round(_overlap_ms / _sequential_ms, 4)
    _clip_slowdown_ms: float | None = None
    if isinstance(clip_interval_ms, float):
        _excess = clip_interval_ms - float(state.get("clip_encode_process_cpu_ms", 0.0) or 0.0)
        _clip_slowdown_ms = round(max(0.0, _excess), 3)
    return {
        "request_id": state.get("request_id", ""),
        "restored_instance_id": _LATEST_RESTORED_INSTANCE_ID,
        "restore_session_id": _LATEST_RESTORE_SESSION_ID,
        "mode": state.get("mode", ""),
        "trigger": state.get("trigger", ""),
        "key_hash": state.get("key_hash", ""),
        "status": state.get("status", ""),
        "terminal": bool(state.get("terminal", False)),
        "fallback_elected": bool(state.get("fallback_elected", False)),
        "fallback_reason": state.get("fallback_reason", ""),
        "reason": state.get("reason", ""),
        "transfer_count": state.get("transfer_count", 0),
        "clip_interval_ms": clip_interval_ms,
        "activation_interval_ms": activation_interval_ms,
        "overlap_ms": _overlap_ms,
        "sequential_equivalent_ms": _sequential_ms,
        "combined_interval_ms": _combined_ms,
        "efficiency": _efficiency,
        "clip_slowdown_ms": _clip_slowdown_ms,
        "graph_visible_wait_ms": state.get("join_wait_ms", 0.0) or 0.0,
        "join_wait_ms": state.get("join_wait_ms", 0.0) or 0.0,
        "clip_encode_wall_ms": state.get("clip_encode_wall_ms", 0.0),
        "clip_encode_process_cpu_ms": state.get("clip_encode_process_cpu_ms", 0.0),
        "lane_wait_ms": state.get("lane_wait_ms", 0.0),
        "load_wall_ms": state.get("load_wall_ms", 0.0),
        "load_thread_cpu_ms": state.get("load_thread_cpu_ms"),
        "load_process_cpu_ms": state.get("load_process_cpu_ms"),
        "submitted_mono_ns": state.get("submitted_mono_ns", 0) or 0,
        "worker_started_mono_ns": state.get("worker_started_mono_ns", 0) or 0,
        "terminal_mono_ns": state.get("terminal_mono_ns", 0) or 0,
        "clip_encode_start_mono_ns": state.get("clip_encode_start_mono_ns", 0) or 0,
        "clip_encode_end_mono_ns": state.get("clip_encode_end_mono_ns", 0) or 0,
        "gpu_free_bytes": state.get("gpu_free_bytes"),
        "gpu_required_bytes": state.get("gpu_required_bytes"),
        "safety_margin_bytes": state.get("safety_margin_bytes"),
        "gpu_allocated_before": state.get("gpu_allocated_before"),
        "gpu_allocated_after": state.get("gpu_allocated_after"),
        "gpu_allocated_delta_bytes": state.get("gpu_allocated_delta_bytes"),
        "clip_retained": bool(state.get("clip_retained", False)),
        "clip_resident": bool(state.get("clip_resident", False)),
        "clip_residency_status": state.get("clip_residency_status", ""),
        "cache_present": bool(state.get("cache_present", False)),
        "eligible": bool(state.get("eligible", False)),
        "eligibility_reason": state.get("eligibility_reason", ""),
        "clip_encode_entries": state.get("clip_encode_entries", 0),
        "unet_patcher_object_id": state.get("unet_patcher_object_id", ""),
        "unet_diffusion_object_id": state.get("unet_diffusion_object_id", ""),
        "sampler_patcher_object_id": state.get("sampler_patcher_object_id", ""),
        "clip_object_id": state.get("clip_object_id", ""),
    }


def _emit_unet_early_activation_reconciliation_line(
    record: dict[str, Any],
) -> None:
    try:
        _parts = []
        for _k, _v in record.items():
            if _k == "request_id":
                continue
            _parts.append(f"{_k}={_v if _v is not None else 'absent'}")
        print(
            f"[v2.unet_early_activation] event=reconciliation "
            f"request_id={record.get('request_id') or 'absent'} " + " ".join(_parts),
            flush=True,
        )
    except Exception:
        pass


def finalize_unet_early_activation(
    request_id: str,
    *,
    trace: RuntimeTrace | None = None,
) -> dict[str, Any] | None:
    """Request-end cleanup + reconciliation.

    Emits ``unet_early_activation_reconciliation`` with the request-end
    derived intervals, marks any still-pending activation cancelled (the
    worker observes this before its GPU mutation), and drops the request
    state.  Never leaves an activation future or model mutation pending —
    the coordinator pool shutdown in ``close_workers`` terminates any
    in-flight worker."""
    if not request_id:
        return None
    with _UNET_ACTIVATION_LOCK:
        _state = _UNET_ACTIVATION_STATE.pop(request_id, None)
    if _state is None:
        return None
    _future = _state.get("future")
    with _UNET_ACTIVATION_LOCK:
        if not _state.get("terminal", False):
            _state["status"] = "cancelled"
            _state["cancelled"] = True
            _state["terminal"] = True
            _state["reason"] = "request_finalized"
            _state["terminal_mono_ns"] = time.monotonic_ns()
        if _future is not None and not _future.done():
            try:
                _future.cancel()
            except Exception:
                pass
    _record = _build_unet_early_activation_reconciliation(_state)
    if trace is not None:
        trace.emit(_EVENT_UNET_EA_RECONCILIATION, phase="execution", metadata=_record)
    _emit_unet_early_activation_reconciliation_line(_record)
    return _record


# ═══════════════════════════════════════════════════════════════════════
# V2 VAE early activation (COMFYMODAL_V2_VAE_ACTIVATION_MODE)
# ═══════════════════════════════════════════════════════════════════════
# Mode "late" (default) preserves existing behavior exactly: the VAE may be
# submitted during restore preparation (prepare_vae) and is served at graph
# VAELoader demand through the original loader.  The ONLY allowed opt-in
# value is "sampling_end" (V2-only production timing): restore/preparation
# never submits a VAE future; instead the VAE GPU/cache activation is
# scheduled exactly once, through the existing coordinator pool and its
# shared mutation lane, at the real SAMPLER_SAMPLE sampling_end boundary
# (hooked from runtime_executor._build_sampling_wrapper — never from
# progress/milestones).  The worker performs the normal ComfyUI GPU/cache
# load through the existing model-management wrappers on the shared
# mutation lane; VAEDecode demand joins the same future outside the lane.
# Any resolution/load/validation failure falls back to the unchanged
# original graph loader path.
_VAE_ACTIVATION_MODE_LATE = "late"
_VAE_ACTIVATION_MODE_SAMPLING_END = "sampling_end"
_VAE_ACTIVATION_MODE_VALID = frozenset(
    {_VAE_ACTIVATION_MODE_LATE, _VAE_ACTIVATION_MODE_SAMPLING_END}
)
# Modes that schedule/join the VAE activation future.  Late mode is NOT
# included — it must never create state, join, or add graph waits.
_VAE_ACTIVATION_MODE_ACTIVE = frozenset({_VAE_ACTIVATION_MODE_SAMPLING_END})

_EVENT_VAE_EA_MODE = "vae_early_activation_mode"
_EVENT_VAE_EA_SCHEDULED = "vae_early_activation_scheduled"
_EVENT_VAE_EA_LOAD_START = "vae_early_activation_load_start"
_EVENT_VAE_EA_TERMINAL = "vae_early_activation_terminal"
_EVENT_VAE_EA_CONSUMED = "vae_early_activation_consumed"
_EVENT_VAE_EA_SKIPPED = "vae_early_activation_skipped"
_EVENT_VAE_EA_FAILED = "vae_early_activation_failed"
_EVENT_VAE_EA_INVALID = "vae_early_activation_invalid"
_EVENT_VAE_EA_CANCELLED = "vae_early_activation_cancelled"
_EVENT_VAE_EA_FALLBACK = "vae_early_activation_fallback"
_EVENT_VAE_EA_RECONCILIATION = "vae_early_activation_reconciliation"


def _resolve_vae_activation_mode(raw: str) -> str:
    """Normalize a ``COMFYMODAL_V2_VAE_ACTIVATION_MODE`` value.

    The ONLY allowed opt-in value is exactly ``"sampling_end"`` (V2-only).
    ``"late"`` is the default.  Any other value — including any historical
    ``"early"`` spelling — falls back to ``"late"`` so existing behavior is
    never altered by a typo or an unknown value.
    """
    value = str(raw or "").strip().lower()
    if value == _VAE_ACTIVATION_MODE_SAMPLING_END:
        return _VAE_ACTIVATION_MODE_SAMPLING_END
    return _VAE_ACTIVATION_MODE_LATE


_VAE_ACTIVATION_MODE: str = _resolve_vae_activation_mode(
    os.environ.get("COMFYMODAL_V2_VAE_ACTIVATION_MODE", _VAE_ACTIVATION_MODE_LATE)
)
_VAE_ACTIVATION_MODE_LOG_EMITTED: bool = False


def vae_activation_mode() -> str:
    """Return the effective VAE activation mode.

    ``"late"`` (default) preserves existing behavior exactly; the only
    allowed opt-in value is ``"sampling_end"``.  Logs the parsed effective
    mode once per process on first access.
    """
    global _VAE_ACTIVATION_MODE_LOG_EMITTED
    if not _VAE_ACTIVATION_MODE_LOG_EMITTED:
        _VAE_ACTIVATION_MODE_LOG_EMITTED = True
        try:
            print(
                f"[v2.vae_early_activation] event=mode "
                f"mode={_VAE_ACTIVATION_MODE} "
                f"env_raw={os.environ.get('COMFYMODAL_V2_VAE_ACTIVATION_MODE', 'late')} "
                f"restored_instance_id={_LATEST_RESTORED_INSTANCE_ID or 'absent'} "
                f"restore_session_id={_LATEST_RESTORE_SESSION_ID or 'absent'}",
                flush=True,
            )
        except Exception:
            pass
    return _VAE_ACTIVATION_MODE


# ── Request-scoped VAE activation state ────────────────────────────────
# One dict per request_id: future / key / trigger / owner / terminal /
# error plus post-load validation evidence.  Bounded (oldest request ids
# are evicted first) and never persisted across restored containers — the
# key never contains the restored identity and the state is dropped by
# request-end cleanup.

_VAE_ACTIVATION_STATE: dict[str, dict[str, Any]] = {}
_VAE_ACTIVATION_LOCK: RLock = RLock()
_VAE_ACTIVATION_MAX = 64


def _vae_activation_new_state(request_id: str) -> dict[str, Any]:
    return {
        "request_id": request_id,
        "future": None,
        "owner": "sampling_end",
        "trigger": "sampling_end",
        "mode": _VAE_ACTIVATION_MODE,
        "key": {},
        "key_hash": "",
        "status": "idle",
        "terminal": False,
        "cancelled": False,
        "joined": False,
        "fallback_elected": False,
        "fallback_reason": "",
        "reason": "",
        "error": "",
        "transfer_count": 0,
        "vae": None,
        "vae_object_id": "",
        "vae_patcher_object_id": "",
        "vae_resolution_source": "",
        "vae_identity": "",
        "sampling_end_mono_ns": 0,
        "sampling_end_duration_ms": 0.0,
        "submitted_mono_ns": 0,
        "worker_started_mono_ns": 0,
        "terminal_mono_ns": 0,
        "join_demand_mono_ns": 0,
        "join_completed_mono_ns": 0,
        "join_wait_ms": 0.0,
        "lane_wait_ms": 0.0,
        "load_wall_ms": 0.0,
        "gpu_free_bytes": None,
        "gpu_required_bytes": None,
        "safety_margin_bytes": None,
        "gpu_allocated_before": None,
        "gpu_allocated_after": None,
        "gpu_allocated_delta_bytes": None,
        "cache_present": False,
        "current_device": "",
        "load_device": "",
        "compute_dtype": "",
        "loaded_bytes": None,
        "model_bytes": None,
        "residency_status": "",
        "diagnostics": {},
    }


def _vae_activation_get(request_id: str) -> dict[str, Any] | None:
    """Return the VAE activation state dict for *request_id* (live ref)."""
    if not request_id:
        return None
    with _VAE_ACTIVATION_LOCK:
        return _VAE_ACTIVATION_STATE.get(request_id)


def _vae_activation_trim() -> None:
    """Evict the OLDEST request ids when the bound is exceeded."""
    with _VAE_ACTIVATION_LOCK:
        if len(_VAE_ACTIVATION_STATE) > _VAE_ACTIVATION_MAX:
            _excess = len(_VAE_ACTIVATION_STATE) - _VAE_ACTIVATION_MAX
            for _stale in list(_VAE_ACTIVATION_STATE.keys())[:_excess]:
                _VAE_ACTIVATION_STATE.pop(_stale, None)


# ── Identity key ───────────────────────────────────────────────────────


def _build_vae_activation_key(
    *,
    mode: str,
    model_key: ModelRestoreKey,
    request_id: str,
    vae: Any,
    source: str,
    sampling_end_mono_ns: int,
) -> tuple[dict[str, Any], str]:
    """Build the request-scoped identity key for the VAE early activation.

    Covers the exact VAE object identity, the VAE patcher identity, the
    requested vae identity, resolution source, compute dtype, and target
    device.  Returns ``(components, key_hash)``.
    """
    _vae_id = str(id(vae)) if vae is not None else ""
    _patcher_id = ""
    _device = ""
    _compute_dtype = ""
    if vae is not None:
        try:
            _patcher = getattr(vae, "patcher", None)
            if _patcher is not None:
                _patcher_id = str(id(_patcher))
                _dev = getattr(_patcher, "load_device", None)
                if _dev is not None:
                    _device = str(_dev)
                _md = getattr(_patcher, "model_dtype", None)
                _md_value = _md() if callable(_md) else None
                _compute_dtype = str(_md_value) if _md_value is not None else ""
            if not _compute_dtype:
                _compute_dtype = str(getattr(vae, "vae_dtype", "") or "")
        except Exception:
            pass
    if not _device:
        try:
            import comfy.model_management as _mm_vk
            _device = str(_mm_vk.get_torch_device())
        except Exception:
            _device = ""
    components = {
        "mode": mode,
        "request_id": request_id,
        "vae_identity": str(model_key.vae_identity) if model_key is not None else "",
        "vae_object_id": _vae_id,
        "vae_patcher_object_id": _patcher_id,
        "vae_resolution_source": source,
        "compute_dtype": _compute_dtype,
        "device": _device,
        "sampling_end_mono_ns": int(sampling_end_mono_ns or 0),
    }
    key_hash = stable_hash(components)[:24]
    return components, key_hash


# ── Live ComfyUI model-management helpers for the VAE worker ──────────


def _vae_patcher_loaded_bytes(patcher: Any) -> int:
    """Return the VAE patcher's loaded (GPU) bytes via its ModelPatcher API."""
    try:
        _fn = getattr(patcher, "loaded_size", None)
        if callable(_fn):
            return int(_fn() or 0)
    except Exception:
        pass
    return 0


def _module_device(module: Any) -> str:
    if module is None:
        return ""
    try:
        for tensor in module.parameters():
            return str(tensor.device)
    except Exception:
        pass
    try:
        for tensor in module.buffers():
            return str(tensor.device)
    except Exception:
        pass
    return ""


def _probe_vae_activation_evidence(vae: Any, patcher: Any) -> dict[str, Any]:
    """Read-only residency/cache/device/dtype evidence after the early VAE
    load.  Never raises, never transfers or mutates tensors, never mutates
    ComfyUI cache lists.  Reuses the real model-management cache/loaded-size
    APIs only — no fabricated evidence.
    """
    evidence: dict[str, Any] = {
        "vae_object_id": str(id(vae)) if vae is not None else "",
        "vae_patcher_object_id": str(id(patcher)) if patcher is not None else "",
        "cache_present": False,
        "current_device": "",
        "load_device": "",
        "compute_dtype": "",
        "loaded_bytes": None,
        "model_bytes": None,
        "residency_status": "unknown",
    }
    if patcher is not None:
        try:
            import comfy.model_management as _mm_vae
            _loaded = getattr(_mm_vae, "current_loaded_models", None)
            if _loaded is not None:
                for _lm in _loaded:
                    if getattr(_lm, "model", None) is patcher:
                        evidence["cache_present"] = True
                        break
        except Exception:
            pass
        try:
            _dev = getattr(patcher, "load_device", None)
            if _dev is not None:
                evidence["load_device"] = str(_dev)
        except Exception:
            pass
        try:
            _md = getattr(patcher, "model_dtype", None)
            if callable(_md):
                evidence["compute_dtype"] = str(_md() or "")
        except Exception:
            pass
        if not evidence["compute_dtype"]:
            evidence["compute_dtype"] = str(getattr(vae, "vae_dtype", "") or "")
        try:
            _fn = getattr(patcher, "loaded_size", None)
            if callable(_fn):
                evidence["loaded_bytes"] = int(_fn() or 0)
        except Exception:
            pass
        try:
            _fn = getattr(patcher, "model_size", None)
            if callable(_fn):
                evidence["model_bytes"] = int(_fn() or 0)
        except Exception:
            pass
    _fs = getattr(vae, "first_stage_model", None)
    evidence["current_device"] = _module_device(_fs)
    if not evidence["current_device"]:
        evidence["current_device"] = _module_device(getattr(patcher, "model", None))
    _cur = str(evidence.get("current_device", "") or "").lower()
    _lb = evidence.get("loaded_bytes")
    _mb = evidence.get("model_bytes")
    if _cur and "cpu" in _cur:
        evidence["residency_status"] = "cpu_resident"
    elif _lb is not None and _mb is not None and _lb > 0 and _lb >= _mb:
        evidence["residency_status"] = "resident_full"
    elif evidence.get("cache_present") and _cur:
        evidence["residency_status"] = "resident"
    elif _cur:
        evidence["residency_status"] = "gpu_resident"
    else:
        evidence["residency_status"] = "unknown"
    return evidence


def _measure_vae_activation_lane_wait_ms(
    trace: RuntimeTrace | None,
    *,
    request_id: str,
    wait_start_ns: int | None,
) -> float | None:
    """Measure the truthful mutation-lane wait from existing lane trace events.

    The existing GPU loader wrapper acquires the shared mutation lane INSIDE
    ``load_models_gpu`` and emits ``gpu_lane_wait_start`` at the instant the
    lane is actually acquired.  The worker's own load-start marker precedes
    the load call, so the interval between the worker marker and the
    wrapper's ``gpu_lane_wait_start`` (lane ``VAE``) is the truthful lane
    wait.  Returns None when the wrapper never reported the lane acquisition
    — the value is never fabricated.  The worker never acquires the lane
    itself, so this cannot deadlock the existing GPU wrapper.
    """
    if trace is None or not wait_start_ns:
        return None
    _wait_ns: int | None = None
    for _event in trace.events:
        if _event.name != "gpu_lane_wait_start":
            continue
        _meta = _event.metadata or {}
        if str(_meta.get("lane", "")) != "VAE":
            continue
        if _event.monotonic_ns < wait_start_ns:
            continue
        _wait_ns = _event.monotonic_ns - wait_start_ns
        break
    if _wait_ns is None or _wait_ns < 0:
        return None
    return round(_wait_ns / 1_000_000, 3)


# ── Terminal / fallback helpers ────────────────────────────────────────


def _vae_activation_terminal(
    state: dict[str, Any],
    trace: RuntimeTrace | None,
    request_id: str,
    *,
    status: str,
    reason: str,
    error: str = "",
    transfer_count: int = 0,
    diagnostics: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Establish the terminal VAE activation state exactly once and emit the
    concise ``event=terminal`` line (with the requested status)."""
    with _VAE_ACTIVATION_LOCK:
        _first_terminal = not state.get("terminal", False)
        if not state.get("terminal", False):
            state["terminal"] = True
            state["status"] = status
            state["reason"] = reason
            if error:
                state["error"] = error
            if transfer_count:
                state["transfer_count"] = transfer_count
            state["terminal_mono_ns"] = time.monotonic_ns()
        if diagnostics:
            _diag = state.setdefault("diagnostics", {})
            for _k, _v in dict(diagnostics).items():
                if not isinstance(_v, (bytes, bytearray)):
                    _diag[_k] = _v
    if not _first_terminal:
        return {
            "status": state.get("status", status),
            "reason": state.get("reason", reason),
            "terminal": True,
        }
    if trace is not None:
        trace.emit(_EVENT_VAE_EA_TERMINAL, phase="execution", metadata={
            "mode": state.get("mode", ""),
            "trigger": state.get("trigger", ""),
            "request_id": request_id,
            "key_hash": state.get("key_hash", ""),
            "status": state.get("status", status),
            "reason": state.get("reason", reason),
            "error": state.get("error", "") or None,
            "transfer_count": state.get("transfer_count", 0),
            "vae_object_id": state.get("vae_object_id", ""),
            "vae_patcher_object_id": state.get("vae_patcher_object_id", ""),
            "vae_resolution_source": state.get("vae_resolution_source", ""),
            "cache_present": bool(state.get("cache_present", False)),
            "residency_status": state.get("residency_status", ""),
            "restored_instance_id": _LATEST_RESTORED_INSTANCE_ID,
            "restore_session_id": _LATEST_RESTORE_SESSION_ID,
        })
    print(
        f"[v2.vae_early_activation] event=terminal "
        f"request_id={request_id or 'absent'} mode={state.get('mode', '')} "
        f"key_hash={state.get('key_hash', '')} status={state.get('status', status)} "
        f"reason={state.get('reason', reason) or 'ok'} error={state.get('error', '') or 'absent'} "
        f"transfer_count={state.get('transfer_count', 0)} "
        f"source={state.get('vae_resolution_source', '') or 'absent'}",
        flush=True,
    )
    return {
        "status": state.get("status", status),
        "reason": state.get("reason", reason),
        "terminal": True,
    }


def _vae_activation_fallback(
    state: dict[str, Any],
    trace: RuntimeTrace | None,
    request_id: str,
    *,
    reason: str,
    error: str = "",
    join_wait_ms: float = 0.0,
) -> dict[str, Any]:
    """Record the unchanged late fallback exactly once (atomic, never
    overwritten).  Returns an outcome dict with ``valid=False``."""
    with _VAE_ACTIVATION_LOCK:
        _elected = bool(state.get("fallback_elected", False))
        if not _elected:
            state["fallback_elected"] = True
            state["fallback_reason"] = reason
            state["terminal"] = True
            if error:
                state["error"] = error
    if trace is not None and not _elected:
        trace.emit(_EVENT_VAE_EA_FALLBACK, phase="execution", metadata={
            "mode": state.get("mode", ""),
            "trigger": state.get("trigger", ""),
            "request_id": request_id,
            "key_hash": state.get("key_hash", ""),
            "status": state.get("status", "fallback"),
            "reason": reason,
            "error": error or None,
            "join_wait_ms": round(float(join_wait_ms), 3),
        })
    return {"scheduled": True, "status": state.get("status", "fallback"),
            "terminal": True, "valid": False, "reason": reason,
            "join_wait_ms": round(float(join_wait_ms), 3), "vae": None}


# ── Early VAE activation worker ────────────────────────────────────────


def _run_early_vae_activation(
    bridge: "V2LoaderBridge",
    *,
    prep: RestorePreparation,
    trace: RuntimeTrace | None,
    request_id: str,
    state: dict[str, Any],
    vae: Any,
    source: str,
    key_hash: str,
    mode: str,
) -> dict[str, Any]:
    """Early VAE GPU/cache activation worker (coordinator pool).

    Runs after the authoritative sampling_end boundary.  Uses the exact
    adapter-resolved VAE object and the original ComfyUI
    ``load_models_gpu`` path — the existing GPU loader wrapper acquires the
    shared mutation lane as owner ``VAE`` around the actual load, so the
    worker can never overlap active sampling.  Emits the concise
    ``[v2.vae_early_activation] event=load_start`` immediately before the
    GPU/cache mutation and ``event=terminal status=ready`` only after
    successful validation (identity / target device / dtype / cache
    membership / residency).  Never executes VAE decode.  No ContextVar
    assumptions: request/trace/bridge are carried explicitly.
    """
    with _VAE_ACTIVATION_LOCK:
        state["status"] = "running"
        state["worker_started_mono_ns"] = time.monotonic_ns()
    if vae is None:
        return _vae_activation_terminal(
            state, trace, request_id, status="skipped", reason="no_vae_object"
        )
    state["vae_object_id"] = str(id(vae))
    state["vae_resolution_source"] = source
    _patcher = getattr(vae, "patcher", None)
    state["vae_patcher_object_id"] = str(id(_patcher)) if _patcher is not None else ""
    if _patcher is None:
        return _vae_activation_terminal(
            state, trace, request_id, status="skipped", reason="no_vae_patcher"
        )
    # Reject identity drift between scheduling and the worker (the key was
    # built with the REAL resolved object at the sampling_end boundary).
    _expected_id = str((state.get("key") or {}).get("vae_object_id", "") or "")
    if _expected_id and _expected_id != str(id(vae)):
        return _vae_activation_terminal(
            state, trace, request_id, status="invalid", reason="identity_changed"
        )
    # Request cleanup may have finalized while we queued.
    if state.get("cancelled") or state.get("terminal"):
        return _vae_activation_terminal(
            state, trace, request_id, status="cancelled", reason="request_finalized"
        )
    # VRAM pre-check (outside the lane).
    _vram = _check_early_activation_vram([_patcher])
    state["gpu_free_bytes"] = _vram.get("free_bytes")
    state["gpu_required_bytes"] = _vram.get("required_bytes")
    state["safety_margin_bytes"] = _vram.get("margin_bytes")
    if not _vram.get("ok"):
        return _vae_activation_terminal(
            state, trace, request_id, status="skipped",
            reason=str(_vram.get("reason", "vram_insufficient")),
            diagnostics=_vram,
        )
    # Re-check cancellation IMMEDIATELY before the GPU mutation.
    if state.get("cancelled") or state.get("terminal"):
        return _vae_activation_terminal(
            state, trace, request_id, status="cancelled", reason="request_finalized"
        )
    # ── Original ComfyUI GPU/cache load path (lane acquired by the
    # existing wrapper as owner "VAE" around the load only). ──
    _loaded_before = _vae_patcher_loaded_bytes(_patcher)
    _gpu_alloc_before = _gpu_allocated_bytes()
    _load_start = _capture_phase_counters()
    _lane_wait_start_ns = time.monotonic_ns()
    if trace is not None:
        trace.emit(_EVENT_VAE_EA_LOAD_START, phase="execution", metadata={
            "mode": mode,
            "trigger": state.get("trigger", ""),
            "request_id": request_id,
            "key_hash": state.get("key_hash", ""),
            "source": source,
        })
    print(
        f"[v2.vae_early_activation] event=load_start "
        f"request_id={request_id or 'absent'} mode={mode} "
        f"key_hash={state.get('key_hash', '')} source={source or 'absent'} "
        f"vae_object_id={state.get('vae_object_id', '')} "
        f"vae_patcher_object_id={state.get('vae_patcher_object_id', '')}",
        flush=True,
    )
    try:
        import torch as _torch_vae
        with _torch_vae.inference_mode():
            _mm_load_models_gpu([_patcher])
    except Exception as exc:
        return _vae_activation_terminal(
            state, trace, request_id, status="failed",
            reason="load_failed", error=str(exc)[:200],
        )
    _load_end = _capture_phase_counters()
    _deltas = _phase_counter_deltas(_load_start, _load_end)
    state["load_wall_ms"] = _deltas.get("wall_ms", 0.0) or 0.0
    state["transfer_count"] = 1 if _vae_patcher_loaded_bytes(_patcher) > _loaded_before else 0
    _gpu_alloc_after = _gpu_allocated_bytes()
    state["gpu_allocated_before"] = _gpu_alloc_before
    state["gpu_allocated_after"] = _gpu_alloc_after
    if _gpu_alloc_before is not None and _gpu_alloc_after is not None:
        state["gpu_allocated_delta_bytes"] = _gpu_alloc_after - _gpu_alloc_before
    state["lane_wait_ms"] = _measure_vae_activation_lane_wait_ms(
        trace, request_id=request_id, wait_start_ns=_lane_wait_start_ns,
    ) or 0.0
    # ── Terminal validation (identity/device/dtype/cache/residency) ──
    _evidence = _probe_vae_activation_evidence(vae, _patcher)
    state["cache_present"] = bool(_evidence.get("cache_present", False))
    state["current_device"] = str(_evidence.get("current_device", "") or "")
    state["load_device"] = str(_evidence.get("load_device", "") or "")
    state["compute_dtype"] = str(_evidence.get("compute_dtype", "") or "")
    state["loaded_bytes"] = _evidence.get("loaded_bytes")
    state["model_bytes"] = _evidence.get("model_bytes")
    state["residency_status"] = str(_evidence.get("residency_status", "") or "")
    if state["residency_status"] == "cpu_resident" or not state["cache_present"]:
        return _vae_activation_terminal(
            state, trace, request_id, status="invalid",
            reason="residency_not_proven", diagnostics=_evidence,
        )
    return _vae_activation_terminal(
        state, trace, request_id, status="ready", reason="ok",
        transfer_count=state["transfer_count"], diagnostics=_evidence,
    )


# ── Public API ─────────────────────────────────────────────────────────


def release_sampler_mutation_lane_at_sampling_end(
    *,
    trace: RuntimeTrace | None = None,
    request_id: str = "",
) -> bool:
    """Release the existing sampler owner after the authoritative boundary."""
    if vae_activation_mode() != _VAE_ACTIVATION_MODE_SAMPLING_END:
        return False
    lane = _get_mutation_lane()
    if lane.owner != "sampler":
        return False
    lane.release("sampler")
    if trace is not None:
        trace.emit("sampler_lane_released_at_sampling_end", phase="execution", metadata={
            "request_id": request_id or str(trace.request_id),
        })
    return True


def acquire_sampler_mutation_lane_at_sampling_start() -> None:
    """Reacquire the shared sampler owner for later sampler invocations."""
    if vae_activation_mode() != _VAE_ACTIVATION_MODE_SAMPLING_END:
        return
    lane = _get_mutation_lane()
    if lane.owner != "sampler":
        lane.acquire("sampler")


def schedule_vae_early_activation_at_sampling_end(
    bridge: "V2LoaderBridge",
    *,
    trace: RuntimeTrace | None = None,
    request_id: str = "",
    sampler_node_id: str = "",
    sampler_node_class: str = "",
    duration_ms: float = 0.0,
) -> bool:
    """Schedule the sampling_end VAE early activation exactly once.

    Hooked from the real SAMPLER_SAMPLE sampling_end boundary
    (``runtime_executor._build_sampling_wrapper``) — never from
    progress/milestones, restore, or active sampling.  Ordering:
      1. authoritative ``sampling_end`` trace/log (already emitted by the
         wrapper BEFORE this call);
      2. release the existing ``sampler`` mutation-lane ownership so the
         VAE worker's lane-acquiring load can proceed after sampling
         (idempotent — the outer execute finally release stays harmless);
      3. emit exactly one concise
         ``[v2.vae_early_activation] event=scheduled trigger=sampling_end``
         line;
      4. submit the VAE activation future through the existing coordinator
         pool (single-flight via ``RestorePreparation.vae_future``).
    In ``late`` mode (default) this is a no-op.  Any resolution failure
    falls back silently to the unchanged original graph loader path.
    Returns True when scheduled (or already scheduled).
    """
    if vae_activation_mode() != _VAE_ACTIVATION_MODE_SAMPLING_END:
        return False
    _request_id = str(request_id or "")
    if not _request_id and trace is not None:
        _request_id = str(trace.request_id)
    if not _request_id:
        return False
    release_sampler_mutation_lane_at_sampling_end(
        trace=trace,
        request_id=_request_id,
    )
    if bridge is None:
        return False
    prep = getattr(bridge, "_preparation", None)
    model_key = getattr(bridge, "_model_key", None)
    if prep is None or model_key is None or not getattr(model_key, "vae_identity", ""):
        return False
    # Idempotent: a scheduled future for this request is never rescheduled.
    with _VAE_ACTIVATION_LOCK:
        _existing = _VAE_ACTIVATION_STATE.get(_request_id)
        if _existing is not None:
            return bool(_existing.get("future") is not None)
        _state = _vae_activation_new_state(_request_id)
        _state["status"] = "resolving"
        _state["sampling_end_mono_ns"] = time.monotonic_ns()
        _state["sampling_end_duration_ms"] = round(float(duration_ms or 0.0), 3)
        _VAE_ACTIVATION_STATE[_request_id] = _state
    _sampling_end_mono_ns = time.monotonic_ns()
    # Resolve the exact VAE object via the bridge adapter.
    try:
        _vae, _source = bridge.resolve_vae_object(trace=trace)
    except Exception as exc:
        _vae_activation_terminal(
            _state, trace, _request_id, status="failed",
            reason="resolution_failed", error=str(exc)[:200],
        )
        return False
    if _vae is None:
        if trace is not None:
            trace.emit(_EVENT_VAE_EA_SKIPPED, phase="execution", metadata={
                "mode": _VAE_ACTIVATION_MODE,
                "trigger": "sampling_end",
                "request_id": _request_id,
                "reason": "no_vae_resolution",
                "restored_instance_id": _LATEST_RESTORED_INSTANCE_ID,
                "restore_session_id": _LATEST_RESTORE_SESSION_ID,
            })
        _vae_activation_terminal(
            _state, trace, _request_id, status="skipped",
            reason="no_vae_resolution",
        )
        return False
    _key_components, _key_hash = _build_vae_activation_key(
        mode=_VAE_ACTIVATION_MODE,
        model_key=model_key,
        request_id=_request_id,
        vae=_vae,
        source=_source,
        sampling_end_mono_ns=_sampling_end_mono_ns,
    )
    return _vae_activation_submit(
        bridge,
        request_id=_request_id, trace=trace, prep=prep, model_key=model_key,
        vae=_vae, source=_source,
        key_components=_key_components, key_hash=_key_hash,
        trigger="sampling_end",
        sampling_end_duration_ms=duration_ms,
    )


def _vae_activation_submit(
    bridge: "V2LoaderBridge",
    *,
    request_id: str,
    trace: RuntimeTrace | None,
    prep: RestorePreparation,
    model_key: ModelRestoreKey,
    vae: Any,
    source: str,
    key_components: dict[str, Any],
    key_hash: str,
    trigger: str = "sampling_end",
    sampling_end_duration_ms: float = 0.0,
) -> bool:
    """Shared coordinator/single-flight scheduling core for the VAE early
    activation.

    Atomically (under the existing activation lock) creates/finds the
    request state, emits the concise scheduled line, and submits the VAE
    activation worker once through ``bridge.coordinator.schedule_vae_activation``
    (single-flight via ``RestorePreparation.vae_future``).  The scheduled
    line is emitted WHILE HOLDING the lock, so it is guaranteed to precede
    any worker-emitted load-start marker (monotonic-order invariant).
    Returns True when scheduled (or already scheduled), False on submit
    failure.
    """
    with _VAE_ACTIVATION_LOCK:
        _state = _VAE_ACTIVATION_STATE.get(request_id)
        if _state is not None and _state.get("future") is not None:
            return True
        if _state is None:
            _state = _vae_activation_new_state(request_id)
            _VAE_ACTIVATION_STATE[request_id] = _state
        _state["owner"] = trigger
        _state["trigger"] = trigger
        _state["mode"] = _VAE_ACTIVATION_MODE
        _state["key"] = key_components
        _state["key_hash"] = key_hash
        _state["vae"] = vae
        _state["vae_object_id"] = key_components.get("vae_object_id", "")
        _state["vae_patcher_object_id"] = key_components.get("vae_patcher_object_id", "")
        _state["vae_resolution_source"] = source
        _state["vae_identity"] = key_components.get("vae_identity", "")
        _state["sampling_end_mono_ns"] = int(key_components.get("sampling_end_mono_ns", 0) or 0)
        _state["sampling_end_duration_ms"] = round(float(sampling_end_duration_ms or 0.0), 3)
        _state["status"] = "scheduled"
        _state["submitted_mono_ns"] = time.monotonic_ns()
        # Emit the concise scheduled line BEFORE submitting so the worker's
        # load-start (guarded by the same lock) can never precede it.
        if trace is not None:
            trace.emit(_EVENT_VAE_EA_SCHEDULED, phase="execution", metadata={
                "mode": _VAE_ACTIVATION_MODE,
                "trigger": trigger,
                "request_id": request_id,
                "key_hash": key_hash,
                "source": source,
                "vae_object_id": key_components.get("vae_object_id", ""),
                "vae_patcher_object_id": key_components.get("vae_patcher_object_id", ""),
                "vae_identity_hash": stable_hash(str(model_key.vae_identity))[:16] if model_key is not None else "",
                "restored_instance_id": _LATEST_RESTORED_INSTANCE_ID,
                "restore_session_id": _LATEST_RESTORE_SESSION_ID,
            })
        print(
            f"[v2.vae_early_activation] event=scheduled "
            f"request_id={request_id or 'absent'} mode={_VAE_ACTIVATION_MODE} "
            f"trigger={trigger} key_hash={key_hash} source={source or 'absent'} "
            f"vae_identity_hash={stable_hash(str(model_key.vae_identity))[:16] if model_key is not None else ''} "
            f"restored_instance_id={_LATEST_RESTORED_INSTANCE_ID or 'absent'} "
            f"restore_session_id={_LATEST_RESTORE_SESSION_ID or 'absent'}",
            flush=True,
        )

        def _worker() -> Any:
            return _run_early_vae_activation(
                bridge,
                prep=prep,
                trace=trace,
                request_id=request_id,
                state=_state,
                vae=vae,
                source=source,
                key_hash=key_hash,
                mode=_VAE_ACTIVATION_MODE,
            )

        try:
            _future = bridge.coordinator.schedule_vae_activation(
                _worker, prep, trace=trace,
            )
        except Exception as exc:
            _state["status"] = "failed"
            _state["terminal"] = True
            _state["reason"] = "submit_failed"
            _state["error"] = str(exc)[:200]
            _state["terminal_mono_ns"] = time.monotonic_ns()
            print(
                f"[v2.vae_early_activation] event=terminal "
                f"request_id={request_id or 'absent'} mode={_VAE_ACTIVATION_MODE} "
                f"status=failed reason=submit_failed error={str(exc)[:200]}",
                flush=True,
            )
            return False
        if _future is None:
            _state["status"] = "failed"
            _state["terminal"] = True
            _state["reason"] = "no_active_preparation"
            _state["terminal_mono_ns"] = time.monotonic_ns()
            return False
        _state["future"] = _future
    _vae_activation_trim()
    return True


def _validate_vae_early_activation(
    state: dict[str, Any],
    *,
    demanded_vae: Any = None,
) -> tuple[bool, str, Any]:
    """Validate the early-activated VAE at graph demand.

    Rechecks identity (exact VAE object id), cache membership, residency,
    target device, and compute dtype against the values recorded by the
    worker's post-load evidence.  Never raises; returns ``(valid, reason,
    vae)``.
    """
    _vae = state.get("vae")
    if _vae is None:
        return False, "vae_missing", None
    _key = state.get("key") or {}
    _expected_id = _key.get("vae_object_id", "")
    if _expected_id and _expected_id != str(id(_vae)):
        return False, "vae_identity_mismatch", None
    if demanded_vae is not None and demanded_vae is not _vae:
        return False, "graph_vae_identity_mismatch", None
    if not state.get("cache_present", False):
        return False, "cache_missing", None
    if state.get("residency_status") in {"", "unknown", "cpu_resident"}:
        return False, "residency_unproven", None
    _device = _key.get("device", "")
    _cur = str(state.get("current_device", "") or "")
    if not _device or not _cur:
        return False, "device_unproven", None
    if str(_cur) != str(_device):
        return False, "device_mismatch", None
    _expected_dtype = _key.get("compute_dtype", "")
    _actual = str(state.get("compute_dtype", "") or "")
    if not _expected_dtype or not _actual:
        return False, "dtype_unproven", None
    if _actual != _expected_dtype:
        return False, "dtype_mismatch", None
    return True, "ok", _vae


def finalize_vae_early_activation(
    request_id: str,
    *,
    trace: RuntimeTrace | None = None,
) -> dict[str, Any] | None:
    """Request-end cleanup + reconciliation.

    Marks any still-pending VAE activation cancelled (the worker observes
    this before its GPU mutation), pops the request state, and emits a
    concise reconciliation record.  Never leaves an activation future or
    model mutation pending — the coordinator pool shutdown in
    ``close_workers`` terminates any in-flight worker.
    """
    if not request_id:
        return None
    with _VAE_ACTIVATION_LOCK:
        _state = _VAE_ACTIVATION_STATE.pop(request_id, None)
    if _state is None:
        return None
    _future = _state.get("future")
    with _VAE_ACTIVATION_LOCK:
        if not _state.get("terminal", False):
            _state["status"] = "cancelled"
            _state["cancelled"] = True
            _state["terminal"] = True
            _state["reason"] = "request_finalized"
            _state["terminal_mono_ns"] = time.monotonic_ns()
        if _future is not None and not _future.done():
            try:
                _future.cancel()
            except Exception:
                pass
    if trace is not None:
        trace.emit(_EVENT_VAE_EA_RECONCILIATION, phase="execution", metadata={
            "request_id": request_id,
            "mode": _state.get("mode", ""),
            "trigger": _state.get("trigger", ""),
            "key_hash": _state.get("key_hash", ""),
            "status": _state.get("status", ""),
            "terminal": bool(_state.get("terminal", False)),
            "join_wait_ms": _state.get("join_wait_ms", 0.0),
            "lane_wait_ms": _state.get("lane_wait_ms", 0.0),
            "load_wall_ms": _state.get("load_wall_ms", 0.0),
            "transfer_count": _state.get("transfer_count", 0),
            "cache_present": bool(_state.get("cache_present", False)),
            "residency_status": _state.get("residency_status", ""),
            "vae_object_id": _state.get("vae_object_id", ""),
            "vae_resolution_source": _state.get("vae_resolution_source", ""),
            "sampling_end_mono_ns": _state.get("sampling_end_mono_ns", 0),
            "sampling_end_duration_ms": _state.get("sampling_end_duration_ms", 0.0),
            "restored_instance_id": _LATEST_RESTORED_INSTANCE_ID,
            "restore_session_id": _LATEST_RESTORE_SESSION_ID,
        })
    return _state


# ── Backward-compatible aliases for test imports ─────────────────────
# The four factories below were renamed with ``_breakdown`` suffix to
# avoid name conflicts with later diagnostic wrappers having the same
# public names.  Tests import the old names and expect the breakdown
# (``model_patcher_load_breakdown``) behavior, not the diagnostic
# (``mp_load_start/end``) behavior.  These aliases preserve backward
# compatibility so that ``from comfymodal_runtime.model_preload import
# _make_model_patcher_load_wrapper`` resolves to the breakdown version.
_make_model_patcher_load_wrapper = _make_model_patcher_load_breakdown_wrapper
_make_model_patcher_load_list_wrapper = _make_model_patcher_load_list_breakdown_wrapper
_make_model_patcher_patch_weight_wrapper = _make_model_patcher_patch_weight_breakdown_wrapper
_make_cast_to_device_wrapper = _make_cast_to_device_breakdown_wrapper
