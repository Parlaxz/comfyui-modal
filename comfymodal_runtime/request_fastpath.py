"""Request-scoped fast-path loader context for R44B (``FastPathRequestContext``).

This module makes the FastSafe loader lane a *first-class, request-scoped*
capability instead of one that only engaged through historical side
channels: the Golden execution context, ``RestorePreparation`` wiring, or
snapshot-captured manifests.  A request that wants fast-path loaders simply
opens a :class:`FastPathRequestContext` via :func:`begin` around its worker
callback and closes it with :func:`teardown`; every helper below resolves
the active context through a ``ContextVar`` following the same pattern as
``model_preload._ACTIVE_REQUEST_TRACE``.

Scope discipline (what this module deliberately does NOT do):

* **No full value reads.**  Descriptor construction iterates safetensors
  headers only (``get_slice(k).get_shape()/get_dtype()``); tensor payloads
  are never touched here.
* **No full-file SHA.**  Freshness is detected cheaply by re-statting
  (size + ``mtime_ns`` match), never by hashing content.
* **No CPU materialization.**  Nothing in this module stages bytes into
  RAM; the optional checkpoint prewarmer owns any cooperative reading.
* **D15 neutrality.**  This module owns no GPU gates.  GPU-lane
  coordination stays in ``gpu_lane_coordination`` / D15 surfaces; states
  here are pure request-lifecycle bookkeeping.
* **Fail-closed truth.**  Terminal reasons are append-only and sticky:
  once recorded they can never be erased, mirroring the R42A
  terminal-fallback stickiness semantics of ``loader_selection``.
"""

from __future__ import annotations

import json
import os
import threading
import time
from collections import OrderedDict
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any, Iterable, Optional

from .env import env_flag

# ---------------------------------------------------------------------------
# Environment flags
# ---------------------------------------------------------------------------

FLAG_MASTER = "COMFYMODAL_V2_REQUEST_FASTSAFE"
FLAG_CLIP = "COMFYMODAL_V2_REQUEST_CLIP_FASTSAFE"
FLAG_UNET = "COMFYMODAL_V2_REQUEST_UNET_FASTSAFE"
FLAG_SOURCE_PREP = "COMFYMODAL_V2_REQUEST_UNET_SOURCE_PREP"
#: R44F: native zero-copy CLIP adoption (meta construction + assign-style
#: bind of the served FastSafe CUDA tensors).  Narrowly scoped: requires the
#: request CLIP FastSafe lane AND this flag; default OFF everywhere.
FLAG_CLIP_NATIVE_ADOPT = "COMFYMODAL_V2_REQUEST_CLIP_FASTSAFE_NATIVE_ADOPT"

#: Per-role flags default to the master flag when absent.
_DEFAULT_FOLLOW_MASTER = True


def enabled() -> bool:
    """Master request fast-path switch."""
    return env_flag(FLAG_MASTER)


def clip_enabled() -> bool:
    """Master AND clip-specific switch (clip defaults to master)."""
    return enabled() and env_flag(FLAG_CLIP, default=_DEFAULT_FOLLOW_MASTER)


def clip_native_adopt_enabled() -> bool:
    """R44F native zero-copy CLIP adoption switch.

    Requires the request CLIP FastSafe lane (master + clip flags) AND the
    dedicated adopt flag; defaults OFF so every profile that does not
    explicitly opt in keeps the proven R44B/R44E copy-mode producer."""
    return clip_enabled() and env_flag(FLAG_CLIP_NATIVE_ADOPT, default=False)


def unet_enabled() -> bool:
    """Master AND unet-specific switch (unet defaults to master)."""
    return enabled() and env_flag(FLAG_UNET, default=_DEFAULT_FOLLOW_MASTER)


def source_prep_enabled() -> bool:
    """Master AND unet source-prep switch (defaults to master)."""
    return enabled() and env_flag(FLAG_SOURCE_PREP, default=_DEFAULT_FOLLOW_MASTER)


# ---------------------------------------------------------------------------
# Immutable model file descriptors (header-only)
# ---------------------------------------------------------------------------

_DESCRIPTOR_CACHE_MAX = 16
_DESCRIPTOR_CACHE: "OrderedDict[tuple, ModelFileDescriptor]" = OrderedDict()
_DESCRIPTOR_CACHE_LOCK = threading.Lock()


@dataclass(frozen=True)
class ModelFileDescriptor:
    """Immutable, header-derived description of one safetensors file.

    Built exclusively from the safetensors header (keys, shapes, dtypes,
    metadata) plus a stat snapshot.  Never carries tensor values.
    """

    role: str
    path: str
    size_bytes: int
    mtime_ns: int
    keys: tuple[str, ...]
    shapes: dict[str, tuple[int, ...]]
    dtypes: dict[str, str]
    metadata: dict[str, str]
    target_device: str

    def fresh(self) -> bool:
        """Cheap freshness detector: re-stat and compare size + mtime_ns.

        Never hashes content and never opens the file for reading.
        """
        try:
            st = os.stat(self.path)
        except OSError:
            return False
        return st.st_size == self.size_bytes and st.st_mtime_ns == self.mtime_ns


def build_descriptor(
    role: str, path: str, target_device: str = "cuda", metrics: Optional[dict] = None
) -> Optional[ModelFileDescriptor]:
    """Build a header-only :class:`ModelFileDescriptor` for *path*.

    Iterates the safetensors header via ``safe_open(...).get_slice(k)``
    (shapes + dtypes only -- NO tensor value reads).  Returns ``None`` on
    missing files or parse errors.  Successful descriptors are cached at
    process level keyed by ``(canonical path, size, mtime_ns)``; the cache
    holds only immutable descriptors and is bounded via a simple LRU.
    When *metrics* (a dict) is supplied it receives ``cache_hit`` and
    ``wall_ms`` for this call.
    """
    t0 = time.monotonic_ns()
    cache_hit = False
    try:
        canonical = os.path.normcase(os.path.abspath(path))
        st = os.stat(canonical)
        cache_key = (canonical, st.st_size, st.st_mtime_ns)
        with _DESCRIPTOR_CACHE_LOCK:
            hit = _DESCRIPTOR_CACHE.get(cache_key)
            if hit is not None:
                _DESCRIPTOR_CACHE.move_to_end(cache_key)
                cache_hit = True
                if metrics is not None:
                    metrics["cache_hit"] = True
                    metrics["wall_ms"] = round((time.monotonic_ns() - t0) / 1e6, 3)
                return hit

        # Lazy import: keep this module importable without safetensors/torch.
        from safetensors import safe_open

        keys: list[str] = []
        shapes: dict[str, tuple[int, ...]] = {}
        dtypes: dict[str, str] = {}
        with safe_open(canonical, framework="pt") as sf:
            meta = sf.metadata() or {}
            for k in sf.keys():
                sl = sf.get_slice(k)
                keys.append(str(k))
                shapes[str(k)] = tuple(int(d) for d in sl.get_shape())
                dtypes[str(k)] = str(sl.get_dtype())

        desc = ModelFileDescriptor(
            role=str(role),
            path=canonical,
            size_bytes=int(st.st_size),
            mtime_ns=int(st.st_mtime_ns),
            keys=tuple(keys),
            shapes=shapes,
            dtypes=dtypes,
            metadata={str(k): str(v) for k, v in meta.items()},
            target_device=str(target_device),
        )
        with _DESCRIPTOR_CACHE_LOCK:
            _DESCRIPTOR_CACHE[cache_key] = desc
            _DESCRIPTOR_CACHE.move_to_end(cache_key)
            while len(_DESCRIPTOR_CACHE) > _DESCRIPTOR_CACHE_MAX:
                _DESCRIPTOR_CACHE.popitem(last=False)
        if metrics is not None:
            metrics["cache_hit"] = False
            metrics["wall_ms"] = round((time.monotonic_ns() - t0) / 1e6, 3)
        return desc
    except Exception:
        if metrics is not None:
            metrics["cache_hit"] = False
            metrics["wall_ms"] = round((time.monotonic_ns() - t0) / 1e6, 3)
        return None


# ---------------------------------------------------------------------------
# Request-scoped fast-path context
# ---------------------------------------------------------------------------

_ROLE_STATES = (
    "idle",
    "loading",
    "ready",
    "forwarding",
    "critical_done",
    "adopted",
    "failed",
    "fallback",
)


def _json_safe(value: Any) -> Any:
    """Coerce *value* onto the JSON-safe subset (str/int/float/bool/None)."""
    if value is None or isinstance(value, (str, bool, int, float)):
        return value
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(v) for v in value]
    return str(value)


def interval_overlap_ms(a0_ns: Optional[int], a1_ns: Optional[int], b0_ns: Optional[int], b1_ns: Optional[int]) -> Optional[float]:
    """Overlap of two monotonic-ns intervals in ms; None when any stamp is
    missing; disjoint intervals yield 0.0 (never negative, never double-
    counted across multiple intervals)."""
    if a0_ns is None or a1_ns is None or b0_ns is None or b1_ns is None:
        return None
    overlap = min(a1_ns, b1_ns) - max(a0_ns, b0_ns)
    if overlap <= 0:
        return 0.0
    return overlap / 1e6


class FastPathRequestContext:
    """Request-lifetime coordination for fast-path loaders.

    All state mutations happen under a single ``RLock``; completion events
    are plain ``threading.Event`` instances.  Role lifecycle states follow
    the frozen vocabulary::

        idle -> loading -> ready -> forwarding -> critical_done
        (terminal alternatives: adopted | failed | fallback)
    """

    def __init__(self, request_id: str = "", trace: Any = None) -> None:
        self.request_id = str(request_id or "")
        self.trace = trace
        self.created_mono_ns = time.monotonic_ns()
        self.descriptors: dict[str, ModelFileDescriptor] = {}

        self._lock = threading.RLock()
        self._states: dict[str, str] = {"clip": "idle", "unet": "idle"}
        self._claims: dict[str, bool] = {"clip": False, "unet": False}
        self._clip_forward_t0_mono_ns: Optional[int] = None
        self._clip_forward_wall_ms: Optional[float] = None
        self._clip_forward_done = threading.Event()
        self._results: dict[str, Any] = {}
        self._result_events: dict[str, threading.Event] = {}
        self._terminal_reasons: list[str] = []
        self._prep_armed = False
        self._prep_joined = False
        self._prewarmer: Any = None
        self._prep_arm_wall_ms: Optional[float] = None
        self._prep_join_wall_ms: Optional[float] = None
        self._prep_start_mono_ns: Optional[int] = None
        self._prep_join_start_mono_ns: Optional[int] = None
        self._prep_join_end_mono_ns: Optional[int] = None
        self._clip_forward_end_mono_ns: Optional[int] = None
        self._unet_source_identity: Optional[dict] = None
        self._durable_trace_resolver: Any = None
        self._token: Any = None
        self._torn_down = False

    # -- role state accessors ------------------------------------------------

    @property
    def clip_state(self) -> str:
        with self._lock:
            return self._states.get("clip", "idle")

    @property
    def unet_state(self) -> str:
        with self._lock:
            return self._states.get("unet", "idle")

    def _set_state(self, role: str, state: str) -> None:
        with self._lock:
            self._states[role] = state

    # -- single-flight physical load latch ------------------------------------

    def claim_physical_load(self, role: str) -> bool:
        """Single-flight latch: True exactly once per (context, role).

        Duplicate claims return ``False`` so concurrent loaders cannot both
        perform the physical load.  The first claim transitions the role
        state ``idle -> loading``.
        """
        with self._lock:
            if self._claims.get(role):
                return False
            self._claims[role] = True
            if self._states.get(role, "idle") == "idle":
                self._states[role] = "loading"
            return True

    def release_claim(self, role: str, reason: str) -> None:
        """Release a held claim, recording *reason* as a terminal reason."""
        with self._lock:
            self._claims[role] = False
            self._terminal_reasons.append(f"{role}:{str(reason)[:290]}"[:300])
            if self._states.get(role) in ("idle", "loading"):
                self._states[role] = "fallback"

    # -- descriptors ------------------------------------------------------------

    def set_descriptor(self, role: str, desc: ModelFileDescriptor) -> None:
        with self._lock:
            self.descriptors[role] = desc

    def descriptor(self, role: str) -> Optional[ModelFileDescriptor]:
        with self._lock:
            return self.descriptors.get(role)

    # -- clip critical-section lifecycle ----------------------------------------

    def mark_clip_loaded(self) -> None:
        """Clip weights resident: ``ready``.  Idempotent-safe."""
        with self._lock:
            if self._states.get("clip") in ("idle", "loading"):
                self._states["clip"] = "ready"

    def mark_clip_forward_start(self) -> None:
        """Enter the clip forward critical section; records t0.

        R44E: this is ALSO the UNET source-prep trigger point.  When the
        immutable plan-derived UNET source identity is already stored and
        source prep is enabled, the CPU-only prewarmer arms HERE so the
        storage read overlaps CLIP GPU compute (never the CLIP FastSafe
        transport, which completed before encode begins)."""
        with self._lock:
            self._clip_forward_t0_mono_ns = time.monotonic_ns()
            self._states["clip"] = "forwarding"
        self._maybe_arm_prep_on_forward_start()

    def _maybe_arm_prep_on_forward_start(self) -> None:
        try:
            if self._prep_armed:
                return
            ident = self.unet_source_identity()
            if not ident or not ident.get("path"):
                return
            if not source_prep_enabled():
                return
            self.arm_unet_source_prep([ident.get("path")], trigger="clip_forward_start")
        except Exception:
            pass

    def mark_clip_forward_end(self) -> None:
        """Leave the clip forward critical section.

        Order-tolerant: calling without a prior start still sets the
        done event (wall time is then measured from context creation).
        """
        with self._lock:
            t0 = self._clip_forward_t0_mono_ns
            if t0 is None:
                t0 = self.created_mono_ns
            now = time.monotonic_ns()
            self._clip_forward_wall_ms = (now - t0) / 1e6
            self._clip_forward_end_mono_ns = now
            self._states["clip"] = "critical_done"
        self._clip_forward_done.set()

    def clip_forward_window(self) -> tuple[Optional[int], Optional[int]]:
        """Monotonic-ns ``(forward_start, forward_end)`` stamps (either may
        be ``None`` before the corresponding boundary is marked)."""
        with self._lock:
            return (self._clip_forward_t0_mono_ns, self._clip_forward_end_mono_ns)

    def prep_stamps(self) -> dict:
        """Raw monotonic-ns source-prep stamps for durable overlap math."""
        with self._lock:
            prewarmer = self._prewarmer
            stats: dict = {}
            if prewarmer is not None:
                try:
                    raw = prewarmer.as_dict() or {}
                    for key in (
                        "prewarm_bytes", "prewarm_read_calls", "prewarm_stop_reason",
                        "prewarm_finished_before_demand", "prewarm_wall_ms",
                        "prewarm_thread_cpu_ms", "prewarm_join_ms",
                        "source_fence_valid", "prefetch_retirement_result",
                    ):
                        if key in raw:
                            stats[key] = raw.get(key)
                except Exception:
                    stats = {}
            return {
                "armed": self._prep_armed,
                "armed_at_mono_ns": self._prep_start_mono_ns,
                "prep_start_mono_ns": self._prep_start_mono_ns,
                "prep_join_start_mono_ns": self._prep_join_start_mono_ns,
                "prep_join_end_mono_ns": self._prep_join_end_mono_ns,
                "joined": self._prep_joined,
                "join_wall_ms": self._prep_join_wall_ms,
                "arm_wall_ms": self._prep_arm_wall_ms,
                "stats": stats,
            }

    def clip_forward_done_event(self) -> threading.Event:
        """Event set once the clip forward critical section completes."""
        return self._clip_forward_done

    # -- unet source prep (bounded cooperative prewarm fence) -------------------

    def set_unet_source_identity(self, **identity: Any) -> None:
        """Store the immutable plan-derived UNET source identity.

        Identity only (path/stat/node coordinates) — no header parse, no
        value reads, no prewarm start.  Arming remains a separate,
        forward-start-triggered decision."""
        with self._lock:
            self._unet_source_identity = dict(identity)

    def unet_source_identity(self) -> Optional[dict]:
        with self._lock:
            ident = self._unet_source_identity
            return dict(ident) if ident else None

    def arm_unet_source_prep(self, paths: Iterable[Any], trigger: str = "unet_loader_entry") -> bool:
        """Arm the cooperative source-prep prewarmer exactly once.

        Lazily imports ``checkpoint_prewarm`` and constructs a
        :class:`~comfymodal_runtime.checkpoint_prewarm.CheckpointPrewarmer`
        honoring the ``COMFYMODAL_V2_CHECKPOINT_PREWARM_*`` env knobs while
        NOT requiring its global enable flag (enablement is forced here).
        Never raises; returns whether a worker actually started.
        """
        with self._lock:
            if self._prep_armed:
                return self._prewarmer is not None
            self._prep_armed = True
            self._prep_start_mono_ns = time.monotonic_ns()
        t0 = time.monotonic_ns()
        started = False
        prewarmer: Any = None
        kwargs: dict[str, Any] = {}
        try:
            # sys.modules-faithful resolution: ``import x.y as z`` prefers the
            # package attribute, which shadows test doubles installed via
            # ``sys.modules[...]``; import_module honors the active mapping.
            import importlib

            cp = importlib.import_module("comfymodal_runtime.checkpoint_prewarm")

            kwargs["enabled"] = True
            threads_raw = os.environ.get(cp.PREWARM_THREADS_ENV, "").strip()
            if threads_raw:
                try:
                    kwargs["threads"] = max(1, int(threads_raw))
                except ValueError:
                    pass
            chunk_raw = os.environ.get(cp.PREWARM_CHUNK_MB_ENV, "").strip()
            if chunk_raw:
                try:
                    kwargs["chunk_bytes"] = max(1, int(chunk_raw)) * (1024 * 1024)
                except ValueError:
                    pass
            prewarmer = cp.CheckpointPrewarmer(**kwargs)
            started = bool(prewarmer.start(list(paths)))
        except Exception:
            started = False
            prewarmer = None
        finally:
            with self._lock:
                self._prewarmer = prewarmer if started else None
                self._prep_arm_wall_ms = (time.monotonic_ns() - t0) / 1e6
        try:
            ident = self.unet_source_identity() or {}
            targeted: list[dict] = []
            for raw_path in paths:
                try:
                    st = os.stat(raw_path)
                    targeted.append({
                        "path_basename": os.path.basename(str(raw_path)),
                        "size_bytes": int(st.st_size),
                    })
                except Exception:
                    fallback_size = ident.get("size_bytes") if len(paths) == 1 else None
                    targeted.append({
                        "path_basename": os.path.basename(str(raw_path)),
                        "size_bytes": int(fallback_size) if fallback_size is not None else None,
                    })
            self.telemetry(
                "unet_source_prep_armed",
                trigger=str(trigger),
                armed_at_mono_ns=self._prep_start_mono_ns,
                started=bool(started),
                targeted_bytes=sum(int(e["size_bytes"]) for e in targeted if e["size_bytes"] is not None),
                files=targeted,
                threads=kwargs.get("threads"),
                chunk_mb=(int(kwargs.get("chunk_bytes", 0)) // (1024 * 1024)) if kwargs.get("chunk_bytes") else None,
                arm_wall_ms=round(self._prep_arm_wall_ms or 0.0, 3),
            )
        except Exception:
            pass
        return started

    def join_unet_source_prep(self, timeout_s: float = 30.0) -> dict:
        """Bounded fence before demand load: prewarm join, then stop+retire.

        Idempotent and never raises.  Returns a JSON-safe dict
        ``{"armed": bool, "joined": bool, "wall_ms": float}``.
        """
        deadline = time.monotonic() + max(0.0, float(timeout_s))
        with self._lock:
            if self._prep_joined:
                return {
                    "armed": self._prewarmer is not None,
                    "joined": True,
                    "wall_ms": round(float(self._prep_join_wall_ms or 0.0), 3),
                }
            prewarmer = self._prewarmer
            self._prep_joined = True
            self._prep_join_start_mono_ns = time.monotonic_ns()
        t0 = time.monotonic_ns()
        # Nothing armed -> the fence is vacuously satisfied.
        joined = prewarmer is None
        try:
            if prewarmer is not None:
                remaining = max(0.0, deadline - time.monotonic())
                prewarmer.before_demand_load()
                remaining = max(0.0, deadline - time.monotonic())
                joined = bool(
                    prewarmer.stop_and_join_before_demand()
                ) or remaining <= 0.0
        except Exception:
            joined = False
        wall_ms = (time.monotonic_ns() - t0) / 1e6
        with self._lock:
            self._prep_join_wall_ms = wall_ms
            self._prep_join_end_mono_ns = time.monotonic_ns()
        result = {
            "armed": prewarmer is not None,
            "joined": bool(joined),
            "wall_ms": round(wall_ms, 3),
        }
        try:
            stamps = self.prep_stamps()
            stats = stamps.get("stats") or {}
            self.telemetry(
                "unet_source_prep_joined",
                join_start_mono_ns=self._prep_join_start_mono_ns,
                join_end_mono_ns=self._prep_join_end_mono_ns,
                join_wall_ms=round(wall_ms, 3),
                armed=result["armed"],
                joined=result["joined"],
                touched_bytes=stats.get("prewarm_bytes"),
                read_count=stats.get("prewarm_read_calls"),
                stop_reason=stats.get("prewarm_stop_reason"),
                finished_before_demand=stats.get("prewarm_finished_before_demand"),
                source_fence_valid=stats.get("source_fence_valid"),
            )
        except Exception:
            pass
        return result

    # -- result handoff -----------------------------------------------------------

    def publish_result(self, role: str, payload: Any) -> None:
        """Store *payload* for *role* and wake waiters."""
        with self._lock:
            self._results[role] = payload
            event = self._result_events.get(role)
            if event is None:
                event = threading.Event()
                self._result_events[role] = event
        event.set()

    def result(self, role: str, timeout_s: Optional[float] = None):
        """Return the published payload for *role*, optionally waiting.

        With ``timeout_s`` given, blocks up to that long on the role's
        completion event.  Returns ``None`` when nothing was published.
        The wait event is registered lazily under the lock so a waiter
        that arrives BEFORE the producer publishes still observes the
        wakeup (a bare ``Event.wait`` on a not-yet-existing event would
        return immediately and defeat the bounded wait).
        """
        with self._lock:
            payload = self._results.get(role)
            event = self._result_events.get(role)
            if event is None and payload is None and timeout_s is not None:
                # Pre-register the wake event for the future publisher.
                event = threading.Event()
                self._result_events[role] = event
        if timeout_s is not None and event is not None and payload is None:
            event.wait(max(0.0, float(timeout_s)))
            with self._lock:
                payload = self._results.get(role)
        return payload

    # -- fail-closed terminal ledger ----------------------------------------------

    def record_terminal(self, reason: str, role: Optional[str] = None) -> None:
        """Append *reason* to the sticky terminal ledger (never erased)."""
        entry = f"{role}:{reason}" if role else str(reason)
        with self._lock:
            self._terminal_reasons.append(entry[:300])

    def terminal_reasons(self) -> tuple[str, ...]:
        with self._lock:
            return tuple(self._terminal_reasons)

    # -- telemetry -----------------------------------------------------------------

    def set_durable_trace_resolver(self, resolver: Any) -> None:
        """Install a callable returning the canonical durable request trace.

        When unset, telemetry lazily resolves
        ``model_preload._ACTIVE_REQUEST_TRACE`` per emission (the same
        proven pattern used by the UNET FastSafe producer)."""
        self._durable_trace_resolver = resolver

    def _durable_trace(self) -> Any:
        resolver = getattr(self, "_durable_trace_resolver", None)
        if callable(resolver):
            try:
                return resolver()
            except Exception:
                return None
        try:
            import importlib

            _mp = importlib.import_module("comfymodal_runtime.model_preload")
            return _mp._ACTIVE_REQUEST_TRACE.get()
        except Exception:
            return None

    def telemetry(self, event: str, **md: Any) -> None:
        """Best-effort trace emission; NEVER raises.

        R44E DURABILITY: ONE payload, TWO sinks.  The event is emitted to
        the request-local diagnostics sink (``self.trace``, unchanged
        behavior incl. adaptive snapshot suppression) AND to the canonical
        durable request trace (resolved via :meth:`_durable_trace`) so every
        FastSafe/decomposition event persists into run artifacts.  The same
        ``safe_md`` mapping serves both sinks; no duplicate payload
        construction.  Emission to the durable sink is skipped when it IS
        the diagnostics sink (no double record).

        Adaptive snapshot suppression: when the trace sink's ``emit``
        signature accepts a ``snapshot`` parameter (TeardownDiagnostics-style
        sinks capture a FULL process snapshot by default), pass
        ``snapshot=False`` — per-request loader telemetry must not pay for a
        process snapshot per event.  The signature probe is computed ONCE per
        trace object (cached on ``self._emit_supports_snapshot``) via pure
        ``inspect.signature`` inspection; no teardown/trace module imports.
        """
        try:
            safe_md = {str(k): _json_safe(v) for k, v in md.items()}
        except Exception:
            return
        if self.trace is not None:
            try:
                supports_snapshot = getattr(self, "_emit_supports_snapshot", None)
                if supports_snapshot is None:
                    try:
                        import inspect

                        supports_snapshot = (
                            "snapshot" in inspect.signature(self.trace.emit).parameters
                        )
                    except Exception:
                        supports_snapshot = False
                    try:
                        self._emit_supports_snapshot = bool(supports_snapshot)
                    except Exception:
                        pass
                if supports_snapshot:
                    self.trace.emit(
                        str(event), phase="execution", metadata=safe_md, snapshot=False
                    )
                else:
                    self.trace.emit(str(event), phase="execution", metadata=safe_md)
            except Exception:
                pass
        try:
            durable = self._durable_trace()
            if durable is not None and durable is not self.trace:
                durable.emit(str(event), phase="execution", metadata=safe_md)
        except Exception:
            pass

    # -- summary ---------------------------------------------------------------------

    def summary(self) -> dict:
        """JSON-safe snapshot of context state for logging/handoff."""
        with self._lock:
            clip_t0 = self._clip_forward_t0_mono_ns
            return {
                "request_id": self.request_id,
                "created_age_ms": round((time.monotonic_ns() - self.created_mono_ns) / 1e6, 3),
                "states": {
                    "clip": self._states.get("clip", "idle"),
                    "unet": self._states.get("unet", "idle"),
                },
                "claims": {
                    "clip": bool(self._claims.get("clip")),
                    "unet": bool(self._claims.get("unet")),
                },
                "descriptors": sorted(self.descriptors.keys()),
                "terminal_reasons": list(self._terminal_reasons),
                "clip_forward_started": clip_t0 is not None,
                "clip_forward_wall_ms": (
                    round(self._clip_forward_wall_ms, 3)
                    if self._clip_forward_wall_ms is not None
                    else None
                ),
                "clip_forward_done": self._clip_forward_done.is_set(),
                "results_published": sorted(self._results.keys()),
                "source_prep_armed": self._prep_armed,
                "source_prep_active": self._prewarmer is not None,
                "source_prep_joined": self._prep_joined,
                "source_prep_arm_wall_ms": (
                    round(self._prep_arm_wall_ms, 3)
                    if self._prep_arm_wall_ms is not None
                    else None
                ),
                "source_prep_join_wall_ms": (
                    round(self._prep_join_wall_ms, 3)
                    if self._prep_join_wall_ms is not None
                    else None
                ),
                "unet_source_identity": dict(self._unet_source_identity) if self._unet_source_identity else None,
                "torn_down": self._torn_down,
            }


# ---------------------------------------------------------------------------
# ContextVar plumbing (mirrors model_preload._ACTIVE_REQUEST_TRACE)
# ---------------------------------------------------------------------------

_active: ContextVar["Optional[FastPathRequestContext]"] = ContextVar(
    "comfymodal_r44b_request_fastpath", default=None
)


def current() -> Optional[FastPathRequestContext]:
    """Return the active request fast-path context, or ``None``."""
    return _active.get()


def begin(request_id: str = "", trace: Any = None) -> FastPathRequestContext:
    """Open a request fast-path context and bind it to the current task.

    The saved ``ContextVar`` token is attached as ``ctx._token`` so
    :func:`teardown` can restore the prior value exactly.
    """
    ctx = FastPathRequestContext(request_id=request_id, trace=trace)
    ctx._token = _active.set(ctx)
    ctx.telemetry(
        "request_fastpath_begin",
        request_id=ctx.request_id,
        master=enabled(),
        clip=clip_enabled(),
        unet=unet_enabled(),
        source_prep=source_prep_enabled(),
        clip_native_adopt=clip_native_adopt_enabled(),
    )
    return ctx


def teardown(ctx: Optional[FastPathRequestContext]) -> None:
    """Close a request fast-path context; idempotent and never raises.

    Resets the ``ContextVar`` to the saved token, performs a best-effort
    bounded join of an armed source-prep prewarmer, and emits
    ``request_fastpath_end`` with the final summary.
    """
    if ctx is None:
        return
    try:
        with ctx._lock:
            already = ctx._torn_down
            ctx._torn_down = True
        if not already:
            try:
                ctx.join_unet_source_prep(timeout_s=5.0)
            except Exception:
                pass
            token = getattr(ctx, "_token", None)
            if token is not None and current() is ctx:
                _active.reset(token)
                ctx._token = None
            ctx.telemetry(
                "request_fastpath_end",
                request_id=ctx.request_id,
                summary=json.dumps(_json_safe(ctx.summary()), sort_keys=True),
            )
    except Exception:
        pass


__all__ = [
    "FLAG_MASTER",
    "FLAG_CLIP",
    "FLAG_UNET",
    "FLAG_SOURCE_PREP",
    "FLAG_CLIP_NATIVE_ADOPT",
    "ModelFileDescriptor",
    "FastPathRequestContext",
    "build_descriptor",
    "interval_overlap_ms",
    "enabled",
    "clip_enabled",
    "clip_native_adopt_enabled",
    "unet_enabled",
    "source_prep_enabled",
    "current",
    "begin",
    "teardown",
]
