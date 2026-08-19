"""Focused tests for the [v2.prompt_executor_breakdown] line builder.

The breakdown line decomposes the execution_start → execution_cached window
(and the execution_cached → first-"executing" window) into the opt_exec_*
sub-spans captured by runtime_executor.  This test drives the pure builder
with synthetic state and asserts:

* every expected key is present in the emitted line
* residual_ms == exec_to_cached_ms − sum(present children) (exact), emitted
  even when some children are absent (absent children are part of residual)
* c2f_residual_ms == cached_to_first_node_ms − sum(present c2f children) (exact)
* signature_keys_ms == add_keys total − is_changed_ms (exact)
* c2f_first_node_prefix_ms is only emitted when a stage-END stamp exists and
  is the post-staging remainder (never the full cached→first-node window, so
  the -138.269-style double-count is impossible)
* missing state renders "absent" without breaking the line
"""

from __future__ import annotations

from comfymodal_runtime.runtime_executor import (
    _PROMPT_EXEC_BREAKDOWN_FIELDS,
    build_prompt_executor_breakdown_line,
)

_EXPECTED_KEYS = (
    "request_id", "exec_to_cached_ms", "dynamic_prompt_ms", "is_changed_ms",
    "signature_keys_ms", "seed_apply_ms", "clean_unused_ms", "cache_gather_ms",
    "cleanup_gc_ms", "residual_ms",
    "c2f_cached_to_first_node_ms", "c2f_topo_walk_ms", "c2f_stage_ms",
    "c2f_first_node_prefix_ms", "c2f_residual_ms",
)


def _parse_fields(line: str) -> dict[str, str]:
    assert line.startswith("[v2.prompt_executor_breakdown]")
    fields: dict[str, str] = {}
    for token in line.split()[1:]:
        key, _, value = token.partition("=")
        fields[key] = value
    return fields


def _float_of(fields: dict[str, str], key: str) -> float:
    value = fields[key]
    assert value != "absent"
    return float(value)


def test_breakdown_line_reconciles_children_to_parents():
    parent_exec_to_cached = 1120.5
    parent_c2f = 140.25
    state = {
        "opt_exec_dynamic_prompt_ms": 80.1234,
        "opt_exec_is_changed_ms": 45.0,
        "opt_exec_signature_keys_total_ms": 210.0,
        "opt_exec_seed_apply_ms": 12.5,
        "opt_exec_clean_unused_ms": 3.25,
        "opt_exec_cache_gather_ms": 700.1,
        "opt_exec_cleanup_gc_ms": 40.0,
        "opt_exec_topo_walk_ms": 30.5,
        "opt_exec_stage_ms": 2.5,
        "opt_exec_stage_end_mono_ns": 1000,
    }
    # executing event fires 25 ms after the first stage completion.
    executing_mono_ns = 1000 + int(25.0 * 1_000_000)

    line = build_prompt_executor_breakdown_line(
        request_id="req-1",
        exec_to_cached_ms=parent_exec_to_cached,
        cached_to_first_node_ms=parent_c2f,
        state=state,
        executing_mono_ns=executing_mono_ns,
    )
    fields = _parse_fields(line)

    # All expected keys are present.
    for key in _EXPECTED_KEYS:
        assert key in fields, f"missing field {key!r} in {line}"
    for key in _PROMPT_EXEC_BREAKDOWN_FIELDS:
        assert key in fields, f"missing module-declared field {key!r}"

    # Derived signature split reconciles exactly.
    assert fields["signature_keys_ms"] == "165.000"
    assert fields["is_changed_ms"] == "45.000"

    # exec→cached: residual == parent − sum(children).
    exec_children = [
        "dynamic_prompt_ms", "is_changed_ms", "signature_keys_ms",
        "seed_apply_ms", "clean_unused_ms", "cache_gather_ms", "cleanup_gc_ms",
    ]
    exec_sum = sum(_float_of(fields, c) for c in exec_children)
    exec_parent = _float_of(fields, "exec_to_cached_ms")
    residual = _float_of(fields, "residual_ms")
    assert residual == round(exec_parent - exec_sum, 3)

    # cached→first-node: residual == parent − sum(children).
    c2f_children = ["c2f_topo_walk_ms", "c2f_stage_ms", "c2f_first_node_prefix_ms"]
    c2f_sum = sum(_float_of(fields, c) for c in c2f_children)
    c2f_parent = _float_of(fields, "c2f_cached_to_first_node_ms")
    c2f_residual = _float_of(fields, "c2f_residual_ms")
    assert c2f_residual == round(c2f_parent - c2f_sum, 3)

    # First-node prefix stamp math is exact (measured from stage END).
    assert fields["c2f_first_node_prefix_ms"] == "25.000"

    # Double-count guard: prefix is the post-staging remainder, so it can
    # never exceed parent − topo − stage (the pre-staging share) — RUN-1's
    # full-window double count made this negative (-138.269).
    assert prefix_within_bounds(fields, "c2f_cached_to_first_node_ms")


def test_prefix_requires_stage_end_stamp():
    """Prefix is only emitted when the stage-END stamp exists; the stage
    entry stamp alone (or a bare first-node timestamp) must NOT emit it."""
    base_state = {
        "opt_exec_topo_walk_ms": 30.5,
        "opt_exec_stage_ms": 2.5,
        "opt_exec_first_stage_mono_ns": 1000,
    }
    executing_mono_ns = 1000 + int(25.0 * 1_000_000)
    for state in (dict(base_state), {}, {"opt_exec_stage_end_mono_ns": 1000}):
        line = build_prompt_executor_breakdown_line(
            request_id="req-prefix",
            exec_to_cached_ms=100.0,
            cached_to_first_node_ms=50.0,
            state=state,
            executing_mono_ns=executing_mono_ns,
        )
        fields = _parse_fields(line)
        if "opt_exec_stage_end_mono_ns" in state:
            assert fields["c2f_first_node_prefix_ms"] == "25.000"
        else:
            # Stage-entry stamp only (or none) → prefix absent, never the
            # parent window, never a bogus value.
            assert fields["c2f_first_node_prefix_ms"] == "absent", line

    # No executing timestamp at all → prefix absent even with the stamp.
    fields = _parse_fields(
        build_prompt_executor_breakdown_line(
            request_id="req-prefix",
            exec_to_cached_ms=100.0,
            cached_to_first_node_ms=50.0,
            state={"opt_exec_stage_end_mono_ns": 1000},
        )
    )
    assert fields["c2f_first_node_prefix_ms"] == "absent"


def test_prefix_never_equals_parent_window():
    """Regression for RUN-1: prefix must not equal the parent window.  With a
    realistic stage-end stamp the prefix is small, and topo + stage + prefix
    never double-count the parent (residual is ~0, never -138)."""
    parent_c2f = 137.443
    topo = 137.295
    stage = 0.974
    # Stage ends ~at the same instant the first node starts (real RUN-1 shape).
    stage_end_mono = 1_000_000
    executing_mono_ns = stage_end_mono + int(0.2 * 1_000_000)  # 0.2 ms later
    fields = _parse_fields(
        build_prompt_executor_breakdown_line(
            request_id="req-run1",
            exec_to_cached_ms=100.0,
            cached_to_first_node_ms=parent_c2f,
            state={
                "opt_exec_topo_walk_ms": topo,
                "opt_exec_stage_ms": stage,
                "opt_exec_stage_end_mono_ns": stage_end_mono,
            },
            executing_mono_ns=executing_mono_ns,
        )
    )
    prefix = _float_of(fields, "c2f_first_node_prefix_ms")
    assert prefix < parent_c2f  # never the full window
    # No double count: topo + stage + prefix lands inside the parent window
    # within the ~0..-1ms boundary-overlap band (never the -138.269 shape).
    assert parent_c2f - (topo + stage + prefix) >= -2.0
    c2f_residual = _float_of(fields, "c2f_residual_ms")
    assert c2f_residual >= -2.0  # ~0 to -1ms overlap artifact, never -138


def prefix_within_bounds(fields: dict[str, str], c2f_parent_key: str) -> bool:
    """Assert the emitted c2f residual is not the RUN-1 double-count shape."""
    prefix = _float_of(fields, "c2f_first_node_prefix_ms")
    parent = _float_of(fields, c2f_parent_key)
    topo = _float_of(fields, "c2f_topo_walk_ms")
    stage = _float_of(fields, "c2f_stage_ms")
    residual = _float_of(fields, "c2f_residual_ms")
    # prefix must be the post-staging remainder (small relative to parent).
    assert prefix < parent, f"prefix {prefix} equals/exceeds parent {parent}"
    # topo + stage + prefix must not double-count the parent.
    assert round(parent - (topo + stage + prefix), 3) >= -2.0
    assert residual >= -2.0, f"double-count residual {residual}"
    return True


def test_breakdown_line_missing_state_renders_absent():
    line = build_prompt_executor_breakdown_line(
        request_id=None,
        exec_to_cached_ms=None,
        cached_to_first_node_ms=None,
        state={},
    )
    fields = _parse_fields(line)
    assert fields["request_id"] == "absent"
    for key in _EXPECTED_KEYS[1:]:
        assert fields[key] == "absent", f"expected absent for {key!r}: {line}"


def test_breakdown_residual_emits_with_partial_children():
    """Residual is computed from PRESENT children only (absent children are
    implicitly part of the residual).  seed_apply_ms missing → residual =
    parent − sum(present) — the RUN-1 shape, which previously hid it."""
    fields = _parse_fields(
        build_prompt_executor_breakdown_line(
            request_id="req-seed",
            exec_to_cached_ms=1429.485,
            cached_to_first_node_ms=10.0,
            state={
                "opt_exec_dynamic_prompt_ms": 0.005,
                "opt_exec_is_changed_ms": 0.483,
                "opt_exec_signature_keys_total_ms": 1409.064,
                "opt_exec_clean_unused_ms": 0.017,
                "opt_exec_cache_gather_ms": 0.065,
                "opt_exec_cleanup_gc_ms": 4.666,
                # no opt_exec_seed_apply_ms
            },
        )
    )
    assert fields["seed_apply_ms"] == "absent"
    present = [
        _float_of(fields, "dynamic_prompt_ms"),
        _float_of(fields, "is_changed_ms"),
        _float_of(fields, "signature_keys_ms"),
        _float_of(fields, "clean_unused_ms"),
        _float_of(fields, "cache_gather_ms"),
        _float_of(fields, "cleanup_gc_ms"),
    ]
    # 1429.485 − 1413.817 ≈ 15.668 (the real RUN-1 exec-window gap).
    assert fields["residual_ms"] == "15.668"

    # c2f window: no c2f children present → c2f residual stays absent.
    assert fields["c2f_cached_to_first_node_ms"] == "10.000"
    assert fields["c2f_topo_walk_ms"] == "absent"
    assert fields["c2f_residual_ms"] == "absent"


def test_breakdown_partial_state_keeps_remaining_absent():
    # Only some captures available → residual renders from present children,
    # fields without any capture stay absent.
    line = build_prompt_executor_breakdown_line(
        request_id="req-2",
        exec_to_cached_ms=100.0,
        cached_to_first_node_ms=10.0,
        state={"opt_exec_dynamic_prompt_ms": 40.0},
    )
    fields = _parse_fields(line)
    assert fields["request_id"] == "req-2"
    assert fields["dynamic_prompt_ms"] == "40.000"
    assert fields["is_changed_ms"] == "absent"
    assert fields["signature_keys_ms"] == "absent"
    # At least one child present → residual = 100.0 − 40.0.
    assert fields["residual_ms"] == "60.000"
    assert fields["c2f_cached_to_first_node_ms"] == "10.000"
    assert fields["c2f_topo_walk_ms"] == "absent"
    # No c2f children present → c2f residual stays absent.
    assert fields["c2f_residual_ms"] == "absent"


def test_topo_lazy_fields_render_when_present_and_absent():
    """topo_lazy_hits / topo_lazy_pending render from the per-request state
    when present and render ``absent`` when the state lacks them (additive
    evidence; the c2f reconciliation formula is untouched)."""
    line = build_prompt_executor_breakdown_line(
        request_id="req-topo-lazy",
        exec_to_cached_ms=100.0,
        cached_to_first_node_ms=10.0,
        state={
            "opt_exec_topo_lazy_hit_count": 39,
            "opt_exec_topo_lazy_saved_count": 12,
        },
    )
    fields = _parse_fields(line)
    assert fields["topo_lazy_hits"] == "39"
    assert fields["topo_lazy_pending"] == "12"
    # The c2f reconciliation children are unchanged by the new fields.
    assert fields["c2f_topo_walk_ms"] == "absent"
    assert fields["c2f_residual_ms"] == "absent"
    assert fields["c2f_cached_to_first_node_ms"] == "10.000"

    # Missing state → both new fields render absent, no crash.
    line_missing = build_prompt_executor_breakdown_line(
        request_id="req-topo-lazy-missing",
        exec_to_cached_ms=100.0,
        cached_to_first_node_ms=10.0,
        state={},
    )
    fields_missing = _parse_fields(line_missing)
    assert fields_missing["topo_lazy_hits"] == "absent"
    assert fields_missing["topo_lazy_pending"] == "absent"

    # Zero counts render as 0 (never collapsed into absent).
    line_zero = build_prompt_executor_breakdown_line(
        request_id="req-topo-lazy-zero",
        exec_to_cached_ms=100.0,
        cached_to_first_node_ms=10.0,
        state={"opt_exec_topo_lazy_hit_count": 0, "opt_exec_topo_lazy_saved_count": 0},
    )
    fields_zero = _parse_fields(line_zero)
    assert fields_zero["topo_lazy_hits"] == "0"
    assert fields_zero["topo_lazy_pending"] == "0"
