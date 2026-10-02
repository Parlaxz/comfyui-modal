"""Offline contracts for the isolated C9 recovery campaign."""

from __future__ import annotations

import asyncio
import json
import struct
import threading
from pathlib import Path

import c9_recovery_modal as recovery
from comfymodal_runtime import source_ceiling_oracle as oracle
from tools import run_c9_recovery as runner


def _valid_result(item: dict) -> dict:
    return {
        "experiment": "c9_recovery",
        "arm": "source_only",
        "execution_arm": "source_only",
        "status": "ok",
        "role": item["role"],
        "model_name": item["model_name"],
        "configured_source_qd": item["qd"],
        "source_block_bytes": runner.BLOCK_BYTES,
        "source_only": True,
        "torch_imported": True,
        "cuda_available": True,
        "cuda_build": "13.0",
        "gpu_attachment": {"attached": True, "requested": True, "gpu": "rtx-pro-6000"},
        "execution_contract": {"torch_imported": True},
        "cuda_used": False,
        "h2d_used": False,
        "model_construction": False,
        "FILE_TO_CUDA_WALL_MS": None,
        "fixed_config": {
            "execution_arm": "source_only",
            "configured_qd": item["qd"],
            "producer_count": item["qd"],
            "source_block_bytes": runner.BLOCK_BYTES,
            "h2d_target_bytes": None,
            "aggregation_enabled": False,
            "cuda_used": False,
            "h2d_used": False,
            "model_construction": False,
        },
        "metrics": {"H2D_WALL_MS": None},
        "coverage": {"ok": True},
        "byte_reconciliation": {"returned_equals_expected": True},
        "C9_TOTAL_WALL_MS": 1.0,
        "PHYSICAL_READ_SPAN_MS": 0.5,
        "SOURCE_WALL_MS": 1.0,
        "effective_gbps": 1.0,
        "time_weighted_achieved_qd": 1.0,
        "max_achieved_qd": item["qd"],
        "workers": [{"is_pinned": True} for _ in range(item["qd"])],
        "regions": [{"producer_id": n, "end": 12} for n in range(item["qd"])],
        "filesystem_identity": {},
        "cpu_allocation": {
            "requested_cpu": 12,
            "observed_runtime_shape_cpu_request": 12,
            "observed_cpu": 21,
        },
        "fd_topology": {
            "mode": "one_shared_fd",
            "open_count": 1,
            "positioned_reads": True,
            "close_after_all_workers": True,
        },
        "buffer_type": "pytorch_pinned_host",
        "pinned_host": True,
        "pinned_host_evidence": {
            "buffer_type": "pytorch_pinned_host",
            "is_pinned": True,
            "buffers": [
                {
                    "buffer_type": "pytorch_pinned_host",
                    "pinned_host": True,
                    "is_pinned": True,
                    "bytes": runner.BLOCK_BYTES,
                }
                for _ in range(item["qd"])
            ],
        },
        "buffer_allocations": {
            "count": item["qd"],
            "bytes_per_worker": runner.BLOCK_BYTES,
            "allocation_in_c9_total_wall": False,
            "reused_for_each_read": True,
            "reusable_lifetime": "worker_source_wall",
            "is_pinned": True,
            "released_after_all_workers_join": True,
        },
        "hashing_in_timed_loop": False,
        "allocation_in_timed_loop": False,
        "telemetry_in_timed_loop": False,
        "timing_boundary": {"name": "C9_TOTAL_WALL"},
        "physical_reads": [{
            "worker_id": 0,
            "offset": 8,
            "requested_bytes": 4,
            "returned_bytes": 4,
            "syscall_begin_ns": 1,
            "syscall_end_ns": 2,
        }],
        "all_requests_within_buffer": True,
        "max_requested_bytes": 4,
    }


def test_fixed_schedule_is_exact_and_has_no_other_geometry():
    schedule = runner.campaign_schedule()
    assert len(schedule) == 60
    assert {item["role"] for item in schedule} == {"clip", "unet"}
    assert {item["qd"] for item in schedule} == {2, 4, 8}
    assert {item["block_bytes"] for item in schedule} == {32 * 1024 * 1024}
    assert {item["observation"] for item in schedule} == set(range(1, 11))
    assert len({item["attempt_id"] for item in schedule}) == 60


def test_directional_schedule_allows_one_observation_without_new_geometry():
    schedule = runner.campaign_schedule(1)
    assert len(schedule) == 6
    assert {item["block_bytes"] for item in schedule} == {runner.BLOCK_BYTES}


def test_smoke_schedules_have_exact_requested_cardinality():
    first = runner.campaign_schedule(2, roles="unet", qds="8")
    second = runner.campaign_schedule(2, roles="unet", qds="2,4,8")

    assert len(first) == 2
    assert {(item["role"], item["qd"]) for item in first} == {("unet", 8)}
    assert len(second) == 6
    assert {(item["role"], item["qd"]) for item in second} == {
        ("unet", 2),
        ("unet", 4),
        ("unet", 8),
    }
    assert [item["observation"] for item in first] == [1, 2]


def test_schedule_filters_roles_and_qds_without_changing_order():
    schedule = runner.campaign_schedule(2, roles=("clip", "unet"), qds=(8, 2))

    assert len(schedule) == 8
    assert [(item["observation"], item["qd"], item["role"]) for item in schedule] == [
        (1, 2, "clip"),
        (1, 2, "unet"),
        (1, 8, "clip"),
        (1, 8, "unet"),
        (2, 2, "clip"),
        (2, 2, "unet"),
        (2, 8, "clip"),
        (2, 8, "unet"),
    ]


def test_campaign_records_selected_geometry_and_rejects_mismatch(tmp_path: Path):
    async def fake_call(_function, item):
        return _valid_result(item)

    output = asyncio.run(
        runner.run_campaign(
            "test-c9",
            tmp_path,
            function=object(),
            call=fake_call,
            observations=2,
            roles="unet",
            qds="8",
        )
    )
    assert len(output["results"]) == 2
    ledger = json.loads((tmp_path / "ledger.json").read_text(encoding="utf-8"))
    assert ledger["geometry"]["roles"] == ["unet"]
    assert ledger["geometry"]["qd_values"] == [8]
    assert ledger["geometry"]["expected_attempts_per_run"] == 2

    try:
        asyncio.run(
            runner.run_campaign(
                "test-c9",
                tmp_path,
                function=object(),
                call=fake_call,
                observations=2,
                roles="unet",
                qds="2,4,8",
            )
        )
    except RuntimeError as exc:
        assert "geometry mismatch" in str(exc)
    else:
        raise AssertionError("ledger geometry mismatch was reused")


def test_validation_rejects_non_32mib_or_non_source_result():
    item = runner.campaign_schedule()[0]
    result = _valid_result(item)
    result["source_block_bytes"] = 64 * 1024 * 1024
    result["fixed_config"]["source_block_bytes"] = 64 * 1024 * 1024
    failures = runner.validate_c9_result(result, item)
    assert "top_level_block_bytes_mismatch" in failures
    assert "fixed_config_source_block_bytes_mismatch" in failures


def test_campaign_calls_are_strictly_serial_and_keeps_ledger(tmp_path: Path):
    active = 0
    maximum = 0
    calls: list[str] = []

    async def fake_call(_function, item):
        nonlocal active, maximum
        active += 1
        maximum = max(maximum, active)
        calls.append(item["attempt_id"])
        await asyncio.sleep(0)
        active -= 1
        return _valid_result(item)

    output = asyncio.run(runner.run_campaign("test-c9", tmp_path, function=object(), call=fake_call))
    assert maximum == 1
    assert len(calls) == 60
    assert len(output["results"]) == 60
    ledger = json.loads((tmp_path / "ledger.json").read_text(encoding="utf-8"))
    assert ledger["status"] == "COMPLETE"
    assert len(ledger["attempts"]) == 60
    assert all(item["status"] == "COMPLETE" for item in ledger["attempts"])
    assert len(list((tmp_path / "runs").glob("*.json"))) == 60


def test_campaign_records_remote_failure(tmp_path: Path):
    async def failing_call(_function, item):
        if item["campaign_index"] == 1:
            raise RuntimeError("synthetic remote failure")
        return _valid_result(item)

    output = asyncio.run(runner.run_campaign("test-c9", tmp_path, function=object(), call=failing_call))
    assert output["results"][0]["classification"] == "DNF"
    ledger = json.loads((tmp_path / "ledger.json").read_text(encoding="utf-8"))
    assert ledger["attempts"][0]["status"] == "FAILED"
    assert len(ledger["attempts"]) == 60


def test_source_only_uses_one_fd_reusable_buffer_and_32mib_tail(tmp_path, monkeypatch):
    payload = b"x" * (32 * 1024 * 1024 + 5)
    header = json.dumps({"x": {"data_offsets": [0, len(payload)]}}, separators=(",", ":")).encode()
    path = tmp_path / "model.safetensors"
    path.write_bytes(struct.pack("<Q", len(header)) + header + payload)

    allocations = []

    class FakeTensor(bytearray):
        nbytes = 32 * 1024 * 1024

        def numpy(self):
            return self

        def is_pinned(self):
            return True

    class FakeTorch:
        uint8 = object()
        __version__ = "fake"
        version = type("Version", (), {"cuda": "fake-cuda"})()
        cuda = type("Cuda", (), {
            "is_available": staticmethod(lambda: True),
            "get_device_name": staticmethod(lambda _index: "fake-gpu"),
        })()

        @staticmethod
        def empty(size, *, dtype, pin_memory):
            assert dtype is FakeTorch.uint8
            assert pin_memory is True
            allocations.append((size, threading.current_thread().name))
            return FakeTensor(size)

    reads = []

    def preadv(fd, buffers, offset):
        target = buffers[0]
        with path.open("rb") as handle:
            handle.seek(offset)
            data = handle.read(len(target))
        target[:len(data)] = data
        reads.append((fd, offset, len(target), len(data)))
        return len(data)

    monkeypatch.setattr(oracle, "_import_torch", lambda: FakeTorch)
    oracle._TORCH_IMPORTED = True
    monkeypatch.setattr(oracle.os, "preadv", preadv, raising=False)
    result = oracle._run_source_only(str(path), "clip", 1, 32 * 1024 * 1024)

    assert result["status"] == "ok"
    assert allocations == [(32 * 1024 * 1024, "MainThread")]
    assert len({fd for fd, *_ in reads}) == 1
    assert [request for _, _, request, _ in reads] == [32 * 1024 * 1024, 5]
    assert result["read_size_evidence"][-1]["returned_bytes"] == 5
    assert result["source_read_count"] == len(reads)
    assert result["metrics"]["source_read_count"] == len(reads)
    assert result["transport_stats"]["source_read_count"] == len(reads)
    assert result["physical_syscall_telemetry"] == []
    assert result["read_evidence_complete"] is False
    assert result["effective_gbps"] is not None
    assert "effective_GBps" not in result
    assert "effective_GBps" not in result["metrics"]
    assert result["buffer_type"] == "pytorch_pinned_host"
    assert result["pinned_host"] is True
    assert result["buffer_allocations"]["count"] == 1
    assert result["buffer_allocations"]["bytes_per_worker"] == 32 * 1024 * 1024
    assert result["buffer_allocations"]["reusable_lifetime"] == "worker_source_wall"
    assert result["buffer_allocations"]["is_pinned"] is True
    assert result["hashing_in_timed_loop"] is False
    assert result["allocation_in_timed_loop"] is False
    assert result["telemetry_in_timed_loop"] is False
    assert result["timing_boundary"]["name"] == "THREAD_START_TO_JOIN_WALL"
    assert result["C9_TOTAL_WALL_MS"] >= result["PHYSICAL_READ_SPAN_MS"]
    assert result["buffer_allocations"]["allocated_before_source_wall"] is True


def test_source_only_allocates_each_buffer_in_worker_and_reconciles_ranges(tmp_path, monkeypatch):
    payload = b"y" * (64 * 1024 * 1024 + 7)
    header = json.dumps({"x": {"data_offsets": [0, len(payload)]}}, separators=(",", ":")).encode()
    path = tmp_path / "model.safetensors"
    path.write_bytes(struct.pack("<Q", len(header)) + header + payload)

    allocations = []

    class FakeTensor(bytearray):
        nbytes = 32 * 1024 * 1024

        def numpy(self):
            return self

        def is_pinned(self):
            return True

    class FakeTorch:
        uint8 = object()
        version = type("Version", (), {"cuda": "fake-cuda"})()
        cuda = type("Cuda", (), {
            "is_available": staticmethod(lambda: True),
            "get_device_name": staticmethod(lambda _index: "fake-gpu"),
        })()

        @staticmethod
        def empty(size, *, dtype, pin_memory):
            assert dtype is FakeTorch.uint8
            assert pin_memory is True
            allocations.append((size, threading.current_thread().name))
            return FakeTensor(size)

    reads = []

    def preadv(fd, buffers, offset):
        target = buffers[0]
        with path.open("rb") as handle:
            handle.seek(offset)
            data = handle.read(len(target))
        target[:len(data)] = data
        reads.append((fd, offset, len(data)))
        return len(data)

    monkeypatch.setattr(oracle, "_import_torch", lambda: FakeTorch)
    oracle._TORCH_IMPORTED = True
    monkeypatch.setattr(oracle.os, "preadv", preadv, raising=False)
    result = oracle._run_source_only(str(path), "unet", 2, 32 * 1024 * 1024)

    assert result["status"] == "ok"
    assert sorted(allocations) == [
        (32 * 1024 * 1024, "MainThread"),
        (32 * 1024 * 1024, "MainThread"),
    ]
    assert result["source_bytes"] == len(payload)
    assert result["coverage"]["returned_bytes"] == len(payload)
    assert result["coverage"]["ok"] is True
    assert len({fd for fd, _, _ in reads}) == 1
    assert len(result["workers"]) == 2
    ranges = [(row["region_start"], row["region_end"]) for row in result["workers"]]
    assert ranges[0][1] == ranges[1][0]
    assert result["buffer_allocations"]["allocation_in_c9_total_wall"] is False
    assert result["buffer_allocations"]["allocated_before_source_wall"] is True


def test_source_only_imports_torch_before_c9_timing_boundary(tmp_path, monkeypatch):
    payload = b"payload"
    header = json.dumps({"x": {"data_offsets": [0, len(payload)]}}).encode()
    path = tmp_path / "model.safetensors"
    path.write_bytes(struct.pack("<Q", len(header)) + header + payload)
    events = []

    class RecordingThread(threading.Thread):
        def __init__(self, *args, **kwargs):
            events.append("thread_constructed")
            super().__init__(*args, **kwargs)

        def start(self):
            events.append("thread_started")
            return super().start()

    class FakeTensor(bytearray):
        nbytes = len(payload)

        def numpy(self):
            return self

        def is_pinned(self):
            return True

    class FakeTorch:
        uint8 = object()
        version = type("Version", (), {"cuda": "fake-cuda"})()
        cuda = type("Cuda", (), {
            "is_available": staticmethod(lambda: False),
        })()

        @staticmethod
        def empty(size, *, dtype, pin_memory):
            assert dtype is FakeTorch.uint8
            assert pin_memory is True
            return FakeTensor(size)

    def import_torch():
        events.append("torch_import")
        return FakeTorch

    clock = 0

    def monotonic_ns():
        nonlocal clock
        events.append("timing_clock")
        clock += 1
        return clock

    def preadv(_fd, buffers, offset):
        target = buffers[0]
        data = path.read_bytes()[offset:offset + len(target)]
        target[:len(data)] = data
        return len(data)

    monkeypatch.setattr(oracle, "_import_torch", import_torch)
    monkeypatch.setattr(oracle.threading, "Thread", RecordingThread)
    monkeypatch.setattr(oracle.time, "monotonic_ns", monotonic_ns)
    monkeypatch.setattr(oracle.os, "preadv", preadv, raising=False)

    result = oracle._run_source_only(str(path), "clip", 1, len(payload))

    assert result["status"] == "ok"
    assert events.index("torch_import") < events.index("timing_clock")
    constructed = [index for index, event in enumerate(events) if event == "thread_constructed"]
    started = [index for index, event in enumerate(events) if event == "thread_started"]
    clocks = [index for index, event in enumerate(events) if event == "timing_clock"]
    assert constructed and started and clocks
    assert max(constructed) < min(clocks) < min(started)


def test_cpu_validation_rejects_any_non_12_result():
    item = runner.campaign_schedule(1)[0]
    result = _valid_result(item)
    result["cpu_allocation"]["observed_runtime_shape_cpu_request"] = 11
    assert "cpu_observed_not_12" in runner.validate_c9_result(result, item)


def test_torch_pinned_allocation_is_exact_and_has_no_fallback(monkeypatch):
    calls = []

    class Tensor(bytearray):
        def is_pinned(self):
            return True

        def numpy(self):
            return self

    class FakeTorch:
        uint8 = object()

        @staticmethod
        def empty(size, *, dtype, pin_memory):
            calls.append((size, dtype, pin_memory))
            return Tensor(size)

    monkeypatch.setattr(oracle, "_import_torch", lambda: FakeTorch)
    tensor = oracle._allocate_pinned_buffer(4096)
    assert calls == [(4096, FakeTorch.uint8, True)]
    assert tensor.is_pinned() is True


def test_torch_pinned_allocation_fails_closed(monkeypatch):
    class Tensor(bytearray):
        def is_pinned(self):
            return False

    class FakeTorch:
        uint8 = object()

        @staticmethod
        def empty(size, *, dtype, pin_memory):
            return Tensor(size)

    monkeypatch.setattr(oracle, "_import_torch", lambda: FakeTorch)
    try:
        oracle._allocate_pinned_buffer(4096)
    except RuntimeError as exc:
        assert "not_pinned" in str(exc)
    else:
        raise AssertionError("allocation did not fail closed")


def test_source_run_records_allocation_error_and_never_falls_back(tmp_path, monkeypatch):
    payload = b"payload"
    header = json.dumps({"x": {"data_offsets": [0, len(payload)]}}).encode()
    path = tmp_path / "model.safetensors"
    path.write_bytes(struct.pack("<Q", len(header)) + header + payload)
    preadv_calls = []

    def fail_allocation(_size):
        raise MemoryError("synthetic pinned allocation failure")

    monkeypatch.setattr(oracle, "_import_torch", lambda: object())
    monkeypatch.setattr(oracle, "_allocate_pinned_buffer", fail_allocation)
    monkeypatch.setattr(
        oracle.os, "preadv", lambda *args: preadv_calls.append(args) or 0, raising=False
    )
    result = oracle._run_source_only(str(path), "clip", 2, 32 * 1024 * 1024)
    assert result["status"] == "error"
    assert "MemoryError:synthetic pinned allocation failure" in result["error"]
    assert result["pinned_host_evidence"]["buffers"][0]["allocation_exception"] == (
        "MemoryError:synthetic pinned allocation failure"
    )
    assert len(result["pinned_host_evidence"]["buffers"]) == 1
    assert all(
        buffer["allocation_exception"] == "MemoryError:synthetic pinned allocation failure"
        for buffer in result["pinned_host_evidence"]["buffers"]
    )
    assert preadv_calls == []


def test_capability_shape_does_not_read_or_copy(monkeypatch):
    class Tensor(bytearray):
        def is_pinned(self):
            return True

        def numpy(self):
            return self

    class FakeTorch:
        uint8 = object()
        __version__ = "fake"
        version = type("Version", (), {"cuda": "fake-cuda"})()
        cuda = type("Cuda", (), {
            "is_available": staticmethod(lambda: True),
            "get_device_name": staticmethod(lambda _index: "fake-gpu"),
        })()

        @staticmethod
        def empty(size, *, dtype, pin_memory):
            return Tensor(size)

    monkeypatch.setattr(oracle, "_import_torch", lambda: FakeTorch)
    result = oracle.run_c9_capability_smoke(2)
    assert result["status"] == "ok"
    assert result["model_read"] is False
    assert result["h2d_pipeline_initialized"] is False
    assert result["torch_imported"] is True
    assert len(result["buffers"]) == 2
    assert all(row["is_pinned"] is True for row in result["buffers"])


def test_cpu_validation_uses_runtime_shape_field_over_process_cpu_count():
    item = runner.campaign_schedule(1)[0]
    result = _valid_result(item)
    result["cpu_allocation"]["observed_cpu"] = 21
    assert not any(
        failure.startswith("cpu_") for failure in runner.validate_c9_result(result, item)
    )


def test_wrapper_returns_oracle_error_without_secondary_block_check(monkeypatch):
    oracle_error = {
        "status": "error",
        "error": "RuntimeError:torch.empty pinned allocation failed",
    }
    monkeypatch.setattr(oracle, "run_source_only", lambda *args, **kwargs: oracle_error)

    result = recovery.run_c9_recovery.local(
        "clip", recovery.MODELS["clip"], 2, "attempt-1"
    )

    assert result is oracle_error


def test_wrapper_copies_runtime_shape_cpu_evidence(monkeypatch):
    item = runner.campaign_schedule(1)[0]
    oracle_result = _valid_result(item)
    oracle_result["identity"] = {
        "cpu_allocation": {
            "cpu_request": 12,
            "observed_runtime_shape_cpu_request": 12,
        }
    }
    oracle_result["workers"] = [{"producer_id": n} for n in range(item["qd"])]
    oracle_result["regions"] = [
        {"producer_id": n, "region_id": n, "start": 0, "end": 12}
        for n in range(item["qd"])
    ]
    monkeypatch.setattr(oracle, "run_source_only", lambda *args, **kwargs: oracle_result)

    result = recovery.run_c9_recovery.local(
        item["role"], item["model_name"], item["qd"], "attempt-2"
    )

    assert result["cpu_allocation"]["observed_cpu"] == 12
    assert result["cpu_observed"] == 12


def test_runner_rejects_non_testing_7_workspace(tmp_path, monkeypatch):
    registry = {
        "active_workspace_id": "wrong",
        "workspaces": [{"id": "wrong", "label": "Default", "token_id": "ak-id", "token_secret": "as-secret"}],
    }
    (tmp_path / ".modal_workspaces.json").write_text(json.dumps(registry), encoding="utf-8")
    monkeypatch.setattr(runner, "_ROOT", tmp_path)
    try:
        runner._active_workspace()
    except RuntimeError as exc:
        assert "Testing 7" in str(exc)
    else:
        raise AssertionError("workspace policy did not fail closed")
