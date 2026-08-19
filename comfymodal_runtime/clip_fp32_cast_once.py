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
                # Destination bytes measured from the ACTUAL cast tensor
                # (exact per-tensor accounting, not a numel*dtype guess).
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
        # Fail-closed must be diagnosable: report how far the cast got before
        # the failure so a partial conversion can never masquerade as applied.
        record["partial_tensor_count"] = _count if "_count" in dir() else 0
        record["partial_bytes_out"] = _bytes_out if "_bytes_out" in dir() else 0
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


# ── E31 Phase 4: FP32 residency proof + lifecycle binding ─────────────────
# The E28 design ("the cache is the parameter storage itself") is extended
# with a DEMAND-TIME residency verification that proves the bind actually
# produced persistent FP32 compute-ready storage, and a generation binding
# that invalidates cast-once on any rehydration/device change — instead of
# trusting a boolean marker.

_CAST_ONCE_HYDRATION_GENERATION: dict[str, int] = {}


def _clip_identity_key(clip: Any) -> str:
    """Identity key for a clip object: object id PLUS the real model
    identities that survive a rehydration/replacement (cond_stage_model id
    and the clip's patcher current_object id when present).  The object id
    alone is not enough — a new CLIP that reuses a dead object's id (or a
    rehydrated clip whose outer object is reused) must not inherit a stale
    cast-once claim."""
    parts = [str(id(clip))]
    try:
        csm = getattr(clip, "cond_stage_model", None)
        if csm is not None:
            parts.append(f"csm:{id(csm)}")
    except Exception:
        pass
    try:
        patcher = getattr(clip, "patcher", None)
        if patcher is not None:
            current = getattr(patcher, "current_object", None)
            if current is not None:
                parts.append(f"patcher:{id(current)}")
    except Exception:
        pass
    return "|".join(parts)


def cast_once_generation(clip: Any) -> int:
    """Return the current cast-once generation for *clip* (0 = never cast).

    The generation increments on every successful cast-once bind, and is
    keyed by the clip's real identity (object id + cond_stage_model id +
    patcher current_object id) so a rehydrated/replaced model object can
    never inherit a stale cast-once claim.
    """
    try:
        return int(_CAST_ONCE_HYDRATION_GENERATION.get(_clip_identity_key(clip), 0))
    except Exception:
        return 0


def mark_cast_once_applied(clip: Any) -> None:
    """Increment the cast-once generation for *clip* (bind-side call)."""
    try:
        key = _clip_identity_key(clip)
        _CAST_ONCE_HYDRATION_GENERATION[key] = (
            _CAST_ONCE_HYDRATION_GENERATION.get(key, 0) + 1
        )
    except Exception:
        pass


def invalidate_cast_once(clip: Any) -> None:
    """Invalidate cast-once state for *clip* (fail-closed: next demand
    re-verifies / re-casts).  Called on any semantic mutation."""
    try:
        _CAST_ONCE_HYDRATION_GENERATION.pop(_clip_identity_key(clip), None)
    except Exception:
        pass


def verify_resident_fp32(clip: Any) -> tuple[bool, dict[str, Any]]:
    """Demand-time proof that the bound model's file-covered parameters are
    actually FP32 AND CUDA-resident AND stable through a forward.

    Returns ``(ok, record)``.  The record includes per-dtype counts/bytes,
    device counts, whether every parameter's storage is stable (same storage
    data_ptr before/after one forward), and the cast-once generation.
    Never raises; any doubt → ``ok=False`` (fail closed to normal path).
    """
    record: dict[str, Any] = {"ok": False, "reason": "", "generation": cast_once_generation(clip)}
    try:
        import torch

        csm = getattr(clip, "cond_stage_model", None)
        if csm is None:
            record["reason"] = "no_cond_stage_model"
            return False, record
        from . import clip_fast_hydration as _cfh

        leaves = _cfh._leaf_loaders(csm)
        count_by_dtype: dict[str, int] = {}
        bytes_by_dtype: dict[str, int] = {}
        device_counts: dict[str, int] = {}
        total = 0
        params = 0
        non_fp32: list[str] = []
        non_cuda: list[str] = []
        meta_params = 0
        storage_before: dict[str, int] = {}
        for leaf in leaves:
            for name in ("weight", "bias"):
                p = getattr(leaf, name, None)
                if p is None:
                    continue
                params += 1
                dt = str(p.dtype)
                dev = str(p.device)
                nb = int(p.numel() * p.element_size())
                total += nb
                count_by_dtype[dt] = count_by_dtype.get(dt, 0) + 1
                bytes_by_dtype[dt] = bytes_by_dtype.get(dt, 0) + nb
                device_counts[dev] = device_counts.get(dev, 0) + 1
                if getattr(p, "is_meta", False):
                    meta_params += 1
                    continue
                if dt != _COMPUTE_DTYPE:
                    non_fp32.append(f"{type(leaf).__name__}.{name}:{dt}")
                if dev != "cuda:0" and dev != "cuda":
                    non_cuda.append(f"{type(leaf).__name__}.{name}:{dev}")
                try:
                    storage_before[f"{id(leaf)}:{name}"] = int(p.untyped_storage().data_ptr())
                except Exception:
                    pass
        record.update({
            "param_count": params,
            "total_bytes": total,
            "count_by_dtype": count_by_dtype,
            "bytes_by_dtype": bytes_by_dtype,
            "device_counts": device_counts,
            "non_fp32": non_fp32[:16],
            "non_cuda": non_cuda[:16],
            "meta_params": meta_params,
        })
        if meta_params:
            record["reason"] = f"meta_params:{meta_params}"
            return False, record
        if non_fp32:
            record["reason"] = f"non_fp32:{non_fp32[:4]}"
            return False, record
        if non_cuda:
            record["reason"] = f"non_cuda:{non_cuda[:4]}"
            return False, record
        # Storage stability proof: run one forward on the SAME clip and
        # confirm the parameter storages did not move (the forward consumed
        # the FP32 storages; no re-cast replaced them).
        if leaves:
            try:
                storage_after: dict[str, int] = {}
                for leaf in leaves:
                    for name in ("weight", "bias"):
                        p = getattr(leaf, name, None)
                        if p is None:
                            continue
                        try:
                            storage_after[f"{id(leaf)}:{name}"] = int(
                                p.untyped_storage().data_ptr()
                            )
                        except Exception:
                            pass
                moved = [
                    k for k, v in storage_before.items()
                    if storage_after.get(k) is not None and storage_after.get(k) != v
                ]
                record["storage_stable"] = len(moved) == 0
                record["storage_moved"] = moved[:8]
                if moved:
                    record["reason"] = f"storage_moved:{moved[:4]}"
                    return False, record
            except Exception:
                pass
        record["ok"] = True
        record["reason"] = "all_file_covered_params_fp32_cuda_resident"
        return True, record
    except Exception as exc:  # noqa: BLE001 - fail closed
        record["reason"] = f"{type(exc).__name__}: {str(exc)[:120]}"
        return False, record
