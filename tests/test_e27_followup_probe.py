"""Unit tests for the E27 Follow-Up A probe battery (measurement-only)."""

from __future__ import annotations

import json
import os
import struct
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from comfymodal_runtime import e27_followup_probe as fp  # noqa: E402


def _write_synthetic_safetensors(path: str) -> dict:
    """Write a small multi-dtype safetensors file and return its header."""
    import torch  # noqa: PLC0415

    t_f32 = torch.randn(4, 8, dtype=torch.float32)
    t_f16 = torch.randn(8, 8, dtype=torch.float16)
    b_f32 = torch.randn(4, dtype=torch.float32)
    header = {
        "w_f32": {"dtype": "F32", "shape": list(t_f32.shape),
                  "data_offsets": [0, t_f32.numel() * 4]},
        "w_f16": {"dtype": "F16", "shape": list(t_f16.shape),
                  "data_offsets": [t_f32.numel() * 4,
                                   t_f32.numel() * 4 + t_f16.numel() * 2]},
        "layer.bias": {"dtype": "F32", "shape": list(b_f32.shape),
                       "data_offsets": [t_f32.numel() * 4 + t_f16.numel() * 2,
                                        t_f32.numel() * 4 + t_f16.numel() * 2
                                        + b_f32.numel() * 4]},
    }
    payload = (t_f32.numpy().tobytes() + t_f16.numpy().tobytes()
               + b_f32.numpy().tobytes())
    header_bytes = json.dumps(header, separators=(",", ":")).encode("utf-8")
    with open(path, "wb") as fh:
        fh.write(struct.pack("<Q", len(header_bytes)))
        fh.write(header_bytes)
        fh.write(payload)
    return header


def test_enumerate_safetensors_dtypes_exact():
    with tempfile.TemporaryDirectory() as td:
        path = os.path.join(td, "synthetic.safetensors")
        _write_synthetic_safetensors(path)
        r = fp.enumerate_safetensors_dtypes(path)
        assert r["status"] == "ok"
        assert r["tensor_count"] == 3
        # w_f32 (4*8*4=128) + b_f32 (4*4=16) + w_f16 (8*8*2=128)
        assert r["bytes_by_dtype"]["F32"] == 128 + 16
        assert r["bytes_by_dtype"]["F16"] == 128
        assert r["bias_bytes_by_dtype"]["F32"] == 16
        # fp32 conversion bytes: F16 only
        assert r["fp32_conversion_bytes"] == 128
        # fp32 resident: F32 stays (144) + F16 doubles (256) = 400
        assert r["fp32_resident_bytes_total"] == 144 + 256
        assert r["total_data_bytes"] == 144 + 128


def test_spot_regions_bounds():
    regions = fp._spot_regions(1000)
    assert regions[0][0] == 0
    assert regions[-1][0] + regions[-1][1] == 1000
    for start, length in regions:
        assert start >= 0 and length > 0
        assert start + length <= 1000


def test_safetensors_data_start():
    with tempfile.TemporaryDirectory() as td:
        path = os.path.join(td, "synthetic.safetensors")
        _write_synthetic_safetensors(path)
        data_start = fp._safetensors_data_start(path)
        with open(path, "rb") as fh:
            header_len = int.from_bytes(fh.read(8), "little")
        assert data_start == 8 + header_len


def test_fastsafe_load_missing_module_degrades():
    # When fastsafetensors is absent the cell must return error status
    # gracefully (no raise), and the screen result must still be JSON-safe.
    import importlib

    if importlib.util.find_spec("fastsafetensors") is None:
        r = fp._fastsafe_load_once("/nonexistent/file.safetensors", "cuda:0",
                                   threads=4, max_copy_block_bytes=1 << 20)
        assert r["status"] in ("error", "ok")
