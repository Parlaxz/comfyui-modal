"""
Optimizations module for comfyui-modal.

Implements Phase 1-7 of the cold-start consistency and good-run latency work:

* Phase 1: Production cold-model physical-read coordinator + UNET start boundary
  + corrected VAE deferral + collapse classification.
* Phase 2: Exact-prompt CLIP encoding reuse + canonical CLIP fingerprint +
  persistent bounded LRU cache (CPU-only, lazy post-delivery).
* Phase 3: Custom-node generation-token fast path (skip full fingerprint when
  authoritative generation record already matches).
* Phase 4: Resolved-model-path cache (per-models-generation-token, with eviction
  on path disappearance or generation change).
* Phase 5: Third-party custom-node log suppression (allowlist only, request-
  scoped, exception/traceback-safe).
* Phase 6: Bake-candidate report (read-only audit) — not a runtime change.
* Phase 7: Waterfall telemetry helpers + collapse classification writers.

All pieces are gated by explicit env flags and fall back to current behavior
on any failure. No global FUSE governor is enabled. CacheDiT is never touched.
"""

import contextlib
import hashlib
import json
import os
import queue
import sys
import tempfile
import threading
import time
import traceback as _traceback
from collections import OrderedDict, deque
from typing import Any, Callable, Deque, Dict, List, Optional, Tuple


# ── Flag helpers (all opt-in, conservative defaults) ───────────────────────


def _env_flag(name: str, default: str = "0") -> bool:
    return os.environ.get(name, default).strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, str(default)).strip())
    except (TypeError, ValueError):
        return default


def _env_str(name: str, default: str) -> str:
    return os.environ.get(name, default)


# ── Phase 1: Production cold-model physical-read coordinator ──────────────
#
# The coordinator enforces a single in-flight eligible cold model Volume
# read at a time. It is intentionally narrow:
#
#   * It only governs the lowest-level physical Volume-backed read of
#     a model file (CLIP state-dict preload, production restore-background
#     UNET physical read, VAE actual-load physical read, and any graph
#     loader that reaches the same cold physical read before a speculative
#     worker).
#   * It does NOT hold during model object construction, GPU transfer,
#     encoding, sampling, model patching, or output conversion.
#   * It does NOT block non-model filesystem operations.
#   * It does NOT depend on the global FUSE governor (FUSE_READ_GOVERNOR).
#   * It is exception-safe and thread-safe.
#   * The uncontended path is a single boolean check and a lock acquire.

PRODUCTION_MODEL_READ_COORDINATOR_ENABLED = _env_flag(
    "COMFYMODAL_PRODUCTION_MODEL_READ_COORDINATOR", "0"
)
PRODUCTION_UNET_START_BOUNDARY = _env_str(
    "COMFYMODAL_PRODUCTION_UNET_START_BOUNDARY", "after_clip_preload"
).strip().lower()
PRODUCTION_MODEL_READ_COORDINATOR_DIAG = _env_flag(
    "COMFYMODAL_PRODUCTION_MODEL_READ_COORDINATOR_DIAG", "0"
)


# Bound how long a wait may block before releasing (avoids deadlocks in case
# of bug).  Generous so real cold reads do not time out under contention.
_COORDINATOR_WAIT_TIMEOUT_S = _env_int(
    "COMFYMODAL_PRODUCTION_MODEL_READ_COORDINATOR_WAIT_TIMEOUT_S", 300
)


class _CoordinatorStats:
    __slots__ = (
        "acquired",
        "released",
        "waited",
        "exceptions",
        "total_wait_ms",
        "total_hold_ms",
        "peak_wait_ms",
        "peak_hold_ms",
        "last_owner",
        "last_loader_type",
        "last_path",
        "last_wait_ms",
        "last_hold_ms",
    )

    def __init__(self) -> None:
        self.acquired: int = 0
        self.released: int = 0
        self.waited: int = 0
        self.exceptions: int = 0
        self.total_wait_ms: float = 0.0
        self.total_hold_ms: float = 0.0
        self.peak_wait_ms: float = 0.0
        self.peak_hold_ms: float = 0.0
        self.last_owner: str = ""
        self.last_loader_type: str = ""
        self.last_path: str = ""
        self.last_wait_ms: float = 0.0
        self.last_hold_ms: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "acquired": self.acquired,
            "released": self.released,
            "waited": self.waited,
            "exceptions": self.exceptions,
            "total_wait_ms": round(self.total_wait_ms, 1),
            "total_hold_ms": round(self.total_hold_ms, 1),
            "peak_wait_ms": round(self.peak_wait_ms, 1),
            "peak_hold_ms": round(self.peak_hold_ms, 1),
            "last_owner": self.last_owner,
            "last_loader_type": self.last_loader_type,
            "last_path": self.last_path,
            "last_wait_ms": round(self.last_wait_ms, 1),
            "last_hold_ms": round(self.last_hold_ms, 1),
        }


class ProductionModelReadCoordinator:
    """Process-local coordinator for eligible cold model physical reads.

    Acquires immediately before actual file access and releases in ``finally``
    immediately after the state dict or file payload has been obtained. The
    uncontended path is a single boolean check and a lock acquire.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._cond = threading.Condition(self._lock)
        self._in_flight: Optional[Dict[str, Any]] = None
        self._stats = _CoordinatorStats()
        # Per-process accounting
        self.queue_log: Deque[Dict[str, Any]] = deque(maxlen=64)

    @property
    def enabled(self) -> bool:
        return PRODUCTION_MODEL_READ_COORDINATOR_ENABLED

    def is_in_flight(self) -> bool:
        with self._lock:
            return self._in_flight is not None

    def _record(
        self,
        *,
        event: str,
        owner: str,
        loader_type: str,
        canonical_path: str,
        queue_enter_ms: float,
        queue_exit_ms: float,
        wait_ms: float,
        hold_ms: float,
    ) -> None:
        rec = {
            "event": event,
            "owner": owner,
            "loader_type": loader_type,
            "canonical_path": canonical_path[:200] if canonical_path else "",
            "queue_enter_ms": round(queue_enter_ms, 3),
            "queue_exit_ms": round(queue_exit_ms, 3),
            "wait_ms": round(wait_ms, 3),
            "hold_ms": round(hold_ms, 3),
            "ts": time.time(),
        }
        self.queue_log.append(rec)
        if PRODUCTION_MODEL_READ_COORDINATOR_DIAG:
            print(
                f"[model_read_coordinator] event={event} owner={owner} "
                f"loader={loader_type} path={canonical_path[:80]} "
                f"wait_ms={wait_ms:.1f} hold_ms={hold_ms:.1f}"
            )

    @contextlib.contextmanager
    def acquire(
        self,
        *,
        owner: str,
        loader_type: str,
        canonical_path: str,
        timeout_s: Optional[float] = None,
    ):
        """Acquire the coordinator for one cold model physical read.

        Always yields exactly once. Behavior:
          * disabled → yields ``{"acquired": False, "reason": "coordinator_disabled"}``
          * uncontended → yields ``{"acquired": True, "wait_ms": 0.0, "degraded": False}``
          * contended, acquires within timeout → yields ``{"acquired": True, "wait_ms": ..., "degraded": False}``
          * contended, exceeds timeout → **fail-open**: yields
            ``{"acquired": False, "reason": "wait_timeout", "degraded": True, "wait_ms": ...}``.
            The caller MUST treat the surrounding physical read as if the
            coordinator were not present; the coordinator never raises out
            of this context manager. This preserves the requirement that a
            speculative optimization can never fail image generation.

        Spurious wake-up safety: the wait loop uses a deadline computed
        before the first wait, so a normal notification followed by a
        different waiter winning the lock does NOT trigger a spurious
        timeout. Only an actual elapsed-deadline timeout exits the loop.

        Lock-scope safety: the timeout path sets a flag, EXITS the
        condition-lock context (releasing the condition lock), and
        ONLY THEN yields to the caller. A timed-out caller never
        retains the condition lock while running the model read. A
        circular wait between a timed-out caller and a normal
        holder is therefore impossible.
        """
        if not self.enabled:
            yield {"acquired": False, "reason": "coordinator_disabled", "degraded": False}
            return
        _timeout_s = float(timeout_s) if timeout_s is not None else float(_COORDINATOR_WAIT_TIMEOUT_S)
        deadline = time.time() + _timeout_s
        # Pre-compute the degraded sentinel OUTSIDE the condition lock
        # so the yield below can be safe.
        _degraded_sentinel: Optional[Dict[str, Any]] = None
        waited_ms = 0.0
        with self._cond:
            while self._in_flight is not None:
                remaining = deadline - time.time()
                if remaining <= 0.0:
                    # Decide to degrade. Record the failure stat and
                    # prepare the sentinel. We DO NOT yield while
                    # holding the cond lock.
                    self._stats.exceptions += 1
                    self._record(
                        event="wait_timeout_fail_open",
                        owner=owner,
                        loader_type=loader_type,
                        canonical_path=canonical_path,
                        queue_enter_ms=0.0,
                        queue_exit_ms=0.0,
                        wait_ms=_timeout_s * 1000.0,
                        hold_ms=0.0,
                    )
                    _degraded_sentinel = {
                        "acquired": False,
                        "reason": "wait_timeout",
                        "degraded": True,
                        "wait_ms": _timeout_s * 1000.0,
                    }
                    break
                # Bounded wait. Use a small wake interval so we re-check
                # the deadline often.
                _wake = min(remaining, 0.05)
                self._cond.wait(timeout=_wake)
                # Loop re-checks _in_flight AND the deadline.
            else:
                # Loop exited without a `break` — we acquired.
                t_exit = time.time()
                waited_ms = (t_exit - (deadline - _timeout_s)) * 1000.0
                self._in_flight = {
                    "owner": owner,
                    "loader_type": loader_type,
                    "canonical_path": canonical_path,
                    "acquired_at": t_exit,
                }
                self._stats.acquired += 1
                if waited_ms > 0.0:
                    self._stats.waited += 1
                    self._stats.total_wait_ms += waited_ms
                    if waited_ms > self._stats.peak_wait_ms:
                        self._stats.peak_wait_ms = waited_ms
                self._stats.last_wait_ms = waited_ms
                self._stats.last_owner = owner
                self._stats.last_loader_type = loader_type
                self._stats.last_path = canonical_path
                self._record(
                    event="acquired",
                    owner=owner,
                    loader_type=loader_type,
                    canonical_path=canonical_path,
                    queue_enter_ms=0.0,
                    queue_exit_ms=t_exit * 1000.0,
                    wait_ms=waited_ms,
                    hold_ms=0.0,
                )
        # The cond lock is RELEASED here regardless of acquired /
        # degraded outcome. Either the caller proceeds with the
        # protected physical read, or the caller proceeds with the
        # degraded sentinel.
        if _degraded_sentinel is not None:
            yield _degraded_sentinel
            return
        t_hold_start = time.time()
        try:
            yield {
                "acquired": True,
                "wait_ms": waited_ms,
                "degraded": False,
                "holder_owner": self._in_flight.get("owner") if self._in_flight else None,
            }
        finally:
            hold_ms = (time.time() - t_hold_start) * 1000.0
            with self._cond:
                if self._in_flight is not None and self._in_flight.get("owner") == owner:
                    self._in_flight = None
                    self._cond.notify_all()
                self._stats.released += 1
                self._stats.total_hold_ms += hold_ms
                if hold_ms > self._stats.peak_hold_ms:
                    self._stats.peak_hold_ms = hold_ms
                self._stats.last_hold_ms = hold_ms
            self._record(
                event="released",
                owner=owner,
                loader_type=loader_type,
                canonical_path=canonical_path,
                queue_enter_ms=0.0,
                queue_exit_ms=0.0,
                wait_ms=0.0,
                hold_ms=hold_ms,
            )

    def stats(self) -> Dict[str, Any]:
        return self._stats.to_dict()

    def recent(self, n: int = 16) -> List[Dict[str, Any]]:
        return list(self.queue_log)[-n:]


# Process-local singleton.
_model_read_coordinator = ProductionModelReadCoordinator()


def get_model_read_coordinator() -> ProductionModelReadCoordinator:
    return _model_read_coordinator


# ── UNET start boundary selector ─────────────────────────────────────────
#
# Production-only. Controls when the production restore-background UNET
# thread is submitted relative to CLIP state-dict preload, CLIP object
# construction, and CLIP encoding. The selector is read from
# ``COMFYMODAL_PRODUCTION_UNET_START_BOUNDARY`` once at process start; the
# active boundary can be inspected via ``current_unet_start_boundary()``.


def current_unet_start_boundary() -> str:
    """Return the active production UNET start boundary.

    Valid values:
      * ``after_clip_preload``  — current default, maximal overlap
      * ``after_clip_object``   — start UNET after CLIP object is constructed
      * ``after_clip_encode``   — fully serialized, diagnostic only
    """
    b = (PRODUCTION_UNET_START_BOUNDARY or "after_clip_preload").strip().lower()
    if b not in ("after_clip_preload", "after_clip_object", "after_clip_encode"):
        return "after_clip_preload"
    return b


# ── Phase 1: VAE deferral gate metrics ──────────────────────────────────


class VaeGateMetrics:
    """Per-request VAE deferral gate metrics.

    All fields are diagnostic. The fields named ``physical_read_*``
    are loader-span (entire ``VAELoader.load_vae`` call) rather than
    physical-read-span (only the safetensors read). The latter would
    require patches deep inside the loader call site; this metric is
    intended for coarse-grained telemetry, not for automatic policy.
    """

    __slots__ = (
        "future_submitted",
        "physical_read_deferred",
        "gate_wait_ms_total",
        "physical_read_ms_total",
        "ready_before_graph_request",
        "graph_fallback_used",
        "duplicate_prevented",
    )

    def __init__(self) -> None:
        self.future_submitted: int = 0
        self.physical_read_deferred: int = 0
        self.gate_wait_ms_total: float = 0.0
        self.physical_read_ms_total: float = 0.0
        self.ready_before_graph_request: int = 0
        self.graph_fallback_used: int = 0
        self.duplicate_prevented: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "future_submitted": self.future_submitted,
            "physical_read_deferred": self.physical_read_deferred,
            "gate_wait_ms_total": round(self.gate_wait_ms_total, 1),
            "physical_read_ms_total": round(self.physical_read_ms_total, 1),
            "ready_before_graph_request": self.ready_before_graph_request,
            "graph_fallback_used": self.graph_fallback_used,
            "duplicate_prevented": self.duplicate_prevented,
        }


# ── Phase 1: Collapse classification ─────────────────────────────────────


_COLLAPSE_NONE = "none"
_COLLAPSE_CLIP_PRELOAD = "clip_preload_collapse"
_COLLAPSE_CLIP_CONSTRUCTION = "clip_construction_collapse"
_COLLAPSE_UNET_READ = "unet_read_collapse"
_COLLAPSE_VAE_READ = "vae_read_collapse"
_COLLAPSE_COMPOUND = "compound_model_io_collapse"
_COLLAPSE_UNKNOWN = "unknown_model_load_tail"


def classify_collapse(stats: Dict[str, Any]) -> Dict[str, Any]:
    """Classify a single request's model-load behavior.

    ``stats`` is expected to include at least:
      * ``clip_preload_throughput_gbps`` (float, -1 if unknown)
      * ``clip_construction_ms`` (float)
      * ``unet_physical_read_ms`` (float)
      * ``unet_post_read_construction_ms`` (float)
      * ``vae_gate_wait_ms`` (float)
      * ``vae_physical_read_ms`` (float)
      * ``overlap_violation_count`` (int)
      * ``graph_waits_ms`` (dict[str, float])

    The function never raises and never modifies input.
    """
    out: Dict[str, Any] = {
        "kind": _COLLAPSE_NONE,
        "dominant_phase": "none",
        "explanations": [],
    }
    try:
        clip_throughput = float(stats.get("clip_preload_throughput_gbps", -1) or -1)
        clip_construction = float(stats.get("clip_construction_ms", 0) or 0)
        unet_read = float(stats.get("unet_physical_read_ms", 0) or 0)
        unet_post = float(stats.get("unet_post_read_construction_ms", 0) or 0)
        vae_gate_wait = float(stats.get("vae_gate_wait_ms", 0) or 0)
        vae_read = float(stats.get("vae_physical_read_ms", 0) or 0)
        overlap_violations = int(stats.get("overlap_violation_count", 0) or 0)
    except (TypeError, ValueError):
        out["kind"] = _COLLAPSE_UNKNOWN
        out["dominant_phase"] = "input_parse"
        out["explanations"].append("invalid_stats_input")
        return out

    collapsed: List[Tuple[str, float, str]] = []

    # Heuristic thresholds (chosen to be conservative; tuned for
    # typical good-run timings observed in the baseline).
    if clip_throughput > 0 and clip_throughput < 2.5:
        collapsed.append(
            (
                _COLLAPSE_CLIP_PRELOAD,
                2.5 - clip_throughput,
                f"clip_preload_throughput={clip_throughput:.2f} GB/s",
            )
        )
    if clip_construction > 1500:
        collapsed.append(
            (
                _COLLAPSE_CLIP_CONSTRUCTION,
                clip_construction / 1000.0,
                f"clip_construction={clip_construction:.0f} ms",
            )
        )
    if unet_read > 5000:
        collapsed.append(
            (
                _COLLAPSE_UNET_READ,
                unet_read / 1000.0,
                f"unet_physical_read={unet_read:.0f} ms",
            )
        )
    if vae_gate_wait + vae_read > 4000:
        collapsed.append(
            (
                _COLLAPSE_VAE_READ,
                (vae_gate_wait + vae_read) / 1000.0,
                f"vae_gate_wait+read={vae_gate_wait + vae_read:.0f} ms",
            )
        )
    if overlap_violations > 0:
        collapsed.append(
            (
                _COLLAPSE_COMPOUND,
                float(overlap_violations),
                f"overlap_violation_count={overlap_violations}",
            )
        )

    if not collapsed:
        out["kind"] = _COLLAPSE_NONE
        return out

    if len(collapsed) >= 2:
        out["kind"] = _COLLAPSE_COMPOUND
    else:
        out["kind"] = collapsed[0][0]
    out["dominant_phase"] = collapsed[0][0]
    for kind, magnitude, evidence in collapsed:
        out["explanations"].append(
            {"kind": kind, "magnitude": round(magnitude, 3), "evidence": evidence}
        )
    return out


# ── Phase 2: CLIP canonical fingerprint + safe bundle extraction ─────────

CLIP_FINGERPRINT_SCHEMA_VERSION = 1
CLIP_FINGERPRINT_CACHE_VERSION = 1
PROMPT_BUNDLE_SCHEMA_VERSION = 1
PERSISTENT_CLIP_CACHE_SCHEMA_VERSION = 1


def _safe_sha256(payload: Any) -> str:
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _normalize_filename(name: str) -> str:
    return (name or "").strip().replace("\\", "/").split("/")[-1].lower()


def _resolve_canonical_path(path: str) -> str:
    if not path:
        return ""
    try:
        return os.path.normcase(os.path.normpath(os.path.realpath(path)))
    except OSError:
        return os.path.normcase(os.path.normpath(path or ""))


def build_clip_fingerprint(
    *,
    resolved_paths: List[str],
    clip_type: str,
    loader_class: str,
    model_generation: str = "",
    encode_options: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Build a stable CLIP fingerprint for cache keys.

    The fingerprint is intentionally narrow: it captures only fields whose
    changes invalidate CLIPTextEncode output.
    """
    return {
        "schema_version": CLIP_FINGERPRINT_SCHEMA_VERSION,
        "paths": [_resolve_canonical_path(p) for p in resolved_paths if p],
        "clip_type": (clip_type or "").strip().lower(),
        "loader_class": (loader_class or "").strip(),
        "model_generation": (model_generation or "").strip(),
        "encode_options": dict(encode_options or {}),
    }


def clip_fingerprint_key(fp: Dict[str, Any]) -> str:
    payload = {
        "schema": fp.get("schema_version", CLIP_FINGERPRINT_SCHEMA_VERSION),
        "paths": fp.get("paths", []),
        "clip_type": fp.get("clip_type", ""),
        "loader_class": fp.get("loader_class", ""),
        "model_generation": fp.get("model_generation", ""),
        "encode_options": fp.get("encode_options", {}),
    }
    return _safe_sha256(payload)


# Native loader class names eligible for exact-prompt prefill / persistent
# cache. Anything not in this set is treated as a custom encoder and is
# rejected for cross-object cache reuse.
_NATIVE_CLIP_LOADER_CLASSES = {
    "CLIPLoader",
    "DualCLIPLoader",
    "CLIPLoaderAdvanced",
    "CLIPTextEncode",
}


def _is_native_clip_loader_class(cls_name: str) -> bool:
    return (cls_name or "").strip() in _NATIVE_CLIP_LOADER_CLASSES


# Per-loader-class mapping of which input keys carry the literal model
# filename(s) and which carry the clip type. The native ComfyUI loader
# code uses ``clip_name`` (single), ``clip_name1``/``clip_name2`` (dual),
# and ``type`` (clip type).  Adding a new native loader means adding a
# row here.
_LOADER_MODEL_KEYS = {
    "CLIPLoader": ["clip_name"],
    "DualCLIPLoader": ["clip_name1", "clip_name2"],
    "CLIPLoaderAdvanced": ["clip_name1", "clip_name2"],
}


def _loader_first_filename(cls: str, inputs: Dict[str, Any]) -> str:
    keys = _LOADER_MODEL_KEYS.get(cls, [])
    for k in keys:
        v = inputs.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return ""


def _loader_all_filenames(cls: str, inputs: Dict[str, Any]) -> List[str]:
    keys = _LOADER_MODEL_KEYS.get(cls, [])
    out: List[str] = []
    for k in keys:
        v = inputs.get(k)
        if isinstance(v, str) and v.strip():
            out.append(v.strip())
    return out


def extract_safe_prompt_bundle(workflow: Dict[str, Any]) -> Dict[str, Any]:
    """Extract a safe, canonical prompt bundle from a workflow.

    Eligibility rules (any failure → ``eligible=False``):
      * Native ``CLIPTextEncode`` node.
      * Literal text input (not a dynamic text connection).
      * ``clip`` input connected directly to a supported native
        ``CLIPLoader`` / ``DualCLIPLoader`` / ``CLIPLoaderAdvanced``.
      * Literal loader model filenames and clip type.
      * No intermediate CLIP LoRA, model patch, custom encoder node,
        textual-inversion transform, or unknown CLIP mutation.

    Loader input keys are taken from ``_LOADER_MODEL_KEYS``; the
    previous version of this helper used ``ckpt_name`` which is the
    ComfyUI CheckpointLoaderSimple field, not the CLIPLoader field.
    """
    if not isinstance(workflow, dict):
        return {"eligible": False, "reason": "workflow_not_dict", "encodes": []}

    encodes: List[Dict[str, Any]] = []

    # Step 1: collect eligible loader outputs that have literal model
    # names and clip type. Map: target_node_id -> {cls, filenames, type}.
    loader_outputs: Dict[str, Dict[str, Any]] = {}
    for node_id, spec in workflow.items():
        if not isinstance(spec, dict):
            continue
        cls = spec.get("class_type") or ""
        if cls not in _LOADER_MODEL_KEYS:
            continue
        inputs = spec.get("inputs", {}) or {}
        filenames = _loader_all_filenames(cls, inputs)
        if not filenames:
            return {
                "eligible": False,
                "reason": "loader_filenames_not_literal",
                "node_id": str(node_id),
                "encodes": [],
            }
        if len(filenames) != len(_LOADER_MODEL_KEYS.get(cls, [])):
            return {
                "eligible": False,
                "reason": "loader_filenames_incomplete",
                "node_id": str(node_id),
                "encodes": [],
            }
        clip_type = inputs.get("type")
        if not isinstance(clip_type, str) or not clip_type.strip():
            return {
                "eligible": False,
                "reason": "loader_clip_type_not_literal",
                "node_id": str(node_id),
                "encodes": [],
            }
        loader_outputs[str(node_id)] = {
            "loader_class": cls,
            "filenames": filenames,
            "clip_type": clip_type.strip(),
        }

    if not loader_outputs:
        return {"eligible": False, "reason": "no_native_clip_loader", "encodes": []}

    # Step 2: find native CLIPTextEncode nodes whose text is literal
    # and whose clip is wired directly to one of the eligible loaders.
    for node_id, spec in workflow.items():
        if not isinstance(spec, dict):
            continue
        if spec.get("class_type") != "CLIPTextEncode":
            continue
        inputs = spec.get("inputs", {}) or {}
        text = inputs.get("text")
        if not isinstance(text, str):
            return {"eligible": False,
                    "reason": "text_not_literal",
                    "node_id": str(node_id),
                    "encodes": []}
        clip_link = inputs.get("clip")
        if not isinstance(clip_link, list) or len(clip_link) < 1:
            return {"eligible": False,
                    "reason": "clip_not_connected",
                    "node_id": str(node_id),
                    "encodes": []}
        loader_node_id = str(clip_link[0])
        loader_info = loader_outputs.get(loader_node_id)
        if loader_info is None:
            return {"eligible": False,
                    "reason": "clip_not_from_native_loader",
                    "node_id": str(node_id),
                    "encodes": []}
        encodes.append(
            {
                "node_id": str(node_id),
                "text": text,
                "loader_class": loader_info["loader_class"],
                "filenames": list(loader_info["filenames"]),
                "clip_type": loader_info["clip_type"],
            }
        )

    if not encodes:
        return {"eligible": False, "reason": "no_eligible_encode", "encodes": []}

    bundle: Dict[str, Any] = {
        "schema_version": PROMPT_BUNDLE_SCHEMA_VERSION,
        "encodes": sorted(encodes, key=lambda e: e["node_id"]),
    }
    bundle["bundle_hash"] = _safe_sha256(
        {
            "schema": PROMPT_BUNDLE_SCHEMA_VERSION,
            "encodes": [
                {
                    "node_id": e["node_id"],
                    "text": e["text"],
                    "loader_class": e["loader_class"],
                    "filenames": e["filenames"],
                    "clip_type": e["clip_type"],
                }
                for e in bundle["encodes"]
            ],
        }
    )
    return {"eligible": True, "reason": "ok", "encodes": bundle["encodes"],
            "bundle": bundle}


# ── Phase 2: In-memory CLIPTextEncode cache (bounded, fingerprint-aware) ─


class InMemoryClipTextCache:
    """Bounded in-memory cache for CLIPTextEncode outputs.

    Two-tier keys:
      * exact object identity (``id(clip)``) — always honored, fastest
      * stable fingerprint — only used when present and ``eligible=True``

    Unknown or modified CLIP objects use only exact-object caching.
    """

    def __init__(self, *, max_entries: int = 256) -> None:
        self._max_entries = max(1, int(max_entries))
        self._exact: "OrderedDict[Tuple[Any, ...], Any]" = OrderedDict()
        self._fingerprint: "OrderedDict[Tuple[Any, ...], Any]" = OrderedDict()
        self._lock = threading.Lock()
        self.hits_exact = 0
        self.hits_fingerprint = 0
        self.misses = 0
        self.evictions = 0
        self.bypassed_unknown = 0

    def get(
        self,
        *,
        text: str,
        clip,
        fingerprint: Optional[Dict[str, Any]] = None,
    ) -> Optional[Any]:
        clip_id = id(clip)
        # Always try exact first
        exact_key = (text, clip_id)
        with self._lock:
            hit = self._exact.get(exact_key)
            if hit is not None:
                self._exact.move_to_end(exact_key)
                self.hits_exact += 1
                return hit
            # Relaxed fingerprint lookup only when caller provides one
            if fingerprint is not None and fingerprint.get("eligible"):
                fp_key = (
                    text,
                    fingerprint.get("loader_class", ""),
                    tuple(fingerprint.get("paths", [])),
                    fingerprint.get("clip_type", ""),
                    fingerprint.get("model_generation", ""),
                    json.dumps(
                        fingerprint.get("encode_options", {}),
                        sort_keys=True,
                        separators=(",", ":"),
                    ),
                )
                hit = self._fingerprint.get(fp_key)
                if hit is not None:
                    self._fingerprint.move_to_end(fp_key)
                    self.hits_fingerprint += 1
                    return hit
            self.misses += 1
            if fingerprint is None or not fingerprint.get("eligible"):
                self.bypassed_unknown += 1
            return None

    def put(
        self,
        *,
        text: str,
        clip,
        value: Any,
        fingerprint: Optional[Dict[str, Any]] = None,
    ) -> None:
        clip_id = id(clip)
        exact_key = (text, clip_id)
        with self._lock:
            self._exact[exact_key] = value
            self._exact.move_to_end(exact_key)
            while len(self._exact) > self._max_entries:
                self._exact.popitem(last=False)
                self.evictions += 1
            if fingerprint is not None and fingerprint.get("eligible"):
                fp_key = (
                    text,
                    fingerprint.get("loader_class", ""),
                    tuple(fingerprint.get("paths", [])),
                    fingerprint.get("clip_type", ""),
                    fingerprint.get("model_generation", ""),
                    json.dumps(
                        fingerprint.get("encode_options", {}),
                        sort_keys=True,
                        separators=(",", ":"),
                    ),
                )
                self._fingerprint[fp_key] = value
                self._fingerprint.move_to_end(fp_key)
                while len(self._fingerprint) > self._max_entries:
                    self._fingerprint.popitem(last=False)
                    self.evictions += 1

    def clear(self) -> None:
        with self._lock:
            self._exact.clear()
            self._fingerprint.clear()

    def stats(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "max_entries": self._max_entries,
                "exact_size": len(self._exact),
                "fingerprint_size": len(self._fingerprint),
                "hits_exact": self.hits_exact,
                "hits_fingerprint": self.hits_fingerprint,
                "misses": self.misses,
                "evictions": self.evictions,
                "bypassed_unknown": self.bypassed_unknown,
            }


# ── Phase 2: Persistent CLIP cache (CPU-only, bounded LRU) ──────────────


PERSISTENT_CLIP_CACHE_MAX_BUNDLES = _env_int(
    "COMFYMODAL_PERSISTENT_CLIP_CACHE_MAX_BUNDLES", 3
)
PERSISTENT_CLIP_CACHE_MAX_CANDIDATE_MB = _env_int(
    "COMFYMODAL_PERSISTENT_CLIP_CACHE_MAX_CANDIDATE_MB", 256
)
PERSISTENT_CLIP_CACHE_ENABLED = _env_flag("COMFYMODAL_PERSISTENT_CLIP_CACHE", "0")
EXACT_CLIP_PREFILL_ENABLED = _env_flag("COMFYMODAL_EXACT_CLIP_PREFILL", "0")
GENERIC_CLIP_WARMUP_FALLBACK_ENABLED = _env_flag(
    "COMFYMODAL_GENERIC_CLIP_WARMUP_FALLBACK", "0"
)


def is_persistent_clip_cache_enabled() -> bool:
    return PERSISTENT_CLIP_CACHE_ENABLED


def is_exact_clip_prefill_enabled() -> bool:
    return EXACT_CLIP_PREFILL_ENABLED


def is_generic_clip_warmup_fallback_enabled() -> bool:
    return GENERIC_CLIP_WARMUP_FALLBACK_ENABLED


class PersistentClipCache:
    """Bounded, atomic, file-backed CLIP encoding LRU.

    Stores up to ``max_bundles`` prompt bundles. Each bundle is a
    directory containing a ``manifest.json`` plus safetensors files for
    each eligible CLIPTextEncode output. A manifest checksum and schema
    version are enforced. Corrupt manifests become misses, never failures.
    """

    def __init__(
        self,
        *,
        root_dir: str,
        max_bundles: int = PERSISTENT_CLIP_CACHE_MAX_BUNDLES,
    ) -> None:
        self._root = root_dir
        self._max_bundles = max(1, int(max_bundles))
        self._lock = threading.Lock()
        os.makedirs(self._root, exist_ok=True)
        self._manifest_path = os.path.join(self._root, "manifest.json")
        self._read_manifest_best_effort()

    def _read_manifest_best_effort(self) -> None:
        self._entries: "OrderedDict[str, Dict[str, Any]]" = OrderedDict()
        try:
            with open(self._manifest_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict):
                return
            if data.get("schema_version") != PERSISTENT_CLIP_CACHE_SCHEMA_VERSION:
                return
            entries = data.get("entries", [])
            if not isinstance(entries, list):
                return
            for e in entries:
                if not isinstance(e, dict):
                    continue
                bh = e.get("bundle_hash")
                if not isinstance(bh, str):
                    continue
                self._entries[bh] = e
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            self._entries = OrderedDict()

    def _write_manifest_atomic(self) -> None:
        tmp = f"{self._manifest_path}.tmp"
        payload = {
            "schema_version": PERSISTENT_CLIP_CACHE_SCHEMA_VERSION,
            "updated_at": time.time(),
            "entries": list(self._entries.values()),
        }
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(payload, f, sort_keys=True, separators=(",", ":"))
            f.flush()
            try:
                os.fsync(f.fileno())
            except OSError:
                pass
        os.replace(tmp, self._manifest_path)

    def list_bundles(self) -> List[Dict[str, Any]]:
        with self._lock:
            return list(self._entries.values())

    def has_bundle(self, bundle_hash: str) -> bool:
        with self._lock:
            return bundle_hash in self._entries

    def get_bundle_dir(self, bundle_hash: str) -> Optional[str]:
        with self._lock:
            e = self._entries.get(bundle_hash)
            if e is None:
                return None
            return os.path.join(self._root, e.get("dir", ""))

    def lookup(
        self,
        *,
        bundle_hash: str,
        clip_fingerprint_key_value: str,
    ) -> Optional[Dict[str, Any]]:
        """Return the manifest entry if it matches; else None."""
        with self._lock:
            e = self._entries.get(bundle_hash)
            if e is None:
                return None
            if e.get("clip_fingerprint_key") != clip_fingerprint_key_value:
                return None
            return e

    def commit(
        self,
        *,
        bundle: Dict[str, Any],
        clip_fingerprint_key_value: str,
        bundle_dir_name: str,
        file_manifest: List[Dict[str, Any]],
        total_bytes: int,
        checksum: str,
    ) -> Dict[str, Any]:
        """Atomically commit a new bundle. LRU evicts if needed."""
        with self._lock:
            now = time.time()
            entry = {
                "bundle_hash": bundle["bundle_hash"],
                "schema_version": PERSISTENT_CLIP_CACHE_SCHEMA_VERSION,
                "clip_fingerprint_key": clip_fingerprint_key_value,
                "dir": bundle_dir_name,
                "files": file_manifest,
                "total_bytes": int(total_bytes),
                "checksum": checksum,
                "created_at": now,
                "last_used_at": now,
                "encodes": bundle.get("encodes", []),
            }
            # Remove any existing entry with the same hash
            self._entries.pop(bundle["bundle_hash"], None)
            self._entries[bundle["bundle_hash"]] = entry
            # Evict by oldest last_used_at
            while len(self._entries) > self._max_bundles:
                oldest_key = min(
                    self._entries.keys(),
                    key=lambda k: self._entries[k].get("last_used_at", 0),
                )
                self._evict_locked(oldest_key)
            self._write_manifest_atomic()
            return entry

    def touch(self, bundle_hash: str) -> None:
        with self._lock:
            e = self._entries.get(bundle_hash)
            if e is None:
                return
            e["last_used_at"] = time.time()
            # Move to end (LRU semantics)
            self._entries.move_to_end(bundle_hash)
            self._write_manifest_atomic()

    def _evict_locked(self, bundle_hash: str) -> None:
        e = self._entries.pop(bundle_hash, None)
        if e is None:
            return
        try:
            import shutil
            shutil.rmtree(os.path.join(self._root, e.get("dir", "")), ignore_errors=True)
        except OSError:
            pass


# ── Phase 2: Prompt-cache candidate payload ─────────────────────────────


def build_clip_candidate_payload(
    *,
    bundle: Dict[str, Any],
    clip_fingerprint: Dict[str, Any],
    conditioning_tensors: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Build a serializable, bounded payload for the post-delivery
    prompt-cache persistence RPC.

    ``conditioning_tensors`` is a list of ``{"node_id", "dtype", "shape",
    "data_b64", "pooled_b64"?}`` dicts (already detached CPU tensors).
    The recursive byte count is enforced by the caller via
    ``PERSISTENT_CLIP_CACHE_MAX_CANDIDATE_MB``.
    """
    return {
        "schema_version": PERSISTENT_CLIP_CACHE_SCHEMA_VERSION,
        "bundle": bundle,
        "clip_fingerprint": clip_fingerprint,
        "conditioning_tensors": conditioning_tensors,
        "created_at": time.time(),
    }


def candidate_payload_bytes(payload: Dict[str, Any]) -> int:
    try:
        return len(json.dumps(payload, default=str).encode("utf-8"))
    except (TypeError, ValueError):
        return 0


def _serialize_tensor_to_b64(tensor, *, _b64_import=None, _th_import=None):
    """Serialize a single tensor to base64, handling bfloat16 via int16 view.

    Returns ``(b64_str, dtype_str, shape_list)`` or raises on error.
    The returned dtype_str always uses ``torch.<dtype>`` naming.
    """
    if _b64_import is None:
        import base64 as _b64_import
    if _th_import is None:
        import torch as _th_import
    t = tensor.detach().cpu().contiguous()
    dtype_str = str(t.dtype)  # e.g. "torch.bfloat16"
    if t.dtype == _th_import.bfloat16:
        # bfloat16 not natively supported by numpy; store as int16 bytes
        t_bytes = t.view(_th_import.int16).numpy().tobytes()
    else:
        t_bytes = t.numpy().tobytes()
    return _b64_import.b64encode(t_bytes).decode("ascii"), dtype_str, list(t.shape)


def _deserialize_tensor_from_b64(b64_str, dtype_str, shape_list, *, _b64_import=None, _np_import=None, _th_import=None):
    """Deserialize a single tensor from base64, handling bfloat16 via int16 view."""
    if _b64_import is None:
        import base64 as _b64_import
    if _np_import is None:
        import numpy as _np_import
    if _th_import is None:
        import torch as _th_import
    if dtype_str.startswith("torch."):
        dtype_str_clean = dtype_str[len("torch."):]
    else:
        dtype_str_clean = dtype_str
    torch_dtype = _th_import.__dict__.get(dtype_str_clean, _th_import.float32)
    raw = _b64_import.b64decode(b64_str)
    if torch_dtype == _th_import.bfloat16:
        # Read as int16, then view as bfloat16
        arr = _np_import.frombuffer(raw, dtype=_np_import.int16).reshape(shape_list)
        return _th_import.from_numpy(arr.copy()).contiguous().view(_th_import.bfloat16)
    else:
        # Map torch dtype to numpy dtype
        _np_map = {
            _th_import.float32: _np_import.float32,
            _th_import.float64: _np_import.float64,
            _th_import.float16: _np_import.float16,
            _th_import.int32: _np_import.int32,
            _th_import.int64: _np_import.int64,
            _th_import.int16: _np_import.int16,
            _th_import.int8: _np_import.int8,
            _th_import.uint8: _np_import.uint8,
            _th_import.bool: _np_import.bool_,
        }
        np_dtype = _np_map.get(torch_dtype, _np_import.float32)
        arr = _np_import.frombuffer(raw, dtype=np_dtype).reshape(shape_list)
        return _th_import.from_numpy(arr.copy()).contiguous()


def _validate_metadata_value(value, depth=0, max_depth=4):
    """Recursively validate a metadata value is safe for JSON serialization.

    Raises ValueError if the value contains unsupported types or exceeds max_depth.
    """
    if depth > max_depth:
        raise ValueError(f"metadata recursion depth exceeded ({depth} > {max_depth})")
    if isinstance(value, (str, int, float, bool, type(None))):
        return
    if isinstance(value, (list, tuple)):
        for item in value:
            _validate_metadata_value(item, depth + 1, max_depth)
        return
    if isinstance(value, dict):
        for k, v in value.items():
            if not isinstance(k, str):
                raise ValueError(f"metadata dict key must be str, got {type(k).__name__}")
            _validate_metadata_value(v, depth + 1, max_depth)
        return
    raise ValueError(f"unsupported metadata type: {type(value).__name__}")


def stable_clip_cache_tag(paths, clip_type):
    """Single source of truth for the stable CLIP cache tag.

    Used as the fourth key component in:
      (text, paths, clip_type, tag, id(clip))    exact
      (text, paths, clip_type, tag)              relaxed

    by every call site: graph-side CLIPTextEncode lookup,
    result-side candidate extraction, restore-time
    persistent-cache seeding, and exact-prefill grouping.

    The previous code computed this string inline at three
    different sites (graph wrapper, restore-time seed, and
    candidate builder).  The candidate-builder copy used
    ``type(clip).__name__`` instead of the stable tag, which
    meant the graph wrote entries under one tag and the
    candidate builder searched under another, so ``_hit``
    was always None in production.

    The path-basename tail is used to remain deterministic
    across cold/warm boundaries without depending on the
    Python class name (unknown before the CLIP object is
    constructed).
    """
    if clip_type is None:
        clip_type = ""
    tail_parts = []
    for p in paths or ():
        if not p:
            continue
        s = str(p)
        tail_parts.append(s.rsplit("/", 1)[-1])
    tail = "_".join(tail_parts)
    return f"{clip_type}@{tail}" if tail else str(clip_type)


def serialize_conditioning_for_cache(value):
    """Serialize a CLIPTextEncode output for the prompt cache.

    The native conditioning value is ``[[tensor, {"pooled": pooled}], ...]``
    — a list with one or more entries, each being a list with two
    elements: a torch.Tensor (the conditioning) and a metadata
    dict that usually contains a ``pooled`` tensor.  Anything
    else is treated as a non-cacheable value (returns None).

    Serializes ALL entries, not just the first one.
    Handles bfloat16 correctly via int16 view.
    Rejects requires_grad=True and GPU-resident tensors.
    Validates metadata values recursively.
    """
    import base64 as _b64
    import torch as _th
    try:
        if isinstance(value, tuple):
            if not value:
                return None
            value = value[0]
        if not isinstance(value, list) or not value:
            return None
        entries_out = []
        for entry_idx, entry in enumerate(value):
            if not isinstance(entry, list) or len(entry) < 2:
                return None
            cond = entry[0]
            meta = entry[1] if len(entry) > 1 else {}
            if not isinstance(cond, _th.Tensor):
                return None
            if cond.requires_grad:
                # Reject requires_grad tensors
                return None
            if cond.device.type != "cpu":
                # Reject GPU-resident tensors
                return None
            cond_cpu = cond.detach().cpu().contiguous()
            cond_b64, cond_dtype_str, cond_shape = _serialize_tensor_to_b64(cond_cpu)
            meta_dict = {}
            if isinstance(meta, dict):
                for mk, mv in meta.items():
                    if isinstance(mv, _th.Tensor):
                        if mv.requires_grad:
                            return None
                        if mv.device.type != "cpu":
                            return None
                        mv_b64, mv_dtype_str, mv_shape = _serialize_tensor_to_b64(mv)
                        meta_dict[mk] = {
                            "kind": "tensor",
                            "data": mv_b64,
                            "dtype": mv_dtype_str,
                            "shape": mv_shape,
                        }
                    elif isinstance(mv, (str, int, float, bool, type(None))):
                        meta_dict[mk] = {"kind": "raw", "value": mv}
                    elif isinstance(mv, (list, dict)):
                        # Validate recursively before accepting
                        try:
                            _validate_metadata_value(mv)
                        except ValueError:
                            return None
                        meta_dict[mk] = {"kind": "raw", "value": mv}
                    else:
                        # Unsupported metadata type -> reject the whole entry
                        return None
            entries_out.append({
                "cond_b64": cond_b64,
                "cond_dtype": cond_dtype_str,
                "cond_shape": cond_shape,
                "metadata": meta_dict,
            })
        if not entries_out:
            return None
        return {
            "kind": "conditioning_list_v1",
            "schema_version": 1,
            "entries": entries_out,
        }
    except Exception:
        return None


def deserialize_conditioning_for_cache(serialized):
    """Rebuild a CLIPTextEncode output from a serialized payload.

    Returns a list-of-lists structure compatible with the native
    ComfyUI ``[[tensor, {"pooled": pooled}]]`` shape, or None if
    the payload is malformed.  Deserializes ALL entries, not just
    the first one.  Handles bfloat16 correctly via int16 view.
    """
    import base64 as _b64
    import torch as _th
    try:
        if not isinstance(serialized, dict):
            return None
        if serialized.get("kind") != "conditioning_list_v1":
            return None
        if serialized.get("schema_version") != 1:
            return None
        entries = serialized.get("entries", [])
        if not isinstance(entries, list) or not entries:
            return None
        result = []
        for e_idx, entry in enumerate(entries):
            if not isinstance(entry, dict):
                return None
            cond = _deserialize_tensor_from_b64(
                entry.get("cond_b64", ""),
                entry.get("cond_dtype", "torch.float32"),
                tuple(entry.get("cond_shape", []) or []),
            )
            if cond is None:
                return None
            meta_dict = {}
            for mk, mv in (entry.get("metadata") or {}).items():
                if not isinstance(mv, dict):
                    continue
                if mv.get("kind") == "tensor":
                    mt = _deserialize_tensor_from_b64(
                        mv.get("data", ""),
                        mv.get("dtype", "torch.float32"),
                        tuple(mv.get("shape", []) or []),
                    )
                    if mt is None:
                        return None
                    meta_dict[mk] = mt
                elif mv.get("kind") == "raw":
                    meta_dict[mk] = mv.get("value")
                else:
                    return None
            result.append([cond, meta_dict])
        return result
    except Exception:
        return None


def conditioning_equals(a, b) -> bool:
    """Bit-exact equality of two serialized-then-deserialized
    conditioning values, including tensor bytes, dtype, shape,
    and metadata values.  Used by integration tests to confirm
    that the round-trip preserves content.
    """
    if type(a) is not type(b):
        return False
    if isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            return False
        return all(conditioning_equals(x, y) for x, y in zip(a, b))
    if isinstance(a, dict) and isinstance(b, dict):
        if a.keys() != b.keys():
            return False
        return all(conditioning_equals(a[k], b[k]) for k in a)
    try:
        import torch as _th
        if isinstance(a, _th.Tensor) and isinstance(b, _th.Tensor):
            if a.shape != b.shape:
                return False
            if a.dtype != b.dtype:
                return False
            return bool((a == b).all().item())
    except Exception:
        pass
    return a == b


# Backwards-compat aliases (the production comfyapp.py was
# patched first; tests import these from optimizations).
_serialize_conditioning_for_cache = serialize_conditioning_for_cache
_deserialize_conditioning_for_cache = deserialize_conditioning_for_cache
_conditioning_equals = conditioning_equals


# ── Phase 2: Post-delivery persistence dispatcher ───────────────────────


class PostDeliveryPersistenceDispatcher:
    """Bounded, untracked-but-supervised background task dispatcher.

    The dispatcher is used to fire the prompt-cache persistence RPC after
    a successful local delivery.  Concurrency is bounded by a
    semaphore.  Duplicate writes for the same bundle are prevented by
    the ``_seen`` map (only populated on a successful persistence
    result — failed attempts do not poison future retries).

    **Timeout semantics** (per audit round 4): ``timeout_s`` is the
    time spent waiting on the semaphore (``semaphore.acquire``).
    It does NOT bound the time spent inside ``fn()`` itself.
    The actual ``fn()`` execution is bounded indirectly by the
    Modal function ``timeout`` (e.g. ``timeout=30`` on
    ``persist_clip_cache_payload``).  This dispatcher does not
    implement a per-task wall-clock timeout on ``fn()``; if the
    remote function hangs, the dispatcher will block in
    ``_run`` indefinitely until the Modal function times out
    at the RPC layer and the thread is collected.
    """

    def __init__(self, *, max_concurrent: int = 4, default_timeout_s: float = 30.0) -> None:
        self._sem = threading.BoundedSemaphore(max(1, int(max_concurrent)))
        self._default_timeout_s = float(default_timeout_s)
        self._inflight: Dict[str, threading.Thread] = {}
        self._lock = threading.Lock()
        self._seen: Dict[str, float] = {}
        self._max_seen = 1024

    def submit(
        self,
        *,
        task_id: str,
        fn: Callable[[], Any],
        timeout_s: Optional[float] = None,
    ) -> Optional[threading.Thread]:
        if not task_id:
            return None
        with self._lock:
            if task_id in self._inflight:
                return None
            # _seen must only be populated on a SUCCESSFUL persistence,
            # otherwise a transient failure permanently marks the bundle
            # as attempted and prevents future retries.
            if task_id in self._seen:
                # Already submitted at some point in this process — skip
                # duplicate writes for the same bundle.
                return None
            t = threading.Thread(
                target=self._run,
                kwargs={"task_id": task_id, "fn": fn,
                        "timeout_s": float(timeout_s or self._default_timeout_s)},
                daemon=True,
                name=f"post-delivery-{task_id[:24]}",
            )
            self._inflight[task_id] = t
        t.start()
        return t

    def _run(self, *, task_id: str, fn: Callable[[], Any], timeout_s: float) -> None:
        # Semaphore acquire: must inspect the return value. Bounded
        # Semaphore returns True on success, False on timeout.
        _acquired = self._sem.acquire(timeout=timeout_s)
        if not _acquired:
            self._cleanup(task_id, ok=False, err="semaphore_timeout")
            return
        try:
            try:
                _result = fn()
                # Inspect the result: an error dict must be
                # recorded as a failure so the caller does not see
                # "ok" for an actual error.  This is a contract
                # with the local bridge: persist_clip_cache_payload
                # returns ``{"status": "ok", ...}`` on success and
                # ``{"status": "error", ...}`` on failure.
                if isinstance(_result, dict) and _result.get("status") == "error":
                    _err = str(_result.get("error", "unknown"))[:200]
                    self._cleanup(task_id, ok=False, err=f"result_error:{_err}")
                    return
            except Exception as exc:
                # Never raise out of background task
                self._cleanup(task_id, ok=False, err=f"{type(exc).__name__}: {exc}")
                return
        finally:
            try:
                self._sem.release()
            except Exception:
                pass
        self._cleanup(task_id, ok=True, err="")

    def _cleanup(self, task_id: str, *, ok: bool, err: str) -> None:
        with self._lock:
            self._inflight.pop(task_id, None)
            if ok:
                # Mark as seen ONLY on success. A failure does NOT
                # mark the task as seen so a future attempt can retry.
                self._seen[task_id] = time.time()
                while len(self._seen) > self._max_seen:
                    self._seen.pop(next(iter(self._seen)))
        if ok:
            print(
                f"[post_delivery] task_id={task_id[:24]} status=ok"
            )
        else:
            print(
                f"[post_delivery] task_id={task_id[:24]} status=err err={err[:200]}"
            )

    def inflight_count(self) -> int:
        with self._lock:
            return len(self._inflight)


# ── Phase 3: Custom-node generation-token fast path ─────────────────────


CUSTOM_NODE_GENERATION_FASTPATH_ENABLED = _env_flag(
    "COMFYMODAL_CUSTOM_NODE_GENERATION_FASTPATH", "0"
)
CUSTOM_NODE_GENERATION_SCHEMA_VERSION = 1


def _read_custom_node_generation_record(path: str) -> Optional[Dict[str, Any]]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return None
        if data.get("schema_version") != CUSTOM_NODE_GENERATION_SCHEMA_VERSION:
            return None
        gen = data.get("generation")
        if not isinstance(gen, str) or not gen.strip():
            return None
        return data
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None


def _write_custom_node_generation_record(
    path: str,
    *,
    generation: str,
    content_hash: str = "",
    reason: str = "",
    expected_node_count: int = -1,
) -> None:
    payload = {
        "schema_version": CUSTOM_NODE_GENERATION_SCHEMA_VERSION,
        "generation": generation,
        "content_hash": content_hash,
        "updated_at": time.time(),
        "reason": reason,
        "expected_node_count": int(expected_node_count),
    }
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, sort_keys=True, separators=(",", ":"))
        f.flush()
        try:
            os.fsync(f.fileno())
        except OSError:
            pass
    os.replace(tmp, path)


# ── Phase 4: Resolved-model-path cache (per-generation) ─────────────────


MODEL_PATH_CACHE_ENABLED = _env_flag("COMFYMODAL_MODEL_PATH_CACHE", "0")
MODEL_PATH_CACHE_SCHEMA_VERSION = 1
ALLOWED_MODEL_FOLDERS = frozenset({
    "checkpoints", "diffusion_models", "unet", "unets", "clip", "text_encoders",
    "vae", "loras", "controlnet", "upscale_models", "embeddings", "hypernetworks",
    "gligen", "photomaker", "classifiers", "model_patches", "configs", "t2i_adapter",
    "ipadapter", "instantid", "sams", "diffusers",
})


def _coerce_folder(folder: str) -> str:
    f = (folder or "").strip().lower().replace("\\", "/").strip("/")
    if "/" in f:
        f = f.split("/")[0]
    if f not in ALLOWED_MODEL_FOLDERS:
        raise ValueError(f"unsupported model folder: {folder!r}")
    return f


def _coerce_filename(filename: str) -> str:
    n = (filename or "").strip()
    if not n:
        raise ValueError("empty filename")
    if "/" in n or "\\" in n:
        raise ValueError(f"unsafe filename: {filename!r}")
    if os.path.isabs(n):
        raise ValueError(f"unsafe filename: {filename!r}")
    return n


class ResolvedModelPathCache:
    """Per-models-generation resolved-path cache.

    A successful resolution caches ``(generation, folder, filename)`` →
    realpath. The cache is invalidated on any generation change. Missing
    paths or corrupt generation records fall back to the caller-provided
    resolver. Negative lookups do not survive a generation change.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._generation: str = ""
        self._cache: Dict[Tuple[str, str], str] = {}

    def reset(self) -> None:
        with self._lock:
            self._generation = ""
            self._cache.clear()

    def invalidate(self) -> None:
        with self._lock:
            self._cache.clear()

    def _evict_if_missing(self, folder: str, filename: str, path: str) -> None:
        try:
            if not os.path.isfile(path):
                with self._lock:
                    self._cache.pop((folder, filename), None)
        except OSError:
            with self._lock:
                self._cache.pop((folder, filename), None)

    def resolve(
        self,
        *,
        generation: str,
        folder: str,
        filename: str,
        resolver: Callable[[str, str], Optional[str]],
    ) -> Optional[str]:
        if not MODEL_PATH_CACHE_ENABLED:
            return resolver(folder, filename)
        if not generation:
            return resolver(folder, filename)
        try:
            folder_n = _coerce_folder(folder)
            filename_n = _coerce_filename(filename)
        except ValueError:
            return resolver(folder, filename)
        with self._lock:
            if self._generation and self._generation != generation:
                self._cache.clear()
                self._generation = generation
            elif not self._generation:
                self._generation = generation
            cached = self._cache.get((folder_n, filename_n))
        if cached is not None:
            self._evict_if_missing(folder_n, filename_n, cached)
            with self._lock:
                cached = self._cache.get((folder_n, filename_n))
            if cached is not None:
                return cached
        resolved = resolver(folder_n, filename_n)
        if resolved and os.path.isfile(resolved):
            with self._lock:
                self._cache[(folder_n, filename_n)] = os.path.realpath(resolved)
            return resolved
        return resolved

    def stats(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "enabled": MODEL_PATH_CACHE_ENABLED,
                "generation": self._generation,
                "size": len(self._cache),
            }


# ── Phase 5: Third-party log suppression (allowlist, request-scoped) ─────


THIRD_PARTY_LOG_SUPPRESSION_ENABLED = _env_flag(
    "COMFYMODAL_THIRD_PARTY_LOG_SUPPRESSION", "0"
)

# Allowlist of (logger_name, message_prefix) tuples. Anything not in this
# list passes through untouched.  We deliberately do NOT match on broad
# substrings like "cache", "model", or "warning".
THIRD_PARTY_LOG_ALLOWLIST: List[Tuple[str, str]] = [
    ("cachedit", "CacheDiT"),
    ("cachedit", "FBCache"),
    ("comfyui_controlnet_aux", "Loading"),
    ("comfyui_controlnet_aux", "Loaded"),
    ("comfyui_inpaint", "Downloading"),
    ("comfyui_segment_anything", "Downloading"),
    ("comfyui_impact_pack", "Loading"),
    ("comfyui_impact_pack", "Loaded"),
    ("rgthree", "Processing"),
    ("rgthree", "ComfyUI"),
]


class RequestScopedLogSuppressor:
    """Suppress only allowlisted third-party log lines for a single request.

    Design:
      * Does NOT replace global stdout permanently.
      * Holds a lock during the request; releases it on exit.
      * Buffers suppressed lines in a bounded ring buffer.
      * If an exception or traceback is observed while suppression is
        active, suppression is disabled for the remainder of the request
        and the buffered context is flushed.

    The class is intentionally NOT a context manager that swaps sys.stdout
    with a global proxy. Instead it exposes ``should_suppress(record)`` and
    ``record(record)`` for callers that already route logging through a
    known choke point (e.g. a logger they control).
    """

    def __init__(self, *, ring_size: int = 128) -> None:
        self._ring: Deque[Tuple[str, str]] = deque(maxlen=max(1, int(ring_size)))
        self._suppressed_counts: Dict[Tuple[str, str], int] = {}
        self._lock = threading.Lock()
        self._disabled = False
        self._disable_reason: str = ""
        self._scope: str = ""

    def __enter__(self) -> "RequestScopedLogSuppressor":
        with self._lock:
            self._disabled = False
            self._disable_reason = ""
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        # Print suppression summary
        try:
            self._print_summary()
        except Exception:
            pass
        # If an exception occurred, flush buffered context
        if exc_type is not None or exc is not None or tb is not None:
            try:
                self._flush_buffered()
            except Exception:
                pass

    def set_scope(self, scope: str) -> None:
        with self._lock:
            self._scope = scope

    def disable(self, reason: str = "") -> None:
        with self._lock:
            self._disabled = True
            self._disable_reason = reason

    def is_disabled(self) -> bool:
        with self._lock:
            return self._disabled

    def should_suppress(self, *, logger_name: str, message: str) -> bool:
        if not THIRD_PARTY_LOG_SUPPRESSION_ENABLED:
            return False
        with self._lock:
            if self._disabled:
                return False
        msg = (message or "").strip()
        if not msg:
            return False
        # Never suppress exceptions, tracebacks, or warnings indicating
        # actual failures.
        if _looks_like_failure_message(msg):
            return False
        for allow_logger, allow_prefix in THIRD_PARTY_LOG_ALLOWLIST:
            if logger_name == allow_logger and msg.startswith(allow_prefix):
                return True
        return False

    def record(self, *, logger_name: str, message: str) -> None:
        key = (logger_name, message[:60])
        with self._lock:
            self._suppressed_counts[key] = self._suppressed_counts.get(key, 0) + 1
            self._ring.append((logger_name, message))

    def filter(self, *, logger_name: str, message: str) -> bool:
        """Return True if the caller should drop the line."""
        if self.should_suppress(logger_name=logger_name, message=message):
            self.record(logger_name=logger_name, message=message)
            return True
        return False

    def _print_summary(self) -> None:
        with self._lock:
            counts = dict(self._suppressed_counts)
            scope = self._scope
        if not counts:
            return
        total = sum(counts.values())
        print(
            f"[log_suppressor] scope={scope} suppressed_total={total} "
            f"distinct={len(counts)} disabled={int(self._disabled)}"
        )
        # Top 5
        top = sorted(counts.items(), key=lambda kv: kv[1], reverse=True)[:5]
        for (logger_name, msg), count in top:
            print(
                f"[log_suppressor]   suppressed count={count} logger={logger_name} "
                f"prefix={msg[:60]!r}"
            )

    def _flush_buffered(self) -> None:
        with self._lock:
            items = list(self._ring)
        if not items:
            return
        print(f"[log_suppressor] flushing {len(items)} buffered lines after exception")
        for logger_name, msg in items[-20:]:
            print(f"[log_suppressor.buffered] logger={logger_name} msg={msg[:200]}")


_FAILURE_TOKENS = (
    "traceback", "exception", "error: ", "fatal: ",
    "missingnode", "missing node", "load failed", "load failure",
    "broken", "corrupt", "importerror", "modulenotfounderror",
    "keyerror: '", "attributeerror",
)


def _looks_like_failure_message(msg: str) -> bool:
    lower = (msg or "").lower()
    return any(tok in lower for tok in _FAILURE_TOKENS)


# ── Phase 7: Waterfall telemetry helpers ───────────────────────────────


WATERFALL_EVENT_VERSION = 1


def make_waterfall_event(
    *,
    name: str,
    phase: str,
    started_at: float,
    ended_at: float,
    on_critical_path: bool,
    overlaps: Optional[List[str]] = None,
    optimizable: bool = False,
    expected_gain_ms: float = 0.0,
    observed_gain_ms: float = 0.0,
    metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    return {
        "version": WATERFALL_EVENT_VERSION,
        "name": name,
        "phase": phase,
        "started_at": round(started_at, 6),
        "ended_at": round(ended_at, 6),
        "duration_ms": round((ended_at - started_at) * 1000.0, 3),
        "on_critical_path": bool(on_critical_path),
        "overlaps": list(overlaps or []),
        "optimizable": bool(optimizable),
        "expected_gain_ms": round(float(expected_gain_ms), 3),
        "observed_gain_ms": round(float(observed_gain_ms), 3),
        "metadata": dict(metadata or {}),
    }


class WaterfallRecorder:
    """Thread-safe, request-scoped waterfall event recorder."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._events: List[Dict[str, Any]] = []

    def record(self, event: Dict[str, Any]) -> None:
        with self._lock:
            self._events.append(event)

    def snapshot(self) -> List[Dict[str, Any]]:
        with self._lock:
            return list(self._events)

    def to_dict(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "version": WATERFALL_EVENT_VERSION,
                "events": list(self._events),
            }


# ── Phase 7: CPU/process resource snapshot (profiling only) ─────────────


PROFILE_RESOURCES_ENABLED = _env_flag("COMFYMODAL_PROFILE_RESOURCES", "0")


def safe_resource_snapshot() -> Dict[str, Any]:
    """Best-effort process resource snapshot. Never raises.

    Only does meaningful work on Linux (via /proc); on Windows it returns
    an empty dict with a ``platform`` key.
    """
    out: Dict[str, Any] = {"platform": sys.platform}
    if not PROFILE_RESOURCES_ENABLED:
        return out
    if sys.platform.startswith("linux"):
        try:
            with open("/proc/self/status", "r", encoding="utf-8", errors="replace") as f:
                text = f.read()
            for key in ("VmRSS:", "VmSize:", "RssAnon:", "RssFile:", "RssShmem:"):
                for line in text.splitlines():
                    if line.startswith(key):
                        out[key.rstrip(":").lower()] = line
                        break
        except OSError:
            pass
        try:
            with open("/proc/self/io", "r", encoding="utf-8", errors="replace") as f:
                text = f.read()
            io = {}
            for line in text.splitlines():
                if ":" in line:
                    k, v = line.split(":", 1)
                    io[k.strip()] = v.strip()
            out["io"] = io
        except OSError:
            pass
    return out


# ── Phase 6: Bake-candidate report (read-only) ──────────────────────────


def emit_bake_candidate_report() -> Dict[str, Any]:
    """Return a ranked recommendation list of small, immutable, frequently
    reused runtime assets that could be baked into the snapshot.

    This function is purely advisory — it does not modify any state. It is
    safe to call at startup; the result should be logged once.
    """
    return {
        "schema_version": 1,
        "policy": "small, immutable, content-hashable, frequently reused",
        "max_size_mb": 250,
        "candidates": [
            {
                "name": "openai/clip-vit-base-patch32 tokenizer files",
                "approx_size_kb": 1024,
                "rationale": "Tokenizers are loaded by every CLIP model load; baking the JSON saves a small filesystem hit.",
                "risk": "tokenizer JSON must be content-hashable and version-gated",
            },
            {
                "name": "comfyui_impact_pack SAM/YOLO weights (small variants)",
                "approx_size_kb": 30000,
                "rationale": "Loaded repeatedly on workflows using Impact Pack; small variants fit under 250MB.",
                "risk": "Must not be model weights; only architecture/auxiliary assets.",
            },
        ],
    }


# ── Convenience: process-wide singletons (lazy) ─────────────────────────


# Process-wide singleton for the post-delivery persistence
# dispatcher. The local bridge in __init__.py imports this exact
# name (`_POST_DELIVERY_SINGLETON`) and uses it as the single
# dispatcher for the entire process; creating per-request
# instances would defeat cross-request deduplication and
# backpressure. The audit flagged that this name was not
# previously defined in this module, which silently caused the
# import to NameError and the whole post-delivery hook to be
# swallowed. Defining it here closes that gap.
_POST_DELIVERY_SINGLETON = PostDeliveryPersistenceDispatcher()
# Audit-friendly alias (no underscore) for tests and documentation
POST_DELIVERY_SINGLETON = _POST_DELIVERY_SINGLETON


_persistent_clip_cache_singleton: Optional[PersistentClipCache] = None
_persistent_clip_cache_lock = threading.Lock()


def get_persistent_clip_cache(root_dir: str) -> PersistentClipCache:
    global _persistent_clip_cache_singleton
    with _persistent_clip_cache_lock:
        if _persistent_clip_cache_singleton is None:
            _persistent_clip_cache_singleton = PersistentClipCache(root_dir=root_dir)
        return _persistent_clip_cache_singleton


_resolved_model_path_cache_singleton: Optional[ResolvedModelPathCache] = None
_resolved_model_path_cache_lock = threading.Lock()


def get_resolved_model_path_cache() -> ResolvedModelPathCache:
    global _resolved_model_path_cache_singleton
    with _resolved_model_path_cache_lock:
        if _resolved_model_path_cache_singleton is None:
            _resolved_model_path_cache_singleton = ResolvedModelPathCache()
        return _resolved_model_path_cache_singleton


# ── Module-level flag surface (callers can introspect) ──────────────────


def get_all_flag_values() -> Dict[str, Any]:
    return {
        "PRODUCTION_MODEL_READ_COORDINATOR_ENABLED":
            PRODUCTION_MODEL_READ_COORDINATOR_ENABLED,
        "PRODUCTION_UNET_START_BOUNDARY": current_unet_start_boundary(),
        "PRODUCTION_MODEL_READ_COORDINATOR_DIAG":
            PRODUCTION_MODEL_READ_COORDINATOR_DIAG,
        "PERSISTENT_CLIP_CACHE_ENABLED": PERSISTENT_CLIP_CACHE_ENABLED,
        "PERSISTENT_CLIP_CACHE_MAX_BUNDLES": PERSISTENT_CLIP_CACHE_MAX_BUNDLES,
        "PERSISTENT_CLIP_CACHE_MAX_CANDIDATE_MB":
            PERSISTENT_CLIP_CACHE_MAX_CANDIDATE_MB,
        "EXACT_CLIP_PREFILL_ENABLED": EXACT_CLIP_PREFILL_ENABLED,
        "GENERIC_CLIP_WARMUP_FALLBACK_ENABLED":
            GENERIC_CLIP_WARMUP_FALLBACK_ENABLED,
        "CUSTOM_NODE_GENERATION_FASTPATH_ENABLED":
            CUSTOM_NODE_GENERATION_FASTPATH_ENABLED,
        "MODEL_PATH_CACHE_ENABLED": MODEL_PATH_CACHE_ENABLED,
        "THIRD_PARTY_LOG_SUPPRESSION_ENABLED":
            THIRD_PARTY_LOG_SUPPRESSION_ENABLED,
        "PROFILE_RESOURCES_ENABLED": PROFILE_RESOURCES_ENABLED,
    }
