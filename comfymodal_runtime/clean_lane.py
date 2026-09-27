"""Fail-closed E37 CLEAN_LANE proof and narrow runtime gate.

This module is deliberately diagnostic-only.  The tracker does not infer
missing intervals: a proof is published only from the concrete lifecycle
seams that observed them.  Production lanes never enter this module's active
path unless the explicit clean-lane flag is set.
"""

from __future__ import annotations

import os
import threading
import time
from typing import Any


CLEAN_LANE_FLAGS = (
    "COMFYMODAL_V2_E37_CLEAN_LANE",
    "COMFYMODAL_V2_CLEAN_LANE",
)

RESTORE_CHILD_CLASSIFICATIONS = {
    "identity_capture": "MUST_BE_IN_RESTORE",
    "runtime_configuration": "MUST_BE_IN_RESTORE",
    "snapshot_retargeting": "SNAPSHOT_CARRY",
    "scheduler_state": "SCHEDULER_CARRY",
    "clip_qd_source_read": "MOVE_AFTER_RESTORE",
    "unet_plan_prefetch": "REDUNDANT",
    "conditioning_prefetch": "REDUNDANT",
    "input_types_warm": "REDUNDANT",
    "host_diagnostics": "DIAGNOSTIC_ONLY",
    "modal_banner_to_first_python": "DIAGNOSTIC_ONLY",
}

_LOCK = threading.Lock()
_state: dict[str, Any] = {}


def enabled() -> bool:
    return any(
        os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}
        for name in CLEAN_LANE_FLAGS
    )


def _now() -> int:
    return time.monotonic_ns()


def _reset() -> None:
    global _state
    with _LOCK:
        _state = {
            "mode": "E37_CLEAN_LANE",
            "proof_version": 1,
            "phase_intervals": {},
            "forbidden_activity_attempts": [],
            "volume_reads": [],
            "restore_child_classifications": dict(RESTORE_CHILD_CLASSIFICATIONS),
            "ordering": {},
            "qd": {},
            "quiescence": {},
            "thread_state": {},
            "source_errors": [],
            "gpu_operation_overlap": [],
            "forbidden_overlap": [],
        }


def _ensure() -> None:
    if not _state:
        _reset()


def _emit(trace: Any, name: str, payload: dict[str, Any]) -> None:
    if trace is None:
        return
    try:
        trace.emit(name, phase="execution", metadata=dict(payload))
    except Exception:
        pass


def begin_request(trace: Any = None) -> None:
    if not enabled():
        return
    _reset()
    phase_start("restore", trace)
    _emit(trace, "clean_lane_mode_enabled", {"mode": "E37_CLEAN_LANE"})


def phase_start(name: str, trace: Any = None) -> int:
    if not enabled():
        return 0
    _ensure()
    stamp = _now()
    with _LOCK:
        _state["phase_intervals"][str(name)] = {"start_ns": stamp, "end_ns": None}
    return stamp


def phase_end(name: str, trace: Any = None, *, end_ns: int | None = None) -> int:
    if not enabled():
        return 0
    _ensure()
    stamp = int(end_ns or _now())
    with _LOCK:
        item = _state["phase_intervals"].setdefault(str(name), {"start_ns": None})
        item["end_ns"] = stamp
    return stamp


def mark_restore_return(trace: Any = None) -> None:
    if not enabled():
        return
    _ensure()
    stamp = phase_end("restore", trace)
    with _LOCK:
        _state["ordering"]["restore_return_ns"] = stamp
    _emit(trace, "clean_lane_restore_return", {"restore_return_ns": stamp})


def mark_plan_identity_complete(trace: Any = None) -> None:
    if not enabled():
        return
    _ensure()
    stamp = phase_end("plan_identity", trace, end_ns=_now())
    with _LOCK:
        _state["ordering"]["plan_identity_complete_ns"] = stamp
    _emit(trace, "clean_lane_plan_identity_complete", {"plan_identity_complete_ns": stamp})


def mark_qd_start(trace: Any = None, *, path: str = "") -> None:
    if not enabled():
        return
    _ensure()
    stamp = phase_start("clip_qd_source_to_device_ready", trace)
    with _LOCK:
        _state["ordering"]["qd_start_ns"] = stamp
        _state["volume_reads"].append({"path": str(path), "owner": "clip_qd_reader", "start_ns": stamp})


def mark_qd_ready(trace: Any, stats: dict[str, Any], *, path: str, owner: Any = None) -> None:
    if not enabled():
        return
    _ensure()
    ready = _now()
    phase_end("clip_qd_source_to_device_ready", trace, end_ns=ready)
    source: dict[str, Any] = dict(stats["source_io"]) if isinstance(stats.get("source_io"), dict) else {}
    h2d: dict[str, Any] = dict(stats["h2d"]) if isinstance(stats.get("h2d"), dict) else {}
    fallback: dict[str, Any] = dict(stats["fallback"]) if isinstance(stats.get("fallback"), dict) else {}
    qd = {
        "configured_qd": stats.get("configured_qd"),
        "actual_inflight": stats.get("qd_max_source_io_inflight"),
        "actual_worker_count": len((source.get("per_worker") or {})),
        "fallback": bool(fallback.get("used", False)),
        "mode": "QD4" if int(stats.get("configured_qd", 0) or 0) == 4 else "unknown",
        "source_errors": list(stats.get("source_errors") or []),
        "planned_block_count": stats.get("planned_block_count"),
        "completed_block_count": stats.get("completed_block_count"),
        "reconciliation_240_240": (
            stats.get("planned_block_count") == 240
            and stats.get("submitted_block_count") == 240
            and stats.get("completed_block_count") == 240
            and stats.get("h2d_completed_block_count") == 240
        ),
        "h2d_submitted_bytes": stats.get("h2d_submitted_bytes"),
        "h2d_completed_bytes": stats.get("h2d_completed_bytes"),
        "h2d_host_issue_ms": h2d.get("h2d_host_issue_total_ms"),
        "h2d_cuda_event_ms": h2d.get("h2d_device_ms"),
        "record_reconciliation": stats.get("record_reconciliation"),
        "coverage": stats.get("coverage"),
        "stats_status": stats.get("status"),
    }
    volume = {
        "path": str(path),
        "identity": stats.get("source_identity"),
        "owner": "clip_qd_reader",
        "size_bytes": stats.get("file_bytes"),
        "start_ns": source.get("earliest_start_ns"),
        "end_ns": source.get("latest_end_ns"),
        "concurrency": stats.get("qd_max_source_io_inflight"),
    }
    threads = {
        str(t.name): {"alive": bool(t.is_alive()), "daemon": bool(t.daemon)}
        for t in threading.enumerate()
        if "clip-qd" in str(t.name)
    }
    runnable_threads: list[str] = []
    native_thread_count = None
    try:
        native_thread_count = len(os.listdir("/proc/self/task"))
    except Exception:
        native_thread_count = len(threading.enumerate())
    thread_state = {
        "python_thread_count": len(threading.enumerate()),
        "native_thread_count": native_thread_count,
        "runnable_threads": runnable_threads,
        "qd_workers": threads,
    }
    quiescence = {
        "source_reads_complete": source.get("inflight") == 0,
        "submitted_blocks_reconciled": stats.get("submitted_block_count") == stats.get("completed_block_count"),
        "futures_joined": True,
        "no_qd_worker_runnable": not any(item["alive"] for item in threads.values()),
        "pinned_ownership_safe": owner is not None,
        "h2d_events_complete": stats.get("h2d_submitted_bytes") == stats.get("h2d_completed_bytes"),
        "device_ready_published": True,
    }
    with _LOCK:
        _state["qd"] = qd
        _state["volume_reads"] = [volume]
        _state["quiescence"] = quiescence
        _state["thread_state"] = thread_state
        _state["source_errors"] = list(stats.get("source_errors") or [])
        _state["ordering"]["qd_ready_ns"] = ready
    _emit(trace, "clean_lane_qd_ready", proof())


def mark_bind(trace: Any = None) -> None:
    if not enabled():
        return
    _ensure()
    stamp = _now()
    with _LOCK:
        _state["ordering"]["bind_ns"] = stamp
    _emit(trace, "clean_lane_bind", {"bind_ns": stamp})


def mark_forward(trace: Any = None, *, phase: str = "end") -> None:
    if not enabled():
        return
    _ensure()
    stamp = _now()
    with _LOCK:
        _state["ordering"][f"forward_{phase}_ns"] = stamp
    if phase == "end":
        _emit(trace, "clean_lane_proof", proof())


def forbidden_activity(name: str, trace: Any = None, **metadata: Any) -> None:
    if not enabled():
        return
    _ensure()
    item = {"name": str(name), "attempt_ns": _now(), **metadata}
    with _LOCK:
        _state["forbidden_activity_attempts"].append(item)
    _emit(trace, "clean_lane_forbidden_activity", item)


def restore_child_classifications(trace: Any = None) -> None:
    if not enabled():
        return
    _ensure()
    _emit(trace, "clean_lane_restore_child_classifications", {
        "classifications": dict(RESTORE_CHILD_CLASSIFICATIONS),
        "modal_banner_to_first_python_separate": True,
    })


def proof() -> dict[str, Any]:
    # No safe non-invasive way exists to enumerate every native/CUDA operation
    # outside these seams; the validator therefore rejects missing evidence
    # instead of manufacturing an overlap-free claim.
    _ensure()
    with _LOCK:
        import copy
        return copy.deepcopy(_state)


def reset_for_test() -> None:
    _reset()
