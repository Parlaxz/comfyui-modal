"""Single-file restore cache for parsed safetensors metadata.

``golden_model_transport._parse_layout`` re-reads and re-parses a checkpoint's
safetensors header on every request. The production-008 exhaustive profile
measured 351.4 ms of self time over three calls (CLIP 194.6 ms, UNET 97 ms,
VAE 60 ms), almost all of it ``json.loads`` plus range/dtype validation. The
parsed result depends only on the header, which depends only on the file.

This module caches that parse in ONE file so restore can hydrate it in a few
milliseconds and a request can hit the cache with zero Volume data reads.

Design notes
------------
Identity
    A cache hit must be provably about the bytes on disk. The key is the same
    :func:`golden_model_transport._file_identity` tuple the transport already
    trusts -- ``(st_dev, st_ino, st_size, st_mtime_ns)``. Replacing a file
    changes the inode; rewriting it changes size and/or nanosecond mtime. This is
    metadata only: a hit performs ``os.stat`` and never reads the payload, which
    is what keeps cache hits free of Volume data reads.

    Verifying the header hash instead would require reading the header on every
    request -- the very I/O this cache exists to avoid -- and still would not
    cover the payload. The chosen bound is therefore explicit: identical device,
    inode, size and nanosecond mtime. Each entry also records the header sha256
    it was built from, so the identity of a cached entry is auditable.

One normalized representation
    A layout carries both the raw ``header`` dict and a derived ``tensor_map``.
    Only the normalized tensor list is stored -- ``(key, dtype, shape, offset,
    length)`` -- and the header dict is rebuilt from it on demand, so the same
    fact is not stored twice. Nothing reads ``SafetensorsLayout.header`` on the
    load path today; it is rebuilt to keep the dataclass contract intact.

Failure policy
    A missing, stale, corrupt or foreign cache can only cost time, never
    correctness: every load path falls back to the original parser.
"""

from __future__ import annotations

import os
import pickle
import struct
import tempfile
import time
from typing import Any, Optional

CACHE_SCHEMA_VERSION = 3
CACHE_BASENAME = "golden_model_metadata.bin"
CACHE_DIRNAME = "caching_data"

# Payloads are few and small (a few hundred KB), so the default runtime-state
# location is used rather than adding a Volume mount. Overridable for tests and
# for any deployment that wants the cache beside the models.
DEFAULT_CACHE_ROOT = "/root/comfymodal_runtime_state"
ENV_CACHE_ROOT = "COMFYMODAL_GOLDEN_METADATA_CACHE_ROOT"

_TensorRow = tuple  # (key, dtype, shape, offset, length)


def cache_root() -> str:
    return os.environ.get(ENV_CACHE_ROOT) or DEFAULT_CACHE_ROOT


def cache_dir() -> str:
    return os.path.join(cache_root(), CACHE_DIRNAME)


def cache_path() -> str:
    return os.path.join(cache_dir(), CACHE_BASENAME)


# ── normalized (de)serialization ──────────────────────────────────────────


def _header_bytes(path: str) -> tuple[bytes, int]:
    """Read the raw safetensors header. Only used on a cache miss."""
    size = os.path.getsize(path)
    with open(path, "rb") as handle:
        raw_length = handle.read(8)
        if len(raw_length) != 8:
            raise ValueError("truncated_safetensors_header_length")
        header_length = struct.unpack("<Q", raw_length)[0]
        if header_length <= 0 or header_length > size - 8:
            raise ValueError(f"invalid_safetensors_header_length:{header_length}")
        raw_header = handle.read(header_length)
    return raw_header, size


def normalize_layout(layout: Any) -> dict[str, Any]:
    """Collapse a SafetensorsLayout into the one representation we persist."""
    rows: list[_TensorRow] = []
    for entry in layout.tensor_map:
        rows.append(
            (
                str(entry["key"]),
                str(entry["dtype"]),
                tuple(int(v) for v in entry["shape"]),
                int(entry["offset"]),
                int(entry["length"]),
            )
        )
    meta = layout.header.get("__metadata__") if isinstance(layout.header, dict) else None
    return {
        "path": str(layout.path),
        "identity": tuple(int(v) for v in layout.identity),
        "data_start": int(layout.data_start),
        "data_bytes": int(layout.data_bytes),
        "meta": meta if isinstance(meta, dict) else None,
        "rows": tuple(rows),
    }


def build_layout(record: dict[str, Any], path: str, identity: tuple[int, ...]) -> Any:
    """Rebuild the transport's SafetensorsLayout from a normalized record."""
    from .golden_model_transport import SafetensorsLayout

    rows = record["rows"]
    tensor_map = tuple(
        {"key": key, "dtype": dtype, "shape": list(shape), "offset": offset, "length": length}
        for key, dtype, shape, offset, length in rows
    )
    header: dict[str, Any] = {}
    for key, dtype, shape, offset, length in rows:
        header[key] = {"dtype": dtype, "shape": list(shape), "data_offsets": [offset, offset + length]}
    if record.get("meta") is not None:
        header["__metadata__"] = record["meta"]
    raw_identity = tuple(int(v) for v in record["identity"])[:4]
    identity4 = (
        raw_identity[0] if len(raw_identity) > 0 else 0,
        raw_identity[1] if len(raw_identity) > 1 else 0,
        raw_identity[2] if len(raw_identity) > 2 else 0,
        raw_identity[3] if len(raw_identity) > 3 else 0,
    )
    return SafetensorsLayout(
        path=str(record["path"]),
        identity=identity4,
        header=header,
        data_start=int(record["data_start"]),
        data_bytes=int(record["data_bytes"]),
        tensor_map=tensor_map,
    )


# ── the cache ────────────────────────────────────────────────────────────


class MetadataCache:
    """In-memory view of the one metadata file, hydrated at restore."""

    def __init__(self) -> None:
        self.records: dict[str, dict[str, Any]] = {}
        self.hydration_ms: float = 0.0
        self.hydration_breakdown: dict[str, float] = {}
        self.loaded_from_disk = False
        self.hits = 0
        self.misses = 0
        self.publish_failures = 0

    # -- lookup ---------------------------------------------------------------

    def get(self, path: str, identity: tuple[int, ...]) -> Optional[Any]:
        record = self.records.get(path)
        if record is None or tuple(record.get("identity") or ()) != tuple(identity):
            self.misses += 1
            return None
        self.hits += 1
        return build_layout(record, path, tuple(identity))

    def put(self, layout: Any) -> None:
        self.records[str(layout.path)] = normalize_layout(layout)

    # -- persistence ----------------------------------------------------------

    def hydrate(self, *, path: Optional[str] = None) -> dict[str, Any]:
        """Read and deserialize the single cache file. Never raises."""
        breakdown: dict[str, float] = {}
        started = time.perf_counter()
        target = path or cache_path()
        payload = b""
        try:
            t0 = time.perf_counter()
            with open(target, "rb") as handle:
                payload = handle.read()
            breakdown["open_read_ms"] = (time.perf_counter() - t0) * 1000.0
        except Exception:
            breakdown["open_read_ms"] = (time.perf_counter() - started) * 1000.0
            breakdown["total_ms"] = (time.perf_counter() - started) * 1000.0
            self.hydration_breakdown = breakdown
            self.hydration_ms = breakdown["total_ms"]
            self.loaded_from_disk = False
            return dict(breakdown)

        try:
            t0 = time.perf_counter()
            document = pickle.loads(payload)
            if not isinstance(document, dict) or document.get("schema") != CACHE_SCHEMA_VERSION:
                raise ValueError("metadata_cache_schema_mismatch")
            records = document.get("records")
            if not isinstance(records, dict):
                raise ValueError("metadata_cache_records_invalid")
            self.records = records
            self.loaded_from_disk = True
            breakdown["deserialize_ms"] = (time.perf_counter() - t0) * 1000.0
        except Exception:
            # A corrupt cache must never make Golden incorrect.
            self.records = {}
            self.loaded_from_disk = False
            breakdown["deserialize_ms"] = (time.perf_counter() - t0) * 1000.0

        breakdown["bytes"] = float(len(payload))
        breakdown["models"] = float(len(self.records))
        breakdown["total_ms"] = (time.perf_counter() - started) * 1000.0
        self.hydration_breakdown = breakdown
        self.hydration_ms = breakdown["total_ms"]
        return dict(breakdown)

    def publish(self, *, path: Optional[str] = None) -> bool:
        """Write the one file atomically. Call outside the request path."""
        target = path or cache_path()
        document = {"schema": CACHE_SCHEMA_VERSION, "records": self.records}
        try:
            payload = pickle.dumps(document, protocol=pickle.HIGHEST_PROTOCOL)
            directory = os.path.dirname(target)
            os.makedirs(directory, exist_ok=True)
            handle, temp_path = tempfile.mkstemp(dir=directory, suffix=".tmp")
            try:
                with os.fdopen(handle, "wb") as stream:
                    stream.write(payload)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(temp_path, target)
            except BaseException:
                try:
                    os.unlink(temp_path)
                except OSError:
                    pass
                raise
            return True
        except Exception:
            self.publish_failures += 1
            return False

    def telemetry(self) -> dict[str, Any]:
        return {
            "loaded_from_disk": self.loaded_from_disk,
            "models": len(self.records),
            "hits": self.hits,
            "misses": self.misses,
            "publish_failures": self.publish_failures,
            "hydration_ms": round(self.hydration_ms, 3),
            "hydration_breakdown_ms": {
                key: (round(value, 3) if isinstance(value, float) else value)
                for key, value in self.hydration_breakdown.items()
            },
        }


_CACHE = MetadataCache()


def cache() -> MetadataCache:
    return _CACHE


def reset_for_tests() -> MetadataCache:
    global _CACHE
    _CACHE = MetadataCache()
    return _CACHE