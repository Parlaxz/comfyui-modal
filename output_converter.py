"""
Output format conversion for comfyui-modal.

Converts ComfyUI-generated PNG images to WebP (lossless/lossy) or JPEG
after generation, without modifying the workflow graph.  This module
runs on the Modal side before the image bytes are returned to the
local bridge.
"""

import io
import time
from pathlib import Path

try:
    from PIL import Image
except ImportError:
    Image = None

# ── Public enum values (must match frontend) ──────────────────────────
OUTPUT_FORMATS = ("original", "webp_lossless", "webp_lossy", "jpeg")
WEBP_LOSSLESS_COMPRESSION = ("fast", "balanced", "max")

# ── Quality defaults ──────────────────────────────────────────────────
DEFAULT_QUALITY = 75

# WebP lossless method mapping (method 0-6, higher = slower + smaller)
_WEBP_LOSSLESS_METHOD = {
    "fast": 0,
    "balanced": 4,
    "max": 6,
}

# WebP lossy method
_WEBP_LOSSY_METHOD = 4

# ── Extension / MIME mapping ──────────────────────────────────────────
_FORMAT_META = {
    "original":       {"ext": ".png",  "mime": "image/png"},
    "webp_lossless":  {"ext": ".webp", "mime": "image/webp"},
    "webp_lossy":     {"ext": ".webp", "mime": "image/webp"},
    "jpeg":           {"ext": ".jpg",  "mime": "image/jpeg"},
}

DEFAULTS = {
    "output_format":              "original",
    "quality":                    75,
    "webp_lossless_compression":  "balanced",
}


def _has_alpha(img: "Image.Image") -> bool:
    """Return True if the PIL image has an alpha channel."""
    return img.mode in ("RGBA", "LA", "PA") or (
        img.mode == "P" and "transparency" in img.info
    )


def _coerce_rgb(img: "Image.Image") -> "Image.Image":
    """Composite RGBA/LA/PA images onto white background, return RGB."""
    if img.mode == "RGBA":
        background = Image.new("RGB", img.size, (255, 255, 255))
        background.paste(img, mask=img.split()[3])
        return background
    if img.mode == "LA":
        background = Image.new("L", img.size, 255)
        background.paste(img, mask=img.split()[1])
        return background.convert("RGB")
    if img.mode == "P":
        if "transparency" in img.info:
            img = img.convert("RGBA")
        else:
            return img.convert("RGB")
    # Re-check after conversion
    if img.mode == "RGBA":
        background = Image.new("RGB", img.size, (255, 255, 255))
        background.paste(img, mask=img.split()[3])
        return background
    if img.mode == "LA":
        background = Image.new("L", img.size, 255)
        background.paste(img, mask=img.split()[1])
        return background.convert("RGB")
    return img.convert("RGB")


def _sanitize_filename(name: str) -> str:
    """Replace unsafe filename characters with underscores."""
    import re
    sanitized = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name)
    return sanitized.strip() or "output"


def convert_image_bytes(
    input_bytes: bytes,
    output_format: str = "original",
    quality: int = 75,
    webp_lossless_compression: str = "balanced",
) -> dict:
    """Convert raw PNG bytes to the requested output format.

    Args:
        input_bytes: Raw image bytes (expected to be PNG).
        output_format: One of ``"original"``, ``"webp_lossless"``,
                       ``"webp_lossy"``, ``"jpeg"``.
        quality: Quality 0–100 (used for WebP lossy and JPEG).
        webp_lossless_compression: ``"fast"``, ``"balanced"``, or ``"max"``
                                   (only for ``webp_lossless``).

    Returns a dict::

        {
            "bytes": <converted bytes>,
            "mime_type": "image/webp",
            "file_ext": ".webp",
            "output_format": "webp_lossless",
            "original_size_bytes": 3145728,
            "returned_size_bytes": 850000,
            "conversion_time_ms": 42,
            "quality": 75,
            "webp_lossless_compression": "balanced",
            "fallback": False,
            "error": None,
        }
    """
    t0 = time.time()
    meta = {
        "bytes": input_bytes,
        "mime_type": "image/png",
        "file_ext": ".png",
        "output_format": output_format,
        "original_size_bytes": len(input_bytes),
        "returned_size_bytes": len(input_bytes),
        "conversion_time_ms": 0,
        "quality": None,
        "webp_lossless_compression": None,
        "fallback": False,
        "error": None,
    }

    # ── Clamp / validate inputs ──────────────────────────────────────
    if output_format not in OUTPUT_FORMATS:
        meta["error"] = f"unknown output_format: {output_format!r}"
        meta["output_format"] = "original"
        output_format = "original"

    if not isinstance(quality, (int, float)):
        quality = 75
    quality = max(0, min(100, int(quality)))

    if webp_lossless_compression not in WEBP_LOSSLESS_COMPRESSION:
        webp_lossless_compression = "balanced"

    fmt_ext = _FORMAT_META.get(output_format, _FORMAT_META["original"])
    meta["mime_type"] = fmt_ext["mime"]
    meta["file_ext"] = fmt_ext["ext"]

    # ── Original / no-op ─────────────────────────────────────────────
    if output_format == "original":
        meta["conversion_time_ms"] = round((time.time() - t0) * 1000, 1)
        return meta

    if Image is None:
        meta["error"] = "Pillow not available; returning original PNG"
        meta["fallback"] = True
        meta["conversion_time_ms"] = round((time.time() - t0) * 1000, 1)
        return meta

    try:
        img = Image.open(io.BytesIO(input_bytes))
    except Exception as exc:
        meta["error"] = f"failed to open image: {exc}"
        meta["fallback"] = True
        meta["conversion_time_ms"] = round((time.time() - t0) * 1000, 1)
        return meta

    width, height = img.size
    out_buf = io.BytesIO()

    try:
        if output_format == "webp_lossless":
            meta["quality"] = None
            meta["webp_lossless_compression"] = webp_lossless_compression
            method = _WEBP_LOSSLESS_METHOD.get(
                webp_lossless_compression, 4
            )
            img.save(
                out_buf,
                format="WEBP",
                lossless=True,
                method=method,
            )

        elif output_format == "webp_lossy":
            meta["quality"] = quality
            meta["webp_lossless_compression"] = None
            img.save(
                out_buf,
                format="WEBP",
                lossless=False,
                quality=quality,
                method=_WEBP_LOSSY_METHOD,
            )

        elif output_format == "jpeg":
            meta["quality"] = quality
            meta["webp_lossless_compression"] = None
            if img.mode in ("RGBA", "LA", "PA", "P"):
                img = _coerce_rgb(img)
            elif img.mode != "RGB":
                img = img.convert("RGB")
            img.save(out_buf, format="JPEG", quality=quality)

        out_buf.seek(0)
        meta["bytes"] = out_buf.read()
        meta["returned_size_bytes"] = len(meta["bytes"])

    except Exception as exc:
        meta["error"] = f"conversion failed: {exc}"
        meta["fallback"] = True
        meta["bytes"] = input_bytes
        meta["returned_size_bytes"] = len(input_bytes)
        meta["file_ext"] = ".png"
        meta["mime_type"] = "image/png"

    meta["conversion_time_ms"] = round((time.time() - t0) * 1000, 1)

    if meta.get("fallback"):
        print(
            f"[output_converter] FALLBACK to PNG: fmt={output_format} "
            f"err={meta['error']}"
        )

    return meta


def change_extension(filename: str, new_ext: str) -> str:
    """Replace the file extension of *filename* with *new_ext*.

    >>> change_extension("ComfyUI_00001_.png", ".webp")
    'ComfyUI_00001_.webp'
    """
    p = Path(filename)
    return p.stem + new_ext
