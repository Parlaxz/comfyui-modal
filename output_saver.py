"""
Local auto-save for comfyui-modal.

After the local bridge receives completed image bytes from Modal,
this module handles saving them to user-configured directories
with optional metadata JSON sidecars.
"""

import json
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path


# ── Safe defaults ────────────────────────────────────────────────────
DEFAULTS = {
    "auto_save_local": False,
    "save_folder": "",
    "save_metadata_sidecar": True,
}

# Default save folder relative to ComfyUI root
_DEFAULT_SAVE_SUBDIR = os.path.join("output", "modal")


def _normalize_save_folder(save_folder: str) -> str:
    normalized = (save_folder or "").replace("\\", "/").strip()
    normalized = normalized.lstrip("./").rstrip("/")
    if normalized.lower().startswith("comfyui/"):
        normalized = normalized[len("comfyui/"):]
    return normalized


def _resolve_save_folder(save_folder: str, comfyui_root: str) -> str:
    """Resolve the save folder, falling back to ComfyUI/output/modal/."""
    if save_folder and os.path.isabs(save_folder):
        return save_folder
    normalized = _normalize_save_folder(save_folder)
    if normalized:
        candidate = os.path.join(comfyui_root, *normalized.split("/"))
    else:
        candidate = os.path.join(comfyui_root, _DEFAULT_SAVE_SUBDIR)
    return candidate


def _ensure_dir(path: str) -> bool:
    """Create directory if it doesn't exist. Returns True on success."""
    try:
        os.makedirs(path, exist_ok=True)
        return True
    except OSError:
        return False


def _sanitize(text: str) -> str:
    """Replace unsafe path characters."""
    return re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", (text or "untitled")).strip() or "untitled"


def _unique_filename(directory: str, filename: str) -> str:
    """Return a unique path in *directory* by appending _1, _2, etc. if needed."""
    base = os.path.join(directory, filename)
    if not os.path.exists(base):
        return base
    stem, ext = os.path.splitext(filename)
    counter = 1
    while True:
        candidate = os.path.join(directory, f"{stem}_{counter}{ext}")
        if not os.path.exists(candidate):
            return candidate
        counter += 1


def _build_filename(
    *,
    timestamp: float,
    workflow_hash: str,
    seed: str,
    index: int,
    file_ext: str,
    workflow_name: str = "",
) -> str:
    """Build a sanitized output filename.

    Format: ``{ISO_date}_{workflow_name}_seed-{seed}_{index}.{ext}``
    """
    name = _sanitize(workflow_name or workflow_hash[:12])
    seed_str = _sanitize(str(seed or "0"))
    dt = datetime.fromtimestamp(timestamp, tz=timezone.utc)
    date_str = dt.strftime("%Y-%m-%d_%H%M%S")
    ext = file_ext if file_ext.startswith(".") else f".{file_ext}"
    return f"{date_str}_{name}_seed-{seed_str}_{index}{ext}"


def _build_metadata_sidecar(
    *,
    created_at: str,
    workflow_hash: str,
    workflow_name: str,
    seed: str,
    width: int,
    height: int,
    output_format: str,
    mime_type: str,
    file_ext: str,
    quality: int | None,
    webp_lossless_compression: str | None,
    image_path: str,
    image_size_bytes: int,
    original_png_size_bytes_before_conversion: int,
    conversion_time_ms: float,
    saved_local: bool = True,
    **extra,
) -> dict:
    return {
        "created_at": created_at,
        "workflow_hash": workflow_hash,
        "workflow_name": workflow_name or "",
        "seed": str(seed),
        "width": width,
        "height": height,
        "output_format": output_format,
        "mime_type": mime_type,
        "file_ext": file_ext,
        "quality": quality,
        "webp_lossless_compression": webp_lossless_compression,
        "image_path": image_path,
        "image_size_bytes": image_size_bytes,
        "original_png_size_bytes_before_conversion": original_png_size_bytes_before_conversion,
        "conversion_time_ms": conversion_time_ms,
        "saved_local": saved_local,
    }


def save_output_image(
    image_bytes: bytes,
    *,
    output_format: str = "original",
    file_ext: str = ".png",
    mime_type: str = "image/png",
    quality: int | None = None,
    webp_lossless_compression: str | None = None,
    original_size_bytes: int = 0,
    conversion_time_ms: float = 0,
    save_folder: str = "",
    save_metadata_sidecar: bool = True,
    workflow_hash: str = "",
    workflow_name: str = "",
    seed: str = "",
    width: int = 0,
    height: int = 0,
    index: int = 0,
    comfyui_root: str = "",
    extra_meta: dict | None = None,
) -> dict:
    """Save an output image to the local auto-save folder.

    Returns a dict with ``"saved"``, ``"path"``, ``"metadata_path"``,
    and ``"error"`` fields.
    """
    result: dict = {
        "saved": False,
        "path": "",
        "metadata_path": "",
        "error": None,
    }

    try:
        resolved = _resolve_save_folder(save_folder, comfyui_root)
        images_dir = os.path.join(resolved, "images")
        metadata_dir = os.path.join(resolved, "metadata")

        if not _ensure_dir(images_dir):
            result["error"] = f"cannot create directory: {images_dir}"
            return result

        timestamp = time.time()
        filename = _build_filename(
            timestamp=timestamp,
            workflow_hash=workflow_hash,
            seed=str(seed or "0"),
            index=index,
            file_ext=file_ext.lstrip("."),
            workflow_name=workflow_name,
        )
        image_path = _unique_filename(images_dir, filename)

        with open(image_path, "wb") as f:
            f.write(image_bytes)

        result["saved"] = True
        result["path"] = image_path

        if save_metadata_sidecar:
            if not _ensure_dir(metadata_dir):
                print(f"[output_saver] cannot create metadata dir: {metadata_dir}")
            else:
                created_at = datetime.fromtimestamp(
                    timestamp, tz=timezone.utc
                ).isoformat()

                meta = _build_metadata_sidecar(
                    created_at=created_at,
                    workflow_hash=workflow_hash,
                    workflow_name=workflow_name,
                    seed=str(seed or "0"),
                    width=width,
                    height=height,
                    output_format=output_format,
                    mime_type=mime_type,
                    file_ext=file_ext,
                    quality=quality,
                    webp_lossless_compression=webp_lossless_compression,
                    image_path=image_path,
                    image_size_bytes=len(image_bytes),
                    original_png_size_bytes_before_conversion=original_size_bytes,
                    conversion_time_ms=conversion_time_ms,
                    saved_local=True,
                )
                if extra_meta:
                    meta.update(extra_meta)

                meta_filename = _build_filename(
                    timestamp=timestamp,
                    workflow_hash=workflow_hash,
                    seed=str(seed or "0"),
                    index=index,
                    file_ext="json",
                    workflow_name=workflow_name,
                )
                meta_path = _unique_filename(metadata_dir, meta_filename)

                with open(meta_path, "w", encoding="utf-8") as f:
                    json.dump(meta, f, indent=2, default=str)

                result["metadata_path"] = meta_path

    except Exception as exc:
        result["error"] = str(exc)

    if result.get("error"):
        print(f"[output_saver] SAVE ERROR: {result['error']}")

    return result
