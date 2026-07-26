"""Explicit output delivery strategy chain.

Strategies:
  DirectOutputSink              — production registry entries (in-memory encoded data)
  HistoryOutputCollector        — ComfyUI execution history outputs
  RequestBoundFilesystemCollector — constrained filesystem scan by request/prompt/node IDs
  SubprocessOutputCollector     — subprocess stdout/stderr output collection

Each strategy returns a structured ``Attempt`` with metrics.
"""

from __future__ import annotations

import base64
import dataclasses
import hashlib
import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import Any, Callable, Mapping, Sequence

from .contracts import OutputStrategy


# ---------------------------------------------------------------------------
# Structured result types
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ConversionMeta:
    """Per-item conversion metadata.

    Computed by the strategy that converts raw bytes into deliverable forms.
    Base64 metrics are zero in descriptor mode (no base64 for mere metrics).
    """
    format: str = ""
    mime_type: str = ""
    file_ext: str = ""
    raw_bytes: int = 0
    base64_bytes: int = 0
    json_result_bytes: int = 0
    hash_of_raw: str = ""  # sha256 of raw converted bytes, computed *before* base64
    conversion_time_ms: float = 0.0


@dataclass(frozen=True)
class OutputItem:
    """A single output item produced by a strategy."""
    node_id: str = ""
    output_key: str = ""
    filename: str = ""
    path: str = ""
    raw_bytes: bytes = b""
    base64_data: str = ""
    content_sha256: str = ""
    mime_type: str = ""
    file_ext: str = ""
    width: int = 0
    height: int = 0
    output_index: int = 0
    comparison_side: str = ""
    format: str = ""
    animated: bool = False
    conversion_meta: ConversionMeta | None = None

    def __post_init__(self) -> None:
        if self.content_sha256:
            return
        digest = (
            self.conversion_meta.hash_of_raw
            if self.conversion_meta is not None and self.conversion_meta.hash_of_raw
            else (hashlib.sha256(self.raw_bytes).hexdigest() if self.raw_bytes else "")
        )
        object.__setattr__(self, "content_sha256", digest)


@dataclass(frozen=True)
class Attempt:
    """Result of attempting to collect output via a single strategy."""
    strategy: str = ""
    success: bool = False
    items: tuple[OutputItem, ...] = ()
    total_items: int = 0
    total_raw_bytes: int = 0
    total_base64_bytes: int = 0
    total_json_result_bytes: int = 0
    total_conversion_time_ms: float = 0.0
    error: str = ""
    metrics: Mapping[str, Any] = field(default_factory=lambda: MappingProxyType({}))
    # ── Phase 6 timing / fallback observability ─────────────────────
    strategy_start_ms: float = 0.0
    strategy_end_ms: float = 0.0
    strategy_duration_ms: float = 0.0
    fallback_depth: int = 0
    attempt_number: int = 0
    total_base64_encoding_time_ms: float = 0.0
    # ── Phase 6 result serialization size ────────────────────────────
    serialized_result_bytes: int = 0
    # ── Phase 6 output-delivery diagnostics ──────────────────────────
    output_asset_write_ms: float = 0.0
    output_volume_commit_ms: float = 0.0
    output_commit_overlap_ms: float = 0.0
    output_hash_count: int = 0
    base64_encode_count: int = 0
    base64_decode_count: int = 0

    def __post_init__(self) -> None:
        if self.output_hash_count == 0 and self.items:
            object.__setattr__(self, "output_hash_count", len(self.items))
        if self.base64_encode_count == 0 and self.items:
            object.__setattr__(
                self,
                "base64_encode_count",
                sum(1 for item in self.items if item.base64_data),
            )

    @property
    def conversion_total_ms(self) -> float:
        """Compatibility alias for ``total_conversion_time_ms``."""
        return self.total_conversion_time_ms

    @property
    def timing(self) -> dict[str, float]:
        """Return a flat dict of timing fields for serialization."""
        return {
            "strategy_start_ms": self.strategy_start_ms,
            "strategy_end_ms": self.strategy_end_ms,
            "strategy_duration_ms": self.strategy_duration_ms,
            "fallback_depth": float(self.fallback_depth),
            "attempt_number": float(self.attempt_number),
            "total_base64_encoding_time_ms": self.total_base64_encoding_time_ms,
            "total_conversion_time_ms": self.total_conversion_time_ms,
        }


# ---------------------------------------------------------------------------
# Lane C: AssetDescriptor — lightweight metadata-only output descriptor
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class AssetDescriptor:
    """Lightweight asset metadata for V2 production and Studio consumption.

    Contains NO raw bytes or base64 data.  Frontend fetches actual bytes
    asynchronously through the existing asset-serving route.

    Fields match the Studio frontend contract:
      identity            — content hash (sha256:hex) for dedup/caching
      path                — filesystem path on backend volume or local FS
      filename            — display filename
      mime_type           — MIME type (e.g. ``image/png``)
      file_ext            — file extension (e.g. ``.png``)
      width, height       — pixel dimensions
      byte_count          — file size in bytes
      node_id             — ComfyUI node that produced this output
      output_key          — output key (e.g. ``images``, ``b_images``)
      output_index        — index within the output list
      comparison_side     — ``"a"``, ``"b"``, or ``""``
      generation          — generation / version tag
      thumbnail_identity  — optional identity string for thumbnail variant
    """
    asset_id: str = ""
    identity: str = ""
    backend_path: str = ""
    path: str = ""
    filename: str = ""
    mime_type: str = ""
    file_ext: str = ""
    width: int = 0
    height: int = 0
    byte_count: int = 0
    node_id: str = ""
    output_key: str = ""
    output_index: int = 0
    comparison_side: str = ""
    generation: str = ""
    thumbnail_identity: str = ""


def build_asset_descriptor_list(
    attempt: Attempt,
    *,
    generation: str = "",
    thumbnail_identities: Mapping[str, str] | None = None,
) -> list[AssetDescriptor]:
    """Build a list of lightweight ``AssetDescriptor`` from an *Attempt*.

    *generation* is an optional version tag applied to all descriptors.
    *thumbnail_identities* maps ``node_id`` → thumbnail identity string.

    No base64 data is computed or included — this is the pure metadata path.
    """
    descriptors: list[AssetDescriptor] = []
    for item in attempt.items:
        # Use content_sha256 from _item_from_entry (pre-computed).
        # Defensive fallback for items created outside _item_from_entry.
        digest = item.content_sha256 or (
            item.conversion_meta.hash_of_raw
            if item.conversion_meta is not None else ""
        )
        identity = f"sha256:{digest}" if digest else ""
        thumb_id = ""
        if thumbnail_identities is not None:
            thumb_id = thumbnail_identities.get(item.node_id, "")
        descriptors.append(AssetDescriptor(
            asset_id=digest,
            identity=identity,
            backend_path=item.path,
            path=item.path,
            filename=item.filename,
            mime_type=item.mime_type,
            file_ext=item.file_ext,
            width=item.width,
            height=item.height,
            byte_count=len(item.raw_bytes),
            node_id=item.node_id,
            output_key=item.output_key,
            output_index=item.output_index,
            comparison_side=item.comparison_side,
            generation=generation,
            thumbnail_identity=thumb_id,
        ))
    return descriptors


def attempt_to_descriptor_result(
    attempt: Attempt,
    *,
    generation: str = "",
    legacy_data: bool = False,
    thumbnail_identities: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Convert an *Attempt* to a result dict with lightweight descriptors.

    Default mode (``legacy_data=False``) produces entries WITHOUT ``data``
    or ``base64_data`` — frontend fetches bytes via existing asset route.
    In descriptor mode, base64 metrics are zero and ``include_base64`` is
    ``False``.

    Set *legacy_data* to ``True`` for the narrow fallback that includes
    inline base64 ``data`` (preserved for backward compatibility).

    The returned dict always carries:
      - ``images`` / ``videos`` arrays with metadata-only entries
      - ``outputs`` dict with native ComfyUI ``{filename, subfolder, type}``
      - ``asset_descriptors`` list with full ``AssetDescriptor`` dicts
    """
    descriptors = build_asset_descriptor_list(
        attempt,
        generation=generation,
        thumbnail_identities=thumbnail_identities,
    )
    outputs: dict[str, dict[str, list[dict[str, Any]]]] = {}
    images: list[dict[str, Any]] = []
    videos: list[dict[str, Any]] = []

    for item in attempt.items:
        output_key = item.output_key or ("gifs" if item.animated else "images")
        raw = item.raw_bytes
        # Use content_sha256 from _item_from_entry (pre-computed).
        # Defensive fallback for items created outside _item_from_entry.
        digest = item.content_sha256 or (
            item.conversion_meta.hash_of_raw
            if item.conversion_meta is not None else ""
        )
        identity = f"sha256:{digest}" if digest else ""
        entry: dict[str, Any] = {
            "asset_id": digest,
            "filename": item.filename,
            "node_id": item.node_id,
            "output_key": output_key,
            "comparison_side": item.comparison_side,
            "mime_type": item.mime_type,
            "file_ext": item.file_ext,
            "width": item.width,
            "height": item.height,
            "output_index": item.output_index,
            "format": item.format,
            "byte_count": len(raw),
            "identity": identity,
            "backend_path": item.path,
            "path": item.path,
            "generation": generation,
        }
        if legacy_data:
            data = item.base64_data or base64.b64encode(raw).decode("ascii") if raw else ""
            entry["data"] = data

        # Native ComfyUI output descriptor (filename/subfolder/type)
        native_entry = {
            "filename": item.filename,
            "subfolder": "",
            "type": "output",
        }
        outputs.setdefault(item.node_id, {}).setdefault(output_key, []).append(native_entry)

        if item.animated or output_key in {"gifs", "videos"}:
            videos.append(entry)
        else:
            images.append(entry)

    descriptors_as_dicts = [dataclasses.asdict(d) for d in descriptors]

    return {
        "images": images,
        "videos": videos,
        "outputs": outputs,
        "asset_descriptors": descriptors_as_dicts,
        "use_descriptors": True,
        "include_base64": bool(legacy_data),
    }


def attempt_to_descriptor_result_v2(
    attempt: Attempt,
    *,
    generation: str = "",
    include_base64: bool = False,
    thumbnail_identities: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """V2 descriptor result — defaults include_base64 to False.

    Unlike attempt_to_descriptor_result which uses legacy_data=True for
    backward-compatible base64 inclusion, this function explicitly defaults
    to no base64.  Production callers should use this; legacy callers use
    attempt_to_descriptor_result with legacy_data=True.
    """
    return attempt_to_descriptor_result(
        attempt,
        generation=generation,
        legacy_data=include_base64,
        thumbnail_identities=thumbnail_identities,
    )


# ---------------------------------------------------------------------------
# Conversion helpers (dependency-safe; uses output_converter via narrow import)
# ---------------------------------------------------------------------------

def _import_converter():
    """Lazy narrow import of output_converter to avoid ComfyUI dependency at module load."""
    from output_converter import convert_image_bytes, change_extension
    return convert_image_bytes, change_extension


def _import_output_saver_helpers():
    """Lazy import of output_saver helpers for path resolution."""
    from output_saver import _resolve_save_folder, _resolve_modal_output_dir
    return _resolve_save_folder, _resolve_modal_output_dir


def _hash_raw_bytes(raw: bytes) -> str:
    """SHA-256 hex digest of raw bytes."""
    return hashlib.sha256(raw).hexdigest()


def _measure_json_bytes(payload: dict) -> int:
    """Return the JSON UTF-8 byte length of *payload* (measurement only, no side effects).

    Uses compact separators to match typical wire serialization without
    duplicating or transmitting the payload.
    """
    return len(json.dumps(payload, separators=(",", ":")).encode("utf-8"))


def _make_conversion_meta(
    raw_bytes: bytes,
    format: str,
    mime_type: str,
    file_ext: str,
    conversion_time_ms: float,
) -> ConversionMeta:
    """Build ConversionMeta from raw bytes.

    NOTE: base64 is NOT constructed merely for metrics — the
    ``base64_bytes`` and ``json_result_bytes`` fields are set to 0.
    In the narrow legacy path where base64 is actually needed,
    those fields are populated downstream.
    """
    return ConversionMeta(
        format=format,
        mime_type=mime_type,
        file_ext=file_ext,
        raw_bytes=len(raw_bytes),
        base64_bytes=0,
        json_result_bytes=0,
        hash_of_raw=_hash_raw_bytes(raw_bytes),
        conversion_time_ms=conversion_time_ms,
    )


def _timed_b64_encode(data: bytes) -> tuple[str, float]:
    """Base64-encode *data* and return (encoded_str, duration_ms)."""
    t0 = time.monotonic()
    encoded = base64.b64encode(data).decode("ascii")
    duration_ms = (time.monotonic() - t0) * 1000.0
    return encoded, duration_ms


# ---------------------------------------------------------------------------
# Strategy base
# ---------------------------------------------------------------------------

def _item_from_entry(
    entry: Mapping[str, Any],
    *,
    node_id: str,
    output_key: str,
    fallback_index: int = 0,
    path: str = "",
    descriptor_mode: bool = True,
) -> tuple[OutputItem, float]:
    """Build an OutputItem from a dictionary entry (registry or result dict).

    In *descriptor_mode* (default), base64 is NOT computed — the returned
    ``OutputItem`` has an empty ``base64_data`` field.  Set
    ``descriptor_mode=False`` for the narrow legacy fallback that includes
    base64 encoding.

    Returns ``(item, base64_encoding_time_ms)``.
    """
    raw = entry.get("raw_bytes") or entry.get("bytes") or b""
    if not raw and "data" in entry:
        raw = base64.b64decode(entry["data"])
    b64_data = entry.get("base64_data") or ""
    b64_time_ms = 0.0
    if not descriptor_mode and not b64_data and raw:
        b64_data, b64_time_ms = _timed_b64_encode(raw)
    meta_raw = entry.get("conversion_meta")
    if meta_raw is not None and isinstance(meta_raw, ConversionMeta):
        conv_meta = meta_raw
    elif raw:
        conv_meta = _make_conversion_meta(
            raw_bytes=raw,
            format=str(entry.get("format", "") or "original"),
            mime_type=str(entry.get("mime_type", "image/png")),
            file_ext=str(entry.get("file_ext", ".png")),
            conversion_time_ms=float(entry.get("conversion_time_ms", 0) or 0),
        )
    else:
        conv_meta = None
    # Compute content_sha256 once from final raw bytes
    _content_sha256 = (
        conv_meta.hash_of_raw
        if conv_meta is not None and conv_meta.hash_of_raw
        else (hashlib.sha256(raw).hexdigest() if raw else "")
    )
    return (
        OutputItem(
            node_id=str(node_id),
            output_key=str(output_key),
            filename=str(entry.get("filename", f"output_{fallback_index}.bin")),
            path=path or str(entry.get("path", "")),
            raw_bytes=raw,
            base64_data=b64_data,
            content_sha256=_content_sha256,
            mime_type=str(entry.get("mime_type", "image/png")),
            file_ext=str(entry.get("file_ext", ".png")),
            width=int(entry.get("width", 0) or 0),
            height=int(entry.get("height", 0) or 0),
            output_index=int(entry.get("output_index", fallback_index)),
            comparison_side=str(entry.get("comparison_side", "")),
            format=str(entry.get("format", "")),
            animated=bool(entry.get("animated", False)),
            conversion_meta=conv_meta,
        ),
        b64_time_ms,
    )


# ---------------------------------------------------------------------------
# Strategy 1: DirectOutputSink
# ---------------------------------------------------------------------------

class DirectOutputSink:
    """Collect output from an in-memory production output registry.

    Reads entries keyed by ``(prompt_id, node_id)`` from a provided
    registry dict (the ``_production_output_registry`` shape).
    """

    NAME = "direct_output_sink"

    def __init__(self, registry: Mapping[str, Any] | None = None):
        self._registry = dict(registry or {})

    @classmethod
    def from_registry(
        cls,
        registry: Mapping[str, Any],
    ) -> DirectOutputSink:
        return cls(registry=registry)

    def collect(
        self,
        strategy: OutputStrategy | None = None,
        *,
        prompt_id: str = "",
        output_node_ids: tuple[str, ...] = (),
        descriptor_mode: bool = True,
    ) -> Attempt:
        items: list[OutputItem] = []
        total_raw = 0
        total_b64 = 0
        total_json = 0
        total_conv_ms = 0.0
        total_b64_time_ms = 0.0

        for node_id, node_registry in self._registry.items():
            if output_node_ids and node_id not in output_node_ids:
                continue
            if isinstance(node_registry, list):
                grouped_entries = {"images": node_registry}
            elif isinstance(node_registry, dict):
                grouped_entries = node_registry
            else:
                continue
            for output_key, entries in grouped_entries.items():
                if not isinstance(entries, list):
                    continue
                for idx, entry in enumerate(entries):
                    if not isinstance(entry, dict):
                        continue
                    item, b64_time = _item_from_entry(
                        entry,
                        node_id=node_id,
                        output_key=str(entry.get("output_key") or output_key),
                        fallback_index=idx,
                        descriptor_mode=descriptor_mode,
                    )
                    items.append(item)
                    total_raw += len(item.raw_bytes)
                    if item.base64_data:
                        total_b64 += len(item.base64_data)
                    total_b64_time_ms += b64_time
                    if item.conversion_meta:
                        total_json += item.conversion_meta.json_result_bytes
                        total_conv_ms += item.conversion_meta.conversion_time_ms

        return Attempt(
            strategy=self.NAME,
            success=bool(items),
            items=tuple(items),
            total_items=len(items),
            total_raw_bytes=total_raw,
            total_base64_bytes=total_b64,
            total_json_result_bytes=total_json,
            total_conversion_time_ms=total_conv_ms,
            total_base64_encoding_time_ms=total_b64_time_ms,
            metrics={
                "source": "registry",
                "prompt_id": prompt_id,
                "node_count": len({i.node_id for i in items}),
            },
        )


# ---------------------------------------------------------------------------
# Strategy 2: HistoryOutputCollector
# ---------------------------------------------------------------------------

class HistoryOutputCollector:
    """Collect output from ComfyUI execution history.

    The history dict is the standard ``{prompt_id: {"outputs": {...}}}``
    shape produced by the ComfyUI PromptQueue.
    """

    NAME = "history_output_collector"

    def __init__(self, history: Mapping[str, Any] | None = None):
        self._history = dict(history or {})

    @classmethod
    def from_history(cls, history: Mapping[str, Any]) -> HistoryOutputCollector:
        return cls(history=history)

    def collect(
        self,
        strategy: OutputStrategy | None = None,
        *,
        prompt_id: str = "",
        output_node_ids: tuple[str, ...] = (),
        materials_dir: str = "",
        descriptor_mode: bool = True,
    ) -> Attempt:
        items: list[OutputItem] = []
        total_b64_time_ms = 0.0
        prompt_history = self._history.get(prompt_id, {})
        outputs = prompt_history.get("outputs", {}) if isinstance(prompt_history, dict) else {}

        for node_id, node_outputs in outputs.items():
            if output_node_ids and node_id not in output_node_ids:
                continue
            if not isinstance(node_outputs, dict):
                continue
            for output_key, entries in node_outputs.items():
                if not isinstance(entries, list):
                    continue
                for idx, entry in enumerate(entries):
                    if not isinstance(entry, dict):
                        continue
                    resolved_path = ""
                    if materials_dir:
                        filename = entry.get("filename", "")
                        if filename:
                            candidate = os.path.join(materials_dir, filename)
                            if os.path.isfile(candidate):
                                resolved_path = candidate
                    entry_for_item = entry
                    if resolved_path and not (
                        entry.get("raw_bytes")
                        or entry.get("bytes")
                        or entry.get("data")
                    ):
                        try:
                            entry_for_item = dict(entry)
                            entry_for_item["raw_bytes"] = Path(resolved_path).read_bytes()
                        except OSError:
                            entry_for_item = entry
                    item, b64_time = _item_from_entry(
                        entry_for_item,
                        node_id=node_id,
                        output_key=str(output_key),
                        fallback_index=idx,
                        path=resolved_path,
                        descriptor_mode=descriptor_mode,
                    )
                    items.append(item)
                    total_b64_time_ms += b64_time

        total_raw = sum(len(i.raw_bytes) for i in items)
        total_b64 = sum(len(i.base64_data) for i in items)
        total_json = sum(
            i.conversion_meta.json_result_bytes for i in items if i.conversion_meta
        )
        total_conv_ms = sum(
            i.conversion_meta.conversion_time_ms for i in items if i.conversion_meta
        )

        return Attempt(
            strategy=self.NAME,
            success=bool(items),
            items=tuple(items),
            total_items=len(items),
            total_raw_bytes=total_raw,
            total_base64_bytes=total_b64,
            total_json_result_bytes=total_json,
            total_conversion_time_ms=total_conv_ms,
            total_base64_encoding_time_ms=total_b64_time_ms,
            metrics={
                "source": "history",
                "prompt_id": prompt_id,
                "node_count": len({i.node_id for i in items}),
            },
        )


# ---------------------------------------------------------------------------
# Strategy 3: RequestBoundFilesystemCollector
# ---------------------------------------------------------------------------

class RequestBoundFilesystemCollector:
    """Filesystem fallback constrained by request/prompt/node IDs and
    request start boundary.

    Scans ``materials_dir`` for files whose names contain the prompt_id
    or output_node_ids.  Never performs an unrestricted recent-file scan.
    """

    NAME = "request_bound_filesystem_collector"

    def __init__(
        self,
        materials_dir: str = "",
        *,
        mime_type_hint: str = "image/png",
        file_ext_hint: str = ".png",
    ):
        self._materials_dir = materials_dir
        self._mime_type_hint = mime_type_hint
        self._file_ext_hint = file_ext_hint

    def collect(
        self,
        strategy: OutputStrategy | None = None,
        *,
        prompt_id: str = "",
        output_node_ids: tuple[str, ...] = (),
        request_start_boundary: float = 0.0,
        descriptor_mode: bool = True,
    ) -> Attempt:
        items: list[OutputItem] = []
        if not self._materials_dir or not os.path.isdir(self._materials_dir):
            return Attempt(
                strategy=self.NAME,
                success=False,
                error="materials_dir not available",
            )

        # Build safe search tokens
        tokens: set[str] = set()
        if prompt_id:
            tokens.add(prompt_id)
        for nid in output_node_ids:
            tokens.add(nid)

        if not tokens:
            return Attempt(
                strategy=self.NAME,
                success=False,
                error="no search tokens (prompt_id or output_node_ids required)",
            )

        scanned = 0
        total_b64_time_ms = 0.0
        for fname in os.listdir(self._materials_dir):
            fpath = os.path.join(self._materials_dir, fname)
            if not os.path.isfile(fpath):
                continue
            if not any(token in fname for token in tokens):
                continue
            # Check request start boundary (mtime >= boundary)
            if request_start_boundary > 0:
                try:
                    mtime = os.path.getmtime(fpath)
                    if mtime < request_start_boundary:
                        continue
                except OSError:
                    continue
            scanned += 1
            try:
                raw = Path(fpath).read_bytes()
            except OSError:
                continue
            ext = Path(fname).suffix or self._file_ext_hint
            # Derive node_id from filename if possible
            derived_node_id = ""
            for nid in output_node_ids:
                if nid in fname:
                    derived_node_id = nid
                    break
            conv = _make_conversion_meta(raw, "original", self._mime_type_hint, ext, 0.0)
            b64_data = ""
            b64_time = 0.0
            if not descriptor_mode:
                b64_data, b64_time = _timed_b64_encode(raw)
                total_b64_time_ms += b64_time
            item = OutputItem(
                node_id=derived_node_id,
                output_key="images",
                filename=fname,
                path=fpath,
                raw_bytes=raw,
                base64_data=b64_data,
                mime_type=self._mime_type_hint,
                file_ext=ext,
                conversion_meta=conv,
            )
            items.append(item)

        total_raw = sum(len(i.raw_bytes) for i in items)
        total_b64 = sum(len(i.base64_data) for i in items)
        total_json = sum(
            i.conversion_meta.json_result_bytes for i in items if i.conversion_meta
        )

        return Attempt(
            strategy=self.NAME,
            success=bool(items),
            items=tuple(items),
            total_items=len(items),
            total_raw_bytes=total_raw,
            total_base64_bytes=total_b64,
            total_json_result_bytes=total_json,
            total_conversion_time_ms=0.0,
            total_base64_encoding_time_ms=total_b64_time_ms,
            metrics={
                "source": "filesystem",
                "prompt_id": prompt_id,
                "files_scanned": scanned,
                "materials_dir": self._materials_dir,
            },
        )


# ---------------------------------------------------------------------------
# Strategy 4: SubprocessOutputCollector
# ---------------------------------------------------------------------------

class SubprocessOutputCollector:
    """Collect output from a subprocess stdout/stderr.

    Useful for capturing output from external tools or scripts
    that produce stdout/stderr files in a constrained directory.
    """

    NAME = "subprocess_output_collector"

    def __init__(self, subprocess_output_dir: str = ""):
        self._output_dir = subprocess_output_dir

    def collect(
        self,
        strategy: OutputStrategy | None = None,
        *,
        prompt_id: str = "",
        output_node_ids: tuple[str, ...] = (),
        descriptor_mode: bool = True,
    ) -> Attempt:
        items: list[OutputItem] = []
        if not self._output_dir or not os.path.isdir(self._output_dir):
            return Attempt(
                strategy=self.NAME,
                success=False,
                error="subprocess_output_dir not available",
            )

        # Build safe search tokens — fail closed when neither prompt_id
        # nor output_node_ids provides a constraint.  Never add an empty
        # token that would scan every file.
        tokens: set[str] = set()
        if prompt_id:
            tokens.add(prompt_id)
        for nid in output_node_ids:
            tokens.add(nid)
        if not tokens:
            return Attempt(
                strategy=self.NAME,
                success=False,
                error="no constraint tokens (prompt_id or output_node_ids required)",
            )

        total_b64_time_ms = 0.0
        for fname in os.listdir(self._output_dir):
            fpath = os.path.join(self._output_dir, fname)
            if not os.path.isfile(fpath):
                continue
            if not any(token in fname for token in tokens):
                continue

            try:
                raw = Path(fpath).read_bytes()
            except OSError:
                continue

            ext = Path(fname).suffix or ".bin"
            mime = "text/plain"
            if ext in (".png", ".jpg", ".jpeg", ".webp", ".gif"):
                mime_map = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
                            ".webp": "image/webp", ".gif": "image/gif"}
                mime = mime_map.get(ext, "image/png")

            derived_node_id = ""
            for nid in output_node_ids:
                if nid in fname:
                    derived_node_id = nid
                    break

            conv = _make_conversion_meta(raw, "original", mime, ext, 0.0)
            b64_data = ""
            b64_time = 0.0
            if not descriptor_mode:
                b64_data, b64_time = _timed_b64_encode(raw)
                total_b64_time_ms += b64_time
            item = OutputItem(
                node_id=derived_node_id,
                output_key=prompt_id if prompt_id else "subprocess",
                filename=fname,
                path=fpath,
                raw_bytes=raw,
                base64_data=b64_data,
                mime_type=mime,
                file_ext=ext,
                conversion_meta=conv,
            )
            items.append(item)

        total_raw = sum(len(i.raw_bytes) for i in items)

        return Attempt(
            strategy=self.NAME,
            success=bool(items),
            items=tuple(items),
            total_items=len(items),
            total_raw_bytes=total_raw,
            total_base64_bytes=sum(len(i.base64_data) for i in items),
            total_json_result_bytes=sum(
                i.conversion_meta.json_result_bytes for i in items if i.conversion_meta
            ),
            total_base64_encoding_time_ms=total_b64_time_ms,
            metrics={
                "source": "subprocess_output_dir",
                "prompt_id": prompt_id,
                "output_dir": self._output_dir,
            },
        )


# ---------------------------------------------------------------------------
# Strategy chain runner
# ---------------------------------------------------------------------------

def run_strategy_chain(
    strategies: list[Any],
    *,
    strategy_config: OutputStrategy | None = None,
    prompt_id: str = "",
    output_node_ids: tuple[str, ...] = (),
    materials_dir: str = "",
    request_start_boundary: float = 0.0,
    descriptor_mode: bool = True,
    **kwargs: Any,
) -> list[Attempt]:
    """Run each strategy in order, collecting attempts.

    Strategies are called left-to-right. Each strategy's ``collect``
    method receives the ``prompt_id``, ``output_node_ids``, and
    strategy-specific extras.

    When *descriptor_mode* is True (default), base64 is NOT computed
    — the returned Attempts carry ``OutputItem`` objects with empty
    ``base64_data`` fields, suitable for ``attempt_to_descriptor_result``.

    Each returned ``Attempt`` includes per-strategy timing
    (``strategy_start_ms``, ``strategy_end_ms``, ``strategy_duration_ms``),
    ``attempt_number`` (position in chain), and ``fallback_depth`` (number of
    earlier failed strategies before the first successful one).
    """
    results: list[Attempt] = []
    fallback_depth = 0
    found_success = False
    for attempt_number, strat in enumerate(strategies):
        t0 = time.monotonic()
        try:
            if isinstance(strat, DirectOutputSink):
                attempt = strat.collect(strategy_config, prompt_id=prompt_id, output_node_ids=output_node_ids, descriptor_mode=descriptor_mode)
            elif isinstance(strat, HistoryOutputCollector):
                attempt = strat.collect(strategy_config, prompt_id=prompt_id, output_node_ids=output_node_ids, materials_dir=materials_dir, descriptor_mode=descriptor_mode)
            elif isinstance(strat, RequestBoundFilesystemCollector):
                attempt = strat.collect(strategy_config, prompt_id=prompt_id, output_node_ids=output_node_ids, request_start_boundary=request_start_boundary, descriptor_mode=descriptor_mode)
            elif isinstance(strat, SubprocessOutputCollector):
                attempt = strat.collect(strategy_config, prompt_id=prompt_id, output_node_ids=output_node_ids, descriptor_mode=descriptor_mode)
            else:
                attempt = Attempt(strategy=getattr(strat, "NAME", "unknown"), success=False, error="unknown strategy type")
        except Exception as exc:
            attempt = Attempt(
                strategy=getattr(strat, "NAME", "unknown"),
                success=False,
                error=f"{type(exc).__name__}: {exc}",
            )
        t1 = time.monotonic()
        elapsed_ms = (t1 - t0) * 1000.0
        # fallback_depth counts failed strategies *before* this one
        attempt = _replace_attempt_timing(attempt, t0, t1, elapsed_ms, attempt_number, fallback_depth)
        results.append(attempt)
        # Update for next iteration: increment only for failures before first success
        if not found_success and not attempt.success:
            fallback_depth += 1
        if attempt.success:
            found_success = True
    return results


def _replace_attempt_timing(
    attempt: Attempt,
    start_mono: float,
    end_mono: float,
    duration_ms: float,
    attempt_number: int,
    fallback_depth: int,
) -> Attempt:
    """Return a new ``Attempt`` with Phase 6 timing fields set."""
    start_ms = start_mono * 1000.0
    end_ms = end_mono * 1000.0
    metrics = dict(attempt.metrics)
    metrics["strategy_start_ms"] = start_ms
    metrics["strategy_end_ms"] = end_ms
    metrics["strategy_duration_ms"] = duration_ms
    metrics["attempt_number"] = attempt_number
    metrics["fallback_depth"] = fallback_depth
    return Attempt(
        strategy=attempt.strategy,
        success=attempt.success,
        items=attempt.items,
        total_items=attempt.total_items,
        total_raw_bytes=attempt.total_raw_bytes,
        total_base64_bytes=attempt.total_base64_bytes,
        total_json_result_bytes=attempt.total_json_result_bytes,
        total_conversion_time_ms=attempt.total_conversion_time_ms,
        error=attempt.error,
        metrics=MappingProxyType(metrics),
        strategy_start_ms=start_ms,
        strategy_end_ms=end_ms,
        strategy_duration_ms=duration_ms,
        fallback_depth=fallback_depth,
        attempt_number=attempt_number,
        total_base64_encoding_time_ms=attempt.total_base64_encoding_time_ms,
        serialized_result_bytes=attempt.serialized_result_bytes,
    )


# ---------------------------------------------------------------------------
# Async output persistence (Modal Volume commit helpers)
# ---------------------------------------------------------------------------


async def _commit_volume_async(volume: Any) -> bool:
    """Async commit using Modal's awaited ``volume.commit.aio()``.

    Requires Modal's async interface. A volume without ``commit.aio()`` is
    rejected rather than calling the synchronous API from async delivery.
    Returns True on success.
    """
    import asyncio
    import inspect

    if volume is None:
        return False
    try:
        aio_fn = getattr(volume.commit, "aio", None)
        if aio_fn is not None:
            if inspect.isawaitable(aio_fn):
                await aio_fn
                return True
            result = aio_fn()
            if inspect.isawaitable(result):
                await result
                return True
        print("[output_delivery] commit_async unavailable: commit.aio() missing", flush=True)
        return False
    except Exception as exc:
        print(f"[output_delivery] commit_async failed: {exc}", flush=True)
        return False


async def persist_output_assets_async(
    volume: Any,
    *,
    output_dir: str = "",
    items: Sequence[OutputItem] = (),
    descriptors: Sequence[AssetDescriptor] = (),
    result_metadata: dict[str, Any] | None = None,
    metrics: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Persist output assets to a Modal Volume asynchronously.

    Steps:
      1. Atomic writes for each OutputItem that has raw_bytes.
      2. Start volume.commit.aio() immediately after writes.
      3. While commit runs, build descriptor/result metadata/metrics.
      4. Await commit before final result.

    Never calls blocking commit() in async context.
    No commit is issued when no new files were written (empty items).

    Returns diagnostics dict with write/commit timing.
    """
    import asyncio
    import json
    import inspect
    from pathlib import Path

    t0 = time.monotonic()
    diag: dict[str, Any] = {
        "files_written": 0,
        "bytes_written": 0,
        "write_ms": 0.0,
        "commit_ms": 0.0,
        "overlap_ms": 0.0,
        "errors": [],
    }

    if volume is None or not items:
        return diag

    output_path = output_dir or "outputs"

    # 1. Atomic writes
    write_t0 = time.monotonic()
    written_any = False
    for item in items:
        if not item.raw_bytes:
            continue
        filename = item.filename or f"output_{item.node_id}_{item.output_index}.bin"
        filepath = f"{output_path}/{filename}"
        try:
            exists = getattr(volume, "exists", None)
            if callable(exists) and exists(filepath):
                continue
            tmp_path = f"{output_path}/.{filename}.tmp"
            volume.write_bytes(tmp_path, item.raw_bytes)
            # Simulate atomic rename via write to final path
            volume.write_bytes(filepath, item.raw_bytes)
            volume.remove(tmp_path)
            diag["files_written"] += 1
            diag["bytes_written"] += len(item.raw_bytes)
            written_any = True
        except Exception as exc:
            diag["errors"].append(f"write:{filename}:{str(exc)[:60]}")

    diag["write_ms"] = round((time.monotonic() - write_t0) * 1000, 3)

    if not written_any:
        return diag

    # 2. Start commit
    commit_t0 = time.monotonic()
    commit_task = asyncio.create_task(_commit_volume_async(volume))

    # 3. Overlap: build descriptors/result/metadata while commit runs
    _build_overlap_t0 = time.monotonic()
    desc_list = [dataclasses.asdict(d) for d in descriptors] if descriptors else []
    meta = dict(result_metadata or {})
    metric_values = dict(metrics or {})
    overlap_ms = round((time.monotonic() - _build_overlap_t0) * 1000, 3)
    diag["overlap_ms"] = overlap_ms
    diag["descriptors"] = desc_list
    diag["result_metadata"] = meta
    diag["metrics"] = metric_values
    diag["serialized_result_bytes"] = len(
        json.dumps(
            {"asset_descriptors": desc_list, **meta, **metric_values},
            separators=(",", ":"),
            default=str,
        ).encode("utf-8")
    )

    # 4. Await commit
    try:
        commit_ok = await commit_task
        diag["commit_ms"] = round((time.monotonic() - commit_t0) * 1000, 3)
        if not commit_ok:
            diag["errors"].append("commit_failed")
    except Exception as exc:
        diag["commit_ms"] = round((time.monotonic() - commit_t0) * 1000, 3)
        diag["errors"].append(f"commit_error:{str(exc)[:60]}")

    diag["total_ms"] = round((time.monotonic() - t0) * 1000, 3)
    return diag


# ---------------------------------------------------------------------------
# Convenience: build default strategy chain
# ---------------------------------------------------------------------------

def build_default_chain(
    registry: Mapping[str, Any] | None = None,
    history: Mapping[str, Any] | None = None,
    materials_dir: str = "",
    subprocess_output_dir: str = "",
) -> list[Any]:
    """Build the standard four-strategy chain with sensible defaults."""
    chain: list[Any] = [
        DirectOutputSink(registry=registry),
        HistoryOutputCollector(history=history),
    ]
    if materials_dir:
        chain.append(RequestBoundFilesystemCollector(materials_dir=materials_dir))
    if subprocess_output_dir:
        chain.append(SubprocessOutputCollector(subprocess_output_dir=subprocess_output_dir))
    return chain
