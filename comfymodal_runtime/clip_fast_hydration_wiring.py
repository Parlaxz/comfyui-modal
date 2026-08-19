"""D3 production wiring: default-OFF generic CLIP fast hydration + snapshot
weight exclusion for first-cold ComfyUI safetensors text encoders.

Two independent default-off flags:

* ``COMFYMODAL_V2_CLIP_FAST_HYDRATION=1`` (Path A) — hydrate eligible text
  encoders from their source safetensors via fastsafetensors direct CUDA +
  capability-validated ``assign=True`` bind at the first encode demand.
* ``COMFYMODAL_V2_CLIP_SNAPSHOT_EXCLUDE_WEIGHTS=1`` (Path B) — remove the
  physical parameter payload from the CPU snapshot at capture, retaining the
  structure/tokenizer/patcher and a frozen capability manifest; the weights
  are re-hydrated (or natively reconstructed) at demand.

Both are capability-based (no model-family branches) and fail closed:

* Invalid flag values are False (``env_flag`` semantics).
* Snapshot exclusion REQUIRES a verified fast-hydration-capable OR safe
  native-reconstruction manifest frozen at snapshot construction; eligibility
  is never re-derived from missing weight values after restore.
* Any pre-publication fast-path failure discards partial state, releases
  owners/buffers safely, clears temporary CUDA state, and falls back to the
  current native Comfy path — no partial model may escape.
* Cache-hit requests never encode, never call ``CLIP.load_model``, and
  therefore perform ZERO hydration.

Telemetry rides D2's trace with the same event shape (phase="execution",
JSON-safe metadata) and adds a ``hydration_source`` mode per request:
``native_cpu_h2d`` / ``fastsafetensors_direct_gpu`` / ``already_resident`` /
``conditioning_cache_hit_no_hydration``.  The fast-hydration layer itself
exposes file_to_gpu_wall_ms, checkpoint_bytes, GB/s, bind_wall_ms,
owner_mode, RSS delta, CUDA delta, zero_copy proof and fallback_count.

Initial remote tuning uses the C9-evidenced configuration as the starting
point (fastsafetensors, nogds=True, use_buf_register=False, 16 threads,
1 GiB blocks, bounded concurrency); parameters are exposed but no sweep is
run without remote evidence.
"""

from __future__ import annotations

import os
import inspect
import time
import weakref
from collections.abc import Mapping
from typing import Any, Callable, Optional

import torch

from comfymodal_runtime.env import env_flag
from comfymodal_runtime import clip_fast_hydration as cfh
from comfymodal_runtime import gpu_lane_coordination as _gpu_coord

_FLAG_FAST = "COMFYMODAL_V2_CLIP_FAST_HYDRATION"
_FLAG_STAGED = "COMFYMODAL_V2_CLIP_STAGED_HYDRATION"
_FLAG_EXCLUDE = "COMFYMODAL_V2_CLIP_SNAPSHOT_EXCLUDE_WEIGHTS"

_FASTSAFE_NOGDS = True
_FASTSAFE_USE_BUF_REGISTER = False

# ── E28: direct-GPU loader tuning (Target B) ──────────────────────────────
# E27 Follow-Up A first-touch screening (fresh container, RTX PRO 6000):
#   CLIP control T16/B1GiB = 3066.6 ms (2.62 GB/s)
#   CLIP best  T8/B64MiB  =  490.7 ms (16.40 GB/s)  6.25x
#   UNET control T16/B1GiB = 4287.4 ms (2.87 GB/s)
#   UNET best  T8/B256MiB =  699.4 ms (17.60 GB/s)  6.1x
# The CLIP and UNET loaders are tuned as an integrated pair (CPU/PCIe/stream
# contention).  Env overrides exist so the integrated campaign can tune
# without a redeploy of constants: threads via
# COMFYMODAL_V2_CLIP_FASTSAFE_THREADS (default 8), block bytes via
# COMFYMODAL_V2_CLIP_FASTSAFE_BLOCK_BYTES (default 64 MiB).  Values are read
# at call time so a request-carried allowlisted env can tune per run.
_FASTSAFE_THREADS = 8
_FASTSAFE_BLOCK_BYTES = 64 * 1024 * 1024  # 64 MiB (E28 winning configuration)
_FASTSAFE_NOGDS = True
_FASTSAFE_USE_BUF_REGISTER = False

_CLIP_THREADS_ENV = "COMFYMODAL_V2_CLIP_FASTSAFE_THREADS"
_CLIP_BLOCK_BYTES_ENV = "COMFYMODAL_V2_CLIP_FASTSAFE_BLOCK_BYTES"
_CLIP_BBUF_KB_ENV = "COMFYMODAL_V2_CLIP_FASTSAFE_BBUF_KB"
_CLIP_BBUF_KB = 512 * 1024  # 512 MiB bounce-buffer pool (see UNET note)


def _clip_fastsafe_bbuf_kb() -> int:
    """Effective nogds bounce-buffer pool size in KiB (env override, then
    default 512 MiB).  Minimum 16 MiB (the library default floor)."""
    try:
        raw = os.environ.get(_CLIP_BBUF_KB_ENV, "").strip()
        if raw:
            value = int(raw)
            if value >= 16 * 1024:
                return value
    except Exception:
        pass
    return _CLIP_BBUF_KB


def _clip_fastsafe_threads() -> int:
    """Effective CLIP loader thread count (env override, then default 8)."""
    try:
        raw = os.environ.get(_CLIP_THREADS_ENV, "").strip()
        if raw:
            value = int(raw)
            if value >= 1:
                return value
    except Exception:
        pass
    return _FASTSAFE_THREADS


def _clip_fastsafe_block_bytes() -> int:
    """Effective CLIP loader max-copy-block size (env override, then default
    64 MiB)."""
    try:
        raw = os.environ.get(_CLIP_BLOCK_BYTES_ENV, "").strip()
        if raw:
            value = int(raw)
            if value >= 1024 * 1024:
                return value
    except Exception:
        pass
    return _FASTSAFE_BLOCK_BYTES


def clip_fastsafe_config() -> dict[str, Any]:
    """Current effective CLIP loader configuration (telemetry/identity)."""
    return {
        "threads": _clip_fastsafe_threads(),
        "block_bytes": _clip_fastsafe_block_bytes(),
        "bbuf_kb": _clip_fastsafe_bbuf_kb(),
        "nogds": _FASTSAFE_NOGDS,
        "use_buf_register": _FASTSAFE_USE_BUF_REGISTER,
    }

_TOKENIZER_BLOB_KEYS = cfh._TOKENIZER_BLOB_KEYS

_RECORD: dict[str, dict[str, Any]] = {}

# Telemetry-only globals.  ``_ACTIVE_TRACE`` is the last trace seen at
# demand-install time (the demand-wrapper entry checkpoint has no trace of
# its own and falls back to it); ``_LAST_CLIP`` is a WEAKREF to the last clip
# observed by the demand path so ``clip_fh_request_summary`` can attach live
# state WITHOUT rooting the model object — a module-global STRONG reference to
# a CLIP defeats the snapshot eviction weakref-death gate (deploy4 failure
# class: ``RuntimeError('Full eviction failed: original weakrefs still
# alive')``).  Both are read only under the D3 flag gate and never affect
# hydration semantics.
_ACTIVE_TRACE: Any = None
_LAST_CLIP: Any = None  # weakref.ref(clip) or None; never a strong reference


def _blob_free(sd: dict) -> dict:
    """View of a file state dict without structural tokenizer blob tensors.

    Keys ``spiece_model`` / ``tekken_model`` / ``tokenizer_json`` are torch
    uint8 payloads consumed by tokenizer construction at ``CLIP.__init__``
    (comfy/sd.py reads them via ``clip_data[0].get(...)`` and never pops
    them; ``load_state_dict(strict=False)`` tolerates them as unexpected
    keys at bind time).  They are NOT bound parameters: exclude them from
    the capability gates, the frozen manifest evidence and the exact
    key/shape/dtype verification, but NEVER strip them from the actual
    state dict passed to the bind."""
    return {k: v for k, v in sd.items() if k not in _TOKENIZER_BLOB_KEYS}


def clip_fast_hydration_enabled() -> bool:
    return env_flag(_FLAG_FAST)


def clip_staged_hydration_enabled() -> bool:
    return env_flag(_FLAG_STAGED)


def clip_snapshot_exclude_weights_enabled() -> bool:
    return env_flag(_FLAG_EXCLUDE)


# Public re-export for the restore-side lanes (modal_app / model_preload) and
# for the demand wrapper's entry checkpoint: the pure hydration-state
# snapshot lives in clip_fast_hydration; wiring only re-exports it.
clip_hydration_state = cfh.clip_hydration_state


def _request_id() -> str:
    try:
        from comfymodal_runtime.model_preload import get_active_request_id

        value = get_active_request_id()
        return str(value) if value else ""
    except Exception:
        return ""


def _emit(trace: Any, name: str, metadata: dict[str, Any]) -> None:
    if trace is None:
        return
    try:
        payload = dict(metadata)
        payload.setdefault("request_id", _request_id())
        if hasattr(trace, "emit_at"):
            trace.emit_at(
                name,
                wall_unix_ns=time.time_ns(),
                monotonic_ns=time.monotonic_ns(),
                phase="execution",
                metadata=payload,
            )
        elif hasattr(trace, "emit"):
            trace.emit(name, phase="execution", metadata=payload)
    except Exception:
        pass


def _state_detail(state: dict[str, Any]) -> dict[str, Any]:
    """JSON-safe, small view of a clip_hydration_state snapshot: parameter
    counts, logical bytes and patcher devices only — no raw objects."""
    patcher = state.get("patcher") or {}
    return {
        "params": state.get("params"),
        "bytes": state.get("bytes"),
        "devices": {
            "load_device": patcher.get("load_device"),
            "offload_device": patcher.get("offload_device"),
            "current_device": patcher.get("current_device"),
        },
    }


def _emit_decision(
    trace: Any,
    *,
    decision: str,
    reason: str,
    state_before: Optional[str] = None,
    state_detail: Optional[dict[str, Any]] = None,
    state_after: Optional[str] = None,
    fast_hydration_allowed: Optional[bool] = None,
    weights_excluded: Optional[bool] = None,
) -> None:
    """Emit one ``clip_fh_hydration_decision`` trace event.

    JSON-safe metadata only: decision/reason strings, canonical state labels
    (state_before/state_after), the trimmed state_detail dict, and the two
    capability booleans.  Never raises (``_emit`` swallows all errors)."""
    metadata: dict[str, Any] = {"decision": decision, "reason": reason}
    if state_before is not None:
        metadata["state_before"] = state_before
    if state_detail is not None:
        metadata["state_detail"] = state_detail
    if state_after is not None:
        metadata["state_after"] = state_after
    if fast_hydration_allowed is not None:
        metadata["fast_hydration_allowed"] = bool(fast_hydration_allowed)
    if weights_excluded is not None:
        metadata["weights_excluded"] = bool(weights_excluded)
    _emit(trace, "clip_fh_hydration_decision", metadata)


def resolve_capture_clip(holder: Any) -> tuple[Any, str]:
    """Resolve the canonical CLIP object a lifecycle checkpoint should inspect.

    Production call sites (``modal_app`` capture/restore checkpoints) pass the
    ``CpuSnapshotModels`` CONTAINER, not the CLIP itself.  ``clip_hydration_state``
    walks the passed object literally — a container has no ``cond_stage_model``,
    no manifest, no markers — so probing the container directly reports
    ``INVALID/PARTIAL total_params=0 manifest_eligible=False`` (the D10 Gate-D
    failure: reconcile proved 399 meta params + eligible manifest at
    16:01:29.809Z, Gate D "lost" them 44 ms later because it inspected the
    wrong holder, not because the object changed).

    Resolution rules (deterministic, capability-based, no model-name branches):

      * holder is None                                   -> (None, "none")
      * holder has ``cond_stage_model`` only             -> (holder, "direct")
      * holder has ``clip`` only (container-like)        -> (holder.clip, "cpu_snapshot_models.clip")
      * holder has BOTH (conflicting candidates)         -> (None, "ambiguous") — fail closed
      * otherwise                                        -> (None, "unsupported")

    Returns the object + a holder-source label; NEVER stores the object
    anywhere (non-rooting), never mutates the model, never allocates.
    """
    if holder is None:
        return None, "none"
    has_csm = hasattr(holder, "cond_stage_model")
    has_clip_attr = hasattr(holder, "clip")
    if has_csm and has_clip_attr:
        return None, "ambiguous"
    if has_csm:
        return holder, "direct"
    if has_clip_attr:
        try:
            return holder.clip, "cpu_snapshot_models.clip"
        except Exception:
            return None, "cpu_snapshot_models.clip"
    return None, "unsupported"


def clip_state_checkpoint(trace: Any, name: str, holder: Any) -> None:
    """Emit a ``clip_state_checkpoint`` event carrying the pure
    ``clip_hydration_state(clip)`` snapshot under *name*.

    *holder* may be the CLIP itself or the ``CpuSnapshotModels`` container —
    the canonical CLIP is resolved through :func:`resolve_capture_clip` so
    capture/restore checkpoints always inspect the ACTUAL object retained for
    snapshot capture / consumed by restore (D10 Gate-D root cause:
    CHECKPOINT_TARGET_MISMATCH).  When resolution yields no CLIP the
    checkpoint reports ``state=no_clip`` and the event carries
    ``holder_source`` + ``clip_object_id=None`` — fail closed, never a
    fabricated INVALID/PARTIAL.

    Gated on ``clip_fast_hydration_enabled() or
    clip_snapshot_exclude_weights_enabled()``: with both flags off this is a
    strict no-op (zero behavior change).  *trace* may be None — the last
    trace seen at demand-install time (``_ACTIVE_TRACE``) is then used, which
    is what the demand-wrapper entry checkpoint relies on.  JSON-safe
    value-only metadata (ids/bools/ints/strings); the resolved object is
    NEVER stored (non-rooting); never raises."""
    if not (
        clip_fast_hydration_enabled()
        or clip_staged_hydration_enabled()
        or clip_snapshot_exclude_weights_enabled()
    ):
        return
    active = trace if trace is not None else _ACTIVE_TRACE
    clip, holder_source = None, "none"
    try:
        clip, holder_source = resolve_capture_clip(holder)
    except Exception:
        clip, holder_source = None, "unsupported"
    if clip is None:
        print(
            f"[v2.clip_state] checkpoint={name} state=no_clip "
            f"holder_source={holder_source} clip_object_id=None",
            flush=True,
        )
        _emit(
            active,
            "clip_state_checkpoint",
            {
                "checkpoint": name,
                "state": None,
                "holder_source": holder_source,
                "clip_object_id": None,
                "cond_stage_model_object_id": None,
                "patcher_object_id": None,
                "underlying_model_object_id": None,
                "manifest_present": False,
                "manifest_eligible": False,
                "demand_wrapper_present": False,
                "hydration_marker_present": False,
            },
        )
        return
    try:
        state = cfh.clip_hydration_state(clip)
    except Exception:
        state = {}
    params = state.get("params") or {}
    bytes_ = state.get("bytes") or {}
    _csm = getattr(clip, "cond_stage_model", None)
    _patcher = getattr(clip, "patcher", None)
    _underlying = getattr(_patcher, "model", None) if _patcher is not None else None
    print(
        f"[v2.clip_state] checkpoint={name} state={state.get('state')} "
        f"cpu_bytes={bytes_.get('cpu', 0)} cuda_params={params.get('cuda', 0)} "
        f"meta_params={params.get('meta', 0)} cpu_params={params.get('cpu', 0)} "
        f"total_params={params.get('total', 0)} "
        f"manifest_eligible={bool(state.get('manifest_eligible', False))} "
        f"holder_source={holder_source} clip_object_id={id(clip)} "
        f"cond_stage_model_object_id={id(_csm) if _csm is not None else 'None'} "
        f"patcher_object_id={id(_patcher) if _patcher is not None else 'None'} "
        f"underlying_model_object_id={id(_underlying) if _underlying is not None else 'None'} "
        f"manifest_present={bool(state.get('manifest_present', False))} "
        f"demand_wrapper_present={bool(getattr(clip, cfh.DEMAND_WRAPPER_MARKER, False))} "
        f"hydration_marker_present={bool(state.get('hydrated', False))}",
        flush=True,
    )
    _emit(
        active,
        "clip_state_checkpoint",
        {
            "checkpoint": name,
            "state": state,
            "holder_source": holder_source,
            "clip_object_id": id(clip),
            "cond_stage_model_object_id": id(_csm) if _csm is not None else None,
            "patcher_object_id": id(_patcher) if _patcher is not None else None,
            "underlying_model_object_id": id(_underlying) if _underlying is not None else None,
            "manifest_present": bool(state.get("manifest_present", False)),
            "manifest_eligible": bool(state.get("manifest_eligible", False)),
            "demand_wrapper_present": bool(getattr(clip, cfh.DEMAND_WRAPPER_MARKER, False)),
            "hydration_marker_present": bool(state.get("hydrated", False)),
        },
    )


def _note_clip(clip: Any) -> None:
    """Record the last clip observed by the demand path as a WEAKREF so the
    module-global never roots a model object.  A strong reference here would
    defeat the snapshot eviction weakref-death gate (the deploy4 failure
    class: the capture-side install kept the CLIP alive, so the full-eviction
    weakref proof could never reach alive=0).  Non-weakrefable objects are
    ignored (stored as None)."""
    global _LAST_CLIP
    if clip is None:
        _LAST_CLIP = None
        return
    try:
        _LAST_CLIP = weakref.ref(clip)
    except TypeError:
        _LAST_CLIP = None


def _comfy_utils(comfy_utils: Any = None) -> Any:
    if comfy_utils is not None:
        return comfy_utils
    try:
        import comfy.utils

        return comfy.utils
    except Exception:
        return None


def _cuda_baseline() -> Optional[int]:
    try:
        import torch

        if not torch.cuda.is_available():
            return None
        torch.cuda.reset_peak_memory_stats()
        return int(torch.cuda.memory_allocated())
    except Exception:
        return None


def _cuda_peak_delta(baseline: Optional[int]) -> Optional[int]:
    if baseline is None:
        return None
    try:
        import torch

        if not torch.cuda.is_available():
            return None
        peak = torch.cuda.max_memory_allocated()
        return max(int(peak - int(baseline)), 0)
    except Exception:
        return None


def _rss_mb() -> Optional[float]:
    try:
        import psutil

        return float(psutil.Process().memory_info().rss) / 1048576.0
    except Exception:
        return None


# ── Transform pipeline (capability-triggered, recorded at capture) ─────────


def _select_pipeline(sd: dict) -> list[dict]:
    """Select the state-dict transforms strictly from key-pattern triggers."""
    pipeline: list[dict] = []
    if "transformer.resblocks.0.ln_1.weight" in sd:
        pipeline.append(
            {"op": "clip_text_transformers_convert", "prefix_from": "", "prefix_to": ""}
        )
    if "text_projection" in sd and "text_projection.weight" not in sd:
        pipeline.append({"op": "text_projection"})
    if "lm_head.weight" in sd:
        pipeline.append({"op": "lm_head"})
    return pipeline


def _apply_pipeline(sd: dict, pipeline: list[dict], comfy_utils: Any = None) -> dict:
    out = dict(sd)
    for op in pipeline:
        name = op.get("op")
        if name == "clip_text_transformers_convert":
            cu = _comfy_utils(comfy_utils)
            if cu is None:
                raise RuntimeError("comfy.utils unavailable for clip_text_transformers_convert")
            out = cu.clip_text_transformers_convert(
                out, op.get("prefix_from", ""), op.get("prefix_to", "")
            )
        elif name == "text_projection":
            out["text_projection.weight"] = out.pop("text_projection").transpose(0, 1).contiguous()
        elif name == "lm_head":
            out["model.lm_head.weight"] = out.pop("lm_head.weight")
    return out


# ── Manifest (frozen at snapshot construction) ─────────────────────────────


def _clip_file_paths(cpu_models: Any) -> list[str]:
    paths: list[str] = []
    facts = getattr(cpu_models, "file_facts", ()) or ()
    for fact in facts:
        if getattr(fact, "role", "") in ("clip1", "clip2") and getattr(fact, "path", ""):
            paths.append(str(fact.path))
    return paths


def _loader_specs(cpu_models: Any) -> list[dict]:
    specs: list[dict] = []
    try:
        loaders = (getattr(cpu_models, "model_spec", None) or {}).get("loaders", {})
        for entry in loaders.get("clip", []) or []:
            spec: dict[str, Any] = {}
            getter = getattr(entry, "get", None)
            if callable(getter):
                spec["clip_name"] = str(getter("clip_name", "") or "")
                spec["type"] = str(getter("type", "") or "")
            elif isinstance(entry, (tuple, list)) and entry:
                spec["clip_name"] = str(entry[0] if entry else "")
                spec["type"] = str(entry[1] if len(entry) > 1 else "")
            if spec.get("clip_name"):
                specs.append(spec)
    except Exception:
        pass
    return specs


def _verify_file_against_manifest(
    file_manifest: dict, sd: dict
) -> tuple[bool, str]:
    # Both sides must agree on the same key universe: the manifest never
    # recorded tokenizer blob keys, so verify against the blob-free view of
    # the replayed sd (the raw sd still carries the blobs to the bind).
    view = _blob_free(sd)
    key_set = file_manifest.get("key_set") or []
    if sorted(view.keys()) != key_set:
        return False, (
            f"key set mismatch: got {len(view)} expected {len(key_set)} "
            "(state-dict transform replay diverged from the frozen manifest)"
        )
    for key, tensor in view.items():
        expected_shape = file_manifest.get("key_shapes", {}).get(key)
        if expected_shape is not None and list(tensor.shape) != expected_shape:
            return False, f"shape mismatch for {key}"
        if str(tensor.dtype) != file_manifest.get("dtype"):
            return False, f"dtype mismatch for {key}"
    return True, f"exact key/shape/dtype match vs frozen manifest ({len(key_set)} keys)"


def _build_manifest(
    clip: Any, paths: list[str], comfy_utils: Any = None
) -> Optional[dict]:
    import torch

    import safetensors.torch

    if not paths:
        return None
    if getattr(clip, "cond_stage_model", None) is None:
        return None
    files: list[dict[str, Any]] = []
    reasons: list[str] = []
    for path in paths:
        if not os.path.exists(path):
            reasons.append(f"missing:{os.path.basename(path)}")
            continue
        try:
            metadata: dict[str, Any] = {}
            with safetensors.safe_open(path, framework="pt") as sf:
                metadata = dict(sf.metadata() or {})
            sd = safetensors.torch.load_file(path, device="cpu")
            non_tensor = [k for k, v in sd.items() if not isinstance(v, torch.Tensor)]
            # Tokenizer blob tensors (spiece_model / tekken_model /
            # tokenizer_json) are structural payloads consumed at tokenizer
            # construction — never bound parameters.  Exclude them from the
            # gates, key_set, key_shapes and dtype evidence (both sides of the
            # manifest verification) while the raw sd keeps them for the bind.
            work = _blob_free({k: v for k, v in sd.items() if isinstance(v, torch.Tensor)})
            quant_keys = [k for k in work if "comfy_quant" in k or "scaled_fp8" in k]
            quant = bool(quant_keys) or bool(metadata.get("_quantization_metadata"))
            pipeline = _select_pipeline(work)
            transformed = _apply_pipeline(work, pipeline, comfy_utils=comfy_utils)
            storage_ok = cfh.gate_plain_tensor_storage(transformed)
            dtype_ok = cfh.gate_uniform_dtype(transformed)
            if not (storage_ok.passed and dtype_ok.passed and not quant):
                reasons.append(
                    f"{os.path.basename(path)}: storage={storage_ok.passed} "
                    f"dtype={dtype_ok.passed} quant={quant}"
                )
                continue
            dtypes = {str(v.dtype) for v in transformed.values()}
            files.append(
                {
                    "path": path,
                    "size_bytes": int(os.path.getsize(path)),
                    "mtime_ns": int(os.path.getmtime(path) * 1_000_000_000),
                    "dtype": str(next(iter(dtypes))),
                    "key_set": sorted(transformed.keys()),
                    "key_shapes": {k: list(v.shape) for k, v in transformed.items()},
                    "pipeline": pipeline,
                    "non_tensor_entries": non_tensor,
                    "quant_metadata_present": bool(metadata.get("_quantization_metadata")),
                }
            )
        except Exception as exc:
            reasons.append(f"{os.path.basename(path)}: {type(exc).__name__}: {str(exc)[:120]}")
    if not files:
        return {"eligible": False, "reason": "; ".join(reasons) or "no usable files"}
    per_file_key_sets = [set(f["key_set"]) for f in files]
    routing_ok, routing_detail = cfh.verify_leaf_routing(clip, per_file_key_sets)
    assign_ok, assign_detail = cfh.can_assign_sd_supported(clip)
    if not routing_ok:
        return {"eligible": False, "reason": f"routing: {routing_detail}"}
    if not assign_ok:
        return {"eligible": False, "reason": f"can_assign_sd: {assign_detail}"}
    return {
        "schema": 1,
        "eligible": True,
        "reason": "capability gates passed at capture",
        "files": files,
        "assign_bind_supported": True,
        "fastsafe_config": {
            "threads": _clip_fastsafe_threads(),
            "block_bytes": _clip_fastsafe_block_bytes(),
            "nogds": _FASTSAFE_NOGDS,
            "use_buf_register": _FASTSAFE_USE_BUF_REGISTER,
        },
        "capture_ts_ns": time.time_ns(),
        "loader_specs": [],
    }


# ── Capture side (startup) ─────────────────────────────────────────────────


def maybe_prepare_clip_snapshot_exclusion(
    cpu_models: Any, *, trace: Any = None, comfy_utils: Any = None
) -> dict[str, Any]:
    """Build the frozen capability manifest at snapshot construction; when
    Path B is on and the candidate is eligible, strip the parameter payload
    in place (retaining structure/tokenizer/patcher).  Fail closed."""
    if not (
        clip_fast_hydration_enabled()
        or clip_staged_hydration_enabled()
        or clip_snapshot_exclude_weights_enabled()
    ):
        return {"status": "disabled"}
    clip = getattr(cpu_models, "clip", None)
    if clip is None:
        return {"status": "no_clip"}
    if cfh.clip_weights_excluded(clip):
        return {"status": "already_excluded"}
    try:
        manifest = _build_manifest(clip, _clip_file_paths(cpu_models), comfy_utils=comfy_utils)
    except Exception as exc:
        _emit(trace, "clip_fh_capture", {"status": "error", "reason": f"{type(exc).__name__}: {str(exc)[:160]}"})
        return {"status": "error", "reason": str(exc)[:200]}
    if manifest is None or not manifest.get("eligible"):
        reason = (manifest or {}).get("reason", "no manifest")
        _emit(trace, "clip_fh_capture", {"status": "ineligible", "reason": reason})
        return {"status": "ineligible", "reason": reason}
    manifest["loader_specs"] = _loader_specs(cpu_models)
    manifest["fast_hydration_allowed"] = clip_fast_hydration_enabled()
    manifest["staged_hydration_allowed"] = clip_staged_hydration_enabled()
    cfh.attach_clip_manifest(clip, manifest)
    if clip_snapshot_exclude_weights_enabled():
        clip_state_checkpoint(trace, "capture_pre_exclusion", clip)
        stats = cfh.strip_clip_weights(clip)
        clip_state_checkpoint(trace, "capture_post_exclusion", clip)
        _emit(
            trace,
            "clip_fh_capture",
            {
                "status": "excluded",
                "params_replaced": stats["params_replaced"],
                "payload_bytes_removed": stats["payload_bytes_removed"],
            },
        )
        return {"status": "excluded", "manifest": manifest, "stripped": True}
    _emit(
        trace,
        "clip_fh_capture",
        {"status": "manifest_only", "files": len(manifest.get("files", []))},
    )
    return {"status": "manifest_only", "manifest": manifest, "stripped": False}


# ── Restore / demand side ──────────────────────────────────────────────────


def _fastsafe_load(path: str) -> tuple[dict, Any, Any]:
    """fastsafetensors direct-to-GPU read (E28 tuned config: threads=8,
    max_copy_block=64 MiB — env-overridable).  Returns (tensors, loader,
    fb); caller OWNS loader+fb and must not close while tensors are live.
    Raises on failure."""
    mod = cfh._fastsafe_module()
    if mod is None:
        raise RuntimeError("fastsafetensors unavailable")
    cls = getattr(mod, "SafeTensorsFileLoader", None)
    if not callable(cls):
        raise RuntimeError("fastsafetensors.SafeTensorsFileLoader unavailable")
    import torch

    from typing import cast as _cast

    device_str = f"cuda:{torch.cuda.current_device()}"
    loader = _cast(Any, cls(
        None,
        device_str,
        max_threads=_clip_fastsafe_threads(),
        # E28: a large nogds bounce-buffer pool keeps all reader threads with
        # reads in flight (the library default 16 MiB serializes the cold
        # file read to ~1.2 GB/s).  Env-overridable.
        bbuf_size_kb=_clip_fastsafe_bbuf_kb(),
        nogds=_FASTSAFE_NOGDS,
        disable_cache=True,
    ))
    try:
        loader.add_filenames({0: [str(path)]})
        fb = loader.copy_files_to_device(
            use_buf_register=_FASTSAFE_USE_BUF_REGISTER,
            max_copy_block_size=_clip_fastsafe_block_bytes(),
        )
        keys = list(loader.get_keys())
        sd = {k: fb.get_tensor(k) for k in keys}
        return sd, loader, fb
    except Exception:
        try:
            loader.close()
        except Exception:
            pass
        raise


def _try_fast_hydrate(
    clip: Any, manifest: dict, *, trace: Any = None, comfy_utils: Any = None
) -> dict[str, Any]:
    """Load every file to GPU, replay the frozen pipeline, verify against the
    manifest, bind via Comfy's own dispatch with assign=True, attach owners.
    All files are loaded+verified BEFORE any bind so a failure leaves the
    model untouched."""
    import torch

    files = manifest.get("files", [])
    owners: list[tuple[Any, Any]] = []
    per_file_sds: list[dict] = []
    checkpoint_bytes = 0
    file_to_gpu_ms = 0.0
    rss_before = _rss_mb()
    baseline = _cuda_baseline()
    t0 = time.perf_counter()
    _orchestration_record = None
    _copy_event = None
    _scoped_readiness = _gpu_coord.scoped_cuda_readiness_enabled()
    # ── E25: take a completed speculative read (file->GPU + transform) so
    # the file read is hidden under setup; verification + bind + sync still
    # run here exactly as before.  Fail-closed: on any inconsistency the
    # normal per-file read loop below runs.
    _speculative_taken = None
    _speculative_take_reason = ""
    try:
        from .speculative_clip_hydration import (
            take_speculative_read,
            active_speculative_request_id,
            join_speculative_clip_lane,
            get_speculative_clip_lane,
        )

        _rid = str(getattr(trace, "request_id", "") or _request_id())
        _speculative_taken = take_speculative_read(_rid) if _rid else None
        if _speculative_taken is None:
            # Demand-time request-id fallback: when the primary lookup misses
            # (trace request_id differs from the lane's plan-receipt key) OR
            # the trace/context carries no request_id, fall back to the single
            # active lane (the container runs one request at a time).
            # Fail-closed: only when exactly one unconsumed lane exists and
            # its read is completed+ok.
            _fallback_rid = active_speculative_request_id()
            if _fallback_rid and _fallback_rid != _rid:
                _speculative_taken = take_speculative_read(_fallback_rid)
                _speculative_take_reason = f"primary_miss_fallback:{_fallback_rid}"
            elif _fallback_rid == _rid and _speculative_taken is None:
                _speculative_take_reason = "lane_not_takeable"
            elif not _fallback_rid:
                _speculative_take_reason = "no_active_lane"
        if _speculative_taken is None:
            # E26: the speculative lane may still be READING when the demand
            # path arrives (the plan-receipt start is earlier than the graph
            # demand, but the read can outlast request setup).  Join it with a
            # bounded wait so a completed successful speculative read is
            # consumed instead of forcing a second full CLIP file read.  The
            # join is fail-closed: on timeout or a failed read the normal
            # demand read loop runs exactly once.
            _join_rid = _rid or active_speculative_request_id()
            _lane = get_speculative_clip_lane(_join_rid) if _join_rid else None
            if _lane is not None and _lane.finished_mono_ns == 0:
                _join_ms = join_speculative_clip_lane(_join_rid, timeout_s=20.0)
                _speculative_take_reason = (
                    f"joined_lane_ms={round((_join_ms or {}).get('speculative_read_ms', 0) or 0, 1)}"
                )
                _speculative_taken = take_speculative_read(_join_rid)
                if _speculative_taken is None:
                    _speculative_take_reason += ":join_take_failed"
            elif _lane is not None:
                _speculative_take_reason = "lane_finished_not_takeable"
        _emit(
            trace,
            "clip_fh_speculative_take_result",
            {
                "request_id": _rid,
                "taken": int(_speculative_taken is not None),
                "reason": _speculative_take_reason or "primary_hit",
            },
        )
    except Exception:
        _speculative_taken = None
    try:
        try:
            from comfymodal_runtime.fast_cold_orchestration import (
                before_clip_demand as _before_clip_demand,
                record_fastsafe as _record_fastsafe,
            )

            _orchestration_record = _record_fastsafe
            if not _before_clip_demand(
                request_id=str(getattr(trace, "request_id", "") or _request_id()),
                trace=trace,
                paths=[entry.get("path", "") for entry in files],
            ):
                raise RuntimeError("structural_source_fence_failure:clip")
            _record_fastsafe(
                "clip",
                "start",
                request_id=str(getattr(trace, "request_id", "") or _request_id()),
                trace=trace,
                execution_identity=cfh.MODE_FASTSAFE,
            )
        except Exception as _exc:
            if "structural_source_fence_failure" in str(_exc):
                raise
            _orchestration_record = None
        if _speculative_taken is not None:
            # The speculative lane already read + transformed every file.  The
            # manifest verification below is the same gate the normal read
            # loop applies — a mismatch drops the speculative tensors and
            # falls back to the normal per-file read.
            _spec_per_file_sds, _spec_owners, _spec_record = _speculative_taken
            # E28 Target C: when the speculative lane applied the compute-ready
            # FP32 cast-once, verification expects FP32 (the cast target) —
            # exact key set + shapes as frozen, dtype FP32.  Fail-closed: any
            # doubt falls back to the normal BF16 read.  The record's
            # ``cast_once`` is always a dict (never None).
            _spec_cast_applied = bool(
                ((_spec_record or {}).get("cast_once") or {}).get("applied", False)
            )
            _all_ok = True
            _detail = ""
            if len(_spec_per_file_sds) != len(files):
                _all_ok = False
                _detail = f"file count {len(_spec_per_file_sds)} != manifest {len(files)}"
            if _all_ok and _spec_cast_applied:
                try:
                    from .clip_fp32_cast_once import (
                        assert_compute_ready_no_patches,
                        verify_cast_once_sd,
                    )

                    _ready_ok, _ready_detail = assert_compute_ready_no_patches(clip)
                    if not _ready_ok:
                        _all_ok = False
                        _detail = f"cast_once_patch_gate: {_ready_detail}"
                    for _idx, (_file_manifest, _sd) in enumerate(
                        zip(files, _spec_per_file_sds)
                    ):
                        if not _all_ok:
                            break
                        ok, detail = verify_cast_once_sd(_file_manifest, _sd)
                        if not ok:
                            _all_ok = False
                            _detail = f"file {_idx}: {detail}"
                            break
                except Exception as _cast_exc:
                    _all_ok = False
                    _detail = f"cast_once_verify_error: {type(_cast_exc).__name__}"
            elif _all_ok:
                for _idx, (_file_manifest, _sd) in enumerate(
                    zip(files, _spec_per_file_sds)
                ):
                    ok, detail = _verify_file_against_manifest(_file_manifest, _sd)
                    if not ok:
                        _all_ok = False
                        _detail = f"file {_idx}: {detail}"
                        break
            if _all_ok:
                per_file_sds = _spec_per_file_sds
                owners = _spec_owners
                for _file_manifest in files:
                    checkpoint_bytes += int(_file_manifest.get("size_bytes", 0))
                file_to_gpu_ms = float(
                    (_spec_record or {}).get("speculative_read_ms", 0.0) or 0.0
                )
                # ── E28: ownership-chain proof at take-consume ──
                # Object IDs + CPU/CUDA/meta parameter counts at the exact
                # take boundary, so the speculative->bind ownership is
                # provable from telemetry alone (never inferred).
                try:
                    _chain_state = cfh.clip_hydration_state(clip)
                    _chain_params = _chain_state.get("params") or {}
                    _emit(
                        trace,
                        "clip_fh_speculative_consume_proof",
                        {
                            "clip_object_id": str(id(clip)),
                            "cond_stage_model_object_id": str(
                                id(getattr(clip, "cond_stage_model", None))
                            ) if getattr(clip, "cond_stage_model", None) is not None else "None",
                            "patcher_object_id": str(
                                id(getattr(clip, "patcher", None))
                            ) if getattr(clip, "patcher", None) is not None else "None",
                            "state": _chain_state.get("state"),
                            "params": _chain_params,
                            "speculative": 1,
                        },
                    )
                except Exception:
                    pass
                _emit(
                    trace,
                    "clip_fh_speculative_consumed",
                    {
                        "files": len(per_file_sds),
                        "speculative_read_ms": round(file_to_gpu_ms, 3),
                        "cast_once": int(_spec_cast_applied),
                    },
                )
            else:
                # Mismatch: release the speculative owners and run the normal
                # read loop below (the manifest is authoritative).
                for _loader, _fb in _spec_owners:
                    try:
                        _loader.close()
                    except Exception:
                        pass
                _emit(
                    trace,
                    "clip_fh_speculative_rejected",
                    {"reason": _detail or "unknown"},
                )
        if not per_file_sds:
            for file_manifest in files:
                path = file_manifest.get("path", "")
                if not os.path.exists(path):
                    raise RuntimeError(f"missing source file: {path}")
                t_load = time.perf_counter()
                _e27_source_start = time.monotonic_ns()
                sd_raw, loader, fb = _fastsafe_load(path)
                _e27_source_end = time.monotonic_ns()
                t_loaded = time.perf_counter()
                file_to_gpu_ms += (t_loaded - t_load) * 1000.0
                # E27: CLIP source-read span on the shared monotonic axis.
                try:
                    from .e27_forensics import emit_e27_span

                    emit_e27_span(
                        "clip_source_read",
                        start_ns=_e27_source_start,
                        end_ns=_e27_source_end,
                        path=path,
                        file_bytes=int(file_manifest.get("size_bytes", 0) or 0),
                    )
                except Exception:
                    pass
                transformed = _apply_pipeline(sd_raw, file_manifest.get("pipeline", []), comfy_utils=comfy_utils)
                ok, detail = _verify_file_against_manifest(file_manifest, transformed)
                if not ok:
                    raise RuntimeError(detail)
                per_file_sds.append(transformed)
                owners.append((loader, fb))
                checkpoint_bytes += int(file_manifest.get("size_bytes", 0))
        if _scoped_readiness:
            _copy_event = _gpu_coord.record_copy_event(
                "clip", trace, stream=torch.cuda.current_stream()
            )
            if _copy_event is None:
                raise RuntimeError("scoped_copy_event_unavailable")
        t_bind = time.perf_counter()
        ok, evidence = cfh.hydrate_clip_bind(
            clip,
            per_file_sds,
            require_no_meta=cfh.clip_weights_excluded(clip),
            expect_device=f"cuda:{torch.cuda.current_device()}",
        )
        if not ok:
            raise RuntimeError(f"bind: {evidence}")
        for loader, fb in owners:
            cfh.owner_attach(clip, loader, fb)
        _bind_wait_started_ns = 0
        _bind_wait_ok = False
        try:
            _bind_wait_started_ns = _gpu_coord.bind_wait_start(
                trace, reason="clip_bind_completion"
            )
        except Exception:
            _bind_wait_started_ns = time.monotonic_ns()
        try:
            if _scoped_readiness:
                _bind_wait_ok = _gpu_coord.wait_copy_event(
                    "clip", _copy_event, trace,
                    stream=torch.cuda.current_stream(),
                )
                if not _bind_wait_ok:
                    raise RuntimeError("scoped_copy_event_wait_failed")
            else:
                _gpu_coord.record_device_wide_sync("clip", trace)
                torch.cuda.synchronize()
            _bind_wait_ok = True
        finally:
            try:
                _gpu_coord.bind_wait_end(
                    trace,
                    _bind_wait_started_ns,
                    success=_bind_wait_ok,
                    reason="clip_bind_completion",
                )
            except Exception:
                pass
        bind_ms = (time.perf_counter() - t_bind) * 1000.0
        wall_ms = (time.perf_counter() - t0) * 1000.0
        cfh.mark_clip_hydrated(clip)
        # ── E28: post-bind ownership/residency proof ──
        # GPU parameter counts after the bind — proves the speculative
        # GPU tensors were retained (cuda=N, meta=0) or exposes a fallback.
        try:
            _post_state = cfh.clip_hydration_state(clip)
            _post_params = _post_state.get("params") or {}
            _emit(
                trace,
                "clip_fh_bind_residency_proof",
                {
                    "clip_object_id": str(id(clip)),
                    "state": _post_state.get("state"),
                    "params": _post_params,
                    "speculative": int(_speculative_taken is not None),
                },
            )
        except Exception:
            pass
        if _orchestration_record is not None:
            _orchestration_record(
                "clip",
                "end",
                request_id=str(getattr(trace, "request_id", "") or ""),
                trace=trace,
                event_recorded=bool(_copy_event),
            )
        gbps = (
            round((checkpoint_bytes / (1024.0 ** 3)) / (file_to_gpu_ms / 1000.0), 3)
            if file_to_gpu_ms > 0
            else None
        )
        result: dict[str, Any] = {
            "ok": True,
            "mode": cfh.MODE_FASTSAFE,
            "file_to_gpu_wall_ms": round(file_to_gpu_ms, 3),
            "checkpoint_bytes": checkpoint_bytes,
            "gbps": gbps,
            "bind_wall_ms": round(bind_ms, 3),
            "wall_ms": round(wall_ms, 3),
            "owner_mode": "fastsafetensors_buf",
            "rss_delta_mb": (
                None if rss_before is None else round((_rss_mb() or rss_before) - rss_before, 3)
            ),
            "cuda_delta_bytes": _cuda_peak_delta(baseline),
            "zero_copy": True,
            "zero_copy_evidence": evidence,
            "fallback_count": 0,
        }
        _emit(
            trace,
            "clip_fh_hydration_start",
            {"mode": result["mode"], "checkpoint_bytes": checkpoint_bytes},
        )
        # E27: memory boundary before/after CLIP hydration (gated, aggregated).
        try:
            from .e27_forensics import snapshot_e27_memory

            snapshot_e27_memory(
                trace, "clip_hydration_done",
                mode=result["mode"],
                checkpoint_bytes=checkpoint_bytes,
            )
        except Exception:
            pass
        _emit(trace, "clip_fh_hydration_end", result)
        return result
    except Exception as exc:
        if _orchestration_record is not None:
            try:
                _orchestration_record(
                    "clip",
                    "end",
                    request_id=str(getattr(trace, "request_id", "") or ""),
                    trace=trace,
                    event_recorded=False,
                )
            except Exception:
                pass
        for loader, fb in owners:
            try:
                loader.close()
            except Exception:
                pass
        try:
            torch.cuda.empty_cache()
        except Exception:
            pass
        reason = f"{type(exc).__name__}: {str(exc)[:160]}"
        state = cfh.clip_hydration_state(clip)["state"]
        _emit_decision(
            trace,
            decision="fast_path",
            reason=reason,
            state_before=state,
            state_after=state,
        )
        if "scoped_copy_event" in str(exc) or "structural_source_fence_failure" in str(exc):
            raise
        return {
            "ok": False,
            "mode": cfh.MODE_NATIVE,
            "reason": reason,
            "fallback_count": 1,
            "wall_ms": round((time.perf_counter() - t0) * 1000.0, 3),
        }


def _hydrate_cpu_assign(
    clip: Any, manifest: dict, *, trace: Any = None, comfy_utils: Any = None
) -> dict[str, Any]:
    """Safe native reconstruction (Path B fallback): CPU mmap tensors bound
    through Comfy's own load_sd dispatch with assign=True; the subsequent
    native load_model performs the ordinary H2D."""
    import torch

    import safetensors.torch

    state_before = cfh.clip_hydration_state(clip)["state"]
    try:
        per_file_sds: list[dict] = []
        for file_manifest in manifest.get("files", []):
            path = file_manifest.get("path", "")
            sd = safetensors.torch.load_file(path, device="cpu")
            work = {k: v for k, v in sd.items() if isinstance(v, torch.Tensor)}
            transformed = _apply_pipeline(work, file_manifest.get("pipeline", []), comfy_utils=comfy_utils)
            ok, detail = _verify_file_against_manifest(file_manifest, transformed)
            if not ok:
                raise RuntimeError(detail)
            per_file_sds.append(transformed)
        ok, evidence = cfh.hydrate_clip_bind(
            clip, per_file_sds, require_no_meta=True, expect_device="cpu"
        )
        if not ok:
            raise RuntimeError(f"bind: {evidence}")
        cfh.mark_clip_hydrated(clip)
        result = {
            "ok": True,
            "mode": cfh.MODE_NATIVE,
            "reconstruction": "cpu_assign",
            "zero_copy_evidence": evidence,
            "fallback_count": 1,
        }
        _emit(trace, "clip_fh_hydration_end", result)
        _emit_decision(
            trace,
            decision="native_fallback",
            reason="cpu_assign",
            state_before=state_before,
            state_after=cfh.clip_hydration_state(clip)["state"],
        )
        return result
    except Exception:
        _emit_decision(
            trace,
            decision="native_copy_fallback",
            reason="cpu_assign_failed",
            state_before=state_before,
        )
        return _hydrate_native_copy(clip, manifest, trace=trace, comfy_utils=comfy_utils)


def _invoke_native_clip_loader(specs: list[dict]) -> Any:
    """Invoke the CURRENT native Comfy CLIP loader exactly once (device='cpu'
    when supported), mirroring the capture-time loader call shape."""
    try:
        import inspect

        from comfy import nodes
    except Exception:
        return None
    try:
        if len(specs) == 1:
            loader = nodes.CLIPLoader()
            fn = getattr(loader, "load_clip", None)
            if not callable(fn):
                return None
            kwargs: dict[str, Any] = {}
            sig = inspect.signature(fn)
            if "device" in sig.parameters:
                kwargs["device"] = "cpu"
            return fn(str(specs[0].get("clip_name", "")), str(specs[0].get("type", "stable_diffusion")), **kwargs)
        if len(specs) >= 2:
            loader = nodes.DualCLIPLoader()
            fn = getattr(loader, "load_clip", None)
            if not callable(fn):
                return None
            kwargs = {}
            sig = inspect.signature(fn)
            if "device" in sig.parameters:
                kwargs["device"] = "cpu"
            return fn(
                str(specs[0].get("clip_name", "")),
                str(specs[1].get("clip_name", "")),
                str(specs[0].get("type", "stable_diffusion")),
                **kwargs,
            )
    except Exception:
        return None
    return None


def _resolve_param(module: Any, dotted: str) -> Any:
    obj = module
    parts = str(dotted).split(".")
    try:
        for part in parts:
            obj = getattr(obj, part)
    except Exception:
        return None
    return obj


def _replace_param(module: Any, dotted: str, tensor: Any, requires_grad: bool) -> bool:
    parts = str(dotted).split(".")
    if len(parts) < 1:
        return False
    owner = module
    try:
        for part in parts[:-1]:
            owner = getattr(owner, part)
        setattr(
            owner,
            parts[-1],
            torch.nn.Parameter(tensor.detach().clone(), requires_grad=requires_grad),
        )
        return True
    except Exception:
        return False


def _hydrate_native_copy(
    clip: Any, manifest: dict, *, trace: Any = None, comfy_utils: Any = None
) -> dict[str, Any]:
    """Last-resort reconstruction: fresh native load once, then move its
    weights into the restored structure in place via parameter replacement
    (object identity of the clip/patcher preserved so graph references stay
    valid; meta placeholder parameters are replaced, not copied into)."""
    import torch

    state_before = cfh.clip_hydration_state(clip)["state"]
    try:
        specs = manifest.get("loader_specs") or []
        native = _invoke_native_clip_loader(specs)
        if native is None:
            raise RuntimeError("native loader unavailable or loader specs absent")
        count = 0
        with torch.no_grad():
            for name, param in native.cond_stage_model.named_parameters():
                ours = _resolve_param(clip.cond_stage_model, name)
                if ours is None:
                    continue
                data = param.detach().to(dtype=ours.dtype, device="cpu")
                if _replace_param(clip.cond_stage_model, name, data, bool(ours.requires_grad)):
                    count += 1
        cfh.mark_clip_hydrated(clip)
        result = {
            "ok": True,
            "mode": cfh.MODE_NATIVE,
            "reconstruction": "native_copy",
            "params_copied": count,
            "fallback_count": 1,
        }
        _emit(trace, "clip_fh_hydration_end", result)
        _emit_decision(
            trace,
            decision="native_fallback",
            reason="native_copy",
            state_before=state_before,
            state_after=cfh.clip_hydration_state(clip)["state"],
        )
        return result
    except Exception as exc:
        result = {
            "ok": False,
            "mode": cfh.MODE_NATIVE,
            "reason": f"{type(exc).__name__}: {str(exc)[:160]}",
            "fallback_count": 1,
        }
        _emit(trace, "clip_fh_hydration_end", result)
        _emit_decision(
            trace,
            decision="native_copy_fallback",
            reason=f"{type(exc).__name__}: {str(exc)[:160]}",
            state_before=state_before,
            state_after=cfh.clip_hydration_state(clip)["state"],
        )
        return result


def _record_mode(
    clip: Any,
    mode: str,
    info: dict[str, Any],
    *,
    state_before: Optional[str] = None,
    state_after: Optional[str] = None,
) -> dict[str, Any]:
    rid = _request_id()
    rec = _RECORD.setdefault(
        rid, {"mode": None, "fallback_count": 0, "hydrated": False, "last": None}
    )
    rec["mode"] = mode
    rec["fallback_count"] += int(info.get("fallback_count", 0) or 0)
    if info.get("ok"):
        rec["hydrated"] = True
    entry = dict(info)
    if state_before is not None:
        entry["state_before"] = state_before
    if state_after is not None:
        entry["state_after"] = state_after
    rec["last"] = entry
    _note_clip(clip)
    try:
        from comfymodal_runtime.fast_cold_orchestration import (
            record_loader_execution_identity,
        )
        from comfymodal_runtime.model_preload import _ACTIVE_REQUEST_TRACE

        _trace = _ACTIVE_REQUEST_TRACE.get()
        _identity = {
            cfh.MODE_FASTSAFE: "fastsafetensors_direct_gpu",
            cfh.MODE_STAGED: "staged",
            cfh.MODE_NATIVE: "native",
            cfh.MODE_RESIDENT: "resident",
            cfh.MODE_CACHE_HIT: "cache_hit",
        }.get(mode, str(mode))
        record_loader_execution_identity(
            "clip",
            _identity,
            trace=_trace,
            fallback=bool(info.get("fallback_count", 0) or 0),
        )
    except Exception:
        pass
    return {"mode": mode, "request_id": rid, **entry}


def _staged_core() -> Any:
    try:
        from comfymodal_runtime import staged_safetensors

        return staged_safetensors
    except Exception:
        try:
            import staged_safetensors

            return staged_safetensors
        except Exception:
            return None


def _stage_fields(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    try:
        return dict(vars(value))
    except Exception:
        return {}


def _stage_method(core: Any, phase: str, previous: Any = None) -> Any:
    method = getattr(core, phase, None)
    if callable(method):
        return method
    method = getattr(previous, phase, None)
    return method if callable(method) else None


def _invoke_stage_method(method: Any, phase: str, values: dict[str, Any]) -> Any:
    fallback = {
        "plan": values.get("paths"),
        "prepare": values.get("plan"),
        "commit": values.get("prepared"),
        "result": values.get("committed"),
    }[phase]
    try:
        signature = inspect.signature(method)
    except (TypeError, ValueError):
        return method(fallback)
    args: list[Any] = []
    kwargs: dict[str, Any] = {}
    has_var_kwargs = False
    for parameter in signature.parameters.values():
        if parameter.name in ("self", "cls"):
            continue
        if parameter.kind is inspect.Parameter.VAR_KEYWORD:
            has_var_kwargs = True
            continue
        if parameter.kind is inspect.Parameter.VAR_POSITIONAL:
            continue
        if parameter.name in values:
            value = values[parameter.name]
        elif parameter.default is not inspect.Parameter.empty:
            continue
        else:
            value = fallback
        if parameter.kind is inspect.Parameter.POSITIONAL_ONLY:
            args.append(value)
        else:
            kwargs[parameter.name] = value
    if has_var_kwargs:
        kwargs.update(values)
    return method(*args, **kwargs)


def _stage_tensor_dicts(value: Any) -> Optional[list[dict]]:
    if isinstance(value, Mapping):
        if value and all(isinstance(item, torch.Tensor) for item in value.values()):
            return [dict(value)]
        for key in ("state_dict", "state_dicts", "per_file_sds", "sds", "tensors"):
            if key in value:
                found = _stage_tensor_dicts(value[key])
                if found is not None:
                    return found
        for key in ("result", "committed", "prepared"):
            if key in value:
                found = _stage_tensor_dicts(value[key])
                if found is not None:
                    return found
        return None
    if isinstance(value, (tuple, list)):
        for item in value:
            found = _stage_tensor_dicts(item)
            if found:
                return found
        if value and all(isinstance(item, Mapping) for item in value):
            if all(
                all(isinstance(tensor, torch.Tensor) for tensor in item.values())
                for item in value
            ):
                return [dict(item) for item in value]
        for item in value:
            found = _stage_tensor_dicts(item)
            if found is not None:
                return found
    for key in ("state_dict", "state_dicts", "per_file_sds", "sds", "tensors", "result"):
        child = getattr(value, key, None)
        if child is not None:
            found = _stage_tensor_dicts(child)
            if found is not None:
                return found
    return None


def _stage_owners(value: Any) -> list[Any]:
    if isinstance(value, Mapping):
        for key in ("owners", "owner", "storage_owner", "handles"):
            if key in value:
                child = value[key]
                if child is None:
                    return []
                return list(child) if isinstance(child, (tuple, list)) else [child]
        for key in ("result", "committed"):
            if key in value:
                found = _stage_owners(value[key])
                if found:
                    return found
    for key in ("owners", "owner", "storage_owner", "handles"):
        child = getattr(value, key, None)
        if child is not None:
            return list(child) if isinstance(child, (tuple, list)) else [child]
    for key in ("_owner", "_gpu_owner"):
        child = getattr(value, key, None)
        if child is not None:
            return [child]
    return []


def _add_stage_owners(target: list[Any], value: Any) -> None:
    for owner in _stage_owners(value):
        if all(existing is not owner for existing in target):
            target.append(owner)


def _stage_metrics(value: Any) -> dict[str, Any]:
    metrics: dict[str, Any] = {}
    if isinstance(value, Mapping):
        metrics.update(value)
        for key in ("metrics", "telemetry", "timings", "result", "committed"):
            child = value.get(key)
            if isinstance(child, Mapping):
                metrics.update(child)
    else:
        metrics.update(_stage_fields(value))
        reported = getattr(value, "metrics", None)
        if callable(reported):
            try:
                reported = reported()
            except Exception:
                reported = None
        if isinstance(reported, Mapping):
            metrics.update(reported)
    return metrics


def _stage_metric(metrics: dict[str, Any], *names: str) -> Any:
    for name in names:
        if name in metrics and metrics[name] is not None:
            return metrics[name]
    return None


def _close_stage_owner(owner: Any) -> None:
    if owner is None:
        return
    if isinstance(owner, (tuple, list)):
        for item in owner:
            _close_stage_owner(item)
        return
    close = getattr(owner, "close", None)
    if callable(close):
        try:
            close()
        except Exception:
            pass


def _detach_stage_owners(value: Any) -> None:
    for name in ("_owner", "_gpu_owner"):
        if hasattr(value, name):
            try:
                setattr(value, name, None)
            except Exception:
                pass


def _stage_target_device(clip: Any, state_dicts: Optional[list[dict]] = None) -> str:
    patcher = getattr(clip, "patcher", None)
    device = getattr(patcher, "load_device", None)
    if device is not None:
        return str(device)
    for state_dict in state_dicts or []:
        for tensor in state_dict.values():
            if isinstance(tensor, torch.Tensor):
                return str(tensor.device)
    return "cuda:0"


def _try_staged_hydrate(
    clip: Any, manifest: dict, *, trace: Any = None, comfy_utils: Any = None
) -> dict[str, Any]:
    t0 = time.perf_counter()
    timings: dict[str, Any] = {
        "clip_staged_prepare_ms": None,
        "clip_staged_commit_ms": None,
        "clip_staged_h2d_ms": None,
        "clip_staged_bind_ms": None,
        "clip_staged_fallback_reason": "",
    }
    owners: list[Any] = []
    try:
        core = _staged_core()
        if core is None:
            raise RuntimeError("staged_safetensors unavailable")
        file_entries = list(manifest.get("files") or [])
        paths = [str(entry.get("path", "")) for entry in file_entries]
        values = {
            "paths": paths,
            "files": paths,
            "file_paths": paths,
            "file_manifests": file_entries,
            "file_manifest": file_entries,
            "manifest": manifest,
            "metadata": manifest,
            "clip": clip,
            "target_device": _stage_target_device(clip),
            "device": _stage_target_device(clip),
        }
        plan_method = _stage_method(core, "plan")
        if plan_method is None:
            raise RuntimeError("staged_safetensors.plan unavailable")
        plan = _invoke_stage_method(plan_method, "plan", values)
        plan_fields = _stage_fields(plan)
        if plan_fields.get("eligible") is False:
            raise RuntimeError(str(plan_fields.get("reason") or "staged plan ineligible"))

        prepare_method = _stage_method(core, "prepare", plan)
        if prepare_method is None:
            raise RuntimeError("staged_safetensors.prepare unavailable")
        values.update({"plan": plan, "staged_plan": plan})
        t_prepare = time.perf_counter()
        prepared = _invoke_stage_method(prepare_method, "prepare", values)
        _add_stage_owners(owners, prepared)
        timings["clip_staged_prepare_ms"] = round(
            (time.perf_counter() - t_prepare) * 1000.0, 3
        )

        commit_method = _stage_method(core, "commit", prepared)
        if commit_method is None:
            raise RuntimeError("staged_safetensors.commit unavailable")
        values.update({"prepared": prepared, "preparation": prepared})
        t_commit = time.perf_counter()
        committed = _invoke_stage_method(commit_method, "commit", values)
        _add_stage_owners(owners, committed)
        timings["clip_staged_commit_ms"] = round(
            (time.perf_counter() - t_commit) * 1000.0, 3
        )

        result_method = _stage_method(core, "result", committed)
        if result_method is None:
            raise RuntimeError("staged_safetensors.result unavailable")
        values.update({"committed": committed, "commit_result": committed})
        result = _invoke_stage_method(result_method, "result", values)
        result_fields = _stage_metrics(committed)
        result_fields.update(_stage_metrics(result))
        _add_stage_owners(owners, result)
        if result_fields.get("success") is not True:
            reason = (
                result_fields.get("fallback_reason")
                or result_fields.get("error")
                or result_fields.get("reason")
                or "staged result success flag missing"
            )
            raise RuntimeError(str(reason))
        reported_prepare_ms = _stage_metric(
            result_fields, "clip_staged_prepare_ms", "prepare_ms"
        )
        if reported_prepare_ms is not None:
            timings["clip_staged_prepare_ms"] = reported_prepare_ms
        reported_commit_ms = _stage_metric(
            result_fields, "clip_staged_commit_ms", "commit_ms"
        )
        if reported_commit_ms is not None:
            timings["clip_staged_commit_ms"] = reported_commit_ms
        state_dicts = _stage_tensor_dicts(result)
        if state_dicts is None:
            state_dicts = _stage_tensor_dicts(committed)
        if not state_dicts:
            raise RuntimeError("staged result contained no tensor state dicts")
        file_entries = list(manifest.get("files") or [])
        if len(state_dicts) != len(file_entries):
            raise RuntimeError(
                f"staged result state dict count mismatch: got {len(state_dicts)} "
                f"expected {len(file_entries)}"
            )
        transformed_state_dicts: list[dict[str, Any]] = []
        for file_manifest, state_dict in zip(file_entries, state_dicts):
            if not state_dict or not all(
                isinstance(tensor, torch.Tensor) for tensor in state_dict.values()
            ):
                raise RuntimeError(
                    "staged result contained an incomplete tensor state dict"
                )
            transformed = _apply_pipeline(
                dict(state_dict),
                file_manifest.get("pipeline", []),
                comfy_utils=comfy_utils,
            )
            ok, detail = _verify_file_against_manifest(file_manifest, transformed)
            if not ok:
                raise RuntimeError(detail)
            transformed_state_dicts.append(transformed)
        state_dicts = transformed_state_dicts
        for name in (
            "checkpoint_bytes",
            "disk_to_stage_ms",
            "cpu_cast_ms",
            "cpu_cast_bytes",
            "exact_copy_bytes",
            "h2d_enqueue_ms",
            "h2d_device_ms",
            "effective_h2d_gbps",
            "producer_wait_ms",
            "consumer_wait_ms",
            "peak_pinned_bytes",
            "pinned_fast_path_active",
            "contiguous_gpu_buckets_active",
            "native_pin_budget_available",
            "local_bounded_budget_used",
            "native_pin_budget_rejected",
            "host_slab_is_pinned",
            "host_slab_is_pinned_all",
            "host_slab_is_pinned_per_slot",
            "bucket_bytes",
            "host_bucket_bytes_configured",
            "host_slab_count",
            "gpu_bucket_count",
            "packed_model_bytes",
            "h2d_bucket_count",
            "h2d_full_bucket_count",
            "h2d_final_bucket_bytes",
            "min_h2d_copy_bytes",
            "median_h2d_copy_bytes",
            "max_h2d_copy_bytes",
            "h2d_stream_span_ms",
            "h2d_dma_busy_ms",
            "h2d_stream_idle_estimate_ms",
            "h2d_dma_gbps",
            "h2d_span_gbps",
            "slab_reuse_wait_ms",
            "tensor_count",
            "producer_count",
            "copy_count",
            "non_blocking",
            "stream_count",
            "source_read_ms",
            "source_materialization_ms",
            "bucket_pack_cpu_ms",
            "bucket_ready_wait_ms",
            "source_order_enabled",
            "source_order_eligible",
            "source_order_fallback_reason",
            "source_file_count",
            "source_tensor_count",
            "source_model_bytes",
            "source_read_calls",
            "source_read_min_bytes",
            "source_read_median_bytes",
            "source_read_max_bytes",
            "source_sequential_bytes",
            "source_repack_bytes",
            "source_read_wall_ms",
            "source_read_worker_accumulated_ms",
            "source_to_pinned_copy_bytes",
            "source_to_pinned_copy_ms",
            "alignment_fallback_tensor_count",
        ):
            value = _stage_metric(result_fields, name)
            if value is not None:
                timings[name] = value
        timings["clip_staged_h2d_ms"] = _stage_metric(
            result_fields,
            "clip_staged_h2d_ms",
            "h2d_device_ms",
            "h2d_enqueue_ms",
            "h2d_ms",
            "h2d_wall_ms",
            "transfer_ms",
        )
        t_bind = time.perf_counter()
        expected_device = _stage_target_device(clip, state_dicts)
        ok, evidence = cfh.hydrate_clip_bind(
            clip,
            state_dicts,
            require_no_meta=True,
            expect_device=expected_device,
        )
        timings["clip_staged_bind_ms"] = round(
            (time.perf_counter() - t_bind) * 1000.0, 3
        )
        timings["bind_ms"] = timings["clip_staged_bind_ms"]
        if not ok:
            raise RuntimeError(f"bind: {evidence}")
        if not owners or any(getattr(owner, "_closed", False) for owner in owners):
            raise RuntimeError("staged result owner was not live through bind")
        for owner in owners:
            cfh.staged_owner_attach(clip, owner)
        _detach_stage_owners(committed)
        _detach_stage_owners(result)
        cfh.mark_clip_hydrated(clip)
        timings["clip_staged_fallback_reason"] = ""
        outcome = {
            "ok": True,
            "mode": cfh.MODE_STAGED,
            "fallback_count": 0,
            "wall_ms": round((time.perf_counter() - t0) * 1000.0, 3),
            "zero_copy": True,
            "zero_copy_evidence": evidence,
            "owner_mode": "staged_safetensors",
            **timings,
        }
        _emit(trace, "clip_staged_hydration", outcome)
        _emit(trace, "clip_fh_hydration_end", outcome)
        return outcome
    except Exception as exc:
        for owner in owners:
            _close_stage_owner(owner)
        reason = f"{type(exc).__name__}: {str(exc)[:160]}"
        timings["clip_staged_fallback_reason"] = reason
        outcome = {
            "ok": False,
            "mode": cfh.MODE_STAGED,
            "fallback_count": 0,
            "wall_ms": round((time.perf_counter() - t0) * 1000.0, 3),
            **timings,
        }
        _emit(trace, "clip_staged_hydration", outcome)
        return outcome


def _merge_staged_telemetry(result: dict[str, Any], staged: Optional[dict[str, Any]]) -> dict[str, Any]:
    if not staged:
        return result
    for key in (
        "clip_staged_prepare_ms",
        "clip_staged_commit_ms",
        "clip_staged_h2d_ms",
        "clip_staged_bind_ms",
        "clip_staged_fallback_reason",
    ):
        if key in staged:
            result[key] = staged[key]
    return result


def _hydrate_clip_on_demand(
    clip: Any, *, trace: Any = None, comfy_utils: Any = None
) -> dict[str, Any]:
    """Demand-time hydrator invoked by the CLIP.load_model wrapper.

    Every branch records a ``clip_fh_hydration_decision`` event BEFORE acting
    (decision/reason/state_before/state_detail/fast_hydration_allowed/
    weights_excluded), plus a ``clip_state_checkpoint`` at entry.  The
    semantic invariant from the D6 corrected run: a fully CPU-materialized
    clip (no hydration marker) is NEVER silently skipped as already hydrated —
    it proceeds through hydration and records
    cpu_materialized_requires_hydration (state_before CPU_NATIVE_MATERIALIZED).
    """
    state = cfh.clip_hydration_state(clip)
    state_before = state["state"]
    state_detail = _state_detail(state)
    manifest = cfh.get_clip_manifest(clip)
    fast_allowed = bool((manifest or {}).get("fast_hydration_allowed", False))
    excluded = bool(state.get("excluded_marker")) or cfh.clip_weights_excluded(clip)
    clip_state_checkpoint(trace, "clip_hydration_decision", clip)
    if manifest is None or not manifest.get("eligible"):
        _emit_decision(
            trace,
            decision="no_manifest",
            reason="no_manifest",
            state_before=state_before,
            state_detail=state_detail,
            fast_hydration_allowed=fast_allowed,
            weights_excluded=excluded,
        )
        return _record_mode(
            clip,
            cfh.MODE_NATIVE,
            {"ok": True, "reason": "no_manifest"},
            state_before=state_before,
            state_after=state_before,
        )
    if cfh.clip_hydrated(clip):
        _emit_decision(
            trace,
            decision="already_hydrated",
            reason="hydrated_marker_set",
            state_before=state_before,
            state_detail=state_detail,
            fast_hydration_allowed=fast_allowed,
            weights_excluded=excluded,
        )
        return _record_mode(
            clip,
            cfh.MODE_RESIDENT,
            {"ok": True, "reason": "already_hydrated"},
            state_before=state_before,
            state_after=state_before,
        )
    staged_allowed = bool(
        (manifest or {}).get("staged_hydration_allowed", clip_staged_hydration_enabled())
    )
    staged_failure: Optional[dict[str, Any]] = None
    result: dict[str, Any] = {}
    if excluded and staged_allowed and clip_staged_hydration_enabled():
        _emit_decision(
            trace,
            decision="staged_path",
            reason="staged_hydration_allowed",
            state_before=state_before,
            state_detail=state_detail,
            fast_hydration_allowed=fast_allowed,
            weights_excluded=excluded,
        )
        staged_result = _try_staged_hydrate(
            clip, manifest, trace=trace, comfy_utils=comfy_utils
        )
        if staged_result.get("ok"):
            state_after = cfh.clip_hydration_state(clip)["state"]
            return _record_mode(
                clip,
                cfh.MODE_STAGED,
                staged_result,
                state_before=state_before,
                state_after=state_after,
            )
        staged_failure = staged_result
        _emit_decision(
            trace,
            decision="fast_path",
            reason="staged_path_failed",
            state_before=state_before,
            state_detail=state_detail,
            fast_hydration_allowed=fast_allowed,
            weights_excluded=excluded,
        )
        result = _try_fast_hydrate(
            clip, manifest, trace=trace, comfy_utils=comfy_utils
        )
        _merge_staged_telemetry(result, staged_failure)
    elif not fast_allowed:
        _emit_decision(
            trace,
            decision="cpu_assign_fallback",
            reason="fast_hydration_disallowed",
            state_before=state_before,
            state_detail=state_detail,
            fast_hydration_allowed=fast_allowed,
            weights_excluded=excluded,
        )
        result = _hydrate_cpu_assign(clip, manifest, trace=trace, comfy_utils=comfy_utils)
        _merge_staged_telemetry(result, staged_failure)
        state_after = cfh.clip_hydration_state(clip)["state"]
        return _record_mode(
            clip,
            result.get("mode", cfh.MODE_NATIVE),
            result,
            state_before=state_before,
            state_after=state_after,
        )
    if staged_failure is None:
        _emit_decision(
            trace,
            decision="fast_path",
            reason="fast_hydration_allowed",
            state_before=state_before,
            state_detail=state_detail,
            fast_hydration_allowed=fast_allowed,
            weights_excluded=excluded,
        )
        result = _try_fast_hydrate(
            clip, manifest, trace=trace, comfy_utils=comfy_utils
        )
    if result.get("ok"):
        state_after = cfh.clip_hydration_state(clip)["state"]
        return _record_mode(
            clip,
            result.get("mode", cfh.MODE_FASTSAFE),
            result,
            state_before=state_before,
            state_after=state_after,
        )
    if excluded:
        _emit_decision(
            trace,
            decision="cpu_assign_fallback",
            reason="fast_path_failed_excluded",
            state_before=state_before,
            state_detail=state_detail,
            fast_hydration_allowed=fast_allowed,
            weights_excluded=excluded,
        )
        result = _hydrate_cpu_assign(clip, manifest, trace=trace, comfy_utils=comfy_utils)
        _merge_staged_telemetry(result, staged_failure)
        state_after = cfh.clip_hydration_state(clip)["state"]
        return _record_mode(
            clip,
            result.get("mode", cfh.MODE_NATIVE),
            result,
            state_before=state_before,
            state_after=state_after,
        )
    _emit_decision(
        trace,
        decision="native_record",
        reason="fast_path_failed_not_excluded",
        state_before=state_before,
        state_detail=state_detail,
        fast_hydration_allowed=fast_allowed,
        weights_excluded=excluded,
    )
    return _record_mode(
        clip,
        cfh.MODE_NATIVE,
        result,
        state_before=state_before,
        state_after=state_before,
    )


def maybe_install_clip_fh_demand(
    cpu_models: Any, *, trace: Any = None, comfy_utils: Any = None
) -> dict[str, Any]:
    """Install the demand-time hydration wrapper on the restored/served CLIP.

    Called from startup (after capture) and restore (after snapshot state
    init).  Idempotent.  Without a frozen manifest the wrapper is NOT
    installed — the native path runs untouched (fail closed).
    """
    clip = getattr(cpu_models, "clip", None)
    if clip is None:
        return {"status": "no_clip"}
    if not (
        clip_fast_hydration_enabled()
        or clip_staged_hydration_enabled()
        or clip_snapshot_exclude_weights_enabled()
    ):
        try:
            coordination_status = cfh.install_gpu_critical_coordination(clip)
        except Exception:
            coordination_status = "unavailable"
        return {"status": "disabled", "coordination": coordination_status}
    _note_excluded(_request_id(), cfh.clip_weights_excluded(clip), clip)
    manifest = cfh.get_clip_manifest(clip)
    if manifest is None or not manifest.get("eligible"):
        try:
            coordination_status = cfh.install_gpu_critical_coordination(clip)
        except Exception:
            coordination_status = "unavailable"
        return {"status": "no_manifest", "coordination": coordination_status}
    if getattr(clip, cfh.DEMAND_WRAPPER_MARKER, False):
        coordination_status = cfh.install_gpu_critical_coordination(clip)
        return {"status": "already_wrapped", "coordination": coordination_status}

    def _hydrator(c: Any) -> None:
        _hydrate_clip_on_demand(c, trace=trace, comfy_utils=comfy_utils)

    clip_state_checkpoint(trace, "clip_fh_pre_install", clip)
    installed = cfh.install_demand_wrapper(clip, _hydrator)
    if not installed:
        return {"status": "wrap_failed"}
    coordination_status = cfh.install_gpu_critical_coordination(clip)
    global _ACTIVE_TRACE
    _ACTIVE_TRACE = trace
    clip_state_checkpoint(trace, "clip_fh_post_install", clip)
    _emit(
        trace,
        "clip_fh_install",
        {
            "status": "installed",
            "mode_candidates": [
                cfh.MODE_STAGED,
                cfh.MODE_FASTSAFE,
                cfh.MODE_NATIVE,
                cfh.MODE_RESIDENT,
                cfh.MODE_CACHE_HIT,
            ],
        },
    )
    return {"status": "installed", "coordination": coordination_status}


def clip_fh_request_summary(request_id: str = "") -> dict[str, Any]:
    """Per-request hydration attribution.

    TRAP: when no demand was ever recorded, the mode resolves to
    ``already_resident`` (or ``conditioning_cache_hit_no_hydration`` for an
    excluded clip) — that is the DEFAULT, NOT proof that the demand wrapper
    ran.  ``state`` (from clip_hydration_state) is attached whenever a clip
    is available so consumers can distinguish a genuinely GPU-resident model
    (GPU_FAST_HYDRATED / GPU_NATIVE_LOADED) from a CPU-materialized model
    that was never hydrated (CPU_NATIVE_MATERIALIZED) — the exact D6 failure
    class.
    """
    rid = request_id or _request_id()
    rec = _RECORD.get(rid) or {}
    mode = rec.get("mode")
    if mode is None:
        mode = cfh.MODE_CACHE_HIT if _last_excluded() else cfh.MODE_RESIDENT
    result = {
        "request_id": rid,
        "hydration_source": mode,
        "hydrated": bool(rec.get("hydrated", False)),
        "fallback_count": int(rec.get("fallback_count", 0) or 0),
        "last": rec.get("last"),
    }
    # ``_LAST_CLIP`` is a weakref.ref (stored by ``_note_clip`` so the
    # capture/eviction lifecycle is never rooted); dereference safely.  A raw
    # object fallback is kept for defensive compatibility with any direct
    # assignment — production code always stores a weakref.
    _clip_ref = _LAST_CLIP
    if isinstance(_clip_ref, weakref.ref):
        clip = _clip_ref()
    else:
        clip = _clip_ref
    if clip is not None:
        try:
            result["state"] = cfh.clip_hydration_state(clip)["state"]
        except Exception:
            pass
    return result


_LAST_EXCLUDED: dict[str, bool] = {}


def _note_excluded(rid: str, excluded: bool, clip: Any = None) -> None:
    _LAST_EXCLUDED[rid] = excluded
    if clip is not None:
        _note_clip(clip)


def _last_excluded() -> bool:
    rid = _request_id()
    return bool(_LAST_EXCLUDED.get(rid, False))
