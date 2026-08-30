"""Gated sampling deep profile (Level A + Level B instrumentation).

Implements the gated, reversible, comfyui-modal-owned diagnostic pass
described in ``SAMPLING_DEEP_DECOMPOSITION.md``.

Level A (per sampling step / model evaluation)
  - Reversibly monkeypatches ``comfy.samplers.KSamplerX0Inpaint.__call__`` for
    one sampler invocation (guarded, idempotent, restored in ``finalize``).
  - Records host ``time.monotonic_ns()`` eval start/end for every model call —
    the same steady clock used by the authoritative ``sampling_start`` /
    ``sampling_end`` trace events, so setup/steps/teardown reconcile exactly
    with the event pair (no cross-clock arithmetic).
  - Uses the per-step ComfyUI callback index ``i`` to classify the 8 steps and
    the final callback index 8; the pinned workflow is expected to produce
    16 in-loop evals + 1 final teardown eval (17 total).
  - Produces setup / per-step (pre-model, eval0, gap, eval1, post-model) /
    teardown(final eval) and explicit derived residuals.

Level B (inside a model evaluation)
  - Entirely reversible comfyui-modal-owned ``nn.Module`` forward pre/post
    hooks registered on the diffusion model, its main/context/noise-refiner
    blocks and their submodules (attention, MLP, norms/adaLN) where hookable.
  - Distinguishes CacheDiT compute vs whole-forward skip: block-total
    "compute-marker" hooks on main/refiner blocks fire only on computed
    forwards and are installed in BOTH modes (steps mode stays minimal with no
    category sub-hooks); CacheDiT whole-forward skips never reach the inner
    blocks.  When no inner marker is hookable, evals classify ``unknown``
    rather than a fabricated skip.
  - Reads CacheDiT scalar counters post-sampling (already-imported module
    first, fresh import only as fallback) and cross-checks the expected
    17/10/7 cadence; never touches tensor ``last_result``.
  - Aggregates per-block total / attention / MLP / directly-measured norm /
    derived ``norm_gate_residual`` and derives residuals.  Unhookable
    interleaved tensor ops are never claimed to be directly timed (see the
    artifact ``semantics`` block).

CUDA (optional, blocks mode, CUDA available only)
  - ``torch.cuda.Event`` pairs recorded around GPU-bearing hooked spans only,
    with no inner synchronization.  Terminal events are recorded before the
    executor returns; the single realization (one ``torch.cuda.synchronize``
    + ``elapsed_time``) runs ONLY in the post-boundary diagnostic cleanup
    AFTER the authoritative ``sampling_end`` event — outside the
    ``sampling_start``→``sampling_end`` window.  If a robust post-boundary
    realization cannot be performed, CUDA-event collection is marked
    unavailable with an artifact warning instead of violating the boundary.

Off path
  - ``COMFYMODAL_SAMPLING_DEEP_PROFILE`` default ``off``; invalid values
    normalise to ``off``.  The off path never imports or patches ComfyUI
    sampler/model classes and never adds events or synchronizations.
  - Optionally a file ``/root/comfymodal_runtime_state/sampling_deep_profile.txt``
    (mirrors the existing ``comfyapp.RUNTIME_CONFIG_DIR`` pattern) is read when
    it exists; environment wins otherwise.
"""

from __future__ import annotations

import contextvars
import functools
import importlib
import inspect
import json
import os
import threading
import time
from typing import Any, Callable, Optional

SCHEMA_VERSION = 1
EVENT_NAME = "sampling_deep_profile"

FLAG_ENV = "COMFYMODAL_SAMPLING_DEEP_PROFILE"
# Mirrors comfyapp.RUNTIME_CONFIG_DIR ("/root/comfymodal_runtime_state"); read
# only when the file exists, exactly like comfyapp's _resolve_runtime_flag.
FLAG_FILE = "/root/comfymodal_runtime_state/sampling_deep_profile.txt"

_VALID_LEVELS = frozenset({"off", "steps", "blocks"})
_DEFAULT_LEVEL = "off"

# Pinned-workflow expected cadence: 8 steps x 2 row evals + 1 final teardown
# eval; CacheDiT warmup=3 / skip_interval=2 gives 10 computes / 7 skips.
EXPECTED_EVALS = 17
EXPECTED_CALLBACKS = 9  # indices 0..8
EXPECTED_CACHEDIT = (17, 10, 7)  # calls / computes / skips for the pinned config

# Block submodules to hook in blocks mode, with their category.
_BLOCK_SUBMODULES = {
    "attention": "attention",
    "feed_forward": "mlp",
    "attention_norm1": "norm",
    "attention_norm2": "norm",
    "ffn_norm1": "norm",
    "ffn_norm2": "norm",
    "adaLN_modulation": "norm",
}
# Embedding/output modules hookable on the diffusion model.
_DM_DIRECT_MODULES = (
    ("x_embedder", "embed:x_embedder", "embeddings"),
    ("cap_embedder", "embed:cap_embedder", "embeddings"),
    ("t_embedder", "embed:t_embedder", "embeddings"),
    ("final_layer", "output:final_layer", "output"),
)

_PATCH_MARKER = "_comfymodal_sampling_deep_profile_patched"

# Request/task scoped state; the class-level KSamplerX0Inpaint patch is global
# and guarded by a module lock owned by at most one profile at a time.
_CURRENT_PROFILE: "contextvars.ContextVar[SamplingDeepProfile | None]" = contextvars.ContextVar(
    "comfymodal_sampling_deep_profile", default=None
)

_PATCH_LOCK = threading.Lock()
_PATCH_OWNER: Optional[int] = None  # id(profile) that owns the class patch
_PATCH_ORIGINALS: dict[int, Callable] = {}  # id(cls) -> original __call__
_LAST_PATCHED_CLASS: Optional[type] = None  # for best-effort test cleanup


# ---------------------------------------------------------------------------
# Resolvable seams (tests monkeypatch these)
# ---------------------------------------------------------------------------


def _resolve_ksampler_x0_inpaint() -> Optional[type]:
    """Resolve the ComfyUI sampler wrapper class (lazy, off-path safe)."""
    try:
        import comfy.samplers as _cs  # type: ignore[import-not-found]
        return getattr(_cs, "KSamplerX0Inpaint", None)
    except Exception:
        return None


def _resolve_cuda_module():
    """Resolve ``torch.cuda`` when CUDA is available, else None."""
    try:
        import torch as _torch
        if getattr(_torch, "cuda", None) is not None and _torch.cuda.is_available():
            return _torch.cuda
    except Exception:
        pass
    return None


def _resolve_loaded_cachedit_module() -> Optional[Any]:
    """Return an ALREADY-IMPORTED ComfyUI-CacheDiT.nodes module if one exists.

    Scans a snapshot of ``sys.modules.values()`` (no fresh import) for a module
    whose normalized ``__file__`` contains a directory component exactly equal
    to ``ComfyUI-CacheDiT`` (case-insensitive) and which exposes the
    ``_lightweight_cache_state`` scalar state dict.  This guarantees the loaded
    state wins over a competing fresh import and avoids duplicate module
    instances.  Returns None when no such module is present.
    """
    import sys
    wanted = {"comfyui-cachedit"}
    for mod in tuple(sys.modules.values()):
        if mod is None:
            continue
        namespace = getattr(mod, "__dict__", None)
        if not isinstance(namespace, dict) or "_lightweight_cache_state" not in namespace:
            continue
        f = namespace.get("__file__")
        if not isinstance(f, str) or not f:
            continue
        norm = os.path.normpath(f).replace("\\", "/")
        parts = {p.lower() for p in norm.split("/") if p}
        if wanted & parts:
            return mod
    return None


def _read_cachedit_counters(dm: Any, patcher: Any) -> Optional[dict[str, Any]]:
    """Read CacheDiT lightweight-cache scalar counters post-sampling.

    Discovery order:
      1. an already-imported ``ComfyUI-CacheDiT.nodes`` module found by
         scanning ``sys.modules`` (loaded state wins; no fresh import);
      2. a safe fresh ``importlib.import_module`` fallback when not loaded.

    Reads scalar state only (``enabled`` / ``call_count`` / ``compute_count`` /
    ``skip_count``).  Never touches tensor ``last_result``.  Returns None when
    the CacheDiT module/state is not discoverable; callers report that as a
    warning.
    """
    out: dict[str, Any] = {"discoverable": False, "module_source": "absent"}
    # attached / enabled from the transformer itself.
    if dm is not None:
        try:
            orig = getattr(dm, "_original_forward", None)
            fwd = getattr(dm, "forward", None)
            cfg = getattr(dm, "_cache_dit_config", None)
            out["attached"] = bool(
                orig is not None and fwd is not None and fwd is not orig
            )
            if isinstance(cfg, dict):
                out["config_present"] = True
                if "warmup_steps" in cfg:
                    out["warmup_steps"] = cfg["warmup_steps"]
                if "skip_interval" in cfg:
                    out["skip_interval"] = cfg["skip_interval"]
        except Exception:
            pass
    mod = None
    try:
        mod = _resolve_loaded_cachedit_module()
        if mod is not None:
            out["module_source"] = "loaded"
    except Exception:
        mod = None
    if mod is None:
        try:
            mod = importlib.import_module("ComfyUI-CacheDiT.nodes")
            if mod is not None:
                out["module_source"] = "fresh_import"
        except Exception:
            mod = None
    if mod is not None:
        st = getattr(mod, "_lightweight_cache_state", None)
        if isinstance(st, dict):
            out["discoverable"] = True
            out["enabled"] = bool(st.get("enabled"))
            for key in ("call_count", "compute_count", "skip_count"):
                val = st.get(key)
                if isinstance(val, int):
                    out[key] = val
    # Warmup/skip_interval may also live in the patcher's model_options.
    if patcher is not None:
        try:
            opts = getattr(patcher, "model_options", None) or {}
            cfg = (opts.get("transformer_options") or {}).get("cache_dit_turbo")
            if cfg is not None:
                uw = getattr(cfg, "user_warmup_steps", None)
                si = getattr(cfg, "user_skip_interval", None)
                if isinstance(uw, int):
                    out.setdefault("warmup_steps", uw)
                if isinstance(si, int):
                    out.setdefault("skip_interval", si)
        except Exception:
            pass
    return out


# ---------------------------------------------------------------------------
# Flag resolution
# ---------------------------------------------------------------------------


def _normalize_level(raw: Any) -> str:
    val = str(raw or "").strip().lower()
    return val if val in _VALID_LEVELS else _DEFAULT_LEVEL


def resolve_profile_level() -> str:
    """Resolve the effective profile level (env first, then flag file).

    Invalid values and an absent flag/file normalise to ``off``.
    """
    raw = os.environ.get(FLAG_ENV)
    if raw is not None:
        return _normalize_level(raw)
    try:
        if os.path.isfile(FLAG_FILE):
            with open(FLAG_FILE, "r", encoding="utf-8") as _f:
                return _normalize_level(_f.read().strip())
    except Exception:
        pass
    return _DEFAULT_LEVEL


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------


def _hookable(module: Any) -> bool:
    return module is not None and callable(getattr(module, "register_forward_pre_hook", None)) \
        and callable(getattr(module, "register_forward_hook", None))


def _is_gpu_span(key: str) -> bool:
    return key == "forward" or key.startswith("block:") or key.startswith("refiner:") \
        or key.startswith("embed:") or key.startswith("output:")


def _ms(ns: Optional[int]) -> Optional[float]:
    if ns is None:
        return None
    return round(ns / 1_000_000, 3)


_CALLABLE_METADATA_FALLBACK = "<callable_metadata_unavailable>"
_MAX_METADATA_CHARS = 384
_MAX_BACKEND_CALLS = 1_000_000
_MAX_PATCHES = 64
_MAX_NATIVE_LEAF_EVENTS = 64
_MISSING = object()

# These are dispatch controls rather than tensor inputs.  Keep this list
# explicit: attention kwargs can contain tensors and arbitrary library state.
_ATTENTION_SCALAR_OPTIONS = (
    "qk_quant_gran",
    "pv_accum_dtype",
    "tensor_layout",
    "return_lse",
    "is_causal",
    "causal",
    "sm_scale",
    "scale",
    "softmax_scale",
    "dropout_p",
    "return_softmax",
    "return_attn_probs",
    "out_dtype",
    "output_dtype",
    "skip_reshape",
    "skip_output_proj",
)


def _callable_label(value: Any) -> str:
    """Return a bounded, stable label for a callable without invoking it."""
    try:
        if not callable(value):
            return ""
        module = getattr(value, "__module__", "") or ""
        qualname = getattr(value, "__qualname__", None) or getattr(value, "__name__", None)
        return ".".join(
            part for part in (str(module), str(qualname or "<callable>")) if part
        ) or _CALLABLE_METADATA_FALLBACK
    except Exception:
        # Callable metadata is untrusted library state.  It must never escape a
        # forward hook, and the fallback deliberately cannot identify a backend.
        return _CALLABLE_METADATA_FALLBACK


def _bounded_repr(value: Any, limit: int = _MAX_METADATA_CHARS) -> str:
    """Return a JSON-safe, bounded repr without inspecting tensor contents."""
    # ``repr(torch.Tensor)`` can materialize device data for some tensor-like
    # implementations.  Closure diagnostics need identity, not contents.
    try:
        if (
            hasattr(value, "shape")
            and hasattr(value, "dtype")
            and hasattr(value, "device")
        ):
            return (
                f"<{type(value).__module__}.{type(value).__qualname__} "
                f"shape={_bounded_repr(getattr(value, 'shape', None), 96)} "
                f"dtype={_bounded_repr(getattr(value, 'dtype', None), 96)} "
                f"device={_bounded_repr(getattr(value, 'device', None), 96)}>"
            )[:limit]
    except Exception:
        return "<tensor_metadata_unavailable>"
    try:
        text = repr(value)
    except Exception:
        return _CALLABLE_METADATA_FALLBACK
    if not isinstance(text, str):
        text = str(text)
    return text[:limit]


def _safe_metadata_text(value: Any) -> Optional[str]:
    try:
        return str(value)[:_MAX_METADATA_CHARS] if value is not None else None
    except Exception:
        return None


def _callable_metadata(value: Any) -> Optional[dict[str, Any]]:
    """Serialize callable identity and a small closure sample, without calling it."""
    if not callable(value):
        return None
    result: dict[str, Any] = {
        "repr": _bounded_repr(value),
        "__name__": None,
        "__qualname__": None,
        "__module__": None,
        "sourcefile": None,
        "closure": [],
    }
    # Keep the dunder spelling in the artifact (it mirrors the inspected
    # attributes) and friendly aliases for consumers that use normal labels.
    for attr in ("__name__", "__qualname__", "__module__"):
        try:
            result[attr] = _safe_metadata_text(getattr(value, attr, None))
        except Exception:
            result[attr] = None
    result["name"] = result["__name__"]
    result["qualname"] = result["__qualname__"]
    result["module"] = result["__module__"]
    try:
        result["sourcefile"] = _safe_metadata_text(inspect.getsourcefile(value))
    except Exception:
        result["sourcefile"] = None
    try:
        cells = tuple(getattr(value, "__closure__", None) or ())[:8]
    except Exception:
        cells = ()
    for index, cell in enumerate(cells):
        entry: dict[str, Any] = {"index": index, "cell_type": "cell"}
        try:
            contents = cell.cell_contents
            entry["value_type"] = _callable_label(contents) if callable(contents) else (
                f"{type(contents).__module__}.{type(contents).__qualname__}"
            )
            entry["value_repr"] = _bounded_repr(contents)
        except Exception as exc:
            entry["value_type"] = type(exc).__name__
            entry["value_repr"] = "<cell_unavailable>"
        result["closure"].append(entry)
    return result


def _callable_chain(value: Any, *, _depth: int = 0, _seen: Optional[set[int]] = None) -> list[str]:
    """Describe a small callable-closure chain used by attention dispatch.

    This is metadata-only: it never calls a function or traverses arbitrary
    objects.  The bound keeps diagnostics safe if a library creates a large
    closure graph.
    """
    try:
        if not callable(value) or _depth > 3:
            return []
        seen = _seen if _seen is not None else set()
        if id(value) in seen:
            return []
        seen.add(id(value))
        result = [_callable_label(value)]
        try:
            cells = tuple(getattr(value, "__closure__", None) or ())[:8]
        except Exception:
            cells = ()
        for cell in cells:
            try:
                child = cell.cell_contents
            except (AttributeError, ValueError):
                continue
            try:
                is_callable = callable(child)
            except Exception:
                is_callable = False
            if is_callable:
                result.extend(_callable_chain(child, _depth=_depth + 1, _seen=seen))
            if len(result) >= 16:
                break
        return list(dict.fromkeys(item for item in result if item))[:16]
    except Exception:
        return [_CALLABLE_METADATA_FALLBACK]


_MAX_CLOSURE_ALIAS_DEPTH = 4
_MAX_CLOSURE_ALIAS_CELLS = 8
_MAX_CLOSURE_ALIAS_RECORDS = 32


def _sage_callable_counter(value: Any) -> tuple[Optional[str], bool]:
    """Classify a callable using identity metadata only.

    KJNodes can copy the native Sage callable into a local closure variable.
    In that case changing ``sageattention.sageattn`` later cannot affect the
    copied object.  The second result indicates whether enough metadata was
    readable to make a classification, so inspection failures are explicit.
    """
    if not callable(value):
        return None, True
    fields: list[str] = []
    readable = True
    for attr in ("__module__", "__name__", "__qualname__"):
        try:
            item = getattr(value, attr, None)
        except Exception:
            readable = False
            continue
        if item is not None:
            try:
                fields.append(str(item)[:_MAX_METADATA_CHARS].lower())
            except Exception:
                readable = False
    try:
        source = inspect.getsourcefile(value)
    except Exception:
        source = None
    if source:
        try:
            fields.append(str(source)[:_MAX_METADATA_CHARS].lower())
        except Exception:
            readable = False
    if not readable:
        return None, False

    specialized = any(
        "sageattn_" in field and "_cuda" in field for field in fields
    )
    if specialized:
        try:
            name = getattr(value, "__name__", None)
        except Exception:
            name = None
        if not isinstance(name, str) or not name:
            name = "sageattn_specialized"
        return f"sageattention_specialized:{name[:128]}", True

    # Do not classify KJNodes' ``sage_func``/``attention_sage`` containers by
    # name.  They can be wrappers whose callers rely on ``.__wrapped__``;
    # closure traversal below reaches the imported native alias instead.
    if (
        "sageattention" in " ".join(fields)
        or "sageattn" in " ".join(fields)
        or "sage_attention" in " ".join(fields)
    ):
        return "sageattention_sageattn", True
    return None, True


def _replace_closure_cell(cell: Any, replacement: Any) -> bool:
    """Replace one closure cell, rolling back if the write is not observable."""
    try:
        original = cell.cell_contents
    except Exception:
        return False
    try:
        cell.cell_contents = replacement
        if cell.cell_contents is replacement:
            return True
    except Exception:
        pass
    # A partially successful cell write must not leave a probe wrapper behind.
    try:
        cell.cell_contents = original
    except Exception:
        pass
    return False


def _tensor_descriptor(value: Any) -> dict[str, Any]:
    """Describe an attention input without copying or synchronizing it."""
    result: dict[str, Any] = {}
    try:
        shape = getattr(value, "shape", None)
        if shape is not None:
            result["shape"] = [int(x) for x in shape]
        dtype = getattr(value, "dtype", None)
        device = getattr(value, "device", None)
        if dtype is not None:
            result["dtype"] = str(dtype)
        if device is not None:
            result["device"] = str(device)
        layout = getattr(value, "layout", None)
        if layout is not None:
            result["layout"] = str(layout)
    except Exception:
        return {}
    return result


def _attention_scalar(value: Any) -> Any:
    """Return a JSON-safe scalar, without inspecting tensor-like values."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return _MISSING


def _attention_call_descriptor(
    args: Any, kwargs: Optional[dict[str, Any]] = None, *, override: bool = False
) -> dict[str, Any]:
    """Describe q/k/v and control flags without reading tensor data."""
    positional = tuple(args) if isinstance(args, (tuple, list)) else ()
    kw = kwargs if isinstance(kwargs, dict) else {}
    offset = 1 if override and positional and callable(positional[0]) else 0

    def value_at(index: int, name: str) -> Any:
        if name in kw:
            return kw.get(name)
        return positional[offset + index] if len(positional) > offset + index else None

    q = value_at(0, "q")
    k = value_at(1, "k")
    v = value_at(2, "v")
    heads = kw.get("heads", kw.get("num_heads"))
    if heads is None and len(positional) > offset + 3:
        heads = positional[offset + 3]
    mask = kw.get("mask")
    if mask is None and len(positional) > offset + 4:
        mask = positional[offset + 4]

    descriptor: dict[str, Any] = {
        "q": _tensor_descriptor(q),
        "k": _tensor_descriptor(k),
        "v": _tensor_descriptor(v),
        "mask_present": mask is not None,
    }
    if mask is not None:
        descriptor["mask"] = _tensor_descriptor(mask)
    if heads is not None and isinstance(heads, (str, int, float, bool)):
        descriptor["heads"] = heads
    for name in _ATTENTION_SCALAR_OPTIONS:
        if name not in kw:
            continue
        value = _attention_scalar(kw[name])
        if value is not _MISSING:
            descriptor[name] = value
    # A few Comfy attention versions expose skip_reshape after an optional
    # precision argument, while others put it immediately after mask.  A bool
    # is unambiguous here; never serialize an unknown positional object.
    if "skip_reshape" not in descriptor:
        for index in (5, 6):
            if len(positional) > offset + index:
                value = positional[offset + index]
                if isinstance(value, bool):
                    descriptor["skip_reshape"] = value
                    break
    return descriptor


_PROFILER_KEY_MARKERS = (
    "sageattention",
    "comfy_kitchen",
    "scaled_dot_product_attention",
    "aten::_scaled_dot_product",
    "aten::scaled_dot_product",
    "aten::_flash_attention",
    "aten::_efficient_attention",
)


def _create_attention_profiler() -> Any:
    """Create a CPU+CUDA profiler without importing torch on the off path."""
    import torch

    profiler_api = getattr(torch, "profiler")
    factory = getattr(profiler_api, "profile")
    activity_type = getattr(profiler_api, "ProfilerActivity", None)
    activities = []
    if activity_type is not None:
        for name in ("CPU", "CUDA"):
            activity = getattr(activity_type, name, None)
            if activity is not None:
                activities.append(activity)
    kwargs: dict[str, Any] = {
        "record_shapes": False,
        "profile_memory": False,
        "with_stack": False,
    }
    if activities:
        kwargs["activities"] = activities
    return factory(**kwargs)


def _profiler_number(value: Any) -> Optional[float]:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return round(float(value), 3)


def _filtered_profiler_events(events: Any) -> list[dict[str, Any]]:
    """Keep only bounded attention/native key averages as JSON-safe scalars."""
    result: list[dict[str, Any]] = []
    try:
        iterator = iter(events)
    except Exception:
        return result
    for event in iterator:
        if len(result) >= _MAX_NATIVE_LEAF_EVENTS:
            break
        try:
            key = str(getattr(event, "key", ""))[:256]
        except Exception:
            continue
        lowered = key.lower()
        if not key or not any(marker in lowered for marker in _PROFILER_KEY_MARKERS):
            continue
        item: dict[str, Any] = {"key": key}
        try:
            count = getattr(event, "count", None)
            if isinstance(count, (int, float)) and not isinstance(count, bool):
                item["count"] = int(count)
        except Exception:
            pass
        timing_fields = (
            ("self_cpu_time_total", "self_cpu_time_total_us"),
            ("cpu_time_total", "cpu_time_total_us"),
            ("self_cuda_time_total", "self_cuda_time_total_us"),
            ("cuda_time_total", "cuda_time_total_us"),
            ("self_device_time_total", "self_device_time_total_us"),
            ("device_time_total", "device_time_total_us"),
        )
        for source, target in timing_fields:
            try:
                value = _profiler_number(getattr(event, source, None))
            except Exception:
                value = None
            if value is not None:
                item[target] = value
        result.append(item)
    return result


# ---------------------------------------------------------------------------
# Profile object
# ---------------------------------------------------------------------------


class SamplingDeepProfile:
    """One sampler-invocation deep profile.

    Thread-confined to the sampler thread (it owns the class-level patch for
    its duration).  ``finalize`` restores every patch/hook unconditionally and
    emits a single ``sampling_deep_profile`` trace event with a bounded,
    JSON-serializable artifact.
    """

    __slots__ = (
        "trace", "level", "node_id", "node_class", "steps", "requested_backend",
        "sampling_start_mono_ns", "sampling_start_wall_ns",
        "sampling_end_mono_ns", "sampling_end_wall_ns",
        "patcher", "dm", "rejected",
        "errors", "warnings", "callback_indices", "evals",
        "_current_eval", "_span_stack", "_hooks", "_ctx_token",
        "_patched_class", "_original_ksampler_call", "_ksampler_owner",
        "_inner_marker_available",
        "_cuda_module", "_cuda_enabled", "_cuda_pairs", "_cuda_timings",
        "_cuda_per_eval_forward",
        "_backend_module", "_backend_original", "_backend_observations",
        "_backend_counts", "_backend_signatures",
        "_backend_patches", "_backend_first_calls", "_specialized_counts",
        "_fallback_counts", "_kitchen_public_first_calls",
        "_attention_profiler", "_attention_profiler_status",
        "_attention_profiler_error", "_attention_profiler_attempted",
        "_attention_profiler_context", "_attention_profiler_call",
        "_native_leaf_events",
        "_override_container", "_override_original",
        "_override_wrapper", "_override_wrappers", "_override_metadata",
        "_override_chain", "_override_call_count",
        "_override_first_call",
        "_closure_aliases", "_closure_alias_unobservable", "_closure_alias_cells",
        "_start_perf_ns", "finalize_host_ms", "cuda_sync_ms", "last_artifact",
        "finalized",
    )

    def __init__(
        self,
        trace: Any,
        *,
        level: str,
        node_id: str,
        node_class: str,
        steps: int,
        sampling_start_monotonic_ns: int,
        sampling_start_wall_unix_ns: int,
        patcher: Any,
        dm: Any,
        requested_backend: str = "",
    ) -> None:
        self.trace = trace
        self.level = level
        self.node_id = str(node_id or "")
        self.node_class = str(node_class or "")
        self.steps = int(steps or 0)
        self.requested_backend = str(requested_backend or "")
        self.sampling_start_mono_ns = int(sampling_start_monotonic_ns or 0)
        self.sampling_start_wall_ns = int(sampling_start_wall_unix_ns or 0)
        self.sampling_end_mono_ns = 0
        self.sampling_end_wall_ns = 0
        self.patcher = patcher
        self.dm = dm
        self.rejected = False
        self.errors: list[str] = []
        self.warnings: list[str] = []
        self.callback_indices: list[tuple[Any, int]] = []  # (index, mono_ns)
        self.evals: list[dict[str, Any]] = []
        self._current_eval: Optional[dict[str, Any]] = None
        self._span_stack: list[dict[str, Any]] = []
        self._hooks: list[tuple[str, Any]] = []
        self._ctx_token: Optional[contextvars.Token] = None
        self._patched_class: Optional[type] = None
        self._original_ksampler_call: Optional[Callable] = None
        self._ksampler_owner = False
        self._inner_marker_available = False
        self._cuda_module: Any = None
        self._cuda_enabled = False
        self._cuda_pairs: list[tuple[Any, Any, str, int]] = []
        self._cuda_timings: dict[str, float] = {}
        self._cuda_per_eval_forward: dict[int, float] = {}
        self._backend_module: Any = None
        self._backend_original: Optional[Callable] = None
        self._backend_observations: list[dict[str, Any]] = []
        self._backend_counts: dict[str, int] = {}
        self._backend_signatures: dict[str, list[list[str]]] = {}
        self._backend_patches: list[tuple[str, Any, str, Any, Any]] = []
        self._backend_first_calls: dict[str, dict[str, Any]] = {}
        self._specialized_counts: dict[str, int] = {}
        self._fallback_counts: dict[str, int] = {}
        self._kitchen_public_first_calls: dict[str, dict[str, Any]] = {}
        self._attention_profiler: Any = None
        self._attention_profiler_status = "not_requested"
        self._attention_profiler_error: Optional[str] = None
        self._attention_profiler_attempted = False
        self._attention_profiler_context: Any = None
        self._attention_profiler_call: Optional[str] = None
        self._native_leaf_events: list[dict[str, Any]] = []
        self._override_container: Optional[dict[str, Any]] = None
        self._override_original: Optional[Callable] = None
        self._override_wrapper: Optional[Callable] = None
        self._override_wrappers: list[tuple[Callable, Callable]] = []
        self._override_metadata: Optional[dict[str, Any]] = None
        self._override_chain: list[str] = []
        self._override_call_count = 0
        self._override_first_call: Optional[dict[str, Any]] = None
        self._closure_aliases: list[dict[str, Any]] = []
        self._closure_alias_unobservable: list[str] = []
        self._closure_alias_cells: set[int] = set()
        self._start_perf_ns = time.perf_counter_ns()
        self.finalize_host_ms = 0.0
        self.cuda_sync_ms = 0.0
        self.last_artifact: Optional[dict[str, Any]] = None
        self.finalized = False

    # ── Level A: KSamplerX0Inpaint.__call__ patch ─────────────────────────

    def _install_ksampler_patch(self) -> bool:
        global _PATCH_OWNER
        cls = _resolve_ksampler_x0_inpaint()
        if cls is None:
            self.warnings.append(
                "level_a_unavailable: comfy.samplers.KSamplerX0Inpaint not resolvable"
            )
            return False
        with _PATCH_LOCK:
            if getattr(cls, _PATCH_MARKER, False):
                if _PATCH_OWNER is not None:
                    self.rejected = True
                    self.warnings.append(
                        "concurrency_rejected: another sampler invocation holds "
                        "the KSamplerX0Inpaint patch; profiling disabled for this one"
                    )
                    return False
                # Stale marker without an owner: restore first, then reinstall.
                stale = _PATCH_ORIGINALS.pop(id(cls), None)
                if stale is not None:
                    try:
                        cls.__call__ = stale
                    except Exception:
                        pass
                try:
                    delattr(cls, _PATCH_MARKER)
                except Exception:
                    pass
            self._patched_class = cls
            self._original_ksampler_call = cls.__call__
            _PATCH_ORIGINALS[id(cls)] = cls.__call__

            def _profiled_call(_self: Any, *args: Any, **kwargs: Any) -> Any:
                self._begin_eval()
                orig_call = self._original_ksampler_call
                assert orig_call is not None
                try:
                    return orig_call(_self, *args, **kwargs)
                finally:
                    self._end_eval()

            cls.__call__ = _profiled_call
            setattr(cls, _PATCH_MARKER, True)
            _PATCH_OWNER = id(self)
            global _LAST_PATCHED_CLASS
            _LAST_PATCHED_CLASS = cls
            self._ksampler_owner = True
            return True

    def _restore_ksampler_patch(self) -> None:
        global _PATCH_OWNER, _LAST_PATCHED_CLASS
        cls = getattr(self, "_patched_class", None)
        if cls is not None:
            try:
                orig = _PATCH_ORIGINALS.pop(id(cls), None)
                if orig is not None:
                    cls.__call__ = orig
                elif getattr(self, "_original_ksampler_call", None) is not None:
                    cls.__call__ = self._original_ksampler_call
            except Exception:
                self.errors.append("restore_ksampler_patch_failed")
            try:
                if getattr(cls, _PATCH_MARKER, False):
                    delattr(cls, _PATCH_MARKER)
            except Exception:
                pass
            if _LAST_PATCHED_CLASS is cls:
                _LAST_PATCHED_CLASS = None
        with _PATCH_LOCK:
            if _PATCH_OWNER == id(self):
                _PATCH_OWNER = None
        self._ksampler_owner = False

    # ── Level A eval recording ────────────────────────────────────────────

    def _begin_eval(self) -> None:
        if self._current_eval is not None:
            self.errors.append(
                f"nested_ksampler_call: eval {self._current_eval['index']} still open"
            )
        ev: dict[str, Any] = {
            "index": len(self.evals),
            # Same steady clock as the authoritative sampling_start/sampling_end
            # event timestamps so setup/steps/teardown reconcile exactly.
            "start_ns": time.monotonic_ns(),
            "end_ns": None,
            "spans": {"forward": None, "blocks": {}},
            "block_categories": {},
            "categories": {},
            "backend": {"dispatch": {}, "calls": {}},
            "compute_or_skip": "unknown",
            "block_hooks_fired": False,
        }
        self.evals.append(ev)
        self._current_eval = ev

    def _end_eval(self) -> None:
        ev = self._current_eval
        if ev is not None:
            ev["end_ns"] = time.monotonic_ns()
            if self._span_stack:
                self.errors.append(
                    f"unclosed_spans_during_eval_{ev['index']}: "
                    f"{[s['key'] for s in self._span_stack]}"
                )
                self._span_stack.clear()
        self._current_eval = None

    def on_callback_index(self, index: Any) -> None:
        """Record one per-step callback index (int) with its host timestamp."""
        if isinstance(index, bool):
            index = int(index)
        if isinstance(index, int):
            self.callback_indices.append((index, time.monotonic_ns()))
        else:
            self.callback_indices.append((index, time.monotonic_ns()))
            if not any(w.startswith("callback_index_non_int") for w in self.warnings):
                self.warnings.append(
                    f"callback_index_non_int: {type(index).__name__} recorded as-is"
                )

    # ── Level B hooks ─────────────────────────────────────────────────────

    def _add_hook(self, module: Any, key: str, category: Optional[str]) -> None:
        pre = _make_pre_hook(self, key, category)
        post = _make_post_hook(self, key, category)
        try:
            self._hooks.append((f"{key}.pre", module.register_forward_pre_hook(pre, with_kwargs=True)))
            self._hooks.append((f"{key}.post", module.register_forward_hook(post)))
        except Exception as exc:
            self.errors.append(f"hook_install_failed:{key}:{type(exc).__name__}")

    def _install_diffusion_hooks(self) -> None:
        dm = self.dm
        if dm is None:
            self.warnings.append("level_b_unavailable: no diffusion model resolved")
            return
        if not _hookable(dm):
            self.warnings.append(
                "level_b_unavailable: diffusion model lacks nn.Module hook registry"
            )
            return
        try:
            self._add_hook(dm, "forward", None)
        except Exception as exc:
            self.errors.append(f"dm_forward_hook_failed:{type(exc).__name__}")
            return
        # Compute marker: block-total hooks on main/refiner blocks.  These fire
        # only on COMPUTED forwards (CacheDiT whole-forward skips bypass the
        # inner blocks), so they distinguish compute vs skip in BOTH modes.
        self._install_block_marker_hooks()
        if self.level == "steps":
            return  # minimal overhead: dm forward + block-total markers only
        # ── blocks mode: category sub-hooks on main blocks ──
        layers = getattr(dm, "layers", None)
        if layers is not None:
            try:
                for i, block in enumerate(layers):
                    if not _hookable(block):
                        continue
                    for sub_name, cat in _BLOCK_SUBMODULES.items():
                        sub = getattr(block, sub_name, None)
                        if _hookable(sub):
                            self._add_hook(sub, f"block:{i}:{cat}", cat)
            except Exception as exc:
                self.errors.append(f"block_hook_failed:{type(exc).__name__}")
        # ── embeddings / output ──
        for name, key, cat in _DM_DIRECT_MODULES:
            m = getattr(dm, name, None)
            if _hookable(m):
                self._add_hook(m, key, cat)

    def _install_block_marker_hooks(self) -> None:
        """Install block-total forward hooks on main/refiner blocks.

        These are the minimum inner compute-marker hooks: they fire on every
        computed forward but never on CacheDiT whole-forward skips.  No
        category sub-hooks are installed here (steps mode stays minimal).
        When no inner blocks are hookable, ``_inner_marker_available`` stays
        False and evals are classified ``unknown`` rather than fabricated skips.
        """
        count = 0
        # Refiner block-total markers accumulate into the "refiner" category
        # only in blocks mode; steps mode keeps zero category accumulation.
        refiner_cat = "refiner" if self.level == "blocks" else None
        for kind, attr in (
            ("main", "layers"),
            ("noise", "noise_refiner"),
            ("context", "context_refiner"),
        ):
            blocks = getattr(self.dm, attr, None)
            if not blocks:
                continue
            try:
                for i, block in enumerate(blocks):
                    if not _hookable(block):
                        continue
                    if kind == "main":
                        self._add_hook(block, f"block:{i}", None)
                    else:
                        self._add_hook(block, f"refiner:{kind}:{i}", refiner_cat)
                    count += 1
            except Exception as exc:
                self.errors.append(f"marker_hook_failed:{kind}:{type(exc).__name__}")
        if count > 0:
            self._inner_marker_available = True

    def _remove_hooks(self) -> None:
        for desc, handle in self._hooks:
            try:
                if hasattr(handle, "remove"):
                    handle.remove()
            except Exception:
                pass
        self._hooks = []

    # ── CUDA events (blocks mode, CUDA available) ─────────────────────────

    def _install_cuda_recorder(self) -> None:
        if self.level != "blocks":
            return
        cu = _resolve_cuda_module()
        if cu is None:
            self.warnings.append("cuda_events_unavailable: CUDA not available")
            if self.requested_backend in {"sage", "comfy_kitchen"}:
                self._attention_profiler_status = "unavailable"
                self._attention_profiler_error = "CUDA is not available"
            return
        self._cuda_module = cu
        self._cuda_enabled = True

    def _install_backend_probe(self) -> None:
        """Install observation-only wrappers around reachable attention seams.

        Every wrapper calls the exact object it replaces.  This is deliberately
        separate from the Golden selector: an import-time alias which has
        already been copied elsewhere cannot be intercepted safely and is only
        reported as such.
        """
        if self.level != "blocks":
            return

        # KJNodes/NextDiT puts the active override here.  Inspect it before
        # replacing it; metadata collection never invokes the callable.
        try:
            options = getattr(self.patcher, "model_options", None)
            transformer_options = (
                options.get("transformer_options")
                if isinstance(options, dict)
                else None
            )
            original_override = (
                transformer_options.get("optimized_attention_override")
                if isinstance(transformer_options, dict)
                else None
            )
            if callable(original_override) and isinstance(transformer_options, dict):
                self._install_override_mapping(transformer_options, original_override)
        except Exception as exc:
            self.warnings.append(
                f"attention_observation_install_failed:optimized_attention_override:{type(exc).__name__}"
            )

        # Import each module independently.  A missing optional package must
        # not prevent observation of the Comfy seams that are available.
        sage = self._optional_module("sageattention", "sageattention")
        if sage is not None:
            self._patch_callable_attr(sage, "sageattn", "sageattention_sageattn")
            specialized = []
            try:
                namespace = getattr(sage, "__dict__", {})
                specialized = [
                    name for name, value in namespace.items()
                    if name.startswith("sageattn_") and name.endswith("_cuda")
                    and callable(value)
                ][:32]
            except Exception:
                specialized = []
            for name in specialized:
                self._specialized_counts.setdefault(name, 0)
                self._patch_callable_attr(sage, name, f"sageattention_specialized:{name}")
            if not specialized:
                self.warnings.append(
                    "attention_observation_unavailable:sageattention_specialized"
                )
        else:
            self.warnings.append("attention_observation_unavailable:sageattention_sageattn")

        kitchen = self._optional_module("comfy_kitchen", "comfy_kitchen")
        if kitchen is not None:
            # These are public Python entry points.  Native
            # comfy_kitchen::int8_attention* evidence is collected separately
            # by the one-shot profiler and is never folded into these counts.
            self._patch_callable_attr(
                kitchen, "int8_attention", "comfy_kitchen_int8_attention"
            )
            self._patch_callable_attr(
                kitchen,
                "int8_attention_masked",
                "comfy_kitchen_int8_attention_masked",
            )
        else:
            self.warnings.append(
                "attention_observation_unavailable:comfy_kitchen_int8_attention"
            )

        attention = self._optional_module(
            "comfy.ldm.modules.attention", "comfy_attention"
        )
        if attention is None:
            self.warnings.append("attention_observation_unavailable:comfy_attention")
            self.warnings.append("attention_observation_unavailable:attention_pytorch")
            self.warnings.append("attention_observation_unavailable:pytorch_sdpa")
            self.warnings.append("attention_observation_unavailable:comfy_fallbacks")
        else:
            self._patch_callable_attr(attention, "attention_pytorch", "attention_pytorch")
            self._patch_callable_attr(
                attention, "scaled_dot_product_attention", "pytorch_sdpa"
            )
            self._install_fallback_targets(attention)

        # Current Comfy builds also expose the SDPA seam from comfy.ops.  Keep
        # this target for callers which imported that name directly.
        ops = self._optional_module("comfy.ops", "comfy_ops")
        if ops is not None:
            self._patch_callable_attr(ops, "scaled_dot_product_attention", "pytorch_sdpa")
            self._install_fallback_targets(ops, warn=False)
        else:
            self.warnings.append("attention_observation_unavailable:comfy_ops")
            self.warnings.append("attention_observation_unavailable:pytorch_sdpa")

    def _optional_module(self, module_name: str, target: str) -> Optional[Any]:
        try:
            return importlib.import_module(module_name)
        except Exception as exc:
            self.warnings.append(
                f"attention_observation_unavailable:{target}:{type(exc).__name__}"
            )
            return None

    def _override_wrapper_for(self, original: Any) -> Optional[Callable]:
        for wrapper, source in self._override_wrappers:
            if source is original:
                return wrapper
        return None

    def _override_source_for(self, value: Any) -> Any:
        for wrapper, source in self._override_wrappers:
            if value is wrapper:
                return source
        return value

    def _install_override_mapping(
        self, transformer_options: dict[str, Any], original: Callable
    ) -> bool:
        """Wrap one exact per-call transformer-options mapping.

        Comfy/KJNodes can create this mapping after profile installation.  The
        first callable is retained for the artifact, while each mapping gets a
        wrapper around the callable it actually contains.  This is observation
        only: the wrapper returns the original result unchanged.
        """
        if not callable(original):
            return False
        if self._override_original is None:
            self._override_original = original
            self._override_metadata = _callable_metadata(original)
            # Capture before closure cells are replaced so existing upper-chain
            # evidence remains the original KJNodes chain.
            self._override_chain = _callable_chain(original)
        if self._override_container is None:
            self._override_container = transformer_options

        wrapper = self._override_wrapper_for(original)
        if wrapper is None:
            def _profiled_override(*args: Any, **kwargs: Any) -> Any:
                self._override_call_count = min(
                    self._override_call_count + 1, _MAX_BACKEND_CALLS
                )
                self._record_backend_call(
                    "optimized_attention_override", args=args, kwargs=kwargs
                )
                if self._override_first_call is None:
                    self._override_first_call = _attention_call_descriptor(
                        args, kwargs, override=True
                    )
                return self._invoke_observed_backend(
                    "optimized_attention_override", original, args, kwargs
                )

            wrapper = _profiled_override
            self._override_wrappers.append((wrapper, original))
            if self._override_wrapper is None:
                self._override_wrapper = wrapper

        # Inspect the original callable rather than the wrapper just placed in
        # transformer_options: KJNodes may have copied Sage callables into
        # closure cells before this probe was installed.
        self._install_closure_alias_probes(original)

        try:
            current = transformer_options.get("optimized_attention_override", _MISSING)
        except Exception:
            current = _MISSING
        if current is wrapper:
            return True
        self._patch_mapping(
            transformer_options, "optimized_attention_override", original, wrapper
        )
        return True

    def _mark_closure_alias_unobservable(self, label: str, reason: str) -> None:
        entry = f"{label}:{reason}"
        if entry not in self._closure_alias_unobservable:
            self._closure_alias_unobservable.append(entry)
        warning = f"closure_alias_unobservable:{entry}"
        if warning not in self.warnings:
            self.warnings.append(warning)

    def _install_closure_alias_probes(self, root: Any) -> None:
        """Wrap bounded Sage callable aliases reachable through closure cells."""
        if not callable(root):
            return
        stack: list[tuple[Any, int]] = [(root, 0)]
        seen: set[int] = set()
        while stack:
            current, depth = stack.pop()
            current_id = id(current)
            if current_id in seen:
                continue
            seen.add(current_id)
            if depth >= _MAX_CLOSURE_ALIAS_DEPTH:
                continue
            try:
                closure = getattr(current, "__closure__", None)
            except Exception as exc:
                self._mark_closure_alias_unobservable(
                    _callable_label(current)[:_MAX_METADATA_CHARS],
                    f"closure_read_failed:{type(exc).__name__}",
                )
                continue
            try:
                cells = tuple(closure or ())[:_MAX_CLOSURE_ALIAS_CELLS]
            except Exception as exc:
                self._mark_closure_alias_unobservable(
                    _callable_label(current)[:_MAX_METADATA_CHARS],
                    f"closure_read_failed:{type(exc).__name__}",
                )
                continue
            for cell_index, cell in enumerate(cells):
                try:
                    child = cell.cell_contents
                except (AttributeError, ValueError):
                    continue
                try:
                    child_callable = callable(child)
                except Exception:
                    child_callable = False
                if not child_callable:
                    continue
                counter, metadata_readable = _sage_callable_counter(child)
                child_label = _callable_label(child)[:_MAX_METADATA_CHARS]
                if not metadata_readable:
                    self._mark_closure_alias_unobservable(
                        child_label, "callable_metadata_unreadable"
                    )
                elif counter is not None and id(cell) not in self._closure_alias_cells:
                    if len(self._backend_patches) >= _MAX_PATCHES:
                        self._mark_closure_alias_unobservable(
                            child_label, "patch_limit_reached"
                        )
                    elif len(self._closure_aliases) >= _MAX_CLOSURE_ALIAS_RECORDS:
                        self._mark_closure_alias_unobservable(
                            child_label, "alias_limit_reached"
                        )
                    else:
                        original = child

                        def _make_closure_wrapper(
                            source: Callable, backend: str
                        ) -> Callable:
                            def _profiled_closure_alias(
                                *args: Any, **kwargs: Any
                            ) -> Any:
                                self._record_backend_call(
                                    backend, args=args, kwargs=kwargs
                                )
                                return self._invoke_observed_backend(
                                    backend, source, args, kwargs
                                )

                            # Preserve wrapper contracts for any pass-through
                            # callable that is safe to observe.  KJNodes
                            # containers are excluded by _sage_callable_counter
                            # above, but this keeps __wrapped__ intact if a
                            # future native alias is itself decorated.
                            try:
                                functools.update_wrapper(
                                    _profiled_closure_alias, source
                                )
                            except Exception:
                                pass
                            return _profiled_closure_alias

                        _profiled_closure_alias = _make_closure_wrapper(
                            original, counter
                        )

                        # Keep a restore record even if a platform refuses the
                        # cell assignment.  The normal finalizer remains the
                        # last safety net for a partial write.
                        patch = (
                            "closure", cell, child_label, original,
                            _profiled_closure_alias,
                        )
                        self._backend_patches.append(patch)
                        try:
                            replaced = _replace_closure_cell(
                                cell, _profiled_closure_alias
                            )
                        except Exception as exc:
                            replaced = False
                            self._mark_closure_alias_unobservable(
                                child_label,
                                f"cell_replace_failed:{type(exc).__name__}",
                            )
                        if replaced:
                            self._closure_alias_cells.add(id(cell))
                            self._closure_aliases.append({
                                "counter": counter,
                                "callable": child_label,
                                "cell_index": cell_index,
                                "depth": depth + 1,
                            })
                        elif not any(
                            item.startswith(f"{child_label}:cell_replace_failed")
                            for item in self._closure_alias_unobservable
                        ):
                            self._mark_closure_alias_unobservable(
                                child_label, "cell_replace_failed"
                            )
                if depth + 1 < _MAX_CLOSURE_ALIAS_DEPTH:
                    stack.append((child, depth + 1))

    def _patch_mapping(
        self, mapping: dict[str, Any], name: str, original: Any, wrapper: Any
    ) -> None:
        if len(self._backend_patches) >= _MAX_PATCHES:
            self.warnings.append("attention_observation_patch_limit_reached")
            return
        self._backend_patches.append(("mapping", mapping, name, original, wrapper))
        try:
            mapping[name] = wrapper
        except Exception:
            self._backend_patches.pop()
            raise

    def _attention_profiler_requested(self, counter: str) -> bool:
        return (
            self.level == "blocks"
            and self.requested_backend in {"sage", "comfy_kitchen"}
            and counter
            in {
                "sageattention_sageattn",
                "comfy_kitchen_int8_attention",
                "comfy_kitchen_int8_attention_masked",
                "optimized_attention_override",
            }
        )

    def _start_attention_profiler(self, counter: str) -> bool:
        """Start the bounded profiler immediately before one public call."""
        if not self._attention_profiler_requested(counter):
            return False
        if self._attention_profiler_attempted:
            return False
        self._attention_profiler_attempted = True
        if self._cuda_module is None:
            self._attention_profiler_status = "unavailable"
            self._attention_profiler_error = "CUDA is not available"
            return False
        try:
            profiler = _create_attention_profiler()
            entered = profiler.__enter__()
            self._attention_profiler = entered if entered is not None else profiler
            self._attention_profiler_context = profiler
            self._attention_profiler_call = counter
            self._attention_profiler_status = "started"
            return True
        except Exception as exc:
            self._attention_profiler = None
            self._attention_profiler_status = "error"
            self._attention_profiler_error = f"{type(exc).__name__}: {str(exc)[:256]}"
            return False

    def _stop_attention_profiler(self) -> None:
        profiler = self._attention_profiler
        context = self._attention_profiler_context
        if profiler is None:
            return
        stop_error: Optional[Exception] = None
        try:
            (context or profiler).__exit__(None, None, None)
        except Exception as exc:
            stop_error = exc
        try:
            events = profiler.key_averages()
            self._native_leaf_events = _filtered_profiler_events(events)
        except Exception as exc:
            if stop_error is None:
                stop_error = exc
        self._attention_profiler = None
        self._attention_profiler_context = None
        if stop_error is not None:
            self._attention_profiler_status = "error"
            self._attention_profiler_error = (
                f"{type(stop_error).__name__}: {str(stop_error)[:256]}"
            )
        elif self._native_leaf_events:
            self._attention_profiler_status = "captured"
        else:
            # A completed capture without a matching marker is evidence of
            # absence only, not proof that a native backend was not used.
            self._attention_profiler_status = "captured_no_markers"

    def _invoke_observed_backend(
        self, counter: str, original: Callable, args: Any, kwargs: Any
    ) -> Any:
        capture = self._start_attention_profiler(counter)
        try:
            return original(*args, **kwargs)
        finally:
            if capture:
                self._stop_attention_profiler()

    def _patch_callable_attr(self, module: Any, name: str, counter: str) -> bool:
        try:
            original = getattr(module, name, None)
        except Exception:
            original = None
        if not callable(original):
            self.warnings.append(f"attention_observation_unavailable:{counter}")
            return False
        if len(self._backend_patches) >= _MAX_PATCHES:
            self.warnings.append("attention_observation_patch_limit_reached")
            return False

        def _profiled_backend(*args: Any, **kwargs: Any) -> Any:
            self._record_backend_call(counter, args=args, kwargs=kwargs)
            return self._invoke_observed_backend(counter, original, args, kwargs)

        try:
            self._backend_patches.append(
                ("attribute", module, name, original, _profiled_backend)
            )
            setattr(module, name, _profiled_backend)
        except Exception:
            self._backend_patches.pop()
            self.warnings.append(
                f"attention_observation_patch_failed:{counter}:{type(original).__name__}"
            )
            return False
        if counter == "pytorch_sdpa" and self._backend_module is None:
            self._backend_module = module
            self._backend_original = original
        return True

    def _install_fallback_targets(self, module: Any, *, warn: bool = True) -> None:
        names = {
            "attention_fallback", "attention_sub_quad", "attention_split",
            "attention_xformers", "attention_sliced", "attention_npu",
        }
        try:
            namespace = getattr(module, "__dict__", {})
            reachable = [
                name for name, value in namespace.items()
                if (name in names or "fallback" in name.lower()) and callable(value)
            ][:16]
        except Exception:
            reachable = []
        for name in reachable:
            self._fallback_counts.setdefault(name, 0)
            self._patch_callable_attr(module, name, f"fallback:{name}")
        if not reachable and warn:
            self.warnings.append("attention_observation_unavailable:comfy_fallbacks")

    def _record_backend_call(
        self, backend: str, *, args: Any = (), kwargs: Optional[dict[str, Any]] = None
    ) -> None:
        self._backend_counts[backend] = min(
            self._backend_counts.get(backend, 0) + 1, _MAX_BACKEND_CALLS
        )
        if backend.startswith("sageattention_specialized:"):
            name = backend.split(":", 1)[1]
            self._specialized_counts[name] = self._backend_counts[backend]
        elif backend.startswith("fallback:"):
            name = backend.split(":", 1)[1]
            self._fallback_counts[name] = self._backend_counts[backend]
        self._backend_first_calls.setdefault(
            backend, _attention_call_descriptor(args, kwargs)
        )
        if backend.startswith("comfy_kitchen_int8_attention"):
            self._kitchen_public_first_calls.setdefault(
                backend, _attention_call_descriptor(args, kwargs)
            )
        ev = self._current_eval
        if ev is not None:
            calls = ev["backend"]["calls"]
            calls[backend] = min(calls.get(backend, 0) + 1, _MAX_BACKEND_CALLS)

    def _record_attention_dispatch(
        self, module: Any, args: Any, kwargs: Optional[dict[str, Any]]
    ) -> None:
        ev = self._current_eval
        if ev is None:
            return
        backend = "unknown_attention_dispatch"
        signature: list[str] = []
        override = None
        override_present = False
        input_descriptor: dict[str, Any] = {}
        module_label = ""
        metadata_error: Optional[Exception] = None
        try:
            options = kwargs.get("transformer_options") if isinstance(kwargs, dict) else None
            observed_override = (
                options.get("optimized_attention_override")
                if isinstance(options, dict)
                else None
            )
            override_present = callable(observed_override)
            if callable(observed_override) and isinstance(options, dict):
                if self._override_source_for(observed_override) is observed_override:
                    self._install_override_mapping(options, observed_override)
                override = self._override_source_for(observed_override)
            else:
                override = observed_override
                if not any(
                    item.startswith("attention_observation_unavailable:optimized_attention_override")
                    for item in self.warnings
                ):
                    self.warnings.append(
                        "attention_observation_unavailable:optimized_attention_override"
                    )
            try:
                import comfy.ldm.modules.attention as attention  # type: ignore[import-not-found]
                base = getattr(attention, "optimized_attention_masked", None)
            except Exception:
                base = None
            selected = override if override_present else base
            signature = _callable_chain(selected)
            joined = " ".join(signature).lower()
            # The fallback label means metadata inspection failed.  Do not let
            # a partially observed name turn that into a backend claim.
            if _CALLABLE_METADATA_FALLBACK in signature:
                metadata_error = RuntimeError("callable metadata unavailable")
            if _CALLABLE_METADATA_FALLBACK not in signature:
                if "attention_fallback" in joined or "attention_pytorch" in joined:
                    backend = "pytorch_override"
                elif "sage" in joined or "sageattn" in joined:
                    backend = "sage_override"
                elif "comfy_kitchen" in joined or "kitchen_int8" in joined:
                    backend = "comfy_kitchen_int8_override"
                elif callable(selected):
                    backend = "other_attention_override"
            input_tensor = args[0] if isinstance(args, tuple) and args else None
            input_descriptor = _tensor_descriptor(input_tensor)
            module_label = _callable_label(module)
            if module_label == _CALLABLE_METADATA_FALLBACK:
                metadata_error = RuntimeError("module callable metadata unavailable")
        except Exception as exc:
            metadata_error = exc
            # Keep the observation and span alive, but fail closed on the
            # backend classification when callable metadata is unusual.
            backend = "unknown_attention_dispatch"
            signature = []
            input_descriptor = {}
            module_label = _CALLABLE_METADATA_FALLBACK

        if metadata_error is not None:
            marker = f"attention_callable_metadata_failed:{type(metadata_error).__name__}"
            if not any(item.startswith("attention_callable_metadata_failed:") for item in self.warnings):
                self.warnings.append(marker)

        dispatch = ev["backend"]["dispatch"]
        dispatch[backend] = dispatch.get(backend, 0) + 1
        self._backend_counts[backend] = self._backend_counts.get(backend, 0) + 1
        signatures = self._backend_signatures.setdefault(backend, [])
        if signature and signature not in signatures and len(signatures) < 8:
            signatures.append(signature)
        if len(self._backend_observations) < 512:
            input_tensor = args[0] if isinstance(args, tuple) and args else None
            self._backend_observations.append({
                "eval_index": ev["index"],
                "backend_classification": backend,
                "callable_chain": signature,
                "input": input_descriptor,
                "override_present": override_present,
                "module": module_label,
            })

    def _span_begin(self, key: str, category: Optional[str]) -> None:
        ev = self._current_eval
        if ev is None:
            if not any(w.startswith("hook_outside_eval") for w in self.warnings):
                self.warnings.append("hook_outside_eval: span ignored (no active eval)")
            return
        entry: dict[str, Any] = {
            "key": key,
            "category": category,
            "start_ns": time.monotonic_ns(),
        }
        if self._cuda_enabled and _is_gpu_span(key):
            try:
                s = self._cuda_module.Event(enable_timing=True)
                s.record()
                entry["cuda_start"] = s
            except Exception:
                pass
        if key.startswith("block:") or key.startswith("refiner:"):
            ev["block_hooks_fired"] = True
        self._span_stack.append(entry)

    def _span_end(self, key: str, category: Optional[str]) -> None:
        if not self._span_stack:
            return
        entry = self._span_stack.pop()
        if entry["key"] != key:
            self.errors.append(f"span_mismatch: closed {key} but top is {entry['key']}")
            return
        end_ns = time.monotonic_ns()
        dur_ns = end_ns - entry["start_ns"]
        ev = self._current_eval
        if self._cuda_enabled and "cuda_start" in entry:
            try:
                e = self._cuda_module.Event(enable_timing=True)
                e.record()
                self._cuda_pairs.append(
                    (entry["cuda_start"], e, key, ev["index"] if ev is not None else -1)
                )
            except Exception:
                pass
        if ev is None:
            return
        if key == "forward":
            ev["spans"]["forward"] = (entry["start_ns"], end_ns)
            if ev["compute_or_skip"] == "unknown":
                if self._inner_marker_available:
                    ev["compute_or_skip"] = "compute" if ev["block_hooks_fired"] else "skip"
                # No inner compute-marker hooks available: classify unknown
                # rather than fabricating a skip.
            return
        if key.startswith("block:") and key.count(":") == 1:
            parts = key.split(":")
            try:
                bi = int(parts[1])
            except (ValueError, IndexError):
                return
            ev["spans"]["blocks"][bi] = (entry["start_ns"], end_ns)
            return
        cat = entry.get("category")
        if cat:
            ev["categories"][cat] = ev["categories"].get(cat, 0) + dur_ns
            parts = key.split(":")
            if len(parts) == 3 and parts[0] == "block":
                try:
                    bi = int(parts[1])
                except (ValueError, IndexError):
                    return
                bc = ev["block_categories"].setdefault(bi, {})
                bc[parts[2]] = bc.get(parts[2], 0) + dur_ns

    # ── CUDA realization (post-boundary only) ─────────────────────────────

    def _finalize_cuda(self) -> None:
        """Single realization pass: one sync + elapsed_time per pair.

        Called by ``finalize`` AFTER the authoritative ``sampling_end`` event
        has been emitted by the wrapper.  Never called inside
        ``sampling_start``→``sampling_end``.
        """
        if not self._cuda_enabled or not self._cuda_pairs:
            return
        try:
            t0 = time.perf_counter_ns()
            self._cuda_module.synchronize()
            self.cuda_sync_ms = (time.perf_counter_ns() - t0) / 1_000_000
        except Exception as exc:
            self.warnings.append(f"cuda_realization_failed:{type(exc).__name__}")
            self._cuda_pairs = []
            return
        for ev_start, ev_end, key, eval_idx in self._cuda_pairs:
            try:
                ms = ev_start.elapsed_time(ev_end)
                self._cuda_timings[key] = self._cuda_timings.get(key, 0.0) + ms
                if key == "forward" and eval_idx >= 0:
                    self._cuda_per_eval_forward[eval_idx] = (
                        self._cuda_per_eval_forward.get(eval_idx, 0.0) + ms
                    )
            except Exception:
                pass
        self._cuda_pairs = []

    # ── Artifact / reconciliation ─────────────────────────────────────────

    def _build_artifact(self) -> dict[str, Any]:
        if self.rejected:
            return {
                "schema_version": SCHEMA_VERSION,
                "level": self.level,
                "status": "rejected",
                "clocks": {"host": "monotonic_ns", "cuda_events": False},
                "node_id": self.node_id,
                "node_class": self.node_class,
                "request_id": str(getattr(self.trace, "request_id", "")),
                "steps": self.steps,
                "authoritative_sampling_window_ms": None,
                "callbacks": {"observed_indices": [], "expected": []},
                "evals": {"count": 0, "expected": 2 * self.steps + 1, "per_eval": []},
                "compute_or_skip": {"compute": 0, "skip": 0, "unknown": 0},
                "reconciliation": {},
                "categories_ms": {},
                "blocks": [],
                "attention_backend": self._attention_backend_artifact(
                    requested=self.requested_backend or None
                ),
                "cachedit": {"discoverable": False},
                "errors": [],
                "warnings": list(self.warnings)[:50],
                "instrumentation_overhead": {
                    "placement": "post_sampling_end_cleanup",
                    "finalize_ms": round(self.finalize_host_ms, 3),
                    "cuda_sync_ms": round(self.cuda_sync_ms, 3),
                },
            }
        start_ns = self.sampling_start_mono_ns
        end_ns = self.sampling_end_mono_ns
        steps = self.steps
        evals = self.evals
        cb_list = list(self.callback_indices)
        cb_times = {idx: ns for idx, ns in cb_list if isinstance(idx, int)}
        cb_indices = [idx for idx, _ in cb_list]

        errors = list(self.errors)
        warnings = list(self.warnings)

        expected_evals = 2 * steps + 1
        if steps == 8:
            # Pinned production workflow expectation (8 steps -> indices 0..8).
            expected_cbs = list(range(EXPECTED_CALLBACKS))
        else:
            expected_cbs = list(range(steps + 1))
        if steps <= 0:
            errors.append("steps_invalid: expected positive step count")
        if len(evals) != expected_evals:
            errors.append(f"eval_count_mismatch: expected={expected_evals} observed={len(evals)}")
        if cb_indices != expected_cbs:
            if not cb_indices:
                warnings.append("callbacks_absent: step boundaries derived from eval indices only")
            else:
                errors.append(
                    f"callback_indices_mismatch: expected={expected_cbs} observed={cb_indices}"
                )

        # Per-eval payload (bounded; blocks mode adds per-eval categories).
        per_eval: list[dict[str, Any]] = []
        for ev in evals:
            d: dict[str, Any] = {
                "index": ev["index"],
                "ms": _ms(None if ev["end_ns"] is None else ev["end_ns"] - ev["start_ns"]),
                "compute_or_skip": ev["compute_or_skip"],
            }
            fwd = ev["spans"].get("forward")
            if fwd:
                d["forward_ms"] = _ms(fwd[1] - fwd[0])
            gpu_fwd = self._cuda_per_eval_forward.get(ev["index"])
            if gpu_fwd is not None:
                d["forward_gpu_ms"] = round(gpu_fwd, 3)
            if self.level == "blocks" and ev["categories"]:
                d["categories_ms"] = {k: round(v / 1e6, 3) for k, v in ev["categories"].items()}
            backend = ev.get("backend") or {}
            if backend.get("dispatch") or backend.get("calls"):
                d["attention_backend"] = {
                    "dispatch": dict(backend.get("dispatch") or {}),
                    "calls": dict(backend.get("calls") or {}),
                }
            per_eval.append(d)

        # ── Per-step decomposition (ns-precision; rounded for the payload) ──
        steps_ms: list[dict[str, Any]] = []
        step_total_ns_list: list[int] = []
        for s in range(steps):
            e0 = evals[2 * s] if len(evals) > 2 * s else None
            e1 = evals[2 * s + 1] if len(evals) > 2 * s + 1 else None
            entry: dict[str, Any] = {"step": s}
            if s == 0:
                step_start_ns = e0["start_ns"] if e0 else None
                entry["pre_model_ms"] = 0.0
                entry["pre_model_in_setup"] = True
                pre_ns: Optional[int] = 0
            else:
                cb_prev = cb_times.get(s - 1)
                if cb_prev is not None:
                    step_start_ns = cb_prev
                elif len(evals) > 2 * s - 1 and evals[2 * s - 1]["end_ns"] is not None:
                    step_start_ns = evals[2 * s - 1]["end_ns"]
                    if not cb_indices:
                        warnings.append("step_boundaries_from_evals_only")
                else:
                    step_start_ns = None
                pre_ns = None
                if e0 is not None and step_start_ns is not None:
                    pre_ns = e0["start_ns"] - step_start_ns
                    entry["pre_model_ms"] = _ms(pre_ns)
            cb_s = cb_times.get(s)
            if cb_s is not None:
                step_end_ns = cb_s
            elif e1 is not None and e1["end_ns"] is not None:
                step_end_ns = e1["end_ns"]
            else:
                step_end_ns = None
            eval0_ns: Optional[int] = None
            eval1_ns: Optional[int] = None
            gap_ns: Optional[int] = None
            post_ns: Optional[int] = None
            if e0 is not None and e0["end_ns"] is not None:
                eval0_ns = e0["end_ns"] - e0["start_ns"]
                entry["eval0_ms"] = _ms(eval0_ns)
            if e1 is not None and e1["end_ns"] is not None:
                eval1_ns = e1["end_ns"] - e1["start_ns"]
                entry["eval1_ms"] = _ms(eval1_ns)
            if e0 is not None and e0["end_ns"] is not None and e1 is not None and e1["start_ns"] is not None:
                gap_ns = e1["start_ns"] - e0["end_ns"]
                entry["gap_ms"] = _ms(gap_ns)
            if e1 is not None and e1["end_ns"] is not None and step_end_ns is not None:
                post_ns = step_end_ns - e1["end_ns"]
                entry["post_model_ms"] = _ms(post_ns)
            if step_start_ns is not None and step_end_ns is not None:
                total_ns = step_end_ns - step_start_ns
                step_total_ns_list.append(total_ns)
                entry["total_ms"] = _ms(total_ns)
                children_ns = [
                    v for v in (pre_ns, eval0_ns, gap_ns, eval1_ns, post_ns)
                    if isinstance(v, int)
                ]
                entry["residual_ms"] = round((total_ns - sum(children_ns)) / 1e6, 3)
            steps_ms.append(entry)

        # ── Setup / teardown / final eval (ns-precision) ──
        first_eval = evals[0] if evals else None
        setup_ns: Optional[int] = None
        setup_ms = None
        if first_eval is not None and start_ns:
            setup_ns = first_eval["start_ns"] - start_ns
            setup_ms = _ms(setup_ns)
        last_step_cb = cb_times.get(steps - 1)
        teardown_ns: Optional[int] = None
        teardown_ms = None
        if last_step_cb is not None and end_ns:
            teardown_ns = end_ns - last_step_cb
            teardown_ms = _ms(teardown_ns)
        elif evals:
            last_end = evals[-1]["end_ns"]
            if last_end is not None and end_ns:
                teardown_ns = end_ns - last_end
                teardown_ms = _ms(teardown_ns)
                if not cb_indices:
                    warnings.append("teardown_from_last_eval: callbacks absent")
        final_eval = evals[-1] if len(evals) == expected_evals and evals else None
        final_eval_ms = None
        if final_eval is not None and final_eval["end_ns"] is not None:
            final_eval_ms = _ms(final_eval["end_ns"] - final_eval["start_ns"])
        teardown_residual_ms = None
        if teardown_ns is not None and final_eval is not None and final_eval["end_ns"] is not None:
            teardown_residual_ms = round(
                (teardown_ns - (final_eval["end_ns"] - final_eval["start_ns"])) / 1e6, 3
            )

        sampling_total_ms = _ms(end_ns - start_ns) if start_ns and end_ns else None
        accounted_ns = 0.0
        if setup_ns is not None:
            accounted_ns += setup_ns
        accounted_ns += float(sum(step_total_ns_list))
        if teardown_ns is not None:
            accounted_ns += teardown_ns
        accounted_ms = round(accounted_ns / 1e6, 3) if (start_ns and end_ns) else None
        sampling_residual_ms = None
        if start_ns and end_ns:
            sampling_residual_ms = round((end_ns - start_ns - accounted_ns) / 1e6, 3)
        residual_status = "ok"
        # Residuals are exact deltas of the same perf_counter_ns boundaries, so
        # the true value is ~0; a small negative here is display rounding (max
        # ~3e-3 ms).  Only a real overlap (negative beyond rounding tolerance)
        # is flagged as an error.
        for r in [sampling_residual_ms, teardown_residual_ms] + [e.get("residual_ms") for e in steps_ms]:
            if isinstance(r, (int, float)) and r < -0.01:
                residual_status = "overlap_error"
                break

        # ── Compute / skip ──
        cs = {"compute": 0, "skip": 0, "unknown": 0}
        for ev in evals:
            cs[ev["compute_or_skip"]] = cs.get(ev["compute_or_skip"], 0) + 1

        # ── Blocks / category aggregation (blocks mode) ──
        blocks_agg: dict[int, dict[str, float]] = {}
        categories: dict[str, float] = {}
        forward_residual_negative = False
        for ev in evals:
            for cat, dur_ns in ev["categories"].items():
                categories[cat] = categories.get(cat, 0) + dur_ns
            if self.level == "blocks":
                for bi, (bs, be) in ev["spans"]["blocks"].items():
                    b = blocks_agg.setdefault(bi, {"total_ns": 0.0, "attention_ns": 0.0, "mlp_ns": 0.0, "norm_ns": 0.0})
                    b["total_ns"] += be - bs
                    bc = ev["block_categories"].get(bi, {})
                    b["attention_ns"] += bc.get("attention", 0.0)
                    b["mlp_ns"] += bc.get("mlp", 0.0)
                    b["norm_ns"] += bc.get("norm", 0.0)
                # per-eval forward residual (unhookable interleaved ops).
                fwd = ev["spans"].get("forward")
                if fwd:
                    inner = 0.0
                    for key in ("embeddings", "refiner", "output"):
                        inner += ev["categories"].get(key, 0.0)
                    inner += sum(
                        (be - bs) for bs, be in ev["spans"]["blocks"].values()
                    )
                    fr = (fwd[1] - fwd[0]) - inner
                    if fr < -1.0:
                        forward_residual_negative = True
        blocks_payload: list[dict[str, Any]] = []
        norm_gate_residual_ns = 0.0
        if self.level == "blocks":
            for bi, b in sorted(blocks_agg.items()):
                residual_ns = b["total_ns"] - b["attention_ns"] - b["mlp_ns"] - b["norm_ns"]
                norm_gate_residual_ns += residual_ns
                blocks_payload.append({
                    "block": bi,
                    "total_ms": round(b["total_ns"] / 1e6, 3),
                    "attention_ms": round(b["attention_ns"] / 1e6, 3),
                    "mlp_ms": round(b["mlp_ns"] / 1e6, 3),
                    # Directly measured norm/adaLN module hooks.
                    "norm_ms": round(b["norm_ns"] / 1e6, 3),
                    # Derived: unhookable gate/modulate/residual-add tensor ops
                    # plus launch/other gaps — NOT directly timed.
                    "norm_gate_residual_ms": round(residual_ns / 1e6, 3),
                    "residual_ms": round(residual_ns / 1e6, 3),
                })
        categories_ms = {k: round(v / 1e6, 3) for k, v in sorted(categories.items())}
        if self.level == "blocks":
            categories_ms["norm_gate_residual"] = round(norm_gate_residual_ns / 1e6, 3)
        if forward_residual_negative:
            errors.append("forward_residual_negative: unhookable interleaved ops exceed forward span")
        # Bounded CUDA-event timing results (aggregated per span key, JSON
        # scalars only); per-eval forward GPU ms live in evals.per_eval.
        cuda_timings_ms = {k: round(v, 3) for k, v in sorted(self._cuda_timings.items())}
        dispatch_counts = {
            "pytorch_override": 0,
            "sage_override": 0,
            "comfy_kitchen_int8_override": 0,
            "other_attention_override": 0,
            "unknown_attention_dispatch": 0,
        }
        for key, value in self._backend_counts.items():
            if key in dispatch_counts:
                dispatch_counts[key] = value
        pytorch_sdpa_calls = int(self._backend_counts.get("pytorch_sdpa", 0))
        kitchen_public_counts = {
            "int8_attention": int(
                self._backend_counts.get("comfy_kitchen_int8_attention", 0)
            ),
            "int8_attention_masked": int(
                self._backend_counts.get(
                    "comfy_kitchen_int8_attention_masked", 0
                )
            ),
        }
        kitchen_public_calls = sum(kitchen_public_counts.values())
        sage_public_calls = int(
            self._backend_counts.get("sageattention_sageattn", 0)
        )
        sage_sdpa_observed_evals = sum(
            1
            for ev in evals
            if (ev.get("backend") or {}).get("dispatch", {}).get("sage_override", 0)
            and (ev.get("backend") or {}).get("calls", {}).get("pytorch_sdpa", 0)
        )
        if sage_sdpa_observed_evals:
            actual_backend = "sage_override_and_pytorch_sdpa_observed_non_correlated"
        elif pytorch_sdpa_calls:
            actual_backend = "pytorch_sdpa"
        elif dispatch_counts["pytorch_override"]:
            actual_backend = "pytorch_override_without_observed_sdpa"
        elif dispatch_counts["sage_override"]:
            actual_backend = "sageattention_override_no_sdpa_observed"
        elif dispatch_counts["comfy_kitchen_int8_override"]:
            actual_backend = "comfy_kitchen_int8_override"
        elif kitchen_public_calls:
            actual_backend = "comfy_kitchen_public_observed"
        elif sage_public_calls:
            actual_backend = "sageattention_sageattn_public_observed"
        else:
            actual_backend = "unknown"
        requested_backend = self.requested_backend or None
        if requested_backend in {"sage", "comfy_kitchen"}:
            wrong = (
                pytorch_sdpa_calls
                or dispatch_counts["pytorch_override"]
                or (
                    requested_backend == "sage"
                    and dispatch_counts["comfy_kitchen_int8_override"]
                )
                or (
                    requested_backend == "comfy_kitchen"
                    and dispatch_counts["sage_override"]
                )
                or (requested_backend == "sage" and kitchen_public_calls)
                or (requested_backend == "comfy_kitchen" and sage_public_calls)
            )
            if wrong:
                errors.append(
                    f"attention_backend_fallback_or_wrong_backend:{requested_backend}"
                )
        semantics = {
            "norm_category": (
                "norm_ms is directly measured from attention/ffn RMSNorm and "
                "adaLN modulation module forward hooks"
            ),
            "norm_gate_residual": (
                "norm_gate_residual_ms is DERIVED (block_total - attention - mlp - "
                "norm); it covers unhookable gate/modulate/residual-add tensor ops "
                "and launch/other gaps, NOT directly timed"
            ),
            "step_callback_partition": (
                "for step s>0, pre_model begins at the previous callback timestamp "
                "and therefore owns the callback-to-next-eval loop tail and "
                "next-loop prep; all step spans are contiguous and non-overlapping"
            ),
            "cuda_realization": (
                "CUDA events recorded around GPU-bearing spans only; one "
                "synchronize + elapsed_time realization happens after the "
                "authoritative sampling_end event, outside the sampling window"
            ),
            "attention_backend": (
                "dispatch is identified from the actual transformer_options "
                "override closure; pytorch_sdpa is counted at ComfyUI's shared "
                "scaled_dot_product_attention seam. A Sage override plus SDPA "
                "in the aggregate evidence is observational only: the counts are "
                "not correlated per call and do not establish a fallback path. "
                "Specialized Sage exports and bounded Sage callable aliases in "
                "closure cells are counted when safely replaceable; any cell "
                "that cannot be observed is listed as closure_alias_unobservable."
            ),
            "attention_profiler": (
                "one-shot torch.profiler capture around the first requested public "
                "Sage or Comfy Kitchen call; native markers are observational and "
                "missing markers do not prove a zero native count"
            ),
        }

        # ── CacheDiT cross-check ──
        cachedit_raw = _read_cachedit_counters(self.dm, self.patcher)
        cachedit: dict[str, Any] = cachedit_raw if isinstance(cachedit_raw, dict) else {"discoverable": False}
        cachedit["expected"] = {"calls": expected_evals, "pinned_17_10_7": (steps == 8)}
        if cachedit.get("discoverable"):
            call_n = cachedit.get("call_count")
            compute_n = cachedit.get("compute_count")
            skip_n = cachedit.get("skip_count")
            if isinstance(call_n, int) and call_n != expected_evals:
                errors.append(
                    f"cachedit_call_count_mismatch: expected={expected_evals} observed={call_n}"
                )
            if steps == 8:
                pinned = EXPECTED_CACHEDIT
                if (call_n, compute_n, skip_n) != pinned:
                    errors.append(
                        f"cachedit_counter_mismatch: expected(pinned)={pinned} "
                        f"observed={(call_n, compute_n, skip_n)}"
                    )
            if isinstance(compute_n, int) and cs["unknown"] == 0 and cs["compute"] != compute_n:
                errors.append(
                    f"cachedit_hook_mismatch: hook_compute={cs['compute']} cachedit_compute={compute_n}"
                )
            if isinstance(skip_n, int) and cs["unknown"] == 0 and cs["skip"] != skip_n:
                errors.append(
                    f"cachedit_hook_mismatch: hook_skip={cs['skip']} cachedit_skip={skip_n}"
                )
        else:
            warnings.append("cachedit_counters_unavailable")

        status = "ok"
        if self.rejected:
            status = "rejected"
        elif errors:
            status = "incomplete"

        artifact: dict[str, Any] = {
            "schema_version": SCHEMA_VERSION,
            "level": self.level,
            "status": status,
            "clocks": {
                "host": "monotonic_ns",
                "cuda_events": bool(self._cuda_enabled),
            },
            "node_id": self.node_id,
            "node_class": self.node_class,
            "request_id": str(getattr(self.trace, "request_id", "")),
            "steps": steps,
            "authoritative_sampling_window_ms": sampling_total_ms,
            "callbacks": {
                "observed_indices": cb_indices,
                "expected": expected_cbs,
            },
            "evals": {
                "count": len(evals),
                "expected": expected_evals,
                "per_eval": per_eval,
            },
            "compute_or_skip": cs,
            "reconciliation": {
                "sampling_total_ms": sampling_total_ms,
                "setup_ms": setup_ms,
                "steps_ms": steps_ms,
                "teardown_ms": teardown_ms,
                "teardown_final_eval_ms": final_eval_ms,
                "teardown_residual_ms": teardown_residual_ms,
                "accounted_ms": accounted_ms,
                "sampling_residual_ms": sampling_residual_ms,
                "residual_status": residual_status,
            },
            "categories_ms": categories_ms,
            "blocks": blocks_payload,
            "cuda_timings_ms": cuda_timings_ms,
            "attention_backend": {
                "requested_backend": requested_backend,
                "actual_backend": actual_backend,
                "dispatch_counts": dispatch_counts,
                "pytorch_sdpa_calls": pytorch_sdpa_calls,
                # Retain the legacy field as null rather than making an
                # unsupported per-call fallback claim.  The useful aggregate
                # count is carried under an explicitly observational name.
                "correlated_fallback_evals": None,
                "observed_sage_sdpa_evals": sage_sdpa_observed_evals,
                "signatures": self._backend_signatures,
                "observations": self._backend_observations,
                **self._attention_backend_artifact(requested=requested_backend),
            },
            "semantics": semantics,
            "cachedit": cachedit,
            "errors": errors[:50],
            "warnings": warnings[:50],
            "instrumentation_overhead": {
                "placement": "post_sampling_end_cleanup",
                "finalize_ms": round(self.finalize_host_ms, 3),
                "cuda_sync_ms": round(self.cuda_sync_ms, 3),
            },
        }
        return artifact

    def _attention_backend_artifact(
        self, *, requested: Optional[str] = None
    ) -> dict[str, Any]:
        """Return bounded observation fields shared by normal/rejected output."""
        specialized = dict(sorted(self._specialized_counts.items()))
        fallbacks = dict(sorted(self._fallback_counts.items()))
        override_chain = list(self._override_chain)
        return {
            "requested_backend": requested,
            "original_callable_metadata": self._override_metadata,
            "original_callable": self._override_metadata,
            "original_callable_chain": override_chain,
            "override_call_count": self._override_call_count,
            # Short aliases make the fields convenient while retaining the
            # explicit names used by existing artifact consumers.
            "override_calls": self._override_call_count,
            "override_first_call": self._override_first_call,
            "first_call_descriptor": self._override_first_call,
            "override_first_call_descriptor": self._override_first_call,
            "sageattention_sageattn_calls": self._backend_counts.get(
                "sageattention_sageattn", 0
            ),
            "specialized_kernel_counts": specialized,
            "sageattention_specialized_kernel_counts": specialized,
            "sageattention_specialized_calls": specialized,
            "attention_pytorch_calls": self._backend_counts.get(
                "attention_pytorch", 0
            ),
            "pytorch_sdpa_calls": self._backend_counts.get("pytorch_sdpa", 0),
            "kitchen_public_counts": {
                "int8_attention": self._backend_counts.get(
                    "comfy_kitchen_int8_attention", 0
                ),
                "int8_attention_masked": self._backend_counts.get(
                    "comfy_kitchen_int8_attention_masked", 0
                ),
            },
            "comfy_kitchen_int8_attention_calls": self._backend_counts.get(
                "comfy_kitchen_int8_attention", 0
            ),
            "comfy_kitchen_int8_attention_masked_calls": self._backend_counts.get(
                "comfy_kitchen_int8_attention_masked", 0
            ),
            "comfy_kitchen_public_calls": sum(
                self._backend_counts.get(name, 0)
                for name in (
                    "comfy_kitchen_int8_attention",
                    "comfy_kitchen_int8_attention_masked",
                )
            ),
            "kitchen_public_first_calls": dict(self._kitchen_public_first_calls),
            "fallback_counts": fallbacks,
            "fallback_backend_counts": fallbacks,
            "backend_first_calls": self._backend_first_calls,
            "profiler_status": self._attention_profiler_status,
            "profiler_error": self._attention_profiler_error,
            "profiler_first_public_call": self._attention_profiler_call,
            "profiler": {
                "status": self._attention_profiler_status,
                "error": self._attention_profiler_error,
                "first_public_call": self._attention_profiler_call,
                "native_leaf_events": list(self._native_leaf_events)[
                    :_MAX_NATIVE_LEAF_EVENTS
                ],
            },
            "native_leaf_events": list(self._native_leaf_events)[
                :_MAX_NATIVE_LEAF_EVENTS
            ],
            "native_key_averages": list(self._native_leaf_events)[
                :_MAX_NATIVE_LEAF_EVENTS
            ],
            "native_evidence_status": (
                "observed" if self._native_leaf_events else "unproven"
            ),
            "closure_aliases": list(self._closure_aliases)[:_MAX_CLOSURE_ALIAS_RECORDS],
            "closure_alias_unobservable": list(self._closure_alias_unobservable)[:_MAX_CLOSURE_ALIAS_RECORDS],
        }

    def _restore_all(self) -> None:
        self._restore_ksampler_patch()
        self._remove_hooks()
        for kind, owner, name, original, wrapper in reversed(self._backend_patches):
            try:
                if kind == "mapping":
                    if owner.get(name, _MISSING) is wrapper:
                        owner[name] = original
                elif kind == "closure":
                    if owner.cell_contents is wrapper:
                        owner.cell_contents = original
                else:
                    if getattr(owner, name, _MISSING) is wrapper:
                        setattr(owner, name, original)
            except Exception as exc:
                self.errors.append(f"attention_observation_restore_failed:{name}:{type(exc).__name__}")
        self._backend_patches = []
        self._backend_module = None
        self._backend_original = None
        token = self._ctx_token
        self._ctx_token = None
        if token is not None:
            try:
                _CURRENT_PROFILE.reset(token)
            except Exception:
                pass

    def _finalize_inner(self, *, sampling_end_monotonic_ns: int, sampling_end_wall_unix_ns: int) -> dict[str, Any]:
        self.sampling_end_mono_ns = int(sampling_end_monotonic_ns or 0)
        self.sampling_end_wall_ns = int(sampling_end_wall_unix_ns or 0)
        if self.sampling_end_mono_ns <= 0:
            self.errors.append("sampling_end_timestamp_missing")
        if self.sampling_start_mono_ns <= 0:
            self.errors.append("sampling_start_timestamp_missing")
        try:
            self._finalize_cuda()
        except Exception as exc:
            self.warnings.append(f"cuda_realization_failed:{type(exc).__name__}")
        try:
            return self._build_artifact()
        except Exception as exc:
            return {
                "schema_version": SCHEMA_VERSION,
                "level": self.level,
                "status": "finalize_error",
                "errors": [f"artifact_build_failed:{type(exc).__name__}"],
                "warnings": list(self.warnings)[:50],
            }


# ---------------------------------------------------------------------------
# Hook closures
# ---------------------------------------------------------------------------


def _make_pre_hook(profile: SamplingDeepProfile, key: str, category: Optional[str]) -> Callable:
    def _pre(module: Any, args: Any, kwargs: Optional[dict] = None) -> None:
        if category == "attention":
            profile._record_attention_dispatch(module, args, kwargs)
        profile._span_begin(key, category)
    return _pre


def _make_post_hook(profile: SamplingDeepProfile, key: str, category: Optional[str]) -> Callable:
    def _post(module: Any, args: Any, output: Any) -> None:
        profile._span_end(key, category)
    return _post


# ---------------------------------------------------------------------------
# Public lifecycle
# ---------------------------------------------------------------------------


def begin_sampling_profile(
    trace: Any,
    *,
    level: str = _DEFAULT_LEVEL,
    node_id: str = "",
    node_class: str = "",
    steps: int = 0,
    sampling_start_monotonic_ns: int = 0,
    sampling_start_wall_unix_ns: int = 0,
    patcher: Any = None,
    requested_backend: str = "",
) -> Optional[SamplingDeepProfile]:
    """Begin a sampling deep profile for one sampler invocation.

    Returns ``None`` on the off path (no imports, no patches, no events).
    Returns a rejected profile (observation disabled) when another profiler
    already owns the class-level patch or a profile is already active in this
    context; sampling behavior is left unchanged.
    """
    level = _normalize_level(level)
    if level == "off":
        return None
    if _CURRENT_PROFILE.get() is not None:
        prof = SamplingDeepProfile(
            trace, level=level, node_id=node_id, node_class=node_class, steps=steps,
            sampling_start_monotonic_ns=sampling_start_monotonic_ns,
            sampling_start_wall_unix_ns=sampling_start_wall_unix_ns,
            patcher=patcher, dm=None,
            requested_backend=requested_backend,
        )
        prof.rejected = True
        prof.warnings.append(
            "concurrency_rejected: profile already active in this context"
        )
        return prof

    dm = None
    if patcher is not None:
        try:
            from comfymodal_runtime.unet_forward_probe import resolve_diffusion_model
            _, dm = resolve_diffusion_model(patcher)
        except Exception:
            dm = None

    profile = SamplingDeepProfile(
        trace, level=level, node_id=node_id, node_class=node_class, steps=steps,
        sampling_start_monotonic_ns=sampling_start_monotonic_ns,
        sampling_start_wall_unix_ns=sampling_start_wall_unix_ns,
        patcher=patcher, dm=dm,
        requested_backend=requested_backend,
    )
    profile._ctx_token = _CURRENT_PROFILE.set(profile)
    try:
        profile._install_ksampler_patch()
        if profile.rejected:
            profile.warnings.append(
                "concurrency_rejected: profiling disabled for this invocation"
            )
        else:
            profile._install_diffusion_hooks()
            profile._install_cuda_recorder()
            profile._install_backend_probe()
    except Exception as exc:
        profile.errors.append(f"begin_failed:{type(exc).__name__}")
    return profile


def finalize_sampling_profile(
    profile: Optional[SamplingDeepProfile],
    trace: Any,
    *,
    sampling_end_monotonic_ns: int,
    sampling_end_wall_unix_ns: int,
    sampling_end_emission_failed: bool = False,
) -> dict[str, Any]:
    """Finalize a profile and emit its artifact.

    Called by the SAMPLER_SAMPLE wrapper AFTER the authoritative
    ``sampling_end`` event has been emitted.  Any blocks-mode CUDA realization
    (one synchronize) happens here, in the post-boundary diagnostic cleanup —
    never inside ``sampling_start``→``sampling_end``.  Patches/hooks are
    restored unconditionally, even on exception.

    ``sampling_end_emission_failed`` is set by the wrapper when the
    authoritative ``sampling_end`` trace emission raised; the profile then
    records a warning and finalizes with the supplied (current) timestamps so
    restoration still runs and the class patch never leaks.
    """
    if profile is None:
        return {}
    if sampling_end_emission_failed:
        profile.warnings.append(
            "sampling_end_emission_failed: authoritative sampling_end event "
            "could not be emitted; finalized with current timestamps"
        )
    t0 = time.perf_counter_ns()
    try:
        artifact = profile._finalize_inner(
            sampling_end_monotonic_ns=sampling_end_monotonic_ns,
            sampling_end_wall_unix_ns=sampling_end_wall_unix_ns,
        )
    finally:
        profile.finalize_host_ms = (time.perf_counter_ns() - t0) / 1_000_000
        try:
            profile._restore_all()
        finally:
            profile.finalized = True
    profile.last_artifact = artifact
    if trace is not None:
        try:
            # One bounded, JSON-serializable trace event.
            payload = json.loads(json.dumps(artifact, default=str))
            trace.emit(EVENT_NAME, phase="diagnostics", metadata=payload)
        except Exception as exc:
            try:
                trace.emit(
                    EVENT_NAME,
                    phase="diagnostics",
                    metadata={
                        "schema_version": SCHEMA_VERSION,
                        "level": profile.level,
                        "status": "emit_failed",
                        "errors": [f"artifact_serialize_failed:{type(exc).__name__}"],
                    },
                )
            except Exception:
                pass
    _print_summary(artifact)
    return artifact


def _print_summary(artifact: dict[str, Any]) -> None:
    try:
        print(
            "[v2.sampling_deep_profile] "
            f"level={artifact.get('level')} status={artifact.get('status')} "
            f"steps={artifact.get('steps')} "
            f"window_ms={artifact.get('authoritative_sampling_window_ms')} "
            f"evals={artifact.get('evals', {}).get('count')} "
            f"expected={artifact.get('evals', {}).get('expected')} "
            f"compute_skip={artifact.get('compute_or_skip')} "
            f"errors={len(artifact.get('errors', []))} "
            f"warnings={len(artifact.get('warnings', []))}",
            flush=True,
        )
    except Exception:
        pass


def reset_for_tests() -> None:
    """Best-effort test cleanup: restore any lingering patch and state."""
    global _PATCH_OWNER, _LAST_PATCHED_CLASS
    with _PATCH_LOCK:
        cls = _LAST_PATCHED_CLASS
        if cls is not None:
            orig = _PATCH_ORIGINALS.pop(id(cls), None)
            if orig is not None:
                try:
                    cls.__call__ = orig
                except Exception:
                    pass
            try:
                if getattr(cls, _PATCH_MARKER, False):
                    delattr(cls, _PATCH_MARKER)
            except Exception:
                pass
            _LAST_PATCHED_CLASS = None
        _PATCH_ORIGINALS.clear()
        _PATCH_OWNER = None
    try:
        cur = _CURRENT_PROFILE.get()
        if cur is not None:
            try:
                cur._restore_all()
            except Exception:
                pass
    except Exception:
        pass
