"""V2 Batch D8 — get_model wall-time forensics harness (isolated, local-only).

Zero-spend root-cause investigation: explain what ``config.get_model`` is
actually doing during the ~2-3 s Worker-A meta-construction wall observed in
the D6 remote run (wall ~2981 ms, thread CPU ~410 ms).

This tool:

1. Synthesizes a header-faithful ZImage (dim=3840, 32 layers) meta state dict
   (the real local checkpoint is a 0-byte Modal placeholder), derives the
   model config through the SAME ComfyUI detection path production uses
   (``comfy.model_detection.model_config_from_unet``), and drives the SAME
   ``config.get_model(meta_sd, "")`` call inside ``torch.no_grad()`` +
   ``torch.device("meta")``.
2. Builds a DISJOINT span accounting tree inside get_model (wall + current
   thread CPU per span) plus nested module-init per-class attribution and GC
   callbacks, mirroring the production ``COMFYMODAL_V2_UNET_FORENSICS``
   technique without touching production files.
3. Measures first-vs-steady-state behavior and controlled factor experiments
   (GIL contention, IO worker, torch threadpool, gc/allocator pre-trim,
   config reuse, input_types_warm-style concurrency).

All instrumentation is process-local: production functions are patched
temporarily and restored in ``finally``.  No production file is edited.
No Modal deploy/request.  No GPU requirement (meta construction is CPU-only;
CUDA probes are exercised only if present).

Usage:
    python tools/v2_d8_get_model_forensics.py [--iters N] [--quick]
                                               [--json PATH] [--no-experiments]

Exit code 0 on success.  Writes JSON results to --json (default
V2_BATCH_D8_get_model_bench.json at repo root).
"""

from __future__ import annotations

import argparse
import gc
import json
import os
import sys
import tempfile
import threading
import time
from typing import Any, Callable, Optional

_COMFY_ROOT = r"C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI"
if _COMFY_ROOT not in sys.path:
    sys.path.insert(0, _COMFY_ROOT)
# The script runs from tools/; cwd is not on sys.path for scripts, so expose
# the repo root (comfymodal_runtime lives there) explicitly.
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

try:
    import torch
    import comfy.model_detection  # noqa: F401
    import comfy.model_base  # noqa: F401
    import comfy.model_management  # noqa: F401
    import comfy.ops  # noqa: F401
    _HAS_COMFY = True
except Exception as _exc:  # pragma: no cover
    _HAS_COMFY = False
    _COMFY_IMPORT_ERROR = f"{type(_exc).__name__}: {_exc}"

try:
    import psutil
    _HAS_PSUTIL = True
except Exception:  # pragma: no cover
    _HAS_PSUTIL = False

_NS_PER_MS = 1_000_000.0


# ── Synthetic ZImage state dict (header-faithful) ──────────────────────────


def synthetic_zimage_header(*, dim: int = 3840, n_layers: int = 32,
                            n_refiner_layers: int = 2,
                            cap_feat_dim: int = 5120,
                            n_heads: int = 30, n_kv_heads: int = 30,
                            in_channels: int = 4, patch_size: int = 2,
                            dtype: str = "BF16",
                            ffn_hidden: Optional[int] = None) -> dict:
    """Synthetic safetensors-style header (shape/dtype only) that
    ``detect_unet_config`` classifies as ZImage (dim=3840 branch).  Mirrors
    the real z_image_turbo_bf16 key layout (unprefixed keys)."""
    if ffn_hidden is None:
        multiple_of = 256
        ffn_hidden = multiple_of * int((dim * (8.0 / 3.0) + multiple_of - 1)
                                       // multiple_of)
    head_dim = dim // n_heads
    qkv_out = (n_heads + n_kv_heads + n_kv_heads) * head_dim
    header: dict[str, Any] = {}

    def _add(key: str, shape: list[int], dt: str = dtype) -> None:
        header[key] = {"dtype": dt, "shape": shape,
                       "data_offsets": [0, 0]}

    def _block_keys(prefix: str, modulation: bool) -> None:
        _add(f"{prefix}.attention.qkv.weight", [qkv_out, dim])
        _add(f"{prefix}.attention.out.weight", [dim, dim])
        _add(f"{prefix}.attention.q_norm.weight", [head_dim])
        _add(f"{prefix}.attention.k_norm.weight", [head_dim])
        _add(f"{prefix}.feed_forward.w1.weight", [ffn_hidden, dim])
        _add(f"{prefix}.feed_forward.w2.weight", [dim, ffn_hidden])
        _add(f"{prefix}.feed_forward.w3.weight", [ffn_hidden, dim])
        _add(f"{prefix}.attention_norm1.weight", [dim])
        _add(f"{prefix}.ffn_norm1.weight", [dim])
        _add(f"{prefix}.attention_norm2.weight", [dim])
        _add(f"{prefix}.ffn_norm2.weight", [dim])
        if modulation:
            _add(f"{prefix}.adaLN_modulation.0.weight", [4 * dim, 256])
            _add(f"{prefix}.adaLN_modulation.0.bias", [4 * dim])

    _add("x_embedder.weight", [dim, patch_size * patch_size * in_channels])
    _add("x_embedder.bias", [dim])
    for i in range(n_refiner_layers):
        _block_keys(f"noise_refiner.{i}", modulation=True)
    for i in range(n_refiner_layers):
        _block_keys(f"context_refiner.{i}", modulation=False)
    _add("t_embedder.linear_1.weight", [min(dim, 1024), 256])
    _add("t_embedder.linear_1.bias", [min(dim, 1024)])
    _add("t_embedder.linear_2.weight", [min(dim, 1024), min(dim, 1024)])
    _add("t_embedder.linear_2.bias", [min(dim, 1024)])
    _add("t_embedder.mlp.1.weight", [256, min(dim, 1024)])
    _add("t_embedder.mlp.1.bias", [256])
    _add("cap_embedder.0.weight", [dim, cap_feat_dim])
    _add("cap_embedder.1.weight", [dim, cap_feat_dim])
    _add("cap_embedder.1.bias", [dim])
    for i in range(n_layers):
        _block_keys(f"layers.{i}", modulation=True)
    _add("final_layer.linear.weight", [patch_size * patch_size * in_channels, dim])
    _add("final_layer.linear.bias", [patch_size * patch_size * in_channels])
    _add("final_layer.adaLN_modulation.0.weight", [dim, 256])
    _add("final_layer.adaLN_modulation.0.bias", [dim])
    return header


def header_to_meta_sd(header: dict, *, probe_tensor: Optional[torch.Tensor] = None,
                      probe_key: str = "layers.30.ffn_norm1.weight") -> dict:
    """meta-device state dict (mirrors mp._c6_build_meta_sd) with an optional
    injected REAL CPU probe tensor so detect_unet_config's allow_fp16 std
    probe can run (mirrors the C8 test injection)."""
    _map = {
        "BF16": torch.bfloat16, "F16": torch.float16, "F32": torch.float32,
        "F64": torch.float64, "I64": torch.int64, "I32": torch.int32,
        "U8": torch.uint8, "U16": torch.uint16, "U32": torch.uint32,
    }
    sd: dict[str, Any] = {}
    for key, info in header.items():
        if key == "__metadata__":
            continue
        dt = _map.get(str(info.get("dtype", "")))
        shape = info.get("shape")
        if dt is None or not shape:
            continue
        try:
            sd[key] = torch.empty(shape, dtype=dt, device="meta")
        except Exception:
            continue
    if probe_tensor is not None and probe_key in header:
        sd[probe_key] = probe_tensor
    return sd


def derive_config(meta_sd: dict, *, allow_fp16: bool = True
                  ) -> tuple[Any, dict[str, Any]]:
    """Derive the ZImage model config exactly like production
    (``_ring_derive_config`` minus the file reads): detection, config class
    construction, value probe, unet_dtype/manual_cast, set_inference_dtype.
    Returns (config, diagnostics)."""
    diag: dict[str, Any] = {}
    _t0 = time.perf_counter_ns()
    _cfg_fn = comfy.model_detection.model_config_from_unet
    config = _cfg_fn(meta_sd, "", metadata=None)
    diag["detect_ms"] = round((time.perf_counter_ns() - _t0) / _NS_PER_MS, 3)
    if config is None:
        raise RuntimeError("model_config_from_unet returned None")
    # Value probe result → unet_config allow_fp16 (mirrors _ring_derive_config).
    _uc = getattr(config, "unet_config", None)
    if isinstance(_uc, dict):
        _uc["allow_fp16"] = bool(allow_fp16)
    # unet_dtype / manual_cast / set_inference_dtype (mirrors production).
    try:
        from comfy.utils import calculate_parameters, weight_dtype
        from comfy.model_management import (unet_dtype, unet_manual_cast,
                                            unet_offload_device)
        _t1 = time.perf_counter_ns()
        _params = calculate_parameters(meta_sd)
        _wd = weight_dtype(meta_sd)
        _supported = list(getattr(config, "supported_inference_dtypes", None) or [])
        _udt = unet_dtype(model_params=_params, supported_dtypes=_supported,
                          weight_dtype=_wd)
        _load_device = None
        try:
            _load_device = unet_offload_device()
        except Exception:
            _load_device = None
        _mc = None
        try:
            _mc = unet_manual_cast(_udt, _load_device, _supported)
        except Exception:
            _mc = None
        _set = getattr(config, "set_inference_dtype", None)
        if callable(_set):
            try:
                _set(_udt, _mc)
            except Exception:
                pass
        diag["dtype_resolve_ms"] = round(
            (time.perf_counter_ns() - _t1) / _NS_PER_MS, 3)
        diag["unet_dtype"] = str(_udt)
    except Exception as _exc:
        diag["dtype_resolve_error"] = f"{type(_exc).__name__}: {_exc}"
    return config, diag


# ── Disjoint span accounting ───────────────────────────────────────────────


class Span:
    """Wall + thread-CPU span.  Children are disjoint by construction: each
    production function is entered exactly once per get_model and timed at
    the function boundary.  Residual = parent - sum(children) is computed by
    the caller."""

    __slots__ = ("name", "wall_ns", "cpu_ns", "children", "extra", "_t0", "_c0")

    def __init__(self, name: str):
        self.name = name
        self.wall_ns = 0
        self.cpu_ns = 0
        self.children: list["Span"] = []
        self.extra: dict[str, Any] = {}
        self._t0 = 0
        self._c0 = None

    def start(self) -> None:
        self._t0 = time.perf_counter_ns()
        try:
            self._c0 = time.thread_time()
        except Exception:
            self._c0 = None

    def stop(self) -> None:
        self.wall_ns = max(0, time.perf_counter_ns() - self._t0)
        if self._c0 is not None:
            try:
                self.cpu_ns = max(0.0, (time.thread_time() - self._c0) * 1e9)
            except Exception:
                self.cpu_ns = 0.0

    def child(self, name: str) -> "Span":
        c = Span(name)
        self.children.append(c)
        return c

    def wall_ms(self) -> float:
        return round(self.wall_ns / _NS_PER_MS, 3)

    def cpu_ms(self) -> float:
        return round(self.cpu_ns / _NS_PER_MS, 3)

    def to_dict(self, *, depth: int = 0) -> dict[str, Any]:
        out: dict[str, Any] = {
            "name": self.name,
            "wall_ms": self.wall_ms(),
            "cpu_ms": self.cpu_ms(),
        }
        if self.extra:
            out["extra"] = self.extra
        if self.children:
            out["children"] = [c.to_dict(depth=depth + 1) for c in self.children]
            out["children_wall_sum_ms"] = round(
                sum(c.wall_ns for c in self.children) / _NS_PER_MS, 3)
        return out

    def check_disjoint(self, errors: list[str]) -> None:
        for c in self.children:
            if c.wall_ns > self.wall_ns:
                errors.append(f"{c.name} wall {c.wall_ms()} > parent {self.wall_ms()}")
            if c.wall_ns < 0 or c.cpu_ns < 0:
                errors.append(f"{c.name} negative time")
            # Windows thread_time granularity is ~15.6 ms (1/64 s quantum);
            # per-child CPU deltas below that quantize to full quanta, so only
            # flag gross violations (> 2 quanta).  Total-call CPU is measured
            # on a longer interval and is the trustworthy number.
            if c.cpu_ns > c.wall_ns + 32_000_000:
                errors.append(f"{c.name} cpu {c.cpu_ms()} > wall {c.wall_ms()}")
            c.check_disjoint(errors)


class _Timer:
    __slots__ = ("span",)

    def __init__(self, span: Span):
        self.span = span

    def __enter__(self) -> Span:
        self.span.start()
        return self.span

    def __exit__(self, *exc: Any) -> None:
        self.span.stop()


# ── Telemetry sampler ──────────────────────────────────────────────────────


class _Sampler:
    """Light background sampler: process CPU ticks, RSS, native thread count,
    active python threads, gc count.  Runs only during a timed window."""

    def __init__(self) -> None:
        self._stop = threading.Event()
        self._samples: list[dict[str, Any]] = []
        self._proc = psutil.Process() if _HAS_PSUTIL else None
        self._thread = None

    def start(self) -> None:
        if self._proc is None:
            return
        self._stop.clear()
        self._samples = []
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self) -> None:
        prev = self._proc.cpu_times()
        while not self._stop.wait(0.015):
            try:
                cur = self._proc.cpu_times()
                rss = self._proc.memory_info().rss
                nthreads = len(self._proc.threads())
                self._samples.append({
                    "t_ms": round(time.perf_counter() * 1000, 1),
                    "proc_cpu_ms": round(
                        ((cur.user + cur.system) - (prev.user + prev.system)) * 1000, 2),
                    "rss_mb": round(rss / (1024 * 1024), 2),
                    "native_threads": nthreads,
                    "py_threads": threading.active_count(),
                    "gc_count": gc.get_count(),
                })
                prev = cur
            except Exception:
                pass

    def stop(self) -> list[dict[str, Any]]:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
        return self._samples


# ── Instrumented get_model ─────────────────────────────────────────────────


class _Instrumenter:
    """Temporarily wraps production callables with disjoint span timers.

    Patches (all restored in ``restore()``):
      comfy.ops.pick_operations                     -> ops_selection
      comfy.ldm.lumina.model.NextDiT.__init__       -> diffusion_model_construct
      comfy.model_management.archive_model_dtypes   -> archive_dtypes
      comfy.model_base.model_sampling               -> model_sampling_construct
      torch.nn.Module.__init__                      -> nested per-class aggregation
      gc callbacks                                  -> GC wall accounting
    """

    def __init__(self, root: Span, *, module_attribution: bool = True):
        self._root = root
        self._orig: list[tuple[Any, str, Any]] = []
        self._gc_cb = None
        self._gc_state: dict[str, Any] = {"total_ns": 0, "count": 0, "cur": None,
                                          "t0": None}
        self._module_agg: dict[str, Any] = {}
        self._module_count = 0
        self._first_op_ns = None
        self._install(module_attribution=module_attribution)

    # ── installation ──
    def _wrap(self, owner: Any, attr: str, span_name: str,
              factory: Optional[Callable] = None) -> None:
        if owner is None:
            return
        orig = getattr(owner, attr, None)
        if not callable(orig):
            return
        self._orig.append((owner, attr, orig))
        span = self._root.child(span_name)

        def wrapper(*args: Any, **kwargs: Any) -> Any:
            with _Timer(span):
                return orig(*args, **kwargs)

        if factory is not None:
            factory(orig, wrapper)
        try:
            setattr(owner, attr, wrapper)
        except Exception:
            self._orig.pop()

    def _install(self, *, module_attribution: bool) -> None:
        self._wrap(comfy.ops, "pick_operations", "ops_selection")
        try:
            import comfy.ldm.lumina.model as _lum
            self._wrap(_lum.NextDiT, "__init__", "diffusion_model_construct")
        except Exception:
            pass
        self._wrap(comfy.model_management, "archive_model_dtypes",
                   "archive_dtypes")
        self._wrap(comfy.model_base, "model_sampling",
                   "model_sampling_construct")
        if module_attribution:
            self._install_module_init()
        self._install_gc()

    def _install_module_init(self) -> None:
        orig = torch.nn.Module.__init__
        self._orig.append((torch.nn.Module, "__init__", orig))
        # NOTE: capture the aggregators as locals; inside the patch ``self``
        # is the partially-constructed module, so ``self.<attr>`` would
        # resolve through its __getattr__ and raise AttributeError.
        agg = self._module_agg
        counter = self

        def forensic_init(module_self: Any, *a: Any, **k: Any) -> None:
            t0 = time.perf_counter_ns()
            try:
                orig(module_self, *a, **k)
            finally:
                name = type(module_self).__name__
                entry = agg.setdefault(
                    name, {"count": 0, "wall_ms": 0.0})
                entry["count"] += 1
                entry["wall_ms"] += (time.perf_counter_ns() - t0) / _NS_PER_MS
                counter._module_count += 1

        torch.nn.Module.__init__ = forensic_init

    def _install_gc(self) -> None:
        state = self._gc_state

        def cb(phase: str, info: Any) -> None:
            now = time.perf_counter_ns()
            if phase == "start":
                if state["cur"] is None:
                    state["cur"] = now
            elif phase == "stop" and state["cur"] is not None:
                state["total_ns"] += now - state["cur"]
                state["cur"] = None
                state["count"] += 1

        self._gc_cb = cb
        gc.callbacks.append(cb)

    # ── restore ──
    def restore(self) -> None:
        for owner, attr, orig in reversed(self._orig):
            try:
                setattr(owner, attr, orig)
            except Exception:
                pass
        self._orig = []
        if self._gc_cb is not None:
            try:
                gc.callbacks.remove(self._gc_cb)
            except Exception:
                pass
            self._gc_cb = None

    # ── results ──
    def module_attribution(self) -> dict[str, Any]:
        return {
            "by_class": self._module_agg,
            "total_wall_ms": round(
                sum(e["wall_ms"] for e in self._module_agg.values()), 3),
            "count": self._module_count,
        }


def instrumented_get_model(config: Any, meta_sd: dict) -> dict[str, Any]:
    """One instrumented ``config.get_model(meta_sd, "")`` under the production
    meta context, with disjoint spans + telemetry.  Never mutates production
    state on exit.  Returns a results dict."""
    out: dict[str, Any] = {}
    root = Span("get_model_total")
    _inst = _Instrumenter(root)
    sampler = _Sampler()
    _t0 = time.perf_counter_ns()
    _cpu0 = None
    try:
        _cpu0 = time.thread_time()
    except Exception:
        pass
    _proc_cpu0 = None
    if _HAS_PSUTIL:
        try:
            _t = psutil.Process().cpu_times()
            _proc_cpu0 = _t.user + _t.system
        except Exception:
            pass
    try:
        sampler.start()
        root.start()
        with torch.no_grad(), torch.device("meta"):
            model = config.get_model(meta_sd, "")
        root.stop()
        out["model"] = model
    finally:
        try:
            root.stop()
        except Exception:
            pass
        samples = sampler.stop()
        _inst.restore()
    out["wall_ms"] = round((time.perf_counter_ns() - _t0) / _NS_PER_MS, 3)
    if _cpu0 is not None:
        try:
            out["thread_cpu_ms"] = round(
                (time.thread_time() - _cpu0) * 1000, 3)
        except Exception:
            out["thread_cpu_ms"] = None
    if _proc_cpu0 is not None and _HAS_PSUTIL:
        try:
            _t = psutil.Process().cpu_times()
            out["process_cpu_ms"] = round(
                (_t.user + _t.system - _proc_cpu0) * 1000, 3)
        except Exception:
            out["process_cpu_ms"] = None
    # Disjoint accounting.
    errors: list[str] = []
    root.check_disjoint(errors)
    out["tree"] = root.to_dict()
    out["tree_disjoint_errors"] = errors
    # Residual = total wall - sum(top-level children wall).
    _ch_sum = sum(c.wall_ns for c in root.children)
    out["residual_wall_ms"] = round(
        max(0.0, (root.wall_ns - _ch_sum) / _NS_PER_MS), 3)
    out["children_wall_sum_ms"] = round(_ch_sum / _NS_PER_MS, 3)
    out["accounted_percent"] = round(
        100.0 * _ch_sum / root.wall_ns, 1) if root.wall_ns > 0 else None
    # Nested attribution (NOT part of the disjoint tree).
    out["module_attribution"] = _inst.module_attribution()
    out["gc_wall_ms"] = round(_inst._gc_state["total_ns"] / _NS_PER_MS, 3)
    out["gc_count"] = _inst._gc_state["count"]
    # Sampler summary.
    if samples:
        out["sampler"] = {
            "n": len(samples),
            "max_proc_cpu_ms_per_15ms": round(
                max(s["proc_cpu_ms"] for s in samples), 2),
            "sum_proc_cpu_ms": round(
                sum(s["proc_cpu_ms"] for s in samples), 2),
            "max_native_threads": max(s["native_threads"] for s in samples),
            "min_native_threads": min(s["native_threads"] for s in samples),
            "rss_delta_mb": round(
                samples[-1]["rss_mb"] - samples[0]["rss_mb"], 2),
            "max_rss_mb": max(s["rss_mb"] for s in samples),
        }
    else:
        out["sampler"] = None
    return out


def model_inventory(model: Any) -> dict[str, Any]:
    """Count modules, parameters, buffers, tensors + logical bytes."""
    params = list(model.parameters())
    bufs = list(model.buffers())
    n_modules = len(list(model.modules()))
    logical_bytes = sum(
        int(p.numel()) * max(1, p.element_size()) for p in params)
    buf_bytes = sum(
        int(b.numel()) * max(1, b.element_size()) for b in bufs)
    all_meta = all(getattr(p, "is_meta", False) for p in params)
    buf_meta = all(getattr(b, "is_meta", False) for b in bufs)
    return {
        "modules": n_modules,
        "parameters": len(params),
        "param_numel": sum(int(p.numel()) for p in params),
        "param_logical_bytes": logical_bytes,
        "param_physical_bytes": 0 if all_meta else logical_bytes,
        "param_all_meta": all_meta,
        "buffers": len(bufs),
        "buffer_numel": sum(int(b.numel()) for b in bufs),
        "buffer_all_meta": buf_meta,
        "tensor_objects": len(params) + len(bufs),
    }


# ── Post-get_model production steps (mirrored) ─────────────────────────────


def post_construction_steps(model: Any, config: Any) -> dict[str, Any]:
    """Mirror _fs_meta_construct post-steps: param validation + model_sampling
    poison detect/repair.  Returns per-step wall ms."""
    out: dict[str, Any] = {}
    _t = time.perf_counter_ns()
    _params = list(model.parameters())
    out["param_validate_ms"] = round(
        (time.perf_counter_ns() - _t) / _NS_PER_MS, 3)
    _t = time.perf_counter_ns()
    _sampling = getattr(model, "model_sampling", None)
    _poisoned = collect_meta_tensors(_sampling) if _sampling is not None else []
    out["sampling_detect_ms"] = round(
        (time.perf_counter_ns() - _t) / _NS_PER_MS, 3)
    out["sampling_poisoned"] = len(_poisoned)
    if _poisoned:
        _t = time.perf_counter_ns()
        model.model_sampling = comfy.model_base.model_sampling(
            model.model_config, model.model_type)
        out["sampling_fix_ms"] = round(
            (time.perf_counter_ns() - _t) / _NS_PER_MS, 3)
        out["sampling_fixed"] = True
    else:
        out["sampling_fix_ms"] = 0.0
        out["sampling_fixed"] = False
    return out


def collect_meta_tensors(module: Any) -> list:
    """Mirror model_preload.collect_meta_tensors semantics (standalone copy)."""
    found = []
    for t in list(getattr(module, "parameters", lambda: [])()) \
            + list(getattr(module, "buffers", lambda: [])()):
        if getattr(t, "is_meta", False):
            found.append(t)
    return found


# ── Benchmark: first-vs-steady ─────────────────────────────────────────────


def run_serial_benchmark(config_factory: Callable[[], Any],
                         meta_sd: dict, iters: int) -> dict[str, Any]:
    """Repeated construction, fresh config each iteration (production shape).
    Reports first vs steady-state separately."""
    rows: list[dict[str, Any]] = []
    for i in range(iters):
        config, _diag = config_factory()
        r = instrumented_get_model(config, meta_sd)
        r["index"] = i
        rows.append(r)
    steady = rows[1:]
    med = lambda key: _median([r[key] for r in steady if r.get(key) is not None])
    return {
        "iters": iters,
        "first_wall_ms": rows[0]["wall_ms"],
        "first_thread_cpu_ms": rows[0].get("thread_cpu_ms"),
        "first_process_cpu_ms": rows[0].get("process_cpu_ms"),
        "steady_median_wall_ms": med("wall_ms"),
        "steady_median_thread_cpu_ms": med("thread_cpu_ms"),
        "steady_min_wall_ms": min(r["wall_ms"] for r in steady),
        "steady_max_wall_ms": max(r["wall_ms"] for r in steady),
        "steady_median_cpu_ms": med("thread_cpu_ms"),
        "steady_median_accounted_percent": med("accounted_percent"),
        "first_vs_steady_ratio": round(
            rows[0]["wall_ms"] / med("wall_ms"), 2) if med("wall_ms") else None,
        "rows": rows,
    }


def _median(values: list[float]) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    n = len(s)
    if n % 2 == 1:
        return s[n // 2]
    return (s[n // 2 - 1] + s[n // 2]) / 2.0


# ── Factor experiments ─────────────────────────────────────────────────────


def _gil_worker(stop: threading.Event) -> None:
    """GIL-heavy Python worker (dict/list/str churn)."""
    i = 0
    acc: dict[str, int] = {}
    while not stop.is_set():
        i += 1
        acc[str(i % 97)] = (i * 7919) % 104729
        if i % 500 == 0:
            _ = sorted(acc.items())[:10]
            acc.clear()


def _io_worker(stop: threading.Event, path: str) -> None:
    """Disk IO worker: 256 KiB chunked reads (releases GIL during syscalls)."""
    try:
        with open(path, "rb") as f:
            while not stop.is_set():
                _ = f.read(262144)
                if not _:
                    f.seek(0)
    except Exception:
        pass


def _make_io_file(size_mb: int = 96) -> str:
    td = tempfile.mkdtemp(prefix="v2_d8_io_")
    path = os.path.join(td, "blob.bin")
    with open(path, "wb") as f:
        chunk = os.urandom(1024 * 1024)
        for _ in range(size_mb):
            f.write(chunk)
    return path


_WARM_CLASS_TYPES = [
    "CheckpointLoaderSimple", "UNETLoader", "CLIPLoader", "VAELoader",
    "LoraLoaderModelOnly", "CLIPTextEncode", "EmptyLatentImage", "KSampler",
    "VAEDecode", "VAEEncode", "SaveImage", "LoadImage", "PreviewImage",
    "CLIPVisionLoader", "CLIPVisionEncode", "ConditioningCombine",
    "ConditioningSetArea", "ConditioningZeroOut", "ConditioningAverage",
    "ConditioningSetMask", "ControlNetLoader", "ControlNetApplyAdvanced",
    "LatentUpscale", "LatentScale", "ImageScale", "ImageUpscaleWithModel",
    "LatentFromBatch", "LatentBatch", "RepeatLatentBatch", "LatentBlend",
    "LoraLoader", "ModelMergeSimple",
]


def _warm_worker(stop: threading.Event) -> dict[str, Any]:
    """input_types_warm-style concurrent worker (D8-supporting experiment).

    Mirrors modal_app's Task B: warm_classes_input_types over a synthetic
    prompt of ~31 distinct node classes.  Uses the LIVE repo helper
    (execution_warm.warm_classes_input_types); independent of D9's changes.
    """
    res: dict[str, Any] = {"count": 0, "ms": 0.0, "error": None}
    try:
        from comfymodal_runtime.execution_warm import warm_classes_input_types
        prompt = {
            str(i): {"class_type": ct}
            for i, ct in enumerate(_WARM_CLASS_TYPES)
        }
        t0 = time.perf_counter()
        count, ms = warm_classes_input_types(prompt)
        res["count"] = count
        res["ms"] = ms
        res["wall_ms"] = round((time.perf_counter() - t0) * 1000, 1)
    except Exception as exc:
        res["error"] = f"{type(exc).__name__}: {exc}"
    return res


def run_experiment(name: str, config_factory: Callable[[], Any],
                   meta_sd: dict, iters: int,
                   setup: Optional[Callable[[], None]] = None,
                   worker: Optional[Callable[[threading.Event], None]] = None,
                   worker_kwargs: Optional[dict] = None) -> dict[str, Any]:
    """One factor experiment: N constructions under the given condition."""
    worker_kwargs = worker_kwargs or {}
    rows = []
    worker_results: dict[str, Any] = {}
    for i in range(iters):
        _w = None
        _stop = threading.Event()
        if worker is not None:
            _w = threading.Thread(
                target=worker, args=(_stop,), kwargs=worker_kwargs,
                daemon=True)
            _w.start()
        try:
            if setup is not None:
                setup()
            config, _diag = config_factory()
            r = instrumented_get_model(config, meta_sd)
            r["index"] = i
            rows.append(r)
        finally:
            if _w is not None:
                _stop.set()
                _w.join(timeout=5.0)
    # If a worker records a result, capture it (single-shot workers only).
    return {
        "name": name,
        "iters": iters,
        "median_wall_ms": _median([r["wall_ms"] for r in rows]),
        "median_thread_cpu_ms": _median(
            [r["thread_cpu_ms"] for r in rows if r.get("thread_cpu_ms") is not None]),
        "min_wall_ms": min(r["wall_ms"] for r in rows),
        "max_wall_ms": max(r["wall_ms"] for r in rows),
        "median_process_cpu_ms": _median(
            [r["process_cpu_ms"] for r in rows if r.get("process_cpu_ms") is not None]),
        "median_accounted_percent": _median(
            [r["accounted_percent"] for r in rows if r.get("accounted_percent") is not None]),
        "rows": rows,
    }


def _config_factory(meta_sd: dict, *, reuse: Optional[Any] = None):
    if reuse is not None:
        def _factory():
            return reuse, {}
        return _factory

    def _factory():
        return derive_config(meta_sd)
    return _factory


# ── Main ───────────────────────────────────────────────────────────────────


def _env_snapshot() -> dict[str, Any]:
    out: dict[str, Any] = {
        "torch_version": torch.__version__,
        "torch_threads": torch.get_num_threads(),
        "torch_interop_threads": torch.get_num_interop_threads(),
        "cuda_available": bool(torch.cuda.is_available()),
        "cuda_device_count": int(torch.cuda.device_count()) if torch.cuda.is_available() else 0,
        "processors": os.cpu_count(),
        "python": sys.version.split()[0],
        "platform": sys.platform,
    }
    if _HAS_PSUTIL:
        try:
            p = psutil.Process()
            out["native_threads_at_start"] = len(p.threads())
            out["rss_start_mb"] = round(p.memory_info().rss / (1024 * 1024), 2)
        except Exception:
            pass
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--iters", type=int, default=5, help="iterations per arm")
    ap.add_argument("--quick", action="store_true",
                    help="short run (iters=3, skip heavy arms)")
    ap.add_argument("--json", type=str,
                    default=os.path.join(
                        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "V2_BATCH_D8_get_model_bench.json"),
                    help="JSON output path")
    ap.add_argument("--no-experiments", action="store_true",
                    help="only the serial first-vs-steady benchmark")
    args = ap.parse_args()

    if not _HAS_COMFY:
        print(f"[v2_d8] comfy unavailable: {_COMFY_IMPORT_ERROR}", flush=True)
        return 2
    iters = 3 if args.quick else args.iters

    print("[v2_d8] building synthetic ZImage meta sd...", flush=True)
    header = synthetic_zimage_header()
    probe = (torch.randn(3840, dtype=torch.float32) * 0.1)  # std 0.1 < 0.42
    meta_sd = header_to_meta_sd(header, probe_tensor=probe)
    print(f"[v2_d8] synthetic header keys: {len(header)}", flush=True)

    env = _env_snapshot()
    print(f"[v2_d8] env: {json.dumps(env)}", flush=True)

    results: dict[str, Any] = {
        "batch": "D8",
        "env": env,
        "synthetic": {
            "header_keys": len(header),
            "n_layers": 32,
            "dim": 3840,
        },
        "arms": {},
    }

    # 0. Config derivation check (mirrors production detection).
    config, diag = derive_config(meta_sd)
    results["config"] = {
        "class": type(config).__name__,
        "unet_config": {k: str(v) for k, v in getattr(config, "unet_config", {}).items()},
        "diag": diag,
    }
    print(f"[v2_d8] config class: {type(config).__name__}", flush=True)
    if type(config).__name__ != "ZImage":
        print("[v2_d8] ERROR: expected ZImage config", flush=True)
        return 2

    # 1. First-vs-steady serial benchmark (fresh config each iteration).
    print(f"[v2_d8] serial benchmark ({iters} iters)...", flush=True)
    serial = run_serial_benchmark(
        _config_factory(meta_sd), meta_sd, iters=iters)
    results["arms"]["serial_first_vs_steady"] = serial
    _first = serial["first_wall_ms"]
    _steady = serial["steady_median_wall_ms"]
    print(f"[v2_d8] first={_first} ms steady_median={_steady} ms "
          f"ratio={serial.get('first_vs_steady_ratio')}", flush=True)

    # Inventory from the first construction.
    _m = serial["rows"][0]["model"]
    results["inventory"] = model_inventory(_m)
    print(f"[v2_d8] inventory: {json.dumps(results['inventory'])}", flush=True)

    # Deep look at the first row's tree + attribution.
    results["first_row"] = {
        k: serial["rows"][0][k] for k in (
            "wall_ms", "thread_cpu_ms", "process_cpu_ms", "tree",
            "residual_wall_ms", "children_wall_sum_ms", "accounted_percent",
            "module_attribution", "gc_wall_ms", "gc_count", "sampler",
            "tree_disjoint_errors",
        )
    }

    # Post-construction production steps (mirrored).
    post = post_construction_steps(_m, config)
    results["post_construction_steps"] = post
    print(f"[v2_d8] post steps: {json.dumps(post)}", flush=True)

    if args.no_experiments:
        results["experiments"] = {}
        _dump(results, args.json)
        return 0

    # 2. Factor experiments.
    arms: dict[str, dict[str, Any]] = {}

    arms["baseline_serial"] = run_experiment(
        "baseline_serial", _config_factory(meta_sd), meta_sd, iters=iters)

    if not args.quick:
        # B: GIL-heavy Python worker concurrently.
        arms["gil_worker_concurrent"] = run_experiment(
            "gil_worker_concurrent", _config_factory(meta_sd), meta_sd,
            iters=iters, worker=_gil_worker)

        # C: disk IO worker concurrently.
        _io_path = _make_io_file()
        try:
            arms["io_worker_concurrent"] = run_experiment(
                "io_worker_concurrent", _config_factory(meta_sd), meta_sd,
                iters=iters, worker=_io_worker, worker_kwargs={"path": _io_path})
        finally:
            try:
                os.remove(_io_path)
            except Exception:
                pass

        # D: torch threadpool variations (construction is not parallel, but
        # threadpool init / interop spins can still bite on first use).
        # NOTE: set_num_interop_threads is illegal after parallel work has
        # started; only intra-op threads are varied here.
        def _set_threads_1() -> None:
            torch.set_num_threads(1)

        def _set_threads_max() -> None:
            try:
                torch.set_num_threads(max(1, os.cpu_count() or 1))
            except Exception:
                pass

        arms["torch_threads_1"] = run_experiment(
            "torch_threads_1", _config_factory(meta_sd), meta_sd,
            iters=iters, setup=_set_threads_1)
        try:
            torch.set_num_threads(env["torch_threads"])
        except Exception:
            pass
        arms["torch_threads_default"] = run_experiment(
            "torch_threads_default", _config_factory(meta_sd), meta_sd,
            iters=iters)

        # F: gc.collect before construction.
        arms["gc_before"] = run_experiment(
            "gc_before", _config_factory(meta_sd), meta_sd,
            iters=iters, setup=lambda: gc.collect())

        # G: allocator trim (cuda empty_cache only when CUDA present).
        def _alloc_trim() -> None:
            gc.collect()
            if torch.cuda.is_available():
                try:
                    torch.cuda.empty_cache()
                except Exception:
                    pass

        arms["allocator_trim"] = run_experiment(
            "allocator_trim", _config_factory(meta_sd), meta_sd,
            iters=iters, setup=_alloc_trim)

        # H: config reuse (immutable structure reused across constructions).
        _reuse_config, _ = derive_config(meta_sd)
        arms["config_reuse"] = run_experiment(
            "config_reuse", _config_factory(meta_sd, reuse=_reuse_config),
            meta_sd, iters=iters)

        # I: input_types_warm-style concurrency (D8-supporting experiment).
        # The warm worker is single-shot (like production: one warm thread per
        # request) — so this arm runs ONE concurrent warm pass across the
        # first construction and reports its own wall.
        _warm_result: dict[str, Any] = {}

        def _warm_once(stop: threading.Event) -> None:
            _warm_result.update(_warm_worker(stop))

        arms["input_types_warm_concurrent"] = run_experiment(
            "input_types_warm_concurrent", _config_factory(meta_sd), meta_sd,
            iters=min(3, iters), worker=_warm_once)
        arms["input_types_warm_concurrent"]["warm_worker"] = _warm_result

        # J: cold-imports shape — construction in a FRESH interpreter is
        # measured by the first-iteration delta; here we additionally report
        # the comfy import wall once.
        t0 = time.perf_counter()
        _ = derive_config(meta_sd)
        results["config_derive_warm_ms"] = round(
            (time.perf_counter() - t0) * 1000, 3)

    results["experiments"] = arms

    # 3. Summary table.
    print("\n=== V2 D8 experiment summary ===", flush=True)
    print(f"{'arm':<34} {'median wall ms':>14} {'median cpu ms':>13} "
          f"{'min':>9} {'max':>9} {'acct %':>7}", flush=True)
    for name, arm in arms.items():
        print(
            f"{name:<34} {arm['median_wall_ms']:>14.1f} "
            f"{arm['median_thread_cpu_ms']:>13.1f} "
            f"{arm['min_wall_ms']:>9.1f} {arm['max_wall_ms']:>9.1f} "
            f"{arm['median_accounted_percent'] or 0.0:>7.1f}",
            flush=True)

    _dump(results, args.json)
    print(f"\n[v2_d8] JSON written to {args.json}", flush=True)
    return 0


def _dump(results: dict[str, Any], path: str) -> None:
    try:
        # Drop live model objects (not JSON-serializable).
        _strip_models(results)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, default=str)
    except Exception as exc:
        print(f"[v2_d8] JSON dump failed: {exc}", flush=True)


def _strip_models(obj: Any) -> None:
    if isinstance(obj, dict):
        for k in list(obj.keys()):
            if k == "model":
                del obj[k]
            else:
                _strip_models(obj[k])
    elif isinstance(obj, list):
        for item in obj:
            _strip_models(item)


if __name__ == "__main__":
    sys.exit(main())
