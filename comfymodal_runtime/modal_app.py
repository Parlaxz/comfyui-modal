"""Deployable v2 Modal application and its runtime entrypoint."""

from __future__ import annotations

import asyncio
import base64
import concurrent.futures
import hashlib
import importlib
import inspect
import os
import platform
import posixpath
import threading
import time
import uuid
import copy
from types import MappingProxyType

import dataclasses
from contextvars import ContextVar
from dataclasses import dataclass
from pathlib import Path
from typing import Any, AsyncIterator, Callable, ContextManager, Mapping, cast

from gpu_catalog import parse_gpu_request, normalize_gpu_value, GPU_CATALOG, GPU_BY_VALUE

from .contracts import DeploymentIdentity, ExecutionPlan, ModelRestoreKey, RestorePlan, _thaw, stable_hash
from .deployment_spec import build_deployment_identity
from .restore_plan import RestorePlanPublisher, build_restore_model_spec, derive_model_key, derive_prefill_key
from .runtime_bootstrap import BootstrapConfig, RuntimeBootstrap
from .runtime_executor import (
    ExecutionContext,
    RuntimeExecutor,
    pre_sampler_instrumentation_scope,
    set_lock_wait_ms,
    _attach_structured_report,
)
from .runtime_state import CommitCoordinator, ModalMountedStateVolume
from .model_preload import (
    V2LoaderBridge,
    RestorePreparation,
    _collect_restore_events_for_summary,
    _PREFILL_LANE_MODE,
    get_restore_return_marker,
    gpu_not_observed_summary,
    request_execution_trace_scope,
    resolve_unet_effective_dtype,
    set_model_load_identity,
    set_restore_return_marker,
    _capture_host_info,
    _DIAGNOSTIC_FLAG as _MP_DIAGNOSTIC_FLAG,
)
from .cpu_snapshot_models import (
    CpuSnapshotModels,
    collect_unet_runtime_state,
    identity_from_profile,
    inspect_and_validate_snapshot_params,
    load_cpu_snapshot_models,
    validate_cpu_snapshot_models,
    validate_snapshot_unet_bf16_native,
    retarget_cpu_snapshot_models,
    _COMPUTE_POLICY_BF16_NATIVE,
)
from .unet_forward_probe import (
    register_unet_forward_probe,
    install_registered_unet_forward_hooks,
    reset_first_cuda_dedup,
)
from .output_delivery import (
    Attempt,
    _measure_json_bytes,
    attempt_to_descriptor_result,
    base64_counting_scope,
    build_default_chain,
    run_strategy_chain,
)
from .result_delivery import ConversionFailedError, convert_output_items
from .trace import RuntimeTrace, _emit_breakdown_line, merge_runtime_traces

_V2_STAGE_MAP: tuple[tuple[str, str, str], ...] = (
    ("unet_load",      "t4b_unet_load_start",      "t4b_unet_load_end"),
    ("clip_load",      "t4_clip_load_start",       "t4_clip_load_end"),
    ("vae_load",       "t4c_vae_load_start",       "t4c_vae_load_end"),
    ("clip_encode",    "t5_text_encode_start",     "t5_text_encode_end"),
    ("sampler",        "t6_sampler_start",          "t6_sampler_end"),
    ("vae_decode",     "t7_vae_decode_start",       "t7_vae_decode_end"),
    ("cachedit",       "t8_cachedit_start",         "t8_cachedit_end"),
    ("noise_inject",   "t8_noise_inject_start",     "t8_noise_inject_end"),
    ("model_sampling", "t4d_model_sampling_start",  "t4d_model_sampling_end"),
    ("model_patch",    "t4e_model_patch_start",     "t4e_model_patch_end"),
    ("sampler_setup",  "t8_sampler_setup_start",    "t8_sampler_setup_end"),
)

_V2_CRITICAL_PATH_FIELDS: tuple[str, ...] = (
    "python_resume_to_restore_enter_ms",
    "restore_total_ms",
    "restore_exit_to_run_enter_ms",
    "run_enter_to_plan_received_ms",
    "plan_received_to_executor_invoke_ms",
    "executor_invoke_to_first_node_ms",
    "first_node_to_sampler_node_ms",
    "sampler_node_to_sampler_start_ms",
    "pre_sampler_unattributed_ms",
)


def _critical_path_delta_ms(start_ns: Any, end_ns: Any) -> float | None:
    if not isinstance(start_ns, int) or not isinstance(end_ns, int):
        return None
    return round((end_ns - start_ns) / 1_000_000, 3)


def _format_v2_critical_path(values: Mapping[str, Any]) -> str:
    return " ".join(
        ["[v2.critical_path]"]
        + [
            f"{field}={ModalRuntimeEntrypoint._fmt_or_absent(values.get(field))}"
            for field in _V2_CRITICAL_PATH_FIELDS
        ]
    )


def _build_v2_critical_path(
    restore_timing: Mapping[str, Any],
    execution_timing: Mapping[str, Any],
    *,
    run_enter_mono_ns: int,
    plan_received_mono_ns: int,
    same_process_as_restore: bool,
) -> dict[str, Any]:
    first_node_perf_ns = execution_timing.get("first_node_enter_perf_ns")
    sampler_node_perf_ns = execution_timing.get("sampler_node_enter_perf_ns")
    values: dict[str, Any] = {
        "python_resume_to_restore_enter_ms": _critical_path_delta_ms(
            restore_timing.get("remote_python_resume_mono_ns"),
            restore_timing.get("restore_method_start_mono_ns"),
        ),
        "restore_total_ms": restore_timing.get("restore_total_ms"),
        "restore_exit_to_run_enter_ms": (
            _critical_path_delta_ms(
                restore_timing.get("restore_method_end_mono_ns"),
                run_enter_mono_ns,
            )
            if same_process_as_restore
            else None
        ),
        "run_enter_to_plan_received_ms": _critical_path_delta_ms(
            run_enter_mono_ns, plan_received_mono_ns
        ),
        "plan_received_to_executor_invoke_ms": _critical_path_delta_ms(
            plan_received_mono_ns,
            execution_timing.get("executor_invoke_mono_ns"),
        ),
        "executor_invoke_to_first_node_ms": _critical_path_delta_ms(
            execution_timing.get("executor_invoke_perf_ns"),
            first_node_perf_ns,
        ),
        "first_node_to_sampler_node_ms": _critical_path_delta_ms(
            first_node_perf_ns, sampler_node_perf_ns
        ),
        # Reuse pre-computed value from pre_sampler_stages authoritative
        # calculation (milestone-based T1/T2 monotonic_ns) rather than
        # recalculating from sampler_stage_start_perf_ns (separate wall-clock).
        "sampler_node_to_sampler_start_ms": execution_timing.get(
            "sampler_node_to_sampler_start_ms"
        ),
        "pre_sampler_unattributed_ms": execution_timing.get(
            "pre_sampler_unattributed_ms"
        ),
    }
    return values


try:
    import modal as _modal
except Exception:
    _modal = None


APP_NAME = os.environ.get("COMFYMODAL_V2_APP_NAME", "stable-modal-comfy-v2-shadow").strip() or "stable-modal-comfy-v2-shadow"
MODELS_VOLUME_NAME = os.environ.get("COMFYMODAL_MODELS_VOLUME", "comfyui-models")
CUSTOM_NODES_VOLUME_NAME = os.environ.get("COMFYMODAL_CUSTOM_NODES_VOLUME", "comfyui-custom-nodes")
RUNTIME_STATE_VOLUME_NAME = os.environ.get("COMFYMODAL_RUNTIME_STATE_VOLUME", "comfymodal-runtime-config")
MODELS_PATH = "/root/models"
CUSTOM_NODES_PATH = "/root/custom_nodes_vol"
RUNTIME_STATE_PATH = "/mnt/comfymodal_runtime_state"
V2_RESTORE_STATE_FILE = "v2_restore_plan.json"
MIN_CONTAINERS = 0
SCALEDOWN_WINDOW = 4
_PUBLISHER_MARKER = "COMFYMODAL_PUBLISHER_CONTAINER"
CLASS_NAME = "ModalRuntimeEntrypoint"
# Process-local restore-stage timer accumulator.
# Populated by _wrap_restore_stage wrappers in _configure_runtime, consumed by
# restore() when building _restore_timing.  Thread-safe via GIL.
_RESTORE_STAGE_TIMERS: dict[str, float] = {}

# Process-local fallback for lifecycle timing when Modal separates enter/method instances.
# Both startup() and restore() refresh this; _run_in_process and run_plan_stream
# read it when self._restore_timing is None.
_LATEST_LIFECYCLE_TIMING: dict[str, Any] | None = None
_LATEST_RESTORED_INSTANCE_ID: str = ""
"""Module-level latest restored_instance_id.  Set by restore() after
snapshot restoration; read by background worker and graph-entry paths.
This is distinct from container_session_id: it changes on every restore
cycle while the container session persists across lifecycle."""

# V1-parity module-level stable identity so instance/snapshot boundaries cannot erase identity.
# Set once at import time, before any Modal instance construction.
_V2_CONTAINER_SESSION_ID: str = uuid.uuid4().hex[:16]
_V2_CONTAINER_IMPORT_UNIX_S: float = time.time()
_v2_container_restore_count: int = 0

# All local Python modules that comfyapp.py imports at the top level
# and that must be available in the remote V2 shadow container.
# External ComfyUI modules (nodes, server, folder_paths, torch, ...)
# are provided by the base runtime image â€” do not list them here.
V2_SOURCE_MODULES = (
    "api_prompt_validator",
    "canonical_execution",
    "comfyapp",
    "comfymodal_runtime",
    "failure_summary",
    "gpu_catalog",
    "modal_client",
    "optimizations",
    "production_workflow",
    "profiler_trace_v4",
    "run_prompt_options",
    "timing_trace",
    "wall_clock_trace_v3",
    "warmup_profile",
    "workflow_metadata",
)

# â”€â”€ V2 validation certificate (V1-parity persistent validation cache) â”€â”€
# Enabled by default.  Set COMFYMODAL_V2_VALIDATION_CERT=0 to disable.
# Certificates are stored on the runtime-state Volume keyed by a stable
# identity that includes workflow struct hash and deployment identity.
_V2_VALIDATION_CERT_ENABLED: bool = (
    os.environ.get("COMFYMODAL_V2_VALIDATION_CERT", "1") == "1"
)
_V2_CERT_SCHEMA_VERSION: int = 2
_V2_CERT_FILENAME_PREFIX: str = "v2_cert_"

# Pre-computed deployment identity hash for certificate identity.
# Populated at module level once during import.
_V2_DEPLOYMENT_COMBINED_HASH: str = ""

# Process-local validation certificate cache.
# Keyed by (container_session_id, cert_identity).  The container session ID
# is stable across restores within the same container, so the cache persists
# across multiple restore cycles.  Stores copies only of outputs_to_execute,
# node_errors, preflight_ok, schema_version, and identity_components for exact
# revalidation.  No live graph/executor/model/node/cache objects are stored.
# Evicted on replacement write, component mismatch, or any validation
# failure detected at read time.
_V2_CERT_PROCESS_CACHE: dict[tuple[str, str], dict[str, Any]] = {}

# Process-local RES4LYF prepared options cache.
# Keyed by workflow_hash.  Set at restore time, read by ClownsharKSampler_Beta
# hook at graph-execution time.  Never stores live model/sampler objects.
_RES4LYF_PREPARED: dict[str, dict[str, Any]] = {}
_RES4LYF_HOOK_INSTALLED: bool = False

# Process-local CacheDiT prepared state.
# Keyed by workflow_hash.  Stores UNET object id, workflow hash, inputs.
_CACHEDIT_PREPARED: dict[str, dict[str, Any]] = {}

# ContextVar for the current request's workflow hash.
# Set in _execute_v2_prompt_executor immediately before PromptExecutor
# execution and reset in finally.  Read by the RES4LYF hook to avoid
# passing undeclared kwargs through the graph node interface.
_V2_WORKFLOW_HASH: ContextVar[str] = ContextVar("_v2_workflow_hash", default="")

# Import SAMPLER_SAMPLE wrapper from runtime_executor (neutral module).
from comfymodal_runtime.runtime_executor import _COMFYMODAL_V2_SAMPLING_WRAPPER, _sampler_wrapper_dedup, _sampler_wrapper_dedup_lock

# ── Canonical per-role identity comparison for restore + request binding ──


def _resolve_effective_dtype_from_spec(model_spec: Any) -> str:
    """Extract effective compute dtype label from a model_spec.

    Reads the first UNET loader entry's weight_dtype and resolves it
    through the snapshot-safe resolver.  Returns the resolved label or
    ``"default"`` when the spec or entry is unavailable.  Never raises.
    Logs ``"absent"`` when no UNET loader entry is present.
    Accepts any ``collections.abc.Mapping`` (including ``MappingProxyType``).
    """
    try:
        if not isinstance(model_spec, Mapping):
            return "absent"
        loaders = model_spec.get("loaders", {})
        if not isinstance(loaders, Mapping):
            return "absent"
        unet_entries = loaders.get("unet", [])
        if not isinstance(unet_entries, (list, tuple)) or not unet_entries:
            return "absent"
        entry = unet_entries[0]
        if not isinstance(entry, Mapping):
            return "absent"
        weight_dtype = str(entry.get("weight_dtype", "default"))
        # Resolve through the snapshot-safe helper (no CUDA calls)
        from comfymodal_runtime.model_preload import resolve_unet_effective_dtype
        _dtype, _label = resolve_unet_effective_dtype(weight_dtype)
        return _label or weight_dtype
    except Exception:
        return "absent"


def _resolve_model_config_hash_from_spec(model_spec: Any) -> str:
    """Compute a deterministic hash of UNET model-type/configuration fields
    available in the spec.  Returns ``"absent"`` when no config fields exist.
    Accepts any ``collections.abc.Mapping`` (including ``MappingProxyType``).
    """
    try:
        if not isinstance(model_spec, Mapping):
            return "absent"
        loaders = model_spec.get("loaders", {})
        if not isinstance(loaders, Mapping):
            return "absent"
        unet_entries = loaders.get("unet", [])
        if not isinstance(unet_entries, (list, tuple)) or not unet_entries:
            return "absent"
        entry = unet_entries[0]
        if not isinstance(entry, Mapping):
            return "absent"
        # Include UNET name, loader_class, and weight_dtype in config identity
        config_parts = {
            "unet_name": str(entry.get("unet_name", "")),
            "loader_class": str(entry.get("loader_class", "")),
            "weight_dtype": str(entry.get("weight_dtype", "default")),
        }
        if not any(config_parts.values()):
            return "absent"
        from comfymodal_runtime.contracts import stable_hash
        return stable_hash(config_parts)[:16]
    except Exception:
        return "absent"


def _resolve_static_patch_hash_from_spec(model_spec: Any) -> str:
    """Return static model patches hash from model_spec if present,
    ``"none"`` when no patch metadata exists, ``"absent"`` when the spec
    is not available.
    Accepts any ``collections.abc.Mapping`` (including ``MappingProxyType``).
    """
    try:
        if not isinstance(model_spec, Mapping):
            return "absent"
        # Static patches would be stored in model_spec["static_patches_hash"]
        # if present.  For standard V2 fast paths without CacheDiT/RES4LYF
        # no patch metadata exists.
        patch_hash = model_spec.get("static_patches_hash", "")
        if patch_hash:
            return str(patch_hash)
        return "none"
    except Exception:
        return "absent"


def _canonical_role_match_report(
    *,
    request_model_spec: Any,
    snapshot_model_spec: Any,
    request_custom_node_generation: str = "",
    request_deployment_combined_hash: str = "",
    snapshot_custom_node_generation: str = "",
    snapshot_deployment_combined_hash: str = "",
    request_unet_effective_dtype: str = "",
    snapshot_unet_effective_dtype: str = "",
    request_unet_model_config_hash: str = "",
    snapshot_unet_model_config_hash: str = "",
    request_unet_static_patches_hash: str = "",
    snapshot_unet_static_patches_hash: str = "",
) -> dict[str, Any]:
    """Compare request and snapshot model specs using canonical per-role identity.

    Returns a dict with:
      ``compatible`` (bool) — True when BOTH UNET and CLIP role identities
        are equivalent.  VAE does NOT participate.
      ``unet_match`` (bool) — True when UNET identity matches.
      ``clip_match`` (bool) — True when CLIP identity matches.
      ``unet_mismatch_fields`` (list[str]) — Differing UNET fields.
      ``clip_mismatch_fields`` (list[str]) — Differing CLIP fields.
      ``unet_request_identity``, ``unet_snapshot_identity``,
      ``clip_request_identity``, ``clip_snapshot_identity`` — the computed
        identity dicts (with ``stable_id``).
      ``reason`` (str) — Human-readable mismatch description, or ``"ok"``.

    Uses the same ``compute_loader_role_identity`` /
    ``find_role_identity_mismatch_fields`` helpers as executor seeding so
    that restore matching and cache seeding derive from a single canonical
    implementation.
    """
    from .contracts import (
        compute_loader_role_identity,
        find_role_identity_mismatch_fields,
    )

    result: dict[str, Any] = {
        "compatible": False,
        "unet_match": False,
        "clip_match": False,
        "unet_mismatch_fields": [],
        "clip_mismatch_fields": [],
        "reason": "unknown",
    }

    unet_request = compute_loader_role_identity(
        "unet", request_model_spec or {},
        custom_node_generation=request_custom_node_generation,
        deployment_combined_hash=request_deployment_combined_hash,
        static_model_patches_hash=request_unet_static_patches_hash,
        effective_compute_dtype_label=request_unet_effective_dtype,
        model_configuration_hash=request_unet_model_config_hash,
    )
    unet_snapshot = compute_loader_role_identity(
        "unet", snapshot_model_spec or {},
        custom_node_generation=snapshot_custom_node_generation,
        deployment_combined_hash=snapshot_deployment_combined_hash,
        static_model_patches_hash=snapshot_unet_static_patches_hash,
        effective_compute_dtype_label=snapshot_unet_effective_dtype,
        model_configuration_hash=snapshot_unet_model_config_hash,
    )
    clip_request = compute_loader_role_identity(
        "clip", request_model_spec or {},
        custom_node_generation=request_custom_node_generation,
        deployment_combined_hash=request_deployment_combined_hash,
    )
    clip_snapshot = compute_loader_role_identity(
        "clip", snapshot_model_spec or {},
        custom_node_generation=snapshot_custom_node_generation,
        deployment_combined_hash=snapshot_deployment_combined_hash,
    )

    unet_mismatch = find_role_identity_mismatch_fields(unet_request, unet_snapshot)
    clip_mismatch = find_role_identity_mismatch_fields(clip_request, clip_snapshot)

    unet_match = len(unet_mismatch) == 0
    clip_match = len(clip_mismatch) == 0
    compatible = unet_match and clip_match

    # Build human-readable reason
    parts: list[str] = []
    if not unet_match:
        parts.append(f"UNET:{','.join(unet_mismatch)}")
    if not clip_match:
        parts.append(f"CLIP:{','.join(clip_mismatch)}")
    reason = "; ".join(parts) if parts else "ok"

    result["compatible"] = compatible
    result["unet_match"] = unet_match
    result["clip_match"] = clip_match
    result["unet_mismatch_fields"] = unet_mismatch
    result["clip_mismatch_fields"] = clip_mismatch
    result["unet_request_identity"] = unet_request
    result["unet_snapshot_identity"] = unet_snapshot
    result["clip_request_identity"] = clip_request
    result["clip_snapshot_identity"] = clip_snapshot
    result["reason"] = reason
    return result


# Plan A/B spec projection helpers (Plan C compatibility, kept for reference)


def _cpu_snapshot_spec_projection(spec: Any) -> dict[str, list[dict[str, Any]]]:
    """Project a model_spec dict to only the fields relevant for Plan A/B matching.

    Extracts loaders from any spec shape (Plan A from identity_from_profile or
    Plan B from build_restore_model_spec) and returns a canonical dict with
    ``{"unet": [...], "clip": [...]}`` containing only the requested identity
    fields.  Fields ignored: ``node_id``, ``model_stack``, VAE loaders, CLIP
    ``device``, and any extra top-level keys.

    UNET loaders keep ``loader_class``, ``unet_name``, ``weight_dtype``.
    CLIP loaders keep ``loader_class``, ``clip_name`` (or ``clip_name1``/
    ``clip_name2`` for dual), and ``type``.

    Accepts any ``collections.abc.Mapping`` (including ``MappingProxyType``
    used by frozen ``RestorePlan.model_spec``) as well as plain ``dict``.
    Loader entries may also be ``Mapping`` types.

    Preserves list multiplicity and order so extra or swapped loaders miss.
    Returns an empty projection when *spec* is not a Mapping or has no loaders.
    """
    if not isinstance(spec, Mapping):
        return {"unet": [], "clip": []}
    loaders = spec.get("loaders", {})
    if not isinstance(loaders, Mapping):
        return {"unet": [], "clip": []}

    result: dict[str, list[dict[str, Any]]] = {"unet": [], "clip": []}

    # NOTE: compute policy is NOT included in the projection. It is stored
    # separately on CpuSnapshotModels.compute_policy and compared outside
    # the spec matching path.  This keeps the request model_spec clean
    # (weight_dtype="default" only) while snapshot matching still works.

    for loader in loaders.get("unet", []):
        if not isinstance(loader, Mapping):
            continue
        result["unet"].append({
            "loader_class": loader.get("loader_class", ""),
            "unet_name": loader.get("unet_name", ""),
            "weight_dtype": str(loader.get("weight_dtype", "default")),
        })

    for loader in loaders.get("clip", []):
        if not isinstance(loader, Mapping):
            continue
        entry: dict[str, Any] = {
            "loader_class": loader.get("loader_class", ""),
            "type": loader.get("type", ""),
        }
        if "clip_name1" in loader:
            entry["clip_name1"] = loader.get("clip_name1", "")
            entry["clip_name2"] = loader.get("clip_name2", "")
        else:
            entry["clip_name"] = loader.get("clip_name", "")
        result["clip"].append(entry)

    return result


def _cpu_snapshot_specs_match(spec_a: Any, spec_b: Any) -> bool:
    """Compare two model_spec dicts using only the requested identity fields.

    Compares UNET identity (``unet_name``, ``weight_dtype``, ``loader_class``)
    and CLIP identity (filenames, ``loader_class``, ``type``, single-vs-dual
    layout) while ignoring ``node_id``, ``model_stack``, VAE loaders, CLIP
    ``device``, and any other extraneous fields.

    Preserves list multiplicity and order so extra or differently-ordered
    loaders cause a mismatch.
    """
    return _cpu_snapshot_spec_projection(spec_a) == _cpu_snapshot_spec_projection(spec_b)


def _cpu_snapshot_model_keys_match(key_a: ModelRestoreKey, key_b: ModelRestoreKey) -> bool:
    """Compare two model keys ignoring ``vae_identity``.

    Compares only fields that are materially derived on both Plan A snapshot
    construction and Plan B request derivation: ``unet_identity``,
    ``clip_identity`` (including dual-file dual identity), and ``clip_type``.

    Fields such as ``loader_configuration``, ``model_volume_generation``,
    and ``optimization_loader_options`` are default-only and never populated
    by ``identity_from_profile`` or ``derive_model_key`` — they are not
    evidence and do not gate activation.
    """
    return (
        key_a.unet_identity == key_b.unet_identity
        and key_a.clip_identity == key_b.clip_identity
        and key_a.clip_type == key_b.clip_type
    )


def _cpu_snapshot_key_mismatch_reason(
    key_a: ModelRestoreKey,
    key_b: ModelRestoreKey,
) -> str | None:
    """Return exact mismatch reason or None if keys match (ignoring vae_identity).

    Checks only the materially-derived fields: ``unet_identity``,
    ``clip_identity`` (including dual-file dual identity), and ``clip_type``.
    Fields never populated by ``identity_from_profile`` or ``derive_model_key``
    (``loader_configuration``, ``model_volume_generation``,
    ``optimization_loader_options``) are not checked.
    """
    if key_a.unet_identity != key_b.unet_identity:
        return "UNET identity mismatch"
    if key_a.clip_identity != key_b.clip_identity:
        return "CLIP identity mismatch"
    if key_a.clip_type != key_b.clip_type:
        return "clip_type mismatch"
    return None


def _cpu_snapshot_spec_mismatch_reason(
    spec_a: Any,
    spec_b: Any,
) -> str | None:
    """Return exact mismatch reason or None if projected specs match.

    Compares projected UNET identity (unet_name, weight_dtype, loader_class)
    and CLIP identity (filenames, loader_class, type, single-vs-dual layout)
    and returns the first field-level difference found.
    """
    proj_a = _cpu_snapshot_spec_projection(spec_a)
    proj_b = _cpu_snapshot_spec_projection(spec_b)

    unet_a = proj_a.get("unet", [])
    unet_b = proj_b.get("unet", [])
    if len(unet_a) != len(unet_b):
        return "UNET loader count mismatch"
    for i, (ua, ub) in enumerate(zip(unet_a, unet_b)):
        if ua.get("loader_class") != ub.get("loader_class"):
            return "UNET loader_class mismatch"
        if ua.get("unet_name") != ub.get("unet_name"):
            return "UNET filename mismatch"
        if ua.get("weight_dtype") != ub.get("weight_dtype"):
            return "UNET weight_dtype mismatch"

    clip_a = proj_a.get("clip", [])
    clip_b = proj_b.get("clip", [])
    if len(clip_a) != len(clip_b):
        return "CLIP loader count mismatch"
    for i, (ca, cb) in enumerate(zip(clip_a, clip_b)):
        if ca.get("loader_class") != cb.get("loader_class"):
            return "CLIP loader_class mismatch"
        if ca.get("type") != cb.get("type"):
            return "CLIP type mismatch"
        if "clip_name1" in ca and "clip_name1" in cb:
            if ca["clip_name1"] != cb["clip_name1"] or ca["clip_name2"] != cb["clip_name2"]:
                return "CLIP dual filename mismatch"
        elif "clip_name" in ca and "clip_name" in cb:
            if ca["clip_name"] != cb["clip_name"]:
                return "CLIP filename mismatch"
        else:
            return "CLIP single/dual structural mismatch"

    if proj_a != proj_b:
        return "spec projection mismatch"
    return None


def _cpu_model_snapshot_enabled() -> bool:
    """Return True when COMFYMODAL_V2_CPU_MODEL_SNAPSHOT == '1'.

    Rejects the combination with COMFYMODAL_ENABLE_GPU_SNAPSHOT == '1'
    with a clear RuntimeError.
    """
    enabled = os.environ.get("COMFYMODAL_V2_CPU_MODEL_SNAPSHOT", "0") == "1"
    if not enabled:
        return False
    if os.environ.get("COMFYMODAL_ENABLE_GPU_SNAPSHOT", "0") == "1":
        raise RuntimeError(
            "COMFYMODAL_V2_CPU_MODEL_SNAPSHOT=1 is incompatible with "
            "COMFYMODAL_ENABLE_GPU_SNAPSHOT=1"
        )
    return enabled


def _get_preflight_context(api: Any, module: Any) -> tuple[str, str, str]:
    """Extract cheap request-time preflight context from the loaded legacy API.

    Calls ``api._resolve_requirements_repair_mode()`` for repair mode and
    ``module._resolve_custom_nodes_generation(api=api)`` for the authoritative
    custom-nodes generation (hydrated API field first, persisted record
    fallback).  Returns ``(repair_mode, custom_nodes_generation, source)``.
    Either may be empty when the helpers are absent or raise — optimisation fails
    closed.
    """
    repair_mode = ""
    try:
        repair_mode = str(api._resolve_requirements_repair_mode() or "")
    except Exception:
        pass
    custom_nodes_gen = ""
    source = "missing"
    try:
        _cn_val, _cn_src = module._resolve_custom_nodes_generation(api=api)
        custom_nodes_gen = _cn_val
        source = _cn_src
    except Exception:
        pass
    return repair_mode, custom_nodes_gen, source


# ── CacheDiT snapshot-safe pre-import (testable) ──────────────────────
_CACHEDIT_LOCK_PACKAGES: list[tuple[str, str, str]] = [
    ("transformers", "transformers", "transformers"),
    ("diffusers", "diffusers", "diffusers"),
    ("cache-dit", "cache_dit", "cache_dit"),
]
"""Snapshot-safe pre-import list: (metadata_name, import_name, display_label)."""


def preimport_cachedit_family(
    *,
    _importlib: Any = None,
    _print: Callable[..., None] = print,
) -> dict[str, Any]:
    """Pre-import transformers, diffusers, cache_dit in snapshot-safe mode.

    Resolves only safe immutable metadata/classes/config validation available
    in cache-dit v1.2.3 (inspects APIs rather than inventing symbols).
    Does NOT create prompt/timestep/cache/latent/CUDA/session state.

    Returns a dict with:
      ``ok`` (bool), ``versions`` (dict), ``paths`` (dict),
      ``cache_dit_info`` (dict | str), ``errors`` (list).

    On any import failure, ``ok`` is False and *errors* describes the issue.
    Never raises.
    """
    result: dict[str, Any] = {
        "ok": False,
        "versions": {},
        "paths": {},
        "cache_dit_info": {},
        "errors": [],
    }
    if _importlib is None:
        import importlib
        import importlib.metadata  # ensure metadata submodule is loaded
        _importlib = importlib

    for meta_name, import_name, label in _CACHEDIT_LOCK_PACKAGES:
        try:
            ver = _importlib.metadata.version(meta_name)
            mod = _importlib.import_module(import_name)
            mod_path = getattr(mod, "__file__", "?")
            result["versions"][label] = ver
            result["paths"][label] = mod_path
            _print(f"[cachedit.startup] preimport {label} version={ver} path={mod_path}")
        except Exception as exc:
            msg = f"preimport {label} ({meta_name}): {exc}"
            result["errors"].append(msg)
            _print(f"[cachedit.startup] ERROR {msg}")

    # Immutable cache_dit v1.2.3 API inspection (no request/CUDA/session state)
    # Use injected _importlib when available; fall back to real import otherwise.
    try:
        _cd = _importlib.import_module("cache_dit") if _importlib else __import__("cache_dit")
        _cd_info: dict[str, Any] = {}
        for attr in ("__version__", "__title__", "__description__"):
            val = getattr(_cd, attr, None)
            if val is not None:
                _cd_info[attr] = str(val)
        # Inspect safe top-level class names (no instantiation)
        _class_names = [
            name for name in dir(_cd)
            if isinstance(getattr(_cd, name, None), type)
            and not name.startswith("_")
        ]
        _cd_info["top_level_classes"] = sorted(_class_names)
        result["cache_dit_info"] = _cd_info
        _print(f"[cachedit.startup] cache_dit metadata={_cd_info}")
    except Exception as exc:
        result["errors"].append(f"cache_dit api inspection: {exc}")
        _print(f"[cachedit.startup] ERROR cache_dit api inspection: {exc}")

    result["ok"] = len(result["errors"]) == 0
    return result


def _install_res4lyf_parser_hook() -> bool:
    """Install a process-local hook on the ``ExtraOptions`` class used by
    ClownsharKSampler_Beta's module so that when ``ExtraOptions(raw_string)``
    is called at request time, the cached restore-prepared parser result is
    returned when the current workflow hash and exact raw options match.

    Reads ``_V2_WORKFLOW_HASH`` ContextVar — never adds undeclared kwargs
    or passes parser objects as string arguments.  The hook replaces
    ``ExtraOptions`` in the sampler module's namespace with a wrapper that
    checks the ContextVar and returns a cached dict-based instance on exact
    match, otherwise falling through to the original class.

    Returns True when hook was installed.  Idempotent.
    Does not edit external custom-node source files.
    """
    global _RES4LYF_HOOK_INSTALLED
    if _RES4LYF_HOOK_INSTALLED:
        return True
    try:
        import nodes as _r4_nodes
        _cls = getattr(_r4_nodes, "NODE_CLASS_MAPPINGS", {}).get("ClownsharKSampler_Beta")
        if _cls is None:
            return False
        _mod = getattr(_cls, "__module__", "")
        if not _mod:
            return False
        import importlib
        _sampler_mod = importlib.import_module(_mod)
        _orig_extra_options = getattr(_sampler_mod, "ExtraOptions", None)
        if _orig_extra_options is None:
            return False
        if getattr(_orig_extra_options, "_comfy_modal_res4lyf_hook", False):
            _RES4LYF_HOOK_INSTALLED = True
            return True

        # Wrapper that checks ContextVar and caches parser result
        class _HookedExtraOptions(_orig_extra_options):
            _comfy_modal_res4lyf_hook = True

            def __init__(self, raw_options, *args, **kwargs):
                wf_hash = _V2_WORKFLOW_HASH.get()
                if wf_hash and wf_hash in _RES4LYF_PREPARED:
                    _prep = _RES4LYF_PREPARED[wf_hash]
                    _raw_key = str(raw_options).strip()
                    for _record in _prep.get("records", ()):
                        if _record.get("raw_options") == _raw_key:
                            _parser_state = _record.get("parser_state")
                            if _parser_state is not None:
                                self.__dict__.update(dict(_parser_state))
                                print(
                                    "[v2.res4lyf_request] decision=reused parse_called=0",
                                    flush=True,
                                )
                                return
                super().__init__(raw_options, *args, **kwargs)

        setattr(_sampler_mod, "ExtraOptions", _HookedExtraOptions)
        _RES4LYF_HOOK_INSTALLED = True
        return True
    except Exception:
        return False


def _compute_v2_cert_identity(
    workflow_hash: str,
    repair_mode: str = "",
    custom_nodes_generation: str = "",
) -> tuple[str, dict[str, str]]:
    """Build a deterministic certificate identity from *workflow_hash*,
    the deployment's combined hash (``_V2_DEPLOYMENT_COMBINED_HASH``), and
    mutable preflight context.

    Returns ``(identity_hex, components_dict)``.  Identity is a SHA-256 hex
    string.  When ``_V2_DEPLOYMENT_COMBINED_HASH`` is empty, only the
    workflow_hash is used (deployment combined hash is empty — less
    discrimination but still safe).
    """
    import hashlib
    dep_hash = _V2_DEPLOYMENT_COMBINED_HASH
    h = hashlib.sha256()
    h.update(f"cert_schema={_V2_CERT_SCHEMA_VERSION}\n".encode())
    h.update(f"workflow_hash={workflow_hash}\n".encode())
    h.update(f"deployment_hash={dep_hash}\n".encode())
    h.update(f"repair_mode={repair_mode}\n".encode())
    h.update(f"custom_nodes_generation={custom_nodes_generation}\n".encode())
    identity = h.hexdigest()
    components = {
        "schema_version": str(_V2_CERT_SCHEMA_VERSION),
        "workflow_hash": workflow_hash,
        "deployment_hash": dep_hash,
        "repair_mode": repair_mode,
        "custom_nodes_generation": custom_nodes_generation,
    }
    return identity, components


def _v2_cert_filename(cert_identity: str) -> str:
    """Return the on-volume filename for a certificate identity."""
    return f"{_V2_CERT_FILENAME_PREFIX}{cert_identity}.json"


async def _write_v2_validation_certificate(
    cert_identity: str,
    outputs_to_execute: list[str],
    node_errors: dict[str, Any],
    *,
    components: dict[str, str] | None = None,
    preflight_ok: bool = False,
) -> bool:
    """Write a validation certificate to the runtime-state volume (async).

    When *preflight_ok* is True the certificate attests that deterministic
    preflight completed successfully for this identity.  Schema v2+ requires
    preflight_ok to be True for the certificate to be eligible as a preflight
    skip.

    Uses volume.commit.aio() only — no synchronous commit in async path.
    Returns True on success, False on any error.
    """
    try:
        import json as _json

        # Invalidate EVERY process-local cache entry for this certificate
        # identity BEFORE any I/O or volume-lookup, so a failed or
        # unavailable volume write still clears stale entries.
        _keys_to_pop = [
            k for k in _V2_CERT_PROCESS_CACHE
            if len(k) == 2 and k[1] == cert_identity
        ]
        for _k in _keys_to_pop:
            _V2_CERT_PROCESS_CACHE.pop(_k, None)

        resources = globals().get("_MODAL_RESOURCES", {})
        modal_volume = resources.get("runtime_state_volume")
        if modal_volume is None:
            return False
        from .runtime_state import ModalMountedStateVolume
        volume = ModalMountedStateVolume(RUNTIME_STATE_PATH, modal_volume)
        filename = _v2_cert_filename(cert_identity)
        payload = {
            "schema_version": _V2_CERT_SCHEMA_VERSION,
            "identity": cert_identity,
            "created_at": time.time(),
            "outputs_to_execute": outputs_to_execute,
            "node_errors": dict(node_errors or {}),
            "preflight_ok": bool(preflight_ok),
        }
        if components:
            payload["identity_components"] = dict(components)

        # Atomic write through the volume (temp file + rename inside volume)
        encoded = _json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
        volume.write_bytes(filename, encoded)
        # Async commit: await modal_volume.commit.aio() directly
        # (no synchronous commit, no commit_async wrapper)
        _raw_commit = getattr(modal_volume, "commit", None)
        if _raw_commit is not None:
            _aio = getattr(_raw_commit, "aio", None)
            if callable(_aio):
                _coro = _aio()
                await _coro
            else:
                # Fallback for fakes without aio: call commit in a thread
                await asyncio.to_thread(_raw_commit)
        print(
            f"[v2.cert] write identity={cert_identity[:16]} status=committed",
            flush=True,
        )
        return True
    except Exception as exc:
        print(
            f"[v2.cert] write identity={cert_identity[:16]} status=error error={str(exc)[:120]}",
            flush=True,
        )
        return False


def _validate_cert_dict_payload(
    payload: dict[str, Any],
    cert_identity: str,
    *,
    expected_components: dict[str, str] | None = None,
) -> dict[str, Any] | None:
    """Validate a parsed certificate payload *dict* against schema/identity/components.

    Pure validation - no I/O.  Returns
    ``{"outputs_to_execute": [...], "node_errors": {...}}`` on success or
    ``None`` on any validation failure.  Never raises.
    """
    try:
        if not isinstance(payload, dict):
            return None

        # Schema version must match
        if payload.get("schema_version") != _V2_CERT_SCHEMA_VERSION:
            return None

        # Schema v2+: preflight_ok must be True for the cert to be eligible
        # as a preflight-skip token.  Old v1 payloads (no preflight_ok key)
        # fail this check naturally.
        if payload.get("preflight_ok") is not True:
            return None

        # Identity must match the requested cert_hash
        stored_identity = payload.get("identity", "")
        if stored_identity and stored_identity != cert_identity:
            return None

        # Verify identity components if provided
        if expected_components and isinstance(expected_components, dict):
            stored_components = payload.get("identity_components", {})
            if not isinstance(stored_components, dict):
                return None
            for key, expected_val in expected_components.items():
                stored_val = stored_components.get(key)
                if stored_val is None or str(stored_val) != str(expected_val):
                    print(
                        f"[v2.cert] hit=0 identity={cert_identity[:16]} "
                        f"reason={key}_changed "
                        f"stored={str(stored_val)[:32]!r} "
                        f"expected={str(expected_val)[:32]!r}",
                        flush=True,
                    )
                    return None

        # outputs_to_execute must be a non-empty list
        outputs = payload.get("outputs_to_execute")
        if not isinstance(outputs, list) or len(outputs) == 0:
            return None

        # Verify output IDs are unique strings
        seen: set[str] = set()
        for oid in outputs:
            if not isinstance(oid, str) or oid in seen:
                return None
            seen.add(oid)

        # node_errors must be dict of dicts
        errors = payload.get("node_errors", {})
        if not isinstance(errors, dict):
            errors = {}

        print(
            f"[v2.cert] hit=1 identity={cert_identity[:16]} "
            f"outputs={len(outputs)} errors={len(errors)}",
            flush=True,
        )
        return {"outputs_to_execute": outputs, "node_errors": errors}
    except Exception as exc:
        print(
            f"[v2.cert] read identity={cert_identity[:16]} "
            f"status=error error={str(exc)[:120]}",
            flush=True,
        )
        return None


def _read_and_validate_cert_payload(
    volume: Any,
    cert_identity: str,
    *,
    expected_components: dict[str, str] | None = None,
) -> dict[str, Any] | None:
    """Read and validate a certificate payload from an already-reloaded *volume*.

    Shared helper used by both sync and async read paths.  Never raises.
    Returns ``{"outputs_to_execute": [...], "node_errors": {...}}`` on hit, or
    ``None`` on miss/mismatch/error.
    """
    try:
        import json as _json
        filename = _v2_cert_filename(cert_identity)
        if not volume.exists(filename):
            return None
        raw = volume.read_bytes(filename)
        if not raw:
            return None
        payload = _json.loads(raw.decode("utf-8"))
        return _validate_cert_dict_payload(
            payload, cert_identity, expected_components=expected_components,
        )
    except Exception as exc:
        print(
            f"[v2.cert] read identity={cert_identity[:16]} "
            f"status=error error={str(exc)[:120]}",
            flush=True,
        )
        return None
def _read_v2_validation_certificate(
    cert_identity: str,
    *,
    expected_components: dict[str, str] | None = None,
) -> dict[str, Any] | None:
    """Read and validate a certificate from the runtime-state volume.

    Synchronous variant â€” creates a ``ModalMountedStateVolume``, calls
    ``volume.reload()`` synchronously, then delegates to
    ``_read_and_validate_cert_payload()``.

    Never raises.  Returns the cached ``(outputs_to_execute, node_errors)``
    dict on hit, or None on miss/mismatch/error.

    When *expected_components* is provided, each stored identity component
    is verified against its expected value.  A mismatch logs the changed
    component and returns None.
    """
    try:
        resources = globals().get("_MODAL_RESOURCES", {})
        modal_volume = resources.get("runtime_state_volume")
        if modal_volume is None:
            return None
        from .runtime_state import ModalMountedStateVolume
        volume = ModalMountedStateVolume(RUNTIME_STATE_PATH, modal_volume)
        volume.reload()
        return _read_and_validate_cert_payload(
            volume, cert_identity, expected_components=expected_components,
        )
    except Exception as exc:
        print(
            f"[v2.cert] read identity={cert_identity[:16]} "
            f"status=error error={str(exc)[:120]}",
            flush=True,
        )
        return None


async def _read_v2_validation_certificate_async(
    cert_identity: str,
    *,
    expected_components: dict[str, str] | None = None,
) -> tuple[dict[str, Any] | None, dict[str, float]]:
    """Async variant -- uses ``volume.reload_async()`` to avoid Modal's
    "synchronous reload in async context" warning, then reads,
    parses and validates the certificate payload.

    Returns ``(result, timings)`` where *result* is
    ``{"outputs_to_execute": [...], "node_errors": {...}}`` on hit
    or ``None`` on miss/mismatch/error, and *timings* is a dict with
    ``cert_volume_reload_ms``, ``cert_file_read_ms``, and
    ``cert_json_parse_validate_ms`` keys.

    Prefer this over the sync variant when calling from an async context
    (e.g. ``_execute_v2_prompt_executor``).
    """
    timings: dict[str, float] = {
        "cert_volume_reload_ms": 0.0,
        "cert_file_read_ms": 0.0,
        "cert_json_parse_validate_ms": 0.0,
    }
    try:
        import json as _json
        resources = globals().get("_MODAL_RESOURCES", {})
        modal_volume = resources.get("runtime_state_volume")
        if modal_volume is None:
            return None, timings
        from .runtime_state import ModalMountedStateVolume
        volume = ModalMountedStateVolume(RUNTIME_STATE_PATH, modal_volume)

        _t0 = time.perf_counter()
        await volume.reload_async()
        timings["cert_volume_reload_ms"] = round((time.perf_counter() - _t0) * 1000, 3)

        filename = _v2_cert_filename(cert_identity)
        _t1 = time.perf_counter()
        if not volume.exists(filename):
            timings["cert_file_read_ms"] = round((time.perf_counter() - _t1) * 1000, 3)
            return None, timings
        raw = volume.read_bytes(filename)
        timings["cert_file_read_ms"] = round((time.perf_counter() - _t1) * 1000, 3)
        if not raw:
            return None, timings

        _t2 = time.perf_counter()
        payload = _json.loads(raw.decode("utf-8"))
        result = _validate_cert_dict_payload(
            payload, cert_identity, expected_components=expected_components,
        )
        timings["cert_json_parse_validate_ms"] = round((time.perf_counter() - _t2) * 1000, 3)
        return result, timings
    except Exception as exc:
        print(
            f"[v2.cert] read identity={cert_identity[:16]} "
            f"status=error error={str(exc)[:120]}",
            flush=True,
        )
        return None, timings
def _capture_remote_identity() -> dict[str, Any]:
    """Capture Modal identity and environment metadata at remote entry.

    Gathers ``modal.current_input_id()`` (safe fallback on failure), Modal
    runtime env vars, and current runtime mode.  Never raises â€” all access
    is wrapped in try/except.
    """
    identity: dict[str, Any] = {}
    try:
        if _modal is not None:
            input_id = _modal.current_input_id()
            if input_id:
                identity["modal_input_id"] = str(input_id)
    except Exception:
        pass
    for env_key, meta_key in (
        ("MODAL_TASK_ID", "container_task_id"),
        ("MODAL_IMAGE_ID", "image_id"),
        ("MODAL_CLOUD_PROVIDER", "cloud"),
        ("MODAL_REGION", "region"),
    ):
        value = os.environ.get(env_key, "")
        if value:
            identity[meta_key] = value
    runtime_mode = os.environ.get("COMFYMODAL_RUNTIME", "").strip()
    if runtime_mode:
        identity["runtime_mode"] = runtime_mode
    return identity


def _resource_identity(spec: ModalRuntimeSpec | None = None) -> dict[str, Any]:
    """Resource, volume, and snapshot configuration for invocation metadata.

    Returns the additive common-schema identity keys used across V1 and V2
    remote resource metadata.  All values are remote-observed or null/empty
    â€” never client-generated IDs or raw workflow/image/credential data.
    """
    actual = spec or _MODAL_RESOURCES.get("spec", ModalRuntimeSpec())
    return {
        # â”€â”€ App / class identity (from remote-observed values) â”€â”€â”€â”€â”€â”€â”€â”€
        "app_name": actual.app_name,
        "class_name": CLASS_NAME,
        # â”€â”€ Resource allocation â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        "gpu": list(actual.gpu),
        "cpu": actual.cpu,
        "memory_mb": actual.memory,
        "target_inputs": actual.target_inputs,
        "max_inputs": actual.max_inputs,
        # â”€â”€ Snapshot flags â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        "snapshot_enabled": str(actual.enable_memory_snapshot),
        "gpu_snapshot_enabled": str(
            os.environ.get("COMFYMODAL_ENABLE_GPU_SNAPSHOT", "0") == "1"
        ),
        # â”€â”€ Volume names and mount paths â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        "models_volume": actual.models_volume_name,
        "runtime_state_volume": actual.runtime_state_volume_name,
        "custom_nodes_volume": actual.custom_nodes_volume_name,
        "volume_mount_paths": {
            actual.models_volume_name: actual.models_path,
            actual.custom_nodes_volume_name: actual.custom_nodes_path,
            actual.runtime_state_volume_name: actual.runtime_state_path,
        },
        # â”€â”€ Snapshot target fingerprint â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        "fingerprint": _snapshot_target_fingerprint(actual),
    }


def _parse_memory_mb() -> int:
    """Parse COMFYMODAL_V2_MEMORY_MB, default 24576, positive int required."""
    raw = os.environ.get("COMFYMODAL_V2_MEMORY_MB", "24576").strip()
    if not raw:
        return 24576
    try:
        val = int(raw)
    except (ValueError, TypeError):
        raise RuntimeError(
            f"COMFYMODAL_V2_MEMORY_MB={raw!r} is not a valid integer"
        )
    if val <= 0:
        raise RuntimeError(
            f"COMFYMODAL_V2_MEMORY_MB={val} must be a positive integer (MiB)"
        )
    return val


def _snapshot_target_fingerprint(
    spec: ModalRuntimeSpec | None = None,
) -> str:
    """Deterministic stable hash of deployment-defined class resource config.

    Hashes app, registered remote class name, lifecycle/method decorator
    configuration, GPU/CPU/memory/timeout allocation, target/max inputs,
    min_containers/scaledown_window, enable_memory_snapshot, all three
    volume name + mount path identities, complete normalized
    ``_runtime_env()`` mapping, experimental_options GPU snapshot setting
    (when enabled), registration-known environment (``MODAL_ENVIRONMENT``),
    and source deployment combined hash.

    **Excludes** runtime-varying fields: cloud, region, image ID,
    task/container/session identity, hostname, PID. Those are emitted
    separately in ``[v2.snapshot_runtime]``.

    Never hashes live object reprs or unstable handles.  The result is a
    SHA-256 hex digest suitable for diagnostic correlation across
    startup/restore/request boundaries.
    """
    actual = spec or _MODAL_RESOURCES.get("spec", ModalRuntimeSpec())
    _source_id = _MODAL_RESOURCES.get("source_identity")
    _combined = _source_id.combined_hash if _source_id is not None else ""

    # Registered remote class name (decorated V2 subclass or base fallback)
    _registered_cls = globals().get("ModalRuntimeEntrypointV2", ModalRuntimeEntrypoint)

    # Stable static lifecycle/method decorator configuration (never changes at runtime)
    _lifecycle_config: dict[str, dict[str, Any]] = {
        "startup": {"enter": True, "snap": True},
        "restore": {"enter": True, "snap": False},
        "run_plan_stream": {"method": True, "is_generator": True},
        "run_prompt_stream": {"method": True, "is_generator": True},
        "publish_restore_plan": {"method": True, "is_generator": False},
        "read_output_asset": {"method": True, "is_generator": False},
        "run_checkpoint_stream": {"method": True, "is_generator": True},
    }

    # Complete normalized _runtime_env() mapping (captures snapshot/warmup class env)
    _env = _runtime_env()

    # Experimental_options GPU snapshot flag
    _enable_gpu_snapshot = os.environ.get("COMFYMODAL_ENABLE_GPU_SNAPSHOT", "0") == "1"

    # Volume name + mount path identities
    _vol_mount_paths: dict[str, str] = {
        actual.models_volume_name: actual.models_path,
        actual.custom_nodes_volume_name: actual.custom_nodes_path,
        actual.runtime_state_volume_name: actual.runtime_state_path,
    }

    _fingerprint_fields: dict[str, Any] = {
        # ── App / registered class identity ──────────────────────────────
        "app": actual.app_name,
        "class": _registered_cls.__name__,
        "lifecycle": _lifecycle_config,
        # ── Resource allocation ──────────────────────────────────────────
        "gpu": list(actual.gpu),
        "cpu": actual.cpu,
        "memory_mb": actual.memory,
        "timeout": actual.timeout,
        "target_inputs": actual.target_inputs,
        "max_inputs": actual.max_inputs,
        "min_containers": actual.min_containers,
        "scaledown_window": actual.scaledown_window,
        "enable_memory_snapshot": actual.enable_memory_snapshot,
        # ── Volume name + mount path identities ──────────────────────────
        "models_volume": actual.models_volume_name,
        "custom_nodes_volume": actual.custom_nodes_volume_name,
        "runtime_state_volume": actual.runtime_state_volume_name,
        "volume_mount_paths": _vol_mount_paths,
        # ── Source / env (static deployment config only) ─────────────────
        "source_combined_hash": _combined,
        "runtime_env": _env,
        "experimental_options": {"enable_gpu_snapshot": _enable_gpu_snapshot},
        "environment": os.environ.get("MODAL_ENVIRONMENT", ""),
    }
    return stable_hash(_fingerprint_fields)


def _snapshot_runtime_identity() -> dict[str, str]:
    """Runtime-specific identity for ``[v2.snapshot_runtime]`` emission.

    Contains ``image_id``, ``cloud``, ``region``, and
    ``container_session_id`` — fields that vary per runtime container
    but are NOT part of the static deployment snapshot target
    fingerprint.
    """
    return {
        "image_id": os.environ.get("MODAL_IMAGE_ID", ""),
        "cloud": os.environ.get("MODAL_CLOUD_PROVIDER", ""),
        "region": os.environ.get("MODAL_REGION", ""),
        "container_session_id": _V2_CONTAINER_SESSION_ID,
    }


@dataclass(frozen=True)
class ModalRuntimeSpec:
    app_name: str = APP_NAME
    models_volume_name: str = MODELS_VOLUME_NAME
    custom_nodes_volume_name: str = CUSTOM_NODES_VOLUME_NAME
    runtime_state_volume_name: str = RUNTIME_STATE_VOLUME_NAME
    models_path: str = MODELS_PATH
    custom_nodes_path: str = CUSTOM_NODES_PATH
    runtime_state_path: str = RUNTIME_STATE_PATH
    gpu: tuple[str, ...] = dataclasses.field(default_factory=parse_gpu_request)
    cpu: int = 4
    memory: int = dataclasses.field(default_factory=_parse_memory_mb)
    timeout: int = 3600
    target_inputs: int = 1
    max_inputs: int = 1
    min_containers: int = MIN_CONTAINERS
    scaledown_window: int = SCALEDOWN_WINDOW
    enable_memory_snapshot: bool = True


def _local_custom_nodes_root() -> Path:
    explicit = os.environ.get("COMFYMODAL_LOCAL_CUSTOM_NODES", "").strip()
    if explicit:
        return Path(explicit).resolve()
    return Path(__file__).resolve().parents[1]


def _collect_warmup_env() -> dict[str, str]:
    """Collect externally supplied ``COMFYMODAL_WARMUP_*`` env vars.

    Returns a dict of warmup environment variables that are present in the
    current process environment.  Absent keys are omitted so the Modal image
    inherits module-level defaults from ``comfyapp`` rather than being forced
    to empty strings.  Propagated keys:

    * ``COMFYMODAL_WARMUP_PROFILE``
    * ``COMFYMODAL_WARMUP_CHECKPOINT``
    * ``COMFYMODAL_WARMUP_UNET``
    * ``COMFYMODAL_WARMUP_CLIP1``
    * ``COMFYMODAL_WARMUP_CLIP2``
    * ``COMFYMODAL_WARMUP_VAE``
    * ``COMFYMODAL_WARMUP_CLIP_TYPE``
    * ``COMFYMODAL_WARMUP_TEXT``
    """
    _WARMUP_KEYS = (
        "COMFYMODAL_WARMUP_PROFILE",
        "COMFYMODAL_WARMUP_CHECKPOINT",
        "COMFYMODAL_WARMUP_UNET",
        "COMFYMODAL_WARMUP_CLIP1",
        "COMFYMODAL_WARMUP_CLIP2",
        "COMFYMODAL_WARMUP_VAE",
        "COMFYMODAL_WARMUP_CLIP_TYPE",
        "COMFYMODAL_WARMUP_TEXT",
    )
    return {k: os.environ[k] for k in _WARMUP_KEYS if k in os.environ}


def _runtime_env() -> dict[str, str]:
    """Build the runtime environment dict for Modal's class-level ``env=`` parameter.

    Contains ``COMFYMODAL_V2_CPU_MODEL_SNAPSHOT`` and
    ``COMFYMODAL_ENABLE_GPU_SNAPSHOT`` (both defaulting to ``"0"`` when
    absent from the local process environment), optional
    ``COMFYMODAL_V2_MEMORY_MB`` when present, and any ``COMFYMODAL_WARMUP_*``
    keys that are set in the current environment.

    This is used at deploy time via ``resources["app"].cls(..., env=...)``
    rather than as a build step on the Image, so Modal's requirement that
    ``image.env()`` precede ``add_local_python_source`` does not apply.
    """
    env = {
        "COMFYMODAL_V2_CPU_MODEL_SNAPSHOT": os.environ.get(
            "COMFYMODAL_V2_CPU_MODEL_SNAPSHOT", "0"
        ),
        "COMFYMODAL_ENABLE_GPU_SNAPSHOT": os.environ.get(
            "COMFYMODAL_ENABLE_GPU_SNAPSHOT", "0"
        ),
        "COMFYMODAL_V2_UNET_FORWARD_DIAG": os.environ.get(
            "COMFYMODAL_V2_UNET_FORWARD_DIAG", "0"
        ),
    }
    memory_mb = os.environ.get("COMFYMODAL_V2_MEMORY_MB")
    if memory_mb is not None:
        env["COMFYMODAL_V2_MEMORY_MB"] = memory_mb
    # Propagate externally-supplied warmup profile env vars so startup
    # snapshot creation can read a split profile via env_default fallback.
    env.update(_collect_warmup_env())
    return env


def _load_cpu_snapshot_unet(
    unet_name: str,
    weight_dtype: str,
    *,
    target_gpus: tuple[str, ...],
    unet_cls: Any,
) -> Any:
    """Load one snapshot UNET with the target-GPU-resolved dtype.

    For BF16-native compute policy (effective BF16 + BF16-capable target GPU),
    wraps the construction call in ``cpu_snapshot_unet_compute_policy`` so
    that ``comfy.model_management.unet_manual_cast`` returns ``None`` during
    the call.  This prevents ComfyUI from falling back to ``torch.float32``
    manual-cast on CPU and instead builds the model with native BF16 compute.
    """
    from comfymodal_runtime.model_preload import cpu_snapshot_unet_compute_policy
    from gpu_catalog import gpu_supports_bf16
    import torch as _torch_validate

    _eff_dtype, _eff_label = resolve_unet_effective_dtype(
        weight_dtype, target_gpus=target_gpus,
    )

    # Determine if BF16-native compute policy applies.
    # Primary GPU semantics: only the first target GPU determines BF16 capability,
    # consistent with resolve_unet_effective_dtype and _resolve_compute_policy.
    _primary_gpu = target_gpus[0] if target_gpus else ""
    _is_bf16_native = (
        _eff_dtype is not None
        and _eff_dtype == _torch_validate.bfloat16
        and _primary_gpu
        and gpu_supports_bf16(_primary_gpu)
    )

    if _eff_dtype is not None:
        import comfy.sd as _comfy_sd
        import folder_paths as _fp

        _unet_path = _fp.get_full_path_or_raise("diffusion_models", unet_name)

        with cpu_snapshot_unet_compute_policy(
            effective_weight_dtype=_eff_dtype,
            target_gpus=target_gpus,
        ):
            _model = _comfy_sd.load_diffusion_model(
                _unet_path,
                model_options={"dtype": _eff_dtype},
            )
        if isinstance(_model, (tuple, list)) and len(_model) > 0:
            _model = _model[0]

        # Construction validation for BF16-native policy
        if _is_bf16_native:
            validate_snapshot_unet_bf16_native(
                _model,
                context="snapshot_construction.",
                target_gpus=target_gpus,
                requested_weight_dtype=weight_dtype,
                effective_weight_dtype=_eff_dtype,
                effective_compute_dtype=_eff_dtype,
            )
        return _model

    if unet_cls is None:
        raise RuntimeError(
            f"snapshot UNET loader is unavailable for unresolved dtype {weight_dtype!r}"
        )
    loader = unet_cls()
    cls_method = unet_cls.load_unet if unet_cls else None
    orig = getattr(cls_method, "_comfy_modal_v2_original", None)
    if orig is not None:
        with cpu_snapshot_unet_compute_policy(
            effective_weight_dtype=_eff_dtype,
            target_gpus=target_gpus,
        ):
            out = orig(loader, unet_name, weight_dtype)
    else:
        with cpu_snapshot_unet_compute_policy(
            effective_weight_dtype=_eff_dtype,
            target_gpus=target_gpus,
        ):
            out = loader.load_unet(unet_name, weight_dtype)
    if isinstance(out, (tuple, list)) and len(out) > 0:
        out = out[0]

    # Construction validation for BF16-native policy (unet_cls path)
    if _is_bf16_native:
        validate_snapshot_unet_bf16_native(
            out,
            context="snapshot_construction.",
            target_gpus=target_gpus,
            requested_weight_dtype=weight_dtype,
            effective_weight_dtype=_eff_dtype,
            effective_compute_dtype=_eff_dtype,
        )
    return out


def _reference_image() -> Any:
    """Build the V2 shadow deployment image from the production base.

    Uses ``_image_base`` (pre-local-sources) so that the V2 source modules
    can be appended legally — Modal requires that all build steps
    (``.pip_install``, ``.run_commands``, ``.env()``, ``.add_local_dir``)
    precede ``.add_local_python_source()``, and ``_image_base`` already
    satisfies that constraint.

    Environment variables (snapshot flags, warmup profile, memory) are
    **not** set here via ``image.env()`` — they are propagated at deploy
    time via the class-level ``env=`` parameter in
    ``_register_remote_entrypoint`` using ``_runtime_env()``.  This avoids
    adding build steps to an image whose base may already contain
    ``add_local_dir``/``add_local_file`` operations.
    """
    try:
        legacy = importlib.import_module("comfyapp")
        # Use _image_base (pre-local-sources).  comfyapp.image already has
        # add_local_python_source applied and cannot be further modified with
        # build-step commands.
        base = getattr(legacy, "_image_base", None)
        if base is None:
            # Fallback: attempt the fully-built image (risks build-order
            # rejection, but avoids hard crash when _image_base is absent)
            base = getattr(legacy, "image", None)
            if base is None:
                raise RuntimeError("comfyapp._image_base and .image are unavailable")
        image = base
        for module_name in V2_SOURCE_MODULES:
            image = image.add_local_python_source(module_name)
        return image
    except Exception as exc:
        raise RuntimeError("unable to build v2 image from the working ComfyUI image") from exc


def build_modal_resources(*, spec: ModalRuntimeSpec | None = None) -> dict[str, Any]:
    """Build the actual v2 app, image, Volumes, and source identity."""
    runtime_spec = spec or ModalRuntimeSpec()
    # Lightweight container path: standalone publisher never needs
    # custom_nodes_root, deployment identity, reference image, or
    # Modal volume/app handles.  Return null resources immediately.
    if os.environ.get(_PUBLISHER_MARKER) == "1":
        print("[comfymodal] publisher_container=1 skipping heavyweight resource construction", flush=True)
        return {
            "app": None,
            "image": None,
            "models_volume": None,
            "custom_nodes_volume": None,
            "runtime_state_volume": None,
            "source_identity": None,
            "spec": runtime_spec,
        }
    runtime_root = Path(__file__).resolve().parent
    custom_root = _local_custom_nodes_root()
    identity = build_deployment_identity(runtime_root, custom_node_paths=[custom_root])
    if _modal is None:
        return {
            "app": None,
            "image": None,
            "models_volume": None,
            "custom_nodes_volume": None,
            "runtime_state_volume": None,
            "source_identity": identity,
            "spec": runtime_spec,
        }

    image = _reference_image()
    models_volume = _modal.Volume.from_name(runtime_spec.models_volume_name, create_if_missing=True)
    custom_nodes_volume = _modal.Volume.from_name(runtime_spec.custom_nodes_volume_name, create_if_missing=True)
    runtime_state_volume = _modal.Volume.from_name(runtime_spec.runtime_state_volume_name, create_if_missing=True)
    app = _modal.App(runtime_spec.app_name, image=image)
    return {
        "app": app,
        "image": image,
        "models_volume": models_volume,
        "custom_nodes_volume": custom_nodes_volume,
        "runtime_state_volume": runtime_state_volume,
        "source_identity": identity,
        "spec": runtime_spec,
    }


# Host memory reporting (cgroup v2 + process rss)


def _unescape_mountinfo_field(value: str) -> str:
    return (
        value.replace(r"\040", " ")
        .replace(r"\011", "\t")
        .replace(r"\012", "\n")
        .replace(r"\134", "\\")
    )


def _resolve_cgroup_v2_base(
    mountinfo_path: str = "/proc/self/mountinfo",
    cgroup_path: str = "/proc/self/cgroup",
) -> tuple[str, str] | None:
    """Resolve the process cgroup v2 directory from procfs metadata.

    Returns ``(resolved_cgroup_base, mount_point)`` on success, ``None`` on any
    error.  The resolved path includes the mount point and the cgroup relative
    path joined together (e.g. ``/sys/fs/cgroup/user.slice/job-123``).
    """
    mount_point: str | None = None
    try:
        with open(mountinfo_path) as f:
            for line in f:
                parts = line.split()
                separator = next(
                    (index for index, part in enumerate(parts) if part == "-"),
                    None,
                )
                if (
                    separator is not None
                    and separator >= 5
                    and separator + 1 < len(parts)
                    and parts[separator + 1] == "cgroup2"
                ):
                    candidate = _unescape_mountinfo_field(parts[4])
                    if candidate.startswith("/"):
                        mount_point = candidate
                        break
    except Exception:
        return None
    if not mount_point:
        return None

    cgroup_rel: str | None = None
    try:
        with open(cgroup_path) as f:
            for line in f:
                stripped = line.strip()
                if stripped.startswith("0::"):
                    cgroup_rel = stripped[3:]
                    break
    except Exception:
        return None
    if cgroup_rel is None:
        return None
    if not cgroup_rel or cgroup_rel == "/":
        return (mount_point, mount_point)
    if not cgroup_rel.startswith("/"):
        return None
    components = [component for component in cgroup_rel.split("/") if component]
    if any(component in {".", ".."} for component in components):
        return None
    return (posixpath.join(mount_point, *components), mount_point)


def _read_cgroup_v2_memory(path: str) -> int | str | None:
    """Read a cgroup v2 memory stat file, preserving an unlimited ``max``."""
    try:
        with open(path) as f:
            raw = f.read().strip()
            if raw == "max":
                return raw
            return int(raw)
    except Exception:
        return None


def _report_host_memory(stage: str) -> dict[str, Any]:
    """Low-overhead host memory snapshot.

    Emits ``[v2.host_memory]`` with cgroup v2 memory MiB conversions, OOM
    counters, process RSS, and resolved cgroup paths.  Resolves cgroup v2
    paths through ``/proc/self/mountinfo`` and ``/proc/self/cgroup``.
    Reads ``memory.current``, ``memory.peak``, ``memory.max``,
    ``memory.events``, and ``memory.stat`` when available; parses OOM,
    OOM kill, and selected memory.stat counters.  Missing values are
    reported as ``"absent"``.  Unlimited memory.max is reported as
    ``"unlimited"``.  Never raises.
    """
    info: dict[str, Any] = {
        "stage": stage,
        "memory.current": "absent",
        "memory.peak": "absent",
        "memory.max": "absent",
        "memory.events": "absent",
        "current_mib": "absent",
        "peak_mib": "absent",
        "limit_mib": "absent",
        "process_rss_mib": "absent",
        "process_maxrss_mib": "absent",
        "oom_count": "absent",
        "oom_kill_count": "absent",
        "cgroup_path": "absent",
        "cgroup_mount": "absent",
    }
    try:
        if platform.system() == "Linux":
            cgroup_result = _resolve_cgroup_v2_base()
            cgroup_base: str | None = None
            cgroup_mount: str | None = None
            if cgroup_result is not None:
                cgroup_base, cgroup_mount = cgroup_result
            if cgroup_base:
                info["cgroup_path"] = cgroup_base
            if cgroup_mount:
                info["cgroup_mount"] = cgroup_mount

            # memory.current
            if cgroup_base:
                mem_current = _read_cgroup_v2_memory(posixpath.join(cgroup_base, "memory.current"))
            else:
                mem_current = None
            if isinstance(mem_current, int) and mem_current >= 0:
                info["memory.current"] = mem_current
                info["current_mib"] = round(mem_current / (1024 * 1024), 1)
            # memory.peak
            if cgroup_base:
                mem_peak = _read_cgroup_v2_memory(posixpath.join(cgroup_base, "memory.peak"))
            else:
                mem_peak = None
            if isinstance(mem_peak, int) and mem_peak >= 0:
                info["memory.peak"] = mem_peak
                info["peak_mib"] = round(mem_peak / (1024 * 1024), 1)
            # memory.max (limit)
            if cgroup_base:
                mem_max = _read_cgroup_v2_memory(posixpath.join(cgroup_base, "memory.max"))
            else:
                mem_max = None
            if isinstance(mem_max, str) and mem_max == "max":
                info["memory.max"] = "max"
                info["limit_mib"] = "unlimited"
            elif isinstance(mem_max, int) and mem_max >= 0:
                info["memory.max"] = mem_max
                if mem_max < 2**60:
                    info["limit_mib"] = round(mem_max / (1024 * 1024), 1)
            # memory.events (OOM)
            if cgroup_base:
                try:
                    events_path = posixpath.join(cgroup_base, "memory.events")
                    events: dict[str, int] = {}
                    with open(events_path) as f:
                        for line in f:
                            line = line.strip()
                            if " " in line:
                                key, val_str = line.split(" ", 1)
                                try:
                                    events[key] = int(val_str)
                                except ValueError:
                                    pass
                    if events:
                        info["memory.events"] = events
                        info["oom_count"] = events.get("oom", "absent")
                        info["oom_kill_count"] = events.get("oom_kill", "absent")
                except Exception:
                    pass
            # memory.stat (file, inactive_file, active_file, workingset_*)
            if cgroup_base:
                try:
                    stat_path = posixpath.join(cgroup_base, "memory.stat")
                    _stat_keys = {
                        "file", "inactive_file", "active_file",
                        "workingset_refault_file", "workingset_activate_file",
                        "pgfault", "pgmajfault",
                    }
                    with open(stat_path) as f:
                        for line in f:
                            line = line.strip()
                            if " " in line:
                                key, val_str = line.split(" ", 1)
                                if key in _stat_keys:
                                    try:
                                        info.setdefault("memory.stat", {})[key] = int(val_str)
                                    except ValueError:
                                        pass
                except Exception:
                    pass
        # Process RSS from /proc/self/status
        if platform.system() == "Linux":
            try:
                with open("/proc/self/status") as f:
                    for line in f:
                        if line.startswith("VmRSS:"):
                            parts = line.split()
                            if len(parts) >= 2:
                                info["process_rss_mib"] = round(int(parts[1]) / 1024, 1)
            except Exception:
                pass
        # Host-memory process_maxrss_mib from rusage (cross-platform)
        try:
            import resource as _resource
            _maxrss_kb = _resource.getrusage(_resource.RUSAGE_SELF).ru_maxrss
            if _maxrss_kb > 0:
                info["process_maxrss_mib"] = round(_maxrss_kb / 1024, 1)
        except Exception:
            pass
        info["status"] = "ok"
    except Exception:
        info["status"] = "error"
    # One-line [v2.host_memory] with spec-compliant fields only.
    # Do NOT include raw memory.current, memory.peak, memory.max, memory.events,
    # memory.stat field names — only MiB-formatted values and aggregate counters.
    _line_fields: dict[str, Any] = {
        "stage": info.get("stage", stage),
        "current_mib": info.get("current_mib", "absent"),
        "peak_mib": info.get("peak_mib", "absent"),
        "limit_mib": info.get("limit_mib", "absent"),
        "process_rss_mib": info.get("process_rss_mib", "absent"),
        "process_maxrss_mib": info.get("process_maxrss_mib", "absent"),
        "oom_count": info.get("oom_count", "absent"),
        "oom_kill_count": info.get("oom_kill_count", "absent"),
        "status": info.get("status", "ok"),
        "cgroup_path": info.get("cgroup_path", "absent"),
        "cgroup_mount": info.get("cgroup_mount", "absent"),
    }
    _line = " ".join(
        f"{k}={v}" for k, v in _line_fields.items()
    )
    print(f"[v2.host_memory] {_line}", flush=True)
    return info


# â”€â”€ GPU allocation reporting (remote runtime capabilities) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


def _detect_gpu_allocation(requested_gpu_order: tuple[str, ...]) -> dict[str, Any]:
    """Detect actual GPU runtime capabilities and emit ``[v2.gpu_allocation]``.

    Uses ``torch`` and ``nvidia-smi``-equivalent introspection to report
    the GPU that was actually allocated.  Never raises.
    """
    info: dict[str, Any] = {
        "gpu_requested_order": ",".join(requested_gpu_order),
    }
    try:
        import torch
        info["torch_version"] = torch.__version__
        if torch.cuda.is_available():
            device_count = torch.cuda.device_count()
            if device_count > 0:
                props = torch.cuda.get_device_properties(0)
                info["gpu_actual_name"] = props.name
                info["gpu_compute_capability"] = f"{props.major}.{props.minor}"
                info["gpu_vram_total_mib"] = props.total_memory // (1024 * 1024)
            info["cuda_version"] = torch.version.cuda or ""
    except Exception:
        pass
    # Print one-line summary
    _fmt = {k: v for k, v in info.items() if v is not None}
    _line = " ".join(
        f"{k}={v}" for k, v in sorted(_fmt.items())
    )
    print(f"[v2.gpu_allocation] {_line}", flush=True)
    return info


def _resolve_cgroup_cpu_stat_path() -> tuple[str | None, list[str], list[str]]:
    """Resolve a readable cpu.stat path using CPU-specific probing.

    Probes in order:
      1. ``_resolve_cgroup_v2_base()[0]/cpu.stat`` when the resolver returns a base.
      2. ``/sys/fs/cgroup/cpu.stat``
      3. Parse the unified ``0::...`` line from ``/proc/self/cgroup``, join the
         relative path below ``/sys/fs/cgroup``, and probe its ``cpu.stat``.

    Returns ``(path, candidates, errors)`` where *path* is the first readable
    absolute path or ``None``, *candidates* lists every attempted path, and
    *errors* lists per-probe diagnostic messages with exception type+message.
    """
    candidates: list[str] = []
    errors: list[str] = []

    def _probe(path: str, label: str) -> str | None:
        if path in candidates:
            return None
        candidates.append(path)
        try:
            with open(path) as _f:
                _f.read(1)
        except Exception as exc:
            errors.append(f"{label} path={path}: {type(exc).__name__}: {exc}")
            return None
        return path

    # Probe 1: _resolve_cgroup_v2_base()[0] + "/cpu.stat"
    try:
        base = _resolve_cgroup_v2_base()
    except Exception as exc:
        errors.append(f"resolve_cgroup_v2_base: {type(exc).__name__}: {exc}")
        base = None
    if base is None:
        errors.append("resolve_cgroup_v2_base: returned no readable cgroup base")
    else:
        path = _probe(posixpath.join(base[0], "cpu.stat"), "probe1")
        if path is not None:
            return path, candidates, errors

    # Probe 2: /sys/fs/cgroup/cpu.stat
    path = _probe("/sys/fs/cgroup/cpu.stat", "probe2")
    if path is not None:
        return path, candidates, errors

    # Probe 3: parse /proc/self/cgroup unified line, join below /sys/fs/cgroup
    _cgroup_rel: str | None = None
    try:
        with open("/proc/self/cgroup") as _f:
            for _line in _f:
                _stripped = _line.strip()
                if _stripped.startswith("0::"):
                    _cgroup_rel = _stripped[3:]
                    break
    except Exception as exc:
        errors.append(f"parse_proc_cgroup: {type(exc).__name__}: {exc}")
    if _cgroup_rel is None:
        errors.append("parse_proc_cgroup: no unified 0:: entry")
    else:
        _rel = _cgroup_rel if _cgroup_rel.startswith("/") else f"/{_cgroup_rel}"
        _components = [component for component in _rel.split("/") if component]
        if any(component in {".", ".."} for component in _components):
            errors.append(f"parse_proc_cgroup: unsafe unified path {_cgroup_rel!r}")
        else:
            path = _probe(
                posixpath.join("/sys/fs/cgroup", *_components, "cpu.stat"),
                "probe3",
            )
            if path is not None:
                return path, candidates, errors

    return None, candidates, errors


def _read_cgroup_cpu_usage_usec(cpu_stat_path: str) -> int | None:
    """Read ``usage_usec`` from an already-resolved ``cpu.stat`` file.

    Takes the full absolute path directly.  Does NOT swallow exceptions —
    callers that need resilience (e.g. the sampler background thread) must
    catch at their own boundary.
    """
    with open(cpu_stat_path) as cpu_stat:
        for line in cpu_stat:
            key, _, value = line.partition(" ")
            if key == "usage_usec":
                usage = int(value.strip())
                return usage if usage >= 0 else None
    return None


def _emit_cgroup_spike_summary(peak: float, intervals: list[dict[str, Any]]) -> None:
    parts = [
        f"peak_effective_cores={peak:.3f}",
        f"interval_count={len(intervals)}",
    ]
    for index, interval in enumerate(intervals):
        parts.extend(
            (
                f"i{index}_start_unix_ns={interval['start_unix_ns']}",
                f"i{index}_end_unix_ns={interval['end_unix_ns']}",
                f"i{index}_start_elapsed_ms={interval['start_elapsed_ms']:.3f}",
                f"i{index}_end_elapsed_ms={interval['end_elapsed_ms']:.3f}",
                f"i{index}_duration_ms={interval['duration_ms']:.3f}",
                f"i{index}_mean_effective_cores={interval['mean_effective_cores']:.3f}",
                f"i{index}_peak_effective_cores={interval['peak_effective_cores']:.3f}",
                f"i{index}_phase={interval['phase']}",
            )
        )
    print(f"[v2.cgroup_cpu_spike] {' '.join(parts)}", flush=True)


def _emit_cgroup_cpu_unavailable(
    reason: str,
    candidates: list[str],
    errors: list[str],
) -> None:
    candidate_text = ";".join(candidates) or "none"
    error_text = ";".join(errors) or "none"
    print(
        f"[v2.cgroup_cpu_spike] status=unavailable "
        f"reason={reason} candidates={candidate_text} errors={error_text}",
        flush=True,
    )


class _CgroupCpuSample:
    __slots__ = (
        "timestamp_unix_ns",
        "elapsed_request_ms",
        "effective_cgroup_cores",
        "phase",
    )

    def __init__(
        self,
        timestamp_unix_ns: int,
        elapsed_request_ms: float,
        effective_cgroup_cores: float,
        phase: str,
    ) -> None:
        self.timestamp_unix_ns = timestamp_unix_ns
        self.elapsed_request_ms = elapsed_request_ms
        self.effective_cgroup_cores = effective_cgroup_cores
        self.phase = phase


class _CgroupCpuSampler:
    _INTERVAL_SECONDS = 0.050

    def __init__(self, method_entry_mono_ns: int) -> None:
        self._method_entry_mono_ns = method_entry_mono_ns
        self._samples: list[_CgroupCpuSample] = []
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._lock = threading.Lock()
        self._phase = "method"
        self._phase_source: Callable[[], str] | None = None
        self._cpu_stat_path, self._resolution_candidates, self._resolution_errors = (
            _resolve_cgroup_cpu_stat_path()
        )
        self._resolution_failure = (
            "no readable cpu.stat" if self._cpu_stat_path is None else None
        )
        self._failure_reason: str | None = None
        self._prev_usage_usec: int | None = None
        self._prev_mono_ns: int | None = None

    def start(self) -> None:
        if not self._cpu_stat_path or self._thread is not None:
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self) -> None:
        self._sample()
        while not self._stop_event.wait(self._INTERVAL_SECONDS):
            self._sample()

    def _current_phase(self) -> str:
        source = self._phase_source
        if source is not None:
            try:
                phase = source()
                if phase:
                    return str(phase)
            except Exception:
                pass
        return self._phase

    def _sample(self) -> None:
        if not self._cpu_stat_path:
            return
        try:
            usage_usec = _read_cgroup_cpu_usage_usec(self._cpu_stat_path)
        except Exception as exc:
            self._failure_reason = f"read_error: {type(exc).__name__}: {exc}"
            return
        if usage_usec is None:
            self._failure_reason = (
                f"read_error: {self._cpu_stat_path}: missing usage_usec"
            )
            return
        now_mono_ns = time.monotonic_ns()
        now_unix_ns = time.time_ns()
        with self._lock:
            if self._prev_usage_usec is None or self._prev_mono_ns is None:
                effective_cores = 0.0
            else:
                delta_usage_usec = usage_usec - self._prev_usage_usec
                delta_wall_usec = (now_mono_ns - self._prev_mono_ns) / 1_000.0
                effective_cores = (
                    max(0.0, delta_usage_usec / delta_wall_usec)
                    if delta_wall_usec > 0.0
                    else 0.0
                )
            self._samples.append(
                _CgroupCpuSample(
                    timestamp_unix_ns=now_unix_ns,
                    elapsed_request_ms=round(
                        (now_mono_ns - self._method_entry_mono_ns) / 1_000_000.0,
                        3,
                    ),
                    effective_cgroup_cores=round(effective_cores, 3),
                    phase=self._current_phase(),
                )
            )
            self._prev_usage_usec = usage_usec
            self._prev_mono_ns = now_mono_ns

    def set_phase_source(self, source: Callable[[], str]) -> None:
        self._phase_source = source

    def set_phase(self, phase: str) -> None:
        self._phase = phase

    def report(self) -> None:
        samples = self._snapshot()
        if not samples:
            reason_parts: list[str] = []
            if self._resolution_failure:
                reason_parts.append(self._resolution_failure)
            if self._failure_reason:
                reason_parts.append(self._failure_reason)
            if not reason_parts:
                reason_parts.append("zero_samples")
            _emit_cgroup_cpu_unavailable(
                reason=" | ".join(reason_parts),
                candidates=self._resolution_candidates,
                errors=self._resolution_errors + (
                    [self._failure_reason] if self._failure_reason else []
                ),
            )
            return
        _emit_cgroup_spike_summary(
            self.compute_peak_cores(), self.compute_spike_intervals()
        )

    def stop(self) -> None:
        thread = self._thread
        if thread is None:
            return
        self._stop_event.set()
        thread.join()
        self._thread = None
        self._sample()

    def _snapshot(self) -> list[_CgroupCpuSample]:
        with self._lock:
            return list(self._samples)

    def compute_peak_cores(self) -> float:
        samples = self._snapshot()
        return max(
            (sample.effective_cgroup_cores for sample in samples),
            default=0.0,
        )

    def compute_spike_intervals(self, threshold: float = 12.0) -> list[dict[str, Any]]:
        samples = self._snapshot()
        intervals: list[dict[str, Any]] = []
        current: list[tuple[_CgroupCpuSample, _CgroupCpuSample]] = []
        previous_index = -2
        current_phase = ""
        for index in range(1, len(samples)):
            previous = samples[index - 1]
            sample = samples[index]
            if sample.effective_cgroup_cores <= threshold:
                if current:
                    intervals.append(_summarize_cgroup_interval(current))
                    current = []
                previous_index = -2
                current_phase = ""
                continue
            if current and (index != previous_index + 1 or sample.phase != current_phase):
                intervals.append(_summarize_cgroup_interval(current))
                current = []
            current.append((previous, sample))
            previous_index = index
            current_phase = sample.phase
        if current:
            intervals.append(_summarize_cgroup_interval(current))
        return intervals


def _summarize_cgroup_interval(
    sample_intervals: list[tuple[_CgroupCpuSample, _CgroupCpuSample]],
) -> dict[str, Any]:
    first_previous, _ = sample_intervals[0]
    _, last_sample = sample_intervals[-1]
    weighted_core_ms = 0.0
    for previous, sample in sample_intervals:
        interval_ms = max(0.0, sample.elapsed_request_ms - previous.elapsed_request_ms)
        weighted_core_ms += sample.effective_cgroup_cores * interval_ms
    duration_ms = max(
        0.0,
        last_sample.elapsed_request_ms - first_previous.elapsed_request_ms,
    )
    return {
        "start_unix_ns": first_previous.timestamp_unix_ns,
        "end_unix_ns": last_sample.timestamp_unix_ns,
        "start_elapsed_ms": first_previous.elapsed_request_ms,
        "end_elapsed_ms": last_sample.elapsed_request_ms,
        "duration_ms": round(duration_ms, 3),
        "mean_effective_cores": round(
            weighted_core_ms / duration_ms if duration_ms > 0.0 else 0.0,
            3,
        ),
        "peak_effective_cores": max(
            sample.effective_cgroup_cores for _, sample in sample_intervals
        ),
        "phase": sample_intervals[0][1].phase,
    }


async def _with_cgroup_sampler_cleanup(
    stream: AsyncIterator[dict[str, Any]],
    sampler: _CgroupCpuSampler | None,
) -> AsyncIterator[dict[str, Any]]:
    try:
        async for event in stream:
            yield event
    finally:
        if sampler is not None:
            sampler.stop()


class ModalRuntimeEntrypoint:
    """Real v2 runtime facade backed by the existing ComfyUI executor."""

    def __init__(
        self,
        *,
        bootstrap: RuntimeBootstrap | None = None,
        executor: RuntimeExecutor | None = None,
        config: BootstrapConfig | None = None,
        checkpoint_runner: Callable[..., Any] | None = None,
    ) -> None:
        self._config = config
        self._bootstrap_injected = bootstrap is not None
        self.bootstrap = bootstrap or RuntimeBootstrap(config)
        self._executor_injected = executor is not None
        self.executor = executor or RuntimeExecutor(in_process_runner=self._run_in_process)
        self.checkpoint_runner = checkpoint_runner
        self._legacy_module: Any | None = None
        self._legacy_api: Any | None = None
        self._runtime_configured = False
        self._restore_plan: RestorePlan | None = None
        self._restore_publisher: RestorePlanPublisher | None = None
        self._preload_bridge = V2LoaderBridge()
        self._lifecycle_trace: RuntimeTrace | None = None
        # Stable module-level identity so snapshot boundaries cannot erase identity.
        self.container_session_id: str = _V2_CONTAINER_SESSION_ID
        self._restore_count: int = 0
        self._request_count: int = 0
        self._restore_timing: dict[str, Any] | None = None
        self._cgroup_sampler: _CgroupCpuSampler | None = None
        # CPU snapshot model state (Plan C lifecycle)
        self._cpu_snapshot_models: CpuSnapshotModels | None = None
        self._cpu_snapshot_models_active: bool = False
        # Propagated UNET runtime state from restore() to request trace.
        self._cpu_snapshot_unet_runtime_state: dict[str, Any] | None = None

    def _remember_lifecycle_trace(self, trace: RuntimeTrace) -> None:
        if self._lifecycle_trace is None:
            self._lifecycle_trace = trace
        elif self._lifecycle_trace is not trace:
            self._lifecycle_trace.extend(trace.events)

    def _get_remote_restore_publisher(self) -> RestorePlanPublisher:
        if self._restore_publisher is not None:
            return self._restore_publisher
        resources = globals().get("_MODAL_RESOURCES", {})
        modal_volume = resources.get("runtime_state_volume")
        if modal_volume is None:
            raise RuntimeError("v2 runtime-state Modal Volume is not mounted")
        volume = ModalMountedStateVolume(RUNTIME_STATE_PATH, modal_volume)
        coordinator = CommitCoordinator(volume, state_path=V2_RESTORE_STATE_FILE)
        self._restore_publisher = RestorePlanPublisher(coordinator)
        return self._restore_publisher

    def _join_legacy_background_threads(self, api: Any, *, join_timeout: float = 30.0) -> int:
        """Join remaining alive threads in the legacy API's ``_actual_load_futures``.

        Returns the number of threads joined.  Uses a bounded per-thread
        timeout.  If the graph already consumed the future (thread is dead),
        the join returns immediately.  Never raises â€” errors are swallowed so
        existing error behaviour is preserved.
        """
        joined = 0
        if api is None:
            return 0
        try:
            futures = getattr(api, "_actual_load_futures", None)
            if not isinstance(futures, dict):
                return 0
            for key, thread in list(futures.items()):
                if thread is not None and getattr(thread, "is_alive", lambda: False)():
                    try:
                        thread.join(timeout=join_timeout)
                        joined += 1
                    except Exception:
                        pass
        except Exception:
            pass
        return joined

    @staticmethod
    def _check_unet_deferral_eligible(api: Any, plan: Any) -> bool:
        """Return True when the optimized V2 UNET-deferral handoff is eligible.

        Checks that the plan has a UNET identity and the legacy API exposes
        the two helper methods needed by the handoff.  Never raises.
        """
        try:
            if plan is None:
                return False
            model_key = getattr(plan, "model_key", None)
            if model_key is None or not getattr(model_key, "unet_identity", ""):
                return False
            if not callable(getattr(api, '_patch_unet_loader_cache', None)):
                return False
            if not callable(getattr(api, '_start_production_restore_unet', None)):
                return False
            return True
        except Exception:
            return False

    def _lazy_init_snapshot_state(self) -> None:
        """Ensure CPU snapshot instance attrs exist after unpickling.

        Modal may unpickle a cold instance whose __init__ was never called.
        This helper ensures the three CPU-snapshot attrs are always present
        regardless of how the instance was created.
        """
        if not hasattr(self, "_cpu_snapshot_models"):
            self._cpu_snapshot_models = None
        if not hasattr(self, "_cpu_snapshot_models_active"):
            self._cpu_snapshot_models_active = False
        if not hasattr(self, "_cpu_snapshot_unet_runtime_state"):
            self._cpu_snapshot_unet_runtime_state = None

    def _cpu_snapshot_profile(self, api: Any) -> Mapping[str, Any] | None:
        """Derive a validated warmup profile for a CPU model snapshot.

        Requires the output of ``api._snapshot_preload_profile()`` to be a
        Mapping containing ``mode`` (must be ``"split"``), ``unet``,
        ``clip1``, and ``clip_type`` as non-empty strings.  ``clip2`` is
        optional.  Raises ``RuntimeError`` when the profile is missing,
        not a mapping, has an unsupported mode, or lacks required fields.
        """
        self._lazy_init_snapshot_state()
        raw = api._snapshot_preload_profile()
        if raw is None:
            env_profile = os.environ.get("COMFYMODAL_WARMUP_PROFILE", "")
            env_unet = os.environ.get("COMFYMODAL_WARMUP_UNET", "")
            env_clip1 = os.environ.get("COMFYMODAL_WARMUP_CLIP1", "")
            env_clip_type = os.environ.get("COMFYMODAL_WARMUP_CLIP_TYPE", "")
            if (
                env_profile == "split"
                and env_unet.strip()
                and env_clip1.strip()
                and env_clip_type.strip()
            ):
                profile: dict[str, str] = {
                    "mode": "split",
                    "unet": env_unet,
                    "clip1": env_clip1,
                    "clip_type": env_clip_type,
                }
                env_clip2 = os.environ.get("COMFYMODAL_WARMUP_CLIP2", "")
                if env_clip2.strip():
                    profile["clip2"] = env_clip2
                env_vae = os.environ.get("COMFYMODAL_WARMUP_VAE", "")
                if env_vae.strip():
                    profile["vae"] = env_vae
                return profile
            raise RuntimeError("cpu model snapshot profile is None")
        if not isinstance(raw, Mapping):
            raise RuntimeError(
                f"cpu model snapshot profile must be a Mapping, got {type(raw).__name__}"
            )
        profile = dict(raw)
        mode = profile.get("mode", "")
        if not isinstance(mode, str) or mode.strip() != "split":
            raise RuntimeError(
                f"cpu model snapshot profile mode must be 'split', got {mode!r}"
            )
        required = ("unet", "clip1", "clip_type")
        for key in required:
            value = profile.get(key)
            if not isinstance(value, str) or not value.strip():
                raise RuntimeError(
                    f"cpu model snapshot profile {key} must be a non-empty string, "
                    f"got {value!r}"
                )
        return profile

    def _use_cpu_snapshot_models_on_bridge(
        self,
        model_key: Any,
        prefill_key: Any,
        model_spec: Any,
        unet: Any,
        clip: Any,
        trace: RuntimeTrace | None = None,
    ) -> None:
        """Activate already-loaded CPU snapshot models on the preload bridge.

        Delegates to ``V2LoaderBridge.use_ready_models(...)`` which creates
        a fully-resolved ``RestorePreparation`` with completed futures so
        graph-time consumers retrieve the snapshot models without going
        through the thread pool.  On failure the bridge is cleared and
        active state is reset so the existing preload path runs.
        Never sets private fields directly on the bridge.
        """
        try:
            self._preload_bridge.use_ready_models(
                model_key=model_key,
                prefill_key=prefill_key,
                model_spec=model_spec,
                unet=unet,
                clip=clip,
                trace=trace,
            )
        except Exception:
            self._preload_bridge.clear()
            self._cpu_snapshot_models_active = False
            self._cpu_snapshot_unet_runtime_state = None
            raise

    def _load_legacy_runtime(self) -> Any:
        if self._legacy_api is not None:
            return self._legacy_api
        module = self._legacy_module or importlib.import_module("comfyapp")
        gpu_value = os.environ.get("COMFYMODAL_V2_GPU", "rtx-pro-6000").strip().lower()
        class_name = "ComfyAPI"
        try:
            catalog = importlib.import_module("gpu_catalog")
            class_name = catalog.GPU_BY_VALUE.get(gpu_value, {}).get("class_name", class_name)
        except Exception:
            pass
        api_class = getattr(module, class_name, None) or getattr(module, "ComfyAPI", None)
        if api_class is None:
            raise RuntimeError(f"ComfyUI GPU runtime class is unavailable: {class_name}")
        self._legacy_module = module
        self._legacy_api = api_class()
        return self._legacy_api

    def _gpu_requested_order(self) -> tuple[str, ...]:
        """Return the ordered GPU list from spec, falling back to env-based parse."""
        spec = _MODAL_RESOURCES.get("spec")
        if spec is not None and spec.gpu:
            return spec.gpu
        return parse_gpu_request()

    def _configure_runtime(self) -> None:
        if self._runtime_configured or self._bootstrap_injected:
            return
        api = self._load_legacy_runtime()
        module = self._legacy_module

        # Make the canonical deployment combined hash available to the loaded
        # comfyapp module so that ``_resolve_deployment_combined_hash()``
        # returns the builder-computed value on first priority.
        module._CANONICAL_DEPLOYMENT_COMBINED_HASH = _V2_DEPLOYMENT_COMBINED_HASH

        # ── Restore-accounting timer wrappers ──
        # Each wrapped callback records monotonic duration into module-level
        # _RESTORE_STAGE_TIMERS.  The accumulated durations are merged into
        # _restore_timing at the restore() method boundary.
        def _wrap_restore_stage(name: str, fn: Callable[[], Any]) -> Callable[[], Any]:
            """Return a wrapper that records monotonic wall time in _RESTORE_STAGE_TIMERS."""
            global _RESTORE_STAGE_TIMERS
            def _timed() -> Any:
                _start = time.monotonic_ns()
                try:
                    return fn()
                finally:
                    _dur = round((time.monotonic_ns() - _start) / 1_000_000, 3)
                    _RESTORE_STAGE_TIMERS[name] = _RESTORE_STAGE_TIMERS.get(name, 0.0) + _dur
            return _timed

        def reload_models() -> None:
            volume = getattr(module, "vol", None)
            if volume is not None:
                volume.reload()

        def reload_runtime_state() -> None:
            volume = getattr(module, "runtime_config_vol", None)
            if volume is not None:
                volume.reload()

        def sync_custom_nodes() -> Any:
            return api._sync_custom_nodes_from_volume()

        def install_requirements() -> Any:
            return api._install_custom_node_requirements()

        def start_backend() -> str:
            snapshot_context = getattr(api, "_force_cpu_during_snapshot", None)
            if callable(snapshot_context):
                with cast(ContextManager[Any], snapshot_context()):
                    api._start_in_process_backend()
            else:
                api._start_in_process_backend()
            return "in_process"

        def restore_gpu_state() -> Any:
            return api._restore_in_process_gpu_state()

        def initialize_cuda() -> dict[str, Any]:
            value = api._initialize_cuda_context()
            if isinstance(value, tuple) and len(value) == 2:
                return {"device": str(value[0]), "diagnostics": value[1]}
            return {"result": value}

        # Wrap restore-related callbacks with monotonic timers for restore accounting.
        # The _RESTORE_STAGE_TIMERS dict is accumulated here and consumed by the
        # restore() method's final _restore_timing merge.
        reload_models = _wrap_restore_stage("reload_models", reload_models)
        reload_runtime_state = _wrap_restore_stage("reload_runtime_state", reload_runtime_state)
        restore_gpu_state = _wrap_restore_stage("restore_gpu_state", restore_gpu_state)
        initialize_cuda = _wrap_restore_stage("initialize_cuda", initialize_cuda)

        def apply_sage_policy() -> Any:
            return api._apply_sage_attention_policy()

        def observe_generations() -> dict[str, str]:
            _cn_val, _cn_src = module._resolve_custom_nodes_generation(api=api)
            return {
                "runtime_state": str(getattr(api, "_runtime_generation_seen", "") or ""),
                "custom_nodes": _cn_val,
                "custom_nodes_source": _cn_src,
            }

        def read_current_custom_node_identity() -> dict[str, str]:
            """Authoritative-only current identity read via API token API."""
            result: dict[str, str] = {
                "custom_node_generation": "",
                "generation_source": "unavailable",
                "schema_version": "0",
                "deployment_combined_hash": "",
                "token": "",
            }
            try:
                # Use the module's _resolve_custom_nodes_generation with
                # API token only — no directory scan, no hash.
                cn_gen, cn_src = module._resolve_custom_nodes_generation(
                    api=api,
                    authoritative_only=True,
                )
                if cn_gen:
                    result["custom_node_generation"] = str(cn_gen)
                    result["generation_source"] = str(cn_src)
                    result["schema_version"] = "1"
                    result["deployment_combined_hash"] = _V2_DEPLOYMENT_COMBINED_HASH
                # Capture API token
                token = getattr(api, "_runtime_generation_seen", "")
                if token:
                    result["token"] = str(token)
            except Exception:
                pass
            return result

        config = self._config or BootstrapConfig(
            comfyui_root="/root/comfy/ComfyUI",
            models_path=MODELS_PATH,
            custom_nodes_path=CUSTOM_NODES_PATH,
            prescan_record_path=f"{RUNTIME_STATE_PATH}/prescan_custom_nodes.json",
            min_containers=MIN_CONTAINERS,
            scaledown_window=SCALEDOWN_WINDOW,
        )
        self.bootstrap = RuntimeBootstrap(
            config,
            reload_models=reload_models,
            reload_runtime_state=reload_runtime_state,
            sync_custom_nodes=sync_custom_nodes,
            install_requirements=install_requirements,
            start_backend=start_backend,
            restore_gpu_state=restore_gpu_state,
            initialize_cuda=initialize_cuda,
            apply_sage_policy=apply_sage_policy,
            observe_generations=observe_generations,
            read_current_custom_node_identity=read_current_custom_node_identity,
            deployment_combined_hash=_V2_DEPLOYMENT_COMBINED_HASH,
        )
        self.bootstrap._sage_baked_cuda_available = (
            getattr(api, "_sage_runtime_mode", "triton_fallback") == "baked_cuda"
        )
        self._runtime_configured = True

    def startup(self) -> dict[str, Any]:
        global _LATEST_LIFECYCLE_TIMING
        _report_host_memory("restore_start")
        _startup_perf = time.perf_counter()
        identity = _capture_remote_identity()
        self._configure_runtime()
        trace = RuntimeTrace(process="remote")
        trace.container_session_id = self.container_session_id or _V2_CONTAINER_SESSION_ID
        trace.set_metadata(**identity)
        trace.set_metadata(container_session_id=self.container_session_id or _V2_CONTAINER_SESSION_ID)
        startup_session_id = uuid.uuid4().hex
        trace.emit(
            "remote_method_entry",
            phase="lifecycle",
            metadata={
                "app_name": APP_NAME,
                "class_name": CLASS_NAME,
                "method_name": "startup",
                "snapshot": "True",
                "lifecycle_session_id": startup_session_id,
                "lifecycle_count": "1",
                "container_session_id": self.container_session_id or _V2_CONTAINER_SESSION_ID,
                **identity,
                **_resource_identity(),
            },
        )
        trace.emit(
            "gpu_invocation_submit",
            phase="lifecycle",
            metadata=_resource_identity(),
        )
        trace.emit("remote_lifecycle_start", phase="lifecycle", metadata={"snapshot": "True"})
        _fp = _snapshot_target_fingerprint()
        _spec = _MODAL_RESOURCES.get("spec", ModalRuntimeSpec())
        _gpu_str = ",".join(_spec.gpu) if _spec.gpu else "none"
        _reg_cls = globals().get("ModalRuntimeEntrypointV2", ModalRuntimeEntrypoint)
        print(
            f"[v2.snapshot_target] "
            f"static_fingerprint={_fp} "
            f"app={_spec.app_name} "
            f"class={_reg_cls.__name__} "
            f"gpu={_gpu_str} "
            f"cpu={_spec.cpu} "
            f"memory={_spec.memory}",
            flush=True,
        )
        _runtime_id = _snapshot_runtime_identity()
        print(
            f"[v2.snapshot_runtime] "
            f"image_id={_runtime_id['image_id']} "
            f"cloud={_runtime_id['cloud']} "
            f"region={_runtime_id['region']} "
            f"container_session_id={_runtime_id['container_session_id']}",
            flush=True,
        )
        _lifecycle_error: str | None = None
        try:
            state = self.bootstrap.startup(snapshot=True, trace=trace)

            # [v2.generation_identity] bootstrap diagnostic
            _boot_cn_gen = str(state.custom_node_generation or "")
            _boot_cn_short = (_boot_cn_gen[:24] + "…") if len(_boot_cn_gen) > 24 else _boot_cn_gen
            _boot_rs_gen = str(state.runtime_generation or "")
            _boot_cn_src = "missing"
            _boot_api_id = str(id(self._legacy_api))
            try:
                _boot_r, _boot_src = self._legacy_module._resolve_custom_nodes_generation(
                    api=self._legacy_api
                )
                _boot_cn_src = _boot_src
            except Exception:
                pass
            print(
                f"[v2.generation_identity] "
                f"method=startup "
                f"custom_nodes_generation={_boot_cn_short!r} "
                f"raw_empty={str(not bool(_boot_cn_gen)).lower()} "
                f"source={_boot_cn_src} "
                f"runtime_state_generation={_boot_rs_gen!r} "
                f"api_object_id={_boot_api_id} "
                f"deployment_combined_hash={_V2_DEPLOYMENT_COMBINED_HASH[:16] if _V2_DEPLOYMENT_COMBINED_HASH else '<empty>'}",
                flush=True,
            )

            # ── V2 snapshot certificate: build from RestorePlan ──
            # Reads snapshot_plan via read_current_plan(), requires nonempty
            # snapshot_plan.workflow_hash, derives repair mode from the exact
            # production execution options in the plan, gets custom_nodes_generation
            # via _get_preflight_context, computes identity via
            # _compute_v2_cert_identity, runs real api preflight then
            # execution.validate_prompt via one-shot sync coroutine helper.
            # Stores exact certificate on bootstrap state, valid true.
            snapshot_plan = None
            try:
                snapshot_plan = self._get_remote_restore_publisher().read_current_plan()
            except Exception:
                pass
            # Exact guard: if snapshot_plan has workflow_hash but no workflow,
            # the plan is corrupt and cannot build a certificate.  This guard
            # is OUTSIDE the cert try/except so RuntimeError escapes startup
            # and snapshot creation stops.
            if snapshot_plan is not None and snapshot_plan.workflow_hash and not snapshot_plan.workflow:
                raise RuntimeError("restore plan contains workflow_hash but no workflow")
            try:
                if snapshot_plan is not None and snapshot_plan.workflow_hash:
                    _sp_wf = _thaw(snapshot_plan.workflow)
                    _sp_wf_hash = snapshot_plan.workflow_hash
                    _sp_api = self._load_legacy_runtime()
                    # Derive repair_mode from the SAME _get_preflight_context
                    # helper used by _execute_v2_prompt_executor — not from
                    # plan fields (which request execution does not use).
                    _sp_repair_mode, _sp_cn_gen, _sp_cn_src = _get_preflight_context(
                        _sp_api, self._legacy_module,
                    )
                    _sp_identity, _sp_components = _compute_v2_cert_identity(
                        _sp_wf_hash,
                        repair_mode=_sp_repair_mode,
                        custom_nodes_generation=_sp_cn_gen,
                    )
                    import execution as _exec_mod

                    async def _build_startup_cert():
                        _pf_fn = getattr(_sp_api, "_preflight_before_prompt_execution", None)
                        if callable(_pf_fn):
                            await asyncio.to_thread(_pf_fn, _sp_wf if _sp_wf else {})
                        return await _exec_mod.validate_prompt(
                            f"startup-cert-{uuid.uuid4().hex[:12]}",
                            _sp_wf if _sp_wf else {},
                            None,
                        )

                    _sp_valid, _sp_error, _sp_outputs, _sp_errors = asyncio.run(
                        _build_startup_cert()
                    )
                    if (
                        _sp_valid
                        and isinstance(_sp_outputs, list)
                        and len(_sp_outputs) > 0
                        and all(isinstance(o, str) for o in _sp_outputs)
                        and len(set(_sp_outputs)) == len(_sp_outputs)
                        and isinstance(_sp_errors, dict)
                    ):
                        _sp_payload = {
                            "schema_version": _V2_CERT_SCHEMA_VERSION,
                            "identity": _sp_identity,
                            "identity_components": dict(_sp_components),
                            "cert_identity": _sp_identity,
                            "outputs_to_execute": list(_sp_outputs),
                            "node_errors": dict(_sp_errors),
                            "preflight_ok": True,
                            "runtime_generation": state.runtime_generation,
                            "custom_nodes_generation": _sp_cn_gen,
                            "cert_hash": _sp_identity[:32],
                            "deployment_combined_hash": _V2_DEPLOYMENT_COMBINED_HASH,
                            "created_at": time.time(),
                        }
                        state.set_snapshot_certificate(_sp_payload)
                        print(
                            f"[v2.cert] startup cert v2 valid=1 "
                            f"identity={_sp_identity[:16]} "
                            f"outputs={len(_sp_outputs)}",
                            flush=True,
                        )
            except Exception as _sp_exc:
                print(f"[v2.cert] startup cert build skipped: {_sp_exc}", flush=True)

            # Plan C: CPU model snapshot construction
            if _cpu_model_snapshot_enabled():
                self._lazy_init_snapshot_state()
                _cpu_snap_ok = False
                api: Any | None = None
                cpu_profile: Mapping[str, Any] | None = None
                _cpu_snapshot_perf_start = time.perf_counter()
                try:
                    api = self._load_legacy_runtime()
                    # Derive profile from the live snapshot-preload profile.
                    cpu_profile = self._cpu_snapshot_profile(api)
                    if cpu_profile is None:
                        raise RuntimeError("cpu model snapshot profile is unavailable")

                    # Build resolve_path from live folder_paths on the
                    # initialized backend.
                    import folder_paths as _fp

                    def _cpu_resolve_path(role: str, filename: str) -> str:
                        if role in ("unet",):
                            folder = "diffusion_models"
                        elif role in ("clip1", "clip2"):
                            folder = "text_encoders"
                        else:
                            folder = role
                        resolver = getattr(_fp, "get_full_path_or_raise", None)
                        if resolver is None:
                            resolver = getattr(_fp, "get_full_path", None)
                        if resolver is None:
                            raise AttributeError(
                                "folder_paths has neither get_full_path_or_raise nor get_full_path"
                            )
                        resolved = resolver(folder, filename)
                        if resolved is None:
                            raise FileNotFoundError(
                                f"cannot resolve {role} file {filename!r} in folder {folder!r}"
                            )
                        return resolved

                    # Build load_unet / load_clip callbacks from the live
                    # node classes via NODE_CLASS_MAPPINGS, using the
                    # original wrapped methods (_comfy_modal_v2_original)
                    # when available to avoid double-wrapping.
                    import nodes as _ns

                    _mappings = getattr(_ns, "NODE_CLASS_MAPPINGS", {})
                    _unet_cls = _mappings.get("UNETLoader")
                    _clip_cls = _mappings.get("CLIPLoader")
                    _dual_clip_cls = _mappings.get("DualCLIPLoader")

                    # ── Resolve target GPU(s) from configured policy ──
                    # Inside the CPU snapshot context, CUDA APIs cannot be
                    # called (Modal's snapshot builder has no GPU).  We use
                    # the configured target GPU(s) from the deployment policy
                    # to determine the effective UNET dtype, not a live probe.
                    _target_gpus = parse_gpu_request()

                    # UNET loader: returns first public output.
                    # load_cpu_snapshot_models passes (name, weight_dtype) — no device arg.
                    # Resolve original from class-level _comfy_modal_v2_original (unbound)
                    # when V2 wrappers are installed; otherwise use the bound method.
                    def _cpu_load_unet(unet_name: str, weight_dtype: str) -> Any:
                        return _load_cpu_snapshot_unet(
                            unet_name,
                            weight_dtype,
                            target_gpus=_target_gpus,
                            unet_cls=_unet_cls,
                        )

                    # CLIP loader: returns first public output.
                    # load_cpu_snapshot_models passes 3 positional args for single
                    # (clip_name, type, "default") and 4 for dual
                    # (clip_name1, clip_name2, type, "default").
                    # Resolve original from class-level _comfy_modal_v2_original (unbound)
                    # when V2 wrappers are installed; otherwise use the bound method.
                    # Inspect the original callable's signature; pass device='cpu'
                    # only when the method accepts it, otherwise omit.
                    def _cpu_load_clip(*args: Any) -> Any:
                        clip_name = args[0] if args else ""
                        is_dual = len(args) >= 4
                        if is_dual:
                            if _dual_clip_cls is None:
                                raise RuntimeError(
                                    "DualCLIPLoader class not found; "
                                    "cannot load dual clip model"
                                )
                            clip_name1, clip_name2, clip_type = args[0], args[1], args[2]
                            loader = _dual_clip_cls()
                            cls_method = _dual_clip_cls.load_clip if _dual_clip_cls else None
                            orig = getattr(cls_method, "_comfy_modal_v2_original", None)
                            if orig is not None:
                                _sig = inspect.signature(orig) if callable(orig) else None
                                if _sig is not None and 'device' in _sig.parameters:
                                    out = orig(loader, clip_name1, clip_name2, clip_type, device='cpu')
                                else:
                                    out = orig(loader, clip_name1, clip_name2, clip_type)
                            else:
                                _sig = inspect.signature(loader.load_clip) if callable(loader.load_clip) else None
                                if _sig is not None and 'device' in _sig.parameters:
                                    out = loader.load_clip(clip_name1, clip_name2, clip_type, device='cpu')
                                else:
                                    out = loader.load_clip(clip_name1, clip_name2, clip_type)
                        else:
                            clip_type = args[1]
                            loader = _clip_cls()
                            cls_method = _clip_cls.load_clip if _clip_cls else None
                            orig = getattr(cls_method, "_comfy_modal_v2_original", None)
                            if orig is not None:
                                _sig = inspect.signature(orig) if callable(orig) else None
                                if _sig is not None and 'device' in _sig.parameters:
                                    out = orig(loader, clip_name, clip_type, device='cpu')
                                else:
                                    out = orig(loader, clip_name, clip_type)
                            else:
                                _sig = inspect.signature(loader.load_clip) if callable(loader.load_clip) else None
                                if _sig is not None and 'device' in _sig.parameters:
                                    out = loader.load_clip(clip_name, clip_type, device='cpu')
                                else:
                                    out = loader.load_clip(clip_name, clip_type)
                        if isinstance(out, (tuple, list)) and len(out) > 0:
                            return out[0]
                        return out

                    # Load under CPU-only context
                    import comfy.utils as _comfy_utils

                    _cpu_models = None
                    _MISSING = object()
                    _mmap_orig = getattr(_comfy_utils, "DISABLE_MMAP", _MISSING)
                    # Require callable _force_cpu_during_snapshot — no fallback.
                    _snap_ctx = getattr(api, "_force_cpu_during_snapshot", None)
                    if not callable(_snap_ctx):
                        raise RuntimeError(
                            "api._force_cpu_during_snapshot is not available; "
                            "cannot construct CPU snapshot models"
                        )
                    try:
                        with cast(ContextManager[Any], _snap_ctx()):
                            _comfy_utils.DISABLE_MMAP = True
                            _cpu_models = load_cpu_snapshot_models(
                                cpu_profile,
                                load_unet=_cpu_load_unet,
                                load_clip=_cpu_load_clip,
                                resolve_path=_cpu_resolve_path,
                                trace=trace,
                                target_gpus=_target_gpus,
                            )
                    finally:
                        if _mmap_orig is _MISSING:
                            delattr(_comfy_utils, "DISABLE_MMAP")
                        else:
                            _comfy_utils.DISABLE_MMAP = _mmap_orig

                    # ── Emit snapshot_created runtime state (print + trace) ─
                    try:
                        _snap_state = collect_unet_runtime_state(
                            _cpu_models.unet,
                            model_management=None,
                        )
                        _unet_ident = getattr(getattr(_cpu_models, "model_key", None), "unet_identity", "")
                        # Derive requested_weight_dtype from model_spec loaders.unet
                        _req_wd_snap = "default"
                        try:
                            _snap_loaders = (_cpu_models.model_spec or {}).get("loaders", {}).get("unet", [])
                            for _sl in _snap_loaders:
                                if isinstance(_sl, Mapping) and _sl.get("unet_name") == _unet_ident:
                                    _req_wd_snap = str(_sl.get("weight_dtype", "default"))
                                    break
                        except Exception:
                            _req_wd_snap = "default"
                        # Resolve effective dtype for the runtime state record
                        _eff_dtype_snap, _eff_label_snap = resolve_unet_effective_dtype(
                            _req_wd_snap, target_gpus=_target_gpus,
                        )
                        # ── Hard correctness guard (reusable helper) ──────────
                        # After snapshot UNET construction, verify ALL floating-
                        # point parameters have the expected effective dtype and
                        # are on CPU.  Rejects stale FP32 snapshots with a clear
                        # RuntimeError — does not catch and suppress.
                        _snap_param_dist = {}
                        try:
                            _unet_module = getattr(_cpu_models.unet, "model", None)
                            if _unet_module is not None:
                                _snap_dm = getattr(_unet_module, "diffusion_model", _unet_module)
                            else:
                                _snap_dm = getattr(_cpu_models.unet, "diffusion_model", None)
                            if _snap_dm is None:
                                raise RuntimeError(
                                    "snapshot_created: diffusion model is unavailable "
                                    "for parameter dtype validation"
                                )
                            _snap_param_dist = inspect_and_validate_snapshot_params(
                                _snap_dm,
                                expected_dtype=_eff_dtype_snap,
                                require_cpu=True,
                                context="snapshot_created:",
                            )
                        except RuntimeError as _dtype_exc:
                            raise RuntimeError(
                                "CPU snapshot UNET dtype validation failed: "
                                f"requested_weight_dtype={_req_wd_snap!r} "
                                f"effective_snapshot_weight_dtype={_eff_label_snap} "
                                f"target_gpus={_target_gpus} "
                                f"parameter_distribution={_snap_param_dist} "
                                f"detail={_dtype_exc}"
                            ) from _dtype_exc
                        except Exception:
                            pass
                        # ── Derive compute / manual-cast dtype from policy, not observed state ──
                        _snap_compute_dtype = _eff_label_snap  # "bfloat16" not "torch.bfloat16"
                        _observed_manual = _snap_state.get("manual_cast_dtype", "absent")
                        # When effective weight is bf16 and target supports BF16, effective
                        # manual_cast_dtype is "none" (native). Otherwise fall back to observed.
                        from gpu_catalog import gpu_supports_bf16 as _gsb
                        _snap_primary_gpu = _target_gpus[0] if _target_gpus else ""
                        _eff_is_bf16_native = (
                            _eff_dtype_snap is not None
                            and _eff_label_snap == "bfloat16"
                            and _snap_primary_gpu
                            and _gsb(_snap_primary_gpu)
                        )
                        _snap_manual_cast_eff = "none" if _eff_is_bf16_native else _observed_manual
                        # ── Log snapshot_created state with dtype metadata ────
                        _dtype_source = "target_gpu_policy"
                        _snap_state["param_distribution"] = _snap_param_dist
                        _snap_state["effective_snapshot_compute_dtype"] = _snap_compute_dtype
                        _snap_state["effective_snapshot_manual_cast_dtype"] = _snap_manual_cast_eff
                        _state_json = __import__("json").dumps(_snap_state, default=str, separators=(",", ":"), sort_keys=True)
                        print(
                            f"[v2.unet_runtime_state] "
                            f"stage=snapshot_created "
                            f"unet_identity={_unet_ident} "
                            f"requested_weight_dtype={_req_wd_snap} "
                            f"effective_snapshot_weight_dtype={_eff_label_snap} "
                            f"effective_snapshot_compute_dtype={_snap_compute_dtype} "
                            f"effective_snapshot_manual_cast_dtype={_snap_manual_cast_eff} "
                            f"effective_weight_dtype={_eff_label_snap} "
                            f"dtype_resolution_source={_dtype_source} "
                            f"target_gpus={','.join(_target_gpus)} "
                            f"state={_state_json}",
                            flush=True,
                        )
                        trace.emit(
                            "unet_runtime_state",
                            metadata={
                                "stage": "snapshot_created",
                                "unet_identity": _unet_ident,
                                "requested_weight_dtype": _req_wd_snap,
                                "effective_snapshot_weight_dtype": _eff_label_snap,
                                "effective_snapshot_compute_dtype": _snap_compute_dtype,
                                "effective_snapshot_manual_cast_dtype": _snap_manual_cast_eff,
                                "effective_weight_dtype": _eff_label_snap,
                                "dtype_resolution_source": _dtype_source,
                                "target_gpus": list(_target_gpus),
                                "request_id": "",
                                "restored_instance_id": "",
                                "restore_session_id": "",
                                "state": _snap_state,
                            },
                        )
                    except Exception:
                        raise

                    self._cpu_snapshot_models = _cpu_models
                    self._cpu_snapshot_models_active = False
                    _cpu_snap_ok = True
                    _created_duration_ms = round((time.perf_counter() - _cpu_snapshot_perf_start) * 1000.0, 2)
                    trace.emit(
                        "cpu_snapshot_models_created",
                        phase="lifecycle",
                        metadata={
                            "status": "created",
                            "reason": "ok",
                            "model_key_hash": _cpu_models.model_key.stable_hash[:16]
                            if _cpu_models.model_key else "",
                            "clip_object_type": type(_cpu_models.clip).__name__ if _cpu_models.clip is not None else "",
                            "unet_object_type": type(_cpu_models.unet).__name__ if _cpu_models.unet is not None else "",
                            "duration_ms": _created_duration_ms,
                        },
                    )
                except BaseException as _cpu_exc:
                    self._cpu_snapshot_models = None
                    self._cpu_snapshot_models_active = False
                    _created_duration_ms = round((time.perf_counter() - _cpu_snapshot_perf_start) * 1000.0, 2)
                    trace.emit(
                        "cpu_snapshot_models_created",
                        phase="lifecycle",
                        metadata={
                            "status": "failed",
                            "reason": str(_cpu_exc)[:200],
                            "model_key_hash": "",
                            "clip_object_type": "",
                            "unet_object_type": "",
                            "duration_ms": _created_duration_ms,
                        },
                    )
                    raise

        except Exception as exc:
            _lifecycle_error = str(exc)[:200]
            trace.emit("remote_lifecycle_end", phase="lifecycle", metadata={"status": "error", "error": _lifecycle_error})
            self._remember_lifecycle_trace(trace)
            startup_total_ms = round((time.perf_counter() - _startup_perf) * 1000.0, 3)
            err_timing: dict[str, Any] = {
                "restore_total_ms": startup_total_ms,
                "restore_session_id": startup_session_id,
                "container_session_id": self.container_session_id,
                "restore_count": 1,
                "lifecycle_status": "error",
                "lifecycle_error": _lifecycle_error,
                "lifecycle_method": "startup",
            }
            self._restore_timing = err_timing
            _LATEST_LIFECYCLE_TIMING = err_timing
            raise
        trace.emit("remote_lifecycle_end", phase="lifecycle", metadata={"status": "ready"})
        self._remember_lifecycle_trace(trace)

        startup_total_ms = round((time.perf_counter() - _startup_perf) * 1000.0, 3)
        _restore_timing: dict[str, Any] = {
            "restore_total_ms": startup_total_ms,
            "restore_session_id": startup_session_id,
            "container_session_id": self.container_session_id,
            "restore_count": 1,
            "lifecycle_status": "ok",
            "lifecycle_method": "startup",
        }
        if state.stage_durations:
            for _stage, _dur_ms in state.stage_durations.items():
                if _dur_ms is not None and _dur_ms > 0:
                    _restore_timing[f"{_stage}_ms"] = round(float(_dur_ms), 3)
        self._restore_timing = _restore_timing
        _LATEST_LIFECYCLE_TIMING = _restore_timing

        _report_host_memory("restore_complete")

        # Pre-import transformers, diffusers, cache_dit in snapshot-safe mode.
        # Resolves only safe immutable metadata/classes/config validation;
        # does NOT create prompt/timestep/cache/latent/CUDA/session state.
        _cd_preimport = preimport_cachedit_family()
        if not _cd_preimport["ok"]:
            _cd_errors = "; ".join(_cd_preimport["errors"])
            raise RuntimeError(
                f"CacheDiT snapshot preimport FAILED: {_cd_errors} "
                "(image should have passed build gate)"
            )
        else:
            _cd_vers = _cd_preimport["versions"]
            _cd_paths = _cd_preimport["paths"]
            _cd_meta = _cd_preimport["cache_dit_info"]
            print(
                f"[cachedit.startup] preimport ok "
                f"transformers={_cd_vers.get('transformers', '?')} "
                f"diffusers={_cd_vers.get('diffusers', '?')} "
                f"cache_dit={_cd_vers.get('cache_dit', '?')} "
                f"cache_dit_info={_cd_meta}",
                flush=True,
            )

        print(
            f"[v2.lifecycle] method=startup snap=True "
            f"container_session={_V2_CONTAINER_SESSION_ID} "
            f"restore_total_ms={startup_total_ms} "
            f"status=ready"
        )

        return {
            "backend": state.backend,
            "status": "ready",
            "trace": trace.to_dict(),
            "_restore_timing": _restore_timing,
            "phase_durations_ms": trace.export_phase_durations(),
            "_cachedit_preimport": _cd_preimport,
        }

    def restore(self) -> dict[str, Any]:
        self._cgroup_sampler = _CgroupCpuSampler(time.monotonic_ns())
        self._cgroup_sampler.set_phase("restore")
        self._cgroup_sampler.start()
        global _LATEST_LIFECYCLE_TIMING, _LATEST_RESTORED_INSTANCE_ID, _v2_container_restore_count, _RESTORE_STAGE_TIMERS
        _report_host_memory("restore_start")
        # Reset per-request counter so first request after every fresh restore
        # is exactly 1.  Snapshotted state cannot carry request count.
        self._request_count = 0
        # Reset process-global restore-stage timers at entry to prevent
        # stale accumulation across restores.  Each restore gets its own
        # timing state.
        _RESTORE_STAGE_TIMERS.clear()
        _RESTORE_STAGE_TIMERS["snapshot_identity_checks"] = 0.0
        _RESTORE_STAGE_TIMERS["cpu_snapshot_retargeting"] = 0.0
        # â”€â”€ Remote resume / restore method boundary timestamps â”€â”€â”€â”€â”€â”€â”€â”€
        remote_python_resume_wall_ns: int = int(time.time() * 1_000_000_000)
        remote_python_resume_mono_ns: int = time.monotonic_ns()
        restore_method_start_wall_ns: int = remote_python_resume_wall_ns
        restore_method_start_mono_ns: int = remote_python_resume_mono_ns
        _restore_status: str = "unknown"
        _restore_end_wall_ns: int | None = None
        _restore_end_mono_ns: int | None = None
        _restore_perf_start = time.perf_counter()
        try:
            identity = _capture_remote_identity()
            self._configure_runtime()
            trace = RuntimeTrace(process="remote")
            trace.container_session_id = self.container_session_id or _V2_CONTAINER_SESSION_ID
            trace.set_metadata(**identity)
            trace.set_metadata(container_session_id=self.container_session_id or _V2_CONTAINER_SESSION_ID)
            _v2_container_restore_count += 1
            self._restore_count = _v2_container_restore_count
            restore_session_id = uuid.uuid4().hex
            # â”€â”€ V2 restore correlation identity â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
            restored_instance_id = uuid.uuid4().hex
            self._restored_instance_id = restored_instance_id
            _LATEST_RESTORED_INSTANCE_ID = restored_instance_id
            set_model_load_identity(restored_instance_id, restore_session_id)
            # Legacy identity: rename old container_session_id internally
            legacy_container_session_id = self.container_session_id or _V2_CONTAINER_SESSION_ID
            trace.set_metadata(
                trace_id=trace.trace_id,
                restored_instance_id=restored_instance_id,
                restore_session_id=restore_session_id,
                legacy_container_session_id=legacy_container_session_id,
                **_resource_identity(),
            )
            trace.emit(
                "remote_method_entry",
                phase="lifecycle",
                metadata={
                    "app_name": APP_NAME,
                    "class_name": CLASS_NAME,
                    "method_name": "restore",
                    "snapshot": "False",
                    "restore_session_id": restore_session_id,
                    "restored_instance_id": restored_instance_id,
                    "legacy_container_session_id": legacy_container_session_id,
                    "restore_count": str(self._restore_count),
                    "container_session_id": self.container_session_id or _V2_CONTAINER_SESSION_ID,
                    **identity,
                    **_resource_identity(),
                },
            )
            trace.emit(
                "gpu_invocation_submit",
                phase="restore",
                metadata=_resource_identity(),
            )
            trace.emit("remote_lifecycle_start", phase="restore", metadata={"snapshot": "False"})
            trace.emit("restore_plan_read_start", phase="restore")
            try:
                self._restore_plan = self._get_remote_restore_publisher().read_current_plan()
                trace.emit(
                    "restore_plan_read_end",
                    phase="restore",
                    metadata={
                        "status": "found" if self._restore_plan else "absent",
                        "generation": str(self._restore_plan.generation if self._restore_plan else ""),
                    },
                )
            except Exception as exc:
                trace.emit(
                    "restore_plan_read_end",
                    phase="restore",
                    metadata={"status": "error", "error": str(exc)[:200]},
                )
            _lifecycle_error: str | None = None
            try:
                # Clear process-local caches from previous restore cycle
                _RES4LYF_PREPARED.clear()
                _CACHEDIT_PREPARED.clear()
                trace.emit("v2_bootstrap_restore_start", phase="restore")
                state = self.bootstrap.restore(trace=trace)
                trace.emit("v2_bootstrap_restore_end", phase="restore")

                # [v2.generation_identity] bootstrap diagnostic
                _boot_cn_gen = str(state.custom_node_generation or "")
                _boot_cn_short = (_boot_cn_gen[:24] + "…") if len(_boot_cn_gen) > 24 else _boot_cn_gen
                _boot_rs_gen = str(state.runtime_generation or "")
                _boot_cn_src = "missing"
                _boot_api_id = str(id(self._legacy_api))
                try:
                    _boot_r, _boot_src = self._legacy_module._resolve_custom_nodes_generation(
                        api=self._legacy_api
                    )
                    _boot_cn_src = _boot_src
                except Exception:
                    pass
                print(
                    f"[v2.generation_identity] "
                    f"method=restore "
                    f"custom_nodes_generation={_boot_cn_short!r} "
                    f"raw_empty={str(not bool(_boot_cn_gen)).lower()} "
                    f"source={_boot_cn_src} "
                    f"runtime_state_generation={_boot_rs_gen!r} "
                    f"api_object_id={_boot_api_id} "
                    f"deployment_combined_hash={_V2_DEPLOYMENT_COMBINED_HASH[:16] if _V2_DEPLOYMENT_COMBINED_HASH else '<empty>'}",
                    flush=True,
                )
            except Exception as exc:
                _lifecycle_error = str(exc)[:200]
                trace.emit("v2_bootstrap_restore_end", phase="restore", metadata={"status": "error", "error": _lifecycle_error})
                trace.emit("remote_lifecycle_end", phase="restore", metadata={"status": "error", "error": _lifecycle_error})
                self._remember_lifecycle_trace(trace)
                restore_total_ms = round((time.perf_counter() - _restore_perf_start) * 1000.0, 3)
                # Capture end timestamps BEFORE constructing err_timing
                _restore_status = "error"
                _restore_end_wall_ns = int(time.time() * 1_000_000_000)
                _restore_end_mono_ns = time.monotonic_ns()
                err_timing: dict[str, Any] = {
                    "restore_total_ms": restore_total_ms,
                    "restore_session_id": restore_session_id,
                    "restored_instance_id": restored_instance_id,
                    "container_session_id": self.container_session_id,
                    "restore_count": self._restore_count,
                    "lifecycle_status": "error",
                    "lifecycle_error": _lifecycle_error,
                    "lifecycle_method": "restore",
                    "remote_python_resume_wall_unix_ns": remote_python_resume_wall_ns,
                    "remote_python_resume_mono_ns": remote_python_resume_mono_ns,
                    "restore_method_start_wall_unix_ns": restore_method_start_wall_ns,
                    "restore_method_start_mono_ns": restore_method_start_mono_ns,
                    "restore_method_end_wall_unix_ns": _restore_end_wall_ns,
                    "restore_method_end_mono_ns": _restore_end_mono_ns,
                    "restore_method_status": "error",
                }
                self._restore_timing = err_timing
                _LATEST_LIFECYCLE_TIMING = err_timing
                print(
                    f"[v2.lifecycle] method=restore snap=False "
                    f"container_session={_V2_CONTAINER_SESSION_ID} "
                    f"restore_count={self._restore_count} "
                    f"restore_total_ms={restore_total_ms} "
                    f"remote_python_resume_wall_unix_ns={remote_python_resume_wall_ns} "
                    f"restore_method_start_wall_unix_ns={restore_method_start_wall_ns} "
                    f"restore_method_end_wall_unix_ns={_restore_end_wall_ns} "
                    f"modal_method_entry_wall_unix_ns={self._fmt_or_absent(None)} "
                    f"restore_status={_restore_status} "
                    f"restore_method_status={_restore_status} "
                    f"status=error",
                    flush=True,
                )
                raise
        except:
            # Method-level guard: captures end timestamps for exceptions that
            # escape before the preload/finalize try block (e.g. identity
            # capture, configuration, trace setup, plan read, bootstrap).
            # The bootstrap error handler already sets _restore_end_wall_ns
            # etc., so this except only fires for truly early failures.
            if _restore_end_wall_ns is None:
                _restore_end_wall_ns = int(time.time() * 1_000_000_000)
                _restore_end_mono_ns = time.monotonic_ns()
                if _restore_status not in ("success", "error"):
                    _restore_status = "error"
                print(
                    f"[v2.lifecycle] method=restore snap=False "
                    f"container_session={_V2_CONTAINER_SESSION_ID} "
                    f"restore_count={getattr(self, '_restore_count', 0)} "
                    f"restore_total_ms={round((time.perf_counter() - _restore_perf_start) * 1000.0, 3)} "
                    f"remote_python_resume_wall_unix_ns={remote_python_resume_wall_ns} "
                    f"restore_method_start_wall_unix_ns={restore_method_start_wall_ns} "
                    f"restore_method_end_wall_unix_ns={_restore_end_wall_ns} "
                    f"modal_method_entry_wall_unix_ns={self._fmt_or_absent(None)} "
                    f"restore_status={_restore_status} "
                    f"restore_method_status={_restore_status} "
                    f"status=error",
                    flush=True,
                )
                if self._restore_timing is None:
                    self._restore_timing = {
                        "restore_total_ms": round((time.perf_counter() - _restore_perf_start) * 1000.0, 3),
                        "restore_session_id": "",
                        "restored_instance_id": "",
                        "container_session_id": getattr(self, "container_session_id", ""),
                        "restore_count": getattr(self, "_restore_count", 0),
                        "lifecycle_status": "error",
                        "lifecycle_error": "unhandled_restore_error",
                        "lifecycle_method": "restore",
                        "remote_python_resume_wall_unix_ns": remote_python_resume_wall_ns,
                        "remote_python_resume_mono_ns": remote_python_resume_mono_ns,
                        "restore_method_start_wall_unix_ns": restore_method_start_wall_ns,
                        "restore_method_start_mono_ns": restore_method_start_mono_ns,
                        "restore_method_end_wall_unix_ns": _restore_end_wall_ns,
                        "restore_method_end_mono_ns": _restore_end_mono_ns,
                        "restore_method_status": "error",
                    }
                    _LATEST_LIFECYCLE_TIMING = self._restore_timing
                elif self._restore_timing is not None:
                    # Bootstrap error path may have set _restore_timing without raw end fields;
                    # backfill them now from the captured _restore_end_* locals.
                    _rt = self._restore_timing
                    if _rt.get("restore_method_end_wall_unix_ns") is None:
                        _rt["restore_method_end_wall_unix_ns"] = _restore_end_wall_ns
                    if _rt.get("restore_method_end_mono_ns") is None:
                        _rt["restore_method_end_mono_ns"] = _restore_end_mono_ns
                    if _rt.get("restore_method_status") is None:
                        _rt["restore_method_status"] = "error"
                    if _rt.get("remote_python_resume_wall_unix_ns") is None:
                        _rt["remote_python_resume_wall_unix_ns"] = remote_python_resume_wall_ns
                    if _rt.get("remote_python_resume_mono_ns") is None:
                        _rt["remote_python_resume_mono_ns"] = remote_python_resume_mono_ns
                    if _rt.get("restore_method_start_wall_unix_ns") is None:
                        _rt["restore_method_start_wall_unix_ns"] = restore_method_start_wall_ns
                    if _rt.get("restore_method_start_mono_ns") is None:
                        _rt["restore_method_start_mono_ns"] = restore_method_start_mono_ns
                    _LATEST_LIFECYCLE_TIMING = _rt
            raise
        # Plan C: CPU snapshot model activation (Variant C)
        # Compatibility-first flow: compare plan request key/spec to stored
        # models key/spec using non-VAE/projected matchers.  On mismatch the
        # bridge is cleared and the existing fallback handles preload.
        # On match, models validate against their own identity (file facts,
        # object shapes, tensor safety) before retarget and activation.
        # Success preserves existing [v2.cpu_snapshot] status=hit output
        # and skips bridge.prepare/background UNET submission.
        _cpu_snapshot_activated: bool = False
        self._lazy_init_snapshot_state()
        if (
            _cpu_model_snapshot_enabled()
            and self._cpu_snapshot_models is not None
            and self._restore_plan is not None
        ):
            _cpu_snapshot_activate_error: str | None = None
            _activation_perf_start = time.perf_counter()
            _activation_duration_ms = 0.0
            models = self._cpu_snapshot_models
            if models is None:
                raise RuntimeError("cpu snapshot models disappeared before activation")
            # Pre-compute hashes for diagnostics (used in except block).
            _snapshot_key_hash: str = models.model_key.stable_hash[:16] if models.model_key else ""
            _snapshot_spec_hash: str = stable_hash(models.model_spec)[:16] if models.model_spec else ""
            _request_key_hash: str = ""
            _request_spec_hash: str = ""
            try:
                import folder_paths as _fp_restore

                def _validate_resolve_path(role: str, filename: str) -> str:
                    # Map unet -> diffusion_models (the live category used by
                    # nodes.py), clip1/clip2 -> text_encoders.
                    if role == "unet":
                        folder = "diffusion_models"
                    else:
                        folder = "text_encoders"
                    resolver = getattr(_fp_restore, "get_full_path_or_raise", None)
                    if resolver is None:
                        resolver = getattr(_fp_restore, "get_full_path", None)
                    if resolver is None:
                        raise AttributeError(
                            "folder_paths has neither get_full_path_or_raise nor get_full_path"
                        )
                    resolved = resolver(folder, filename)
                    if resolved is None:
                        raise FileNotFoundError(
                            f"validate: cannot resolve {role} file {filename!r}"
                        )
                    return resolved

                plan = self._restore_plan

                # Step 1: Compatibility check using non-VAE key matcher
                #          + projected spec matcher (no canonical role identity).
                _identity_check_start_ns = time.monotonic_ns()
                _keys_match = _cpu_snapshot_model_keys_match(plan.model_key, models.model_key)
                _specs_match = _cpu_snapshot_specs_match(plan.model_spec, models.model_spec)
                _key_reason = _cpu_snapshot_key_mismatch_reason(plan.model_key, models.model_key) if not _keys_match else None
                _spec_reason = _cpu_snapshot_spec_mismatch_reason(plan.model_spec, models.model_spec) if not _specs_match else None
                _RESTORE_STAGE_TIMERS["snapshot_identity_checks"] = round(
                    (time.monotonic_ns() - _identity_check_start_ns) / 1_000_000, 3
                )
                _request_key_hash = stable_hash(plan.model_key.to_dict())[:16] if plan.model_key else ""
                _request_spec_hash = stable_hash(models.model_spec)[:16] if models.model_spec else ""
                print(
                    f"[v2.cpu_snapshot_match] "
                    f"keys_match={int(_keys_match)} specs_match={int(_specs_match)} "
                    f"key_reason={_key_reason or 'ok'} "
                    f"spec_reason={_spec_reason or 'ok'} "
                    f"snapshot_key_hash={_snapshot_key_hash} "
                    f"request_key_hash={_request_key_hash} "
                    f"snapshot_spec_hash={_snapshot_spec_hash} "
                    f"request_spec_hash={_request_spec_hash}",
                    flush=True,
                )

                if not (_keys_match and _specs_match):
                    # Incompatible: clear bridge and fall through to existing
                    # preload branch exactly as before.
                    self._preload_bridge.clear()
                    self._cpu_snapshot_models_active = False
                    self._cpu_snapshot_unet_runtime_state = None
                    _cpu_snapshot_activated = False
                    _role_reason = "; ".join(
                        p for p in [
                            f"key:{_key_reason}" if _key_reason else "",
                            f"spec:{_spec_reason}" if _spec_reason else "",
                        ] if p
                    ) or "compatibility mismatch"
                    _cpu_snapshot_activate_error = _role_reason
                    _activation_duration_ms = round(
                        (time.perf_counter() - _activation_perf_start) * 1000.0,
                        3,
                    )
                    trace.emit(
                        "cpu_snapshot_models_activated",
                        phase="restore",
                        metadata={
                            "status": "failed",
                            "reason": _cpu_snapshot_activate_error[:60],
                            "model_key_hash": _snapshot_key_hash,
                            "clip_object_type": type(models.clip).__name__
                            if models.clip is not None else "",
                            "unet_object_type": type(models.unet).__name__
                            if models.unet is not None else "",
                            "duration_ms": _activation_duration_ms,
                            "keys_match": int(_keys_match),
                            "specs_match": int(_specs_match),
                        },
                    )
                    _bridge_installed = 1 if self._preload_bridge._original_methods else 0
                    _c_prep = self._preload_bridge._preparation
                    _c_clip_ready = 1 if _c_prep is not None and _c_prep.clip_future is not None and _c_prep.clip_future.done() else 0
                    _c_unet_ready = 1 if _c_prep is not None and _c_prep.unet_future is not None and _c_prep.unet_future.done() else 0
                    print(
                        f"[v2.cpu_snapshot] status=miss reason={_cpu_snapshot_activate_error[:60]} "
                        f"bridge_installed={_bridge_installed} "
                        f"clip_ready={_c_clip_ready} unet_ready={_c_unet_ready}",
                        flush=True,
                    )
                else:
                    # Step 2: Full validation against models' own key/spec
                    _valid, _reason = validate_cpu_snapshot_models(
                        models,
                        expected_key=models.model_key,
                        expected_spec=models.model_spec,
                        resolve_path=_validate_resolve_path,
                    )
                    if not _valid:
                        raise RuntimeError(
                            f"snapshot activation validation failed: {_reason}"
                        )

                    # Retarget devices through live model_management.
                    import comfy.model_management as _mm
                    _unet_ident = getattr(getattr(models, "model_key", None), "unet_identity", "")

                    # ── Emit pre-retarget state (print + trace) ──────────
                    _pre_retarget_state: dict[str, Any] = {}
                    try:
                        _pre_retarget_state = collect_unet_runtime_state(
                            models.unet, model_management=_mm,
                        )
                        # Derive requested_weight_dtype from plan.model_spec
                        _req_wd_pre = "default"
                        try:
                            _plan_unet = (plan.model_spec or {}).get("loaders", {}).get("unet", [])
                            _plan_uid = getattr(getattr(plan, "model_key", None), "unet_identity", "")
                            for _pl in _plan_unet:
                                if isinstance(_pl, Mapping) and _pl.get("unet_name") == _plan_uid:
                                    _req_wd_pre = str(_pl.get("weight_dtype", "default"))
                                    break
                        except Exception:
                            _req_wd_pre = "default"
                        _pre_expected_dtype, _pre_effective_label = resolve_unet_effective_dtype(
                            _req_wd_pre, target_gpus=parse_gpu_request(),
                        )
                        _pre_model = getattr(models.unet, "model", None)
                        _pre_dm = (
                            getattr(_pre_model, "diffusion_model", _pre_model)
                            if _pre_model is not None
                            else getattr(models.unet, "diffusion_model", None)
                        )
                        if _pre_dm is None:
                            raise RuntimeError(
                                "restore: diffusion model is unavailable for "
                                "snapshot parameter validation"
                            )
                        try:
                            _pre_param_dist = inspect_and_validate_snapshot_params(
                                _pre_dm,
                                expected_dtype=_pre_expected_dtype,
                                require_cpu=True,
                                context="restore:",
                            )
                        except RuntimeError as _dtype_exc:
                            raise RuntimeError(
                                "Restore-time UNET dtype validation failed: "
                                f"requested_weight_dtype={_req_wd_pre!r} "
                                f"effective_snapshot_weight_dtype={_pre_effective_label} "
                                f"target_gpus={parse_gpu_request()} "
                                f"detail={_dtype_exc}"
                            ) from _dtype_exc
                        _pre_retarget_state["param_distribution"] = _pre_param_dist
                        _pre_retarget_state["effective_snapshot_weight_dtype"] = _pre_effective_label
                        _pre_retarget_state["effective_weight_dtype"] = _pre_effective_label
                        _pre_retarget_state["dtype_resolution_source"] = "target_gpu_policy"
                        _pre_retarget_state["target_gpus"] = list(parse_gpu_request())
                        # ── Effective labels from policy, not serialized dtype ─
                        _pre_compute_dtype = _pre_effective_label  # "bfloat16" not "torch.bfloat16"
                        _pre_manual_cast_eff = (
                            "none" if _pre_effective_label == "bfloat16" and _pre_expected_dtype is not None
                            else _pre_retarget_state.get("manual_cast_dtype", "absent")
                        )
                        _pre_retarget_state["effective_snapshot_compute_dtype"] = _pre_compute_dtype
                        _pre_retarget_state["effective_snapshot_manual_cast_dtype"] = _pre_manual_cast_eff
                        _state_json_pre = __import__("json").dumps(
                            _pre_retarget_state, default=str, separators=(",", ":"), sort_keys=True,
                        )
                        print(
                            f"[v2.unet_runtime_state] "
                            f"stage=snapshot_restored_pre_retarget "
                            f"unet_identity={_unet_ident} "
                            f"requested_weight_dtype={_req_wd_pre} "
                            f"effective_snapshot_weight_dtype={_pre_effective_label} "
                            f"effective_snapshot_compute_dtype={_pre_compute_dtype} "
                            f"effective_snapshot_manual_cast_dtype={_pre_manual_cast_eff} "
                            f"effective_weight_dtype={_pre_effective_label} "
                            f"dtype_resolution_source=target_gpu_policy "
                            f"target_gpus={','.join(parse_gpu_request())} "
                            f"restored_instance_id={restored_instance_id} "
                            f"restore_session_id={restore_session_id} "
                            f"state={_state_json_pre}",
                            flush=True,
                        )
                        trace.emit(
                            "unet_runtime_state",
                            metadata={
                                "stage": "snapshot_restored_pre_retarget",
                                "unet_identity": _unet_ident,
                                "requested_weight_dtype": _req_wd_pre,
                                "effective_snapshot_weight_dtype": _pre_effective_label,
                                "effective_snapshot_compute_dtype": _pre_compute_dtype,
                                "effective_snapshot_manual_cast_dtype": _pre_manual_cast_eff,
                                "effective_weight_dtype": _pre_effective_label,
                                "dtype_resolution_source": "target_gpu_policy",
                                "target_gpus": list(parse_gpu_request()),
                                "request_id": str(trace.request_id if trace else ""),
                                "restored_instance_id": restored_instance_id,
                                "restore_session_id": restore_session_id,
                                "state": _pre_retarget_state,
                            },
                        )
                    except Exception:
                        raise

                    retarget_ok, retarget_reason = retarget_cpu_snapshot_models(
                        models, model_management=_mm,
                    )
                    if not retarget_ok:
                        raise RuntimeError(f"retarget failed: {retarget_reason}")

                    # ── Emit post-retarget state (print + trace) ──────────
                    _post_retarget_state: dict[str, Any] = {}
                    _req_wd_post = "default"
                    try:
                        _post_retarget_state = collect_unet_runtime_state(
                            models.unet, model_management=_mm,
                        )
                        # Derive requested_weight_dtype from plan.model_spec
                        try:
                            _plan_unet_post = (plan.model_spec or {}).get("loaders", {}).get("unet", [])
                            _plan_uid_post = getattr(getattr(plan, "model_key", None), "unet_identity", "")
                            for _pl in _plan_unet_post:
                                if isinstance(_pl, Mapping) and _pl.get("unet_name") == _plan_uid_post:
                                    _req_wd_post = str(_pl.get("weight_dtype", "default"))
                                    break
                        except Exception:
                            _req_wd_post = "default"
                        _post_expected_dtype, _post_effective_label = resolve_unet_effective_dtype(
                            _req_wd_post, target_gpus=parse_gpu_request(),
                        )
                        _post_model = getattr(models.unet, "model", None)
                        _post_dm = (
                            getattr(_post_model, "diffusion_model", _post_model)
                            if _post_model is not None
                            else getattr(models.unet, "diffusion_model", None)
                        )
                        if _post_dm is None:
                            raise RuntimeError(
                                "restore: diffusion model is unavailable for "
                                "post-retarget parameter validation"
                            )
                        try:
                            _post_param_dist = inspect_and_validate_snapshot_params(
                                _post_dm,
                                expected_dtype=_post_expected_dtype,
                                require_cpu=False,
                                context="restore:",
                            )
                        except RuntimeError as _dtype_exc:
                            raise RuntimeError(
                                "Restore-time post-retarget UNET dtype validation failed: "
                                f"requested_weight_dtype={_req_wd_post!r} "
                                f"effective_snapshot_weight_dtype={_post_effective_label} "
                                f"target_gpus={parse_gpu_request()} "
                                f"detail={_dtype_exc}"
                            ) from _dtype_exc
                        _post_retarget_state["param_distribution"] = _post_param_dist
                        _post_retarget_state["effective_snapshot_weight_dtype"] = _post_effective_label
                        _post_retarget_state["effective_weight_dtype"] = _post_effective_label
                        _post_retarget_state["dtype_resolution_source"] = "target_gpu_policy"
                        _post_retarget_state["target_gpus"] = list(parse_gpu_request())
                        # ── Effective labels from policy, not serialized dtype ─
                        _post_compute_dtype = _post_effective_label
                        _post_manual_cast_eff = (
                            "none" if _post_effective_label == "bfloat16" and _post_expected_dtype is not None
                            else _post_retarget_state.get("manual_cast_dtype", "absent")
                        )
                        _post_retarget_state["effective_snapshot_compute_dtype"] = _post_compute_dtype
                        _post_retarget_state["effective_snapshot_manual_cast_dtype"] = _post_manual_cast_eff
                        _state_json_post = __import__("json").dumps(
                            _post_retarget_state, default=str, separators=(",", ":"), sort_keys=True,
                        )
                        print(
                            f"[v2.unet_runtime_state] "
                            f"stage=snapshot_restored_post_retarget "
                            f"unet_identity={_unet_ident} "
                            f"requested_weight_dtype={_req_wd_post} "
                            f"effective_snapshot_weight_dtype={_post_effective_label} "
                            f"effective_snapshot_compute_dtype={_post_compute_dtype} "
                            f"effective_snapshot_manual_cast_dtype={_post_manual_cast_eff} "
                            f"effective_weight_dtype={_post_effective_label} "
                            f"dtype_resolution_source=target_gpu_policy "
                            f"target_gpus={','.join(parse_gpu_request())} "
                            f"restored_instance_id={restored_instance_id} "
                            f"restore_session_id={restore_session_id} "
                            f"state={_state_json_post}",
                            flush=True,
                        )
                        trace.emit(
                            "unet_runtime_state",
                            metadata={
                                "stage": "snapshot_restored_post_retarget",
                                "unet_identity": _unet_ident,
                                "requested_weight_dtype": _req_wd_post,
                                "effective_snapshot_weight_dtype": _post_effective_label,
                                "effective_snapshot_compute_dtype": _post_compute_dtype,
                                "effective_snapshot_manual_cast_dtype": _post_manual_cast_eff,
                                "effective_weight_dtype": _post_effective_label,
                                "dtype_resolution_source": "target_gpu_policy",
                                "target_gpus": list(parse_gpu_request()),
                                "request_id": str(trace.request_id if trace else ""),
                                "restored_instance_id": restored_instance_id,
                                "restore_session_id": restore_session_id,
                                "state": _post_retarget_state,
                            },
                        )
                    except Exception:
                        raise

                    # Stash post-retarget state for request-trace propagation.
                    try:
                        self._cpu_snapshot_unet_runtime_state = copy.deepcopy({
                            "stage": "snapshot_restored_post_retarget",
                            "unet_identity": _unet_ident,
                            "requested_weight_dtype": _req_wd_post,
                            "effective_snapshot_weight_dtype": _post_effective_label,
                            "effective_snapshot_compute_dtype": _post_compute_dtype,
                            "effective_snapshot_manual_cast_dtype": _post_manual_cast_eff,
                            "effective_weight_dtype": _post_effective_label,
                            "dtype_resolution_source": "target_gpu_policy",
                            "target_gpus": list(parse_gpu_request()),
                            "restored_instance_id": restored_instance_id,
                            "restore_session_id": restore_session_id,
                            "state": _post_retarget_state,
                        })
                    except Exception:
                        pass

                    # ── BF16-native validation before bridge publication ──
                    # Uses models.compute_policy (not plan.model_spec) since
                    # compute_policy is stored separately from model_spec.
                    if models.compute_policy == _COMPUTE_POLICY_BF16_NATIVE:
                        validate_snapshot_unet_bf16_native(
                            models.unet,
                            context="restore_pre_bridge.",
                            target_gpus=parse_gpu_request(),
                            requested_weight_dtype=_req_wd_post,
                            effective_weight_dtype=_post_effective_label,
                            effective_compute_dtype=_post_effective_label,
                        )

                    # Activate on the bridge.
                    _retarget_start_ns = time.monotonic_ns()
                    self._use_cpu_snapshot_models_on_bridge(
                        plan.model_key,
                        plan.prefill_key,
                        plan.model_spec,
                        models.unet,
                        models.clip,
                        trace=trace,
                    )
                    _RESTORE_STAGE_TIMERS["cpu_snapshot_retargeting"] = round(
                        (time.monotonic_ns() - _retarget_start_ns) / 1_000_000, 3
                    )
                    self._cpu_snapshot_models_active = True
                    _cpu_snapshot_activated = True
                    state.snapshot_loader_outputs = {
                        "unet": models.unet,
                        "clip": models.clip,
                    }
                    state.snapshot_model_identities = {
                        "unet": str(getattr(plan.model_key, "unet_identity", "") or ""),
                        "clip": str(getattr(plan.model_key, "clip_identity", "") or ""),
                    }
                    register_unet_forward_probe(models.unet, source="cpu_snapshot")
                    # Explicitly install SAMPLER_SAMPLE timing wrapper on the
                    # restored snapshot UNET, even though register_unet_forward_probe
                    # also calls ensure_sampling_timing_wrapper internally.
                    # This redundancy ensures the wrapper is installed regardless
                    # of which code path activates the UNET.
                    from comfymodal_runtime.runtime_executor import ensure_sampling_timing_wrapper
                    ensure_sampling_timing_wrapper(models.unet)
                    install_registered_unet_forward_hooks()
                    # CacheDiT restore preparation: locate exactly one
                    # CacheDiT_Model_Optimizer node from snapshot plan.workflow,
                    # pass ONLY its node inputs (helper removes 'model'), consume
                    # patched_model and replace all UNET references.
                    _cd_restore_node_ids: list[str] = []
                    _cd_restore_inputs: dict[str, Any] = {}
                    try:
                        _plan_wf = _thaw(getattr(plan, "workflow", {}))
                        for _nid, _node in _plan_wf.items():
                            if isinstance(_node, Mapping) and _node.get("class_type") == "CacheDiT_Model_Optimizer":
                                _cd_restore_node_ids.append(str(_nid))
                        # Require exactly one CacheDiT_Model_Optimizer node
                        if len(_cd_restore_node_ids) == 1:
                            _cd_restore_node_id = _cd_restore_node_ids[0]
                            _cd_restore_inputs = dict(
                                _plan_wf.get(_cd_restore_node_id, {}).get("inputs", {})
                            )
                            _cd_result = state._restore_cachedit_prepare(
                                unet=models.unet,
                                workflow_inputs=_cd_restore_inputs,
                                workflow_hash=str(getattr(plan, "workflow_hash", "")),
                            )
                            if _cd_result.get("ok"):
                                _patched_model = _cd_result.get("patched_model")
                                if _patched_model is not None:
                                    # Replace all UNET references with patched model
                                    state.snapshot_loader_outputs["unet"] = _patched_model
                                    self._cpu_snapshot_models.unet = _patched_model
                                    # Re-activate the bridge with patched UNET
                                    self._use_cpu_snapshot_models_on_bridge(
                                        plan.model_key,
                                        plan.prefill_key,
                                        plan.model_spec,
                                        _patched_model,
                                        models.clip,
                                        trace=trace,
                                    )
                                    # Re-register forward probe after replacement
                                    register_unet_forward_probe(_patched_model, source="cachedit_restore")
                                    # Also explicitly install timing wrapper on the
                                    # CacheDiT-patched model.
                                    from comfymodal_runtime.runtime_executor import ensure_sampling_timing_wrapper
                                    ensure_sampling_timing_wrapper(_patched_model)
                                _CACHEDIT_PREPARED[str(getattr(plan, "workflow_hash", ""))] = {
                                    "unet_id": id(_patched_model) if _patched_model is not None else id(models.unet),
                                    "workflow_hash": str(getattr(plan, "workflow_hash", "")),
                                    "cache_dit_inputs": _cd_restore_inputs,
                                }
                                if _patched_model is not None:
                                    print(
                                        f"[v2.cachedit_restore] decision=prepared "
                                        f"node_id={_cd_restore_node_id} "
                                        f"unet_match=1",
                                        flush=True,
                                    )
                    except Exception as _cd_exc:
                        print(f"[v2.cachedit_restore] error={_cd_exc}", flush=True)
                    # RES4LYF restore preparation
                    try:
                        _sampler_nodes_r4 = [
                            {"node_id": str(nid), "inputs": dict(node.get("inputs", {}))}
                            for nid, node in getattr(plan, "workflow", {}).items()
                            if isinstance(node, Mapping)
                            and node.get("class_type") == "ClownsharKSampler_Beta"
                        ]
                        _r4_result = state._restore_res4lyf_prepare(
                            sampler_node_inputs=_sampler_nodes_r4,
                        )
                        if _r4_result.get("ok"):
                            _installed = _install_res4lyf_parser_hook()
                            _prepared_records = []
                            for _record in _r4_result.get("prepared_records", ()):
                                _parser = _record.get("parser")
                                if _parser is None:
                                    continue
                                _prepared_records.append(MappingProxyType({
                                    "node_id": str(_record.get("node_id", "")),
                                    "raw_options": str(_record.get("raw_extra_options", "")).strip(),
                                    "parser_state": MappingProxyType(dict(_parser.__dict__)),
                                }))
                            if _installed and _prepared_records:
                                _wf_hash_key = str(getattr(plan, "workflow_hash", ""))
                                _RES4LYF_PREPARED[_wf_hash_key] = {
                                    "records": tuple(_prepared_records),
                                }
                                _r4_node_ids = ",".join(
                                    str(record["node_id"]) for record in _prepared_records
                                )
                                print(
                                    f"[v2.res4lyf_restore] decision=prepared "
                                    f"node_id={_r4_node_ids} "
                                    f"hook_installed={int(_RES4LYF_HOOK_INSTALLED)}",
                                    flush=True,
                                )
                        else:
                            _reason = _r4_result.get("reason", "unknown")
                            print(
                                f"[v2.res4lyf_restore] ok=0 reason={_reason}",
                                flush=True,
                            )
                    except Exception as _r4_exc:
                        print(f"[v2.res4lyf_restore] error={_r4_exc}", flush=True)
                    _activation_duration_ms = round(
                        (time.perf_counter() - _activation_perf_start) * 1000.0,
                        3,
                    )
                    trace.emit(
                        "cpu_snapshot_models_activated",
                        phase="restore",
                        metadata={
                            "status": "activated",
                            "reason": "ok",
                            "model_key_hash": _snapshot_key_hash,
                            "clip_object_type": type(models.clip).__name__ if models.clip is not None else "",
                            "unet_object_type": type(models.unet).__name__ if models.unet is not None else "",
                            "duration_ms": _activation_duration_ms,
                            "keys_match": int(_keys_match),
                            "specs_match": int(_specs_match),
                        },
                    )
                    _bridge_installed = 1 if self._preload_bridge._original_methods else 0
                    _c_prep = self._preload_bridge._preparation
                    _c_clip_ready = 1 if _c_prep is not None and _c_prep.clip_future is not None and _c_prep.clip_future.done() else 0
                    _c_unet_ready = 1 if _c_prep is not None and _c_prep.unet_future is not None and _c_prep.unet_future.done() else 0
                    print(
                        f"[v2.cpu_snapshot] status=hit reason=ok "
                        f"bridge_installed={_bridge_installed} "
                        f"clip_ready={_c_clip_ready} unet_ready={_c_unet_ready}",
                        flush=True,
                    )
            except Exception as _act_exc:
                self._preload_bridge.clear()
                self._cpu_snapshot_models_active = False
                self._cpu_snapshot_unet_runtime_state = None
                _cpu_snapshot_activated = False
                _cpu_snapshot_activate_error = str(_act_exc)[:80]
                _activation_duration_ms = round(
                    (time.perf_counter() - _activation_perf_start) * 1000.0,
                    3,
                )
                trace.emit(
                    "cpu_snapshot_models_activated",
                    phase="restore",
                    metadata={
                        "status": "failed",
                        "reason": _cpu_snapshot_activate_error,
                        "model_key_hash": _snapshot_key_hash,
                        "clip_object_type": type(models.clip).__name__
                        if models.clip is not None else "",
                        "unet_object_type": type(models.unet).__name__
                        if models.unet is not None else "",
                        "duration_ms": _activation_duration_ms,
                    },
                )
                _bridge_installed = 1 if self._preload_bridge._original_methods else 0
                _c_prep = self._preload_bridge._preparation
                _c_clip_ready = 1 if _c_prep is not None and _c_prep.clip_future is not None and _c_prep.clip_future.done() else 0
                _c_unet_ready = 1 if _c_prep is not None and _c_prep.unet_future is not None and _c_prep.unet_future.done() else 0
                print(
                    f"[v2.cpu_snapshot] status=miss reason={_cpu_snapshot_activate_error[:60]} "
                    f"bridge_installed={_bridge_installed} "
                    f"clip_ready={_c_clip_ready} unet_ready={_c_unet_ready}",
                    flush=True,
                )
                # Fall through to the existing preload branch.
        # ── Prefill-configuration diagnostic (after CPU snapshot state is final) ──
        _prefill_env_raw = os.environ.get("COMFYMODAL_V2_PREFILL_LANES", "critical")
        print(
            f"[v2.prefill_config] env={_prefill_env_raw} parsed={_PREFILL_LANE_MODE} "
            f"cpu_snapshot_active={int(bool(_cpu_snapshot_activated))}",
            flush=True,
        )
        try:
            # Pre-initialize for Plan C gating
            preparation: RestorePreparation | None = None
            _optimized_ok = False
            _unet_deferred_meta: dict[str, Any] = {}
            _defer_api = None if _cpu_snapshot_activated else (self._load_legacy_runtime() if self._restore_plan else None)

            if self._restore_plan is not None:
                trace.emit("preload_submission_start", phase="restore", metadata={
                    "restore_plan_generation": str(self._restore_plan.generation),
                })
                # â”€â”€ Bounded V2 latency: check if we can defer UNET+VAE to
                #    original graph loaders and prepare only CLIP through the
                #    V2 bridge.  On any failure (missing helper, exception,
                #    non-submitted background future) we fail closed to the
                #    existing full V2 preload path. â”€â”€
                if not _cpu_snapshot_activated and self._check_unet_deferral_eligible(_defer_api, self._restore_plan):
                    trace.emit("defer_trial_start", phase="restore", metadata={
                        "unet_identity_hash": stable_hash(self._restore_plan.model_key.unet_identity) if self._restore_plan else "",
                    })
                    try:
                        # â”€â”€ v2 UNET cache patch â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
                        trace.emit("v2_unet_cache_patch_start", phase="restore")
                        _defer_api._patch_unet_loader_cache()
                        trace.emit("v2_unet_cache_patch_end", phase="restore")

                        # â”€â”€ v2 CLIP prepare submit â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
                        trace.emit("v2_clip_prepare_submit_start", phase="restore")
                        # Prepare only CLIP through V2; UNET and VAE are
                        # deferred to the original (patched) graph loaders.
                        preparation = self._preload_bridge.prepare(
                            self._restore_plan, trace=trace,
                            prepare_unet=False, prepare_vae=False,
                        )
                        trace.emit("v2_clip_prepare_submit_end", phase="restore")

                        # â”€â”€ v2 CLIP worker wait â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
                        trace.emit("v2_clip_worker_wait_start", phase="restore")
                        self._preload_bridge.close_workers()
                        trace.emit("v2_clip_worker_wait_end", phase="restore")
                        trace.emit("v2_clip_ready", phase="restore")

                        # â”€â”€ v2 UNET spec extract â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
                        trace.emit("v2_unet_spec_extract_start", phase="restore")
                        unet_name = self._restore_plan.model_key.unet_identity
                        weight_dtype = "default"
                        try:
                            unet_specs = self._restore_plan.model_spec.get("loaders", {}).get("unet", [])
                            if unet_specs and isinstance(unet_specs, list) and len(unet_specs) > 0:
                                weight_dtype = str(unet_specs[0].get("weight_dtype", "default"))
                        except Exception:
                            pass
                        trace.emit("v2_unet_spec_extract_end", phase="restore",
                                   metadata={"unet_name": unet_name, "weight_dtype": weight_dtype})

                        # â”€â”€ v2 background UNET submit â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
                        trace.emit("v2_background_unet_submit_start", phase="restore")

                        # Build diagnostic scope factory for the background worker.
                        # Use a shared mutable dict so _start_production_restore_unet
                        # populates canonical_key, diagnostic_id, resolved_path before
                        # the worker thread starts, and the factory reads the live values.
                        _bg_diag_ctx: dict[str, Any] = {
                            "canonical_key": "",
                            "diagnostic_id": "",
                            "resolved_path": "",
                            "restored_instance_id": restored_instance_id,
                            "restore_session_id": restore_session_id,
                            "weight_dtype": weight_dtype,
                            "submitted_at_unix": time.time(),
                        }
                        _bg_unet_trace_ref = None
                        try:
                            from comfymodal_runtime.model_preload import external_model_lane_scope
                            _factory_tid = trace.trace_id

                            def _bg_unet_diag_scope_factory():
                                """Create external_model_lane_scope for the bg UNET worker.
                                Reads live values from the shared mutable _bg_diag_ctx
                                dict, which _start_production_restore_unet populated."""
                                _ck = str(_bg_diag_ctx.get("canonical_key", ""))
                                _did = str(_bg_diag_ctx.get("diagnostic_id", ""))
                                _rp = str(_bg_diag_ctx.get("resolved_path", ""))
                                _bt = RuntimeTrace(
                                    process="remote_background_unet",
                                    trace_id=_factory_tid,
                                )
                                _bt.set_metadata(
                                    restored_instance_id=str(_bg_diag_ctx.get("restored_instance_id", "")),
                                    restore_session_id=str(_bg_diag_ctx.get("restore_session_id", "")),
                                    canonical_key=_ck,
                                    diagnostic_id=_did,
                                    resolved_path=_rp,
                                    weight_dtype=str(_bg_diag_ctx.get("weight_dtype", "")),
                                )
                                return external_model_lane_scope(
                                    _bt, lane="UNET", phase="restore", expected_read_count=1,
                                )

                            _defer_result = _defer_api._start_production_restore_unet(
                                {"unet": unet_name, "weight_dtype": weight_dtype},
                                restore_start=time.time(),
                                restore_stages={},
                                diagnostic_scope_factory=_bg_unet_diag_scope_factory,
                                diagnostic_context=_bg_diag_ctx,
                                diagnostic_sink=None,
                            )
                            # Update shared context with values returned by the method
                            _defer_key = str(_defer_result.get("canonical_key", ""))
                            _defer_did = str(_defer_result.get("diagnostic_id", ""))
                            if _defer_key:
                                _bg_diag_ctx["canonical_key"] = _defer_key
                            if _defer_did:
                                _bg_diag_ctx["diagnostic_id"] = _defer_did
                            _bg_unet_trace_ref = None
                        except Exception:
                            _defer_result = _defer_api._start_production_restore_unet(
                                {"unet": unet_name, "weight_dtype": weight_dtype},
                                restore_start=time.time(),
                                restore_stages={},
                            )

                        trace.emit("v2_background_unet_submit_end", phase="restore",
                                   metadata={"submitted": _defer_result.get("submitted", False),
                                             "canonical_key": _defer_result.get("canonical_key", ""),
                                             "diagnostic_id": _defer_result.get("diagnostic_id", "")})

                        # NOTE: bg_unet IO/stages summaries are NOT emitted here.
                        # They are emitted inside external_model_lane_scope's finally
                        # block after the worker completes (model_preload.py).
                        if _defer_result.get("submitted"):
                            _optimized_ok = True
                            _unet_deferred_meta = {
                                "decision": str(_defer_result.get("decision", "unknown")),
                                "submitted": True,
                                "unet_identity": unet_name,
                            }
                            trace.emit("defer_trial_result", phase="restore", metadata={
                                "submitted": True,
                                "decision": str(_defer_result.get("decision", "unknown"))[:120],
                            })
                        else:
                            trace.emit("defer_trial_result", phase="restore", metadata={
                                "submitted": False,
                                "reason": "not_submitted",
                            })
                    except Exception as _defer_exc:
                        trace.emit("defer_trial_result", phase="restore", metadata={
                            "submitted": False,
                            "reason": str(_defer_exc)[:200],
                        })
                if not _cpu_snapshot_activated and not _optimized_ok:
                    # Check whether an existing clip-only preparation can be
                    # extended with UNET+VAE rather than cleared+reprepared.
                    _existing = self._preload_bridge._preparation
                    _can_extend = False
                    if _existing is not None and _existing.clip_future is not None:
                        try:
                            _existing.clip_future.result()  # non-blocking; already waited
                            _can_extend = True
                        except Exception:
                            _can_extend = False
                    if _can_extend:
                        preparation = self._preload_bridge.extend_preparation(
                            prepare_unet=True, prepare_vae=True, trace=trace,
                        )
                        self._preload_bridge.close_workers()
                        trace.emit(
                            "preload_fallback_mode", phase="restore",
                            metadata={"mode": "extended_existing_preparation"},
                        )
                    else:
                        # Fail closed: clear any partially-prepared bridge state
                        # and use the full V2 preload path.
                        _reason = "no_useful_existing_preparation"
                        if _existing is not None and _existing.clip_future is not None:
                            _reason = "clip_future_failed"
                        self._preload_bridge.clear()
                        preparation = self._preload_bridge.prepare(self._restore_plan, trace=trace)
                        self._preload_bridge.close_workers()
                        trace.emit(
                            "preload_fallback_mode", phase="restore",
                            metadata={"mode": "full_reprepare", "reason": _reason},
                        )
                # Shared tail
                if _cpu_snapshot_activated:
                    trace.emit("preload_cpu_snapshot_skip", phase="restore", metadata={
                        "unet_identity": self._restore_plan.model_key.unet_identity,
                        "clip_identity": self._restore_plan.model_key.clip_identity,
                    })
                    trace.emit("preload_submission_end", phase="restore", metadata={
                        "preload_scheduled": False,
                        "cpu_snapshot": True,
                    })
                    trace.set_metadata(
                        restore_plan_generation=str(self._restore_plan.generation),
                        preload_scheduled=False,
                        preload_diagnostics=self._preload_bridge.diagnostics(),
                    )
                else:
                    trace.emit("preload_submission_end", phase="restore", metadata={
                        "preload_scheduled": str(bool(preparation)),
                        "unet_deferred": _optimized_ok,
                    })
                    trace.set_metadata(
                        restore_plan_generation=str(self._restore_plan.generation),
                        preload_scheduled=bool(preparation),
                        preload_diagnostics=self._preload_bridge.diagnostics(),
                    )
                    if _optimized_ok:
                        trace.emit("unet_deferred", phase="restore", metadata=_unet_deferred_meta)
            else:
                self._preload_bridge.clear()
            trace.emit(
                "restore_completion_evidence",
                phase="restore",
                metadata={
                    "preload_submitted": str(self._restore_plan is not None),
                    "restore_plan_generation": str(
                        self._restore_plan.generation if self._restore_plan else ""
                    ),
                },
            )
            # â”€â”€ v2 restore finalize â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
            trace.emit("v2_restore_finalize_start", phase="restore")

            trace.emit("remote_lifecycle_end", phase="restore", metadata={"status": "restored"})
            self._remember_lifecycle_trace(trace)
            trace = self._lifecycle_trace or trace

            restore_total_ms = round((time.perf_counter() - _restore_perf_start) * 1000.0, 3)
            # Capture end timestamps BEFORE constructing _restore_timing
            _restore_status = "success"
            _restore_end_wall_ns = int(time.time() * 1_000_000_000)
            _restore_end_mono_ns = time.monotonic_ns()
            _restore_timing: dict[str, Any] = {
                "restore_total_ms": restore_total_ms,
                "restore_session_id": restore_session_id,
                "restored_instance_id": restored_instance_id,
                "legacy_container_session_id": legacy_container_session_id,
                "container_session_id": self.container_session_id,
                "restore_count": self._restore_count,
                "lifecycle_status": "ok",
                "lifecycle_method": "restore",
                "remote_python_resume_wall_unix_ns": remote_python_resume_wall_ns,
                "remote_python_resume_mono_ns": remote_python_resume_mono_ns,
                "restore_method_start_wall_unix_ns": restore_method_start_wall_ns,
                "restore_method_start_mono_ns": restore_method_start_mono_ns,
                "restore_method_end_wall_unix_ns": _restore_end_wall_ns,
                "restore_method_end_mono_ns": _restore_end_mono_ns,
                "restore_method_status": "success",
            }
            # Include available stage timings from bootstrap state (only when present)
            if state.stage_durations:
                for _stage, _dur_ms in state.stage_durations.items():
                    if _dur_ms is not None and _dur_ms > 0:
                        _restore_timing[f"{_stage}_ms"] = round(float(_dur_ms), 3)
            # Merge restore-stage timers (reload_runtime_state, reload_models,
            # restore_gpu_state, initialize_cuda, snapshot_identity_checks,
            # cpu_snapshot_retargeting) collected by _wrap_restore_stage and
            # direct inline timing in restore().
            _REQUIRED_RESTORE_STAGES = (
                "reload_runtime_state", "reload_models", "restore_gpu_state",
                "initialize_cuda", "snapshot_identity_checks", "cpu_snapshot_retargeting",
            )
            for _stage in _REQUIRED_RESTORE_STAGES:
                _dur_ms = _RESTORE_STAGE_TIMERS.get(_stage, 0.0)
                _restore_timing[f"{_stage}_ms"] = round(_dur_ms, 3)
                _restore_timing[f"{_stage}_invoked"] = _dur_ms > 0.0
                _restore_timing[f"{_stage}_reason"] = (
                    "ok" if _dur_ms > 0.0 else "not_invoked"
                )
            # Merge any additional non-required stage timers present
            if _RESTORE_STAGE_TIMERS:
                for _stage, _dur_ms in _RESTORE_STAGE_TIMERS.items():
                    if _stage not in _REQUIRED_RESTORE_STAGES and _dur_ms > 0:
                        _restore_timing[f"{_stage}_ms"] = round(_dur_ms, 3)
            self._restore_timing = _restore_timing
            _LATEST_LIFECYCLE_TIMING = _restore_timing

            trace.emit("v2_restore_finalize_end", phase="restore")
            _restore_result = {
                "backend": state.backend,
                "cuda": dict(state.cuda),
                "runtime_generation": state.runtime_generation,
                "status": "restored",
                "_restore_timing": _restore_timing,
                "restored_instance_id": restored_instance_id,
                "restore_session_id": restore_session_id,
                "container_session_id": self.container_session_id or _V2_CONTAINER_SESSION_ID,
                "trace": trace.to_dict(),
                "phase_durations_ms": trace.export_phase_durations(),
            }

            # â”€â”€ Emit compact restore-breakdown summary â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
            _brk, _clip = _collect_restore_events_for_summary(trace)
            print(
                f"[v2.restore_breakdown] "
                f"bootstrap_ms={_brk.get('bootstrap_ms')} "
                f"unet_cache_patch_ms={_brk.get('unet_cache_patch_ms')} "
                f"clip_prepare_submit_ms={_brk.get('clip_prepare_submit_ms')} "
                f"clip_worker_wait_ms={_brk.get('clip_worker_wait_ms')} "
                f"unet_spec_extract_ms={_brk.get('unet_spec_extract_ms')} "
                f"bg_unet_submit_ms={_brk.get('bg_unet_submit_ms')} "
                f"restore_finalize_ms={_brk.get('restore_finalize_ms')}",
                flush=True,
            )
            print(
                f"[v2.clip_stages] "
                f"worker_queue_ms={_clip.get('worker_queue_ms')} "
                f"load_torch_file_ms={_clip.get('load_torch_file_ms')} "
                f"read_to_ready_ms={_clip.get('read_to_ready_ms')} "
                f"post_read_cpu_prepare_ms={_clip.get('post_read_cpu_prepare_ms')} "
                f"gpu_wait_ms={_clip.get('gpu_wait_ms')} "
                f"gpu_commit_ms={_clip.get('gpu_commit_ms')} "
                f"read_end_to_ready_ms={_clip.get('read_end_to_ready_ms')} "
                f"worker_total_ms={_clip.get('worker_total_ms')} "
                f"worker_close_wait_ms={_clip.get('worker_close_wait_ms')} "
                f"restore_finalization_ms={_clip.get('restore_finalization_ms')}",
                flush=True,
            )

            # â”€â”€ Emit restoration identity line â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
            print(
                f"[v2.restoration_identity] "
                f"restored_instance_id={restored_instance_id} "
                f"restore_session_id={restore_session_id} "
                f"container_session_id={self.container_session_id or _V2_CONTAINER_SESSION_ID} "
                f"modal_task_id={identity.get('container_task_id', '')} "
                f"modal_image_id={identity.get('image_id', '')} "
                f"modal_cloud={identity.get('cloud', '')} "
                f"modal_region={identity.get('region', '')} "
                f"pid={os.getpid()} "
                f"hostname={_capture_host_info().get('hostname', '')} "
                f"restore_total_ms={restore_total_ms} "
                f"remote_python_resume_wall_unix_ns={remote_python_resume_wall_ns} "
                f"restore_method_start_wall_unix_ns={restore_method_start_wall_ns} "
                f"restore_method_end_wall_unix_ns={self._fmt_or_absent(_restore_end_wall_ns)} "
                f"modal_method_entry_wall_unix_ns={self._fmt_or_absent(None)} "
                f"restore_status={_restore_status} "
                f"restore_method_status={_restore_status} ",
                flush=True,
            )

            print(
                f"[v2.lifecycle] method=restore snap=False "
                f"container_session={_V2_CONTAINER_SESSION_ID} "
                f"restore_count={self._restore_count} "
                f"restore_total_ms={restore_total_ms} "
                f"remote_python_resume_wall_unix_ns={remote_python_resume_wall_ns} "
                f"restore_method_start_wall_unix_ns={restore_method_start_wall_ns} "
                f"restore_method_end_wall_unix_ns={self._fmt_or_absent(_restore_end_wall_ns)} "
                f"modal_method_entry_wall_unix_ns={self._fmt_or_absent(None)} "
                f"restore_status={_restore_status} "
                f"restore_method_status={_restore_status} "
                f"status=restored"
            )

            _report_host_memory("restore_complete")

            _detect_gpu_allocation(
                _MODAL_RESOURCES.get("spec", ModalRuntimeSpec()).gpu
            )

            trace.emit("v2_restore_return", phase="restore")
            _restore_result["trace"] = trace.to_dict()
            set_restore_return_marker(
                restored_instance_id=restored_instance_id,
                restore_session_id=restore_session_id,
                legacy_container_session_id=legacy_container_session_id,
                modal_task_id=identity.get("container_task_id", ""),
                pid=os.getpid(),
            )
            return _restore_result
        finally:
            # Clear process-global restore-stage timers to prevent stale
            # accumulation on the next restore.  This finally runs regardless
            # of success or cancellation.
            _RESTORE_STAGE_TIMERS.clear()
            if _restore_end_wall_ns is None:
                _restore_end_wall_ns = int(time.time() * 1_000_000_000)
                _restore_end_mono_ns = time.monotonic_ns()
                if _restore_status not in ("success", "error"):
                    _restore_status = "error"
                print(
                    f"[v2.lifecycle] method=restore snap=False "
                    f"container_session={_V2_CONTAINER_SESSION_ID} "
                    f"restore_count={getattr(self, '_restore_count', 0)} "
                    f"restore_total_ms={round((time.perf_counter() - _restore_perf_start) * 1000.0, 3)} "
                    f"remote_python_resume_wall_unix_ns={remote_python_resume_wall_ns} "
                    f"restore_method_start_wall_unix_ns={restore_method_start_wall_ns} "
                    f"restore_method_end_wall_unix_ns={_restore_end_wall_ns} "
                    f"modal_method_entry_wall_unix_ns={self._fmt_or_absent(None)} "
                    f"restore_status={_restore_status} "
                    f"restore_method_status={_restore_status} "
                    f"status=error",
                    flush=True,
                )
                # Backfill _restore_timing with raw fields when this finally
                # path catches an error that escaped the success/error handlers
                # above (e.g. preload/finalize unexpected exception).
                if self._restore_timing is not None:
                    _rt = self._restore_timing
                    if _rt.get("restore_method_end_wall_unix_ns") is None:
                        _rt["restore_method_end_wall_unix_ns"] = _restore_end_wall_ns
                    if _rt.get("restore_method_end_mono_ns") is None:
                        _rt["restore_method_end_mono_ns"] = _restore_end_mono_ns
                    if _rt.get("restore_method_status") is None:
                        _rt["restore_method_status"] = "error"
                    if _rt.get("remote_python_resume_wall_unix_ns") is None:
                        _rt["remote_python_resume_wall_unix_ns"] = remote_python_resume_wall_ns
                    if _rt.get("remote_python_resume_mono_ns") is None:
                        _rt["remote_python_resume_mono_ns"] = remote_python_resume_mono_ns
                    if _rt.get("restore_method_start_wall_unix_ns") is None:
                        _rt["restore_method_start_wall_unix_ns"] = restore_method_start_wall_ns
                    if _rt.get("restore_method_start_mono_ns") is None:
                        _rt["restore_method_start_mono_ns"] = restore_method_start_mono_ns
                    _LATEST_LIFECYCLE_TIMING = _rt

    async def _run_in_process(self, plan: ExecutionPlan, context: ExecutionContext) -> dict[str, Any]:
        if context.cancelled and context.cancelled():
            raise RuntimeError("execution cancelled before PromptExecutor start")
        _report_host_memory("prompt_executor_start")
        trace = context.trace or RuntimeTrace(request_id=context.request_id, process="remote")
        trace.emit("runtime_config_start", phase="execution")
        self._configure_runtime()
        trace.emit("runtime_config_end", phase="execution")
        trace.emit("legacy_runtime_load_start", phase="execution")
        api = self._load_legacy_runtime()
        trace.emit("legacy_runtime_load_end", phase="execution")
        # Attach stable container identity to execution trace
        _cid = self.container_session_id or _V2_CONTAINER_SESSION_ID
        trace.container_session_id = _cid
        trace.emit("graph_execution_start", phase="execution")
        # Stash the execution trace on the legacy API so the patched UNET
        # loader (_cached_unet_load) can emit V2 cache-hit events even
        # when current_v2_loader_bridge() returns None.
        try:
            api._v2_graph_trace = trace
        except Exception:
            pass
        # â”€â”€ Plan C: CPU snapshot request binding â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        # When CPU snapshot models are active, derive the request identity
        # and re-bind the bridge so the pre-loaded models serve this
        # specific request.  If the request model identity differs, clear
        # the bridge and deactivate without rebuilding the snapshot.
        self._lazy_init_snapshot_state()
        _bind_perf = time.perf_counter()
        if self._cpu_snapshot_models_active and self._cpu_snapshot_models is not None:
            try:
                workflow = _thaw(plan.workflow) if hasattr(plan, "workflow") else {}
                model_stack = dict(plan.model_stack) if hasattr(plan, "model_stack") else {}
                request_model_key = derive_model_key(workflow)
                request_prefill_key = derive_prefill_key(request_model_key, workflow)
                request_model_spec = build_restore_model_spec(workflow, model_stack)
                snapshot_key = self._cpu_snapshot_models.model_key
                snapshot_spec = self._cpu_snapshot_models.model_spec
                _role_report = _canonical_role_match_report(
                    request_model_spec=request_model_spec,
                    snapshot_model_spec=snapshot_spec,
                )
                if _role_report["compatible"]:
                    _flags = plan.execution_options.compatibility_flags
                    _bypass_snapshot_unet = isinstance(_flags, Mapping) and _flags.get("diagnostic_bypass_cpu_snapshot_unet") is True
                    if _bypass_snapshot_unet:
                        self._preload_bridge.use_ready_clip(
                            model_key=request_model_key,
                            prefill_key=request_prefill_key,
                            model_spec=request_model_spec,
                            clip=self._cpu_snapshot_models.clip,
                            trace=trace,
                        )
                        self._preload_bridge.extend_preparation(
                            prepare_unet=True, prepare_vae=False, trace=trace,
                        )
                        _unet_source = "normal_loader"
                        _clip_source = "cpu_snapshot"
                        _reason = "diagnostic_unet_bypass"
                    else:
                        self._use_cpu_snapshot_models_on_bridge(
                            request_model_key,
                            request_prefill_key,
                            request_model_spec,
                            self._cpu_snapshot_models.unet,
                            self._cpu_snapshot_models.clip,
                            trace=trace,
                        )
                        _unet_source = "cpu_snapshot"
                        _clip_source = "cpu_snapshot"
                        _reason = "ok"
                        self._maybe_propagate_cpu_snapshot_unet_state(
                            request_model_key, request_model_spec, trace,
                        )
                    if _bypass_snapshot_unet:
                        print(
                            "[v2.cpu_snapshot_request] status=partial_bypass "
                            "reason=diagnostic_unet_bypass clip_source=cpu_snapshot "
                            "unet_source=normal_loader",
                            flush=True,
                        )
                    else:
                        print(
                            "[v2.cpu_snapshot_request] status=reused reason=ok",
                            flush=True,
                        )
                    trace.emit(
                        "cpu_snapshot_models_request_bound",
                        phase="execution",
                        metadata={
                            "status": "bound",
                            "reason": _reason,
                            "diagnostic_bypass_cpu_snapshot_unet": 1 if _bypass_snapshot_unet else 0,
                            "cpu_snapshot_clip_reused": 1,
                            "cpu_snapshot_unet_reused": 0 if _bypass_snapshot_unet else 1,
                            "unet_source": _unet_source,
                            "clip_source": _clip_source,
                            "model_key_hash": snapshot_key.stable_hash[:16] if snapshot_key else "",
                            "clip_object_type": type(self._cpu_snapshot_models.clip).__name__,
                            "unet_object_type": type(self._cpu_snapshot_models.unet).__name__,
                            "duration_ms": round((time.perf_counter() - _bind_perf) * 1000.0, 3),
                        },
                    )
                else:
                    # Model identity differs — clear bridge and deactivate.
                    self._preload_bridge.clear()
                    self._cpu_snapshot_models_active = False
                    self._cpu_snapshot_unet_runtime_state = None
                    trace.emit(
                        "cpu_snapshot_models_request_bound",
                        phase="execution",
                        metadata={
                            "status": "mismatch",
                            "reason": "model_or_spec_mismatch",
                            "model_key_hash": snapshot_key.stable_hash[:16] if snapshot_key else "",
                            "snapshot_key_hash": snapshot_key.stable_hash[:16] if snapshot_key else "",
                            "request_key_hash": request_model_key.stable_hash[:16],
                            "clip_object_type": type(self._cpu_snapshot_models.clip).__name__,
                            "unet_object_type": type(self._cpu_snapshot_models.unet).__name__,
                            "duration_ms": round((time.perf_counter() - _bind_perf) * 1000.0, 3),
                        },
                    )
                    print(
                        "[v2.cpu_snapshot_request] status=fallback reason=model_or_spec_mismatch",
                        flush=True,
                    )
            except Exception as _bind_exc:
                self._preload_bridge.clear()
                self._cpu_snapshot_models_active = False
                self._cpu_snapshot_unet_runtime_state = None
                trace.emit(
                    "cpu_snapshot_models_request_bound",
                    phase="execution",
                    metadata={
                        "status": "error",
                        "reason": str(_bind_exc)[:200],
                        "model_key_hash": "",
                        "clip_object_type": type(self._cpu_snapshot_models.clip).__name__
                        if self._cpu_snapshot_models is not None and self._cpu_snapshot_models.clip is not None else "",
                        "unet_object_type": type(self._cpu_snapshot_models.unet).__name__
                        if self._cpu_snapshot_models is not None and self._cpu_snapshot_models.unet is not None else "",
                        "duration_ms": round((time.perf_counter() - _bind_perf) * 1000.0, 3),
                    },
                )
                print(
                    "[v2.cpu_snapshot_request] status=fallback "
                    f"reason=error:{str(_bind_exc)[:80]}",
                    flush=True,
                )
        # â”€â”€ Execution-phase CLIP exact-prefill single-flight â”€â”€â”€â”€â”€â”€â”€â”€
        # Schedule prefill immediately after graph start so it runs
        # concurrently with execution setup.  The callback waits for both
        # UNET and CLIP preparation futures before encoding, preventing
        # GPU model-load/encode overlap.  Idempotent and thread-safe.
        if not self._cpu_snapshot_models_active:
            _scheduled = self._preload_bridge.schedule_execution_prefill(trace=trace)
            print(f"[v2.execution_prefill] scheduled={1 if _scheduled else 0}", flush=True)
        else:
            print(f"[v2.execution_prefill] scheduled=0", flush=True)
        try:
            with request_execution_trace_scope(trace):
                with self._preload_bridge.request_scope():
                    result: dict[str, Any] = await self._execute_v2_prompt_executor(plan, context, api, trace)
                _gpu_summary = gpu_not_observed_summary()
                trace.set_metadata(gpu_observation_summary=_gpu_summary)
                # â”€â”€ Build GPU observation classification from helper + trace events â”€â”€
                _gpu_wrapper_installed = _gpu_summary.get("wrapper_status") == "installed"
                _gpu_wrapper_calls = _gpu_summary.get("count", 0)
                _gpu_graph_load_obs = any(e.name == "graph_gpu_load_start" for e in trace.events)
                _gpu_sampler_setup_obs = (
                    any(e.name in ("sampler_lane_wait_start", "sampler_lane_wait_end") for e in trace.events)
                    or any(
                        e.name == "graph_gpu_load_start"
                        and e.metadata.get("caller_classification") == "sampler_setup"
                        for e in trace.events
                    )
                )
                _gpu_obs_classification = {
                    "wrapper_installed": _gpu_wrapper_installed,
                    "wrapper_calls_observed": _gpu_wrapper_calls > 0,
                    "graph_gpu_load_observed": _gpu_graph_load_obs,
                    "sampler_setup_observed": _gpu_sampler_setup_obs,
                }
                trace.set_metadata(gpu_observation_classification=_gpu_obs_classification)
            trace.emit("graph_execution_end", phase="execution")
            # Drain late worker events (read/cpu/gpu/ready) from bridge
            # preparation into the execution trace so they are not lost.
            self._preload_bridge.drain_worker_events(trace)
            self._preload_bridge.close_workers()
            # Ensure any remaining legacy API background loader threads
            # for this request are terminal before result delivery.
            # MUST happen before the _BG_UNET_DIAG_STORE drain so
            # a workflow that never demands UNET still has its
            # background worker finish and store events first.
            self._join_legacy_background_threads(api)
            # Drain available background UNET diagnostics into trace
            try:
                from comfymodal_runtime.model_preload import _BG_UNET_DIAG_STORE, _BG_UNET_DIAG_LOCK
                with _BG_UNET_DIAG_LOCK:
                    for _ck in list(_BG_UNET_DIAG_STORE.keys()):
                        _bg_events = _BG_UNET_DIAG_STORE.pop(_ck, [])
                        if _bg_events:
                            trace.extend(_bg_events)
            except Exception:
                pass
            trace.set_metadata(
                restore_plan_generation=str(self._restore_plan.generation if self._restore_plan else ""),
                execution_backend="in_process",
                preload_diagnostics=self._preload_bridge.diagnostics(),
                container_session_id=_cid,
            )
            _gpu_locations: list[str] = []
            for _gpu_event in trace.events:
                if _gpu_event.name == "graph_gpu_load_start":
                    _classification = str(_gpu_event.metadata.get("caller_classification", "graph_model_loading"))
                    if _classification not in _gpu_locations:
                        _gpu_locations.append(_classification)
                elif _gpu_event.name == "gpu_commit_start":
                    _lane_name = str(_gpu_event.metadata.get("lane", ""))
                    _lane_location = {
                        "UNET": "background_unet_preparation",
                        "CLIP": "restore_clip_preparation",
                        "VAE": "restore_vae_preparation",
                    }.get(_lane_name)
                    if _lane_location and _lane_location not in _gpu_locations:
                        _gpu_locations.append(_lane_location)
            if not _gpu_locations:
                _gpu_locations = ["not_observed"]
            trace.set_metadata(gpu_loading_observed=_gpu_locations)
            result["gpu_loading_observed"] = _gpu_locations
            result["trace"] = trace.to_dict()
            if "_stage_timings" in result:
                result["trace"]["stages"] = result.pop("_stage_timings")
            result["container_session_id"] = _cid
            result["restore_plan_generation"] = str(self._restore_plan.generation if self._restore_plan else "")
            _rt = self._restore_timing or _LATEST_LIFECYCLE_TIMING
            if _rt is not None:
                result["_restore_timing"] = dict(_rt)
            result["_snapshot_target_fingerprint"] = _snapshot_target_fingerprint()
            result["phase_durations_ms"] = trace.export_phase_durations()
            _report_host_memory("result_complete")
            return result
        except Exception as exc:
            trace.emit("graph_execution_end", phase="execution", metadata={"status": "error", "error": str(exc)[:200]})
            # Capture GPU observation summary/classification on exception path too.
            # Safe after request_execution_trace_scope exit â€” reads from module-level state.
            try:
                _gpu_summary = gpu_not_observed_summary()
                trace.set_metadata(gpu_observation_summary=_gpu_summary)
                _gpu_wrapper_installed = _gpu_summary.get("wrapper_status") == "installed"
                _gpu_wrapper_calls = _gpu_summary.get("count", 0)
                _gpu_graph_load_obs = any(e.name == "graph_gpu_load_start" for e in trace.events)
                _gpu_sampler_setup_obs = (
                    any(e.name in ("sampler_lane_wait_start", "sampler_lane_wait_end") for e in trace.events)
                    or any(
                        e.name == "graph_gpu_load_start"
                        and e.metadata.get("caller_classification") == "sampler_setup"
                        for e in trace.events
                    )
                )
                _gpu_obs_classification = {
                    "wrapper_installed": _gpu_wrapper_installed,
                    "wrapper_calls_observed": _gpu_wrapper_calls > 0,
                    "graph_gpu_load_observed": _gpu_graph_load_obs,
                    "sampler_setup_observed": _gpu_sampler_setup_obs,
                }
                trace.set_metadata(gpu_observation_classification=_gpu_obs_classification)
            except Exception:
                pass
            # Ensure any remaining legacy API background loader threads
            # are terminal before draining diagnostics (same ordering as
            # success path: join first, then drain).
            self._preload_bridge.close_workers()
            self._join_legacy_background_threads(api)
            # Drain bg diagnostics on exception path too
            try:
                from comfymodal_runtime.model_preload import _BG_UNET_DIAG_STORE, _BG_UNET_DIAG_LOCK
                with _BG_UNET_DIAG_LOCK:
                    for _ck in list(_BG_UNET_DIAG_STORE.keys()):
                        _bg_events = _BG_UNET_DIAG_STORE.pop(_ck, [])
                        if _bg_events:
                            trace.extend(_bg_events)
            except Exception:
                pass
            raise

    def _maybe_propagate_cpu_snapshot_unet_state(
        self,
        request_model_key: Any,
        request_model_spec: Any,
        trace: RuntimeTrace,
    ) -> None:
        """Propagate saved snapshot UNET state into request trace.

        Called from ``_run_in_process`` inside the exact-match reuse branch.
        Validates that the stored state belongs to the current request by
        comparing UNET identity and requested weight dtype, then emits the
        state as a trace event with ``propagated_from_restore=True`` and the
        current request ID.  On mismatch the saved state is cleared so no
        stale state is used by later requests.

        Must be called only when ``_cpu_snapshot_models_active`` is True,
        models match, and ``diagnostic_bypass_cpu_snapshot_unet`` is False.
        """
        if self._cpu_snapshot_unet_runtime_state is None:
            return
        _req_unet_ident = str(getattr(request_model_key, "unet_identity", ""))
        _req_wd = "default"
        try:
            _plan_unet = (request_model_spec or {}).get("loaders", {}).get("unet", [])
            for _pl in _plan_unet:
                if isinstance(_pl, Mapping) and _pl.get("unet_name") == _req_unet_ident:
                    _req_wd = str(_pl.get("weight_dtype", "default"))
                    break
        except Exception:
            _req_wd = "default"
        _stored_unet = self._cpu_snapshot_unet_runtime_state.get("unet_identity", "")
        _stored_wd = self._cpu_snapshot_unet_runtime_state.get("requested_weight_dtype", "")
        if _req_unet_ident == _stored_unet and _req_wd == _stored_wd:
            _prop_meta = copy.deepcopy(self._cpu_snapshot_unet_runtime_state)
            _prop_meta["request_id"] = str(trace.request_id if trace else "")
            _prop_meta["propagated_from_restore"] = True
            trace.emit("unet_runtime_state", metadata=_prop_meta)
            print(
                f"[v2.unet_runtime_state_propagated] status=emitted "
                f"request_id={trace.request_id} "
                f"unet_identity={_stored_unet} "
                f"requested_weight_dtype={_stored_wd} "
                f"restored_instance_id={_prop_meta.get('restored_instance_id', '')} "
                f"restore_session_id={_prop_meta.get('restore_session_id', '')}",
                flush=True,
            )
        else:
            self._cpu_snapshot_unet_runtime_state = None
            print(
                f"[v2.unet_runtime_state_propagated] status=skipped "
                f"reason=identity_or_dtype_mismatch",
                flush=True,
            )

    @staticmethod
    def _interval_from_trace(trace: Any, start_name: str, end_name: str) -> float | None:
        """Compute ms interval from the first start_name event to the first
        end_name event in the trace.  Returns None if either event is missing
        or end is before start (wrapping).  Does not raise."""
        start_ns: int | None = None
        end_ns: int | None = None
        for ev in trace.events:
            if ev.name == start_name and start_ns is None:
                start_ns = ev.monotonic_ns
            if ev.name == end_name and end_ns is None:
                end_ns = ev.monotonic_ns
            if start_ns is not None and end_ns is not None:
                break
        if start_ns is not None and end_ns is not None and end_ns >= start_ns:
            return round((end_ns - start_ns) / 1_000_000, 3)
        return None

    @staticmethod
    def _fmt_or_absent(v: float | int | None) -> str:
        """Format a numeric interval for the one-line summary.
        Returns ``str(v)`` for numeric values (including ``0.0``), ``"absent"`` for None."""
        if v is None:
            return "absent"
        return str(v)

    async def _execute_v2_prompt_executor(
        self,
        plan: ExecutionPlan,
        context: ExecutionContext,
        api: Any,
        trace: RuntimeTrace,
    ) -> dict[str, Any]:
        """Run the live ComfyUI PromptExecutor without the legacy wrapper.

        The v2 boundary owns request identity, validation, production
        authorization, output collection, and result packaging. ComfyUI still
        owns its actual PromptExecutor and node execution semantics.
        """
        # Reset the per-request unet_first_cuda_op dedup so the first forward
        # pass of this request emits the event.  Must fire before any CUDA op.
        reset_first_cuda_dedup()
        # Clear SAMPLER_SAMPLE wrapper dedup so each new request gets fresh
        # sampling_start/sampling_end events.
        with _sampler_wrapper_dedup_lock:
            _sampler_wrapper_dedup.clear()

        if context.cancelled and context.cancelled():
            raise RuntimeError("execution cancelled before PromptExecutor start")

        workflow = _thaw(plan.workflow)
        _res4lyf_reported = int(plan.production_report.get("res4lyf_options_injected_count", 0) or 0)
        _res4lyf_injected_ids = [
            str(node_id)
            for node_id, node in workflow.items()
            if isinstance(node, Mapping)
            and node.get("class_type") == "ClownOptions_ExtraOptions_Beta"
            and "disable_dummy_sampler_init" in str((node.get("inputs") or {}).get("extra_options", ""))
        ]
        print(
            f"[v2.exec] res4lyf_dummy_init_disabled={int(bool(_res4lyf_injected_ids))} "
            f"reported_injected={_res4lyf_reported} actual_injected={len(_res4lyf_injected_ids)}",
            flush=True,
        )
        trace.emit(
            "res4lyf_dummy_init_transform",
            phase="execution",
            metadata={
                "reported_injected": _res4lyf_reported,
                "actual_injected": len(_res4lyf_injected_ids),
                "disabled": bool(_res4lyf_injected_ids),
            },
        )
        prompt_id = str(context.request_id or f"v2-{id(workflow):x}")
        module = self._legacy_module
        executor = getattr(api, "_executor", None)
        if executor is None:
            raise RuntimeError("v2 PromptExecutor runtime is not initialized")

        wait_for_preload = getattr(api, "_wait_for_restore_preload_before_request", None)
        if callable(wait_for_preload):
            trace.emit("legacy_preload_check_start", phase="execution")
            wait_for_preload(workflow)
            trace.emit("legacy_preload_check_end", phase="execution")

        materialize_inputs = getattr(module, "_materialize_input_images", None)
        if plan.input_images and callable(materialize_inputs):
            trace.emit("input_materialization_start", phase="execution")
            materialize_inputs(dict(plan.input_images))
            trace.emit("input_materialization_end", phase="execution")
        # Preflight context and certificate-gated preflight fast path
        # Phase 2: resolve the exact certificate before expensive preflight.
        # On exact identity/component hit + preflight_ok, skip preflight.
        # Missing-node repair always runs outside the certified skip.
        # Process-local cache (keyed by restored_instance_id + cert_identity)
        # avoids volume reload/read/parse on repeated hits within the same
        # restore lifecycle.
        _v2_cert_hit = False
        _v2_cert_preflight_skip = False
        _v2_preflight_ran = False
        _v2_cert_identity = ""
        _v2_cert_components: dict[str, str] = {}
        _v2_schedule_cert_write = False
        _v2_dep_identity: DeploymentIdentity | None = globals().get("_MODAL_RESOURCES", {}).get("source_identity")
        _v2_repair_mode: str = ""
        _v2_custom_nodes_gen: str = ""

        # Pre-initialize outputs_to_execute/node_errors so they are always
        # defined before the execution/output section regardless of cert path.
        outputs_to_execute: list[str] = []
        node_errors: dict[str, Any] = {}

        # Diagnostic timing fields for certificate, preflight, and validation.
        _diag_cert_identity_build_ms: float = 0.0
        _diag_cert_cache_hit: bool = False
        _diag_cert_volume_reload_ms: float = 0.0
        _diag_cert_file_read_ms: float = 0.0
        _diag_cert_json_parse_validate_ms: float = 0.0
        _diag_cert_total_ms: float = 0.0
        _diag_legacy_preflight_ms: float = 0.0
        _diag_prompt_validation_ms: float = 0.0

        # Certificate tracking: initialize all branch state before first use
        _snap_cert_source: str | None = None
        _snapshot_valid: bool = False
        _cached_valid: bool = False
        _evict_reason: str = ""

        # Obtain preflight context from the loaded legacy API
        _preflight_fn = getattr(api, "_preflight_before_prompt_execution", None)
        if callable(_preflight_fn) and not getattr(api, "_preflight_already_ran", False):
            _v2_repair_mode, _v2_custom_nodes_gen, _v2_custom_nodes_src = _get_preflight_context(api, module)

            # [v2.generation_identity] diagnostic: source, raw-empty visibility,
            # short value, runtime state generation, api object id
            _cn_diag_val = _v2_custom_nodes_gen
            _cn_diag_short = (_cn_diag_val[:24] + "…") if len(_cn_diag_val) > 24 else _cn_diag_val
            _cn_diag_raw_empty = str(not bool(_cn_diag_val)).lower()
            _rs_gen = str(getattr(api, "_runtime_generation_seen", "") or "")
            _api_id = str(id(api))
            print(
                f"[v2.generation_identity] "
                f"custom_nodes_generation={_cn_diag_short!r} "
                f"raw_empty={_cn_diag_raw_empty} "
                f"source={_v2_custom_nodes_src} "
                f"runtime_state_generation={_rs_gen!r} "
                f"api_object_id={_api_id} "
                f"deployment_combined_hash={_V2_DEPLOYMENT_COMBINED_HASH[:16] if _V2_DEPLOYMENT_COMBINED_HASH else '<empty>'}",
                flush=True,
            )

            # Try cert lookup before preflight -- only eligible when the
            # deployment identity, repair mode, and custom-nodes generation
            # are all complete and recognised.
            if _V2_VALIDATION_CERT_ENABLED:
                _cert_wf_hash = plan.workflow_hash or ""
                if _cert_wf_hash:
                    _v2_dep_hash = _V2_DEPLOYMENT_COMBINED_HASH

                    # Cert read eligibility: nonempty deployment combined
                    # hash, recognised repair mode, and nonempty custom-nodes
                    # generation.  Incomplete context means preflight+validate
                    # must run and no certificate will be written.
                    _cert_eligible = (
                        bool(_v2_dep_hash)
                        and _v2_repair_mode in ("off", "fail_fast", "dev")
                        and bool(_v2_custom_nodes_gen)
                    )
                    if _cert_eligible:
                        # Compute cert identity WITH timing
                        _cert_identity_build_start = time.perf_counter()
                        _v2_cert_identity, _v2_cert_components = _compute_v2_cert_identity(
                            _cert_wf_hash,
                            repair_mode=_v2_repair_mode,
                            custom_nodes_generation=_v2_custom_nodes_gen,
                        )
                        _diag_cert_identity_build_ms = round((time.perf_counter() - _cert_identity_build_start) * 1000, 3)

                        # -- Snapshot-memory certificate check --
                        # On exact hit (full identity_components match or cert_identity),
                        # assign outputs/node_errors from stored payload, set V2 cert
                        # skip flags, zero all volume/file/json diagnostics, and do NOT
                        # enter process-cache/Volume/dependency preflight/validation paths.
                        _snap_cert_source = None
                        _snapshot_valid = False
                        if hasattr(self, 'bootstrap') and self.bootstrap is not None:
                            _bs = getattr(self.bootstrap, 'state', None)
                            if _bs is not None and _bs.snapshot_cert_valid:
                                _sc = _bs.snapshot_certificate
                                _sc_components = _sc.get("identity_components", {}) if isinstance(_sc, dict) else {}
                                _sc_outputs = _sc.get("outputs_to_execute", [])
                                _sc_errors = _sc.get("node_errors", {})
                                # Match full identity_components dictionary: workflow_hash,
                                # deployment_hash, repair_mode, custom_nodes_generation,
                                # schema_version — or cert_identity — not only workflow_hash
                                # and custom_nodes_generation.
                                _sc_identity_ok = (
                                    isinstance(_sc_components, dict)
                                    and _sc_components == _v2_cert_components
                                )
                                if not _sc_identity_ok:
                                    # Fallback: match by cert_identity
                                    _sc_cert_id = str(_sc.get("identity", "") or "")
                                    _sc_identity_ok = bool(_sc_cert_id and _sc_cert_id == _v2_cert_identity)
                                if (
                                    _sc_identity_ok
                                    and _sc.get("preflight_ok") is True
                                    and isinstance(_sc_outputs, list)
                                    and len(_sc_outputs) > 0
                                    and all(isinstance(o, str) for o in _sc_outputs)
                                    and len(set(_sc_outputs)) == len(_sc_outputs)
                                    and isinstance(_sc_errors, dict)
                                ):
                                    outputs_to_execute = list(_sc_outputs)
                                    node_errors = copy.deepcopy(_sc_errors) if isinstance(_sc_errors, dict) else {}
                                    _v2_cert_hit = True
                                    _v2_cert_preflight_skip = True
                                    _snapshot_valid = True
                                    _cached_valid = True
                                    _diag_cert_cache_hit = True
                                    _diag_cert_volume_reload_ms = 0.0
                                    _diag_cert_file_read_ms = 0.0
                                    _diag_cert_json_parse_validate_ms = 0.0
                                    _diag_cert_total_ms = _diag_cert_identity_build_ms
                                    _snap_cert_source = "snapshot_memory"
                                    print(
                                        f"[v2.cert] source=snapshot_memory hit=1 "
                                        f"outputs={len(outputs_to_execute)}",
                                        flush=True,
                                    )

                        if not _snapshot_valid:
                            # -- Process-local cache lookup --
                            _cache_key = (self.container_session_id or _V2_CONTAINER_SESSION_ID, _v2_cert_identity)
                            _cached = _V2_CERT_PROCESS_CACHE.get(_cache_key)
                            _cached_valid = False
                            _evict_reason = ""
                            if _cached is not None:
                                # Full revalidation of all stored fields
                                _cached_valid = True

                                # Check schema_version
                                if _cached.get("schema_version") != _V2_CERT_SCHEMA_VERSION:
                                    _cached_valid = False
                                    _evict_reason = "schema_version_mismatch"

                            # Check preflight_ok is True
                            if _cached_valid and _cached.get("preflight_ok") is not True:
                                _cached_valid = False
                                _evict_reason = "preflight_not_ok"

                            # Check identity_components
                            if _cached_valid:
                                _stored_comp = _cached.get("identity_components", {})
                                if not isinstance(_stored_comp, dict) or _stored_comp != _v2_cert_components:
                                    _cached_valid = False
                                    _evict_reason = "component_mismatch"

                            # Check outputs_to_execute is a list of unique strings
                            if _cached_valid:
                                _cached_outputs = _cached.get("outputs_to_execute", [])
                                if not isinstance(_cached_outputs, list):
                                    _cached_valid = False
                                    _evict_reason = "outputs_not_list"
                                else:
                                    _seen_out: set[str] = set()
                                    for _oid in _cached_outputs:
                                        if not isinstance(_oid, str) or _oid in _seen_out:
                                            _cached_valid = False
                                            _evict_reason = "outputs_not_unique_strings"
                                            break
                                        _seen_out.add(_oid)

                            # Check node_errors is a dict
                            if _cached_valid:
                                _cached_errs = _cached.get("node_errors", {})
                                if not isinstance(_cached_errs, dict):
                                    _cached_valid = False
                                    _evict_reason = "node_errors_not_dict"

                            if _cached_valid:
                                # Full cache hit
                                outputs_to_execute = list(_cached["outputs_to_execute"])
                                node_errors = copy.deepcopy(_cached["node_errors"]) if _cached.get("node_errors") else {}
                                _v2_cert_hit = True
                                _v2_cert_preflight_skip = True
                                _diag_cert_cache_hit = True
                                _cached_valid = True
                                # Cache hit uses 0.0 for volume/file/parse timings
                                _diag_cert_volume_reload_ms = 0.0
                                _diag_cert_file_read_ms = 0.0
                                _diag_cert_json_parse_validate_ms = 0.0
                                _diag_cert_total_ms = _diag_cert_identity_build_ms
                                print(
                                    f"[v2.cert] cache_hit=1 identity={_v2_cert_identity[:16]} "
                                    f"outputs={len(outputs_to_execute)}",
                                    flush=True,
                                )
                            else:
                                # Revalidation failure -- evict cache entry and fall through
                                _V2_CERT_PROCESS_CACHE.pop(_cache_key, None)
                                print(
                                    f"[v2.cert] cache_evict reason={_evict_reason} "
                                    f"identity={_v2_cert_identity[:16]}",
                                    flush=True,
                                )

                        if not _cached_valid:
                            # Cache miss or evicted -- read from volume with granular timing
                            trace.emit(
                                "certificate_reload_start",
                                phase="execution",
                                metadata={"cert_identity": _v2_cert_identity[:16]},
                            )
                            _cert_result, _cert_timings = await _read_v2_validation_certificate_async(
                                _v2_cert_identity,
                                expected_components=_v2_cert_components,
                            )
                            _diag_cert_volume_reload_ms = _cert_timings["cert_volume_reload_ms"]
                            _diag_cert_file_read_ms = _cert_timings["cert_file_read_ms"]
                            _diag_cert_json_parse_validate_ms = _cert_timings["cert_json_parse_validate_ms"]
                            _diag_cert_total_ms = round(
                                _diag_cert_identity_build_ms
                                + _diag_cert_volume_reload_ms
                                + _diag_cert_file_read_ms
                                + _diag_cert_json_parse_validate_ms,
                                3,
                            )

                            if _cert_result is not None:
                                outputs_to_execute = _cert_result["outputs_to_execute"]
                                node_errors = _cert_result.get("node_errors", {})
                                _v2_cert_hit = True
                                _v2_cert_preflight_skip = True
                                # Store in process-local cache (deep copies only)
                                _V2_CERT_PROCESS_CACHE[_cache_key] = {
                                    "outputs_to_execute": list(outputs_to_execute),
                                    "node_errors": copy.deepcopy(node_errors) if node_errors else {},
                                    "preflight_ok": True,
                                    "schema_version": _V2_CERT_SCHEMA_VERSION,
                                    "identity_components": dict(_v2_cert_components),
                                }
                                print(
                                    f"[v2.cert] hit=1 preflight_skip=1 identity={_v2_cert_identity[:16]} "
                                    f"outputs={len(outputs_to_execute)}",
                                    flush=True,
                                )
                            else:
                                # Volume read failed or invalid -- do NOT cache
                                print(
                                    f"[v2.cert] hit=0 identity={_v2_cert_identity[:16]}",
                                    flush=True,
                                )

                            trace.emit(
                                "certificate_reload_end",
                                phase="execution",
                                metadata={
                                    "cert_identity": _v2_cert_identity[:16],
                                    "hit": _v2_cert_hit,
                                    "cert_cache_hit": _diag_cert_cache_hit,
                                    "cert_identity_build_ms": _diag_cert_identity_build_ms,
                                    "cert_volume_reload_ms": _diag_cert_volume_reload_ms,
                                    "cert_file_read_ms": _diag_cert_file_read_ms,
                                    "cert_json_parse_validate_ms": _diag_cert_json_parse_validate_ms,
                                    "cert_total_ms": _diag_cert_total_ms,
                                },
                            )

                        # certificate_read_outcome emitted for BOTH local-cache
                        # AND volume paths without claiming a volume reload on cache hit.
                        trace.emit(
                            "certificate_read_outcome",
                            phase="execution",
                            metadata={
                                "cert_identity": _v2_cert_identity[:16],
                                "hit": _v2_cert_hit,
                                "preflight_skip": _v2_cert_preflight_skip,
                                "cert_cache_hit": _diag_cert_cache_hit,
                                "cert_identity_build_ms": _diag_cert_identity_build_ms,
                                "cert_volume_reload_ms": _diag_cert_volume_reload_ms,
                                "cert_file_read_ms": _diag_cert_file_read_ms,
                                "cert_json_parse_validate_ms": _diag_cert_json_parse_validate_ms,
                                "cert_total_ms": _diag_cert_total_ms,
                            },
                        )
                    else:
                        # Not eligible for cert -- preflight+validate will run
                        print(
                            f"[v2.cert] skip reason=not_eligible "
                            f"dep_hash={bool(_v2_dep_hash)} "
                            f"repair_mode={_v2_repair_mode!r} "
                            f"custom_nodes_gen={bool(_v2_custom_nodes_gen)}",
                            flush=True,
                        )

        # ── Dependency preflight identity check (captured at startup/restore) ──
        # Exact match on workflow hash, custom node generation, deployment hash,
        # repair mode, and manifest schema version skips scan/enumeration/
        # fingerprint/manifest build/validation entirely.
        _dep_preflight_skip = False
        _bs_dep = getattr(getattr(self, 'bootstrap', None), 'state', None)
        if (
            _bs_dep is not None
            and _bs_dep.dependency_manifest_identity
            and not _v2_cert_preflight_skip
        ):
            _dep_match = (
                str(_bs_dep.dependency_manifest_workflow_hash) == str(plan.workflow_hash)
                and str(_bs_dep.dependency_manifest_custom_node_generation) == str(_v2_custom_nodes_gen)
                and str(_bs_dep.dependency_manifest_deployment_hash) == str(_V2_DEPLOYMENT_COMBINED_HASH)
                and str(_bs_dep.dependency_manifest_repair_mode) == str(_v2_repair_mode)
                and str(_bs_dep.dependency_manifest_schema_version) == "1"
            )
            if _dep_match:
                _dep_preflight_skip = True
                _diag_legacy_preflight_ms = 0.0
                trace.emit(
                    "preflight_dependency_skip",
                    phase="execution",
                    metadata={
                        "dependency_identity": _bs_dep.dependency_manifest_identity[:16],
                        "wf_hash": str(plan.workflow_hash)[:16],
                    },
                )
                print(
                    f"[v2.dependency_preflight] decision=snapshot_exact_skip "
                    f"scan_called=0 validation_called=0 "
                    f"identity={_bs_dep.dependency_manifest_identity[:16]}",
                    flush=True,
                )
        if not _dep_preflight_skip:
            # Preflight (skip on exact certificate hit)
            if callable(_preflight_fn) and not getattr(api, "_preflight_already_ran", False):
                if _v2_cert_preflight_skip:
                    trace.emit(
                        "preflight_certificate_skip",
                        phase="execution",
                        metadata={
                            "cert_identity": _v2_cert_identity[:16] if _v2_cert_identity else "",
                            "cert_hit": True,
                        },
                    )
                    _diag_legacy_preflight_ms = 0.0
                else:
                    _v2_preflight_ran = True
                    _pf_start = time.perf_counter()
                    trace.emit("preflight_start", phase="execution")
                    await asyncio.to_thread(_preflight_fn, workflow)
                    trace.emit("preflight_end", phase="execution")
                    _diag_legacy_preflight_ms = round((time.perf_counter() - _pf_start) * 1000, 3)
                    # Count actual expensive calls
                    if _bs_dep is not None:
                        _bs_dep.dependency_scan_call_count += 1
                        _bs_dep.dependency_validation_call_count += 1
                        _bs_dep.dependency_manifest_build_call_count += 1

        repair_missing_nodes = getattr(api, "_repair_missing_workflow_nodes", None)
        repair_summary: Any = None
        if callable(repair_missing_nodes):
            trace.emit("missing_node_repair_start", phase="execution")
            repair_summary = repair_missing_nodes(workflow)
            trace.emit(
                "missing_node_repair_end",
                phase="execution",
                metadata={
                    "missing_before": list(repair_summary.get("missing_before", [])) if isinstance(repair_summary, Mapping) else [],
                    "missing_after": list(repair_summary.get("missing_after", [])) if isinstance(repair_summary, Mapping) else [],
                    "blocked": bool(repair_summary.get("blocked_by_mode", False)) if isinstance(repair_summary, Mapping) else False,
                },
            )
            if (
                isinstance(repair_summary, Mapping)
                and repair_summary.get("blocked_by_mode")
                and repair_summary.get("missing_before")
            ):
                raise RuntimeError(
                    "Workflow references missing custom node class(es): "
                    f"{repair_summary['missing_before']}. Runtime repair is disabled."
                )

            # Oracle Gate 2: if a cert skip occurred but the repair reports
            # nodes that were missing before repair, the cached validation
            # result may be stale because repair changed node availability.
            # Only invalidates the request cache -- never mutates the snapshot
            # cert on bootstrap state.
            if (
                _v2_cert_preflight_skip
                and isinstance(repair_summary, Mapping)
                and repair_summary.get("missing_before")
            ):
                print(
                    f"[v2.cert] invalidating cached result after missing-node repair "
                    f"missing_before={repair_summary['missing_before']}",
                    flush=True,
                )
                _v2_cert_hit = False
                _v2_cert_preflight_skip = False
                outputs_to_execute = []
                node_errors = {}
                _cache_key_inval = (self.container_session_id or _V2_CONTAINER_SESSION_ID, _v2_cert_identity)
                _V2_CERT_PROCESS_CACHE.pop(_cache_key_inval, None)
                _v2_preflight_ran = True
                _pf_start2 = time.perf_counter()
                if callable(_preflight_fn):
                    trace.emit("preflight_start", phase="execution")
                    await asyncio.to_thread(_preflight_fn, workflow)
                    trace.emit("preflight_end", phase="execution")
                    if _bs_dep is not None:
                        _bs_dep.dependency_scan_call_count += 1
                        _bs_dep.dependency_validation_call_count += 1
                        _bs_dep.dependency_manifest_build_call_count += 1
                _diag_legacy_preflight_ms = round((time.perf_counter() - _pf_start2) * 1000, 3)

        import execution

        # Prompt validation
        # When preflight was skipped via certificate hit, outputs_to_execute
        # and node_errors are already populated from the stored certificate.
        valid: bool = False
        error: dict[str, Any] | str = {}
        if not _v2_cert_preflight_skip:
            outputs_to_execute = []
            node_errors = {}
        trace.emit(
            "prompt_validation_start",
            phase="execution",
            metadata={
                "prompt_id": prompt_id,
                "cert_hit": _v2_cert_hit,
                "preflight_skip": _v2_cert_preflight_skip,
            },
        )
        if not _v2_cert_preflight_skip:
            _pv_start = time.perf_counter()
            valid, error, outputs_to_execute, node_errors = await execution.validate_prompt(
                prompt_id, workflow, None
            )
            _diag_prompt_validation_ms = round((time.perf_counter() - _pv_start) * 1000, 3)
            _cert_write_eligible = (
                bool(_V2_DEPLOYMENT_COMBINED_HASH)
                and _v2_repair_mode in ("off", "fail_fast", "dev")
                and bool(_v2_custom_nodes_gen)
            )
            if valid and outputs_to_execute and _cert_write_eligible:
                if not _v2_cert_identity:
                    _cert_wf_hash = plan.workflow_hash or ""
                    if _cert_wf_hash and _V2_VALIDATION_CERT_ENABLED:
                        _v2_cert_identity, _v2_cert_components = _compute_v2_cert_identity(
                            _cert_wf_hash,
                            repair_mode=_v2_repair_mode,
                            custom_nodes_generation=_v2_custom_nodes_gen,
                        )
                if _v2_cert_identity:
                    _v2_schedule_cert_write = True
        else:
            valid = True
            error = {}
            _diag_prompt_validation_ms = 0.0
        trace.emit(
            "prompt_validation_end",
            phase="execution",
            metadata={
                "valid": bool(valid),
                "output_count": len(outputs_to_execute or []),
                "node_error_count": len(node_errors or {}),
                "cert_hit": _v2_cert_hit,
                "preflight_skip": _v2_cert_preflight_skip,
                "preflight_ran": _v2_preflight_ran,
                "cert_identity": _v2_cert_identity[:16] if _v2_cert_identity else "",
                # Diagnostic timing fields
                "cert_identity_build_ms": _diag_cert_identity_build_ms,
                "cert_cache_hit": _diag_cert_cache_hit,
                "cert_volume_reload_ms": _diag_cert_volume_reload_ms,
                "cert_file_read_ms": _diag_cert_file_read_ms,
                "cert_json_parse_validate_ms": _diag_cert_json_parse_validate_ms,
                "cert_total_ms": _diag_cert_total_ms,
                "legacy_preflight_ms": _diag_legacy_preflight_ms,
                "prompt_validation_ms": _diag_prompt_validation_ms,
                "certificate_skipped_preflight": _v2_cert_preflight_skip,
                "certificate_skipped_prompt_validation": _v2_cert_preflight_skip,
            },
        )
        if not valid:
            detail = error.get("message", str(error)) if isinstance(error, dict) else str(error)
            raise RuntimeError(f"Workflow validation failed: {detail}")
        trace.emit("pregraph_setup_start", phase="execution", metadata={
            "prompt_id": prompt_id,
        })
        _pregraph_error: str | None = None
        try:
            legacy_options = plan.execution_options.to_legacy_dict()
            production_report = dict(plan.production_report)
            production = legacy_options.get("production", {})
            production_enabled = bool(
                (production.get("enabled") if isinstance(production, Mapping) else False)
                or production_report.get("enabled")
            )
            authorized_node_ids: list[str] = []
            if production_report:
                for key in (
                    "direct_output_rewritten_node_ids",
                    "rgthree_comparer_rewritten_node_ids",
                ):
                    authorized_node_ids.extend(str(value) for value in production_report.get(key, []) or [])
            authorized_node_ids = list(dict.fromkeys(authorized_node_ids))
            register_request = getattr(module, "_register_production_request", None)
            cleanup_request = getattr(module, "_cleanup_production_request", None)
            cleanup_registry = getattr(module, "_cleanup_production_registry", None)
            pop_outputs = getattr(module, "_pop_production_outputs", None)
            if production_enabled and not callable(pop_outputs):
                raise RuntimeError("v2 production output registry is unavailable")

            if production_enabled and callable(register_request):
                trace.emit(
                    "production_registry_setup_start",
                    phase="execution",
                    metadata={"production_enabled": True, "authorized_node_count": len(authorized_node_ids)},
                )
                register_request(
                    prompt_id,
                    {
                        "enabled": True,
                        "prompt_id": prompt_id,
                        "output_format": legacy_options.get("output_format", "original"),
                        "quality": legacy_options.get("quality", 75),
                        "webp_lossless_compression": legacy_options.get(
                            "webp_lossless_compression", "balanced"
                        ),
                        "return_comparison_a": legacy_options.get("return_comparison_a", False),
                        "metadata_mode": production.get("metadata_mode", "none") if isinstance(production, Mapping) else "none",
                        "authorized_node_ids": authorized_node_ids,
                    },
                )
                trace.emit("production_registry_setup_end", phase="execution")

            _begin_profile = getattr(api, "_begin_prompt_profile", None)
            if callable(_begin_profile):
                _begin_profile(workflow, prompt_id, outputs_to_execute)
        except Exception as _pg_exc:
            _pregraph_error = str(_pg_exc)[:200]

        _lane = getattr(self._preload_bridge.coordinator, "mutation_lane", None)
        _lane_acquired = [False]
        _seed_hook_restore: Callable[[], None] | None = None
        started = time.time()
        try:
            # ── CacheDiT request verification ──
            _wf_hash = plan.workflow_hash or ""
            _cd_prep = _CACHEDIT_PREPARED.get(_wf_hash)
            if _cd_prep is not None:
                _bs_state = getattr(getattr(self, 'bootstrap', None), 'state', None)
                _cd_current_unet = (
                    _bs_state.snapshot_loader_outputs.get("unet")
                    if _bs_state is not None else None
                )
                _cd_match = (
                    _cd_current_unet is not None
                    and id(_cd_current_unet) == _cd_prep.get("unet_id")
                    and _wf_hash == _cd_prep.get("workflow_hash", "")
                )
                if _cd_match:
                    print(
                        f"[v2.cachedit_request] decision=reused attach_called=0 "
                        f"wf_hash={_wf_hash[:16]}",
                        flush=True,
                    )
                else:
                    _CACHEDIT_PREPARED.pop(_wf_hash, None)
            # ── RES4LYF request verification ──
            _r4_prep = _RES4LYF_PREPARED.get(_wf_hash)
            if _r4_prep is not None:
                print(
                    f"[v2.res4lyf_request] decision=reused parse_called=0 "
                    f"wf_hash={_wf_hash[:16]}",
                    flush=True,
                )

            trace.emit("executor_reset_start", phase="execution")
            executor.reset()
            trace.emit("executor_reset_end", phase="execution")
            _seed_hook_restore = self._install_snapshot_executor_seed_hook(
                executor, workflow, plan, trace,
            )
            # End pregraph span here â€” before prompt_executor_invoke_start, after
            # all V2-owned setup including executor.reset().
            trace.emit("pregraph_setup_end", phase="execution", metadata={
                "status": "error" if _pregraph_error else "ok",
                "error": _pregraph_error or "",
            })
            if _pregraph_error:
                raise RuntimeError(_pregraph_error)
            execute_async = getattr(executor, "execute_async", None)
            execute_kwargs = {
                "prompt": workflow,
                "prompt_id": prompt_id,
                "extra_data": {"client_id": prompt_id},
                "execute_outputs": outputs_to_execute,
            }
            # â”€â”€ Build node-ID â†’ class_type map â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
            _node_class_map: dict[str, str] = {}
            if isinstance(workflow, dict):
                for _nid, _node in workflow.items():
                    if isinstance(_node, dict):
                        _ct = _node.get("class_type", "")
                        if _ct:
                            _node_class_map[str(_nid)] = str(_ct)
            _first_node_id = str(outputs_to_execute[0]) if outputs_to_execute else ""
            _first_class_type = _node_class_map.get(_first_node_id, "")
            _has_clip_loader = any(ct.startswith("CLIP") for ct in _node_class_map.values())
            _has_text_encode = any("TextEncode" in ct or "CLIPTextEncode" in ct for ct in _node_class_map.values())
            _has_sampler = any("Sampler" in ct or "KSampler" in ct for ct in _node_class_map.values())
            _sampler_node_ids = [
                nid for nid, ct in _node_class_map.items()
                if "Sampler" in ct or "KSampler" in ct
            ]
            # â”€â”€ PromptExecutor internal milestone interception â”€â”€
            # Request-local: wraps executor.add_message (3-arg shape:
            # event, data: dict, broadcast: bool) to capture
            # execution_start and execution_cached timestamps (first
            # occurrences only via setdefault).  Wraps
            # executor.server.send_sync (3-arg shape: event, data: dict,
            # client_id) to capture the first executing node and to
            # classify first model-loader, CLIP/text-encode, and
            # sampler-related nodes.  Both wrappers are restored in
            # the finally block and always delegate with original args.
            _orig_add_message = getattr(executor, "add_message", None)
            _server = getattr(executor, "server", None)
            _orig_send_sync = getattr(_server, "send_sync", None) if _server is not None else None
            _milestones: dict[str, Any] = {}
            _milestone_wrapper_ok = False
            _send_sync_wrapper_ok = False

            if callable(_orig_add_message) and not getattr(_orig_add_message, "_comfy_modal_milestone", False):
                def _milestone_wrapper(*args: Any, **kwargs: Any) -> Any:
                    # Real shape: add_message(event, data: dict, broadcast: bool)
                    event = args[0] if args else kwargs.get("event", "")
                    if event in ("execution_start", "execution_cached"):
                        _milestones.setdefault(event, time.monotonic_ns())
                    return _orig_add_message(*args, **kwargs)
                setattr(_milestone_wrapper, "_comfy_modal_milestone", True)
                executor.add_message = _milestone_wrapper
                _milestone_wrapper_ok = True

            if callable(_orig_send_sync) and not getattr(_orig_send_sync, "_comfy_modal_send_sync", False):
                def _send_sync_wrapper(*args: Any, **kwargs: Any) -> Any:
                    # Real shape: send_sync(event, data: dict, client_id)
                    event = args[0] if args else kwargs.get("event", "")
                    if event == "executing":
                        _event_ns = time.monotonic_ns()
                        _milestones.setdefault(event, _event_ns)
                        _data = args[1] if len(args) > 1 else kwargs.get("data", {})
                        if isinstance(_data, dict):
                            _node = _data.get("node")
                            if _node:
                                _node_str = str(_node)
                                _class_node = _node_class_map.get(str(_node), "")
                                # First executing node
                                if "first_executing_node" not in _milestones:
                                    _milestones["first_executing_node"] = _node_str
                                    _milestones["first_executing_node_class"] = _class_node
                                    _milestones["first_executing_node_ns"] = _event_ns
                                # First model-loader node: *Loader, Checkpoint, UNETLoader,
                                # VAELoader, CLIPLoader/DualCLIPLoader/LoraLoader; exclude CLIPTextEncode
                                _class_lower = _class_node.lower()
                                if ("first_loader_node" not in _milestones
                                        and "textencode" not in _class_lower
                                        and (_class_lower.endswith("loader")
                                             or "checkpointloader" in _class_lower
                                             or "model_loader" in _class_lower)):
                                    _milestones["first_loader_node"] = _node_str
                                    _milestones["first_loader_node_class"] = _class_node
                                    _milestones["first_loader_node_ns"] = _event_ns
                                # First CLIP/text-encode node
                                if ("first_clip_encode_node" not in _milestones
                                        and ("CLIPTextEncode" in _class_node or "TextEncode" in _class_node
                                             or "CLIP" in _class_node)):
                                    _milestones["first_clip_encode_node"] = _node_str
                                    _milestones["first_clip_encode_node_class"] = _class_node
                                    _milestones["first_clip_encode_node_ns"] = _event_ns
                                # VAE decode node tracking: emit start when VAEDecode first
                                # executes, end when the next different node or None executes.
                                if "VAEDecode" in _class_node and "vae_decode_started" not in _milestones:
                                    _milestones["vae_decode_started"] = _event_ns
                                    _milestones["vae_decode_node_id"] = _node_str
                                    trace.emit("vae_decode_start", phase="execution", metadata={
                                        "node_id": _node_str,
                                        "node_class": _class_node,
                                    })
                                # VAE end: when a different node or None executes after VAEDecode
                                # (before or independently of output encode check).
                                if ("vae_decode_started" in _milestones and "vae_decode_ended" not in _milestones
                                        and (_node is None or _node_str != _milestones.get("vae_decode_node_id", ""))):
                                    _milestones["vae_decode_ended"] = _event_ns
                                    _vae_dur = round(
                                        (_event_ns - _milestones["vae_decode_started"]) / 1_000_000, 3
                                    )
                                    trace.emit("vae_decode_end", phase="execution", metadata={
                                        "duration_ms": _vae_dur,
                                    })
                                # Production output encode tracking: ComfyModalProductionOutput
                                # and ComfyModalProductionImageComparerOutput are OUTPUT_NODE=True
                                # nodes that run after VAE decode to encode images to WebP/PNG.
                                # We track their execution as the authoritative output encode.
                                if ("ComfyModalProductionOutput" in _class_node
                                        or "ComfyModalProductionImageComparerOutput" in _class_node):
                                    if "output_encode_started" not in _milestones:
                                        _milestones["output_encode_started"] = _event_ns
                                        trace.emit("output_encode_start", phase="execution", metadata={
                                            "node_id": _node_str,
                                            "node_class": _class_node,
                                        })
                                elif "output_encode_started" in _milestones and "output_encode_ended" not in _milestones:
                                    # End when a different node or None executes after the output node
                                    if _node is None or (
                                        "ComfyModalProductionOutput" not in _class_node
                                        and "ComfyModalProductionImageComparerOutput" not in _class_node
                                    ):
                                        _milestones["output_encode_ended"] = _event_ns
                                        _enc_dur = round(
                                            (_event_ns - _milestones["output_encode_started"]) / 1_000_000, 3
                                        )
                                        trace.emit("output_encode_end", phase="execution", metadata={
                                            "duration_ms": _enc_dur,
                                        })
                                # First sampler-related node
                                if ("first_sampler_node" not in _milestones
                                        and ("Sampler" in _class_node or "KSampler" in _class_node)):
                                    _milestones["first_sampler_node"] = _node_str
                                    _milestones["first_sampler_node_class"] = _class_node
                                    _milestones["first_sampler_node_ns"] = _event_ns
                                    # Acquire mutation lane: blocks until previous
                                    # GPU commit finishes, preventing overlap
                                    # between model GPU commits and sampling.
                                    if _lane is not None and not _lane_acquired[0]:
                                        _blocking_owner = _lane.owner or ""
                                        _lane_wait_start_ns = time.monotonic_ns()
                                        trace.emit("sampler_lane_wait_start", phase="execution", metadata={
                                            "sampler_node_id": _node_str,
                                            "sampler_node_class": _class_node,
                                            "blocking_owner": _blocking_owner,
                                        })
                                        _lane.acquire("sampler")
                                        _milestones["_lane_acquired_mono_ns"] = time.monotonic_ns()
                                        _lane_wait_ms = round((_milestones["_lane_acquired_mono_ns"] - _lane_wait_start_ns) / 1_000_000, 3)
                                        trace.emit("sampler_lane_wait_end", phase="execution", metadata={
                                            "sampler_node_id": _node_str,
                                            "sampler_node_class": _class_node,
                                            "wait_ms": _lane_wait_ms,
                                            "blocking_owner": _blocking_owner,
                                        })
                                        # Bridge lock wait duration into pre-sampler instrumentation state
                                        set_lock_wait_ms(_lane_wait_ms)
                                        _lane_acquired[0] = True
                    elif event in ("sampler_start", "sampling_start", "sampler_stage_start", "progress") and "first_sampler_node" in _milestones:
                        # Diagnostics-only marker: records that a progress-like
                        # event was observed for this request.  This is NOT a
                        # start boundary — authoritative sampling_start/end are
                        # emitted only by the SAMPLER_SAMPLE production wrapper
                        # (see runtime_executor._build_sampling_wrapper).
                        if "sampler_first_progress_ns" not in _milestones:
                            _milestones["sampler_first_progress_ns"] = time.monotonic_ns()
                            _milestones["sampler_first_progress_event"] = event
                    return _orig_send_sync(*args, **kwargs)
                setattr(_send_sync_wrapper, "_comfy_modal_send_sync", True)
                _server.send_sync = _send_sync_wrapper
                _send_sync_wrapper_ok = True

            if not _milestone_wrapper_ok and not _send_sync_wrapper_ok:
                trace.emit("prompt_executor_internal_milestones_unavailable", phase="execution",
                           metadata={"reason": "add_message_and_send_sync_unavailable"})
            elif not _milestone_wrapper_ok:
                trace.emit("prompt_executor_internal_milestones_unavailable", phase="execution",
                           metadata={"reason": "add_message_unavailable"})
            elif not _send_sync_wrapper_ok:
                trace.emit("prompt_executor_internal_milestones_unavailable", phase="execution",
                           metadata={"reason": "send_sync_unavailable"})

            # T5: immediately before prompt executor invocation
            _report_host_memory("peak_execution")
            _t5_wall_ns = int(time.time() * 1_000_000_000)
            _t5_mono_ns = time.monotonic_ns()
            _t5_perf_ns = time.perf_counter_ns()
            _execute_call_ns = _t5_mono_ns  # preserve for milestone calculations
            trace.emit("prompt_executor_invoke_start", phase="execution", metadata={
                "prompt_id": prompt_id,
                "request_id": str(context.trace.request_id if context.trace else ""),
                "t5_wall_ns": _t5_wall_ns,
                "t5_mono_ns": _t5_mono_ns,
                "first_node_id": _first_node_id,
                "first_class_type": _first_class_type,
                "has_clip_loader": _has_clip_loader,
                "has_text_encode": _has_text_encode,
                "has_sampler": _has_sampler,
                "sampler_node_count": len(_sampler_node_ids),
                "total_nodes": len(_node_class_map),
            })
            _wf_hash_token = _V2_WORKFLOW_HASH.set(_wf_hash)
            try:
                with pre_sampler_instrumentation_scope() as _pre_sampler_state:
                    if callable(execute_async):
                        execute_result = execute_async(**execute_kwargs)
                        if inspect.isawaitable(execute_result):
                            await execute_result
                    else:
                        executor.execute(**execute_kwargs)
            finally:
                _V2_WORKFLOW_HASH.reset(_wf_hash_token)
                try:
                    # Restore original add_message
                    if _milestone_wrapper_ok and _orig_add_message is not None:
                        executor.add_message = _orig_add_message
                    # Restore original send_sync
                    if _send_sync_wrapper_ok and _orig_send_sync is not None and _server is not None:
                        _server.send_sync = _orig_send_sync
                finally:
                    # Always emit invoke_end â€” even if restore/release raises
                    _invoke_elapsed_ms = round((time.monotonic_ns() - _execute_call_ns) / 1_000_000, 3)
                    trace.emit("prompt_executor_invoke_end", phase="execution", metadata={
                        "invoke_elapsed_ms": _invoke_elapsed_ms,
                    })

            # â”€â”€ Compute derived milestone intervals â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
            _exec_st_ns = _milestones.get("execution_start") if _milestones else None
            _cached_ns = _milestones.get("execution_cached") if _milestones else None
            _first_ns = _milestones.get("executing") if _milestones else None
            _first_exec_node_id = _milestones.get("first_executing_node", "") if _milestones else ""
            _first_exec_node_class = _milestones.get("first_executing_node_class", "") if _milestones else ""
            _first_loader_node_id = _milestones.get("first_loader_node", "") if _milestones else ""
            _first_clip_encode_node_id = _milestones.get("first_clip_encode_node", "") if _milestones else ""
            _first_sampler_node_id = _milestones.get("first_sampler_node", "") if _milestones else ""
            # Extract monotonic_ns timestamps for node classifications (A)
            _first_exec_node_ns = _milestones.get("first_executing_node_ns") if _milestones else None
            _first_loader_node_ns = _milestones.get("first_loader_node_ns") if _milestones else None
            _first_clip_ns = _milestones.get("first_clip_encode_node_ns") if _milestones else None
            _first_sampler_ns = _milestones.get("first_sampler_node_ns") if _milestones else None
            # Fix 3: authoritative sampling_start from SAMPLER_SAMPLE wrapper (not progress).
            _sampling_start_ns: int | None = None
            for _ev in trace.events:
                if _ev.name == "sampling_start":
                    _sampling_start_ns = _ev.monotonic_ns
                    break
            _first_sampler_stage_event = _milestones.get("sampler_first_progress_event", "") if _milestones else ""
            _exec_st_val = round((_exec_st_ns - _execute_call_ns) / 1_000_000, 3) if _exec_st_ns else None
            _exec_to_cache = round((_cached_ns - _exec_st_ns) / 1_000_000, 3) if _exec_st_ns and _cached_ns else None
            _cache_to_node = round((_first_ns - _cached_ns) / 1_000_000, 3) if _cached_ns and _first_ns else None
            _call_to_cached = round((_cached_ns - _execute_call_ns) / 1_000_000, 3) if _cached_ns else None
            _call_to_first_node = round((_first_ns - _execute_call_ns) / 1_000_000, 3) if _first_ns else None
            # â”€â”€ Node-to-node sub-intervals (B) â”€â”€
            _first_node_to_clip_ms: float | None = None
            _clip_to_sampler_node_ms: float | None = None
            _sampler_node_to_sampler_start_ms: float | None = None
            if _first_exec_node_ns is not None and _first_clip_ns is not None:
                _first_node_to_clip_ms = round((_first_clip_ns - _first_exec_node_ns) / 1_000_000, 3)
            if _first_clip_ns is not None and _first_sampler_ns is not None:
                _clip_to_sampler_node_ms = round((_first_sampler_ns - _first_clip_ns) / 1_000_000, 3)
            if _first_sampler_ns is not None and _sampling_start_ns is not None:
                _sampler_node_to_sampler_start_ms = round((_sampling_start_ns - _first_sampler_ns) / 1_000_000, 3)
                _pre_sampler_state["sampler_node_to_sampler_start_ms"] = _sampler_node_to_sampler_start_ms
            if _milestones:
                trace.emit("prompt_executor_milestones", phase="execution", metadata={
                    "executor_call_to_execution_start_ms": _exec_st_val,
                    "execution_start_to_cached_ms": _exec_to_cache,
                    "cached_to_first_node_ms": _cache_to_node,
                    "executor_call_to_cached_ms": _call_to_cached,
                    "executor_call_to_first_node_ms": _call_to_first_node,
                    "first_executing_node_id": _first_exec_node_id,
                    "first_executing_node_class": _first_exec_node_class,
                    # Loader/CLIP/sampler node classification (B)
                    "first_loader_node_id": _first_loader_node_id,
                    "first_clip_encode_node_id": _first_clip_encode_node_id,
                    "first_sampler_node_id": _first_sampler_node_id,
                    "first_sampler_stage_event": _first_sampler_stage_event,
                    # Node-to-node intervals (B)
                    "first_node_to_clip_ms": _first_node_to_clip_ms,
                    "clip_to_sampler_node_ms": _clip_to_sampler_node_ms,
                    "sampler_node_to_sampler_start_ms": _sampler_node_to_sampler_start_ms,
                    # Raw monotonic-ns timestamps
                    "first_executing_node_monotonic_ns": _first_exec_node_ns,
                    "first_loader_node_monotonic_ns": _first_loader_node_ns,
                    "first_clip_encode_node_monotonic_ns": _first_clip_ns,
                    "first_sampler_node_monotonic_ns": _first_sampler_ns,
                    "sampling_start_monotonic_ns": _sampling_start_ns,
                })

            # â”€â”€ Classify sampler stage from first executing node â”€â”€
            _sampler_stage_status: str = "awaiting_classification"
            if _first_exec_node_class:
                if "Sampler" in _first_exec_node_class or "KSampler" in _first_exec_node_class:
                    _sampler_stage_status = "sampler_active"
                elif "CLIPTextEncode" in _first_exec_node_class or "TextEncode" in _first_exec_node_class:
                    _sampler_stage_status = "text_encoding"
                elif "CLIP" in _first_exec_node_class:
                    _sampler_stage_status = "clip_loading"
                elif "VAE" in _first_exec_node_class:
                    _sampler_stage_status = "vae_loading"
                elif "UNET" in _first_exec_node_class or "UNet" in _first_exec_node_class:
                    _sampler_stage_status = "unet_loading"
                elif "Load" in _first_exec_node_class:
                    _sampler_stage_status = f"loading:{_first_exec_node_class}"
                else:
                    _sampler_stage_status = f"other:{_first_exec_node_class}"

            # â”€â”€ Compute setup intervals from existing trace events â”€â”€â”€â”€â”€â”€â”€
            _cert_ms = self._interval_from_trace(trace, "certificate_reload_start", "certificate_reload_end")
            _preflight_ms = self._interval_from_trace(trace, "preflight_start", "preflight_end")
            _validation_ms = self._interval_from_trace(trace, "prompt_validation_start", "prompt_validation_end")
            _pregraph_ms = self._interval_from_trace(trace, "pregraph_setup_start", "pregraph_setup_end")
            _exec_reset_ms = self._interval_from_trace(trace, "executor_reset_start", "executor_reset_end")
            _sampler_lane_ms = self._interval_from_trace(trace, "sampler_lane_wait_start", "sampler_lane_wait_end")
            _graph_setup_ms = self._interval_from_trace(trace, "graph_execution_start", "prompt_executor_invoke_start")
            _met_start_ms = self._interval_from_trace(trace, "remote_method_entry", "graph_execution_start")
            # Additional setup interval fields (C)
            _runtime_config_ms = self._interval_from_trace(trace, "runtime_config_start", "runtime_config_end")
            _method_entry_to_runtime_ms = self._interval_from_trace(trace, "remote_method_entry", "runtime_config_end")
            _legacy_runtime_ms = self._interval_from_trace(trace, "legacy_runtime_load_start", "legacy_runtime_load_end")
            _preload_check_ms = self._interval_from_trace(trace, "legacy_preload_check_start", "legacy_preload_check_end")
            _repair_ms = self._interval_from_trace(trace, "missing_node_repair_start", "missing_node_repair_end")
            _production_registry_ms = self._interval_from_trace(trace, "production_registry_setup_start", "production_registry_setup_end")
            # Residual before invoke: gap between pregraph_setup_end (or last measured) and invoke_start
            _pregraph_end_event_ns: int | None = None
            for ev in reversed(trace.events):
                if ev.name == "pregraph_setup_end":
                    _pregraph_end_event_ns = ev.monotonic_ns
                    break
            if _pregraph_end_event_ns and _execute_call_ns > _pregraph_end_event_ns:
                _residual_before_invoke = round((_execute_call_ns - _pregraph_end_event_ns) / 1_000_000, 3)
            else:
                _residual_before_invoke = None

            # â”€â”€ Measured children sum (leaf-level, non-overlapping) (C) â”€â”€
            # pregraph_setup_ms includes executor_reset_ms; decompose into
            # pregraph_without_reset + exec_reset (non-overlapping leaves).
            _pregraph_without_reset_ms = (_pregraph_ms - _exec_reset_ms) if _pregraph_ms is not None and _exec_reset_ms is not None else None
            _leaf_setup = [
                _cert_ms, _preflight_ms, _repair_ms, _validation_ms,
                _pregraph_without_reset_ms, _exec_reset_ms,
            ]
            # Include sampler_lane_wait_ms only when lane was acquired
            # (avoids including lane wait in both sampler_lane and residual).
            if _lane_acquired[0]:
                _leaf_setup.append(_sampler_lane_ms)
            _leaf_setup_ms = sum(v for v in _leaf_setup if v is not None)
            # Sampler node â†’ lane acquired â†’ actual stage decompose
            # the single sampler_node_to_sampler_start_ms into two
            # non-overlapping sub-intervals for the leaf sum.
            _lane_acquired_ns = _milestones.get("_lane_acquired_mono_ns") if _milestones else None
            _sampler_node_to_lane_acquired_ms: float | None = None
            _lane_acquired_to_actual_stage_ms: float | None = None
            if _first_sampler_ns is not None and _lane_acquired_ns is not None:
                _sampler_node_to_lane_acquired_ms = round((_lane_acquired_ns - _first_sampler_ns) / 1_000_000, 3)
            if _lane_acquired_ns is not None and _sampling_start_ns is not None:
                _lane_acquired_to_actual_stage_ms = round((_sampling_start_ns - _lane_acquired_ns) / 1_000_000, 3)
            _leaf_milestone = [
                _exec_st_val, _exec_to_cache, _cache_to_node,
                _first_node_to_clip_ms, _clip_to_sampler_node_ms,
                _sampler_node_to_lane_acquired_ms, _lane_acquired_to_actual_stage_ms,
            ]
            _leaf_milestone_ms = sum(v for v in _leaf_milestone if v is not None)
            _total_children_val = _leaf_setup_ms + _leaf_milestone_ms
            _measured_children_ms = round(_total_children_val, 3) if _total_children_val > 0 else None

            # â”€â”€ Build named interval map for overlap diagnostics â”€â”€
            _overlap_interval_map: dict[str, float | None] = {
                "certificate_ms": _cert_ms,
                "preflight_ms": _preflight_ms,
                "repair_ms": _repair_ms,
                "validation_ms": _validation_ms,
                "pregraph_without_reset_ms": _pregraph_without_reset_ms,
                "executor_reset_ms": _exec_reset_ms,
                "sampler_lane_wait_ms": _sampler_lane_ms if _lane_acquired[0] else None,
                "invoke_to_execution_start_ms": _exec_st_val,
                "execution_start_to_cached_ms": _exec_to_cache,
                "cached_to_first_node_ms": _cache_to_node,
                "first_node_to_clip_ms": _first_node_to_clip_ms,
                "clip_to_sampler_node_ms": _clip_to_sampler_node_ms,
                "sampler_node_to_lane_acquired_ms": _sampler_node_to_lane_acquired_ms,
                "lane_acquired_to_actual_stage_ms": _lane_acquired_to_actual_stage_ms,
            }
            _overlapping_intervals: list[str] = [
                name for name, val in _overlap_interval_map.items() if val is not None
            ]

            # â”€â”€ pre_sampler_total_ms from remote_method_entry to first_sampler_stage_ns (C) â”€â”€
            _remote_method_entry_ns = None
            for ev in trace.events:
                if ev.name == "remote_method_entry":
                    _remote_method_entry_ns = ev.monotonic_ns
                    break
            if _remote_method_entry_ns is not None and _sampling_start_ns is not None:
                _pre_sampler_total_ms = round((_sampling_start_ns - _remote_method_entry_ns) / 1_000_000, 3)
            else:
                _pre_sampler_total_ms = None
            if _pre_sampler_total_ms is not None:
                if _measured_children_ms is not None and _measured_children_ms > _pre_sampler_total_ms:
                    _reconciliation_status = "overlap_error"
                    _residual_ms = round(_pre_sampler_total_ms - _measured_children_ms, 3)
                else:
                    _reconciliation_status = "ok"
                    _residual_ms = round(_pre_sampler_total_ms - (_measured_children_ms or 0.0), 3)
            else:
                _reconciliation_status = "absent_total"
                _residual_ms = None

            # â”€â”€ Gather identity metadata for pre_sampler_stages event and print (D) â”€â”€
            _ps_prompt_id = prompt_id
            _ps_identity = _capture_remote_identity()
            _ps_modal_input_id = _ps_identity.get("modal_input_id", "absent")
            _ps_modal_task_id = _ps_identity.get("container_task_id", "absent")
            _ps_host_info = _capture_host_info()
            _ps_pid = _ps_host_info.get("pid", os.getpid())
            _ps_hostname = _ps_host_info.get("hostname", "absent")
            _ps_boot_id = _ps_host_info.get("boot_id", "absent")
            _ps_restored_id_actual = getattr(self, "_restored_instance_id", "")
            _ps_restore_session = (self._restore_timing or {}).get("restore_session_id", "") or "absent"
            _ps_restored_instance_id = _ps_restored_id_actual or "absent"
            _ps_cid = self.container_session_id or _V2_CONTAINER_SESSION_ID or "absent"

            # Always emit pre_sampler_stages â€” even when milestones absent (C/D)
            trace.emit("pre_sampler_stages", phase="execution", metadata={
                # Setup intervals from trace events
                "method_entry_to_graph_start_ms": _met_start_ms,
                "graph_setup_ms": _graph_setup_ms,
                "certificate_ms": _cert_ms,
                "preflight_ms": _preflight_ms,
                "validation_ms": _validation_ms,
                "runtime_configuration_ms": _runtime_config_ms,
                "method_entry_to_runtime_configuration_ms": _method_entry_to_runtime_ms,
                "legacy_runtime_resolution_ms": _legacy_runtime_ms,
                "preload_check_ms": _preload_check_ms,
                "missing_node_repair_ms": _repair_ms,
                "production_registry_setup_ms": _production_registry_ms,
                "production_registry_profile_setup_ms": _production_registry_ms,
                "pregraph_setup_ms": _pregraph_ms,
                "executor_reset_ms": _exec_reset_ms,
                "sampler_lane_wait_ms": _sampler_lane_ms,
                "residual_before_invoke_ms": _residual_before_invoke,
                # Internal milestone intervals (from wrapper captures)
                "invoke_to_execution_start_ms": _exec_st_val,
                "execution_start_to_cached_ms": _exec_to_cache,
                "cached_to_first_node_ms": _cache_to_node,
                "first_node_to_clip_ms": _first_node_to_clip_ms,
                "clip_to_sampler_node_ms": _clip_to_sampler_node_ms,
                "sampler_node_to_lane_acquired_ms": _sampler_node_to_lane_acquired_ms,
                "lane_acquired_to_actual_stage_ms": _lane_acquired_to_actual_stage_ms,
                "sampler_node_to_sampler_start_ms": _sampler_node_to_sampler_start_ms,
                # Totals and reconciliation (C)
                "pre_sampler_total_ms": _pre_sampler_total_ms,
                "measured_children_ms": _measured_children_ms,
                "residual_ms": _residual_ms,
                "reconciliation_status": _reconciliation_status,
                "overlapping_intervals": _overlapping_intervals,
                "lane_acquired": _lane_acquired[0],
                # Node classification (B)
                "total_nodes": len(_node_class_map),
                "first_output_node_id": _first_node_id,
                "first_output_class_type": _first_class_type,
                "first_executing_node_id": _first_exec_node_id,
                "first_executing_node_class": _first_exec_node_class,
                "first_loader_node_id": _first_loader_node_id,
                "first_loader_node_class": _milestones.get("first_loader_node_class", "") if _milestones else "",
                "first_clip_encode_node_id": _first_clip_encode_node_id,
                "first_clip_encode_node_class": _milestones.get("first_clip_encode_node_class", "") if _milestones else "",
                "first_sampler_node_id": _first_sampler_node_id,
                "first_sampler_node_class": _milestones.get("first_sampler_node_class", "") if _milestones else "",
                "first_sampler_stage_event": _first_sampler_stage_event,
                # Raw monotonic-ns timestamps
                "first_executing_node_monotonic_ns": _first_exec_node_ns,
                "first_loader_node_monotonic_ns": _first_loader_node_ns,
                "first_clip_encode_node_monotonic_ns": _first_clip_ns,
                "first_sampler_node_monotonic_ns": _first_sampler_ns,
                "sampling_start_monotonic_ns": _sampling_start_ns,
                "sampler_stage_status": _sampler_stage_status,
                "has_clip_loader": _has_clip_loader,
                "has_text_encode": _has_text_encode,
                "has_sampler": _has_sampler,
                "sampler_node_ids": ",".join(_sampler_node_ids) if _sampler_node_ids else "",
                "sampler_node_count": len(_sampler_node_ids),
                # Wrapper availability
                "add_message_available": _milestone_wrapper_ok,
                "send_sync_available": _send_sync_wrapper_ok,
                # Identity metadata (D)
                "request_id": _ps_prompt_id,
                "modal_input_id": _ps_modal_input_id,
                "modal_task_id": _ps_modal_task_id,
                "container_task_id": _ps_modal_task_id,
                "pid": _ps_pid,
                "boot_id": _ps_boot_id,
                "hostname": _ps_hostname,
                "restored_instance_id": _ps_restored_instance_id,
                "restore_session_id": _ps_restore_session,
                "container_session_id": _ps_cid,
            })
            # â”€â”€ One-line [v2.pre_sampler_stages] summary (always emitted) â”€â”€â”€
            print(
                f"[v2.pre_sampler_stages] "
                f"request_id={_ps_prompt_id} "
                f"restored_instance_id={_ps_restored_instance_id} "
                f"restore_session_id={_ps_restore_session} "
                f"container_session_id={_ps_cid} "
                f"modal_input_id={_ps_modal_input_id} "
                f"modal_task_id={_ps_modal_task_id} "
                f"pid={_ps_pid} "
                f"boot_id={_ps_boot_id} "
                f"hostname={_ps_hostname} "
                f"total_nodes={len(_node_class_map)} "
                f"first_output_node={_first_node_id}:{_first_class_type} "
                f"first_executing_node={_first_exec_node_id}:{_first_exec_node_class} "
                f"sampler_stage_status={_sampler_stage_status} "
                f"method_entry_to_graph_start_ms={self._fmt_or_absent(_met_start_ms)} "
                f"graph_setup_ms={self._fmt_or_absent(_graph_setup_ms)} "
                f"certificate_ms={self._fmt_or_absent(_cert_ms)} "
                f"cert_identity_build_ms={self._fmt_or_absent(_diag_cert_identity_build_ms)} "
                f"cert_cache_hit={int(_diag_cert_cache_hit)} "
                f"cert_volume_reload_ms={self._fmt_or_absent(_diag_cert_volume_reload_ms)} "
                f"cert_file_read_ms={self._fmt_or_absent(_diag_cert_file_read_ms)} "
                f"cert_json_parse_validate_ms={self._fmt_or_absent(_diag_cert_json_parse_validate_ms)} "
                f"cert_total_ms={self._fmt_or_absent(_diag_cert_total_ms)} "
                f"legacy_preflight_ms={self._fmt_or_absent(_diag_legacy_preflight_ms)} "
                f"prompt_validation_ms={self._fmt_or_absent(_diag_prompt_validation_ms)} "
                f"certificate_skipped_preflight={int(_v2_cert_preflight_skip)} "
                f"certificate_skipped_prompt_validation={int(_v2_cert_preflight_skip)} "
                f"preflight_ms={self._fmt_or_absent(_preflight_ms)} "
                f"validation_ms={self._fmt_or_absent(_validation_ms)} "
                f"missing_node_repair_ms={self._fmt_or_absent(_repair_ms)} "
                f"production_registry_setup_ms={self._fmt_or_absent(_production_registry_ms)} "
                f"production_registry_profile_setup_ms={self._fmt_or_absent(_production_registry_ms)} "
                f"pregraph_setup_ms={self._fmt_or_absent(_pregraph_ms)} "
                f"executor_reset_ms={self._fmt_or_absent(_exec_reset_ms)} "
                f"sampler_lane_wait_ms={self._fmt_or_absent(_sampler_lane_ms)} "
                f"residual_before_invoke_ms={self._fmt_or_absent(_residual_before_invoke)} "
                f"method_entry_to_runtime_configuration_ms={self._fmt_or_absent(_method_entry_to_runtime_ms)} "
                f"call_to_exec_start_ms={self._fmt_or_absent(_exec_st_val)} "
                f"exec_start_to_cached_ms={self._fmt_or_absent(_exec_to_cache)} "
                f"cached_to_first_executing_ms={self._fmt_or_absent(_cache_to_node)} "
                f"call_to_cached_ms={self._fmt_or_absent(_call_to_cached)} "
                f"call_to_first_node_ms={self._fmt_or_absent(_call_to_first_node)} "
                f"first_node_to_clip_ms={self._fmt_or_absent(_first_node_to_clip_ms)} "
                f"clip_to_sampler_node_ms={self._fmt_or_absent(_clip_to_sampler_node_ms)} "
                f"sampler_node_to_sampler_start_ms={self._fmt_or_absent(_sampler_node_to_sampler_start_ms)} "
                f"sampler_node_to_lane_acquired_ms={self._fmt_or_absent(_sampler_node_to_lane_acquired_ms)} "
                f"lane_acquired_to_actual_stage_ms={self._fmt_or_absent(_lane_acquired_to_actual_stage_ms)} "
                f"pre_sampler_total_ms={self._fmt_or_absent(_pre_sampler_total_ms)} "
                f"measured_children_ms={self._fmt_or_absent(_measured_children_ms)} "
                f"residual_ms={self._fmt_or_absent(_residual_ms)} "
                f"reconciliation_status={_reconciliation_status} "
                f"add_message={_milestone_wrapper_ok} "
                f"send_sync={_send_sync_wrapper_ok} "
                f"has_sampler={_has_sampler} "
                f"sampler_count={len(_sampler_node_ids)} "
                f"lane_acquired={_lane_acquired[0]}",
                flush=True,
            )
            trace.emit(
                "prompt_executor_end",
                phase="execution",
                metadata={"elapsed_ms": round((time.time() - started) * 1000.0, 3)},
            )
            if context.cancelled and context.cancelled():
                raise RuntimeError("execution cancelled after PromptExecutor completion")
            if getattr(executor, "success", True) is False:
                raise RuntimeError(self._executor_error_message(executor))

            trace.emit("output_collect_start", phase="output")
            registry = pop_outputs(prompt_id) if production_enabled and callable(pop_outputs) else {}
            if not isinstance(registry, Mapping):
                registry = {}
            history_result = getattr(executor, "history_result", None)
            history = {prompt_id: history_result} if isinstance(history_result, dict) else {}
            output_dir = Path("/root/comfy/ComfyUI/output")
            trace.emit(
                "output_chain_start",
                phase="output",
                metadata={"prompt_id": prompt_id},
            )
            chain = build_default_chain(
                registry=registry,
                history=history,
                materials_dir=str(output_dir) if output_dir.is_dir() else "",
            )
            attempts = run_strategy_chain(
                chain,
                prompt_id=prompt_id,
                output_node_ids=tuple(plan.output_node_ids),
                materials_dir=str(output_dir) if output_dir.is_dir() else "",
                request_start_boundary=started,
            )
            trace.emit(
                "output_chain_end",
                phase="output",
                metadata={
                    "prompt_id": prompt_id,
                    "attempts": len(attempts),
                    "successful": sum(1 for a in attempts if a.success),
                },
            )
            selected_index = next(
                (index for index, attempt in enumerate(attempts) if attempt.success),
                None,
            )
            selected = attempts[selected_index] if selected_index is not None else None
            if selected is None:
                if production_enabled:
                    raise RuntimeError("v2 production execution produced no materializable output")
                selected = Attempt(strategy="none", success=False, error="no output")
            output_format = str(legacy_options.get("output_format", "original") or "original")
            if selected.success and selected.strategy != "direct_output_sink" and output_format != "original":
                trace.emit(
                    "output_conversion_start",
                    phase="output",
                    metadata={
                        "format": output_format,
                        "items": len(selected.items),
                    },
                )
                try:
                    converted = convert_output_items(
                        list(selected.items),
                        output_format=output_format,
                        quality=int(legacy_options.get("quality", 75) or 75),
                        webp_lossless_compression=str(
                            legacy_options.get("webp_lossless_compression", "balanced")
                        ),
                    )
                except ConversionFailedError as exc:
                    # The registry path is already encoded by the production
                    # node. For history/filesystem compatibility, retain the
                    # original bytes when a requested conversion cannot run.
                    selected = Attempt(
                        strategy=selected.strategy,
                        success=selected.success,
                        items=selected.items,
                        total_items=selected.total_items,
                        total_raw_bytes=selected.total_raw_bytes,
                        total_base64_bytes=selected.total_base64_bytes,
                        total_json_result_bytes=selected.total_json_result_bytes,
                        total_conversion_time_ms=selected.total_conversion_time_ms,
                        error=str(exc),
                        metrics={**dict(selected.metrics), "conversion_fallback": True},
                    )
                else:
                    selected = Attempt(
                        strategy=selected.strategy,
                        success=bool(converted.items),
                        items=tuple(converted.items),
                        total_items=len(converted.items),
                        total_raw_bytes=converted.total_raw_bytes,
                        total_base64_bytes=converted.total_base64_bytes,
                        total_json_result_bytes=converted.total_json_result_bytes,
                        total_conversion_time_ms=converted.total_conversion_time_ms,
                        error="" if converted.items else "output conversion produced no items",
                        metrics={**dict(selected.metrics), "converted": True},
                    )
                if selected_index is not None:
                    attempts[selected_index] = selected
                _conv_ok = selected.success and selected.strategy != "direct_output_sink" and output_format != "original"
                trace.emit(
                    "output_conversion_end",
                    phase="output",
                    metadata={
                        "format": output_format,
                        "success": _conv_ok,
                        "error": selected.error if not _conv_ok else "",
                        "conversion_time_ms": round(getattr(selected, "total_conversion_time_ms", 0), 3),
                        "fallback": bool(
                            selected.metrics.get("conversion_fallback")
                        ) if hasattr(selected, "metrics") and isinstance(selected.metrics, Mapping) else False,
                    },
                )
            # If output_encode_started but output_encode_ended not set (final
            # output node in graph), emit output_encode_end now at persist boundary.
            if _milestones and "output_encode_started" in _milestones and "output_encode_ended" not in _milestones:
                _milestones["output_encode_ended"] = time.monotonic_ns()
                _enc_dur = round(
                    (_milestones["output_encode_ended"] - _milestones["output_encode_started"]) / 1_000_000, 3
                ) if _milestones.get("output_encode_started") else 0.0
                trace.emit("output_encode_end", phase="execution", metadata={
                    "duration_ms": _enc_dur,
                })
            # output_persist_start/end: wraps actual volume persistence + descriptor
            # construction.  Distinguished from output_encode_start/end which wrap
            # the actual image encoding inside the executor (ComfyModalProductionOutput).
            trace.emit("output_persist_start", phase="output", metadata={
                "prompt_id": prompt_id,
                "strategy": selected.strategy,
                "items": selected.total_items,
            })
            _descriptor_start_mono_ns = time.monotonic_ns()
            selected, _asset_commit_task, _asset_diag = await self._persist_output_assets(selected)
            if selected_index is not None:
                attempts[selected_index] = selected
            if _asset_commit_task is not None:
                await asyncio.sleep(0)
            with base64_counting_scope(selected):
                result = attempt_to_descriptor_result(
                selected,
                generation=_snapshot_target_fingerprint(),
                legacy_data=False,
            )
            _descriptor_end_mono_ns = time.monotonic_ns()
            trace.emit("output_persist_end", phase="output", metadata={
                "duration_ms": round((_descriptor_end_mono_ns - _descriptor_start_mono_ns) / 1_000_000, 3),
                "items": selected.total_items,
                "hashes": selected.output_hash_count,
                "serialized_bytes": result.get("output_diagnostics", {}).get("serialized_result_bytes", 0),
            })
            if _asset_commit_task is not None:
                _asset_commit_diag = await _asset_commit_task
                _asset_diag.update(_asset_commit_diag)
            # Compute overlap between commit and descriptor build intervals
            _commit_start = _asset_diag.get("commit_start_mono_ns", 0)
            _commit_end = _asset_diag.get("commit_end_mono_ns", 0)
            _overlap_ns = max(0,
                min(_commit_end, _descriptor_end_mono_ns) -
                max(_commit_start, _descriptor_start_mono_ns)
            ) if _commit_start and _commit_end else 0
            result["output_diagnostics"] = {
                "output_asset_write_ms": _asset_diag.get("write_ms", 0.0),
                "output_volume_commit_ms": _asset_diag.get("commit_ms", 0.0),
                "output_commit_overlap_ms": round(_overlap_ns / 1_000_000, 3),
                "output_hash_count": selected.output_hash_count,
                "base64_encode_count": selected.base64_encode_count,
                "base64_decode_count": selected.base64_decode_count,
                "serialized_result_bytes": 0,
            }
            result["output_attempts"] = [
                {
                    "strategy": attempt.strategy,
                    "success": attempt.success,
                    "total_items": attempt.total_items,
                    "total_raw_bytes": attempt.total_raw_bytes,
                    "total_base64_bytes": attempt.total_base64_bytes,
                    "error": attempt.error,
                    "metrics": dict(attempt.metrics),
                }
                for attempt in attempts
            ]
            result["_registry_used"] = bool(attempts and attempts[0].success)
            result["_registry_entries"] = attempts[0].total_items if attempts else 0

            # â”€â”€ Phase 6: measure serialized result payload size â”€â”€â”€â”€â”€â”€â”€â”€
            payload_bytes = _measure_json_bytes(result)
            selected = dataclasses.replace(
                selected,
                serialized_result_bytes=payload_bytes,
                metrics=MappingProxyType({**dict(selected.metrics), "serialized_result_bytes": payload_bytes}),
            )
            if selected_index is not None:
                result["output_attempts"][selected_index]["metrics"]["serialized_result_bytes"] = payload_bytes
            if isinstance(result.get("output_diagnostics"), dict):
                result["output_diagnostics"]["serialized_result_bytes"] = payload_bytes
            # Exactly one per-request output summary (after serialized_result_bytes is real)
            print(
                f"[v2.output] "
                f"hashes={result['output_diagnostics']['output_hash_count']} "
                f"base64_encode={result['output_diagnostics']['base64_encode_count']} "
                f"base64_decode={result['output_diagnostics']['base64_decode_count']} "
                f"commit_ms={result['output_diagnostics']['output_volume_commit_ms']} "
                f"overlap_ms={result['output_diagnostics']['output_commit_overlap_ms']} "
                f"serialized_bytes={result['output_diagnostics']['serialized_result_bytes']}",
                flush=True,
            )

            trace.emit(
                "output_collect_end",
                phase="output",
                metadata={
                    "strategy": selected.strategy,
                    "items": selected.total_items,
                    "raw_bytes": selected.total_raw_bytes,
                    "serialized_result_bytes": payload_bytes,
                },
            )

            _stage_windows = getattr(api, "_stage_windows", None)
            _sampler_stage_start_perf_ns: int | None = None
            if _stage_windows:
                _stages: dict[str, float | int] = {}
                for _stage, _sk, _ek in _V2_STAGE_MAP:
                    _fields = _stage_windows.get(_stage, {})
                    _s = _fields.get("start")
                    _e = _fields.get("end")
                    if _s is not None:
                        _stages[_sk] = _s
                    if _e is not None:
                        _stages[_ek] = _e
                    if _stage == "sampler":
                        _stage_perf_ns = _fields.get("start_perf_ns")
                        if isinstance(_stage_perf_ns, int):
                            _sampler_stage_start_perf_ns = _stage_perf_ns
                            _stages["sampler_stage_start_perf_ns"] = _stage_perf_ns
                if _stages:
                    result["_stage_timings"] = _stages

            result["_v2_critical_path_data"] = {
                "executor_invoke_mono_ns": _t5_mono_ns,
                "executor_invoke_perf_ns": _t5_perf_ns,
                "first_node_enter_perf_ns": _pre_sampler_state.get("first_node_enter_perf_ns"),
                "sampler_node_enter_perf_ns": _pre_sampler_state.get("sampler_node_enter_perf_ns"),
                "sampler_stage_start_perf_ns": _sampler_stage_start_perf_ns,
                "pre_sampler_unattributed_ms": _pre_sampler_state.get("pre_sampler_unattributed_ms"),
                # Pre-computed authoritative value from milestone calculation;
                # _build_v2_critical_path reads this directly rather than
                # recalculating from sampler_stage_start_perf_ns (T3).
                "sampler_node_to_sampler_start_ms": _pre_sampler_state.get("sampler_node_to_sampler_start_ms"),
            }
            # Attach structured pre-sampler report from live instrumentation
            _attach_structured_report(result, _pre_sampler_state)

            # â”€â”€ Write validation certificate after successful execution â”€â”€
            # Schema v2 certs include preflight_ok=True to attest that
            # deterministic preflight completed successfully for this identity.
            # Only write when preflight actually ran (not on cert skip).
            # Also store on BootstrapState for snapshot persistence.
            if _v2_schedule_cert_write and _v2_preflight_ran:
                await _write_v2_validation_certificate(
                    _v2_cert_identity,
                    outputs_to_execute,
                    node_errors,
                    components=_v2_cert_components,
                    preflight_ok=True,
                )


            return result
        finally:
            if _seed_hook_restore is not None:
                _seed_hook_restore()
            # Release sampler lane if acquired during execution.
            # Must happen before production cleanup to ensure GPU
            # commit lane is free before any post-execution work.
            if _lane is not None and _lane_acquired[0]:
                _lane.release("sampler")
            if production_enabled:
                trace.emit("production_cleanup_start", phase="output")
            if production_enabled and callable(cleanup_request):
                cleanup_request(prompt_id)
            if production_enabled and callable(cleanup_registry):
                cleanup_registry(prompt_id)
            if production_enabled:
                trace.emit("production_cleanup_end", phase="output")

    @staticmethod
    def _executor_error_message(executor: Any) -> str:
        messages = getattr(executor, "status_messages", [])
        errors = [
            payload.get("exception_message", str(payload))
            for event, payload in messages
            if event == "execution_error" and isinstance(payload, dict)
        ]
        return "; ".join(errors) or "ComfyUI PromptExecutor failed"

    def _install_snapshot_executor_seed_hook(
        self,
        executor: Any,
        workflow: Mapping[str, Any],
        plan: ExecutionPlan,
        trace: RuntimeTrace,
    ) -> Callable[[], None] | None:
        state = getattr(getattr(self, "bootstrap", None), "state", None)
        if state is None or not state.snapshot_loader_outputs:
            return None
        # Derive request model identity from workflow (not plan.model_key).
        # Compare against complete snapshot plan.model_key from
        # self._cpu_snapshot_models — no partial ModelRestoreKey reconstruction.
        _wf = _thaw(workflow)
        request_model_key = derive_model_key(_wf)
        _snap_models = getattr(self, "_cpu_snapshot_models", None)
        _snap_model_key = getattr(_snap_models, "model_key", None) if _snap_models is not None else None
        _snap_spec = getattr(_snap_models, "model_spec", None) if _snap_models is not None else None
        _request_model_spec = build_restore_model_spec(
            _wf, dict(plan.model_stack) if hasattr(plan, "model_stack") else {}
        )
        caches = getattr(executor, "caches", None)
        outputs_cache = getattr(caches, "outputs", None) if caches is not None else None
        original_set_prompt = getattr(outputs_cache, "set_prompt", None)
        if not callable(original_set_prompt):
            return None
        # Build candidate loader node list with class types
        _loader_types_allowed = {
            "UNETLoader", "CLIPLoader", "DualCLIPLoader",
            "VAELoader", "CheckpointLoader", "CheckpointLoaderSimple",
        }
        _candidate_nodes: list[tuple[str, str]] = []
        _class_type_map: dict[str, str] = {}
        for _nid, _node in _wf.items():
            if isinstance(_node, Mapping):
                _ct = str(_node.get("class_type", ""))
                if _ct in _loader_types_allowed:
                    _candidate_nodes.append((str(_nid), _ct))
                    _class_type_map[str(_nid)] = _ct
        if not _candidate_nodes:
            return None

        # Build actual node outputs per role from snapshot models.
        # UNET=(model,), CLIP=(clip,), DualCLIP→one CLIP, VAE only real,
        # checkpoint=(model,clip,vae) only all present.
        _snap_unet = state.snapshot_loader_outputs.get("unet")
        _snap_clip = state.snapshot_loader_outputs.get("clip")
        _snap_vae = state.snapshot_loader_outputs.get("vae")
        _loader_outputs: dict[str, Any] = {}
        for _nid, _ct in _class_type_map.items():
            if _ct == "UNETLoader" and _snap_unet is not None:
                _loader_outputs[_nid] = _snap_unet
            elif _ct in ("CLIPLoader", "DualCLIPLoader") and _snap_clip is not None:
                _loader_outputs[_nid] = _snap_clip
            elif _ct == "VAELoader" and _snap_vae is not None:
                _vae = _snap_vae
                _vae_class = type(_vae).__name__ if _vae is not None else ""
                if _vae_class == "VAE":
                    _loader_outputs[_nid] = _vae
            elif _ct in ("CheckpointLoader", "CheckpointLoaderSimple"):
                if _snap_unet is not None and _snap_clip is not None and _snap_vae is not None:
                    _loader_outputs[_nid] = (_snap_unet, _snap_clip, _snap_vae)

        async def seeded_set_prompt(*args: Any, **kwargs: Any) -> Any:
            # Let set_prompt initialize cache keys
            result = await original_set_prompt(*args, **kwargs)
            trace.emit(
                "executor_seed_apply_start",
                phase="execution",
                metadata={"loader_count": len(_candidate_nodes), "workflow_hash": plan.workflow_hash},
            )
            # Build authoritative model spec from complete snapshot identities
            _wf_hash = plan.workflow_hash or ""
            _cn_gen = state.snapshot_custom_node_generation or ""
            _dep_hash = _V2_DEPLOYMENT_COMBINED_HASH or getattr(state, "deployment_combined_hash", "")
            _seeded = await state.seed_loader_cache_signatures(
                executor=executor,
                loader_node_ids=[nid for nid, _ in _candidate_nodes],
                loader_node_class_types=_class_type_map,
                loader_outputs=_loader_outputs,
                request_model_key=request_model_key.to_dict(),
                snapshot_model_key=_snap_model_key.to_dict() if _snap_model_key is not None else {},
                request_model_spec=_request_model_spec,
                snapshot_model_spec=_thaw(_snap_spec) if _snap_spec is not None else {},
                workflow_hash=_wf_hash,
                custom_node_generation=_cn_gen,
                deployment_combined_hash=_dep_hash,
                allow_cache=True,
            )
            # Print every candidate exactly once with canonical format.
            # Format: [v2.executor_seed] node=<id> class=<class> role=<unet|clip|vae>
            #   decision=<seeded|missing_snapshot_output|identity_mismatch|unsupported>
            #   expected_identity=<short hash> actual_identity=<short hash>
            #   mismatch_fields=<exact comma-separated fields or none>
            for _node_id, _outcome in _seeded.items():
                _ct = _class_type_map.get(_node_id, "?")
                _d = _outcome.get("decision", "?") if isinstance(_outcome, dict) else str(_outcome)
                _r = _outcome.get("role", "?") if isinstance(_outcome, dict) else "?"
                _ei = _outcome.get("expected_identity", "") if isinstance(_outcome, dict) else ""
                _ai = _outcome.get("actual_identity", "") if isinstance(_outcome, dict) else ""
                _mf = _outcome.get("mismatch_fields", "none") if isinstance(_outcome, dict) else "none"
                print(
                    f"[v2.executor_seed] node={_node_id} "
                    f"class={_ct} role={_r} decision={_d} "
                    f"expected_identity={_ei} actual_identity={_ai} "
                    f"mismatch_fields={_mf}",
                    flush=True,
                )
            trace.emit(
                "executor_loader_cache_seed_end",
                phase="execution",
                metadata={"diagnostics": _seeded},
            )
            trace.emit(
                "executor_seed_apply_end",
                phase="execution",
                metadata={
                    "seeded": sum(
                        1 for v in _seeded.values()
                        if isinstance(v, dict) and v.get("decision") == "seeded"
                    ),
                },
            )
            return result

        outputs_cache.set_prompt = seeded_set_prompt

        def restore_hook() -> None:
            outputs_cache.set_prompt = original_set_prompt

        return restore_hook

    @staticmethod
    def _attempt_to_result(attempt: Attempt) -> dict[str, Any]:
        outputs: dict[str, dict[str, list[dict[str, Any]]]] = {}
        images: list[dict[str, Any]] = []
        videos: list[dict[str, Any]] = []
        for item in attempt.items:
            output_key = item.output_key or ("gifs" if item.animated else "images")
            data = item.base64_data or base64.b64encode(item.raw_bytes).decode("ascii")
            entry = {
                "filename": item.filename,
                "data": data,
                "node_id": item.node_id,
                "output_key": output_key,
                "comparison_side": item.comparison_side,
                "mime_type": item.mime_type,
                "file_ext": item.file_ext,
                "width": item.width,
                "height": item.height,
                "output_index": item.output_index,
                "format": item.format,
            }
            outputs.setdefault(item.node_id, {}).setdefault(output_key, []).append(entry)
            if item.animated or output_key in {"gifs", "videos"}:
                videos.append(entry)
            else:
                images.append(entry)
        return {"images": images, "videos": videos, "outputs": outputs}

    async def _persist_output_assets(
        self,
        attempt: Attempt,
    ) -> tuple[Attempt, asyncio.Task[Any] | None, dict[str, Any]]:
        root = Path(RUNTIME_STATE_PATH, "output_assets")
        root.mkdir(parents=True, exist_ok=True)
        persisted = []
        wrote = False
        write_start = time.monotonic()
        for item in attempt.items:
            raw = item.raw_bytes
            if not raw:
                persisted.append(item)
                continue
            digest = item.content_sha256 or (
                item.conversion_meta.hash_of_raw
                if item.conversion_meta is not None else ""
            )
            if not digest:
                digest = hashlib.sha256(raw).hexdigest()
                item = dataclasses.replace(item, content_sha256=digest)
            ext = item.file_ext if item.file_ext in {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"} else ".bin"
            relative_path = f"output_assets/{digest}{ext}"
            target = Path(RUNTIME_STATE_PATH, relative_path)
            if not target.exists():
                temp = target.with_name(f".{target.name}.{uuid.uuid4().hex}.tmp")
                try:
                    temp.write_bytes(raw)
                    os.replace(temp, target)
                    wrote = True
                finally:
                    try:
                        temp.unlink(missing_ok=True)
                    except OSError:
                        pass
            persisted.append(dataclasses.replace(item, path=relative_path))
        write_end_ns = time.monotonic_ns()
        diag: dict[str, Any] = {
            "write_ms": round((time.monotonic() - write_start) * 1000, 3),
            "write_end_mono_ns": write_end_ns,
            "commit_start_mono_ns": 0,
            "commit_end_mono_ns": 0,
            "commit_ms": 0.0,
            "overlap_ms": 0.0,
            "files_written": int(wrote),
            "commit_error": "",
        }
        if not wrote:
            return dataclasses.replace(attempt, items=tuple(persisted)), None, diag
        volume = globals().get("_MODAL_RESOURCES", {}).get("runtime_state_volume")
        commit = getattr(volume, "commit", None)
        commit_aio = getattr(commit, "aio", None) if commit is not None else None
        if not callable(commit_aio):
            raise RuntimeError("output volume commit.aio is unavailable")
        commit_start_ns = time.monotonic_ns()
        diag["commit_start_mono_ns"] = commit_start_ns

        async def commit_volume() -> dict[str, Any]:
            try:
                result = commit_aio()
                if inspect.isawaitable(result):
                    await result
                elif inspect.isawaitable(commit_aio):
                    await commit_aio
                commit_end_ns = time.monotonic_ns()
                commit_ms = round((commit_end_ns - commit_start_ns) / 1_000_000, 3)
                # Calculate overlap between write interval [write_end_early, write_end]
                # and commit interval [commit_start, commit_end].
                # write_end_early is when _persist_output_assets write loop completed.
                # The overlap is zero since intervals are sequential, but we
                # compute it for diagnostic completeness.
                _overlap_ns = max(0,
                    min(write_end_ns, commit_end_ns) - max(commit_start_ns, write_end_ns)
                )
                _overlap_ms = round(_overlap_ns / 1_000_000, 3)
                return {
                    "commit_ms": commit_ms,
                    "commit_end_mono_ns": commit_end_ns,
                    "overlap_ms": _overlap_ms,
                }
            except Exception as exc:
                # Propagate commit failures so no result yield
                raise RuntimeError(
                    f"output volume commit failed: {str(exc)[:120]}"
                ) from exc

        commit_task = asyncio.create_task(commit_volume())
        return dataclasses.replace(attempt, items=tuple(persisted)), commit_task, diag

    def read_output_asset(self, backend_path: str, expected_sha256: str = "") -> dict[str, Any]:
        volume = globals().get("_MODAL_RESOURCES", {}).get("runtime_state_volume")
        reload_volume = getattr(volume, "reload", None)
        if callable(reload_volume):
            reload_volume()
        root = Path(RUNTIME_STATE_PATH, "output_assets").resolve()
        candidate = Path(RUNTIME_STATE_PATH, str(backend_path or "")).resolve()
        try:
            candidate.relative_to(root)
        except ValueError as exc:
            raise ValueError("invalid output asset path") from exc
        if not candidate.is_file():
            raise FileNotFoundError("output asset not found")
        data = candidate.read_bytes()
        digest = hashlib.sha256(data).hexdigest()
        if expected_sha256 and digest != expected_sha256:
            raise ValueError("output asset identity mismatch")
        return {
            "data": data,
            "byte_count": len(data),
            "sha256": digest,
            "filename": candidate.name,
        }

    async def run_plan_stream(
        self,
        plan_payload: Mapping[str, Any],
        *,
        request_id: str = "",
        cancelled: Callable[[], bool] | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        # â”€â”€ TRUE METHOD FIRST LINE (before any identity or trace exists) â”€â”€
        _method_first_line_ns = time.monotonic_ns()
        _method_first_line_wall_ns = int(time.time() * 1_000_000_000)
        _method_first_line_pid = os.getpid()
        # Consistent field-name aliases for method-entry timestamps
        modal_method_entry_mono_ns: int = _method_first_line_ns
        modal_method_entry_wall_ns: int = _method_first_line_wall_ns
        _method_restore_marker = get_restore_return_marker()
        _cgroup_sampler: _CgroupCpuSampler | None = getattr(self, '_cgroup_sampler', None)
        _entry_host = _capture_host_info()

        identity = _capture_remote_identity()
        _identity_capture_end_ns = time.monotonic_ns()

        # â”€â”€ Extract request origin info before deserialization â”€â”€â”€â”€â”€
        _request_origin_info: dict[str, Any] = {}
        _safe_payload = dict(plan_payload) if isinstance(plan_payload, Mapping) else plan_payload
        if isinstance(_safe_payload, dict):
            _request_origin_info = dict(_safe_payload.pop("__request_origin_info__", {}) or {})
        _t4_request_id = str(_request_origin_info.get("request_id", request_id or ""))

        # â”€â”€ Re-emit local submission breakdown from client â”€â”€â”€â”€â”€â”€
        _local_submission_breakdown = _request_origin_info.pop("local_submission_breakdown", None)
        if isinstance(_local_submission_breakdown, dict):
            _emit_breakdown_line(
                "[v2.local_submission_breakdown.remote]", _local_submission_breakdown,
            )

        plan = ExecutionPlan.from_dict(_safe_payload if isinstance(_safe_payload, dict) else plan_payload)
        _deserialize_end_ns = time.monotonic_ns()

        # â”€â”€ Compute method entry gap before any trace output â”€â”€â”€â”€â”€â”€â”€â”€â”€
        _method_entry_gap_results: dict[str, Any] = {}
        try:
            # Durations are valid only when all process identities match.
            _marker_restored_id = (_method_restore_marker or {}).get("restored_instance_id", "")
            _marker_restore_session_id = (_method_restore_marker or {}).get("restore_session_id", "")
            _marker_task_id = (_method_restore_marker or {}).get("modal_task_id", "")
            _marker_pid = (_method_restore_marker or {}).get("pid", 0)
            _marker_boot_id = (_method_restore_marker or {}).get("boot_id", "")
            _marker_hostname = (_method_restore_marker or {}).get("hostname", "")
            _current_rid = self._restored_instance_id if hasattr(self, "_restored_instance_id") else ""
            _current_restore_session_id = (self._restore_timing or {}).get("restore_session_id", "")
            _current_task_id = identity.get("container_task_id", "")
            _current_host = _entry_host
            _identity_matches = {
                "restored_instance_id": bool(_current_rid and _current_rid == _marker_restored_id),
                "restore_session_id": bool(_current_restore_session_id and _current_restore_session_id == _marker_restore_session_id),
                "modal_task_id": bool(_current_task_id and _current_task_id == _marker_task_id),
                "pid": bool(_method_first_line_pid == _marker_pid),
                "boot_id": bool(_marker_boot_id and _marker_boot_id == _current_host.get("boot_id", "")),
                "hostname": bool(_marker_hostname and _marker_hostname == _current_host.get("hostname", "")),
            }
            _same_process = all(
                _identity_matches[key]
                for key in ("restored_instance_id", "modal_task_id", "pid", "boot_id")
            )
            _method_entry_gap_results["identity_matches"] = _identity_matches
            _method_entry_gap_results["identity_mismatch_reasons"] = [
                key for key, matched in _identity_matches.items() if not matched
            ]
            if _same_process and _method_restore_marker is not None:
                _restore_return_ns = _method_restore_marker.get("monotonic_ns", 0)
                if _restore_return_ns and _method_first_line_ns >= _restore_return_ns:
                    _method_entry_gap_results["restore_return_to_method_first_line_ms"] = round(
                        (_method_first_line_ns - _restore_return_ns) / 1_000_000, 3
                    )
                _method_entry_gap_results["same_process"] = True
                _method_entry_gap_results["cross_process_duration_unavailable"] = False
            else:
                _method_entry_gap_results["same_process"] = False
                _method_entry_gap_results["cross_process_duration_unavailable"] = True
        except Exception as exc:
            _method_entry_gap_results["same_process"] = False
            _method_entry_gap_results["cross_process_duration_unavailable"] = True
            _method_entry_gap_results["identity_mismatch_reasons"] = [f"identity_check_error:{type(exc).__name__}"]

        # â”€â”€ Continue with normal setup â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

        # Use a local event buffer until trace exists
        _pre_trace_events: list[dict[str, Any]] = [
            {"name": "run_plan_method_first_line", "phase": "method",
             "wall_unix_ns": _method_first_line_wall_ns,
             "monotonic_ns": _method_first_line_ns,
             "metadata": {"pid": _method_first_line_pid, **_entry_host,
                          "modal_method_entry_wall_unix_ns": _method_first_line_wall_ns,
                          "modal_method_entry_mono_ns": _method_first_line_ns}}
        ]

        context = ExecutionContext(
            request_id=_t4_request_id or request_id,
            cancelled=cancelled,
            trace=RuntimeTrace(request_id=_t4_request_id or request_id, process="remote"),
        )
        context.trace.set_metadata(
            **identity,
            trace_id=context.trace.trace_id,
            restored_instance_id=getattr(self, "_restored_instance_id", ""),
            restore_session_id=(self._restore_timing or {}).get("restore_session_id", ""),
            legacy_container_session_id=self.container_session_id or _V2_CONTAINER_SESSION_ID,
            request_origin_info=_request_origin_info,
            **_entry_host,
            **_resource_identity(),
        )
        if _cgroup_sampler is not None and _method_entry_gap_results.get("same_process", False):
            _cgroup_sampler.set_phase_source(
                lambda: (
                    context.trace.events[-1].phase
                    if context.trace.events and context.trace.events[-1].phase
                    else "method"
                )
            )

        if isinstance(_request_origin_info, dict):
            _origin_events = (
                ("ui_or_test_run_triggered", _request_origin_info.get("ui_run_triggered_wall_unix_ms"), "t0"),
                ("local_run_request_received", _request_origin_info.get("local_receive_wall_ns"), "t1"),
            )
            for _name, _timestamp, _boundary in _origin_events:
                if isinstance(_timestamp, (int, float)) and _timestamp > 0:
                    _wall_ns = int(_timestamp * (1_000_000 if _boundary == "t0" else 1))
                    context.trace.emit_at(
                        _name,
                        wall_unix_ns=_wall_ns,
                        process="local",
                        phase="request_origin",
                        metadata={
                            "request_id": _t4_request_id or request_id,
                            "trigger_source": _request_origin_info.get("trigger_source", ""),
                            "benchmark_run_index": _request_origin_info.get("benchmark_run_index"),
                        },
                    )

        # Now merge pre-trace events into the real trace
        for _pt_event in _pre_trace_events:
            context.trace.emit_at(
                _pt_event["name"],
                wall_unix_ns=_pt_event["wall_unix_ns"],
                monotonic_ns=_pt_event["monotonic_ns"],
                phase=_pt_event["phase"],
                metadata={**_pt_event.get("metadata", {}),
                          "deferred": True},
            )

        # â”€â”€ Emit identity capture/deserialize/trace-setup spans â”€â”€â”€â”€â”€
        context.trace.emit(
            "run_plan_identity_capture_start",
            phase="method",
            metadata={"pid": _method_first_line_pid},
        )
        context.trace.emit(
            "run_plan_identity_capture_end",
            phase="method",
            metadata={
                "capture_ms": round((_identity_capture_end_ns - _method_first_line_ns) / 1_000_000, 3),
            },
        )
        context.trace.emit("run_plan_deserialize_start", phase="method")
        context.trace.emit(
            "run_plan_deserialize_end",
            phase="method",
            metadata={
                "deserialize_ms": round((_deserialize_end_ns - _identity_capture_end_ns) / 1_000_000, 3),
            },
        )

        # â”€â”€ Emit method entry gap summary â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        _first_line_to_now_ms = round((time.monotonic_ns() - _method_first_line_ns) / 1_000_000, 3)
        context.trace.emit(
            "run_plan_method_entry_gap",
            phase="method",
            metadata={
                **_method_entry_gap_results,
                "method_first_line_to_running_log_ms": _first_line_to_now_ms,
            },
        )

        # â”€â”€ Compute restore_end_to_modal_method_ms from raw restore-method-end
        #    monotonic timestamp in _restore_timing (not the return marker).
        #    Same-process identity check required; emit "absent" when unavailable.
        _restore_end_to_modal_ms: str = "absent"
        _restore_end_wall_from_timing: str = "absent"
        _restore_start_wall_from_timing: str = "absent"
        _resume_wall_from_timing: str = "absent"
        _rt = self._restore_timing or {}
        if _rt:
            _resume_wall_from_timing = self._fmt_or_absent(_rt.get("remote_python_resume_wall_unix_ns"))
            _restore_start_wall_from_timing = self._fmt_or_absent(_rt.get("restore_method_start_wall_unix_ns"))
            _restore_end_wall_from_timing = self._fmt_or_absent(_rt.get("restore_method_end_wall_unix_ns"))
            _rt_end_mono = _rt.get("restore_method_end_mono_ns")
            # Same-process: restored_instance_id, modal_task_id, pid, boot_id must all match
            _same_process = _method_entry_gap_results.get("same_process", False)
            if _same_process and _rt_end_mono is not None and _method_first_line_ns >= _rt_end_mono:
                _restore_end_to_modal_ms = str(round(
                    (_method_first_line_ns - _rt_end_mono) / 1_000_000, 3
                ))
        print(
            f"[v2.method_entry_gap] "
            f"restore_to_method_ms={_method_entry_gap_results.get('restore_return_to_method_first_line_ms')} "
            f"first_line_to_running_log_ms={_first_line_to_now_ms} "
            f"same_process={_method_entry_gap_results.get('same_process')} "
            f"identity_mismatch_reasons={','.join(_method_entry_gap_results.get('identity_mismatch_reasons', [])) or 'none'} "
            f"remote_python_resume_wall_unix_ns={_resume_wall_from_timing} "
            f"restore_method_start_wall_unix_ns={_restore_start_wall_from_timing} "
            f"restore_method_end_wall_unix_ns={_restore_end_wall_from_timing} "
            f"modal_method_entry_wall_unix_ns={_method_first_line_wall_ns} "
            f"restore_end_to_modal_method_ms={_restore_end_to_modal_ms}",
            flush=True,
        )

        # â”€â”€ Normal trace setup â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        self._request_count = getattr(self, "_request_count", 0) + 1

        if context.trace is not None:
            _auth_cid = self.container_session_id or _V2_CONTAINER_SESSION_ID
            context.trace.container_session_id = _auth_cid
            context.trace.set_metadata(
                **identity,
                trace_id=context.trace.trace_id,
                restored_instance_id=getattr(self, "_restored_instance_id", ""),
                restore_session_id=(self._restore_timing or {}).get("restore_session_id", ""),
                legacy_container_session_id=_auth_cid,
                request_origin_info=_request_origin_info,
                **_resource_identity(),
            )
            _wf_hash_prefix = plan.workflow_hash[:16] if plan.workflow_hash else ""
            _src_wf_hash_prefix = plan.source_workflow_hash[:16] if plan.source_workflow_hash else ""
            try:
                _opts_dict = plan.execution_options.to_dict() if hasattr(plan, "execution_options") and plan.execution_options else {}
                _opts_hash = stable_hash(_opts_dict) if _opts_dict else ""
            except Exception:
                _opts_hash = ""

            # â”€â”€ Emit trace-setup span (remote_method_entry at original first-line time) â”€â”€
            context.trace.emit("run_plan_trace_setup_start", phase="method")
            context.trace.emit_at(
                "remote_method_entry",
                wall_unix_ns=_method_first_line_wall_ns,
                monotonic_ns=_method_first_line_ns,
                phase="method",
                metadata={
                    "app_name": APP_NAME,
                    "class_name": CLASS_NAME,
                    "method_name": "run_plan_stream",
                    "workflow_hash": plan.workflow_hash,
                    "workflow_hash_prefix": _wf_hash_prefix,
                    "source_workflow_hash": plan.source_workflow_hash,
                    "source_workflow_hash_prefix": _src_wf_hash_prefix,
                    "effective_options_hash": _opts_hash,
                    # â”€â”€ Correlation identity â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
                    "restored_instance_id": getattr(self, "_restored_instance_id", ""),
                    "restore_session_id": (self._restore_timing or {}).get("restore_session_id", ""),
                    "restore_count": getattr(self, "_restore_count", 0),
                    "request_count": getattr(self, "_request_count", 0),
                    "legacy_container_session_id": self.container_session_id or _V2_CONTAINER_SESSION_ID,
                    # â”€â”€ Method-entry timestamps for downstream consumers â”€â”€â”€â”€â”€
                    "modal_method_entry_wall_unix_ns": _method_first_line_wall_ns,
                    "modal_method_entry_mono_ns": _method_first_line_ns,
                    # â”€â”€ Request origin identity â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
                    "request_id": _t4_request_id,
                    "trigger_source": _request_origin_info.get("trigger_source", ""),
                    # â”€â”€ Remote-observed identity â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
                    **identity,
                    **_resource_identity(),
                },
            )
            context.trace.emit(
                "container_entry",
                phase="execution",
                metadata={
                    "container_session_id": _auth_cid,
                    "workflow_hash": plan.workflow_hash,
                },
            )
            context.trace.emit("run_plan_trace_setup_end", phase="method")

        # â”€â”€ First status yield â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        _plan_received_mono_ns = time.monotonic_ns()
        context.trace.emit("run_plan_first_status_yield", phase="method")
        yield {
            "type": "status",
            "phase": "plan_received",
            "request_id": request_id,
            "trace_id": context.trace.trace_id if context.trace else "",
        }
        _execution_stream = self.executor.stream(plan, context=context)
        async for event in _execution_stream:
            if event.get("type") == "result" and isinstance(event.get("data"), dict):
                data = dict(event["data"])
                _exec_trace = data.get("trace", {})
                _exec_stages = _exec_trace.get("stages") if isinstance(_exec_trace, Mapping) else None

                # â”€â”€ Drain available background UNET diagnostics â”€â”€â”€â”€
                _bg_trace_events: list[dict[str, Any]] = []
                try:
                    from comfymodal_runtime.model_preload import _BG_UNET_DIAG_STORE, _BG_UNET_DIAG_LOCK
                    with _BG_UNET_DIAG_LOCK:
                        for _canonical_key in list(_BG_UNET_DIAG_STORE.keys()):
                            _bg_trace_events.extend(_BG_UNET_DIAG_STORE.pop(_canonical_key, []))
                except Exception:
                    pass

                merged = merge_runtime_traces(
                    self._lifecycle_trace,
                    _exec_trace,
                )
                _authoritative_cid = self.container_session_id or _V2_CONTAINER_SESSION_ID
                if _authoritative_cid:
                    merged.container_session_id = _authoritative_cid
                # Merge background UNET diagnostic events into the result trace
                if _bg_trace_events:
                    merged.extend(_bg_trace_events)
                # â”€â”€ Event identity enrichment â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
                # Backfill missing request_id, restore IDs, task/input/pid/tid
                # on lifecycle and background events now that the authoritative
                # request_id is known.  Updates BOTH event.request_id (top-level
                # serialized field) and event.metadata identity keys.
                # Does NOT overwrite nonempty values.
                _enrich_identity = {
                    "request_id": _t4_request_id,
                    "restored_instance_id": getattr(self, "_restored_instance_id", ""),
                    "restore_session_id": (self._restore_timing or {}).get("restore_session_id", ""),
                    "restore_count": getattr(self, "_restore_count", 0),
                    "request_count": getattr(self, "_request_count", 0),
                    "modal_task_id": identity.get("container_task_id", ""),
                }
                _enrich_identity = {k: v for k, v in _enrich_identity.items() if v}
                if _enrich_identity:
                    for _evt in merged.events:
                        # Update top-level request_id if empty
                        if _t4_request_id and not _evt.request_id:
                            object.__setattr__(_evt, "request_id", _t4_request_id)
                        # Update metadata identity keys if missing
                        if hasattr(_evt, "metadata") and isinstance(_evt.metadata, dict):
                            for _ek, _ev in _enrich_identity.items():
                                if _ek not in _evt.metadata or not _evt.metadata.get(_ek):
                                    _evt.metadata[_ek] = _ev
                # Ensure merged.request_id is set to authoritative value
                if _t4_request_id:
                    merged.request_id = _t4_request_id
                # Merge legacy stages from events with node-stage windows.
                # Node-stage windows win for exact keys; legacy stages fill
                # gaps (e.g. container_entry -> t3_modal_entry).
                _legacy_stages = merged.to_legacy_timing().get("stages", {})
                if _exec_stages:
                    _legacy_stages.update(_exec_stages)
                data["trace"] = merged.to_dict()
                data["trace"]["stages"] = _legacy_stages
                data["phase_durations_ms"] = merged.export_phase_durations()
                _rt = self._restore_timing or _LATEST_LIFECYCLE_TIMING
                if _rt is not None and "_restore_timing" not in data:
                    data["_restore_timing"] = dict(_rt)
                # â”€â”€ Request-origin summary (T0â€“T5) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
                # Gather raw wall timestamps from origin info + local captures
                _t4_wall = _method_first_line_wall_ns
                _t4_request = _t4_request_id
                _trig_src = _request_origin_info.get("trigger_source", "unknown")
                _t0_wall = _request_origin_info.get("ui_run_triggered_wall_unix_ms", None)
                if _t0_wall is not None:
                    _t0_wall_ns = int(_t0_wall * 1_000_000)  # convert msâ†’ns
                else:
                    _t0_wall_ns = None
                _t1_wall_ns = _request_origin_info.get("local_receive_wall_ns", None)
                _t2_wall_ns = _request_origin_info.get("modal_submission_attempt_wall_ns", None)
                _t3_wall_ns = _request_origin_info.get("modal_generator_created_wall_ns", None)
                # V2 remote request origin: generator create start (before
                # remote_gen.aio), first iteration start (before __anext__),
                # and first remote event (after __anext__).
                # Only generator_create_start is sent in the plan payload;
                # the others are captured too late and render "absent".
                _gen_create_start_wall_ns = _request_origin_info.get("modal_generator_create_start_wall_ns", None)
                _first_iter_start_wall_ns = _request_origin_info.get("modal_first_iteration_start_wall_ns", None)
                _first_remote_event_wall_ns = _request_origin_info.get("modal_first_remote_event_wall_ns", None)
                # Extract authoritative T5 from remote V2 prompt_executor_invoke_start event.
                # Filter for process=remote to ignore legacy/duplicate traces.
                # Iterate until a remote event with non-empty t5_wall_ns is found;
                # do NOT break on the first remote event missing the raw timestamp.
                _t5_wall_ns = None
                if isinstance(_exec_trace, dict):
                    _exec_events = _exec_trace.get("events", [])
                    if isinstance(_exec_events, list):
                        for _evt in _exec_events:
                            if isinstance(_evt, dict) and _evt.get("name") == "prompt_executor_invoke_start":
                                _evt_proc = _evt.get("process", "") or ""
                                if _evt_proc == "remote":
                                    _evt_meta = _evt.get("metadata", {}) or {}
                                    _t5_raw = _evt_meta.get("t5_wall_ns")
                                    if _t5_raw:
                                        _t5_wall_ns = int(_t5_raw)
                                        break

                # Compute all eight intervals with clock-scope metadata.
                # Cross-process intervals MUST use wall; same-process may use mono.
                # T0(browser)â†’T1(server): cross-process â†’ wall
                _t0_t1_ms = round((_t1_wall_ns - _t0_wall_ns) / 1_000_000, 3) if _t0_wall_ns and _t1_wall_ns else None
                _t0_t1_scope = "wall_cross_process" if _t0_wall_ns and _t1_wall_ns else None
                # T1(server)â†’T2(server): same-process â†’ mono preferred
                _t1_t2_ms = None
                _t1_t2_scope = None
                _t1_mono = _request_origin_info.get("local_receive_mono_ns", None)
                _t2_mono = _request_origin_info.get("modal_submission_attempt_mono_ns", None)
                if _t1_mono and _t2_mono:
                    _t1_t2_ms = round((_t2_mono - _t1_mono) / 1_000_000, 3)
                    _t1_t2_scope = "mono_same_process"
                elif _t1_wall_ns and _t2_wall_ns:
                    _t1_t2_ms = round((_t2_wall_ns - _t1_wall_ns) / 1_000_000, 3)
                    _t1_t2_scope = "wall_fallback"
                # T2(server)â†’T3(server): same-process â†’ mono
                _t2_t3_ms = None
                _t2_t3_scope = None
                if _t2_mono and _request_origin_info.get("modal_generator_created_mono_ns"):
                    _t2_t3_ms = round((_request_origin_info["modal_generator_created_mono_ns"] - _t2_mono) / 1_000_000, 3)
                    _t2_t3_scope = "mono_same_process"
                elif _t2_wall_ns and _t3_wall_ns:
                    _t2_t3_ms = round((_t3_wall_ns - _t2_wall_ns) / 1_000_000, 3)
                    _t2_t3_scope = "wall_fallback"
                # T2(server)â†’T4(remote): cross-process â†’ wall
                _t2_t4_ms = round((_t4_wall - _t2_wall_ns) / 1_000_000, 3) if _t2_wall_ns and _t4_wall else None
                _t2_t4_scope = "wall_cross_process" if _t2_wall_ns and _t4_wall else None
                # T3(server)â†’T4(remote): cross-process â†’ wall
                _t3_t4_ms = round((_t4_wall - _t3_wall_ns) / 1_000_000, 3) if _t3_wall_ns and _t4_wall else None
                _t3_t4_scope = "wall_cross_process" if _t3_wall_ns and _t4_wall else None
                # T4(remote)â†’T5(remote): same-process â†’ mono
                _t4_t5_ms = None
                _t4_t5_scope = None
                _t5_mono_from_trace = None
                if isinstance(_exec_trace, dict):
                    _exec_events = _exec_trace.get("events", [])
                    if isinstance(_exec_events, list):
                        for _evt in _exec_events:
                            if isinstance(_evt, dict) and _evt.get("name") == "prompt_executor_invoke_start":
                                _evt_proc = _evt.get("process", "") or ""
                                if _evt_proc == "remote":
                                    _evt_meta = _evt.get("metadata", {}) or {}
                                    _t5_mono_candidate = _evt_meta.get("t5_mono_ns")
                                    if _t5_mono_candidate:
                                        _t5_mono_from_trace = _t5_mono_candidate
                                        break
                if _method_first_line_ns and _t5_mono_from_trace:
                    _t4_t5_ms = round((_t5_mono_from_trace - _method_first_line_ns) / 1_000_000, 3)
                    _t4_t5_scope = "mono_same_process"
                elif _t4_wall and _t5_wall_ns:
                    _t4_t5_ms = round((_t5_wall_ns - _t4_wall) / 1_000_000, 3)
                    _t4_t5_scope = "wall_fallback"
                # T0(browser)â†’T4(remote): cross-process â†’ wall
                _t0_t4_ms = round((_t4_wall - _t0_wall_ns) / 1_000_000, 3) if _t0_wall_ns and _t4_wall else None
                _t0_t4_scope = "wall_cross_process" if _t0_wall_ns and _t4_wall else None
                # T0(browser)â†’T5(remote): cross-process â†’ wall
                _t0_t5_ms = round((_t5_wall_ns - _t0_wall_ns) / 1_000_000, 3) if _t0_wall_ns and _t5_wall_ns else None
                _t0_t5_scope = "wall_cross_process" if _t0_wall_ns and _t5_wall_ns else None

                # Embed raw timestamps + intervals + clock scope in result data
                data["request_id"] = _t4_request
                data["trigger_source"] = _trig_src
                data["raw_timestamps"] = {
                    "t0_ui_trigger_wall_unix_ns": _t0_wall_ns,
                    "t1_local_receive_wall_unix_ns": _t1_wall_ns,
                    "modal_generator_create_start_wall_unix_ns": _gen_create_start_wall_ns,
                    "modal_submission_attempt_wall_unix_ns": _t2_wall_ns,
                    "modal_generator_created_wall_unix_ns": _t3_wall_ns,
                    "modal_first_iteration_start_wall_unix_ns": _first_iter_start_wall_ns,
                    "modal_first_remote_event_wall_unix_ns": _first_remote_event_wall_ns,
                    "t4_modal_method_entry_wall_unix_ns": _t4_wall,
                    "t5_prompt_executor_invoke_start_wall_unix_ns": _t5_wall_ns,
                }
                data["intervals_ms"] = {
                    "run_trigger_to_local_receive_ms": _t0_t1_ms,
                    "local_receive_to_actual_submission_ms": _t1_t2_ms,
                    "generator_create_ms": _t2_t3_ms,
                    "actual_submission_to_method_entry_ms": _t2_t4_ms,
                    "generator_created_to_entry_ms": _t3_t4_ms,
                    "method_entry_to_prompt_executor_ms": _t4_t5_ms,
                    "run_trigger_to_modal_entry_ms": _t0_t4_ms,
                    "run_trigger_to_prompt_executor_ms": _t0_t5_ms,
                }
                data["clock_scopes"] = {
                    "run_trigger_to_local_receive": _t0_t1_scope,
                    "local_receive_to_actual_submission": _t1_t2_scope,
                    "generator_create": _t2_t3_scope,
                    "actual_submission_to_method_entry": _t2_t4_scope,
                    "generator_created_to_entry": _t3_t4_scope,
                    "method_entry_to_prompt_executor": _t4_t5_scope,
                    "run_trigger_to_modal_entry": _t0_t4_scope,
                    "run_trigger_to_prompt_executor": _t0_t5_scope,
                }

                _modal_input_id = identity.get("modal_input_id", "")
                _modal_task_id = identity.get("container_task_id", "")

                # â”€â”€ Exact one-line [v2.request_origin] summary â”€â”€â”€â”€â”€â”€
                _trig_to_dispatch = _t0_t1_ms  # same as run_trigger_to_local_receive
                _dispatch_to_entry = _t2_t4_ms
                _entry_to_exec = _t4_t5_ms       # same as method_entry_to_prompt_executor
                _trig_to_exec = _t0_t5_ms        # same as run_trigger_to_prompt_executor
                print(
                    f"[v2.remote_request_origin.remote] "
                    f"request_id={_t4_request} "
                    f"trigger_source={_trig_src} "
                    f"ui_trigger_unix_ms={self._fmt_or_absent(_t0_wall)} "
                    f"local_receive_unix_ns={self._fmt_or_absent(_t1_wall_ns)} "
                    f"modal_generator_create_start_unix_ns={self._fmt_or_absent(_gen_create_start_wall_ns)} "
                    f"modal_submission_attempt_unix_ns={self._fmt_or_absent(_t2_wall_ns)} "
                    f"modal_generator_created_unix_ns={self._fmt_or_absent(_t3_wall_ns)} "
                    f"modal_first_iteration_start_unix_ns={self._fmt_or_absent(_first_iter_start_wall_ns)} "
                    f"modal_first_remote_event_unix_ns={self._fmt_or_absent(_first_remote_event_wall_ns)} "
                    f"modal_method_entry_unix_ns={_t4_wall} "
                    f"prompt_executor_invoke_start_unix_ns={self._fmt_or_absent(_t5_wall_ns)} "
                    f"trigger_to_dispatch_ms={_trig_to_dispatch} "
                    f"dispatch_to_modal_entry_ms={_dispatch_to_entry} "
                    f"modal_entry_to_executor_ms={_entry_to_exec} "
                    f"trigger_to_executor_ms={_trig_to_exec} "
                    f"modal_input_id={_modal_input_id} "
                    f"modal_task_id={_modal_task_id}",
                    flush=True,
                )
                _critical_path_data = data.pop("_v2_critical_path_data", {})
                if not isinstance(_critical_path_data, Mapping):
                    _critical_path_data = {}
                _critical_path_values = _build_v2_critical_path(
                    _rt or {},
                    _critical_path_data,
                    run_enter_mono_ns=_method_first_line_ns,
                    plan_received_mono_ns=_plan_received_mono_ns,
                    same_process_as_restore=bool(
                        _method_entry_gap_results.get("same_process", False)
                    ),
                )
                print(_format_v2_critical_path(_critical_path_values), flush=True)
                event = {**event, "data": data}
                if _cgroup_sampler is not None:
                    _cgroup_sampler.stop()
                    _cgroup_sampler.report()
                    self._cgroup_sampler = None
                    _cgroup_sampler = None
            yield event

    async def run_prompt_stream(
        self,
        workflow: dict,
        input_images: dict | None = None,
        trace: dict | None = None,
        modal_options: dict | None = None,
        production_report: dict | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        from .contracts import ExecutionOptions

        plan = ExecutionPlan(
            workflow=workflow,
            input_images=input_images or {},
            production_report=production_report or {},
            execution_options=ExecutionOptions.from_legacy(
                modal_options,
                production_report=production_report or {},
                default_production=bool((production_report or {}).get("enabled")),
            ),
            request_metadata={"trace": dict(trace or {})},
        )
        plan_dict = plan.to_dict()
        # Propagate request_origin_info from the trace dict so it reaches
        # run_plan_stream on the v2 benchmark/legacy path.
        if isinstance(trace, dict):
            _roi = trace.get("request_origin_info", None)
            if _roi and isinstance(_roi, dict):
                plan_dict["__request_origin_info__"] = dict(_roi)
        async for event in self.run_plan_stream(plan_dict):
            yield event

    async def publish_restore_plan(self, plan_payload: Mapping[str, Any]) -> dict[str, Any]:
        identity = _capture_remote_identity()
        plan = RestorePlan.from_dict(plan_payload)
        # Use async commit path in async context
        result = await _publish_restore_plan_impl_async(plan)
        authoritative = await self._get_remote_restore_publisher().read_current_plan_async()
        self._restore_plan = authoritative or plan
        result.setdefault("identity", {}).update(identity)
        return result

    async def run_checkpoint_stream(self, *args: Any, **kwargs: Any) -> AsyncIterator[dict[str, Any]]:
        if self.checkpoint_runner is None:
            yield {"type": "error", "message": "checkpoint compatibility runner is not configured"}
            return
        result = self.checkpoint_runner(*args, **kwargs)
        if inspect.isawaitable(result):
            result = await result
        if hasattr(result, "__aiter__"):
            async for event in result:
                yield event
        elif isinstance(result, dict):
            yield {"type": "result", "data": result}


def _build_decorated_v2_class() -> type:
    """Build a ``ModalRuntimeEntrypointV2`` subclass with all Modal lifecycle
    and method decorators applied, but WITHOUT ``modal.concurrent()`` or
    ``app.cls()`` binding (which requires resources).

    Uses ``object.__init__`` to avoid Modal's custom-constructor deprecation
    warning.  Per-container initialization is deferred to the ``enter()``
    hooks (``startup`` for snapshotted, ``restore`` for post-snapshot) and
    lazy-init in ``_v2_init_instance``.

    This must be called BEFORE ``build_modal_resources()`` so the decorated
    class (with finalized ``enter``/``method`` registrations) is exported
    to ``globals()`` regardless of resource availability.  Modal's worker
    importer needs the decorated raw class at module level; replacing it
    with a plain ``ModalRuntimeEntrypoint`` would cause ``KeyError`` on
    ``run_plan_stream`` in the container IO manager.

    When ``_modal`` is unavailable, returns ``None`` and the caller should
    export a plain compatibility alias instead.
    """
    if _modal is None:
        return None
    import functools

    # Create subclass with object.__init__ to avoid Modal's custom constructor warning.
    cls = type("ModalRuntimeEntrypointV2", (ModalRuntimeEntrypoint,), {
        "__init__": object.__init__,
    })

    # Lazy per-instance initialization (__init__ is skipped).
    def _v2_init_instance(self):
        if hasattr(self, "_v2_initialized"):
            return
        self._config = None
        self._bootstrap_injected = False
        self.bootstrap = RuntimeBootstrap(None)
        self._executor_injected = False
        self.executor = RuntimeExecutor(in_process_runner=self._run_in_process)
        self.checkpoint_runner = None
        self._legacy_module = None
        self._legacy_api = None
        self._runtime_configured = False
        self._restore_plan = None
        self._restore_publisher = None
        self._preload_bridge = V2LoaderBridge()
        self._lifecycle_trace = None
        self.container_session_id = _V2_CONTAINER_SESSION_ID
        self._restore_count = 0
        self._restore_timing = None
        self._cgroup_sampler = None
        self._cpu_snapshot_unet_runtime_state = None
        self._v2_initialized = True

    # Wrap each Modal-exposed method to lazy-init first.
    _METHODS_TO_WRAP = (
        "startup", "restore",
        "run_plan_stream", "run_prompt_stream",
        "publish_restore_plan", "read_output_asset", "run_checkpoint_stream",
    )
    for _name in _METHODS_TO_WRAP:
        _orig = getattr(cls, _name)

        def _make_wrapper(orig_method):
            if inspect.isasyncgenfunction(orig_method):
                @functools.wraps(orig_method)
                async def _wrapper(self, *args, **kwargs):
                    _v2_init_instance(self)
                    async for item in orig_method(self, *args, **kwargs):
                        yield item
                return _wrapper
            elif inspect.isgeneratorfunction(orig_method):
                @functools.wraps(orig_method)
                def _wrapper(self, *args, **kwargs):
                    _v2_init_instance(self)
                    yield from orig_method(self, *args, **kwargs)
                return _wrapper
            else:
                @functools.wraps(orig_method)
                def _wrapper(self, *args, **kwargs):
                    _v2_init_instance(self)
                    return orig_method(self, *args, **kwargs)
                return _wrapper

        setattr(cls, _name, _make_wrapper(_orig))

    # Apply Modal lifecycle/method decorators.
    setattr(cls, "startup", _modal.enter(snap=True)(cls.startup))
    setattr(cls, "restore", _modal.enter(snap=False)(cls.restore))
    setattr(cls, "run_plan_stream", _modal.method(is_generator=True)(cls.run_plan_stream))
    setattr(cls, "run_prompt_stream", _modal.method(is_generator=True)(cls.run_prompt_stream))
    setattr(cls, "publish_restore_plan", _modal.method()(cls.publish_restore_plan))
    setattr(cls, "read_output_asset", _modal.method()(cls.read_output_asset))
    setattr(cls, "run_checkpoint_stream", _modal.method(is_generator=True)(cls.run_checkpoint_stream))
    return cls


def _register_remote_entrypoint(resources: Mapping[str, Any], spec: ModalRuntimeSpec) -> Any:
    if _modal is None or resources.get("app") is None:
        return None

    # The raw decorated class was already exported by the module tail.
    # Reuse it for concurrent + app binding; do NOT re-create it (that
    # would register duplicate Modal functions).
    remote_class = globals().get("ModalRuntimeEntrypointV2")
    if remote_class is None or remote_class is ModalRuntimeEntrypoint:
        # Guard: if the decorated class somehow wasn't set (e.g. _modal was
        # unavailable when _build_decorated_v2_class was called but became
        # available now), build it fresh.
        remote_class = _build_decorated_v2_class()
        if remote_class is not None:
            globals()["ModalRuntimeEntrypointV2"] = remote_class
    if remote_class is None:
        return None

    remote_class = _modal.concurrent(
        target_inputs=spec.target_inputs,
        max_inputs=spec.max_inputs,
    )(remote_class)
    _enable_gpu_snapshot = os.environ.get("COMFYMODAL_ENABLE_GPU_SNAPSHOT", "0") == "1"
    # Pass ordered GPU list for Modal's native ordered-GPU fallback.
    _gpu_arg: str | list[str] = list(spec.gpu) if len(spec.gpu) > 1 else spec.gpu[0]
    return resources["app"].cls(
        gpu=_gpu_arg,
        cpu=spec.cpu,
        memory=spec.memory,
        timeout=spec.timeout,
        min_containers=spec.min_containers,
        scaledown_window=spec.scaledown_window,
        volumes={
            spec.models_path: resources["models_volume"],
            spec.custom_nodes_path: resources["custom_nodes_volume"],
            spec.runtime_state_path: resources["runtime_state_volume"],
        },
        enable_memory_snapshot=spec.enable_memory_snapshot,
        env=_runtime_env(),
        **({"experimental_options": {"enable_gpu_snapshot": True}} if _enable_gpu_snapshot else {}),
    )(remote_class)


def _publish_restore_plan_impl(plan: RestorePlan) -> dict[str, Any]:
    resources = globals().get("_MODAL_RESOURCES", {})
    modal_volume = resources.get("runtime_state_volume")
    if modal_volume is None:
        # The volume is mounted via the function's ``volumes={...}``
        # declaration, but the module-level ``_MODAL_RESOURCES`` fallback
        # may not carry the live handle.  Resolve the named Volume from
        # inside the remote function as a remote-safe fallback.
        try:
            import modal as _modal_fallback
            modal_volume = _modal_fallback.Volume.from_name(
                RUNTIME_STATE_VOLUME_NAME, create_if_missing=False,
            )
        except Exception:
            modal_volume = None
    if modal_volume is None:
        raise RuntimeError("v2 runtime-state Modal Volume is not mounted")
    volume = ModalMountedStateVolume(RUNTIME_STATE_PATH, modal_volume)
    coordinator = CommitCoordinator(volume, state_path=V2_RESTORE_STATE_FILE)
    publisher = RestorePlanPublisher(coordinator)
    result = publisher.publish_with_metrics(plan)
    readback_started = time.perf_counter()
    authoritative = publisher.read_current_plan()
    readback_ms = round((time.perf_counter() - readback_started) * 1000.0, 3)
    if authoritative is None:
        raise RuntimeError("published RestorePlan could not be read back from runtime-state Volume")
    # â”€â”€ Add publish_readback event to publication trace â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    pub_trace = result.get("trace", {})
    if isinstance(pub_trace, dict) and "events" in pub_trace:
        pub_trace["events"].append({
            "name": "publish_readback",
            "phase": "publish",
            "wall_unix_ns": int(time.time() * 1_000_000_000),
            "monotonic_ns": time.monotonic_ns(),
            "process": "publisher",
            "metadata": {"readback_ms": readback_ms},
        })
    result.update({
        "status": "published" if result.get("changed") else "unchanged",
        "generation": authoritative.generation,
        "canonical_hash": authoritative.canonical_hash,
        "runtime_state_volume": RUNTIME_STATE_VOLUME_NAME,
        "state_path": V2_RESTORE_STATE_FILE,
        "readback_ms": readback_ms,
        "models_volume_write_count": 0,
        "models_volume_commit_count": 0,
    })
    return result


async def _publish_restore_plan_impl_async(plan: RestorePlan) -> dict[str, Any]:
    """Async variant of ``_publish_restore_plan_impl`` that uses async commit.

    Uses ``RestorePlanPublisher.publish_with_metrics_async()`` which calls
    ``coordinator.commit_async()`` to perform exactly one awaited async
    Volume commit and no blocking Modal commit.
    """
    resources = globals().get("_MODAL_RESOURCES", {})
    modal_volume = resources.get("runtime_state_volume")
    if modal_volume is None:
        try:
            import modal as _modal_fallback
            modal_volume = _modal_fallback.Volume.from_name(
                RUNTIME_STATE_VOLUME_NAME, create_if_missing=False,
            )
        except Exception:
            modal_volume = None
    if modal_volume is None:
        raise RuntimeError("v2 runtime-state Modal Volume is not mounted")
    volume = ModalMountedStateVolume(RUNTIME_STATE_PATH, modal_volume)
    coordinator = CommitCoordinator(volume, state_path=V2_RESTORE_STATE_FILE)
    publisher = RestorePlanPublisher(coordinator)
    result = await publisher.publish_with_metrics_async(plan)
    readback_started = time.perf_counter()
    authoritative = await publisher.read_current_plan_async()
    readback_ms = round((time.perf_counter() - readback_started) * 1000.0, 3)
    if authoritative is None:
        raise RuntimeError("published RestorePlan could not be read back from runtime-state Volume")
    pub_trace = result.get("trace", {})
    if isinstance(pub_trace, dict) and "events" in pub_trace:
        pub_trace["events"].append({
            "name": "publish_readback",
            "phase": "publish",
            "wall_unix_ns": int(time.time() * 1_000_000_000),
            "monotonic_ns": time.monotonic_ns(),
            "process": "publisher",
            "metadata": {"readback_ms": readback_ms},
        })
    result.update({
        "status": "published" if result.get("changed") else "unchanged",
        "generation": authoritative.generation,
        "canonical_hash": authoritative.canonical_hash,
        "runtime_state_volume": RUNTIME_STATE_VOLUME_NAME,
        "state_path": V2_RESTORE_STATE_FILE,
        "readback_ms": readback_ms,
        "models_volume_write_count": 0,
        "models_volume_commit_count": 0,
    })
    return result


def publish_restore_plan_remote(plan_payload: Mapping[str, Any]) -> dict[str, Any]:
    """Publish before GPU class lookup so the next snap=False sees the plan."""
    _t0 = time.perf_counter()
    print("[publish_restore_plan] entry", flush=True)
    try:
        identity = _capture_remote_identity()
        result = _publish_restore_plan_impl(RestorePlan.from_dict(plan_payload))
        result.setdefault("identity", {}).update(identity)
        _elapsed_ms = round((time.perf_counter() - _t0) * 1000, 1)
        print(f"[publish_restore_plan] success elapsed_ms={_elapsed_ms}", flush=True)
        return result
    except Exception as exc:
        _elapsed_ms = round((time.perf_counter() - _t0) * 1000, 1)
        print(
            f"[publish_restore_plan] error elapsed_ms={_elapsed_ms} "
            f"exception_type={type(exc).__name__}",
            flush=True,
        )
        raise


# â”€â”€ ModalRuntimeEntrypointV2: decorated class exported BEFORE resource
#    construction so Modal's finalized function registry (enter/method)
#    is always populated.  Resource-independent: only depends on _modal
#    being importable.  When _modal is unavailable, export a plain
#    compatibility alias (no decorated methods, but prevents crash-loop
#    on missing attribute).
_v2_decorated_class = _build_decorated_v2_class()
globals()["ModalRuntimeEntrypointV2"] = (
    _v2_decorated_class if _v2_decorated_class is not None else ModalRuntimeEntrypoint
)

try:
    _MODAL_RESOURCES = build_modal_resources()
except Exception:
    _MODAL_RESOURCES = {
        "app": None,
        "image": None,
        "models_volume": None,
        "custom_nodes_volume": None,
        "runtime_state_volume": None,
        "source_identity": None,
        "spec": ModalRuntimeSpec(),
    }
# Phase 1: Pre-compute deployment combined hash from the canonical
# DeploymentIdentity / source_identity used by V2 resources.  This
# stable nonempty value is what startup/restore/request consumers and
# certificate / manifest expected identity paths all reference — never
# an ad-hoc env hash or Modal image ID.
_V2_DEPLOYMENT_COMBINED_HASH = (
    _MODAL_RESOURCES.get("source_identity").combined_hash
    if _MODAL_RESOURCES.get("source_identity") is not None
    else ""
)
# Modal CLI discovers the application through a module-level ``app`` object.
# Keep the resource construction above as the single source of truth while
# exposing the registered shadow app for ``modal deploy -m``.
app = _MODAL_RESOURCES.get("app")
ModalRuntimeEntrypointRemote = _register_remote_entrypoint(
    _MODAL_RESOURCES,
    _MODAL_RESOURCES["spec"],
)
if _modal is not None and _MODAL_RESOURCES.get("app") is not None:
    publish_restore_plan_remote = _MODAL_RESOURCES["app"].function(
        image=_MODAL_RESOURCES["image"],
        cpu=2,
        memory=4096,
        timeout=300,
        startup_timeout=120,
        retries=0,
        env={_PUBLISHER_MARKER: "1"},
        min_containers=MIN_CONTAINERS,
        max_containers=1,
        scaledown_window=SCALEDOWN_WINDOW,
        volumes={
            _MODAL_RESOURCES["spec"].runtime_state_path: _MODAL_RESOURCES["runtime_state_volume"],
        },
    )(publish_restore_plan_remote)
