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


LOADER_SELECTION = "LOADER_SELECTION"
EXECUTION_POLICY = "EXECUTION_POLICY"
CACHE_POLICY = "CACHE_POLICY"
SNAPSHOT_POLICY = "SNAPSHOT_POLICY"
TIMING_DIAGNOSTICS = "TIMING_DIAGNOSTICS"
DEPRECATED_DIAGNOSTIC = "DEPRECATED_DIAGNOSTIC"
ROLES = ("clip", "unet", "vae")


def _spec(
    env_var: str,
    type_: str,
    default: Any,
    classification: str,
    description: str,
    *,
    choices: tuple[str, ...] = (),
) -> dict[str, Any]:
    value: dict[str, Any] = {
        "name": env_var,
        "env_var": env_var,
        "type": type_,
        "default": default,
        "classification": classification,
        "description": description,
    }
    if choices:
        value["choices"] = choices
    return value


# Insertion order is intentional: it is the stable order used by reconciliation
# reports and makes the registry easy to audit against the runtime env manifest.
GOLDEN_CONTROL_FLAGS: dict[str, dict[str, Any]] = {
    # R42 Golden pipeline master selector (deploy-time enablement; the
    # runtime-side authority still registers it so requested/deployed/
    # observed reconciliation can never disagree about it silently).
    "COMFYMODAL_GOLDEN_PIPELINE": _spec("COMFYMODAL_GOLDEN_PIPELINE", "bool", False, EXECUTION_POLICY, "Enable the R42 Golden QD4 pipeline."),

    # CLIP loader and hydration controls.
    "COMFYMODAL_V2_CLIP_QD_READER": _spec("COMFYMODAL_V2_CLIP_QD_READER", "bool", False, LOADER_SELECTION, "Enable the genuine queue-depth CLIP reader."),
    "COMFYMODAL_V2_CLIP_QD_QD": _spec("COMFYMODAL_V2_CLIP_QD_QD", "int", 4, LOADER_SELECTION, "CLIP queue depth."),
    "COMFYMODAL_V2_CLIP_QD_BLOCK_MIB": _spec("COMFYMODAL_V2_CLIP_QD_BLOCK_MIB", "int", 32, LOADER_SELECTION, "CLIP queue-reader block size in MiB."),
    "COMFYMODAL_V2_CLIP_QD_LAUNCH_POLICY": _spec("COMFYMODAL_V2_CLIP_QD_LAUNCH_POLICY", "enum", "restore_earliest", LOADER_SELECTION, "CLIP queue-reader launch boundary.", choices=("restore_earliest", "after_restore_sensitive_phase", "after_cuda_restore", "method_entry", "clean_lane_post_restore")),
    "COMFYMODAL_V2_CLIP_FAST_HYDRATION": _spec("COMFYMODAL_V2_CLIP_FAST_HYDRATION", "bool", False, LOADER_SELECTION, "Enable direct fast CLIP hydration."),
    "COMFYMODAL_V2_CLIP_STAGED_HYDRATION": _spec("COMFYMODAL_V2_CLIP_STAGED_HYDRATION", "bool", False, LOADER_SELECTION, "Enable staged CLIP hydration."),
    "COMFYMODAL_V2_SPECULATIVE_CLIP_HYDRATION": _spec("COMFYMODAL_V2_SPECULATIVE_CLIP_HYDRATION", "bool", False, LOADER_SELECTION, "DIAGNOSTIC_ONLY speculative CLIP hydration; explicit opt-in required (E40: unset must never activate)."),
    "COMFYMODAL_V2_CLIP_FP32_CAST_ONCE": _spec("COMFYMODAL_V2_CLIP_FP32_CAST_ONCE", "bool", False, LOADER_SELECTION, "Retain compute-ready FP32 CLIP weights and cast once."),
    "COMFYMODAL_V2_CLIP_SNAPSHOT_EXCLUDE_WEIGHTS": _spec("COMFYMODAL_V2_CLIP_SNAPSHOT_EXCLUDE_WEIGHTS", "bool", False, SNAPSHOT_POLICY, "Exclude CLIP weights from the snapshot."),
    "COMFYMODAL_V2_CLIP_FASTSAFE_THREADS": _spec("COMFYMODAL_V2_CLIP_FASTSAFE_THREADS", "int", 8, LOADER_SELECTION, "CLIP FastSafeTensor reader threads."),
    "COMFYMODAL_V2_CLIP_FASTSAFE_BLOCK_BYTES": _spec("COMFYMODAL_V2_CLIP_FASTSAFE_BLOCK_BYTES", "int", 67108864, LOADER_SELECTION, "CLIP FastSafeTensor block size in bytes."),
    "COMFYMODAL_V2_CLIP_FASTSAFE_BBUF_KB": _spec("COMFYMODAL_V2_CLIP_FASTSAFE_BBUF_KB", "int", 524288, LOADER_SELECTION, "CLIP FastSafeTensor bounce-buffer size in KiB."),
    "COMFYMODAL_V2_STAGED_PRODUCERS": _spec("COMFYMODAL_V2_STAGED_PRODUCERS", "int", 4, LOADER_SELECTION, "Staged hydration producer count."),
    "COMFYMODAL_V2_STAGED_POOL_MB": _spec("COMFYMODAL_V2_STAGED_POOL_MB", "int", 1024, LOADER_SELECTION, "Staged hydration pool size in MiB."),
    "COMFYMODAL_V2_STAGED_BUCKET_MB": _spec("COMFYMODAL_V2_STAGED_BUCKET_MB", "int", 256, LOADER_SELECTION, "Staged hydration bucket size in MiB."),
    "COMFYMODAL_V2_STAGED_CPU_CAST": _spec("COMFYMODAL_V2_STAGED_CPU_CAST", "bool", True, LOADER_SELECTION, "Cast staged CPU buckets before transfer."),
    "COMFYMODAL_V2_STAGED_ASYNC_H2D": _spec("COMFYMODAL_V2_STAGED_ASYNC_H2D", "bool", True, LOADER_SELECTION, "Use asynchronous staged host-to-device copies."),
    "COMFYMODAL_V2_STAGED_CONTIGUOUS_GPU_BUCKETS": _spec("COMFYMODAL_V2_STAGED_CONTIGUOUS_GPU_BUCKETS", "bool", False, LOADER_SELECTION, "Use contiguous GPU staging buckets."),
    "COMFYMODAL_V2_STAGED_SOURCE_ORDER": _spec("COMFYMODAL_V2_STAGED_SOURCE_ORDER", "bool", False, LOADER_SELECTION, "Preserve source order in staged hydration."),

    # UNET loader controls.
    "COMFYMODAL_V2_UNET_FASTSAFETENSORS": _spec("COMFYMODAL_V2_UNET_FASTSAFETENSORS", "bool", False, LOADER_SELECTION, "Use the FastSafeTensor UNET loader."),
    "COMFYMODAL_V2_UNET_META_DIRECT": _spec("COMFYMODAL_V2_UNET_META_DIRECT", "bool", False, LOADER_SELECTION, "Use the meta-direct UNET loader."),
    "COMFYMODAL_V2_STAGED_SAFETENSORS": _spec("COMFYMODAL_V2_STAGED_SAFETENSORS", "bool", False, LOADER_SELECTION, "Use staged safetensors UNET hydration."),
    "COMFYMODAL_V2_NATIVE_FAST_DISK_UNET": _spec("COMFYMODAL_V2_NATIVE_FAST_DISK_UNET", "bool", False, LOADER_SELECTION, "Use the native fast-disk UNET loader."),
    "COMFYMODAL_V2_SNAPSHOT_EXCLUDE_UNET": _spec("COMFYMODAL_V2_SNAPSHOT_EXCLUDE_UNET", "bool", False, SNAPSHOT_POLICY, "Exclude UNET from the snapshot identity."),
    "COMFYMODAL_V2_UNET_ACTIVATION_MODE": _spec("COMFYMODAL_V2_UNET_ACTIVATION_MODE", "enum", "late", EXECUTION_POLICY, "UNET activation boundary.", choices=("late", "clip_encode_start", "clip_gpu_ready")),
    "COMFYMODAL_V2_UNET_FASTSAFE_THREADS": _spec("COMFYMODAL_V2_UNET_FASTSAFE_THREADS", "int", 8, LOADER_SELECTION, "UNET FastSafeTensor reader threads."),
    "COMFYMODAL_V2_UNET_FASTSAFE_BLOCK_BYTES": _spec("COMFYMODAL_V2_UNET_FASTSAFE_BLOCK_BYTES", "int", 268435456, LOADER_SELECTION, "UNET FastSafeTensor block size in bytes."),
    "COMFYMODAL_V2_UNET_FASTSAFE_BBUF_KB": _spec("COMFYMODAL_V2_UNET_FASTSAFE_BBUF_KB", "int", 524288, LOADER_SELECTION, "UNET FastSafeTensor bounce-buffer size in KiB."),
    "COMFYMODAL_V2_UNET_PINNED_STAGING": _spec("COMFYMODAL_V2_UNET_PINNED_STAGING", "bool", False, LOADER_SELECTION, "Use pinned memory for UNET staging."),
    "COMFYMODAL_V2_UNET_STAGING_CHUNK_MB": _spec("COMFYMODAL_V2_UNET_STAGING_CHUNK_MB", "int", 512, LOADER_SELECTION, "UNET staging chunk size in MiB."),

    # R44B first-class request-time FastSafe controls (per-role flags default
    # to the master flag when absent; see comfymodal_runtime.request_fastpath).
    "COMFYMODAL_V2_REQUEST_FASTSAFE": _spec("COMFYMODAL_V2_REQUEST_FASTSAFE", "bool", False, LOADER_SELECTION, "Enable the R44B request-time FastSafe loader lane."),
    "COMFYMODAL_V2_REQUEST_CLIP_FASTSAFE": _spec("COMFYMODAL_V2_REQUEST_CLIP_FASTSAFE", "bool", False, LOADER_SELECTION, "Request-time FastSafe direct-GPU CLIP transport (defaults to REQUEST_FASTSAFE)."),
    "COMFYMODAL_V2_REQUEST_UNET_FASTSAFE": _spec("COMFYMODAL_V2_REQUEST_UNET_FASTSAFE", "bool", False, LOADER_SELECTION, "Request-time FastSafe direct-GPU UNET transport (defaults to REQUEST_FASTSAFE)."),
    "COMFYMODAL_V2_REQUEST_UNET_SOURCE_PREP": _spec("COMFYMODAL_V2_REQUEST_UNET_SOURCE_PREP", "bool", False, LOADER_SELECTION, "Request-time UNET CPU/page-cache source preparation (defaults to REQUEST_FASTSAFE)."),
    "COMFYMODAL_V2_REQUEST_CLIP_FASTSAFE_NATIVE_ADOPT": _spec("COMFYMODAL_V2_REQUEST_CLIP_FASTSAFE_NATIVE_ADOPT", "bool", False, LOADER_SELECTION, "R44F: construct the native CLIP on a meta skeleton and bind served FastSafe CUDA tensors assign-style (zero-copy, single residency); requires REQUEST_CLIP_FASTSAFE and defaults OFF."),
    "COMFYMODAL_V2_CLIP_SAME_DTYPE_RESIDENCY": _spec("COMFYMODAL_V2_CLIP_SAME_DTYPE_RESIDENCY", "bool", False, LOADER_SELECTION, "R44I3 ARM A: adopt the CHECKPOINT dtype as the live CLIP residency dtype (BF16 checkpoint -> BF16 live) via the parity same_storage_assign lane; overrides the text_encoder_dtype policy for the fast arm only. Requires REQUEST_CLIP_FASTSAFE + NATIVE_ADOPT and defaults OFF."),
    "COMFYMODAL_V2_CLIP_FP16_VOLUME_TWIN": _spec("COMFYMODAL_V2_CLIP_FP16_VOLUME_TWIN", "bool", False, LOADER_SELECTION, "R44I3 ARM B: prefer a preconverted <name>.fp16.safetensors sibling on the models volume (written once by tools/preconvert_clip_fp16_volume.py) so the parity lane binds FP16->FP16 with zero conversion; falls back to the original checkpoint when the twin is absent."),

    # VAE and preload/warmup controls.
    "COMFYMODAL_V2_VAE_POLICY": _spec("COMFYMODAL_V2_VAE_POLICY", "enum", "v1", LOADER_SELECTION, "VAE restore policy.", choices=("v0", "v1")),
    "COMFYMODAL_V2_VAE_ACTIVATION_MODE": _spec("COMFYMODAL_V2_VAE_ACTIVATION_MODE", "enum", "late", EXECUTION_POLICY, "VAE activation boundary.", choices=("late", "sampling_end", "sampling_first_step")),
    "COMFYMODAL_V2_VAE_SNAPSHOT": _spec("COMFYMODAL_V2_VAE_SNAPSHOT", "bool", False, SNAPSHOT_POLICY, "Include VAE weights in the snapshot."),
    "COMFYMODAL_V2_VAE_PREFETCH_MODE": _spec("COMFYMODAL_V2_VAE_PREFETCH_MODE", "enum", "off", EXECUTION_POLICY, "VAE prefetch policy.", choices=("off", "on", "auto")),
    "COMFYMODAL_V2_VAE_EARLY_START_MS": _spec("COMFYMODAL_V2_VAE_EARLY_START_MS", "int", 0, EXECUTION_POLICY, "VAE early-start lead time in milliseconds."),
    "COMFYMODAL_PRELOAD_MODE": _spec("COMFYMODAL_PRELOAD_MODE", "enum", "off", EXECUTION_POLICY, "CPU preload arm selected during restore.", choices=("off", "clip_only", "unet_only", "unet_vae_only", "vae", "default", "sequential", "workers_1", "workers_2", "async_no_wait", "budgeted_1500ms")),
    "COMFYMODAL_V2_MODEL_PRELOAD": _spec("COMFYMODAL_V2_MODEL_PRELOAD", "bool", True, EXECUTION_POLICY, "Enable model preload."),
    "COMFYMODAL_V2_GRAPH_PRELOAD": _spec("COMFYMODAL_V2_GRAPH_PRELOAD", "bool", True, EXECUTION_POLICY, "Enable graph preload."),
    "COMFYMODAL_V2_EXECUTION_PREFILL": _spec("COMFYMODAL_V2_EXECUTION_PREFILL", "bool", True, EXECUTION_POLICY, "Enable execution prefill."),
    "COMFYMODAL_V2_CHECKPOINT_PREWARM": _spec("COMFYMODAL_V2_CHECKPOINT_PREWARM", "bool", False, EXECUTION_POLICY, "Prewarm checkpoint payloads."),
    "COMFYMODAL_V2_CHECKPOINT_PREWARM_THREADS": _spec("COMFYMODAL_V2_CHECKPOINT_PREWARM_THREADS", "int", 4, EXECUTION_POLICY, "Checkpoint prewarm thread count."),
    "COMFYMODAL_V2_CHECKPOINT_PREWARM_CHUNK_MB": _spec("COMFYMODAL_V2_CHECKPOINT_PREWARM_CHUNK_MB", "int", 8, EXECUTION_POLICY, "Checkpoint prewarm read chunk size in MiB."),
    "COMFYMODAL_V2_CHECKPOINT_PREWARM_MAX_MB": _spec("COMFYMODAL_V2_CHECKPOINT_PREWARM_MAX_MB", "int", 0, EXECUTION_POLICY, "Checkpoint prewarm byte budget in MiB."),
    "COMFYMODAL_V2_CHECKPOINT_PREWARM_MAX_MS": _spec("COMFYMODAL_V2_CHECKPOINT_PREWARM_MAX_MS", "int", 0, EXECUTION_POLICY, "Checkpoint prewarm wall-time budget in milliseconds."),
    "COMFYMODAL_V2_CONDITIONING_CACHE_PREFETCH": _spec("COMFYMODAL_V2_CONDITIONING_CACHE_PREFETCH", "bool", True, CACHE_POLICY, "Prefetch conditioning-cache entries."),
    "COMFYMODAL_ENABLE_WARMUP": _spec("COMFYMODAL_ENABLE_WARMUP", "bool", True, EXECUTION_POLICY, "Enable runtime warmup."),
    "COMFYMODAL_DIRECT_WARMUP_LOAD_UNET": _spec("COMFYMODAL_DIRECT_WARMUP_LOAD_UNET", "bool", False, EXECUTION_POLICY, "Load UNET during direct warmup."),
    "COMFYMODAL_DIRECT_WARMUP_LOAD_CLIP": _spec("COMFYMODAL_DIRECT_WARMUP_LOAD_CLIP", "bool", False, EXECUTION_POLICY, "Load CLIP during direct warmup."),
    "COMFYMODAL_DIRECT_WARMUP_CLIP_ENCODE": _spec("COMFYMODAL_DIRECT_WARMUP_CLIP_ENCODE", "bool", False, EXECUTION_POLICY, "Run the direct warmup CLIP encode."),

    # Cache and persistence controls.
    "COMFYMODAL_V2_EXACT_CACHE_PERSIST": _spec("COMFYMODAL_V2_EXACT_CACHE_PERSIST", "bool", True, CACHE_POLICY, "Persist exact conditioning-cache state."),
    "COMFYMODAL_V2_BACKGROUND_PERSISTENCE": _spec("COMFYMODAL_V2_BACKGROUND_PERSISTENCE", "bool", True, CACHE_POLICY, "Persist background runtime state."),
    "COMFYMODAL_V2_CLIP_CONDITIONING_CACHE": _spec("COMFYMODAL_V2_CLIP_CONDITIONING_CACHE", "bool", False, CACHE_POLICY, "Persist CLIP conditioning across requests."),
    "COMFYMODAL_EXACT_CLIP_CONDITIONING_CACHE": _spec("COMFYMODAL_EXACT_CLIP_CONDITIONING_CACHE", "bool", False, CACHE_POLICY, "Legacy exact CLIP conditioning-cache alias."),
    "COMFYMODAL_V2_CONDITIONING_CACHE_ASYNC_LRU": _spec("COMFYMODAL_V2_CONDITIONING_CACHE_ASYNC_LRU", "bool", False, CACHE_POLICY, "Use asynchronous LRU conditioning-cache eviction."),
    "COMFYMODAL_V2_PROMPT_SIGNATURE_CACHE": _spec("COMFYMODAL_V2_PROMPT_SIGNATURE_CACHE", "bool", True, CACHE_POLICY, "Cache conditioning by prompt signature."),

    # Restore, snapshot, and runtime policy controls.
    "COMFYMODAL_MINIMAL_RESTORE": _spec("COMFYMODAL_MINIMAL_RESTORE", "bool", True, EXECUTION_POLICY, "Select the E37 minimal restore path."),
    "COMFYMODAL_V2_CLEAN_LANE": _spec("COMFYMODAL_V2_CLEAN_LANE", "bool", False, EXECUTION_POLICY, "Compatibility clean-lane selector."),
    "COMFYMODAL_V2_E37_CLEAN_LANE": _spec("COMFYMODAL_V2_E37_CLEAN_LANE", "bool", False, EXECUTION_POLICY, "E37 clean-lane runtime selector."),
    "COMFYMODAL_V2_E37_STRICT_PROOF": _spec("COMFYMODAL_V2_E37_STRICT_PROOF", "bool", False, DEPRECATED_DIAGNOSTIC, "Enable fail-closed E37 proof validation."),
    "COMFYMODAL_V2_E37_EXPECTED_OUTPUT_SHA": _spec("COMFYMODAL_V2_E37_EXPECTED_OUTPUT_SHA", "string", "", DEPRECATED_DIAGNOSTIC, "Expected output digest for E37 proof validation."),
    "COMFYMODAL_V2_SINGLE_USE_CONTAINERS": _spec("COMFYMODAL_V2_SINGLE_USE_CONTAINERS", "bool", False, EXECUTION_POLICY, "Use a fresh container for every request."),
    "COMFYMODAL_V2_CRITICAL_PATH_LEDGER": _spec("COMFYMODAL_V2_CRITICAL_PATH_LEDGER", "bool", True, TIMING_DIAGNOSTICS, "Enable the canonical critical-path ledger."),
    "COMFYMODAL_V2_GANTT_TELEMETRY": _spec("COMFYMODAL_V2_GANTT_TELEMETRY", "bool", False, TIMING_DIAGNOSTICS, "Emit Gantt timing telemetry."),
    "COMFYMODAL_V2_CRITICAL_GPU_COORDINATION": _spec("COMFYMODAL_V2_CRITICAL_GPU_COORDINATION", "bool", False, EXECUTION_POLICY, "Coordinate the critical GPU lane."),
    "COMFYMODAL_V2_THREAD_POLICY": _spec("COMFYMODAL_V2_THREAD_POLICY", "string", "TBASE", EXECUTION_POLICY, "Runtime thread-shape policy."),
    "COMFYMODAL_V2_RELEASE_GPU_AFTER_REQUEST": _spec("COMFYMODAL_V2_RELEASE_GPU_AFTER_REQUEST", "bool", True, EXECUTION_POLICY, "Release GPU memory after each request."),
    "COMFYMODAL_V2_FAST_COLD_ORCHESTRATION": _spec("COMFYMODAL_V2_FAST_COLD_ORCHESTRATION", "bool", False, EXECUTION_POLICY, "Select fast cold-start orchestration."),
    "COMFYMODAL_V2_GPU_FAST_RETURN": _spec("COMFYMODAL_V2_GPU_FAST_RETURN", "bool", True, EXECUTION_POLICY, "Skip redundant GPU load bookkeeping on proven-ready models."),
    "COMFYMODAL_V2_EVICT_MODELS_BEFORE_SNAPSHOT": _spec("COMFYMODAL_V2_EVICT_MODELS_BEFORE_SNAPSHOT", "bool", False, SNAPSHOT_POLICY, "Evict models before snapshot capture."),
    "COMFYMODAL_V2_CPU_MODEL_SNAPSHOT": _spec("COMFYMODAL_V2_CPU_MODEL_SNAPSHOT", "bool", False, SNAPSHOT_POLICY, "Capture CPU-resident model weights."),
    "COMFYMODAL_V2_SNAPSHOT_MODEL_ORDER": _spec("COMFYMODAL_V2_SNAPSHOT_MODEL_ORDER", "string", "O0", SNAPSHOT_POLICY, "Snapshot model load order."),
    "COMFYMODAL_V2_ENV_PROFILE": _spec("COMFYMODAL_V2_ENV_PROFILE", "enum", "inherit", EXECUTION_POLICY, "Runtime environment profile.", choices=("production", "diagnostic", "inherit")),
    "COMFYMODAL_V2_PREFILL_LANES": _spec("COMFYMODAL_V2_PREFILL_LANES", "enum", "critical", EXECUTION_POLICY, "Prefill lane policy.", choices=("none", "critical", "full")),
    "COMFYMODAL_V2_PREFILL_WAIT_FOR_UNET": _spec("COMFYMODAL_V2_PREFILL_WAIT_FOR_UNET", "bool", False, EXECUTION_POLICY, "Wait for UNET readiness before prefill."),
    "COMFYMODAL_V2_PERSISTENT_LOCAL_HANDLE": _spec("COMFYMODAL_V2_PERSISTENT_LOCAL_HANDLE", "bool", True, SNAPSHOT_POLICY, "Keep a persistent local snapshot handle."),
    "COMFYMODAL_V2_EVICT_RETAIN_ROLE": _spec("COMFYMODAL_V2_EVICT_RETAIN_ROLE", "enum", "none", SNAPSHOT_POLICY, "Role retained after model eviction.", choices=("none", "clip", "unet", "clip_vae")),
    "COMFYMODAL_V2_EVICT_RESTORE_IDLE_SECONDS": _spec("COMFYMODAL_V2_EVICT_RESTORE_IDLE_SECONDS", "int", 0, SNAPSHOT_POLICY, "Idle seconds before restore eviction."),
    "COMFYMODAL_V2_ATOMIC_PROFILE": _spec("COMFYMODAL_V2_ATOMIC_PROFILE", "bool", False, EXECUTION_POLICY, "Atomic runtime profile selector."),
    "COMFYMODAL_V2_SCOPED_CUDA_READINESS": _spec("COMFYMODAL_V2_SCOPED_CUDA_READINESS", "bool", False, EXECUTION_POLICY, "Scope CUDA readiness checks to the request."),
    "COMFYMODAL_V2_INPUT_TYPES_WARM": _spec("COMFYMODAL_V2_INPUT_TYPES_WARM", "bool", True, EXECUTION_POLICY, "Warm input-type resolution at import."),
    "COMFYMODAL_V2_RESTORE_TOTAL_VRAM_FROZEN": _spec("COMFYMODAL_V2_RESTORE_TOTAL_VRAM_FROZEN", "bool", False, EXECUTION_POLICY, "Use the frozen-total-VRAM restore arm."),
    "COMFYMODAL_V2_HIGH_HEADROOM_EMPTY_CACHE_BYPASS": _spec("COMFYMODAL_V2_HIGH_HEADROOM_EMPTY_CACHE_BYPASS", "bool", False, EXECUTION_POLICY, "Bypass empty-cache calls with high headroom."),
    "COMFYMODAL_V2_EXECUTION_UNET_H2D_DELAY_MS": _spec("COMFYMODAL_V2_EXECUTION_UNET_H2D_DELAY_MS", "int", 0, EXECUTION_POLICY, "Execution-phase UNET host-to-device delay."),
    "COMFYMODAL_V2_UNET_READ_H2D_PIPELINE": _spec("COMFYMODAL_V2_UNET_READ_H2D_PIPELINE", "string", "", LOADER_SELECTION, "UNET read/H2D pipeline selector."),
    "COMFYMODAL_V2_UNET_PINNED_RING": _spec("COMFYMODAL_V2_UNET_PINNED_RING", "string", "", LOADER_SELECTION, "Pinned-ring UNET loader selector."),
    "COMFYMODAL_V2_C9QD_EXTRAS": _spec("COMFYMODAL_V2_C9QD_EXTRAS", "bool", False, LOADER_SELECTION, "C9 queue-depth loader extras."),
    "COMFYMODAL_V2_PIN_UNET_TRANSFER": _spec("COMFYMODAL_V2_PIN_UNET_TRANSFER", "bool", False, EXECUTION_POLICY, "Pin UNET transfer buffers."),
    "COMFYMODAL_V2_UNET_QUIESCED_TRANSFER": _spec("COMFYMODAL_V2_UNET_QUIESCED_TRANSFER", "bool", False, EXECUTION_POLICY, "Delay UNET transfer until sampling quiesces."),

    # Legacy comfyapp behavior switches that remain live on the runtime side.
    "COMFYMODAL_EXECUTION_BACKEND": _spec("COMFYMODAL_EXECUTION_BACKEND", "string", "in_process", EXECUTION_POLICY, "Execution backend selector."),
    "COMFYMODAL_ACTUAL_LOAD_MODE": _spec("COMFYMODAL_ACTUAL_LOAD_MODE", "enum", "clip_vae_only", EXECUTION_POLICY, "Actual model-load role selector.", choices=("off", "clip_vae_only", "unet_only", "unet_vae_only")),
    "COMFYMODAL_RESTORE_DIRECT_CLIP_POLICY": _spec("COMFYMODAL_RESTORE_DIRECT_CLIP_POLICY", "enum", "auto", EXECUTION_POLICY, "Direct restore CLIP policy.", choices=("auto", "off", "load_only", "load_and_encode")),
    "COMFYMODAL_SAFETENSORS_READ_MODE": _spec("COMFYMODAL_SAFETENSORS_READ_MODE", "enum", "normal", LOADER_SELECTION, "Safetensors read strategy.", choices=("auto", "normal", "read_bytes")),
    "COMFYMODAL_FASTPATH_V21621": _spec("COMFYMODAL_FASTPATH_V21621", "bool", True, EXECUTION_POLICY, "Enable the v2.16.21 cold-start fast path."),
    "COMFYMODAL_FASTPATH_V21621_BACKGROUND_UNET": _spec("COMFYMODAL_FASTPATH_V21621_BACKGROUND_UNET", "bool", True, EXECUTION_POLICY, "Enable the fast-path background UNET arm."),
    "COMFYMODAL_FASTPATH_V21621_CLIP_LOAD_ONLY": _spec("COMFYMODAL_FASTPATH_V21621_CLIP_LOAD_ONLY", "bool", True, EXECUTION_POLICY, "Use load-only behavior for fast-path CLIP."),
    "COMFYMODAL_FASTPATH_V21621_CLIP_READ_BYTES": _spec("COMFYMODAL_FASTPATH_V21621_CLIP_READ_BYTES", "bool", True, LOADER_SELECTION, "Use byte reads for fast-path CLIP."),
    "COMFYMODAL_FUSE_READ_GOVERNOR": _spec("COMFYMODAL_FUSE_READ_GOVERNOR", "bool", False, LOADER_SELECTION, "Enable the FUSE read governor."),
    "COMFYMODAL_DEFER_VAE_ACTUAL_LOAD_DURING_RBG_UNET": _spec("COMFYMODAL_DEFER_VAE_ACTUAL_LOAD_DURING_RBG_UNET", "bool", True, EXECUTION_POLICY, "Defer VAE load while background UNET runs."),
    "COMFYMODAL_DEFER_VAE_INCLUDING_PRODUCTION_UNET": _spec("COMFYMODAL_DEFER_VAE_INCLUDING_PRODUCTION_UNET", "bool", False, EXECUTION_POLICY, "Defer VAE including the production UNET path."),
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

    When ``COMFYMODAL_GOLDEN_PIPELINE`` resolves true, every role is
    requested as the single canonical Golden arm ``golden_qd4``; the
    per-role legacy precedence below is only reached when the Golden
    pipeline is disabled.

    Legacy precedence (Golden OFF).  Weight residency comes first: when the
    snapshot does NOT exclude CLIP weights, CLIP is ``snapshot_resident``
    (E37-style composition — weights ride the memory snapshot, so no
    request-time file transport exists to name); likewise UNET is
    ``cpu_snapshot_native`` when UNET is not excluded from the snapshot.
    Otherwise CLIP is ``qd4_reader`` first, then
    ``fastsafetensors_direct_gpu``, ``staged_hydration``, ``speculative_clip``, and
    finally ``native_comfy``.  UNET is ``fastsafetensors`` first, then
    ``meta_direct``, then the native CPU-snapshot/fast-disk arm, and finally
    ``native_comfy``.      VAE selects ``policy_v1`` only when the V1 policy and
    VAE snapshot are both active; otherwise it is ``native_comfy``.

    R44B request-time FastSafe precedence sits between the Golden branch and
    the legacy arms: when ``COMFYMODAL_V2_REQUEST_FASTSAFE`` resolves on AND
    the role sub-flag is on (a per-role flag absent from the environment
    follows the master flag, mirroring ``request_fastpath``), CLIP is
    requested as ``fastsafetensors_direct_gpu`` and UNET as
    ``fastsafetensors`` — these lanes deliver weights at request time, so
    they must outrank the metadata-only snapshot-residency arms.
    """
    if role not in ROLES:
        raise ValueError("role must be one of: clip, unet, vae")
    config = resolve() if resolved is None else resolved
    if config.get("COMFYMODAL_GOLDEN_PIPELINE"):
        return "golden_qd4"

    def _r44b_role_on(flag: str) -> bool:
        # Compound-flag semantics mirrored from request_fastpath: an absent
        # per-role flag follows the master REQUEST_FASTSAFE value.
        if config.sources.get(flag) == "default":
            return bool(config.get("COMFYMODAL_V2_REQUEST_FASTSAFE"))
        return bool(config.get(flag))

    if bool(config.get("COMFYMODAL_V2_REQUEST_FASTSAFE")):
        if role == "clip" and _r44b_role_on("COMFYMODAL_V2_REQUEST_CLIP_FASTSAFE"):
            return "fastsafetensors_direct_gpu"
        if role == "unet" and _r44b_role_on("COMFYMODAL_V2_REQUEST_UNET_FASTSAFE"):
            return "fastsafetensors"
    if role == "clip":
        if not config.get("COMFYMODAL_V2_CLIP_SNAPSHOT_EXCLUDE_WEIGHTS"):
            # E37-style composition: CLIP weights ride the memory snapshot,
            # so no request-time file transport exists to name.
            return "snapshot_resident"
        if config.get("COMFYMODAL_V2_CLIP_QD_READER"):
            return "qd4_reader"
        if config.get("COMFYMODAL_V2_CLIP_FAST_HYDRATION"):
            return "fastsafetensors_direct_gpu"
        if config.get("COMFYMODAL_V2_CLIP_STAGED_HYDRATION"):
            return "staged_hydration"
        if config.get("COMFYMODAL_V2_SPECULATIVE_CLIP_HYDRATION"):
            return "speculative_clip"
        return "native_comfy"
    if role == "unet":
        if not config.get("COMFYMODAL_V2_SNAPSHOT_EXCLUDE_UNET"):
            # Weights ride the memory snapshot; cpu_snapshot_native is the
            # canonical arm for snapshot-delivered UNET weights.
            return "cpu_snapshot_native"
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


# ── R42 five-layer configuration truth ─────────────────────────────────────
#
# The E40 remote evidence exposed a hidden divergence class: the deploy
# RECORD projected post-selector values ("1") for three controls while the
# deployed container environment carried the resolved profile values ("0"),
# so the runtime authority resolved false while provenance claimed true.
# R42 requires every Golden-semantics control to be represented explicitly
# across five layers:
#
#   requested         profile/CLI intent (what the operator asked for)
#   resolved          ConfigResolver output (profile chain resolution)
#   deployed          the raw value actually present in container env
#   semantic_effective  the value the runtime acts on AFTER documented policy
#                       mapping (e.g. a legacy control superseded by Golden)
#   observed          what the runtime actually did (loader selection etc.)
#
# A row agrees when requested==resolved==deployed==semantic_effective, or
# when every disagreement carries an explicit documented reason.  An
# agreement=false row with an empty reason is a hard validation failure.

_GOLDEN_TRUTH_CONTROLS: tuple[str, ...] = (
    "COMFYMODAL_GOLDEN_PIPELINE",
    "COMFYMODAL_V2_CLIP_QD_READER",
    "COMFYMODAL_V2_CLIP_QD_QD",
    "COMFYMODAL_V2_CLIP_QD_BLOCK_MIB",
    "COMFYMODAL_V2_CLIP_SNAPSHOT_EXCLUDE_WEIGHTS",
    "COMFYMODAL_V2_FAST_COLD_ORCHESTRATION",
    "COMFYMODAL_V2_UNET_FASTSAFETENSORS",
    "COMFYMODAL_V2_SPECULATIVE_CLIP_HYDRATION",
    "COMFYMODAL_V2_EXECUTION_PREFILL",
    "COMFYMODAL_V2_BACKGROUND_PERSISTENCE",
    "COMFYMODAL_V2_CHECKPOINT_PREWARM",
    "COMFYMODAL_V2_MODEL_PRELOAD",
    "COMFYMODAL_V2_GRAPH_PRELOAD",
    "COMFYMODAL_MINIMAL_RESTORE",
    "COMFYMODAL_V2_CRITICAL_PATH_LEDGER",
    "COMFYMODAL_V2_SINGLE_USE_CONTAINERS",
    "COMFYMODAL_V2_EXACT_CACHE_PERSIST",
    "COMFYMODAL_V2_VAE_POLICY",
    "COMFYMODAL_V2_NATIVE_FAST_DISK_UNET",
    "COMFYMODAL_V2_CPU_MODEL_SNAPSHOT",
    "COMFYMODAL_V2_SNAPSHOT_EXCLUDE_UNET",
    "COMFYMODAL_V2_VAE_SNAPSHOT",
)

_LEGACY_CONTROL_MAPPINGS: dict[str, dict[str, Any]] = {
    # E40 anomaly control 1: under the Golden snapshot contract ALL role
    # weight values are excluded regardless of this legacy CLIP-only flag,
    # so the semantic effective value is True-equivalent even when the
    # deployed/resolved value is False.
    "COMFYMODAL_V2_CLIP_SNAPSHOT_EXCLUDE_WEIGHTS": {
        "control": "COMFYMODAL_V2_CLIP_SNAPSHOT_EXCLUDE_WEIGHTS",
        "semantic_effective": True,
        "reason": "superseded_by_golden_snapshot_policy",
        "note": (
            "Golden snapshot excludes CLIP/UNET/VAE weight values by policy; "
            "the legacy CLIP-only exclusion flag no longer gates behavior."
        ),
    },
    # E40 anomaly control 2: orchestration is owned by the deterministic
    # Golden pipeline state machine; the legacy fast-cold orchestrator is
    # not on the Golden path.
    "COMFYMODAL_V2_FAST_COLD_ORCHESTRATION": {
        "control": "COMFYMODAL_V2_FAST_COLD_ORCHESTRATION",
        "semantic_effective": False,
        "reason": "superseded_by_golden_pipeline_orchestration",
        "note": (
            "Golden pipeline scheduling replaces the legacy fast-cold "
            "orchestration arm entirely."
        ),
    },
    # E40 anomaly control 3: UNET nominal transport is golden_qd4; the
    # FastSafeTensor UNET loader survives only as a DEGRADED fallback.
    "COMFYMODAL_V2_UNET_FASTSAFETENSORS": {
        "control": "COMFYMODAL_V2_UNET_FASTSAFETENSORS",
        "semantic_effective": False,
        "reason": "superseded_by_golden_qd4_loader",
        "note": (
            "golden_qd4 is the only nominal UNET transport; fastsafetensors "
            "remains a production correctness fallback (never nominal)."
        ),
    },
}


def explain_legacy_control(name: str) -> dict[str, Any] | None:
    """Return the documented Golden policy mapping for a legacy control.

    Returns ``None`` for controls with no special mapping (their semantic
    effective value equals their resolved/deployed value).
    """
    return _LEGACY_CONTROL_MAPPINGS.get(str(name))


def build_config_truth(
    resolved: ResolvedConfig,
    *,
    requested_overrides: Mapping[str, Any] | None = None,
    observed: Mapping[str, Any] | None = None,
    deployed_env: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the five-layer truth block for every Golden-semantics control.

    ``resolved`` supplies the resolved and deployed layers (deployed falls
    back to the resolved value when ``deployed_env`` is not supplied).
    ``requested_overrides`` carries profile/CLI intent where it differs from
    resolution.  ``observed`` carries runtime-observed values (e.g. loader
    selection) keyed by control name.

    Each row: {name, requested, resolved, deployed, semantic_effective,
    observed, agreement, reason}.  ``agreement`` is False only when two
    layers that are REQUIRED to match differ without a documented reason;
    documented policy mappings (see :func:`explain_legacy_control`) keep the
    row agreeing while recording the divergence reason explicitly.
    """
    overrides = dict(requested_overrides or {})
    observed_map = dict(observed or {})
    env = dict(deployed_env) if deployed_env is not None else None
    golden_enabled = bool(resolved.get("COMFYMODAL_GOLDEN_PIPELINE"))
    rows: list[dict[str, Any]] = []
    unexplained: list[str] = []
    for name in _GOLDEN_TRUTH_CONTROLS:
        spec = GOLDEN_CONTROL_FLAGS.get(name)
        if spec is None:
            continue
        resolved_value = resolved.get(name, spec["default"])
        if env is not None and name in env:
            valid, deployed_value = _coerce(env[name], spec)
            deployed_value = deployed_value if valid else resolved_value
        else:
            deployed_value = resolved_value
        requested_value = overrides.get(name, resolved_value)
        override_reason = ""
        if isinstance(requested_value, Mapping):
            override_reason = str(requested_value.get("reason", "") or "")
            requested_value = requested_value.get("value")
        requested_value = _coerce(requested_value, spec)[1]
        mapping = _LEGACY_CONTROL_MAPPINGS.get(name) if golden_enabled else None
        if mapping is not None:
            semantic_effective = mapping["semantic_effective"]
            reason = mapping["reason"]
        else:
            semantic_effective = resolved_value
            reason = ""
        observed_value = observed_map.get(name)
        agreement = (
            requested_value == resolved_value == deployed_value
            and semantic_effective == resolved_value
        )
        if override_reason:
            reason = override_reason
        if not agreement and not reason:
            unexplained.append(name)
        rows.append(
            {
                "name": name,
                "requested": requested_value,
                "resolved": resolved_value,
                "deployed": deployed_value,
                "semantic_effective": semantic_effective,
                "observed": observed_value,
                "agreement": agreement,
                "reason": reason,
            }
        )
    return {
        "controls": rows,
        "unexplained_mismatches": sorted(unexplained),
        "fingerprint": hashlib.sha256(
            json.dumps(rows, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
        ).hexdigest(),
    }


__all__ = [
    "ALLOWLIST_UNREGISTERED",
    "GOLDEN_CONTROL_FLAGS",
    "ResolvedConfig",
    "build_config_truth",
    "detect_unregistered_mutations",
    "explain_legacy_control",
    "reconcile",
    "requested_loader",
    "resolve",
]
