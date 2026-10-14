"""Web-adjacent inpaint/expand helpers (pure functions, Pillow + numpy only).

Deterministic image-geometry utilities for Studio inpaint/outpaint flows:
bounding boxes, crops, edge-replicated padding, masked stitching, and
seam-feathered preservation. No classes, no ComfyUI imports, no network.
"""

from __future__ import annotations

from typing import Optional, Tuple

import numpy as np
from PIL import Image

_LANCZOS = getattr(getattr(Image, "Resampling", object), "LANCZOS", 1)

Box = Tuple[int, int, int, int]


def _require_rgb(image, name: str) -> None:
    if not isinstance(image, Image.Image):
        raise ValueError(f"{name} must be a PIL Image, got {type(image).__name__}")
    if image.mode != "RGB":
        raise ValueError(f"{name} must be mode 'RGB', got mode {image.mode!r}")


def _require_mask(image, name: str) -> None:
    if not isinstance(image, Image.Image):
        raise ValueError(f"{name} must be a PIL Image, got {type(image).__name__}")
    if image.mode != "L":
        raise ValueError(f"{name} must be mode 'L', got mode {image.mode!r}")


def _require_box(box, name: str = "box") -> Box:
    if not isinstance(box, (tuple, list)) or len(box) != 4:
        raise ValueError(f"{name} must be a 4-tuple (x0, y0, x1, y1), got {box!r}")
    vals = tuple(box)
    for v in vals:
        if isinstance(v, bool) or not isinstance(v, int):
            raise ValueError(f"{name} coordinates must be ints, got {box!r}")
    x0, y0, x1, y1 = vals
    if x0 >= x1 or y0 >= y1:
        raise ValueError(f"{name} is degenerate/empty: got {tuple(vals)!r}")
    return (x0, y0, x1, y1)


def mask_bbox(mask_L, threshold=128) -> Optional[Box]:
    """Return exclusive-upper ``(x0, y0, x1, y1)`` bbox of pixels > threshold.

    Returns None when no pixel exceeds the threshold.
    """
    _require_mask(mask_L, "mask_L")
    if isinstance(threshold, bool) or not isinstance(threshold, (int, float)):
        raise ValueError(f"threshold must be a number in [0, 255], got {threshold!r}")
    if not 0 <= threshold <= 255:
        raise ValueError(f"threshold must be in [0, 255], got {threshold!r}")
    arr = np.asarray(mask_L)
    if arr.ndim != 2:
        raise ValueError(f"mask_L must be a 2D mode-'L' image, got shape {arr.shape}")
    ys, xs = np.where(arr > threshold)
    if xs.size == 0:
        return None
    return (int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1)


def crop_box_for_mask(w, h, bbox, margin_frac=0.25, min_margin=24) -> Box:
    """Expand bbox by margin, then return a centered SQUARE box snapped to /8.

    Squareness is structural, not cosmetic: ordinary I2I graphs in the wild
    force fixed output geometry (e.g. cover-resize to a square), so a
    non-square crop would come back content-shifted and stitch misaligned. A
    square crop round-trips through such graphs as a pure scale, which the
    stitch step inverts exactly. Extra context never leaks into the result:
    stitching composites through the full-image mask, so outside-mask pixels
    always come from the original. The returned box is exactly square (the
    /8 snap trims right/bottom to re-square); only the full-frame degenerate
    case may be non-square.
    """
    for label, v in (("w", w), ("h", h)):
        if isinstance(v, bool) or not isinstance(v, int) or v <= 0:
            raise ValueError(f"{label} must be a positive int, got {v!r}")
    x0, y0, x1, y1 = _require_box(bbox, "bbox")
    if isinstance(margin_frac, bool) or not isinstance(margin_frac, (int, float)):
        raise ValueError(f"margin_frac must be a non-negative number, got {margin_frac!r}")
    if margin_frac < 0:
        raise ValueError(f"margin_frac must be non-negative, got {margin_frac!r}")
    if isinstance(min_margin, bool) or not isinstance(min_margin, int):
        raise ValueError(f"min_margin must be a non-negative int, got {min_margin!r}")
    if min_margin < 0:
        raise ValueError(f"min_margin must be non-negative, got {min_margin!r}")
    bw = x1 - x0
    bh = y1 - y0
    margin = max(min_margin, round(margin_frac * max(bw, bh)))
    nx0 = max(0, x0 - margin)
    ny0 = max(0, y0 - margin)
    nx1 = min(w, x1 + margin)
    ny1 = min(h, y1 + margin)
    side0 = max(nx1 - nx0, ny1 - ny0)
    if side0 >= min(w, h):
        # Degenerate: the mask covers the frame; crop is the full image.
        return (_snap_down(0), _snap_down(0), _snap_up(w, w), _snap_up(h, h))
    side = min(side0, w, h)
    cx = (nx0 + nx1) // 2
    cy = (ny0 + ny1) // 2
    sx0 = min(max(cx - side // 2, 0), w - side)
    sy0 = min(max(cy - side // 2, 0), h - side)
    sx1 = sx0 + side
    sy1 = sy0 + side
    sx0 = _snap_down(sx0)
    sy0 = _snap_down(sy0)
    sx1 = _snap_up(sx1, w)
    sy1 = _snap_up(sy1, h)
    side = min(sx1 - sx0, sy1 - sy0)
    sx1 = sx0 + side
    sy1 = sy0 + side
    if sx0 >= sx1 or sy0 >= sy1:
        raise ValueError(
            f"expanded box is empty/degenerate: bbox={tuple(bbox)!r} "
            f"for {w}x{h}"
        )
    return (sx0, sy0, sx1, sy1)


def _snap_down(v):
    return (int(v) // 8) * 8


def _snap_up(v, limit):
    return min(int(limit), ((int(v) + 7) // 8) * 8)


def crop_image_and_mask(source_rgb, mask_L, box):
    """Crop source RGB and mask to box; both inputs must share the same size."""
    _require_rgb(source_rgb, "source_rgb")
    _require_mask(mask_L, "mask_L")
    if source_rgb.size != mask_L.size:
        raise ValueError(
            f"source_rgb and mask_L must share the same size, "
            f"got {source_rgb.size} vs {mask_L.size}"
        )
    x0, y0, x1, y1 = _require_box(box, "box")
    w, h = source_rgb.size
    if not (0 <= x0 < x1 <= w and 0 <= y0 < y1 <= h):
        raise ValueError(f"box {tuple(box)!r} is outside image bounds {(w, h)}")
    return (source_rgb.crop((x0, y0, x1, y1)), mask_L.crop((x0, y0, x1, y1)))


def pad_canvas(source_rgb, top, right, bottom, left):
    """Pad canvas with edge-replicated fill (numpy edge pad, not solid color)."""
    _require_rgb(source_rgb, "source_rgb")
    pads = (("top", top), ("right", right), ("bottom", bottom), ("left", left))
    for label, v in pads:
        if isinstance(v, bool) or not isinstance(v, int):
            raise ValueError(f"{label} pad must be a non-negative int, got {v!r}")
        if v < 0:
            raise ValueError(f"{label} pad must be non-negative, got {v!r}")
    if top == 0 and right == 0 and bottom == 0 and left == 0:
        raise ValueError("at least one pad (top/right/bottom/left) must be > 0")
    arr = np.asarray(source_rgb)
    padded = np.pad(arr, ((top, bottom), (left, right), (0, 0)), mode="edge")
    return Image.fromarray(padded, mode="RGB")


def stitch_composite(original_rgb, generated_rgb, box, mask_full_L):
    """Paste generated crop over a copy of the original using the mask as alpha.

    ``generated_rgb`` is resized with Lanczos ONLY when its size differs from
    the box size. ``mask_full_L`` is full-image sized and cropped to the box.
    """
    _require_rgb(original_rgb, "original_rgb")
    _require_rgb(generated_rgb, "generated_rgb")
    _require_mask(mask_full_L, "mask_full_L")
    if mask_full_L.size != original_rgb.size:
        raise ValueError(
            f"mask_full_L must match original_rgb size {original_rgb.size}, "
            f"got {mask_full_L.size}"
        )
    x0, y0, x1, y1 = _require_box(box, "box")
    w, h = original_rgb.size
    if not (0 <= x0 < x1 <= w and 0 <= y0 < y1 <= h):
        raise ValueError(f"box {tuple(box)!r} is outside image bounds {(w, h)}")
    bw, bh = x1 - x0, y1 - y0
    if generated_rgb.size != (bw, bh):
        generated_rgb = generated_rgb.resize((bw, bh), _LANCZOS)
    alpha = mask_full_L.crop((x0, y0, x1, y1))
    out = original_rgb.copy()
    out.paste(generated_rgb, (x0, y0), alpha)
    if out.mode != "RGB":
        out = out.convert("RGB")
    return out


def preserve_composite(expanded_result_rgb, original_rgb, origin_xy):
    """Paste the original back at (ox, oy) with a feathered rectangular alpha.

    Feather width is deterministic: ``max(8, min(orig_w, orig_h) // 64)``.
    Interior pixels (>= feather_px from every edge) are restored exactly.
    """
    _require_rgb(expanded_result_rgb, "expanded_result_rgb")
    _require_rgb(original_rgb, "original_rgb")
    if (
        not isinstance(origin_xy, (tuple, list))
        or len(origin_xy) != 2
        or any(isinstance(v, bool) or not isinstance(v, int) for v in origin_xy)
    ):
        raise ValueError(f"origin_xy must be a pair of ints, got {origin_xy!r}")
    ox, oy = int(origin_xy[0]), int(origin_xy[1])
    if ox < 0 or oy < 0:
        raise ValueError(f"origin_xy must be non-negative, got {(ox, oy)!r}")
    ow, oh = original_rgb.size
    ew, eh = expanded_result_rgb.size
    if ox + ow > ew or oy + oh > eh:
        raise ValueError(
            f"original {ow}x{oh} at origin {(ox, oy)} does not fit "
            f"in expanded canvas {ew}x{eh}"
        )
    feather_px = max(8, min(ow, oh) // 64)
    # Linear ramp: 0 at the outer edge, 255 once >= feather_px inside.
    yy, xx = np.mgrid[0:oh, 0:ow]
    dist = np.minimum(np.minimum(xx, yy), np.minimum(ow - 1 - xx, oh - 1 - yy))
    alpha_arr = np.where(
        dist >= feather_px, 255, np.round(255.0 * dist / float(feather_px))
    ).astype(np.uint8)
    alpha = Image.fromarray(alpha_arr, mode="L")
    out = expanded_result_rgb.copy()
    out.paste(original_rgb, (ox, oy), alpha)
    if out.mode != "RGB":
        out = out.convert("RGB")
    return out


# ---------------------------------------------------------------------------
# Inpaint-conditioning anchors (append-only section; helpers above untouched).
#
# Pure ComfyUI API-prompt helpers: locate the single KSampler + single VAE
# output, then splice in LoadImage / ImageToMask / InpaintModelConditioning
# nodes. Stdlib only (copy) plus a guarded `nodes` import inside
# `_return_types`; no network, no classes.
# ---------------------------------------------------------------------------
import copy


def _return_types(class_type):
    """Return old-style ``RETURN_TYPES`` for a ComfyUI node class, or None.

    Resolves ``nodes.NODE_CLASS_MAPPINGS.get(class_type)`` and returns
    ``list(RETURN_TYPES)`` only when it is a list/tuple of all-strings.
    Any exception, missing class, or non-conforming value yields None.
    This function never raises.
    """
    try:
        import nodes as _nodes

        mappings = getattr(_nodes, "NODE_CLASS_MAPPINGS", None)
        if not isinstance(mappings, dict):
            return None
        cls = mappings.get(class_type)
        if cls is None:
            return None
        rt = getattr(cls, "RETURN_TYPES", None)
        if not isinstance(rt, (list, tuple)):
            return None
        if not all(isinstance(item, str) for item in rt):
            return None
        return list(rt)
    except Exception:
        return None


def find_conditioning_anchors(prompt):
    """Locate the KSampler + VAE anchors for inpaint conditioning.

    ``prompt`` is ComfyUI API-format
    ``{node_id: {"class_type": str, "inputs": {...}}}``. Returns a dict with
    keys ``compatible``, ``reasons``, ``sampler_id``, ``positive``,
    ``negative``, ``latent`` and ``vae``. Link values are ``[node_id, slot]``
    lists (first two entries of the raw link). ``reasons`` entries always
    carry an ``INPAINT-COND-xx`` code.
    """
    if not isinstance(prompt, dict):
        raise ValueError(
            "prompt must be a dict of node_id to node, "
            f"got {type(prompt).__name__}"
        )
    sampler_ids = [
        node_id
        for node_id, node in prompt.items()
        if isinstance(node, dict) and node.get("class_type") == "KSampler"
    ]
    reasons = []
    sampler_id = None
    positive = None
    negative = None
    latent = None
    vae = None

    if len(sampler_ids) == 0:
        reasons.append("INPAINT-COND-01: no KSampler node found")
    elif len(sampler_ids) >= 2:
        ordered = sorted(str(n) for n in sampler_ids)
        reasons.append(f"INPAINT-COND-02: ambiguous samplers {ordered}")
    else:
        sampler_id = sampler_ids[0]
        node = prompt.get(sampler_id)
        inputs = node.get("inputs") if isinstance(node, dict) else None
        if not isinstance(inputs, dict):
            inputs = {}
        pos_link = inputs.get("positive")
        if not isinstance(pos_link, (list, tuple)) or len(pos_link) < 2:
            reasons.append(
                f"INPAINT-COND-03: sampler {sampler_id!r} missing "
                "or non-link 'positive' input (expected [node_id, slot])"
            )
        else:
            positive = [pos_link[0], pos_link[1]]
        neg_link = inputs.get("negative")
        if not isinstance(neg_link, (list, tuple)) or len(neg_link) < 2:
            reasons.append(
                f"INPAINT-COND-04: sampler {sampler_id!r} missing "
                "or non-link 'negative' input (expected [node_id, slot])"
            )
        else:
            negative = [neg_link[0], neg_link[1]]
        lat_link = inputs.get("latent_image")
        if not isinstance(lat_link, (list, tuple)) or len(lat_link) < 2:
            reasons.append(
                f"INPAINT-COND-05: sampler {sampler_id!r} missing "
                "or non-link 'latent_image' input (expected [node_id, slot])"
            )
        else:
            latent = [lat_link[0], lat_link[1]]

    vae_candidates = []
    for node_id, node in prompt.items():
        if not isinstance(node, dict):
            continue
        class_type = node.get("class_type")
        if not isinstance(class_type, str):
            continue
        return_types = _return_types(class_type)
        if return_types is None:
            continue
        for slot_index, type_name in enumerate(return_types):
            if type_name == "VAE":
                vae_candidates.append((node_id, slot_index))
    if len(vae_candidates) == 0:
        reasons.append("INPAINT-COND-06: no VAE output found")
    elif len(vae_candidates) >= 2:
        labels = [f"{node_id}:{slot}" for node_id, slot in vae_candidates]
        reasons.append(f"INPAINT-COND-07: ambiguous VAE outputs {labels}")
    else:
        vae_node, vae_slot = vae_candidates[0]
        vae = [vae_node, vae_slot]

    compatible = (
        sampler_id is not None
        and positive is not None
        and negative is not None
        and latent is not None
        and vae is not None
    )
    if compatible:
        vae_node_ok, vae_slot_ok = vae_candidates[0]
        reasons.append(
            f"INPAINT-COND-OK: sampler {sampler_id!r} with positive/negative/"
            f"latent links and VAE '{vae_node_ok}:{vae_slot_ok}'"
        )
    return {
        "compatible": compatible,
        "reasons": reasons,
        "sampler_id": sampler_id,
        "positive": positive,
        "negative": negative,
        "latent": latent,
        "vae": vae,
    }


def inject_inpaint_conditioning(prompt, *, source_file, mask_file):
    """Splice inpaint-conditioning nodes into a deep copy of ``prompt``.

    Adds ``LoadImage`` (source), ``LoadImage`` (mask), ``ImageToMask`` and
    ``InpaintModelConditioning`` nodes with deterministic fresh string ids
    (``max(existing int ids, default 8999) + 1 ...``), then rewires the
    sampler's ``positive``/``negative``/``latent_image`` inputs to the new
    conditioning node's slots 0/1/2. Returns ``(new_prompt, diagnostics)``.
    The input ``prompt`` is never mutated. Raises ValueError for bad
    filenames or when anchors are incompatible.
    """
    new_prompt = copy.deepcopy(prompt)
    if not isinstance(source_file, str) or not source_file:
        raise ValueError(
            f"source_file must be a non-empty string, got {source_file!r}"
        )
    if not isinstance(mask_file, str) or not mask_file:
        raise ValueError(
            f"mask_file must be a non-empty string, got {mask_file!r}"
        )
    if not isinstance(new_prompt, dict):
        raise ValueError(
            "prompt must be a dict of node_id to node, "
            f"got {type(new_prompt).__name__}"
        )
    anchors = find_conditioning_anchors(new_prompt)
    if not anchors["compatible"]:
        raise ValueError("; ".join(anchors["reasons"]))
    assert anchors["positive"] is not None
    assert anchors["negative"] is not None
    assert anchors["latent"] is not None
    assert anchors["vae"] is not None
    sampler_id = anchors["sampler_id"]
    positive_from = [anchors["positive"][0], anchors["positive"][1]]
    negative_from = [anchors["negative"][0], anchors["negative"][1]]
    latent_from = [anchors["latent"][0], anchors["latent"][1]]
    vae_from = [anchors["vae"][0], anchors["vae"][1]]

    existing_ints = []
    for key in new_prompt.keys():
        try:
            existing_ints.append(int(key))
        except (TypeError, ValueError):
            continue
    base = max(existing_ints, default=8999)
    load_source_id = str(base + 1)
    load_mask_id = str(base + 2)
    to_mask_id = str(base + 3)
    cond_id = str(base + 4)

    new_prompt[load_source_id] = {
        "class_type": "LoadImage",
        "inputs": {"image": source_file},
    }
    new_prompt[load_mask_id] = {
        "class_type": "LoadImage",
        "inputs": {"image": mask_file},
    }
    new_prompt[to_mask_id] = {
        "class_type": "ImageToMask",
        "inputs": {"image": [load_mask_id, 0], "channel": "red"},
    }
    new_prompt[cond_id] = {
        "class_type": "InpaintModelConditioning",
        "inputs": {
            "positive": positive_from,
            "negative": negative_from,
            "vae": vae_from,
            "pixels": [load_source_id, 0],
            "mask": [to_mask_id, 0],
            "noise_mask": True,
        },
    }
    sampler_node = new_prompt[sampler_id]
    sampler_inputs = sampler_node.get("inputs")
    if not isinstance(sampler_inputs, dict):
        sampler_inputs = {}
        sampler_node["inputs"] = sampler_inputs
    sampler_inputs["positive"] = [cond_id, 0]
    sampler_inputs["negative"] = [cond_id, 1]
    sampler_inputs["latent_image"] = [cond_id, 2]

    diagnostics = {
        "injected_nodes": {
            "load_source": load_source_id,
            "load_mask": load_mask_id,
            "to_mask": to_mask_id,
            "conditioning": cond_id,
        },
        "sampler_id": sampler_id,
        "positive_from": positive_from,
        "negative_from": negative_from,
        "latent_from": latent_from,
        "vae_from": vae_from,
        "source_file": source_file,
        "mask_file": mask_file,
        "noise_mask": True,
    }
    return (new_prompt, diagnostics)
