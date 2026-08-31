"""P1 Serial Golden v1 — canonical self-contained strictly-serial ComfyModal runtime.

Scope (binding spec: ``.slim/deepwork/p1-serial-golden-v1.md``, Phase 1 Oracle
gate CONDITIONAL GO for Writer A):

* This module owns ALL ComfyModal-specific Golden v1 logic.  It imports only
  stdlib, third-party packages (torch/PIL/numpy/modal), the narrow canonical
  output-durability policy module, and upstream ComfyUI modules (``nodes``,
  ``folder_paths``, ``execution``, ``comfy.*``, ``comfy_execution.*``).  The
  opt-in QD dispatcher is loaded lazily through the focused transport seam;
  this module MUST NOT import ``comfyapp``, ``modal_app``, or any broad
  golden/timing/profiler/residency/preload/speculative helper stack.
* :func:`golden_serial_execute` is the one obvious explicit top-level entry
  point.  Its body visibly calls the stages in the exact required order:
  REAL RESTORE -> ``golden_request_setup`` -> ``golden_clip_load`` ->
  ``golden_clip_forward`` -> ``golden_unet_load`` ->
  ``golden_sampler_prepare`` -> ``golden_vae_load`` -> ``golden_sampling`` ->
  ``golden_sampler_tail`` -> ``golden_vae_decode`` ->
  ``golden_output`` -> (strict-only ``golden_durable_commit``) -> committed-object
  reopen/stat/read/hash verification -> true-durable mark -> ``golden_teardown``;
  off mode marks ``FIRST_RESULT_READY`` instead.
* No cross-stage overlap, no unowned callbacks/futures/event buses/background
  prefetch.  The opt-in P4-6 diagnostic uses only reversible existing sampler
  callbacks/model hooks and never participates in workflow execution.  Internal
  QD source workers are allowed but every worker is joined and every CUDA
  completion event is waited before the load function returns.
* Every failure path is fail-closed: no historical pin/alignment fallback,
  no reread, no second H2D, no native loader fallback.

Physical QD transport ported from ``clip_qd_reader.py::read_file_qd_gpu``
(E37/E30) with the fallbacks removed; UNET constructor/adopter semantics
ported from R42 ``model_preload.py::_make_golden_load_diffusion_model_wrapper``
with the fallbacks removed; serial node execution uses upstream ComfyUI node
semantics through a narrow Golden-owned driver (never
``PromptExecutor.execute_async``).
"""

from __future__ import annotations

import asyncio
import base64
import copy
import contextlib
import contextvars
import dataclasses
import hashlib
import importlib
import inspect
import json
import logging
import math
import ntpath
import os
import posixpath
import sys
import tempfile
import threading
import time
import types
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Mapping, Optional

import torch

# Loaded through the stdlib import mechanism so the Golden module remains
# compatible with its direct file-based loader; this is the one permitted
# project-local dependency, owning the generic runtime selector.
_OUTPUT_DURABILITY = importlib.import_module(
    "comfymodal_runtime.output_durability"
)
ConfigurationError = _OUTPUT_DURABILITY.ConfigurationError
ReadyOutputArtifact = _OUTPUT_DURABILITY.ReadyOutputArtifact
resolve_output_durability = _OUTPUT_DURABILITY.resolve_output_durability

LOG = logging.getLogger("comfymodal_runtime.golden_serial")

# ── Canonical contract constants ──────────────────────────────────────────

# SHA-256 over the sorted-key compact JSON of the canonical prompt
# (independently computed by the parent orchestrator).
EXPECTED_WORKFLOW_SHA256 = "e44389ea2eda82ba5e2328acc08307b6879ed6d4ea4b030727ab044704c0d3b5"
# SHA-256 of the current canonical OUTPUT PNG bytes (NOT a workflow hash).
# The observed content hash remains authoritative; a configured expectation
# mismatch is recorded as a warning and does not prevent durability proof.
EXPECTED_OUTPUT_PNG_SHA256 = "8a92446890bebaecdc10eb5f207766a4b05af40ca3137108e25bfe88d9c1c44e"
CANONICAL_CLIP_NAME = "qwen_3_4b.safetensors"
CANONICAL_CLIP_TYPE = "lumina2"
CANONICAL_UNET_NAME = "z_image_turbo_bf16.safetensors"
CANONICAL_VAE_NAME = "ae.safetensors"
CANONICAL_SAMPLER_CLASS = "ClownsharKSampler_Beta"

# P4-6 is deliberately opt-in. The diagnostic path only observes existing
# sampler/model callbacks and CacheDiT scalar state; it never changes sampler
# inputs or performs a CUDA synchronization.
GOLDEN_SAMPLING_DIAGNOSTICS_ENV = "COMFYMODAL_GOLDEN_SAMPLING_DIAGNOSTICS"
# Cross-stage transport/CLIP/VAE diagnostics are deliberately separate from
# RA6's sampling selector.  The normal Golden path must not pay for them.
GOLDEN_STAGE_DIAGNOSTICS_ENV = "COMFYMODAL_GOLDEN_STAGE_DIAGNOSTICS"
# QD transport is an explicit experiment selector, deliberately independent
# from stage diagnostics.  ``legacy`` remains the byte-for-byte control arm.
GOLDEN_QD_TRANSPORT_ENV = "COMFYMODAL_GOLDEN_QD_TRANSPORT"
_GOLDEN_QD_ARM_CONTEXT: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "golden_qd_transport_arm", default=None
)

# RA9H CLIP residency is a request-local view of the already-registered loader
# selector.  Do not add a Golden-only alias: the canonical V2 flag is the one
# source of truth when the request does not supply a test/request override.
CLIP_FP32_CAST_ONCE_ENV = "COMFYMODAL_V2_CLIP_FP32_CAST_ONCE"
CLIP_RESIDENCY_MODES = ("bf16", "fp32_cast_once")
_CLIP_TOKENIZER_KEYS = {"spiece_model", "tekken_model", "tokenizer_json"}

# Public Golden request selector.  This is deliberately request-local; it is
# not a process/global ComfyUI attention switch.
ATTENTION_BACKENDS = ("pytorch", "sage", "comfy_kitchen")

GOLDEN_QD = 4
GOLDEN_BLOCK_BYTES = 32 * 1024 * 1024


def golden_qd_transport_arm(value: Optional[str] = None) -> str:
    """Resolve the request's explicit QD transport arm.

    The dispatcher module is imported lazily so the legacy Golden module keeps
    its existing self-contained import surface and does not make the
    experiment module part of the control arm's import path.
    """
    transport = importlib.import_module("comfymodal_runtime.golden_qd_transport")
    selected = value
    if selected is None:
        selected = _GOLDEN_QD_ARM_CONTEXT.get()
    if selected is None:
        selected = os.environ.get(GOLDEN_QD_TRANSPORT_ENV)
    return str(transport.normalize_transport_arm(selected))


@contextlib.contextmanager
def _golden_qd_transport_arm_scope(arm: str):
    token = _GOLDEN_QD_ARM_CONTEXT.set(str(arm))
    try:
        yield
    finally:
        _GOLDEN_QD_ARM_CONTEXT.reset(token)


def normalize_clip_residency(value: Any) -> str:
    """Normalize the frozen CLIP residency selector and fail closed."""
    if not isinstance(value, str):
        raise ValueError("golden_clip_residency_must_be_string")
    selected = value.strip().lower()
    if selected not in CLIP_RESIDENCY_MODES:
        raise ValueError(
            "golden_clip_residency_invalid:"
            f"{value!r}; allowed={','.join(CLIP_RESIDENCY_MODES)}"
        )
    return selected


def resolve_clip_residency(value: Optional[str] = None) -> str:
    """Resolve CLIP residency once at the request boundary.

    An omitted selector uses the canonical environment arm; an absent or
    invalid environment value follows the established safe BF16 control path.
    """
    if value is not None:
        return normalize_clip_residency(value)
    # Match the established env_flag contract: absent and explicit false-like
    # values select the BF16 control, while true-like values opt in.  Unknown
    # explicit values are safely false under that canonical parser.
    raw = os.environ.get(CLIP_FP32_CAST_ONCE_ENV)
    enabled = raw is not None and raw.strip().lower() in {"1", "true", "yes", "on"}
    return "fp32_cast_once" if enabled else "bf16"


_RA9H_TELEMETRY_FIELDS = (
    "clip_residency_requested",
    "clip_residency_effective",
    "cast_once_attempted",
    "cast_once_applied",
    "cast_once_fallback",
    "fallback_reason",
    "cast_once_fallback_reason",
    "fallback_source",
    "fatal_failure",
    "failure_classification",
    "lifecycle_phase",
    "source_generation_identity",
    "selected_tensor_count",
    "source_dtype",
    "resident_dtype",
    "compute_dtype",
    "compute_dtype_evidence",
    "expected_device",
    "cast_destination_bytes",
    "adopted_parameter_count",
    "adopted_storage_proven",
    "source_refs_dropped",
    "source_owner_retired",
    "clip_load_total_ms",
    "cast_once_transform_ms",
    "cast_once_bind_ms",
    "cast_once_proof_ms",
    "clip_forward_total_ms",
    "real_forward_count",
    "per_forward_conversion_counts",
    "per_forward_conversion_bytes",
    "repeated_conversion_count",
    "repeated_conversion_bytes",
    "forward_diagnostics_status",
    "ownership_checkpoints",
)


def _new_ra9h_telemetry(requested: str = "bf16") -> dict[str, Any]:
    """Return the bounded, flat RA9H request/run telemetry contract."""
    return {
        "clip_residency_requested": requested,
        "clip_residency_effective": requested,
        "cast_once_attempted": False,
        "cast_once_applied": False,
        "cast_once_fallback": False,
        "fallback_reason": None,
        "cast_once_fallback_reason": None,
        "fallback_source": None,
        "fatal_failure": False,
        "failure_classification": None,
        "lifecycle_phase": None,
        "source_generation_identity": None,
        "selected_tensor_count": None,
        "source_dtype": None,
        "resident_dtype": None,
        "compute_dtype": None,
        "compute_dtype_evidence": None,
        "expected_device": None,
        "cast_destination_bytes": None,
        "adopted_parameter_count": None,
        "adopted_storage_proven": None,
        "source_refs_dropped": "NOT RUN",
        "source_owner_retired": "NOT RUN",
        "clip_load_total_ms": None,
        "cast_once_transform_ms": None,
        "cast_once_bind_ms": None,
        "cast_once_proof_ms": None,
        "clip_forward_total_ms": None,
        "real_forward_count": None,
        "per_forward_conversion_counts": None,
        "per_forward_conversion_bytes": None,
        "repeated_conversion_count": None,
        "repeated_conversion_bytes": None,
        "forward_diagnostics_status": "NOT RUN",
        "ownership_checkpoints": None,
    }


def _bounded_telemetry_value(value: Any) -> Any:
    """Keep the flat request record scalar/metadata-only."""
    if value is None or isinstance(value, (str, int, bool, float)):
        return value
    if isinstance(value, Mapping):
        return {str(key): _bounded_telemetry_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_bounded_telemetry_value(item) for item in value]
    return f"<{type(value).__module__}.{type(value).__name__}>"


def _generation_identity(identity: Any) -> dict[str, Any]:
    """Keep only the bounded identity portion out of the named flat fields."""
    metadata = identity.metadata() if callable(getattr(identity, "metadata", None)) else identity
    if not isinstance(metadata, Mapping):
        return {}
    return {
        str(key): _bounded_telemetry_value(value)
        for key, value in metadata.items()
        if str(key) in {
            "checkpoint_identity", "manifest_generation", "selected_tensor_scope",
            "target_device", "cast_policy_version", "model_patch_identity", "digest",
        }
    }


def _set_ra9h_telemetry(session: Any, **updates: Any) -> None:
    """Update request-local RA9H fields and the recorder's metadata copy."""
    telemetry = getattr(session, "clip_residency_telemetry", None)
    if not isinstance(telemetry, dict):
        telemetry = _new_ra9h_telemetry(str(getattr(session, "clip_residency", "bf16")))
        session.clip_residency_telemetry = telemetry
    if "cast_once_fallback_reason" in updates and "fallback_reason" not in updates:
        updates["fallback_reason"] = updates["cast_once_fallback_reason"]
    telemetry.update({
        key: _bounded_telemetry_value(value)
        for key, value in updates.items()
        if key in _RA9H_TELEMETRY_FIELDS
    })
    run_identity = getattr(session, "run_identity", None)
    if isinstance(run_identity, dict):
        run_identity.update({
            key: telemetry[key]
            for key in ("clip_residency_requested", "clip_residency_effective")
        })
    recorder = getattr(session, "recorder", None)
    if recorder is not None:
        recorder.clip_residency_telemetry = copy.deepcopy(telemetry)
        if isinstance(run_identity, dict):
            recorder.run_identity = dict(run_identity)

# z_image_turbo_bf16 NextDiT intended parameter/buffer count (R42 evidence).
EXPECTED_UNET_TENSOR_COUNT = 453

DEFAULT_OUTPUT_ROOT = "output_assets"

# The adapter performs REAL RESTORE before handing control to this module.
# ``golden_restore`` is only the request-time observation of that handoff; it
# must not be interpreted as the restore operation or its duration.
STAGE_ORDER = (
    "golden_restore",
    "golden_request_setup",
    "golden_clip_load",
    "golden_clip_forward",
    "golden_unet_load",
    "golden_sampler_prepare",
    "golden_vae_load",
    "golden_sampling",
    "golden_sampler_tail",
    "golden_vae_decode",
    "golden_output",
    "golden_durable_commit",
)

EVENT_TRUE_FIRST_DURABLE_RESULT = "TRUE_FIRST_DURABLE_RESULT"
EVENT_FIRST_RESULT_READY = "FIRST_RESULT_READY"
EVENT_RESULT_ASSEMBLED = "RESULT_ASSEMBLED"
EVENT_TEARDOWN_COMPLETE = "TEARDOWN_COMPLETE"
EVENT_REAL_RESTORE = "REAL_RESTORE"
EVENT_OUTPUT_ENCODE_DONE = "OUTPUT_ENCODE_DONE"
EVENT_ASSET_WRITE_DONE = "ASSET_WRITE_DONE"
EVENT_VOLUME_COMMIT_START = "VOLUME_COMMIT_START"
EVENT_VOLUME_COMMIT_COMPLETE = "VOLUME_COMMIT_COMPLETE"
EVENT_DURABLE_RESULT_MARKER_PUBLICATION = "DURABLE_RESULT_MARKER_PUBLICATION"

# These are deliberately wall-clock subspans of the one authoritative durable
# commit stage.  Modal exposes Volume.commit as one blocking operation; there
# is no lower-level server-side breakdown available to this process.
DURABLE_COMMIT_SUBSPAN_NAMES = (
    "pre_commit_bookkeeping",
    "volume_commit_call_wall",
    "commit_return_to_reopen_start",
    "reopen_open",
    "stat",
    "readback",
    "readback_sha256",
    "byte_count_content_verification",
    "close_finalize",
)
DURABLE_RESULT_MARKER_SUBSPAN = "true_durable_result_marker_publication"
DURABLE_COMMIT_BLOCKING_NOTE = (
    "Modal exposes Volume.commit as one blocking call; lower-level commit timing "
    "inside the service is unavailable and is not inferred here."
)

_TORCH_DTYPE = {
    "F32": torch.float32,
    "F16": torch.float16,
    "BF16": torch.bfloat16,
    "F64": torch.float64,
    "I64": torch.int64,
    "I32": torch.int32,
    "I16": torch.int16,
    "I8": torch.int8,
    "U8": torch.uint8,
    "BOOL": torch.bool,
}


def canonical_workflow_sha256(prompt: dict) -> str:
    """Deterministic SHA-256 over the sorted-key compact JSON of the prompt."""
    payload = json.dumps(prompt, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


# ── Frozen contracts ──────────────────────────────────────────────────────


@dataclass(frozen=True)
class ClipLoadSpec:
    """Generalized CLIP loading contract: 1..4 ordered checkpoint names, the
    CLIPType name, and the folder_paths directory they resolve in.

    ``embedding_directory`` overrides the default embeddings folders when
    non-None; ``model_options_overrides`` is merged over native empty
    ``model_options`` (the canonical spec keeps it empty).  ``initial_device``
    is reserved for the scoped Golden seam below.  ``dtype_policy`` is
    ``"uniform"`` only — mixed-dtype sources are an explicit opt-in that does
    not exist yet and fail closed.  Validation runs at construction; there is
    no repair/fallback path.
    """

    checkpoint_names: tuple[str, ...]
    clip_type: str
    folder: str = "text_encoders"
    embedding_directory: Optional[list] = None
    model_options_overrides: dict = field(default_factory=dict)
    dtype_policy: str = "uniform"
    require_dynamic_patcher: bool = True

    def __post_init__(self) -> None:
        names = self.checkpoint_names
        if not isinstance(names, tuple):
            raise ValueError(f"clip_spec_checkpoint_names_not_tuple:{type(names).__name__}")
        if not (1 <= len(names) <= 4):
            raise ValueError(f"clip_spec_checkpoint_count_invalid:{len(names)}")
        if any(not isinstance(n, str) or not n for n in names):
            raise ValueError("clip_spec_checkpoint_names_invalid")
        if not isinstance(self.clip_type, str) or not self.clip_type:
            raise ValueError("clip_spec_clip_type_invalid")
        if str(self.dtype_policy) != "uniform":
            raise ValueError(f"clip_spec_dtype_policy_unsupported:{self.dtype_policy}")


# Exact canonical CLIP contract: identical values to the historical frozen
# constants, so every default-constructed contract behaves byte-identically.
CANONICAL_CLIP_SPEC = ClipLoadSpec(
    checkpoint_names=(CANONICAL_CLIP_NAME,),
    clip_type=CANONICAL_CLIP_TYPE,
)


@dataclass(frozen=True)
class GoldenWorkflowContract:
    """Immutable canonical workflow/config contract for P1."""

    workflow_sha256: str = EXPECTED_WORKFLOW_SHA256
    expected_output_png_sha256: str = EXPECTED_OUTPUT_PNG_SHA256
    clip_name: str = CANONICAL_CLIP_NAME
    clip_type: str = CANONICAL_CLIP_TYPE
    unet_name: str = CANONICAL_UNET_NAME
    vae_name: str = CANONICAL_VAE_NAME
    sampler_class_type: str = CANONICAL_SAMPLER_CLASS
    qd: int = GOLDEN_QD
    block_bytes: int = GOLDEN_BLOCK_BYTES
    output_root: str = DEFAULT_OUTPUT_ROOT
    expected_unet_tensor_count: int = EXPECTED_UNET_TENSOR_COUNT
    # Defaults to the exact canonical spec; appended last so positional
    # constructions of the historical fields stay valid.
    clip_spec: ClipLoadSpec = CANONICAL_CLIP_SPEC


@dataclass(frozen=True)
class GoldenRequest:
    """One frozen Golden request: id + workflow + optional attention arm.

    ``attention_backend`` is the only supported backend selector for the
    public Golden API.  ``None`` preserves an omitted selector and means
    auto: Golden does not install an attention override.  Explicit selectors
    are normalized once at the request boundary and subsequently treated as
    immutable run identity.
    """

    request_id: str
    prompt: dict
    extra_data: dict = field(default_factory=dict)
    attention_backend: Optional[str] = None
    # ``None`` means omitted at the public boundary and is resolved exactly
    # once from the canonical V2 loader selector.
    clip_residency: Optional[str] = None

    def __post_init__(self) -> None:
        if self.attention_backend is not None:
            object.__setattr__(
                self,
                "attention_backend",
                normalize_attention_backend(self.attention_backend),
            )
        object.__setattr__(self, "clip_residency", resolve_clip_residency(self.clip_residency))

    @property
    def clip_residency_mode(self) -> str:
        """Compatibility spelling for callers that name the field ``mode``."""
        return str(self.clip_residency)


class AttentionBackendValidationError(RuntimeError):
    """Raised when a requested Golden attention arm cannot be proven."""


def normalize_attention_backend(value: Any) -> str:
    """Normalize and validate the public ``attention_backend`` field."""
    if not isinstance(value, str):
        raise ValueError("golden_attention_backend_must_be_string")
    normalized = value.strip().lower()
    if normalized not in ATTENTION_BACKENDS:
        raise ValueError(
            "golden_attention_backend_invalid:"
            f"{value!r}; allowed={','.join(ATTENTION_BACKENDS)}"
        )
    return normalized


_MISSING = object()


def _require_attention_backend_invocation(backend: str, state: Mapping[str, Any]) -> None:
    """Fail closed when a non-baseline override was never observed in use."""
    if backend != "pytorch" and int(state.get("calls", 0)) == 0:
        raise AttentionBackendValidationError("attention_backend_override_not_invoked")


def _attention_call_args(
    args: tuple[Any, ...], kwargs: dict[str, Any]
) -> tuple[Any, Any, Any, int, Any, bool, bool, dict[str, Any]]:
    """Extract the common Comfy attention call shape without copying tensors."""
    if len(args) < 4:
        raise AttentionBackendValidationError("attention_call_shape_invalid")
    q, k, v, heads = args[:4]
    if len(args) > 4:
        mask = args[4]
        if "mask" in kwargs or "attn_mask" in kwargs:
            raise AttentionBackendValidationError("attention_masks_conflict")
    else:
        mask = kwargs.get("mask", _MISSING)
        attn_mask = kwargs.get("attn_mask", _MISSING)
        if mask is _MISSING:
            mask = attn_mask
        elif attn_mask is not _MISSING and mask is not attn_mask:
            raise AttentionBackendValidationError("attention_masks_conflict")
        if mask is _MISSING:
            mask = None
    if len(args) > 5 and "attn_precision" not in kwargs:
        kwargs["attn_precision"] = args[5]
    skip_reshape = bool(args[6] if len(args) > 6 else kwargs.get("skip_reshape", False))
    skip_output_reshape = bool(
        args[7] if len(args) > 7 else kwargs.get("skip_output_reshape", False)
    )
    return q, k, v, heads, mask, skip_reshape, skip_output_reshape, kwargs


def _raw_attention_callable(value: Callable) -> Callable:
    """Use a wrapped Comfy callable's implementation without re-entering the seam."""
    raw = getattr(value, "__wrapped__", None)
    return raw if callable(raw) else value


def _sage_public_supports_sm_scale(value: Callable) -> bool:
    """Return whether the selected public Sage callable names ``sm_scale``."""
    try:
        parameter = inspect.signature(value).parameters.get("sm_scale")
    except (TypeError, ValueError):
        return False
    return parameter is not None and parameter.kind != inspect.Parameter.POSITIONAL_ONLY


def _sage_attention_call_kwargs(
    selected: Callable,
    q: Any,
    k: Any,
    v: Any,
    heads: int,
    mask: Any,
    skip_reshape: bool,
    call_kwargs: dict[str, Any],
) -> tuple[Any, Any, Any, int, dict[str, Any]]:
    """Validate Comfy semantics and build Sage's public arguments."""
    if mask is not None:
        raise AttentionBackendValidationError("sage_attention_mask_unsupported")
    if call_kwargs.get("is_causal", False):
        raise AttentionBackendValidationError("sage_causal_attention_unsupported")
    if call_kwargs.get("enable_gqa", False):
        raise AttentionBackendValidationError("sage_gqa_unsupported")
    if call_kwargs.get("attn_precision") is not None:
        raise AttentionBackendValidationError("sage_attention_precision_unsupported")
    if not isinstance(heads, int) or isinstance(heads, bool) or heads <= 0:
        raise AttentionBackendValidationError("sage_attention_heads_invalid")

    try:
        q_shape = tuple(q.shape)
        k_shape = tuple(k.shape)
        v_shape = tuple(v.shape)
    except Exception as exc:
        raise AttentionBackendValidationError("sage_attention_tensor_shape_invalid") from exc

    if skip_reshape:
        if not all(len(shape) == 4 for shape in (q_shape, k_shape, v_shape)):
            raise AttentionBackendValidationError("sage_attention_hnd_shape_invalid")
        q_heads, k_heads, v_heads = (q_shape[1], k_shape[1], v_shape[1])
        if (q_heads, k_heads, v_heads) != (heads, heads, heads):
            raise AttentionBackendValidationError("sage_gqa_unsupported")
        tensor_layout = "HND"
        q_native, k_native, v_native = q, k, v
        dim_head = q_shape[-1]
    else:
        if not all(len(shape) == 3 for shape in (q_shape, k_shape, v_shape)):
            raise AttentionBackendValidationError("sage_attention_nhd_shape_invalid")
        if q_shape[0] != k_shape[0] or q_shape[0] != v_shape[0]:
            raise AttentionBackendValidationError("sage_attention_batch_shape_invalid")
        if q_shape[-1] != k_shape[-1] or q_shape[-1] != v_shape[-1]:
            raise AttentionBackendValidationError("sage_gqa_unsupported")
        if q_shape[-1] % heads:
            raise AttentionBackendValidationError("sage_attention_head_dim_invalid")
        dim_head = q_shape[-1] // heads
        q_native, k_native, v_native = (
            tensor.view(q_shape[0], -1, heads, dim_head)
            for tensor in (q, k, v)
        )
        tensor_layout = "NHD"

    sage_kwargs: dict[str, Any] = {
        "is_causal": False,
        "tensor_layout": tensor_layout,
    }
    scale = call_kwargs.get("scale", _MISSING)
    sm_scale = call_kwargs.get("sm_scale", _MISSING)
    if scale is not _MISSING and sm_scale is not _MISSING and scale != sm_scale:
        raise AttentionBackendValidationError("sage_attention_scale_conflict")
    requested_scale = sm_scale if sm_scale is not _MISSING else scale
    if requested_scale is not _MISSING:
        if requested_scale is not None and (
            isinstance(requested_scale, bool)
            or not isinstance(requested_scale, (int, float))
        ):
            raise AttentionBackendValidationError("sage_attention_scale_invalid")
        if not _sage_public_supports_sm_scale(selected):
            raise AttentionBackendValidationError("sage_sm_scale_unsupported")
        sage_kwargs["sm_scale"] = requested_scale
    return q_native, k_native, v_native, dim_head, sage_kwargs


def _resolve_kitchen_attention_callable() -> tuple[Callable, str]:
    """Resolve only the official Comfy/Kitchen INT8 callable.

    No fallback is returned.  The first name is the official ComfyUI wrapper;
    the latter names are the official native Kitchen entry points used by
    compatible ComfyUI releases.
    """
    try:
        attention = importlib.import_module("comfy.ldm.modules.attention")
        wrapper = getattr(attention, "attention_comfy_kitchen_int8", None)
        if callable(wrapper):
            return wrapper, "attention_comfy_kitchen_int8"
    except Exception:
        pass
    for module_name in ("comfy_kitchen", "comfy_kitchen.sage_attention"):
        try:
            module = importlib.import_module(module_name)
            native = getattr(module, "int8_attention", None)
            if callable(native):
                return native, f"{module_name}.int8_attention"
        except Exception:
            continue
    raise AttentionBackendValidationError("comfy_kitchen_attention_unavailable")


@contextlib.contextmanager
def attention_backend_scope(patcher: Any, backend: str):
    """Install one backend on the active ModelPatcher and always restore it.

    The override is placed in the existing ``model_options`` /
    ``transformer_options`` seam consumed by ComfyUI attention.  No CLIP or
    VAE object is touched and no global attention alias is rebound.
    """
    backend = normalize_attention_backend(backend)
    calls = 0
    selected_name = backend
    if backend == "pytorch":
        attention = importlib.import_module("comfy.ldm.modules.attention")
        selected = getattr(attention, "attention_pytorch", None)
        if not callable(selected):
            raise AttentionBackendValidationError("pytorch_attention_unavailable")
        selected_name = "comfy.ldm.modules.attention.attention_pytorch"

        def attention_backend_pytorch_override(_func: Callable, *args: Any, **kwargs: Any) -> Any:
            nonlocal calls
            calls += 1
            call_kwargs = dict(kwargs)
            call_kwargs["_inside_attn_wrapper"] = True
            return _raw_attention_callable(selected)(*args, **call_kwargs)

        override = attention_backend_pytorch_override
    elif backend == "sage":
        try:
            sage = importlib.import_module("sageattention")
            selected = getattr(sage, "sageattn", None)
        except Exception as exc:
            raise AttentionBackendValidationError(
                f"sageattention_import_failed:{type(exc).__name__}"
            ) from exc
        if not callable(selected):
            raise AttentionBackendValidationError("sageattention_sageattn_unavailable")
        selected_name = "sageattention.sageattn"

        def attention_backend_sage_override(_func: Callable, *args: Any, **kwargs: Any) -> Any:
            nonlocal calls
            calls += 1
            q, k, v, heads, mask, skip_reshape, skip_output_reshape, call_kwargs = _attention_call_args(
                args, kwargs
            )
            if call_kwargs.get("low_precision_attention", True) is False:
                raise AttentionBackendValidationError("sage_low_precision_disabled")
            q_native, k_native, v_native, dim_head, sage_kwargs = _sage_attention_call_kwargs(
                selected,
                q,
                k,
                v,
                heads,
                mask,
                skip_reshape,
                call_kwargs,
            )
            batch = q.shape[0]
            tensor_layout = sage_kwargs["tensor_layout"]
            try:
                out = selected(
                    q_native,
                    k_native,
                    v_native,
                    **sage_kwargs,
                )
            except Exception as exc:
                raise AttentionBackendValidationError(
                    f"sageattention_native_call_failed:{type(exc).__name__}"
                ) from exc
            if tensor_layout == "HND":
                if not skip_output_reshape:
                    out = out.transpose(1, 2).reshape(batch, -1, heads * dim_head)
            elif skip_output_reshape:
                out = out.transpose(1, 2)
            else:
                out = out.reshape(batch, -1, heads * dim_head)
            return out

        override = attention_backend_sage_override
    else:
        selected, selected_name = _resolve_kitchen_attention_callable()

        if selected_name == "attention_comfy_kitchen_int8":
            def attention_backend_comfy_kitchen_int8_override(
                _func: Callable, *args: Any, **kwargs: Any
            ) -> Any:
                nonlocal calls
                calls += 1
                call_kwargs = dict(kwargs)
                call_kwargs["_inside_attn_wrapper"] = True
                try:
                    return _raw_attention_callable(selected)(*args, **call_kwargs)
                except Exception as exc:
                    raise AttentionBackendValidationError(
                        f"comfy_kitchen_native_call_failed:{type(exc).__name__}"
                    ) from exc
        else:
            def attention_backend_comfy_kitchen_int8_override(
                _func: Callable, *args: Any, **kwargs: Any
            ) -> Any:
                nonlocal calls
                calls += 1
                q, k, v, heads, mask, skip_reshape, skip_output_reshape, _call_kwargs = _attention_call_args(
                    args, kwargs
                )
                if mask is not None:
                    raise AttentionBackendValidationError("comfy_kitchen_attention_mask_unsupported")
                if skip_reshape:
                    batch, _, _, dim_head = q.shape
                    q_native, k_native, v_native = q, k, v
                else:
                    batch, _, dim_head = q.shape
                    dim_head //= heads
                    q_native, k_native, v_native = (
                        t.view(batch, -1, heads, dim_head).transpose(1, 2)
                        for t in (q, k, v)
                    )
                try:
                    out = _raw_attention_callable(selected)(q_native, k_native, v_native)
                except Exception as exc:
                    raise AttentionBackendValidationError(
                        f"comfy_kitchen_native_call_failed:{type(exc).__name__}"
                    ) from exc
                if skip_reshape:
                    if not skip_output_reshape:
                        out = out.transpose(1, 2).reshape(batch, -1, heads * dim_head)
                elif skip_output_reshape:
                    out = out.transpose(1, 2)
                else:
                    out = out.transpose(1, 2).reshape(batch, -1, heads * dim_head)
                return out

        override = attention_backend_comfy_kitchen_int8_override

    options = getattr(patcher, "model_options", None)
    created_options = options is None
    if created_options and backend != "pytorch":
        raise AttentionBackendValidationError("active_unet_model_options_unavailable")
    if created_options:
        options = {}
        try:
            setattr(patcher, "model_options", options)
        except Exception as exc:
            raise AttentionBackendValidationError(
                "active_unet_model_options_unavailable"
            ) from exc
    if not isinstance(options, dict):
        raise AttentionBackendValidationError("active_unet_model_options_unavailable")
    previous_transformer_options = options.get("transformer_options", _MISSING)
    if (
        previous_transformer_options is not _MISSING
        and previous_transformer_options is not None
        and not isinstance(previous_transformer_options, dict)
    ):
        raise AttentionBackendValidationError("active_unet_transformer_options_unavailable")
    transformer_options = previous_transformer_options
    created_transformer_options = not isinstance(transformer_options, dict)
    if created_transformer_options:
        transformer_options = {}
        options["transformer_options"] = transformer_options
    if not isinstance(transformer_options, dict):
        raise AttentionBackendValidationError("active_unet_transformer_options_unavailable")

    previous = transformer_options.get("optimized_attention_override", _MISSING)
    transformer_options["optimized_attention_override"] = override
    state = {"requested_backend": backend, "selected_callable": selected_name, "calls": 0}
    try:
        yield state
        state["calls"] = calls
    finally:
        if previous is _MISSING:
            transformer_options.pop("optimized_attention_override", None)
        else:
            transformer_options["optimized_attention_override"] = previous
        if created_transformer_options:
            if previous_transformer_options is _MISSING:
                options.pop("transformer_options", None)
            else:
                options["transformer_options"] = previous_transformer_options
        if created_options:
            try:
                delattr(patcher, "model_options")
            except Exception:
                pass


@dataclass(frozen=True)
class GoldenNodeMap:
    """Resolved handles of the canonical workflow nodes."""

    clip_loader_id: str
    clip_encode_id: str
    unet_loader_id: str
    vae_loader_id: str
    sampler_id: str
    vae_decode_id: str


@dataclass(frozen=True, init=False)
class GoldenVolumeHandle:
    """Explicit Modal Volume handle and its mounted filesystem root.

    The root is deliberately required at the adapter boundary.  A local
    output directory is never inferred to be mounted storage.
    """

    handle: Any
    volume_mount_root: str
    label: str = "runtime_state_volume"

    def __init__(
        self,
        handle: Any,
        volume_mount_root: Optional[str] = None,
        label: str = "runtime_state_volume",
        *,
        mount_root: Optional[str] = None,
        mounted_filesystem_root: Optional[str] = None,
    ) -> None:
        root = volume_mount_root or mount_root or mounted_filesystem_root
        if not root:
            raise RuntimeError("volume_mount_root_required")
        object.__setattr__(self, "handle", handle)
        object.__setattr__(self, "volume_mount_root", str(root))
        object.__setattr__(self, "label", str(label))

    @property
    def mount_root(self) -> str:
        """Compatibility spelling for callers that use the shorter name."""
        return self.volume_mount_root

    @property
    def mounted_filesystem_root(self) -> str:
        return self.volume_mount_root


_DURABLE_REOPEN_PROOF_TOKEN = object()


@dataclass(frozen=True)
class _DurableReopenProof:
    """Typed proof produced only by :func:`verify_committed_object`."""

    byte_count: int
    sha256: str
    stat_size_bytes: int
    asset_path: str
    volume_mount_root: str
    pending_identity: int
    _proof_token: Any = field(default=None, repr=False, compare=False)

    def __getitem__(self, key: str) -> Any:
        return self.as_dict()[key]

    def get(self, key: str, default: Any = None) -> Any:
        return self.as_dict().get(key, default)

    def as_dict(self) -> dict:
        return {
            "byte_count": self.byte_count,
            "sha256": self.sha256,
            "stat_size_bytes": self.stat_size_bytes,
            "asset_path": self.asset_path,
            "volume_mount_root": self.volume_mount_root,
        }


# ── Telemetry recorder ────────────────────────────────────────────────────


@dataclass
class GoldenStageInterval:
    name: str
    entry_monotonic_ns: int
    entry_wall_ns: int
    end_monotonic_ns: Optional[int] = None
    end_wall_ns: Optional[int] = None
    ready_monotonic_ns: Optional[int] = None
    ok: Optional[bool] = None
    details: dict = field(default_factory=dict)


class GoldenTelemetryRecorder:
    """Authoritative stage-interval telemetry.

    One explicit ENTRY and one successful END/READY mark per stage; child
    detail events are allowed only for QD/construction/adoption/output/
    teardown concerns.  Monotonic-ns marks are authoritative for ordering;
    wall-ns marks are recorded alongside for cross-process correlation.
    """

    def __init__(
        self,
        *,
        monotonic: Callable[[], int] = time.monotonic_ns,
        wall: Callable[[], int] = time.time_ns,
    ):
        self._monotonic = monotonic
        self._wall = wall
        self._intervals: dict[str, GoldenStageInterval] = {}
        self._events: list[dict] = []
        self._open_stage: Optional[str] = None
        self._true_durable_marked = False
        self._first_result_ready_marked = False
        self._reopen_verified = False
        self._reopen_proof: Optional[_DurableReopenProof] = None
        self._external_restore: dict = {}
        self.output_durability_mode = "off"
        self.durability_requested = False
        self.result_durable = False
        self.clip_residency = "bf16"
        self.clip_residency_record: dict[str, Any] = {}
        self.clip_residency_telemetry = _new_ra9h_telemetry()
        self.clip_forward_conversion: dict[str, Any] = {}
        self.sampling_diagnostics: Optional[GoldenSamplingDiagnostics] = None
        self.seriality_violations: list[str] = []

    def record_external_restore(self, metadata: Optional[dict]) -> None:
        """Record adapter-observed restore boundaries without timing them here."""
        if metadata is None:
            metadata = {}
        if not isinstance(metadata, dict):
            raise RuntimeError("restore_metadata_invalid_shape")
        self._external_restore = dict(metadata)
        # The QD selector is session evidence, not a stage boundary.  It is
        # captured when the session is constructed for compatibility with
        # callers that inspect a fresh session, but REAL_RESTORE must remain
        # the first event once the execution timeline begins.
        selector_event = next(
            (
                event
                for event in self._events
                if event["name"] == "golden_qd_transport_selector"
            ),
            None,
        )
        if selector_event is not None:
            self._events.remove(selector_event)
        self.event(EVENT_REAL_RESTORE, **dict(metadata))
        if selector_event is not None:
            self._events.append(selector_event)

    # -- stage intervals ---------------------------------------------------

    def begin_stage(self, name: str) -> GoldenStageInterval:
        if name in self._intervals:
            raise RuntimeError(f"telemetry_duplicate_stage_entry:{name}")
        if self._open_stage is not None:
            raise RuntimeError(
                f"telemetry_stage_overlap:{self._open_stage}still_open_while_beginning:{name}"
            )
        interval = GoldenStageInterval(
            name=name,
            entry_monotonic_ns=self._monotonic(),
            entry_wall_ns=self._wall(),
        )
        self._intervals[name] = interval
        self._open_stage = name
        return interval

    def end_stage(self, name: str, *, ready: bool = False, **details: Any) -> None:
        interval = self._require_open(name)
        interval.end_monotonic_ns = self._monotonic()
        interval.end_wall_ns = self._wall()
        if ready:
            interval.ready_monotonic_ns = interval.end_monotonic_ns
        interval.ok = True
        interval.details.update(details)
        telemetry = getattr(self, "clip_residency_telemetry", None)
        if isinstance(telemetry, dict):
            duration_ms = max(
                0.0,
                (int(interval.end_monotonic_ns) - int(interval.entry_monotonic_ns)) / 1_000_000.0,
            )
            if name == "golden_clip_load":
                telemetry["clip_load_total_ms"] = duration_ms
            elif name == "golden_clip_forward":
                telemetry["clip_forward_total_ms"] = duration_ms
            if name in {"golden_clip_load", "golden_clip_forward"}:
                interval.details.update(copy.deepcopy(telemetry))
        self._open_stage = None

    def fail_stage(self, name: str, exc: BaseException, **details: Any) -> None:
        interval = self._require_open(name)
        interval.end_monotonic_ns = self._monotonic()
        interval.end_wall_ns = self._wall()
        interval.ok = False
        interval.details.update(details)
        interval.details["error"] = f"{type(exc).__name__}: {exc}"
        telemetry = getattr(self, "clip_residency_telemetry", None)
        if isinstance(telemetry, dict):
            duration_ms = max(
                0.0,
                (int(interval.end_monotonic_ns) - int(interval.entry_monotonic_ns)) / 1_000_000.0,
            )
            if name == "golden_clip_load":
                telemetry["clip_load_total_ms"] = duration_ms
            elif name == "golden_clip_forward":
                telemetry["clip_forward_total_ms"] = duration_ms
            if name in {"golden_clip_load", "golden_clip_forward"}:
                interval.details.update(copy.deepcopy(telemetry))
        # Transport adapters may add structured evidence while preserving the
        # public stage exception type.  Keep that evidence on the failure
        # interval instead of reducing it to the exception string.
        transport_telemetry = getattr(exc, "telemetry", None)
        if isinstance(transport_telemetry, Mapping):
            interval.details["transport_telemetry"] = copy.deepcopy(dict(transport_telemetry))
        transport_failure = getattr(exc, "transport_failure", None)
        if isinstance(transport_failure, Mapping):
            interval.details["transport_failure"] = copy.deepcopy(dict(transport_failure))
        self._open_stage = None

    def _require_open(self, name: str) -> GoldenStageInterval:
        interval = self._intervals.get(name)
        if interval is None or interval.end_monotonic_ns is not None:
            raise RuntimeError(f"telemetry_stage_not_open:{name}")
        return interval

    def mark_ready(self, name: str) -> None:
        interval = self._intervals.get(name)
        if interval is None or interval.end_monotonic_ns is None:
            raise RuntimeError(f"telemetry_ready_before_end:{name}")
        interval.ready_monotonic_ns = self._monotonic()

    # -- child detail events -------------------------------------------------

    def event(self, name: str, **fields: Any) -> None:
        self._events.append(
            {
                "name": name,
                "monotonic_ns": self._monotonic(),
                "wall_ns": self._wall(),
                # Raw events are snapshots.  In particular, a later marker or
                # caller mutation must not rewrite an already-emitted timing
                # decomposition.
                "fields": copy.deepcopy(fields),
            }
        )

    def mark_true_durable(self) -> None:
        if getattr(self, "output_durability_mode", "off") != "strict":
            raise RuntimeError("true_durable_requires_output_durability_strict")
        if self._true_durable_marked:
            raise RuntimeError("true_first_durable_result_already_marked")
        commit = self._intervals.get("golden_durable_commit")
        if commit is None or commit.ok is not True:
            raise RuntimeError("true_durable_requires_successful_commit_stage")
        if not self._reopen_verified or self._reopen_proof is None:
            raise RuntimeError("true_durable_requires_reopen_verification")
        marker_start_ns = self._monotonic()
        self._true_durable_marked = True
        self.result_durable = True
        self.event(EVENT_TRUE_FIRST_DURABLE_RESULT)
        marker_end_ns = self._monotonic()
        marker_span = {
            "start_monotonic_ns": marker_start_ns,
            "end_monotonic_ns": marker_end_ns,
            "duration_ns": max(0, marker_end_ns - marker_start_ns),
            "stage_boundary": "post_commit_result_marker",
            "outside_durable_commit_stage": True,
        }
        self.event(
            EVENT_DURABLE_RESULT_MARKER_PUBLICATION,
            subspan=DURABLE_RESULT_MARKER_SUBSPAN,
            **marker_span,
        )

    def mark_first_result_ready(self) -> None:
        """Mark encoded output ready before teardown, without claiming durability."""
        if self._first_result_ready_marked:
            raise RuntimeError("first_result_ready_already_marked")
        output = self._intervals.get("golden_output")
        if output is None or output.ok is not True or output.ready_monotonic_ns is None:
            raise RuntimeError("first_result_ready_requires_successful_output")
        if self.output_durability_mode != "off":
            raise RuntimeError("first_result_ready_requires_output_durability_off")
        self._first_result_ready_marked = True
        self.event(EVENT_FIRST_RESULT_READY)

    def mark_reopen_verified(self, proof: Any) -> None:
        if (
            not isinstance(proof, _DurableReopenProof)
            or getattr(proof, "_proof_token", None) is not _DURABLE_REOPEN_PROOF_TOKEN
        ):
            raise RuntimeError("durable_reopen_verification_invalid_proof")
        details = proof.as_dict()
        if proof.pending_identity <= 0 or not proof.volume_mount_root:
            raise RuntimeError("durable_reopen_verification_unbound_proof")
        self._reopen_proof = proof
        self._reopen_verified = True
        self.event("durable_reopen_verified", **details)

    @property
    def true_durable_marked(self) -> bool:
        return self._true_durable_marked

    @property
    def intervals(self) -> dict[str, GoldenStageInterval]:
        return dict(self._intervals)

    @property
    def events(self) -> list[dict]:
        return list(self._events)

    # -- seriality reconciliation -------------------------------------------

    def reconcile_seriality(self) -> dict:
        """Verify previous.END <= next.ENTRY across stages in STAGE order."""
        violations: list[str] = []
        ordered = [name for name in STAGE_ORDER if name in self._intervals]
        for prev_name, next_name in zip(ordered, ordered[1:]):
            prev_end = self._intervals[prev_name].end_monotonic_ns
            next_entry = self._intervals[next_name].entry_monotonic_ns
            if prev_end is None or next_entry is None or prev_end > next_entry:
                violations.append(f"{prev_name}.END > {next_name}.ENTRY")
        self.seriality_violations = violations
        return {"ok": not violations, "violations": list(violations), "count": len(violations)}

    # -- persistence ---------------------------------------------------------

    def to_json_dict(self) -> dict:
        reconcile = self.reconcile_seriality()
        payload = {
            "schema": "golden_p1_telemetry_v1",
            "true_durable_marked": self._true_durable_marked,
            "output_durability_mode": self.output_durability_mode,
            "durability_requested": self.durability_requested,
            "result_durable": self.result_durable,
            "first_result_ready_marked": self._first_result_ready_marked,
            "reopen_verified": self._reopen_verified,
            "clip_residency": self.clip_residency,
            "clip_residency_record": dict(self.clip_residency_record),
            "clip_residency_telemetry": copy.deepcopy(self.clip_residency_telemetry),
            "clip_forward_conversion": dict(self.clip_forward_conversion),
            "external_restore": dict(self._external_restore),
            "seriality": reconcile,
            "stages": [
                {
                    "name": iv.name,
                    "entry_monotonic_ns": iv.entry_monotonic_ns,
                    "entry_wall_ns": iv.entry_wall_ns,
                    "end_monotonic_ns": iv.end_monotonic_ns,
                    "end_wall_ns": iv.end_wall_ns,
                    "ready_monotonic_ns": iv.ready_monotonic_ns,
                    "ok": iv.ok,
                    "details": iv.details,
                }
                for iv in self._intervals.values()
            ],
            "events": list(self._events),
        }
        run_identity = getattr(self, "run_identity", None)
        if isinstance(run_identity, dict):
            payload["run_identity"] = dict(run_identity)
        named_telemetry = copy.deepcopy(self.clip_residency_telemetry)
        payload.update(named_telemetry)
        diagnostics = self.sampling_diagnostics
        if diagnostics is not None:
            payload["sampling_diagnostics"] = diagnostics.to_json_dict()
        return payload

    def persist(self, path: str) -> str:
        """Atomically persist the complete JSON telemetry document."""
        path = str(path)
        parent = os.path.dirname(os.path.abspath(path))
        os.makedirs(parent, exist_ok=True)
        # This marker is part of the document only after persistence has been
        # requested; its presence in the atomically replaced file is direct
        # evidence that this recorder performed the write.  Keep the measured
        # write duration outside the document because it is only known after
        # the write completes.
        payload = self.to_json_dict()
        payload["telemetry_persistence"] = {"telemetry_persisted": True}
        document = json.dumps(payload, indent=1, default=str)
        fd, tmp = tempfile.mkstemp(dir=parent, prefix=".golden_telemetry_", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(document)
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp, path)
        except BaseException:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise
        return path


# ── Opt-in bounded sampler diagnostics (P4-6) ──────────────────────────────


def _sampling_diagnostics_enabled() -> bool:
    """Return whether the low-overhead sampler timeline was explicitly enabled."""
    raw = os.environ.get(GOLDEN_SAMPLING_DIAGNOSTICS_ENV)
    return str(raw or "").strip().lower() in {"1", "true", "yes", "on"}


def stage_diagnostics_enabled() -> bool:
    """Return whether optional CLIP/VAE/QD stage diagnostics are enabled."""
    raw = os.environ.get(GOLDEN_STAGE_DIAGNOSTICS_ENV)
    return str(raw or "").strip().lower() in {"1", "true", "yes", "on"}


def _stage_diagnostics_enabled() -> bool:
    """Test-compatible private adapter for the public stage selector."""
    return stage_diagnostics_enabled()


def _allocator_state() -> dict[str, Any]:
    """Read cheap allocator counters without realizing any CUDA work."""
    state = {
        "allocated_bytes": None,
        "reserved_bytes": None,
        "active_bytes": None,
        "inactive_split_bytes": None,
        "max_allocated_bytes": None,
    }
    cuda = getattr(torch, "cuda", None)
    if cuda is None:
        state["available"] = False
        return state
    readers = {
        "allocated_bytes": "memory_allocated",
        "reserved_bytes": "memory_reserved",
        "max_allocated_bytes": "max_memory_allocated",
    }
    for key, name in readers.items():
        try:
            reader = getattr(cuda, name, None)
            if callable(reader):
                value = reader()
                if isinstance(value, int) and not isinstance(value, bool):
                    state[key] = int(value)
        except Exception:
            pass
    # memory_stats is optional and may itself be unavailable on test doubles.
    try:
        stats_fn = getattr(cuda, "memory_stats", None)
        stats = stats_fn() if callable(stats_fn) else None
        if isinstance(stats, dict):
            for key, stat_key in (
                ("active_bytes", "active_bytes.all.current"),
                ("inactive_split_bytes", "inactive_split_bytes.all.current"),
            ):
                value = stats.get(stat_key)
                if isinstance(value, int) and not isinstance(value, bool):
                    state[key] = int(value)
    except Exception:
        pass
    state["available"] = any(value is not None for value in state.values())
    return state


def _host_memory_visibility() -> dict[str, Any]:
    state: dict[str, Any] = {
        "rss_bytes": None,
        "rss_source": None,
        "max_rss_bytes": None,
        "memlock_soft_bytes": None,
        "memlock_hard_bytes": None,
    }
    try:
        psutil = importlib.import_module("psutil")
        rss = getattr(getattr(psutil, "Process")(), "memory_info")().rss
        if isinstance(rss, int) and not isinstance(rss, bool):
            state["rss_bytes"] = int(rss)
            state["rss_source"] = "psutil"
    except Exception:
        try:
            with open("/proc/self/statm", "r", encoding="ascii") as fh:
                pages = int(fh.read().split()[1])
            page_size = int(os.sysconf("SC_PAGE_SIZE"))
            state["rss_bytes"] = pages * page_size
            state["rss_source"] = "proc_statm"
        except Exception:
            pass
    try:
        resource = importlib.import_module("resource")
        usage = resource.getrusage(resource.RUSAGE_SELF)
        max_rss = int(usage.ru_maxrss)
        if sys.platform != "darwin" and sys.platform != "win32":
            max_rss *= 1024
        state["max_rss_bytes"] = max_rss
        soft, hard = resource.getrlimit(resource.RLIMIT_MEMLOCK)
        state["memlock_soft_bytes"] = None if soft < 0 else int(soft)
        state["memlock_hard_bytes"] = None if hard < 0 else int(hard)
    except Exception:
        pass
    state["available"] = any(value is not None for key, value in state.items() if key != "available")
    return state


def _process_page_faults() -> dict[str, Any]:
    """Read raw process fault counters without touching or prewarming pages.

    ``resource.getrusage`` is authoritative where available.  Linux procfs is
    only a fallback for runtimes without usable ``resource`` counters; missing
    dimensions remain ``None`` rather than being represented as zero.
    """
    result = {
        "available": False,
        "minor_faults": None,
        "major_faults": None,
        # Historical VAE consumers use these explicit aliases; they are
        # adapters over the same raw counters, not another definition.
        "minor_page_faults": None,
        "major_page_faults": None,
        "source": None,
    }
    try:
        resource = importlib.import_module("resource")
        usage = resource.getrusage(resource.RUSAGE_SELF)
        minor = getattr(usage, "ru_minflt", None)
        major = getattr(usage, "ru_majflt", None)
        if isinstance(minor, int) and not isinstance(minor, bool):
            result["minor_faults"] = int(minor)
        if isinstance(major, int) and not isinstance(major, bool):
            result["major_faults"] = int(major)
        result["minor_page_faults"] = result["minor_faults"]
        result["major_page_faults"] = result["major_faults"]
        result["available"] = result["minor_faults"] is not None or result["major_faults"] is not None
        if result["available"]:
            result["source"] = "resource.getrusage(RUSAGE_SELF)"
            return result
    except Exception:
        pass
    if sys.platform.startswith("linux"):
        try:
            # /proc/<pid>/stat puts minflt at field 10 and majflt at field 12.
            # The command name may contain spaces, so split only after ')'.
            with open("/proc/self/stat", "r", encoding="ascii") as stat_file:
                fields = stat_file.read().rsplit(")", 1)[1].split()
            result.update(
                available=True,
                source="/proc/self/stat",
                minor_faults=int(fields[7]),
                major_faults=int(fields[9]),
                minor_page_faults=int(fields[7]),
                major_page_faults=int(fields[9]),
            )
        except Exception:
            pass
    return result


def page_fault_delta(before: Mapping[str, Any], after: Mapping[str, Any]) -> dict[str, Any]:
    def delta(name: str) -> Optional[int]:
        alias = name.replace("_faults", "_page_faults")
        left = before.get(name, before.get(alias))
        right = after.get(name, after.get(alias))
        if not isinstance(left, int) or isinstance(left, bool):
            return None
        if not isinstance(right, int) or isinstance(right, bool):
            return None
        return max(0, int(right) - int(left))

    minor = delta("minor_faults")
    major = delta("major_faults")
    return {
        "available": minor is not None or major is not None,
        "minor_delta": minor,
        "major_delta": major,
        "minor_page_faults_delta": minor,
        "major_page_faults_delta": major,
        "supporting_evidence_only": True,
        "source": after.get("source") or before.get("source"),
    }


def aggregate_timing_intervals(
    intervals: Iterable[Mapping[str, Any]],
    *,
    enclosing_start_ns: Optional[int] = None,
    enclosing_end_ns: Optional[int] = None,
) -> dict[str, Any]:
    spans = []
    for item in intervals:
        start = item.get("start_ns")
        end = item.get("end_ns")
        if start is None or end is None:
            continue
        start, end = int(start), int(end)
        if end < start:
            raise ValueError("timing_interval_inverted")
        spans.append((start, end))
    spans.sort()
    union_ns = 0
    overlap_ns = 0
    union_end = None
    for start, end in spans:
        if union_end is None:
            union_end = end
            union_ns = end - start
        elif start >= union_end:
            union_ns += end - start
            union_end = end
        else:
            overlap_ns += min(end, union_end) - start
            if end > union_end:
                union_ns += end - union_end
                union_end = end
    sum_ns = sum(end - start for start, end in spans)
    wall_ns = None
    residual_ns = None
    if enclosing_start_ns is not None and enclosing_end_ns is not None:
        wall_ns = max(0, int(enclosing_end_ns) - int(enclosing_start_ns))
        residual_ns = wall_ns - union_ns
    return {
        "interval_count": len(spans),
        "sum_ns": sum_ns,
        "union_ns": union_ns,
        "overlap_ns": overlap_ns,
        "wall_ns": wall_ns,
        "residual_ns": residual_ns,
        "non_additive": bool(overlap_ns or (wall_ns is not None and sum_ns != wall_ns)),
        "aggregation": "union_for_wall_sum_for_nested_durations",
    }


def _percentile(values: Iterable[int], fraction: float) -> Optional[int]:
    """Return an interpolated percentile from an already bounded sample."""
    ordered = sorted(max(0, int(value)) for value in values)
    if not ordered:
        return None
    position = (len(ordered) - 1) * float(fraction)
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    if lower == upper:
        return ordered[lower]
    return int(round(ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)))


def _read_duration_summary(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    """Describe the bounded observed per-read sample without inventing data."""
    samples = [int(value) for value in snapshot.get("read_duration_samples_ns", ())]
    observed_count = int(snapshot.get("read_count", 0))
    sample_limit = int(snapshot.get("read_duration_sample_limit", 0))
    percentiles = {
        "p50_ns": _percentile(samples, 0.50),
        "p90_ns": _percentile(samples, 0.90),
        "p95_ns": _percentile(samples, 0.95),
        "p99_ns": _percentile(samples, 0.99),
    }
    return {
        "observed_count": observed_count,
        "sample_count": len(samples),
        "sample_limit": sample_limit,
        "sample_truncated": observed_count > len(samples),
        "sampling": "first_reads_bounded" if observed_count > len(samples) else "all_observed_reads",
        "percentiles_ns": percentiles,
        "percentiles_ms": {
            key[:-3] + "ms": (value / 1e6 if value is not None else None)
            for key, value in percentiles.items()
        },
        "max_ns": snapshot.get("read_duration_max_ns"),
        "max_ms": (
            int(snapshot["read_duration_max_ns"]) / 1e6
            if snapshot.get("read_duration_max_ns") is not None else None
        ),
    }


def build_qd_transport_diagnostics(stats: Mapping[str, Any]) -> dict[str, Any]:
    source = dict(stats.get("source_open_header_layout") or {})
    staging = dict(stats.get("staging") or {})
    source_reads = dict(stats.get("source_reads") or {})
    h2d_enqueue = dict(stats.get("h2d_enqueue") or {})
    h2d_gpu = dict(stats.get("h2d_gpu_event") or {})
    waits = dict(stats.get("waits_quiescence") or {})
    experiment = dict(stats.get("dispatcher_telemetry") or {})
    execution_arm = stats.get("execution_arm", experiment.get("execution_arm", "legacy"))
    source_bytes = stats.get("source_read_bytes", stats.get("bytes_read"))
    if source_bytes is None:
        source_bytes = source_reads.get("bytes", experiment.get("source_bytes"))
    source_read_count = stats.get("source_read_count")
    if source_read_count is None:
        source_read_count = source_reads.get("read_count", experiment.get("source_read_count"))
    source_wall_ns = source_reads.get("wall_ns", stats.get("source_read_wall_ns"))
    source_wall_ms = source_reads.get("wall_ms", stats.get("source_read_wall_ms"))
    if source_wall_ns is None:
        source_wall_ns = experiment.get("source_read_wall_ns")
    if source_wall_ms is None:
        source_wall_ms = experiment.get("source_read_wall_ms")
    if source_wall_ms is None and source_wall_ns is not None:
        source_wall_ms = int(source_wall_ns) / 1e6
    if source_bytes is not None:
        source_reads.setdefault("bytes", source_bytes)
    if source_read_count is not None:
        source_reads.setdefault("read_count", source_read_count)
    if source_wall_ns is not None:
        source_reads.setdefault("wall_ns", source_wall_ns)
    if source_wall_ms is not None:
        source_reads.setdefault("wall_ms", source_wall_ms)
    if "per_read" not in source_reads and experiment.get("source_reads_per_read") is not None:
        source_reads["per_read"] = copy.deepcopy(experiment["source_reads_per_read"])
    if execution_arm == "dispatcher":
        # The dispatcher performs the positioned read directly into the lease.
        # There is no separate CPU-to-pinned copy or legacy pinned-slot reuse,
        # but CudaTransferBackend still allocates real pinned staging storage.
        pinned_staging = {
            "status": "NOT RUN",
            "reason": "positioned readinto fills the acquired staging lease directly",
        }
        pinned_slot_wait = {
            "status": "NOT RUN",
            "reason": "dispatcher does not use legacy pinned slots",
        }
        allocation_pinning = dict(stats.get("allocation_pinning") or {})
        h2d_event_poll = dict(stats.get("h2d_event_poll") or {})
        if not h2d_event_poll:
            h2d_event_poll = {
                "status": "OBSERVED",
                "wall_ns": int(float(experiment.get("dispatcher_reap_wall_ms") or 0.0) * 1e6),
                "wall_ms": float(experiment.get("dispatcher_reap_wall_ms") or 0.0),
                "poll_count": int(experiment.get("dispatcher_reap_count") or 0),
                "timing_scope": "TOTAL dispatcher event polling/reap",
            }
        h2d_event_wait = {
            "status": "NOT RUN",
            "reason": "dispatcher polling/reap wall is not a host event wait",
        }
    else:
        pinned_staging = dict(stats.get("cpu_to_pinned_staging") or {})
        pinned_slot_wait = dict(stats.get("pinned_slot_wait") or {})
        allocation_pinning = dict(stats.get("allocation_pinning") or staging)
        h2d_event_poll = dict(stats.get("h2d_event_poll") or {
            "status": "NOT RUN",
            "reason": "legacy transport uses blocking completion-event waits",
        })
        h2d_event_wait = dict(stats.get("h2d_event_wait") or {
            "status": "NOT RUN",
            "reason": "host completion wait was not measured",
        })
    h2d_event_completion = dict(stats.get("h2d_event_completion") or {})
    if not h2d_event_completion:
        completion_latency = stats.get(
            "h2d_event_completion_latency_ms",
            experiment.get("h2d_event_completion_latency_ms"),
        )
        if completion_latency is not None:
            h2d_event_completion = {
                "status": "OBSERVED",
                "latency_ms": completion_latency,
                "sample_count": stats.get(
                    "h2d_completed_count",
                    experiment.get("h2d_completed_count"),
                ),
                "timing_scope": "PARTIAL H2D submit-to-event completion latency",
            }
    lease_wait = dict(stats.get("lease_wait") or {})
    if not lease_wait and execution_arm == "dispatcher":
        lease_wait = {
            "wait_ns": int(float(experiment.get("producer_capacity_block_wall_ms") or 0.0) * 1e6),
            "wait_ms": float(experiment.get("producer_capacity_block_wall_ms") or 0.0),
            "wait_count": int(experiment.get("producer_capacity_block_count") or 0),
            "timing_scope": "TOTAL waits to acquire a reusable dispatcher lease",
        }
    ready_backpressure = dict(stats.get("ready_backpressure") or {})
    if not ready_backpressure and execution_arm == "dispatcher":
        ready_backpressure = {
            "wait_ns": int(float(experiment.get("ready_queue_block_wall_ms") or 0.0) * 1e6),
            "wait_ms": float(experiment.get("ready_queue_block_wall_ms") or 0.0),
            "wait_count": int(experiment.get("ready_queue_block_count") or 0),
            "ready_depth_at_end": experiment.get("ready_queue_depth"),
            "timing_scope": "TOTAL producer waits for dispatcher ready-queue capacity",
        }
    qd_occupancy = dict(stats.get("producer_qd_occupancy") or {})
    if not qd_occupancy and execution_arm == "dispatcher":
        qd_occupancy = {
            "target": experiment.get("source_qd_target"),
            "max_depth": max(experiment.get("source_qd_depth_samples") or [0]),
            "fraction_time_at_target": experiment.get("fraction_time_at_target_source_qd"),
            "timeline": experiment.get("source_qd_timeline") or [],
        }
    free_ready_depth = dict(stats.get("free_ready_depth") or {})
    if not free_ready_depth and execution_arm == "dispatcher":
        free_ready_depth = {
            "minimum_free_slots": experiment.get("minimum_free_slots"),
            "ready_queue_depth_at_end": experiment.get("ready_queue_depth"),
        }
    fallback = dict(stats.get("fallback") or {})
    if not fallback and execution_arm == "dispatcher":
        fallback = {
            "count": int(experiment.get("fallback_count") or 0),
            "reason": experiment.get("fallback_reason"),
        }
    exact_reconciliation = dict(
        stats.get("exact_reconciliation")
        or experiment.get("exact_reconciliation")
        or stats.get("record_reconciliation")
        or {}
    )
    return {
        "schema": "golden_qd_transport_diagnostics_v1",
        "role": stats.get("role"),
        "execution_arm": execution_arm,
        "source_bytes": source_bytes,
        "source_read_count": source_read_count,
        "source_open_count": stats.get("source_open_count"),
        "header_parse_count": stats.get("header_parse_count"),
        "duplicate_read_count": stats.get("duplicate_read_count"),
        "owner_count": stats.get("owner_count", experiment.get("owner_count")),
        "adoption_result": stats.get("adoption_result", experiment.get("adoption_result")),
        "fallback_count": (stats.get("fallback") or {}).get("fallback_count", 0),
        "fallback_reason": (stats.get("fallback") or {}).get("fallback_reason"),
        "source_open_header_layout": source,
        "staging": staging,
        "source_reads": source_reads,
        "source_read_wall_ns": source_wall_ns,
        "source_read_wall_ms": source_wall_ms,
        "cpu_to_pinned_staging": pinned_staging,
        "allocation_pinning": allocation_pinning,
        "pinned_slot_wait": pinned_slot_wait,
        "h2d_enqueue": h2d_enqueue,
        "h2d_submit_wall": dict(stats.get("h2d_submit_wall") or h2d_enqueue),
        "h2d_gpu_event": h2d_gpu,
        "h2d_event_poll": h2d_event_poll,
        "h2d_event_completion": h2d_event_completion,
        "h2d_event_completion_latency_ms": h2d_event_completion.get("latency_ms"),
        "h2d_event_wait": h2d_event_wait,
        "lease_wait": lease_wait,
        "ready_backpressure": ready_backpressure,
        "producer_qd_occupancy": qd_occupancy,
        "free_ready_depth": free_ready_depth,
        "fallback": fallback,
        "exact_reconciliation": exact_reconciliation,
        "waits_quiescence": waits,
        "final_drain": dict(stats.get("final_drain") or {}),
        "post_transport_construction_adoption": dict(
            stats.get("post_transport_construction_adoption") or {
                "status": "NOT RUN",
                "reason": "outside the QD transport/read boundary",
            }
        ),
        "throughput": {
            "source_gbps": stats.get("effective_source_gbps", stats.get("qd_source_gbps")),
            "h2d_gbps": stats.get("effective_h2d_gbps"),
            "h2d_scope": "sum_of_copy_event_durations",
        },
        "overlap": {
            "nested_timings_not_additive": True,
            "sum_is_not_wall": True,
            "wall_fields": ["source_reads.wall_ns", "h2d_enqueue.wall_ns"],
        },
        # Dispatcher counters are already JSON-safe and retain their explicit
        # TOTAL/PARTIAL timing scopes without promoting nested work to a stage
        # wall.  The legacy arm reports only boundaries observed in its own
        # read/transport code.
        "experiment": experiment,
    }


def build_vae_load_decomposition(
    *,
    stage_start_ns: int,
    stage_end_ns: int,
    components: Iterable[Mapping[str, Any]],
    transport_stats: Mapping[str, Any],
    memory_before: Optional[Mapping[str, Any]] = None,
    memory_after: Optional[Mapping[str, Any]] = None,
) -> dict[str, Any]:
    component_list = [dict(component) for component in components]
    aggregate = aggregate_timing_intervals(
        component_list,
        enclosing_start_ns=stage_start_ns,
        enclosing_end_ns=stage_end_ns,
    )
    return {
        "schema": "vae_load_decomposition_v1",
        "clock": "perf_counter_ns",
        "stage_wall_ns": max(0, int(stage_end_ns) - int(stage_start_ns)),
        "stage_wall_ms": round(max(0, int(stage_end_ns) - int(stage_start_ns)) / 1e6, 4),
        "components": component_list,
        "aggregation": aggregate,
        "transport": build_qd_transport_diagnostics(transport_stats),
        "memory": {
            "before": dict(memory_before or {}),
            "after": dict(memory_after or {}),
        },
        "overlap": {
            "nested_timings_not_additive": True,
            "do_not_sum_components_for_stage_wall": True,
            "residual_ns": aggregate["residual_ns"],
        },
    }


def _safe_diagnostic_value(value: Any) -> Any:
    """Keep passive state JSON-safe; never stringify an unknown counter."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (list, tuple)) and all(
        isinstance(item, (str, int, float, bool)) or item is None for item in value
    ):
        return list(value)
    if isinstance(value, dict):
        return {
            str(key): _safe_diagnostic_value(item)
            for key, item in value.items()
            if isinstance(item, (str, int, float, bool, list, tuple, dict)) or item is None
        }
    return None


def _read_cachedit_state(patcher: Any, diffusion_model: Any) -> dict[str, Any]:
    """Passively read already-loaded CacheDiT scalar state.

    This deliberately does not import CacheDiT, call a method, inspect a tensor,
    or derive one counter from another.  Every requested field remains explicit
    ``None`` when the installed CacheDiT exposes no matching scalar.
    """
    fields = {
        "expected": None,
        "computed": None,
        "cached": None,
        "skipped": None,
        "hit_rate": None,
        "recompute_reasons": None,
    }
    config = {"warmup_steps": None, "skip_interval": None}
    candidates: list[tuple[str, Any]] = []
    seen: set[int] = set()
    for module in tuple(sys.modules.values()):
        if module is None or id(module) in seen:
            continue
        namespace = getattr(module, "__dict__", None)
        if not isinstance(namespace, dict):
            continue
        filename = namespace.get("__file__")
        module_name = str(namespace.get("__name__", ""))
        if not (
            isinstance(filename, str)
            and "comfyui-cachedit" in filename.replace("\\", "/").lower()
        ) and "cachedit" not in module_name.lower():
            continue
        state = namespace.get("_lightweight_cache_state")
        if isinstance(state, dict):
            candidates.append(("loaded_module", state))
            seen.add(id(module))
    for owner_name, owner in (("diffusion_model", diffusion_model), ("patcher", patcher)):
        if owner is None:
            continue
        for attr in (
            "_lightweight_cache_state",
            "_cache_dit_state",
            "_cache_dit_stats",
            "cache_dit_state",
        ):
            try:
                state = getattr(owner, attr, None)
            except Exception:
                state = None
            if isinstance(state, dict):
                candidates.append((f"{owner_name}.{attr}", state))

    aliases = {
        "expected": ("expected", "expected_count", "expected_calls"),
        "computed": ("computed", "computed_count", "compute_count"),
        "cached": ("cached", "cached_count", "cache_count", "cache_hits", "hit_count"),
        "skipped": ("skipped", "skipped_count", "skip_count"),
        "hit_rate": ("hit_rate", "cache_hit_rate"),
        "recompute_reasons": ("recompute_reasons", "recompute_reason", "reasons"),
    }
    source = None
    for candidate_source, state in candidates:
        for field_name, names in aliases.items():
            if fields[field_name] is not None:
                continue
            for name in names:
                if name in state:
                    value = _safe_diagnostic_value(state.get(name))
                    if value is not None:
                        fields[field_name] = value
                        source = source or candidate_source
                    break
        for config_name in config:
            if config[config_name] is not None:
                continue
            for state_name in (config_name, f"user_{config_name}"):
                if state_name in state:
                    value = _safe_diagnostic_value(state.get(state_name))
                    if value is not None:
                        config[config_name] = value
                    break
    try:
        options = getattr(patcher, "model_options", None) or {}
        transformer_options = options.get("transformer_options") or {}
        cache_config = transformer_options.get("cache_dit_turbo")
        if cache_config is not None:
            for config_name, attr in (
                ("warmup_steps", "user_warmup_steps"),
                ("skip_interval", "user_skip_interval"),
            ):
                if config[config_name] is None:
                    value = getattr(cache_config, attr, None)
                    if isinstance(value, int) and not isinstance(value, bool):
                        config[config_name] = value
    except Exception:
        pass
    attached = None
    try:
        original = getattr(diffusion_model, "_original_forward", None)
        forward = getattr(diffusion_model, "forward", None)
        attached = bool(original is not None and forward is not None and forward is not original)
    except Exception:
        pass
    unavailable = [name for name, value in fields.items() if value is None]
    return {
        "available": bool(source is not None or attached is True),
        "source": source,
        "attached": attached,
        "config": config,
        **fields,
        "unavailable_fields": unavailable,
    }


class GoldenSamplingDiagnostics:
    """One opt-in, reversible timeline around the canonical sampler node."""

    _CALLBACK_NAMES = frozenset({"callback", "callback_function"})

    def __init__(self, recorder: GoldenTelemetryRecorder, *, sampler_id: str, sampler_class: str):
        self.recorder = recorder
        self.sampler_id = str(sampler_id)
        self.sampler_class = str(sampler_class)
        self.timeline: list[dict[str, Any]] = []
        self.callback_count = 0
        self.callback_available = False
        self._callbacks: list[dict[str, Any]] = []
        self.step_timeline: Optional[list[dict[str, Any]]] = None
        self.step_timeline_unavailable_reason: Optional[str] = None
        self.model_forward_count = 0
        self.first_model_forward_wall_ms: Optional[float] = None
        self.sampler_wall_ms: Optional[float] = None
        self.cachedit: Optional[dict[str, Any]] = None
        self.allocator: dict[str, Any] = {}
        self._model_hooks: list[Any] = []
        self._forward_starts: list[int] = []
        self._sampling_start_ns: Optional[int] = None
        self._cleanup_done = False

    def _event(self, kind: str, **fields: Any) -> None:
        item = {"kind": kind, **fields}
        self.timeline.append(item)
        try:
            self.recorder.event("golden_sampling_diagnostic", **item)
        except Exception:
            pass

    @staticmethod
    def _duration_ms(start_ns: int, end_ns: int) -> float:
        return round(max(0, int(end_ns) - int(start_ns)) / 1_000_000, 3)

    def begin(self, session: GoldenSession) -> None:
        self._sampling_start_ns = time.monotonic_ns()
        self.allocator["vae_before_sampling"] = _allocator_state()
        prep = session.recorder.intervals.get("golden_sampler_prepare")
        prep_ms = None
        if prep is not None and prep.end_monotonic_ns is not None:
            prep_ms = self._duration_ms(prep.entry_monotonic_ns, prep.end_monotonic_ns)
        self._event(
            "sampler_setup",
            sampler_id=self.sampler_id,
            sampler_class=self.sampler_class,
            wall_ms=prep_ms,
            source_stage="golden_sampler_prepare",
            unavailable=prep_ms is None,
            allocator=self.allocator["vae_before_sampling"],
        )
        self._event("sampling_start", allocator=self.allocator["vae_before_sampling"])

    def install_model_hooks(self, patcher: Any) -> None:
        try:
            model = getattr(patcher, "model", None) if patcher is not None else None
            diffusion_model = getattr(model, "diffusion_model", None) if model is not None else None
            if diffusion_model is None and patcher is not None:
                diffusion_model = getattr(patcher, "diffusion_model", None)
        except Exception:
            diffusion_model = None
        pre_register = getattr(diffusion_model, "register_forward_pre_hook", None)
        post_register = getattr(diffusion_model, "register_forward_hook", None)
        if not callable(pre_register) or not callable(post_register):
            self._event("model_forward_hooks_unavailable", wall_ms=None)
            return

        def pre_hook(*_args: Any, **_kwargs: Any) -> None:
            self._forward_starts.append(time.monotonic_ns())

        def post_hook(*_args: Any, **_kwargs: Any) -> None:
            end_ns = time.monotonic_ns()
            start_ns = self._forward_starts.pop() if self._forward_starts else end_ns
            wall_ms = self._duration_ms(start_ns, end_ns)
            self.model_forward_count += 1
            if self.first_model_forward_wall_ms is None:
                self.first_model_forward_wall_ms = wall_ms
                self._event("first_model_forward", index=0, wall_ms=wall_ms)
            self._event(
                "model_forward",
                index=self.model_forward_count - 1,
                wall_ms=wall_ms,
                hook_wall_ms=wall_ms,
            )

        try:
            try:
                self._model_hooks.append(pre_register(pre_hook, with_kwargs=True))
            except TypeError:
                self._model_hooks.append(pre_register(pre_hook))
            self._model_hooks.append(post_register(post_hook))
            self._diffusion_model = diffusion_model
        except Exception as exc:
            self._event("model_forward_hooks_unavailable", wall_ms=None, error=type(exc).__name__)
            self._remove_model_hooks()

    def wrap_sampler_inputs(self, inputs: dict) -> dict:
        """Wrap only an already-present callback; absent callbacks stay absent."""
        wrapped = dict(inputs)
        for key, value in list(wrapped.items()):
            if str(key).lower() in self._CALLBACK_NAMES and callable(value):
                wrapped[key] = self._wrap_callback(value)
            elif str(key).lower() in self._CALLBACK_NAMES and isinstance(value, list):
                if len(value) == 1 and callable(value[0]):
                    wrapped[key] = [self._wrap_callback(value[0])]
        options = wrapped.get("model_options")
        if isinstance(options, dict):
            options_copy = dict(options)
            for key, value in list(options_copy.items()):
                if str(key).lower() in self._CALLBACK_NAMES and callable(value):
                    options_copy[key] = self._wrap_callback(value)
            wrapped["model_options"] = options_copy
        return wrapped

    def _wrap_callback(self, callback: Callable) -> Callable:
        self.callback_available = True

        def timed_callback(*args: Any, **kwargs: Any) -> Any:
            start_ns = time.monotonic_ns()
            try:
                return callback(*args, **kwargs)
            finally:
                end_ns = time.monotonic_ns()
                index = args[0] if args else kwargs.get("i", kwargs.get("step", None))
                self.callback_count += 1
                step_index = index if isinstance(index, int) and not isinstance(index, bool) else None
                total_steps = (
                    args[3]
                    if len(args) > 3 and isinstance(args[3], int) and not isinstance(args[3], bool)
                    else kwargs.get("total_steps")
                )
                self._callbacks.append({
                    "step_index": step_index,
                    "total_steps": total_steps if isinstance(total_steps, int) else None,
                    "start_ns": start_ns,
                    "end_ns": end_ns,
                })
                self._event(
                    "callback",
                    step_index=step_index,
                    index=index if isinstance(index, (int, str, type(None))) else None,
                    wall_ms=self._duration_ms(start_ns, end_ns),
                    callback_wall_ms=self._duration_ms(start_ns, end_ns),
                )

        return timed_callback

    def finish_sampling(self, patcher: Any, *, ok: bool) -> None:
        end_ns = time.monotonic_ns()
        if self._sampling_start_ns is not None:
            self.sampler_wall_ms = self._duration_ms(self._sampling_start_ns, end_ns)
        self.allocator["sampling_after"] = _allocator_state()
        callback_total = next(
            (item["total_steps"] for item in self._callbacks if item["total_steps"] is not None),
            None,
        )
        step_callbacks = [
            item for item in self._callbacks
            if item["step_index"] is not None
            and (callback_total is None or item["step_index"] < callback_total)
        ]
        if step_callbacks and all(item["step_index"] is not None for item in step_callbacks):
            steps: list[dict[str, Any]] = []
            previous_ns = self._sampling_start_ns
            for item in step_callbacks:
                boundary_ns = int(item["start_ns"])
                duration_ms = (
                    self._duration_ms(previous_ns, boundary_ns)
                    if previous_ns is not None
                    else None
                )
                steps.append({
                    "step_index": item["step_index"],
                    "wall_ms": duration_ms,
                    "callback_wall_ms": self._duration_ms(item["start_ns"], item["end_ns"]),
                })
                previous_ns = boundary_ns
            self.step_timeline = steps
            self.step_timeline_unavailable_reason = None
        else:
            self.step_timeline = None
            self.step_timeline_unavailable_reason = (
                "callback_not_observed"
                if not self._callbacks
                else "callback_step_index_unavailable"
            )
        diffusion_model = getattr(self, "_diffusion_model", None)
        if diffusion_model is None:
            try:
                model = getattr(patcher, "model", None) if patcher is not None else None
                diffusion_model = getattr(model, "diffusion_model", None)
            except Exception:
                diffusion_model = None
        self.cachedit = _read_cachedit_state(patcher, diffusion_model)
        self._event(
            "sampling_end",
            ok=bool(ok),
            wall_ms=self.sampler_wall_ms,
            allocator=self.allocator["sampling_after"],
            cachedit=self.cachedit,
        )

    def _remove_model_hooks(self) -> None:
        for handle in self._model_hooks:
            try:
                remove = getattr(handle, "remove", None)
                if callable(remove):
                    remove()
            except Exception:
                pass
        self._model_hooks = []

    def cleanup(self) -> None:
        if self._cleanup_done:
            return
        started_ns = time.monotonic_ns()
        self._remove_model_hooks()
        self._cleanup_done = True
        self._event("final_cleanup", wall_ms=self._duration_ms(started_ns, time.monotonic_ns()))

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "enabled": True,
            "sampler": {
                "node_id": self.sampler_id,
                "class_type": self.sampler_class,
                "wall_ms": self.sampler_wall_ms,
            },
            "allocator": dict(self.allocator),
            "model_forward": {
                "count": self.model_forward_count,
                "first_wall_ms": self.first_model_forward_wall_ms,
            },
            "callback": {
                "available": self.callback_available,
                "count": self.callback_count,
            },
            "steps": self.step_timeline,
            "steps_unavailable": self.step_timeline is None,
            "steps_unavailable_reason": self.step_timeline_unavailable_reason,
            "cachedit": self.cachedit or {
                "available": False,
                "source": None,
                "attached": None,
                "config": {"warmup_steps": None, "skip_interval": None},
                "expected": None,
                "computed": None,
                "cached": None,
                "skipped": None,
                "hit_rate": None,
                "recompute_reasons": None,
                "unavailable_fields": [
                    "expected", "computed", "cached", "skipped",
                    "hit_rate", "recompute_reasons",
                ],
            },
            "timeline": list(self.timeline),
            "cleanup_complete": self._cleanup_done,
        }


# ── SafeTensors header / planning (exact semantics, fail-closed) ──────────


def parse_safetensors_header(path: str) -> dict:
    """Read and fully validate an 8-byte-length safetensors header.

    Returns ``{"status": "ok", header, data_start, total_data_bytes,
    tensor_count, size_bytes}`` or ``{"status": "error", reason}``.  Validates
    per-tensor dtype/shape/offset consistency, total coverage of the data
    section by contiguous non-overlapping ranges, and exact file size.
    """
    out: dict = {"status": "error", "path": str(path)}
    try:
        size = int(os.path.getsize(path))
        if size < 8:
            return {**out, "reason": "truncated_header"}
        with open(path, "rb") as fh:
            raw = fh.read(8)
        if len(raw) < 8:
            return {**out, "reason": "truncated_header"}
        header_len = int.from_bytes(raw, "little")
        if header_len <= 0 or header_len > size - 8:
            return {**out, "reason": f"invalid_header_len:{header_len}"}
        with open(path, "rb") as fh:
            fh.seek(8)
            hb = fh.read(header_len)
        if len(hb) != header_len:
            return {**out, "reason": "truncated_header_bytes"}
        header = json.loads(hb.decode("utf-8"))
        if not isinstance(header, dict):
            return {**out, "reason": "header_not_object"}
        data_start = 8 + header_len
        data_bytes = size - data_start
        if data_bytes <= 0:
            return {**out, "reason": "no_tensor_data"}
        ranges: list[tuple[int, int, str]] = []
        count = 0
        for key, info in header.items():
            if key == "__metadata__":
                continue
            if not isinstance(info, dict):
                return {**out, "reason": f"tensor_entry_not_dict:{key}"}
            offs = info.get("data_offsets")
            if not isinstance(offs, (list, tuple)) or len(offs) != 2:
                return {**out, "reason": f"bad_data_offsets:{key}"}
            if any(isinstance(v, bool) or not isinstance(v, int) for v in offs):
                return {**out, "reason": f"non_integer_offsets:{key}"}
            start, end = int(offs[0]), int(offs[1])
            if start < 0 or end < start:
                return {**out, "reason": f"negative_or_inverted_range:{key}"}
            dtype_name = str(info.get("dtype", ""))
            dtype = _TORCH_DTYPE.get(dtype_name)
            if dtype is None:
                return {**out, "reason": f"unsupported_dtype:{key}:{dtype_name}"}
            shape = info.get("shape")
            if not isinstance(shape, (list, tuple)):
                return {**out, "reason": f"bad_shape:{key}"}
            if any(isinstance(d, bool) or not isinstance(d, int) for d in shape):
                return {**out, "reason": f"non_integer_shape:{key}"}
            shape_values = [int(d) for d in shape]
            if any(d < 0 for d in shape_values):
                return {**out, "reason": f"negative_shape:{key}"}
            expected = int(math.prod(shape_values)) * int(dtype.itemsize)
            length = end - start
            if length != expected:
                return {**out, "reason": f"dtype_shape_size_mismatch:{key}:{length}!={expected}"}
            ranges.append((start, end, str(key)))
            count += 1
        if not ranges:
            return {**out, "reason": "no_tensor_data"}
        expect = 0
        for start, end, key in sorted(ranges):
            if end > data_bytes:
                return {**out, "reason": f"range_out_of_bounds:{key}"}
            if start != expect:
                return {
                    **out,
                    "reason": f"non_contiguous_data_ranges:{key}:expected={expect}:got={start}",
                }
            expect = end
        if expect != data_bytes:
            return {**out, "reason": f"data_section_end_mismatch:{expect}!={data_bytes}"}
        return {
            **out,
            "status": "ok",
            "header": header,
            "data_start": int(data_start),
            "total_data_bytes": int(data_bytes),
            "tensor_count": int(count),
            "size_bytes": int(size),
        }
    except Exception as exc:
        return {**out, "reason": f"{type(exc).__name__}: {str(exc)[:160]}"}


def partition_coverage(ranges: list, total: int) -> tuple[bool, str]:
    """Ranges (relative [start,end)) must exactly cover [0,total): sorted at 0,
    contiguous, no overlap, final end == total."""
    if not ranges:
        return (total == 0), "empty"
    rs = sorted((int(s), int(e)) for s, e in ranges)
    expect = 0
    for s, e in rs:
        if s != expect:
            return False, f"gap_or_overlap at {s} (expected {expect})"
        if e < s:
            return False, f"inverted_range {s}..{e}"
        expect = e
    if expect != int(total):
        return False, f"end {expect} != total {total}"
    return True, "ok"


def plan_source_regions(
    data_start: int, total_data_bytes: int, block_bytes: int, qd: int
) -> list[list[tuple[int, int]]]:
    """Exactly *qd* static forward-only DATA SECTION regions of <=block_bytes."""
    data_start = int(data_start)
    total_data_bytes = int(total_data_bytes)
    block_bytes = max(1, int(block_bytes))
    qd = max(1, int(qd))
    if data_start < 0 or total_data_bytes < 0:
        raise ValueError("invalid data section")
    blocks = [
        (data_start + off, min(block_bytes, total_data_bytes - off))
        for off in range(0, total_data_bytes, block_bytes)
    ]
    regions: list[list[tuple[int, int]]] = []
    base, extra = divmod(len(blocks), qd)
    cursor = 0
    for worker in range(qd):
        count = base + (1 if worker < extra else 0)
        regions.append(blocks[cursor : cursor + count])
        cursor += count
    return regions


def build_header_tensor_map(header: dict) -> list[tuple[str, str, list, int, int]]:
    """(key, dtype_str, shape, rel_start, length) tuples in file order."""
    tensor_map: list[tuple[str, str, list, int, int]] = []
    for key, info in header.items():
        if key == "__metadata__":
            continue
        offs = info.get("data_offsets") or [0, 0]
        start = int(offs[0])
        length = int(offs[1]) - start
        if length <= 0:
            continue
        tensor_map.append((
            str(key),
            str(info.get("dtype", "")),
            [int(d) for d in (info.get("shape") or [])],
            start,
            length,
        ))
    return tensor_map


# ── QD GPU transport owner ────────────────────────────────────────────────

# Registry of every thread this module creates (stronger than a name scan:
# teardown asserts on these exact handles, not just on naming conventions).
_GOLDEN_THREAD_LOCK = threading.Lock()
_GOLDEN_THREADS: set = set()
_GOLDEN_QD_OPERATIONS: set = set()


class GoldenQDOwner:
    """Owner of the contiguous CUDA destination buffer + pinned staging slots.

    Tensors produced by :func:`read_file_qd_gpu` are zero-copy views over the
    retained CUDA buffer; they are only valid while this owner is alive.
    ``close()``/``release_storage()`` are idempotent.  For the UNET role the
    CUDA buffer backs live model weights (``assign=True`` storage sharing), so
    teardown only releases staging slots via :meth:`release_staging`; process
    exit owns final CUDA/model reclamation.
    """

    def __init__(self, gpu_buf: Any, slots: list, device: str, role: str):
        self._gpu_buf = gpu_buf
        self._slots = list(slots)
        self.device = str(device)
        self.role = str(role)
        self.closed = False

    @property
    def gpu_buf(self) -> Any:
        return self._gpu_buf

    @property
    def slots(self) -> list:
        return list(self._slots)

    def release_staging(self) -> None:
        """Release pinned staging slots only (safe while views are live)."""
        self._slots = []

    def release_storage(self, purge_allocator: bool = False) -> None:
        """Release backing storage; the RA9G seam supplies an explicit no-purge contract."""
        if purge_allocator:
            raise RuntimeError("golden_qd_owner_allocator_purge_forbidden")
        if self.closed:
            return
        self.closed = True
        self.release_staging()
        self._gpu_buf = None

    def close(self) -> None:
        self.release_storage()


def _wait_event_host_ns(event: Any, *, measure: bool = True) -> int:
    if event is None:
        raise RuntimeError("missing_completion_event")
    started = time.perf_counter_ns() if measure else None
    query = getattr(event, "query", None)
    complete = bool(query()) if callable(query) else False
    if not complete:
        sync = getattr(event, "synchronize", None)
        if not callable(sync):
            raise RuntimeError("completion_event_not_waitable")
        sync()
        if callable(query) and not bool(query()):
            raise RuntimeError("incomplete_completion_event")
    return max(0, time.perf_counter_ns() - int(started)) if started is not None else 0


def _wait_event_host(event: Any) -> float:
    return _wait_event_host_ns(event) / 1e6


def _cuda_event_elapsed_ms(start_event: Any, end_event: Any) -> Optional[float]:
    elapsed = getattr(start_event, "elapsed_time", None)
    if not callable(elapsed):
        return None
    try:
        value = float(elapsed(end_event))
    except Exception:
        return None
    return value if math.isfinite(value) and value >= 0 else None


def _read_at(fd: int, mv: Any, offset: int) -> int:
    """Fill ``mv`` fully from absolute file offset (preadv > pread > lseek+read)."""
    total = 0
    if hasattr(os, "preadv"):
        while total < len(mv):
            n = int(os.preadv(fd, [mv[total:]], int(offset) + total))
            if n <= 0:
                break
            total += n
    elif hasattr(os, "pread"):
        while total < len(mv):
            data = os.pread(fd, len(mv) - total, int(offset) + total)
            n = len(data)
            if n <= 0:
                break
            mv[total : total + n] = data
            total += n
    else:
        while total < len(mv):
            os.lseek(fd, int(offset) + total, os.SEEK_SET)
            data = os.read(fd, len(mv) - total)
            n = len(data)
            if n <= 0:
                break
            mv[total : total + n] = data
            total += n
    return total


class _SourceTelemetry:
    """Observed source-read depth/counters (never fabricated from records)."""

    READ_DURATION_SAMPLE_LIMIT = 4096

    def __init__(self, qd: int, *, enabled: bool = True):
        self.enabled = bool(enabled)
        self._lock = threading.Lock()
        self.inflight = 0
        self.max_inflight = 0
        self.earliest_start_ns: Optional[int] = None
        self.latest_end_ns: Optional[int] = None
        self.read_count = 0
        self.read_bytes = 0
        self.read_duration_samples_ns: list[int] = []
        self.read_duration_max_ns: Optional[int] = None
        self.per_worker = {
            i: {"read_count": 0, "read_bytes": 0, "first_start_ns": None, "last_end_ns": None}
            for i in range(int(qd))
        }

    def before(self, worker_id: int) -> int:
        if not self.enabled:
            return 0
        now = time.perf_counter_ns()
        with self._lock:
            self.inflight += 1
            self.max_inflight = max(self.max_inflight, self.inflight)
            self.earliest_start_ns = (
                now if self.earliest_start_ns is None else min(self.earliest_start_ns, now)
            )
            worker = self.per_worker[int(worker_id)]
            if worker["first_start_ns"] is None:
                worker["first_start_ns"] = now
        return now

    def after(self, worker_id: int, started_ns: int, read_bytes: int) -> int:
        if not self.enabled:
            return 0
        now = time.perf_counter_ns()
        with self._lock:
            self.inflight -= 1
            self.latest_end_ns = (
                now if self.latest_end_ns is None else max(self.latest_end_ns, now)
            )
            worker = self.per_worker[int(worker_id)]
            duration_ns = max(0, now - int(started_ns))
            self.read_count += 1
            self.read_bytes += int(read_bytes)
            if len(self.read_duration_samples_ns) < self.READ_DURATION_SAMPLE_LIMIT:
                self.read_duration_samples_ns.append(duration_ns)
            self.read_duration_max_ns = (
                duration_ns if self.read_duration_max_ns is None
                else max(self.read_duration_max_ns, duration_ns)
            )
            worker["read_count"] += 1
            worker["read_bytes"] += int(read_bytes)
            worker["last_end_ns"] = now
        return now

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "inflight": self.inflight,
                "max_inflight": self.max_inflight,
                "earliest_start_ns": self.earliest_start_ns,
                "latest_end_ns": self.latest_end_ns,
                "read_count": self.read_count,
                "read_bytes": self.read_bytes,
                "read_duration_samples_ns": list(self.read_duration_samples_ns),
                "read_duration_sample_limit": self.READ_DURATION_SAMPLE_LIMIT,
                "read_duration_max_ns": self.read_duration_max_ns,
                "per_worker": {str(k): dict(v) for k, v in self.per_worker.items()},
            }


class _QDReaderState:
    """Authoritative completion ledger for one QD transport run."""

    def __init__(self, regions: list[list[tuple[int, int]]], *, diagnostics_enabled: bool = True):
        self.regions = regions
        self.diagnostics_enabled = bool(diagnostics_enabled)
        self._lock = threading.Lock()
        self.records: list[dict] = []
        self.errors: list[str] = []
        self.submitted = 0
        self.completed = 0
        self.buffer_pool_wait_ms = 0.0
        self.buffer_pool_wait_ns = 0
        self.buffer_pool_wait_count = 0
        self.h2d_wait_ns = 0
        self.h2d_wait_count = 0
        self.h2d_gpu_event_ns = 0
        self.h2d_gpu_event_count = 0
        self._worker_counts = {
            wid: {"submitted": 0, "completed": 0, "record_bytes": 0}
            for wid in range(len(regions))
        }
        self._worker_finalization: dict[int, dict] = {}
        self.workers_joined = False
        self.events_waited = False

    @property
    def planned_items(self) -> list[tuple[int, int]]:
        return [item for region in self.regions for item in region]

    def submit(self, worker_id: int) -> None:
        with self._lock:
            self.submitted += 1
            worker = self._worker_counts.setdefault(
                int(worker_id), {"submitted": 0, "completed": 0, "record_bytes": 0}
            )
            worker["submitted"] += 1

    def record(self, record: dict) -> None:
        with self._lock:
            self.records.append(record)
            self.completed += 1
            worker = self._worker_counts.setdefault(
                int(record["worker_id"]), {"submitted": 0, "completed": 0, "record_bytes": 0}
            )
            worker["completed"] += 1
            worker["record_bytes"] += int(record.get("read_len", 0))

    def error(self, worker_id: int, exc: BaseException) -> None:
        with self._lock:
            self.errors.append(f"worker={worker_id}:{type(exc).__name__}:{str(exc)[:160]}")

    def add_buffer_wait(self, ms: float) -> None:
        if not self.diagnostics_enabled:
            return
        with self._lock:
            self.buffer_pool_wait_ms += float(ms)
            self.buffer_pool_wait_count += 1

    def add_buffer_wait_ns(self, value: int) -> None:
        if not self.diagnostics_enabled:
            return
        with self._lock:
            self.buffer_pool_wait_ns += max(0, int(value))

    def add_h2d_wait_ns(self, value: int) -> None:
        if not self.diagnostics_enabled:
            return
        with self._lock:
            self.h2d_wait_ns += max(0, int(value))
            self.h2d_wait_count += 1

    def add_h2d_gpu_event_ms(self, value: Optional[float]) -> None:
        if not self.diagnostics_enabled or value is None:
            return
        with self._lock:
            self.h2d_gpu_event_ns += max(0, int(round(float(value) * 1e6)))
            self.h2d_gpu_event_count += 1

    def finalize_worker(self, worker_id: int) -> None:
        with self._lock:
            counts = self._worker_counts.get(int(worker_id), {"submitted": 0, "completed": 0, "record_bytes": 0})
            self._worker_finalization[int(worker_id)] = {
                "finalized": True,
                "submitted_count": int(counts["submitted"]),
                "record_count": int(counts["completed"]),
                "record_bytes": int(counts["record_bytes"]),
            }

    def worker_finalization_snapshot(self) -> dict:
        with self._lock:
            return {str(k): dict(v) for k, v in self._worker_finalization.items()}


def _qd_gpu_worker(
    state: _QDReaderState,
    slots: list,
    events: list,
    start_events: list,
    gpu_buf: Any,
    data_start: int,
    fd: int,
    worker_id: int,
    telemetry: _SourceTelemetry,
    diagnostics_enabled: bool,
) -> None:
    """One static source worker: positioned reads into its two pinned slots,
    async non-blocking H2D into the contiguous CUDA buffer, slot reuse gated
    on the previous copy's completion event."""
    slot_records: list[Optional[dict]] = [None, None]
    try:
        for index, (abs_start, ln) in enumerate(state.regions[worker_id]):
            slot_index = index % 2
            previous = slot_records[slot_index]
            if previous is not None:
                end_event = events[slot_index]
                wait_ns = _wait_event_host_ns(end_event, measure=diagnostics_enabled)
                previous["h2d_completed_bytes"] = int(previous["planned_len"])
                if diagnostics_enabled:
                    previous["h2d_wait_ns"] = wait_ns
                    state.add_buffer_wait(wait_ns / 1e6)
                    state.add_buffer_wait_ns(wait_ns)
                    state.add_h2d_wait_ns(wait_ns)
                    previous["h2d_gpu_event_ms"] = _cuda_event_elapsed_ms(
                        start_events[slot_index], end_event
                    )
                    state.add_h2d_gpu_event_ms(previous["h2d_gpu_event_ms"])
            rel = int(abs_start) - int(data_start)
            if rel < 0 or rel + int(ln) > int(gpu_buf.numel()):
                raise RuntimeError(f"destination_slice_out_of_range:{rel}:{ln}")
            state.submit(worker_id)
            started = telemetry.before(worker_id) if diagnostics_enabled else 0
            slot = slots[slot_index]
            if not bool(getattr(slot, "is_pinned", lambda: False)()):
                raise RuntimeError("pinned_slot_required")
            mv = memoryview(slot.numpy())[:ln]
            got = int(_read_at(fd, mv, abs_start))
            ended = telemetry.after(worker_id, started, got) if diagnostics_enabled else 0
            record = {
                "worker_id": worker_id,
                "off": int(abs_start),
                "planned_len": int(ln),
                "read_len": int(got),
                "source_start_ns": started if diagnostics_enabled else None,
                "source_end_ns": ended if diagnostics_enabled else None,
            }
            if diagnostics_enabled:
                record.update({
                    "cpu_to_pinned_start_ns": started,
                    "cpu_to_pinned_end_ns": ended,
                })
            record.update({
                "slot_index": slot_index,
                "h2d_submitted_bytes": 0,
                "h2d_completed_bytes": 0,
            })
            if diagnostics_enabled:
                record.update({
                    "h2d_enqueue_start_ns": None,
                    "h2d_enqueue_end_ns": None,
                    "h2d_wait_ns": 0,
                    "h2d_gpu_event_ms": None,
                })
            record["error"] = None
            state.record(record)
            if got != ln:
                record["error"] = f"short_read got={got} want={ln}"
                state.error(worker_id, RuntimeError(record["error"]))
                continue
            event = events[slot_index]
            if event is None:
                raise RuntimeError("missing_completion_event")
            try:
                if diagnostics_enabled:
                    record["h2d_enqueue_start_ns"] = time.perf_counter_ns()
                    start_events[slot_index].record()
                gpu_buf[rel : rel + ln].copy_(slot[:ln], non_blocking=True)
                event.record()
                if diagnostics_enabled:
                    record["h2d_enqueue_end_ns"] = time.perf_counter_ns()
            except BaseException as exc:
                record["error"] = f"h2d_failed:{type(exc).__name__}"
                state.error(worker_id, exc)
                continue
            record["h2d_submitted_bytes"] = int(ln)
            slot_records[slot_index] = record
    except BaseException as exc:
        state.error(worker_id, exc)
    finally:
        state.finalize_worker(worker_id)


def validate_transport_records(
    records: list[dict],
    planned_items: list[tuple[int, int]],
    data_start: int,
    total: int,
) -> tuple[bool, str]:
    """Exact planned/read/H2D reconciliation (pure; fail-closed)."""
    expected = sorted((int(off), int(ln)) for off, ln in planned_items)
    actual = sorted((int(r.get("off", -1)), int(r.get("planned_len", -1))) for r in records)
    if len(records) != len(planned_items) or actual != expected:
        return False, f"block_count_or_identity:{len(records)}:{len(planned_items)}"
    rel = [(off - int(data_start), off - int(data_start) + ln) for off, ln in expected]
    ok, reason = partition_coverage(rel, int(total))
    if not ok:
        return False, reason
    if any(int(r.get("read_len", 0)) != int(r["planned_len"]) for r in records):
        return False, "read_bytes_reconciliation"
    if any(int(r.get("h2d_submitted_bytes", 0)) != int(r["planned_len"]) for r in records):
        return False, "h2d_submitted_reconciliation"
    if any(int(r.get("h2d_completed_bytes", 0)) != int(r["planned_len"]) for r in records):
        return False, "h2d_completed_reconciliation"
    return True, "ok"


def check_view_alignment(rel_start: int, length: int, elem_size: int, shape: list) -> None:
    """Fail-closed zero-copy view alignment proof (no alignment-copy fallback)."""
    if int(rel_start) % int(elem_size) != 0:
        raise RuntimeError(f"view_misaligned_offset:{rel_start}:{elem_size}")
    if int(length) % int(elem_size) != 0:
        raise RuntimeError(f"view_misaligned_length:{length}:{elem_size}")
    if int(length) != int(math.prod(shape)) * int(elem_size):
        raise RuntimeError(f"view_length_mismatch:{length}")


def make_zero_copy_view(gpu_buf: Any, dtype: torch.dtype, shape: list, rel_start: int, length: int) -> Any:
    """Typed zero-copy view over the contiguous CUDA destination buffer."""
    if getattr(gpu_buf, "device", None) is None or str(gpu_buf.device).split(":")[0] != "cuda":
        raise RuntimeError(f"non_cuda_destination:{getattr(gpu_buf, 'device', None)}")
    check_view_alignment(int(rel_start), int(length), int(dtype.itemsize), list(shape))
    flat = gpu_buf[int(rel_start) : int(rel_start) + int(length)]
    return flat.view(dtype).view(tuple(shape))


def _read_file_qd_gpu_dispatcher(
    path: str,
    *,
    role: str,
    device: Optional[str],
    qd: int,
    block_bytes: int,
    diagnostics: Optional[bool],
) -> dict:
    """Run the opt-in dispatcher arm and adapt it to the Golden load contract.

    The legacy implementation below is intentionally left intact.  This arm
    owns only the source/H2D transport plane: Golden still creates typed views,
    performs adoption proofs, and retains the returned CUDA backing owner at
    the same stage boundaries as the control path.
    """
    transport_module = importlib.import_module("comfymodal_runtime.golden_qd_transport")
    selected = transport_module.normalize_transport_arm("dispatcher")
    if selected != "dispatcher":
        raise RuntimeError(f"unexpected_dispatcher_arm:{selected}")
    qd = max(1, min(32, int(qd)))
    block_bytes = max(1, int(block_bytes))
    diagnostics_enabled = stage_diagnostics_enabled() if diagnostics is None else bool(diagnostics)
    if not torch.cuda.is_available():
        raise RuntimeError("cuda_unavailable")
    dev = device or f"cuda:{torch.cuda.current_device()}"

    total_start_ns = time.perf_counter_ns()
    header_start_ns = time.perf_counter_ns()
    parsed = parse_safetensors_header(path)
    header_end_ns = time.perf_counter_ns()
    if parsed.get("status") != "ok":
        raise RuntimeError(f"header_invalid:{parsed.get('reason')}")
    header = parsed["header"]
    data_start = int(parsed["data_start"])
    total = int(parsed["total_data_bytes"])
    layout_start_ns = time.perf_counter_ns()
    tensor_map = build_header_tensor_map(header)
    regions = plan_source_regions(data_start, total, block_bytes, qd)
    items = [item for region in regions for item in region]
    coverage_ok, coverage_reason = partition_coverage(
        [(off - data_start, off - data_start + ln) for off, ln in items], total
    )
    if not coverage_ok:
        raise RuntimeError(f"coverage:{coverage_reason}")
    layout_end_ns = time.perf_counter_ns()

    gpu_buf = None
    owner: Optional[GoldenQDOwner] = None
    dispatcher = None
    try:
        gpu_buf = torch.empty(total, dtype=torch.uint8, device=dev)
        owner = GoldenQDOwner(gpu_buf, [], dev, role=role)
        cuda_backend = transport_module.CudaTransferBackend(gpu_buf)

        class _MeasuredCudaBackend:
            """Measure host submit calls without copying the lease payload."""

            def __init__(self, backend: Any):
                self.backend = backend
                self.staging_allocation_ns = 0
                self.submit_wall_ns = 0
                self.submit_count = 0

            def allocate_staging_buffers(self, slots: int, block_size: int) -> Any:
                started = time.perf_counter_ns()
                try:
                    return self.backend.allocate_staging_buffers(slots, block_size)
                finally:
                    self.staging_allocation_ns += max(0, time.perf_counter_ns() - started)

            def submit_h2d(self, source: Any, destination_offset: int) -> Any:
                # StagingPool exposes an ephemeral memoryview for lease
                # generation safety.  Turn that view into a Tensor view, not a
                # Python payload, before handing it to CudaTransferBackend.
                if not isinstance(source, torch.Tensor):
                    source = torch.frombuffer(source, dtype=torch.uint8)
                started = time.perf_counter_ns()
                try:
                    return self.backend.submit_h2d(source, destination_offset)
                finally:
                    self.submit_wall_ns += max(0, time.perf_counter_ns() - started)
                    self.submit_count += 1

            def poll_event(self, event: Any) -> Any:
                return self.backend.poll_event(event)

            def cancel_event(self, event: Any) -> None:
                return self.backend.cancel_event(event)

        backend = _MeasuredCudaBackend(cuda_backend)
        staging_slots = max(2 * qd, 1)
        config = transport_module.TransportConfig(
            queue_depth=qd,
            block_bytes=block_bytes,
            staging_slots=staging_slots,
            ready_queue_capacity=staging_slots,
            producer_workers=qd,
            capacity_class=f"qd{qd}-{block_bytes}",
        )
        dispatcher = transport_module.create_transport(
            "dispatcher", config=config, backend=backend
        )
        staging_allocation_ns = int(backend.staging_allocation_ns)
        flags = os.O_RDONLY | getattr(os, "O_BINARY", 0)

        source_telemetry = _SourceTelemetry(qd, enabled=True)

        class _PositionedSource:
            """One positioned source object with one descriptor per producer."""

            def __init__(self) -> None:
                self._fds: dict[int, int] = {}
                self._lock = threading.Lock()
                self.open_count = 0

            def _fd_for_thread(self) -> int:
                thread_id = threading.get_ident()
                with self._lock:
                    fd = self._fds.get(thread_id)
                    if fd is None:
                        fd = os.open(path, flags)
                        self._fds[thread_id] = fd
                        self.open_count += 1
                    return fd

            def readinto(self, target: Any, offset: int) -> int:
                worker_id = threading.get_ident() % qd
                started = source_telemetry.before(worker_id)
                try:
                    got = int(_read_at(self._fd_for_thread(), target, int(offset)))
                except BaseException:
                    raise
                else:
                    source_telemetry.after(worker_id, started, got)
                    return got

            def close(self) -> None:
                with self._lock:
                    fds = tuple(self._fds.items())
                closed: list[tuple[int, int]] = []
                errors: list[OSError] = []
                for thread_id, fd in fds:
                    try:
                        os.close(fd)
                    except OSError as exc:
                        errors.append(exc)
                    else:
                        closed.append((thread_id, fd))
                with self._lock:
                    for thread_id, fd in closed:
                        if self._fds.get(thread_id) == fd:
                            self._fds.pop(thread_id, None)
                if errors:
                    primary = errors[0]
                    for secondary in errors[1:]:
                        primary.add_note(f"additional source close failure: {secondary}")
                    raise primary

        source = _PositionedSource()

        source_ranges = [
            transport_module.SourceRange(
                int(abs_start), int(length), int(abs_start) - data_start, index
            )
            for index, (abs_start, length) in enumerate(items)
        ]
        result = dispatcher.execute(
            source_ranges,
            source,
            destination_size=total,
            materialize_output=False,
            parse_count=1,
            owner=owner,
            owner_count=1,
            adoption_result="transport_backing_pending",
        )
        dispatcher.snapshot_quiescence()
        telemetry = dict(result.telemetry)
        source_snapshot = source_telemetry.snapshot()
        source_wall_ns = (
            max(0, int(source_snapshot["latest_end_ns"]) - int(source_snapshot["earliest_start_ns"]))
            if source_snapshot["earliest_start_ns"] is not None
            and source_snapshot["latest_end_ns"] is not None
            else 0
        )
        source_wall_ms = source_wall_ns / 1e6
        source_bytes = int(source_snapshot["read_bytes"])
        source_read_count = int(source_snapshot["read_count"])
        if source_bytes != total or source_bytes != int(telemetry.get("source_bytes") or 0):
            raise RuntimeError(
                f"source_read_reconciliation:{source_bytes}:{telemetry.get('source_bytes')}:{total}"
            )
        source_open_count = int(source.open_count)
        source_gbps = (
            source_bytes / max(source_wall_ms * 1_000_000.0, 1.0)
            if source_wall_ms > 0 else None
        )
        records = []
        for record in result.records:
            records.append({
                "worker_id": None,
                "off": int(record.source_offset),
                "planned_len": int(record.nbytes),
                "read_len": int(record.nbytes),
                "slot_index": None,
                "h2d_submitted_bytes": int(record.nbytes),
                "h2d_completed_bytes": int(record.nbytes),
                "error": None,
            })
        record_ok, record_reason = validate_transport_records(records, items, data_start, total)
        if not record_ok:
            raise RuntimeError(f"record_reconciliation:{record_reason}")
        if int(result.submitted_bytes) != total or int(result.completed_bytes) != total:
            raise RuntimeError(
                f"h2d_reconciliation:{result.submitted_bytes}:{result.completed_bytes}:{total}"
            )
        h2d_bytes = int(result.completed_bytes)
        h2d_submit_wall = {
            "wall_ns": int(backend.submit_wall_ns),
            "wall_ms": backend.submit_wall_ns / 1e6,
            "submit_count": int(backend.submit_count),
            "bytes": int(result.submitted_bytes),
            "timing_scope": "TOTAL host CudaTransferBackend.submit_h2d intervals",
        }
        h2d_event_poll = {
            "status": "OBSERVED",
            "wall_ns": int(float(telemetry.get("dispatcher_reap_wall_ms") or 0.0) * 1e6),
            "wall_ms": float(telemetry.get("dispatcher_reap_wall_ms") or 0.0),
            "poll_count": int(telemetry.get("dispatcher_reap_count") or 0),
            "timing_scope": "TOTAL dispatcher event polling/reap",
        }
        h2d_event_completion = {
            "status": "OBSERVED",
            "latency_ms": telemetry.get("h2d_event_completion_latency_ms"),
            "sample_count": int(telemetry.get("h2d_completed_count") or 0),
            "timing_scope": "PARTIAL H2D submit-to-event completion latency",
        }
        h2d_event_wait = {
            "status": "NOT RUN",
            "reason": "dispatcher polling/reap does not measure host event wait",
        }
        per_read = _read_duration_summary(source_snapshot)
        ready_wait_ns = int(float(telemetry.get("ready_queue_block_wall_ms") or 0.0) * 1e6)
        lease_wait_ns = int(float(telemetry.get("producer_capacity_block_wall_ms") or 0.0) * 1e6)
        exact_reconciliation = {
            "ok": True,
            "reason": "ok",
            "planned_ranges": len(items),
            "completed_ranges": len(records),
            "planned_bytes": total,
            "source_read_bytes": source_bytes,
            "h2d_submitted_bytes": int(result.submitted_bytes),
            "h2d_completed_bytes": h2d_bytes,
        }
        dispatcher_stats = {
            **telemetry,
            "execution_arm": "dispatcher",
            "total_entry_to_return_wall_ms": telemetry.get("total_entry_to_return_wall_ms"),
            "source_bytes": source_bytes,
            "source_read_count": source_read_count,
            "source_open_count": source_open_count,
            "h2d_submitted_bytes": int(result.submitted_bytes),
            "h2d_completed_bytes": h2d_bytes,
            "source_read_wall_ns": source_wall_ns,
            "source_read_wall_ms": source_wall_ms,
            "source_reads_per_read": per_read,
            "h2d_submit_wall": h2d_submit_wall,
            "h2d_event_poll": h2d_event_poll,
            "h2d_event_completion": h2d_event_completion,
            "h2d_event_wait": h2d_event_wait,
            "lease_wait_ns": lease_wait_ns,
            "ready_backpressure_wait_ns": ready_wait_ns,
            "producer_qd_occupancy": {
                "target": telemetry.get("source_qd_target"),
                "max_depth": max(telemetry.get("source_qd_depth_samples") or [0]),
                "fraction_time_at_target": telemetry.get("fraction_time_at_target_source_qd"),
                "timeline": telemetry.get("source_qd_timeline") or [],
            },
            "free_ready_depth": {
                "minimum_free_slots": telemetry.get("minimum_free_slots"),
                "ready_queue_depth_at_end": telemetry.get("ready_queue_depth"),
            },
            "fallback": {
                "count": int(telemetry.get("fallback_count") or 0),
                "reason": telemetry.get("fallback_reason"),
            },
            "exact_reconciliation": exact_reconciliation,
            "owner_count": 1,
            "adoption_result": "transport_backing_pending",
        }
        stats = {
            "kind": "golden_qd_read",
            "role": str(role),
            "status": "ok",
            "execution_arm": "dispatcher",
            "configured_qd": qd,
            "block_bytes": int(block_bytes),
            "file_bytes": total,
            "planned_block_count": len(items),
            "submitted_block_count": len(records),
            "completed_block_count": len(records),
            "bytes_read": source_bytes,
            "source_read_count": source_read_count,
            "source_read_bytes": source_bytes,
            "h2d_submitted_bytes": int(result.submitted_bytes),
            "h2d_completed_bytes": h2d_bytes,
            "qd_source_io_wall_ms": source_wall_ms,
            "qd_source_gbps": source_gbps,
            "effective_source_gbps": source_gbps,
            "effective_h2d_gbps": None,
            "max_inflight": max(telemetry.get("source_qd_depth_samples") or [0]),
            "pinned_bytes": staging_slots * block_bytes,
            "gpu_bytes": total,
            "buffer_pool_wait_ms": float(telemetry.get("producer_capacity_block_wall_ms") or 0.0),
            "source_open_header_layout": {
                "header_layout_ns": max(0, header_end_ns - header_start_ns),
                "header_layout_ms": (header_end_ns - header_start_ns) / 1e6,
                "source_open_ns": None,
                "source_open_ms": None,
                "tensor_layout_ns": max(0, layout_end_ns - layout_start_ns),
                "tensor_layout_ms": (layout_end_ns - layout_start_ns) / 1e6,
            },
            "staging": {
                "allocation_count": staging_slots,
                "allocated_bytes": staging_slots * block_bytes,
                "reuse_count": max(0, len(items) - staging_slots),
                "retained_bytes": 0,
                "allocation_ns": staging_allocation_ns,
                "memory_kind": "pinned",
                "pinned": True,
                "retained_by": "request_dispatcher_pool_until_quiescence",
            },
            "source_reads": {
                "bytes": source_bytes,
                "copy_count": source_read_count,
                "read_count": source_read_count,
                "wall_ns": source_wall_ns,
                "wall_ms": source_wall_ms,
                "per_read": per_read,
                "timing_scope": "TOTAL positioned readinto intervals; may overlap",
            },
            "cpu_to_pinned_staging": {
                "status": "NOT RUN",
                "reason": "positioned readinto fills the acquired staging lease directly",
            },
            "allocation_pinning": {
                "status": "OBSERVED",
                "allocation_ns": staging_allocation_ns,
                "allocation_count": staging_slots,
                "allocated_bytes": staging_slots * block_bytes,
                "pinned_bytes": staging_slots * block_bytes,
                "pinned": True,
                "timing_scope": "TOTAL CudaTransferBackend pinned staging allocation",
            },
            "pinned_slot_wait": {
                "status": "NOT RUN",
                "reason": "dispatcher has no legacy pinned slots",
            },
            "lease_wait": {
                "wait_ns": lease_wait_ns,
                "wait_ms": lease_wait_ns / 1e6,
                "wait_count": int(telemetry.get("producer_capacity_block_count") or 0),
                "timing_scope": "TOTAL waits to acquire a reusable dispatcher lease",
            },
            "ready_backpressure": {
                "wait_ns": ready_wait_ns,
                "wait_ms": ready_wait_ns / 1e6,
                "wait_count": int(telemetry.get("ready_queue_block_count") or 0),
                "ready_capacity": config.ready_queue_capacity,
                "ready_depth_at_end": telemetry.get("ready_queue_depth"),
                "timing_scope": "TOTAL producer waits for dispatcher ready-queue capacity",
            },
            "producer_qd_occupancy": dispatcher_stats["producer_qd_occupancy"],
            "free_ready_depth": dispatcher_stats["free_ready_depth"],
            "h2d_enqueue": {
                "bytes": int(result.submitted_bytes),
                "copy_count": int(telemetry.get("h2d_submitted_count") or 0),
                "wall_ns": h2d_submit_wall["wall_ns"],
                "wall_ms": h2d_submit_wall["wall_ms"],
                "submit_count": h2d_submit_wall["submit_count"],
                "timing_scope": "TOTAL host CudaTransferBackend.submit_h2d intervals",
            },
            "h2d_gpu_event": {
                "duration_ns": None,
                "duration_ms": None,
                "copy_count": int(telemetry.get("h2d_completed_count") or 0),
                "bytes": h2d_bytes,
                "scope": "event completion latency is reported separately",
                "non_additive": True,
            },
            "h2d_submit_wall": h2d_submit_wall,
            "h2d_event_poll": h2d_event_poll,
            "h2d_event_completion": h2d_event_completion,
            "h2d_event_wait": h2d_event_wait,
            "final_drain": {
                "wall_ns": int(float(telemetry.get("final_drain_wall_ms") or 0.0) * 1e6),
                "wall_ms": telemetry.get("final_drain_wall_ms"),
                "timing_scope": "TOTAL dispatcher final drain interval",
            },
            "waits_quiescence": {
                "workers_joined": True,
                "h2d_events_waited": True,
                "copies_complete": True,
                "operation_live": False,
                "lease_wait_ns": lease_wait_ns,
                "ready_backpressure_wait_ns": ready_wait_ns,
                "dispatcher_reap_count": int(telemetry.get("dispatcher_reap_count") or 0),
                "final_drain_wall_ms": telemetry.get("final_drain_wall_ms"),
            },
            "quiescence": {
                "workers_joined": True,
                "h2d_events_waited": True,
                "copies_complete": True,
                "operation_live": False,
            },
            "coverage": {"ok": True, "reason": "ok"},
            "record_reconciliation": exact_reconciliation,
            "fallback": {
                "pin_fallback": 0,
                "alignment_tensor_count": 0,
                "fallback_count": int(telemetry.get("fallback_count") or 0),
                "fallback_reason": telemetry.get("fallback_reason"),
            },
            "blocks": records,
            "dispatcher_telemetry": dispatcher_stats,
            "header_parse_count": 1,
            "source_open_count": source_open_count,
            "duplicate_read_count": int(telemetry.get("duplicate_read_count") or 0),
            "owner_count": 1,
            "adoption_result": "transport_backing_pending",
            "transport_entry_ns": total_start_ns,
            "post_transport_construction_adoption": {
                "status": "NOT RUN",
                "reason": "outside the dispatcher transport/read boundary",
            },
        }
        stats["owner_count"] = 1
        stats["adoption_result"] = "backing_owner_retained_for_adoption"
        views: dict[str, Any] = {}
        for key, dtype_str, shape, rel_start, length in tensor_map:
            dtype = _TORCH_DTYPE.get(dtype_str)
            if dtype is None:
                raise RuntimeError(f"unsupported_dtype:{key}:{dtype_str}")
            views[key] = make_zero_copy_view(
                gpu_buf, dtype, shape, rel_start, length
            )
        return {
            "status": "ok",
            "sd": views,
            "owner": owner,
            "stats": stats,
            "tensor_map": tensor_map,
            "header_metadata": header.get("__metadata__"),
        }
    except BaseException as exc:
        retain_owner = bool(
            owner is not None
            and dispatcher is not None
            and not dispatcher.backend_owner_release_allowed()
        )
        if owner is not None and not retain_owner:
            try:
                owner.release_storage()
            except Exception:
                pass
        wrapped = RuntimeError(
            f"golden_qd_transport_failed[{role}]:{type(exc).__name__}:{str(exc)[:200]}"
        )
        telemetry = getattr(exc, "telemetry", None)
        if isinstance(telemetry, Mapping):
            wrapped.telemetry = copy.deepcopy(dict(telemetry))
        transport_failure = getattr(exc, "to_dict", None)
        if callable(transport_failure):
            try:
                wrapped.transport_failure = copy.deepcopy(transport_failure())
            except Exception:
                pass
        if retain_owner:
            # This is the fail-closed ownership handoff for a late CUDA event:
            # keep both the owner and transport/backend reachable until the
            # event reaches a terminal state, rather than releasing storage in
            # adapter error cleanup.
            wrapped.retained_owner = owner
            wrapped.retained_transport = dispatcher
        elif getattr(exc, "retained_transport", None) is not None:
            # Preserve a retriable source handle after a close failure.
            wrapped.retained_transport = exc.retained_transport
        raise wrapped from exc
def read_file_qd_gpu(
    path: str,
    *,
    role: str,
    device: Optional[str] = None,
    qd: int = GOLDEN_QD,
    block_bytes: int = GOLDEN_BLOCK_BYTES,
    diagnostics: Optional[bool] = None,
    transport_arm: Optional[str] = None,
) -> dict:
    """Single-source QD physical transport: parse header -> plan -> four source
    workers (one fd each, two pinned slots each) -> positioned reads -> async
    non-blocking H2D into ONE contiguous uint8 CUDA buffer -> join all workers
    -> wait all completion events -> exact reconciliation -> zero-copy typed
    views -> retained owner.

    Fails closed (RuntimeError, all resources released) on: malformed header,
    duplicate/missing region, pin allocation failure, short read, missing
    completion event, non-CUDA destination, unsupported/misaligned tensors,
    or any reconciliation error.  There is NO pin fallback, NO alignment-copy
    fallback, and NO reread.
    """
    if golden_qd_transport_arm(transport_arm) == "dispatcher":
        return _read_file_qd_gpu_dispatcher(
            path,
            role=role,
            device=device,
            qd=qd,
            block_bytes=block_bytes,
            diagnostics=diagnostics,
        )
    qd = max(1, min(32, int(qd)))
    block_bytes = max(1, int(block_bytes))
    diagnostics_enabled = (
        stage_diagnostics_enabled() if diagnostics is None else bool(diagnostics)
    )
    if not torch.cuda.is_available():
        raise RuntimeError("cuda_unavailable")
    dev = device or f"cuda:{torch.cuda.current_device()}"
    header_start_ns = time.perf_counter_ns() if diagnostics_enabled else None
    parsed = parse_safetensors_header(path)
    if parsed.get("status") != "ok":
        raise RuntimeError(f"header_invalid:{parsed.get('reason')}")
    header = parsed["header"]
    data_start = int(parsed["data_start"])
    total = int(parsed["total_data_bytes"])
    header_end_ns = time.perf_counter_ns() if diagnostics_enabled else None
    layout_start_ns = time.perf_counter_ns() if diagnostics_enabled else None
    tensor_map = build_header_tensor_map(header)
    regions = plan_source_regions(data_start, total, block_bytes, qd)
    items = [item for region in regions for item in region]
    cov_ok, cov_reason = partition_coverage(
        [(off - data_start, off - data_start + ln) for off, ln in items], total
    )
    if not cov_ok:
        raise RuntimeError(f"coverage:{cov_reason}")
    layout_end_ns = time.perf_counter_ns() if diagnostics_enabled else None

    stats: dict = {
        "kind": "golden_qd_read",
        "role": str(role),
        "status": "running",
        "configured_qd": qd,
        "block_bytes": int(block_bytes),
        "file_bytes": total,
        "planned_block_count": len(items),
        "submitted_block_count": 0,
        "completed_block_count": 0,
        "bytes_read": 0,
        "h2d_submitted_bytes": 0,
        "h2d_completed_bytes": 0,
        "source_read_count": 0,
        "source_read_bytes": 0,
        "qd_source_io_wall_ms": None,
        "qd_source_gbps": None,
        "max_inflight": 0,
        "pinned_bytes": 0,
        "gpu_bytes": total,
        "buffer_pool_wait_ms": 0.0,
        "coverage": {"ok": False, "reason": "not_validated"},
        "record_reconciliation": {"ok": False, "reason": "not_finalized"},
        # Fail-closed transport: these counters are structurally always zero.
        "fallback": {"pin_fallback": 0, "alignment_tensor_count": 0},
        "blocks": [],
        "quiescence": {
            "workers_joined": False,
            "h2d_events_waited": False,
            "copies_complete": False,
            "operation_live": True,
        },
    }
    if diagnostics_enabled:
        stats.update({
            "effective_source_gbps": None,
            "effective_h2d_gbps": None,
            "source_bytes": 0,
            "staging_allocation_bytes": 0,
            "staging_reuse_count": sum(max(0, len(region) - 2) for region in regions),
            "staging_retained_bytes": 0,
            "buffer_pool_wait_ns": 0,
            "source_open_header_layout": {
                "header_layout_ns": None,
                "header_layout_ms": None,
                "source_open_ns": None,
                "source_open_ms": None,
                "tensor_layout_ns": None,
                "tensor_layout_ms": None,
            },
            "staging": {
                "allocation_count": 0,
                "allocated_bytes": 0,
                "reuse_count": sum(max(0, len(region) - 2) for region in regions),
                "retained_bytes": 0,
                "allocation_ns": None,
                "retained_by": "transport_owner",
                "memory_kind": "pinned",
                "pinned": True,
            },
            "source_reads": {},
            "cpu_to_pinned_staging": {
                "status": "NOT RUN",
                "reason": "positioned reads land directly in pinned slots; no separate CPU copy",
            },
            "allocation_pinning": {},
            "pinned_slot_wait": {},
            "h2d_enqueue": {},
            "h2d_submit_wall": {},
            "h2d_gpu_event": {},
            "h2d_event_wait": {},
            "waits_quiescence": {},
            "final_drain": {},
            "post_transport_construction_adoption": {
                "status": "NOT RUN",
                "reason": "outside the QD transport/read boundary",
            },
            "memory_visibility": {
                "before": _host_memory_visibility(),
                "after": None,
            },
        })
    cuda_before = int(torch.cuda.memory_allocated()) if diagnostics_enabled else None
    owner: Optional[GoldenQDOwner] = None
    fds: list[int] = []
    threads: list[threading.Thread] = []
    operation_token = object()
    with _GOLDEN_THREAD_LOCK:
        _GOLDEN_QD_OPERATIONS.add(operation_token)
    try:
        gpu_buf = torch.empty(total, dtype=torch.uint8, device=dev)
        slots: list[list] = []
        events: list[list] = []
        start_events: list[list] = []
        allocation_start_ns = time.perf_counter_ns() if diagnostics_enabled else None
        for _ in range(qd):
            worker_slots: list = []
            worker_events: list = []
            worker_start_events: list = []
            for _slot in range(2):
                try:
                    slot = torch.empty(block_bytes, dtype=torch.uint8, pin_memory=True)
                except Exception as exc:
                    raise RuntimeError(f"pin_allocation_failed:{type(exc).__name__}") from exc
                if not bool(getattr(slot, "is_pinned", lambda: False)()):
                    raise RuntimeError("pin_allocation_failed:not_pinned")
                worker_slots.append(slot)
                # Completion events are correctness machinery.  Start events
                # are timing-only and do not exist on the normal path.
                worker_events.append(torch.cuda.Event(enable_timing=False))
                if diagnostics_enabled:
                    worker_start_events.append(torch.cuda.Event(enable_timing=True))
            slots.append(worker_slots)
            events.append(worker_events)
            start_events.append(worker_start_events)
        stats["pinned_bytes"] = sum(block_bytes for worker in slots for _ in worker)
        if diagnostics_enabled:
            stats["staging"] = {
                **stats["staging"],
                "allocation_count": qd * 2,
                "allocated_bytes": stats["pinned_bytes"],
                "retained_bytes": stats["pinned_bytes"],
                "allocation_ns": time.perf_counter_ns() - int(allocation_start_ns),
            }
            stats["staging_allocation_bytes"] = stats["staging"]["allocated_bytes"]
            stats["staging_retained_bytes"] = stats["staging"]["retained_bytes"]

        state = _QDReaderState(regions, diagnostics_enabled=diagnostics_enabled)
        telemetry = _SourceTelemetry(qd, enabled=diagnostics_enabled)
        flags = os.O_RDONLY | getattr(os, "O_BINARY", 0)
        open_start_ns = time.perf_counter_ns() if diagnostics_enabled else None
        fds = [os.open(path, flags) for _ in range(qd)]
        if diagnostics_enabled:
            stats["source_open_header_layout"]["source_open_ns"] = (
                time.perf_counter_ns() - int(open_start_ns)
            )
            stats["source_open_header_layout"]["source_open_ms"] = round(
                stats["source_open_header_layout"]["source_open_ns"] / 1e6, 4
            )
        for i in range(qd):
            t = threading.Thread(
                target=_qd_gpu_worker,
                args=(
                    state, slots[i], events[i], start_events[i], gpu_buf,
                    data_start, fds[i], i, telemetry, diagnostics_enabled,
                ),
                daemon=True,
                name=f"golden-qd-{role}-{i}",
            )
            threads.append(t)
        with _GOLDEN_THREAD_LOCK:
            _GOLDEN_THREADS.update(threads)
        t_wall0 = time.perf_counter_ns() if diagnostics_enabled else None
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        state.workers_joined = True
        worker_join_wall_ns = (
            max(0, time.perf_counter_ns() - int(t_wall0))
            if diagnostics_enabled else None
        )

        # Wait every outstanding CUDA completion event before declaring the
        # buffer contents final; mark the protected records complete.
        final_drain_start_ns = time.perf_counter_ns() if diagnostics_enabled else None
        final_drain_count = 0
        for record in state.records:
            if record.get("h2d_submitted_bytes") and not record.get("h2d_completed_bytes"):
                event = events[int(record["worker_id"])][int(record["slot_index"])]
                wait_ns = _wait_event_host_ns(event, measure=diagnostics_enabled)
                record["h2d_completed_bytes"] = int(record["planned_len"])
                if diagnostics_enabled:
                    final_drain_count += 1
                    record["h2d_wait_ns"] = wait_ns
                    state.add_h2d_wait_ns(wait_ns)
                    record["h2d_gpu_event_ms"] = _cuda_event_elapsed_ms(
                        start_events[int(record["worker_id"])][int(record["slot_index"])], event
                    )
                    state.add_h2d_gpu_event_ms(record["h2d_gpu_event_ms"])
        state.events_waited = True
        final_drain_end_ns = time.perf_counter_ns() if diagnostics_enabled else None

        source = (
            telemetry.snapshot()
            if diagnostics_enabled
            else {"max_inflight": 0, "earliest_start_ns": None, "latest_end_ns": None}
        )
        stats["max_inflight"] = source["max_inflight"]
        stats["source_read_count"] = source.get("read_count", len(state.records))
        # NOTE: qd_source_io_wall_ms / qd_source_gbps are computed BELOW, after
        # the reconciled record bytes are populated into stats["bytes_read"].

        valid, reason = validate_transport_records(state.records, items, data_start, total)
        stats["coverage"] = {"ok": valid, "reason": reason}
        stats["submitted_block_count"] = int(state.submitted)
        stats["completed_block_count"] = len(state.records)
        stats["bytes_read"] = sum(int(r.get("read_len", 0)) for r in state.records)
        stats["source_read_bytes"] = source.get("read_bytes", stats["bytes_read"])
        stats["h2d_submitted_bytes"] = sum(int(r.get("h2d_submitted_bytes", 0)) for r in state.records)
        stats["h2d_completed_bytes"] = sum(int(r.get("h2d_completed_bytes", 0)) for r in state.records)
        stats["buffer_pool_wait_ms"] = round(state.buffer_pool_wait_ms, 4)
        if diagnostics_enabled:
            stats["source_bytes"] = stats["source_read_bytes"]
            stats["buffer_pool_wait_ns"] = state.buffer_pool_wait_ns
        stats["blocks"] = list(state.records)

        # Actual positioned-read wall is the observed earliest read start to
        # latest read end.  It is intentionally narrower than worker launch
        # through join (which includes thread scheduling and CUDA submission).
        source_wall_ns = None
        if source["earliest_start_ns"] is not None and source["latest_end_ns"] is not None:
            source_wall_ns = max(
                0,
                int(source["latest_end_ns"]) - int(source["earliest_start_ns"]),
            )

        # Throughput is computed from the RECONCILED byte totals above.  The
        # denominator is a nonzero floor of 1ns so tiny reads whose observed
        # earliest/latest timestamps are equal still report >0 GB/s; zero is
        # kept only for a zero-byte read or missing timing observations.
        start_ns, end_ns = source["earliest_start_ns"], source["latest_end_ns"]
        if start_ns is not None and end_ns is not None:
            elapsed_ns = max(int(end_ns) - int(start_ns), 1)
            stats["qd_source_io_wall_ms"] = round(elapsed_ns / 1_000_000, 4)
            stats["qd_source_gbps"] = round(stats["bytes_read"] / elapsed_ns, 4)
            if diagnostics_enabled:
                stats["effective_source_gbps"] = stats["qd_source_gbps"]

        if diagnostics_enabled:
            source_layout = stats["source_open_header_layout"]
            source_layout["header_layout_ns"] = max(0, int(header_end_ns) - int(header_start_ns))
            source_layout["header_layout_ms"] = round(source_layout["header_layout_ns"] / 1e6, 4)
            source_layout["tensor_layout_ns"] = max(0, int(layout_end_ns) - int(layout_start_ns))
            source_layout["tensor_layout_ms"] = round(source_layout["tensor_layout_ns"] / 1e6, 4)

        source_records = list(state.records)
        if diagnostics_enabled:
            cpu_intervals = [
                {"start_ns": r.get("cpu_to_pinned_start_ns"), "end_ns": r.get("cpu_to_pinned_end_ns")}
                for r in source_records
            ]
            enqueue_intervals = [
                {"start_ns": r.get("h2d_enqueue_start_ns"), "end_ns": r.get("h2d_enqueue_end_ns")}
                for r in source_records
            ]
            stats["source_reads"] = {
                **aggregate_timing_intervals(
                    [{"start_ns": r.get("source_start_ns"), "end_ns": r.get("source_end_ns")} for r in source_records]
                ),
                "bytes": stats["bytes_read"],
                "wall_ns": source_wall_ns,
                "read_count": source.get("read_count", len(source_records)),
                "read_bytes": source.get("read_bytes", stats["bytes_read"]),
                "per_read": _read_duration_summary(source),
                "timing_scope": "TOTAL positioned _read_at intervals; may overlap",
            }
            stats["cpu_to_pinned_staging"] = {
                "status": "NOT RUN",
                "reason": "positioned reads land directly in pinned slots; no separate CPU copy",
            }
            stats["h2d_enqueue"] = {
                **aggregate_timing_intervals(enqueue_intervals),
                "bytes": stats["h2d_submitted_bytes"],
                "timing_scope": "TOTAL host H2D submit intervals; may overlap",
            }
            stats["h2d_submit_wall"] = dict(stats["h2d_enqueue"])
            h2d_event_ns = state.h2d_gpu_event_ns
            stats["h2d_gpu_event"] = {
                "duration_ns": h2d_event_ns if state.h2d_gpu_event_count else None,
                "duration_ms": round(h2d_event_ns / 1e6, 4) if state.h2d_gpu_event_count else None,
                "copy_count": state.h2d_gpu_event_count,
                "bytes": stats["h2d_completed_bytes"],
                "scope": "sum_of_copy_event_durations",
                "non_additive": True,
            }
            if h2d_event_ns > 0:
                stats["effective_h2d_gbps"] = round(stats["h2d_completed_bytes"] / h2d_event_ns, 4)
            stats["allocation_pinning"] = {
                "status": "OBSERVED",
                "allocation_ns": stats["staging"].get("allocation_ns"),
                "allocation_count": stats["staging"].get("allocation_count"),
                "allocated_bytes": stats["staging"].get("allocated_bytes"),
                "pinned_bytes": stats["pinned_bytes"],
                "pinned": True,
                "timing_scope": "TOTAL pinned-slot allocation loop",
            }
            stats["pinned_slot_wait"] = {
                "wait_ns": state.buffer_pool_wait_ns,
                "wait_ms": state.buffer_pool_wait_ns / 1e6,
                "wait_count": state.buffer_pool_wait_count,
                "timing_scope": "TOTAL host waits before legacy pinned-slot reuse",
            }
            stats["h2d_event_wait"] = {
                "wait_ns": state.h2d_wait_ns,
                "wait_ms": state.h2d_wait_ns / 1e6,
                "wait_count": state.h2d_wait_count,
                "timing_scope": "TOTAL host waits for H2D completion events",
            }
            final_drain_ns = (
                max(0, int(final_drain_end_ns) - int(final_drain_start_ns))
                if final_drain_start_ns is not None and final_drain_end_ns is not None else None
            )
            stats["final_drain"] = {
                "wall_ns": final_drain_ns,
                "wall_ms": final_drain_ns / 1e6 if final_drain_ns is not None else None,
                "event_wait_count": final_drain_count,
                "timing_scope": "TOTAL final outstanding-event drain after worker join",
            }
        if diagnostics_enabled:
            stats["waits_quiescence"] = {
                "buffer_pool_wait_ns": state.buffer_pool_wait_ns,
                "h2d_wait_ns": state.h2d_wait_ns,
                "h2d_event_wait_count": state.h2d_wait_count,
                "pinned_slot_wait_count": state.buffer_pool_wait_count,
                "final_drain": dict(stats["final_drain"]),
                "workers_joined": state.workers_joined,
                "h2d_events_waited": state.events_waited,
                "copies_complete": False,
            }

        finalization = state.worker_finalization_snapshot()
        recon_ok = True
        recon_reasons: list[str] = []
        for wid_str, fin in finalization.items():
            worker_records = [r for r in state.records if str(r["worker_id"]) == wid_str]
            if (
                int(fin["record_count"]) != len(worker_records)
                or int(fin["record_bytes"]) != sum(int(r["read_len"]) for r in worker_records)
            ):
                recon_ok = False
                recon_reasons.append(f"worker={wid_str}:finalization_mismatch")
        if stats["source_read_count"] > len(state.records):
            recon_ok = False
            recon_reasons.append("source_exceeds_records")
        stats["record_reconciliation"] = {
            "ok": recon_ok,
            "reason": "ok" if recon_ok else ";".join(recon_reasons),
        }

        if state.errors or not valid or not recon_ok or stats["bytes_read"] != total:
            raise RuntimeError(
                ";".join(state.errors) or reason or stats["record_reconciliation"]["reason"]
            )

        finalization = state.worker_finalization_snapshot()
        if not state.workers_joined or set(finalization) != {str(i) for i in range(qd)}:
            raise RuntimeError("qd_workers_not_finalized")
        if not state.events_waited or any(
            int(r.get("h2d_completed_bytes", 0)) != int(r.get("planned_len", 0))
            for r in state.records
        ):
            raise RuntimeError("qd_h2d_not_complete")
        stats["quiescence"] = {
            "workers_joined": True,
            "h2d_events_waited": True,
            "copies_complete": True,
            "operation_live": False,
        }
        if diagnostics_enabled:
            stats["waits_quiescence"].update(stats["quiescence"])
        if diagnostics_enabled:
            stats["memory_visibility"]["after"] = {
                "host": _host_memory_visibility(),
                "cuda": _allocator_state(),
            }

        sd: dict[str, Any] = {}
        for key, dtype_str, shape, rel_start, length in tensor_map:
            dt = _TORCH_DTYPE.get(dtype_str)
            if dt is None:
                raise RuntimeError(f"unsupported_dtype:{key}:{dtype_str}")
            sd[key] = make_zero_copy_view(gpu_buf, dt, shape, rel_start, length)

        owner = GoldenQDOwner(gpu_buf, [slot for worker in slots for slot in worker], dev, role=role)
        stats["status"] = "ok"
        if diagnostics_enabled:
            stats["cuda_alloc_delta_bytes"] = max(
                int(torch.cuda.memory_allocated()) - int(cuda_before), 0
            )
        # Retain the parsed safetensors metadata from the INITIAL transport so
        # consumers (e.g. VAE) never reread the header/payload after transport.
        return {
            "status": "ok",
            "sd": sd,
            "owner": owner,
            "stats": stats,
            "tensor_map": tensor_map,
            "header_metadata": header.get("__metadata__"),
        }
    except BaseException as exc:
        if owner is not None:
            try:
                owner.release_storage()
            except Exception:
                pass
        stats["status"] = "error"
        stats["error"] = f"{type(exc).__name__}: {str(exc)[:200]}"
        raise RuntimeError(f"golden_qd_transport_failed[{role}]:{stats['error']}") from exc
    finally:
        # If setup/start or validation failed before the normal join block,
        # finish joining every worker here before releasing the operation from
        # the registry.  A failed load must never return with a live source
        # worker.
        for t in threads:
            if t.is_alive():
                t.join()
        with _GOLDEN_THREAD_LOCK:
            _GOLDEN_QD_OPERATIONS.discard(operation_token)
            for t in threads:
                _GOLDEN_THREADS.discard(t)
        for t in threads:
            if t.is_alive():
                raise RuntimeError("qd_worker_thread_still_alive_after_join")
        for fd in fds:
            try:
                os.close(fd)
            except Exception:
                pass


def _require_transport_quiescence(transport: dict, *, tag: str) -> dict:
    """Require the QD operation's joined/copy-complete proof at stage return."""
    stats = transport.get("stats") or {}
    proof = stats.get("quiescence") or {}
    required = ("workers_joined", "h2d_events_waited", "copies_complete")
    if any(proof.get(key) is not True for key in required):
        raise RuntimeError(f"{tag}_qd_not_quiescent:{proof}")
    if proof.get("operation_live") is not False:
        raise RuntimeError(f"{tag}_qd_operation_live:{proof}")
    with _GOLDEN_THREAD_LOCK:
        live_threads = [t.name for t in _GOLDEN_THREADS if t.is_alive()]
        live_operations = len(_GOLDEN_QD_OPERATIONS)
    if live_threads or live_operations:
        raise RuntimeError(
            f"{tag}_golden_qd_live:threads={live_threads}:operations={live_operations}"
        )
    return dict(proof)


def _assert_runner_quiescence(runner: Any) -> None:
    """Require completion of work observed/owned by the Golden runner.

    A foreign ``assert_quiescent`` method is not an authority: it may be a
    test double or may know only about futures passed to ``_resolve``.
    """
    if isinstance(runner, GoldenSerialRunner):
        runner.assert_quiescent()
        return
    futures = getattr(runner, "_golden_futures", ())
    if any(not future.done() for future in futures):
        raise RuntimeError("golden_future_pending")
    baseline = getattr(runner, "_golden_task_baseline", None)
    current = asyncio.current_task()
    tasks = set(asyncio.all_tasks())
    if baseline is not None:
        tasks.difference_update(baseline)
    tasks.discard(current)
    pending = [task for task in tasks if not task.done()]
    if pending:
        raise RuntimeError(f"golden_task_pending:{len(pending)}")


# ── Passive runtime-only snapshot content proof ───────────────────────────


# Modal does not expose serialized snapshot bytes inside the callback.  The
# adapter therefore supplies the process RSS measured immediately before the
# capture boundary as a conservative resident-memory proxy.  It is explicitly
# recorded as such; it must never be reported as a platform-serialized size.
GOLDEN_SNAPSHOT_SIZE_LIMIT_BYTES = 5 * 1024 * 1024 * 1024
SNAPSHOT_SIZE_SOURCE = "process_rss_pre_capture_resident_memory_proxy"
_SNAPSHOT_PROOF_MAX_SIZE_BYTES = GOLDEN_SNAPSHOT_SIZE_LIMIT_BYTES
_SNAPSHOT_PROOF_ATOMIC_TYPES = (type(None), bool, int, float, complex, str, bytes, bytearray)
_SNAPSHOT_PROOF_MAX_DEPTH = 2
_SNAPSHOT_PROOF_MAX_NODES = 128
_SNAPSHOT_PROOF_MAX_CHILDREN = 32


def _is_opaque_surface_leaf(obj: Any) -> bool:
    """Identify values that are deliberately not treated as data surfaces."""
    if isinstance(obj, _SNAPSHOT_PROOF_ATOMIC_TYPES):
        return True
    if isinstance(obj, types.ModuleType):
        return True
    if inspect.isclass(obj) or inspect.isroutine(obj):
        return True
    return (
        inspect.ismethoddescriptor(obj)
        or inspect.isdatadescriptor(obj)
        or inspect.isgetsetdescriptor(obj)
        or inspect.ismemberdescriptor(obj)
        or isinstance(obj, (property, staticmethod, classmethod))
    )


def _surface_namespace(obj: Any) -> Optional[dict]:
    """Read an instance namespace without invoking user ``__getattribute__``."""
    try:
        namespace = object.__getattribute__(obj, "__dict__")
    except Exception:
        return None
    return namespace if isinstance(namespace, dict) else None


def _surface_value(obj: Any, name: str, default: Any = None) -> Any:
    """Read a known instance field without invoking arbitrary descriptors."""
    namespace = _surface_namespace(obj)
    if namespace is not None and name in namespace:
        try:
            return namespace[name]
        except Exception:
            return default
    return default


def _safe_class_has_attribute(obj: Any, name: str) -> bool:
    """Check a known class surface without invoking an instance descriptor."""
    try:
        for cls in type(obj).__mro__:
            if name in vars(cls):
                return True
    except Exception:
        return False
    return False


def _surface_children(obj: Any) -> Any:
    """Return a safe child iterator for selected proof surfaces only."""
    if type(obj) is dict:
        return dict.values(obj)
    if type(obj) is list:
        return list.__iter__(obj)
    if type(obj) is tuple:
        return tuple.__iter__(obj)
    if type(obj) is set:
        return set.__iter__(obj)
    if type(obj) is frozenset:
        return frozenset.__iter__(obj)
    namespace = _surface_namespace(obj)
    if isinstance(namespace, dict):
        return dict.values(namespace)
    return None


def _validate_snapshot_size(snapshot_size_bytes: Any) -> int:
    """Validate the positive pre-capture resident-memory proxy."""
    if (
        isinstance(snapshot_size_bytes, bool)
        or not isinstance(snapshot_size_bytes, int)
        or snapshot_size_bytes <= 0
    ):
        raise RuntimeError("snapshot_proof_snapshot_size_unavailable")
    if snapshot_size_bytes >= _SNAPSHOT_PROOF_MAX_SIZE_BYTES:
        raise RuntimeError(
            f"snapshot_proof_snapshot_size_limit:{snapshot_size_bytes}:"
            f"{_SNAPSHOT_PROOF_MAX_SIZE_BYTES}"
        )
    return snapshot_size_bytes


def golden_snapshot_content_proof(
    *,
    roots: Iterable[Any] = (),
    registries: Iterable[Any] = (),
    coordinators: Iterable[Any] = (),
    roles: tuple = ("unet", "clip", "vae"),
    persist_path: Optional[str] = None,
    snapshot_size_bytes: Optional[int] = None,
    snapshot_size_source: str = SNAPSHOT_SIZE_SOURCE,
    snapshot_size_is_serialized: bool = False,
) -> dict:
    """Passively prove the pre-capture snapshot is below the hard size limit.

    ``snapshot_size_bytes`` is the required pre-capture process-RSS proxy.  The
    source and non-serialized marker are fixed by this contract so a report
    cannot mislabel RSS as a platform-serialized snapshot size.  The supplied
    surfaces are retained as metadata and traversed only through a small fixed
    selected-root bound.  The traversal reads built-in container values and
    instance ``__dict__`` values only; it never invokes arbitrary properties,
    follows GC referents, or copies tensor contents.  Thus cycles and
    arbitrarily deep runtime scaffolding cannot crash startup, while nested
    tensor/model contamination within the proof bound fails closed.
    """
    surfaces = [("root", r) for r in roots] + [("registry", r) for r in registries] + [
        ("coordinator", c) for c in coordinators
    ]
    if not surfaces:
        # Fail closed: a proof with no supplied surfaces proves nothing and
        # must never silently pass.
        raise RuntimeError("snapshot_proof_no_surfaces_supplied")
    if snapshot_size_source != SNAPSHOT_SIZE_SOURCE:
        raise RuntimeError("snapshot_proof_snapshot_size_source_invalid")
    if snapshot_size_is_serialized is not False:
        raise RuntimeError("snapshot_proof_serialized_size_forbidden")
    measured_snapshot_size = _validate_snapshot_size(snapshot_size_bytes)
    for kind, obj in surfaces:
        scannable = isinstance(obj, (dict, list, tuple, set, frozenset))
        if (
            not scannable
            and not isinstance(obj, (torch.Tensor, asyncio.Future))
            and not _is_opaque_surface_leaf(obj)
        ):
            if _surface_namespace(obj) is None:
                raise RuntimeError(f"snapshot_proof_surface_unavailable:{kind}:{type(obj).__name__}")

    counts = {
        "tensor_count": 0,
        "parameter_bytes": 0,
        "model_patcher_count": 0,
        "qd_owner_count": 0,
        "open_payload_reader_count": 0,
        "preload_worker_count": 0,
        "future_count": 0,
    }
    per_role = {
        str(role): {"tensor_count": 0, "parameter_bytes": 0, "qd_owner_count": 0}
        for role in roles
    }

    storage_ids: set[int] = set()
    unsafe_nested_surface = False

    def note_tensor(tensor: Any, role: Optional[str]) -> None:
        counts["tensor_count"] += 1
        try:
            storage = tensor.untyped_storage()
            storage_id = int(storage.data_ptr())
            nbytes = int(storage.nbytes())
        except Exception:
            nbytes = int(tensor.numel()) * int(tensor.element_size())
            storage_id = id(tensor)
        unique_storage = storage_id not in storage_ids
        if unique_storage:
            storage_ids.add(storage_id)
            counts["parameter_bytes"] += nbytes
        if role is not None and role in per_role:
            per_role[role]["tensor_count"] += 1
            if unique_storage:
                per_role[role]["parameter_bytes"] += nbytes

    queue: list[tuple[Any, int]] = [(item, 0) for _kind, item in surfaces]
    seen: set[int] = set()
    while queue and len(seen) < _SNAPSHOT_PROOF_MAX_NODES:
        item, depth = queue.pop(0)
        try:
            item_id = id(item)
            if item_id in seen:
                continue
            seen.add(item_id)
            if isinstance(item, torch.Tensor):
                note_tensor(item, None)
                continue
            if isinstance(item, asyncio.Future):
                counts["future_count"] += 1
                continue
            if _is_opaque_surface_leaf(item):
                continue
            if isinstance(item, (dict, list, tuple, set, frozenset)) and type(item) not in {
                dict, list, tuple, set, frozenset
            }:
                unsafe_nested_surface = True
                continue
            type_name = type(item).__name__
            if _looks_like_model_patcher(item):
                counts["model_patcher_count"] += 1
            is_qd_owner = type_name == GoldenQDOwner.__name__ or isinstance(item, GoldenQDOwner)
            if is_qd_owner:
                counts["qd_owner_count"] += 1
                role = str(_surface_value(item, "role", "") or "")
                if role in per_role:
                    per_role[role]["qd_owner_count"] += 1
                buf = _surface_value(item, "_gpu_buf")
                if isinstance(buf, torch.Tensor):
                    note_tensor(buf, role if role in per_role else None)
            closed = _surface_value(item, "closed")
            if isinstance(closed, bool) and closed is False and _safe_class_has_attribute(item, "read"):
                counts["open_payload_reader_count"] += 1
            if depth >= _SNAPSHOT_PROOF_MAX_DEPTH:
                continue
            children = _surface_children(item)
            if children is not None:
                for child_index, child in enumerate(children):
                    if child_index >= _SNAPSHOT_PROOF_MAX_CHILDREN:
                        break
                    if child is not None:
                        queue.append((child, depth + 1))
        except Exception:
            # Selected surfaces are diagnostic inputs.  An object that rejects
            # safe inspection contributes no trusted children and cannot abort
            # the proof or cleanup path.
            continue

    if unsafe_nested_surface:
        raise RuntimeError("snapshot_proof_surface_unavailable:nested_container")

    for thread in threading.enumerate():
        name = str(getattr(thread, "name", ""))
        if "preload" in name.lower() or name.startswith("golden-qd"):
            counts["preload_worker_count"] += 1

    proof = {
        "schema": "golden_snapshot_content_proof_v1",
        "passive": True,
        "surface_count": len(surfaces),
        "snapshot_size_bytes": measured_snapshot_size,
        "snapshot_size_limit_bytes": _SNAPSHOT_PROOF_MAX_SIZE_BYTES,
        "snapshot_size_source": SNAPSHOT_SIZE_SOURCE,
        "snapshot_size_is_serialized": False,
        **counts,
        "roles": per_role,
    }
    nonzero = {
        key: value
        for key, value in counts.items()
        if value != 0
    }
    nonzero_roles = {
        role: sub
        for role, sub in per_role.items()
        if any(sub.values())
    }
    proof["nonzero"] = nonzero
    proof["nonzero_roles"] = nonzero_roles
    if persist_path:
        parent = os.path.dirname(os.path.abspath(str(persist_path)))
        os.makedirs(parent, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=parent, prefix=".golden_snapshot_", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(proof, fh, indent=1, default=str)
            os.replace(tmp, str(persist_path))
        except BaseException:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise
    if nonzero or nonzero_roles:
        raise RuntimeError(f"snapshot_proof_nonzero:{json.dumps(proof, default=str)[:800]}")
    return proof


def _looks_like_model_patcher(obj: Any) -> bool:
    """Detect upstream and dynamic patchers without relying on one class name."""
    type_name = type(obj).__name__
    if type_name in {"ModelPatcher", "ModelPatcherDynamic", "CoreModelPatcher"}:
        return True
    if (
        type_name.endswith("ModelPatcher")
        or type_name.endswith("ModelPatcherDynamic")
        or "modelpatcher" in type_name.lower()
        or "model_patcher" in type_name.lower()
    ):
        return True
    try:
        import comfy.model_patcher as model_patcher

        classes = tuple(
            cls for cls in (
                getattr(model_patcher, "ModelPatcher", None),
                getattr(model_patcher, "ModelPatcherDynamic", None),
                getattr(model_patcher, "CoreModelPatcher", None),
            ) if isinstance(cls, type)
        )
        if classes and isinstance(obj, classes):
            return True
    except (ImportError, AttributeError):
        pass
    # Capability detection covers upstream subclasses/rebindings while still
    # requiring the distinctive patcher surface.  Inspect class dictionaries,
    # rather than reading instance attributes, so hostile properties cannot be
    # invoked by the bounded proof.
    try:
        class_names = set()
        for cls in type(obj).__mro__:
            class_names.update(vars(cls))
        return {
            "is_dynamic", "model_size", "load_device", "offload_device"
        }.issubset(class_names)
    except Exception:
        return False


# ── Session ───────────────────────────────────────────────────────────────


@dataclass
class PendingDurability:
    """Required pending-durability object produced by the output stage.

    ``committed`` becomes True only after the real Volume commit completes;
    the true-durable stamp happens only at top level after that.
    """

    asset_abs_path: str
    volume_rel_path: str
    sha256: str
    byte_count: int
    sidecar_path: str
    committed: bool = False
    volume_mount_root: Optional[str] = None


@dataclass
class GoldenFinalResult:
    request_id: str
    image_sha256: str
    asset_path: str
    volume_rel_path: str
    true_durable: bool
    seriality_violation_count: int
    executed_nodes: list
    restore_observation: dict = field(default_factory=dict)
    # Persistence is application work after the Golden teardown wall.  It is
    # intentionally not part of any stage interval.
    telemetry_persist_ms: Optional[float] = None
    attention_backend: Optional[str] = None
    run_identity: dict = field(default_factory=dict)
    output_durability_mode: str = "off"
    durability_requested: bool = False
    result_durable: Optional[bool] = None
    filename: str = ""
    mime_type: str = "image/png"
    byte_count: int = 0
    width: int = 0
    height: int = 0
    output_node_id: str = ""
    image_data: str = ""

    def __post_init__(self) -> None:
        # Keep manually constructed historical strict results compatible while
        # making the serialized field unambiguous for new callers.
        if self.result_durable is None:
            self.result_durable = bool(self.true_durable)

    @property
    def restore_metadata(self) -> dict:
        return self.restore_observation

    @property
    def real_restore_interval(self) -> dict:
        return self.restore_observation


class GoldenSession:
    """Mutable per-execution session carrying frozen contracts and results."""

    def __init__(
        self,
        request: GoldenRequest,
        *,
        volume: Any,
        volume_mount_root: Optional[str] = None,
        output_root: Optional[str] = None,
        telemetry_path: Optional[str] = None,
        node_classes: Optional[dict] = None,
        contract: Optional[GoldenWorkflowContract] = None,
        snapshot_proof: Optional[Callable[[], dict]] = None,
        restore_metadata: Optional[dict] = None,
        restore_observation: Optional[dict] = None,
    ):
        self.request = request
        self.contract = contract or GoldenWorkflowContract()
        # Capture the transport arm in request evidence.  Missing external
        # bookkeeping does not gate execution; an invalid runtime selector does.
        self.qd_transport_arm = golden_qd_transport_arm()
        self.clip_residency = resolve_clip_residency(request.clip_residency)
        # Snapshot the authoritative identity at request construction so a
        # caller cannot mutate extra_data between setup and CLIP load.
        self.clip_source_identity = _ra9h_authoritative_identity(self)
        self.output_durability_policy = resolve_output_durability()
        self.output_durability_mode = self.output_durability_policy.mode
        self.durability_requested = self.output_durability_policy.durability_requested
        if isinstance(volume, GoldenVolumeHandle):
            self.volume = volume.handle
            self.volume_mount_root = str(volume.volume_mount_root)
            self.volume_contract = volume
        else:
            # Raw handles remain accepted for request-time compatibility, but
            # cannot reach durable success without an explicit mount root.
            self.volume = volume
            self.volume_mount_root = str(volume_mount_root) if volume_mount_root else None
            self.volume_contract = (
                GoldenVolumeHandle(volume, self.volume_mount_root)
                if self.volume_mount_root
                else None
            )
        self.telemetry_path = telemetry_path
        self.node_classes = node_classes
        # Required fail-closed proof boundary: the thin adapter must supply a
        # callable returning {"roots": [...], "registries": [...],
        # "coordinators": [...]} real surfaces.  This module cannot obtain
        # project-local surfaces itself (self-containment), so teardown fails
        # closed when no proof supplier was provided — it never silently
        # passes zero surfaces.
        self.snapshot_proof = snapshot_proof
        self.snapshot_proof_result: Optional[dict] = None
        self._restore_metadata_supplied = restore_metadata is not None or restore_observation is not None
        supplied_restore = restore_metadata if restore_metadata is not None else restore_observation
        if supplied_restore is not None and not isinstance(supplied_restore, dict):
            raise RuntimeError("restore_metadata_invalid_shape")
        self.restore_metadata = dict(supplied_restore or {})
        self.recorder = GoldenTelemetryRecorder()
        self.recorder.output_durability_mode = self.output_durability_mode
        self.recorder.durability_requested = self.durability_requested
        self.recorder.clip_residency = self.clip_residency
        self.clip_residency_telemetry = _new_ra9h_telemetry(self.clip_residency)
        if self.clip_source_identity:
            self.clip_residency_telemetry["source_generation_identity"] = _bounded_telemetry_value(
                self.clip_source_identity
            )
            self.clip_residency_telemetry["expected_device"] = self.clip_source_identity.get(
                "target_device"
            )
        self.recorder.clip_residency_telemetry = copy.deepcopy(self.clip_residency_telemetry)
        # P4-6 is completely absent from the default path: no hooks, callback
        # wrappers, CacheDiT inspection, or extra telemetry events are created.
        self.sampling_diagnostics: Optional[GoldenSamplingDiagnostics] = None
        requested_output_root = output_root or self.contract.output_root
        if self.volume_mount_root and not os.path.isabs(str(requested_output_root)):
            requested_output_root = os.path.join(self.volume_mount_root, str(requested_output_root))
        self.output_root = os.path.abspath(requested_output_root)
        self.runner: Optional[GoldenSerialRunner] = None
        self.node_map: Optional[GoldenNodeMap] = None
        self.model_paths: dict[str, str] = {}
        self.clip_paths: list[str] = []
        self.clip: Any = None
        self.clip_owner: Optional[GoldenQDOwner] = None
        # One retained QD owner PER checkpoint (canonical spec has exactly one).
        self.clip_owners: list = []
        # Transaction visibility begins at transport success, before a later
        # checkpoint/constructor/adoption can fail.  Teardown consults this
        # registry rather than waiting for the all-checkpoints assignment.
        self.qd_transaction_owners: list[GoldenQDOwner] = []
        # CLIP compute-scope proof is deliberately separate from the wrapper
        # root.  Small constructor-owned extras (for example logit_scale) are
        # not part of compute readiness.
        self.clip_compute_scope: Any = None
        self.clip_compute_scope_identity: dict = {}
        self.clip_load_timing: dict = {}
        self.clip_forward_timing: dict = {}
        self.clip_load_page_faults: dict = {}
        self.clip_forward_page_faults: dict = {}
        # RA9H state is request-local.  Only scalar/metadata records survive
        # the transfer; the transfer object itself is cleared after cleanup.
        self.clip_ownership_transfer: Any = None
        self.clip_ownership_transfer_record: dict = {}
        self.clip_residency_record: dict = {}
        self.clip_forward_conversion: dict = {}
        self.conditioning: Any = None
        self.patcher: Any = None
        self.unet_owner: Optional[GoldenQDOwner] = None
        self.vae: Any = None
        self.vae_owner: Optional[GoldenQDOwner] = None
        self.images: Any = None
        self.pending_durability: Optional[PendingDurability] = None
        self.output_artifact: Optional[ReadyOutputArtifact] = None
        self.final_result: Optional[GoldenFinalResult] = None
        self.telemetry_persist_ms: Optional[float] = None
        self.restore_baseline: dict = {}
        self.run_identity = {
            "request_id": str(request.request_id),
            "workflow_sha256": canonical_workflow_sha256(request.prompt),
            "attention_backend": request.attention_backend,
            "qd_transport_arm": self.qd_transport_arm,
            "clip_residency": self.clip_residency,
            "clip_residency_requested": self.clip_residency,
            "clip_residency_effective": self.clip_residency,
            "clip_source_identity_supplied": bool(self.clip_source_identity),
        }
        self.recorder.event("golden_qd_transport_selector", arm=self.qd_transport_arm)
        self.recorder.run_identity = dict(self.run_identity)

    def register_qd_owner(self, owner: GoldenQDOwner) -> None:
        """Make a successful transport owner cleanup-visible immediately."""
        if not isinstance(owner, GoldenQDOwner):
            raise RuntimeError("qd_owner_invalid")
        owners = getattr(self, "qd_transaction_owners", None)
        if owners is None:
            owners = []
            self.qd_transaction_owners = owners
        if not any(existing is owner for existing in owners):
            owners.append(owner)

    def cleanup_clip_ownership_transfer(self) -> None:
        """Release an incomplete RA9H transfer without masking the primary error."""
        transfer = getattr(self, "clip_ownership_transfer", None)
        if transfer is None:
            return
        try:
            state = str(getattr(transfer, "state", ""))
            if state != "READY":
                record = transfer.release()
                self.recorder.event("clip_fp32_cast_once_cleanup", **dict(record))
        finally:
            self.clip_ownership_transfer = None

    def build_final_result(self) -> GoldenFinalResult:
        output_mode = getattr(self, "output_durability_mode", "off")
        durability_requested = bool(
            getattr(self, "durability_requested", False)
        )
        pending = self.pending_durability
        artifact = getattr(self, "output_artifact", None)
        if output_mode == "strict":
            if pending is None or not pending.committed:
                raise RuntimeError("final_result_requires_committed_pending_durability")
            if not self.recorder.true_durable_marked:
                raise RuntimeError("final_result_requires_true_durable_mark")
            image_sha256 = pending.sha256
            asset_path = pending.asset_abs_path
            volume_rel_path = pending.volume_rel_path
            filename = os.path.basename(pending.asset_abs_path)
            mime_type = "image/png"
            byte_count = pending.byte_count
            width = 0
            height = 0
            output_node_id = str(getattr(self, "output_node_id", ""))
            image_data = ""
            result_durable = True
        else:
            if artifact is None:
                raise RuntimeError("final_result_requires_ready_output_artifact")
            if not self.recorder._first_result_ready_marked:
                raise RuntimeError("final_result_requires_first_result_ready")
            image_sha256 = artifact.sha256
            asset_path = ""
            volume_rel_path = ""
            filename = artifact.filename
            mime_type = artifact.mime_type
            byte_count = artifact.byte_count
            width = artifact.width
            height = artifact.height
            output_node_id = str(getattr(self, "output_node_id", ""))
            image_data = base64.b64encode(artifact.raw_bytes).decode("ascii")
            result_durable = False
        reconcile = self.recorder.reconcile_seriality()
        return GoldenFinalResult(
            request_id=self.request.request_id,
            image_sha256=image_sha256,
            asset_path=asset_path,
            volume_rel_path=volume_rel_path,
            true_durable=result_durable,
            seriality_violation_count=int(reconcile["count"]),
            executed_nodes=list(self.runner.executed_summary()) if self.runner else [],
            restore_observation=dict(getattr(self.recorder, "_external_restore", {})),
            attention_backend=self.request.attention_backend,
            run_identity=dict(getattr(self, "run_identity", {})),
            output_durability_mode=output_mode,
            durability_requested=durability_requested,
            result_durable=result_durable,
            filename=filename,
            mime_type=mime_type,
            byte_count=byte_count,
            width=width,
            height=height,
            output_node_id=output_node_id,
            image_data=image_data,
        )


# ── Node classification ───────────────────────────────────────────────────

HEAVY_NODE_STAGES = {
    "CLIPLoader": "clip_load",
    "CLIPTextEncode": "clip_forward",
    "UNETLoader": "unet_load",
    "VAELoader": "vae_load",
    "VAEDecode": "vae_decode",
}
SAMPLER_CLASS_HINTS = ("Sampler", "KSampler", "sampler")


def classify_node(class_type: str) -> str:
    """Classify a node class to a Golden stage ('prepare' is the default)."""
    if class_type in HEAVY_NODE_STAGES:
        return HEAVY_NODE_STAGES[class_type]
    if class_type == CANONICAL_SAMPLER_CLASS:
        return "sampling"
    if any(hint in str(class_type) for hint in SAMPLER_CLASS_HINTS):
        return "sampling"
    return "prepare"


# ── Serial upstream-semantics node runner ─────────────────────────────────


def _is_link(value: Any) -> bool:
    """Upstream link shape: [node_id:str, socket:int] (list or tuple)."""
    return (
        isinstance(value, (list, tuple))
        and len(value) == 2
        and isinstance(value[0], str)
        and isinstance(value[1], int)
        and not isinstance(value[1], bool)
    )


@dataclasses.dataclass
class _CacheEntry:
    outputs: Any
    ui: Any = None


class GoldenSerialRunner:
    """Golden-owned narrow serial runner over upstream ComfyUI node semantics.

    Executes requested node targets and their dependencies ONE node at a time.
    Preserves V1 node calls, INPUT_IS_LIST/OUTPUT_IS_LIST, lazy dependencies,
    dynamic/subgraph outputs, hidden inputs, UI outputs, and external
    custom-node semantics.  V3 nodes whose FUNCTION is EXECUTE_NORMALIZED are
    invoked through that same bound entry point and their ``NodeOutput``
    returns are narrowly normalized (.result/.ui only; block_execution and
    expand fail closed — the frozen workflow never exercises them).  Its
    embedded subset is kept aligned with the installed upstream input/output
    primitives without constructing a PromptExecutor or taking over global
    execution state.  After any node
    produces an async result it is awaited/resolved IMMEDIATELY — no other
    node is ever scheduled while a task is pending.  No generic runtime
    cache/preload bridge exists here.

    Seeded nodes (explicit outputs injected via :meth:`seed`) are never
    executed; downstream links consume the exact seeded objects.
    """

    def __init__(self, prompt: dict, *, node_classes: Optional[dict] = None, extra_data: Optional[dict] = None):
        self.prompt = dict(prompt)
        self.extra_data = extra_data or {}
        self._node_classes = node_classes
        self.cache: dict[str, _CacheEntry] = {}
        self.executed: list[dict] = []
        self.scope_allowed: Optional[set[str]] = None
        self.ui_outputs: dict[str, Any] = {}
        self._golden_futures: set[asyncio.Future] = set()
        try:
            self._golden_task_baseline = set(asyncio.all_tasks())
            self._golden_task_baseline_ready = True
        except RuntimeError:
            self._golden_task_baseline = set()
            self._golden_task_baseline_ready = False
        self._golden_tasks: set[asyncio.Task] = set()
        self.sampling_diagnostics: Optional[GoldenSamplingDiagnostics] = None

    def _observe_tasks(self) -> None:
        """Record tasks not present when this runner was constructed."""
        try:
            tasks = set(asyncio.all_tasks())
        except RuntimeError:
            return
        tasks.discard(asyncio.current_task())
        if not self._golden_task_baseline_ready:
            self._golden_task_baseline = set(tasks)
            self._golden_task_baseline_ready = True
            return
        self._golden_tasks.update(tasks - self._golden_task_baseline)

    # -- class resolution ----------------------------------------------------

    def _classes(self) -> dict:
        if self._node_classes is not None:
            return self._node_classes
        import nodes  # upstream ComfyUI module (allowed import)

        return nodes.NODE_CLASS_MAPPINGS

    # -- seeding ---------------------------------------------------------------

    def seed(self, node_id: str, outputs: Any, ui: Any = None) -> None:
        if node_id not in self.prompt:
            raise RuntimeError(f"seed_unknown_node:{node_id}")
        self.cache[node_id] = _CacheEntry(outputs=outputs, ui=ui)

    # -- scope guard -----------------------------------------------------------

    def begin_scope(self, allowed_stage_classes: Optional[set[str]]) -> None:
        self.scope_allowed = set(allowed_stage_classes) if allowed_stage_classes else set()

    def end_scope(self) -> None:
        self.scope_allowed = None

    def executed_summary(self) -> list:
        return [(item["node_id"], item["class_type"], item["stage_class"]) for item in self.executed]

    # -- input assembly (upstream get_input_data semantics) ---------------------

    @staticmethod
    def _input_info(class_def: Any, input_name: str, valid_inputs: dict):
        for category in ("required", "optional", "hidden"):
            section = valid_inputs.get(category)
            if section and input_name in section:
                info = section[input_name]
                input_info = info[1] if len(info) > 1 else {}
                return category, input_info if isinstance(input_info, dict) else {}
        return None, {}

    def _get_input_data(self, unique_id: str, class_def: Any) -> tuple[dict, dict]:
        inputs = self.prompt[unique_id]["inputs"]
        valid_inputs = class_def.INPUT_TYPES()
        out: dict[str, list] = {}
        missing: dict[str, bool] = {}
        for x, value in inputs.items():
            _, input_info = self._input_info(class_def, x, valid_inputs)
            if _is_link(value) and not (input_info or {}).get("rawLink", False):
                src, socket = value[0], value[1]
                entry = self.cache.get(src)
                if entry is None or entry.outputs is None or socket >= len(entry.outputs):
                    missing[x] = True
                    out[x] = (None,)
                    continue
                out[x] = entry.outputs[socket]
            else:
                out[x] = [value]
        hidden = valid_inputs.get("hidden") or {}
        for hname, htype in hidden.items():
            if htype == "PROMPT":
                out[hname] = [self.prompt]
            elif htype == "DYNPROMPT":
                out[hname] = [self.prompt]
            elif htype == "EXTRA_PNGINFO":
                out[hname] = [self.extra_data.get("extra_pnginfo")]
            elif htype == "UNIQUE_ID":
                out[hname] = [unique_id]
            elif htype in ("AUTH_TOKEN_COMFY_ORG", "API_KEY_COMFY_ORG"):
                out[hname] = [self.extra_data.get(str(htype).lower())]
        return out, missing

    # -- lazy dependency support -------------------------------------------------

    def _required_lazy_inputs(self, unique_id: str, obj: Any, input_data_all: dict) -> list[str]:
        checker = getattr(obj, "check_lazy_status", None)
        if checker is None:
            return []
        sliced = {k: (v[0] if len(v) > 0 else None) for k, v in input_data_all.items()}
        required = checker(**sliced)
        if required is None:
            return []
        names: list[str] = []
        for item in required:
            if isinstance(item, list):
                names.extend(item)
            else:
                names.append(item)
        return [n for n in names if isinstance(n, str)]

    # -- result merging (upstream merge_result_data/get_output_from_returns) -----

    @staticmethod
    def _v3_node_output(r: Any) -> Any:
        """Return *r* when it is an upstream V3 NodeOutput, else None.

        Mirrors upstream ``execution.get_output_from_returns`` by testing
        against ``comfy_api.internal._NodeOutputInternal``.  Fails closed when
        the upstream marker class cannot be imported — a V3 node result must
        never be silently mis-normalized.
        """
        try:
            from comfy_api.internal import _NodeOutputInternal  # upstream ComfyUI module

            return r if isinstance(r, _NodeOutputInternal) else None
        except Exception as exc:
            raise RuntimeError(f"v3_node_output_class_unavailable:{type(exc).__name__}") from exc

    @staticmethod
    def _merge_results(results: list, class_def: Any) -> list:
        output = []
        output_is_list = [False] * len(results[0])
        if hasattr(class_def, "OUTPUT_IS_LIST"):
            output_is_list = class_def.OUTPUT_IS_LIST
        for i, is_list in zip(range(len(results[0])), output_is_list):
            if is_list:
                value = []
                for o in results:
                    value.extend(o[i])
                output.append(value)
            else:
                output.append([o[i] for o in results])
        return output

    def _outputs_from_returns(self, return_values: list, class_def: Any) -> tuple[list, dict, bool]:
        results = []
        uis = []
        has_subgraph = False
        expansions: list = []
        for r in return_values:
            v3_output = self._v3_node_output(r)
            if v3_output is not None:
                # Narrow frozen-workflow V3 normalization (e.g. node 88
                # EmptySD3LatentImage): consume .result plus optional .ui only.
                # This frozen node never exercises ExecutionBlocker or subgraph
                # expansion, so both fail closed instead of being emulated.
                if getattr(v3_output, "block_execution", None) is not None:
                    raise RuntimeError("v3_node_block_execution_unsupported")
                if getattr(v3_output, "expand", None) is not None:
                    raise RuntimeError("v3_node_expand_unsupported")
                ui = getattr(v3_output, "ui", None)
                if ui is not None:
                    if not isinstance(ui, dict):
                        as_dict = getattr(ui, "as_dict", None)
                        if not callable(as_dict):
                            raise RuntimeError("v3_node_ui_not_convertible")
                        ui = as_dict()
                    uis.append(ui)
                # Use the .result property (never len(NodeOutput)); it is the
                # positional-args tuple, or None when the node returned nothing.
                result = v3_output.result
                if result is not None:
                    results.append(result)
                continue
            if isinstance(r, dict):
                if "ui" in r:
                    uis.append(r["ui"])
                if "expand" in r:
                    has_subgraph = True
                    expansions.append((r["expand"], r.get("result")))
                elif "result" in r:
                    results.append(r["result"])
            else:
                results.append(r)
        if has_subgraph:
            output = []
            for new_graph, node_outputs in expansions:
                if new_graph is None:
                    output.append(node_outputs)
                else:
                    resolved = self._register_subgraph(new_graph, node_outputs)
                    output.append(resolved)
            return output, self._merged_ui(uis), has_subgraph
        output = self._merge_results(results, class_def) if results else []
        return output, self._merged_ui(uis), False

    @staticmethod
    def _merged_ui(uis: list) -> dict:
        if not uis:
            return {}
        merged: dict = {}
        for ui in uis:
            for key, values in (ui or {}).items():
                merged.setdefault(key, []).extend(values)
        return merged

    def _register_subgraph(self, new_graph: dict, node_outputs: Any) -> Any:
        """Register expanded subgraph nodes and resolve output links against
        the cache immediately (serially — nothing is deferred)."""
        for node_id, node_info in (new_graph or {}).items():
            self.prompt[node_id] = node_info
        if _is_link(node_outputs):
            src, socket = node_outputs[0], node_outputs[1]
            entry = self.cache.get(src)
            if entry is None or socket >= len(entry.outputs):
                raise RuntimeError(f"subgraph_link_unresolved:{src}:{socket}")
            return entry.outputs[socket]
        return node_outputs

    # -- single-node execution -----------------------------------------------------

    async def _execute_one(self, unique_id: str, _depth: int = 0) -> None:
        self._observe_tasks()
        if unique_id in self.cache:
            return
        if unique_id not in self.prompt:
            raise RuntimeError(f"node_not_found:{unique_id}")
        info = self.prompt[unique_id]
        class_type = info["class_type"]
        classes = self._classes()
        if class_type not in classes:
            raise RuntimeError(f"class_not_registered:{class_type}")
        class_def = classes[class_type]
        stage_class = classify_node(class_type)
        if stage_class != "prepare":
            if self.scope_allowed is None or stage_class not in self.scope_allowed:
                raise RuntimeError(
                    f"heavy_node_outside_assigned_stage:{unique_id}:{class_type}:{stage_class}"
                )

        obj = class_def()

        # Lazy evaluation: resolve missing lazy dependencies serially, then retry.
        for _attempt in range(32):
            input_data_all, _missing = self._get_input_data(unique_id, class_def)
            required = self._required_lazy_inputs(unique_id, obj, input_data_all)
            pending_links = [
                name
                for name in required
                if name in _missing
                and name in info["inputs"]
                and _is_link(info["inputs"][name])
            ]
            if not pending_links:
                break
            if _depth > 32:
                raise RuntimeError(f"lazy_dependency_depth_exceeded:{unique_id}")
            for name in pending_links:
                await self._ensure(info["inputs"][name][0], _depth + 1)
        else:
            raise RuntimeError(f"lazy_status_never_satisfied:{unique_id}")

        # INPUT_IS_LIST: call once with full lists; otherwise slice per index.
        input_is_list = getattr(obj, "INPUT_IS_LIST", False)
        results: list = []
        if input_is_list:
            results.append(await self._call_node(unique_id, obj, input_data_all))
        elif len(input_data_all) == 0:
            results.append(await self._call_node(unique_id, obj, {}))
        else:
            max_len = max(len(v) for v in input_data_all.values())

            def slice_dict(d: dict, i: int) -> dict:
                return {k: v[i if len(v) > i else -1] for k, v in d.items()}

            for i in range(max_len):
                results.append(await self._call_node(unique_id, obj, slice_dict(input_data_all, i)))

        # Resolve any async/task results IMMEDIATELY before advancing.
        resolved = []
        for r in results:
            if isinstance(r, list):
                resolved.append([await self._resolve(x) for x in r])
            else:
                resolved.append(await self._resolve(r))

        output, ui, _has_subgraph = self._outputs_from_returns(resolved, class_def)
        if ui:
            self.ui_outputs[unique_id] = ui
        self.cache[unique_id] = _CacheEntry(outputs=output, ui=ui)
        self.executed.append(
            {"node_id": unique_id, "class_type": class_type, "stage_class": stage_class}
        )
        self._observe_tasks()

    async def _resolve(self, value: Any) -> Any:
        self._observe_tasks()
        if inspect.iscoroutine(value):
            result = await value
            self._observe_tasks()
            return result
        if asyncio.isfuture(value):
            self._golden_futures.add(value)
            try:
                result = await asyncio.shield(value)
                self._observe_tasks()
                return result
            finally:
                self._golden_futures.discard(value)
        return value

    def assert_quiescent(self) -> None:
        self._observe_tasks()
        pending = [f for f in self._golden_futures if not f.done()]
        if pending:
            raise RuntimeError(f"golden_future_pending:{len(pending)}")
        pending_tasks = [task for task in self._golden_tasks if not task.done()]
        if pending_tasks:
            raise RuntimeError(f"golden_task_pending:{len(pending_tasks)}")

    async def _call_node(self, unique_id: str, obj: Any, inputs: dict) -> Any:
        func = getattr(obj, obj.FUNCTION)
        diagnostics = self.sampling_diagnostics
        if (
            diagnostics is not None
            and unique_id == diagnostics.sampler_id
            and str(self.prompt[unique_id].get("class_type")) == diagnostics.sampler_class
        ):
            inputs = diagnostics.wrap_sampler_inputs(inputs)
        if inspect.iscoroutinefunction(func):
            # Await inline: a task is never left pending across nodes.
            return await func(**inputs)
        result = func(**inputs)
        return await self._resolve(result)

    # -- closure execution ------------------------------------------------------

    async def _ensure(self, node_id: str, _depth: int = 0) -> None:
        if node_id in self.cache:
            return
        if node_id not in self.prompt:
            raise RuntimeError(f"node_not_found:{node_id}")
        inputs = self.prompt[node_id]["inputs"]
        class_def = self._classes()[self.prompt[node_id]["class_type"]]
        for name, value in inputs.items():
            if not _is_link(value):
                continue
            _, input_info = self._input_info(class_def, name, class_def.INPUT_TYPES())
            if (input_info or {}).get("lazy", False):
                continue  # pulled on demand by check_lazy_status
            await self._ensure(value[0], _depth + 1)
        await self._execute_one(node_id, _depth)

    async def run_closure(self, target_id: str, *, include_target: bool) -> list:
        """Execute the dependency closure of *target_id*, one node at a time.
        With ``include_target=False`` the target itself is NOT executed
        (used to stop right before a heavy node)."""
        if target_id not in self.prompt:
            raise RuntimeError(f"node_not_found:{target_id}")

        async def visit(nid: str, depth: int) -> None:
            if nid in self.cache:
                return
            if nid == target_id and not include_target:
                return
            await self._ensure(nid, depth)

        inputs = self.prompt[target_id]["inputs"]
        class_def = self._classes()[self.prompt[target_id]["class_type"]]
        for name, value in inputs.items():
            if not _is_link(value):
                continue
            _, input_info = self._input_info(class_def, name, class_def.INPUT_TYPES())
            if (input_info or {}).get("lazy", False):
                continue
            await self._ensure(value[0])
        if include_target:
            await self._execute_one(target_id)
        return self.executed_summary()


def _sampler_bound_patcher(session: GoldenSession) -> Any:
    """Return the model object that the sampler will actually receive.

    Preparatory model-wrapper nodes may clone the seeded patcher.  The clone is
    retained in the runner cache under the source node, so applying the
    attention override only to ``session.patcher`` would miss the sampler's
    active model.  Unresolved or non-link model inputs retain the direct-model
    behavior used by clone-free workflows.
    """
    fallback = session.patcher
    runner = session.runner
    node_map = session.node_map
    if runner is None or node_map is None:
        return fallback
    prompt = getattr(runner, "prompt", None) or getattr(session.request, "prompt", {})
    sampler_info = prompt.get(node_map.sampler_id, {})
    model_link = (sampler_info.get("inputs") or {}).get("model")
    if not _is_link(model_link):
        return fallback
    entry = getattr(runner, "cache", {}).get(model_link[0])
    outputs = getattr(entry, "outputs", None)
    if not isinstance(outputs, (list, tuple)):
        return fallback
    socket = model_link[1]
    if socket < 0 or socket >= len(outputs):
        return fallback
    values = outputs[socket]
    if not isinstance(values, (list, tuple)) or len(values) != 1:
        return fallback
    return values[0] if values[0] is not None else fallback


# ── Canonical workflow resolution (pure) ──────────────────────────────────


def resolve_golden_node_map(prompt: dict, *, contract: Optional[GoldenWorkflowContract] = None) -> GoldenNodeMap:
    """Locate the canonical nodes in the workflow prompt.  Pure; fails closed.

    The workflow CLIPLoader node is validated against the contract's
    :class:`ClipLoadSpec` (declared ``clip_name`` and ``type``).  Only the
    single-checkpoint CLIPLoader shape is supported for workflow discovery;
    multi-checkpoint specs fail closed here (no multi-loader discovery).
    """
    contract = contract or GoldenWorkflowContract()
    spec = contract.clip_spec or CANONICAL_CLIP_SPEC
    if len(spec.checkpoint_names) != 1:
        raise RuntimeError("golden_clip_workflow_single_checkpoint_required")
    expected_clip_name = spec.checkpoint_names[0]
    if contract.clip_name != expected_clip_name or contract.clip_type != spec.clip_type:
        raise RuntimeError("golden_contract_clip_spec_mismatch")
    matches = {
        "clip_loader": [],
        "clip_encode": [],
        "unet_loader": [],
        "vae_loader": [],
        "sampler": [],
        "vae_decode": [],
    }
    for node_id, info in prompt.items():
        class_type = str(info.get("class_type", ""))
        inputs = info.get("inputs") or {}
        if class_type == "CLIPLoader":
            if inputs.get("clip_name") == expected_clip_name and str(inputs.get("type")) == spec.clip_type:
                matches["clip_loader"].append(node_id)
        elif class_type == "UNETLoader":
            if inputs.get("unet_name") == contract.unet_name:
                matches["unet_loader"].append(node_id)
        elif class_type == "VAELoader":
            if inputs.get("vae_name") == contract.vae_name:
                matches["vae_loader"].append(node_id)
        elif class_type == "CLIPTextEncode":
            matches["clip_encode"].append(node_id)
        elif class_type == contract.sampler_class_type:
            matches["sampler"].append(node_id)
        elif class_type == "VAEDecode":
            matches["vae_decode"].append(node_id)
    duplicates = {
        name: ids for name, ids in matches.items() if len(ids) > 1
    }
    if duplicates:
        raise RuntimeError(f"canonical_nodes_duplicate:{duplicates}")
    resolved = {name: ids[0] if ids else None for name, ids in matches.items()}
    missing = [
        name
        for name, value in resolved.items()
        if value is None
    ]
    if missing:
        raise RuntimeError(f"canonical_nodes_missing:{','.join(missing)}")
    return GoldenNodeMap(
        clip_loader_id=resolved["clip_loader"],
        clip_encode_id=resolved["clip_encode"],
        unet_loader_id=resolved["unet_loader"],
        vae_loader_id=resolved["vae_loader"],
        sampler_id=resolved["sampler"],
        vae_decode_id=resolved["vae_decode"],
    )


# ── Stage implementations ─────────────────────────────────────────────────


_GOLDEN_SAMPLING_PROFILE_RECORD_MAX_BYTES = 512 * 1024


def _record_golden_sampling_profile(
    recorder: GoldenTelemetryRecorder,
    artifact: Any,
    *,
    level: str,
    source: str,
    schema_version: int = 1,
) -> None:
    """Copy one bounded, JSON-safe profile artifact into Golden telemetry."""
    try:
        payload = json.loads(json.dumps(artifact, default=str))
        encoded_size = len(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
        if encoded_size > _GOLDEN_SAMPLING_PROFILE_RECORD_MAX_BYTES:
            payload = {
                "schema_version": int(schema_version),
                "level": str(level),
                "status": "record_bounded",
                "errors": [f"artifact_bytes_exceeded:{encoded_size}"],
            }
    except Exception as exc:
        payload = {
            "schema_version": int(schema_version),
            "level": str(level),
            "status": "record_serialize_failed",
            "errors": [f"artifact_serialize_failed:{type(exc).__name__}"],
        }
    recorder.event(
        "sampling_deep_profile",
        phase="diagnostics",
        metadata=payload,
        source=source,
    )


def validate_attention_backend_diagnostics(
    requested_backend: Optional[str], artifact: Mapping[str, Any] | None
) -> None:
    """Fail closed when optional dispatch evidence contradicts the request."""
    if not isinstance(artifact, Mapping):
        return
    # An omitted selector is the historical auto path.  There is no Golden
    # override to prove, so optional diagnostics must not reinterpret the
    # existing patcher's/KJNodes dispatch as a failed explicit arm.
    if requested_backend is None:
        return
    requested = normalize_attention_backend(requested_backend)
    observed = artifact.get("attention_backend")
    if not isinstance(observed, Mapping):
        return
    counts = observed.get("dispatch_counts")
    if not isinstance(counts, Mapping):
        return
    incompatible = {
        "pytorch": ("sage_override", "comfy_kitchen_int8_override"),
        "sage": ("pytorch_override", "comfy_kitchen_int8_override"),
        "comfy_kitchen": ("pytorch_override", "sage_override"),
    }[requested]
    if any(int(counts.get(key, 0) or 0) > 0 for key in incompatible):
        raise AttentionBackendValidationError(
            f"attention_backend_fallback_or_wrong_backend:{requested}"
        )
    if requested in {"sage", "comfy_kitchen"} and int(
        observed.get("pytorch_sdpa_calls", 0) or 0
    ) > 0:
        raise AttentionBackendValidationError(
            f"attention_backend_fallback_or_wrong_backend:{requested}"
        )


async def golden_restore(session: GoldenSession) -> dict:
    """Observe the adapter's already-completed REAL RESTORE handoff.

    This stage owns no restore work.  External boundary metadata is copied
    verbatim (with naming aliases only); no duration is made here.
    """
    rec = session.recorder
    rec.begin_stage("golden_restore")
    try:
        metadata = dict(getattr(session, "restore_metadata", {}) or {})
        if not getattr(session, "_restore_metadata_supplied", False):
            extra = getattr(getattr(session, "request", None), "extra_data", {}) or {}
            nested = extra.get("restore_timing") if isinstance(extra, dict) else None
            if isinstance(nested, dict):
                metadata = dict(nested)
            metadata = {
                **metadata,
                **{
                    str(key): value
                    for key, value in extra.items()
                    if "restore" in str(key).lower() or "resume" in str(key).lower()
                    or "method_entry" in str(key).lower()
                },
            }
        # Accept the names emitted by the installed Modal adapter as well as
        # the concise names used by thin test/adaptor boundaries.
        aliases = {
            "remote_python_resume_wall_unix_ns": "remote_python_resume_wall_ns",
            "restore_method_start_wall_ns": "actual_restore_start_wall_ns",
            "restore_method_end_wall_ns": "actual_restore_end_wall_ns",
            "restore_method_start_mono_ns": "actual_restore_start_mono_ns",
            "restore_method_end_mono_ns": "actual_restore_end_mono_ns",
            "restore_method_entry_wall_ns": "method_entry_wall_ns",
            "restore_method_entry_mono_ns": "method_entry_mono_ns",
        }
        for source, target in aliases.items():
            if target not in metadata and source in metadata:
                metadata[target] = metadata[source]
        if getattr(session, "_restore_metadata_supplied", False) and metadata:
            boundary_keys = {
                "remote_python_resume_mono_ns",
                "remote_python_resume_wall_ns",
                "actual_restore_start_mono_ns",
                "actual_restore_start_wall_ns",
                "actual_restore_end_mono_ns",
                "actual_restore_end_wall_ns",
                "method_entry_mono_ns",
                "method_entry_wall_ns",
            }
            present = boundary_keys.intersection(metadata)
            if not present:
                raise RuntimeError("restore_metadata_boundary_missing")
            for key in present:
                value = metadata[key]
                if isinstance(value, bool) or not isinstance(value, int):
                    raise RuntimeError(f"restore_metadata_boundary_invalid:{key}")
        rec.record_external_restore(metadata)
        if not torch.cuda.is_available():
            raise RuntimeError("cuda_unavailable")
        preload_workers = [
            t.name
            for t in threading.enumerate()
            if "preload" in t.name.lower() or t.name.startswith("golden-qd")
        ]
        if preload_workers:
            raise RuntimeError(f"restore_preload_workers_present:{preload_workers}")
        baseline = {
            "device": torch.cuda.get_device_name(torch.cuda.current_device()),
            "memory_allocated_bytes": int(torch.cuda.memory_allocated()),
            "thread_names": sorted(t.name for t in threading.enumerate()),
            "request_id": session.request.request_id,
            "observation_only": True,
            "external_restore_interval": metadata,
        }
        session.restore_baseline = baseline
        rec.end_stage(
            "golden_restore",
            ready=True,
            observation_only=True,
            external_restore_interval=metadata,
            device=str(baseline["device"]),
        )
        return baseline
    except BaseException as exc:
        rec.fail_stage("golden_restore", exc)
        raise


async def golden_request_setup(session: GoldenSession) -> GoldenNodeMap:
    """Validate the frozen request/contract, hash-verify the canonical
    workflow, resolve canonical node handles and model paths, and construct
    the serial runner."""
    rec = session.recorder
    rec.begin_stage("golden_request_setup")
    try:
        contract = session.contract
        actual_sha = canonical_workflow_sha256(session.request.prompt)
        workflow_hash_check_value = os.environ.get(
            "COMFYMODAL_V2_GOLDEN_WORKFLOW_HASH_CHECK", "1"
        ).strip().lower()
        workflow_hash_check_enabled = workflow_hash_check_value not in {
            "0", "false", "no", "off"
        }
        rec.event(
            "golden_workflow_hash_check",
            actual_sha256=actual_sha,
            expected_sha256=contract.workflow_sha256,
            attention_backend=session.request.attention_backend,
            enabled=workflow_hash_check_enabled,
            bypassed=not workflow_hash_check_enabled,
        )
        if not workflow_hash_check_enabled:
            raise RuntimeError(
                "workflow_hash_check_disabled:Golden workflow hash verification is required"
            )
        if actual_sha != contract.workflow_sha256:
            raise RuntimeError(f"workflow_sha_mismatch:{actual_sha}!={contract.workflow_sha256}")
        node_map = resolve_golden_node_map(session.request.prompt, contract=contract)
        session.node_map = node_map

        import folder_paths  # upstream ComfyUI module (allowed import)

        spec = contract.clip_spec or CANONICAL_CLIP_SPEC
        clip_paths = [
            folder_paths.get_full_path_or_raise(spec.folder, name)
            for name in spec.checkpoint_names
        ]
        session.clip_paths = clip_paths
        session.model_paths = {
            "clip": clip_paths[0],
            "unet": folder_paths.get_full_path_or_raise("diffusion_models", contract.unet_name),
            "vae": folder_paths.get_full_path_or_raise("vae", contract.vae_name),
        }
        session.runner = GoldenSerialRunner(
            session.request.prompt,
            node_classes=session.node_classes,
            extra_data=session.request.extra_data,
        )
        rec.end_stage(
            "golden_request_setup",
            ready=True,
            request_id=session.request.request_id,
            attention_backend=session.request.attention_backend,
            clip_residency=getattr(session, "clip_residency", "bf16"),
            run_identity=dict(getattr(session, "run_identity", {})),
            node_count=len(session.request.prompt),
            actual_workflow_sha256=actual_sha,
            expected_workflow_sha256=contract.workflow_sha256,
            workflow_hash_check_enabled=workflow_hash_check_enabled,
            workflow_hash_check_bypassed=not workflow_hash_check_enabled,
            clip_loader=node_map.clip_loader_id,
            sampler=node_map.sampler_id,
            clip_name=[n for n in spec.checkpoint_names],
            clip_type=spec.clip_type,
            clip_folder=spec.folder,
        )
        return node_map
    except BaseException as exc:
        rec.fail_stage("golden_request_setup", exc)
        raise


_CLIP_LOAD_TIMING_PHASES = (
    "source_open_read",
    "header_layout_parse",
    "qd_staging_allocation",
    "h2d_transport",
    "skeleton_patcher_construction",
    "storage_adoption",
    "owner_publish_handoff",
    "compute_ready_proof",
)


class _ClipTiming:
    """Small, JSON-safe host timing ledger owned by the CLIP stages.

    The ledger never synchronizes CUDA.  A phase may be ``unproven`` when an
    upstream helper exposes a duration but not an absolute boundary; that is
    preferable to manufacturing a boundary from a stage total.
    """

    def __init__(self, *, enabled: bool = True) -> None:
        self.enabled = bool(enabled)
        self.started_ns = time.perf_counter_ns() if self.enabled else None
        self.phases: list[dict[str, Any]] = []
        self.qwen_forwards: list[dict[str, Any]] = []
        self.qwen_hook_status = "UNPROVEN"

    @contextlib.contextmanager
    def span(self, name: str, *, boundary_kind: str = "host_observed", level: str = "parent"):
        if not self.enabled:
            yield
            return
        start = time.perf_counter_ns()
        try:
            yield
        finally:
            end = time.perf_counter_ns()
            self.phases.append({
                "name": str(name),
                "start_ns": start,
                "end_ns": end,
                "duration_ns": max(0, end - start),
                "boundary_kind": boundary_kind,
                "level": level,
            })

    def unproven(self, name: str, *, duration_ns: Optional[int] = None, detail: Any = None,
                 parent: Optional[str] = None) -> None:
        if not self.enabled:
            return
        self.phases.append({
            "name": str(name),
            "start_ns": None,
            "end_ns": None,
            "duration_ns": int(duration_ns) if duration_ns is not None else None,
            "boundary_kind": "unproven",
            "level": "nested" if parent else "parent",
            "parent_phase": parent,
            "detail": detail,
        })

    def finish(self) -> dict[str, Any]:
        if not self.enabled:
            return {"enabled": False}
        observed = [
            p for p in self.phases
            if p.get("level") == "parent" and p.get("start_ns") is not None
        ]
        observed.sort(key=lambda p: int(p["start_ns"]))
        overlap_ns = 0
        previous_end: Optional[int] = None
        union_ns = 0
        for phase in observed:
            start, end = int(phase["start_ns"]), int(phase["end_ns"])
            if previous_end is not None and start < previous_end:
                overlap_ns += min(previous_end, end) - start
            if previous_end is None or start >= previous_end:
                union_ns += end - start
            elif end > previous_end:
                union_ns += end - previous_end
            previous_end = max(previous_end or end, end)
        wall_ns = max(0, time.perf_counter_ns() - int(self.started_ns))
        return {
            "schema": "golden_clip_timing_v1",
            "clock": "perf_counter_ns",
            "phases": list(self.phases),
            "required_phases": list(_CLIP_LOAD_TIMING_PHASES),
            "parent_reconciliation": {
                "wall_ns": wall_ns,
                "observed_union_ns": union_ns,
                "residual_ns": wall_ns - union_ns,
                "overlap_ns": overlap_ns,
                "non_additive": bool(overlap_ns),
            },
        }


def _clip_page_fault_snapshot() -> dict[str, Any]:
    """Compatibility adapter for the canonical raw process-counter reader."""
    raw = _process_page_faults()
    return {
        "available": raw.get("available", False),
        "source": raw.get("source"),
        "minor_faults": raw.get("minor_faults"),
        "major_faults": raw.get("major_faults"),
    }


def _clip_page_fault_delta(
    start: Mapping[str, Any], end: Mapping[str, Any]
) -> dict[str, Any]:
    """Compatibility adapter retaining the historical CLIP summary keys."""
    delta = page_fault_delta(start, end)
    return {
        "available": delta["available"],
        "source": delta["source"],
        "minor_fault_delta": delta["minor_delta"],
        "major_fault_delta": delta["major_delta"],
    }


def _clip_page_faults_summary(
    stage: str, start: Mapping[str, Any], end: Mapping[str, Any]
) -> dict[str, Any]:
    """Build the JSON-safe event/end-stage shape for one CLIP interval."""
    delta = _clip_page_fault_delta(start, end)
    return {
        "stage": str(stage),
        "start": {
            "minor_faults": start.get("minor_faults"),
            "major_faults": start.get("major_faults"),
        },
        "end": {
            "minor_faults": end.get("minor_faults"),
            "major_faults": end.get("major_faults"),
        },
        "start_counters": {
            "minor_faults": start.get("minor_faults"),
            "major_faults": start.get("major_faults"),
        },
        "end_counters": {
            "minor_faults": end.get("minor_faults"),
            "major_faults": end.get("major_faults"),
        },
        **delta,
        "diagnostic_only": True,
    }


@contextlib.contextmanager
def _clip_qwen_forward_hooks(
    scope: Any,
    timing: _ClipTiming,
    snapshot: Callable[[], dict[str, Any]],
    recorder: Optional[GoldenTelemetryRecorder] = None,
    conversion_observer: Optional[Callable[[str, int], None]] = None,
    *,
    enabled: bool = True,
):
    """Observe selected-scope forwards, restoring hooks in all outcomes.

    Hooks return ``None`` and never synchronize or alter arguments/results.
    Every callback is best effort: an instrumentation failure is retained as
    ``UNPROVEN`` data and cannot replace a real CLIP result or exception.
    """
    if not enabled:
        yield
        return
    forwards: list[dict[str, Any]] = []
    handles: list[Any] = []
    starts: list[dict[str, Any]] = []
    timing.qwen_forwards = forwards
    timing.qwen_hook_status = "UNPROVEN"

    def safe_snapshot() -> dict[str, Any]:
        try:
            value = snapshot()
            return value if isinstance(value, dict) else {
                "status": "unproven", "reason": "snapshot_invalid_shape"
            }
        except Exception as exc:
            return {"status": "unproven", "reason": f"snapshot_failed:{type(exc).__name__}"}

    def safe_faults() -> dict[str, Any]:
        try:
            return _clip_page_fault_snapshot()
        except Exception as exc:
            return {
                "available": False,
                "source": None,
                "minor_faults": None,
                "major_faults": None,
                "reason": f"page_fault_snapshot_failed:{type(exc).__name__}",
            }

    def pre_hook(*hook_args: Any, **hook_kwargs: Any) -> None:
        # A stack handles nested forwards without making assumptions about the
        # selected module's implementation.
        try:
            module_inputs = hook_args[1] if len(hook_args) > 1 else ()
            if len(hook_args) > 2 and isinstance(hook_args[2], Mapping):
                module_kwargs = hook_args[2]
                boundary_input = (module_inputs, module_kwargs)
            else:
                boundary_input = module_inputs
            index = len(forwards)
            input_facts = _clip_forward_tensor_facts(boundary_input)
            starts.append({
                "start_ns": time.perf_counter_ns(),
                "snapshot": safe_snapshot(),
                "faults": safe_faults(),
                "input_facts": input_facts,
                "input_facts_truncated": bool(getattr(input_facts, "truncated", False)),
            })
            if callable(conversion_observer):
                conversion_observer("start", index)
        except Exception as exc:
            timing.unproven(
                "clip_qwen_transformer_forward",
                detail={"status": "UNPROVEN", "reason": f"pre_hook_failed:{type(exc).__name__}"},
            )

    def post_hook(*hook_args: Any, **hook_kwargs: Any) -> None:
        try:
            end_ns = time.perf_counter_ns()
            start = starts.pop() if starts else {
                "start_ns": end_ns,
                "snapshot": {"status": "unproven", "reason": "pre_hook_not_observed"},
                "faults": safe_faults(),
            }
            after_snapshot = safe_snapshot()
            after_faults = safe_faults()
            index = len(forwards)
            module_output = hook_args[-1] if hook_args else None
            output_facts = _clip_forward_tensor_facts(module_output)
            fault_summary = _clip_page_faults_summary(
                "clip_qwen_transformer_forward", start["faults"], after_faults
            )
            record = {
                "index": index,
                "phase": "first_qwen_compute" if index == 0 else "later_forward_work",
                "start_ns": int(start["start_ns"]),
                "end_ns": int(end_ns),
                "duration_ns": max(0, int(end_ns) - int(start["start_ns"])),
                "boundary_kind": "host_observed",
                "before_snapshot": start["snapshot"],
                "after_snapshot": after_snapshot,
                "page_faults": fault_summary,
                "input_facts": list(start.get("input_facts") or []),
                "input_facts_truncated": bool(start.get("input_facts_truncated")),
                "output_facts": output_facts,
                "output_facts_truncated": bool(getattr(output_facts, "truncated", False)),
            }
            forwards.append(record)
            if callable(conversion_observer):
                conversion_observer("end", index)
            timing.phases.append({
                "name": "clip_qwen_transformer_forward",
                "start_ns": record["start_ns"],
                "end_ns": record["end_ns"],
                "duration_ns": record["duration_ns"],
                "boundary_kind": "host_observed_nested",
                "level": "nested",
                "detail": {
                    "index": index,
                    "phase": record["phase"],
                    "page_faults": fault_summary,
                },
            })
            timing.qwen_hook_status = "host_observed"
            if recorder is not None:
                try:
                    recorder.event("clip_qwen_transformer_forward", **record)
                    recorder.event("clip_page_faults", **fault_summary)
                except Exception:
                    pass
        except Exception as exc:
            timing.unproven(
                "clip_qwen_transformer_forward",
                detail={"status": "UNPROVEN", "reason": f"post_hook_failed:{type(exc).__name__}"},
            )

    try:
        pre_register = getattr(scope, "register_forward_pre_hook", None)
        post_register = getattr(scope, "register_forward_hook", None)
        if not callable(pre_register) or not callable(post_register):
            timing.unproven(
                "clip_qwen_transformer_forward",
                detail={"status": "UNPROVEN", "reason": "scope_hooks_unavailable"},
            )
            yield
            return
        try:
            try:
                handles.append(pre_register(pre_hook, with_kwargs=True))
            except TypeError:
                handles.append(pre_register(pre_hook))
            handles.append(post_register(post_hook))
            timing.qwen_hook_status = "installed"
        except Exception as exc:
            timing.unproven(
                "clip_qwen_transformer_forward",
                detail={"status": "UNPROVEN", "reason": f"hook_install_failed:{type(exc).__name__}"},
            )
            for handle in reversed(handles):
                try:
                    handle.remove()
                except Exception:
                    pass
            handles.clear()
        yield
    finally:
        for handle in reversed(handles):
            try:
                handle.remove()
            except Exception:
                pass
        if not forwards and timing.qwen_hook_status in {"installed", "host_observed"}:
            timing.unproven(
                "clip_qwen_transformer_forward",
                detail={"status": "UNPROVEN", "reason": "no_scope_forward_observed"},
            )


def _clip_scope_snapshot(scope: Any, patcher: Any = None) -> dict[str, Any]:
    """Capture only scalar device/dtype/storage identity for a compute scope."""
    try:
        tensors = list(scope.named_parameters()) + list(scope.named_buffers())
        if not tensors:
            return {"status": "unproven", "reason": "scope_has_no_tensors"}
        entries = []
        for name, tensor in tensors:
            storage = tensor.untyped_storage()
            entries.append({
                "name": str(name),
                "device": str(tensor.device),
                "dtype": str(tensor.dtype),
                "data_ptr": int(tensor.data_ptr()),
                "storage_ptr": int(storage.data_ptr()),
                "storage_bytes": int(storage.nbytes()),
                "shape": [int(x) for x in tensor.shape],
            })
        patcher = patcher if patcher is not None else getattr(scope, "patcher", None)
        patcher_state = {}
        if patcher is not None:
            for key in ("is_dynamic", "load_device", "offload_device", "model_size"):
                try:
                    value = getattr(patcher, key)
                    patcher_state[key] = str(value) if key != "is_dynamic" else bool(value)
                except Exception:
                    patcher_state[key] = None
        return {
            "status": "proven",
            "tensor_count": len(entries),
            "entries": entries,
            "patcher": patcher_state,
        }
    except Exception as exc:
        return {"status": "unproven", "reason": f"{type(exc).__name__}"}


def _clip_compute_identity(scope: Any, adoption: Mapping[str, Any], patcher: Any = None) -> dict[str, Any]:
    snap = _clip_scope_snapshot(scope, patcher)
    entries = snap.get("entries", []) if snap.get("status") == "proven" else []
    devices = sorted({str(item["device"]) for item in entries})
    dtypes = sorted({str(item["dtype"]) for item in entries})
    storage_proven = bool(
        snap.get("status") == "proven"
        and int(adoption.get("matched_count", 0)) == int(adoption.get("same_storage_count", 0))
        and int(adoption.get("copied_storage_count", 1)) == 0
    )
    ready = bool(storage_proven and len(devices) == 1 and len(dtypes) == 1)
    return {
        # This is the actual adopted selected-scope storage snapshot.  It is
        # deliberately separate from compute_dtype, which is unavailable
        # until a real Qwen forward boundary is observed.
        "resident_dtype": dtypes[0] if len(dtypes) == 1 else None,
        "compute_scope_device": devices[0] if len(devices) == 1 else devices,
        "compute_scope_dtype": dtypes[0] if len(dtypes) == 1 else dtypes,
        "compute_scope_storage_proven": storage_proven,
        "compute_ready": ready,
        "compute_scope_tensor_count": len(entries),
        "compute_scope_snapshot": snap,
    }


def _clip_materialization_status(before: Mapping[str, Any], after: Mapping[str, Any]) -> str:
    if before.get("status") != "proven" or after.get("status") != "proven":
        return "UNPROVEN"
    before_entries = before.get("entries") or []
    after_entries = after.get("entries") or []
    if len(before_entries) != len(after_entries):
        return "YES"
    before_map = {item.get("name"): item for item in before_entries}
    for item in after_entries:
        old = before_map.get(item.get("name"))
        if old is None:
            return "YES"
        if any(old.get(key) != item.get(key) for key in ("device", "dtype", "data_ptr", "storage_ptr")):
            return "YES"
    return "NO"


class _ClipTensorFacts(list):
    """JSON-compatible bounded facts with explicit truncation metadata."""

    truncated: bool = False


def _clip_forward_tensor_facts(value: Any, *, limit: int = 32) -> _ClipTensorFacts:
    """Collect bounded dtype/device facts and signal omitted tensors."""
    facts = _ClipTensorFacts()

    def visit(item: Any) -> None:
        if len(facts) >= limit:
            facts.truncated = True
            return
        if isinstance(item, torch.Tensor):
            facts.append({
                "dtype": str(item.dtype),
                "device": str(item.device),
                "shape": [int(dim) for dim in item.shape],
            })
            return
        if isinstance(item, Mapping):
            for child in item.values():
                visit(child)
                if facts.truncated:
                    return
        elif isinstance(item, (tuple, list)):
            for child in item:
                visit(child)
                if facts.truncated:
                    return

    visit(value)
    return facts


def _clip_compute_dtype_from_forward_evidence(
    forwards: Any, conversion: Optional[Mapping[str, Any]] = None,
) -> tuple[Optional[str], dict[str, Any]]:
    """Derive compute dtype only from an observed selected-scope forward.

    Residency is intentionally not an input.  A dtype is proven when the
    actual forward boundary has a single dtype across its observed inputs and
    outputs, or when its observed output agrees with a real cast destination.
    """
    evidence: dict[str, Any] = {
        "status": "UNPROVEN",
        "forward_count": 0,
        "input_dtypes": [],
        "output_dtypes": [],
        "cast_destination_dtypes": [],
    }
    if not isinstance(forwards, list) or not forwards:
        return None, evidence
    is_compute_dtype = lambda value: str(value).startswith((
        "torch.float", "torch.bfloat", "torch.half"
    ))
    input_dtypes = sorted({
        str(fact.get("dtype"))
        for forward in forwards
        for fact in (forward.get("input_facts") or [])
        if isinstance(fact, Mapping) and fact.get("dtype") and is_compute_dtype(fact.get("dtype"))
    })
    observed_output_dtypes = sorted({
        str(fact.get("dtype"))
        for forward in forwards
        for fact in (forward.get("output_facts") or [])
        if isinstance(fact, Mapping) and fact.get("dtype")
    })
    output_dtypes = sorted({
        str(fact.get("dtype"))
        for forward in forwards
        for fact in (forward.get("output_facts") or [])
        if isinstance(fact, Mapping) and fact.get("dtype") and is_compute_dtype(fact.get("dtype"))
    })
    cast_dtypes = sorted({
        str(item.get("destination_dtype"))
        for item in (conversion or {}).get("conversions", [])
        if isinstance(item, Mapping) and item.get("destination_dtype")
    })
    def facts_truncated(forward: Mapping[str, Any], name: str) -> bool:
        facts = forward.get(name)
        return bool(forward.get(f"{name}_truncated")) or bool(
            getattr(facts, "truncated", False)
        )

    evidence.update({
        "status": "OBSERVED",
        "forward_count": len(forwards),
        "input_dtypes": input_dtypes,
        "output_dtypes": output_dtypes,
        "observed_output_dtypes": observed_output_dtypes,
        "cast_destination_dtypes": cast_dtypes,
        "input_facts_truncated": any(
            facts_truncated(forward, "input_facts") for forward in forwards
            if isinstance(forward, Mapping)
        ),
        "output_facts_truncated": any(
            facts_truncated(forward, "output_facts") for forward in forwards
            if isinstance(forward, Mapping)
        ),
    })
    if evidence["input_facts_truncated"] or evidence["output_facts_truncated"]:
        evidence["reason"] = "bounded_forward_facts_truncated"
        return None, evidence
    # A mixed output is not a compute-dtype proof.  In particular, do not let
    # one matching output hide another output that was observed at a different
    # dtype.  The same conservative rule applies to mixed inputs.
    if len(input_dtypes) != 1 or len(output_dtypes) != 1 or len(observed_output_dtypes) != 1:
        evidence["reason"] = "mixed_or_missing_forward_boundary_dtype"
        return None, evidence
    boundary_dtypes = sorted(set(input_dtypes) | set(output_dtypes))
    if len(boundary_dtypes) == 1:
        evidence["status"] = "PROVEN"
        return boundary_dtypes[0], evidence
    # A cast destination is relevant only when the selected Qwen boundary also
    # produced an output of that dtype; it may not promote residency into a
    # compute claim by itself.
    matching = sorted(set(output_dtypes) & set(cast_dtypes))
    if len(cast_dtypes) == 1 and len(matching) == 1:
        evidence["status"] = "PROVEN"
        evidence["basis"] = "observed_output_and_cast_destination"
        return matching[0], evidence
    return None, evidence


_CLIP_CAST_ONCE_PHASES = (
    "identity", "transform", "constructor_preflight", "bind", "adoption",
    "proof", "source_drop", "retirement", "ready",
)
_CLIP_CAST_ONCE_FATAL_PHASES = frozenset({
    "bind", "adoption", "proof", "source_drop", "retirement", "ready",
})


def _clip_cast_once_failure_classification(phase: str) -> tuple[bool, str]:
    """Classify from the explicit lifecycle phase, never exception text."""
    phase = str(phase)
    if phase in _CLIP_CAST_ONCE_FATAL_PHASES:
        return True, "fatal_bind_or_proof"
    return False, {
        "identity": "identity_failure",
        "transform": "transform_failure",
        "constructor_preflight": "constructor_preflight_failure",
    }.get(phase, "cast_once_load_failure")


@contextlib.contextmanager
def _clip_forward_wrappers(
    clip: Any,
    timing: _ClipTiming,
    snapshot: Callable[[], dict[str, Any]],
    *,
    enabled: bool = True,
):
    """Temporarily classify CLIP tokenization and encode, then restore exactly."""
    if not enabled:
        yield
        return
    names = (
        ("tokenize", "clip_tokenization_input_prep"),
        ("encode_from_tokens_scheduled", "clip_qwen_transformer_encode"),
    )
    originals: list[tuple[str, bool, Any]] = []
    installed: list[str] = []
    snapshots = getattr(timing, "snapshots", {})
    timing.snapshots = snapshots
    try:
        for attr, phase in names:
            original = getattr(clip, attr)
            had_local = attr in getattr(clip, "__dict__", {})
            local_dict = getattr(clip, "__dict__", {})
            originals.append((attr, had_local, local_dict.get(attr) if had_local else None))

            def wrapped(*args: Any, _original=original, _phase=phase, **kwargs: Any) -> Any:
                with timing.span(
                    _phase,
                    boundary_kind="host_observed_nested",
                    level="nested",
                ):
                    result = _original(*args, **kwargs)
                key = "after_tokenization" if _phase == "clip_tokenization_input_prep" else "after_encode"
                try:
                    snapshots[key] = snapshot()
                except Exception:
                    snapshots[key] = {"status": "unproven", "reason": "snapshot_failed"}
                return result

            try:
                setattr(clip, attr, wrapped)
            except Exception as exc:
                timing.unproven(
                    phase,
                    detail=f"wrapper_install_failed:{type(exc).__name__}",
                )
                originals.pop()
                continue
            installed.append(attr)
        yield
    finally:
        for attr, had_local, old in reversed(originals):
            try:
                if had_local:
                    setattr(clip, attr, old)
                else:
                    delattr(clip, attr)
            except Exception:
                # Restoration is diagnostic-only; never replace a real CLIP
                # result or exception with an instrumentation exception.
                pass


def _ra9h_clip_module() -> Any:
    """Load only the RA9G ownership seam, and only when requested."""
    return importlib.import_module("comfymodal_runtime.clip_fp32_cast_once")


def _ra9h_manifest_for_transport(transport: Mapping[str, Any], file_index: int) -> dict[str, Any]:
    """Build tensor facts from the already-parsed transport view.

    This is not source identity generation.  Identity fields must come from
    the authoritative request/model manifest and are added separately.
    """
    state_dict = transport.get("sd")
    if not isinstance(state_dict, Mapping):
        raise RuntimeError(f"clip_fp32_manifest_state_dict_missing:{file_index}")
    model_keys = [str(key) for key in state_dict if str(key) not in {"spiece_model", "tekken_model", "tokenizer_json"}]
    if not model_keys:
        raise RuntimeError(f"clip_fp32_manifest_empty:{file_index}")
    dtypes = {str(getattr(state_dict[key], "dtype", "")) for key in state_dict if str(key) in model_keys}
    if len(dtypes) != 1:
        raise RuntimeError(f"clip_fp32_manifest_non_uniform_dtype:{file_index}")
    return {
        "file_index": int(file_index),
        "dtype": next(iter(dtypes)),
        "key_set": model_keys,
        "key_shapes": {
            key: [int(dim) for dim in getattr(state_dict[key], "shape", ())]
            for key in model_keys
        },
    }


def _ra9h_authoritative_identity(session: GoldenSession) -> dict[str, Any]:
    """Read identity supplied by the request/model authority, never invent it."""
    candidates: list[Any] = [getattr(session, "clip_source_identity", None)]
    extra = getattr(getattr(session, "request", None), "extra_data", {}) or {}
    if isinstance(extra, Mapping):
        candidates.extend((extra.get("clip_source_identity"), extra.get("source_identity")))
    metadata = getattr(session, "clip_source_metadata", None)
    candidates.append(metadata)
    for candidate in candidates:
        if isinstance(candidate, Mapping):
            return {
                str(key): value
                for key, value in candidate.items()
                if str(key) in {
                    "checkpoint_identity", "checkpoint_id", "source_identity", "checkpoint_hash",
                    "stable_hash", "manifest_generation", "content_generation", "manifest_digest",
                    "generation", "digest", "selected_tensor_scope", "tensor_scope", "selected_scope",
                    "scope", "model_patch_identity", "patch_identity", "model_identity", "target_device",
                    "cast_policy_version",
                }
            }
    return {}


@contextlib.contextmanager
def _ra9h_forward_conversion_instrumentation(*, enabled: bool):
    """Observe actual ``cast_to`` allocations without synchronizing CUDA.

    The wrapper counts only a new tensor returned by the existing Comfy cast
    seam.  If that seam cannot be installed, the result is NOT RUN rather than
    a synthetic zero.  Installation is scoped to the real CLIP forward and is
    restored on every outcome.
    """
    record: dict[str, Any] = {
        "status": "NOT RUN",
        "reason": "disabled" if not enabled else "unavailable",
        "conversion_count": None,
        "destination_bytes": None,
        "source_bytes": None,
        "instrumentation_scope": "actual_comfy_cast_to_returned_tensor",
        "timing_scope": "NOT RUN",
        "synchronization": "none",
        "real_forward_count": None,
        "per_forward": None,
        "repeated_conversion_count": None,
        "repeated_conversion_bytes": None,
        "forward_diagnostics_status": "NOT RUN",
    }
    if not enabled:
        yield record
        return
    try:
        management = importlib.import_module("comfy.model_management")
        original = getattr(management, "cast_to", None)
    except Exception as exc:
        record["reason"] = f"instrumentation_install_failed:{type(exc).__name__}"
        record.pop("_observe_forward", None)
        yield record
        return
    if not callable(original):
        yield record
        return
    count = 0
    source_bytes = 0
    destination_bytes = 0
    conversions: list[dict[str, Any]] = []
    forward_starts: dict[int, tuple[int, int, int]] = {}
    per_forward: list[dict[str, Any]] = []

    def observe_forward(phase: str, index: int) -> None:
        if phase == "start":
            forward_starts[int(index)] = (count, source_bytes, destination_bytes)
            return
        start_count, start_source, start_destination = forward_starts.pop(
            int(index), (count, source_bytes, destination_bytes)
        )
        per_forward.append({
            "forward_index": int(index),
            "conversion_count": max(0, count - start_count),
            "source_bytes": max(0, source_bytes - start_source),
            "destination_bytes": max(0, destination_bytes - start_destination),
        })

    # Request-local callback only; it is removed before telemetry is emitted.
    record["_observe_forward"] = observe_forward

    def wrapped(*args: Any, **kwargs: Any) -> Any:
        nonlocal count, source_bytes, destination_bytes
        result = original(*args, **kwargs)
        tensor = args[0] if args else None
        if (
            isinstance(tensor, torch.Tensor)
            and isinstance(result, torch.Tensor)
            and result is not tensor
            and (tensor.dtype != result.dtype or tensor.device != result.device)
        ):
            count += 1
            source_bytes += int(tensor.numel() * tensor.element_size())
            destination_bytes += int(result.numel() * result.element_size())
            conversions.append({
                "source_dtype": str(tensor.dtype),
                "destination_dtype": str(result.dtype),
                "source_bytes": int(tensor.numel() * tensor.element_size()),
                "destination_bytes": int(result.numel() * result.element_size()),
            })
        return result

    try:
        setattr(management, "cast_to", wrapped)
    except Exception as exc:
        record["reason"] = f"instrumentation_install_failed:{type(exc).__name__}"
        yield record
        return
    record.update({"status": "RUN", "reason": "installed", "conversion_count": 0, "destination_bytes": 0, "source_bytes": 0, "timing_scope": "TOTAL actual forward cast_to observation", "conversions": conversions, "per_forward": per_forward})
    try:
        yield record
    finally:
        try:
            setattr(management, "cast_to", original)
        finally:
            record.update({
                "conversion_count": count,
                "destination_bytes": destination_bytes,
                "source_bytes": source_bytes,
                "conversions": list(conversions),
                "per_forward": list(per_forward),
                "real_forward_count": len(per_forward) if per_forward else None,
                "forward_diagnostics_status": (
                    "PROVEN" if len(per_forward) >= 2 else
                    "UNPROVEN" if per_forward else "NOT RUN"
                ),
            })
            record.pop("_observe_forward", None)
            if len(per_forward) >= 2:
                record["repeated_conversion_count"] = sum(
                    int(item["conversion_count"]) for item in per_forward[1:]
                )
                record["repeated_conversion_bytes"] = sum(
                    int(item["destination_bytes"]) for item in per_forward[1:]
                )


async def golden_clip_load(session: GoldenSession) -> Any:
    """Load CLIP via the contract's :class:`ClipLoadSpec` and the real
    upstream constructor.

    Resolves each spec checkpoint (already path-resolved in the spec folder
    during request setup), performs exactly ONE QD physical source read + H2D
    PER CHECKPOINT in spec order retaining every per-file owner, then calls
    ``comfy.sd.load_text_encoder_state_dicts`` ONCE with the ordered shallow
    copies of every checkpoint's QD views, the spec's CLIPType resolved
    dynamically from ``comfy.sd.CLIPType`` by normalized name (unknown names
    fail closed — no silent fallback), and native CLIP model options (empty for
    the canonical path) so Comfy derives dtype and load/offload devices.  A
    scoped ``text_encoder_initial_device -> meta`` seam keeps the constructor
    from calling ``load_models_gpu``; weights are adopted zero-copy via
    ``assign=True`` under a dynamic CoreModelPatcher.

    NOTE: upstream ``comfy.sd.load_clip`` reads each file itself via
    ``load_torch_file``, which would force a second payload read; this stage
    mirrors its exact delegation into ``load_text_encoder_state_dicts``
    instead (same ordering semantics), preserving single-read QD transport.
    Every QD owner is retained on the session (and the first on the returned
    CLIP) so views outlive forward.  The fail-closed adoption proof runs via
    the generic scope selector over the combined cond_stage_model against the
    UNION of all checkpoints' view pointers.  A non-dynamic patcher
    (disable_offload wrapper) is rejected with a clear marker rather than
    silently accepting copies.  If the explicitly requested cast-once arm
    cannot establish its identity or transfer proof, the already-transported
    source is used for an observable BF16 fallback; no reread or second H2D is
    permitted.
    """
    rec = session.recorder
    rec.begin_stage("golden_clip_load")
    diagnostics_enabled = stage_diagnostics_enabled()
    clip_page_fault_start = _clip_page_fault_snapshot() if diagnostics_enabled else None
    transports: list[dict] = []
    clip_timing = _ClipTiming(enabled=diagnostics_enabled)
    clip_transfer: Any = None
    transformed_state_dicts: Optional[list[dict]] = None
    clip_lifecycle_phase = "constructor_preflight"
    residency = getattr(session, "clip_residency", "bf16")
    try:
        contract = session.contract
        spec = contract.clip_spec or CANONICAL_CLIP_SPEC
        request = getattr(session, "request", None)
        residency = resolve_clip_residency(
            getattr(request, "clip_residency", residency)
        )
        session.clip_residency = residency
        session.clip_residency_record = {
            "requested": residency,
            "actual": "bf16" if residency == "bf16" else "NOT RUN",
            "fallback": False,
            "status": "CONTROL" if residency == "bf16" else "REQUESTED",
        }
        session.recorder.clip_residency_record = dict(session.clip_residency_record)
        _set_ra9h_telemetry(
            session,
            clip_residency_requested=residency,
            clip_residency_effective=residency,
            cast_once_attempted=residency == "fp32_cast_once",
            cast_once_applied=False,
            cast_once_fallback=False,
            cast_once_fallback_reason=None,
            source_refs_dropped=("NOT RUN" if residency == "bf16" else False),
            source_owner_retired=("NOT RUN" if residency == "bf16" else False),
        )
        if str(spec.dtype_policy) != "uniform":
            raise RuntimeError(f"clip_dtype_policy_unsupported:{spec.dtype_policy}")
        if not session.clip_paths:
            raise RuntimeError("clip_paths_missing")

        # One QD physical transport PER checkpoint, in spec order; every
        # per-file owner is retained (no reread, no second H2D).
        state_dicts: list[dict] = []
        for index, path in enumerate(session.clip_paths):
            role = "clip" if len(session.clip_paths) == 1 else f"clip{index}"
            with clip_timing.span("source_open_read", boundary_kind="host_observed"):
                with _golden_qd_transport_arm_scope(getattr(session, "qd_transport_arm", "legacy")):
                    transport = read_file_qd_gpu(
                        path,
                        role=role,
                        qd=contract.qd,
                        block_bytes=contract.block_bytes,
                    )
            transports.append(transport)
            session.register_qd_owner(transport["owner"])
            state_dicts.append(transport["sd"])
            stats = transport.get("stats") or {}
            source_layout = stats.get("source_open_header_layout") or {}
            staging = stats.get("staging") or {}
            if diagnostics_enabled:
                clip_timing.unproven(
                    "header_layout_parse",
                    duration_ns=source_layout.get("header_layout_ns"),
                    detail="transport exposes duration but not an absolute parse boundary",
                    parent="source_open_read",
                )
                clip_timing.unproven(
                    "qd_staging_allocation",
                    duration_ns=staging.get("allocation_ns"),
                    detail="pinned allocation duration is reported by transport",
                    parent="source_open_read",
                )
                h2d_intervals = [
                    (item.get("h2d_enqueue_start_ns"), item.get("h2d_enqueue_end_ns"))
                    for item in stats.get("blocks", [])
                    if item.get("h2d_enqueue_start_ns") is not None
                    and item.get("h2d_enqueue_end_ns") is not None
                ]
                if h2d_intervals:
                    h2d_start = min(int(item[0]) for item in h2d_intervals)
                    h2d_end = max(int(item[1]) for item in h2d_intervals)
                    clip_timing.phases.append({
                        "name": "h2d_transport",
                        "start_ns": h2d_start,
                        "end_ns": h2d_end,
                        "duration_ns": max(0, h2d_end - h2d_start),
                        "boundary_kind": "host_observed_transport_overlap",
                        "level": "nested",
                        "parent_phase": "source_open_read",
                    })
                else:
                    clip_timing.unproven(
                        "h2d_transport", parent="source_open_read",
                        detail="no absolute H2D enqueue boundaries available",
                    )
            owner_fields = {
                "role": role,
                "gpu_bytes": transport["stats"]["gpu_bytes"],
                "clip_index": index,
            }
            if diagnostics_enabled:
                owner_fields["transport_timing"] = build_qd_transport_diagnostics(stats)
            rec.event("clip_qd_owner_created", **owner_fields)
        owners = [t["owner"] for t in transports]
        session.clip_owners = owners
        session.clip_owner = owners[0]
        source_state_dict_count = len(state_dicts)
        source_tensor_count = sum(
            sum(1 for key in sd if str(key) not in _CLIP_TOKENIZER_KEYS)
            for sd in state_dicts
        )
        authoritative = _ra9h_authoritative_identity(session)
        if authoritative:
            _set_ra9h_telemetry(
                session,
                source_generation_identity={
                    str(key): value for key, value in authoritative.items()
                    if key in {
                        "checkpoint_identity", "checkpoint_id", "source_identity",
                        "checkpoint_hash", "stable_hash", "manifest_generation",
                        "content_generation", "manifest_digest", "generation", "digest",
                        "selected_tensor_scope", "tensor_scope", "selected_scope", "scope",
                        "model_patch_identity", "patch_identity", "model_identity", "target_device",
                    }
                },
                selected_tensor_count=source_tensor_count,
            )
        source_dtype = uniform_source_dtype_across(state_dicts, tag="clip_source")
        _set_ra9h_telemetry(session, source_dtype=str(source_dtype))

        if residency == "fp32_cast_once":
            # RA9G owns the source and transformed mappings from this point
            # until the actual bind, proof, and source-reference retirement.
            ra9g = _ra9h_clip_module()
            clip_lifecycle_phase = "identity"

            def set_clip_lifecycle_phase(phase: str) -> None:
                nonlocal clip_lifecycle_phase
                if phase not in _CLIP_CAST_ONCE_PHASES:
                    raise RuntimeError(f"clip_lifecycle_phase_invalid:{phase}")
                clip_lifecycle_phase = phase
                session.clip_residency_record["lifecycle_phase"] = phase
                _set_ra9h_telemetry(session, lifecycle_phase=phase)

            def fallback_to_transported_bf16(exc: Exception) -> None:
                """Use only the source already returned by QD transport."""
                nonlocal clip_transfer, transformed_state_dicts
                if clip_transfer is not None:
                    # Do not retire the source owner here: the ordinary BF16
                    # bind below still consumes these already-transported
                    # views.  Session teardown remains the cleanup owner.
                    clip_transfer = None
                    session.clip_ownership_transfer = None
                transformed_state_dicts = state_dicts
                session.clip_residency_record.update({
                    "actual": "bf16",
                    "status": "FALLBACK",
                    "fallback": True,
                    "fallback_source": "already_transported_bf16",
                    "fallback_reason": f"{type(exc).__name__}: {str(exc)[:240]}",
                    "timing": {"transform_once": "NOT RUN"},
                })
                session.recorder.clip_residency_record = dict(session.clip_residency_record)
                _set_ra9h_telemetry(
                    session,
                    clip_residency_effective="bf16",
                    cast_once_applied=False,
                    cast_once_fallback=True,
                    cast_once_fallback_reason=f"{type(exc).__name__}: {str(exc)[:240]}",
                    fallback_source="already_transported_bf16",
                    failure_classification="safe_bf16_fallback",
                    resident_dtype=None,
                    compute_dtype=None,
                    cast_destination_bytes=None,
                    cast_once_transform_ms=None,
                )
                rec.event(
                    "clip_fp32_cast_once_fallback",
                    requested="fp32_cast_once",
                    actual="bf16",
                    fallback=True,
                    fallback_reason=str(exc)[:240],
                )

            try:
                manifests = [
                    _ra9h_manifest_for_transport(transport, index)
                    for index, transport in enumerate(transports)
                ]
                authoritative = _ra9h_authoritative_identity(session)
                identity = ra9g.build_source_manifest_identity(
                    manifests,
                    identity=authoritative,
                    target_device=authoritative.get("target_device"),
                    cast_policy_version=str(authoritative.get("cast_policy_version", "ra9g-fp32-v1")),
                )
            except Exception as exc:
                # Identity construction is the only pre-transform fallback
                # boundary.  Updates/events stay outside this handler so
                # telemetry failures remain visible.
                fallback_to_transported_bf16(exc)
            else:
                session.run_identity["clip_source_identity_digest"] = identity.digest
                session.recorder.run_identity = dict(session.run_identity)
                set_clip_lifecycle_phase("constructor_preflight")
                clip_transfer = ra9g.construct_ownership_transfer(
                    state_dicts,
                    owners,
                    manifests,
                    identity=identity,
                    strict=True,
                )
                session.clip_ownership_transfer = clip_transfer
                set_clip_lifecycle_phase("transform")
                transform_started_ns = time.perf_counter_ns()
                try:
                    transformed_state_dicts, transform_record = clip_transfer.transform_once()
                except Exception as exc:
                    fallback_to_transported_bf16(exc)
                else:
                    set_clip_lifecycle_phase("constructor_preflight")
                    transform_record = {
                        **dict(transform_record),
                        "timing_scope": "TOTAL transform_once host wall",
                        "host_wall_ns": max(0, time.perf_counter_ns() - transform_started_ns),
                        "status": "TOTAL",
                    }
                    session.clip_residency_record.update({
                        # Transformation alone is not application.  The effective
                        # arm remains unproven until bind, proof, and retirement
                        # all reach READY below.
                        "actual": "NOT RUN",
                        "status": "TRANSFORMED_UNBOUND",
                        "identity": identity.metadata(),
                        "transform": transform_record,
                    })
                    session.recorder.clip_residency_record = dict(session.clip_residency_record)
                    _set_ra9h_telemetry(
                        session,
                        source_generation_identity=_generation_identity(identity),
                        selected_tensor_count=len(identity.expected_keys),
                        source_dtype=str(next(iter(identity.expected_dtypes))[1]),
                        expected_device=identity.target_device,
                        cast_destination_bytes=transform_record.get("destination_bytes"),
                        cast_once_transform_ms=(
                            float(transform_record["host_wall_ns"]) / 1_000_000.0
                            if transform_record.get("host_wall_ns") is not None else None
                        ),
                    )
                    rec.event("clip_fp32_cast_once_transform", **transform_record)
        else:
            # Do not touch the existing BF16 state dicts or loader arguments in
            # the control arm.
            transformed_state_dicts = state_dicts

        if residency == "fp32_cast_once":
            set_clip_lifecycle_phase("constructor_preflight")

        import comfy.sd  # upstream ComfyUI module (allowed import)
        import folder_paths

        # Fail-closed preflight (spec-gated): the dynamic CoreModelPatcher
        # must be active BEFORE construction so load_sd can adopt weights by
        # reference (assign=True) instead of copying.
        if spec.require_dynamic_patcher:
            require_dynamic_core_model_patcher(tag="clip")
        # Keep the uniform source-dtype proof, but use native CLIP construction
        # semantics.  The canonical spec therefore passes an empty options
        # dict, allowing Comfy to derive dtype and load/offload devices.  The
        # initial-device override is deliberately a scoped seam below rather
        # than a model option (which would change native policy selection).
        # Validate constructor input, but publish residency only from the
        # post-bind selected-scope snapshot below.
        uniform_source_dtype_across(transformed_state_dicts, tag="clip")
        model_options = {}
        if spec.model_options_overrides:
            model_options.update(dict(spec.model_options_overrides))
        if "initial_device" in model_options:
            raise RuntimeError("clip_initial_device_override_unsupported")
        embedding_directory = (
            list(spec.embedding_directory)
            if spec.embedding_directory is not None
            else folder_paths.get_folder_paths("embeddings")
        )
        clip_type_value = resolve_clip_type(spec.clip_type)
        import comfy.model_management as model_management

        native_initial_device = model_management.text_encoder_initial_device

        def golden_initial_device(load_device, offload_device, model_size=0):
            return torch.device("meta")

        model_management.text_encoder_initial_device = golden_initial_device
        try:
            # Shallow dict copies retain the SAME tensor objects (zero-copy
            # preserved) while shielding our retained view dicts from upstream
            # key mutations inside load_text_encoder_state_dicts.
            with clip_timing.span("skeleton_patcher_construction"):
                clip = comfy.sd.load_text_encoder_state_dicts(
                    [dict(sd) for sd in transformed_state_dicts],
                    embedding_directory=embedding_directory,
                    clip_type=clip_type_value,
                    model_options=model_options,
                )
        finally:
            model_management.text_encoder_initial_device = native_initial_device
        if clip is None:
            raise RuntimeError("clip_construct_failed")
        # Postflight: a non-dynamic patcher (e.g. a disable_offload wrapper)
        # would silently accept weight COPIES — always rejected, regardless of
        # the spec preflight gate.
        rec.event(
            "clip_patcher_identity",
            **require_dynamic_patcher_instance(tag="clip", patcher=getattr(clip, "patcher", None)),
        )
        with clip_timing.span("owner_publish_handoff"):
            try:
                setattr(clip, "_golden_qd_owner", owners[0])
            except Exception:
                pass  # owner lifetime is additionally held by the session
            session.clip = clip

        usable = callable(getattr(clip, "encode_from_tokens_scheduled", None)) and callable(
            getattr(clip, "tokenize", None)
        )
        if not usable:
            raise RuntimeError("clip_not_usable")
        cond_model = getattr(clip, "cond_stage_model", None)
        # Fail-closed adoption proof: every cond-stage parameter/buffer must be
        # CUDA-resident, at the exact uniform transported source dtype, and
        # storage-identical to a QD view.  No model.to / loader fallback.
        # Generic scope selection locates the checkpoint module purely by
        # pointer identity among cond-stage submodules (wrapper-shape
        # agnostic); the view set is the UNION of ALL checkpoints' views, so
        # every checkpoint's tensors are accounted and any copied/missing/
        # unused view fails closed.
        combined_views: dict[str, Any] = {}
        for index, sd in enumerate(transformed_state_dicts):
            for key, view in sd.items():
                combined_views[f"[{index}]{key}"] = view
        if clip_transfer is not None:
            set_clip_lifecycle_phase("bind")
        bind_started_ns = time.perf_counter_ns() if clip_transfer is not None else None
        if clip_transfer is not None:
            # This is the actual post-loader destination, not the transformed
            # mapping.  The receipt is built before any source owner cleanup.
            ra9g = _ra9h_clip_module()
            actual_destination = ra9g.actual_bind_destination_map(
                clip, clip_transfer.identity.expected_keys
            )
            receipt = ra9g.build_actual_bind_receipt(
                clip, actual_destination, clip_transfer.identity, assign=True
            )
            clip_transfer.acknowledge_actual_bind(
                actual_destination, receipt=receipt, assign=True, clip=clip
            )
            bind_end_ns = time.perf_counter_ns()
            _set_ra9h_telemetry(
                session,
                cast_once_bind_ms=(
                    float(max(0, bind_end_ns - bind_started_ns)) / 1_000_000.0
                    if bind_started_ns is not None else None
                ),
            )
            set_clip_lifecycle_phase("proof")
            proof_started_ns = time.perf_counter_ns()
            transfer_proof = clip_transfer.prove_storage(
                expected_device=clip_transfer.identity.target_device
            )
            session.clip_residency_record.update({
                "actual_bind_receipt": receipt,
                "storage_proof": transfer_proof,
                "timing": {
                    "transform_once": "TOTAL",
                    "actual_bind_receipt": "PARTIAL post-loader destination receipt",
                    "storage_proof": "TOTAL RA9G prove_storage boundary",
                },
            })
            session.recorder.clip_residency_record = dict(session.clip_residency_record)
            rec.event(
                "clip_fp32_cast_once_actual_bind",
                receipt=receipt,
                storage_proof=transfer_proof,
            )
        if clip_transfer is not None:
            set_clip_lifecycle_phase("adoption")
        with clip_timing.span("storage_adoption"):
            adoption = select_and_validate_qd_adoption_scope("clip", cond_model, combined_views)
        selected_scope = next(
            (module for path, module in cond_model.named_modules()
             if str(path) == str(adoption["selected_scope"])),
            cond_model if adoption["selected_scope"] == "" else None,
        )
        if selected_scope is None:
            raise RuntimeError("clip_compute_scope_not_found")
        if clip_transfer is not None:
            set_clip_lifecycle_phase("proof")
        with clip_timing.span("compute_ready_proof"):
            compute_identity = _clip_compute_identity(
                selected_scope, adoption, getattr(clip, "patcher", None)
            )
        if not compute_identity["compute_ready"]:
            raise RuntimeError(f"clip_compute_scope_not_ready:{compute_identity}")
        if clip_transfer is not None:
            # Keep source mappings and their owner alive through BOTH RA9G's
            # storage proof and Golden's generic adoption proof.  Only then is
            # it safe to drop mappings, prove source-free storage, and retire.
            set_clip_lifecycle_phase("source_drop")
            clip_transfer.drop_source_references(
                receipt={"source_refs_dropped": True, "identity_digest": clip_transfer.identity.digest}
            )
            source_free_proof = clip_transfer.source_free_storage_proof(
                actual_destination,
                expected_device=clip_transfer.identity.target_device,
            )
            proof_end_ns = time.perf_counter_ns()
            # The transport result also retains the source view dictionaries.
            # Remove every caller-owned source mapping before releasing the
            # backing owner; transformed FP32 maps are independent storage.
            for transport in transports:
                transport["sd"] = {}
            state_dicts.clear()
            set_clip_lifecycle_phase("retirement")
            clip_transfer.retire_owners()
            source_free_proof = clip_transfer.source_free_storage_proof(
                actual_destination,
                expected_device=clip_transfer.identity.target_device,
            )
            if not source_free_proof.get("ok"):
                raise RuntimeError("clip_source_free_proof_failed_after_retirement")
            set_clip_lifecycle_phase("ready")
            ready_record = clip_transfer.mark_ready(clip)
            session.clip_ownership_transfer_record = clip_transfer.snapshot()
            session.clip_residency_record.update({
                "source_free_storage_proof": source_free_proof,
                "owner_cleanup": ready_record,
                "source_refs_dropped_before_owner_retirement": True,
                "actual": "fp32_cast_once",
                "fallback": False,
                "status": "READY",
            })
            session.recorder.clip_residency_record = dict(session.clip_residency_record)
            _set_ra9h_telemetry(
                session,
                clip_residency_effective="fp32_cast_once",
                cast_once_attempted=True,
                cast_once_applied=True,
                cast_once_fallback=False,
                cast_once_fallback_reason=None,
                source_generation_identity=_generation_identity(clip_transfer.identity),
                selected_tensor_count=len(clip_transfer.identity.expected_keys),
                source_dtype=str(source_dtype),
                resident_dtype=compute_identity.get("resident_dtype") or (
                    compute_identity.get("compute_scope_dtype")
                    if compute_identity.get("compute_scope_storage_proven") else None
                ),
                compute_dtype=None,
                expected_device=clip_transfer.identity.target_device,
                cast_destination_bytes=clip_transfer.snapshot().get("destination_bytes"),
                adopted_parameter_count=len(clip_transfer.identity.expected_keys),
                adopted_storage_proven=True,
                source_refs_dropped=True,
                source_owner_retired=True,
                ownership_checkpoints=ready_record.get("ownership_checkpoints"),
                cast_once_proof_ms=(
                    float(max(0, proof_end_ns - proof_started_ns)) / 1_000_000.0
                    if proof_started_ns is not None else None
                ),
            )
            rec.event(
                "clip_fp32_cast_once_ready",
                source_free_storage_proof=source_free_proof,
                owner_cleanup=ready_record,
                source_refs_dropped_before_owner_retirement=True,
            )
            # The model owns the adopted FP32 storage now.  Drop every
            # request-local mapping/container that still points at source or
            # transformed tensors before leaving the load stage.
            combined_views.clear()
            state_dicts.clear()
            if transformed_state_dicts is not None:
                transformed_state_dicts.clear()
            for transport in transports:
                transport["sd"] = {}
            session.clip_ownership_transfer = None
        session.clip_compute_scope = selected_scope
        session.clip_compute_scope_identity = dict(compute_identity)
        if clip_transfer is None:
            _set_ra9h_telemetry(
                session,
                clip_residency_effective="bf16",
                source_dtype=str(source_dtype),
                resident_dtype=compute_identity.get("resident_dtype") or (
                    compute_identity.get("compute_scope_dtype")
                    if compute_identity.get("compute_scope_storage_proven") else None
                ),
                compute_dtype=None,
                expected_device=str(compute_identity["compute_scope_device"]),
                adopted_parameter_count=adoption.get(
                    "matched_count", adoption.get("tensor_count")
                ),
                adopted_storage_proven=bool(
                    compute_identity.get("compute_scope_storage_proven")
                ),
                source_refs_dropped="NOT RUN",
                source_owner_retired="NOT RUN",
            )
        rec.event(
            "clip_adoption_identity",
            state_dict_count=source_state_dict_count,
            **adoption,
            compute_scope_device=compute_identity["compute_scope_device"],
            compute_scope_dtype=compute_identity["compute_scope_dtype"],
            compute_scope_storage_proven=compute_identity["compute_scope_storage_proven"],
        )
        rec.event(
            "clip_published",
            tensor_count=source_tensor_count,
            compute_scope_device=compute_identity["compute_scope_device"],
            compute_scope_dtype=compute_identity["compute_scope_dtype"],
            compute_scope_storage_proven=compute_identity["compute_scope_storage_proven"],
            compute_ready=compute_identity["compute_ready"],
            outer_extra_count=adoption["outer_extra_count"],
            outer_extra_bytes=adoption["outer_extra_bytes"],
            outer_extra_devices=adoption["outer_extra_devices"],
            outer_extra_names=adoption["outer_extra_names"],
            owner_retained=session.clip_owner is owners[0],
        )
        qd_quiescence = [
            _require_transport_quiescence(transport, tag=f"clip{index}")
            for index, transport in enumerate(transports)
        ]
        clip_page_faults = (
            _clip_page_faults_summary(
                "golden_clip_load", clip_page_fault_start, _clip_page_fault_snapshot()
            ) if diagnostics_enabled else {}
        )
        session.clip_load_page_faults = clip_page_faults
        session.clip_load_timing = clip_timing.finish() if diagnostics_enabled else {}
        if diagnostics_enabled:
            rec.event("clip_load_timing", **session.clip_load_timing)
            rec.event("clip_page_faults", **clip_page_faults)
        rec.end_stage(
            "golden_clip_load",
            ready=True,
            usable=True,
            published=source_tensor_count,
            compute_scope_device=compute_identity["compute_scope_device"],
            compute_scope_dtype=compute_identity["compute_scope_dtype"],
            compute_scope_storage_proven=compute_identity["compute_scope_storage_proven"],
            compute_ready=compute_identity["compute_ready"],
            outer_extra_count=adoption["outer_extra_count"],
            outer_extra_bytes=adoption["outer_extra_bytes"],
            outer_extra_devices=adoption["outer_extra_devices"],
            outer_extra_names=adoption["outer_extra_names"],
            owner_retained=True,
            clip_name=[n for n in spec.checkpoint_names],
            clip_type=spec.clip_type,
            state_dict_count=source_state_dict_count,
            clip_residency=getattr(session, "clip_residency", "bf16"),
            clip_residency_record=dict(getattr(session, "clip_residency_record", {})),
            ownership_transfer=dict(getattr(session, "clip_ownership_transfer_record", {})),
            selected_scope=adoption["selected_scope"],
            source_read_count=sum(int(t["stats"]["source_read_count"]) for t in transports),
            h2d_completed_bytes=sum(int(t["stats"]["h2d_completed_bytes"]) for t in transports),
            qd_quiescence=qd_quiescence,
            **(
                {
                    "clip_load_timing": session.clip_load_timing,
                    "clip_page_faults": clip_page_faults,
                    "transport_stats": [
                        build_qd_transport_diagnostics(t["stats"]) for t in transports
                    ],
                }
                if diagnostics_enabled or getattr(session, "qd_transport_arm", "legacy") == "dispatcher" else {}
            ),
        )
        return clip
    except BaseException as exc:
        if residency == "fp32_cast_once":
            error_text = str(exc)[:240]
            fatal_bind_or_proof, failure_classification = _clip_cast_once_failure_classification(
                clip_lifecycle_phase
            )
            session.clip_residency_record = {
                **dict(getattr(session, "clip_residency_record", {})),
                "requested": "fp32_cast_once",
                "actual": "NOT RUN",
                "status": "FAILED",
                "lifecycle_phase": clip_lifecycle_phase,
                "fallback": False,
                "fatal_failure": fatal_bind_or_proof,
                "failure_classification": failure_classification,
                "fallback_reason": f"{type(exc).__name__}: {error_text}",
            }
            session.recorder.clip_residency_record = dict(session.clip_residency_record)
            _set_ra9h_telemetry(
                session,
                clip_residency_effective="NOT RUN",
                cast_once_attempted=True,
                cast_once_applied=False,
                cast_once_fallback=False,
                cast_once_fallback_reason=None,
                fallback_reason=f"{type(exc).__name__}: {error_text}",
                fatal_failure=fatal_bind_or_proof,
                failure_classification=failure_classification,
                resident_dtype=None,
                compute_dtype=None,
                expected_device=None,
                adopted_parameter_count=None,
                adopted_storage_proven=None,
                source_refs_dropped=False,
                source_owner_retired=False,
                cast_destination_bytes=None,
                cast_once_bind_ms=None,
                cast_once_proof_ms=None,
            )
            rec.event(
                "clip_fp32_cast_once_failed",
                requested="fp32_cast_once",
                actual="NOT RUN",
                fallback=False,
                fatal_failure=fatal_bind_or_proof,
                failure_classification=failure_classification,
                lifecycle_phase=clip_lifecycle_phase,
                reason=error_text,
            )
        clip_page_faults = (
            _clip_page_faults_summary(
                "golden_clip_load", clip_page_fault_start, _clip_page_fault_snapshot()
            ) if diagnostics_enabled else {}
        )
        session.clip_load_page_faults = clip_page_faults
        if diagnostics_enabled:
            try:
                rec.event("clip_page_faults", **clip_page_faults)
            except Exception:
                pass
        rec.fail_stage(
            "golden_clip_load", exc,
            **({"clip_page_faults": clip_page_faults} if diagnostics_enabled else {}),
        )
        raise


async def golden_clip_forward(session: GoldenSession) -> Any:
    """Execute the canonical CLIPTextEncode node through the serial runner with
    exact upstream semantics: its full dependency closure (including any
    linked text-encode dependencies) executes/serially resolves first, then
    the encode node itself runs ``tokenize`` +
    ``clip.encode_from_tokens_scheduled`` — so the real CLIP forward happens
    inside this stage interval and its timing is preserved.  The CLIP loader
    is seeded so no source reread can occur.  No conditioning cache, no
    prefetch, and no UNET/VAE source activity may begin here."""
    rec = session.recorder
    rec.begin_stage("golden_clip_forward")
    diagnostics_enabled = stage_diagnostics_enabled()
    clip_page_fault_start = _clip_page_fault_snapshot() if diagnostics_enabled else None
    clip_timing = _ClipTiming(enabled=diagnostics_enabled)
    conversion_telemetry: Optional[dict[str, Any]] = None
    try:
        runner = session.runner
        if runner is None:
            raise RuntimeError("clip_forward_requires_runner")
        node_map = session.node_map
        # Native socket-major cache shape: one output socket carrying one item.
        runner.seed(node_map.clip_loader_id, [[session.clip]])
        scope = session.clip_compute_scope
        patcher = getattr(session.clip, "patcher", None)
        before = _clip_scope_snapshot(scope, patcher) if scope is not None else {
            "status": "unproven", "reason": "compute_scope_missing"
        }
        clip_timing.snapshots = {"before": before}
        rec.event(
            "clip_cache_status",
            status="not_used",
            cache_owner="golden_serial_runner",
            explanation="runner cache is node execution bookkeeping, not a CLIP conditioning cache",
        )
        clip_timing.unproven(
            "clip_model_patcher_device_cast_preparation",
            detail="no separate cast/materialization boundary is directly observable in Golden Serial",
        )
        clip_timing.unproven(
            "clip_projection_final_layers",
            detail="upstream encode call is the proven aggregate boundary; inner projection split unavailable",
        )
        clip_timing.unproven(
            "clip_cache_interaction",
            detail="no conditioning cache bridge exists in Golden Serial",
        )
        runner.begin_scope({"clip_forward"})
        try:
            with _ra9h_forward_conversion_instrumentation(
                enabled=(
                    diagnostics_enabled
                    and
                    (getattr(session, "clip_residency_record", {}) or {}).get("actual")
                    in {"bf16", "fp32_cast_once"}
                )
            ) as conversion_telemetry:
                with _clip_qwen_forward_hooks(
                    scope,
                    clip_timing,
                    lambda: _clip_scope_snapshot(scope, patcher) if scope is not None else {
                        "status": "unproven", "reason": "compute_scope_missing"
                    },
                    recorder=rec,
                    conversion_observer=(
                        lambda phase, index: (
                            conversion_telemetry.get("_observe_forward", lambda *_: None)(phase, index),
                            conversion_telemetry.setdefault(
                                "_forward_observer_events", []
                            ).append({"phase": phase, "index": int(index)})
                        )
                        if conversion_telemetry is not None else None
                    ),
                    enabled=diagnostics_enabled,
                ):
                    with _clip_forward_wrappers(
                        session.clip,
                        clip_timing,
                        lambda: _clip_scope_snapshot(scope, patcher) if scope is not None else {
                            "status": "unproven", "reason": "compute_scope_missing"
                        },
                        enabled=diagnostics_enabled,
                    ):
                        with clip_timing.span("clip_graph_node_wrapper"):
                            executed = await runner.run_closure(node_map.clip_encode_id, include_target=True)
        finally:
            runner.end_scope()
        qwen_forwards = list(getattr(clip_timing, "qwen_forwards", []))
        if diagnostics_enabled:
            rec.event(
                "clip_qwen_transformer_hooks",
                status=getattr(clip_timing, "qwen_hook_status", "UNPROVEN"),
                forward_count=len(qwen_forwards),
                first_qwen_compute=(qwen_forwards[0] if qwen_forwards else None),
                later_forward_work=qwen_forwards[1:],
            )
        with clip_timing.span("clip_post_forward_sync_wait"):
            _assert_runner_quiescence(runner)
        if conversion_telemetry is not None:
            observer_events = conversion_telemetry.pop("_forward_observer_events", [])
            # Pairing is done here, after the context has restored the cast
            # seam.  The qwen hook owns the authoritative real-forward count;
            # the conversion seam contributes only per-forward allocation facts.
            if observer_events and conversion_telemetry.get("per_forward") is None:
                conversion_telemetry["per_forward"] = []
            session.clip_forward_conversion = dict(conversion_telemetry)
            session.recorder.clip_forward_conversion = dict(conversion_telemetry)
            rec.event("clip_forward_conversion_instrumentation", **conversion_telemetry)
        compute_dtype, compute_evidence = _clip_compute_dtype_from_forward_evidence(
            qwen_forwards, conversion_telemetry
        )
        repeated_conversion_count = (
            conversion_telemetry.get("repeated_conversion_count")
            if isinstance(conversion_telemetry, Mapping) else None
        )
        repeated_conversion_bytes = (
            conversion_telemetry.get("repeated_conversion_bytes")
            if isinstance(conversion_telemetry, Mapping) else None
        )
        forward_diag_status = (
            "PROVEN" if len(qwen_forwards) >= 2
            and isinstance(conversion_telemetry, Mapping)
            and conversion_telemetry.get("status") == "RUN"
            else "UNPROVEN" if qwen_forwards else "NOT RUN"
        )
        repeated_cast_work = (
            "PROVEN_ZERO" if forward_diag_status == "PROVEN" and repeated_conversion_count == 0
            else "PROVEN_NONZERO" if forward_diag_status == "PROVEN"
            else forward_diag_status
        )
        _set_ra9h_telemetry(
            session,
            compute_dtype=compute_dtype,
            compute_dtype_evidence=compute_evidence,
            real_forward_count=len(qwen_forwards) if qwen_forwards else None,
            per_forward_conversion_counts=(
                [item.get("conversion_count") for item in (conversion_telemetry or {}).get("per_forward", [])]
                if conversion_telemetry is not None and conversion_telemetry.get("per_forward") is not None else None
            ),
            per_forward_conversion_bytes=(
                [item.get("destination_bytes") for item in (conversion_telemetry or {}).get("per_forward", [])]
                if conversion_telemetry is not None and conversion_telemetry.get("per_forward") is not None else None
            ),
            repeated_conversion_count=repeated_conversion_count,
            repeated_conversion_bytes=repeated_conversion_bytes,
            forward_diagnostics_status=forward_diag_status,
        )
        encode_classes = [sc for _n, _c, sc in executed if sc == "clip_forward"]
        if not encode_classes:
            raise RuntimeError("clip_encode_node_did_not_execute")
        entry = runner.cache.get(node_map.clip_encode_id)
        if entry is None or not entry.outputs:
            raise RuntimeError("clip_encode_output_missing")
        with clip_timing.span("clip_conditioning_packaging"):
            conditioning = entry.outputs[0][0] if isinstance(entry.outputs[0], list) else entry.outputs[0]
        session.conditioning = conditioning
        after = clip_timing.snapshots.get("after_encode", {
            "status": "unproven", "reason": "encode_not_observed"
        })
        materialization = _clip_materialization_status(before, after)
        session.clip_compute_scope_identity = {
            **dict(session.clip_compute_scope_identity),
            "before_forward": before,
            "after_tokenization": clip_timing.snapshots.get("after_tokenization", {
                "status": "unproven", "reason": "tokenization_not_observed"
            }),
            "after_encode": after,
            "deferred_forward_materialization": materialization,
        }
        clip_timing_payload = clip_timing.finish() if diagnostics_enabled else {}
        if diagnostics_enabled:
            clip_timing_payload["deferred_forward_materialization"] = materialization
            clip_timing_payload["repeated_cast_work"] = repeated_cast_work
            clip_timing_payload["cache_status"] = "not_used"
            clip_timing_payload["first_qwen_compute"] = (
                qwen_forwards[0] if qwen_forwards else "UNPROVEN"
            )
            clip_timing_payload["later_forward_work"] = {
                "qwen_forwards": qwen_forwards[1:],
                "packaging_phase": "clip_conditioning_packaging",
                "residual_boundary": "UNPROVEN",
            }
        clip_page_faults = (
            _clip_page_faults_summary(
                "golden_clip_forward", clip_page_fault_start, _clip_page_fault_snapshot()
            ) if diagnostics_enabled else {}
        )
        session.clip_forward_page_faults = clip_page_faults
        session.clip_forward_timing = clip_timing_payload
        if diagnostics_enabled:
            rec.event("clip_forward_timing", **session.clip_forward_timing)
            rec.event("clip_page_faults", **clip_page_faults)
            rec.event(
                "clip_forward_readiness_recheck",
                before_forward=before,
                after_tokenization=clip_timing.snapshots.get("after_tokenization"),
                after_encode=after,
                deferred_forward_materialization=materialization,
                repeated_cast_work=repeated_cast_work,
            )
        rec.event(
            "clip_forward_complete",
            clip_forward_nodes=len(encode_classes),
            executed_nodes=[nid for nid, _cls, _sc in runner.executed_summary()],
            cache_status="not_used",
            conversion_instrumentation=(
                dict(conversion_telemetry) if conversion_telemetry is not None else "NOT RUN"
            ),
        )
        rec.end_stage(
            "golden_clip_forward",
            ready=True,
            encoded=True,
            deferred_forward_materialization=materialization,
            repeated_cast_work=repeated_cast_work,
            cache_status="not_used",
            conversion_instrumentation=(
                dict(conversion_telemetry) if conversion_telemetry is not None else "NOT RUN"
            ),
            **(
                {
                    "clip_forward_timing": session.clip_forward_timing,
                    "clip_page_faults": clip_page_faults,
                }
                if diagnostics_enabled else {}
            ),
        )
        return conditioning
    except BaseException as exc:
        clip_page_faults = (
            _clip_page_faults_summary(
                "golden_clip_forward", clip_page_fault_start, _clip_page_fault_snapshot()
            ) if diagnostics_enabled else {}
        )
        session.clip_forward_page_faults = clip_page_faults
        if diagnostics_enabled:
            try:
                rec.event("clip_page_faults", **clip_page_faults)
            except Exception:
                pass
        rec.fail_stage(
            "golden_clip_forward", exc,
            **({"clip_page_faults": clip_page_faults} if diagnostics_enabled else {}),
        )
        raise


# ── UNET construction helpers (R42-derived, fail-closed) ──────────────────


def _native_detection_input(base_sd: dict, base_meta: Any, prefix_fn, strip_fn, quant_fn=None):
    """EXACT input parity with comfy.sd.load_diffusion_model_state_dict:
    convert_old_quants -> unet_prefix_from_state_dict ->
    state_dict_prefix_replace(filter_keys=True) applied ONLY when non-empty."""
    detect_sd = dict(base_sd)
    detect_meta = base_meta
    if callable(quant_fn):
        # Match load_diffusion_model_state_dict: conversion errors are real
        # loader errors, not a reason to continue with an unconverted copy.
        detect_sd, detect_meta = quant_fn(detect_sd, "", metadata=detect_meta)
    prefix = prefix_fn(detect_sd)
    temp = strip_fn(dict(detect_sd), {prefix: ""}, filter_keys=True)
    if len(temp) > 0:
        detect_sd = temp
        if callable(quant_fn):
            detect_sd, detect_meta = quant_fn(detect_sd, "", metadata=detect_meta)
    return detect_sd, detect_meta, prefix


def validate_unet_binding(
    model: Any,
    views: dict,
    *,
    expected_count: int = EXPECTED_UNET_TENSOR_COUNT,
    expected_dtype: Optional[torch.dtype] = torch.bfloat16,
    device_prefix: str = "cuda",
) -> dict:
    """Strict 453/453 pointer-identity binding validation.

    Every bound parameter/buffer must have exact key presence, shape, BF16
    dtype, CUDA device, and identical ``data_ptr`` to its QD view.  Missing,
    unexpected/leftover, or copied tensors are rejected.  (``device_prefix``
    exists solely so offline synthetic tests can exercise the validator on
    CPU-shared-storage fakes; production uses the default 'cuda'.)
    """
    inner = getattr(model, "diffusion_model", model)
    named = dict(inner.named_parameters())
    named.update(dict(inner.named_buffers()))
    if len(named) != int(expected_count):
        raise RuntimeError(f"unet_tensor_count:{len(named)}!={expected_count}")
    same_storage = copied = unexpected_device = unexpected_dtype = leftover = 0
    ptr_map: dict = {}
    for name, tensor in named.items():
        src = views.get(name)
        if src is None:
            leftover += 1
            continue
        if tuple(tensor.shape) != tuple(src.shape):
            raise RuntimeError(f"bind_shape:{name}")
        if expected_dtype is not None and tensor.dtype != expected_dtype:
            raise RuntimeError(f"bind_dtype:{name}:{tensor.dtype}")
        if not str(tensor.device).startswith(device_prefix):
            raise RuntimeError(f"bind_device:{name}:{tensor.device}")
        if int(tensor.data_ptr()) != int(src.data_ptr()):
            copied += 1
            raise RuntimeError(f"bind_copied_storage:{name}")
        same_storage += 1
        ptr_map[name] = int(tensor.data_ptr())
    missing = sorted(set(views) - set(named))
    if missing:
        raise RuntimeError(f"bind_missing:{missing[:8]}")
    if leftover:
        raise RuntimeError(f"bind_leftover:{leftover}")
    return {
        "tensor_count": len(named),
        "same_storage_count": same_storage,
        "copied_storage_count": copied,
        "unexpected_device_count": unexpected_device,
        "unexpected_dtype_count": unexpected_dtype,
        "leftover_count": leftover,
        "ptr_map": ptr_map,
    }


def validate_qd_adoption(
    tag: str,
    modules: Iterable[Any],
    views: dict,
    *,
    device_prefix: str = "cuda",
) -> dict:
    """Fail-closed CLIP/VAE adoption proof over QD zero-copy views.

    Requires EXACT one-to-one coverage between live tensors (parameters AND
    buffers across ``modules``) and QD views, compared purely by unique
    ``data_ptr`` sets — never by transformed key names.  Fails closed unless:
    counts match AND the live-pointer set equals the view-pointer set
    (leftover/unused views are rejected, and duplicate aliases on either side
    are rejected), every matched pair agrees on EXACT shape and dtype, and
    every live tensor is CUDA-resident.  Zero adopted tensors fails closed.
    Counts returned are measured, not asserted.
    """
    tensors: list = []
    for module in modules:
        if module is None:
            continue
        inner = getattr(module, "diffusion_model", module)
        tensors.extend(inner.named_parameters())
        tensors.extend(inner.named_buffers())
    if not tensors:
        raise RuntimeError(f"{tag}_adoption_no_tensors")

    live_ptr_counts: dict[int, int] = {}
    for _name, tensor in tensors:
        ptr = int(tensor.data_ptr())
        live_ptr_counts[ptr] = live_ptr_counts.get(ptr, 0) + 1
    live_dupes = sorted(ptr for ptr, count in live_ptr_counts.items() if count > 1)
    if live_dupes:
        raise RuntimeError(f"{tag}_adoption_live_duplicate_alias:{live_dupes[:4]}")

    view_ptrs: dict[int, Any] = {}
    for view in views.values():
        ptr = int(view.data_ptr())
        if ptr in view_ptrs:
            raise RuntimeError(f"{tag}_adoption_view_duplicate_alias:{ptr}")
        view_ptrs[ptr] = view

    live_ptrs = set(live_ptr_counts)
    if len(tensors) != len(views) or live_ptrs != set(view_ptrs):
        uncovered = sorted(live_ptrs - set(view_ptrs))[:4]
        unused_views = sorted(set(view_ptrs) - live_ptrs)[:4]
        raise RuntimeError(
            f"{tag}_adoption_coverage_mismatch:"
            f"live={len(tensors)}:views={len(views)}:"
            f"uncovered={uncovered}:unused_views={unused_views}"
        )

    unexpected_device = unexpected_shape = unexpected_dtype = 0
    for name, tensor in tensors:
        view = view_ptrs[int(tensor.data_ptr())]
        if not str(tensor.device).startswith(device_prefix):
            unexpected_device += 1
            raise RuntimeError(f"{tag}_adoption_device:{name}:{tensor.device}")
        if tuple(tensor.shape) != tuple(view.shape):
            unexpected_shape += 1
            raise RuntimeError(f"{tag}_adoption_shape:{name}")
        if tensor.dtype != view.dtype:
            unexpected_dtype += 1
            raise RuntimeError(f"{tag}_adoption_dtype:{name}:{tensor.dtype}!={view.dtype}")
    return {
        "tensor_count": len(tensors),
        "view_count": len(views),
        "matched_count": len(tensors),
        "same_storage_count": len(tensors),
        "copied_storage_count": 0,
        "unexpected_device_count": unexpected_device,
        "unexpected_shape_count": unexpected_shape,
        "unexpected_dtype_count": unexpected_dtype,
        "source_dtypes": sorted({str(v.dtype) for v in views.values()}),
    }


# Conservative, model-agnostic bounds for constructor-owned tensors that may
# legitimately live OUTSIDE the adopted checkpoint scope in the cond-stage
# root (e.g. scalar logit-scale parameters/buffers created by text-encoder
# wrapper constructors).  Sized for a handful of scalars/tiny vectors only —
# orders of magnitude below any model-sized weight — so a copied checkpoint,
# a second model copy, or any bulk weight duplication outside the proven
# scope can never pass.
_CLIP_ADOPTION_OUTER_EXTRA_MAX_COUNT = 8
_CLIP_ADOPTION_OUTER_EXTRA_MAX_BYTES = 4096


def select_and_validate_qd_adoption_scope(
    tag: str,
    root: Any,
    views: dict,
    *,
    device_prefix: str = "cuda",
    max_outer_extra_count: int = _CLIP_ADOPTION_OUTER_EXTRA_MAX_COUNT,
    max_outer_extra_bytes: int = _CLIP_ADOPTION_OUTER_EXTRA_MAX_BYTES,
) -> dict:
    """Generic fail-closed CLIP checkpoint-adoption proof (wrapper-shape agnostic).

    Text-encoder wrappers nest the constructed checkpoint module under
    wrapper-specific submodules; this helper never assumes particular module
    or tensor names.  It traverses ``root`` itself plus every named submodule
    and identifies candidate modules whose recursive parameter/buffer UNIQUE
    ``data_ptr`` set exactly equals the complete QD view pointer set with
    matching counts — pure pointer identity, no model-specific naming.

    Selection rules (fail-closed):
    * At least one candidate is required.
    * All candidates hold the SAME pointer set by construction; their module
      paths must form ONE ancestor/descendant chain (the normal parent/child
      artifact of recursive ``named_parameters`` under nested wrappers).
      Disjoint equally-matching scopes are rejected as ambiguous.
    * The DEEPEST candidate (smallest load scope) is selected, then the
      existing strict :func:`validate_qd_adoption` runs on it, preserving the
      exact count/device/dtype/shape/pointer checks.

    Outer-root accounting: tensors reachable from ``root`` but outside the
    selected scope are permitted only as bounded constructor-owned extras —
    at most ``max_outer_extra_count`` tensors and at most
    ``max_outer_extra_bytes`` aggregate bytes (defaults sized for scalar
    logit scales, far below model weights).  Duplicate/aliased extras and any
    excess fail closed.  Every QD pointer must appear in BOTH the root and
    the selected scope; missing, copied, or unused QD views always fail
    closed.  Returns strict-adoption telemetry plus selected-scope and
    outer-extra summaries.
    """
    if root is None:
        raise RuntimeError(f"{tag}_adoption_root_missing")
    if not views:
        raise RuntimeError(f"{tag}_adoption_no_views")

    # QD view pointers must be unique and nonempty.
    view_ptrs: dict[int, Any] = {}
    for view in views.values():
        ptr = int(view.data_ptr())
        if ptr in view_ptrs:
            raise RuntimeError(f"{tag}_adoption_view_duplicate_alias:{ptr}")
        view_ptrs[ptr] = view
    view_ptr_set = set(view_ptrs)

    def _collect(module: Any) -> dict[str, Any]:
        # Recursive parameters + buffers (torch dedups repeated registrations
        # by default; a defensive alias check still runs on outer extras).
        named: dict[str, Any] = {}
        for name, tensor in module.named_parameters():
            named[name] = tensor
        for name, tensor in module.named_buffers():
            named.setdefault(name, tensor)
        return named

    def _is_ancestor(ancestor: str, descendant: str) -> bool:
        if ancestor == "":
            return True  # root is an ancestor of every submodule path
        return descendant.startswith(ancestor + ".")

    # Traverse root ("") plus every named submodule; pointer-set candidates.
    candidates: list[tuple[str, Any]] = []
    for path, module in root.named_modules():
        tensors = _collect(module)
        if len(tensors) != len(view_ptr_set):
            continue
        if {int(t.data_ptr()) for t in tensors.values()} == view_ptr_set:
            candidates.append((str(path), module))
    if not candidates:
        raise RuntimeError(f"{tag}_adoption_no_scope_matches_view_pointer_set")

    ordered = sorted(candidates, key=lambda item: (item[0].count("."), item[0]))
    for (shallow_path, _), (deep_path, _) in zip(ordered, ordered[1:]):
        if not _is_ancestor(shallow_path, deep_path):
            raise RuntimeError(
                f"{tag}_adoption_ambiguous_disjoint_scopes:{[p for p, _ in ordered]}"
            )
    selected_path, selected_module = ordered[-1]

    # Strict adoption proof on the selected checkpoint scope (exact
    # count/device/dtype/shape/pointer checks preserved unchanged).
    adoption = validate_qd_adoption(
        tag, [selected_module], views, device_prefix=device_prefix
    )

    # Root-level containment: every QD pointer must be live somewhere in the
    # root (never missing/copied away from the transported buffer).
    root_tensors = _collect(root)
    root_ptr_set = {int(t.data_ptr()) for t in root_tensors.values()}
    missing_in_root = sorted(view_ptr_set - root_ptr_set)
    if missing_in_root:
        raise RuntimeError(f"{tag}_adoption_view_missing_from_root:{missing_in_root[:4]}")

    # Outer extras: root tensors beyond the selected checkpoint scope.
    extra_names: list[str] = []
    extra_ptrs: set[int] = set()
    extra_devices: set[str] = set()
    extra_dtypes: set[str] = set()
    extra_bytes = 0
    for name, tensor in root_tensors.items():
        ptr = int(tensor.data_ptr())
        if ptr in view_ptr_set:
            continue
        if ptr in extra_ptrs:
            raise RuntimeError(f"{tag}_adoption_outer_extra_alias:{name}")
        extra_ptrs.add(ptr)
        extra_names.append(str(name))
        extra_bytes += int(tensor.numel()) * int(tensor.element_size())
        extra_devices.add(str(tensor.device))
        extra_dtypes.add(str(tensor.dtype))
    if len(extra_names) > int(max_outer_extra_count):
        raise RuntimeError(
            f"{tag}_adoption_outer_extra_count:{len(extra_names)}>"
            f"{int(max_outer_extra_count)}:{sorted(extra_names)[:8]}"
        )
    if extra_bytes > int(max_outer_extra_bytes):
        raise RuntimeError(
            f"{tag}_adoption_outer_extra_bytes:{extra_bytes}>{int(max_outer_extra_bytes)}"
        )

    return {
        **adoption,
        "selected_scope": selected_path,
        "scope_candidates": [p for p, _ in ordered],
        "adopted_count": adoption["matched_count"],
        "view_count": len(views),
        "outer_extra_count": len(extra_names),
        "outer_extra_bytes": extra_bytes,
        "outer_extra_names": extra_names,
        "outer_extra_devices": sorted(extra_devices),
        "outer_extra_dtypes": sorted(extra_dtypes),
        "outer_extra_limits": {
            "max_count": int(max_outer_extra_count),
            "max_bytes": int(max_outer_extra_bytes),
        },
    }


# ── Dynamic-assign preflight / uniform-dtype derivation (fail-closed) ─────


def require_dynamic_core_model_patcher(*, tag: str) -> Any:
    """Fail-closed CLIP/VAE preflight: upstream ``comfy.model_patcher.
    CoreModelPatcher`` must currently BE ``ModelPatcherDynamic`` (dynamic VRAM
    enabled at ComfyUI startup, main.py rebinds the symbol).  Only class
    identity is read — no global monkey-patching, no fallback.  Returns the
    verified CoreModelPatcher class."""
    import comfy.model_patcher as mp  # upstream ComfyUI module (allowed import)

    core = getattr(mp, "CoreModelPatcher", None)
    dynamic = getattr(mp, "ModelPatcherDynamic", None)
    if core is None or dynamic is None or core is not dynamic:
        raise RuntimeError(f"{tag}_dynamic_core_model_patcher_required")
    return core


def require_dynamic_patcher_instance(*, tag: str, patcher: Any) -> dict:
    """Fail-closed post-construction check: the constructed patcher must
    report ``is_dynamic()`` True before adoption is accepted.  Returns the
    recorded patcher class identity for telemetry."""
    if patcher is None:
        raise RuntimeError(f"{tag}_patcher_missing")
    checker = getattr(patcher, "is_dynamic", None)
    if not callable(checker) or not bool(checker()):
        raise RuntimeError(f"{tag}_patcher_not_dynamic:{type(patcher).__name__}")
    return {"patcher_class": type(patcher).__name__, "is_dynamic": True}


def uniform_source_dtype(views: dict, *, tag: str) -> torch.dtype:
    """Single uniform dtype across QD zero-copy views; fail closed on an
    empty state dict or mixed dtypes."""
    if not views:
        raise RuntimeError(f"{tag}_source_state_dict_empty")
    dtypes = {view.dtype for view in views.values()}
    if len(dtypes) != 1:
        raise RuntimeError(f"{tag}_non_uniform_source_dtype:{sorted(str(d) for d in dtypes)}")
    return next(iter(dtypes))


def uniform_source_dtype_across(state_dicts: list, *, tag: str) -> torch.dtype:
    """Exact uniform source dtype across ALL checkpoints' QD views; fail
    closed on empty input, any per-checkpoint mix, or cross-checkpoint
    mismatch (mixed-dtype opt-in does not exist yet)."""
    if not state_dicts:
        raise RuntimeError(f"{tag}_source_state_dicts_empty")
    dtype = uniform_source_dtype(state_dicts[0], tag=tag)
    for index, sd in enumerate(state_dicts[1:], start=1):
        other = uniform_source_dtype(sd, tag=tag)
        if other != dtype:
            raise RuntimeError(
                f"{tag}_cross_checkpoint_dtype_mismatch:[0]={dtype}:[{index}]={other}"
            )
    return dtype


def resolve_clip_type(name: str) -> Any:
    """Resolve a ``comfy.sd.CLIPType`` member by normalized name (case- and
    dash-insensitive).  NO silent fallback: unknown names fail closed."""
    import comfy.sd  # upstream ComfyUI module (allowed import)

    normalized = str(name).strip().upper().replace("-", "_")
    member = getattr(comfy.sd.CLIPType, normalized, None)
    if member is None:
        raise RuntimeError(f"unknown_clip_type:{name}")
    return member


async def golden_unet_load(session: GoldenSession) -> Any:
    """UNET Candidate A: single-source QD payload -> real Lumina2/NextDiT
    skeleton -> CoreModelPatcher -> ``model.load_model_weights(dict(views),
    "", assign=True)`` -> strict 453/453 pointer-identity validation.

    Never calls ``model.to``, native ``load_torch_file``, an original-loader
    fallback, clone, CPU state_dict rematerialization, a second read, a second
    H2D, or a second CUDA representation.  Header/meta tensors drive config
    detection BEFORE the single payload read; scaled FP8 / non-uniform /
    unsupported dtypes are rejected.
    """
    rec = session.recorder
    rec.begin_stage("golden_unet_load")
    try:
        import comfy.model_detection as md  # upstream
        import comfy.model_management as mm  # upstream
        import comfy.model_patcher as mp  # upstream
        import comfy.utils as cu  # upstream

        contract = session.contract
        unet_path = session.model_paths["unet"]

        parsed = parse_safetensors_header(unet_path)
        if parsed.get("status") != "ok":
            raise RuntimeError(f"unet_header_invalid:{parsed.get('reason')}")
        header = parsed["header"]
        metadata = header.get("__metadata__")
        entries = build_header_tensor_map(header)
        if any(".scaled_fp8" in name for name, *_ in entries):
            raise RuntimeError("scaled_fp8_rejected")
        dtype_names = {dtype_str for _, dtype_str, *_ in entries}
        if len(dtype_names) != 1:
            raise RuntimeError(f"non_uniform_dtype:{sorted(dtype_names)}")
        view_dtype = _TORCH_DTYPE.get(next(iter(dtype_names)))
        if view_dtype is None:
            raise RuntimeError("unknown_dtype")

        meta_sd = {
            name: torch.empty(tuple(shape), dtype=_TORCH_DTYPE[dtype_str], device="meta")
            for name, dtype_str, shape, _s, _l in entries
        }
        prefix_fn = getattr(md, "unet_prefix_from_state_dict", None)
        strip_fn = getattr(cu, "state_dict_prefix_replace", None)
        config_fn = getattr(md, "model_config_from_unet", None)
        quant_fn = getattr(cu, "convert_old_quants", None)
        if not all(callable(x) for x in (prefix_fn, strip_fn, config_fn)):
            raise RuntimeError("missing_comfy_helper")
        detect_sd, detect_meta, prefix = _native_detection_input(
            meta_sd, metadata, prefix_fn, strip_fn, quant_fn
        )
        model_config = config_fn(detect_sd, "", metadata=detect_meta)
        if model_config is None:
            raise RuntimeError("model_config_none")
        rec.event(
            "unet_model_config_detect",
            arch=type(model_config).__name__,
            prefix=str(prefix),
            raw_key_count=len(meta_sd),
        )

        selected = mm.unet_dtype(supported_dtypes=list(model_config.supported_inference_dtypes))
        if selected != view_dtype:
            raise RuntimeError(f"inference_dtype_mismatch:{selected}!={view_dtype}")
        manual_cast = mm.unet_manual_cast(
            selected, mm.get_torch_device(), model_config.supported_inference_dtypes
        )
        model_config.set_inference_dtype(selected, manual_cast)
        # This identity must hold before constructing even the meta skeleton;
        # otherwise assign=True adoption is not a trustworthy contract.
        dynamic_core = require_dynamic_core_model_patcher(tag="unet")
        allocation_checkpoints: list[dict] = []
        peak_supported = callable(getattr(torch.cuda, "max_memory_allocated", None)) and callable(
            getattr(torch.cuda, "reset_peak_memory_stats", None)
        )
        if not peak_supported:
            raise RuntimeError("unet_peak_measurement_api_unavailable")

        def checkpoint(name: str) -> dict:
            if not torch.cuda.is_available():
                raise RuntimeError("cuda_unavailable")
            synchronize = getattr(torch.cuda, "synchronize", None)
            if callable(synchronize):
                synchronize()
            allocated = int(torch.cuda.memory_allocated())
            peak = int(torch.cuda.max_memory_allocated()) if peak_supported else allocated
            value = {
                "name": str(name),
                "allocated_bytes": allocated,
                "reserved_bytes": int(
                    getattr(torch.cuda, "memory_reserved", lambda: 0)()
                ),
                "peak_allocated_bytes": peak,
                "peak_measurement_supported": peak_supported,
            }
            allocation_checkpoints.append(value)
            rec.event(
                "unet_cuda_allocation_checkpoint",
                checkpoint_name=value["name"],
                allocated_bytes=value["allocated_bytes"],
                reserved_bytes=value["reserved_bytes"],
                peak_allocated_bytes=value["peak_allocated_bytes"],
                peak_measurement_supported=value["peak_measurement_supported"],
            )
            return value

        def reset_peak_stats() -> None:
            reset = getattr(torch.cuda, "reset_peak_memory_stats", None)
            if callable(reset):
                synchronize = getattr(torch.cuda, "synchronize", None)
                if callable(synchronize):
                    synchronize()
                reset()

        reset_peak_stats()
        before_skeleton = checkpoint("before_skeleton")
        # Build only a meta skeleton.  The retained QD CUDA owner is the sole
        # physical weight allocation; assign=True later adopts those views.
        model = model_config.get_model(detect_sd, "", device=torch.device("meta"))
        patcher = mp.CoreModelPatcher(
            model, load_device=mm.get_torch_device(), offload_device=mm.unet_offload_device()
        )
        if type(patcher) is not dynamic_core:
            raise RuntimeError(f"unet_dynamic_patcher_identity:{type(patcher).__name__}")
        after_skeleton = checkpoint("after_skeleton")
        rec.event("unet_skeleton_patcher_created", arch=type(model_config).__name__)

        # The single QD physical producer into CUDA (one read, one H2D).
        reset_peak_stats()
        with _golden_qd_transport_arm_scope(getattr(session, "qd_transport_arm", "legacy")):
            transport = read_file_qd_gpu(
                unet_path,
                role="unet",
                qd=contract.qd,
                block_bytes=contract.block_bytes,
            )
        views = {
            k[len(prefix):] if prefix and k.startswith(prefix) else k: v
            for k, v in transport["sd"].items()
        }
        session.unet_owner = transport["owner"]
        session.register_qd_owner(session.unet_owner)
        after_qd = checkpoint("after_qd_destination")
        rec.event("unet_qd_owner_created", role="unet", gpu_bytes=transport["stats"]["gpu_bytes"])
        skeleton_peak_delta = None
        if peak_supported:
            skeleton_peak_delta = max(
                int(after_skeleton["peak_allocated_bytes"])
                - int(before_skeleton["allocated_bytes"]),
                0,
            )
            if skeleton_peak_delta >= int(transport["stats"]["gpu_bytes"]):
                raise RuntimeError(f"unet_skeleton_model_sized_allocation:{skeleton_peak_delta}")

        # load_model_weights POPS keys from the dict it receives; pass a copy
        # so `views` survives for the identity measurement below.
        reset_peak_stats()
        result = model.load_model_weights(dict(views), "", assign=True)
        missing = getattr(result, "missing_keys", None) if result is not None else None
        if missing:
            raise RuntimeError(f"unet_missing_keys:{list(missing)[:8]}")

        identity = validate_unet_binding(model, views, expected_count=contract.expected_unet_tensor_count)
        after_adoption = checkpoint("after_assign_adoption")
        post_qd_delta = int(after_adoption["allocated_bytes"]) - int(after_qd["allocated_bytes"])
        if post_qd_delta >= int(transport["stats"]["gpu_bytes"]):
            raise RuntimeError(f"unet_second_model_sized_allocation:{post_qd_delta}")
        adoption_peak_delta = None
        if peak_supported:
            adoption_peak_delta = max(
                int(after_adoption["peak_allocated_bytes"]) - int(after_qd["allocated_bytes"]),
                0,
            )
            if adoption_peak_delta >= int(transport["stats"]["gpu_bytes"]):
                raise RuntimeError(f"unet_peak_model_sized_allocation:{adoption_peak_delta}")
        session.unet_cuda_allocation_checkpoints = allocation_checkpoints
        transport["stats"]["cuda_allocation_checkpoints"] = list(allocation_checkpoints)
        qd_quiescence = _require_transport_quiescence(transport, tag="unet")
        rec.event("unet_storage_identity", **{k: v for k, v in identity.items() if k != "ptr_map"})
        session.patcher = patcher
        try:
            setattr(patcher, "_golden_qd_owner", transport["owner"])
        except Exception:
            pass
        rec.end_stage(
            "golden_unet_load",
            ready=True,
            assigned_count=len(views),
            same_storage_count=identity["same_storage_count"],
            assign_mode="assign_true",
            source_read_count=int(transport["stats"]["source_read_count"]),
            h2d_completed_bytes=int(transport["stats"]["h2d_completed_bytes"]),
            qd_quiescence=qd_quiescence,
            cuda_allocation_checkpoints=allocation_checkpoints,
            post_qd_allocation_delta_bytes=post_qd_delta,
            skeleton_peak_delta_bytes=skeleton_peak_delta,
            adoption_peak_delta_bytes=adoption_peak_delta,
            peak_measurement_supported=peak_supported,
            transport_stats=build_qd_transport_diagnostics(transport["stats"]),
        )
        return patcher
    except BaseException as exc:
        rec.fail_stage("golden_unet_load", exc)
        raise


async def golden_sampler_prepare(session: GoldenSession) -> dict:
    """Execute, serially, every sampler dependency / model wrapper /
    CacheDiT / external preparatory node needed by the canonical sampler,
    stopping before the sampler node itself.  UNET and conditioning are
    already seeded, so graph dependencies consume the exact Golden objects."""
    rec = session.recorder
    rec.begin_stage("golden_sampler_prepare")
    try:
        runner = session.runner
        node_map = session.node_map
        # Seed the already-produced Golden objects in the native socket-major
        # cache shape (one socket, one item: [[value]]) so loader/encode nodes
        # can never execute or reread.  Idempotent with the clip_forward seed.
        runner.seed(node_map.clip_loader_id, [[session.clip]])
        runner.seed(node_map.clip_encode_id, [[session.conditioning]])
        runner.seed(node_map.unet_loader_id, [[session.patcher]])

        unet_ready_ns = session.recorder.intervals["golden_unet_load"].ready_monotonic_ns
        cuda_before = int(torch.cuda.memory_allocated())
        patcher_identity_before = id(session.patcher)

        runner.begin_scope(set())  # only 'prepare' classes permitted
        executed_start = len(runner.executed)
        try:
            await runner.run_closure(node_map.sampler_id, include_target=False)
        finally:
            runner.end_scope()
        _assert_runner_quiescence(runner)

        cuda_delta = int(torch.cuda.memory_allocated()) - cuda_before
        prep_executed = runner.executed[executed_start:]
        source_reads = sum(
            1 for item in prep_executed if classify_node(item["class_type"]) in HEAVY_NODE_STAGES.values()
        )
        if source_reads:
            executed_heavy = [
                (item["node_id"], item["class_type"], item["stage_class"])
                for item in prep_executed
                if classify_node(item["class_type"]) in HEAVY_NODE_STAGES.values()
            ]
            raise RuntimeError(
                f"prepare_forbidden_heavy_executions:{source_reads}:{executed_heavy!r}"
            )
        if cuda_delta > 64 * 1024 * 1024:
            raise RuntimeError(f"prepare_large_cuda_allocation:{cuda_delta}")
        if id(session.patcher) != patcher_identity_before:
            raise RuntimeError("prepare_patcher_identity_changed")
        # Measured evidence only: the heavy-class execution ban above is exact;
        # the CUDA delta is a bounded sanity check, NOT proof that zero hidden
        # weight movement occurred — do not overclaim.
        details = {
            "executed_nodes": [item["node_id"] for item in prep_executed],
            "cuda_alloc_delta_bytes_bounded_check": cuda_delta,
            "patcher_identity": patcher_identity_before,
        }
        if unet_ready_ns is not None:
            prep_entry_ns = session.recorder.intervals["golden_sampler_prepare"].entry_monotonic_ns
            rec.event(
                "unet_ready_to_prep_entry_gap_ns",
                gap_ns=int(prep_entry_ns - unet_ready_ns),
            )
        rec.end_stage("golden_sampler_prepare", ready=True, **details)
        return details
    except BaseException as exc:
        rec.fail_stage("golden_sampler_prepare", exc)
        raise


async def golden_sampling(session: GoldenSession) -> Any:
    """Execute the exact canonical sampler node through the serial runner,
    preserving all workflow inputs (RES4LYF/CacheDiT/model wrappers/scheduler/
    steps/seed) and deterministic math.  Await complete return; no VAE work."""
    rec = session.recorder
    rec.begin_stage("golden_sampling")
    requested_attention_backend = getattr(session.request, "attention_backend", None)
    if requested_attention_backend is not None:
        requested_attention_backend = normalize_attention_backend(
            requested_attention_backend
        )
    diagnostics = (
        GoldenSamplingDiagnostics(
            rec,
            sampler_id=session.node_map.sampler_id,
            sampler_class=session.contract.sampler_class_type,
        )
        if _sampling_diagnostics_enabled()
        else None
    )
    session.sampling_diagnostics = diagnostics
    rec.sampling_diagnostics = diagnostics
    try:
        runner = session.runner
        node_map = session.node_map
        attention_patcher = _sampler_bound_patcher(session)
        if diagnostics is not None:
            diagnostics.begin(session)
            diagnostics.install_model_hooks(session.patcher)
            runner.sampling_diagnostics = diagnostics
        try:
            runtime_executor = importlib.import_module("comfymodal_runtime.runtime_executor")
            _sampling_wrapper_installed = runtime_executor.ensure_sampling_timing_wrapper(
                session.patcher
            )
            rec.event(
                "sampling_wrapper_install",
                installed=bool(_sampling_wrapper_installed),
                patcher_type=type(session.patcher).__name__,
                source="golden_sampling_runner",
            )
        except Exception as exc:
            rec.event(
                "sampling_wrapper_install",
                installed=False,
                patcher_type=type(session.patcher).__name__,
                source="golden_sampling_runner",
                error=type(exc).__name__,
            )
            try:
                print(
                    "[v2.sampling_deep_profile] event=runner_install_failed "
                    f"error={type(exc).__name__}",
                    flush=True,
                )
            except Exception:
                pass
        # GoldenSerialRunner calls the node method directly, so ComfyUI's
        # SAMPLER_SAMPLE wrapper can be installed successfully while never
        # seeing this invocation.  In that canonical path, bridge the same
        # existing lifecycle explicitly instead of changing sampler inputs or
        # execution order.  The active request trace is authoritative; a
        # profile already owned by the production wrapper is left alone so a
        # wrapper transition cannot create two profiles for one invocation.
        deep_profile = None
        deep_profile_trace = None
        deep_profile_sdp = None
        sampling_start_event = None
        profile_steps = 0
        sampling_profile_skipped = False
        sampling_profile_setup_failed = False
        trace_profile_count_before = 0
        try:
            try:
                deep_profile_sdp = importlib.import_module(
                    "comfymodal_runtime.sampling_deep_profile"
                )
                profile_level = deep_profile_sdp.resolve_profile_level()
                if profile_level in {"steps", "blocks"}:
                    model_preload = importlib.import_module("comfymodal_runtime.model_preload")
                    deep_profile_trace = model_preload._ACTIVE_REQUEST_TRACE.get()
                    if deep_profile_trace is None:
                        runtime_trace_module = importlib.import_module("comfymodal_runtime.trace")
                        deep_profile_trace = runtime_trace_module.RuntimeTrace(
                            request_id=str(session.request.request_id),
                            process="golden_sampling",
                        )
                    trace_profile_count_before = sum(
                        1
                        for event in getattr(deep_profile_trace, "events", ())
                        if getattr(event, "name", None) == deep_profile_sdp.EVENT_NAME
                    )
                    current_profile = None
                    try:
                        current_profile = deep_profile_sdp._CURRENT_PROFILE.get()
                    except Exception:
                        pass
                    # _PATCH_OWNER covers a concurrent production invocation;
                    # _CURRENT_PROFILE covers the wrapper in this context.
                    if (
                        current_profile is not None
                        or getattr(deep_profile_sdp, "_PATCH_OWNER", None) is not None
                    ):
                        sampling_profile_skipped = True
                    else:
                        sampler_inputs = (
                            session.request.prompt.get(node_map.sampler_id, {}).get("inputs", {})
                        )
                        requested_steps = sampler_inputs.get("steps")
                        if _is_link(requested_steps):
                            linked_entry = runner.cache.get(str(requested_steps[0]))
                            if linked_entry is not None:
                                socket = int(requested_steps[1])
                                linked_outputs = getattr(linked_entry, "outputs", None)
                                if linked_outputs is not None and socket < len(linked_outputs):
                                    requested_steps = linked_outputs[socket]
                        def _positive_int(value: Any, depth: int = 0) -> int:
                            if depth > 4:
                                return 0
                            if isinstance(value, int) and not isinstance(value, bool) and value > 0:
                                return int(value)
                            if isinstance(value, (list, tuple)):
                                for item in value:
                                    resolved = _positive_int(item, depth + 1)
                                    if resolved:
                                        return resolved
                            return 0
                        profile_steps = _positive_int(requested_steps)
                        sampling_start_event = deep_profile_trace.emit(
                            "sampling_start",
                            phase="execution",
                            metadata={
                                "node_id": str(node_map.sampler_id),
                                "node_class": str(session.contract.sampler_class_type),
                                "steps": profile_steps,
                                "source": "golden_sampling_runner",
                            },
                        )
                        deep_profile = deep_profile_sdp.begin_sampling_profile(
                            deep_profile_trace,
                            level=profile_level,
                            node_id=str(node_map.sampler_id),
                            node_class=str(session.contract.sampler_class_type),
                            steps=profile_steps,
                            sampling_start_monotonic_ns=sampling_start_event.monotonic_ns,
                            sampling_start_wall_unix_ns=sampling_start_event.wall_unix_ns,
                            patcher=session.patcher,
                            requested_backend=requested_attention_backend,
                        )
            except Exception as profile_setup_exc:
                # Deep profiling is measurement-only.  In particular, an import,
                # configuration, trace-metadata, or profiler setup failure must
                # never change the canonical sampler result or escape into it.
                deep_profile = None
                sampling_profile_skipped = True
                sampling_profile_setup_failed = True
                try:
                    rec.event(
                        "sampling_deep_profile_setup_failed",
                        source="golden_sampling_runner",
                        profiling_disabled=True,
                        measurement_only=True,
                        error=type(profile_setup_exc).__name__,
                    )
                except Exception:
                    pass

            scope_started = False
            attention_scope_state: dict[str, Any] | None = None
            try:
                runner.begin_scope({"sampling"})
                scope_started = True
                try:
                    if requested_attention_backend is None:
                        # Preserve the historical omission/no-override route:
                        # KJNodes or another already-installed sampler-bound
                        # override remains authoritative for this run.
                        executed = await runner.run_closure(
                            node_map.sampler_id, include_target=True
                        )
                    else:
                        with attention_backend_scope(
                            attention_patcher,
                            requested_attention_backend,
                        ) as attention_scope_state:
                            executed = await runner.run_closure(
                                node_map.sampler_id, include_target=True
                            )
                finally:
                    if (
                        deep_profile_trace is not None
                        and sampling_start_event is not None
                        and sampling_profile_setup_failed
                    ):
                        # The start boundary is authoritative even when profile
                        # setup fails.  Close only the boundary this runner
                        # emitted; an owning production profile never reaches
                        # this path because it skips the Golden bridge above.
                        try:
                            deep_profile_trace.emit(
                                "sampling_end",
                                phase="execution",
                                metadata={
                                    "node_id": str(node_map.sampler_id),
                                    "node_class": str(session.contract.sampler_class_type),
                                    "steps": profile_steps,
                                    "duration_ms": round(
                                        (time.monotonic_ns() - sampling_start_event.monotonic_ns)
                                        / 1_000_000,
                                        3,
                                    ),
                                    "source": "golden_sampling_runner",
                                    "profiling_setup_failed": True,
                                },
                            )
                        except Exception:
                            # Preserve the sampler result/exception if the
                            # measurement-only close emission also fails.
                            pass
                    elif deep_profile_trace is not None and not sampling_profile_skipped:
                        sampling_end_event = None
                        try:
                            sampling_end_event = deep_profile_trace.emit(
                                "sampling_end",
                                phase="execution",
                                metadata={
                                    "node_id": str(node_map.sampler_id),
                                    "node_class": str(session.contract.sampler_class_type),
                                    "steps": profile_steps,
                                    "duration_ms": round(
                                        (time.monotonic_ns() - sampling_start_event.monotonic_ns)
                                        / 1_000_000,
                                        3,
                                    ),
                                    "source": "golden_sampling_runner",
                                },
                            )
                        except Exception:
                            # Preserve the sampler exception and let the existing
                            # lifecycle record a failed authoritative emission.
                            pass
                        if deep_profile is not None:
                            try:
                                if sampling_end_event is not None:
                                    end_mono = sampling_end_event.monotonic_ns
                                    end_wall = sampling_end_event.wall_unix_ns
                                    end_emission_failed = False
                                else:
                                    end_mono = time.monotonic_ns()
                                    end_wall = time.time_ns()
                                    end_emission_failed = True
                                artifact = deep_profile_sdp.finalize_sampling_profile(
                                    deep_profile,
                                    deep_profile_trace,
                                    sampling_end_monotonic_ns=end_mono,
                                    sampling_end_wall_unix_ns=end_wall,
                                    sampling_end_emission_failed=end_emission_failed,
                                )
                            except Exception as profile_exc:
                                artifact = {
                                    "schema_version": getattr(deep_profile_sdp, "SCHEMA_VERSION", 1),
                                    "level": profile_level,
                                    "status": "finalize_failed",
                                    "errors": [f"finalize_failed:{type(profile_exc).__name__}"],
                                }
                            validate_attention_backend_diagnostics(
                                requested_attention_backend,
                                artifact,
                            )
                            # sampling_deep_profile.finalize_sampling_profile emits
                            # the RuntimeTrace event.  Mirror its bounded JSON
                            # payload into the authoritative Golden recorder.
                            _record_golden_sampling_profile(
                                rec,
                                artifact,
                                level=profile_level,
                                source="golden_sampling_runner",
                                schema_version=getattr(deep_profile_sdp, "SCHEMA_VERSION", 1),
                            )
                        elif deep_profile_sdp is not None:
                            # A lifecycle rejection is itself fail-closed.  Do not
                            # manufacture a second profile; an owning production
                            # wrapper, if present, is responsible for its event.
                            pass
                    elif (
                        deep_profile_trace is not None
                        and sampling_profile_skipped
                        and not sampling_profile_setup_failed
                    ):
                        # If the production wrapper owned this invocation, copy
                        # only a newly emitted profile into the Golden recorder;
                        # never finalize or emit a second one here.
                        profile_events = [
                            event
                            for event in getattr(deep_profile_trace, "events", ())[0:]
                            if getattr(event, "name", None) == deep_profile_sdp.EVENT_NAME
                        ]
                        if len(profile_events) > trace_profile_count_before:
                            metadata = profile_events[-1].metadata
                            _record_golden_sampling_profile(
                                rec,
                                dict(metadata),
                                level="unknown",
                                source="production_sampler_wrapper",
                                schema_version=getattr(deep_profile_sdp, "SCHEMA_VERSION", 1),
                            )
            finally:
                if scope_started:
                    runner.end_scope()
            if requested_attention_backend is None:
                rec.event(
                    "attention_backend_selection",
                    requested_backend=None,
                    selected_callable="existing_patcher_override",
                    calls=None,
                    override_applied=False,
                    source="active_unet_model_patcher_transformer_options",
                )
            else:
                if attention_scope_state is None:
                    raise AttentionBackendValidationError("attention_backend_scope_missing")
                rec.event(
                    "attention_backend_selection",
                    requested_backend=requested_attention_backend,
                    selected_callable=attention_scope_state["selected_callable"],
                    calls=attention_scope_state["calls"],
                    source="active_unet_model_patcher_transformer_options",
                )
                _require_attention_backend_invocation(
                    requested_attention_backend,
                    attention_scope_state,
                )
        finally:
            # The sampling scope is closed by the inner finally above.  Keep
            # this outer finally as the diagnostics/lifecycle boundary, but do
            # not close the same runner scope a second time.
            pass
        _assert_runner_quiescence(runner)
        sampler_classes = [sc for _n, _c, sc in executed if sc == "sampling"]
        if not sampler_classes:
            raise RuntimeError("sampler_node_did_not_execute")
        entry = runner.cache.get(node_map.sampler_id)
        if entry is None or not entry.outputs:
            raise RuntimeError("sampler_output_missing")
        sampled = entry.outputs
        session.images_pending_latent = sampled
        if diagnostics is not None:
            try:
                diagnostics.finish_sampling(session.patcher, ok=True)
            except Exception as diag_exc:
                diagnostics._event("diagnostics_read_failed", error=type(diag_exc).__name__)
            finally:
                diagnostics.cleanup()
        rec.end_stage("golden_sampling", ready=True, sampling_nodes=len(sampler_classes))
        return sampled
    except BaseException as exc:
        if diagnostics is not None:
            try:
                diagnostics.finish_sampling(session.patcher, ok=False)
            except Exception as diag_exc:
                diagnostics._event("diagnostics_read_failed", error=type(diag_exc).__name__)
            finally:
                diagnostics.cleanup()
        rec.fail_stage("golden_sampling", exc)
        raise


async def golden_sampler_tail(session: GoldenSession) -> dict:
    """Narrow single-use process-lifetime-safe historical equivalent of the
    post-sampling tail.

    EVIDENCE GAP (J1/O4): the historical J1/O4 source bodies for this tail
    were not recoverable at implementation time, so the exact historical
    behavior cannot be reproduced line-for-line.  This stage therefore does
    ONLY bounded bookkeeping: it closes sampler-local tiny resources/progress
    state and records diagnostics.  It performs NO full GC, NO model unload,
    NO ``torch.cuda.empty_cache()``, and NO allocator purge; broad cleanup is
    never silently invoked.
    """
    rec = session.recorder
    rec.begin_stage("golden_sampler_tail")
    try:
        diagnostics = {
            "executed_node_count": len(session.runner.executed),
            "ui_output_nodes": sorted(session.runner.ui_outputs.keys()),
            "evidence_gap": "J1/O4 tail source bodies unrecovered; bounded bookkeeping only",
        }
        rec.end_stage("golden_sampler_tail", ready=True, **diagnostics)
        return diagnostics
    except BaseException as exc:
        rec.fail_stage("golden_sampler_tail", exc)
        raise


async def golden_vae_load(session: GoldenSession) -> Any:
    """Resolve ``ae.safetensors`` and use the same serial QD physical transport;
    construct the real upstream VAE from the already-loaded state dict with
    correct keys/device/dtype and retained owner lifetime.  A dynamic
    CoreModelPatcher is required (fail-closed, before construction) and the
    explicit exact source dtype makes upstream's ``.to(vae_dtype)`` a no-op so
    the strict pointer proof can only pass on zero-copy adoption.  The
    safetensors metadata parsed during the INITIAL transport is reused — the
    VAE never rereads its header/payload after transport.  Zero fallback, zero
    second read; all loader work joined before READY."""
    rec = session.recorder
    rec.begin_stage("golden_vae_load")
    diagnostics_enabled = stage_diagnostics_enabled()
    stage_start_ns = time.perf_counter_ns() if diagnostics_enabled else None
    page_faults_before = _process_page_faults() if diagnostics_enabled else None
    memory_before = (
        {"host": _host_memory_visibility(), "cuda": _allocator_state()}
        if diagnostics_enabled else None
    )
    components: list[dict[str, Any]] = []
    try:
        import comfy.sd  # upstream

        contract = session.contract
        transport_start_ns = time.perf_counter_ns() if diagnostics_enabled else None
        with _golden_qd_transport_arm_scope(getattr(session, "qd_transport_arm", "legacy")):
            transport = read_file_qd_gpu(
                session.model_paths["vae"],
                role="vae",
                qd=contract.qd,
                block_bytes=contract.block_bytes,
            )
        transport_end_ns = time.perf_counter_ns() if diagnostics_enabled else None
        if diagnostics_enabled:
            components.append({
                "name": "qd_transport",
                "start_ns": transport_start_ns,
                "end_ns": transport_end_ns,
                "scope": "enclosing_transport_wall",
                "non_additive": True,
            })
        views = transport["sd"]
        owner = transport["owner"]
        session.vae_owner = owner
        session.register_qd_owner(owner)
        rec.event("vae_qd_owner_created", role="vae", gpu_bytes=transport["stats"]["gpu_bytes"])

        # Fail-closed preflight: the dynamic CoreModelPatcher must be active
        # BEFORE construction — upstream VAE builds its patcher from
        # CoreModelPatcher and derives load_state_dict(assign=) from
        # patcher.is_dynamic(), which is what makes weight adoption zero-copy.
        construction_start_ns = time.perf_counter_ns() if diagnostics_enabled else None
        require_dynamic_core_model_patcher(tag="vae")
        source_dtype = uniform_source_dtype(views, tag="vae")

        # Metadata comes from the initial transport parse — no reread.
        metadata = transport.get("header_metadata")
        device = torch.device("cuda", torch.cuda.current_device())
        # Explicit exact source dtype/device: upstream's first_stage_model
        # .to(vae_dtype) becomes a no-op relative to the final adopted state,
        # and assign=True binds parameters to the QD views directly.  The
        # strict pointer proof below fails if anything moved or copied.
        vae = comfy.sd.VAE(sd=views, device=device, dtype=source_dtype, metadata=metadata)
        vae.throw_exception_if_invalid()
        construction_end_ns = time.perf_counter_ns() if diagnostics_enabled else None
        if diagnostics_enabled:
            components.append({
                "name": "skeleton_patcher_construction",
                "start_ns": construction_start_ns,
                "end_ns": construction_end_ns,
                "scope": "constructor_and_dynamic_patcher_preflight",
                "non_additive": True,
            })
        rec.event(
            "vae_patcher_identity",
            **require_dynamic_patcher_instance(tag="vae", patcher=getattr(vae, "patcher", None)),
        )

        first_stage = getattr(vae, "first_stage_model", None)
        params = list(first_stage.parameters()) if first_stage is not None else []
        if not params:
            raise RuntimeError("vae_no_parameters")
        bad_device = [str(p.device) for p in params if not str(p.device).startswith("cuda")]
        if bad_device:
            raise RuntimeError(f"vae_param_device:{bad_device[:4]}")
        working = {str(dt) for dt in getattr(vae, "working_dtypes", [])}
        if working and str(params[0].dtype) not in working:
            raise RuntimeError(f"vae_param_dtype:{params[0].dtype} not in {working}")
        if diagnostics_enabled:
            components.append({
                "name": "dtype_device_finalization",
                "start_ns": construction_start_ns,
                "end_ns": time.perf_counter_ns(),
                "scope": "source_dtype_device_and_final_parameter_checks",
                "non_additive": True,
            })
        # Fail-closed adoption proof: every first-stage parameter/buffer must
        # be CUDA-resident, BF16 (the transported source requires BF16), and
        # storage-identical to a QD view.  No model.to / loader fallback.
        adoption_start_ns = time.perf_counter_ns() if diagnostics_enabled else None
        adoption = validate_qd_adoption("vae", [first_stage], views)
        adoption_end_ns = time.perf_counter_ns() if diagnostics_enabled else None
        if diagnostics_enabled:
            components.append({
                "name": "storage_adoption",
                "start_ns": adoption_start_ns,
                "end_ns": adoption_end_ns,
                "scope": "pointer_identity_validation",
                "non_additive": True,
            })
        rec.event("vae_adoption_identity", **adoption)
        try:
            setattr(vae, "_golden_qd_owner", owner)
        except Exception:
            pass
        session.vae = vae
        qd_quiescence = _require_transport_quiescence(transport, tag="vae")
        decomposition = None
        page_faults = None
        if diagnostics_enabled:
            compute_ready_ns = time.perf_counter_ns()
            components.append({
                "name": "compute_ready_return",
                "start_ns": compute_ready_ns,
                "end_ns": compute_ready_ns,
                "scope": "ready_point",
                "non_additive": True,
            })
            stage_end_ns = time.perf_counter_ns()
            page_faults_after = _process_page_faults()
            page_faults = {
                "before": page_faults_before,
                "after": page_faults_after,
                "delta": page_fault_delta(page_faults_before, page_faults_after),
            }
            memory_after = {"host": _host_memory_visibility(), "cuda": _allocator_state()}
            decomposition = build_vae_load_decomposition(
                stage_start_ns=int(stage_start_ns),
                stage_end_ns=stage_end_ns,
                components=components,
                transport_stats=transport["stats"],
                memory_before=memory_before,
                memory_after={**memory_after, "page_faults": page_faults},
            )
            rec.event(
                "vae_load_decomposition",
                decomposition=decomposition,
                source_bytes=transport["stats"].get("bytes_read"),
                effective_source_gbps=transport["stats"].get("effective_source_gbps"),
                effective_h2d_gbps=transport["stats"].get("effective_h2d_gbps"),
                page_faults=page_faults,
            )
        rec.end_stage(
            "golden_vae_load",
            ready=True,
            param_count=len(params),
            device=str(params[0].device),
            dtype=str(params[0].dtype),
            source_read_count=int(transport["stats"]["source_read_count"]),
            h2d_completed_bytes=int(transport["stats"]["h2d_completed_bytes"]),
            qd_quiescence=qd_quiescence,
            source_bytes=transport["stats"].get("bytes_read"),
            effective_source_gbps=transport["stats"].get("effective_source_gbps"),
            effective_h2d_gbps=transport["stats"].get("effective_h2d_gbps"),
            **(
                {
                    "transport_stats": build_qd_transport_diagnostics(transport["stats"]),
                    "vae_load_decomposition": decomposition,
                    "page_faults": page_faults,
                }
                if diagnostics_enabled or getattr(session, "qd_transport_arm", "legacy") == "dispatcher" else {}
            ),
        )
        return vae
    except BaseException as exc:
        if diagnostics_enabled:
            page_faults_after = _process_page_faults()
            rec.fail_stage(
                "golden_vae_load",
                exc,
                page_faults={
                    "before": page_faults_before,
                    "after": page_faults_after,
                    "delta": page_fault_delta(page_faults_before, page_faults_after),
                },
            )
        else:
            rec.fail_stage("golden_vae_load", exc)
        raise


async def golden_vae_decode(session: GoldenSession) -> Any:
    """Decode separately using exact upstream VAEDecode semantics through the
    serial runner (seeded VAE loader; sampler latent already cached); returns
    IMAGE tensor(s).  Begins only after sampling and tail have ended."""
    rec = session.recorder
    rec.begin_stage("golden_vae_decode")
    try:
        tail = session.recorder.intervals.get("golden_sampler_tail")
        if tail is None or tail.end_monotonic_ns is None or tail.ok is not True:
            raise RuntimeError("vae_decode_requires_completed_sampler_tail")
        runner = session.runner
        node_map = session.node_map
        # Native socket-major cache shape: one output socket, one item.
        runner.seed(node_map.vae_loader_id, [[session.vae]])
        runner.begin_scope({"vae_decode"})
        try:
            await runner.run_closure(node_map.vae_decode_id, include_target=True)
        finally:
            runner.end_scope()
        _assert_runner_quiescence(runner)
        entry = runner.cache.get(node_map.vae_decode_id)
        if entry is None or not entry.outputs:
            raise RuntimeError("vae_decode_output_missing")
        images = entry.outputs[0][0] if isinstance(entry.outputs[0], list) else entry.outputs[0]
        session.images = images
        shape = tuple(images.shape) if hasattr(images, "shape") else None
        rec.end_stage("golden_vae_decode", ready=True, image_shape=str(shape))
        return images
    except BaseException as exc:
        rec.fail_stage("golden_vae_decode", exc)
        raise


def _fsync_directory(dir_path: str) -> None:
    """Best-effort parent-directory fsync after an atomic rename.

    Makes the post-replace directory entry durable before the Volume commit.
    Windows/filesystems without directory-fsync support degrade to a no-op
    (open/fsync OSError is swallowed); the artifact bytes themselves were
    already fsynced through their own file descriptor.
    """
    try:
        fd = os.open(str(dir_path), os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(fd)
    except OSError:
        pass  # unsupported platform (e.g. Windows) — bytes-level fsync stands
    finally:
        try:
            os.close(fd)
        except OSError:
            pass


def _require_path_in_volume(path: str, volume_mount_root: Optional[str]) -> tuple[str, str]:
    """Return real paths after proving *path* is inside explicit mounted root."""
    if not volume_mount_root or not isinstance(volume_mount_root, (str, os.PathLike)):
        raise RuntimeError("volume_mount_root_required")
    root_real = os.path.realpath(os.fspath(volume_mount_root))
    if not os.path.isdir(root_real):
        raise RuntimeError(f"volume_mount_root_missing:{root_real}")
    path_real = os.path.realpath(os.fspath(path))
    try:
        inside = os.path.commonpath((root_real, path_real)) == root_real
    except ValueError:
        inside = False
    if not inside:
        raise RuntimeError(f"asset_outside_volume_mount:{path_real}:{root_real}")
    return path_real, root_real


def _normalize_volume_rel_path(path: Any) -> str:
    """Require the canonical, portable relative spelling used by descriptors."""
    if not isinstance(path, (str, os.PathLike)):
        raise RuntimeError("volume_rel_path_invalid")
    raw = os.fspath(path)
    if not isinstance(raw, str) or not raw:
        raise RuntimeError("volume_rel_path_invalid")
    portable = raw.replace("\\", "/")
    drive, _ = ntpath.splitdrive(raw)
    if drive or portable.startswith("/"):
        raise RuntimeError("volume_rel_path_absolute")
    parts = portable.split("/")
    if any(not part or part in (".", "..") for part in parts):
        raise RuntimeError("volume_rel_path_traversal")
    if posixpath.normpath(portable) != portable:
        raise RuntimeError("volume_rel_path_not_normalized")
    return portable


def _volume_rel_path_for_checked_asset(asset_path: str, mount_root: str) -> str:
    """Derive a descriptor path only from already-checked canonical paths."""
    relative = os.path.relpath(asset_path, mount_root)
    return _normalize_volume_rel_path(relative)


async def golden_output(session: GoldenSession) -> PendingDurability | ReadyOutputArtifact:
    """Level-1 PNG from the decoded Comfy IMAGE tensor with EXACT current
    upstream output encoding semantics (255*scale, clip, uint8,
    ``compress_level=1`` and no PNG metadata), atomic local write under a content-addressed
    ``output_assets/<sha256>.png``, descriptor/sidecar creation, and the
    required pending-durability object.  Does NOT stamp true durable.

    The canonical SaveImage node is NOT executed here: executing it would
    perform an uncontrolled duplicate write into the shared ComfyUI output
    directory outside durability accounting.  Instead the EXACT canonical
    output branch is validated and executed: SaveImage.images must link to
    the single pass-through node whose class is ``Any Switch (rgthree)``
    and whose selected input is exactly ``any_02 -> [vae_decode_id, 0]``;
    that pass-through node (and only it — VAEDecode is already cached) is
    executed through the serial runner, and the PNG is encoded from the
    runner-cache output of that node.  The encoded SHA is content-addressed
    and recorded.  A configured expectation mismatch is an explicit warning,
    not a write or durability failure.
    """
    rec = session.recorder
    # Missing mode is the documented default: direct/off fixtures must remain
    # in-memory and must not acquire an implicit strict write path.
    output_mode = getattr(session, "output_durability_mode", "off")
    durability_requested = bool(
        getattr(session, "durability_requested", False)
    )
    rec.begin_stage("golden_output")
    try:
        import io  # stdlib

        import numpy as np  # third-party
        from PIL import Image  # third-party
        from PIL.PngImagePlugin import PngInfo  # third-party

        # Explicit canonical output-branch validation (SaveImage itself is
        # never executed).
        if session.runner is None:
            raise RuntimeError("output_requires_runner")
        node_map = session.node_map
        if node_map is None:
            raise RuntimeError("output_requires_node_map")
        classes = session.runner._classes()
        save_nodes = [
            (nid, info)
            for nid, info in session.request.prompt.items()
            if str(info.get("class_type")) == "SaveImage"
        ]
        if len(save_nodes) != 1:
            raise RuntimeError(f"saveimage_node_ambiguous:{len(save_nodes)}")
        save_id, save_info = save_nodes[0]
        session.output_node_id = str(save_id)
        images_link = (save_info.get("inputs") or {}).get("images")
        if not _is_link(images_link):
            raise RuntimeError("saveimage_images_link_mismatch")
        if int(images_link[1]) != 0:
            raise RuntimeError("saveimage_images_socket_mismatch")
        switch_id = str(images_link[0])
        switch_info = session.request.prompt.get(switch_id)
        if switch_info is None:
            raise RuntimeError("saveimage_passthrough_node_missing")
        if str(switch_info.get("class_type")) != "Any Switch (rgthree)":
            raise RuntimeError(
                f"saveimage_passthrough_class_mismatch:{switch_info.get('class_type')}"
            )
        any_02 = (switch_info.get("inputs") or {}).get("any_02")
        if not (
            _is_link(any_02)
            and str(any_02[0]) == str(node_map.vae_decode_id)
            and int(any_02[1]) == 0
        ):
            raise RuntimeError("saveimage_passthrough_selected_input_mismatch")
        try:
            save_class_def = classes["SaveImage"]
        except KeyError:
            raise RuntimeError("saveimage_class_not_registered") from None
        save_fn_name = getattr(save_class_def, "FUNCTION", None)
        if not save_fn_name or not callable(getattr(save_class_def, save_fn_name, None)):
            raise RuntimeError("saveimage_contract_invalid")

        # Execute ONLY the pass-through node, one node at a time; VAEDecode is
        # already cached so nothing upstream re-executes, and SaveImage node
        # itself stays unexecuted (no uncontrolled duplicate output).
        executed = await session.runner.run_closure(switch_id, include_target=True)
        _assert_runner_quiescence(session.runner)
        executed_ids = [nid for nid, _cls, _sc in executed]
        if switch_id not in executed_ids:
            raise RuntimeError("saveimage_passthrough_did_not_execute")
        if str(node_map.vae_decode_id) not in session.runner.cache:
            raise RuntimeError("vae_decode_cache_missing_for_output_branch")
        branch_entry = session.runner.cache.get(switch_id)
        if branch_entry is None or not branch_entry.outputs:
            raise RuntimeError("output_branch_output_missing")
        branch_socket = branch_entry.outputs[0]
        images = branch_socket[0] if isinstance(branch_socket, list) else branch_socket
        if not hasattr(images, "cpu"):
            raise RuntimeError("output_branch_not_image_tensor")
        rec.event(
            "output_branch_executed",
            saveimage_node=str(save_id),
            passthrough_node=switch_id,
            passthrough_class="Any Switch (rgthree)",
            executed_nodes=executed_ids,
        )

        # Exact upstream SaveImage.save_images conversion + encoding.
        i = 255.0 * images.detach().cpu().numpy()
        first = np.clip(i, 0, 255).astype(np.uint8)[0]
        img = Image.fromarray(first)
        bio = io.BytesIO()
        img.save(bio, format="PNG", compress_level=1)
        buf = bio.getvalue()

        sha256 = hashlib.sha256(buf).hexdigest()
        expected_sha = session.contract.expected_output_png_sha256
        output_sha_match = bool(expected_sha) and sha256.lower() == expected_sha.lower()
        output_sha_warning = None
        if expected_sha and not output_sha_match:
            output_sha_warning = {
                "expected": expected_sha,
                "observed": sha256,
                "reason": "configured_output_sha_mismatch",
            }
            LOG.warning(
                "Golden output SHA mismatch is warning-only: expected=%s observed=%s",
                expected_sha,
                sha256,
            )
            print(
                "[v2.golden_p1] WARNING output_sha_mismatch "
                f"expected={expected_sha} observed={sha256}",
                flush=True,
            )
            rec.event(
                "OUTPUT_SHA_MISMATCH_WARNING",
                expected_sha=expected_sha,
                observed_sha=sha256,
                output_sha_match=False,
                output_sha_warning=output_sha_warning,
            )
        artifact = ReadyOutputArtifact(
            raw_bytes=buf,
            sha256=sha256,
            byte_count=len(buf),
            filename=f"{sha256}.png",
            mime_type="image/png",
            width=int(first.shape[1]),
            height=int(first.shape[0]),
        )
        session.output_artifact = artifact
        if output_mode == "off":
            end_output_stage = rec.end_stage
            rec.event(
                EVENT_OUTPUT_ENCODE_DONE,
                sha256=artifact.sha256,
                expected_sha256=expected_sha,
                output_sha_match=output_sha_match,
                output_sha_warning=output_sha_warning,
                byte_count=artifact.byte_count,
                output_durability_mode=output_mode,
                durability_requested=durability_requested,
            )
            end_output_stage(
                "golden_output",
                ready=True,
                sha256=artifact.sha256,
                expected_sha256=expected_sha,
                output_sha_match=output_sha_match,
                output_sha_warning=output_sha_warning,
                byte_count=artifact.byte_count,
                output_durability_mode=output_mode,
                durability_requested=durability_requested,
                result_durable=False,
            )
            rec.mark_first_result_ready()
            return artifact
        out_dir = os.path.abspath(session.output_root)
        asset_path = os.path.join(out_dir, f"{sha256}.png")
        sidecar_path = os.path.join(out_dir, f"{sha256}.json")
        mount_root = getattr(session, "volume_mount_root", None)
        if mount_root is None and isinstance(getattr(session, "volume", None), GoldenVolumeHandle):
            mount_root = session.volume.volume_mount_root
        # Check after forming the final name so symlinked output directories and
        # traversal/escape attempts are judged by their real filesystem paths.
        asset_path, mount_root = _require_path_in_volume(asset_path, mount_root)
        sidecar_path, _ = _require_path_in_volume(sidecar_path, mount_root)
        volume_rel_path = _volume_rel_path_for_checked_asset(asset_path, mount_root)
        os.makedirs(out_dir, exist_ok=True)
        # Atomic local write.
        fd, tmp = tempfile.mkstemp(dir=out_dir, prefix=".golden_asset_", suffix=".tmp")
        try:
            with os.fdopen(fd, "wb") as fh:
                fh.write(buf)
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp, asset_path)
            _fsync_directory(out_dir)
        except BaseException:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise
        descriptor = {
            "schema": "golden_p1_asset_descriptor_v1",
            "sha256": sha256,
            "byte_count": len(buf),
            "width": int(first.shape[1]),
            "height": int(first.shape[0]),
            "request_id": session.request.request_id,
            "volume_rel_path": volume_rel_path,
        }
        fd, tmp = tempfile.mkstemp(dir=out_dir, prefix=".golden_sidecar_", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(descriptor, fh, indent=1)
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp, sidecar_path)
            _fsync_directory(out_dir)
        except BaseException:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise

        pending = PendingDurability(
            asset_abs_path=asset_path,
            volume_rel_path=volume_rel_path,
            sha256=sha256,
            byte_count=len(buf),
            sidecar_path=sidecar_path,
            committed=False,
            volume_mount_root=mount_root,
        )
        session.pending_durability = pending
        rec.event(
            EVENT_OUTPUT_ENCODE_DONE,
            sha256=sha256,
            expected_sha256=expected_sha,
            output_sha_match=output_sha_match,
            output_sha_warning=output_sha_warning,
            byte_count=len(buf),
            output_durability_mode=output_mode,
            durability_requested=durability_requested,
        )
        rec.event(
            EVENT_ASSET_WRITE_DONE,
            asset_path=os.path.basename(asset_path),
            output_durability_mode=output_mode,
        )
        rec.end_stage(
            "golden_output",
            ready=True,
            sha256=sha256,
            expected_sha256=expected_sha,
            output_sha_match=output_sha_match,
            output_sha_warning=output_sha_warning,
            byte_count=len(buf),
            committed=False,
            output_durability_mode=output_mode,
            durability_requested=durability_requested,
            result_durable=False,
        )
        return pending
    except BaseException as exc:
        rec.fail_stage("golden_output", exc)
        raise


def io_bytes_png(Image: Any, array: Any, *, pnginfo: Any = None, compress_level: int = 1) -> bytes:
    """Encode a HxWx3 uint8 array to PNG bytes via PIL with upstream SaveImage
    semantics (``compress_level=1``, optional PngInfo metadata; kept separate
    for tests)."""
    import io

    img = Image.fromarray(array)
    bio = io.BytesIO()
    img.save(bio, format="PNG", pnginfo=pnginfo, compress_level=int(compress_level))
    return bio.getvalue()


def _new_durable_commit_timing(*, clock_name: str = "monotonic_ns") -> dict[str, Any]:
    """Create raw, monotonic-ns evidence for the durable commit decomposition."""
    return {
        "clock": clock_name,
        "blocking_commit_note": DURABLE_COMMIT_BLOCKING_NOTE,
        "durable_commit_subspans": {
            name: {
                "start_monotonic_ns": None,
                "end_monotonic_ns": None,
                "duration_ns": None,
            }
            for name in DURABLE_COMMIT_SUBSPAN_NAMES
        },
    }


def _start_durable_subspan(
    timing: dict[str, Any],
    name: str,
    *,
    monotonic: Callable[[], int] = time.monotonic_ns,
    started_ns: Optional[int] = None,
) -> int:
    started_ns = monotonic() if started_ns is None else int(started_ns)
    timing["durable_commit_subspans"][name]["start_monotonic_ns"] = started_ns
    return started_ns


def _finish_durable_subspan(
    timing: dict[str, Any],
    name: str,
    *,
    end_ns: Optional[int] = None,
    monotonic: Callable[[], int] = time.monotonic_ns,
) -> int:
    ended_ns = monotonic() if end_ns is None else int(end_ns)
    span = timing["durable_commit_subspans"][name]
    started_ns = span["start_monotonic_ns"]
    if started_ns is not None:
        span["end_monotonic_ns"] = ended_ns
        span["duration_ns"] = max(0, ended_ns - int(started_ns))
    return ended_ns


def _finish_open_durable_subspans(
    timing: dict[str, Any], *, monotonic: Callable[[], int] = time.monotonic_ns
) -> None:
    """Close only spans that started before a failure; leave later work null."""
    for name in DURABLE_COMMIT_SUBSPAN_NAMES:
        span = timing["durable_commit_subspans"][name]
        if span["start_monotonic_ns"] is not None and span["end_monotonic_ns"] is None:
            _finish_durable_subspan(timing, name, monotonic=monotonic)


def verify_committed_object(
    pending: PendingDurability,
    *,
    expected_sha256: str,
    enforce_expected_sha: bool = True,
    timing: Optional[dict[str, Any]] = None,
    monotonic: Callable[[], int] = time.monotonic_ns,
) -> _DurableReopenProof:
    """Post-commit durability proof: reopen/stat/read/hash the COMMITTED
    object from disk and fail closed unless stat size, reopened byte count,
    and the pending record all agree.  Strict callers may enforce the
    configured expectation; Golden's output expectation is warning-only while
    content-addressed pending/reopened integrity remains fail-closed."""
    if pending is None:
        raise RuntimeError("reopen_requires_pending_durability")
    if not pending.committed:
        raise RuntimeError("reopen_requires_committed_pending_durability")
    asset_path, mount_root = _require_path_in_volume(
        pending.asset_abs_path, getattr(pending, "volume_mount_root", None)
    )
    volume_rel_path = _normalize_volume_rel_path(getattr(pending, "volume_rel_path", None))
    relative_asset_path = os.path.join(mount_root, *volume_rel_path.split("/"))
    relative_asset_path, _ = _require_path_in_volume(relative_asset_path, mount_root)
    if relative_asset_path != asset_path:
        raise RuntimeError(
            f"durable_asset_path_mismatch:{relative_asset_path}!={asset_path}"
        )
    _sidecar_path, _ = _require_path_in_volume(
        pending.sidecar_path, mount_root
    )
    fh = None
    try:
        if timing is not None:
            _start_durable_subspan(timing, "reopen_open", monotonic=monotonic)
        try:
            fh = open(asset_path, "rb")
        finally:
            if timing is not None:
                open_start = timing["durable_commit_subspans"]["reopen_open"][
                    "start_monotonic_ns"
                ]
                open_end = _finish_durable_subspan(
                    timing, "reopen_open", monotonic=monotonic
                )
                handoff = timing["durable_commit_subspans"][
                    "commit_return_to_reopen_start"
                ]
                if handoff["start_monotonic_ns"] is not None and handoff["end_monotonic_ns"] is None:
                    _finish_durable_subspan(
                        timing,
                        "commit_return_to_reopen_start",
                        end_ns=open_start or open_end,
                        monotonic=monotonic,
                    )

        if timing is not None:
            _start_durable_subspan(timing, "stat", monotonic=monotonic)
        try:
            stat = os.stat(asset_path)
        finally:
            if timing is not None:
                _finish_durable_subspan(timing, "stat", monotonic=monotonic)

        if timing is not None:
            _start_durable_subspan(timing, "readback", monotonic=monotonic)
        try:
            data = fh.read()
        finally:
            if timing is not None:
                _finish_durable_subspan(timing, "readback", monotonic=monotonic)

        if timing is not None:
            _start_durable_subspan(
                timing, "readback_sha256", monotonic=monotonic
            )
        try:
            byte_count = len(data)
            sha256 = hashlib.sha256(data).hexdigest()
        finally:
            if timing is not None:
                _finish_durable_subspan(
                    timing, "readback_sha256", monotonic=monotonic
                )

        if timing is not None:
            _start_durable_subspan(
                timing,
                "byte_count_content_verification",
                monotonic=monotonic,
            )
        try:
            if int(stat.st_size) != byte_count or byte_count != int(pending.byte_count):
                raise RuntimeError(
                    f"durable_byte_count_mismatch:stat={int(stat.st_size)}:"
                    f"read={byte_count}:pending={int(pending.byte_count)}"
                )
            if sha256 != pending.sha256:
                raise RuntimeError(f"durable_sha_mismatch:{sha256}!={pending.sha256}")
            if enforce_expected_sha and sha256 != expected_sha256:
                raise RuntimeError(
                    f"durable_expected_output_sha_mismatch:{sha256}!={expected_sha256}"
                )
        finally:
            if timing is not None:
                _finish_durable_subspan(
                    timing,
                    "byte_count_content_verification",
                    monotonic=monotonic,
                )
    finally:
        if fh is not None:
            if timing is not None:
                _start_durable_subspan(
                    timing, "close_finalize", monotonic=monotonic
                )
            try:
                fh.close()
            finally:
                if timing is not None:
                    _finish_durable_subspan(
                        timing, "close_finalize", monotonic=monotonic
                    )
    return _DurableReopenProof(
        byte_count=byte_count,
        sha256=sha256,
        stat_size_bytes=int(stat.st_size),
        asset_path=asset_path,
        volume_mount_root=mount_root,
        pending_identity=id(pending),
        _proof_token=_DURABLE_REOPEN_PROOF_TOKEN,
    )


async def golden_durable_commit(
    volume: Any,
    pending: PendingDurability,
    recorder: GoldenTelemetryRecorder,
    *,
    expected_sha256: Optional[str] = None,
    enforce_expected_sha: bool = False,
) -> _DurableReopenProof:
    """Emit VOLUME_COMMIT_START, await the REAL Modal Volume commit API
    (``commit.aio()`` when present, else an awaitable/sync ``commit()``), then
    VOLUME_COMMIT_COMPLETE.  When ``expected_sha256`` is supplied, this stage
    also owns the reopen/stat/read/hash proof before its END.  The expected SHA
    is an observation contract; a mismatch was already recorded by
    ``golden_output`` and does not weaken reopened pending-content integrity.
    OUTPUT_ENCODE_DONE
    / ASSET_WRITE_DONE are emitted exactly once by :func:`golden_output` at the
    real write — they are NOT re-emitted here.
    """
    recorder.begin_stage("golden_durable_commit")
    monotonic = recorder._monotonic
    timing = _new_durable_commit_timing(clock_name="recorder.monotonic_ns")
    _start_durable_subspan(timing, "pre_commit_bookkeeping", monotonic=monotonic)
    subspans_event_emitted = False
    try:
        if getattr(recorder, "output_durability_mode", "off") != "strict":
            raise RuntimeError("durable_commit_requires_output_durability_strict")
        if pending is None:
            raise RuntimeError("durable_commit_requires_pending_durability")
        if expected_sha256 is None:
            raise RuntimeError("durable_commit_requires_mount_reopen_proof")
        _, pending_mount_root = _require_path_in_volume(
            pending.asset_abs_path, getattr(pending, "volume_mount_root", None)
        )
        if isinstance(volume, GoldenVolumeHandle):
            handle = getattr(volume, "handle", None)
            handle_mount_root = getattr(volume, "volume_mount_root", None)
            if handle is None or not handle_mount_root:
                raise RuntimeError("volume_handle_contract_required")
            handle_mount_root = os.path.realpath(os.fspath(handle_mount_root))
            if handle_mount_root != pending_mount_root:
                raise RuntimeError(
                    f"volume_mount_root_mismatch:{handle_mount_root}!={pending_mount_root}"
                )
            volume = handle
        elif pending_mount_root is None:
            raise RuntimeError("pending_volume_mount_root_required")

        _finish_durable_subspan(
            timing, "pre_commit_bookkeeping", monotonic=monotonic
        )
        recorder.event(EVENT_VOLUME_COMMIT_START, label=str(getattr(volume, "label", "")))
        commit_fn = getattr(volume, "commit", None)
        if not callable(commit_fn):
            raise RuntimeError("volume_commit_api_unavailable")
        aio_fn = getattr(commit_fn, "aio", None)
        _start_durable_subspan(
            timing, "volume_commit_call_wall", monotonic=monotonic
        )
        try:
            if callable(aio_fn):
                await aio_fn()
            else:
                result = commit_fn()
                if inspect.isawaitable(result):
                    await result
        except BaseException as exc:
            _finish_durable_subspan(
                timing, "volume_commit_call_wall", monotonic=monotonic
            )
            recorder.event("VOLUME_COMMIT_FAILED", error=f"{type(exc).__name__}: {exc}")
            pending.committed = False
            raise
        commit_return_ns = monotonic()
        _finish_durable_subspan(
            timing,
            "volume_commit_call_wall",
            end_ns=commit_return_ns,
            monotonic=monotonic,
        )
        # This boundary starts at return from the single blocking Modal API,
        # before completion bookkeeping and before the reopen call.
        _start_durable_subspan(
            timing,
            "commit_return_to_reopen_start",
            monotonic=monotonic,
            started_ns=commit_return_ns,
        )
        recorder.event(EVENT_VOLUME_COMMIT_COMPLETE)
        pending.committed = True
        reopened = None
        reopened = verify_committed_object(
            pending,
            expected_sha256=expected_sha256,
            enforce_expected_sha=enforce_expected_sha,
            timing=timing,
            monotonic=monotonic,
        )
        recorder.mark_reopen_verified(reopened)
        recorder.event(
            "DURABLE_COMMIT_SUBSPANS",
            outcome="success",
            clock=timing["clock"],
            blocking_commit_note=timing["blocking_commit_note"],
            durable_commit_subspans=copy.deepcopy(timing["durable_commit_subspans"]),
        )
        subspans_event_emitted = True
        recorder.end_stage(
            "golden_durable_commit",
            ready=True,
            sha256=pending.sha256,
            volume_rel_path=pending.volume_rel_path,
            reopened_verified=reopened is not None,
            clock=timing["clock"],
            blocking_commit_note=timing["blocking_commit_note"],
            durable_commit_subspans=copy.deepcopy(timing["durable_commit_subspans"]),
        )
        return reopened
    except BaseException as exc:
        _finish_open_durable_subspans(timing, monotonic=monotonic)
        if pending is not None:
            pending.committed = False
        if not subspans_event_emitted:
            recorder.event(
                "DURABLE_COMMIT_SUBSPANS",
                outcome="failure",
                clock=timing["clock"],
                blocking_commit_note=timing["blocking_commit_note"],
                durable_commit_subspans=copy.deepcopy(timing["durable_commit_subspans"]),
            )
        recorder.fail_stage(
            "golden_durable_commit",
            exc,
            clock=timing["clock"],
            blocking_commit_note=timing["blocking_commit_note"],
            durable_commit_subspans=copy.deepcopy(timing["durable_commit_subspans"]),
        )
        raise


async def golden_teardown(session: GoldenSession) -> dict:
    """Single-use minimal teardown: close/release QD owner staging resources
    safely, and assert no Golden-owned worker/thread is still live using the
    module thread registry (stronger than a name assertion).
    Snapshot proof is a passive reusable helper, not a request-teardown step.

    Final telemetry persistence belongs to the top-level executor, after this
    function has recorded its END.  Keeping that application write outside the
    interval makes the teardown wall represent teardown work only.

    NEVER performs a full unload, model-sized CPU/GPU transfer, broad GC,
    ``empty_cache``, or allocator purge — process exit owns CUDA/model
    reclaim.  (For the UNET role the QD CUDA buffer backs live weights via
    ``assign=True`` storage sharing, so only pinned staging slots are
    released here.)
    """
    rec = session.recorder
    rec.begin_stage("golden_teardown")
    substage_timings: dict = {}
    try:
        t0 = time.monotonic_ns()
        # RA9H transfer cleanup precedes owner staging release.  A completed
        # transfer has already retired its source owner and is metadata-only;
        # incomplete transfers still own source mappings/handles here.
        session.cleanup_clip_ownership_transfer()
        owners: list[GoldenQDOwner] = []
        for attr in ("clip_owner", "unet_owner", "vae_owner"):
            owner = getattr(session, attr, None)
            if owner is not None:
                owners.append(owner)
        # Every per-checkpoint CLIP owner (release_staging is idempotent).
        owners.extend(getattr(session, "clip_owners", []))
        # Include owners as soon as transport succeeds, including unpublished
        # earlier CLIP checkpoints when a later checkpoint or adoption fails.
        owners.extend(getattr(session, "qd_transaction_owners", []))
        seen_owner_ids: set[int] = set()
        for owner in owners:
            if id(owner) in seen_owner_ids:
                continue
            seen_owner_ids.add(id(owner))
            owner.release_staging()
        substage_timings["owner_staging_release_ms"] = (time.monotonic_ns() - t0) / 1e6

        # Final runner quiescence check must happen before teardown END.  The
        # helper deliberately uses the trusted Golden runner implementation
        # rather than an arbitrary runner.assert_quiescent method.
        t1 = time.monotonic_ns()
        runner = getattr(session, "runner", None)
        if runner is not None:
            _assert_runner_quiescence(runner)

        # Leak checks on ALL Golden-owned handles this module created: the
        # exact thread registry first, then a name scan as a backstop.
        with _GOLDEN_THREAD_LOCK:
            registry_live = [t.name for t in _GOLDEN_THREADS if t.is_alive()]
        if registry_live:
            raise RuntimeError(f"teardown_registry_threads_live:{registry_live}")
        pending_workers = [
            t.name
            for t in threading.enumerate()
            if (t.name.startswith("golden-qd-") or "preload" in t.name.lower()) and t.is_alive()
        ]
        if pending_workers:
            raise RuntimeError(f"teardown_workers_pending:{pending_workers}")
        substage_timings["worker_assert_ms"] = (time.monotonic_ns() - t1) / 1e6

        t2 = time.monotonic_ns()
        reconcile = rec.reconcile_seriality()
        substage_timings["reconcile_ms"] = (time.monotonic_ns() - t2) / 1e6

        rec.end_stage(
            "golden_teardown",
            ready=True,
            seriality_violations=reconcile["count"],
            **{k: round(v, 4) for k, v in substage_timings.items()},
        )
        return {**substage_timings, "telemetry_path": None}
    except BaseException as exc:
        rec.fail_stage("golden_teardown", exc)
        raise


def _persist_final_telemetry(session: GoldenSession) -> Optional[str]:
    """Persist once as explicit application work after teardown.

    The returned duration is deliberately kept outside the teardown interval.
    It is also attached to the final result by the top-level executor; the
    persistence operation itself remains the single final telemetry write.
    """
    if not session.telemetry_path:
        session.telemetry_persist_ms = None
        return None
    started_ns = time.monotonic_ns()
    try:
        return session.recorder.persist(session.telemetry_path)
    finally:
        session.telemetry_persist_ms = round(
            (time.monotonic_ns() - started_ns) / 1e6, 4
        )


# ── Top-level explicit serial executor ────────────────────────────────────


async def golden_serial_execute(
    request: GoldenRequest,
    *,
    volume: Any,
    volume_mount_root: Optional[str] = None,
    output_root: Optional[str] = None,
    telemetry_path: Optional[str] = None,
    node_classes: Optional[dict] = None,
    contract: Optional[GoldenWorkflowContract] = None,
    snapshot_proof: Optional[Callable[[], dict]] = None,
    restore_metadata: Optional[dict] = None,
    restore_observation: Optional[dict] = None,
) -> GoldenFinalResult:
    """The one obvious explicit strictly-serial Golden execution.

    The body calls every stage in the exact required contract order
    (REAL RESTORE observation -> request setup -> remaining stages); successful
    ordering remains visually obvious while ``try/except/else`` guarantees
    teardown runs exactly once on every path: after a primary failure the
    primary exception stays the raised error even if teardown also fails,
    and on success the result is returned only after teardown succeeds.
    ``TEARDOWN_COMPLETE`` is recorded after teardown END, then final telemetry
    is persisted once as separate post-teardown application work measured by
    ``telemetry_persist_ms``.
    In strict mode durability is:
    commit -> reopen/stat/read/hash the committed object -> verify byte count
    and SHA from the REOPENED bytes against the pending record (the configured
    output expectation is warning-only) -> TRUE_FIRST_DURABLE_RESULT ->
    RESULT_ASSEMBLED.  In off mode the encoded bytes are validated in memory,
    FIRST_RESULT_READY is emitted, and the commit stage is absent.
    ``snapshot_proof`` is retained as an optional reusable helper input for
    compatibility, but request teardown does not invoke it.
    """
    session = GoldenSession(
        request,
        volume=volume,
        volume_mount_root=volume_mount_root,
        output_root=output_root,
        telemetry_path=telemetry_path,
        node_classes=node_classes,
        contract=contract,
        snapshot_proof=snapshot_proof,
        restore_metadata=restore_metadata,
        restore_observation=restore_observation,
    )
    primary_error: Optional[BaseException] = None
    teardown_error: Optional[BaseException] = None
    # The selector is request state, not live process configuration.  Keep the
    # arm captured by GoldenSession in this task's context for every stage
    # read, even if the environment changes mid-request.
    transport_arm_token = _GOLDEN_QD_ARM_CONTEXT.set(session.qd_transport_arm)
    try:
        await golden_restore(session)
        await golden_request_setup(session)
        await golden_clip_load(session)
        await golden_clip_forward(session)
        await golden_unet_load(session)
        await golden_sampler_prepare(session)
        await golden_vae_load(session)
        await golden_sampling(session)
        await golden_sampler_tail(session)
        await golden_vae_decode(session)
        await golden_output(session)
        if session.output_durability_mode == "strict":
            await golden_durable_commit(
                session.volume_contract or session.volume,
                session.pending_durability,
                session.recorder,
                expected_sha256=session.contract.expected_output_png_sha256,
            )
            session.recorder.mark_true_durable()
        result = session.build_final_result()
        session.recorder.event(EVENT_RESULT_ASSEMBLED, request_id=request.request_id)
    except BaseException as exc:
        # Primary failure: mandatory teardown still runs exactly once.  Its
        # failure and any failure writing the best-effort artifact must never
        # replace the primary exception.
        primary_error = exc
        try:
            await golden_teardown(session)
        except BaseException:
            pass
    else:
        # Success path: the result may only be returned after teardown
        # succeeds; a teardown failure fails the call.
        try:
            await golden_teardown(session)
        except BaseException as exc:
            teardown_error = exc
        else:
            session.recorder.event(EVENT_TEARDOWN_COMPLETE, request_id=request.request_id)
    finally:
        _GOLDEN_QD_ARM_CONTEXT.reset(transport_arm_token)

    # This is the sole final telemetry write for either outcome.  On success
    # it necessarily follows TEARDOWN_COMPLETE; on failure it preserves the
    # primary error while still leaving the latest teardown boundary on disk.
    try:
        _persist_final_telemetry(session)
    except BaseException:
        if primary_error is not None:
            raise primary_error
        if teardown_error is not None:
            raise teardown_error
        raise

    if primary_error is not None:
        raise primary_error
    if teardown_error is not None:
        raise teardown_error

    result.telemetry_persist_ms = session.telemetry_persist_ms
    return result


__all__ = [
    "CANONICAL_CLIP_SPEC",
    "ATTENTION_BACKENDS",
    "AttentionBackendValidationError",
    "EXPECTED_OUTPUT_PNG_SHA256",
    "EXPECTED_WORKFLOW_SHA256",
    "EXPECTED_UNET_TENSOR_COUNT",
    "GOLDEN_BLOCK_BYTES",
    "GOLDEN_QD",
    "GOLDEN_SAMPLING_DIAGNOSTICS_ENV",
    "GOLDEN_STAGE_DIAGNOSTICS_ENV",
    "GOLDEN_QD_TRANSPORT_ENV",
    "CLIP_FP32_CAST_ONCE_ENV",
    "CLIP_RESIDENCY_MODES",
    "DURABLE_COMMIT_BLOCKING_NOTE",
    "DURABLE_COMMIT_SUBSPAN_NAMES",
    "DURABLE_RESULT_MARKER_SUBSPAN",
    "EVENT_FIRST_RESULT_READY",
    "ConfigurationError",
    "ReadyOutputArtifact",
    "resolve_output_durability",
    "EVENT_DURABLE_RESULT_MARKER_PUBLICATION",
    "STAGE_ORDER",
    "ClipLoadSpec",
    "GoldenWorkflowContract",
    "GoldenFinalResult",
    "GoldenNodeMap",
    "GoldenQDOwner",
    "GoldenRequest",
    "GoldenSerialRunner",
    "GoldenSamplingDiagnostics",
    "GoldenSession",
    "GoldenTelemetryRecorder",
    "GoldenVolumeHandle",
    "PendingDurability",
    "canonical_workflow_sha256",
    "golden_qd_transport_arm",
    "normalize_clip_residency",
    "resolve_clip_residency",
    "stage_diagnostics_enabled",
    "attention_backend_scope",
    "aggregate_timing_intervals",
    "build_qd_transport_diagnostics",
    "build_vae_load_decomposition",
    "check_view_alignment",
    "classify_node",
    "golden_clip_forward",
    "golden_clip_load",
    "golden_durable_commit",
    "golden_output",
    "golden_request_setup",
    "golden_restore",
    "golden_sampler_prepare",
    "golden_sampler_tail",
    "golden_sampling",
    "golden_serial_execute",
    "golden_snapshot_content_proof",
    "golden_teardown",
    "golden_unet_load",
    "golden_vae_decode",
    "golden_vae_load",
    "make_zero_copy_view",
    "parse_safetensors_header",
    "page_fault_delta",
    "normalize_attention_backend",
    "partition_coverage",
    "plan_source_regions",
    "read_file_qd_gpu",
    "require_dynamic_core_model_patcher",
    "require_dynamic_patcher_instance",
    "resolve_clip_type",
    "resolve_golden_node_map",
    "select_and_validate_qd_adoption_scope",
    "uniform_source_dtype",
    "uniform_source_dtype_across",
    "validate_qd_adoption",
    "validate_attention_backend_diagnostics",
    "validate_transport_records",
    "validate_unet_binding",
    "verify_committed_object",
]
