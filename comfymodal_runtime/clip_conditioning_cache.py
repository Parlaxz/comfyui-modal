"""Bounded, exact, cross-container cache for completed CPU CLIP conditioning.

Opt-in via ``COMFYMODAL_V2_CLIP_CONDITIONING_CACHE=1``.  When disabled
(default) every access is a miss, nothing is written, and the existing
prefill encode path is byte-for-byte unchanged.

Guarantees (fail closed on every violation):

* Only COMPLETED CPU CLIP conditioning is stored; every stored tensor is
  detached, on CPU, contiguous.
* Safe explicit serialization only — never pickle, ``torch.save``, or
  ``torch.load``.  Each entry is a self-describing JSON header (explicit
  tensor dtype/shape/offset/byte-length/checksum plus the full canonical
  key) plus one raw little-endian data blob.  SHA-256 covers the blob and
  the payload.
* Atomic writes: the data blob and header are written to unique temp
  files, fsync'd, and ``os.replace()``-d before the manifest is atomically
  replaced.  A partial/corrupt/checksum-mismatched entry is a miss.
* Bounded storage: hard entry cap and byte cap with deterministic LRU
  eviction (oldest ``last_access_seq``; ties broken by ``key_hash``).
* Validation before reuse: schema/format version, full canonical key
  equality, model identity, per-tensor dtype/shape/byte-range, per-tensor
  checksums, and the payload checksum.  Any mismatch is a miss.
* No user input images or unrelated workflow state are stored — only
  conditioning tensors plus the exact key components (identities/hashes
  and prompt text).
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
import time
import uuid
from collections import deque
from collections.abc import Mapping as ABCMapping
from dataclasses import dataclass
from typing import Any, Mapping

from .env import env_flag

# ── Experiment 5 (conditioning_hit) accessors — fail-open when the
#    v2_experiments registry is absent so the cache never breaks imports. ──
try:
    from .v2_experiments import (
        conditioning_async_lru_enabled as _conditioning_async_lru_enabled,
        experiment_line as _v2_experiment_line,
        resolve_experiment as _v2_resolve_experiment,
    )
except Exception:
    _conditioning_async_lru_enabled = lambda: False  # type: ignore
    _v2_experiment_line = lambda _s: ""  # type: ignore
    _v2_resolve_experiment = lambda _n: None  # type: ignore

# ── Env surface (opt-in; all defaults preserve current behavior) ────────
ENV_ENABLED = "COMFYMODAL_V2_CLIP_CONDITIONING_CACHE"
ENV_ENABLED_LEGACY = "COMFYMODAL_EXACT_CLIP_CONDITIONING_CACHE"
ENV_ROOT = "COMFYMODAL_EXACT_CLIP_CONDITIONING_CACHE_ROOT"
ENV_MAX_ENTRIES = "COMFYMODAL_EXACT_CLIP_CONDITIONING_CACHE_MAX_ENTRIES"
ENV_MAX_BYTES = "COMFYMODAL_EXACT_CLIP_CONDITIONING_CACHE_MAX_BYTES"
# Throttle interval (seconds) for the persistence WORKER's reload-before-
# batch, the ONLY Volume reload in the cache.  The lookup path performs zero
# Volume RPCs.  <=0 means "reload at most once per process".
ENV_RELOAD_INTERVAL_S = "COMFYMODAL_EXACT_CLIP_CONDITIONING_CACHE_RELOAD_INTERVAL_S"
# Bound on the background persistence queue (entries awaiting a batch write).
ENV_MAX_QUEUE = "COMFYMODAL_EXACT_CLIP_CONDITIONING_CACHE_MAX_QUEUE"
# Bound on the background LRU-touch queue (touched digests awaiting a
# coalesced manifest rewrite) — Experiment 5 async_lru arm.
ENV_MAX_LRU_QUEUE = "COMFYMODAL_EXACT_CLIP_CONDITIONING_CACHE_MAX_LRU_QUEUE"
# RUN-6 (serve-by-components): bounded number of the manifest's existing
# entries whose header+data are ALSO prefetched (keyed by their OWN stored
# digests) so a demand lookup whose plan-time digest drifted can still be
# served via the component-match scan.  Clamped to [0, 8].
ENV_PREFETCH_MAX_ENTRIES = "COMFYMODAL_V2_CONDITIONING_PREFETCH_MAX_ENTRIES"
_PREFETCH_MAX_ENTRIES_DEFAULT = 3

SCHEMA_VERSION = 1
FORMAT_VERSION = 1
FORMAT_NAME = "comfymodal_exact_clip_conditioning"

_DEFAULT_ROOT = "/root/prompt_cache_vol/exact_conditioning"
_DEFAULT_MAX_ENTRIES = 64
_DEFAULT_MAX_BYTES = 512 * 1024 * 1024
_DEFAULT_RELOAD_INTERVAL_S = 15.0
_DEFAULT_MAX_QUEUE = 256

# Key components that must be non-empty for the cache to be usable.  When
# any of these is unavailable from request metadata the lookup/store fails
# closed (miss, no write) rather than silently weakening the exact key.
_REQUIRED_KEY_FIELDS = (
    "clip_identity",
    "clip_type",
    "loader_class",
    "model_generation",
    "workflow_hash",
    "deployment_hash",
    "custom_node_generation",
    "production_options_hash",
    "tokenizer_identity",
    "compute_dtype",
    "torch_version",
)
_KEY_VALIDATION_SCOPE = (
    "clip_model_workflow_custom_nodes_schema_format_side_conditioning_inputs"
)

_LOG_EMITTED = False
_LOG_LOCK = threading.Lock()
_LAST_SERIALIZE_ERROR = ""

# Experiment 5 (conditioning_hit async_lru) one-time per-process logs.
_LRU_EXPERIMENT_LOGGED = False
_LRU_SYNC_FALLBACK_LOGGED = False


def _lru_experiment_log_once() -> None:
    """Print the canonical ``[v2.experiment]`` line once per process when the
    async_lru arm is first exercised.  Never raises."""
    global _LRU_EXPERIMENT_LOGGED
    with _LOG_LOCK:
        if _LRU_EXPERIMENT_LOGGED:
            return
        _LRU_EXPERIMENT_LOGGED = True
    try:
        _sel = _v2_resolve_experiment("conditioning_hit")  # type: ignore[arg-type]
        print(_v2_experiment_line(_sel), flush=True)  # type: ignore[arg-type]
    except Exception:
        pass


def _lru_sync_fallback_log_once() -> None:
    """Log once per process when the LRU worker could not be started and a
    touch fell back to the synchronous manifest rewrite.  Never raises."""
    global _LRU_SYNC_FALLBACK_LOGGED
    with _LOG_LOCK:
        if _LRU_SYNC_FALLBACK_LOGGED:
            return
        _LRU_SYNC_FALLBACK_LOGGED = True
    try:
        print(
            "[cache.lru] worker_start_failed falling_back_to_sync_touch",
            flush=True,
        )
    except Exception:
        pass

try:  # measurement-only diagnostics must never break the cache path
    from .optimization_diagnostics import opt_diag_enabled
except Exception:  # pragma: no cover - diagnostics absent => off
    opt_diag_enabled = lambda: False

_OPT_DIAG = opt_diag_enabled()
"""Frozen measurement-only gate (off by default)."""

_OPT_LAST_LOOKUP_DIAG_MAX = 8
_OPT_LAST_LOOKUP_DIAG: dict[str, dict[str, Any]] = {}
_OPT_LAST_LOOKUP_DIAG_LOCK = threading.Lock()
_OPT_LOOKUP_DIAG_SEQ = 0


def _opt_store_last_lookup_diag(diag: Mapping[str, Any], request_id: Any) -> None:
    """Bounded store of the most recent measurement-only lookup diag.

    Keyed by request id + a monotonic sequence counter; the oldest entry
    is evicted beyond ``_OPT_LAST_LOOKUP_DIAG_MAX``.  No-op when
    diagnostics are off (the dict then stays empty).
    """
    if not _OPT_DIAG:
        return
    global _OPT_LOOKUP_DIAG_SEQ
    with _OPT_LAST_LOOKUP_DIAG_LOCK:
        _OPT_LOOKUP_DIAG_SEQ += 1
        _key = f"{_s(request_id)}:{_OPT_LOOKUP_DIAG_SEQ}"
        _OPT_LAST_LOOKUP_DIAG[_key] = dict(diag)
        while len(_OPT_LAST_LOOKUP_DIAG) > _OPT_LAST_LOOKUP_DIAG_MAX:
            _OPT_LAST_LOOKUP_DIAG.pop(next(iter(_OPT_LAST_LOOKUP_DIAG)))


def opt_last_lookup_diag() -> dict[str, Any] | None:
    """Return the most recent measurement-only lookup diag, else ``None``.

    Intended for tests / orchestrator trace attachment; never affects
    cache behavior.  Always ``None`` when diagnostics are off.
    """
    if not _OPT_DIAG:
        return None
    with _OPT_LAST_LOOKUP_DIAG_LOCK:
        if not _OPT_LAST_LOOKUP_DIAG:
            return None
        return dict(next(reversed(list(_OPT_LAST_LOOKUP_DIAG.values()))))


def _log_once(flag_name: str, **kv: Any) -> None:
    global _LOG_EMITTED
    with _LOG_LOCK:
        if _LOG_EMITTED:
            return
        _LOG_EMITTED = True
        _parts = [f"{k}={v if v is not None else 'absent'}" for k, v in kv.items()]
        try:
            print(
                f"[v2.clip_conditioning_cache] event=mode "
                f"flag={flag_name} " + " ".join(_parts),
                flush=True,
            )
        except Exception:
            pass


def _log_decision(decision: str, **kv: Any) -> None:
    _parts = [f"{k}={v if v is not None else 'absent'}" for k, v in kv.items()]
    try:
        print(
            f"[v2.clip_conditioning_cache] decision={decision} " + " ".join(_parts),
            flush=True,
        )
    except Exception:
        pass


def log_conditioning_cache_decision(decision: str, **kv: Any) -> None:
    """Public decision logger (same concise style as the internal one)."""
    _log_decision(decision, **kv)


# ── Canonical key encoding ──────────────────────────────────────────────


def _s(value: Any) -> str:
    return str(value or "")


def _canonical_json(value: Any) -> str:
    return json.dumps(
        _jsonable(value), sort_keys=True, separators=(",", ":"), ensure_ascii=False,
        allow_nan=False,
    )


def _jsonable(value: Any) -> Any:
    if isinstance(value, ABCMapping):
        return {
            str(key): _jsonable(item)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    raise TypeError(f"unsupported key value: {type(value).__name__}")


def _canonical_value(value: Any) -> Any:
    return json.loads(_canonical_json(value))


def build_exact_key_components(ctx: Mapping[str, Any]) -> dict[str, Any]:
    """Canonical, deterministic key components for one CLIP encode.

    Every conditioning-affecting input available at the prefill boundary is
    included.  ``entry_layer``/``entry_skip`` are always present as empty
    fields because the native ``CLIPTextEncode`` node has no layer/skip
    inputs at this boundary — the fields exist in the schema so a future
    node with such inputs cannot produce a colliding key.

    ``cache_nonce`` is a benchmark-only, semantic-neutral key isolation
    field: a fresh value forces a MISS even when the ordinary key exists.  It
    is CONDITIONAL — included only when ``ctx["cache_nonce"]`` is a non-empty
    string, so the canonical key JSON is byte-identical when the nonce is
    absent (never an empty-string placeholder).  It never reaches
    tokenization/encode/model inputs or the sampler.
    """
    filenames = [str(f) for f in (ctx.get("filenames") or []) if str(f or "").strip()]
    components = {
        "schema_version": int(ctx.get("schema_version", SCHEMA_VERSION)),
        "format_version": int(ctx.get("format_version", FORMAT_VERSION)),
        "clip_identity": _s(ctx.get("clip_identity")),
        "clip_type": _s(ctx.get("clip_type")),
        "loader_class": _s(ctx.get("loader_class")),
        "filenames": filenames,
        "weight_dtype": _s(ctx.get("weight_dtype")),
        "compute_dtype": _s(ctx.get("compute_dtype")),
        "torch_version": _s(ctx.get("torch_version")),
        "torch_num_threads": int(ctx.get("torch_num_threads", 0) or 0),
        "model_generation": _s(ctx.get("model_generation")),
        "tokenizer_identity": _s(ctx.get("tokenizer_identity")),
        "workflow_hash": _s(ctx.get("workflow_hash")),
        "deployment_hash": _s(ctx.get("deployment_hash")),
        "custom_node_generation": _s(ctx.get("custom_node_generation")),
        "production_options_hash": _s(ctx.get("production_options_hash")),
        "entry": {
            "node_class": _s(ctx.get("entry_node_class")),
            "role": _s(ctx.get("entry_role")),
            "prompt_input": _s(ctx.get("entry_prompt_input")),
            "text": _s(ctx.get("entry_text")),
            "conditioning_inputs": _canonical_value(
                ctx.get("entry_conditioning_inputs") or {}
            ),
            "adapter_chain": _canonical_value(ctx.get("entry_adapter_chain") or []),
            "layer": _canonical_value(ctx.get("entry_layer", "")),
            "skip": _canonical_value(ctx.get("entry_skip", "")),
        },
    }
    # Semantic-neutral conditioning-cache nonce (benchmark-only): conditional
    # top-level field — absent when empty so the byte layout is unchanged.
    _cache_nonce = str(ctx.get("cache_nonce") or "").strip()
    if _cache_nonce:
        components["cache_nonce"] = _cache_nonce
    return components


def exact_key_digest(components: Mapping[str, Any]) -> str:
    blob = _canonical_json(components)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def conditioning_cache_key_summary(
    base_ctx: Mapping[str, Any],
    entries: list[Mapping[str, Any]],
) -> dict[str, Any]:
    digests: list[str] = []
    missing: list[str] = []
    for entry in entries:
        components = build_exact_key_components(
            _merge_entry_context(base_ctx, entry)
        )
        digest = exact_key_digest(components)
        digests.append(digest)
        reason = _key_usable(components)
        if reason:
            missing.append(reason)
    if not digests:
        key_hash = "absent"
    elif len(digests) == 1:
        key_hash = digests[0]
    else:
        key_hash = hashlib.sha256(
            _canonical_json(sorted(digests)).encode("utf-8")
        ).hexdigest()
    summary = {
        "key_hash": key_hash,
        "identity_status": "valid" if digests and not missing else "invalid",
        "schema_version": SCHEMA_VERSION,
        "validation_scope": _KEY_VALIDATION_SCOPE,
        "missing": ",".join(sorted(set(missing))),
    }
    # Semantic-neutral conditioning-cache nonce (benchmark-only): surfaced so
    # telemetry shows WHICH nonce isolated this key; absent when unused (the
    # summary then carries no nonce key at all).
    _nonce = str(base_ctx.get("cache_nonce") or "").strip()
    if _nonce:
        summary["cache_nonce"] = _nonce
    return summary


def _merge_entry_context(base_ctx: Mapping[str, Any], entry: Mapping[str, Any]) -> dict[str, Any]:
    ctx = dict(base_ctx)
    ctx["entry_node_class"] = str(entry.get("node_class", "") or "")
    ctx["entry_role"] = str(entry.get("role", "") or "")
    ctx["entry_prompt_input"] = str(entry.get("prompt_input", "text") or "")
    ctx["entry_text"] = str(entry.get("text", "") or "")
    ctx["entry_adapter_chain"] = list(entry.get("adapter_chain") or [])
    ctx["entry_conditioning_inputs"] = {
        "clip": entry.get("clip_connection"),
        "text": entry.get("text_connection"),
        "text_source": list(entry.get("text_source") or []),
    }
    ctx["entry_layer"] = entry.get("layer", ctx.get("entry_layer", ""))
    ctx["entry_skip"] = entry.get("skip", ctx.get("entry_skip", ""))
    # Per-entry loader identity (authoritative for this CLIPTextEncode).
    if entry.get("loader_class"):
        ctx["loader_class"] = str(entry["loader_class"])
    if entry.get("clip_type"):
        ctx["clip_type"] = str(entry["clip_type"])
    filenames = entry.get("filenames") or []
    if isinstance(filenames, (list, tuple)) and filenames:
        ctx["filenames"] = [str(f) for f in filenames]
    # Tokenizer identity is determined by the CLIP family (clip_type) and
    # the loader class; the tokenizer itself is not available before the
    # CLIP object is constructed at this boundary.
    return ctx


def _key_usable(components: Mapping[str, Any]) -> str:
    """Return '' when the key is complete, else the missing field name."""
    for name in _REQUIRED_KEY_FIELDS:
        if not _s(components.get(name)):
            return name
    filenames = components.get("filenames") or []
    if not any(str(f or "").strip() for f in filenames):
        return "filenames"
    entry = components.get("entry") or {}
    if not _s(entry.get("text")):
        return "entry.text"
    if not _s(entry.get("role")):
        return "entry.role"
    return ""


def _base_key_missing(components: Mapping[str, Any]) -> str:
    """Missing required SHARED field (ignores per-entry fields)."""
    for name in _REQUIRED_KEY_FIELDS:
        if not _s(components.get(name)):
            return name
    return ""


# ── Explicit tensor (de)serialization (no pickle / torch.load) ──────────


def _tensor_dtype_to_str(dtype: Any) -> str:
    name = str(dtype)
    if name.startswith("torch."):
        return name
    return f"torch.{name}"


def _numpy_dtype_for(torch_dtype: Any) -> Any:
    import numpy as _np
    import torch as _th

    if torch_dtype == _th.bfloat16:
        return _np.int16
    return {
        _th.float32: _np.float32,
        _th.float64: _np.float64,
        _th.float16: _np.float16,
        _th.int64: _np.int64,
        _th.int32: _np.int32,
        _th.int16: _np.int16,
        _th.int8: _np.int8,
        _th.uint8: _np.uint8,
        _th.bool: _np.bool_,
    }.get(torch_dtype, _np.float32)


def _torch_dtype_for(dtype_str: str) -> Any:
    import torch as _th

    clean = dtype_str[len("torch."):] if dtype_str.startswith("torch.") else dtype_str
    return getattr(_th, clean, _th.float32)


def _tensor_to_bytes(tensor: Any) -> tuple[bytes, str, list[int]]:
    """Return ``(raw_bytes, dtype_str, shape)`` for one detached CPU tensor.

    bfloat16 is stored through an int16 view (numpy cannot represent it).
    """
    import numpy as _np
    import torch as _th

    if tensor.requires_grad:
        raise ValueError("conditioning tensor must be detached")
    t = tensor.detach().to(device="cpu").contiguous()
    if t.dtype == _th.bfloat16:
        raw = t.view(_th.int16).numpy().tobytes()
    else:
        raw = t.numpy().tobytes()
    return raw, _tensor_dtype_to_str(t.dtype), list(t.shape)


def _bytes_to_tensor(
    raw: bytes,
    dtype_str: str,
    shape: list[int],
    *,
    _diag: dict[str, Any] | None = None,
) -> Any:
    import numpy as _np
    import torch as _th

    _rb_start = 0
    if _diag is not None:
        _rb_start = time.monotonic_ns()
    dtype = _torch_dtype_for(dtype_str)
    if dtype == _th.bfloat16:
        arr = _np.frombuffer(raw, dtype=_np.int16).reshape(list(shape))
        result = _th.from_numpy(arr.copy()).contiguous().view(_th.bfloat16)
    else:
        np_dtype = _numpy_dtype_for(dtype)
        arr = _np.frombuffer(raw, dtype=np_dtype).reshape(list(shape))
        result = _th.from_numpy(arr.copy()).contiguous()
    if _diag is not None:
        _diag["deser_tensor_rebuild_ms"] = _diag.get("deser_tensor_rebuild_ms", 0.0) + round(
            (time.monotonic_ns() - _rb_start) / 1_000_000, 3
        )
    return result


def _serialize_tensor_descriptor(
    tensor: Any,
    data_buf: bytearray,
    offset: int,
    _diag: dict[str, Any] | None = None,
) -> tuple[int, dict[str, Any]]:
    _mat_start = 0
    if _diag is not None:
        _mat_start = time.monotonic_ns()
    raw, dtype_str, shape = _tensor_to_bytes(tensor)
    if _diag is not None:
        _diag["materialize_ms"] = _diag.get("materialize_ms", 0.0) + round(
            (time.monotonic_ns() - _mat_start) / 1_000_000, 3
        )
        _diag["materialize_bytes"] = _diag.get("materialize_bytes", 0) + len(raw)
    length = len(raw)
    data_buf.extend(raw)
    _ck_start = 0
    if _diag is not None:
        _ck_start = time.monotonic_ns()
    checksum = hashlib.sha256(raw).hexdigest()
    if _diag is not None:
        _diag["checksum_ms"] = _diag.get("checksum_ms", 0.0) + round(
            (time.monotonic_ns() - _ck_start) / 1_000_000, 3
        )
    return length, {
        "dtype": dtype_str,
        "shape": shape,
        "offset": offset,
        "byte_length": length,
        "checksum": checksum,
    }


def serialize_conditioning(
    value: Any,
    _diag: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], bytes] | None:
    """Serialize one CLIPTextEncode output into ``(header, data_bytes)``.

    The native conditioning value is ``[[tensor, {"pooled": pooled}], ...]``.
    Returns ``None`` (fail closed — do not store) for anything else.
    """
    import torch as _th

    global _LAST_SERIALIZE_ERROR
    _LAST_SERIALIZE_ERROR = ""
    _ser_start = 0
    if _diag is not None:
        _ser_start = time.monotonic_ns()
    try:
        result_container = "list"
        if isinstance(value, tuple):
            if len(value) != 1:
                return None
            result_container = "tuple"
            value = value[0]
        if not isinstance(value, list) or not value:
            return None
        data_buf = bytearray()
        entries_out: list[dict[str, Any]] = []
        for entry in value:
            if not isinstance(entry, list) or len(entry) != 2:
                return None
            cond = entry[0]
            meta = entry[1] if len(entry) > 1 else {}
            if not isinstance(cond, _th.Tensor):
                return None
            _, cond_desc = _serialize_tensor_descriptor(cond, data_buf, len(data_buf), _diag=_diag)
            meta_out: list[dict[str, Any]] = []
            if not isinstance(meta, dict):
                return None
            for mk, mv in meta.items():
                if not isinstance(mk, str):
                    return None
                if isinstance(mv, _th.Tensor):
                    _, mv_desc = _serialize_tensor_descriptor(mv, data_buf, len(data_buf), _diag=_diag)
                    meta_out.append({"key": mk, "kind": "tensor", **mv_desc})
                elif isinstance(mv, (str, int, float, bool, type(None))):
                    meta_out.append({"key": mk, "kind": "raw", "value": mv})
                elif isinstance(mv, (list, dict)):
                    meta_out.append({
                        "key": mk,
                        "kind": "raw",
                        "value": _canonical_value(mv),
                    })
                else:
                    return None
            entries_out.append({"cond": cond_desc, "meta": meta_out})
        data = bytes(data_buf)
        _pk_start = 0
        if _diag is not None:
            _pk_start = time.monotonic_ns()
        payload_checksum = hashlib.sha256(data).hexdigest()
        if _diag is not None:
            _diag["checksum_ms"] = _diag.get("checksum_ms", 0.0) + round(
                (time.monotonic_ns() - _pk_start) / 1_000_000, 3
            )
        header = {
            "format": FORMAT_NAME,
            "schema_version": SCHEMA_VERSION,
            "format_version": FORMAT_VERSION,
            "result_container": result_container,
            "byte_length": len(data),
            "payload_checksum": payload_checksum,
            "conditioning": {"entries": entries_out},
        }
        if _diag is not None:
            _diag["serialize_ms"] = _diag.get("serialize_ms", 0.0) + round(
                (time.monotonic_ns() - _ser_start) / 1_000_000, 3
            )
            _diag["serialized_payload_bytes"] = _diag.get("serialized_payload_bytes", 0) + len(data)
        return header, data
    except Exception as exc:
        _LAST_SERIALIZE_ERROR = f"{type(exc).__name__}:{exc}"[:160]
        return None


def _deserialize_tensor_descriptor(
    desc: Mapping[str, Any],
    data: bytes,
    *,
    _diag: dict[str, Any] | None = None,
) -> Any:
    if not isinstance(desc, Mapping):
        return None
    try:
        dtype = str(desc.get("dtype", ""))
        shape = list(desc.get("shape") or [])
        offset = int(desc.get("offset", -1))
        byte_length = int(desc.get("byte_length", -1))
        checksum = str(desc.get("checksum", ""))
    except (TypeError, ValueError):
        return None
    if not dtype or not shape or offset < 0 or byte_length < 0:
        return None
    if any(not isinstance(s, int) or s < 0 for s in shape):
        return None
    if offset + byte_length > len(data):
        return None
    raw = data[offset:offset + byte_length]
    if len(raw) != byte_length:
        return None
    _sha_start = 0
    if _diag is not None:
        _sha_start = time.monotonic_ns()
    if checksum and hashlib.sha256(raw).hexdigest() != checksum:
        return None
    if _diag is not None:
        _diag["deser_tensor_sha_ms"] = _diag.get("deser_tensor_sha_ms", 0.0) + round(
            (time.monotonic_ns() - _sha_start) / 1_000_000, 3
        )
    try:
        tensor = _bytes_to_tensor(raw, dtype, shape, _diag=_diag)
    except Exception:
        return None
    if str(tensor.dtype) != dtype:
        return None
    if list(tensor.shape) != shape:
        return None
    if _diag is not None:
        _diag["deser_tensor_count"] = _diag.get("deser_tensor_count", 0) + 1
        _diag["deser_tensors_bytes"] = _diag.get("deser_tensors_bytes", 0) + byte_length
    return tensor


def deserialize_conditioning(
    header: Mapping[str, Any],
    data: bytes,
    *,
    _diag: dict[str, Any] | None = None,
) -> Any:
    """Rebuild a conditioning value from the header + data blob, or None.

    ``_diag`` is measurement-only: when provided, brackets the payload
    checksum and the per-entry result assembly.  Default ``None`` keeps
    behavior byte-for-byte identical.
    """
    try:
        if not isinstance(header, Mapping):
            return None
        if header.get("format") != FORMAT_NAME:
            return None
        if header.get("schema_version") != SCHEMA_VERSION:
            return None
        if header.get("format_version") != FORMAT_VERSION:
            return None
        if int(header.get("byte_length", -1)) != len(data):
            return None
        payload_checksum = str(header.get("payload_checksum", ""))
        _pk_start = 0
        if _diag is not None:
            _pk_start = time.monotonic_ns()
        if payload_checksum and hashlib.sha256(data).hexdigest() != payload_checksum:
            return None
        if _diag is not None:
            _diag["deser_payload_sha_ms"] = _diag.get("deser_payload_sha_ms", 0.0) + round(
                (time.monotonic_ns() - _pk_start) / 1_000_000, 3
            )
        cond = header.get("conditioning") or {}
        entries = cond.get("entries") or []
        if not isinstance(entries, list) or not entries:
            return None
        _mat_start = 0
        if _diag is not None:
            _mat_start = time.monotonic_ns()
        result = []
        for e in entries:
            if not isinstance(e, Mapping):
                return None
            cond_tensor = _deserialize_tensor_descriptor(e.get("cond"), data, _diag=_diag)
            if cond_tensor is None:
                return None
            meta_dict: dict[str, Any] = {}
            for mv in (e.get("meta") or []):
                if not isinstance(mv, Mapping):
                    return None
                key = str(mv.get("key", ""))
                if mv.get("kind") == "tensor":
                    mt = _deserialize_tensor_descriptor(mv, data, _diag=_diag)
                    if mt is None:
                        return None
                    meta_dict[key] = mt
                elif mv.get("kind") == "raw":
                    meta_dict[key] = mv.get("value")
                else:
                    return None
            result.append([cond_tensor, meta_dict])
        if _diag is not None:
            _diag["deser_materialize_ms"] = _diag.get("deser_materialize_ms", 0.0) + round(
                (time.monotonic_ns() - _mat_start) / 1_000_000, 3
            )
        if header.get("result_container") == "tuple":
            return (result,)
        if header.get("result_container") != "list":
            return None
        return result
    except Exception:
        return None


# ── Storage (atomic, bounded, deterministic LRU) ────────────────────────


def _atomic_write(path: str, data: bytes, _diag: dict[str, Any] | None = None) -> None:
    tmp = f"{path}.{uuid.uuid4().hex}.tmp"
    _fsync_ms = 0.0
    _fsync_count = 0
    try:
        with open(tmp, "wb") as f:
            f.write(data)
            f.flush()
            try:
                _fs_start = 0
                if _diag is not None:
                    _fs_start = time.monotonic_ns()
                os.fsync(f.fileno())
                if _diag is not None:
                    _fsync_ms += round((time.monotonic_ns() - _fs_start) / 1_000_000, 3)
                    _fsync_count += 1
            except OSError:
                pass
        os.replace(tmp, path)
        try:
            directory_fd = os.open(os.path.dirname(path) or ".", os.O_RDONLY)
            try:
                _fs_start = 0
                if _diag is not None:
                    _fs_start = time.monotonic_ns()
                os.fsync(directory_fd)
                if _diag is not None:
                    _fsync_ms += round((time.monotonic_ns() - _fs_start) / 1_000_000, 3)
                    _fsync_count += 1
            finally:
                os.close(directory_fd)
        except OSError:
            pass
    finally:
        try:
            if os.path.exists(tmp):
                os.remove(tmp)
        except OSError:
            pass
    if _diag is not None:
        _diag["fsync_ms"] = _diag.get("fsync_ms", 0.0) + _fsync_ms
        _diag["fsync_count"] = _diag.get("fsync_count", 0) + _fsync_count


def _atomic_write_text(path: str, text: str, _diag: dict[str, Any] | None = None) -> None:
    _atomic_write(path, text.encode("utf-8"), _diag=_diag)


@dataclass
class _PendingEntry:
    """Immutable queued payload handed from the foreground to the persistence
    thread.  ``data`` is materialized bytes, ``header`` and ``components``
    are plain dicts — nothing references live tensors, so crossing threads is
    safe."""

    components: dict[str, Any]
    header: dict[str, Any]
    data: bytes
    enqueue_mono_ns: float = 0.0


def _detect_mounted(root: str) -> bool:
    """Auto-detect whether *root* (or an ancestor) lives on a mounted volume.

    Walks up from the cache root; the first ``os.path.ismount()`` hit wins.
    In local-only / unmounted mode this returns False so the persistence
    thread issues ZERO reload/commit RPCs.
    """
    path = root
    while True:
        try:
            if os.path.ismount(path):
                return True
        except OSError:
            return False
        parent = os.path.dirname(path)
        if parent == path:
            return False
        path = parent


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, str(default)).strip())
    except (TypeError, ValueError):
        return default


def _safe_getsize(path: str) -> int | None:
    """Best-effort ``os.path.getsize``; ``None`` on any failure."""
    try:
        return int(os.path.getsize(path))
    except OSError:
        return None


class ExactConditioningCache:
    """File-backed bounded LRU for exact CLIP conditioning entries."""

    def __init__(
        self,
        root_dir: str,
        max_entries: int,
        max_bytes: int,
        mounted: bool | None = None,
    ) -> None:
        self._root = root_dir
        self._max_entries = max(1, int(max_entries))
        self._max_bytes = max(1, int(max_bytes))
        self._entries_dir = os.path.join(self._root, "entries")
        self._manifest_path = os.path.join(self._root, "manifest.json")
        self._lock = threading.RLock()
        self._commit_hook: Any = None
        self._reload_hook: Any = None
        self._last_store_reason = ""
        # True when the cache root lives on a mounted volume (or an ancestor
        # does).  When False the persistence thread skips commit/reload
        # entirely (local-only mode → ZERO Volume RPCs).
        if mounted is None:
            mounted = _detect_mounted(self._root)
        self._mounted = bool(mounted)
        # Throttled reload state (Stage 2).
        self._reload_interval_s = _env_float(ENV_RELOAD_INTERVAL_S, _DEFAULT_RELOAD_INTERVAL_S)
        self._last_reload_mono: float | None = None
        self._reload_once_done = False
        # Background persistence queue + worker (Stages 1/3).
        self._queue_cond = threading.Condition(self._lock)
        self._pending: deque[_PendingEntry] = deque()
        self._pending_keys: set[str] = set()
        self._max_queue = max(1, int(_env_int(ENV_MAX_QUEUE, _DEFAULT_MAX_QUEUE)))
        self._closing = False
        self._worker: threading.Thread | None = None
        self._worker_broken = False
        self._worker_exited = False
        self._dirty_since_commit = False
        # Experiment 5 (conditioning_hit async_lru): bounded background LRU-
        # touch queue + worker.  LRU state is PURE eviction/recency metadata —
        # ``_lookup_entry`` never reads ``last_access_seq`` and only
        # ``_enforce_bounds`` consumes it — so a dropped/queued touch can
        # never change a hit/miss outcome.  Default arm (sync_lru) never
        # touches any of this state.
        self._pending_lru: set[str] = set()
        self._lru_cond = threading.Condition(self._lock)
        self._lru_worker: threading.Thread | None = None
        self._lru_closing = False
        self._max_lru_queue = max(
            16, min(65536, _env_int(ENV_MAX_LRU_QUEUE, 1024))
        )
        self._lru_diag: dict[str, Any] = {
            "lru_async_enqueued": 0,
            "lru_async_batches": 0,
            "lru_async_batch_size": 0,
            "lru_async_persist_ms": 0.0,
            "lru_async_dropped": 0,
            "lru_async_failed": 0,
            "lru_async_flush_count": 0,
        }
        # Shared thread-safe diagnostics (replaces the old threading.local()).
        self._diag_lock = threading.Lock()
        self._lookup_diag: dict[str, Any] | None = None
        self._store_diag: dict[str, Any] | None = None
        self._worker_diag: dict[str, Any] = {
            "enqueued": 0,
            "persisted": 0,
            "persist_failed": 0,
            "commit_failed": 0,
            "queue_depth": 0,
            "queue_deduped": 0,
            "queue_full_dropped": 0,
            "batch_size": 0,
            "batch_count": 0,
            "persistence_queue_wait_ms": 0.0,
            "file_write_ms": 0.0,
            "manifest_ms": 0.0,
            "reload_ms": 0.0,
            "commit_ms": 0.0,
            "lock_wait_ms": 0.0,
            "unindexed_files_removed": 0,
            "last_flush_ms": 0.0,
            "last_flush_status": "",
            "flush_count": 0,
            "fallback_sync_stores": 0,
        }
        # ── Plan-time prefetch + in-memory cache (Task 2) ────────────────
        # Plan-time background prefetch reads the manifest + entry bytes into
        # memory so demand-time lookup can serve an exact hit without the
        # cold Modal-Volume file reads.  ALL memory state is guarded by
        # ``_prefetch_lock`` (SEPARATE from ``self._lock``; the two are never
        # nested — the lookup path snapshots before acquiring ``self._lock``
        # and defers memory-entry discards until after releasing it).  Any
        # validation failure or self-store/commit invalidates the memory
        # entries (fail closed to the normal file path).
        self._prefetch_lock = threading.Lock()
        self._mem_manifest: dict[str, Any] | None = None
        self._mem_manifest_mono_ns: int = 0
        self._mem_manifest_mtime_ns: int = 0
        self._mem_manifest_size: int = 0
        self._mem_payloads: dict[str, dict[str, Any]] = {}
        self._mem_invalidated = False
        self._prefetch_diag: dict[str, Any] = {
            "prefetch_requested": 0,
            "prefetch_loaded": 0,
            "prefetch_failures": 0,
            "prefetch_manifest_bytes": 0,
            "prefetch_payload_bytes": 0,
            "prefetch_wall_ms": 0.0,
            "prefetch_reload_ms": 0.0,
            "prefetch_source": "none",
        }
        # Throttle for the prefetch-time volume reload — a separate throttle
        # from ``_maybe_reload``; its duration lives ONLY in the prefetch
        # diagnostics (never in the lookup-path ``volume_reload_ms``).
        # RUN-2: the FIRST prefetch of the container SKIPS the reload
        # entirely (single-use request containers see the latest volume
        # commit at mount); ``_prefetch_reload_count`` distinguishes the
        # first prefetch from later ones (which keep the throttled reload).
        self._prefetch_last_reload_mono: float | None = None
        self._prefetch_reload_count: int = 0
        self._prefetch_reload_interval_s = _env_float(
            "COMFYMODAL_EXACT_CLIP_CONDITIONING_CACHE_PREFETCH_RELOAD_INTERVAL_S",
            _DEFAULT_RELOAD_INTERVAL_S,
        )
        # RUN-2: in-flight prefetch join events keyed by request_id (guarded
        # by ``_prefetch_lock``).  ``prefetch_entries`` registers an Event
        # BEFORE any slow work and sets it in a ``finally``; the demand-time
        # prefill hook calls ``join_prefetch`` (bounded) so the memory
        # manifest/payloads are installed before the demand lookup.
        self._prefetch_events: dict[str, threading.Event] = {}
        os.makedirs(self._entries_dir, exist_ok=True)

    # ── Commit hook (registered by the Modal prompt-cache volume owner) ──
    def set_commit_hook(self, hook: Any) -> None:
        with self._lock:
            self._commit_hook = hook

    # ── Reload hook (test seam; production leaves it None) ──────────────
    def set_reload_hook(self, hook: Any) -> None:
        with self._lock:
            self._reload_hook = hook

    def _commit(self) -> bool:
        """Run the registered commit hook.  Returns True when there is
        nothing to commit or the commit succeeded; False on hook failure.
        Never raises.  In local-only/unmounted mode this is a no-op (ZERO
        Volume RPCs) even when a hook is registered."""
        if not self._mounted:
            return True
        hook = self._commit_hook
        if hook is None:
            return True
        # A commit may surface other containers' state and always follows a
        # local self-store — prefetched in-memory bytes are superseded (fail
        # closed).  No ``self._lock`` is held here (test-pinned), so the
        # ``_prefetch_lock`` acquisition is safe.
        self._invalidate_mem()
        try:
            hook()
            return True
        except Exception as exc:
            _log_decision("persist_commit_error", reason=f"{type(exc).__name__}:{exc}"[:120])
            return False

    def _maybe_reload(self) -> None:
        """Throttled Modal volume reload (called under ``self._lock``).

        Skips entirely in local-only/unmounted mode and when no Modal volume
        is in play (no reload/commit hook registered).  Otherwise reloads at
        most once per ``_reload_interval_s`` (or once per process when the
        interval is <= 0).  Any failure fails closed to a miss.
        """
        if not self._mounted:
            return
        if self._reload_hook is None and self._commit_hook is None:
            return
        now = time.monotonic()
        if self._reload_interval_s <= 0:
            if self._reload_once_done:
                return
            self._reload_once_done = True
        elif self._last_reload_mono is not None:
            if now - self._last_reload_mono < self._reload_interval_s:
                return
        _rl_start = time.monotonic_ns()
        try:
            if self._reload_hook is not None:
                self._reload_hook()
            else:
                self._reload_volume()
        finally:
            self._last_reload_mono = time.monotonic()
            self._accumulate_worker(
                "reload_ms",
                round((time.monotonic_ns() - _rl_start) / 1_000_000, 3),
            )

    # ── Manifest ────────────────────────────────────────────────────────
    def _read_manifest(self, _diag: dict[str, Any] | None = None) -> dict[str, Any]:
        try:
            with open(self._manifest_path, "r", encoding="utf-8") as f:
                _text = f.read()
            if _diag is not None:
                _diag["manifest_read_bytes"] = _diag.get("manifest_read_bytes", 0) + len(
                    _text.encode("utf-8")
                )
            data = json.loads(_text)
            if not isinstance(data, dict):
                raise ValueError("manifest_not_dict")
            if data.get("schema_version") != SCHEMA_VERSION:
                raise ValueError("schema_version_mismatch")
            entries = data.get("entries")
            if not isinstance(entries, list):
                raise ValueError("entries_not_list")
            return data
        except (FileNotFoundError, json.JSONDecodeError, OSError, ValueError):
            return {
                "schema_version": SCHEMA_VERSION,
                "format_version": FORMAT_VERSION,
                "next_seq": 0,
                "entries": [],
            }

    def _write_manifest_atomic(self, manifest: dict[str, Any], _diag: dict[str, Any] | None = None) -> None:
        manifest["schema_version"] = SCHEMA_VERSION
        manifest["format_version"] = FORMAT_VERSION
        _text = json.dumps(manifest, sort_keys=True, separators=(",", ":"))
        if _diag is not None:
            _diag["manifest_bytes_written"] = _diag.get("manifest_bytes_written", 0) + len(
                _text.encode("utf-8")
            )
        _atomic_write_text(self._manifest_path, _text, _diag=_diag)

    def _entry_paths(self, key_hash: str) -> tuple[str, str]:
        return (
            os.path.join(self._entries_dir, f"{key_hash}.header.json"),
            os.path.join(self._entries_dir, f"{key_hash}.data.bin"),
        )

    def _remove_unindexed_files(self, manifest: Mapping[str, Any]) -> int:
        indexed = {
            str(entry.get("key_hash", ""))
            for entry in manifest.get("entries", [])
            if isinstance(entry, Mapping) and entry.get("key_hash")
        }
        try:
            names = os.listdir(self._entries_dir)
        except OSError:
            return 0
        _removed = 0
        for name in names:
            if name.endswith(".header.json"):
                key_hash = name[:-len(".header.json")]
            elif name.endswith(".data.bin"):
                key_hash = name[:-len(".data.bin")]
            else:
                continue
            if key_hash in indexed:
                continue
            try:
                os.remove(os.path.join(self._entries_dir, name))
                _removed += 1
            except OSError:
                pass
        return _removed

    # ── Plan-time prefetch + in-memory cache (Task 2) ────────────────────

    def _prefetch_maybe_reload(self) -> tuple[float, str]:
        """Throttled Modal volume reload for the prefetch path only.

        RUN-2: SKIPS the reload entirely on the FIRST prefetch of the
        container (status ``skipped_first``) — single-use request containers
        see the latest volume commit at mount, so the reload adds latency
        without freshness (the explorer research documented this).  Later
        prefetches keep the throttled reload (long-lived containers).  Any
        reload duration is recorded ONLY in the prefetch diagnostics —
        never in the lookup-path ``volume_reload_ms`` (test-pinned to ~0.0
        on lookup).  Any failure is a miss.  Returns ``(reload_ms, status)``
        where status is one of ``ran`` / ``skipped_first`` /
        ``skipped_throttled`` / ``skipped_unmounted`` / ``skipped_no_hooks``.
        """
        if not self._mounted:
            return 0.0, "skipped_unmounted"
        if self._reload_hook is None and self._commit_hook is None:
            return 0.0, "skipped_no_hooks"
        if self._prefetch_reload_count == 0:
            self._prefetch_reload_count = 1
            return 0.0, "skipped_first"
        now = time.monotonic()
        if self._prefetch_last_reload_mono is not None:
            if now - self._prefetch_last_reload_mono < self._prefetch_reload_interval_s:
                return 0.0, "skipped_throttled"
        _rl_start = time.monotonic_ns()
        try:
            if self._reload_hook is not None:
                self._reload_hook()
            else:
                self._reload_volume()
        except Exception:
            pass
        finally:
            self._prefetch_last_reload_mono = time.monotonic()
            self._prefetch_reload_count += 1
        return round((time.monotonic_ns() - _rl_start) / 1_000_000, 3), "ran"

    def _mem_state_snapshot(self) -> dict[str, Any]:
        """Snapshot the prefetch memory state under ``_prefetch_lock``.

        Called BEFORE acquiring ``self._lock`` so ``_prefetch_lock`` is never
        nested inside it.  The snapshot holds the current manifest dict and
        payload map references plus the prefetch diagnostics.
        """
        with self._prefetch_lock:
            return {
                "manifest": self._mem_manifest,
                "manifest_mono_ns": self._mem_manifest_mono_ns,
                "manifest_mtime_ns": self._mem_manifest_mtime_ns,
                "manifest_size": self._mem_manifest_size,
                "payloads": self._mem_payloads,
                "invalidated": self._mem_invalidated,
                "prefetch_diag": dict(self._prefetch_diag),
            }

    def _mem_manifest_stale(self, mem_state: Mapping[str, Any]) -> bool:
        """True when the on-disk manifest no longer matches the prefetched
        copy (mtime/size changed since the prefetch read)."""
        if not mem_state.get("manifest"):
            return True
        try:
            _st = os.stat(self._manifest_path)
        except OSError:
            return True
        if not _st.st_size:
            return False
        if int(_st.st_mtime_ns) != int(mem_state.get("manifest_mtime_ns") or 0):
            return True
        if int(_st.st_size) != int(mem_state.get("manifest_size") or 0):
            return True
        return False

    def _invalidate_mem_locked(self) -> None:
        """Mark prefetched memory state stale.  Caller holds ``self._lock``;
        the plain attribute write is GIL-atomic and never acquires
        ``_prefetch_lock`` (the no-nesting rule holds)."""
        self._mem_invalidated = True

    def _invalidate_mem(self) -> None:
        """Mark prefetched memory state stale (no ``self._lock`` held)."""
        with self._prefetch_lock:
            self._mem_invalidated = True

    def _discard_mem_payloads(self, digests: set[str]) -> None:
        """Drop failed memory entries.  Called OUTSIDE ``self._lock`` so
        ``_prefetch_lock`` is never nested inside it."""
        if not digests:
            return
        with self._prefetch_lock:
            for _d in digests:
                self._mem_payloads.pop(_d, None)

    def prefetch_entries(
        self,
        base_ctx: Mapping[str, Any],
        entries: list[Mapping[str, Any]],
        request_id: str = "",
    ) -> dict[str, Any]:
        """Best-effort plan-time prefetch of exact conditioning entries.

        Reads the manifest and each requested entry's header + data blob
        into memory so a later demand-time ``lookup_many`` can serve an
        exact hit without cold file reads.  Runs ONE throttled volume
        reload (recorded only in the prefetch diagnostics).  Prefetch-time
        validation mirrors the demand-time header rules (parse + format /
        schema / format-version / key_hash + manifest byte_length); the
        FULL canonical-key / model-identity / checksum validation still runs
        at demand time on the in-memory bytes (fail closed).  Entries whose
        files do not exist are skipped.  A missing manifest is recorded and
        returns (fail-open to a plain demand-time miss).  Never raises,
        never touches the coordinator pool, and never blocks lookups on the
        prefetch lock.  Returns a small diagnostics dict
        ``{requested, loaded, failures, manifest_bytes, payload_bytes,
        wall_ms, source, prefetch_reload_ms}``.
        """
        _t0 = time.monotonic_ns()
        _rid = str(request_id or "")
        # RUN-2: register the in-flight join event BEFORE any slow work so a
        # demand-time ``join_prefetch`` can wait for this prefetch.  The
        # Event is set (and the registration dropped) in the ``finally``.
        _done_event = threading.Event()
        with self._prefetch_lock:
            self._prefetch_events[_rid] = _done_event
        diag: dict[str, Any] = {
            "requested": 0,
            "loaded": 0,
            "failures": 0,
            "manifest_bytes": 0,
            "payload_bytes": 0,
            "wall_ms": 0.0,
            "source": "none",
            "prefetch_reload": "",
        }
        try:
            requested = list(entries) if isinstance(entries, (list, tuple)) else []
            if requested:
                diag["requested"] = len(requested)
            _reload_ms, _reload_status = self._prefetch_maybe_reload()
            diag["prefetch_reload"] = _reload_status
            if _reload_ms:
                diag["prefetch_reload_ms"] = _reload_ms
            _mr_diag: dict[str, Any] = {}
            try:
                manifest = self._read_manifest(_diag=_mr_diag)
            except Exception:
                manifest = None
            if manifest is not None:
                diag["manifest_bytes"] = int(_mr_diag.get("manifest_read_bytes", 0))
            if not manifest or not manifest.get("entries"):
                # Missing/empty manifest: record and return.  The memory
                # manifest is NOT installed so the demand path stays on the
                # file read (fail-open to a normal miss).
                diag["source"] = "manifest_missing"
            else:
                manifest_entries = {
                    str(e.get("key_hash", "")): e
                    for e in manifest.get("entries", [])
                    if isinstance(e, Mapping) and e.get("key_hash")
                }
                mem_payloads: dict[str, dict[str, Any]] = {}
                loaded = 0
                failures = 0
                payload_bytes = 0
                for entry in requested:
                    try:
                        ctx = _merge_entry_context(base_ctx, entry)
                        components = build_exact_key_components(ctx)
                        missing = _key_usable(components)
                        if missing:
                            failures += 1
                            continue
                        digest = exact_key_digest(components)
                        if digest not in manifest_entries:
                            continue  # not in the manifest -> nothing to load
                        header_path, data_path = self._entry_paths(digest)
                        if not os.path.isfile(header_path) or not os.path.isfile(data_path):
                            continue  # skip entries whose files don't exist
                        with open(header_path, "rb") as _hf:
                            header_bytes = _hf.read()
                        header = json.loads(header_bytes.decode("utf-8"))
                        if not isinstance(header, Mapping):
                            failures += 1
                            continue
                        # Same header-level rules as _lookup_entry (full
                        # canonical-key equality is deferred to demand time
                        # on the in-memory bytes).
                        if header.get("format") != FORMAT_NAME:
                            failures += 1
                            continue
                        if header.get("schema_version") != SCHEMA_VERSION:
                            failures += 1
                            continue
                        if header.get("format_version") != FORMAT_VERSION:
                            failures += 1
                            continue
                        if header.get("key_hash") != digest:
                            failures += 1
                            continue
                        with open(data_path, "rb") as _df:
                            data_bytes = _df.read()
                        if int(manifest_entries[digest].get("byte_length", -1)) != len(data_bytes):
                            failures += 1
                            continue
                        mem_payloads[digest] = {
                            "header_bytes": header_bytes,
                            "data_bytes": data_bytes,
                            "read_mono_ns": time.monotonic_ns(),
                        }
                        payload_bytes += len(data_bytes)
                        loaded += 1
                    except (OSError, json.JSONDecodeError, TypeError, ValueError, UnicodeDecodeError):
                        failures += 1
                        continue
                # ── RUN-6 (serve-by-components) fallback: also prefetch a
                #    BOUNDED number of the manifest's existing entries, keyed
                #    by their OWN stored digests (read from each header), so
                #    a demand lookup whose plan-time digest drifted can still
                #    be served via the component-match scan.  The plan-time
                #    digest rarely equals a stored digest (compute_dtype /
                #    tokenizer_identity approximations drift), so this is the
                #    path that actually populates the payload memory store. ──
                try:
                    _prefetch_max_entries = max(
                        0, min(8, int(os.environ.get(ENV_PREFETCH_MAX_ENTRIES, str(_PREFETCH_MAX_ENTRIES_DEFAULT)) or "0"))
                    )
                except (TypeError, ValueError):
                    _prefetch_max_entries = _PREFETCH_MAX_ENTRIES_DEFAULT
                _manifest_loaded = 0
                for _manifest_entry in reversed(manifest.get("entries", [])):
                    if _manifest_loaded >= _prefetch_max_entries:
                        break
                    if not isinstance(_manifest_entry, Mapping):
                        continue
                    _stored_digest = str(_manifest_entry.get("key_hash", "") or "")
                    if not _stored_digest or _stored_digest in mem_payloads:
                        continue
                    _m_hdr_path, _m_data_path = self._entry_paths(_stored_digest)
                    try:
                        if not os.path.isfile(_m_hdr_path) or not os.path.isfile(_m_data_path):
                            continue
                        with open(_m_hdr_path, "rb") as _mhf:
                            _m_header_bytes = _mhf.read()
                        _m_header = json.loads(_m_header_bytes.decode("utf-8"))
                        if not isinstance(_m_header, Mapping):
                            continue
                        _own_digest = str(_m_header.get("key_hash", "") or "")
                        if not _own_digest or _own_digest in mem_payloads:
                            continue
                        # Same header-level rules as the plan-digest path.
                        if (
                            _m_header.get("format") != FORMAT_NAME
                            or _m_header.get("schema_version") != SCHEMA_VERSION
                            or _m_header.get("format_version") != FORMAT_VERSION
                        ):
                            continue
                        with open(_m_data_path, "rb") as _mdf:
                            _m_data_bytes = _mdf.read()
                        if int(_manifest_entry.get("byte_length", -1)) != len(_m_data_bytes):
                            continue
                        mem_payloads[_own_digest] = {
                            "header_bytes": _m_header_bytes,
                            "data_bytes": _m_data_bytes,
                            "read_mono_ns": time.monotonic_ns(),
                        }
                        payload_bytes += len(_m_data_bytes)
                        loaded += 1
                        _manifest_loaded += 1
                    except (OSError, json.JSONDecodeError, TypeError, ValueError, UnicodeDecodeError):
                        continue
                # Install the memory manifest even when zero payloads loaded
                # (manifest-only prefetch still skips the cold manifest read).
                with self._prefetch_lock:
                    self._mem_manifest = dict(manifest)
                    self._mem_manifest_mono_ns = _t0
                    try:
                        _st = os.stat(self._manifest_path)
                        self._mem_manifest_mtime_ns = int(_st.st_mtime_ns)
                        self._mem_manifest_size = int(_st.st_size)
                    except OSError:
                        self._mem_manifest_mtime_ns = 0
                        self._mem_manifest_size = 0
                    if mem_payloads:
                        self._mem_payloads.update(mem_payloads)
                    self._mem_invalidated = False
                diag["loaded"] = loaded
                diag["failures"] = failures
                diag["payload_bytes"] = payload_bytes
                diag["prefetch_payload_entries"] = loaded
                diag["source"] = "full" if loaded else "manifest_only"
        except Exception as exc:
            diag["failures"] = diag.get("failures", 0) + 1
            try:
                print(
                    f"[cache.prefetch] failed reason={type(exc).__name__}:{exc}"[:200],
                    flush=True,
                )
            except Exception:
                pass
        finally:
            # RUN-2: signal demand-time joiners that this prefetch finished
            # (success OR failure) and drop the in-flight registration.
            with self._prefetch_lock:
                self._prefetch_events.pop(_rid, None)
            _done_event.set()
        diag["wall_ms"] = round((time.monotonic_ns() - _t0) / 1_000_000, 3)
        with self._prefetch_lock:
            self._prefetch_diag = {
                "prefetch_requested": diag["requested"],
                "prefetch_loaded": diag["loaded"],
                "prefetch_failures": diag["failures"],
                "prefetch_manifest_bytes": diag["manifest_bytes"],
                "prefetch_payload_bytes": diag["payload_bytes"],
                "prefetch_payload_entries": diag.get("prefetch_payload_entries", 0),
                "prefetch_wall_ms": diag["wall_ms"],
                "prefetch_reload_ms": diag.get("prefetch_reload_ms", 0.0),
                "prefetch_reload": diag.get("prefetch_reload", ""),
                "prefetch_source": diag["source"],
            }
        return diag

    def join_prefetch(self, request_id: str = "", timeout_s: float = 1.5) -> bool:
        """Bounded wait for an in-flight prefetch to complete.

        RUN-2 demand-time join: the demand-time prefill hook calls this
        right before ``lookup_many`` so the memory manifest/payloads are
        installed before the demand lookup (converting a cold ~700ms file
        path into a memory hit).  Returns True when no prefetch is in flight
        for *request_id* or the in-flight prefetch completed within the
        bound; False on timeout.  Never raises; never blocks longer than the
        bound.  A bounded ``""``-key fallback is consulted when the exact
        request-id has no in-flight prefetch (launches that carried no id
        register under ``""``).  The Event is set in ``prefetch_entries``'s
        ``finally`` on success OR failure.
        """
        _rid = str(request_id or "")
        _event: threading.Event | None = None
        with self._prefetch_lock:
            _event = self._prefetch_events.get(_rid)
            if _event is None and _rid:
                _event = self._prefetch_events.get("")
        if _event is None:
            return True
        try:
            _bound = max(0.0, float(timeout_s or 0.0))
        except (TypeError, ValueError):
            _bound = 1.5
        return _event.wait(timeout=_bound)

    # ── Lookup ──────────────────────────────────────────────────────────
    def _reload_volume(self) -> None:
        """Best-effort Modal volume reload so other containers' commits are
        visible.  Any failure is a miss (fail closed), never an error."""
        try:
            import sys as _sys_cn
            _comfyapp = _sys_cn.modules.get("comfyapp")
            if _comfyapp is None:
                return
            _vol = getattr(_comfyapp, "prompt_cache_vol", None)
            if _vol is not None and hasattr(_vol, "reload"):
                _vol.reload()
        except Exception:
            pass

    def lookup_many(
        self,
        base_ctx: Mapping[str, Any],
        entries: list[Mapping[str, Any]],
    ) -> tuple[dict[int, Any], list[dict[str, Any]], int, int]:
        """Look up every entry.  Returns ``(hits_by_index, miss_entries,
        hit_count, miss_count)``.  Hits are the deserialized conditioning
        values; every other outcome is a miss that falls back to the
        unchanged encode path."""
        hits: dict[int, Any] = {}
        misses: list[dict[str, Any]] = []
        diag: dict[str, Any] = {
            "lock_wait_ms": 0.0,
            "volume_reload_ms": 0.0,
            "manifest_read_ms": 0.0,
            "manifest_read_bytes": 0,
            "manifest_entries": 0,
            "key_build_digest_ms": 0.0,
            "entry_lookup_ms": 0.0,
            "header_bytes_read": 0,
            "data_bytes_read": 0,
            "lru_touch_ms": 0.0,
            "lru_touch_mode": "sync",
            "entries_requested": len(entries),
            "hit_count": 0,
            "miss_count": 0,
            "total_ms": 0.0,
            "residual_ms": 0.0,
            # Task 2: plan-time prefetch / in-memory cache fields (additive;
            # never part of the measured-children sum).
            "prefetch_requested": 0,
            "prefetch_wall_ms": 0.0,
            "prefetch_overlap_ms": 0.0,
            "prefetch_source": "none",
            "prefetch_reload": "",
            "prefetch_payload_entries": 0,
            "manifest_memory_hit": 0,
            "payload_memory_hit": 0,
            "payload_memory_source": "",
            "normal_lookup_fallback": 0,
        }
        _t0 = time.monotonic_ns()
        if not entries:
            diag["total_ms"] = 0.0
            self._set_lookup_diag(diag)
            return hits, misses, 0, 0
        try:
            _kb_start = time.monotonic_ns()
            base_components = build_exact_key_components(base_ctx)
            diag["key_build_digest_ms"] += round((time.monotonic_ns() - _kb_start) / 1_000_000, 3)
            if not _base_key_missing(base_components):
                # ── Task 2: snapshot the prefetch memory state BEFORE taking
                #    self._lock so _prefetch_lock is never nested inside it. ──
                _mem_state = self._mem_state_snapshot()
                _pf_diag = _mem_state.get("prefetch_diag") or {}
                diag["prefetch_requested"] = int(_pf_diag.get("prefetch_requested", 0))
                diag["prefetch_wall_ms"] = round(float(_pf_diag.get("prefetch_wall_ms", 0.0)), 3)
                diag["prefetch_source"] = str(_pf_diag.get("prefetch_source", "none"))
                diag["prefetch_reload"] = str(_pf_diag.get("prefetch_reload", "") or "")
                diag["prefetch_payload_entries"] = int(_pf_diag.get("prefetch_payload_entries", 0))
                _mem_discard_digests: set[str] = set()
                _lw_start = time.monotonic_ns()
                self._lock.acquire()
                diag["lock_wait_ms"] = round((time.monotonic_ns() - _lw_start) / 1_000_000, 3)
                try:
                    # Re-check invalidation under self._lock: a store may have
                    # enqueued between the snapshot and the lock acquisition.
                    if self._mem_invalidated:
                        _mem_state["invalidated"] = True
                    # NOTE: the lookup path performs ZERO Volume RPCs.  The
                    # only reload is the worker's throttled reload-before-
                    # batch inside _persist_batch(), which runs off the
                    # foreground path.  ``volume_reload_ms`` stays ~0.0 so
                    # downstream consumers keep reading the key.
                    manifest = None
                    if (
                        _mem_state.get("manifest") is not None
                        and not _mem_state.get("invalidated")
                        and not self._mem_manifest_stale(_mem_state)
                    ):
                        # Fresh prefetched manifest: serve from memory (the
                        # manifest is NOT re-read from disk).
                        manifest = _mem_state["manifest"]
                        diag["manifest_memory_hit"] = 1
                    if manifest is None:
                        _mr_start = time.monotonic_ns()
                        manifest = self._read_manifest(_diag=diag)
                        diag["manifest_read_ms"] = round((time.monotonic_ns() - _mr_start) / 1_000_000, 3)
                    diag["manifest_entries"] = len(manifest.get("entries", []))
                    manifest_entries = {
                        str(e.get("key_hash", "")): e
                        for e in manifest.get("entries", [])
                        if isinstance(e, Mapping) and e.get("key_hash")
                    }
                    touched_digests: set[str] = set()
                    for index, entry in enumerate(entries):
                        _kb_start = time.monotonic_ns()
                        ctx = _merge_entry_context(base_ctx, entry)
                        components = build_exact_key_components(ctx)
                        missing = _key_usable(components)
                        if missing:
                            diag["key_build_digest_ms"] += round((time.monotonic_ns() - _kb_start) / 1_000_000, 3)
                            misses.append(dict(entry))
                            continue
                        digest = exact_key_digest(components)
                        diag["key_build_digest_ms"] += round((time.monotonic_ns() - _kb_start) / 1_000_000, 3)
                        _el_start = time.monotonic_ns()
                        value, _discard_mem = self._lookup_entry_maybe_mem(
                            components, digest, manifest_entries, _mem_state,
                            _diag=diag, _lookup_start_mono=_t0,
                        )
                        if _discard_mem:
                            _mem_discard_digests.add(digest)
                        diag["entry_lookup_ms"] += round((time.monotonic_ns() - _el_start) / 1_000_000, 3)
                        if value is None:
                            misses.append(dict(entry))
                        else:
                            hits[index] = value
                            manifest_entries[digest] = manifest_entries.get(digest) or {
                                "key_hash": digest,
                                "byte_length": 0,
                                "last_access_seq": 0,
                            }
                            touched_digests.add(digest)
                    if touched_digests:
                        _lt_start = time.monotonic_ns()
                        self._persist_lru_touch(manifest_entries, touched_digests)
                        diag["lru_touch_ms"] = round((time.monotonic_ns() - _lt_start) / 1_000_000, 3)
                        # In async mode ``lru_touch_ms`` measures ONLY the
                        # bounded enqueue cost; the coalesced manifest rewrite
                        # happens on the background LRU worker.
                        diag["lru_touch_mode"] = (
                            "async" if _conditioning_async_lru_enabled() else "sync"
                        )
                finally:
                    self._lock.release()
                # ── Post-lock: discard memory entries whose in-memory bytes
                #    failed validation (never nest _prefetch_lock inside
                #    self._lock) ──
                if _mem_discard_digests:
                    self._discard_mem_payloads(_mem_discard_digests)
            else:
                missing = _base_key_missing(base_components)
                _log_decision(
                    "miss_insufficient_identity",
                    reason=missing or "unknown",
                    request_id=_s(base_ctx.get("request_id")),
                )
                misses = [dict(e) for e in entries]
        except Exception as exc:
            _log_decision("miss_error", reason=f"{type(exc).__name__}:{exc}"[:120])
            misses = [dict(e) for e in entries]
        diag["hit_count"] = len(hits)
        diag["miss_count"] = len(misses)
        diag["total_ms"] = round((time.monotonic_ns() - _t0) / 1_000_000, 3)
        _children = (
            (diag["lock_wait_ms"] or 0.0)
            + diag["volume_reload_ms"]
            + diag["manifest_read_ms"]
            + diag["key_build_digest_ms"]
            + diag["entry_lookup_ms"]
            + diag["lru_touch_ms"]
        )
        diag["measured_children_ms"] = round(_children, 3)
        diag["residual_ms"] = round(diag["total_ms"] - _children, 3)
        if _OPT_DIAG and hits:
            _hit_read_bytes = diag["data_bytes_read"] + diag["header_bytes_read"]
            diag["hit_read_bytes"] = _hit_read_bytes
            _total_s = diag["total_ms"] / 1000.0
            diag["hit_read_mbps"] = (
                round(_hit_read_bytes / 1e6 / _total_s, 3) if _total_s > 0 else None
            )
            diag["cold_vs_warm_hint"] = "unknown"
            _opt_store_last_lookup_diag(diag, base_ctx.get("request_id"))
        self._set_lookup_diag(diag)
        return hits, misses, len(hits), len(misses)

    def _validate_entry_bytes(
        self,
        header_bytes: bytes,
        data_bytes: bytes,
        components: Mapping[str, Any],
        digest: str,
        manifest_byte_length: int,
        _diag: dict[str, Any] | None = None,
    ) -> Any:
        """Validate + deserialize one entry from bytes (on-disk or memory).

        The SAME validation sequence runs for the file path
        (``_lookup_entry``) and the in-memory prefetch path
        (``_lookup_entry_maybe_mem``) so the two are provably identical:
        header parse, format/schema/format-version, ``key_hash == digest``,
        full canonical key equality vs the live components, model identity
        equality, manifest ``byte_length``, then
        ``deserialize_conditioning`` with the payload + per-tensor
        checksums.  Returns the conditioning value or ``None`` (fail
        closed).  Never raises.
        """
        try:
            _hp_start = 0
            if _diag is not None and _OPT_DIAG:
                _hp_start = time.monotonic_ns()
            header = json.loads(header_bytes.decode("utf-8"))
            if _diag is not None and _OPT_DIAG:
                _diag["entry_header_parse_ms"] = _diag.get(
                    "entry_header_parse_ms", 0.0
                ) + round((time.monotonic_ns() - _hp_start) / 1_000_000, 3)
            if not isinstance(header, Mapping):
                return None
            _hv_start = 0
            if _diag is not None and _OPT_DIAG:
                _hv_start = time.monotonic_ns()
            if header.get("format") != FORMAT_NAME:
                return None
            if header.get("schema_version") != SCHEMA_VERSION:
                return None
            if header.get("format_version") != FORMAT_VERSION:
                return None
            if header.get("key_hash") != digest:
                return None
            # Full canonical key equality (never trust the hash alone).
            stored_components = header.get("key_components")
            if _canonical_json(stored_components) != _canonical_json(components):
                return None
            if header.get("model_identity") != _model_identity_block(components):
                return None
            if _diag is not None and _OPT_DIAG:
                _diag["entry_header_validate_ms"] = _diag.get(
                    "entry_header_validate_ms", 0.0
                ) + round((time.monotonic_ns() - _hv_start) / 1_000_000, 3)
            if int(manifest_byte_length) != len(data_bytes):
                return None
            _de_start = 0
            if _diag is not None and _OPT_DIAG:
                _de_start = time.monotonic_ns()
            value = deserialize_conditioning(
                header, data_bytes, _diag=_diag if _OPT_DIAG else None
            )
            if _diag is not None and _OPT_DIAG:
                _diag["entry_deserialize_ms"] = _diag.get(
                    "entry_deserialize_ms", 0.0
                ) + round((time.monotonic_ns() - _de_start) / 1_000_000, 3)
            return value
        except (json.JSONDecodeError, TypeError, ValueError, UnicodeDecodeError):
            return None

    def _lookup_entry_maybe_mem(
        self,
        components: Mapping[str, Any],
        digest: str,
        manifest_entries: Mapping[str, Any],
        mem_state: Mapping[str, Any] | None,
        *,
        _diag: dict[str, Any] | None = None,
        _lookup_start_mono: int = 0,
    ) -> tuple[Any, bool]:
        """Serve one entry from the prefetched memory cache when valid.

        Runs the IDENTICAL validation sequence on the in-memory bytes as
        the file path.  On success the memory copy is served (bytes-served
        accounting still reports the on-disk file sizes).  On ANY validation
        failure the memory copy is discarded (deferred by the caller until
        ``self._lock`` is released) and the normal file path runs (fail
        closed).

        RUN-6 (serve-by-components): when the digest-keyed memory entry
        misses, the prefetched payloads (keyed by their OWN stored digests)
        are scanned and each is validated against the LIVE components with
        the SAME rigorous rules — because the stored key_hash equals the
        demand digest IFF the stored canonical components equal the live
        ones, a pass here is a provably-exact match.  Any pass serves
        (``payload_memory_source=component_match``); none -> cold file path.

        Returns ``(value_or_None, discard_mem_digest)``.
        """
        header_path, data_path = self._entry_paths(digest)
        mem_payload = None
        mem_payloads_snapshot = None
        if (
            mem_state is not None
            and not mem_state.get("invalidated")
            and mem_state.get("manifest") is not None
        ):
            mem_payloads_snapshot = mem_state.get("payloads") or {}
            mem_payload = mem_payloads_snapshot.get(digest)
        if mem_payload is not None:
            if _diag is not None:
                _diag["manifest_memory_hit"] = 1
            _manifest_byte_length = -1
            _manifest_entry = manifest_entries.get(digest)
            if _manifest_entry is not None:
                _manifest_byte_length = int(_manifest_entry.get("byte_length", -1))
            value = self._validate_entry_bytes(
                mem_payload["header_bytes"],
                mem_payload["data_bytes"],
                components,
                digest,
                _manifest_byte_length,
                _diag=_diag,
            )
            if value is None:
                if _diag is not None:
                    _diag["normal_lookup_fallback"] = _diag.get("normal_lookup_fallback", 0) + 1
                return self._lookup_entry(components, digest, manifest_entries, _diag=_diag), True
            if _diag is not None:
                _diag["payload_memory_hit"] = _diag.get("payload_memory_hit", 0) + 1
                _diag["payload_memory_source"] = "key_hit"
                # Bytes SERVED still report the on-disk file sizes (telemetry
                # pin); the lengths of the in-memory copies are the fallback
                # when the files have since been removed.
                _h_size = _safe_getsize(header_path)
                _d_size = _safe_getsize(data_path)
                _diag["header_bytes_read"] = _diag.get("header_bytes_read", 0) + (
                    _h_size if _h_size is not None else len(mem_payload["header_bytes"])
                )
                _diag["data_bytes_read"] = _diag.get("data_bytes_read", 0) + (
                    _d_size if _d_size is not None else len(mem_payload["data_bytes"])
                )
                if _lookup_start_mono and mem_payload.get("read_mono_ns"):
                    _diag["prefetch_overlap_ms"] = max(
                        0, (_lookup_start_mono - int(mem_payload["read_mono_ns"])) / 1_000_000
                    )
            return value, False
        # ── RUN-6 component-match scan (digest-keyed miss) ────────────────
        if mem_payloads_snapshot:
            for _cand_digest, _cand in mem_payloads_snapshot.items():
                # Use the candidate's OWN header key_hash for the manifest
                # byte_length lookup (the dict key may differ from the header
                # key_hash when a payload was keyed by a drifted plan digest).
                _cand_key_hash = _cand_digest
                try:
                    _cand_hdr = json.loads(_cand["header_bytes"].decode("utf-8"))
                    _hdr_hash = str((_cand_hdr or {}).get("key_hash", "") or "")
                    if _hdr_hash:
                        _cand_key_hash = _hdr_hash
                except Exception:
                    pass
                _cand_byte_length = -1
                _cand_manifest = manifest_entries.get(_cand_key_hash)
                if _cand_manifest is not None:
                    _cand_byte_length = int(_cand_manifest.get("byte_length", -1))
                try:
                    _scan_value = self._validate_entry_bytes(
                        _cand["header_bytes"],
                        _cand["data_bytes"],
                        components,
                        digest,
                        _cand_byte_length,
                        _diag=None,
                    )
                except Exception:
                    _scan_value = None
                if _scan_value is None:
                    continue
                if _diag is not None:
                    _diag["manifest_memory_hit"] = 1
                    _diag["payload_memory_hit"] = _diag.get("payload_memory_hit", 0) + 1
                    _diag["payload_memory_source"] = "component_match"
                    _h_size = _safe_getsize(header_path)
                    _d_size = _safe_getsize(data_path)
                    _diag["header_bytes_read"] = _diag.get("header_bytes_read", 0) + (
                        _h_size if _h_size is not None else len(_cand["header_bytes"])
                    )
                    _diag["data_bytes_read"] = _diag.get("data_bytes_read", 0) + (
                        _d_size if _d_size is not None else len(_cand["data_bytes"])
                    )
                    if _lookup_start_mono and _cand.get("read_mono_ns"):
                        _diag["prefetch_overlap_ms"] = max(
                            0, (_lookup_start_mono - int(_cand["read_mono_ns"])) / 1_000_000
                        )
                # Best-effort re-key under the demand digest so later
                # lookups hit the digest-keyed path directly.
                try:
                    with self._prefetch_lock:
                        self._mem_payloads.setdefault(digest, _cand)
                except Exception:
                    pass
                return _scan_value, False
        return self._lookup_entry(components, digest, manifest_entries, _diag=_diag), False

    def _lookup_entry(
        self,
        components: Mapping[str, Any],
        digest: str,
        manifest_entries: Mapping[str, Any],
        _diag: dict[str, Any] | None = None,
    ) -> Any:
        """Validate and deserialize one entry from disk.  Every mismatch is a miss."""
        if digest not in manifest_entries:
            return None
        header_path, data_path = self._entry_paths(digest)
        try:
            if not os.path.isfile(header_path) or not os.path.isfile(data_path):
                return None
            _hdr_start = 0
            if _diag is not None and _OPT_DIAG:
                _hdr_start = time.monotonic_ns()
            with open(header_path, "r", encoding="utf-8") as f:
                header_text = f.read()
            header_bytes = header_text.encode("utf-8")
            if _diag is not None:
                _diag["header_bytes_read"] = _diag.get("header_bytes_read", 0) + len(
                    header_bytes
                )
            if _diag is not None and _OPT_DIAG:
                _diag["entry_header_open_read_ms"] = _diag.get(
                    "entry_header_open_read_ms", 0.0
                ) + round((time.monotonic_ns() - _hdr_start) / 1_000_000, 3)
            _d_start = 0
            if _diag is not None and _OPT_DIAG:
                _d_start = time.monotonic_ns()
            with open(data_path, "rb") as f:
                data_bytes = f.read()
            if _diag is not None:
                _diag["data_bytes_read"] = _diag.get("data_bytes_read", 0) + len(data_bytes)
            if _diag is not None and _OPT_DIAG:
                _diag["entry_data_open_read_ms"] = _diag.get(
                    "entry_data_open_read_ms", 0.0
                ) + round((time.monotonic_ns() - _d_start) / 1_000_000, 3)
                _diag["entry_data_bytes"] = len(data_bytes)
            return self._validate_entry_bytes(
                header_bytes,
                data_bytes,
                components,
                digest,
                int(manifest_entries[digest].get("byte_length", -1)),
                _diag=_diag,
            )
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            return None

    def _persist_lru_touch_sync(self, touched_digests: set[str]) -> None:
        """Rewrite the manifest with bumped access sequence numbers (A path).

        Runs on the foreground request thread under ``self._lock``.  LRU
        state is eviction/recency metadata only — a failure here must never
        change a hit/miss outcome, so it is swallowed.
        """
        try:
            with self._lock:
                manifest = self._read_manifest()
                next_seq = int(manifest.get("next_seq", 0) or 0)
                for existing in manifest.get("entries", []):
                    key_hash = str(existing.get("key_hash", ""))
                    if key_hash in touched_digests:
                        next_seq += 1
                        existing["last_access_seq"] = max(
                            int(existing.get("last_access_seq", 0) or 0),
                            next_seq,
                        )
                manifest["next_seq"] = next_seq
                self._write_manifest_atomic(manifest)
        except Exception:
            pass

    def _persist_lru_touch(
        self,
        manifest_entries: Mapping[str, Any],
        touched_digests: set[str],
    ) -> None:
        """Rewrite the manifest with bumped access sequence numbers.

        Experiment 5 (conditioning_hit): when the async_lru arm is active the
        touch is enqueued into the bounded background LRU queue instead of a
        synchronous re-read + 2-fsync atomic rewrite on the foreground request
        thread.  The sync path (A) stays byte-for-byte when the flag is off.
        LRU metadata is PURE eviction/recency state — hits never depend on it
        (``_lookup_entry`` never reads ``last_access_seq``), so queueing the
        touch is always correct.
        """
        if _conditioning_async_lru_enabled():
            self._enqueue_lru_touch(touched_digests)
            return
        self._persist_lru_touch_sync(touched_digests)

    def _enqueue_lru_touch(self, touched_digests) -> None:
        """Boundedly enqueue one touch for the background LRU worker.

        Caller may hold ``self._lock`` (RLock).  Duplicates are merged; the
        queue is bounded by ``_max_lru_queue`` (drops beyond it are counted,
        never raised).  If the worker cannot be started the digests drain
        back into a synchronous touch so recency is not lost.
        """
        _lru_experiment_log_once()
        _fallback: set[str] = set()
        with self._lock:
            if self._lru_closing:
                return
            added = 0
            for d in touched_digests:
                if d not in self._pending_lru:
                    if len(self._pending_lru) >= self._max_lru_queue:
                        self._lru_diag["lru_async_dropped"] += 1
                        continue
                    self._pending_lru.add(d)
                    added += 1
            if added:
                self._lru_diag["lru_async_enqueued"] += added
                self._lru_cond.notify()
            self._ensure_lru_worker()
            if self._lru_worker is None or not self._lru_worker.is_alive():
                # Worker could not be started in this environment — drain the
                # queue back into the synchronous touch (mirrors the store
                # path's ``need_sync`` fallback).
                _fallback = set(self._pending_lru)
                self._pending_lru.clear()
        if _fallback:
            _lru_sync_fallback_log_once()
            self._persist_lru_touch_sync(_fallback)

    def _ensure_lru_worker(self) -> None:
        """Lazily start (or respawn) the background LRU-touch thread.

        Caller must hold ``self._lock`` (via ``self._lru_cond``).  Double-start
        is impossible: the alive-check and the assignment both happen under the
        RLock.  On start failure the caller falls back to the synchronous
        touch for that call (counted + logged once).
        """
        if self._lru_closing:
            return
        if self._lru_worker is not None and self._lru_worker.is_alive():
            return
        try:
            worker = threading.Thread(
                target=self._lru_loop,
                name="comfymodal-exact-conditioning-lru",
                daemon=False,
            )
            worker.start()
            self._lru_worker = worker
        except Exception:
            self._lru_diag["lru_async_failed"] += 1

    def _lru_loop(self) -> None:
        """Background LRU-touch loop.  Never lets an exception escape."""
        try:
            while True:
                with self._lru_cond:
                    while not self._pending_lru and not self._lru_closing:
                        self._lru_cond.wait(timeout=0.5)
                    if not self._pending_lru and self._lru_closing:
                        break
                    batch = set(self._pending_lru)
                    self._pending_lru.clear()
                if batch:
                    self._persist_lru_batch(batch)
        except Exception as exc:
            with self._lru_cond:
                self._lru_diag["lru_async_failed"] += 1
            try:
                print(f"[cache.lru] async touch failed: {type(exc).__name__}: {exc}"[:160], flush=True)
            except Exception:
                pass

    def _persist_lru_batch(self, batch: set[str]) -> None:
        """One coalesced manifest rewrite bumping recency for *batch*.

        Same mutation as ``_persist_lru_touch_sync`` (read once, bump
        ``next_seq``/``last_access_seq``, atomic rewrite) but run off the
        foreground thread.  ``self._lock`` (RLock) makes the read-modify-
        write atomic.  Never raises; a failure only costs eviction-order
        recency, never cache correctness.
        """
        _start = time.monotonic_ns()
        try:
            with self._lock:
                manifest = self._read_manifest()
                next_seq = int(manifest.get("next_seq", 0) or 0)
                for existing in manifest.get("entries", []):
                    key_hash = str(existing.get("key_hash", ""))
                    if key_hash in batch:
                        next_seq += 1
                        existing["last_access_seq"] = max(
                            int(existing.get("last_access_seq", 0) or 0),
                            next_seq,
                        )
                manifest["next_seq"] = next_seq
                self._write_manifest_atomic(manifest)
        except Exception as exc:
            with self._lru_cond:
                self._lru_diag["lru_async_failed"] += 1
            try:
                print(f"[cache.lru] async touch failed: {type(exc).__name__}: {exc}"[:160], flush=True)
            except Exception:
                pass
            return
        with self._lru_cond:
            self._lru_diag["lru_async_batches"] += 1
            self._lru_diag["lru_async_batch_size"] = len(batch)
            self._lru_diag["lru_async_persist_ms"] += round(
                (time.monotonic_ns() - _start) / 1_000_000, 3
            )

    def _enforce_bounds(self, manifest: dict[str, Any], keep_digest: str) -> tuple[int, int]:
        """Enforce the entry and byte caps with deterministic LRU eviction.

        Evicts the entry with the smallest ``last_access_seq``; ties are
        broken by ``key_hash`` so eviction order is deterministic.  The
        just-written entry is never evicted when it is the only entry.
        Returns ``(evicted_count, evicted_bytes)``.
        """
        entries = manifest.get("entries", [])
        total_bytes = sum(int(e.get("byte_length", 0) or 0) for e in entries)
        _evicted = 0
        _evicted_bytes = 0
        while len(entries) > self._max_entries or total_bytes > self._max_bytes:
            oldest = min(
                entries,
                key=lambda e: (int(e.get("last_access_seq", 0) or 0), str(e.get("key_hash", ""))),
            )
            oldest_hash = str(oldest.get("key_hash", ""))
            if oldest_hash == keep_digest and len(entries) == 1:
                break
            header_path, data_path = self._entry_paths(oldest_hash)
            for path in (header_path, data_path):
                try:
                    if os.path.isfile(path):
                        os.remove(path)
                except OSError:
                    pass
            _evicted += 1
            _evicted_bytes += int(oldest.get("byte_length", 0) or 0)
            total_bytes -= int(oldest.get("byte_length", 0) or 0)
            entries.remove(oldest)
        manifest["entries"] = entries
        return _evicted, _evicted_bytes

    # ── Store (synchronous serialize → enqueue; file writes, manifest
    #    mutation, fsync and commit all belong to the background persistence
    #    worker — the miss_stored log therefore reports enqueued, with
    #    persisted/persist_failed read back from the shared worker counters) ──
    def store_entry(
        self,
        base_ctx: Mapping[str, Any],
        entry: Mapping[str, Any],
        value: Any,
    ) -> bool:
        """Serialize *value* and enqueue it for background persistence.

        Returns True when the immutable payload was accepted into the
        bounded persistence queue (or deduped against an already-queued
        entry).  Returns False when the cache is shutting down, the queue is
        full, or serialization/validation failed — every failure fails
        closed to a future miss.  Never performs file/manifest/fsync/commit
        work on this thread.  Never raises.
        """
        diag = self._store_entry_diag()
        _t0 = time.monotonic_ns()
        try:
            self._set_last_store_reason("")
            _kb_start = time.monotonic_ns()
            ctx = _merge_entry_context(base_ctx, entry)
            components = build_exact_key_components(ctx)
            missing = _key_usable(components)
            if missing:
                diag["key_build_digest_ms"] += round((time.monotonic_ns() - _kb_start) / 1_000_000, 3)
                self._set_last_store_reason(f"key:{missing}")
                diag["store_reason"] = self.last_store_reason
                return self._store_diag_close(diag, _t0, ok=False)
            digest = exact_key_digest(components)
            diag["key_build_digest_ms"] += round((time.monotonic_ns() - _kb_start) / 1_000_000, 3)
            payload = self._process_value(components, digest, value, _diag=diag)
            if payload is None:
                diag["store_reason"] = self.last_store_reason
                return self._store_diag_close(diag, _t0, ok=False)
            _ok = self._enqueue(payload, diag=diag)
            diag["store_reason"] = self.last_store_reason
            return self._store_diag_close(diag, _t0, ok=_ok)
        except Exception as exc:
            self._set_last_store_reason(f"store_exception:{type(exc).__name__}:{exc}"[:160])
            diag["store_reason"] = self.last_store_reason
            return self._store_diag_close(diag, _t0, ok=False)

    def _enqueue(
        self,
        payload: _PendingEntry,
        diag: dict[str, Any] | None = None,
    ) -> bool:
        """Append one immutable payload to the bounded persistence queue.

        Dedupes by ``key_hash`` (identical deterministic content), enforces
        the queue bound, and lazily starts the persistence worker.  Never
        raises.  Returns True when the entry is accepted (or already
        queued); False on queue-full or shutdown.
        """
        _enq_start = time.monotonic_ns()
        _lw_start = time.monotonic_ns()
        digest = str(payload.header.get("key_hash", ""))
        need_sync = False
        with self._queue_cond:
            if diag is not None:
                diag["lock_wait_ms"] = diag.get("lock_wait_ms", 0.0) + round(
                    (time.monotonic_ns() - _lw_start) / 1_000_000, 3
                )
            if self._closing:
                self._set_last_store_reason("shutting_down")
                if diag is not None:
                    diag["enqueue_ms"] = diag.get("enqueue_ms", 0.0) + round(
                        (time.monotonic_ns() - _enq_start) / 1_000_000, 3
                    )
                return False
            if digest and digest in self._pending_keys:
                self._accumulate_worker("queue_deduped", 1)
                self._set_last_store_reason("queue_deduped")
                if diag is not None:
                    diag["enqueue_ms"] = diag.get("enqueue_ms", 0.0) + round(
                        (time.monotonic_ns() - _enq_start) / 1_000_000, 3
                    )
                return True
            if len(self._pending) >= self._max_queue:
                self._accumulate_worker("queue_full_dropped", 1)
                self._set_last_store_reason("queue_full")
                if diag is not None:
                    diag["enqueue_ms"] = diag.get("enqueue_ms", 0.0) + round(
                        (time.monotonic_ns() - _enq_start) / 1_000_000, 3
                    )
                return False
            payload.enqueue_mono_ns = time.monotonic_ns()
            self._pending.append(payload)
            if digest:
                self._pending_keys.add(digest)
            # A self-store supersedes any prefetched bytes for this key (and
            # the manifest rewrite that follows invalidates the whole memory
            # manifest): fail closed so stale prefetched bytes are never
            # served.  Caller holds self._lock via self._queue_cond.
            self._invalidate_mem_locked()
            self._accumulate_worker("enqueued", 1)
            self._set_last_store_reason("")
            self._set_worker("queue_depth", len(self._pending))
            self._ensure_worker()
            if self._worker_broken and self._worker is None:
                # Fallback: worker could not be started in this environment —
                # remove the entry from the queue and persist synchronously.
                need_sync = True
                try:
                    self._pending.remove(payload)
                    self._pending_keys.discard(digest)
                except ValueError:
                    pass
                self._set_worker("queue_depth", len(self._pending))
            self._queue_cond.notify()
        if need_sync:
            self._accumulate_worker("fallback_sync_stores", 1)
            self._persist_batch([payload])
        if diag is not None:
            diag["enqueue_ms"] = diag.get("enqueue_ms", 0.0) + round(
                (time.monotonic_ns() - _enq_start) / 1_000_000, 3
            )
        return True

    def _ensure_worker(self) -> None:
        """Lazily start (or respawn after death) the persistence thread.

        Caller must hold ``self._queue_cond``.  Double-start is impossible:
        the alive-check and the assignment both happen under the queue
        condition's RLock.  If the thread cannot be started in this
        environment the cache degrades to synchronous single-entry persists.
        """
        if self._worker_broken or self._closing:
            return
        if self._worker is not None and self._worker.is_alive():
            return
        try:
            worker = threading.Thread(
                target=self._persistence_loop,
                name="comfymodal-exact-conditioning-persist",
                daemon=False,
            )
            worker.start()
            self._worker = worker
        except Exception as exc:
            self._worker_broken = True
            _log_decision(
                "persist_worker_start_failed",
                reason=f"{type(exc).__name__}:{exc}"[:120],
            )

    def _persistence_loop(self) -> None:
        """Background persistence loop.  Never lets an exception escape."""
        try:
            while True:
                with self._queue_cond:
                    while not self._pending and not self._closing:
                        self._queue_cond.wait(timeout=0.5)
                    if not self._pending and self._closing:
                        break
                    batch = [self._pending.popleft() for _ in range(len(self._pending))]
                    for payload in batch:
                        self._pending_keys.discard(
                            str(payload.header.get("key_hash", ""))
                        )
                    self._set_worker("queue_depth", len(self._pending))
                if batch:
                    self._persist_batch(batch)
            # Worker-exit path (closing): one final commit if a batch was
            # written but its coalesced commit is still pending.  Runs
            # outside the RLock.  flush() is the backstop when this fails.
            if self._dirty_since_commit:
                if self._commit():
                    self._dirty_since_commit = False
                else:
                    self._accumulate_worker("commit_failed", 1)
                    _log_decision(
                        "persist_commit_failed",
                        reason="worker_final_commit_failed",
                    )
        except Exception as exc:
            _log_decision(
                "persist_worker_error",
                reason=f"{type(exc).__name__}:{exc}"[:120],
            )
        finally:
            self._worker_exited = True
            with self._queue_cond:
                self._queue_cond.notify_all()

    def _persist_batch(self, batch: list[_PendingEntry]) -> None:
        """Persist one batch: reload-before-batch, atomic file + manifest
        writes, bounds, unindexed sweep (all under the RLock) then ONE
        coalesced commit outside the RLock.  Never raises."""
        if not batch:
            return
        n = len(batch)
        # Cumulative queue-wait accounting (now - enqueue_mono_ns per entry).
        _now_ns = time.monotonic_ns()
        self._accumulate_worker(
            "persistence_queue_wait_ms",
            round(sum((_now_ns - p.enqueue_mono_ns) for p in batch) / 1_000_000, 3),
        )
        _lw_start = time.monotonic_ns()
        try:
            with self._lock:
                self._accumulate_worker(
                    "lock_wait_ms",
                    round((time.monotonic_ns() - _lw_start) / 1_000_000, 3),
                )
                _rl_start = time.monotonic_ns()
                self._maybe_reload()
                self._accumulate_worker(
                    "reload_ms",
                    round((time.monotonic_ns() - _rl_start) / 1_000_000, 3),
                )
                _fw_start = time.monotonic_ns()
                manifest = self._read_manifest()
                next_seq = int(manifest.get("next_seq", 0) or 0)
                entries_by_hash: dict[str, Any] = {
                    str(e.get("key_hash", "")): e
                    for e in manifest.get("entries", [])
                    if isinstance(e, Mapping) and e.get("key_hash")
                }
                last_digest = ""
                for payload in batch:
                    digest = str(payload.header.get("key_hash", ""))
                    last_digest = digest
                    header_path, data_path = self._entry_paths(digest)
                    # Atomic data blob first, then the header, then the manifest.
                    _atomic_write(data_path, payload.data)
                    _header_json = json.dumps(
                        payload.header, sort_keys=True, separators=(",", ":")
                    )
                    _atomic_write_text(header_path, _header_json)
                    next_seq += 1
                    created_at = payload.header.get("created_at", time.time())
                    existing = entries_by_hash.get(digest)
                    if existing is not None:
                        # SAFE max() bump — a stale manifest must never
                        # regress an entry's LRU sequence.
                        existing["key_hash"] = digest
                        existing["byte_length"] = len(payload.data)
                        existing["last_access_seq"] = max(
                            int(existing.get("last_access_seq", 0) or 0),
                            next_seq,
                        )
                        existing["created_at"] = created_at
                    else:
                        entry = {
                            "key_hash": digest,
                            "byte_length": len(payload.data),
                            "last_access_seq": next_seq,
                            "created_at": created_at,
                        }
                        manifest["entries"].append(entry)
                        entries_by_hash[digest] = entry
                manifest["next_seq"] = next_seq
                self._accumulate_worker(
                    "file_write_ms",
                    round((time.monotonic_ns() - _fw_start) / 1_000_000, 3),
                )
                self._enforce_bounds(manifest, keep_digest=last_digest)
                _mw_start = time.monotonic_ns()
                self._write_manifest_atomic(manifest)
                self._accumulate_worker(
                    "manifest_ms",
                    round((time.monotonic_ns() - _mw_start) / 1_000_000, 3),
                )
                _removed = self._remove_unindexed_files(manifest)
                self._accumulate_worker("unindexed_files_removed", _removed)
                self._dirty_since_commit = True
                # A batch was written + the manifest rewritten: any
                # prefetched in-memory bytes are superseded (fail closed).
                # Caller holds self._lock here.
                self._invalidate_mem_locked()
            # ── LEAVE the RLock before the commit RPC ─────────────────────
            _cm_start = time.monotonic_ns()
            commit_ok = self._commit()
            self._accumulate_worker(
                "commit_ms",
                round((time.monotonic_ns() - _cm_start) / 1_000_000, 3),
            )
            if commit_ok:
                self._dirty_since_commit = False
            else:
                self._accumulate_worker("commit_failed", 1)
                _log_decision(
                    "persist_commit_failed",
                    reason="batch_commit_failed",
                    batch_size=n,
                )
            self._accumulate_worker("persisted", n)
            self._set_worker("batch_size", n)
            self._accumulate_worker("batch_count", 1)
        except Exception as exc:
            self._accumulate_worker("persist_failed", n)
            _log_decision(
                "persist_failed",
                reason=f"{type(exc).__name__}:{exc}"[:120],
                batch_size=n,
            )

    def flush(self, timeout: float) -> dict[str, Any]:
        """Bounded teardown flush.  Idempotent.

        Signals the worker to drain, joins it within *timeout* seconds, then
        drains any entries the worker never processed and performs ONE final
        explicit commit when the mount is still dirty (a worker batch was
        written without a successful coalesced commit).  Never holds the
        RLock across the commit hook.  Returns a diagnostics dict.
        """
        _f0 = time.monotonic_ns()
        status = "ok"
        drained_count = 0
        final_commit_ms = 0.0
        # ── Experiment 5 (conditioning_hit async_lru) teardown ─────────────
        # Drain the background LRU-touch queue synchronously (ONE coalesced
        # manifest rewrite) and stop the LRU worker, BEFORE the store join.
        # LRU recency metadata is eviction-only, so this is best-effort,
        # bounded, and idempotent — it never extends the store teardown
        # budget beyond a short join guard.
        with self._lru_cond:
            self._lru_closing = True
            lru_batch = set(self._pending_lru)
            self._pending_lru.clear()
            self._lru_cond.notify_all()
        if lru_batch:
            self._persist_lru_batch(lru_batch)
            with self._lru_cond:
                self._lru_diag["lru_async_flush_count"] += 1
        lru_worker = self._lru_worker
        if lru_worker is not None and lru_worker.is_alive():
            lru_worker.join(min(timeout, 2.0))
        with self._queue_cond:
            self._closing = True
            self._queue_cond.notify_all()
            worker = self._worker
        if worker is not None:
            worker.join(timeout)
            if worker.is_alive():
                status = "timeout"
                _log_decision(
                    "flush_timeout",
                    reason="worker_join_timeout_modal_shutdown_commit_backstop",
                )
                _flush_ms = round((time.monotonic_ns() - _f0) / 1_000_000, 3)
                self._record_flush(_flush_ms, status, 0, 0.0)
                return self._flush_diag(_flush_ms, status, 0, 0.0)
        # Worker exited (or never started): drain any queue remnant the
        # worker never processed (e.g. it crashed mid-request).  Payloads
        # are materialized bytes — safe to persist on this thread.
        with self._queue_cond:
            pending = list(self._pending)
            if pending:
                self._pending.clear()
                for payload in pending:
                    self._pending_keys.discard(
                        str(payload.header.get("key_hash", ""))
                    )
                self._set_worker("queue_depth", 0)
            self._queue_cond.notify_all()
        if pending:
            self._persist_batch(pending)
            drained_count = len(pending)
        if self._dirty_since_commit:
            _cm_start = time.monotonic_ns()
            commit_ok = self._commit()
            final_commit_ms = round((time.monotonic_ns() - _cm_start) / 1_000_000, 3)
            if commit_ok:
                self._dirty_since_commit = False
            else:
                self._accumulate_worker("commit_failed", 1)
                _log_decision(
                    "flush_final_commit_failed",
                    reason="final_commit_failed",
                )
        _flush_ms = round((time.monotonic_ns() - _f0) / 1_000_000, 3)
        self._record_flush(_flush_ms, status, drained_count, final_commit_ms)
        return self._flush_diag(_flush_ms, status, drained_count, final_commit_ms)

    def _record_flush(
        self, flush_ms: float, status: str, drained_count: int, final_commit_ms: float
    ) -> None:
        with self._diag_lock:
            self._worker_diag["flush_count"] = self._worker_diag.get("flush_count", 0) + 1
            self._worker_diag["last_flush_ms"] = flush_ms
            self._worker_diag["last_flush_status"] = status
            self._worker_diag["drained_count"] = drained_count
            self._worker_diag["final_commit_ms"] = final_commit_ms

    def _flush_diag(
        self, flush_ms: float, status: str, drained_count: int, final_commit_ms: float
    ) -> dict[str, Any]:
        return {
            "flush_ms": flush_ms,
            "flush_status": status,
            "flush_count": self._worker_diag.get("flush_count", 0),
            "drained_count": drained_count,
            "final_commit_ms": final_commit_ms,
            "closing": self._closing,
            "worker_exited": self._worker_exited,
        }

    # ── Shared thread-safe diagnostics ──────────────────────────────────
    def _store_entry_diag(self) -> dict[str, Any]:
        """Fresh PER-CALL store diagnostics dict — never the shared dict.

        ``store_entry`` accumulates into this private copy; ``_store_diag_close``
        merges it into the shared ``_store_diag`` under ``_diag_lock``.  This
        keeps concurrent foreground store calls (coordinator pool workers)
        from racing on the shared structure.
        """
        return {
            "store_calls": 0,
            "store_failed": 0,
            "key_build_digest_ms": 0.0,
            "serialization_ms": 0.0,
            "materialize_ms": 0.0,
            "checksum_ms": 0.0,
            "serialized_payload_bytes": 0,
            "enqueue_ms": 0.0,
            "lock_wait_ms": 0.0,
            "total_ms": 0.0,
            "measured_children_ms": 0.0,
            "residual_ms": 0.0,
            "store_reason": "",
        }

    def _set_lookup_diag(self, diag: dict[str, Any]) -> None:
        with self._diag_lock:
            self._lookup_diag = dict(diag)

    def _accumulate_worker(self, key: str, amount: Any) -> None:
        with self._diag_lock:
            self._worker_diag[key] = self._worker_diag.get(key, 0) + amount

    def _set_worker(self, key: str, value: Any) -> None:
        with self._diag_lock:
            self._worker_diag[key] = value

    def _set_last_store_reason(self, reason: str) -> None:
        with self._diag_lock:
            self._last_store_reason = reason

    def _store_diag_close(self, diag: dict[str, Any], _t0: int, *, ok: bool) -> bool:
        diag["store_calls"] = diag.get("store_calls", 0) + 1
        if not ok:
            diag["store_failed"] = diag.get("store_failed", 0) + 1
        diag["total_ms"] = diag.get("total_ms", 0.0) + round((time.monotonic_ns() - _t0) / 1_000_000, 3)
        _children = (
            (diag.get("key_build_digest_ms") or 0.0)
            + (diag.get("serialization_ms") or 0.0)
            + (diag.get("enqueue_ms") or 0.0)
            + (diag.get("lock_wait_ms") or 0.0)
        )
        diag["measured_children_ms"] = round(_children, 3)
        diag["residual_ms"] = round(diag.get("total_ms", 0.0) - _children, 3)
        # Merge the per-call private dict into the shared structure under
        # the lock so concurrent foreground store calls never race.
        with self._diag_lock:
            if self._store_diag is None:
                self._store_diag = self._store_entry_diag()
            shared = self._store_diag
            for key, value in diag.items():
                if key in shared and isinstance(value, (int, float)) and not isinstance(value, bool):
                    shared[key] = shared[key] + value
                else:
                    shared[key] = value
        return ok

    def latest_lookup_diagnostics(self) -> dict[str, Any]:
        # Snapshot the LRU counters under ``_lru_cond`` FIRST, then the lookup
        # diag under ``_diag_lock`` — never nest the other way around, because
        # the store path already acquires ``_lock`` -> ``_diag_lock``.
        with self._lru_cond:
            lru_diag = dict(self._lru_diag)
        with self._diag_lock:
            diag = self._lookup_diag
            result = dict(diag) if diag else {}
        # Experiment 5 (conditioning_hit async_lru): merge the cumulative
        # LRU-worker counters so callers can see async touch activity.
        result.update(lru_diag)
        return result

    def pop_store_diagnostics(self) -> dict[str, Any]:
        """Pop the foreground per-request store diag merged with a snapshot
        of the cumulative worker diag (worker keys win on collision), then
        reset the foreground diag.  Worker counters stay cumulative.
        Returns {} when there was no foreground store activity."""
        with self._diag_lock:
            store = self._store_diag
            self._store_diag = None
            worker = dict(self._worker_diag)
        if store is None:
            return {}
        merged = dict(store)
        merged.update(worker)
        return merged

    def _process_value(
        self,
        components: Mapping[str, Any],
        digest: str,
        value: Any,
        _diag: dict[str, Any] | None = None,
    ) -> _PendingEntry | None:
        """Synchronous serialize + stamp step.  Returns the immutable
        payload (components/header/data) or None (fail closed)."""
        _serialized = serialize_conditioning(value, _diag=_diag)
        if _diag is not None and _diag.get("serialize_ms"):
            _diag["serialization_ms"] = _diag.get("serialization_ms", 0.0) + _diag.pop(
                "serialize_ms", 0.0
            )
        if _serialized is None:
            self._set_last_store_reason(_LAST_SERIALIZE_ERROR or "serialization_failed")
            return None
        header, data = _serialized
        if len(data) > self._max_bytes:
            self._set_last_store_reason("entry_exceeds_byte_cap")
            return None
        header["key_hash"] = digest
        header["key_components"] = components
        header["model_identity"] = _model_identity_block(components)
        header["created_at"] = time.time()
        return _PendingEntry(
            components=dict(components),
            header=header,
            data=data,
            enqueue_mono_ns=0.0,  # stamped at actual enqueue time
        )

    @property
    def last_store_reason(self) -> str:
        with self._diag_lock:
            return self._last_store_reason


def _model_identity_block(components: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "clip_identity": _s(components.get("clip_identity")),
        "clip_type": _s(components.get("clip_type")),
        "loader_class": _s(components.get("loader_class")),
        "filenames": [str(f or "") for f in (components.get("filenames") or [])],
        "weight_dtype": _s(components.get("weight_dtype")),
        "model_generation": _s(components.get("model_generation")),
    }


# ── Singleton ───────────────────────────────────────────────────────────


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, str(default)).strip())
    except (TypeError, ValueError):
        return default


_SINGLETON: ExactConditioningCache | None = None
_SINGLETON_LOCK = threading.Lock()
_SINGLETON_RESOLVED = False


def _register_commit_hook_from_comfyapp(cache: ExactConditioningCache) -> None:
    """Best-effort registration of the Modal prompt-cache volume commit hook."""
    try:
        import sys as _sys_cm
        _comfyapp = _sys_cm.modules.get("comfyapp")
        if _comfyapp is None:
            return
        _vol = getattr(_comfyapp, "prompt_cache_vol", None)
        if _vol is not None and hasattr(_vol, "commit"):
            cache.set_commit_hook(_vol.commit)
    except Exception:
        pass


def get_exact_conditioning_cache() -> ExactConditioningCache | None:
    """Return the process-wide cache service, or None when disabled.

    When disabled every caller treats the cache as an unconditional miss
    and the existing prefill encode path is unchanged.
    """
    global _SINGLETON, _SINGLETON_RESOLVED
    with _SINGLETON_LOCK:
        if _SINGLETON_RESOLVED:
            return _SINGLETON
        _SINGLETON_RESOLVED = True
        if not (env_flag(ENV_ENABLED) or env_flag(ENV_ENABLED_LEGACY)):
            _log_once(ENV_ENABLED, enabled=0)
            _SINGLETON = None
            return None
        root = str(os.environ.get(ENV_ROOT, _DEFAULT_ROOT) or _DEFAULT_ROOT)
        max_entries = _env_int(ENV_MAX_ENTRIES, _DEFAULT_MAX_ENTRIES)
        max_bytes = _env_int(ENV_MAX_BYTES, _DEFAULT_MAX_BYTES)
        try:
            _SINGLETON = ExactConditioningCache(
                root_dir=root, max_entries=max_entries, max_bytes=max_bytes,
            )
        except Exception as exc:
            _log_decision("miss_error", reason=f"init:{type(exc).__name__}"[:120])
            _SINGLETON = None
            return None
        _register_commit_hook_from_comfyapp(_SINGLETON)
        _log_once(ENV_ENABLED, enabled=1, root=root, max_entries=max_entries, max_bytes=max_bytes)
        return _SINGLETON
