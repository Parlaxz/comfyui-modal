"""FAST_UNIT tests for the UNET quant_fp8 source plan builder.

CPU-only, synthetic header entries (no files, no GPU): covers admission
shape (specs, quant-layer association, growth math) and every fail-closed
rejection.  The stage consumes the plan live, never here.
"""

from __future__ import annotations

import json

import pytest

torch = pytest.importorskip("torch")

from comfymodal_runtime import golden_serial as gs


pytestmark = pytest.mark.fast_unit


def _entries():
    return [
        ("blk.weight", "F8_E4M3", (32, 48), 0, 1536),
        ("blk.weight_scale", "F32", (1,), 1536, 4),
        ("blk.bias", "F32", (32,), 1540, 128),
        ("norm.weight", "BF16", (48,), 1668, 96),
    ]


def _metadata():
    return {"_quantization_metadata": json.dumps({"layers": {
        "blk": {"format": "float8_e4m3fn"},
    }})}


class TestBuildQuantFp8SourcePlan:
    def test_admits_mixed_fp8_file(self):
        plan = gs.build_quant_fp8_source_plan(_entries(), _metadata())
        assert plan["kind"] == "scaled_fp8"
        specs = plan["source_specs"]
        # Weights AND buffers admitted; artifacts excluded.
        assert set(specs) == {"blk.weight", "blk.bias", "norm.weight"}
        assert specs["blk.weight"]["shape"] == (32, 48)
        # Proof dtype is post-normalization truth; source dtype kept.
        assert specs["blk.weight"]["torch_dtype"] == torch.bfloat16
        assert specs["blk.weight"]["source_dtype_name"] == "F8_E4M3"
        assert specs["blk.bias"]["torch_dtype"] == torch.float32
        assert plan["quant_layers"]["blk"]["scale_keys"] == [
            "blk.weight_scale"]
        assert plan["quant_layers"]["blk"]["weight_keys"] == [
            "blk.bias", "blk.weight"]
        assert plan["dropped_quant_keys"] == ["blk.weight_scale"]
        # 1536 F8 bytes -> 1536 bytes growth doubling to BF16.
        assert plan["expected_growth_bytes"] == 1536
        assert plan["normalized_compute_dtype"] == "bfloat16"

    def test_legacy_scale_keys_without_metadata(self):
        entries = [
            ("blk.weight", "F8_E4M3", (16, 16), 0, 256),
            ("blk.scale_weight", "F32", (1,), 256, 4),
        ]
        plan = gs.build_quant_fp8_source_plan(entries, {})
        assert plan["quant_layers"]["blk"]["scale_keys"] == [
            "blk.scale_weight"]
        assert set(plan["source_specs"]) == {"blk.weight"}

    def test_no_fp8_rejected(self):
        entries = [("a.weight", "BF16", (4, 4), 0, 32)]
        with pytest.raises(RuntimeError, match="unet_quant_plan_no_fp8"):
            gs.build_quant_fp8_source_plan(entries, {})

    def test_bad_dtype_rejected(self):
        entries = [("a.weight", "NOPE", (4, 4), 0, 32)]
        with pytest.raises(RuntimeError, match="unet_source_plan_dtype"):
            gs.build_quant_fp8_source_plan(entries, {})

    def test_duplicate_keys_rejected(self):
        entries = [("a.weight", "F8_E4M3", (4, 4), 0, 16),
                   ("a.weight", "F8_E4M3", (4, 4), 16, 16)]
        with pytest.raises(RuntimeError, match="unet_source_plan_key"):
            gs.build_quant_fp8_source_plan(entries, {})

    def test_zero_length_rejected(self):
        entries = [("a.weight", "F8_E4M3", (4, 4), 0, 0)]
        with pytest.raises(RuntimeError, match="unet_source_plan_zero"):
            gs.build_quant_fp8_source_plan(entries, {})

    def test_descriptor_payload_rejected(self):
        entries = [("a.weight", "F8_E4M3", (4, 4), 0, 16),
                   ("a.comfy_quant", "U8", (10,), 16, 10)]
        with pytest.raises(RuntimeError, match="descriptor_payload"):
            gs.build_quant_fp8_source_plan(entries, {})

    def test_garbage_rejected(self):
        with pytest.raises(RuntimeError):
            gs.build_quant_fp8_source_plan(None, None)
        with pytest.raises(RuntimeError):
            gs.build_quant_fp8_source_plan([("only",)], None)
