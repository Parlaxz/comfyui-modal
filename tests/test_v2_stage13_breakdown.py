"""V2 Stage-13 output/descriptor window decomposition contract suite.

Pure decomposition tests against ``comfymodal_runtime.stage13_breakdown``
(no Modal, no ComfyUI graph, no timing):

- ``children_order`` matches the ``CHILD_NAMES`` tuple exactly.
- Children tile the parent window: child spans are never negative, the
  ladder decomposition reconciles within ``RECONCILE_TOLERANCE_MS`` and
  ``reconciliation_ms == stage13_total_ms - sum_children_ms`` exactly.
- Missing boundaries degrade to ``status="partial"`` with ``None`` spans.
- The input mapping is never mutated; negative-diff spans are ``None``.
- A children-sum that exceeds the parent window reports ``"gap"``.
- The breakdown is JSON-safe.
"""

from __future__ import annotations

import json

from comfymodal_runtime.stage13_breakdown import (
    CHILD_NAMES,
    RECONCILE_TOLERANCE_MS,
    build_stage13_breakdown,
)

BOUNDARY_KEYS = (
    "output_collect_start_mono_ns",
    "persist_start_mono_ns",
    "asset_write_end_mono_ns",
    "descriptor_end_mono_ns",
    "exec_result_ready_mono_ns",
    "interval_start_mono_ns",
    "interval_end_mono_ns",
    "resource_start_mono_ns",
    "resource_end_mono_ns",
    "waterfall_start_mono_ns",
    "waterfall_end_mono_ns",
    "emit_mono_ns",
)


def _ladder() -> dict[str, int]:
    """12 strictly monotonic boundaries, i ms apart (i * 1e6 ns, i in 0..11)."""
    return {key: i * 1_000_000 for i, key in enumerate(BOUNDARY_KEYS)}


def _from_gap_ms(gaps: list[float]) -> dict[str, int]:
    """Build 12 monotonic boundaries from per-step gaps in ms."""
    values = [0]
    for gap in gaps:
        values.append(values[-1] + int(gap * 1_000_000))
    return {key: values[i] for i, key in enumerate(BOUNDARY_KEYS)}


# ── 1. Children ordered ─────────────────────────────────────────────────────


def test_children_order_matches_child_names():
    breakdown = build_stage13_breakdown(_ladder())
    assert breakdown["children_order"] == list(CHILD_NAMES)


# ── 2. Ladder: nonnegative durations and exact values ───────────────────────


def test_ladder_children_nonnegative_and_exact_values():
    breakdown = build_stage13_breakdown(_ladder())
    assert breakdown["status"] == "ok"
    for name in CHILD_NAMES:
        assert breakdown[name] >= 0, name
    # 1 ms ladder: seven 1 ms direct spans + three 1 ms pre-emit gaps.
    assert breakdown["output_collection_ms"] == 1.0
    assert breakdown["asset_local_write_ms"] == 1.0
    assert breakdown["descriptor_build_ms"] == 1.0
    assert breakdown["trace_enrichment_ms"] == 1.0
    assert breakdown["interval_build_ms"] == 1.0
    assert breakdown["resource_enrichment_ms"] == 1.0
    assert breakdown["waterfall_build_ms"] == 1.0
    assert breakdown["other_pre_emit_ms"] == 3.0
    assert breakdown["stage13_total_ms"] == 11.0
    assert breakdown["sum_children_ms"] == 10.0
    assert breakdown["reconciliation_ms"] == 1.0
    assert breakdown["reconciliation_status"] == "ok"


# ── 3. Children reconcile the parent window ─────────────────────────────────


def test_ladder_variants_reconcile_parent():
    variants = [
        # g9 (resource_end -> waterfall_start) stays 1 ms in every variant.
        [1, 2, 1, 1, 2, 1, 1, 2, 1, 1, 1],
        [2, 2, 2, 2, 2, 2, 2, 2, 1, 2, 2],
        [0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5],
    ]
    for gaps in variants:
        breakdown = build_stage13_breakdown(_from_gap_ms(gaps))
        assert breakdown["status"] == "ok", gaps
        assert breakdown["stage13_total_ms"] is not None, gaps
        assert abs(breakdown["reconciliation_ms"]) <= RECONCILE_TOLERANCE_MS, gaps
        assert breakdown["reconciliation_status"] == "ok", gaps
        # Exact arithmetic: the stored reconciliation is precisely
        # total - sum (both already rounded to 3 ms decimals).
        assert (
            breakdown["reconciliation_ms"]
            == breakdown["stage13_total_ms"] - breakdown["sum_children_ms"]
        ), gaps


# ── 4. Partial when boundaries missing ──────────────────────────────────────


def test_partial_when_boundaries_missing():
    for boundaries in ({"emit_mono_ns": 1_000_000}, {}):
        breakdown = build_stage13_breakdown(boundaries)  # must not raise
        assert breakdown["status"] == "partial"
        assert breakdown["boundaries_present"] is False
        assert breakdown["stage13_total_ms"] is None
        for name in CHILD_NAMES:
            assert breakdown[name] is None, name
        assert breakdown["reconciliation_ms"] is None
        assert breakdown["reconciliation_status"] is None


# ── 5. Input not mutated ────────────────────────────────────────────────────


def test_input_mapping_not_mutated():
    boundaries = _ladder()
    snapshot = dict(boundaries)
    build_stage13_breakdown(boundaries)
    assert boundaries == snapshot


# ── 6. Negative-diff child span is None ─────────────────────────────────────


def test_negative_diff_child_span_is_none():
    boundaries = _ladder()
    boundaries["persist_start_mono_ns"] = 2_000_000
    boundaries["asset_write_end_mono_ns"] = 1_000_000  # end < start
    breakdown = build_stage13_breakdown(boundaries)  # must not raise
    assert breakdown["asset_local_write_ms"] is None
    assert breakdown["status"] == "partial"
    # Neighbouring spans still decompose from the mutated stamps.
    assert breakdown["output_collection_ms"] == 2.0
    assert breakdown["descriptor_build_ms"] == 2.0
    assert breakdown["reconciliation_ms"] is not None


# ── 7. Tolerance breach reported as "gap" ───────────────────────────────────


def test_reconciliation_gap_reported_when_children_exceed_parent():
    # 1 ms ladder where the (exec_result_ready - descriptor_end) gap is
    # inflated by 5 ms to 6 ms, and the waterfall window overlaps backward
    # into the resource window.  The children then double-count a region:
    # other_pre_emit = 8.0, sum_children = 15.0, stage13_total = 11.0 ->
    # reconciliation = -4.0, which breaches RECONCILE_TOLERANCE_MS.
    boundaries = {
        "output_collect_start_mono_ns": 0,
        "persist_start_mono_ns": 1_000_000,
        "asset_write_end_mono_ns": 2_000_000,
        "descriptor_end_mono_ns": 3_000_000,
        "exec_result_ready_mono_ns": 9_000_000,
        "interval_start_mono_ns": 10_000_000,
        "interval_end_mono_ns": 10_000_000,
        "resource_start_mono_ns": 11_000_000,
        "resource_end_mono_ns": 12_000_000,
        "waterfall_start_mono_ns": 8_000_000,
        "waterfall_end_mono_ns": 10_000_000,
        "emit_mono_ns": 11_000_000,
    }
    breakdown = build_stage13_breakdown(boundaries)
    assert breakdown["other_pre_emit_ms"] == 8.0
    assert breakdown["sum_children_ms"] == 15.0
    assert breakdown["stage13_total_ms"] == 11.0
    assert breakdown["reconciliation_ms"] == -4.0
    assert abs(breakdown["reconciliation_ms"]) > RECONCILE_TOLERANCE_MS
    assert breakdown["reconciliation_status"] == "gap"


# ── 8. JSON-safe ────────────────────────────────────────────────────────────


def test_breakdown_is_json_serializable():
    for boundaries in (_ladder(), {"emit_mono_ns": 1_000_000}, {}):
        breakdown = build_stage13_breakdown(boundaries)
        text = json.dumps(breakdown)  # no default=str needed
        assert text
