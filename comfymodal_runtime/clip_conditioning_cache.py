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
from typing import Any, Mapping

from .env import env_flag

# ── Env surface (opt-in; all defaults preserve current behavior) ────────
ENV_ENABLED = "COMFYMODAL_V2_CLIP_CONDITIONING_CACHE"
ENV_ENABLED_LEGACY = "COMFYMODAL_EXACT_CLIP_CONDITIONING_CACHE"
ENV_ROOT = "COMFYMODAL_EXACT_CLIP_CONDITIONING_CACHE_ROOT"
ENV_MAX_ENTRIES = "COMFYMODAL_EXACT_CLIP_CONDITIONING_CACHE_MAX_ENTRIES"
ENV_MAX_BYTES = "COMFYMODAL_EXACT_CLIP_CONDITIONING_CACHE_MAX_BYTES"

SCHEMA_VERSION = 1
FORMAT_VERSION = 1
FORMAT_NAME = "comfymodal_exact_clip_conditioning"

_DEFAULT_ROOT = "/root/prompt_cache_vol/exact_conditioning"
_DEFAULT_MAX_ENTRIES = 64
_DEFAULT_MAX_BYTES = 512 * 1024 * 1024

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

_LOG_EMITTED = False
_LOG_LOCK = threading.Lock()
_LAST_SERIALIZE_ERROR = ""


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
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
        allow_nan=False,
    )


def _canonical_value(value: Any) -> Any:
    return json.loads(_canonical_json(value))


def build_exact_key_components(ctx: Mapping[str, Any]) -> dict[str, Any]:
    """Canonical, deterministic key components for one CLIP encode.

    Every conditioning-affecting input available at the prefill boundary is
    included.  ``entry_layer``/``entry_skip`` are always present as empty
    fields because the native ``CLIPTextEncode`` node has no layer/skip
    inputs at this boundary — the fields exist in the schema so a future
    node with such inputs cannot produce a colliding key.
    """
    filenames = [str(f) for f in (ctx.get("filenames") or []) if str(f or "").strip()]
    return {
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


def exact_key_digest(components: Mapping[str, Any]) -> str:
    blob = _canonical_json(components)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


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


def _bytes_to_tensor(raw: bytes, dtype_str: str, shape: list[int]) -> Any:
    import numpy as _np
    import torch as _th

    dtype = _torch_dtype_for(dtype_str)
    if dtype == _th.bfloat16:
        arr = _np.frombuffer(raw, dtype=_np.int16).reshape(list(shape))
        return _th.from_numpy(arr.copy()).contiguous().view(_th.bfloat16)
    np_dtype = _numpy_dtype_for(dtype)
    arr = _np.frombuffer(raw, dtype=np_dtype).reshape(list(shape))
    return _th.from_numpy(arr.copy()).contiguous()


def _serialize_tensor_descriptor(tensor: Any, data_buf: bytearray, offset: int) -> tuple[int, dict[str, Any]]:
    raw, dtype_str, shape = _tensor_to_bytes(tensor)
    length = len(raw)
    data_buf.extend(raw)
    return length, {
        "dtype": dtype_str,
        "shape": shape,
        "offset": offset,
        "byte_length": length,
        "checksum": hashlib.sha256(raw).hexdigest(),
    }


def serialize_conditioning(value: Any) -> tuple[dict[str, Any], bytes] | None:
    """Serialize one CLIPTextEncode output into ``(header, data_bytes)``.

    The native conditioning value is ``[[tensor, {"pooled": pooled}], ...]``.
    Returns ``None`` (fail closed — do not store) for anything else.
    """
    import torch as _th

    global _LAST_SERIALIZE_ERROR
    _LAST_SERIALIZE_ERROR = ""
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
            _, cond_desc = _serialize_tensor_descriptor(cond, data_buf, len(data_buf))
            meta_out: list[dict[str, Any]] = []
            if not isinstance(meta, dict):
                return None
            for mk, mv in meta.items():
                if not isinstance(mk, str):
                    return None
                if isinstance(mv, _th.Tensor):
                    _, mv_desc = _serialize_tensor_descriptor(mv, data_buf, len(data_buf))
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
        header = {
            "format": FORMAT_NAME,
            "schema_version": SCHEMA_VERSION,
            "format_version": FORMAT_VERSION,
            "result_container": result_container,
            "byte_length": len(data),
            "payload_checksum": hashlib.sha256(data).hexdigest(),
            "conditioning": {"entries": entries_out},
        }
        return header, data
    except Exception as exc:
        _LAST_SERIALIZE_ERROR = f"{type(exc).__name__}:{exc}"[:160]
        return None


def _deserialize_tensor_descriptor(desc: Mapping[str, Any], data: bytes) -> Any:
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
    if checksum and hashlib.sha256(raw).hexdigest() != checksum:
        return None
    try:
        tensor = _bytes_to_tensor(raw, dtype, shape)
    except Exception:
        return None
    if str(tensor.dtype) != dtype:
        return None
    if list(tensor.shape) != shape:
        return None
    return tensor


def deserialize_conditioning(header: Mapping[str, Any], data: bytes) -> Any:
    """Rebuild a conditioning value from the header + data blob, or None."""
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
        if payload_checksum and hashlib.sha256(data).hexdigest() != payload_checksum:
            return None
        cond = header.get("conditioning") or {}
        entries = cond.get("entries") or []
        if not isinstance(entries, list) or not entries:
            return None
        result = []
        for e in entries:
            if not isinstance(e, Mapping):
                return None
            cond_tensor = _deserialize_tensor_descriptor(e.get("cond"), data)
            if cond_tensor is None:
                return None
            meta_dict: dict[str, Any] = {}
            for mv in (e.get("meta") or []):
                if not isinstance(mv, Mapping):
                    return None
                key = str(mv.get("key", ""))
                if mv.get("kind") == "tensor":
                    mt = _deserialize_tensor_descriptor(mv, data)
                    if mt is None:
                        return None
                    meta_dict[key] = mt
                elif mv.get("kind") == "raw":
                    meta_dict[key] = mv.get("value")
                else:
                    return None
            result.append([cond_tensor, meta_dict])
        if header.get("result_container") == "tuple":
            return (result,)
        if header.get("result_container") != "list":
            return None
        return result
    except Exception:
        return None


# ── Storage (atomic, bounded, deterministic LRU) ────────────────────────


def _atomic_write(path: str, data: bytes) -> None:
    tmp = f"{path}.{uuid.uuid4().hex}.tmp"
    try:
        with open(tmp, "wb") as f:
            f.write(data)
            f.flush()
            try:
                os.fsync(f.fileno())
            except OSError:
                pass
        os.replace(tmp, path)
        try:
            directory_fd = os.open(os.path.dirname(path) or ".", os.O_RDONLY)
            try:
                os.fsync(directory_fd)
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


def _atomic_write_text(path: str, text: str) -> None:
    _atomic_write(path, text.encode("utf-8"))


class ExactConditioningCache:
    """File-backed bounded LRU for exact CLIP conditioning entries."""

    def __init__(self, root_dir: str, max_entries: int, max_bytes: int) -> None:
        self._root = root_dir
        self._max_entries = max(1, int(max_entries))
        self._max_bytes = max(1, int(max_bytes))
        self._entries_dir = os.path.join(self._root, "entries")
        self._manifest_path = os.path.join(self._root, "manifest.json")
        self._lock = threading.RLock()
        self._commit_hook: Any = None
        self._last_store_reason = ""
        os.makedirs(self._entries_dir, exist_ok=True)

    # ── Commit hook (registered by the Modal prompt-cache volume owner) ──
    def set_commit_hook(self, hook: Any) -> None:
        with self._lock:
            self._commit_hook = hook

    def _commit(self) -> None:
        hook = self._commit_hook
        if hook is None:
            return
        try:
            hook()
        except Exception:
            pass

    # ── Manifest ────────────────────────────────────────────────────────
    def _read_manifest(self) -> dict[str, Any]:
        try:
            with open(self._manifest_path, "r", encoding="utf-8") as f:
                data = json.load(f)
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

    def _write_manifest_atomic(self, manifest: dict[str, Any]) -> None:
        manifest["schema_version"] = SCHEMA_VERSION
        manifest["format_version"] = FORMAT_VERSION
        _atomic_write_text(
            self._manifest_path,
            json.dumps(manifest, sort_keys=True, separators=(",", ":")),
        )

    def _entry_paths(self, key_hash: str) -> tuple[str, str]:
        return (
            os.path.join(self._entries_dir, f"{key_hash}.header.json"),
            os.path.join(self._entries_dir, f"{key_hash}.data.bin"),
        )

    def _remove_unindexed_files(self, manifest: Mapping[str, Any]) -> None:
        indexed = {
            str(entry.get("key_hash", ""))
            for entry in manifest.get("entries", [])
            if isinstance(entry, Mapping) and entry.get("key_hash")
        }
        try:
            names = os.listdir(self._entries_dir)
        except OSError:
            return
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
            except OSError:
                pass

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
        if not entries:
            return hits, misses, 0, 0
        try:
            base_components = build_exact_key_components(base_ctx)
            if not _base_key_missing(base_components):
                with self._lock:
                    self._reload_volume()
                    manifest = self._read_manifest()
                    manifest_entries = {
                        str(e.get("key_hash", "")): e
                        for e in manifest.get("entries", [])
                        if isinstance(e, Mapping) and e.get("key_hash")
                    }
                    touched_digests: set[str] = set()
                    for index, entry in enumerate(entries):
                        ctx = _merge_entry_context(base_ctx, entry)
                        components = build_exact_key_components(ctx)
                        missing = _key_usable(components)
                        if missing:
                            misses.append(dict(entry))
                            continue
                        digest = exact_key_digest(components)
                        value = self._lookup_entry(components, digest, manifest_entries)
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
                        self._persist_lru_touch(manifest_entries, touched_digests)
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
        return hits, misses, len(hits), len(misses)

    def _lookup_entry(
        self,
        components: Mapping[str, Any],
        digest: str,
        manifest_entries: Mapping[str, Any],
    ) -> Any:
        """Validate and deserialize one entry.  Every mismatch is a miss."""
        if digest not in manifest_entries:
            return None
        header_path, data_path = self._entry_paths(digest)
        try:
            if not os.path.isfile(header_path) or not os.path.isfile(data_path):
                return None
            with open(header_path, "r", encoding="utf-8") as f:
                header = json.load(f)
            if not isinstance(header, Mapping):
                return None
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
            with open(data_path, "rb") as f:
                data = f.read()
            if int(manifest_entries[digest].get("byte_length", -1)) != len(data):
                return None
            value = deserialize_conditioning(header, data)
            if value is None:
                return None
            return value
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            return None

    def _persist_lru_touch(
        self,
        manifest_entries: Mapping[str, Any],
        touched_digests: set[str],
    ) -> None:
        """Rewrite the manifest with bumped access sequence numbers."""
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

    def _enforce_bounds(self, manifest: dict[str, Any], keep_digest: str) -> None:
        """Enforce the entry and byte caps with deterministic LRU eviction.

        Evicts the entry with the smallest ``last_access_seq``; ties are
        broken by ``key_hash`` so eviction order is deterministic.  The
        just-written entry is never evicted when it is the only entry.
        """
        entries = manifest.get("entries", [])
        total_bytes = sum(int(e.get("byte_length", 0) or 0) for e in entries)
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
            total_bytes -= int(oldest.get("byte_length", 0) or 0)
            entries.remove(oldest)
        manifest["entries"] = entries

    # ── Store (synchronous so the miss_stored log follows the atomic store) ─
    def store_entry(
        self,
        base_ctx: Mapping[str, Any],
        entry: Mapping[str, Any],
        value: Any,
    ) -> bool:
        """Atomically store *value* after the unchanged encode completes."""
        try:
            self._last_store_reason = ""
            ctx = _merge_entry_context(base_ctx, entry)
            components = build_exact_key_components(ctx)
            missing = _key_usable(components)
            if missing:
                self._last_store_reason = f"key:{missing}"
                return False
            digest = exact_key_digest(components)
            return self._process_value(components, digest, value)
        except Exception:
            self._last_store_reason = "store_exception"
            return False

    def _process_value(
        self,
        components: Mapping[str, Any],
        digest: str,
        value: Any,
    ) -> bool:
        header, data = serialize_conditioning(value)
        if header is None:
            self._last_store_reason = _LAST_SERIALIZE_ERROR or "serialization_failed"
            return False
        if len(data) > self._max_bytes:
            self._last_store_reason = "entry_exceeds_byte_cap"
            return False
        header["key_hash"] = digest
        header["key_components"] = components
        header["model_identity"] = _model_identity_block(components)
        header["created_at"] = time.time()
        return self._write_entry(components, header, data)

    @property
    def last_store_reason(self) -> str:
        return self._last_store_reason

    def _write_entry(
        self,
        components: Mapping[str, Any],
        header: Mapping[str, Any],
        data: bytes,
    ) -> bool:
        digest = str(header.get("key_hash", ""))
        if not digest:
            return False
        header_path, data_path = self._entry_paths(digest)
        with self._lock:
            # Atomic data blob first, then the header, then the manifest.
            _atomic_write(data_path, data)
            _atomic_write_text(
                header_path,
                json.dumps(header, sort_keys=True, separators=(",", ":")),
            )
            manifest = self._read_manifest()
            next_seq = int(manifest.get("next_seq", 0) or 0) + 1
            existing = [e for e in manifest["entries"] if e.get("key_hash") == digest]
            if existing:
                entry = existing[0]
                entry.update({
                    "key_hash": digest,
                    "byte_length": len(data),
                    "last_access_seq": next_seq,
                    "created_at": time.time(),
                })
            else:
                manifest["entries"].append({
                    "key_hash": digest,
                    "byte_length": len(data),
                    "last_access_seq": next_seq,
                    "created_at": time.time(),
                })
            manifest["next_seq"] = next_seq
            self._enforce_bounds(manifest, keep_digest=digest)
            self._write_manifest_atomic(manifest)
            self._remove_unindexed_files(manifest)
            self._commit()
        return True


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
