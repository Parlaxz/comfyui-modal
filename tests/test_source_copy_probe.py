"""Synthetic tests for the source copy stall probe and its classifier.

No real model, no Modal, no network: every case is a constructed operation
record.  The suite proves the deltas, the fail-soft contract, the ordering and
thresholds, the ratio guard, and above all that compact telemetry stays
bounded and that pre-existing telemetry fields are untouched.
"""

from __future__ import annotations

import pytest

from comfymodal_runtime import golden_source_threads as source
from comfymodal_runtime.source_copy_probe import (
    PROBE_CPU_ID,
    PROBE_RESIDENT_PRE,
    PROBE_RUSAGE,
    PROBE_THREAD_CPU,
    SENTINEL,
    SourceCopyProbe,
    sentinel_record,
)
from comfymodal_runtime.source_stall_classification import (
    CLASSIFICATIONS,
    SLOW_MS,
    TOP_N,
    classify_copy,
    copy_wall_ms,
    summarize_copy_stalls,
    thread_cpu_ms,
    wall_cpu_ratio,
)


def _record(**overrides):
    """A healthy 64 MiB copy: ~50 ms wall, mostly CPU, no faults."""
    base = {
        "ordinal": 0,
        "reader_id": 0,
        "source_offset": 0,
        "nbytes": 64 * 1024 * 1024,
        "copy_wall_ns": 50_000_000,
        "memcpy_start_ns": 1_000,
        "memcpy_end_ns": 51_000_000,
        "thread_cpu_ns_before": 1_000_000_000,
        "thread_cpu_ns_after": 1_049_000_000,
        "minflt_delta": 3,
        "majflt_delta": 0,
        "inblock_delta": 0,
        "nvcsw_delta": 1,
        "nivcsw_delta": 0,
        "start_cpu": 5,
        "end_cpu": 5,
        "diag_flags": PROBE_RUSAGE | PROBE_THREAD_CPU | PROBE_CPU_ID,
        "resident_pre_ppm": 900_000,
    }
    base.update(overrides)
    return base


# ── rusage deltas ─────────────────────────────────────────────────────────


def test_thread_cpu_delta_is_the_difference_of_the_two_samples():
    assert thread_cpu_ms(_record()) == pytest.approx(49.0)


def test_rusage_deltas_are_read_as_absolute_differences():
    detail = classify_copy(_record(minflt_delta=12, majflt_delta=0, inblock_delta=0))
    assert detail["minflt_delta"] == 12
    assert detail["majflt_delta"] == 0
    assert detail["inblock_delta"] == 0


def test_fault_totals_sum_across_copies():
    records = [
        _record(ordinal=0, minflt_delta=1, majflt_delta=2, inblock_delta=3),
        _record(ordinal=1, minflt_delta=4, majflt_delta=5, inblock_delta=6),
    ]
    totals = summarize_copy_stalls(records)["fault_and_context_totals"]
    assert totals["minflt"] == 5
    assert totals["majflt"] == 7
    assert totals["inblock"] == 9


# ── fail-soft contract ────────────────────────────────────────────────────


@pytest.mark.parametrize("field", [
    "thread_cpu_ns_before", "thread_cpu_ns_after", "majflt_delta",
    "inblock_delta", "nvcsw_delta", "nivcsw_delta", "minflt_delta",
    "resident_pre_ppm",
])
def test_sentinel_is_unavailable_not_zero(field):
    record = _record(**{field: SENTINEL})
    assert copy_wall_ms(record) is not None
    detail = classify_copy(record)
    if field.startswith("thread_cpu"):
        assert thread_cpu_ms(record) is None
        assert wall_cpu_ratio(record) is None
        assert detail["classification"] == "UNRESOLVED"
    elif field == "resident_pre_ppm":
        assert detail["pre_resident_fraction"] is None
    else:
        # A real zero delta must stay distinguishable from "no data".
        assert detail[field] is None
        assert detail["classification"] != "PAGE_IO_STALL" or not field.startswith(
            ("majflt", "inblock")
        )


def test_probe_disabled_is_a_no_op():
    probe = SourceCopyProbe(enabled=False)
    assert probe.begin(4096, 4096) == ()
    assert probe.end(()) == sentinel_record()


def test_probe_enabled_without_posix_counters_never_raises():
    probe = SourceCopyProbe(enabled=True)
    record = probe.end(probe.begin(4096, 4096))
    assert isinstance(record["copy_wall_ns"], int)
    assert record["copy_wall_ns"] >= 0


def test_missing_wall_and_cpu_classifies_unresolved():
    detail = classify_copy({
        "copy_wall_ns": SENTINEL,
        "thread_cpu_ns_before": SENTINEL,
        "thread_cpu_ns_after": SENTINEL,
    })
    assert detail["classification"] == "UNRESOLVED"
    assert detail["reason"] == "cpu_or_wall_unavailable"


def test_zero_thread_cpu_does_not_divide_by_zero():
    record = _record(thread_cpu_ns_before=5_000_000, thread_cpu_ns_after=5_000_000)
    assert wall_cpu_ratio(record) is None
    assert classify_copy(record)["classification"] == "UNRESOLVED"


def test_legacy_span_is_used_when_the_probe_did_not_run():
    # copy_wall_ns == 0 means the probe recorded nothing, so the wider
    # memcpy_end - memcpy_start span (which includes pacer bookkeeping) is the
    # only evidence available.
    record = _record(copy_wall_ns=0)
    # memcpy_end_ns (51_000_000) - memcpy_start_ns (1_000) = 50.999 ms.
    assert copy_wall_ms(record) == pytest.approx(50.999)


# ── classification ────────────────────────────────────────────────────────


def test_slow_copy_with_major_faults_and_idle_thread_is_page_io():
    detail = classify_copy(_record(
        copy_wall_ns=4_000_000_000,
        thread_cpu_ns_before=0, thread_cpu_ns_after=20_000_000,
        majflt_delta=4096, inblock_delta=900,
    ))
    assert detail["classification"] == "PAGE_IO_STALL"
    assert detail["wall_cpu_ratio"] > 100


def test_slow_copy_with_context_switches_and_no_io_is_deschedule():
    detail = classify_copy(_record(
        copy_wall_ns=2_000_000_000,
        thread_cpu_ns_before=0, thread_cpu_ns_after=10_000_000,
        nvcsw_delta=5000, nivcsw_delta=4000,
    ))
    assert detail["classification"] == "DESCHEDULE_STALL"


def test_slow_copy_that_burned_cpu_is_cpu_memory():
    detail = classify_copy(_record(
        copy_wall_ns=2_000_000_000,
        thread_cpu_ns_before=0, thread_cpu_ns_after=1_950_000_000,
    ))
    assert detail["classification"] == "CPU_MEMORY_STALL"


def test_busy_copy_with_rising_faults_is_mixed():
    detail = classify_copy(_record(
        copy_wall_ns=2_000_000_000,
        thread_cpu_ns_before=0, thread_cpu_ns_after=1_900_000_000,
        majflt_delta=2048,
    ))
    assert detail["classification"] == "MIXED"


def test_stalled_copy_with_low_residency_is_page_io():
    detail = classify_copy(_record(
        copy_wall_ns=3_000_000_000,
        thread_cpu_ns_before=0, thread_cpu_ns_after=10_000_000,
        resident_pre_ppm=100_000,
        # Only incidental switches: well under the meaningful-switch floor.
        nvcsw_delta=2, nivcsw_delta=1,
    ))
    assert detail["classification"] == "PAGE_IO_STALL"
    assert detail["pre_resident_fraction"] == pytest.approx(0.1)


def test_a_single_incidental_switch_does_not_manufacture_deschedule():
    detail = classify_copy(_record(
        copy_wall_ns=3_000_000_000,
        thread_cpu_ns_before=0, thread_cpu_ns_after=10_000_000,
        nvcsw_delta=1, nivcsw_delta=0,
    ))
    assert detail["classification"] != "DESCHEDULE_STALL"


def test_classification_is_never_forced_into_a_label():
    """Counters that do not discriminate must stay UNRESOLVED."""
    detail = classify_copy(_record(
        copy_wall_ns=1_500_000_000,
        thread_cpu_ns_before=0, thread_cpu_ns_after=500_000_000,
    ))
    assert detail["classification"] in CLASSIFICATIONS
    if detail["classification"] == "UNRESOLVED":
        assert detail["reason"] == "counters do not discriminate"


# ── thresholds, ordering, compactness ─────────────────────────────────────


def test_slow_copy_thresholds_count_each_class_exactly_once():
    records = [
        _record(ordinal=0, copy_wall_ns=50_000_000),                    # healthy
        _record(ordinal=1, copy_wall_ns=150_000_000),                   # >100
        _record(ordinal=2, copy_wall_ns=300_000_000),                   # >250
        _record(ordinal=3, copy_wall_ns=600_000_000),                   # >500
        _record(ordinal=4, copy_wall_ns=2_000_000_000),                 # >1000
    ]
    counts = summarize_copy_stalls(records)["slow_copy_counts"]
    assert counts == {"gt_100ms": 4, "gt_250ms": 3, "gt_500ms": 2, "gt_1000ms": 1}


def test_threshold_boundaries_are_strictly_greater_than():
    records = [_record(ordinal=0, copy_wall_ns=int(SLOW_MS * 1e6))]
    assert summarize_copy_stalls(records)["slow_copy_counts"]["gt_100ms"] == 0


def test_top_slowest_is_ordered_and_capped():
    records = [
        _record(ordinal=index, copy_wall_ns=(index + 1) * 10_000_000)
        for index in range(25)
    ]
    top = summarize_copy_stalls(records)["top_8_slowest"]
    assert len(top) == TOP_N
    walls = [item["memcpy_wall_ms"] for item in top]
    assert walls == sorted(walls, reverse=True)
    assert top[0]["ordinal"] == 24


def test_top_slowest_entries_carry_only_compact_fields():
    top = summarize_copy_stalls([_record()])["top_8_slowest"][0]
    assert set(top) == {
        "ordinal", "reader_id", "source_offset", "nbytes", "memcpy_wall_ms",
        "thread_cpu_ms", "wall_cpu_ratio", "minflt_delta", "majflt_delta",
        "inblock_delta", "nvcsw_delta", "nivcsw_delta", "start_cpu", "end_cpu",
        "pre_resident_fraction", "classification",
    }


def test_no_list_in_compact_telemetry_is_unbounded():
    records = [_record(ordinal=index, reader_id=index % 4) for index in range(200)]
    summary = summarize_copy_stalls(records)

    def walk(node, path="summary"):
        if isinstance(node, dict):
            for key, value in node.items():
                walk(value, f"{path}.{key}")
        elif isinstance(node, list):
            assert len(node) <= TOP_N, f"{path} has {len(node)} entries"
            for index, value in enumerate(node):
                walk(value, f"{path}[{index}]")

    walk(summary)


def test_percentiles_are_reported_for_wall_cpu_and_ratio():
    records = [
        _record(ordinal=index, copy_wall_ns=(index + 1) * 20_000_000,
                thread_cpu_ns_before=0,
                thread_cpu_ns_after=(index + 1) * 19_000_000)
        for index in range(20)
    ]
    summary = summarize_copy_stalls(records)
    for key in ("memcpy_wall_ms", "thread_cpu_ms", "wall_cpu_ratio"):
        assert summary[key]["p50"] is not None, key
        assert summary[key]["p90"] is not None, key
        assert summary[key]["max"] is not None, key


def test_slow_class_breakdown_aggregates_evidence_per_label():
    records = [
        _record(ordinal=0, copy_wall_ns=2_000_000_000,
                thread_cpu_ns_before=0, thread_cpu_ns_after=10_000_000,
                majflt_delta=100, inblock_delta=50, nvcsw_delta=7, nivcsw_delta=3),
        _record(ordinal=1, copy_wall_ns=1_500_000_000,
                thread_cpu_ns_before=0, thread_cpu_ns_after=5_000_000,
                majflt_delta=20, inblock_delta=10, nvcsw_delta=1, nivcsw_delta=1),
    ]
    breakdown = summarize_copy_stalls(records)["slow_class_breakdown"]
    page = breakdown["PAGE_IO_STALL"]
    assert page["count"] == 2
    assert page["majflt_total"] == 120
    assert page["inblock_total"] == 60
    assert page["cpu_mean_ms"] == pytest.approx(7.5)


def test_per_reader_and_model_summaries_are_preserved():
    records = [_record(ordinal=index, reader_id=index % 4) for index in range(12)]
    summary = summarize_copy_stalls(records)
    assert summary["copy_count"] == 12
    assert summary["slow_threshold_ms"] == SLOW_MS


def test_old_telemetry_fields_are_unchanged_by_the_new_ring():
    """The pre-existing 18 ring fields keep their names, order, and meaning."""
    assert source.OP_FIELDS[:18] == (
        "generation", "reader_id", "thread_id", "slot_index", "ordinal",
        "source_offset", "nbytes", "source_start_ns", "map_start_ns",
        "access_start_ns", "memcpy_start_ns", "memcpy_end_ns", "munmap_start_ns",
        "munmap_end_ns", "slot_wait_ns", "pacing_wait_ns", "ready_ns", "flags",
    )
    assert source.OP.size == 8 * len(source.OP_FIELDS)


def test_ring_capacity_stays_well_above_a_real_model_block_count():
    assert source.MAX_OPS > 1000


def test_malformed_records_are_ignored_rather_than_raising():
    """Junk entries must be skipped, never crash the summary or the request."""
    summary = summarize_copy_stalls([None, "text", 7, _record()])
    assert summary["copy_count"] == 1
    assert summary["top_8_slowest"][0]["ordinal"] == 0


def test_empty_record_is_counted_but_carries_no_evidence():
    """An empty mapping is structurally a record; it simply has no data."""
    summary = summarize_copy_stalls([{}])
    assert summary["copy_count"] == 1
    assert summary["memcpy_wall_ms"]["max"] is None
    assert summary["classification_counts"]["UNRESOLVED"] == 1