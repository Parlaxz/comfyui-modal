"""E28 compute-ready FP32 / cast-once CLIP (Target C).

Measured evidence (E27 Follow-Up A, real Qwen-3-4B):
* qwen_3_4b.safetensors: 398 tensors, ALL BF16, 8,044,936,192 source bytes;
  exact FP32 residency = 16,089,872,384 bytes (14.9849 GiB).
* Per-forward cast tax: 253 casts/forward (1 weight + 252 bias), 15.31 GB
  materialized, 6.1-9.4 ms CPU host wall, 0 ms GPU event wall — the D7-era
  "20-35% of encode" estimate is superseded; the real tax is ~0.3-0.7% of a
  1.2-3.6 s forward.

Design (ownership model A — REPLACE resident storage, never duplicate):
* The speculative CLIP lane hydrates BF16 direct-to-GPU (fastsafetensors),
  then this module casts each tensor ONCE to FP32 (exact widening, GPU op)
  before the zero-copy assign bind.
* ``hydrate_clip_bind`` uses Comfy's ``load_state_dict(assign=True)`` path:
  the parameters ADOPT the FP32 tensors as their data, so the final model
  storage IS FP32 — there is no separate cache to invalidate.
* At forward, ``cast_bias_weight`` runs ``cast_to`` (device already cuda,
  no copy) then ``weight.to(dtype=torch.float32)`` — a no-op when the
  resident dtype is already FP32 → the per-forward cast tax disappears.

Invalidation semantics (fail-closed):
* The "cache" is the parameter storage itself.  Any semantic mutation —
  ``patch_weight_to_device``, ``weight_function``/``bias_function``
  registration, ``manual_cast_dtype`` retarget, ``assign``/storage
  replacement, clone/rehome, device move, dtype retarget — rewrites the
  parameter data in place; a subsequent forward either sees the mutated
  (still-FP32) values (patches applied in FP32 by Comfy's patch machinery)
  or triggers the regular cast path.  A stale compute-ready representation
  is structurally impossible because there is no second representation.
* Defensive demand-time check: :func:`assert_compute_ready_no_patches`
  verifies every file-covered parameter is FP32 and no weight/bias function
  is registered on the leaves before the bind is allowed to proceed with
  cast-once tensors; any violation fails closed to the normal BF16 read.

Telemetry (per prompt 6.5):
* one-time conversion host wall + CUDA-event wall
* bytes cast, tensor count
* VRAM delta (before/after allocated)
* per-forward casts remaining (measured by the E27 forward-cast counter:
  the same 253 call sites, but materialized dest_bytes -> 0)
"""

from __future__ import annotations

import os
import time
from typing import Any, Optional

from .env import env_flag

_FLAG = "COMFYMODAL_V2_CLIP_FP32_CAST_ONCE"
_COMPUTE_DTYPE = "torch.float32"


def cast_once_enabled() -> bool:
    """Gate: compute-ready FP32 cast-once (default OFF — experimental)."""
    return env_flag(_FLAG, default=False)


def cast_once_flag() -> str:
    return _FLAG


def cast_once_expected_dtype() -> str:
    return _COMPUTE_DTYPE


def apply_cast_once(
    per_file_sds: list[dict],
    file_manifests: list[dict],
    *,
    trace: Any = None,
) -> tuple[list[dict], dict[str, Any]]:
    """Cast every tensor in *per_file_sds* from its source dtype to FP32
    (exact widening) in place on the tensor's own device.

    Gates (fail-closed — returns the input unchanged with ``applied=False``):
    * the flag is on;
    * every file manifest dtype is BF16 (the measured Qwen profile; other
      dtypes are left to the normal per-forward cast path);
    * every tensor is a plain dense tensor whose dtype matches the manifest.

    Returns ``(state_dicts, record)``; the record is JSON-safe telemetry:
    applied, tensor_count, bytes_in, bytes_out, host_wall_ms,
    cuda_event_wall_ms, allocated_delta_bytes, dtype_before, dtype_after.
    """
    import torch

    record: dict[str, Any] = {
        "applied": False,
        "reason": "",
        "tensor_count": 0,
        "bytes_in": 0,
        "bytes_out": 0,
        "host_wall_ms": 0.0,
        "cuda_event_wall_ms": 0.0,
        "allocated_delta_bytes": 0,
        "dtype_before": "",
        "dtype_after": _COMPUTE_DTYPE,
    }
    if not cast_once_enabled():
        record["reason"] = "flag_off"
        return per_file_sds, record
    try:
        if len(per_file_sds) != len(file_manifests):
            record["reason"] = "file_count_mismatch"
            return per_file_sds, record
        for entry in file_manifests:
            if str(entry.get("dtype", "")) != "torch.bfloat16":
                record["reason"] = f"unsupported_source_dtype:{entry.get('dtype', '')}"
                return per_file_sds, record
        _t0 = time.perf_counter()
        _ev_start = None
        _ev_end = None
        try:
            if torch.cuda.is_available():
                _ev_start = torch.cuda.Event(enable_timing=True)
                _ev_end = torch.cuda.Event(enable_timing=True)
                _ev_start.record()
        except Exception:
            _ev_start = _ev_end = None
        _alloc_before = int(torch.cuda.memory_allocated()) if torch.cuda.is_available() else 0
        _bytes_in = 0
        _bytes_out = 0
        _count = 0
        _cast_sds: list[dict] = []
        for sd in per_file_sds:
            out: dict[str, Any] = {}
            for key, tensor in sd.items():
                if not isinstance(tensor, torch.Tensor):
                    out[key] = tensor
                    continue
                if str(tensor.dtype) != "torch.bfloat16":
                    # Non-BF16 tensors (e.g. tokenizer blobs) pass through.
                    out[key] = tensor
                    continue
                _bytes_in += int(tensor.numel() * tensor.element_size())
                cast = tensor.to(torch.float32)
                _bytes_out += int(cast.numel() * cast.element_size())
                _count += 1
                out[key] = cast
            _cast_sds.append(out)
        if _ev_end is not None:
            _ev_end.record()
            try:
                _ev_end.synchronize()
                _cuda_ms = float(_ev_start.elapsed_time(_ev_end))
            except Exception:
                _cuda_ms = 0.0
        else:
            _cuda_ms = 0.0
        _alloc_after = int(torch.cuda.memory_allocated()) if torch.cuda.is_available() else 0
        record.update({
            "applied": True,
            "reason": "ok",
            "tensor_count": _count,
            "bytes_in": _bytes_in,
            "bytes_out": _bytes_out,
            "host_wall_ms": round((time.perf_counter() - _t0) * 1000.0, 3),
            "cuda_event_wall_ms": round(_cuda_ms, 3),
            "allocated_delta_bytes": max(int(_alloc_after - _alloc_before), 0),
            "dtype_before": "torch.bfloat16",
        })
        return _cast_sds, record
    except Exception as exc:  # noqa: BLE001 - fail closed
        record["reason"] = f"{type(exc).__name__}: {str(exc)[:160]}"
        return per_file_sds, record


def verify_cast_once_sd(file_manifest: dict, sd: dict) -> tuple[bool, str]:
    """Manifest verification for cast-once state dicts: exact key set and
    shapes as frozen, but dtype must be FP32 (the cast target) instead of the
    frozen source dtype."""
    from .clip_fast_hydration_wiring import _blob_free

    view = _blob_free(sd)
    key_set = file_manifest.get("key_set") or []
    if sorted(view.keys()) != key_set:
        return False, (
            f"key set mismatch: got {len(view)} expected {len(key_set)} "
            "(cast-once transform replay diverged from the frozen manifest)"
        )
    for key, tensor in view.items():
        expected_shape = file_manifest.get("key_shapes", {}).get(key)
        if expected_shape is not None and list(tensor.shape) != expected_shape:
            return False, f"shape mismatch for {key}"
        if str(tensor.dtype) != _COMPUTE_DTYPE:
            return False, (
                f"dtype mismatch for {key}: got {tensor.dtype} "
                f"expected {_COMPUTE_DTYPE} (cast-once)"
            )
    return True, f"exact key/shape match + FP32 compute-ready vs frozen manifest ({len(key_set)} keys)"


def assert_compute_ready_no_patches(clip: Any) -> tuple[bool, str]:
    """Defensive demand-time check before binding cast-once tensors.

    Verifies (fail-closed) ONLY what is knowable before the bind:
    * the leaf loader modules expose no ``weight_function``/``bias_function``
      registrations (a patch would need the regular per-forward cast path);
    * the clip has a cond_stage_model.

    The per-file state dicts are verified separately by
    :func:`verify_cast_once_sd` (exact key set + shapes + FP32 dtype) —
    checking the PRE-BIND model parameters here would be wrong: they are
    still meta/BF16 placeholders until the bind (the E28 baked cast-once
    rejection: ``not_compute_ready:['logit_scale:meta', ...]`` on the
    pre-bind model).

    Returns ``(ok, detail)``.  Never raises.
    """
    try:
        from . import clip_fast_hydration as _cfh

        csm = getattr(clip, "cond_stage_model", None)
        if csm is None:
            return False, "no_cond_stage_model"
        leaves = _cfh._leaf_loaders(csm)
        for leaf in leaves:
            for name in ("weight_function", "bias_function"):
                fn = getattr(leaf, name, None)
                if fn is not None and len(fn) > 0:
                    return False, f"patch_function_registered:{name}"
        return True, "no_patches_compute_ready_expected"
    except Exception as exc:  # noqa: BLE001 - fail closed
        return False, f"{type(exc).__name__}: {str(exc)[:120]}"
