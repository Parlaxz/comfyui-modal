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
    _c0_window_trace_enabled,
    _destination_reserve_capacities,
    _percentile_summary,
    _sticky_lane_ranges,
    resolve_c0_transport_geometry,
    summarize_c0_reader,
    summarize_dispatcher,
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
    assert tuple(signature.parameters) == ("self", "path", "role")
    # The role is a diagnostic label for the 30 s per-model-load gate only.
    # It must never become a dispatch input: the loader still runs entirely
    # off the resolved path, and an unlabelled caller keeps the neutral default.
    role = signature.parameters["role"]
    assert role.kind is inspect.Parameter.KEYWORD_ONLY
    assert role.default == "model"


def test_transport_geometry_is_fixed_to_proven_m2_contract(monkeypatch):
    for key in (
        "COMFYMODAL_GOLDEN_IO_PROCESS_V2_STREAMING",
        "COMFYMODAL_GOLDEN_IO_PROCESS_V2_SOURCE_ENGINE",
        "COMFYMODAL_GOLDEN_IO_PROCESS_V2_SOURCE_GEOMETRY",
    ):
        monkeypatch.delenv(key, raising=False)

    transport = GoldenModelTransport()

    assert (transport.qd, transport.block_bytes, transport.staging_slots) == (
        QD,
        BLOCK_BYTES,
        1,
    )
    assert transport.staging_bytes == STAGING_BYTES == 256 * 1024 * 1024
    assert transport.staging_backing == "anonymous"
    assert transport._c0_enabled is False


def test_c0_streaming_with_exact_window_engine_selects_shared_arena(monkeypatch):
    monkeypatch.setenv("COMFYMODAL_GOLDEN_IO_PROCESS_V2_STREAMING", "1")
    monkeypatch.setenv("COMFYMODAL_GOLDEN_IO_PROCESS_V2_SOURCE_ENGINE", "mmap_fresh")
    monkeypatch.setenv("COMFYMODAL_GOLDEN_IO_PROCESS_V2_SOURCE_GEOMETRY", "qd4_64")

    transport = GoldenModelTransport()

    assert transport._c0_enabled is True
    # C0 prepare is a cheap no-op: no fork, no staging build, no CUDA work.
    telemetry = transport.prepare_cpu()
    assert transport._prepared is True
    assert transport.staging is None
    assert transport._children == []
    assert telemetry["transport_runtime_reused"] is False


def test_c0_streaming_without_exact_window_engine_fails_closed(monkeypatch):
    # Half-armed C0 selection must not silently run the M2 execution arm.
    monkeypatch.setenv("COMFYMODAL_GOLDEN_IO_PROCESS_V2_STREAMING", "1")
    monkeypatch.delenv("COMFYMODAL_GOLDEN_IO_PROCESS_V2_SOURCE_ENGINE", raising=False)

    with pytest.raises(RuntimeError, match="c0_streaming_requires_mmap_fresh"):
        GoldenModelTransport()


def test_c0_transport_geometry_defaults_to_qd4_64(monkeypatch):
    monkeypatch.delenv("COMFYMODAL_GOLDEN_C0_TRANSPORT_GEOMETRY", raising=False)

    geo = resolve_c0_transport_geometry()

    assert geo["name"] == "qd4_64"
    assert geo["queue_depth"] == QD == 4
    assert geo["block_bytes"] == BLOCK_BYTES == 64 * 1024 * 1024
    assert geo["producer_workers"] == 4
    assert geo["aggregation_enabled"] is False
    assert geo["required_slot_bytes"] == 64 * 1024 * 1024


def test_c0_transport_geometry_qd2_128(monkeypatch):
    monkeypatch.setenv("COMFYMODAL_GOLDEN_C0_TRANSPORT_GEOMETRY", "qd2_128")

    geo = resolve_c0_transport_geometry()

    assert geo["queue_depth"] == 2
    assert geo["block_bytes"] == 128 * 1024 * 1024
    assert geo["producer_workers"] == 2
    assert geo["required_slot_bytes"] == 128 * 1024 * 1024


def test_c0_transport_geometry_h2d128_keeps_64mib_source_windows(monkeypatch):
    monkeypatch.setenv("COMFYMODAL_GOLDEN_C0_TRANSPORT_GEOMETRY", "qd4_64_h2d128")

    geo = resolve_c0_transport_geometry()

    assert geo["queue_depth"] == 4
    assert geo["block_bytes"] == 64 * 1024 * 1024
    assert geo["aggregation_enabled"] is True
    assert geo["h2d_target_bytes"] == 128 * 1024 * 1024


def test_c0_transport_geometry_qd4_128(monkeypatch):
    monkeypatch.setenv("COMFYMODAL_GOLDEN_C0_TRANSPORT_GEOMETRY", "qd4_128")

    geo = resolve_c0_transport_geometry()

    assert geo["queue_depth"] == 4
    assert geo["block_bytes"] == 128 * 1024 * 1024
    assert geo["producer_workers"] == 4
    assert geo["aggregation_enabled"] is False
    assert geo["required_slot_bytes"] == 128 * 1024 * 1024
    assert geo["capacity_class"] == "c0-qd4-128m"


def test_c0_arena_geometry_qd4_128_keeps_512mib():
    """The 128 MiB arm is unchanged; only the qd4_64 arm moved to 1 GiB.

    The arena is derived as ``slot_count * slot_bytes`` per arm, because
    ``SharedArenaRing`` rejects any other total.  So qd4_128 keeps its 512 MiB
    while the active qd4_64 arm is now 16 x 64 MiB = 1 GiB.
    """
    from comfymodal_runtime.golden_io_process_v2 import (
        resolve_c0_geometry,
    )

    resolved = resolve_c0_geometry("qd4_128")

    assert resolved["arena_bytes"] == 512 * 1024 * 1024
    assert resolved["slot_bytes"] == 128 * 1024 * 1024
    assert resolved["slot_count"] == 4
    assert resolved["slot_bytes"] * resolved["slot_count"] == resolved["arena_bytes"]
    assert resolved["source_geometry"] == "qd4_128"


def test_c0_arena_geometry_qd4_64_is_sixteen_64mib_slots():
    """The counted Production-009 arm is now 16 x 64 MiB = 1 GiB."""
    from comfymodal_runtime.golden_io_process_v2 import resolve_c0_geometry

    resolved = resolve_c0_geometry("qd4_64")

    assert resolved["slot_count"] == 16
    assert resolved["slot_bytes"] == 64 * 1024 * 1024
    assert resolved["arena_bytes"] == 1024 * 1024 * 1024 == 1073741824
    assert resolved["slot_bytes"] * resolved["slot_count"] == resolved["arena_bytes"]
    # Unchanged by this treatment.
    assert resolved["source_workers"] == 4
    assert len(resolved["slot_owners"]) == resolved["slot_count"]
    assert set(resolved["slot_owners"]) == {0, 1, 2, 3}


def test_c0_public_constants_track_the_active_arm():
    """``C0_ARENA_BYTES``/``C0_SLOT_COUNT`` describe whichever arm is deployed."""
    from comfymodal_runtime.golden_io_process_v2 import (
        C0_ARENA_BYTES,
        C0_SLOT_COUNT,
        resolve_c0_geometry,
    )

    active = resolve_c0_geometry()
    assert C0_ARENA_BYTES == active["arena_bytes"]
    assert C0_SLOT_COUNT == active["slot_count"]
    assert C0_ARENA_BYTES == C0_SLOT_COUNT * active["slot_bytes"]


def test_every_c0_arm_fully_utilises_its_own_arena():
    """No arm may declare an arena its slots cannot fill.

    ``SharedArenaRing`` raises ``c0_arena_geometry_mismatch`` on any other
    total, so the product invariant is asserted here for every arm rather than
    for the counted arm only.
    """
    from comfymodal_runtime.golden_io_process_v2 import resolve_c0_geometry

    for selector in ("qd4_32", "qd2_128", "qd4_64", "qd4_128"):
        resolved = resolve_c0_geometry(selector)
        assert resolved["arena_bytes"] == resolved["slot_count"] * resolved["slot_bytes"], selector
        assert len(resolved["slot_owners"]) == resolved["slot_count"], selector


def test_c0_geometry_selector_fails_closed_on_an_unknown_arm():
    from comfymodal_runtime.golden_io_process_v2 import resolve_c0_geometry

    with pytest.raises(ValueError, match="SOURCE_GEOMETRY_invalid"):
        resolve_c0_geometry("qd16_512")


def test_c0_transport_geometry_unknown_fails_closed(monkeypatch):
    monkeypatch.setenv("COMFYMODAL_GOLDEN_C0_TRANSPORT_GEOMETRY", "qd8_256")

    with pytest.raises(ValueError, match="invalid C0 transport geometry"):
        resolve_c0_transport_geometry()


def test_c0_window_trace_defaults_off(monkeypatch):
    monkeypatch.delenv("COMFYMODAL_GOLDEN_C0_WINDOW_TRACE", raising=False)
    assert _c0_window_trace_enabled() is False
    monkeypatch.setenv("COMFYMODAL_GOLDEN_C0_WINDOW_TRACE", "1")
    assert _c0_window_trace_enabled() is True


def test_percentile_summary_math():
    assert _percentile_summary([]) == {"count": 0}
    assert _percentile_summary(["x", None, True]) == {"count": 0}

    summary = _percentile_summary([100_000_000, 200_000_000, 300_000_000, 400_000_000])

    assert summary["count"] == 4
    assert summary["min_ms"] == 100.0
    assert summary["max_ms"] == 400.0
    assert summary["p50_ms"] == pytest.approx(250.0)
    assert summary["mean_ms"] == pytest.approx(250.0)
    assert summary["sum_ms"] == pytest.approx(1000.0)


def test_summarize_c0_reader_tolerates_missing_attributes():
    summary = summarize_c0_reader(object())

    assert summary["fills"] == 0
    assert summary["map"] == {"count": 0}
    assert summary["worst_window"] is None
    assert summary["reader_pids"] == []


def test_summarize_c0_reader_collects_phases_and_worst_window():
    class FakeRing:
        backpressure_block_count = 3
        backpressure_block_ns = 9_000_000
        fills_submitted = 10
        fills_ready = 10

    class FakeReader:
        _ring = FakeRing()
        fills = 4
        fill_wall_ns = 1_000_000_000
        fd_open_count = 1
        fd_reuse_count = 3
        fd_close_count = 0
        _mmap_map_ns = [1_000_000, 2_000_000]
        _mmap_memcpy_ns = [200_000_000, 260_000_000]
        _mmap_munmap_ns = [5_000_000, 7_000_000]
        _mmap_pipe_rtt_ns = [210_000_000, 270_000_000]
        _mmap_gate_wait_ns = [0, 4_000_000]
        _mmap_minflt = [100, 120]
        _mmap_majflt = [0, 2]
        _mmap_reader_pids = {111, 222}
        _mmap_memcpy_first_ns = [200_000_000]
        _mmap_memcpy_reuse_ns = [260_000_000]
        _mmap_map_first_ns = []
        _mmap_map_reuse_ns = []
        _mmap_read_records = [
            {"mmap_op_ns": 100_000_000, "producer_id": 0,
             "source_range": [0, 67108864]},
            {"mmap_op_ns": 300_000_000, "producer_id": 2,
             "source_range": [134217728, 201326592]},
        ]

    summary = summarize_c0_reader(FakeReader())

    assert summary["fills"] == 4
    assert summary["ring_backpressure_blocks"] == 3
    assert summary["memcpy"]["count"] == 2
    assert summary["memcpy"]["max_ms"] == pytest.approx(260.0)
    assert summary["majflt_total"] == 2
    assert summary["reader_pids"] == [111, 222]
    assert summary["worst_window"]["producer_id"] == 2
    assert summary["worst_window"]["source_range"] == [134217728, 201326592]
    assert summary["memcpy_first_ms"] == pytest.approx(200.0)
    assert summary["memcpy_reuse_ms"] == pytest.approx(260.0)


def test_summarize_cpu_windows_reports_deltas():
    from comfymodal_runtime.golden_model_transport import _summarize_cpu_windows

    windows = {
        (66, "mmap_ru_utime_ns"): [1_000_000_000, 1_500_000_000],
        (66, "mmap_sched_wait_ns"): [100_000_000, 130_000_000],
        (67, "mmap_ru_utime_ns"): [2_000_000_000, 2_200_000_000],
        ("bad",): [1, 2],
        (68, "mmap_ru_utime_ns"): ["x", 5],
    }

    summary = _summarize_cpu_windows(windows)

    assert summary["utime_ms"] == pytest.approx(700.0)
    assert summary["stime_ms"] is None
    assert summary["sched_wait_ms"] == pytest.approx(30.0)
    assert summary["per_pid"]["66"]["mmap_ru_utime_ns"] == pytest.approx(500.0)
    assert _summarize_cpu_windows(None)["utime_ms"] is None
    assert _summarize_cpu_windows({})["per_pid"] == {}


def test_arena_ensure_detail_reports_establishment_cost():
    from comfymodal_runtime.golden_model_transport import arena_ensure_detail

    class FakeRuntime:
        size_bytes = 536870912
        slot_count = 8
        slot_bytes = 67108864
        backing_create_ms = 12.5
        register_ms = 44.0
        registered = True
        child_pid = 66
        child_start_ns = 1_000_000_000
        child_ready_ns = 1_300_000_000

    detail = arena_ensure_detail(FakeRuntime())

    assert detail["arena_bytes"] == 536870912
    assert detail["backing_create_ms"] == 12.5
    assert detail["register_ms"] == 44.0
    assert detail["child_startup_ms"] == pytest.approx(300.0)
    assert arena_ensure_detail(None)["arena_bytes"] is None
    assert arena_ensure_detail(object())["child_startup_ms"] is None


def test_summarize_dispatcher_tolerates_missing_telemetry():
    summary = summarize_dispatcher(object())

    assert summary["producer_capacity_block_count"] is None
    assert summary["min_free_slots"] is None
    assert summary["qd_depth_max"] is None
    assert summary["h2d_latency"] == {"count": 0}


def test_c0_identity_is_c0_parallel_not_m2_arm():
    import inspect as _inspect

    source = _inspect.getsource(GoldenModelTransport._load_c0_sync)
    assert '"execution_architecture": "c0_parallel"' in source
    assert '"source_engine": "m2_exact_window"' in source
    assert '"c0_arena_bytes"' in source
    assert "m2_mmap_process" not in source
    assert "load_m2_safetensors" not in source
    assert "build_staging" not in source


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
