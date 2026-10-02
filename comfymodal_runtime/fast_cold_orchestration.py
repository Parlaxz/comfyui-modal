"""Opt-in request orchestration for the final fastsafetensors cold path."""

from __future__ import annotations

import os
import threading
import time
from dataclasses import dataclass
from typing import Any, Mapping, Optional

from .checkpoint_prewarm import CheckpointPrewarmer, resolve_prewarm_paths
from . import clean_lane
from .env import env_flag


MASTER_FLAG = "COMFYMODAL_V2_FAST_COLD_ORCHESTRATION"
COMMIT_WAIT_MS_ENV = "COMFYMODAL_V2_FAST_COLD_COMMIT_WAIT_MS"


class SourceFenceFailure(RuntimeError):
    """The prefetch reader could not retire before a demand boundary."""


def is_source_fence_failure(error: BaseException) -> bool:
    return isinstance(error, SourceFenceFailure) or "structural_source_fence_failure" in str(error)

STORAGE_NONE = "NONE"
STORAGE_CLIP_PREFETCH = "CLIP_PREFETCH"
STORAGE_CLIP_DEMAND = "CLIP_DEMAND"
STORAGE_UNET_PREFETCH = "UNET_PREFETCH"
STORAGE_UNET_DEMAND = "UNET_DEMAND"
STORAGE_STATES = (
    STORAGE_NONE,
    STORAGE_CLIP_PREFETCH,
    STORAGE_CLIP_DEMAND,
    STORAGE_UNET_PREFETCH,
    STORAGE_UNET_DEMAND,
)

_ALLOWED_TRANSITIONS = {
    STORAGE_NONE: frozenset(STORAGE_STATES),
    STORAGE_CLIP_PREFETCH: frozenset({STORAGE_CLIP_PREFETCH, STORAGE_CLIP_DEMAND, STORAGE_NONE}),
    STORAGE_CLIP_DEMAND: frozenset({STORAGE_CLIP_DEMAND, STORAGE_UNET_PREFETCH, STORAGE_UNET_DEMAND, STORAGE_NONE}),
    STORAGE_UNET_PREFETCH: frozenset({STORAGE_UNET_PREFETCH, STORAGE_UNET_DEMAND, STORAGE_NONE}),
    STORAGE_UNET_DEMAND: frozenset({STORAGE_UNET_DEMAND, STORAGE_NONE}),
}


def enabled() -> bool:
    return env_flag(MASTER_FLAG, default=False)


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        return max(0, int(raw.strip()))
    except (TypeError, ValueError):
        return default


def _request_id(request_id: str = "", trace: Any = None) -> str:
    trace_id = str(getattr(trace, "request_id", "") or "")
    if trace_id:
        return trace_id
    if request_id:
        return str(request_id)
    return ""


def _resolve_path(folder: str, name: Any) -> Optional[str]:
    value = str(name or "")
    if not value:
        return None
    if os.path.isabs(value) and os.path.isfile(value):
        return value
    if os.path.isfile(value):
        return os.path.abspath(value)
    try:
        import folder_paths

        resolver = getattr(folder_paths, "get_full_path_or_raise", None)
        if callable(resolver):
            try:
                path = resolver(folder, value)
                if path:
                    return str(path)
            except Exception:
                pass
        resolver = getattr(folder_paths, "get_full_path", None)
        if callable(resolver):
            path = resolver(folder, value)
            if path:
                return str(path)
    except Exception:
        pass
    return None


def _loader_entries(model_spec: Any, role: str) -> list[Any]:
    if not isinstance(model_spec, Mapping):
        return []
    loaders = model_spec.get("loaders", model_spec)
    if not isinstance(loaders, Mapping):
        return []
    entries = loaders.get(role, [])
    return list(entries) if isinstance(entries, (list, tuple)) else []


def resolve_model_paths(model_spec: Any) -> dict[str, list[str]]:
    """Resolve physical checkpoint paths without inspecting model families."""
    paths = {"clip": [], "unet": []}
    for entry in _loader_entries(model_spec, "clip"):
        if not isinstance(entry, Mapping):
            continue
        names = (
            entry.get("path"),
            entry.get("resolved_path"),
            entry.get("clip_name"),
            entry.get("clip_name1"),
            entry.get("clip_name2"),
        )
        for name in names:
            path = str(name or "")
            if path and os.path.isfile(path):
                paths["clip"].append(path)
            elif name and not str(name).startswith("/"):
                resolved = _resolve_path("text_encoders", name)
                if resolved:
                    paths["clip"].append(resolved)
    for entry in _loader_entries(model_spec, "unet"):
        if not isinstance(entry, Mapping):
            continue
        for name in (entry.get("path"), entry.get("resolved_path"), entry.get("unet_name")):
            path = str(name or "")
            if path and os.path.isfile(path):
                paths["unet"].append(path)
            elif name:
                resolved = _resolve_path("diffusion_models", name)
                if resolved:
                    paths["unet"].append(resolved)
    return {
        role: resolve_prewarm_paths(values)
        for role, values in paths.items()
    }


@dataclass(frozen=True)
class StorageTransition:
    storage_owner: str
    transition_from: str
    transition_to: str
    transition_at: float
    storage_wait_ms: float


class StorageOwnershipController:
    """Small request-scoped state machine for aggressive source ownership."""

    def __init__(self, request_id: str, trace: Any = None):
        self.request_id = str(request_id or "")
        self.trace = trace
        self.storage_owner = STORAGE_NONE
        self.transitions: list[StorageTransition] = []
        self.storage_wait_total_ms = 0.0
        self._lock = threading.RLock()

    def set_trace(self, trace: Any) -> None:
        if trace is not None:
            self.trace = trace

    def add_wait(self, wait_ms: float) -> None:
        with self._lock:
            self.storage_wait_total_ms += max(0.0, float(wait_ms or 0.0))

    def transition(self, target: str, *, storage_wait_ms: float = 0.0) -> StorageTransition:
        target = str(target)
        with self._lock:
            current = self.storage_owner
            if target not in STORAGE_STATES:
                raise ValueError(f"unknown storage state: {target}")
            if target not in _ALLOWED_TRANSITIONS[current]:
                raise ValueError(f"illegal storage transition {current}->{target}")
            now = time.monotonic()
            transition = StorageTransition(
                storage_owner=target,
                transition_from=current,
                transition_to=target,
                transition_at=now,
                storage_wait_ms=round(max(0.0, float(storage_wait_ms or 0.0)), 3),
            )
            self.storage_owner = target
            if target != current:
                self.transitions.append(transition)
                self.storage_wait_total_ms += transition.storage_wait_ms
            return transition

    def release(self) -> None:
        with self._lock:
            if self.storage_owner != STORAGE_NONE:
                self.transition(STORAGE_NONE)

    def as_dict(self) -> dict[str, Any]:
        with self._lock:
            latest = self.transitions[-1] if self.transitions else None
            return {
                "storage_owner": self.storage_owner,
                "storage_owner_transition_count": len(self.transitions),
                "storage_wait_total_ms": round(self.storage_wait_total_ms, 3),
                "transition_from": latest.transition_from if latest else STORAGE_NONE,
                "transition_to": latest.transition_to if latest else STORAGE_NONE,
                "transition_at": latest.transition_at if latest else None,
                "storage_wait_ms": latest.storage_wait_ms if latest else 0.0,
                "storage_owner_transitions": [
                    {
                        "storage_owner": item.storage_owner,
                        "transition_from": item.transition_from,
                        "transition_to": item.transition_to,
                        "transition_at": item.transition_at,
                        "storage_wait_ms": item.storage_wait_ms,
                    }
                    for item in self.transitions
                ],
            }


def _duration_ms(start: Optional[float], end: Optional[float]) -> Optional[float]:
    if start is None or end is None or end < start:
        return None
    return round((end - start) * 1000.0, 3)


def interval_overlap_ms(
    start: Optional[float],
    end: Optional[float],
    other_start: Optional[float],
    other_end: Optional[float],
) -> Optional[float]:
    """Return exact overlap, or None when either interval is unavailable."""
    if (
        start is None
        or end is None
        or other_start is None
        or other_end is None
    ):
        return None
    if end < start or other_end < other_start:
        return None
    return round(
        max(0.0, min(end, other_end) - max(start, other_start)) * 1000.0,
        3,
    )


def classify_clip_forward_health(forward_ms: Optional[float]) -> str:
    if forward_ms is None:
        return "UNKNOWN"
    if forward_ms <= 2200.0:
        return "CLEAN_OR_NEAR_CLEAN"
    if forward_ms <= 3500.0:
        return "DEGRADED"
    return "SEVERELY_CONTENDED_OR_REGRESSED"


class FastColdOrchestrator:
    def __init__(self, request_id: str, model_spec: Any = None, trace: Any = None):
        self.request_id = str(request_id or "")
        self.trace = trace
        self.started_at = time.monotonic()
        self._request_origin: Optional[float] = None
        self.storage = StorageOwnershipController(self.request_id, trace)
        self.paths = resolve_model_paths(model_spec)
        self.clip_prefetch: Optional[CheckpointPrewarmer] = None
        self.unet_prefetch: Optional[CheckpointPrewarmer] = None
        self._lock = threading.RLock()
        self._clip_forward_done = threading.Event()
        self._no_forward = threading.Event()
        self._finalized = False
        self._clip_critical_start: Optional[float] = None
        self._clip_critical_end: Optional[float] = None
        self._record: dict[str, Any] = {
            "fast_cold_orchestration_enabled": True,
            "request_id": self.request_id,
            "storage_owner_transition_count": 0,
            "storage_wait_total_ms": 0.0,
            "clip_prefetch_started": False,
            "clip_prefetch_bytes": 0,
            "clip_prefetch_fraction": 0.0,
            "clip_prefetch_wall_ms": 0.0,
            "clip_prefetch_join_ms": 0.0,
            "clip_prefetch_overlap_with_setup_ms": 0.0,
            "clip_prefetch_file_details": [],
            "clip_prefetch_stop_reason": "never_started",
            "clip_prefetch_effective_max_bytes": 0,
            "clip_prefetch_ram_headroom_bound_bytes": 0,
            "clip_prefetch_threads": 0,
            "clip_fastsafe_start_at": None,
            "clip_fastsafe_done_at": None,
            "clip_fastsafe_ms": None,
            "clip_copy_event_recorded": False,
            "clip_copy_event_waited": False,
            "clip_copy_event_recorded_at": None,
            "clip_copy_event_waited_at": None,
            "clip_device_wide_sync_count": 0,
            "clip_targeted_event_sync_count": 0,
            "clip_prefetch_stop_requested_at": None,
            "clip_prefetch_workers_alive_at_stop": 0,
            "clip_prefetch_workers_alive_after_primary_join": 0,
            "clip_prefetch_workers_alive_at_demand_start": 0,
            "clip_prefetch_retirement_ms": None,
            "clip_prefetch_retirement_result": "not_started",
            "clip_source_fence_valid": True,
            "clip_forward_start_at": None,
            "clip_forward_end_at": None,
            "clip_forward_ms": None,
            "clip_forward_health": "UNKNOWN",
            "clip_ready_at": None,
            "clip_loader_execution_identity": None,
            "clip_fallback_count": 0,
            "clip_substage_tokenize_ms": None,
            "clip_substage_hydration_ms": None,
            "clip_substage_forward_inner_ms": None,
            "clip_substage_post_forward_ms": None,
            "clip_gpu_critical_start_at": None,
            "clip_gpu_critical_end_at": None,
            "clip_gpu_critical_ms": None,
            "unet_meta_start_at": None,
            "unet_meta_ready_at": None,
            "unet_meta_ms": None,
            "unet_prefetch_start_at": None,
            "unet_prefetch_end_at": None,
            "unet_prefetch_bytes": 0,
            "unet_prefetch_fraction": 0.0,
            "unet_prefetch_wall_ms": 0.0,
            "unet_prefetch_join_ms": 0.0,
            "unet_prefetch_overlap_with_setup_ms": 0.0,
            "unet_prefetch_file_details": [],
            "unet_prefetch_stop_reason": "never_started",
            "unet_prefetch_effective_max_bytes": 0,
            "unet_prefetch_ram_headroom_bound_bytes": 0,
            "unet_prefetch_threads": 0,
            "unet_fastsafe_start_at": None,
            "unet_fastsafe_done_at": None,
            "unet_fastsafe_ms": None,
            "unet_loader_execution_identity": None,
            "unet_fallback_count": 0,
            "unet_gpu_commit_wait_ms": 0.0,
            "unet_copy_event_recorded": False,
            "unet_copy_event_waited": False,
            "unet_copy_event_recorded_at": None,
            "unet_copy_event_waited_at": None,
            "unet_device_wide_sync_count": 0,
            "unet_targeted_event_sync_count": 0,
            "unet_prefetch_stop_requested_at": None,
            "unet_prefetch_workers_alive_at_stop": 0,
            "unet_prefetch_workers_alive_after_primary_join": 0,
            "unet_prefetch_workers_alive_at_demand_start": 0,
            "unet_prefetch_retirement_ms": None,
            "unet_prefetch_retirement_result": "not_started",
            "unet_source_fence_valid": True,
            "unet_ready_at": None,
            "model_readiness_gate_ms": None,
            "model_readiness_gate_at": None,
            "readiness_gated_by": "UNKNOWN",
            "model_readiness_status": "UNKNOWN",
            "unet_gpu_intervals": [],
            "unet_gpu_overlap_with_clip_forward_ms": None,
            "unet_gpu_overlap_with_clip_critical_ms": None,
            "prefetch_and_demand_overlap_detected": False,
            "source_fence_valid": True,
            "unet_gpu_overlap_with_clip_critical": False,
            "orchestration_fallback": False,
            "orchestration_fallback_reason": "",
            # E26: the speculative CLIP lane owns the CLIP source file when
            # active; the checkpoint prewarmer's clip prefetch is skipped so
            # one CLIP file -> one large read.
            "clip_speculative_owned": False,
        }
        if self.take_clip_speculative_ownership():
            # Speculative CLIP owns the CLIP source: do NOT start the
            # checkpoint prewarmer's clip prefetch (it would race the same
            # file).  UNET prefetch is released by the speculative lane's
            # completion callback (CLIP-first/UNET-second).  The storage
            # state is CLIP_PREFETCH-owned by the lane.
            return
        self.start_clip_prefetch()

    def _emit(self, name: str, metadata: Mapping[str, Any]) -> None:
        trace = self.trace
        if trace is None:
            return
        try:
            payload = dict(metadata)
            payload.setdefault("request_id", self.request_id)
            trace.emit(name, phase="execution", metadata=payload)
        except Exception:
            pass

    def set_trace(self, trace: Any) -> None:
        with self._lock:
            if trace is not None:
                self.trace = trace
                self.storage.set_trace(trace)

    def set_request_origin(self, origin: Optional[float] = None) -> None:
        self._request_origin = origin or time.monotonic()

    def set_paths(self, role: str, paths: Any) -> None:
        role = "clip" if role == "clip" else "unet"
        resolved = resolve_prewarm_paths(paths)
        if resolved:
            with self._lock:
                self.paths[role] = resolved

    def _start_prefetch(self, role: str, paths: Any) -> bool:
        if clean_lane.enabled():
            clean_lane.forbidden_activity(
                "checkpoint_volume_prefetch", getattr(self, "trace", None), role=role
            )
            return False
        if not env_flag("COMFYMODAL_V2_CHECKPOINT_PREWARM", default=False):
            return False
        resolved = resolve_prewarm_paths(paths)
        if not resolved:
            return False
        target = STORAGE_CLIP_PREFETCH if role == "clip" else STORAGE_UNET_PREFETCH
        try:
            if self.storage.storage_owner == STORAGE_CLIP_PREFETCH and role == "unet":
                if self.speculative_clip_owner():
                    # E26: the speculative CLIP lane owns the CLIP source; there
                    # is no prewarmer to retire.  Leave the storage state in
                    # CLIP_PREFETCH so the real CLIP demand performs the
                    # CLIP_PREFETCH → CLIP_DEMAND transition exactly once.
                    pass
                else:
                    self.before_clip_demand()
            elif self.storage.storage_owner == STORAGE_CLIP_DEMAND and role == "unet":
                self.storage.transition(target)
            elif self.storage.storage_owner == STORAGE_NONE:
                self.storage.transition(target)
            elif self.storage.storage_owner != target:
                raise ValueError(f"storage owner is {self.storage.storage_owner}")
            prewarmer = CheckpointPrewarmer()
            prewarmer.mark_setup_start()
            if not prewarmer.start(resolved):
                if self.storage.storage_owner == target:
                    self.storage.release()
                return False
            with self._lock:
                if role == "clip":
                    self.clip_prefetch = prewarmer
                    self._record["clip_prefetch_started"] = True
                    self._record["clip_prefetch_start_at"] = prewarmer.as_dict().get("prewarm_start_at")
                else:
                    self.unet_prefetch = prewarmer
                    self._record["unet_prefetch_start_at"] = prewarmer.as_dict().get("prewarm_start_at")
            self._emit("fast_cold_prefetch_start", {"role": role, "paths": resolved})
            return True
        except Exception as exc:
            self._record["orchestration_fallback"] = True
            self._record["orchestration_fallback_reason"] = f"prefetch_{role}:{type(exc).__name__}"
            return False

    def start_clip_prefetch(self, paths: Any = None) -> bool:
        if paths is not None:
            self.set_paths("clip", paths)
        if self.clip_prefetch is not None:
            return True
        if self.speculative_clip_owner():
            # E26: the speculative CLIP lane owns the CLIP source file; the
            # checkpoint prewarmer must NEVER also read it (one CLIP file ->
            # one large read).  The lane's completion callback retires the
            # storage state; this is a no-op.
            return True
        return self._start_prefetch("clip", self.paths.get("clip", []))

    def start_unet_prefetch(self, paths: Any = None) -> bool:
        if paths is not None:
            self.set_paths("unet", paths)
        if self.unet_prefetch is not None:
            return True
        return self._start_prefetch("unet", self.paths.get("unet", []))

    # ── E26: CLIP-first / UNET-second coordinated early-loader schedule ──
    # One coordinated ownership machine for the CLIP source file: either the
    # E26 speculative CLIP lane OR the checkpoint prewarmer (never both) owns
    # the single large CLIP read.  When speculative CLIP is active it takes
    # ownership and the prewarmer is skipped for clip; UNET source prefetch is
    # released only after the speculative CLIP read definitively finishes
    # (success or failure) so CLIP keeps the critical path and a failed
    # speculative read can never delay UNET.
    def _clip_speculative_active(self) -> bool:
        try:
            from .speculative_clip_hydration import (
                speculative_clip_hydration_enabled,
            )

            return speculative_clip_hydration_enabled()
        except Exception:
            return False

    def take_clip_speculative_ownership(self, paths: Any = None) -> bool:
        """Speculative CLIP owns the CLIP source file for this request.

        Called at plan receipt BEFORE the checkpoint prewarmer starts its
        clip prefetch.  When speculative CLIP hydration is enabled and the
        lane will read from the frozen manifest, the prewarmer must NOT also
        read the same file (one CLIP file -> one large read).  Returns True
        when the caller (speculative CLIP) owns the source; False when the
        prewarmer should own it (speculative disabled)."""
        if not self._clip_speculative_active():
            return False
        try:
            with self._lock:
                if self._record.get("clip_speculative_owned"):
                    return True
                self._record["clip_speculative_owned"] = True
            # Claim the storage owner for the CLIP source.  From NONE or
            # CLIP_PREFETCH we move to a CLIP-owned state; UNET prefetch
            # waits for the release callback.
            if self.storage.storage_owner in (STORAGE_NONE, STORAGE_CLIP_PREFETCH):
                self.storage.transition(STORAGE_CLIP_PREFETCH)
            self._emit("fast_cold_speculative_clip_owner", {
                "ownership": "speculative_clip",
                "release_condition": "spec_read_complete_or_failure",
            })
            return True
        except Exception as exc:
            self._record["orchestration_fallback"] = True
            self._record["orchestration_fallback_reason"] = (
                f"clip_spec_ownership:{type(exc).__name__}"
            )
            return False

    def on_speculative_clip_done(self) -> None:
        """CLIP-first/UNET-second release point.

        Invoked by the speculative CLIP lane exactly once when its source
        read definitively finishes (success OR failure).  Retires the CLIP
        source ownership and releases UNET source prefetch so it can overlap
        the CLIP forward window.  A failed speculative read must NOT delay
        UNET — this is the release path for both outcomes."""
        try:
            try:
                if self.storage.storage_owner == STORAGE_CLIP_PREFETCH:
                    self.storage.transition(STORAGE_CLIP_DEMAND)
            except Exception:
                pass
            self._emit("fast_cold_speculative_clip_done", {
                "unet_prefetch_released": 1,
                "storage_owner": self.storage.storage_owner,
            })
            self.start_unet_prefetch()
        except Exception:
            pass

    def speculative_clip_owner(self) -> bool:
        """True when the E26 speculative CLIP lane owns the CLIP source."""
        with self._lock:
            return bool(self._record.get("clip_speculative_owned", False))

    def _record_prefetch(self, role: str, prewarmer: CheckpointPrewarmer) -> dict[str, Any]:
        snapshot = prewarmer.as_dict()
        prefix = "clip" if role == "clip" else "unet"
        with self._lock:
            self._record[f"{prefix}_prefetch_bytes"] = int(snapshot.get("prewarm_bytes", 0) or 0)
            self._record[f"{prefix}_prefetch_fraction"] = float(snapshot.get("prewarm_fraction", 0.0) or 0.0)
            self._record[f"{prefix}_prefetch_wall_ms"] = float(snapshot.get("prewarm_wall_ms", 0.0) or 0.0)
            self._record[f"{prefix}_prefetch_join_ms"] = float(snapshot.get("prewarm_join_ms", 0.0) or 0.0)
            self._record[f"{prefix}_prefetch_overlap_with_setup_ms"] = float(
                snapshot.get("prewarm_overlap_with_setup_ms", 0.0) or 0.0
            )
            self._record[f"{prefix}_prefetch_file_details"] = list(
                snapshot.get("prewarm_file_details", []) or []
            )
            self._record[f"{prefix}_prefetch_stop_reason"] = str(
                snapshot.get("prewarm_stop_reason", "never_started")
            )
            self._record[f"{prefix}_prefetch_effective_max_bytes"] = int(
                snapshot.get("prewarm_effective_max_bytes", 0) or 0
            )
            self._record[f"{prefix}_prefetch_ram_headroom_bound_bytes"] = int(
                snapshot.get("prewarm_ram_headroom_bound_bytes", 0) or 0
            )
            self._record[f"{prefix}_prefetch_threads"] = int(
                snapshot.get("prewarm_threads", 0) or 0
            )
            self._record[f"{prefix}_prefetch_end_at"] = snapshot.get("prewarm_stop_at")
            self._record[f"{prefix}_prefetch_stop_requested_at"] = snapshot.get(
                "prefetch_stop_requested_at"
            )
            self._record[f"{prefix}_prefetch_workers_alive_at_stop"] = int(
                snapshot.get("prefetch_workers_alive_at_stop", 0) or 0
            )
            self._record[f"{prefix}_prefetch_workers_alive_after_primary_join"] = int(
                snapshot.get("prefetch_workers_alive_after_primary_join", 0) or 0
            )
            self._record[f"{prefix}_prefetch_workers_alive_at_demand_start"] = int(
                snapshot.get("prefetch_workers_alive_at_demand_start", 0) or 0
            )
            self._record[f"{prefix}_prefetch_retirement_ms"] = snapshot.get(
                "prefetch_retirement_ms"
            )
            self._record[f"{prefix}_prefetch_retirement_result"] = str(
                snapshot.get("prefetch_retirement_result", "not_started")
            )
            self._record[f"{prefix}_source_fence_valid"] = bool(
                snapshot.get("source_fence_valid", False)
            )
            self._record["source_fence_valid"] = bool(
                self._record.get("clip_source_fence_valid", True)
                and self._record.get("unet_source_fence_valid", True)
            )
            self.storage.add_wait(float(snapshot.get("prewarm_join_ms", 0.0) or 0.0))
        return snapshot

    def before_clip_demand(self, paths: Any = None) -> bool:
        if paths is not None:
            self.start_clip_prefetch(paths)
        prewarmer = self.clip_prefetch
        try:
            if prewarmer is not None:
                snapshot = prewarmer.as_dict()
                if snapshot.get("demand_loader_start_at") is None:
                    prewarmer.mark_setup_end()
                    joined = prewarmer.before_demand_load()
                    snapshot = self._record_prefetch("clip", prewarmer)
                else:
                    joined = bool(snapshot.get("prewarm_finished_before_demand", True))
                if not joined or not bool(snapshot.get("source_fence_valid", False)):
                    with self._lock:
                        self._record["prefetch_and_demand_overlap_detected"] = True
                        self._record["source_fence_valid"] = False
                        self._record["orchestration_fallback"] = True
                        self._record["orchestration_fallback_reason"] = (
                            "clip_source_fence_failed"
                        )
                    return False
            else:
                snapshot = None
                with self._lock:
                    self._record["clip_source_fence_valid"] = True
            if self.storage.storage_owner == STORAGE_CLIP_PREFETCH:
                self.storage.transition(STORAGE_CLIP_DEMAND)
            elif self.storage.storage_owner == STORAGE_NONE:
                self.storage.transition(STORAGE_CLIP_DEMAND)
            elif self.storage.storage_owner in (STORAGE_UNET_PREFETCH, STORAGE_UNET_DEMAND):
                # E26: the speculative CLIP lane owns the CLIP source.  Its
                # completion already retired CLIP_PREFETCH → CLIP_DEMAND and
                # released UNET prefetch, so by CLIP demand time the storage
                # owner is UNET_PREFETCH/UNET_DEMAND.  The CLIP source
                # ownership is resolved; the demand path reads the speculative
                # tensors (or falls back).  Return True without re-entering
                # the CLIP state machine (CLIP_DEMAND is not reachable from
                # UNET states by design).
                if not self.speculative_clip_owner():
                    raise ValueError(
                        f"storage owner is {self.storage.storage_owner} with no spec owner"
                    )
            elif self.storage.storage_owner != STORAGE_CLIP_DEMAND:
                raise ValueError(f"storage owner is {self.storage.storage_owner}")
            self._emit("fast_cold_storage_demand_start", {
                "role": "clip",
                "prefetch_joined": bool(snapshot is None or snapshot.get("prewarm_finished_before_demand", True)),
            })
            return True
        except Exception as exc:
            self._record["orchestration_fallback"] = True
            self._record["orchestration_fallback_reason"] = f"clip_demand:{type(exc).__name__}"
            return False

    def on_clip_forward_start(self) -> None:
        now = time.monotonic()
        with self._lock:
            if self._record["clip_forward_start_at"] is not None:
                return
            self._record["clip_forward_start_at"] = now
        self.start_unet_prefetch()
        self._emit("fast_cold_clip_forward_start", {})

    def on_clip_forward_end(self) -> None:
        now = time.monotonic()
        with self._lock:
            if self._record["clip_forward_end_at"] is None:
                self._record["clip_forward_end_at"] = now
                self._record["clip_forward_ms"] = _duration_ms(
                    self._record["clip_forward_start_at"], now
                )
                self._record["clip_ready_at"] = now
        self._clip_forward_done.set()
        self._emit("fast_cold_clip_forward_end", {})

    def mark_no_forward(self) -> None:
        now = time.monotonic()
        with self._lock:
            self._record["clip_ready_at"] = self._record["clip_ready_at"] or now
        self._no_forward.set()
        self.start_unet_prefetch()

    def wait_for_unet_commit(self) -> float:
        wait_start = time.monotonic()
        timeout = _env_int(COMMIT_WAIT_MS_ENV, 10_000) / 1000.0
        if self._record.get("clip_forward_start_at") is None and self._no_forward.is_set():
            return 0.0
        if self._clip_forward_done.is_set() or self._no_forward.is_set():
            return 0.0
        if not self._clip_forward_done.wait(timeout=max(0.0, timeout)) and not self._no_forward.is_set():
            self._record["orchestration_fallback"] = True
            self._record["orchestration_fallback_reason"] = "clip_commit_wait_timeout"
        return round((time.monotonic() - wait_start) * 1000.0, 3)

    def before_unet_demand(self, paths: Any = None) -> bool:
        if paths is not None:
            self.set_paths("unet", paths)
        commit_wait_ms = self.wait_for_unet_commit()
        with self._lock:
            self._record["unet_gpu_commit_wait_ms"] = round(
                float(self._record.get("unet_gpu_commit_wait_ms", 0.0) or 0.0)
                + commit_wait_ms,
                3,
            )
        prewarmer = self.unet_prefetch
        try:
            if prewarmer is not None:
                snapshot = prewarmer.as_dict()
                if snapshot.get("demand_loader_start_at") is None:
                    prewarmer.mark_setup_end()
                    joined = prewarmer.before_demand_load()
                    snapshot = self._record_prefetch("unet", prewarmer)
                else:
                    joined = bool(snapshot.get("prewarm_finished_before_demand", True))
                if not joined or not bool(snapshot.get("source_fence_valid", False)):
                    with self._lock:
                        self._record["prefetch_and_demand_overlap_detected"] = True
                        self._record["source_fence_valid"] = False
                        self._record["orchestration_fallback"] = True
                        self._record["orchestration_fallback_reason"] = (
                            "unet_source_fence_failed"
                        )
                    return False
            else:
                snapshot = None
                with self._lock:
                    self._record["unet_source_fence_valid"] = True
            if self.storage.storage_owner == STORAGE_CLIP_PREFETCH:
                # A cache-hit/no-forward path can reach UNET demand before a
                # CLIP demand hook.  Retire the CLIP prefetch first so the
                # state machine never takes a direct CLIP_PREFETCH ->
                # UNET_DEMAND transition.
                if not self.before_clip_demand():
                    return False
            if self.storage.storage_owner == STORAGE_UNET_PREFETCH:
                self.storage.transition(STORAGE_UNET_DEMAND)
            elif self.storage.storage_owner in (STORAGE_NONE, STORAGE_CLIP_DEMAND):
                self.storage.transition(STORAGE_UNET_DEMAND)
            elif self.storage.storage_owner != STORAGE_UNET_DEMAND:
                raise ValueError(f"storage owner is {self.storage.storage_owner}")
            self._emit("fast_cold_storage_demand_start", {
                "role": "unet",
                "prefetch_joined": bool(snapshot is None or snapshot.get("prewarm_finished_before_demand", True)),
            })
            return True
        except Exception as exc:
            self._record["orchestration_fallback"] = True
            self._record["orchestration_fallback_reason"] = f"unet_demand:{type(exc).__name__}"
            return False

    def record_clip_critical_start(self) -> None:
        now = time.monotonic()
        self._clip_critical_start = now
        with self._lock:
            self._record["clip_gpu_critical_start_at"] = now

    def record_clip_critical_end(self) -> None:
        now = time.monotonic()
        self._clip_critical_end = now
        with self._lock:
            self._record["clip_gpu_critical_end_at"] = now
            self._record["clip_gpu_critical_ms"] = _duration_ms(
                self._record.get("clip_gpu_critical_start_at"), now
            )

    def record_commit_wait(self, wait_ms: float) -> None:
        with self._lock:
            self._record["unet_gpu_commit_wait_ms"] = round(
                float(self._record.get("unet_gpu_commit_wait_ms", 0.0) or 0.0)
                + max(0.0, float(wait_ms or 0.0)), 3
            )

    def record_fastsafe(
        self,
        role: str,
        phase: str,
        *,
        event_recorded: Optional[bool] = None,
        execution_identity: Optional[str] = None,
        success: Optional[bool] = None,
    ) -> None:
        now = time.monotonic()
        prefix = "clip" if role == "clip" else "unet"
        with self._lock:
            if phase == "start":
                self._record[f"{prefix}_fastsafe_start_at"] = now
            else:
                self._record[f"{prefix}_fastsafe_done_at"] = now
                self._record[f"{prefix}_fastsafe_ms"] = _duration_ms(
                    self._record.get(f"{prefix}_fastsafe_start_at"), now
                )
            if execution_identity:
                self._record[f"{prefix}_loader_execution_identity"] = str(
                    execution_identity
                )
            if success is False:
                self._record[f"{prefix}_loader_execution_identity"] = "fallback"
                self._record[f"{prefix}_fallback_count"] = int(
                    self._record.get(f"{prefix}_fallback_count", 0) or 0
                ) + 1
            if event_recorded is not None:
                self._record[f"{prefix}_copy_event_recorded"] = bool(event_recorded)

    def record_loader_execution_identity(
        self, role: str, identity: str, *, fallback: bool = False
    ) -> None:
        prefix = "clip" if role == "clip" else "unet"
        with self._lock:
            self._record[f"{prefix}_loader_execution_identity"] = str(identity)
            if fallback:
                self._record[f"{prefix}_fallback_count"] = int(
                    self._record.get(f"{prefix}_fallback_count", 0) or 0
                ) + 1

    def record_unet_gpu_interval(
        self,
        start: Optional[float],
        end: Optional[float],
        *,
        identity: str,
    ) -> None:
        if start is None or end is None or end < start:
            return
        with self._lock:
            self._record.setdefault("unet_gpu_intervals", []).append(
                {
                    "start_at": float(start),
                    "end_at": float(end),
                    "identity": str(identity),
                }
            )

    def record_copy_event(self, role: str, recorded_at: Optional[float] = None) -> None:
        prefix = "clip" if role == "clip" else "unet"
        with self._lock:
            self._record[f"{prefix}_copy_event_recorded"] = True
            self._record[f"{prefix}_copy_event_recorded_at"] = (
                time.monotonic() if recorded_at is None else float(recorded_at)
            )

    def record_copy_event_wait(self, role: str, waited_at: Optional[float] = None) -> None:
        prefix = "clip" if role == "clip" else "unet"
        with self._lock:
            self._record[f"{prefix}_copy_event_waited"] = True
            self._record[f"{prefix}_copy_event_waited_at"] = (
                time.monotonic() if waited_at is None else float(waited_at)
            )
            self._record[f"{prefix}_targeted_event_sync_count"] = int(
                self._record.get(f"{prefix}_targeted_event_sync_count", 0) or 0
            ) + 1

    def record_device_wide_sync(self, role: str) -> None:
        prefix = "clip" if role == "clip" else "unet"
        with self._lock:
            self._record[f"{prefix}_device_wide_sync_count"] = int(
                self._record.get(f"{prefix}_device_wide_sync_count", 0) or 0
            ) + 1

    def record_clip_substage(self, stage: str, phase: str) -> None:
        """Record CLIP substage timing. stage: tokenize/hydration/forward_inner/post_forward. phase: start/end."""
        now = time.monotonic()
        key = f"clip_substage_{stage}_{phase}_at"
        with self._lock:
            self._record[key] = now
            if phase == "end":
                start_key = f"clip_substage_{stage}_start_at"
                ms_key = f"clip_substage_{stage}_ms"
                self._record[ms_key] = _duration_ms(self._record.get(start_key), now)

    def source_fence_failed(self) -> bool:
        with self._lock:
            return bool(
                not self._record.get("source_fence_valid", True)
                or self._record.get("orchestration_fallback_reason", "").endswith(
                    "source_fence_failed"
                )
            )

    def record_meta(self, phase: str) -> None:
        now = time.monotonic()
        with self._lock:
            key = "unet_meta_start_at" if phase == "start" else "unet_meta_ready_at"
            self._record[key] = now
            if phase != "start":
                self._record["unet_meta_ms"] = _duration_ms(
                    self._record.get("unet_meta_start_at"), now
                )

    def _final_record(self) -> dict[str, Any]:
        with self._lock:
            storage = self.storage.as_dict()
            self._record.update(storage)
            origin = self._request_origin or self.started_at
            self._record["request_origin_at"] = origin
            clip_ready = self._record.get("clip_ready_at")
            unet_ready = self._record.get("unet_ready_at")
            if clip_ready is not None and unet_ready is not None:
                gate = max(float(clip_ready), float(unet_ready))
                self._record["model_readiness_gate_at"] = gate
                self._record["model_readiness_gate_ms"] = round(
                    max(0.0, gate - origin) * 1000.0, 3
                )
                self._record["readiness_gated_by"] = (
                    "CLIP" if clip_ready > unet_ready
                    else "UNET" if unet_ready > clip_ready
                    else "TIE"
                )
                self._record["model_readiness_status"] = "KNOWN"
            else:
                self._record["model_readiness_gate_at"] = None
                self._record["model_readiness_gate_ms"] = None
                self._record["readiness_gated_by"] = "UNKNOWN"
                self._record["model_readiness_status"] = "UNKNOWN"
            clip_start = self._clip_critical_start or self._record.get("clip_forward_start_at")
            clip_end = self._clip_critical_end or self._record.get("clip_forward_end_at")
            forward_start = self._record.get("clip_forward_start_at")
            forward_end = self._record.get("clip_forward_end_at")
            intervals = list(self._record.get("unet_gpu_intervals") or [])
            if intervals:
                critical_ms = sum(
                    interval_overlap_ms(
                        clip_start,
                        clip_end,
                        item.get("start_at"),
                        item.get("end_at"),
                    ) or 0.0
                    for item in intervals
                )
                forward_ms = sum(
                    interval_overlap_ms(
                        forward_start,
                        forward_end,
                        item.get("start_at"),
                        item.get("end_at"),
                    ) or 0.0
                    for item in intervals
                )
                self._record["unet_gpu_overlap_with_clip_critical_ms"] = (
                    round(critical_ms, 3)
                    if clip_start is not None and clip_end is not None
                    else None
                )
                self._record["unet_gpu_overlap_with_clip_forward_ms"] = (
                    round(forward_ms, 3)
                    if forward_start is not None and forward_end is not None
                    else None
                )
                self._record["unet_gpu_overlap_with_clip_critical"] = (
                    bool(critical_ms > 0.0)
                    if clip_start is not None and clip_end is not None
                    else None
                )
            else:
                self._record["unet_gpu_overlap_with_clip_critical"] = None
                self._record["unet_gpu_overlap_with_clip_critical_ms"] = None
                self._record["unet_gpu_overlap_with_clip_forward_ms"] = None
            self._record["clip_forward_health"] = classify_clip_forward_health(
                self._record.get("clip_forward_ms")
            )
            clip_pf_start = self._record.get("clip_prefetch_start_at")
            clip_pf_end = self._record.get("clip_prefetch_end_at")
            clip_demand = self._record.get("clip_fastsafe_start_at")
            unet_pf_start = self._record.get("unet_prefetch_start_at")
            unet_pf_end = self._record.get("unet_prefetch_end_at")
            unet_demand = self._record.get("unet_fastsafe_start_at")
            self._record["prefetch_and_demand_overlap_detected"] = bool(
                (clip_pf_start is not None and clip_demand is not None and clip_pf_end is not None and clip_pf_end > clip_demand)
                or (unet_pf_start is not None and unet_demand is not None and unet_pf_end is not None and unet_pf_end > unet_demand)
                or self._record.get("clip_prefetch_workers_alive_at_demand_start", 0)
                or self._record.get("unet_prefetch_workers_alive_at_demand_start", 0)
                or self._record.get("prefetch_and_demand_overlap_detected", False)
            )
            self._record["source_fence_valid"] = bool(
                self._record.get("clip_source_fence_valid", True)
                and self._record.get("unet_source_fence_valid", True)
            )
            self._record["storage_wait_total_ms"] = round(
                float(self.storage.storage_wait_total_ms), 3
            )
            self._record["storage_owner_transition_count"] = len(self.storage.transitions)
            return dict(self._record)

    def finalize(self) -> dict[str, Any]:
        with self._lock:
            if self._finalized:
                return dict(self._record)
            self._finalized = True
        source_fence_ok = True
        for role, prewarmer in (("clip", self.clip_prefetch), ("unet", self.unet_prefetch)):
            if prewarmer is None:
                with self._lock:
                    self._record[f"{role}_source_fence_valid"] = True
                continue
            snapshot = prewarmer.as_dict()
            needs_retirement = (
                snapshot.get("demand_loader_start_at") is None
                or not bool(snapshot.get("source_fence_valid", False))
            )
            if needs_retirement:
                try:
                    prewarmer.mark_setup_end()
                    joined = prewarmer.before_demand_load()
                    self._record_prefetch(role, prewarmer)
                    if not joined:
                        source_fence_ok = False
                except Exception:
                    source_fence_ok = False
                    with self._lock:
                        self._record[f"{role}_source_fence_valid"] = False
            snapshot = prewarmer.as_dict()
            if not bool(snapshot.get("source_fence_valid", False)):
                source_fence_ok = False
        if source_fence_ok:
            try:
                self.storage.release()
            except Exception:
                self._record["orchestration_fallback"] = True
                self._record["orchestration_fallback_reason"] = "storage_release"
        else:
            with self._lock:
                self._record["source_fence_valid"] = False
                self._record["orchestration_fallback"] = True
                self._record["orchestration_fallback_reason"] = (
                    "source_fence_retirement_failed"
                )
        record = self._final_record()
        self._emit("fast_cold_orchestration", record)
        return record


_CONTROLLERS: dict[str, FastColdOrchestrator] = {}
_CONTROLLERS_LOCK = threading.RLock()


def begin_request(request_id: str, model_spec: Any = None, trace: Any = None) -> Optional[FastColdOrchestrator]:
    if not enabled() or not request_id:
        return None
    rid = _request_id(request_id, trace)
    with _CONTROLLERS_LOCK:
        controller = _CONTROLLERS.get(rid)
        legacy_id = str(request_id or "")
        if controller is None and legacy_id and legacy_id != rid:
            controller = _CONTROLLERS.pop(legacy_id, None)
            if controller is not None:
                controller.request_id = rid
                controller.storage.request_id = rid
                controller._record["request_id"] = rid
                _CONTROLLERS[rid] = controller
        if controller is None or controller._finalized:
            controller = FastColdOrchestrator(rid, model_spec=model_spec, trace=trace)
            _CONTROLLERS[rid] = controller
        else:
            controller.set_trace(trace)
        return controller


def get_controller(request_id: str = "", trace: Any = None) -> Optional[FastColdOrchestrator]:
    rid = _request_id(request_id, trace)
    if not rid:
        return None
    with _CONTROLLERS_LOCK:
        return _CONTROLLERS.get(rid)


def attach_trace(request_id: str, trace: Any) -> Optional[FastColdOrchestrator]:
    controller = get_controller(request_id, trace)
    if controller is not None:
        controller.set_trace(trace)
    return controller


def finalize_request(request_id: str, trace: Any = None) -> Optional[dict[str, Any]]:
    rid = _request_id(request_id, trace)
    with _CONTROLLERS_LOCK:
        controller = _CONTROLLERS.pop(rid, None)
    if controller is None:
        return None
    controller.set_trace(trace)
    return controller.finalize()


def notify_clip_critical(request_id: str, trace: Any, active: bool) -> None:
    controller = get_controller(request_id, trace)
    if controller is None:
        return
    if active:
        controller.record_clip_critical_start()
    else:
        controller.record_clip_critical_end()


def before_clip_demand(request_id: str = "", trace: Any = None, paths: Any = None) -> bool:
    controller = get_controller(request_id, trace)
    return True if controller is None else controller.before_clip_demand(paths)


def before_unet_demand(request_id: str = "", trace: Any = None, paths: Any = None) -> bool:
    controller = get_controller(request_id, trace)
    return True if controller is None else controller.before_unet_demand(paths)


def record_copy_event(role: str, request_id: str = "", trace: Any = None) -> None:
    controller = get_controller(request_id, trace)
    if controller is not None:
        controller.record_copy_event(role)


def record_copy_event_wait(role: str, request_id: str = "", trace: Any = None) -> None:
    controller = get_controller(request_id, trace)
    if controller is not None:
        controller.record_copy_event_wait(role)


def record_device_wide_sync(role: str, request_id: str = "", trace: Any = None) -> None:
    controller = get_controller(request_id, trace)
    if controller is not None:
        controller.record_device_wide_sync(role)


def source_fence_failed(request_id: str = "", trace: Any = None) -> bool:
    controller = get_controller(request_id, trace)
    return bool(controller is not None and controller.source_fence_failed())


def record_fastsafe(
    role: str,
    phase: str,
    request_id: str = "",
    trace: Any = None,
    *,
    event_recorded: Optional[bool] = None,
    execution_identity: Optional[str] = None,
    success: Optional[bool] = None,
) -> None:
    controller = get_controller(request_id, trace)
    if controller is not None:
        controller.record_fastsafe(
            role,
            phase,
            event_recorded=event_recorded,
            execution_identity=execution_identity,
            success=success,
        )


def record_loader_execution_identity(
    role: str,
    identity: str,
    request_id: str = "",
    trace: Any = None,
    *,
    fallback: bool = False,
) -> None:
    controller = get_controller(request_id, trace)
    if controller is not None:
        controller.record_loader_execution_identity(
            role, identity, fallback=fallback
        )


def record_unet_gpu_interval(
    start: Optional[float],
    end: Optional[float],
    identity: str,
    request_id: str = "",
    trace: Any = None,
) -> None:
    controller = get_controller(request_id, trace)
    if controller is not None:
        controller.record_unet_gpu_interval(start, end, identity=identity)


def record_meta(phase: str, request_id: str = "", trace: Any = None) -> None:
    controller = get_controller(request_id, trace)
    if controller is not None:
        controller.record_meta(phase)


def record_unet_ready(request_id: str = "", trace: Any = None) -> None:
    controller = get_controller(request_id, trace)
    if controller is not None:
        with controller._lock:
            controller._record["unet_ready_at"] = time.monotonic()


def record_commit_wait(wait_ms: float, request_id: str = "", trace: Any = None) -> None:
    controller = get_controller(request_id, trace)
    if controller is not None:
        controller.record_commit_wait(wait_ms)


def mark_clip_forward_start(request_id: str = "", trace: Any = None) -> None:
    controller = get_controller(request_id, trace)
    if controller is not None:
        controller.on_clip_forward_start()


def mark_clip_forward_end(request_id: str = "", trace: Any = None) -> None:
    controller = get_controller(request_id, trace)
    if controller is not None:
        controller.on_clip_forward_end()


def mark_no_forward(request_id: str = "", trace: Any = None) -> None:
    controller = get_controller(request_id, trace)
    if controller is not None:
        controller.mark_no_forward()


def set_request_origin(origin: Optional[float] = None, request_id: str = "", trace: Any = None) -> None:
    controller = get_controller(request_id, trace)
    if controller is not None:
        controller.set_request_origin(origin)


def record_clip_substage(stage: str, phase: str, request_id: str = "", trace: Any = None) -> None:
    controller = get_controller(request_id, trace)
    if controller is not None:
        controller.record_clip_substage(stage, phase)


def reset_for_tests() -> None:
    with _CONTROLLERS_LOCK:
        controllers = list(_CONTROLLERS.values())
        _CONTROLLERS.clear()
    for controller in controllers:
        try:
            controller.finalize()
        except Exception:
            pass


__all__ = [
    "MASTER_FLAG",
    "STORAGE_STATES",
    "STORAGE_NONE",
    "STORAGE_CLIP_PREFETCH",
    "STORAGE_CLIP_DEMAND",
    "STORAGE_UNET_PREFETCH",
    "STORAGE_UNET_DEMAND",
    "StorageOwnershipController",
    "FastColdOrchestrator",
    "interval_overlap_ms",
    "classify_clip_forward_health",
    "begin_request",
    "get_controller",
    "attach_trace",
    "finalize_request",
    "before_clip_demand",
    "before_unet_demand",
    "record_copy_event",
    "record_copy_event_wait",
    "record_device_wide_sync",
    "source_fence_failed",
    "SourceFenceFailure",
    "is_source_fence_failure",
    "record_fastsafe",
    "record_loader_execution_identity",
    "record_unet_gpu_interval",
    "record_meta",
    "record_unet_ready",
    "record_commit_wait",
    "mark_clip_forward_start",
    "mark_clip_forward_end",
    "mark_no_forward",
    "notify_clip_critical",
    "set_request_origin",
    "record_clip_substage",
    "resolve_model_paths",
    "reset_for_tests",
]
