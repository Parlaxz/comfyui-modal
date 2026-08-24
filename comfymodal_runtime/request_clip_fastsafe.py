"""Request-time CLIP FastSafe direct-GPU transport (R44B ``request_clip_fastsafe``).

E28 proved that a fastsafetensors direct-to-GPU read of the CLIP checkpoint,
followed by native Comfy construction over those CUDA tensors, removes the
CLIP cold-load from the critical path.  Historically that transport only
engaged through side channels: the Golden execution context,
``RestorePreparation`` wiring, or snapshot-captured manifests.  This module
makes it a FIRST-CLASS REQUEST-TIME loader: it engages because the request
needs a CLIP — no Golden context, no RestorePreparation, no snapshot manifest.

Engagement contract
-------------------
``install_request_clip_fastsafe()`` wraps ``NODE_CLASS_MAPPINGS["CLIPLoader"]
.load_clip``, ``NODE_CLASS_MAPPINGS["DualCLIPLoader"].load_clip`` and
``NODE_CLASS_MAPPINGS["CLIPTextEncode"].encode`` exactly once per process
(sentinel-attribute pattern, originals preserved as
``_comfymodal_r44b_original``).  When no request fast-path context is active
(``request_fastpath.current() is None``) or the CLIP lane is disabled, every
wrapper calls the original immediately: near-zero overhead, zero behavior
change.

Single physical read contract
-----------------------------
The producer performs ONE fastsafetensors direct-to-GPU read per checkpoint
file (via ``clip_fast_hydration_wiring._fastsafe_load`` — R44B baseline
threads/block/bbuf come from the profile-set environment defaults, never
hardcoded here), then temporarily overrides ``comfy.utils.load_torch_file``
with a guard that serves ONLY our resolved paths from the resident CUDA
tensors (honoring ``return_metadata``) while every other path passes through
to the saved original.  Comfy natively detects architecture/tokenizer and
constructs the CLIP from those CUDA tensors: no second file read, no CPU
materialization.  Ownership of the (loader, buffer) pairs is attached to the
produced clip via ``clip_fast_hydration.owner_attach`` so the GPU fragment
memory dies with the clip; storage identity between the bound parameters and
the transported tensors is measured honestly (``same_storage`` vs
``copy_cuda``) — either way the physical transport was FastSafe single-read.

Fail-closed fallback
--------------------
Any exception in the transport/construction window closes every loader/buffer
safely, releases the duplicate-load claim, records sticky terminal reasons
and the canonical ``native_comfy`` fallback observation, and THEN calls the
original node method so the request still succeeds natively.  Partial owners
are never left attached and partial results are never published.

Adoption modes (R44H1)
----------------------
The dtype gates classify each checkpoint into ONE adoption mode.  In
``same_storage_assign`` (checkpoint dtype == expected runtime dtype) the
native skeleton is built on ``torch.device("meta")`` and Comfy's own assign
bind ties FINAL parameter storage to the transported tensors: pointers are
shared, so the FastSafe staging owners MUST stay alive until the patcher
detaches (the ``ON_DETACH`` release point).  In ``cast_once_fp16`` (BF16
checkpoint, FP16 expectation) the skeleton is built directly on the CUDA
load device and Comfy's own ``load_state_dict(assign=False)`` performs
EXACTLY ONE BF16->FP16 conversion into final live parameter storage; values
are validated bit-exactly against the staging, residency registration stays
bookkeeping-only, and the BF16 staging owners are retired immediately after
validation (non-destructive ``retire_source_owners``, never close/purge on
the hot path) so no second model-sized materialization survives into the
forward window.  Honest nomenclature: ``cast_once_fp16`` is NOT pointer-
same-storage.  Every other dtype pair fails closed at the gates.

D15 neutrality
--------------
The CLIP lane never takes the UNET GPU gate.  This module owns no GPU-lane
coordination; the forward-boundary wrapper only measures the CLIP forward
window (the event downstream consumers may wait on) and records honest
telemetry.
"""

from __future__ import annotations

import os
import threading
import time
import traceback
from typing import Any, Callable, Optional

# ---------------------------------------------------------------------------
# Module state
# ---------------------------------------------------------------------------

_INSTALL_LOCK = threading.Lock()
_INSTALLED = False

#: Serializes the scoped construction-seam window (install -> original
#: construction -> restore) in the native producer.  The seams mutate
#: process-global ``comfy.*`` attributes, so concurrent producers on other
#: threads must not interleave installs/restores mid-window.
_SEAM_LOCK = threading.Lock()

#: Sentinel attributes (mirrors model_preload V2LoaderBridge.install).
_MARKER = "_comfymodal_r44b_request_clip_fastsafe"
_ORIGINAL_ATTR = "_comfymodal_r44b_original"

#: Reentrancy guard for the ``comfy.utils.load_torch_file`` override
#: (thread-local: a nested producer on the same thread must not stack guards).
_GUARD_LOCAL = threading.local()

_WRAPPER_TARGETS = (
    # (NODE_CLASS_MAPPINGS key, method name, clip-name parameter names)
    ("CLIPLoader", "load_clip", ("clip_name",)),
    ("DualCLIPLoader", "load_clip", ("clip_name1", "clip_name2")),
)
#: class_name -> clip-name parameter names (built ONCE from the 3-tuples;
#: ``dict(_WRAPPER_TARGETS)`` over 3-tuples would raise ValueError).
_LOAD_NAME_PARAMS: dict[str, tuple[str, ...]] = {
    class_name: name_params for class_name, _method, name_params in _WRAPPER_TARGETS
}
_FORWARD_TARGETS = (("CLIPTextEncode", "encode"),)

_CANONICAL_ARM = "fastsafetensors_direct_gpu"


def _norm(path: str) -> str:
    """Windows-safe canonical path comparison key."""
    return os.path.normcase(os.path.abspath(str(path)))


# ---------------------------------------------------------------------------
# Node-wrapper installer
# ---------------------------------------------------------------------------


def install_request_clip_fastsafe(trace: Any = None) -> bool:
    """Install the request-time CLIP FastSafe wrappers exactly once.

    Wraps ``CLIPLoader.load_clip`` / ``DualCLIPLoader.load_clip`` (producer)
    and ``CLIPTextEncode.encode`` (forward boundary) on the live
    ``nodes.NODE_CLASS_MAPPINGS`` classes.  Idempotent: returns ``True`` when
    the wrappers are (already) installed.
    """
    global _INSTALLED
    with _INSTALL_LOCK:
        if _INSTALLED:
            return True
        import nodes as nodes_module

        mappings = getattr(nodes_module, "NODE_CLASS_MAPPINGS", {})
        if not isinstance(mappings, dict):
            return False
        installed_any = False
        for class_name, method_name, _names in _WRAPPER_TARGETS:
            node_class = mappings.get(class_name)
            method = getattr(node_class, method_name, None) if node_class else None
            if not callable(method) or getattr(method, _MARKER, False):
                continue
            wrapper = _make_load_wrapper(class_name, method)
            setattr(wrapper, _MARKER, True)
            setattr(wrapper, _ORIGINAL_ATTR, method)
            setattr(node_class, method_name, wrapper)
            installed_any = True
        for class_name, method_name in _FORWARD_TARGETS:
            node_class = mappings.get(class_name)
            method = getattr(node_class, method_name, None) if node_class else None
            if not callable(method) or getattr(method, _MARKER, False):
                continue
            wrapper = _make_encode_wrapper(method)
            setattr(wrapper, _MARKER, True)
            setattr(wrapper, _ORIGINAL_ATTR, method)
            setattr(node_class, method_name, wrapper)
            installed_any = True
        if installed_any:
            _INSTALLED = True
            try:
                from . import request_fastpath

                if trace is not None:
                    ctx = request_fastpath.current()
                    if ctx is not None:
                        ctx.telemetry(
                        "clip_request_fastsafe_installed",
                        classes=[name for name, _, _ in _WRAPPER_TARGETS]
                        + [name for name, _ in _FORWARD_TARGETS],
                    )
            except Exception:
                pass
        return _INSTALLED


def uninstall_for_tests() -> None:
    """Best-effort removal of the wrappers (test lane only)."""
    global _INSTALLED
    with _INSTALL_LOCK:
        try:
            import nodes as nodes_module

            mappings = getattr(nodes_module, "NODE_CLASS_MAPPINGS", {})
            for class_name, method_name in [
                (c, m) for c, m, _ in _WRAPPER_TARGETS
            ] + list(_FORWARD_TARGETS):
                node_class = mappings.get(class_name)
                method = getattr(node_class, method_name, None) if node_class else None
                if callable(method) and getattr(method, _MARKER, False):
                    original = getattr(method, _ORIGINAL_ATTR, None)
                    if callable(original):
                        setattr(node_class, method_name, original)
        except Exception:
            pass
        _INSTALLED = False


# ---------------------------------------------------------------------------
# Wrapper factories
# ---------------------------------------------------------------------------


def _make_load_wrapper(class_key: str, original: Callable[..., Any]) -> Callable[..., Any]:
    name_params = _LOAD_NAME_PARAMS[class_key]

    def _load_wrapper(self: Any, *args: Any, **kwargs: Any) -> Any:
        # Fast path: near-zero overhead, zero behavior change.
        try:
            from . import request_fastpath

            ctx = request_fastpath.current()
            engaged = ctx is not None and request_fastpath.clip_enabled()
        except Exception:
            ctx, engaged = None, False
        if not engaged:
            return original(self, *args, **kwargs)
        # One production attempt per context: after a success OR a recorded
        # terminal fallback, later invocations go straight to the original.
        if getattr(ctx, "_comfymodal_r44b_clip_attempted", False):
            return original(self, *args, **kwargs)
        try:
            setattr(ctx, "_comfymodal_r44b_clip_attempted", True)
        except Exception:
            pass
        clip_names = _extract_clip_names(name_params, args, kwargs)
        if not clip_names:
            return original(self, *args, **kwargs)
        call_args = (self,) + args
        if _native_adopt_active():
            # R44F: native zero-copy adoption (meta construction + assign-style
            # bind).  Same fail-closed contract: any gate failure closes the
            # owners and falls back to the original node method.
            produced = _produce_clip_fastsafe_native(
                ctx, clip_names, original, call_args, kwargs
            )
        else:
            produced = _produce_clip_fastsafe(ctx, clip_names, original, call_args, kwargs)
        if produced is None:
            return original(self, *args, **kwargs)
        return produced

    _load_wrapper.__name__ = f"_comfymodal_request_fastsafe_{class_key}_load_clip"
    return _load_wrapper


def _make_encode_wrapper(original: Callable[..., Any]) -> Callable[..., Any]:
    def _encode_wrapper(self: Any, *args: Any, **kwargs: Any) -> Any:
        try:
            from . import request_fastpath

            ctx = request_fastpath.current()
            engaged = ctx is not None and request_fastpath.clip_enabled()
        except Exception:
            ctx, engaged = None, False
        if not engaged:
            return original(self, *args, **kwargs)
        allocated0 = reserved0 = None
        try:
            import torch

            allocated0 = int(torch.cuda.memory_allocated())
            reserved0 = int(torch.cuda.memory_reserved())
        except Exception:
            pass
        t0 = time.perf_counter()
        ctx.mark_clip_forward_start()
        ctx.telemetry("clip_forward_start", allocated_bytes=allocated0)
        try:
            result = original(self, *args, **kwargs)
        except Exception as exc:
            # Ensure the forward-done event always fires (it releases the
            # UNET GPU phase), then record the sticky terminal reason.
            try:
                ctx.mark_clip_forward_end()
            except Exception:
                pass
            ctx.telemetry("clip_forward_end", ok=False, error=type(exc).__name__)
            ctx.record_terminal(f"clip_forward_failed:{type(exc).__name__}", role="clip")
            raise
        wall_ms = (time.perf_counter() - t0) * 1000.0
        try:
            ctx.mark_clip_forward_end()
        except Exception:
            pass
        allocated1 = reserved1 = None
        try:
            import torch

            allocated1 = int(torch.cuda.memory_allocated())
            reserved1 = int(torch.cuda.memory_reserved())
        except Exception:
            pass
        # R44F additive instrumentation: cheap residency + model-sized-copy
        # detectors.  The forward window includes CLIP.load_model's
        # load_models_gpu call, so after it returns the produced patcher is
        # expected to be registered in current_loaded_models; a post-forward
        # allocation delta at or above the parameter bytes indicates a
        # model-sized migration actually happened during the window.
        resident_registered: Any = None
        parameter_bytes = None
        try:
            payload = ctx.result("clip")
            clip_obj = payload[0] if isinstance(payload, tuple) and len(payload) == 1 else payload
            patcher = getattr(clip_obj, "patcher", None)
            csm = getattr(clip_obj, "cond_stage_model", None)
            if csm is not None and callable(getattr(csm, "named_parameters", None)):
                parameter_bytes = sum(
                    int(p.numel()) * int(p.element_size())
                    for p in csm.parameters()
                    if not bool(getattr(p, "is_meta", False))
                )
            if patcher is not None:
                import comfy.model_management as comfy_mm

                resident_registered = any(
                    getattr(lm, "model", None) is patcher
                    for lm in comfy_mm.current_loaded_models
                )
        except Exception:
            pass
        model_sized_migration_detected = False
        if (
            allocated0 is not None
            and allocated1 is not None
            and parameter_bytes
            and (allocated1 - allocated0) >= int(0.9 * parameter_bytes)
        ):
            model_sized_migration_detected = True
        ctx.telemetry(
            "clip_forward_end",
            ok=True,
            wall_ms=round(wall_ms, 3),
            allocated_delta_bytes=(
                None if allocated0 is None or allocated1 is None else allocated1 - allocated0
            ),
            reserved_delta_bytes=(
                None if reserved0 is None or reserved1 is None else reserved1 - reserved0
            ),
            # R44F: cheap detector now runs — a delta at/above the live
            # parameter bytes flags a real model-sized migration.
            model_sized_migration_detected=model_sized_migration_detected,
            clip_parameter_bytes=parameter_bytes,
            clip_resident_registered=resident_registered,
        )
        return result

    _encode_wrapper.__name__ = "_comfymodal_request_fastsafe_clip_text_encode"
    return _encode_wrapper


def _extract_clip_names(
    name_params: tuple[str, ...], args: Any, kwargs: dict[str, Any]
) -> Optional[list[str]]:
    """Resolve the checkpoint name(s) from positional-or-keyword arguments."""
    names: list[str] = []
    for index, param in enumerate(name_params):
        if param in kwargs:
            value = kwargs[param]
        elif len(args) > index:
            value = args[index]
        else:
            return None
        if not isinstance(value, str) or not value:
            return None
        names.append(value)
    return names or None


# ---------------------------------------------------------------------------
# R44F: native zero-copy CLIP adoption (meta construction + assign bind)
# ---------------------------------------------------------------------------

#: Adoption modes (R44H1 nomenclature).
#: Parity assign: checkpoint dtype == expected runtime dtype; storages bind
#: with zero conversion (meta skeleton + assign semantics).
_MODE_SAME_STORAGE_ASSIGN = "same_storage_assign"
#: Cast-once: checkpoint BF16 -> expected FP16 happens EXACTLY ONCE, inside
#: Comfy's own load_state_dict copy, directly into FINAL live CUDA parameter
#: storage built on the load device. Temporary FastSafe BF16 staging is
#: released before forward.
_MODE_CAST_ONCE_FP16 = "cast_once_fp16"
#: Symmetric sibling (not produced by current gates; kept for completeness).
_MODE_CAST_ONCE_BF16 = "cast_once_bf16"
#: R44B/R44E legacy lane: native construction over served CUDA tensors with
#: ordinary (possibly CPU-resident) parameter materialization.
_MODE_COPY_CUDA_LEGACY = "copy_cuda_legacy"

#: (safetensors dtype, expected torch dtype name) -> adoption mode.
#: Only pairs whose conversion native Comfy itself performs identically in
#: its default load path are eligible; everything else fails closed.
_ADOPTION_DTYPE_PAIRS = {
    ("F16", "torch.float16"): _MODE_SAME_STORAGE_ASSIGN,
    ("BF16", "torch.bfloat16"): _MODE_SAME_STORAGE_ASSIGN,
    ("BF16", "torch.float16"): _MODE_CAST_ONCE_FP16,
    ("F16", "torch.bfloat16"): _MODE_CAST_ONCE_BF16,
    # FP32 parity (and the CPU test harness): zero-conversion assign bind.
    ("F32", "torch.float32"): _MODE_SAME_STORAGE_ASSIGN,
}

#: Patcher attribute marking that the ON_DETACH owner-release callback was
#: installed (idempotency latch for re-adoption of the same patcher).
_OWNER_RELEASE_HOOK_ATTR = "_comfymodal_r44f_owner_release_hook_installed"

#: Release point published in telemetry/provenance: the Comfy
#: ``CallbacksMP.ON_DETACH`` phase ("on_detach_after"), invoked by
#: ``ModelPatcher.detach(unpatch_all)`` after unpatch completes.
_OWNER_RELEASE_POINT = "on_detach_after"

# ---------------------------------------------------------------------------
# R44H3: bounded deterministic cast-once value validation
# ---------------------------------------------------------------------------
#: Default value-proof mode: structural checks run for EVERY comparable key
#: (metadata-only, O(1) per key); bit-exactness is proven on a DETERMINISTIC
#: bounded sample of each tensor instead of reading every byte.  This removes
#: the second model-sized GPU cast and the two model-sized device-to-host
#: transfers the old full ``torch.equal`` proof performed on the hot path.
_VALIDATION_MODE_BOUNDED = "bounded_deterministic_sample"
#: Diagnostic mode (opt-in via env): the historical FULL bit-exact proof —
#: every byte of both sides is read (two model-sized D2H transfers plus a
#: second model-sized staging cast).  Off by default.
_VALIDATION_MODE_DEEP = "deep_full_scan"
#: Env flag enabling the diagnostic deep/full-scan value proof.
_DEEP_VALIDATION_ENV = "COMFYMODAL_CLIP_CAST_ONCE_DEEP_VALIDATION"
#: Env override for the per-tensor sample element budget (bounded mode).
_SAMPLE_ELEMENTS_ENV = "COMFYMODAL_CLIP_CAST_ONCE_SAMPLE_ELEMENTS"
#: Default per-tensor sample budget (elements pulled to CPU per side).
_DEFAULT_SAMPLE_ELEMENTS = 256

#: safetensors dtype string -> torch dtype name (local map; this module must
#: stay free of any model_preload dependency — see
#: tests/test_r44b_request_fastsafe.py).
_SAFETENSORS_TORCH_DTYPES = {
    "F64": "float64",
    "F32": "float32",
    "F16": "float16",
    "BF16": "bfloat16",
    "F8_E4M3": "float8_e4m3fn",
    "F8_E5M2": "float8_e5m2",
    "I64": "int64",
    "I32": "int32",
    "I16": "int16",
    "I8": "int8",
    "U8": "uint8",
    "BOOL": "bool",
}

#: Keys whose presence forces native sd preprocessing transforms inside
#: ``comfy.sd.load_clip`` / ``load_text_encoder_state_dicts`` (transpose /
#: rename / full conversion).  Those transforms break storage identity, so
#: adoption is ineligible rather than silently degrading to copies.
_NATIVE_TRANSFORM_KEY_MARKERS = (
    "transformer.resblocks.",
    "scaled_fp8",
    "comfy_quant",
)

_NATIVE_TRANSFORM_EXACT_KEYS = frozenset({"text_projection", "lm_head.weight"})


def _native_adopt_active() -> bool:
    """R44F gate: request CLIP FastSafe lane AND the native-adopt flag."""
    try:
        from . import request_fastpath

        return bool(request_fastpath.clip_native_adopt_enabled())
    except Exception:
        return False


def _blob_keys() -> tuple[str, ...]:
    """Tokenizer blob key names (structural payloads, never parameters)."""
    try:
        from .clip_fast_hydration import _TOKENIZER_BLOB_KEYS

        return tuple(_TOKENIZER_BLOB_KEYS)
    except Exception:
        return ("spiece_model", "tekken_model", "tokenizer_json")


def _current_cuda_device_str() -> str:
    """``cuda:<index>`` when CUDA is usable, else ``cpu`` (test lanes)."""
    try:
        import torch

        if torch.cuda.is_available():
            return f"cuda:{torch.cuda.current_device()}"
    except Exception:
        pass
    return "cpu"


def _cuda_metrics() -> dict:
    """Best-effort CUDA allocator snapshot (absent fields on CPU lanes)."""
    out: dict[str, Any] = {}
    try:
        import torch

        if not torch.cuda.is_available():
            return out
        out["allocated"] = int(torch.cuda.memory_allocated())
        out["reserved"] = int(torch.cuda.memory_reserved())
        try:
            out["peak_allocated"] = int(torch.cuda.max_memory_allocated())
            out["peak_reserved"] = int(torch.cuda.max_memory_reserved())
        except Exception:
            pass
    except Exception:
        pass
    return out


def _reset_cuda_peak_stats() -> None:
    try:
        import torch

        if torch.cuda.is_available():
            torch.cuda.reset_peak_memory_stats()
    except Exception:
        pass


def _node_device_arg(
    name_params: tuple[str, ...], args: tuple[Any, ...], kwargs: dict[str, Any]
) -> str:
    """Resolve the node's trailing ``device`` argument (default "default")."""
    if isinstance(kwargs.get("device"), str):
        return str(kwargs["device"])
    # args[0] is self; names follow; then type; device is last positional.
    if len(args) > 2 + len(name_params) and isinstance(args[-1], str):
        return str(args[-1])
    return "default"


def _descriptor_weight_dtypes(desc: Any, blobs: tuple[str, ...]) -> set[str]:
    """Dtype strings of one descriptor's entries, excluding blob keys."""
    dtypes: set[str] = set()
    for key in desc.keys:
        if key in blobs:
            continue
        dtype = desc.dtypes.get(key)
        if dtype:
            dtypes.add(str(dtype))
    return dtypes


def _expected_te_dtype_str() -> Optional[str]:
    """The dtype the NATIVE path would give cond_stage_model parameters.

    Mirrors comfy.sd.CLIP.__init__: ``model_options.get('dtype')`` (never set
    by the CLIPLoader/DualCLIPLoader nodes for GPU loads) else
    ``model_management.text_encoder_dtype(load_device)``.  Assign-mode binds
    never cast, so parity requires the checkpoint dtype to equal this."""
    try:
        import comfy.model_management as comfy_mm

        load_device = comfy_mm.text_encoder_device()
        return str(comfy_mm.text_encoder_dtype(load_device))
    except Exception:
        return None


#: R44I3 ARM A: same-dtype residency override.  When "1", the fast arm
#: adopts the CHECKPOINT dtype as the LIVE residency dtype (BF16 checkpoint
#: -> BF16 live CLIP) instead of requiring parity with the
#: ``text_encoder_dtype`` policy (FP16).  The proven R44F parity lane binds
#: the served FastSafe CUDA tensors with ZERO conversion and ZERO second
#: representation; FP16 remains the native-fallback policy unchanged.
_SAME_DTYPE_RESIDENCY_ENV = "COMFYMODAL_V2_CLIP_SAME_DTYPE_RESIDENCY"


def _same_dtype_residency_enabled() -> bool:
    return str(os.environ.get(_SAME_DTYPE_RESIDENCY_ENV, "")).strip() == "1"


#: R44I3 ARM B: prefer a preconverted ``<name>.fp16.safetensors`` sibling on
#: the models volume (written once off the critical path) so the parity lane
#: binds FP16->FP16 with zero conversion.
_FP16_VOLUME_TWIN_ENV = "COMFYMODAL_V2_CLIP_FP16_VOLUME_TWIN"


def _fp16_volume_twin_enabled() -> bool:
    return str(os.environ.get(_FP16_VOLUME_TWIN_ENV, "")).strip() == "1"


def _native_adoption_gates(
    name_params: tuple[str, ...],
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
    descriptors: list[Any],
) -> tuple[bool, str, dict]:
    """Pre-transport eligibility gates for the R44F native construction.

    Returns ``(eligible, reason, details)``.  Every check is cheap
    (header-only descriptor data + env/model-management queries); NO tensor
    payloads are read.  Ineligibility is NOT a transport failure: the caller
    releases the claim and lets the original node method run natively."""
    details: dict = {}
    blobs = _blob_keys()

    # G1: the node's explicit CPU-device choice routes load_device to CPU;
    # a direct-GPU transport would be wasted and the bind would be wrong.
    device_arg = _node_device_arg(name_params, args, kwargs)
    details["device_arg"] = device_arg
    if device_arg == "cpu":
        return False, "cpu_device_requested", details

    # G2: CUDA must be available for the direct-GPU transport.
    try:
        import torch

        if not torch.cuda.is_available():
            return False, "cuda_unavailable", details
    except Exception:
        return False, "cuda_unavailable", details

    # G3: the native text-encoder load device must be CUDA (otherwise the
    # native path itself keeps weights on CPU and there is nothing to adopt).
    te_device_str = ""
    expected_dtype = _expected_te_dtype_str()
    details["expected_te_dtype"] = expected_dtype
    try:
        import comfy.model_management as comfy_mm

        te_device_str = str(comfy_mm.text_encoder_device())
    except Exception:
        return False, "te_device_unavailable", details
    details["te_device"] = te_device_str
    if not te_device_str.startswith("cuda"):
        return False, "te_device_not_cuda", details
    if not expected_dtype:
        return False, "te_dtype_unavailable", details

    # G4/G5/G6: per-file header gates — uniform weight dtype classified into
    # an adoption mode (R44H1: BF16+FP16 is ELIGIBLE cast-once; the old
    # ``dtype_parity_mismatch`` rejection is gone), no native-transform keys,
    # no quant evidence.
    modes: list[str] = []
    found_dtypes: list[str] = []
    residency_override = _same_dtype_residency_enabled()
    if residency_override:
        details["same_dtype_residency"] = True
    for index, desc in enumerate(descriptors):
        dtypes = _descriptor_weight_dtypes(desc, blobs)
        details[f"file_{index}_dtypes"] = sorted(dtypes)
        if len(dtypes) != 1:
            return False, f"non_uniform_dtype:file_{index}", details
        found = next(iter(dtypes))
        torch_name = _SAFETENSORS_TORCH_DTYPES.get(found)
        expected_pair = expected_dtype
        if residency_override and torch_name:
            # R44I3 ARM A: pair the checkpoint dtype with ITSELF so the
            # parity same_storage_assign lane is selected regardless of the
            # text_encoder_dtype policy.  The live CLIP then shares storage
            # with the served FastSafe CUDA tensors (zero conversion).
            expected_pair = f"torch.{torch_name}"
            details["expected_te_dtype"] = expected_pair
            details["expected_te_dtype_source"] = "same_dtype_residency_override"
        mode = (
            _ADOPTION_DTYPE_PAIRS.get((found, expected_pair))
            if expected_pair
            else None
        )
        if mode is None or torch_name is None:
            return False, f"unsupported_dtype_pair:file_{index}:{found}->{expected_pair}", details
        modes.append(mode)
        found_dtypes.append(found)
        for key in desc.keys:
            if key in blobs:
                continue
            if key in _NATIVE_TRANSFORM_EXACT_KEYS or any(
                marker in key for marker in _NATIVE_TRANSFORM_KEY_MARKERS
            ):
                return False, f"native_preprocess_transform:file_{index}", details
        meta_quant = any(
            "quant" in str(k).lower() for k in (desc.metadata or {})
        )
        if meta_quant:
            return False, f"quantized_checkpoint:file_{index}", details

    if len(set(modes)) != 1:
        return False, "mixed_adoption_modes", details
    details["checkpoint_dtype"] = found_dtypes[0]
    details["adoption_mode"] = modes[0]
    # R44I3 ARM A accounting: the text_encoder_dtype POLICY is recorded
    # separately from the EFFECTIVE live residency dtype actually adopted by
    # the fast arm, plus the explicit override marker.
    details["native_policy_te_dtype"] = expected_dtype
    if residency_override and found_dtypes:
        details.setdefault(
            "effective_live_dtype",
            f"torch.{_SAFETENSORS_TORCH_DTYPES.get(found_dtypes[0], '')}",
        )
    else:
        details["effective_live_dtype"] = expected_dtype
    details["same_dtype_residency_override"] = 1 if residency_override else 0
    details["gate_count"] = 6
    return True, "ok", details


def _return_true() -> bool:
    return True


def _return_false() -> bool:
    return False


def _install_native_construction_seams(
    targets: dict[str, tuple[dict, dict[str, str]]],
    counters: Optional[dict],
    skeleton_device: Optional[torch.device] = None,
    force_assign: bool = True,
) -> Callable[[], None]:
    """Install the scoped R44F/R44H1 construction seams; returns restore.

    Seam 1 — ``comfy.utils.load_torch_file`` guard serving OUR resolved paths
    from the resident FastSafe CUDA tensors (identical semantics to the
    legacy ``_invoke_with_guard`` guard, including ``return_metadata``).
    Always installed.

    Seam 2 — ``comfy.model_management.text_encoder_initial_device`` returns
    ``skeleton_device`` so ``CLIP.__init__`` builds cond_stage_model there:
    ``torch.device("meta")`` for the parity assign lane (zero model-sized
    allocation at construction) or the CUDA load device for cast-once (the
    skeleton IS the final FP16 storage).  Installed ONLY when
    ``skeleton_device`` is not None.

    Seam 3 — ``comfy.sd.CLIP.load_sd`` wrapper.  ``force_assign=True``
    (parity): temporarily shadows ``patcher.is_dynamic`` with an INSTANCE
    attribute returning True for the duration of each load call, so Comfy's
    own assign machinery engages (``can_assign_sd=True`` spray / ``assign=``
    kwarg).  The instance shadow is deleted as soon as each load returns, so
    the published patcher reports ``is_dynamic() == False`` like any normal
    non-dynamic ModelPatcher and downstream ``load_models_gpu`` bookkeeping
    stays on the production path.  ``force_assign=False`` (cast-once): the
    SAME instance-shadow mechanism pinned to False (R44I3 remote fix).  On
    this pinned Comfy, ``CLIP.__init__`` builds a ``CoreModelPatcher`` whose
    ``is_dynamic()`` is True, so the unpatched native dispatch sprays
    ``can_assign_sd=True`` and the recipient runs
    ``load_state_dict(assign=True)`` — ASSIGNING the BF16 checkpoint tensors
    over the FP16 skeleton with no conversion (observed remotely as
    ``bind_dtype_mismatch:model.embed_tokens.weight``).  Cast-once requires
    ``assign=False`` so Comfy performs exactly ONE BF16->FP16 copy-cast into
    the final live parameters.  The wrapper additionally records wall time /
    call counts, pin engagement counters, and the returned missing/unexpected
    keys into ``counters`` so the construction window decomposes honestly.

    All installed swaps are restored in the returned callable (only when
    nothing else swapped them meanwhile).  Default behavior when the R44F
    flag is off: none of these seams is ever installed.
    """
    import comfy.utils as comfy_utils
    import comfy.sd as comfy_sd
    import comfy.model_management as comfy_mm

    saved_ltf = comfy_utils.load_torch_file
    saved_load_sd = comfy_sd.CLIP.load_sd
    saved_initial_device = comfy_mm.text_encoder_initial_device

    def _guarded_load_torch_file(ckpt: Any, *f_args: Any, **f_kwargs: Any) -> Any:
        hit = targets.get(_norm(str(ckpt)))
        if hit is None:
            if counters is not None:
                try:
                    counters["passthrough_calls"] = (
                        int(counters.get("passthrough_calls", 0)) + 1
                    )
                except Exception:
                    pass
            return saved_ltf(ckpt, *f_args, **f_kwargs)
        if counters is not None:
            try:
                counters["served_hits"] = int(counters.get("served_hits", 0)) + 1
            except Exception:
                pass
        sd_cuda, metadata = hit
        return_metadata = bool(f_kwargs.get("return_metadata", False))
        if not return_metadata and len(f_args) >= 3:
            return_metadata = bool(f_args[2])
        if return_metadata:
            return dict(sd_cuda), metadata
        return dict(sd_cuda)

    if force_assign:

        def _load_sd_wrapper(clip_self: Any, sd: Any, full_model: bool = False) -> Any:
            patcher = getattr(clip_self, "patcher", None)
            pdict = getattr(patcher, "__dict__", None)
            added = False
            if (
                patcher is not None
                and isinstance(pdict, dict)
                and "is_dynamic" not in pdict
            ):
                try:
                    setattr(patcher, "is_dynamic", _return_true)
                    added = True
                except Exception:
                    added = False
            try:
                return saved_load_sd(clip_self, sd, full_model)
            finally:
                if added:
                    try:
                        delattr(patcher, "is_dynamic")
                    except Exception:
                        pass

    else:

        def _load_sd_wrapper(clip_self: Any, sd: Any, full_model: bool = False) -> Any:
            t_loadsd = time.perf_counter()
            # R44I3 remote fix: pin Comfy's assign decision OFF for the
            # duration of each load call (see Seam 3 docstring).  Instance
            # shadow added before / deleted after — identical lifecycle to
            # the parity lane's is_dynamic shadow above.
            patcher = getattr(clip_self, "patcher", None)
            pdict = getattr(patcher, "__dict__", None)
            added = False
            if (
                patcher is not None
                and isinstance(pdict, dict)
                and "is_dynamic" not in pdict
            ):
                if counters is not None:
                    try:
                        if bool(patcher.is_dynamic()):
                            counters["is_dynamic_observed_true_calls"] = int(
                                counters.get("is_dynamic_observed_true_calls", 0)
                            ) + 1
                    except Exception:
                        pass
                try:
                    setattr(patcher, "is_dynamic", _return_false)
                    added = True
                except Exception:
                    added = False
            if added and counters is not None:
                try:
                    counters["assign_pin_added_calls"] = int(
                        counters.get("assign_pin_added_calls", 0)
                    ) + 1
                except Exception:
                    pass
            try:
                result = saved_load_sd(clip_self, sd, full_model)
            finally:
                if added:
                    try:
                        delattr(patcher, "is_dynamic")
                    except Exception:
                        pass
            loadsd_ms = (time.perf_counter() - t_loadsd) * 1000.0
            if counters is not None:
                try:
                    counters["load_sd_wall_ms"] = (
                        float(counters.get("load_sd_wall_ms", 0.0)) + loadsd_ms
                    )
                    counters["load_sd_calls"] = int(counters.get("load_sd_calls", 0)) + 1
                    # R44I1: capture the EXACT post-transformation keyset that
                    # native Comfy hands toward the load_state_dict recipient
                    # (CLIP.load_sd input == loadsd input for this path).  A
                    # bounded sorted sample of the FIRST call is kept for the
                    # telemetry artifact; totals accumulate across calls.
                    if isinstance(sd, dict):
                        counters["loadsd_input_key_total"] = (
                            int(counters.get("loadsd_input_key_total", 0))
                            + len(sd)
                        )
                        if "loadsd_input_keys_sample" not in counters:
                            counters["loadsd_input_keys_sample"] = sorted(
                                str(k) for k in sd.keys()
                            )[:12]
                    if (
                        isinstance(result, tuple)
                        and len(result) == 2
                        and isinstance(result[0], list)
                        and isinstance(result[1], list)
                    ):
                        counters.setdefault("load_sd_missing_keys", []).extend(result[0])
                        counters.setdefault("load_sd_unexpected_keys", []).extend(
                            result[1]
                        )
                except Exception:
                    pass
            return result

    def _skeleton_initial_device(load_device: Any, offload_device: Any, model_size: int = 0) -> Any:
        return skeleton_device

    # Perform the three attribute swaps inside try/except: ANY failure
    # restores already-swapped attributes (identity-checked) before
    # re-raising, so a partial install can never leak and the returned
    # restore callable is always valid.
    swapped_ltf = False
    swapped_load_sd = False
    swapped_initial_device = False
    try:
        comfy_utils.load_torch_file = _guarded_load_torch_file
        swapped_ltf = True
        comfy_sd.CLIP.load_sd = _load_sd_wrapper
        swapped_load_sd = True
        install_initial = skeleton_device is not None
        if install_initial:
            comfy_mm.text_encoder_initial_device = _skeleton_initial_device
            swapped_initial_device = True
    except Exception:
        if swapped_ltf and comfy_utils.load_torch_file is _guarded_load_torch_file:
            comfy_utils.load_torch_file = saved_ltf
        if (
            swapped_load_sd
            and comfy_sd.CLIP.load_sd is _load_sd_wrapper
        ):
            comfy_sd.CLIP.load_sd = saved_load_sd
        if (
            swapped_initial_device
            and comfy_mm.text_encoder_initial_device is _skeleton_initial_device
        ):
            comfy_mm.text_encoder_initial_device = saved_initial_device
        raise

    def _restore() -> None:
        # Per-item guards: one failed assignment must never skip the others.
        if comfy_utils.load_torch_file is _guarded_load_torch_file:
            try:
                comfy_utils.load_torch_file = saved_ltf
            except Exception:
                pass
        if comfy_sd.CLIP.load_sd is _load_sd_wrapper:
            try:
                comfy_sd.CLIP.load_sd = saved_load_sd
            except Exception:
                pass
        if (
            install_initial
            and comfy_mm.text_encoder_initial_device is _skeleton_initial_device
        ):
            try:
                comfy_mm.text_encoder_initial_device = saved_initial_device
            except Exception:
                pass

    return _restore


def _validate_native_bind(
    clip_obj: Any,
    cuda_sds: list[dict],
    descriptors: list[Any],
) -> dict:
    """Fail-closed zero-copy validation + FULL mapping accounting.

    Raises ``RuntimeError`` (caller fail-closes to the native loader) when:

    * the produced object is not a structural CLIP (cond_stage_model /
      patcher / tokenizer), or
    * ANY parameter or buffer remains on the meta device (a missing key the
      native strict=False load would have silently tolerated — with a meta
      skeleton it could never run), or
    * ANY parameter does not share storage with a served FastSafe tensor
      (model-sized copy happened / random-init leftover) — EXCEPT ctor-owned
      leftovers OUTSIDE the native ``load_state_dict`` recipient (R44I3:
      e.g. the constant-init ``logit_scale`` parameter, created by
      ``sd1_clip.py`` on CPU regardless of skeleton device and NEVER
      checkpoint-sourced), which are counted + reported, mirroring the
      R44I1 cast-once policy.  Unbound parameters INSIDE the derived
      recipient remain hard-fatal.
    * an assigned parameter's shape/dtype diverges from its served tensor.

    On success returns the accounting dict consumed by telemetry."""
    import torch

    csm = getattr(clip_obj, "cond_stage_model", None)
    patcher = getattr(clip_obj, "patcher", None)
    tokenizer = getattr(clip_obj, "tokenizer", None)
    if csm is None or patcher is None or tokenizer is None:
        raise RuntimeError("not_a_structural_clip")

    params = list(csm.named_parameters())
    buffers = list(csm.named_buffers())

    meta_residuals = [
        name for name, t in params + buffers if bool(getattr(t, "is_meta", False))
    ]
    if meta_residuals:
        raise RuntimeError(f"meta_residual:{len(meta_residuals)}")

    served: dict[int, Any] = {}
    for sd in cuda_sds:
        for tensor in sd.values():
            try:
                if isinstance(tensor, torch.Tensor):
                    served.setdefault(int(tensor.data_ptr()), tensor)
            except Exception:
                continue

    param_ptrs: set[int] = set()
    missing_params: list[str] = []
    mismatched: list[str] = []
    parameter_bytes = 0
    devices: set[str] = set()
    dtypes: set[str] = set()
    for name, p in params:
        try:
            ptr = int(p.data_ptr())
        except Exception:
            continue
        param_ptrs.add(ptr)
        devices.add(str(p.device))
        dtypes.add(str(p.dtype))
        parameter_bytes += int(p.numel()) * int(p.element_size())
        src = served.get(ptr)
        if src is None:
            missing_params.append(name)
            continue
        if tuple(p.shape) != tuple(src.shape) or p.dtype != src.dtype:
            mismatched.append(name)
    if missing_params:
        # R44I3: classify unbound parameters against the derived native
        # recipient.  Tolerate OUTSIDE-recipient leftovers ONLY when the
        # recipient derivation is UNIQUE (the R44I1 contract); with zero,
        # multiple, or underived candidates there is no faithful recipient
        # model and the historical fatal behavior stands unchanged.
        prefixes: list[str] = []
        try:
            _blobs = _blob_keys()
            required = {
                key
                for sd in cuda_sds
                for key in sd.keys()
                if key not in _blobs
            }
            candidates = _resolve_loadsd_recipients(csm, required)
            if len(candidates) == 1:
                prefixes = [candidates[0][0]]
        except Exception:
            prefixes = []
        if prefixes:
            inside_missing = [
                name
                for name in missing_params
                if name.startswith(prefixes[0])
            ]
            outside_missing = [
                name for name in missing_params if name not in inside_missing
            ]
            extra_live_parameter_names = sorted(outside_missing)
            if inside_missing:
                raise RuntimeError(f"missing_param_storage:{len(inside_missing)}")
        else:
            extra_live_parameter_names = []
            raise RuntimeError(f"missing_param_storage:{len(missing_params)}")
    else:
        extra_live_parameter_names = []
    if mismatched:
        raise RuntimeError(f"bind_shape_dtype_mismatch:{len(mismatched)}")

    buffer_ptrs: set[int] = set()
    buffer_bytes = 0
    matched_buffers = 0
    for _name, b in buffers:
        try:
            ptr = int(b.data_ptr())
        except Exception:
            continue
        buffer_ptrs.add(ptr)
        buffer_bytes += int(b.numel()) * int(b.element_size())
        if ptr in served:
            matched_buffers += 1

    # Per-key classification against the header descriptors.
    blobs = _blob_keys()
    checkpoint_tensor_count = 0
    transformed_keys: list[str] = []
    exception_keys: list[str] = []
    direct_mappings: list[str] = []
    #: R44F full-mapping telemetry: data_ptrs of checkpoint entries classified
    #: as DIRECTLY COMPARABLE (not blobs, not preprocessing-transformed).
    comparable_ptrs: set[int] = set()
    byte_coverage = 0
    source_bytes_total = 0
    blob_bytes = 0
    for sd, desc in zip(cuda_sds, descriptors):
        for key, tensor in sd.items():
            checkpoint_tensor_count += 1
            try:
                nbytes = int(tensor.numel()) * int(tensor.element_size())
            except Exception:
                nbytes = 0
            source_bytes_total += nbytes
            if key in blobs:
                exception_keys.append(key)
                blob_bytes += nbytes
                continue
            header_shape = (desc.shapes or {}).get(key)
            header_dtype = (desc.dtypes or {}).get(key)
            if header_dtype:
                # Descriptor dtypes are safetensors strings ("F16", "BF16",
                # ...); normalize through the local map before comparing.
                torch_name = _SAFETENSORS_TORCH_DTYPES.get(str(header_dtype))
                actual_dtype = str(tensor.dtype)
                if torch_name is not None:
                    dtype_matches = actual_dtype == f"torch.{torch_name}"
                else:
                    dtype_matches = actual_dtype == str(header_dtype)
            else:
                dtype_matches = True
            if header_shape is not None and (
                tuple(tensor.shape) != tuple(header_shape) or not dtype_matches
            ):
                # Native preprocessing replaced this payload (transpose /
                # conversion): storage identity for this key is impossible.
                transformed_keys.append(key)
                continue
            try:
                ptr_hit = int(tensor.data_ptr()) in param_ptrs or int(
                    tensor.data_ptr()
                ) in buffer_ptrs
            except Exception:
                ptr_hit = False
            if ptr_hit:
                direct_mappings.append(key)
                try:
                    comparable_ptrs.add(int(tensor.data_ptr()))
                except Exception:
                    pass
                byte_coverage += nbytes
            else:
                exception_keys.append(key)

    # R44F full-mapping telemetry (purely additive, derived from the
    # already-built parameter/buffer names and the per-key classification
    # above): comparable LIVE mappings count only parameters / buffers whose
    # storage is represented by a DIRECTLY COMPARABLE checkpoint entry
    # (never blobs or transformed payloads); extra_model_tensor_count counts
    # live parameter/buffer tensors with NO comparable checkpoint entry.
    param_names = {name for name, _p in params}
    comparable_live_parameter_mappings = 0
    comparable_live_storage_mappings = 0
    extra_model_tensors = 0
    for name, t in params + buffers:
        try:
            ptr = int(t.data_ptr())
        except Exception:
            extra_model_tensors += 1
            continue
        if ptr not in comparable_ptrs:
            extra_model_tensors += 1
            continue
        comparable_live_storage_mappings += 1
        if name in param_names:
            comparable_live_parameter_mappings += 1

    same_storage_count = len(direct_mappings)
    eligible_bytes = max(0, source_bytes_total - blob_bytes)
    return {
        "checkpoint_tensor_count": checkpoint_tensor_count,
        "direct_mapping_count": same_storage_count,
        "same_storage_count": same_storage_count,
        "non_same_count": checkpoint_tensor_count - same_storage_count,
        "transformed_count": len(transformed_keys),
        "transformed_keys_sample": transformed_keys[:8],
        "exception_count": len(exception_keys),
        "exception_keys_sample": exception_keys[:8],
        "missing_parameter_count": 0,
        "extra_served_count": len(exception_keys) + len(transformed_keys),
        "comparable_live_parameter_mapping_count": comparable_live_parameter_mappings,
        "comparable_live_storage_mapping_count": comparable_live_storage_mappings,
        "extra_model_tensor_count": extra_model_tensors,
        "byte_coverage_bytes": byte_coverage,
        "source_bytes_total": source_bytes_total,
        "eligible_bytes_total": eligible_bytes,
        "byte_coverage_pct": (
            round(100.0 * byte_coverage / eligible_bytes, 3) if eligible_bytes else 0.0
        ),
        "parameter_count": len(params),
        "buffer_count": len(buffers),
        "matched_buffer_count": matched_buffers,
        "parameter_bytes": parameter_bytes,
        "buffer_bytes": buffer_bytes,
        "parameter_devices": sorted(devices),
        "parameter_dtypes": sorted(dtypes),
        # R44I3: ctor-owned leftovers outside the native recipient
        # (tolerated + reported, never fatal — see missing_params block).
        "extra_live_parameter_count": len(extra_live_parameter_names),
        "extra_live_parameter_sample": extra_live_parameter_names[:8],
    }


def _cast_once_validation_mode() -> str:
    """Resolve the cast-once value-proof mode from the environment.

    Default is the bounded deterministic sample; the deep full-scan proof is
    strictly opt-in via ``COMFYMODAL_CLIP_CAST_ONCE_DEEP_VALIDATION``."""
    try:
        raw = str(os.environ.get(_DEEP_VALIDATION_ENV, "")).strip().lower()
    except Exception:
        raw = ""
    if raw in {"1", "true", "yes", "on"}:
        return _VALIDATION_MODE_DEEP
    return _VALIDATION_MODE_BOUNDED


def _cast_once_sample_elements() -> int:
    """Per-tensor sample element budget (bounded mode); env-overridable."""
    try:
        value = int(str(os.environ.get(_SAMPLE_ELEMENTS_ENV, "")).strip())
        if value > 0:
            return value
    except Exception:
        pass
    return _DEFAULT_SAMPLE_ELEMENTS


def _bounded_sample_cpu(tensor: Any, max_elements: int) -> tuple[Any, int]:
    """Deterministically sample up to ``max_elements`` elements to CPU.

    The sample positions are a pure function of the tensor's numel (fixed
    stride over the flat index space), so the same checkpoint content always
    yields the same sample — no RNG anywhere.  Bounded by construction: at
    most ``max_elements`` elements are ever transferred host-ward.

    Contiguous tensors take the single-kernel strided-view path; the rare
    non-contiguous fallback uses scalar coordinate picks so no large
    intermediate (e.g. a model-sized ``reshape(-1)`` copy) can occur.
    Returns ``(cpu_sample_tensor, sampled_element_count)``."""
    import torch

    numel = int(tensor.numel())
    detached = tensor.detach()
    if numel == 0:
        return detached.cpu(), 0
    stride = -(-numel // max(1, int(max_elements)))
    if bool(getattr(detached, "is_contiguous", lambda: True)()):
        index = torch.arange(0, numel, stride, device=detached.device)[:max_elements]
        sample = detached.reshape(-1)[index]
        return sample.cpu(), int(sample.numel())
    shape = tuple(int(d) for d in detached.shape)
    picks: list[tuple[int, ...]] = []
    for offset in range(0, numel, stride):
        rem = offset
        coord: list[int] = []
        for dim in reversed(shape):
            coord.append(rem % dim)
            rem //= dim
        picks.append(tuple(reversed(coord)))
    picked = [detached[c] for c in picks[:max_elements]]
    if not picked:
        return detached.cpu(), 0
    sample = torch.stack(picked)
    return sample.cpu(), int(sample.numel())


#: R44I1: the historically failing checkpoint key MUST stay visible in the
#: bounded mapping-sample telemetry whenever it is present in a staged file.
_PRIORITY_MAPPING_SAMPLE_KEY = "model.embed_tokens.weight"

#: Bounded number of {source_key, loadsd_key, live_key, mapping_kind} records
#: emitted into telemetry/report artifacts.
_MAPPING_SAMPLE_LIMIT = 8


def _resolve_loadsd_recipients(
    csm: Any, required_keys: set[str]
) -> list[tuple[str, str, Any]]:
    """Deterministically derive the native ``load_state_dict`` recipient(s).

    R44I1 root-cause contract: native Comfy does NOT rename Qwen/Llama
    text-encoder keys.  The staged dict reaches
    ``<recipient>.load_state_dict(sd, strict=False, assign=...)`` VERBATIM
    (pinned ``sd1_clip.py`` ``SDClipModel.load_sd`` delegates to
    ``self.transformer.load_state_dict``), and that recipient is a nested
    module of ``cond_stage_model`` — for the pinned FLUX/Qwen3_4B path it is
    ``cond_stage_model.transformer`` (``llama.Qwen3_4B``, whose child
    ``model`` is ``Llama2_``).  torch resolves every key against the
    RECIPIENT's own namespace, so a candidate recipient is exactly any module
    in the ``cond_stage_model`` tree whose own ``state_dict()`` contains
    EVERY required key verbatim.  This mirrors
    ``torch.nn.Module.load_state_dict`` key resolution — no prefix stripping,
    no suffix heuristics, no first-match guessing.

    Returns ``(prefix, module_name, module)`` where ``prefix`` maps
    staged/loadsd keys onto OUTER ``cond_stage_model.state_dict()`` names
    ("" when the root itself is the recipient).  Because the root module is
    always traversed, zero candidates means at least one required key exists
    NOWHERE in the live tree (a true missing key); more than one candidate is
    a genuine ambiguity that must fail closed."""
    import torch

    candidates: list[tuple[str, str, Any]] = []
    for name, module in csm.named_modules():
        sd_fn = getattr(module, "state_dict", None)
        if not callable(sd_fn):
            continue
        try:
            mod_keys = {
                k for k, v in sd_fn().items() if isinstance(v, torch.Tensor)
            }
        except Exception:
            continue
        if len(mod_keys) < len(required_keys):
            continue
        if required_keys <= mod_keys:
            candidates.append(
                (f"{name}." if name else "", name or "<cond_stage_model>", module)
            )
    return candidates


def _validate_cast_once_bind(
    clip_obj: Any,
    cuda_sds: list[dict],
    descriptors: list[Any],
    expected_dtype_str: str,
    target_device_str: str,
) -> dict:
    """Fail-closed CAST-ONCE validation + accounting (R44H1/R44I1).

    The native construction built the skeleton DIRECTLY on the load device
    and Comfy's own ``load_state_dict(assign=False)`` performed exactly one
    checkpoint->expected-dtype conversion into FINAL live parameter storage.
    This validator proves that per key against the staged FastSafe tensors:

    * structural CLIP shape (cond_stage_model / patcher / tokenizer);
    * NO meta residual on any parameter or buffer;
    * every comparable staged key resolves — through the EXACT native
      ``load_state_dict`` recipient mapping derived by
      :func:`_resolve_loadsd_recipients` (unique per file, else fail-closed
      ``ambiguous_live_key``/``missing_key``) — to a live tensor with
      matching shape, EXACTLY the expected runtime dtype, a device on the
      load device, and BIT-EXACT values after the single cast;
    * any live PARAMETER without a mapped staged source fails closed
      (``unbound_parameter`` — random-init leftover).

    R44I1 namespace reconciliation: the validator no longer assumes staged
    checkpoint keys equal OUTER ``cond_stage_model.state_dict()`` names.
    Native semantics keep the loadsd keys verbatim while the recipient sits
    BELOW wrapper prefixes (Qwen3_4B: ``transformer.model.<key>`` outer ==
    ``<key>`` at the recipient), so validation targets the same logical
    weight correspondence native Comfy actually loaded.

    Raises ``RuntimeError`` (caller fail-closes to the native loader) on any
    violation; returns the accounting dict consumed by telemetry.  Nominal
    value proof is a deterministic, per-tensor bounded sample.  The former
    full-tensor proof remains available only through the explicit diagnostic
    environment flag."""
    import torch

    csm = getattr(clip_obj, "cond_stage_model", None)
    patcher = getattr(clip_obj, "patcher", None)
    tokenizer = getattr(clip_obj, "tokenizer", None)
    if csm is None or patcher is None or tokenizer is None:
        raise RuntimeError("not_a_structural_clip")

    params = list(csm.named_parameters())
    buffers = list(csm.named_buffers())

    meta_residuals = [
        name for name, t in params + buffers if bool(getattr(t, "is_meta", False))
    ]
    if meta_residuals:
        raise RuntimeError(f"meta_residual:{len(meta_residuals)}")

    live: dict[str, Any] = {
        name: t
        for name, t in csm.state_dict().items()
        if isinstance(t, torch.Tensor)
    }
    param_names = {name for name, _p in params}
    device_prefix = target_device_str.split(":")[0]

    blobs = _blob_keys()
    checkpoint_tensor_count = 0
    transformed_keys: list[str] = []
    exception_keys: list[str] = []
    comparable_bytes = 0
    source_bytes_total = 0
    blob_bytes = 0
    transformed_bytes = 0
    direct_bytes = 0
    remapped_bytes = 0
    alias_bytes = 0
    cast_once_count = 0
    direct_match_count = 0
    remapped_count = 0
    alias_count = 0
    comparable_param_count = 0
    comparable_storage_count = 0
    validation_mode = _cast_once_validation_mode()
    sample_elements = _cast_once_sample_elements()
    validation_sample_count = 0
    validation_sample_bytes = 0
    validation_cpu_transfer_bytes = 0
    mapping_records: list[dict[str, str]] = []
    bound_live_keys: set[str] = set()
    seen_live_ptrs: dict[int, str] = {}
    recipient_names: list[str] = []

    # ---- PASS 1 (R44I1): namespace-independent classification. ----------
    # Blob and header-transform classification needs only the staged payload
    # and the safetensors header — never the live namespace — so it runs
    # BEFORE recipient derivation and those keys never participate in it.
    comparable_per_file: list[dict[str, tuple[Any, int]]] = []
    for sd, desc in zip(cuda_sds, descriptors):
        comparable: dict[str, tuple[Any, int]] = {}
        for key, staged in sd.items():
            checkpoint_tensor_count += 1
            try:
                nbytes = int(staged.numel()) * int(staged.element_size())
            except Exception:
                nbytes = 0
            source_bytes_total += nbytes
            if key in blobs:
                exception_keys.append(key)
                blob_bytes += nbytes
                continue
            header_shape = (desc.shapes or {}).get(key)
            header_dtype = (desc.dtypes or {}).get(key)
            if header_dtype:
                # Descriptor dtypes are safetensors strings ("F16", "BF16",
                # ...); normalize through the local map before comparing.
                torch_name = _SAFETENSORS_TORCH_DTYPES.get(str(header_dtype))
                actual_dtype = str(staged.dtype)
                if torch_name is not None:
                    dtype_matches = actual_dtype == f"torch.{torch_name}"
                else:
                    dtype_matches = actual_dtype == str(header_dtype)
            else:
                dtype_matches = True
            if header_shape is not None and (
                tuple(staged.shape) != tuple(header_shape) or not dtype_matches
            ):
                # Header disagrees with the STAGED payload: the native load
                # transformed this entry (storage identity impossible), so it
                # is REPORTED, not fatal.
                transformed_keys.append(key)
                transformed_bytes += nbytes
                continue
            comparable[key] = (staged, nbytes)
        comparable_per_file.append(comparable)

    # ---- PASS 2 (R44I1): derive the EXACT native recipients. ------------
    # One unique recipient module per staged file, or fail closed.  Because
    # the root module always participates in the traversal, zero candidates
    # implies at least one required key is absent from the ENTIRE live tree.
    recipient_prefixes: list[str] = []
    for comparable in comparable_per_file:
        if not comparable:
            raise RuntimeError("no_comparable_keys")
        required = set(comparable.keys())
        candidates = _resolve_loadsd_recipients(csm, required)
        if len(candidates) > 1:
            first_key = sorted(required)[0]
            raise RuntimeError(
                f"ambiguous_live_key:{first_key}:{len(candidates)}"
            )
        if not candidates:
            absent = sorted(k for k in required if k not in live)
            raise RuntimeError(
                f"missing_key:{absent[0] if absent else sorted(required)[0]}"
            )
        prefix, module_name, _recipient_module = candidates[0]
        recipient_prefixes.append(prefix)
        recipient_names.append(module_name)
    # ---- PASS 3 (R44I1): mapped structural + bounded value proof. -------
    # Each comparable source tensor is validated against the live tensor it
    # was natively loaded INTO (recipient namespace), reached through the
    # derived wrapper prefix — never via raw-name guessing on the outer
    # module.
    for comparable, prefix in zip(comparable_per_file, recipient_prefixes):
        for key, staged_pair in comparable.items():
            staged, nbytes = staged_pair
            live_key = f"{prefix}{key}"
            bound_live_keys.add(live_key)
            t = live.get(live_key)
            if t is None:
                # Any missing comparable key is fatal: we cannot distinguish
                # ctor-initialized from silently-tolerated here.
                raise RuntimeError(f"missing_key:{key}")
            # Storage-independence proof: the live tensor must NOT alias the
            # staged tensor.  Cast-once retirement frees the staging, which
            # would invalidate any aliased live parameter.
            try:
                live_ptr = int(t.data_ptr())
                staged_ptr = int(staged.data_ptr())
            except Exception:
                live_ptr = staged_ptr = None
            if (
                live_ptr is not None
                and staged_ptr is not None
                and live_ptr == staged_ptr
            ):
                raise RuntimeError(f"aliasing_unexpected:{key}")
            # Tied/alias destination accounting: a second source resolving to
            # storage already bound by another source key.
            alias_hit = False
            if live_ptr is not None:
                prior_source = seen_live_ptrs.get(live_ptr)
                if prior_source is not None and prior_source != key:
                    alias_hit = True
                else:
                    seen_live_ptrs[live_ptr] = key
            if tuple(t.shape) != tuple(staged.shape):
                raise RuntimeError(f"bind_shape_mismatch:{key}")
            if str(t.dtype) != expected_dtype_str:
                raise RuntimeError(f"bind_dtype_mismatch:{key}")
            device_ok = str(t.device).startswith(device_prefix) and (
                ":" not in target_device_str
                or str(t.device) == target_device_str
                or target_device_str == "cpu"
            )
            if not device_ok:
                raise RuntimeError(f"bind_device_mismatch:{key}")
            if validation_mode == _VALIDATION_MODE_DEEP:
                live_value = t.detach().cpu()
                staged_value = staged.detach().to(t.dtype).cpu()
                validation_sample_count += int(live_value.numel())
                validation_sample_bytes += int(live_value.numel()) * int(t.element_size())
                validation_cpu_transfer_bytes += (
                    int(live_value.numel()) * int(t.element_size())
                    + int(staged_value.numel()) * int(staged.element_size())
                )
            else:
                live_value, live_count = _bounded_sample_cpu(t, sample_elements)
                staged_value, staged_count = _bounded_sample_cpu(staged, sample_elements)
                if live_count != staged_count:
                    raise RuntimeError(f"sample_count_mismatch:{key}")
                validation_sample_count += live_count
                validation_sample_bytes += live_count * int(t.element_size())
                validation_cpu_transfer_bytes += (
                    live_count * int(t.element_size())
                    + staged_count * int(staged.element_size())
                )
                staged_value = staged_value.to(dtype=live_value.dtype)
            if not bool(torch.equal(live_value, staged_value)):
                raise RuntimeError(f"value_mismatch:{key}")
            cast_once_count += 1
            comparable_bytes += nbytes
            comparable_storage_count += 1
            if live_key in param_names:
                comparable_param_count += 1
            if prefix:
                remapped_count += 1
                remapped_bytes += nbytes
            else:
                direct_match_count += 1
                direct_bytes += nbytes
            if alias_hit:
                alias_count += 1
                alias_bytes += nbytes
            mapping_records.append(
                {
                    "source_key": key,
                    "loadsd_key": key,
                    "live_key": live_key,
                    "mapping_kind": (
                        "native_wrapper_prefix" if prefix else "direct"
                    ),
                }
            )

    # Extra LIVE entries with no mapped staged source: parameters are
    # random-init leftovers (fail closed); buffers are ctor-initialized
    # (tolerated).  R44I1: binding is judged through the derived recipient
    # mapping (prefix + source key), so wrapper-prefixed live tensors are
    # correctly recognized as sourced.
    #
    # R44I1 native-semantics carve-out: live tensors OUTSIDE every derived
    # recipient namespace are, by pinned construction, left untouched by
    # Comfy's OWN load path as well (``SDClipModel.load_sd`` only ever loads
    # the recipient module; e.g. the constant-init ``logit_scale`` parameter
    # ``torch.tensor(4.6055)`` is never sourced from text-encoder
    # checkpoints).  The same ctor code ran here, so those tensors are
    # bit-equivalent to the native fallback's — accounted and reported,
    # never fatal.  Unbound parameters INSIDE a recipient remain fatal.
    recipient_prefix_set = set(recipient_prefixes)
    buffer_extra_count = 0
    extra_model_tensors = 0
    extra_live_parameter_count = 0
    extra_live_parameter_sample: list[str] = []
    for name in live.keys():
        if name in bound_live_keys:
            continue
        extra_model_tensors += 1
        if name in param_names:
            if recipient_prefix_set and not any(
                name.startswith(p) for p in recipient_prefix_set
            ):
                extra_live_parameter_count += 1
                if len(extra_live_parameter_sample) < 8:
                    extra_live_parameter_sample.append(name)
                continue
            raise RuntimeError(f"unbound_parameter:{name}")
        buffer_extra_count += 1

    parameter_bytes = sum(int(p.numel()) * int(p.element_size()) for _n, p in params)
    buffer_bytes = sum(int(b.numel()) * int(b.element_size()) for _n, b in buffers)
    devices = sorted({str(p.device) for _n, p in params})
    dtypes = sorted({str(p.dtype) for _n, p in params})
    eligible_bytes = max(0, source_bytes_total - blob_bytes)

    # R44I1: deterministic bounded mapping samples.  The historically
    # failing key stays ALWAYS visible when present; remaining slots fill in
    # sorted source-key order (no full 398-string console noise).
    ordered_records = sorted(mapping_records, key=lambda r: r["source_key"])
    mapping_samples: list[dict[str, str]] = [
        r
        for r in ordered_records
        if r["source_key"] == _PRIORITY_MAPPING_SAMPLE_KEY
    ][:_MAPPING_SAMPLE_LIMIT]
    for record in ordered_records:
        if len(mapping_samples) >= _MAPPING_SAMPLE_LIMIT:
            break
        if record not in mapping_samples:
            mapping_samples.append(record)
    return {
        "checkpoint_tensor_count": checkpoint_tensor_count,
        "direct_mapping_count": 0,
        "same_storage_count": 0,
        "non_same_count": checkpoint_tensor_count - cast_once_count,
        "transformed_count": len(transformed_keys),
        "transformed_keys_sample": transformed_keys[:8],
        "exception_count": len(exception_keys),
        "exception_keys_sample": exception_keys[:8],
        "missing_parameter_count": 0,
        "extra_served_count": len(exception_keys) + len(transformed_keys),
        "comparable_live_parameter_mapping_count": comparable_param_count,
        "comparable_live_storage_mapping_count": comparable_storage_count,
        "extra_model_tensor_count": extra_model_tensors,
        "byte_coverage_bytes": comparable_bytes,
        "source_bytes_total": source_bytes_total,
        "eligible_bytes_total": eligible_bytes,
        "byte_coverage_pct": (
            round(100.0 * comparable_bytes / eligible_bytes, 3)
            if eligible_bytes
            else 0.0
        ),
        "parameter_count": len(params),
        "buffer_count": len(buffers),
        "matched_buffer_count": 0,
        "parameter_bytes": parameter_bytes,
        "buffer_bytes": buffer_bytes,
        "parameter_devices": devices,
        "parameter_dtypes": dtypes,
        # --- R44H1 cast-once additions ---
        "cast_once_count": cast_once_count,
        "legacy_copy_count": 0,
        "live_parameter_dtype": (
            ", ".join(dtypes) if len(dtypes) > 1 else (dtypes[0] if dtypes else "")
        ),
        "final_live_weight_bytes": parameter_bytes,
        "buffer_extra_count": buffer_extra_count,
        "validation_mode": validation_mode,
        "validation_sample_count": validation_sample_count,
        "validation_sample_bytes": validation_sample_bytes,
        "validation_cpu_transfer_bytes": validation_cpu_transfer_bytes,
        "validation_full_model_scan": validation_mode == _VALIDATION_MODE_DEEP,
        # --- R44I1 namespace reconciliation additions ---
        "native_loadsd_input_count": sum(len(sd) for sd in cuda_sds),
        "live_parameter_key_count": len(params),
        "live_tensor_key_count": len(live),
        "recipient_module_names": recipient_names,
        "direct_match_count": direct_match_count,
        "remapped_count": remapped_count,
        "alias_count": alias_count,
        "buffer_blob_count": len(exception_keys),
        "missing_count": 0,
        "ambiguous_count": 0,
        "extra_live_parameter_count": extra_live_parameter_count,
        "extra_live_parameter_sample": extra_live_parameter_sample,
        "transformed_bytes": transformed_bytes,
        "blob_bytes": blob_bytes,
        "direct_bytes": direct_bytes,
        "remapped_bytes": remapped_bytes,
        "alias_bytes": alias_bytes,
        "validation_mapping_mode": "native_recipient_state_dict",
        "mapping_samples": mapping_samples,
    }


def _register_residency(
    ctx: Any, clip_obj: Any, parameter_bytes: Optional[int] = None
) -> dict:
    """Register the adopted CLIP patcher with model_management NOW.

    The bound parameters ARE resident VRAM from the moment the bind
    completes, but native bookkeeping only tracks registered patchers via
    ``current_loaded_models``; without early registration a subsequent UNET
    free-memory computation would under-count the live CLIP residency.
    ``force_full_load=True`` mirrors comfy.sd.CLIP.__init__'s high-VRAM arm;
    with every module already on the load device this is bookkeeping-only
    (no model-sized copy).  A cheap allocator-delta detector flags any real
    model-sized movement (delta at/above 0.9x the parameter bytes).  Never
    raises."""
    result: dict = {"registered": False}
    try:
        import comfy.model_management as comfy_mm

        patcher = getattr(clip_obj, "patcher", None)
        if patcher is None:
            return result
        t0 = time.perf_counter()
        before = _cuda_metrics()
        try:
            before["loaded_models"] = len(comfy_mm.current_loaded_models)
        except Exception:
            pass
        comfy_mm.load_models_gpu([patcher], force_full_load=True)
        after = _cuda_metrics()
        wall_ms = (time.perf_counter() - t0) * 1000.0
        movement = False
        if (
            parameter_bytes is not None
            and before.get("allocated") is not None
            and after.get("allocated") is not None
            and (int(after["allocated"]) - int(before["allocated"]))
            >= int(0.9 * int(parameter_bytes))
        ):
            movement = True
        result["wall_ms"] = wall_ms
        result["model_sized_movement_detected"] = bool(movement)
        try:
            after["loaded_models"] = len(comfy_mm.current_loaded_models)
            result["registered"] = any(
                getattr(lm, "model", None) is patcher
                for lm in comfy_mm.current_loaded_models
            )
        except Exception:
            pass
        result["before"] = before
        result["after"] = after
        ctx.telemetry(
            "clip_fastsafe_residency_register",
            ok=True,
            registered=bool(result.get("registered")),
            force_full_load=True,
            loaded_models_before=before.get("loaded_models"),
            loaded_models_after=after.get("loaded_models"),
            allocated_before_bytes=before.get("allocated"),
            allocated_after_bytes=after.get("allocated"),
            reserved_before_bytes=before.get("reserved"),
            reserved_after_bytes=after.get("reserved"),
            model_sized_movement_detected=bool(movement),
            wall_ms=round(wall_ms, 3),
        )
    except Exception as exc:
        result["error"] = f"{type(exc).__name__}: {str(exc)[:120]}"
        ctx.telemetry(
            "clip_fastsafe_residency_register",
            ok=False,
            error=result["error"],
        )
    return result


def _install_owner_release_hook(clip_obj: Any) -> bool:
    """Install a per-adopted-patcher ``ON_DETACH`` owner-release callback.

    R44F follow-up: ``owner_attach`` retains the FastSafe (loader, buffer)
    owners on the adopted patcher, but nothing released them.  This installs
    a callback under ``comfy.patcher_extension.CallbacksMP.ON_DETACH``
    (invoked by ``ModelPatcher.detach(unpatch_all)`` AFTER unpatch) that
    calls ``clip_fast_hydration.release_owner(clip_obj)`` exactly once when
    — and only when — ``unpatch_all`` is true.  Partial detaches/offloads
    return without releasing so buffers backing live parameters are never
    closed prematurely.

    Conservative by construction: every capability the release point needs
    (patcher callback registry, ``add_callback``, the Comfy callback
    contract, and the ``release_owner`` helper) is verified BEFORE
    installation; any gap returns ``False`` so the caller can fail closed
    instead of publishing an adoption whose GPU fragment memory could never
    be reclaimed.  Idempotent: a second call on an already-hooked patcher
    returns True without adding another callback."""
    try:
        from comfy.patcher_extension import CallbacksMP

        from .clip_fast_hydration import release_owner

        if not callable(release_owner):
            return False
        release_point = str(getattr(CallbacksMP, "ON_DETACH", _OWNER_RELEASE_POINT))
        patcher = getattr(clip_obj, "patcher", None)
        if patcher is None:
            return False
        registry = getattr(patcher, "callbacks", None)
        if not isinstance(registry, dict):
            return False
        add_callback = getattr(patcher, "add_callback", None)
        if not callable(add_callback):
            return False
        if getattr(patcher, _OWNER_RELEASE_HOOK_ATTR, False):
            return True

        def _release_on_detach(_patcher: Any, unpatch_all: Any) -> None:
            # Partial detach / offload must NOT close buffers still backing
            # live parameters; only a FULL detach may release.
            if not unpatch_all:
                return
            try:
                release_owner(clip_obj)
            except Exception:
                pass

        add_callback(release_point, _release_on_detach)
        setattr(patcher, _OWNER_RELEASE_HOOK_ATTR, True)
        return True
    except Exception:
        return False


def _produce_clip_fastsafe_native(
    ctx: Any,
    clip_names: list[str],
    original_callable: Callable[..., Any],
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
) -> Optional[Any]:
    """R44F producer: ONE FastSafe direct-GPU read per file, then REAL native
    CLIP construction over those tensors with ZERO second model-sized
    allocation:

      1. Pre-transport eligibility gates (header-only; see
         :func:`_native_adoption_gates`).
      2. Identical FastSafe transport to the R44B/R44E lane (settings come
         from the profile-set environment defaults; untouched here).
      3. Scoped construction seams: load_torch_file serves our tensors,
         text_encoder_initial_device yields meta (skeleton construction),
         CLIP.load_sd forces instance-level assign semantics.  Restored in
         ``finally`` — default native behavior is untouched outside.
      4. Fail-closed validation + full mapping accounting.
      5. Owner retention on the patcher, hydration state, publication,
         sticky observed-arm truth, and early residency registration so
         ``load_models_gpu(CLIP)`` bookkeeping sees the live VRAM.

    Any failure closes every owner, records the sticky terminal reason and
    the canonical native fallback observation, and THEN calls the original
    node method (request still succeeds natively).  No half-published CLIP.
    """
    import folder_paths

    # 1) Resolve absolute paths (single targeted lookups, NO folder scans).
    #    R44I3 ARM B: when the FP16 volume-twin flag is set, a preconverted
    #    sibling ``<name>.fp16.safetensors`` (written ONCE off the request
    #    critical path by tools/preconvert_clip_fp16_volume.py) is preferred
    #    so the parity same_storage_assign lane binds FP16->FP16 with zero
    #    conversion.  Missing twin -> original checkpoint path unchanged.
    #    ``base_paths`` keeps the ORIGINAL resolution: the node method still
    #    requests it, so the construction guard must serve the twin tensors
    #    under BOTH keys.
    paths: list[str] = []
    base_paths: list[str] = []
    for name in clip_names:
        try:
            resolved = folder_paths.get_full_path("text_encoders", name)
        except Exception:
            resolved = None
        if not resolved or not os.path.isfile(resolved):
            ctx.telemetry("clip_fastsafe_skip", reason="path_unresolved", clip_name=name)
            return None
        base_paths.append(resolved)
        if _fp16_volume_twin_enabled():
            _root, _ext = os.path.splitext(resolved)
            _twin = f"{_root}.fp16{_ext}"
            try:
                if os.path.isfile(_twin):
                    ctx.telemetry(
                        "clip_fp16_volume_twin_selected",
                        requested=name,
                        twin=os.path.basename(_twin),
                    )
                    resolved = _twin
            except OSError:
                pass
        paths.append(resolved)

    # 2) Duplicate-load latch: another lane owns the physical load.
    if not ctx.claim_physical_load("clip"):
        return None

    owners: list[tuple[Any, Any]] = []
    # Initialized OUTSIDE the try so the failure arm can always reference
    # them: a half-built CLIP may have its patcher REGISTERED in
    # comfy.model_management.current_loaded_models (pinned sd.py:280-281
    # calls load_models_gpu from CLIP.__init__ itself), which must be
    # discarded before the native fallback builds another CLIP.
    clip_obj: Any = None
    owner_attach_count = 0
    try:
        import torch

        from . import loader_selection
        from . import request_fastpath
        from .clip_fast_hydration import owner_attach, mark_clip_hydrated
        from .clip_fast_hydration_wiring import _fastsafe_load

        target_device = _current_cuda_device_str()

        # 3) Header-only descriptors (freshness-checked; shared with legacy).
        descriptors = []
        descriptor_wall_ms = 0.0
        descriptor_cache_hits = 0
        for path in paths:
            desc_metrics: dict = {}
            t_desc = time.perf_counter()
            desc = request_fastpath.build_descriptor(
                "clip", path, target_device=target_device, metrics=desc_metrics
            )
            descriptor_wall_ms += (time.perf_counter() - t_desc) * 1000.0
            if desc_metrics.get("cache_hit"):
                descriptor_cache_hits += 1
            if desc is None or not desc.fresh():
                ctx.release_claim("clip", "clip_descriptor_unavailable")
                ctx.record_terminal("clip_descriptor_unavailable", role="clip")
                try:
                    loader_selection.record_observed(
                        "clip",
                        "native_comfy",
                        fallback_attempted=True,
                        fallback_loader="native_comfy",
                        fallback_reason="descriptor_unavailable",
                    )
                except Exception:
                    pass
                return None
            ctx.set_descriptor("clip", desc)
            descriptors.append(desc)

        # 4) R44F pre-transport eligibility gates (header-only).
        name_params = next(
            (
                params
                for _cls, _m, params in _WRAPPER_TARGETS
                if len(params) == len(clip_names)
            ),
            ("clip_name",),
        )
        eligible, gate_reason, gate_details = _native_adoption_gates(
            name_params, args, kwargs, descriptors
        )
        if not eligible:
            # Ineligible is NOT a transport failure: release without native
            # fallback poisoning (mirrors the UNET lane semantics), but keep
            # the sticky terminal ledger entry.
            ctx.release_claim("clip", f"ineligible:{gate_reason}")
            ctx.record_terminal(f"clip_fastsafe_ineligible:{gate_reason}", role="clip")
            ctx.telemetry(
                "clip_fastsafe_skip",
                reason="native_adoption_ineligible",
                detail=gate_reason,
                gates=gate_details,
            )
            return None

        # R44H1: per-request adoption mode selected by the dtype gates.
        # Any "cast_once_*" mode (cast_once_fp16 AND the gated
        # cast_once_bf16 pair) routes through the cast-once branch; the
        # parity/meta+assign branch is reserved for same_storage_assign.
        selected_mode = gate_details.get("adoption_mode")
        cast_mode = bool(selected_mode) and str(selected_mode).startswith("cast_once")

        # 5) Physical transport: one FastSafe direct-GPU read per file
        #    (IDENTICAL settings to the proven R44B/R44E lane).
        alloc_before = int(torch.cuda.memory_allocated())
        reserved_before = int(torch.cuda.memory_reserved())
        _reset_cuda_peak_stats()
        t0 = time.perf_counter()
        transport_metrics: dict = {}
        ctx.telemetry(
            "clip_fast_load_start",
            paths=[os.path.basename(p) for p in paths],
            device=target_device,
            tensor_count_expected=sum(len(d.keys) for d in descriptors),
            source_bytes_total=sum(int(d.size_bytes) for d in descriptors),
            descriptor_wall_ms=round(descriptor_wall_ms, 3),
            adoption_mode=selected_mode,
            checkpoint_dtype=gate_details.get("checkpoint_dtype"),
            expected_runtime_dtype=gate_details.get("expected_te_dtype"),
            native_policy_dtype=gate_details.get("native_policy_te_dtype"),
            effective_live_dtype=gate_details.get("effective_live_dtype"),
            same_dtype_residency_override=gate_details.get(
                "same_dtype_residency_override"
            ),
        )
        cuda_sds: list[dict] = []
        tensor_count = 0
        source_bytes = 0
        file_to_gpu_ms = 0.0
        for path, desc in zip(paths, descriptors):
            t_load = time.perf_counter()
            cuda_sd, loader, fb = _fastsafe_load(path, transport_metrics)
            file_to_gpu_ms += (time.perf_counter() - t_load) * 1000.0
            owners.append((loader, fb))
            cuda_sds.append(cuda_sd)
            tensor_count += len(cuda_sd)
            source_bytes += int(desc.size_bytes)
        alloc_after_fs = int(torch.cuda.memory_allocated())
        reserved_after_fs = int(torch.cuda.memory_reserved())

        # 6) SINGLE-PHYSICAL-READ native construction behind the scoped seams.
        # R44I3 ARM B: serve the (possibly twin) tensors under BOTH the
        # transported path and the ORIGINAL node-resolved path — the node
        # method still asks for the original name, and the guard must hand
        # it the twin's FP16 CUDA tensors.
        targets: dict[str, tuple[dict, dict[str, str]]] = {}
        for _base, _path, _cuda_sd, _desc in zip(
            base_paths, paths, cuda_sds, descriptors
        ):
            _entry = (_cuda_sd, dict(_desc.metadata))
            targets[_norm(_path)] = _entry
            if _norm(_base) != _norm(_path):
                targets.setdefault(_norm(_base), _entry)
        seam_counters: dict = {}
        t_construct = time.perf_counter()
        if getattr(_GUARD_LOCAL, "active", False):
            # Reentrant producer on this thread: refuse to stack seams.
            raise RuntimeError("reentrant_native_construction")
        # Serialize the whole install -> original_callable -> restore window:
        # the seams are process-global attribute swaps and must never
        # interleave with another thread's seam window.
        with _SEAM_LOCK:
            _GUARD_LOCAL.active = True
            try:
                if cast_mode:
                    # Cast-once: the skeleton IS the final FP16 storage — build it
                    # directly on the load device; Comfy's own load_state_dict
                    # (assign=False) performs the single BF16->FP16 conversion.
                    restore_seams = _install_native_construction_seams(
                        targets,
                        seam_counters,
                        skeleton_device=torch.device(target_device),
                        force_assign=False,
                    )
                else:
                    # Parity assign: meta skeleton + assign semantics, zero copy.
                    restore_seams = _install_native_construction_seams(
                        targets,
                        seam_counters,
                        skeleton_device=torch.device("meta"),
                        force_assign=True,
                    )
                try:
                    result = original_callable(*args, **kwargs)
                finally:
                    restore_seams()
            finally:
                _GUARD_LOCAL.active = False
        construct_ms = (time.perf_counter() - t_construct) * 1000.0
        wall_ms = (time.perf_counter() - t0) * 1000.0
        try:
            alloc_after_construct = int(torch.cuda.memory_allocated())
            reserved_after_construct = int(torch.cuda.memory_reserved())
        except Exception:
            alloc_after_construct = None
            reserved_after_construct = None

        clip_obj = _unwrap_single(result)
        if clip_obj is None:
            raise RuntimeError("original construction returned no CLIP object")

        # 7) Fail-closed validation + full mapping accounting (mode-specific).
        t_valid0 = time.perf_counter()
        if cast_mode:
            accounting = _validate_cast_once_bind(
                clip_obj,
                cuda_sds,
                descriptors,
                gate_details["expected_te_dtype"],
                target_device,
            )
        else:
            accounting = _validate_native_bind(clip_obj, cuda_sds, descriptors)
        valid_ms = (time.perf_counter() - t_valid0) * 1000.0

        # 8) Ownership adopt + hydration state + provenance.
        owner_attach_count = _attach_owners(clip_obj, owners)
        mark_clip_hydrated(clip_obj)
        _record_mode_best_effort(clip_obj)

        # 8b) R44F follow-up: owner-release point.  Installed per adopted
        #     patcher BEFORE any publication; an unsupported callback /
        #     ownership lifecycle fails closed into the native lane rather
        #     than publishing owners that could never be reclaimed.
        #     Cast-once keeps it as the SAFETY NET behind the early staging
        #     release below (it no-ops once owners are retired).
        hook_installed = _install_owner_release_hook(clip_obj)
        if not hook_installed:
            raise RuntimeError("owner_release_hook_install_failed")

        # Dtype-honest bind_mode: publish the actual cast-once mode name
        # (cast_once_fp16 OR cast_once_bf16), never a generic label that
        # could mask an FP16-live/BF16-expected mismatch.
        bind_mode = str(selected_mode) if cast_mode else "same_storage"
        release_point = "after_cast_validation" if cast_mode else _OWNER_RELEASE_POINT

        try:
            setattr(
                clip_obj,
                "_comfymodal_r44b_request_fastsafe",
                {
                    "paths": [os.path.basename(p) for p in paths],
                    "bind_mode": bind_mode,
                    "adoption_mode": selected_mode,
                    "tensor_count": tensor_count,
                    "source_bytes": source_bytes,
                    "owner_attach_count": owner_attach_count,
                    "device": target_device,
                    "same_storage_count": accounting["same_storage_count"],
                    "checkpoint_tensor_count": accounting["checkpoint_tensor_count"],
                    "owner_release_hook_installed": True,
                    "owner_release_point": release_point,
                },
            )
        except Exception:
            pass

        # 9) Early residency registration (bookkeeping-only; see
        #    :func:`_register_residency`).
        registration = _register_residency(
            ctx, clip_obj, accounting.get("parameter_bytes")
        )
        if not registration.get("registered", False):
            raise RuntimeError("residency_registration_failed")

        # 9b) R44H1 EARLY STAGING RELEASE (cast-once only): the FP16 live
        #     parameters no longer borrow the BF16 staging, so retire the
        #     source owners NOW — after validation+residency, BEFORE forward
        #     and publication.  ``retire_source_owners`` prefers the
        #     non-destructive storage-release API (never close/empty_cache on
        #     this hot path), fails closed on partial retirement, and clears
        #     both the caller's list and the patcher OWNER_ATTR on full
        #     success.  On failure NOTHING is closed: owners stay attached
        #     and the ON_DETACH hook remains the safety net.
        released_ok = False
        owner_release_wall_ms: Optional[float] = None
        cuda_allocated_after_source_release: Optional[int] = None
        cuda_reserved_after_source_release: Optional[int] = None
        duplicate_weight_bytes_before_forward: Optional[int] = None
        retire_result: dict = {}
        if cast_mode:
            from .clip_fast_hydration import retire_source_owners

            t_release = time.perf_counter()
            try:
                retire_result = dict(
                    retire_source_owners(
                        owners, bf16_bytes=int(source_bytes), clip=clip_obj
                    )
                )
            except Exception as exc:
                retire_result = {
                    "ok": False,
                    "owners_retired": 0,
                    "owners_failed": len(owners),
                    "owner_bytes_before": int(source_bytes),
                    "error": f"{type(exc).__name__}: {str(exc)[:120]}",
                }
            owner_release_wall_ms = round(
                (time.perf_counter() - t_release) * 1000.0, 3
            )
            released_ok = bool(retire_result.get("ok"))
            try:
                cuda_allocated_after_source_release = int(torch.cuda.memory_allocated())
                cuda_reserved_after_source_release = int(torch.cuda.memory_reserved())
            except Exception:
                pass
            duplicate_weight_bytes_before_forward = (
                0 if released_ok else int(source_bytes)
            )
            # R44H3 FAIL-CLOSED: a failed/partial source retirement means the
            # BF16/F16 staging may still be alive while publication would hand
            # out the fast CLIP — refuse to publish.  Raising here routes
            # through the outer fail-closed handler below: owners stay
            # attached for _detach_partial_owners/_fail_closed (which CLOSES
            # them), the precise failure lands in telemetry/terminal reasons,
            # and the request survives via the native lane.
            if not released_ok:
                retire_error = str(retire_result.get("error") or "").strip()
                retire_summary = (
                    "owners_retired="
                    f"{retire_result.get('owners_retired')};"
                    f"owners_failed={retire_result.get('owners_failed')}"
                )
                if retire_error:
                    retire_summary += f";error={retire_error}"
                raise RuntimeError(
                    f"cast_once_source_retirement_failed ({retire_summary})"
                )

        # 10) Success bookkeeping.  Sticky observed truth is recorded FIRST:
        #     if record_observed fails, nothing is published and the clean
        #     fallback proceeds; the reverse order could leave a published
        #     fast CLIP plus a native fallback observation.
        loader_selection.record_observed("clip", _CANONICAL_ARM)
        ctx.mark_clip_loaded()
        ctx.publish_result("clip", clip_obj)
        alloc_after = int(torch.cuda.memory_allocated())
        peak = _cuda_metrics()
        alloc_delta = alloc_after - alloc_before
        duplicate_residency_detected = (
            source_bytes > 0 and alloc_delta > int(1.5 * source_bytes)
        )
        load_sd_wall_ms = round(float(seam_counters.get("load_sd_wall_ms", 0.0)), 3)
        peak_allocated = peak.get("peak_allocated")
        temporary_duplicate_peak = (
            max(0, int(peak_allocated) - alloc_before)
            if peak_allocated is not None
            else 0
        )
        # R44I1: namespace-reconciliation telemetry (additive).  Raw vs
        # loadsd-captured vs live key counts plus the bounded mapping
        # samples; cast-mode-only fields stay absent on the parity lane.
        namespace_telemetry: dict = {
            "raw_checkpoint_key_count": tensor_count,
            "live_parameter_key_count": accounting.get("parameter_count"),
        }
        if cast_mode:
            namespace_telemetry.update(
                {
                    "transformed_loadsd_key_count": int(
                        seam_counters.get("loadsd_input_key_total", 0)
                    ),
                    "loadsd_input_keys_sample": seam_counters.get(
                        "loadsd_input_keys_sample"
                    ),
                    "key_mapping_mode": accounting.get("validation_mapping_mode"),
                    "validation_mapping_mode": accounting.get(
                        "validation_mapping_mode"
                    ),
                    "direct_key_count": accounting.get("direct_match_count"),
                    "remapped_key_count": accounting.get("remapped_count"),
                    "alias_key_count": accounting.get("alias_count"),
                    "missing_key_count": accounting.get("missing_count"),
                    "ambiguous_key_count": accounting.get("ambiguous_count"),
                    "extra_live_key_count": accounting.get(
                        "extra_live_parameter_count"
                    ),
                    "recipient_modules": accounting.get("recipient_module_names"),
                    "mapping_samples": accounting.get("mapping_samples"),
                    # R44I3: assign-pin engagement proof (cast-once only).
                    "assign_pin_added_calls": int(
                        seam_counters.get("assign_pin_added_calls", 0)
                    ),
                    "is_dynamic_observed_true_calls": int(
                        seam_counters.get("is_dynamic_observed_true_calls", 0)
                    ),
                }
            )
        ctx.telemetry(
            "clip_fast_load_end",
            ok=True,
            file_to_gpu_wall_ms=round(file_to_gpu_ms, 3),
            wall_ms=round(wall_ms, 3),
            bind_ms=round(construct_ms, 3),
            tensor_count=tensor_count,
            source_bytes=source_bytes,
            device=target_device,
            bind_mode=bind_mode,
            cuda_alloc_delta_bytes=alloc_delta,
            owner_retained=(True if not cast_mode else not released_ok),
            owner_attach_count=owner_attach_count,
            owner_release_hook_installed=hook_installed,
            owner_release_point=release_point,
            clip_device_ready=True,
            fastsafe_setup_wall_ms=transport_metrics.get("fastsafe_setup_wall_ms"),
            fastsafe_copy_wall_ms=transport_metrics.get("fastsafe_copy_wall_ms"),
            fastsafe_get_keys_wall_ms=transport_metrics.get("fastsafe_get_keys_wall_ms"),
            fastsafe_get_tensor_loop_wall_ms=transport_metrics.get(
                "fastsafe_get_tensor_loop_wall_ms"
            ),
            descriptor_wall_ms=round(descriptor_wall_ms, 3),
            descriptor_cache_hits=descriptor_cache_hits,
            cuda_allocated_before_bytes=alloc_before,
            cuda_reserved_before_bytes=reserved_before,
            cuda_allocated_after_fastsafe_bytes=alloc_after_fs,
            cuda_reserved_after_fastsafe_bytes=reserved_after_fs,
            cuda_allocated_after_construction_bytes=alloc_after_construct,
            sampled_tensor_count=accounting["same_storage_count"],
            sampled_same_storage_count=accounting["same_storage_count"],
            sampled_non_same_storage_count=accounting["non_same_count"],
            seam_served_hits=int(seam_counters.get("served_hits", 0)),
            seam_passthrough_calls=int(seam_counters.get("passthrough_calls", 0)),
            # --- R44F additions (additive; all legacy fields preserved) ---
            adoption_mode=selected_mode,
            construction_wall_ms=round(construct_ms, 3),
            validation_wall_ms=round(valid_ms, 3),
            validation_mode=accounting.get("validation_mode"),
            validation_sample_count=accounting.get("validation_sample_count", 0),
            validation_sample_bytes=accounting.get("validation_sample_bytes", 0),
            validation_cpu_transfer_bytes=accounting.get(
                "validation_cpu_transfer_bytes", 0
            ),
            validation_full_model_scan=bool(
                accounting.get("validation_full_model_scan", False)
            ),
            native_gates=gate_details,
            checkpoint_tensor_count=accounting["checkpoint_tensor_count"],
            direct_mapping_count=accounting["direct_mapping_count"],
            same_storage_count=accounting["same_storage_count"],
            non_same_storage_count=accounting["non_same_count"],
            transformed_count=accounting["transformed_count"],
            transformed_keys_sample=accounting["transformed_keys_sample"],
            exception_count=accounting["exception_count"],
            exception_keys_sample=accounting["exception_keys_sample"],
            missing_parameter_count=accounting["missing_parameter_count"],
            extra_served_count=accounting["extra_served_count"],
            comparable_live_parameter_mapping_count=accounting[
                "comparable_live_parameter_mapping_count"
            ],
            comparable_live_storage_mapping_count=accounting[
                "comparable_live_storage_mapping_count"
            ],
            extra_model_tensor_count=accounting["extra_model_tensor_count"],
            byte_coverage_bytes=accounting["byte_coverage_bytes"],
            byte_coverage_pct=accounting["byte_coverage_pct"],
            parameter_count=accounting["parameter_count"],
            buffer_count=accounting["buffer_count"],
            matched_buffer_count=accounting["matched_buffer_count"],
            parameter_bytes=accounting["parameter_bytes"],
            buffer_bytes=accounting["buffer_bytes"],
            parameter_devices=accounting["parameter_devices"],
            parameter_dtypes=accounting["parameter_dtypes"],
            peak_allocated_bytes=peak.get("peak_allocated"),
            peak_reserved_bytes=peak.get("peak_reserved"),
            duplicate_residency_detected=duplicate_residency_detected,
            model_sized_copy_detected=duplicate_residency_detected,
            residency_registered=bool(registration.get("registered")),
            # --- R44H1 additions (additive; emitted for BOTH modes where the
            # value exists, None otherwise) ---
            checkpoint_dtype=gate_details.get("checkpoint_dtype"),
            expected_runtime_dtype=gate_details.get("expected_te_dtype"),
            live_parameter_dtype=(
                accounting.get("live_parameter_dtype")
                or ", ".join(accounting["parameter_dtypes"])
            ),
            comparable_tensor_count=(
                accounting["cast_once_count"]
                if cast_mode
                else accounting["direct_mapping_count"]
            ),
            cast_once_count=accounting.get("cast_once_count", 0),
            legacy_copy_count=accounting.get("legacy_copy_count", 0),
            transformed_exception_count=accounting["transformed_count"],
            missing_count=accounting["missing_parameter_count"],
            extra_count=accounting["extra_model_tensor_count"],
            checkpoint_bytes=source_bytes,
            final_live_weight_bytes=accounting["parameter_bytes"],
            temporary_source_bytes_peak=source_bytes,
            temporary_duplicate_weight_bytes_peak=temporary_duplicate_peak,
            duplicate_weight_bytes_before_forward=duplicate_weight_bytes_before_forward,
            load_sd_wall_ms=load_sd_wall_ms,
            construction_ex_loadsd_wall_ms=round(
                max(0.0, construct_ms - load_sd_wall_ms), 3
            ),
            owner_release_wall_ms=owner_release_wall_ms,
            owner_release_method=(
                "retire_source_owners" if cast_mode else None
            ),
            owners_retired=retire_result.get("owners_retired"),
            owners_failed=retire_result.get("owners_failed"),
            owner_bytes_before=retire_result.get("owner_bytes_before"),
            residency_register_wall_ms=(
                round(float(registration["wall_ms"]), 3)
                if registration.get("wall_ms") is not None
                else None
            ),
            cuda_reserved_after_construction_bytes=reserved_after_construct,
            cuda_allocated_after_source_release_bytes=cuda_allocated_after_source_release,
            cuda_reserved_after_source_release_bytes=cuda_reserved_after_source_release,
            model_sized_movement_detected=bool(
                registration.get("model_sized_movement_detected")
            ),
            **namespace_telemetry,
        )
        return result
    except Exception as exc:
        # C) Fail-closed fallback: never leave partial owners attached, never
        # publish a partial result, never leave a half-built patcher
        # registered, then let the original succeed natively.
        if clip_obj is not None:
            _detach_partial_owners(clip_obj, owner_attach_count)
            _discard_failed_clip(ctx, clip_obj)
        _fail_closed(ctx, owners, exc)
        return original_callable(*args, **kwargs)


def _discard_failed_clip(ctx: Any, clip_obj: Any) -> None:
    """Best-effort discard of a FAILED cast-once/native adoption's patcher.

    Pinned comfy sd.py:280-281 shows ``CLIP.__init__`` itself calls
    ``model_management.load_models_gpu([self.patcher], force_full_load=True)``
    when the skeleton device equals the load device — i.e. from our
    construction onward the patcher may already be REGISTERED in
    ``current_loaded_models``.  On any failure after construction we must not
    leave it registered while the fallback builds another CLIP.  Never
    raises; every step is individually guarded."""
    try:
        patcher = getattr(clip_obj, "patcher", None)
        if patcher is None:
            return
        import comfy.model_management as comfy_mm

        registry = getattr(comfy_mm, "current_loaded_models", None)
        if not isinstance(registry, list):
            return
        discarded = 0
        kept: list[Any] = []
        for lm in list(registry):
            try:
                if getattr(lm, "model", None) is not patcher:
                    kept.append(lm)
                    continue
                unload = getattr(lm, "model_unload", None)
                if callable(unload):
                    try:
                        unload(unpatch_all=True)
                    except TypeError:
                        try:
                            unload()
                        except Exception:
                            pass
                    except Exception:
                        pass
                discarded += 1
            except Exception:
                kept.append(lm)
        if discarded:
            registry[:] = kept
            try:
                ctx.telemetry(
                    "clip_fastsafe_failed_patchers_discarded",
                    count=int(discarded),
                )
            except Exception:
                pass
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Producer: single-physical-read FastSafe CLIP construction (R44B/R44E lane)
# ---------------------------------------------------------------------------


def _produce_clip_fastsafe(
    ctx: Any,
    clip_names: list[str],
    original_callable: Callable[..., Any],
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
) -> Optional[Any]:
    """Build the CLIP over FastSafe CUDA tensors; ``None`` => caller falls
    back to the original node method.  Fail-closed: any exception falls back
    to the original so the request still succeeds natively."""
    import folder_paths

    # 1) Resolve absolute paths (single targeted lookups, NO folder scans).
    paths: list[str] = []
    for name in clip_names:
        try:
            resolved = folder_paths.get_full_path("text_encoders", name)
        except Exception:
            resolved = None
        if not resolved or not os.path.isfile(resolved):
            ctx.telemetry("clip_fastsafe_skip", reason="path_unresolved", clip_name=name)
            return None
        paths.append(resolved)

    # 2) Duplicate-load latch: another lane owns the physical load.
    if not ctx.claim_physical_load("clip"):
        return None

    owners: list[tuple[Any, Any]] = []
    try:
        import torch

        from . import loader_selection
        from . import request_fastpath
        from .clip_fast_hydration import owner_attach, mark_clip_hydrated
        from .clip_fast_hydration_wiring import _fastsafe_load

        target_device = f"cuda:{torch.cuda.current_device()}"

        # 3) Header-only descriptors (freshness-checked; R44E sub-walls).
        descriptors = []
        descriptor_wall_ms = 0.0
        descriptor_cache_hits = 0
        for path in paths:
            desc_metrics: dict = {}
            t_desc = time.perf_counter()
            desc = request_fastpath.build_descriptor(
                "clip", path, target_device=target_device, metrics=desc_metrics
            )
            descriptor_wall_ms += (time.perf_counter() - t_desc) * 1000.0
            if desc_metrics.get("cache_hit"):
                descriptor_cache_hits += 1
            if desc is None or not desc.fresh():
                ctx.release_claim("clip", "clip_descriptor_unavailable")
                ctx.record_terminal("clip_descriptor_unavailable", role="clip")
                try:
                    from . import loader_selection

                    loader_selection.record_observed(
                        "clip",
                        "native_comfy",
                        fallback_attempted=True,
                        fallback_loader="native_comfy",
                        fallback_reason="descriptor_unavailable",
                    )
                except Exception:
                    pass
                return None
            ctx.set_descriptor("clip", desc)
            descriptors.append(desc)

        # 4) Physical transport: one FastSafe direct-GPU read per file.
        alloc_before = int(torch.cuda.memory_allocated())
        reserved_before = int(torch.cuda.memory_reserved())
        t0 = time.perf_counter()
        transport_metrics: dict = {}
        ctx.telemetry(
            "clip_fast_load_start",
            paths=[os.path.basename(p) for p in paths],
            device=target_device,
            tensor_count_expected=sum(len(d.keys) for d in descriptors),
            source_bytes_total=sum(int(d.size_bytes) for d in descriptors),
            descriptor_wall_ms=round(descriptor_wall_ms, 3),
            adoption_mode=_MODE_COPY_CUDA_LEGACY,
        )
        cuda_sds: list[dict] = []
        tensor_count = 0
        source_bytes = 0
        file_to_gpu_ms = 0.0
        for path, desc in zip(paths, descriptors):
            t_load = time.perf_counter()
            cuda_sd, loader, fb = _fastsafe_load(path, transport_metrics)
            file_to_gpu_ms += (time.perf_counter() - t_load) * 1000.0
            owners.append((loader, fb))
            cuda_sds.append(cuda_sd)
            tensor_count += len(cuda_sd)
            source_bytes += int(desc.size_bytes)
        alloc_after_fs = int(torch.cuda.memory_allocated())
        reserved_after_fs = int(torch.cuda.memory_reserved())

        # 5) SINGLE-PHYSICAL-READ construction: serve our paths from the
        # resident CUDA tensors inside comfy.utils.load_torch_file; every
        # other path passes through to the saved original.
        targets: dict[str, tuple[dict, dict[str, str]]] = {
            _norm(path): (cuda_sd, dict(desc.metadata))
            for path, cuda_sd, desc in zip(paths, cuda_sds, descriptors)
        }
        t_construct = time.perf_counter()
        seam_counters: dict = {}
        result = _invoke_with_guard(
            original_callable, args, kwargs, targets, counters=seam_counters
        )
        bind_ms = (time.perf_counter() - t_construct) * 1000.0
        wall_ms = (time.perf_counter() - t0) * 1000.0
        try:
            alloc_after_construct = int(torch.cuda.memory_allocated())
        except Exception:
            alloc_after_construct = None

        clip_obj = _unwrap_single(result)
        if clip_obj is None:
            raise RuntimeError("original construction returned no CLIP object")

        # 6) Ownership adopt + honest storage-identity proof.
        owner_attach_count = _attach_owners(clip_obj, owners)
        bind_mode, bind_counts = _storage_bind_mode(clip_obj, cuda_sds)

        # 7) Hydration state + provenance.
        mark_clip_hydrated(clip_obj)
        _record_mode_best_effort(clip_obj)
        try:
            setattr(
                clip_obj,
                "_comfymodal_r44b_request_fastsafe",
                {
                    "paths": [os.path.basename(p) for p in paths],
                    "bind_mode": bind_mode,
                    "tensor_count": tensor_count,
                    "source_bytes": source_bytes,
                    "owner_attach_count": owner_attach_count,
                    "device": target_device,
                },
            )
        except Exception:
            pass

        # 8) Success bookkeeping (observed truth recorded ONLY here).
        ctx.mark_clip_loaded()
        ctx.publish_result("clip", clip_obj)
        loader_selection.record_observed("clip", _CANONICAL_ARM)
        alloc_after = int(torch.cuda.memory_allocated())
        ctx.telemetry(
            "clip_fast_load_end",
            ok=True,
            file_to_gpu_wall_ms=round(file_to_gpu_ms, 3),
            wall_ms=round(wall_ms, 3),
            bind_ms=round(bind_ms, 3),
            tensor_count=tensor_count,
            source_bytes=source_bytes,
            device=target_device,
            bind_mode=bind_mode,
            cuda_alloc_delta_bytes=alloc_after - alloc_before,
            owner_retained=True,
            owner_attach_count=owner_attach_count,
            clip_device_ready=True,
            fastsafe_setup_wall_ms=transport_metrics.get("fastsafe_setup_wall_ms"),
            fastsafe_copy_wall_ms=transport_metrics.get("fastsafe_copy_wall_ms"),
            fastsafe_get_keys_wall_ms=transport_metrics.get("fastsafe_get_keys_wall_ms"),
            fastsafe_get_tensor_loop_wall_ms=transport_metrics.get(
                "fastsafe_get_tensor_loop_wall_ms"
            ),
            descriptor_wall_ms=round(descriptor_wall_ms, 3),
            descriptor_cache_hits=descriptor_cache_hits,
            cuda_allocated_before_bytes=alloc_before,
            cuda_reserved_before_bytes=reserved_before,
            cuda_allocated_after_fastsafe_bytes=alloc_after_fs,
            cuda_reserved_after_fastsafe_bytes=reserved_after_fs,
            cuda_allocated_after_construction_bytes=alloc_after_construct,
            sampled_tensor_count=bind_counts.get("sampled", 0),
            sampled_same_storage_count=bind_counts.get("same_storage", 0),
            sampled_non_same_storage_count=bind_counts.get("non_same_storage", 0),
            seam_served_hits=int(seam_counters.get("served_hits", 0)),
            seam_passthrough_calls=int(seam_counters.get("passthrough_calls", 0)),
            adoption_mode=_MODE_COPY_CUDA_LEGACY,
        )
        return result
    except Exception as exc:
        # C) Fail-closed fallback: never leave partial owners attached, never
        # publish a partial result, then let the original succeed natively.
        _fail_closed(ctx, owners, exc)
        return original_callable(*args, **kwargs)


def _invoke_with_guard(
    original_callable: Callable[..., Any],
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
    targets: dict[str, tuple[dict, dict[str, str]]],
    counters: Optional[dict] = None,
) -> Any:
    """Run ``original_callable`` with ``comfy.utils.load_torch_file`` guarded
    so OUR resolved paths are served from resident CUDA tensors."""
    if getattr(_GUARD_LOCAL, "active", False):
        # Reentrant producer on this thread: the outer guard is still
        # installed and will intercept; do not stack another one.
        return original_callable(*args, **kwargs)
    import comfy.utils as comfy_utils

    original_ltf = comfy_utils.load_torch_file

    def _guarded_load_torch_file(ckpt: Any, *f_args: Any, **f_kwargs: Any) -> Any:
        hit = targets.get(_norm(str(ckpt)))
        if hit is None:
            if counters is not None:
                try:
                    counters["passthrough_calls"] = (
                        int(counters.get("passthrough_calls", 0)) + 1
                    )
                except Exception:
                    pass
            return original_ltf(ckpt, *f_args, **f_kwargs)
        if counters is not None:
            try:
                counters["served_hits"] = int(counters.get("served_hits", 0)) + 1
            except Exception:
                pass
        sd_cuda, metadata = hit
        # Signature: load_torch_file(ckpt, safe_load=False, device=None,
        # return_metadata=False) — accept positional or keyword variations.
        return_metadata = bool(f_kwargs.get("return_metadata", False))
        if not return_metadata and len(f_args) >= 3:
            return_metadata = bool(f_args[2])
        if return_metadata:
            return dict(sd_cuda), metadata
        return dict(sd_cuda)

    _GUARD_LOCAL.active = True
    try:
        comfy_utils.load_torch_file = _guarded_load_torch_file
        try:
            return original_callable(*args, **kwargs)
        finally:
            # Only restore if nothing else swapped the attribute meanwhile.
            if comfy_utils.load_torch_file is _guarded_load_torch_file:
                comfy_utils.load_torch_file = original_ltf
    finally:
        _GUARD_LOCAL.active = False


def _attach_owners(clip_obj: Any, owners: list[tuple[Any, Any]]) -> int:
    """Attach (loader, fb) owners to the clip patcher, mirroring the
    ``_try_fast_hydrate`` success path.  Returns the attach count."""
    from .clip_fast_hydration import owner_attach

    attached = 0
    for loader, fb in owners:
        owner_attach(clip_obj, loader, fb)
        attached += 1
    return attached


def _detach_partial_owners(clip_obj: Any, attached: int) -> None:
    """Remove owners we attached to a half-built clip (failure cleanup)."""
    try:
        from .clip_fast_hydration import OWNER_ATTR

        patcher = getattr(clip_obj, "patcher", None)
        if patcher is None:
            return
        owners_list = getattr(patcher, OWNER_ATTR, None)
        if isinstance(owners_list, list) and attached > 0:
            del owners_list[-attached:]
            if not owners_list:
                try:
                    delattr(patcher, OWNER_ATTR)
                except Exception:
                    pass
    except Exception:
        pass


def _storage_bind_mode(clip_obj: Any, cuda_sds: list[dict]) -> tuple[str, dict]:
    """Honest storage-identity proof: compare ``data_ptr()`` of sampled
    ``cond_stage_model`` parameters against the transported CUDA tensors.
    Returns ``(bind_mode, counts)`` where counts carries the sampled /
    same-storage / non-same-storage tallies behind the mode verdict."""
    empty = {"sampled": 0, "same_storage": 0, "non_same_storage": 0}
    try:
        csm = getattr(clip_obj, "cond_stage_model", None)
        if csm is None or not callable(getattr(csm, "named_parameters", None)):
            return "copy_cuda", dict(empty)
        sd_ptrs = set()
        for sd in cuda_sds:
            for tensor in sd.values():
                try:
                    sd_ptrs.add(int(tensor.data_ptr()))
                except Exception:
                    continue
        checked = matched = 0
        for _name, param in csm.named_parameters():
            if checked >= 8:
                break
            try:
                if bool(getattr(param, "is_meta", False)):
                    continue
                checked += 1
                if int(param.data_ptr()) in sd_ptrs:
                    matched += 1
            except Exception:
                continue
        counts = {
            "sampled": checked,
            "same_storage": matched,
            "non_same_storage": checked - matched,
        }
        return ("same_storage" if matched > 0 else "copy_cuda"), counts
    except Exception:
        return "copy_cuda", dict(empty)


def _record_mode_best_effort(clip_obj: Any) -> None:
    """Reuse the historical mode recorder so downstream proof sees the same
    vocabulary; never raises (Golden-free request lane has no request id)."""
    try:
        from . import clip_fast_hydration as cfh
        from .clip_fast_hydration_wiring import _record_mode

        _record_mode(
            clip_obj,
            cfh.MODE_FASTSAFE,
            {"ok": True, "fallback_count": 0, "source": "request_time"},
        )
    except Exception:
        pass


def _unwrap_single(result: Any) -> Any:
    """Return the CLIP object from the node's ``(clip,)`` return shape."""
    if isinstance(result, tuple) and len(result) == 1:
        return result[0]
    return result


def _close_owner(loader: Any, fb: Any) -> None:
    for component in (fb, loader):
        close = getattr(component, "close", None)
        if callable(close):
            try:
                close()
            except Exception:
                pass


def _fail_closed(ctx: Any, owners: list[tuple[Any, Any]], exc: BaseException) -> None:
    """Close everything safely and record the canonical native fallback."""
    try:
        import torch

        torch.cuda.empty_cache()
    except Exception:
        pass
    for loader, fb in owners:
        _close_owner(loader, fb)
    short_reason = f"{type(exc).__name__}: {_first_line(exc)}"[:300]
    try:
        ctx.release_claim("clip", short_reason)
    except Exception:
        pass
    try:
        ctx.record_terminal(f"clip_fastsafe_failed:{type(exc).__name__}", role="clip")
    except Exception:
        pass
    try:
        from . import loader_selection

        loader_selection.record_observed(
            "clip",
            "native_comfy",
            fallback_attempted=True,
            fallback_loader="native_comfy",
            fallback_reason=short_reason,
        )
    except Exception:
        pass
    try:
        ctx.telemetry(
            "clip_fastsafe_fallback",
            error=type(exc).__name__,
            reason=short_reason,
            owners_closed=len(owners),
        )
    except Exception:
        pass


def _first_line(exc: BaseException) -> str:
    try:
        lines = traceback.format_exception_only(type(exc), exc)
        return (lines[0] if lines else "").strip().rstrip("\n")
    except Exception:
        return ""


__all__ = [
    "install_request_clip_fastsafe",
    "uninstall_for_tests",
]
