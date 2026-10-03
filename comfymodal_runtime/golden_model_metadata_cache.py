"""Persistent, fail-soft SafeTensors header blueprints for Golden CLIP loads.

The file contains only identities and one normalized tensor table.  It is
deliberately independent of Torch and of the model weights so the downloader
can publish it from its dedicated container.
"""

from __future__ import annotations

import hashlib
import json
import os
import posixpath
import struct
import tempfile
import time
import zlib
from typing import Any


# The blob must live inside the runtime-state Volume as the V2 runtime actually
# mounts it.  ModalRuntimeEntrypointV2 mounts that Volume at
# RUNTIME_STATE_PATH = "/mnt/comfymodal_runtime_state" and exports
# COMFYMODAL_V2_STATE_VOLUME_ROOT; the legacy ComfyAPI class mounts the *same*
# Volume at "/root/comfymodal_runtime_state".  Writing to the legacy path from
# a V2 container lands in an ordinary directory that no Volume backs, so the
# bytes are discarded with the container and the commit is a no-op on an
# untouched Volume.  Resolve the mount the runtime actually publishes.
_RUNTIME_STATE_ROOT = os.environ.get(
    "COMFYMODAL_V2_STATE_VOLUME_ROOT", "/mnt/comfymodal_runtime_state"
)
CACHE_PATH = posixpath.join(
    _RUNTIME_STATE_ROOT, "caching_data", "golden_model_metadata.bin"
)
SCHEMA_VERSION = 1
_MAGIC = b"CMCLIPMETA\x01"
_HEADER = struct.Struct("<HII32s")
_MAX_CACHE_BYTES = 64 * 1024 * 1024

_DTYPE_ITEMSIZE = {
    "F64": 8, "F32": 4, "F16": 2, "BF16": 2,
    "I64": 8, "I32": 4, "I16": 2, "I8": 1,
    "U8": 1, "U16": 2, "U32": 4, "U64": 8, "BOOL": 1,
    "F8_E4M3": 1, "F8_E5M2": 1,
}


def canonical_model_relative_path(path: str | os.PathLike[str], models_root: str | None = None) -> str | None:
    """Return the stable model-relative path, never a container inode/path."""
    raw = str(path).replace("\\", "/")
    if not raw:
        return None
    is_absolute = raw.startswith("/") or (len(raw) >= 3 and raw[1] == ":" and raw[2] == "/")
    if not is_absolute:
        relative = posixpath.normpath(raw)
        return None if relative in {"", ".", ".."} or relative.startswith("../") else relative
    roots = [models_root, os.environ.get("COMFYMODAL_MODELS_PATH"), "/root/models", "/root/comfy/ComfyUI/models"]
    for root in roots:
        if not root:
            continue
        root_norm = posixpath.normpath(str(root).replace("\\", "/"))
        prefix = root_norm.rstrip("/") + "/"
        if raw == root_norm or not raw.startswith(prefix):
            continue
        relative = posixpath.normpath(raw[len(prefix):])
        if relative not in {"", ".", ".."} and not relative.startswith("../"):
            return relative
    return None


def _header_bytes(path: str | os.PathLike[str]) -> tuple[int, bytes, int, int]:
    size = int(os.path.getsize(path))
    if size < 8:
        raise ValueError("truncated_header_length")
    with open(path, "rb") as handle:
        raw_length = handle.read(8)
        if len(raw_length) != 8:
            raise ValueError("truncated_header_length")
        header_length = struct.unpack("<Q", raw_length)[0]
        if header_length <= 0 or header_length > size - 8:
            raise ValueError(f"invalid_header_length:{header_length}")
        header = handle.read(header_length)
    if len(header) != header_length:
        raise ValueError("truncated_header")
    return size, header, 8 + int(header_length), size - 8 - int(header_length)


def build_entry(path: str | os.PathLike[str], model_relative_path: str | None = None) -> dict[str, Any]:
    """Parse one complete SafeTensors header into the compact cache blueprint."""
    path = str(path)
    size, raw_header, data_start, data_bytes = _header_bytes(path)
    header = json.loads(raw_header.decode("utf-8"))
    if not isinstance(header, dict):
        raise ValueError("header_not_object")
    tensors: list[list[Any]] = []
    ranges: list[tuple[int, int, str]] = []
    for name, info in header.items():
        if name == "__metadata__":
            continue
        if not isinstance(name, str) or not isinstance(info, dict):
            raise ValueError(f"invalid_tensor_metadata:{name}")
        dtype = str(info.get("dtype", ""))
        itemsize = _DTYPE_ITEMSIZE.get(dtype)
        shape = info.get("shape")
        offsets = info.get("data_offsets")
        if itemsize is None or not isinstance(shape, list) or not isinstance(offsets, list) or len(offsets) != 2:
            raise ValueError(f"invalid_tensor_metadata:{name}")
        if any(isinstance(value, bool) or not isinstance(value, int) for value in shape + offsets):
            raise ValueError(f"invalid_tensor_metadata:{name}")
        shape_values = [int(value) for value in shape]
        start, end = int(offsets[0]), int(offsets[1])
        if any(value < 0 for value in shape_values) or start < 0 or end <= start or end > data_bytes:
            raise ValueError(f"tensor_offset_out_of_range:{name}")
        expected = itemsize
        for value in shape_values:
            expected *= value
        if end - start != expected:
            raise ValueError(f"dtype_shape_size_mismatch:{name}")
        ranges.append((start, end, name))
        tensors.append([name, dtype, shape_values, start, end - start])
    if not tensors:
        raise ValueError("empty_header")
    ordered_ranges = sorted(ranges)
    if ordered_ranges[0][0] != 0 or ordered_ranges[-1][1] != data_bytes:
        raise ValueError("non_contiguous_tensor_ranges")
    for previous, current in zip(ordered_ranges, ordered_ranges[1:]):
        if previous[1] > current[0]:
            raise ValueError(f"overlapping_tensor_ranges:{previous[2]}:{current[2]}")
    relative = model_relative_path or canonical_model_relative_path(path)
    if not relative:
        raise ValueError("model_relative_path_unresolved")
    stat_result = os.stat(path)
    return {
        "path": relative,
        "size": int(stat_result.st_size),
        "mtime_ns": int(getattr(stat_result, "st_mtime_ns", 0)),
        "header_sha256": hashlib.sha256(raw_header).hexdigest(),
        "data_start": int(data_start),
        "data_bytes": int(data_bytes),
        "tensors": tensors,
    }


def _validate_entry(entry: Any) -> dict[str, Any]:
    if not isinstance(entry, dict):
        raise ValueError("entry_not_object")
    required = {"path", "size", "mtime_ns", "header_sha256", "data_start", "data_bytes", "tensors"}
    if set(entry) != required:
        raise ValueError("entry_schema")
    path = str(entry["path"])
    if not path or path.startswith("/") or path == "." or path.startswith("../"):
        raise ValueError("entry_path")
    if any(not isinstance(entry[key], int) or isinstance(entry[key], bool) for key in ("size", "mtime_ns", "data_start", "data_bytes")):
        raise ValueError("entry_integer")
    digest = entry["header_sha256"]
    if not isinstance(digest, str) or len(digest) != 64:
        raise ValueError("entry_digest")
    tensors = entry["tensors"]
    if not isinstance(tensors, list) or not tensors:
        raise ValueError("entry_tensors")
    normalized: list[list[Any]] = []
    ranges: list[tuple[int, int, str]] = []
    for item in tensors:
        if not isinstance(item, list) or len(item) != 5:
            raise ValueError("tensor_schema")
        name, dtype, shape, offset, length = item
        if not isinstance(name, str) or dtype not in _DTYPE_ITEMSIZE or not isinstance(shape, list):
            raise ValueError("tensor_schema")
        if any(isinstance(value, bool) or not isinstance(value, int) or value < 0 for value in shape):
            raise ValueError("tensor_shape")
        if any(isinstance(value, bool) or not isinstance(value, int) for value in (offset, length)) or offset < 0 or length <= 0:
            raise ValueError("tensor_range")
        expected = _DTYPE_ITEMSIZE[dtype]
        for value in shape:
            expected *= value
        if expected != length:
            raise ValueError("tensor_size")
        ranges.append((offset, offset + length, name))
        normalized.append([name, dtype, [int(value) for value in shape], int(offset), int(length)])
    ordered_ranges = sorted(ranges)
    if ordered_ranges[0][0] != 0 or ordered_ranges[-1][1] != entry["data_bytes"]:
        raise ValueError("tensor_coverage")
    for previous, current in zip(ordered_ranges, ordered_ranges[1:]):
        if previous[1] > current[0]:
            raise ValueError("tensor_overlap")
    return {**entry, "path": path, "tensors": normalized}


def _serialize(entries: dict[str, dict[str, Any]]) -> bytes:
    payload = json.dumps(
        {"schema_version": SCHEMA_VERSION, "entries": entries},
        sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")
    compressed = zlib.compress(payload, level=6)
    return _MAGIC + _HEADER.pack(SCHEMA_VERSION, len(compressed), len(payload), hashlib.sha256(compressed).digest()) + compressed


def deserialize(raw: bytes) -> dict[str, dict[str, Any]]:
    if len(raw) < len(_MAGIC) + _HEADER.size or not raw.startswith(_MAGIC):
        raise ValueError("cache_magic")
    version, compressed_len, payload_len, digest = _HEADER.unpack_from(raw, len(_MAGIC))
    if version != SCHEMA_VERSION:
        raise ValueError(f"cache_schema:{version}")
    start = len(_MAGIC) + _HEADER.size
    if compressed_len <= 0 or start + compressed_len != len(raw):
        raise ValueError("cache_truncated")
    compressed = raw[start:]
    if hashlib.sha256(compressed).digest() != digest:
        raise ValueError("cache_checksum")
    payload = zlib.decompress(compressed)
    if len(payload) != payload_len:
        raise ValueError("cache_payload_length")
    document = json.loads(payload.decode("utf-8"))
    if not isinstance(document, dict) or document.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("cache_payload_schema")
    entries = document.get("entries")
    if not isinstance(entries, dict):
        raise ValueError("cache_entries")
    return {str(path): _validate_entry(entry) for path, entry in entries.items()}


_state: dict[str, Any] | None = None


def hydrate(path: str = CACHE_PATH, *, force: bool = False) -> dict[str, Any]:
    """Load and validate the one cache blob; all failures become telemetry."""
    global _state
    if _state is not None and not force and _state.get("path") == path:
        return dict(_state)
    started = time.perf_counter_ns()
    info: dict[str, Any] = {
        "path": path, "loaded": False, "schema": "absent", "file_bytes": 0,
        "hydration_ms": 0.0, "entries": {}, "error": None,
    }
    try:
        file_bytes = os.path.getsize(path)
        info["file_bytes"] = int(file_bytes)
        if file_bytes > _MAX_CACHE_BYTES:
            raise ValueError("cache_too_large")
        with open(path, "rb") as handle:
            entries = deserialize(handle.read())
        info.update({"loaded": True, "schema": SCHEMA_VERSION, "entries": entries})
    except FileNotFoundError:
        pass
    except Exception as exc:
        info.update({"schema": "corrupt", "error": f"{type(exc).__name__}:{str(exc)[:160]}"})
    info["hydration_ms"] = (time.perf_counter_ns() - started) / 1e6
    # Only a successful load is memoized.  A miss must stay re-checkable: the
    # blob is written by a different container, so a probe that runs before the
    # runtime-config Volume is reloaded would otherwise pin _state to 'absent'
    # for the rest of this container's life and every later lookup would keep
    # reporting a miss even though the blob is now visible.  Re-probing costs
    # one stat() on a path that is normally a hit.
    if info["loaded"]:
        _state = info
    else:
        _state = None
    return dict(info)


def reset_for_tests() -> None:
    global _state
    _state = None


def lookup(path: str | os.PathLike[str], cache_path: str = CACHE_PATH) -> dict[str, Any]:
    """Return an exact identity match, or a visible fail-soft miss."""
    state = hydrate(cache_path)
    result: dict[str, Any] = {
        "entry": None, "entry_hit": False, "identity_match": False,
        "canonical_path": canonical_model_relative_path(path),
        "reason": state.get("error") or ("cache_not_loaded" if not state.get("loaded") else "unknown_model"),
        "hydration_ms": state.get("hydration_ms", 0.0),
    }
    relative = result["canonical_path"]
    if not relative or not state.get("loaded"):
        return result
    entry = state.get("entries", {}).get(relative)
    if entry is None:
        return result
    result["entry_hit"] = True
    try:
        # Cheap identity first.  size+mtime_ns already change on any
        # modification, and stat() is a local call, so the common case avoids
        # re-reading the SafeTensors header off the Volume - which cost as much
        # as the parse it was meant to replace (~39 ms versus ~31 ms).  The
        # header digest is still verified whenever the cheap identity does not
        # match, or when it is not recorded, so a rewritten file cannot be
        # served from a stale blueprint.
        stat_result = os.stat(path)
        size = int(stat_result.st_size)
        mtime_ns = int(getattr(stat_result, "st_mtime_ns", 0))
        if size != entry["size"] or mtime_ns != entry["mtime_ns"]:
            # Cheap identity disagrees.  Confirm with the header digest before
            # rejecting, so a touched-but-identical file (a re-commit, a
            # timestamp bump) is not mistaken for a different model.
            header_size, raw_header, _data_start, _data_bytes = _header_bytes(path)
            if hashlib.sha256(raw_header).hexdigest() != entry.get("header_sha256"):
                result["reason"] = "identity_mismatch"
                return result
        result["identity_match"] = True
        result["reason"] = "hit"
        result["entry"] = entry
    except Exception as exc:
        result["reason"] = f"identity_read:{type(exc).__name__}"
    return result


def publish_model_metadata(
    path: str | os.PathLike[str],
    model_relative_path: str,
    runtime_config_volume: Any = None,
    cache_path: str = CACHE_PATH,
) -> dict[str, Any]:
    """Publish one entry after the downloader has atomically installed weights."""
    try:
        entry = build_entry(path, model_relative_path)
    except Exception as exc:
        return {"status": "skipped", "reason": f"header:{type(exc).__name__}"}
    entries: dict[str, dict[str, Any]] = {}
    try:
        if os.path.isfile(cache_path):
            with open(cache_path, "rb") as handle:
                entries = deserialize(handle.read())
    except Exception:
        # A new valid entry may replace a corrupt cache; inference remains
        # fail-soft if this writer itself cannot publish.
        entries = {}
    existing = entries.get(entry["path"])
    if existing is not None:
        if existing == entry:
            try:
                result = {
                    "status": "noop",
                    "entry": entry["path"],
                    "file_bytes": os.path.getsize(cache_path),
                }
                reset_for_tests()
                return result
            except Exception as exc:
                return {"status": "error", "reason": f"stat:{type(exc).__name__}"}
    entries[entry["path"]] = entry
    parent = os.path.dirname(cache_path)
    os.makedirs(parent, exist_ok=True)
    temp_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(mode="wb", dir=parent, prefix=".golden_model_metadata.", suffix=".part", delete=False) as handle:
            temp_name = handle.name
            handle.write(_serialize(entries))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, cache_path)
        temp_name = None
        if runtime_config_volume is not None:
            runtime_config_volume.commit()
        reset_for_tests()
        return {"status": "ok", "entry": entry["path"], "file_bytes": os.path.getsize(cache_path)}
    except Exception as exc:
        if temp_name:
            try:
                os.unlink(temp_name)
            except OSError:
                pass
        return {"status": "error", "reason": f"publish:{type(exc).__name__}"}
