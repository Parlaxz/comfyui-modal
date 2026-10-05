"""E40 runtime configuration authority.

Golden behavior must never depend on an inherited environment setting that
this module does not expose.  This module is the runtime-side authority
contract: every environment control which can change model loading,
execution, caching, snapshot composition, or the interpretation of a Golden
run is registered here, parsed once, and represented by :class:`ResolvedConfig`.
Deploy-time resolution is deliberately out of scope.  A deployer may carry
the same names, but the runtime compares the two resolved maps rather than
silently trusting inherited process state.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass
from typing import Any, Mapping

from . import config_schema as _config_schema


LOADER_SELECTION = "LOADER_SELECTION"
EXECUTION_POLICY = "EXECUTION_POLICY"
CACHE_POLICY = "CACHE_POLICY"
SNAPSHOT_POLICY = "SNAPSHOT_POLICY"
TIMING_DIAGNOSTICS = "TIMING_DIAGNOSTICS"
DEPRECATED_DIAGNOSTIC = "DEPRECATED_DIAGNOSTIC"


# Insertion order is intentional: it is the stable order used by reconciliation
# reports and makes the registry easy to audit against the runtime env manifest.
# Reconciliation-report metadata only.  Everything a resolver needs -- name,
# type, default, enum values and description -- is read from the single
# authority in config/v2/flag_registry.toml, so a flag added there is
# resolvable here without a second definition.
_CLASSIFICATION: dict[str, str] = {
    "COMFYMODAL_V2_GOLDEN_ENABLE_DYNAMIC_VRAM": EXECUTION_POLICY,
    "COMFYMODAL_V2_GOLDEN_WORKFLOW_HASH_CHECK": EXECUTION_POLICY,
    "COMFYMODAL_V2_CLIP_QD_READER": LOADER_SELECTION,
    "COMFYMODAL_V2_CLIP_QD_QD": LOADER_SELECTION,
    "COMFYMODAL_V2_CLIP_QD_BLOCK_MIB": LOADER_SELECTION,
    "COMFYMODAL_V2_CLIP_QD_LAUNCH_POLICY": LOADER_SELECTION,
    "COMFYMODAL_V2_CLIP_FAST_HYDRATION": LOADER_SELECTION,
    "COMFYMODAL_V2_CLIP_STAGED_HYDRATION": LOADER_SELECTION,
    "COMFYMODAL_V2_SPECULATIVE_CLIP_HYDRATION": LOADER_SELECTION,
    "COMFYMODAL_V2_CLIP_FP32_CAST_ONCE": LOADER_SELECTION,
    "COMFYMODAL_V2_CLIP_SNAPSHOT_EXCLUDE_WEIGHTS": SNAPSHOT_POLICY,
    "COMFYMODAL_V2_CLIP_FASTSAFE_THREADS": LOADER_SELECTION,
    "COMFYMODAL_V2_CLIP_FASTSAFE_BLOCK_BYTES": LOADER_SELECTION,
    "COMFYMODAL_V2_CLIP_FASTSAFE_BBUF_KB": LOADER_SELECTION,
    "COMFYMODAL_V2_STAGED_PRODUCERS": LOADER_SELECTION,
    "COMFYMODAL_V2_STAGED_POOL_MB": LOADER_SELECTION,
    "COMFYMODAL_V2_STAGED_BUCKET_MB": LOADER_SELECTION,
    "COMFYMODAL_V2_STAGED_CPU_CAST": LOADER_SELECTION,
    "COMFYMODAL_V2_STAGED_ASYNC_H2D": LOADER_SELECTION,
    "COMFYMODAL_V2_STAGED_CONTIGUOUS_GPU_BUCKETS": LOADER_SELECTION,
    "COMFYMODAL_V2_STAGED_SOURCE_ORDER": LOADER_SELECTION,
    "COMFYMODAL_V2_UNET_FASTSAFETENSORS": LOADER_SELECTION,
    "COMFYMODAL_V2_UNET_META_DIRECT": LOADER_SELECTION,
    "COMFYMODAL_V2_STAGED_SAFETENSORS": LOADER_SELECTION,
    "COMFYMODAL_V2_NATIVE_FAST_DISK_UNET": LOADER_SELECTION,
    "COMFYMODAL_V2_SNAPSHOT_EXCLUDE_UNET": SNAPSHOT_POLICY,
    "COMFYMODAL_V2_UNET_ACTIVATION_MODE": EXECUTION_POLICY,
    "COMFYMODAL_V2_UNET_FASTSAFE_THREADS": LOADER_SELECTION,
    "COMFYMODAL_V2_UNET_FASTSAFE_BLOCK_BYTES": LOADER_SELECTION,
    "COMFYMODAL_V2_UNET_FASTSAFE_BBUF_KB": LOADER_SELECTION,
    "COMFYMODAL_V2_UNET_PINNED_STAGING": LOADER_SELECTION,
    "COMFYMODAL_V2_UNET_STAGING_CHUNK_MB": LOADER_SELECTION,
    "COMFYMODAL_V2_VAE_POLICY": LOADER_SELECTION,
    "COMFYMODAL_V2_VAE_ACTIVATION_MODE": EXECUTION_POLICY,
    "COMFYMODAL_V2_VAE_SNAPSHOT": SNAPSHOT_POLICY,
    "COMFYMODAL_V2_VAE_PREFETCH_MODE": EXECUTION_POLICY,
    "COMFYMODAL_V2_VAE_EARLY_START_MS": EXECUTION_POLICY,
    "COMFYMODAL_PRELOAD_MODE": EXECUTION_POLICY,
    "COMFYMODAL_V2_MODEL_PRELOAD": EXECUTION_POLICY,
    "COMFYMODAL_V2_GRAPH_PRELOAD": EXECUTION_POLICY,
    "COMFYMODAL_V2_EXECUTION_PREFILL": EXECUTION_POLICY,
    "COMFYMODAL_V2_CHECKPOINT_PREWARM": EXECUTION_POLICY,
    "COMFYMODAL_V2_CHECKPOINT_PREWARM_THREADS": EXECUTION_POLICY,
    "COMFYMODAL_V2_CHECKPOINT_PREWARM_CHUNK_MB": EXECUTION_POLICY,
    "COMFYMODAL_V2_CHECKPOINT_PREWARM_MAX_MB": EXECUTION_POLICY,
    "COMFYMODAL_V2_CHECKPOINT_PREWARM_MAX_MS": EXECUTION_POLICY,
    "COMFYMODAL_V2_CONDITIONING_CACHE_PREFETCH": CACHE_POLICY,
    "COMFYMODAL_ENABLE_WARMUP": EXECUTION_POLICY,
    "COMFYMODAL_DIRECT_WARMUP_LOAD_UNET": EXECUTION_POLICY,
    "COMFYMODAL_DIRECT_WARMUP_LOAD_CLIP": EXECUTION_POLICY,
    "COMFYMODAL_DIRECT_WARMUP_CLIP_ENCODE": EXECUTION_POLICY,
    "COMFYMODAL_V2_EXACT_CACHE_PERSIST": CACHE_POLICY,
    "COMFYMODAL_V2_BACKGROUND_PERSISTENCE": CACHE_POLICY,
    "COMFYMODAL_V2_CLIP_CONDITIONING_CACHE": CACHE_POLICY,
    "COMFYMODAL_EXACT_CLIP_CONDITIONING_CACHE": CACHE_POLICY,
    "COMFYMODAL_V2_CONDITIONING_CACHE_ASYNC_LRU": CACHE_POLICY,
    "COMFYMODAL_V2_PROMPT_SIGNATURE_CACHE": CACHE_POLICY,
    "COMFYMODAL_MINIMAL_RESTORE": EXECUTION_POLICY,
    "COMFYMODAL_GOLDEN_MINIMAL_RESTORE": EXECUTION_POLICY,
    "COMFYMODAL_GOLDEN_IO_PROCESS_V2": EXECUTION_POLICY,
    "COMFYMODAL_GOLDEN_IO_PROCESS_V2_BACKING": EXECUTION_POLICY,
    "COMFYMODAL_GOLDEN_IO_PROCESS_V2_SOURCE_GEOMETRY": EXECUTION_POLICY,
    "COMFYMODAL_GOLDEN_IO_PROCESS_V2_STREAMING": EXECUTION_POLICY,
    "COMFYMODAL_GOLDEN_IO_PROCESS_V2_PERSISTENT_FDS": EXECUTION_POLICY,
    "COMFYMODAL_GOLDEN_IO_PROCESS_V2_SOURCE_ENGINE": EXECUTION_POLICY,
    "COMFYMODAL_GOLDEN_C0_MMAP_LIFECYCLE": EXECUTION_POLICY,
    "COMFYMODAL_GOLDEN_C0_SOURCE_THREADS": EXECUTION_POLICY,
    "COMFYMODAL_GOLDEN_C0_CHILD_VIZTRACER": TIMING_DIAGNOSTICS,
    "COMFYMODAL_GOLDEN_C0_PRIVATE_SPLIT_IO": TIMING_DIAGNOSTICS,
    "COMFYMODAL_GOLDEN_C0_HOST_REGISTER": EXECUTION_POLICY,
    "COMFYMODAL_GOLDEN_C0_SHM_POPULATE": EXECUTION_POLICY,
    "COMFYMODAL_GOLDEN_C0_READER_GATE": EXECUTION_POLICY,
    "COMFYMODAL_GOLDEN_C0_DMA_RING": EXECUTION_POLICY,
    "COMFYMODAL_GOLDEN_C0_FIVE_SLOTS": EXECUTION_POLICY,
    "COMFYMODAL_GOLDEN_C0_REGISTRATION_DIAG": TIMING_DIAGNOSTICS,
    "COMFYMODAL_GOLDEN_C0_REGISTRATION_ORDER": TIMING_DIAGNOSTICS,
    "COMFYMODAL_GOLDEN_C0_REGISTRATION_CONTEXT_PREINIT": TIMING_DIAGNOSTICS,
    "COMFYMODAL_GOLDEN_CLIP_SKELETON_OVERLAP": EXECUTION_POLICY,
    "COMFYMODAL_GOLDEN_C0_SOURCE_VOLUME_V1": LOADER_SELECTION,
    "COMFYMODAL_GOLDEN_C0_PREADV_SICKNESS_DIAG": TIMING_DIAGNOSTICS,
    "COMFYMODAL_V2_CLEAN_LANE": EXECUTION_POLICY,
    "COMFYMODAL_V2_E37_CLEAN_LANE": EXECUTION_POLICY,
    "COMFYMODAL_V2_E37_STRICT_PROOF": DEPRECATED_DIAGNOSTIC,
    "COMFYMODAL_V2_E37_EXPECTED_OUTPUT_SHA": DEPRECATED_DIAGNOSTIC,
    "COMFYMODAL_V2_SINGLE_USE_CONTAINERS": EXECUTION_POLICY,
    "COMFYMODAL_V2_CRITICAL_PATH_LEDGER": TIMING_DIAGNOSTICS,
    "COMFYMODAL_V2_GANTT_TELEMETRY": TIMING_DIAGNOSTICS,
    "COMFYMODAL_GOLDEN_QD2_TELEMETRY": TIMING_DIAGNOSTICS,
    "COMFYMODAL_GOLDEN_QD2_DEFER_H2D": TIMING_DIAGNOSTICS,
    "COMFYMODAL_GOLDEN_COMPLETION_EVENT_LIFETIME": EXECUTION_POLICY,
    "COMFYMODAL_GOLDEN_IO_PROCESS_V2_MMAP_COPY_DIAG": TIMING_DIAGNOSTICS,
    "COMFYMODAL_GOLDEN_CLIP_UNET_SCHEDULE": EXECUTION_POLICY,
    "COMFYMODAL_GOLDEN_SAMPLING_VAE_SCHEDULE": EXECUTION_POLICY,
    "COMFYMODAL_V2_CRITICAL_GPU_COORDINATION": EXECUTION_POLICY,
    "COMFYMODAL_V2_THREAD_POLICY": EXECUTION_POLICY,
    "COMFYMODAL_V2_RELEASE_GPU_AFTER_REQUEST": EXECUTION_POLICY,
    "COMFYMODAL_V2_FAST_COLD_ORCHESTRATION": EXECUTION_POLICY,
    "COMFYMODAL_V2_GPU_FAST_RETURN": EXECUTION_POLICY,
    "COMFYMODAL_V2_EVICT_MODELS_BEFORE_SNAPSHOT": SNAPSHOT_POLICY,
    "COMFYMODAL_V2_CPU_MODEL_SNAPSHOT": SNAPSHOT_POLICY,
    "COMFYMODAL_V2_SNAPSHOT_MODEL_ORDER": SNAPSHOT_POLICY,
    "COMFYMODAL_V2_ENV_PROFILE": EXECUTION_POLICY,
    "COMFYMODAL_V2_PREFILL_LANES": EXECUTION_POLICY,
    "COMFYMODAL_V2_PREFILL_WAIT_FOR_UNET": EXECUTION_POLICY,
    "COMFYMODAL_V2_PERSISTENT_LOCAL_HANDLE": SNAPSHOT_POLICY,
    "COMFYMODAL_V2_EVICT_RETAIN_ROLE": SNAPSHOT_POLICY,
    "COMFYMODAL_V2_EVICT_RESTORE_IDLE_SECONDS": SNAPSHOT_POLICY,
    "COMFYMODAL_V2_ATOMIC_PROFILE": EXECUTION_POLICY,
    "COMFYMODAL_V2_SCOPED_CUDA_READINESS": EXECUTION_POLICY,
    "COMFYMODAL_V2_INPUT_TYPES_WARM": EXECUTION_POLICY,
    "COMFYMODAL_V2_RESTORE_TOTAL_VRAM_FROZEN": EXECUTION_POLICY,
    "COMFYMODAL_V2_HIGH_HEADROOM_EMPTY_CACHE_BYPASS": EXECUTION_POLICY,
    "COMFYMODAL_V2_EXECUTION_UNET_H2D_DELAY_MS": EXECUTION_POLICY,
    "COMFYMODAL_V2_UNET_READ_H2D_PIPELINE": LOADER_SELECTION,
    "COMFYMODAL_V2_UNET_PINNED_RING": LOADER_SELECTION,
    "COMFYMODAL_V2_C9QD_EXTRAS": LOADER_SELECTION,
    "COMFYMODAL_V2_PIN_UNET_TRANSFER": EXECUTION_POLICY,
    "COMFYMODAL_V2_UNET_QUIESCED_TRANSFER": EXECUTION_POLICY,
    "COMFYMODAL_EXECUTION_BACKEND": EXECUTION_POLICY,
    "COMFYMODAL_ACTUAL_LOAD_MODE": EXECUTION_POLICY,
    "COMFYMODAL_RESTORE_DIRECT_CLIP_POLICY": EXECUTION_POLICY,
    "COMFYMODAL_SAFETENSORS_READ_MODE": LOADER_SELECTION,
    "COMFYMODAL_FASTPATH_V21621": EXECUTION_POLICY,
    "COMFYMODAL_FASTPATH_V21621_BACKGROUND_UNET": EXECUTION_POLICY,
    "COMFYMODAL_FASTPATH_V21621_CLIP_LOAD_ONLY": EXECUTION_POLICY,
    "COMFYMODAL_FASTPATH_V21621_CLIP_READ_BYTES": LOADER_SELECTION,
    "COMFYMODAL_FUSE_READ_GOVERNOR": LOADER_SELECTION,
    "COMFYMODAL_DEFER_VAE_ACTUAL_LOAD_DURING_RBG_UNET": EXECUTION_POLICY,
    "COMFYMODAL_DEFER_VAE_INCLUDING_PRODUCTION_UNET": EXECUTION_POLICY,
}


# Names which are allowed to remain outside the Golden registry because they
# are diagnostics, proof/reporting metadata, harness selectors, or transport
# bookkeeping.  Entries may be exact names or suffixes (with a leading ``*``).
ALLOWLIST_UNREGISTERED = frozenset(
    {
        "COMFYMODAL_V2_E31_FORENSICS", "COMFYMODAL_V2_E31_FORWARD_PROFILE",
        "COMFYMODAL_V2_E31_CAST_SAMPLE_LIMIT", "COMFYMODAL_V2_E27_FORENSICS",
        "COMFYMODAL_V2_CLIP_COLD_FORENSICS", "COMFYMODAL_V2_CLIP_COLD_FORENSICS_CAST",
        "COMFYMODAL_V2_CLIP_COLD_FORENSICS_SYNC_CUDA", "COMFYMODAL_V2_UNET_FORENSICS",
        "COMFYMODAL_V2_RESIDENCY_DIAGNOSTICS", "COMFYMODAL_V2_DEEP_MODEL_DIAG",
        "COMFYMODAL_V2_PAGEFAULT_TRACKING", "COMFYMODAL_V2_FULL_TRACE",
        "COMFYMODAL_V2_OPTIMIZATION_DIAGNOSTICS", "COMFYMODAL_V2_SNAPSHOT_MANIFEST",
        "COMFYMODAL_V2_SNAPSHOT_ALLOCATOR_HYGIENE", "COMFYMODAL_V2_RESOURCE_TELEMETRY",
        "COMFYMODAL_V2_OBSERVABILITY_MODE", "COMFYMODAL_V2_VARIANCE_DIAGNOSTICS",
        "COMFYMODAL_V2_UNET_PRETOUCH", "COMFYMODAL_V2_CLIP_QD_ARTIFACT",
        "COMFYMODAL_V2_FULL_TRACE_ENTRIES", "COMFYMODAL_V2_FULL_TRACE_RESOURCE_INTERVAL_MS",
        "COMFYMODAL_V2_FULL_TRACE_MAX_STACK_DEPTH", "COMFYMODAL_V2_FULL_TRACE_TORCH",
        "COMFYMODAL_V2_QUIET", "COMFYMODAL_ENABLE_REMOTE_BACKGROUND_DEPLOY",
        "V2_BENCHMARK_RUNS", "V2_BENCHMARK_GAP_SECONDS", "V2_BENCHMARK_MODE",
        "V2_RESTORE_ONLY_RUN_COUNT", "V2_RESTORE_ONLY_MAX_ATTEMPTS",
        "V2_RESTORE_ONLY_GAP_SECONDS", "V2_VOLUME_READ_RUN_COUNT",
        "V2_VOLUME_READ_GAP_SECONDS", "V2_E22_CONDITIONING_NONCE",
        "V2_E25_CONDITIONING_NONCE", "V2_E26_CONDITIONING_NONCE",
        "V2_E28_CONDITIONING_NONCE", "V2_E19_FINAL_COLD_LOADER",
        "V2_D6_FASTPATH_VALIDATION", "V2_D10_INTEGRATION_VALIDATION",
        "V2_E10_BUCKET_FIRST_VALIDATION", "V2_E25_VALIDATION", "V2_E26_VALIDATION",
        "V2_E28_VALIDATION", "V2_E31_VALIDATION", "V2_E37_VALIDATION",
        "*DIAGNOSTIC", "*DIAGNOSTICS", "*FORENSICS", "*TELEMETRY", "*TRACE",
        "*ARTIFACT", "*EXPECTED_OUTPUT_SHA", "*PROOF", "*PROFILE_CONFIG_FINGERPRINT",
        "*DEPLOY_FINGERPRINT", "*RUN_FINGERPRINT", "*INVOCATION_ID",
    }
)

_ENV_NAME_RE = re.compile(r"^(?:COMFYMODAL_|V2_)")
_TRUE = frozenset({"1", "true", "yes", "on"})
_FALSE = frozenset({"0", "false", "no", "off", "", "none"})


def _coerce(raw: Any, spec: Mapping[str, Any]) -> tuple[bool, Any]:
    """Return ``(valid, normalized)`` for one raw environment value."""
    kind = spec["type"]
    if kind == "bool":
        if isinstance(raw, bool):
            return True, raw
        value = str(raw).strip().lower()
        if value in _TRUE:
            return True, True
        if value in _FALSE:
            return True, False
        return False, spec["default"]
    if kind == "int":
        if isinstance(raw, bool):
            return False, spec["default"]
        try:
            value = int(str(raw).strip(), 10)
        except (TypeError, ValueError):
            return False, spec["default"]
        return True, value
    if kind == "float":
        if isinstance(raw, bool):
            return False, spec["default"]
        try:
            return True, float(str(raw).strip())
        except (TypeError, ValueError):
            return False, spec["default"]
    value = str(raw).strip()
    if kind == "enum" and value.lower() not in {str(item).lower() for item in spec.get("choices", ())}:
        return False, spec["default"]
    return True, value.lower() if kind == "enum" else value


_REGISTRY_INDEX: dict[str, dict[str, Any]] = {
    str(entry.get("name")): entry
    for entry in _config_schema.load_registry()
    if isinstance(entry.get("name"), str)
}


def _spec_from_registry(name: str, classification: str) -> dict[str, Any]:
    """Build one resolver spec from the flag registry's declaration.

    The registry owns the facts.  ``enum_values`` implies the enum type, because
    the registry stores a closed choice set as a string plus its allowed values.
    Its defaults are stored as strings, so the declared default is coerced here
    and keeps the Python type the resolver has always returned -- the
    ``ResolvedConfig`` fingerprint hashes these values.
    """
    entry = _REGISTRY_INDEX[name]
    choices = tuple(entry.get("enum_values") or ())
    type_ = "enum" if choices else str(entry.get("type", "string"))
    spec: dict[str, Any] = {
        "name": name,
        "env_var": name,
        "type": type_,
        "classification": classification,
        "description": str(entry.get("description", "")),
    }
    if choices:
        spec["choices"] = choices
    spec["default"] = _coerce(str(entry.get("default", "")), spec)[1]
    return spec


#: Every control the runtime resolves, built from the registry.  A flag that is
#: not declared in the registry cannot be resolved, which is the invariant that
#: stops a second specification table from reappearing here.
GOLDEN_CONTROL_FLAGS: dict[str, dict[str, Any]] = {
    name: _spec_from_registry(name, classification)
    for name, classification in _CLASSIFICATION.items()
}


_MISSING_FROM_REGISTRY = sorted(set(_CLASSIFICATION) - set(_REGISTRY_INDEX))
if _MISSING_FROM_REGISTRY:  # pragma: no cover - guarded by test_config_authority_*
    raise RuntimeError(
        "flags resolved at runtime but absent from config/v2/flag_registry.toml: "
        + ", ".join(_MISSING_FROM_REGISTRY)
    )


def _resolve_mapping(environment: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, str]]:
    values: dict[str, Any] = {}
    sources: dict[str, str] = {}
    for name, spec in GOLDEN_CONTROL_FLAGS.items():
        if name not in environment:
            values[name] = spec["default"]
            sources[name] = "default"
            continue
        valid, value = _coerce(environment[name], spec)
        values[name] = value
        sources[name] = "environment" if valid else "invalid_fallback_to_default"
    return values, sources


@dataclass(frozen=True)
class ResolvedConfig:
    """One immutable-at-the-contract-boundary snapshot of runtime controls."""

    values: dict[str, Any]
    sources: dict[str, str]

    def fingerprint(self) -> str:
        canonical = json.dumps(self.values, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def get(self, name: str, default: Any = None) -> Any:
        return self.values.get(name, default)

    def as_dict(self) -> dict[str, Any]:
        return dict(self.values)


def resolve(env: Mapping[str, Any] | None = None) -> ResolvedConfig:
    """Read the process environment once and return normalized Golden values."""
    environment = dict(os.environ if env is None else env)
    values, sources = _resolve_mapping(environment)
    return ResolvedConfig(values, sources)


def reconcile(
    deployed_env: Mapping[str, Any], runtime_env: Mapping[str, Any] | None = None
) -> list[dict[str, Any]]:
    """Compare two independently supplied environments, flag by flag.

    The two-argument form is the E40 contract.  A one-argument call is kept
    useful for callers migrating from the old ``observed_env`` wording: it
    compares that mapping with itself and therefore reports no false drift.
    Both sides are normalized with this registry, so spelling differences such
    as ``"1"`` and ``"true"`` agree for boolean controls.
    """
    right = deployed_env if runtime_env is None else runtime_env
    deployed_values, _ = _resolve_mapping(dict(deployed_env))
    runtime_values, _ = _resolve_mapping(dict(right))
    return [
        {
            "flag": name,
            "deployed": deployed_values[name],
            "runtime": runtime_values[name],
            "agree": deployed_values[name] == runtime_values[name],
        }
        for name in GOLDEN_CONTROL_FLAGS
    ]


def _is_allowlisted(name: str) -> bool:
    if name in ALLOWLIST_UNREGISTERED:
        return True
    return any(item.startswith("*") and name.endswith(item[1:]) for item in ALLOWLIST_UNREGISTERED)


def detect_unregistered_mutations(runtime_env: Mapping[str, Any]) -> list[str]:
    """Return sorted algorithm-looking env names not exposed by the authority."""
    return sorted(
        name
        for name in runtime_env
        if _ENV_NAME_RE.match(str(name))
        and name not in GOLDEN_CONTROL_FLAGS
        and not _is_allowlisted(str(name))
    )


def requested_loader(role: str, resolved: ResolvedConfig | None = None) -> str:
    """Return the semantic loader arm selected by resolved values only.

    Precedence is deliberate.  CLIP is ``qd4_reader`` first, then
    ``fastsafe_hydration``, ``staged_hydration``, ``speculative_clip``, and
    finally ``native_comfy``.  UNET is ``fastsafetensors`` first, then
    ``meta_direct``, then the native CPU-snapshot/fast-disk arm, and finally
    ``native_comfy``.  VAE selects ``policy_v1`` only when the V1 policy and
    VAE snapshot are both active; otherwise it is ``native_comfy``.
    """
    config = resolve() if resolved is None else resolved
    if role == "clip":
        if config.get("COMFYMODAL_V2_CLIP_QD_READER"):
            return "qd4_reader"
        if config.get("COMFYMODAL_V2_CLIP_FAST_HYDRATION"):
            return "fastsafe_hydration"
        if config.get("COMFYMODAL_V2_CLIP_STAGED_HYDRATION"):
            return "staged_hydration"
        if config.get("COMFYMODAL_V2_SPECULATIVE_CLIP_HYDRATION"):
            return "speculative_clip"
        return "native_comfy"
    if role == "unet":
        if config.get("COMFYMODAL_V2_UNET_FASTSAFETENSORS"):
            return "fastsafetensors"
        if config.get("COMFYMODAL_V2_UNET_META_DIRECT"):
            return "meta_direct"
        if config.get("COMFYMODAL_V2_NATIVE_FAST_DISK_UNET") or config.get("COMFYMODAL_V2_CPU_MODEL_SNAPSHOT"):
            return "cpu_snapshot_native"
        return "native_comfy"
    if role == "vae":
        if config.get("COMFYMODAL_V2_VAE_POLICY") == "v1" and config.get("COMFYMODAL_V2_VAE_SNAPSHOT"):
            return "policy_v1"
        return "native_comfy"
    raise ValueError("role must be one of: clip, unet, vae")


_OVERLAP_SCHEDULE_CHOICES = ("serial", "overlap")


def _resolve_overlap_schedule(
    flag: str, value: Any, resolved: ResolvedConfig | None
) -> str:
    if value is not None:
        selected = str(value).strip().lower() or "serial"
    else:
        config = resolve() if resolved is None else resolved
        selected = str(config.get(flag, "serial")).strip().lower() or "serial"
    if selected not in _OVERLAP_SCHEDULE_CHOICES:
        raise ValueError(
            f"invalid {flag} value {selected!r}; expected serial or overlap"
        )
    return selected


def resolve_clip_unet_schedule(
    value: Any = None, resolved: ResolvedConfig | None = None
) -> str:
    """Resolve the CLIP-forward || UNET-load schedule (``serial`` default)."""
    return _resolve_overlap_schedule(
        "COMFYMODAL_GOLDEN_CLIP_UNET_SCHEDULE", value, resolved
    )


def resolve_sampling_vae_schedule(
    value: Any = None, resolved: ResolvedConfig | None = None
) -> str:
    """Resolve the sampling || VAE-load schedule (``serial`` default)."""
    return _resolve_overlap_schedule(
        "COMFYMODAL_GOLDEN_SAMPLING_VAE_SCHEDULE", value, resolved
    )


def resolve_completion_event_lifetime(
    value: Any = None, resolved: ResolvedConfig | None = None
) -> str:
    """Resolve the H2D completion-event lifetime (``reuse`` default).

    Applies to every transport role: ``one_shot_events`` gives each H2D its own
    freshly allocated completion event pair, retired when the slot is returned.
    """
    if value is not None:
        selected = str(value).strip().lower() or "reuse"
    else:
        config = resolve() if resolved is None else resolved
        selected = str(
            config.get("COMFYMODAL_GOLDEN_COMPLETION_EVENT_LIFETIME", "reuse")
        ).strip().lower() or "reuse"
    if selected not in {"reuse", "one_shot_events"}:
        raise ValueError(
            f"invalid completion-event lifetime {selected!r}; "
            "expected reuse or one_shot_events"
        )
    return selected


__all__ = [
    "ALLOWLIST_UNREGISTERED",
    "GOLDEN_CONTROL_FLAGS",
    "ResolvedConfig",
    "detect_unregistered_mutations",
    "reconcile",
    "requested_loader",
    "resolve",
    "resolve_clip_unet_schedule",
    "resolve_sampling_vae_schedule",
    "resolve_completion_event_lifetime",
]
