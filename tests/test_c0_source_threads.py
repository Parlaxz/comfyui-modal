"""Focused contracts for the opt-in C0 source-thread protocol."""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest

from comfymodal_runtime import golden_source_threads as source

pytestmark = pytest.mark.fast_unit


def test_geometry_is_exactly_eight_64m_slots_and_four_threads() -> None:
    assert source.geometry() == {
        "arena_bytes": 8 * 64 * 1024 * 1024,
        "slot_count": 8,
        "slot_bytes": 64 * 1024 * 1024,
        "thread_count": 4,
        "pacer_gap_ns": 4_000_000,
    }


def test_plan_is_self_serve_and_has_no_per_block_command_surface() -> None:
    manager_calls: list[object] = []

    class FakeManager:
        def plan_once(self, **kwargs):
            manager_calls.append(("plan", kwargs))

        def wait_ready(self, _timeout):
            if not hasattr(self, "records"):
                self.records = [
                    source.ReadyRecord(i, 1, i * 4, i * 4, 4, i, i, i + 10,
                                       f"planned-{i}", 1)
                    for i in range(2)
                ]
            return self.records.pop(0) if self.records else None

        def claim_ready(self, record):
            manager_calls.append(("claim", record.range_index))
            return record

        def release_slot(self, record, **kwargs):
            manager_calls.append(("release", record.range_index))

    class Lease:
        def mark_filled(self, count):
            self.count = count

        def retire(self):
            raise AssertionError("bridge must let transport.publish retire the lease")

    class FakeTransport:
        def acquire(self, **kwargs):
            lease = Lease()
            manager_calls.append(("acquire", kwargs["preferred_slot_index"]))
            return lease

        def publish(self, lease, record):
            manager_calls.append(("publish", record.record_id))

    ranges = [
        type("Range", (), {"source_offset": i * 4, "length": 4,
                            "target_offset": i * 4, "record_id": f"planned-{i}"})()
        for i in range(2)
    ]
    bridge = source.SourcePlanBridge(FakeManager(), FakeTransport())
    assert bridge.publish_all(
        ranges, generation=1, path="model.safetensors", identity=(1, 2, 8, 3),
        destination_size=8,
    ) == 2
    assert [item[0] for item in manager_calls].count("plan") == 1
    assert [item[0] for item in manager_calls].count("publish") == 2
    assert not any(item[0] == "fill" for item in manager_calls)


def test_pacer_has_no_sub_four_millisecond_gap_and_zero_waits() -> None:
    pacer = source.GlobalSourcePacer()
    starts = [pacer.reserve(now_ns=value)[0] for value in (0, 4_000_000, 8_000_000, 12_000_000)]
    assert starts == [0, 4_000_000, 8_000_000, 12_000_000]
    telemetry = pacer.telemetry()
    assert telemetry["source_gap_violation_count"] == 0
    assert telemetry["pacing_zero_delay_count"] == 4


def test_source_control_stale_generation_is_rejected() -> None:
    if source.os.name != "posix":
        pytest.skip("POSIX shared-memory lock protocol")
    manager = source.SourceThreadProcess.__new__(source.SourceThreadProcess)
    manager.control = source.shared_memory.SharedMemory(create=True, size=source.CONTROL_BYTES)
    manager.control.buf[:] = b"\0" * source.CONTROL_BYTES
    source._write_header(manager.control.buf, generation=7, plan_count=1, next_range=1,
                         ready_count=1, completed_count=0, failed_count=0)
    manager._lock = source._FileLock(str(Path(manager.control.name + ".lock").absolute()))
    manager.telemetry = {}
    record = source.ReadyRecord(0, 7, 0, 0, 4, 0, 0, 10)
    source._put_slot(manager.control.buf, 0, (source.READY, 7, 0, 0, 0, 4, 10, 0))
    manager.claim_ready(record)
    with pytest.raises(source.SourceProtocolError, match="stale_release_generation"):
        manager.release_slot(source.ReadyRecord(0, 6, 0, 0, 4, 0, 0, 10))
    manager.release_slot(record)
    manager.control.close()
    manager.control.unlink()
    manager._lock.close()


def test_source_module_is_cuda_sterile() -> None:
    path = Path(inspect.getfile(source))
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imports = [node for node in ast.walk(tree) if isinstance(node, (ast.Import, ast.ImportFrom))]
    names = {
        alias.name.split(".")[0]
        for node in imports
        for alias in node.names
    }
    assert "torch" not in names
    assert "cuda" not in names


def test_source_reader_uses_native_mmap_lifecycle_not_pread_bytes() -> None:
    text = Path(inspect.getfile(source)).read_text(encoding="utf-8")
    assert "ctypes.CDLL(None" in text
    assert "libc.mmap" in text
    assert "libc.memmove" in text
    assert "libc.munmap" in text
    assert "os.pread(" not in text
    assert "mmap_lifecycle" in text


def test_source_plan_requires_exact_destination_coverage() -> None:
    with pytest.raises(source.SourceProtocolError, match="destination_coverage_gap_or_overlap"):
        source.validate_plan(
            [source.SourceRange(0, 4, 0), source.SourceRange(4, 4, 8)],
            source_size=12,
            destination_size=12,
        )


def test_source_identity_and_geometry_are_explicit_in_runtime_source() -> None:
    text = Path(inspect.getfile(source)).read_text(encoding="utf-8")
    assert '"CUDA_VISIBLE_DEVICES": ""' in text
    assert "resource_tracker.unregister" in text
    assert '"thread_identities"' in text
    assert '"source_operation_records"' in text


def test_source_thread_transport_is_restore_owned_not_model_constructed() -> None:
    path = Path(__file__).parents[1] / "comfymodal_runtime" / "golden_model_transport.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    loader = next(
        node for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef)
        and node.name == "_load_c0_source_threads_sync"
    )
    assert not any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "GoldenQDTransport"
        for node in ast.walk(loader)
    )
    assert "source_transport_created_once" in path.read_text(encoding="utf-8")


def test_dispatcher_releases_external_source_slot_only_after_completion() -> None:
    from comfymodal_runtime.golden_qd_transport import (
        FakeBackend,
        GoldenQDTransport,
        SourceRange,
        StagingPool,
        TransportConfig,
    )

    pool = StagingPool(slots=1, block_bytes=4, capacity_class="source")
    backend = FakeBackend(destination=bytearray(4))
    transport = GoldenQDTransport(
        TransportConfig(
            queue_depth=1, block_bytes=4, staging_slots=1,
            ready_queue_capacity=1, producer_workers=1,
            capacity_class="source", h2d_target_bytes=4,
        ),
        backend,
        pool=pool,
    )
    released: list[bool] = []
    item = SourceRange(10, 4, 0, 1)
    lease = transport.acquire(
        declared_range=item, producer_id=0,
        preferred_slot_index=0, preferred_only=True,
    )
    lease.fill(b"abcd")
    lease._external_release_callback = lambda: released.append(True)
    transport.start(destination_size=4)
    transport.publish(lease, __import__(
        "comfymodal_runtime.golden_qd_transport", fromlist=["ReadyRecord"]
    ).ReadyRecord(10, 0, 4, 1, 0))
    result = transport.finalize_external_ready([item], destination_size=4)
    assert result.completed_bytes == 4
    assert released == [True]
    assert pool.states()[0].value == "free"


def test_clip_forward_telemetry_shape_keeps_meaningful_boundaries() -> None:
    serial_path = Path(__file__).parents[1] / "comfymodal_runtime" / "golden_serial.py"
    text = serial_path.read_text(encoding="utf-8")
    for boundary in (
        "clip_forward_entry_setup",
        "clip_tokenization_input_prep",
        "clip_qwen_transformer_forward",
        "clip_post_forward_sync_wait",
        "clip_conditioning_packaging",
    ):
        assert boundary in text
    assert "golden_clip_forward_decomposition_v2" in text
