"""Local contracts for the P9 source/destination copy-isolation experiment.

These are contracts, not smoke tests.  Each one pins something the remote
experiment cannot be trusted to reveal on its own: which arm was selected, that
the pinned and anonymous destinations really are different objects, that the
anonymous buffers were actually written before timing, that the 64 MiB block
size is the production one, that source offsets and slot indices are reported
as production reports them, that thread-CPU accounting cannot silently divide by
zero, and that the experiment is completely inert unless explicitly enabled.
"""

from __future__ import annotations

import ctypes
import inspect
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from comfymodal_runtime import golden_source_threads as gsrc  # noqa: E402
from comfymodal_runtime import source_copy_isolation as sci  # noqa: E402
from comfymodal_runtime.source_copy_probe import SourceCopyProbe  # noqa: E402
from tools import source_copy_isolation_report as report_tool  # noqa: E402

_MIB = 1024 * 1024


# ── arm selection ────────────────────────────────────────────────────────

def test_arm_layout_matches_the_2x2_design():
    assert sci.arm_layout("A")["source"] == "model_mmap"
    assert sci.arm_layout("A")["destination"] == "pinned_shared_arena"
    assert sci.arm_layout("B")["source"] == "model_mmap"
    assert sci.arm_layout("B")["destination"] == "anonymous"
    assert sci.arm_layout("C")["source"] == "anonymous"
    assert sci.arm_layout("C")["destination"] == "pinned_shared_arena"
    assert sci.arm_layout("D")["source"] == "anonymous"
    assert sci.arm_layout("D")["destination"] == "anonymous"


def test_only_the_control_is_both_mapped_and_pinned():
    # A is the only arm that is simultaneously a mapped Volume source and the
    # production pinned arena, which is what makes it the control.  A2 and A3 are
    # A plus one population treatment, so they share both properties by design.
    both = [
        arm for arm in sci.ARMS
        if sci.arm_layout(arm)["source"] == "model_mmap"
        and sci.arm_layout(arm)["destination"] == "pinned_shared_arena"
    ]
    assert both == ["A", "A2", "A3"]
    assert sci.POPULATION_TREATMENT_ARMS == ("A2", "A3")
    mapped = [arm for arm in sci.ARMS if sci.arm_layout(arm)["source"] == "model_mmap"]
    assert mapped == ["A", "A2", "A3", "B"]
    pinned = [arm for arm in sci.ARMS if sci.arm_layout(arm)["destination"] == "pinned_shared_arena"]
    assert pinned == ["A", "A2", "A3", "C"]


def test_mapped_source_arms_use_production_concurrency_only():
    # Only C and D carry the single-thread baseline the decision tree needs to
    # separate a concurrency-specific effect from a memory-placement effect.
    assert sci.arm_layout("A")["variants"] == ("concurrent4",)
    assert sci.arm_layout("B")["variants"] == ("concurrent4",)
    assert sci.arm_layout("C")["variants"] == ("single", "concurrent4")
    assert sci.arm_layout("D")["variants"] == ("single", "concurrent4")
    assert sci.VARIANT_READERS == {"single": 1, "concurrent4": gsrc.READER_COUNT}


def test_selected_arm_defaults_to_the_production_control(monkeypatch):
    monkeypatch.delenv(sci.ARM_ENV, raising=False)
    assert sci.selected_arm() == "A"
    monkeypatch.setenv(sci.ARM_ENV, "c")
    assert sci.selected_arm() == "C"


@pytest.mark.parametrize("bad", ["Z", "", "ab", "model"])
def test_selected_arm_fails_closed_on_an_unknown_arm(monkeypatch, bad):
    monkeypatch.setenv(sci.ARM_ENV, bad)
    with pytest.raises(ValueError):
        sci.selected_arm()


def test_model_key_fails_closed_on_an_unknown_model(monkeypatch):
    monkeypatch.setenv(sci.MODEL_ENV, "sd15")
    with pytest.raises(ValueError):
        sci.resolve_model_key()


def test_copy_count_never_silently_falls_below_the_sampling_floor():
    assert sci.resolve_copies(128) == 128
    assert sci.resolve_copies(256) == 256
    with pytest.raises(ValueError):
        sci.resolve_copies(127)
    # An unparseable value must not quietly become 1 or 0 either.
    assert sci.resolve_copies("not-a-number") == sci.DEFAULT_COPIES
    assert sci.DEFAULT_COPIES >= sci.MINIMUM_COPIES >= 128


# ── 64 MiB block size and source sequencing ──────────────────────────────

def test_block_size_is_the_production_64_mib():
    assert gsrc.SLOT_BYTES == 64 * _MIB
    assert sci.gsrc.SLOT_BYTES == 64 * _MIB
    ranges = sci.file_block_ranges(3 * 64 * _MIB)
    assert [item[1] for item in ranges] == [64 * _MIB] * 3


def test_file_block_ranges_cover_the_file_exactly_once():
    size = 5 * 64 * _MIB + 12345
    ranges = sci.file_block_ranges(size)
    assert ranges[0][0] == 0
    assert sum(item[1] for item in ranges) == size
    for left, right in zip(ranges, ranges[1:]):
        assert left[0] + left[1] == right[0], "source coverage must have no gap"
    assert ranges[-1][0] + ranges[-1][1] == size
    assert ranges[-1][1] == 12345, "only the final block may be a short tail"


def test_file_block_ranges_rejects_an_empty_file():
    with pytest.raises(ValueError):
        sci.file_block_ranges(0)


def test_repeated_ranges_hold_exactly_the_requested_copy_count():
    ranges = sci.repeated_plan_ranges(2 * 64 * _MIB, 300)
    assert len(ranges) == 300
    assert sum(item[1] for item in ranges) == 300 * 64 * _MIB
    cursor = 0
    for source_offset, length, destination_offset, _record in ranges:
        assert length == 64 * _MIB
        assert destination_offset == cursor, "destination must stay gap-free"
        cursor += length
        assert source_offset < 2 * 64 * _MIB, "source offset must stay inside the file"


def test_repeated_ranges_reuse_source_offsets_so_identity_correlation_is_possible():
    ranges = sci.repeated_plan_ranges(64 * _MIB, 5)
    offsets = [item[0] for item in ranges]
    assert offsets == [0, 0, 0, 0, 0]
    assert len({item[2] for item in ranges}) == 5, "destination offsets must stay distinct"


def test_repeated_ranges_refuse_a_nonpositive_copy_count():
    with pytest.raises(ValueError):
        sci.repeated_plan_ranges(64 * _MIB, 0)


# ── anonymous buffers are pre-touched ────────────────────────────────────

def test_anonymous_buffer_is_fully_written_before_it_is_handed_out():
    size = 4 * _MIB + 4096
    buffer, address = sci._anonymous_buffer(size)
    try:
        assert address > 0
        raw = bytes(buffer)
        assert len(raw) == size
        # A page that was never written would still read as zero, so a full
        # non-zero read-back is the proof that every page was touched.
        assert raw == bytes([0xA5]) * size
    finally:
        sci._release_anonymous(buffer)


def test_anonymous_buffer_rejects_a_nonpositive_size():
    with pytest.raises(ValueError):
        sci._anonymous_buffer(0)


def test_pinned_and_anonymous_destinations_are_different_objects():
    # The pinned destination registers with CUDA; the anonymous one must not
    # even import CUDA, and neither may claim a registration it never made.
    anonymous_source = inspect.getsource(sci._anonymous_destination_evidence)
    assert "import torch" not in anonymous_source
    assert "cudaHostRegister(" not in anonymous_source
    evidence = sci._anonymous_destination_evidence(None, 1234)
    assert evidence["cuda_host_registered"] is False
    assert evidence["kind"] == "anonymous"
    assert evidence["backing"] == "anonymous_mmap"
    assert evidence["prefault_applied"] is True
    assert evidence["address"] == 1234
    # Same destination size as the pinned arena: only the KIND of memory differs.
    assert evidence["bytes"] == gsrc.ARENA_BYTES


def test_pinned_arena_unregisters_before_it_releases_the_mapping():
    # A registration outlives the Python object.  Closing and unlinking the
    # shared-memory segment while it is still registered leaves the address
    # range registered in the driver, the next 1 GiB allocation reuses that
    # address, and the production cudaHostRegister then fails with
    # cudaErrorAlreadyMapped.  That was a real first-run failure, not a
    # hypothetical, so the contract is pinned here.
    source = inspect.getsource(sci.PinnedSharedArena.close)
    assert "cudaHostUnregister" in source
    assert source.index("cudaHostUnregister") < source.index("self.shm.close()")
    assert "self.buffer.release()" in source
    run_arm_source = inspect.getsource(sci.run_arm)
    assert 'report["teardown"] = arena.close()' in run_arm_source


def test_pinned_arena_geometry_is_the_production_arena():
    arena = sci.PinnedSharedArena()
    try:
        evidence = arena.evidence()
        assert evidence["bytes"] == gsrc.ARENA_BYTES
        assert evidence["bytes"] == gsrc.SLOT_COUNT * gsrc.SLOT_BYTES
        assert evidence["backing"] == "posix_shared_memory"
        assert evidence["cuda_host_register_flags"] == 0
        assert evidence["cuda_host_registered"] is False, "unregistered until register() runs"
    finally:
        arena.close()


# ── slot index reporting ─────────────────────────────────────────────────

def test_slot_index_projects_to_the_production_destination_byte_offset():
    record = dict(zip(gsrc.OP_FIELDS, [0] * len(gsrc.OP_FIELDS)))
    record.update({
        "reader_id": 2, "thread_id": 7, "slot_index": 5, "ordinal": 9,
        "source_offset": 3 * 64 * _MIB, "nbytes": 64 * _MIB,
    })
    row = sci.project_copy(record)
    assert row["dest_slot"] == 5
    assert row["dest_byte_offset"] == 5 * 64 * _MIB
    assert row["source_offset"] == 3 * 64 * _MIB
    assert row["copy_ordinal"] == 9
    assert row["reader"] == 2
    assert row["thread"] == 7
    assert row["nbytes"] == 64 * _MIB


def test_slot_index_is_reported_as_missing_rather_than_invented():
    record = dict(zip(gsrc.OP_FIELDS, [0] * len(gsrc.OP_FIELDS)))
    record["slot_index"] = 0
    assert sci.project_copy(record)["dest_byte_offset"] == 0
    record["slot_index"] = gsrc.SLOT_COUNT  # one past the last slot
    row = sci.project_copy(record)
    assert row["dest_slot"] == gsrc.SLOT_COUNT
    assert row["dest_byte_offset"] is None


# ── thread CPU / wall accounting ─────────────────────────────────────────

def _copy_record(**overrides):
    record = dict(zip(gsrc.OP_FIELDS, [0] * len(gsrc.OP_FIELDS)))
    record.update({
        "copy_wall_ns": 1_460_000_000,
        "thread_cpu_ns_before": 10_000_000_000,
        "thread_cpu_ns_after": 11_370_000_000,
        "slot_index": 1,
        "source_offset": 64 * _MIB,
    })
    record.update(overrides)
    return record


def test_thread_cpu_is_the_before_after_delta_not_the_absolute_clock():
    row = sci.project_copy(_copy_record())
    assert row["wall_ms"] == 1460.0
    assert row["thread_cpu_ms"] == 1370.0
    assert row["wall_cpu_ratio"] == pytest.approx(1460.0 / 1370.0, rel=1e-4)


def test_unavailable_thread_cpu_is_none_and_never_fabricated():
    sentinel = (1 << 64) - 1
    row = sci.project_copy(_copy_record(thread_cpu_ns_after=sentinel))
    assert row["thread_cpu_ms"] is None
    assert row["wall_cpu_ratio"] is None
    assert row["wall_ms"] == 1460.0, "wall stays measured even without thread CPU"


def test_a_backwards_or_zero_thread_cpu_delta_does_not_produce_a_ratio():
    assert sci.project_copy(_copy_record(thread_cpu_ns_before=5, thread_cpu_ns_after=5))[
        "wall_cpu_ratio"
    ] is None
    assert sci.project_copy(_copy_record(thread_cpu_ns_before=9, thread_cpu_ns_after=5))[
        "thread_cpu_ms"
    ] is None


def test_fault_and_context_deltas_distinguish_sentinel_from_zero():
    sentinel = (1 << 64) - 1
    row = sci.project_copy(_copy_record(minflt_delta=0, majflt_delta=0, inblock_delta=0))
    assert row["minflt_delta"] == 0 and row["majflt_delta"] == 0
    assert row["inblock_delta"] == 0, "a real zero must not be reported as unavailable"
    unknown = sci.project_copy(_copy_record(minflt_delta=sentinel))
    assert unknown["minflt_delta"] is None


# ── statistics ───────────────────────────────────────────────────────────

def test_describe_reports_every_required_statistic():
    stats = sci.describe([10, 20, 30, 40, 50])
    assert stats["count"] == 5
    assert stats["min"] == 10 and stats["max"] == 50
    assert stats["p50"] == 30
    assert 40 <= stats["p90"] <= 50
    assert 40 <= stats["p95"] <= 50
    assert 40 <= stats["p99"] <= 50
    assert stats["mean"] == 30
    assert stats["sd"] == pytest.approx(15.8113883, rel=1e-6)
    assert stats["cv"] == pytest.approx(stats["sd"] / stats["mean"], rel=1e-4)


def test_describe_of_an_empty_series_is_all_null_not_a_crash():
    stats = sci.describe([])
    assert stats["count"] == 0
    assert all(stats[key] is None for key in ("min", "p50", "p99", "max", "mean", "sd", "cv"))


def test_summarize_counts_every_stall_threshold():
    copies = [
        {"wall_ms": 50.0, "thread_cpu_ms": 45.0, "wall_cpu_ratio": 1.1, "source_offset": 0, "dest_slot": 0, "reader": 0},
        {"wall_ms": 120.0, "thread_cpu_ms": 100.0, "wall_cpu_ratio": 1.2, "source_offset": 64 * _MIB, "dest_slot": 1, "reader": 1},
        {"wall_ms": 300.0, "thread_cpu_ms": 280.0, "wall_cpu_ratio": 1.07, "source_offset": 0, "dest_slot": 2, "reader": 2},
        {"wall_ms": 700.0, "thread_cpu_ms": 660.0, "wall_cpu_ratio": 1.06, "source_offset": 0, "dest_slot": 3, "reader": 3},
        {"wall_ms": 1460.0, "thread_cpu_ms": 1370.0, "wall_cpu_ratio": 1.07, "source_offset": 0, "dest_slot": 0, "reader": 0},
    ]
    summary = sci.summarize_copies(copies)
    assert summary["over_thresholds"] == {">100ms": 4, ">250ms": 3, ">500ms": 2, ">1000ms": 1}
    assert summary["slowest"][0]["wall_ms"] == 1460.0
    assert summary["distinct_source_offsets"] == 2
    assert summary["distinct_dest_slots"] == 4
    assert summary["distinct_readers"] == 4
    assert summary["wall_ms"]["max"] == 1460.0


def test_summarize_caps_the_slowest_list_at_twenty():
    copies = [
        {"wall_ms": float(index), "thread_cpu_ms": 1.0, "wall_cpu_ratio": 1.0,
         "source_offset": index, "dest_slot": index % 16, "reader": 0}
        for index in range(64)
    ]
    summary = sci.summarize_copies(copies)
    assert len(summary["slowest"]) == 20
    assert summary["slowest"][0]["wall_ms"] == 63.0


def test_slowest_copies_are_ordered_worst_first():
    copies = [
        {"wall_ms": value, "thread_cpu_ms": 1.0, "wall_cpu_ratio": 1.0,
         "source_offset": 0, "dest_slot": 0, "reader": 0}
        for value in (5.0, 900.0, 100.0)
    ]
    walls = [item["wall_ms"] for item in sci.summarize_copies(copies)["slowest"]]
    assert walls == sorted(walls, reverse=True)


# ── opt-in / production-path isolation ───────────────────────────────────

def test_experiment_is_disabled_by_default(monkeypatch):
    monkeypatch.delenv(sci.EXPERIMENT_ENV, raising=False)
    assert sci.enabled() is False
    assert sci.run_from_session(object()) == {"status": "disabled"}


@pytest.mark.parametrize("raw", ["1", "true", "TRUE", "yes", "on"])
def test_experiment_enables_only_on_an_explicit_true(monkeypatch, raw):
    monkeypatch.setenv(sci.EXPERIMENT_ENV, raw)
    assert sci.enabled() is True


@pytest.mark.parametrize("raw", ["0", "false", "no", "", "off", "2"])
def test_experiment_stays_off_for_anything_that_is_not_true(monkeypatch, raw):
    monkeypatch.setenv(sci.EXPERIMENT_ENV, raw)
    assert sci.enabled() is False


def test_experiment_does_not_reimplement_the_production_copy():
    source = inspect.getsource(sci)
    assert "def execute_block" not in source, "the copy kernel has exactly one owner"
    assert "def memmove" not in source
    # It drives the production reader loop, which calls the production kernel.
    assert "gsrc._run_reader_loop" in source
    assert "golden_source_threads._run_reader_loop" in source
    # No production geometry is redefined here.
    for constant in ("SLOT_COUNT =", "SLOT_BYTES =", "ARENA_BYTES =", "READER_COUNT =",
                     "PACER_GAP_NS =", "FREE_MASK ="):
        assert constant not in source


def test_experiment_never_mutates_the_production_copy_path():
    # The production source-thread module must still be the Phase-1 base file:
    # the experiment adds capability beside it, never inside it.  Concretely,
    # the experiment module must not re-export or shadow any production symbol,
    # and the production module must still define the copy kernel itself.
    assert not hasattr(sci, "execute_block")
    assert not hasattr(sci, "_run_reader_loop")
    assert not hasattr(sci, "claim_block")
    assert not hasattr(sci, "publish_ready")
    assert hasattr(gsrc, "execute_block")
    assert hasattr(gsrc, "_run_reader_loop")
    # The experiment binds the production geometry by reading it, never by
    # shadowing it: its own module namespace carries no such constants.
    for name in ("SLOT_COUNT", "SLOT_BYTES", "ARENA_BYTES", "READER_COUNT",
                 "FREE_MASK", "READY", "IN_FLIGHT"):
        assert name not in vars(sci)


def test_golden_parallel_hook_is_gated_on_the_experiment_flag():
    import pathlib

    text = pathlib.Path(gsrc.__file__).with_name("golden_parallel.py").read_text(
        encoding="utf-8"
    )
    assert "_source_copy_isolation.enabled()" in text
    assert "run_from_session(session)" in text
    # The hook must sit after request setup (model paths resolved) and before
    # the first model read, so it cannot compete with the real source load.
    hook = text.index("_source_copy_isolation.enabled()")
    setup = text.index("await golden_request_setup(session)")
    clip = text.index("await golden_clip_load(session")
    assert setup < hook < clip


def test_runtime_identity_never_invents_a_region():
    identity = sci.runtime_identity()
    assert identity["region"] in {"reported_only", "unavailable"}
    assert "env" in identity and identity["env"]
    assert identity["module_sha256"]


def test_host_facts_declares_numa_as_not_inferred():
    facts = sci.host_facts(None)
    assert facts["numa"] == "not_inferred"
    assert "placement" in facts


# ── the real driver, at a test-sized geometry ────────────────────────────

def test_driver_runs_production_copies_and_reports_slot_identity(monkeypatch):
    """Exercise the real reader loop, slot state machine and ring, end to end.

    Geometry is shrunk so the test is fast; nothing else is stubbed.  The copy
    itself is still ``libc.memmove`` through ``execute_block``, the control block
    is the production one, and the returned rows are the production records.
    """
    slot_bytes = 1 * _MIB
    slot_count = 4
    monkeypatch.setattr(gsrc, "SLOT_BYTES", slot_bytes)
    monkeypatch.setattr(gsrc, "SLOT_COUNT", slot_count)
    monkeypatch.setattr(gsrc, "ARENA_BYTES", slot_bytes * slot_count)
    monkeypatch.setattr(gsrc, "FREE_MASK", (1 << slot_count) - 1)
    monkeypatch.setattr(gsrc, "PACER_GAP_NS", 1_000_000)
    monkeypatch.setattr(gsrc, "_PAGE_SIZE", 4096)
    monkeypatch.setattr(gsrc, "_PROBE", None, raising=False)

    # The production kernel reaches libc through ``_MAPPER``; on the Linux
    # container that is ``CDLL(None)`` and here it is the platform C runtime.
    libc = ctypes.CDLL(None if os.name == "posix" else "msvcrt")
    libc.memmove.restype = ctypes.c_void_p
    libc.memmove.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t]
    monkeypatch.setattr(gsrc, "_MAPPER", libc, raising=False)
    monkeypatch.setattr(gsrc, "_PROBE", SourceCopyProbe(enabled=False), raising=False)

    source_buffer, source_address = sci._anonymous_buffer(slot_bytes * 8)
    destination, destination_address = sci._anonymous_buffer(gsrc.ARENA_BYTES)
    plan = sci._plan(
        generation=1,
        path="<test-anonymous-source>",
        identity=(0, 0, slot_bytes * 8, 0),
        ranges=tuple(
            (index * slot_bytes, slot_bytes, index * slot_bytes, None)
            for index in range(8)
        ),
        map_address=source_address,
        map_length=slot_bytes * 8,
    )
    try:
        result = sci._run_variant(
            variant="concurrent4",
            plan=plan,
            arena_buffer=destination,
            reader_count=4,
            copies=8,
        )
        assert result["published_copies"] == 8
        assert result["recorded_copies"] == 8
        assert result["timed_out"] is False
        assert result["fatal"] == [] and result["failure_messages"] == []
        assert result["slots_quiescent"] is True
        rows = [sci.project_copy(item) for item in result["records"]]
        assert len(rows) == 8
        assert {row["dest_slot"] for row in rows} <= set(range(slot_count))
        assert {row["source_offset"] for row in rows} == {index * slot_bytes for index in range(8)}
        assert all(row["nbytes"] == slot_bytes for row in rows)
        assert all(row["wall_ms"] >= 0.0 for row in rows)
        summary = sci.summarize_copies(rows)
        assert summary["count"] == 8
        assert summary["wall_ms"]["count"] == 8
        assert len({row["reader"] for row in rows}) >= 1
    finally:
        sci._release_anonymous(source_buffer)
        sci._release_anonymous(destination)

# ── the population decision must survive an intermittent mechanism ────────
# The measured A/A2/A3 cohort made this concrete: MAP_POPULATE cleared the
# pooled p99 and the >=1% slow-fraction floor, yet one of its five containers
# still contained a 2.1 s copy.  Pooling four healthy containers with one
# catastrophic one is how a treatment gets credited with removing a stall that it
# did not remove.

def _population_summary(*, control_pathological, control_slow_containers,
                         arm2_pathological, arm2_slow_containers,
                         arm3_pathological, arm3_slow_containers):
    def cohort(pathological, slow_containers):
        return {
            "pathological": pathological,
            "usable_containers": 5,
            "pooled": {
                "per_container": [
                    {"over_thresholds": {">100ms": 3 if index < slow_containers else 0}}
                    for index in range(5)
                ],
            },
        }

    def arm(pathological, slow_containers):
        return {"cohorts": {"deploy1": cohort(pathological, slow_containers)}}

    return {"arms": {
        "A": arm(control_pathological, control_slow_containers),
        "A2": arm(arm2_pathological, arm2_slow_containers),
        "A3": arm(arm3_pathological, arm3_slow_containers),
    }}


def test_a_treatment_that_leaves_a_pathological_container_is_not_credited():
    # Exactly the measured A3 shape: pooled-clean, one bad container.
    decision = report_tool.classify_population(_population_summary(
        control_pathological=True, control_slow_containers=1,
        arm2_pathological=True, arm2_slow_containers=2,
        arm3_pathological=False, arm3_slow_containers=2,
    ))
    assert decision["pooled_healthy_treatment_arms"] == ["A3"]
    assert decision["healthy_treatment_arms"] == []
    assert decision["classification"] == "INCONCLUSIVE_CURRENT_COHORT"
    assert "pooled_thresholds_and_per_container_evidence_disagree" in decision["reasons"]
    assert decision["pathological_containers"] == {"A": 1, "A2": 2, "A3": 2}


def test_a_treatment_with_no_pathological_container_is_credited():
    decision = report_tool.classify_population(_population_summary(
        control_pathological=True, control_slow_containers=2,
        arm2_pathological=True, arm2_slow_containers=2,
        arm3_pathological=False, arm3_slow_containers=0,
    ))
    assert decision["healthy_treatment_arms"] == ["A3"]
    assert decision["classification"] == "BACKING_POPULATION_CONFIRMED"


def test_willneed_alone_working_is_reported_as_such():
    decision = report_tool.classify_population(_population_summary(
        control_pathological=True, control_slow_containers=2,
        arm2_pathological=False, arm2_slow_containers=0,
        arm3_pathological=True, arm3_slow_containers=2,
    ))
    assert decision["classification"] == "WILLNEED_ONLY_EFFECTIVE"
    assert decision["healthy_treatment_arms"] == ["A2"]


def test_a_control_that_never_goes_pathological_cannot_credit_a_treatment():
    decision = report_tool.classify_population(_population_summary(
        control_pathological=False, control_slow_containers=0,
        arm2_pathological=True, arm2_slow_containers=2,
        arm3_pathological=True, arm3_slow_containers=2,
    ))
    assert decision["classification"] == "INCONCLUSIVE_CURRENT_COHORT"
    assert "control_did_not_reproduce_the_stall" in decision["reasons"]
    assert decision["healthy_treatment_arms"] == []


def test_the_prefetch_family_fails_only_when_no_container_improves():
    decision = report_tool.classify_population(_population_summary(
        control_pathological=True, control_slow_containers=1,
        arm2_pathological=True, arm2_slow_containers=1,
        arm3_pathological=True, arm3_slow_containers=1,
    ))
    assert decision["classification"] == "PREFETCH_FAMILY_FAILED"
    assert "every_treatment_arm_still_contains_a_pathological_container" in (
        decision["reasons"])


def test_pathological_containers_counts_containers_not_copies():
    # One container with fifty slow copies is one sick container; that is the
    # distinction the pooled distribution cannot make.
    per_container = [
        {"over_thresholds": {">100ms": 50}},
        {"over_thresholds": {">100ms": 0}},
        {"over_thresholds": {">100ms": 1}},
    ]
    assert report_tool.pathological_containers(per_container) == 2
    assert report_tool.pathological_containers([]) == 0
