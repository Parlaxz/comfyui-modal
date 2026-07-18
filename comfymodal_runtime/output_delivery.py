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
import hashlib
import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import Any, Callable, Mapping

from .contracts import OutputStrategy


# ---------------------------------------------------------------------------
# Structured result types
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ConversionMeta:
    """Per-item conversion metadata.

    Computed by the strategy that converts raw bytes into deliverable forms.
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
    mime_type: str = ""
    file_ext: str = ""
    width: int = 0
    height: int = 0
    output_index: int = 0
    comparison_side: str = ""
    format: str = ""
    animated: bool = False
    conversion_meta: ConversionMeta | None = None


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

    @property
    def conversion_total_ms(self) -> float:
        """Compatibility alias for ``total_conversion_time_ms``."""
        return self.total_conversion_time_ms


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


def _make_conversion_meta(
    raw_bytes: bytes,
    format: str,
    mime_type: str,
    file_ext: str,
    conversion_time_ms: float,
) -> ConversionMeta:
    """Build ConversionMeta from converted raw bytes (already encoded)."""
    b64 = base64.b64encode(raw_bytes)
    json_result = json.dumps({"data": b64.decode("ascii")}, separators=(",", ":")).encode("utf-8")
    return ConversionMeta(
        format=format,
        mime_type=mime_type,
        file_ext=file_ext,
        raw_bytes=len(raw_bytes),
        base64_bytes=len(b64),
        json_result_bytes=len(json_result),
        hash_of_raw=_hash_raw_bytes(raw_bytes),
        conversion_time_ms=conversion_time_ms,
    )


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
) -> OutputItem:
    """Build an OutputItem from a dictionary entry (registry or result dict)."""
    raw = entry.get("raw_bytes") or entry.get("bytes") or b""
    if not raw and "data" in entry:
        raw = base64.b64decode(entry["data"])
    b64_data = entry.get("base64_data") or ""
    if not b64_data and raw:
        b64_data = base64.b64encode(raw).decode("ascii")
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
    return OutputItem(
        node_id=str(node_id),
        output_key=str(output_key),
        filename=str(entry.get("filename", f"output_{fallback_index}.bin")),
        path=path or str(entry.get("path", "")),
        raw_bytes=raw,
        base64_data=b64_data,
        mime_type=str(entry.get("mime_type", "image/png")),
        file_ext=str(entry.get("file_ext", ".png")),
        width=int(entry.get("width", 0) or 0),
        height=int(entry.get("height", 0) or 0),
        output_index=int(entry.get("output_index", fallback_index)),
        comparison_side=str(entry.get("comparison_side", "")),
        format=str(entry.get("format", "")),
        animated=bool(entry.get("animated", False)),
        conversion_meta=conv_meta,
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
    ) -> Attempt:
        items: list[OutputItem] = []
        total_raw = 0
        total_b64 = 0
        total_json = 0
        total_conv_ms = 0.0

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
                    item = _item_from_entry(
                        entry,
                        node_id=node_id,
                        output_key=str(entry.get("output_key") or output_key),
                        fallback_index=idx,
                    )
                    items.append(item)
                    total_raw += len(item.raw_bytes)
                    total_b64 += len(item.base64_data)
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
    ) -> Attempt:
        items: list[OutputItem] = []
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
                    item = _item_from_entry(
                        entry_for_item,
                        node_id=node_id,
                        output_key=str(output_key),
                        fallback_index=idx,
                        path=resolved_path,
                    )
                    items.append(item)

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
            item = OutputItem(
                node_id=derived_node_id,
                output_key="images",
                filename=fname,
                path=fpath,
                raw_bytes=raw,
                base64_data=base64.b64encode(raw).decode("ascii"),
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
            item = OutputItem(
                node_id=derived_node_id,
                output_key=prompt_id if prompt_id else "subprocess",
                filename=fname,
                path=fpath,
                raw_bytes=raw,
                base64_data=base64.b64encode(raw).decode("ascii"),
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
    **kwargs: Any,
) -> list[Attempt]:
    """Run each strategy in order, collecting attempts.

    Strategies are called left-to-right. Each strategy's ``collect``
    method receives the ``prompt_id``, ``output_node_ids``, and
    strategy-specific extras.
    """
    results: list[Attempt] = []
    for strat in strategies:
        try:
            if isinstance(strat, DirectOutputSink):
                attempt = strat.collect(strategy_config, prompt_id=prompt_id, output_node_ids=output_node_ids)
            elif isinstance(strat, HistoryOutputCollector):
                attempt = strat.collect(strategy_config, prompt_id=prompt_id, output_node_ids=output_node_ids, materials_dir=materials_dir)
            elif isinstance(strat, RequestBoundFilesystemCollector):
                attempt = strat.collect(strategy_config, prompt_id=prompt_id, output_node_ids=output_node_ids, request_start_boundary=request_start_boundary)
            elif isinstance(strat, SubprocessOutputCollector):
                attempt = strat.collect(strategy_config, prompt_id=prompt_id, output_node_ids=output_node_ids)
            else:
                attempt = Attempt(strategy=getattr(strat, "NAME", "unknown"), success=False, error="unknown strategy type")
        except Exception as exc:
            attempt = Attempt(
                strategy=getattr(strat, "NAME", "unknown"),
                success=False,
                error=f"{type(exc).__name__}: {exc}",
            )
        results.append(attempt)
    return results


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
