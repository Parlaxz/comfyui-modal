"""Focused validation for the experimental strict CPU-I/O process (Phase 2).

Proves the child performs real storage reads into the process-shared ring, the
parent copies shared -> its target exactly, and the child remains CUDA-sterile.
No GPU/CUDA is required by this test.
"""

from __future__ import annotations

import os

from comfymodal_runtime.golden_io_process import (
    IO_SLOTS,
    IO_SLOT_BYTES,
    GoldenIoProcess,
    io_process_enabled,
)


def test_flag_default_off():
    os.environ.pop("COMFYMODAL_GOLDEN_IO_PROCESS", None)
    assert io_process_enabled() is False
    os.environ["COMFYMODAL_GOLDEN_IO_PROCESS"] = "0"
    assert io_process_enabled() is False
    os.environ["COMFYMODAL_GOLDEN_IO_PROCESS"] = "1"
    try:
        assert io_process_enabled() is True
    finally:
        os.environ.pop("COMFYMODAL_GOLDEN_IO_PROCESS", None)


def test_geometry_matches_transport(tmp_path):
    assert IO_SLOTS == 8
    assert IO_SLOT_BYTES == 32 * 1024 * 1024


def test_child_roundtrip_exact_and_cuda_sterile(tmp_path):
    data = os.urandom(1024 * 1024)
    blob = tmp_path / "payload.bin"
    blob.write_bytes(data)

    worker = GoldenIoProcess()
    try:
        record = worker.start()
        assert record["slot_count"] == IO_SLOTS
        assert record["slot_bytes"] == IO_SLOT_BYTES
        assert record["pid"] == worker.pid

        # Exact whole-file read into the parent target.
        target = bytearray(len(data))
        got = worker.readinto(str(blob), target, 0, 0)
        assert got == len(data)
        assert bytes(target) == data

        # Positioned read with an arbitrary offset and length.
        target2 = bytearray(4096)
        got2 = worker.readinto(str(blob), target2, 12345, 0)
        assert got2 == 4096
        assert bytes(target2) == data[12345 : 12345 + 4096]

        # The child must remain CUDA-sterile from spawn through reads.
        probe = worker.probe()
        assert probe["pid_match"] is True
        assert probe["child_cuda_initialized"] is False
        assert probe["child_cuda_tasks_run"] == 0
        assert probe["child_gpu_alloc_bytes"] == 0
        assert probe["spawn_count"] == 1

        # shared -> pinned accounting reflects the real copied bytes.
        assert worker.shared_to_pinned_bytes == len(data) + 4096
        assert worker.shared_to_pinned_ms > 0.0
    finally:
        worker.stop()
