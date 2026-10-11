"""FAST_UNIT tests for selective FP8->BF16 upcast (generic shape rule).

CPU-only.  Covers the alignment rule, the state-dict transform (scale
folding, quant-artifact removal, metadata scrub), the fail-safe revert,
the env kill-switch, and the log guard installer.  Loaders themselves are
exercised live, never here.
"""

from __future__ import annotations

import json
import logging
import os

import pytest

torch = pytest.importorskip("torch")

from comfymodal_runtime import golden_generic_loaders as ggl


pytestmark = pytest.mark.fast_unit


def _f8(*shape):
    return torch.empty(*shape, dtype=torch.float8_e4m3fn)


def _quant_descriptor():
    return torch.tensor(list(b'{"format": "float8_e4m3fn"}'),
                        dtype=torch.uint8)


def _make_sd():
    return {
        # Hostile N (3396 % 16 != 0): must upcast.
        "blk.bad.weight": _f8(64, 3396),
        "blk.bad.weight_scale": torch.tensor(2.0),
        "blk.bad.input_scale": torch.tensor(1.0),
        "blk.bad.comfy_quant": _quant_descriptor(),
        # Legacy scale-key scheme (pre-convert UNET sd): must upcast.
        "blk.old.weight": _f8(48, 283),
        "blk.old.scale_weight": torch.tensor(0.5),
        # Aligned: must stay FP8.
        "blk.good.weight": _f8(64, 256),
        "blk.good.weight_scale": torch.tensor(3.0),
        "blk.good.comfy_quant": _quant_descriptor(),
        # Non-FP8: untouched.
        "blk.plain.weight": torch.zeros(64, 256, dtype=torch.bfloat16),
        "blk.bias": torch.zeros(64),
    }


def _make_metadata():
    return {"_quantization_metadata": json.dumps({"layers": {
        "blk.bad": {"format": "float8_e4m3fn"},
        "blk.old": {"format": "float8_e4m3fn"},
        "blk.good": {"format": "float8_e4m3fn"},
    }})}


class TestFp8NativeShapeOk:
    def test_aligned(self):
        assert ggl._fp8_native_shape_ok((2560, 2560)) is True
        assert ggl._fp8_native_shape_ok((6144, 6144, 3, 3)) is True

    def test_hostile_live_shapes(self):
        assert ggl._fp8_native_shape_ok((2560, 3396)) is False
        assert ggl._fp8_native_shape_ok((2560, 283)) is False
        assert ggl._fp8_native_shape_ok((6144, 4379)) is False

    def test_non_matrix_and_garbage_fail_safe(self):
        assert ggl._fp8_native_shape_ok((64,)) is True
        assert ggl._fp8_native_shape_ok(None) is True
        assert ggl._fp8_native_shape_ok("nope") is True


class TestSelectiveUpcast:
    def test_upcasts_hostile_leaves_aligned(self):
        sd = _make_sd()
        out, meta, report = ggl.selective_fp8_bf16_upcast(sd, _make_metadata())
        assert report["enabled"] is True
        assert report["upcast_count"] == 2
        assert report["reverted"] == []
        # Hostile layers: BF16, artifacts gone.
        for prefix in ("blk.bad", "blk.old"):
            assert out[prefix + ".weight"].dtype == torch.bfloat16
            for suffix in ggl._FP8_QUANT_SUFFIXES:
                assert prefix + suffix not in out
        # Aligned FP8: untouched, descriptor retained.
        assert out["blk.good.weight"].dtype == torch.float8_e4m3fn
        assert "blk.good.comfy_quant" in out
        # Plain tensors: untouched.
        assert out["blk.plain.weight"].dtype == torch.bfloat16
        # Metadata scrubbed of upcast layers only.
        layers = json.loads(meta["_quantization_metadata"])["layers"]
        assert "blk.bad" not in layers
        assert "blk.old" not in layers
        assert "blk.good" in layers

    def test_scale_folding_math(self):
        sd = _make_sd()
        expected = (sd["blk.bad.weight"].to(torch.bfloat16)
                    * sd["blk.bad.weight_scale"].to(torch.bfloat16))
        out, _, _ = ggl.selective_fp8_bf16_upcast(sd, _make_metadata())
        assert torch.equal(out["blk.bad.weight"], expected)

    def test_env_kill_switch(self, monkeypatch):
        monkeypatch.setenv(ggl._FP8_SELECTIVE_UPCAST_ENV, "0")
        sd = _make_sd()
        out, _, report = ggl.selective_fp8_bf16_upcast(sd, _make_metadata())
        assert report["enabled"] is False
        assert report["upcast_count"] == 0
        assert out["blk.bad.weight"].dtype == torch.float8_e4m3fn
        assert "blk.bad.comfy_quant" in out

    def test_no_metadata_still_upcasts_with_insd_pops(self):
        sd = _make_sd()
        out, _, report = ggl.selective_fp8_bf16_upcast(sd, None)
        assert report["upcast_count"] == 2
        assert out["blk.bad.weight"].dtype == torch.bfloat16

    def test_never_raises_on_garbage(self):
        _, _, report = ggl.selective_fp8_bf16_upcast(None, None)
        assert report["upcast_count"] == 0
        _, _, report = ggl.selective_fp8_bf16_upcast("nope", 42)
        assert report["enabled"] in (True, False)


class TestLogGuard:
    def test_install_idempotent_and_caps(self):
        assert ggl._install_fp8_fallback_log_guard() is True
        assert ggl._install_fp8_fallback_log_guard() is True
        logger = logging.getLogger("comfy_kitchen.tensor.fp8")
        assert len(logger.filters) >= 1

        def _passes(msg):
            rec = logging.LogRecord("comfy_kitchen.tensor.fp8",
                                    logging.WARNING, __file__, 1,
                                    msg, None, None)
            return all(f.filter(rec) for f in logger.filters)

        spam = ("FP8 _scaled_mm failed: falling back to dequantization",)
        ggl._fp8_log_guard_drops = 0
        assert [_passes(spam) for _ in range(5)] == [True] * 5
        assert _passes(spam) is False
        assert _passes("something else") is True
