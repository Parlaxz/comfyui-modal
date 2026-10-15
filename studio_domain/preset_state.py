"""Closed normalization/validation for version-scoped ``studio_state`` v1.

A ``studio_state`` is the image-free UI intent snapshot a ``WorkflowPreset``
carries for one ``WorkflowVersion``.  Root shape::

    {"schema_version": 1, "core": {...}, "styles": {...}, "layout": {...},
     "methods": {...}, "references": {...}, "guidance": {...},
     "sketch": {...}, "post": {...}, "output": {...}}

Rules (fail-closed, field-specific errors):

* ``schema_version`` must be the int ``1`` (bools/strings rejected).
* All eight sections are required and must be dicts; unknown root keys and
  unknown/non-allowlisted section fields are rejected.
* Any image-bearing key is rejected: exact deny-list (source/mask/reference
  files, guide image, sketch pixels, compare/outputs, file/image/pixel
  words) plus substring deny (``base64``, ``blob``, ``data:image``,
  ``url``).  Image-shaped *values* (``data:``/``blob:``/``http(s):``) are
  rejected too.  Allowlisted keys never trip the deny-list by construction.
* Caps: 64 KiB UTF-8 total (canonical JSON), 8 KiB UTF-8 per string,
  64 entries per collection.
* ``0`` / ``False`` / ``""`` are preserved (only ``None``/absent count as
  missing; declared bools also accept ``0``/``1``, normalized to bool).
* ``null`` is preserved only where documented as "unchosen"
  (``methods`` overrides, ``references.override``).

This module is dependency-light (stdlib + ``models`` errors only) so the
portability layer can reuse it without the service.  Membership of
``core.controls`` keys against the version's mapping is a *service*
concern (needs the stored mapping); here ``controls`` values are checked
as scalars and asset-role keys (``source_image``/``mask``) are rejected.
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
import re
from typing import Any

from .models import WorkflowDomainValidationError

STUDIO_STATE_SCHEMA_VERSION = 1

STUDIO_STATE_SECTIONS: tuple[str, ...] = (
    "core",
    "styles",
    "layout",
    "methods",
    "references",
    "guidance",
    "sketch",
    "post",
    "output",
)

MAX_STATE_BYTES = 64 * 1024
MAX_STRING_BYTES = 8 * 1024
MAX_COLLECTION_ENTRIES = 64

MAX_PRESET_NAME_LEN = 200
MAX_PRESET_DESCRIPTION_LEN = 2000
MAX_PRESET_TAGS = 20
MAX_PRESET_TAG_LEN = 80

_SHA256_HEX_RE = re.compile(r"[0-9a-f]{64}")

# Keys that can never appear in an image-free state (compared lowercase).
# Note: the bare words "reference"/"references" are NOT denied — the
# required "references" section and its "method"/"override"/"cards" fields
# are allowlisted; only reference *file/image* keys are image-bearing.
_IMAGE_KEY_EXACT = frozenset({
    "source", "source_image", "source_images", "sourceimage", "sourceimages",
    "mask", "mask_image", "maskimage",
    "reference_file", "reference_files",
    "reference_image", "reference_images",
    "guide", "guide_image", "guideimage",
    "sketch_pixels", "sketchpixels", "sketch_image", "sketchimage",
    "sketch_data", "sketchdata",
    "compare", "compare_image", "compareimage",
    "outputs", "output_image", "output_images", "outputimage",
    "image", "images", "image_data", "imagedata",
    "pixel", "pixels", "pixel_data", "pixeldata",
    "file", "files", "file_data", "filedata",
    "upload", "uploads", "upload_image",
    "url", "urls", "link", "links", "href",
    "base64", "blob",
    "data", "data_image", "dataimage",
    "thumbnail", "snapshot", "snapshot_image",
    "canvas", "canvas_data", "layer", "layers",
    "asset", "assets", "attachment", "attachments",
    "photo_bytes", "photo_data",
})

# Substrings that mark a key as image/URL-bearing (compared lowercase).
_IMAGE_KEY_SUBSTRINGS = ("base64", "blob", "data:image", "data_image", "url")


def _is_image_key(key: str) -> bool:
    lowered = key.lower()
    if lowered in _IMAGE_KEY_EXACT:
        return True
    return any(part in lowered for part in _IMAGE_KEY_SUBSTRINGS)


def _is_image_value(value: str) -> bool:
    lowered = value.strip().lower()
    return lowered.startswith(("data:", "blob:", "http://", "https://"))


# ── scalar helpers ─────────────────────────────────────────────────────────


def _is_finite_number(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
    )


def _check_str_cap(path: str, value: str) -> None:
    if len(value.encode("utf-8")) > MAX_STRING_BYTES:
        raise WorkflowDomainValidationError(
            f"{path} exceeds {MAX_STRING_BYTES} bytes"
        )


def _norm_str(section: str, field: str, value: Any, *, allow_empty: bool = True) -> str:
    path = f"studio_state.{section}.{field}"
    if not isinstance(value, str):
        raise WorkflowDomainValidationError(f"{path} must be a string")
    if not allow_empty and not value:
        raise WorkflowDomainValidationError(f"{path} must be a non-empty string")
    _check_str_cap(path, value)
    if _is_image_value(value):
        raise WorkflowDomainValidationError(
            f"{path} must not carry an image/URL value"
        )
    return value


def _norm_num(section: str, field: str, value: Any) -> Any:
    path = f"studio_state.{section}.{field}"
    if isinstance(value, bool) or not _is_finite_number(value):
        raise WorkflowDomainValidationError(f"{path} must be a finite number")
    return value


def _norm_bool(section: str, field: str, value: Any) -> bool:
    path = f"studio_state.{section}.{field}"
    if isinstance(value, bool):
        return value
    if value in (0, 1):
        return bool(value)
    raise WorkflowDomainValidationError(f"{path} must be a boolean")


def _norm_sha256(section: str, field: str, value: Any) -> str:
    text = _norm_str(section, field, value)
    if text and _SHA256_HEX_RE.fullmatch(text) is None:
        raise WorkflowDomainValidationError(
            f"studio_state.{section}.{field} must be a 64-character "
            "lowercase hex sha256 or empty"
        )
    return text


def _reject_unknown(section: str, data: dict, allowed: frozenset[str] | set[str]) -> None:
    for key in data:
        if key not in allowed:
            raise WorkflowDomainValidationError(
                f"studio_state.{section}.{key} is not an allowlisted field"
            )


def _check_collection_cap(path: str, value: Any) -> None:
    if isinstance(value, (dict, list)) and len(value) > MAX_COLLECTION_ENTRIES:
        raise WorkflowDomainValidationError(
            f"{path} exceeds {MAX_COLLECTION_ENTRIES} entries"
        )


# ── section validators (each returns a normalized deep copy) ───────────────


# Asset roles may never appear as preset control keys (no image payloads).
_ASSET_CONTROL_ROLES = frozenset({"source_image", "mask"})

_CORE_FIELDS = frozenset({
    "positive_prompt", "negative_prompt", "controls",
    "activeMode", "activeSubtool", "skipTextGenerate",
})


def _norm_core(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise WorkflowDomainValidationError("studio_state.core must be an object")
    _check_collection_cap("studio_state.core", data)
    _reject_unknown("core", data, _CORE_FIELDS)
    out: dict[str, Any] = {}
    for field in ("positive_prompt", "negative_prompt", "activeMode", "activeSubtool"):
        if field not in data:
            raise WorkflowDomainValidationError(
                f"studio_state.core.{field} is required"
            )
        out[field] = _norm_str("core", field, data[field])
    if "skipTextGenerate" not in data:
        raise WorkflowDomainValidationError(
            "studio_state.core.skipTextGenerate is required"
        )
    out["skipTextGenerate"] = _norm_bool("core", "skipTextGenerate",
                                          data["skipTextGenerate"])
    if "controls" not in data or not isinstance(data["controls"], dict):
        raise WorkflowDomainValidationError(
            "studio_state.core.controls must be an object"
        )
    controls = data["controls"]
    _check_collection_cap("studio_state.core.controls", controls)
    norm_controls: dict[str, Any] = {}
    for role, value in controls.items():
        path = f"studio_state.core.controls[{role!r}]"
        if not isinstance(role, str) or not role:
            raise WorkflowDomainValidationError(
                "studio_state.core.controls keys must be non-empty strings"
            )
        if role in _ASSET_CONTROL_ROLES:
            raise WorkflowDomainValidationError(
                f"{path} is an image-bearing asset role and can never be a preset control"
            )
        if _is_image_key(role):
            raise WorkflowDomainValidationError(
                f"{path} is an image-bearing key and is rejected"
            )
        if value is None:
            raise WorkflowDomainValidationError(f"{path} must be a scalar, not null")
        if isinstance(value, str):
            _check_str_cap(path, value)
            if _is_image_value(value):
                raise WorkflowDomainValidationError(
                    f"{path} must not carry an image/URL value"
                )
            norm_controls[role] = value
        elif _is_finite_number(value):
            norm_controls[role] = value
        elif isinstance(value, bool):
            norm_controls[role] = value
        else:
            raise WorkflowDomainValidationError(
                f"{path} must be a string, number, or boolean scalar"
            )
    out["controls"] = norm_controls
    return out


_STYLES_FIELDS = frozenset({"setId", "selectedId", "basePrompt", "base_prompt"})


def _norm_styles(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise WorkflowDomainValidationError("studio_state.styles must be an object")
    _check_collection_cap("studio_state.styles", data)
    _reject_unknown("styles", data, _STYLES_FIELDS)
    out: dict[str, Any] = {}
    for field in ("setId", "selectedId"):
        if field not in data:
            raise WorkflowDomainValidationError(
                f"studio_state.styles.{field} is required"
            )
        out[field] = _norm_str("styles", field, data[field])
    # The base user prompt travels with the style ids; the expanded style
    # content itself is never stored.  Both spellings accepted, stored as-is.
    for field in ("basePrompt", "base_prompt"):
        if field in data:
            out[field] = _norm_str("styles", field, data[field])
    return out


_LAYOUT_FIELDS = frozenset({
    "high_level_description", "background", "style_mode", "aesthetics",
    "lighting", "photo", "medium", "art_style", "color_palette",
    "width", "height", "bgBrightness", "boxes",
})
_BOX_FIELDS = frozenset({
    "id", "type", "x", "y", "w", "h", "desc", "text",
    "color_palette", "nobbox", "locked",
})


def _norm_layout(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise WorkflowDomainValidationError("studio_state.layout must be an object")
    _check_collection_cap("studio_state.layout", data)
    _reject_unknown("layout", data, _LAYOUT_FIELDS)
    out: dict[str, Any] = {}
    for field in ("high_level_description", "background", "style_mode",
                  "aesthetics", "lighting", "photo", "medium", "art_style",
                  "color_palette"):
        if field in data:
            out[field] = _norm_str("layout", field, data[field])
    for field in ("width", "height", "bgBrightness"):
        if field in data:
            out[field] = _norm_num("layout", field, data[field])
    if "boxes" in data:
        boxes = data["boxes"]
        if not isinstance(boxes, list):
            raise WorkflowDomainValidationError(
                "studio_state.layout.boxes must be a list"
            )
        _check_collection_cap("studio_state.layout.boxes", boxes)
        norm_boxes: list[dict[str, Any]] = []
        for idx, raw in enumerate(boxes):
            path = f"studio_state.layout.boxes[{idx}]"
            if not isinstance(raw, dict):
                raise WorkflowDomainValidationError(f"{path} must be an object")
            _check_collection_cap(path, raw)
            for key in raw:
                if key not in _BOX_FIELDS:
                    raise WorkflowDomainValidationError(
                        f"{path}.{key} is not an allowlisted field"
                    )
            if not isinstance(raw.get("id"), str) or not raw.get("id"):
                raise WorkflowDomainValidationError(
                    f"{path}.id must be a non-empty string"
                )
            item: dict[str, Any] = {"id": raw["id"]}
            _check_str_cap(f"{path}.id", raw["id"])
            for field in ("type", "desc", "text", "color_palette"):
                if field in raw:
                    if not isinstance(raw[field], str):
                        raise WorkflowDomainValidationError(
                            f"{path}.{field} must be a string"
                        )
                    _check_str_cap(f"{path}.{field}", raw[field])
                    if _is_image_value(raw[field]):
                        raise WorkflowDomainValidationError(
                            f"{path}.{field} must not carry an image/URL value"
                        )
                    item[field] = raw[field]
            for field in ("x", "y", "w", "h"):
                if field in raw:
                    if isinstance(raw[field], bool) or not _is_finite_number(raw[field]):
                        raise WorkflowDomainValidationError(
                            f"{path}.{field} must be a finite number"
                        )
                    item[field] = raw[field]
            for field in ("nobbox", "locked"):
                if field in raw:
                    item[field] = _norm_bool("layout", f"boxes[{idx}].{field}",
                                             raw[field])
            norm_boxes.append(item)
        out["boxes"] = norm_boxes
    return out


_METHODS_FIELDS = frozenset({
    "inpaintMethod", "inpaintOverride", "expandMethod", "expandOverride",
    "padTop", "padRight", "padBottom", "padLeft",
})
_OVERRIDE_FIELDS = frozenset({"workflow_id", "workflow_version_id"})


def _norm_override(section: str, field: str, value: Any) -> dict[str, Any] | None:
    path = f"studio_state.{section}.{field}"
    if value is None:
        return None  # null = unchosen, preserved
    if not isinstance(value, dict):
        raise WorkflowDomainValidationError(
            f"{path} must be an object with exactly "
            "{workflow_id, workflow_version_id} or null"
        )
    for key in value:
        if key not in _OVERRIDE_FIELDS:
            raise WorkflowDomainValidationError(
                f"{path}.{key} is not an allowlisted field"
            )
    for key in ("workflow_id", "workflow_version_id"):
        if not isinstance(value.get(key), str) or not value.get(key):
            raise WorkflowDomainValidationError(
                f"{path}.{key} must be a non-empty string"
            )
    return {"workflow_id": value["workflow_id"],
            "workflow_version_id": value["workflow_version_id"]}


def _norm_methods(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise WorkflowDomainValidationError("studio_state.methods must be an object")
    _check_collection_cap("studio_state.methods", data)
    _reject_unknown("methods", data, _METHODS_FIELDS)
    out: dict[str, Any] = {}
    for field in ("inpaintMethod", "expandMethod"):
        if field in data:
            if data[field] is None:
                out[field] = None
            else:
                out[field] = _norm_str("methods", field, data[field])
    for field in ("inpaintOverride", "expandOverride"):
        if field in data:
            out[field] = _norm_override("methods", field, data[field])
    for field in ("padTop", "padRight", "padBottom", "padLeft"):
        if field in data:
            if data[field] is None:
                out[field] = None
            else:
                out[field] = _norm_num("methods", field, data[field])
    return out


_REFERENCES_FIELDS = frozenset({"method", "override", "cards"})


def _norm_references(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise WorkflowDomainValidationError(
            "studio_state.references must be an object"
        )
    _check_collection_cap("studio_state.references", data)
    _reject_unknown("references", data, _REFERENCES_FIELDS)
    out: dict[str, Any] = {}
    if "method" in data:
        out["method"] = _norm_str("references", "method", data["method"])
    if "override" in data:
        out["override"] = _norm_override("references", "override", data["override"])
    if "cards" in data:
        cards = data["cards"]
        if not isinstance(cards, list):
            raise WorkflowDomainValidationError(
                "studio_state.references.cards must be a list"
            )
        _check_collection_cap("studio_state.references.cards", cards)
        norm_cards: list[dict[str, str]] = []
        for idx, raw in enumerate(cards):
            path = f"studio_state.references.cards[{idx}]"
            if not isinstance(raw, dict):
                raise WorkflowDomainValidationError(f"{path} must be an object")
            for key in raw:
                if key != "label":
                    raise WorkflowDomainValidationError(
                        f"{path}.{key} is not an allowlisted field "
                        "(cards carry only {label})"
                    )
            if not isinstance(raw.get("label"), str) or not raw.get("label"):
                raise WorkflowDomainValidationError(
                    f"{path}.label must be a non-empty string"
                )
            _check_str_cap(f"{path}.label", raw["label"])
            norm_cards.append({"label": raw["label"]})
        out["cards"] = norm_cards  # order preserved
    return out


_GUIDANCE_FIELDS = frozenset({
    "engaged", "mode", "mechanism", "model_sha256", "mapping_revision",
    "controller", "nodes", "conditioning",
})
_CONTROLLER_FIELDS = frozenset({"checkpoint", "folder", "checkpoint_sha256"})
_NODES_FIELDS = frozenset({"loader", "apply", "preprocessor"})
_CONDITIONING_FIELDS = frozenset({"strength", "start", "end"})


def _norm_guidance(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise WorkflowDomainValidationError("studio_state.guidance must be an object")
    _check_collection_cap("studio_state.guidance", data)
    _reject_unknown("guidance", data, _GUIDANCE_FIELDS)
    out: dict[str, Any] = {}
    if "engaged" in data:
        out["engaged"] = _norm_bool("guidance", "engaged", data["engaged"])
    for field in ("mode", "mechanism", "mapping_revision"):
        if field in data:
            out[field] = _norm_str("guidance", field, data[field])
    if "model_sha256" in data:
        out["model_sha256"] = _norm_sha256("guidance", "model_sha256",
                                           data["model_sha256"])
    if "controller" in data:
        ctrl = data["controller"]
        if not isinstance(ctrl, dict):
            raise WorkflowDomainValidationError(
                "studio_state.guidance.controller must be an object"
            )
        _check_collection_cap("studio_state.guidance.controller", ctrl)
        _reject_unknown("guidance.controller", ctrl, _CONTROLLER_FIELDS)
        norm_ctrl: dict[str, str] = {}
        for field in ("checkpoint", "folder"):
            if field in ctrl:
                norm_ctrl[field] = _norm_str("guidance.controller", field,
                                            ctrl[field])
        if "checkpoint_sha256" in ctrl:
            norm_ctrl["checkpoint_sha256"] = _norm_sha256(
                "guidance.controller", "checkpoint_sha256",
                ctrl["checkpoint_sha256"])
        out["controller"] = norm_ctrl
    if "nodes" in data:
        nodes = data["nodes"]
        if not isinstance(nodes, dict):
            raise WorkflowDomainValidationError(
                "studio_state.guidance.nodes must be an object"
            )
        _check_collection_cap("studio_state.guidance.nodes", nodes)
        _reject_unknown("guidance.nodes", nodes, _NODES_FIELDS)
        out["nodes"] = {
            field: _norm_str("guidance.nodes", field, nodes[field])
            for field in nodes
        }
    if "conditioning" in data:
        cond = data["conditioning"]
        if not isinstance(cond, dict):
            raise WorkflowDomainValidationError(
                "studio_state.guidance.conditioning must be an object"
            )
        _check_collection_cap("studio_state.guidance.conditioning", cond)
        _reject_unknown("guidance.conditioning", cond, _CONDITIONING_FIELDS)
        # Intent only: numeric intent knobs, never live control values.
        norm_cond: dict[str, Any] = {}
        for field in cond:
            if cond[field] is None:
                norm_cond[field] = None
            else:
                norm_cond[field] = _norm_num("guidance.conditioning", field,
                                             cond[field])
        out["conditioning"] = norm_cond
    return out


_SKETCH_FIELDS = frozenset({
    "tool", "brushSize", "opacity", "hardness", "color", "bgColor",
    "width", "height",
})


def _norm_sketch(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise WorkflowDomainValidationError("studio_state.sketch must be an object")
    _check_collection_cap("studio_state.sketch", data)
    _reject_unknown("sketch", data, _SKETCH_FIELDS)
    out: dict[str, Any] = {}
    for field in ("tool", "color", "bgColor"):
        if field in data:
            out[field] = _norm_str("sketch", field, data[field])
    for field in ("brushSize", "opacity", "hardness", "width", "height"):
        if field in data:
            out[field] = _norm_num("sketch", field, data[field])
    return out


_POST_FIELDS = frozenset({"recipe"})
# Frozen numeric/choice recipe knobs.  Spot lists and LUT contents are not
# allowlisted (closed validation rejects them as unknown fields).
_POST_RECIPE_FIELDS = frozenset({
    "curves", "mixer", "grading", "crop",
    "format", "quality", "embedMetadata", "embed_metadata",
})


def _norm_post(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise WorkflowDomainValidationError("studio_state.post must be an object")
    _check_collection_cap("studio_state.post", data)
    _reject_unknown("post", data, _POST_FIELDS)
    out: dict[str, Any] = {}
    if "recipe" in data:
        recipe = data["recipe"]
        if not isinstance(recipe, dict):
            raise WorkflowDomainValidationError(
                "studio_state.post.recipe must be an object"
            )
        _check_collection_cap("studio_state.post.recipe", recipe)
        _reject_unknown("post.recipe", recipe, _POST_RECIPE_FIELDS)
        norm_recipe: dict[str, Any] = {}
        for field, value in recipe.items():
            path = f"studio_state.post.recipe.{field}"
            if value is None:
                norm_recipe[field] = None
            elif isinstance(value, str):
                _check_str_cap(path, value)
                if _is_image_value(value):
                    raise WorkflowDomainValidationError(
                        f"{path} must not carry an image/URL value"
                    )
                norm_recipe[field] = value
            elif isinstance(value, bool) or _is_finite_number(value):
                norm_recipe[field] = value
            else:
                raise WorkflowDomainValidationError(
                    f"{path} must be a frozen numeric/choice scalar, not "
                    "spot lists or LUT contents"
                )
        out["recipe"] = norm_recipe
    return out


_OUTPUT_FIELDS = frozenset({
    "output_format", "quality", "webp_lossless_compression",
    "auto_save_local", "save_folder", "save_metadata_sidecar",
})


def _norm_output(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise WorkflowDomainValidationError("studio_state.output must be an object")
    _check_collection_cap("studio_state.output", data)
    out: dict[str, Any] = {}
    for key, value in data.items():
        if key.startswith("preview_"):
            # Canonical preview_* names carry scalar settings only.
            if not isinstance(value, (str, int, float, bool)) or value is None:
                raise WorkflowDomainValidationError(
                    f"studio_state.output.{key} must be a scalar preview setting"
                )
            if isinstance(value, str):
                _check_str_cap(f"studio_state.output.{key}", value)
                if _is_image_value(value):
                    raise WorkflowDomainValidationError(
                        f"studio_state.output.{key} must not carry an image/URL value"
                    )
            elif isinstance(value, bool):
                pass
            elif not _is_finite_number(value):
                raise WorkflowDomainValidationError(
                    f"studio_state.output.{key} must be a finite number"
                )
            out[key] = value
            continue
        if key not in _OUTPUT_FIELDS:
            raise WorkflowDomainValidationError(
                f"studio_state.output.{key} is not an allowlisted field"
            )
        if key in ("auto_save_local", "save_metadata_sidecar",
                   "webp_lossless_compression"):
            out[key] = _norm_bool("output", key, value)
        elif key == "quality":
            out[key] = _norm_num("output", key, value)
        elif key == "save_folder":
            folder = _norm_str("output", key, value)
            if folder:
                lowered = folder.replace("\\", "/")
                segments = lowered.split("/")
                if (lowered.startswith("/")
                        or re.match(r"^[a-zA-Z]:", lowered)
                        or ".." in segments
                        or lowered.startswith("~")):
                    raise WorkflowDomainValidationError(
                        "studio_state.output.save_folder must be a relative "
                        "directory path without parent traversal"
                    )
                if len(folder) > 500:
                    raise WorkflowDomainValidationError(
                        "studio_state.output.save_folder exceeds 500 characters"
                    )
            out[key] = folder
        else:  # output_format
            out[key] = _norm_str("output", key, value)
    return out


_SECTION_NORMALIZERS = {
    "core": _norm_core,
    "styles": _norm_styles,
    "layout": _norm_layout,
    "methods": _norm_methods,
    "references": _norm_references,
    "guidance": _norm_guidance,
    "sketch": _norm_sketch,
    "post": _norm_post,
    "output": _norm_output,
}


def _scan_image_keys(value: Any, path: str) -> None:
    """Reject image-bearing keys/values anywhere in the raw state first."""
    if isinstance(value, dict):
        _check_collection_cap(path, value)
        for key, item in value.items():
            if not isinstance(key, str):
                raise WorkflowDomainValidationError(
                    f"{path} keys must be strings"
                )
            _check_str_cap(f"{path}.{key}", key)
            if _is_image_key(key):
                raise WorkflowDomainValidationError(
                    f"{path}.{key} is an image-bearing key and is rejected"
                )
            _scan_image_keys(item, f"{path}.{key}")
    elif isinstance(value, list):
        _check_collection_cap(path, value)
        for idx, item in enumerate(value):
            _scan_image_keys(item, f"{path}[{idx}]")
    elif isinstance(value, str):
        _check_str_cap(path, value)
        if _is_image_value(value):
            raise WorkflowDomainValidationError(
                f"{path} must not carry an image/URL value"
            )


def _canonical_size_bytes(state: dict) -> int:
    return len(json.dumps(state, sort_keys=True, separators=(",", ":"),
                          ensure_ascii=False).encode("utf-8"))


def normalize_studio_state(state: Any) -> dict[str, Any]:
    """Validate a ``studio_state`` closedly and return its canonical copy.

    Raises ``WorkflowDomainValidationError`` with a field-specific message;
    never truncates, coerces lossily, or merges defaults.
    """
    if not isinstance(state, dict):
        raise WorkflowDomainValidationError("studio_state must be an object")
    if _canonical_size_bytes(state) > MAX_STATE_BYTES:
        raise WorkflowDomainValidationError(
            f"studio_state exceeds {MAX_STATE_BYTES} bytes UTF-8 total"
        )
    version = state.get("schema_version")
    if isinstance(version, bool) or not isinstance(version, int):
        raise WorkflowDomainValidationError(
            "studio_state.schema_version must be the int 1"
        )
    if version != STUDIO_STATE_SCHEMA_VERSION:
        raise WorkflowDomainValidationError(
            f"unsupported studio_state schema_version: {version!r} (supported: 1)"
        )
    for key in state:
        if key != "schema_version" and key not in STUDIO_STATE_SECTIONS:
            raise WorkflowDomainValidationError(
                f"unknown studio_state section: {key!r}"
            )
    for section in STUDIO_STATE_SECTIONS:
        if section not in state:
            raise WorkflowDomainValidationError(
                f"studio_state section {section!r} is required"
            )
    # Image-bearing sweep before section shaping so the refusal reason names
    # the offending key even where it would also be non-allowlisted.
    _scan_image_keys(state, "studio_state")
    normalized: dict[str, Any] = {"schema_version": STUDIO_STATE_SCHEMA_VERSION}
    for section in STUDIO_STATE_SECTIONS:
        normalized[section] = _SECTION_NORMALIZERS[section](state[section])
    if _canonical_size_bytes(normalized) > MAX_STATE_BYTES:
        raise WorkflowDomainValidationError(
            f"studio_state exceeds {MAX_STATE_BYTES} bytes UTF-8 total"
        )
    return copy.deepcopy(normalized)


validate_studio_state = normalize_studio_state


def normalize_preset_metadata(
    name: Any, description: Any = "", tags: Any = None
) -> tuple[str, str, list[str]]:
    """Validate preset identity fields (fail-closed, field-specific)."""
    if not isinstance(name, str) or not name.strip():
        raise WorkflowDomainValidationError("preset name is required")
    clean_name = name.strip()
    if len(clean_name) > MAX_PRESET_NAME_LEN:
        raise WorkflowDomainValidationError(
            f"preset name exceeds {MAX_PRESET_NAME_LEN} characters"
        )
    clean_description = "" if description is None else description
    if not isinstance(clean_description, str):
        raise WorkflowDomainValidationError("preset description must be a string")
    if len(clean_description) > MAX_PRESET_DESCRIPTION_LEN:
        raise WorkflowDomainValidationError(
            f"preset description exceeds {MAX_PRESET_DESCRIPTION_LEN} characters"
        )
    raw_tags = [] if tags is None else tags
    if not isinstance(raw_tags, list):
        raise WorkflowDomainValidationError("preset tags must be a list of strings")
    if len(raw_tags) > MAX_PRESET_TAGS:
        raise WorkflowDomainValidationError(
            f"preset tags exceed {MAX_PRESET_TAGS} entries"
        )
    clean_tags: list[str] = []
    for tag in raw_tags:
        if not isinstance(tag, str) or not tag.strip():
            raise WorkflowDomainValidationError(
                "preset tags must be non-empty strings"
            )
        trimmed = tag.strip()
        if len(trimmed) > MAX_PRESET_TAG_LEN:
            raise WorkflowDomainValidationError(
                f"preset tag {trimmed!r} exceeds {MAX_PRESET_TAG_LEN} characters"
            )
        if trimmed not in clean_tags:
            clean_tags.append(trimmed)
    return clean_name, clean_description, clean_tags


def compute_mapping_fingerprint(mapping: dict[str, Any] | None) -> str:
    """Server-computed fingerprint of a version's mapping bindings.

    Covers the ordered ``{role: {node_id, input_name, kind}}`` projection so
    a preset copied onto a re-mapped version fails closed on drift instead
    of silently binding stale inputs.  Never raises.
    """
    try:
        entries: dict[str, Any] = {}
        raw = (mapping or {}).get("entries")
        items: list[dict[str, Any]] = []
        if isinstance(raw, dict):
            items = [v for v in raw.values() if isinstance(v, dict)]
        elif isinstance(raw, list):
            items = [v for v in raw if isinstance(v, dict)]
        for entry in items:
            role = str(entry.get("semantic_role", "") or "")
            if not role:
                continue
            entries[role] = {
                "node_id": str(entry.get("node_id", "") or ""),
                "input_name": str(entry.get("input_name", "") or ""),
                "kind": str(entry.get("kind", "") or ""),
            }
        canonical = json.dumps({"entries": entries}, sort_keys=True,
                               separators=(",", ":"), ensure_ascii=False)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    except Exception:
        return ""
