"""Tests for web-adjacent inpaint/expand helpers (pure Pillow/numpy)."""

from __future__ import annotations

import numpy as np
import pytest
from PIL import Image

from studio_inpaint_expand import (
    crop_box_for_mask,
    crop_image_and_mask,
    mask_bbox,
    pad_canvas,
    preserve_composite,
    stitch_composite,
)


pytestmark = pytest.mark.fast_unit


def _rgb(arr: np.ndarray) -> Image.Image:
    return Image.fromarray(arr.astype(np.uint8), mode="RGB")


def _mask(arr: np.ndarray) -> Image.Image:
    return Image.fromarray(arr.astype(np.uint8), mode="L")


def test_mask_bbox_empty_returns_none():
    assert mask_bbox(_mask(np.zeros((16, 16), dtype=np.uint8))) is None


def test_mask_bbox_single_pixel_and_full():
    arr = np.zeros((16, 12), dtype=np.uint8)
    arr[7, 5] = 255
    assert mask_bbox(_mask(arr)) == (5, 7, 6, 8)
    assert mask_bbox(_mask(np.full((12, 16), 255, dtype=np.uint8))) == (0, 0, 16, 12)


def test_mask_bbox_threshold_selective():
    arr = np.zeros((8, 8), dtype=np.uint8)
    arr[1, 1] = 100
    arr[5, 6] = 200
    assert mask_bbox(_mask(arr), threshold=128) == (6, 5, 7, 6)
    assert mask_bbox(_mask(arr), threshold=50) == (1, 1, 7, 6)


def test_mask_bbox_bad_input_raises():
    with pytest.raises(ValueError):
        mask_bbox(_rgb(np.zeros((4, 4, 3), dtype=np.uint8)))
    with pytest.raises(ValueError):
        mask_bbox(_mask(np.zeros((4, 4), dtype=np.uint8)), threshold=300)
    with pytest.raises(ValueError):
        mask_bbox("not-an-image")


def test_crop_box_expand_and_clamp():
    # 10x10 box, margin = max(24, round(0.25*10)=2) = 24 -> (0,0,34,34);
    # squared (side 34, centered) then /8-snapped -> (0, 0, 40, 40).
    assert crop_box_for_mask(100, 100, (0, 0, 10, 10)) == (0, 0, 40, 40)
    # Bottom-right corner: (66,66,100,100) -> square side 34 -> snap -> (64, 64, 100, 100).
    assert crop_box_for_mask(100, 100, (90, 90, 100, 100)) == (64, 64, 100, 100)
    # Interior box: (16,16,84,84) -> square side 68 -> (16, 16, 88, 88).
    assert crop_box_for_mask(100, 100, (40, 40, 60, 60)) == (16, 16, 88, 88)
    # Non-square mask still yields a square box.
    box = crop_box_for_mask(200, 200, (50, 80, 150, 100))
    assert box[2] - box[0] == box[3] - box[1]
    # Full-frame mask degenerates to the whole image.
    assert crop_box_for_mask(100, 100, (0, 0, 100, 100)) == (0, 0, 100, 100)


def test_crop_box_degen_raises():
    with pytest.raises(ValueError):
        crop_box_for_mask(100, 100, (5, 5, 5, 10))
    with pytest.raises(ValueError):
        crop_box_for_mask(0, 100, (0, 0, 10, 10))
    with pytest.raises(ValueError):
        crop_box_for_mask(100, 100, (10, 10, 0, 0))


def test_crop_image_and_mask_roundtrip_and_mismatch():
    src = _rgb(np.arange(8 * 8 * 3, dtype=np.uint8).reshape(8, 8, 3))
    msk = _mask(np.arange(64, dtype=np.uint8).reshape(8, 8))
    crop_rgb, crop_m = crop_image_and_mask(src, msk, (2, 2, 6, 6))
    assert crop_rgb.size == (4, 4) and crop_m.size == (4, 4)
    assert np.array_equal(np.asarray(crop_rgb), np.asarray(src)[2:6, 2:6])
    other = _mask(np.zeros((4, 4), dtype=np.uint8))
    with pytest.raises(ValueError):
        crop_image_and_mask(src, other, (0, 0, 4, 4))
    with pytest.raises(ValueError):
        crop_image_and_mask(src, msk, (0, 0, 99, 99))


def test_pad_dims_and_edge_fill():
    # 2-color image: red left column, blue elsewhere.
    arr = np.zeros((3, 4, 3), dtype=np.uint8)
    arr[:, :, 2] = 255
    arr[:, 0, :] = (255, 0, 0)
    src = _rgb(arr)
    out = pad_canvas(src, 1, 2, 1, 1)
    assert out.size == (4 + 1 + 2, 3 + 1 + 1)
    a = np.asarray(out)
    # Edge replication: new top row == original first row; new left col == orig first col.
    assert np.array_equal(a[0, 1:-2], arr[0])
    assert np.array_equal(a[1:-1, 0], arr[:, 0])
    assert np.array_equal(a[-1, 1:-2], arr[-1])
    assert np.array_equal(a[1:-1, -1], arr[:, -1])


def test_pad_rejects_negative_and_all_zero():
    src = _rgb(np.zeros((4, 4, 3), dtype=np.uint8))
    with pytest.raises(ValueError):
        pad_canvas(src, -1, 0, 0, 0)
    with pytest.raises(ValueError):
        pad_canvas(src, 0, 0, 0, 0)


def test_stitch_identity_when_generated_matches_crop():
    rng = np.random.RandomState(0)
    orig = _rgb(rng.randint(0, 256, size=(32, 32, 3)))
    box = (8, 8, 24, 24)
    gen = orig.crop(box)
    mask_arr = np.zeros((32, 32), dtype=np.uint8)
    mask_arr[8:24, 8:24] = 255
    out = stitch_composite(orig, gen, box, _mask(mask_arr))
    assert out.size == orig.size
    assert np.array_equal(np.asarray(out), np.asarray(orig))


def test_stitch_resize_on_mismatch_and_mode_checks():
    orig = _rgb(np.zeros((32, 32, 3), dtype=np.uint8))
    gen = _rgb(np.full((4, 4, 3), (0, 255, 0), dtype=np.uint8))
    mask_arr = np.zeros((32, 32), dtype=np.uint8)
    mask_arr[8:24, 8:24] = 255
    out = stitch_composite(orig, gen, (8, 8, 24, 24), _mask(mask_arr))
    assert out.size == (32, 32)
    region = np.asarray(out)[8:24, 8:24]
    assert region[..., 1].mean() > 200  # resized solid green fills the box
    with pytest.raises(ValueError):
        stitch_composite(orig, gen, (8, 8, 24, 24), _mask(np.zeros((8, 8), dtype=np.uint8)))
    with pytest.raises(ValueError):
        stitch_composite(orig, _mask(np.zeros((4, 4), dtype=np.uint8)), (8, 8, 24, 24),
                         _mask(mask_arr))


def test_preserve_restores_exact_interior():
    rng = np.random.RandomState(1)
    orig = _rgb(rng.randint(0, 256, size=(64, 64, 3)))
    expanded = _rgb(np.full((96, 96, 3), 127, dtype=np.uint8))
    ox, oy = 16, 16
    out = preserve_composite(expanded, orig, (ox, oy))
    assert out.size == (96, 96)
    feather = max(8, 64 // 64)
    o = np.asarray(orig)
    r = np.asarray(out)
    # Pixels well inside the seam (margin > feather) must be bit-exact.
    inner_o = o[feather + 2:-feather - 2, feather + 2:-feather - 2]
    inner_r = r[oy + feather + 2:oy + 64 - feather - 2, ox + feather + 2:ox + 64 - feather - 2]
    assert np.array_equal(inner_o, inner_r)


def test_preserve_bad_origin_raises():
    orig = _rgb(np.zeros((16, 16, 3), dtype=np.uint8))
    expanded = _rgb(np.zeros((32, 32, 3), dtype=np.uint8))
    with pytest.raises(ValueError):
        preserve_composite(expanded, orig, (20, 20))
    with pytest.raises(ValueError):
        preserve_composite(expanded, orig, (-1, 0))


# ---------------------------------------------------------------------------
# Inpaint-conditioning anchors (append-only tests; tests above untouched).
# ---------------------------------------------------------------------------
import copy as _copy

import studio_inpaint_expand as _sie
from studio_inpaint_expand import (
    _return_types,
    find_conditioning_anchors,
    inject_inpaint_conditioning,
)


def test_cond_return_types_never_raises():
    assert _return_types("NoSuchClassXYZ______") is None
    assert _return_types("") is None
    assert _return_types(None) is None
    assert _return_types(123) is None
    assert _return_types(["KSampler"]) is None


def test_cond_compatible_with_stubbed_vae(monkeypatch):
    monkeypatch.setattr(
        _sie, "_return_types", lambda ct: ["VAE"] if ct == "TestVAENode" else None
    )
    prompt = {
        "1": {
            "class_type": "KSampler",
            "inputs": {
                "positive": ["2", 0],
                "negative": ["3", 0],
                "latent_image": ["4", 0],
            },
        },
        "2": {"class_type": "OtherNode", "inputs": {}},
        "3": {"class_type": "OtherNode", "inputs": {}},
        "4": {"class_type": "OtherNode", "inputs": {}},
        "5": {"class_type": "TestVAENode", "inputs": {}},
    }
    out = find_conditioning_anchors(prompt)
    assert out["compatible"] is True
    assert out["sampler_id"] == "1"
    assert out["positive"] == ["2", 0]
    assert out["negative"] == ["3", 0]
    assert out["latent"] == ["4", 0]
    assert out["vae"] == ["5", 0]
    assert any("INPAINT-COND-OK" in r for r in out["reasons"])


def test_cond_no_sampler(monkeypatch):
    monkeypatch.setattr(
        _sie, "_return_types", lambda ct: ["VAE"] if ct == "TestVAENode" else None
    )
    prompt = {"5": {"class_type": "TestVAENode", "inputs": {}}}
    out = find_conditioning_anchors(prompt)
    assert out["compatible"] is False
    assert out["sampler_id"] is None
    assert any("INPAINT-COND-01" in r for r in out["reasons"])


def test_cond_two_samplers(monkeypatch):
    monkeypatch.setattr(
        _sie, "_return_types", lambda ct: ["VAE"] if ct == "TestVAENode" else None
    )
    prompt = {
        "1": {
            "class_type": "KSampler",
            "inputs": {
                "positive": ["2", 0],
                "negative": ["3", 0],
                "latent_image": ["4", 0],
            },
        },
        "2": {"class_type": "OtherNode", "inputs": {}},
        "3": {"class_type": "OtherNode", "inputs": {}},
        "4": {"class_type": "OtherNode", "inputs": {}},
        "5": {"class_type": "TestVAENode", "inputs": {}},
        "6": {
            "class_type": "KSampler",
            "inputs": {
                "positive": ["2", 0],
                "negative": ["3", 0],
                "latent_image": ["4", 0],
            },
        },
    }
    out = find_conditioning_anchors(prompt)
    assert out["compatible"] is False
    assert any("INPAINT-COND-02" in r for r in out["reasons"])


def test_cond_literal_positive_input(monkeypatch):
    monkeypatch.setattr(
        _sie, "_return_types", lambda ct: ["VAE"] if ct == "TestVAENode" else None
    )
    prompt = {
        "1": {
            "class_type": "KSampler",
            "inputs": {
                "positive": "not-a-link",
                "negative": ["3", 0],
                "latent_image": ["4", 0],
            },
        },
        "3": {"class_type": "OtherNode", "inputs": {}},
        "4": {"class_type": "OtherNode", "inputs": {}},
        "5": {"class_type": "TestVAENode", "inputs": {}},
    }
    out = find_conditioning_anchors(prompt)
    assert out["compatible"] is False
    assert any("INPAINT-COND-03" in r for r in out["reasons"])


def test_cond_missing_negative_and_latent_inputs(monkeypatch):
    monkeypatch.setattr(
        _sie, "_return_types", lambda ct: ["VAE"] if ct == "TestVAENode" else None
    )
    prompt = {
        "1": {
            "class_type": "KSampler",
            "inputs": {"positive": ["2", 0], "negative": ["3"]},
        },
        "2": {"class_type": "OtherNode", "inputs": {}},
        "3": {"class_type": "OtherNode", "inputs": {}},
        "5": {"class_type": "TestVAENode", "inputs": {}},
    }
    out = find_conditioning_anchors(prompt)
    assert out["compatible"] is False
    assert any("INPAINT-COND-04" in r for r in out["reasons"])
    assert any("INPAINT-COND-05" in r for r in out["reasons"])


def test_cond_no_vae(monkeypatch):
    monkeypatch.setattr(_sie, "_return_types", lambda ct: None)
    prompt = {
        "1": {
            "class_type": "KSampler",
            "inputs": {
                "positive": ["2", 0],
                "negative": ["3", 0],
                "latent_image": ["4", 0],
            },
        },
        "2": {"class_type": "OtherNode", "inputs": {}},
        "3": {"class_type": "OtherNode", "inputs": {}},
        "4": {"class_type": "OtherNode", "inputs": {}},
    }
    out = find_conditioning_anchors(prompt)
    assert out["compatible"] is False
    assert any("INPAINT-COND-06" in r for r in out["reasons"])


def test_cond_two_vae_outputs(monkeypatch):
    def _fake(ct):
        if ct in ("TestVAENodeA", "TestVAENodeB"):
            return ["VAE"]
        return None

    monkeypatch.setattr(_sie, "_return_types", _fake)
    prompt = {
        "1": {
            "class_type": "KSampler",
            "inputs": {
                "positive": ["2", 0],
                "negative": ["3", 0],
                "latent_image": ["4", 0],
            },
        },
        "2": {"class_type": "OtherNode", "inputs": {}},
        "3": {"class_type": "OtherNode", "inputs": {}},
        "4": {"class_type": "OtherNode", "inputs": {}},
        "5": {"class_type": "TestVAENodeA", "inputs": {}},
        "6": {"class_type": "TestVAENodeB", "inputs": {}},
    }
    out = find_conditioning_anchors(prompt)
    assert out["compatible"] is False
    assert any("INPAINT-COND-07" in r for r in out["reasons"])
    reason = next(r for r in out["reasons"] if "INPAINT-COND-07" in r)
    assert "5:0" in reason and "6:0" in reason


def test_cond_real_nodes_vae_scan_or_skip():
    nodes = pytest.importorskip("nodes")
    vae_class = None
    for name, cls in nodes.NODE_CLASS_MAPPINGS.items():
        rt = getattr(cls, "RETURN_TYPES", None)
        if isinstance(rt, (list, tuple)) and "VAE" in list(rt):
            vae_class = name
            break
    if vae_class is None:
        pytest.skip("no VAE-output class in the real nodes module")
    prompt = {
        "1": {
            "class_type": "KSampler",
            "inputs": {
                "positive": ["2", 0],
                "negative": ["3", 0],
                "latent_image": ["4", 0],
            },
        },
        "2": {"class_type": "OtherNode", "inputs": {}},
        "3": {"class_type": "OtherNode", "inputs": {}},
        "4": {"class_type": "OtherNode", "inputs": {}},
        "5": {"class_type": vae_class, "inputs": {}},
    }
    out = find_conditioning_anchors(prompt)
    assert out["compatible"] is True
    assert out["vae"][0] == "5"


def test_cond_inject_success_rewires_and_preserves_input(monkeypatch):
    monkeypatch.setattr(
        _sie, "_return_types", lambda ct: ["VAE"] if ct == "TestVAENode" else None
    )
    prompt = {
        "1": {
            "class_type": "KSampler",
            "inputs": {
                "positive": ["2", 0],
                "negative": ["3", 0],
                "latent_image": ["4", 0],
                "seed": 1,
            },
        },
        "2": {"class_type": "OtherNode", "inputs": {}},
        "3": {"class_type": "OtherNode", "inputs": {}},
        "4": {"class_type": "OtherNode", "inputs": {}},
        "5": {"class_type": "TestVAENode", "inputs": {}},
    }
    before = _copy.deepcopy(prompt)
    new_prompt, diagnostics = inject_inpaint_conditioning(
        prompt, source_file="src.png", mask_file="mask.png"
    )
    assert prompt == before
    assert new_prompt is not prompt
    assert len(new_prompt) == len(prompt) + 4
    assert diagnostics["injected_nodes"] == {
        "load_source": "6",
        "load_mask": "7",
        "to_mask": "8",
        "conditioning": "9",
    }
    assert new_prompt["6"] == {
        "class_type": "LoadImage",
        "inputs": {"image": "src.png"},
    }
    assert new_prompt["7"] == {
        "class_type": "LoadImage",
        "inputs": {"image": "mask.png"},
    }
    assert new_prompt["8"] == {
        "class_type": "ImageToMask",
        "inputs": {"image": ["7", 0], "channel": "red"},
    }
    assert new_prompt["9"] == {
        "class_type": "InpaintModelConditioning",
        "inputs": {
            "positive": ["2", 0],
            "negative": ["3", 0],
            "vae": ["5", 0],
            "pixels": ["6", 0],
            "mask": ["8", 0],
            "noise_mask": True,
        },
    }
    sampler_inputs = new_prompt["1"]["inputs"]
    assert sampler_inputs["positive"] == ["9", 0]
    assert sampler_inputs["negative"] == ["9", 1]
    assert sampler_inputs["latent_image"] == ["9", 2]
    assert sampler_inputs["seed"] == 1
    assert diagnostics["sampler_id"] == "1"
    assert diagnostics["positive_from"] == ["2", 0]
    assert diagnostics["negative_from"] == ["3", 0]
    assert diagnostics["latent_from"] == ["4", 0]
    assert diagnostics["vae_from"] == ["5", 0]
    assert diagnostics["source_file"] == "src.png"
    assert diagnostics["mask_file"] == "mask.png"
    assert diagnostics["noise_mask"] is True


def test_cond_inject_incompatible_raises(monkeypatch):
    monkeypatch.setattr(_sie, "_return_types", lambda ct: None)
    prompt = {"1": {"class_type": "OtherNode", "inputs": {}}}
    before = _copy.deepcopy(prompt)
    with pytest.raises(ValueError, match="INPAINT-COND-01"):
        inject_inpaint_conditioning(
            prompt, source_file="src.png", mask_file="mask.png"
        )
    assert prompt == before


def test_cond_inject_bad_filenames_raise(monkeypatch):
    monkeypatch.setattr(
        _sie, "_return_types", lambda ct: ["VAE"] if ct == "TestVAENode" else None
    )
    prompt = {
        "1": {
            "class_type": "KSampler",
            "inputs": {
                "positive": ["2", 0],
                "negative": ["3", 0],
                "latent_image": ["4", 0],
            },
        },
        "2": {"class_type": "OtherNode", "inputs": {}},
        "3": {"class_type": "OtherNode", "inputs": {}},
        "4": {"class_type": "OtherNode", "inputs": {}},
        "5": {"class_type": "TestVAENode", "inputs": {}},
    }
    with pytest.raises(ValueError):
        inject_inpaint_conditioning(prompt, source_file="", mask_file="m.png")
    with pytest.raises(ValueError):
        inject_inpaint_conditioning(prompt, source_file="s.png", mask_file="")
    with pytest.raises(ValueError):
        inject_inpaint_conditioning(prompt, source_file=None, mask_file="m.png")


# ---------------------------------------------------------------------------
# Phase-3 explicit-method orchestration (append-only tests; above untouched).
# Exercises studio_workflow_run._sanitize_studio_method, _method_wh_overrides,
# _prepare_studio_method and _apply_studio_method_post with real PNG files in
# tmp dirs. No product code is touched; file I/O is monkeypatched to tmp_path.
# ---------------------------------------------------------------------------
import os as _os
import shutil as _shutil
from pathlib import Path as _Path

import local_artifacts as _local_artifacts
import studio_workflow_run as _swr
from studio_workflow_run import (
    _apply_studio_method_post,
    _method_wh_overrides,
    _prepare_studio_method,
    _sanitize_studio_method,
)


def _phase3_input_dir(monkeypatch, tmp_path):
    """Route _method_input_path at tmp_path (missing names raise ValueError)."""

    def _resolve(name):
        candidate = tmp_path / str(name)
        if not candidate.is_file():
            raise ValueError(f"image {name!r} not found on server")
        return str(candidate)

    monkeypatch.setattr(_swr, "_method_input_path", _resolve)
    return tmp_path


def _phase3_outputs_dir(monkeypatch, tmp_path):
    out = tmp_path / "studio-outputs"
    out.mkdir(exist_ok=True)
    monkeypatch.setattr(_local_artifacts, "get_studio_outputs_dir", lambda: out)
    return out


def _phase3_write_src_mask(tmp_path, size=(64, 64), rect=(20, 20, 40, 30)):
    from PIL import ImageDraw

    src = tmp_path / "src.png"
    msk = tmp_path / "mask.png"
    Image.new("RGB", size, (10, 20, 30)).save(src)
    mask_img = Image.new("L", size, 0)
    ImageDraw.Draw(mask_img).rectangle(rect, fill=255)
    mask_img.save(msk)
    return "src.png", "mask.png"


def _phase3_bundle(schema):
    return {"control_schema": dict(schema), "version": {"executable_prompt": {}}}


def _phase3_wh_schema():
    return {"width": {"type": "int"}, "height": {"type": "int"}}


def test_phase3_sanitize_none_and_non_dict():
    assert _sanitize_studio_method(None) == (None, None)
    method, error = _sanitize_studio_method("crop_stitch")
    assert method is None
    assert error and "must be an object" in error
    method, error = _sanitize_studio_method(["inpaint"])
    assert method is None and error


def test_phase3_sanitize_unknown_kind_and_method():
    method, error = _sanitize_studio_method(
        {"kind": "upscale", "method": "x", "params": {}}
    )
    assert method is None
    assert error and "unknown studio method kind" in error
    method, error = _sanitize_studio_method(
        {"kind": "inpaint", "method": "pad", "params": {"mask_file": "m.png"}}
    )
    assert method is None
    assert error and "unknown inpaint method" in error
    method, error = _sanitize_studio_method(
        {"kind": "expand", "method": "crop_stitch", "params": {"top": 1}}
    )
    assert method is None
    assert error and "unknown expand method" in error


def test_phase3_sanitize_expand_all_zero_pads_error():
    raw = {
        "kind": "expand",
        "method": "pad",
        "params": {"top": 0, "right": 0, "bottom": 0, "left": 0},
    }
    method, error = _sanitize_studio_method(raw)
    assert method is None
    assert error and "no expansion requested" in error


def test_phase3_sanitize_expand_negative_and_bool_pad_error():
    for bad in (-1, True, 1.5, "8"):
        raw = {
            "kind": "expand",
            "method": "pad_preserve",
            "params": {"top": bad, "right": 8, "bottom": 0, "left": 0},
        }
        method, error = _sanitize_studio_method(raw)
        assert method is None, bad
        assert error and "non-negative int" in error, bad


def test_phase3_sanitize_expand_valid_shape():
    raw = {
        "kind": "expand",
        "method": "pad_preserve",
        "params": {"top": 4, "right": 8, "bottom": 0, "left": 6, "zzz": 1},
        "bogus": "stripped",
    }
    method, error = _sanitize_studio_method(raw)
    assert error is None
    assert method == {
        "kind": "expand",
        "method": "pad_preserve",
        "params": {"top": 4, "right": 8, "bottom": 0, "left": 6},
        "override": "",
    }


def test_phase3_sanitize_inpaint_without_mask_errors():
    for kind_method in ("crop_stitch", "conditioning"):
        method, error = _sanitize_studio_method(
            {"kind": "inpaint", "method": kind_method, "params": {}}
        )
        assert method is None
        assert error and "mask" in error
        method, error = _sanitize_studio_method(
            {"kind": "inpaint", "method": kind_method, "params": {"mask_file": "  "}}
        )
        assert method is None
        assert error and "mask" in error
        method, error = _sanitize_studio_method(
            {"kind": "inpaint", "method": kind_method}
        )
        assert method is None
        assert error and "mask" in error


def test_phase3_sanitize_inpaint_valid_shapes_strip_unknown_keys():
    for kind_method in ("crop_stitch", "conditioning"):
        method, error = _sanitize_studio_method(
            {
                "kind": "inpaint",
                "method": kind_method,
                "params": {"mask_file": " m.png ", "zzz": 9},
                "override": "ignored-unless-dedicated",
                "bogus": [1],
            }
        )
        assert error is None
        assert method == {
            "kind": "inpaint",
            "method": kind_method,
            "params": {"mask_file": "m.png"},
            "override": "",
        }


def test_phase3_sanitize_dedicated_without_override_errors():
    for kind in ("inpaint", "expand"):
        params = {"mask_file": "m.png"} if kind == "inpaint" else {
            "top": 0, "right": 4, "bottom": 0, "left": 0,
        }
        method, error = _sanitize_studio_method(
            {"kind": kind, "method": "dedicated", "params": params}
        )
        assert method is None
        assert error and "dedicated workflow" in error
        method, error = _sanitize_studio_method(
            {"kind": kind, "method": "dedicated", "params": params, "override": "  "}
        )
        assert method is None
        assert error and "dedicated workflow" in error


def test_phase3_sanitize_dedicated_valid_shapes():
    method, error = _sanitize_studio_method(
        {
            "kind": "inpaint",
            "method": "dedicated",
            "params": {"mask_file": "m.png"},
            "override": " wf_x ",
        }
    )
    assert error is None
    assert method is not None
    assert method == {
        "kind": "inpaint",
        "method": "dedicated",
        "params": {"mask_file": "m.png"},
        "override": "wf_x",
    }
    method, error = _sanitize_studio_method(
        {
            "kind": "expand",
            "method": "dedicated",
            "params": {"top": 0, "right": 4, "bottom": 0, "left": 0},
            "override": "wf_y",
        }
    )
    assert error is None
    assert method is not None
    assert method["override"] == "wf_y"
    # Pads are meaningless for a dedicated override (it brings its own
    # expansion): they are stripped, and no pads are required at all.
    assert method["params"] == {}
    method, error = _sanitize_studio_method(
        {"kind": "expand", "method": "dedicated", "params": {}, "override": "wf_y"}
    )
    assert error is None
    assert method is not None
    assert method["params"] == {}


def test_phase3_wh_overrides_both_roles():
    assert _method_wh_overrides(_phase3_wh_schema(), 40, 30) == {
        "width": 40,
        "height": 30,
    }


def test_phase3_wh_overrides_missing_either_role():
    assert _method_wh_overrides({"width": {}}, 40, 30) == {}
    assert _method_wh_overrides({"height": {}}, 40, 30) == {}
    assert _method_wh_overrides({}, 40, 30) == {}


def test_phase3_wh_overrides_non_dict_schema():
    assert _method_wh_overrides(None, 40, 30) == {}
    assert _method_wh_overrides([], 40, 30) == {}
    assert _method_wh_overrides("width", 40, 30) == {}


def test_phase3_prepare_inpaint_crop_new_temp_files(monkeypatch, tmp_path):
    _phase3_input_dir(monkeypatch, tmp_path)
    src, msk = _phase3_write_src_mask(tmp_path)
    bundle = _phase3_bundle(_phase3_wh_schema())
    method, error = _sanitize_studio_method(
        {"kind": "inpaint", "method": "crop_stitch", "params": {"mask_file": msk}}
    )
    assert error is None
    values = {"source_image": src, "mask": msk, "prompt": "x"}
    out = _prepare_studio_method(bundle, values, method)
    assert "error" not in out, out.get("error")
    merged, ctx = out["merged_values"], out["ctx"]
    # Merged source/mask are NEW temp files (never the uploaded names).
    assert merged["source_image"] != src
    assert merged["source_image"].startswith("studio-method-")
    assert (tmp_path / merged["source_image"]).is_file()
    assert ctx["crop_source"] == merged["source_image"]
    assert ctx["crop_mask"] != msk
    assert (tmp_path / ctx["crop_mask"]).is_file()
    # The mapped mask role is stripped from the merged values.
    assert "mask" not in merged
    # Crop box is square and the wh override matches it.
    box = ctx["box"]
    assert box[2] - box[0] == box[3] - box[1] > 0
    assert merged["width"] == box[2] - box[0]
    assert merged["height"] == box[3] - box[1]
    assert ctx["wh_overridden"] is True
    assert ctx["mask_file"] == msk and ctx["source_file"] == src
    # Caller inputs are never mutated.
    assert values == {"source_image": src, "mask": msk, "prompt": "x"}


def test_phase3_prepare_inpaint_no_wh_schema(monkeypatch, tmp_path):
    _phase3_input_dir(monkeypatch, tmp_path)
    src, msk = _phase3_write_src_mask(tmp_path)
    bundle = _phase3_bundle({})
    method, error = _sanitize_studio_method(
        {"kind": "inpaint", "method": "conditioning", "params": {"mask_file": msk}}
    )
    assert error is None
    out = _prepare_studio_method(bundle, {"source_image": src}, method)
    assert "error" not in out
    assert "width" not in out["merged_values"]
    assert "height" not in out["merged_values"]
    assert out["ctx"]["wh_overridden"] is False


def test_phase3_prepare_inpaint_empty_mask_errors(monkeypatch, tmp_path):
    _phase3_input_dir(monkeypatch, tmp_path)
    src = tmp_path / "src.png"
    Image.new("RGB", (32, 32), (1, 2, 3)).save(src)
    Image.new("L", (32, 32), 0).save(tmp_path / "empty.png")
    bundle = _phase3_bundle({})
    method, error = _sanitize_studio_method(
        {"kind": "inpaint", "method": "crop_stitch", "params": {"mask_file": "empty.png"}}
    )
    assert error is None
    out = _prepare_studio_method(bundle, {"source_image": "src.png"}, method)
    assert "error" in out and "empty" in out["error"]


def test_phase3_prepare_missing_file_errors(monkeypatch, tmp_path):
    _phase3_input_dir(monkeypatch, tmp_path)
    src = tmp_path / "src.png"
    Image.new("RGB", (32, 32), (1, 2, 3)).save(src)
    bundle = _phase3_bundle({})
    method, error = _sanitize_studio_method(
        {"kind": "inpaint", "method": "crop_stitch", "params": {"mask_file": "gone.png"}}
    )
    assert error is None
    out = _prepare_studio_method(bundle, {"source_image": "src.png"}, method)
    assert "error" in out and "not found" in out["error"]
    out = _prepare_studio_method(bundle, {}, method)
    assert "error" in out and "source image" in out["error"]


def test_phase3_prepare_expand_pad_dims_and_origin(monkeypatch, tmp_path):
    _phase3_input_dir(monkeypatch, tmp_path)
    src_path = tmp_path / "src.png"
    Image.new("RGB", (32, 24), (9, 9, 9)).save(src_path)
    bundle = _phase3_bundle(_phase3_wh_schema())
    method, error = _sanitize_studio_method(
        {
            "kind": "expand",
            "method": "pad",
            "params": {"top": 4, "right": 8, "bottom": 2, "left": 6},
        }
    )
    assert error is None
    out = _prepare_studio_method(bundle, {"source_image": "src.png"}, method)
    assert "error" not in out, out.get("error")
    merged, ctx = out["merged_values"], out["ctx"]
    assert merged["source_image"] != "src.png"
    padded = Image.open(tmp_path / merged["source_image"])
    assert padded.size == (32 + 8 + 6, 24 + 4 + 2)
    assert ctx["padded_size"] == [46, 30]
    assert ctx["origin"] == [6, 4]
    assert merged["width"] == 46 and merged["height"] == 30
    assert ctx["wh_overridden"] is True


def test_phase3_post_crop_stitch_identity(monkeypatch, tmp_path):
    _phase3_input_dir(monkeypatch, tmp_path)
    out_dir = _phase3_outputs_dir(monkeypatch, tmp_path)
    src, msk = _phase3_write_src_mask(tmp_path)
    bundle = _phase3_bundle(_phase3_wh_schema())
    method, error = _sanitize_studio_method(
        {"kind": "inpaint", "method": "crop_stitch", "params": {"mask_file": msk}}
    )
    assert error is None
    prep = _prepare_studio_method(bundle, {"source_image": src}, method)
    assert "error" not in prep
    ctx = prep["ctx"]
    orig = Image.open(tmp_path / src).convert("RGB")
    box = tuple(ctx["box"])
    gen_path = tmp_path / "gen.png"
    orig.crop(box).save(gen_path)
    normalized = {"primary_output": {"path": str(gen_path)}, "trace": {}}
    capture = {"materialized_paths": [str(gen_path)]}
    normalized2, capture2 = _apply_studio_method_post(normalized, capture, ctx, bundle)
    finals = capture2["materialized_paths"]
    assert len(finals) == 1
    assert _Path(finals[0]).parent == out_dir
    final = Image.open(finals[0]).convert("RGB")
    assert final.size == orig.size
    assert np.array_equal(np.asarray(final), np.asarray(orig))
    assert normalized2["primary_output"]["path"] == finals[0]
    diag = normalized2["trace"]["studio_method"]
    assert diag["kind"] == "inpaint" and diag["method"] == "crop_stitch"
    assert capture2["studio_method"]["stored_hash_unchanged"] is True
    assert capture2["studio_method"]["method"] == "crop_stitch"


def test_phase3_post_pad_preserve_restores_center(monkeypatch, tmp_path):
    _phase3_input_dir(monkeypatch, tmp_path)
    out_dir = _phase3_outputs_dir(monkeypatch, tmp_path)
    rng = np.random.RandomState(7)
    orig_arr = rng.randint(0, 256, size=(48, 48, 3)).astype(np.uint8)
    Image.fromarray(orig_arr, mode="RGB").save(tmp_path / "src.png")
    bundle = _phase3_bundle({})
    method, error = _sanitize_studio_method(
        {
            "kind": "expand",
            "method": "pad_preserve",
            "params": {"top": 0, "right": 16, "bottom": 16, "left": 0},
        }
    )
    assert error is None
    prep = _prepare_studio_method(bundle, {"source_image": "src.png"}, method)
    assert "error" not in prep
    ctx = prep["ctx"]
    assert ctx["padded_size"] == [64, 64]
    result_path = tmp_path / "result.png"
    _shutil.copy(tmp_path / prep["merged_values"]["source_image"], result_path)
    normalized = {"trace": {}}
    capture = {"materialized_paths": [str(result_path)]}
    normalized2, capture2 = _apply_studio_method_post(normalized, capture, ctx, bundle)
    finals = capture2["materialized_paths"]
    assert len(finals) == 1 and _Path(finals[0]).parent == out_dir
    final = np.asarray(Image.open(finals[0]).convert("RGB"))
    assert final.shape == (64, 64, 3)
    feather = max(8, 48 // 64)
    margin = feather + 2
    assert np.array_equal(
        final[margin:48 - margin, margin:48 - margin], orig_arr[margin:48 - margin, margin:48 - margin]
    )
    assert capture2["studio_method"]["stored_hash_unchanged"] is True


def test_phase3_post_pad_resizes_mismatch(monkeypatch, tmp_path):
    _phase3_input_dir(monkeypatch, tmp_path)
    out_dir = _phase3_outputs_dir(monkeypatch, tmp_path)
    Image.new("RGB", (32, 24), (4, 5, 6)).save(tmp_path / "src.png")
    bundle = _phase3_bundle({})
    method, error = _sanitize_studio_method(
        {
            "kind": "expand",
            "method": "pad",
            "params": {"top": 4, "right": 8, "bottom": 2, "left": 6},
        }
    )
    assert error is None
    prep = _prepare_studio_method(bundle, {"source_image": "src.png"}, method)
    assert "error" not in prep
    ctx = prep["ctx"]
    small = tmp_path / "small.png"
    Image.new("RGB", (8, 8), (200, 10, 10)).save(small)
    normalized = {"primary_output": {"path": str(small)}, "trace": {}}
    capture = {"materialized_paths": [str(small)]}
    normalized2, capture2 = _apply_studio_method_post(normalized, capture, ctx, bundle)
    finals = capture2["materialized_paths"]
    assert len(finals) == 1 and _Path(finals[0]).parent == out_dir
    assert Image.open(finals[0]).size == (46, 30)
    assert normalized2["primary_output"]["path"] == finals[0]
    assert capture2["studio_method"]["resized_result"] is True


def test_phase3_post_missing_result_errors(monkeypatch, tmp_path):
    _phase3_input_dir(monkeypatch, tmp_path)
    _phase3_outputs_dir(monkeypatch, tmp_path)
    ctx = {
        "kind": "expand",
        "method": "pad",
        "padded_size": [10, 10],
        "stored_hash": "",
    }
    with pytest.raises(ValueError, match="no readable image"):
        _apply_studio_method_post(
            {}, {"materialized_paths": [str(tmp_path / "nope.png")]}, ctx, {}
        )


def test_phase3_sanitize_dedicated_inpaint_without_mask_errors():
    method, error = _sanitize_studio_method(
        {"kind": "inpaint", "method": "dedicated", "params": {}, "override": "wf_x"}
    )
    assert method is None
    assert error and "mask" in error
    method, error = _sanitize_studio_method(
        {
            "kind": "inpaint",
            "method": "dedicated",
            "params": {"mask_file": "  "},
            "override": "wf_x",
        }
    )
    assert method is None
    assert error and "mask" in error


def test_phase3_tolerated_base_errors_drops_only_mask():
    tolerated = _swr._tolerated_method_base_errors
    errors = [
        {"field": "mask", "message": "required control 'mask' must not be empty"},
        {"field": "mask", "message": "missing required control 'mask'"},
        {"field": "prompt", "message": "required control 'prompt' must not be empty"},
    ]
    method, error = _sanitize_studio_method(
        {
            "kind": "inpaint",
            "method": "dedicated",
            "params": {"mask_file": "m.png"},
            "override": "wf_x",
        }
    )
    assert error is None
    kept = tolerated(errors, method)
    assert [e["field"] for e in kept] == ["prompt"]
    # No method (plain run): nothing tolerated.
    assert tolerated(errors, None) == errors
    # Expand methods never carry a mask: nothing tolerated.
    expand, error = _sanitize_studio_method(
        {
            "kind": "expand",
            "method": "pad",
            "params": {"top": 0, "right": 4, "bottom": 0, "left": 0},
        }
    )
    assert error is None
    assert tolerated(errors, expand) == errors


def test_phase3_transfer_values_seeds_method_mask():
    seed = _swr._transfer_values_with_method_mask
    method, error = _sanitize_studio_method(
        {
            "kind": "inpaint",
            "method": "dedicated",
            "params": {"mask_file": "m.png"},
            "override": "wf_x",
        }
    )
    assert error is None
    out = seed({"prompt": "p", "source_image": "s.png"}, method)
    assert out["mask"] == "m.png"
    assert out["prompt"] == "p"
    # An explicitly merged mask is never overwritten.
    out2 = seed({"mask": "live.png"}, method)
    assert out2["mask"] == "live.png"
    # Plain runs pass values through untouched.
    assert seed({"prompt": "p"}, None) == {"prompt": "p"}


def test_phase3_transfer_values_defuse_cross_graph_links():
    seed = _swr._transfer_values_with_method_mask
    method, error = _sanitize_studio_method(
        {
            "kind": "inpaint",
            "method": "dedicated",
            "params": {"mask_file": "m.png"},
            "override": "wf_x",
        }
    )
    assert error is None
    # A link-form seed (["node_id", slot]) is graph-local: it must not be
    # carried to the override graph (where the node id may be a Prompt
    # node). It becomes a fresh random scalar instead.
    out = seed({"prompt": "p", "seed": ["8", 0]}, method)
    assert isinstance(out["seed"], int) and not isinstance(out["seed"], bool)
    assert 0 <= out["seed"] <= 2**32 - 1
    assert out["mask"] == "m.png"
    # A scalar seed transfers verbatim (reproducible override runs).
    out2 = seed({"prompt": "p", "seed": 8}, method)
    assert out2["seed"] == 8
    # Other link-form roles are dropped so the override default applies.
    out3 = seed({"prompt": ["8", 0], "seed": 7}, method)
    assert "prompt" not in out3
    assert out3["seed"] == 7
