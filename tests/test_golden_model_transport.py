from __future__ import annotations

import inspect
import json
import struct
from collections import OrderedDict

import pytest

from comfymodal_runtime.golden_model_transport import GoldenModelTransport
from comfymodal_runtime.m2_source_core import _persistent_reader_close_fds


pytestmark = pytest.mark.fast_unit


def _write_safetensors(path, key: str, payload: bytes = b"abcd") -> None:
    header = {
        key: {"dtype": "U8", "shape": [len(payload)], "data_offsets": [0, len(payload)]},
    }
    encoded = json.dumps(header, separators=(",", ":")).encode("utf-8")
    path.write_bytes(struct.pack("<Q", len(encoded)) + encoded + payload)


def test_transport_inspects_only_requested_path_and_bounds_layout_cache(tmp_path):
    paths = []
    for index in range(4):
        path = tmp_path / f"model-{index}.safetensors"
        _write_safetensors(path, f"tensor_{index}")
        paths.append(path)

    transport = GoldenModelTransport()
    first = transport.inspect(str(paths[0]))
    assert first.path == str(paths[0].resolve())
    assert list(first.tensor_map[0]) == ["key", "dtype", "shape", "offset", "length"]
    assert len(transport.layout_cache) == 1

    for path in paths[1:]:
        transport.inspect(str(path))
    assert len(transport.layout_cache) == 3
    assert str(paths[0].resolve()) not in transport.layout_cache


def test_models_generation_invalidates_layout_cache_without_recreating_runtime(tmp_path):
    path = tmp_path / "model.safetensors"
    _write_safetensors(path, "tensor")
    transport = GoldenModelTransport()
    transport.inspect(str(path))
    assert transport.layout_cache

    transport.update_models_generation("generation-2")

    assert not transport.layout_cache
    assert transport.lifecycle_telemetry(reused=False)["staging_reused"] is False


def test_transport_load_is_role_neutral_and_path_driven():
    signature = inspect.signature(GoldenModelTransport.load)
    assert tuple(signature.parameters) == ("self", "path")


def test_persistent_reader_fd_cache_closes_fd_from_identity_tuple(monkeypatch):
    closed = []
    monkeypatch.setattr("comfymodal_runtime.m2_source_core.os.close", closed.append)
    cache = OrderedDict({"model.safetensors": (17, (1, 2, 3, 4))})

    _persistent_reader_close_fds(cache)

    assert closed == [17]
    assert not cache
