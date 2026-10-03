from __future__ import annotations

import os
import sys
from types import SimpleNamespace

import pytest

from comfymodal_runtime import source_latency_telemetry as telemetry


pytestmark = pytest.mark.fast_unit


def _operation(
    ordinal: int,
    duration_ms: float | int,
    *,
    reader_id: int = 0,
    nbytes: int = 1,
    source_offset: int | None = None,
    ready_ns: int | None = None,
) -> dict[str, int]:
    start_ns = 1_000_000_000 + ordinal * 1_000_000
    return {
        "ordinal": ordinal,
        "reader_id": reader_id,
        "source_offset": ordinal if source_offset is None else source_offset,
        "nbytes": nbytes,
        "memcpy_start_ns": start_ns,
        "memcpy_end_ns": start_ns + int(duration_ms * 1_000_000),
        "slot_wait_ns": 2_000_000,
        "pacing_wait_ns": 3_000_000,
        "ready_ns": (start_ns + 4_000_000) if ready_ns is None else ready_ns,
    }


def test_duration_summary_has_expected_percentiles_and_mean() -> None:
    operations = [_operation(index, value) for index, value in enumerate([10, 20, 30, 40, 50])]

    summary = telemetry.summarize_source_operations(operations)

    assert summary["memcpy_duration_ms"] == {
        "min": 10.0,
        "p50": 30.0,
        "p90": 46.0,
        "p95": 48.0,
        "max": 50.0,
        "mean": 30.0,
    }


def test_empty_duration_summary_uses_none_for_every_duration_field() -> None:
    summary = telemetry.summarize_source_operations([])

    assert summary["memcpy_duration_ms"] == {
        "min": None,
        "p50": None,
        "p90": None,
        "p95": None,
        "max": None,
        "mean": None,
    }


def test_memcpy_stall_counts_use_strict_thresholds() -> None:
    durations = [50, 100, 250, 500, 1000, 60, 200, 300, 600, 1100]
    summary = telemetry.summarize_source_operations(
        [_operation(index, duration) for index, duration in enumerate(durations)]
    )

    assert summary["memcpy_counts"] == {
        "gt_50ms": 9,
        "gt_100ms": 7,
        "gt_250ms": 5,
        "gt_500ms": 3,
        "gt_1000ms": 1,
    }


def test_per_reader_aggregation_is_sorted_and_preserves_uneven_counts() -> None:
    operations = [
        _operation(0, 1, reader_id=0, nbytes=10),
        _operation(1, 2, reader_id=0, nbytes=20),
        _operation(2, 3, reader_id=0, nbytes=30),
        _operation(3, 4, reader_id=0, nbytes=40),
        _operation(4, 5, reader_id=0, nbytes=50),
        _operation(5, 10, reader_id=1, nbytes=100),
        _operation(6, 20, reader_id=3, nbytes=200),
        _operation(7, 30, reader_id=3, nbytes=300),
    ]

    per_reader = telemetry.summarize_source_operations(operations)["per_reader"]

    assert per_reader == [
        {
            "reader_id": 0,
            "operation_count": 5,
            "bytes": 150,
            "memcpy_total_ms": 15.0,
            "memcpy_mean_ms": 3.0,
            "memcpy_max_ms": 5.0,
        },
        {
            "reader_id": 1,
            "operation_count": 1,
            "bytes": 100,
            "memcpy_total_ms": 10.0,
            "memcpy_mean_ms": 10.0,
            "memcpy_max_ms": 10.0,
        },
        {
            "reader_id": 3,
            "operation_count": 2,
            "bytes": 500,
            "memcpy_total_ms": 50.0,
            "memcpy_mean_ms": 25.0,
            "memcpy_max_ms": 30.0,
        },
    ]


def test_first_eight_operations_are_lowest_ordinals_in_ordinal_order() -> None:
    operations = [_operation(ordinal, ordinal + 1) for ordinal in range(11)]
    shuffled = [operations[index] for index in [8, 2, 10, 0, 7, 4, 9, 1, 6, 3, 5]]

    first_eight = telemetry.summarize_source_operations(shuffled)["first_8_operations"]

    assert [item["ordinal"] for item in first_eight] == list(range(8))
    assert len(first_eight) == 8
    assert all(
        set(item) == {
            "ordinal",
            "reader_id",
            "source_offset",
            "memcpy_ms",
            "slot_wait_ms",
            "pacing_wait_ms",
        }
        for item in first_eight
    )


def test_thirds_use_earlier_extra_elements_and_cover_seven_operations() -> None:
    summary = telemetry.summarize_source_operations(
        [_operation(index, index + 1) for index in range(7)]
    )

    assert summary["thirds"] == {
        "first_third": {"p50": 2.0, "max": 3.0},
        "middle_third": {"p50": 4.5, "max": 5.0},
        "final_third": {"p50": 6.5, "max": 7.0},
    }


@pytest.mark.parametrize("count", [0, 1, 2])
def test_thirds_with_fewer_than_three_operations_are_fail_soft(count: int) -> None:
    thirds = telemetry.summarize_source_operations(
        [_operation(index, index + 1) for index in range(count)]
    )["thirds"]

    if count == 0:
        assert thirds["first_third"] == {"p50": None, "max": None}
    else:
        assert thirds["first_third"] == {"p50": 1.0, "max": 1.0}
    if count < 2:
        assert thirds["middle_third"] == {"p50": None, "max": None}
    else:
        assert thirds["middle_third"] == {"p50": 2.0, "max": 2.0}
    assert thirds["final_third"]["p50"] is None
    assert thirds["final_third"]["max"] is None


def test_first_operation_uses_lowest_ordinal_but_first_completion_uses_ready_time() -> None:
    source_start_ns = 1_000_000_000
    operations = [
        {
            **_operation(2, 1, ready_ns=1_100_000_000),
            "source_offset": 200,
        },
        {
            **_operation(1, 7, ready_ns=1_200_000_000),
            "source_offset": 100,
        },
    ]

    summary = telemetry.summarize_source_operations(
        operations,
        source_span={"source_start_ns": source_start_ns},
    )

    assert summary["first_operation_memcpy_ms"] == 7.0
    assert summary["first_completed_operation_ms_from_source_start"] == 100.0


@pytest.mark.parametrize("source_span", [None, {}, {"source_end_ns": 2_000_000_000}])
def test_first_completion_is_none_without_source_start(source_span) -> None:
    summary = telemetry.summarize_source_operations(
        [_operation(0, 1, ready_ns=1_100_000_000)], source_span=source_span
    )

    assert summary["first_completed_operation_ms_from_source_start"] is None


def test_summarize_first_h2d_computes_all_three_intervals() -> None:
    result = telemetry.summarize_first_h2d(
        [_operation(0, 1, ready_ns=1_050_000_000)],
        source_start_ns=1_000_000_000,
        first_h2d_submit_ns=1_080_000_000,
        first_h2d_completion_ns=1_130_000_000,
    )

    assert result == {
        "source_start_to_first_ready_ms": 50.0,
        "source_start_to_first_h2d_submit_ms": 80.0,
        "first_h2d_submit_to_completion_ms": 50.0,
    }


@pytest.mark.parametrize(
    ("missing", "expected_none"),
    [
        ("source_start_ns", "source_start_to_first_ready_ms"),
        ("first_h2d_submit_ns", "source_start_to_first_h2d_submit_ms"),
        ("first_h2d_completion_ns", "first_h2d_submit_to_completion_ms"),
    ],
)
def test_summarize_first_h2d_missing_one_input_is_fail_soft(missing, expected_none) -> None:
    values: dict[str, int | None] = {
        "source_start_ns": 1_000_000_000,
        "first_h2d_submit_ns": 1_080_000_000,
        "first_h2d_completion_ns": 1_130_000_000,
    }
    values[missing] = None

    result = telemetry.summarize_first_h2d([], **values)

    assert result[expected_none] is None


def test_summarize_first_h2d_with_all_inputs_missing_returns_three_none_values() -> None:
    assert telemetry.summarize_first_h2d(
        None,
        source_start_ns=None,
        first_h2d_submit_ns=None,
        first_h2d_completion_ns=None,
    ) == {
        "source_start_to_first_ready_ms": None,
        "source_start_to_first_h2d_submit_ms": None,
        "first_h2d_submit_to_completion_ms": None,
    }


def test_already_computed_counter_scalars_are_emitted_under_documented_names() -> None:
    counters = {
        "source_wall_ms": 12.5,
        "source_gbps": 3.4,
        "effective_reader_concurrency": 2.5,
        "time_weighted_reader_concurrency": {
            "effective_concurrency": 3.25,
            "below_four_reader_ns": 11_000_000,
            "longest_zero_reader_ns": 12_000_000,
        },
        "slot_acquire_wait_ns": 13_000_000,
        "slot_acquire_wait_count": 14,
        "all_slots_occupied_count": 15,
        "capacity_wait_ns": 16_000_000,
        "capacity_wait_count": 17,
        "ready_queue_wait_ns": 18_000_000,
        "ready_queue_wait_count": 19,
        "pacing_wait_count": 20,
        "pacing_zero_delay_count": 21,
        "min_source_gap_ns": 22_000_000,
        "pacer_gap_violation_count": 23,
        "source_final_byte_complete_ns": 24_000_000_000,
        "final_h2d_submit_ns": 25_000_000_000,
        "final_h2d_completion_observed_ns": 26_000_000_000,
        "gpu_ready_tail_ms": 27.5,
    }

    summary = telemetry.summarize_source_operations([], counters_source=counters)

    assert summary["source_wall_ms"] == 12.5
    assert summary["source_gbps"] == 3.4
    assert summary["effective_reader_concurrency"] == 2.5
    assert summary["time_weighted_effective_concurrency"] == 3.25
    assert summary["below_four_reader_ms"] == 11.0
    assert summary["longest_zero_reader_ms"] == 12.0
    assert summary["slot_wait_ms"] == 13.0
    assert summary["slot_wait_count"] == 14
    assert summary["all_slots_occupied_count"] == 15
    assert summary["capacity_wait_ms"] == 16.0
    assert summary["capacity_wait_count"] == 17
    assert summary["ready_queue_wait_ms"] == 18.0
    assert summary["ready_queue_wait_count"] == 19
    assert summary["pacing_wait_count"] == 20
    assert summary["pacing_zero_delay_count"] == 21
    assert summary["min_source_gap_ms"] == 22.0
    assert summary["pacer_gap_violation_count"] == 23
    assert summary["source_final_byte_complete_ns"] == 24_000_000_000
    assert summary["final_h2d_submit_ns"] == 25_000_000_000
    assert summary["final_h2d_completion_observed_ns"] == 26_000_000_000
    assert summary["gpu_ready_tail_ms"] == 27.5


def test_malformed_records_are_ignored_and_negative_duration_is_not_reported() -> None:
    operations = [
        None,
        "not a record",
        {"ordinal": "wrong", "memcpy_start_ns": 0, "memcpy_end_ns": 1},
        {"ordinal": 0, "memcpy_start_ns": 2_000_000, "memcpy_end_ns": 1_000_000},
        {"ordinal": 1, "reader_id": "wrong", "nbytes": "wrong"},
        _operation(2, 4),
    ]

    summary = telemetry.summarize_source_operations(operations)

    assert summary["operation_count"] == 3
    assert summary["memcpy_duration_ms"] == {
        "min": 4.0,
        "p50": 4.0,
        "p90": 4.0,
        "p95": 4.0,
        "max": 4.0,
        "mean": 4.0,
    }
    assert summary["memcpy_counts"] == {
        "gt_50ms": 0,
        "gt_100ms": 0,
        "gt_250ms": 0,
        "gt_500ms": 0,
        "gt_1000ms": 0,
    }


def test_large_summary_has_no_recursive_list_longer_than_eight() -> None:
    summary = telemetry.summarize_source_operations(
        [_operation(index, 1, reader_id=0) for index in range(40)]
    )

    def assert_compact(value) -> None:
        if isinstance(value, list):
            assert len(value) <= 8
            for item in value:
                assert_compact(item)
        elif isinstance(value, dict):
            for item in value.values():
                assert_compact(item)

    assert_compact(summary)


def _install_single_gpu_probe(monkeypatch) -> None:
    class FakeCuda:
        @staticmethod
        def device_count() -> int:
            return 1

        @staticmethod
        def current_device() -> int:
            return 0

        @staticmethod
        def get_device_name(index: int) -> str:
            return "synthetic GPU"

        @staticmethod
        def get_device_capability(index: int) -> tuple[int, int]:
            return (8, 0)

    monkeypatch.setitem(sys.modules, "torch", SimpleNamespace(cuda=FakeCuda()))

    def no_nvml(name: str):
        raise ImportError(name)

    monkeypatch.setattr(telemetry.importlib, "import_module", no_nvml)
    monkeypatch.setattr(telemetry, "_current_cpu", lambda: 7)
    monkeypatch.setattr(os, "sched_getaffinity", lambda pid: {2, 4}, raising=False)
    monkeypatch.setattr(telemetry, "_arena_numa_pages", lambda name: None)


def test_placement_collection_is_fail_soft_memoized_and_has_documented_sections(
    monkeypatch,
) -> None:
    _install_single_gpu_probe(monkeypatch)
    previous_cache = telemetry._PLACEMENT_CACHE
    telemetry._PLACEMENT_CACHE = None
    try:
        first = telemetry.collect_placement_telemetry()
        second = telemetry.collect_placement_telemetry(
            arena_name="different", arena_bytes=123, source_child_pid=456
        )
        assert first is second
    finally:
        telemetry._PLACEMENT_CACHE = previous_cache

    assert first["status"] in {"ok", "degraded"}
    assert {"parent", "source", "arena", "gpu"}.issubset(first)
    assert first["arena"]["shared_memory_name"] is None
    assert "arena.shared_memory_name" in first["unavailable"]


def test_placement_does_not_guess_pci_id_when_sysfs_has_no_uevent(monkeypatch, tmp_path) -> None:
    device = tmp_path / "class" / "drm" / "card0" / "device"
    device.mkdir(parents=True)
    monkeypatch.setattr(telemetry, "SYSFS_ROOT", str(tmp_path))
    _install_single_gpu_probe(monkeypatch)
    previous_cache = telemetry._PLACEMENT_CACHE
    telemetry._PLACEMENT_CACHE = None
    try:
        result = telemetry.collect_placement_telemetry()
    finally:
        telemetry._PLACEMENT_CACHE = previous_cache

    assert result["gpu"]["pci_bus_id"] is None
    assert "gpu.pci_bus_id" in result["unavailable"]


def test_placement_reads_pci_id_and_numa_node_from_sysfs(monkeypatch, tmp_path) -> None:
    device = tmp_path / "class" / "drm" / "card0" / "device"
    device.mkdir(parents=True)
    (device / "uevent").write_text(
        "DRIVER=nvidia\nPCI_SLOT_NAME=0000:41:00.0\n", encoding="utf-8"
    )
    (device / "numa_node").write_text("0\n", encoding="utf-8")
    monkeypatch.setattr(telemetry, "SYSFS_ROOT", str(tmp_path))
    _install_single_gpu_probe(monkeypatch)
    previous_cache = telemetry._PLACEMENT_CACHE
    telemetry._PLACEMENT_CACHE = None
    try:
        result = telemetry.collect_placement_telemetry()
    finally:
        telemetry._PLACEMENT_CACHE = previous_cache

    assert result["gpu"]["pci_bus_id"] == "0000:41:00.0"
    assert result["gpu"]["gpu_numa_node"] == 0


def test_placement_reports_unavailable_pci_when_sysfs_probe_returns_none(monkeypatch) -> None:
    _install_single_gpu_probe(monkeypatch)
    monkeypatch.setattr(telemetry, "_sysfs_gpu", lambda index: (None, None))
    previous_cache = telemetry._PLACEMENT_CACHE
    telemetry._PLACEMENT_CACHE = None
    try:
        result = telemetry.collect_placement_telemetry()
    finally:
        telemetry._PLACEMENT_CACHE = previous_cache

    assert result["gpu"]["pci_bus_id"] is None
    assert "gpu.pci_bus_id" in result["unavailable"]
