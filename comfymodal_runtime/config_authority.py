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
    # Golden runtime activation must cross Modal's class-env boundary before
    # ComfyUI imports model modules that capture AIMDO state.
    "COMFYMODAL_V2_GOLDEN_ENABLE_DYNAMIC_VRAM": _spec(
        "COMFYMODAL_V2_GOLDEN_ENABLE_DYNAMIC_VRAM",
        "bool",
        False,
        EXECUTION_POLICY,
        "Enable the fail-closed Golden DynamicVRAM activation path.",
    ),
    "COMFYMODAL_V2_GOLDEN_WORKFLOW_HASH_CHECK": _spec(
        "COMFYMODAL_V2_GOLDEN_WORKFLOW_HASH_CHECK",
        "bool",
        True,
        EXECUTION_POLICY,
        "Require Golden workflow SHA equality during request setup; disabled is fail-closed.",
    ),
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
    "COMFYMODAL_GOLDEN_MINIMAL_RESTORE": _spec("COMFYMODAL_GOLDEN_MINIMAL_RESTORE", "bool", False, EXECUTION_POLICY, "Experimental Golden Parallel minimal post-snapshot restore. Default OFF."),
    "COMFYMODAL_GOLDEN_IO_PROCESS_V2": _spec("COMFYMODAL_GOLDEN_IO_PROCESS_V2", "bool", False, EXECUTION_POLICY, "Faithful two-process Golden I/O (V2): one reusable process-shared host backing registered for direct parent H2D. Default OFF."),
    "COMFYMODAL_GOLDEN_IO_PROCESS_V2_BACKING": _spec("COMFYMODAL_GOLDEN_IO_PROCESS_V2_BACKING", "enum", "posix", EXECUTION_POLICY, "Golden I/O Process V2 backing selector; no cross-arm fallback.", choices=("posix", "sysv")),
    "COMFYMODAL_GOLDEN_IO_PROCESS_V2_SOURCE_GEOMETRY": _spec("COMFYMODAL_GOLDEN_IO_PROCESS_V2_SOURCE_GEOMETRY", "enum", "qd4_32", EXECUTION_POLICY, "Golden I/O Process V2 child source-reader geometry; parent H2D remains unchanged.", choices=("qd4_32", "qd2_128", "qd4_64")),
    "COMFYMODAL_GOLDEN_IO_PROCESS_V2_STREAMING": _spec("COMFYMODAL_GOLDEN_IO_PROCESS_V2_STREAMING", "bool", False, EXECUTION_POLICY, "Golden I/O V2 C0 bounded shared-pinned streaming arena selector; requires the V2 switch and has no cross-arm fallback. Default OFF."),
    "COMFYMODAL_GOLDEN_IO_PROCESS_V2_PERSISTENT_FDS": _spec("COMFYMODAL_GOLDEN_IO_PROCESS_V2_PERSISTENT_FDS", "bool", False, EXECUTION_POLICY, "Golden I/O V2 C0 child persistent positioned-FD cache selector: reuse one descriptor per normalized (path, producer_id) instead of per-fill open/close. Default OFF (control); requires the C0 streaming arm and has no cross-arm fallback."),
    "COMFYMODAL_GOLDEN_IO_PROCESS_V2_SOURCE_ENGINE": _spec("COMFYMODAL_GOLDEN_IO_PROCESS_V2_SOURCE_ENGINE", "enum", "preadv", EXECUTION_POLICY, "Golden I/O V2 C0 child byte-producer engine: preadv (default positioned-read control) or mmap_fresh (frozen mmap engine: independent reader processes with a persistent per-(path,producer) descriptor, a fresh exact-window PROT_READ|MAP_PRIVATE mapping per read, native libc.memcpy into the leased slot, synchronous munmap, and a 4 ms global launch-spacing floor). No cross-arm fallback.", choices=("preadv", "mmap_fresh")),
    "COMFYMODAL_GOLDEN_C0_MMAP_LIFECYCLE": _spec("COMFYMODAL_GOLDEN_C0_MMAP_LIFECYCLE", "enum", "fresh", EXECUTION_POLICY, "TESTING9-only C0 mmap lifetime diagnostic: fresh exact-window per logical read, whole-file mapping per model/path, or aligned approximately 1 GiB epoch mappings. Default fresh preserves the current C0 lifecycle; requires mmap_fresh and is never a production fallback.", choices=("fresh", "whole", "epoch")),
    "COMFYMODAL_GOLDEN_C0_SOURCE_THREADS": _spec("COMFYMODAL_GOLDEN_C0_SOURCE_THREADS", "bool", False, EXECUTION_POLICY, "TESTING9 source-thread arm: one CUDA-sterile process with four persistent self-serving reader threads and a 16 x 64 MiB shared arena. Restore/deploy-owned; no fallback.",),
    "COMFYMODAL_GOLDEN_C0_CHILD_VIZTRACER": _spec("COMFYMODAL_GOLDEN_C0_CHILD_VIZTRACER", "bool", False, TIMING_DIAGNOSTICS, "Forensic child-only VizTracer capture for the C0 CUDA-sterile reader process: traces source worker/writer/positioned-read boundaries and writes a deterministic child trace the parent bundles. Default OFF; trace config only, never execution semantics."),
    "COMFYMODAL_GOLDEN_C0_PRIVATE_SPLIT_IO": _spec("COMFYMODAL_GOLDEN_C0_PRIVATE_SPLIT_IO", "bool", False, TIMING_DIAGNOSTICS, "Diagnostic-only C0 source/destination split selector: ON stages each fill in one reusable private buffer per source worker (thread or mmap reader process) and then copies into the existing leased SHM slot, exposing split source-read vs private->SHM timings. Default OFF reproduces the exact direct source->SHM path with no private buffers. Evidence-only; requires C0 streaming and never changes geometry, FD lifecycle, H2D, or adoption."),
    "COMFYMODAL_GOLDEN_C0_HOST_REGISTER": _spec("COMFYMODAL_GOLDEN_C0_HOST_REGISTER", "bool", True, EXECUTION_POLICY, "C0 POSIX-SHM arena cudaHostRegister arm selector. Default ON registers the shared mapping once so the parent H2Ds directly from it (existing production behavior). OFF leaves the byte-identical mapping, slots, geometry, source engine, and H2D dispatcher unregistered. Requires C0 streaming; no other difference between arms."),
    "COMFYMODAL_GOLDEN_C0_SHM_POPULATE": _spec("COMFYMODAL_GOLDEN_C0_SHM_POPULATE", "bool", False, EXECUTION_POLICY, "Experiment-1 treatment: materialize the fresh C0 SHM with real parallel CPU writes before cudaHostRegister. Default OFF is the production-005 control."),
    "COMFYMODAL_GOLDEN_C0_READER_GATE": _spec("COMFYMODAL_GOLDEN_C0_READER_GATE", "bool", False, EXECUTION_POLICY, "Experiment-4 treatment: enforce the 4 ms source-launch floor inside each forked reader immediately before its expensive mmap/memcpy access. Default OFF keeps coordinator claim-spacing only."),
    "COMFYMODAL_GOLDEN_C0_DMA_RING": _spec("COMFYMODAL_GOLDEN_C0_DMA_RING", "bool", False, EXECUTION_POLICY, "Experiment-3 treatment: 5 x 64 MiB global pageable source pool plus 2 x 64 MiB parent-owned pinned DMA ring with SHM->pinned staging and split lease ownership. Default OFF is the production-005 16-slot registered arena."),
    "COMFYMODAL_GOLDEN_C0_FIVE_SLOTS": _spec("COMFYMODAL_GOLDEN_C0_FIVE_SLOTS", "bool", False, EXECUTION_POLICY, "Composition treatment: 5 x 64 MiB globally shared source slots (320 MiB) with no other change; registration still follows COMFYMODAL_GOLDEN_C0_HOST_REGISTER and the DMA ring stays off unless separately selected. Default OFF is the production-005 16-slot geometry."),
    "COMFYMODAL_GOLDEN_C0_REGISTRATION_DIAG": _spec("COMFYMODAL_GOLDEN_C0_REGISTRATION_DIAG", "bool", False, TIMING_DIAGNOSTICS, "Observation-only deep cudaHostRegister identity, mapping, proc-state, rusage, and context diagnostics. Default OFF."),
    "COMFYMODAL_GOLDEN_C0_REGISTRATION_ORDER": _spec("COMFYMODAL_GOLDEN_C0_REGISTRATION_ORDER", "enum", "overlap", TIMING_DIAGNOSTICS, "Diagnostic-only C0 registration ordering arm: overlap preserves current Popen-before-register behavior; register_first isolates child startup. Default overlap.", choices=("overlap", "register_first")),
    "COMFYMODAL_GOLDEN_C0_REGISTRATION_CONTEXT_PREINIT": _spec("COMFYMODAL_GOLDEN_C0_REGISTRATION_CONTEXT_PREINIT", "bool", False, TIMING_DIAGNOSTICS, "Hoist the CUDA primary-context preinitialization onto a bounded worker started at the post-snapshot (snap=False) restore boundary and joined before the first caller needs a CUDA context, so it overlaps restore's own CUDA-free state repair instead of running serially in front of cudaHostRegister. Default OFF is the exact production control: no CUDA is touched before cudaHostRegister. snap=True never starts it; the join is bounded and fails closed before arena use. cudaHostRegister itself is unchanged and remains mandatory."),
    "COMFYMODAL_GOLDEN_C0_SOURCE_SLOT_COUNT": _spec("COMFYMODAL_GOLDEN_C0_SOURCE_SLOT_COUNT", "enum", "16", EXECUTION_POLICY, "Slot count of the registered C0 source arena, owned by golden_source_threads. SLOT_BYTES is always 64 MiB, so 16 is 1 GiB (the accepted Production-009 default that removed 8-slot source-capacity starvation) and 12 is 768 MiB. Any other value fails closed. Arena-depth axis only: QD, reader count, block size, pacer, source engine, mmap lifecycle, H2D dispatcher and the slot state machine are unchanged.", choices=("12", "16")),
    "COMFYMODAL_GOLDEN_C0_EXPERIMENT_ARM": _spec("COMFYMODAL_GOLDEN_C0_EXPERIMENT_ARM", "enum", "", TIMING_DIAGNOSTICS, "Declared P10 2x2 experiment arm (arena slot count x hoisted CUDA primary-context preinit). Empty means the arm axis is unused and the deployment is not evidence for any P10 cell. A non-empty value that does not exactly match the observed slot count and preinit flag fails closed at arena construction, so a deployment whose environment did not reach the container cannot produce a valid-looking run for the wrong arm.", choices=("p10-12-nopreinit", "p10-12-preinit", "p10-16-nopreinit", "p10-16-preinit")),
    "COMFYMODAL_GOLDEN_CLIP_SKELETON_OVERLAP": _spec("COMFYMODAL_GOLDEN_CLIP_SKELETON_OVERLAP", "bool", False, EXECUTION_POLICY, "CLIP skeleton overlap selector. Default OFF keeps the fused source-then-construct order. ON builds the weightless CLIP skeleton from header-derived meta tensors concurrently with the QD source/H2D read, then binds the real transported views into it; the frozen mmap/QD4/64 MiB/process-reader source path, H2D dispatcher, adoption proof, and restore lifecycle are unchanged. Fail-closed: any unsupported header or upstream key normalization falls back to the exact fused constructor."),
    "COMFYMODAL_GOLDEN_C0_SOURCE_VOLUME_V1": _spec("COMFYMODAL_GOLDEN_C0_SOURCE_VOLUME_V1", "bool", False, LOADER_SELECTION, "Distinct C0 direct Volume V1 treatment selector: ON replaces only the child's byte producer with a VolumeGetFile2 ranged read streamed 8 MiB-block-by-block into the leased SHM slot, with no preadv fallback. Default OFF preserves the exact C0 preadv control. Requires the C0 streaming arm; geometry, worker pool, IPC, SHM, H2D, and adoption are unchanged."),
    "COMFYMODAL_GOLDEN_C0_PREADV_SICKNESS_DIAG": _spec("COMFYMODAL_GOLDEN_C0_PREADV_SICKNESS_DIAG", "bool", False, TIMING_DIAGNOSTICS, "Diagnostic-only clustered C0 preadv-sickness selector: ON instruments every child production preadv with an outstanding-read registry and runs an independent 500ms watchdog that captures a passive snapshot before a bounded, fresh-FD active probe matrix against pre-registered CLIP/UNET control offsets. Default OFF preserves the exact C0 persistent-FD preadv control; never changes QD, geometry, SHM, H2D, adoption, fallback, or validation. Evidence-only, never promoted."),

    "COMFYMODAL_V2_CLEAN_LANE": _spec("COMFYMODAL_V2_CLEAN_LANE", "bool", False, EXECUTION_POLICY, "Compatibility clean-lane selector."),
    "COMFYMODAL_V2_E37_CLEAN_LANE": _spec("COMFYMODAL_V2_E37_CLEAN_LANE", "bool", False, EXECUTION_POLICY, "E37 clean-lane runtime selector."),
    "COMFYMODAL_V2_E37_STRICT_PROOF": _spec("COMFYMODAL_V2_E37_STRICT_PROOF", "bool", False, DEPRECATED_DIAGNOSTIC, "Enable fail-closed E37 proof validation."),
    "COMFYMODAL_V2_E37_EXPECTED_OUTPUT_SHA": _spec("COMFYMODAL_V2_E37_EXPECTED_OUTPUT_SHA", "string", "", DEPRECATED_DIAGNOSTIC, "Expected output digest for E37 proof validation."),
    "COMFYMODAL_V2_SINGLE_USE_CONTAINERS": _spec("COMFYMODAL_V2_SINGLE_USE_CONTAINERS", "bool", False, EXECUTION_POLICY, "Use a fresh container for every request."),
    "COMFYMODAL_V2_CRITICAL_PATH_LEDGER": _spec("COMFYMODAL_V2_CRITICAL_PATH_LEDGER", "bool", True, TIMING_DIAGNOSTICS, "Enable the canonical critical-path ledger."),
    "COMFYMODAL_V2_GANTT_TELEMETRY": _spec("COMFYMODAL_V2_GANTT_TELEMETRY", "bool", False, TIMING_DIAGNOSTICS, "Emit Gantt timing telemetry."),
    "COMFYMODAL_GOLDEN_QD2_TELEMETRY": _spec("COMFYMODAL_GOLDEN_QD2_TELEMETRY", "enum", "light", TIMING_DIAGNOSTICS, "QD2 transport telemetry mode: light timing default vs heavy_current per-range diagnostics.", choices=("light", "heavy_current")),
    "COMFYMODAL_GOLDEN_QD2_DEFER_H2D": _spec("COMFYMODAL_GOLDEN_QD2_DEFER_H2D", "bool", False, TIMING_DIAGNOSTICS, "Phase B4 diagnostic-only gate: defer QD2 H2D until CPU source read completes; NORMAL when off."),
    "COMFYMODAL_GOLDEN_COMPLETION_EVENT_LIFETIME": _spec("COMFYMODAL_GOLDEN_COMPLETION_EVENT_LIFETIME", "enum", "reuse", EXECUTION_POLICY, "Golden H2D completion-event lifetime: reuse (default) keeps the persistent per-slot event pair; one_shot_events allocates ONE fresh production event pair per H2D ticket and retires it when the slot is returned, so no completion-event object is ever reused between transfers.", choices=("reuse", "one_shot_events")),
    "COMFYMODAL_GOLDEN_IO_PROCESS_V2_MMAP_COPY_DIAG": _spec("COMFYMODAL_GOLDEN_IO_PROCESS_V2_MMAP_COPY_DIAG", "bool", False, TIMING_DIAGNOSTICS, "Diagnostic-only: in the mmap source engine, repeat each read's copy into a private anonymous buffer and report its duration, so source page-in cost can be split from destination-copy cost. Default OFF; it doubles the copied bytes and must never be enabled for production throughput."),
    "COMFYMODAL_GOLDEN_CLIP_UNET_SCHEDULE": _spec("COMFYMODAL_GOLDEN_CLIP_UNET_SCHEDULE", "enum", "serial", EXECUTION_POLICY, "Golden CLIP-forward || UNET-load schedule. serial (default) keeps the exact historical ordering; overlap runs both stages concurrently on the request event loop and joins both before sampler preparation.", choices=("serial", "overlap")),
    "COMFYMODAL_GOLDEN_SAMPLING_VAE_SCHEDULE": _spec("COMFYMODAL_GOLDEN_SAMPLING_VAE_SCHEDULE", "enum", "serial", EXECUTION_POLICY, "Golden sampling || VAE-load schedule. serial (default) keeps the exact historical ordering; overlap starts the VAE load concurrently with sampling, joins before VAE decode, and never changes sampler math, steps, or output.", choices=("serial", "overlap")),
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
