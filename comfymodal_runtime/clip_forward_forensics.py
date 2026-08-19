"""E31 CLIP forward forensics: synchronized GPU timing + cast classification.

Batch E31 ownership: CLIP-forward variance and correct FP32 cast-once
mechanics/measurement.  This module is E31-owned and self-contained; it adds
NO hooks to E29-owned files (``modal_app.py``, ``runtime_bootstrap.py``,
``runtime_executor.py``, ``gantt_telemetry.py``, ``v2_waterfall.py``, the
benchmark harness) and does NOT edit E30's CLIP source-loader files.

Motivation (why E28's ``cuda_event_wall_ms = 0.0`` is not proof):

* E28's forward-cast counter wrapped ``comfy.ops.cast_bias_weight`` but
  parsed the arguments as ``(weight, bias, dtype)`` while the real signature
  is ``(s, input=None, dtype=None, ...)`` — so ``source_dtypes`` came back
  all ``unknown`` and the shapes as ``()``.  The 253 calls / 15.31 GB dest
  bytes are real (252 bias + 1 weight cast to FP32 per forward), but the GPU
  time of those conversions was never actually measured.
* The old per-call event measurement recorded start and end events back-to-
  back on the default stream *after* the cast had already been enqueued and
  computed ``elapsed_time`` immediately — events with no work between them
  and no synchronize → 0.0 ms regardless of the real GPU conversion time.
* Python ``.to()``/``cast_to`` enqueue async GPU work; host submission wall
  is not GPU conversion wall.  The correct measurement is event pairs on the
  REAL stream, with ONE synchronize after the whole forward, then read.

Design (all default OFF):

* ``COMFYMODAL_V2_E31_FORENSICS=1`` — synchronized whole-forward CUDA timing
  + corrected cast classification + per-cast structured evidence.
* ``COMFYMODAL_V2_E31_FORWARD_PROFILE=1`` — opt-in torch.profiler pass over
  one forward (explicit, one-shot, never in production).
* ``COMFYMODAL_V2_CLIP_FP32_CAST_ONCE=1`` — E28's compute-ready FP32
  cast-once (retained; see ``clip_fp32_cast_once.py``).

With the gate OFF every function here is a no-op, no wrapper is installed,
and no CUDA work is performed at import time.

Measurement protocol (Phase 2):

* ``ForwardTimer`` — one start event + one end event recorded on
  ``torch.cuda.current_stream()`` bracketing the whole forward; a single
  ``end_event.synchronize()`` after forward; then
  ``start_event.elapsed_time(end_event)``.  Reports host wall, GPU elapsed,
  host-only residual (wall - gpu, clamped >= 0), and the measured event
  overhead of an empty bracketed pair on the same stream (subtracted).
* Per-cast diagnosis records event pairs WITHOUT synchronizing per call and
  WITHOUT reading elapsed_time at call time (a pre-sync read is the E28
  ``0.0 ms`` bug).  The pairs are queued and resolved once, after the single
  post-forward sync, by :func:`resolve_pending_cast_events` (called from
  :meth:`ForwardTimer.end`).  Values are only reported for pairs recorded on
  the stream that is current at resolution time.

Cast classification (Phase 3):

For every call through the wrapped cast entry points
(``comfy.ops.cast_bias_weight`` and ``comfy.model_management.cast_to`` /
``cast_to_device``) we classify the outcome:

* REAL_CONVERSION          — dtype changed AND a new tensor/storage was
                            produced (or an in-place dtype mutation).
* REAL_COPY_NO_DTYPE_CHANGE— new storage, same dtype (device or copy move).
* VIEW_ALIAS               — result aliases the source (same storage,
                            different tensor object, e.g. non-copy same
                            dtype/device).
* NOOP_SAME_TENSOR         — result is the identical tensor object.
* NOOP_SAME_STORAGE        — different object, same storage, no dtype change.
* OTHER                    — anything unclassifiable (non-tensor, exception).

Aggregates: real conversions count + real bytes converted (union of
destination bytes for REAL_CONVERSION), same-storage noops, new allocations,
and the synchronized GPU conversion milliseconds (sum of per-call event
deltas after the single forward sync).  Structured per-call evidence is kept
in a bounded ring (``COMFYMODAL_V2_E31_CAST_SAMPLE_LIMIT``, default 1024) and
never dumped to logs by default.
"""

from __future__ import annotations

import os
import threading
import time
from collections import deque
from typing import Any, Callable, Optional

from .env import env_flag

_E31_FORENSICS_FLAG = "COMFYMODAL_V2_E31_FORENSICS"
_E31_PROFILE_FLAG = "COMFYMODAL_V2_E31_FORWARD_PROFILE"
_E31_CAST_SAMPLE_LIMIT = "COMFYMODAL_V2_E31_CAST_SAMPLE_LIMIT"

# E29 ledger integration surface: the canonical request-scoped event store
# (COMFYMODAL_V2_CRITICAL_PATH_LEDGER, default ON).  E31 events are emitted
# ONLY when the E31 forensics gate is also on, so a non-E31 run never pays
# for them; when both gates are on, the E31 events appear on the canonical
# axis with the request identity block (no competing timeline).
_LEDGER_EVENT_NAMES = (
    "clip_forward_start",
    "clip_forward_end",
    "clip_gpu_event_start",
    "clip_gpu_event_end",
    "clip_forward_gpu_ms",
    "clip_cast_once_start",
    "clip_cast_once_end",
    "clip_cast_once_gpu_ms",
    "clip_forward_cast_summary",
    "clip_profiler_start",
    "clip_profiler_end",
)

_ENABLED: bool = env_flag(_E31_FORENSICS_FLAG, default=False)
_PROFILE_ENABLED: bool = env_flag(_E31_PROFILE_FLAG, default=False)

_SENTINEL_CAST = "_comfymodal_e31_cast_wrapper"
_SENTINEL_PROFILE = "_comfymodal_e31_profile_wrapper"

# Classification result strings (Phase 3 taxonomy).
REAL_CONVERSION = "REAL_CONVERSION"
REAL_COPY_NO_DTYPE_CHANGE = "REAL_COPY_NO_DTYPE_CHANGE"
VIEW_ALIAS = "VIEW_ALIAS"
NOOP_SAME_TENSOR = "NOOP_SAME_TENSOR"
NOOP_SAME_STORAGE = "NOOP_SAME_STORAGE"
OTHER = "OTHER"


# ── stream- and event helpers (never touch CUDA at import time) ──────────

def _current_stream() -> Any:
    """Return the current CUDA stream object (or None when unavailable)."""
    try:
        import torch

        if not torch.cuda.is_available():
            return None
        return torch.cuda.current_stream()
    except Exception:
        return None


def _make_event() -> Any:
    """Create a CUDA timing event (or a no-op stub when CUDA is unavailable)."""
    try:
        import torch

        if torch.cuda.is_available():
            return torch.cuda.Event(enable_timing=True)
    except Exception:
        pass

    class _NoopEvent:
        def record(self, stream: Any = None) -> None:
            pass

        def synchronize(self) -> None:
            pass

        def elapsed_time(self, _other: Any) -> float:
            return 0.0

    return _NoopEvent()


def _ledger_enabled() -> bool:
    """Whether the E29 canonical ledger store is live (never raises)."""
    try:
        from . import critical_path_ledger as _cpl

        return bool(getattr(_cpl, "_ENABLED", False))
    except Exception:
        return False


def emit_ledger_event(name: str, *, mono_ns: int | None = None, **metadata: Any) -> None:
    """Emit one E31 event on the E29 canonical ledger axis.

    No-op when the E31 forensics gate is off or the ledger is unavailable.
    The event name must be in :data:`_LEDGER_EVENT_NAMES` (the E29-integration
    contract) — anything else is dropped so a typo cannot silently create a
    competing timeline.  Never raises.
    """
    if not _ENABLED:
        return
    if name not in _LEDGER_EVENT_NAMES:
        return
    try:
        from . import critical_path_ledger as _cpl

        _cpl.record_event(
            name,
            mono_ns=mono_ns,
            metadata=dict(metadata),
        )
    except Exception:
        pass


def _module_path_prefix(module: Any, max_len: int = 96) -> str:
    """Best-effort module path prefix (``module_path`` attr or class name)."""
    try:
        path = getattr(module, "module_path", "") or ""
        if path:
            return str(path)[:max_len]
    except Exception:
        pass
    try:
        return type(module).__name__[:max_len]
    except Exception:
        return "?"


class ForwardTimer:
    """Synchronized whole-forward CUDA timing (host wall + GPU elapsed).

    Usage::

        timer = ForwardTimer()
        timer.start()          # records start event on the real stream
        forward(...)           # the actual forward, unchanged
        timer.end()            # records end event, ONE synchronize, reads
                               # elapsed_time — never raises

    ``end()`` reports ``host_wall_ms``, ``gpu_elapsed_ms``,
    ``host_only_residual_ms`` (wall - gpu, clamped >= 0), and
    ``event_overhead_ms`` (measured once per timer by an empty bracketed
    pair, lazily).  With CUDA unavailable the GPU fields are ``None`` — never
    a fabricated 0.0.
    """

    def __init__(self) -> None:
        self._start_event: Any = None
        self._end_event: Any = None
        self._start_wall: float | None = None
        self._end_wall: float | None = None
        self._start_mono_ns: int | None = None
        self._end_mono_ns: int | None = None
        self._overhead: float | None = None

    def start(self) -> None:
        stream = _current_stream()
        self._start_wall = time.perf_counter()
        self._start_mono_ns = time.monotonic_ns()
        emit_ledger_event("clip_forward_start", mono_ns=self._start_mono_ns)
        emit_ledger_event("clip_gpu_event_start", mono_ns=self._start_mono_ns)
        if stream is None:
            self._start_event = None
            self._end_event = None
            return
        try:
            self._start_event = _make_event()
            self._end_event = _make_event()
            self._start_event.record(stream)
        except Exception:
            self._start_event = None
            self._end_event = None

    def end(self) -> dict[str, Any]:
        stream = _current_stream()
        self._end_wall = time.perf_counter()
        self._end_mono_ns = time.monotonic_ns()
        emit_ledger_event("clip_forward_end", mono_ns=self._end_mono_ns)
        emit_ledger_event("clip_gpu_event_end", mono_ns=self._end_mono_ns)
        host_wall_ms = (
            (self._end_wall - self._start_wall) * 1000.0
            if self._start_wall is not None
            else None
        )
        if stream is None or self._start_event is None or self._end_event is None:
            return {
                "host_wall_ms": None if host_wall_ms is None else round(host_wall_ms, 3),
                "gpu_elapsed_ms": None,
                "host_only_residual_ms": None,
                "event_overhead_ms": None,
                "cuda_available": False,
            }
        try:
            self._end_event.record(stream)
            # The single synchronization — this is the entire sync budget of
            # the measurement; it also makes every recorded cast event pair
            # readable.
            self._end_event.synchronize()
            gpu_ms = float(self._start_event.elapsed_time(self._end_event))
            # Now that the forward's work has completed on the stream, read
            # every queued per-cast event pair (deferred, never per-call).
            resolve_pending_cast_events()
            emit_cast_summary_ledger(mono_ns=self._end_mono_ns)
        except Exception:
            gpu_ms = None
        overhead = self._measure_overhead(stream)
        residual = None
        if host_wall_ms is not None and gpu_ms is not None:
            residual = max(0.0, host_wall_ms - gpu_ms)
        if gpu_ms is not None:
            emit_ledger_event(
                "clip_forward_gpu_ms",
                mono_ns=self._end_mono_ns,
                gpu_ms=round(gpu_ms, 3),
            )
        return {
            "host_wall_ms": None if host_wall_ms is None else round(host_wall_ms, 3),
            "gpu_elapsed_ms": None if gpu_ms is None else round(gpu_ms, 3),
            "host_only_residual_ms": None if residual is None else round(residual, 3),
            "event_overhead_ms": None if overhead is None else round(overhead, 3),
            "cuda_available": stream is not None,
        }

    def _measure_overhead(self, stream: Any) -> float | None:
        """Measure one empty start/end event pair on the same stream (lazy)."""
        if self._overhead is not None:
            return self._overhead
        try:
            a = _make_event()
            b = _make_event()
            a.record(stream)
            b.record(stream)
            b.synchronize()
            self._overhead = float(a.elapsed_time(b))
        except Exception:
            self._overhead = None
        return self._overhead


# ── cast classification (Phase 3) ─────────────────────────────────────────

def _tensor_facts(t: Any) -> dict[str, Any]:
    """Collect classification facts about a tensor-like object (never raises)."""
    if t is None:
        return {"is_tensor": False}
    try:
        import torch

        if not isinstance(t, torch.Tensor):
            return {"is_tensor": False, "type": type(t).__name__}
    except Exception:
        return {"is_tensor": False, "type": type(t).__name__}
    try:
        return {
            "is_tensor": True,
            "dtype": str(t.dtype),
            "device": str(t.device),
            "data_ptr": int(t.data_ptr()) if not t.is_meta else None,
            "numel": int(t.numel()),
            "element_size": int(t.element_size()),
            "bytes": int(t.numel() * t.element_size()),
            "contiguous": bool(t.is_contiguous()),
            "storage_data_ptr": (
                int(t.untyped_storage().data_ptr()) if not t.is_meta else None
            ),
        }
    except Exception:
        return {"is_tensor": True, "error": "facts_failed"}


def classify_cast(source: Any, result: Any) -> tuple[str, dict[str, Any]]:
    """Classify one cast call's outcome.

    Returns ``(classification, evidence)`` where *evidence* carries the
    source/result facts plus the classification reason.  Never raises.
    """
    src = _tensor_facts(source)
    dst = _tensor_facts(result)
    if not src.get("is_tensor") or not dst.get("is_tensor"):
        return OTHER, {"reason": "non_tensor", "source": src, "dest": dst}
    if source is result:
        return NOOP_SAME_TENSOR, {"reason": "identical_object", "source": src, "dest": dst}
    if src.get("storage_data_ptr") == dst.get("storage_data_ptr"):
        if src.get("data_ptr") == dst.get("data_ptr"):
            return VIEW_ALIAS, {"reason": "same_storage_same_ptr_alias", "source": src, "dest": dst}
        return NOOP_SAME_STORAGE, {"reason": "same_storage", "source": src, "dest": dst}
    if src.get("dtype") != dst.get("dtype"):
        return REAL_CONVERSION, {"reason": "dtype_changed", "source": src, "dest": dst}
    return REAL_COPY_NO_DTYPE_CHANGE, {"reason": "new_storage_same_dtype", "source": src, "dest": dst}


# ── corrected cast wrapper (the E28 ``unknown``-dtype bug fix) ────────────

_CAST_LOCK = threading.Lock()
_cast_account: dict[str, Any] = {
    "weight_casts": 0,
    "bias_casts": 0,
    "other_casts": 0,
    "classifications": {},
    "real_conversions": 0,
    "real_conversion_bytes": 0,
    "same_storage_noops": 0,
    "new_allocations": 0,
    "host_wall_ms": 0.0,
    "gpu_event_ms": 0.0,
    "source_dtypes": {},
    "dest_dtypes": {},
    "first_weight_shapes": [],
    "first_bias_shapes": [],
    "module_paths": {},
}
_cast_samples: deque[dict[str, Any]] = deque(maxlen=1024)
# Per-call CUDA event pairs are NOT read at call time (that would be the
# E28 bug: reading elapsed_time before the work completed).  They are queued
# here and resolved after the ONE post-forward synchronize in
# ForwardTimer.end().  `_pending_ev_ts` records the stream the pair was
# recorded on (torch.cuda.current_stream() at call time), so the deferred
# read can re-check the current stream before trusting the value.
_cast_pending_events: deque[tuple[Any, Any, Any]] = deque()
_CAST_DEFER_MAX = 8192


def _pending_event_capacity() -> int:
    try:
        return max(64, min(int(os.environ.get(_E31_CAST_SAMPLE_LIMIT, "1024")) * 8, _CAST_DEFER_MAX))
    except Exception:
        return _CAST_DEFER_MAX


def _queue_cast_events(ev_start: Any, ev_end: Any, ev_stream: Any) -> None:
    """Queue a per-cast event pair for the deferred post-forward read."""
    if ev_start is None or ev_end is None:
        return
    with _CAST_LOCK:
        if len(_cast_pending_events) >= _pending_event_capacity():
            return
        _cast_pending_events.append((ev_start, ev_end, ev_stream))


def resolve_pending_cast_events() -> None:
    """Read every queued per-cast event pair (call ONCE after the single
    post-forward synchronize).  Each pair's stream is re-checked against the
    current stream; a mismatch means the events could not have completed on
    this stream and the value is discarded (never fabricated).  Aggregates
    into the account; the queue is drained.  Never raises.
    """
    if not _ENABLED:
        return
    pairs: list[tuple[Any, Any, Any]] = []
    with _CAST_LOCK:
        pairs = list(_cast_pending_events)
        _cast_pending_events.clear()
    if not pairs:
        return
    try:
        import torch as _t

        cur_stream = _t.cuda.current_stream() if _t.cuda.is_available() else None
    except Exception:
        cur_stream = None
    total_ms = 0.0
    for ev_start, ev_end, ev_stream in pairs:
        try:
            if cur_stream is None or ev_stream is None or cur_stream != ev_stream:
                continue
            total_ms += float(ev_start.elapsed_time(ev_end))
        except Exception:
            continue
    if total_ms:
        with _CAST_LOCK:
            _cast_account["gpu_event_ms"] += total_ms


def _module_label(module: Any) -> str:
    """Short stable label for a cast source module (``<path>.<attr>``)."""
    try:
        prefix = _module_path_prefix(module)
        attr = ""
        for name in ("weight", "bias"):
            if getattr(module, name, None) is not None:
                attr = f".{name}"
                break
        return f"{prefix}{attr}"
    except Exception:
        return "?"


def _cast_sample_limit() -> int:
    try:
        return max(1, int(os.environ.get(_E31_CAST_SAMPLE_LIMIT, "1024")))
    except Exception:
        return 1024


def _install_cast_wrapper(owner: Any, attr: str, kind: str) -> str:
    """Wrap one comfy cast entry point with correct arg parsing + event pairs."""
    if not _ENABLED:
        return "gated_off"
    try:
        original = getattr(owner, attr, None)
        if not callable(original):
            return "unavailable"
        if getattr(original, _SENTINEL_CAST, False):
            return "already"

        @functools_wraps(original)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            if not _ENABLED:
                return original(*args, **kwargs)
            start_ns = time.monotonic_ns()
            start_wall = time.perf_counter()
            # Parse the REAL signatures:
            #   cast_bias_weight(s, input=None, dtype=None, device=None, ...)
            #   cast_to(weight, dtype=None, device=None, ...)
            #   cast_to_device(tensor, device, dtype, ...)
            s = args[0] if args else None
            is_module = hasattr(s, "weight") or hasattr(s, "bias") or hasattr(s, "comfy_cast_weights")
            if kind == "cast_bias_weight" and is_module:
                # First arg is the module; the cast source is its weight.
                source = getattr(s, "weight", None)
                bias_source = getattr(s, "bias", None)
                dest_dtype = None
                if len(args) >= 2:
                    _in = args[1]
                    if isinstance(_in, torch_Tensor()):
                        dest_dtype = _in.dtype
                elif "dtype" in kwargs:
                    dest_dtype = kwargs["dtype"]
            else:
                source = args[0] if args else None
                dest_dtype = None
                if len(args) >= 2:
                    dest_dtype = args[1]
                elif "dtype" in kwargs:
                    dest_dtype = kwargs["dtype"]
            ev_start = None
            ev_end = None
            ev_stream = None
            try:
                import torch as _t

                if _t.cuda.is_available():
                    ev_stream = _t.cuda.current_stream()
                    ev_start = _t.cuda.Event(enable_timing=True)
                    ev_end = _t.cuda.Event(enable_timing=True)
                    ev_start.record(ev_stream)
            except Exception:
                ev_start = ev_end = ev_stream = None
            result: Any = None
            error: BaseException | None = None
            try:
                result = original(*args, **kwargs)
            except BaseException as _exc:
                error = _exc
                raise
            finally:
                end_ns = time.monotonic_ns()
                end_wall = time.perf_counter()
                if ev_end is not None and ev_stream is not None:
                    try:
                        import torch as _t2

                        ev_end.record(ev_stream)
                        # NO per-call synchronize and NO elapsed_time read
                        # here: the pair is queued and resolved after the
                        # single post-forward sync in
                        # ForwardTimer.end()/resolve_pending_cast_events().
                        _queue_cast_events(ev_start, ev_end, ev_stream)
                    except Exception:
                        pass
                # NEVER return from this finally (that would swallow a
                # propagating exception); the recording below only runs when
                # the original call succeeded.
                if error is None:
                    # cast_bias_weight returns (weight, bias) OR, with
                    # offloadable=True, (weight, bias, offload_stream).
                    # Record each returned tensor separately so weight vs
                    # bias accounting matches the real conversion count —
                    # the third element is never a bias.
                    if kind == "cast_bias_weight" and isinstance(result, tuple):
                        _w_res = result[0]
                        _b_res = result[1] if len(result) >= 2 else None
                        _w_src = getattr(s, "weight", None) if is_module else None
                        _b_src = getattr(s, "bias", None) if is_module else None
                        _record_cast(
                            kind="cast_bias_weight",
                            source=_w_src,
                            result=_w_res,
                            dest_dtype=dest_dtype,
                            host_wall_ms=(end_wall - start_wall) * 1000.0,
                            gpu_event_ms=None,
                            wall_ms=(end_ns - start_ns) / 1_000_000,
                            role="weight",
                            module=s if is_module else None,
                        )
                        if _b_src is not None and _b_res is not None:
                            _record_cast(
                                kind="cast_bias_weight",
                                source=_b_src,
                                result=_b_res,
                                dest_dtype=dest_dtype,
                                host_wall_ms=0.0,
                                gpu_event_ms=None,
                                wall_ms=0.0,
                                role="bias",
                                module=s if is_module else None,
                            )
                    else:
                        _record_cast(
                            kind=kind,
                            source=source,
                            result=result,
                            dest_dtype=dest_dtype,
                            host_wall_ms=(end_wall - start_wall) * 1000.0,
                            gpu_event_ms=None,
                            wall_ms=(end_ns - start_ns) / 1_000_000,
                            role=None,
                            module=s if is_module else None,
                        )
            return result

        setattr(wrapper, _SENTINEL_CAST, True)
        setattr(owner, attr, wrapper)
        return "installed"
    except Exception as exc:
        return f"error:{type(exc).__name__}:{str(exc)[:120]}"


def torch_Tensor() -> type:
    """Return ``torch.Tensor`` (imported lazily; never at module import)."""
    import torch

    return torch.Tensor


def _record_cast(
    *,
    kind: str,
    source: Any,
    result: Any,
    dest_dtype: Any,
    host_wall_ms: float,
    gpu_event_ms: float | None,
    wall_ms: float,
    role: str | None = None,
    module: Any = None,
) -> None:
    """Aggregate one cast call into the account + bounded sample ring."""
    classification, evidence = classify_cast(source, result)
    is_bias = role == "bias"
    src_dtype = str(getattr(source, "dtype", "unknown"))
    dst_facts = _tensor_facts(result[0] if isinstance(result, tuple) else result)
    dst_dtype = dst_facts.get("dtype", "unknown")
    label = _module_label(module) if module is not None else None
    with _CAST_LOCK:
        if label:
            _cast_account["module_paths"][label] = (
                _cast_account["module_paths"].get(label, 0) + 1
            )
        if is_bias:
            _cast_account["bias_casts"] += 1
            if len(_cast_account["first_bias_shapes"]) < 8:
                try:
                    _cast_account["first_bias_shapes"].append(str(getattr(source, "shape", ())))
                except Exception:
                    pass
        elif kind == "cast_bias_weight":
            _cast_account["weight_casts"] += 1
            if len(_cast_account["first_weight_shapes"]) < 8:
                try:
                    _cast_account["first_weight_shapes"].append(str(getattr(source, "shape", ())))
                except Exception:
                    pass
        else:
            _cast_account["other_casts"] += 1
        _cast_account["classifications"][classification] = (
            _cast_account["classifications"].get(classification, 0) + 1
        )
        _cast_account["source_dtypes"][src_dtype] = (
            _cast_account["source_dtypes"].get(src_dtype, 0) + 1
        )
        _cast_account["dest_dtypes"][dst_dtype] = (
            _cast_account["dest_dtypes"].get(dst_dtype, 0) + 1
        )
        _cast_account["host_wall_ms"] += host_wall_ms
        if classification == REAL_CONVERSION:
            _cast_account["real_conversions"] += 1
            _bytes = dst_facts.get("bytes") or 0
            _cast_account["real_conversion_bytes"] += _bytes
        elif classification == NOOP_SAME_STORAGE:
            _cast_account["same_storage_noops"] += 1
        elif classification in (REAL_COPY_NO_DTYPE_CHANGE,):
            _cast_account["new_allocations"] += 1
        sample = {
            "kind": kind,
            "classification": classification,
            "reason": evidence.get("reason"),
            "source_dtype": src_dtype,
            "dest_dtype": dst_dtype,
            "source_bytes": evidence.get("source", {}).get("bytes"),
            "dest_bytes": evidence.get("dest", {}).get("bytes"),
            "host_wall_ms": round(host_wall_ms, 3),
            "gpu_event_ms": None,
            "module": label,
        }
        _cast_samples.append(sample)


def install_cast_forensics(comfy_ops: Any, model_management: Any) -> dict[str, Any]:
    """Install the corrected cast wrappers (default OFF → no-op).

    Wraps ``comfy.ops.cast_bias_weight``, ``comfy.ops.cast_to`` and
    ``comfy.model_management.cast_to`` / ``cast_to_device``.  Returns
    per-attribute install status; never mutates call semantics.
    """
    result: dict[str, Any] = {"enabled": _ENABLED, "installed": {}}
    if not _ENABLED:
        return result
    targets = (
        ("cast_bias_weight", "cast_bias_weight"),
        ("cast_to", "cast_to"),
        ("cast_to_device", "cast_to_device"),
    )
    for attr, kind in targets:
        owner = None
        for candidate in (comfy_ops, model_management):
            if candidate is not None and callable(getattr(candidate, attr, None)):
                owner = candidate
                break
        if owner is None:
            result["installed"][attr] = "unavailable"
            continue
        result["installed"][attr] = _install_cast_wrapper(owner, attr, kind)
    return result


def cast_forensics_summary() -> dict[str, Any]:
    """JSON-safe copy of the E31 cast account (never raises)."""
    with _CAST_LOCK:
        return {
            "weight_casts": int(_cast_account.get("weight_casts", 0)),
            "bias_casts": int(_cast_account.get("bias_casts", 0)),
            "other_casts": int(_cast_account.get("other_casts", 0)),
            "classifications": dict(_cast_account.get("classifications", {})),
            "real_conversions": int(_cast_account.get("real_conversions", 0)),
            "real_conversion_bytes": int(_cast_account.get("real_conversion_bytes", 0)),
            "same_storage_noops": int(_cast_account.get("same_storage_noops", 0)),
            "new_allocations": int(_cast_account.get("new_allocations", 0)),
            "host_wall_ms": round(float(_cast_account.get("host_wall_ms", 0.0)), 3),
            "gpu_event_ms": round(float(_cast_account.get("gpu_event_ms", 0.0)), 3),
            "source_dtypes": dict(_cast_account.get("source_dtypes", {})),
            "dest_dtypes": dict(_cast_account.get("dest_dtypes", {})),
            "first_weight_shapes": list(_cast_account.get("first_weight_shapes", [])),
            "first_bias_shapes": list(_cast_account.get("first_bias_shapes", [])),
            "module_paths": dict(_cast_account.get("module_paths", {})),
            "pending_event_pairs": len(_cast_pending_events),
        }


def emit_cast_summary_ledger(mono_ns: int | None = None) -> None:
    """Push the current cast summary onto the canonical ledger axis.

    No-op when the E31 gate is off or the ledger is unavailable.  Emits the
    ``clip_forward_cast_summary`` event carrying the aggregated counts and
    classification totals (per-call evidence stays in the bounded ring, never
    on the ledger).
    """
    if not _ENABLED:
        return
    try:
        summary = cast_forensics_summary()
        emit_ledger_event(
            "clip_forward_cast_summary",
            mono_ns=mono_ns,
            weight_casts=summary["weight_casts"],
            bias_casts=summary["bias_casts"],
            other_casts=summary["other_casts"],
            real_conversions=summary["real_conversions"],
            real_conversion_bytes=summary["real_conversion_bytes"],
            same_storage_noops=summary["same_storage_noops"],
            new_allocations=summary["new_allocations"],
            host_wall_ms=summary["host_wall_ms"],
            gpu_event_ms=summary["gpu_event_ms"],
            source_dtypes=summary["source_dtypes"],
            dest_dtypes=summary["dest_dtypes"],
        )
    except Exception:
        pass


def cast_sample_evidence(limit: int = 64) -> list[dict[str, Any]]:
    """Return the most recent bounded per-call cast evidence (never raises)."""
    with _CAST_LOCK:
        return list(_cast_samples)[-max(1, min(limit, 4096)):]


def reset_cast_forensics() -> None:
    with _CAST_LOCK:
        _cast_account.update({
            "weight_casts": 0,
            "bias_casts": 0,
            "other_casts": 0,
            "classifications": {},
            "real_conversions": 0,
            "real_conversion_bytes": 0,
            "same_storage_noops": 0,
            "new_allocations": 0,
            "host_wall_ms": 0.0,
            "gpu_event_ms": 0.0,
            "source_dtypes": {},
            "dest_dtypes": {},
            "first_weight_shapes": [],
            "first_bias_shapes": [],
            "module_paths": {},
        })
        _cast_samples.clear()
        _cast_pending_events.clear()


def e31_enabled() -> bool:
    return _ENABLED


def e31_profile_enabled() -> bool:
    return _PROFILE_ENABLED


# ── Phase 5: opt-in one-shot forward profiler (explicit, default OFF) ─────

class ForwardProfiler:
    """Bracket one forward with torch.profiler (one-shot, explicit).

    Usage::

        with ForwardProfiler() as prof:
            forward(...)
        record = prof.record()   # JSON-safe aggregate + sorted op table

    Default OFF; never enabled in production.  When CUDA/GPU is available the
    profiler uses ``activities=[CPU, CUDA]`` and exports the key table.
    """

    def __init__(self, enabled: bool | None = None) -> None:
        self._enabled = _PROFILE_ENABLED if enabled is None else enabled
        self._prof: Any = None
        self._record: dict[str, Any] = {"enabled": self._enabled}

    def __enter__(self) -> "ForwardProfiler":
        if not self._enabled:
            return self
        try:
            import torch

            activities = [torch.profiler.ProfilerActivity.CPU]
            if torch.cuda.is_available():
                activities.append(torch.profiler.ProfilerActivity.CUDA)
            self._prof = torch.profiler.profile(
                activities=activities,
                record_shapes=False,
                with_stack=False,
            )
            self._prof.__enter__()
            emit_ledger_event("clip_profiler_start", mono_ns=time.monotonic_ns())
        except Exception as exc:
            self._record["error"] = f"{type(exc).__name__}:{str(exc)[:160]}"
            self._prof = None
        return self

    def __exit__(self, *exc_info: Any) -> None:
        if self._prof is not None:
            try:
                self._prof.__exit__(*exc_info)
            except Exception:
                pass

    def record(self) -> dict[str, Any]:
        if self._prof is None:
            self._record["status"] = "not_run" if self._record.get("error") is None else "error"
            return self._record
        try:
            import torch

            self._record["status"] = "ok"
            table = self._prof.key_averages().table(sort_by="cuda_time_total", row_limit=40)
            self._record["key_table"] = str(table)
            totals = self._prof.key_averages()
            cpu_total = 0.0
            cuda_total = 0.0
            ops: list[dict[str, Any]] = []
            for row in totals:
                cpu_ms = float(getattr(row, "self_cpu_time_total", 0) or 0) / 1000.0
                cuda_ms = float(getattr(row, "cuda_time_total", 0) or 0) / 1000.0
                ops.append({
                    "key": str(row.key),
                    "count": int(row.count),
                    "cpu_ms": round(cpu_ms, 3),
                    "cuda_ms": round(cuda_ms, 3),
                })
                cpu_total += float(getattr(row, "self_cpu_time_total", 0) or 0)
                cuda_total += float(getattr(row, "cuda_time_total", 0) or 0)
            ops.sort(key=lambda r: -(r["cuda_ms"] + r["cpu_ms"]))
            self._record["op_count"] = len(ops)
            self._record["cpu_self_total_ms"] = round(cpu_total / 1000.0, 3)
            self._record["cuda_self_total_ms"] = round(cuda_total / 1000.0, 3)
            self._record["ops_top"] = ops[:40]
            emit_ledger_event(
                "clip_profiler_end",
                mono_ns=time.monotonic_ns(),
                status=self._record["status"],
                op_count=self._record["op_count"],
                cpu_self_total_ms=self._record["cpu_self_total_ms"],
                cuda_self_total_ms=self._record["cuda_self_total_ms"],
            )
        except Exception as exc:
            self._record["status"] = "error"
            self._record["error"] = f"{type(exc).__name__}:{str(exc)[:160]}"
        return self._record


def functools_wraps(original: Callable[..., Any]) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    try:
        import functools

        return functools.wraps(original)
    except Exception:
        def _identity(fn: Callable[..., Any]) -> Callable[..., Any]:
            return fn

        return _identity
