"""G3 / Batch A per-node timeline tests.

Verifies that ``per_node_timings`` records now carry ``start_perf_ns`` /
``end_perf_ns`` (perf_counter domain) plus ``pass_outcome``, that the
sampling-start cutoff clips the record's ``end_perf_ns`` to the cutoff, and
that the v2 waterfall positions node rows as NON-ACCOUNTING overlap detail
without disturbing reconciliation.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

import pytest

from comfymodal_runtime.runtime_executor import (
    install_pre_sampler_hooks,
    uninstall_pre_sampler_hooks,
    _attach_structured_report,
    _clip_node_interval,
    _derive_pass_outcome,
    _instrumentation_var,
    _sampling_cutoff_perf_ns,
)
from comfymodal_runtime.v2_waterfall import (
    DERIVED,
    INVALID,
    MEASURED,
    UNAVAILABLE,
)
from tests.test_pre_sampler_critical_path_integration import (
    _ensure_comfyui_stubs,
    _make_fake_cacheset,
    _make_fake_execution_list,
    _make_fake_is_changed_cache,
    _make_real_get_input_data,
)
from tools.v2_waterfall import build_waterfall

# The integration module's module-level call already created the stubs; an
# explicit (idempotent) call keeps this module self-contained regardless of
# import order.
_ensure_comfyui_stubs()


# ═══════════════════════════════════════════════════════════════════════
# Fixtures / harness (mirrors test_pre_sampler_critical_path_integration)
# ═══════════════════════════════════════════════════════════════════════


@pytest.fixture(autouse=True)
def _clean_hooks():
    """Ensure hooks are uninstalled before and after each test."""
    uninstall_pre_sampler_hooks()
    yield
    uninstall_pre_sampler_hooks()


def _install_with_exec_node(exec_node, state):
    """Assign a fake ``execution.execute`` first, then install hooks.

    ``install_pre_sampler_hooks`` snapshots ``execution.execute`` at install
    time, so the fake must be in place BEFORE hooks are installed.
    """
    import execution as _execution
    _execution.execute = exec_node
    install_pre_sampler_hooks()
    return _execution


async def _run_node(_execution, state, node_id, class_type, *, set_cutoff_mid=False):
    """Direct-call pattern mirroring the integration harness (lines
    1220-1259 of test_pre_sampler_critical_path_integration.py)."""
    state["_prompt"] = {node_id: {"class_type": class_type, "inputs": {}}}
    return await _execution.execute(
        server=None,
        dynprompt=None,
        caches=_make_fake_cacheset(),
        current_item=node_id,
        extra_data={"class_type": class_type},
        executed=set(),
        prompt_id="test-per-node",
        execution_list=_make_fake_execution_list(),
        pending_subgraph_results={},
        pending_async_nodes={},
        ui_outputs={},
    )


async def _run_instrumented(exec_node, node_id, class_type, *, state=None):
    """Run one node under instrumentation with a fresh per-request state.

    Each call uses a fresh state dict; the instrumentation ContextVar token
    is set inside a try/finally that always resets it.  Exceptions from the
    node propagate to the caller (after the token is reset).
    """
    state = {} if state is None else state
    _execution = _install_with_exec_node(exec_node, state)
    token = _instrumentation_var.set(state)
    try:
        await _run_node(_execution, state, node_id, class_type)
    finally:
        _instrumentation_var.reset(token)
    return state


# ═══════════════════════════════════════════════════════════════════════
# Fake exec nodes
# ═══════════════════════════════════════════════════════════════════════


async def _exec_success(*a, **kw):
    time.sleep(0.003)
    return (0, None, None)  # ExecutionResult.SUCCESS


async def _exec_pending(*a, **kw):
    time.sleep(0.002)
    return (2, None, None)  # ExecutionResult.PENDING


async def _exec_failure(*a, **kw):
    time.sleep(0.001)
    raise RuntimeError("boom")


async def _exec_non_tuple(*a, **kw):
    time.sleep(0.001)
    return None


async def _exec_cancelled(*a, **kw):
    time.sleep(0.001)
    raise asyncio.CancelledError()


def _make_mid_cutoff_exec(cutoff_box):
    """Exec that sets the sampling cutoff mid-execution, simulating the
    sampler node being truncated by sampling_start.

    ``_sampling_cutoff_perf_ns`` is a ContextVar; ``set()`` from inside the
    same task context is visible to the wrapper's ``finally`` block.
    """
    async def _execute(*a, **kw):
        time.sleep(0.001)
        cutoff_box["ns"] = time.perf_counter_ns()
        _sampling_cutoff_perf_ns.set(cutoff_box["ns"])
        time.sleep(0.02)
        return (0, None, None)
    return _execute


# ═══════════════════════════════════════════════════════════════════════
# Pure helper tests
# ═══════════════════════════════════════════════════════════════════════


def test_derive_pass_outcome():
    class _Status:
        def __init__(self, value, name):
            self.value = value
            self.name = name

    cases = [
        ((0, None, None), {}, "COMPLETE"),
        ((2, None, None), {}, "PENDING"),
        ((1, None, None), {}, "ERROR"),
        (None, {"raised": True}, "ERROR"),
        ((0, None, None), {"cancelled": True}, "UNKNOWN"),
        (None, {}, "UNKNOWN"),
        ("junk", {}, "UNKNOWN"),
        (True, {}, "UNKNOWN"),
        ((_Status(0, "SUCCESS"), None, None), {}, "COMPLETE"),
    ]
    for result, kwargs, expected in cases:
        got = _derive_pass_outcome(result, **kwargs)
        assert got == expected, (
            f"_derive_pass_outcome({result!r}, {kwargs!r}) expected "
            f"{expected!r}, got {got!r}"
        )


def test_clip_node_interval_pure():
    # No cutoff: full interval, end preserved.
    elapsed, end = _clip_node_interval(1_000_000, 3_000_000, None)
    assert (elapsed, end) == (2.0, 3_000_000), (elapsed, end)
    # Mid cutoff: duration stops at the cutoff, end == cutoff.
    elapsed, end = _clip_node_interval(1_000_000, 30_000_000, 5_000_000)
    assert (elapsed, end) == (4.0, 5_000_000), (elapsed, end)
    # Cutoff before start: node contributes 0, end == start.
    elapsed, end = _clip_node_interval(5_000_000, 8_000_000, 4_000_000)
    assert (elapsed, end) == (0.0, 5_000_000), (elapsed, end)
    # Cutoff after end: must NOT inflate; unchanged.
    elapsed, end = _clip_node_interval(1_000_000, 3_000_000, 5_000_000)
    assert (elapsed, end) == (2.0, 3_000_000), (elapsed, end)


# ═══════════════════════════════════════════════════════════════════════
# Executor per-node record tests
# ═══════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_new_record_has_start_end_and_outcome():
    state = await _run_instrumented(_exec_success, "0", "UNETLoader")
    timings = state.get("_pre_sampler_node_timings", [])
    assert len(timings) == 1, f"expected exactly 1 record, got {len(timings)}"
    rec = timings[0]
    for key in ("start_perf_ns", "end_perf_ns", "pass_outcome"):
        assert key in rec, f"missing {key!r} in record {rec}"
    assert isinstance(rec["start_perf_ns"], int) and rec["start_perf_ns"] > 0, (
        f"start_perf_ns not a positive int: {rec['start_perf_ns']!r}"
    )
    assert isinstance(rec["end_perf_ns"], int) and rec["end_perf_ns"] > 0, (
        f"end_perf_ns not a positive int: {rec['end_perf_ns']!r}"
    )
    assert rec["end_perf_ns"] >= rec["start_perf_ns"], (
        f"end before start: {rec}"
    )
    assert rec["end_perf_ns"] <= time.perf_counter_ns(), (
        f"end_perf_ns in the future: {rec['end_perf_ns']}"
    )
    assert rec["pass_outcome"] == "COMPLETE", f"got {rec['pass_outcome']!r}"


@pytest.mark.asyncio
async def test_duration_reconciles_with_end_minus_start():
    state = await _run_instrumented(_exec_success, "0", "UNETLoader")
    rec = state["_pre_sampler_node_timings"][0]
    delta = (rec["end_perf_ns"] - rec["start_perf_ns"]) / 1_000_000
    assert abs(delta - rec["duration_ms"]) <= 0.002, (
        f"duration_ms {rec['duration_ms']} does not reconcile with "
        f"end-start {delta:.6f}ms"
    )


@pytest.mark.asyncio
async def test_pending_outcome_marked():
    state = await _run_instrumented(_exec_pending, "0", "KSampler")
    rec = state["_pre_sampler_node_timings"][0]
    assert rec["pass_outcome"] == "PENDING", f"got {rec['pass_outcome']!r}"


@pytest.mark.asyncio
async def test_error_and_cancelled_and_non_tuple_outcomes():
    # Failure: the record is still appended with ERROR outcome.
    state: dict[str, Any] = {}
    with pytest.raises(RuntimeError):
        await _run_instrumented(_exec_failure, "0", "UNETLoader", state=state)
    assert state["_pre_sampler_node_timings"][0]["pass_outcome"] == "ERROR", (
        f"failure record: {state['_pre_sampler_node_timings']}"
    )

    # Cancellation cannot tell us the node's state → UNKNOWN.
    # (install_pre_sampler_hooks is a one-shot install — uninstall first so
    # the new fake is snapshotted as the wrapper's original.)
    uninstall_pre_sampler_hooks()
    state = {}
    with pytest.raises(asyncio.CancelledError):
        await _run_instrumented(_exec_cancelled, "0", "UNETLoader", state=state)
    assert state["_pre_sampler_node_timings"][0]["pass_outcome"] == "UNKNOWN", (
        f"cancelled record: {state['_pre_sampler_node_timings']}"
    )

    # Non-tuple return shape → UNKNOWN.
    uninstall_pre_sampler_hooks()
    state = await _run_instrumented(_exec_non_tuple, "0", "UNETLoader")
    assert state["_pre_sampler_node_timings"][0]["pass_outcome"] == "UNKNOWN", (
        f"non-tuple record: {state['_pre_sampler_node_timings']}"
    )


@pytest.mark.asyncio
async def test_cutoff_clips_sampler_node_record_end():
    cutoff_box: dict[str, Any] = {"ns": None}
    state = await _run_instrumented(
        _make_mid_cutoff_exec(cutoff_box), "1", "KSampler"
    )
    assert cutoff_box["ns"] is not None, "cutoff was not set mid-execution"
    timings = state.get("_pre_sampler_node_timings", [])
    assert len(timings) == 1, f"expected 1 record, got {len(timings)}"
    rec = timings[0]
    assert rec["end_perf_ns"] == cutoff_box["ns"], (
        f"record end {rec['end_perf_ns']} != cutoff {cutoff_box['ns']}"
    )
    delta = (rec["end_perf_ns"] - rec["start_perf_ns"]) / 1_000_000
    assert abs(delta - rec["duration_ms"]) <= 0.002, (
        f"duration_ms {rec['duration_ms']} does not reconcile with "
        f"clipped end-start {delta:.6f}ms"
    )
    assert rec["duration_ms"] < 10, (
        f"record was not truncated: duration_ms={rec['duration_ms']}"
    )


@pytest.mark.asyncio
async def test_structured_report_carries_new_fields():
    state = await _run_instrumented(_exec_success, "0", "UNETLoader")
    result: dict[str, Any] = {}
    _attach_structured_report(result, state)
    report = result["pre_sampler_structured_report"]
    rec = report["per_node_timings"][0]
    for key in ("start_perf_ns", "end_perf_ns", "pass_outcome"):
        assert key in rec, f"missing {key!r} in structured report record {rec}"


# ═══════════════════════════════════════════════════════════════════════
# Waterfall positioning tests
# ═══════════════════════════════════════════════════════════════════════

# Pre-sampler window in the synthetic trace: graph region ~ [1600, 2200] ms
# monotonic (resolved via first_node_to_clip_ms + clip_to_sampler_node_ms);
# sampling stage starts at 2900 ms monotonic.
_PRE_SAMPLER_START_NS = 1_600_000_000
_PRE_SAMPLER_END_NS = 2_200_000_000
_SAMPLING_START_NS = 2_900_000_000

_POSITIONED_NODE = {
    "node_id": "0",
    "class_type": "CLIPTextEncode",
    "duration_ms": 200.0,
    "start_perf_ns": 1_800_000_000,
    "end_perf_ns": 2_000_000_000,
    "pass_outcome": "PENDING",
}
_OLD_STYLE_NODE = {
    "node_id": "2",
    "class_type": "EmptyLatentImage",
    "duration_ms": 100.0,
}


def _make_waterfall_result(per_node_timings: list[dict[str, Any]]) -> dict[str, Any]:
    """Synthetic completed result following tests/test_v2_waterfall.py's
    ``_complete_result`` pattern, plus per_node_timings."""
    def _event(name, wall_ms, mono_ms, process, **metadata):
        return {
            "name": name,
            "process": process,
            "wall_unix_ns": wall_ms * 1_000_000,
            "monotonic_ns": mono_ms * 1_000_000,
            "metadata": metadata,
        }

    events = [
        _event("worker_start", 1000, 1000, "local"),
        _event("transport_entry", 1001, 1001, "local"),
        _event("modal_handle_lookup_start", 1001, 1001, "local"),
        _event("modal_submission_attempt", 1010, 1010, "local"),
        _event("remote_method_entry", 5100, 1100, "remote_method"),
        _event("prompt_executor_invoke_start", 5200, 1200, "remote"),
        _event("sampling_start", 6900, 2900, "remote"),
        _event("sampling_end", 10900, 6900, "remote"),
        _event("vae_decode_start", 10900, 6900, "remote"),
        _event("vae_decode_end", 11400, 7400, "remote"),
        _event("output_encode_start", 11400, 7400, "remote"),
        _event("output_encode_end", 11600, 7600, "remote"),
        _event("output_persist_start", 11600, 7600, "remote"),
        _event("output_persist_end", 12300, 8300, "remote"),
        _event("final_result_received", 13100, 13100, "local"),
        {
            "name": "prompt_executor_milestones",
            "process": "remote",
            "wall_unix_ns": 5_300_000_000,
            "monotonic_ns": 1_300_000_000,
            "metadata": {
                "executor_call_to_first_node_ms": 800,
                "invoke_to_execution_start_ms": 100,
                "execution_start_to_cached_ms": 200,
                "cached_to_first_node_ms": 100,
                "first_node_to_clip_ms": 300,
                "clip_to_sampler_node_ms": 400,
                "sampler_node_to_sampler_start_ms": 200,
                "output_encode_ms": 200,
                "output_commit_ms": 100,
            },
        },
        {
            "name": "pre_sampler_stages",
            "process": "remote",
            "wall_unix_ns": 5_600_000_000,
            "monotonic_ns": 1_600_000_000,
            "metadata": {
                "first_sampler_node_monotonic_ns": 2_200_000_000,
                "sampling_start_monotonic_ns": 2_900_000_000,
            },
        },
    ]
    return {
        "request_id": "request-per-node",
        "identity": {
            "app_name": "stable-modal-comfy-v2-shadow",
            "class_name": "ModalRuntimeEntrypointV2",
            "gpu": "rtx-pro-6000",
            "restored_instance_id": "instance-1",
            "restore_count": 1,
            "request_count": 1,
        },
        "_restore_timing": {
            "remote_python_resume_wall_unix_ns": 4_000_000_000,
            "remote_python_resume_mono_ns": 0,
            "restore_method_start_wall_unix_ns": 4_000_000_000,
            "restore_method_start_mono_ns": 0,
            "restore_method_end_wall_unix_ns": 5_000_000_000,
            "restore_method_end_mono_ns": 1_000_000_000,
            "restore_total_ms": 1000,
        },
        "trace": {"events": events, "metadata": {}},
        "pre_sampler_structured_report": {
            "per_node_timings": per_node_timings,
        },
    }


def _build_report(result: dict[str, Any]):
    return build_waterfall(
        result=result,
        timing={"wall_ms": 12100},
        wall_ms=12100,
        command_start_unix_ms=1000,
        response_received_unix_ns=13100 * 1_000_000,
        run_label="per-node-timeline",
    )


def _node_rows(report):
    return [d for d in report.details if d.key.startswith("node_timing_")]


def test_waterfall_node_rows_positioned_and_non_accounting():
    report = _build_report(_make_waterfall_result(
        [dict(_POSITIONED_NODE), dict(_OLD_STYLE_NODE)]
    ))
    rows = _node_rows(report)
    assert len(rows) == 2, f"expected 2 node rows, got {len(rows)}"

    pos_row = next(d for d in rows if d.key == "node_timing_0")
    assert pos_row.label == "Node: CLIPTextEncode", pos_row.label
    assert pos_row.start_ns == _POSITIONED_NODE["start_perf_ns"], pos_row
    assert pos_row.end_ns == _POSITIONED_NODE["end_perf_ns"], pos_row
    assert pos_row.clock_scope == "monotonic:remote", pos_row.clock_scope
    assert pos_row.status == MEASURED, pos_row.status
    assert pos_row.included_in_total is False, pos_row.included_in_total
    assert pos_row.accounting_role == "child", pos_row.accounting_role
    assert pos_row.source_fields == ("pass_outcome:PENDING",), pos_row.source_fields
    assert pos_row.duration_ms == 200.0, pos_row.duration_ms

    old_row = next(d for d in rows if d.key == "node_timing_1")
    assert old_row.label == "Node: EmptyLatentImage", old_row.label
    assert old_row.start_ns is None, old_row.start_ns
    assert old_row.end_ns is None, old_row.end_ns
    assert old_row.status == DERIVED, old_row.status
    assert old_row.clock_scope == "metadata", old_row.clock_scope
    assert old_row.included_in_total is False, old_row.included_in_total
    assert old_row.accounting_role == "child", old_row.accounting_role


def test_node_rows_do_not_change_reconciliation():
    report = _build_report(_make_waterfall_result(
        [dict(_POSITIONED_NODE), dict(_OLD_STYLE_NODE)]
    ))
    other = _build_report(_make_waterfall_result([]))

    assert report.reconciliation_ms == other.reconciliation_ms, (
        f"reconciliation changed: {report.reconciliation_ms} vs "
        f"{other.reconciliation_ms}"
    )
    assert report.accounted_ms == other.accounted_ms, (
        f"accounted changed: {report.accounted_ms} vs {other.accounted_ms}"
    )
    assert [s.key for s in report.stages] == [s.key for s in other.stages], (
        "top-level stage keys changed"
    )
    for a, b in zip(report.stages, other.stages):
        assert a.duration_ms == b.duration_ms, (
            f"stage {a.key} duration changed: {a.duration_ms} vs {b.duration_ms}"
        )


def test_positioned_node_row_may_overlap_top_level_stage():
    # The node row's interval deliberately overlaps where the pre-sampler
    # execution stage sits (window ~[1600, 2200] ms mono) AND the sampling
    # stage's start (2900 ms mono).  Detail rows are not overlap-checked, so
    # no warnings may be added and no top-level stage may become INVALID.
    overlapping_node = {
        "node_id": "3",
        "class_type": "KSampler",
        "duration_ms": 1250.0,
        "start_perf_ns": _PRE_SAMPLER_START_NS + 100_000_000,
        "end_perf_ns": _SAMPLING_START_NS + 50_000_000,
        "pass_outcome": "COMPLETE",
    }
    report = _build_report(_make_waterfall_result([overlapping_node]))
    other = _build_report(_make_waterfall_result([]))

    assert report.warnings == other.warnings, (
        f"detail-row overlap added warnings: {report.warnings}"
    )
    pre_sampler = next(s for s in report.stages if s.key == "pre_sampler_execution")
    sampling = next(s for s in report.stages if s.key == "sampling")
    assert pre_sampler.status != INVALID, pre_sampler.status
    assert sampling.status != INVALID, sampling.status
    assert sampling.start_ns == _SAMPLING_START_NS, sampling.start_ns


def test_sampler_cutoff_row_end_aligns_with_sampling_start():
    # Simulates the executor clipping the sampler node at sampling_start:
    # the record's end_perf_ns equals the sampling event's monotonic_ns.
    cutoff_rec = {
        "node_id": "1",
        "class_type": "KSampler",
        "duration_ms": 500.0,
        "start_perf_ns": 2_400_000_000,
        "end_perf_ns": _SAMPLING_START_NS,
        "pass_outcome": "COMPLETE",
    }
    report = _build_report(_make_waterfall_result([cutoff_rec]))
    sampling = next(s for s in report.stages if s.key == "sampling")
    node_row = next(d for d in _node_rows(report) if d.key == "node_timing_0")
    assert node_row.end_ns == sampling.start_ns == _SAMPLING_START_NS, (
        f"node row end {node_row.end_ns} != sampling start {sampling.start_ns}"
    )
    assert node_row.status == MEASURED, node_row.status
