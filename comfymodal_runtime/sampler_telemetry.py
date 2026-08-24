"""R44H2 — lightweight sampler boundary telemetry (timestamp-only).

Closes the R44G3 telemetry gaps WITHOUT touching sampler numerics, CUDA
synchronization behavior, or any model path:

* true ``sampling_start`` capture and durable persistence support
  (the authoritative SAMPLER_SAMPLE wrapper emission stays the primary
  source; this module is the request-scoped durable store + backfill
  resolver so ``pre_sampler_stages.sampling_start_monotonic_ns`` is
  populated from the TRUE event whenever it exists, never from the first
  progress callback);
* per-step callback ticks (compact array, negligible overhead for the
  8-step cohort);
* sampler post-loop tail measurement (last progress callback -> sampler
  node return) with cheap host-timer sub-timings for the R44G3-suspected
  internal work: ``gc.collect()``, ``copy.deepcopy(state_info_out)``,
  ``Tensor.cpu()`` transfers, aggregated over the sampler-node window;
* ``load_models_gpu`` mono start/end stamps + caller classification
  (enriches the existing CPU-owner records; also captures the VAE-decode
  call that the sampling-start cutoff previously dropped entirely).

Design constraints honored:
* NO torch.cuda.synchronize / empty_cache / filesystem scans /
  model introspection / large serialization are introduced.  A ``.cpu()``
  is timed by wrapping the actual call (it synchronizes implicitly by
  itself); no second sync is ever added.
* All patches are request-window-bounded, idempotent, fail-safe
  (original behavior restored in ``finally``), and disabled wholesale
  when ``COMFYMODAL_V2_SAMPLER_TELEMETRY=0``.
* Pure stdlib except an optional guarded ``torch`` import for the
  ``.cpu()`` byte accounting.

This module NEVER changes model output, sampler scheduling, or resource
shape: every hook is observational.
"""

from __future__ import annotations

import copy as _copymod
import gc as _gc
import os
import threading
import time
from typing import Any

_ENABLED = os.environ.get("COMFYMODAL_V2_SAMPLER_TELEMETRY", "1") != "0"

_LOCK = threading.RLock()

# Max per-step ticks retained (8-step cohort ≪ bound; protects memory on
# pathological step counts).
_MAX_TICKS = 4096
# Max load_models_gpu stamp records per request.
_MAX_LMG_RECORDS = 64

# R44I2 — direct, clone-independent class-level boundary seams.
DIRECT_SAMPLING_START_SOURCE = "direct_sampler_call_boundary"
DEFERRED_EMISSION_FLAG = "deferred_boundary"


def _now() -> tuple[int, int]:
    """(monotonic_ns, perf_counter_ns) captured as close together as possible."""
    return time.monotonic_ns(), time.perf_counter_ns()


class _SamplerTelemetry:
    """Request-scoped recorder.  One instance per process; reset per request."""

    __slots__ = (
        "request_id", "node_id", "node_class", "steps",
        "node_entry_mono_ns", "node_entry_perf_ns",
        "sampling_start_mono_ns", "sampling_start_wall_ns",
        "sampling_start_source", "sampling_end_mono_ns",
        "first_eval_mono_ns",
        "sigmas_len", "latent_dtype", "latent_device", "default_dtype",
        "ss_hook_installed", "ss_hook_invoked",
        "fe_hook_installed", "fe_hook_invoked",
        "ticks", "last_tick_perf_ns", "last_tick_mono_ns",
        "tail", "lmg_records", "_pending_lmg", "_emitted",
        "_patches_installed", "_gc_total_ns", "_gc_count",
        "_deepcopy_total_ns", "_deepcopy_count",
        "_cpu_total_ns", "_cpu_bytes", "_cpu_count",
        "_orig_gc_collect", "_orig_deepcopy", "_orig_tensor_cpu",
    )

    def __init__(self) -> None:
        self.reset("")

    def reset(self, request_id: str) -> None:
        self.request_id = str(request_id or "")
        self.node_id = ""
        self.node_class = ""
        self.steps = 0
        self.node_entry_mono_ns = 0
        self.node_entry_perf_ns = 0
        self.sampling_start_mono_ns = 0
        self.sampling_start_wall_ns = 0
        self.sampling_start_source = ""
        self.sampling_end_mono_ns = 0
        self.first_eval_mono_ns = 0
        self.sigmas_len: int | None = None
        self.latent_dtype = ""
        self.latent_device = ""
        self.default_dtype = ""
        self.ss_hook_installed = False
        self.ss_hook_invoked = False
        self.fe_hook_installed = False
        self.fe_hook_invoked = False
        self.ticks: list[dict[str, Any]] = []
        self.last_tick_perf_ns = 0
        self.last_tick_mono_ns = 0
        self.tail: dict[str, Any] | None = None
        self.lmg_records: list[dict[str, Any]] = []
        self._pending_lmg: dict[int, int] = {}
        self._emitted = False
        self._patches_installed = False
        self._gc_total_ns = 0
        self._gc_count = 0
        self._deepcopy_total_ns = 0
        self._deepcopy_count = 0
        self._cpu_total_ns = 0
        self._cpu_bytes = 0
        self._cpu_count = 0
        self._orig_gc_collect = None
        self._orig_deepcopy = None
        self._orig_tensor_cpu = None


_TELEMETRY = _SamplerTelemetry()


def enabled() -> bool:
    return _ENABLED


def reset_request(request_id: str = "") -> None:
    """Start a fresh request scope (never removes installed patches twice)."""
    if not _ENABLED:
        return
    with _LOCK:
        _TELEMETRY._remove_subtiming_patches()
        _TELEMETRY.reset(request_id)
        try:
            install_direct_boundaries()
        except Exception:
            pass


# ── boundary notes ────────────────────────────────────────────────────────


def note_sampler_node_entry(node_id: Any = "", node_class: Any = "") -> None:
    """Record the sampler NODE entry (comfyapp profiled-node begin)."""
    if not _ENABLED:
        return
    mono, perf = _now()
    with _LOCK:
        if _TELEMETRY.node_entry_mono_ns:
            return
        _TELEMETRY.node_id = str(node_id or "")
        _TELEMETRY.node_class = str(node_class or "")
        _TELEMETRY.node_entry_mono_ns = mono
        _TELEMETRY.node_entry_perf_ns = perf
        try:
            install_direct_boundaries()
        except Exception:
            pass


def note_sampling_start(
    mono_ns: int,
    wall_unix_ns: int = 0,
    *,
    node_id: Any = "",
    steps: int = 0,
    request_id: str = "",
    source: str = "authoritative_wrapper",
    sigmas_len: int | None = None,
    latent_dtype: str = "",
    latent_device: str = "",
    default_dtype: str = "",
) -> None:
    """Record the TRUE sampling start (SAMPLER_SAMPLE wrapper emit point)."""
    if not _ENABLED:
        return
    with _LOCK:
        if _TELEMETRY.sampling_start_mono_ns:
            return
        _TELEMETRY.sampling_start_mono_ns = int(mono_ns)
        _TELEMETRY.sampling_start_wall_ns = int(wall_unix_ns or 0)
        _TELEMETRY.sampling_start_source = str(source)
        _TELEMETRY.steps = int(steps or 0)
        _TELEMETRY.sigmas_len = sigmas_len
        _TELEMETRY.latent_dtype = str(latent_dtype or "")
        _TELEMETRY.latent_device = str(latent_device or "")
        _TELEMETRY.default_dtype = str(default_dtype or "")
        if request_id and not _TELEMETRY.request_id:
            _TELEMETRY.request_id = str(request_id)
        if node_id and not _TELEMETRY.node_id:
            _TELEMETRY.node_id = str(node_id)


def note_sampling_end(mono_ns: int) -> None:
    if not _ENABLED:
        return
    with _LOCK:
        if not _TELEMETRY.sampling_end_mono_ns:
            _TELEMETRY.sampling_end_mono_ns = int(mono_ns)


def note_first_eval(mono_ns: int) -> None:
    """Record the first underlying denoiser evaluation start (probe-fed)."""
    if not _ENABLED:
        return
    with _LOCK:
        if not _TELEMETRY.first_eval_mono_ns:
            _TELEMETRY.first_eval_mono_ns = int(mono_ns)


def note_progress_tick(
    step: Any = None,
    progress: Any = None,
    *,
    source: str = "wrapper_callback",
) -> None:
    """Record one per-step callback tick (compact; bounded)."""
    if not _ENABLED:
        return
    mono, perf = _now()
    try:
        step_i = int(step) if step is not None else len(_TELEMETRY.ticks)
    except (TypeError, ValueError):
        step_i = len(_TELEMETRY.ticks)
    try:
        prog = float(progress) if progress is not None else None
    except (TypeError, ValueError):
        prog = None
    with _LOCK:
        if len(_TELEMETRY.ticks) >= _MAX_TICKS:
            return
        _TELEMETRY.ticks.append({
            "step": step_i,
            "mono_ns": mono,
            "perf_ns": perf,
            "progress": prog,
            "source": str(source),
        })
        _TELEMETRY.last_tick_perf_ns = perf
        _TELEMETRY.last_tick_mono_ns = mono


# ── load_models_gpu seam ──────────────────────────────────────────────────

_SAMPLER_CLASS_MARKERS = ("Sampler",)
_VAE_CALLER_MARKERS = ("VAEDecode", "VAELoader")


def classify_caller(node_class: Any = "") -> str:
    nc = str(node_class or "")
    if any(m in nc for m in _VAE_CALLER_MARKERS):
        return "vae_decode"
    if any(m in nc for m in _SAMPLER_CLASS_MARKERS):
        return "sampler_prep"
    return nc or "unknown"


def note_load_models_gpu_enter(models: Any, node_class: Any = "") -> int:
    """Called at ``load_models_gpu`` entry.

    Returns the monotonic entry stamp (0 when disabled).  When the caller
    is the sampler's own internal model-management call (inside
    SharkSampler.main, before ``guider.sample``), this is ALSO the last
    reliable seam that holds the exact patcher/diffusion-model about to
    be sampled: the authoritative SAMPLER_SAMPLE timing wrapper and the
    first-forward probe are (re-)installed here idempotently, restoring
    the R44E-lost ``sampling_start`` durability without touching loading
    or adoption behavior.
    """
    if not _ENABLED:
        return 0
    mono, _perf = _now()
    caller = classify_caller(node_class)
    with _LOCK:
        if len(_TELEMETRY.lmg_records) < _MAX_LMG_RECORDS:
            _TELEMETRY.lmg_records.append({
                "caller": caller,
                "start_mono_ns": mono,
                "end_mono_ns": 0,
                "wall_ms": 0.0,
                "roles": "",
            })
        _pending = mono
    if caller == "sampler_prep":
        _install_sampling_instrumentation(models)
        _TELEMETRY._install_subtiming_patches()
        try:
            install_direct_boundaries()
        except Exception:
            pass
    return _pending


def note_load_models_gpu_exit(entry_mono_ns: int, roles: Any = "") -> None:
    if not _ENABLED or not entry_mono_ns:
        return
    mono, _perf = _now()
    wall_ms = round((time.perf_counter_ns() - _pending_perf(entry_mono_ns)) / 1e6, 3)
    with _LOCK:
        for rec in reversed(_TELEMETRY.lmg_records):
            if rec.get("start_mono_ns") == entry_mono_ns and not rec.get("end_mono_ns"):
                rec["end_mono_ns"] = mono
                rec["wall_ms"] = wall_ms
                if roles:
                    rec["roles"] = str(roles)
                break


def _pending_perf(entry_mono_ns: int) -> float:
    # perf/mono share the epoch offset per process; recovering perf from a
    # stored mono stamp is only used for a display wall — derive via a fresh
    # pair delta so no cross-domain math can drift beyond microseconds.
    mono_now, perf_now = _now()
    del mono_now
    return perf_now - (mono_now - entry_mono_ns)


def _install_sampling_instrumentation(models: Any) -> None:
    """Idempotent telemetry (re-)install on the patcher being sampled."""
    try:
        seq = list(models) if models else []
    except TypeError:
        return
    for m in seq:
        try:
            from comfymodal_runtime.runtime_executor import (
                ensure_sampling_timing_wrapper,
            )
            ensure_sampling_timing_wrapper(m)
        except Exception:
            pass
        try:
            from comfymodal_runtime.unet_forward_probe import (
                register_unet_forward_probe,
            )
            register_unet_forward_probe(m, source="sampler_lmg_seam")
        except Exception:
            pass


# ── direct class-level boundary seams (clone-independent) ─────────────────


def build_direct_sampling_start_wrapper(orig_sample: Any) -> Any:
    def _direct_sampling_start(self: Any, *args: Any, **kwargs: Any) -> Any:
        if _ENABLED:
            t = _TELEMETRY
            if t.request_id:
                t.ss_hook_invoked = True
                if not t.sampling_start_mono_ns:
                    mono = time.monotonic_ns()
                    wall = time.time_ns()
                    sigmas = args[3] if len(args) > 3 else kwargs.get("sigmas")
                    latent = args[1] if len(args) > 1 else kwargs.get("latent_image")
                    steps = 0
                    sigmas_len = None
                    try:
                        if sigmas is not None and hasattr(sigmas, "__len__"):
                            sigmas_len = int(len(sigmas)); steps = max(0, sigmas_len - 1)
                    except Exception:
                        pass
                    note_sampling_start(mono, wall,
                        node_id=t.node_id, steps=steps, request_id=t.request_id,
                        source=DIRECT_SAMPLING_START_SOURCE, sigmas_len=sigmas_len,
                        latent_dtype=str(getattr(latent, "dtype", "") or ""),
                        latent_device=str(getattr(latent, "device", "") or ""))
        return orig_sample(self, *args, **kwargs)
    return _direct_sampling_start


def build_direct_first_eval_wrapper(orig_apply_model: Any) -> Any:
    def _direct_first_eval(self: Any, *args: Any, **kwargs: Any) -> Any:
        if _ENABLED:
            t = _TELEMETRY
            if t.request_id and not t.first_eval_mono_ns:
                t.fe_hook_invoked = True
                mono = time.monotonic_ns()
                with _LOCK:
                    if not t.first_eval_mono_ns:
                        t.first_eval_mono_ns = int(mono)
            elif t.request_id:
                t.fe_hook_invoked = True
        return orig_apply_model(self, *args, **kwargs)
    return _direct_first_eval


_direct_state: dict[str, Any] = {
    "ss_orig": None, "ss_wrapped": None, "fe_orig": None, "fe_wrapped": None,
}


def install_direct_boundaries() -> dict[str, bool]:
    status = {"sampling_start": False, "first_eval": False}
    if not _ENABLED:
        return status
    try:
        import comfy.samplers as _cs
        if _direct_state["ss_wrapped"] is None:
            orig = getattr(_cs.CFGGuider, "sample", None)
            if callable(orig):
                wrapped = build_direct_sampling_start_wrapper(orig)
                _cs.CFGGuider.sample = wrapped
                _direct_state["ss_orig"] = orig
                _direct_state["ss_wrapped"] = wrapped
        if _direct_state["ss_wrapped"] is not None:
            _TELEMETRY.ss_hook_installed = True
            status["sampling_start"] = True
    except Exception:
        pass
    try:
        import comfy.model_base as _cmb
        if _direct_state["fe_wrapped"] is None:
            orig = getattr(_cmb.BaseModel, "apply_model", None)
            if callable(orig):
                wrapped = build_direct_first_eval_wrapper(orig)
                _cmb.BaseModel.apply_model = wrapped
                _direct_state["fe_orig"] = orig
                _direct_state["fe_wrapped"] = wrapped
        if _direct_state["fe_wrapped"] is not None:
            _TELEMETRY.fe_hook_installed = True
            status["first_eval"] = True
    except Exception:
        pass
    return status


def remove_direct_boundaries() -> None:
    try:
        import comfy.samplers as _cs
        if _direct_state["ss_orig"] is not None and getattr(_cs.CFGGuider, "sample", None) is _direct_state["ss_wrapped"]:
            _cs.CFGGuider.sample = _direct_state["ss_orig"]
    except Exception:
        pass
    try:
        import comfy.model_base as _cmb
        if _direct_state["fe_orig"] is not None and getattr(_cmb.BaseModel, "apply_model", None) is _direct_state["fe_wrapped"]:
            _cmb.BaseModel.apply_model = _direct_state["fe_orig"]
    except Exception:
        pass
    _direct_state.update(ss_orig=None, ss_wrapped=None, fe_orig=None, fe_wrapped=None)


# ── tail sub-timing patches (window-bounded, fail-safe) ───────────────────


def _install_subtiming_patches(self: "_SamplerTelemetry") -> None:  # type: ignore[misc]
    if not _ENABLED or self._patches_installed:
        return
    self._patches_installed = True

    orig_gc = _gc.collect

    def _timed_gc_collect(gen: Any = None) -> int:  # type: ignore[misc]
        t0 = time.perf_counter_ns()
        try:
            if gen is None:
                return orig_gc()
            return orig_gc(gen)
        finally:
            with _LOCK:
                self._gc_total_ns += time.perf_counter_ns() - t0
                self._gc_count += 1

    orig_dc = _copymod.deepcopy

    def _timed_deepcopy(x: Any, memo: Any = None, _nil: Any = []) -> Any:  # type: ignore[misc]
        t0 = time.perf_counter_ns()
        try:
            return orig_dc(x, memo, _nil)
        finally:
            with _LOCK:
                self._deepcopy_total_ns += time.perf_counter_ns() - t0
                self._deepcopy_count += 1

    self._orig_gc_collect = orig_gc
    self._orig_deepcopy = orig_dc
    _gc.collect = _timed_gc_collect  # type: ignore[assignment]
    _copymod.deepcopy = _timed_deepcopy  # type: ignore[assignment]

    # Tensor.cpu: timed at the actual call (implicit sync belongs to the call
    # itself; NO additional synchronize is added).  Guarded import.
    try:
        import torch as _torch

        orig_cpu = _torch.Tensor.cpu

        def _timed_tensor_cpu(self_t: Any, *a: Any, **kw: Any) -> Any:  # noqa: N805
            t0 = time.perf_counter_ns()
            try:
                return orig_cpu(self_t, *a, **kw)
            finally:
                dt = time.perf_counter_ns() - t0
                try:
                    nbytes = int(self_t.numel()) * int(self_t.element_size())
                except Exception:
                    nbytes = 0
                with _LOCK:
                    self._cpu_total_ns += dt
                    self._cpu_count += 1
                    self._cpu_bytes += nbytes

        self._orig_tensor_cpu = orig_cpu
        _torch.Tensor.cpu = _timed_tensor_cpu  # type: ignore[assignment]
    except Exception:
        self._orig_tensor_cpu = None


def _remove_subtiming_patches(self: "_SamplerTelemetry") -> None:  # type: ignore[misc]
    if not self._patches_installed:
        return
    if self._orig_gc_collect is not None:
        try:
            _gc.collect = self._orig_gc_collect  # type: ignore[assignment]
        except Exception:
            pass
    if self._orig_deepcopy is not None:
        try:
            _copymod.deepcopy = self._orig_deepcopy  # type: ignore[assignment]
        except Exception:
            pass
    if self._orig_tensor_cpu is not None:
        try:
            import torch as _torch

            _torch.Tensor.cpu = self._orig_tensor_cpu  # type: ignore[assignment]
        except Exception:
            pass
    self._patches_installed = False


_SamplerTelemetry._install_subtiming_patches = _install_subtiming_patches  # type: ignore[attr-defined]
_SamplerTelemetry._remove_subtiming_patches = _remove_subtiming_patches  # type: ignore[attr-defined]


# ── tail closure ──────────────────────────────────────────────────────────


def finish_sampler_tail(
    node_return_perf_ns: int,
    node_return_mono_ns: int,
    *,
    output_tensor_count: Any = None,
) -> dict[str, Any] | None:
    """Close the sampler post-loop tail (last progress -> node return).

    Returns the tail record (also retained for the durable emitter).
    Never raises; returns None when there is no tick to anchor the tail.
    """
    if not _ENABLED:
        return None
    with _LOCK:
        t = _TELEMETRY
        t._remove_subtiming_patches()
        if t.tail is not None:
            return t.tail  # idempotent: first close wins
        if not t.last_tick_perf_ns or not node_return_perf_ns:
            return None
        wall_ms = round(max(0, node_return_perf_ns - t.last_tick_perf_ns) / 1e6, 3)
        tail = {
            "start_mono_ns": int(t.last_tick_mono_ns),
            "end_mono_ns": int(node_return_mono_ns),
            "wall_ms": wall_ms,
            "gc_collect_ms": round(t._gc_total_ns / 1e6, 3),
            "gc_collect_count": t._gc_count,
            "state_info_deepcopy_ms": round(t._deepcopy_total_ns / 1e6, 3),
            "state_info_deepcopy_count": t._deepcopy_count,
            "cpu_transfer_wall_ms": round(t._cpu_total_ns / 1e6, 3),
            "cpu_transfer_bytes": int(t._cpu_bytes),
            "cpu_transfer_count": t._cpu_count,
            "output_tensor_count": (
                int(output_tensor_count) if isinstance(output_tensor_count, (int, float)) else None
            ),
            "subtiming_other_ms": round(
                max(
                    0.0,
                    wall_ms
                    - (t._gc_total_ns + t._deepcopy_total_ns + t._cpu_total_ns) / 1e6,
                ),
                3,
            ),
            "node_id": t.node_id,
            "request_id": t.request_id,
        }
        t.tail = tail
        return tail


def snapshot() -> dict[str, Any]:
    """Read-only copy of current boundaries (for backfill/emitters)."""
    with _LOCK:
        t = _TELEMETRY
        return {
            "request_id": t.request_id,
            "node_id": t.node_id,
            "node_class": t.node_class,
            "steps": t.steps,
            "node_entry_mono_ns": t.node_entry_mono_ns,
            "sampling_start_mono_ns": t.sampling_start_mono_ns,
            "sampling_start_wall_ns": t.sampling_start_wall_ns,
            "sampling_start_source": t.sampling_start_source,
            "sampling_end_mono_ns": t.sampling_end_mono_ns,
            "first_eval_mono_ns": t.first_eval_mono_ns,
            "ss_hook_installed": bool(t.ss_hook_installed),
            "ss_hook_invoked": bool(t.ss_hook_invoked),
            "fe_hook_installed": bool(t.fe_hook_installed),
            "fe_hook_invoked": bool(t.fe_hook_invoked),
            "tick_count": len(t.ticks),
            "ticks": list(t.ticks),
            "tail": dict(t.tail) if t.tail else None,
            "lmg_records": [dict(r) for r in t.lmg_records],
        }


def resolve_sampling_start(
    trace_events: Any,
    milestones: Any = None,
) -> tuple[int | None, str]:
    """Resolve the TRUE sampling start for ``pre_sampler_stages`` backfill.

    Priority (never invents a timestamp):
    1. durable ``sampling_start`` trace event (authoritative wrapper)
     → ``("authoritative_wrapper")``
    2. this module's in-memory capture of the same emission
     → ``"wrapper_runtime_store"``
    3. milestone proxy (first progress-class stage boundary), explicitly
     labeled ``"proxy_first_progress"`` — callers must NOT present it as
     the true sampling start.
    Returns ``(monotonic_ns_or_None, source_label)``.
    """
    try:
        for ev in trace_events or []:
            name = getattr(ev, "name", None)
            if name is None and isinstance(ev, dict):
                name = ev.get("name")
            if name == "sampling_start":
                mono = getattr(ev, "monotonic_ns", None)
                if mono is None and isinstance(ev, dict):
                    mono = ev.get("monotonic_ns")
                mono_i = int(mono) if mono else 0
                if mono_i > 0:
                    return mono_i, "authoritative_wrapper"
    except (TypeError, AttributeError):
        pass
    snap_mono = _TELEMETRY.sampling_start_mono_ns
    if snap_mono > 0:
        if str(_TELEMETRY.sampling_start_source) == DIRECT_SAMPLING_START_SOURCE:
            return int(snap_mono), "authoritative_direct_sampler_boundary"
        return int(snap_mono), "wrapper_runtime_store"
    try:
        proxy = (milestones or {}).get("sampler_first_stage_ns") if milestones else None
        if not proxy:
            proxy = (milestones or {}).get("sampler_first_progress_ns") if milestones else None
        proxy_i = int(proxy) if proxy else 0
        if proxy_i > 0:
            return proxy_i, "proxy_first_progress"
    except (TypeError, AttributeError, ValueError):
        pass
    return None, "unavailable"


def subtiming_totals() -> dict[str, float]:
    with _LOCK:
        t = _TELEMETRY
        return {
            "gc_collect_ms": round(t._gc_total_ns / 1e6, 3),
            "gc_collect_count": t._gc_count,
            "state_info_deepcopy_ms": round(t._deepcopy_total_ns / 1e6, 3),
            "state_info_deepcopy_count": t._deepcopy_count,
            "cpu_transfer_wall_ms": round(t._cpu_total_ns / 1e6, 3),
            "cpu_transfer_bytes": int(t._cpu_bytes),
            "cpu_transfer_count": t._cpu_count,
        }


def _trace_has_sampling_start(trace: Any) -> bool:
    try:
        for ev in getattr(trace, "events", None) or []:
            name = getattr(ev, "name", None)
            if name is None and isinstance(ev, dict):
                name = ev.get("name")
            if name == "sampling_start":
                return True
    except Exception:
        pass
    return False


def emit_durable_events(trace: Any) -> int:
    """Persist the R44H2 sampler boundary events onto the request trace.

    Emitted (each only when its evidence exists, timestamp-only):
      ``sampler_prep_phase``       node entry → true sampling start
      ``sampler_first_eval_start`` first underlying denoiser evaluation
      ``sampler_step_ticks``       compact per-step callback array
      ``sampler_tail``             last progress → node return + sub-timings
      ``sampling_start``           deferred authoritative boundary (only when
                                   the trace lacks one)
      ``sampler_telemetry_status`` final hook install/invocation/persistence
                                   status (always emitted)

    Returns the number of events emitted.  Never raises.
    """
    if not _ENABLED or trace is None:
        return 0
    emitted = 0
    try:
        with _LOCK:
            t = _TELEMETRY
            if t._emitted:
                return 0
            t._emitted = True
            node_entry = int(t.node_entry_mono_ns or 0)
            samp_start = int(t.sampling_start_mono_ns or 0)
            first_eval = int(t.first_eval_mono_ns or 0)
            ticks = list(t.ticks)
            tail = dict(t.tail) if t.tail else None
            samp_wall = int(t.sampling_start_wall_ns or 0)
            samp_source = str(t.sampling_start_source or "")
            samp_steps = int(t.steps or 0)
            sigmas_len = t.sigmas_len
            latent_dtype = str(t.latent_dtype or "")
            latent_device = str(t.latent_device or "")
            default_dtype = str(t.default_dtype or "")
            ss_installed = bool(t.ss_hook_installed)
            ss_invoked = bool(t.ss_hook_invoked)
            fe_installed = bool(t.fe_hook_installed)
            fe_invoked = bool(t.fe_hook_invoked)
            lmg_count = len(t.lmg_records)
            meta_common = {
                "node_id": t.node_id,
                "node_class": t.node_class,
                "request_id": t.request_id,
            }
            prep_meta = dict(meta_common)
            prep_meta.update({
                "start_mono_ns": node_entry,
                "end_mono_ns": samp_start,
                "wall_ms": (
                    round((samp_start - node_entry) / 1e6, 3)
                    if node_entry and samp_start and samp_start > node_entry else None
                ),
                "default_dtype": t.default_dtype,
                "sigmas_len": t.sigmas_len,
                "latent_dtype": t.latent_dtype,
                "latent_device": t.latent_device,
                "sampling_start_source": t.sampling_start_source,
            })
        if node_entry and samp_start and samp_start > node_entry:
            trace.emit("sampler_prep_phase", phase="execution", metadata=prep_meta)
            emitted += 1
        if first_eval:
            fe_meta = dict(meta_common)
            fe_meta.update({"mono_ns": first_eval, "step_index": 0})
            trace.emit("sampler_first_eval_start", phase="execution", metadata=fe_meta)
            emitted += 1
        if ticks:
            tk_meta = dict(meta_common)
            tk_meta.update({
                "count": len(ticks),
                "steps": [
                    {"i": tk.get("step"), "mono_ns": tk.get("mono_ns"),
                     "progress": tk.get("progress")}
                    for tk in ticks
                ],
                "sources": sorted({str(tk.get("source")) for tk in ticks}),
            })
            trace.emit("sampler_step_ticks", phase="execution", metadata=tk_meta)
            emitted += 1
        if tail:
            tl_meta = dict(meta_common)
            tl_meta.update(tail)
            trace.emit("sampler_tail", phase="execution", metadata=tl_meta)
            emitted += 1
        if samp_start > 0 and not _trace_has_sampling_start(trace):
            ds_meta = dict(meta_common)
            ds_meta.update({
                "mono_ns": samp_start,
                "wall_unix_ns": samp_wall,
                "source": samp_source or DIRECT_SAMPLING_START_SOURCE,
                "emission": DEFERRED_EMISSION_FLAG,
                "steps": samp_steps,
                "sigmas_len": sigmas_len,
                "latent_dtype": latent_dtype,
                "latent_device": latent_device,
                "default_dtype": default_dtype,
            })
            trace.emit("sampling_start", phase="execution", metadata=ds_meta)
            emitted += 1
        status_meta = dict(meta_common)
        status_meta.update({
            "sampling_start_hook_installed": ss_installed,
            "sampling_start_hook_invoked": ss_invoked,
            "sampling_start_persisted": samp_start > 0,
            "first_eval_hook_installed": fe_installed,
            "first_eval_hook_invoked": fe_invoked,
            "first_eval_persisted": first_eval > 0,
            "tick_count": len(ticks),
            "tail_present": tail is not None,
            "lmg_record_count": lmg_count,
        })
        trace.emit("sampler_telemetry_status", phase="execution", metadata=status_meta)
        emitted += 1
    except Exception:
        pass
    return emitted
