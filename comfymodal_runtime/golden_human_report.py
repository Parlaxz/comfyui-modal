"""Pure human-facing rendering for the Golden profiler report.

The report generator owns the measurements and ``report_data.json`` remains
the machine-facing contract.  This module only turns an already materialized
structured report into a small, deterministic console view.  In particular,
the functions below do not read files, inspect clocks, or consult runtime
state.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Any


WIDTH = 100
THRESHOLD_MS = 50.0
BLOCK = "\N{FULL BLOCK}"
POINT = "\N{BLACK CIRCLE}"
UNAVAILABLE = "measurement_unavailable"


class ClockDomainError(ValueError):
    """Raised when a renderer would combine timestamps from different clocks."""


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _text(value: Any, default: str = UNAVAILABLE) -> str:
    if value is None or value == "":
        return default
    return str(value).replace("\r", " ").replace("\n", " ").replace("=", ":")


def _fmt_ms(value: Any) -> str:
    number = _number(value)
    return UNAVAILABLE if number is None else f"{max(0.0, number):.1f}ms"


def _fmt_pct(value: Any) -> str:
    number = _number(value)
    return UNAVAILABLE if number is None else f"{number:.1f}%"


def _domain(value: Mapping[str, Any]) -> str | None:
    for key in ("clock_domain", "clock", "time_domain", "domain"):
        candidate = value.get(key)
        if candidate is not None and str(candidate).strip():
            return str(candidate)
    return None


def _check_clock(
    value: Any,
    clock_domain: str,
    alignment: Mapping[str, Any] | None,
) -> None:
    """Validate a record's declared clock without silently converting it."""
    if not isinstance(clock_domain, str) or not clock_domain.strip():
        raise ClockDomainError("clock_domain must be an explicit non-empty string")
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        for item in value:
            _check_clock(item, clock_domain, alignment)
        return
    if not isinstance(value, Mapping):
        return
    declared = _domain(value)
    if declared is not None and declared != clock_domain:
        if not isinstance(alignment, Mapping):
            raise ClockDomainError(
                f"cross-clock render rejected: {declared!r} versus {clock_domain!r}"
            )
    for key in ("children", "events", "timestamp_lanes"):
        nested = value.get(key)
        if isinstance(nested, Sequence) and not isinstance(nested, (str, bytes)):
            for item in nested:
                _check_clock(item, clock_domain, alignment)


def _valid_interval(
    item: Mapping[str, Any],
    *,
    parent_start: float = 0.0,
    parent_end: float | None = None,
) -> tuple[float, float] | None:
    start = _number(item.get("start_ms"))
    end = _number(item.get("end_ms"))
    absolute_times = start is not None
    if start is None and _number(item.get("start_offset_ms")) is not None:
        start = _number(item.get("start_offset_ms"))
    if end is None and start is not None:
        duration = _number(item.get("duration_ms"))
        if duration is not None:
            end = start + duration
    if start is None or end is None or end < start:
        return None
    # A span from the persisted profile is absolute.  Offset-only children
    # are already relative and are identified by the absence of start_ms.
    if parent_start and absolute_times:
        start -= parent_start
        end -= parent_start
    if parent_end is not None:
        start = max(0.0, min(parent_end, start))
        end = max(0.0, min(parent_end, end))
    return start, end


def _parent_window(parent: Any) -> tuple[float, float, float]:
    """Return relative start, relative end, and wall duration."""
    if isinstance(parent, Mapping):
        start = _number(parent.get("start_ms"))
        end = _number(parent.get("end_ms"))
        wall = _number(parent.get("wall_ms"))
        if start is not None and end is not None and end >= start:
            return start, end, end - start
        if wall is not None:
            return 0.0, max(0.0, wall), max(0.0, wall)
    wall = _number(parent)
    return 0.0, max(0.0, wall or 0.0), max(0.0, wall or 0.0)


def _clip_intervals(
    children: Sequence[Mapping[str, Any]],
    *,
    parent_start: float,
    wall: float,
) -> list[tuple[Mapping[str, Any], float, float]]:
    clipped: list[tuple[Mapping[str, Any], float, float]] = []
    for child in children:
        interval = _valid_interval(child, parent_start=parent_start, parent_end=wall)
        if interval is None:
            continue
        raw_interval = _valid_interval(child, parent_start=parent_start)
        if raw_interval is None:
            continue
        raw_start, raw_end = raw_interval
        if raw_end < 0.0 or raw_start > wall:
            continue
        start, end = interval
        clipped.append((child, start, end))
    return clipped


def _union(intervals: Sequence[tuple[float, float]]) -> list[tuple[float, float]]:
    ordered = sorted(
        ((max(0.0, start), max(0.0, end)) for start, end in intervals if end > start),
        key=lambda pair: (pair[0], pair[1]),
    )
    result: list[tuple[float, float]] = []
    for start, end in ordered:
        if not result or start > result[-1][1]:
            result.append((start, end))
        else:
            result[-1] = (result[-1][0], max(result[-1][1], end))
    return result


def _length(intervals: Sequence[tuple[float, float]]) -> float:
    return sum(end - start for start, end in intervals)


def _bar(start: float, end: float, wall: float, *, point: bool = False) -> str:
    if wall <= 0.0:
        return POINT + " " * (WIDTH - 1) if point else BLOCK + " " * (WIDTH - 1)
    if point or end <= start:
        column = max(0, min(WIDTH - 1, int(start / wall * WIDTH)))
        return " " * column + POINT + " " * (WIDTH - column - 1)
    lo = max(0, min(WIDTH - 1, int(start / wall * WIDTH)))
    hi = max(lo + 1, min(WIDTH, int(math.ceil(end / wall * WIDTH))))
    return " " * lo + BLOCK * (hi - lo) + " " * (WIDTH - hi)


def _row(label: Any, bar: str, duration: Any, pct: Any, source: Any) -> str:
    return f"{_text(label, '?')[:32]:<32} |{bar}| {_fmt_ms(duration)} {_fmt_pct(pct)} [{_text(source, 'unknown')}]"


def _visible_rows(
    children: Sequence[Mapping[str, Any]],
    *,
    parent_start: float,
    wall: float,
    depth: int = 0,
    include_subthreshold: bool = False,
) -> list[tuple[Mapping[str, Any], float, float, int]]:
    rows: list[tuple[Mapping[str, Any], float, float, int]] = []
    for child, start, end in _clip_intervals(
        children, parent_start=parent_start, wall=wall
    ):
        duration = end - start
        nested = child.get("children")
        nested_items = (
            [item for item in nested if isinstance(item, Mapping)]
            if isinstance(nested, list)
            else []
        )
        if include_subthreshold or duration > THRESHOLD_MS or duration == 0.0:
            rows.append((child, start, end, depth))
            child_depth = depth + 1
        else:
            # Short wrappers are hidden, but their long descendants remain
            # useful attribution.  They still participate in this parent's
            # accounting through the direct interval above.
            child_depth = depth
        rows.extend(
            _visible_rows(
                nested_items,
                parent_start=parent_start,
                wall=wall,
                depth=child_depth,
                include_subthreshold=include_subthreshold,
            )
        )
    return rows


def render_mini_gantt(
    parent_ms: float | Mapping[str, Any],
    children: Sequence[Mapping[str, Any]],
    *,
    clock_domain: str = "host_monotonic",
    alignment: Mapping[str, Any] | None = None,
    include_subthreshold: bool = False,
) -> str:
    """Render one 100-column parent/child timeline and its accounting footer."""
    if not isinstance(children, Sequence) or isinstance(children, (str, bytes)):
        raise TypeError("children must be a sequence of mappings")
    parent_start, _parent_end, wall = _parent_window(parent_ms)
    _check_clock(parent_ms, clock_domain, alignment)
    valid_children = [child for child in children if isinstance(child, Mapping)]
    for child in valid_children:
        _check_clock(child, clock_domain, alignment)
    clipped = _clip_intervals(valid_children, parent_start=parent_start, wall=wall)
    all_intervals = [(start, end) for _child, start, end in clipped]
    union = _union(all_intervals)
    child_union = _length(union)
    child_sum = sum(end - start for _child, start, end in clipped)
    overlap = max(0.0, child_sum - child_union)
    subthreshold_union = _length(
        _union(
            [(start, end) for child, start, end in clipped if end - start <= THRESHOLD_MS]
        )
    )
    residual = max(0.0, wall - child_union)
    residual_pct = residual / wall * 100.0 if wall > 0.0 else None

    lines = [
        _row(
            "parent",
            _bar(0.0, wall, wall),
            wall,
            100.0 if wall > 0.0 else 0.0,
            _domain(parent_ms) if isinstance(parent_ms, Mapping) else clock_domain,
        )
    ]
    for child, start, end, depth in _visible_rows(
        valid_children, parent_start=parent_start, wall=wall,
        include_subthreshold=include_subthreshold,
    ):
        duration = end - start
        label = ("  " * depth) + _text(child.get("label", child.get("name", "?")), "?")
        source = child.get("source", child.get("evidence_source", clock_domain))
        lines.append(
            _row(label, _bar(start, end, wall, point=duration == 0.0), duration,
                 duration / wall * 100.0 if wall > 0.0 else 0.0, source)
        )

    # Gaps are based on the union of every valid child, including hidden short
    # children.  This makes the location of a real unowned interval auditable.
    cursor = 0.0
    for start, end in union:
        if start - cursor > THRESHOLD_MS:
            gap = start - cursor
            lines.append(
                _row("[unattributed gap]", _bar(cursor, start, wall), gap,
                     gap / wall * 100.0 if wall > 0.0 else 0.0, "derived")
            )
        cursor = max(cursor, end)
    if wall - cursor > THRESHOLD_MS:
        gap = wall - cursor
        lines.append(
            _row("[unattributed gap]", _bar(cursor, wall, wall), gap,
                 gap / wall * 100.0 if wall > 0.0 else 0.0, "derived")
        )
    lines.append(
        "ACCOUNTING "
        f"wall {_fmt_ms(wall)} child_union {_fmt_ms(child_union)} "
        f"overlap {_fmt_ms(overlap)} subthreshold_union {_fmt_ms(subthreshold_union)} "
        f"residual {_fmt_ms(residual)} residual_pct {_fmt_pct(residual_pct)}"
    )
    return "\n".join(lines)


def _transport_lanes(transport: Mapping[str, Any]) -> tuple[float, list[dict[str, Any]], str]:
    axis = transport.get("timestamp_axis")
    axis = axis if isinstance(axis, Mapping) else {}
    axis_start = _number(axis.get("start_ns"))
    axis_end = _number(axis.get("end_ns"))
    lanes = transport.get("timestamp_lanes")
    lanes = lanes if isinstance(lanes, list) else []
    usable = [row for row in lanes if isinstance(row, Mapping)]
    if axis_start is None and usable:
        axis_start = min((_number(row.get("start_ns")) or 0.0) for row in usable)
    if axis_end is None and usable:
        axis_end = max((_number(row.get("end_ns")) or axis_start or 0.0) for row in usable)
    axis_start = axis_start or 0.0
    axis_end = max(axis_start, axis_end or axis_start)
    wall = (axis_end - axis_start) / 1_000_000.0
    # Collapse producer/token lanes into deterministic aggregate segments.  The
    # raw lane list remains machine evidence; the console is not a per-read or
    # per-token dump, and retaining separate union segments preserves gaps.
    grouped: dict[str, list[tuple[float, float]]] = {}
    for row in usable:
        start = _number(row.get("start_ns"))
        end = _number(row.get("end_ns"))
        if start is None or end is None or end < start:
            continue
        name = str(row.get("lane") or "transport")
        grouped.setdefault(name, []).append(
            ((start - axis_start) / 1_000_000.0, (end - axis_start) / 1_000_000.0)
        )
    children: list[dict[str, Any]] = []
    for name in sorted(grouped):
        intervals = _union(grouped[name])
        for index, (start, end) in enumerate(intervals):
            children.append({
                "label": name if index == 0 else f"{name} (segment {index + 1})",
                "start_ms": start,
                "end_ms": end,
                "source": "timestamp_lanes",
            })
    domain = str(axis.get("clock") or "monotonic_ns")
    return wall, children, domain


def render_transport_gantt(
    transport: Mapping[str, Any],
    *,
    clock_domain: str = "monotonic_ns",
    alignment: Mapping[str, Any] | None = None,
) -> str:
    """Render aggregate source/H2D transport occupancy from persisted lanes."""
    if not isinstance(transport, Mapping):
        raise TypeError("transport must be a mapping")
    _check_clock(transport, clock_domain, alignment)
    wall, children, persisted_domain = _transport_lanes(transport)
    if persisted_domain != clock_domain and not isinstance(alignment, Mapping):
        raise ClockDomainError(
            f"cross-clock render rejected: {persisted_domain!r} versus {clock_domain!r}"
        )
    lines = ["TRANSPORT GANTT"]
    if children and wall > 0.0:
        lines.append(render_mini_gantt(
            wall, children, clock_domain=clock_domain, alignment=alignment
        ))
    else:
        lines.append("transport lanes unavailable")
    return "\n".join(lines)


def render_qd_histogram(
    transport: Mapping[str, Any],
    *,
    clock_domain: str = "monotonic_ns",
    alignment: Mapping[str, Any] | None = None,
) -> str:
    """Render the persisted QD occupancy aggregate without raw event rows."""
    if not isinstance(transport, Mapping):
        raise TypeError("transport must be a mapping")
    _check_clock(transport, clock_domain, alignment)
    values = transport.get("qd_occupancy_ms", transport.get("QD_OCCUPANCY_MS", {}))
    if (not isinstance(values, Mapping) or not values) and transport and all(
        _number(value) is not None for value in transport.values()
    ):
        values = transport
    values = values if isinstance(values, Mapping) else {}
    parsed = [(str(key), _number(value)) for key, value in values.items()]
    parsed = [(key, value) for key, value in parsed if value is not None and value >= 0.0]
    parsed.sort(key=lambda pair: (_number(pair[0]) if _number(pair[0]) is not None else math.inf, pair[0]))
    maximum = max((value for _key, value in parsed), default=0.0)
    lines = ["QD OCCUPANCY HISTOGRAM"]
    for key, value in parsed:
        width = int(round(value / maximum * 40.0)) if maximum else 0
        display_key = _text(key, "?")
        lines.append(f"QD {display_key:<8} {BLOCK * width:<40} {_fmt_ms(value)}")
    if not parsed:
        lines.append("occupancy unavailable")
    return "\n".join(lines)


def _profile(report: Mapping[str, Any]) -> Mapping[str, Any]:
    value = report.get("golden_profile")
    if isinstance(value, Mapping):
        return value
    # Accept the persisted golden summary directly as a convenience for
    # offline consumers; generate_full_trace_report passes the richer machine
    # report_data shape.
    return report if isinstance(report.get("root"), Mapping) else {}


def _root(report: Mapping[str, Any]) -> Mapping[str, Any]:
    profile = _profile(report)
    value = profile.get("root")
    return value if isinstance(value, Mapping) else {}


_OVERALL_CANONICAL_STAGES = (
    "golden_clip_load",
    "golden_clip_forward",
    "golden_unet_load",
    "golden_sampler_prepare",
    "golden_vae_load",
    "golden_sampling",
    "golden_vae_decode",
    "golden_output",
)


def _canonical_interval(
    span: Mapping[str, Any], *, root_start: float, wall: float
) -> tuple[float, float] | None:
    """Return an aligned canonical interval without deriving an end time.

    ``golden_profile`` contains both absolute VizTracer milliseconds and the
    already-normalized ``*_offset_ms`` values.  The real adapter can also
    provide an absolute end alongside a normalized start.  Select the
    coordinate system from the explicit root window; do not use duration as a
    substitute for a missing endpoint.
    """
    absolute_start = _number(span.get("start_ms"))
    absolute_end = _number(span.get("end_ms"))
    offset_start = _number(span.get("start_offset_ms"))
    offset_end = _number(span.get("end_offset_ms"))
    if offset_start is not None:
        start = offset_start
        if offset_end is not None:
            end = offset_end
        elif absolute_end is not None:
            end = absolute_end - root_start
        else:
            return None
    else:
        if absolute_start is None or absolute_end is None:
            return None
        # Prefer the root-relative interpretation only when the pair is
        # already inside the normalized window.  Otherwise, accept the
        # absolute VizTracer pair and align it to the root origin.
        if root_start > 0.0 and root_start <= absolute_start <= root_start + wall and root_start <= absolute_end <= root_start + wall:
            start, end = absolute_start - root_start, absolute_end - root_start
        elif 0.0 <= absolute_start <= wall and 0.0 <= absolute_end <= wall:
            start, end = absolute_start, absolute_end
        else:
            return None
    if end < start:
        return None
    raw_start, raw_end = start, end
    if raw_end < 0.0 or raw_start > wall:
        return None
    return max(0.0, min(wall, raw_start)), max(0.0, min(wall, raw_end))


def _render_canonical_overall(
    root: Mapping[str, Any], spans: Mapping[str, Mapping[str, Any]], *,
    clock_domain: str, alignment: Mapping[str, Any] | None,
) -> str:
    """Render canonical stage ownership and accounting on the root clock."""
    parent_start, _parent_end, wall = _parent_window(root)
    intervals: list[tuple[str, Mapping[str, Any], float, float]] = []
    for name in _OVERALL_CANONICAL_STAGES:
        span = spans.get(name)
        if span is None:
            continue
        _check_clock(span, clock_domain, alignment)
        interval = _canonical_interval(span, root_start=parent_start, wall=wall)
        if interval is not None:
            intervals.append((name, span, *interval))

    union = _union([(start, end) for _name, _span, start, end in intervals])
    stage_sum = sum(end - start for _name, _span, start, end in intervals)
    overlap = max(0.0, stage_sum - _length(union))
    subthreshold_union = _length(
        _union([
            (start, end)
            for _name, _span, start, end in intervals
            if end - start <= THRESHOLD_MS
        ])
    )
    gaps: list[tuple[float, float]] = []
    cursor = 0.0
    for start, end in union:
        if start > cursor:
            gaps.append((cursor, start))
        cursor = max(cursor, end)
    if cursor < wall:
        gaps.append((cursor, wall))
    true_gaps = _length(gaps)

    lines = [
        _row(
            "parent", _bar(0.0, wall, wall), wall,
            100.0 if wall > 0.0 else 0.0, _domain(root) or clock_domain,
        )
    ]
    for name, span, start, end in intervals:
        duration = end - start
        lines.append(_row(
            name, _bar(start, end, wall, point=duration == 0.0), duration,
            duration / wall * 100.0 if wall > 0.0 else 0.0,
            span.get("source", span.get("evidence_source", "canonical")),
        ))
    for start, end in gaps:
        if end - start > THRESHOLD_MS:
            gap = end - start
            lines.append(_row(
                "[true gap]", _bar(start, end, wall), gap,
                gap / wall * 100.0 if wall > 0.0 else 0.0, "derived",
            ))
    lines.append(
        "ACCOUNTING "
        f"wall {_fmt_ms(wall)} canonical_stage_union {_fmt_ms(_length(union))} "
        f"overlap {_fmt_ms(overlap)} subthreshold_union {_fmt_ms(subthreshold_union)} "
        f"true_gaps {_fmt_ms(true_gaps)} residual {_fmt_ms(true_gaps)} "
        f"residual_pct {_fmt_pct(true_gaps / wall * 100.0 if wall > 0.0 else None)}"
    )
    return "\n".join(lines)


def render_overall_timeline(
    report: Mapping[str, Any],
    *,
    clock_domain: str = "host_monotonic",
    alignment: Mapping[str, Any] | None = None,
) -> str:
    """Render the Golden root and its attributed top-level children."""
    if not isinstance(report, Mapping):
        raise TypeError("report must be a mapping")
    root = _root(report)
    _check_clock(report, clock_domain, alignment)
    profile = _profile(report)
    canonical = profile.get("canonical_spans")
    canonical_spans = (
        [span for span in canonical if isinstance(span, Mapping)]
        if isinstance(canonical, list) else []
    )
    canonical_by_name = {
        str(span.get("name")): span for span in canonical_spans
        if str(span.get("name")) in _OVERALL_CANONICAL_STAGES
    }
    children = root.get("children", [])
    children = [item for item in children if isinstance(item, Mapping)] if isinstance(children, list) else []
    if not root:
        return "OVERALL GOLDEN TIMELINE\nprofile unavailable"
    if canonical_by_name:
        return "OVERALL GOLDEN TIMELINE\n" + _render_canonical_overall(
            root, canonical_by_name, clock_domain=clock_domain, alignment=alignment
        )
    return "OVERALL GOLDEN TIMELINE\n" + render_mini_gantt(
        root, children, clock_domain=clock_domain, alignment=alignment
    )


def _stage(report: Mapping[str, Any], name: str) -> Mapping[str, Any] | None:
    profile = _profile(report)
    aliases = {name, name.removeprefix("golden_")}
    spans = profile.get("canonical_spans", [])
    candidates: list[Any] = []
    if isinstance(spans, list):
        candidates.extend(spans)
    nodes = profile.get("nodes", [])
    if isinstance(nodes, list):
        candidates.extend(nodes)
    for container_name in ("stages", "golden_stages"):
        container = report.get(container_name)
        if isinstance(container, Mapping):
            for key, value in container.items():
                if str(key) in aliases and isinstance(value, Mapping):
                    candidate = dict(value)
                    candidate.setdefault("name", str(key))
                    candidates.append(candidate)
        elif isinstance(container, list):
            candidates.extend(container)
    for span in candidates:
        if isinstance(span, Mapping) and str(span.get("name")) in aliases:
            return span
    return None


def _stage_render(
    report: Mapping[str, Any],
    title: str,
    name: str,
    *,
    clock_domain: str,
    alignment: Mapping[str, Any] | None,
) -> str:
    span = _stage(report, name)
    if span is None:
        return f"{title}\nmeasurement unavailable"
    children = span.get("children", [])
    children = [item for item in children if isinstance(item, Mapping)] if isinstance(children, list) else []
    return title + "\n" + render_mini_gantt(
        span, children, clock_domain=clock_domain, alignment=alignment
    )


def render_unresolved(
    unresolved: Sequence[Mapping[str, Any]] | Mapping[str, Any],
    *,
    clock_domain: str = "host_monotonic",
    alignment: Mapping[str, Any] | None = None,
) -> str:
    """Render only unresolved intervals exceeding the human-report threshold."""
    if isinstance(unresolved, Mapping):
        value = unresolved.get("unresolved_over_50ms", [])
        unresolved = value if isinstance(value, Sequence) else []
    if not isinstance(unresolved, Sequence) or isinstance(unresolved, (str, bytes)):
        raise TypeError("unresolved must be a sequence")
    _check_clock(unresolved, clock_domain, alignment)
    rows = []
    for item in unresolved:
        if not isinstance(item, Mapping):
            continue
        duration = _number(item.get("duration_ms", item.get("wall_ms")))
        if duration is None or duration <= THRESHOLD_MS:
            continue
        rows.append((
            _text(item.get("label", item.get("name", item.get("operation", "?"))), "?"),
            duration,
            _text(item.get("source", item.get("evidence_source", "unknown"))),
            _text(item.get("coverage", "remaining")),
            _text(item.get("reason", "not established")),
        ))
    rows.sort(key=lambda row: (-row[1], row[0], row[2], row[3]))
    lines = ["UNRESOLVED >50ms"]
    for category in ("VizTracer coverage", "cross-evidence", "remaining"):
        lines.append(category)
        category_rows = [row for row in rows if row[3] == category]
        if category_rows:
            lines.extend(
                f"{label} {_fmt_ms(duration)} [{source}] reason: {reason}"
                for label, duration, source, _coverage, reason in category_rows
            )
        else:
            lines.append("none")
    return "\n".join(lines)


def render_artifacts_footer(
    report: Mapping[str, Any],
    *,
    clock_domain: str = "host_monotonic",
    alignment: Mapping[str, Any] | None = None,
) -> str:
    """Render concise artifact identity/status information."""
    if not isinstance(report, Mapping):
        raise TypeError("report must be a mapping")
    _check_clock(report, clock_domain, alignment)
    identity = report.get("trace_identity")
    identity = identity if isinstance(identity, Mapping) else {}
    artifact = report.get("full_trace_artifact")
    artifact = artifact if isinstance(artifact, Mapping) else {}
    files = report.get("derived_files", [])
    if not files:
        files = report.get("artifacts", [])
    names = []
    if isinstance(files, list):
        for item in files:
            if isinstance(item, Mapping):
                path = item.get("path")
            else:
                path = item
            if path:
                names.append(_text(str(path).replace("\\", "/").split("/")[-1], "?"))
    names = sorted(set(names))
    human_artifacts = report.get("human_artifacts")
    if isinstance(human_artifacts, Mapping):
        for value in human_artifacts.values():
            if isinstance(value, str) and value.endswith((".txt", ".json", ".md")):
                names.append(value.rsplit("/", 1)[-1])
        names = sorted(set(names))
    lines = ["ARTIFACTS"]
    lines.append(f"status {_text(artifact.get('status', report.get('status')))}")
    if identity.get("request_id"):
        lines.append(f"request {_text(identity.get('request_id'))}")
    if identity.get("trace_entry_count") is not None:
        lines.append(f"trace entries {identity.get('trace_entry_count')}")
    if names:
        lines.append("files")
        for index in range(0, len(names), 5):
            lines.append("  " + ", ".join(names[index:index + 5]))
    else:
        lines.append("files " + UNAVAILABLE)
    return "\n".join(lines)


# The serial runner has more semantic stages than the seven human-facing
# Gantts.  Keep this contract here, beside the renderer, so every artifact and
# the Modal console select the same stage and phase names.
_STAGE_SPECS = (
    ("CLIP LOAD", "golden_clip_load", "clip"),
    ("CLIP FORWARD", "golden_clip_forward", "clip"),
    ("UNET LOAD", "golden_unet_load", "unet"),
    ("SAMPLER PREPARE", "golden_sampler_prepare", "sampler"),
    ("VAE LOAD", "golden_vae_load", "vae"),
    ("SAMPLING", "golden_sampling", "sampling"),
    ("VAE DECODE", "golden_vae_decode", "vae_decode"),
)

_PHASE_LABELS = {
    "clip_forward_entry_setup": "entry/setup",
    "clip_graph_node_wrapper": "graph/model forward",
    "clip_forward_post_sync": "post-forward sync",
    "clip_conditioning_package": "conditioning/package",
    "clip_post_forward_sync_wait": "post-forward sync",
    "clip_conditioning_packaging": "conditioning/package",
    "clip_tokenization_input_prep": "entry/setup",
    "clip_qwen_transformer_encode": "graph/model forward",
    "clip_qwen_transformer_forward": "graph/model forward",
    "header_config_preflight": "header preflight",
    "skeleton_patcher_construction": "patcher construction",
    "source_h2d_transport": "source -> H2D",
    "assign_adoption": "storage adoption",
    "binding_validation": "binding validation",
    "transport_quiescence": "transport quiescence",
    "prepare_seed_cache": "seed/cache",
    "prepare_dependency_closure": "dependency closure",
    "prepare_quiescence": "quiescence",
    "prepare_validation": "validation",
    "vae_qd_transport": "QD transport",
    "vae_patcher_construction": "patcher construction",
    "vae_dtype_device": "dtype/device",
    "vae_storage_adoption": "storage adoption",
    "vae_compute_ready": "compute-ready",
    "vae_decode_seed": "seed",
    "vae_decode_dependency_closure": "dependency closure",
    "vae_decode_quiescence": "quiescence",
    "vae_decode_output_extract": "output extract",
}


def _stage_items(report: Mapping[str, Any], stage_name: str) -> Mapping[str, Any] | None:
    """Find one canonical stage in the normalized report."""
    span = _stage(report, stage_name)
    if span is not None:
        return span
    profile = _profile(report)
    stages = profile.get("stages")
    if isinstance(stages, Mapping):
        value = stages.get(stage_name)
        if isinstance(value, Mapping):
            return value
    return None


def _phase_name(value: Any) -> str:
    text = _text(value, "measurement unavailable")
    return text.rsplit(".", 1)[-1]


def _stage_phase_children(span: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    children = span.get("children", [])
    return [item for item in children if isinstance(item, Mapping)] if isinstance(children, list) else []


def _phase_children_with_labels(span: Mapping[str, Any]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for child in _stage_phase_children(span):
        item = dict(child)
        raw = _phase_name(item.get("name", item.get("label", "phase")))
        item["label"] = _PHASE_LABELS.get(raw, raw.replace("_", " "))
        item.setdefault("source", item.get("evidence_source", "viztracer"))
        result.append(item)
    return result


def _clip_module_rows(report: Mapping[str, Any]) -> list[tuple[str, float]]:
    """Extract bounded CLIP module timing summaries from Golden telemetry."""
    result: list[tuple[str, float]] = []
    root = report.get("runtime_result")
    pending: list[Any] = [root]
    seen: set[int] = set()
    while pending and len(seen) < 256:
        value = pending.pop()
        if not isinstance(value, (Mapping, list, tuple)) or id(value) in seen:
            continue
        seen.add(id(value))
        if isinstance(value, Mapping):
            for key in ("module_host_durations_ns", "module_durations_ns"):
                durations = value.get(key)
                if isinstance(durations, Mapping):
                    for name, duration in durations.items():
                        number = _number(duration)
                        if number is not None and number > 50_000_000:
                            result.append((str(name), number / 1_000_000.0))
            records = value.get("module_records")
            if isinstance(records, list):
                for record in records[:128]:
                    if not isinstance(record, Mapping):
                        continue
                    number = _number(record.get("duration_ms"))
                    if number is None:
                        duration_ns = _number(record.get("duration_ns"))
                        number = duration_ns / 1_000_000.0 if duration_ns is not None else None
                    if number is not None and number > THRESHOLD_MS:
                        result.append((str(record.get("qualified_name", record.get("name", "module"))), number))
            for child in value.values():
                if isinstance(child, (Mapping, list, tuple)):
                    pending.append(child)
        else:
            pending.extend(value[:64])
    merged: dict[str, float] = {}
    for name, duration in result:
        merged[name] = merged.get(name, 0.0) + duration
    return sorted(merged.items(), key=lambda pair: (-pair[1], pair[0]))[:12]


def _persisted_node_rows(report: Mapping[str, Any], stage_name: str) -> list[dict[str, Any]]:
    """Return explicit, report-axis node timings for a canonical stage."""
    runtime_result = report.get("runtime_result")
    if not isinstance(runtime_result, Mapping):
        return []
    records = runtime_result.get("node_timing_records")
    if not isinstance(records, list):
        return []
    expected_class = {
        "golden_vae_decode": "VAEDecode",
    }.get(stage_name)
    if expected_class is None:
        return []
    rows: list[dict[str, Any]] = []
    for record in records[:128]:
        if not isinstance(record, Mapping):
            continue
        class_type = str(record.get("class_type", record.get("node_class", "")))
        if class_type != expected_class:
            continue
        node_id = str(record.get("node_id", record.get("id", "")))
        start_ms = _number(record.get("start_ms"))
        end_ms = _number(record.get("end_ms"))
        if start_ms is None or end_ms is None:
            start_ns = _number(record.get("start_monotonic_ns", record.get("start_ns")))
            end_ns = _number(record.get("end_monotonic_ns", record.get("end_ns")))
            if start_ns is not None and end_ns is not None:
                start_ms, end_ms = start_ns / 1_000_000.0, end_ns / 1_000_000.0
        if start_ms is None or end_ms is None or end_ms <= start_ms:
            continue
        rows.append({
            "label": f"{class_type} node {node_id}" if node_id else class_type,
            "name": class_type,
            "start_ms": start_ms,
            "end_ms": end_ms,
            "duration_ms": end_ms - start_ms,
            "source": "persisted node timing",
            "clock_domain": "host_monotonic",
        })
    return rows


def _clock_line(source: str, clock: str) -> str:
    display = "VizTracer parent clock (host_monotonic)" if clock == "host_monotonic" else clock
    return f"evidence {source}; clock {display}"


def render_stage_gantt(
    report: Mapping[str, Any],
    title: str,
    stage_name: str,
    *,
    role: str = "",
    clock_domain: str = "host_monotonic",
    alignment: Mapping[str, Any] | None = None,
) -> str:
    """Render one detailed stage Gantt using the local 100-column contract."""
    span = _stage_items(report, stage_name)
    lines = [title]
    if span is None:
        lines.extend(["measurement unavailable", _clock_line("VizTracer", clock_domain)])
        return "\n".join(lines)
    _check_clock(span, clock_domain, alignment)
    source = span.get("source", "VizTracer")
    lines.append(_clock_line(source, clock_domain))
    children = _phase_children_with_labels(span)
    node_rows = _persisted_node_rows(report, stage_name)
    timeline_children = [*children, *node_rows]
    if timeline_children:
        lines.append(render_mini_gantt(
            span, timeline_children, clock_domain=clock_domain, alignment=alignment,
            include_subthreshold=True,
        ))
    elif stage_name == "golden_vae_load":
        _parent_start, _parent_end, wall = _parent_window(span)
        lines.append(f"{title} — {_fmt_ms(wall)} parent")
    else:
        lines.append("measurement unavailable; no traced stage phases")

    # A missing phase is an evidence gap, not a zero-duration measurement.  It
    # is deliberately listed as text rather than drawn on the timeline.
    expected = {
        "golden_clip_load": ("source_open_read", "skeleton_patcher_construction", "owner_publish_handoff", "storage_adoption", "compute_ready_proof"),
        "golden_clip_forward": (
            "clip_forward_entry_setup", "clip_graph_node_wrapper",
            "clip_post_forward_sync_wait", "clip_conditioning_packaging",
        ),
        "golden_unet_load": ("header_config_preflight", "skeleton_patcher_construction", "source_h2d_transport", "assign_adoption", "binding_validation", "transport_quiescence"),
        "golden_sampler_prepare": ("prepare_seed_cache", "prepare_dependency_closure", "prepare_quiescence", "prepare_validation"),
        "golden_vae_load": ("qd_transport", "skeleton_patcher_construction", "dtype_device_finalization", "storage_adoption", "compute_ready_return"),
        "golden_sampling": ("setup", "step", "finalization"),
        "golden_vae_decode": ("vae_decode_seed", "vae_decode_dependency_closure", "vae_decode_quiescence", "vae_decode_output_extract"),
    }.get(stage_name, ())
    observed = {_phase_name(item.get("name", item.get("label"))) for item in children}
    missing = [name.replace("_", " ") for name in expected if name not in observed]
    if missing:
        lines.append("unavailable phases: " + ", ".join(missing))
    if stage_name == "golden_clip_load":
        lines.append("header/QD detail: non-temporal fallback when absolute seam timestamps are absent")
    if stage_name == "golden_vae_load":
        lines.append("compute-ready ●; dtype/device and readiness may be point evidence, not a wall")
    if stage_name == "golden_unet_load":
        lines.append("QD occupancy is a histogram, not a timeline")
    if stage_name == "golden_clip_forward":
        lines.append("MODULE DETAIL INCLUSIVE / NON-ADDITIVE")
        module_rows = _clip_module_rows(report)
        if module_rows:
            lines.extend(f"{name} inclusive {_fmt_ms(duration)}" for name, duration in module_rows)
        else:
            module_status = str(
                report.get("clip_module_records_status")
                or report.get("runtime_result", {}).get("clip_module_records_status", "producer_absent")
                if isinstance(report.get("runtime_result"), Mapping)
                else report.get("clip_module_records_status", "producer_absent")
            )
            if module_status == "ingest_failure":
                lines.append("module detail unavailable; aggregate forward wall retained (ingest failure)")
            else:
                lines.append("module detail unavailable; aggregate forward wall retained (producer absent)")
    if stage_name == "golden_vae_decode" and not children and not node_rows:
        lines.append("opaque-node fallback: VAEDecode node detail unavailable; stage wall retained")
    if stage_name == "golden_vae_decode":
        lines.append("VAEDecode node row: " + ("persisted" if node_rows else "measurement unavailable"))
        lines.extend(f"{row['name']} inclusive {_fmt_ms(row['duration_ms'])}" for row in node_rows)
    if stage_name == "golden_sampler_prepare" and not children:
        lines.append("node rows >50ms unavailable; dependency closure evidence is not a trace span")
    elif stage_name == "golden_sampler_prepare":
        lines.append("node rows >50ms: rendered from VizTracer children")
    return "\n".join(lines)


def _transport_intervals(transport: Mapping[str, Any]) -> tuple[float, list[dict[str, Any]], list[tuple[float, float]], list[tuple[float, float]]]:
    axis = transport.get("timestamp_axis")
    axis = axis if isinstance(axis, Mapping) else {}
    lanes = transport.get("timestamp_lanes")
    lanes = lanes if isinstance(lanes, list) else []
    usable: list[dict[str, Any]] = []
    for row in lanes:
        if not isinstance(row, Mapping):
            continue
        start = _number(row.get("start_ns"))
        end = _number(row.get("end_ns"))
        if start is None or end is None or end <= start:
            continue
        usable.append({"lane": str(row.get("lane", "transport")), "label": str(row.get("label", "")), "start": start, "end": end})
    axis_start = _number(axis.get("start_ns"))
    axis_end = _number(axis.get("end_ns"))
    if usable:
        axis_start = min([axis_start, *(row["start"] for row in usable)] if axis_start is not None else [row["start"] for row in usable])
        axis_end = max([axis_end, *(row["end"] for row in usable)] if axis_end is not None else [row["end"] for row in usable])
    axis_start = axis_start or 0.0
    axis_end = max(axis_start, axis_end or axis_start)
    # E27 persists every lane on the same monotonic_ns axis.  Normalize the
    # complete interval set once, at renderer entry, so producer rows use the
    # same relative millisecond coordinates as source/H2D unions below.
    for row in usable:
        row["start"] = (row["start"] - axis_start) / 1_000_000.0
        row["end"] = (row["end"] - axis_start) / 1_000_000.0
    wall = (axis_end - axis_start) / 1_000_000.0
    source = _union([(row["start"], row["end"]) for row in usable if row["lane"] == "source"])
    h2d = _union([(row["start"], row["end"]) for row in usable if row["lane"] == "h2d"])
    return wall, usable, source, h2d


def _intersection(left: Sequence[tuple[float, float]], right: Sequence[tuple[float, float]]) -> list[tuple[float, float]]:
    result: list[tuple[float, float]] = []
    for start, end in left:
        for other_start, other_end in right:
            lo, hi = max(start, other_start), min(end, other_end)
            if hi > lo:
                result.append((lo, hi))
    return _union(result)


def _union_bar(intervals: Sequence[tuple[float, float]], wall: float) -> str:
    """Draw a binary 100-column lane while retaining internal gaps."""
    if wall <= 0.0:
        return " " * WIDTH
    chars = [" "] * WIDTH
    for start, end in intervals:
        lo = max(0, min(WIDTH - 1, int(start / wall * WIDTH)))
        hi = max(lo + 1, min(WIDTH, int(math.ceil(end / wall * WIDTH))))
        for index in range(lo, hi):
            chars[index] = BLOCK
    return "".join(chars)


def render_transport_mini_gantt(
    transport: Mapping[str, Any],
    *,
    title: str = "E27 TRANSPORT MINI-GANTT",
    clock_domain: str = "monotonic_ns",
    alignment: Mapping[str, Any] | None = None,
) -> str:
    """Render bounded E27 occupancy: aggregate lanes, never per-read spam."""
    if not clock_domain or clock_domain == UNAVAILABLE:
        clock_domain = "monotonic_ns"
    _check_clock(transport, clock_domain, alignment)
    wall, raw, source, h2d = _transport_intervals(transport)
    lines = [title, f"evidence E27 persisted transport; clock {clock_domain}"]
    producers: dict[str, list[tuple[float, float]]] = {}
    for row in raw:
        if row["lane"] == "source":
            label = row["label"] or "producer ?"
            producer = label.split("=", 1)[-1] if "=" in label else label
            producers.setdefault(producer, []).append((row["start"], row["end"]))
    # The four producer lanes are the stable E27 visual contract.  Missing
    # producers remain visibly unavailable instead of being inferred.
    source_end = max((end for _start, end in source), default=0.0)
    h2d_end = max((end for _start, end in h2d), default=0.0)
    lane_rows: list[tuple[str, list[tuple[float, float]], str]] = []
    producer_names = sorted(producers, key=lambda value: (int(value) if value.isdigit() else 9999, value))
    for index in range(max(4, len(producer_names))):
        name = producer_names[index] if index < len(producer_names) else str(index)
        lane_rows.append((f"producer {name}", _union(producers.get(name, [])), "E27"))
    intersection = _intersection(source, h2d)
    lane_rows.extend([
        ("source union", source, "E27 derived"),
        ("H2D union", h2d, "E27 derived"),
        ("source ∩ H2D", intersection, "E27 derived"),
        ("post-source tail", [(source_end, h2d_end)] if h2d_end > source_end else [], "E27 derived"),
    ])
    if wall > 0.0:
        lines.extend(
            _row(label, _union_bar(intervals, wall), _length(intervals),
                 _length(intervals) / wall * 100.0, source_name)
            for label, intervals, source_name in lane_rows
        )
    else:
        lines.append("transport intervals unavailable")
    lines.append(render_qd_histogram(transport, clock_domain=clock_domain, alignment=alignment))
    read_bytes = _number(transport.get("source_read_bytes", transport.get("read_bytes")))
    summary = {
        "reads": transport.get("source_read_count", transport.get("read_count", UNAVAILABLE)),
        "GiB": f"{read_bytes / (1024 ** 3):.3f}" if read_bytes is not None else UNAVAILABLE,
        "producers": transport.get("observed_producer_count", transport.get("producer_count", UNAVAILABLE)),
        "wall": _fmt_ms(wall),
        "overlap": _fmt_ms(_length(intersection)),
        "tail": _fmt_ms(max(0.0, h2d_end - source_end)),
        "fallbacks": _text(transport.get("fallback")),
        "poison": _text(transport.get("poison")),
        "mechanism": _text(transport.get("mechanism", transport.get("arm"))),
    }
    lines.append("SUMMARY " + " ".join(f"{key} {value}" for key, value in summary.items()))
    return "\n".join(lines)


def _sampling_report(report: Mapping[str, Any]) -> Mapping[str, Any]:
    value = report.get("sampling_deep_profile")
    return value if isinstance(value, Mapping) else {}


def render_sampling_stage(report: Mapping[str, Any]) -> str:
    """Render sampling A (temporal) and B (dominant model evidence)."""
    deep = _sampling_report(report)
    lines = ["SAMPLING DETAIL", "A. STEP/EVAL TIMELINE (aligned sampling_window)"]
    temporal = _profile(report).get("sampling_temporal_rows", [])
    temporal = temporal if isinstance(temporal, list) else []
    stage = _stage_items(report, "golden_sampling")
    if stage is not None and temporal:
        children = [dict(row, label=row.get("label", "step/eval"), source=row.get("source", "sampling_window")) for row in temporal if isinstance(row, Mapping)]
        try:
            lines.append(render_mini_gantt(
                stage, children, clock_domain="host_monotonic", include_subthreshold=True,
            ))
        except ClockDomainError:
            lines.append("sampling window present but clock alignment is unavailable")
    else:
        lines.append("sampling_window alignment unavailable")
    lines.append("accounting parent-vs-window-vs-union: non-additive; see reconciliation")
    rows = deep.get("human_model_breakdown", deep.get("model_breakdown", []))
    rows = rows if isinstance(rows, list) else []
    raw_rows = deep.get("model_breakdown", [])
    raw_rows = raw_rows if isinstance(raw_rows, list) else []
    hotspots: list[tuple[float, Mapping[str, Any]]] = []
    categories: list[Mapping[str, Any]] = []
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        scope = str(row.get("scope", ""))
        if "category" in scope:
            categories.append(row)
        host = _number(row.get("host_monotonic_ms")) or 0.0
        cuda = _number(row.get("cuda_device_ms")) or 0.0
        value = max(host, cuda)
        if value > THRESHOLD_MS:
            hotspots.append((value, row))
    for row in raw_rows:
        if not isinstance(row, Mapping) or str(row.get("scope", "")) not in {"eval_category", "aggregate_category"}:
            continue
        categories.append(row)
    hotspots.sort(key=lambda item: (-item[0], str(item[1].get("step", "")), str(item[1].get("eval_index", ""))))
    lines.append("B. MODEL DETAIL (dominant rows >50ms; inclusive, non-additive)")
    for value, row in hotspots[:12]:
        lines.append(
            f"step {row.get('step', UNAVAILABLE)} eval {row.get('eval_index', UNAVAILABLE)} "
            f"{row.get('phase', row.get('block', 'model'))} inclusive {_fmt_ms(value)}"
        )
    if len(hotspots) > 12:
        lines.append(f"{len(hotspots) - 12} additional dominant rows omitted; full detail is in report.md")
    if not hotspots:
        lines.append("no model detail above 50ms")
    lines.append("NON-ADDITIVE CATEGORY TABLE")
    for row in categories[:12]:
        lines.append(f"{row.get('category', 'category')} inclusive {_fmt_ms(row.get('host_monotonic_ms', row.get('cuda_device_ms')))}")
    if not categories:
        lines.append("category detail unavailable")
    return "\n".join(lines)


def render_stage_gantts(report: Mapping[str, Any]) -> str:
    """Render the seven detailed Gantts in execution order."""
    parts: list[str] = []
    for title, stage, role in _STAGE_SPECS:
        parts.append(render_stage_artifact(report, title, stage, role=role))
    return "\n\n".join(parts) + "\n"


_TRANSPORT_LOAD_STAGES = {
    "golden_clip_load",
    "golden_unet_load",
    "golden_vae_load",
}


def _stage_transport(
    transport: Mapping[str, Any], stage: str, role: str,
) -> tuple[Mapping[str, Any] | None, bool]:
    """Resolve one load-stage transport projection, failing closed on identity."""
    by_stage = transport.get("by_stage")
    if isinstance(by_stage, Mapping) and stage in by_stage:
        selected = by_stage.get(stage)
        if not isinstance(selected, Mapping):
            return None, False
        reason = str(selected.get("reason", "")).lower()
        if "ambiguous" in reason or "disagree" in reason:
            return None, True
        selected_stage = selected.get("stage")
        selected_role = selected.get("role")
        if (selected_stage is not None and str(selected_stage) != stage) or (
            selected_role is not None and str(selected_role) != role
        ):
            return None, True
        if str(selected.get("status", "")).lower() in {
            "unavailable", "timestamps_unavailable", "reconciliation_invalid",
        }:
            return None, False
        return selected, False

    by_role = transport.get("by_role")
    if isinstance(by_role, Mapping) and role in by_role:
        selected = by_role.get(role)
        if not isinstance(selected, Mapping):
            return None, False
        reason = str(selected.get("reason", "")).lower()
        if "ambiguous" in reason or "disagree" in reason:
            return None, True
        selected_stage = selected.get("stage")
        selected_role = selected.get("role")
        if (selected_stage is not None and str(selected_stage) != stage) or (
            selected_role is not None and str(selected_role) != role
        ):
            return None, True
        if str(selected.get("status", "")).lower() in {
            "unavailable", "timestamps_unavailable", "reconciliation_invalid",
        }:
            return None, False
        return selected, False

    selected_stage = transport.get("stage")
    selected_role = transport.get("role")
    if selected_stage is not None or selected_role is not None:
        if (selected_stage is not None and str(selected_stage) != stage) or (
            selected_role is not None and str(selected_role) != role
        ):
            return None, True
        if str(transport.get("status", "")).lower() in {
            "unavailable", "timestamps_unavailable", "reconciliation_invalid",
        }:
            return None, False
        return transport, False
    return None, bool(transport.get("timestamp_lanes"))


def render_stage_artifact(
    report: Mapping[str, Any], title: str, stage: str, *, role: str = ""
) -> str:
    """Render one stage plus its same-source nested diagnostic sections."""
    parts = [render_stage_gantt(report, title, stage, role=role)]
    if stage == "golden_sampling":
        parts.append(render_sampling_stage(report))
    transport = report.get("source_h2d_transport")
    if stage in _TRANSPORT_LOAD_STAGES and role and isinstance(transport, Mapping):
        selected, ambiguous = _stage_transport(transport, stage, role)
        if ambiguous:
            parts.append("TRANSPORT UNAVAILABLE — ambiguous stage ownership")
        elif isinstance(selected, Mapping):
            parts.append(render_transport_mini_gantt(
                selected, title=f"{role.upper()} TRANSPORT (nested)"
            ))
    return "\n\n".join(parts)


def render_full_console(
    structured_report_dict: Mapping[str, Any],
    *,
    clock_domain: str = "host_monotonic",
    alignment: Mapping[str, Any] | None = None,
) -> str:
    """Render the canonical bounded Golden console from structured data only."""
    if not isinstance(structured_report_dict, Mapping):
        raise TypeError("structured_report_dict must be a mapping")
    report = structured_report_dict
    profile = _profile(report)
    root = _root(report)
    host_clock = clock_domain
    lines = ["GOLDEN PROFILE"]
    lines.extend([
        f"status {_text(profile.get('GOLDEN_PROFILE_COMPLETE', report.get('golden_profile_complete')))}",
        f"reason {_text(profile.get('GOLDEN_PROFILE_REASON', report.get('golden_profile_reason')))}",
        f"wall {_fmt_ms(root.get('wall_ms'))}",
        "clock VizTracer parent clock (host_monotonic)",
    ])
    transport = report.get("source_h2d_transport", report.get("transport"))
    if isinstance(transport, Mapping):
        transport_domain = str(
            ((transport.get("timestamp_axis") or {}).get("clock"))
            if isinstance(transport.get("timestamp_axis"), Mapping)
            else "monotonic_ns"
        )
        if transport_domain == UNAVAILABLE:
            transport_domain = "monotonic_ns"
        lines.append(render_transport_mini_gantt(transport, clock_domain=transport_domain))
    lines.append(render_overall_timeline(
        report, clock_domain=host_clock, alignment=alignment
    ))

    for title, name, role in _STAGE_SPECS:
        lines.append(render_stage_artifact(
            report, title, name, role=role,
        ))

    unresolved = report.get(
        "unresolved_over_50ms",
        profile.get("unresolved_over_50ms", []),
    )
    unresolved = unresolved if isinstance(unresolved, list) else []
    lines.append(render_unresolved(
        unresolved, clock_domain=host_clock, alignment=alignment
    ))
    lines.append(render_artifacts_footer(
        report, clock_domain=host_clock, alignment=alignment
    ))
    return "\n".join(lines) + "\n"


PARALLEL_CONSOLE_GANTT_ORDER = (
    ("golden_restore", "restore"),
    ("golden_request_setup", "request_setup"),
    ("golden_clip_load", "CLIP load"),
    ("golden_unet_load", "UNET load"),
    ("golden_clip_forward", "CLIP forward"),
    ("golden_sampler_prepare", "sampler_prepare"),
    ("golden_sampling", "sampling"),
    ("golden_vae_load", "VAE load"),
    ("golden_sampler_tail", "sampler_tail"),
    ("golden_vae_decode", "VAE decode"),
    ("golden_output", "output"),
    ("golden_durable_commit", "durable_commit"),
    ("golden_teardown", "teardown"),
)

_PARALLEL_CONSOLE_GANTT_WIDTH = 56


def _parallel_gantt_ms(value: Any) -> float | None:
    number = _number(value)
    if number is None:
        return None
    return float(number)


def _parallel_gantt_bar(start_ms: float, end_ms: float, total_ms: float, width: int) -> str:
    if not total_ms > 0 or width < 8:
        return ""
    lo = max(0, min(width - 1, int(start_ms / total_ms * width)))
    hi = max(lo + 1, min(width, int(end_ms / total_ms * width) + 1))
    return "[" + "." * lo + "#" * (hi - lo) + "." * (width - hi) + "]"


def _parallel_gantt_overlap(first: tuple[float, float] | None,
                            second: tuple[float, float] | None) -> float | None:
    if not first or not second:
        return None
    start = max(first[0], second[0])
    end = min(first[1], second[1])
    return max(0.0, end - start) if end > start else 0.0


def render_parallel_console_gantt(
    stages: Mapping[str, Any],
    *,
    transports: Sequence[Mapping[str, Any]] | None = None,
    arch: str = "",
    width: int = _PARALLEL_CONSOLE_GANTT_WIDTH,
    external_restore_ms: Any = None,
    external_snapshot_ms: Any = None,
) -> str:
    """Render one compact ASCII Gantt for a Golden Parallel request.

    Pure rendering over already-recorded measurements: ``stages`` maps a
    recorder stage name to an ``(entry_ns, end_ns)`` pair on ONE monotonic
    clock (normally the session recorder intervals).  Transport records
    contribute standalone durations only -- no cross-clock arithmetic is
    performed.  Stages without a closed interval are skipped silently so a
    partial request still renders.  Output is plain ASCII for Modal logs.
    """
    spans: dict[str, tuple[float, float]] = {}
    if isinstance(stages, Mapping):
        for name, bounds in stages.items():
            entry_ns, end_ns = None, None
            if isinstance(bounds, Mapping):
                entry_ns = _parallel_gantt_ms(bounds.get("entry_monotonic_ns"))
                end_ns = _parallel_gantt_ms(bounds.get("end_monotonic_ns"))
            elif isinstance(bounds, (list, tuple)) and len(bounds) == 2:
                entry_ns = _parallel_gantt_ms(bounds[0])
                end_ns = _parallel_gantt_ms(bounds[1])
            if entry_ns is None or end_ns is None or end_ns < entry_ns:
                continue
            spans[str(name)] = (entry_ns / 1e6, end_ns / 1e6)
    if not spans:
        return "[GOLDEN GANTT]\nno closed stage intervals recorded"
    t0 = min(start for start, _end in spans.values())
    total_ms = max(end for _start, end in spans.values()) - t0
    transport_list = [item for item in (transports or []) if isinstance(item, Mapping)]

    def transport_detail(index: int) -> str:
        if index >= len(transport_list):
            return ""
        record = transport_list[index]
        parts = []
        source_ms = _parallel_gantt_ms(record.get("source_wall_ms"))
        full_ms = _parallel_gantt_ms(record.get("total_load_ms"))
        if source_ms is not None:
            parts.append(f"src={source_ms:.1f}ms")
        if full_ms is not None:
            parts.append(f"full={full_ms:.1f}ms")
        engine = record.get("source_engine")
        if engine:
            parts.append(f"eng={engine}")
        path = record.get("path")
        if path:
            parts.append(str(path).replace("\r", " ").replace("\n", " "))
        return " | " + " ".join(parts) if parts else ""

    arena_note = ""
    if transport_list:
        arena_bytes = _parallel_gantt_ms(transport_list[0].get("c0_arena_bytes"))
        if arena_bytes is not None:
            arena_note = f" arena={arena_bytes / (1024 * 1024):.0f}MiB"
    header = "[GOLDEN GANTT] mode=parallel"
    if arch:
        header += f" arch={arch}"
    header += arena_note
    lines = [header]
    restore_ms = _parallel_gantt_ms(external_restore_ms)
    snapshot_ms = _parallel_gantt_ms(external_snapshot_ms)
    if restore_ms is not None:
        lead = f"external restore: {restore_ms:.1f}ms (pre-method, observation-only)"
        if snapshot_ms is not None:
            lead += f" [platform snapshot {snapshot_ms:.1f}ms]"
        lines.append(lead)
    for stage_name, label in PARALLEL_CONSOLE_GANTT_ORDER:
        bounds = spans.get(stage_name)
        if bounds is None:
            continue
        start_ms, end_ms = bounds[0] - t0, bounds[1] - t0
        wall_ms = end_ms - start_ms
        bar = _parallel_gantt_bar(start_ms, end_ms, total_ms, int(width))
        detail = ""
        if stage_name == "golden_clip_load":
            detail = transport_detail(0)
        elif stage_name == "golden_unet_load":
            detail = transport_detail(1)
        elif stage_name == "golden_restore":
            detail = " | observation-only"
        lines.append(
            f"t+{start_ms / 1000.0:7.3f}s |{label:14s}| {wall_ms:9.1f}ms {bar}{detail}"
        )
    overlaps = [
        ("unet_load", "clip_forward",
         _parallel_gantt_overlap(spans.get("golden_unet_load"), spans.get("golden_clip_forward"))),
        ("vae_load", "sampling",
         _parallel_gantt_overlap(spans.get("golden_vae_load"), spans.get("golden_sampling"))),
    ]
    shown = [f"{inner} inside {outer} {ms:.1f}ms" for inner, outer, ms in overlaps if ms]
    lines.append("OVERLAP: " + ("; ".join(shown) if shown else "none measured"))
    return "\n".join(lines)


__all__ = [
    "ClockDomainError",
    "render_artifacts_footer",
    "render_full_console",
    "render_mini_gantt",
    "render_overall_timeline",
    "render_parallel_console_gantt",
    "render_qd_histogram",
    "render_sampling_stage",
    "render_stage_artifact",
    "render_stage_gantt",
    "render_stage_gantts",
    "render_transport_gantt",
    "render_transport_mini_gantt",
    "render_unresolved",
]
