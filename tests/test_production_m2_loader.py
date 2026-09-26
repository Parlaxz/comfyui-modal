from __future__ import annotations

import json
import struct

import pytest

from comfymodal_runtime.production_m2_loader import (
    build_header_tensor_map,
    parse_safetensors_header,
)


pytestmark = pytest.mark.fast_unit


def _write_safetensors(path, header, payload=b"\x00" * 8):
    encoded = json.dumps(header, separators=(",", ":")).encode("utf-8")
    path.write_bytes(struct.pack("<Q", len(encoded)) + encoded + payload)


def test_parse_header_uses_offsets_relative_to_data_section(tmp_path):
    path = tmp_path / "clip.safetensors"
    header = {
        "weight": {"dtype": "F32", "shape": [2], "data_offsets": [0, 8]},
        "__metadata__": {"format": "pt"},
    }
    _write_safetensors(path, header)

    parsed, data_start, data_bytes = parse_safetensors_header(str(path))

    assert parsed["weight"]["data_offsets"] == [0, 8]
    assert data_start > 8
    assert data_bytes == 8
    assert build_header_tensor_map(parsed) == [
        {"key": "weight", "dtype": "F32", "shape": [2], "offset": 0, "length": 8}
    ]


def test_parse_header_rejects_overlapping_ranges(tmp_path):
    path = tmp_path / "bad.safetensors"
    header = {
        "a": {"dtype": "U8", "shape": [4], "data_offsets": [0, 4]},
        "b": {"dtype": "U8", "shape": [4], "data_offsets": [3, 7]},
    }
    _write_safetensors(path, header)

    with pytest.raises(ValueError, match="overlapping_tensor_ranges"):
        parse_safetensors_header(str(path))
