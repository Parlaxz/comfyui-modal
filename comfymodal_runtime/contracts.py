"""Typed, serializable contracts for the v2 runtime."""

from __future__ import annotations

import hashlib
import json
import os
import sys
import time
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from types import MappingProxyType
from typing import Any


METADATA_RUNTIME_MODE = "runtime_mode"
METADATA_WORKFLOW_HASH_PREFIX = "workflow_hash_prefix"
METADATA_APP_NAME = "app_name"
METADATA_CLASS_NAME = "class_name"
METADATA_METHOD_NAME = "method_name"
METADATA_MODAL_INPUT_ID = "modal_input_id"
METADATA_CONTAINER_TASK_ID = "container_task_id"
METADATA_CONTAINER_SESSION_ID = "container_session_id"
METADATA_IMAGE_ID = "image_id"
METADATA_GPU = "gpu"
METADATA_CLOUD = "cloud"
METADATA_REGION = "region"
METADATA_CPU = "cpu"
METADATA_MEMORY_MB = "memory_mb"
METADATA_SNAPSHOT_ENABLED = "snapshot_enabled"
METADATA_GPU_SNAPSHOT_ENABLED = "gpu_snapshot_enabled"
METADATA_RESTORE_PLAN_GENERATION = "restore_plan_generation"

# All current deployment fingerprints use this namespace.  The explicit
# namespace keeps the source-identity compatibility spelling from being
# confused with the canonical image-plan deployment hash.
DEPLOYMENT_HASH_NAMESPACE = "comfy-modal/deployment/v2"
SOURCE_IDENTITY_HASH_NAMESPACE = "comfy-modal/source/v2"
DEPLOYMENT_IDENTITY_SCHEMA_VERSION = 2

VAE_POLICY_VERSION = 1
VAE_POLICY_ENV_KEY = "COMFYMODAL_V2_VAE_POLICY"
VAE_PREFETCH_ENV_KEY = "COMFYMODAL_V2_VAE_PREFETCH_MODE"

# Static, architecture-sensitive C5 implementation version.  Bumped only
# when the runtime-side (Category 5) VAE policy handling semantics change.
C5_IMPL_VERSION = "1.0.0"

# Best-effort runtime-version capture env overrides.  Deployments pin these
# so policy identity stays stable across environments.
C5_ARCH_ENV_KEY = "COMFYMODAL_V2_C5_ARCH"
C5_TORCH_VERSION_ENV_KEY = "COMFYMODAL_V2_C5_TORCH_VERSION"
C5_CUDA_VERSION_ENV_KEY = "COMFYMODAL_V2_C5_CUDA_VERSION"

# Allowed Form-B tuple component value sets.
VAE_WEIGHT_DTYPES = frozenset({"float32", "bfloat16", "float16"})
VAE_COMPUTE_DTYPES = frozenset({
    "float32", "bfloat16_native", "bfloat16_autocast",
    "float16_native", "float16_autocast",
})
VAE_MEMORY_FORMATS = frozenset({"contiguous", "channels_last"})
VAE_PREFETCH_MODES = frozenset({
    "off", "madvise_willneed", "madvise_populate_read", "bounded_native_touch",
})


def vae_prefetch_mode() -> str:
    raw = os.environ.get(VAE_PREFETCH_ENV_KEY, "off").strip().lower()
    return raw if raw in VAE_PREFETCH_MODES else "off"


_C5_RUNTIME_CACHE: dict[str, Any] | None = None


def capture_c5_runtime_metadata() -> dict[str, Any]:
    """Best-effort torch/CUDA/arch capture WITHOUT initializing CUDA.

    Env overrides always win so deployments can pin versions for identity
    stability.  ``torch.version`` and ``torch.cuda.get_arch_list()`` do not
    initialize the CUDA runtime.  Results are cached when no overrides are
    present (the common production case) so callers pay the capture cost at
    most once per process.
    """
    global _C5_RUNTIME_CACHE
    has_overrides = bool(
        os.environ.get(C5_ARCH_ENV_KEY)
        or os.environ.get(C5_TORCH_VERSION_ENV_KEY)
        or os.environ.get(C5_CUDA_VERSION_ENV_KEY)
    )
    if _C5_RUNTIME_CACHE is not None and not has_overrides:
        return dict(_C5_RUNTIME_CACHE)
    torch_version = os.environ.get(C5_TORCH_VERSION_ENV_KEY, "").strip()
    cuda_version = os.environ.get(C5_CUDA_VERSION_ENV_KEY, "").strip()
    arch = os.environ.get(C5_ARCH_ENV_KEY, "").strip()
    if not torch_version or not cuda_version or not arch:
        try:
            import torch
            if not torch_version:
                torch_version = str(getattr(torch, "__version__", "") or "")
            if not cuda_version:
                try:
                    cuda_version = str(getattr(torch.version, "cuda", "") or "")
                except Exception:
                    cuda_version = ""
            if not arch:
                try:
                    _arch_list = torch.cuda.get_arch_list()
                    arch = ";".join(_arch_list) if _arch_list else ""
                except Exception:
                    arch = ""
                if not arch:
                    try:
                        import platform as _p
                        arch = _p.machine()
                    except Exception:
                        arch = ""
        except Exception:
            pass
    result = {
        "torch_version": torch_version,
        "cuda_version": cuda_version,
        "arch_identifier": arch,
    }
    if not has_overrides:
        _C5_RUNTIME_CACHE = dict(result)
    return result


def _resolve_vae_policy_core(label: str) -> dict[str, Any] | None:
    if label == "v0":
        return {
            "vae_weight_dtype": "float32",
            "vae_compute_dtype": "float32",
            "vae_memory_format": "contiguous",
        }
    if label == "v1":
        return {
            "vae_weight_dtype": "bfloat16",
            "vae_compute_dtype": "bfloat16_native",
            "vae_memory_format": "contiguous",
        }
    if label == "v2":
        return {
            "vae_weight_dtype": "bfloat16",
            "vae_compute_dtype": "bfloat16_autocast",
            "vae_memory_format": "contiguous",
        }
    if label == "v3":
        return {
            "vae_weight_dtype": "bfloat16",
            "vae_compute_dtype": "bfloat16_autocast",
            "vae_memory_format": "channels_last",
        }
    if label == "v4":
        # Completes the controlled 2x2 (compute native/autocast) x
        # (memory contiguous/channels_last) matrix on bfloat16:
        #   v1 = native/contiguous, v2 = autocast/contiguous,
        #   v3 = autocast/channels_last, v4 = native/channels_last.
        return {
            "vae_weight_dtype": "bfloat16",
            "vae_compute_dtype": "bfloat16_native",
            "vae_memory_format": "channels_last",
        }
    return None


def _parse_vae_policy_tuple(value: str) -> dict[str, Any] | None:
    """Parse the Form-B tuple form ``tuple:<weight>:<compute>:<format>``.

    Returns the core policy dict only when all three components are in the
    allowed value sets; otherwise ``None`` (callers fail closed).
    """
    parts = value.split(":")
    if len(parts) != 4 or parts[0] != "tuple":
        return None
    weight, compute, fmt = parts[1], parts[2], parts[3]
    if weight not in VAE_WEIGHT_DTYPES:
        return None
    if compute not in VAE_COMPUTE_DTYPES:
        return None
    if fmt not in VAE_MEMORY_FORMATS:
        return None
    return {
        "vae_weight_dtype": weight,
        "vae_compute_dtype": compute,
        "vae_memory_format": fmt,
    }


def _resolve_vae_policy_detail(mode: str | None = None) -> tuple[dict[str, Any], str, str]:
    """Shared resolution returning ``(core, resolved_mode, provenance)``.

    Kept private so ``resolve_vae_policy`` can return exactly its original
    key set (5 keys) — ``derive_model_key`` in restore_plan.py splats
    ``resolve_vae_policy().items()`` (minus ``vae_policy_mode``) into the
    ``ModelRestoreKey`` constructor, so adding keys here would break it.

    Direct label semantics (the controlled matrix):
        v0 - float32/float32/contiguous            (FP32 fail-closed fallback/control)
        v1 - bf16/bfloat16_native/contiguous       (V1 native — production default)
        v2 - bf16/bfloat16_autocast/contiguous     (V2 controlled-compute)
        v3 - bf16/bfloat16_autocast/channels_last  (explicit winner-slot arm)
        v4 - bf16/bfloat16_native/channels_last    (explicit winner-slot arm)
    The production default (absent policy) is **v1**: weight bfloat16,
    compute bfloat16_native, memory format contiguous, prefetch off.  v0
    (float32/float32/contiguous) is preserved as an explicit FP32 control
    option AND as the fail-closed fallback: any invalid/unsupported label or
    tuple fails closed to v0 (provenance ``invalid_*_fallback``).  No
    channels-last, prefetch, autocast, per-layer mixed dtype, or benchmark-only
    matrices are enabled by default.
    ``v3``/``v4`` are the harness's nominal winner-bound slots: in a
    benchmark the harness binds them to the selected V3/V4 winner via the
    explicit Form-B tuple ``tuple:<weight>:<compute>:<format>``.  The direct
    label mappings above are provided for completeness and reference only;
    they are unambiguous and never inferred from observed tensor dtype or
    layout.  If the harness binds a tuple that does not parse, resolution
    fails closed to v0 (provenance ``invalid_tuple_fallback``).
    """
    raw_mode = os.environ.get(VAE_POLICY_ENV_KEY, "v1") if mode is None else mode
    raw = str(raw_mode or "v0").strip().lower()
    if not raw:
        raw = "v0"
    from_env = mode is None
    if raw in {"v0", "v1", "v2", "v3", "v4"}:
        core = _resolve_vae_policy_core(raw)
        resolved_mode = raw
        provenance = "env" if from_env else "legacy_label"
    elif raw.startswith("tuple:"):
        core = _parse_vae_policy_tuple(raw)
        if core is None:
            core = _resolve_vae_policy_core("v0")
            resolved_mode = "v0"
            provenance = "invalid_tuple_fallback"
        else:
            resolved_mode = raw
            provenance = "env" if from_env else "tuple_form_b"
    else:
        core = _resolve_vae_policy_core("v0")
        resolved_mode = "v0"
        provenance = "invalid_fallback"
    return core, resolved_mode, provenance


def resolve_vae_policy(mode: str | None = None) -> dict[str, Any]:
    """Resolve the immutable VAE weight/compute/layout policy.

    Accepts the legacy label modes ``v0``/``v1``/``v2``/``v3``/``v4`` and the
    explicit Form-B tuple form ``tuple:<weight>:<compute>:<format>`` used
    by the harness to bind the V3/V4 winner after selection.  Tuple
    components are validated against the allowed value sets; invalid
    tuples fail closed to the v0 default.  The mode is derived purely from
    the supplied label/string — never inferred from observed tensor dtype
    or layout.

    Returns exactly ``vae_policy_version``, ``vae_weight_dtype``,
    ``vae_compute_dtype``, ``vae_memory_format``, ``vae_policy_mode``.
    Extended identity metadata (prefetch strategy, provenance, C5 impl
    version, runtime versions) is available via ``build_vae_policy_metadata``.
    """
    core, resolved_mode, _provenance = _resolve_vae_policy_detail(mode)
    return {
        "vae_policy_version": VAE_POLICY_VERSION,
        "vae_weight_dtype": core["vae_weight_dtype"],
        "vae_compute_dtype": core["vae_compute_dtype"],
        "vae_memory_format": core["vae_memory_format"],
        "vae_policy_mode": resolved_mode,
    }


def build_vae_policy_metadata(
    policy: Mapping[str, Any] | None = None,
    *,
    include_runtime_versions: bool = True,
) -> dict[str, Any]:
    """Full VAE policy identity metadata (requested/applied).

    Merges the resolved policy (label or Form-B tuple) with the explicit
    prefetch strategy, provenance, static C5 implementation version, and
    best-effort runtime versions.  ``include_runtime_versions=False`` drops
    the runtime-local torch/CUDA version strings for stable persistent
    identity serialization (they remain in snapshot markers, activation
    identity, and trace metadata).
    """
    mode = policy.get("vae_policy_mode") if isinstance(policy, Mapping) else None
    core, resolved_mode, provenance = _resolve_vae_policy_detail(mode)
    metadata = {
        "vae_policy_version": VAE_POLICY_VERSION,
        "vae_weight_dtype": core["vae_weight_dtype"],
        "vae_compute_dtype": core["vae_compute_dtype"],
        "vae_memory_format": core["vae_memory_format"],
        "vae_policy_mode": resolved_mode,
        "vae_policy_provenance": provenance,
        "vae_prefetch_mode": vae_prefetch_mode(),
        "c5_impl_version": C5_IMPL_VERSION,
    }
    if isinstance(policy, Mapping):
        for key in ("vae_policy_version", "vae_weight_dtype", "vae_compute_dtype", "vae_memory_format"):
            value = policy.get(key)
            if value not in (None, ""):
                metadata[key] = value
        prefetch = policy.get("vae_prefetch_mode")
        if prefetch not in (None, ""):
            metadata["vae_prefetch_mode"] = str(prefetch).strip().lower()
        source = policy.get("vae_policy_provenance")
        if source not in (None, ""):
            metadata["vae_policy_provenance"] = str(source)
    metadata.update(capture_c5_runtime_metadata())
    metadata["env_overrides"] = {
        "vae_policy": bool(os.environ.get(VAE_POLICY_ENV_KEY)),
        "vae_prefetch_mode": bool(os.environ.get(VAE_PREFETCH_ENV_KEY)),
        "c5_arch": bool(os.environ.get(C5_ARCH_ENV_KEY)),
        "c5_torch_version": bool(os.environ.get(C5_TORCH_VERSION_ENV_KEY)),
        "c5_cuda_version": bool(os.environ.get(C5_CUDA_VERSION_ENV_KEY)),
    }
    if not include_runtime_versions:
        metadata.pop("torch_version", None)
        metadata.pop("cuda_version", None)
    return metadata


def diagnosis_metadata(**kwargs: Any) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in kwargs.items():
        if value is not None:
            result[key] = value
    return result


_COMPATIBILITY_KEY_COUNTS: dict[str, int] = {}


def _record_compatibility_key(key: str) -> None:
    _COMPATIBILITY_KEY_COUNTS[key] = _COMPATIBILITY_KEY_COUNTS.get(key, 0) + 1


def compatibility_usage_snapshot() -> dict[str, int]:
    return dict(_COMPATIBILITY_KEY_COUNTS)


def _freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType({str(k): _freeze(v) for k, v in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(v) for v in value)
    if isinstance(value, set):
        return tuple(sorted(_freeze(v) for v in value))
    return value


def _thaw(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(k): _thaw(v) for k, v in value.items()}
    if isinstance(value, tuple):
        return [_thaw(v) for v in value]
    return value


def _jsonable(value: Any) -> Any:
    return _thaw(value)


def stable_hash(value: Any) -> str:
    encoded = json.dumps(
        _jsonable(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _normalized_ids(values: Any) -> tuple[str, ...]:
    if not isinstance(values, (list, tuple, set, frozenset)):
        return ()
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        normalized = str(value).strip()
        if normalized and normalized not in seen:
            seen.add(normalized)
            result.append(normalized)

    def sort_key(value: str) -> tuple[int, int | str]:
        try:
            return (0, int(value))
        except ValueError:
            return (1, value)

    return tuple(sorted(result, key=sort_key))


def _ordered_ids(values: Any) -> tuple[str, ...]:
    """Stringify, deduplicate, and preserve order for order-sensitive IDs.

    Unlike ``_normalized_ids`` this does NOT sort: used for execution order
    hints where the recorded sequence is semantically meaningful.
    """
    if not isinstance(values, (list, tuple, set, frozenset)):
        return ()
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        normalized = str(value).strip()
        if normalized and normalized not in seen:
            seen.add(normalized)
            result.append(normalized)
    return tuple(result)


OUTPUT_FORMATS = ("original", "webp_lossless", "webp_lossy", "jpeg")
WEBP_LOSSLESS_COMPRESSION = ("fast", "balanced", "max")
OUTPUT_MODES = ("original", "preview")
DEFAULT_OUTPUT_QUALITY = 75
DEFAULT_PREVIEW_QUALITY = 70
# E2D: encoder-effort policy.  The historical field name carries the
# fast/balanced/max vocabulary; the mapped Pillow/libwebp method integer is a
# speed/size dial at fixed quality and is applied to BOTH WebP modes.
WEBP_EFFORT_METHODS = {"fast": 0, "balanced": 4, "max": 6}
DEFAULT_WEBP_EFFORT = "balanced"
# Preview is a latency-sensitive path: freeze the fast effort unless the
# accepted request explicitly supplies one.
PREVIEW_WEBP_EFFORT = "fast"

_OUTPUT_FORMAT_ALIASES = {
    "original": "original",
    "png": "original",
    "webp": "webp_lossy",
    "webp_lossy": "webp_lossy",
    "webp-lossy": "webp_lossy",
    "webp_lossless": "webp_lossless",
    "webp-lossless": "webp_lossless",
    "jpeg": "jpeg",
    "jpg": "jpeg",
}


def normalize_output_mode(value: Any) -> str:
    """Return the explicit semantic output mode.

    Codec and filename values are deliberately not accepted as mode aliases:
    WebP can be an explicitly requested Original, so mode must be carried by
    the accepted request rather than inferred downstream.
    """
    raw = "original" if value is None else str(value).strip().lower()
    if not raw:
        raw = "original"
    if raw not in OUTPUT_MODES:
        raise ValueError(
            f"unsupported output mode {value!r}; expected one of "
            f"{', '.join(OUTPUT_MODES)}"
        )
    return raw


def build_logical_output_key(
    node_id: Any, output_key: Any, output_index: Any = 0
) -> str | None:
    """Build the stable attempt/variant/codec-independent output identity."""
    if not isinstance(node_id, str) or not isinstance(output_key, str):
        return None
    node = node_id.strip()
    slot = output_key.strip()
    if not node or not slot or isinstance(output_index, bool):
        return None
    try:
        item_index = int(output_index)
    except (TypeError, ValueError):
        return None
    if item_index < 0:
        return None
    return f"node:{node}:slot:{slot}:item:{item_index}"


def normalize_output_format(value: Any) -> str:
    """Return the canonical runtime output format or reject it."""
    raw = "original" if value is None else str(value).strip().lower()
    if not raw:
        raw = "original"
    try:
        return _OUTPUT_FORMAT_ALIASES[raw]
    except KeyError as exc:
        raise ValueError(
            f"unsupported output format {value!r}; expected one of "
            f"{', '.join(OUTPUT_FORMATS)} or the webp/png/jpg aliases"
        ) from exc


def normalize_quality(value: Any, *, default: int = DEFAULT_OUTPUT_QUALITY) -> int:
    """Coerce quality to an integer in the Pillow-supported 0-100 range."""
    try:
        if value is None:
            raise ValueError
        quality = int(float(value))
    except (TypeError, ValueError, OverflowError):
        quality = int(default)
    return max(0, min(100, quality))


def normalize_webp_lossless_compression(value: Any) -> str:
    """Return a supported WebP lossless method name."""
    raw = "balanced" if value is None else str(value).strip().lower()
    if raw not in WEBP_LOSSLESS_COMPRESSION:
        raise ValueError(
            f"unsupported webp_lossless_compression {value!r}; expected "
            f"one of {', '.join(WEBP_LOSSLESS_COMPRESSION)}"
        )
    return raw


def resolve_webp_pillow_method(effort: Any) -> int:
    """Map an encoder-effort label to the Pillow/libwebp method integer.

    Single source of truth for both WebP save seams (direct tensor sink and
    byte converter).  Unknown values fall back to the historical balanced
    method so behavior never silently drifts from the pre-E2D encoder.
    """
    try:
        normalized = normalize_webp_lossless_compression(effort)
    except ValueError:
        normalized = DEFAULT_WEBP_EFFORT
    return WEBP_EFFORT_METHODS[normalized]


def normalize_output_conversion_options(value: Mapping[str, Any] | None) -> dict[str, Any]:
    """Normalize the serializable output codec contract once at its boundary."""
    source = dict(value) if isinstance(value, Mapping) else {}
    if not source:
        return {}
    raw_format = source.get("format", source.get("output_format", "original"))
    output_format = normalize_output_format(raw_format)
    normalized = dict(source)
    normalized["format"] = output_format

    quality_default = (
        DEFAULT_PREVIEW_QUALITY
        if str(raw_format or "").strip().lower() == "webp"
        else DEFAULT_OUTPUT_QUALITY
    )
    if "quality" in source or str(raw_format or "").strip().lower() == "webp":
        normalized["quality"] = normalize_quality(source.get("quality"), default=quality_default)
    if "webp_lossless_compression" in source:
        normalized["webp_lossless_compression"] = normalize_webp_lossless_compression(
            source.get("webp_lossless_compression")
        )
    return normalized


def normalize_output_intent_options(value: Mapping[str, Any] | None) -> dict[str, Any]:
    """Freeze output mode and Preview codec settings at plan acceptance."""
    source = dict(value) if isinstance(value, Mapping) else {}
    raw_mode = source.get("output_mode")
    if raw_mode is None and "preview_enabled" in source:
        raw_mode = "preview" if bool(source.get("preview_enabled")) else "original"
    output_mode = normalize_output_mode(raw_mode)
    normalized = dict(source)
    normalized["output_mode"] = output_mode

    conversion = source.get("output_conversion_options", source.get("output_conversion"))
    conversion = dict(conversion) if isinstance(conversion, Mapping) else {}
    if output_mode == "preview":
        conversion.setdefault("format", source.get("preview_codec", "webp"))
        if conversion.get("quality") is None:
            conversion["quality"] = source.get("preview_quality", DEFAULT_PREVIEW_QUALITY)
        # E2D: freeze the fast encoder effort into the accepted Preview intent
        # so replay/history truth carries the effective lossy method.
        conversion.setdefault("webp_lossless_compression", PREVIEW_WEBP_EFFORT)
    if conversion:
        normalized["output_conversion_options"] = normalize_output_conversion_options(conversion)
        normalized["output_format"] = normalized["output_conversion_options"]["format"]
        if "quality" in normalized["output_conversion_options"]:
            normalized["quality"] = normalized["output_conversion_options"]["quality"]
        if "webp_lossless_compression" in normalized["output_conversion_options"]:
            normalized["webp_lossless_compression"] = normalized["output_conversion_options"][
                "webp_lossless_compression"
            ]
    return normalized


def _normalized_entries(values: Any) -> tuple[dict[str, Any], ...]:
    """Normalize a sequence of mapping entries into frozen, str-keyed dicts.

    Non-mapping entries are dropped; frozen mapping proxies keep the frozen
    dataclass truly immutable while staying JSON-thawable via ``to_dict``.
    """
    if not isinstance(values, (list, tuple, set, frozenset)):
        return ()
    result: list[dict[str, Any]] = []
    for item in values:
        if isinstance(item, Mapping):
            entry = dict(item)
        else:
            continue
        result.append(_freeze(entry))
    return tuple(result)


@dataclass(frozen=True)
class ExecutionOptions:
    production_enabled: bool = True
    production_output_node_ids: tuple[str, ...] = ()
    output_conversion_options: Mapping[str, Any] = field(default_factory=dict)
    result_route: str = ""
    profiling_level: str = "summary"
    requested_backend: str = "in_process"
    cancellation_options: Mapping[str, Any] = field(default_factory=dict)
    progress_options: Mapping[str, Any] = field(default_factory=dict)
    compatibility_flags: Mapping[str, Any] = field(default_factory=dict)
    legacy_passthrough: Mapping[str, Any] = field(default_factory=dict)
    output_mode: str = "original"

    def __post_init__(self) -> None:
        object.__setattr__(self, "production_output_node_ids", _normalized_ids(self.production_output_node_ids))
        output_mode = normalize_output_mode(self.output_mode)
        conversion = dict(self.output_conversion_options or {})
        if output_mode == "preview":
            conversion.setdefault("format", "webp")
            if conversion.get("quality") is None:
                conversion["quality"] = DEFAULT_PREVIEW_QUALITY
            # E2D: freeze the fast encoder effort into the accepted Preview
            # options so the serialized plan carries the effective method.
            conversion.setdefault("webp_lossless_compression", PREVIEW_WEBP_EFFORT)
        object.__setattr__(
            self,
            "output_conversion_options",
            normalize_output_conversion_options(conversion),
        )
        for name in (
            "cancellation_options",
            "progress_options",
            "compatibility_flags",
            "legacy_passthrough",
        ):
            object.__setattr__(self, name, _freeze(getattr(self, name) or {}))
        object.__setattr__(self, "production_enabled", bool(self.production_enabled))
        object.__setattr__(self, "output_mode", output_mode)
        object.__setattr__(self, "result_route", str(self.result_route or ""))
        object.__setattr__(self, "profiling_level", str(self.profiling_level or "summary").lower())
        object.__setattr__(self, "requested_backend", str(self.requested_backend or "in_process").lower())

    @classmethod
    def from_legacy(
        cls,
        value: Mapping[str, Any] | None,
        *,
        production_report: Mapping[str, Any] | None = None,
        default_production: bool = True,
    ) -> "ExecutionOptions":
        source = dict(value or {})
        production = source.get("production")
        if isinstance(production, Mapping):
            _record_compatibility_key("production")
            production_enabled = bool(production.get("enabled", default_production))
            output_ids = production.get("output_node_ids", ())
        elif isinstance(production_report, Mapping) and production_report.get("enabled"):
            production_enabled = True
            output_ids = production_report.get("output_node_ids", ())
        else:
            production_enabled = bool(default_production)
            output_ids = ()

        conversion = source.get("output_conversion_options", source.get("output_conversion"))
        if conversion is None and "output_format" in source:
            conversion = {"format": source["output_format"]}
            _record_compatibility_key("output_format")
        if conversion is None:
            conversion = {}
        elif not isinstance(conversion, Mapping):
            raise ValueError("output_conversion_options must be a mapping")
        else:
            conversion = dict(conversion)
        for key in ("quality", "webp_lossless_compression"):
            if key not in conversion and key in source:
                conversion[key] = source[key]
        raw_output_mode = source.get("output_mode")
        if raw_output_mode is None and "preview_enabled" in source:
            raw_output_mode = "preview" if bool(source.get("preview_enabled")) else "original"
        output_mode = normalize_output_mode(raw_output_mode)
        if output_mode == "preview":
            if "format" not in conversion:
                conversion["format"] = source.get("preview_codec", "webp")
            if conversion.get("quality") is None:
                conversion["quality"] = source.get("preview_quality", DEFAULT_PREVIEW_QUALITY)
        if "output_conversion" in source:
            _record_compatibility_key("output_conversion")

        runtime = source.get("runtime")
        runtime = runtime if isinstance(runtime, Mapping) else {}
        backend = source.get("requested_backend", source.get("backend", runtime.get("requested_backend", runtime.get("backend", "in_process"))))
        profile = source.get("profiling_level", source.get("profile_level", runtime.get("profiling_level", "summary")))
        cancellation = source.get("cancellation_options", source.get("cancellation", source.get("cancel", {})))
        progress = source.get("progress_options", source.get("progress", {}))
        flags = source.get("compatibility_flags", {})
        if "actual_load" in source:
            _record_compatibility_key("actual_load")
            flags = dict(flags) if isinstance(flags, Mapping) else {}
            flags.setdefault("actual_load", source["actual_load"])

        known = {
            "production",
            "output_conversion_options",
            "output_conversion",
            "output_format",
            "output_mode",
            "preview_enabled",
            "preview_codec",
            "preview_quality",
            "quality",
            "webp_lossless_compression",
            "result_route",
            "profiling_level",
            "profile_level",
            "requested_backend",
            "backend",
            "runtime",
            "cancellation_options",
            "cancellation",
            "cancel",
            "progress_options",
            "progress",
            "compatibility_flags",
            "actual_load",
            "legacy_passthrough",
        }
        passthrough = source.get("legacy_passthrough", {})
        passthrough = dict(passthrough) if isinstance(passthrough, Mapping) else {}
        for key in source:
            if key not in known:
                _record_compatibility_key(str(key))
                passthrough[str(key)] = source[key]

        if isinstance(production, Mapping):
            production_unknown = {
                str(key): value
                for key, value in production.items()
                if key not in {"enabled", "output_node_ids"}
            }
            if production_unknown:
                existing = passthrough.get("production", {})
                merged = dict(existing) if isinstance(existing, Mapping) else {}
                merged.update(production_unknown)
                passthrough["production"] = merged

        runtime_source = source.get("runtime")
        if isinstance(runtime_source, Mapping):
            runtime_unknown = {
                str(key): value
                for key, value in runtime_source.items()
                if key not in {"requested_backend", "backend", "profiling_level"}
            }
            if runtime_unknown:
                existing = passthrough.get("runtime", {})
                merged = dict(existing) if isinstance(existing, Mapping) else {}
                merged.update(runtime_unknown)
                passthrough["runtime"] = merged

        return cls(
            production_enabled=production_enabled,
            production_output_node_ids=output_ids,
            output_mode=output_mode,
            output_conversion_options=conversion,
            result_route=source.get("result_route", ""),
            profiling_level=profile,
            requested_backend=backend,
            cancellation_options=cancellation,
            progress_options=progress,
            compatibility_flags=flags,
            legacy_passthrough=passthrough,
        )

    @classmethod
    def from_dict(cls, value: Mapping[str, Any] | None) -> "ExecutionOptions":
        return cls.from_legacy(value, default_production=False)

    def to_dict(self) -> dict[str, Any]:
        return {
            "production": {
                "enabled": self.production_enabled,
                "output_node_ids": list(self.production_output_node_ids),
            },
            "output_mode": self.output_mode,
            "output_conversion_options": _thaw(self.output_conversion_options),
            "result_route": self.result_route,
            "profiling_level": self.profiling_level,
            "requested_backend": self.requested_backend,
            "cancellation_options": _thaw(self.cancellation_options),
            "progress_options": _thaw(self.progress_options),
            "compatibility_flags": _thaw(self.compatibility_flags),
            "legacy_passthrough": _thaw(self.legacy_passthrough),
        }

    def to_legacy_dict(self) -> dict[str, Any]:
        passthrough = _thaw(self.legacy_passthrough)
        result = dict(passthrough) if isinstance(passthrough, dict) else {}
        result.pop("legacy_passthrough", None)

        # Typed fields are applied after passthrough values so the canonical
        # contract always wins over stale compatibility data.
        result["production"] = {
            **(
                dict(result.get("production", {}))
                if isinstance(result.get("production"), Mapping)
                else {}
            ),
            "enabled": self.production_enabled,
            "output_node_ids": list(self.production_output_node_ids),
        }
        result["output_conversion_options"] = _thaw(self.output_conversion_options)
        result["output_mode"] = self.output_mode
        result["result_route"] = self.result_route
        result["profiling_level"] = self.profiling_level
        result["requested_backend"] = self.requested_backend
        result["cancellation_options"] = _thaw(self.cancellation_options)
        result["progress_options"] = _thaw(self.progress_options)
        result["compatibility_flags"] = _thaw(self.compatibility_flags)

        runtime = result.get("runtime")
        runtime = dict(runtime) if isinstance(runtime, Mapping) else {}
        runtime["requested_backend"] = self.requested_backend
        runtime["profiling_level"] = self.profiling_level
        result["runtime"] = runtime

        conversion = _thaw(self.output_conversion_options)
        if isinstance(conversion, dict) and "format" in conversion:
            result["output_format"] = conversion["format"]
        if isinstance(conversion, dict) and "quality" in conversion:
            result["quality"] = conversion["quality"]
        if isinstance(conversion, dict) and "webp_lossless_compression" in conversion:
            result["webp_lossless_compression"] = conversion["webp_lossless_compression"]
        flags = _thaw(self.compatibility_flags)
        actual_load = flags.get("actual_load") if isinstance(flags, dict) else None
        if isinstance(actual_load, Mapping):
            result["actual_load"] = dict(actual_load)
        return result


# Schema version for the plan-carried host-side validation proof payload
# (ExecutionPlan.validation).  Bump on any incompatible change to the
# payload shape consumed by instrumentation/tooling.
VALIDATION_PROOF_SCHEMA_VERSION = 1

# Schema version for the canonical deployment-static proof frozen into
# BootstrapState at snapshot creation (executor-side, never consumed by
# decisions in Step 2).
DEPLOYMENT_PROOF_SCHEMA_VERSION = 1


def compute_registry_fingerprint(class_mappings=None, *, roots=None) -> str:
    """Deterministic SHA-256 over the custom-node class registry.

    Pure and lazy: ``nodes`` is imported only when ``class_mappings`` is not
    supplied.  When *roots* is a non-empty iterable of directory paths, only
    classes whose module file lives under one of the roots are included, so a
    consistent deployment layout yields the same fingerprint across host and
    container despite different absolute paths.  Modules that cannot be
    resolved (``sys.modules`` miss) are included conservatively.  File paths
    are never part of the hash input (path-independent).  Returns ``""``
    (ineligible — never fabricate identity) when the registry is unavailable,
    empty, or cannot be enumerated.
    """
    if class_mappings is None:
        try:
            import nodes
        except Exception:
            return ""
        class_mappings = getattr(nodes, "NODE_CLASS_MAPPINGS", None) or {}
    _norm_roots: tuple[str, ...] = ()
    if roots is not None:
        _norm_roots = tuple(
            os.path.normpath(str(r))
            for r in roots
            if str(r or "").strip()
        )
    try:
        entries = []
        for _name in sorted(str(k) for k in class_mappings.keys()):
            _cls = class_mappings[_name]
            if _norm_roots:
                _mod = sys.modules.get(getattr(_cls, "__module__", ""))
                if _mod is not None:
                    _file = str(getattr(_mod, "__file__", "") or "")
                    if _file:
                        _norm_file = os.path.normpath(_file)
                        if not any(
                            _norm_file == _root or _norm_file.startswith(_root + os.sep)
                            for _root in _norm_roots
                        ):
                            continue
                # module not resolvable -> include the class conservatively
            entries.append(f"{_name}={getattr(_cls, '__module__', '')}.{getattr(_cls, '__qualname__', '')}")
        if not entries:
            return ""
        return hashlib.sha256("\n".join(entries).encode("utf-8")).hexdigest()
    except Exception:
        return ""


def evaluate_plan_snapshot_parity(plan_identity: Mapping | None, snapshot_proof: Mapping | None) -> dict:
    """Exact-match matrix between plan-carried deployment identity and the
    frozen snapshot proof.  Never consumed by decisions in Step 2.

    The AUTHORITATIVE registry axis is the workflow-relevant registry proof:
    the plan must carry a complete per-class canonical-identity proof for the
    workflow's own class set and that proof must match the snapshot's registry
    manifest for exactly those classes.  The legacy full-registry fingerprint
    equality is still computed but only as DIAGNOSTIC (``registry_fingerprint_match``).
    """
    # Lazy import keeps this module stdlib-only at import time.
    from comfymodal_runtime.registry_proof import evaluate_workflow_registry_parity
    _plan = dict(plan_identity or {})
    _proof = dict(snapshot_proof or {})
    _dep_match = bool(_plan.get("deployment_combined_hash") and _proof.get("deployment_combined_hash")
                      and _plan["deployment_combined_hash"] == _proof["deployment_combined_hash"])
    _gen_match = bool(_plan.get("custom_nodes_generation") and _proof.get("custom_nodes_generation")
                      and _plan["custom_nodes_generation"] == _proof["custom_nodes_generation"])
    _reg_parity = evaluate_workflow_registry_parity(_plan.get("registry_proof"), _proof.get("registry_manifest"))
    _reg_match = bool(_plan.get("registry_proof_complete")) and bool(_reg_parity.get("workflow_registry_match"))
    # When the planner supplies the optional exact binding, reject a proof
    # copied from a different dispatch workflow.  Legacy frozen identities
    # without this field retain the existing class-set parity behavior.
    _plan_workflow_hash = str(_plan.get("workflow_hash", "") or "")
    _plan_registry_proof = _plan.get("registry_proof")
    _proof_workflow_hash = str(
        _plan_registry_proof.get("workflow_hash", "")
        if isinstance(_plan_registry_proof, Mapping) else ""
    )
    _workflow_binding_ok = not _plan_workflow_hash or not _proof_workflow_hash or _plan_workflow_hash == _proof_workflow_hash
    if not _workflow_binding_ok:
        _reg_match = False
    # Legacy full-registry fingerprint equality — DIAGNOSTIC ONLY (never an
    # eligibility blocker).
    _reg_full_match = bool(_plan.get("registry_fingerprint") and _proof.get("registry_fingerprint")
                           and _plan["registry_fingerprint"] == _proof["registry_fingerprint"])
    _dep_proof_match = bool(_plan.get("dependency_manifest_identity") and _proof.get("dependency_manifest_identity")
                            and _plan["dependency_manifest_identity"] == _proof["dependency_manifest_identity"])
    _schema_ok = bool(_proof.get("schema_version") and _proof.get("valid"))
    _eligible = bool(_plan.get("complete") and _proof.get("complete") and _schema_ok
                     and _dep_match and _gen_match and _reg_match and _dep_proof_match)
    _reasons = []
    if not _plan.get("complete"):
        _reasons.append("plan_identity_incomplete")
    if not _proof.get("complete"):
        _reasons.append("snapshot_proof_incomplete")
    if not _schema_ok:
        _reasons.append("snapshot_proof_invalid_or_unsupported")
    if not _dep_match:
        _reasons.append("deployment_hash_mismatch")
    if not _gen_match:
        _reasons.append("custom_nodes_generation_mismatch")
    if not _reg_match:
        _reasons.append("workflow_registry_mismatch")
    if not _dep_proof_match:
        _reasons.append("dependency_proof_mismatch")
    return {
        "plan_validation_schema": _plan.get("schema_version", 0),
        "plan_deployment_complete": bool(_plan.get("complete", False)),
        "snapshot_proof_present": bool(_proof),
        "snapshot_proof_complete": bool(_proof.get("complete", False)),
        "snapshot_proof_valid": bool(_proof.get("valid", False)),
        "deployment_hash_match": _dep_match,
        "custom_nodes_generation_match": _gen_match,
        # Full-registry fingerprint equality — DIAGNOSTIC only now.
        "registry_fingerprint_match": _reg_full_match,
        # Workflow-relevant registry proof parity — the AUTHORITATIVE axis.
        "workflow_registry_match": _reg_match,
        "registry_parity_reason": str(_reg_parity.get("reason", "") or ""),
        "registry_parity_counts": {
            k: _reg_parity.get(k)
            for k in ("workflow_class_count", "host_proved_count", "snapshot_proved_count",
                      "missing_host_total", "missing_snapshot_total", "identity_mismatch_total")
        },
        "dependency_proof_match": _dep_proof_match,
        "future_fast_path_eligible": _eligible,
        "future_fast_path_ineligible_reason": ",".join(_reasons) if not _eligible else "",
    }


def evaluate_plan_validation_consumption(
    parity: Mapping | None,
    plan_validation: Mapping | None,
    *,
    workflow_hash_match: bool,
    validation_hash_match: bool,
    structure_ok: bool,
    outputs_nonempty: bool,
) -> dict:
    """Final Step-3 decision: may plan-carried validation be consumed?

    Pure and decision-free for tests; modal_app applies it.  Never trusts the
    plan-provided workflow hash (the caller passes the recompute result).
    """
    _pv = dict(plan_validation or {})
    _parity = dict(parity or {})
    _schema_ok = _pv.get("schema_version") == VALIDATION_PROOF_SCHEMA_VERSION
    _validated = bool(_pv.get("validated", False))
    _parity_eligible = bool(_parity.get("future_fast_path_eligible", False))
    _eligible = bool(
        _parity_eligible and _schema_ok and _validated
        and validation_hash_match and workflow_hash_match
        and structure_ok and outputs_nonempty
    )
    _reasons = []
    if not _parity_eligible:
        _reasons.append(_parity.get("future_fast_path_ineligible_reason") or "parity_ineligible")
    if not _schema_ok:
        _reasons.append("unsupported_validation_schema")
    if not _validated:
        _reasons.append("validation_not_validated")
    if not validation_hash_match:
        _reasons.append("validation_hash_mismatch")
    if not workflow_hash_match:
        _reasons.append("workflow_hash_mismatch")
    if not structure_ok:
        _reasons.append("structure_check_failed")
    if not outputs_nonempty:
        _reasons.append("empty_outputs")
    return {"eligible": _eligible, "ineligible_reason": ",".join(_reasons) if not _eligible else ""}


def apply_repair_invalidation(consumed: bool, reason: str) -> tuple[bool, str]:
    """Oracle Gate-2: a missing-node repair invalidates a consumed plan-proof.

    Returns the post-repair ``(consumed, reason)`` pair.  Pure and testable;
    the runtime applies it so the plan-proof state is cleared before the
    legacy re-validation path runs.
    """
    if consumed:
        return (False, str(reason or "repair_changed"))
    return (consumed, str(reason or ""))


def should_write_validation_cert(scheduled: bool, preflight_ran: bool) -> bool:
    """A validation certificate is written only when scheduled AND preflight
    actually ran (never on a cert/plan-proof skip)."""
    return bool(scheduled and preflight_ran)


@dataclass(frozen=True)
class ExecutionPlan:
    schema_version: int = 1
    workflow: Mapping[str, Any] = field(default_factory=dict)
    workflow_hash: str = ""
    source_workflow_hash: str = ""
    production_report: Mapping[str, Any] = field(default_factory=dict)
    model_stack: Mapping[str, Any] = field(default_factory=dict)
    prompt_bundle: Mapping[str, Any] = field(default_factory=dict)
    output_node_ids: tuple[str, ...] = ()
    input_images: Mapping[str, str] = field(default_factory=dict)
    execution_options: ExecutionOptions = field(default_factory=ExecutionOptions)
    request_metadata: Mapping[str, Any] = field(default_factory=dict)
    # Step-1 plan-carried workflow-validation proof + deployment identity.
    # Carried and instrumented only — never consumed by the container's
    # validation/certificate decision path.
    validation: Mapping[str, Any] = field(default_factory=dict)
    deployment_identity: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "workflow", _freeze(self.workflow or {}))
        object.__setattr__(self, "production_report", _freeze(self.production_report or {}))
        object.__setattr__(self, "model_stack", _freeze(self.model_stack or {}))
        object.__setattr__(self, "prompt_bundle", _freeze(self.prompt_bundle or {}))
        object.__setattr__(self, "input_images", _freeze(self.input_images or {}))
        object.__setattr__(self, "request_metadata", _freeze(self.request_metadata or {}))
        object.__setattr__(self, "validation", _freeze(self.validation or {}))
        object.__setattr__(self, "deployment_identity", _freeze(self.deployment_identity or {}))
        if not isinstance(self.execution_options, ExecutionOptions):
            object.__setattr__(self, "execution_options", ExecutionOptions.from_dict(self.execution_options))
        output_ids = self.output_node_ids
        if not output_ids and isinstance(self.production_report, Mapping):
            output_ids = self.production_report.get("output_node_ids", ())
        object.__setattr__(self, "output_node_ids", _normalized_ids(output_ids))
        workflow_hash = self.workflow_hash or stable_hash(self.workflow)
        object.__setattr__(self, "workflow_hash", str(workflow_hash))
        object.__setattr__(self, "source_workflow_hash", str(self.source_workflow_hash or workflow_hash))

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "ExecutionPlan":
        source = dict(value)
        return cls(
            schema_version=int(source.get("schema_version", 1)),
            workflow=source.get("workflow", {}),
            workflow_hash=str(source.get("workflow_hash", "")),
            source_workflow_hash=str(source.get("source_workflow_hash", "")),
            production_report=source.get("production_report", {}),
            model_stack=source.get("model_stack", {}),
            prompt_bundle=source.get("prompt_bundle", {}),
            output_node_ids=source.get("output_node_ids", ()),
            input_images=source.get("input_images", {}),
            execution_options=ExecutionOptions.from_dict(source.get("execution_options", {})),
            request_metadata=source.get("request_metadata", {}),
            validation=dict(source.get("validation") or {}),
            deployment_identity=dict(source.get("deployment_identity") or {}),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "workflow": _thaw(self.workflow),
            "workflow_hash": self.workflow_hash,
            "source_workflow_hash": self.source_workflow_hash,
            "production_report": _thaw(self.production_report),
            "model_stack": _thaw(self.model_stack),
            "prompt_bundle": _thaw(self.prompt_bundle),
            "output_node_ids": list(self.output_node_ids),
            "input_images": _thaw(self.input_images),
            "execution_options": self.execution_options.to_dict(),
            "request_metadata": _thaw(self.request_metadata),
            "validation": _thaw(self.validation) if self.validation else {},
            "deployment_identity": _thaw(self.deployment_identity) if self.deployment_identity else {},
        }


@dataclass(frozen=True)
class ModelRestoreKey:
    unet_identity: str = ""
    clip_identity: str = ""
    vae_identity: str = ""
    clip_type: str = ""
    loader_configuration: Mapping[str, Any] = field(default_factory=dict)
    model_volume_generation: str = ""
    optimization_loader_options: Mapping[str, Any] = field(default_factory=dict)
    vae_policy_version: int = VAE_POLICY_VERSION
    vae_weight_dtype: str = "float32"
    vae_compute_dtype: str = "float32"
    vae_memory_format: str = "contiguous"
    vae_policy_metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for name in ("loader_configuration", "optimization_loader_options"):
            object.__setattr__(self, name, _freeze(getattr(self, name) or {}))
        for name in ("unet_identity", "clip_identity", "vae_identity", "clip_type", "model_volume_generation"):
            object.__setattr__(self, name, str(getattr(self, name) or ""))
        object.__setattr__(self, "vae_policy_version", int(self.vae_policy_version or 0))
        for name in ("vae_weight_dtype", "vae_compute_dtype", "vae_memory_format"):
            object.__setattr__(self, name, str(getattr(self, name) or ""))
        object.__setattr__(self, "vae_policy_metadata", _freeze(self.vae_policy_metadata or {}))

    @classmethod
    def from_dict(cls, value: Mapping[str, Any] | None) -> "ModelRestoreKey":
        source = dict(value or {})
        vae_identity = source.get("vae_identity", source.get("vae", ""))
        policy = resolve_vae_policy()
        # Unmarked or partially-marked VAEs fall back to the canonical
        # model-key policy values (never zero/empty markers) so request and
        # snapshot identities stay stable for VAEs that predate the policy
        # fields.  Present fields always win; missing fields default.
        return cls(
            unet_identity=source.get("unet_identity", source.get("unet", "")),
            clip_identity=source.get("clip_identity", source.get("clip", "")),
            vae_identity=vae_identity,
            clip_type=source.get("clip_type", ""),
            loader_configuration=source.get("loader_configuration", source.get("loader_config", {})),
            model_volume_generation=str(source.get("model_volume_generation", source.get("model_generation", ""))),
            optimization_loader_options=source.get("optimization_loader_options", source.get("optimization_options", {})),
            vae_policy_version=source.get("vae_policy_version", policy["vae_policy_version"]),
            vae_weight_dtype=source.get("vae_weight_dtype", policy["vae_weight_dtype"]),
            vae_compute_dtype=source.get("vae_compute_dtype", policy["vae_compute_dtype"]),
            vae_memory_format=source.get("vae_memory_format", policy["vae_memory_format"]),
            vae_policy_metadata=source.get(
                "vae_policy_metadata",
                build_vae_policy_metadata(include_runtime_versions=False),
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "unet_identity": self.unet_identity,
            "clip_identity": self.clip_identity,
            "vae_identity": self.vae_identity,
            "clip_type": self.clip_type,
            "loader_configuration": _thaw(self.loader_configuration),
            "model_volume_generation": self.model_volume_generation,
            "optimization_loader_options": _thaw(self.optimization_loader_options),
            "vae_policy_version": self.vae_policy_version,
            "vae_weight_dtype": self.vae_weight_dtype,
            "vae_compute_dtype": self.vae_compute_dtype,
            "vae_memory_format": self.vae_memory_format,
            "vae_policy_metadata": _thaw(self.vae_policy_metadata),
        }

    @property
    def stable_hash(self) -> str:
        return stable_hash(self.to_dict())


@dataclass(frozen=True)
class PrefillKey:
    model_key: ModelRestoreKey = field(default_factory=ModelRestoreKey)
    prompt_bundle_hash: str = ""
    encode_options: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.model_key, ModelRestoreKey):
            object.__setattr__(self, "model_key", ModelRestoreKey.from_dict(self.model_key))
        object.__setattr__(self, "prompt_bundle_hash", str(self.prompt_bundle_hash or ""))
        object.__setattr__(self, "encode_options", _freeze(self.encode_options or {}))

    @classmethod
    def from_dict(cls, value: Mapping[str, Any] | None) -> "PrefillKey":
        source = dict(value or {})
        return cls(
            model_key=ModelRestoreKey.from_dict(source.get("model_key", {})),
            prompt_bundle_hash=str(source.get("prompt_bundle_hash", source.get("bundle_hash", ""))),
            encode_options=source.get("encode_options", {}),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "model_key": self.model_key.to_dict(),
            "prompt_bundle_hash": self.prompt_bundle_hash,
            "encode_options": _thaw(self.encode_options),
        }

    @property
    def stable_hash(self) -> str:
        return stable_hash(self.to_dict())


@dataclass(frozen=True)
class RestorePlan:
    schema_version: int = 1
    generation: int | str = 0
    model_key: ModelRestoreKey = field(default_factory=ModelRestoreKey)
    prefill_key: PrefillKey = field(default_factory=PrefillKey)
    model_spec: Mapping[str, Any] = field(default_factory=dict)
    prefill_spec: Mapping[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    source_workflow_hash: str = ""
    # ── Startup-cert construction fields ──
    # Captured from ExecutionPlan payload at publish time; serialized
    # by to_dict and persisted alongside source_workflow_hash.
    workflow: Mapping[str, Any] = field(default_factory=dict)
    workflow_hash: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.model_key, ModelRestoreKey):
            object.__setattr__(self, "model_key", ModelRestoreKey.from_dict(self.model_key))
        if not isinstance(self.prefill_key, PrefillKey):
            object.__setattr__(self, "prefill_key", PrefillKey.from_dict(self.prefill_key))
        object.__setattr__(self, "model_spec", _freeze(self.model_spec or {}))
        object.__setattr__(self, "prefill_spec", _freeze(self.prefill_spec or {}))
        object.__setattr__(self, "source_workflow_hash", str(self.source_workflow_hash or ""))
        object.__setattr__(self, "workflow", _freeze(self.workflow or {}))
        object.__setattr__(self, "workflow_hash", str(self.workflow_hash or ""))

    @classmethod
    def from_dict(cls, value: Mapping[str, Any] | None) -> "RestorePlan":
        source = dict(value or {})
        return cls(
            schema_version=int(source.get("schema_version", 1)),
            generation=source.get("generation", 0),
            model_key=ModelRestoreKey.from_dict(source.get("model_key", {})),
            prefill_key=PrefillKey.from_dict(source.get("prefill_key", {})),
            model_spec=source.get("model_spec", {}),
            prefill_spec=source.get("prefill_spec", {}),
            created_at=float(source.get("created_at", time.time())),
            source_workflow_hash=str(source.get("source_workflow_hash", "")),
            workflow=source.get("workflow", {}),
            workflow_hash=str(source.get("workflow_hash", source.get("source_workflow_hash", ""))),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "generation": self.generation,
            "model_key": self.model_key.to_dict(),
            "prefill_key": self.prefill_key.to_dict(),
            "model_spec": _thaw(self.model_spec),
            "prefill_spec": _thaw(self.prefill_spec),
            "created_at": self.created_at,
            "source_workflow_hash": self.source_workflow_hash,
            "workflow": _thaw(self.workflow),
            "workflow_hash": self.workflow_hash,
        }

    @property
    def canonical_hash(self) -> str:
        return stable_hash(self.to_dict())


@dataclass(frozen=True)
class OutputStrategy:
    name: str
    source: str
    priority: int = 0
    constraints: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", str(self.name))
        object.__setattr__(self, "source", str(self.source))
        object.__setattr__(self, "constraints", _freeze(self.constraints or {}))

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "source": self.source,
            "priority": self.priority,
            "constraints": _thaw(self.constraints),
        }


@dataclass(frozen=True)
class SnapshotExecutionSeed:
    """Immutable seed data for restoring cached executor state from snapshot.

    Schema v2 stores ONLY deterministic structural data — no outputs,
    conditioning tensors, latents, seed-dependent node outputs, request/client
    IDs, cancellation/progress/random state, mutable ComfyUI cache objects, or
    GPU handles.

    Built from the same canonical workflow once at snapshot startup and stored
    on the snapshotted entrypoint/bootstrap.  v1 payloads remain readable via
    ``from_dict``: schema-v2-only fields fall back to empty/derived values and
    the recorded ``schema_version`` is preserved.
    """
    schema_version: int = 2
    workflow_hash: str = ""
    source_workflow_hash: str = ""
    output_node_ids: tuple[str, ...] = ()
    reachable_node_ids: tuple[str, ...] = ()
    execution_order_hint: tuple[str, ...] = ()
    loader_node_ids: tuple[str, ...] = ()
    loader_cache_signatures: tuple[dict[str, Any], ...] = ()
    static_node_signatures: tuple[dict[str, Any], ...] = ()
    dynamic_input_map: tuple[dict[str, Any], ...] = ()
    sampler_node_ids: tuple[str, ...] = ()
    sampler_static_inputs: tuple[dict[str, Any], ...] = ()
    custom_node_generation: str = ""
    deployment_combined_hash: str = ""

    def __post_init__(self) -> None:
        workflow_hash = str(self.workflow_hash or "")
        object.__setattr__(self, "workflow_hash", workflow_hash)
        object.__setattr__(self, "source_workflow_hash", str(self.source_workflow_hash or workflow_hash))
        object.__setattr__(self, "output_node_ids", _normalized_ids(self.output_node_ids))
        object.__setattr__(self, "reachable_node_ids", _normalized_ids(self.reachable_node_ids))
        object.__setattr__(self, "execution_order_hint", _ordered_ids(self.execution_order_hint))
        object.__setattr__(self, "loader_node_ids", _normalized_ids(self.loader_node_ids))
        object.__setattr__(self, "loader_cache_signatures", _normalized_entries(self.loader_cache_signatures))
        object.__setattr__(self, "static_node_signatures", _normalized_entries(self.static_node_signatures))
        object.__setattr__(self, "dynamic_input_map", _normalized_entries(self.dynamic_input_map))
        object.__setattr__(self, "sampler_node_ids", _normalized_ids(self.sampler_node_ids))
        object.__setattr__(self, "sampler_static_inputs", _normalized_entries(self.sampler_static_inputs))
        object.__setattr__(self, "custom_node_generation", str(self.custom_node_generation or ""))
        object.__setattr__(self, "deployment_combined_hash", str(self.deployment_combined_hash or ""))

    @classmethod
    def from_dict(cls, value: Mapping[str, Any] | None) -> "SnapshotExecutionSeed":
        """Restore a seed from a dict, tolerating v1 or partial payloads.

        Only known structural keys are read; any forbidden runtime state
        (outputs, latents, request IDs, caches, ...) present in the source is
        ignored and never deserialized.
        """
        source = dict(value or {})
        workflow_hash = str(source.get("workflow_hash", ""))
        return cls(
            schema_version=int(source.get("schema_version", 2)),
            workflow_hash=workflow_hash,
            source_workflow_hash=str(source.get("source_workflow_hash", workflow_hash)),
            output_node_ids=source.get("output_node_ids", ()),
            reachable_node_ids=source.get("reachable_node_ids", ()),
            execution_order_hint=source.get("execution_order_hint", ()),
            loader_node_ids=source.get("loader_node_ids", ()),
            loader_cache_signatures=source.get("loader_cache_signatures", ()),
            static_node_signatures=source.get("static_node_signatures", ()),
            dynamic_input_map=source.get("dynamic_input_map", ()),
            sampler_node_ids=source.get("sampler_node_ids", ()),
            sampler_static_inputs=source.get("sampler_static_inputs", ()),
            custom_node_generation=str(source.get("custom_node_generation", "")),
            deployment_combined_hash=str(source.get("deployment_combined_hash", "")),
        )

    @property
    def stable_hash(self) -> str:
        """Deterministic hash over ALL structural identity fields.

        Includes the schema version, workflow hashes, topology, loader and
        sampler fields.  Never includes outputs, conditioning, latents,
        random/request/client/cancellation/progress state, or mutable objects.
        """
        return stable_hash(self.to_dict())

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "workflow_hash": self.workflow_hash,
            "source_workflow_hash": self.source_workflow_hash,
            "output_node_ids": list(self.output_node_ids),
            "reachable_node_ids": list(self.reachable_node_ids),
            "execution_order_hint": list(self.execution_order_hint),
            "loader_node_ids": list(self.loader_node_ids),
            "loader_cache_signatures": [_thaw(entry) for entry in self.loader_cache_signatures],
            "static_node_signatures": [_thaw(entry) for entry in self.static_node_signatures],
            "dynamic_input_map": [_thaw(entry) for entry in self.dynamic_input_map],
            "sampler_node_ids": list(self.sampler_node_ids),
            "sampler_static_inputs": [_thaw(entry) for entry in self.sampler_static_inputs],
            "custom_node_generation": self.custom_node_generation,
            "deployment_combined_hash": self.deployment_combined_hash,
        }


@dataclass(frozen=True)
class DeploymentIdentity:
    schema_version: int = DEPLOYMENT_IDENTITY_SCHEMA_VERSION
    runtime_hash: str = ""
    dependency_hash: str = ""
    custom_node_hash: str = ""
    source_bytes: int = 0
    file_hashes: Mapping[str, str] = field(default_factory=dict)
    # Compatibility records may carry the canonical image-plan deployment
    # hash.  When present it is authoritative; ``combined_hash`` is only its
    # compatibility alias.  An absent value retains the source-only hash for
    # standalone legacy callers and is explicitly marked by the namespace.
    deployment_hash: str = ""
    hash_namespace: str = SOURCE_IDENTITY_HASH_NAMESPACE

    def __post_init__(self) -> None:
        object.__setattr__(self, "file_hashes", _freeze(self.file_hashes or {}))

    @property
    def combined_hash(self) -> str:
        if self.deployment_hash:
            return self.deployment_hash
        return stable_hash({
            "hash_namespace": self.hash_namespace,
            "schema_version": self.schema_version,
            "runtime_hash": self.runtime_hash,
            "dependency_hash": self.dependency_hash,
            "custom_node_hash": self.custom_node_hash,
            "file_hashes": _thaw(self.file_hashes),
        })

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "runtime_hash": self.runtime_hash,
            "dependency_hash": self.dependency_hash,
            "custom_node_hash": self.custom_node_hash,
            "source_bytes": self.source_bytes,
            "file_hashes": _thaw(self.file_hashes),
            "deployment_hash": self.deployment_hash,
            "hash_namespace": self.hash_namespace,
            "combined_hash": self.combined_hash,
        }

    def with_deployment_hash(self, deployment_hash: str) -> "DeploymentIdentity":
        """Attach the canonical image-plan hash without changing source data."""
        return replace(
            self,
            deployment_hash=str(deployment_hash or ""),
            hash_namespace=DEPLOYMENT_HASH_NAMESPACE,
        )


@dataclass(frozen=True)
class TraceEvent:
    name: str
    process: str = "local"
    phase: str = ""
    wall_unix_ns: int = field(default_factory=time.time_ns)
    monotonic_ns: int = field(default_factory=time.monotonic_ns)
    request_id: str = ""
    container_session_id: str = ""
    trace_id: str = ""
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "metadata", _freeze(self.metadata or {}))
        object.__setattr__(self, "name", str(self.name))
        object.__setattr__(self, "process", str(self.process))
        object.__setattr__(self, "phase", str(self.phase))

    @classmethod
    def now(
        cls,
        name: str,
        *,
        process: str = "local",
        phase: str = "",
        request_id: str = "",
        container_session_id: str = "",
        trace_id: str = "",
        metadata: Mapping[str, Any] | None = None,
    ) -> "TraceEvent":
        """Create a TraceEvent capturing both wall and monotonic clocks NOW.

        Same-process duration calculations use ``monotonic_ns`` exclusively.
        Cross-process correlation uses ``wall_unix_ns`` only.
        """
        return cls(
            name=name,
            process=process,
            phase=phase,
            wall_unix_ns=time.time_ns(),
            monotonic_ns=time.monotonic_ns(),
            request_id=request_id,
            container_session_id=container_session_id,
            trace_id=trace_id,
            metadata=metadata or {},
        )

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "TraceEvent":
        source = dict(value)
        return cls(
            name=str(source.get("name", "")),
            process=str(source.get("process", "legacy")),
            phase=str(source.get("phase", "legacy")),
            wall_unix_ns=int(source.get("wall_unix_ns", source.get("wall_ns", time.time_ns()))),
            monotonic_ns=int(source.get("monotonic_ns", source.get("mono_ns", 0))),
            request_id=str(source.get("request_id", "")),
            container_session_id=str(source.get("container_session_id", source.get("container_session", ""))),
            trace_id=str(source.get("trace_id", "")),
            metadata=source.get("metadata", {}),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "process": self.process,
            "phase": self.phase,
            "wall_unix_ns": self.wall_unix_ns,
            "monotonic_ns": self.monotonic_ns,
            "request_id": self.request_id,
            "container_session_id": self.container_session_id,
            "trace_id": self.trace_id,
            "metadata": _thaw(self.metadata),
        }


# ── Canonical per-role identity for cold-path acceptance ──────────────────


def compute_loader_role_identity(
    role: str,
    spec: Mapping[str, Any],
    custom_node_generation: str = "",
    deployment_combined_hash: str = "",
    static_model_patches_hash: str = "",
    *,
    effective_compute_dtype_label: str = "",
    model_configuration_hash: str = "",
) -> dict[str, str]:
    """Compute canonical identity for a single loader role from a model_spec.

    Used for both CPU snapshot restore matching (Plan A) and executor
    cache seeding (Plan B).  Returns a dict with identity fields and a
    ``stable_id`` hash that captures all fields relevant to this role.

    Parameters
    ----------
    role:
        One of ``"unet"``, ``"clip"``, ``"vae"``.
    spec:
        A ``model_spec`` dict with a ``loaders`` key containing per-role
        loader entry lists (the shape produced by ``build_restore_model_spec``
        and ``identity_from_profile``).
    custom_node_generation:
        Custom-node generation value for identity comparison.
    deployment_combined_hash:
        Deployment identity hash for identity comparison.
    static_model_patches_hash:
        *Deprecated — no longer included in identity.*  Kept for caller
        compatibility; unused.
    effective_compute_dtype_label:
        *Deprecated — no longer included in identity.*  Kept for caller
        compatibility; unused.
    model_configuration_hash:
        *Deprecated — no longer included in identity.*  Kept for caller
        compatibility; unused.
    """
    loaders_raw = (spec or {}).get("loaders", {}) if isinstance(spec, Mapping) else {}
    entries = list(loaders_raw.get(role, [])) if isinstance(loaders_raw, Mapping) else []

    base: dict[str, str] = {
        "role": role,
        "custom_node_generation": custom_node_generation or "",
        "deployment_combined_hash": deployment_combined_hash or "",
    }

    if role == "unet":
        unet_entries = tuple(
            (
                str(e.get("unet_name", "")),
                str(e.get("weight_dtype", "default")),
                str(e.get("loader_class", "")),
            )
            for e in entries
            if isinstance(e, Mapping)
        )
        base["model_identity"] = ";".join(f"{n}:{d}:{c}" for n, d, c in unet_entries)
        base["weight_dtype"] = unet_entries[0][1] if unet_entries else ""
        base["loader_class"] = unet_entries[0][2] if unet_entries else ""
        base["loader_count"] = str(len(unet_entries))
    elif role == "clip":
        clip_parts: list[str] = []
        for e in entries:
            if not isinstance(e, Mapping):
                continue
            lc = str(e.get("loader_class", ""))
            if "clip_name1" in e:
                clip_parts.append(
                    f"{e.get('clip_name1','')}||{e.get('clip_name2','')}:{lc}"
                )
            else:
                clip_parts.append(f"{str(e.get('clip_name', ''))}:{lc}")
        base["model_identity"] = ";".join(clip_parts) if clip_parts else ""
        base["loader_class"] = str(entries[0].get("loader_class", "")) if entries else ""
        base["clip_type"] = str(entries[0].get("type", "")) if entries else ""
        base["device"] = str(entries[0].get("device", "default")) if entries else ""
        base["device_policy"] = str(entries[0].get("device", "default")) if entries else ""
        base["loader_count"] = str(len(clip_parts))
    elif role == "vae":
        vae_entries = tuple(
            (
                str(e.get("vae_name", "")),
                str(e.get("vae_policy_version", 0)),
                str(e.get("vae_weight_dtype", "legacy_unset")),
                str(e.get("vae_compute_dtype", "legacy_unset")),
                str(e.get("vae_memory_format", "legacy_unset")),
                str(e.get("vae_prefetch_mode", "legacy_unset")),
                str(e.get("c5_impl_version", "legacy_unset")),
            )
            for e in entries
            if isinstance(e, Mapping)
        )
        base["model_identity"] = ";".join(":".join(entry) for entry in vae_entries) if vae_entries else ""
        base["vae_policy_version"] = vae_entries[0][1] if vae_entries else ""
        base["vae_weight_dtype"] = vae_entries[0][2] if vae_entries else ""
        base["vae_compute_dtype"] = vae_entries[0][3] if vae_entries else ""
        base["vae_memory_format"] = vae_entries[0][4] if vae_entries else ""
        base["vae_prefetch_mode"] = vae_entries[0][5] if vae_entries else ""
        base["c5_impl_version"] = vae_entries[0][6] if vae_entries else ""
        base["loader_count"] = str(len(vae_entries))
    else:
        base["model_identity"] = ""
        base["loader_count"] = "0"

    base["stable_id"] = stable_hash(base)
    return base


def find_role_identity_mismatch_fields(
    request_identity: dict[str, str],
    snapshot_identity: dict[str, str],
) -> list[str]:
    """Return ordered list of field names that differ between two role identities.

    Excludes ``stable_id`` and ``role`` from comparison.  Fields that are
    empty on both sides are not reported.  Returns empty list when identities
    are equivalent (including when both are empty/missing).
    """
    _IDENTITY_FIELDS = (
        "model_identity",
        "weight_dtype",
        "loader_class",
        "clip_type",
        "device",
        "device_policy",
        "custom_node_generation",
        "deployment_combined_hash",
        "loader_count",
        "vae_policy_version",
        "vae_weight_dtype",
        "vae_compute_dtype",
        "vae_memory_format",
        "vae_prefetch_mode",
        "c5_impl_version",
    )
    mismatched: list[str] = []
    for field in _IDENTITY_FIELDS:
        rv = request_identity.get(field, "")
        sv = snapshot_identity.get(field, "")
        # Skip when both empty — same effective value
        if not rv and not sv:
            continue
        if rv != sv:
            mismatched.append(field)
    return mismatched
