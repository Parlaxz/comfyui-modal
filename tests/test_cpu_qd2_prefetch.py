from __future__ import annotations

import json
import os
import threading
import time

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
    layout = gs.FrozenClipSourceLayout(
        path=str(path), file_size_bytes=parsed["size_bytes"], data_start=parsed["data_start"],
        total_data_bytes=parsed["total_data_bytes"], header=parsed["header"],
        tensor_map=tuple(gs.build_header_tensor_map(parsed["header"])),
        regions=tuple(tuple(r) for r in gs.plan_source_regions(parsed["data_start"], parsed["total_data_bytes"], 4, 2)),
        qd=2, block_bytes=4,
    )
    return path, layout, payload


def _preadv_for(path, payload, *, short=False, gate=None, fail_offset=None):
    source = path.read_bytes()
    calls: list[tuple[int, int]] = []
    lock = threading.Lock()
    short_offsets: set[int] = set()

    def fake(fd, vectors, offset):
        offset = int(offset)
        if gate is not None and offset == gate[0]:
            gate[1].set()
            gate[2].wait(timeout=2)
        if fail_offset is not None and offset == fail_offset:
            return 0
        data = source[offset:offset + len(vectors[0])]
        count = len(data)
        if short and offset not in short_offsets and count > 1:
            count //= 2
            short_offsets.add(offset)
        vectors[0][:count] = data[:count]
        with lock:
            calls.append((offset, count))
        return count

    return fake, calls


def test_qd2_geometry_is_128m_and_contiguous_half_owned():
    extent = gs.CPU_QD2_SOURCE_EXTENT_BYTES
    regions = gs.plan_source_regions(100, extent * 59 + 126090240, extent, 2)
    assert len(regions) == 2
    assert all(regions)
    assert sum(len(region) for region in regions) == 60
    assert len(regions[0]) == 30
    assert len(regions[1]) == 30
    assert regions[0][-1][0] + regions[0][-1][1] == regions[1][0][0]


def test_two_real_workers_preadv_exact_coverage_and_cleanup(tmp_path, monkeypatch):
    path, layout, payload = _fixture(tmp_path)
    fake, calls = _preadv_for(path, payload)
    monkeypatch.setattr(os, "preadv", fake, raising=False)
    ticket = gs.CpuRawPrefetchTicket(layout)
    ticket.start()
    ticket.join()
    telemetry = ticket.telemetry()
    assert telemetry["source_owner_count"] == 1
    assert telemetry["source_lifecycle_count"] == 1
    assert telemetry["worker_count"] == 2
    assert telemetry["worker_extents"] == {"0": 1, "1": 1}
    assert telemetry["worker_bytes"] == {"0": 4, "1": 4}
    assert telemetry["source_provenance"] == "actual_os_preadv"
    assert telemetry["syscall_count"] == len(calls) == 2
    assert telemetry["syscall_bytes"] == len(payload)
    assert sorted((r["offset"], r["bytes"]) for r in telemetry["syscall_records"]) == [(layout.data_start, 4), (layout.data_start + 4, 4)]
    assert telemetry["ready_intervals"] == [(0, 4), (4, 8)]
    assert bytes(ticket.read_range(0, len(payload))) == payload
    ticket.close()
    assert ticket.telemetry()["raw_backing_released"] is True
    assert not any(t.is_alive() for t in ticket._threads)


def test_out_of_order_extent_readiness_never_exposes_gap(tmp_path, monkeypatch):
    path, layout, payload = _fixture(tmp_path)
    started = threading.Event()
    release = threading.Event()
    fake, _calls = _preadv_for(path, payload, gate=(layout.data_start, started, release))
    monkeypatch.setattr(os, "preadv", fake, raising=False)
    ticket = gs.CpuRawPrefetchTicket(layout)
    ticket.start()
    assert started.wait(timeout=2)
    # Worker 1 owns the second extent and may publish out of order.
    assert bytes(ticket.read_range(4, 4)) == payload[4:]
    result: list[bytes] = []
    reader = threading.Thread(target=lambda: result.append(bytes(ticket.read_range(0, 8))))
    reader.start()
    time.sleep(0.02)
    assert reader.is_alive()
    release.set()
    reader.join(timeout=2)
    ticket.join()
    assert result == [payload]
    assert ticket.telemetry()["contiguous_prefix_bytes"] == len(payload)
    ticket.close()


def test_short_read_retries_are_exact_and_proven(tmp_path, monkeypatch):
    path, layout, payload = _fixture(tmp_path)
    fake, calls = _preadv_for(path, payload, short=True)
    monkeypatch.setattr(os, "preadv", fake, raising=False)
    ticket = gs.CpuRawPrefetchTicket(layout)
    ticket.start()
    ticket.join()
    telemetry = ticket.telemetry()
    assert telemetry["source_provenance"] == "actual_os_preadv"
    assert telemetry["short_read_retries"] == 4
    assert telemetry["syscall_count"] == len(calls) == 6
    assert telemetry["syscall_bytes"] == len(payload)
    ticket.close()


def test_short_read_zero_fails_closed_and_releases_backing(tmp_path, monkeypatch):
    path, layout, _payload = _fixture(tmp_path)
    fake, _calls = _preadv_for(path, b"", fail_offset=layout.data_start)
    monkeypatch.setattr(os, "preadv", fake, raising=False)
    ticket = gs.CpuRawPrefetchTicket(layout)
    ticket.start()
    with pytest.raises(RuntimeError, match="cpu_prefetch_source_failed"):
        ticket.join()
    assert ticket.telemetry()["raw_backing_released"] is True
    assert not any(t.is_alive() for t in ticket._threads)


def test_missing_preadv_fails_closed_without_fallback(tmp_path, monkeypatch):
    _path, layout, _payload = _fixture(tmp_path)
    monkeypatch.delattr(os, "preadv", raising=False)
    ticket = gs.CpuRawPrefetchTicket(layout)
    with pytest.raises(RuntimeError, match="preadv_unavailable"):
        ticket.start()
    assert ticket.telemetry()["raw_backing_released"] is True
    assert ticket._threads == []


def test_request_selector_and_transport_contracts():
    request = gs.GoldenRequest("r", {})
    assert request.cpu_qd2_prefetch is False
    assert request.deep_trace_level == "off"
