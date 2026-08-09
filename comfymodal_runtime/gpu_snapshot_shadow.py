"""Shadow GPU-snapshot proof app (Gate 1 canary + Gate 3 full-stack GPU snapshot).

This module defines an ISOLATED shadow Modal App that proves whether our
current RTX PRO 6000 + Torch/ComfyUI environment can create a GPU memory
snapshot of the ENTIRE currently-used Z-Image model stack and restore it
into a fresh cold single-use container.  It is deliberately separate from
the production V2 deployment: GPU snapshots are NEVER enabled on the
production app from this code.

Two classes are registered on the shadow App:

* ``GpuSnapshotCanary`` (Gate 1): minimal CUDA canary.  During ``snap=True``
  enter it records versions, initializes CUDA, allocates a deterministic CUDA
  tensor, synchronizes, and returns so Modal captures the GPU snapshot.  On a
  restored container the ``snap=False`` enter verifies the retained tensor is
  still CUDA-resident with exact contents and performs a trivial CUDA
  computation.

* ``GpuSnapshotUnetShadow`` (Gate 3, full-stack): uses our actual current
  ComfyUI initialization (production bootstrap + legacy in-process backend)
  and snapshots UNET + CLIP + VAE — the entire Z-Image model stack — onto the
  GPU.  During ``snap=True`` enter:

    1. init ComfyUI normally (production bootstrap + in-process backend;
       custom nodes, Sage policy, HIGH_VRAM model-management config),
    2. initialize CUDA explicitly,
    3. run ONE dependency preflight with the provisioned benchmark workflow
       (populates the in-memory dependency-validation cache and persists the
       immutable dependency manifest on the runtime-config volume) so the
       post-restore preflight is a cheap identity check,
    4. load the exact Z-Image UNET, Qwen-3 4B CLIP, and AE VAE through the
       normal ComfyUI loading path, move all three to CUDA through the normal
       ComfyUI path (``model_management.load_models_gpu``),
    5. pre-apply CacheDiT to the UNET via the production restore machinery
       (deterministic; the graph re-apply at request time is an idempotent
       no-op),
    6. run ONE production compile + graph validation + validation-certificate
       write with the provisioned workflow (topology-only cached state; the
       certificate identity is prompt-bound in the current architecture, so
       only same-prompt requests hit it),
    7. verify each model is fully CUDA-resident, record memory, synchronize,
       and return so Modal captures the GPU snapshot.

  After restore (``snap=False`` enter): verify CUDA + all three models
  CUDA-resident + identities, record memory.  The workflow itself runs in
  ``run_gpu_snapshot_workflow``: the retained UNET/CLIP/VAE are published as
  ready on the loader bridge (identity-checked consumption; original loaders
  never run), and the request executes through the existing in-process
  executor with the normal CLIP encode / sampler / VAE decode paths.

  All hard markers are printed to stdout (flush=True) AND accumulated in the
  returned evidence so the local runner can classify every attempt and locate
  the exact last successful marker on crash (exit 139).

Deploy: ``modal deploy -m comfymodal_runtime.gpu_snapshot_shadow``
"""

from __future__ import annotations

import functools
import hashlib
import os
import sys
import time
from typing import Any, Mapping

import modal as _modal

# ── Production machinery reuse (read-only; production app is never deployed
#    from this module, and production GPU snapshot is never toggled here). ──
from comfymodal_runtime.modal_app import (  # noqa: E402
    _reference_image,
    _runtime_env,
    ModalRuntimeSpec,
    MODELS_PATH,
    CUSTOM_NODES_PATH,
    RUNTIME_STATE_PATH,
    _V2_CONTAINER_SESSION_ID,
    parse_gpu_request,
)
from comfymodal_runtime.modal_app import (  # noqa: E402
    ModalRuntimeEntrypoint,
)
from comfymodal_runtime.modal_app import (  # noqa: E402
    _parse_evict_models_before_snapshot,
    _parse_evict_retain_role,
    _resolve_region_pin,
    _resolve_cloud_pin,
)
from comfymodal_runtime.restore_state_probe import (  # noqa: E402
    emit_stage_line,
    probe_alive_weakrefs,
    probe_cuda_memory,
    probe_model_storage,
    probe_process_memory,
    probe_reference_holders,
    probe_worker_fingerprint,
)
from comfymodal_runtime.runtime_bootstrap import (  # noqa: E402
    RuntimeBootstrap,
)
from comfymodal_runtime.model_preload import (  # noqa: E402
    V2LoaderBridge,
)
from comfymodal_runtime.cpu_snapshot_models import (  # noqa: E402
    prove_unet_gpu_residency,
)
from comfymodal_runtime.restore_plan import (  # noqa: E402
    derive_model_key,
    derive_prefill_key,
    build_restore_model_spec,
)
from comfymodal_runtime.trace import RuntimeTrace  # noqa: E402
from comfymodal_runtime.runtime_executor import RuntimeExecutor  # noqa: E402
from comfymodal_runtime.v2_waterfall import (  # noqa: E402
    build_waterfall,
    attach_waterfall,
)

SHADOW_APP_NAME = os.environ.get(
    "COMFYMODAL_V2_GPU_SNAPSHOT_APP",
    "stable-modal-comfy-v2-gpu-snapshot-shadow",
).strip() or "stable-modal-comfy-v2-gpu-snapshot-shadow"

# ── Resource / lifecycle shape (matches production V2) ──────────────────
GPU = "rtx-pro-6000"
CPU = 16
MEMORY_MB = 49152
MIN_CONTAINERS = 0
SCALEDOWN_WINDOW = 4
TIMEOUT = 3600
SINGLE_USE = True

# Name of the provisioned workflow file on the runtime-config volume
# (``/mnt/comfymodal_runtime_state``).  The runner uploads
# ``latest_benchmark_workflow.json`` there before deploy; the snapshot build
# reads it to pre-run dependency preflight / graph validation / CacheDiT
# preparation.  Absent file => those stages are skipped (graceful fallback to
# the request-time path), the model stack itself is loaded from the
# ``COMFYMODAL_WARMUP_*`` environment (same convention as the production
# warmup profile).
SHADOW_WORKFLOW_FILE = "gpu_snapshot_workflow.json"
SHADOW_WORKFLOW_PATH = os.path.join(RUNTIME_STATE_PATH, SHADOW_WORKFLOW_FILE)

# ── Shadow-side instrumentation state (captured inside the GPU snapshot) ──
# The read recorder and the timing wrappers are installed once during
# ``snap=True`` and survive the restore, so the restored request can be
# proven to have performed zero safetensors rereads and to have executed the
# CLIP/sampler/VAE boundaries exactly once with wall timestamps.
_SHADOW_READ_RECORDS: list[dict[str, Any]] = []
_SHADOW_READ_RECORDER_INSTALLED = False
_SHADOW_TIMING_EVENTS: list[dict[str, Any]] = []
_SHADOW_TIMING_WRAPPERS_INSTALLED = False

# ── 2x2 restore-matrix placement pins ─────────────────────────────────────
# The matrix runner deploys this module once per arm with
# COMFYMODAL_V2_REGION / COMFYMODAL_V2_CLOUD set; the pins are resolved at
# deploy (module import) time so each arm's cls carries Modal's
# SchedulerPlacement.  Unpinned (both absent) preserves the historical
# multi-region behavior — the existing gate deployments stay unchanged.
_MATRIX_REGION = _resolve_region_pin()
_MATRIX_CLOUD = _resolve_cloud_pin()


def _pin_kwargs() -> dict[str, Any]:
    kwargs: dict[str, Any] = {}
    if _MATRIX_REGION is not None:
        kwargs["region"] = _MATRIX_REGION
    if _MATRIX_CLOUD is not None:
        kwargs["cloud"] = _MATRIX_CLOUD
    return kwargs


def _emit(self: Any, marker: str, **kv: Any) -> None:
    """Emit a hard marker to stdout (Modal logs) and record it on self."""
    extra = " ".join(f"{k}={v}" for k, v in sorted(kv.items()))
    line = f"[gpu_snapshot] {marker}"
    if extra:
        line += f" {extra}"
    print(line, flush=True)
    record = {"marker": marker, "wall_unix_ns": int(time.time() * 1_000_000_000)}
    record.update({k: v for k, v in kv.items()})
    if not hasattr(self, "_gpu_snapshot_markers"):
        self._gpu_snapshot_markers = []
    self._gpu_snapshot_markers.append(record)


def _record_versions() -> dict[str, str]:
    """Record Python / Modal / Torch / CUDA / accelerate versions.

    accelerate is REPORTED ONLY (absent -> "absent"); never installed or
    changed here.
    """
    versions: dict[str, str] = {
        "python": sys.version.split()[0],
        "modal": str(getattr(_modal, "__version__", "unknown")),
        "torch": "",
        "cuda": "",
        "accelerate": "absent",
    }
    try:
        import torch
        versions["torch"] = str(torch.__version__)
        cuda_ver = getattr(getattr(torch, "version", None), "cuda", None)
        versions["cuda"] = str(cuda_ver or "")
    except Exception as exc:  # noqa: BLE001
        versions["torch"] = f"error:{type(exc).__name__}"
    try:
        import importlib.metadata as _imd
        versions["accelerate"] = str(_imd.version("accelerate"))
    except Exception:  # noqa: BLE001
        versions["accelerate"] = "absent"
    return versions


def _probe_thread_state() -> dict[str, Any]:
    """Python + native thread counts (``/proc/self/task`` where available)."""
    out: dict[str, Any] = {"python_threads": 0, "native_threads": None}
    try:
        import threading
        out["python_threads"] = int(threading.active_count())
    except Exception:  # noqa: BLE001
        pass
    try:
        out["native_threads"] = int(len(os.listdir("/proc/self/task")))
    except Exception:  # noqa: BLE001
        pass
    return out


def _probe_loaded_modules() -> dict[str, Any]:
    """Count loaded modules, split by CUDA-related name patterns (cheap)."""
    out: dict[str, Any] = {"total": 0}
    try:
        _names = list(sys.modules)
        out["total"] = len(_names)
        for _pat in ("cuda", "nvrtc", "cublas", "cudnn", "cusparse", "nccl", "torch._C"):
            _lower = _pat.lower()
            out[_pat] = int(sum(1 for n in _names if _lower in n.lower()))
    except Exception:  # noqa: BLE001
        pass
    return out


def _probe_gc_count() -> int:
    """Live GC-tracked object count (bounded single call, never raised)."""
    try:
        import gc
        return int(len(gc.get_objects()))
    except Exception:  # noqa: BLE001
        return -1


def torch_memory_allocated() -> int:
    import torch
    try:
        return int(torch.cuda.memory_allocated())
    except Exception:  # noqa: BLE001
        return -1


def torch_memory_reserved() -> int:
    import torch
    try:
        return int(torch.cuda.memory_reserved())
    except Exception:  # noqa: BLE001
        return -1


def torch_synchronize() -> None:
    import torch
    torch.cuda.synchronize()


def _verify_output_images(images: list[Any]) -> dict[str, Any]:
    """Verify returned output images: PNG magic, dimensions, non-blank."""
    import base64
    import hashlib
    import struct

    out: dict[str, Any] = {
        "count": len(images),
        "valid_png": False,
        "dimensions": [],
        "sha256": [],
        "non_blank": [],
    }
    for img in images:
        data_b64 = str(img.get("data", "") or "")
        raw = b""
        try:
            raw = base64.b64decode(data_b64)
        except Exception:  # noqa: BLE001
            pass
        is_png = raw[:8] == b"\x89PNG\r\n\x1a\n"
        dims: list[int] = []
        if is_png and len(raw) >= 24:
            try:
                w, h = struct.unpack(">II", raw[16:24])
                dims = [int(w), int(h)]
            except Exception:  # noqa: BLE001
                pass
        out["valid_png"] = out["valid_png"] or bool(is_png)
        out["dimensions"].append(dims)
        out["sha256"].append(hashlib.sha256(raw).hexdigest() if raw else "")
        out["non_blank"].append(len(raw) > 1024)
    return out


def _read_provisioned_workflow() -> tuple[dict[str, Any], dict[str, Any]]:
    """Read the provisioned benchmark workflow from the runtime-config volume.

    Returns ``(prompt, modal_options)`` — the canonical ``{node_id: spec}``
    prompt dict plus its modal options — or ``({}, {})`` when the file is
    absent/unreadable (the snapshot build then degrades gracefully to the
    request-time preflight/validation paths).
    """
    import json
    try:
        if not os.path.isfile(SHADOW_WORKFLOW_PATH):
            return {}, {}
        with open(SHADOW_WORKFLOW_PATH, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        if isinstance(data, dict) and data.get("payload", {}).get("prompt"):
            return (
                dict(data["payload"]["prompt"]),
                dict(data["payload"].get("modal_options", {}) or {}),
            )
        if isinstance(data, dict) and data.get("prompt"):
            return dict(data["prompt"]), {}
        return {}, {}
    except Exception:  # noqa: BLE001
        return {}, {}


def _workflow_hash(workflow: Mapping[str, Any]) -> str:
    """Canonical SHA-256 of a workflow dict (JSON, sorted keys)."""
    import json
    try:
        encoded = json.dumps(
            dict(workflow), sort_keys=True, separators=(",", ":"), ensure_ascii=False,
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()
    except Exception:  # noqa: BLE001
        return ""


def _load_spec_from_workflow(workflow: Mapping[str, Any]) -> dict[str, Any]:
    """Extract the concrete loader requests the graph will make.

    Mirrors ``build_restore_model_spec`` semantics: returns the ``loaders``
    buckets (unet/clip/vae) so the snapshot build constructs the models with
    the exact same node arguments the request-time graph loaders use.
    """
    spec = build_restore_model_spec(dict(workflow), None)
    return dict(spec.get("loaders", {}))


# ── Shadow instrumentation (installed pre-capture, retained in snapshot) ──


def _install_shadow_read_recorder() -> bool:
    """Wrap ``comfy.utils.load_torch_file`` to record every model-file read.

    Installed during ``snap=True`` so the restored container keeps recording;
    the request method computes deltas against the pre-request baseline to
    prove zero rereads of the three model files.  Idempotent.
    """
    global _SHADOW_READ_RECORDER_INSTALLED
    if _SHADOW_READ_RECORDER_INSTALLED:
        return True
    try:
        import comfy.utils as _cu
        original = _cu.load_torch_file
        if getattr(original, "_comfy_modal_shadow_read_recorder", False):
            _SHADOW_READ_RECORDER_INSTALLED = True
            return True

        @functools.wraps(original)
        def _recording_read(ckpt, safe_load=False, device=None, return_metadata=False):
            t0 = time.perf_counter()
            try:
                return original(ckpt, safe_load=safe_load, device=device, return_metadata=return_metadata)
            finally:
                _SHADOW_READ_RECORDS.append({
                    "path": str(ckpt),
                    "basename": os.path.basename(str(ckpt)) if ckpt else "",
                    "wall_ms": round((time.perf_counter() - t0) * 1000.0, 3),
                })

        setattr(_recording_read, "_comfy_modal_shadow_read_recorder", True)
        _cu.load_torch_file = _recording_read
        _SHADOW_READ_RECORDER_INSTALLED = True
        return True
    except Exception:  # noqa: BLE001
        return False


def _record_shadow_timing(kind: str, start_ns: int, end_ns: int, **kv: Any) -> None:
    _SHADOW_TIMING_EVENTS.append({
        "kind": kind,
        "start_wall_unix_ns": int(start_ns),
        "end_wall_unix_ns": int(end_ns),
        "wall_ms": round((end_ns - start_ns) / 1_000_000, 3),
        **kv,
    })


def _install_shadow_timing_wrappers() -> bool:
    """Wrap CLIPTextEncode.encode / VAEDecode.decode / KSAMPLER.sample with
    wall-clock recorders (installed pre-capture; retained in the snapshot)."""
    global _SHADOW_TIMING_WRAPPERS_INSTALLED
    if _SHADOW_TIMING_WRAPPERS_INSTALLED:
        return True
    installed: list[str] = []
    try:
        import nodes as _nodes
        _clip_cls = _nodes.NODE_CLASS_MAPPINGS.get("CLIPTextEncode")
        _vae_cls = _nodes.NODE_CLASS_MAPPINGS.get("VAEDecode")
        if _clip_cls is not None and callable(getattr(_clip_cls, "encode", None)):
            _orig_encode = _clip_cls.encode
            if not getattr(_orig_encode, "_comfy_modal_shadow_timed", False):

                @functools.wraps(_orig_encode)
                def _timed_encode(*args: Any, **kwargs: Any) -> Any:
                    _text = str(kwargs.get("text", args[1] if len(args) > 1 else ""))
                    _t0 = time.time_ns()
                    try:
                        return _orig_encode(*args, **kwargs)
                    finally:
                        _record_shadow_timing(
                            "clip_encode", _t0, time.time_ns(),
                            text_hash=hashlib.sha256(_text.encode("utf-8", "replace")).hexdigest()[:12],
                        )

                setattr(_timed_encode, "_comfy_modal_shadow_timed", True)
                _clip_cls.encode = _timed_encode
                installed.append("CLIPTextEncode.encode")
        if _vae_cls is not None and callable(getattr(_vae_cls, "decode", None)):
            _orig_decode = _vae_cls.decode
            if not getattr(_orig_decode, "_comfy_modal_shadow_timed", False):

                @functools.wraps(_orig_decode)
                def _timed_decode(*args: Any, **kwargs: Any) -> Any:
                    _t0 = time.time_ns()
                    try:
                        return _orig_decode(*args, **kwargs)
                    finally:
                        _record_shadow_timing("vae_decode", _t0, time.time_ns())

                setattr(_timed_decode, "_comfy_modal_shadow_timed", True)
                _vae_cls.decode = _timed_decode
                installed.append("VAEDecode.decode")
        import comfy.samplers as _samplers
        if callable(getattr(_samplers.KSAMPLER, "sample", None)):
            _orig_sample = _samplers.KSAMPLER.sample
            if not getattr(_orig_sample, "_comfy_modal_shadow_timed", False):

                @functools.wraps(_orig_sample)
                def _timed_sample(*args: Any, **kwargs: Any) -> Any:
                    _t0 = time.time_ns()
                    try:
                        return _orig_sample(*args, **kwargs)
                    finally:
                        _record_shadow_timing("sampler", _t0, time.time_ns())

                setattr(_timed_sample, "_comfy_modal_shadow_timed", True)
                _samplers.KSAMPLER.sample = _timed_sample
                installed.append("KSAMPLER.sample")
        _SHADOW_TIMING_WRAPPERS_INSTALLED = True
        return True
    except Exception:  # noqa: BLE001
        return bool(installed)


def _prove_model_gpu_residency(module: Any, patcher: Any, label: str) -> dict[str, Any]:
    """Generic GPU-residency proof for a CLIP/VAE module + patcher.

    Mirrors ``prove_unet_gpu_residency`` evidence semantics: parameter device
    distribution over the module, patcher load/current device, model-cache
    membership, and GPU memory totals.  Never transfers or mutates tensors.

    Device fields use ``ModelPatcher.current_loaded_device()`` (this ComfyUI
    build tracks residency via ``model.device``; there is no
    ``current_device`` attribute).
    """
    evidence: dict[str, Any] = {
        "label": label,
        "status": "absent",
        "parameter_count": 0,
        "gpu_parameter_count": 0,
        "cpu_parameter_count": 0,
        "gpu_parameter_fraction": 0.0,
        "load_device": "absent",
        "current_device": "absent",
        "in_model_cache": 0,
    }
    if module is None or patcher is None:
        return evidence
    try:
        import torch
    except Exception:  # noqa: BLE001
        return evidence
    gpu_params = 0
    cpu_params = 0
    total = 0
    try:
        for p in module.parameters():
            dev = str(getattr(p, "device", ""))
            total += 1
            if dev.startswith("cuda"):
                gpu_params += 1
            elif dev == "cpu":
                cpu_params += 1
    except Exception:  # noqa: BLE001
        pass
    evidence["parameter_count"] = total
    evidence["gpu_parameter_count"] = gpu_params
    evidence["cpu_parameter_count"] = cpu_params
    evidence["gpu_parameter_fraction"] = round(gpu_params / total, 4) if total else 0.0
    load_device = getattr(patcher, "load_device", None)
    evidence["load_device"] = str(load_device) if load_device is not None else "absent"
    try:
        _cld = getattr(patcher, "current_loaded_device", None)
        _cur = _cld() if callable(_cld) else getattr(patcher, "model", _cld)
        _cur = getattr(_cur, "device", _cur) if _cur is not None else None
        evidence["current_device"] = str(_cur) if _cur is not None else "absent"
    except Exception:  # noqa: BLE001
        evidence["current_device"] = "absent"
    try:
        import comfy.model_management as _mm
        for _lm in getattr(_mm, "current_loaded_models", []):
            if getattr(_lm, "model", None) is not None and id(_lm.model) == id(patcher):
                evidence["in_model_cache"] = 1
                break
    except Exception:  # noqa: BLE001
        pass
    if total == 0:
        evidence["status"] = "no_params"
    elif gpu_params == total:
        evidence["status"] = "gpu_resident"
    elif gpu_params > 0:
        evidence["status"] = "partially_gpu"
    elif cpu_params == total:
        evidence["status"] = "cpu_resident"
    else:
        evidence["status"] = "unknown"
    return evidence


def _clip_module_and_patcher(clip: Any) -> tuple[Any, Any]:
    """Resolve (module, patcher) for a ComfyUI CLIP wrapper."""
    csm = getattr(clip, "cond_stage_model", None)
    if csm is not None and hasattr(csm, "parameters"):
        return csm, getattr(clip, "patcher", None)
    patcher = getattr(clip, "patcher", None)
    pm = getattr(patcher, "model", None)
    if pm is not None and hasattr(pm, "parameters"):
        return pm, patcher
    return csm, patcher


def _vae_module_and_patcher(vae: Any) -> tuple[Any, Any]:
    """Resolve (module, patcher) for a ComfyUI VAE wrapper."""
    first_stage = getattr(vae, "first_stage_model", None)
    return first_stage, getattr(vae, "patcher", None)


def _gpu_stage_fields(
    self: Any, stage: str, *,
    unet: Any = None, clip: Any = None, vae: Any = None, final: bool = False,
) -> None:
    """Emit one ``gpu_snapshot_size stage=...`` line and retain the raw
    probe payloads on ``self._gpu_snapshot_size_stages[stage]``.

    Fields: process memory (RSS/PSS/anonymous/cgroup), CUDA allocated and
    RESERVED, deduplicated CUDA model bytes per role, total unique CUDA
    model bytes, and the non-model CUDA residual (allocated minus model
    bytes — only meaningful at stages where models are resident).
    """
    mem = probe_process_memory()
    cuda = probe_cuda_memory()
    storage = None
    if unet is not None or clip is not None or vae is not None:
        storage = probe_model_storage(unet, clip, vae, device_prefix="cuda")
    allocated_mib = cuda.get("allocated_mib")
    total_cuda_model_bytes = 0
    if storage:
        total_cuda_model_bytes = int(storage.get("total_unique_model_bytes", 0) or 0)
    non_model_cuda_bytes = None
    if isinstance(allocated_mib, (int, float)) and total_cuda_model_bytes:
        non_model_cuda_bytes = max(0, int(allocated_mib * (1024.0 * 1024.0)) - total_cuda_model_bytes)
    fields: dict[str, Any] = {
        "rss_mib": mem.get("rss_mib"),
        "pss_mib": mem.get("pss_mib"),
        "anonymous_mib": mem.get("anonymous_mib"),
        "cgroup_current_mib": mem.get("cgroup_current_mib"),
        "cuda_allocated_mib": allocated_mib,
        "cuda_reserved_mib": cuda.get("reserved_mib"),
        "cuda_max_allocated_mib": cuda.get("max_allocated_mib"),
        "cuda_max_reserved_mib": cuda.get("max_reserved_mib"),
        "cuda_free_mib": cuda.get("free_mib"),
        "cuda_total_mib": cuda.get("total_mib"),
        "unet_cuda_bytes": 0, "clip_cuda_bytes": 0, "vae_cuda_bytes": 0,
        "total_cuda_model_bytes": total_cuda_model_bytes,
        "non_model_cuda_bytes": non_model_cuda_bytes,
    }
    if storage:
        for role in ("unet", "clip", "vae"):
            fields[f"{role}_cuda_bytes"] = int(
                storage.get("per_model", {}).get(role, {}).get("bytes", 0) or 0
            )
        fields["unet_present"] = int(bool(storage.get("per_model", {}).get("unet", {}).get("object_present")))
        fields["clip_present"] = int(bool(storage.get("per_model", {}).get("clip", {}).get("object_present")))
        fields["vae_present"] = int(bool(storage.get("per_model", {}).get("vae", {}).get("object_present")))
    if final:
        try:
            self._gpu_snapshot_fingerprint = probe_worker_fingerprint(cuda_torch=True)
        except Exception:  # noqa: BLE001
            self._gpu_snapshot_fingerprint = {}
    emit_stage_line("gpu_snapshot_size", stage, fields)
    if not hasattr(self, "_gpu_snapshot_size_stages"):
        self._gpu_snapshot_size_stages = {}
    self._gpu_snapshot_size_stages[str(stage)] = {
        "process": mem, "cuda": cuda, "storage": storage, "fields": fields,
    }


def _capture_gpu_snapshot_boundary(
    self: Any,
    unet: Any,
    clip: Any,
    vae: Any,
    mm: Any,
) -> dict[str, Any]:
    """One GPU-snapshot boundary state capture (read-only, never mutates).

    Order matters: cgroup + CUDA first (cheap, no model access), then the
    model storage walk (demand-pages CPU-side model-wrapper metadata — a
    bounded measurement artifact, ~242 MiB worst case per the capture-stage
    deltas), then holder/weakref surveys.  Every sub-probe is bounded and
    never raises.
    """
    out: dict[str, Any] = {
        "capture_wall_unix_ns": time.time_ns(),
        "process_memory": probe_process_memory(),
        "cuda_memory": probe_cuda_memory(),
        "cpu_snapshot_models_present": int(
            getattr(self, "_cpu_snapshot_models", None) is not None
        ),
        "cpu_model_objects_never_constructed": int(
            bool(getattr(self, "_gpu_build_cpu_models_never_constructed", False))
        ),
        "threads": _probe_thread_state(),
        "modules": _probe_loaded_modules(),
        "gc_objects": _probe_gc_count(),
        "cpu_storage": {},
        "cuda_storage": {},
    }
    try:
        out["cpu_storage"] = probe_model_storage(unet, clip, vae, device_prefix="cpu")
    except Exception:  # noqa: BLE001
        out["cpu_storage"] = {"error": "probe_failed"}
    try:
        out["cuda_storage"] = probe_model_storage(unet, clip, vae, device_prefix="cuda")
    except Exception:  # noqa: BLE001
        out["cuda_storage"] = {"error": "probe_failed"}
    try:
        out["alive_weakrefs"] = probe_alive_weakrefs(unet, clip, vae)
    except Exception:  # noqa: BLE001
        out["alive_weakrefs"] = {"error": "probe_failed"}
    try:
        out["reference_holders"] = probe_reference_holders(
            self,
            model_management=mm,
            bootstrap_state=getattr(self, "bootstrap", None),
        )
    except Exception:  # noqa: BLE001
        out["reference_holders"] = {"error": "probe_failed"}
    return out


def _emit_boundary(self: Any, marker: str, boundary: dict[str, Any]) -> None:
    """Emit one compact boundary marker line and retain the raw payload."""
    pm = boundary.get("process_memory", {}) or {}
    cuda = boundary.get("cuda_memory", {}) or {}
    cpu_st = boundary.get("cpu_storage", {}) or {}
    cuda_st = boundary.get("cuda_storage", {}) or {}
    _emit(
        self, marker,
        cgroup_current_mib=pm.get("cgroup_current_mib"),
        cuda_allocated_mib=cuda.get("allocated_mib"),
        cuda_reserved_mib=cuda.get("reserved_mib"),
        total_unique_cpu_model_bytes=cpu_st.get("total_unique_model_bytes", 0),
        total_unique_cuda_model_bytes=cuda_st.get("total_unique_model_bytes", 0),
        unet_cpu_bytes=cpu_st.get("unet_cpu_bytes", 0),
        clip_cpu_bytes=cpu_st.get("clip_cpu_bytes", 0),
        vae_cpu_bytes=cpu_st.get("vae_cpu_bytes", 0),
        cpu_snapshot_models_present=boundary.get("cpu_snapshot_models_present", 0),
    )
    if not hasattr(self, "_gpu_snapshot_boundaries"):
        self._gpu_snapshot_boundaries = {}
    self._gpu_snapshot_boundaries[str(marker)] = boundary


# ── Shadow App (deployed via `modal deploy -m comfymodal_runtime.gpu_snapshot_shadow`) ──
app = _modal.App(SHADOW_APP_NAME, image=_reference_image())

# Runtime env for the shadow classes: same propagation as production
# (`_runtime_env`), so COMFYMODAL_WARMUP_UNET, COMFYMODAL_ENABLE_GPU_SNAPSHOT,
# resource-shape vars, etc. reach the container.  GPU snapshot is enabled by
# the experimental option on the cls below, never by toggling production.
_SHADOW_SPEC = ModalRuntimeSpec(app_name=SHADOW_APP_NAME)
_SHADOW_ENV = _runtime_env(_SHADOW_SPEC)


# ═══════════════════════════════════════════════════════════════════════
# Gate 1 — minimal CUDA canary
# ═══════════════════════════════════════════════════════════════════════
@app.cls(
    gpu=GPU,
    cpu=CPU,
    memory=MEMORY_MB,
    timeout=TIMEOUT,
    min_containers=MIN_CONTAINERS,
    scaledown_window=SCALEDOWN_WINDOW,
    enable_memory_snapshot=True,
    experimental_options={"enable_gpu_snapshot": True},
    single_use_containers=SINGLE_USE,
    env=_SHADOW_ENV,
    **_pin_kwargs(),
)
class GpuSnapshotCanary:
    """Gate 1: minimal CUDA GPU-snapshot canary (no ComfyUI)."""

    @_modal.enter(snap=True)
    def snapshot_build(self) -> dict[str, Any]:
        self._gpu_snapshot_markers = []
        self._phase = "build"
        _emit(self, "gpu_snapshot_enter_start")
        versions = _record_versions()
        self._gpu_snapshot_versions = versions
        import torch
        torch.cuda.init()
        _emit(self, "cuda_initialized", available=int(torch.cuda.is_available()))
        # Deterministic CUDA tensor retained on self so the snapshot carries it.
        n = 1 << 22
        self._canary_tensor = torch.arange(n, dtype=torch.float32, device="cuda")
        self._canary_expected_sum = float(n * (n - 1) / 2)
        _emit(self, "canary_tensor_created", elements=n)
        torch.cuda.synchronize()
        _emit(self, "cuda_sync_before_snapshot_complete")
        # ── Pre-capture retained-state probe (PART B arm-2 baseline):
        #    CUDA-initialized + tiny canary tensor, NO ComfyUI, NO models. ──
        try:
            self._canary_build_state = {
                "process_memory": probe_process_memory(),
                "cuda_memory": probe_cuda_memory(),
                "threads": _probe_thread_state(),
                "modules": _probe_loaded_modules(),
                "gc_objects": _probe_gc_count(),
            }
        except Exception:  # noqa: BLE001
            self._canary_build_state = {"error": "probe_failed"}
        _emit(self, "canary_pre_capture_state_probed")
        _emit(self, "gpu_snapshot_enter_returning")
        return {"phase": "build"}

    @_modal.enter(snap=False)
    def restore(self) -> dict[str, Any]:
        # FIRST executable line of the restored Python process.
        _emit(self, "gpu_snapshot_restore_python_enter")
        self._phase = "restore"
        import torch
        verification: dict[str, Any] = {}
        try:
            tensor = getattr(self, "_canary_tensor", None)
            device_ok = tensor is not None and getattr(tensor, "is_cuda", False)
            contents_ok = False
            if device_ok:
                n = 1 << 22
                expected = torch.arange(n, dtype=torch.float32, device="cuda")
                contents_ok = bool(torch.equal(tensor, expected))
            verification = {
                "tensor_present": tensor is not None,
                "tensor_is_cuda": bool(device_ok),
                "tensor_contents_exact": bool(contents_ok),
                "tensor_sum_matches": bool(
                    device_ok and contents_ok
                    and abs(float(tensor.sum().item()) - self._canary_expected_sum) < 1.0
                ),
            }
            _emit(
                self, "canary_tensor_verified",
                tensor_present=int(verification["tensor_present"]),
                tensor_is_cuda=int(verification["tensor_is_cuda"]),
                tensor_contents_exact=int(verification["tensor_contents_exact"]),
                tensor_sum_matches=int(verification["tensor_sum_matches"]),
            )
            # Trivial CUDA computation on the restored tensor.
            if device_ok:
                result = float((tensor * 2.0).sum().item())
                verification["trivial_cuda_op_result"] = result
            torch.cuda.synchronize()
            _emit(self, "post_restore_cuda_operation_verified", op="tensor_mul2_sum")
        except Exception as exc:  # noqa: BLE001
            verification["error"] = f"{type(exc).__name__}: {exc}"
            _emit(self, "post_restore_cuda_operation_verified", error=type(exc).__name__)
        _emit(self, "canary_complete", ok=int(bool(verification.get("tensor_sum_matches"))))
        # ── Post-restore retained-state probe (PART B arm 2): CUDA host
        #    state recreated by GPU-snapshot restore, no models. ──
        try:
            self._canary_restore_state = {
                "process_memory": probe_process_memory(),
                "cuda_memory": probe_cuda_memory(),
                "threads": _probe_thread_state(),
                "modules": _probe_loaded_modules(),
                "gc_objects": _probe_gc_count(),
                "worker_fingerprint": probe_worker_fingerprint(cuda_torch=True),
            }
        except Exception:  # noqa: BLE001
            self._canary_restore_state = {"error": "probe_failed"}
        _emit(self, "canary_post_restore_state_probed")
        self._gpu_snapshot_verification = verification
        return {"phase": "restore"}

    @_modal.method()
    def run_canary(
        self,
        request_id: str = "",
        submit_wall_unix_ns: int = 0,
    ) -> dict[str, Any]:
        entry_wall_ns = int(time.time() * 1_000_000_000)
        markers = list(getattr(self, "_gpu_snapshot_markers", []))
        return {
            "phase": getattr(self, "_phase", "unknown"),
            "request_id": request_id,
            "submit_wall_unix_ns": int(submit_wall_unix_ns or 0),
            "entry_wall_unix_ns": entry_wall_ns,
            "versions": getattr(self, "_gpu_snapshot_versions", _record_versions()),
            "verification": getattr(self, "_gpu_snapshot_verification", {}),
            "build_state": getattr(self, "_canary_build_state", {}),
            "restore_state": getattr(self, "_canary_restore_state", {}),
            "markers": markers,
        }


# ═══════════════════════════════════════════════════════════════════════
# Gate 3 — full-stack (UNET + CLIP + VAE) GPU snapshot (isolated shadow)
# ═══════════════════════════════════════════════════════════════════════


def _shadow_init(self: Any) -> None:
    """Replicate the production V2 lazy-init attribute surface.

    The shadow class deliberately avoids Modal's custom-constructor path
    (same pattern as the production ``ModalRuntimeEntrypointV2``), so the
    attribute list below is a minimal stable mirror of ``_v2_init_instance``.
    """
    if getattr(self, "_shadow_initialized", False):
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
    self._preload_bridge = V2LoaderBridge()
    self._lifecycle_trace = None
    self.container_session_id = _V2_CONTAINER_SESSION_ID
    self._restore_count = 0
    self._restore_timing = None
    self._cgroup_sampler = None
    self._cpu_snapshot_unet_runtime_state = None
    self._full_trace_session = None
    self._torch_thread_limit_applied = False
    self._gpu_snapshot_markers = []
    # Gate 3 full-stack retained objects (set during snap=True; the snapshot
    # carries them, the restored container must never rebuild them).
    self._shadow_unet = None
    self._shadow_unet_name = ""
    self._shadow_clip = None
    self._shadow_clip_name = ""
    self._shadow_clip_type = ""
    self._shadow_vae = None
    self._shadow_vae_name = ""
    self._shadow_cachedit_applied = False
    self._shadow_workflow_provisioned = False
    self._shadow_workflow_hash = ""
    self._shadow_read_baseline_len = 0
    self._shadow_initialized = True


def _marker_wall(markers: list[dict[str, Any]], name: str) -> int | None:
    """Last wall_unix_ns for a marker name, else None."""
    for m in reversed(markers):
        if m.get("marker") == name:
            try:
                value = int(m.get("wall_unix_ns", 0)) or None
            except (TypeError, ValueError):
                value = None
            if value is not None:
                return value
    return None


def _build_gpu_snapshot_waterfall(
    self: Any,
    request_id: str,
    result: Mapping[str, Any],
    run_label: str,
) -> Any:
    """Adapter for the DIRECT full-workflow result path.

    ``run_gpu_snapshot_workflow`` bypasses ``ModalRuntimeEntrypoint.run_plan_stream``
    (which normally assembles the trace/waterfall), so there is no trace to
    feed ``build_waterfall``.  This converts the existing hard markers
    (``self._gpu_snapshot_markers``) and ``_SHADOW_TIMING_EVENTS`` into the
    waterfall's input shape using SAME-PROCESS remote wall timestamps only.
    The local submit wall clock is never used as the command boundary (it is
    a cross-host clock and would skew the report).

    Stages whose boundaries are absent stay ``unavailable`` — never fabricated
    zeros.  Returns the built ``WaterfallReport``.
    """
    markers = list(getattr(self, "_gpu_snapshot_markers", []) or [])
    post_restore_ns = _marker_wall(markers, "gpu_snapshot_post_restore_enter")
    method_ns = _marker_wall(markers, "gpu_snapshot_request_method_entry")
    gen_ns = _marker_wall(markers, "gpu_snapshot_generation_complete")

    events: list[dict[str, Any]] = []
    if method_ns is not None:
        events.append({
            "name": "remote_method_entry",
            "process": "remote",
            "wall_unix_ns": method_ns,
            "request_id": request_id,
        })
    for ev in _SHADOW_TIMING_EVENTS:
        kind = str(ev.get("kind", ""))
        start_ns = ev.get("start_wall_unix_ns")
        end_ns = ev.get("end_wall_unix_ns")
        if kind == "sampler":
            events.append({"name": "sampling_start", "process": "remote", "wall_unix_ns": start_ns})
            events.append({"name": "sampling_end", "process": "remote", "wall_unix_ns": end_ns})
        elif kind == "vae_decode":
            events.append({"name": "vae_decode_start", "process": "remote", "wall_unix_ns": start_ns})
            events.append({"name": "vae_decode_end", "process": "remote", "wall_unix_ns": end_ns})

    total_ms: float | None = None
    if post_restore_ns is not None and gen_ns is not None:
        total_ms = (gen_ns - post_restore_ns) / 1_000_000.0
    elif method_ns is not None and gen_ns is not None:
        total_ms = (gen_ns - method_ns) / 1_000_000.0
    else:
        _gw = result.get("generation_wall_ms")
        if isinstance(_gw, (int, float)) and not isinstance(_gw, bool):
            total_ms = float(_gw)

    restore_timing: dict[str, Any] = {}
    if post_restore_ns is not None:
        restore_timing["restore_method_start_wall_unix_ns"] = post_restore_ns
        if method_ns is not None:
            restore_timing["restore_method_end_wall_unix_ns"] = method_ns

    view: dict[str, Any] = {
        "request_id": request_id,
        "identity": {
            "app_name": SHADOW_APP_NAME,
            "class_name": type(self).__name__,
            "gpu": GPU,
            "container_session_id": getattr(self, "container_session_id", ""),
            "restore_count": getattr(self, "_restore_count", 0),
            "request_count": 1,
        },
        "_restore_timing": restore_timing,
        "trace": {"events": events},
    }
    return build_waterfall(
        result=view,
        timing={},
        wall_ms=total_ms,
        run_label=run_label,
    )


@app.cls(
    gpu=GPU,
    cpu=CPU,
    memory=MEMORY_MB,
    timeout=TIMEOUT,
    min_containers=MIN_CONTAINERS,
    scaledown_window=SCALEDOWN_WINDOW,
    enable_memory_snapshot=True,
    experimental_options={"enable_gpu_snapshot": True},
    single_use_containers=SINGLE_USE,
    env=_SHADOW_ENV,
    volumes={
        MODELS_PATH: _modal.Volume.from_name("comfyui-models", create_if_missing=True),
        CUSTOM_NODES_PATH: _modal.Volume.from_name("comfyui-custom-nodes", create_if_missing=True),
        RUNTIME_STATE_PATH: _modal.Volume.from_name("comfymodal-runtime-config", create_if_missing=True),
    },
    **_pin_kwargs(),
)
class GpuSnapshotUnetShadow(ModalRuntimeEntrypoint):
    """Gate 3: production ComfyUI init + full-stack (UNET+CLIP+VAE) GPU snapshot.

    snap=True enter: ComfyUI init normally, load the exact Z-Image UNET,
    Qwen-3 4B CLIP, and AE VAE via the normal ComfyUI loading path, move all
    three to CUDA through the normal ComfyUI path, pre-apply CacheDiT (via
    the production restore machinery), run one dependency preflight + one
    graph compile/validation/certificate pass with the provisioned workflow,
    verify each model CUDA-resident, record memory, sync, return.

    snap=False enter (restore): verify CUDA + all three models CUDA-resident +
    identities, record memory.  The workflow itself runs in
    ``run_gpu_snapshot_workflow`` (publishing the retained UNET/CLIP/VAE as
    ready on the loader bridge — the identity-checked consumption path; the
    original loaders never run for them), with CLIP encode / sampler / VAE
    decode through their existing normal paths.
    """

    __init__ = object.__init__  # avoid Modal's custom-constructor path

    # ── snap=True: build the snapshot ──────────────────────────────────
    @_modal.enter(snap=True)
    def snapshot_build(self) -> dict[str, Any]:
        _shadow_init(self)
        self._gpu_snapshot_markers = []
        self._phase = "build"
        _emit(self, "gpu_snapshot_enter_start")
        trace = RuntimeTrace(process="remote")
        try:
            self._configure_runtime()
            # The production start_backend callback wraps the backend start
            # in _force_cpu_during_snapshot (CPU-snapshot semantics).  For a
            # GPU snapshot we must keep the GPU visible while blocking CUDA
            # C-extension imports — the comfyapp GPU-snapshot variant.
            api = self._legacy_api or self._load_legacy_runtime()

            def _gpu_snapshot_start_backend() -> str:
                triton_ctx = getattr(api, "_force_triton_during_snapshot", None)
                if callable(triton_ctx):
                    with triton_ctx():
                        api._start_in_process_backend()
                else:
                    api._start_in_process_backend()
                return "in_process"

            self.bootstrap.start_backend = _gpu_snapshot_start_backend
            self.bootstrap._backend_started = False
            state = self.bootstrap.startup(snapshot=True, trace=trace)
            _emit(self, "gpu_snapshot_comfy_init_complete",
                  backend=str(getattr(state, "backend", "") or ""))
        except Exception as exc:  # noqa: BLE001
            _emit(self, "gpu_snapshot_comfy_init_complete", error=type(exc).__name__)
            raise

        # ── Explicit CUDA initialization (request-independent) ──
        try:
            import torch as _torch
            api._initialize_cuda_context()
            torch_synchronize()
            _emit(self, "gpu_snapshot_cuda_init_complete",
                  available=int(_torch.cuda.is_available()))
        except Exception as exc:  # noqa: BLE001
            _emit(self, "gpu_snapshot_cuda_init_complete", error=type(exc).__name__)
            raise

        # ── Install shadow instrumentation (read recorder + timing
        #    wrappers) BEFORE any further model work so the snapshot carries
        #    them and the restored request can be proven clean. ──
        _install_shadow_read_recorder()
        _install_shadow_timing_wrappers()
        _emit(self, "gpu_snapshot_instrumentation_installed")

        # ── GPU arm retained-state stage: before_models ──
        _gpu_stage_fields(self, "before_models", unet=None, clip=None, vae=None)

        # ── Provisioned workflow (topology fixture for preflight /
        #    prevalidation / CacheDiT preparation).  Optional. ──
        wf, wf_modal_options = _read_provisioned_workflow()
        self._shadow_workflow_provisioned = bool(wf)
        self._shadow_workflow_hash = _workflow_hash(wf) if wf else ""
        _emit(self, "gpu_snapshot_workflow_provisioned",
              present=int(bool(wf)), hash=self._shadow_workflow_hash[:16])

        # ── One dependency preflight (populates the in-memory dependency
        #    validation cache + persists the immutable manifest on the
        #    runtime-config volume).  The post-restore preflight then takes
        #    the cheap identity-check fast path. ──
        if wf:
            try:
                _pf_t0 = time.perf_counter()
                _pf = api._preflight_before_prompt_execution(wf)
                _emit(self, "gpu_snapshot_dependency_preflight_complete",
                      total_ms=round((time.perf_counter() - _pf_t0) * 1000.0, 3),
                      prepared=int(bool(_pf.get("prepared", True))))
            except Exception as exc:  # noqa: BLE001
                _emit(self, "gpu_snapshot_dependency_preflight_complete",
                      error=f"{type(exc).__name__}: {str(exc)[:120]}")
                raise

        # ── UNET construction + load (normal ComfyUI path) ──
        # NOTE: production's `_load_cpu_snapshot_unet` applies
        # `validate_snapshot_unet_bf16_native` which REQUIRES CPU residency —
        # a CPU-snapshot invariant.  In GPU-snapshot mode ComfyUI loads the
        # model directly onto cuda (GPU visible during snap=True), which is
        # exactly the state we want captured.  We therefore use the SAME
        # underlying loader (`comfy.sd.load_diffusion_model` under the
        # bf16-native compute policy) without the CPU-only validation.
        import comfy.model_management as mm
        import comfy.sd as _comfy_sd
        import folder_paths as _fp
        from comfymodal_runtime.modal_app import resolve_unet_effective_dtype
        from comfymodal_runtime.model_preload import cpu_snapshot_unet_compute_policy

        unet_name = os.environ.get("COMFYMODAL_WARMUP_UNET", "").strip()
        if not unet_name:
            raise RuntimeError("COMFYMODAL_WARMUP_UNET is not set; cannot load the Z-Image UNET")
        _emit(self, "gpu_snapshot_unet_load_start", unet=unet_name)
        weight_dtype = os.environ.get("COMFYMODAL_WARMUP_UNET_DTYPE", "default").strip() or "default"
        target_gpus = parse_gpu_request()
        _eff_dtype, _eff_label = resolve_unet_effective_dtype(
            weight_dtype, target_gpus=target_gpus,
        )
        _unet_path = _fp.get_full_path_or_raise("diffusion_models", unet_name)
        with cpu_snapshot_unet_compute_policy(
            effective_weight_dtype=_eff_dtype,
            target_gpus=target_gpus,
        ):
            unet = _comfy_sd.load_diffusion_model(
                _unet_path, model_options={"dtype": _eff_dtype},
            )
        if isinstance(unet, (tuple, list)) and len(unet) > 0:
            unet = unet[0]
        _emit(self, "gpu_snapshot_unet_load_complete", unet=unet_name,
              object_type=type(unet).__name__,
              effective_weight_dtype=_eff_label)

        # ── Move UNET to CUDA through the normal ComfyUI path ──
        mm.load_models_gpu([unet])
        residency = prove_unet_gpu_residency(unet, model_management=mm)
        _emit(self, "gpu_snapshot_unet_cuda_verified",
              status=str(residency.get("status", "unknown")),
              gpu_parameter_fraction=str(residency.get("gpu_parameter_fraction", "")))
        self._shadow_unet = unet
        self._shadow_unet_name = unet_name

        # ── CLIP construction + load + CUDA (normal graph loader path) ──
        clip = None
        clip_name = os.environ.get("COMFYMODAL_WARMUP_CLIP1", "").strip()
        clip_type = os.environ.get("COMFYMODAL_WARMUP_CLIP_TYPE", "").strip() or "lumina2"
        loaders = _load_spec_from_workflow(wf) if wf else {}
        _clip_requests = loaders.get("clip", []) if isinstance(loaders, Mapping) else []
        if _clip_requests and not clip_name:
            _clip_req = _clip_requests[0]
            clip_name = str(_clip_req.get("clip_name", ""))
            clip_type = str(_clip_req.get("type", clip_type))
        if clip_name:
            import nodes as _nodes
            _emit(self, "gpu_snapshot_clip_load_start", clip=clip_name, clip_type=clip_type)
            _clip_cls = _nodes.NODE_CLASS_MAPPINGS.get("CLIPLoader")
            _clip_out = _clip_cls().load_clip(clip_name, type=clip_type, device="default")
            clip = _clip_out[0] if isinstance(_clip_out, (tuple, list)) and _clip_out else _clip_out
            _emit(self, "gpu_snapshot_clip_load_complete", clip=clip_name,
                  object_type=type(clip).__name__)
            # Guarantee CUDA + registration (HIGH_VRAM path loads at
            # construction; the explicit call is the registration guarantee).
            mm.load_models_gpu([clip.patcher])
            _clip_mod, _clip_patcher = _clip_module_and_patcher(clip)
            _clip_res = _prove_model_gpu_residency(_clip_mod, _clip_patcher, "clip")
            _emit(self, "gpu_snapshot_clip_cuda_verified",
                  status=str(_clip_res.get("status", "unknown")),
                  gpu_parameter_fraction=str(_clip_res.get("gpu_parameter_fraction", "")))
            self._shadow_clip = clip
            self._shadow_clip_name = clip_name
            self._shadow_clip_type = clip_type
        else:
            _emit(self, "gpu_snapshot_clip_load_start", clip="", skipped=1,
                  reason="no_clip_request")

        # ── VAE construction + load + CUDA (normal graph loader path) ──
        vae = None
        vae_name = os.environ.get("COMFYMODAL_WARMUP_VAE", "").strip()
        _vae_requests = loaders.get("vae", []) if isinstance(loaders, Mapping) else []
        if _vae_requests and not vae_name:
            vae_name = str(_vae_requests[0].get("vae_name", ""))
        if vae_name:
            import nodes as _nodes
            _emit(self, "gpu_snapshot_vae_load_start", vae=vae_name)
            _vae_cls = _nodes.NODE_CLASS_MAPPINGS.get("VAELoader")
            _vae_out = _vae_cls().load_vae(vae_name)
            vae = _vae_out[0] if isinstance(_vae_out, (tuple, list)) and _vae_out else _vae_out
            _emit(self, "gpu_snapshot_vae_load_complete", vae=vae_name,
                  object_type=type(vae).__name__)
            mm.load_models_gpu([vae.patcher])
            _vae_mod, _vae_patcher = _vae_module_and_patcher(vae)
            _vae_res = _prove_model_gpu_residency(_vae_mod, _vae_patcher, "vae")
            _emit(self, "gpu_snapshot_vae_cuda_verified",
                  status=str(_vae_res.get("status", "unknown")),
                  gpu_parameter_fraction=str(_vae_res.get("gpu_parameter_fraction", "")))
            self._shadow_vae = vae
            self._shadow_vae_name = vae_name
        else:
            _emit(self, "gpu_snapshot_vae_load_start", vae="", skipped=1,
                  reason="no_vae_request")

        # ── GPU arm retained-state stage: full_stack_loaded ──
        _gpu_stage_fields(self, "full_stack_loaded", unet=unet, clip=clip, vae=vae)

        # ── CacheDiT pre-application (deterministic; request-time graph
        #    re-apply is an idempotent no-op).  Reuses the production
        #    restore machinery exactly. ──
        if wf and unet is not None:
            _cd_inputs: dict[str, Any] = {}
            _cd_node_id = ""
            for _nid, _node in wf.items():
                if isinstance(_node, Mapping) and _node.get("class_type") == "CacheDiT_Model_Optimizer":
                    _cd_node_id = str(_nid)
                    _cd_inputs = dict(_node.get("inputs", {}) or {})
                    break
            if _cd_node_id:
                try:
                    _cd_result = state._restore_cachedit_prepare(
                        unet=unet,
                        workflow_inputs=_cd_inputs,
                        workflow_hash=self._shadow_workflow_hash,
                    )
                    if _cd_result.get("ok") and _cd_result.get("patched_model") is not None:
                        unet = _cd_result["patched_model"]
                        self._shadow_unet = unet
                        self._shadow_cachedit_applied = True
                        _emit(self, "gpu_snapshot_cachedit_prepared",
                              node_id=_cd_node_id, applied=1,
                              identity=str(_cd_result.get("unet_identity", ""))[:16])
                    else:
                        _emit(self, "gpu_snapshot_cachedit_prepared",
                              node_id=_cd_node_id, applied=0,
                              reason=str(_cd_result.get("error", "not_ok"))[:120])
                except Exception as exc:  # noqa: BLE001
                    _emit(self, "gpu_snapshot_cachedit_prepared",
                          node_id=_cd_node_id, applied=0,
                          error=f"{type(exc).__name__}: {str(exc)[:120]}")
            else:
                _emit(self, "gpu_snapshot_cachedit_prepared", node_id="", applied=0,
                      reason="no_cachedit_node")

        # ── One graph compile + validation + certificate pass (topology-
        #    only cached state; certificate identity is prompt-bound in the
        #    current architecture, so only same-prompt requests hit it). ──
        if wf:
            try:
                _gv = _prevalidate_graph(api, wf, wf_modal_options)
                _emit(self, "gpu_snapshot_graph_prevalidation_complete",
                      cert_identity=str(_gv.get("cert_identity", ""))[:16],
                      cert_written=int(bool(_gv.get("cert_written"))),
                      workflow_cache_seeded=int(bool(_gv.get("workflow_cache_seeded"))),
                      validate_ms=round(float(_gv.get("validate_ms", 0.0)), 3))
            except Exception as exc:  # noqa: BLE001
                _emit(self, "gpu_snapshot_graph_prevalidation_complete",
                      error=f"{type(exc).__name__}: {str(exc)[:120]}")

        # ── Pre-capture verification: every model fully CUDA-resident ──
        _pre = {"unet": {}, "clip": {}, "vae": {}}
        if unet is not None:
            _pre["unet"] = prove_unet_gpu_residency(unet, model_management=mm)
        if clip is not None:
            _cm, _cp = _clip_module_and_patcher(clip)
            _pre["clip"] = _prove_model_gpu_residency(_cm, _cp, "clip")
        if vae is not None:
            _vm, _vp = _vae_module_and_patcher(vae)
            _pre["vae"] = _prove_model_gpu_residency(_vm, _vp, "vae")
        self._gpu_snapshot_cuda_before = {
            "allocated": int(torch_memory_allocated()),
            "reserved": int(torch_memory_reserved()),
        }
        _emit(self, "gpu_snapshot_pre_capture_verified",
              unet_status=str(_pre["unet"].get("status", "")),
              unet_gpu_fraction=str(_pre["unet"].get("gpu_parameter_fraction", "")),
              clip_status=str(_pre["clip"].get("status", "")),
              clip_gpu_fraction=str(_pre["clip"].get("gpu_parameter_fraction", "")),
              vae_status=str(_pre["vae"].get("status", "")),
              vae_gpu_fraction=str(_pre["vae"].get("gpu_parameter_fraction", "")))
        # ── CPU-eviction flag probe (GPU arm): the production eviction
        #    machinery (_evict_snapshot_models) operates on the CPU-side
        #    CpuSnapshotModels container, which a GPU snapshot never
        #    constructs — the models are loaded CUDA-direct and retained as
        #    GPU-resident objects.  This line documents, per capture, that
        #    there is nothing CPU-side for eviction to act on. ──
        if _parse_evict_models_before_snapshot():
            _emit(self, "gpu_snapshot_evict_flag", enabled=1,
                  cpu_snapshot_models_present=0,
                  unet_gpu_resident=int(_pre["unet"].get("status") == "gpu_resident"),
                  clip_gpu_resident=int(_pre["clip"].get("status") == "gpu_resident"),
                  vae_gpu_resident=int(_pre["vae"].get("status") == "gpu_resident"))
        _emit(self, "gpu_snapshot_cuda_memory",
              allocated=self._gpu_snapshot_cuda_before["allocated"],
              reserved=self._gpu_snapshot_cuda_before["reserved"])
        # ── GPU arm retained-state stage: final_pre_capture ──
        _gpu_stage_fields(self, "final_pre_capture", unet=unet, clip=clip, vae=vae,
                          final=True)
        torch_synchronize()
        _emit(self, "gpu_snapshot_pre_capture_sync_complete")
        # ── Boundary A — literal FINAL user-code measurement before the
        #    snap=True return: all models CUDA-resident, CacheDiT/preflight/
        #    validation complete, CUDA synchronized.  Nothing but logging
        #    executes between this marker and the return. ──
        self._gpu_build_cpu_models_never_constructed = True
        _boundary_a = _capture_gpu_snapshot_boundary(self, unet, clip, vae, mm)
        _emit_boundary(self, "gpu_snapshot_final_pre_capture", _boundary_a)
        _emit(self, "gpu_snapshot_enter_returning")
        return {"phase": "build"}

    # ── snap=False: restored container verification ────────────────────
    @_modal.enter(snap=False)
    def restore_snapshot(self) -> dict[str, Any]:
        # FIRST executable line of the restored Python process (timing anchor;
        # logging only — no state mutation).
        _emit(self, "gpu_snapshot_post_restore_enter")
        # ── Boundary B — literal FIRST measurement after restore, BEFORE
        #    any CUDA verification / model verification / bridge activity /
        #    cleanup / GC / bootstrap work.  cgroup + CUDA are captured
        #    before the model storage walk (the walk demand-pages CPU-side
        #    wrapper metadata — a bounded measurement artifact). ──
        import comfy.model_management as _mm_b0  # noqa: E402 (cached import)
        _boundary_b = _capture_gpu_snapshot_boundary(
            self,
            getattr(self, "_shadow_unet", None),
            getattr(self, "_shadow_clip", None),
            getattr(self, "_shadow_vae", None),
            _mm_b0,
        )
        _emit_boundary(self, "gpu_snapshot_first_python_after_restore", _boundary_b)
        self._phase = "restore"
        _shadow_init(self)
        import torch
        import comfy.model_management as mm

        verify: dict[str, Any] = {}
        # CUDA functional check (trivial op, no model load).
        try:
            torch.cuda.init()
            ok = torch.cuda.is_available()
            probe = torch.tensor([1.0, 2.0], device="cuda")
            probe_sum = float((probe + 1.0).sum().item())
            torch.cuda.synchronize()
            verify["cuda_functional"] = bool(ok)
            verify["cuda_probe_sum"] = probe_sum
        except Exception as exc:  # noqa: BLE001
            verify["cuda_functional"] = False
            verify["cuda_error"] = f"{type(exc).__name__}: {exc}"
        _emit(self, "gpu_snapshot_post_restore_cuda_verified",
              functional=int(bool(verify.get("cuda_functional"))))

        # ── All three objects present and CUDA-resident, identities match ──
        unet = getattr(self, "_shadow_unet", None)
        clip = getattr(self, "_shadow_clip", None)
        vae = getattr(self, "_shadow_vae", None)
        verify["unet_object_present"] = unet is not None
        verify["clip_object_present"] = clip is not None
        verify["vae_object_present"] = vae is not None
        verify["unet_identity"] = str(getattr(self, "_shadow_unet_name", "") or "")
        verify["clip_identity"] = str(getattr(self, "_shadow_clip_name", "") or "")
        verify["clip_type"] = str(getattr(self, "_shadow_clip_type", "") or "")
        verify["vae_identity"] = str(getattr(self, "_shadow_vae_name", "") or "")

        if unet is not None:
            try:
                residency = prove_unet_gpu_residency(unet, model_management=mm)
                verify["unet_residency_status"] = str(residency.get("status", "unknown"))
                verify["unet_gpu_parameter_fraction"] = str(
                    residency.get("gpu_parameter_fraction", "")
                )
                verify["unet_already_cuda_resident"] = (
                    residency.get("status") == "gpu_resident"
                )
            except Exception as exc:  # noqa: BLE001
                verify["unet_residency_error"] = f"{type(exc).__name__}: {exc}"
                verify["unet_already_cuda_resident"] = False
        if clip is not None:
            try:
                _cm, _cp = _clip_module_and_patcher(clip)
                _res = _prove_model_gpu_residency(_cm, _cp, "clip")
                verify["clip_residency_status"] = str(_res.get("status", "unknown"))
                verify["clip_gpu_parameter_fraction"] = str(
                    _res.get("gpu_parameter_fraction", "")
                )
                verify["clip_already_cuda_resident"] = (
                    _res.get("status") == "gpu_resident"
                )
            except Exception as exc:  # noqa: BLE001
                verify["clip_residency_error"] = f"{type(exc).__name__}: {exc}"
                verify["clip_already_cuda_resident"] = False
        if vae is not None:
            try:
                _vm, _vp = _vae_module_and_patcher(vae)
                _res = _prove_model_gpu_residency(_vm, _vp, "vae")
                verify["vae_residency_status"] = str(_res.get("status", "unknown"))
                verify["vae_gpu_parameter_fraction"] = str(
                    _res.get("gpu_parameter_fraction", "")
                )
                verify["vae_already_cuda_resident"] = (
                    _res.get("status") == "gpu_resident"
                )
            except Exception as exc:  # noqa: BLE001
                verify["vae_residency_error"] = f"{type(exc).__name__}: {exc}"
                verify["vae_already_cuda_resident"] = False
        try:
            verify["allocated_after_restore"] = int(torch_memory_allocated())
            verify["reserved_after_restore"] = int(torch_memory_reserved())
        except Exception:  # noqa: BLE001
            pass
        _emit(self, "gpu_snapshot_post_restore_models_verified",
              unet_present=int(bool(verify.get("unet_object_present"))),
              unet_cuda_resident=int(bool(verify.get("unet_already_cuda_resident"))),
              clip_present=int(bool(verify.get("clip_object_present"))),
              clip_cuda_resident=int(bool(verify.get("clip_already_cuda_resident"))),
              vae_present=int(bool(verify.get("vae_object_present"))),
              vae_cuda_resident=int(bool(verify.get("vae_already_cuda_resident"))))
        # ── Restore-time retained-state measurement (state after Modal
        #    restored the GPU snapshot; nothing executed since). ──
        try:
            verify["process_memory_after_restore"] = probe_process_memory()
            verify["cuda_after_restore"] = probe_cuda_memory()
            verify["cuda_model_storage_after_restore"] = probe_model_storage(
                unet, clip, vae, device_prefix="cuda",
            )
            verify["worker_fingerprint"] = probe_worker_fingerprint(cuda_torch=True)
            verify["threads_after_restore"] = _probe_thread_state()
            verify["modules_after_restore"] = _probe_loaded_modules()
            verify["gc_objects_after_restore"] = _probe_gc_count()
            _restore_fields: dict[str, Any] = {
                "rss_mib": verify["process_memory_after_restore"].get("rss_mib"),
                "pss_mib": verify["process_memory_after_restore"].get("pss_mib"),
                "cgroup_current_mib": verify["process_memory_after_restore"].get(
                    "cgroup_current_mib"
                ),
                "cuda_allocated_mib": verify["cuda_after_restore"].get("allocated_mib"),
                "cuda_reserved_mib": verify["cuda_after_restore"].get("reserved_mib"),
                "total_cuda_model_bytes": verify["cuda_model_storage_after_restore"].get(
                    "total_unique_model_bytes", 0
                ),
            }
            emit_stage_line("gpu_snapshot_size", "restored", _restore_fields)
        except Exception:  # noqa: BLE001
            pass
        # ── Boundary B2 — state AFTER the normal GPU restore verification
        #    (CUDA check, residency proofs, probes): same fields, so the
        #    first-Python vs post-verified transition is observable. ──
        try:
            _boundary_b2 = _capture_gpu_snapshot_boundary(self, unet, clip, vae, mm)
            _emit_boundary(self, "gpu_snapshot_post_restore_verified", _boundary_b2)
        except Exception:  # noqa: BLE001
            pass
        _emit(self, "gpu_snapshot_post_restore_verify_complete")
        self._gpu_snapshot_verification = verify
        return {"phase": "restore"}

    # ── Request method ─────────────────────────────────────────────────
    @_modal.method()
    def run_gpu_snapshot_restore_probe(
        self,
        request_id: str = "",
        submit_wall_unix_ns: int = 0,
    ) -> dict[str, Any]:
        """RESTORE-ONLY probe: verify the restored GPU snapshot state and
        return a tiny JSON result.  No workflow, no CLIP encode, no
        sampling, no VAE decode, no image output.

        T1 (banner → first Python line) is anchored on the
        ``gpu_snapshot_post_restore_enter`` marker emitted by the snap=False
        enter; this method only measures and returns.
        """
        _shadow_init(self)
        entry_wall_ns = int(time.time() * 1_000_000_000)
        _emit(self, "gpu_snapshot_restore_probe_entry", request_id=request_id)
        import comfy.model_management as mm
        unet = getattr(self, "_shadow_unet", None)
        clip = getattr(self, "_shadow_clip", None)
        vae = getattr(self, "_shadow_vae", None)
        verify: dict[str, Any] = {
            "unet_object_present": unet is not None,
            "clip_object_present": clip is not None,
            "vae_object_present": vae is not None,
            "unet_identity": str(getattr(self, "_shadow_unet_name", "") or ""),
            "clip_identity": str(getattr(self, "_shadow_clip_name", "") or ""),
            "vae_identity": str(getattr(self, "_shadow_vae_name", "") or ""),
        }
        ok = bool(unet is not None and clip is not None and vae is not None)
        try:
            if unet is not None:
                res = prove_unet_gpu_residency(unet, model_management=mm)
                verify["unet_residency_status"] = str(res.get("status", "unknown"))
                verify["unet_already_cuda_resident"] = res.get("status") == "gpu_resident"
                ok = ok and res.get("status") == "gpu_resident"
            _cm, _cp = _clip_module_and_patcher(clip) if clip is not None else (None, None)
            if clip is not None:
                res = _prove_model_gpu_residency(_cm, _cp, "clip")
                verify["clip_residency_status"] = str(res.get("status", "unknown"))
                verify["clip_already_cuda_resident"] = res.get("status") == "gpu_resident"
                ok = ok and res.get("status") == "gpu_resident"
            _vm, _vp = _vae_module_and_patcher(vae) if vae is not None else (None, None)
            if vae is not None:
                res = _prove_model_gpu_residency(_vm, _vp, "vae")
                verify["vae_residency_status"] = str(res.get("status", "unknown"))
                verify["vae_already_cuda_resident"] = res.get("status") == "gpu_resident"
                ok = ok and res.get("status") == "gpu_resident"
        except Exception as exc:  # noqa: BLE001
            verify["residency_error"] = f"{type(exc).__name__}: {exc}"
            ok = False
        try:
            verify["process_memory"] = probe_process_memory()
            verify["cuda_memory"] = probe_cuda_memory()
            verify["cuda_model_storage"] = probe_model_storage(
                unet, clip, vae, device_prefix="cuda",
            )
            verify["worker_fingerprint"] = probe_worker_fingerprint(cuda_torch=True)
            verify["threads_after_restore"] = _probe_thread_state()
            verify["modules_after_restore"] = _probe_loaded_modules()
            verify["gc_objects_after_restore"] = _probe_gc_count()
        except Exception:  # noqa: BLE001
            pass
        _emit(self, "gpu_snapshot_restore_probe_complete",
              ok=int(ok), request_id=request_id)
        return {
            "phase": getattr(self, "_phase", "unknown"),
            "request_id": request_id,
            "submit_wall_unix_ns": int(submit_wall_unix_ns or 0),
            "entry_wall_unix_ns": entry_wall_ns,
            "verification": verify,
            "boundaries": getattr(self, "_gpu_snapshot_boundaries", {}),
            "build_stages": getattr(self, "_gpu_snapshot_size_stages", {}),
            "build_fingerprint": getattr(self, "_gpu_snapshot_fingerprint", {}),
            "markers": list(getattr(self, "_gpu_snapshot_markers", [])),
        }

    # ── Request method ─────────────────────────────────────────────────
    @_modal.method()
    def run_gpu_snapshot_workflow(
        self,
        workflow: Mapping[str, Any],
        modal_options: Mapping[str, Any] | None = None,
        request_id: str = "",
        submit_wall_unix_ns: int = 0,
    ) -> dict[str, Any]:
        """Execute ONE real Z-Image workflow on the restored container.

        The restored UNET/CLIP/VAE are published as ready on the loader
        bridge (identity-checked consumption — the original loaders never
        run for them), so no safetensors reread and no CPU->GPU migration
        happens for any of the three.  Sampler, VAE, output persistence,
        and final image correctness are verified; file reads and
        ``load_models_gpu`` calls are instrumented for hard proof.
        """
        _shadow_init(self)
        _SHADOW_TIMING_EVENTS.clear()
        entry_wall_ns = int(time.time() * 1_000_000_000)
        _emit(self, "gpu_snapshot_request_method_entry", request_id=request_id)
        api = self._load_legacy_runtime()
        bridge: V2LoaderBridge = self._preload_bridge
        unet = getattr(self, "_shadow_unet", None)
        clip = getattr(self, "_shadow_clip", None)
        vae = getattr(self, "_shadow_vae", None)
        result: dict[str, Any] = {}
        load_models_gpu_calls: list[dict[str, Any]] = []
        read_baseline = len(_SHADOW_READ_RECORDS)

        try:
            if unet is None:
                raise RuntimeError("restored UNET object is missing on the restored container")

            # ── Publish the retained CUDA-resident models as ready.  The
            #    identity-checked bridge consumption makes the graph
            #    loaders validation/no-op only; CLIP/VAE missing (fallback
            #    build) fall through to their original loaders. ──
            model_key = derive_model_key(dict(workflow))
            prefill_key = derive_prefill_key(model_key, dict(workflow))
            model_spec = build_restore_model_spec(dict(workflow), None)
            trace = RuntimeTrace(process="remote", request_id=request_id)
            prep = bridge._init_ready_preparation(
                model_key=model_key,
                prefill_key=prefill_key,
                model_spec=model_spec,
                unet=unet,
                clip=clip,
                trace=trace,
            )
            result["bridge_unet_ready"] = prep is not None and prep.unet_future is not None
            result["bridge_clip_ready"] = prep is not None and prep.clip_future is not None
            if vae is not None:
                # Late VAE-activation mode consumes ``prep.vae_future``; a
                # completed future makes graph VAELoader demand a no-op.
                from concurrent.futures import Future as _Future
                _vae_future: _Future = _Future()
                _vae_future.set_result(vae)
                prep.vae_future = _vae_future
                prep.diagnostics.vae_started_at = prep.diagnostics.vae_completed_at = time.time()
                try:
                    bridge.set_exact_vae(vae)
                    bridge.set_snapshot_loader_outputs({
                        "unet": unet, "clip": clip, "vae": vae,
                    })
                except Exception:  # noqa: BLE001
                    pass
            result["bridge_vae_ready"] = prep is not None and prep.vae_future is not None

            # ── Instrument load_models_gpu to prove all three models are
            #    never CPU->GPU transferred during the workflow. ──
            import comfy.model_management as mm
            original_lmg = mm.load_models_gpu

            def _patcher_device(m: Any) -> str:
                """True residency device of a ModelPatcher (``model.device`` in
                this ComfyUI build; ``current_device`` does not exist)."""
                try:
                    _cld = getattr(m, "current_loaded_device", None)
                    if callable(_cld):
                        _d = _cld()
                    else:
                        _d = getattr(getattr(m, "model", None), "device", None)
                    return str(_d) if _d is not None else "absent"
                except Exception:  # noqa: BLE001
                    return "absent"

            def _loaded_state() -> dict[int, str]:
                out: dict[int, str] = {}
                for _lm in list(getattr(mm, "current_loaded_models", [])):
                    _m = getattr(_lm, "model", None)
                    if _m is not None:
                        out[id(_m)] = _patcher_device(_m)
                return out

            def _recording_load_models_gpu(models, memory_required=0, force_patch_weights=False, **kw):
                t0 = time.perf_counter()
                allocated_before = torch_memory_allocated()
                state_before = _loaded_state()
                try:
                    return original_lmg(models, memory_required=memory_required,
                                        force_patch_weights=force_patch_weights, **kw)
                finally:
                    state_after = _loaded_state()
                    per_model = []
                    for m in (models or []):
                        mid = id(m)
                        per_model.append({
                            "patcher_id": mid,
                            "class": getattr(getattr(m, "model", None), "__class__", type(m)).__name__,
                            "is_shadow_unet": mid == id(unet),
                            "is_shadow_clip": clip is not None and mid == id(clip.patcher),
                            "is_shadow_vae": vae is not None and mid == id(vae.patcher),
                            "was_registered": mid in state_before,
                            "device_before": state_before.get(mid, "absent"),
                            "device_after": state_after.get(mid, "absent"),
                        })
                    _delta = int(torch_memory_allocated() - allocated_before) if allocated_before >= 0 else -1
                    load_models_gpu_calls.append({
                        "model_ids": [id(m) for m in (models or [])],
                        "per_model": per_model,
                        "wall_ms": round((time.perf_counter() - t0) * 1000.0, 3),
                        "allocated_delta": _delta,
                    })

            mm.load_models_gpu = _recording_load_models_gpu
            try:
                with bridge.request_scope():
                    gen_start_ns = int(time.time() * 1_000_000_000)
                    exec_result = api._execute_in_process(
                        dict(workflow),
                        input_images=None,
                        collect_outputs=True,
                        trace=None,
                        modal_options=dict(modal_options or {}),
                        production_report=None,
                    )
                    gen_end_ns = int(time.time() * 1_000_000_000)
            finally:
                mm.load_models_gpu = original_lmg

            images = list(exec_result.get("images", []) or [])
            videos = list(exec_result.get("videos", []) or [])
            result["images_count"] = len(images)
            result["videos_count"] = len(videos)
            result["generation_wall_ms"] = round((gen_end_ns - gen_start_ns) / 1_000_000, 3)
            result["image_verification"] = _verify_output_images(images)

            # ── H2D-bypass evidence.  A genuine CPU->GPU migration is a
            #    physical transfer: it moves gigabytes (allocated delta) and
            #    takes far longer than a validation walk.  A call whose
            #    demanded patchers were already cuda-resident (or absent from
            #    the registry with tensors already on cuda) with a
            #    sub-threshold wall time and no allocation growth is a
            #    validation no-op by definition. ──
            _H2D_DELTA_BYTES = 64 * 1024 * 1024   # 64 MB of allocation growth
            _H2D_WALL_MS = 500.0                  # a 12 GB H2D takes seconds

            def _call_migrated(call: dict[str, Any]) -> bool:
                return bool(
                    call.get("allocated_delta", 0) > _H2D_DELTA_BYTES
                    or call.get("wall_ms", 0.0) > _H2D_WALL_MS
                )

            unet_calls = [c for c in load_models_gpu_calls
                          if any(p.get("is_shadow_unet") for p in c.get("per_model", []))]
            clip_calls = [c for c in load_models_gpu_calls
                          if any(p.get("is_shadow_clip") for p in c.get("per_model", []))]
            vae_calls = [c for c in load_models_gpu_calls
                         if any(p.get("is_shadow_vae") for p in c.get("per_model", []))]
            result["load_models_gpu_calls"] = {
                "total": len(load_models_gpu_calls),
                "unet_calls": len(unet_calls),
                "clip_calls": len(clip_calls),
                "vae_calls": len(vae_calls),
                "all_call_wall_ms": [c.get("wall_ms") for c in load_models_gpu_calls],
                "all_call_allocated_delta": [c.get("allocated_delta") for c in load_models_gpu_calls],
                "unet_call_wall_ms": [c.get("wall_ms") for c in unet_calls],
                "clip_call_wall_ms": [c.get("wall_ms") for c in clip_calls],
                "vae_call_wall_ms": [c.get("wall_ms") for c in vae_calls],
                "unet_call_allocated_delta": [c.get("allocated_delta") for c in unet_calls],
                "clip_call_allocated_delta": [c.get("allocated_delta") for c in clip_calls],
                "vae_call_allocated_delta": [c.get("allocated_delta") for c in vae_calls],
                "per_call": load_models_gpu_calls,
            }
            result["unet_transferred_h2d"] = any(_call_migrated(c) for c in unet_calls)
            result["clip_transferred_h2d"] = any(_call_migrated(c) for c in clip_calls)
            result["vae_transferred_h2d"] = any(_call_migrated(c) for c in vae_calls)
            _emit(self, "gpu_snapshot_h2d_bypass_verified",
                  total_load_calls=len(load_models_gpu_calls),
                  unet_load_calls=len(unet_calls),
                  clip_load_calls=len(clip_calls),
                  vae_load_calls=len(vae_calls),
                  unet_h2d=int(result["unet_transferred_h2d"]),
                  clip_h2d=int(result["clip_transferred_h2d"]),
                  vae_h2d=int(result["vae_transferred_h2d"]))

            # ── Zero-reread evidence: the three model files must not appear
            #    in any read record since the request baseline. ──
            new_reads = _SHADOW_READ_RECORDS[read_baseline:]
            _model_names = {
                "unet": os.path.basename(str(getattr(self, "_shadow_unet_name", "") or "")),
                "clip": os.path.basename(str(getattr(self, "_shadow_clip_name", "") or "")),
                "vae": os.path.basename(str(getattr(self, "_shadow_vae_name", "") or "")),
            }
            rereads: dict[str, Any] = {}
            for _role, _name in _model_names.items():
                _hits = [r for r in new_reads if _name and r.get("basename") == _name]
                rereads[_role] = {
                    "expected_file": _name,
                    "reads": len(_hits),
                    "wall_ms": [r.get("wall_ms") for r in _hits],
                }
            result["file_rereads"] = {
                **rereads,
                "other_reads": [
                    {"basename": r.get("basename", ""), "wall_ms": r.get("wall_ms")}
                    for r in new_reads
                    if not any(r.get("basename") == v for v in _model_names.values() if v)
                ],
            }
            result["file_rereads_total"] = len(new_reads)
            _emit(self, "gpu_snapshot_no_reread_verified",
                  unet_rereads=int(rereads["unet"]["reads"]),
                  clip_rereads=int(rereads["clip"]["reads"]),
                  vae_rereads=int(rereads["vae"]["reads"]),
                  other_reads=len(result["file_rereads"]["other_reads"]))

            # ── Per-stage timing from the snapshot-retained wrappers ──
            result["stage_timing"] = list(_SHADOW_TIMING_EVENTS)
        except Exception as exc:  # noqa: BLE001
            result["error"] = f"{type(exc).__name__}: {exc}"
            result["load_models_gpu_calls"] = {
                "total": len(load_models_gpu_calls),
                "unet_calls": len([c for c in load_models_gpu_calls
                                   if any(p.get("is_shadow_unet") for p in c.get("per_model", []))]),
            }
        _emit(self, "gpu_snapshot_generation_complete",
              ok=int(not result.get("error") and result.get("images_count", 0) > 0))
        # ── Best-effort direct-path waterfall (restored workflow only).
        #    The direct path bypasses run_plan_stream, so the trace is
        #    synthesized here from the retained markers/timing wrappers.  A
        #    waterfall failure must never fail the workflow: attach a small
        #    error marker and continue. ──
        if getattr(self, "_phase", "unknown") == "restore":
            try:
                _report = _build_gpu_snapshot_waterfall(
                    self, request_id, result,
                    run_label="gpu-snapshot direct workflow",
                )
                attach_waterfall(
                    result, report=_report,
                    run_label="gpu-snapshot direct workflow",
                )
            except Exception as _wf_exc:  # noqa: BLE001
                result["waterfall_error"] = (
                    f"{type(_wf_exc).__name__}: {str(_wf_exc)[:160]}"
                )
                print(
                    f"[gpu_snapshot] waterfall_error "
                    f"error_type={type(_wf_exc).__name__}",
                    flush=True,
                )
        return {
            "phase": getattr(self, "_phase", "unknown"),
            "request_id": request_id,
            "submit_wall_unix_ns": int(submit_wall_unix_ns or 0),
            "entry_wall_unix_ns": entry_wall_ns,
            "verification": getattr(self, "_gpu_snapshot_verification", {}),
            "boundaries": getattr(self, "_gpu_snapshot_boundaries", {}),
            "result": result,
            "markers": list(getattr(self, "_gpu_snapshot_markers", [])),
        }


def _cpu_stage_fields(
    self: Any, stage: str, *,
    models: Any, evict_enabled: bool, retain_role: str,
    alive: dict[str, Any] | None = None,
) -> None:
    """Emit one ``cpu_snapshot_size stage=...`` line and retain the raw
    probe payloads on ``self._cpu_snapshot_size_stages[stage]``.

    Fields: process memory (RSS/PSS/anonymous/cgroup), deduplicated CPU
    model bytes per role (unique storage), total unique CPU model bytes,
    UNET/CLIP/VAE alive flags, eviction enabled + resolved retain role.
    """
    unet = getattr(models, "unet", None) if models is not None else None
    clip = getattr(models, "clip", None) if models is not None else None
    vae = getattr(models, "vae", None) if models is not None else None
    mem = probe_process_memory()
    storage = probe_model_storage(unet, clip, vae)
    if alive is None:
        alive = {
            "unet": int(unet is not None),
            "clip": int(clip is not None),
            "vae": int(vae is not None),
        }
    per_model = storage.get("per_model", {})
    fields: dict[str, Any] = {
        "rss_mib": mem.get("rss_mib"),
        "pss_mib": mem.get("pss_mib"),
        "anonymous_mib": mem.get("anonymous_mib"),
        "cgroup_current_mib": mem.get("cgroup_current_mib"),
        "unet_cpu_bytes": int(per_model.get("unet", {}).get("unique_storage_bytes", 0) or 0),
        "clip_cpu_bytes": int(per_model.get("clip", {}).get("unique_storage_bytes", 0) or 0),
        "vae_cpu_bytes": int(per_model.get("vae", {}).get("unique_storage_bytes", 0) or 0),
        "total_cpu_model_bytes": int(storage.get("total_unique_model_bytes", 0) or 0),
        "unet_alive": int(bool(alive.get("unet"))),
        "clip_alive": int(bool(alive.get("clip"))),
        "vae_alive": int(bool(alive.get("vae"))),
        "evict_enabled": int(bool(evict_enabled)),
        "retain_role": retain_role,
    }
    emit_stage_line("cpu_snapshot_size", stage, fields)
    if not hasattr(self, "_cpu_snapshot_size_stages"):
        self._cpu_snapshot_size_stages = {}
    self._cpu_snapshot_size_stages[str(stage)] = {
        "process": mem, "storage": storage, "alive": alive, "fields": fields,
    }


@app.cls(
    gpu=GPU,
    cpu=CPU,
    memory=MEMORY_MB,
    timeout=TIMEOUT,
    min_containers=MIN_CONTAINERS,
    scaledown_window=SCALEDOWN_WINDOW,
    enable_memory_snapshot=True,
    single_use_containers=SINGLE_USE,
    env=_SHADOW_ENV,
    volumes={
        MODELS_PATH: _modal.Volume.from_name("comfyui-models", create_if_missing=True),
        CUSTOM_NODES_PATH: _modal.Volume.from_name("comfyui-custom-nodes", create_if_missing=True),
        RUNTIME_STATE_PATH: _modal.Volume.from_name("comfymodal-runtime-config", create_if_missing=True),
    },
    **_pin_kwargs(),
)
class CpuSnapshotRestoreShadow(ModalRuntimeEntrypoint):
    """Matrix CPU arm: production CPU memory snapshot + restore-only probe.

    snap=True enter: calls the PRODUCTION ``startup`` method untouched
    (exact current CPU snapshot behavior — model loads, optional gated
    eviction, vae skip, startup-ready return), wrapped in the four
    retained-state stages:

      before_model_load     — process state before ``startup`` runs
      full_models_loaded    — process state after ``startup`` returned
      after_intended_eviction — same boundary; carries the resolved
                              eviction flag + retain role, so a baseline
                              run (eviction disabled) shows the models
                              still resident
      final_pre_capture     — immediately before Modal captures, with
                              detached weakref-alive proof

    snap=False enter: first-line marker (T1) + restore-time state.
    ``run_cpu_snapshot_restore_probe`` returns a tiny JSON result.
    """

    __init__ = object.__init__  # avoid Modal's custom-constructor path

    @_modal.enter(snap=True)
    def snapshot_build_cpu(self) -> dict[str, Any]:
        _shadow_init(self)
        self._gpu_snapshot_markers = []
        self._phase = "build"
        _emit(self, "cpu_snapshot_enter_start")
        evict_enabled = _parse_evict_models_before_snapshot()
        retain_role = _parse_evict_retain_role()
        self._cpu_evict_enabled = bool(evict_enabled)
        self._cpu_retain_role = retain_role
        _cpu_stage_fields(self, "before_model_load", models=None,
                          evict_enabled=evict_enabled, retain_role=retain_role)
        _build_start = time.perf_counter()
        try:
            result = self.startup()
        except BaseException as exc:  # noqa: BLE001
            _emit(self, "cpu_snapshot_startup_error", error=type(exc).__name__)
            raise
        _build_ms = round((time.perf_counter() - _build_start) * 1000.0, 1)
        _emit(self, "cpu_snapshot_startup_returned",
              status=str((result or {}).get("status", "")),
              build_ms=_build_ms)
        # ── Shadow instrumentation installed AFTER production startup so the
        #    request-time reload reads (post-restore) are the delta against
        #    the build-time baseline.  Retained in the snapshot. ──
        _install_shadow_read_recorder()
        _install_shadow_timing_wrappers()
        _emit(self, "cpu_snapshot_instrumentation_installed")
        models = getattr(self, "_cpu_snapshot_models", None)
        # With eviction disabled (baseline) the post-startup state IS the
        # full-models-loaded state; both stages are measured at the same
        # boundary and the eviction flags on the lines make that explicit.
        _cpu_stage_fields(self, "full_models_loaded", models=models,
                          evict_enabled=evict_enabled, retain_role=retain_role)
        _cpu_stage_fields(self, "after_intended_eviction", models=models,
                          evict_enabled=evict_enabled, retain_role=retain_role)
        # Detached weakref-alive proof: drop our locals, keep only the
        # state the snapshot will retain, then check liveness.  The
        # storage scan for final_pre_capture re-reads the models from the
        # retained state (``self._cpu_snapshot_models``) so the line shows
        # the true retained bytes, not 0.
        import gc as _gc
        import weakref as _wr
        _unet = getattr(models, "unet", None) if models is not None else None
        _clip = getattr(models, "clip", None) if models is not None else None
        _vae = getattr(models, "vae", None) if models is not None else None
        _wrs = {}
        for _role, _obj in (("unet", _unet), ("clip", _clip), ("vae", _vae)):
            if _obj is not None:
                try:
                    _wrs[_role] = _wr.ref(_obj)
                except TypeError:
                    _wrs[_role] = None
        _alive = {r: 0 for r in ("unet", "clip", "vae")}
        _retained_models: Any = models
        try:
            del models, _unet, _clip, _vae
            _gc.collect()
            for _role, _w in _wrs.items():
                _alive[_role] = int(_w is not None and _w() is not None)
            _retained_models = getattr(self, "_cpu_snapshot_models", None)
        except Exception:  # noqa: BLE001
            pass
        # Reference-holder survey (proves WHO keeps the storages alive).
        _holders: dict[str, Any] = {}
        try:
            import comfy.model_management as _mm
            _holders = probe_reference_holders(
                self, model_management=_mm,
                bootstrap_state=getattr(self, "bootstrap", None),
            )
        except Exception:  # noqa: BLE001
            _holders = {"error": "probe_failed"}
        self._cpu_snapshot_reference_holders = _holders
        _cpu_stage_fields(self, "final_pre_capture", models=_retained_models,
                          evict_enabled=evict_enabled, retain_role=retain_role,
                          alive=_alive)
        try:
            self._cpu_snapshot_fingerprint = probe_worker_fingerprint(cuda_torch=False)
        except Exception:  # noqa: BLE001
            self._cpu_snapshot_fingerprint = {}
        _emit(self, "cpu_snapshot_enter_returning", build_ms=_build_ms,
              models_present=int(getattr(self, "_cpu_snapshot_models", None) is not None))
        return {"phase": "build", "build_ms": _build_ms}

    # ── snap=False: restored CPU container verification ────────────────
    @_modal.enter(snap=False)
    def restore_cpu(self) -> dict[str, Any]:
        # FIRST executable line of the restored Python process.
        _emit(self, "cpu_snapshot_post_restore_enter")
        self._phase = "restore"
        _shadow_init(self)
        models = getattr(self, "_cpu_snapshot_models", None)
        unet = getattr(models, "unet", None) if models is not None else None
        clip = getattr(models, "clip", None) if models is not None else None
        vae = getattr(models, "vae", None) if models is not None else None
        verify: dict[str, Any] = {
            "models_container_present": models is not None,
            "unet_object_present": unet is not None,
            "clip_object_present": clip is not None,
            "vae_object_present": vae is not None,
            "unet_identity": "",
            "clip_identity": "",
            "vae_identity": "",
            "evict_enabled": int(bool(getattr(self, "_cpu_evict_enabled", False))),
            "retain_role": str(getattr(self, "_cpu_retain_role", "none")),
        }
        try:
            _key = getattr(models, "model_key", None) if models is not None else None
            if _key is not None:
                verify["unet_identity"] = str(getattr(_key, "unet_identity", ""))
                verify["clip_identity"] = str(getattr(_key, "clip_identity", ""))
                verify["vae_identity"] = str(getattr(_key, "vae_identity", ""))
        except Exception:  # noqa: BLE001
            pass
        try:
            verify["process_memory_after_restore"] = probe_process_memory()
            verify["model_storage_after_restore"] = probe_model_storage(unet, clip, vae)
            verify["worker_fingerprint"] = probe_worker_fingerprint(cuda_torch=False)
            _restore_fields: dict[str, Any] = {
                "rss_mib": verify["process_memory_after_restore"].get("rss_mib"),
                "pss_mib": verify["process_memory_after_restore"].get("pss_mib"),
                "anonymous_mib": verify["process_memory_after_restore"].get("anonymous_mib"),
                "cgroup_current_mib": verify["process_memory_after_restore"].get("cgroup_current_mib"),
                "total_cpu_model_bytes": verify["model_storage_after_restore"].get(
                    "total_unique_model_bytes", 0
                ),
                "unet_alive": int(unet is not None),
                "clip_alive": int(clip is not None),
                "vae_alive": int(vae is not None),
            }
            emit_stage_line("cpu_snapshot_size", "restored", _restore_fields)
        except Exception:  # noqa: BLE001
            pass
        _emit(self, "cpu_snapshot_post_restore_verify_complete")
        self._cpu_snapshot_restore_verification = verify
        return {"phase": "restore"}

    # ── Request method: restore-only probe ─────────────────────────────
    @_modal.method()
    def run_cpu_snapshot_restore_probe(
        self,
        request_id: str = "",
        submit_wall_unix_ns: int = 0,
    ) -> dict[str, Any]:
        """RESTORE-ONLY probe: verify the restored CPU snapshot state and
        return a tiny JSON result.  No workflow, no CLIP encode, no
        sampling, no VAE decode, no image output.

        T1 (banner → first Python line) is anchored on the
        ``cpu_snapshot_post_restore_enter`` marker from the snap=False
        enter; this method only measures and returns.
        """
        _shadow_init(self)
        entry_wall_ns = int(time.time() * 1_000_000_000)
        _emit(self, "cpu_snapshot_restore_probe_entry", request_id=request_id)
        models = getattr(self, "_cpu_snapshot_models", None)
        unet = getattr(models, "unet", None) if models is not None else None
        clip = getattr(models, "clip", None) if models is not None else None
        vae = getattr(models, "vae", None) if models is not None else None
        verify: dict[str, Any] = {
            "models_container_present": models is not None,
            "unet_object_present": unet is not None,
            "clip_object_present": clip is not None,
            "vae_object_present": vae is not None,
            "unet_identity": "",
            "clip_identity": "",
            "vae_identity": "",
            "evict_enabled": int(bool(getattr(self, "_cpu_evict_enabled", False))),
            "retain_role": str(getattr(self, "_cpu_retain_role", "none")),
        }
        ok = bool(unet is not None and clip is not None and vae is not None)
        try:
            _key = getattr(models, "model_key", None) if models is not None else None
            if _key is not None:
                verify["unet_identity"] = str(getattr(_key, "unet_identity", ""))
                verify["clip_identity"] = str(getattr(_key, "clip_identity", ""))
                verify["vae_identity"] = str(getattr(_key, "vae_identity", ""))
        except Exception:  # noqa: BLE001
            pass
        try:
            import comfy.model_management as _mm
            verify["reference_holders"] = probe_reference_holders(
                self, model_management=_mm,
                bootstrap_state=getattr(self, "bootstrap", None),
            )
        except Exception:  # noqa: BLE001
            verify["reference_holders"] = {"error": "probe_failed"}
        try:
            verify["process_memory"] = probe_process_memory()
            verify["model_storage"] = probe_model_storage(unet, clip, vae)
            verify["worker_fingerprint"] = probe_worker_fingerprint(cuda_torch=False)
        except Exception:  # noqa: BLE001
            pass
        _emit(self, "cpu_snapshot_restore_probe_complete",
              ok=int(ok), request_id=request_id)
        return {
            "phase": getattr(self, "_phase", "unknown"),
            "request_id": request_id,
            "submit_wall_unix_ns": int(submit_wall_unix_ns or 0),
            "entry_wall_unix_ns": entry_wall_ns,
            "verification": verify,
            "build_stages": getattr(self, "_cpu_snapshot_size_stages", {}),
            "build_reference_holders": getattr(self, "_cpu_snapshot_reference_holders", {}),
            "build_fingerprint": getattr(self, "_cpu_snapshot_fingerprint", {}),
            "markers": list(getattr(self, "_gpu_snapshot_markers", [])),
        }


def _prevalidate_graph(
    api: Any,
    workflow: Mapping[str, Any],
    modal_options: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Run ONE production compile + graph validation + certificate pass.

    Mirrors the pre-validation section of ``comfyapp.ComfyAPI._execute_in_process``
    using the same production functions (``compile_production_workflow``,
    ``_build_validation_certificate_identity``, ``execution.validate_prompt``,
    ``_write_validation_certificate``) and seeds the api's in-memory workflow
    execution cache so the first restored request with the same topology hits
    it.  The certificate identity is prompt-bound in the current architecture
    (the compiled workflow retains text inputs), so a different-prompt request
    legitimately rebuilds — this function never bakes request output state.

    Returns a diagnostics dict; never raises.
    """
    out: dict[str, Any] = {"ok": False}
    try:
        import comfyapp as _ca
        from production_workflow import compile_production_workflow

        _t0 = time.perf_counter()
        _production_cache = _ca.normalize_production_options(dict(modal_options or {}))
        _production_enabled = bool(_production_cache.get("enabled", False))
        out["production_enabled"] = int(_production_enabled)
        if not _production_enabled:
            return out
        _compiled, _report = compile_production_workflow(
            dict(workflow),
            _production_cache,
            allow_direct_output_rewrite=True,
            stable=bool(_ca._resolve_runtime_flag("PRODUCTION_STABLE_PATH", "1")),
        )
        out["compile_ms"] = round((time.perf_counter() - _t0) * 1000.0, 3)
        # Dependency identity from the in-memory validation cache (populated
        # by the preflight that ran just before this call).
        _dep_id = _ca._dependency_validation_memory_cache.get("current_hash", "") if _ca._dependency_validation_memory_cache else ""
        if not _dep_id:
            try:
                _dep_fp = _ca.custom_node_dependency_fingerprint(
                    _ca.get_runtime_custom_node_source_root_for_dependency_validation()
                )
                _dep_id = _dep_fp.get("overall_dependency_hash", "")
            except Exception:  # noqa: BLE001
                _dep_id = ""
        _cert_identity, _cert_components = _ca._build_validation_certificate_identity(
            _compiled, _production_cache,
            dependency_identity=_dep_id,
            models_generation=_ca._current_models_generation_id(),
            custom_nodes_identity=_ca._current_custom_nodes_generation_id(),
            return_components=True,
        )
        out["cert_identity"] = _cert_identity
        if not _cert_identity:
            out["reason"] = "cert_identity_unavailable"
            return out
        _wf_cache_key = f"wf_exec:v2:{_cert_identity}"
        import execution as _exec_mod
        _prompt_id = str(hashlib.sha256(_cert_identity.encode("utf-8")).hexdigest()[:16])
        _validate_t0 = time.perf_counter()
        _valid, _error, _outputs, _node_errors = api._event_loop.run_until_complete(
            _exec_mod.validate_prompt(_prompt_id, _compiled, None)
        )
        out["validate_ms"] = round((time.perf_counter() - _validate_t0) * 1000.0, 3)
        if not _valid:
            out["reason"] = f"validation_failed: {str(_error)[:120]}"
            return out
        # Seed the in-memory workflow execution cache (survives the snapshot).
        if not hasattr(api, "_workflow_exec_cache"):
            api._workflow_exec_cache = {}
        api._workflow_exec_cache[_wf_cache_key] = (_outputs, _node_errors)
        out["workflow_cache_seeded"] = True
        # Persist the validation certificate on the runtime-config volume
        # (shared across containers; prompt-bound identity as designed).
        try:
            _cert_components["source_workflow"] = _ca.compute_canonical_source_workflow_hash(dict(workflow))
            _wr = _ca._write_validation_certificate(
                _cert_identity, _outputs, _node_errors,
                identity_components=_cert_components,
                runtime_config_volume=getattr(_ca, "runtime_config_vol", None),
                commit=True,
            )
            out["cert_written"] = bool(_wr and _wr.get("status") in ("written", "exists"))
        except Exception as exc:  # noqa: BLE001
            out["cert_write_error"] = f"{type(exc).__name__}: {str(exc)[:120]}"
        out["ok"] = True
        return out
    except Exception as exc:  # noqa: BLE001
        out["error"] = f"{type(exc).__name__}: {str(exc)[:160]}"
        return out
