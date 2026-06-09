import contextlib
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path

import modal

from api_prompt_validator import assert_valid_api_prompt_structure
from gpu_catalog import GPU_CATALOG, get_supported_gpus, is_gpu_hidden
from timing_trace import Trace, coerce_t0_from_browser
from failure_summary import FailureSummary

# ── Inline output-converter constants & helpers (self-contained for Modal) ──
_OUTPUT_FORMATS = ("original", "webp_lossless", "webp_lossy", "jpeg")
_WEBP_LOSSLESS_COMPRESSION = ("fast", "balanced", "max")
_WEBP_LOSSLESS_METHOD = {"fast": 0, "balanced": 4, "max": 6}
_WEBP_LOSSY_METHOD = 4
_FORMAT_META = {
    "original":       {"ext": ".png",  "mime": "image/png"},
    "webp_lossless":  {"ext": ".webp", "mime": "image/webp"},
    "webp_lossy":     {"ext": ".webp", "mime": "image/webp"},
    "jpeg":           {"ext": ".jpg",  "mime": "image/jpeg"},
}
_CONVERTER_DEFAULTS = {
    "output_format":              "original",
    "quality":                    75,
    "webp_lossless_compression":  "balanced",
}


def _change_extension(filename: str, new_ext: str) -> str:
    """Replace the file extension of *filename* with *new_ext*."""
    import os as _os
    stem, _ = _os.path.splitext(filename)
    return stem + new_ext


def _convert_image_bytes(
    input_bytes: bytes,
    output_format: str = "original",
    quality: int = 75,
    webp_lossless_compression: str = "balanced",
) -> dict:
    """Convert raw PNG bytes to target format.  Returns metadata dict."""
    import io as _io
    import time as _time

    _t0 = _time.time()
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

    if output_format not in _OUTPUT_FORMATS:
        meta["error"] = f"unknown output_format: {output_format!r}"
        meta["output_format"] = "original"
        output_format = "original"
    if not isinstance(quality, (int, float)):
        quality = 75
    quality = max(0, min(100, int(quality)))
    if webp_lossless_compression not in _WEBP_LOSSLESS_COMPRESSION:
        webp_lossless_compression = "balanced"

    fmt_ext = _FORMAT_META.get(output_format, _FORMAT_META["original"])
    meta["mime_type"] = fmt_ext["mime"]
    meta["file_ext"] = fmt_ext["ext"]

    if output_format == "original":
        meta["conversion_time_ms"] = round((_time.time() - _t0) * 1000, 1)
        return meta

    try:
        from PIL import Image as _PillowImage
    except ImportError:
        meta["error"] = "Pillow not available; returning original PNG"
        meta["fallback"] = True
        meta["conversion_time_ms"] = round((_time.time() - _t0) * 1000, 1)
        return meta

    try:
        img = _PillowImage.open(_io.BytesIO(input_bytes))
    except Exception as exc:
        meta["error"] = f"failed to open image: {exc}"
        meta["fallback"] = True
        meta["conversion_time_ms"] = round((_time.time() - _t0) * 1000, 1)
        return meta

    out_buf = _io.BytesIO()
    try:
        if output_format == "webp_lossless":
            meta["quality"] = None
            meta["webp_lossless_compression"] = webp_lossless_compression
            method = _WEBP_LOSSLESS_METHOD.get(webp_lossless_compression, 4)
            img.save(out_buf, format="WEBP", lossless=True, method=method)
        elif output_format == "webp_lossy":
            meta["quality"] = quality
            meta["webp_lossless_compression"] = None
            img.save(out_buf, format="WEBP", lossless=False, quality=quality, method=_WEBP_LOSSY_METHOD)
        elif output_format == "jpeg":
            meta["quality"] = quality
            meta["webp_lossless_compression"] = None
            # Composite alpha onto white background
            if img.mode in ("RGBA", "LA", "PA"):
                if img.mode == "RGBA":
                    bg = _PillowImage.new("RGB", img.size, (255, 255, 255))
                    bg.paste(img, mask=img.split()[3])
                    img = bg
                elif img.mode == "LA":
                    bg = _PillowImage.new("L", img.size, 255)
                    bg.paste(img, mask=img.split()[1])
                    img = bg.convert("RGB")
                elif img.mode == "PA":
                    img = img.convert("RGBA")
                    bg = _PillowImage.new("RGB", img.size, (255, 255, 255))
                    bg.paste(img, mask=img.split()[3])
                    img = bg
            elif img.mode == "P":
                if "transparency" in img.info:
                    img = img.convert("RGBA")
                    bg = _PillowImage.new("RGB", img.size, (255, 255, 255))
                    bg.paste(img, mask=img.split()[3])
                    img = bg
                else:
                    img = img.convert("RGB")
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

    meta["conversion_time_ms"] = round((_time.time() - _t0) * 1000, 1)
    if meta.get("fallback"):
        print(f"[comfyapp.convert] FALLBACK to PNG: fmt={output_format} err={meta['error']}")
    return meta

# ── PART 12: Silent exception logging helper ──
_SILENT_EXCEPTION_DEBUG = os.getenv("COMFYMODAL_SILENT_EXCEPTION_DEBUG", "0") == "1"


def _log_silent_exception(context: str, exc: Exception, detail: str = "") -> None:
    """Log an exception that would otherwise be silently swallowed.

    Only emits logs when PROFILING_ENABLED or _SILENT_EXCEPTION_DEBUG is set,
    to avoid log spam in the hot path.  Use this for expected optional failures
    where the ``pass`` is intentional but the detail is useful for debugging.
    """
    if PROFILING_ENABLED or _SILENT_EXCEPTION_DEBUG:
        detail_str = f" {detail}" if detail else ""
        print(f"[comfyapp.silent] context={context} error={exc}{detail_str}")


PROFILING_ENABLED = os.getenv("COMFYMODAL_PROFILING", "0") == "1"
DEFAULT_EXECUTION_BACKEND = os.getenv("COMFYMODAL_EXECUTION_BACKEND", "in_process")
ENABLE_WARMUP = os.getenv("COMFYMODAL_ENABLE_WARMUP", "1") == "1"
ENABLE_TORCH_COMPILE = os.getenv("COMFYMODAL_ENABLE_TORCH_COMPILE", "0") == "1"
ENABLE_GPU_SNAPSHOT = os.getenv("COMFYMODAL_ENABLE_GPU_SNAPSHOT", "0") == "1"
CUSTOM_NODE_REQUIREMENTS_TIMEOUT_S = int(os.getenv("COMFYMODAL_CUSTOM_NODE_REQUIREMENTS_TIMEOUT_S", "180"))
CUSTOM_NODE_COPY_MODE = os.getenv("COMFYMODAL_CUSTOM_NODE_COPY_MODE", "combined").strip().lower()
if CUSTOM_NODE_COPY_MODE not in ("combined", "per_node"):
    print(f"[comfyapp] WARNING: invalid COMFYMODAL_CUSTOM_NODE_COPY_MODE={CUSTOM_NODE_COPY_MODE!r}, falling back to 'combined'")
    CUSTOM_NODE_COPY_MODE = "combined"

# Generic collector for custom-node import/entrypoint failures during startup.
# Populated by the logging.warning patch in _start_in_process_backend.
# Each record is a dict with keys: phase, custom_node_name, custom_node_path,
# entrypoint_name, exception_type, exception_message, traceback, timestamp.
_CUSTOM_NODE_IMPORT_FAILURES: list[dict] = []

# Module paths of custom nodes whose entrypoint/schema failed during CPU snapshot.
# Retried after GPU warmup so schema generation has real device availability.
_CUSTOM_NODE_REGISTRATION_PENDING_RETRY: set[str] = set()

# ── PART 2: Custom-node retry registry ──
class CustomNodeRetryEntry:
    __slots__ = (
        "path", "first_seen_at", "retry_count", "last_retry_at",
        "last_status", "last_exception_type", "last_exception_message",
        "last_traceback", "registered_delta", "retryable_reason", "resolved",
    )

    def __init__(self, path: str):
        self.path = path
        self.first_seen_at = time.time()
        self.retry_count = 0
        self.last_retry_at = 0.0
        self.last_status = "pending"
        self.last_exception_type = ""
        self.last_exception_message = ""
        self.last_traceback = ""
        self.registered_delta = 0.0
        self.retryable_reason = ""
        self.resolved = False

    def record_failure(self, exc_type: str, exc_msg: str, tb: str) -> None:
        self.last_status = "failed"
        self.last_exception_type = exc_type
        self.last_exception_message = exc_msg
        self.last_traceback = tb

    def record_retry(self) -> None:
        self.retry_count += 1
        self.last_retry_at = time.time()
        self.last_status = "retrying"

    def mark_resolved(self) -> None:
        self.resolved = True
        self.last_status = "succeeded"

    def to_dict(self) -> dict:
        return {
            "path": self.path,
            "first_seen_at": self.first_seen_at,
            "retry_count": self.retry_count,
            "last_retry_at": self.last_retry_at,
            "last_status": self.last_status,
            "last_exception_type": self.last_exception_type,
            "last_exception_message": self.last_exception_message[:500] if self.last_exception_message else "",
            "last_traceback_available": bool(self.last_traceback),
            "registered_delta": self.registered_delta,
            "retryable_reason": self.retryable_reason,
            "resolved": self.resolved,
        }


class CustomNodeRetryRegistry:
    MAX_RETRIES = 2

    def __init__(self):
        self._entries: dict[str, CustomNodeRetryEntry] = {}

    def register_failure(self, path: str, exc_type: str = "", exc_msg: str = "", tb: str = "",
                         retryable_reason: str = "") -> None:
        if path not in self._entries:
            self._entries[path] = CustomNodeRetryEntry(path)
        entry = self._entries[path]
        entry.record_failure(exc_type, exc_msg, tb)
        if retryable_reason:
            entry.retryable_reason = retryable_reason

    def should_retry(self, path: str) -> bool:
        entry = self._entries.get(path)
        if entry is None:
            return False
        if entry.resolved:
            return False
        if entry.last_status == "succeeded":
            return False
        if entry.retry_count >= self.MAX_RETRIES:
            return False
        if entry.last_exception_type == "ModuleNotFoundError" and not entry.retryable_reason:
            return False
        return True

    def record_retry(self, path: str) -> None:
        entry = self._entries.get(path)
        if entry is not None:
            entry.record_retry()

    def mark_resolved(self, path: str) -> None:
        entry = self._entries.get(path)
        if entry is not None:
            entry.mark_resolved()

    def get_entry(self, path: str) -> CustomNodeRetryEntry | None:
        return self._entries.get(path)

    def get_pending_paths(self) -> list[str]:
        return [p for p, e in self._entries.items() if e.last_status == "pending" and not e.resolved]

    def get_failed_paths(self) -> list[dict]:
        return [e.to_dict() for e in self._entries.values() if e.last_status == "failed" and not e.resolved]

    def get_all(self) -> list[dict]:
        return [e.to_dict() for e in self._entries.values()]

    def clear_resolved(self) -> None:
        self._entries = {p: e for p, e in self._entries.items() if not e.resolved}


_CUSTOM_NODE_RETRY_REGISTRY = CustomNodeRetryRegistry()

# ── PART 3: Preload guardrails ──
# Controls whether unknown (never-seen-before) workflow profiles get
# expensive CPU preload.  Set to 1 to always preload regardless.
PRELOAD_UNKNOWN_PROFILES = os.getenv("COMFYMODAL_PRELOAD_UNKNOWN_PROFILES", "0") == "1"
# Maximum total preload size in GB across all files.
PRELOAD_MAX_TOTAL_GB = float(os.getenv("COMFYMODAL_PRELOAD_MAX_TOTAL_GB", "12"))
# Maximum single-file preload size in GB.
PRELOAD_MAX_FILE_GB = float(os.getenv("COMFYMODAL_PRELOAD_MAX_FILE_GB", "10"))
# Minimum observed throughput (GB/s) to continue preloading.
# If measured throughput stays below this after the outlier_abort window,
# preloading is cancelled and falls back to lazy loading.
PRELOAD_MIN_THROUGHPUT_GBPS = float(os.getenv("COMFYMODAL_PRELOAD_MIN_THROUGHPUT_GBPS", "0.5"))
# After this many seconds of preload, evaluate throughput and abort if below threshold.
PRELOAD_OUTLIER_ABORT_SECONDS = float(os.getenv("COMFYMODAL_PRELOAD_OUTLIER_ABORT_SECONDS", "10"))

# ── PART 4: Custom-node requirements repair mode ──
#   off        - Never install requirements during prompt execution.
#   fail_fast  - If requirements hash is missing/stale, fail with
#                actionable error before model preload.
#   dev        - Allow runtime repair for development.
REQUIREMENTS_REPAIR_MODE = os.getenv("COMFYMODAL_REQUIREMENTS_REPAIR_MODE", "fail_fast").strip().lower()
# When fail_fast is active, this message is included in the error.
_FAIL_FAST_REQ_MSG = (
    "Custom node requirements are not prepared for this image. "
    "Missing/stale requirements detected. "
    "Run the custom-node sync/build step before inference, "
    "or set COMFYMODAL_REQUIREMENTS_REPAIR_MODE=dev for runtime install."
)

# ── PART 7: Remote background deploy gating ──
ENABLE_REMOTE_BACKGROUND_DEPLOY = os.getenv("COMFYMODAL_ENABLE_REMOTE_BACKGROUND_DEPLOY", "0") == "1"
WARMUP_PROFILE = os.getenv("COMFYMODAL_WARMUP_PROFILE", "off")
WARMUP_CHECKPOINT = os.getenv("COMFYMODAL_WARMUP_CHECKPOINT", "").strip()
WARMUP_UNET = os.getenv("COMFYMODAL_WARMUP_UNET", "").strip()
WARMUP_CLIP1 = os.getenv("COMFYMODAL_WARMUP_CLIP1", "").strip()
WARMUP_CLIP2 = os.getenv("COMFYMODAL_WARMUP_CLIP2", "").strip()
WARMUP_VAE = os.getenv("COMFYMODAL_WARMUP_VAE", "").strip()
WARMUP_CLIP_TYPE = os.getenv("COMFYMODAL_WARMUP_CLIP_TYPE", "flux").strip() or "flux"
WARMUP_TEXT = os.getenv("COMFYMODAL_WARMUP_TEXT", "warmup")

# Comma-separated custom-node names to ignore in baked vs. volume node-set mismatch validation.
# Default empty — all node set mismatches are reported.
_CUSTOM_NODE_SET_MISMATCH_IGNORE_ENV = os.getenv("COMFYMODAL_CUSTOM_NODE_SET_MISMATCH_IGNORE", "")

# Preload mode controls which model files are loaded to CPU during restore
# and how loading behaves:
#   workers_2      — (default fallback) UNET + CLIP concurrent, 2 workers
#   default        — UNET + CLIP concurrent, 4 workers
#   sequential     — UNET first then CLIP, 1 worker
#   workers_1      — UNET + CLIP concurrent, 1 worker
#   unet_only      — UNET only
#   clip_only      — CLIP only
#   vae            — UNET + CLIP + VAE concurrent, 4 workers
#   off            — skip CPU preload entirely
#   async_no_wait  — fire preload in background thread, don't block restore
#   budgeted_1500ms — preload with 1500ms time budget, stop when exceeded
PRELOAD_MODE = os.getenv("COMFYMODAL_PRELOAD_MODE", "off").strip().lower()
PROMPT_ASYNC_PRELOAD = os.getenv("PROMPT_ASYNC_PRELOAD", "0") == "1"
PROMPT_PRELOAD_WORKERS = int(os.getenv("PROMPT_PRELOAD_WORKERS", "2"))
PROMPT_ASYNC_ACTUAL_LOAD = os.getenv("PROMPT_ASYNC_ACTUAL_LOAD", "0") == "1"
PROMPT_ASYNC_ACTUAL_LOAD_UNET = os.getenv("PROMPT_ASYNC_ACTUAL_LOAD_UNET", "0") == "1"
DISABLE_CACHEDIT_FOR_Z_IMAGE = os.getenv("DISABLE_CACHEDIT_FOR_Z_IMAGE", "0") == "1"
DISABLE_RESTORE_WARMUP_FOR_Z_IMAGE = os.getenv("DISABLE_RESTORE_WARMUP_FOR_Z_IMAGE", "0") == "1"
ACTUAL_LOAD_MODE = os.getenv("ACTUAL_LOAD_MODE", "clip_vae_only").strip().lower()

# P1 — Direct warmup granular flags.
# DIRECT_WARMUP_LOAD_UNET/LOAD_CLIP gate whether UNET/CLIP are loaded
# during direct warmup at all.  Default both to 0 so that synchronous
# model reads during restore (16+ GB) are opt-in rather than the default.
# DIRECT_WARMUP_CLIP_ENCODE gates the dummy CLIPTextEncode forward pass.
DIRECT_WARMUP_LOAD_UNET = os.getenv("COMFYMODAL_DIRECT_WARMUP_LOAD_UNET", "0") == "1"
DIRECT_WARMUP_LOAD_CLIP = os.getenv("COMFYMODAL_DIRECT_WARMUP_LOAD_CLIP", "0") == "1"
DIRECT_WARMUP_CLIP_ENCODE = os.getenv("COMFYMODAL_DIRECT_WARMUP_CLIP_ENCODE", "0") == "1"
# When enabled, direct warmup only loads a model file if it is already
# present in the CPU cache (populated by CPU preload).  This prevents
# direct warmup from becoming a synchronous 16.85 GB volume read when
# CPU preload is disabled or async.
DIRECT_WARMUP_REQUIRE_CPU_CACHE_HIT = os.getenv("COMFYMODAL_DIRECT_WARMUP_REQUIRE_CPU_CACHE_HIT", "1") == "1"

# P2 — Sage runtime policy.
#   auto           — (default) probe and select automatically
#   baked_cuda     — skip probing, assume Blackwell baked CUDA path
#   triton_fallback — skip probing, force Triton fallback
SAGE_RUNTIME_MODE = os.getenv("COMFYMODAL_SAGE_RUNTIME_MODE", "auto").strip().lower()
# When 0, skip the Sage CUDA extension smoke test during restore.
# Use the persistent volume cache if available, or SAGE_RUNTIME_MODE default.
SAGE_RUNTIME_PROBE_ON_RESTORE = os.getenv("COMFYMODAL_SAGE_RUNTIME_PROBE_ON_RESTORE", "1") == "1"
PRELOAD_MODE_PATH = "/root/models/.preload_mode"
RUNTIME_CONFIG_DIR = "/root/models/runtime_config"
RUNTIME_RETURN_MODE_PATH = os.path.join(RUNTIME_CONFIG_DIR, "return_mode.txt")
RUNTIME_STATE_SNAPSHOT_PATH = os.path.join(RUNTIME_CONFIG_DIR, ".runtime_state_snapshot.json")

# ── PART 4: Baked dependency manifest (inside the image, NOT on volume) ──
BAKED_CUSTOM_NODE_DEPS_MANIFEST_PATH = "/opt/comfymodal/custom_node_deps_baked.json"

# ── PART 11: Known-good workflow profiles (for preload eligibility) ──
KNOWN_GOOD_WORKFLOW_PROFILES_PATH = "/root/models/runtime_config/known_good_workflow_profiles.json"
CURRENT_CUSTOM_NODE_DEPS_CACHE_PATH = "/root/models/runtime_config/current_custom_node_dependency_manifest_cache.json"

_WORKFLOW_IMAGE_SUFFIX_DIRS = {
    " [output]": "output",
    " [input]": "input",
    " [temp]": "temp",
}


def _split_workflow_image_reference(filename: str) -> tuple[str, str]:
    name = (filename or "").strip()
    for suffix, directory in _WORKFLOW_IMAGE_SUFFIX_DIRS.items():
        if name.endswith(suffix):
            return name[:-len(suffix)].rstrip(), directory
    return name, "input"


def _workflow_image_parts(filename: str) -> list[str]:
    normalized = (filename or "").replace("\\", "/")
    parts = [part for part in normalized.split("/") if part not in ("", ".")]
    if not parts or any(part == ".." for part in parts):
        raise ValueError(f"unsafe workflow image path: {filename}")
    return parts


def _resolve_input_image_destination(filename: str, comfy_root: str = "/root/comfy/ComfyUI") -> Path:
    relative_name, directory = _split_workflow_image_reference(filename)
    return Path(comfy_root) / directory / Path(*_workflow_image_parts(relative_name))


def _materialize_input_images(input_images: dict | None, comfy_root: str = "/root/comfy/ComfyUI") -> tuple[int, int]:
    import base64

    input_count = 0
    input_bytes = 0
    for filename, b64data in (input_images or {}).items():
        dest = _resolve_input_image_destination(filename, comfy_root=comfy_root)
        dest.parent.mkdir(parents=True, exist_ok=True)
        raw = base64.b64decode(b64data)
        dest.write_bytes(raw)
        input_count += 1
        input_bytes += len(raw)
    return input_count, input_bytes


def _model_cpu_cache_key(path: str) -> str:
    normalized = os.path.realpath(path) if path else path
    return os.path.normcase(os.path.normpath(normalized))


def _model_cpu_cache_lookup_keys(path: str) -> tuple[str, ...]:
    full_key = _model_cpu_cache_key(path)
    raw_norm = os.path.normcase(os.path.normpath(path)) if path else path
    basename = os.path.basename(path)
    candidates = []
    for candidate in (full_key, raw_norm, path, basename):
        if candidate and candidate not in candidates:
            candidates.append(candidate)
    return tuple(candidates)


def _iter_image_entries(node_out: dict):
    """Yield ``(output_key, entry)`` for each entry in ``node_out`` that looks
    like an image/video file reference (dict with a ``"filename"`` key).

    Skips non-list values (e.g. ``"animated"``).  The caller still needs to
    check ``node_out.get("animated", False)`` for the per-node animation flag.
    """
    for key, value in node_out.items():
        if not isinstance(value, list):
            continue
        for entry in value:
            if isinstance(entry, dict) and "filename" in entry:
                yield key, entry


def _apply_return_mode(result: dict, return_mode: str, payload_image_count: int, payload_video_count: int) -> dict:
    result.setdefault("_return_payload_info", {})["return_mode"] = return_mode
    if return_mode == "first_image_only" and result.get("images"):
        result["images"] = result["images"][:1]
        new_b64 = sum(len(img.get("data", "")) for img in result["images"])
        result["_return_payload_info"]["b64_bytes"] = new_b64
        print(f"[comfyapp] return_mode=first_image_only: kept 1/{payload_image_count} images, b64={new_b64}")
    elif return_mode == "metadata_only":
        for img in result.get("images", []):
            img.pop("data", None)
        for vid in result.get("videos", []):
            vid.pop("data", None)
        result["_return_payload_info"]["b64_bytes"] = 0
        print(f"[comfyapp] return_mode=metadata_only: stripped data from {payload_image_count} images/{payload_video_count} videos")
    elif return_mode == "paths_only":
        for img in result.get("images", []):
            img.pop("data", None)
            img["path"] = f"/root/comfy/ComfyUI/output/{img.get('filename', '')}"
        for vid in result.get("videos", []):
            vid.pop("data", None)
            vid["path"] = f"/root/comfy/ComfyUI/output/{vid.get('filename', '')}"
        result["_return_payload_info"]["b64_bytes"] = 0
        print(f"[comfyapp] return_mode=paths_only: {payload_image_count} images, {payload_video_count} videos")
    return result


def _resolve_runtime_flag(name: str, default: str) -> bool:
    """Read a runtime ``0``/``1`` flag from file or env var.

    Priority:
    1. File on the model volume at ``runtime_config/{name}.txt``.
    2. Env var ``COMFYMODAL_{name}``.
    3. ``default`` string (``"0"`` or ``"1"``).
    """
    path = os.path.join(RUNTIME_CONFIG_DIR, f"{name}.txt")
    try:
        if os.path.isfile(path):
            v = open(path).read().strip().lower()
            if v in ("0", "1"):
                return v == "1"
    except Exception:
        pass
    env = os.environ.get(f"COMFYMODAL_{name}", default)
    return env == "1"


def _resolve_sage_runtime_env_override() -> str:
    """Return the effective SAGE_RUNTIME_MODE from file, env, or module default.

    Priority:
    1. File ``runtime_config/sage_runtime_mode.txt``.
    2. Module-level ``SAGE_RUNTIME_MODE`` (from env var ``COMFYMODAL_SAGE_RUNTIME_MODE``).
    """
    path = os.path.join(RUNTIME_CONFIG_DIR, "sage_runtime_mode.txt")
    try:
        if os.path.isfile(path):
            v = open(path).read().strip().lower()
            if v in ("auto", "baked_cuda", "triton_fallback"):
                return v
    except Exception:
        pass
    return SAGE_RUNTIME_MODE


def _resolve_sage_probe_on_restore() -> bool:
    """Return whether to probe Sage runtime during restore.

    Priority:
    1. File ``runtime_config/sage_runtime_probe.txt``.
    2. Module-level ``SAGE_RUNTIME_PROBE_ON_RESTORE``.
    """
    path = os.path.join(RUNTIME_CONFIG_DIR, "sage_runtime_probe.txt")
    try:
        if os.path.isfile(path):
            v = open(path).read().strip().lower()
            if v in ("0", "1"):
                return v == "1"
    except Exception:
        pass
    return SAGE_RUNTIME_PROBE_ON_RESTORE


def _resolve_preload_mode() -> str:
    """Return the effective preload mode.

    Priority:
    1. File on the model volume (set by ``set_preload_mode``).
    2. Module-level env-var default (``PRELOAD_MODE``).
    """
    try:
        if os.path.isfile(PRELOAD_MODE_PATH):
            _v = open(PRELOAD_MODE_PATH).read().strip().lower()
            if _v:
                return _v
    except Exception:
        pass
    return PRELOAD_MODE


def _resolve_return_mode() -> str:
    """Return the effective return mode.

    Priority:
    1. File on the model volume (set by ``set_return_mode``).
    2. Env var ``COMFYMODAL_RETURN_MODE``.
    3. ``"full_base64"`` (default).
    """
    try:
        if os.path.isfile(RUNTIME_RETURN_MODE_PATH):
            _v = open(RUNTIME_RETURN_MODE_PATH).read().strip().lower()
            if _v in ("full_base64", "first_image_only", "metadata_only", "paths_only", "urls_only"):
                return _v
    except Exception:
        pass
    _valid = ("full_base64", "first_image_only", "metadata_only", "paths_only", "urls_only")
    _env = os.environ.get("COMFYMODAL_RETURN_MODE", "").strip().lower()
    if _env in _valid:
        return _env
    return "full_base64"

# ── Custom-node volume helpers ────────────────────────────────────────────

def _safe_listdir(path: str) -> list[str]:
    if not os.path.isdir(path):
        return []
    return sorted(os.listdir(path))


def custom_node_source_fingerprint(source_root: str) -> dict:
    """Return a fingerprint of the top-level custom-node directory structure
    including file content hashes (not just topology)."""
    nodes = []
    for name in _iter_syncable_custom_node_dirs(source_root):
        node_path = os.path.join(source_root, name)
        entry = {"name": name, "is_dir": True}
        if os.path.islink(node_path):
            entry["realpath_if_symlink"] = os.path.realpath(node_path)
        _hasher = hashlib.sha256()
        _tracked_exts = {".py", ".txt", ".toml", ".cfg"}
        _tracked_files = {"requirements.txt", "pyproject.toml", "setup.py", "setup.cfg"}
        try:
            for _dirpath, _dirnames, _filenames in os.walk(node_path):
                _dirnames[:] = [d for d in _dirnames if d not in (".git", "__pycache__", "node_modules", ".venv", "venv")]
                for _fn in sorted(_filenames):
                    _ext = os.path.splitext(_fn)[1].lower()
                    if _ext in _tracked_exts or _fn in _tracked_files:
                        _fp = os.path.join(_dirpath, _fn)
                        _rel = os.path.relpath(_fp, node_path).replace("\\", "/")
                        _hasher.update(f"{_rel}:".encode())
                        try:
                            _hasher.update(Path(_fp).read_bytes())
                        except OSError:
                            pass
        except Exception:
            pass
        entry["content_hash"] = _hasher.hexdigest()[:16]
        nodes.append(entry)
    return {
        "schema_version": 2,
        "source_root": source_root,
        "nodes": nodes,
    }


# Alias for backward compatibility
custom_node_topology_fingerprint = custom_node_source_fingerprint


def _is_volume_managed_link(link_path: str, volume_root: str) -> bool:
    if not os.path.islink(link_path):
        return False
    target = os.path.realpath(link_path)
    try:
        common = os.path.commonpath([os.path.abspath(volume_root), os.path.abspath(target)])
    except ValueError:
        return False
    return common == os.path.abspath(volume_root)


def custom_node_volume_state(volume_root: str) -> tuple:
    volume_root = os.path.abspath(volume_root)
    state = []
    for name in _iter_syncable_custom_node_dirs(volume_root):
        path = os.path.join(volume_root, name)
        stat = os.stat(path)
        req_file = os.path.join(path, "requirements.txt")
        req_mtime_ns = os.stat(req_file).st_mtime_ns if os.path.isfile(req_file) else None
        state.append((name, stat.st_mtime_ns, req_mtime_ns))
    return tuple(state)


def missing_expected_nodes(state: tuple, expected_nodes: list[str]) -> list[str]:
    visible = {name for name, *_ in state}
    return [name for name in expected_nodes if name not in visible]


def sync_custom_nodes_into_comfy(volume_root: str, comfy_custom_nodes_root: str, include_state: bool = False) -> dict:
    volume_root = os.path.abspath(volume_root)
    comfy_custom_nodes_root = os.path.abspath(comfy_custom_nodes_root)
    os.makedirs(comfy_custom_nodes_root, exist_ok=True)

    volume_dirs = []
    state = []
    for name in _iter_syncable_custom_node_dirs(volume_root):
        path = os.path.join(volume_root, name)
        volume_dirs.append(name)
        if include_state:
            stat = os.stat(path)
            req_file = os.path.join(path, "requirements.txt")
            req_mtime_ns = os.stat(req_file).st_mtime_ns if os.path.isfile(req_file) else None
            state.append((name, stat.st_mtime_ns, req_mtime_ns))

    removed = []
    created = []
    kept = []
    blocked = []

    for name in _safe_listdir(comfy_custom_nodes_root):
        dst = os.path.join(comfy_custom_nodes_root, name)
        if not _is_volume_managed_link(dst, volume_root):
            continue
        expected_src = os.path.join(volume_root, name)
        if name not in volume_dirs or os.path.realpath(dst) != os.path.realpath(expected_src):
            os.unlink(dst)
            removed.append(name)

    for name in sorted(volume_dirs):
        src = os.path.join(volume_root, name)
        dst = os.path.join(comfy_custom_nodes_root, name)
        if os.path.islink(dst) and os.path.realpath(dst) == os.path.realpath(src):
            kept.append(name)
            continue
        if os.path.lexists(dst):
            # A real directory (not a volume-managed symlink) is blocking
            # the symlink.  The volume is the source of truth for custom
            # nodes, so remove the directory and replace it with a symlink.
            # This handles the case where a previous image or snapshot
            # installed the node as a real directory.
            if os.path.isdir(dst) and not os.path.islink(dst):
                import shutil
                shutil.rmtree(dst)
                print(f"[comfyapp] sync: replaced real directory with volume symlink name={name}")
            else:
                os.unlink(dst)
        os.symlink(src, dst)
        created.append(name)

    result = {
        "created": created,
        "removed": removed,
        "kept": kept,
        "blocked": blocked,
    }
    if include_state:
        result["state"] = tuple(state)
    print(f"[comfyapp] sync_custom_nodes_into_comfy: created={len(created)} kept={len(kept)} "
          f"removed={len(removed)} blocked={len(blocked)} volume_dirs={len(volume_dirs)}")
    return result

RUNTIME_METADATA_PATH = "/root/models/runtime_config/runtime_metadata.json"


def requirements_file_hash(path: str) -> str | None:
    """Return sha256 hex of a requirements.txt file, or None if missing."""
    if not os.path.isfile(path):
        return None
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def collect_custom_node_dependency_files(node_path: str) -> dict[str, str]:
    """Collect dependency-relevant file paths under *node_path*.

    This is the single source of truth for dependency file scanning.
    Used by both ``build_custom_node_dependency_manifest`` (hashing)
    and ``_prepare_custom_node_requirements_build_context`` (copying).

    Returns a dict of ``relative_path -> sha256_hex`` for:
    - requirements.txt
    - any file included by -r / --requirement
    - pyproject.toml, setup.py, setup.cfg
    - local wheel files referenced by requirements
    - local packages/folders referenced by -e, --editable, ./path, ../path
    - constraints files included by -c / --constraint

    Does NOT hash the whole source tree.  Ignores .git, __pycache__,
    node_modules, venv, .venv, image files, videos, markdown docs,
    notebooks, model files.
    """
    _IGNORE_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".tiff", ".bmp",
                    ".webp", ".ico", ".mp4", ".avi", ".mov", ".mkv",
                    ".webm", ".md", ".rst", ".ipynb", ".gz", ".zip",
                    ".tar", ".pyc", ".pyo", ".safetensors", ".ckpt",
                    ".pt", ".pth", ".bin"}
    _IGNORE_DIRS = {".git", "__pycache__", "node_modules", ".venv", "venv",
                    ".ipynb_checkpoints"}

    files: dict[str, str] = {}
    _seen_real: set[str] = set()

    def _add_file(filepath: str, node_root: str) -> None:
        if not os.path.isfile(filepath):
            return
        real = os.path.realpath(filepath)
        if real in _seen_real:
            return
        _seen_real.add(real)
        rel = _safe_dependency_relpath(filepath, node_root)
        files[rel] = hashlib.sha256(Path(filepath).read_bytes()).hexdigest()

    def _scan_requirements(req_path: str, node_root: str, seen_req: set[str]) -> None:
        req_path = os.path.abspath(req_path)
        if req_path in seen_req:
            return
        seen_req.add(req_path)
        if not os.path.isfile(req_path):
            return
        _add_file(req_path, node_root)
        req_dir = os.path.dirname(req_path)
        try:
            for line in Path(req_path).read_text(encoding="utf-8").splitlines():
                stripped = line.strip()
                if not stripped or stripped.startswith("#"):
                    continue
                stripped = stripped.split(";", 1)[0].strip()
                if not stripped:
                    continue
                if stripped.startswith("-r ") or stripped.startswith("--requirement "):
                    prefix = stripped.split(" ", 1)[1].strip()
                    included = os.path.abspath(os.path.join(req_dir, prefix))
                    if os.path.isfile(included):
                        _scan_requirements(included, node_root, seen_req)
                elif stripped.startswith("-c ") or stripped.startswith("--constraint "):
                    prefix = stripped.split(" ", 1)[1].strip()
                    included = os.path.abspath(os.path.join(req_dir, prefix))
                    _add_file(included, node_root)
                elif stripped.startswith("-e ") or stripped.startswith("--editable "):
                    local_path = stripped.split(" ", 1)[1].strip()
                    resolved = os.path.abspath(os.path.join(req_dir, local_path))
                    _add_tree(resolved, node_root)
                elif stripped.startswith("./") or stripped.startswith("../"):
                    local_path = os.path.abspath(os.path.join(req_dir, stripped))
                    _add_tree(local_path, node_root)
        except (OSError, UnicodeDecodeError):
            pass

    def _add_tree(path: str, node_root: str) -> None:
        if not os.path.exists(path):
            return
        real = os.path.realpath(path)
        if real in _seen_real:
            return
        _seen_real.add(real)
        if os.path.isfile(path):
            rel = _safe_dependency_relpath(path, node_root)
            files[rel] = hashlib.sha256(Path(path).read_bytes()).hexdigest()
        elif os.path.isdir(path):
            for dirpath, dirnames, filenames in os.walk(path):
                dirnames[:] = [d for d in dirnames if d not in _IGNORE_DIRS]
                for fn in filenames:
                    ext = os.path.splitext(fn)[1].lower()
                    if ext in _IGNORE_EXTS:
                        continue
                    fp = os.path.join(dirpath, fn)
                    _add_file(fp, node_root)

    req_path = os.path.join(node_path, "requirements.txt")
    _scan_requirements(req_path, node_path, set())

    req_dir = os.path.join(node_path, "requirements")
    if os.path.isdir(req_dir):
        for _rf in sorted(os.listdir(req_dir)):
            if _rf.endswith(".txt") or _rf.endswith(".pip"):
                _scan_requirements(os.path.join(req_dir, _rf), node_path, set())

    for base_name in ("pyproject.toml", "setup.py", "setup.cfg", "install.py"):
        base_path = os.path.join(node_path, base_name)
        if os.path.isfile(base_path):
            _add_file(base_path, node_path)

    return files


def _collect_dependency_file_paths(node_path: str) -> dict[str, str]:
    """Backward-compatible alias for ``collect_custom_node_dependency_files``."""
    return collect_custom_node_dependency_files(node_path)


class RequestPipelineState:
    """Structured request pipeline state for truthful summary generation.

    Tracks every phase of a prompt request through the pipeline so the
    summary dict is populated from real state rather than best-effort kwargs.
    """

    __slots__ = (
        "request_id", "mode", "stream",
        "workflow_hash", "model_stack",
        "local_preflight_validated", "remote_preflight_validated",
        "custom_node_sync_result", "custom_node_sync_skipped",
        "custom_node_sync_skip_reason",
        "dependency_result", "dependency_manifest_cache_hit",
        "missing_node_result",
        "active_profile_result", "active_profile_expired",
        "active_profile_source", "preload_skip_reason",
        "prompt_preload_result", "actual_load_result",
        "execution_started", "execution_success",
        "known_good_marked", "known_good_mark_result",
        "failure_phase", "failure_reason",
        "clip_actual_load_submitted", "clip_actual_load_cache_hit",
        "clip_actual_load_duration_ms",
        "_timestamps",
    )

    def __init__(self, request_id: str = "", mode: str = "", stream: bool = False):
        self.request_id = request_id
        self.mode = mode
        self.stream = stream
        self.workflow_hash = ""
        self.model_stack = {}
        self.local_preflight_validated = False
        self.remote_preflight_validated = False
        self.custom_node_sync_result = ""
        self.custom_node_sync_skipped = False
        self.custom_node_sync_skip_reason = ""
        self.dependency_result = ""
        self.dependency_manifest_cache_hit = False
        self.missing_node_result = ""
        self.active_profile_result = ""
        self.active_profile_expired = False
        self.active_profile_source = ""
        self.preload_skip_reason = ""
        self.prompt_preload_result = ""
        self.actual_load_result = ""
        self.execution_started = False
        self.execution_success = False
        self.known_good_marked = False
        self.known_good_mark_result = ""
        self.failure_phase = ""
        self.failure_reason = ""
        self.clip_actual_load_submitted = False
        self.clip_actual_load_cache_hit = False
        self.clip_actual_load_duration_ms = 0.0
        self._timestamps: dict[str, float] = {}

    def mark(self, phase: str) -> None:
        self._timestamps[phase] = time.time()

    def fail(self, phase: str, reason: str) -> None:
        self.failure_phase = phase
        self.failure_reason = reason
        self.mark(f"fail_{phase}")

    def to_summary(self) -> dict:
        return {
            "request_id": self.request_id,
            "mode": self.mode,
            "stream": self.stream,
            "workflow_hash": self.workflow_hash,
            "model_stack": self.model_stack,
            "local_preflight_validated": self.local_preflight_validated,
            "remote_preflight_validated": self.remote_preflight_validated,
            "custom_node_sync_result": self.custom_node_sync_result,
            "custom_node_sync_skipped": self.custom_node_sync_skipped,
            "custom_node_sync_skip_reason": self.custom_node_sync_skip_reason,
            "dependency_result": self.dependency_result,
            "dependency_manifest_cache_hit": self.dependency_manifest_cache_hit,
            "missing_node_result": self.missing_node_result,
            "active_profile_result": self.active_profile_result,
            "active_profile_expired": self.active_profile_expired,
            "active_profile_source": self.active_profile_source,
            "preload_skip_reason": self.preload_skip_reason,
            "prompt_preload_result": self.prompt_preload_result,
            "actual_load_result": self.actual_load_result,
            "execution_started": self.execution_started,
            "execution_success": self.execution_success,
            "known_good_marked": self.known_good_marked,
            "known_good_mark_result": self.known_good_mark_result,
            "failure_phase": self.failure_phase,
            "failure_reason": self.failure_reason,
            "clip_actual_load_submitted": self.clip_actual_load_submitted,
            "clip_actual_load_cache_hit": self.clip_actual_load_cache_hit,
            "clip_actual_load_duration_ms": self.clip_actual_load_duration_ms,
        }


def make_request_pipeline_summary(**kwargs) -> dict:
    """Build a compact request pipeline summary for log/metadata.

    Passes all kwargs matching ``RequestPipelineState`` fields through
    to the state object so callers provide real data rather than defaults.
    """
    state = RequestPipelineState(
        request_id=kwargs.get("request_id", ""),
        mode=kwargs.get("mode", ""),
        stream=kwargs.get("stream", False),
    )
    for field in RequestPipelineState.__slots__:
        if field in kwargs and field not in ("request_id", "mode", "stream"):
            setattr(state, field, kwargs[field])
    return state.to_summary()


def custom_node_dependency_fingerprint(source_root: str) -> dict:
    """Build a dependency-only fingerprint for caching.

    Uses ``collect_custom_node_dependency_files`` for every top-level
    custom node.  Includes only dependency-relevant files (no ordinary
    .py source, no mtimes).  The ``overall_dependency_hash`` changes
    only when dependency-relevant files change.

    Returns:
        ``{"schema_version": 1, "source_root": str, "nodes": {...},
          "overall_dependency_hash": str}``
    """
    hasher = hashlib.sha256()
    nodes_out: dict = {}
    for entry in _iter_syncable_custom_node_dirs(source_root):
        node_path = os.path.join(source_root, entry)
        dep_files = collect_custom_node_dependency_files(node_path)
        if not dep_files:
            continue
        nodes_out[entry] = {"dependency_files": dep_files}
        for rel_path in sorted(dep_files):
            hasher.update(f"{entry}/{rel_path}:{dep_files[rel_path]}".encode())

    return {
        "schema_version": 1,
        "source_root": source_root,
        "nodes": nodes_out,
        "overall_dependency_hash": hasher.hexdigest(),
    }


def build_custom_node_dependency_manifest(source_root: str) -> dict:
    """Build a deterministic dependency manifest for all custom nodes under
    *source_root*.

    Scans dependency-relevant files only — not entire source trees.
    """
    import sys as _sys
    nodes_manifest: dict[str, dict] = {}
    overall_input: dict[str, dict] = {}
    for node_name in _iter_syncable_custom_node_dirs(source_root):
        node_path = os.path.join(source_root, node_name)
        dep_files = _collect_dependency_file_paths(node_path)
        has_reqs = "requirements.txt" in dep_files
        req_hash = ""
        if has_reqs:
            req_hash = dep_files["requirements.txt"]
        nodes_manifest[node_name] = {
            "has_requirements": has_reqs,
            "dependency_files": dep_files,
            "requirements_hash": req_hash,
        }
        # Only include nodes with non-empty dependency_files in overall hash
        # so adding/removing a no-dependency node does not force a rebuild.
        if dep_files:
            overall_input[node_name] = dep_files

    syncable_node_names = _iter_syncable_custom_node_dirs(source_root)
    dependency_node_names = sorted([
        name for name, data in nodes_manifest.items() if data.get("dependency_files")
    ])
    stable = json.dumps(overall_input, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    overall_hash = hashlib.sha256(stable.encode("utf-8")).hexdigest()
    return {
        "schema_version": 2,
        "created_by": "comfyapp.py",
        "python_version": f"{_sys.version_info.major}.{_sys.version_info.minor}.{_sys.version_info.micro}",
        "comfyapp_version": COMFYAPP_VERSION,
        "source_root": source_root,
        "syncable_node_names": syncable_node_names,
        "nodes": nodes_manifest,
        "dependency_nodes": dependency_node_names,
        "overall_dependency_hash": overall_hash,
    }


def load_baked_custom_node_dependency_manifest() -> dict:
    """Read the baked dependency manifest from inside the image.

    Returns an empty dict if the manifest does not exist (image was not
    built with the manifest — compatibility fallback).
    """
    if not os.path.isfile(BAKED_CUSTOM_NODE_DEPS_MANIFEST_PATH):
        return {}
    try:
        with open(BAKED_CUSTOM_NODE_DEPS_MANIFEST_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict) and data.get("schema_version") in (1, 2):
            return data
        return {}
    except (json.JSONDecodeError, OSError):
        return {}


def get_runtime_custom_node_source_root_for_dependency_validation() -> str:
    """Return the custom-node source root that actually controls runtime nodes.

    The volume (``CUSTOM_NODES_PATH``) is authoritative for dynamic custom
    nodes.  When the volume is empty or contains only non-syncable entries
    (``.staging``, ``__pycache__``, etc.), the image-baked nodes at
    ``/root/comfy/ComfyUI/custom_nodes`` are used as fallback.

    Uses ``_iter_syncable_custom_node_dirs`` to filter out non-node entries
    so that stray artifacts do not cause false dependency mismatches.
    """
    _raw_entries = len(_safe_listdir(CUSTOM_NODES_PATH)) if os.path.isdir(CUSTOM_NODES_PATH) else 0
    _syncable = _iter_syncable_custom_node_dirs(CUSTOM_NODES_PATH) if os.path.isdir(CUSTOM_NODES_PATH) else []
    if os.path.isdir(CUSTOM_NODES_PATH) and _syncable:
        _used_root = CUSTOM_NODES_PATH
        _source = "volume"
    else:
        _used_root = "/root/comfy/ComfyUI/custom_nodes"
        _source = "image_baked"
    print(
        f"[comfyapp] dependency_validation source_root={_used_root} "
        f"source={_source} "
        f"volume_syncable_nodes={len(_syncable)} "
        f"raw_volume_entries={_raw_entries}"
    )
    return _used_root


def build_current_custom_node_dependency_manifest() -> dict:
    """Build a current dependency manifest from the runtime source root.

    Uses the same scanning rules as ``build_custom_node_dependency_manifest``.
    The source root is determined by
    ``get_runtime_custom_node_source_root_for_dependency_validation()``:
    volume if it has content, otherwise the image-baked custom nodes path.
    """
    return build_custom_node_dependency_manifest(
        get_runtime_custom_node_source_root_for_dependency_validation()
    )


def validate_custom_node_dependencies_prepared() -> dict:
    """Compare the baked image manifest against the current custom-node volume.

    Returns a dict with keys:
    - prepared: bool
    - reason: str
    - baked_hash: str | None
    - current_hash: str | None
    - changed_nodes: list[str]
    """
    baked = load_baked_custom_node_dependency_manifest()
    if not baked:
        return {
            "prepared": False,
            "reason": "baked_manifest_missing",
            "baked_hash": None,
            "current_hash": None,
            "changed_nodes": [],
        }
    try:
        current = build_current_custom_node_dependency_manifest_cached()
    except Exception as exc:
        return {
            "prepared": False,
            "reason": f"current_manifest_invalid:{exc}",
            "baked_hash": baked.get("overall_dependency_hash"),
            "current_hash": None,
            "changed_nodes": [],
        }
    baked_hash = baked.get("overall_dependency_hash", "")
    current_hash = current.get("overall_dependency_hash", "")

    baked_node_names = set(baked.get("syncable_node_names", baked.get("nodes", {}).keys()) or [])
    current_node_names = set(current.get("syncable_node_names", current.get("nodes", {}).keys()) or [])

    # Node set mismatch detection: if baked manifest has no nodes but current does
    if current_node_names and not baked_node_names:
        return {
            "prepared": False,
            "reason": "baked_manifest_has_no_custom_nodes",
            "baked_hash": baked_hash,
            "current_hash": current_hash,
            "changed_nodes": sorted(current_node_names),
        }

    if baked_node_names != current_node_names:
        _ignored_env = os.environ.get("COMFYMODAL_CUSTOM_NODE_SET_MISMATCH_IGNORE", "").strip()
        _ignored = {x.strip() for x in _ignored_env.split(",")} if _ignored_env else set()
        missing_in_baked = sorted(current_node_names - baked_node_names - _ignored)
        extra_in_baked = sorted(baked_node_names - current_node_names - _ignored)
        effective_mismatch = bool(missing_in_baked or extra_in_baked)
        if _ignored:
            print(
                f"[comfyapp] node_set_mismatch_ignored={sorted(_ignored & (current_node_names ^ baked_node_names))} "
                f"(configured via COMFYMODAL_CUSTOM_NODE_SET_MISMATCH_IGNORE)"
            )
        if not effective_mismatch:
            if baked_hash == current_hash:
                return {
                    "prepared": True,
                    "reason": "hash_match_after_ignored_mismatches",
                    "baked_hash": baked_hash,
                    "current_hash": current_hash,
                    "changed_nodes": [],
                }
        return {
            "prepared": False,
            "reason": "custom_node_set_mismatch",
            "baked_hash": baked_hash,
            "current_hash": current_hash,
            "changed_nodes": missing_in_baked,
        }

    if baked_hash == current_hash:
        return {
            "prepared": True,
            "reason": "hash_match",
            "baked_hash": baked_hash,
            "current_hash": current_hash,
            "changed_nodes": [],
        }
    # Find changed nodes
    baked_nodes = baked.get("nodes", {})
    current_nodes = current.get("nodes", {})
    changed = []
    all_names = set(baked_nodes) | set(current_nodes)
    for name in sorted(all_names):
        bn = baked_nodes.get(name, {})
        cn = current_nodes.get(name, {})
        if bn.get("requirements_hash") != cn.get("requirements_hash"):
            changed.append(name)
        elif bn.get("dependency_files") != cn.get("dependency_files"):
            changed.append(name)
    return {
        "prepared": False,
        "reason": "dependency_hash_mismatch",
        "baked_hash": baked_hash,
        "current_hash": current_hash,
        "changed_nodes": changed,
    }


# ── PART 11: Known-good workflow profiles ──
def load_known_good_workflow_profiles() -> dict:
    """Load known-good workflow profiles from the volume."""
    try:
        if os.path.isfile(KNOWN_GOOD_WORKFLOW_PROFILES_PATH):
            with open(KNOWN_GOOD_WORKFLOW_PROFILES_PATH, "r") as f:
                data = json.load(f)
            if isinstance(data, dict):
                return data
    except (json.JSONDecodeError, OSError):
        pass
    return {}


import threading as _threading
_volume_commit_lock = _threading.Lock()
_volume_commit_inflight_labels: set[str] = set()
_volume_commit_dirty_labels: set[str] = set()


def _commit_volume_async(label: str = "") -> None:
    """Schedule an asynchronous ``vol.commit()`` in a daemon thread.

    Uses a loop‑based worker per label so no follow‑up depth cap can
    drop a dirty write:

    * If no commit is running for *label*, start one.
    * If a commit is already running, mark *label* dirty and return.
    * The running worker loops until no dirty marker remains.
    """
    import threading
    with _volume_commit_lock:
        if label and label in _volume_commit_inflight_labels:
            _volume_commit_dirty_labels.add(label)
            print(
                f"[comfyapp] volume_commit_async_deferred "
                f"label={label} reason=already_in_flight_marked_dirty"
            )
            return
        if label:
            _volume_commit_inflight_labels.add(label)
    if label:
        print(f"[comfyapp] volume_commit_async_started label={label}")
    t = threading.Thread(target=_commit_worker, args=(label,), daemon=True)
    t.start()


def _commit_worker(label: str) -> None:
    """Loop: commit until no dirty marker remains for this label."""
    while True:
        try:
            vol.commit()
            print(f"[comfyapp] volume_commit_async_finished label={label}")
        except Exception as exc:
            print(f"[comfyapp] volume_commit_async_failed label={label} error={exc}")
        with _volume_commit_lock:
            if label and label in _volume_commit_dirty_labels:
                _volume_commit_dirty_labels.discard(label)
                print(f"[comfyapp] volume_commit_async_followup_started label={label}")
                continue
            if label:
                _volume_commit_inflight_labels.discard(label)
            break


def save_known_good_workflow_profiles(profiles: dict) -> None:
    """Persist known-good workflow profiles to the volume."""
    try:
        os.makedirs(os.path.dirname(KNOWN_GOOD_WORKFLOW_PROFILES_PATH), exist_ok=True)
        tmp = f"{KNOWN_GOOD_WORKFLOW_PROFILES_PATH}.tmp"
        with open(tmp, "w") as f:
            json.dump(profiles, f, indent=2, sort_keys=True)
        os.replace(tmp, KNOWN_GOOD_WORKFLOW_PROFILES_PATH)
        _commit_volume_async(label="known_good_profiles")
    except Exception as exc:
        print(f"[comfyapp] failed to save known-good profiles: {exc}")


def _is_known_good_workflow_profile(workflow_hash: str, profile: dict) -> bool:
    """Return True if this workflow/profile is known-good (previously succeeded)."""
    profiles = load_known_good_workflow_profiles()
    if workflow_hash in profiles:
        return True
    mode = profile.get("mode", "")
    if mode == "checkpoint":
        ckpt = profile.get("checkpoint", "")
        return any(
            p.get("mode") == "checkpoint" and p.get("checkpoint") == ckpt
            for p in profiles.values()
        )
    elif mode == "split":
        unet = profile.get("unet", "")
        return any(
            p.get("mode") == "split" and p.get("unet") == unet
            for p in profiles.values()
        )
    return False


def _mark_known_good_workflow_profile(workflow_hash: str, profile: dict) -> bool:
    """Mark a workflow/profile as known-good after successful execution.

    Returns True if a new or changed entry was persisted and a volume
    commit was scheduled.  Returns False when the entry already exists
    and is identical (no commit scheduled).
    """
    profiles = load_known_good_workflow_profiles()
    new_entry = {
        "mode": profile.get("mode", ""),
        "workflow_hash": workflow_hash,
        **profile,
    }
    existing = profiles.get(workflow_hash)
    if existing is not None and existing == new_entry:
        print(f"[comfyapp] marked known-good workflow hash={workflow_hash} changed=0 (identical)")
        return False
    profiles[workflow_hash] = new_entry
    save_known_good_workflow_profiles(profiles)
    print(f"[comfyapp] marked known-good workflow hash={workflow_hash} changed=1")
    return True


def load_current_dependency_manifest_cache() -> dict:
    """Load the cached current dependency manifest.

    Returns an empty dict when the cache does not exist or is corrupt.
    """
    try:
        if os.path.isfile(CURRENT_CUSTOM_NODE_DEPS_CACHE_PATH):
            with open(CURRENT_CUSTOM_NODE_DEPS_CACHE_PATH, "r") as f:
                data = json.load(f)
            if isinstance(data, dict) and data.get("schema_version") == 1:
                return data
    except (json.JSONDecodeError, OSError):
        pass
    return {}


def save_current_dependency_manifest_cache(cache: dict) -> None:
    """Persist the current dependency manifest cache to volume storage."""
    try:
        os.makedirs(os.path.dirname(CURRENT_CUSTOM_NODE_DEPS_CACHE_PATH), exist_ok=True)
        tmp = f"{CURRENT_CUSTOM_NODE_DEPS_CACHE_PATH}.tmp"
        with open(tmp, "w") as f:
            json.dump(cache, f, indent=2, sort_keys=True)
        os.replace(tmp, CURRENT_CUSTOM_NODE_DEPS_CACHE_PATH)
        _commit_volume_async(label="dependency_manifest_cache")
    except Exception as exc:
        print(f"[comfyapp] failed to save dependency manifest cache: {exc}")


def build_current_custom_node_dependency_manifest_cached() -> dict:
    """Build current dependency manifest using the dependency-only fingerprint cache.

    When the dependency fingerprint is unchanged since the last call, the
    previously-built manifest is returned.  The cache is invalidated only
    when dependency-relevant file content changes (requirements.txt,
    pyproject.toml, setup.py, etc.) — ordinary .py source changes do not
    invalidate it.
    """
    source_root = get_runtime_custom_node_source_root_for_dependency_validation()
    dep_fp = custom_node_dependency_fingerprint(source_root)
    dep_hash = dep_fp.get("overall_dependency_hash", "")

    cache = load_current_dependency_manifest_cache()
    cache_manifest = cache.get("manifest") if isinstance(cache, dict) else None
    if (
        cache
        and isinstance(cache_manifest, dict)
        and cache.get("source_root") == source_root
        and cache.get("dependency_fingerprint_hash") == dep_hash
    ):
        print(f"[comfyapp] dependency_manifest_cache hit hash={dep_hash[:16]}...")
        return cache_manifest

    reason = "miss"
    if not cache:
        reason = "no_cache"
    elif cache.get("source_root") != source_root:
        reason = "source_root_changed"
    elif cache.get("dependency_fingerprint_hash") != dep_hash:
        reason = "fingerprint_changed"

    manifest = build_custom_node_dependency_manifest(source_root)
    new_cache = {
        "schema_version": 1,
        "source_root": source_root,
        "dependency_fingerprint_hash": dep_hash,
        "manifest": manifest,
        "created_at": time.time(),
    }
    save_current_dependency_manifest_cache(new_cache)
    print(f"[comfyapp] dependency_manifest_cache miss reason={reason} hash={dep_hash[:16]}...")
    return manifest


_REQ_TOP_LEVEL_NAME = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.\-]*")


def _iter_top_level_requirement_names(req_path: str) -> list[str]:
    """Yield top-level distribution names from a requirements.txt.

    Skips comments, blank lines, pip flags (``-r``, ``--editable``), local
    paths (``./foo``), and VCS / URL sources. Extras like ``package[gpu]==1.0``
    are normalised to the base distribution name.
    """
    if not os.path.isfile(req_path):
        return []
    names: list[str] = []
    for raw in Path(req_path).read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        # Strip inline environment markers
        line = line.split(";", 1)[0].strip()
        if not line:
            continue
        if line.startswith("-r") or line.startswith("--requirement"):
            continue
        if line.startswith("-c") or line.startswith("--constraint"):
            continue
        if line.startswith("-e ") or line.startswith("--editable "):
            line = line.split(" ", 1)[1].strip()
        if line.startswith("./") or line.startswith("../") or line.startswith("/"):
            continue
        if "://" in line:
            continue
        match = _REQ_TOP_LEVEL_NAME.match(line)
        if not match:
            continue
        # Skip packages whose platform marker doesn't match the current platform.
        # This avoids false missing-distribution detection for conditionally-
        # required packages (e.g. triton-windows on Linux, triton on Windows).
        if ";" in raw:
            marker_text = raw.split(";", 1)[1].strip().lower()
            if "sys_platform" in marker_text:
                if "== 'win32'" in marker_text and sys.platform != "win32":
                    continue
                if "== 'linux'" in marker_text and sys.platform != "linux":
                    continue
                if "!= 'win32'" in marker_text and sys.platform == "win32":
                    continue
                if "!= 'linux'" in marker_text and sys.platform == "linux":
                    continue
        names.append(match.group(0))
    return names


def _canonicalize_dist_name(name: str) -> str:
    """Normalize a distribution name per PEP 503 (lowercase, ``[-_.]+`` → ``-``)."""
    return re.sub(r"[-_.]+", "-", name).lower()


def _requirements_have_importable_packages(req_path: str) -> bool:
    """Return True if every top-level requirement listed in ``req_path``
    corresponds to an installed distribution (by metadata ``Name`` field).

    Uses distribution metadata (``importlib.metadata.distributions()``)
    rather than import-module guesses so that packages whose distribution
    name differs from their module name (e.g. ``Pillow`` → ``PIL``,
    ``opencv-python-headless`` → ``cv2``) are correctly recognised.

    Returns ``True`` when the file is empty or contains only local paths /
    VCS sources / pip flags (no top-level packages to verify). Returns
    ``False`` as soon as one named distribution is not found among the
    currently installed packages, indicating the cache entry is stale and
    ``_install_custom_node_requirements`` should reinstall.
    """
    names = _iter_top_level_requirement_names(req_path)
    if not names:
        return True
    import importlib.metadata
    installed = set()
    for dist in importlib.metadata.distributions():
        dist_name = dist.metadata.get("Name")
        if dist_name:
            installed.add(_canonicalize_dist_name(dist_name))
    req_names = {_canonicalize_dist_name(n) for n in names}
    return req_names.issubset(installed)


def model_volume_state(volume_root: str) -> tuple:
    """Snapshot of (folder, name, mtime_ns, size) for every file on a model volume."""
    volume_root = os.path.abspath(volume_root)
    state = []
    for folder in _safe_listdir(volume_root):
        folder_path = os.path.join(volume_root, folder)
        if not os.path.isdir(folder_path):
            continue
        for name in _safe_listdir(folder_path):
            path = os.path.join(folder_path, name)
            if not os.path.isfile(path):
                continue
            try:
                st = os.stat(path)
            except (OSError, FileNotFoundError):
                continue
            state.append((folder, name, st.st_mtime_ns, st.st_size))
    return tuple(state)


def load_runtime_metadata() -> dict:
    """Load JSON metadata from the container filesystem."""
    if not os.path.isfile(RUNTIME_METADATA_PATH):
        return {"requirements": {}, "runtime": {}}
    try:
        with open(RUNTIME_METADATA_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return {"requirements": {}, "runtime": {}}
        return data
    except (json.JSONDecodeError, OSError):
        return {"requirements": {}, "runtime": {}}


def save_runtime_metadata(data: dict) -> None:
    """Persist JSON metadata to the volume, scheduling an async commit.

    Skips write when the content is identical to the existing file to
    avoid unnecessary volume commits in the hot path.
    """
    payload = json.dumps(data, indent=2, sort_keys=True)
    if os.path.isfile(RUNTIME_METADATA_PATH):
        try:
            with open(RUNTIME_METADATA_PATH, "r", encoding="utf-8") as f:
                if f.read() == payload:
                    return
        except (OSError, UnicodeDecodeError):
            pass
    os.makedirs(os.path.dirname(RUNTIME_METADATA_PATH), exist_ok=True)
    tmp_path = f"{RUNTIME_METADATA_PATH}.tmp"
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            f.write(payload)
        os.replace(tmp_path, RUNTIME_METADATA_PATH)
        _commit_volume_async(label="runtime_metadata")
    except Exception as exc:
        print(f"[comfyapp] failed to save runtime metadata: {exc}")


def set_manager_network_mode_offline() -> list[str]:
    """Force ComfyUI-Manager into offline mode for runtime containers."""
    config_paths = [
        "/root/comfy/ComfyUI/user/default/__manager/config.ini",
        "/root/comfy/ComfyUI/user/default/ComfyUI-Manager/config.ini",
    ]
    written = []
    for config_path in config_paths:
        os.makedirs(os.path.dirname(config_path), exist_ok=True)
        with open(config_path, "w", encoding="utf-8") as f:
            f.write("[default]\nnetwork_mode = offline\n")
        written.append(config_path)
    return written


def _get_system_ram_gb() -> float:
    """Return total system RAM in GB by parsing /proc/meminfo.

    Falls back to 16 GB if the file cannot be read (e.g. non-Linux).
    """
    try:
        with open("/proc/meminfo") as f:
            for line in f:
                if line.startswith("MemTotal:"):
                    kb = int(line.split()[1])
                    val = kb / (1024 * 1024)
                    return round(val, 1)
    except Exception:
        pass
    return 16.0


def load_warmup_profile() -> dict:
    """Return the configured pinned warmup profile, if any.

    Prefers runtime-set env vars over module-level constants so that
    dynamically-set env vars (e.g. restore-time defaults) take effect.
    """
    _get = lambda k, dflt="": (os.environ.get(k) or dflt).strip()
    checkpoint = _get("COMFYMODAL_WARMUP_CHECKPOINT", WARMUP_CHECKPOINT)
    unet = _get("COMFYMODAL_WARMUP_UNET", WARMUP_UNET)
    clip1 = _get("COMFYMODAL_WARMUP_CLIP1", WARMUP_CLIP1)
    clip2 = _get("COMFYMODAL_WARMUP_CLIP2", WARMUP_CLIP2)
    vae = _get("COMFYMODAL_WARMUP_VAE", WARMUP_VAE)
    clip_type = _get("COMFYMODAL_WARMUP_CLIP_TYPE", WARMUP_CLIP_TYPE) or "flux"
    if checkpoint:
        return {
            "mode": "checkpoint",
            "checkpoint": checkpoint,
        }
    if unet and clip1 and clip2 and vae:
        c1, c2 = normalize_flux_clip_pair(clip1, clip2) if clip_type == "flux" else (clip1, clip2)
        return {
            "mode": "split",
            "unet": unet,
            "clip1": c1,
            "clip2": c2,
            "vae": vae,
            "clip_type": clip_type,
        }
    return {}


def extract_requested_model_stack(workflow: dict) -> dict:
    """Extract a minimal model stack from a workflow for warmup matching."""
    stack: dict = {"checkpoint": [], "unet": [], "clip": [], "vae": [], "clip_type": "flux"}
    for node in workflow.values():
        if not isinstance(node, dict):
            continue
        class_type = node.get("class_type", "")
        inputs = node.get("inputs", {})
        if not isinstance(inputs, dict):
            continue
        if class_type in {"CheckpointLoaderSimple", "CheckpointLoader"}:
            value = inputs.get("ckpt_name")
            if isinstance(value, str) and value and value not in stack["checkpoint"]:
                stack["checkpoint"].append(value)
        elif class_type == "UNETLoader":
            value = inputs.get("unet_name")
            if isinstance(value, str) and value and value not in stack["unet"]:
                stack["unet"].append(value)
        elif class_type == "DualCLIPLoader":
            for key in ("clip_name1", "clip_name2"):
                value = inputs.get(key)
                if isinstance(value, str) and value and value not in stack["clip"]:
                    stack["clip"].append(value)
            # Capture clip_type from the actual workflow loader node
            _ct = inputs.get("type", "")
            if isinstance(_ct, str) and _ct:
                stack["clip_type"] = _ct
        elif class_type == "CLIPLoader":
            value = inputs.get("clip_name")
            if isinstance(value, str) and value and value not in stack["clip"]:
                stack["clip"].append(value)
            _ct = inputs.get("type", "")
            if isinstance(_ct, str) and _ct:
                stack["clip_type"] = _ct
        elif class_type == "VAELoader":
            value = inputs.get("vae_name")
            if isinstance(value, str) and value and value not in stack["vae"]:
                stack["vae"].append(value)
    return stack


def warmup_profile_matches_workflow(profile: dict, requested: dict) -> bool:
    """Return True when the requested workflow matches the pinned warmup profile."""
    if not profile:
        return True
    mode = profile.get("mode")
    if mode == "checkpoint":
        checkpoint = profile.get("checkpoint", "")
        return bool(checkpoint) and checkpoint in requested.get("checkpoint", [])
    if mode == "split":
        return (
            profile.get("unet", "") in requested.get("unet", [])
            and profile.get("clip1", "") in requested.get("clip", [])
            and profile.get("clip2", "") in requested.get("clip", [])
            and profile.get("vae", "") in requested.get("vae", [])
        )
    return False


def normalize_flux_clip_pair(clip1: str, clip2: str) -> tuple[str, str]:
    """Return ComfyUI's expected FLUX DualCLIPLoader order: clip-l, then T5.

    Current ComfyUI documents DualCLIPLoader ``type='flux'`` as
    ``clip-l, t5``.  Keep already-correct pairs unchanged, but fix common
    reversed env/profile ordering.
    """
    a = clip1.lower()
    b = clip2.lower()
    a_is_t5 = "t5" in a
    b_is_clip_l = "clip_l" in b or "clip-l" in b or "clip-vit" in b
    if a_is_t5 and b_is_clip_l:
        return clip2, clip1
    return clip1, clip2


def list_sageattention_extension_files(site_packages_root: str) -> list[Path]:
    root = Path(site_packages_root) / "sageattention"
    if not root.is_dir():
        return []
    return sorted(root.glob("*.so"))


def choose_sage_runtime_mode(enabled: bool, extension_files: list[Path], import_ok: bool, smoke_ok: bool) -> tuple[str, str]:
    if not enabled:
        return "disabled", "explicitly-disabled"
    if not extension_files:
        return "triton_fallback", "compiled-extensions-missing"
    if not import_ok:
        return "triton_fallback", "compiled-extensions-unusable"
    if not smoke_ok:
        return "triton_fallback", "smoke-test-failed"
    return "baked_cuda", "compiled-extensions-usable"


def patch_kjnodes_get_sage_func(module, baked_cuda_available: bool) -> bool:
    original = getattr(module, "get_sage_func", None)
    fallback = getattr(module, "attention_pytorch", None)
    wrap_attn_fn = getattr(module, "wrap_attn", None)
    if original is None or fallback is None or wrap_attn_fn is None:
        return False

    module._comfy_modal_baked_cuda_available = baked_cuda_available
    if getattr(module, "_comfy_modal_get_sage_func_patched", False):
        return True

    def wrapped_get_sage_func(sage_attention, allow_compile=False):
        if getattr(module, "_comfy_modal_baked_cuda_available", False) or sage_attention == "disabled":
            return original(sage_attention, allow_compile=allow_compile)
        if sage_attention != "auto" and "sageattn" not in str(sage_attention):
            return original(sage_attention, allow_compile=allow_compile)

        @wrap_attn_fn
        def attention_fallback(q, k, v, heads, mask=None, attn_precision=None, skip_reshape=False, skip_output_reshape=False, **kwargs):
            return fallback(
                q,
                k,
                v,
                heads,
                mask=mask,
                attn_precision=attn_precision,
                skip_reshape=skip_reshape,
                skip_output_reshape=skip_output_reshape,
                **kwargs,
            )

        return attention_fallback

    module.get_sage_func = wrapped_get_sage_func
    module._comfy_modal_get_sage_func_patched = True
    return True


def build_replay_warmup_workflow(workflow: dict) -> dict:
    """Create a lightweight warmup from a real successful workflow.

    This preserves the exact loader nodes, clip order/type, UNET dtype, model
    sampling nodes, custom options, and graph topology that already worked for
    the user.  Only generation cost is reduced: samplers run one step and
    generated latent sizes are capped to 512x512.
    """
    import copy

    def is_numeric(value) -> bool:
        return isinstance(value, (int, float)) or (isinstance(value, str) and value.isdigit())

    warmup = copy.deepcopy(workflow)
    for node in warmup.values():
        if not isinstance(node, dict):
            continue
        class_type = node.get("class_type", "")
        inputs = node.get("inputs", {})
        if not isinstance(inputs, dict):
            continue

        # Reduce common sampler fields across built-in and custom samplers.
        # The previous exact-class check missed custom Flux samplers, causing
        # restore warmup to run full 20/30-step generations.
        for key in ("steps", "num_steps", "total_steps", "sampling_steps"):
            if key in inputs and is_numeric(inputs[key]):
                inputs[key] = 1
        if "start_at_step" in inputs and is_numeric(inputs["start_at_step"]):
            inputs["start_at_step"] = 0
        if "end_at_step" in inputs and is_numeric(inputs["end_at_step"]):
            inputs["end_at_step"] = 1

        # Cap any latent/model dimensions in the replay graph. This is warmup,
        # not final output generation, so smaller tensors preserve model-load
        # benefits without paying full inference cost.
        for key in ("width", "height"):
            if key in inputs and is_numeric(inputs[key]):
                inputs[key] = min(int(inputs[key]), 512)
        if "batch_size" in inputs and is_numeric(inputs["batch_size"]):
            inputs["batch_size"] = min(int(inputs["batch_size"]), 1)
        if class_type == "SaveImage" and "filename_prefix" in inputs:
            inputs["filename_prefix"] = "warmup"
    return warmup


def stack_to_profile(stack: dict) -> dict:
    """Convert an extracted model stack into a warmup-profile-compatible dict.

    The warmup profile uses either "checkpoint" mode (single ckpt_name) or
    "split" mode (individual unet/clip1/clip2/vae).  The stack from
    ``extract_requested_model_stack()`` uses lists; we pick the first
    entry from each list.

    If the stack was saved with a ``clip_type`` key (from the actual
    workflow's loader node), that clip_type is preserved.  Otherwise
    defaults to ``"flux"`` for backward compatibility.
    """
    if stack.get("checkpoint"):
        return {"mode": "checkpoint", "checkpoint": stack["checkpoint"][0]}
    if stack.get("unet") and stack.get("clip") and stack.get("vae"):
        clips = stack["clip"]
        clip1, clip2 = normalize_flux_clip_pair(clips[0], clips[-1] if len(clips) > 1 else clips[0])
        # Preserve clip_type from the actual workflow; fall back to "flux"
        _clip_type = stack.get("clip_type", "flux")
        return {
            "mode": "split",
            "unet": stack["unet"][0],
            "clip1": clip1,
            "clip2": clip2,
            "vae": stack["vae"][0],
            "clip_type": _clip_type,
        }
    return {}


# ── PART 8: Runtime model-download policy ──
#   off       — Never download model files during request execution.
#   explicit  — Only download via explicit preinstall/precache functions.
#   dev       — Allow runtime model downloads (current default for dev).
COMFYMODAL_ALLOW_RUNTIME_MODEL_DOWNLOADS = os.getenv("COMFYMODAL_ALLOW_RUNTIME_MODEL_DOWNLOADS", "0") == "1"
COMFYMODAL_MODEL_DOWNLOAD_MODE = os.getenv("COMFYMODAL_MODEL_DOWNLOAD_MODE", "dev").strip().lower()


def _check_runtime_model_download_policy(context: str = "") -> bool:
    """Check whether runtime model downloads are allowed.

    Returns True if downloads are permitted.  Logs a warning if blocked.
    """
    if COMFYMODAL_MODEL_DOWNLOAD_MODE in ("off", "explicit") and not COMFYMODAL_ALLOW_RUNTIME_MODEL_DOWNLOADS:
        context_str = f" ({context})" if context else ""
        print(
            f"[comfyapp] runtime_model_download BLOCKED by policy "
            f"mode={COMFYMODAL_MODEL_DOWNLOAD_MODE}{context_str}"
        )
        return False
    return True


def _verify_model_file(path: str, expected_size: int | None = None, expected_sha256: str | None = None) -> dict:
    """Verify a model file exists and optionally matches size/hash.

    Returns dict with keys: exists, size_ok, sha256_ok, actual_size, actual_sha256.
    """
    result = {"exists": False, "size_ok": None, "sha256_ok": None, "actual_size": None, "actual_sha256": None}
    if not os.path.isfile(path):
        return result
    result["exists"] = True
    try:
        actual_size = os.path.getsize(path)
        result["actual_size"] = actual_size
        if expected_size is not None:
            result["size_ok"] = actual_size == expected_size
    except OSError:
        pass
    if expected_sha256 is not None:
        try:
            actual_sha256 = hashlib.sha256(Path(path).read_bytes()).hexdigest()
            result["actual_sha256"] = actual_sha256
            result["sha256_ok"] = actual_sha256 == expected_sha256
        except OSError:
            pass
    return result


# Bump this version whenever comfyapp.py changes.
# The custom node compares this against the last deployed version
# and re-runs `modal deploy` only when the version changes.
COMFYAPP_VERSION = "2.15.0"

APP_NAME = "comfyui"
VOLUME_NAME = "comfyui-models"
CUSTOM_NODES_VOLUME_NAME = "comfyui-custom-nodes"
COMFYUI_PORT = 8188


def _looks_like_custom_nodes_source_root(path: str) -> bool:
    if not path or not os.path.isdir(path):
        return False
    real = os.path.realpath(path)
    if real in ("/", "/root", "/home", "/mnt", "/tmp", "/usr", "/opt"):
        return False
    try:
        entries = sorted(os.listdir(path))
    except OSError:
        return False
    candidate_count = 0
    for name in entries:
        p = os.path.join(path, name)
        if not os.path.isdir(p) or os.path.islink(p) or name.startswith("."):
            continue
        if os.path.isfile(os.path.join(p, "__init__.py")) or os.path.isfile(os.path.join(p, "requirements.txt")):
            candidate_count += 1
    return candidate_count >= 3


def _resolve_local_custom_nodes_root() -> str:
    explicit = os.getenv("COMFYMODAL_LOCAL_CUSTOM_NODES", "").strip()
    here = os.path.dirname(os.path.abspath(__file__))
    candidates = []
    if explicit:
        candidates.append(explicit)
    candidates.extend([
        os.path.abspath(os.path.join(here, "..")),
        os.path.abspath(os.path.join(here, "..", "custom_nodes")),
        os.path.abspath(os.path.join(here, "..", "ComfyUI", "custom_nodes")),
        "/root/comfy/ComfyUI/custom_nodes",
        os.path.abspath(os.path.join(here, "comfy", "ComfyUI", "custom_nodes")),
    ])
    for candidate in candidates:
        candidate = os.path.abspath(candidate)
        if _looks_like_custom_nodes_source_root(candidate):
            return candidate
    if os.environ.get("COMFYMODAL_RUNTIME") == "1":
        return "/root/comfy/ComfyUI/custom_nodes"
    raise RuntimeError(
        "Could not resolve local custom-node source root. "
        "Set env COMFYMODAL_LOCAL_CUSTOM_NODES to the local directory "
        "that contains your custom node folders (the parent directory "
        "containing 'comfyui-modal' and other custom-node directories). "
        f"Tried: {candidates}"
    )


def _assert_valid_local_custom_nodes_root(path: str) -> None:
    real = os.path.realpath(path)
    if real in ("/", "/root", "/home", "/mnt", "/tmp", "/usr", "/opt"):
        raise RuntimeError(f"Refusing to use unsafe local custom-node root: {real}")
    nodes = _iter_syncable_custom_node_dirs(path)
    if not nodes:
        raise RuntimeError(
            f"Local custom-node root has no syncable nodes: {real} "
            f"(resolve sources tried: {[os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), p)) for p in ['..', '../custom_nodes', '../ComfyUI/custom_nodes']]})"
        )
    suspicious_system_names = {"bin", "boot", "dev", "etc", "lib", "proc", "sys", "usr", "var"}
    if len(set(nodes) & suspicious_system_names) >= 3:
        raise RuntimeError(
            f"Local custom-node root looks like a system root, not custom nodes: {real}; "
            f"nodes={nodes[:30]}"
        )


# Resolved at deploy time to copy local custom nodes into the image.
_COMFYUI_MODAL_DIR = os.path.dirname(os.path.abspath(__file__))
_LOCAL_CUSTOM_NODES = _resolve_local_custom_nodes_root()

# Requirements-only build context so pip-install layers cache independently of
# non-requirements custom node source changes.
_LOCAL_CUSTOM_NODE_REQUIREMENTS_DIR = os.path.join(
    _COMFYUI_MODAL_DIR, ".custom_node_requirements"
)

_CUSTOM_NODE_SYNC_EXCLUDE_DIRS = {".git", "__pycache__", "node_modules", ".venv", "venv", ".ipynb_checkpoints"}
_CUSTOM_NODE_IMAGE_IGNORE_PATTERNS = [
    ".git/",
    "__pycache__/",
    "*.pyc",
    ".venv/",
    "venv/",
    "node_modules/",
]
_COMFYUI_MODAL_IMAGE_IGNORE_PATTERNS = [
    ".gitignore",
    "*.md",
    ".deploy_log",
    ".tmp",
    "*.tmp",
    ".custom_node_requirements/",
    ".hf_token",
    ".civitai_token",
    ".deployed_state.json",
    ".deployed_version",
    ".modal_settings.json",
    "latest_benchmark_workflow.json",
    "modal_logs.txt",
    "_deploy_output.log",
]
_COMBINED_CUSTOM_NODE_IGNORE_PATTERNS = [
    "*/.git/",
    "*/__pycache__/",
    "*/.ipynb_checkpoints/",
    "*/node_modules/",
    "*/.venv/",
    "*/venv/",
    "*.pyc",
    "*.pyo",
    "comfyui-modal/.gitignore",
    "comfyui-modal/.deploy_log",
    "comfyui-modal/.tmp",
    "comfyui-modal/*.tmp",
    "comfyui-modal/*.log",
    "comfyui-modal/modal_logs.txt",
    "comfyui-modal/_deploy_output.log",
    "comfyui-modal/latest_benchmark_workflow.json",
    "comfyui-modal/.hf_token",
    "comfyui-modal/.civitai_token",
    "comfyui-modal/.deployed_state.json",
    "comfyui-modal/.deployed_version",
    "comfyui-modal/.modal_settings.json",
    "comfyui-modal/.last_custom_node_context_manifest.json",
    "comfyui-modal/.custom_node_requirements/",
    "comfyui-modal/.baked_custom_node_deps/",
    "comfyui-modal/*.md",
]
_CUSTOM_NODE_REQUIREMENTS_COPY_IGNORE = shutil.ignore_patterns(
    ".git",
    "__pycache__",
    ".ipynb_checkpoints",
    "*.pyc",
    "*.pyo",
    "node_modules",
    ".venv",
    "venv",
    ".last_context_manifest.json",
    # Image/media/docs — not needed for pip install
    "*.jpg",
    "*.jpeg",
    "*.png",
    "*.gif",
    "*.tiff",
    "*.bmp",
    "*.webp",
    "*.ico",
    "*.mp4",
    "*.avi",
    "*.mov",
    "*.mkv",
    "*.webm",
    "*.ipynb",
    "*.md",
    "*.rst",
    "*.gz",
    "*.zip",
    "*.tar",
)


def _iter_syncable_custom_node_dirs(cn_root: str) -> list[str]:
    """Return sorted, filtered list of top-level custom node directory names.

    Filters:
    - must be a regular directory (not a symlink, not a file)
    - must not start with ``.``
    - must not be in the exclude set (``.git``, ``__pycache__``, …)
    - broken symlinks are excluded (``os.path.isdir`` returns ``False``)
    """
    if not os.path.isdir(cn_root):
        return []
    names = []
    for node_name in sorted(os.listdir(cn_root)):
        node_path = os.path.join(cn_root, node_name)
        if not os.path.isdir(node_path):
            continue
        if os.path.islink(node_path):
            continue
        if node_name.startswith(".") or node_name in _CUSTOM_NODE_SYNC_EXCLUDE_DIRS:
            continue
        names.append(node_name)
    return names


def _custom_node_image_ignore_patterns(node_name: str) -> list[str]:
    patterns = list(_CUSTOM_NODE_IMAGE_IGNORE_PATTERNS)
    if node_name == os.path.basename(_COMFYUI_MODAL_DIR):
        patterns.extend(_COMFYUI_MODAL_IMAGE_IGNORE_PATTERNS)
    return patterns


def _custom_node_requirements_context_dir(node_name: str) -> str:
    return os.path.join(_LOCAL_CUSTOM_NODE_REQUIREMENTS_DIR, node_name)


def _patch_cachedit_node_class(cachedit_cls) -> bool:
    cachedit_func = getattr(cachedit_cls, "FUNCTION", "apply_model_optimization")
    original = getattr(cachedit_cls, cachedit_func, None)
    if original is None:
        return False
    if getattr(original, "_comfy_modal_disabled", False):
        return True

    def _cd_noop(self_node, model, *args, **kwargs):
        print("[cachedit] DISABLED by DISABLE_CACHEDIT_FOR_Z_IMAGE=1 - returning model unchanged")
        return (model,)

    _cd_noop._comfy_modal_disabled = True
    setattr(cachedit_cls, cachedit_func, _cd_noop)
    return True


def _rmtree_robust(path: str) -> None:
    """Remove a directory tree, handling Windows deep-path limitations."""
    try:
        shutil.rmtree(path)
    except OSError:
        if sys.platform == "win32":
            subprocess.run(
                ["powershell.exe", "-Command",
                 f"Remove-Item -Recurse -Force -LiteralPath {path!r}"],
                capture_output=True, timeout=60,
            )
        else:
            raise


def _build_requirements_context_manifest(root: str) -> dict[str, str]:
    manifest = {}
    if not os.path.isdir(root):
        return manifest
    for dirpath, _, filenames in os.walk(root):
        for filename in sorted(filenames):
            path = os.path.join(dirpath, filename)
            rel_path = os.path.relpath(path, root).replace("\\", "/")
            manifest[rel_path] = hashlib.sha256(Path(path).read_bytes()).hexdigest()
    return manifest


LAST_CONTEXT_MANIFEST_FILENAME = ".last_custom_node_context_manifest.json"
_LAST_CONTEXT_MANIFEST_PATH = os.path.join(
    _COMFYUI_MODAL_DIR, LAST_CONTEXT_MANIFEST_FILENAME
)


def _compute_deterministic_context_hash(requirements_dir: str) -> dict:
    if not os.path.isdir(requirements_dir):
        return {
            "context_hash": "", "file_count": 0, "total_bytes": 0,
            "node_dirs": 0, "top_20_largest": [], "file_hashes": {},
        }
    hasher = hashlib.sha256()
    file_hashes = {}
    file_sizes: list[tuple[int, str]] = []
    total_bytes = 0
    node_dirs = set()
    for dirpath, _, filenames in os.walk(requirements_dir):
        rel_dir = os.path.relpath(dirpath, requirements_dir).replace("\\", "/")
        if rel_dir != ".":
            node_dirs.add(rel_dir.split("/")[0])
        for filename in sorted(filenames):
            path = os.path.join(dirpath, filename)
            rel_path = os.path.relpath(path, requirements_dir).replace("\\", "/")
            if rel_path.replace("\\", "/") == LAST_CONTEXT_MANIFEST_FILENAME:
                continue
            try:
                data = Path(path).read_bytes()
            except OSError:
                data = b""
            h = hashlib.sha256(data).hexdigest()
            file_hashes[rel_path] = h
            hasher.update(f"{rel_path}:{h}".encode())
            size = len(data)
            total_bytes += size
            file_sizes.append((size, rel_path))
    file_sizes.sort(reverse=True)
    return {
        "context_hash": hasher.hexdigest(),
        "file_count": len(file_hashes),
        "total_bytes": total_bytes,
        "node_dirs": len(node_dirs),
        "top_20_largest": [{"path": p, "bytes": s} for s, p in file_sizes[:20]],
        "file_hashes": file_hashes,
    }


def _save_last_context_manifest(manifest: dict) -> None:
    try:
        payload = {k: v for k, v in manifest.items() if k != "file_hashes"}
        payload["file_hashes"] = manifest.get("file_hashes", {})
        os.makedirs(os.path.dirname(_LAST_CONTEXT_MANIFEST_PATH), exist_ok=True)
        tmp = _LAST_CONTEXT_MANIFEST_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, sort_keys=True)
        os.replace(tmp, _LAST_CONTEXT_MANIFEST_PATH)
    except Exception as exc:
        print(f"[comfyapp] WARNING: failed to save context manifest: {exc}")


def _load_last_context_manifest() -> dict:
    try:
        if os.path.isfile(_LAST_CONTEXT_MANIFEST_PATH):
            with open(_LAST_CONTEXT_MANIFEST_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
    except (json.JSONDecodeError, OSError) as exc:
        print(f"[comfyapp] WARNING: failed to load context manifest: {exc}")
    return {}


def _diff_context_manifests(current: dict, previous: dict) -> dict:
    cur_hashes = current.get("file_hashes", {})
    prev_hashes = previous.get("file_hashes", {})
    cur_files = set(cur_hashes.keys())
    prev_files = set(prev_hashes.keys())
    added = sorted(cur_files - prev_files)
    removed = sorted(prev_files - cur_files)
    changed = sorted(f for f in cur_files & prev_files if cur_hashes[f] != prev_hashes.get(f))
    changed_nodes = sorted(set(
        f.split("/")[0] for f in changed + added + removed if "/" in f
    ))
    return {
        "added": added,
        "removed": removed,
        "changed": changed,
        "changed_node_names": changed_nodes,
        "added_count": len(added),
        "removed_count": len(removed),
        "changed_count": len(changed),
        "total_changed": len(added) + len(removed) + len(changed),
    }


def _classify_dependency_file(rel_path: str) -> str:
    name = os.path.basename(rel_path)
    if name == "requirements.txt":
        return "requirements.txt"
    if name.startswith("requirements") and name.endswith(".txt"):
        return "requirements/*.txt"
    if name.startswith("constraints") and name.endswith(".txt"):
        return "constraint file"
    if name == "pyproject.toml":
        return "pyproject.toml"
    if name == "setup.py":
        return "setup.py"
    if name == "setup.cfg":
        return "setup.cfg"
    if name == "install.py":
        return "install.py"
    if name.endswith(".whl"):
        return "wheel file"
    if name.endswith(".txt") or name.endswith(".pip"):
        return "requirements/*.txt"
    return "unknown"


def _scan_local_editable_dependencies(source_root: str) -> list[dict]:
    results = []
    for node_name in _iter_syncable_custom_node_dirs(source_root):
        node_path = os.path.join(source_root, node_name)
        for req_file in ("requirements.txt",):
            req_path = os.path.join(node_path, req_file)
            if not os.path.isfile(req_path):
                continue
            try:
                for line in Path(req_path).read_text(encoding="utf-8").splitlines():
                    stripped = line.strip()
                    if not stripped or stripped.startswith("#"):
                        continue
                    stripped = stripped.split(";", 1)[0].strip()
                    if not stripped:
                        continue
                    is_editable = stripped.startswith("-e ") or stripped.startswith("--editable ")
                    is_local_path = stripped.startswith("./") or stripped.startswith("../")
                    if not (is_editable or is_local_path):
                        continue
                    prefix = stripped.split(" ", 1)[1].strip() if is_editable else stripped
                    resolved = os.path.abspath(os.path.join(os.path.dirname(req_path), prefix))
                    file_count = 0
                    total_bytes = 0
                    if os.path.isdir(resolved):
                        for dp, dn, fn in os.walk(resolved):
                            dn[:] = [d for d in dn if d not in (".git", "__pycache__", "node_modules", ".venv", "venv")]
                            file_count += len(fn)
                            for f in fn:
                                try:
                                    total_bytes += os.path.getsize(os.path.join(dp, f))
                                except OSError:
                                    pass
                    elif os.path.isfile(resolved):
                        file_count = 1
                        try:
                            total_bytes = os.path.getsize(resolved)
                        except OSError:
                            pass
                    cache_risk = "high" if (is_editable and ".." in prefix) or file_count > 50 else "medium" if file_count > 10 else "low"
                    results.append({
                        "node_name": node_name,
                        "req_file": f"{node_name}/{req_file}",
                        "raw_line": line.strip(),
                        "resolved_path": resolved,
                        "file_count": file_count,
                        "total_bytes": total_bytes,
                        "cache_risk": cache_risk,
                    })
            except (OSError, UnicodeDecodeError):
                pass
    return results


def _scan_raw_build_files(source_root: str) -> list[dict]:
    RAW_BUILD_FILES = {"pyproject.toml", "setup.py", "setup.cfg", "install.py"}
    results = []
    for node_name in _iter_syncable_custom_node_dirs(source_root):
        node_path = os.path.join(source_root, node_name)
        has_reqs = os.path.isfile(os.path.join(node_path, "requirements.txt"))
        for bf in RAW_BUILD_FILES:
            bf_path = os.path.join(node_path, bf)
            if os.path.isfile(bf_path):
                try:
                    data = Path(bf_path).read_bytes()
                    fhash = hashlib.sha256(data).hexdigest()
                    fsize = len(data)
                except OSError:
                    fhash = ""
                    fsize = 0
                results.append({
                    "node_name": node_name,
                    "file_path": bf,
                    "hash": fhash,
                    "size": fsize,
                    "has_requirements_txt": has_reqs,
                })
    return results


def _diagnose_custom_node_requirements_context(source_root: str, requirements_dir: str, dep_manifest: dict) -> None:
    print("[comfyapp] === Requirements Context Diagnostics ===")
    print(f"[comfyapp] COMFYAPP_VERSION={COMFYAPP_VERSION}")
    print(f"[comfyapp] source_root={source_root}")
    print(f"[comfyapp] requirements_dir={requirements_dir}")

    # Task 7: Cache killer flags
    modal_force_build = os.environ.get("MODAL_FORCE_BUILD", "")
    modal_ignore_cache = os.environ.get("MODAL_IGNORE_CACHE", "")
    force_build_env = os.environ.get("FORCE_BUILD", "")
    print(f"[comfyapp] MODAL_FORCE_BUILD={modal_force_build!r}")
    print(f"[comfyapp] MODAL_IGNORE_CACHE={modal_ignore_cache!r}")
    print(f"[comfyapp] FORCE_BUILD={force_build_env!r}")

    _scan_ignore_dirs = {".git", "__pycache__", ".venv", "venv", "node_modules", ".ipynb_checkpoints", ".custom_node_requirements"}
    _node_sizes: list[tuple[int, str]] = []
    for _n in _iter_syncable_custom_node_dirs(source_root):
        _p = os.path.join(source_root, _n)
        _sz = 0
        try:
            for _dp, _dn, _fn in os.walk(_p):
                _dn[:] = [d for d in _dn if d not in _scan_ignore_dirs]
                _sz += sum(os.path.getsize(os.path.join(_dp, f)) for f in _fn if not f.endswith((".pyc", ".pyo")))
        except OSError:
            pass
        _node_sizes.append((_sz, _n))
    _node_sizes.sort(reverse=True)
    print(f"[comfyapp] source_copy_node_count={len(_node_sizes)}")
    print(f"[comfyapp] source_copy_top_20_largest_nodes (best-effort bytes after ignore):")
    for _sz, _n in _node_sizes[:20]:
        print(f"  {_n}: {_sz} bytes ({round(_sz/1024/1024, 1)} MB)")

    current = _compute_deterministic_context_hash(requirements_dir)
    previous = _load_last_context_manifest()
    dep_hash = dep_manifest.get("overall_dependency_hash", "") if dep_manifest else ""

    print(f"[comfyapp] custom_node_requirements_context_hash={current['context_hash'][:16] if current['context_hash'] else '<empty>'}...")
    print(f"[comfyapp] requirements_context_file_count={current['file_count']}")
    print(f"[comfyapp] requirements_context_total_bytes={current['total_bytes']}")
    print(f"[comfyapp] requirements_context_node_dirs={current['node_dirs']}")
    if current["top_20_largest"]:
        print(f"[comfyapp] requirements_context_top_20_largest:")
        for entry in current["top_20_largest"]:
            print(f"  {entry['path']}: {entry['bytes']} bytes")
    print(f"[comfyapp] dependency_manifest_hash={dep_hash[:16] if dep_hash else '<none>'}...")

    # Task 2: Context diff
    if previous.get("context_hash"):
        diff = _diff_context_manifests(current, previous)
        if diff["total_changed"] == 0:
            print(f"[comfyapp] requirements_context_unchanged=1")
        else:
            print(f"[comfyapp] requirements_context_changed=1 total_changed={diff['total_changed']}")
            print(f"[comfyapp]   added_files={diff['added']}")
            print(f"[comfyapp]   removed_files={diff['removed']}")
            print(f"[comfyapp]   changed_files={diff['changed']}")
            print(f"[comfyapp]   changed_node_names={diff['changed_node_names']}")

            # Task 3: Classify changed files
            all_changed = diff["added"] + diff["removed"] + diff["changed"]
            classified: dict[str, list[str]] = {}
            for f in all_changed:
                cls = _classify_dependency_file(f)
                classified.setdefault(cls, []).append(f)
            print(f"[comfyapp] changed_files_by_type:")
            for cls, files in sorted(classified.items()):
                print(f"  {cls}: {files}")

            dep_only_changed = all(
                _classify_dependency_file(f) != "unknown" for f in all_changed
            )
            if not dep_only_changed:
                print(f"[comfyapp] WARNING: dependency context changed even though no dependency files should have changed")
    else:
        print(f"[comfyapp] requirements_context_first_deploy=1 (no previous manifest)")

    # Task 4: Local editable/path dependencies
    local_deps = _scan_local_editable_dependencies(source_root)
    if local_deps:
        print(f"[comfyapp] local_editable_path_dependencies ({len(local_deps)}):")
        for dep in local_deps:
            print(f"  node={dep['node_name']} req={dep['req_file']} "
                  f"line={dep['raw_line']} "
                  f"files={dep['file_count']} bytes={dep['total_bytes']} "
                  f"cache_risk={dep['cache_risk']}")

    # Task 5: Raw setup/pyproject/setup.cfg/install.py
    raw_build = _scan_raw_build_files(source_root)
    if raw_build:
        print(f"[comfyapp] raw_build_file_contributors ({len(raw_build)}):")
        for entry in raw_build:
            print(f"  node={entry['node_name']} file={entry['file_path']} "
                  f"hash={entry['hash'][:16]} size={entry['size']} "
                  f"has_reqtxt={entry['has_requirements_txt']}")

    # Task 8: Verify actual build order
    _node_names = _iter_syncable_custom_node_dirs(source_root)
    print(f"[comfyapp] custom_node_copy_mode={CUSTOM_NODE_COPY_MODE}")
    print(f"[comfyapp] syncable_custom_nodes={len(_node_names)}")
    _combined_layers = 1 if CUSTOM_NODE_COPY_MODE == "combined" else len(_node_names)
    print(f"[comfyapp] source_copy_layers={_combined_layers}")
    print(f"[comfyapp] local_custom_node_root={source_root}")
    combined_excluded_ok = (
        os.path.isdir(os.path.join(requirements_dir, "..", "comfyui-modal", ".custom_node_requirements"))
        if CUSTOM_NODE_COPY_MODE == "combined" else True
    )
    print(f"[comfyapp] comfyui_modal_excluded_custom_node_requirements={'yes' if combined_excluded_ok else 'check_logs'}")
    print(f"[comfyapp] comfyui_modal_excluded_baked_custom_node_deps={'yes' if combined_excluded_ok else 'check_logs'}")
    print(f"[comfyapp] build_order:")
    print(f"  1. base CUDA image (nvidia/cuda:13.0.0-devel-ubuntu24.04)")
    print(f"  2. comfy-cli install")
    print(f"  3. PyTorch CUDA reinstall (cu130)")
    print(f"  4. triton install")
    print(f"  5. SageAttention build")
    print(f"  6. env vars")
    print(f"  7. add .custom_node_requirements (as local_dir)")
    print(f"  8. run custom-node prereq pip loop")
    print(f"  9. add custom-node source (mode={CUSTOM_NODE_COPY_MODE}, layers={_combined_layers})")
    print(f"  10. generate/add baked dependency manifest")
    print(f"  11. add helper Python sources")
    print(f"[comfyapp] ===========================================")

    _save_last_context_manifest(current)


def _safe_dependency_relpath(filepath: str, node_root: str) -> str:
    """Return a POSIX-style relative path from *node_root* to *filepath*.

    Raises ``RuntimeError`` if *filepath* is outside *node_root* or contains
    path traversal (``../``).  External local editable/path dependencies are
    not supported for the cached build context.
    """
    resolved_file = os.path.realpath(filepath)
    resolved_root = os.path.realpath(node_root)
    try:
        common = os.path.commonpath([resolved_file, resolved_root])
    except ValueError:
        raise RuntimeError(
            f"Local dependency path is outside custom node root and is not "
            f"supported for cached build context: {filepath} relative to "
            f"{node_root}. Move the dependency inside the custom node folder "
            f"or package it as a wheel."
        )
    if common != resolved_root:
        raise RuntimeError(
            f"Local dependency path is outside custom node root and is not "
            f"supported for cached build context: {filepath} relative to "
            f"{node_root}. Move the dependency inside the custom node folder "
            f"or package it as a wheel."
        )
    rel = os.path.relpath(resolved_file, resolved_root).replace("\\", "/")
    if rel.startswith("/"):
        raise RuntimeError(
            f"Path {rel} is absolute after resolution. "
            f"Move the dependency inside {node_root}."
        )
    parts = rel.split("/")
    if any(part == ".." for part in parts):
        raise RuntimeError(
            f"Path {rel} escapes the custom node root and is not supported. "
            f"Move the dependency inside {node_root}."
        )
    return rel


# _copy_requirement_reference_tree was intentionally removed.
# All dependency copying uses collect_custom_node_dependency_files +
# _sync_custom_node_dependency_files, which is the single source of truth.


def _sync_custom_node_dependency_files(node_path: str, dst_node_dir: str) -> None:
    """Sync dependency files from *node_path* to *dst_node_dir*.

    Copies the exact set of files returned by
    ``collect_custom_node_dependency_files``.  Only overwrites the target
    when file content actually differs.
    """
    dep_files = collect_custom_node_dependency_files(node_path)
    if not dep_files:
        return
    with tempfile.TemporaryDirectory() as temp_root:
        staged_dir = os.path.join(temp_root, os.path.basename(dst_node_dir))
        os.makedirs(staged_dir, exist_ok=True)
        for rel_path in dep_files:
            # Normalize separators before any safety check
            normalized_rel = rel_path.replace("\\", "/")
            if normalized_rel.startswith("/") or any(part == ".." for part in normalized_rel.split("/")):
                raise RuntimeError(
                    f"Unsafe dependency path key in manifest: {rel_path!r}. "
                    f"This indicates a corrupted or malicious manifest. "
                    f"Skipping copy for {node_path}."
                )
            src = os.path.join(node_path, normalized_rel.replace("/", os.sep))
            if not os.path.isfile(src):
                continue
            # Defense-in-depth: verify src stays within node_path
            src_real = os.path.realpath(src)
            node_root_real = os.path.realpath(node_path)
            try:
                src_common = os.path.commonpath([node_root_real, src_real])
            except ValueError:
                raise RuntimeError(
                    f"Source dependency {rel_path} is on a different drive than "
                    f"{node_path}. Aborting copy."
                )
            if src_common != node_root_real:
                raise RuntimeError(
                    f"Source dependency {rel_path} is outside {node_path}. "
                    f"Aborting copy."
                )
            dst = os.path.join(staged_dir, normalized_rel.replace("/", os.sep))
            dst_real = os.path.realpath(dst)
            staged_real = os.path.realpath(staged_dir)
            try:
                dst_common = os.path.commonpath([staged_real, dst_real])
            except ValueError:
                raise RuntimeError(
                    f"Dependency path {rel_path} resolves to a different drive "
                    f"than staging. Aborting copy."
                )
            if dst_common != staged_real:
                raise RuntimeError(
                    f"Dependency path {rel_path} would copy outside staged "
                    f"directory. Aborting copy for {node_path}."
                )
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copy2(src, dst)
        if _build_requirements_context_manifest(staged_dir) == _build_requirements_context_manifest(dst_node_dir):
            return
        if os.path.isdir(dst_node_dir):
            _rmtree_robust(dst_node_dir)
        shutil.copytree(staged_dir, dst_node_dir)


def _prepare_custom_node_requirements_build_context(source_root: str, target_root: str) -> None:
    """Copy dependency files from each custom node into target_root.

    Uses ``collect_custom_node_dependency_files`` as the single source of
    truth (same scanner used by ``build_custom_node_dependency_manifest``).
    Copies only dependency-relevant files (requirements.txt, pyproject.toml,
    setup.py, setup.cfg, -r/-c references, local editable deps).

    The resulting tree is used as a separate ``add_local_dir`` build context
    so that Docker layer caching busts the pip-install step when any
    dependency-relevant file changes.
    """
    os.makedirs(target_root, exist_ok=True)
    desired_nodes = set()
    for node_name in _iter_syncable_custom_node_dirs(source_root):
        node_path = os.path.join(source_root, node_name)
        dep_files = collect_custom_node_dependency_files(node_path)
        if not dep_files:
            continue
        desired_nodes.add(node_name)
        _sync_custom_node_dependency_files(
            node_path,
            os.path.join(target_root, node_name),
        )

    for entry in os.listdir(target_root):
        entry_path = os.path.join(target_root, entry)
        if os.path.isdir(entry_path) and entry not in desired_nodes:
            _rmtree_robust(entry_path)


_assert_valid_local_custom_nodes_root(_LOCAL_CUSTOM_NODES)
_prepare_custom_node_requirements_build_context(
    _LOCAL_CUSTOM_NODES, _LOCAL_CUSTOM_NODE_REQUIREMENTS_DIR
)
COMFYUI_API_PORT = 8189
MODELS_PATH = "/root/models"
CUSTOM_NODES_PATH = "/root/custom_nodes_vol"
LAST_MODEL_STACK_PATH = "/root/models/.last_model_stack.json"
ACTIVE_NEXT_PROFILE_PATH = "/root/models/runtime_config/active_next_profile.json"
ACTIVE_NEXT_PROFILE_TTL_S = 60
LAST_WARMUP_WORKFLOW_PATH = "/root/models/.last_warmup_workflow.json"
SAGE_RUNTIME_CACHE_PATH = "/root/models/.sage_runtime_cache.json"

SUPPORTED_GPUS = get_supported_gpus()

GPU_PROFILES = {
    "budget": {"cpu": 2, "memory": 8192, "target_inputs": 1, "max_inputs": 1},
    "standard": {"cpu": 4, "memory": 32768, "target_inputs": 1, "max_inputs": 1},
    "high_mem": {"cpu": 4, "memory": 32768, "target_inputs": 1, "max_inputs": 1},
}

SAGEATTENTION_GIT_REF = "v2.2.0"
SAGEATTENTION_SITE_PACKAGES = "/usr/local/lib/python3.11/site-packages"



_image_base = (
    modal.Image.from_registry(
        "nvidia/cuda:13.0.0-devel-ubuntu24.04",
        add_python="3.11",
    )
    .entrypoint([])
    .apt_install(
        "git",
        "libgl1",
        "libglib2.0-0",
        "libsm6",
        "libxrender1",
        "libxext6",
        "ffmpeg",
        "build-essential",
        "ninja-build",
        # CUDA 13.0 on Ubuntu 24.04 supports both GCC 13 (default) and clang
        # as host compilers for nvcc.  We install clang as a reliable fallback
        # since the nvidia/cuda:13.0.0-devel-ubuntu24.04 image may not ship a
        # full GCC toolchain.
        "clang",
    )
    .pip_install("comfy-cli==1.3.7", "httpx>=0.27.0")
    .run_commands(
        "comfy --skip-prompt install --nvidia",
        gpu="a10g",
    )
    # Force CUDA 13.0 PyTorch after comfy install (which may install older CUDA build)
    .run_commands(
        "python -m pip install --upgrade --force-reinstall "
        "torch torchvision torchaudio "
        "--index-url https://download.pytorch.org/whl/cu130",
        gpu="a10g",
    )
    # Triton >= 3.0 required for SageAttention2 on Blackwell
    .run_commands(
        "python -m pip install --upgrade 'triton>=3.0.0'",
    )
    .run_commands(
        "CUDA_HOME=/usr/local/cuda TORCH_CUDA_ARCH_LIST=12.0+PTX MAX_JOBS=4 "
        "python -m pip install --upgrade --force-reinstall "
        "git+https://github.com/thu-ml/SageAttention.git@v2.2.0 "
        "--no-build-isolation --no-deps",
        gpu="a10g",
    )
    .run_commands(
        "python -X utf8 -c \"import pathlib, site; "
        "site_root = next((p for p in site.getsitepackages() if 'site-packages' in p), site.getsitepackages()[0]); "
        "files = list(pathlib.Path(site_root).joinpath('sageattention').glob('*.so')); "
        "print([f.name for f in files]); "
        "assert files, 'no sageattention shared objects built'\"",
        gpu="a10g",
    )
    .run_commands(
        "python -X utf8 -c \"import sageattention._fused; print('sageattention._fused ok')\"",
        gpu="a10g",
    )
    .env(
        {
            "TORCHINDUCTOR_CACHE_DIR": "/root/models/.inductor-cache",
            "TORCHINDUCTOR_FX_GRAPH_CACHE": "1",
            "TRITON_CACHE_DIR": "/tmp/triton_cache",
            "TORCHINDUCTOR_EMULATE_PRECISION_CASTS": "1",
            "TORCHINDUCTOR_COMPILE_THREADS": "1",
            "COMFYMODAL_ENABLE_TORCH_COMPILE": "0",
            "COMFYMODAL_ENABLE_GPU_SNAPSHOT": "0",
            "COMFYMODAL_WARMUP_TEXT": "warmup",
            # Restore latency fix — default production profile (Config D)
            "COMFYMODAL_SAGE_RUNTIME_MODE": "baked_cuda",
            "COMFYMODAL_SAGE_RUNTIME_PROBE_ON_RESTORE": "0",
            "COMFYMODAL_DIRECT_WARMUP_LOAD_UNET": "0",
            "COMFYMODAL_DIRECT_WARMUP_LOAD_CLIP": "0",
            "COMFYMODAL_DIRECT_WARMUP_CLIP_ENCODE": "0",
            "COMFYMODAL_DIRECT_WARMUP_REQUIRE_CPU_CACHE_HIT": "1",
            "COMFYMODAL_RUNTIME": "1",
            "PROMPT_ASYNC_PRELOAD": "0",
            "PROMPT_PRELOAD_WORKERS": "2",
            "PROMPT_ASYNC_ACTUAL_LOAD": "1",
            "PROMPT_ASYNC_ACTUAL_LOAD_UNET": "1",
            "ACTUAL_LOAD_MODE": "unet_vae_only",
            "DISABLE_CACHEDIT_FOR_Z_IMAGE": "0",
            "DISABLE_RESTORE_WARMUP_FOR_Z_IMAGE": "1",
            # Production guardrails (PART 3, 4, 7)
            "COMFYMODAL_REQUIREMENTS_REPAIR_MODE": "fail_fast",
            "COMFYMODAL_PRELOAD_UNKNOWN_PROFILES": "0",
            "COMFYMODAL_PRELOAD_MAX_TOTAL_GB": "12",
            "COMFYMODAL_PRELOAD_MAX_FILE_GB": "10",
            "COMFYMODAL_PRELOAD_MIN_THROUGHPUT_GBPS": "0.5",
            "COMFYMODAL_PRELOAD_OUTLIER_ABORT_SECONDS": "10",
            "COMFYMODAL_ENABLE_REMOTE_BACKGROUND_DEPLOY": "0",
        }
    )
)

# Combined requirements layer: one COPY + one pip loop (single cache unit).
# When no requirements.txt changes, the layer is cached (~5s deploy).
# Changed requirements cause all pip installs to re-run within this layer.
_image_base = _image_base.add_local_dir(
    _LOCAL_CUSTOM_NODE_REQUIREMENTS_DIR,
    "/root/comfy-build/custom_node_requirements",
    copy=True,
).run_commands(
    '__ts_ms() { python3 -c "import time; print(int(time.time()*1000))"; }; '
    'echo "CUSTOM_NODE_PREREQ_INSTALL_START ts_ms=$(__ts_ms)"; '
    '_total_req=0; _total_installed=0; _total_skipped=0; '
    '_pip_node() { local d="$1"; '
    '  local name; name=$(basename "$d"); '
    '  [ -f "$d/requirements.txt" ] || { _total_skipped=$((_total_skipped+1)); return 0; }; '
    '  _total_req=$((_total_req+1)); '
    '  local t0; t0=$(__ts_ms); '
    '  echo "CUSTOM_NODE_PREREQ_INSTALL_NODE name=$name start_ts=$t0"; '
    '  cd "$d" && pip install -r requirements.txt --quiet; '
    '  local t1; t1=$(__ts_ms); '
    '  local dur; dur=$((t1 - t0)); '
    '  echo "CUSTOM_NODE_PREREQ_INSTALL_NODE name=$name end_ts=$t1 duration_ms=$dur"; '
    '  _total_installed=$((_total_installed+1)); '
    '}; '
    'for d in /root/comfy-build/custom_node_requirements/*/; do '
    '  _pip_node "$d"; '
    'done; '
    '_end_ts=$(__ts_ms); '
    'echo "CUSTOM_NODE_PREREQ_INSTALL_END ts_ms=$_end_ts total_nodes=$_total_req installed=$_total_installed skipped_no_req=$_total_skipped"'
)

# ── PART 3b: Custom-node source copy (combined or per-node) ──
_syncable_node_names = _iter_syncable_custom_node_dirs(_LOCAL_CUSTOM_NODES)
_cn_copy_layer_count = 0
if CUSTOM_NODE_COPY_MODE == "combined":
    _image_base = _image_base.add_local_dir(
        _LOCAL_CUSTOM_NODES,
        "/root/comfy/ComfyUI/custom_nodes",
        copy=True,
        ignore=_COMBINED_CUSTOM_NODE_IGNORE_PATTERNS,
    )
    _cn_copy_layer_count = 1
    print(f"[comfyapp] custom_node_copy_mode=combined nodes={len(_syncable_node_names)} layers=1 "
          f"src={_LOCAL_CUSTOM_NODES} dst=/root/comfy/ComfyUI/custom_nodes")
else:
    for _node_name in _syncable_node_names:
        _node_src = os.path.join(_LOCAL_CUSTOM_NODES, _node_name)
        _image_base = _image_base.add_local_dir(
            _node_src,
            f"/root/comfy/ComfyUI/custom_nodes/{_node_name}",
            copy=True,
            ignore=_custom_node_image_ignore_patterns(_node_name),
        )
    _cn_copy_layer_count = len(_syncable_node_names)
    print(f"[comfyapp] custom_node_copy_mode=per_node nodes={len(_syncable_node_names)} layers={_cn_copy_layer_count}")

# ── PART 4: Generate baked dependency manifest and copy into image ──
_BAKED_MANIFEST_DIR = os.path.join(_COMFYUI_MODAL_DIR, ".baked_custom_node_deps")
os.makedirs(_BAKED_MANIFEST_DIR, exist_ok=True)
_BAKED_MANIFEST_TEMP = os.path.join(_BAKED_MANIFEST_DIR, "custom_node_deps_baked.json")
try:
    _baked_manifest = build_custom_node_dependency_manifest(_LOCAL_CUSTOM_NODES)
    with open(_BAKED_MANIFEST_TEMP, "w", encoding="utf-8") as _f:
        json.dump(_baked_manifest, _f, indent=2, sort_keys=True)
    _baked_nodes = _baked_manifest.get("nodes", {})
    _baked_node_names = sorted(_baked_nodes.keys())
    _baked_node_count = len(_baked_node_names)
    _baked_with_deps = sum(1 for n in _baked_nodes.values() if n.get("dependency_files"))
    _baked_dep_nodes = sorted([n for n in _baked_nodes if _baked_nodes[n].get("dependency_files")])
    _staged_reqs = _LOCAL_CUSTOM_NODE_REQUIREMENTS_DIR
    _staged_count = len(os.listdir(_staged_reqs)) if os.path.isdir(_staged_reqs) else 0
    print(f"[comfyapp] build-context: comfyapp_dir={_COMFYUI_MODAL_DIR}")
    print(f"[comfyapp] build-context: local_source={_LOCAL_CUSTOM_NODES}")
    print(f"[comfyapp] build-context: local_syncable_nodes={_baked_node_count} "
          f"nodes_with_dep_files={_baked_with_deps}")
    if _baked_node_names:
        _truncated = _baked_node_names[:50]
        print(f"[comfyapp] build-context: local_node_names={_truncated}"
              f"{'...' if len(_baked_node_names) > 50 else ''}")
    if _baked_dep_nodes:
        _deps_truncated = _baked_dep_nodes[:30]
        print(f"[comfyapp] build-context: nodes_with_dep_files={len(_baked_dep_nodes)} "
              f"dep_nodes={_deps_truncated}"
              f"{'...' if len(_baked_dep_nodes) > 30 else ''}")
    print(f"[comfyapp] build-context: staged_requirements={_staged_reqs} staged_nodes={_staged_count}")
    print(f"[comfyapp] baked manifest generated: nodes={_baked_node_count} "
          f"deps_nodes={len(_baked_dep_nodes)} "
          f"hash={_baked_manifest.get('overall_dependency_hash', '')[:16]}...")
except Exception as _bake_exc:
    print(f"[comfyapp] WARNING: baked manifest generation failed: {_bake_exc}")
    # Write empty manifest so the file exists in the image
    with open(_BAKED_MANIFEST_TEMP, "w", encoding="utf-8") as _f:
        json.dump({"schema_version": 1, "nodes": {}, "overall_dependency_hash": ""}, _f)

# ── Dependency build-context diagnostics ──
_baked_manifest_for_diag = locals().get("_baked_manifest", {})
if not _baked_manifest_for_diag:
    try:
        if os.path.isfile(_BAKED_MANIFEST_TEMP):
            with open(_BAKED_MANIFEST_TEMP, "r", encoding="utf-8") as _f:
                _baked_manifest_for_diag = json.load(_f)
    except Exception:
        pass
_diagnose_custom_node_requirements_context(
    _LOCAL_CUSTOM_NODES, _LOCAL_CUSTOM_NODE_REQUIREMENTS_DIR, _baked_manifest_for_diag
)

_image_base = _image_base.add_local_file(
    _BAKED_MANIFEST_TEMP,
    "/opt/comfymodal/custom_node_deps_baked.json",
    copy=True,
)

_COMFYMODAL_LOCAL_PYTHON_SOURCES = (
    "gpu_catalog",
    "timing_trace",
    "api_prompt_validator",
    "failure_summary",
)

def _add_comfymodal_local_python_sources(img):
    for _module_name in _COMFYMODAL_LOCAL_PYTHON_SOURCES:
        img = img.add_local_python_source(_module_name)
    return img

image = _add_comfymodal_local_python_sources(_image_base)

download_image = _add_comfymodal_local_python_sources(
    modal.Image.debian_slim(python_version="3.11")
    .pip_install("httpx>=0.27.0")
)

app = modal.App(APP_NAME, image=image)
vol = modal.Volume.from_name(VOLUME_NAME, create_if_missing=True)
custom_nodes_vol = modal.Volume.from_name(CUSTOM_NODES_VOLUME_NAME, create_if_missing=True)


@app.function(
    image=download_image,
    cpu=2,
    memory=512,
    timeout=1800,
    volumes={MODELS_PATH: vol},
)
def download_model_to_volume(url: str, filename: str, save_path: str = "checkpoints", hf_token: str = "", civitai_token: str = ""):
    import httpx
    from pathlib import Path

    dest = Path(MODELS_PATH) / save_path / filename
    dest.parent.mkdir(parents=True, exist_ok=True)

    if dest.exists():
        return {"status": "ok", "skipped": True, "path": str(dest)}

    headers = {}
    if hf_token and "huggingface.co" in url:
        headers["Authorization"] = f"Bearer {hf_token}"
    if civitai_token and ("civitai" in url or "civitai.red" in url):
        headers["Authorization"] = f"Bearer {civitai_token}"

    # Atomic download: write to .part file, then rename on success
    _part = dest.parent / f"{filename}.part"
    if _part.exists():
        _part.unlink()
    total = 0
    downloaded = 0
    with httpx.stream("GET", url, headers=headers, follow_redirects=True, timeout=1800) as r:
        r.raise_for_status()
        total = int(r.headers.get("content-length", 0))
        downloaded = 0
        with open(_part, "wb") as f:
            for chunk in r.iter_bytes(chunk_size=1048576):
                f.write(chunk)
                downloaded += len(chunk)
                if total:
                    pct = downloaded / total * 100
                    sys.stdout.write(f"\r  {pct:.1f}%  ({downloaded // 1024**2} MB / {total // 1024**2} MB)")
                    sys.stdout.flush()

    if total and downloaded != total:
        _part.unlink(missing_ok=True)
        raise RuntimeError(f"Download size mismatch: expected {total} bytes, got {downloaded} bytes")

    os.replace(str(_part), str(dest))
    vol.commit()
    return {"status": "ok", "path": str(dest)}


@app.function(
    image=download_image,
    cpu=2,
    memory=512,
    timeout=1800,
    volumes={MODELS_PATH: vol},
)
def download_model_stream(url: str, filename: str, save_path: str = "checkpoints", hf_token: str = "", civitai_token: str = ""):
    import httpx
    from pathlib import Path

    dest = Path(MODELS_PATH) / save_path / filename
    dest.parent.mkdir(parents=True, exist_ok=True)

    if dest.exists():
        yield {"type": "complete", "status": "ok", "skipped": True, "path": str(dest), "filename": filename}
        return

    headers = {}
    if hf_token and "huggingface.co" in url:
        headers["Authorization"] = f"Bearer {hf_token}"
    if civitai_token and ("civitai" in url or "civitai.red" in url):
        headers["Authorization"] = f"Bearer {civitai_token}"

    _part = dest.parent / f"{filename}.part"
    if _part.exists():
        _part.unlink()
    total = 0
    downloaded = 0
    with httpx.stream("GET", url, headers=headers, follow_redirects=True, timeout=1800) as r:
        r.raise_for_status()
        total = int(r.headers.get("content-length", 0))
        downloaded = 0
        with open(_part, "wb") as f:
            for chunk in r.iter_bytes(chunk_size=1048576):
                f.write(chunk)
                downloaded += len(chunk)
                if total:
                    pct = downloaded / total * 100
                    yield {
                        "type": "progress",
                        "pct": round(pct, 1),
                        "downloaded_mb": downloaded // 1024**2,
                        "total_mb": total // 1024**2,
                        "filename": filename,
                        "save_path": save_path,
                    }

    if total and downloaded != total:
        _part.unlink(missing_ok=True)
        yield {"type": "error", "message": f"Download size mismatch: expected {total} bytes, got {downloaded} bytes", "filename": filename}
        return

    os.replace(str(_part), str(dest))
    vol.commit()
    yield {"type": "complete", "status": "ok", "path": str(dest), "filename": filename}


@app.function(
    image=download_image,
    cpu=2,
    memory=512,
    timeout=1800,
    volumes={MODELS_PATH: vol},
)
def batch_download_models(items: list, hf_token: str = "", civitai_token: str = "") -> list:
    starmap_args = []
    for item in items:
        args = [item["url"], item["filename"], item.get("save_path", "checkpoints"), hf_token]
        if civitai_token:
            args.append(civitai_token)
        starmap_args.append(tuple(args))
    results = list(download_model_to_volume.starmap(starmap_args))
    return results


def _safe_remove_path(path: str) -> None:
    """Remove a filesystem entry safely (symlink, dir, file, or missing)."""
    if os.path.islink(path):
        os.unlink(path)
    elif os.path.isdir(path):
        shutil.rmtree(path)
    elif os.path.exists(path):
        os.remove(path)


def _validate_safe_tar_member(member, staging_dir: str) -> None:
    """Validate a tar member is safe to extract.

    Rejects:
    - absolute paths, parent references (``..``)
    - empty/root target (``""``, ``"."``)
    - symlinks, hardlinks, devices, FIFOs, and other specials
    - members whose resolved path escapes *staging_dir*

    Uses ``os.path.commonpath`` for containment rather than string
    prefix checks to avoid path-component sibling attacks.
    """
    name = member.name or ""
    normalized = name.replace("\\", "/")
    parts = [p for p in normalized.split("/") if p not in ("", ".")]
    if not parts:
        raise ValueError(
            f"Tar member {member.name!r} is empty or targets archive root — not allowed"
        )
    if name.startswith("/") or normalized.startswith("/") or any(part == ".." for part in parts):
        raise ValueError(f"Tar member '{member.name}' contains unsafe path")
    if member.issym() or member.islnk():
        raise ValueError(
            f"Tar member '{member.name}' is a symlink/hardlink — not allowed"
        )
    if member.isdev() or member.ischr() or member.isblk() or member.isfifo():
        raise ValueError(f"Tar member '{member.name}' is a special file type — not allowed")
    if not (member.isfile() or member.isdir()):
        raise ValueError(f"Tar member '{member.name}' is an unsupported file type")
    staging_real = os.path.realpath(staging_dir)
    dest_real = os.path.realpath(os.path.join(staging_real, *parts))
    try:
        common = os.path.commonpath([staging_real, dest_real])
    except ValueError:
        raise ValueError(f"Tar member '{member.name}' would extract outside target directory")
    if common != staging_real:
        raise ValueError(f"Tar member '{member.name}' would extract outside target directory")


@app.function(
    image=_add_comfymodal_local_python_sources(
        modal.Image.debian_slim(python_version="3.11")
    ),
    cpu=2,
    memory=4096,
    timeout=1800,
    volumes={CUSTOM_NODES_PATH: custom_nodes_vol},
)
def sync_custom_nodes_to_volume(archive_data: bytes) -> dict:
    """Receive a tar.gz archive of custom nodes and extract to volume."""
    import tarfile
    import io
    import os
    import shutil

    staging_dir = os.path.join(CUSTOM_NODES_PATH, ".staging")

    # Clean any leftover staging dir (safe regardless of type)
    _safe_remove_path(staging_dir)
    os.makedirs(staging_dir)

    # Extract to staging with path traversal and symlink protection.
    # NOTE: old content is NOT removed until the new archive has been
    # fully validated AND extracted into staging.
    try:
        buf = io.BytesIO(archive_data)
        with tarfile.open(fileobj=buf, mode="r:gz") as tar:
            # Validate all members before any extraction
            for member in tar.getmembers():
                _validate_safe_tar_member(member, staging_dir)
            buf.seek(0)
            with tarfile.open(fileobj=buf, mode="r:gz") as tar2:
                for member in tar2.getmembers():
                    _validate_safe_tar_member(member, staging_dir)
                    tar2.extract(member, path=staging_dir)
    except Exception:
        _safe_remove_path(staging_dir)
        raise

    # ── Old content removal (only after new archive is in staging) ──
    _staging_name = os.path.basename(staging_dir)
    for item in os.listdir(CUSTOM_NODES_PATH):
        if item == _staging_name:
            continue
        item_path = os.path.join(CUSTOM_NODES_PATH, item)
        if os.path.islink(item_path):
            os.unlink(item_path)
        elif os.path.isdir(item_path):
            shutil.rmtree(item_path)
        else:
            os.remove(item_path)

    # Move extracted items from staging to volume root
    for item in os.listdir(staging_dir):
        src = os.path.join(staging_dir, item)
        dst = os.path.join(CUSTOM_NODES_PATH, item)
        shutil.move(src, dst)

    # Clean up staging
    _safe_remove_path(staging_dir)

    custom_nodes_vol.commit()

    # Return runtime-syncable nodes (not artifacts)
    nodes = _iter_syncable_custom_node_dirs(CUSTOM_NODES_PATH)
    raw_dirs = sorted(
        d for d in os.listdir(CUSTOM_NODES_PATH)
        if os.path.isdir(os.path.join(CUSTOM_NODES_PATH, d))
    ) if os.path.isdir(CUSTOM_NODES_PATH) else []
    print(f"[comfyapp] sync_custom_nodes_to_volume extracted syncable_nodes={len(nodes)} raw_dirs={len(raw_dirs)}")
    return {"status": "ok", "nodes": nodes, "raw_dirs": raw_dirs}


@app.function(
    image=_add_comfymodal_local_python_sources(
        modal.Image.debian_slim(python_version="3.11")
    ),
    cpu=1,
    memory=512,
    timeout=60,
    volumes={MODELS_PATH: vol, CUSTOM_NODES_PATH: custom_nodes_vol},
)
def get_volume_status() -> dict:
    """Return current state of both volumes."""
    import os

    vol.reload()
    custom_nodes_vol.reload()

    # Scan models
    models = []
    if os.path.isdir(MODELS_PATH):
        for folder in os.listdir(MODELS_PATH):
            folder_path = os.path.join(MODELS_PATH, folder)
            if not os.path.isdir(folder_path):
                continue
            for fname in os.listdir(folder_path):
                fpath = os.path.join(folder_path, fname)
                if os.path.isfile(fpath):
                    models.append({"folder": folder, "name": fname, "size": os.path.getsize(fpath)})

    # Scan custom nodes (syncable only for runtime; raw dirs available separately)
    custom_nodes = _iter_syncable_custom_node_dirs(CUSTOM_NODES_PATH)

    return {
        "models": models,
        "custom_nodes": custom_nodes,
        "custom_nodes_raw_dirs": sorted(
            d for d in os.listdir(CUSTOM_NODES_PATH)
            if os.path.isdir(os.path.join(CUSTOM_NODES_PATH, d))
        ) if os.path.isdir(CUSTOM_NODES_PATH) else [],
    }


@app.function(
    image=_add_comfymodal_local_python_sources(
        modal.Image.debian_slim(python_version="3.11")
    ),
    cpu=1,
    memory=512,
    timeout=30,
    volumes={MODELS_PATH: vol},
)
def set_preload_mode(mode: str) -> str:
    """Set the preload mode for the next cold restore.

    Writes the mode to ``/root/models/.preload_mode`` on the volume so
    the lifecycle restore function reads it before CPU preload.
    """
    import os
    mode = mode.strip().lower()
    valid = {"default", "sequential", "unet_only", "clip_only", "vae", "workers_1", "workers_2",
             "off", "async_no_wait"}
    if mode not in valid and not mode.startswith("budgeted_"):
        return f"invalid mode: {mode}  valid={valid} or budgeted_<ms>"
    os.makedirs("/root/models", exist_ok=True)
    with open(PRELOAD_MODE_PATH, "w") as f:
        f.write(mode)
    vol.commit()
    print(f"[comfyapp] set_preload_mode: {mode}")
    return f"preload_mode={mode}"


@app.function(
    image=_add_comfymodal_local_python_sources(
        modal.Image.debian_slim(python_version="3.11")
    ),
    cpu=1,
    memory=512,
    timeout=30,
    volumes={MODELS_PATH: vol},
)
def set_runtime_flag(name: str, value: str) -> str:
    """Set a runtime config value for the next cold restore.

    Writes ``value`` to ``/root/models/runtime_config/{name}.txt`` which is read
    by ``_resolve_runtime_flag()`` (for bool flags) or inline readers during restore.
    """
    import os
    os.makedirs("/root/models/runtime_config", exist_ok=True)
    path = os.path.join("/root/models/runtime_config", f"{name}.txt")
    with open(path, "w") as f:
        f.write(value.strip())
    vol.commit()
    print(f"[comfyapp] set_runtime_flag: {name}={value}")
    return f"runtime_flag {name}={value}"


@app.function(
    image=_add_comfymodal_local_python_sources(
        modal.Image.debian_slim(python_version="3.11")
    ),
    cpu=2,
    memory=4096,
    timeout=1800,
    volumes={MODELS_PATH: vol},
)
def upload_model_to_volume(file_data: bytes, folder: str, filename: str) -> dict:
    """Upload a model file directly to the volume."""
    import os
    from pathlib import Path

    dest = Path(MODELS_PATH) / folder / filename
    dest.parent.mkdir(parents=True, exist_ok=True)

    with open(dest, "wb") as f:
        f.write(file_data)

    vol.commit()
    return {"status": "ok", "path": str(dest), "size": len(file_data)}


@app.function(
    image=_add_comfymodal_local_python_sources(
        modal.Image.debian_slim(python_version="3.11")
    ),
    cpu=2,
    memory=4096,
    timeout=3600,
    volumes={MODELS_PATH: vol},
)
def set_active_warmup_profile(payload: dict) -> dict:
    validate_active_warmup_profile_payload(payload)
    return _write_active_warmup_profile_payload(payload)


def validate_active_warmup_profile_payload(payload: dict) -> None:
    if not isinstance(payload, dict):
        raise RuntimeError(
            "Refusing to write active_next_profile: payload must be a dict, "
            f"got {type(payload).__name__}"
        )
    if not payload.get("preflight_validated"):
        raise RuntimeError(
            "Refusing to write active_next_profile: payload was not "
            "preflight validated. Validate API prompt locally before "
            "writing active_next_profile."
        )
    if not isinstance(payload.get("workflow_hash"), str) or not payload["workflow_hash"]:
        raise RuntimeError(
            "Refusing to write active_next_profile: workflow_hash "
            "must be a non-empty string."
        )
    if not isinstance(payload.get("validation_token"), str) or not payload["validation_token"]:
        raise RuntimeError(
            "Refusing to write active_next_profile: validation_token "
            "must be a non-empty string."
        )
    if not isinstance(payload.get("model_stack"), dict):
        raise RuntimeError(
            "Refusing to write active_next_profile: model_stack "
            "must be a dict."
        )
    wp = payload.get("warmup_profile")
    if not (isinstance(wp, dict) or payload.get("disable_warmup")):
        raise RuntimeError(
            "Refusing to write active_next_profile: warmup_profile "
            "must be a dict or disable_warmup must be True."
        )


def _write_active_warmup_profile_payload(payload: dict) -> dict:
    validate_active_warmup_profile_payload(payload)
    os.makedirs(RUNTIME_CONFIG_DIR, exist_ok=True)
    profile = dict(payload or {})
    tmp_path = f"{ACTIVE_NEXT_PROFILE_PATH}.tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(profile, f, indent=2, sort_keys=True)
    os.replace(tmp_path, ACTIVE_NEXT_PROFILE_PATH)
    vol.commit()
    print(
        f"[comfyapp] _write_active_warmup_profile_payload token={profile.get('profile_token','')} "
        f"workflow_hash={profile.get('workflow_hash','')} disable_warmup={1 if profile.get('disable_warmup') else 0}"
    )
    return {"status": "ok", "profile_token": profile.get("profile_token", "")}


@app.function(
    image=_add_comfymodal_local_python_sources(
        modal.Image.debian_slim(python_version="3.11")
    ),
    cpu=2,
    memory=4096,
    timeout=3600,
    volumes={MODELS_PATH: vol},
)
def upload_model_chunk(chunk_data: bytes, folder: str, filename: str, offset: int, is_last: bool) -> dict:
    """Upload a model file chunk to the volume. Chunks are appended sequentially.

    Uses a ``.part`` file until the final chunk arrives.  Validates that
    the offset matches the current partial file size before appending to
    prevent silent corruption from out-of-order chunks.
    """
    import os
    from pathlib import Path

    dest = Path(MODELS_PATH) / folder / filename
    dest.parent.mkdir(parents=True, exist_ok=True)

    part = dest.parent / f"{filename}.part"

    # Validate offset equals current part file size
    if offset == 0:
        if part.exists():
            part.unlink()
        if dest.exists():
            dest.unlink()
    else:
        if not part.exists():
            return {"status": "error", "message": f"offset={offset} but no partial file exists"}
        current_size = part.stat().st_size
        if current_size != offset:
            return {
                "status": "error",
                "message": f"offset mismatch: expected {current_size}, got {offset}",
                "expected_offset": current_size,
            }

    with open(part, "ab") as f:
        f.write(chunk_data)

    if is_last:
        os.replace(str(part), str(dest))
        vol.commit()
        return {"status": "ok", "path": str(dest), "size": os.path.getsize(dest)}

    return {"status": "partial", "offset": offset + len(chunk_data)}


# ── CPU-only standalone functions ─────────────────────────────────────────
# These used to be GPU-bound @modal.method() on the ComfyAPI class, wasting
# expensive GPU containers for trivial filesystem/health ops.
# Names end with ``_cpu`` to avoid collision with the existing
# ``@modal.method()`` of the same name on the GPU-tagged ComfyAPI class.


@app.function(
    image=_add_comfymodal_local_python_sources(
        modal.Image.debian_slim(python_version="3.11")
    ),
    cpu=1,
    memory=128,
    timeout=10,
)
def health_cpu():
    """Minimal health probe.  CPU-only — no GPU cost."""
    return {"status": "ok"}


@app.function(
    image=_add_comfymodal_local_python_sources(
        modal.Image.debian_slim(python_version="3.11")
    ),
    cpu=1,
    memory=512,
    timeout=60,
    volumes={MODELS_PATH: vol},
)
def list_models_cpu() -> dict:
    """List all models on the volume.  CPU-only — no GPU cost."""
    import os

    vol.reload()

    solo_folders = [
        "loras", "vae", "controlnet", "upscale_models",
        "embeddings", "clip", "text_encoders",
    ]
    result = {}
    for folder in solo_folders:
        folder_path = os.path.join(MODELS_PATH, folder)
        if not os.path.isdir(folder_path):
            result[folder] = []
            continue
        files = []
        for fname in sorted(os.listdir(folder_path)):
            fpath = os.path.join(folder_path, fname)
            if os.path.isfile(fpath):
                files.append({"name": fname, "size": os.path.getsize(fpath), "folder": folder})
        result[folder] = files

    checkpoint_family = ["checkpoints", "diffusion_models", "unet"]
    result["checkpoints"] = []
    for folder in checkpoint_family:
        folder_path = os.path.join(MODELS_PATH, folder)
        if not os.path.isdir(folder_path):
            continue
        for fname in sorted(os.listdir(folder_path)):
            fpath = os.path.join(folder_path, fname)
            if os.path.isfile(fpath):
                result["checkpoints"].append({"name": fname, "size": os.path.getsize(fpath), "folder": folder})
    return result


@app.function(
    image=_add_comfymodal_local_python_sources(
        modal.Image.debian_slim(python_version="3.11")
    ),
    cpu=1,
    memory=512,
    timeout=30,
    volumes={MODELS_PATH: vol},
)
def delete_model_cpu(folder: str, filename: str) -> dict:
    """Delete a model file from the volume.  CPU-only — no GPU cost."""
    import os

    safe_folder = os.path.basename(folder)
    safe_file = os.path.basename(filename)
    target = os.path.join(MODELS_PATH, safe_folder, safe_file)
    if not os.path.isfile(target):
        return {"status": "error", "message": "File not found"}
    os.remove(target)
    vol.commit()
    return {"status": "ok", "deleted": f"{safe_folder}/{safe_file}"}


@app.function(
    image=_add_comfymodal_local_python_sources(
        modal.Image.debian_slim(python_version="3.11")
    ),
    cpu=1,
    memory=512,
    timeout=30,
    volumes={MODELS_PATH: vol, CUSTOM_NODES_PATH: custom_nodes_vol},
)
def runtime_state_cpu() -> dict:
    """Check if the remote runtime state is stale relative to the volumes.
    CPU-only — no GPU cost."""
    import json

    vol.reload()
    custom_nodes_vol.reload()

    current_models = model_volume_state(MODELS_PATH)
    current_nodes = custom_node_volume_state(CUSTOM_NODES_PATH)

    stale_reasons = []
    try:
        if os.path.isfile(RUNTIME_STATE_SNAPSHOT_PATH):
            saved = json.loads(open(RUNTIME_STATE_SNAPSHOT_PATH, "r").read())
            saved_models = tuple(tuple(e) for e in saved.get("models", []))
            saved_nodes = tuple(tuple(e) for e in saved.get("custom_nodes", []))
            if current_models != saved_models:
                stale_reasons.append("models changed")
            if current_nodes != saved_nodes:
                stale_reasons.append("custom nodes changed")
    except Exception:
        stale_reasons.append("no previous snapshot")

    # Write current state as snapshot for next comparison
    os.makedirs(os.path.dirname(RUNTIME_STATE_SNAPSHOT_PATH), exist_ok=True)
    snapshot = {
        "models": [list(e) for e in current_models],
        "custom_nodes": [list(e) for e in current_nodes],
    }
    with open(RUNTIME_STATE_SNAPSHOT_PATH, "w") as f:
        json.dump(snapshot, f)
    vol.commit()

    return {
        "stale": bool(stale_reasons),
        "stale_reasons": stale_reasons,
        "models_changed": "models changed" in stale_reasons,
        "custom_nodes_changed": "custom nodes changed" in stale_reasons,
    }


def _filter_preload_paths_by_size(file_paths: list[str]) -> tuple[list[str], dict]:
    """Filter preload candidate paths by size guardrails.

    Returns ``(filtered_paths, result_dict)`` where ``result_dict``
    contains the decision reason and per-file details.

    Policy:
    1. Remove individual files above ``PRELOAD_MAX_FILE_GB``.
    2. Compute total size of remaining candidates.
    3. If total exceeds ``PRELOAD_MAX_TOTAL_GB``, return empty list
       with ``reason=max_total_gb_exceeded`` — no partial preload.
    4. Otherwise return the filtered list.
    """
    result: dict = {
        "total_gb": 0.0,
        "files_input": len(file_paths),
        "files_kept": 0,
        "files_skipped": [],
        "skipped_reason": "",
    }
    kept: list[str] = []
    _total_gb = 0.0

    # Phase 1: remove files above PRELOAD_MAX_FILE_GB
    for _p in file_paths:
        try:
            _sz_gb = os.path.getsize(_p) / (1024**3)
        except OSError:
            continue
        if _sz_gb > PRELOAD_MAX_FILE_GB:
            result["files_skipped"].append({
                "path": _p,
                "size_gb": round(_sz_gb, 2),
                "reason": "max_file_gb_exceeded",
            })
            print(
                f"[comfyapp] preload_skipped reason=max_file_gb_exceeded "
                f"file={os.path.basename(_p)} size_gb={round(_sz_gb, 2)} "
                f"max_file_gb={PRELOAD_MAX_FILE_GB}"
            )
            continue
        kept.append(_p)
        _total_gb += _sz_gb

    # Phase 2: if total exceeds max_total_gb, reject everything
    if _total_gb > PRELOAD_MAX_TOTAL_GB:
        result["total_gb"] = round(_total_gb, 2)
        result["files_kept"] = 0
        result["reason"] = "max_total_gb_exceeded"
        print(
            f"[comfyapp] preload_skipped reason=max_total_gb_exceeded "
            f"total_gb={round(_total_gb, 2)} "
            f"max_total_gb={PRELOAD_MAX_TOTAL_GB}"
        )
        return [], result

    result["total_gb"] = round(_total_gb, 2)
    result["files_kept"] = len(kept)
    if not kept and file_paths:
        result["reason"] = result["files_skipped"][0]["reason"] if result["files_skipped"] else "all_files_filtered"
    return kept, result


class _MemoizedValidationCache:
    """Per-container memoization for expensive-but-stable validation results.

    Results are invalidated when the underlying fingerprint changes,
    when a volume reload indicates changed state, or on explicit reset.
    """

    def __init__(self):
        self._data: dict[str, object] = {}
        self._fingerprints: dict[str, str] = {}

    def get(self, key: str) -> object | None:
        return self._data.get(key)

    def set(self, key: str, value: object, fingerprint: str = "") -> None:
        self._data[key] = value
        if fingerprint:
            self._fingerprints[key] = fingerprint

    def has(self, key: str, fingerprint: str = "") -> bool:
        if key not in self._data:
            return False
        if fingerprint and self._fingerprints.get(key) != fingerprint:
            return False
        return True

    def invalidate(self, key: str = "") -> None:
        if key:
            self._data.pop(key, None)
            self._fingerprints.pop(key, None)
        else:
            self._data.clear()
            self._fingerprints.clear()

    def invalidate_all(self) -> None:
        self._data.clear()
        self._fingerprints.clear()


class _ComfyAPIMixin:
    """Shared implementation for all GPU-specific ComfyAPI classes."""

    # Cached localhost HTTP client for ComfyUI API calls.
    _http_client_obj = None

    def _profile_ms(self, started_at: float) -> float:
        return round((time.time() - started_at) * 1000, 1)

    def _log_profile(self, stage: str, **fields) -> None:
        if not PROFILING_ENABLED:
            return
        payload = " ".join(f"{k}={v}" for k, v in fields.items())
        print(f"[comfyapp.profile] stage={stage} {payload}".rstrip())

    # ── PART 7: Shared custom-node sync and dependency policy ────────────
    def _handle_custom_node_sync_and_dependency_policy(self, workflow: dict, stream: bool = False) -> dict:
        """Validate prompt, sync custom nodes, and enforce dependency policy.

        Used by both ``run_prompt`` and ``run_prompt_stream``.  In production
        modes (``off``, ``fail_fast``) dependency mismatch raises immediately;
        sync errors are fatal.  In ``dev`` mode runtime repair is allowed.

        Returns a structured summary dict.
        """
        # 1. Validate API prompt structure
        assert_valid_api_prompt_structure(workflow)

        # 2. Sync custom nodes from volume
        _cn_start = time.time()
        summary, state = self._sync_custom_nodes_from_volume()
        _cn_created = summary.get("created", [])
        _cn_sync_ms = round((time.time() - _cn_start) * 1000, 1)

        # 3. Determine repair mode
        mode = self._resolve_requirements_repair_mode()

        dep_prepared = True
        dep_reason = ""
        installed = []
        skipped = []
        failed = []

        # 4. Production modes: never pip install
        if mode in ("off", "fail_fast"):
            dep_check = validate_custom_node_dependencies_prepared()
            dep_prepared = dep_check.get("prepared", False)
            dep_reason = dep_check.get("reason", "")
            if not dep_prepared:
                baked_hash = dep_check.get("baked_hash", "?") or "?"
                current_hash = dep_check.get("current_hash", "?") or "?"
                changed_nodes = dep_check.get("changed_nodes", [])
                error_msg = (
                    "Custom node dependencies are not prepared for this image. "
                    f"Runtime pip install is disabled in {mode} mode. "
                    "Rebuild/deploy the Modal image after syncing "
                    "custom-node requirements. "
                    f"reason={dep_reason} "
                    f"baked_hash={baked_hash} "
                    f"current_hash={current_hash} "
                    f"changed_nodes={changed_nodes}"
                )
                if stream:
                    # Streaming path: raise so the stream yields a fatal error
                    raise RuntimeError(error_msg)
                else:
                    raise RuntimeError(error_msg)

        # 5. Dev mode: runtime repair is allowed
        if mode == "dev":
            req_result = self._install_custom_node_requirements(force=False)
            installed = req_result.get("installed", [])
            skipped = req_result.get("skipped", [])
            failed = req_result.get("failed", [])
            _in_proc = self._select_backend() == "in_process"
            if _cn_created and _in_proc and self._event_loop is not None:
                import nodes as _pol_nodes
                self._event_loop.run_until_complete(_pol_nodes.init_extra_nodes())

        # ── 6. Enforce node classes available before model work ─────
        _missing_node_result = self._enforce_workflow_node_classes_available_before_model_work(workflow)

        return {
            "sync_created_count": len(_cn_created),
            "sync_kept_count": len(summary.get("kept", [])),
            "sync_removed_count": len(summary.get("removed", [])),
            "repair_mode": mode,
            "dependency_prepared": dep_prepared,
            "dependency_reason": dep_reason,
            "sync_ms": _cn_sync_ms,
            "installed": installed,
            "skipped": skipped,
            "failed": failed,
            "missing_node_check_ran": _missing_node_result.get("missing_node_check_ran", False),
            "missing_nodes_before_model_work": _missing_node_result.get("missing_nodes_before_model_work", []),
            "missing_node_repair_attempted": _missing_node_result.get("missing_node_repair_attempted", False),
            "missing_nodes_after_repair": _missing_node_result.get("missing_nodes_after_repair", []),
            "missing_node_blocked_by_mode": _missing_node_result.get("missing_node_blocked_by_mode", False),
        }

    # ── PART 7: Preflight before prompt execution ────────────────────────
    def _preflight_before_prompt_execution(self, workflow: dict) -> dict:
        """Run preflight checks before any prompt execution.

        Must run before: missing-node repair, async preload, actual load,
        CPU preload, direct warmup, ComfyUI validate_prompt.

        Returns a structured preflight summary dict.
        """
        _repair_mode = self._resolve_requirements_repair_mode()

        # 1. API prompt structure validation
        try:
            assert_valid_api_prompt_structure(workflow)
            valid_prompt = True
        except RuntimeError as exc:
            summary = FailureSummary(phase="preflight")
            summary.fatal_error = str(exc)
            summary.modal_invoked = True
            summary.recommendation = (
                "Remote worker was invoked, but prompt execution was blocked "
                "before model preload/execution due to malformed workflow. "
                "Re-export workflow as API prompt JSON or remove "
                "corrupt/UI-only nodes."
            )
            print(f"[comfyapp] FAILURE SUMMARY: {summary}")
            raise

        # 2. Dependency validation for production modes
        dep_prepared = True
        dep_reason = ""
        if _repair_mode in ("off", "fail_fast"):
            dep_check = validate_custom_node_dependencies_prepared()
            dep_prepared = dep_check.get("prepared", False)
            dep_reason = dep_check.get("reason", "")
            if not dep_prepared:
                baked_hash = dep_check.get("baked_hash", "?") or "?"
                current_hash = dep_check.get("current_hash", "?") or "?"
                changed_nodes = dep_check.get("changed_nodes", [])
                summary = FailureSummary(phase="dependency_preflight")
                summary.fatal_error = "custom node dependencies not prepared"
                summary.modal_invoked = True
                summary.recommendation = (
                    "Rebuild/deploy Modal image after syncing "
                    "custom-node requirements."
                )
                print(f"[comfyapp] FAILURE SUMMARY: {summary}")
                raise RuntimeError(
                    "Custom node dependencies are not prepared for this image. "
                    "Runtime pip install is disabled in "
                    f"{_repair_mode} mode. "
                    f"Rebuild/deploy the Modal image after syncing "
                    f"custom-node requirements. "
                    f"reason={dep_reason} "
                    f"baked_hash={baked_hash} "
                    f"current_hash={current_hash} "
                    f"changed_nodes={changed_nodes}"
                )

        result = {
            "valid_prompt": valid_prompt,
            "dependency_prepared": dep_prepared,
            "repair_mode": _repair_mode,
            "dependency_reason": dep_reason,
        }
        print(f"[comfyapp] preflight result: {result}")
        return result

    @staticmethod
    def _resolve_requirements_repair_mode() -> str:
        """Normalize REQUIREMENTS_REPAIR_MODE, defaulting to fail_fast."""
        mode = REQUIREMENTS_REPAIR_MODE.strip().lower()
        if mode not in ("off", "fail_fast", "dev"):
            mode = "fail_fast"
        return mode

    @property
    def _http_client(self):
        """Lazily-initialised httpx.Client pointed at the local ComfyUI API."""
        import httpx
        if self._http_client_obj is None:
            self._http_client_obj = httpx.Client(base_url=f"http://127.0.0.1:{COMFYUI_API_PORT}")
        return self._http_client_obj

    def _ensure_models_symlink(self):
        """Ensure /root/comfy/ComfyUI/models symlink → MODELS_PATH exists."""
        _t0 = time.time()
        comfy_models = "/root/comfy/ComfyUI/models"
        if not os.path.islink(comfy_models):
            if os.path.isdir(comfy_models):
                import shutil
                shutil.rmtree(comfy_models)
            os.symlink(MODELS_PATH, comfy_models)
            print(f"[comfyapp] models_symlink created -> {MODELS_PATH} "
                  f"in {(time.time()-_t0)*1000:.1f}ms")
        else:
            print(f"[comfyapp] models_symlink already exists -> {os.readlink(comfy_models)} "
                  f"in {(time.time()-_t0)*1000:.1f}ms")

    def _save_last_model_stack(self, stack: dict) -> None:
        """Persist the workflow's model stack to the volume for the next restore.

        Writes the file synchronously but commits to volume in a background
        thread to avoid blocking the response path with network I/O (~370ms).
        Skips write when the content is identical to the existing file.
        """
        import json
        try:
            stack_json = json.dumps(stack, indent=2, sort_keys=True)
            if os.path.isfile(LAST_MODEL_STACK_PATH):
                with open(LAST_MODEL_STACK_PATH, "r") as f:
                    existing = f.read()
                if existing == stack_json:
                    return
            os.makedirs(os.path.dirname(LAST_MODEL_STACK_PATH), exist_ok=True)
            tmp_path = f"{LAST_MODEL_STACK_PATH}.tmp"
            with open(tmp_path, "w") as f:
                f.write(stack_json)
            os.replace(tmp_path, LAST_MODEL_STACK_PATH)
            _commit_volume_async(label="last_model_stack")
        except Exception as exc:
            print(f"[comfyapp] failed to save last model stack: {exc}")

    def _load_last_model_stack(self) -> dict:
        """Read the previously-saved model stack from the volume."""
        try:
            if os.path.isfile(LAST_MODEL_STACK_PATH):
                with open(LAST_MODEL_STACK_PATH) as f:
                    return json.load(f)
        except (json.JSONDecodeError, OSError) as exc:
            print(f"[comfyapp] failed to load last model stack: {exc}")
        return {}

    def _write_active_next_profile(self, payload: dict) -> None:
        try:
            os.makedirs(os.path.dirname(ACTIVE_NEXT_PROFILE_PATH), exist_ok=True)
            tmp_path = f"{ACTIVE_NEXT_PROFILE_PATH}.tmp"
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2, sort_keys=True)
            os.replace(tmp_path, ACTIVE_NEXT_PROFILE_PATH)
            vol.commit()
        except Exception as exc:
            print(f"[comfyapp] failed to write active next profile: {exc}")
            raise

    def _load_active_next_profile(self, now: float | None = None) -> dict:
        reason = ""
        try:
            if not os.path.isfile(ACTIVE_NEXT_PROFILE_PATH):
                reason = "missing_file"
                return {"_diagnostic": {"status": reason, "source_path": ACTIVE_NEXT_PROFILE_PATH}}
            with open(ACTIVE_NEXT_PROFILE_PATH, "r", encoding="utf-8") as f:
                payload = json.load(f)
            if not isinstance(payload, dict) or not payload:
                reason = "invalid_payload"
                return {"_diagnostic": {"status": reason, "source_path": ACTIVE_NEXT_PROFILE_PATH}}
            current = time.time() if now is None else now
            expires_at = float(payload.get("expires_at", 0) or 0)
            payload_diag = {
                "source_path": ACTIVE_NEXT_PROFILE_PATH,
                "now": current,
                "expires_at": expires_at,
                "age_seconds": round(current - float(payload.get("created_at", current)), 1) if payload.get("created_at") else None,
                "ttl_seconds": ACTIVE_NEXT_PROFILE_TTL_S,
                "profile_token": payload.get("profile_token", ""),
                "workflow_hash": payload.get("workflow_hash", ""),
            }
            if payload.get("disable_warmup"):
                reason = "disable_warmup"
                payload_diag["status"] = reason
                print(
                    f"[comfyapp] active_next_profile_skipped reason={reason} "
                    f"token={payload.get('profile_token','?')}"
                )
                payload["_diagnostic"] = payload_diag
                return payload
            if expires_at and current > expires_at:
                reason = "expired"
                payload_diag["status"] = reason
                print(
                    f"[comfyapp] active_next_profile expired token={payload.get('profile_token','?')} "
                    f"now={current} expires_at={expires_at} age_s={payload_diag.get('age_seconds','?')} "
                    f"ttl_s={ACTIVE_NEXT_PROFILE_TTL_S}"
                )
                payload["_diagnostic"] = payload_diag
                return payload
            payload_diag["status"] = "valid"
            payload["_diagnostic"] = payload_diag
            return payload
        except json.JSONDecodeError as exc:
            reason = "invalid_json"
            print(f"[comfyapp] active_next_profile failed reason={reason} error={exc} path={ACTIVE_NEXT_PROFILE_PATH}")
            return {"_diagnostic": {"status": reason, "source_path": ACTIVE_NEXT_PROFILE_PATH, "error": str(exc)}}
        except (OSError, ValueError, TypeError) as exc:
            print(f"[comfyapp] active_next_profile failed reason=read_error error={exc} path={ACTIVE_NEXT_PROFILE_PATH}")
            return {"_diagnostic": {"status": "read_error", "source_path": ACTIVE_NEXT_PROFILE_PATH, "error": str(exc)}}

    def _save_last_warmup_workflow(self, workflow: dict) -> None:
        """Persist a cheap warmup replay derived from a successful prompt."""
        try:
            os.makedirs(os.path.dirname(LAST_WARMUP_WORKFLOW_PATH), exist_ok=True)
            warmup = build_replay_warmup_workflow(workflow)
            warmup_json = json.dumps(warmup, indent=2, sort_keys=True)
            if os.path.isfile(LAST_WARMUP_WORKFLOW_PATH):
                with open(LAST_WARMUP_WORKFLOW_PATH, "r") as f:
                    existing = f.read()
                if existing == warmup_json:
                    return
            tmp_path = f"{LAST_WARMUP_WORKFLOW_PATH}.tmp"
            with open(tmp_path, "w") as f:
                f.write(warmup_json)
            os.replace(tmp_path, LAST_WARMUP_WORKFLOW_PATH)
            _commit_volume_async(label="last_warmup_workflow")
        except Exception as exc:
            print(f"[comfyapp] failed to save last warmup workflow: {exc}")

    def _load_last_warmup_workflow(self) -> dict:
        """Read the replay warmup workflow saved from the last successful prompt."""
        try:
            if os.path.isfile(LAST_WARMUP_WORKFLOW_PATH):
                with open(LAST_WARMUP_WORKFLOW_PATH) as f:
                    workflow = json.load(f)
                if isinstance(workflow, dict) and workflow:
                    return workflow
        except (json.JSONDecodeError, OSError) as exc:
            print(f"[comfyapp] failed to load last warmup workflow: {exc}")
        return {}

    def _find_model_file(self, bucket: str, filename: str) -> str | None:
        """Best-effort model file lookup for warmup preflight checks."""
        candidates = {
            "checkpoint": ["checkpoints"],
            "unet": ["diffusion_models", "unet", "unets"],
            "clip": ["text_encoders", "clip"],
            "vae": ["vae"],
        }.get(bucket, [])
        direct = os.path.join(MODELS_PATH, filename)
        if os.path.isfile(direct):
            return direct
        for folder in candidates:
            path = os.path.join(MODELS_PATH, folder, filename)
            if os.path.isfile(path):
                return path
        return None

    def _validate_warmup_profile_files(self, profile: dict) -> None:
        """Fail fast for missing/placeholder warmup files before expensive execution."""
        checks: list[tuple[str, str]] = []
        if profile.get("mode") == "checkpoint":
            checks.append(("checkpoint", profile.get("checkpoint", "")))
        elif profile.get("mode") == "split":
            checks.extend([
                ("unet", profile.get("unet", "")),
                ("clip", profile.get("clip1", "")),
                ("clip", profile.get("clip2", "")),
                ("vae", profile.get("vae", "")),
            ])
        missing = []
        too_small = []
        for bucket, filename in checks:
            if not filename:
                missing.append(f"{bucket}:<empty>")
                continue
            path = self._find_model_file(bucket, filename)
            if path is None:
                missing.append(f"{bucket}:{filename}")
                continue
            size = os.path.getsize(path)
            print(f"[comfyapp] warmup_validate: bucket={bucket} name={filename} path={path} size_mb={round(size/(1024*1024),1)}")
            if size < 1024 * 1024:
                too_small.append(f"{bucket}:{filename} ({size} bytes)")
        if missing or too_small:
            raise RuntimeError(
                "Warmup model preflight failed; "
                f"missing={missing or []}; too_small={too_small or []}"
            )

    def _ensure_validation_cache(self):
        if not hasattr(self, "_validation_cache"):
            self._validation_cache = _MemoizedValidationCache()

    def _sync_custom_nodes_from_volume(self):
        custom_nodes_vol.reload()
        comfy_custom_nodes = "/root/comfy/ComfyUI/custom_nodes"
        self._ensure_validation_cache()

        # Step 1: Cheap volume state (names + mtimes) for restore hot path.
        # Avoids expensive content hashing of every .py file on every restore.
        cheap_state = custom_node_volume_state(CUSTOM_NODES_PATH)
        cheap_hash = hashlib.md5(str(cheap_state).encode()).hexdigest()
        node_count = len(cheap_state)

        # Check memoized result using cheap volume state
        if self._validation_cache.has("custom_node_sync", fingerprint=cheap_hash):
            _cached = self._validation_cache.get("custom_node_sync")
            if _cached is not None:
                print(
                    f"[comfyapp] custom_node_sync memoized_hit reason=source_fingerprint_unchanged "
                    f"nodes={node_count} created=0"
                )
                _sanitized = (
                    {
                        "created": [],
                        "removed": [],
                        "kept": _cached[0].get("kept", []),
                        "blocked": [],
                        "skipped": True,
                        "skip_reason": "source_fingerprint_unchanged",
                        "node_count": node_count,
                    },
                    _cached[1],
                )
                return _sanitized

        # Step 2: Volume state changed — compute full content fingerprint
        current_fp = custom_node_source_fingerprint(CUSTOM_NODES_PATH)
        current_fp_hash = hashlib.md5(json.dumps(current_fp, sort_keys=True).encode()).hexdigest()
        last_fp = getattr(self, "_last_custom_node_source_fingerprint", None)

        if last_fp is not None and last_fp == current_fp:
            node_count_fp = len(current_fp.get("nodes", []))
            print(
                f"[comfyapp] custom_node_sync_skipped reason=source_fingerprint_unchanged "
                f"nodes={node_count_fp}"
            )
            _result = (
                {
                    "created": [],
                    "removed": [],
                    "kept": [],
                    "blocked": [],
                    "skipped": True,
                    "skip_reason": "source_fingerprint_unchanged",
                },
                cheap_state,
            )
            self._validation_cache.set("custom_node_sync", _result, fingerprint=cheap_hash)
            return _result

        # Step 3: Content actually changed — run the real sync
        summary = sync_custom_nodes_into_comfy(CUSTOM_NODES_PATH, comfy_custom_nodes, include_state=True)
        state = summary.pop("state", cheap_state)
        node_count_fp = len(current_fp.get("nodes", []))
        print(
            f"[comfyapp] custom_node_sync_ran reason=source_fingerprint_changed "
            f"nodes={node_count_fp}"
        )
        self._last_custom_node_source_fingerprint = current_fp
        _result = (summary, state)
        self._validation_cache.set("custom_node_sync", _result, fingerprint=cheap_hash)
        return _result

    def _snapshot_preload_profile(self) -> dict:
        active = self._load_active_next_profile()
        env_profile = load_warmup_profile()
        profile = None
        source = "none"
        if active:
            diag = active.get("_diagnostic", {})
            diag_status = diag.get("status", "")
            if diag_status == "expired":
                print(
                    f"[comfyapp] snapshot_preload_profile source=none reason=active_profile_expired "
                    f"token={active.get('profile_token','?')} "
                    f"now={diag.get('now','?')} expires_at={diag.get('expires_at','?')}"
                )
            elif active.get("disable_warmup"):
                print(
                    f"[comfyapp] snapshot_preload_profile source=active_next_profile profile_token={active.get('profile_token','?')} disable_warmup=1"
                )
                return None
            elif diag_status not in ("expired", "missing_file", "invalid_payload", "invalid_json", "read_error"):
                profile = dict(active.get("warmup_profile") or {})
                source = "active_next_profile"
                if profile:
                    profile["_source"] = source
                    profile["_profile_token"] = active.get("profile_token", "")
                    profile["_workflow_hash"] = active.get("workflow_hash", "")
                    profile["_current_workflow_stack"] = dict(active.get("model_stack") or {})
                    print(
                        f"[comfyapp] snapshot_preload_profile source={source} profile_token={profile.get('_profile_token','')} workflow_hash={profile.get('_workflow_hash','')} data={profile}"
                    )
                    return profile
        if env_profile:
            profile = dict(env_profile)
            profile["_source"] = "env_default"
            print(f"[comfyapp] snapshot_preload_profile source=env_default mode={profile.get('mode','?')} data={profile}")
            return profile
        print("[comfyapp] snapshot_preload_profile source=none - no warmup profile configured")
        return None

    def _log_warmup_vs_workflow_diagnostics(self, warmup_profile: dict, workflow_model_stack: dict, raw_workflow: dict | None = None) -> dict:
        """Compare what the warmup loaded vs what the workflow actually needs.
        Logs a side-by-side diff and returns a match dict.
        """
        result = {
            "warmup_profile": dict(warmup_profile) if warmup_profile else {},
            "workflow_stack": dict(workflow_model_stack) if workflow_model_stack else {},
            "match": {},
        }
        wu = warmup_profile or {}
        ws = workflow_model_stack or {}
        wu_unets = [wu.get("unet", "")] if wu.get("mode") == "split" else wu.get("checkpoint", []) if wu.get("mode") == "checkpoint" else []
        ws_unets = ws.get("unet", []) or ws.get("checkpoint", [])
        wu_clips = [wu.get("clip1", ""), wu.get("clip2", "")] if wu.get("mode") == "split" else []
        ws_clips = ws.get("clip", [])
        wu_vaes = [wu.get("vae", "")] if wu.get("mode") == "split" else []
        ws_vaes = ws.get("vae", [])

        unet_match = bool(set(wu_unets) & set(ws_unets)) if wu_unets and ws_unets else None
        clip_match = bool(set(wu_clips) & set(ws_clips)) if wu_clips and ws_clips else None
        vae_match = bool(set(wu_vaes) & set(ws_vaes)) if wu_vaes and ws_vaes else None
        result["match"] = {"unet": unet_match, "clip": clip_match, "vae": vae_match}

        # Log clip_type from warmup profile and raw workflow nodes
        _wu_clip_type = wu.get("clip_type", "?")
        _wf_clip_types: list[str] = []
        if raw_workflow:
            for _node in raw_workflow.values():
                if isinstance(_node, dict):
                    _ct = _node.get("class_type", "")
                    if _ct in ("CLIPLoader", "DualCLIPLoader"):
                        _t = str(_node.get("inputs", {}).get("type", "?"))
                        if _t not in _wf_clip_types:
                            _wf_clip_types.append(_t)
        ws_clip_type = _wf_clip_types[0] if _wf_clip_types else "?"
        print(f"[comfyapp] warmup_vs_workflow diagnostics:")
        print(f"  WARMUP_PROFILE: unet={wu_unets} clip={wu_clips} vae={wu_vaes} clip_type={_wu_clip_type} mode={wu.get('mode','?')}")
        print(f"  WORKFLOW_STACK: unet={ws_unets} clip={ws_clips} vae={ws_vaes}")
        print(f"  MATCH: unet={unet_match} clip={clip_match} vae={vae_match}")
        if clip_match is False:
            print(f"  CLIP MISMATCH: warmup clips={set(wu_clips)-set(ws_clips)} "
                  f"workflow clips={set(ws_clips)-set(wu_clips)}")
        print(f"  CLIP_TYPE: warmup={_wu_clip_type} workflow={ws_clip_type} match={_wu_clip_type==ws_clip_type}")
        return result

    def _snapshot_preload_paths(self, profile: dict) -> list[str]:
        """Resolve model file paths for snapshot CPU preload.

        Preloads all model files (checkpoint or split) into CPU RAM during
        startup so Modal's memory snapshot captures them.  On restore, the
        cached state dicts are returned by ``_patch_model_cpu_cache``,
        eliminating volume reads during the first prompt execution.

        Which files are preloaded is controlled by PRELOAD_MODE (env var
        ``COMFYMODAL_PRELOAD_MODE``).
        """
        if not profile:
            print("[comfyapp] snapshot_preload_paths: no profile, nothing to preload")
            return []
        profile_mode = profile.get("mode", "")
        checks: list[tuple[str, str]] = []
        if profile_mode == "checkpoint":
            checks.append(("checkpoint", profile.get("checkpoint", "")))
        elif profile_mode == "split":
            unet_f = profile.get("unet", "")
            clip1_f = profile.get("clip1", "")
            clip2_f = profile.get("clip2", "")
            vae_f = profile.get("vae", "")
            _pm = _resolve_preload_mode()
            if _pm == "unet_only":
                checks.append(("unet", unet_f))
            elif _pm == "clip_only":
                checks.append(("clip", clip1_f))
                checks.append(("clip", clip2_f))
            elif _pm == "vae":
                checks.extend([
                    ("unet", unet_f),
                    ("clip", clip1_f),
                    ("clip", clip2_f),
                    ("vae", vae_f),
                ])
            else:
                checks.extend([
                    ("unet", unet_f),
                    ("clip", clip1_f),
                    ("clip", clip2_f),
                ])
        # Deduplicate paths before resolution.
        # When clip1 and clip2 are the same model file (e.g. Qwen 8B used
        # as both text_encoders in Flux), we only need one FUSE stat call.
        # Use filename as the dedup key since bucket is cosmetic.
        active = [(b, f) for b, f in checks if f]
        _active_deduped: list[tuple[str, str]] = []
        _seen_filenames: set[str] = set()
        for b, f in active:
            if f not in _seen_filenames:
                _seen_filenames.add(f)
                _active_deduped.append((b, f))
        if len(_active_deduped) < len(active):
            print(f"[comfyapp] snapshot_preload_paths: deduped {len(active)}→{len(_active_deduped)} "
                  f"duplicates={set(f for _, f in active) - set(f for _, f in _active_deduped)}")
        active = _active_deduped

        paths = []
        seen = set()
        path_times: dict[str, float] = {}
        if active:
            from concurrent.futures import ThreadPoolExecutor, as_completed
            def _resolve(bucket, filename):
                _t = time.time()
                p = self._find_model_file(bucket, filename)
                return filename, p, round((time.time() - _t) * 1000, 1)
            with ThreadPoolExecutor(max_workers=min(len(active), 4)) as _pool:
                _futs = {_pool.submit(_resolve, b, f): (b, f) for b, f in active}
                for _fut in as_completed(_futs):
                    bucket, filename = _futs[_fut]
                    try:
                        fn, path, d_ms = _fut.result()
                        path_times[fn] = d_ms
                        if path and path not in seen:
                            seen.add(path)
                            paths.append(path)
                            print(f"[comfyapp] snapshot_preload_paths: resolved bucket={bucket} name={fn} -> {path} in {d_ms}ms")
                        else:
                            print(f"[comfyapp] snapshot_preload_paths: NOT FOUND bucket={bucket} name={fn} in {d_ms}ms")
                    except Exception as exc:
                        print(f"[comfyapp] snapshot_preload_paths: ERROR bucket={bucket} name={filename}: {exc}")
        print(f"[comfyapp] snapshot_preload_paths: resolved {len(paths)} paths: {[os.path.basename(p) for p in paths]} per-file: {path_times}")
        return paths

    def _preload_models_to_cpu(self, file_paths: list[str], on_file_loaded=None, budget_ms: float | None = None) -> dict:
        """Preload model state dicts into CPU RAM.

        Loaded state dicts are stored in ``_model_cpu_cache``.  The
        ``_patch_model_cpu_cache`` wrapper returns shallow copies of cached
        state dicts when ComfyUI requests a model file, eliminating volume
        reads during the first real-prompt execution.

        This is safe to call during ``restore(snap=False)`` because the
        cache is populated *after* the memory snapshot is already loaded,
        so it does not increase snapshot size (unlike the startup-time
        preload that was disabled for causing 3x restore regression).

        Model files are loaded concurrently via ``ThreadPoolExecutor``
        since FUSE volume reads are I/O-bound and independent across files.

        When ``on_file_loaded`` is callable, it's invoked with ``(filename,)``
        as each file completes loading.  Used by the parallel warmup to
        start text encoding as soon as the CLIP state dict is available.

        When ``budget_ms`` is set, loading stops after approximately that
        many milliseconds have elapsed.  Already-submitted workers continue
        but their results are discarded to avoid blocking.
        """
        if not file_paths:
            return {"count": 0, "cached": [], "file_timing_ms": {},
                    "budget_exceeded": False, "aborted": False, "abort_reason": "",
                    "completed_bytes": 0, "completed_files": 0, "failed_files": 0,
                    "cancelled_futures": 0, "running_threads_not_killable": 0,
                    "pending_not_submitted": 0, "shutdown_wait_false": False}
        if not hasattr(self, "_model_cpu_cache"):
            self._model_cpu_cache = {}
        # Session guard: each preload call gets a unique id.  On abort the
        # session is invalidated so abandoned thread results never mutate
        # the CPU cache after the caller has moved on.
        _preload_session_id = str(uuid.uuid4())
        self._active_cpu_preload_session_id = _preload_session_id
        try:
            _total_start = time.time()
            _total_bytes = 0
            _abort_deadline = time.time() + PRELOAD_OUTLIER_ABORT_SECONDS if PRELOAD_OUTLIER_ABORT_SECONDS > 0 else None
            for p in file_paths:
                try:
                    _total_bytes += os.path.getsize(p)
                except OSError:
                    pass
            # Determine worker count from PRELOAD_MODE
            _preload_max_workers = 4
            _pm = _resolve_preload_mode()
            if _pm == "workers_1":
                _preload_max_workers = 1
            elif _pm == "workers_2":
                _preload_max_workers = 2
            elif _pm in ("sequential",):
                _preload_max_workers = 1

            print(
                f"[comfyapp] preload_models_to_cpu: files={len(file_paths)} "
                f"total_gb={round(_total_bytes / (1024**3), 2)} "
                f"mode={_pm} workers={_preload_max_workers} starting"
            )
            original_loader = getattr(self, "_original_model_loader", None)
            if original_loader is None:
                raise RuntimeError("Original ComfyUI model loader unavailable for CPU preload")

            # Determine which files need loading (skip already-cached)
            to_load = []
            seen_cache_keys = set()
            for path in file_paths:
                cache_key = _model_cpu_cache_key(path)
                if cache_key in seen_cache_keys:
                    continue
                seen_cache_keys.add(cache_key)
                filename = os.path.basename(path)
                if not any(key in self._model_cpu_cache for key in _model_cpu_cache_lookup_keys(path)):
                    to_load.append((path, filename, cache_key))

            cached = []
            file_timing_ms: dict[str, float] = {}
            _aborted = False
            _abort_reason = ""
            _completed_bytes = 0
            _completed_files = 0
            _failed_files = 0
            _cancelled_futures = 0
            _running_threads_not_killable = 0
            _pending_not_submitted = 0
            _shutdown_wait_false = False

            if to_load:
                from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED

                def _load_one(path: str, filename: str, cache_key: str) -> tuple[str, str, object, object | None, float, int]:
                    started = time.time()
                    loaded = original_loader(path, return_metadata=True)
                    d_ms = round((time.time() - started) * 1000, 1)
                    _read_bytes = 0
                    try:
                        _read_bytes = os.path.getsize(path)
                    except OSError:
                        pass
                    if isinstance(loaded, tuple) and len(loaded) == 2:
                        return filename, cache_key, loaded[0], loaded[1], d_ms, _read_bytes
                    return filename, cache_key, loaded, None, d_ms, _read_bytes

                def _check_abort() -> bool:
                    nonlocal _aborted, _abort_reason, _abort_throughput_checked, _last_throughput_check_time, _last_throughput_check_bytes
                    if _aborted:
                        return True
                    if _budget_deadline is not None and time.time() >= _budget_deadline:
                        _aborted = True
                        _abort_reason = "budget_exceeded"
                        _exceeded_by = round((time.time() - _budget_deadline) * 1000, 1)
                        print(f"[comfyapp] preload_models_to_cpu: budget exceeded by {_exceeded_by}ms, "
                              f"loaded {len(cached)}/{len(to_load)} files so far — stopping")
                        return True
                    if _abort_deadline is not None and time.time() >= _abort_deadline:
                        if not _abort_throughput_checked and _completed_bytes == 0:
                            _aborted = True
                            _abort_reason = "no_completed_files_within_abort_window"
                            print(
                                f"[comfyapp] preload_abort_eval: "
                                f"no_completed_files_within_abort_window "
                                f"elapsed_s={round(time.time() - _total_start, 1)}"
                            )
                            return True
                        if not _abort_throughput_checked and _completed_bytes > 0:
                            _elapsed = max(time.time() - _last_throughput_check_time, 0.001)
                            _delta_bytes = _completed_bytes - _last_throughput_check_bytes
                            _observed_gbps = (_delta_bytes) / (1024**3) / _elapsed
                            if _observed_gbps < PRELOAD_MIN_THROUGHPUT_GBPS:
                                _aborted = True
                                _abort_reason = "low_throughput"
                                print(
                                    f"[comfyapp] preload_aborted reason=low_throughput "
                                    f"observed_gbps={round(_observed_gbps, 3)} "
                                    f"threshold_gbps={PRELOAD_MIN_THROUGHPUT_GBPS} "
                                    f"completed_bytes_this_window={_delta_bytes} "
                                    f"elapsed_s={round(time.time() - _total_start, 1)}"
                                )
                                return True
                            _abort_throughput_checked = True
                            _last_throughput_check_time = time.time()
                            _last_throughput_check_bytes = _completed_bytes
                    return False

                _budget_deadline = (time.time() + budget_ms / 1000.0) if budget_ms is not None else None
                _abort_throughput_checked = False
                _last_throughput_check_time = _total_start
                _last_throughput_check_bytes = 0
                _pending = list(to_load)

                pool = ThreadPoolExecutor(max_workers=min(len(to_load), _preload_max_workers))
                try:
                    # Submit initial batch up to max_workers
                    fut_to_item: dict = {}
                    while _pending and len(fut_to_item) < _preload_max_workers:
                        p, f, cache_key = _pending.pop(0)
                        fut = pool.submit(_load_one, p, f, cache_key)
                        fut_to_item[fut] = (f, cache_key, p)

                    while fut_to_item and not _aborted:
                        # Wait for any one future to complete
                        done_set, _ = wait(fut_to_item, timeout=1, return_when=FIRST_COMPLETED)
                        if not done_set:
                            if _check_abort():
                                break
                            continue
                        future = done_set.pop()
                        if future not in fut_to_item:
                            if _check_abort():
                                break
                            continue
                        # Remove before processing to ensure exactly-once
                        _fname, _cache_key, _path = fut_to_item.pop(future)
                        filename = _fname
                        cache_key = _cache_key
                        try:
                            fn, cache_key, state_dict, metadata, d_ms, _read_bytes = future.result()
                            _completed_bytes += _read_bytes
                            _completed_files += 1
                            _session_valid = getattr(self, "_active_cpu_preload_session_id", None) == _preload_session_id
                            if _session_valid:
                                self._model_cpu_cache[cache_key] = (state_dict, metadata)
                                cached.append(fn)
                                if callable(on_file_loaded):
                                    try:
                                        on_file_loaded(fn)
                                    except Exception:
                                        pass
                            file_timing_ms[fn] = d_ms
                            size_mb = "?"
                            for p, f, _cache_key in to_load:
                                if f == fn:
                                    try:
                                        size_mb = round(os.path.getsize(p) / (1024 * 1024), 1)
                                    except OSError:
                                        pass
                                    break
                            self._log_profile(
                                "snapshot_preload_model",
                                file=fn,
                                size_mb=size_mb,
                                duration_ms=d_ms,
                            )
                        except Exception as exc:
                            _failed_files += 1
                            file_timing_ms[filename] = -1.0
                            self._log_profile("snapshot_preload_model_failed", file=filename, error=str(exc)[:200])

                        # Submit next pending if not aborted
                        if not _check_abort() and _pending:
                            p, f, cache_key = _pending.pop(0)
                            fut = pool.submit(_load_one, p, f, cache_key)
                            fut_to_item[fut] = (f, cache_key, p)

                    if _aborted:
                        for _f in list(fut_to_item.keys()):
                            if _f.cancel():
                                _cancelled_futures += 1
                            else:
                                _running_threads_not_killable += 1
                        _pending_not_submitted = len(_pending)
                        _pending.clear()
                        _shutdown_wait_false = True
                        print(
                            f"[comfyapp] preload_abort_requested reason={_abort_reason} "
                            f"cancelled_futures={_cancelled_futures} "
                            f"running_threads_not_killable={_running_threads_not_killable} "
                            f"pending_not_submitted={_pending_not_submitted} "
                            f"shutdown_wait_false=1"
                        )
                        if _running_threads_not_killable:
                            print(
                                f"[comfyapp] preload_session_abandoned "
                                f"session={_preload_session_id} "
                                f"running_threads_not_killable={_running_threads_not_killable} — "
                                f"results discarded"
                            )
                finally:
                    if _aborted:
                        pool.shutdown(wait=False, cancel_futures=True)
                    else:
                        pool.shutdown(wait=True)
            else:
                # All files already cached — just report them
                for path in file_paths:
                    filename = os.path.basename(path)
                    cached.append(filename)

            _total_ms = self._profile_ms(_total_start)
            _loaded_gb = _completed_bytes / (1024**3)
            # Detect preload outliers: any single file >5s
            _slowest_fn = ""
            _slowest_ms = 0.0
            for _fn, _d in file_timing_ms.items():
                if _d > _slowest_ms:
                    _slowest_ms = _d
                    _slowest_fn = _fn
            if _total_ms > 5000 and _slowest_fn:
                _slowest_size_gb = 0.0
                for p in file_paths:
                    if os.path.basename(p) == _slowest_fn:
                        try:
                            _slowest_size_gb = os.path.getsize(p) / (1024**3)
                        except OSError:
                            pass
                        break
                _sl_throughput = round(_slowest_size_gb / max(_slowest_ms / 1000, 0.001), 2) if _slowest_size_gb else 0.0
                print(f"[comfyapp] preload_outlier: true total_ms={_total_ms} "
                      f"slowest_file={_slowest_fn} slowest_ms={_slowest_ms:.0f} "
                      f"size_gb={_slowest_size_gb:.2f} throughput_gbps={_sl_throughput} "
                      f"workers={_preload_max_workers}")

            _throughput_gbps = round(_loaded_gb / max(_total_ms / 1000, 0.001), 2) if _loaded_gb else 0.0
            print(
                f"[comfyapp] preload_models_to_cpu: done in {_total_ms}ms "
                f"loaded={_completed_files} files={len(file_paths)} "
                f"failed={_failed_files} "
                f"cancelled_futures={_cancelled_futures} "
                f"running_threads_not_killable={_running_threads_not_killable} "
                f"loaded_gb={round(_loaded_gb, 2)} "
                f"throughput_gbps={_throughput_gbps}"
            )
            _budget_exceeded = False
            if budget_ms is not None:
                _elapsed = (time.time() - _total_start) * 1000 if _total_start else 0
                _budget_exceeded = _elapsed > budget_ms
            _result = {
                "count": len(cached),
                "cached": cached,
                "file_timing_ms": file_timing_ms,
                "budget_exceeded": _budget_exceeded,
                "aborted": _aborted,
                "abort_reason": _abort_reason,
                "completed_bytes": _completed_bytes,
                "completed_files": _completed_files,
                "failed_files": _failed_files,
                "cancelled_futures": _cancelled_futures,
                "running_threads_not_killable": _running_threads_not_killable,
                "pending_not_submitted": _pending_not_submitted,
                "shutdown_wait_false": _shutdown_wait_false,
            }
            return _result
        finally:
            if getattr(self, "_active_cpu_preload_session_id", None) == _preload_session_id:
                self._active_cpu_preload_session_id = None

    def _model_in_cpu_cache(self, path: str) -> bool:
        """Return True if a model file is already in ``_model_cpu_cache``.

        Uses ``_model_cpu_cache_lookup_keys`` to check all key variants
        (realpath, normcase, basename).
        """
        cache = getattr(self, "_model_cpu_cache", {})
        if not cache:
            return False
        for key in _model_cpu_cache_lookup_keys(path):
            if key in cache:
                return True
        return False

    def _prompt_async_preload(self, workflow: dict) -> dict:
        result = {"enabled": False, "workers": 0, "selected_stack": {}, "resolved_paths": [], "deduped_paths": [], "submitted": [], "duplicate_skipped": 0, "cache_hit": []}
        if not PROMPT_ASYNC_PRELOAD:
            print("[prompt_preload] enabled=0 (PROMPT_ASYNC_PRELOAD not set)")
            return result
        print("[prompt_preload] enabled=1")
        stack = extract_requested_model_stack(workflow)
        result["selected_stack"] = {k: v for k, v in stack.items() if v}
        print(f"[prompt_preload] selected_stack={result['selected_stack']}")
        if not any(stack.values()):
            print("[prompt_preload] no models in stack, nothing to preload")
            return result
        paths, seen_paths = [], set()
        for bucket in ("unet", "clip", "vae", "checkpoint"):
            for filename in stack.get(bucket, []):
                path = self._find_model_file(bucket, filename)
                if path and path not in seen_paths:
                    seen_paths.add(path)
                    paths.append(path)
        result["resolved_paths"] = result["deduped_paths"] = paths
        print(f"[prompt_preload] resolved_paths={[os.path.basename(p) for p in paths]}")
        if not paths:
            print("[prompt_preload] no model files found on disk")
            return result
        workers = PROMPT_PRELOAD_WORKERS
        result["workers"] = workers
        result["enabled"] = True
        print(f"[prompt_preload] workers={workers}")
        if not hasattr(self, "_in_flight_preloads"):
            self._in_flight_preloads = {}
        original_loader = getattr(self, "_original_model_loader", None)
        if original_loader is None:
            print("[prompt_preload] no original model loader, cannot preload")
            return result
        cpu_cache = getattr(self, "_model_cpu_cache", {})
        for path in paths:
            if any(key in cpu_cache for key in _model_cpu_cache_lookup_keys(path)):
                result["cache_hit"].append(os.path.basename(path))
                print(f"[prompt_preload] cache_hit path={os.path.basename(path)}")
                continue
            if path in self._in_flight_preloads:
                result["duplicate_skipped"] += 1
                print(f"[prompt_preload] duplicate_path_skipped path={os.path.basename(path)}")
                continue
            def _load_one(p, cache, loader):
                fname = os.path.basename(p)
                t0 = time.time()
                try:
                    loaded = loader(p, return_metadata=True)
                    if isinstance(loaded, tuple) and len(loaded) == 2:
                        cache[_model_cpu_cache_key(p)] = loaded
                    else:
                        cache[_model_cpu_cache_key(p)] = (loaded, None)
                    print(f"[prompt_preload] done path={fname} ms={round((time.time()-t0)*1000,1)}")
                except Exception as exc:
                    print(f"[prompt_preload] failed path={fname} ms={round((time.time()-t0)*1000,1)} err={exc}")
                finally:
                    getattr(self, "_in_flight_preloads", {}).pop(p, None)
            import threading as _thr
            _t = _thr.Thread(target=_load_one, args=(path, cpu_cache, original_loader), daemon=True)
            _t.start()
            self._in_flight_preloads[path] = _t
            result["submitted"].append(os.path.basename(path))
            print(f"[prompt_preload] submitted path={os.path.basename(path)}")
        return result

    def _init_actual_load_registry(self):
        if not hasattr(self, "_actual_load_futures"):
            self._actual_load_futures: dict[tuple, object] = {}
            self._actual_load_locks: dict[tuple, object] = {}
            self._actual_load_owner_thread: dict[tuple, int] = {}
            self._actual_load_hits = 0
            self._actual_load_waits = 0
            self._actual_load_duplicates_prevented = 0

    @property
    def _original_loaders(self):
        if not hasattr(self, '_original_loaders_store'):
            object.__setattr__(self, '_original_loaders_store', {})
        return self._original_loaders_store

    def _prompt_async_actual_load(self, workflow: dict) -> dict:
        _al_t0 = time.time()
        result = {
            "enabled": False, "submitted": [], "skipped_unet": False, "futures": {},
            "clip_submitted": False, "clip_cache_hit": False, "clip_duration_ms": 0.0,
            "actual_load_mode": ACTUAL_LOAD_MODE,
        }
        if not PROMPT_ASYNC_ACTUAL_LOAD:
            print("[actual_load] enabled=0")
            return result
        print("[actual_load] enabled=1")
        stack = extract_requested_model_stack(workflow)
        selected = {k: v for k, v in stack.items() if v}
        selected["clip_type"] = stack.get("clip_type", "stable_diffusion")
        print(f"[actual_load] selected_stack={selected}")
        if not any(v for k, v in stack.items() if k != "clip_type"):
            print("[actual_load] no loaders in stack, nothing to do")
            return result
        import os as _al_os, nodes as _al_nodes, folder_paths as _al_fp, threading as _al_thr
        self._init_actual_load_registry()
        resolved_keys = []
        _mode_clip = ACTUAL_LOAD_MODE not in ("unet_vae_only", "unet_only")
        _mode_vae = ACTUAL_LOAD_MODE not in ("unet_only",)
        _mode_unet = ACTUAL_LOAD_MODE not in ("clip_vae_only",)
        print(f"[actual_load] mode={ACTUAL_LOAD_MODE} will_start_clip={1 if _mode_clip else 0} will_start_vae={1 if _mode_vae else 0} will_start_unet={1 if _mode_unet else 0}")

        # ── CLIP (single file) ──
        if _mode_clip:
            for clip_name in stack.get("clip", []):
                clip_type = stack.get("clip_type", "stable_diffusion")
                clip_path = (_al_fp.get_full_path("text_encoders", clip_name) or clip_name) if clip_name else ""
                if not clip_path:
                    continue
                try:
                    clip_real = _al_os.path.realpath(clip_path)
                except Exception:
                    clip_real = clip_path
                key = (clip_real, clip_type)
                resolved_keys.append(key)
                lock = self._actual_load_locks.setdefault(key, _al_thr.Lock())
                with lock:
                    if key in self._actual_load_futures:
                        self._actual_load_duplicates_prevented += 1
                        print(f"[actual_load] duplicate_prevented key={key}")
                        result["clip_cache_hit"] = True
                        continue
                    if hasattr(self, "_clip_object_cache") and key in self._clip_object_cache:
                        print(f"[actual_load] cache_hit key={key}")
                        result["clip_cache_hit"] = True
                        continue
                    def _load_clip(k=key, cn=clip_name, ct=clip_type):
                        import threading as _thr_lc
                        _tid = _thr_lc.current_thread().ident
                        self._actual_load_owner_thread[k] = _tid
                        print(f"[actual_load] worker_start loader=CLIP key={k} thread_id={_tid}")
                        t0 = time.time()
                        try:
                            _orig_fn = self._original_loaders.get("CLIPLoader.load_clip")
                            if _orig_fn:
                                print(f"[actual_load] using_original_loader loader=CLIP key={k}")
                                obj = _orig_fn(_al_nodes.NODE_CLASS_MAPPINGS["CLIPLoader"](), clip_name=cn, type=ct)
                            else:
                                obj = _al_nodes.NODE_CLASS_MAPPINGS["CLIPLoader"]().load_clip(clip_name=cn, type=ct)
                            self._clip_object_cache[k] = obj[0]
                            d_ms = round((time.time() - t0) * 1000, 1)
                            result["clip_submitted"] = True
                            result["clip_duration_ms"] = d_ms
                            print(f"[actual_load] done loader=CLIP key={k} ms={d_ms}")
                        except Exception as e:
                            print(f"[actual_load] failed loader=CLIP key={k} err={e}")
                        finally:
                            self._actual_load_owner_thread.pop(k, None)
                    _t = _al_thr.Thread(target=_load_clip, daemon=True)
                    _t.start()
                    self._actual_load_futures[key] = _t
                    result["submitted"].append(f"CLIP key={key}")
                    result["clip_submitted"] = True
                    print(f"[actual_load] submit_raw_key=({clip_path}, {clip_type}) submit_canonical_key={key}")
            # ── CLIP (DualCLIP — second file if different) ──
            clips = stack.get("clip", [])
            if len(clips) >= 2:
                clip_type = stack.get("clip_type", "stable_diffusion")
                for ci in range(1, len(clips)):
                    clip_name = clips[ci]
                    clip_path = _al_fp.get_full_path("text_encoders", clip_name) or clip_name
                    if not clip_path:
                        continue
                    try:
                        clip_real = _al_os.path.realpath(clip_path)
                    except Exception:
                        clip_real = clip_path
                    key = (clip_real, clip_type)
                    if key in resolved_keys:
                        continue
                    resolved_keys.append(key)
                    lock = self._actual_load_locks.setdefault(key, _al_thr.Lock())
                    with lock:
                        if key in self._actual_load_futures:
                            self._actual_load_duplicates_prevented += 1
                            continue
                        if hasattr(self, "_clip_object_cache") and key in self._clip_object_cache:
                            print(f"[actual_load] cache_hit key={key}")
                            continue
                        def _load_clip2(k=key, cn=clip_name, ct=clip_type):
                            import threading as _thr_lc2
                            _tid = _thr_lc2.current_thread().ident
                            self._actual_load_owner_thread[k] = _tid
                            print(f"[actual_load] worker_start loader=DualCLIP key={k} thread_id={_tid}")
                            t0 = time.time()
                            try:
                                _orig_fn = self._original_loaders.get("DualCLIPLoader.load_clip")
                                if _orig_fn:
                                    print(f"[actual_load] using_original_loader loader=DualCLIP key={k}")
                                    obj = _orig_fn(_al_nodes.NODE_CLASS_MAPPINGS["DualCLIPLoader"](), clip_name1=clips[0], clip_name2=cn, type=ct)
                                else:
                                    obj = _al_nodes.NODE_CLASS_MAPPINGS["DualCLIPLoader"]().load_clip(clip_name1=clips[0], clip_name2=cn, type=ct)
                                self._clip_object_cache[k] = obj[0] if obj else None
                                d_ms = round((time.time() - t0) * 1000, 1)
                                print(f"[actual_load] done loader=DualCLIP key={k} ms={d_ms}")
                            except Exception as e:
                                print(f"[actual_load] failed loader=DualCLIP key={k} err={e}")
                            finally:
                                self._actual_load_owner_thread.pop(k, None)
                        _t = _al_thr.Thread(target=_load_clip2, daemon=True)
                        _t.start()
                        self._actual_load_futures[key] = _t
                        result["submitted"].append(f"DualCLIP key={key}")
                        print(f"[actual_load] submit_raw_key=({clip_path}, {clip_type}) submit_canonical_key={key}")
        elif ACTUAL_LOAD_MODE in ("unet_vae_only", "unet_only"):
            print(f"[actual_load] mode_violation_check mode={ACTUAL_LOAD_MODE} started_clip=0 correct=1")

        # ── VAE ──
        if _mode_vae:
            for vae_name in stack.get("vae", []):
                vae_path = _al_fp.get_full_path("vae", vae_name) or vae_name
                if not vae_path:
                    continue
                try:
                    vae_real = _al_os.path.realpath(vae_path)
                except Exception:
                    vae_real = vae_path
                key = ("VAELoader", vae_real)
                resolved_keys.append(key)
                lock = self._actual_load_locks.setdefault(key, _al_thr.Lock())
                with lock:
                    if key in self._actual_load_futures:
                        self._actual_load_duplicates_prevented += 1
                        print(f"[actual_load] duplicate_prevented key={key}")
                        continue
                    self._init_vae_cache()
                    if hasattr(self, "_vae_object_cache") and key in self._vae_object_cache:
                        print(f"[actual_load] cache_hit key={key}")
                        continue
                    def _load_vae(k=key, vn=vae_name):
                        import threading as _thr_lv
                        _tid = _thr_lv.current_thread().ident
                        self._actual_load_owner_thread[k] = _tid
                        print(f"[actual_load] worker_start loader=VAE key={k} thread_id={_tid}")
                        t0 = time.time()
                        try:
                            _orig_fn = self._original_loaders.get("VAELoader.load_vae")
                            if _orig_fn:
                                print(f"[actual_load] using_original_loader loader=VAE key={k}")
                                obj = _orig_fn(_al_nodes.NODE_CLASS_MAPPINGS["VAELoader"](), vae_name=vn)
                            else:
                                obj = _al_nodes.NODE_CLASS_MAPPINGS["VAELoader"]().load_vae(vae_name=vn)
                            self._vae_object_cache[k] = obj[0]
                            d_ms = round((time.time() - t0) * 1000, 1)
                            print(f"[actual_load] done loader=VAE key={k} ms={d_ms}")
                        except Exception as e:
                            print(f"[actual_load] failed loader=VAE key={k} err={e}")
                        finally:
                            self._actual_load_owner_thread.pop(k, None)
                    _t = _al_thr.Thread(target=_load_vae, daemon=True)
                    _t.start()
                    self._actual_load_futures[key] = _t
                    result["submitted"].append(f"VAE key={key}")
                    print(f"[actual_load] submitted loader=VAE key={key}")

        # ── UNET ──
        if _mode_unet:
            unet_names = stack.get("unet", []) or stack.get("checkpoint", [])
            for unet_name in unet_names:
                unet_path = _al_fp.get_full_path("unet", unet_name) or unet_name
                if not unet_path:
                    continue
                try:
                    unet_real = _al_os.path.realpath(unet_path)
                except Exception:
                    unet_real = unet_path
                key = (unet_real, "default")
                resolved_keys.append(key)
                lock = self._actual_load_locks.setdefault(key, _al_thr.Lock())
                with lock:
                    if not PROMPT_ASYNC_ACTUAL_LOAD_UNET:
                        result["skipped_unet"] = True
                        print(f"[actual_load] skipped_unet flag_disabled=1 key={key}")
                        continue
                    self._init_unet_cache()
                    if hasattr(self, "_unet_object_cache") and key in self._unet_object_cache:
                        print(f"[actual_load] cache_hit key={key}")
                        continue
                    if key in self._actual_load_futures:
                        self._actual_load_duplicates_prevented += 1
                        print(f"[actual_load] duplicate_prevented key={key}")
                        continue
                    def _load_unet(k=key, un=unet_name):
                        import threading as _thr_lu
                        _tid = _thr_lu.current_thread().ident
                        self._actual_load_owner_thread[k] = _tid
                        print(f"[actual_load] worker_start loader=UNET key={k} thread_id={_tid}")
                        t0 = time.time()
                        try:
                            _orig_fn = self._original_loaders.get("UNETLoader.load_unet")
                            if _orig_fn:
                                print(f"[actual_load] using_original_loader loader=UNET key={k}")
                                obj = _orig_fn(_al_nodes.NODE_CLASS_MAPPINGS["UNETLoader"](), unet_name=un, weight_dtype="default")
                            else:
                                obj = _al_nodes.NODE_CLASS_MAPPINGS["UNETLoader"]().load_unet(unet_name=un, weight_dtype="default")
                            self._unet_object_cache[k] = obj[0]
                            d_ms = round((time.time() - t0) * 1000, 1)
                            print(f"[actual_load] done loader=UNET key={k} ms={d_ms}")
                        except Exception as e:
                            print(f"[actual_load] failed loader=UNET key={k} err={e}")
                        finally:
                            self._actual_load_owner_thread.pop(k, None)
                    _t = _al_thr.Thread(target=_load_unet, daemon=True)
                    _t.start()
                    self._actual_load_futures[key] = _t
                    result["submitted"].append(f"UNET key={key}")
                    print(f"[actual_load] submitted loader=UNET key={key}")
        else:
            result["skipped_unet"] = True
            print(f"[actual_load] skipped_unet mode={ACTUAL_LOAD_MODE}")
        result["enabled"] = True
        print(f"[actual_load] resolved_keys={resolved_keys}")
        return result

    def _patch_scheduler_clip_encode_prefetch(self, prefetch_cache: dict):
        """Patch CLIPTextEncode to check scheduler prefetch cache first.

        Called by``_start_scheduler_test`` when prefetch is active.
        The prefetch worker populates *prefetch_cache* with keys:

          (text_hash, clip_paths_tuple, clip_type)

        This wrapper checks that cache before the normal CLIPTextEncode
        logic.  Hits are counted on ``self._scheduler_prefetch_real_hit``.
        """
        try:
            import nodes as _ps_nodes
        except Exception:
            return
        _enc_cls = _ps_nodes.NODE_CLASS_MAPPINGS.get("CLIPTextEncode")
        if _enc_cls is None:
            return
        _func_name = getattr(_enc_cls, "FUNCTION", "encode")
        _orig = getattr(_enc_cls, _func_name)
        _api = self
        if not hasattr(_api, "_scheduler_prefetch_real_hit"):
            _api._scheduler_prefetch_real_hit = 0

        def _with_scheduler_prefetch(self_node, clip, text):
            _paths = tuple(getattr(clip, '_warmup_model_paths', None) or [])
            _clip_type = getattr(clip, '_warmup_clip_type', '') or ''
            _text_hash = hashlib.md5(text.encode('utf-8')).hexdigest()
            _key = (_text_hash, _paths, _clip_type)
            if _key in prefetch_cache:
                _api._scheduler_prefetch_real_hit += 1
                return prefetch_cache[_key]
            return _orig(self_node, clip, text)

        setattr(_enc_cls, _func_name, _with_scheduler_prefetch)
        print(f"[scheduler_test] prefetch_cache patch installed on {_enc_cls.__name__}.{_func_name}")

    def _start_scheduler_test(self, workflow: dict, scheduler_config: dict) -> dict:
        """Start controlled scheduler benchmark: dependency validation + model loads.

        Returns a scheduler_trace dict populated asynchronously.
        The caller (run_prompt_stream) waits via ``_scheduler_wait_and_finalize``.

        Modes:
          baseline_current           — no override, existing pipeline
          early_unet_vae             — UNET+VAE at request start, no CLIP
          clip_first                 — CLIP at start_clip_ms, UNET at start_unet_ms, …
          unet_first                 — UNET at start_unet_ms, CLIP at start_clip_ms, …
          clip_serial_then_unet      — CLIP first, then UNET+VAE+encode after CLIP done
          parallel_matrix            — all loads start at configured delays
          clip_load_then_unet_and_encode — CLIP first, then UNET+VAE+encode
          unet_load_then_clip        — UNET first, then CLIP+encode
        """
        import threading
        import os as _st_os
        import nodes as _st_nodes
        import folder_paths as _st_fp

        t_start = time.time()
        mode = scheduler_config.get("mode", "baseline_current")

        trace = {
            "enabled": True,
            "mode": mode,
            "request_start_unix": t_start,
            "scheduler_origin": "comfyapp._start_scheduler_test",
        }

        if mode == "baseline_current":
            trace["enabled"] = False
            trace["notes"] = "baseline — no scheduler override"
            return trace

        # ── 1. Validate prompt structure (cheap) ──────────────
        assert_valid_api_prompt_structure(workflow)

        # ── 2. Sync custom nodes (needed for node classes) ───
        _cn_sync_start = time.time()
        _cn_summary, _cn_state = self._sync_custom_nodes_from_volume()
        _cn_sync_ms = round((time.time() - _cn_sync_start) * 1000, 1)
        trace["custom_nodes_sync_ms"] = _cn_sync_ms
        trace["custom_nodes_created"] = len(_cn_summary.get("created", []))

        # ── 3. Start dependency validation in background ─────
        dep_result = {"prepared": None, "reason": "", "error": None, "changed_nodes": []}
        dep_done = threading.Event()
        dep_start_ms = round((time.time() - t_start) * 1000, 1)
        trace["dependency_validation_start_ms"] = dep_start_ms

        def _dep_worker():
            try:
                dep_check = validate_custom_node_dependencies_prepared()
                dep_result["prepared"] = dep_check.get("prepared", False)
                dep_result["reason"] = dep_check.get("reason", "")
                dep_result["changed_nodes"] = dep_check.get("changed_nodes", [])
            except Exception as e:
                dep_result["error"] = str(e)
            finally:
                dep_done.set()

        dep_thread = threading.Thread(target=_dep_worker, daemon=True)
        dep_thread.start()

        # ── 4. Extract model stack ───────────────────────────
        stack = extract_requested_model_stack(workflow)
        clip_type = stack.get("clip_type", "stable_diffusion")
        trace["model_stack"] = {k: v for k, v in stack.items() if v}

        # ── 5. Init caches/registry ──────────────────────────
        self._init_actual_load_registry()
        self._init_clip_cache()
        self._init_unet_cache()
        self._init_vae_cache()

        # ── 6. Start model loads based on mode ───────────────
        prefetch = scheduler_config.get("prefetch_clip_encode", False)
        start_clip_ms = scheduler_config.get("start_clip_ms")
        start_unet_ms = scheduler_config.get("start_unet_ms")
        start_vae_ms = scheduler_config.get("start_vae_ms")
        unet_after_clip = scheduler_config.get("start_unet_after_clip_load", False)
        vae_after_clip = scheduler_config.get("start_vae_after_clip_load", False)
        clip_after_unet = scheduler_config.get("start_clip_after_unet_load", False)

        # Threads + result dicts for each loader type
        clip_thread = None
        unet_thread = None
        vae_thread = None
        clip_encode_thread = None

        _resolve = lambda bucket, name: _st_fp.get_full_path(
            {"clip": "text_encoders", "unet": "diffusion_models", "vae": "vae"}.get(bucket, bucket), name
        ) or name

        clip_names = stack.get("clip", [])
        unet_names = stack.get("unet", []) or stack.get("checkpoint", [])
        vae_names = stack.get("vae", [])

        # Prefetch cache: populated by the worker, checked by real graph
        _scheduler_prefetch_cache: dict = {}
        # Counter for real graph hits (patched in _patch_scheduler_clip_encode_prefetch)
        self._scheduler_prefetch_real_hit = 0

        # ── Shared loader helpers ────────────────────────────
        _loaded_models: list[dict] = []

        def _record_load(label, basename, filepath, size_gb, t0, t1, sched_ms=0, error=None):
            wall = round((t1 - t0) * 1000, 1) if t0 and t1 else 0
            gbps = round(size_gb / (wall / 1000), 2) if wall > 0 and size_gb > 0 else 0
            rec = {
                "label": label, "basename": basename, "path": filepath,
                "size_gb": size_gb, "effective_gbps": gbps,
                "scheduled_start_ms": sched_ms,
                "actual_start_ms": round((t0 - t_start) * 1000, 1) if t0 else 0,
                "ready_ms": round((t1 - t_start) * 1000, 1) if t1 else 0,
                "load_wall_ms": wall, "error": error,
            }
            _loaded_models.append(rec)
            return rec

        def _load_clip_worker(clip_name, ct, delay_ms, label):
            if delay_ms:
                time.sleep(delay_ms / 1000.0)
            t0 = time.time()
            trace[f"clip_scheduled_start_ms"] = delay_ms
            trace[f"clip_start_ms"] = round((t0 - t_start) * 1000, 1)
            clip_path = _resolve("clip", clip_name)
            try:
                clip_real = _st_os.path.realpath(clip_path) if _st_os.path.exists(clip_path) else clip_path
            except Exception:
                clip_real = clip_path
            key = (clip_real, ct)
            try:
                obj = _st_nodes.NODE_CLASS_MAPPINGS["CLIPLoader"]().load_clip(clip_name=clip_name, type=ct)
                self._clip_object_cache[key] = obj[0]
            except Exception as e:
                t_err = time.time()
                trace["clip_error"] = str(e)
                trace["clip_ready_ms"] = round((t_err - t_start) * 1000, 1)
                trace["clip_load_wall_ms"] = round((t_err - t0) * 1000, 1)
                trace["clip_size_gb"] = 0
                trace["clip_gbps"] = 0
                _record_load(label, _st_os.path.basename(clip_path), clip_real, 0, t0, t_err, sched_ms=delay_ms, error=str(e))
                return
            t1 = time.time()
            try:
                sz = _st_os.path.getsize(clip_real)
            except Exception:
                sz = 0
            size_gb = sz / (1024**3)
            trace["clip_start_ms"] = round((t0 - t_start) * 1000, 1)
            trace["clip_ready_ms"] = round((t1 - t_start) * 1000, 1)
            trace["clip_load_wall_ms"] = round((t1 - t0) * 1000, 1)
            trace["clip_size_gb"] = size_gb
            trace["clip_gbps"] = round(size_gb / (max(t1 - t0, 0.001)), 2)
            _record_load(label, _st_os.path.basename(clip_path), clip_real, size_gb, t0, t1, sched_ms=delay_ms)

        def _load_unet_worker(unet_name, delay_ms, label):
            if delay_ms:
                time.sleep(delay_ms / 1000.0)
            t0 = time.time()
            trace[f"unet_scheduled_start_ms"] = delay_ms
            trace[f"unet_start_ms"] = round((t0 - t_start) * 1000, 1)
            unet_path = _resolve("unet", unet_name)
            try:
                unet_real = _st_os.path.realpath(unet_path) if _st_os.path.exists(unet_path) else unet_path
            except Exception:
                unet_real = unet_path
            try:
                obj = _st_nodes.NODE_CLASS_MAPPINGS["UNETLoader"]().load_unet(unet_name=unet_name, weight_dtype="default")
                self._unet_object_cache[(unet_real, "default")] = obj[0]
            except Exception as e:
                t_err = time.time()
                trace["unet_error"] = str(e)
                trace["unet_ready_ms"] = round((t_err - t_start) * 1000, 1)
                trace["unet_load_wall_ms"] = round((t_err - t0) * 1000, 1)
                trace["unet_size_gb"] = 0
                trace["unet_gbps"] = 0
                _record_load(label, _st_os.path.basename(unet_path), unet_real, 0, t0, t_err, sched_ms=delay_ms, error=str(e))
                return
            t1 = time.time()
            try:
                sz = _st_os.path.getsize(unet_real)
            except Exception:
                sz = 0
            size_gb = sz / (1024**3)
            trace["unet_start_ms"] = round((t0 - t_start) * 1000, 1)
            trace["unet_ready_ms"] = round((t1 - t_start) * 1000, 1)
            trace["unet_load_wall_ms"] = round((t1 - t0) * 1000, 1)
            trace["unet_size_gb"] = size_gb
            trace["unet_gbps"] = round(size_gb / (max(t1 - t0, 0.001)), 2)
            _record_load(label, _st_os.path.basename(unet_path), unet_real, size_gb, t0, t1, sched_ms=delay_ms)

        def _load_vae_worker(vae_name, delay_ms, label):
            if delay_ms:
                time.sleep(delay_ms / 1000.0)
            t0 = time.time()
            trace[f"vae_scheduled_start_ms"] = delay_ms
            trace[f"vae_start_ms"] = round((t0 - t_start) * 1000, 1)
            vae_path = _resolve("vae", vae_name)
            try:
                vae_real = _st_os.path.realpath(vae_path) if _st_os.path.exists(vae_path) else vae_path
            except Exception:
                vae_real = vae_path
            try:
                obj = _st_nodes.NODE_CLASS_MAPPINGS["VAELoader"]().load_vae(vae_name=vae_name)
                self._vae_object_cache[("VAELoader", vae_real)] = obj[0]
            except Exception as e:
                t_err = time.time()
                trace["vae_error"] = str(e)
                trace["vae_ready_ms"] = round((t_err - t_start) * 1000, 1)
                trace["vae_load_wall_ms"] = round((t_err - t0) * 1000, 1)
                trace["vae_size_gb"] = 0
                trace["vae_gbps"] = 0
                _record_load(label, _st_os.path.basename(vae_path), vae_real, 0, t0, t_err, sched_ms=delay_ms, error=str(e))
                return
            t1 = time.time()
            try:
                sz = _st_os.path.getsize(vae_real)
            except Exception:
                sz = 0
            size_gb = sz / (1024**3)
            trace["vae_start_ms"] = round((t0 - t_start) * 1000, 1)
            trace["vae_ready_ms"] = round((t1 - t_start) * 1000, 1)
            trace["vae_load_wall_ms"] = round((t1 - t0) * 1000, 1)
            trace["vae_size_gb"] = size_gb
            trace["vae_gbps"] = round(size_gb / (max(t1 - t0, 0.001)), 2)
            _record_load(label, _st_os.path.basename(vae_path), vae_real, size_gb, t0, t1, sched_ms=delay_ms)

        def _find_eligible_clip_encode_nodes():
            eligible = []
            for node_id, node in workflow.items():
                if not isinstance(node, dict):
                    continue
                if node.get("class_type") != "CLIPTextEncode":
                    continue
                inputs = node.get("inputs", {})
                if not isinstance(inputs, dict):
                    continue
                text = inputs.get("text")
                if not isinstance(text, str) or not text:
                    continue
                clip_src = inputs.get("clip")
                if not isinstance(clip_src, list) or len(clip_src) < 2:
                    continue
                clip_node_id = clip_src[0]
                clip_node = workflow.get(str(clip_node_id))
                if not isinstance(clip_node, dict):
                    continue
                clip_ct = clip_node.get("class_type", "")
                if clip_ct not in ("CLIPLoader", "DualCLIPLoader"):
                    continue
                eligible.append({
                    "node_id": node_id,
                    "text": text,
                    "text_hash": hashlib.md5(text.encode('utf-8')).hexdigest(),
                    "clip_node_id": clip_node_id,
                    "clip_class_type": clip_ct,
                })
            return eligible

        def _run_clip_encode_prefetch():
            start = time.time()
            trace["clip_encode_start_ms"] = round((start - t_start) * 1000, 1)
            eligible = _find_eligible_clip_encode_nodes()
            trace["clip_encode_prefetch_eligible_count"] = len(eligible)
            if not eligible:
                trace["clip_encode_prefetch_done_count"] = 0
                trace["clip_encode_ready_ms"] = trace["clip_encode_start_ms"]
                trace["clip_encode_wall_ms"] = 0
                trace["clip_encode_prefetch_hit"] = 0
                trace["clip_encode_prefetch_miss_reason"] = "no_eligible_nodes"
                return
            try:
                import nodes as _ec_nodes
                enc_cls = _ec_nodes.NODE_CLASS_MAPPINGS.get("CLIPTextEncode")
                if enc_cls is None:
                    trace["clip_encode_ready_ms"] = trace["clip_encode_start_ms"]
                    trace["clip_encode_wall_ms"] = 0
                    trace["clip_encode_prefetch_hit"] = 0
                    trace["clip_encode_prefetch_done_count"] = 0
                    trace["clip_encode_prefetch_miss_reason"] = "CLIPTextEncode_not_found"
                    return
                done = 0
                for info in eligible:
                    try:
                        clip_node = workflow.get(str(info["clip_node_id"]))
                        if not isinstance(clip_node, dict):
                            continue
                        clip_inputs = clip_node.get("inputs", {})
                        ct = clip_inputs.get("type", clip_type)

                        if info["clip_class_type"] == "CLIPLoader":
                            cn = clip_inputs.get("clip_name", "")
                            if not cn:
                                continue
                            clip_path = _resolve("clip", cn)
                            clip_real = _st_os.path.realpath(clip_path) if _st_os.path.exists(clip_path) else clip_path
                            key = (clip_real, ct)
                            clip_obj = self._clip_object_cache.get(key)
                            if clip_obj is None:
                                continue
                            if not hasattr(clip_obj, '_warmup_model_paths'):
                                clip_obj._warmup_model_paths = (clip_real,)
                                clip_obj._warmup_clip_type = ct
                            enc_node = enc_cls()
                            result = enc_node.encode(clip_obj, info["text"])
                            # Store in prefetch cache for real-execution patch
                            _pkey = (info["text_hash"], (clip_real,), ct)
                            _scheduler_prefetch_cache[_pkey] = result
                        elif info["clip_class_type"] == "DualCLIPLoader":
                            cn1 = clip_inputs.get("clip_name1", "")
                            cn2 = clip_inputs.get("clip_name2", "")
                            if not cn1 or not cn2:
                                continue
                            clip1_path = _resolve("clip", cn1)
                            clip2_path = _resolve("clip", cn2)
                            clip1_real = _st_os.path.realpath(clip1_path) if _st_os.path.exists(clip1_path) else clip1_path
                            clip2_real = _st_os.path.realpath(clip2_path) if _st_os.path.exists(clip2_path) else clip2_path
                            key1 = (clip1_real, ct)
                            key2 = (clip2_real, ct)
                            clip_obj1 = self._clip_object_cache.get(key1)
                            clip_obj2 = self._clip_object_cache.get(key2)
                            if clip_obj1 is None or clip_obj2 is None:
                                continue
                            for clip_obj, cr in [(clip_obj1, clip1_real), (clip_obj2, clip2_real)]:
                                if not hasattr(clip_obj, '_warmup_model_paths'):
                                    clip_obj._warmup_model_paths = (clip1_real, clip2_real)
                                    clip_obj._warmup_clip_type = ct
                            from comfy.sd import CLIP
                            combined = CLIP(
                                clip_target = clip_obj1.clip_target,
                                embedding_directory = getattr(clip_obj1, 'embedding_directory', None)
                            )
                            combined.clip = clip_obj1.clip
                            combined.tokenizer = clip_obj1.tokenizer
                            combined.patcher = clip_obj1.patcher
                            combined.load_clip(clip_name2=cn2, type=ct)
                            enc_node = enc_cls()
                            result = enc_node.encode(combined, info["text"])
                            _pkey = (info["text_hash"], (clip1_real, clip2_real), ct)
                            _scheduler_prefetch_cache[_pkey] = result
                        done += 1
                    except Exception as exc:
                        print(f"[scheduler_test] prefetch node {info.get('node_id','?')} failed: {exc}")
                        continue
                end = time.time()
                trace["clip_encode_ready_ms"] = round((end - t_start) * 1000, 1)
                trace["clip_encode_wall_ms"] = round((end - start) * 1000, 1)
                trace["clip_encode_prefetch_hit"] = done
                trace["clip_encode_prefetch_done_count"] = done
                if done == 0 and eligible:
                    trace["clip_encode_prefetch_miss_reason"] = "clip_not_in_cache"
                print(f"[scheduler_test] clip_encode_prefetch done={done} eligible={len(eligible)} ms={trace['clip_encode_wall_ms']}")
            except Exception as exc:
                trace["clip_encode_error"] = str(exc)
                trace["clip_encode_prefetch_hit"] = 0
                trace["clip_encode_prefetch_done_count"] = 0
                trace["clip_encode_prefetch_miss_reason"] = str(exc)
                trace["clip_encode_ready_ms"] = trace.get("clip_encode_start_ms", round((time.time() - t_start) * 1000, 1))
                trace["clip_encode_wall_ms"] = 0
                print(f"[scheduler_test] clip_encode_prefetch failed: {exc}")

        # Install prefetch cache patch on CLIPTextEncode
        if prefetch:
            self._patch_scheduler_clip_encode_prefetch(_scheduler_prefetch_cache)

        # ── Launch loads per mode ────────────────────────────
        if mode == "early_unet_vae":
            for un in unet_names:
                d = start_unet_ms if start_unet_ms is not None else 0
                unet_thread = threading.Thread(target=_load_unet_worker, args=(un, d, "unet"), daemon=True)
                unet_thread.start()
            for vn in vae_names:
                d = start_vae_ms if start_vae_ms is not None else 0
                vae_thread = threading.Thread(target=_load_vae_worker, args=(vn, d, "vae"), daemon=True)
                vae_thread.start()

        elif mode in ("clip_first", "parallel_matrix"):
            if start_clip_ms is not None:
                for cn in clip_names:
                    ct = clip_type
                    clip_thread = threading.Thread(target=_load_clip_worker, args=(cn, ct, start_clip_ms, "clip"), daemon=True)
                    clip_thread.start()
            if start_unet_ms is not None:
                for un in unet_names:
                    unet_thread = threading.Thread(target=_load_unet_worker, args=(un, start_unet_ms, "unet"), daemon=True)
                    unet_thread.start()
            if start_vae_ms is not None:
                for vn in vae_names:
                    vae_thread = threading.Thread(target=_load_vae_worker, args=(vn, start_vae_ms, "vae"), daemon=True)
                    vae_thread.start()
            # Post-CLIP prefetch
            if prefetch and clip_thread is not None:
                def _prefetch_after_clip():
                    clip_thread.join()
                    _run_clip_encode_prefetch()
                clip_encode_thread = threading.Thread(target=_prefetch_after_clip, daemon=True)
                clip_encode_thread.start()

        elif mode == "unet_first":
            if start_unet_ms is not None:
                for un in unet_names:
                    unet_thread = threading.Thread(target=_load_unet_worker, args=(un, start_unet_ms, "unet"), daemon=True)
                    unet_thread.start()
            if start_vae_ms is not None:
                for vn in vae_names:
                    vae_thread = threading.Thread(target=_load_vae_worker, args=(vn, start_vae_ms, "vae"), daemon=True)
                    vae_thread.start()
            if start_clip_ms is not None:
                for cn in clip_names:
                    ct = clip_type
                    clip_thread = threading.Thread(target=_load_clip_worker, args=(cn, ct, start_clip_ms, "clip"), daemon=True)
                    clip_thread.start()
            # Post-CLIP prefetch
            if prefetch and clip_thread is not None:
                def _prefetch_after_clip_unet():
                    clip_thread.join()
                    _run_clip_encode_prefetch()
                clip_encode_thread = threading.Thread(target=_prefetch_after_clip_unet, daemon=True)
                clip_encode_thread.start()

        elif mode in ("clip_serial_then_unet", "clip_load_then_unet_and_encode"):
            for cn in clip_names[:1]:
                ct = clip_type
                clip_thread = threading.Thread(target=_load_clip_worker, args=(cn, ct, 0, "clip"), daemon=True)
                clip_thread.start()
            if clip_thread is not None:
                clip_thread.join()
            for un in unet_names:
                unet_thread = threading.Thread(target=_load_unet_worker, args=(un, 0, "unet"), daemon=True)
                unet_thread.start()
            for vn in vae_names:
                vae_thread = threading.Thread(target=_load_vae_worker, args=(vn, 0, "vae"), daemon=True)
                vae_thread.start()
            if prefetch and clip_thread is not None:
                def _prefetch_serial():
                    _run_clip_encode_prefetch()
                clip_encode_thread = threading.Thread(target=_prefetch_serial, daemon=True)
                clip_encode_thread.start()

        elif mode in ("unet_load_then_clip",):
            for un in unet_names:
                unet_thread = threading.Thread(target=_load_unet_worker, args=(un, 0, "unet"), daemon=True)
                unet_thread.start()
            for vn in vae_names:
                vae_thread = threading.Thread(target=_load_vae_worker, args=(vn, 0, "vae"), daemon=True)
                vae_thread.start()
            if unet_thread is not None:
                unet_thread.join()
            for cn in clip_names[:1]:
                ct = clip_type
                clip_thread = threading.Thread(target=_load_clip_worker, args=(cn, ct, 0, "clip"), daemon=True)
                clip_thread.start()
            if prefetch and clip_thread is not None:
                def _prefetch_after_clip_unet_first():
                    clip_thread.join()
                    _run_clip_encode_prefetch()
                clip_encode_thread = threading.Thread(target=_prefetch_after_clip_unet_first, daemon=True)
                clip_encode_thread.start()

        # ── 7. Store threads for caller to wait on ───────────
        self._scheduler_dep_thread = dep_thread
        self._scheduler_dep_done = dep_done
        self._scheduler_dep_result = dep_result
        self._scheduler_workflow = workflow
        self._scheduler_trace = trace
        self._scheduler_clip_thread = clip_thread
        self._scheduler_unet_thread = unet_thread
        self._scheduler_vae_thread = vae_thread
        self._scheduler_clip_encode_thread = clip_encode_thread
        self._scheduler_prefetch = prefetch
        self._scheduler_t_start = t_start
        self._scheduler_clip_names = clip_names
        self._scheduler_unet_names = unet_names
        self._scheduler_prefetch_cache = _scheduler_prefetch_cache

        print(f"[scheduler_test] config={json.dumps(scheduler_config, default=str)} mode={mode}")
        trace["loaded_models"] = _loaded_models
        return trace

    def _scheduler_wait_and_finalize(self) -> dict:
        """Wait for all scheduler test tasks and finalize the trace.

        Called by run_prompt_stream after scheduler test is started.
        Blocks until dependency validation passes (or fails) and
        required model loads complete. Returns the finalized trace.
        """
        trace = getattr(self, "_scheduler_trace", {})
        if not trace.get("enabled"):
            return trace

        t_start = getattr(self, "_scheduler_t_start", time.time())
        dep_thread = getattr(self, "_scheduler_dep_thread", None)
        dep_done = getattr(self, "_scheduler_dep_done", None)
        dep_result = getattr(self, "_scheduler_dep_result", None)
        clip_thread = getattr(self, "_scheduler_clip_thread", None)
        unet_thread = getattr(self, "_scheduler_unet_thread", None)
        vae_thread = getattr(self, "_scheduler_vae_thread", None)
        clip_encode_thread = getattr(self, "_scheduler_clip_encode_thread", None)
        prefetch = getattr(self, "_scheduler_prefetch", False)
        mode = trace.get("mode", "")

        _repair_mode = self._resolve_requirements_repair_mode()

        # Wait for dependency validation
        if dep_thread is not None and dep_thread.is_alive():
            dep_thread.join()
        if dep_done is not None and dep_done.is_set():
            trace["dependency_gate_done_ms"] = round((time.time() - t_start) * 1000, 1)
            if dep_result:
                trace["dependency_prepared"] = dep_result.get("prepared")
                trace["dependency_reason"] = dep_result.get("reason", "")
                if dep_result.get("error"):
                    trace["dependency_error"] = dep_result["error"]
        else:
            trace["dependency_gate_done_ms"] = trace.get("dependency_validation_start_ms")

        if _repair_mode in ("off", "fail_fast"):
            if dep_result and not dep_result.get("prepared"):
                raise RuntimeError(
                    f"Custom node dependencies are not prepared. "
                    f"Runtime repair is disabled in {_repair_mode} mode. "
                    f"reason={dep_result.get('reason','')} "
                    f"changed_nodes={dep_result.get('changed_nodes',[])} "
                )

        # Missing-node gate
        _mn_workflow = getattr(self, "_scheduler_workflow", None) or {}
        try:
            _mn_result = self._enforce_workflow_node_classes_available_before_model_work(_mn_workflow)
            trace["missing_node_gate_done_ms"] = round((time.time() - t_start) * 1000, 1)
            trace["missing_nodes"] = _mn_result.get("missing_nodes_before_model_work", [])
            if _mn_result.get("missing_node_blocked_by_mode") and _mn_result.get("missing_nodes_before_model_work"):
                raise RuntimeError(
                    f"Missing custom node class(es): "
                    f"{_mn_result['missing_nodes_before_model_work']}"
                )
        except RuntimeError:
            raise
        except Exception as e:
            trace["missing_node_error"] = str(e)

        # Wait for model loads
        for t in (clip_thread, unet_thread, vae_thread):
            if t is not None and t.is_alive():
                t.join()

        if prefetch and clip_encode_thread is not None and clip_encode_thread.is_alive():
            clip_encode_thread.join()

        # Read real-execution prefetch hit counter
        real_hit = getattr(self, "_scheduler_prefetch_real_hit", 0)
        if real_hit > 0:
            trace["clip_encode_prefetch_real_hit"] = real_hit
            trace["clip_encode_prefetch_hit"] = real_hit

        # ── Compute sampler gate ────────────────────────────
        gate_candidates = []
        dep_gate = trace.get("dependency_gate_done_ms")
        if isinstance(dep_gate, (int, float)):
            gate_candidates.append(dep_gate)
        mn_gate = trace.get("missing_node_gate_done_ms")
        if isinstance(mn_gate, (int, float)):
            gate_candidates.append(mn_gate)
        unet_ready = trace.get("unet_ready_ms")
        if isinstance(unet_ready, (int, float)):
            gate_candidates.append(unet_ready)
        has_clip = bool(getattr(self, "_scheduler_clip_names", []))
        if has_clip:
            clip_encode_ready = trace.get("clip_encode_ready_ms")
            if prefetch and isinstance(clip_encode_ready, (int, float)):
                gate_candidates.append(clip_encode_ready)
            else:
                clip_ready = trace.get("clip_ready_ms")
                if isinstance(clip_ready, (int, float)):
                    gate_candidates.append(clip_ready)
        vae_ready = trace.get("vae_ready_ms")
        sampler_gate_without_vae = max(gate_candidates) if gate_candidates else 0
        if isinstance(vae_ready, (int, float)):
            gate_candidates.append(vae_ready)
        trace["sampler_gate_ready_ms"] = max(gate_candidates) if gate_candidates else 0
        trace["sampler_gate_ready_without_vae_ms"] = sampler_gate_without_vae
        trace["sampler_gate_ready_with_vae_ms"] = max(gate_candidates) if gate_candidates else 0

        # ── Notes ─────────────────────────────────────────
        notes_parts = []
        if trace.get("clip_encode_prefetch_hit", 0) > 0:
            notes_parts.append(f"clip_encode_prefetch_hit={trace['clip_encode_prefetch_hit']}")
        if real_hit > 0:
            notes_parts.append(f"prefetch_real_hit={real_hit}")
        trace["notes"] = (trace.get("notes") or "") + " " + "; ".join(notes_parts)
        trace["notes"] = trace["notes"].strip()

        print(f"[scheduler_test] finalized mode={mode} sampler_gate_ready_ms={trace.get('sampler_gate_ready_ms')}")
        return trace

    def _patch_model_cpu_cache(self, comfy_utils) -> None:
        """Patch ComfyUI model loading to reuse CPU-cached state dicts.
        Also coordinates with in-flight prompt-time async preloads."""
        if getattr(self, "_model_cpu_cache_patched", False):
            return
        original_load = comfy_utils.load_torch_file
        self._original_model_loader = original_load
        # Instrumentation counters for cache diagnostics
        self._cpu_cache_hits: dict[str, int] = {}
        self._cpu_cache_misses: dict[str, int] = {}

        def cached_load(path, *args, **kwargs):
            import copy

            filename = os.path.basename(path)
            cache = getattr(self, "_model_cpu_cache", {})
            cache_key = None
            cached = None
            for candidate in _model_cpu_cache_lookup_keys(path):
                if candidate in cache:
                    cache_key = candidate
                    cached = cache[candidate]
                    break
            if cache_key is not None:
                self._cpu_cache_hits[cache_key] = self._cpu_cache_hits.get(cache_key, 0) + 1
                _dc_start = time.time()
                if isinstance(cached, tuple) and len(cached) == 2:
                    state_dict, metadata = copy.copy(cached[0]), copy.copy(cached[1])
                else:
                    state_dict, metadata = copy.copy(cached), None
                _dc_ms = round((time.time() - _dc_start) * 1000, 1)
                acc = getattr(self, "_exec_deepcopy_ms", 0.0)
                self._exec_deepcopy_ms = acc + _dc_ms
                self._log_profile("model_cache_hit", file=filename, deepcopy_ms=_dc_ms)
                if kwargs.get("return_metadata"):
                    return state_dict, metadata
                return state_dict

            # ── In-flight preload coordination ──
            _inflight = getattr(self, "_in_flight_preloads", {})
            if PROMPT_ASYNC_PRELOAD and path in _inflight:
                _thread = _inflight.pop(path, None)
                if _thread is not None:
                    t0 = time.time()
                    _thread.join()
                    wait_ms = round((time.time() - t0) * 1000, 1)
                    print(f"[loader_concurrent] waited_for_preload path={filename} wait_ms={wait_ms}")
                    for candidate in _model_cpu_cache_lookup_keys(path):
                        if candidate in cache:
                            cached = cache[candidate]
                            self._cpu_cache_hits[candidate] = self._cpu_cache_hits.get(candidate, 0) + 1
                            _dc_start = time.time()
                            if isinstance(cached, tuple) and len(cached) == 2:
                                state_dict, metadata = copy.copy(cached[0]), copy.copy(cached[1])
                            else:
                                state_dict, metadata = copy.copy(cached), None
                            acc = getattr(self, "_exec_deepcopy_ms", 0.0)
                            self._exec_deepcopy_ms = acc + round((time.time() - _dc_start) * 1000, 1)
                            if kwargs.get("return_metadata"):
                                return state_dict, metadata
                            return state_dict

            miss_key = _model_cpu_cache_key(path)
            self._cpu_cache_misses[miss_key] = self._cpu_cache_misses.get(miss_key, 0) + 1
            started = time.time()
            result = original_load(path, *args, **kwargs)
            duration_ms = self._profile_ms(started)
            try:
                size_mb = round(os.path.getsize(path) / (1024 * 1024), 1)
            except OSError:
                size_mb = "?"
            self._log_profile(
                "model_volume_load",
                file=filename,
                size_mb=size_mb,
                return_metadata=1 if kwargs.get("return_metadata") else 0,
                duration_ms=duration_ms,
            )
            # Accumulate into execution-profile accumulator
            acc = getattr(self, "_exec_model_load_io_ms", 0.0)
            self._exec_model_load_io_ms = acc + duration_ms
            return result

        comfy_utils.load_torch_file = cached_load
        self._model_cpu_cache_patched = True

    def _count_requirement_cache_hits(self) -> tuple[int, int]:
        """Return (hits, misses) for custom node requirements hashes.

        Used by ``off`` and ``fail_fast`` modes to decide whether runtime
        install would be needed.
        """
        metadata = load_runtime_metadata()
        cached = metadata.get("requirements", {})
        hits = 0
        misses = 0
        for node_dir in _iter_syncable_custom_node_dirs(CUSTOM_NODES_PATH):
            src = os.path.join(CUSTOM_NODES_PATH, node_dir)
            req_file = os.path.join(src, "requirements.txt")
            if not os.path.isfile(req_file):
                continue
            current_hash = requirements_file_hash(req_file)
            if current_hash and cached.get(node_dir) == current_hash:
                hits += 1
            else:
                misses += 1
        return hits, misses

    def _install_custom_node_requirements(self, force: bool = False) -> dict:
        """Install requirements.txt for each custom node.

        Respects ``COMFYMODAL_REQUIREMENTS_REPAIR_MODE``:

        * ``off`` — Never pip install.  Validate baked manifest.  Return.
        * ``fail_fast`` — Never pip install.  Validate baked manifest.
          Raise RuntimeError if not prepared.
        * ``dev`` — Runtime pip install allowed.  ``force=True`` works only
          in dev mode.

        CRITICAL: ``force=True`` must NOT override ``off`` or ``fail_fast``.
        """
        mode = self._resolve_requirements_repair_mode()

        if mode == "off":
            dep_check = validate_custom_node_dependencies_prepared()
            print(
                f"[comfyapp] requirements repair=off: "
                f"prepared={dep_check.get('prepared')} "
                f"reason={dep_check.get('reason', '')}"
            )
            return {
                "installed": [], "skipped": [], "failed": [],
                "mode": "off",
                "prepared": dep_check.get("prepared", False),
                "dependency_reason": dep_check.get("reason", ""),
            }

        if mode == "fail_fast":
            dep_check = validate_custom_node_dependencies_prepared()
            if not dep_check.get("prepared", False):
                baked_hash = dep_check.get("baked_hash", "?") or "?"
                current_hash = dep_check.get("current_hash", "?") or "?"
                changed_nodes = dep_check.get("changed_nodes", [])
                raise RuntimeError(
                    "Custom node dependencies are not prepared for this image. "
                    "Runtime pip install is disabled in fail_fast mode. "
                    "Rebuild/deploy the Modal image after syncing "
                    "custom-node requirements. "
                    f"reason={dep_check.get('reason', '')} "
                    f"baked_hash={baked_hash} "
                    f"current_hash={current_hash} "
                    f"changed_nodes={changed_nodes}"
                )
            skipped = []
            for node_dir in _iter_syncable_custom_node_dirs(CUSTOM_NODES_PATH):
                src = os.path.join(CUSTOM_NODES_PATH, node_dir)
                req_file = os.path.join(src, "requirements.txt")
                if os.path.isfile(req_file):
                    skipped.append(node_dir)
            return {
                "installed": [], "skipped": skipped, "failed": [],
                "mode": "fail_fast", "prepared": True,
            }

        # ── dev mode: runtime pip install allowed ──
        if force:
            print(
                "[comfyapp] WARNING: requirements repair mode=dev: "
                "force=True requested runtime pip install; "
                "this is slow and not production-safe."
            )
        else:
            print(
                "[comfyapp] requirements repair mode=dev: "
                "runtime pip install allowed; "
                "this is slow and not production-safe."
            )

        metadata = load_runtime_metadata()
        cached_version = metadata.get("comfyapp_version")
        if not force and cached_version and cached_version != COMFYAPP_VERSION:
            print(
                f"[comfyapp] requirements cache stale: comfyapp_version "
                f"{cached_version} != {COMFYAPP_VERSION}, invalidating all hashes"
            )
            metadata.pop("requirements", None)
            metadata["comfyapp_version"] = COMFYAPP_VERSION
            save_runtime_metadata(metadata)
        cached = metadata.get("requirements", {})
        installed = []
        skipped = []
        failures = []
        updated_hashes = {}
        _t0 = time.time()
        _hash_hit_count = 0
        _import_checked_count = 0

        for node_dir in _iter_syncable_custom_node_dirs(CUSTOM_NODES_PATH):
            src = os.path.join(CUSTOM_NODES_PATH, node_dir)
            req_file = os.path.join(src, "requirements.txt")
            if not os.path.isfile(req_file):
                continue
            current_hash = requirements_file_hash(req_file)
            if not force and current_hash:
                if cached.get(node_dir) == current_hash:
                    _hash_hit_count += 1
                    skipped.append(node_dir)
                    continue
                if _requirements_have_importable_packages(req_file):
                    _import_checked_count += 1
                    updated_hashes[node_dir] = current_hash
                    skipped.append(node_dir)
                    continue

            req_lines = Path(req_file).read_text(encoding="utf-8").splitlines()
            req_dir = os.path.dirname(req_file)
            missing_local_paths = []
            for line in req_lines:
                stripped = line.strip()
                if not stripped or stripped.startswith("#"):
                    continue
                requirement = stripped.split(";", 1)[0].strip()
                if requirement.startswith("-e "):
                    requirement = requirement[3:].strip()
                elif requirement.startswith("--editable "):
                    requirement = requirement[len("--editable "):].strip()
                if requirement.startswith("./") or requirement.startswith("../"):
                    resolved = os.path.abspath(os.path.join(req_dir, requirement))
                    if not os.path.exists(resolved):
                        missing_local_paths.append(requirement)

            if missing_local_paths:
                failures.append({
                    "node": node_dir,
                    "stderr": (
                        "Missing local requirement path(s): "
                        f"{', '.join(missing_local_paths)} relative to {req_dir}"
                    )[:1000],
                })
                continue

            print(
                f"[comfyapp] installing custom node requirements node={node_dir} "
                f"timeout_s={CUSTOM_NODE_REQUIREMENTS_TIMEOUT_S}"
            )
            try:
                result = subprocess.run(
                    [sys.executable, "-m", "pip", "install", "-r", req_file],
                    capture_output=True,
                    text=True,
                    timeout=CUSTOM_NODE_REQUIREMENTS_TIMEOUT_S,
                    cwd=src,
                )
            except subprocess.TimeoutExpired as exc:
                failures.append({
                    "node": node_dir,
                    "stderr": (
                        f"requirements install timed out after {CUSTOM_NODE_REQUIREMENTS_TIMEOUT_S}s"
                    )[:1000],
                })
                print(
                    f"[comfyapp] custom node requirements timed out node={node_dir} "
                    f"timeout_s={CUSTOM_NODE_REQUIREMENTS_TIMEOUT_S}"
                )
                continue
            if result.returncode != 0:
                print(f"[comfyapp] custom node requirements install FAILED node={node_dir}: "
                      f"{result.stderr[:500] or result.stdout[:500] or 'no output'}")
                failures.append({
                    "node": node_dir,
                    "stderr": (result.stderr or result.stdout or "requirements install failed")[:1000],
                })
            else:
                print(f"[comfyapp] installed custom node requirements node={node_dir}")
                installed.append(node_dir)
                if current_hash:
                    updated_hashes[node_dir] = current_hash

        if updated_hashes or force:
            metadata["requirements"] = {**cached, **updated_hashes}
            metadata["comfyapp_version"] = COMFYAPP_VERSION
            save_runtime_metadata(metadata)

        if failures:
            print(f"[comfyapp] custom node requirements had {len(failures)} failure(s) — continuing "
                  f"(affects: {[f['node'] for f in failures]})")

        _total_ms = round((time.time() - _t0) * 1000, 1)
        print(
            f"[comfyapp] requirements check complete in {_total_ms}ms "
            f"total_with_reqs={len(installed) + len(skipped)} "
            f"hash_hit={_hash_hit_count} importability_checked={_import_checked_count} "
            f"installed={len(installed)} skipped={len(skipped)} failed={len(failures)}"
        )

        return {"installed": installed, "skipped": skipped, "failed": [f["node"] for f in failures]}

    # ── sageattention runtime policy helpers ──────────────────────────────

    def _preferred_sage_backend(self):
        import sageattention

        for name, kwargs in (
            ("sageattn_qk_int8_pv_fp16_cuda", {"pv_accum_dtype": "fp32"}),
            ("sageattn_qk_int8_pv_fp8_cuda", {"pv_accum_dtype": "fp32+fp32"}),
        ):
            candidate = getattr(sageattention, name, None)
            if callable(candidate):
                return name, candidate, kwargs
        return None, None, {}

    def _verify_baked_sageattention_runtime(self) -> tuple[bool, list[str]]:
        import importlib
        import torch

        extension_files = list_sageattention_extension_files(SAGEATTENTION_SITE_PACKAGES)
        if not extension_files:
            return False, ["compiled-extensions-missing"]

        try:
            import sageattention._fused  # noqa: F401
            importlib.invalidate_caches()
            import sageattention  # noqa: F401
        except Exception as exc:
            return False, [f"_fused-import-failed:{type(exc).__name__}"]

        try:
            backend_name, backend, backend_kwargs = self._preferred_sage_backend()
            if backend is None:
                return False, ["no-supported-kjnodes-backend-symbol"]
            q = torch.randn(1, 16, 8, 64, device="cuda", dtype=torch.float16)
            k = torch.randn(1, 16, 8, 64, device="cuda", dtype=torch.float16)
            v = torch.randn(1, 16, 8, 64, device="cuda", dtype=torch.float16)
            _ = backend(q, k, v, is_causal=False, attn_mask=None, tensor_layout="NHD", **backend_kwargs)
            torch.cuda.synchronize()
            return True, [str(backend_name or "unknown-backend"), *[p.name for p in extension_files]]
        except Exception as exc:
            return False, [f"cuda-smoke-test-failed:{type(exc).__name__}"]

    def _select_sage_runtime_mode(self) -> tuple[str, str]:
        # Sticky — already selected earlier in this restore
        if getattr(self, "_sage_runtime_mode", None) is not None:
            return self._sage_runtime_mode, getattr(self, "_sage_runtime_reason", "sticky")

        # P2 — runtime-configurable env override (file → env → module)
        _rt_sage_mode = _resolve_sage_runtime_env_override()
        _rt_sage_probe = _resolve_sage_probe_on_restore()
        if _rt_sage_mode in ("baked_cuda", "triton_fallback"):
            self._sage_runtime_mode = _rt_sage_mode
            self._sage_runtime_reason = f"runtime_override"
            print(f"[comfyapp] sage_runtime_mode={self._sage_runtime_mode} reason={self._sage_runtime_reason} "
                  f"(SAGE_RUNTIME_MODE={_rt_sage_mode})")
            return self._sage_runtime_mode, self._sage_runtime_reason

        # P2 — skip probe on restore: prefer cached value, else env default
        if not _rt_sage_probe:
            cached = self._load_sage_runtime_cache()
            if cached:
                print(f"[comfyapp] sage_runtime_cache hit mode={cached['mode']} reason={cached['reason']} "
                      f"gpu={cached['gpu_name']} sage_v={cached['sage_version']} (probe skipped)")
                self._sage_runtime_mode = cached["mode"]
                self._sage_runtime_reason = cached["reason"]
                return self._sage_runtime_mode, self._sage_runtime_reason
            # No cache available — fall back to baked_cuda (safe on Blackwell,
            # and Triton fallback works even if baked CUDA import fails later)
            import torch
            gpu_name = torch.cuda.get_device_name(0) if torch.cuda.is_available() else "unknown"
            _default_mode = "baked_cuda" if "Blackwell" in gpu_name or "RTX PRO 6000" in gpu_name else "triton_fallback"
            self._sage_runtime_mode = _default_mode
            self._sage_runtime_reason = f"no_cache_restore_default_gpu={gpu_name}"
            print(f"[comfyapp] sage_runtime_mode={self._sage_runtime_mode} reason={self._sage_runtime_reason} (probe skipped, no cache)")
            return self._sage_runtime_mode, self._sage_runtime_reason

        # Normal path: check persistent cache, probe if needed
        import json, os
        cached = self._load_sage_runtime_cache()
        if cached:
            print(f"[comfyapp] sage_runtime_cache hit mode={cached['mode']} reason={cached['reason']} "
                  f"gpu={cached['gpu_name']} sage_v={cached['sage_version']}")
            self._sage_runtime_mode = cached["mode"]
            self._sage_runtime_reason = cached["reason"]
            return self._sage_runtime_mode, self._sage_runtime_reason

        import torch
        extension_files = list_sageattention_extension_files(SAGEATTENTION_SITE_PACKAGES)
        ok, details = self._verify_baked_sageattention_runtime()
        mode, reason = choose_sage_runtime_mode(
            enabled=True,
            extension_files=extension_files,
            import_ok=ok,
            smoke_ok=ok,
        )
        self._sage_runtime_mode = mode
        self._sage_runtime_reason = details[0] if details else reason
        print(f"[comfyapp] sage_runtime_mode={self._sage_runtime_mode} reason={self._sage_runtime_reason}")
        # Persist to volume for future restores
        self._save_sage_runtime_cache(mode, self._sage_runtime_reason)
        return self._sage_runtime_mode, self._sage_runtime_reason

    def _load_sage_runtime_cache(self) -> dict | None:
        """Read cached sage runtime mode from volume. Returns None if stale or missing."""
        import json, os, torch
        try:
            if not os.path.isfile(SAGE_RUNTIME_CACHE_PATH):
                return None
            with open(SAGE_RUNTIME_CACHE_PATH) as f:
                data = json.load(f)
            if not isinstance(data, dict):
                return None
            gpu_name = torch.cuda.get_device_name(0) if torch.cuda.is_available() else "unknown"
            sage_version = ""
            try:
                import sageattention
                sage_version = getattr(sageattention, "__version__", "") or ""
            except ImportError:
                pass
            # Cache is valid if GPU and sage version match
            if data.get("gpu_name") == gpu_name and data.get("sage_version") == sage_version:
                return data
            print(f"[comfyapp] sage_runtime_cache stale: gpu {data.get('gpu_name')}->{gpu_name} "
                  f"sage {data.get('sage_version')}->{sage_version}")
        except Exception as exc:
            print(f"[comfyapp] sage_runtime_cache error: {exc}")
        return None

    def _save_sage_runtime_cache(self, mode: str, reason: str) -> None:
        """Persist sage runtime mode to volume for faster future restores."""
        import json, os, torch, time
        try:
            gpu_name = torch.cuda.get_device_name(0) if torch.cuda.is_available() else "unknown"
            sage_version = ""
            try:
                import sageattention
                sage_version = getattr(sageattention, "__version__", "") or ""
            except ImportError:
                pass
            data = {
                "mode": mode,
                "reason": reason,
                "gpu_name": gpu_name,
                "sage_version": sage_version,
                "created_at": time.time(),
            }
            os.makedirs(os.path.dirname(SAGE_RUNTIME_CACHE_PATH), exist_ok=True)
            tmp = f"{SAGE_RUNTIME_CACHE_PATH}.tmp"
            with open(tmp, "w") as f:
                json.dump(data, f, indent=2, sort_keys=True)
            os.replace(tmp, SAGE_RUNTIME_CACHE_PATH)
            _commit_volume_async(label="sage_runtime_cache")
            print(f"[comfyapp] sage_runtime_cache saved mode={mode} gpu={gpu_name} sage_v={sage_version}")
        except Exception as exc:
            print(f"[comfyapp] sage_runtime_cache save error: {exc}")

    def _apply_sage_attention_policy(self):
        _t0 = time.time()
        baked_cuda_available = getattr(self, "_sage_runtime_mode", "triton_fallback") == "baked_cuda"
        found = False
        patched = False
        for mod in list(sys.modules.values()):
            file_name = getattr(mod, "__file__", "") or ""
            if file_name.endswith("model_optimization_nodes.py"):
                found = True
                patched = patch_kjnodes_get_sage_func(mod, baked_cuda_available=baked_cuda_available)
                _dur = round((time.time() - _t0) * 1000, 1)
                print(f"[comfyapp] sage_policy module=model_optimization_nodes.py "
                      f"found=True patched={patched} "
                      f"baked_cuda_available={baked_cuda_available} "
                      f"duration={_dur}ms")
                return patched
        _dur = round((time.time() - _t0) * 1000, 1)
        print(f"[comfyapp] sage_policy module=model_optimization_nodes.py "
              f"found=False baked_cuda_available={baked_cuda_available} "
              f"duration={_dur}ms")
        return False

    # ── Backend scaffold (warmup + execution backend selection) ──────────

    def _begin_prompt_profile(self, workflow: dict, prompt_id: str, outputs_to_execute) -> None:
        node_map: dict[str, str] = {}
        class_counts: dict[str, int] = {}
        for node_id, spec in (workflow or {}).items():
            if not isinstance(spec, dict):
                continue
            class_type = str(spec.get("class_type", "?"))
            node_map[str(node_id)] = class_type
            class_counts[class_type] = class_counts.get(class_type, 0) + 1

        self._current_prompt_node_map = node_map
        self._current_prompt_id = prompt_id[:8]
        self._perf_last_node = None
        self._perf_last_ts = None
        self._ksampler_state = None

        # Stage windows for the per-node timing trace (t4..t7).
        # Each window records first/last seen timestamps for a given
        # class_type so that CLIPLoader, CLIPTextEncode, Sampler and
        # VAEDecode each have a clean start/end pair even when a single
        # node execution spans multiple event dispatches.
        self._stage_windows: dict[str, dict[str, float]] = {
            "unet_load": {},
            "clip_load": {},
            "vae_load": {},
            "clip_encode": {},
            "sampler": {},
            "vae_decode": {},
            "cachedit": {},
            "noise_inject": {},
            "sampler_setup": {},
        }

        if not PROFILING_ENABLED:
            return

        self._log_profile(
            "inproc_node_map",
            prompt_id=prompt_id[:8],
            outputs=len(outputs_to_execute or []),
            map=json.dumps(node_map, sort_keys=True, separators=(",", ":")),
        )
        self._log_profile(
            "inproc_node_counts",
            prompt_id=prompt_id[:8],
            counts=json.dumps(class_counts, sort_keys=True, separators=(",", ":")),
        )

    def _node_class_type(self, node_id) -> str:
        return getattr(self, "_current_prompt_node_map", {}).get(str(node_id), "?")

    def _begin_profiled_node(self, node, now: float) -> None:
        node = str(node)
        class_type = self._node_class_type(node)
        self._perf_last_node = node
        self._perf_last_ts = now
        if "Sampler" in class_type:
            self._ksampler_state = {
                "node": node,
                "class_type": class_type,
                "started": now,
                "first_progress": None,
                "last_progress": None,
                "progress_events": 0,
                "max_step": 0,
                "max_steps": 0,
            }
        # Trace t4..t7 stage windows: record the first time a node of the
        # given class starts so we have a clean t<N>_start timestamp even
        # when the class appears multiple times in the graph (e.g. dual
        # CLIPTextEncode nodes).  The matching t<N>_end is recorded in
        # _finish_profiled_node.
        stage = self._stage_for_class(class_type)
        if stage:
            windows = getattr(self, "_stage_windows", None)
            if windows is not None and stage != "sampler" and "start" not in windows[stage]:
                windows[stage]["start"] = now
                windows[stage]["start_node"] = node
                windows[stage]["start_class"] = class_type
        if not PROFILING_ENABLED:
            return
        self._log_profile(
            "inproc_exec_progress",
            event="executing_node",
            node=node[:40],
            class_type=class_type[:80],
        )

    @staticmethod
    def _stage_for_class(class_type: str) -> str | None:
        """Map a node class_type to one of the t4..t7 or warmup trace stages."""
        ct = class_type or ""
        if "CacheDiT_Model_Optimizer" in ct or "CacheDiT" in ct:
            return "cachedit"
        if "LGNoiseInjectionLatent" in ct or "NoiseInjection" in ct or "FeatureInjLatent" in ct:
            return "noise_inject"
        if "UNETLoader" in ct:
            return "unet_load"
        if "CLIPLoader" in ct or "DualCLIPLoader" in ct:
            return "clip_load"
        if "VAELoader" in ct:
            return "vae_load"
        if "TextEncode" in ct or "CLIPTextEncode" in ct:
            return "clip_encode"
        if "Sampler" in ct or "SamplerAdvanced" in ct or "SamplerCustom" in ct:
            return "sampler"
        if "VAEDecode" in ct:
            return "vae_decode"
        return None

    def _commit_stage_windows_to_trace(self, trace: Trace) -> None:
        """Copy the t4..t7 stage windows onto the given trace and log timings."""
        windows = getattr(self, "_stage_windows", None) or {}
        for stage, fields in windows.items():
            if not fields:
                continue
            start = fields.get("start")
            end = fields.get("end")
            if start is not None and end is not None:
                if stage == "clip_load":
                    trace._t["t4_clip_load_start"] = start
                    trace._t["t4_clip_load_end"] = end
                elif stage == "clip_encode":
                    trace._t["t5_text_encode_start"] = start
                    trace._t["t5_text_encode_end"] = end
                elif stage == "sampler":
                    trace._t["t6_sampler_start"] = start
                    trace._t["t6_sampler_end"] = end
                    # Sub-millisecond sampler phases
                    ps = fields.get("progress_start")
                    pe = fields.get("progress_end")
                    if ps is not None:
                        trace._t["t6_sampler_progress_start"] = ps
                    if pe is not None:
                        trace._t["t6_sampler_progress_end"] = pe
                elif stage == "vae_decode":
                    trace._t["t7_vae_decode_start"] = start
                    trace._t["t7_vae_decode_end"] = end
                elif stage == "unet_load":
                    trace._t["t4b_unet_load_start"] = start
                    trace._t["t4b_unet_load_end"] = end
                elif stage == "vae_load":
                    trace._t["t4c_vae_load_start"] = start
                    trace._t["t4c_vae_load_end"] = end
                elif stage == "cachedit":
                    trace._t["t8_cachedit_start"] = start
                    trace._t["t8_cachedit_end"] = end
                elif stage == "noise_inject":
                    trace._t["t8_noise_inject_start"] = start
                    trace._t["t8_noise_inject_end"] = end
                dur = round((end - start) * 1000, 1)
                print(f"[timing.node] {stage}={dur}ms start_class={fields.get('start_class','?')}")

    def _note_progress_event(self, data: dict) -> None:
        state = getattr(self, "_ksampler_state", None)
        if not state:
            return
        node = str(data.get("node", ""))
        if node != str(state.get("node")):
            return
        now = time.time()
        if state["first_progress"] is None:
            state["first_progress"] = now
        state["last_progress"] = now
        state["progress_events"] += 1
        state["max_step"] = max(state["max_step"], int(data.get("step", 0)))
        state["max_steps"] = max(state["max_steps"], int(data.get("max", 0)))

    def _finish_profiled_node(self, now: float) -> None:
        last_node = getattr(self, "_perf_last_node", None)
        last_ts = getattr(self, "_perf_last_ts", None)
        if last_node is None or last_ts is None:
            return
        class_type = self._node_class_type(last_node)
        duration_ms = round((now - last_ts) * 1000, 1)
        # Trace: close the matching t<N>_end timestamp for this stage.
        stage = self._stage_for_class(class_type)
        windows = getattr(self, "_stage_windows", None)
        if stage and windows and stage != "sampler" and "start" in windows[stage] and "end" not in windows[stage]:
            windows[stage]["end"] = now
            windows[stage]["end_node"] = last_node

        sampler_phase = None
        state = getattr(self, "_ksampler_state", None)
        if stage == "sampler" and state and str(state.get("node")) == str(last_node):
            first = state.get("first_progress")
            last = state.get("last_progress")
            if first is None:
                prep_ms = duration_ms
                denoise_ms = 0.0
                teardown_ms = 0.0
            else:
                prep_ms = round(max(0.0, (first - state["started"]) * 1000), 1)
                denoise_ms = round(max(0.0, ((last or first) - first) * 1000), 1)
                teardown_ms = round(max(0.0, duration_ms - prep_ms - denoise_ms), 1)
            if windows and stage in windows:
                # Prefer the sampler node that actually emitted progress callbacks.
                # This avoids latching onto earlier light-weight sampler-like
                # nodes that finish instantly but still match the class-name heuristic.
                if first is not None:
                    windows[stage]["node_start"] = state["started"]
                    windows[stage]["start"] = first
                    windows[stage]["end"] = last or first
                    windows[stage]["progress_start"] = first
                    windows[stage]["progress_end"] = last or first
                    windows[stage]["progress_events"] = state.get("progress_events", 0)
                    windows[stage]["max_step"] = state.get("max_step", 0)
                    windows[stage]["max_steps"] = state.get("max_steps", 0)
                    windows[stage]["duration_ms"] = duration_ms
                    windows[stage]["source"] = "progress"
                else:
                    previous_duration = float(windows[stage].get("duration_ms", -1.0))
                    if duration_ms > previous_duration:
                        windows[stage]["start"] = state["started"]
                        windows[stage]["end"] = now
                        windows[stage]["duration_ms"] = duration_ms
                        windows[stage]["source"] = "node_duration"
            sampler_phase = {
                "prep_ms": prep_ms,
                "denoise_ms": denoise_ms,
                "teardown_ms": teardown_ms,
                "progress_events": state.get("progress_events", 0),
                "max_step": state.get("max_step", 0),
                "max_steps": state.get("max_steps", 0),
                "duration_ms": duration_ms,
            }
            self._ksampler_state = None

        if not PROFILING_ENABLED:
            return
        print(f"[comfyapp.perf] node={last_node} class_type={class_type} duration_ms={duration_ms:.1f}")

        if sampler_phase is not None:
            self._log_profile(
                "ksampler_phase",
                node=str(last_node)[:40],
                class_type=class_type[:80],
                prep_ms=sampler_phase["prep_ms"],
                denoise_ms=sampler_phase["denoise_ms"],
                teardown_ms=sampler_phase["teardown_ms"],
                progress_events=sampler_phase["progress_events"],
                max_step=sampler_phase["max_step"],
                max_steps=sampler_phase["max_steps"],
                duration_ms=sampler_phase["duration_ms"],
            )

    def _patch_model_clone_profiling(self, model_patcher_module) -> None:
        if getattr(self, "_model_clone_profile_patched", False):
            return

        for method_name in ("clone", "patch_model", "unpatch_model"):
            original = getattr(model_patcher_module.ModelPatcher, method_name, None)
            if not callable(original):
                continue

            def _wrapped(patcher, *args, __orig=original, __name=method_name, **kwargs):
                started = time.time()
                result = __orig(patcher, *args, **kwargs)
                model_obj = getattr(patcher, "model", None)
                self._log_profile(
                    "model_clone",
                    call=__name,
                    patcher=type(patcher).__name__,
                    model=type(model_obj).__name__[:80],
                    duration_ms=self._profile_ms(started),
                )
                return result

            setattr(model_patcher_module.ModelPatcher, method_name, _wrapped)

        self._model_clone_profile_patched = True

    def _loaded_model_names(self, model_management_module) -> list[str]:
        names: list[str] = []
        loaded = getattr(model_management_module, "current_loaded_models", None)
        if not isinstance(loaded, list):
            loaded = getattr(model_management_module, "loaded_models", None)
        if not isinstance(loaded, list):
            return names
        for entry in loaded:
            candidate = entry
            model_obj = getattr(candidate, "model", None)
            if model_obj is not None:
                names.append(type(model_obj).__name__[:80])
                continue
            model = getattr(candidate, "model_patcher", None)
            model_obj = getattr(model, "model", None)
            if model_obj is not None:
                names.append(type(model_obj).__name__[:80])
                continue
            names.append(type(candidate).__name__[:80])
        names.sort()
        return names

    def _gpu_mem_profile(self):
        alloc_gb = reserved_gb = None
        try:
            import torch
            if torch.cuda.is_available():
                alloc_gb = round(torch.cuda.memory_allocated() / (1024 ** 3), 3)
                reserved_gb = round(torch.cuda.memory_reserved() / (1024 ** 3), 3)
        except Exception:
            pass
        return alloc_gb, reserved_gb

    def _patch_model_management_profiling(self, model_management_module) -> None:
        if getattr(self, "_model_management_profile_patched", False):
            return

        for func_name in ("load_models_gpu", "load_model_gpu", "cleanup_models_gc", "soft_empty_cache", "free_memory"):
            original = getattr(model_management_module, func_name, None)
            if not callable(original):
                continue

            def _wrapped(*args, __orig=original, __name=func_name, **kwargs):
                loaded_before = self._loaded_model_names(model_management_module)
                alloc_before_gb, reserved_before_gb = self._gpu_mem_profile()
                vram_state_before = getattr(model_management_module, "vram_state", None)
                disable_smart_memory = getattr(model_management_module, "DISABLE_SMART_MEMORY", None)
                started = time.time()
                result = __orig(*args, **kwargs)
                loaded_after = self._loaded_model_names(model_management_module)
                alloc_after_gb, reserved_after_gb = self._gpu_mem_profile()
                vram_state_after = getattr(model_management_module, "vram_state", None)
                model_count = "?"
                if args:
                    first = args[0]
                    if isinstance(first, (list, tuple, set)):
                        model_count = len(first)
                    elif first is not None:
                        model_count = 1
                self._log_profile(
                    "model_mgmt",
                    call=__name,
                    models=model_count,
                    loaded_count_before=len(loaded_before),
                    loaded_count_after=len(loaded_after),
                    loaded_before=json.dumps(loaded_before, separators=(",", ":")),
                    loaded_after=json.dumps(loaded_after, separators=(",", ":")),
                    alloc_before_gb=alloc_before_gb if alloc_before_gb is not None else "?",
                    alloc_after_gb=alloc_after_gb if alloc_after_gb is not None else "?",
                    reserved_before_gb=reserved_before_gb if reserved_before_gb is not None else "?",
                    reserved_after_gb=reserved_after_gb if reserved_after_gb is not None else "?",
                    vram_state_before=vram_state_before if vram_state_before is not None else "?",
                    vram_state_after=vram_state_after if vram_state_after is not None else "?",
                    disable_smart_memory=disable_smart_memory if disable_smart_memory is not None else "?",
                    duration_ms=self._profile_ms(started),
                )
                return result

            setattr(model_management_module, func_name, _wrapped)

        self._model_management_profile_patched = True

    def _patch_offload_devices_for_high_vram(self, model_management_module) -> None:
        """When vram_state is HIGH_VRAM, keep text encoders, VAE, and
        intermediate tensors on GPU instead of offloading to CPU.

        ComfyUI's ``unet_offload_device()`` already respects HIGH_VRAM,
        but ``text_encoder_offload_device()``, ``vae_offload_device()`` and
        ``intermediate_device()`` only check ``args.gpu_only``.  This patch
        makes them consistent so that HIGH_VRAM truly means "keep everything
        on GPU when possible".
        """
        if getattr(self, "_offload_devices_patched", False):
            return
        mm = model_management_module
        torch_dev = mm.get_torch_device()
        high_vram = mm.VRAMState.HIGH_VRAM

        for func_name in ("text_encoder_offload_device", "vae_offload_device", "intermediate_device"):
            original = getattr(mm, func_name, None)
            if not callable(original):
                continue

            def _wrapper(*args, __orig=original, **kwargs):
                if getattr(mm, "vram_state", None) == high_vram:
                    return torch_dev
                return __orig(*args, **kwargs)

            setattr(mm, func_name, _wrapper)

        self._offload_devices_patched = True

    def _enable_torch_compile_on_unet(self) -> None:
        """Apply ``torch.compile`` directly to ``diffusion_model._forward``
        on any loaded diffusion model.

        Unlike the old approach (``set_torch_compile_wrapper`` which hooked into
        ``APPLY_MODEL`` wrappers with ``fullgraph=True``), this compiles the
        inner ``_forward`` method of the Flux/UNET module directly.  This avoids:

        - Graph breaks from ``WrapperExecutor`` dispatch in Flux's ``forward()``
        - Wrapper overhead on every denoising step
        - ``fullgraph=True`` raising on Python-level control flow

        Enabled by ``COMFYMODAL_ENABLE_TORCH_COMPILE=1`` env var.
        """
        if not ENABLE_TORCH_COMPILE:
            return
        if getattr(self, "_torch_compile_enabled", False):
            return
        import comfy.model_management as _mm
        import torch

        # torch.compile is disabled on this branch.  It triggers
        # "invalid argument to getCurrentStream" CUDA errors during Dynamo
        # tracing in the post-restore CUDA context — a known interaction
        # between torch.compile and Modal's memory snapshot infrastructure.
        # SageAttention's pre-compiled CUDA/Blackwell kernels already provide
        # optimal performance; torch.compile adds overhead without benefit.
        if not ENABLE_TORCH_COMPILE:
            return

    def _compute_workflow_struct_hash(self, workflow: dict) -> str:
        import hashlib
        _mutable_keys = {"seed", "text", "width", "height", "batch_size"}
        stripped = {}
        for _nid, _spec in workflow.items():
            if not isinstance(_spec, dict):
                continue
            _inp = dict(_spec.get("inputs", {}))
            for _k in _mutable_keys:
                _inp.pop(_k, None)
            stripped[_nid] = {"class_type": _spec.get("class_type"), "inputs": _inp}
        return hashlib.md5(json.dumps(stripped, sort_keys=True).encode()).hexdigest()[:16]

    def _find_missing_workflow_node_classes(self, workflow: dict) -> list[str]:
        """Return sorted list of class_type values referenced in *workflow*
        that are NOT registered in ``nodes.NODE_CLASS_MAPPINGS``.

        Pure read-only scan: no pip install, no model load, no repair.
        """
        import nodes
        requested = sorted({
            spec.get("class_type")
            for spec in workflow.values()
            if isinstance(spec, dict) and spec.get("class_type")
        })
        return [name for name in requested if name not in nodes.NODE_CLASS_MAPPINGS]

    def _compute_near_matches(self, missing_name: str, max_matches: int = 5) -> list[tuple[str, float]]:
        """Return up to *max_matches* registered node class names that
        share tokens with *missing_name*, scored by token overlap.

        Tokenizes on CamelCase, underscores, hyphens, and digit boundaries.
        Scores are ``matched_token_count / union_token_count`` (0-1).
        """
        import re as _re
        import nodes as _near_nodes
        registered = list(getattr(_near_nodes, "NODE_CLASS_MAPPINGS", {}).keys())
        _tokens = set(_re.findall(r"[A-Z]?[a-z]+|[A-Z]+(?=[A-Z][a-z]|\d|$)|\d+|[a-z]+", missing_name))
        if not _tokens:
            return []
        scored = []
        for _cls in registered:
            _cls_tokens = set(_re.findall(r"[A-Z]?[a-z]+|[A-Z]+(?=[A-Z][a-z]|\d|$)|\d+|[a-z]+", _cls))
            if not _cls_tokens:
                continue
            shared = _tokens & _cls_tokens
            if not shared:
                continue
            score = len(shared) / len(_tokens | _cls_tokens)
            scored.append((_cls, round(score, 3)))
        scored.sort(key=lambda x: (-x[1], x[0]))
        return scored[:max_matches]

    def _enforce_workflow_node_classes_available_before_model_work(self, workflow: dict) -> dict:
        """Gate: fail fast if workflow references missing node classes.

        Must be called AFTER custom-node sync and AFTER dependency validation,
        but BEFORE ``_prompt_async_preload``, ``_prompt_async_actual_load``,
        or ``_execute_in_process``.

        Production modes (``off``, ``fail_fast``) raise immediately.
        Dev mode attempts runtime repair then re-checks.
        """
        missing = self._find_missing_workflow_node_classes(workflow)
        mode = self._resolve_requirements_repair_mode()

        if not missing:
            return {
                "missing_node_check_ran": True,
                "missing_nodes_before_model_work": [],
                "missing_node_repair_attempted": False,
                "missing_nodes_after_repair": [],
                "missing_node_blocked_by_mode": False,
            }

        print(
            f"[comfyapp] missing workflow nodes pre_model_work: {missing} "
            f"repair_mode={mode}"
        )

        if mode != "dev":
            _diag = self._collect_missing_node_diagnostics(workflow)
            _near = {m: self._compute_near_matches(m) for m in missing}
            _near_strs = []
            for _m, _matches in _near.items():
                if _matches:
                    _top = ", ".join(f"{n}({s})" for n, s in _matches[:3])
                    _near_strs.append(f"{_m}->[{_top}]")
            _near_msg = ""
            if _near_strs:
                _near_msg = " Near matches (top scored): " + "; ".join(_near_strs[:6]) + "."
            raise RuntimeError(
                "These node classes are missing from nodes.NODE_CLASS_MAPPINGS "
                "after custom-node sync: "
                f"{missing}. "
                "This usually means the corresponding custom node package is "
                "not present, did not import successfully, or changed class "
                "names. "
                "Check ComfyUI custom-node import logs before this request."
                f"{_near_msg} "
                f"repair_mode={mode} "
                f"{_diag}"
            )

        # ── dev mode: attempt runtime repair ──
        req_summary = self._install_custom_node_requirements(force=True)
        import nodes as _repair_nodes
        if self._event_loop is not None:
            self._event_loop.run_until_complete(_repair_nodes.init_extra_nodes())
        missing_after = self._find_missing_workflow_node_classes(workflow)
        if missing_after:
            raise RuntimeError(
                "Workflow still references missing custom node class(es) "
                f"after dev repair: {missing_after}. "
                "Install/sync the required custom nodes manually."
            )
        return {
            "missing_node_check_ran": True,
            "missing_nodes_before_model_work": missing,
            "missing_node_repair_attempted": True,
            "missing_nodes_after_repair": missing_after,
            "missing_node_blocked_by_mode": False,
            "installed": req_summary.get("installed", []),
            "skipped": req_summary.get("skipped", []),
            "failed": req_summary.get("failed", []),
        }

    def _retry_pending_custom_node_registrations(self) -> list[str]:
        """Re-register custom nodes whose entrypoint/schema failed during CPU snapshot.

        After GPU warmup makes CUDA available, retry load_custom_node for each
        pending path.  Uses the retry registry for bookkeeping.
        Returns list of paths that succeeded on retry.
        """
        import nodes as _retry_nodes
        global _CUSTOM_NODE_REGISTRATION_PENDING_RETRY, _CUSTOM_NODE_RETRY_REGISTRY
        _pending = list(_CUSTOM_NODE_REGISTRATION_PENDING_RETRY)
        if not _pending:
            # Also check registry for any failed entries
            _registered_pending = _CUSTOM_NODE_RETRY_REGISTRY.get_pending_paths()
            if _registered_pending:
                _CUSTOM_NODE_REGISTRATION_PENDING_RETRY.update(_registered_pending)
                _pending = list(_CUSTOM_NODE_REGISTRATION_PENDING_RETRY)
            if not _pending:
                return []
        _succeeded = []
        print(
            f"[comfyapp] retrying custom node registration after GPU warmup: "
            f"pending={len(_pending)} paths={_pending}"
        )
        for _path in _pending:
            _CUSTOM_NODE_RETRY_REGISTRY.record_retry(_path)
            try:
                _ok = self._event_loop.run_until_complete(
                    _retry_nodes.load_custom_node(_path)
                )
                if _ok:
                    _succeeded.append(_path)
                    _CUSTOM_NODE_RETRY_REGISTRY.mark_resolved(_path)
                    print(
                        f"[comfyapp] custom_node_retry_success path={_path}"
                    )
                else:
                    _entry = _CUSTOM_NODE_RETRY_REGISTRY.get_entry(_path)
                    if _entry:
                        _entry.record_failure("still_failed", "load_custom_node returned False", "")
                    print(
                        f"[comfyapp] custom_node_retry_still_failed path={_path}"
                    )
            except Exception as _e:
                import traceback as _tb
                _tb.print_exc()
                _exc_type = type(_e).__name__
                _exc_msg = str(_e)
                _tb_text = "".join(_tb.format_exception(_e))
                _CUSTOM_NODE_RETRY_REGISTRY.register_failure(_path, _exc_type, _exc_msg, _tb_text)
                print(
                    f"[comfyapp] custom_node_retry_exception "
                    f"path={_path} error={_e}"
                )
        # Clear only paths that succeeded or are no longer retryable
        for _path in list(_CUSTOM_NODE_REGISTRATION_PENDING_RETRY):
            if not _CUSTOM_NODE_RETRY_REGISTRY.should_retry(_path):
                _CUSTOM_NODE_REGISTRATION_PENDING_RETRY.discard(_path)
        # Log remaining failed entries for diagnostics
        _failed = _CUSTOM_NODE_RETRY_REGISTRY.get_failed_paths()
        if _failed:
            print(f"[comfyapp] custom_node_retry_failed_remaining: {[f['path'] for f in _failed]}")
        return _succeeded

    def _collect_custom_node_import_health(self) -> dict:
        """Log structured summary of custom-node import state after ComfyUI node init."""
        import nodes as _health_nodes
        registered_count = len(getattr(_health_nodes, "NODE_CLASS_MAPPINGS", {}) or {})
        volume_dirs = _iter_syncable_custom_node_dirs(CUSTOM_NODES_PATH) if os.path.isdir(CUSTOM_NODES_PATH) else []
        comfy_root = "/root/comfy/ComfyUI/custom_nodes"
        comfy_entries = sorted(os.listdir(comfy_root)) if os.path.isdir(comfy_root) else []
        symlink_dirs = []
        for _name in comfy_entries:
            _path = os.path.join(comfy_root, _name)
            if os.path.islink(_path):
                try:
                    if os.path.commonpath([os.path.realpath(_path), os.path.realpath(CUSTOM_NODES_PATH)]) == os.path.realpath(CUSTOM_NODES_PATH):
                        symlink_dirs.append(_name)
                except ValueError:
                    pass
        _failures = list(_CUSTOM_NODE_IMPORT_FAILURES)
        result = {
            "registered_node_classes": registered_count,
            "volume_syncable_custom_node_count": len(volume_dirs),
            "volume_syncable_custom_node_dirs": volume_dirs,
            "comfy_custom_node_entry_count": len(comfy_entries),
            "comfy_volume_symlink_count": len(symlink_dirs),
            "comfy_volume_symlink_dirs": symlink_dirs,
            "import_failure_count": len(_failures),
            "import_failures": _failures,
        }
        print(f"[comfyapp] custom_node_import_health: "
              f"registered={registered_count} "
              f"volume_syncable={len(volume_dirs)} "
              f"comfy_entries={len(comfy_entries)} "
              f"comfy_symlinks={len(symlink_dirs)} "
              f"failures={len(_failures)}")
        for _f in _failures:
            print(f"[comfyapp] custom_node_import_failure: "
                  f"name={os.path.basename(_f.get('custom_node_path', '?'))} "
                  f"phase={_f.get('phase', '?')} "
                  f"exception_type={_f.get('exception_type', '?')} "
                  f"message={_f.get('exception_message', '?')[:200]} "
                  f"traceback_available={'yes' if _f.get('traceback') else 'no'}")
        if volume_dirs:
            print(f"[comfyapp] custom_node_import_health: volume_dirs={volume_dirs}")
        if symlink_dirs:
            print(f"[comfyapp] custom_node_import_health: comfy_volume_symlink_dirs={symlink_dirs}")
        return result

    def _collect_missing_node_diagnostics(self, workflow: dict) -> str:
        """Build a short diagnostic string for missing-node error messages."""
        import nodes as _diag_nodes
        parts = []
        try:
            volume_dirs = _iter_syncable_custom_node_dirs(CUSTOM_NODES_PATH) if os.path.isdir(CUSTOM_NODES_PATH) else []
            parts.append(f"volume_syncable_custom_node_dirs={len(volume_dirs)}")
            if len(volume_dirs) <= 50:
                parts.append(f"volume_dirs={sorted(volume_dirs)}")
        except Exception:
            pass
        try:
            cn_root = "/root/comfy/ComfyUI/custom_nodes"
            if os.path.isdir(cn_root):
                raw_entries = sorted(os.listdir(cn_root))
                symlink_dirs = []
                for _name in raw_entries:
                    _path = os.path.join(cn_root, _name)
                    if os.path.islink(_path):
                        try:
                            if os.path.commonpath([os.path.realpath(_path), os.path.realpath(CUSTOM_NODES_PATH)]) == os.path.realpath(CUSTOM_NODES_PATH):
                                symlink_dirs.append(_name)
                        except ValueError:
                            pass
                parts.append(f"comfy_entries={len(raw_entries)}")
                parts.append(f"comfy_symlink_dirs={len(symlink_dirs)}")
        except Exception:
            pass
        parts.append(f"registered_node_classes={len(_diag_nodes.NODE_CLASS_MAPPINGS)}")
        return " | ".join(parts)

    def _repair_missing_workflow_nodes(self, workflow: dict) -> dict:
        missing_before = self._find_missing_workflow_node_classes(workflow)
        if not missing_before or self._event_loop is None:
            return {
                "attempted": False,
                "blocked_by_mode": False,
                "missing_before": missing_before,
                "missing_after": missing_before,
                "installed": [],
                "skipped": [],
            }

        mode = self._resolve_requirements_repair_mode()
        print(f"[comfyapp] missing workflow nodes: {missing_before} (repair_mode={mode})")

        if mode != "dev":
            # Production: never repair. Validation must fail with
            # a clear missing-node message.
            missing_after = missing_before
            print(f"[comfyapp] missing workflow nodes (repair blocked by mode={mode}): {missing_after}")
            return {
                "attempted": False,
                "blocked_by_mode": True,
                "missing_before": missing_before,
                "missing_after": missing_after,
                "installed": [],
                "skipped": [],
            }

        # ── dev mode: attempt runtime repair ──
        import nodes as _repair_nodes
        req_summary = self._install_custom_node_requirements(force=True)
        self._event_loop.run_until_complete(_repair_nodes.init_extra_nodes())
        missing_after = self._find_missing_workflow_node_classes(workflow)
        print(f"[comfyapp] missing workflow nodes after repair: {missing_after}")
        return {
            "attempted": True,
            "blocked_by_mode": False,
            "missing_before": missing_before,
            "missing_after": missing_after,
            "installed": req_summary.get("installed", []),
            "skipped": req_summary.get("skipped", []),
        }

    def _execute_in_process(self, workflow: dict, input_images: dict | None = None, collect_outputs: bool = True, trace: Trace | None = None, modal_options: dict | None = None) -> dict:
        """Execute a ComfyUI workflow directly in-process.

        Args:
            workflow: ComfyUI workflow (dict of node-id → node-spec).
            input_images: Optional mapping of filename → base64-encoded data.
            collect_outputs: When False, skip output collection (warmup mode).
            trace: Optional Trace to populate with timing markers.
            modal_options: Optional output-format / conversion options dict.

        Returns:
            ``{"images": [...], "videos": [...]}`` where each entry contains
            ``filename``, ``data`` (base64), and ``node_id``.
        """
        # Enable torch.compile on UNET models if configured.
        # Patches load_models_gpu so any diffusion model loaded during this
        # execution (or any subsequent one) gets compiled via ComfyUI's
        # set_torch_compile_wrapper.  The compile triggers lazily on the
        # first forward pass during the denoising loop.
        self._enable_torch_compile_on_unet()

        import execution

        prompt_id = str(uuid.uuid4())
        prompt_start_time: float | None = None

        # ── PART 7: Preflight before any model operations ──
        # Must run before: missing-node repair, async preload, actual load,
        # CPU preload, direct warmup, ComfyUI validate_prompt.
        # When called from run_prompt/run_prompt_stream, the preflight already
        # ran via _handle_custom_node_sync_and_dependency_policy().  Skip
        # redundant re-validation to avoid double dependency scanning.
        if not getattr(self, "_preflight_already_ran", False):
            self._preflight_before_prompt_execution(workflow)

        # ── Write input images to ComfyUI's input directory ──
        stage_started = time.time()
        if input_images:
            _materialize_input_images(input_images)
        self._log_profile("inproc_input_prepare", prompt_id=prompt_id[:8], count=len(input_images or {}), duration_ms=self._profile_ms(stage_started))

        # Start the execution window after source-image uploads land on
        # disk so the fallback output scan does not echo them back as
        # generated outputs.
        prompt_start_time = time.time()
        if trace is not None:
            trace.mark("t3d_prompt_start", t=prompt_start_time)

        repair_started = time.time()
        repair_summary = self._repair_missing_workflow_nodes(workflow)
        self._log_profile(
            "inproc_missing_node_repair",
            prompt_id=prompt_id[:8],
            attempted=1 if repair_summary.get("attempted") else 0,
            missing_before=len(repair_summary.get("missing_before", [])),
            missing_after=len(repair_summary.get("missing_after", [])),
            installed=len(repair_summary.get("installed", [])),
            skipped=len(repair_summary.get("skipped", [])),
            blocked=1 if repair_summary.get("blocked_by_mode") else 0,
            duration_ms=self._profile_ms(repair_started),
        )
        if repair_summary.get("blocked_by_mode") and repair_summary.get("missing_before"):
            _mode = self._resolve_requirements_repair_mode()
            raise RuntimeError(
                f"Workflow references missing custom node class(es): "
                f"{repair_summary['missing_before']}. "
                f"Runtime repair is disabled in {_mode} mode. "
                f"Install/sync the custom node and rebuild/deploy the "
                f"Modal image if dependencies changed."
            )

        # ── Fixed-workflow fast path: skip validation if hash matches ──
        _wf_hash = self._compute_workflow_struct_hash(workflow)
        _wf_cache_key = f"wf_exec:{_wf_hash}"
        _wf_cache = getattr(self, "_workflow_exec_cache", {})
        _cached = _wf_cache.get(_wf_cache_key) if collect_outputs else None
        stage_started = time.time()
        if _cached is not None and collect_outputs:
            outputs_to_execute, node_errors = _cached
            valid = True
            error = {}
            _validate_ms = self._profile_ms(stage_started)
            self._log_profile("inproc_validate_cached", prompt_id=prompt_id[:8], hash=_wf_hash, duration_ms=_validate_ms)
        elif not collect_outputs:
            # Warmup-only mode: skip output validation since warmup workflows
            # may have no output consumers (e.g. UNETLoader + DualCLIPLoader).
            # Treat all workflow nodes as outputs to execute.
            outputs_to_execute = list(workflow.keys())
            self._log_profile("inproc_validate_skip", prompt_id=prompt_id[:8], outputs=len(outputs_to_execute), duration_ms=self._profile_ms(stage_started))
            valid = True
            node_errors = {}
            error = {}
        else:
            valid, error, outputs_to_execute, node_errors = self._event_loop.run_until_complete(
                execution.validate_prompt(prompt_id, workflow, None)
            )
            _validate_ms = self._profile_ms(stage_started)
            self._log_profile("inproc_validate", prompt_id=prompt_id[:8], valid=1 if valid else 0, outputs=len(outputs_to_execute or []), duration_ms=_validate_ms)
            # Cache for future requests with same structure
            if valid and outputs_to_execute:
                if not hasattr(self, '_workflow_exec_cache'):
                    self._workflow_exec_cache = {}
                self._workflow_exec_cache[_wf_cache_key] = (outputs_to_execute, node_errors)
        self._last_graph_validate_ms = self._profile_ms(stage_started)
        if trace is not None:
            trace.mark("t3b_validate_done")
        if not valid:
            parts = [error.get("message", str(error)) if isinstance(error, dict) else str(error)]
            if node_errors:
                for nid, info in node_errors.items():
                    ct = info.get("class_type", f"Node {nid}")
                    for e in info.get("errors", []):
                        parts.append(f"{ct}: {e.get('message', 'unknown error')}")
            raise RuntimeError(f"Workflow validation failed: {'; '.join(parts)}")

        self._begin_prompt_profile(workflow, prompt_id, outputs_to_execute)

        # ── Reset execution-level accumulators ──
        self._exec_model_load_io_ms = 0.0
        self._exec_deepcopy_ms = 0.0
        self._log_profile("inproc_prep_done", prompt_id=prompt_id[:8], duration_ms=self._profile_ms(stage_started))
        if trace is not None:
            trace.mark("t3c_prep_done")
        _exec_stage = time.time()

        # ── Instrument executor for overhead breakdown ──
        import execution as _exec_mod
        _perf_data = {}
        _exec_profiling = _resolve_runtime_flag('exec_profile', '0')
        if _exec_profiling and not getattr(_exec_mod, '_comfy_modal_exec_patched', False):
            _orig_exec_fn = _exec_mod.execute
            _exec_prof_data = {"nodes": {}, "_first_call_start": None, "_last_call_end": None, "_call_count": 0}
            async def _profiled_exec(*args, **kwargs):
                _t0 = time.perf_counter()
                if _exec_prof_data["_first_call_start"] is None:
                    _exec_prof_data["_first_call_start"] = _t0
                try:
                    return await _orig_exec_fn(*args, **kwargs)
                finally:
                    _t1 = time.perf_counter()
                    _exec_prof_data["_last_call_end"] = _t1
                    _exec_prof_data["_call_count"] += 1
                    _node_id = kwargs.get('current_item') or (args[3] if len(args) > 3 else None)
                    _ct = "?"
                    try:
                        _dyn = kwargs.get('dynprompt') or (args[1] if len(args) > 1 else None)
                        if _dyn and _node_id is not None:
                            _n = _dyn.get_node(str(_node_id))
                            if _n:
                                _ct = _n.get('class_type', '?')
                    except Exception:
                        pass
                    _duration_ms = (_t1 - _t0) * 1000
                    _nodes = _exec_prof_data["nodes"]
                    if _ct not in _nodes:
                        _nodes[_ct] = {"ms": 0.0, "count": 0}
                    _nodes[_ct]["ms"] += _duration_ms
                    _nodes[_ct]["count"] += 1
            _exec_mod.execute = _profiled_exec
            _exec_mod._comfy_modal_exec_patched = True
            _exec_mod._comfy_modal_exec_prof = _exec_prof_data

        # ── Instrument sampler for per-step breakdown ──
        _sampler_profiling = _resolve_runtime_flag('sampler_profile', '0')
        if _sampler_profiling:
            import comfy.samplers as _samplers_mod
            if not getattr(_samplers_mod, '_comfy_modal_sampler_prof_patched', False):
                _orig_ksampler_sample = _samplers_mod.KSAMPLER.sample
                _sampler_prof_data = {}
                def _profiled_ksampler_sample(self, model_wrap, sigmas, extra_args, callback, noise, latent_image=None, denoise_mask=None, disable_pbar=False):
                    _t0 = time.perf_counter()
                    _times = {}
                    _last_cb_time = None
                    _step_count = 0
                    if callback is not None:
                        _orig_cb = callback
                        def _ts_cb(step_idx, denoised, x, total_steps):
                            nonlocal _last_cb_time, _step_count
                            _now = time.perf_counter()
                            if _last_cb_time is None:
                                _times["setup_ms"] = (_now - _t0) * 1000
                            else:
                                _step_count += 1
                                _times[f"step_{_step_count}_ms"] = (_now - _last_cb_time) * 1000
                            _last_cb_time = _now
                            return _orig_cb(step_idx, denoised, x, total_steps)
                        callback = _ts_cb
                    result = _orig_ksampler_sample(self, model_wrap, sigmas, extra_args, callback, noise, latent_image, denoise_mask, disable_pbar)
                    _t1 = time.perf_counter()
                    if _last_cb_time is not None:
                        _times["teardown_ms"] = (_t1 - _last_cb_time) * 1000
                    _times["total_ms"] = (_t1 - _t0) * 1000
                    _sampler_prof_data.update(_times)
                    return result
                _samplers_mod.KSAMPLER.sample = _profiled_ksampler_sample
                _samplers_mod._comfy_modal_sampler_prof_patched = True
                _samplers_mod._comfy_modal_sampler_prof = _sampler_prof_data

        # ── Instrument guider for overhead breakdown ──
        _guider_profiling = _resolve_runtime_flag('guider_profile', '0')
        if _guider_profiling:
            import comfy.samplers as _gs_mod
            import comfy.sampler_helpers as _gsh_mod
            if not getattr(_gs_mod, '_comfy_modal_guider_prof_patched', False):
                _guider_prof_data = {"segments": {}}
                def _gwrap(label):
                    def _deco(orig_fn):
                        def _wrapper(*args, **kwargs):
                            _t0 = time.perf_counter()
                            try:
                                return orig_fn(*args, **kwargs)
                            finally:
                                _d = (time.perf_counter() - _t0) * 1000
                                segs = _guider_prof_data["segments"]
                                segs[label] = segs.get(label, 0.0) + _d
                        return _wrapper
                    return _deco
                _gs_mod.CFGGuider.sample = _gwrap("guider_sample")(_gs_mod.CFGGuider.sample)
                _gs_mod.CFGGuider.outer_sample = _gwrap("guider_outer_sample")(_gs_mod.CFGGuider.outer_sample)
                _gs_mod.CFGGuider.inner_sample = _gwrap("guider_inner_sample")(_gs_mod.CFGGuider.inner_sample)
                _gsh_mod.prepare_sampling = _gwrap("prepare_sampling")(_gsh_mod.prepare_sampling)
                _gsh_mod.cleanup_models = _gwrap("cleanup_models")(_gsh_mod.cleanup_models)
                _gs_mod._comfy_modal_guider_prof_patched = True
                _gs_mod._comfy_modal_guider_prof = _guider_prof_data

        # ── Deep sampler wrapper profiling ──
        _deep_profiling = _resolve_runtime_flag('deep_profile', '0')
        if _deep_profiling:
            import comfy.sampler_helpers as _dsh_mod
            import comfy.model_management as _dmm_mod
            import comfy_extras.nodes_custom_sampler as _dcs_mod
            _deep_prof = {}
            def _dp_wrap(module, name, label):
                orig = getattr(module, name, None)
                if orig is None:
                    return
                def _dp(*args, **kwargs):
                    _t0 = time.perf_counter()
                    try:
                        return orig(*args, **kwargs)
                    finally:
                        _deep_prof[label] = _deep_prof.get(label, 0) + (time.perf_counter() - _t0) * 1000
                setattr(module, name, _dp)
            _dp_wrap(_dsh_mod, 'get_additional_models', 'ps_get_additional_models')
            _dp_wrap(_dsh_mod, 'get_additional_models_from_model_options', 'ps_get_additional_models_opts')
            _dp_wrap(_dsh_mod, 'estimate_memory', 'ps_estimate_memory')
            # ── Comprehensive load_models_gpu profiler + fastpath diagnostics ──
            _fp_dryrun = _resolve_runtime_flag('lmg_fastpath_dryrun', '0')
            _fp_enabled = _resolve_runtime_flag('lmg_fastpath', '0')
            _orig_lmg = _dmm_mod.load_models_gpu
            _lmg_calls = []
            def _profiled_lmg(models, memory_required=0, force_patch_weights=False, minimum_memory_required=None, force_full_load=False):
                _classes = [m.model.__class__.__name__ for m in models if hasattr(m, 'model')]
                _lm_models = list(getattr(_dmm_mod, 'current_loaded_models', []))
                _loaded_before = len(_lm_models)
                # Identity diagnostics for each requested model
                _diag = []
                _matched_idx = None
                _model_patcher = models[0] if models else None
                for mi, m in enumerate(models):
                    _m_key = getattr(m, '_comfy_modal_stable_key', None) if hasattr(m, 'model') else None
                    _md = {
                        "class": m.model.__class__.__name__ if hasattr(m, 'model') else '?',
                        "patcher_id": id(m) if hasattr(m, 'model') else 0,
                        "model_id": id(m.model) if hasattr(m, 'model') else 0,
                        "matched_idx": -1,
                        "same_patcher": False,
                        "stable_key_match": False,
                        "lm_stable_key": None,
                    }
                    for li, lm in enumerate(_lm_models):
                        _lm_p = lm.model if hasattr(lm, 'model') else None
                        if _lm_p is not None:
                            if _lm_p is m:
                                _md["matched_idx"] = li
                                _md["same_patcher"] = True
                                _matched_idx = li
                                break
                            # Stable key fallback match
                            _lm_key = getattr(_lm_p, '_comfy_modal_stable_key', None)
                            if _m_key and _lm_key and _m_key.get("resolved_path") and _lm_key.get("resolved_path"):
                                if _m_key["resolved_path"] == _lm_key["resolved_path"] and _m_key["options_str"] == _lm_key["options_str"]:
                                    _md["matched_idx"] = li
                                    _md["stable_key_match"] = True
                                    _md["lm_stable_key"] = _lm_key
                                    _matched_idx = li
                                    break
                    _diag.append(_md)
                # Fastpath decision
                _would_fastpath = _matched_idx is not None and len(models) == 1
                _fp_reject = "none" if _would_fastpath else ("no_identity_match" if _matched_idx is None else "multiple_models")
                _vram_ok = getattr(_dmm_mod, 'vram_state', None) == _dmm_mod.VRAMState.HIGH_VRAM
                # ── Guarded fast path execution ──
                if _fp_enabled and _would_fastpath and _vram_ok:
                    _t0 = time.perf_counter()
                    _lm = _lm_models[_matched_idx]
                    _lm.currently_used = True
                    _t1 = time.perf_counter()
                    _call_data = {
                        "ms": round((_t1 - _t0) * 1000, 1),
                        "models": _classes,
                        "count": len(models),
                        "loaded_before": _loaded_before,
                        "loaded_after": len(getattr(_dmm_mod, 'current_loaded_models', [])),
                        "identity": _diag,
                        "fastpath_hit": True,
                        "fastpath_saved_ms": 0,
                    }
                    _lmg_calls.append(_call_data)
                    _deep_prof["lmg"] = list(_lmg_calls)
                    return
                else:
                    _t0 = time.perf_counter()
                    try:
                        return _orig_lmg(models, memory_required, force_patch_weights, minimum_memory_required, force_full_load)
                    finally:
                        _t1 = time.perf_counter()
                        _call_data = {
                            "ms": round((_t1 - _t0) * 1000, 1),
                            "models": _classes,
                            "count": len(models),
                            "loaded_before": _loaded_before,
                            "loaded_after": len(getattr(_dmm_mod, 'current_loaded_models', [])),
                            "identity": _diag,
                            "would_fastpath": _would_fastpath,
                            "fp_reject": _fp_reject if not _would_fastpath else ("not_high_vram" if not _vram_ok else "none"),
                            "fastpath_hit": False,
                        }
                        _lmg_calls.append(_call_data)
                        _deep_prof["lmg"] = list(_lmg_calls)
            _dmm_mod.load_models_gpu = _profiled_lmg
            # ── Warmup registration logging ──
            _warmup_lm = list(getattr(_dmm_mod, 'current_loaded_models', []))
            _deep_prof["warmup"] = {
                "registered_count": len(_warmup_lm),
                "entries": [{
                    "class": lm.model.__class__.__name__ if hasattr(lm, 'model') else '?',
                    "actual_model": lm.model.model.__class__.__name__ if hasattr(lm, 'model') and hasattr(lm.model, 'model') else '?',
                    "actual_model_id": id(lm.model.model) if hasattr(lm, 'model') and hasattr(lm.model, 'model') else 0,
                    "patcher_id": id(lm) if hasattr(lm, 'model') else 0,
                } for lm in _warmup_lm],
            }
            # KSAMPLER.sample setup proved ~0.35ms — no further breakdown needed
            import comfy as _comfy_mod
            _comfy_mod._comfy_modal_deep_prof = _deep_prof

        # ── Execute ──
        # PromptExecutor.reset() only clears ComfyUI's per-prompt execution
        # caches/UI state. It does not unload the warm model/runtime state we
        # want to preserve across prompts.
        self._executor.reset()
        stage_started = time.time()
        if trace is not None:
            trace.mark("t3e_execution_start", t=stage_started)
        self._executor.execute(
            prompt=workflow,
            prompt_id=prompt_id,
            extra_data={"client_id": prompt_id},
            execute_outputs=outputs_to_execute,
        )
        total_exec_ms = self._profile_ms(stage_started)
        _deepcopy_total = getattr(self, "_exec_deepcopy_ms", 0.0)
        self._log_profile(
            "inproc_execute", prompt_id=prompt_id[:8],
            duration_ms=total_exec_ms,
            load_io_ms=round(self._exec_model_load_io_ms, 1),
            deepcopy_ms=round(_deepcopy_total, 1),
            non_io_exec_ms=round(max(0.0, total_exec_ms - self._exec_model_load_io_ms - _deepcopy_total), 1),
            success=1 if getattr(self._executor, "success", True) else 0,
        )
        # Commit t4..t7 stage windows from the node events to the trace.
        if trace is not None:
            self._commit_stage_windows_to_trace(trace)
        # t8 — final image was written by SaveImage.  The actual file
        # mtime is a more truthful marker than "executor returned" so we
        # query the youngest png/jpg in the output directory that
        # appeared during this prompt's window.
        if trace is not None and collect_outputs:
            try:
                from pathlib import Path as _P
                out_dir = _P("/root/comfy/ComfyUI/output")
                if out_dir.is_dir():
                    candidates = []
                    for ext in (".png", ".jpg", ".jpeg", ".webp", ".gif", ".mp4", ".webm"):
                        for f in out_dir.glob(f"*{ext}"):
                            try:
                                mt = f.stat().st_mtime
                            except OSError:
                                continue
                            if mt >= prompt_start_time - 1.0:
                                candidates.append((mt, f))
                    if candidates:
                        latest_mt = max(c[0] for c in candidates)
                        trace.mark("t8_image_written", t=latest_mt)
            except Exception as exc:
                print(f"[comfyapp] trace t8 lookup failed: {exc}")
        if getattr(self._executor, "success", True) is False:
            messages = getattr(self._executor, "status_messages", [])
            error_messages = []
            for event, payload in messages:
                if event == "execution_error" and isinstance(payload, dict):
                    error_messages.append(payload.get("exception_message", str(payload)))
            detail = "; ".join(error_messages) if error_messages else "ComfyUI execution failed"
            raise RuntimeError(detail)

        if not collect_outputs:
            # Store executor timing breakdown for warmup analysis
            self._warmup_exec_timing = {
                "we_load_io_ms": round(self._exec_model_load_io_ms, 1),
                "we_deepcopy_ms": round(_deepcopy_total, 1),
                "we_non_io_ms": round(max(0.0, total_exec_ms - self._exec_model_load_io_ms - _deepcopy_total), 1),
            }
            return {"images": [], "videos": [], "_known_good_marked": False}

        # ── PART 11: Mark known-good after successful execution ──
        # Only real prompts (collect_outputs=True) that succeed get marked.
        # Warmup-only prompts and failed prompts do not become known-good.
        _known_good_marked = False
        try:
            _known_workflow_hash = self._compute_workflow_struct_hash(workflow)
            _known_stack = extract_requested_model_stack(workflow)
            _known_profile = stack_to_profile(_known_stack)
            if _known_profile:
                _known_good_marked = _mark_known_good_workflow_profile(_known_workflow_hash, _known_profile)
                if _known_good_marked:
                    print(
                        f"[comfyapp] marked known-good workflow hash={_known_workflow_hash} "
                        f"profile={json.dumps(_known_profile, separators=(',',':'))}"
                    )
        except Exception as _kg_exc:
            print(f"[comfyapp] failed to mark known-good: {_kg_exc}")
        stage_started = time.time()
        if trace is not None:
            trace.mark("t7b_collect_start", t=stage_started)
        result = self._collect_in_process_outputs(prompt_id, prompt_start_time=prompt_start_time, modal_options=modal_options)
        self._log_profile("inproc_collect", prompt_id=prompt_id[:8], images=len(result.get("images", [])), videos=len(result.get("videos", [])), duration_ms=self._profile_ms(stage_started))
        if trace is not None:
            trace.mark("t8b_outputs_collected")
        result["_known_good_marked"] = _known_good_marked
        return result

    def _collect_in_process_outputs(self, prompt_id: str, prompt_start_time: float | None = None, modal_options: dict | None = None) -> dict:
        """Read generated outputs after an in-process execution.

        Tries four sources, in priority order, returning the union:

        1. ``self._executor.history_result`` — set by ``PromptExecutor.execute()``
           when the last execution populated it.
        2. ``self._dummy_server.prompt_queue.history[prompt_id]`` — populated
           by the PromptQueue (typically empty for direct executor calls).
        3. **Directory scan scoped to the prompt's execution window** —
           finds any image/video file written to ComfyUI's ``output``,
           ``temp``, or ``input`` directory *after* ``prompt_start_time``.
           This catches every file the workflow actually wrote regardless
           of whether history metadata is structured as expected.
        4. **Directory scan of the most-recent 20 files** — last-resort
           fallback when no ``prompt_start_time`` is available (e.g. older
           callers).

        Returns ``{"images": [...], "videos": [...], "outputs": {node_id: {key: [...]}}}``.
        The ``outputs`` map preserves the original per-node output-key structure
        (e.g. ``"a_images"``, ``"b_images"``) so the caller can forward it to the
        frontend intact.  ``images`` and ``videos`` are flat lists of the same
        entries for backward compatibility.

        Each image/video entry is ``{"filename", "data" (base64), "node_id"}``.

        The ``type`` field on image metadata is honoured: ``output`` is
        looked up under ``ComfyUI/output``, ``temp`` under ``ComfyUI/temp``,
        ``input`` under ``ComfyUI/input``.  The supplemental directory-scan
        path only walks ``output`` and ``temp`` so uploaded source images do
        not get returned as generated outputs.
        """
        _oc_t0 = time.time()
        import base64
        from pathlib import Path

        images: list[dict] = []
        videos: list[dict] = []
        seen_filenames: set[str] = set()  # de-dupe across sources
        per_node_outputs: dict[str, dict[str, list[dict]]] = {}

        comfy_root = Path("/root/comfy/ComfyUI")
        dir_for_type = {
            "output": comfy_root / "output",
            "temp": comfy_root / "temp",
            "input": comfy_root / "input",
        }

        # ── Conversion state ──────────────────────────────────────────
        _mo = modal_options or {}
        _output_fmt = _mo.get("output_format", _CONVERTER_DEFAULTS["output_format"])
        _quality = _mo.get("quality", _CONVERTER_DEFAULTS["quality"])
        _wlc = _mo.get("webp_lossless_compression", _CONVERTER_DEFAULTS["webp_lossless_compression"])
        _conversion_meta: list[dict] = []
        _oc_timing = {
            "history_fetch_ms": 0.0,
            "file_scan_ms": 0.0,
            "read_total_ms": 0.0,
            "conversion_total_ms": 0.0,
            "return_packaging_ms": 0.0,
            "files_read": 0,
            "bytes_read": 0,
            "bytes_returned": 0,
            "images_found": 0,
            "videos_found": 0,
            "files_returned": 0,
        }
        print("[timing.output] collection_start")

        def _is_rgthree_temp_file(fp: Path) -> bool:
            """Return True if *fp* is an rgthree compare temp file."""
            name = fp.name.lower()
            return ("_temp_" in name or name.endswith("_temp")) and "rgthree" in name

        def _read_and_store(fp: Path, node_id: str, animated: bool, output_key: str | None = None, allow_rgthree_temp: bool = True) -> None:
            """Read a single file and append to images/videos.

            When ``output_key`` is given the entry is also recorded in
            ``per_node_outputs[node_id][output_key]``.
            """
            if not fp.is_file():
                return
            if not allow_rgthree_temp and _is_rgthree_temp_file(fp):
                return
            key = str(fp)
            if key in seen_filenames:
                return
            seen_filenames.add(key)
            _r_start = time.time()
            raw = fp.read_bytes()
            _r_ms = round((time.time() - _r_start) * 1000, 1)
            _oc_timing["read_total_ms"] += _r_ms
            _oc_timing["files_read"] += 1
            _oc_timing["bytes_read"] += len(raw)
            if _r_ms > 100:
                print(f"[comfyapp] slow output read: file={fp.name} size={len(raw)} duration_ms={_r_ms}")

            # ── Apply output format conversion ──────────────────────
            is_animated = animated or fp.suffix.lower() in (".gif", ".mp4", ".webm")
            do_convert = (
                _output_fmt != "original"
                and not is_animated
                and fp.suffix.lower() in (".png", ".jpg", ".jpeg")
            )
            converted = None
            _conv_start = time.time()
            if do_convert:
                converted = _convert_image_bytes(
                    raw,
                    output_format=_output_fmt,
                    quality=_quality,
                    webp_lossless_compression=_wlc,
                )
                out_bytes = converted["bytes"]
                out_filename = _change_extension(fp.name, converted["file_ext"])
                _conversion_meta.append({
                    "filename": out_filename,
                    "node_id": node_id,
                    "output_format": converted["output_format"],
                    "mime_type": converted["mime_type"],
                    "file_ext": converted["file_ext"],
                    "original_size_bytes": converted["original_size_bytes"],
                    "returned_size_bytes": converted["returned_size_bytes"],
                    "conversion_time_ms": converted["conversion_time_ms"],
                    "quality": converted.get("quality"),
                    "webp_lossless_compression": converted.get("webp_lossless_compression"),
                    "fallback": converted.get("fallback", False),
                    "error": converted.get("error"),
                })
                _oc_timing["conversion_total_ms"] += converted["conversion_time_ms"]
                print(
                    f"[comfyapp.convert] fmt={_output_fmt} "
                    f"orig={converted['original_size_bytes']}B "
                    f"out={converted['returned_size_bytes']}B "
                    f"time={converted['conversion_time_ms']}ms "
                    f"file={out_filename}"
                    + (f" fallback_err={converted['error']}" if converted.get("fallback") else "")
                )
            else:
                out_bytes = raw
                out_filename = fp.name
            _oc_timing["conversion_total_ms"] += round((time.time() - _conv_start) * 1000, 1) - (converted["conversion_time_ms"] if converted else 0)

            entry = {"filename": out_filename, "data": base64.b64encode(out_bytes).decode(), "node_id": node_id}
            _oc_timing["bytes_returned"] += len(entry["data"])
            if animated or fp.suffix.lower() in (".gif", ".mp4", ".webm", ".webp"):
                videos.append(entry)
                _oc_timing["videos_found"] += 1
            else:
                images.append(entry)
                _oc_timing["images_found"] += 1
            _oc_timing["files_returned"] += 1
            # Per-file timing log
            print(f"[timing.output.file] filename={fp.name} read_ms={_r_ms:.1f} bytes_in={len(raw)} bytes_out={len(entry['data'])}")
            if output_key is not None:
                per_node_outputs.setdefault(node_id, {}).setdefault(output_key, []).append(entry)

        def _scan_dir_for_files(base: Path, since_ts: float | None, limit: int = 20) -> None:
            """Scan a base directory for image/video files, optionally
            filtered to ``mtime >= since_ts``.  Adds to images/videos via
            ``_read_and_store`` (flat lists only, no per-node tracking)."""
            if not base.is_dir():
                return
            candidates: list[Path] = []
            for f in base.iterdir():
                if not f.is_file():
                    continue
                if f.suffix.lower() not in (".png", ".jpg", ".jpeg", ".webp", ".gif", ".mp4", ".webm"):
                    continue
                if since_ts is not None:
                    try:
                        if f.stat().st_mtime < since_ts - 1.0:  # 1s slack for clock drift
                            continue
                    except OSError:
                        continue
                candidates.append(f)
            candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
            for f in candidates[:limit]:
                animated = f.suffix.lower() in (".gif", ".mp4", ".webm")
                _read_and_store(f, node_id="0", animated=animated)

        def _process_history_source(node_out: dict, node_id: str) -> None:
            """Read all image-bearing entries from a history output dict."""
            for output_key, img in _iter_image_entries(node_out):
                base = dir_for_type.get(img.get("type", "output"), comfy_root / "output")
                sub = img.get("subfolder", "") or ""
                fp = base / sub / img.get("filename", "")
                if not fp.is_file():
                    print(f"[comfyapp] history-listed file not found: {fp}")
                    continue
                if prompt_start_time is not None:
                    try:
                        if fp.stat().st_mtime < prompt_start_time - 1.0:
                            print(f"[comfyapp] skipping stale history-listed file (mtime < prompt_start): {fp.name}")
                            continue
                    except OSError:
                        continue
                animated = bool(node_out.get("animated", False)) or output_key == "gifs"
                _read_and_store(fp, node_id=node_id, animated=animated, output_key=output_key, allow_rgthree_temp=True)

        # ── Source 1: executor.history_result ─────────────────────────
        _s_hf = time.time()
        outputs: dict = {}
        try:
            history_result = getattr(self._executor, "history_result", None)
            if isinstance(history_result, dict):
                outputs = history_result.get("outputs", {}) or {}
        except Exception as exc:
            print(f"[comfyapp] executor.history_result read failed: {exc}")
        _oc_timing["history_fetch_ms"] = round((time.time() - _s_hf) * 1000, 1)
        if outputs:
            for node_id, node_out in outputs.items():
                if not isinstance(node_out, dict):
                    continue
                _process_history_source(node_out, node_id)

        # ── Source 2: dummy_server.prompt_queue.history[prompt_id] ───
        if not seen_filenames:
            try:
                history = self._dummy_server.prompt_queue.history
                if isinstance(history, dict) and prompt_id in history:
                    queue_outputs = history[prompt_id].get("outputs", {}) or {}
                    if queue_outputs:
                        for node_id, node_out in queue_outputs.items():
                            if not isinstance(node_out, dict):
                                continue
                            _process_history_source(node_out, node_id)
            except Exception as exc:
                print(f"[comfyapp] prompt_queue.history read failed: {exc}")

        # ── Source 3: directory scan scoped to the prompt's time window ─
        _s_fs = time.time()
        # Always run as a supplement — catches files the workflow wrote
        # that the executor didn't return in its history metadata.
        if prompt_start_time is not None:
            for base in (comfy_root / "output", comfy_root / "temp"):
                _scan_dir_for_files(base, since_ts=prompt_start_time)
        _oc_timing["file_scan_ms"] = round((time.time() - _s_fs) * 1000, 1)

        # ── Source 4: most-recent-files fallback ──────────────────────
        if not seen_filenames and prompt_start_time is None:
            print("[comfyapp] output history not found, scanning output directory")
            _scan_dir_for_files(comfy_root / "output", since_ts=None)

        if not seen_filenames:
            print(
                f"[comfyapp] no outputs found for prompt_id={prompt_id[:8]} "
                f"(history_result_empty={not bool(outputs)} "
                f"prompt_start_time={'set' if prompt_start_time else 'none'})"
            )
        print(f"[comfyapp] collected {len(images)} images, {len(videos)} videos")
        print(f"[comfyapp] sanity: prompt_id={prompt_id[:8]} "
              f"job_id={prompt_id[:8]} "
              f"sampler_started={'yes' if images or outputs else 'no'} "
              f"output_files={len(images)} "
              f"filenames={[img['filename'] for img in images]}")
        _files_from_history = sum(
            1 for node_outs in outputs.values() if isinstance(node_outs, dict)
            for _ in _iter_image_entries(node_outs)
        )
        _files_returned = len(images) + len(videos)
        _skipped_temp = 0
        print(f"[output_collect] prompt_id={prompt_id[:8]}")
        print(f"[output_collect] job_id={prompt_id[:8]}")
        print(f"[output_collect] job_start={prompt_start_time or 0}")
        print(f"[output_collect] files_from_history={_files_from_history}")
        print(f"[output_collect] files_returned={_files_returned}")
        print(f"[output_collect] skipped_stale=0")
        print(f"[output_collect] skipped_temp={_skipped_temp}")
        _oc_total = round((time.time() - _oc_t0) * 1000, 1)
        _oc_timing["return_packaging_ms"] = round(_oc_total - _oc_timing.get("history_fetch_ms", 0) - _oc_timing.get("file_scan_ms", 0) - _oc_timing.get("read_total_ms", 0) - _oc_timing.get("conversion_total_ms", 0), 1)
        print(
            f"[timing.output] output_collection_total_ms={_oc_total} "
            f"history_fetch_ms={_oc_timing.get('history_fetch_ms', 0)} "
            f"file_scan_ms={_oc_timing.get('file_scan_ms', 0)} "
            f"read_total_ms={round(_oc_timing.get('read_total_ms', 0), 1)} "
            f"conversion_total_ms={round(_oc_timing.get('conversion_total_ms', 0), 1)} "
            f"return_packaging_ms={_oc_timing.get('return_packaging_ms', 0)} "
            f"files_read={_oc_timing.get('files_read', 0)} "
            f"images_found={_oc_timing.get('images_found', 0)} "
            f"videos_found={_oc_timing.get('videos_found', 0)} "
            f"files_returned={_oc_timing.get('files_returned', 0)} "
            f"bytes_read={_oc_timing.get('bytes_read', 0)} "
            f"bytes_returned={_oc_timing.get('bytes_returned', 0)}"
        )
        return {
            "images": images,
            "videos": videos,
            "outputs": per_node_outputs,
            "_conversion_meta": _conversion_meta,
            "_oc_timing": _oc_timing,
        }

    def _select_backend(self) -> str:
        """Return the backend to use, sticky on subprocess fallback."""
        if getattr(self, "_backend_fallback", False):
            return "subprocess"
        return DEFAULT_EXECUTION_BACKEND

    @contextlib.contextmanager
    def _force_cpu_during_snapshot(self):
        """Lie to PyTorch about CUDA availability during snap=True.

        Modal's GPU memory snapshot captures the parent's CUDA driver state
        (context handles, streams, events) along with the Python state.
        On restore the driver context is fresh — the captured handles are
        dangling pointers → SIGSEGV (exit code 139) the first time the
        restored process touches a CUDA tensor.

        Workaround: monkey-patch ``torch.cuda.is_available()`` and
        ``torch.cuda.current_device()`` to lie about CUDA during snap=True
        so ComfyUI's ``model_management`` thinks there is no GPU and skips
        all CUDA initialisation.  The snapshot then captures a CPU-only
        Python state (imported modules, registered nodes, PromptExecutor,
        DummyServer, etc.) with zero CUDA driver state.

        On restore, ``_warmup_cuda()`` reconnects the real GPU; the first
        ``executor.execute()`` allocates fresh CUDA tensors.

        Additionally, this context manager blocks imports of CUDA C
        extension modules (``sageattn_qk_int8_pv_fp16_cuda``,
        ``sageattn_qk_int8_pv_fp8_cuda``, and any other module matching
        the ``*_cuda`` / ``cuda_*`` pattern).  These C extensions'
        ``PyInit_*`` functions call CUDA APIs directly (bypassing the
        ``torch.cuda.is_available()`` patch) and allocate GPU memory
        during module load — which would land in the snapshot and
        trigger SIGSEGV on restore.  The block makes any custom node
        that imports sageattention fall back to Triton mode for the
        duration of the snapshot; restore later selects a baked runtime
        mode after CUDA is available again.

        This is the technique used by tolgaouz/modal-comfy-worker for the
        "ComfyUI Cold Starts Down to Under 3 Seconds on Modal" example.
        The patch is removed in the ``finally`` block, so the snapshot
        does **not** contain the monkey-patched functions.
        """
        import sys
        import warnings
        import torch

        comfy_path = "/root/comfy/ComfyUI"
        if comfy_path not in sys.path:
            sys.path.insert(0, comfy_path)
        import comfy.cli_args

        # ── Monkey-patch torch.cuda query functions ──
        # The first access to torch.cuda triggers its __init__.py which calls
        # _check_driver() — this detects the real GPU and emits a noisy
        # "compute capability (CC) 12.0 is unsupported" warning.  During
        # snap=True we deliberately hide the GPU; suppress the warning at
        # the import point.
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            original_is_available = torch.cuda.is_available
            original_current_device = torch.cuda.current_device
        original_args_cpu = getattr(comfy.cli_args.args, "cpu", False)
        torch.cuda.is_available = lambda: False
        torch.cuda.current_device = lambda: torch.device("cpu")
        # ComfyUI's model_management defaults cpu_state=GPU at import time
        # unless CLI args explicitly force CPU mode. During snap=True we
        # must also lie at the ComfyUI argument layer so its import-time
        # feature probes don't touch CUDA.
        comfy.cli_args.args.cpu = True

        # ── Block CUDA C extension imports during snapshot creation ─────
        # The C extension's PyInit_* runs CUDA driver calls (cudaGetDevice,
        # cudaMalloc, …) that bypass torch.cuda.is_available and create
        # state in the captured snapshot.  Raising ImportError makes
        # sageattention's __init__.py fall back to its Triton path.
        class _BlockCudaModuleImport:
            def find_spec(self, name, path=None, target=None):
                if self._is_cuda_module(name):
                    raise ImportError(
                        f"[comfyapp] blocked CUDA module import "
                        f"{name!r} during snap=True to keep snapshot clean"
                    )
                return None

            def find_module(self, name, path=None):
                if self._is_cuda_module(name):
                    return self
                return None

            def load_module(self, name):
                raise ImportError(
                    f"[comfyapp] blocked CUDA module import "
                    f"{name!r} during snap=True to keep snapshot clean"
                )

            @staticmethod
            def _is_cuda_module(name: str) -> bool:
                # Matches:
                #   sageattn_qk_int8_pv_fp16_cuda
                #   sageattn_qk_int8_pv_fp8_cuda
                #   comfy_*/cuda_*
                #   *_cuda
                #   cuda_*
                return (
                    name.endswith("_cuda")
                    or name.startswith("cuda_")
                    or "_cuda_" in name
                )

        blocker = _BlockCudaModuleImport()
        sys.meta_path.insert(0, blocker)

        try:
            yield
        finally:
            try:
                sys.meta_path.remove(blocker)
            except ValueError:
                pass
            comfy.cli_args.args.cpu = original_args_cpu
            torch.cuda.is_available = original_is_available
            torch.cuda.current_device = original_current_device

    @contextlib.contextmanager
    def _force_triton_during_snapshot(self):
        """Block SageAttention C extensions during snap=True for GPU snapshots.

        With ``enable_gpu_snapshot=True`` we want ComfyUI to initialise with
        GPU so Modal captures the CUDA context, compiled kernels, and any
        warmup model tensors.  However, SageAttention's ``PyInit_*`` in C
        extension .so files calls CUDA driver APIs directly (cudaGetDevice,
        cudaMalloc, …) — these create raw CUDA driver handles that become
        dangling pointers on snapshot restore → SIGSEGV.

        This manager **_only_** blocks C extension imports (via a
        ``sys.meta_path`` finder).  It does **_not_** monkey-patch
        ``torch.cuda.is_available`` or ``comfy.cli_args.args.cpu``, so
        ComfyUI naturally detects the GPU during startup.  SageAttention
        falls back to its Triton path, which uses torch CUDA APIs that
        Modal properly checkpoints.

        On restore, ``_select_sage_runtime_mode()`` detects that the real
        GPU CUDA backend is available and switches to the baked CUDA path
        for subsequent prompt executions.
        """
        import sys

        class _BlockCudaModuleImport:
            def find_spec(self, name, path=None, target=None):
                if _is_cuda_module(name):
                    raise ImportError(
                        f"[comfyapp] blocked CUDA module import "
                        f"{name!r} during snap=True to keep snapshot clean"
                    )
                return None

            def find_module(self, name, path=None):
                if _is_cuda_module(name):
                    return self
                return None

            def load_module(self, name):
                raise ImportError(
                    f"[comfyapp] blocked CUDA module import "
                    f"{name!r} during snap=True to keep snapshot clean"
                )

        def _is_cuda_module(name: str) -> bool:
            return (
                name.endswith("_cuda")
                or name.startswith("cuda_")
                or "_cuda_" in name
            )

        blocker = _BlockCudaModuleImport()
        sys.meta_path.insert(0, blocker)

        # Ensure ComfyUI's CLI layer is initialised with GPU mode so
        # model_management starts in HIGH_VRAM during the snapshot.
        comfy_path = "/root/comfy/ComfyUI"
        if comfy_path not in sys.path:
            sys.path.insert(0, comfy_path)
        import comfy.cli_args
        comfy.cli_args.args.cpu = False

        try:
            yield
        finally:
            try:
                sys.meta_path.remove(blocker)
            except ValueError:
                pass

    def _start_in_process_backend(self):
        """Initialize ComfyUI in-process for snapshot-friendly execution.

        Sets up ComfyUI's execution environment in the current Python process
        instead of launching a subprocess. This allows Modal's memory snapshot
        to capture the initialized state (imported modules, registered nodes,
        etc.) so subsequent container starts skip Python initialization.

        GPU is available during startup — ``enable_gpu_snapshot=True`` in the
        Modal app ensures GPU memory is preserved in the snapshot.
        """
        t0 = time.time()
        _stage = time.time()

        # ── Match comfy launch CWD — ComfyUI modules use relative path
        #    resolution (e.g. ``from utils.install_util import ...``). ──
        comfy_path = "/root/comfy/ComfyUI"
        os.chdir(comfy_path)
        if comfy_path not in sys.path:
            sys.path.insert(0, comfy_path)

        # Line-buffered stdout so container logs are not delayed
        sys.stdout.reconfigure(line_buffering=True)
        self._log_profile("inproc_chdir_cwd", duration_ms=self._profile_ms(_stage))
        _stage = time.time()

        # ── Import order matters: ComfyUI's utils/ package (directory) is
        #    shadowed by comfy/utils.py (module file) when comfy is imported
        #    first.  Replicate main.py's order: folder_paths + utils.* BEFORE
        #    any import that touches the comfy package.                       ──
        import folder_paths  # safe — no comfy deps
        import utils.extra_config  # establishes utils as the /utils/ package
        import utils.mime_types  # reinforces utils package before comfy loads

        import asyncio
        import comfy.model_management
        import comfy.model_patcher
        import comfy.utils
        import execution
        import nodes

        # ── Generic entrypoint traceback collector ──
        # ComfyUI's load_custom_node catches entrypoint exceptions at
        # nodes.py line 2277 and logs them via logging.warning without
        # exc_info=True.  We patch logging.warning to detect this
        # specific pattern and add the full traceback.
        # This works for ANY custom node entrypoint failure.
        import logging as _comfy_logging
        import traceback as _comfy_tb
        # Idempotent: only patch once
        if not getattr(_comfy_logging.Logger, '_comfy_modal_warning_patched', False):
            _comfy_logging.Logger._comfy_modal_warning_orig = _comfy_logging.Logger.warning
            _orig_logger_warning = _comfy_logging.Logger.warning
            def _patched_logger_warning(self, msg, *args, **kwargs):
                result = _orig_logger_warning(self, msg, *args, **kwargs)
                msg_str = str(msg) if not isinstance(msg, str) else msg
                if "Error while calling comfy_entrypoint" in msg_str:
                    _exc = sys.exc_info()
                    if _exc[0] is not None:
                        _tb_text = "".join(_comfy_tb.format_exception(*_exc))
                        _comfy_tb.print_exc()
                        # Record structured failure for import health
                        _exception_type = _exc[0].__name__ if _exc[0] else "?"
                        _exception_msg = str(_exc[1]) if _exc[1] else "?"
                        try:
                            _module_path = msg_str.split("in ")[-1].strip().split(":")[0].strip()
                        except Exception:
                            _module_path = "?"
                        global _CUSTOM_NODE_IMPORT_FAILURES, _CUSTOM_NODE_RETRY_REGISTRY
                        _CUSTOM_NODE_IMPORT_FAILURES.append({
                            "phase": "entrypoint",
                            "custom_node_path": _module_path,
                            "exception_type": _exception_type,
                            "exception_message": _exception_msg,
                            "traceback": _tb_text,
                            "timestamp": time.time(),
                        })
                        # Record for post-GPU-warmup retry (schema failures caused
                        # by CPU-only snapshot where device lists are empty).
                        global _CUSTOM_NODE_REGISTRATION_PENDING_RETRY
                        if _module_path and _module_path != "?":
                            _CUSTOM_NODE_REGISTRATION_PENDING_RETRY.add(_module_path)
                            _CUSTOM_NODE_RETRY_REGISTRY.register_failure(
                                path=_module_path,
                                exc_type=_exception_type,
                                exc_msg=_exception_msg,
                                tb=_tb_text,
                                retryable_reason="cpu_snapshot_schema" if "CUDA" in _exception_msg or "device" in _exception_msg.lower() else "",
                            )
                return result
            _comfy_logging.Logger.warning = _patched_logger_warning
            _comfy_logging.Logger._comfy_modal_warning_patched = True

        import server as comfy_server
        self._log_profile("inproc_imports", duration_ms=self._profile_ms(_stage))
        _stage = time.time()

        comfy.model_management.DISABLE_SMART_MEMORY = False
        if hasattr(comfy.model_management, "VRAMState") and hasattr(comfy.model_management.VRAMState, "HIGH_VRAM"):
            comfy.model_management.vram_state = comfy.model_management.VRAMState.HIGH_VRAM
            self._patch_offload_devices_for_high_vram(comfy.model_management)
        self._patch_model_cpu_cache(comfy.utils)
        if PROFILING_ENABLED:
            self._patch_model_clone_profiling(comfy.model_patcher)
            self._patch_model_management_profiling(comfy.model_management)
        self._log_profile("inproc_patch", duration_ms=self._profile_ms(_stage))
        _stage = time.time()

        # ── Patch get_input_data for sync-safe cache access ──
        # Custom-node compatibility wrappers (e.g. comfyui_image_metadata_extension's
        # OutputCacheCompat) may pass raw HierarchicalCache objects as the execution_list
        # param and call the async ``cache.get()`` method synchronously, returning an
        # unawaited coroutine instead of a CacheEntry.  This coroutine then hits
        # ``AttributeError: 'coroutine' object has no attribute 'outputs'`` inside
        # ``get_input_data()`` and leaks ``RuntimeWarning: coroutine was never awaited``.
        #
        # This patch wraps the cache-access call site so any coroutine is detected,
        # closed (to suppress the warning), and the sync-safe ``get_local()`` fallback
        # is tried instead.  The fix is generic — no custom-node names are hardcoded.
        if not getattr(execution, '_comfy_modal_sync_cache_patched', False):
            _orig_get_input_data = execution.get_input_data
            def _patched_get_input_data(inputs, class_def, unique_id, execution_list=None, dynprompt=None, extra_data=None):
                if extra_data is None:
                    extra_data = {}
                if execution_list is not None and hasattr(execution_list, 'get_cache'):
                    class _SafeExecutionListWrapper:
                        def __init__(self, wrapped):
                            self.__wrapped = wrapped
                        def get_cache(self, from_id, to_id):
                            result = self.__wrapped.get_cache(from_id, to_id)
                            if asyncio.iscoroutine(result):
                                try:
                                    result.close()
                                except Exception:
                                    pass
                                if hasattr(self.__wrapped, 'get_local'):
                                    return self.__wrapped.get_local(from_id)
                                if hasattr(self.__wrapped, '_cache') and hasattr(self.__wrapped._cache, 'get_local'):
                                    return self.__wrapped._cache.get_local(from_id)
                                return None
                            return result
                        def __getattr__(self, name):
                            return getattr(self.__wrapped, name)
                    execution_list = _SafeExecutionListWrapper(execution_list)
                return _orig_get_input_data(inputs, class_def, unique_id, execution_list, dynprompt, extra_data)
            execution.get_input_data = _patched_get_input_data
            execution._comfy_modal_sync_cache_patched = True

        # ── DummyServer: minimal PromptServer that doesn't bind a port ──
        event_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(event_loop)

        class _DummyServer(comfy_server.PromptServer):
            def __init__(self, loop):
                super().__init__(loop)
                comfy_server.PromptServer.instance = self
                q = execution.PromptQueue(comfy_server.PromptServer.instance)
                self.client_id = "in-process"
                self.prompt_queue = q
                self._send_sync_callback = None

            def send_sync(self, event, data, sid=None):
                if self._send_sync_callback:
                    self._send_sync_callback(event, data, sid)

        dummy = _DummyServer(event_loop)
        self._log_profile("inproc_server_init", duration_ms=self._profile_ms(_stage))
        _stage = time.time()

        # ── PromptExecutor for direct workflow execution (must provide
        #    cache_args dict; v0.22+ unconditionally indexes into it) ──
        total_ram_gb = _get_system_ram_gb()
        # Cap at 24 GB: ComfyUI's model cache only needs to hold
        # state_dicts for the active workflow (max ~17 GB for
        # Flux UNet + Qwen-sized text encoders on 32 GB hosts).
        cache_ram_gb = round(max(4.0, min(total_ram_gb * 0.5, 24.0)), 1)
        print(
            f"[comfyapp] total_ram={total_ram_gb}G  "
            f"cache_ram={cache_ram_gb}G"
        )
        self._executor = execution.PromptExecutor(
            dummy,
            cache_args={"lru": 0, "ram": cache_ram_gb, "ram_inactive": 96.0},
        )
        self._dummy_server = dummy
        self._event_loop = event_loop
        self._log_profile("inproc_executor_init", ram_gb=total_ram_gb, cache_gb=cache_ram_gb, duration_ms=self._profile_ms(_stage))
        _stage = time.time()

        # ── Wire up send_sync for execution-progress logging ──
        def _on_sync(event, data, sid):
            # Forward only JSON-style execution events to progress streaming.
            # ComfyUI also emits binary preview-image events via send_sync;
            # those payloads are not dicts and will break the local forwarder,
            # which expects standard websocket event payload objects.
            _prog_q = getattr(self, "_prog_queue", None)
            if _prog_q is not None and event in {"execution_start", "executing", "progress", "progress_state", "execution_error"} and isinstance(data, dict):
                try:
                    _prog_q.put_nowait((event, data))
                except Exception:
                    pass
            if event == "execution_start":
                if PROFILING_ENABLED:
                    self._log_profile("inproc_exec_progress", event="execution_start", prompt_id=data.get("prompt_id","")[:8])
            elif event == "executing":
                node = data.get("node", None)
                now = time.time()
                if node is None:
                    self._finish_profiled_node(now)
                    if PROFILING_ENABLED:
                        self._log_profile("inproc_exec_progress", event="execution_done")
                else:
                    self._finish_profiled_node(now)
                    self._begin_profiled_node(node, now)
            elif event == "progress":
                self._note_progress_event(data)
                if PROFILING_ENABLED:
                    self._log_profile("inproc_exec_progress", event="progress", node=str(data.get("node",""))[:40], step=data.get("step",0), max=data.get("max",0))
            elif event == "execution_error":
                if PROFILING_ENABLED:
                    self._log_profile("inproc_exec_progress", event="execution_error", node=str(data.get("node",""))[:40])
        dummy._send_sync_callback = _on_sync

        # ── Install progress hook (mirrors main.py:hijack_progress) ──────
        # Without this, sampler step progress is never emitted in in-process
        # mode, so the frontend never receives "progress" events.
        from comfy_execution.utils import get_executing_context

        def _progress_hook(value, total, preview_image, prompt_id=None, node_id=None):
            ctx = get_executing_context()
            if prompt_id is None and ctx is not None:
                prompt_id = ctx.prompt_id
            if node_id is None and ctx is not None:
                node_id = ctx.node_id
            if prompt_id is None or node_id is None:
                return
            dummy.send_sync("progress", {
                "value": value,
                "max": total,
                "prompt_id": prompt_id,
                "node": node_id,
            })

        comfy.utils.set_progress_bar_global_hook(_progress_hook)

        # Register built-in + custom nodes (async in ComfyUI v0.22+)
        self._event_loop.run_until_complete(nodes.init_extra_nodes())
        self._collect_custom_node_import_health()
        self._apply_sage_attention_policy()
        self._log_profile("inproc_node_init", duration_ms=self._profile_ms(_stage))

        self._in_process_ready = True
        duration = time.time() - t0
        print(f"[comfyapp] in-process backend initialized in {duration:.3f}s")

    def _start_backend(self):
        """Select and start the execution backend."""
        backend = self._select_backend()
        print(f"[comfyapp] selected backend={backend}")
        if backend == "in_process":
            try:
                self._start_in_process_backend()
            except Exception as exc:
                print(f"[comfyapp] in_process backend failed ({exc}), falling back to subprocess")
                self._backend_fallback = True
                self._restart_comfy()
        else:
            self._restart_comfy()
        print(f"[comfyapp] active backend={self._select_backend()}")

    def _submit_and_poll(self, workflow: dict) -> dict:
        """Submit a workflow directly to the local ComfyUI API and wait for history."""
        client_id = f"warmup-{uuid.uuid4()}"
        r = self._http_client.post(
            "/prompt",
            json={"prompt": workflow, "client_id": client_id},
        )
        r.raise_for_status()
        queued = r.json()
        prompt_id = queued["prompt_id"]
        delay = 0.25
        elapsed = 0.0
        while elapsed < 3600:
            history = self._http_client.get(f"/history/{prompt_id}").json()
            if prompt_id in history:
                return history[prompt_id]
            time.sleep(delay)
            elapsed += delay
        raise TimeoutError(f"Warmup prompt {prompt_id} timed out")

    def _build_warmup_workflow(self, profile: dict) -> dict:
        """Build a warmup workflow from the pinned warmup profile.

        Returns only model-loading nodes (UNETLoader, CLIPLoader) — no
        inference nodes.  Loading the models into ComfyUI's GPU cache is
        the critical part; running a warmup inference step adds ~500ms
        with no measurable benefit for the first real prompt.
        """
        if profile.get("mode") == "checkpoint":
            # Checkpoint path: just load the checkpoint, skip inference
            return {
                "3": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": profile["checkpoint"]}},
            }
        # Use CLIPLoader (not DualCLIPLoader) to match the real prompt's
        # loader type so the model cache entry is shared.
        clip_name = profile.get("clip1", "")
        clip_type = profile.get("clip_type", "flux")
        return {
            "1": {"class_type": "UNETLoader", "inputs": {"unet_name": profile["unet"], "weight_dtype": "default"}},
            "2": {"class_type": "CLIPLoader", "inputs": {
                "clip_name": clip_name,
                "type": clip_type,
            }},
        }

    def _preload_warmup_profile(self) -> dict:
        """Preload and warm the pinned or auto-detected model stack.

        Priority: pinned env vars > auto-detected stack from last prompt.

        Uses the active execution backend (in-process or subprocess/HTTP).
        During startup (snap=True) with in-process CUDA is hidden, so this
        method is intentionally skipped by ``startup()`` when
        ``is_in_proc=True`` — it only runs on the ``restore()`` path where
        the GPU is available.
        """
        _t0 = time.time()
        profile = load_warmup_profile()
        t_load_profile = round((time.time() - _t0) * 1000, 1)

        replay_workflow = {}
        t_load_replay = 0.0
        if not profile:
            _t0 = time.time()
            replay_workflow = self._load_last_warmup_workflow()
            t_load_replay = round((time.time() - _t0) * 1000, 1)

        t_load_stack = 0.0
        if not profile and not replay_workflow:
            _t0 = time.time()
            profile = stack_to_profile(self._load_last_model_stack())
            t_load_stack = round((time.time() - _t0) * 1000, 1)

        if not profile and not replay_workflow:
            print(f"[comfyapp] warmup disabled (no profile, no replay, no stack)")
            return {"mode": "none", "status": "disabled"}
        started = time.time()
        try:
            if replay_workflow:
                workflow = replay_workflow
                mode = "workflow"
                t_validate = 0.0
                t_build = 0.0
            else:
                _t0 = time.time()
                self._validate_warmup_profile_files(profile)
                t_validate = round((time.time() - _t0) * 1000, 1)
                _t0 = time.time()
                workflow = self._build_warmup_workflow(profile)
                t_build = round((time.time() - _t0) * 1000, 1)
                mode = profile.get("mode")
            if self._select_backend() == "in_process":
                _t0 = time.time()
                self._execute_in_process(workflow, collect_outputs=False)
                t_exec = round((time.time() - _t0) * 1000, 1)
            else:
                _t0 = time.time()
                self._submit_and_poll(workflow)
                t_exec = round((time.time() - _t0) * 1000, 1)
            duration_ms = round((time.time() - started) * 1000, 1)
            t_overhead = round(duration_ms - t_exec - t_validate - t_build - t_load_profile - t_load_replay - t_load_stack, 1)
            # Extract per-node timing breakdown from stage windows
            node_timing: dict[str, float] = {}
            windows = getattr(self, "_stage_windows", None) or {}
            for stage, fields in windows.items():
                s = fields.get("start")
                e = fields.get("end")
                if s is not None and e is not None:
                    node_timing[f"{stage}_ms"] = round((e - s) * 1000, 1)
            print(f"[comfyapp] warmup mode={mode} total={duration_ms}ms "
                  f"load_profile={t_load_profile}ms "
                  f"load_replay={t_load_replay}ms "
                  f"load_stack={t_load_stack}ms "
                  f"validate={t_validate}ms "
                  f"build={t_build}ms "
                  f"exec={t_exec}ms "
                  f"overhead={t_overhead}ms "
                  f"node_timing={node_timing}")
            return {"mode": mode, "status": "ok", "duration_ms": duration_ms, "node_timing": node_timing}
        except Exception as exc:
            import traceback
            duration_ms = round((time.time() - started) * 1000, 1)
            print(f"[comfyapp] warmup failed after {duration_ms}ms "
                  f"mode={'workflow' if replay_workflow else profile.get('mode')}:\n{traceback.format_exc()}")
            return {
                "mode": "workflow" if replay_workflow else profile.get("mode"),
                "status": "error",
                "duration_ms": duration_ms,
                "error": str(exc)[:500],
            }

    def _warmup_runtime(self) -> dict:
        """Warm up the ComfyUI runtime if enabled.

        For the subprocess backend, submits a model-loading workflow so the
        GPU model cache is populated before the snapshot is taken.  These
        model tensors are then captured in the GPU memory snapshot and are
        immediately available after restore — no volume re-read needed.
        """
        if not ENABLE_WARMUP:
            return {"enabled": False, "profile": WARMUP_PROFILE}
        t0 = time.time()
        node_timing: dict = {}
        try:
            if self._select_backend() == "in_process":
                _ = self._executor
            else:
                # Subprocess: load models into ComfyUI's GPU cache via the
                # HTTP API.  This populates current_loaded_models inside the
                # subprocess so the GPU snapshot captures them.
                wr = self._preload_warmup_profile()
                if isinstance(wr, dict):
                    node_timing = wr.get("node_timing", {})
            duration_s = round(time.time() - t0, 3)
            return {"enabled": True, "profile": WARMUP_PROFILE, "duration_s": duration_s, "status": "ok", **node_timing}
        except Exception as exc:
            duration_s = round(time.time() - t0, 3)
            print(f"[comfyapp] warmup failed after {duration_s:.3f}s: {exc}")
            return {"enabled": True, "profile": WARMUP_PROFILE, "duration_s": duration_s, "status": "error", "error": str(exc)[:200]}

    def _restart_comfy(self):
        _restart_t0 = time.time()
        print("[comfyapp] _restart_comfy starting")
        # If running in-process, switch to subprocess mode
        if getattr(self, "_in_process_ready", False):
            print("[comfyapp] switching from in-process to subprocess backend")
            self._in_process_ready = False
            self._executor = None
            self._dummy_server = None
            self._event_loop = None

        if self._http_client_obj is not None:
            self._http_client_obj.close()
            self._http_client_obj = None
        if getattr(self, "_proc", None) and self._proc.poll() is None:
            print("[comfyapp] terminating existing ComfyUI subprocess")
            self._proc.terminate()
            try:
                self._proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                print("[comfyapp] killing unresponsive ComfyUI subprocess")
                self._proc.kill()
        _kill_ms = round((time.time() - _restart_t0) * 1000, 1)
        self._proc = subprocess.Popen(
            [
                "comfy", "launch", "--", "--listen", "0.0.0.0",
                f"--port={COMFYUI_API_PORT}", "--disable-auto-launch",
                "--gpu-only", "--disable-smart-memory", "--cache-classic",
            ],
        )
        _launch_ms = round((time.time() - _restart_t0) * 1000, 1)
        self._wait_for_comfy()
        _total_ms = round((time.time() - _restart_t0) * 1000, 1)
        print(f"[comfyapp] _restart_comfy done: kill_ms={_kill_ms} launch_ready_ms={_total_ms} wait_ms={_total_ms - _launch_ms}")

    @modal.enter(snap=True)
    def startup(self):
        t0 = time.time()
        _snap_mode = os.environ.get("COMFYMODAL_SNAPSHOT_MODE", "full").strip().lower()
        print(f"[comfyapp] lifecycle=startup snap=True snapshot_mode={_snap_mode}")

        is_in_proc = (self._select_backend() == "in_process")

        stage_started = time.time()
        self._ensure_models_symlink()
        self._log_profile("startup_symlink", duration_ms=self._profile_ms(stage_started))

        stage_started = time.time()
        manager_paths = set_manager_network_mode_offline()
        self._log_profile("manager_network_mode", mode="offline", paths=len(manager_paths), duration_ms=self._profile_ms(stage_started))

        stage_started = time.time()
        vol.reload()
        self._log_profile("volume_reload", duration_ms=self._profile_ms(stage_started))

        stage_started = time.time()
        _, self._custom_nodes_state = self._sync_custom_nodes_from_volume()
        self._log_profile("custom_nodes_sync", duration_ms=self._profile_ms(stage_started), state_count=len(self._custom_nodes_state))

        stage_started = time.time()
        try:
            install_summary = self._install_custom_node_requirements()
        except RuntimeError as _req_err:
            # In fail_fast mode, abort startup if requirements are missing.
            # This prevents a container from booting in a broken state.
            print(f"[comfyapp] FATAL: {_req_err}")
            raise
        self._log_profile("requirements_install", duration_ms=self._profile_ms(stage_started), installed=len(install_summary.get("installed", [])), skipped=len(install_summary.get("skipped", [])))

        stage_started = time.time()
        self._record_runtime_state()
        self._log_profile("runtime_state_record", duration_ms=self._profile_ms(stage_started))

        _need_backend = True
        if _snap_mode == "none":
            _need_backend = False
            print("[comfyapp] snapshot_mode=none: skipping backend init during snap=True")
        elif _snap_mode == "minimal":
            # Minimal snapshot: import backend modules but skip heavy GPU init.
            # ComfyUI will fully init on restore.
            _need_backend = False
            print("[comfyapp] snapshot_mode=minimal: backend init deferred to restore")
        if _need_backend and is_in_proc:
            if ENABLE_GPU_SNAPSHOT:
                stage_started = time.time()
                with self._force_triton_during_snapshot():
                    self._start_backend()
                self._log_profile("backend_start", backend=self._select_backend(), duration_ms=self._profile_ms(stage_started))
            else:
                stage_started = time.time()
                with self._force_cpu_during_snapshot():
                    self._start_backend()
                self._log_profile("backend_start", backend=self._select_backend(), duration_ms=self._profile_ms(stage_started))
        elif _need_backend:
            stage_started = time.time()
            self._start_backend()
            self._log_profile("backend_start", backend=self._select_backend(), duration_ms=self._profile_ms(stage_started))
            # Skip the GPU warmup preload during snap=True — loading ~9GB
            # of Flux/Qwen weights into the subprocess's GPU memory would
            # be captured in the snapshot, costing ~30+ seconds of GPU
            # memory transfer on every restore.  The first prompt after
            # restore pays the model load cost.
            warmup_result = self._warmup_runtime()
            print(f"[comfyapp] warmup={warmup_result}")

        duration = time.time() - t0
        print(f"[comfyapp] startup complete in {duration:.3f}s  "
              f"req_installed={len(install_summary.get('installed', []))}")

    def _warmup_cuda(self):
        """Revitalise CUDA driver context and force GPU clock ramp-up.

        Modal's ``enable_gpu_snapshot`` preserves GPU *memory* across
        restore, but the CUDA driver context can become stale on a new
        container.  The first kernel launch then pays an ~8s penalty
        and the GPU may stay in a low-power state that throttles
        memory-bandwidth-bound ops (VAE decode, text encoding).

        Running a brief warmup here pays the penalty once during
        restore rather than silently degrading prompt execution.
        """
        import torch
        if not torch.cuda.is_available():
            print("[comfyapp] CUDA warmup skipped — no GPU")
            return
        dev = torch.device(torch.cuda.current_device())
        _t0 = time.time()
        # Force CUDA context reconnection (first call is slow if stale)
        torch.cuda.synchronize(dev)
        _ctx_ms = round((time.time() - _t0) * 1000, 1)
        _t0 = time.time()
        # Run a handful of GEMMs to coax GPU Boost out of its low-power state
        a = torch.randn(2048, 2048, device=dev)
        b = torch.randn(2048, 2048, device=dev)
        for _ in range(5):
            a = a @ b
        torch.cuda.synchronize(dev)
        _gemm_ms = round((time.time() - _t0) * 1000, 1)
        # Warm the memory allocator with a moderate allocation
        _t0 = time.time()
        _warm = torch.empty(256, 1024, 1024, dtype=torch.float16, device=dev)
        _warm.zero_()
        torch.cuda.synchronize(dev)
        del _warm
        _alloc_ms = round((time.time() - _t0) * 1000, 1)
        print(f"[comfyapp] CUDA warmup done device={torch.cuda.get_device_name(dev)} "
              f"ctx_sync={_ctx_ms}ms gemm={_gemm_ms}ms alloc={_alloc_ms}ms")

    def _warmup_sage_attention_cuda(self):
        """Run one SageAttention CUDA forward pass to pre-load kernels."""
        try:
            _t0 = time.time()
            backend_name, backend, backend_kwargs = self._preferred_sage_backend()
            if backend is None:
                print("[comfyapp] sage_warmup skipped — no backend")
                return
            import torch
            q = torch.randn(1, 16, 8, 64, device="cuda", dtype=torch.float16)
            k = torch.randn(1, 16, 8, 64, device="cuda", dtype=torch.float16)
            v = torch.randn(1, 16, 8, 64, device="cuda", dtype=torch.float16)
            _ = backend(q, k, v, is_causal=False, attn_mask=None,
                        tensor_layout="NHD", **backend_kwargs)
            torch.cuda.synchronize()
            _dur = round((time.time() - _t0) * 1000, 1)
            print(f"[comfyapp] sage_warmup done backend={backend_name} {_dur}ms")
        except Exception as exc:
            print(f"[comfyapp] sage_warmup failed: {exc}")

    def _warmup_direct(self, profile: dict) -> dict:
        """Direct warmup: load models and prime CLIPTextEncode cache without
        ComfyUI executor overhead.

        Calls UNETLoader, CLIPLoader, and CLIPTextEncode node functions
        directly instead of going through ``_execute_in_process()``.  This
        skips ~800ms of executor dispatch, IS_CHANGED calls, and profiling.

        The loaded models still land in ComfyUI's GPU model cache via
        ``load_models_gpu()`` which the node functions call internally.

        Model loading is further gated by:
        - ``DIRECT_WARMUP_LOAD_UNET`` / ``DIRECT_WARMUP_LOAD_CLIP`` — enable
          UNET / CLIP loading in direct warmup (both default 0).
        - ``DIRECT_WARMUP_REQUIRE_CPU_CACHE_HIT`` — when 1 (default), only
          load a model if it is already present in the CPU cache (populated
          by ``_preload_models_to_cpu``).  This prevents direct warmup from
          becoming a blocking 16.85 GB volume read when CPU preload is
          disabled or async.
        - ``DIRECT_WARMUP_CLIP_ENCODE`` — enable dummy CLIPTextEncode forward
          pass (default 0).
        """
        _t0 = time.time()
        _phases: dict[str, float] = {}
        try:
            import nodes
            import folder_paths

            unet_name = profile.get("unet", "")
            clip_name = profile.get("clip1", "")
            clip_type = profile.get("clip_type", "flux")

            # ── Resolve model paths for CPU cache checks ──────────────
            _unet_full_path = folder_paths.get_full_path("unet", unet_name) or "" if unet_name else ""
            _clip_full_path = folder_paths.get_full_path("text_encoders", clip_name) or "" if clip_name else ""

            # Resolve runtime-configurable flags (file → env → module default)
            _rt_load_unet = _resolve_runtime_flag("DIRECT_WARMUP_LOAD_UNET", "0")
            _rt_load_clip = _resolve_runtime_flag("DIRECT_WARMUP_LOAD_CLIP", "0")
            _rt_clip_encode = _resolve_runtime_flag("DIRECT_WARMUP_CLIP_ENCODE", "0")
            _rt_require_cpu_hit = _resolve_runtime_flag("DIRECT_WARMUP_REQUIRE_CPU_CACHE_HIT", "1")

            # ── 1. Load UNET via UNETLoader (if enabled) ─────────────
            _phases["direct_warmup_load_unet"] = 1.0 if _rt_load_unet else 0.0
            _phases["direct_warmup_require_cpu_cache_hit"] = 1.0 if _rt_require_cpu_hit else 0.0
            _s = time.time()
            _skip_unet = False
            if _rt_require_cpu_hit and _unet_full_path:
                if not self._model_in_cpu_cache(_unet_full_path):
                    print(f"[comfyapp] direct warmup: UNET {unet_name} not in CPU cache, skipping (REQUIRE_CPU_CACHE_HIT)")
                    _skip_unet = True
                    _phases["direct_unet_cpu_hit"] = 0.0
                else:
                    _phases["direct_unet_cpu_hit"] = 1.0
            _unet_loaded = False
            if _rt_load_unet and unet_name and not _skip_unet:
                unet_cls = nodes.NODE_CLASS_MAPPINGS.get("UNETLoader")
                if unet_cls:
                    unet_loader = unet_cls()
                    _unet_result = unet_loader.load_unet(unet_name=unet_name, weight_dtype="default")
                    _unet_loaded = True
                    _phases["direct_unet_load_ms"] = round((time.time() - _s) * 1000, 1)
                    # Store in UNET object cache for real prompt reuse
                    if _unet_result and _unet_result[0] is not None:
                        self._init_unet_cache()
                        try:
                            _unet_cache_path = folder_paths.get_full_path("unet", unet_name) or ""
                            if _unet_cache_path:
                                _key = self._unet_cache_key(_unet_cache_path, "default")
                                self._unet_object_cache[_key] = _unet_result[0]
                                print(f"[comfyapp] direct warmup: UNET cached key={_key} id={id(_unet_result[0])}")
                        except Exception as exc:
                            print(f"[comfyapp] direct warmup: UNET cache store failed: {exc}")
                else:
                    _phases["direct_unet_load_ms"] = 0.0
            else:
                _phases["direct_unet_load_ms"] = 0.0

            # ── 2. Load CLIP via CLIPLoader (if enabled) ─────────────
            _phases["direct_warmup_load_clip"] = 1.0 if _rt_load_clip else 0.0
            _s = time.time()
            clip_cls = nodes.NODE_CLASS_MAPPINGS.get("CLIPLoader")
            clip_out = None
            _skip_clip = False
            if _rt_require_cpu_hit and _clip_full_path:
                if not self._model_in_cpu_cache(_clip_full_path):
                    print(f"[comfyapp] direct warmup: CLIP {clip_name} not in CPU cache, skipping (REQUIRE_CPU_CACHE_HIT)")
                    _skip_clip = True
                    _phases["direct_clip_cpu_hit"] = 0.0
                else:
                    _phases["direct_clip_cpu_hit"] = 1.0
            if _rt_load_clip and clip_cls and clip_name and not _skip_clip:
                clip_loader = clip_cls()
                clip_out = clip_loader.load_clip(clip_name=clip_name, type=clip_type)
                _phases["direct_clip_load_ms"] = round((time.time() - _s) * 1000, 1)
                # Store in CLIP object cache for real prompt reuse
                if clip_out:
                    self._init_clip_cache()
                    try:
                        if _clip_full_path:
                            _key = self._clip_cache_key(_clip_full_path, clip_type)
                            self._clip_object_cache[_key] = clip_out[0]
                            _phases["direct_clip_cached"] = 1.0
                            print(f"[comfyapp] direct warmup: CLIP cached key={_key} "
                                  f"id={id(clip_out[0])}")
                    except Exception as exc:
                        print(f"[comfyapp] direct warmup: CLIP cache store failed: {exc}")
            else:
                _phases["direct_clip_load_ms"] = 0.0

            # ── 3. Prime CLIPTextEncode cache (if enabled) ───────────
            # Costs ~1000ms for Qwen 8B forward pass but saves ~600ms
            # during inference.  Net savings ~400ms by disabling.
            _phases["direct_warmup_clip_encode"] = 1.0 if _rt_clip_encode else 0.0
            _s = time.time()
            if _rt_clip_encode and clip_out and WARMUP_TEXT:
                enc_cls = nodes.NODE_CLASS_MAPPINGS.get("CLIPTextEncode")
                if enc_cls:
                    encoder = enc_cls()
                    encoder.encode(clip=clip_out[0], text=WARMUP_TEXT)
            _phases["direct_clip_encode_ms"] = round((time.time() - _s) * 1000, 1)
            _phases["direct_total_ms"] = round((time.time() - _t0) * 1000, 1)
            print(f"[comfyapp] direct warmup OK — {_phases}")
            return {"status": "ok", **_phases}
        except Exception as exc:
            import traceback
            _phases["direct_total_ms"] = round((time.time() - _t0) * 1000, 1)
            print(f"[comfyapp] direct warmup FAILED after {_phases['direct_total_ms']}ms: {exc}\n{traceback.format_exc()}")
            return {"status": "error", "error": str(exc)[:200], **_phases}

    def _clip_cache_key(self, clip_path: str, clip_type: str) -> tuple:
        """Deterministic cache key for a CLIP model load request."""
        try:
            resolved = os.path.realpath(clip_path)
        except Exception:
            resolved = clip_path
        return (resolved, clip_type or "stable_diffusion")

    def _init_clip_cache(self):
        """Initialise instance-level CLIP object cache."""
        if not hasattr(self, '_clip_object_cache'):
            self._clip_object_cache: dict[tuple, object] = {}
            self._clip_cache_keys: list[tuple] = []

    def _init_unet_cache(self):
        """Initialise instance-level UNET ModelPatcher cache."""
        if not hasattr(self, '_unet_object_cache'):
            self._unet_object_cache: dict[tuple, object] = {}
            self._unet_cache_hits = 0
            self._unet_cache_misses = 0

    def _unet_cache_key(self, unet_path: str, weight_dtype: str) -> tuple:
        try:
            resolved = os.path.realpath(unet_path)
        except Exception:
            resolved = unet_path
        return (resolved, weight_dtype or "default")

    def _patch_unet_loader_cache(self):
        """Patch UNETLoader.load_unet to reuse ModelPatcher objects cached from warmup."""
        self._init_unet_cache()
        _api = self
        try:
            import folder_paths
            import nodes
        except Exception as exc:
            print(f"[comfyapp] unet_loader_cache: imports failed: {exc}")
            return
        cls = nodes.NODE_CLASS_MAPPINGS.get("UNETLoader")
        if cls is None:
            print("[comfyapp] unet_loader_cache: UNETLoader not found")
            return
        orig_load = getattr(cls, "load_unet", None)
        if orig_load is None:
            print("[comfyapp] unet_loader_cache: UNETLoader.load_unet not found")
            return
        if getattr(orig_load, '_comfy_modal_unet_cached', False):
            return

        _api._original_loaders["UNETLoader.load_unet"] = orig_load

        def _cached_unet_load(self_node, **kwargs):
            unet_name = kwargs.get("unet_name", "")
            weight_dtype = kwargs.get("weight_dtype", "default")
            if not unet_name:
                return orig_load(self_node, **kwargs)
            path = ""
            try:
                path = folder_paths.get_full_path("unet", unet_name) or ""
            except Exception:
                path = unet_name
            if not path:
                return orig_load(self_node, **kwargs)
            key = _api._unet_cache_key(path, weight_dtype)
            _cache = getattr(_api, '_unet_object_cache', {})
            if key in _cache:
                _api._unet_cache_hits = getattr(_api, '_unet_cache_hits', 0) + 1
                print(f"[unet_loader_cache] cache_hit path={unet_name}")
                return (_cache[key],)
            print(f"[unet_loader_cache] canonical_key={key} object_cache_exists={'1' if key in _cache else '0'}")
            # Self-future detection
            import threading as _thr_sfu
            _owner_map = getattr(_api, "_actual_load_owner_thread", {})
            if _owner_map.get(key) == _thr_sfu.current_thread().ident:
                print(f"[loader_future] self_future_detected key={key} -> using original loader directly")
                return orig_load(self_node, **kwargs)
            # Check CPU cache next: if the state dict is cached, load normally
            # (the CPU cache deepcopy will be fast)
            _cpu_cache = getattr(_api, "_model_cpu_cache", {})
            if any(key in _cpu_cache for key in _model_cpu_cache_lookup_keys(path)):
                print(f"[unet_loader_cache] cpu_cache_hit path={unet_name} — normal load will use CPU cache")
            # Check in-flight preloads
            _inflight = getattr(_api, "_in_flight_preloads", {})
            if PROMPT_ASYNC_PRELOAD and path in _inflight:
                _thread = _inflight.pop(path, None)
                if _thread is not None:
                    t0 = time.time()
                    _thread.join()
                    wait_ms = round((time.time() - t0) * 1000, 1)
                    print(f"[unet_loader_cache] waited_for_inflight path={unet_name} wait_ms={wait_ms}")
                    if key in _cache:
                        _api._unet_cache_hits = getattr(_api, '_unet_cache_hits', 0) + 1
                        return (_cache[key],)
            # Check in-flight actual-load future
            _futures_exists = getattr(_api, '_actual_load_futures', {})
            print(f"[unet_loader_cache] future_exists={'1' if key in _futures_exists else '0'}")
            if _api._consume_actual_load_future(key):
                if key in _cache:
                    print(f"[loader_future] returned_future_result loader=UNET key={key}")
                    _api._unet_cache_hits = getattr(_api, '_unet_cache_hits', 0) + 1
                    return (_cache[key],)
            _api._unet_cache_misses = getattr(_api, '_unet_cache_misses', 0) + 1
            t0 = time.time()
            result = orig_load(self_node, **kwargs)
            d_ms = round((time.time() - t0) * 1000, 1)
            print(f"[unet_loader_cache] normal_load path={unet_name} ms={d_ms}")
            if result and result[0] is not None:
                _cache[key] = result[0]
                print(f"[unet_loader_cache] returned_cached_object path={unet_name}")
            return result

        _cached_unet_load._comfy_modal_unet_cached = True
        setattr(cls, "load_unet", _cached_unet_load)
        print("[comfyapp] unet_loader_cache: patched UNETLoader.load_unet")

    def _init_vae_cache(self):
        if not hasattr(self, '_vae_object_cache'):
            self._vae_object_cache: dict[tuple, object] = {}

    def _patch_vae_loader_cache(self):
        self._init_vae_cache()
        _api = self
        try:
            import folder_paths, nodes
        except Exception as exc:
            print(f"[comfyapp] vae_loader_cache: imports failed: {exc}")
            return
        cls = nodes.NODE_CLASS_MAPPINGS.get("VAELoader")
        if cls is None:
            print("[comfyapp] vae_loader_cache: VAELoader not found")
            return
        orig_load = getattr(cls, "load_vae", None)
        if orig_load is None or getattr(orig_load, '_comfy_modal_vae_cached', False):
            return

        _api._original_loaders["VAELoader.load_vae"] = orig_load

        def _cached_vae_load(self_node, **kwargs):
            vae_name = kwargs.get("vae_name", "")
            if not vae_name:
                return orig_load(self_node, **kwargs)
            path = ""
            try:
                path = folder_paths.get_full_path("vae", vae_name) or ""
            except Exception:
                path = vae_name
            if not path:
                return orig_load(self_node, **kwargs)
            try:
                resolved = os.path.realpath(path)
            except Exception:
                resolved = path
            key = ("VAELoader", resolved)
            cache = getattr(_api, '_vae_object_cache', {})
            if key in cache:
                print(f"[vae_loader_cache] cache_hit path={vae_name}")
                return (cache[key],)
            # Self-future detection
            import threading as _thr_sfv
            _owner_map = getattr(_api, "_actual_load_owner_thread", {})
            if _owner_map.get(key) == _thr_sfv.current_thread().ident:
                print(f"[loader_future] self_future_detected key={key} -> using original loader directly")
                return orig_load(self_node, **kwargs)
            # Check in-flight actual load future
            thread = getattr(_api, '_actual_load_futures', {}).pop(key, None)
            if thread is not None:
                t0 = time.time()
                thread.join()
                wait_ms = round((time.time() - t0) * 1000, 1)
                print(f"[loader_future] waited loader=VAE key={key} wait_ms={wait_ms}")
                if key in cache:
                    _api._actual_load_waits = getattr(_api, '_actual_load_waits', 0) + 1
                    return (cache[key],)
            t0 = time.time()
            result = orig_load(self_node, **kwargs)
            d_ms = round((time.time() - t0) * 1000, 1)
            print(f"[loader_future] fallback_normal_load loader=VAE key={key} ms={d_ms}")
            if result and result[0] is not None:
                cache[key] = result[0]
            return result

        _cached_vae_load._comfy_modal_vae_cached = True
        setattr(cls, "load_vae", _cached_vae_load)
        print("[comfyapp] vae_loader_cache: patched VAELoader.load_vae")

    def _consume_actual_load_future(self, key: tuple) -> bool:
        """Check and wait for an in-flight actual-load future. Returns True if consumed."""
        futures = getattr(self, "_actual_load_futures", {})
        if key not in futures:
            return False
        thread = futures.pop(key, None)
        if thread is None:
            return False
        t0 = time.time()
        thread.join()
        wait_ms = round((time.time() - t0) * 1000, 1)
        print(f"[loader_future] waited key={key} wait_ms={wait_ms}")
        self._actual_load_waits = getattr(self, '_actual_load_waits', 0) + 1
        return True

    def _patch_clip_loader_cache(self):
        """Patch CLIPLoader.load_clip and DualCLIPLoader.load_clip to
        reuse CLIP objects loaded during warmup.

        The warmup ``_warmup_direct()`` stores the loaded CLIP object in
        ``self._clip_object_cache`` keyed by (resolved_path, clip_type).
        When the real prompt's CLIPLoader/DualCLIPLoader asks for the
        same file, the patch returns the cached object instead of
        constructing a new one — eliminating the ~400-600ms clip_load.
        """
        self._init_clip_cache()
        _api = self  # capture ComfyAPI instance for closure access
        try:
            import folder_paths
            import nodes
        except Exception as exc:
            print(f"[comfyapp] clip_loader_cache: imports failed: {exc}")
            return

        for node_name in ("CLIPLoader", "DualCLIPLoader"):
            cls = nodes.NODE_CLASS_MAPPINGS.get(node_name)
            if cls is None:
                print(f"[comfyapp] clip_loader_cache: {node_name} not found")
                continue
            orig_load = getattr(cls, "load_clip", None)
            if orig_load is None:
                continue
            if getattr(orig_load, '_comfy_modal_clip_cached', False):
                continue

            def _make_cached_load(_orig=orig_load, _name=node_name):
                _api._original_loaders[f"{_name}.load_clip"] = _orig

                def _cached_load(self_node, **kwargs):
                    # Handle both CLIPLoader (clip_name) and DualCLIPLoader (clip_name1, clip_name2)
                    clip_a = kwargs.get("clip_name") or kwargs.get("clip_name1") or ""
                    clip_b = kwargs.get("clip_name2") or ""
                    clip_type = kwargs.get("type", "stable_diffusion")

                    # Resolve clip paths
                    path_a = ""
                    if clip_a:
                        try:
                            path_a = folder_paths.get_full_path("text_encoders", clip_a) or ""
                        except Exception:
                            path_a = clip_a
                    path_b = ""
                    if clip_b:
                        try:
                            path_b = folder_paths.get_full_path("text_encoders", clip_b) or ""
                        except Exception:
                            path_b = clip_b

                    # Build cache keys
                    keys = []
                    if path_a:
                        keys.append(_api._clip_cache_key(path_a, clip_type))
                    if path_b:
                        keys.append(_api._clip_cache_key(path_b, clip_type))

                    print(f"[clip_loader_cache] incoming args=clip_a={clip_a} clip_b={clip_b} clip_type={clip_type}")
                    print(f"[clip_loader_cache] raw_paths=path_a={path_a} path_b={path_b}")
                    print(f"[clip_loader_cache] canonical_keys={keys}")
                    _cache = getattr(_api, '_clip_object_cache', {})
                    unique_keys = list(dict.fromkeys(keys))
                    missing = [k for k in unique_keys if k not in _cache]
                    _futures = getattr(_api, '_actual_load_futures', {})
                    for _k in unique_keys:
                        print(f"[clip_loader_cache] key={_k} object_cache_exists={'1' if _k in _cache else '0'} future_exists={'1' if _k in _futures else '0'}")

                    if not missing:
                        # All keys in cache → HIT
                        _api._clip_cache_hits = getattr(_api, '_clip_cache_hits', 0) + 1
                        if _name == "DualCLIPLoader":
                            return (_cache[unique_keys[0]], _cache[unique_keys[-1]])
                        else:
                            return (_cache[unique_keys[0]],)

                    # Self-future detection: if this thread owns a key's future, call original directly
                    import threading as _thr_sf
                    _current_tid = _thr_sf.current_thread().ident
                    _owner_map = getattr(_api, "_actual_load_owner_thread", {})
                    for _uk in unique_keys:
                        if _owner_map.get(_uk) == _current_tid:
                            print(f"[loader_future] self_future_detected key={_uk} -> using original loader directly")
                            return _orig(self_node, **kwargs)

                    # Check in-flight actual-load futures before normal load
                    for _mk in missing:
                        if _api._consume_actual_load_future(_mk):
                            if _mk in _cache:
                                _api._clip_cache_hits = getattr(_api, '_clip_cache_hits', 0) + 1
                                if _name == "DualCLIPLoader":
                                    return (_cache[unique_keys[0]], _cache[unique_keys[-1]])
                                else:
                                    return (_cache[unique_keys[0]],)

                    # MISS: load normally, attach metadata for CLIPTextEncode cache
                    _api._clip_cache_misses = getattr(_api, '_clip_cache_misses', 0) + 1
                    result = _orig(self_node, **kwargs)
                    # Attach resolved paths and type to clip for CLIPTextEncode cache key
                    if result:
                        for _clip_obj in result:
                            if _clip_obj is not None:
                                _clip_obj._warmup_model_paths = unique_keys if unique_keys else []
                                _clip_obj._warmup_clip_type = clip_type
                    return result

                _cached_load._comfy_modal_clip_cached = True
                return _cached_load

            setattr(cls, "load_clip", _make_cached_load())
            print(f"[comfyapp] clip_loader_cache: patched {node_name}.load_clip")

    def _patch_model_cache_comparison(self):
        """Patch LoadedModel.__eq__ to match by class+size+device.

        Gated behind ``deep_profile`` — no measurable production win for the
        current Flux2 workflow (0 hits out of 3 calls; class names differ
        between warmup and prompt wrappers).  Retained as a diagnostic tool.

        ComfyUI's GPU model cache (``current_loaded_models``) uses Python
        identity to determine if a model is already loaded:
        ``self.model is other.model``.  This patch logs cache hit/miss stats
        in ``comfy.model_management._gpu_cache_eq_stats`` for diagnostic
        visibility.
        """
        import comfy.model_management
        if getattr(comfy.model_management.LoadedModel, '_comfy_modal_patched', False):
            return
        original_eq = comfy.model_management.LoadedModel.__eq__
        _gpu_stats: dict = {
            "calls": 0, "class_hits": 0, "modeltype_hits": 0,
            "misses": 0, "details": {},
        }
        comfy.model_management._gpu_cache_eq_stats = _gpu_stats

        def _eq(self, other):
            _n1 = _n2 = "?"
            try:
                _n1 = self.model.model.__class__.__name__ if self.model and self.model.model else "?"
                _n2 = other.model.model.__class__.__name__ if other.model and other.model.model else "?"
            except Exception:
                pass
            key = f"{_n1}->{_n2}"
            if self.model is other.model:
                _gpu_stats["calls"] += 1
                _gpu_stats["class_hits"] += 1
                _gpu_stats["details"].setdefault(key, {"hits": 0, "misses": 0})
                _gpu_stats["details"][key]["hits"] += 1
                _gpu_stats["details"][key]["last"] = "identity"
                return True
            if self.model is None or other.model is None:
                _gpu_stats["calls"] += 1
                _gpu_stats["misses"] += 1
                _gpu_stats["details"].setdefault(key, {"hits": 0, "misses": 0})
                _gpu_stats["details"][key]["misses"] += 1
                _gpu_stats["details"][key]["last"] = "none_model"
                return False
            if self.device != other.device:
                _gpu_stats["calls"] += 1
                _gpu_stats["misses"] += 1
                _gpu_stats["details"].setdefault(key, {"hits": 0, "misses": 0})
                _gpu_stats["details"][key]["misses"] += 1
                _gpu_stats["details"][key]["last"] = "device_mismatch"
                return False
            try:
                n1 = self.model.model.__class__.__name__
                n2 = other.model.model.__class__.__name__
                sz1 = self.model.model_size()
                sz2 = other.model.model_size()
                if n1 == n2 and sz1 == sz2:
                    _gpu_stats["calls"] += 1
                    _gpu_stats["class_hits"] += 1
                    _gpu_stats["details"].setdefault(key, {"hits": 0, "misses": 0})
                    _gpu_stats["details"][key]["hits"] += 1
                    _gpu_stats["details"][key]["last"] = "class_match"
                    return True
                # Fallback: match by model_type if class names differ
                # (e.g. CLIPLoader vs DualCLIPLoader wrappers)
                try:
                    t1 = self.model.model.model_type
                    t2 = other.model.model.model_type
                    if t1 == t2 and sz1 == sz2:
                        _gpu_stats["calls"] += 1
                        _gpu_stats["modeltype_hits"] += 1
                        _gpu_stats["details"].setdefault(key, {"hits": 0, "misses": 0})
                        _gpu_stats["details"][key]["hits"] += 1
                        _gpu_stats["details"][key]["last"] = "modeltype_match"
                        return True
                except Exception:
                    pass
                _gpu_stats["calls"] += 1
                _gpu_stats["misses"] += 1
                _gpu_stats["details"].setdefault(key, {"hits": 0, "misses": 0})
                _gpu_stats["details"][key]["misses"] += 1
                _gpu_stats["details"][key]["last"] = f"no_match_{n1}_vs_{n2}_sz{sz1}_vs_{sz2}"
                return False
            except Exception:
                _gpu_stats["calls"] += 1
                _gpu_stats["misses"] += 1
                _gpu_stats["details"].setdefault(key, {"hits": 0, "misses": 0})
                _gpu_stats["details"][key]["misses"] += 1
                _gpu_stats["details"][key]["last"] = "exception"
                return original_eq(self, other)

        comfy.model_management.LoadedModel.__eq__ = _eq
        comfy.model_management.LoadedModel._comfy_modal_patched = True

    def _patch_clip_text_encode_cache(self):
        """Cache CLIPTextEncode outputs by text input.

        The same text produces the same embedding every time, but ComfyUI
        re-runs the full Qwen 8B forward pass per ``executor.execute()``
        because its node cache is scoped per-execution.  This patch stores
        embeddings in a module-level cache keyed by text string.

        Called during ``restore()`` before the warmup workflow, which then
        pre-populates the cache by encoding the warmup text.  The real
        prompt's CLIPTextEncode hits the cache → 0ms clip_encode.
        """
        try:
            import nodes
            _clip_node_cls = nodes.NODE_CLASS_MAPPINGS.get("CLIPTextEncode")
            if _clip_node_cls is None:
                print("[comfyapp] clip_cache: CLIPTextEncode not found")
                return
            _func_name = getattr(_clip_node_cls, "FUNCTION", "encode")
            _orig = getattr(_clip_node_cls, _func_name)
            if getattr(_orig, '_comfy_modal_cached', False):
                return
            _cache: dict[tuple, object] = {}
            _cache_mode = "model_aware"
            def _cached(self_node, clip, text):
                # Build model-aware key: includes text, CLIP model identity,
                # resolved paths, clip_type, and class name for safe reuse.
                _paths = tuple(getattr(clip, '_warmup_model_paths', None) or [])
                _clip_type = getattr(clip, '_warmup_clip_type', '') or ''
                _cls_name = type(clip).__name__
                _key = (text, _paths, _clip_type, _cls_name, id(clip))
                # Fast path: exact clip object match
                if _key in _cache:
                    return _cache[_key]
                # Slightly relaxed key: same text + same model files (different obj)
                _relaxed = (text, _paths, _clip_type, _cls_name)
                if _relaxed in _cache:
                    return _cache[_relaxed]
                # Miss: encode and cache
                result = _orig(self_node, clip, text)
                _cache[_key] = result
                _cache[_relaxed] = result  # also cache relaxed key for future calls
                return result
            _cached._comfy_modal_cached = True
            _cached._cache_mode = _cache_mode
            # Expose cache so background encoding can populate it
            _clip_node_cls._clip_text_cache = _cache
            setattr(_clip_node_cls, _func_name, _cached)
            print(f"[comfyapp] clip_cache: patched {_clip_node_cls.__name__}.{_func_name} "
                  f"mode={_cache_mode}")
        except Exception as exc:
            print(f"[comfyapp] clip_cache: patch failed: {exc}")

    def _restore_in_process_gpu_state(self):
        """Re-enable ComfyUI GPU mode after a CPU-only snapshot import.

        During ``snap=True`` we force ComfyUI's CLI args and import-time
        model-management state into CPU mode so snapshot creation doesn't
        touch CUDA. The in-process backend is then snapshotted with that
        CPU-mode state. On restore we must explicitly flip ComfyUI back to
        GPU/HIGH_VRAM mode before the first real execution, otherwise model
        placement and tensor creation stay on CPU and CUDA-only attention
        paths fail with "Input tensors must be on cuda".
        """
        _t0 = time.time()
        import comfy.cli_args
        import comfy.model_management
        import psutil

        comfy.cli_args.args.cpu = False
        comfy.model_management.cpu_state = comfy.model_management.CPUState.GPU
        comfy.model_management.total_vram = (
            comfy.model_management.get_total_memory(comfy.model_management.get_torch_device())
            / (1024 * 1024)
        )
        comfy.model_management.total_ram = psutil.virtual_memory().total / (1024 * 1024)
        comfy.model_management.DISABLE_SMART_MEMORY = False
        if hasattr(comfy.model_management, "VRAMState") and hasattr(comfy.model_management.VRAMState, "HIGH_VRAM"):
            comfy.model_management.vram_state = comfy.model_management.VRAMState.HIGH_VRAM
        _t1 = time.time()
        print(f"[comfyapp] gpu_state restored vram={comfy.model_management.total_vram:.0f}MB "
              f"ram={comfy.model_management.total_ram:.0f}MB "
              f"vram_state={comfy.model_management.vram_state} "
              f"in {(_t1-_t0)*1000:.1f}ms")

    @modal.enter(snap=False)
    def restore(self):
        """Snapshot restore: reattach the GPU to the pre-initialised backend.

        ``startup()`` initialises the in-process ComfyUI backend under
        ``_force_cpu_during_snapshot()`` so the snapshot already contains
        the fully loaded Python state (modules, registered nodes,
        PromptExecutor, DummyServer) with **zero CUDA driver handles** —
        no SIGSEGV on restore.

        On restore we just need to:

        1. Reconnect the real GPU (``_warmup_cuda``).
        2. Select and apply the SageAttention runtime policy once the
           CUDA context is fresh.
        3. Force eager safetensors reads so model-load I/O happens up
           front instead of during compute.
        4. Optionally rebuild the GPU model cache via the warmup
           profile so the first prompt is fast.

        For the subprocess backend, the subprocess is still running from
        snap=True; we just probe ``/system_stats`` and restart on failure.
        """
        if not os.environ.get("COMFYMODAL_PRELOAD_MODE"):
            # Use env var for experiment flexibility, else module default
            pass

        restore_start = time.time()
        print(f"[comfyapp] lifecycle=restore snap=False restore_start_unix={restore_start}")
        __stages: dict[str, float] = {}
        # Clear any stale restore timing from a previous call
        self._last_restore_timing = None

        is_in_proc = (self._select_backend() == "in_process")

        _s = time.time()
        self._ensure_models_symlink()
        __stages["ensure_models_ms"] = self._profile_ms(_s)

        # ── Wait for FUSE volume mounts to become accessible ─────────────
        # After snapshot restore, the Modal FUSE daemon re-establishes its
        # backend connection asynchronously.  If we access the volume mount
        # point before the daemon is ready, os.path.isdir() returns False
        # and the volume appears empty.  This retry loop ensures both models
        # and custom nodes volumes are usable before we proceed.
        _s_vol_mount = time.time()
        _wait_seconds = [0.2, 0.5, 1.0, 2.0, 3.0]
        for vol_obj, mount_path, label in [
            (vol, MODELS_PATH, "models"),
            (custom_nodes_vol, CUSTOM_NODES_PATH, "custom_nodes"),
        ]:
            for _attempt in range(len(_wait_seconds)):
                vol_obj.reload()
                if os.path.isdir(mount_path):
                    if _attempt > 0:
                        print(f"[comfyapp] volume_mount_ready label={label} attempt={_attempt + 1}")
                    break
                if _attempt < len(_wait_seconds) - 1:
                    _delay = _wait_seconds[_attempt]
                    print(f"[comfyapp] volume_mount_wait label={label} attempt={_attempt + 1} delay_s={_delay}")
                    time.sleep(_delay)
            else:
                print(f"[comfyapp] volume_mount_failed label={label} mount_path={mount_path}")
        __stages["volume_mount_wait_ms"] = self._profile_ms(_s_vol_mount)

        # Reload custom nodes volume and sync any nodes added since the snapshot
        # was taken.  The snapshot filesystem only contains custom_nodes symlinks
        # from the time of snap=True; post-snapshot volume writes must be picked
        # up explicitly here or the restored container won't see them.
        _s2 = time.time()
        _cn_summary, self._custom_nodes_state = self._sync_custom_nodes_from_volume()
        _cn_created = _cn_summary.get("created", [])
        __stages["custom_nodes_sync_ms"] = self._profile_ms(_s2)
        __stages["custom_nodes_created"] = len(_cn_created)
        if _cn_created:
            print(f"[comfyapp] restore synced new custom nodes: {_cn_created}")

        __stages["preload_mode"] = _resolve_preload_mode()
        __stages["preload_mode_source"] = "file" if os.path.isfile(PRELOAD_MODE_PATH) else "env_var"

        # ── CacheDiT override ──
        if DISABLE_CACHEDIT_FOR_Z_IMAGE and is_in_proc:
            try:
                import nodes as _cd_nodes
                _cd_cls = _cd_nodes.NODE_CLASS_MAPPINGS.get("CacheDiT_Model_Optimizer")
                if _cd_cls is not None:
                    if _patch_cachedit_node_class(_cd_cls):
                        print("[comfyapp] DISABLE_CACHEDIT_FOR_Z_IMAGE=1: patched CacheDiT_Model_Optimizer -> noop")
                        __stages["disable_cachedit"] = 1
                    else:
                        print("[comfyapp] DISABLE_CACHEDIT_FOR_Z_IMAGE=1: CacheDiT_Model_Optimizer already patched or not found")
                        __stages["disable_cachedit"] = 1
                else:
                    print("[comfyapp] DISABLE_CACHEDIT_FOR_Z_IMAGE=1: CacheDiT_Model_Optimizer class not registered")
                    __stages["disable_cachedit"] = 0
            except Exception as _cd_exc:
                print(f"[comfyapp] DISABLE_CACHEDIT_FOR_Z_IMAGE=1: patch failed: {_cd_exc}")
                __stages["disable_cachedit"] = 0
        else:
            __stages["disable_cachedit"] = 0

        # ── Pre-resolve warmup profile + model paths ─────────────────────
        # FUSE stat calls for model file location are I/O-bound and
        # independent of GPU state.  Resolving them early (before the
        # GPU/Sage warmup section below) lets these stat calls overlap
        # with GPU warmup, hiding ~200-600ms of latency.
        _warmup_profile = None
        _warmup_paths: list[str] = []
        if ENABLE_WARMUP:
            _s = time.time()
            _warmup_profile = self._snapshot_preload_profile()
            if _warmup_profile:
                _warmup_paths = self._snapshot_preload_paths(_warmup_profile)
            __stages["early_path_resolve_ms"] = self._profile_ms(_s)
            print(
                f"[comfyapp] restore warmup selection current_workflow_stack={_warmup_profile.get('_current_workflow_stack', {}) if _warmup_profile else {}} "
                f"selected_warmup_profile={_warmup_profile or {}} profile_source={_warmup_profile.get('_source', 'none') if _warmup_profile else 'none'} "
                f"workflow_hash={_warmup_profile.get('_workflow_hash', '') if _warmup_profile else ''} "
                f"profile_token={_warmup_profile.get('_profile_token', '') if _warmup_profile else ''}"
            )

        if is_in_proc:
            # If backend was skipped during snap=True (snapshot_mode=none/minimal),
            # initialize it now with full GPU access (no force_cpu).
            _backend_inited = getattr(self, "_event_loop", None) is not None
            _backend_deferred = False
            if not _backend_inited:
                _s = time.time()
                print("[comfyapp] deferred backend init on restore (snapshot_mode=none)")
                self._start_backend()
                __stages["deferred_backend_init_ms"] = self._profile_ms(_s)
                _backend_deferred = True
                _backend_inited = True

            # Register any custom node classes that were added to the volume
            # after the snapshot was taken.  _start_backend() already called
            # nodes.init_extra_nodes() for the deferred case above, but for the
            # snapshot-restored case the NODE_CLASS_MAPPINGS is stale.
            if _backend_inited and not _backend_deferred and _cn_created:
                _s_cn_req = time.time()
                _cn_reqs = self._install_custom_node_requirements()
                __stages["custom_node_requirements_ms"] = self._profile_ms(_s_cn_req)
                __stages["custom_node_requirements_installed"] = len(_cn_reqs.get("installed", []))
                __stages["custom_node_requirements_skipped"] = len(_cn_reqs.get("skipped", []))
                _s_cn = time.time()
                import nodes as _restore_nodes
                self._event_loop.run_until_complete(_restore_nodes.init_extra_nodes())
                __stages["custom_nodes_reinit_ms"] = self._profile_ms(_s_cn)

            if ENABLE_GPU_SNAPSHOT and _backend_inited and not _backend_deferred:
                # GPU snapshot restored — ComfyUI already initialised with GPU
                # (CUDA context, HIGH_VRAM mode, executor, etc. are captured).
                # Skip _restore_in_process_gpu_state() but still recalculate
                # VRAM/RAM in case the restore host differs.
                _s = time.time()
                import comfy.model_management
                import psutil
                comfy.model_management.total_vram = (
                    comfy.model_management.get_total_memory(comfy.model_management.get_torch_device())
                    / (1024 * 1024)
                )
                comfy.model_management.total_ram = psutil.virtual_memory().total / (1024 * 1024)
                __stages["gpu_state_ms"] = self._profile_ms(_s)

                _s = time.time()
                self._warmup_cuda()
                __stages["cuda_warmup_ms"] = self._profile_ms(_s)
                self._log_profile("restore_warmup", mode="cuda_warmup_gpu_snap", duration_ms=__stages["cuda_warmup_ms"])
                # Retry custom-node registrations that failed during CPU snapshot
                self._retry_pending_custom_node_registrations()
                import comfy.utils
                comfy.utils.DISABLE_MMAP = True

                _s = time.time()
                mode, reason = self._select_sage_runtime_mode()
                self._apply_sage_attention_policy()
                __stages["sage_runtime_ms"] = self._profile_ms(_s)
                __stages["sage_mode"] = mode
                __stages["sage_reason"] = reason
                __stages["sage_env_mode"] = SAGE_RUNTIME_MODE
                __stages["sage_probe_on_restore"] = 1 if SAGE_RUNTIME_PROBE_ON_RESTORE else 0
                self._log_profile(
                    "restore_sage_runtime",
                    mode=mode,
                    reason=reason,
                    duration_ms=__stages["sage_runtime_ms"],
                )
            else:
                if not _backend_deferred:
                    # CPU-only snapshot — the in-process backend was initialised
                    # under force_cpu, so no CUDA state was captured.  Reattach
                    # the GPU, warm CUDA, select Sage runtime.
                    _s = time.time()
                    self._restore_in_process_gpu_state()
                    __stages["gpu_state_ms"] = self._profile_ms(_s)
                else:
                    # Deferred init: backend already started with GPU
                    __stages["gpu_state_ms"] = 0.0
                    __stages["gpu_state_source"] = "deferred"

                _s = time.time()
                self._warmup_cuda()
                __stages["cuda_warmup_ms"] = self._profile_ms(_s)
                self._log_profile("restore_warmup", mode="cuda_warmup", duration_ms=__stages["cuda_warmup_ms"])
                # Retry custom-node registrations that failed during CPU snapshot
                # (e.g. schema generation that needs device availability).
                self._retry_pending_custom_node_registrations()
                import comfy.utils
                comfy.utils.DISABLE_MMAP = True
                if _resolve_runtime_flag('deep_profile', '0'):
                    self._patch_model_cache_comparison()
                self._patch_clip_text_encode_cache()
                self._patch_clip_loader_cache()
                self._patch_unet_loader_cache()
                self._patch_vae_loader_cache()

                # ── CLIP encode cache debug: clear if requested ──────────
                _clip_cache_clear = _resolve_runtime_flag('clear_clip_encode_cache', '0')
                __stages["clip_cache_clear_requested"] = 1 if _clip_cache_clear else 0
                if _clip_cache_clear:
                    try:
                        import nodes
                        _te_cls = nodes.NODE_CLASS_MAPPINGS.get("CLIPTextEncode")
                        if _te_cls and hasattr(_te_cls, '_clip_text_cache'):
                            _te_cls._clip_text_cache.clear()
                            __stages["clip_cache_cleared"] = 1
                            print("[comfyapp] clip_encode_cache: cleared by flag")
                    except Exception as exc:
                        print(f"[comfyapp] clip_encode_cache: clear failed: {exc}")
                # Cache size at restore start
                try:
                    import nodes
                    _te_cls = nodes.NODE_CLASS_MAPPINGS.get("CLIPTextEncode")
                    if _te_cls and hasattr(_te_cls, '_clip_text_cache'):
                        __stages["clip_cache_size_at_start"] = len(_te_cls._clip_text_cache)
                except Exception:
                    pass

                _s = time.time()
                mode, reason = self._select_sage_runtime_mode()
                self._apply_sage_attention_policy()
                __stages["sage_runtime_ms"] = self._profile_ms(_s)
                __stages["sage_mode"] = mode
                __stages["sage_reason"] = reason
                __stages["sage_env_mode"] = SAGE_RUNTIME_MODE
                __stages["sage_probe_on_restore"] = 1 if SAGE_RUNTIME_PROBE_ON_RESTORE else 0
                self._log_profile(
                    "restore_sage_runtime",
                    mode=mode,
                    reason=reason,
                    duration_ms=__stages["sage_runtime_ms"],
                )

            # Log intermediate restore phases (numeric-only to avoid round() on strings)
            phases = {k: round(v, 1) for k, v in __stages.items()
                      if not k.startswith("warmup_") and isinstance(v, (int, float))}
            print(f"[comfyapp] restore phases (pre-warmup): {phases}")

            # ── Warmup: load models + encode text (for clip cache) ──────
            if ENABLE_WARMUP:
                profile = _warmup_profile
                preload_paths = _warmup_paths
                __stages["warmup_profile_source"] = profile.get("_source", "?") if profile else "none"
                preload_result = {"count": 0, "file_timing_ms": {}}
                _pm = _resolve_preload_mode()

                # ── PART 3: Preload guardrails ──
                # Skip CPU preload for unknown/new workflows unless explicitly
                # enabled.  This prevents wasting ~125s reading 19GB for
                # workflows that may fail validation or never execute.
                _preload_skip_reason = None
                _profile_source = (profile or {}).get("_source", "none")
                _workflow_hash = (profile or {}).get("_workflow_hash", "")

                # Guard 1: Known-good workflow profile check
                # active_next_profile alone does not mean known-good.
                # Only known_good_workflow_profiles.json can make it eligible.
                if _preload_skip_reason is None:
                    if not PRELOAD_UNKNOWN_PROFILES:
                        if _profile_source == "active_next_profile" and _workflow_hash:
                            if _is_known_good_workflow_profile(_workflow_hash, profile or {}):
                                print(
                                    f"[comfyapp] preload known-good profile "
                                    f"workflow_hash={_workflow_hash}"
                                )
                            else:
                                _preload_skip_reason = "unknown_profile"
                                print(
                                    f"[comfyapp] preload_skipped reason=unknown_profile "
                                    f"workflow_hash={_workflow_hash or 'missing'} "
                                    f"profile_source={_profile_source} "
                                    f"COMFYMODAL_PRELOAD_UNKNOWN_PROFILES=0"
                                )
                        else:
                            _preload_skip_reason = "unknown_profile"
                            print(
                                f"[comfyapp] preload_skipped reason=unknown_profile "
                                f"profile_source={_profile_source} "
                                f"workflow_hash={_workflow_hash or 'missing'} "
                                f"COMFYMODAL_PRELOAD_UNKNOWN_PROFILES=0"
                            )

                # Guard 2: Size guardrails via _filter_preload_paths_by_size
                if _preload_skip_reason is None and preload_paths:
                    _filtered_paths, _filter_result = _filter_preload_paths_by_size(preload_paths)
                    if not _filtered_paths:
                        _preload_skip_reason = _filter_result.get("reason", "size_filtered")
                        print(
                            f"[comfyapp] preload_skipped reason={_preload_skip_reason} "
                            f"{_filter_result}"
                        )
                    else:
                        preload_paths = _filtered_paths

                if _preload_skip_reason:
                    preload_paths = []
                    __stages["preload_skipped"] = 1
                    __stages["preload_skip_reason"] = _preload_skip_reason

                # ── Z-Image restore warmup skip ──
                if DISABLE_RESTORE_WARMUP_FOR_Z_IMAGE and profile and profile.get("unet", ""):
                    _wu_unet = profile.get("unet", "").lower()
                    if "z_image" in _wu_unet or "z-image" in _wu_unet:
                        print(f"[comfyapp] DISABLE_RESTORE_WARMUP_FOR_Z_IMAGE=1: skipping restore warmup for {_wu_unet}")
                        preload_paths = []
                        __stages["warmup_preload_skipped"] = 1
                _s = time.time()
                if preload_paths and _pm != "off":
                    if _pm == "async_no_wait":
                        import threading
                        _preload_thread = threading.Thread(
                            target=self._preload_models_to_cpu,
                            args=(preload_paths,),
                            kwargs={"budget_ms": None},
                            daemon=True,
                        )
                        _preload_thread.start()
                        preload_result = {"count": 0, "file_timing_ms": {}, "async": True}
                        print(f"[comfyapp] preload async_no_wait: thread started for {len(preload_paths)} files, not blocking restore")
                    elif _pm.startswith("budgeted_"):
                        # Extract budget from suffix: budgeted_1500ms → 1500, budgeted_2000ms → 2000
                        try:
                            _budget = float(_pm.replace("budgeted_", "").replace("ms", ""))
                        except (ValueError, TypeError):
                            _budget = 1500.0
                        preload_result = self._preload_models_to_cpu(preload_paths, budget_ms=_budget)
                        if preload_result.get("budget_exceeded"):
                            print(f"[comfyapp] preload budgeted_{int(_budget)}ms: budget exceeded, loaded {preload_result.get('count', 0)}/{len(preload_paths)} files")
                    else:
                        preload_result = self._preload_models_to_cpu(preload_paths)
                __stages["warmup_preload_ms"] = self._profile_ms(_s)
                for fname, d_ms in preload_result.get("file_timing_ms", {}).items():
                    safe_key = f"warmup_{fname.replace('.','_').replace('-','_').lower()}_ms"
                    __stages[safe_key] = d_ms
                self._log_profile(
                    "restore_warmup_preload",
                    mode=profile.get("mode", "none") if profile else "none",
                    files=len(preload_paths),
                    cached=preload_result.get("count", 0),
                    duration_ms=__stages["warmup_preload_ms"],
                )
                warmup_result = {"mode": profile.get("mode", "none") if profile else "none", "status": "ok", "preload_count": preload_result.get("count", 0)}

                # ── ModelPatcher lineage trace (creation / clone / flow) ─
                # Logs every ModelPatcher.__init__ and .clone() with caller
                # context to find where identity diverges from warmup.
                _mp_trace = _resolve_runtime_flag('modelpatcher_trace', '0')
                if _mp_trace:
                    try:
                        import comfy.model_patcher as _cmpat
                        import traceback as _ctb
                        _orig_mp_init = _cmpat.ModelPatcher.__init__
                        _orig_mp_clone = _cmpat.ModelPatcher.clone
                        def _traced_init(self, model, load_device, offload_device, size=0, weight_inplace_update=False):
                            _orig_mp_init(self, model, load_device, offload_device, size, weight_inplace_update)
                            # Attach stable key from cached_patcher_init if available
                            _stable_key = getattr(self, '_comfy_modal_stable_key', None)
                            if _stable_key is None and hasattr(self, 'cached_patcher_init') and self.cached_patcher_init:
                                try:
                                    _func, _args = self.cached_patcher_init
                                    if _func and len(_args) >= 1:
                                        import os as _mp_os
                                        _path = _mp_os.path.realpath(_args[0]) if hasattr(_mp_os.path, 'realpath') else str(_args[0])
                                        _opts = str(sorted(_args[1].items())) if len(_args) > 1 and _args[1] else "default"
                                        self._comfy_modal_stable_key = {"resolved_path": _path, "options_str": _opts, "model_class": model.__class__.__name__}
                                        _stable_key = self._comfy_modal_stable_key
                                except Exception:
                                    pass
                            # Fallback: compute from model attributes
                            if _stable_key is None:
                                self._comfy_modal_stable_key = {
                                    "resolved_path": "unknown",
                                    "options_str": "unknown",
                                    "model_class": model.__class__.__name__ if hasattr(model, '__class__') else '?',
                                }
                                _stable_key = self._comfy_modal_stable_key
                            import comfy.samplers as _mp_samp
                            if not hasattr(_mp_samp, '_comfy_modal_mp_trace'):
                                _mp_samp._comfy_modal_mp_trace = []
                            _mp_trace_list = _mp_samp._comfy_modal_mp_trace
                            _frames = list(_ctb.walk_stack(None))[-10:-1]
                            _short = ["{}:{}:{}".format(f[0].f_code.co_filename.split('/')[-1].split('\\')[-1] if f[0] else '?', f[1], f[0].f_code.co_name if f[0] else '?') for f in _frames]
                            _mp_trace_list.append({"event":"CREATE","patcher_id":id(self),"model_id":id(model),"model_class":model.__class__.__name__,"stable_key":str(_stable_key),"callers":_short})
                        def _traced_clone(self, disable_dynamic=False, model_override=None):
                            _result = _orig_mp_clone(self, disable_dynamic, model_override)
                            import comfy.samplers as _mp_samp2
                            if hasattr(_mp_samp2, '_comfy_modal_mp_trace'):
                                _tl = _mp_samp2._comfy_modal_mp_trace
                                _frames = list(_ctb.walk_stack(None))[-10:-1]
                                _short = []
                                for _f2 in _frames:
                                    _fn2 = _f2[0].f_code.co_filename.split('/')[-1].split('\\')[-1] if _f2[0] else '?'
                                    _ln2 = _f2[1]
                                    _nm2 = _f2[0].f_code.co_name if _f2[0] else '?'
                                    _short.append("{}:{}:{}".format(_fn2, _ln2, _nm2))
                                _same = hasattr(_result, 'model') and hasattr(self, 'model') and _result.model is self.model
                                _tl.append({"event":"CLONE","from_id":id(self),"to_id":id(_result),"model_id":id(self.model) if hasattr(self,'model') else '?',"same_model":_same,"callers":_short})
                            return _result
                        _cmpat.ModelPatcher.__init__ = _traced_init
                        _cmpat.ModelPatcher.clone = _traced_clone
                        print("[comfyapp] modelpatcher_trace INSTALLED")
                    except Exception as _mpt_exc:
                        print(f"[comfyapp] modelpatcher_trace FAILED: {_mpt_exc}")
                    # Also trace key node functions
                    try:
                        import comfy_extras.nodes_custom_sampler as _mpncs
                        _orig_cfg_exec = _mpncs.CFGGuider.execute
                        _orig_sca_exec = _mpncs.SamplerCustomAdvanced.execute
                        @classmethod
                        def _traced_cfg_exec(cls, model, positive, negative, cfg):
                            import comfy.samplers as _mp_samp3
                            if hasattr(_mp_samp3, '_comfy_modal_mp_trace'):
                                _mp_samp3._comfy_modal_mp_trace.append({"event":"CFGGuider_INPUT","patcher_id":id(model),"model_id":id(model.model) if hasattr(model,'model') else '?'})
                            result = _orig_cfg_exec(model, positive, negative, cfg)
                            return result
                        @classmethod
                        def _traced_sca_exec(cls, noise, guider, sampler, sigmas, latent_image):
                            import comfy.samplers as _mp_samp4
                            _mp = getattr(guider, 'model_patcher', None)
                            if _mp and hasattr(_mp_samp4, '_comfy_modal_mp_trace'):
                                _mp_samp4._comfy_modal_mp_trace.append({"event":"SamplerCustomAdvanced_GUIDER_MP","patcher_id":id(_mp),"model_id":id(_mp.model) if hasattr(_mp,'model') else '?'})
                            result = _orig_sca_exec(noise, guider, sampler, sigmas, latent_image)
                            return result
                        _mpncs.CFGGuider.execute = _traced_cfg_exec
                        _mpncs.CFGGuider.get_guider = _traced_cfg_exec
                        _mpncs.SamplerCustomAdvanced.execute = _traced_sca_exec
                        _mpncs.SamplerCustomAdvanced.sample = _traced_sca_exec
                    except Exception as _mptn_exc:
                        print(f"[comfyapp] modelpatcher_trace node patch FAILED: {_mptn_exc}")

                # ── Canonical ModelPatcher cache (warmup→prompt reuse) ──
                _mp_cache = _resolve_runtime_flag('modelpatcher_cache', '0')
                _mp_cache_dryrun = _resolve_runtime_flag('modelpatcher_cache_dryrun', '0')
                _mp_cache_store = {}
                if _mp_cache or _mp_cache_dryrun:
                    try:
                        import comfy.sd as _csd
                        import os as _os
                        _orig_load_diff = _csd.load_diffusion_model
                        def _cached_load_diff(unet_path, model_options=None, disable_dynamic=False):
                            if model_options is None:
                                model_options = {}
                            _real = _os.path.realpath(unet_path) if hasattr(_os.path, 'realpath') else unet_path
                            _opts_str = str(sorted(model_options.items())) if model_options else "default"
                            _key = (_real, _opts_str)
                            _hit = _key in _mp_cache_store
                            if _mp_cache_dryrun or _mp_cache:
                                print(f"[comfyapp] modelpatcher_cache: key={_key} hit={_hit} dryrun={_mp_cache_dryrun} active={_mp_cache}")
                            if _mp_cache and _hit:
                                _cached = _mp_cache_store[_key]
                                print(f"[comfyapp] modelpatcher_cache HIT — returning cached ModelPatcher id={id(_cached)}")
                                return _cached
                            _result = _orig_load_diff(unet_path, model_options=model_options, disable_dynamic=disable_dynamic)
                            if not _hit:
                                _mp_cache_store[_key] = _result
                                print(f"[comfyapp] modelpatcher_cache STORE — key={_key} patcher_id={id(_result)} model_id={id(_result.model) if hasattr(_result,'model') else 0}")
                            # Tag with stable key for identity matching
                            try:
                                _result._comfy_modal_stable_key = {
                                    "resolved_path": _real,
                                    "options_str": _opts_str,
                                    "model_class": _result.model.__class__.__name__ if hasattr(_result, 'model') else '?',
                                    "model_id": id(_result.model) if hasattr(_result, 'model') else 0,
                                }
                            except Exception:
                                pass
                            return _result
                        _csd.load_diffusion_model = _cached_load_diff
                    except Exception as _mp_exc:
                        print(f"[comfyapp] modelpatcher_cache install FAILED: {_mp_exc}")

                # ── Direct warmup (no ComfyUI executor) ──────────────────
                # Calls UNETLoader, CLIPLoader, and CLIPTextEncode node
                # functions directly instead of _execute_in_process().
                # This saves ~800ms of executor dispatch overhead while
                # still loading UNET into GPU cache and priming the
                # CLIPTextEncode text cache.
                _skip_direct_warmup = False
                if DISABLE_RESTORE_WARMUP_FOR_Z_IMAGE and profile and profile.get("unet", ""):
                    _wu_unet = profile.get("unet", "").lower()
                    if "z_image" in _wu_unet or "z-image" in _wu_unet:
                        print(f"[comfyapp] DISABLE_RESTORE_WARMUP_FOR_Z_IMAGE=1: skipping direct warmup for {_wu_unet}")
                        _skip_direct_warmup = True

                # ── PART 8: Known-good guard before direct warmup ──
                if not _skip_direct_warmup and profile and profile.get("mode"):
                    _wg_workflow_hash = (profile or {}).get("_workflow_hash", "")
                    _wg_load_unet = _resolve_runtime_flag("DIRECT_WARMUP_LOAD_UNET", "0")
                    _wg_load_clip = _resolve_runtime_flag("DIRECT_WARMUP_LOAD_CLIP", "0")
                    if (_wg_load_unet or _wg_load_clip) and not PRELOAD_UNKNOWN_PROFILES:
                        if _wg_workflow_hash and _is_known_good_workflow_profile(_wg_workflow_hash, profile or {}):
                            print(
                                f"[comfyapp] direct warmup known-good profile "
                                f"workflow_hash={_wg_workflow_hash}"
                            )
                        else:
                            _skip_direct_warmup = True
                            print(
                                f"[comfyapp] direct_warmup_skipped reason=not_known_good "
                                f"workflow_hash={_wg_workflow_hash or 'missing'} "
                                f"load_unet={_wg_load_unet} load_clip={_wg_load_clip}"
                            )
                if profile and profile.get("mode") and not _skip_direct_warmup:
                    _s = time.time()
                    _dw = self._warmup_direct(profile)
                    __stages["warmup_direct_total_ms"] = _dw.get("direct_total_ms", 0.0)
                    for _k in ("direct_unet_load_ms", "direct_clip_load_ms", "direct_clip_encode_ms"):
                        _v = _dw.get(_k)
                        if _v is not None:
                            __stages[f"warmup_{_k}"] = _v
                    for _flag in ("direct_warmup_load_unet", "direct_warmup_load_clip",
                                  "direct_warmup_clip_encode", "direct_warmup_require_cpu_cache_hit",
                                  "direct_unet_cpu_hit", "direct_clip_cpu_hit"):
                        _v = _dw.get(_flag)
                        if _v is not None:
                            __stages[_flag] = _v
                    if _dw.get("status") != "ok":
                        warmup_result["error"] = _dw.get("error", "direct warmup failed")
                        warmup_result["status"] = "error"
                        print(f"[comfyapp] direct warmup FAILED — executor bypass disabled")
                        # No executor fallback: direct warmup is the only path.
                        # If it fails, models load during inference (acceptable).
                    # Remove cleanup suppression (not needed without executor)
                    try:
                        import comfy.model_management as _mm
                        if hasattr(_mm, '_comfy_modal_suppress_cleanup'):
                            _mm._comfy_modal_suppress_cleanup = False
                    except Exception:
                        pass
        else:
            _s = time.time()
            try:
                self._http_client.get("/system_stats", timeout=5)
            except Exception:
                print("[comfyapp] ComfyUI unresponsive on restore, restarting")
                self._restart_comfy()
            __stages["subprocess_health_ms"] = self._profile_ms(_s)
            # Subprocess backend: restart to pick up new custom node symlinks
            if _cn_created:
                _s_cn = time.time()
                print(f"[comfyapp] restarting subprocess due to new custom nodes: {_cn_created}")
                self._restart_comfy()
                __stages["custom_nodes_restart_ms"] = self._profile_ms(_s_cn)

        # CLIP cache size after warmup
        try:
            import nodes
            _te_cls = nodes.NODE_CLASS_MAPPINGS.get("CLIPTextEncode")
            if _te_cls and hasattr(_te_cls, '_clip_text_cache'):
                __stages["clip_cache_size_after_warmup"] = len(_te_cls._clip_text_cache)
        except Exception:
            pass

        # Annotate warmup with per-node timing breakdown
        _wr = locals().get("warmup_result") or {}
        warmup_nodes = _wr.get("node_timing", {}) if isinstance(_wr, dict) else {}
        warmup_status = _wr.get("status", "?") if isinstance(_wr, dict) else "?"
        warmup_error = str(_wr.get("error", ""))[:200] if isinstance(_wr, dict) else ""
        # Collect model cache diagnostics
        _cpu_hits = dict(getattr(self, "_cpu_cache_hits", {}))
        _cpu_misses = dict(getattr(self, "_cpu_cache_misses", {}))
        _gpu_stats: dict = {}
        try:
            import comfy.model_management as _mm
            _gpu_stats = dict(getattr(_mm, "_gpu_cache_eq_stats", {}))
        except Exception:
            pass
        # CLIP object cache diagnostics
        _clip_cache = getattr(self, '_clip_object_cache', {})
        _clip_cache_report = {
            "size": len(_clip_cache),
            "keys": [str(k) for k in _clip_cache.keys()],
        }
        _restore_end = time.time()
        self._last_restore_timing = {
            "restore_total_ms": self._profile_ms(restore_start),
            "restore_start_unix_s": restore_start,
            "restore_end_unix_s": _restore_end,
            "warmup_status": warmup_status,
            "warmup_profile": _warmup_profile or {},  # actual profile used during restore
            "warmup_profile_source": (_warmup_profile or {}).get("_source", "none"),
            "warmup_profile_token": (_warmup_profile or {}).get("_profile_token", ""),
            **__stages,
            **({f"warmup_{k}": v for k, v in warmup_nodes.items()} if warmup_nodes else {}),
            "cpu_cache_hits": _cpu_hits,
            "cpu_cache_misses": _cpu_misses,
            "gpu_cache_eq": _gpu_stats,
            "clip_cache": _clip_cache_report,
        }
        if warmup_error:
            self._last_restore_timing["warmup_error"] = warmup_error
        print(f"[comfyapp] restore sanity check done in {time.time() - restore_start:.3f}s "
              f"perf={self._last_restore_timing}")

    @modal.exit()
    def shutdown(self):
        if self._http_client_obj is not None:
            self._http_client_obj.close()
            self._http_client_obj = None
        if getattr(self, "_proc", None) and self._proc.poll() is None:
            self._proc.terminate()
            try:
                self._proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self._proc.kill()

    def _wait_for_comfy(self):
        for _ in range(120):
            try:
                self._http_client.get("/system_stats")
                return
            except Exception:
                time.sleep(1)
        raise RuntimeError("ComfyUI API failed to start")

    @modal.method()
    def object_info(self):
        if self._select_backend() == "in_process":
            # Return a simplified node registry (class names only) that is
            # JSON-serializable.  NODE_CLASS_MAPPINGS values are class objects
            # and cannot be json.dumps'd directly.
            import nodes
            return {
                "status": "ok",
                "in_process": True,
                "node_count": len(nodes.NODE_CLASS_MAPPINGS),
                "class_types": sorted(nodes.NODE_CLASS_MAPPINGS.keys()),
            }
        r = self._http_client.get("/object_info")
        return r.json()

    @modal.method()
    def refresh_custom_nodes(self, expected_nodes: list[str] | None = None):
        expected_nodes = expected_nodes or []
        last_missing = []
        summary = None
        current_state = ()
        for attempt in range(5):
            summary, current_state = self._sync_custom_nodes_from_volume()
            last_missing = missing_expected_nodes(current_state, expected_nodes)
            if not last_missing:
                self._custom_nodes_state = current_state
                self._restart_comfy()
                return {"status": "ok", **summary}
            if attempt < 4:
                time.sleep(1)
        raise RuntimeError(f"Synced custom nodes not visible in Modal volume yet: {last_missing}")

    @modal.method()
    def run_prompt(
        self,
        workflow: dict,
        input_images: dict | None = None,
        trace: dict | None = None,
        modal_options: dict | None = None,
    ) -> dict:
        """Submit a workflow for execution.

        Custom nodes volume is reloaded and symlinks are synced before
        every prompt so the container always sees the latest set of
        custom nodes.  When new nodes are detected their Python
        dependencies are installed and ComfyUI node classes are
        re-registered automatically.

        The optional ``trace`` parameter is a dict of pre-collected
        timestamps from the local ComfyUI server (browser t0, local t1,
        local t2).  The Modal side merges its own t3..t8 markers into
        the trace and returns the merged dict in the response under
        the ``"trace"`` key.
        """

        # Build a Trace anchored at the earliest known wall-clock time
        # we can find (t0 from the browser).  When no browser t0 is
        # available the anchor falls back to "right now", so all later
        # timestamps are still consistent with each other.
        t0 = coerce_t0_from_browser(trace or {})
        prompt_id_hint = ""
        if isinstance(trace, dict):
            prompt_id_hint = str(trace.get("prompt_id") or "")
        if not prompt_id_hint and isinstance(workflow, dict):
            for node in workflow.values():
                if isinstance(node, dict) and "prompt_id" in node:
                    prompt_id_hint = str(node["prompt_id"])
        server_trace = Trace(prompt_id=prompt_id_hint, t0=t0)
        server_trace.update(trace)
        # t3 = Modal handler entry.  On a cold container this is *after*
        # snapshot restore + CUDA warmup; on a warm container it is just
        # the time the function was dispatched.
        server_trace.mark("t3_modal_entry")

        # ── Check for scheduler test mode ──
        _scheduler_config_ns = (modal_options or {}).get("comfymodal_scheduler_test")
        _is_scheduler_test_ns = isinstance(_scheduler_config_ns, dict) and _scheduler_config_ns.get("enabled")
        _scheduler_trace_ns = None

        if _is_scheduler_test_ns:
            self._preflight_already_ran = False
            self._start_scheduler_test(workflow, _scheduler_config_ns)
            _scheduler_trace_ns = self._scheduler_wait_and_finalize()
            self._preflight_already_ran = True
        else:
            # ── Shared custom-node sync and dependency policy ──
            # Replaces the inline custom-node sync + preflight logic with a
            # single method used by both run_prompt and run_prompt_stream.
            self._preflight_already_ran = False
            _cn_sync_start = time.time()
            _policy = self._handle_custom_node_sync_and_dependency_policy(workflow, stream=False)
            self._preflight_already_ran = True
            __stages = getattr(self, "_last_restore_timing", None)
            if isinstance(__stages, dict):
                __stages["run_prompt_cn_sync_ms"] = round((time.time() - _cn_sync_start) * 1000, 1)
                __stages["run_prompt_cn_created"] = _policy.get("sync_created_count", 0)

        # ── In-process backend: direct execution, no HTTP ──
        if self._select_backend() == "in_process":
            total_started = time.time()
            _last_graph_validate_ms = getattr(self, "_last_graph_validate_ms", None)
            result = self._execute_in_process(workflow, input_images, trace=server_trace, modal_options=modal_options)
            _graph_validate_ms = getattr(self, "_last_graph_validate_ms", None)

            # ── Model residency log ──
            try:
                import comfy.model_management as _rmm
                _loaded = getattr(_rmm, "current_loaded_models", [])
                _cpu_cache = getattr(self, "_model_cpu_cache", {})
                _clip_cache = getattr(self, "_clip_object_cache", {})
                _rt = getattr(self, "_last_restore_timing", None) or {}
                print(f"[model_residency] loaded_models_count={len(_loaded)}")
                print(f"[model_residency] cpu_cache_keys={len(_cpu_cache)}")
                print(f"[model_residency] clip_cache_size={len(_clip_cache)}")
                print(f"[model_residency] did_unload_models=0")
                print(f"[model_residency] did_clear_cache=0")
            except Exception:
                pass

            _t8b_t0 = time.time()

            _s = time.time()
            requested_stack = extract_requested_model_stack(workflow)
            if requested_stack and any(requested_stack.values()):
                self._save_last_warmup_workflow(workflow)
                self._save_last_model_stack(requested_stack)
            _t8b_save_stack_ms = round((time.time() - _s) * 1000, 1)

            _s = time.time()
            _wp = {}
            _rt = getattr(self, "_last_restore_timing", None) or {}
            for _k in ("warmup_status", "warmup_preload_ms", "warmup_direct_total_ms", "warmup_direct_clip_load_ms", "direct_unet_load_ms", "direct_clip_load_ms"):
                _v = _rt.get(_k)
                if _v is not None:
                    _wp[_k] = _v
            print(f"[comfyapp] warmup_profile_during_restore: {_wp}")
            selected_profile = dict((_rt.get("warmup_profile") or {}))
            match_info = self._log_warmup_vs_workflow_diagnostics(selected_profile, requested_stack, raw_workflow=workflow)
            print(
                f"[comfyapp.profile] WARMUP_PROFILE_MATCH={'true' if all(v is not False for v in match_info.get('match', {}).values()) else 'false'} "
                f"profile_source={selected_profile.get('_source', 'none')} profile_token={selected_profile.get('_profile_token', '')} "
                f"workflow_hash={selected_profile.get('_workflow_hash', '')}"
            )
            _t8b_diag_ms = round((time.time() - _s) * 1000, 1)

            _s = time.time()
            total_ms = round((time.time() - total_started) * 1000, 1)
            server_trace.mark("t9_modal_return")

            # ── Timing (non-streaming path) ──
            _rt3 = getattr(self, "_last_restore_timing", None) or {}
            _stages_ns = server_trace._t
            _t3_ns = _stages_ns.get("t3_modal_entry", total_started)
            _s_start_ns = _stages_ns.get("t6_sampler_start", 0)
            _s_end_ns = _stages_ns.get("t6_sampler_end", 0)
            _restore_end_to_prompt_ns = round((total_started - _t3_ns) * 1000, 1) if _t3_ns else 0
            _prompt_to_sampler_ns = round((_s_start_ns - total_started) * 1000, 1) if _s_start_ns else 0
            _sampler_ms_ns = round((_s_end_ns - _s_start_ns) * 1000, 1) if _s_start_ns and _s_end_ns else 0
            _t9_ns = _stages_ns.get("t9_modal_return", time.time())
            _sampler_to_t9_ns = round((_t9_ns - _s_end_ns) * 1000, 1) if _s_end_ns and _t9_ns else 0
            print(f"[timing] restore_total_ms={_rt3.get('restore_total_ms', 0)}")
            print(f"[timing] restore_end_to_prompt_start_ms={_restore_end_to_prompt_ns}")
            print(f"[timing] prompt_start_to_sampler_start_ms={_prompt_to_sampler_ns}")
            print(f"[timing] sampler_ms={_sampler_ms_ns}")
            print(f"[timing] sampler_end_to_outputs_collected_ms={_sampler_to_t9_ns}")
            print(f"[timing] total_input_execution_ms={total_ms}")
            print(f"[timing] prompt_async_preload=0")
            print(f"[timing] prompt_preload_workers=0")
            print(f"[timing] preload_paths_count=0")
            print(f"[timing] preload_cache_hits=0")
            print(f"[timing] preload_waits=0")
            print(f"[timing] duplicate_loads_prevented=0")

            _s = time.time()
            print(
                f"[comfyapp.profile] stage=remote_total backend=in_process duration_ms={total_ms} "
                f"output_images={len(result.get('images', []))} "
                f"output_videos={len(result.get('videos', []))}"
            )
            print(server_trace.log_line())
            _t8b_profile_print_ms = round((time.time() - _s) * 1000, 1)

            _s = time.time()
            trace_summary = server_trace.summary()
            self._enrich_trace_with_restore_timing(trace_summary)
            # Merge derived timing from the non-streaming path.
            # Fields that depend on restore dict or total_started (not in trace):
            _prompt_start_ts = _stages_ns.get("t3d_prompt_start", total_started)
            trace_summary["derived_ms"]["restore_total_ms"] = _rt3.get("restore_total_ms", 0)
            # restore_end_to_prompt_start_ms: only when real restore end exists (cold container)
            if _rt3.get("restore_end_unix_s") is not None:
                trace_summary["derived_ms"]["restore_end_to_prompt_start_ms"] = round((_prompt_start_ts - _rt3["restore_end_unix_s"]) * 1000, 1)
            # modal_entry_to_prompt_start_ms: always computed from trace entry
            if _t3_ns is not None and _prompt_start_ts is not None:
                trace_summary["derived_ms"]["modal_entry_to_prompt_start_ms"] = round((_prompt_start_ts - _t3_ns) * 1000, 1)
            trace_summary["derived_ms"]["total_input_execution_ms"] = total_ms
            result["trace"] = trace_summary
            if isinstance(_scheduler_trace_ns, dict):
                result["scheduler_trace"] = dict(_scheduler_trace_ns)

            # P3 — end-to-end timing: stitch browser t0 to restore phases
            _rt2 = getattr(self, "_last_restore_timing", None)
            if isinstance(_rt2, dict):
                _t0 = trace_summary.get("t0") or 0.0
                _rs = _rt2.get("restore_start_unix_s") or 0.0
                _re = _rt2.get("restore_end_unix_s") or 0.0
                if _t0 > 0 and _rs > 0:
                    _rt2["request_received_to_restore_start_ms"] = round((_rs - _t0) * 1000, 1)
                if _t0 > 0 and _re > 0:
                    _rt2["request_received_to_restore_end_ms"] = round((_re - _t0) * 1000, 1)
                # request_received_to_first_sampler_ms / images_collected_ms
                # come from trace stages (already ms from t0)
                _stages = trace_summary.get("stages", {})
                _t6 = _stages.get("t6_sampler_start")
                if _t6 is not None:
                    _rt2["request_received_to_first_sampler_ms"] = _t6
                _t8 = _stages.get("t8_image_written")
                if _t8 is not None:
                    _rt2["request_received_to_images_collected_ms"] = _t8
                # modal_restore_gap_ms = time from Modal's "Restoring Function"
                # log to first user code.  Can't measure from within the
                # container; benchmark tool fills this from Modal infrastructure
                # logs by comparing "Restoring Function" timestamp to
                # restore_start_unix_s.
                _rt2["modal_restore_gap_ms"] = 0.0

            result["_restore_timing"] = dict(_rt2) if _rt2 else {}
            _t8b_enrich_ms = round((time.time() - _s) * 1000, 1)

            _s = time.time()
            _gpu_stats_raw = {}
            try:
                import comfy.model_management as _mm
                _gpu_stats_raw = dict(getattr(_mm, '_gpu_cache_eq_stats', {}))
            except Exception:
                pass
            result["_cache_diagnostics"] = {
                "cpu_hits": dict(getattr(self, "_cpu_cache_hits", {})),
                "cpu_misses": dict(getattr(self, "_cpu_cache_misses", {})),
                "gpu_eq": _gpu_stats_raw,
                "clip_cache_hits": getattr(self, "_clip_cache_hits", 0),
                "clip_cache_misses": getattr(self, "_clip_cache_misses", 0),
            }
            # Executor profiling data
            import execution as _exec_mod
            _exec_prof_raw = getattr(_exec_mod, '_comfy_modal_exec_prof', None)
            if _exec_prof_raw and _exec_prof_raw.get("nodes"):
                _nodes = _exec_prof_raw.get("nodes", {})
                _total_node_ms = round(sum(n["ms"] for n in _nodes.values()), 2)
                _fcs = _exec_prof_raw.get("_first_call_start")
                _lce = _exec_prof_raw.get("_last_call_end")
                _execute_wall_ms = round((_lce - _fcs) * 1000, 2) if _fcs and _lce else 0.0
                _exec_residual_ms = round(max(0.0, _execute_wall_ms - _total_node_ms), 2)
                _flat = {f"node_{k}": round(v["ms"], 2) for k, v in _nodes.items()}
                _flat["total_node_ms"] = _total_node_ms
                _flat["execute_wall_ms"] = _execute_wall_ms
                _flat["executor_residual_ms"] = _exec_residual_ms
                _flat["node_counts"] = {k: v["count"] for k, v in _nodes.items()}
                result["_exec_profile"] = _flat
                print(f"[comfyapp] exec_profile: nodes={dict(_flat)}")
                # Reset for next prompt (mutate in-place since patched function references this dict)
                _exec_prof_raw.clear()
                _exec_prof_raw["nodes"] = {}
                _exec_prof_raw["_first_call_start"] = None
                _exec_prof_raw["_last_call_end"] = None
                _exec_prof_raw["_call_count"] = 0
            # Sampler profiling data
            import comfy.samplers as _samplers_mod
            _sampler_prof = getattr(_samplers_mod, '_comfy_modal_sampler_prof', None)
            if _sampler_prof and _sampler_prof.get("total_ms"):
                result["_sampler_profile"] = dict(_sampler_prof)
                print(f"[comfyapp] sampler_profile: {_sampler_prof}")
                _sampler_prof.clear()
            # ModelPatcher trace data
            _mp_trace_data = getattr(_samplers_mod, '_comfy_modal_mp_trace', None)
            if _mp_trace_data:
                result["_modelpatcher_trace"] = list(_mp_trace_data)
                _mp_trace_data.clear()
            # Guider profiling data
            _guider_prof = getattr(_samplers_mod, '_comfy_modal_guider_prof', None)
            if _guider_prof and _guider_prof.get("segments"):
                result["_guider_profile"] = dict(_guider_prof["segments"])
                _seg = _guider_prof["segments"]
                print(f"[comfyapp] guider_profile: {dict(_seg)}")
                _guider_prof["segments"].clear()
            # Deep profiling data
            import comfy as _comfy_mod
            _deep_prof = getattr(_comfy_mod, '_comfy_modal_deep_prof', None)
            if _deep_prof:
                result["_deep_profile"] = dict(_deep_prof)
                _dp_clean = {}
                for k, v in _deep_prof.items():
                    if isinstance(v, dict):
                        _dp_clean[k] = {kk: round(vv, 2) if isinstance(vv, (int, float)) else vv for kk, vv in v.items()}
                    elif isinstance(v, list):
                        _dp_clean[k] = [{kk: round(vv, 2) if isinstance(vv, (int, float)) else vv for kk, vv in c.items()} for c in v]
                    else:
                        _dp_clean[k] = round(v, 2) if isinstance(v, (int, float)) else v
                print(f"[comfyapp] deep_profile: {_dp_clean}")
                _deep_prof.clear()
            print(f"[comfyapp] cache_diagnostics: cpu_hits={result['_cache_diagnostics']['cpu_hits']} "
                  f"cpu_misses={result['_cache_diagnostics']['cpu_misses']} "
                  f"gpu_eq_calls={result['_cache_diagnostics']['gpu_eq'].get('calls', '?')} "
                  f"class_hits={result['_cache_diagnostics']['gpu_eq'].get('class_hits', '?')} "
                  f"misses={result['_cache_diagnostics']['gpu_eq'].get('misses', '?')} "
                  f"clip_hits={result['_cache_diagnostics']['clip_cache_hits']} "
                   f"clip_misses={result['_cache_diagnostics']['clip_cache_misses']}")
            _t8b_diag_print_ms = round((time.time() - _s) * 1000, 1)
            # Return payload logging
            _payload_images = result.get("images", [])
            _payload_videos = result.get("videos", [])
            _payload_image_count = len(_payload_images)
            _payload_video_count = len(_payload_videos)
            _payload_b64_bytes = sum(len(img.get("data", "")) for img in _payload_images)
            _payload_b64_bytes += sum(len(vid.get("data", "")) for vid in _payload_videos)
            _payload_json_approx = _payload_b64_bytes + len(json.dumps(result, separators=(",", ":")))
            print(f"[comfyapp] return_payload: images={_payload_image_count} videos={_payload_video_count} "
                  f"b64_bytes={_payload_b64_bytes} approx_json_bytes={_payload_json_approx}")
            result["_return_payload_info"] = {
                "image_count": _payload_image_count,
                "video_count": _payload_video_count,
                "b64_bytes": _payload_b64_bytes,
                "approx_json_bytes": _payload_json_approx,
            }
            _t8b_total_ms = round((time.time() - _t8b_t0) * 1000, 1)
            _t8b_unknown_ms = round(_t8b_total_ms - _t8b_save_stack_ms - _t8b_diag_ms - _t8b_profile_print_ms - _t8b_enrich_ms - _t8b_diag_print_ms, 1)
            _graph_validate_ms = _graph_validate_ms or 0.0
            print(f"[comfyapp] t8b_breakdown: total={_t8b_total_ms}ms "
                  f"save_stack={_t8b_save_stack_ms}ms "
                  f"diagnostics={_t8b_diag_ms}ms "
                  f"profile_print={_t8b_profile_print_ms}ms "
                  f"enrich={_t8b_enrich_ms}ms "
                  f"diag_print={_t8b_diag_print_ms}ms "
                  f"graph_validate={_graph_validate_ms}ms "
                  f"unknown={_t8b_unknown_ms}ms")
            result["_t8b_breakdown"] = {
                "t8b_total_ms": _t8b_total_ms,
                "t8b_save_stack_ms": _t8b_save_stack_ms,
                "t8b_diagnostics_ms": _t8b_diag_ms,
                "t8b_profile_print_ms": _t8b_profile_print_ms,
                "t8b_enrich_ms": _t8b_enrich_ms,
                "t8b_diag_print_ms": _t8b_diag_print_ms,
                "graph_validate_ms": _graph_validate_ms,
                "t8b_unknown_ms": _t8b_unknown_ms,
            }

            # ── Return mode filtering (after full payload logging) ──────
            _return_mode = _resolve_return_mode()
            result = _apply_return_mode(result, _return_mode, _payload_image_count, _payload_video_count)
            # Cache size before real prompt
            try:
                import nodes
                _te_cls = nodes.NODE_CLASS_MAPPINGS.get("CLIPTextEncode")
                if _te_cls and hasattr(_te_cls, '_clip_text_cache'):
                    result["_return_payload_info"]["clip_cache_size_before_prompt"] = len(_te_cls._clip_text_cache)
            except Exception:
                pass
            _rt_summary_i = _rt2 or {}
            _warmup_prof_i = _rt_summary_i.get("warmup_profile") or {}
            _known_good_val_i = result.get("_known_good_marked", False)
            _cn_created_count_i = _rt_summary_i.get("custom_nodes_created", 0)
            _prompt_hash_i = ""
            for _v in (workflow or {}).values():
                if isinstance(_v, dict) and _v.get("prompt_id"):
                    _prompt_hash_i = str(_v.get("prompt_id", ""))[:8]
                    break
            _plv_i = bool(
                (modal_options or {}).get("local_preflight_validated")
                or (modal_options or {}).get("preflight_validated")
            )
            _summary_inproc = make_request_pipeline_summary(
                request_id=_prompt_hash_i,
                mode="in_process",
                stream=False,
                workflow_hash=_warmup_prof_i.get("_workflow_hash", ""),
                model_stack=_warmup_prof_i.get("_current_workflow_stack", {}),
                local_preflight_validated=_plv_i,
                remote_preflight_validated=True,
                custom_node_sync_skipped=_cn_created_count_i == 0,
                custom_node_sync_skip_reason="memoized" if _cn_created_count_i == 0 else "",
                active_profile_result=_rt_summary_i.get("warmup_profile_source", "none"),
                active_profile_expired=_rt_summary_i.get("preload_skip_reason") == "active_profile_expired",
                preload_skip_reason=_rt_summary_i.get("preload_skip_reason", ""),
                dependency_check_ran=True,
                dependency_manifest_cache_hit=True,
                execution_started=True,
                execution_success=result.get("images") is not None,
                known_good_marked=_known_good_val_i,
                known_good_mark_result="marked" if _known_good_val_i else "",
            )
            print(f"[comfyapp] request_pipeline_summary {_summary_inproc}")
            return result

        # ── Subprocess backend: HTTP-based submission ──
        import base64
        import httpx
        from pathlib import Path

        total_started = time.time()
        input_count = 0
        input_bytes = 0

        if input_images:
            input_started = time.time()
            input_count, input_bytes = _materialize_input_images(input_images)
            input_decode_ms = round((time.time() - input_started) * 1000, 1)
            print(
                f"[comfyapp.profile] stage=input_decode_write duration_ms={input_decode_ms} "
                f"count={input_count} bytes={input_bytes}"
            )

        client_id = str(uuid.uuid4())

        requested_stack = extract_requested_model_stack(workflow)
        selected_profile = dict((getattr(self, "_last_restore_timing", None) or {}).get("warmup_profile") or {})
        if not selected_profile:
            selected_profile = self._snapshot_preload_profile() or {}
        warmup_match = warmup_profile_matches_workflow(selected_profile, requested_stack)
        print(
            f"[comfyapp.profile] WARMUP_PROFILE_MATCH={'true' if warmup_match else 'false'} "
            f"profile_source={selected_profile.get('_source', 'none')} "
            f"profile_token={selected_profile.get('_profile_token', '')} workflow_hash={selected_profile.get('_workflow_hash', '')} "
            f"requested={requested_stack} profile={selected_profile}"
        )

        try:
            submit_started = time.time()
            r = self._http_client.post(
                "/prompt",
                json={"prompt": workflow, "client_id": client_id},
            )
            r.raise_for_status()
            queued = r.json()
            submit_ms = round((time.time() - submit_started) * 1000, 1)
            print(f"[comfyapp.profile] stage=prompt_submit duration_ms={submit_ms}")
        except httpx.HTTPStatusError as e:
            # Read the response body for validation error details
            error_body = ""
            try:
                error_data = e.response.json()
                # Extract meaningful error info from ComfyUI's response
                node_errors = error_data.get("node_errors", {})
                if node_errors:
                    msgs = []
                    for node_id, err_info in node_errors.items():
                        class_type = err_info.get("class_type", f"Node {node_id}")
                        for err in err_info.get("errors", []):
                            msgs.append(f"{class_type}: {err.get('message', 'unknown error')}")
                    if msgs:
                        raise RuntimeError(f"Workflow validation failed: {'; '.join(msgs)}") from e
                # Fallback: use the message field
                msg = error_data.get("message", "") or error_data.get("error", "")
                if msg:
                    raise RuntimeError(f"Workflow validation failed: {msg}") from e
            except (json.JSONDecodeError, RuntimeError):
                if isinstance(sys.exc_info()[1], RuntimeError):
                    raise
            raise RuntimeError(f"ComfyUI rejected the prompt (HTTP {e.response.status_code}): {e.response.text[:500]}") from e

        prompt_id = queued["prompt_id"]
        profile: dict = {}
        result = self._poll_until_done(prompt_id, client_id, profile)
        _payload_images = result.get("images", [])
        _payload_videos = result.get("videos", [])
        _payload_image_count = len(_payload_images)
        _payload_video_count = len(_payload_videos)
        _payload_b64_bytes = sum(len(img.get("data", "")) for img in _payload_images)
        _payload_b64_bytes += sum(len(vid.get("data", "")) for vid in _payload_videos)
        result["_return_payload_info"] = {
            "image_count": _payload_image_count,
            "video_count": _payload_video_count,
            "b64_bytes": _payload_b64_bytes,
        }
        result = _apply_return_mode(result, _resolve_return_mode(), _payload_image_count, _payload_video_count)

        # Persist the model stack for auto-warmup on next restart
        if requested_stack and any(requested_stack.values()):
            self._save_last_warmup_workflow(workflow)
            self._save_last_model_stack(requested_stack)

        total_ms = round((time.time() - total_started) * 1000, 1)
        print(
            f"[comfyapp.profile] stage=remote_total backend=subprocess prompt_id={prompt_id[:8]} duration_ms={total_ms} "
            f"output_images={profile.get('output_images', 0)} output_videos={profile.get('output_videos', 0)} "
            f"output_bytes={profile.get('output_bytes', 0)}"
        )
        server_trace.mark("t9_modal_return")
        print(server_trace.log_line())
        trace_summary = server_trace.summary()
        self._enrich_trace_with_restore_timing(trace_summary)
        # Derive what we can for the subprocess path
        _rt3 = getattr(self, "_last_restore_timing", None) or {}
        _stages_sp = server_trace._t
        _prompt_start_ts_sp = _stages_sp.get("t3d_prompt_start", total_started)
        trace_summary["derived_ms"]["restore_total_ms"] = _rt3.get("restore_total_ms", 0)
        _t3_entry_sp = _stages_sp.get("t3_modal_entry", total_started)
        # restore_end_to_prompt_start_ms: only when real restore end exists
        if _rt3.get("restore_end_unix_s") is not None:
            trace_summary["derived_ms"]["restore_end_to_prompt_start_ms"] = round((_prompt_start_ts_sp - _rt3["restore_end_unix_s"]) * 1000, 1)
        # modal_entry_to_prompt_start_ms: always computed
        if _t3_entry_sp is not None and _prompt_start_ts_sp is not None:
            trace_summary["derived_ms"]["modal_entry_to_prompt_start_ms"] = round((_prompt_start_ts_sp - _t3_entry_sp) * 1000, 1)
        trace_summary["derived_ms"]["total_input_execution_ms"] = total_ms
        result["trace"] = trace_summary
        result["_restore_timing"] = dict(getattr(self, "_last_restore_timing", {}))
        # Attach __eq__ hit/miss counters to restore_timing for diagnostics
        if getattr(self, '_comfy_modal_eq', None) is not None:
            c = self._comfy_modal_eq
            result["_restore_timing"]["eq_hits"] = c.get('class_size_hit', 0) + c.get('model_type_hit', 0)
            result["_restore_timing"]["eq_misses"] = c.get('class_size_miss', 0) + c.get('device_miss', 0)
            result["_restore_timing"]["eq_identity"] = c.get('identity_hit', 0)
            if self._comfy_modal_eq_samples:
                result["_restore_timing"]["eq_samples"] = '; '.join(self._comfy_modal_eq_samples[:5])
                self._comfy_modal_eq_samples.clear()
            print(f"[comfyapp] eq: hits={result['_restore_timing']['eq_hits']} misses={result['_restore_timing']['eq_misses']} {dict(c)}")
        _prompt_hash = ""
        for _v in (workflow or {}).values():
            if isinstance(_v, dict) and _v.get("prompt_id"):
                _prompt_hash = str(_v.get("prompt_id", ""))[:8]
                break
        _plv = bool(
            (modal_options or {}).get("local_preflight_validated")
            or (modal_options or {}).get("preflight_validated")
        )
        _rt_summary = result.get("_restore_timing", {})
        _warmup_prof = _rt_summary.get("warmup_profile") or {}
        _known_good_val = result.get("_known_good_marked", False)
        _cn_created_count = _rt_summary.get("custom_nodes_created", 0)
        _summary = make_request_pipeline_summary(
            request_id=_prompt_hash,
            mode="subprocess",
            stream=False,
            workflow_hash=_warmup_prof.get("_workflow_hash", ""),
            model_stack=_warmup_prof.get("_current_workflow_stack", {}),
            local_preflight_validated=_plv,
            remote_preflight_validated=True,
            custom_node_sync_skipped=_cn_created_count == 0,
            custom_node_sync_skip_reason="memoized" if _cn_created_count == 0 else "",
            active_profile_result=_rt_summary.get("warmup_profile_source", "none"),
            active_profile_expired=_rt_summary.get("preload_skip_reason") == "active_profile_expired",
            preload_skip_reason=_rt_summary.get("preload_skip_reason", ""),
            dependency_check_ran=True,
            dependency_manifest_cache_hit=True,
            execution_started=True,
            execution_success=result.get("images") is not None,
            known_good_marked=_known_good_val,
            known_good_mark_result="marked" if _known_good_val else "",
        )
        print(f"[comfyapp] request_pipeline_summary {_summary}")
        return result

    @modal.method(is_generator=True)
    def run_prompt_stream(
        self,
        workflow: dict,
        input_images: dict | None = None,
        trace: dict | None = None,
        modal_options: dict | None = None,
    ):
        """Execute workflow with streaming progress events.

        Yields dicts with these types:
          ``{"type": "status", "message": "..."}`` — phase status (restore, startup).
          ``{"type": "progress", "event": "...", "data": {...}}`` — ComfyUI execution
          events (execution_start, executing, progress, execution_error).
          ``{"type": "result", "data": {...}}`` — final result dict.
          ``{"type": "error", "message": "..."}`` — fatal error.

        The caller iterates via ``.remote_gen()`` and forwards progress events
        to the ComfyUI frontend in real-time.
        """
        import queue as _qm
        import threading

        # Mirror run_prompt() trace setup so streaming path preserves
        # the same timing/restore metadata as the non-streaming path.
        t0 = coerce_t0_from_browser(trace or {})
        prompt_id_hint = ""
        if isinstance(trace, dict):
            prompt_id_hint = str(trace.get("prompt_id") or "")
        if not prompt_id_hint and isinstance(workflow, dict):
            for node in workflow.values():
                if isinstance(node, dict) and "prompt_id" in node:
                    prompt_id_hint = str(node["prompt_id"])
        server_trace = Trace(prompt_id=prompt_id_hint, t0=t0)
        server_trace.update(trace)
        server_trace.mark("t3_modal_entry")
        print(f"[predispatch] phase=modal_entry t={time.time()}")

        _prog_q = _qm.Queue()
        self._prog_queue = _prog_q

        try:
            # ── Check for scheduler test mode ──
            _scheduler_config = (modal_options or {}).get("comfymodal_scheduler_test")
            _is_scheduler_test = isinstance(_scheduler_config, dict) and _scheduler_config.get("enabled")

            if _is_scheduler_test:
                print(f"[scheduler_test] config={json.dumps(_scheduler_config, default=str)}")
                self._preflight_already_ran = False

                try:
                    self._start_scheduler_test(workflow, _scheduler_config)
                except RuntimeError as _dep_err:
                    import traceback as _tb
                    _tb.print_exc()
                    yield {"type": "error", "message": str(_dep_err)}
                    return

                try:
                    _scheduler_trace = self._scheduler_wait_and_finalize()
                except RuntimeError as _dep_err:
                    import traceback as _tb
                    _tb.print_exc()
                    yield {"type": "error", "message": str(_dep_err)}
                    return

                self._preflight_already_ran = True
                _preload_info = {"enabled": False, "workers": 0, "deduped_paths": [], "cache_hit": [], "submitted": [], "duplicate_skipped": 0}
                _actual_load_info = {"enabled": False, "submitted": [], "skipped_unet": True, "futures": {}}
            else:
                # ── Shared custom-node sync and dependency policy ──
                # Runs before prompt preload, actual_load, and execution.
                # Dependency failures yield a clear fatal stream event.
                self._preflight_already_ran = False
                try:
                    self._handle_custom_node_sync_and_dependency_policy(workflow, stream=True)
                    self._preflight_already_ran = True
                except RuntimeError as _dep_err:
                    import traceback as _tb
                    _tb.print_exc()
                    yield {"type": "error", "message": str(_dep_err)}
                    return

                # ── Prompt-time async preload (after dependency policy) ──
                _preload_info: dict = {"enabled": False, "workers": 0, "deduped_paths": [], "cache_hit": [], "submitted": [], "duplicate_skipped": 0}
                if PROMPT_ASYNC_PRELOAD:
                    _preload_info = self._prompt_async_preload(workflow)

                # ── Prompt-time actual loader futures (after dependency policy) ──
                _actual_load_info: dict = self._prompt_async_actual_load(workflow)
                _scheduler_trace = None

            # ── Ensure backend is initialised before _execute_in_process ──
            # The in-process backend (and its self._event_loop) is created
            # lazily in _start_backend().  When snapshot_mode is "none" or
            # "minimal" startup() defers init to restore(), but a streaming
            # prompt can still arrive before restore() has run.  Without
            # this guard self._event_loop is None and
            # `_execute_in_process()` raises "'NoneType' object has no
            # attribute 'run_until_complete'" on its first
            # run_until_complete() call.  Lazy-start the backend here.
            _in_proc = self._select_backend() == "in_process"
            if _in_proc and self._event_loop is None:
                yield {"type": "status", "message": "Initializing backend", "phase": "backend_init"}
                try:
                    self._start_backend()
                except Exception as _init_exc:
                    import traceback as _tb
                    _tb.print_exc()
                    yield {"type": "error", "message": f"Failed to start backend: {_init_exc}"}
                    return
                yield {"type": "status", "message": "Backend ready", "phase": "backend_ready"}

            # ── Yield human-readable startup phases (no percentages) ─────
            _rt = getattr(self, "_last_restore_timing", None) or {}
            if _rt.get("restore_total_ms"):
                yield {"type": "status", "message": "Restoring container", "phase": "restore"}
            if _rt.get("custom_nodes_sync_ms"):
                yield {"type": "status", "message": "Loading custom nodes", "phase": "custom_nodes"}
            if _rt.get("gpu_state_ms") or _rt.get("cuda_warmup_ms") or _rt.get("sage_runtime_ms"):
                yield {"type": "status", "message": "Reconnecting GPU", "phase": "gpu"}
            if _rt.get("warmup_preload_ms") or _rt.get("warmup_direct_total_ms"):
                yield {"type": "status", "message": "Warming models", "phase": "warmup"}
            yield {"type": "status", "message": "Starting execution", "phase": "execution"}

            # ── Run execution in a background thread ─────────────────────
            # _execute_in_process is synchronous and blocking.  Running it
            # in a daemon thread lets the main generator yield progress
            # events from the _on_sync callback as they fire.
            _result: list[dict] = []
            _error: list[Exception] = []

            def _exec() -> None:
                try:
                    _t_exec_start = time.time()
                    _r = self._execute_in_process(workflow, input_images or {}, trace=server_trace, modal_options=modal_options)
                    _t_exec_end = time.time()
                    server_trace.mark("t9_modal_return")
                    trace_summary = server_trace.summary()
                    self._enrich_trace_with_restore_timing(trace_summary)
                    # Merge derived timing from the streaming path
                    _rt2 = getattr(self, "_last_restore_timing", None)
                    _stages = trace_summary.get("stages", {})
                    _t3 = _stages.get("t3_modal_entry", _t_exec_start)
                    _prompt_start_ts = _stages.get("t3d_prompt_start", _t_exec_start)
                    _s_start = _stages.get("t6_sampler_start", 0)
                    _s_end = _stages.get("t6_sampler_end", 0)
                    _restore_ms = (_rt2 or {}).get("restore_total_ms", 0)
                    _restore_end_to_prompt = round((_prompt_start_ts - _t3) * 1000, 1)
                    _prompt_to_sampler = round((_s_start - _t_exec_start) * 1000, 1) if _s_start else 0
                    _sampler_ms = round((_s_end - _s_start) * 1000, 1) if _s_start and _s_end else 0
                    trace_summary["derived_ms"]["restore_total_ms"] = (_rt2 or {}).get("restore_total_ms", 0)
                    # restore_end_to_prompt_start_ms: only when real restore end exists
                    if (_rt2 or {}).get("restore_end_unix_s") is not None:
                        trace_summary["derived_ms"]["restore_end_to_prompt_start_ms"] = round((_prompt_start_ts - _rt2["restore_end_unix_s"]) * 1000, 1)
                    # modal_entry_to_prompt_start_ms: always computed
                    if _t3 is not None and _prompt_start_ts is not None:
                        trace_summary["derived_ms"]["modal_entry_to_prompt_start_ms"] = round((_prompt_start_ts - _t3) * 1000, 1)
                    trace_summary["derived_ms"]["total_input_execution_ms"] = round((_t_exec_end - _t_exec_start) * 1000, 1)
                    _r["trace"] = trace_summary
                    if isinstance(_scheduler_trace, dict):
                        _r["scheduler_trace"] = dict(_scheduler_trace)
                    _r["_restore_timing"] = dict(_rt2) if _rt2 else {}
                    _sampler_to_end = round((_t_exec_end - _s_end) * 1000, 1) if _s_end else 0
                    _total_exec = round((_t_exec_end - _t_exec_start) * 1000, 1)
                    _inflight = getattr(self, "_in_flight_preloads", {})
                    print(f"[timing] restore_total_ms={_restore_ms}")
                    print(f"[timing] restore_end_to_prompt_start_ms={_restore_end_to_prompt}")
                    print(f"[timing] prompt_start_to_sampler_start_ms={_prompt_to_sampler}")
                    print(f"[timing] sampler_ms={_sampler_ms}")
                    print(f"[timing] sampler_end_to_outputs_collected_ms={_sampler_to_end}")
                    print(f"[timing] total_input_execution_ms={_total_exec}")
                    print(f"[timing] prompt_async_preload={'1' if _preload_info.get('enabled') else '0'}")
                    print(f"[timing] prompt_preload_workers={_preload_info.get('workers', 0)}")
                    print(f"[timing] preload_paths_count={len(_preload_info.get('deduped_paths', []))}")
                    print(f"[timing] preload_cache_hits={len(_preload_info.get('cache_hit', []))}")
                    print(f"[timing] preload_waits={len(_preload_info.get('submitted', [])) - len(_inflight)}")
                    print(f"[timing] duplicate_loads_prevented={_preload_info.get('duplicate_skipped', 0)}")
                    _al_hits = getattr(self, '_actual_load_hits', 0)
                    _al_waits = getattr(self, '_actual_load_waits', 0)
                    _al_dups = getattr(self, '_actual_load_duplicates_prevented', 0)
                    print(f"[timing] actual_load_enabled={'1' if _actual_load_info.get('enabled') else '0'}")
                    print(f"[timing] actual_load_unet_enabled={'1' if PROMPT_ASYNC_ACTUAL_LOAD_UNET else '0'}")
                    print(f"[timing] loader_future_hits={_al_hits}")
                    print(f"[timing] loader_future_waits={_al_waits}")
                    print(f"[timing] duplicate_loads_prevented={_al_dups}")
                    _plv = bool(
                        (modal_options or {}).get("local_preflight_validated")
                        or (modal_options or {}).get("preflight_validated")
                    )
                    _rt_summary = _rt2 or {}
                    _warmup_prof = _rt_summary.get("warmup_profile") or {}
                    _known_good_val = _r.get("_known_good_marked", False)
                    _cn_created_count = _rt_summary.get("custom_nodes_created", 0)
                    _summary = make_request_pipeline_summary(
                        request_id=prompt_id_hint[:8] if prompt_id_hint else "",
                        mode="in_process",
                        stream=True,
                        workflow_hash=_warmup_prof.get("_workflow_hash", ""),
                        model_stack=_warmup_prof.get("_current_workflow_stack", {}),
                        local_preflight_validated=_plv,
                        remote_preflight_validated=True,
                        custom_node_sync_skipped=_cn_created_count == 0,
                        custom_node_sync_skip_reason="memoized" if _cn_created_count == 0 else "",
                        active_profile_result=_rt_summary.get("warmup_profile_source", "none"),
                        active_profile_expired=_rt_summary.get("preload_skip_reason") == "active_profile_expired",
                        preload_skip_reason=_rt_summary.get("preload_skip_reason", ""),
                        dependency_check_ran=True,
                        dependency_manifest_cache_hit=True,
                        execution_started=True,
                        execution_success=True,
                        known_good_marked=_known_good_val,
                        known_good_mark_result="marked" if _known_good_val else "",
                        prompt_preload_result="started" if _preload_info.get("enabled") else "",
                        actual_load_result="started" if _actual_load_info.get("enabled") else "",
                    )
                    print(f"[comfyapp] request_pipeline_summary {_summary}")
                    _result.append(_r)
                except Exception as _exc:
                    _error.append(_exc)
                    import traceback as _tb
                    _tb.print_exc()
                finally:
                    _prog_q.put(("__done__", None))

            _t = threading.Thread(target=_exec, daemon=True)
            _t.start()

            # ── Drain progress events until execution finishes ───────────
            while _t.is_alive():
                try:
                    _ev, _data = _prog_q.get(timeout=0.2)
                    if _ev == "__done__":
                        break
                    yield {"type": "progress", "event": _ev, "data": _data}
                except _qm.Empty:
                    pass

            # Drain any events that arrived between the last get and thread exit
            while True:
                try:
                    _ev, _data = _prog_q.get_nowait()
                    if _ev != "__done__":
                        yield {"type": "progress", "event": _ev, "data": _data}
                except _qm.Empty:
                    break

            if _error:
                yield {"type": "error", "message": str(_error[0])}
                return

            yield {"type": "result", "data": _result[0]}

        finally:
            self._prog_queue = None

    def _enrich_trace_with_restore_timing(self, trace_summary: dict) -> None:
        """Merge per-phase restore timing into the trace summary (mutates in-place)."""
        restore_data = getattr(self, "_last_restore_timing", None)
        if restore_data:
            trace_summary["restore"] = dict(restore_data)

    def _poll_until_done(self, prompt_id: str, client_id: str, profile: dict | None = None) -> dict:
        delay = 0.25
        elapsed = 0.0
        poll_count = 0
        poll_started = time.time()
        while elapsed < 3600:
            poll_count += 1
            r = self._http_client.get(f"/history/{prompt_id}")
            history = r.json()
            if prompt_id in history:
                outputs = history[prompt_id].get("outputs", {})
                print(f"[comfyapp] prompt {prompt_id} finished in {elapsed:.3f}s")
                poll_ms = round((time.time() - poll_started) * 1000, 1)
                sleep_ms = round(elapsed * 1000, 1)
                active_poll_ms = round(max(poll_ms - sleep_ms, 0.0), 1)
                print(
                    f"[comfyapp.profile] stage=poll prompt_id={prompt_id[:8]} duration_ms={poll_ms} "
                    f"poll_count={poll_count} sleep_ms={sleep_ms} active_poll_ms={active_poll_ms}"
                )
                return self._collect_outputs(outputs, profile)
            time.sleep(delay)
            elapsed += delay
        raise TimeoutError(f"Prompt {prompt_id} timed out")

    def _collect_outputs(self, outputs: dict, profile: dict | None = None) -> dict:
        import base64
        import urllib.parse

        collect_started = time.time()
        images = []
        videos = []
        total_bytes = 0
        per_node_outputs: dict[str, dict[str, list[dict]]] = {}

        for node_id, node_output in outputs.items():
            raw_animated = node_output.get("animated", False)
            animated_val = raw_animated if isinstance(raw_animated, bool) else (raw_animated[0] if raw_animated else False)

            for output_key, img in _iter_image_entries(node_output):
                filename = img.get("filename", "")
                params = urllib.parse.urlencode({
                    "filename": filename,
                    "subfolder": img.get("subfolder", ""),
                    "type": img.get("type", "output"),
                })
                r = self._http_client.get(f"/view?{params}")
                total_bytes += len(r.content)
                data = base64.b64encode(r.content).decode()
                entry = {"filename": filename, "data": data, "node_id": node_id}

                if output_key == "gifs":
                    is_animated = True
                else:
                    is_animated = animated_val

                if is_animated:
                    videos.append(entry)
                else:
                    images.append(entry)

                per_node_outputs.setdefault(node_id, {}).setdefault(output_key, []).append(entry)

        collect_ms = round((time.time() - collect_started) * 1000, 1)
        print(
            f"[comfyapp.profile] stage=output_collect duration_ms={collect_ms} "
            f"images={len(images)} videos={len(videos)} bytes={total_bytes}"
        )
        print(f"[comfyapp] sanity (subprocess): "
              f"sampler_started={'yes' if images or videos else 'no'} "
              f"output_files={len(images) + len(videos)} "
              f"filenames={[e['filename'] for e in images + videos]}")
        if profile is not None:
            profile["output_images"] = len(images)
            profile["output_videos"] = len(videos)
            profile["output_bytes"] = total_bytes
        return {"images": images, "videos": videos, "outputs": per_node_outputs}

    def _record_runtime_state(self):
        self._models_state = model_volume_state(MODELS_PATH)
        self._custom_nodes_state = custom_node_volume_state(CUSTOM_NODES_PATH)

    def _runtime_state_payload(self) -> dict:
        current_models = model_volume_state(MODELS_PATH)
        current_nodes = custom_node_volume_state(CUSTOM_NODES_PATH)
        models_changed = current_models != getattr(self, "_models_state", None)
        custom_nodes_changed = current_nodes != getattr(self, "_custom_nodes_state", None)
        stale_reasons = []
        if models_changed:
            stale_reasons.append("models changed")
        if custom_nodes_changed:
            stale_reasons.append("custom nodes changed")
        return {
            "stale": bool(stale_reasons),
            "stale_reasons": stale_reasons,
            "models_changed": models_changed,
            "custom_nodes_changed": custom_nodes_changed,
        }

    @modal.method()
    def resync_runtime(self, scope: str = "all"):
        """Explicit in-container resync: reload volumes, sync custom nodes,
        reinstall changed requirements, and restart ComfyUI in place."""
        if getattr(self, "_resync_in_progress", False):
            return {"status": "conflict", "message": "resync already in progress"}
        self._resync_in_progress = True
        try:
            started = time.time()
            print(f"[comfyapp] resync_runtime scope={scope} starting")

            if scope in {"models", "all"}:
                vol.reload()
            summary: dict = {"scope": scope}
            if scope in {"custom_nodes", "all"}:
                node_summary, _ = self._sync_custom_nodes_from_volume()
                summary["custom_nodes"] = node_summary
                summary["requirements"] = self._install_custom_node_requirements()

            self._record_runtime_state()
            self._restart_comfy()

            summary["runtime_state"] = self._runtime_state_payload()
            summary["duration_s"] = round(time.time() - started, 3)
            print(f"[comfyapp] resync_runtime scope={scope} took {summary['duration_s']:.3f}s")
            return {"status": "ok", **summary}
        finally:
            self._resync_in_progress = False

    @modal.method()
    def runtime_state(self) -> dict:
        """Return stale-runtime info by comparing current volume state
        against the last recorded in-memory state."""
        return self._runtime_state_payload()

    @modal.method()
    def health(self):
        return {"status": "ok"}

    @modal.method()
    def list_models(self):
        import os

        vol.reload()

        # Standalone folders shown as their own sections
        solo_folders = ["loras", "vae", "controlnet", "upscale_models",
                        "embeddings", "clip", "text_encoders"]
        result = {}
        for folder in solo_folders:
            folder_path = os.path.join(MODELS_PATH, folder)
            if not os.path.isdir(folder_path):
                result[folder] = []
                continue
            files = []
            for fname in sorted(os.listdir(folder_path)):
                fpath = os.path.join(folder_path, fname)
                if os.path.isfile(fpath):
                    files.append({"name": fname, "size": os.path.getsize(fpath), "folder": folder})
            result[folder] = files
        # Checkpoint-family folders all shown under "checkpoints" in the sidebar,
        # but each file carries its real "folder" so inject/delete uses the right path.
        checkpoint_family = ["checkpoints", "diffusion_models", "unet"]
        result["checkpoints"] = []
        for folder in checkpoint_family:
            folder_path = os.path.join(MODELS_PATH, folder)
            if not os.path.isdir(folder_path):
                continue
            for fname in sorted(os.listdir(folder_path)):
                fpath = os.path.join(folder_path, fname)
                if os.path.isfile(fpath):
                    result["checkpoints"].append({"name": fname, "size": os.path.getsize(fpath), "folder": folder})
        return result

    @modal.method()
    def delete_model(self, folder: str, filename: str):
        import os
        safe_folder = os.path.basename(folder)
        safe_file = os.path.basename(filename)
        target = os.path.join(MODELS_PATH, safe_folder, safe_file)
        if not os.path.isfile(target):
            return {"status": "error", "message": "File not found"}
        os.remove(target)
        vol.commit()
        return {"status": "ok", "deleted": f"{safe_folder}/{safe_file}"}


def _register_gpu_classes():
    for entry in GPU_CATALOG:
        if is_gpu_hidden(entry["value"]):
            continue
        profile = GPU_PROFILES[entry["profile"]]
        # Backward compatibility: the a10g worker keeps the legacy class name "ComfyAPI".
        class_name = entry["class_name"]
        Generated = type(class_name, (_ComfyAPIMixin,), {})
        Generated = modal.concurrent(
            target_inputs=profile["target_inputs"],
            max_inputs=profile["max_inputs"],
        )(Generated)
        Generated = app.cls(
            gpu=entry["modal_gpu"],
            cpu=profile["cpu"],
            memory=profile["memory"],
            timeout=3600,
            min_containers=0,
            # Scale down quickly to avoid holding GPU resources when idle
            scaledown_window=4,
            volumes={MODELS_PATH: vol, CUSTOM_NODES_PATH: custom_nodes_vol},
            enable_memory_snapshot=True,
            # GPU snapshot: when enabled, _force_triton_during_snapshot() blocks
            # SageAttention C extensions (safe) while allowing ComfyUI GPU init.
            # The snapshot captures the CUDA context and compiled kernels.
            **({"experimental_options": {"enable_gpu_snapshot": True}} if ENABLE_GPU_SNAPSHOT else {}),
            secrets=[modal.Secret.from_name("comfyui-warmup-dev")],
        )(Generated)
        globals()[class_name] = Generated


_register_gpu_classes()
