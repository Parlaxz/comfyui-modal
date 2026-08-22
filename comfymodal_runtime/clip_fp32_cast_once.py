"""E28 compute-ready FP32 / cast-once CLIP (Target C).

Measured evidence (E27 Follow-Up A, real Qwen-3-4B):
* qwen_3_4b.safetensors: 398 tensors, ALL BF16, 8,044,936,192 source bytes;
  exact FP32 residency = 16,089,872,384 bytes (14.9849 GiB).
* Relevant Linear weights: approximately 252 tensors/forward and approximately
  14.53 GB of conversion traffic.  This replaces the stale 253/15.31 GB
  estimate; no synchronized conversion time is claimed here.

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
import functools
from typing import Any, Optional

import torch

from .env import env_flag

_FLAG = "COMFYMODAL_V2_CLIP_FP32_CAST_ONCE"
_COMPUTE_DTYPE = "torch.float32"
_SOURCE_DTYPE = "torch.bfloat16"
_CAST_PROVENANCE_ATTR = "_comfymodal_cast_once_provenance"


class _CastOnceStateDict(dict):
    """A state dict carrying non-optional cast-once source provenance.

    The attribute is deliberately attached to the transformed mapping rather
    than hidden in a process-global table: speculative and demand paths can
    pass the mapping through independently while verification still refuses a
    plain, arbitrary FP32 mapping.
    """

    pass


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
        "requested": bool(cast_once_enabled()),
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
            if str(entry.get("dtype", "")) != _SOURCE_DTYPE:
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
        for local_file_index, (sd, manifest) in enumerate(zip(per_file_sds, file_manifests)):
            # ``apply_cast_once`` is also called once per file by the normal
            # demand fallback.  The local enumerate value is therefore not
            # provenance: preserve the accepted manifest/global index so a
            # second checkpoint file cannot be silently relabelled as file 0.
            file_index = int(manifest.get("file_index", local_file_index))
            manifest_keys = [str(key) for key in (manifest.get("key_set") or [])]
            expected_keys = {
                key for key in (manifest_keys or [str(key) for key in sd])
                if key not in _TOKENIZER_KEYS
            }
            actual_keys = {
                str(key) for key in sd if str(key) not in _TOKENIZER_KEYS
            }
            if actual_keys != expected_keys:
                record["reason"] = (
                    f"source_key_set_mismatch:{file_index}:"
                    f"unexpected={len(actual_keys - expected_keys)} "
                    f"missing={len(expected_keys - actual_keys)}"
                )
                return per_file_sds, record
            source_dtypes: dict[str, str] = {}
            source_shapes: dict[str, list[int]] = {}
            for key in sorted(expected_keys):
                tensor = sd.get(key)
                if not isinstance(tensor, torch.Tensor):
                    record["reason"] = f"missing_or_non_tensor_source:{file_index}:{key}"
                    return per_file_sds, record
                actual_dtype = str(tensor.dtype)
                expected_dtype = str(manifest.get("dtype", ""))
                if actual_dtype != expected_dtype or actual_dtype != _SOURCE_DTYPE:
                    record["reason"] = (
                        f"source_dtype_mismatch:{file_index}:{key}:"
                        f"got {actual_dtype} expected {expected_dtype}"
                    )
                    return per_file_sds, record
                expected_shape = (manifest.get("key_shapes") or {}).get(key)
                if expected_shape is not None and list(tensor.shape) != list(expected_shape):
                    record["reason"] = f"source_shape_mismatch:{file_index}:{key}"
                    return per_file_sds, record
                source_dtypes[key] = actual_dtype
                source_shapes[key] = list(tensor.shape)
            out: _CastOnceStateDict = _CastOnceStateDict()
            for key, tensor in sd.items():
                if not isinstance(tensor, torch.Tensor):
                    out[key] = tensor
                    continue
                if str(tensor.dtype) != _SOURCE_DTYPE:
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
            setattr(out, _CAST_PROVENANCE_ATTR, {
                "schema": 1,
                "source_dtype": _SOURCE_DTYPE,
                "source_dtype_by_key": source_dtypes,
                "source_shapes": source_shapes,
                "manifest_key_set": sorted(expected_keys),
                "file_index": file_index,
            })
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
            "source_dtype": _SOURCE_DTYPE,
            "source_provenance_files": len(_cast_sds),
            "source_provenance": [
                dict(getattr(item, _CAST_PROVENANCE_ATTR, {}) or {})
                for item in _cast_sds
            ],
            "per_file": [
                {
                    "file_index": int((file_manifests[index] or {}).get("file_index", index)),
                    "requested": True,
                    "applied": True,
                    "tensor_count": sum(
                        1 for tensor in item.values()
                        if isinstance(tensor, torch.Tensor)
                        and str(tensor.dtype) == _COMPUTE_DTYPE
                    ),
                    "bytes_out": sum(
                        int(tensor.numel() * tensor.element_size())
                        for tensor in item.values()
                        if isinstance(tensor, torch.Tensor)
                        and str(tensor.dtype) == _COMPUTE_DTYPE
                    ),
                }
                for index, item in enumerate(_cast_sds)
            ],
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

    if str(file_manifest.get("dtype", "")) != _SOURCE_DTYPE:
        return False, (
            "manifest source provenance mismatch: cast-once requires "
            f"{_SOURCE_DTYPE}, got {file_manifest.get('dtype', '')}"
        )
    provenance = getattr(sd, _CAST_PROVENANCE_ATTR, None)
    if not isinstance(provenance, dict):
        return False, "missing cast-once source provenance evidence"
    expected_source_keys = sorted(
        str(key) for key in (file_manifest.get("key_set") or [])
        if str(key) not in _TOKENIZER_KEYS
    )
    if provenance.get("source_dtype") != _SOURCE_DTYPE:
        return False, "source provenance dtype is not manifest BF16"
    manifest_file_index = file_manifest.get("file_index")
    if manifest_file_index is not None and provenance.get("file_index") != int(manifest_file_index):
        return False, "source provenance file index mismatch"
    if sorted(provenance.get("manifest_key_set") or []) != expected_source_keys:
        return False, "source provenance key set mismatch"
    source_dtypes = provenance.get("source_dtype_by_key")
    if not isinstance(source_dtypes, dict) or any(
        source_dtypes.get(key) != _SOURCE_DTYPE for key in expected_source_keys
    ):
        return False, "incomplete per-key BF16 source provenance"
    source_shapes = provenance.get("source_shapes")
    expected_shapes = file_manifest.get("key_shapes") or {}
    if not isinstance(source_shapes, dict) or any(
        list(source_shapes.get(key) or []) != list(expected_shapes.get(key) or [])
        for key in expected_source_keys
    ):
        return False, "incomplete source shape provenance"
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


def _storage_ptr(tensor: Any) -> Optional[int]:
    try:
        return int(tensor.untyped_storage().data_ptr())
    except Exception:
        return None


def _tensor_bytes_equal(left: Any, right: Any) -> bool:
    """Compare the actual bytes, including NaN payloads, not just values."""
    try:
        if left.shape != right.shape or left.dtype != right.dtype:
            return False
        if str(left.device) != str(right.device):
            return False
        a = left.detach().contiguous().view(torch.uint8)
        b = right.detach().contiguous().view(torch.uint8)
        return bool(torch.equal(a, b))
    except Exception:
        return False


def _manifest_key_map(file_manifests: list[dict]) -> tuple[dict[str, dict], list[str]]:
    """Return the frozen checkpoint-key map and duplicate manifest keys."""
    expected: dict[str, dict] = {}
    duplicate: list[str] = []
    for file_index, manifest in enumerate(file_manifests):
        keys = manifest.get("key_set") or []
        for key in keys:
            key = str(key)
            if key in expected:
                duplicate.append(key)
                continue
            expected[key] = {
                "file_index": int(file_index),
                "shape": list((manifest.get("key_shapes") or {}).get(key, [])),
                "source_dtype": str(manifest.get("dtype", "")),
            }
    return expected, sorted(set(duplicate))


def _declared_structural_destination_keys(file_manifests: list[dict]) -> set[str]:
    """Return destination-only keys explicitly frozen in the manifest.

    These are model-created structural parameters (for example
    ``logit_scale``), not checkpoint tensors.  They may be present in the
    destination map without a source occurrence, but only when the frozen
    manifest declares them.  An undeclared destination remains an exact
    mapping failure.
    """
    declared: set[str] = set()
    for manifest in file_manifests:
        raw = (manifest or {}).get("structural_destination_keys", ())
        if isinstance(raw, str):
            raw = (raw,)
        if isinstance(raw, (list, tuple, set, frozenset)):
            declared.update(str(key) for key in raw)
    return declared


def snapshot_resident_fp32(
    clip: Any,
    per_file_sds: list[dict],
    file_manifests: list[dict],
    *,
    expect_device: Optional[str] = None,
    phase: str = "snapshot",
) -> dict[str, Any]:
    """Make an exact checkpoint-key -> destination residency proof.

    The frozen manifest defines the expected checkpoint universe.  Source
    tensors are compared to the destination reached through Comfy's shared
    ``_leaf_param_map`` logic, rather than by walking ``weight``/``bias``
    attributes (which misses nested and routed parameters).  Every mismatch is
    represented in JSON-safe evidence and the proof fails closed.
    """
    record: dict[str, Any] = {
        "ok": False,
        "phase": str(phase),
        "reason": "",
        "generation": cast_once_generation(clip),
        "expected_count": 0,
        "source_count": 0,
        "destination_count": 0,
        "matched_count": 0,
        "verified_count": 0,
        "missing_count": 0,
        "duplicate_count": 0,
        "unexpected_count": 0,
        "shape_mismatch_count": 0,
        "dtype_mismatch_count": 0,
        "device_mismatch_count": 0,
        "meta_count": 0,
        "storage_mismatch_count": 0,
        "byte_mismatch_count": 0,
        "expected_bytes": 0,
        "verified_bytes": 0,
        "source_bytes": 0,
        "destination_bytes": 0,
        "fp32_bytes": 0,
        "count_by_dtype": {},
        "bytes_by_dtype": {},
        "device_counts": {},
        "missing_keys": [],
        "missing_source_keys": [],
        "missing_destination_keys": [],
        "structural_destination_keys": [],
        "duplicate_keys": [],
        "unexpected_keys": [],
        "wrong_dtype_keys": [],
        "wrong_device_keys": [],
        "wrong_storage_keys": [],
        "wrong_bytes_keys": [],
        "wrong_meta_keys": [],
        "file_index_mismatch_keys": [],
        "wrong_dtype_count": 0,
        "wrong_device_count": 0,
        "wrong_storage_count": 0,
        "wrong_bytes_count": 0,
        "per_file": [],
        "per_key": [],
    }
    try:
        from . import clip_fast_hydration as _cfh

        expected, manifest_duplicates = _manifest_key_map(file_manifests)
        record["expected_count"] = len(expected)
        record["duplicate_keys"] = list(manifest_duplicates)
        record["duplicate_count"] = len(manifest_duplicates)
        if not expected:
            record["reason"] = "zero_expected_count"
            return record
        if len(per_file_sds) != len(file_manifests):
            record["reason"] = "file_count_mismatch"
            return record

        # Keep the file index attached to every source occurrence.  A flat
        # key->tensor mapping loses which checkpoint file supplied a key and
        # can incorrectly turn a swapped/multiply-present file into proof.
        source_entries: dict[str, list[dict[str, Any]]] = {}
        source_entry_count = 0
        duplicate_source: list[str] = []
        for source_file_index, sd in enumerate(per_file_sds):
            for key, tensor in sd.items():
                if key in _TOKENIZER_KEYS:
                    continue
                key = str(key)
                source_entries.setdefault(key, []).append({
                    "file_index": int(source_file_index),
                    "tensor": tensor,
                })
                source_entry_count += 1
                if len(source_entries[key]) > 1:
                    duplicate_source.append(key)
        duplicate_source = sorted(set(duplicate_source))
        record["duplicate_keys"] = sorted(set(record["duplicate_keys"]) | set(duplicate_source))
        record["duplicate_count"] = len(set(record["duplicate_keys"]))
        record["source_count"] = len(source_entries)
        record["source_entry_count"] = source_entry_count
        unexpected = sorted(set(source_entries) - set(expected))
        missing_source = sorted(set(expected) - set(source_entries))
        record["missing_source_keys"] = list(missing_source)
        # Destination missingness is reconciled below, after the destination
        # map is collected.  ``missing_keys`` is the union of both sides.
        missing = list(missing_source)
        record["unexpected_keys"] = list(unexpected)
        record["unexpected_count"] = len(unexpected)

        csm = getattr(clip, "cond_stage_model", None)
        if csm is None:
            record["reason"] = "no_cond_stage_model"
            return record
        destination: dict[str, Any] = {}
        destination_all: list[tuple[str, Any]] = []
        destination_duplicates: list[str] = []
        destination_ids: dict[int, str] = {}
        for leaf in _cfh._leaf_loaders(csm):
            for key, tensor in _cfh._leaf_param_map(leaf).items():
                destination_all.append((str(key), tensor))
                if key not in expected:
                    continue
                previous = destination.get(key)
                if previous is not None and previous is not tensor:
                    destination_duplicates.append(str(key))
                    continue
                tensor_id = id(tensor)
                other_key = destination_ids.get(tensor_id)
                if other_key is not None and other_key != key:
                    destination_duplicates.extend((other_key, str(key)))
                destination_ids[tensor_id] = str(key)
                destination[str(key)] = tensor
        destination_duplicates = sorted(set(destination_duplicates))
        record["duplicate_keys"] = sorted(set(record["duplicate_keys"]) | set(destination_duplicates))
        record["duplicate_count"] = len(set(record["duplicate_keys"]))
        record["destination_count"] = len(destination)

        expected_destination_ids = {id(tensor) for tensor in destination.values()}
        structural_destination_keys = _declared_structural_destination_keys(file_manifests)
        record["structural_destination_keys"] = sorted(structural_destination_keys)
        unexpected_destination = sorted({
            key for key, tensor in destination_all
            if (
                key not in expected
                and key not in structural_destination_keys
                and id(tensor) not in expected_destination_ids
            )
        })
        record["unexpected_destination_keys"] = list(unexpected_destination)
        unexpected = sorted(set(unexpected) | set(unexpected_destination))
        record["unexpected_keys"] = list(unexpected)
        record["unexpected_count"] = len(unexpected)

        missing_destination = sorted(set(expected) - set(destination))
        record["missing_destination_keys"] = list(missing_destination)
        missing = sorted(set(missing_source) | set(missing_destination))
        record["missing_keys"] = list(missing)
        record["missing_count"] = len(missing)

        for file_index, manifest in enumerate(file_manifests):
            file_keys = {
                str(key) for key in (manifest.get("key_set") or [])
                if str(key) not in _TOKENIZER_KEYS
            }
            expected_bytes = 0
            for key in file_keys:
                shape = (manifest.get("key_shapes") or {}).get(key) or []
                numel = 1
                for dim in shape:
                    numel *= int(dim)
                expected_bytes += numel * 4
            record["per_file"].append({
                "file_index": int(file_index),
                "path": str(manifest.get("path", "")),
                "expected_count": len(file_keys),
                "source_count": 0,
                "destination_count": 0,
                "verified_count": 0,
                "expected_bytes": expected_bytes,
                "source_bytes": 0,
                "destination_bytes": 0,
                "verified_bytes": 0,
                "missing_keys": [],
                "duplicate_keys": [],
                "unexpected_keys": [],
                "wrong_dtype_keys": [],
                "wrong_device_keys": [],
                "wrong_storage_keys": [],
                "wrong_bytes_keys": [],
                "wrong_meta_keys": [],
                "missing_count": 0,
                "duplicate_count": 0,
                "unexpected_count": 0,
                "shape_mismatch_count": 0,
                "dtype_mismatch_count": 0,
                "device_mismatch_count": 0,
                "meta_count": 0,
                "storage_mismatch_count": 0,
                "byte_mismatch_count": 0,
                "file_index_mismatch_count": 0,
            })
            record["expected_bytes"] += expected_bytes

        # Reconcile physical source residency by the actual source file index,
        # including unexpected and duplicate occurrences.  The expected-key
        # loop below deliberately never flattens this association.
        for source_key, occurrences in source_entries.items():
            for occurrence in occurrences:
                source_file_index = int(occurrence.get("file_index", -1))
                source_tensor = occurrence.get("tensor")
                source_bytes = (
                    int(source_tensor.numel() * source_tensor.element_size())
                    if isinstance(source_tensor, torch.Tensor) else 0
                )
                record["source_bytes"] += source_bytes
                if 0 <= source_file_index < len(record["per_file"]):
                    record["per_file"][source_file_index]["source_count"] += 1
                    record["per_file"][source_file_index]["source_bytes"] += source_bytes

        for key in unexpected:
            for occurrence in source_entries.get(key, []):
                source_file_index = int(occurrence.get("file_index", -1))
                if 0 <= source_file_index < len(record["per_file"]):
                    record["per_file"][source_file_index]["unexpected_keys"].append(key)
                    record["per_file"][source_file_index]["unexpected_count"] += 1

        for key in sorted(expected):
            occurrences = source_entries.get(key, [])
            source_entry = occurrences[0] if occurrences else None
            src = source_entry.get("tensor") if source_entry else None
            dst = destination.get(key)
            spec = expected[key]
            manifest_file_index = int(spec.get("file_index", -1))
            source_file_index = (
                int(source_entry.get("file_index")) if source_entry is not None else None
            )
            ev: dict[str, Any] = {
                "key": key,
                "file_index": manifest_file_index,
                "manifest_file_index": manifest_file_index,
                "source_file_index": source_file_index,
                "present_source": src is not None,
                "present_destination": dst is not None,
            }
            file_record = (
                record["per_file"][manifest_file_index]
                if 0 <= manifest_file_index < len(record["per_file"])
                else None
            )
            if file_record is not None and (not occurrences or dst is None):
                file_record["missing_keys"].append(key)
                file_record["missing_count"] += 1
            if file_record is not None and len(occurrences) > 1:
                file_record["duplicate_keys"].append(key)
                file_record["duplicate_count"] += 1
            src_bytes = int(src.numel() * src.element_size()) if isinstance(src, torch.Tensor) else 0
            if dst is not None:
                dst_bytes = int(dst.numel() * dst.element_size())
                record["destination_bytes"] += dst_bytes
                if file_record is not None:
                    file_record["destination_count"] += 1
                    file_record["destination_bytes"] += dst_bytes
            if src is None or dst is None:
                if src is not None:
                    ev.update({
                        "shape": list(getattr(src, "shape", ())),
                        "expected_shape": list(spec.get("shape") or []),
                        "source_dtype": str(getattr(src, "dtype", "")),
                        "source_device": str(getattr(src, "device", "")),
                        "source_is_meta": bool(getattr(src, "is_meta", False)),
                        "source_bytes": src_bytes,
                    })
                record["per_key"].append(ev)
                continue
            ev.update({
                "shape": list(getattr(src, "shape", ())),
                "expected_shape": list(spec.get("shape") or []),
                "source_dtype": str(getattr(src, "dtype", "")),
                "destination_dtype": str(getattr(dst, "dtype", "")),
                "source_device": str(getattr(src, "device", "")),
                "destination_device": str(getattr(dst, "device", "")),
                "source_is_meta": bool(getattr(src, "is_meta", False)),
                "destination_is_meta": bool(getattr(dst, "is_meta", False)),
                "source_bytes": src_bytes,
                "destination_bytes": int(dst.numel() * dst.element_size()),
                "source_data_ptr": None if getattr(src, "is_meta", False) else int(src.data_ptr()),
                "destination_data_ptr": None if getattr(dst, "is_meta", False) else int(dst.data_ptr()),
                "source_storage_ptr": _storage_ptr(src),
                "destination_storage_ptr": _storage_ptr(dst),
            })
            if str(dst.dtype) == _COMPUTE_DTYPE:
                record["fp32_bytes"] += int(dst.numel() * dst.element_size())
            dt = str(dst.dtype)
            record["count_by_dtype"][dt] = record["count_by_dtype"].get(dt, 0) + 1
            record["bytes_by_dtype"][dt] = record["bytes_by_dtype"].get(dt, 0) + int(dst.numel() * dst.element_size())
            dev = str(getattr(dst, "device", ""))
            record["device_counts"][dev] = record["device_counts"].get(dev, 0) + 1
            shape_ok = list(dst.shape) == list(spec.get("shape") or []) and list(src.shape) == list(spec.get("shape") or [])
            dtype_ok = str(src.dtype) == _COMPUTE_DTYPE and str(dst.dtype) == _COMPUTE_DTYPE
            device_ok = not expect_device or str(dst.device) == str(expect_device)
            meta_ok = not bool(getattr(src, "is_meta", False)) and not bool(getattr(dst, "is_meta", False))
            storage_ok = _storage_ptr(src) is not None and _storage_ptr(src) == _storage_ptr(dst) and int(src.data_ptr()) == int(dst.data_ptr())
            bytes_ok = _tensor_bytes_equal(src, dst)
            file_index_ok = source_file_index == manifest_file_index
            ev.update({"shape_ok": shape_ok, "dtype_ok": dtype_ok, "device_ok": device_ok, "meta_ok": meta_ok, "storage_ok": storage_ok, "bytes_ok": bytes_ok, "file_index_ok": file_index_ok, "matched": bool(shape_ok and dtype_ok and device_ok and meta_ok and storage_ok and bytes_ok and file_index_ok)})
            for flag, name in ((not shape_ok, "shape_mismatch_count"), (not dtype_ok, "dtype_mismatch_count"), (not device_ok, "device_mismatch_count"), (not meta_ok, "meta_count"), (not storage_ok, "storage_mismatch_count"), (not bytes_ok, "byte_mismatch_count")):
                if flag:
                    record[name] += 1
                    if file_record is not None:
                        file_record[name] += 1
            if not dtype_ok:
                record["wrong_dtype_keys"].append(key)
                if file_record is not None:
                    file_record["wrong_dtype_keys"].append(key)
            if not device_ok:
                record["wrong_device_keys"].append(key)
                if file_record is not None:
                    file_record["wrong_device_keys"].append(key)
            if not meta_ok:
                record["wrong_meta_keys"].append(key)
                if file_record is not None:
                    file_record["wrong_meta_keys"].append(key)
            if not storage_ok:
                record["wrong_storage_keys"].append(key)
                if file_record is not None:
                    file_record["wrong_storage_keys"].append(key)
            if not bytes_ok:
                record["wrong_bytes_keys"].append(key)
                if file_record is not None:
                    file_record["wrong_bytes_keys"].append(key)
            if not file_index_ok:
                record["file_index_mismatch_keys"].append(key)
                if file_record is not None:
                    file_record["file_index_mismatch_count"] += 1
            if ev["matched"]:
                record["matched_count"] += 1
                record["verified_count"] += 1
                verified_bytes = int(dst.numel() * dst.element_size())
                record["verified_bytes"] += verified_bytes
                if file_record is not None:
                    file_record["verified_count"] += 1
                    file_record["verified_bytes"] += verified_bytes
            record["per_key"].append(ev)

        record["wrong_dtype_keys"] = sorted(set(record["wrong_dtype_keys"]))
        record["wrong_device_keys"] = sorted(set(record["wrong_device_keys"]))
        record["wrong_storage_keys"] = sorted(set(record["wrong_storage_keys"]))
        record["wrong_bytes_keys"] = sorted(set(record["wrong_bytes_keys"]))
        record["wrong_meta_keys"] = sorted(set(record["wrong_meta_keys"]))
        record["file_index_mismatch_keys"] = sorted(set(record["file_index_mismatch_keys"]))
        record["wrong_dtype_count"] = int(record["dtype_mismatch_count"])
        record["wrong_device_count"] = int(record["device_mismatch_count"])
        record["wrong_storage_count"] = int(record["storage_mismatch_count"])
        record["wrong_bytes_count"] = int(record["byte_mismatch_count"])
        record["verified_bytes"] = int(record["verified_bytes"])
        record["verified_count"] = int(record["verified_count"])

        failures = [
            name for name in ("duplicate_count", "missing_count", "unexpected_count", "shape_mismatch_count", "dtype_mismatch_count", "device_mismatch_count", "meta_count", "storage_mismatch_count", "byte_mismatch_count") if int(record[name])
        ]
        if record["file_index_mismatch_keys"]:
            failures.append("file_index_mismatch")
        if record["matched_count"] != record["expected_count"] or record["verified_count"] != record["expected_count"]:
            failures.append("matched_count")
        if record["verified_bytes"] != record["expected_bytes"]:
            failures.append("verified_bytes")
        if failures:
            record["reason"] = "exact_mapping_failed:" + ",".join(failures)
            return record
        record["ok"] = True
        record["reason"] = "exact_checkpoint_mapping_fp32_resident"
        return record
    except Exception as exc:  # noqa: BLE001 - fail closed
        record["reason"] = f"{type(exc).__name__}: {str(exc)[:160]}"
        return record


_TOKENIZER_KEYS = {"spiece_model", "tekken_model", "tokenizer_json"}


def compare_resident_fp32(before: dict[str, Any], after: dict[str, Any]) -> tuple[bool, dict[str, Any]]:
    """Compare the complete residency identity after the real forward.

    Pointer stability is necessary but not sufficient: a forward that swaps a
    key, changes its file association, dtype/device/meta state, generation, or
    byte accounting must fail closed even when an unrelated pointer happens to
    remain unchanged.
    """
    result: dict[str, Any] = {
        "ok": False,
        "reason": "",
        "storage_stable": False,
        "key_set_stable": False,
        "metadata_stable": False,
        "generation_stable": False,
        "storage_moved": [],
        "changed_keys": [],
        "before_generation": int(before.get("generation", 0) or 0),
        "after_generation": int(after.get("generation", 0) or 0),
        "before_count": int(before.get("expected_count", 0) or 0),
        "after_count": int(after.get("expected_count", 0) or 0),
    }
    try:
        result["generation_stable"] = result["before_generation"] == result["after_generation"]
        before_keys = {str(e.get("key")): e for e in before.get("per_key", []) if isinstance(e, dict) and e.get("key") is not None}
        after_keys = {str(e.get("key")): e for e in after.get("per_key", []) if isinstance(e, dict) and e.get("key") is not None}
        result["key_set_stable"] = set(before_keys) == set(after_keys)
        changed: list[str] = []
        moved = []
        for key in sorted(set(before_keys) | set(after_keys)):
            left, right = before_keys.get(key), after_keys.get(key)
            if not left or not right:
                changed.append(str(key))
                moved.append(str(key))
                continue
            if left.get("destination_storage_ptr") != right.get("destination_storage_ptr") or left.get("destination_data_ptr") != right.get("destination_data_ptr"):
                moved.append(str(key))
            metadata_fields = (
                "manifest_file_index", "file_index", "source_file_index", "shape",
                "expected_shape", "source_dtype", "destination_dtype",
                "source_device", "destination_device", "source_is_meta",
                "destination_is_meta", "source_bytes", "destination_bytes",
                "dtype_ok", "device_ok", "meta_ok", "shape_ok",
            )
            if any(left.get(field) != right.get(field) for field in metadata_fields):
                changed.append(str(key))
        result["storage_moved"] = moved[:32]
        result["storage_stable"] = not moved
        result["changed_keys"] = sorted(set(changed))[:32]
        result["metadata_stable"] = not changed and result["key_set_stable"]
        counts_stable = (
            result["before_count"] == result["after_count"]
            and int(before.get("verified_count", before.get("matched_count", 0)) or 0)
            == int(after.get("verified_count", after.get("matched_count", 0)) or 0)
            and int(before.get("expected_bytes", 0) or 0) == int(after.get("expected_bytes", 0) or 0)
            and int(before.get("verified_bytes", before.get("destination_bytes", 0)) or 0)
            == int(after.get("verified_bytes", after.get("destination_bytes", 0)) or 0)
        )
        if not after.get("ok"):
            result["reason"] = "post_forward_exact_mapping_failed"
            return False, result
        if not result["generation_stable"]:
            result["reason"] = "generation_changed_after_real_forward"
            return False, result
        if not result["key_set_stable"]:
            result["reason"] = "key_set_changed_after_real_forward"
            return False, result
        if not result["metadata_stable"] or not counts_stable:
            result["reason"] = "residency_metadata_changed_after_real_forward"
            return False, result
        if moved:
            result["reason"] = "storage_moved_after_real_forward"
            return False, result
        result["ok"] = True
        result["reason"] = "exact_mapping_stable_after_real_forward"
        return True, result
    except Exception as exc:  # noqa: BLE001 - fail closed
        result["reason"] = f"{type(exc).__name__}: {str(exc)[:160]}"
        return False, result


def verify_resident_fp32(
    clip: Any,
    per_file_sds: Optional[list[dict]] = None,
    file_manifests: Optional[list[dict]] = None,
    *,
    expect_device: Optional[str] = None,
    phase: str = "post_bind",
) -> tuple[bool, dict[str, Any]]:
    """Exact residency proof; absent checkpoint evidence fails closed.

    The legacy no-source call remains diagnostic for offline callers, but it
    cannot pass: a residency claim without a frozen checkpoint mapping is not
    proof.  This is deliberately never a best-effort parameter walk.
    """
    if per_file_sds is None or file_manifests is None:
        record: dict[str, Any] = {"ok": False, "reason": "missing_checkpoint_mapping", "generation": cast_once_generation(clip)}
        try:
            csm = getattr(clip, "cond_stage_model", None)
            non_fp32 = []
            if csm is not None:
                for leaf in getattr(csm, "modules", lambda: ())():
                    for name in ("weight", "bias"):
                        p = getattr(leaf, name, None)
                        if p is not None and str(getattr(p, "dtype", "")) != _COMPUTE_DTYPE:
                            non_fp32.append(f"{type(leaf).__name__}.{name}:{p.dtype}")
            if non_fp32:
                record["reason"] = f"non_fp32:{non_fp32[:4]}"
        except Exception:
            pass
        return False, record
    record = snapshot_resident_fp32(clip, per_file_sds, file_manifests, expect_device=expect_device, phase=phase)
    return bool(record.get("ok", False)), record


def install_real_forward_check(clip: Any, callback: Any) -> dict[str, Any]:
    """Wrap the existing CLIP encode boundary, without issuing a forward.

    The callback runs once, after the real encode method returns.  It may raise
    to fail the E31 request.  CPU fakes can provide any of the normal Comfy
    ``encode_from_tokens*`` methods; no CUDA APIs are used here.
    """
    marker = "_comfymodal_e31_real_forward_hook"

    def _public_state(value: dict[str, Any]) -> dict[str, Any]:
        """Return JSON-safe evidence while keeping restoration state private."""
        public = {key: item for key, item in value.items() if key != "originals"}
        public["originals"] = {
            str(name): {
                "callable_id": str(id(original)),
                "module": str(getattr(original, "__module__", "")),
                "qualname": str(getattr(original, "__qualname__", getattr(original, "__name__", ""))),
            }
            for name, original in (value.get("originals") or {}).items()
        }
        return public

    identity = _clip_identity_key(clip)
    generation = cast_once_generation(clip)
    existing = getattr(clip, marker, None)
    if isinstance(existing, dict):
        if existing.get("identity") == identity and int(existing.get("generation", 0) or 0) == generation:
            return _public_state(existing)
        # Restore methods wrapped by the obsolete generation before dropping
        # its state.  Otherwise a reused outer CLIP would retain a closure
        # over the old callback even though the marker was deleted.
        for method_name, original in (existing.get("originals") or {}).items():
            try:
                setattr(clip, method_name, original)
            except Exception:
                pass
        try:
            delattr(clip, marker)
        except Exception:
            pass
    methods = ("encode_from_tokens_scheduled", "encode_from_tokens", "encode_token_weights")
    installed: list[str] = []
    state = {"observed": False, "originals": {}}
    for method_name in methods:
        original = getattr(clip, method_name, None)
        if not callable(original) or getattr(original, marker, False):
            continue

        @functools.wraps(original)
        def _wrapped(*args: Any, _original: Any = original, _name: str = method_name, **kwargs: Any) -> Any:
            started = time.perf_counter()
            result = _original(*args, **kwargs)
            if not state["observed"]:
                state["observed"] = True
                observation = {
                    "forward_observed": True,
                    "forward_actually_observed": True,
                    "forward_method": _name,
                    "forward_wall_ms": round((time.perf_counter() - started) * 1000.0, 3),
                }
                callback(observation)
            return result

        setattr(_wrapped, marker, True)
        setattr(clip, method_name, _wrapped)
        state["originals"][method_name] = original
        installed.append(method_name)
    result = {
        "installed": bool(installed),
        "methods": installed,
        "forward_observed": False,
        "forward_actually_observed": False,
        "identity": identity,
        "generation": generation,
        "originals": dict(state["originals"]),
    }
    setattr(clip, marker, result)
    return _public_state(result)


def clear_real_forward_check(clip: Any) -> None:
    """Remove a stale offline forward wrapper and its callback closure."""
    marker = "_comfymodal_e31_real_forward_hook"
    try:
        existing = getattr(clip, marker, None)
        if isinstance(existing, dict):
            for method_name, original in (existing.get("originals") or {}).items():
                try:
                    setattr(clip, method_name, original)
                except Exception:
                    pass
        if hasattr(clip, marker):
            delattr(clip, marker)
    except Exception:
        pass
