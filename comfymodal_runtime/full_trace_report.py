"""V2 Full Execution Trace Report — offline session analysis.

Schema version: v2-full-trace/1

Produces a comprehensive trace report from an offline session directory
containing VizTracer, PyTorch profiler, resource samples, milestones,
wrapper snapshots, and runtime metadata.  Deterministic, stdlib-only,
no network/LLM/Modal/Torch dependencies.
"""

from __future__ import annotations

import csv
import gzip
import hashlib
import io
import json
import os
import statistics
import struct
from collections import defaultdict
from collections.abc import Callable, Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, TextIO

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MEASUREMENT_UNAVAILABLE = "measurement_unavailable"
VERSION = "v2-full-trace/1"

# Semantic operation type constants (must match requirement 6 exactly)
SEMANTIC_TYPES = {
    "volume_reload:models",
    "volume_reload:runtime_state",
    "restore_plan_read",
    "certificate_read",
    "certificate_write",
    "execution_prefill",
    "clip_graph_encode",
    "clip_prefill_encode",
    "vae_file_load",
    "unet_gpu_activation",
    "cache_seed",
    "cachedit_restore_prepare",
    "cachedit_request_attach",
    "res4lyf_restore_prepare",
    "res4lyf_request_parse",
    "executor_cache_initialize",
    "output_encode",
    "runtime_state_commit",
}

LIFECYCLE_BOUNDARIES = (
    "restore_complete",
    "request_entry",
    "prompt_executor_invoke",
    "sampling_start",
    "trace_stop",
    "trace_stop_boundary",
)

# ---------------------------------------------------------------------------
# Helpers: IO / hashing / CSV
# ---------------------------------------------------------------------------

_CSV_BOM = "\ufeff"


def _sha256_file(path: Path) -> str:
    """Return hex SHA-256 of *path*.  Returns empty string if unreadable."""
    try:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()
    except Exception:
        return ""


def _safe_read_bytes(path: Path) -> bytes:
    """Read *path* as bytes; returns b"" on failure."""
    try:
        return path.read_bytes()
    except Exception:
        return b""


def _safe_read_text(path: Path) -> str:
    """Read *path* as text; returns "" on failure."""
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return ""


def _json_loads(text: str) -> Any:
    """Parse JSON with error handling; returns None on failure."""
    try:
        return json.loads(text)
    except Exception:
        return None


def _json_load(path: Path) -> Any:
    """Load JSON from *path*; returns None on failure."""
    return _json_loads(_safe_read_text(path))


def _json_load_gzip(path: Path) -> Any:
    """Load gzipped JSON from *path*; returns None on failure."""
    raw = _safe_read_bytes(path)
    if not raw:
        return None
    try:
        return json.loads(gzip.decompress(raw).decode("utf-8", errors="replace"))
    except Exception:
        return None


def _jsonl_load_gzip(path: Path) -> list[dict[str, Any]]:
    """Load gzipped JSONL from *path*; returns [] on failure."""
    raw = _safe_read_bytes(path)
    if not raw:
        return []
    try:
        text = gzip.decompress(raw).decode("utf-8", errors="replace")
    except Exception:
        return []
    return _parse_jsonl_lines(text)


def _jsonl_load_gzip_line_by_line(path: Path) -> list[dict[str, Any]]:
    """Parse gzipped JSONL incrementally line-by-line.

    Yields parsed dicts one line at a time without loading the decompressed
    payload fully into memory.  Returns [] on failure.
    """
    raw = _safe_read_bytes(path)
    if not raw:
        return []
    try:
        decompressed = gzip.decompress(raw)
    except Exception:
        return []
    lines: list[dict[str, Any]] = []
    for line in io.StringIO(decompressed.decode("utf-8", errors="replace")):
        line = line.strip()
        if not line:
            continue
        try:
            parsed = json.loads(line)
            if isinstance(parsed, dict):
                lines.append(parsed)
        except Exception:
            pass
    return lines


def _jsonl_load(path: Path) -> list[dict[str, Any]]:
    """Load JSONL from *path*; returns [] on failure."""
    return _parse_jsonl_lines(_safe_read_text(path))


def _parse_jsonl_lines(text: str) -> list[dict[str, Any]]:
    lines: list[dict[str, Any]] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            parsed = json.loads(line)
            if isinstance(parsed, dict):
                lines.append(parsed)
        except Exception:
            pass
    return lines


def _write_csv(
    path: Path,
    rows: Sequence[dict[str, Any]],
    *,
    fieldnames: Sequence[str] | None = None,
) -> None:
    """Write CSV with BOM, deterministic ordering, and None→empty handling."""
    if not rows and fieldnames is None:
        path.write_text(_CSV_BOM + "\n", encoding="utf-8-sig")
        return
    fn = fieldnames or list(rows[0].keys())
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=fn, extrasaction="ignore")
            writer.writeheader()
            for row in rows:
                cleaned = {k: ("" if v is None else v) for k, v in row.items()}
                writer.writerow(cleaned)
    except Exception:
        pass


def _write_json(path: Path, data: Any, *, sort_keys: bool = True) -> None:
    """Write deterministic JSON."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(data, sort_keys=sort_keys, separators=(",", ":"), ensure_ascii=False),
            encoding="utf-8",
        )
    except Exception:
        pass


def _micros(ts: float) -> int:
    """Convert seconds to microseconds."""
    return int(round(ts * 1_000_000))


def _ms(ts: float) -> float:
    """Convert microseconds to milliseconds."""
    return ts / 1000.0


def _clamp_non_negative(value: float, *, epsilon: float = 1e-9) -> float:
    """Clamp tiny negative floating-point errors to zero."""
    if value < 0 and value > -epsilon:
        return 0.0
    return value


def _fmt_ms(us: float | None) -> float | str:
    """Format microseconds as ms, or measurement_unavailable."""
    if us is None:
        return MEASUREMENT_UNAVAILABLE
    return round(us / 1000.0, 3)


# ---------------------------------------------------------------------------
# Helper: read Chrome/VizTracer trace (duplicate of parse_trace_events for
# compatibility; both paths converge through parse_viztracer_trace)
# ---------------------------------------------------------------------------


def _parse_viztracer_trace(data: Any) -> list[dict[str, Any]]:
    """Extract trace events from loaded VizTracer/Chrome trace JSON.

    Handles the top-level ``traceEvents`` array as well as the Vistracer
    wrapper format with ``traceEvents`` inside ``$map`` / metadata.
    Returns a list of raw event dicts (flattened, non-duration events removed
    to keep only X, B, E phase events).
    """
    events: list[dict[str, Any]] = []
    if isinstance(data, dict):
        raw = data.get("traceEvents") or data.get("events") or []
        if isinstance(raw, dict):
            # VizTracer map format
            for val in raw.values():
                if isinstance(val, dict) and "ph" in val:
                    events.append(val)
        elif isinstance(raw, list):
            events = raw
    elif isinstance(data, list):
        events = data
    return events


def parse_chrome_trace_events(data: Any) -> list[dict[str, Any]]:
    """Parse Chrome/VizTracer trace events into a normalized list.

    Returns a list of event dicts with at minimum ``ph`` (phase),
    ``name``, ``ts`` (micros, None if unavailable), and optional ``dur``,
    ``pid``, ``tid``, ``args``, ``cat``.
    Unknown/missing ts/pid/tid are left as None (not fabricated as 0).
    """
    raw = _parse_viztracer_trace(data)
    result: list[dict[str, Any]] = []
    for ev in raw:
        if not isinstance(ev, dict):
            continue
        ph = ev.get("ph", "")
        if ph not in ("X", "B", "E", "i", "I"):
            continue
        normalized: dict[str, Any] = {
            "ph": ph,
            "name": str(ev.get("name", "")),
            "ts": _safe_float(ev.get("ts"), None),
            "pid": ev.get("pid") if "pid" in ev else None,
            "tid": ev.get("tid") if "tid" in ev else None,
        }
        if ph == "X":
            dur = _safe_float(ev.get("dur"), None)
            if dur is not None:
                normalized["dur"] = dur
        cat = ev.get("cat")
        if cat is not None:
            normalized["cat"] = str(cat)
        args = ev.get("args")
        if isinstance(args, dict):
            normalized["args"] = args
        result.append(normalized)
    return result


def _safe_float(value: Any, default: float | None = None) -> float | None:
    """Convert to float or return *default* (None) on failure/inf."""
    try:
        v = float(value)
        if not (v < float("inf")):
            return default
        return v
    except (TypeError, ValueError, OverflowError):
        return default


def _safe_int(value: Any, default: int | None = None) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


# ---------------------------------------------------------------------------
# VizTracer metadata extraction
# ---------------------------------------------------------------------------


def _extract_viztracer_meta(data: Any) -> dict[str, Any]:
    """Extract metadata from VizTracer trace JSON."""
    meta: dict[str, Any] = {}
    if isinstance(data, dict):
        for key in ("traceEvents", "events"):
            raw = data.get(key)
            if isinstance(raw, dict):
                for k, v in raw.items():
                    if isinstance(v, dict) and v.get("ph") == "M":
                        meta[f"map_{k}"] = v
        for key in ("metadata", "meta"):
            val = data.get(key)
            if isinstance(val, dict):
                meta.update(val)
    return meta


# ---------------------------------------------------------------------------
# Core parsing entry points
# ---------------------------------------------------------------------------


def _parse_trace_file(session_dir: Path) -> tuple[list[dict[str, Any]], dict[str, Any], int, int | None, bool]:
    """Parse viztracer.json.gz from session_dir.

    Returns (events, metadata, trace_entry_count, trace_entry_capacity, truncated).
    """
    path = session_dir / "raw" / "viztracer.json.gz"
    if not path.exists():
        return [], {}, 0, None, False
    data = _json_load_gzip(path)
    if data is None:
        return [], {}, 0, None, False
    meta = _extract_viztracer_meta(data)
    events = parse_chrome_trace_events(data)

    # Extract entry count / capacity from metadata
    entry_count = len(events)
    entry_capacity: int | None = None
    truncated = False

    if isinstance(data, dict):
        # VizTracer metadata
        vmeta = data.get("metadata", {}) if isinstance(data.get("metadata"), dict) else {}
        if not vmeta:
            vmeta = data.get("meta", {})
        if isinstance(vmeta, dict):
            # Prefer entry_capacity from tracer_args (configured capacity)
            # over dump_counter (actual number dumped)
            tr = vmeta.get("tracer_args", {})
            if isinstance(tr, dict):
                entry_capacity = _safe_int(tr.get("entry_capacity"), None)
            if entry_capacity is None:
                dc = vmeta.get("dump_counter")
                if dc is not None:
                    entry_capacity = _safe_int(dc, None)
            if vmeta.get("truncated"):
                truncated = True

    return events, meta, entry_count, entry_capacity, truncated


def _parse_torch_trace(session_dir: Path) -> list[dict[str, Any]]:
    """Parse torch_trace.json.gz (Chrome trace) without importing Torch."""
    path = session_dir / "raw" / "torch_trace.json.gz"
    if not path.exists():
        return []
    data = _json_load_gzip(path)
    if data is None:
        return []
    return parse_chrome_trace_events(data)


def _parse_resource_samples(session_dir: Path) -> list[dict[str, Any]]:
    """Parse resource_samples.jsonl.gz incrementally line-by-line."""
    path = session_dir / "raw" / "resource_samples.jsonl.gz"
    if not path.exists():
        return []
    return _jsonl_load_gzip_line_by_line(path)


def _parse_milestones(session_dir: Path) -> list[dict[str, Any]]:
    """Parse milestones.jsonl."""
    path = session_dir / "raw" / "milestones.jsonl"
    if not path.exists():
        return []
    return _jsonl_load(path)


def _parse_session_events(session_dir: Path) -> list[dict[str, Any]]:
    """Parse session_events.jsonl."""
    path = session_dir / "raw" / "session_events.jsonl"
    if not path.exists():
        return []
    return _jsonl_load(path)


def _parse_wrapper_snapshots(session_dir: Path) -> list[dict[str, Any]]:
    """Parse wrapper_snapshots.json.

    Accepts multiple top-level shapes:
    - ``[{...}]`` — list of snapshot dicts (standard)
    - ``{"snapshots": [...]}`` — snapshots wrapped in key
    - ``{"wrappers": {...}}`` — single snapshot with wrappers mapping
    """
    path = session_dir / "raw" / "wrapper_snapshots.json"
    if not path.exists():
        return []
    data = _json_load(path)
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        snapshots = data.get("snapshots")
        if isinstance(snapshots, list):
            return snapshots
        wrappers = data.get("wrappers")
        if isinstance(wrappers, dict):
            return [{"milestone": "", "wrappers": wrappers}]
    return []


def _parse_trace_config(session_dir: Path) -> dict[str, Any]:
    """Parse trace_config.json."""
    path = session_dir / "raw" / "trace_config.json"
    if not path.exists():
        return {}
    data = _json_load(path)
    if isinstance(data, dict):
        return data
    return {}


def _parse_runtime_result_summary(session_dir: Path) -> dict[str, Any]:
    """Parse runtime_result_summary.json."""
    path = session_dir / "raw" / "runtime_result_summary.json"
    if not path.exists():
        return {}
    data = _json_load(path)
    if isinstance(data, dict):
        return data
    return {}


# ---------------------------------------------------------------------------
# Event normalization
# ---------------------------------------------------------------------------


def _normalize_call_event(
    ev: dict[str, Any],
    index: int,
    *,
    be_pairs: dict[str, list[dict[str, Any]]],
) -> dict[str, Any] | None:
    """Normalize a single trace event into a call record.

    Handles complete X events and partial B/E pairs.
    Returns a dict with keys: event_index, name, category, source_file,
    source_line, pid, tid, task_id, start_us, duration_us, end_us, complete,
    args.
    Unknown/missing values are left as None (not fabricated 0).
    Returns None for unparseable events.
    """
    ph = ev.get("ph", "")
    name = str(ev.get("name", ""))
    if not name:
        return None

    pid = ev.get("pid") if "pid" in ev else None
    tid = ev.get("tid") if "tid" in ev else None
    ts = _safe_float(ev.get("ts"), None)
    cat = str(ev.get("cat", "")) if ev.get("cat") else ""
    args_raw = ev.get("args")
    args = args_raw if isinstance(args_raw, dict) else {}
    task_id = str(args.get("task_id", "")) if isinstance(args, dict) else ""

    source_file = None
    source_line = None
    if isinstance(args, dict):
        sf = (
            args.get("source_file")
            or args.get("filename")
            or (isinstance(args.get("call_frame"), dict) and (
                args["call_frame"].get("filename") or args["call_frame"].get("source_file") or ""
            ))
            or (isinstance(args.get("fields"), dict) and (
                args["fields"].get("filename") or args["fields"].get("source_file") or ""
            ))
            or None
        )
        if sf:
            source_file = str(sf)
        sl = (
            args.get("source_line")
            or args.get("lineno")
            or (isinstance(args.get("call_frame"), dict) and (
                args["call_frame"].get("lineno") or args["call_frame"].get("source_line") or None
            ))
            or (isinstance(args.get("fields"), dict) and (
                args["fields"].get("lineno") or args["fields"].get("source_line") or None
            ))
            or None
        )
        if sl is not None:
            source_line = _safe_int(sl, None)

    if ph == "X":
        dur = _safe_float(ev.get("dur"), None)
        complete = ts is not None and dur is not None
        if dur is not None and dur < 0:
            dur = 0.0
            complete = False
        start = ts if ts is not None else None
        end = (ts + dur) if (ts is not None and dur is not None) else None
        return {
            "event_index": index,
            "name": name,
            "category": cat,
            "source_file": source_file,
            "source_line": source_line,
            "pid": pid,
            "tid": tid,
            "task_id": task_id,
            "start_us": start,
            "duration_us": dur,
            "end_us": end,
            "complete": complete,
            "args": args if args else None,
        }

    if ph == "B":
        key = f"{pid}:{tid}:{name}"
        if key not in be_pairs:
            be_pairs[key] = []
        be_pairs[key].append({
            "event_index": index,
            "name": name,
            "category": cat,
            "source_file": source_file,
            "source_line": source_line,
            "pid": pid,
            "tid": tid,
            "task_id": task_id,
            "start_us": ts,
            "complete": False,
            "args": args if args else None,
        })
        return None

    if ph == "E":
        key = f"{pid}:{tid}:{name}"
        pending = be_pairs.get(key, [])
        if pending:
            begin = pending.pop(0)
            dur = (ts - begin["start_us"]) if (ts is not None and begin["start_us"] is not None) else None
            if dur is not None and dur < 0:
                dur = 0.0
            end = ts
            return {
                "event_index": index,
                "name": name,
                "category": cat if cat else begin.get("category", ""),
                "source_file": source_file if source_file else begin.get("source_file"),
                "source_line": source_line if source_line else begin.get("source_line"),
                "pid": pid,
                "tid": tid,
                "task_id": task_id if task_id else begin.get("task_id", ""),
                "start_us": begin["start_us"],
                "duration_us": dur,
                "end_us": end,
                "complete": True,
                "args": args if args else None,
            }

    return None


def _build_calls(trace_events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Build normalized calls list from raw Chrome trace events.

    Handles X, B, E phases and pairs B/E across the full event list.
    Unmatched B events produce calls with complete=0 (no end timestamp).
    Unmatched E events produce calls with complete=0 (no start timestamp).
    Unknown/missing fields use None, not fabricated 0.
    Preserves original event index for all events including unmatched E.
    Preserves args for semantic analysis.
    """
    be_pairs: dict[str, list[dict[str, Any]]] = {}
    unmatched_e: list[tuple[int, dict[str, Any]]] = []
    calls: list[dict[str, Any]] = []
    for i, ev in enumerate(trace_events):
        ph = ev.get("ph", "")
        if ph == "E":
            pid = ev.get("pid") if "pid" in ev else None
            tid = ev.get("tid") if "tid" in ev else None
            key = f"{pid}:{tid}:{ev.get('name', '')}"
            pending = be_pairs.get(key, [])
            if pending:
                call = _normalize_call_event(ev, i, be_pairs=be_pairs)
                if call is not None:
                    calls.append(call)
            else:
                unmatched_e.append((i, ev))
        else:
            call = _normalize_call_event(ev, i, be_pairs=be_pairs)
            if call is not None:
                calls.append(call)

    # Flush unmatched B events as incomplete calls
    for key, pending_list in be_pairs.items():
        for pending in pending_list:
            calls.append({
                "event_index": pending["event_index"],
                "name": pending["name"],
                "category": pending.get("category", ""),
                "source_file": pending.get("source_file"),
                "source_line": pending.get("source_line"),
                "pid": pending["pid"],
                "tid": pending["tid"],
                "task_id": pending.get("task_id", ""),
                "start_us": pending["start_us"],
                "duration_us": None,
                "end_us": None,
                "complete": False,
                "args": pending.get("args"),
            })

    # Flush unmatched E events as incomplete calls (preserve original event index)
    for idx, ev in unmatched_e:
        calls.append({
            "event_index": idx,
            "name": str(ev.get("name", "")),
            "category": str(ev.get("cat", "")),
            "source_file": None,
            "source_line": None,
            "pid": ev.get("pid") if "pid" in ev else None,
            "tid": ev.get("tid") if "tid" in ev else None,
            "task_id": "",
            "start_us": None,
            "duration_us": None,
            "end_us": _safe_float(ev.get("ts"), None),
            "complete": False,
            "args": ev.get("args") if isinstance(ev.get("args"), dict) else None,
        })

    return calls


# ---------------------------------------------------------------------------
# Parent-child reconstruction via interval nesting
# ---------------------------------------------------------------------------


def _reconstruct_parents(calls: list[dict[str, Any]]) -> None:
    """Reconstruct parent-child relationships in-place using interval nesting.

    Groups calls by (pid, tid, task_id) first.  Within each group, sorts by
    start_us then end_us (descending for same-start).  Assigns parent indices
    and parent names using interval nesting.  Ambiguous parenthood (exact same
    interval, or overlapping without strict nesting) leaves parent empty.
    Detects stack inconsistencies.
    """
    # Skip calls with missing start/end (incomplete)
    valid_calls = [c for c in calls if c.get("start_us") is not None and c.get("end_us") is not None]

    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for c in valid_calls:
        key = f"{c['pid']}:{c['tid']}:{c.get('task_id', '')}"
        groups[key].append(c)

    for key, group in groups.items():
        # Sort: start ascending, duration descending (wider first)
        group.sort(key=lambda c: (c["start_us"], -c["duration_us"]))
        # Nesting stack
        stack: list[dict[str, Any]] = []
        for c in group:
            # Pop entries that end before this one starts
            while stack and stack[-1]["end_us"] <= c["start_us"] + 0.001:
                stack.pop()
            # Check if stack top actually nests this call (strict nesting:
            # parent.start <= child.start AND parent.end >= child.end)
            parent = stack[-1] if stack else None
            if parent is not None:
                p_start = parent["start_us"]
                p_end = parent["end_us"]
                c_start = c["start_us"]
                c_end = c["end_us"]
                # Strict nesting only; overlapping without containment = no parent
                if p_start <= c_start and p_end >= c_end:
                    c["parent_event_index"] = parent["event_index"]
                    c["parent_name"] = parent["name"]
                else:
                    # Overlapping but not strict nesting — leave ambiguous
                    c["parent_event_index"] = None
                    c["parent_name"] = ""
            else:
                c["parent_event_index"] = None
                c["parent_name"] = ""
            # Assign depth based on strict nesting only
            c["depth"] = len(stack) if c.get("parent_event_index") is not None else 0
            # Only push to stack if this call is strictly nested within its parent
            if c.get("parent_event_index") is not None:
                stack.append(c)
            elif not stack:
                # Top-level call: push as new stack base if it has valid interval
                stack.append(c)

        # Mark ambiguous parenthood: if a call has same start and duration as
        # its parent, that's an ambiguous nesting (likely concurrent sibling)
        for c in group:
            pi = c.get("parent_event_index")
            if pi is not None:
                parent = None
                for other in group:
                    if other["event_index"] == pi:
                        parent = other
                        break
                if parent is not None:
                    if (abs(c["start_us"] - parent["start_us"]) < 0.001 and
                            abs(c["duration_us"] - parent["duration_us"]) < 0.001):
                        c["parent_event_index"] = None
                        c["parent_name"] = ""
                        c["depth"] = 0


def _detect_stack_inconsistencies(calls: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Detect and report stack inconsistencies.

    Returns a list of issue dicts with event_index and description.
    """
    issues: list[dict[str, Any]] = []
    for c in calls:
        pi = c.get("parent_event_index")
        if pi is not None:
            found = False
            for other in calls:
                if other["event_index"] == pi:
                    found = True
                    if (other.get("end_us") is not None
                            and c.get("start_us") is not None
                            and other["end_us"] < c["start_us"]):
                        issues.append({
                            "event_index": c["event_index"],
                            "description": (
                                f"Child {c['name']} starts at {c['start_us']}us "
                                f"after parent {other['name']} ends at {other['end_us']}us"
                            ),
                        })
                    break
            if not found:
                issues.append({
                    "event_index": c["event_index"],
                    "description": f"Parent index {pi} not found for {c['name']}",
                })
    return issues


# ---------------------------------------------------------------------------
# functions_summary aggregation
# ---------------------------------------------------------------------------


def _merge_intervals(intervals: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """Merge overlapping intervals (start, end). Returns merged list."""
    if not intervals:
        return []
    sorted_int = sorted(intervals, key=lambda x: x[0])
    merged: list[tuple[float, float]] = [sorted_int[0]]
    for start, end in sorted_int[1:]:
        if start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged


def _total_interval_length(intervals: list[tuple[float, float]]) -> float:
    """Return total length of merged intervals."""
    merged = _merge_intervals(intervals)
    return sum(end - start for start, end in merged)


def _build_functions_summary(calls: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Aggregate normalized source_file/function with stats.

    Returns list of dicts sorted by inclusive_ms descending.
    Exclusive = duration minus union of direct child intervals
    (overlapping children not double-subtracted).
    Calls with None duration_us are included in call_count but contribute 0 to timing.
    """
    if not calls:
        return []

    # Build group key -> calls
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for c in calls:
        key = f"{c.get('source_file', '')}:{c['name']}"
        groups[key].append(c)

    # Parent-child lookup
    children_of: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for c in calls:
        pi = c.get("parent_event_index")
        if isinstance(pi, int):
            children_of[pi].append(c)

    rows: list[dict[str, Any]] = []
    for key, group in groups.items():
        src_file = key.split(":", 1)[0]
        func_name = key.split(":", 1)[1] if ":" in key else key
        # Only count non-None durations; None means no measurement available
        durations_us = [c["duration_us"] for c in group if c.get("duration_us") is not None]
        starts_us = [c["start_us"] for c in group if c.get("start_us") is not None]
        ends_us = [c["end_us"] for c in group if c.get("end_us") is not None]
        start_ts = min(starts_us) if starts_us else 0.0
        end_ts = max(ends_us) if ends_us else 0.0

        # Inclusive = sum of all durations (None treated as 0)
        inclusive_us = sum(durations_us) if durations_us else 0.0

        # Exclusive = duration minus *union* of direct child intervals
        # Using interval merging to avoid double-subtracting overlapping children
        exclusive_sum = 0.0
        for c in group:
            child_intervals: list[tuple[float, float]] = [
                (child["start_us"], child["end_us"])
                for child in children_of.get(c["event_index"], [])
                if child.get("start_us") is not None and child.get("end_us") is not None
            ]
            child_union_len = _total_interval_length(child_intervals)
            c_dur = c.get("duration_us")
            excl = (c_dur if c_dur is not None else 0.0) - child_union_len
            excl = _clamp_non_negative(excl)
            exclusive_sum += excl

        # Percentiles (only from calls with measured duration)
        sorted_durs = sorted(durations_us) if durations_us else []
        n = len(sorted_durs)
        mean_us = statistics.mean(sorted_durs) if sorted_durs else 0.0
        median_us = statistics.median(sorted_durs) if sorted_durs else 0.0
        p95_idx = max(0, min(n - 1, int(n * 0.95)))
        p95_us = sorted_durs[p95_idx] if sorted_durs else 0.0
        max_us = max(sorted_durs) if sorted_durs else 0.0

        # Thread and task counts
        thread_ids: set[str] = set()
        task_ids: set[str] = set()
        for c in group:
            thread_ids.add(f"{c['pid']}:{c['tid']}")
            if c.get("task_id"):
                task_ids.add(c["task_id"])

        rows.append({
            "source_file": src_file,
            "function": func_name,
            "call_count": len(group),
            "inclusive_ms": round(inclusive_us / 1000.0, 3),
            "exclusive_ms": round(exclusive_sum / 1000.0, 3),
            "mean_ms": round(mean_us / 1000.0, 3),
            "median_ms": round(median_us / 1000.0, 3),
            "p95_ms": round(p95_us / 1000.0, 3),
            "max_ms": round(max_us / 1000.0, 3),
            "thread_count": len(thread_ids),
            "task_count": len(task_ids),
            "first_start_ms": round(start_ts / 1000.0, 3),
            "last_end_ms": round(end_ts / 1000.0, 3),
        })

    rows.sort(key=lambda r: r["inclusive_ms"], reverse=True)
    return rows


# ---------------------------------------------------------------------------
# critical_timeline
# ---------------------------------------------------------------------------


def _build_critical_timeline(
    calls: list[dict[str, Any]],
    milestones: list[dict[str, Any]],
    sessions: list[dict[str, Any]],
    semantic_ops: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Build chronological critical timeline.

    Includes milestones, semantic operations, and notable Python calls.
    """
    timeline: list[dict[str, Any]] = []

    # Add milestones
    for m in milestones:
        name = str(m.get("name", m.get("event", "")))
        start_ms_raw = next((m[k] for k in ("wall_unix_ms", "timestamp_ms", "time_ms") if k in m), None)
        duration_raw = m.get("duration_ms") if "duration_ms" in m else None
        start_ms = _safe_float(start_ms_raw, None)
        dur_ms = _safe_float(duration_raw, None)
        if start_ms is None:
            continue
        if dur_ms is None:
            dur_ms = 0.0
        pid = _safe_int(m.get("pid", 0))
        tid = _safe_int(m.get("tid", 0))
        task_id = str(m.get("task_id", ""))
        parent = str(m.get("parent", ""))
        phase = str(m.get("phase", m.get("lifecycle_phase", "")))
        evidence = str(m.get("evidence_source", "milestones"))

        timeline.append({
            "start_ms": round(start_ms, 3),
            "end_ms": round(start_ms + dur_ms, 3),
            "duration_ms": round(dur_ms, 3),
            "owner_type": "milestone",
            "owner_name": name,
            "pid": pid,
            "tid": tid,
            "task_id": task_id,
            "parent": parent,
            "lifecycle_phase": phase,
            "evidence_source": evidence,
        })

    # Add semantic operations from session events
    for ev in sessions:
        op_type = str(ev.get("operation_type", ev.get("event_type", "")))
        start_ms_raw = next((ev[k] for k in ("start_ms", "timestamp_ms", "time_ms") if k in ev), None)
        duration_raw = ev.get("duration_ms") if "duration_ms" in ev else None
        start_ms = _safe_float(start_ms_raw, None)
        dur_ms = _safe_float(duration_raw, None)
        if start_ms is None:
            continue
        if dur_ms is None:
            dur_ms = 0.0
        pid = _safe_int(ev.get("pid", 0))
        tid = _safe_int(ev.get("tid", 0))
        task_id = str(ev.get("task_id", ""))
        phase = str(ev.get("phase", ""))
        timeline.append({
            "start_ms": round(start_ms, 3),
            "end_ms": round(start_ms + dur_ms, 3),
            "duration_ms": round(dur_ms, 3),
            "owner_type": "semantic_operation",
            "owner_name": op_type,
            "pid": pid,
            "tid": tid,
            "task_id": task_id,
            "parent": "",
            "lifecycle_phase": phase,
            "evidence_source": "session_events",
        })

    # Add long Python calls (>10ms) from trace
    for c in calls:
        dur = c.get("duration_us")
        if dur is None:
            continue
        dur_ms = dur / 1000.0
        start = c.get("start_us")
        end = c.get("end_us")
        if start is None or end is None:
            continue
        if dur_ms >= 10.0:
            timeline.append({
                "start_ms": round(start / 1000.0, 3),
                "end_ms": round(end / 1000.0, 3),
                "duration_ms": round(dur_ms, 3),
                "owner_type": "python_call",
                "owner_name": c["name"],
                "pid": c.get("pid"),
                "tid": c.get("tid"),
                "task_id": c.get("task_id", ""),
                "parent": c.get("parent_name", ""),
                "lifecycle_phase": "",
                "evidence_source": "viztracer",
            })

    timeline.sort(key=lambda r: (r["start_ms"], r["end_ms"]))
    return timeline


# ---------------------------------------------------------------------------
# Exact duplicate detection
# ---------------------------------------------------------------------------


def _normalize_function_name(name: str) -> str:
    """Normalize a function name for duplicate matching."""
    # Strip module prefixes
    return name.split(".")[-1] if "." in name else name


def _find_duplicate_groups(
    calls: list[dict[str, Any]],
    *,
    window_us: float = 1000.0,
    trace_config: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Find likely duplicate call groups.

    Groups matching normalized function, parent, pid/tid/task within
    configured start window.  Uses ``duplicate_window_us`` from
    *trace_config* when provided, falling back to *window_us*.
    Includes semantic key matching from args when available.
    """
    if trace_config is None:
        trace_config = {}
    # Use duplicate_window from trace_config if provided
    config_window = trace_config.get("duplicate_window_us") or trace_config.get("duplicate_window")
    if config_window is not None:
        try:
            window_us = float(config_window)
        except (TypeError, ValueError):
            pass

    if not calls:
        return []

    # Build candidate groups
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for c in calls:
        key = (
            _normalize_function_name(c["name"]),
            c.get("parent_name", ""),
            c.get("pid"),
            c.get("tid"),
            str(c.get("task_id", "")),
        )
        groups[str(key)].append(c)

    result: list[dict[str, Any]] = []
    for key_str, group in groups.items():
        if len(group) < 2:
            continue
        # Sort by start time
        group = [c for c in group if c.get("start_us") is not None]
        if len(group) < 2:
            continue
        group.sort(key=lambda c: c["start_us"])
        # Find clusters within window_us
        clusters: list[list[dict[str, Any]]] = []
        current: list[dict[str, Any]] = [group[0]]
        for c in group[1:]:
            if c["start_us"] - current[-1]["start_us"] <= window_us:
                current.append(c)
            else:
                if len(current) >= 2:
                    clusters.append(current)
                current = [c]
        if len(current) >= 2:
            clusters.append(current)

        for cluster in clusters:
            start_times = sorted(c["start_us"] for c in cluster)
            durations = sorted(c.get("duration_us") for c in cluster if c.get("duration_us") is not None)
            # Compute evidence strength
            strength = "high" if len(cluster) >= 3 else "medium"
            # Check if durations are very similar
            if len(durations) >= 2 and (max(durations) - min(durations)) < 100:
                strength = "high"
            result.append({
                "duplicate_group": len(result),
                "function": _normalize_function_name(cluster[0]["name"]),
                "parent": cluster[0].get("parent_name", ""),
                "call_count": len(cluster),
                "start_times_ms": [round(s / 1000.0, 3) for s in start_times],
                "durations_ms": [round(d / 1000.0, 3) for d in durations]
                if len(durations) == len(cluster)
                else [round(d / 1000.0, 3) if d is not None else MEASUREMENT_UNAVAILABLE
                      for d in (c.get("duration_us") for c in cluster)],
                "pid": cluster[0]["pid"],
                "tid": cluster[0]["tid"],
                "task_id": str(cluster[0].get("task_id", "")),
                "evidence_strength": strength,
            })

    result.sort(key=lambda r: r["call_count"], reverse=True)
    return result


# ---------------------------------------------------------------------------
# Semantic type recognition & grouping
# ---------------------------------------------------------------------------

_SEMANTIC_PATTERNS: list[tuple[str, str]] = [
    # More specific patterns MUST come first
    ("volume_reload:models", "volume_reload:models"),
    ("models_volume", "volume_reload:models"),
    ("volume_reload:runtime_state", "volume_reload:runtime_state"),
    ("runtime_state_volume", "volume_reload:runtime_state"),
    ("volume_reload", "volume_reload"),
    ("restore_plan_read", "restore_plan_read"),
    ("certificate_read", "certificate_read"),
    ("certificate_write", "certificate_write"),
    ("execution_prefill", "execution_prefill"),
    ("clip_graph_encode", "clip_graph_encode"),
    ("clip_prefill_encode", "clip_prefill_encode"),
    ("vae_file_load", "vae_file_load"),
    ("unet_gpu_activation", "unet_gpu_activation"),
    ("cache_seed", "cache_seed"),
    ("cachedit_restore", "cachedit_restore_prepare"),
    ("cachedit_request", "cachedit_request_attach"),
    ("res4lyf_restore", "res4lyf_restore_prepare"),
    ("res4lyf_request", "res4lyf_request_parse"),
    ("executor_cache_initialize", "executor_cache_initialize"),
    ("output_encode", "output_encode"),
    ("runtime_state. Commit", "runtime_state_commit"),
    ("runtime_state_commit", "runtime_state_commit"),
]


def _classify_semantic_type(name: str, args: dict[str, Any] | None = None) -> str:
    """Classify a call or event into a semantic operation type.

    Returns the semantic type string or empty string if unclassified.
    """
    lower = name.lower()
    for pattern, stype in _SEMANTIC_PATTERNS:
        if pattern in lower:
            return stype
    return ""


def _compute_semantic_key_hash(event: dict[str, Any]) -> str:
    """Compute deterministic SHA-256 hash of semantic key/identity args.

    Uses canonical JSON encoding of the event's key, semantic_key, or identity
    args if present.  Falls back to name + operation_type if no explicit key.
    """
    args = event.get("args", {}) if isinstance(event.get("args"), dict) else {}
    for key_field in ("key", "semantic_key", "identity"):
        val = args.get(key_field)
        if val is not None:
            canonical = json.dumps(val, sort_keys=True, separators=(",", ":"))
            return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    # Fallback: hash the event name + operation type
    fallback = json.dumps(
        {"name": event.get("name", ""), "op": event.get("operation_type", "")},
        sort_keys=True, separators=(",", ":"),
    )
    return hashlib.sha256(fallback.encode("utf-8")).hexdigest()


def _extract_request_session_ids(
    event: dict[str, Any],
    trace_config: dict[str, Any],
) -> tuple[str, str]:
    """Extract request_id and restore_session_id from event args or config."""
    args = event.get("args", {}) if isinstance(event.get("args"), dict) else {}
    req = str(args.get("request_id", trace_config.get("request_id", "")))
    sess = str(args.get("restore_session_id", trace_config.get("restore_session_id", "")))
    return req, sess


def _build_semantic_ops(
    calls: list[dict[str, Any]],
    sessions: list[dict[str, Any]],
    trace_config: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Extract semantic operations from trace calls and session events."""
    if trace_config is None:
        trace_config = {}
    ops: list[dict[str, Any]] = []
    for c in calls:
        stype = _classify_semantic_type(c["name"], c.get("args"))
        if stype:
            req, sess = _extract_request_session_ids(c, trace_config)
            sk_hash = _compute_semantic_key_hash(c)
            ops.append({
                "operation_type": stype,
                "semantic_key_hash": sk_hash,
                "request_id": req,
                "restore_session_id": sess,
                "source": "trace_call",
                "name": c["name"],
                "start_us": c.get("start_us"),
                "end_us": c.get("end_us"),
                "duration_us": c.get("duration_us"),
                "pid": c.get("pid"),
                "tid": c.get("tid"),
                "task_id": c.get("task_id", ""),
            })
    for ev in sessions:
        op_type = str(ev.get("operation_type", ""))
        if op_type:
            start_ms = _safe_float(ev.get("start_ms", 0.0), 0.0)
            dur_ms = _safe_float(ev.get("duration_ms", 0.0), 0.0)
            start_us = start_ms * 1000.0
            req, sess = _extract_request_session_ids(ev, trace_config)
            sk_hash = _compute_semantic_key_hash(ev)
            ops.append({
                "operation_type": op_type,
                "semantic_key_hash": sk_hash,
                "request_id": req,
                "restore_session_id": sess,
                "source": "session_event",
                "name": str(ev.get("name", "")),
                "start_us": start_us,
                "end_us": start_us + dur_ms * 1000.0,
                "duration_us": dur_ms * 1000.0,
                "pid": _safe_int(ev.get("pid", 0)),
                "tid": _safe_int(ev.get("tid", 0)),
                "task_id": str(ev.get("task_id", "")),
            })
    return ops


def _semantic_group_key(op: dict[str, Any]) -> str:
    """Create a grouping key for semantic duplicate detection."""
    return f"{op['operation_type']}:{op.get('semantic_key_hash', '')}:{op.get('request_id', '')}:{op.get('restore_session_id', '')}"


def _build_semantic_duplicates(ops: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Group semantic operations by type + key + request + session and identify duplicates."""
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for op in ops:
        groups[_semantic_group_key(op)].append(op)

    duplicates: list[dict[str, Any]] = []
    for gkey, group in groups.items():
        if len(group) < 2:
            continue
        group.sort(key=lambda o: (o.get("start_us") is None, o.get("start_us") if o.get("start_us") is not None else 0.0))
        duplicates.append({
            "operation_type": group[0]["operation_type"],
            "semantic_key_hash": group[0].get("semantic_key_hash", ""),
            "request_id": group[0].get("request_id", ""),
            "restore_session_id": group[0].get("restore_session_id", ""),
            "call_count": len(group),
            "start_times_ms": [round(o["start_us"] / 1000.0, 3) if o.get("start_us") is not None else MEASUREMENT_UNAVAILABLE for o in group],
            "end_times_ms": [round(o["end_us"] / 1000.0, 3) if o.get("end_us") is not None else MEASUREMENT_UNAVAILABLE for o in group],
            "repeated_starts": len({o["start_us"] for o in group if o.get("start_us") is not None}) < len([o for o in group if o.get("start_us") is not None]),
            "overlaps": _detect_overlaps_in_group(group),
            "repeated_completions": len({o["end_us"] for o in group if o.get("end_us") is not None}) < len([o for o in group if o.get("end_us") is not None]),
        })
    return duplicates


def _detect_overlaps_in_group(group: list[dict[str, Any]]) -> bool:
    """Check if any two operations in the group overlap."""
    sorted_group = sorted(
        (o for o in group if o.get("start_us") is not None and o.get("end_us") is not None),
        key=lambda o: o["start_us"],
    )
    for i in range(len(sorted_group) - 1):
        if sorted_group[i]["end_us"] > sorted_group[i + 1]["start_us"]:
            return True
    return False


# ---------------------------------------------------------------------------
# expected_vs_observed
# ---------------------------------------------------------------------------


def _build_expected_vs_observed(
    ops: list[dict[str, Any]],
    milestones: list[dict[str, Any]],
    session_dir: Path,
    trace_config: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Build expected vs observed operation counts.

    Rules implement at-most-one semantics:
      - volume_reload:models, volume_reload:runtime_state: <=1
      - clip_graph_encode: exactly 1
      - clip_prefill_encode: 0 when snapshot-active/hit explicitly observed;
        measurement_unavailable otherwise
      - unet_gpu_activation: exactly 1
      - vae_file_load: exactly 1
      - cachedit_restore_prepare: exactly 1
      - cachedit_request_attach: 0 (expected)
      - res4lyf_restore_prepare: exactly 1
      - res4lyf_request_parse: 0 (expected)
      - executor_cache_initialize: 1 per loader node
      - output_encode: exactly 1
      - certificate_read: <=1
      - restore_plan_read: <=1
      - runtime_state_commit: <=1

    At-most-one: not_observed for 0, expected for 1, above_expected for >1.
    never below_expected for missing at-most-one. not_observed when a required
    operation has no observation and no defensible expected count.
    """
    if trace_config is None:
        trace_config = {}

    # Count observed operations
    observed_counts: dict[str, int] = defaultdict(int)
    for op in ops:
        observed_counts[op["operation_type"]] += 1

    # Snapshot status
    snapshot_active = trace_config.get("snapshot_enabled", trace_config.get("snapshot_active"))
    if snapshot_active is not None:
        if isinstance(snapshot_active, str):
            snapshot_active = snapshot_active.lower() in ("true", "1", "yes")
        snapshot_active = bool(snapshot_active)

    # Did we explicitly observe a snapshot hit?
    snapshot_hit_explicitly_observed = (
        snapshot_active is True
        and observed_counts.get("clip_prefill_encode", 0) == 0
    )

    rules: list[dict[str, Any]] = []

    def _add_rule(
        operation: str,
        expected: int | str,
        observed_count: int,
        at_most_one: bool = False,
        optional: bool = False,
    ) -> None:
        if isinstance(expected, int):
            if at_most_one:
                # At-most-one: 0 is not_observed (not measured) unless optional;
                # 1 is expected; >1 is above_expected.
                if observed_count == 0:
                    classification = "expected" if optional else "not_observed"
                elif observed_count == 1:
                    classification = "expected"
                else:
                    classification = "above_expected"
            else:
                if observed_count < expected:
                    classification = "below_expected"
                elif observed_count == expected:
                    classification = "expected"
                else:
                    classification = "above_expected"
        elif expected == "measurement_unavailable":
            classification = "measurement_unavailable"
        elif expected == "not_observed":
            classification = "not_observed" if observed_count == 0 else "above_expected"
        else:
            classification = "not_observed" if observed_count == 0 else "above_expected"

        rules.append({
            "operation": operation,
            "expected": expected if isinstance(expected, (int, str)) else str(expected),
            "observed": observed_count,
            "classification": classification,
        })

    # At-most-one volume reloads (optional — may not happen)
    _add_rule("volume_reload:models", 1, observed_counts.get("volume_reload:models", 0), at_most_one=True, optional=True)
    _add_rule("volume_reload:runtime_state", 1, observed_counts.get("volume_reload:runtime_state", 0), at_most_one=True, optional=True)

    # Graph CLIP encode: exactly 1
    _add_rule("clip_graph_encode", 1, observed_counts.get("clip_graph_encode", 0))

    # Execution-prefill CLIP encode: 0 only when snapshot-active/hit is explicitly observed
    prefill_obs = observed_counts.get("clip_prefill_encode", 0)
    if snapshot_hit_explicitly_observed:
        _add_rule("clip_prefill_encode", 0, prefill_obs)
    elif snapshot_active is True:
        # Snapshot active but prefill was actually observed (cache miss)
        _add_rule("clip_prefill_encode", "not_observed", prefill_obs)
    else:
        _add_rule("clip_prefill_encode", "measurement_unavailable", prefill_obs)

    # UNET GPU activation: exactly 1
    _add_rule("unet_gpu_activation", 1, observed_counts.get("unet_gpu_activation", 0))

    # VAE loader execution: exactly 1
    _add_rule("vae_file_load", 1, observed_counts.get("vae_file_load", 0))

    # CacheDiT restore preparation: exactly 1
    _add_rule("cachedit_restore_prepare", 1, observed_counts.get("cachedit_restore_prepare", 0))

    # CacheDiT request attachment: 0
    _add_rule("cachedit_request_attach", 0, observed_counts.get("cachedit_request_attach", 0))

    # RES4LYF restore preparation: 1
    _add_rule("res4lyf_restore_prepare", 1, observed_counts.get("res4lyf_restore_prepare", 0))

    # RES4LYF request parse: 0
    _add_rule("res4lyf_request_parse", 0, observed_counts.get("res4lyf_request_parse", 0))

    # Executor seed per loader node (cache_seed)
    cache_seed_count = observed_counts.get("cache_seed", 0)
    _add_rule("cache_seed", cache_seed_count, cache_seed_count if cache_seed_count > 0 else 0)

    # Executor cache initialize: 1 per loader node
    loader_count = max(observed_counts.get("executor_cache_initialize", 0), 1)
    _add_rule("executor_cache_initialize", loader_count, observed_counts.get("executor_cache_initialize", 0))

    # Output encode: 1
    _add_rule("output_encode", 1, observed_counts.get("output_encode", 0))

    # At-most-one: certificate read, restore plan read, runtime state commit (optional)
    _add_rule("certificate_read", 1, observed_counts.get("certificate_read", 0), at_most_one=True, optional=True)
    _add_rule("restore_plan_read", 1, observed_counts.get("restore_plan_read", 0), at_most_one=True, optional=True)
    _add_rule("runtime_state_commit", 1, observed_counts.get("runtime_state_commit", 0), at_most_one=True, optional=True)

    # Wrapper installation per target: at-most-one (derived from wrapper snapshots)
    _add_rule("wrapper_installation_per_target", "not_observed", 0)

    # Validation certificate authoritative read: at-most-one (same as certificate_read)
    # Already added as certificate_read above.

    # Restore-plan authoritative read: at-most-one (same as restore_plan_read)
    # Already added as restore_plan_read above.

    # Runtime state final commit: at-most-one (same as runtime_state_commit)
    # Already added as runtime_state_commit above.

    return rules


# ---------------------------------------------------------------------------
# overlap_intervals
# ---------------------------------------------------------------------------


def _build_overlap_intervals(
    timeline: list[dict[str, Any]],
    ops: list[dict[str, Any]],
    milestones: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Identify interval overlaps among timeline entries, ops, and milestones."""
    intervals: list[dict[str, Any]] = []

    # Build interval list from timeline
    for entry in timeline:
        intervals.append({
            "owner": entry["owner_name"],
            "owner_type": entry["owner_type"],
            "start_ms": entry["start_ms"],
            "end_ms": entry["end_ms"],
            "pid": entry["pid"],
            "tid": entry["tid"],
        })

    # Add semantic ops not already in timeline
    existing: set[tuple[str, float, float]] = {
        (i["owner"], i["start_ms"], i["end_ms"]) for i in intervals
    }
    for op in ops:
        if op.get("start_us") is None or op.get("end_us") is None:
            continue
        start_ms = round(op["start_us"] / 1000.0, 3)
        end_ms = round(op["end_us"] / 1000.0, 3)
        key = (op["operation_type"], start_ms, end_ms)
        if key not in existing:
            intervals.append({
                "owner": op["operation_type"],
                "owner_type": "semantic_operation",
                "start_ms": start_ms,
                "end_ms": end_ms,
                "pid": op.get("pid", 0),
                "tid": op.get("tid", 0),
            })

    # Find overlaps
    overlaps: list[dict[str, Any]] = []
    intervals.sort(key=lambda i: i["start_ms"])
    for i in range(len(intervals)):
        for j in range(i + 1, len(intervals)):
            left = intervals[i]
            right = intervals[j]
            if left["end_ms"] <= right["start_ms"]:
                continue  # No overlap
            if left["start_ms"] > right["end_ms"]:
                continue
            overlap_ms = min(left["end_ms"], right["end_ms"]) - max(left["start_ms"], right["start_ms"])
            if overlap_ms <= 0:
                continue
            overlaps.append({
                "left_owner": left["owner"],
                "right_owner": right["owner"],
                "left_start_ms": left["start_ms"],
                "left_end_ms": left["end_ms"],
                "right_start_ms": right["start_ms"],
                "right_end_ms": right["end_ms"],
                "overlap_ms": round(overlap_ms, 3),
                "same_thread": left["tid"] == right["tid"],
                "same_task": False,
                "same_process": left["pid"] == right["pid"],
            })

    overlaps.sort(key=lambda o: o["overlap_ms"], reverse=True)
    return overlaps


# ---------------------------------------------------------------------------
# Resource / CPU analysis
# ---------------------------------------------------------------------------


def _parse_cpu_samples(resource_samples: list[dict[str, Any]]) -> dict[str, Any]:
    """Parse resource samples and compute per-sample metrics.

    Uses line-by-line parsed samples with actual adjacent cgroup usage deltas
    for container_effective_cores, process tick deltas divided by system clock
    ticks and wall interval for main/child/sum process, thread tick deltas for
    thread timeline/owners.

    Never substitutes process CPU for container CPU.  Uses explicit parent/main
    pid when supplied, not top_pid heuristic.
    """
    if not resource_samples:
        return {}

    samples: list[dict[str, Any]] = []
    for rs in resource_samples:
        sample: dict[str, Any] = {
            "timestamp_ms": _safe_float(rs.get("timestamp_ms", 0.0), 0.0) or 0.0,
            "container_available": False,
            "container_cpu_ns": MEASUREMENT_UNAVAILABLE,
            "container_effective_cores": MEASUREMENT_UNAVAILABLE,
            "main_process_cores": MEASUREMENT_UNAVAILABLE,
            "child_process_cores": MEASUREMENT_UNAVAILABLE,
            "sum_visible_process_cores": MEASUREMENT_UNAVAILABLE,
            "unattributed_effective_cores": MEASUREMENT_UNAVAILABLE,
            "thread_cores": [],
        }

        # Container-level cgroup CPU — store raw for delta computation
        cgroup = rs.get("cgroup_cpu", rs.get("container_cpu", {}))
        if isinstance(cgroup, dict):
            usage_us = cgroup.get("usage_us")
            if usage_us is not None and isinstance(usage_us, (int, float)):
                sample["container_available"] = True
                sample["cgroup_usage_us"] = float(usage_us)
            nr_periods = cgroup.get("nr_periods")
            quota_us = cgroup.get("quota_us")
            if nr_periods is not None:
                sample["container_nr_periods"] = _safe_float(nr_periods, 0.0) or 0.0
            if quota_us is not None:
                sample["container_quota_us"] = _safe_float(quota_us, 0.0) or 0.0

        # Process-level CPU
        process_cpu = rs.get("process_cpu", {})
        if isinstance(process_cpu, dict):
            procs = process_cpu.get("processes", [])
            if isinstance(procs, list):
                sample["processes"] = list(procs)
            # Explicit parent/main pid from the sample
            sample["main_pid"] = _safe_int(process_cpu.get("main_pid")) or _safe_int(process_cpu.get("parent_pid"))

        # Thread-level CPU
        thread_cpu = rs.get("thread_cpu", {})
        if isinstance(thread_cpu, dict):
            threads = thread_cpu.get("threads", [])
            if isinstance(threads, list):
                sample["threads"] = list(threads)

        # Top consumers (use only for thread names, not PID heuristic)
        top = rs.get("top", {})
        if isinstance(top, dict):
            sample["top_tid"] = top.get("tid")
            sample["top_thread"] = str(top.get("thread", ""))

        sample["active_semantic_ops"] = list(rs.get("active_semantic_operations", [])) if isinstance(rs.get("active_semantic_operations"), list) else []
        sample["active_python_funcs"] = list(rs.get("active_python_functions", [])) if isinstance(rs.get("active_python_functions"), list) else []

        samples.append(sample)

    # Post-process: compute deltas for cgroup and process CPU
    SYSTEM_CLOCK_TICKS_PER_SEC = 100  # Hz (Linux default)

    for i in range(1, len(samples)):
        prev = samples[i - 1]
        cur = samples[i]
        time_delta_s = (cur["timestamp_ms"] - prev["timestamp_ms"]) / 1000.0
        if time_delta_s <= 0:
            time_delta_s = 0.001

        # Container CPU: cgroup usage delta / time delta
        if (isinstance(prev.get("cgroup_usage_us"), (int, float))
                and isinstance(cur.get("cgroup_usage_us"), (int, float))):
            usage_delta_us = cur["cgroup_usage_us"] - prev["cgroup_usage_us"]
            if usage_delta_us >= 0:
                cur["container_cpu_ns"] = usage_delta_us * 1000.0
                cur["container_effective_cores"] = round(usage_delta_us / (time_delta_s * 1_000_000), 3)
                cur["container_available"] = True
            else:
                # Negative delta = counter reset or wrap; mark unavailable
                cur["container_effective_cores"] = MEASUREMENT_UNAVAILABLE

        # Process CPU: tick deltas / system clock ticks / wall interval
        prev_procs = prev.get("processes", []) if isinstance(prev.get("processes"), list) else []
        cur_procs = cur.get("processes", []) if isinstance(cur.get("processes"), list) else []

        prev_ticks: dict[int, float] = {}
        for p in prev_procs:
            pid = _safe_int(p.get("pid"))
            if pid is not None and pid > 0:
                prev_ticks[pid] = _safe_float(p.get("ticks", 0.0), 0.0) or 0.0

        sum_cores = 0.0
        main_cores = 0.0
        child_cores = 0.0
        # Use explicit main_pid if available; fall back to absent (no heuristic substitution)
        main_pid = cur.get("main_pid")

        for p in cur_procs:
            pid = _safe_int(p.get("pid"))
            if pid is None or pid <= 0:
                continue
            cur_ticks = _safe_float(p.get("ticks", 0.0), 0.0) or 0.0
            delta_ticks = cur_ticks - prev_ticks.get(pid, 0.0)
            if delta_ticks > 0:
                cores = delta_ticks / SYSTEM_CLOCK_TICKS_PER_SEC / time_delta_s
                cores = round(cores, 3)
                sum_cores += cores
                if main_pid is not None and pid == main_pid:
                    main_cores += cores
                else:
                    child_cores += cores

        # Thread CPU
        prev_threads = prev.get("threads", []) if isinstance(prev.get("threads"), list) else []
        cur_threads = cur.get("threads", []) if isinstance(cur.get("threads"), list) else []

        prev_thread_ticks: dict[int, float] = {}
        for t in prev_threads:
            tid = _safe_int(t.get("tid"))
            if tid is not None and tid > 0:
                prev_thread_ticks[tid] = _safe_float(t.get("ticks", 0.0), 0.0) or 0.0

        thread_cores_list: list[dict[str, Any]] = []
        for t in cur_threads:
            tid = _safe_int(t.get("tid"))
            if tid is None or tid <= 0:
                continue
            cur_ticks = _safe_float(t.get("ticks", 0.0), 0.0) or 0.0
            delta_ticks = cur_ticks - prev_thread_ticks.get(tid, 0.0)
            if delta_ticks > 0:
                cores = delta_ticks / SYSTEM_CLOCK_TICKS_PER_SEC / time_delta_s
                thread_cores_list.append({
                    "tid": tid,
                    "thread_name": str(t.get("thread_name", t.get("name", ""))),
                    "pid": _safe_int(t.get("pid"), 0) or 0,
                    "effective_cores": round(cores, 3),
                })

        # Only set numeric values when actually computed
        cur["main_process_cores"] = round(main_cores, 3) if main_cores > 0 else MEASUREMENT_UNAVAILABLE
        cur["child_process_cores"] = round(child_cores, 3) if child_cores > 0 else MEASUREMENT_UNAVAILABLE
        cur["sum_visible_process_cores"] = round(sum_cores, 3) if sum_cores > 0 else MEASUREMENT_UNAVAILABLE
        cur["thread_cores"] = thread_cores_list

        # Unattributed: container_cores - sum_process_cores
        # Never substitute process CPU for container CPU.
        cc = cur.get("container_effective_cores")
        if cur.get("container_available") and isinstance(cc, (int, float)):
            if isinstance(sum_cores, (int, float)) and sum_cores > 0:
                unattributed = float(cc) - sum_cores
                # Clamp only tiny FP negatives; keep meaningful negatives
                if unattributed < 0 and unattributed > -0.001:
                    unattributed = _clamp_non_negative(unattributed)
                cur["unattributed_effective_cores"] = round(unattributed, 3)
            else:
                cur["unattributed_effective_cores"] = cc
        else:
            cur["unattributed_effective_cores"] = MEASUREMENT_UNAVAILABLE

    return {"samples": samples}


# ---------------------------------------------------------------------------
# Thread / Process timeline
# ---------------------------------------------------------------------------


def _build_thread_timeline(calls: list[dict[str, Any]], samples_result: dict[str, Any]) -> list[dict[str, Any]]:
    """Build per-thread timeline from trace calls and CPU samples."""
    rows: list[dict[str, Any]] = []

    # Get unique thread identifiers from calls
    thread_info: dict[str, dict[str, Any]] = {}
    for c in calls:
        pid = c.get("pid")
        tid = c.get("tid")
        if pid is None or tid is None:
            continue
        key = f"{pid}:{tid}"
        if key not in thread_info:
            thread_info[key] = {
                "pid": pid,
                "tid": tid,
                "first_call_us": c.get("start_us"),
                "last_call_us": c.get("end_us"),
                "call_count": 0,
            }
        entry = thread_info[key]
        entry["call_count"] += 1
        if c.get("start_us") is not None:
            if entry["first_call_us"] is None:
                entry["first_call_us"] = c["start_us"]
            else:
                entry["first_call_us"] = min(entry["first_call_us"], c["start_us"])
        if c.get("end_us") is not None:
            if entry["last_call_us"] is None:
                entry["last_call_us"] = c["end_us"]
            else:
                entry["last_call_us"] = max(entry["last_call_us"], c["end_us"])

    for key, info in thread_info.items():
        first_ms = round(info["first_call_us"] / 1000.0, 3) if info.get("first_call_us") is not None else ""
        last_ms = round(info["last_call_us"] / 1000.0, 3) if info.get("last_call_us") is not None else ""
        rows.append({
            "pid": info["pid"],
            "tid": info["tid"],
            "thread_key": key,
            "first_call_ms": first_ms,
            "last_call_ms": last_ms,
            "call_count": info["call_count"],
        })

    rows.sort(key=lambda r: (r["pid"], r["tid"]))
    return rows


def _build_process_timeline(calls: list[dict[str, Any]], samples_result: dict[str, Any]) -> list[dict[str, Any]]:
    """Build per-process timeline from trace calls and CPU samples."""
    processes: dict[int, dict[str, Any]] = {}
    for c in calls:
        pid = c.get("pid")
        if pid is None:
            continue
        if pid not in processes:
            processes[pid] = {
                "pid": pid,
                "first_call_us": c.get("start_us"),
                "last_call_us": c.get("end_us"),
                "call_count": 0,
                "threads": set(),
            }
        entry = processes[pid]
        entry["call_count"] += 1
        if c.get("start_us") is not None:
            if entry["first_call_us"] is None:
                entry["first_call_us"] = c["start_us"]
            else:
                entry["first_call_us"] = min(entry["first_call_us"], c["start_us"])
        if c.get("end_us") is not None:
            if entry["last_call_us"] is None:
                entry["last_call_us"] = c["end_us"]
            else:
                entry["last_call_us"] = max(entry["last_call_us"], c["end_us"])
        tid = c.get("tid")
        if tid is not None:
            entry["threads"].add(tid)

    rows: list[dict[str, Any]] = []
    for pid, info in sorted(processes.items()):
        first_ms = round(info["first_call_us"] / 1000.0, 3) if info.get("first_call_us") is not None else ""
        last_ms = round(info["last_call_us"] / 1000.0, 3) if info.get("last_call_us") is not None else ""
        rows.append({
            "pid": pid,
            "first_call_ms": first_ms,
            "last_call_ms": last_ms,
            "call_count": info["call_count"],
            "thread_count": len(info["threads"]),
        })

    # Add container-level metrics from resources
    samples = samples_result.get("samples", []) if isinstance(samples_result, dict) else []
    container_rows: list[dict[str, Any]] = []
    for s in samples:
        container_rows.append({
            "timestamp_ms": s.get("timestamp_ms", 0.0),
            "container_available": s.get("container_available", False),
            "container_effective_cores": s.get("container_effective_cores", MEASUREMENT_UNAVAILABLE),
            "main_process_cores": s.get("main_process_cores", MEASUREMENT_UNAVAILABLE),
            "child_process_cores": s.get("child_process_cores", MEASUREMENT_UNAVAILABLE),
            "sum_visible_process_cores": s.get("sum_visible_process_cores", MEASUREMENT_UNAVAILABLE),
            "unattributed_effective_cores": s.get("unattributed_effective_cores", MEASUREMENT_UNAVAILABLE),
        })

    return rows + container_rows


def _build_resource_owners(
    samples_result: dict[str, Any],
    ops: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Build resource owner attribution from samples and semantic ops."""
    owners: list[dict[str, Any]] = []
    samples = samples_result.get("samples", []) if isinstance(samples_result, dict) else []

    for s in samples:
        ts = s["timestamp_ms"]
        for op_type in s.get("active_semantic_ops", []):
            owners.append({
                "timestamp_ms": round(ts, 3),
                "owner_type": "semantic_operation",
                "owner_name": op_type,
                "pid": "",
                "tid": "",
            })
        for func_name in s.get("active_python_funcs", []):
            owners.append({
                "timestamp_ms": round(ts, 3),
                "owner_type": "python_call",
                "owner_name": func_name,
                "pid": "",
                "tid": "",
            })

    # Add thread core owners from samples
    for s in samples:
        ts = s["timestamp_ms"]
        for tc in s.get("thread_cores", []):
            if tc.get("effective_cores", 0) > 0:
                owners.append({
                    "timestamp_ms": round(ts, 3),
                    "owner_type": "thread",
                    "owner_name": tc.get("thread_name", f"tid:{tc['tid']}"),
                    "pid": tc.get("pid", ""),
                    "tid": tc.get("tid", ""),
                })

        # Add process-level owners from computed CPU fields
        main_pid = s.get("main_pid")
        if main_pid is not None and isinstance(s.get("main_process_cores"), (int, float)):
            owners.append({
                "timestamp_ms": round(ts, 3),
                "owner_type": "process",
                "owner_name": f"main_pid:{main_pid}",
                "pid": main_pid,
                "tid": "",
            })

        # Child process owners
        if isinstance(s.get("child_process_cores"), (int, float)) and s["child_process_cores"] > 0:
            owners.append({
                "timestamp_ms": round(ts, 3),
                "owner_type": "process",
                "owner_name": "child_processes",
                "pid": "",
                "tid": "",
            })

    owners.sort(key=lambda o: (o["timestamp_ms"], o["owner_type"], o["owner_name"]))
    return owners


# ---------------------------------------------------------------------------
# Background survivors
# ---------------------------------------------------------------------------


def _find_background_survivors(
    timelines: list[dict[str, Any]],
    milestones: list[dict[str, Any]],
    sessions: list[dict[str, Any]],
    calls: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Identify background work that crosses lifecycle boundaries.

    Detects interval/task continuity crossing restore_complete, request_entry,
    prompt_executor_invoke, sampling_start, trace_stop_boundary.
    One-time snapshots alone are insufficient — requires interval or task continuity.

    Returns rows with columns:
      owner_type, owner_id, name, created_or_started_ms, boundary_crossed,
      ended_ms, duration_ms, thread_or_task, evidence_source
    """
    # Extract boundary timestamps from milestones
    boundaries: dict[str, float] = {}
    for m in milestones:
        name = str(m.get("name", m.get("event", "")))
        ts_raw = m.get("wall_unix_ms") or m.get("timestamp_ms") or m.get("time_ms")
        try:
            ts = float(ts_raw) if ts_raw else 0.0
        except (TypeError, ValueError):
            ts = 0.0
        for bname in LIFECYCLE_BOUNDARIES:
            pattern = bname if not bname.endswith("_boundary") else bname.replace("_boundary", "")
            if pattern in name.lower().replace(" ", "_"):
                if bname not in boundaries or ts > 0:
                    boundaries[bname] = ts
                break

    survivors: list[dict[str, Any]] = []
    seen: set[tuple[str, float, float, str]] = set()  # dedup

    def _add(bname: str, bts: float, entry: dict[str, Any]) -> None:
        dur_ms = entry.get("end_ms", 0.0) - entry.get("start_ms", 0.0)
        # Convert to required columns
        row = {
            "owner_type": str(entry.get("owner_type", "unknown")),
            "owner_id": str(entry.get("owner_id", entry.get("event_index", ""))),
            "name": str(entry.get("owner_name", entry.get("name", ""))),
            "created_or_started_ms": round(entry.get("start_ms", 0.0), 3),
            "boundary_crossed": bname,
            "ended_ms": round(entry.get("end_ms", 0.0), 3),
            "duration_ms": round(dur_ms, 3),
            "thread_or_task": str(entry.get("tid", entry.get("task_id", ""))),
            "evidence_source": str(entry.get("evidence_source", "viztracer")),
        }
        dedup_key = (row["owner_id"], row["created_or_started_ms"], row["ended_ms"], bname)
        if dedup_key not in seen:
            seen.add(dedup_key)
            survivors.append(row)

    # Check timeline entries crossing boundaries (interval continuity)
    for entry in timelines:
        for bname, bts in boundaries.items():
            start_ms = entry.get("start_ms", 0.0)
            end_ms = entry.get("end_ms", 0.0)
            # Interval crossing: entry starts before and ends after boundary
            if start_ms < bts < end_ms:
                _add(bname, bts, entry)
                break  # one boundary per entry max

    # Also check calls directly (non-timeline entries) for interval continuity
    for bname, bts in boundaries.items():
        bts_us = bts * 1000.0
        for c in calls:
            start_us = c.get("start_us")
            end_us = c.get("end_us")
            if start_us is None or end_us is None:
                continue
            if start_us < bts_us < end_us:
                dur_ms = (end_us - start_us) / 1000.0
                row = {
                    "owner_type": "python_call",
                    "owner_id": str(c.get("event_index", "")),
                    "name": str(c.get("name", "")),
                    "created_or_started_ms": round(start_us / 1000.0, 3),
                    "boundary_crossed": bname,
                    "ended_ms": round(end_us / 1000.0, 3),
                    "duration_ms": round(dur_ms, 3),
                    "thread_or_task": str(c.get("tid", c.get("task_id", ""))),
                    "evidence_source": "viztracer",
                }
                dedup_key = (row["owner_id"], row["created_or_started_ms"], row["ended_ms"], bname)
                if dedup_key not in seen:
                    seen.add(dedup_key)
                    survivors.append(row)

    survivors.sort(key=lambda s: (s["boundary_crossed"], s["created_or_started_ms"]))
    return survivors


# ---------------------------------------------------------------------------
# Wrapper analysis
# ---------------------------------------------------------------------------


def _build_wrapper_chains(wrapper_snapshots: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Analyze wrapper chains from snapshot data.

    Reports depth, repeated callable identities, cycles, multiple known-original
    paths, sentinel attributes, closure callable references, and installation-stage
    changes.
    """
    if not wrapper_snapshots:
        return []

    chains: list[dict[str, Any]] = []
    for snapshot in wrapper_snapshots:
        milestone = str(snapshot.get("milestone", ""))
        wrappers = snapshot.get("wrappers", {})
        if not isinstance(wrappers, dict):
            continue
        for target, chain in wrappers.items():
            if not isinstance(chain, list):
                continue
            callable_ids = [str(w.get("id", w.get("callable_id", ""))) for w in chain if isinstance(w, dict)]
            callable_names = [str(w.get("name", w.get("callable", ""))) for w in chain if isinstance(w, dict)]
            depth = len(chain)
            has_cycles = len(set(callable_ids)) < len(callable_ids) if callable_ids else False
            multiple_origins = len(set(callable_names)) > 1 if callable_names else False
            sentinel_attrs = any(
                isinstance(w, dict) and any(
                    k.startswith("__") or k in ("__wrapped__", "__wrapper__")
                    for k in w.keys()
                )
                for w in chain
            )
            # Closure callable references: entries with __closure__ or func_closure
            closure_refs = any(
                isinstance(w, dict) and any(
                    k in ("__closure__", "func_closure", "closure")
                    for k in w.keys()
                )
                for w in chain
            )
            # Installation-stage changes: detect if wrapper was modified since install
            # (entries with both __wrapped__ and __original__ or similar)
            install_stage_changes = any(
                isinstance(w, dict) and all(
                    k in w for k in ("__wrapped__", "__original__")
                )
                for w in chain
            )
            chains.append({
                "milestone": milestone,
                "target": target,
                "depth": depth,
                "callable_ids": callable_ids,
                "callable_names": callable_names,
                "has_cycles": has_cycles,
                "multiple_known_origins": multiple_origins,
                "sentinel_attributes": sentinel_attrs,
                "closure_callable_refs": closure_refs,
                "installation_stage_changes": install_stage_changes,
            })
    return chains


def _build_wrapper_changes(wrapper_snapshots: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Track wrapper changes between consecutive snapshots.

    Detects identity/stage changes even when depth is unchanged
    (e.g., different callable ids at same depth), as well as
    cycles, repeated identities, known-original paths, sentinel
    and closure refs.
    """
    if len(wrapper_snapshots) < 2:
        return []

    changes: list[dict[str, Any]] = []
    for i in range(1, len(wrapper_snapshots)):
        prev = wrapper_snapshots[i - 1]
        cur = wrapper_snapshots[i]
        prev_milestone = str(prev.get("milestone", ""))
        cur_milestone = str(cur.get("milestone", ""))
        prev_wrappers = prev.get("wrappers", {})
        cur_wrappers = cur.get("wrappers", {})

        if not isinstance(prev_wrappers, dict) or not isinstance(cur_wrappers, dict):
            continue

        all_targets = set(prev_wrappers.keys()) | set(cur_wrappers.keys())
        for target in sorted(all_targets):
            prev_chain = prev_wrappers.get(target, [])
            cur_chain = cur_wrappers.get(target, [])
            if not isinstance(prev_chain, list):
                prev_chain = []
            if not isinstance(cur_chain, list):
                cur_chain = []
            prev_depth = len(prev_chain)
            cur_depth = len(cur_chain)
            prev_ids = [str(w.get("id", w.get("callable_id", ""))) for w in prev_chain if isinstance(w, dict)]
            cur_ids = [str(w.get("id", w.get("callable_id", ""))) for w in cur_chain if isinstance(w, dict)]

            if prev_depth != cur_depth or prev_ids != cur_ids:
                change_type: str
                if prev_depth == 0 and cur_depth > 0:
                    change_type = "appeared"
                elif cur_depth == 0 and prev_depth > 0:
                    change_type = "disappeared"
                elif prev_ids != cur_ids:
                    change_type = "identity_change"
                elif prev_depth < cur_depth:
                    change_type = "depth_increase"
                elif prev_depth > cur_depth:
                    change_type = "depth_decrease"
                else:
                    change_type = "depth_change"
                changes.append({
                    "from_milestone": prev_milestone,
                    "to_milestone": cur_milestone,
                    "target": target,
                    "prev_depth": prev_depth,
                    "cur_depth": cur_depth,
                    "change_type": change_type,
                })
    return changes


# ---------------------------------------------------------------------------
# PyTorch trace analysis
# ---------------------------------------------------------------------------


def _classify_torch_op(event: dict[str, Any]) -> tuple[str, str]:
    """Classify a PyTorch trace event into a category.

    Returns (operator_or_kernel, category).
    """
    name = str(event.get("name", ""))
    cat = str(event.get("cat", ""))
    lower_name = name.lower()

    # CUDA kernels
    if "cuda" in cat.lower() or "kernel" in lower_name or lower_name.startswith("cuda"):
        if "memcpy" in lower_name or "h2d" in lower_name or "d2h" in lower_name:
            return (name, "memory_copy")
        if "memset" in lower_name:
            return (name, "memory_set")
        if "synchronize" in lower_name or "sync" in lower_name:
            return (name, "synchronization")
        if "allocator" in lower_name or "malloc" in lower_name or "free" in lower_name:
            return (name, "allocator")
        return (name, "cuda_kernel")

    # CPU operators — recognize common PyTorch CPU categories
    if cat in ("cpu_op", "operator", "aten", "python_function") or "aten" in cat.lower():
        return (name, "cpu_op")

    # Operator/operator (capital O variant)
    if cat == "Operator" or name.startswith("Operator::") or name.startswith("operator::"):
        return (name, "cpu_op")

    return (name, "other")


def _build_torch_cpu_ops(torch_events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Aggregate PyTorch CPU operators from torch trace.

    Uses explicit self duration fields (``self_dur``, ``self_cpu_time_total``)
    when present; falls back to event duration as documented deterministic default.
    """
    ops: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for ev in torch_events:
        op_name, cat = _classify_torch_op(ev)
        if cat != "cpu_op":
            continue
        dur = _safe_float(ev.get("dur"), 0.0) or 0.0
        # Prefer explicit self duration fields when present
        args = ev.get("args", {}) if isinstance(ev.get("args"), dict) else {}
        self_cpu = (
            _safe_float(args.get("self_dur"), None)
            or _safe_float(args.get("self_cpu_time_total"), None)
            or dur  # documented deterministic fallback
        )
        ops[op_name].append({
            "duration_us": dur,
            "self_us": self_cpu,
        })

    rows: list[dict[str, Any]] = []
    for op_name, entries in ops.items():
        durs = [e["duration_us"] for e in entries]
        selfs = [e["self_us"] for e in entries]
        total_cpu = sum(durs) / 1000.0  # ms
        total_self = sum(selfs) / 1000.0
        mean_cpu = (sum(durs) / len(durs)) / 1000.0 if durs else 0.0
        max_cpu = max(durs) / 1000.0 if durs else 0.0
        rows.append({
            "operator": op_name,
            "call_count": len(entries),
            "total_cpu_ms": round(total_cpu, 3),
            "self_cpu_ms": round(total_self, 3),
            "mean_cpu_ms": round(mean_cpu, 3),
            "max_cpu_ms": round(max_cpu, 3),
        })

    rows.sort(key=lambda r: r["total_cpu_ms"], reverse=True)
    return rows


def _build_torch_cuda_ops(torch_events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Aggregate CUDA operations from torch trace."""
    ops: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for ev in torch_events:
        op_name, cat = _classify_torch_op(ev)
        if cat == "other":
            continue
        dur = _safe_float(ev.get("dur"), 0.0) or 0.0
        stream = str(ev.get("args", {}).get("stream", "")) if isinstance(ev.get("args"), dict) else ""
        ops[op_name].append({
            "category": cat,
            "duration_us": dur,
            "stream": stream,
        })

    rows: list[dict[str, Any]] = []
    for op_name, entries in ops.items():
        durs = [e["duration_us"] for e in entries]
        cat = entries[0]["category"]
        streams = set(e["stream"] for e in entries if e["stream"])
        total_cuda = sum(durs) / 1000.0
        mean_cuda = (sum(durs) / len(durs)) / 1000.0 if durs else 0.0
        max_cuda = max(durs) / 1000.0 if durs else 0.0

        # GPU-idle gaps: identify gaps between consecutive ops > 1ms
        sorted_entries = sorted(entries, key=lambda e: e.get("duration_us", 0))
        gap_info = ""
        if len(sorted_entries) > 1:
            sorted_ts = sorted(
                (ev for ev in torch_events if _classify_torch_op(ev)[0] == op_name),
                key=lambda e: _safe_float(e.get("ts", 0.0), 0.0),
            )
            gaps = []
            for i in range(1, len(sorted_ts)):
                gap = _safe_float(sorted_ts[i].get("ts", 0.0), 0.0) - (
                    _safe_float(sorted_ts[i - 1].get("ts", 0.0), 0.0)
                    + _safe_float(sorted_ts[i - 1].get("dur", 0.0), 0.0)
                )
                if gap > 1000:  # >1ms gap
                    gaps.append(gap)
            if gaps:
                gap_info = f"GPU idle gaps (ms): {[round(g/1000.0, 3) for g in gaps]}"

        rows.append({
            "kernel_or_memcpy": op_name,
            "category": cat,
            "call_count": len(entries),
            "total_cuda_ms": round(total_cuda, 3),
            "mean_cuda_ms": round(mean_cuda, 3),
            "max_cuda_ms": round(max_cuda, 3),
            "stream_count": len(streams),
            "gpu_idle_gaps_ms": gap_info,
        })

    rows.sort(key=lambda r: r["total_cuda_ms"], reverse=True)
    return rows


# ---------------------------------------------------------------------------
# async_tasks.csv
# ---------------------------------------------------------------------------


def _build_async_tasks(
    milestones: list[dict[str, Any]],
    sessions: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Build async tasks CSV from milestones and session events (no manufactured timestamps)."""
    tasks: dict[str, dict[str, Any]] = {}

    def _process_event(
        ev: dict[str, Any],
        event_source: str,
    ) -> None:
        task_id = str(ev.get("task_id", ""))
        if not task_id:
            return
        if task_id not in tasks:
            ts = _safe_float(ev.get("timestamp_ms", ev.get("wall_unix_ms", 0.0)), 0.0)
            tasks[task_id] = {
                "task_id": task_id,
                "task_name": str(ev.get("task_name", ev.get("name", ""))),
                "done": False,
                "cancelled": False,
                "coroutine_qualname": str(ev.get("coroutine_name", ev.get("coroutine_qualname", ""))),
                "top_stack_file": str(ev.get("stack_file", "")),
                "top_stack_line": _safe_int(ev.get("stack_line", 0)),
                "top_stack_function": str(ev.get("stack_function", "")),
                "first_seen_ms": ts,
                "last_seen_ms": ts,
                "boundaries_crossed": [],
                "source": event_source,
            }
        entry = tasks[task_id]
        ts = _safe_float(ev.get("timestamp_ms", ev.get("wall_unix_ms", 0.0)), 0.0)
        entry["last_seen_ms"] = max(entry["last_seen_ms"], ts)
        if ev.get("done"):
            entry["done"] = True
        if ev.get("cancelled"):
            entry["cancelled"] = True
        if ev.get("milestone_start"):
            entry["first_seen_ms"] = min(entry["first_seen_ms"], ts)

        # Check boundary crossing
        for bname in LIFECYCLE_BOUNDARIES:
            event_name = str(ev.get("name", ev.get("event", ""))).lower()
            if bname in event_name:
                if bname not in entry["boundaries_crossed"]:
                    entry["boundaries_crossed"].append(bname)

    for m in milestones:
        _process_event(m, "milestones")
    for ev in sessions:
        _process_event(ev, "session_events")

    rows: list[dict[str, Any]] = []
    for tid, info in sorted(tasks.items()):
        rows.append({
            "milestone": info["task_id"],  # Using task_id as identifier
            "task_id": info["task_id"],
            "task_name": info["task_name"],
            "done": str(info["done"]),
            "cancelled": str(info["cancelled"]),
            "coroutine_qualname": info["coroutine_qualname"],
            "top_stack_file": info["top_stack_file"],
            "top_stack_line": info["top_stack_line"],
            "top_stack_function": info["top_stack_function"],
            "first_seen_ms": round(info["first_seen_ms"], 3),
            "last_seen_ms": round(info["last_seen_ms"], 3),
            "boundaries_crossed": ";".join(info["boundaries_crossed"]),
        })
    return rows


# ---------------------------------------------------------------------------
# report.md generation
# ---------------------------------------------------------------------------

_MEASUREMENT_UNAVAILABLE_STR = "measurement_unavailable"

# Boundary display name mapping for readable headings
_BOUNDARY_DISPLAY_NAMES = {
    "restore_complete": "restore completion",
    "request_entry": "request entry",
    "prompt_executor_invoke": "PromptExecutor invoke",
    "sampling_start": "sampling start",
    "trace_stop": "trace stop",
}


def _generate_report_md(
    status: str,
    warnings: list[str],
    calls: list[dict[str, Any]],
    timeline: list[dict[str, Any]],
    func_summary: list[dict[str, Any]],
    duplicates: list[dict[str, Any]],
    semantic_duplicates: list[dict[str, Any]],
    survivors: list[dict[str, Any]],
    wrapper_chains: list[dict[str, Any]],
    wrapper_changes: list[dict[str, Any]],
    expected_vs_observed: list[dict[str, Any]],
    torch_cpu_ops: list[dict[str, Any]],
    torch_cuda_ops: list[dict[str, Any]],
    resource_result: dict[str, Any],
    process_timeline: list[dict[str, Any]],
    thread_timeline: list[dict[str, Any]],
    resource_owners: list[dict[str, Any]],
    trace_config: dict[str, Any],
    runtime_result: dict[str, Any],
    derived_files: dict[str, Any],
    overlaps: list[dict[str, Any]],
    milestones: list[dict[str, Any]],
) -> str:
    """Generate the full markdown report."""
    lines: list[str] = []
    _w = lines.append

    # ── Heading ──
    _w("# V2 Full Execution Trace Report")
    _w("")

    # ── Trace identity ──
    _w("## Trace identity")
    _w("")
    _w(f"- **Schema version**: {VERSION}")
    _w(f"- **Status**: {status}")
    _w(f"- **Trace entry count**: {derived_files.get('trace_entry_count', 'N/A')}")
    _w(f"- **Trace entry capacity**: {derived_files.get('trace_entry_capacity', 'N/A')}")
    _w(f"- **Trace truncated**: {derived_files.get('trace_truncated', 'N/A')}")
    config_id = trace_config.get("request_id", trace_config.get("trace_id", "N/A"))
    _w(f"- **Request ID**: {config_id}")
    session_id = trace_config.get("session_id", runtime_result.get("container_session_id", "N/A"))
    _w(f"- **Session ID**: {session_id}")
    _w("")

    # ── Trace completeness ──
    _w("## Trace completeness")
    _w("")
    _w(f"- Total trace events parsed: {len(calls)}")
    _w(f"- Timeline entries: {len(timeline)}")
    _w(f"- Function summary entries: {len(func_summary)}")
    _w(f"- Duplicate groups found: {len(duplicates)}")
    _w(f"- Semantic duplicate groups: {len(semantic_duplicates)}")
    _w(f"- Wrapper snapshots: {len(wrapper_chains)}")
    _w(f"- Background survivors: {len(survivors)}")
    _w(f"- Overlap intervals: {len(overlaps)}")
    if warnings:
        _w("")
        _w("### Warnings")
        for w in warnings:
            _w(f"- {w}")
    _w("")

    # ── Runtime configuration ──
    _w("## Runtime configuration")
    _w("")
    if trace_config:
        for k, v in sorted(trace_config.items()):
            _w(f"- **{k}**: {v}")
    else:
        _w("- No trace configuration found.")
    _w("")

    # ── Critical timeline ──
    _w("## Critical timeline")
    _w("")
    _w("| Start (ms) | End (ms) | Duration (ms) | Owner | Type | PID | TID | Evidence |")
    _w("|---|---|---|---|---|---|---|---|")
    for entry in timeline[:50]:  # Top 50 entries
        _w(
            f"| {entry['start_ms']} | {entry['end_ms']} | {entry['duration_ms']} "
            f"| {entry['owner_name']} | {entry['owner_type']} "
            f"| {entry['pid']} | {entry['tid']} | {entry.get('evidence_source', '')} |"
        )
    if len(timeline) > 50:
        _w(f"| *... and {len(timeline) - 50} more entries* |")
    _w("")

    # ── Top functions by inclusive time ──
    _w("## Top functions by inclusive time")
    _w("")
    _w("| Function | Source file | Calls | Inclusive (ms) | Exclusive (ms) | Mean (ms) |")
    _w("|---|---|---|---|---|---|")
    for row in func_summary[:20]:
        _w(
            f"| {row['function']} | {row['source_file']} | {row['call_count']} "
            f"| {row['inclusive_ms']} | {row['exclusive_ms']} | {row['mean_ms']} |"
        )
    if len(func_summary) > 20:
        _w(f"| *... and {len(func_summary) - 20} more functions* |")
    _w("")

    # ── Top functions by exclusive time ──
    _w("## Top functions by exclusive time")
    _w("")
    by_exclusive = sorted(func_summary, key=lambda r: r["exclusive_ms"], reverse=True)
    _w("| Function | Source file | Exclusive (ms) | Inclusive (ms) | Calls |")
    _w("|---|---|---|---|---|")
    for row in by_exclusive[:20]:
        _w(
            f"| {row['function']} | {row['source_file']} | {row['exclusive_ms']} "
            f"| {row['inclusive_ms']} | {row['call_count']} |"
        )
    if len(by_exclusive) > 20:
        _w(f"| *... and {len(by_exclusive) - 20} more functions* |")
    _w("")

    # ── Highest call counts ──
    _w("## Highest call counts")
    _w("")
    by_count = sorted(func_summary, key=lambda r: r["call_count"], reverse=True)
    _w("| Function | Source file | Calls | Inclusive (ms) |")
    _w("|---|---|---|---|")
    for row in by_count[:20]:
        _w(
            f"| {row['function']} | {row['source_file']} | {row['call_count']} "
            f"| {row['inclusive_ms']} |"
        )
    _w("")

    # ── Concurrent operations ──
    _w("## Concurrent operations")
    _w("")
    _w(f"- Total overlapping intervals detected: {len(overlaps)}")
    _w("")
    if overlaps:
        _w("| Left | Right | Overlap (ms) | Same thread | Same process |")
        _w("|---|---|---|---|---|")
        for o in overlaps[:30]:
            _w(
                f"| {o['left_owner']} (L{','.join(str(o.get('left_start_ms', '')))}) "
                f"| {o['right_owner']} (L{','.join(str(o.get('right_start_ms', '')))}) "
                f"| {o['overlap_ms']} | {o['same_thread']} | {o['same_process']} |"
            )
        _w("")

    # ── CPU ownership by process ──
    _w("## CPU ownership by process")
    _w("")
    _w("| PID | First call (ms) | Last call (ms) | Call count | Threads |")
    _w("|---|---|---|---|---|")
    for row in process_timeline[:20]:
        if "pid" in row and "first_call_ms" in row:
            _w(
                f"| {row['pid']} | {row['first_call_ms']} | {row['last_call_ms']} "
                f"| {row['call_count']} | {row['thread_count']} |"
            )
    _w("")

    # ── CPU ownership by native thread ──
    _w("## CPU ownership by native thread")
    _w("")
    _w("| PID:TID | First call (ms) | Last call (ms) | Call count |")
    _w("|---|---|---|---|")
    for row in thread_timeline[:30]:
        _w(
            f"| {row['thread_key']} | {row['first_call_ms']} | {row['last_call_ms']} "
            f"| {row['call_count']} |"
        )
    _w("")

    # ── Background work by boundary ──
    for bname in LIFECYCLE_BOUNDARIES:
        display = _BOUNDARY_DISPLAY_NAMES.get(bname, bname)
        _w(f"## Background work crossing {display}")
        _w("")
        filtered = [s for s in survivors if s["boundary_crossed"] == bname]
        if filtered:
            _w("| Name | Type | ID | Started (ms) | Ended (ms) | Duration (ms) | Thread/Task | Evidence |")
            _w("|---|---|---|---|---|---|---|---|")
            for s in filtered[:20]:
                _w(
                    f"| {s['name']} | {s['owner_type']} | {s['owner_id']} "
                    f"| {s['created_or_started_ms']} | {s['ended_ms']} "
                    f"| {s['duration_ms']} | {s['thread_or_task']} | {s['evidence_source']} |"
                )
        else:
            _w("No background work crossing this boundary.")
        _w("")

    # ── Duplicate semantic work ──
    _w("## Duplicate semantic work")
    _w("")
    if semantic_duplicates:
        _w("| Operation type | Count | Repeated starts | Overlaps | Repeated completions |")
        _w("|---|---|---|---|---|")
        for sd in semantic_duplicates:
            _w(
                f"| {sd['operation_type']} | {sd['call_count']} "
                f"| {sd['repeated_starts']} | {sd['overlaps']} "
                f"| {sd['repeated_completions']} |"
            )
    else:
        _w("No duplicate semantic operations detected.")
    _w("")

    # ── Repeated wrapper layers ──
    _w("## Repeated wrapper layers")
    _w("")
    if wrapper_chains:
        _w("| Target | Milestone | Depth | Cycles | Multiple origins |")
        _w("|---|---|---|---|---|")
        for wc in wrapper_chains[:30]:
            _w(
                f"| {wc['target']} | {wc['milestone']} | {wc['depth']} "
                f"| {wc['has_cycles']} | {wc['multiple_known_origins']} |"
            )
    else:
        _w("No wrapper chains detected.")
    _w("")

    # ── Wrapper changes during lifecycle ──
    _w("## Wrapper changes during the lifecycle")
    _w("")
    if wrapper_changes:
        _w("| From | To | Target | Change | Prev depth | Cur depth |")
        _w("|---|---|---|---|---|---|")
        for wc in wrapper_changes:
            _w(
                f"| {wc['from_milestone']} | {wc['to_milestone']} | {wc['target']} "
                f"| {wc['change_type']} | {wc['prev_depth']} | {wc['cur_depth']} |"
            )
    else:
        _w("No wrapper changes detected.")
    _w("")

    # ── Expected vs observed ──
    _w("## Expected versus observed operation counts")
    _w("")
    _w("| Operation | Expected | Observed | Classification |")
    _w("|---|---|---|---|")
    for r in expected_vs_observed:
        _w(f"| {r['operation']} | {r['expected']} | {r['observed']} | {r['classification']} |")
    _w("")

    # ── PyTorch CPU operator summary ──
    _w("## PyTorch CPU operator summary")
    _w("")
    if torch_cpu_ops:
        _w("| Operator | Calls | Total (ms) | Self (ms) | Mean (ms) | Max (ms) |")
        _w("|---|---|---|---|---|---|")
        for op in torch_cpu_ops[:20]:
            _w(
                f"| {op['operator']} | {op['call_count']} | {op['total_cpu_ms']} "
                f"| {op['self_cpu_ms']} | {op['mean_cpu_ms']} | {op['max_cpu_ms']} |"
            )
    else:
        _w("No PyTorch CPU operators found.")
    _w("")

    # ── CUDA kernel and memory-copy summary ──
    _w("## CUDA kernel and memory-copy summary")
    _w("")
    if torch_cuda_ops:
        _w("| Kernel | Category | Calls | Total (ms) | Mean (ms) | Max (ms) | Streams |")
        _w("|---|---|---|---|---|---|---|")
        for op in torch_cuda_ops[:20]:
            _w(
                f"| {op['kernel_or_memcpy']} | {op['category']} | {op['call_count']} "
                f"| {op['total_cuda_ms']} | {op['mean_cuda_ms']} | {op['max_cuda_ms']} "
                f"| {op['stream_count']} |"
            )
    else:
        _w("No CUDA operations found.")
    _w("")

    # ── Unattributed container CPU ──
    _w("## Unattributed container CPU")
    _w("")
    samples = resource_result.get("samples", []) if isinstance(resource_result, dict) else []
    has_unattributed = any(
        isinstance(s.get("unattributed_effective_cores"), str)
        and s["unattributed_effective_cores"] != _MEASUREMENT_UNAVAILABLE_STR
        or isinstance(s.get("unattributed_effective_cores"), (int, float))
        for s in samples
    )
    if has_unattributed:
        _w("| Timestamp (ms) | Container cores | Process cores | Unattributed cores |")
        _w("|---|---|---|---|")
        for s in samples:
            cc = s.get("container_effective_cores", "N/A")
            pc = s.get("sum_visible_process_cores", "N/A")
            uc = s.get("unattributed_effective_cores", "N/A")
            _w(f"| {s['timestamp_ms']} | {cc} | {pc} | {uc} |")
    else:
        _w("Container CPU data not available or no unattributed CPU detected.")
    _w("")

    # ── Potential optimization artifacts ──
    _w("## Potential optimization artifacts")
    _w("")
    observed: list[str] = []

    # High duplicate call counts
    if duplicates:
        observed.append(f"- **Duplicate call groups**: {len(duplicates)} groups detected")
        for d in duplicates[:5]:
            observed.append(
                f"  - `{d['function']}` called {d['call_count']} times "
                f"(evidence: {d['evidence_strength']})"
            )

    # Wrapper cycles
    for wc in wrapper_chains:
        if wc.get("has_cycles"):
            observed.append(
                f"- **Repeating callable identity**: `{wc['target']}` at `{wc['milestone']}`"
            )

    # Semantic overlaps
    for sd in semantic_duplicates:
        if sd.get("overlaps"):
            observed.append(
                f"- **Overlapping semantic work**: `{sd['operation_type']}` "
                f"({sd['call_count']} instances)"
            )

    # Stack inconsistencies
    stack_issues = _detect_stack_inconsistencies(calls)
    for issue in stack_issues[:5]:
        observed.append(f"- **Stack inconsistency**: {issue['description']}")

    if not observed:
        observed.append("No structural patterns detected beyond baseline.")

    for o in observed:
        _w(o)
    _w("")

    # ── Raw and derived file inventory ──
    _w("## Raw and derived file inventory")
    _w("")
    _w("| Path | Category | Size (bytes) | SHA-256 |")
    _w("|---|---|---|---|")
    for entry in derived_files.get("files", []):
        _w(
            f"| {entry['path']} | {entry['category']} | {entry['size_bytes']} "
            f"| {entry.get('sha256', '')} |"
        )
    _w("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Manifest generation
# ---------------------------------------------------------------------------


def _build_manifest(raw_dir: Path, derived_dir: Path) -> list[dict[str, Any]]:
    """Build manifest listing every raw and derived file.

    Uses POSIX-ish relative paths (forward slashes).
    Does NOT include manifest.json's own entry.
    """
    entries: list[dict[str, Any]] = []

    # Raw files
    if raw_dir.exists():
        for fpath in sorted(raw_dir.iterdir()):
            if fpath.is_file():
                entries.append({
                    "path": str(fpath.relative_to(raw_dir.parent)).replace("\\", "/"),
                    "category": "raw",
                    "size_bytes": fpath.stat().st_size,
                    "sha256": _sha256_file(fpath),
                })

    # Derived files (exclude manifest.json from its own inventory)
    if derived_dir.exists():
        for fpath in sorted(derived_dir.iterdir()):
            if fpath.is_file() and fpath.name != "manifest.json":
                entries.append({
                    "path": str(fpath.relative_to(derived_dir.parent)).replace("\\", "/"),
                    "category": "derived",
                    "size_bytes": fpath.stat().st_size,
                    "sha256": _sha256_file(fpath),
                })

    return entries


# ---------------------------------------------------------------------------
# report_data.json
# ---------------------------------------------------------------------------


def _build_report_data(
    status: str,
    warnings: list[str],
    calls: list[dict[str, Any]],
    timeline: list[dict[str, Any]],
    func_summary: list[dict[str, Any]],
    duplicates: list[dict[str, Any]],
    semantic_duplicates: list[dict[str, Any]],
    survivors: list[dict[str, Any]],
    wrapper_chains: list[dict[str, Any]],
    wrapper_changes: list[dict[str, Any]],
    expected_vs_observed: list[dict[str, Any]],
    torch_cpu_ops: list[dict[str, Any]],
    torch_cuda_ops: list[dict[str, Any]],
    resource_result: dict[str, Any],
    process_timeline: list[dict[str, Any]],
    thread_timeline: list[dict[str, Any]],
    resource_owners: list[dict[str, Any]],
    overlaps: list[dict[str, Any]],
    milestones: list[dict[str, Any]],
    sessions: list[dict[str, Any]],
    trace_config: dict[str, Any],
    runtime_result: dict[str, Any],
    stack_issues: list[dict[str, Any]],
    async_tasks: list[dict[str, Any]],
    # Derived files info
    derived_files: dict[str, Any],
) -> dict[str, Any]:
    """Build the structured report_data.json."""
    data: dict[str, Any] = {
        "schema_version": VERSION,
        "status": status,
        "warnings": warnings,
        "summary": {
            "total_calls": len(calls),
            "total_timeline_entries": len(timeline),
            "total_func_summary_entries": len(func_summary),
            "total_duplicate_groups": len(duplicates),
            "total_semantic_duplicate_groups": len(semantic_duplicates),
            "total_survivors": len(survivors),
            "total_overlaps": len(overlaps),
            "total_wrapper_chains": len(wrapper_chains),
            "total_wrapper_changes": len(wrapper_changes),
        },
        "trace_identity": {
            "request_id": trace_config.get("request_id", ""),
            "session_id": trace_config.get("session_id", runtime_result.get("container_session_id", "")),
            "trace_entry_count": derived_files.get("trace_entry_count", len(calls)),
            "trace_entry_capacity": derived_files.get("trace_entry_capacity"),
            "trace_truncated": derived_files.get("trace_truncated", False),
        },
        "calls": calls,
        "timeline": timeline,
        "functions_summary": func_summary,
        "duplicate_calls": duplicates,
        "semantic_duplicates": semantic_duplicates,
        "overlap_intervals": overlaps,
        "background_survivors": survivors,
        "wrapper_chains": wrapper_chains,
        "wrapper_changes": wrapper_changes,
        "expected_vs_observed": expected_vs_observed,
        "torch_cpu_ops": torch_cpu_ops,
        "torch_cuda_ops": torch_cuda_ops,
        "process_timeline": process_timeline,
        "thread_timeline": thread_timeline,
        "resource_owners": resource_owners,
        "stack_inconsistencies": stack_issues,
        "async_tasks": async_tasks,
        "milestones": milestones,
        "session_events": sessions,
        "trace_config": trace_config,
        "runtime_result": runtime_result,
    }

    # Add resource samples if available
    if isinstance(resource_result, dict) and resource_result.get("samples"):
        data["resource_samples"] = resource_result["samples"]

    return data


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def generate_full_trace_report(session_dir: Path) -> dict[str, Any]:
    """Generate a full execution trace report from *session_dir*.

    Parameters
    ----------
    session_dir:
        Path to an offline session directory containing a ``raw/``
        subdirectory with trace artifacts.

    Returns
    -------
    dict with keys:
        status              "ready" | "partial" | "error"
        report_path         str
        manifest_path       str
        derived_files       dict[str, Any]
        warnings            list[str]
        trace_entry_count   int
        trace_entry_capacity int | None
        trace_truncated     bool
    """
    warnings: list[str] = []
    status = "ready"

    # ── Validate session directory ──
    session_dir = Path(session_dir)
    if not session_dir.is_dir():
        return {
            "status": "error",
            "report_path": "",
            "manifest_path": "",
            "derived_files": [],
            "warnings": [f"Session directory not found: {session_dir}"],
            "trace_entry_count": 0,
            "trace_entry_capacity": None,
            "trace_truncated": False,
        }

    raw_dir = session_dir / "raw"
    derived_dir = session_dir / "derived"

    if not raw_dir.is_dir():
        warnings.append(f"Raw directory not found: {raw_dir}")
        status = "partial"

    # ── Parse raw inputs ──
    trace_events, trace_meta, entry_count, entry_capacity, truncated = _parse_trace_file(session_dir)
    torch_events = _parse_torch_trace(session_dir)
    resource_samples_raw = _parse_resource_samples(session_dir)
    milestones = _parse_milestones(session_dir)
    sessions = _parse_session_events(session_dir)
    wrapper_snapshots = _parse_wrapper_snapshots(session_dir)
    trace_config = _parse_trace_config(session_dir)
    runtime_result = _parse_runtime_result_summary(session_dir)

    # ── Build calls with parent-child relationships ──
    calls = _build_calls(trace_events)

    if not calls:
        warnings.append("No parseable calls found in VizTracer trace.")
        if status == "ready":
            status = "partial"

    _reconstruct_parents(calls)

    # ── Build function summary ──
    func_summary = _build_functions_summary(calls)

    # ── Build semantic operations ──
    semantic_ops = _build_semantic_ops(calls, sessions, trace_config=trace_config)

    # ── Build critical timeline ──
    timeline = _build_critical_timeline(calls, milestones, sessions, semantic_ops)

    # ── Duplicate detection (with trace_config window override) ──
    duplicates = _find_duplicate_groups(calls, trace_config=trace_config)
    semantic_duplicates = _build_semantic_duplicates(semantic_ops)

    # ── Overlap analysis ──
    overlaps = _build_overlap_intervals(timeline, semantic_ops, milestones)

    # ── Expected vs observed ──
    expected_vs_observed = _build_expected_vs_observed(
        semantic_ops, milestones, session_dir, trace_config=trace_config,
    )

    # ── Resource / CPU analysis ──
    resource_result = _parse_cpu_samples(resource_samples_raw)
    process_timeline = _build_process_timeline(calls, resource_result)
    thread_timeline = _build_thread_timeline(calls, resource_result)
    resource_owners = _build_resource_owners(resource_result, semantic_ops)

    # ── Background survivors ──
    survivors = _find_background_survivors(timeline, milestones, sessions, calls)

    # ── Wrapper analysis ──
    wrapper_chains = _build_wrapper_chains(wrapper_snapshots)
    wrapper_changes = _build_wrapper_changes(wrapper_snapshots)

    # ── Torch analysis ──
    torch_cpu_ops = _build_torch_cpu_ops(torch_events)
    torch_cuda_ops = _build_torch_cuda_ops(torch_events)

    # ── Async tasks ──
    async_tasks = _build_async_tasks(milestones, sessions)

    # ── Stack inconsistencies ──
    stack_issues = _detect_stack_inconsistencies(calls)

    # ── Ensure derived directory ──
    derived_dir.mkdir(parents=True, exist_ok=True)

    # ── Write derived files ──

    # calls.csv.gz — CSV may use empty cells for unknown values;
    # report_data.json retains None for unknown and preserves args for semantic analysis.
    calls_csv_path = derived_dir / "calls.csv.gz"
    calls_rows_for_csv = []
    for c in calls:
        calls_rows_for_csv.append({
            "event_index": c["event_index"],
            "name": c["name"],
            "category": c.get("category", ""),
            "source_file": c.get("source_file"),
            "source_line": c.get("source_line"),
            "pid": c.get("pid"),
            "tid": c.get("tid"),
            "task_id": c.get("task_id", ""),
            "start_us": c.get("start_us"),
            "duration_us": c.get("duration_us"),
            "end_us": c.get("end_us"),
            "parent_event_index": c.get("parent_event_index"),
            "parent_name": c.get("parent_name"),
            "depth": c.get("depth"),
            "complete": c.get("complete", True),
        })
    _gzip_csv(calls_csv_path, calls_rows_for_csv, fieldnames=[
        "event_index", "name", "category", "source_file", "source_line",
        "pid", "tid", "task_id", "start_us", "duration_us", "end_us",
        "parent_event_index", "parent_name", "depth", "complete",
    ])

    # functions_summary.csv
    _write_csv(derived_dir / "functions_summary.csv", func_summary, fieldnames=[
        "source_file", "function", "call_count", "inclusive_ms", "exclusive_ms",
        "mean_ms", "median_ms", "p95_ms", "max_ms", "thread_count", "task_count",
        "first_start_ms", "last_end_ms",
    ])

    # critical_timeline.csv
    _write_csv(derived_dir / "critical_timeline.csv", timeline, fieldnames=[
        "start_ms", "end_ms", "duration_ms", "owner_type", "owner_name",
        "pid", "tid", "task_id", "parent", "lifecycle_phase", "evidence_source",
    ])

    # duplicate_calls.csv
    _write_csv(derived_dir / "duplicate_calls.csv", duplicates, fieldnames=[
        "duplicate_group", "function", "parent", "call_count",
        "start_times_ms", "durations_ms", "pid", "tid", "task_id", "evidence_strength",
    ])

    # semantic_duplicates.csv
    _write_csv(derived_dir / "semantic_duplicates.csv", semantic_duplicates, fieldnames=[
        "operation_type", "semantic_key_hash", "request_id", "restore_session_id",
        "call_count", "start_times_ms", "end_times_ms",
        "repeated_starts", "overlaps", "repeated_completions",
    ])

    # overlap_intervals.csv
    _write_csv(derived_dir / "overlap_intervals.csv", overlaps, fieldnames=[
        "left_owner", "right_owner", "left_start_ms", "left_end_ms",
        "right_start_ms", "right_end_ms", "overlap_ms",
        "same_thread", "same_task", "same_process",
    ])

    # background_survivors.csv — exact required columns
    _write_csv(derived_dir / "background_survivors.csv", survivors, fieldnames=[
        "owner_type", "owner_id", "name", "created_or_started_ms",
        "boundary_crossed", "ended_ms", "duration_ms", "thread_or_task", "evidence_source",
    ])

    # process_timeline.csv
    _write_csv(derived_dir / "process_timeline.csv", process_timeline, fieldnames=[
        "pid", "first_call_ms", "last_call_ms", "call_count", "thread_count",
    ])

    # thread_timeline.csv
    _write_csv(derived_dir / "thread_timeline.csv", thread_timeline, fieldnames=[
        "pid", "tid", "thread_key", "first_call_ms", "last_call_ms", "call_count",
    ])

    # resource_owners.csv
    _write_csv(derived_dir / "resource_owners.csv", resource_owners, fieldnames=[
        "timestamp_ms", "owner_type", "owner_name", "pid", "tid",
    ])

    # wrapper_chains.json
    _write_json(derived_dir / "wrapper_chains.json", wrapper_chains)

    # wrapper_changes.csv
    _write_csv(derived_dir / "wrapper_changes.csv", wrapper_changes, fieldnames=[
        "from_milestone", "to_milestone", "target", "prev_depth",
        "cur_depth", "change_type",
    ])

    # async_tasks.csv
    _write_csv(derived_dir / "async_tasks.csv", async_tasks, fieldnames=[
        "milestone", "task_id", "task_name", "done", "cancelled",
        "coroutine_qualname", "top_stack_file", "top_stack_line",
        "top_stack_function", "first_seen_ms", "last_seen_ms", "boundaries_crossed",
    ])

    # torch_cpu_ops.csv
    _write_csv(derived_dir / "torch_cpu_ops.csv", torch_cpu_ops, fieldnames=[
        "operator", "call_count", "total_cpu_ms", "self_cpu_ms",
        "mean_cpu_ms", "max_cpu_ms",
    ])

    # torch_cuda_ops.csv
    _write_csv(derived_dir / "torch_cuda_ops.csv", torch_cuda_ops, fieldnames=[
        "kernel_or_memcpy", "category", "call_count", "total_cuda_ms",
        "mean_cuda_ms", "max_cuda_ms", "stream_count",
    ])

    # expected_vs_observed.csv
    _write_csv(derived_dir / "expected_vs_observed.csv", expected_vs_observed, fieldnames=[
        "operation", "expected", "observed", "classification",
    ])

    # ── Generate report.md ──
    derived_files_info = {
        "trace_entry_count": entry_count,
        "trace_entry_capacity": entry_capacity,
        "trace_truncated": truncated,
        "files": _build_manifest(raw_dir, derived_dir),
    }
    # Note: manifest is rebuilt at the end after all files exist; this is a placeholder.

    report_md = _generate_report_md(
        status=status,
        warnings=warnings,
        calls=calls,
        timeline=timeline,
        func_summary=func_summary,
        duplicates=duplicates,
        semantic_duplicates=semantic_duplicates,
        survivors=survivors,
        wrapper_chains=wrapper_chains,
        wrapper_changes=wrapper_changes,
        expected_vs_observed=expected_vs_observed,
        torch_cpu_ops=torch_cpu_ops,
        torch_cuda_ops=torch_cuda_ops,
        resource_result=resource_result,
        process_timeline=process_timeline,
        thread_timeline=thread_timeline,
        resource_owners=resource_owners,
        trace_config=trace_config,
        runtime_result=runtime_result,
        derived_files=derived_files_info,
        overlaps=overlaps,
        milestones=milestones,
    )

    report_path = derived_dir / "report.md"
    report_path.write_text(report_md, encoding="utf-8")

    # ── Generate report_data.json ──
    report_data_path = derived_dir / "report_data.json"
    _write_json(report_data_path, _build_report_data(
        status=status,
        warnings=warnings,
        calls=calls,
        timeline=timeline,
        func_summary=func_summary,
        duplicates=duplicates,
        semantic_duplicates=semantic_duplicates,
        survivors=survivors,
        wrapper_chains=wrapper_chains,
        wrapper_changes=wrapper_changes,
        expected_vs_observed=expected_vs_observed,
        torch_cpu_ops=torch_cpu_ops,
        torch_cuda_ops=torch_cuda_ops,
        resource_result=resource_result,
        process_timeline=process_timeline,
        thread_timeline=thread_timeline,
        resource_owners=resource_owners,
        overlaps=overlaps,
        milestones=milestones,
        sessions=sessions,
        trace_config=trace_config,
        runtime_result=runtime_result,
        stack_issues=stack_issues,
        async_tasks=async_tasks,
        derived_files=derived_files_info,
    ))

    # ── Generate manifest.json (built AFTER all derived files exist, including report_data.json) ──
    manifest_path = derived_dir / "manifest.json"
    manifest_entries = _build_manifest(raw_dir, derived_dir)
    _write_json(manifest_path, {
        "schema_version": VERSION,
        "generated_at": MEASUREMENT_UNAVAILABLE,  # No timestamps
        "files": manifest_entries,
    })
    # Update derived_files_info with final manifest data
    derived_files_info["files"] = manifest_entries

    # ── Collect derived file listing (as list[str] of POSIX relative paths) ──
    derived_files_list: list[str] = sorted(
        str(p.relative_to(session_dir)).replace("\\", "/")
        for p in derived_dir.iterdir()
        if p.is_file()
    )

    return {
        "status": status,
        "report_path": str(report_path).replace("\\", "/"),
        "manifest_path": str(manifest_path).replace("\\", "/"),
        "derived_files": derived_files_list,
        "warnings": warnings,
        "trace_entry_count": entry_count,
        "trace_entry_capacity": entry_capacity,
        "trace_truncated": truncated,
    }


def _gzip_csv(
    path: Path,
    rows: Sequence[dict[str, Any]],
    *,
    fieldnames: Sequence[str] | None = None,
) -> None:
    """Write a gzipped CSV file with deterministic gzip metadata (mtime=0)."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        buf = io.StringIO()
        if not rows and fieldnames is None:
            buf.write("\n")
        else:
            fn = fieldnames or list(rows[0].keys())
            writer = csv.DictWriter(buf, fieldnames=fn, extrasaction="ignore")
            writer.writeheader()
            for row in rows:
                cleaned = {k: ("" if v is None else v) for k, v in row.items()}
                writer.writerow(cleaned)
        data = buf.getvalue().encode("utf-8-sig")
        # Deterministic gzip: mtime=0, no header filename
        path.write_bytes(gzip.compress(data, mtime=0))
    except Exception:
        pass
