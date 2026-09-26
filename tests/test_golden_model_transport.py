from __future__ import annotations

import inspect
import json
import struct
import sys
from types import SimpleNamespace
from collections import OrderedDict

import pytest

from comfymodal_runtime.golden_model_transport import (
    BLOCK_BYTES,
    DESTINATION_ALIGNMENT,
    GpuDestinationPool,
    GoldenModelTransport,
    MIN_LAUNCH_GAP_NS,
    QD,
    STAGING_BYTES,
    _destination_reserve_capacities,
    _sticky_lane_ranges,
)
from comfymodal_runtime.m2_source_core import (
    _persistent_reader_close_fds,
    _persistent_reader_load,
)


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


def test_transport_geometry_is_fixed_to_proven_m2_contract(monkeypatch):
    monkeypatch.setenv("COMFYMODAL_GOLDEN_IO_PROCESS_V2_STREAMING", "1")
    monkeypatch.setenv("COMFYMODAL_GOLDEN_IO_PROCESS_V2_SOURCE_GEOMETRY", "qd4_64")

    transport = GoldenModelTransport()

    assert (transport.qd, transport.block_bytes, transport.staging_slots) == (
        QD,
        BLOCK_BYTES,
        1,
    )
    assert transport.staging_bytes == STAGING_BYTES == 256 * 1024 * 1024
    assert transport.staging_backing == "anonymous"
    assert not hasattr(transport, "_c0_enabled")


def test_sticky_lanes_are_contiguous_and_cover_every_block_once():
    ranges = _sticky_lane_ranges(11)

    assert ranges == ((0, 3), (3, 6), (6, 9), (9, 11))
    assert [block for start, end in ranges for block in range(start, end)] == list(range(11))


def test_persistent_reader_keeps_frozen_source_ordering_contract():
    source = inspect.getsource(_persistent_reader_load)

    assert "for lane, (start, end) in enumerate(lane_ranges)" in source
    assert "_alloc_gate(" in source
    assert "_MAP_PRIVATE, fd, window_start" in source
    assert "_MAP_POPULATE" not in source
    assert source.index("published.value = sequence + 1") < source.index("_LIBC.munmap")


def test_destination_reserve_uses_three_aligned_generic_capacity_tiers():
    gib = 1024**3
    capacities = _destination_reserve_capacities(80 * gib, 80 * gib)

    assert len(capacities) == 3
    assert capacities[0] > capacities[1] > capacities[2]
    assert all(capacity % DESTINATION_ALIGNMENT == 0 for capacity in capacities)
    assert sum(capacities) <= int(80 * gib * 0.30)


def test_destination_pool_uses_best_fit_and_fresh_lease_wrappers(monkeypatch):
    class FakeTensor:
        def __init__(self, size):
            self.size = size
            self.device = "cuda:0"

    monkeypatch.setattr(
        GpuDestinationPool,
        "_allocate",
        staticmethod(lambda _device, capacity: FakeTensor(capacity)),
    )
    pool = GpuDestinationPool("cuda:0")
    pool.reserve([60, 40, 20])

    medium = pool.acquire(35)
    large = pool.acquire(50)
    small = pool.acquire(10)
    growth = pool.acquire(5)

    assert (medium.capacity_bytes, large.capacity_bytes, small.capacity_bytes) == (40, 60, 20)
    assert medium.reused and large.reused and small.reused
    assert growth.capacity_bytes == 5
    assert growth.reused is False
    medium.release_storage()
    replacement = pool.acquire(30)
    assert replacement is not medium
    assert replacement.capacity_bytes == 40
    assert replacement.reused is True
    assert medium.released is True


def test_prepare_cpu_fails_closed_if_cuda_was_already_initialized(monkeypatch):
    fake_torch = SimpleNamespace(
        cuda=SimpleNamespace(is_initialized=lambda: True),
    )
    monkeypatch.setitem(sys.modules, "torch", fake_torch)
    monkeypatch.setattr("comfymodal_runtime.golden_model_transport.os.name", "posix")
    monkeypatch.setattr(
        "comfymodal_runtime.golden_model_transport.mp.get_all_start_methods",
        lambda: ["fork"],
    )

    with pytest.raises(RuntimeError, match="must_fork_before_cuda"):
        GoldenModelTransport().prepare_cpu()


def test_persistent_reader_fd_cache_closes_fd_from_identity_tuple(monkeypatch):
    closed = []
    monkeypatch.setattr("comfymodal_runtime.m2_source_core.os.close", closed.append)
    cache = OrderedDict({"model.safetensors": (17, (1, 2, 3, 4))})

    _persistent_reader_close_fds(cache)

    assert closed == [17]
    assert not cache
