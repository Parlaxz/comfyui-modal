"""Stage 13 ("Output encode / descriptor") window decomposition.

Pure, deterministic decomposition builder: it turns caller-provided
monotonic timestamps (mono-ns) into a structured breakdown of the Stage 13
parent window ``output_collect_start → remote_result_emit`` (same-process
monotonic clock).  It performs NO timing itself — it only maps boundary
stamps to child spans.

Children tile the parent window so that ``sum(children) ≈ stage13_total``
within ``RECONCILE_TOLERANCE_MS`` (the residual is reported via
``reconciliation_ms`` / ``reconciliation_status``).

This is decomposition, not optimization: waterfall accounting is left
intentionally untouched (the waterfall build span is reported verbatim).
The function never mutates its input and never raises; missing or invalid
boundaries degrade to ``status="partial"`` with ``None`` spans.
"""

from __future__ import annotations

from typing import Any, Mapping

CHILD_NAMES: tuple[str, ...] = (
    "output_collection_ms",
    "asset_local_write_ms",
    "descriptor_build_ms",
    "trace_enrichment_ms",
    "interval_build_ms",
    "resource_enrichment_ms",
    "waterfall_build_ms",
    "other_pre_emit_ms",
)

RECONCILE_TOLERANCE_MS: float = 1.0

# Natural monotonic order of the Stage 13 window stamps (parent start → emit).
_BOUNDARY_KEYS: tuple[str, ...] = (
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


def _ns_to_ms(ns_diff: int) -> float:
    return round(ns_diff / 1_000_000, 3)


def _child_span(lo: int | None, hi: int | None) -> float | None:
    if lo is None or hi is None or hi < lo:
        return None
    return _ns_to_ms(hi - lo)


def _other_pre_emit(boundaries: Mapping[str, Any]) -> float | None:
    """(exec_result_ready − descriptor_end) + (resource_start − interval_end)
    + (emit − waterfall_end); None when any stamp is missing or any term
    would be negative."""
    stamps = (
        "exec_result_ready_mono_ns",
        "descriptor_end_mono_ns",
        "resource_start_mono_ns",
        "interval_end_mono_ns",
        "emit_mono_ns",
        "waterfall_end_mono_ns",
    )
    for key in stamps:
        if boundaries.get(key) is None:
            return None
    terms = (
        boundaries["exec_result_ready_mono_ns"] - boundaries["descriptor_end_mono_ns"],
        boundaries["resource_start_mono_ns"] - boundaries["interval_end_mono_ns"],
        boundaries["emit_mono_ns"] - boundaries["waterfall_end_mono_ns"],
    )
    if any(term < 0 for term in terms):
        return None
    return _ns_to_ms(terms[0] + terms[1] + terms[2])


def build_stage13_breakdown(boundaries: Mapping[str, int | None]) -> dict[str, Any]:
    """Decompose the Stage 13 parent window into child spans.

    *boundaries* keys are mono-ns ints; any may be missing or None.
    Returns the structured breakdown dict (never raises, never mutates the
    input mapping).
    """
    b: dict[str, int | None] = {}
    for key in _BOUNDARY_KEYS:
        value = boundaries.get(key)
        b[key] = value if isinstance(value, int) else None

    children: dict[str, float | None] = {
        "output_collection_ms": _child_span(
            b["output_collect_start_mono_ns"], b["persist_start_mono_ns"]
        ),
        "asset_local_write_ms": _child_span(
            b["persist_start_mono_ns"], b["asset_write_end_mono_ns"]
        ),
        "descriptor_build_ms": _child_span(
            b["asset_write_end_mono_ns"], b["descriptor_end_mono_ns"]
        ),
        "trace_enrichment_ms": _child_span(
            b["exec_result_ready_mono_ns"], b["interval_start_mono_ns"]
        ),
        "interval_build_ms": _child_span(
            b["interval_start_mono_ns"], b["interval_end_mono_ns"]
        ),
        "resource_enrichment_ms": _child_span(
            b["resource_start_mono_ns"], b["resource_end_mono_ns"]
        ),
        "waterfall_build_ms": _child_span(
            b["waterfall_start_mono_ns"], b["waterfall_end_mono_ns"]
        ),
        "other_pre_emit_ms": _other_pre_emit(b),
    }

    all_present = all(value is not None for value in b.values())

    monotonic = True
    if all_present:
        ordered: list[int] = []
        for key in _BOUNDARY_KEYS:
            value = b[key]
            if isinstance(value, int):
                ordered.append(value)
        for prev, cur in zip(ordered, ordered[1:]):
            if cur < prev:
                monotonic = False
                break

    start_ns = b["output_collect_start_mono_ns"]
    emit_ns = b["emit_mono_ns"]
    parent_valid = (
        isinstance(start_ns, int)
        and isinstance(emit_ns, int)
        and emit_ns >= start_ns
    )

    status = "ok" if (all_present and parent_valid and monotonic) else "partial"

    stage13_total_ms: float | None = None
    if parent_valid and isinstance(start_ns, int) and isinstance(emit_ns, int):
        stage13_total_ms = _ns_to_ms(emit_ns - start_ns)

    present = [value for value in children.values() if value is not None]
    sum_children_ms = round(sum(present), 3) if present else 0.0

    reconciliation_ms: float | None = None
    if stage13_total_ms is not None:
        reconciliation_ms = round(stage13_total_ms - sum_children_ms, 3)

    if reconciliation_ms is None:
        reconciliation_status: str | None = None
    elif abs(reconciliation_ms) <= RECONCILE_TOLERANCE_MS:
        reconciliation_status = "ok"
    else:
        reconciliation_status = "gap"

    return {
        "status": status,
        "boundaries_present": all_present,
        "stage13_total_ms": stage13_total_ms,
        **children,
        "sum_children_ms": sum_children_ms,
        "reconciliation_ms": reconciliation_ms,
        "reconciliation_status": reconciliation_status,
        "children_order": list(CHILD_NAMES),
    }
