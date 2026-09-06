from __future__ import annotations

import json
import builtins
import threading
import time
from typing import cast

import pytest

from comfymodal_runtime import golden_serial as gs


pytestmark = pytest.mark.fast_unit


def _fixture(tmp_path):
    payload = b"abcdefgh"
    header = {"weight": {"dtype": "U8", "shape": [len(payload)], "data_offsets": [0, len(payload)]}}
    encoded = json.dumps(header, separators=(",", ":")).encode("utf-8")
    path = tmp_path / "clip.safetensors"
    path.write_bytes(len(encoded).to_bytes(8, "little") + encoded + payload)
    parsed = gs.parse_safetensors_header(str(path))
    assert parsed["status"] == "ok"
    regions = gs.plan_source_regions(parsed["data_start"], parsed["total_data_bytes"], 4, 2)
    layout = gs.FrozenClipSourceLayout(
        path=str(path),
        file_size_bytes=parsed["size_bytes"],
        data_start=parsed["data_start"],
        total_data_bytes=parsed["total_data_bytes"],
        header=parsed["header"],
        tensor_map=tuple(
            (key, dtype, tuple(shape), start, length)
            for key, dtype, shape, start, length in gs.build_header_tensor_map(parsed["header"])
        ),
        regions=tuple(tuple(region) for region in regions),
        qd=2,
        block_bytes=4,
    )
    return path, layout, payload


def test_frozen_layout_metadata_and_ranges(tmp_path):
    _path, layout, _payload = _fixture(tmp_path)
    with pytest.raises(TypeError):
        layout.header["new"] = {}  # type: ignore[index]
    with pytest.raises(Exception):
        layout.path = "changed"  # type: ignore[misc]
    assert sum(length for region in layout.regions for _start, length in region) == layout.total_data_bytes


def test_one_read_raw_reader_blocks_and_accounts_exact_bytes(tmp_path):
    _path, layout, payload = _fixture(tmp_path)
    ticket = gs.CpuRawPrefetchTicket(layout)
    result = []

    reader = threading.Thread(target=lambda: result.append(bytes(ticket.read_range(0, 4))))
    reader.start()
    time.sleep(0.02)
    assert reader.is_alive()
    ticket.start()
    reader.join(timeout=2)
    assert not reader.is_alive()
    ticket.join()
    assert result == [payload[:4]]
    assert ticket.telemetry()["read_calls"] >= 1
    assert ticket.telemetry()["bytes_read"] == len(payload)
    ticket.close()
    assert ticket.telemetry()["raw_backing_released"] is True


def test_prefetch_has_one_source_lifecycle_exact_bytes_and_no_physical_e27_claim(tmp_path):
    _path, layout, _payload = _fixture(tmp_path)
    ticket = gs.CpuRawPrefetchTicket(layout)
    ticket.start()
    ticket.join()
    telemetry = ticket.telemetry()
    assert telemetry["source_lifecycle_count"] == 1
    assert telemetry["read_calls"] >= 1
    assert telemetry["bytes_read"] == layout.total_data_bytes
    assert telemetry["bytes_prefetched"] == layout.total_data_bytes
    assert telemetry["source_completed"] is True
    assert [
        event["name"] for event in ticket.events
        if event["name"].startswith("CPU_PREFETCH_SOURCE_")
    ] == [
        "CPU_PREFETCH_SOURCE_25",
        "CPU_PREFETCH_SOURCE_50",
        "CPU_PREFETCH_SOURCE_75",
        "CPU_PREFETCH_SOURCE_100",
        "CPU_PREFETCH_SOURCE_COMPLETE",
    ]
    assert telemetry["source_provenance"] != "physical_syscall_proven"
    assert not any("E27" in str(event) for event in ticket.events)
    ticket.close()


def test_early_range_is_readable_before_source_completion_and_h2d_observes_it(
    tmp_path, monkeypatch
):
    path, layout, payload = _fixture(tmp_path)
    first_chunk_read = threading.Event()
    release_source = threading.Event()
    real_open = builtins.open

    class DelayedHandle:
        def __init__(self, handle):
            self._handle = handle
            self._calls = 0

        def __enter__(self):
            self._handle.__enter__()
            return self

        def __exit__(self, *args):
            return self._handle.__exit__(*args)

        def seek(self, *args):
            return self._handle.seek(*args)

        def readinto(self, target):
            self._calls += 1
            got = self._handle.readinto(target)
            if self._calls == 1:
                first_chunk_read.set()
                assert got == layout.block_bytes
            elif self._calls == 2:
                assert release_source.wait(timeout=2)
            return got

    def delayed_open(file, mode="r", *args, **kwargs):
        handle = real_open(file, mode, *args, **kwargs)
        return DelayedHandle(handle) if str(file) == str(path) else handle

    monkeypatch.setattr(builtins, "open", delayed_open)
    ticket = gs.CpuRawPrefetchTicket(layout)
    ticket.mark_clip_demand()
    ticket.start()
    assert first_chunk_read.wait(timeout=2)

    assert bytes(ticket.read_range(0, layout.block_bytes)) == payload[:layout.block_bytes]
    assert ticket.bytes_available == layout.block_bytes
    assert ticket.telemetry()["source_completed"] is False

    ticket.mark_h2d_start()
    h2d_start = next(event for event in ticket.events if event["name"] == "H2D_START")
    assert h2d_start["fields"]["bytes_prefetched_at_h2d_start"] == layout.block_bytes
    assert h2d_start["fields"]["source_completed_before_h2d"] is False
    assert ticket.telemetry()["exposed_wait_at_clip_demand_ms"] == 0

    release_source.set()
    ticket.join()
    assert ticket.telemetry()["bytes_read"] == len(payload)
    assert ticket.telemetry()["bytes_prefetched"] == len(payload)
    assert ticket.telemetry()["source_completed"] is True
    assert ticket.telemetry()["read_calls"] >= 2
    ticket.close()


def test_lifecycle_events_are_monotonic_and_ordered(tmp_path):
    _path, layout, _payload = _fixture(tmp_path)
    ticket = gs.CpuRawPrefetchTicket(layout)
    ticket.event("GPU_READINESS_COMPLETE")
    ticket.event("DYNAMICVRAM_ACCEPTED")
    ticket.start()
    ticket.join()
    ticket.mark_h2d_start()
    ticket.mark_h2d_complete(h2d_bytes=layout.total_data_bytes)
    ticket.mark_clip_gpu_ready(adoption_proven=True, storage_proven=True)
    names = [event["name"] for event in ticket.events]
    marks = [event["monotonic_ns"] for event in ticket.events]
    assert marks == sorted(marks)
    assert names.index("GPU_READINESS_COMPLETE") < names.index("DYNAMICVRAM_ACCEPTED")
    assert names.index("H2D_START") < names.index("H2D_COMPLETE_CLIP_GPU_READY")
    assert names.index("H2D_COMPLETE_CLIP_GPU_READY") < names.index("CLIP_GPU_READY")
    telemetry = ticket.telemetry()
    assert telemetry["clip_gpu_ready"] is True
    assert telemetry["h2d_stream_span_ns"] >= 0
    ticket.close()


def test_cpu_qd2_prefetch_rejects_fp32_cast_once_residency(tmp_path, monkeypatch):
    _path, _layout, _payload = _fixture(tmp_path)
    monkeypatch.setenv(gs.CPU_QD2_PREFETCH_ENV, "1")
    monkeypatch.setenv(gs.CLIP_FP32_CAST_ONCE_ENV, "1")
    request = gs.GoldenRequest("r", {}, cpu_qd2_prefetch=True)
    assert gs.resolve_clip_residency(request.clip_residency) == "fp32_cast_once"
    with pytest.raises(RuntimeError, match="cpu_qd2_prefetch_clip_residency_conflict"):
        gs.prepare_cpu_clip_prefetch(request)


def test_memory_visibility_keeps_source_post_h2d_and_close_observations(tmp_path, monkeypatch):
    _path, layout, _payload = _fixture(tmp_path)
    host_samples = iter(
        [
            {"rss_bytes": 5, "max_rss_bytes": 5},
            {"rss_bytes": 10, "max_rss_bytes": 10},
            {"rss_bytes": 20, "max_rss_bytes": 20},
            {"rss_bytes": 15, "max_rss_bytes": 25},
        ]
    )
    available_samples = iter(
        [{"available_bytes": 110, "free_bytes": 60},
         {"available_bytes": 100, "free_bytes": 50},
         {"available_bytes": 90, "free_bytes": 40},
         {"available_bytes": 95, "free_bytes": 45}]
    )
    cgroup_samples = iter(
        [{"current_bytes": 0, "max_bytes": 10},
         {"current_bytes": 1, "max_bytes": 10},
         {"current_bytes": 2, "max_bytes": 10},
         {"current_bytes": 3, "max_bytes": 10}]
    )
    fault_samples = iter(
        [{"available": True, "minor_faults": 0, "major_faults": 0},
         {"available": True, "minor_faults": 1, "major_faults": 0},
         {"available": True, "minor_faults": 2, "major_faults": 0},
         {"available": True, "minor_faults": 3, "major_faults": 0}]
    )
    monkeypatch.setattr(gs, "_host_memory_visibility", lambda: next(host_samples))
    monkeypatch.setattr(gs, "_cpu_prefetch_memory_visibility", lambda: next(available_samples))
    monkeypatch.setattr(gs, "_cpu_prefetch_cgroup_memory", lambda: next(cgroup_samples))
    monkeypatch.setattr(gs, "_process_page_faults", lambda: next(fault_samples))

    ticket = gs.CpuRawPrefetchTicket(layout)
    ticket.start()
    ticket.join()
    ticket.mark_h2d_start()
    ticket.mark_h2d_complete(h2d_bytes=layout.total_data_bytes)
    ticket.close()
    memory = ticket.telemetry()["memory"]
    assert memory["source_completion"]["max_rss_bytes"] == 10
    assert memory["post_h2d"]["max_rss_bytes"] == 20
    assert memory["close"]["max_rss_bytes"] == 25
    assert memory["peak_high_water"] == 25
    assert memory["available_free_lifecycle"]["close"]["free_bytes"] == 45
    assert memory["cgroup"]["post_h2d"]["current_bytes"] == 2
    assert memory["page_faults_lifecycle"]["close"]["minor_faults"] == 3


def test_clip_gpu_ready_raw_event_is_adopted_by_recorder(tmp_path):
    _path, layout, _payload = _fixture(tmp_path)
    ticket = gs.CpuRawPrefetchTicket(layout)
    ticket.event("CLIP_GPU_READY", adoption_proven=True, storage_proven=True)
    session = gs.GoldenSession(
        gs.GoldenRequest("r", {}, cpu_qd2_prefetch=True),
        volume=None,
        cpu_prefetch_ticket=ticket,
    )
    ticket.event("CPU_RAW_BACKING_RELEASE", raw_backing_released=True)
    session.flush_cpu_prefetch_events()
    assert [event["name"] for event in session.recorder._events].count("CLIP_GPU_READY") == 1


def test_failed_source_releases_raw_backing_and_worker(tmp_path):
    _path, layout, _payload = _fixture(tmp_path)
    bad_layout = gs.FrozenClipSourceLayout(
        path=str(tmp_path / "missing.safetensors"),
        file_size_bytes=layout.file_size_bytes,
        data_start=layout.data_start,
        total_data_bytes=layout.total_data_bytes,
        header=layout.header,
        tensor_map=layout.tensor_map,
        regions=layout.regions,
        qd=1,
        block_bytes=4,
    )
    ticket = gs.CpuRawPrefetchTicket(bad_layout)
    ticket.start()
    with pytest.raises(RuntimeError):
        ticket.close()
    assert ticket.telemetry()["raw_backing_released"] is True
    assert ticket._thread is None or not ticket._thread.is_alive()


def test_request_selector_defaults_to_control():
    request = gs.GoldenRequest("r", {})
    assert request.cpu_qd2_prefetch is False


def test_transport_resources_are_omitted_only_for_prefetched_clip():
    class Session:
        cpu_prefetch_ticket = object()

        def __init__(self):
            self.calls = 0

        def get_transport_resources(self):
            self.calls += 1
            return "request-resources"

    raw_session = Session()
    session = cast(gs.GoldenSession, raw_session)
    assert gs._transport_read_options(session, role="clip") == {}
    assert raw_session.calls == 0

    for role in ("unet", "vae"):
        assert gs._transport_read_options(session, role=role) == {
            "transport_resources": "request-resources",
        }
    assert raw_session.calls == 2
