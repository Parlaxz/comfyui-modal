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
from comfymodal_runtime import clean_lane
from comfymodal_runtime import production_m2_loader as _m2_loader

_FLAG_FAST = "COMFYMODAL_V2_CLIP_FAST_HYDRATION"
_FLAG_STAGED = "COMFYMODAL_V2_CLIP_STAGED_HYDRATION"
_FLAG_EXCLUDE = "COMFYMODAL_V2_CLIP_SNAPSHOT_EXCLUDE_WEIGHTS"
_FLAG_M2 = "COMFYMODAL_V2_M2_PRODUCTION_LOADER"

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

CLIP_LOADER_START = "clip_loader_start"
CLIP_DEVICE_READY = "clip_device_ready"


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


def _close_source_owners(owners: Any) -> dict[str, Any]:
    """Failure cleanup with explicit destructive-close diagnostics.

    ``release_storage``/``free_storage``/``release_buffer`` are
    non-destructive ownership APIs and are called only with their explicit
    no-purge contract.  A ``TypeError`` is not a reason to retry them without
    that contract: it may be an implementation failure, not a signature
    mismatch.  ``close()`` is the sole no-argument fallback and is used only
    for this destructive failure-cleanup path.
    """
    errors: list[str] = []
    closed = 0
    for owner in list(owners or []):
        components = tuple(owner) if isinstance(owner, (tuple, list)) else (owner,)
        for component in components:
            if component is None:
                continue
            released = False
            for name in ("release_storage", "free_storage", "release_buffer", "release"):
                method = getattr(component, name, None)
                if not callable(method):
                    continue
                try:
                    method(purge_allocator=False)
                    released = True
                except Exception as exc:
                    errors.append(
                        f"{type(component).__name__}.{name}: "
                        f"{type(exc).__name__}: {str(exc)[:120]}"
                    )
                break
            if released:
                closed += 1
                continue
            close = getattr(component, "close", None)
            if callable(close):
                try:
                    # Explicitly destructive failure cleanup; never use this
                    # no-arg call as a retry for a non-destructive API.
                    close()
                    closed += 1
                except Exception as exc:
                    errors.append(
                        f"{type(component).__name__}.close: "
                        f"{type(exc).__name__}: {str(exc)[:120]}"
                    )
            else:
                errors.append(f"{type(component).__name__}: no cleanup API")
    return {"ok": not errors, "closed": closed, "errors": errors}


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


def _emit_clip_loader_endpoint(
    trace: Any,
    name: str,
    *,
    endpoint_role: str,
    loader_arm: str,
) -> int:
    """Stamp one common CLIP loader boundary on both telemetry axes.

    The timestamp is captured once from ``time.monotonic_ns`` and passed
    unchanged to the trace and canonical ledger.  This seam is deliberately
    independent of the QD reader so FASTSAFE and speculative/QD loads share
    endpoint semantics without one being derived from the other.
    """
    mono_ns = int(time.monotonic_ns())
    payload: dict[str, Any] = {
        "endpoint_role": str(endpoint_role),
        "semantic_endpoint_role": str(endpoint_role),
        "clock": "monotonic_ns",
        "clock_source": "time.monotonic_ns",
        "monotonic_ns": mono_ns,
        "loader_arm": str(loader_arm),
        "hydration_source": str(loader_arm),
        "request_id": _request_id(),
    }
    wall_ns = int(time.time_ns())
    if trace is not None:
        try:
            if hasattr(trace, "emit_at"):
                trace.emit_at(
                    name,
                    wall_unix_ns=wall_ns,
                    monotonic_ns=mono_ns,
                    phase="execution",
                    metadata=dict(payload),
                )
            elif hasattr(trace, "emit"):
                trace.emit(name, phase="execution", metadata=dict(payload))
        except Exception:
            pass
    try:
        from .critical_path_ledger import record_event

        record_event(name, mono_ns=mono_ns, wall_ns=wall_ns, metadata=payload)
    except Exception:
        pass
    return mono_ns


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


def _model_structural_destination_keys(
    clip: Any, expected_keys: set[str]
) -> list[str]:
    """Compatibility wrapper for the RA9G-owned structural-key helper."""
    from comfymodal_runtime import clip_fp32_cast_once as ra9g

    return ra9g.discover_structural_destination_keys(clip, expected_keys)


def _authoritative_clip_manifest_fields(clip: Any, cpu_models: Any) -> dict[str, Any]:
    """Copy identity fields already supplied by the snapshot/model provider.

    This function is deliberately not an identity generator: object ids,
    paths, sizes, mtimes, and locally computed hashes are never promoted to
    source identity.
    """
    result: dict[str, Any] = {}
    model_key = getattr(cpu_models, "model_key", None)
    loader_options = getattr(model_key, "optimization_loader_options", {}) or {}
    candidates = {
        "checkpoint_identity": (
            getattr(model_key, "clip_identity", None)
            or getattr(clip, "checkpoint_identity", None)
            or getattr(clip, "source_identity", None)
        ),
        "manifest_generation": (
            getattr(model_key, "model_volume_generation", None)
            or getattr(clip, "manifest_generation", None)
            or getattr(clip, "content_generation", None)
        ),
        "selected_tensor_scope": (
            getattr(clip, "selected_tensor_scope", None)
            or getattr(model_key, "clip_type", None)
        ),
        "model_patch_identity": (
            getattr(clip, "model_patch_identity", None)
            or (loader_options.get("model_patch_identity") if isinstance(loader_options, Mapping) else None)
        ),
    }
    target_gpus = getattr(cpu_models, "target_gpus", ()) or ()
    candidates["target_device"] = (
        getattr(clip, "target_device", None)
        or (target_gpus[0] if target_gpus else None)
    )
    for key, value in candidates.items():
        if isinstance(value, (str, int, bool)) and str(value):
            result[key] = value
    return result


def _build_manifest(
    clip: Any, paths: list[str], comfy_utils: Any = None,
    *, authoritative_fields: Optional[Mapping[str, Any]] = None,
) -> Optional[dict]:
    import torch

    import safetensors.torch

    if not paths:
        return None
    if getattr(clip, "cond_stage_model", None) is None:
        return None
    files: list[dict[str, Any]] = []
    reasons: list[str] = []
    for file_index, path in enumerate(paths):
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
                    # Index in the accepted manifest/files list (not the
                    # original path list, which may contain skipped files).
                    "file_index": int(len(files)),
                    "path": path,
                    "size_bytes": int(os.path.getsize(path)),
                    "mtime_ns": int(os.path.getmtime(path) * 1_000_000_000),
                    "dtype": str(next(iter(dtypes))),
                    "key_set": sorted(transformed.keys()),
                    "key_shapes": {k: list(v.shape) for k, v in transformed.items()},
                    "expected_count": len(transformed),
                    "expected_bytes": sum(int(v.numel()) * 4 for v in transformed.values()),
                    "pipeline": pipeline,
                    "non_tensor_entries": non_tensor,
                    "quant_metadata_present": bool(metadata.get("_quantization_metadata")),
                }
            )
        except Exception as exc:
            reasons.append(f"{os.path.basename(path)}: {type(exc).__name__}: {str(exc)[:120]}")
    if not files:
        return {"eligible": False, "reason": "; ".join(reasons) or "no usable files"}
    structural_destination_keys = _model_structural_destination_keys(
        clip, {key for entry in files for key in entry["key_set"]}
    )
    # Store this on each frozen file entry because E31's proof contract
    # receives the authoritative ``files`` list, not the enclosing manifest.
    for entry in files:
        entry["structural_destination_keys"] = list(structural_destination_keys)
    per_file_key_sets = [set(f["key_set"]) for f in files]
    routing_ok, routing_detail = cfh.verify_leaf_routing(clip, per_file_key_sets)
    assign_ok, assign_detail = cfh.can_assign_sd_supported(clip)
    if not routing_ok:
        return {"eligible": False, "reason": f"routing: {routing_detail}"}
    if not assign_ok:
        return {"eligible": False, "reason": f"can_assign_sd: {assign_detail}"}
    result = {
        "schema": 1,
        "eligible": True,
        "reason": "capability gates passed at capture",
        "files": files,
        "structural_destination_keys": list(structural_destination_keys),
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
    for key, value in (authoritative_fields or {}).items():
        if key not in result and isinstance(value, (str, int, bool)) and str(value):
            result[key] = value
    return result


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
        manifest = _build_manifest(
            clip,
            _clip_file_paths(cpu_models),
            comfy_utils=comfy_utils,
            authoritative_fields=_authoritative_clip_manifest_fields(clip, cpu_models),
        )
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


def _e31_forward_hook(
    clip: Any,
    per_file_sds: Optional[list[dict]] = None,
    files: Optional[list[dict]] = None,
    *,
    expect_device: Optional[str],
    bind_snapshot: dict[str, Any],
    trace: Any = None,
) -> dict[str, Any]:
    """Arm E31 proof on the existing outer forward boundary.

    The demand hydrator is called from inside the first encode request.  A new
    method wrapper installed here would miss that in-flight call, so the
    production path registers a generation-scoped callback consumed by
    ``model_preload``'s existing outer ``encode_token_weights`` wrapper.  The
    direct method-hook fallback is retained only for small offline fakes that
    do not have the production outer wrapper.
    """
    from .clip_fp32_cast_once import (
        cast_once_enabled,
        compare_resident_fp32,
        install_real_forward_check,
        snapshot_adopted_storage,
        snapshot_resident_fp32,
    )

    import importlib

    ff = importlib.import_module("comfymodal_runtime.clip_forward_forensics")
    strict_e31 = bool(cast_once_enabled())
    installation_evidence = []
    try:
        installation_evidence = list(ff.cast_installation_evidence())
    except Exception:
        installation_evidence = []
    required_cast_surfaces = (
        ("comfy.ops", "cast_bias_weight"),
        ("comfy.model_management", "cast_to"),
        ("comfy.model_management", "cast_to_device"),
    )

    def _surface_matches(entry: dict[str, Any], module_name: str, attr: str) -> bool:
        observed_module = str(entry.get("module", ""))
        return (
            str(entry.get("attribute", "")) == attr
            and (observed_module == module_name or observed_module.endswith("." + module_name.rsplit(".", 1)[-1]))
            and bool(entry.get("wrapped"))
            # ``wrapped`` is only accepted as installation evidence when the
            # audit also identified the live callable and a successful
            # install/idempotent status.  This keeps a stale or partial
            # evidence record from becoming a strict success claim.
            and entry.get("callable_identity") is not None
            and str(entry.get("status", "")) in {"installed", "already", "alias"}
        )

    canonical_cast_surfaces = {
        f"{module_name}.{attr}": any(
            isinstance(entry, dict) and _surface_matches(entry, module_name, attr)
            for entry in installation_evidence
        )
        for module_name, attr in required_cast_surfaces
    }
    instrumentation_available = bool(
        callable(getattr(ff, "cast_forensics_summary", None))
        and bool(getattr(ff, "e31_enabled", lambda: False)())
        and all(canonical_cast_surfaces.values())
    )
    conversion_before = (
        dict(ff.cast_forensics_summary()) if instrumentation_available else None
    )
    legacy_conversion_before = None
    legacy_forensics = None
    if not strict_e31:
        try:
            from . import e27_forensics

            legacy_forensics = e27_forensics
            legacy_conversion_before = dict(e27_forensics.forward_cast_account_summary())
        except Exception:
            legacy_conversion_before = None
    state: dict[str, Any] = {
        "installed": False,
        "forward_observed": False,
        "forward_actually_observed": False,
        "generation": int(bind_snapshot.get("generation", 0) or 0),
        "identity": str(id(getattr(clip, "cond_stage_model", None))),
        "instrumentation_available": instrumentation_available,
        "canonical_cast_surfaces": canonical_cast_surfaces,
        "cast_once_requested": bool(strict_e31),
        "cast_once_applied": True,
        "cast_once_generation": int(bind_snapshot.get("generation", 0) or 0),
        "forward_timing": None,
        "post_forward_stability": None,
        "e31_evidence_schema": 1,
        "canonical": {
            "phase": "execution",
            "forward_boundary": "outer_clip_encode",
        },
    }
    # Never let strict transfer callbacks retain source maps.  The tuple is
    # populated only for the compatibility-only legacy helper path.
    legacy_source = (
        (per_file_sds or [], files or [])
        if not bind_snapshot.get("bind_proof")
        else (None, None)
    )
    try:
        bind_fingerprint = cfh.clip_hydration_fingerprint(clip)
    except Exception:
        bind_fingerprint = None

    def _after_forward(observation: dict[str, Any]) -> None:
        started = time.perf_counter()
        state.update({
            "forward_observed": bool(observation.get("forward_observed", False)),
            "forward_actually_observed": bool(observation.get("forward_actually_observed", False)),
            "forward_method": observation.get("forward_method"),
            "forward_wall_ms": observation.get("forward_wall_ms"),
            "forward_timing": observation.get("forward_timing"),
            "forward_count": observation.get("forward_count"),
            "bound_request_id": observation.get("bound_request_id"),
            "forward_request_id": observation.get("forward_request_id"),
        })
        forward_count = observation.get("forward_count")
        forward_count_ok = forward_count is not None and int(forward_count or 0) == 1
        bound_request_id = str(
            observation.get("bound_request_id") or getattr(trace, "request_id", "") or _request_id()
        )
        forward_request_id = str(observation.get("forward_request_id") or "")
        request_scope_ok = bool(
            not bound_request_id
            or (forward_request_id and forward_request_id == bound_request_id)
        )
        # The E31 strict cast-once claim requires the production outer-boundary
        # count and request identity.  Legacy/off-mode fallback hooks retain
        # their existing diagnostic behavior, but their evidence is not
        # eligible for a strict success claim.
        strict_scope_ok = bool(
            not strict_e31 or (forward_count_ok and request_scope_ok)
        )
        scope_ok = bool(
            (
                observation.get("forward_identity") is None
                or str(observation.get("forward_identity")) == str(state.get("identity"))
            )
            and (
                observation.get("forward_generation") is None
                or int(observation.get("forward_generation", 0) or 0)
                == int(bind_snapshot.get("generation", 0) or 0)
            )
            and strict_scope_ok
        )
        if bind_snapshot.get("bind_proof"):
            after = snapshot_adopted_storage(
                clip,
                bind_snapshot["bind_proof"],
                expect_device=expect_device,
                phase="post_real_forward",
            )
        else:
            # Compatibility-only path for old offline helper tests.  Strict
            # ownership-transfer wiring always has a bind_proof and therefore
            # never captures these source mappings in its callback.
            after = snapshot_resident_fp32(
                clip, legacy_source[0] or [], legacy_source[1] or [],
                expect_device=expect_device,
                phase="post_real_forward",
            )
        stable, stability = compare_resident_fp32(bind_snapshot, after)
        try:
            fingerprint_ok = bind_fingerprint is not None and (
                cfh.clip_hydration_fingerprint(clip) == bind_fingerprint
            )
        except Exception:
            fingerprint_ok = False
        if not fingerprint_ok:
            stable = False
            stability = dict(stability)
            stability["reason"] = "identity_or_patch_fingerprint_changed"
        conversion_after = (
            dict(ff.cast_forensics_summary()) if instrumentation_available else None
        )
        before_real = int((conversion_before or {}).get("real_conversions", 0) or 0)
        after_real = int((conversion_after or {}).get("real_conversions", 0) or 0)
        before_bytes = int((conversion_before or {}).get("real_conversion_bytes", 0) or 0)
        after_bytes = int((conversion_after or {}).get("real_conversion_bytes", 0) or 0)
        real_delta = after_real - before_real
        bytes_delta = after_bytes - before_bytes
        forward_timing = observation.get("forward_timing") or {}
        canonical_cast_calls = forward_timing.get("canonical_cast_calls") or {}
        try:
            canonical_cast_call_count = int(
                forward_timing.get("canonical_cast_call_count", 0) or 0
            )
        except Exception:
            canonical_cast_call_count = 0
        try:
            cast_call_total = sum(
                int(value or 0) for value in canonical_cast_calls.values()
            ) if isinstance(canonical_cast_calls, dict) else -1
        except Exception:
            cast_call_total = -1
        cast_call_evidence_ok = bool(
            isinstance(canonical_cast_calls, dict)
            and canonical_cast_call_count > 0
            and cast_call_total == canonical_cast_call_count
        )
        if strict_e31:
            conversion_ok = bool(
                instrumentation_available
                and conversion_before is not None
                and conversion_after is not None
                and real_delta == 0
                and bytes_delta == 0
                and cast_call_evidence_ok
            )
        else:
            legacy_after = None
            if legacy_conversion_before is not None and legacy_forensics is not None:
                try:
                    legacy_after = dict(legacy_forensics.forward_cast_account_summary())
                except Exception:
                    legacy_after = None
            conversion_ok = bool(
                legacy_conversion_before is None
                or (
                    legacy_after is not None
                    and int(legacy_after.get("dest_bytes", 0) or 0)
                    == int(legacy_conversion_before.get("dest_bytes", 0) or 0)
                )
            )
        result = {
            **observation,
            "e31_evidence_schema": 1,
            "forward_check_ms": round((time.perf_counter() - started) * 1000.0, 3),
            "bind_generation": int(bind_snapshot.get("generation", 0) or 0),
            "post_forward_generation": int(after.get("generation", 0) or 0),
            "residency": after,
            "stability": stability,
            "storage_stable": bool(stable),
            "conversion_before": conversion_before,
            "conversion_after": conversion_after,
            "cast_forensics_before": conversion_before,
            "cast_forensics_after": conversion_after,
            "real_conversions_before": before_real,
            "real_conversions_after": after_real,
            "real_conversions_delta": real_delta,
            "real_conversion_bytes_before": before_bytes,
            "real_conversion_bytes_after": after_bytes,
            "real_conversion_bytes_delta": bytes_delta,
            "instrumentation_available": instrumentation_available,
            "canonical_cast_surfaces": canonical_cast_surfaces,
            "canonical_cast_calls": canonical_cast_calls,
            "canonical_cast_call_count": canonical_cast_call_count,
            "cast_call_evidence_ok": cast_call_evidence_ok,
            "forward_count": forward_count,
            "forward_count_ok": forward_count_ok,
            "bound_request_id": bound_request_id,
            "forward_request_id": forward_request_id,
            "request_scope_ok": request_scope_ok,
            "scope_ok": scope_ok,
            "mutation_guard_ok": bool(fingerprint_ok),
            "legacy_conversion_before": legacy_conversion_before,
            "conversion_ok": bool(conversion_ok),
            "cast_once_requested": bool(strict_e31),
            "cast_once_applied": True,
            "cast_once_generation": int(bind_snapshot.get("generation", 0) or 0),
            "conversion": {"count": int(real_delta), "bytes": int(bytes_delta)},
            "conversion_count": int(real_delta),
            "conversion_bytes": int(bytes_delta),
            "post_forward_stability": {
                "stable": bool(stable),
                "storage_stable": bool(stability.get("storage_stable", stable)),
                "metadata_stable": bool(stability.get("metadata_stable", False)),
                "generation_stable": bool(stability.get("generation_stable", False)),
            },
            "canonical": {
                "phase": "execution",
                "forward_boundary": "outer_clip_encode",
            },
            "forward_observed": bool(observation.get("forward_observed", False)),
            "forward_actually_observed": bool(observation.get("forward_actually_observed", False)),
            "ok": bool(
                observation.get("forward_observed", False)
                and observation.get("forward_actually_observed", False)
                and stable
                and conversion_ok
                and scope_ok
                and fingerprint_ok
            ),
        }
        _e31_request_id = str(getattr(trace, "request_id", "") or _request_id())
        if _e31_request_id:
            result["request_id"] = _e31_request_id
            result["canonical"]["request_id"] = _e31_request_id
        state.update(result)
        state["e31_success"] = bool(result["ok"])
        if result["ok"]:
            # Publication is deliberately after the real-forward proof; a
            # bind alone is not an E31 success claim.
            cfh.mark_clip_hydrated(clip)
            try:
                pending_record = _RECORD.get(_request_id())
                if pending_record is not None:
                    pending_record["hydrated"] = True
                    pending_record["e31_forward_evidence"] = dict(result)
            except Exception:
                pass
        _emit(trace, "clip_fh_cast_once_forward_check", result)
        if not result["ok"]:
            try:
                from .clip_fp32_cast_once import invalidate_cast_once

                invalidate_cast_once(clip)
            except Exception:
                pass
            try:
                from . import model_preload

                model_preload.clear_e31_forward_callback(
                    getattr(clip, "cond_stage_model", None)
                )
            except Exception:
                pass
            setattr(clip, cfh.HYDRATED_MARKER, False)
            _emit(
                trace,
                "clip_fh_cast_once_forward_failed",
                {
                    "reason": (
                        "multiple_outer_forwards"
                        if strict_e31 and not forward_count_ok
                        else "request_or_generation_scope_mismatch"
                        if strict_e31 and not (scope_ok and request_scope_ok)
                        else "storage_or_conversion_instability"
                    ),
                    "evidence": result,
                },
            )
            raise RuntimeError("E31 cast-once real-forward proof failed")

    hook: dict[str, Any]
    csm = getattr(clip, "cond_stage_model", None)
    try:
        from . import model_preload

        hook = model_preload.register_e31_forward_callback(
            csm,
            _after_forward,
            generation=int(bind_snapshot.get("generation", 0) or 0),
            request_id=str(getattr(trace, "request_id", "") or _request_id()),
        )
    except Exception:
        hook = {"installed": False, "reason": "outer_forward_registration_error"}
    # Offline fakes generally have no production encode_token_weights wrapper.
    # They may use the old outer CLIP encode boundary, but production objects
    # must never silently fall back to a hook installed after demand entry.
    if not hook.get("installed") and not callable(
        getattr(type(csm), "encode_token_weights", None)
    ):
        hook = install_real_forward_check(clip, _after_forward)
    state.update({k: v for k, v in hook.items() if k != "callback"})
    try:
        setattr(clip, "_comfymodal_e31_bound_cond_stage_model", csm)
    except Exception:
        pass
    if not hook.get("installed"):
        _emit(
            trace,
            "clip_fh_cast_once_forward_unavailable",
            {"reason": "no_existing_clip_encode_boundary", "generation": int(bind_snapshot.get("generation", 0) or 0)},
        )
    return {
        "hook": state,
        "conversion_before": conversion_before,
        "instrumentation_available": instrumentation_available,
    }


def _cast_transfer_identity(manifest: Mapping[str, Any], files: list[dict]) -> Any:
    """Build strict cast identity from the attached frozen manifest only."""
    from .clip_fp32_cast_once import build_source_manifest_identity

    fields = {
        name: manifest.get(name)
        for name in (
            "checkpoint_identity",
            "manifest_generation",
            "content_generation",
            "selected_tensor_scope",
            "model_patch_identity",
            "target_device",
        )
        if manifest.get(name) not in (None, "", [], {})
    }
    if not str(fields.get("target_device", "")).startswith("cuda:"):
        raise RuntimeError("missing stable identity field: target_device must be explicit CUDA")
    return build_source_manifest_identity(
        files,
        identity=fields,
        target_device=None,
        cast_policy_version=str(manifest.get("cast_policy_version", "ra9g-fp32-v1")),
    )


def _emit_cast_fallback(trace: Any, reason: str) -> None:
    _emit(trace, "clip_fh_cast_once_fallback", {
        "requested": True,
        "applied": False,
        "fallback": "ordinary_bf16",
        "fallback_count": 1,
        "reason": str(reason)[:240],
    })


def _bind_with_ownership_transfer(
    clip: Any,
    transfer: Any,
    transformed: list[dict],
    *,
    require_no_meta: bool,
) -> tuple[dict[str, Any], str]:
    """The sole strict cast-once bind adapter used by demand and take paths."""
    from .clip_fp32_cast_once import actual_bind_destination_map, build_actual_bind_receipt

    ok, evidence = cfh.hydrate_clip_bind(
        clip,
        transformed,
        require_no_meta=require_no_meta,
        expect_device=transfer.identity.target_device,
    )
    if not ok:
        raise RuntimeError(f"bind: {evidence}")
    declared_structural_keys = {
        str(key)
        for manifest in getattr(transfer, "_manifests", ())
        for key in (manifest.get("structural_destination_keys") or ())
    }
    destination = actual_bind_destination_map(
        clip,
        transfer.identity.expected_keys,
        declared_structural_keys=declared_structural_keys,
    )
    receipt = build_actual_bind_receipt(
        clip, destination, transfer.identity, assign=True
    )
    transfer.acknowledge_actual_bind(
        destination, receipt=receipt, assign=True, clip=clip
    )
    return transfer.prove_storage(expected_device=transfer.identity.target_device), evidence


def _try_fast_hydrate(
    clip: Any, manifest: dict, *, trace: Any = None, comfy_utils: Any = None
) -> dict[str, Any]:
    """Load every file to GPU, replay the frozen pipeline, verify against the
    manifest, bind via Comfy's own dispatch with assign=True, attach owners.
    All files are loaded+verified BEFORE any bind so a failure leaves the
    model untouched."""
    import torch

    # Re-hydration starts before source I/O.  Clearing here closes the failure
    # window where a source read/transform error could otherwise leave the old
    # marker or callback visible while native fallback is selected.
    cfh.reset_clip_hydration_for_bind(clip)

    files = manifest.get("files", [])
    owners: list[tuple[Any, Any]] = []
    per_file_sds: list[dict] = []
    checkpoint_bytes = 0
    file_to_gpu_ms = 0.0
    rss_before = _rss_mb()
    baseline = _cuda_baseline()
    t0 = time.perf_counter()
    _clip_loader_start_ns = _emit_clip_loader_endpoint(
        trace,
        CLIP_LOADER_START,
        endpoint_role="loader_start",
        loader_arm="common_loader_boundary",
    )
    _clip_device_ready_ns: Optional[int] = None
    _spec_record: dict[str, Any] = {}
    _orchestration_record = None
    _copy_event = None
    _scoped_readiness = _gpu_coord.scoped_cuda_readiness_enabled()
    _e31_cast_once_applied = False
    _e31_cast_record: dict[str, Any] = {}
    _e31_bind_record: dict[str, Any] = {}
    _cast_transfer: Any = None
    _cast_fallback_reason = ""
    _cast_once_requested = bool(env_flag("COMFYMODAL_V2_CLIP_FP32_CAST_ONCE"))
    # ── E29: canonical ledger CLIP hydration span ───────────────────────
    # The whole fast-hydrate window (source read / speculative take / bind /
    # sync) becomes one ledger span so the serial ledger owns CLIP GPU
    # hydration wall (E30/E31 decision input) instead of hiding it inside
    # the coarse executor span.  Never raises.
    _span_clip_hydration: Any = None
    try:
        from .critical_path_ledger import begin_span as _ledger_begin_span
        _span_clip_hydration = _ledger_begin_span(
            "CLIP hydration", lane="CLIP",
            start_mono_ns=time.monotonic_ns(),
            metadata={"source": "clip_fast_hydration_wiring._try_fast_hydrate"},
        )
    except Exception:
        _span_clip_hydration = None
    # ── E25: take a completed speculative read (file->GPU + transform) so
    # the file read is hidden under setup; verification + bind + sync still
    # run here exactly as before.  Fail-closed: on any inconsistency the
    # normal per-file read loop below runs.
    _speculative_taken = None
    _speculative_take_reason = ""
    _qd_demand_used = False
    _m2_demand_used = False
    _m2_record: dict[str, Any] = {}
    try:
        from .speculative_clip_hydration import (
            take_speculative_read,
            active_speculative_request_id,
            join_speculative_clip_lane,
            get_speculative_clip_lane,
            cancelled_speculative_lane_reason,
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
            # The join is fail-closed: on timeout/cancellation no demand read
            # is started against a worker that may still be draining.
            _join_rid = _rid or active_speculative_request_id()
            _lane = get_speculative_clip_lane(_join_rid) if _join_rid else None
            if _lane is not None and _lane.finished_mono_ns == 0:
                _join_ms = join_speculative_clip_lane(_join_rid, timeout_s=20.0)
                if (_join_ms or {}).get("cancelled"):
                    # The worker has been cancelled and removed from the lane
                    # store, but a filesystem/loader call may still be
                    # draining.  Do not enter either fast read loop: doing so
                    # would create a duplicate read against live owners.
                    raise RuntimeError(
                        f"speculative_join_failed_closed:{(_join_ms or {}).get('reason', 'cancelled')}"
                    )
                _speculative_take_reason = (
                    f"joined_lane_ms={round((_join_ms or {}).get('speculative_read_ms', 0) or 0, 1)}"
                )
                _speculative_taken = take_speculative_read(_join_rid)
                if _speculative_taken is None:
                    _speculative_take_reason += ":join_take_failed"
            elif _lane is not None:
                _speculative_take_reason = "lane_finished_not_takeable"
            elif _join_rid:
                # The lane may already have been removed by cancellation.  A
                # scalar tombstone is still a fail-closed signal; without
                # this check the normal fast read would race the old worker.
                _join_ms = join_speculative_clip_lane(_join_rid, timeout_s=0.0)
                if (_join_ms or {}).get("cancelled"):
                    raise RuntimeError(
                        f"speculative_join_failed_closed:{(_join_ms or {}).get('reason', 'cancelled')}"
                    )
            else:
                _cancelled_reason = cancelled_speculative_lane_reason(_rid)
                if _cancelled_reason:
                    raise RuntimeError(
                        f"speculative_join_failed_closed:{_cancelled_reason}"
                    )
        _emit(
            trace,
            "clip_fh_speculative_take_result",
            {
                "request_id": _rid,
                "taken": int(_speculative_taken is not None),
                "reason": _speculative_take_reason or "primary_hit",
            },
        )
    except Exception as _spec_exc:
        if "speculative_join_failed_closed" in str(_spec_exc):
            raise
        _speculative_taken = None
    if env_flag(_FLAG_M2) and _speculative_taken is None:
        try:
            for _file_manifest in files:
                _path = str(_file_manifest.get("path", ""))
                _loaded = _m2_loader.load_m2_safetensors(_path, trace=trace)
                _transformed = _apply_pipeline(
                    _loaded["sd"], _file_manifest.get("pipeline", []), comfy_utils=comfy_utils
                )
                _ok, _detail = _verify_file_against_manifest(
                    _file_manifest, _transformed
                )
                if not _ok:
                    raise RuntimeError(_detail)
                per_file_sds.append(_transformed)
                owners.append((_loaded["owner"], _loaded["owner"]))
                checkpoint_bytes += int(_file_manifest.get("size_bytes", 0) or 0)
                file_to_gpu_ms += float(
                    (_loaded.get("timing") or {}).get("loader_wall_ms", 0.0) or 0.0
                )
                _m2_record = {
                    **_m2_record,
                    **dict(_loaded.get("timing") or {}),
                }
            _m2_demand_used = True
            _spec_record = {
                "m2_used": True,
                "qd": 4,
                "block_mib": 64,
                "source_wall_ms": _m2_record.get("source_wall_ms"),
                "gpu_ready_wall_ms": _m2_record.get("gpu_ready_wall_ms"),
            }
        except Exception:
            _close_source_owners(owners)
            per_file_sds = []
            owners = []
            raise

    if clean_lane.enabled() and not env_flag(_FLAG_M2) and _speculative_taken is None:
        # CLEAN_LANE deliberately has no restore-time speculative read.  Do
        # the QD read synchronously at demand instead of treating the
        # expected empty speculative lane as a quiescence failure.  The QD
        # reader joins all of its workers and H2D events before returning and
        # publishes the clean-lane quiescence proof at that boundary.
        try:
            from .clip_qd_reader import clip_qd_load, qd_config

            _qd_cfg = qd_config()
            _qd_value = int(_qd_cfg.get("qd", 0) or 0)
            if not bool(_qd_cfg.get("enabled")):
                raise RuntimeError("CLEAN_LANE_QD_READER_DISABLED")
            if _qd_value != 4:
                raise RuntimeError(f"CLEAN_LANE_QD4_REQUIRED: configured={_qd_value}")
            _qd_block_mib = int(
                _qd_cfg.get("block_mib", 0) or 0
            )
            _qd_launch_policy = str(_qd_cfg.get("launch_policy", "") or "")
            if _qd_block_mib < 1 or not _qd_launch_policy:
                raise RuntimeError("CLEAN_LANE_QD_CONFIGURATION_INCOMPLETE")
            if not files:
                raise RuntimeError("CLEAN_LANE_CLIP_MANIFEST_EMPTY")

            for _file_manifest in files:
                _path = _file_manifest.get("path", "")
                if not os.path.exists(_path):
                    raise RuntimeError(f"missing source file: {_path}")
                _t_load = time.perf_counter()
                _sd_raw, _loader, _fb = clip_qd_load(
                    _path,
                    qd=_qd_value,
                    block_mib=_qd_block_mib,
                    trace=trace,
                    launch_policy=_qd_launch_policy,
                    artifact_path=_qd_cfg.get("artifact_path") or None,
                )
                _t_loaded = time.perf_counter()
                file_to_gpu_ms += (_t_loaded - _t_load) * 1000.0
                _transformed = _apply_pipeline(
                    _sd_raw, _file_manifest.get("pipeline", []), comfy_utils=comfy_utils
                )
                _ok, _detail = _verify_file_against_manifest(
                    _file_manifest, _transformed
                )
                if not _ok:
                    raise RuntimeError(_detail)
                per_file_sds.append(_transformed)
                owners.append((_loader, _fb))
                checkpoint_bytes += int(_file_manifest.get("size_bytes", 0) or 0)

            _qd_proof = clean_lane.proof()
            _qd_quiescence = _qd_proof.get("quiescence") or {}
            _required_quiescence = (
                "source_reads_complete",
                "submitted_blocks_reconciled",
                "futures_joined",
                "no_qd_worker_runnable",
                "pinned_ownership_safe",
                "h2d_events_complete",
                "device_ready_published",
            )
            if any(_qd_quiescence.get(_key) is not True for _key in _required_quiescence):
                raise RuntimeError("CLEAN_LANE_QD_NOT_QUIESCENT_BEFORE_BIND")

            _qd_demand_used = True
            _spec_record = {
                "qd_used": True,
                "qd_demand": True,
                "configured_qd": _qd_value,
                "block_mib": _qd_block_mib,
                "launch_policy": _qd_launch_policy,
            }
            try:
                from .clip_qd_reader import (
                    EVT_BIND,
                    EVT_OWNER_RETAINED,
                    EVT_TAKE,
                    emit_qd_event,
                    ledger_event,
                )

                _qd_request_id = str(getattr(trace, "request_id", "") or _request_id())
                _qd_meta = {
                    "request_id": _qd_request_id,
                    "path": str(files[0].get("path", "")) if files else "",
                    "taken": True,
                    "files": len(per_file_sds),
                    "qd_used": True,
                    "demand_side": True,
                }
                emit_qd_event(trace, EVT_TAKE, **_qd_meta)
                ledger_event(EVT_TAKE, **_qd_meta)
                emit_qd_event(
                    trace, EVT_BIND, request_id=_qd_request_id,
                    files=len(per_file_sds), qd_used=True, demand_side=True,
                )
                ledger_event(
                    EVT_BIND, request_id=_qd_request_id,
                    files=len(per_file_sds), qd_used=True, demand_side=True,
                )
                emit_qd_event(
                    trace, EVT_OWNER_RETAINED, request_id=_qd_request_id,
                    owners=len(owners), qd_used=True, demand_side=True,
                )
                ledger_event(
                    EVT_OWNER_RETAINED, request_id=_qd_request_id,
                    owners=len(owners), qd_used=True, demand_side=True,
                )
            except Exception:
                pass
        except Exception:
            clean_lane.forbidden_activity(
                "clip_qd_demand_read_failed", trace,
                reason="synchronous QD demand read did not complete",
            )
            raise

    if clean_lane.enabled() and _speculative_taken is None and not _qd_demand_used and not _m2_demand_used:
        clean_lane.forbidden_activity(
            "clip_forward_hidden_qd_join_or_fastsafe_fallback", trace,
            reason="QD must be complete before bind/forward",
        )
        raise RuntimeError("CLEAN_LANE_QD_NOT_QUIESCENT_BEFORE_BIND")
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
            # ── E30: demand-time take/bind/owner-retained events ──
            # The reader's own take/bind events inside clip_qd_load mark the
            # SOURCE-side boundaries; the authoritative demand-time take +
            # bind + owner-retain happen HERE.  Emit the E30 contract events
            # (canonical ledger + trace) exactly when the QD reader produced
            # the tensors (record.qd_used), so a QD-entered run is provable
            # end-to-end and a fastsafe lane never fabricates QD events.
            _qd_used = bool((_spec_record or {}).get("qd_used", False))
            if clean_lane.enabled() and not _qd_used:
                clean_lane.forbidden_activity("non_qd_speculative_publication", trace)
                raise RuntimeError("CLEAN_LANE_QD_PUBLICATION_REQUIRED")
            if _qd_used:
                try:
                    from .clip_qd_reader import (
                        EVT_TAKE,
                        EVT_BIND,
                        EVT_OWNER_RETAINED,
                        emit_qd_event,
                        ledger_event,
                    )

                    _qd_take_meta = {
                        "request_id": _rid,
                        "path": str(files[0].get("path", "")) if files else "",
                        "taken": True,
                        "files": len(_spec_per_file_sds),
                        "qd_used": True,
                    }
                    emit_qd_event(trace, EVT_TAKE, **_qd_take_meta)
                    ledger_event(EVT_TAKE, **_qd_take_meta)
                    emit_qd_event(
                        trace, EVT_BIND,
                        request_id=_rid,
                        files=len(_spec_per_file_sds),
                        qd_used=True,
                    )
                    ledger_event(
                        EVT_BIND,
                        request_id=_rid,
                        files=len(_spec_per_file_sds),
                        qd_used=True,
                    )
                    emit_qd_event(
                        trace, EVT_OWNER_RETAINED,
                        request_id=_rid,
                        owners=len(_spec_owners),
                        qd_used=True,
                    )
                    ledger_event(
                        EVT_OWNER_RETAINED,
                        request_id=_rid,
                        owners=len(_spec_owners),
                        qd_used=True,
                    )
                except Exception:
                    pass
            # E28 Target C: when the speculative lane applied the compute-ready
            # FP32 cast-once, verification expects FP32 (the cast target) —
            # exact key set + shapes as frozen, dtype FP32.  Fail-closed: any
            # doubt falls back to the normal BF16 read.  The record's
            # ``cast_once`` is always a dict (never None).
            _spec_cast_applied = bool(
                ((_spec_record or {}).get("cast_once") or {}).get("applied", False)
            )
            if _spec_cast_applied:
                _e31_cast_once_applied = True
                _e31_cast_record = dict((_spec_record or {}).get("cast_once") or {})
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
                _e31_cast_once_applied = False
                _e31_cast_record = {}
                _spec_cleanup = _close_source_owners(_spec_owners)
                if _spec_cleanup.get("errors"):
                    _emit(
                        trace,
                        "clip_fh_speculative_cleanup_failed",
                        {
                            "errors": list(_spec_cleanup["errors"]),
                            "primary_error": _detail or "speculative verification failed",
                        },
                    )
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
        # The transfer owns both the BF16 source mappings and the loader
        # handles.  In particular, speculative reads arrive here still BF16;
        # no cast-once representation exists before this request-local object.
        try:
            from .clip_fp32_cast_once import (
                cast_once_enabled,
                construct_ownership_transfer,
            )
            if cast_once_enabled():
                try:
                    _cast_identity = _cast_transfer_identity(manifest, files)
                except Exception as _identity_exc:
                    _cast_fallback_reason = f"{type(_identity_exc).__name__}: {str(_identity_exc)[:160]}"
                    _cast_transfer = None
                else:
                    try:
                        _cast_transfer = construct_ownership_transfer(
                            per_file_sds,
                            owners,
                            files,
                            identity=_cast_identity,
                            strict=True,
                        )
                        per_file_sds, _e31_cast_record = _cast_transfer.transform_once(trace=trace)
                        _e31_cast_once_applied = True
                    except Exception as _cast_exc:
                        _cast_fallback_reason = f"{type(_cast_exc).__name__}: {str(_cast_exc)[:160]}"
                        # The transfer never published a transformed mapping;
                        # retain the original BF16 maps/owners for the
                        # ordinary bind below.  Do not run transfer.release()
                        # here: that would retire the only live source handles
                        # before the documented BF16 fallback can adopt them.
                        _cast_transfer = None
                        _e31_cast_record = {}
        except ImportError:
            pass

        if _scoped_readiness:
            _copy_event = _gpu_coord.record_copy_event(
                "clip", trace, stream=torch.cuda.current_stream()
            )
            if _copy_event is None:
                raise RuntimeError("scoped_copy_event_unavailable")
        t_bind = time.perf_counter()
        # A new bind is a semantic mutation boundary.  Invalidate the old
        # marker/generation and any pending callback before replacing storage.
        cfh.reset_clip_hydration_for_bind(clip)
        if _cast_transfer is not None:
            _e31_bind_record, evidence = _bind_with_ownership_transfer(
                clip,
                _cast_transfer,
                per_file_sds,
                require_no_meta=cfh.clip_weights_excluded(clip),
            )
            ok = True
        else:
            ok, evidence = cfh.hydrate_clip_bind(
                clip,
                per_file_sds,
                require_no_meta=cfh.clip_weights_excluded(clip),
                expect_device=f"cuda:{torch.cuda.current_device()}",
            )
        if not ok:
            raise RuntimeError(f"bind: {evidence}")
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
        _loader_arm = (
            "m2_demand"
            if _m2_demand_used
            else "qd_demand"
            if _qd_demand_used
            else "qd_speculative"
            if bool(_spec_record.get("qd_used", False))
            else "fastsafe"
        )
        _clip_device_ready_ns = _emit_clip_loader_endpoint(
            trace,
            CLIP_DEVICE_READY,
            endpoint_role="device_ready",
            loader_arm=_loader_arm,
        )
        clean_lane.mark_bind(trace)
        _loader_interval = {
            "clock": "monotonic_ns",
            "clock_source": "time.monotonic_ns",
            "start": {
                "name": CLIP_LOADER_START,
                "endpoint_role": "loader_start",
                "semantic_endpoint_role": "loader_start",
                "monotonic_ns": int(_clip_loader_start_ns),
            },
            "ready": {
                "name": CLIP_DEVICE_READY,
                "endpoint_role": "device_ready",
                "semantic_endpoint_role": "device_ready",
                "monotonic_ns": int(_clip_device_ready_ns),
            },
            "loader_arm": _loader_arm,
            "hydration_source": _loader_arm,
            "wall_ms": round(
                (int(_clip_device_ready_ns) - int(_clip_loader_start_ns)) / 1_000_000,
                3,
            ),
        }
        # E31's exact proof belongs after bind completion synchronization and
        # before either hydration marker or owner publication.  A failed proof
        # therefore takes the existing outer fast-path failure cleanup rather
        # than escaping as a successful hydration.
        _e31_forward_install: dict[str, Any] = {}
        _e31_owner_record: dict[str, Any] = {}
        try:
            from .clip_fp32_cast_once import (
                cast_once_enabled as _e31_enabled,
                cast_once_generation as _e31_generation,
            )

            if _e31_enabled() and _cast_transfer is not None:
                if not _e31_cast_once_applied:
                    raise RuntimeError("E31 cast-once expected but no cast-once tensors were produced")
                if _cast_transfer is None or not _e31_cast_once_applied:
                    raise RuntimeError("E31 cast-once requested without an ownership transfer")
                fp32_bytes = int(_e31_bind_record.get("fp32_bytes", 0) or 0)
                # Install and validate the exact real-forward boundary BEFORE
                # retiring source owners or publishing a cast generation.  If
                # the trace-less outer wrapper/forensics path is unavailable,
                # fail closed while all source components are still owned.
                _e31_forward_install = _e31_forward_hook(
                    clip,
                    expect_device=_cast_transfer.identity.target_device,
                    bind_snapshot=_e31_bind_record,
                    trace=trace,
                )
                if not (_e31_forward_install.get("hook") or {}).get("installed"):
                    raise RuntimeError("E31 real-forward hook installation failed")
                if not _e31_forward_install.get("instrumentation_available", False):
                    raise RuntimeError("E31 forward forensics instrumentation unavailable")
                # Drop every local source/transformed reference before the
                # transfer retires its handles.  The callback above captures
                # only immutable proof metadata and the model handle.
                _cast_transfer.drop_source_references()
                per_file_sds = []
                owners = []
                _e31_owner_record = _cast_transfer.retire_owners()
                _emit(trace, "clip_fh_cast_once_owner_retired", _e31_owner_record)
                if not _e31_owner_record.get("ok"):
                    raise RuntimeError(
                        "E31 source owner retirement failed: "
                        f"{_e31_owner_record.get('owners_failed', 0)} owner(s)"
                    )
                (_e31_forward_install.get("hook") or {})["owner_transition"] = dict(_e31_owner_record)
                _e31_generation_before_mark = int(_e31_generation(clip))
                _e31_ready_record = _cast_transfer.mark_ready(clip)
                _e31_bind_record.update(_e31_ready_record)
                _e31_bind_record["generation"] = int(_e31_ready_record.get("generation", 0) or 0)
                bind_proof = _e31_bind_record.get("bind_proof")
                if isinstance(bind_proof, dict):
                    bind_proof["generation"] = _e31_bind_record["generation"]
                if _e31_bind_record["generation"] <= _e31_generation_before_mark:
                    setattr(clip, cfh.HYDRATED_MARKER, False)
                    raise RuntimeError("E31 cast-once generation mark did not advance")
                # Publish the bind proof only after both storage proof and
                # source-owner retirement have succeeded.
                _emit(trace, "clip_fh_cast_once_bind_proof", _e31_bind_record)
                try:
                    from . import model_preload as _e31_preload

                    if not _e31_preload.update_e31_forward_callback_generation(
                        getattr(clip, "cond_stage_model", None),
                        generation=_e31_bind_record["generation"],
                    ):
                        # Offline instance wrappers do not use the production
                        # pending callback.  Their closure observes the
                        # mutable bind record directly.
                        if not (_e31_forward_install.get("hook") or {}).get("methods"):
                            raise RuntimeError("E31 forward callback generation rebind failed")
                except ImportError:
                    pass
                cfh.mark_clip_hydrated(clip)
            else:
                if _e31_enabled() and _cast_fallback_reason:
                    _emit_cast_fallback(trace, _cast_fallback_reason)
                for loader, fb in owners:
                    cfh.owner_attach(clip, loader, fb)
                cfh.mark_clip_hydrated(clip)
        except ImportError:
            for loader, fb in owners:
                cfh.owner_attach(clip, loader, fb)
            cfh.mark_clip_hydrated(clip)
        except Exception:
            try:
                cfh.reset_clip_hydration_for_bind(clip)
            except Exception:
                pass
            setattr(clip, cfh.HYDRATED_MARKER, False)
            try:
                from .clip_fp32_cast_once import invalidate_cast_once

                invalidate_cast_once(clip)
            except Exception:
                pass
            raise
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
        if _e31_bind_record:
            _fp32_param_count = int(
                _e31_bind_record.get("fp32_param_count")
                or (_e31_bind_record.get("count_by_dtype") or {}).get("torch.float32", 0)
                or _e31_bind_record.get("parameter_count", 0)
                or 0
            )
            _fp32_bytes = int(
                _e31_bind_record.get("fp32_bytes")
                or (_e31_bind_record.get("bytes_by_dtype") or {}).get("torch.float32", 0)
                or _e31_bind_record.get("destination_bytes", 0)
                or 0
            )
            _emit(
                trace,
                "clip_fh_cast_once_applied",
                {
                    "generation": int(_e31_bind_record.get("generation", 0)),
                    "fp32_params": _fp32_param_count,
                    "fp32_param_count": _fp32_param_count,
                    "fp32_bytes": _fp32_bytes,
                    "destination_bytes": _fp32_bytes,
                    "post_mark_generation": int(_e31_bind_record.get("generation", 0)),
                    "forward_hook": _e31_forward_install.get("hook", {}),
                },
            )
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
            "mode": "m2_mmap_process" if _m2_demand_used else cfh.MODE_FASTSAFE,
            "file_to_gpu_wall_ms": round(file_to_gpu_ms, 3),
            "checkpoint_bytes": checkpoint_bytes,
            "gbps": gbps,
            "bind_wall_ms": round(bind_ms, 3),
            "wall_ms": round(wall_ms, 3),
            "owner_mode": "m2_torch_cuda_tensor" if _m2_demand_used else "fastsafetensors_buf",
            "rss_delta_mb": (
                None if rss_before is None else round((_rss_mb() or rss_before) - rss_before, 3)
            ),
            "cuda_delta_bytes": _cuda_peak_delta(baseline),
            "zero_copy": True,
            "zero_copy_evidence": evidence,
            "fallback_count": 1 if _cast_once_requested and not _e31_bind_record else 0,
            "e31_evidence_schema": 1,
            "cast_once_requested": _cast_once_requested,
            "cast_once_applied": bool(_e31_bind_record),
            "cast_once_fallback": (
                _cast_fallback_reason or "ordinary_bf16"
                if _cast_once_requested and not _e31_bind_record
                else None
            ),
            "cast_once_generation": int(_e31_bind_record.get("generation", 0) or 0),
            "owner_transition": _e31_owner_record if _e31_bind_record else None,
            "forward_observed": False,
            "forward_timing": None,
            "conversion_count": int(
                _e31_cast_record.get("tensor_count", 0)
                or _e31_bind_record.get("fp32_param_count", 0)
                or 0
            ),
            "conversion_bytes": int(
                _e31_cast_record.get("bytes_out", 0)
                or _e31_bind_record.get("fp32_bytes", 0)
                or _e31_bind_record.get("destination_bytes", 0)
                or 0
            ),
            "post_forward_stability": None,
            "canonical": {
                "phase": "execution",
                "hydration_source": "m2_mmap_process" if _m2_demand_used else cfh.MODE_FASTSAFE,
                "loader_interval": _loader_interval,
            },
        }
        if _m2_demand_used:
            result["m2_timing"] = dict(_m2_record)
            result["m2_source_geometry"] = {"qd": 4, "block_mib": 64, "slots": 1}
        if _e31_bind_record:
            result["cast_once_bind_proof"] = _e31_bind_record
            result["cast_once_owner_transition"] = _e31_owner_record
            result["owner_transition"] = _e31_owner_record
            result["e31_forward_required"] = True
            result["e31_forward_observed"] = False
            result["e31_success"] = False
            result["e31_forward_evidence"] = _e31_forward_install.get("hook", {})
            result["cast_once_requested"] = True
            result["cast_once_applied"] = True
            result["fallback_count"] = 0
            result["fp32_param_count"] = int(
                _e31_bind_record.get("fp32_param_count")
                or _e31_bind_record.get("parameter_count", 0)
                or 0
            )
            result["fp32_bytes"] = int(
                _e31_bind_record.get("fp32_bytes")
                or _e31_bind_record.get("destination_bytes", 0)
                or 0
            )
            result["cast_once_generation"] = int(_e31_bind_record.get("generation", 0) or 0)
            result["conversion"] = {
                "count": int(_e31_cast_record.get("tensor_count", 0) or 0),
                "bytes": int(_e31_cast_record.get("bytes_out", 0) or 0),
            }
            result["post_forward_stability"] = None
        _e31_request_id = str(getattr(trace, "request_id", "") or _request_id())
        if _e31_request_id:
            result["request_id"] = _e31_request_id
            result["canonical"]["request_id"] = _e31_request_id
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
        # ── E29: close the canonical ledger CLIP hydration span ─────────
        if _span_clip_hydration is not None:
            try:
                _span_clip_hydration.finish(mono_ns=time.monotonic_ns())
            except Exception:
                pass
        return result
    except Exception as exc:
        reason = f"{type(exc).__name__}: {str(exc)[:160]}"
        try:
            cfh.reset_clip_hydration_for_bind(clip)
        except Exception:
            pass
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
        if _cast_transfer is not None:
            try:
                _cast_transfer.fail(exc)
                _cast_transfer.release()
            except Exception as _cleanup_exc:
                _emit(trace, "clip_fh_cast_once_cleanup_failed", {
                    "reason": f"{type(_cleanup_exc).__name__}: {str(_cleanup_exc)[:160]}",
                    "primary_error": f"{type(exc).__name__}: {str(exc)[:160]}",
                })
            owners = []
        else:
            _cleanup = _close_source_owners(owners)
            if _cleanup.get("errors"):
                _emit(trace, "clip_fh_source_cleanup_failed", {
                    "errors": list(_cleanup["errors"]),
                    "primary_error": reason,
                })
        try:
            torch.cuda.empty_cache()
        except Exception:
            pass
        # ── E29: close the canonical ledger CLIP hydration span (error) ──
        if _span_clip_hydration is not None:
            try:
                _span_clip_hydration.finish(mono_ns=time.monotonic_ns())
            except Exception:
                pass
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
            "cast_once_requested": _cast_once_requested,
            "cast_once_applied": False,
            "cast_once_fallback": "ordinary_bf16" if _cast_once_requested else None,
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
            "cast_once_requested": bool(env_flag("COMFYMODAL_V2_CLIP_FP32_CAST_ONCE")),
            "cast_once_applied": False,
            "cast_once_fallback": (
                "ordinary_bf16"
                if env_flag("COMFYMODAL_V2_CLIP_FP32_CAST_ONCE")
                else None
            ),
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
    cfh.reset_clip_hydration_for_bind(clip)
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
            "cast_once_requested": bool(env_flag("COMFYMODAL_V2_CLIP_FP32_CAST_ONCE")),
            "cast_once_applied": False,
            "cast_once_fallback": (
                "ordinary_bf16"
                if env_flag("COMFYMODAL_V2_CLIP_FP32_CAST_ONCE")
                else None
            ),
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
        cfh.reset_clip_hydration_for_bind(clip)
        result = {
            "ok": False,
            "mode": cfh.MODE_NATIVE,
            "reason": f"{type(exc).__name__}: {str(exc)[:160]}",
            "fallback_count": 1,
            "cast_once_requested": bool(env_flag("COMFYMODAL_V2_CLIP_FP32_CAST_ONCE")),
            "cast_once_applied": False,
            "cast_once_fallback": (
                "ordinary_bf16"
                if env_flag("COMFYMODAL_V2_CLIP_FP32_CAST_ONCE")
                else None
            ),
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


def _cast_once_requested_for_recording() -> bool:
    return bool(env_flag("COMFYMODAL_V2_CLIP_FP32_CAST_ONCE"))


def _record_mode(
    clip: Any,
    mode: str,
    info: dict[str, Any],
    *,
    state_before: Optional[str] = None,
    state_after: Optional[str] = None,
) -> dict[str, Any]:
    # A requested cast-once path that cannot establish identity/ownership is
    # an ordinary BF16 fallback, never an unrequested nominal success.  Apply
    # this at the recording boundary as well as at the fast-path result so
    # both ``_RECORD`` and loader execution identity retain the truth.
    if _cast_once_requested_for_recording() and not bool(info.get("cast_once_applied", False)):
        info = dict(info)
        info["cast_once_requested"] = True
        info["cast_once_applied"] = False
        info["cast_once_fallback"] = info.get("cast_once_fallback") or "ordinary_bf16"
        info["fallback_count"] = max(int(info.get("fallback_count", 0) or 0), 1)
    rid = _request_id()
    rec = _RECORD.setdefault(
        rid,
        {
            "mode": None,
            "fallback_count": 0,
            "hydrated": False,
            "last": None,
            "cast_once_requested": False,
            "cast_once_applied": False,
        },
    )
    rec["mode"] = mode
    rec["fallback_count"] += int(info.get("fallback_count", 0) or 0)
    if "cast_once_requested" in info:
        rec["cast_once_requested"] = bool(info.get("cast_once_requested"))
    if "cast_once_applied" in info:
        rec["cast_once_applied"] = bool(info.get("cast_once_applied"))
    if info.get("cast_once_fallback"):
        rec["cast_once_fallback"] = str(info["cast_once_fallback"])
    if info.get("ok") and not info.get("e31_forward_required"):
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
    cfh.reset_clip_hydration_for_bind(clip)
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
    def _e31_forward_required() -> bool:
        try:
            from comfymodal_runtime.clip_forward_forensics import e31_enabled
            from comfymodal_runtime.clip_fp32_cast_once import cast_once_enabled

            return bool(e31_enabled() or cast_once_enabled())
        except Exception:
            return False

    if getattr(clip, cfh.DEMAND_WRAPPER_MARKER, False):
        coordination_status = cfh.install_gpu_critical_coordination(clip)
        forward_wrapper_status = "not_requested"
        if _e31_forward_required():
            try:
                from comfymodal_runtime import model_preload as _model_preload

                forward_wrapper_status = _model_preload._ensure_clip_forward_wrapper(clip)
            except Exception as exc:
                forward_wrapper_status = f"error:{type(exc).__name__}"
        return {
            "status": "already_wrapped",
            "coordination": coordination_status,
            "forward_wrapper": forward_wrapper_status,
        }

    # The production forward boundary belongs to the restored CLIP's
    # ``cond_stage_model``, not the outer CLIP holder.  Arm it now, before the
    # first demand can enter ``load_model``; this is intentionally independent
    # of trace availability.  E31 registration later stores/consumes the
    # callback on this same object.
    forward_wrapper_status = "not_requested"
    if _e31_forward_required():
        try:
            from comfymodal_runtime import model_preload as _model_preload

            forward_wrapper_status = _model_preload._ensure_clip_forward_wrapper(clip)
        except Exception as exc:
            forward_wrapper_status = f"error:{type(exc).__name__}"

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
    return {
        "status": "installed",
        "coordination": coordination_status,
        "forward_wrapper": forward_wrapper_status,
    }


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
        "cast_once_requested": bool(rec.get("cast_once_requested", False)),
        "cast_once_applied": bool(rec.get("cast_once_applied", False)),
        "cast_once_fallback": rec.get("cast_once_fallback"),
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
