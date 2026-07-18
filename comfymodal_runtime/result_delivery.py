"""Local result materialization and ComfyUI history compatibility.

Provides legacy payload adapters and a materialization function that
can accept current Modal result dictionaries *without* importing
ComfyUI at module import time.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import Any, Callable, Mapping

from .output_delivery import (
    Attempt,
    ConversionMeta,
    OutputItem,
    _item_from_entry,
    _make_conversion_meta,
)


# ---------------------------------------------------------------------------
# Native output descriptor (compat with ComfyUI's native format)
# ---------------------------------------------------------------------------

def build_native_output_descriptor(filename: str, subfolder: str = "", type_: str = "output") -> dict:
    """Build a standard ComfyUI native output descriptor dict.

    This is the format that ComfyUI execution history expects for
    ``images`` / ``gifs`` entries.
    """
    return {
        "filename": filename,
        "subfolder": subfolder,
        "type": type_,
    }


# ---------------------------------------------------------------------------
# MIME / extension helpers
# ---------------------------------------------------------------------------

_MIME_EXT_MAP = {
    "image/webp": ".webp",
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/gif": ".gif",
    "image/bmp": ".bmp",
}

_MIME_DEFAULT = "image/png"
_EXT_DEFAULT = ".png"


def infer_file_ext(filename: str, mime_type: str | None = None, file_ext: str | None = None) -> str:
    """Infer file extension from filename, MIME type, or explicit ext."""
    if file_ext:
        return file_ext if file_ext.startswith(".") else "." + file_ext
    if mime_type:
        ext = _MIME_EXT_MAP.get(mime_type.lower())
        if ext:
            return ext
    _, ext = os.path.splitext(filename)
    if ext:
        return ext
    return _EXT_DEFAULT


# ---------------------------------------------------------------------------
# Unique path helper (safe filename with conflict avoidance)
# ---------------------------------------------------------------------------

def unique_path(directory: str, filename: str) -> str:
    """Return a unique path in *directory* for *filename*.

    If the path already exists, appends a UUID fragment to avoid collision.
    Validates that the filename is safe (no path traversal, no null bytes).
    """
    if not filename or not isinstance(filename, str):
        raise ValueError(f"invalid filename: {filename!r}")
    if "\x00" in filename:
        raise ValueError("filename contains null byte")
    safe_name = Path(filename).name
    if safe_name != filename or ".." in filename or "/" in filename or "\\" in filename:
        raise ValueError(f"unsafe filename: {filename!r}")
    root = Path(directory).resolve()
    dest = (root / safe_name).resolve()
    if dest.parent != root:
        raise ValueError(f"path escaped root: {filename!r}")
    if not dest.exists():
        return str(dest)
    stem, ext = os.path.splitext(safe_name)
    suffix = uuid.uuid4().hex[:12]
    return str(root / f"{stem}_{suffix}{ext}")


# ---------------------------------------------------------------------------
# Stable output identity (de-duplication key)
# ---------------------------------------------------------------------------

def stable_output_identity(
    node_id: str,
    output_key: str,
    entry: Mapping[str, Any],
    fallback_index: int = 0,
) -> tuple[str, str, str, int]:
    """Build a stable identity tuple for de-duplication."""
    raw_index = entry.get("output_index", fallback_index)
    try:
        output_index = int(raw_index)
    except (TypeError, ValueError):
        output_index = fallback_index
    return (
        str(node_id),
        str(output_key or entry.get("output_key") or "images"),
        str(entry.get("filename", "")),
        output_index,
    )


# ---------------------------------------------------------------------------
# Materialized output entry builder
# ---------------------------------------------------------------------------

def build_materialized_output_entry(
    remote_entry: Mapping[str, Any],
    *,
    node_id: str,
    output_key: str,
    local_filename: str,
    local_path: str,
    decoded_bytes: bytes,
    fallback_index: int = 0,
) -> dict:
    """Build a materialized output entry dict with metadata."""
    inferred_ext = infer_file_ext(
        remote_entry.get("filename", local_filename),
        remote_entry.get("mime_type"),
        remote_entry.get("file_ext"),
    )
    return {
        "filename": local_filename,
        "path": local_path,
        "subfolder": "",
        "type": "output",
        "node_id": str(node_id),
        "output_key": output_key,
        "comparison_side": remote_entry.get("comparison_side", ""),
        "mime_type": remote_entry.get("mime_type", ""),
        "file_ext": inferred_ext,
        "width": remote_entry.get("width"),
        "height": remote_entry.get("height"),
        "format": remote_entry.get("format", ""),
        "output_index": remote_entry.get("output_index", fallback_index),
        "byte_count": len(decoded_bytes),
    }


# ---------------------------------------------------------------------------
# Primary output selection (B side preferred)
# ---------------------------------------------------------------------------

def select_primary_output(per_node_outputs: dict, node_id: str) -> dict | None:
    """Deterministically select the primary/final image entry for a node.

    Selection precedence:
    1. Entry with comparison_side == "b"
    2. Entry under b_images output key
    3. Entry marked primary/final
    4. Entry under images
    5. Entry with comparison_side == "a"
    6. First flat image as last-resort compatibility fallback
    """
    node_outputs = per_node_outputs.get(node_id)
    if not node_outputs or not isinstance(node_outputs, dict):
        return None

    for entries in node_outputs.values():
        if not isinstance(entries, list):
            continue
        for entry in entries:
            if isinstance(entry, dict) and entry.get("comparison_side") == "b":
                return entry

    b_entries = node_outputs.get("b_images")
    if isinstance(b_entries, list) and b_entries:
        if isinstance(b_entries[0], dict):
            return b_entries[0]

    for entries in node_outputs.values():
        if not isinstance(entries, list):
            continue
        for entry in entries:
            if isinstance(entry, dict) and entry.get("primary"):
                return entry

    img_entries = node_outputs.get("images")
    if isinstance(img_entries, list) and img_entries:
        if isinstance(img_entries[0], dict):
            return img_entries[0]

    for entries in node_outputs.values():
        if not isinstance(entries, list):
            continue
        for entry in entries:
            if isinstance(entry, dict) and entry.get("comparison_side") == "a":
                return entry

    for entries in node_outputs.values():
        if isinstance(entries, list) and entries:
            if isinstance(entries[0], dict):
                return entries[0]

    return None


def select_primary_result_entry(result: dict) -> dict | None:
    """Select the primary result entry from a full result dict.

    Iterates structured outputs first, then falls back to flat images.
    """
    outputs = result.get("outputs", {}) if isinstance(result, dict) else {}
    if isinstance(outputs, dict):
        for node_id in outputs:
            entry = select_primary_output(outputs, node_id)
            if not isinstance(entry, dict):
                continue
            resolved = dict(entry)
            resolved.setdefault("node_id", str(node_id))
            if not resolved.get("output_key"):
                for output_key, entries in outputs.get(node_id, {}).items():
                    if isinstance(entries, list) and entry in entries:
                        resolved["output_key"] = output_key
                        break
            resolved.setdefault("output_key", "images")
            return resolved
    for index, entry in enumerate(result.get("images", []) if isinstance(result, dict) else []):
        if not isinstance(entry, dict):
            continue
        resolved = dict(entry)
        resolved.setdefault("node_id", str(entry.get("node_id", "")))
        resolved.setdefault("output_key", entry.get("output_key") or "images")
        resolved.setdefault("output_index", entry.get("output_index", index))
        return resolved
    return None


# ---------------------------------------------------------------------------
# Conversion failure marker
# ---------------------------------------------------------------------------

class ConversionFailedError(Exception):
    """Raised when format conversion fails for an output item.

    Conversion failure fails the item/batch; it never reports success.
    """


# ---------------------------------------------------------------------------
# Parallel conversion runner (records totals)
# ---------------------------------------------------------------------------

@dataclass
class ConversionBatchResult:
    """Result of converting a batch of output items."""
    items: list[OutputItem] = field(default_factory=list)
    total_raw_bytes: int = 0
    total_base64_bytes: int = 0
    total_json_result_bytes: int = 0
    total_conversion_time_ms: float = 0.0
    converted_count: int = 0
    failed_count: int = 0
    failures: list[dict] = field(default_factory=list)

    @property
    def conversion_total_ms(self) -> float:
        """Compatibility alias for ``total_conversion_time_ms``."""
        return self.total_conversion_time_ms


def convert_output_items(
    items: list[OutputItem],
    output_format: str = "original",
    quality: int = 75,
    webp_lossless_compression: str = "balanced",
    *,
    converter_fn: Callable | None = None,
) -> ConversionBatchResult:
    """Convert a batch of OutputItems, recording per-item ConversionMeta.

    Uses the injected *converter_fn* (defaults to lazy import of
    ``output_converter.convert_image_bytes``).  Conversion failure
    raises ``ConversionFailedError`` — failures never report success.

    Parallel totals are recorded in the returned ``ConversionBatchResult``.
    """
    if converter_fn is None:
        try:
            from output_converter import convert_image_bytes as _conv
        except ImportError:
            raise ConversionFailedError("output_converter not available")
        converter_fn = _conv

    result = ConversionBatchResult()
    for item in items:
        if not item.raw_bytes:
            continue
        try:
            meta_dict = converter_fn(
                item.raw_bytes,
                output_format=output_format,
                quality=quality,
                webp_lossless_compression=webp_lossless_compression,
            )
        except Exception as exc:
            result.failed_count += 1
            result.failures.append({
                "node_id": item.node_id,
                "output_key": item.output_key,
                "filename": item.filename,
                "error": f"{type(exc).__name__}: {exc}",
            })
            raise ConversionFailedError(
                f"conversion failed for {item.node_id}/{item.output_key}: {exc}"
            ) from exc

        error = meta_dict.get("error")
        if error:
            result.failed_count += 1
            result.failures.append({
                "node_id": item.node_id,
                "output_key": item.output_key,
                "filename": item.filename,
                "error": error,
            })
            raise ConversionFailedError(
                f"conversion reported error for {item.node_id}/{item.output_key}: {error}"
            )

        converted_bytes = meta_dict.get("bytes", item.raw_bytes)
        mime_type = meta_dict.get("mime_type", item.mime_type)
        file_ext = meta_dict.get("file_ext", item.file_ext)
        conv_time = float(meta_dict.get("conversion_time_ms", 0) or 0)

        conv_meta = _make_conversion_meta(
            raw_bytes=converted_bytes,
            format=output_format,
            mime_type=mime_type,
            file_ext=file_ext,
            conversion_time_ms=conv_time,
        )

        new_item = OutputItem(
            node_id=item.node_id,
            output_key=item.output_key,
            filename=item.filename,
            path=item.path,
            raw_bytes=converted_bytes,
            base64_data=base64.b64encode(converted_bytes).decode("ascii"),
            mime_type=mime_type,
            file_ext=file_ext,
            width=item.width,
            height=item.height,
            output_index=item.output_index,
            comparison_side=item.comparison_side,
            format=output_format,
            animated=item.animated,
            conversion_meta=conv_meta,
        )
        result.items.append(new_item)
        result.converted_count += 1
        result.total_raw_bytes += conv_meta.raw_bytes
        result.total_base64_bytes += conv_meta.base64_bytes
        result.total_json_result_bytes += conv_meta.json_result_bytes
        result.total_conversion_time_ms += conv_meta.conversion_time_ms

    return result


# ---------------------------------------------------------------------------
# Legacy payload adapter
# ---------------------------------------------------------------------------

def adapt_legacy_result_payload(
    raw_payload: Mapping[str, Any],
) -> dict:
    """Adapt a legacy Modal result payload to the standardised result format.

    Legacy payloads from earlier Modal versions may have:
    - ``result`` key wrapping the actual outputs
    - Missing ``outputs`` structure
    - Flat ``images`` list with inline base64 ``data``

    Returns a normalised dict with ``outputs`` and optionally ``images``.
    """
    payload = dict(raw_payload)

    # Unwrap legacy result wrapper
    if "result" in payload and isinstance(payload["result"], dict):
        inner = payload["result"]
        # Merge inner keys upward, keeping outer keys that don't collide
        for k, v in inner.items():
            if k not in payload:
                payload[k] = v

    # Ensure outputs key exists (may be wrapped deeper)
    if "outputs" not in payload:
        # Try common legacy nesting patterns
        for candidate in ("output", "data", "images_data"):
            if candidate in payload and isinstance(payload[candidate], dict):
                payload["outputs"] = payload[candidate]
                break
        else:
            payload["outputs"] = {}

    return payload


# ---------------------------------------------------------------------------
# Materialization function (no ComfyUI imports at module load)
# ---------------------------------------------------------------------------

def materialize_modal_result(
    result: dict,
    *,
    output_dir: str,
    prompt_id: str,
    client_id: str = "",
    send_event: Callable | None = None,
    auto_save_local: bool = False,
    save_folder: str = "",
    save_metadata_sidecar: bool = True,
    workflow_hash: str = "",
    workflow_name: str = "",
    seed: str = "0",
    width: int = 0,
    height: int = 0,
    comfyui_root: str = "",
    save_output_image_fn: Callable | None = None,
    converter_fn: Callable | None = None,
    output_format: str = "original",
) -> dict:
    """Materialise a Modal result dict to the local filesystem.

    Accepts the current Modal result dictionary format (which may
    contain base64-encoded ``data`` fields).  Writes decoded files
    to ``output_dir``, emits ``executed`` events via ``send_event``,
    and optionally auto-saves the primary output.

    This function does **not** import ComfyUI at module load time —
    ComfyUI dependencies are injected (``save_output_image_fn``,
    ``converter_fn``) or lazily imported.
    """
    native_outputs: dict[str, dict] = {}
    materialized_outputs: dict[str, dict] = {}
    written_files: list[str] = []
    save_results: list[dict] = []
    save_warnings: list[str] = []
    handled_output_ids: set[tuple[str, str, str, int]] = set()
    image_count = 0
    video_count = 0
    output_bytes_written = 0

    if send_event is None:
        send_event = lambda _event, _payload: None

    # Adapt legacy payload
    adapted = adapt_legacy_result_payload(result)

    def _store_entry(
        node_id: str,
        output_key: str,
        entry: dict,
        fallback_index: int = 0,
    ) -> None:
        nonlocal image_count, video_count, output_bytes_written
        raw_bytes = base64.b64decode(entry["data"])
        local_filename = entry.get("filename", f"output_{fallback_index}.bin")
        local_path = unique_path(output_dir, local_filename)
        local_filename = os.path.basename(local_path)
        Path(local_path).write_bytes(raw_bytes)
        written_files.append(local_path)
        output_bytes_written += len(raw_bytes)

        is_video = output_key == "gifs" or (entry.get("format", "") in {"gif", "mp4", "webm"})
        if is_video:
            video_count += 1
        else:
            image_count += 1

        native_entry = build_native_output_descriptor(local_filename)
        internal_entry = build_materialized_output_entry(
            entry,
            node_id=str(node_id),
            output_key=output_key,
            local_filename=local_filename,
            local_path=local_path,
            decoded_bytes=raw_bytes,
            fallback_index=fallback_index,
        )

        native_outputs.setdefault(str(node_id), {}).setdefault(output_key, []).append(native_entry)
        materialized_outputs.setdefault(str(node_id), {}).setdefault(output_key, []).append(internal_entry)

        if is_video:
            native_outputs[str(node_id)]["animated"] = [True] * len(native_outputs[str(node_id)][output_key])
            materialized_outputs[str(node_id)]["animated"] = [True] * len(materialized_outputs[str(node_id)][output_key])

        handled_output_ids.add(stable_output_identity(str(node_id), output_key, entry, fallback_index))

    # Process structured outputs
    structured_outputs = adapted.get("outputs", {})
    for node_id, node_outputs in structured_outputs.items():
        if not isinstance(node_outputs, dict):
            continue
        for output_key, entries in node_outputs.items():
            if not isinstance(entries, list):
                continue
            for index, entry in enumerate(entries):
                if isinstance(entry, dict) and "data" in entry:
                    _store_entry(str(node_id), str(output_key), entry, index)

    # Process flat images
    for index, img in enumerate(adapted.get("images", [])):
        if not isinstance(img, dict) or "data" not in img:
            continue
        node_id = str(img.get("node_id", ""))
        output_key = str(img.get("output_key") or "images")
        if stable_output_identity(node_id, output_key, img, index) in handled_output_ids:
            continue
        _store_entry(node_id, output_key, img, index)

    # Process flat videos
    for index, vid in enumerate(adapted.get("videos", [])):
        if not isinstance(vid, dict) or "data" not in vid:
            continue
        node_id = str(vid.get("node_id", ""))
        output_key = str(vid.get("output_key") or "gifs")
        if stable_output_identity(node_id, output_key, vid, index) in handled_output_ids:
            continue
        _store_entry(node_id, output_key, vid, index)

    # Build history outputs (alias b_images -> images for standard consumers)
    history_outputs: dict[str, dict] = {}
    for nid, noutputs in native_outputs.items():
        history_outputs[nid] = dict(noutputs)
    for nid, noutputs in native_outputs.items():
        if "images" not in noutputs and "b_images" in noutputs:
            history_outputs[nid]["images"] = list(noutputs["b_images"])

    # Emit executed events
    for node_id, event_output in native_outputs.items():
        send_event("executed", {
            "node": node_id,
            "display_node": node_id,
            "prompt_id": prompt_id,
            "output": event_output,
        })

    # Determine primary output
    primary_output = None
    primary_entry = select_primary_result_entry({"outputs": materialized_outputs, "images": []})
    if isinstance(primary_entry, dict):
        primary_output = {
            "node_id": str(primary_entry.get("node_id", "")),
            "output_key": str(primary_entry.get("output_key", "images")),
            "comparison_side": primary_entry.get("comparison_side", ""),
            "filename": primary_entry.get("filename", ""),
            "path": primary_entry.get("path", ""),
            "mime_type": primary_entry.get("mime_type", ""),
            "file_ext": primary_entry.get("file_ext", ""),
            "output_index": primary_entry.get("output_index", 0),
            "byte_count": primary_entry.get("byte_count", 0),
        }

    # Auto-save primary output
    if auto_save_local and primary_output and primary_output.get("path"):
        try:
            image_bytes = Path(primary_output["path"]).read_bytes()

            if save_output_image_fn is None:
                try:
                    from output_saver import save_output_image as _save_output_image
                except ImportError:
                    _save_output_image = None
                save_output_image_fn = _save_output_image

            if save_output_image_fn is not None:
                save_result = save_output_image_fn(
                    image_bytes,
                    output_format=output_format,
                    file_ext=primary_output.get("file_ext") or ".png",
                    mime_type=primary_output.get("mime_type") or "image/png",
                    quality=None,
                    webp_lossless_compression=None,
                    original_size_bytes=len(image_bytes),
                    conversion_time_ms=0,
                    save_folder=save_folder,
                    save_metadata_sidecar=save_metadata_sidecar,
                    workflow_hash=workflow_hash,
                    workflow_name=workflow_name,
                    seed=str(seed or "0"),
                    width=width,
                    height=height,
                    index=0,
                    comfyui_root=comfyui_root,
                    extra_meta={
                        "node_id": primary_output.get("node_id", ""),
                        "output_key": primary_output.get("output_key", ""),
                        "comparison_side": primary_output.get("comparison_side", ""),
                        "source_filename": primary_output.get("filename", ""),
                    },
                )
                save_results.append(save_result)
                if save_result.get("error"):
                    save_warnings.append(save_result["error"])
        except OSError as exc:
            save_warnings.append(str(exc))

    return {
        "outputs": native_outputs,
        "history_outputs": history_outputs,
        "materialized_outputs": materialized_outputs,
        "primary_output": primary_output,
        "written_files": written_files,
        "image_count": image_count,
        "video_count": video_count,
        "bytes_written": output_bytes_written,
        "save_results": save_results,
        "save_warnings": save_warnings,
    }


# ---------------------------------------------------------------------------
# Thumbnail helper
# ---------------------------------------------------------------------------

def make_thumbnail(input_path: str, output_path: str, max_size: int = 256) -> bool:
    """Generate a WebP thumbnail. Returns True on success.

    Uses Pillow if available; falls back to copying the original.
    """
    try:
        from PIL import Image
        img = Image.open(input_path)
        img.thumbnail((max_size, max_size))
        img.save(output_path, "WEBP", quality=75)
        return True
    except Exception:
        try:
            import shutil
            shutil.copy2(input_path, output_path)
            return True
        except Exception:
            return False
