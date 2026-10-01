"""Offline exhaustive Golden execution profiler.

Purpose: make wasted time *inside* Golden obvious, from one Markdown artifact,
without adding a single stopwatch to Golden.

This module is the analysis/rendering half of the existing full-trace profiler.
It is not a second profiling architecture: capture is owned exclusively by
:class:`comfymodal_runtime.full_execution_trace.FullExecutionTraceSession`, and
this module is invoked by
:func:`comfymodal_runtime.full_trace_report.generate_full_trace_report` against
artifacts that session already produced.  It imports no profiler and activates
nothing; it is a pure transform over already-captured facts.

Design rules that make the output trustworthy:

* **Dynamic discovery.**  Golden coverage is obtained by walking the call tree
  out of the single authoritative Golden root.  No list of Golden function names
  exists in this module.  A helper added tomorrow underneath
  ``golden_unet_load`` appears automatically.
* **Fail closed.**  ``GOLDEN_EXHAUSTIVE_PROFILE_COMPLETE=YES`` requires every
  contract condition to hold; otherwise the exact reasons are listed and the
  value is ``NO``.  A pretty chart is never labelled complete without evidence.
* **Honest clocks.**  Cross-process ordering is only claimed when the recorded
  VizTracer clock origins agree.  Otherwise the report says
  ``CLOCK_ALIGNMENT=UNPROVEN`` and refuses to draw a merged timeline.
* **No causal invention.**  Bubbles report what overlapped them and how much.
  A cause label is used only where the evidence supports it.
"""

from __future__ import annotations

import csv
import gzip
import io
import json
import os
import sys
import time
from bisect import bisect_left, bisect_right
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

MEASUREMENT_UNAVAILABLE = "measurement_unavailable"

EXHAUSTIVE_SCHEMA = "v2-golden-exhaustive-profile/1"

#: Canonical Golden stages, in contract order.  Used only to *label* sections
#: and to check the completeness contract -- never to decide what to profile.
CANONICAL_STAGE_ORDER: tuple[str, ...] = (
    "golden_restore",
    "golden_request_setup",
    "golden_clip_load",
    "golden_clip_forward",
    "golden_unet_load",
    "golden_sampler_prepare",
    "golden_vae_load",
    "golden_sampling",
    "golden_sampler_tail",
    "golden_vae_decode",
    "golden_output",
    "golden_durable_commit",
)

#: Golden stages that always apply; durability only applies in strict mode.
ALWAYS_REQUIRED_STAGES: tuple[str, ...] = (
    "golden_restore",
    "golden_request_setup",
    "golden_clip_load",
    "golden_clip_forward",
    "golden_unet_load",
    "golden_sampler_prepare",
    "golden_vae_load",
    "golden_sampling",
    "golden_sampler_tail",
    "golden_vae_decode",
    "golden_output",
)

GOLDEN_ROOT_NAMES: tuple[str, ...] = (
    "golden_serial_execute",
    "golden_parallel_execute",
)

#: Chrome-trace category used for the single authoritative Golden root span.
#: VizTracer 1.1.1 hardcodes ``cat="FEE"`` for both explicit ``log_event``
#: spans and automatic Python-call records, so a dedicated category is the only
#: way to make the authoritative root distinguishable offline.
GOLDEN_ROOT_CATEGORY = "GOLDEN_ROOT"

#: Artifact names are fixed so downstream tooling can address them blindly.
REPORT_NAME = "golden_exhaustive_profile.md"
CALLS_NAME = "golden_exhaustive_calls.csv.gz"
MANIFEST_NAME = "golden_process_manifest.json"
SUMMARY_NAME = "golden_exhaustive_summary.json"
MERGED_NAME = "viztracer_merged.json.gz"

#: Fixed-width renderer geometry.  ASCII is authoritative; no Mermaid.
GANTT_WIDTH = 96
LABEL_WIDTH = 34

#: Calls at or above this wall are drawn individually in the Markdown Gantt.
#: Everything smaller is retained in the CSV and grouped into one row per
#: function with an explicit count and time total.  No information is deleted.
DEFAULT_VISUAL_THRESHOLD_MS = 1.0
ENV_VISUAL_THRESHOLD = "COMFYMODAL_GOLDEN_EXHAUSTIVE_VISUAL_MS"

#: Minimum bubble size reported in Markdown.  Bubbles below this are still
#: counted and summed in the machine-readable summary.
DEFAULT_BUBBLE_MIN_MS = 1.0

#: Bubbles that receive full per-interval evidence.  Every bubble is still
#: counted and summed; this only bounds how many get the detailed treatment.
MAX_DETAILED_BUBBLES = 200

#: Top-N sizes for Section 6.
TOP_N = 50

#: Fraction of a bubble that some other lane must cover before that lane is
#: named as the bubble's classification.  Below the threshold the overlap is
#: still reported, just not used as the cause.
LANE_COVERAGE_THRESHOLD = 0.5

#: A merged cross-process timeline is only drawn when every observed process
#: clock origin agrees inside this many nanoseconds.
MAX_CLOCK_SKEW_NS = 1_000_000  # 1 ms

_TRUE_VALUES = frozenset({"1", "true", "yes", "on"})


# ---------------------------------------------------------------------------
# Small shared helpers (kept local so this module stays dependency-free)
# ---------------------------------------------------------------------------


def _safe_float(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    if result != result or result in (float("inf"), float("-inf")):
        return None
    return result


def _safe_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _us_to_ms(value: Any) -> float | None:
    micros = _safe_float(value)
    return None if micros is None else round(micros / 1000.0, 3)


def _basename(name: Any) -> str:
    """Return the semantic name of a trace record, without provenance suffix.

    VizTracer appends `` (file.py:line)`` to both explicit spans and automatic
    Python-call records, so the suffix is not a discriminator.
    """
    value = _qualified_name(name)
    return value.rsplit(".", 1)[-1] if "." in value else value


def _qualified_name(name: Any) -> str:
    """Return the trace name without its `` (file:line)`` provenance suffix."""
    value = str(name or "")
    return value.split(" (", 1)[0]


def _source_from_name(name: Any) -> tuple[str | None, int | None]:
    """Recover ``(source_file, source_line)`` from VizTracer's name suffix.

    VizTracer 1.1.1 encodes provenance as ``name (file.py:line)`` and, unless
    extra capture options are enabled, leaves ``args`` empty.  A name suffix is
    therefore the only place file/line identity exists for a Python call, and it
    is what makes "here are the exact functions/files/lines" answerable.
    """
    value = str(name or "")
    if " (" not in value or not value.endswith(")"):
        return None, None
    suffix = value.rsplit(" (", 1)[1][:-1]
    path, separator, line = suffix.rpartition(":")
    if not separator or not path:
        return None, None
    resolved_line = _safe_int(line)
    if resolved_line is None:
        return None, None
    return path, resolved_line


def _merge_intervals(intervals: Iterable[tuple[float, float]]) -> list[tuple[float, float]]:
    """Return the sorted, disjoint union of *intervals*."""
    ordered = sorted(
        (float(start), float(end))
        for start, end in intervals
        if start is not None and end is not None and float(end) >= float(start)
    )
    merged: list[tuple[float, float]] = []
    for start, end in ordered:
        if merged and start <= merged[-1][1]:
            if end > merged[-1][1]:
                merged[-1] = (merged[-1][0], end)
        else:
            merged.append((start, end))
    return merged


def _union_length(intervals: Iterable[tuple[float, float]]) -> float:
    return sum(end - start for start, end in _merge_intervals(intervals))


def _complement(
    window: tuple[float, float],
    covered: Sequence[tuple[float, float]],
) -> list[tuple[float, float]]:
    """Return the parts of *window* not covered by *covered*."""
    start, end = window
    gaps: list[tuple[float, float]] = []
    cursor = start
    for cover_start, cover_end in _merge_intervals(covered):
        if cover_end <= cursor or cover_start >= end:
            continue
        if cover_start > cursor:
            gaps.append((cursor, min(cover_start, end)))
        cursor = max(cursor, cover_end)
        if cursor >= end:
            break
    if cursor < end:
        gaps.append((cursor, end))
    return [(a, b) for a, b in gaps if b > a]


def _fmt_ms(value: Any, digits: int = 1) -> str:
    number = _safe_float(value)
    if number is None:
        return MEASUREMENT_UNAVAILABLE
    return f"{number:.{digits}f}"


def _fmt_pct(part: Any, whole: Any) -> str:
    numerator = _safe_float(part)
    denominator = _safe_float(whole)
    if numerator is None or not denominator:
        return MEASUREMENT_UNAVAILABLE
    return f"{numerator / denominator * 100.0:.1f}"


def _fmt_int(value: Any) -> str:
    number = _safe_int(value)
    return MEASUREMENT_UNAVAILABLE if number is None else str(number)


def _env_flag(name: str, env: Mapping[str, str] | None = None) -> bool:
    source = os.environ if env is None else env
    try:
        return str(source.get(name) or "").strip().lower() in _TRUE_VALUES
    except Exception:
        return False


def visual_threshold_ms(env: Mapping[str, str] | None = None) -> float:
    """Return the Markdown-only rendering threshold.

    This never affects the retained data: a 20 microsecond call is always in the
    CSV and the JSON tree regardless of this value.
    """
    source = os.environ if env is None else env
    raw = _safe_float(source.get(ENV_VISUAL_THRESHOLD))
    if raw is None or raw < 0:
        return DEFAULT_VISUAL_THRESHOLD_MS
    return raw


# ---------------------------------------------------------------------------
# Section A: process-trace discovery and clock calibration
# ---------------------------------------------------------------------------


def _load_json_maybe_gzip(path: Path) -> Any:
    """Load JSON from *path*, transparently handling ``.gz``."""
    try:
        if path.suffix == ".gz":
            with gzip.open(path, "rb") as handle:
                return json.loads(handle.read().decode("utf-8"))
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _trace_metadata(data: Any) -> dict[str, Any]:
    """Return the ``viztracer_metadata`` block of a parsed trace."""
    if isinstance(data, dict):
        meta = data.get("viztracer_metadata")
        if isinstance(meta, dict):
            return meta
    return {}


def _trace_thread_names(data: Any) -> dict[tuple[Any, Any], str]:
    """Return ``{(pid, tid): thread_name}`` from a trace's metadata events."""
    names: dict[tuple[Any, Any], str] = {}
    events = data.get("traceEvents") if isinstance(data, dict) else None
    if not isinstance(events, list):
        return names
    for event in events:
        if not isinstance(event, dict) or event.get("ph") != "M":
            continue
        if str(event.get("name") or "") not in ("thread_name", "process_name"):
            continue
        args = event.get("args")
        label = args.get("name") if isinstance(args, dict) else None
        if label:
            names.setdefault((event.get("pid"), event.get("tid")), str(label))
    return names


def _trace_pids(data: Any) -> list[Any]:
    pids: list[Any] = []
    events = data.get("traceEvents") if isinstance(data, dict) else None
    if not isinstance(events, list):
        return pids
    for event in events:
        pid = event.get("pid") if isinstance(event, dict) else None
        if pid is not None and pid not in pids:
            pids.append(pid)
    return pids


class ProcessTrace:
    """One process's raw VizTracer artifact plus its trace identity."""

    __slots__ = (
        "role", "pid", "parent_pid", "source", "path", "data", "metadata",
        "base_time_ns", "entry_count", "entry_capacity", "truncated",
        "thread_names", "viztracer_version", "trace_id", "request_id",
        "include_paths", "started_mono_ns", "ended_mono_ns", "error",
    )

    def __init__(self, **kwargs: Any) -> None:
        for slot in self.__slots__:
            setattr(self, slot, kwargs.get(slot))

    def to_dict(self) -> dict[str, Any]:
        return {slot: getattr(self, slot) for slot in self.__slots__}


def _candidate_trace_paths(session_dir: Path) -> list[Path]:
    """Return every process-local raw trace in *session_dir*, deterministically.

    Three naming conventions are accepted so the profiler works with the
    existing ``viztracer.json.gz``/``trace_child_viztracer.json`` artifacts as
    well as the deterministic ``viztracer_<pid>`` names the process bridge
    writes.
    """
    raw_dir = session_dir / "raw"
    if not raw_dir.is_dir():
        return []
    found: list[Path] = []
    for pattern in ("viztracer*.json", "viztracer*.json.gz", "trace_child_viztracer*.json"):
        found.extend(sorted(raw_dir.glob(pattern)))
    unique: list[Path] = []
    seen: set[str] = set()
    for path in found:
        key = path.name
        if key in seen:
            continue
        seen.add(key)
        unique.append(path)
    return unique


def _pid_from_path(path: Path) -> int | None:
    """Extract a pid from a deterministic trace filename, else ``None``."""
    stem = path.name
    for suffix in (".json.gz", ".json"):
        if stem.endswith(suffix):
            stem = stem[: -len(suffix)]
            break
    tail = stem.rsplit("_", 1)[-1]
    return int(tail) if tail.isdigit() else None


def _is_process_trace(data: Any) -> bool:
    """Return whether *data* is a VizTracer trace rather than a manifest.

    A manifest is evidence *about* a trace and must never be counted as one:
    admitting it would invent a process with no clock origin and force a false
    ``CLOCK_ALIGNMENT=UNPROVEN``.
    """
    if not isinstance(data, dict):
        return False
    return isinstance(data.get("traceEvents"), list)


def discover_process_traces(
    session_dir: Path,
    *,
    trace_config: Mapping[str, Any] | None = None,
    parent_pid: Any = None,
) -> list[ProcessTrace]:
    """Build the observed-process set for one session.

    The set is discovered, never declared: every raw process-local trace found
    becomes one entry, and roles come from the per-process metadata sidecar when
    the bridge wrote one.  A trace with no sidecar keeps ``other:<pid>`` rather
    than being attributed to a Golden role it cannot prove.
    """
    config = trace_config or {}
    parent_pid_value = _safe_int(
        parent_pid if parent_pid is not None else config.get("parent_pid")
    )
    processes: list[ProcessTrace] = []
    for path in _candidate_trace_paths(Path(session_dir)):
        data = _load_json_maybe_gzip(path)
        if not _is_process_trace(data):
            # Manifests, sidecars and anything unparseable are not processes.
            continue
        meta = _trace_metadata(data)
        sidecar = _load_json_maybe_gzip(path.with_suffix(".meta.json"))
        if not isinstance(sidecar, dict):
            sidecar = {}
        pids = _trace_pids(data)
        pid = _safe_int(sidecar.get("pid"))
        if pid is None:
            pid = _pid_from_path(path)
        if pid is None:
            pid = _safe_int(pids[0]) if pids else None
        events = data["traceEvents"]
        event_count = len(events)
        capacity = _safe_int(meta.get("entry_capacity")) or _safe_int(
            sidecar.get("trace_entry_capacity")
        )
        if capacity is None:
            capacity = _safe_int(config.get("entry_capacity"))
        overflow = bool(meta.get("overflow"))
        truncated = overflow or (
            capacity is not None and event_count >= capacity and event_count > 0
        )
        role = str(sidecar.get("role") or "").strip()
        is_parent = bool(sidecar.get("is_parent")) or (
            parent_pid_value is not None and pid == parent_pid_value
        )
        if not role:
            role = "parent" if is_parent else f"other:pid{pid}" if pid is not None else "other:unknown"
        processes.append(ProcessTrace(
            role=role,
            pid=pid,
            parent_pid=_safe_int(sidecar.get("parent_pid")),
            source=path.name,
            path=path,
            data=data,
            metadata=meta,
            base_time_ns=_safe_int(
                sidecar.get("base_time_nanoseconds")
                if sidecar.get("base_time_nanoseconds") is not None
                else meta.get("baseTimeNanoseconds")
            ),
            entry_count=_safe_int(sidecar.get("trace_entry_count")) or event_count,
            entry_capacity=capacity,
            truncated=truncated,
            thread_names=_trace_thread_names(data),
            viztracer_version=str(
                sidecar.get("viztracer_version") or meta.get("version") or "unknown"
            ),
            trace_id=str(sidecar.get("trace_id") or config.get("trace_id") or ""),
            request_id=str(sidecar.get("request_id") or ""),
            include_paths=sidecar.get("include_paths") or [],
            started_mono_ns=_safe_int(sidecar.get("started_mono_ns")),
            ended_mono_ns=_safe_int(sidecar.get("ended_mono_ns")),
            error=None,
        ))
    processes.sort(key=lambda p: (0 if p.role == "parent" else 1, p.role, p.pid or 0))
    return processes


def calibrate_clocks(processes: Sequence[ProcessTrace]) -> dict[str, Any]:
    """Decide whether process-local timestamps share one clock domain.

    VizTracer 1.1.1 emits every timestamp relative to a machine-monotonic origin
    recorded as ``baseTimeNanoseconds``.  Two processes that recorded the same
    origin are directly comparable; the residual uncertainty is bounded by the
    difference between the two recorded origins.

    The result is ``PROVEN`` only when every observed process supplied an
    origin and they all agree inside :data:`MAX_CLOCK_SKEW_NS`.  Anything else
    is ``UNPROVEN`` with the exact reason attached -- including the single
    process case, which is trivially aligned and reported as such.
    """
    usable = [p for p in processes if p.error is None]
    if not usable:
        return {
            "status": "UNPROVEN",
            "reason": "no readable process trace",
            "max_skew_ns": None,
            "reference_pid": None,
            "offsets_ns": {},
        }
    missing = [f"{p.role}#{p.pid}" for p in usable if p.base_time_ns is None]
    if missing:
        return {
            "status": "UNPROVEN",
            "reason": "process trace without a recorded clock origin: " + ", ".join(missing),
            "max_skew_ns": None,
            "reference_pid": usable[0].pid,
            "offsets_ns": {},
        }
    reference = usable[0]
    reference_base = int(reference.base_time_ns)
    offsets: dict[str, int] = {}
    skews: list[int] = []
    for process in usable:
        offset = int(process.base_time_ns) - reference_base
        offsets[f"{process.role}#{process.pid}"] = offset
        skews.append(abs(offset))
    max_skew = max(skews)
    if max_skew > MAX_CLOCK_SKEW_NS:
        worst = max(usable, key=lambda p: abs(
            int(p.base_time_ns) - reference_base
        ))
        return {
            "status": "UNPROVEN",
            "reason": (
                f"clock origins disagree by {max_skew} ns "
                f"(> {MAX_CLOCK_SKEW_NS} ns tolerance); worst={worst.role}#{worst.pid}"
            ),
            "max_skew_ns": max_skew,
            "reference_pid": reference.pid,
            "offsets_ns": offsets,
        }
    return {
        "status": "PROVEN",
        "reason": (
            f"all {len(usable)} process traces share one machine-monotonic origin; "
            f"max skew {max_skew} ns <= {MAX_CLOCK_SKEW_NS} ns"
        ),
        "max_skew_ns": max_skew,
        "reference_pid": reference.pid,
        "offsets_ns": offsets,
    }


# ---------------------------------------------------------------------------
# Section B: exhaustive call rows
# ---------------------------------------------------------------------------

EXHAUSTIVE_CALL_FIELDS: tuple[str, ...] = (
    "event_index",
    "process_role",
    "pid",
    "parent_pid",
    "tid",
    "task_id",
    "function",
    "qualified_function",
    "source_file",
    "source_line",
    "category",
    "parent_event_index",
    "parent_function",
    "depth",
    "start_offset_ms",
    "end_offset_ms",
    "wall_ms",
    "direct_child_count",
    "direct_child_sum_ms",
    "direct_child_union_ms",
    "child_overlap_ms",
    "exclusive_self_ms",
    "complete",
)


def _report_module() -> Any:
    """Return the offline report module lazily.

    Both modules import each other inside function bodies only, so there is no
    import-time cycle: the report owns the entry point, this module owns the
    exhaustive transform and reuses the report's existing normalizers rather
    than duplicating them.
    """
    from . import full_trace_report  # type: ignore  # noqa: PLC0415

    return full_trace_report


def _context_key(call: Mapping[str, Any]) -> tuple[Any, Any, str]:
    return (
        call.get("pid"),
        call.get("tid"),
        str(call.get("task_id", "") or ""),
    )


def _same_context(left: Mapping[str, Any], right: Mapping[str, Any]) -> bool:
    return _context_key(left) == _context_key(right)


def _span(call: Mapping[str, Any]) -> tuple[float, float] | None:
    """Return ``(start_us, end_us)`` for a complete call, else ``None``."""
    start = _safe_float(call.get("start_us"))
    end = _safe_float(call.get("end_us"))
    if start is None or end is None or end < start:
        return None
    return start, end


def build_exhaustive_calls(
    processes: Sequence[ProcessTrace],
    *,
    parent_calls: Sequence[Mapping[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Return one normalized call row per captured Python invocation.

    Parent rows are reused verbatim from the session's existing normalizer so the
    exhaustive view cannot disagree with ``calls.csv.gz``.  Each child process is
    normalized with the *same* normalizer, which is what makes the merged view
    comparable rather than a second dialect.
    """
    report = _report_module()
    rows: list[dict[str, Any]] = []
    for process in processes:
        if process.role == "parent" and parent_calls is not None:
            calls = [dict(call) for call in parent_calls]
        else:
            events = report.parse_chrome_trace_events(process.data or {})
            calls = report._build_calls(events)  # noqa: SLF001 - shared normalizer
            report._reconstruct_parents(calls)  # noqa: SLF001
        for call in calls:
            span = _span(call)
            call["process_role"] = process.role
            call["process_parent_pid"] = process.parent_pid
            call["trace_source"] = process.source
            if not call.get("source_file"):
                recovered_file, recovered_line = _source_from_name(call.get("name"))
                if recovered_file:
                    call["source_file"] = recovered_file
                if call.get("source_line") is None and recovered_line is not None:
                    call["source_line"] = recovered_line
            call["span_ok"] = span is not None
            if span is not None:
                call["span_start_us"] = span[0]
                call["span_end_us"] = span[1]
            else:
                call["span_start_us"] = None
                call["span_end_us"] = None
            rows.append(call)
    rows.sort(key=_call_sort_key)
    return rows


def _call_sort_key(call: Mapping[str, Any]) -> tuple[Any, ...]:
    start = call.get("span_start_us")
    return (
        str(call.get("process_role") or ""),
        _safe_int(call.get("pid")) or 0,
        start if start is not None else float("inf"),
        _safe_int(call.get("event_index")) or 0,
        str(call.get("name") or ""),
    )


def _uid(call: Mapping[str, Any]) -> str:
    return (
        f"{call.get('process_role')}#{call.get('pid')}"
        f":{call.get('event_index')}"
    )


def _index_calls(calls: Sequence[Mapping[str, Any]]) -> dict[tuple[Any, Any], dict[str, Any]]:
    index: dict[tuple[Any, Any], dict[str, Any]] = {}
    for call in calls:
        key = (call.get("pid"), call.get("event_index"))
        index[key] = call  # type: ignore[assignment]
    return index


def _children_map(
    calls: Sequence[dict[str, Any]],
) -> dict[tuple[Any, Any], list[dict[str, Any]]]:
    """Group calls by their parent, per process.

    Parenting is only trusted inside one execution context.  A cross-thread or
    cross-process containment is *not* parenthood: those calls become
    concurrent lanes instead, which is the fact a bubble analysis needs.

    A same-context call that is *contained* in a parent but was left unparented
    because of an overlapping sibling is still real work inside that parent.  It
    is attached here, otherwise the parent's exclusive self time would silently
    absorb the sibling's cost.
    """
    index = _index_calls(calls)
    children: dict[tuple[Any, Any], list[dict[str, Any]]] = {}
    for call in calls:
        parent_index = call.get("parent_event_index")
        if parent_index is None:
            continue
        parent = index.get((call.get("pid"), parent_index))
        if parent is None or not _same_context(call, parent):
            continue
        children.setdefault((call.get("pid"), parent_index), []).append(call)  # type: ignore[arg-type]
    _attach_ambiguous_containment(calls, children)
    for bucket in children.values():
        bucket.sort(key=_call_sort_key)
    return children


def _attach_ambiguous_containment(
    calls: Sequence[dict[str, Any]],
    children: dict[tuple[Any, Any], list[dict[str, Any]]],
) -> None:
    """Attach unparented same-context calls to the tightest containing frame.

    One sweep per execution context.  Reconstruction deliberately leaves a
    call unparented when an overlapping (not strictly nested) sibling blocks
    nesting; without this pass that work would be counted as the enclosing
    frame's self time instead of as a child, which is exactly the kind of
    misattribution this profiler exists to prevent.
    """
    by_context: dict[tuple[Any, Any, str], list[dict[str, Any]]] = {}
    for call in calls:
        if not call.get("span_ok"):
            continue
        by_context.setdefault(_context_key(call), []).append(call)
    # Membership per parent bucket.  This used to rescan the parent's existing
    # children for every call, which is O(n^2) across wide frames -- the root
    # alone holds hundreds of thousands of children on a 1.26M event request,
    # and that sweep was costing ~100s.  Seeded from the buckets the explicit
    # parent_event_index pass already filled, so nothing is attached twice.
    attached: dict[tuple[Any, Any], set[int]] = {
        key: {id(existing) for existing in bucket}
        for key, bucket in children.items()
    }
    for context_calls in by_context.values():
        context_calls.sort(key=lambda c: (
            float(c["span_start_us"]), -float(c["span_end_us"]),
            _safe_int(c.get("event_index")) or 0,
        ))
        stack: list[dict[str, Any]] = []
        for call in context_calls:
            start = float(call["span_start_us"])
            end = float(call["span_end_us"])
            while stack and float(stack[-1]["span_end_us"]) <= start + 1e-6:
                stack.pop()
            # Pop frames that merely start earlier but do not contain this call:
            # an overlapping sibling must attach to the enclosing frame, never to
            # a neighbour it overlaps.
            while stack and float(stack[-1]["span_end_us"]) < end - 1e-6:
                stack.pop()
            parent = stack[-1] if stack else None
            if parent is not None:
                parent_key = (parent.get("pid"), parent.get("event_index"))
                call_key = (call.get("pid"), call.get("event_index"))
                seen = attached.get(parent_key)
                if seen is None:
                    seen = attached[parent_key] = set()
                if call_key != parent_key and id(call) not in seen:
                    children.setdefault(parent_key, []).append(call)
                    seen.add(id(call))
            stack.append(call)


def annotate_exclusive_time(
    calls: Sequence[dict[str, Any]],
    children: Mapping[tuple[Any, Any], Sequence[dict[str, Any]]],
) -> None:
    """Fill per-call child accounting and exclusive self time, in place.

    Exclusive time uses the *union* of direct-child intervals so overlapping
    siblings (async fan-out, re-entrant helpers) are never double counted.
    """
    for call in calls:
        span = _span(call)
        key = (call.get("pid"), call.get("event_index"))
        direct = [c for c in children.get(key, ()) if _span(c) is not None]
        intervals = [
            (float(c["span_start_us"]), float(c["span_end_us"])) for c in direct
        ]
        child_sum = sum(end - start for start, end in intervals)
        child_union = _union_length(intervals)
        call["direct_child_count"] = len(direct)
        call["direct_child_sum_ms"] = round(_us_to_ms(child_sum) or 0.0, 3)
        call["direct_child_union_ms"] = round(_us_to_ms(child_union) or 0.0, 3)
        call["child_overlap_ms"] = round(_us_to_ms(child_sum - child_union) or 0.0, 3)
        if span is None:
            call["wall_ms"] = None
            call["exclusive_self_ms"] = None
            continue
        wall = span[1] - span[0]
        call["wall_ms"] = round(_us_to_ms(wall) or 0.0, 3)
        self_ms = wall - child_union
        call["exclusive_self_ms"] = round(_us_to_ms(max(0.0, self_ms)) or 0.0, 3)


# ---------------------------------------------------------------------------
# Section C: authoritative root discovery
# ---------------------------------------------------------------------------


def select_authoritative_root(calls: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """Return the one authoritative Golden root, or fail closed.

    Selection order, and why:

    1. A record whose Chrome category is :data:`GOLDEN_ROOT_CATEGORY`.  That
       category is emitted only by the Golden executor's own span, so it is
       unambiguous by construction.
    2. Otherwise exactly one Python-call record named as a Golden root, which is
       the whole executor function itself.  This is the compatibility path for
       artifacts captured before the dedicated category existed.

    Two candidates for the same root name, or none, is a completeness failure --
    never a silent pick.
    """
    candidates = [c for c in calls if _basename(c.get("name")) in GOLDEN_ROOT_NAMES]
    explicit = [c for c in candidates if c.get("category") == GOLDEN_ROOT_CATEGORY]
    if len(explicit) == 1:
        return {"root": explicit[0], "reason": "complete", "kind": "explicit_root_span"}
    if len(explicit) > 1:
        names = sorted({str(c.get("name")) for c in explicit})
        return {
            "root": None,
            "reason": f"multiple authoritative Golden root spans: {len(explicit)} ({', '.join(names)})",
            "kind": "explicit_root_span",
        }
    hook = [c for c in candidates if c.get("category") == "FEE"]
    if len(hook) == 1:
        return {
            "root": hook[0],
            "reason": "complete",
            "kind": "python_call_record",
        }
    if not candidates:
        return {
            "root": None,
            "reason": "missing Golden root call (expected one of "
                      + ", ".join(GOLDEN_ROOT_NAMES) + ")",
            "kind": "none",
        }
    return {
        "root": None,
        "reason": (
            f"ambiguous Golden root: found {len(candidates)} records named "
            f"{sorted({_basename(c.get('name')) for c in candidates})}"
        ),
        "kind": "ambiguous",
    }


def _containment_descendants(
    root: Mapping[str, Any],
    calls: Sequence[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Return every same-process call contained in *root*'s wall interval.

    Stack nesting cannot express the authoritative root: it is opened around an
    ``await``, so the work it measures runs on a different thread or asyncio task
    and every record looks like an unrelated top-level call.  Time containment
    inside the root's own interval, on the root's own process, is the correct
    relation for a span that delimits the whole executor.

    The interval is also the thing the user cares about, so this stays strictly
    inside the measured root wall and never reaches across processes.
    """
    span = _span(root)
    if span is None or not isinstance(root, dict):
        return []
    pid = root.get("pid")
    start_us, end_us = span
    contained: list[dict[str, Any]] = []
    for call in calls:
        if call is root or not call.get("span_ok"):
            continue
        if pid is not None and call.get("pid") != pid:
            continue
        call_start = call.get("span_start_us")
        call_end = call.get("span_end_us")
        if call_start is None or call_end is None:
            continue
        if call_start >= start_us - 1e-6 and call_end <= end_us + 1e-6:
            contained.append(call)
    return contained


def _assign_containment_depths(
    root: dict[str, Any],
    members: Sequence[dict[str, Any]],
) -> dict[int, dict[str, Any]]:
    """Return the containment tree over *members* under *root*.

    Depth is measured by interval containment rather than by execution context,
    so a stage awaited on another task still nests correctly under the executor.
    """
    parent_of: dict[int, dict[str, Any]] = {}
    stack: list[dict[str, Any]] = [root]
    root["depth"] = 0
    ordered = sorted(
        members,
        key=lambda c: (
            float(c["span_start_us"]), -float(c["span_end_us"]),
            _safe_int(c.get("event_index")) or 0,
        ),
    )
    for call in ordered:
        start = float(call["span_start_us"])
        end = float(call["span_end_us"])
        while stack and float(stack[-1]["span_end_us"]) <= start + 1e-6:
            stack.pop()
        while len(stack) > 1 and float(stack[-1]["span_end_us"]) < end - 1e-6:
            stack.pop()
        call["depth"] = len(stack) - 1
        parent_of[_safe_int(call.get("event_index")) or 0] = stack[-1]
        stack.append(call)
    return parent_of


def resolve_descendants(
    root: Mapping[str, Any],
    calls: Sequence[dict[str, Any]],
    children: Mapping[tuple[Any, Any], Sequence[dict[str, Any]]],
) -> list[dict[str, Any]]:
    """Return every captured descendant of *root*, transitively.

    Two relations are combined, because neither alone is sufficient for a Golden
    root:

    * **stack nesting** inside one execution context -- the normal case for the
      stages that run on the same task as the executor;
    * **time containment** inside the root's own wall interval on the root's own
      process -- required because the root spans an ``await``, so awaited stages
      land on a different thread/task where stack nesting cannot see them.

    Records describing the *same* interval as the root (an explicit span and the
    executor function's own call record) are absorbed rather than nested, because
    they are two measurements of one span.

    Nothing here enumerates Golden function names, so a helper added tomorrow
    underneath any stage appears automatically.
    """
    collected: dict[tuple[Any, Any], dict[str, Any]] = {}

    def walk(call: Mapping[str, Any], depth: int) -> None:
        call["depth"] = depth  # type: ignore[index]
        key = (call.get("pid"), call.get("event_index"))
        if key in collected:
            return
        collected[key] = call  # type: ignore[assignment]
        for child in children.get(key, ()):  # type: ignore[arg-type]
            walk(child, depth + 1)

    root_span = _span(root)
    roots: list[Mapping[str, Any]] = [root]
    if root_span is not None:
        for call in calls:
            span = _span(call)
            if span is None or call is root:
                continue
            if not _same_context(call, root):
                continue
            if _basename(call.get("name")) != _basename(root.get("name")):
                continue
            if (
                abs(span[0] - root_span[0]) < 1e-3
                and abs(span[1] - root_span[1]) < 1e-3
            ):
                roots.append(call)

    for alias in roots:
        walk(alias, 0)

    # Containment pass: everything the root measured, on the root's process.
    if isinstance(root, dict):
        contained = _containment_descendants(root, calls)
        known = {call["event_index"] for call in collected.values()}
        fresh = [call for call in contained if call["event_index"] not in known]
        if fresh:
            _assign_containment_depths(root, fresh)
            for call in fresh:
                collected[(call.get("pid"), call.get("event_index"))] = call

    return sorted(collected.values(), key=_call_sort_key)


# ---------------------------------------------------------------------------
# Section D: canonical stage resolution, lanes and bubble analysis
# ---------------------------------------------------------------------------


def resolve_stage(
    stage: str,
    descendants: Sequence[dict[str, Any]],
    owner: Mapping[str, Any],
) -> dict[str, Any] | None:
    """Return the record that bounds one canonical stage, or ``None``.

    Selection is evidence-based and deterministic: among the records carrying
    this stage's name that lie inside the root's own measured interval, the one
    with the largest measured wall wins.  A stage body and its Python-call
    record cover the same interval, so taking the longest removes a double count
    instead of hiding evidence.  ``candidates_seen`` keeps the discarded ones
    visible.

    Candidate records are matched by **process and containment, not by thread**.
    Golden's overlap schedule runs a canonical stage body on a private executor
    thread (``run_in_executor``), so a same-tid requirement silently discarded
    real, correctly-timed stages: ``golden_clip_forward`` and ``golden_vae_load``
    were observed in the trace and then rejected purely because their thread id
    differed from the root's.  Containment is the honest test -- the span
    genuinely lies within the root's own interval on the same process, which is
    the same rule the root's own descendants are discovered by.
    """
    owner_span = _span(owner)
    candidates: list[dict[str, Any]] = []
    for call in descendants:
        if _basename(call.get("name")) != stage:
            continue
        if not call.get("span_ok"):
            continue
        if owner.get("pid") is not None and call.get("pid") != owner.get("pid"):
            continue
        span = _span(call)
        if span is None:
            continue
        if owner_span is not None and not (
            span[0] >= owner_span[0] - 1e-6 and span[1] <= owner_span[1] + 1e-6
        ):
            continue
        candidates.append(call)
    if not candidates:
        return None

    def key(call: Mapping[str, Any]) -> tuple[float, int]:
        wall = _safe_float(call.get("wall_ms")) or 0.0
        return (-wall, _safe_int(call.get("event_index")) or 0)

    chosen = sorted(candidates, key=key)[0]
    return {
        "stage": stage,
        "call": chosen,
        "candidates_seen": len(candidates),
        "candidate_names": sorted({str(c.get("name")) for c in candidates}),
        "cross_thread": not _same_context(chosen, owner),
    }


def required_stages(trace_config: Mapping[str, Any]) -> list[str]:
    """Return the canonical stages this request is *required* to contain.

    Derived from the request's own durability mode, never from a hardcoded
    per-deployment list.  Observed-but-not-required stages are deliberately not
    promoted here: a stage that happened to run does not become part of the
    contract, or an extra span would mask a genuinely missing one.
    """
    strict = str(
        trace_config.get("output_durability_mode")
        or trace_config.get("output_durability")
        or ""
    ).lower() == "strict"
    stages = list(ALWAYS_REQUIRED_STAGES)
    if strict:
        stages.append("golden_durable_commit")
    return [s for s in CANONICAL_STAGE_ORDER if s in set(stages)]


def build_lanes(
    calls: Sequence[dict[str, Any]],
    thread_names: Mapping[tuple[Any, Any], str],
) -> list[dict[str, Any]]:
    """Return one lane per distinct ``(pid, tid, task)`` execution context."""
    lanes: dict[tuple[Any, Any, str], dict[str, Any]] = {}
    for call in calls:
        if not call.get("span_ok"):
            continue
        key = _context_key(call)
        lane = lanes.get(key)
        if lane is None:
            lane = {
                "pid": call.get("pid"),
                "tid": call.get("tid"),
                "task_id": key[2],
                "process_role": call.get("process_role"),
                "thread_name": thread_names.get(
                    (call.get("pid"), call.get("tid")), ""
                ) or "",
                "calls": [],
                "first_us": None,
                "last_us": None,
            }
            lanes[key] = lane
        lane["calls"].append(call)
        start = float(call["span_start_us"])
        end = float(call["span_end_us"])
        lane["first_us"] = start if lane["first_us"] is None else min(lane["first_us"], start)
        lane["last_us"] = end if lane["last_us"] is None else max(lane["last_us"], end)
    result = []
    for key in sorted(
        lanes,
        key=lambda k: (
            str(lanes[k]["process_role"] or ""),
            _safe_int(k[0]) or 0,
            _safe_int(k[1]) or 0,
            str(k[2]),
        ),
    ):
        lane = lanes[key]
        lane["label"] = lane_label(lane)
        lane["intervals"] = [
            (float(c["span_start_us"]), float(c["span_end_us"]))
            for c in lane["calls"]
        ]
        lane["busy_ms"] = round(_us_to_ms(_union_length(lane["intervals"])) or 0.0, 3)
        lane["wall_span_ms"] = round(
            _us_to_ms((lane["last_us"] or 0.0) - (lane["first_us"] or 0.0)) or 0.0, 3,
        )
        lane["call_count"] = len(lane["calls"])
        lane.pop("calls", None)
        lane["calls"] = []  # keep ordering stable; counts are precomputed
        result.append(lane)
    return result


def lane_label(lane: Mapping[str, Any]) -> str:
    """Return a stable, human-readable lane label."""
    role = str(lane.get("process_role") or "other")
    name = str(lane.get("thread_name") or "")
    tid = lane.get("tid")
    task = str(lane.get("task_id") or "")
    base = f"{role}/tid:{tid}" if tid is not None else role
    if name and name not in base:
        base = f"{base}:{name}"
    if task:
        base = f"{base}/task:{task}"
    return base


BUBBLE_CLASSIFICATIONS: tuple[str, ...] = (
    "SELF_OR_NATIVE",
    "OTHER_THREAD_ACTIVE",
    "OTHER_PROCESS_ACTIVE",
    "ASYNC_WAIT_POSSIBLE",
    "UNTRACED_NATIVE_OR_C",
    "UNKNOWN",
)


def _lane_intervals_in_window(
    lane: Mapping[str, Any],
    window: tuple[float, float],
) -> list[tuple[float, float]]:
    return [
        (max(start, window[0]), min(end, window[1]))
        for start, end in lane.get("intervals", ())
        if end > window[0] and start < window[1]
    ]


def _overlap_length(
    intervals: Sequence[tuple[float, float]],
    window: tuple[float, float],
) -> float:
    clipped = [
        (max(start, window[0]), min(end, window[1]))
        for start, end in intervals
        if end > window[0] and start < window[1]
    ]
    return _union_length(clipped)


def _overlap_of_sorted(
    intervals: Sequence[tuple[float, float]],
    window: tuple[float, float],
) -> float:
    """Overlap of *window* with a pre-merged, sorted, disjoint interval list.

    A two-pointer join keeps bubble analysis linear in the number of intervals
    instead of quadratic in bubbles x calls.  Both inputs are sorted and
    disjoint, which is what makes the single forward pass correct.
    """
    if not intervals:
        return 0.0
    window_start, window_end = window
    total = 0.0
    index = 0
    count = len(intervals)
    while index < count:
        start, end = intervals[index]
        if end <= window_start:
            index += 1
            continue
        if start >= window_end:
            break
        total += max(0.0, min(end, window_end) - max(start, window_start))
        index += 1
    return total


def _bisect_next_start(intervals: Sequence[tuple[float, float]], value: float) -> int:
    low, high = 0, len(intervals)
    while low < high:
        mid = (low + high) // 2
        if intervals[mid][0] < value:
            low = mid + 1
        else:
            high = mid
    return low


def _neighbour_names(
    merged: Sequence[tuple[float, float, str]],
    window: tuple[float, float],
) -> tuple[str, str]:
    """Return the merged-lane names immediately before and after *window*.

    ``merged`` is a sorted list of ``(start, end, name)`` with the name of the
    outermost frame covering each segment, so the answer stays on the bubble's
    own lane.
    """
    before = ""
    for start, end, name in merged:
        if end <= window[0]:
            before = name
            continue
        break
    after = ""
    index = _bisect_next_start([(s, e) for s, e, _ in merged], window[1])
    if index < len(merged):
        after = merged[index][2]
    return before, after


def _semantic_evidence_in_window(
    semantic_ops: Sequence[Mapping[str, Any]],
    window: tuple[float, float],
) -> list[dict[str, Any]]:
    hits: list[dict[str, Any]] = []
    for op in semantic_ops:
        start = _safe_float(op.get("start_us"))
        end = _safe_float(op.get("end_us"))
        if start is None or end is None or end < start:
            continue
        if end <= window[0] or start >= window[1]:
            continue
        hits.append({
            "operation_type": str(op.get("operation_type") or op.get("name") or ""),
            "overlap_ms": round(
                _us_to_ms(min(end, window[1]) - max(start, window[0])) or 0.0, 3
            ),
        })
    hits.sort(key=lambda h: (-float(h["overlap_ms"]), str(h["operation_type"])))
    return hits


def _merged_lane_timeline(
    owner_calls: Sequence[Mapping[str, Any]],
) -> list[tuple[float, float, str]]:
    """Return ``(start, end, name)`` segments of the owner's busy timeline.

    Built by a single sweep so bubble analysis never rescans the call list.
    """
    events: list[tuple[float, int, str]] = []
    for call in owner_calls:
        span = _span(call)
        if span is None:
            continue
        name = _qualified_name(call.get("name"))
        events.append((span[0], 1, name))
        events.append((span[1], -1, name))
    if not events:
        return []
    events.sort(key=lambda e: (e[0], e[1]))
    segments: list[tuple[float, float, str]] = []
    active: list[str] = []
    cursor = events[0][0]
    for position, (timestamp, kind, name) in enumerate(events):
        if timestamp > cursor and active:
            segments.append((cursor, timestamp, active[-1]))
        if kind == 1:
            active.append(name)
        elif active:
            # Remove the innermost matching entry; identical names may repeat.
            for offset in range(len(active) - 1, -1, -1):
                if active[offset] == name:
                    del active[offset]
                    break
        cursor = timestamp
        del position
    return segments


def analyze_bubbles(
    *,
    window: tuple[float, float],
    owner: Mapping[str, Any],
    subject: Mapping[str, Any],
    owner_calls: Sequence[Mapping[str, Any]],
    lanes: Sequence[Mapping[str, Any]],
    semantic_ops: Sequence[Mapping[str, Any]],
    clock_alignment: Mapping[str, Any],
    cpu_evidence: Mapping[str, Any],
    c_function_tracing: bool,
    enclosing_frames: Sequence[Mapping[str, Any]] = (),
    detail_limit: int = MAX_DETAILED_BUBBLES,
) -> dict[str, Any]:
    """Return the uncovered intervals inside *window* on the owner's context.

    A bubble is defined strictly as *a time interval inside the subject frame's
    wall not covered by a traced child on that same execution context*.  It does
    not mean idle, does not mean storage wait and does not mean scheduling delay.
    What did overlap it is measured and reported; the cause label is applied only
    when that measurement supports it.

    ``subject`` (the stage or the root) is deliberately excluded from its own
    coverage.  Including it would cover the whole window and report zero
    bubbles, which would hide exactly the "400 ms vanished between two fast
    calls" case this exists to find.

    Every bubble is counted and summed, but only the ``detail_limit`` largest
    get full per-interval evidence.  The rest stay in the JSON summary as
    counts and totals, so nothing is silently dropped.
    """
    owner_key = _context_key(owner)
    owner_pid = owner.get("pid")
    segments = _merged_lane_timeline([
        call for call in owner_calls if call is not subject
    ])
    same_context = [(start, end) for start, end, _ in segments]
    other_thread: list[tuple[float, float]] = []
    other_process: list[tuple[float, float]] = []
    active_other_lanes: list[dict[str, Any]] = []
    owner_key = _context_key(owner)
    owner_pid = owner.get("pid")
    for lane in lanes:
        key = (lane.get("pid"), lane.get("tid"), str(lane.get("task_id") or ""))
        if key == owner_key:
            continue
        merged = _merge_intervals(lane.get("intervals") or ())
        clipped = [
            (max(s, window[0]), min(e, window[1]))
            for s, e in merged
            if e > window[0] and s < window[1]
        ]
        if not clipped:
            continue
        active_other_lanes.append({
            "lane": lane_label(lane),
            "process_role": str(lane.get("process_role") or ""),
            "pid": lane.get("pid"),
            "tid": lane.get("tid"),
            "task_id": str(lane.get("task_id") or ""),
            "busy_ms": round(_us_to_ms(_union_length(clipped)) or 0.0, 3),
        })
        target = (
            other_process if lane.get("pid") != owner_pid else other_thread
        )
        target.extend(clipped)
    other_thread = _merge_intervals(other_thread)
    other_process = _merge_intervals(other_process)

    cross_process_usable = str(clock_alignment.get("status")) == "PROVEN"
    gaps = _complement(window, same_context)
    total_ms = sum(end - start for start, end in gaps)

    ordered = sorted(gaps, key=lambda g: (-(g[1] - g[0]), g[0]))
    detailed_gaps = ordered[:detail_limit]

    enclosing_spans = sorted(
        [
            (float(s), float(e), _qualified_name(frame.get("name")))
            for frame in enclosing_frames
            for s, e in [_span(frame) or (0.0, 0.0)]
        ],
        key=lambda item: (item[0], -item[1]),
    )

    bubbles: list[dict[str, Any]] = []
    for index, (start, end) in enumerate(detailed_gaps):
        span = (start, end)
        duration_ms = _us_to_ms(end - start) or 0.0
        thread_ms = _us_to_ms(_overlap_of_sorted(other_thread, span)) or 0.0
        process_ms = (
            _us_to_ms(_overlap_of_sorted(other_process, span)) or 0.0
        ) if cross_process_usable else None
        semantic = _semantic_evidence_in_window(semantic_ops, span)
        cpu = _cpu_evidence_in_window(cpu_evidence, span)
        enclosing = _enclosing_frame(enclosing_spans, span)
        classification, why = _classify_bubble(
            duration_ms=duration_ms,
            thread_ms=thread_ms,
            process_ms=process_ms,
            cross_process_usable=cross_process_usable,
            cpu=cpu,
            enclosing=bool(enclosing),
            c_function_tracing=c_function_tracing,
        )
        previous, following = _neighbour_names(segments, span)
        bubbles.append({
            "index": index,
            "start_offset_ms": round(_us_to_ms(start - window[0]) or 0.0, 3),
            "end_offset_ms": round(_us_to_ms(end - window[0]) or 0.0, 3),
            "duration_ms": round(duration_ms, 3),
            "previous_function": previous,
            "next_function": following,
            "same_thread_traced_ms": 0.0,
            "other_thread_traced_ms": round(thread_ms, 3),
            "other_process_traced_ms": process_ms,
            "cross_process_alignment": clock_alignment.get("status"),
            "semantic_evidence": semantic[:8],
            "cpu_evidence": cpu,
            "classification": classification,
            "classification_basis": why,
            "enclosing_python_frame": enclosing or "",
        })
    bubbles.sort(key=lambda b: (-float(b["duration_ms"]), float(b["start_offset_ms"])))
    return {
        "bubbles": bubbles,
        "bubble_count": len(gaps),
        "detailed_bubble_count": len(bubbles),
        "total_bubble_ms": round(_us_to_ms(total_ms) or 0.0, 3),
        "window_ms": round(_us_to_ms(window[1] - window[0]) or 0.0, 3),
        "other_lanes_active": sorted(
            active_other_lanes, key=lambda l: (-float(l["busy_ms"]), str(l["lane"])),
        ),
    }


def _enclosing_frame(
    enclosing_spans: Sequence[tuple[float, float, str]],
    window: tuple[float, float],
) -> str:
    """Return the name of the innermost traced frame covering *window*."""
    best = ""
    best_span = None
    for start, end, name in enclosing_spans:
        if start <= window[0] and end >= window[1]:
            width = end - start
            if best_span is None or width < best_span:
                best_span = width
                best = name
    return best


def _cpu_evidence_in_window(
    cpu_evidence: Mapping[str, Any],
    window: tuple[float, float],
) -> dict[str, Any]:
    """Return resource-sampler evidence overlapping *window*, if any.

    Absence of samples is reported as ``unavailable``; it is never read as
    "the thread was idle".
    """
    samples = cpu_evidence.get("samples_by_pid_tid")
    if not isinstance(samples, Mapping) or not samples:
        return {"status": "unavailable", "reason": "no_cpu_samples"}
    start_ms = _us_to_ms(window[0]) or 0.0
    end_ms = _us_to_ms(window[1]) or 0.0
    running = 0
    total = 0
    for bucket in samples.values():
        entries = bucket if isinstance(bucket, list) else []
        for entry in entries:
            if not isinstance(entry, Mapping):
                continue
            sample_at = _safe_float(entry.get("t_ms"))
            if sample_at is None or sample_at < start_ms or sample_at > end_ms:
                continue
            total += 1
            if _safe_float(entry.get("cpu_running_ms_delta")):
                running += 1
    if not total:
        return {"status": "unavailable", "reason": "no_samples_in_window"}
    return {
        "status": "available",
        "samples_in_window": total,
        "samples_with_cpu_progress": running,
    }


def _classify_bubble(
    *,
    duration_ms: float,
    thread_ms: float,
    process_ms: float | None,
    cross_process_usable: bool,
    cpu: Mapping[str, Any],
    enclosing: bool,
    c_function_tracing: bool,
) -> tuple[str, str]:
    """Return ``(classification, basis)`` for one bubble.

    Precedence is deliberate and evidence-bound:

    1. Another thread on the same process was busy for most of the bubble.
    2. Another process was busy for most of the bubble, and the clocks were
       proven comparable before that claim is made at all.
    3. The bubble sits inside a traced Python frame, so it is that frame's own
       time: untraced native/C time when C tracing is off, otherwise self time.
    4. The resource sampler observed the lane not progressing, which is
       consistent with a wait but does not prove one.
    5. Otherwise: unknown.  No cause is invented.
    """
    if duration_ms <= 0:
        return ("UNKNOWN", "zero_length_interval")
    if thread_ms / duration_ms >= LANE_COVERAGE_THRESHOLD:
        return (
            "OTHER_THREAD_ACTIVE",
            f"another thread covered {thread_ms:.1f} of {duration_ms:.1f} ms "
            f"({thread_ms / duration_ms * 100:.0f}%)",
        )
    if cross_process_usable and process_ms is not None:
        if process_ms / duration_ms >= LANE_COVERAGE_THRESHOLD:
            return (
                "OTHER_PROCESS_ACTIVE",
                f"another process covered {process_ms:.1f} of {duration_ms:.1f} ms "
                f"({process_ms / duration_ms * 100:.0f}%) with proven clock alignment",
            )
    if enclosing:
        if not c_function_tracing:
            return (
                "UNTRACED_NATIVE_OR_C",
                "inside a traced Python frame while C/native call tracing is disabled",
            )
        return ("SELF_OR_NATIVE", "inside a traced Python frame with C tracing enabled")
    if str(cpu.get("status")) == "available" and not int(cpu.get("samples_with_cpu_progress") or 0):
        return (
            "ASYNC_WAIT_POSSIBLE",
            f"no CPU progress observed in {int(cpu.get('samples_in_window') or 0)} "
            "resource samples covering the interval",
        )
    return ("UNKNOWN", "no traced work and no resource evidence covering the interval")


# ---------------------------------------------------------------------------
# Section E: aggregation (function costs, offenders, trees)
# ---------------------------------------------------------------------------


def subtree_of(
    call: Mapping[str, Any],
    calls: Sequence[dict[str, Any]],
    children: Mapping[tuple[Any, Any], Sequence[dict[str, Any]]],
) -> list[dict[str, Any]]:
    """Return *call* plus every transitive descendant, deterministically."""
    key = (call.get("pid"), call.get("event_index"))
    collected: dict[tuple[Any, Any], dict[str, Any]] = {(key[0], key[1]): call}  # type: ignore[index]
    stack = [(key, call)]
    while stack:
        current_key, current = stack.pop()
        for child in children.get(current_key, ()):
            child_key = (child.get("pid"), child.get("event_index"))
            if child_key in collected:
                continue
            collected[child_key] = child
            stack.append((child_key, child))
    return sorted(collected.values(), key=_call_sort_key)


def aggregate_functions(
    calls: Sequence[Mapping[str, Any]],
    *,
    wall_ms: float | None,
) -> list[dict[str, Any]]:
    """Aggregate a call set per function, keeping every call individually.

    ``inclusive_ms`` sums the wall of every invocation, so a 0.2 ms helper called
    10,000 times shows up as 2 seconds instead of being hidden behind a mean.
    """
    buckets: dict[tuple[str, str], dict[str, Any]] = {}
    for call in calls:
        qualified = _qualified_name(call.get("name"))
        function = _basename(call.get("name"))
        key = (qualified, str(call.get("source_file") or ""))
        bucket = buckets.get(key)
        if bucket is None:
            bucket = {
                "qualified_function": qualified,
                "function": function,
                "source_file": str(call.get("source_file") or ""),
                "source_line": call.get("source_line"),
                "process_roles": set(),
                "call_count": 0,
                "inclusive_ms": 0.0,
                "exclusive_ms": 0.0,
                "blocking_wait_ms": 0.0,
                "self_after_blocking_ms": 0.0,
                "max_call_ms": 0.0,
                "complete_calls": 0,
                "incomplete_calls": 0,
            }
            buckets[key] = bucket
        bucket["call_count"] += 1
        bucket["process_roles"].add(str(call.get("process_role") or ""))
        if call.get("complete"):
            bucket["complete_calls"] += 1
        else:
            bucket["incomplete_calls"] += 1
        inclusive = _safe_float(call.get("wall_ms"))
        if inclusive is not None:
            bucket["inclusive_ms"] += inclusive
            bucket["max_call_ms"] = max(bucket["max_call_ms"], inclusive)
        exclusive = _safe_float(call.get("exclusive_self_ms"))
        if exclusive is not None:
            bucket["exclusive_ms"] += exclusive
        bucket["blocking_wait_ms"] += _safe_float(call.get("blocking_wait_ms")) or 0.0
        bucket["self_after_blocking_ms"] += (
            _safe_float(call.get("self_after_blocking_ms")) or 0.0
        )
    result = []
    for bucket in buckets.values():
        bucket["process_roles"] = sorted(bucket["process_roles"])
        bucket["inclusive_ms"] = round(bucket["inclusive_ms"], 3)
        bucket["exclusive_ms"] = round(bucket["exclusive_ms"], 3)
        bucket["blocking_wait_ms"] = round(bucket["blocking_wait_ms"], 3)
        bucket["self_after_blocking_ms"] = round(bucket["self_after_blocking_ms"], 3)
        bucket["max_call_ms"] = round(bucket["max_call_ms"], 3)
        bucket["pct_of_stage_wall"] = (
            round(bucket["inclusive_ms"] / wall_ms * 100.0, 3)
            if wall_ms else None
        )
        bucket["pct_of_stage_exclusive"] = (
            round(bucket["exclusive_ms"] / wall_ms * 100.0, 3)
            if wall_ms else None
        )
        result.append(bucket)
    result.sort(key=lambda b: (
        -float(b["inclusive_ms"]),
        str(b["qualified_function"]),
        str(b["source_file"]),
    ))
    return result


def top_calls(
    calls: Sequence[Mapping[str, Any]],
    *,
    key: str = "wall_ms",
    limit: int = TOP_N,
) -> list[Mapping[str, Any]]:
    """Return the *limit* costliest individual calls by *key*."""
    usable = [c for c in calls if _safe_float(c.get(key)) is not None]
    usable.sort(key=lambda c: (
        -float(c[key] or 0.0),
        _safe_int(c.get("event_index")) or 0,
        str(c.get("qualified_name") or c.get("name")),
    ))
    return usable[:limit]


def repeated_setup_functions(
    functions: Sequence[Mapping[str, Any]],
    *,
    min_calls: int = 8,
    limit: int = TOP_N,
) -> list[dict[str, Any]]:
    """Return functions whose many small calls add up to real time.

    This is the ``0.2 ms x 10,000 calls = 2 s`` detector.  It deliberately does
    not require the function to be slow on its own.
    """
    candidates = [
        dict(f) for f in functions
        if int(f.get("call_count") or 0) >= min_calls
        and _safe_float(f.get("inclusive_ms")) is not None
    ]
    candidates.sort(key=lambda f: (
        -float(f["inclusive_ms"]),
        str(f["qualified_function"]),
    ))
    trimmed = candidates[:limit]
    for entry in trimmed:
        count = max(1, int(entry.get("call_count") or 1))
        entry["mean_ms"] = round(float(entry["inclusive_ms"]) / count, 4)
    return trimmed


def build_call_tree(
    stage_call: Mapping[str, Any] | None,
    stage_calls: Sequence[Mapping[str, Any]],
    children: Mapping[tuple[Any, Any], Sequence[Mapping[str, Any]]],
    *,
    max_depth: int = 6,
    min_ms: float = 0.0,
    max_nodes: int = 400,
) -> list[str]:
    """Render a readable nested call tree for a stage.

    Folding is display-only: nodes below ``min_ms`` collapse into one
    ``... N more calls below threshold (X ms)`` line, and the traversal stops at
    ``max_nodes`` so a million-call stage cannot produce a million-line report.
    Nothing is removed from the CSV or the JSON summary.
    """
    if stage_call is None:
        return []
    lines: list[str] = []
    emitted = {"count": 0}

    def visit(call: Mapping[str, Any], depth: int, prefix: str) -> None:
        if emitted["count"] >= max_nodes:
            return
        span = _span(call)
        wall = _safe_float(call.get("wall_ms"))
        self_ms = _safe_float(call.get("exclusive_self_ms"))
        label = _qualified_name(call.get("name")) or "<unknown>"
        source = str(call.get("source_file") or "")
        line_no = call.get("source_line")
        location = f"  {source}:{line_no}" if source else ""
        header = (
            f"{label}  [{_fmt_ms(wall)} ms, self {_fmt_ms(self_ms)}]"
            f"{location}"
        )
        if wall is not None and wall < min_ms and depth > 0:
            return
        lines.append(f"{prefix}{header}")
        emitted["count"] += 1
        if depth >= max_depth:
            hidden = _count_subtree(call, stage_calls, children)
            if hidden:
                lines.append(f"{prefix}  ... {hidden} deeper calls omitted (depth cap)")
            return
        kids = [
            child for child in children.get(
                (call.get("pid"), call.get("event_index")), ()
            )
            if child in stage_calls
        ]
        for position, child in enumerate(kids):
            last = position == len(kids) - 1
            branch = "`-- " if last else "|-- "
            child_prefix = prefix + ("    " if last else "|   ")
            before = len(lines)
            visit(child, depth + 1, child_prefix + branch)
            if len(lines) == before and (_safe_float(child.get("wall_ms")) or 0.0) < min_ms:
                lines.append(
                    child_prefix + branch
                    + f"{_qualified_name(child.get('name'))}  "
                    + f"[{_fmt_ms(child.get('wall_ms'))} ms, below display threshold]"
                )

    visit(stage_call, 0, "")
    return lines


def _count_subtree(
    call: Mapping[str, Any],
    stage_calls: Sequence[Mapping[str, Any]],
    children: Mapping[tuple[Any, Any], Sequence[Mapping[str, Any]]],
) -> int:
    total = 0
    stack = [(call.get("pid"), call.get("event_index"))]
    seen = set(stack)
    while stack:
        key = stack.pop()
        for child in children.get(key, ()):  # type: ignore[arg-type]
            child_key = (child.get("pid"), child.get("event_index"))
            if child_key in seen:
                continue
            seen.add(child_key)
            total += 1
            stack.append(child_key)
    return total


def partition_stage_window(
    stage_call: Mapping[str, Any],
    stage_span: tuple[float, float],
    calls: Sequence[Mapping[str, Any]],
    pid: Any,
) -> dict[str, Any]:
    """Split every record in a stage window into enclosing / nested / concurrent.

    A stage's wall is measured on one thread, but Golden's work inside it is not
    confined to that thread: the overlap schedule runs a sibling stage body on a
    private executor thread, and a blocking stage (``source_open_read``) sits on
    one lane while the source pool does the work on another.  Attributing a stage
    by its own thread alone therefore drops real, captured work -- 37,499 of
    37,506 records in ``golden_clip_load``, and the whole 5258 ms of
    ``golden_clip_forward`` overlapping ``golden_unet_load``.

    Three disjoint groups, because they mean different things to a reader:

    ``enclosing``
        Frames that *contain* the whole stage window (the root). They measure the
        stage, they do not explain it, and are excluded from coverage.
    ``nested``
        Records on the stage's own thread, strictly inside the window. This is
        the stage's real body.
    ``concurrent``
        Records on other threads of the same process that overlap the window but
        do not contain it. This is work the stage waited for, or ran in parallel.

    Coverage is the union of ``nested`` and ``concurrent`` minus whatever
    ``enclosing`` already accounts for, so a stage can never be reported as
    explained by the root that measures it.
    """
    stage_pid = stage_call.get("pid")
    own_tid = stage_call.get("tid")
    start, end = stage_span
    nested: list[Mapping[str, Any]] = []
    concurrent: list[Mapping[str, Any]] = []
    enclosing: list[Mapping[str, Any]] = []
    for call in calls:
        if not call.get("span_ok"):
            continue
        if pid is not None and call.get("pid") != pid:
            continue
        span = _span(call)
        if span is None:
            continue
        c_start, c_end = span
        if c_start <= start + 1e-6 and c_end >= end - 1e-6:
            # Contains the stage window (or is it): measures, does not explain.
            if (c_start, c_end) != (start, end):
                enclosing.append(call)
            continue
        if c_end <= start + 1e-6 or c_start >= end - 1e-6:
            continue
        if call.get("tid") == own_tid:
            nested.append(call)
        else:
            concurrent.append(call)

    def union_ms(rows: Sequence[Mapping[str, Any]]) -> float:
        iv = [(_safe_float(r.get("start_us")), _safe_float(r.get("end_us"))) for r in rows]
        iv = [(a, b) for a, b in iv if a is not None and b is not None and b >= a]
        return round(_us_to_ms(_union_length(iv) or 0.0) or 0.0, 3)

    nested.sort(key=_call_sort_key)
    concurrent.sort(key=_call_sort_key)
    return {
        "nested": nested,
        "concurrent": concurrent,
        "enclosing": enclosing,
        "nested_union_ms": union_ms(nested),
        "concurrent_union_ms": union_ms(concurrent),
        "enclosing_count": len(enclosing),
        "own_tid": own_tid,
        "stage_pid": stage_pid,
    }


def blocking_wait_ms(
    call: Mapping[str, Any],
    calls: Sequence[Mapping[str, Any]],
) -> float:
    """Return how long *call*'s own lane was blocked on another lane's work.

    A frame that blocks on a pipe, a volume read or a sibling task has no
    same-thread children for the duration, so ``wall - child_union`` charges the
    entire wait to its own self time.  That reads as "this function burned 3.5
    seconds of CPU" when the truth is "this thread waited 3.5 seconds while
    another thread did the work".  The two need to be separable, because only the
    second is a real optimization target for the waiting frame.
    """
    span = _span(call)
    if span is None:
        return 0.0
    own = (call.get("pid"), call.get("tid"))
    iv: list[tuple[float, float]] = []
    for other in calls:
        if not other.get("span_ok"):
            continue
        if (other.get("pid"), other.get("tid")) == own:
            continue
        ospan = _span(other)
        if ospan is None:
            continue
        # Only work that overlaps and does not merely contain the wait.
        if ospan[1] <= span[0] + 1e-6 or ospan[0] >= span[1] - 1e-6:
            continue
        if ospan[0] <= span[0] + 1e-6 and ospan[1] >= span[1] - 1e-6:
            continue
        iv.append(ospan)
    return round(_us_to_ms(_union_length(iv) or 0.0) or 0.0, 3)


#: Spans longer than this are answered by bisect on their start and end rather
#: than by the sorted walk, whose prefix-maximum pruning any single long span
#: defeats. 1ms keeps the "short" side small enough for the pruning to bite
#: while leaving the bisect side sparse inside any one query window.
_LONG_SPAN_US = 1000.0


def _build_lane_interval_index(
    calls: Sequence[Mapping[str, Any]],
) -> dict[
    tuple[Any, Any],
    tuple[
        list[float], list[tuple[float, float]], list[float],
        list[float], list[tuple[float, float]],
        list[float], list[tuple[float, float]],
    ],
]:
    """Index every span once, per lane, for fast overlap queries.

    ``blocking_wait_ms`` used to rescan all calls for every call -- O(calls^2).
    Indexing alone was not enough: pruning the walk with a running maximum of the
    ends is defeated by any long span, because the root's own span covers the
    whole request and keeps that maximum above every window, so the walk still
    ran to index 0 on all 1.26M queries (~10 minutes).

    Each lane is therefore split by duration.  Short spans keep the sorted
    structure with the prefix-maximum pruning, which works because no short span
    reaches across the whole request.  Long spans are answered by identity:
    a span overlaps ``[a, b]`` without containing it exactly when its start lies
    in ``(a, b)`` or its end lies in ``(a, b)``, so both are a bisect away.
    """
    lanes: dict[tuple[Any, Any], list[tuple[float, float]]] = {}
    for c in calls:
        if not c.get("span_ok"):
            continue
        span = _span(c)
        if span is None:
            continue
        lanes.setdefault((c.get("pid"), c.get("tid")), []).append(span)
    index: dict[
        tuple[Any, Any],
        tuple[
            list[float], list[tuple[float, float]], list[float],
            list[float], list[tuple[float, float]],
            list[float], list[tuple[float, float]],
        ],
    ] = {}
    for key, spans in lanes.items():
        spans.sort()
        short = [s for s in spans if (s[1] - s[0]) <= _LONG_SPAN_US]
        long_spans = [s for s in spans if (s[1] - s[0]) > _LONG_SPAN_US]
        starts = [s[0] for s in short]
        prefix_max_end: list[float] = []
        running = float("-inf")
        for s in short:
            if s[1] > running:
                running = s[1]
            prefix_max_end.append(running)
        by_start = sorted(long_spans, key=lambda s: s[0])
        by_end = sorted(long_spans, key=lambda s: s[1])
        index[key] = (
            starts,
            short,
            prefix_max_end,
            [s[0] for s in by_start],
            by_start,
            [s[1] for s in by_end],
            by_end,
        )
    return index


def _blocking_wait_ms_indexed(
    call: Mapping[str, Any],
    index: Mapping[Any, Any],
) -> float:
    """Indexed equivalent of :func:`blocking_wait_ms`.

    Same overlap test and same "merely contains the wait" exclusion as the
    linear scan, so the unioned result is identical.
    """
    span = _span(call)
    if span is None:
        return 0.0
    start, end = span
    own = (call.get("pid"), call.get("tid"))
    iv: list[tuple[float, float]] = []
    for key, lane in index.items():
        if key == own:
            continue
        (
            starts, short, prefix_max_end,
            long_start_keys, long_by_start,
            long_end_keys, long_by_end,
        ) = lane
        hi = bisect_left(starts, end - 1e-6)
        j = hi - 1
        while j >= 0 and prefix_max_end[j] > start + 1e-6:
            o_start, o_end = short[j]
            if o_end > start + 1e-6 and o_start < end - 1e-6:
                if not (o_start <= start + 1e-6 and o_end >= end - 1e-6):
                    iv.append(short[j])
            j -= 1
        lo_i = bisect_right(long_start_keys, start + 1e-6)
        hi_i = bisect_left(long_start_keys, end - 1e-6)
        for o in long_by_start[lo_i:hi_i]:
            iv.append(o)
        lo_j = bisect_right(long_end_keys, start + 1e-6)
        hi_j = bisect_left(long_end_keys, end - 1e-6)
        for o in long_by_end[lo_j:hi_j]:
            iv.append(o)
    return round(_us_to_ms(_union_length(iv) or 0.0) or 0.0, 3)


def stage_diagnosis(
    *,
    stage: str,
    wall_ms: float,
    descendant_union_ms: float,
    functions: Sequence[Mapping[str, Any]],
    bubbles: Mapping[str, Any],
    repeated: Sequence[Mapping[str, Any]],
    clock_alignment: Mapping[str, Any],
) -> dict[str, Any]:
    """Return the mechanical "why is this stage slow" accounting.

    Every line is arithmetic over measured values.  No sentence attributes a
    cause that the evidence does not establish.
    """
    residual_ms = max(0.0, wall_ms - descendant_union_ms)
    # The stage's own span measures the stage; it never explains it. Excluding it
    # here stops a stage with no traced body from naming itself as the dominant
    # owner of its own wall.
    inner = [
        f for f in functions
        if _basename(f.get("qualified_function")) != stage
        and _safe_float(f.get("inclusive_ms"))
    ]
    dominant_wall = max(
        inner, key=lambda f: float(f["inclusive_ms"]), default=None,
    )
    dominant_self = max(
        inner, key=lambda f: float(f["exclusive_ms"]), default=None,
    )
    bubble_rows = bubbles.get("bubbles") or []
    largest_bubble = bubble_rows[0] if bubble_rows else None
    lines: list[str] = [
        f"{stage} = {wall_ms:.1f} ms",
        "",
        f"accounted by traced child union: {_fmt_pct(descendant_union_ms, wall_ms)}%",
        f"exclusive/untraced residual: {_fmt_pct(residual_ms, wall_ms)}% "
        f"({residual_ms:.1f} ms)",
        "",
        "dominant wall owner:",
        (
            f"    {dominant_wall['qualified_function']} = "
            f"{_fmt_pct(dominant_wall['inclusive_ms'], wall_ms)}% "
            f"({float(dominant_wall['inclusive_ms']):.1f} ms over "
            f"{int(dominant_wall['call_count'])} calls)"
            if dominant_wall else "    " + MEASUREMENT_UNAVAILABLE
        ),
        "",
        "dominant self-time owner:",
        (
            f"    {dominant_self['qualified_function']} = "
            f"{float(dominant_self['exclusive_ms']):.1f} ms"
            if dominant_self else "    " + MEASUREMENT_UNAVAILABLE
        ),
        "",
        "largest parent-lane bubble:",
        (
            f"    {float(largest_bubble['duration_ms']):.1f} ms "
            f"({largest_bubble['classification']})"
            if largest_bubble else "    " + MEASUREMENT_UNAVAILABLE
        ),
        "",
        "cross-process source activity during largest bubble:",
        (
            f"    {_fmt_ms(largest_bubble.get('other_process_traced_ms'))} ms"
            if largest_bubble else "    " + MEASUREMENT_UNAVAILABLE
        ),
        "",
        "repeated work:",
    ]
    if repeated:
        for entry in repeated[:5]:
            lines.append(
                f"    {entry['qualified_function']}: {int(entry['call_count'])} calls / "
                f"{float(entry['inclusive_ms']):.1f} ms cumulative "
                f"(mean {_fmt_ms(entry.get('mean_ms'), 3)} ms)"
            )
    else:
        lines.append("    " + MEASUREMENT_UNAVAILABLE)
    lines.extend([
        "",
        "evidence-backed conclusion:",
        (
            f"    python-visible child union accounts for "
            f"{_fmt_pct(descendant_union_ms, wall_ms)}% of the stage; "
            f"{residual_ms:.1f} ms is self time, untraced native/C time, or "
            f"unattributed."
        ),
        (
            f"    clock alignment is {clock_alignment.get('status')}; "
            + (
                "cross-process timings above are directly comparable."
                if str(clock_alignment.get("status")) == "PROVEN"
                else "cross-process overlap was NOT used to attribute any bubble."
            )
        ),
    ])
    return {
        "stage": stage,
        "wall_ms": round(wall_ms, 3),
        "descendant_union_ms": round(descendant_union_ms, 3),
        "residual_ms": round(residual_ms, 3),
        "residual_pct": round(residual_ms / wall_ms * 100.0, 3) if wall_ms else None,
        "dominant_wall_owner": dict(dominant_wall) if dominant_wall else None,
        "dominant_self_owner": dict(dominant_self) if dominant_self else None,
        "largest_bubble": dict(largest_bubble) if largest_bubble else None,
        "repeated": [dict(r) for r in repeated[:5]],
        "narrative": "\n".join(lines),
    }


# ---------------------------------------------------------------------------
# Section F: deterministic fixed-width ASCII rendering
# ---------------------------------------------------------------------------


def render_gantt(
    rows: Sequence[tuple[str, float | None, float | None]],
    *,
    window: tuple[float, float],
    width: int = GANTT_WIDTH,
    label_width: int = LABEL_WIDTH,
    header: str | None = None,
    merged: bool = True,
) -> list[str]:
    """Render *rows* as a fixed-width ASCII Gantt.

    Each row is ``(label, start_ms, end_ms)``.  Geometry depends only on the
    window and the row values, so the same trace always renders the same bytes.
    A merged cross-process chart is only produced when the caller proved the
    clocks comparable; otherwise lanes are rendered separately and the chart is
    explicitly per-process.
    """
    window_start, window_end = window
    span = max(1e-9, window_end - window_start)
    lines: list[str] = []
    if header:
        lines.append(header)
    if not merged:
        lines.append(
            "  (per-process timeline: cross-process clock alignment is UNPROVEN, "
            "so no merged ordering is claimed)"
        )
    ticks = _gantt_axis(window_start, window_end, width)
    lines.append(f"{'':<{label_width}} |{ticks}|")
    lines.append(f"{'-' * label_width}-+{'-' * width}+")
    for label, start, end in rows:
        name = _truncate_label(label, label_width)
        if start is None or end is None or end < start:
            lines.append(f"{name:<{label_width}} |{'':<{width}}|")
            continue
        left = int(round((float(start) - window_start) / span * width))
        right = int(round((float(end) - window_start) / span * width))
        left = max(0, min(width - 1, left))
        right = max(left + 1, min(width, right))
        bar = [" "] * width
        for index in range(left, right):
            bar[index] = "#"
        lines.append(f"{name:<{label_width}} |{''.join(bar)}|")
    return lines


def _gantt_axis(window_start: float, window_end: float, width: int) -> str:
    """Return a deterministic scale string of exactly *width* characters."""
    del window_start, window_end
    axis = ["-"] * width
    for fraction in (0.0, 0.25, 0.5, 0.75, 1.0):
        position = min(width - 1, int(round(fraction * (width - 1))))
        axis[position] = "+"
    axis[0] = "|"
    axis[-1] = "|"
    return "".join(axis)


def _truncate_label(label: Any, width: int) -> str:
    text = str(label or "")
    if len(text) <= width:
        return text
    if width <= 3:
        return text[:width]
    return text[: width - 3] + "..."


def _table(headers: Sequence[str], rows: Sequence[Sequence[Any]]) -> list[str]:
    """Render a deterministic fixed-width Markdown-friendly table."""
    cells = [[("" if c is None else str(c)) for c in row] for row in rows]
    widths = [len(h) for h in headers]
    for row in cells:
        for index, value in enumerate(row):
            if index < len(widths):
                widths[index] = max(widths[index], len(value))
    out = [
        "| " + " | ".join(
            _truncate_label(headers[i], widths[i]) for i in range(len(headers))
        ) + " |",
        "|" + "|".join("-" * (w + 2) for w in widths) + "|",
    ]
    for row in cells:
        out.append(
            "| " + " | ".join(
                _truncate_label(row[i] if i < len(row) else "", widths[i])
                for i in range(len(headers))
            ) + " |"
        )
    return out


def _section(title: str) -> list[str]:
    rule = "=" * max(8, len(title))
    return ["", rule, title, rule, ""]


def _code(lines: Sequence[str]) -> list[str]:
    return ["```text", *lines, "```"]


# ---------------------------------------------------------------------------
# Section G: the completeness contract (fail closed)
# ---------------------------------------------------------------------------


def evaluate_completeness(
    *,
    root_selection: Mapping[str, Any],
    root: Mapping[str, Any] | None,
    root_complete: bool,
    required: Sequence[str],
    observed_stages: Sequence[str],
    processes: Sequence[ProcessTrace],
    manifest: Mapping[str, Any],
    clock_alignment: Mapping[str, Any],
    thread_coverage: Mapping[str, Any],
    incomplete_calls: int,
    stack_inconsistencies: int,
    raw_trace_nonempty: bool,
    report_written: bool,
    stage_count: int,
) -> dict[str, Any]:
    """Return ``{complete, reasons, checks}`` -- every condition must hold.

    ``complete`` is the conjunction of every check below.  Each failing check
    contributes one human-readable reason, so a ``NO`` always says exactly which
    evidence is missing rather than degrading into a vague warning.
    """
    checks: list[dict[str, Any]] = []

    def check(name: str, ok: bool, detail: str) -> None:
        checks.append({"check": name, "ok": bool(ok), "detail": detail})

    check(
        "exactly_one_authoritative_golden_root",
        root is not None,
        str(root_selection.get("reason") or ""),
    )
    check(
        "root_begin_and_end_complete",
        bool(root_complete),
        f"root category={root.get('category') if root else 'n/a'}",
    )
    missing_stages = [s for s in required if s not in set(observed_stages)]
    check(
        "all_required_canonical_stages_present",
        not missing_stages,
        "missing: " + ", ".join(missing_stages) if missing_stages else "none missing",
    )
    check("raw_trace_nonempty", bool(raw_trace_nonempty), f"processes={len(processes)}")
    truncated = [f"{p.role}#{p.pid}" for p in processes if p.truncated]
    check("no_trace_truncation", not truncated, "truncated: " + ", ".join(truncated) if truncated else "none")
    check(
        "no_stack_depth_truncation",
        int(stack_inconsistencies) == 0,
        f"stack_inconsistencies={stack_inconsistencies}",
    )
    check(
        "no_root_corrupting_incomplete_calls",
        int(incomplete_calls) == 0,
        f"incomplete_calls={incomplete_calls}",
    )
    expected = manifest.get("expected_processes")
    traced = manifest.get("traced_processes")
    missing_processes = manifest.get("missing_processes") or []
    check(
        "expected_processes_accounted_for",
        expected is None or not missing_processes,
        f"expected={expected} traced={traced} missing={missing_processes}",
    )
    check(
        "all_process_local_traces_accounted_for",
        expected is None or (traced is not None and int(traced) >= int(expected)),
        f"traced={traced} expected={expected}",
    )
    check(
        "process_clocks_align_for_merged_gantt",
        str(clock_alignment.get("status")) == "PROVEN",
        str(clock_alignment.get("reason") or ""),
    )
    check(
        "thread_tracing_coverage_proven",
        str(thread_coverage.get("status")) == "COMPLETE",
        str(thread_coverage.get("reason") or ""),
    )
    check("every_stage_section_generated", stage_count > 0, f"stages={stage_count}")
    check("report_artifact_written", bool(report_written), "golden_exhaustive_profile.md")

    reasons = [f"{c['check']}: {c['detail']}" for c in checks if not c["ok"]]
    return {
        "complete": not reasons,
        "reasons": reasons,
        "checks": checks,
    }


def build_process_manifest(
    processes: Sequence[ProcessTrace],
    *,
    registry: Mapping[str, Any] | None,
    thread_names: Mapping[tuple[Any, Any], str],
) -> dict[str, Any]:
    """Return the expected/traced/missing process accounting.

    ``expected`` comes from what the run actually registered, never from a
    hardcoded worker count.  When ownership cannot be established the coverage
    is ``UNKNOWN``, which is deliberately distinct from ``COMPLETE``.
    """
    registry_rows = list(registry.get("processes") or []) if isinstance(registry, Mapping) else []
    observed = {
        f"{p.role}#{p.pid}": p
        for p in processes
        if p.error is None
    }
    expected_keys: list[str] = []
    for row in registry_rows:
        expected_keys.append(f"{row.get('role')}#{row.get('pid')}")
    if not expected_keys:
        # No registry: the observed set is all the evidence there is, so
        # coverage cannot be proven -- only reported as unknown.
        expected_keys = list(observed)
        ownership_established = False
    else:
        ownership_established = True

    traced_keys = [
        key for key, process in sorted(observed.items())
        if (process.entry_count or 0) > 0 and not process.truncated
    ]
    missing = [key for key in expected_keys if key not in traced_keys]

    roles: list[dict[str, Any]] = []
    seen: set[str] = set()
    for key in expected_keys:
        if key in seen:
            continue
        seen.add(key)
        role, _, pid_text = key.partition("#")
        process = observed.get(key)
        roles.append({
            "role": role,
            "pid": _safe_int(pid_text),
            "expected": True,
            "traced": key in traced_keys,
            "trace_source": process.source if process else None,
            "trace_entry_count": process.entry_count if process else None,
            "trace_entry_capacity": process.entry_capacity if process else None,
            "truncated": bool(process.truncated) if process else None,
            "base_time_nanoseconds": process.base_time_ns if process else None,
            "viztracer_version": process.viztracer_version if process else "unknown",
            "trace_id": process.trace_id if process else "",
            "request_id": process.request_id if process else "",
            "include_paths": process.include_paths if process else [],
            "threads": sorted({
                name for (pid, _tid), name in thread_names.items()
                if str(pid) == pid_text and name
            }),
            "error": process.error if process else "missing_child_trace",
        })
    for key, process in sorted(observed.items()):
        if key in seen:
            continue
        seen.add(key)
        roles.append({
            "role": process.role,
            "pid": process.pid,
            "expected": False,
            "traced": key in traced_keys,
            "trace_source": process.source,
            "trace_entry_count": process.entry_count,
            "trace_entry_capacity": process.entry_capacity,
            "truncated": bool(process.truncated),
            "base_time_nanoseconds": process.base_time_ns,
            "viztracer_version": process.viztracer_version,
            "trace_id": process.trace_id,
            "request_id": process.request_id,
            "include_paths": process.include_paths,
            "threads": sorted({
                name for (pid, _tid), name in thread_names.items()
                if pid == process.pid and name
            }),
            "error": process.error,
        })

    coverage = "COMPLETE"
    if not ownership_established:
        coverage = "UNKNOWN"
    elif missing:
        coverage = "PARTIAL"
    if len(processes) > 1 and not registry_rows:
        coverage = "UNKNOWN"
    return {
        "schema_version": EXHAUSTIVE_SCHEMA,
        "expected_processes": len(expected_keys) if registry_rows else None,
        "traced_processes": len(traced_keys),
        "missing_processes": missing,
        "process_coverage": coverage,
        "ownership_established": ownership_established,
        "processes": sorted(roles, key=lambda r: (str(r["role"]), _safe_int(r["pid"]) or 0)),
        "observed_trace_files": sorted(p.source for p in processes),
    }


def assess_thread_coverage(
    processes: Sequence[ProcessTrace],
    lanes: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Report what thread coverage the artifacts actually demonstrate.

    Coverage is *proven* by positive evidence that more than the activating
    thread produced traced calls: that can only happen if threads created after
    activation were handed the profile hook.  A known thread with no traced call
    is reported as such, but it is not by itself a coverage failure -- an idle
    sampler thread and a thread blocked in native code look identical from the
    outside, so claiming either would be a guess.
    """
    traced_tids = {
        (lane.get("pid"), lane.get("tid")) for lane in lanes if lane.get("call_count")
    }
    named_tids = set()
    for process in processes:
        named_tids |= set(process.thread_names)
    untraced = sorted(f"{pid}:{tid}" for pid, tid in (named_tids - traced_tids))
    total_threads = len(named_tids)
    traced_lanes = len(traced_tids)
    if traced_lanes == 0:
        return {
            "status": "UNKNOWN",
            "reason": "no lane produced a traced Python call, so thread coverage "
                      "cannot be demonstrated",
            "threads_total": total_threads,
            "threads_with_traced_calls": 0,
            "lanes_with_traced_calls": 0,
            "threads_without_traced_calls": untraced,
        }
    if total_threads <= 1:
        # The artifact declares a single execution lane.  There is provably no
        # second thread that could have been missed, so this is complete rather
        # than a permanent PARTIAL for genuinely single-threaded work.
        return {
            "status": "COMPLETE",
            "reason": "the trace declares a single execution lane; there is no "
                      "second thread that could have gone untraced",
            "threads_total": total_threads,
            "threads_with_traced_calls": traced_lanes,
            "lanes_with_traced_calls": traced_lanes,
            "threads_without_traced_calls": untraced,
        }
    if traced_lanes >= 2:
        return {
            "status": "COMPLETE",
            "reason": (
                f"{traced_lanes} execution lanes produced traced Python calls, "
                "which proves threads created after activation were captured"
            ),
            "threads_total": total_threads,
            "threads_with_traced_calls": len(traced_tids & named_tids) or traced_lanes,
            "lanes_with_traced_calls": traced_lanes,
            "threads_without_traced_calls": untraced,
        }
    return {
        "status": "PARTIAL",
        "reason": (
            "only the activating lane produced traced Python calls; a trace of a "
            "single-threaded stage cannot demonstrate post-activation thread "
            "coverage either way"
        ),
        "threads_total": total_threads,
        "threads_with_traced_calls": len(traced_tids & named_tids) or traced_lanes,
        "lanes_with_traced_calls": traced_lanes,
        "threads_without_traced_calls": untraced,
    }


# ---------------------------------------------------------------------------
# Section H: top-level analysis
# ---------------------------------------------------------------------------


def analyze(
    session_dir: Path,
    *,
    parent_calls: Sequence[Mapping[str, Any]] | None = None,
    trace_config: Mapping[str, Any] | None = None,
    semantic_ops: Sequence[Mapping[str, Any]] = (),
    cpu_evidence: Mapping[str, Any] | None = None,
    stack_inconsistencies: int = 0,
    torch_enabled: bool = False,
    c_function_tracing: bool = False,
    env: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Build the exhaustive Golden profile for one session directory.

    This is a pure transform: it reads artifacts the full-trace session already
    produced and returns the complete profile structure.  Writing the artifacts
    is :func:`write_artifacts`, so the analysis stays testable without touching
    the filesystem beyond reads.
    """
    _t0 = time.perf_counter()

    def _lap(label: str) -> None:
        print(
            "    [gep.analyze] %s elapsed_s=%.1f"
            % (label, time.perf_counter() - _t0),
            flush=True,
        )

    session_dir = Path(session_dir)
    _lap("ENTER session=%s" % (session_dir,))
    config = dict(trace_config or {})
    processes = discover_process_traces(session_dir, trace_config=config)
    _lap("discover_process_traces processes=%d" % len(processes))
    clock_alignment = calibrate_clocks(processes)

    registry: dict[str, Any] = {}
    registry_path = session_dir / "raw" / "golden_process_registry.json"
    loaded = _load_json_maybe_gzip(registry_path)
    if isinstance(loaded, dict):
        registry = loaded

    thread_names: dict[tuple[Any, Any], str] = {}
    for process in processes:
        thread_names.update(process.thread_names)

    _lap("parent_calls=%s" % (
        len(parent_calls) if parent_calls is not None else "none",
    ))
    calls = build_exhaustive_calls(
        processes,
        parent_calls=list(parent_calls) if parent_calls is not None else None,
    )
    _lap("build_exhaustive_calls calls=%d" % len(calls))
    children = _children_map(calls)
    _lap("_children_map")
    annotate_exclusive_time(calls, children)
    _lap("annotate_exclusive_time")

    root_selection = select_authoritative_root(calls)
    _lap("select_authoritative_root")
    root = root_selection.get("root")
    if root is not None:
        # The process that actually owns the authoritative Golden root is the
        # parent.  This is derived from evidence in the trace rather than from a
        # filename or a hand-written sidecar.
        for process in processes:
            if process.pid == root.get("pid") and process.role != "parent":
                process.role = "parent"
        processes.sort(key=lambda p: (0 if p.role == "parent" else 1, p.role, p.pid or 0))
        for call in calls:
            if call.get("pid") == root.get("pid"):
                call["process_role"] = "parent"
    manifest = build_process_manifest(
        processes, registry=registry, thread_names=thread_names,
    )
    lanes = build_lanes(calls, thread_names)
    _lap("build_lanes")
    thread_coverage = assess_thread_coverage(processes, lanes)
    _lap("assess_thread_coverage")

    threshold = visual_threshold_ms(env)
    profile: dict[str, Any] = {
        "schema_version": EXHAUSTIVE_SCHEMA,
        "session_dir": str(session_dir),
        "trace_id": str(config.get("trace_id") or ""),
        "request_id": str(config.get("request_id") or ""),
        "visual_threshold_ms": threshold,
        "clock_alignment": clock_alignment,
        "process_manifest": manifest,
        "thread_coverage": thread_coverage,
        "torch_enabled": bool(torch_enabled),
        "c_function_tracing": bool(c_function_tracing),
        "stack_inconsistencies": int(stack_inconsistencies),
        "root_selection": {
            "kind": root_selection.get("kind"),
            "reason": root_selection.get("reason"),
        },
        "root": None,
        "stages": [],
        "lanes": lanes,
        "calls": calls,
        "children": children,
        "complete": False,
        "reasons": [],
        "rendered": False,
    }

    if root is None:
        profile["incomplete_calls"] = sum(1 for c in calls if not c.get("complete", True))
        profile["raw_trace_nonempty"] = any((p.entry_count or 0) > 0 for p in processes)
        profile["processes"] = [p.to_dict() for p in processes]
        profile["contract"] = evaluate_completeness(
            root_selection=root_selection,
            root=None,
            root_complete=False,
            required=[],
            observed_stages=[],
            processes=processes,
            manifest=manifest,
            clock_alignment=clock_alignment,
            thread_coverage=thread_coverage,
            incomplete_calls=profile["incomplete_calls"],
            stack_inconsistencies=stack_inconsistencies,
            raw_trace_nonempty=profile["raw_trace_nonempty"],
            report_written=False,
            stage_count=0,
        )
        profile["complete"] = False
        profile["reasons"] = list(profile["contract"]["reasons"])
        return profile

    root_span = _span(root)
    if root_span is None:
        # A root without both ends cannot bound anything.  Fail closed with the
        # exact reason rather than rendering an empty chart.
        incomplete = sum(1 for c in calls if not c.get("complete", True))
        profile["root"] = {
            "name": _basename(root.get("name")),
            "qualified_name": _qualified_name(root.get("name")),
            "category": root.get("category"),
            "process_role": root.get("process_role"),
            "pid": root.get("pid"),
            "tid": root.get("tid"),
            "task_id": str(root.get("task_id") or ""),
            "source_file": root.get("source_file"),
            "source_line": root.get("source_line"),
            "span": None,
            "wall_ms": None,
            "complete": False,
            "direct_child_count": 0,
            "direct_child_union_ms": 0.0,
            "call_count": 0,
        }
        profile["incomplete_calls"] = incomplete
        profile["raw_trace_nonempty"] = any((p.entry_count or 0) > 0 for p in processes)
        profile["processes"] = [p.to_dict() for p in processes]
        profile["contract"] = evaluate_completeness(
            root_selection=root_selection,
            root=root,
            root_complete=False,
            required=[],
            observed_stages=[],
            processes=processes,
            manifest=manifest,
            clock_alignment=clock_alignment,
            thread_coverage=thread_coverage,
            incomplete_calls=incomplete,
            stack_inconsistencies=stack_inconsistencies,
            raw_trace_nonempty=profile["raw_trace_nonempty"],
            report_written=False,
            stage_count=0,
        )
        profile["complete"] = False
        profile["reasons"] = ["root_begin_and_end_complete: " + str(
            root_selection.get("reason") or "root span incomplete",
        )]
        return profile

    descendants = resolve_descendants(root, calls, children)
    _lap("resolve_descendants descendants=%d" % len(descendants))
    observed_stages = sorted({
        _basename(c.get("name")) for c in descendants
        if _basename(c.get("name")) in CANONICAL_STAGE_ORDER
    })
    _lap("observed_stages=%s" % (",".join(observed_stages) or "none"))
    required = required_stages(config)

    # Index calls by (pid, tid) once.  The per-stage ownership scan below walked
    # every call for every stage -- O(stages x calls), with a span computation per
    # candidate, which is ~15M iterations on a 1.25M-event request and dominated
    # the entire analysis.  Bucketing by the very same (pid, tid) key that scan
    # already tested makes it O(calls + stages) with identical results.
    calls_by_ctx: dict[tuple[Any, Any], list[Mapping[str, Any]]] = {}
    for _call in calls:
        calls_by_ctx.setdefault(
            (_call.get("pid"), _call.get("tid")), []
        ).append(_call)

    stage_records: list[dict[str, Any]] = []
    _analyze_stage_t0 = time.perf_counter()
    for stage in CANONICAL_STAGE_ORDER:
        if stage not in observed_stages:
            continue
        # Heartbeat per canonical stage.  This loop is where the analysis spends
        # its time, and it used to emit nothing at all between "normalized
        # calls" and "analyzed", so a multi-minute stall looked identical to a
        # hang.  The delta between consecutive lines is the previous stage's cost.
        print(
            "    [gep.analyze] stage=%s elapsed_s=%.1f"
            % (stage, time.perf_counter() - _analyze_stage_t0),
            flush=True,
        )
        if stage not in observed_stages:
            continue
        resolved = resolve_stage(stage, descendants, root)
        if resolved is None:
            continue
        stage_call = resolved["call"]
        stage_span = _span(stage_call)
        if stage_span is None:
            stage_records.append({
                "stage": stage,
                "call": stage_call,
                "wall_ms": None,
                "complete": False,
                "incomplete_reason": "stage span incomplete",
                "candidates_seen": resolved["candidates_seen"],
            })
            continue
        subtree = subtree_of(stage_call, calls, children)
        # Containment matters: an unparented sibling overlapping the stage is
        # real work inside the stage and must not become a bubble. Matched on
        # the stage's own context rather than the root's, because an overlap
        # stage body runs on a different thread than the root.
        stage_ctx = (stage_call.get("pid"), stage_call.get("tid"))
        owner_calls: list[Mapping[str, Any]] = []
        for candidate in calls_by_ctx.get(stage_ctx, ()):
            if not candidate.get("span_ok"):
                continue
            span = _span(candidate)
            if span is None:
                continue
            if span[0] >= stage_span[0] - 1e-6 and span[1] <= stage_span[1] + 1e-6:
                owner_calls.append(candidate)
        enclosing = [c for c in owner_calls if c is not stage_call]
        bubbles = analyze_bubbles(
            window=stage_span,
            owner=root,
            subject=stage_call,
            owner_calls=owner_calls,
            lanes=lanes,
            semantic_ops=semantic_ops,
            clock_alignment=clock_alignment,
            cpu_evidence=cpu_evidence or {},
            c_function_tracing=c_function_tracing,
            enclosing_frames=enclosing,
        )
        wall_ms = _us_to_ms(stage_span[1] - stage_span[0]) or 0.0
        # Coverage is measured from the frames *inside* the stage. Including the
        # stage's own record would make the union equal the stage wall and
        # report 100% accounted with zero residual for a stage that contains no
        # traced work at all -- which is exactly the case a reader needs to see.
        covered_ms = _us_to_ms(_union_length([
            (float(c["span_start_us"]), float(c["span_end_us"]))
            for c in enclosing
        ])) or 0.0
        descendant_union_ms = min(covered_ms, wall_ms)
        functions = aggregate_functions(subtree, wall_ms=wall_ms)
        repeated = repeated_setup_functions(functions)
        direct_children = children.get(
            (stage_call.get("pid"), stage_call.get("event_index")), ()
        )
        window = partition_stage_window(
            stage_call, stage_span, calls, stage_call.get("pid"),
        )
        nested = window["nested"]
        concurrent = window["concurrent"]
        # The stage's own body plus everything that ran alongside it on another
        # lane. Enclosing frames are excluded: the root measures this stage, it
        # does not explain it.
        all_content = list(subtree) + [
            c for c in concurrent if not any(c is n for n in subtree)
        ]
        content_functions = aggregate_functions(all_content, wall_ms=wall_ms)
        # Coverage counts frames strictly INSIDE the stage window. The stage's
        # own record spans the window by construction, so including it would
        # report 100% attributed for every stage and hide exactly the residual a
        # reader needs -- the same trap as counting the root as its own child.
        inner_ids = {id(c) for c in nested} | {id(c) for c in concurrent}
        content_union = _us_to_ms(_union_length([
            (float(c["span_start_us"]), float(c["span_end_us"]))
            for c in all_content
            if c.get("span_ok") and id(c) in inner_ids
        ])) or 0.0
        stage_records.append({
            "stage": stage,
            "call": stage_call,
            "start_offset_ms": round(
                _us_to_ms(stage_span[0] - root_span[0]) or 0.0, 3,
            ) if root_span else None,
            "wall_ms": round(wall_ms, 3),
            "span": stage_span,
            "complete": bool(stage_call.get("complete")) and stage_span is not None,
            "candidates_seen": resolved["candidates_seen"],
            "candidate_names": resolved["candidate_names"],
            "visual_threshold_ms": threshold,
            "owner_calls": owner_calls,
            "subtree": subtree,
            "direct_children": list(direct_children),
            "functions": functions,
            "nested_calls": nested,
            "concurrent_calls": concurrent,
            "enclosing_count": window["enclosing_count"],
            "nested_union_ms": window["nested_union_ms"],
            "concurrent_union_ms": window["concurrent_union_ms"],
            "content_union_ms": round(min(content_union, wall_ms), 3),
            "content_functions": content_functions,
            "repeated": repeated,
            "bubbles": bubbles,
            "descendant_union_ms": round(descendant_union_ms, 3),
            "call_tree": build_call_tree(
                stage_call, subtree, children, min_ms=0.0,
            ),
            "diagnosis": stage_diagnosis(
                stage=stage,
                wall_ms=wall_ms,
                descendant_union_ms=descendant_union_ms,
                functions=functions,
                bubbles=bubbles,
                repeated=repeated,
                clock_alignment=clock_alignment,
            ),
        })

    root_wall_ms = (
        _us_to_ms(root_span[1] - root_span[0]) if root_span else None
    )
    _lap("post_loop_enter")
    root_subtree = resolve_descendants(root, calls, children)
    _lap("resolve_descendants(root) n=%d" % len(root_subtree))
    root_children = children.get((root.get("pid"), root.get("event_index")), ())
    root_functions = aggregate_functions(root_subtree, wall_ms=root_wall_ms)
    _lap("aggregate_functions")

    # Request-level bubbles use the same definition as the per-stage ones, over
    # the root's own wall, so Section 5 is comparable with Section 4.
    root_owner_calls = [
        c for c in root_subtree
        if _same_context(c, root) and c.get("span_ok")
    ]
    request_bubbles = analyze_bubbles(
        window=root_span,
        owner=root,
        subject=root,
        owner_calls=root_owner_calls,
        lanes=lanes,
        semantic_ops=semantic_ops,
        clock_alignment=clock_alignment,
        cpu_evidence=cpu_evidence or {},
        c_function_tracing=c_function_tracing,
        enclosing_frames=[c for c in root_owner_calls if c is not root],
    )

    # Split every call's self time into real self time and time spent blocked on
    # another lane. A frame that waits on a pipe, a volume read or a sibling
    # task has no same-thread children for the duration, so plain
    # `wall - child_union` charges the whole wait to its own self time and reads
    # as CPU burn. Recorded per call so every table can show both.
    _lap("analyze_bubbles(root)")
    # Split every call's self time into real self time and time spent blocked on
    # another lane. A frame that waits on a pipe, a volume read or a sibling
    # task has no same-thread children for the duration, so plain
    # `wall - child_union` charges the whole wait to its own self time and reads
    # as CPU burn. Recorded per call so every table can show both.
    #
    # blocking_wait_ms() scans every call looking for overlapping intervals on
    # other lanes, so this loop is O(calls^2) -- ~1.6e12 iterations on a 1.26M
    # event request. The per-lane index answers the same question without it.
    _lane_interval_index = _build_lane_interval_index(calls)
    for call in calls:
        call["blocking_wait_ms"] = _blocking_wait_ms_indexed(
            call, _lane_interval_index,
        )
        self_ms = _safe_float(call.get("exclusive_self_ms")) or 0.0
        call["self_after_blocking_ms"] = round(
            max(0.0, self_ms - float(call["blocking_wait_ms"])), 3,
        )
    _lap("blocking_wait n=%d" % len(calls))

    profile.update({
        "root": {
            "name": _basename(root.get("name")),
            "qualified_name": _qualified_name(root.get("name")),
            "category": root.get("category"),
            "process_role": root.get("process_role"),
            "pid": root.get("pid"),
            "tid": root.get("tid"),
            "task_id": str(root.get("task_id") or ""),
            "source_file": root.get("source_file"),
            "source_line": root.get("source_line"),
            "span": root_span,
            "wall_ms": root_wall_ms,
            "complete": bool(root.get("complete")) and root_span is not None,
            "direct_child_count": len(root_children),
            "direct_child_union_ms": round(
                _us_to_ms(_union_length([
                    (float(c["span_start_us"]), float(c["span_end_us"]))
                    for c in root_children if c.get("span_ok")
                ])) or 0.0, 3,
            ),
            "call_count": len(root_subtree),
        },
        "stages": stage_records,
        "required_stages": required,
        "observed_stages": observed_stages,
        "root_functions": root_functions,
        "root_subtree": root_subtree,
        "root_call": root,
        "request_bubbles": request_bubbles,
        "incomplete_calls": sum(1 for c in calls if not c.get("complete", True)),
        "raw_trace_nonempty": any((p.entry_count or 0) > 0 for p in processes),
        "processes": [p.to_dict() for p in processes],
        "top_calls": top_calls(root_subtree, key="wall_ms"),
        "top_by_inclusive": root_functions[:TOP_N],
        "top_by_exclusive": sorted(
            root_functions, key=lambda f: (-float(f["exclusive_ms"]), str(f["qualified_function"]))
        )[:TOP_N],
        "top_by_count": sorted(
            root_functions, key=lambda f: (-int(f["call_count"]), str(f["qualified_function"]))
        )[:TOP_N],
        "repeated_setup": repeated_setup_functions(root_functions),
        # Coverage needs absolute timestamps, not durations: the union of
        # captured intervals only means something relative to the root's own
        # start, and a trace can carry durations with a separate origin.
        "root_spans_us": [
            [float(c["span_start_us"]), float(c["span_end_us"])]
            for c in root_subtree
            if c.get("span_ok") and c.get("span_start_us") is not None
            and c.get("span_end_us") is not None
        ],
    })

    # Must run after the root dict exists and before rendering, because the
    # split is derived from the root wall and the captured intervals.
    profile["coverage_split"] = _coverage_split(profile)

    incomplete_calls = profile["incomplete_calls"]
    profile["contract"] = evaluate_completeness(
        root_selection=root_selection,
        root=root,
        root_complete=bool(root.get("complete")) and root_span is not None,
        required=required,
        observed_stages=observed_stages,
        processes=processes,
        manifest=manifest,
        clock_alignment=clock_alignment,
        thread_coverage=thread_coverage,
        incomplete_calls=incomplete_calls,
        stack_inconsistencies=stack_inconsistencies,
        raw_trace_nonempty=profile["raw_trace_nonempty"],
        report_written=False,
        stage_count=len(stage_records),
    )
    profile["complete"] = bool(profile["contract"]["complete"])
    profile["reasons"] = list(profile["contract"]["reasons"])
    return profile


# ---------------------------------------------------------------------------
# Section I: the human-first Markdown report
# ---------------------------------------------------------------------------


def _health_lines(profile: Mapping[str, Any]) -> list[str]:
    """Section 1 -- can this report be trusted at all?"""
    contract = profile.get("contract") or {}
    root = profile.get("root") or {}
    manifest = profile.get("process_manifest") or {}
    clock = profile.get("clock_alignment") or {}
    threads = profile.get("thread_coverage") or {}
    processes = profile.get("processes") or []
    entry_counts = [int(p.get("entry_count") or 0) for p in processes]
    capacities = [p.get("entry_capacity") for p in processes]
    known_capacity = [int(c) for c in capacities if c is not None]
    truncated = any(bool(p.get("truncated")) for p in processes)
    expected = manifest.get("expected_processes")
    lines = [
        f"GOLDEN_EXHAUSTIVE_PROFILE_COMPLETE={'YES' if profile.get('complete') else 'NO'}",
        f"ROOT_COMPLETE={'YES' if root.get('complete') else 'NO'}",
        f"TRACE_TRUNCATED={'YES' if truncated else 'NO'}",
        f"ROOT={root.get('name') or MEASUREMENT_UNAVAILABLE}",
        f"ROOT_WALL_MS={_fmt_ms(root.get('wall_ms'))}",
        "",
        f"PROCESS_COVERAGE={manifest.get('process_coverage') or 'UNKNOWN'}",
        f"EXPECTED_PROCESSES={expected if expected is not None else 'unknown'}",
        f"TRACED_PROCESSES={manifest.get('traced_processes')}",
        f"MISSING_PROCESSES={','.join(manifest.get('missing_processes') or []) or 'none'}",
        "",
        f"THREAD_COVERAGE={threads.get('status') or 'UNKNOWN'}",
        "",
        f"CLOCK_ALIGNMENT={clock.get('status') or 'UNKNOWN'}",
        f"INCOMPLETE_CALLS={profile.get('incomplete_calls', 0)}",
        f"STACK_INCONSISTENCIES={profile.get('stack_inconsistencies', 0)}",
        f"TRACE_ENTRY_COUNT={sum(entry_counts)}",
        f"TRACE_ENTRY_CAPACITY={sum(known_capacity) if known_capacity else 'unknown'}",
        "",
        "PYTHON_FUNCTION_PROFILING="
        + ("COMPLETE" if root.get("complete") else "PARTIAL"),
        f"C_FUNCTION_TRACING={'ENABLED' if profile.get('c_function_tracing') else 'DISABLED'}",
        f"TORCH_PROFILER={'ENABLED' if profile.get('torch_enabled') else 'DISABLED'}",
    ]
    if not profile.get("complete"):
        lines.extend(["", "INCOMPLETE BECAUSE:"])
        lines.extend(f"  - {reason}" for reason in (profile.get("reasons") or []))
    return lines


def _coverage_split(profile: Mapping[str, Any]) -> dict[str, Any]:
    """Split root wall into time a traced Python frame encloses, and the rest.

    VizTracer records Python function calls.  Time inside a CUDA kernel or any
    other C call is invisible to it unless C function tracing is on, so the
    root wall is *not* the sum of captured intervals.

    The attributed figure is the **union** of captured intervals rather than
    their sum, because nested frames double-count: summing would report more
    than the root wall and imply full coverage.  The union is bounded by the
    root wall, and what it does not cover is a CUDA kernel or C call dispatched
    from inside a traced frame -- for example an UNet forward whose Python
    wrapper is captured for 200 ms while the GPU works for 5 s.

    This states both numbers and names the reason for the remainder.  It makes
    no claim about where the unattributed time went beyond "no Python frame
    spans it".
    """
    root = profile.get("root") or {}
    wall = float(root.get("wall_ms") or 0.0)
    spans: list[tuple[float, float]] = [
        (float(s[0]), float(s[1]))
        for s in (profile.get("root_spans_us") or [])
        if len(s) == 2
    ]
    spans = [(a, b) for a, b in spans if b >= a]

    # The root record spans the whole root interval by construction, so leaving
    # it in the union would make coverage trivially 100% and hide the very gap
    # this reports.  Measure coverage from the frames *inside* the root.
    root_span = root.get("span")
    inner = (
        [(a, b) for a, b in spans if (a, b) != (float(root_span[0]), float(root_span[1]))]
        if root_span else list(spans)
    )
    union_us = _union_length(inner) if inner else 0.0
    attributed = float(union_us or 0.0) / 1000.0
    # Never claim more coverage than the root itself measured.
    if wall > 0.0:
        attributed = float(min(attributed, wall))
    unattributed = float(max(0.0, wall - attributed))
    reasons: list[str] = []
    if not profile.get("c_function_tracing"):
        reasons.append("C_FUNCTION_TRACING=DISABLED")
    if not profile.get("torch_enabled"):
        reasons.append("TORCH_PROFILER=DISABLED")
    # A trailing run with no Python frame at all is a different fact from time
    # inside a captured frame, and the distinction decides who should look next.
    trailing_ms = 0.0
    if inner and root_span:
        trailing_ms = float(max(0.0, float(root_span[1]) - max(b for _a, b in inner))) / 1000.0
    return {
        "root_wall_ms": wall,
        "python_attributed_ms": attributed,
        "unattributed_ms": unattributed,
        "python_attributed_pct": (100.0 * attributed / wall) if wall > 0 else None,
        "unattributed_basis": reasons,
        "trailing_unframed_ms": trailing_ms,
    }


def _coverage_lines(profile: Mapping[str, Any]) -> list[str]:
    """Human-readable form of :func:`_coverage_split`."""
    split = profile.get("coverage_split") or {}
    wall = float(split.get("root_wall_ms") or 0.0)
    attributed = float(split.get("python_attributed_ms") or 0.0)
    unattributed = float(split.get("unattributed_ms") or 0.0)
    pct = split.get("python_attributed_pct")
    basis = list(split.get("unattributed_basis") or [])
    lines = [
        f"  total Golden wall          {wall:9.1f} ms",
        f"  inside a traced Py call    {attributed:9.1f} ms"
        + (f"  ({float(pct):.1f}%)" if pct is not None else ""),
        f"  NOT Python-attributed      {unattributed:9.1f} ms",
    ]
    if unattributed > 0:
        why = ", ".join(basis) if basis else "no tracing gap recorded"
        lines.append(f"  unattributed because      {why}")
        trailing = float(split.get("trailing_unframed_ms") or 0.0)
        if trailing > 0:
            # No Python frame spans this at all, so it is not merely a coarse
            # C-level measurement: nothing at all was recorded here.
            lines.append(
                f"  of which unframed tail    {trailing:9.1f} ms"
                "  (no Python frame spans it)"
            )
        lines.append(
            "  -> that time runs in CUDA/C frames this tracer cannot see."
            if "C_FUNCTION_TRACING=DISABLED" in basis
            else "  -> unattributed time is not claimed as Python overhead."
        )
    return lines


def _summary_lines(profile: Mapping[str, Any]) -> list[str]:
    """Section 2 -- the thirty-second answer."""
    root = profile.get("root") or {}
    lines: list[str] = [
        f"Total Golden wall: {_fmt_ms(root.get('wall_ms'))} ms",
        f"Authoritative root: {root.get('qualified_name') or MEASUREMENT_UNAVAILABLE} "
        f"({root.get('category')}, {root.get('process_role')})",
        f"Captured Python calls under the root: {root.get('call_count')}",
        "",
        "Where the wall actually went:",
    ]
    lines.extend(_coverage_lines(profile))
    lines.extend(["", "Canonical stage walls:"])
    stages = [s for s in (profile.get("stages") or []) if s.get("wall_ms") is not None]
    if stages:
        width = max(len(str(s["stage"])) for s in stages)
        for stage in sorted(stages, key=lambda s: -float(s["wall_ms"] or 0.0)):
            lines.append(
                f"  {str(stage['stage']):<{width}}  {_fmt_ms(stage['wall_ms']):>10} ms"
            )
    else:
        lines.append("  " + MEASUREMENT_UNAVAILABLE)

    lines.extend(["", "Largest exclusive/self-time functions:"])
    for entry in (profile.get("top_by_exclusive") or [])[:10]:
        if float(entry["exclusive_ms"]) <= 0:
            continue
        lines.append(
            f"  {entry['qualified_function']:<44} {float(entry['exclusive_ms']):9.1f} ms"
            f"  over {int(entry['call_count'])} calls"
        )

    lines.extend(["", "Largest accumulated function costs:"])
    for entry in (profile.get("top_by_inclusive") or [])[:10]:
        lines.append(
            f"  {entry['qualified_function']:<44} {float(entry['inclusive_ms']):9.1f} ms"
            f"  over {int(entry['call_count'])} calls"
        )

    lines.extend(["", "Highest call-count functions:"])
    for entry in (profile.get("top_by_count") or [])[:10]:
        lines.append(
            f"  {entry['qualified_function']:<44} {int(entry['call_count']):8d} calls"
            f"  = {float(entry['inclusive_ms']):.1f} ms cumulative"
        )

    lines.extend(["", "Largest repeated setup/initialization work:"])
    for entry in (profile.get("repeated_setup") or [])[:8]:
        lines.append(
            f"  {entry['qualified_function']:<44} {int(entry['call_count']):8d} calls"
            f"  mean {_fmt_ms(entry.get('mean_ms'), 3)} ms"
            f"  = {float(entry['inclusive_ms']):.1f} ms"
        )

    lines.extend(["", "Largest unexplained bubbles across all stages:"])
    bubbles: list[tuple[str, Mapping[str, Any]]] = []
    for stage in stages:
        for bubble in (stage.get("bubbles") or {}).get("bubbles") or []:
            bubbles.append((str(stage["stage"]), bubble))
    bubbles.sort(key=lambda pair: -float(pair[1]["duration_ms"]))
    for stage_name, bubble in bubbles[:10]:
        lines.append(
            f"  {float(bubble['duration_ms']):9.1f} ms  {stage_name:<24}"
            f"  {bubble['classification']}"
        )
        lines.append(
            f"      from {bubble.get('previous_function') or '(stage start)'}"
            f" -> {bubble.get('next_function') or '(stage end)'}"
        )
        lines.append(
            f"      other-thread {_fmt_ms(bubble.get('other_thread_traced_ms'))} ms,"
            f" other-process {_fmt_ms(bubble.get('other_process_traced_ms'))} ms,"
            f" basis: {bubble.get('classification_basis')}"
        )
    if not bubbles:
        lines.append("  " + MEASUREMENT_UNAVAILABLE)

    lanes = profile.get("lanes") or []
    overlapping = [l for l in lanes if len(l.get("intervals") or []) > 1]
    lines.extend([
        "",
        f"Concurrency: {len(lanes)} execution lanes observed, "
        f"{len(overlapping)} of them with more than one traced interval.",
        "",
        "Any incomplete evidence:",
        f"  {(profile.get('incomplete_calls') or 0)} incomplete call(s), "
        f"{(profile.get('stack_inconsistencies') or 0)} stack inconsistency(ies).",
    ])
    if not profile.get("complete"):
        lines.append(f"  profile NOT complete: {len(profile.get('reasons') or [])} reason(s)")
    return lines


def _whole_gantt_lines(profile: Mapping[str, Any]) -> list[str]:
    """Section 3 -- the whole-request ASCII Gantt."""
    root = profile.get("root") or {}
    span = root.get("span")
    if not span:
        return [MEASUREMENT_UNAVAILABLE]
    clock = profile.get("clock_alignment") or {}
    merged = str(clock.get("status")) == "PROVEN"
    rows: list[tuple[str, float | None, float | None]] = [
        (f"ROOT {root.get('name')}", 0.0, _fmt_float_or_none(root.get("wall_ms"))),
    ]
    root_start = float(span[0])
    for stage in profile.get("stages") or []:
        stage_span = stage.get("span")
        if not stage_span:
            continue
        rows.append((
            f"  stage {stage['stage']}",
            _us_to_ms(float(stage_span[0]) - root_start),
            _us_to_ms(float(stage_span[1]) - root_start),
        ))
    return render_gantt(
        rows,
        window=(0.0, float(root.get("wall_ms") or 0.0)),
        merged=merged,
        header=(
            "Golden root timeline (ms from root start). "
            f"clock alignment={clock.get('status')}"
        ),
    )


def _fmt_float_or_none(value: Any) -> float | None:
    return _safe_float(value)


def _lane_gantt_lines(profile: Mapping[str, Any], lanes: Sequence[Mapping[str, Any]]) -> list[str]:
    root = profile.get("root") or {}
    wall = _safe_float(root.get("wall_ms")) or 0.0
    root_start = _safe_float((root.get("span") or (None, None))[0]) or 0.0
    rows: list[tuple[str, float | None, float | None]] = []
    for lane in lanes:
        intervals = lane.get("intervals") or []
        if not intervals:
            continue
        rows.append((
            str(lane.get("label")),
            _us_to_ms(float(intervals[0][0]) - root_start),
            _us_to_ms(float(intervals[-1][1]) - root_start),
        ))
    clock = profile.get("clock_alignment") or {}
    return render_gantt(
        rows,
        window=(0.0, wall),
        merged=str(clock.get("status")) == "PROVEN",
        header="Process/thread lanes (first start -> last end per lane, ms from root start)",
    )


def _stage_gantt_lines(stage: Mapping[str, Any]) -> list[str]:
    span = stage.get("span")
    wall = _safe_float(stage.get("wall_ms"))
    if not span or wall is None:
        return [MEASUREMENT_UNAVAILABLE]
    threshold = float(stage.get("visual_threshold_ms") or 0.0)
    base = float(span[0])
    rows: list[tuple[str, float | None, float | None]] = []
    grouped: dict[str, dict[str, Any]] = {}
    for call in stage.get("subtree") or []:
        call_span = _span(call)
        if call_span is None:
            continue
        duration_ms = _us_to_ms(call_span[1] - call_span[0]) or 0.0
        if duration_ms >= threshold:
            rows.append((
                f"{'  ' * int(call.get('depth') or 0)}{_qualified_name(call.get('name'))}",
                _us_to_ms(call_span[0] - base),
                _us_to_ms(call_span[1] - base),
            ))
            continue
        name = _qualified_name(call.get("name"))
        bucket = grouped.setdefault(name, {"count": 0, "sum_ms": 0.0, "max_ms": 0.0})
        bucket["count"] += 1
        bucket["sum_ms"] += duration_ms
        bucket["max_ms"] = max(bucket["max_ms"], duration_ms)
    rows.sort(key=lambda row: (row[1] is None, row[1] or 0.0, row[2] or 0.0, row[0]))
    lines = render_gantt(
        rows,
        window=(0.0, wall),
        merged=False,
        header=(
            f"{stage['stage']}: exhaustive waterfall, ms from stage start. "
            f"calls >= {_fmt_ms(threshold, 3)} ms drawn individually"
        ),
    )
    if grouped:
        lines.append("")
        lines.append(
            f"Grouped below the {threshold} ms visual threshold "
            "(every call is retained in golden_exhaustive_calls.csv.gz):"
        )
        table_rows = []
        for name in sorted(
            grouped,
            key=lambda key: (-grouped[key]["sum_ms"], key),
        ):
            bucket = grouped[name]
            table_rows.append([
                name,
                bucket["count"],
                round(bucket["sum_ms"], 3),
                round(bucket["max_ms"], 3),
            ])
        lines.extend(_table(
            ["Function", "Calls", "Sum ms", "Max ms"], table_rows,
        ))
    return lines


def _stage_lane_lines(stage: Mapping[str, Any]) -> list[str]:
    """Per-lane occupancy of a stage window, split nested vs concurrent.

    Reported per lane rather than as one union: a single union over every lane
    is always the stage wall, because the frame that measures the stage contains
    the window and would swallow the measurement whole.
    """
    nested = list(stage.get("nested_calls") or [])
    concurrent = list(stage.get("concurrent_calls") or [])
    if not nested and not concurrent:
        return ["  no other traced work inside this stage window."]
    lanes: dict[tuple[Any, Any], dict[str, Any]] = {}
    for row, kind in [(c, "nested") for c in nested] + [
        (c, "concurrent") for c in concurrent
    ]:
        key = (row.get("pid"), row.get("tid"))
        bucket = lanes.setdefault(key, {"nested": [], "concurrent": []})
        bucket[kind].append(row)
    out = [
        "  %-22s %-10s %8s %11s %11s" % (
            "lane", "kind", "calls", "union ms", "self ms",
        ),
    ]
    for key in sorted(lanes, key=lambda k: (str(k[0]), str(k[1]))):
        for kind in ("nested", "concurrent"):
            rows = lanes[key][kind]
            if not rows:
                continue
            spans = [
                (float(r["span_start_us"]), float(r["span_end_us"]))
                for r in rows if r.get("span_ok")
            ]
            union = (_us_to_ms(_union_length(spans)) or 0.0) if spans else 0.0
            self_ms = sum(float(r.get("exclusive_self_ms") or 0.0) for r in rows)
            out.append("  pid=%-6s tid=%-9s %8d %11.1f %11.1f" % (
                key[0], key[1], len(rows), union, self_ms,
            ))
    return out


def _stage_function_table(stage: Mapping[str, Any]) -> list[str]:
    """Function cost table shown before each stage Gantt."""
    wall = _safe_float(stage.get("wall_ms"))
    functions = list(stage.get("functions") or [])
    inclusive_view = functions[:15]
    exclusive_view = sorted(
        functions, key=lambda f: (-float(f["exclusive_ms"]), str(f["qualified_function"]))
    )[:15]
    count_view = sorted(
        functions, key=lambda f: (-int(f["call_count"]), str(f["qualified_function"]))
    )[:15]
    max_view = sorted(
        functions, key=lambda f: (-float(f["max_call_ms"]), str(f["qualified_function"]))
    )[:10]

    def view(rows: Sequence[Mapping[str, Any]], percent_key: str) -> list[str]:
        return _table(
            ["Function", "Source", "Calls", "Incl ms", "Self ms", "% stage", "Max call ms"],
            [
                [
                    row["qualified_function"],
                    f"{row['source_file']}:{row['source_line']}"
                    if row.get("source_line") else row.get("source_file", ""),
                    row["call_count"],
                    round(float(row["inclusive_ms"]), 1),
                    round(float(row["exclusive_ms"]), 1),
                    round(float(row[percent_key]), 1)
                    if row.get(percent_key) is not None else "",
                    round(float(row["max_call_ms"]), 1),
                ]
                for row in rows
            ],
        )

    lines = ["By inclusive time:", *view(inclusive_view, "pct_of_stage_wall"), ""]
    lines.extend(["By exclusive / self time:", *view(exclusive_view, "pct_of_stage_exclusive"), ""])
    lines.extend(["By call count:", *view(count_view, "pct_of_stage_wall"), ""])
    lines.extend(["By single worst invocation:", *view(max_view, "pct_of_stage_wall"), ""])
    del wall
    return lines


def _bubble_lines(stage: Mapping[str, Any]) -> list[str]:
    bubbles = stage.get("bubbles") or {}
    rows = list(bubbles.get("bubbles") or [])
    if not rows:
        return [
            f"No uncovered interval on the owner's execution context inside "
            f"{stage.get('stage')} "
            f"(window {_fmt_ms(bubbles.get('window_ms'))} ms, "
            f"traced child union {_fmt_ms(stage.get('descendant_union_ms'))} ms)."
        ]
    out = [
        f"Owner lane: {(stage.get('call') or {}).get('process_role')}"
        f"/tid:{(stage.get('call') or {}).get('tid')}"
        f"  window {_fmt_ms(bubbles.get('window_ms'))} ms",
        f"{len(rows)} bubble(s), total {_fmt_ms(bubbles.get('total_bubble_ms'))} ms.",
        "A bubble is an interval inside the stage wall not covered by a traced "
        "child on that same execution context. It is not by itself idle time.",
        "",
    ]
    for bubble in rows[:20]:
        out.extend([
            f"Bubble: {float(bubble['duration_ms']):.1f} ms",
            f"  stage: {stage.get('stage')}",
            f"  interval: {bubble['start_offset_ms']} -> {bubble['end_offset_ms']} ms "
            "from stage start",
            f"  previous traced function: {bubble.get('previous_function') or '(stage start)'}",
            f"  next traced function: {bubble.get('next_function') or '(stage end)'}",
            f"  same-thread traced work during interval: "
            f"{_fmt_ms(bubble.get('same_thread_traced_ms'))} ms",
            f"  other-thread traced work during interval: "
            f"{_fmt_ms(bubble.get('other_thread_traced_ms'))} ms",
            f"  other-process traced work during interval: "
            f"{_fmt_ms(bubble.get('other_process_traced_ms'))} ms "
            f"(clock alignment {bubble.get('cross_process_alignment')})",
            f"  CPU sampler: {bubble.get('cpu_evidence')}",
            f"  semantic evidence overlapping: "
            + (
                ", ".join(
                    f"{hit['operation_type']}({hit['overlap_ms']} ms)"
                    for hit in bubble.get("semantic_evidence") or []
                ) or "none"
            ),
            f"  classification: {bubble['classification']}",
            f"  basis: {bubble.get('classification_basis')}",
            "",
        ])
    if len(rows) > 20:
        out.append(f"... and {len(rows) - 20} more bubbles in the JSON summary.")
    active = bubbles.get("other_lanes_active") or []
    if active:
        out.append("Other lanes active inside this stage window:")
        out.extend(_table(
            ["Lane", "Process role", "pid", "tid", "task", "Busy ms"],
            [
                [a["lane"], a["process_role"], a["pid"], a["tid"], a["task_id"], a["busy_ms"]]
                for a in active[:15]
            ],
        ))
    return out


    lines.extend(["", "Lanes inside this stage window:", ""])
    lines.extend(_stage_lane_lines(stage))

    lines.extend(["", "Work running concurrently on other threads:", ""])
    concurrent = list(stage.get("concurrent_calls") or [])
    if not concurrent:
        lines.append("  none: this stage's window contains no work on any other thread.")
    else:
        lines.extend(_table(
            ["Function", "Lane", "Wall ms", "Self ms", "Calls"],
            [
            [
                _qualified_name(c.get("name")),
                f"tid:{c.get('tid')}",
                    round(float(c.get("wall_ms") or 0.0), 1),
                    round(float(c.get("exclusive_self_ms") or 0.0), 1),
                    1,
                ]
                for c in sorted(
                    concurrent,
                    key=lambda c: -float(c.get("wall_ms") or 0.0),
                )[:40]
            ],
        ))
        lines.append("")
        lines.append(
            "  concurrent union: %.1f ms of work this stage waited for or ran "
            "alongside" % float(stage.get("concurrent_union_ms") or 0.0)
        )

    lines.extend(["", "Exhaustive waterfall:", ""])
    lines.extend(_code(_stage_gantt_lines(stage)))
    return lines


def _stage_section(stage: Mapping[str, Any]) -> list[str]:
    lines: list[str] = []
    span = stage.get("span")
    lines.extend([
        f"wall: {_fmt_ms(stage.get('wall_ms'))} ms",
        f"start offset from root: {_fmt_ms(stage.get('start_offset_ms'))} ms",
        f"source: {(stage.get('call') or {}).get('source_file')}"
        f":{(stage.get('call') or {}).get('source_line')}",
        f"traced calls in this stage's own body: {len(stage.get('subtree') or [])}",
        f"records carrying this stage name: {stage.get('candidates_seen')}",
        f"owner-lane child union: "
        f"{_fmt_ms(stage.get('descendant_union_ms'))} ms",
        f"concurrent union (other threads in the window): "
        f"{_fmt_ms(stage.get('concurrent_union_ms'))} ms",
        f"total content attributed: "
        f"{_fmt_ms(stage.get('content_union_ms'))} ms "
        f"of {_fmt_ms(stage.get('wall_ms'))} ms wall "
        f"({_fmt_pct(stage.get('content_union_ms'), stage.get('wall_ms'))}%)",
        f"unattributed (GPU/C/native or a lane with no tracer): "
        f"{_fmt_ms(max(0.0, float(stage.get('wall_ms') or 0) - float(stage.get('content_union_ms') or 0)))} ms",
        f"enclosing frames excluded from the above: {stage.get('enclosing_count')}",
        "",
    ])
    lines.extend(_stage_function_table(stage))
    lines.extend(["", "Exhaustive waterfall:", ""])
    lines.extend(_code(_stage_gantt_lines(stage)))
    lines.extend(["", "Bubble / gap analysis:", ""])
    lines.extend(_bubble_lines(stage))
    lines.extend(["", "Concurrency and process activity:", ""])
    lanes_active = (stage.get("bubbles") or {}).get("other_lanes_active") or []
    if lanes_active:
        lines.extend(_table(
            ["Lane", "Process role", "pid", "tid", "task", "Busy ms"],
            [
                [a["lane"], a["process_role"], a["pid"], a["tid"], a["task_id"], a["busy_ms"]]
                for a in lanes_active[:15]
            ],
        ))
    else:
        lines.append(
            "No other execution lane produced traced Python calls inside this "
            "stage window."
        )
    lines.extend(["", "Top repeated calls:", ""])
    repeated = list(stage.get("repeated") or [])
    if repeated:
        lines.extend(_table(
            ["Function", "Calls", "Sum ms", "Mean ms", "Max ms"],
            [
                [
                    r["qualified_function"], r["call_count"],
                    round(float(r["inclusive_ms"]), 1),
                    round(float(r.get("mean_ms") or 0.0), 4),
                    round(float(r["max_call_ms"]), 1),
                ]
                for r in repeated[:15]
            ],
        ))
    else:
        lines.append(MEASUREMENT_UNAVAILABLE)
    lines.extend(["", "Largest self-time calls:", ""])
    self_calls = top_calls(stage.get("subtree") or [], key="exclusive_self_ms", limit=15)
    if self_calls:
        lines.extend(_table(
            ["Function", "Source", "Self ms", "Wall ms", "Calls of same fn"],
            [
                [
                    _qualified_name(c.get("name")),
                    f"{c.get('source_file')}:{c.get('source_line')}"
                    if c.get("source_line") else c.get("source_file", ""),
                    round(float(c.get("exclusive_self_ms") or 0.0), 1),
                    round(float(c.get("wall_ms") or 0.0), 1),
                    "",
                ]
                for c in self_calls
            ],
        ))
    else:
        lines.append(MEASUREMENT_UNAVAILABLE)
    lines.extend(["", "Call tree:", ""])
    tree = list(stage.get("call_tree") or [])
    lines.extend(_code(tree[:300]))
    if len(tree) > 300:
        lines.append(f"... and {len(tree) - 300} more tree lines in the JSON summary.")
    lines.extend(["", "Why is this stage slow?", "", "```text"])
    lines.extend(str((stage.get("diagnosis") or {}).get("narrative", "")).splitlines())
    lines.append("```")
    del span
    return lines


def _top_offender_lines(profile: Mapping[str, Any]) -> list[str]:
    """Section 6 -- the things to actually go and fix."""
    lines: list[str] = []
    lines.append(f"Top {TOP_N} individual calls by wall time:")
    lines.extend(_table(
        ["Function", "Process role", "pid", "tid", "Wall ms", "Self ms", "Source"],
        [
            [
                _qualified_name(c.get("name")),
                c.get("process_role"), c.get("pid"), c.get("tid"),
                round(float(c.get("wall_ms") or 0.0), 1),
                round(float(c.get("exclusive_self_ms") or 0.0), 1),
                f"{c.get('source_file')}:{c.get('source_line')}"
                if c.get("source_line") else c.get("source_file", ""),
            ]
            for c in (profile.get("top_calls") or [])
        ],
    ))
    for title, key, value_key, header in (
        ("Top functions by accumulated inclusive time:", "top_by_inclusive", "inclusive_ms", "Incl ms"),
        ("Top functions by accumulated exclusive/self time:", "top_by_exclusive", "exclusive_ms", "Self ms"),
    ):
        lines.extend(["", title])
        lines.extend(_table(
            ["Function", "Source", "Calls", header, "Max call ms"],
            [
                [
                    f["qualified_function"],
                    f"{f['source_file']}:{f['source_line']}" if f.get("source_line") else f.get("source_file", ""),
                    f["call_count"],
                    round(float(f[value_key]), 1),
                    round(float(f["max_call_ms"]), 1),
                ]
                for f in (profile.get(key) or [])
            ],
        ))
    lines.extend(["", "Top functions by call count:"])
    lines.extend(_table(
        ["Function", "Source", "Calls", "Inclin ms", "Mean ms"],
        [
            [
                f["qualified_function"],
                f"{f['source_file']}:{f['source_line']}" if f.get("source_line") else f.get("source_file", ""),
                f["call_count"],
                round(float(f["inclusive_ms"]), 1),
                round(float(f["inclusive_ms"]) / max(1, int(f["call_count"])), 4),
            ]
            for f in (profile.get("top_by_count") or [])
        ],
    ))
    lines.extend(["", "Top repeated setup/initialization functions:"])
    lines.extend(_table(
        ["Function", "Calls", "Sum ms", "Mean ms", "Max ms"],
        [
            [
                r["qualified_function"], r["call_count"],
                round(float(r["inclusive_ms"]), 1),
                round(float(r.get("mean_ms") or 0.0), 4),
                round(float(r["max_call_ms"]), 1),
            ]
            for r in (profile.get("repeated_setup") or [])
        ],
    ))
    lines.extend(["", "Top stage residuals:"])
    lines.extend(_table(
        ["Stage", "Wall ms", "Child union ms", "Residual ms", "Residual %"],
        [
            [
                s["stage"],
                round(float(s.get("wall_ms") or 0.0), 1),
                round(float(s.get("descendant_union_ms") or 0.0), 1),
                round(max(0.0, float(s.get("wall_ms") or 0.0) - float(s.get("descendant_union_ms") or 0.0)), 1),
                round(
                    (
                        max(0.0, float(s.get("wall_ms") or 0.0) - float(s.get("descendant_union_ms") or 0.0))
                        / float(s["wall_ms"]) * 100.0
                    ) if s.get("wall_ms") else 0.0,
                    1,
                ),
            ]
            for s in (profile.get("stages") or []) if s.get("wall_ms")
        ],
    ))
    lines.extend(["", "Top bubbles across all stages:"])
    flat: list[tuple[str, Mapping[str, Any]]] = []
    for stage in profile.get("stages") or []:
        for bubble in (stage.get("bubbles") or {}).get("bubbles") or []:
            flat.append((str(stage["stage"]), bubble))
    flat.sort(key=lambda pair: -float(pair[1]["duration_ms"]))
    lines.extend(_table(
        ["Stage", "Duration ms", "Classification", "Other thread ms", "Other process ms", "Basis"],
        [
            [
                name,
                round(float(b["duration_ms"]), 1),
                b["classification"],
                round(float(b.get("other_thread_traced_ms") or 0.0), 1),
                b.get("other_process_traced_ms"),
                b.get("classification_basis"),
            ]
            for name, b in flat[:TOP_N]
        ],
    ))
    return lines


def render_markdown(profile: Mapping[str, Any]) -> str:
    """Render ``golden_exhaustive_profile.md`` from *profile*.

    Human-first and self-contained: no Chrome Trace viewer, no second script,
    no Mermaid.  ASCII is authoritative.
    """
    root = profile.get("root") or {}
    manifest = profile.get("process_manifest") or {}
    clock = profile.get("clock_alignment") or {}
    lines: list[str] = [
        "# Golden Exhaustive Execution Profile",
        "",
        "Purpose: make wasted time inside Golden obvious, from the actual call "
        "trace, without adding a stopwatch to Golden.",
        "",
        f"trace_id: {profile.get('trace_id') or MEASUREMENT_UNAVAILABLE}",
        f"request_id: {profile.get('request_id') or MEASUREMENT_UNAVAILABLE}",
        f"schema: {profile.get('schema_version')}",
        "",
        *_section("SECTION 1 - TRACE HEALTH / TRUST"),
        *_code(_health_lines(profile)),
    ]
    if str(clock.get("status")) != "PROVEN":
        lines.extend([
            "",
            "> **CLOCK ALIGNMENT IS UNPROVEN.** Cross-process timestamps are not "
            "known to share a clock, so no merged cross-process ordering is "
            "claimed anywhere in this report. Process lanes are still listed, "
            "but only within their own process. Reason: "
            f"{clock.get('reason')}",
        ])
    lines.extend([
        "",
        *_section("SECTION 2 - 30 SECOND HUMAN SUMMARY"),
        *_code(_summary_lines(profile)),
        "",
        *_section("SECTION 3 - WHOLE GOLDEN GANTT"),
        *_code(_whole_gantt_lines(profile)),
        "",
        *_section("SECTION 4 - ONE WATERFALL PER CANONICAL GOLDEN STAGE"),
    ])
    stages = [s for s in (profile.get("stages") or [])]
    if not stages:
        lines.append(
            "No canonical stage was observed under the authoritative root, so no "
            "per-stage waterfall can be produced."
        )
    for stage in stages:
        lines.extend([
            "",
            "-" * 72,
            f"STAGE: {stage.get('stage')}",
            "-" * 72,
            "",
            *_stage_section(stage),
        ])
    lines.extend([
        "",
        *_section("SECTION 5 - BUBBLE / GAP ANALYSIS (WHOLE REQUEST)"),
    ])
    lines.extend(_code(_bubble_lines({
        "stage": "golden_request",
        "call": root,
        "bubbles": profile.get("request_bubbles") or {"bubbles": []},
        "descendant_union_ms": root.get("direct_child_union_ms"),
    })))
    lines.extend([
        "",
        *_section("SECTION 6 - TOP OFFENDERS"),
        *_code(_top_offender_lines(profile)),
        "",
        *_section("SECTION 7 - PROCESS / THREAD LANES"),
    ])
    lanes = list(profile.get("lanes") or [])
    lines.extend(_code(_lane_gantt_lines(profile, lanes)))
    lines.extend(["", *_table(
        ["Lane", "Process role", "pid", "tid", "task", "Calls", "Busy ms", "Span ms"],
        [
            [
                lane.get("label"), lane.get("process_role"), lane.get("pid"),
                lane.get("tid"), lane.get("task_id"), lane.get("call_count"),
                lane.get("busy_ms"), lane.get("wall_span_ms"),
            ]
            for lane in lanes
        ],
    )])
    lines.extend(["", *_section("SECTION 8 - CALL TREE (WHOLE REQUEST)")])
    root_span = root.get("span")
    if root_span:
        lines.extend(_code(build_call_tree(
            profile.get("root_call") or _root_call_of(profile),
            profile.get("root_subtree") or [],
            profile.get("children") or {},
            max_depth=8,
            min_ms=0.0,
            max_nodes=600,
        )[:600]))
    else:
        lines.append(MEASUREMENT_UNAVAILABLE)
    lines.extend([
        "",
        *_section("SECTION 9 - WHY IS THIS STAGE SLOW?"),
    ])
    for stage in stages:
        lines.extend([
            "",
            "-" * 72,
            f"{stage.get('stage')} = {_fmt_ms(stage.get('wall_ms'))} ms",
            "-" * 72,
            "",
            "```text",
            *str((stage.get("diagnosis") or {}).get("narrative", "")).splitlines(),
            "```",
        ])
    lines.extend([
        "",
        *_section("ARTIFACTS"),
        f"- `{CALLS_NAME}`: one row per captured Golden-owned Python invocation.",
        f"- `{MANIFEST_NAME}`: expected/traced/missing process accounting.",
        f"- `{SUMMARY_NAME}`: machine-readable version of everything above.",
        "",
        "The existing >50 ms Golden summary remains the quick view; this report "
        "is the microscope. Neither replaces the other.",
        "",
    ])
    return "\n".join(lines)


def _root_call_of(profile: Mapping[str, Any]) -> Mapping[str, Any]:
    for call in profile.get("calls") or []:
        if (
            _basename(call.get("name")) in GOLDEN_ROOT_NAMES
            and call.get("category") == GOLDEN_ROOT_CATEGORY
        ):
            return call
    for call in profile.get("calls") or []:
        if _basename(call.get("name")) in GOLDEN_ROOT_NAMES:
            return call
    return {}


# ---------------------------------------------------------------------------
# Section J: artifacts
# ---------------------------------------------------------------------------


def _calls_csv_rows(profile: Mapping[str, Any]) -> list[dict[str, Any]]:
    root = profile.get("root") or {}
    root_span = root.get("span")
    base = float(root_span[0]) if root_span else 0.0
    calls = list(profile.get("calls") or [])
    by_index = {
        (call.get("pid"), call.get("event_index")): call for call in calls
    }
    rows: list[dict[str, Any]] = []
    for call in calls:
        span = _span(call)
        parent_function = ""
        parent_index = call.get("parent_event_index")
        if parent_index is not None:
            parent = by_index.get((call.get("pid"), parent_index))
            if parent is not None:
                parent_function = _qualified_name(parent.get("name"))
        rows.append({
            "event_index": call.get("event_index"),
            "process_role": call.get("process_role"),
            "pid": call.get("pid"),
            "parent_pid": call.get("process_parent_pid"),
            "tid": call.get("tid"),
            "task_id": str(call.get("task_id") or ""),
            "function": _basename(call.get("name")),
            "qualified_function": _qualified_name(call.get("name")),
            "source_file": call.get("source_file"),
            "source_line": call.get("source_line"),
            "category": call.get("category"),
            "parent_event_index": parent_index,
            "parent_function": parent_function,
            "depth": call.get("depth"),
            "start_offset_ms": _us_to_ms(span[0] - base) if span else "",
            "end_offset_ms": _us_to_ms(span[1] - base) if span else "",
            "wall_ms": call.get("wall_ms") if span else "",
            "direct_child_count": call.get("direct_child_count", 0),
            "direct_child_sum_ms": call.get("direct_child_sum_ms"),
            "direct_child_union_ms": call.get("direct_child_union_ms"),
            "child_overlap_ms": call.get("child_overlap_ms"),
            "exclusive_self_ms": call.get("exclusive_self_ms") if span else "",
            "complete": bool(call.get("complete")),
        })
    rows.sort(key=lambda r: (
        str(r["process_role"]), _safe_int(r["pid"]) or 0,
        _safe_float(r["start_offset_ms"]) if r["start_offset_ms"] != "" else float("inf"),
        _safe_int(r["event_index"]) or 0,
    ))
    return rows


def _write_gzip_csv(path: Path, rows: Sequence[Mapping[str, Any]], fieldnames: Sequence[str]) -> None:
    """Write a deterministic gzipped CSV (mtime=0, no stored filename)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=list(fieldnames), extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        writer.writerow({k: ("" if row.get(k) is None else row.get(k)) for k in fieldnames})
    path.write_bytes(gzip.compress(buffer.getvalue().encode("utf-8-sig"), mtime=0))


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=str), encoding="utf-8",
    )


def _jsonable(value: Any) -> Any:
    """Convert analysis structures into JSON-safe values, deterministically."""
    if isinstance(value, Mapping):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def write_artifacts(session_dir: Path, profile: Mapping[str, Any]) -> dict[str, str]:
    """Write the four authoritative artifacts (plus the merged raw trace).

    Returns the written relative paths.  The report is written *last* so its own
    ``report_artifact_written`` check can be satisfied truthfully.
    """
    session_dir = Path(session_dir)
    derived = session_dir / "derived"
    derived.mkdir(parents=True, exist_ok=True)

    written: dict[str, str] = {}
    _write_gzip_csv(derived / CALLS_NAME, _calls_csv_rows(profile), EXHAUSTIVE_CALL_FIELDS)
    written["calls"] = f"derived/{CALLS_NAME}"

    _write_json(derived / MANIFEST_NAME, _jsonable(profile.get("process_manifest")))
    written["manifest"] = f"derived/{MANIFEST_NAME}"

    summary = {
        "schema_version": profile.get("schema_version"),
        "trace_id": profile.get("trace_id"),
        "request_id": profile.get("request_id"),
        "GOLDEN_EXHAUSTIVE_PROFILE_COMPLETE": "YES" if profile.get("complete") else "NO",
        "reasons": profile.get("reasons"),
        "contract": profile.get("contract"),
        "health": {
            "root": profile.get("root"),
            "clock_alignment": profile.get("clock_alignment"),
            "thread_coverage": profile.get("thread_coverage"),
            "process_coverage": (profile.get("process_manifest") or {}).get("process_coverage"),
            "expected_processes": (profile.get("process_manifest") or {}).get("expected_processes"),
            "traced_processes": (profile.get("process_manifest") or {}).get("traced_processes"),
            "missing_processes": (profile.get("process_manifest") or {}).get("missing_processes"),
            "incomplete_calls": profile.get("incomplete_calls"),
            "stack_inconsistencies": profile.get("stack_inconsistencies"),
            "torch_enabled": profile.get("torch_enabled"),
            "c_function_tracing": profile.get("c_function_tracing"),
        },
        "stages": [
            {
                "stage": stage.get("stage"),
                "wall_ms": stage.get("wall_ms"),
                "start_offset_ms": stage.get("start_offset_ms"),
                "source_file": (stage.get("call") or {}).get("source_file"),
                "source_line": (stage.get("call") or {}).get("source_line"),
                "complete": stage.get("complete"),
                "candidates_seen": stage.get("candidates_seen"),
                "descendant_union_ms": stage.get("descendant_union_ms"),
                "functions": stage.get("functions"),
                "repeated": stage.get("repeated"),
                "bubbles": stage.get("bubbles"),
                "diagnosis": stage.get("diagnosis"),
                "call_tree": stage.get("call_tree"),
            }
            for stage in profile.get("stages") or []
        ],
        "top_calls": profile.get("top_calls"),
        "top_by_inclusive": profile.get("top_by_inclusive"),
        "top_by_exclusive": profile.get("top_by_exclusive"),
        "top_by_count": profile.get("top_by_count"),
        "repeated_setup": profile.get("repeated_setup"),
        # Lanes carry their raw interval lists only for in-memory analysis;
        # serializing them would turn a 174k-call request into a ~65 MB summary
        # for no analytical gain.  Counts and totals are what the summary needs.
        "lanes": [
            {k: v for k, v in lane.items() if k != "intervals"}
            for lane in profile.get("lanes") or []
        ],
        "required_stages": profile.get("required_stages"),
        "observed_stages": profile.get("observed_stages"),
        "processes": profile.get("processes"),
        "visual_threshold_ms": profile.get("visual_threshold_ms"),
    }
    _write_json(derived / SUMMARY_NAME, _jsonable(summary))
    written["summary"] = f"derived/{SUMMARY_NAME}"

    merged = write_merged_trace(session_dir, profile)
    if merged:
        written["merged_trace"] = merged

    # Render once to prove the report can be produced at all, then finalize the
    # contract with that evidence and render the authoritative text.  A report
    # that fails to render or write raises instead of leaving a "complete"
    # verdict behind with no artifact to back it.
    render_markdown(profile)
    _finalize_contract(profile)
    report = render_markdown(profile)
    (derived / REPORT_NAME).write_text(report, encoding="utf-8")
    written["report"] = f"derived/{REPORT_NAME}"
    return written


def _finalize_contract(profile: Mapping[str, Any]) -> None:
    """Settle the two checks that can only be decided once rendering happened."""
    if not isinstance(profile, dict):
        return
    contract = profile.get("contract")
    if not isinstance(contract, dict):
        return
    checks = contract.get("checks")
    if not isinstance(checks, list):
        return
    for check in checks:
        if check.get("check") in ("report_artifact_written", "every_stage_section_generated"):
            check["ok"] = True
            check["detail"] = (
                REPORT_NAME if check.get("check") == "report_artifact_written"
                else f"stages={len(profile.get('stages') or [])}"
            )
    contract["reasons"] = [f"{c['check']}: {c['detail']}" for c in checks if not c["ok"]]
    contract["complete"] = not contract["reasons"]
    profile["complete"] = bool(contract["complete"])
    profile["reasons"] = list(contract["reasons"])
    profile["rendered"] = True


def write_merged_trace(session_dir: Path, profile: Mapping[str, Any]) -> str:
    """Write ``derived/viztracer_merged.json.gz`` when the clocks allow it.

    Concatenating timestamps across processes without a proven shared origin
    would produce a chart that looks authoritative and is not, so this returns
    ``""`` when alignment is unproven instead of writing a misleading artifact.
    """
    if str((profile.get("clock_alignment") or {}).get("status")) != "PROVEN":
        return ""
    merged_events: list[dict[str, Any]] = []
    for process in profile.get("processes") or []:
        data = process.get("data")
        if not isinstance(data, dict):
            path = session_dir / "raw" / str(process.get("source") or "")
            data = _load_json_maybe_gzip(path)
        if not isinstance(data, dict):
            continue
        events = data.get("traceEvents")
        if not isinstance(events, list):
            continue
        role = str(process.get("role") or "other")
        pid = process.get("pid")
        for event in events:
            if not isinstance(event, dict):
                continue
            tagged = dict(event)
            # Disambiguate pids so two processes never collapse into one lane.
            tagged["pid"] = f"{role}#{pid}" if pid is not None else role
            merged_events.append(tagged)
    merged_events.sort(key=lambda e: (
        str(e.get("pid") or ""),
        _safe_float(e.get("ts")) if _safe_float(e.get("ts")) is not None else float("inf"),
    ))
    payload = {
        "traceEvents": merged_events,
        "viztracer_metadata": {
            "version": "merged-by-comfymodal-golden-exhaustive-profiler",
            "overflow": any(bool(p.get("truncated")) for p in profile.get("processes") or []),
            "clock_alignment": profile.get("clock_alignment"),
        },
    }
    target = Path(session_dir) / "derived" / MERGED_NAME
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(gzip.compress(
        json.dumps(payload, sort_keys=True, default=str).encode("utf-8"), mtime=0,
    ))
    return f"derived/{MERGED_NAME}"
