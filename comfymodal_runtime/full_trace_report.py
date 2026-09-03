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

# sampling_deep_profile is already bounded by its producers.  Keep the report
# reader defensive as it may also consume hand-copied Golden telemetry.
_SAMPLING_DEEP_PROFILE_MAX_BYTES = 2 * 1024 * 1024

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


def _write_text_exact(path: Path, text: str) -> None:
    """Persist UTF-8 text without platform newline translation."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(str(text).replace("\r\n", "\n").replace("\r", "\n").encode("utf-8"))
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
        # This is a persisted diagnostic artifact, not a timed Python span.
        # Keep it out of calls before parent reconstruction and Golden profile
        # accounting; the structured copy is read from session/Golden evidence.
        if str(ev.get("name", "")) == "sampling_deep_profile":
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
    """Parse and normalize ``session_events.jsonl`` records.

    ``RuntimeTrace`` writes records as ``{"event": ..., "data": ...}``,
    while older fixtures stored the data fields at the top level.  Keep the
    latter shape working, but flatten the current shape and pair operation
    records by their opaque operation id before consumers see them.
    """
    path = session_dir / "raw" / "session_events.jsonl"
    if not path.exists():
        return []
    text = _safe_read_text(path)
    records = _parse_jsonl_lines(text)
    # Keep a marker for a malformed deep-profile line so unavailable evidence
    # is not mistaken for a clean run with no diagnostic event.
    for line in text.splitlines():
        if "sampling_deep_profile" in line:
            try:
                json.loads(line)
            except Exception:
                records.append({"event_type": "sampling_deep_profile", "_malformed": True})
    return _pair_session_events(records)


def _session_timestamp_ms(record: Mapping[str, Any]) -> float | None:
    """Convert a session record's wall-clock timestamp to milliseconds."""
    for key in ("timestamp_ms", "start_ms", "time_ms", "wall_unix_ms"):
        value = _safe_float(record.get(key), None)
        if value is not None:
            return value
    timestamp = _safe_float(record.get("timestamp"), None)
    return timestamp * 1000.0 if timestamp is not None else None


def _normalize_session_event(record: dict[str, Any]) -> dict[str, Any]:
    """Flatten one current or legacy session-event record.

    Missing timestamps and identifiers remain absent/``None``.  In
    particular, a missing wall timestamp is not represented as epoch zero.
    """
    if not isinstance(record.get("data"), dict) or "event" not in record:
        return dict(record)

    event_type = str(record.get("event", ""))
    data = dict(record["data"])
    normalized = dict(data)
    normalized["event"] = event_type
    normalized["event_type"] = event_type
    for key in ("timestamp", "timestamp_iso", "monotonic_ns"):
        if key in record:
            normalized[key] = record[key]

    timestamp_ms = _session_timestamp_ms(record)
    if timestamp_ms is not None:
        normalized.setdefault("timestamp_ms", timestamp_ms)
        normalized.setdefault("time_ms", timestamp_ms)

    # The runtime calls this field native_thread_id and uses asyncio_task_id;
    # report consumers use the shorter context names used by VizTracer calls.
    if "tid" not in normalized and "native_thread_id" in normalized:
        normalized["tid"] = normalized["native_thread_id"]
    if "task_id" not in normalized and "asyncio_task_id" in normalized:
        normalized["task_id"] = str(normalized["asyncio_task_id"])
    if "metadata" in normalized and "args" not in normalized and isinstance(normalized["metadata"], dict):
        normalized["args"] = normalized["metadata"]
    return normalized


def _pair_session_events(records: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    """Flatten session events and pair operation starts/ends by operation id."""
    normalized = [_normalize_session_event(record) for record in records]
    pending: dict[str, list[tuple[int, dict[str, Any]]]] = defaultdict(list)
    replacements: dict[int, dict[str, Any]] = {}
    consumed_end_indexes: set[int] = set()

    for index, record in enumerate(normalized):
        event_type = str(record.get("event_type", record.get("event", "")))
        operation_id = record.get("operation_id")
        if not operation_id:
            continue
        operation_id = str(operation_id)
        if event_type == "operation_start":
            pending[operation_id].append((index, record))
            continue
        if event_type != "operation_end":
            continue

        starts = pending.get(operation_id, [])
        if not starts:
            # Retain an unmatched end as incomplete evidence.
            continue
        start_index, start = starts.pop(0)
        consumed_end_indexes.add(index)
        paired = dict(start)
        paired["event"] = "operation"
        paired["event_type"] = "operation"
        paired["operation_id"] = operation_id
        paired["operation_end"] = dict(record)

        # End metadata is authoritative for completion/status, but does not
        # replace the start timestamp or start-side operation identity.
        for key in ("operation_type", "semantic_key_hash", "request_id", "restore_session_id",
                    "pid", "tid", "task_id"):
            if paired.get(key) in (None, "") and record.get(key) not in (None, ""):
                paired[key] = record[key]
        if isinstance(start.get("metadata"), dict) or isinstance(record.get("metadata"), dict):
            metadata = dict(start.get("metadata") or {})
            metadata.update(record.get("metadata") or {})
            paired["metadata"] = metadata
            paired.setdefault("args", metadata)
        paired["status"] = record.get("status") or start.get("status", "started")
        paired["end_monotonic_ns"] = record.get("end_monotonic_ns")
        paired["end_timestamp_ms"] = _session_timestamp_ms(record)

        start_ms = _session_timestamp_ms(start)
        end_ms = _session_timestamp_ms(record)
        if end_ms is None:
            end_ms = _safe_float(record.get("end_ms"), None)
        duration_ms = _safe_float(record.get("wall_ms"), None)
        if duration_ms is None and start_ms is not None and end_ms is not None:
            duration_ms = end_ms - start_ms
        paired["wall_ms"] = duration_ms
        paired["start_ms"] = start_ms
        paired["timestamp_ms"] = start_ms
        paired["time_ms"] = start_ms
        paired["duration_ms"] = duration_ms
        paired["end_ms"] = end_ms if end_ms is not None else (
            start_ms + duration_ms if start_ms is not None and duration_ms is not None else None
        )
        paired["complete"] = (
            start_ms is not None
            and paired["end_ms"] is not None
            and duration_ms is not None
        )
        replacements[start_index] = paired

    result: list[dict[str, Any]] = []
    for index, record in enumerate(normalized):
        if index in consumed_end_indexes:
            continue
        if str(record.get("event_type", record.get("event", ""))) == "operation_end":
            # An end without its matching start is retained, but its end
            # timestamp must never be mistaken for a fabricated start.
            record = dict(record)
            end_timestamp_ms = _session_timestamp_ms(record)
            if end_timestamp_ms is None:
                end_timestamp_ms = _safe_float(record.get("end_ms"), None)
            record["start_ms"] = None
            record["timestamp_ms"] = None
            record["time_ms"] = None
            record["duration_ms"] = None
            record["end_ms"] = end_timestamp_ms
            record["complete"] = False
        result.append(replacements.get(index, record))
    return result


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
    """Parse the scalar summary and merge its raw invocation-owned telemetry.

    Full-trace finalization intentionally strips nested values from
    ``runtime_result_summary.json``.  Golden telemetry therefore has a
    separate raw artifact, whose contents are authoritative for report-time
    sampling/E27 projection.
    """
    path = session_dir / "raw" / "runtime_result_summary.json"
    data: dict[str, Any] = {}
    if path.is_file():
        loaded = _json_load(path)
        if isinstance(loaded, dict):
            data = loaded

    telemetry_path = session_dir / "raw" / "golden_telemetry.json"
    telemetry = _json_load(telemetry_path) if telemetry_path.is_file() else None
    if isinstance(telemetry, Mapping):
        data["golden_telemetry"] = telemetry
        return data
    if data:
        return data

    # Golden runs persist their complete runtime result in the invocation-owned
    # cohort envelope rather than in the generic full-trace raw layout.  Keep
    # this fallback local to report generation; it does not alter instrumentation
    # or synthesize trace events.
    for attempt_path in sorted(session_dir.glob("attempt_*.json")):
        if (
            not attempt_path.is_file()
            or attempt_path.name.endswith("_events.json")
            or attempt_path.name.endswith(".json.v2ctl-provenance.json")
        ):
            continue
        attempt = _json_load(attempt_path)
        if isinstance(attempt, dict) and isinstance(attempt.get("golden_telemetry"), Mapping):
            return attempt
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

    # Add semantic operations from session events.  Paired RuntimeTrace
    # records have operation_type; lifecycle records (mark/state transition)
    # are emitted separately below so they are not misclassified as semantic
    # operations.
    for ev in sessions:
        op_type = str(ev.get("operation_type", ev.get("event_type", "")))
        if not ev.get("operation_type"):
            continue
        start_ms_raw = next((ev[k] for k in ("start_ms", "timestamp_ms", "time_ms") if k in ev), None)
        duration_raw = ev.get("duration_ms") if "duration_ms" in ev else None
        start_ms = _safe_float(start_ms_raw, None)
        dur_ms = _safe_float(duration_raw, None)
        if start_ms is None:
            continue
        if dur_ms is None:
            dur_ms = 0.0
        pid = _safe_int(ev.get("pid"), None)
        tid = _safe_int(ev.get("tid"), None)
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

    # Current RuntimeTrace lifecycle evidence is also wrapped in
    # session_events.jsonl.  Keep it as point evidence without inventing a
    # duration or a missing timestamp.
    for ev in sessions:
        if ev.get("operation_type"):
            continue
        event_type = str(ev.get("event_type", ev.get("event", "")))
        if event_type not in {"mark", "state_transition", "request_claimed", "identity_updated"}:
            continue
        start_ms = _safe_float(
            next((ev[k] for k in ("timestamp_ms", "time_ms") if k in ev), None),
            None,
        )
        if start_ms is None:
            continue
        name = str(ev.get("name", ""))
        if not name and event_type == "state_transition":
            name = str(ev.get("to", event_type))
        if not name:
            name = event_type
        pid = _safe_int(ev.get("pid"), None)
        tid = _safe_int(ev.get("tid"), None)
        timeline.append({
            "start_ms": round(start_ms, 3),
            "end_ms": round(start_ms, 3),
            "duration_ms": 0.0,
            "owner_type": "milestone" if event_type == "mark" else "lifecycle",
            "owner_name": name,
            "pid": pid,
            "tid": tid,
            "task_id": str(ev.get("task_id", "")),
            "parent": "",
            "lifecycle_phase": str(
                ev.get(
                    "phase",
                    (ev.get("metadata", {}).get("phase", event_type)
                     if isinstance(ev.get("metadata"), dict) else event_type),
                )
            ),
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
    explicit_hash = event.get("semantic_key_hash")
    if isinstance(explicit_hash, str) and explicit_hash:
        return explicit_hash
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
    req = str(event.get("request_id", args.get("request_id", trace_config.get("request_id", ""))))
    sess = str(event.get("restore_session_id", args.get("restore_session_id", trace_config.get("restore_session_id", ""))))
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
                "complete": bool(c.get("complete", True)),
            })
    for ev in sessions:
        op_type = str(ev.get("operation_type", ""))
        if op_type:
            start_ms = _safe_float(
                next((ev[k] for k in ("start_ms", "timestamp_ms", "time_ms") if k in ev), None),
                None,
            )
            dur_ms = _safe_float(ev.get("duration_ms"), None)
            if start_ms is None:
                start_us = None
                end_us = None
            else:
                start_us = start_ms * 1000.0
                end_us = start_us + dur_ms * 1000.0 if dur_ms is not None else None
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
                "end_us": end_us,
                "duration_us": dur_ms * 1000.0 if dur_ms is not None else None,
                "pid": _safe_int(ev.get("pid"), None),
                "tid": _safe_int(ev.get("tid"), None),
                "task_id": str(ev.get("task_id", "")),
                # Legacy semantic fixtures predate the paired-operation
                # completeness marker; their valid measured interval remains
                # complete unless the parser explicitly marked it otherwise.
                "complete": bool(ev.get("complete", True)),
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
        ts = _safe_float(ev.get("timestamp_ms", ev.get("wall_unix_ms")), None)
        if task_id not in tasks:
            tasks[task_id] = {
                "task_id": task_id,
                "task_name": str(ev.get("task_name", ev.get("name", ""))),
                "done": False,
                "cancelled": False,
                "coroutine_qualname": str(ev.get("coroutine_name", ev.get("coroutine_qualname", ""))),
                "top_stack_file": str(ev.get("stack_file", "")),
                "top_stack_line": _safe_int(ev.get("stack_line"), None),
                "top_stack_function": str(ev.get("stack_function", "")),
                "first_seen_ms": ts,
                "last_seen_ms": ts,
                "boundaries_crossed": [],
                "source": event_source,
            }
        entry = tasks[task_id]
        if ts is not None:
            entry["last_seen_ms"] = (
                ts if entry["last_seen_ms"] is None
                else max(entry["last_seen_ms"], ts)
            )
        if ev.get("done"):
            entry["done"] = True
        if ev.get("cancelled"):
            entry["cancelled"] = True
        if ev.get("milestone_start") and ts is not None:
            entry["first_seen_ms"] = (
                ts if entry["first_seen_ms"] is None
                else min(entry["first_seen_ms"], ts)
            )

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
            "first_seen_ms": (
                round(info["first_seen_ms"], 3)
                if info["first_seen_ms"] is not None else MEASUREMENT_UNAVAILABLE
            ),
            "last_seen_ms": (
                round(info["last_seen_ms"], 3)
                if info["last_seen_ms"] is not None else MEASUREMENT_UNAVAILABLE
            ),
            "boundaries_crossed": ";".join(info["boundaries_crossed"]),
        })
    return rows


# ---------------------------------------------------------------------------
# Sampling deep-profile evidence
# ---------------------------------------------------------------------------


def _sampling_profile_name(record: Mapping[str, Any]) -> bool:
    """Return whether *record* names the persisted deep-profile event."""
    for key in ("event_type", "event", "name"):
        value = record.get(key)
        if value:
            return str(value) == "sampling_deep_profile"
    return False


def _sampling_profile_payload(record: Mapping[str, Any]) -> Any:
    """Extract an artifact from RuntimeTrace or GoldenTelemetry event shapes."""
    if all(key in record for key in ("schema_version", "level", "status")):
        return record
    containers: list[Any] = [record]
    for key in ("data", "fields", "metadata", "args"):
        value = record.get(key)
        if isinstance(value, Mapping):
            containers.append(value)
    for container in containers:
        if not isinstance(container, Mapping):
            continue
        for key in ("metadata", "payload", "artifact", "sampling_deep_profile"):
            value = container.get(key)
            if isinstance(value, Mapping):
                return value
            if isinstance(value, str):
                parsed = _json_loads(value)
                if isinstance(parsed, Mapping):
                    return parsed
        if any(key in container for key in ("schema_version", "level", "status", "steps", "evals")):
            return container
    return None


def _sampling_profile_event_records(
    sessions: Sequence[dict[str, Any]], runtime_result: Mapping[str, Any],
) -> list[tuple[Any, str]]:
    """Collect session-event and Golden telemetry copies without touching calls."""
    candidates: list[tuple[Any, str]] = []
    for event in sessions:
        if _sampling_profile_name(event):
            candidates.append((_sampling_profile_payload(event), "session_events"))

    # GoldenTelemetryRecorder.to_json_dict() is normally carried by the runtime
    # result summary.  Walk only that telemetry/event domain; deep-profile data
    # is evidence, never an input to VizTracer accounting.
    telemetry = runtime_result.get("golden_telemetry") if isinstance(runtime_result, Mapping) else None
    if telemetry is None and isinstance(runtime_result, Mapping):
        telemetry = runtime_result.get("telemetry")

    def visit(value: Any, path: str, depth: int = 0) -> None:
        if depth > 5 or not isinstance(value, (Mapping, list, tuple)):
            return
        if isinstance(value, Mapping):
            if _sampling_profile_name(value):
                candidates.append((_sampling_profile_payload(value), f"golden_telemetry:{path}"))
                return
            for key, child in value.items():
                if key in {"events", "golden_telemetry", "telemetry", "fields", "data", "metadata"}:
                    visit(child, f"{path}.{key}", depth + 1)
        else:
            for index, child in enumerate(value[:256]):
                visit(child, f"{path}[{index}]", depth + 1)

    if telemetry is not None:
        visit(telemetry, "golden_telemetry")
    return candidates


def _sampling_number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    return _safe_float(value, None)


def _sampling_metric(payload: Mapping[str, Any], *names: str) -> tuple[float | None, str]:
    """Read a metric from established payload locations, without zero filling."""
    locations: list[tuple[str, Mapping[str, Any]]] = [("payload", payload)]
    for parent_name in ("reconciliation", "sampler_invocation", "summary"):
        parent = payload.get(parent_name)
        if isinstance(parent, Mapping):
            locations.append((parent_name, parent))
    for name in names:
        for location, container in locations:
            if name in container:
                return _sampling_number(container.get(name)), f"{location}.{name}"
    return None, ""


def _sampling_steps(payload: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    reconciliation = payload.get("reconciliation")
    for container in (reconciliation, payload):
        if isinstance(container, Mapping):
            value = container.get("steps_ms")
            if isinstance(value, list):
                return [item for item in value if isinstance(item, Mapping)]
    return []


def _build_sampling_step_breakdown(profiles: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    summary_names = (
        ("FIRST_PASS_WALL_MS", "first_pass_wall_ms"),
        ("SUBSEQUENT_STEPS_WALL_MS", "subsequent_steps_wall_ms"),
        ("TOTAL_STEP_UNION_MS", "total_step_union_ms"),
        ("SAMPLER_PARENT_WALL_MS", "sampler_parent_wall_ms"),
        ("UNACCOUNTED_MS", "unaccounted_ms"),
    )
    for profile_index, record in enumerate(profiles):
        payload = record.get("payload")
        if not isinstance(payload, Mapping):
            continue
        recon = payload.get("reconciliation") if isinstance(payload.get("reconciliation"), Mapping) else {}
        setup, setup_source = _sampling_metric(payload, "setup_ms", "setup_to_first_eval_ms")
        finalization, final_source = _sampling_metric(payload, "teardown_ms", "finalization_ms")
        if setup is not None:
            rows.append({"profile_index": profile_index, "kind": "setup", "label": "setup", "wall_ms": round(setup, 3), "source": setup_source})
        steps = _sampling_steps(payload)
        numeric_totals: list[float] = []
        for step in steps:
            row = {"profile_index": profile_index, "kind": "step", "label": f"step {step.get('step', len(numeric_totals))}", "source": "reconciliation.steps_ms"}
            for key in ("step", "pre_model_ms", "eval0_ms", "gap_ms", "eval1_ms", "post_model_ms", "total_ms", "residual_ms"):
                if key in step:
                    row[key] = step.get(key)
            total = _sampling_number(step.get("total_ms"))
            if total is not None:
                numeric_totals.append(total)
                row["wall_ms"] = round(total, 3)
            else:
                row["wall_ms"] = MEASUREMENT_UNAVAILABLE
            rows.append(row)
        if finalization is not None:
            final_row: dict[str, Any] = {
                "profile_index": profile_index,
                "kind": "finalization",
                "label": "finalization",
                "wall_ms": round(finalization, 3),
                "source": final_source,
            }
            final_eval = recon.get("teardown_final_eval_ms")
            if final_eval is not None:
                final_row["teardown_final_eval_ms"] = final_eval
            rows.append(final_row)

        # These labels are emitted even when unavailable.  In particular, row
        # zero is not treated as a first pass unless the producer recorded that
        # semantic explicitly.
        for display_name, raw_name in summary_names:
            value, source = _sampling_metric(payload, display_name, raw_name)
            if value is None and not source and display_name == "SAMPLER_PARENT_WALL_MS":
                value, source = _sampling_metric(payload, "authoritative_sampling_window_ms", "sampling_total_ms")
            if value is None and not source and display_name == "UNACCOUNTED_MS":
                value, source = _sampling_metric(payload, "sampling_residual_ms", "post_loop_residual_ms")
            rows.append({
                "profile_index": profile_index,
                "kind": "summary",
                "label": display_name,
                "wall_ms": round(value, 3) if value is not None else MEASUREMENT_UNAVAILABLE,
                "source": source or MEASUREMENT_UNAVAILABLE,
            })
    return rows


def _build_sampling_model_breakdown(profiles: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for profile_index, record in enumerate(profiles):
        payload = record.get("payload")
        if not isinstance(payload, Mapping):
            continue
        evals = payload.get("evals")
        per_eval = evals.get("per_eval") if isinstance(evals, Mapping) else []
        if isinstance(per_eval, list):
            for item in per_eval:
                if not isinstance(item, Mapping):
                    continue
                base = {
                    "profile_index": profile_index,
                    "scope": "eval",
                    "eval_index": item.get("index", MEASUREMENT_UNAVAILABLE),
                    "step": item.get("step", MEASUREMENT_UNAVAILABLE),
                    "row": item.get("row", MEASUREMENT_UNAVAILABLE),
                    "timing_domain": "host_monotonic",
                    "host_monotonic_ms": item.get("ms", MEASUREMENT_UNAVAILABLE),
                    "cuda_device_ms": item.get("forward_gpu_ms", MEASUREMENT_UNAVAILABLE),
                }
                rows.append(base)
                categories = item.get("categories_ms")
                if isinstance(categories, Mapping):
                    for category, value in sorted(categories.items(), key=lambda pair: str(pair[0])):
                        rows.append({**base, "scope": "eval_category", "category": str(category), "host_monotonic_ms": value, "cuda_device_ms": MEASUREMENT_UNAVAILABLE})
                blocks = item.get("blocks")
                if isinstance(blocks, Mapping):
                    blocks = [{"block": key, **(value if isinstance(value, Mapping) else {"total_ms": value})} for key, value in blocks.items()]
                if isinstance(blocks, list):
                    for block in blocks:
                        if isinstance(block, Mapping):
                            rows.append({**base, "scope": "eval_block", "block": block.get("block", MEASUREMENT_UNAVAILABLE), "host_monotonic_ms": block.get("total_ms", MEASUREMENT_UNAVAILABLE), "cuda_device_ms": MEASUREMENT_UNAVAILABLE, "attention_ms": block.get("attention_ms", MEASUREMENT_UNAVAILABLE), "mlp_ms": block.get("mlp_ms", MEASUREMENT_UNAVAILABLE), "norm_ms": block.get("norm_ms", MEASUREMENT_UNAVAILABLE)})

        categories = payload.get("categories_ms")
        if isinstance(categories, Mapping):
            for category, value in sorted(categories.items(), key=lambda pair: str(pair[0])):
                rows.append({"profile_index": profile_index, "scope": "aggregate_category", "category": str(category), "timing_domain": "host_monotonic", "host_monotonic_ms": value, "cuda_device_ms": MEASUREMENT_UNAVAILABLE})
        blocks = payload.get("blocks")
        if isinstance(blocks, list):
            for block in blocks:
                if isinstance(block, Mapping):
                    rows.append({"profile_index": profile_index, "scope": "aggregate_block", "block": block.get("block", MEASUREMENT_UNAVAILABLE), "timing_domain": "host_monotonic", "host_monotonic_ms": block.get("total_ms", MEASUREMENT_UNAVAILABLE), "cuda_device_ms": MEASUREMENT_UNAVAILABLE, "attention_ms": block.get("attention_ms", MEASUREMENT_UNAVAILABLE), "mlp_ms": block.get("mlp_ms", MEASUREMENT_UNAVAILABLE), "norm_ms": block.get("norm_ms", MEASUREMENT_UNAVAILABLE)})
        cuda = payload.get("cuda_timings_ms")
        if isinstance(cuda, Mapping):
            for name, value in sorted(cuda.items(), key=lambda pair: str(pair[0])):
                rows.append({"profile_index": profile_index, "scope": "cuda_device", "category": str(name), "timing_domain": "cuda_device_elapsed", "host_monotonic_ms": MEASUREMENT_UNAVAILABLE, "cuda_device_ms": value})
    return rows


def _build_human_sampling_model_breakdown(
    deep: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], bool]:
    """Collapse deep model evidence into readable, non-authoritative rows."""
    raw = deep.get("model_breakdown", [])
    raw = raw if isinstance(raw, list) else []
    has_eval_rows = any(
        isinstance(row, Mapping) and str(row.get("scope", "")).startswith("eval")
        for row in raw
    )
    groups: dict[tuple[Any, ...], dict[str, Any]] = {}
    non_additive = False
    for row in raw:
        if not isinstance(row, Mapping):
            continue
        scope = str(row.get("scope", "evidence"))
        if has_eval_rows and scope.startswith("aggregate"):
            continue
        domain = str(row.get("timing_domain", "host_monotonic"))
        if domain != "host_monotonic" or scope != "eval":
            non_additive = True
        phase = "evaluation"
        if scope == "eval_category":
            phase = str(row.get("category", "category"))
        elif scope == "eval_block":
            phase = "model_blocks"
        elif scope in {"aggregate_category", "aggregate_block", "cuda_device"}:
            phase = str(row.get("category", row.get("block", "aggregate")))
        key = (
            row.get("profile_index"), row.get("step", MEASUREMENT_UNAVAILABLE),
            row.get("eval_index", MEASUREMENT_UNAVAILABLE), phase, domain,
        )
        item = groups.setdefault(key, {
            "profile_index": row.get("profile_index", MEASUREMENT_UNAVAILABLE),
            "step": row.get("step", MEASUREMENT_UNAVAILABLE),
            "eval_index": row.get("eval_index", MEASUREMENT_UNAVAILABLE),
            "row": row.get("row", MEASUREMENT_UNAVAILABLE),
            "phase": phase,
            "timing_domain": domain,
            "count": 0,
            "host_values": [],
            "cuda_values": [],
        })
        item["count"] += 1
        host = _sampling_number(row.get("host_monotonic_ms"))
        cuda = _sampling_number(row.get("cuda_device_ms"))
        if host is not None:
            item["host_values"].append(host)
        if cuda is not None:
            item["cuda_values"].append(cuda)

    result: list[dict[str, Any]] = []
    for item in groups.values():
        hosts = item.pop("host_values")
        cuda = item.pop("cuda_values")
        item["host_monotonic_ms"] = round(sum(hosts), 3) if hosts else MEASUREMENT_UNAVAILABLE
        item["host_min_ms"] = round(min(hosts), 3) if hosts else MEASUREMENT_UNAVAILABLE
        item["host_max_ms"] = round(max(hosts), 3) if hosts else MEASUREMENT_UNAVAILABLE
        item["cuda_device_ms"] = round(sum(cuda), 3) if cuda else MEASUREMENT_UNAVAILABLE
        item["sample_count"] = item.pop("count")
        result.append(item)
    result.sort(key=lambda row: (
        str(row.get("profile_index")), str(row.get("step")),
        str(row.get("eval_index")), str(row.get("phase")),
    ))
    return result, non_additive


def _sampling_temporal_rows(
    deep: Mapping[str, Any],
    trace_config: Mapping[str, Any],
    sampling_node: Mapping[str, Any] | None,
) -> list[dict[str, Any]]:
    """Return aligned per-evaluation intervals only.

    A resource-sampler cadence is not a duration measurement and is never
    used as a cap here.  Rows are drawable only when the producer recorded
    explicit monotonic start/end timestamps *and* an explicit mapping from
    that monotonic clock to the Golden sampling/VizTracer axis.
    """
    records = deep.get("records", [])
    records = records if isinstance(records, list) else []
    rows: list[dict[str, Any]] = []
    for record in records:
        payload = record.get("payload") if isinstance(record, Mapping) else None
        if not isinstance(payload, Mapping):
            continue
        alignment = _sampling_clock_alignment(payload, sampling_node)
        if alignment is None:
            continue
        evals = payload.get("evals")
        per_eval = evals.get("per_eval") if isinstance(evals, Mapping) else []
        if not isinstance(per_eval, list):
            continue
        for item in per_eval:
            if not isinstance(item, Mapping):
                continue
            start = _sampling_number(item.get("start_monotonic_ns", item.get("start_ns")))
            end = _sampling_number(item.get("end_monotonic_ns", item.get("end_ns")))
            if start is None or end is None or end <= start:
                continue
            start_ms = alignment["to_golden_ms"](start)
            end_ms = alignment["to_golden_ms"](end)
            if start_ms is None or end_ms is None or end_ms <= start_ms:
                continue
            node_start = _sampling_number(sampling_node.get("start_ms")) if sampling_node else None
            node_end = _sampling_number(sampling_node.get("end_ms")) if sampling_node else None
            if node_start is not None and node_end is not None and (
                end_ms < node_start or start_ms > node_end
            ):
                continue
            rows.append({
                "label": (
                    f"eval step={item.get('step', MEASUREMENT_UNAVAILABLE)} "
                    f"row={item.get('row', MEASUREMENT_UNAVAILABLE)}"
                    + (
                        f" [{item.get('compute_or_skip')}]"
                        if item.get("compute_or_skip") else ""
                    )
                ),
                "start_ms": round(start_ms, 3),
                "end_ms": round(end_ms, 3),
                "interval_ms": round((end - start) / 1_000_000.0, 3),
                "source": "sampling_deep_profile.host_monotonic.aligned",
            })
        # ``timeline_steps`` is the bounded, authoritative step sequence from
        # sampling_deep_profile.  It is intentionally projected separately
        # from aggregate reconciliation rows and uses the same explicit clock
        # alignment as per-evaluation evidence.
        timeline_steps = payload.get("timeline_steps", [])
        if isinstance(timeline_steps, list):
            for item in timeline_steps:
                if not isinstance(item, Mapping):
                    continue
                start = _sampling_number(item.get("start_monotonic_ns", item.get("start_ns")))
                end = _sampling_number(item.get("end_monotonic_ns", item.get("end_ns")))
                if start is None or end is None or end <= start:
                    continue
                start_ms = alignment["to_golden_ms"](start)
                end_ms = alignment["to_golden_ms"](end)
                if start_ms is None or end_ms is None or end_ms <= start_ms:
                    continue
                rows.append({
                    "label": f"step {item.get('step_index', item.get('step', MEASUREMENT_UNAVAILABLE))}",
                    "start_ms": round(start_ms, 3),
                    "end_ms": round(end_ms, 3),
                    "interval_ms": round((end - start) / 1_000_000.0, 3),
                    "source": "sampling_deep_profile.timeline_steps.aligned",
                })
        # Setup and finalization are drawable only when the producer persisted
        # both sampling-window endpoints and an evaluation endpoint.  These are
        # local-window complements, never inferred from the report wall.
        window_start = _sampling_number(payload.get("sampling_window_start_monotonic_ns"))
        window_end = _sampling_number(payload.get("sampling_window_end_monotonic_ns"))
        eval_intervals = []
        for item in per_eval:
            if not isinstance(item, Mapping):
                continue
            start = _sampling_number(item.get("start_monotonic_ns", item.get("start_ns")))
            end = _sampling_number(item.get("end_monotonic_ns", item.get("end_ns")))
            if start is not None and end is not None and end > start:
                eval_intervals.append((start, end))
        if window_start is not None and eval_intervals:
            first_start = min(start for start, _end in eval_intervals)
            if first_start > window_start:
                rows.append({
                    "label": "setup",
                    "start_ms": round(alignment["to_golden_ms"](window_start), 3),
                    "end_ms": round(alignment["to_golden_ms"](first_start), 3),
                    "interval_ms": round((first_start - window_start) / 1_000_000.0, 3),
                    "source": "sampling_deep_profile.sampling_window.aligned",
                })
        if window_end is not None and eval_intervals:
            last_end = max(end for _start, end in eval_intervals)
            if window_end > last_end:
                rows.append({
                    "label": "finalization",
                    "start_ms": round(alignment["to_golden_ms"](last_end), 3),
                    "end_ms": round(alignment["to_golden_ms"](window_end), 3),
                    "interval_ms": round((window_end - last_end) / 1_000_000.0, 3),
                    "source": "sampling_deep_profile.sampling_window.aligned",
                })
    rows.sort(key=lambda row: (row["start_ms"], row["end_ms"], row["label"]))
    return rows


def _sampling_clock_alignment(
    payload: Mapping[str, Any],
    sampling_node: Mapping[str, Any] | None,
) -> dict[str, Any] | None:
    """Validate an explicit monotonic-to-Golden clock-origin declaration."""
    clocks = payload.get("clocks")
    clocks = clocks if isinstance(clocks, Mapping) else {}
    authoritative = payload.get("authoritative_wall")
    authoritative = authoritative if isinstance(authoritative, Mapping) else {}
    declaration = payload.get("alignment")
    declaration = declaration if isinstance(declaration, Mapping) else {}
    if not declaration:
        declaration = payload.get("clock_alignment")
        declaration = declaration if isinstance(declaration, Mapping) else {}

    clock = str(declaration.get("clock", clocks.get("host", ""))).strip().lower()
    source = str(
        declaration.get("source", declaration.get("reference", authoritative.get("source", "")))
    ).strip().lower()
    boundary = str(declaration.get("boundary", authoritative.get("boundary", ""))).strip().lower()
    if clock != "monotonic_ns" or source not in {"golden_sampling", "golden_sampling_node"}:
        return None
    if boundary and boundary not in {"sampling_start_to_sampling_end", "golden_sampling"}:
        return None

    # The origin must be explicit.  A same-clock assertion alone cannot map
    # absolute monotonic_ns values onto VizTracer's microsecond axis.
    mono_origin = _sampling_number(
        declaration.get(
            "monotonic_origin_ns",
            declaration.get(
                "origin_monotonic_ns",
                declaration.get("golden_sampling_start_monotonic_ns"),
            ),
        )
    )
    golden_origin_ms = _sampling_number(
        declaration.get(
            "golden_origin_ms",
            declaration.get(
                "origin_ms",
                declaration.get("golden_sampling_start_ms"),
            ),
        )
    )
    # A producer may declare the node's monotonic endpoints directly.  This
    # is equivalent evidence and avoids requiring a second origin object.
    if mono_origin is None and sampling_node is not None:
        mono_origin = _sampling_number(sampling_node.get("start_monotonic_ns"))
        golden_origin_ms = _sampling_number(sampling_node.get("start_ms"))
    if mono_origin is None or golden_origin_ms is None:
        return None

    def to_golden_ms(value: float) -> float:
        return golden_origin_ms + (value - mono_origin) / 1_000_000.0

    return {"clock": clock, "source": source, "to_golden_ms": to_golden_ms}


def _build_sampling_deep_evidence(
    sessions: Sequence[dict[str, Any]], runtime_result: Mapping[str, Any], warnings: list[str],
) -> dict[str, Any]:
    candidates = _sampling_profile_event_records(sessions, runtime_result)
    profiles: list[dict[str, Any]] = []
    by_payload: dict[str, int] = {}
    duplicate_count = 0
    for payload, source in candidates:
        if not isinstance(payload, Mapping):
            warnings.append("sampling_deep_profile_invalid: payload is not an object")
            profiles.append({"status": "invalid", "source": source, "payload": None, "error": "payload_not_object"})
            continue
        try:
            encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
        except Exception as exc:
            warnings.append(f"sampling_deep_profile_invalid: serialization failed ({type(exc).__name__})")
            profiles.append({"status": "invalid", "source": source, "payload": None, "error": "serialization_failed"})
            continue
        if len(encoded) > _SAMPLING_DEEP_PROFILE_MAX_BYTES:
            warnings.append(f"sampling_deep_profile_oversized: {len(encoded)} bytes")
            profiles.append({"status": "oversized", "source": source, "payload": None, "error": f"payload_bytes={len(encoded)}"})
            continue
        if not any(key in payload for key in ("schema_version", "level", "status", "steps", "evals")):
            warnings.append("sampling_deep_profile_invalid: unrecognized artifact shape")
            profiles.append({"status": "invalid", "source": source, "payload": None, "error": "unrecognized_shape"})
            continue
        key = hashlib.sha256(encoded).hexdigest()
        existing = by_payload.get(key)
        if existing is not None:
            duplicate_count += 1
            sources = profiles[existing].setdefault("sources", [])
            sources.append(source)
            continue
        status = str(payload.get("status", "unknown"))
        profiles.append({"status": status, "source": source, "sources": [source], "payload": json.loads(encoded.decode("utf-8")), "payload_sha256": key})
        by_payload[key] = len(profiles) - 1
        if status != "ok":
            warnings.append(f"sampling_deep_profile_non_ok: {status}")

    valid_payload_profiles = [profile for profile in profiles if isinstance(profile.get("payload"), Mapping)]
    if not candidates:
        overall = "unavailable"
    elif not valid_payload_profiles:
        recorded_statuses = {str(profile.get("status", "")) for profile in profiles}
        overall = "oversized" if recorded_statuses == {"oversized"} else "invalid"
    elif any(profile.get("status") == "ok" for profile in valid_payload_profiles):
        overall = "available"
    else:
        overall = "non_ok"
    return {
        "status": overall,
        "record_count": len(profiles),
        "duplicate_count": duplicate_count,
        "records": profiles,
        "step_breakdown": _build_sampling_step_breakdown(profiles),
        "model_breakdown": _build_sampling_model_breakdown(profiles),
        "warnings": [warning for warning in warnings if warning.startswith("sampling_deep_profile_")],
        "hierarchy_included": False,
    }


def _sampling_has_additive_reconciliation(deep: Mapping[str, Any]) -> bool:
    """Return true only for an explicit, numerically checkable decomposition."""
    records = deep.get("records", [])
    if not isinstance(records, list):
        return False
    for record in records:
        payload = record.get("payload") if isinstance(record, Mapping) else None
        if not isinstance(payload, Mapping):
            continue
        recon = payload.get("reconciliation")
        if not isinstance(recon, Mapping) or recon.get("residual_status") != "ok":
            continue
        total = _sampling_number(recon.get("sampling_total_ms"))
        accounted = _sampling_number(recon.get("accounted_ms"))
        residual = _sampling_number(recon.get("sampling_residual_ms"))
        if total is None or accounted is None or residual is None:
            continue
        if abs(total - accounted - residual) <= 0.01:
            return True
    return False


# ---------------------------------------------------------------------------
# Report-time E27 source/H2D projection
# ---------------------------------------------------------------------------

_SOURCE_H2D_UNAVAILABLE = MEASUREMENT_UNAVAILABLE
_SOURCE_H2D_FIELDS = (
    "SOURCE_TOTAL_WALL_MS",
    "SOURCE_SYSCALL_UNION_BUSY_MS",
    "read_count",
    "read_bytes",
    "max_inflight",
    "source_read_count",
    "source_read_bytes",
    "max_actual_source_inflight",
    "qd_occupancy_ms",
    "time_weighted_mean_qd",
    "QD_OCCUPANCY_MS",
    "TIME_WEIGHTED_MEAN_QD",
    "H2D_TOTAL_WALL_MS",
    "h2d_submitted_bytes",
    "h2d_completed_bytes",
    "H2D_SUBMITTED_BYTES",
    "H2D_COMPLETED_BYTES",
    "h2d_reconciliation_complete",
    "reconciliation_state",
    "SOURCE_H2D_OVERLAP_MS",
    "SOURCE_TO_GPU_READY_MS",
    "POST_SOURCE_H2D_TAIL_MS",
    "starvation_gaps",
    "STARVATION_GAPS",
    "quiescence",
    "quiescence_checkpoints",
    "fence",
    "QUIESCENCE_EVIDENCE",
    "FENCE_EVIDENCE",
    "producer_count",
    "observed_producer_count",
    "producer_ids",
    "qd_peak",
    "h2d_submission_count",
    "h2d_completion_count",
)

_SOURCE_H2D_STAGE_ROLES = {
    "golden_clip_load": "clip",
    "golden_unet_load": "unet",
    "golden_vae_load": "vae",
}
_SOURCE_H2D_ROLES = tuple(_SOURCE_H2D_STAGE_ROLES.values())
_SOURCE_H2D_ROLE_STAGES = {
    role: stage for stage, role in _SOURCE_H2D_STAGE_ROLES.items()
}


def _source_h2d_stages_from_value(value: Any) -> set[str]:
    """Extract only the canonical Golden load stages from a context value."""
    if not isinstance(value, str):
        return set()
    token = value.strip().lower().replace(".", "_").replace("-", "_").replace(" ", "_")
    return {stage for stage in _SOURCE_H2D_STAGE_ROLES if stage in token}


def _source_h2d_roles_from_value(value: Any) -> set[str]:
    """Extract transport roles without guessing from measurements."""
    if not isinstance(value, str) or not value.strip():
        return {"__invalid__"}
    token = value.strip().lower().replace(".", "_").replace("-", "_").replace(" ", "_")
    roles = {role for role in _SOURCE_H2D_ROLES if token == role or role in token.split("_")}
    return roles or {"__invalid__"}


def _source_h2d_identity(
    stage_context: str,
    record: Mapping[str, Any],
) -> tuple[set[str], set[str]]:
    """Resolve stage/role identity from the record and its traversal context."""
    stage_values: list[Any] = [stage_context]
    role_values: list[Any] = []
    for container in (record, record.get("actual_source"), record.get("actual_source_telemetry")):
        if not isinstance(container, Mapping):
            continue
        for key in ("name", "stage", "stage_name", "event", "event_type", "traversal", "context", "path"):
            if key in container:
                stage_values.append(container[key])
        if "role" in container:
            role_values.append(container["role"])
    stages: set[str] = set()
    for value in stage_values:
        if isinstance(value, (list, tuple)):
            for item in value:
                stages.update(_source_h2d_stages_from_value(item))
        else:
            stages.update(_source_h2d_stages_from_value(value))
    for container in (record, record.get("actual_source"), record.get("actual_source_telemetry")):
        if not isinstance(container, Mapping):
            continue
        for key in ("stage", "stage_name"):
            value = container.get(key)
            if value is not None and isinstance(value, str) and value.strip() and not _source_h2d_stages_from_value(value):
                stages.add("__invalid__")
    roles: set[str] = set()
    for value in role_values:
        roles.update(_source_h2d_roles_from_value(value))
    return stages, roles


def _source_h2d_unavailable(*, status: str = "unavailable", reason: str = "") -> dict[str, Any]:
    """Return a stable projection shape without manufacturing measurements."""
    result: dict[str, Any] = {
        "schema_version": "source-h2d-transport/1",
        "status": status,
        "availability": status,
        "reason": reason or "persisted E27 source/H2D evidence is unavailable",
        "stage": _SOURCE_H2D_UNAVAILABLE,
        "role": _SOURCE_H2D_UNAVAILABLE,
        "reconciliation": {
            "state": "unavailable",
            "complete": _SOURCE_H2D_UNAVAILABLE,
            "reason": "persisted H2D reconciliation evidence is unavailable",
            "submitted_bytes": _SOURCE_H2D_UNAVAILABLE,
            "completed_bytes": _SOURCE_H2D_UNAVAILABLE,
        },
        "h2d_reconciliation_complete": _SOURCE_H2D_UNAVAILABLE,
        "reconciliation_state": "unavailable",
        "timing_semantics": {
            "clock": "source/H2D monotonic intervals as persisted by E27",
            "overlap_is_union": True,
            "non_additive": True,
            "stage_wall_used": False,
            "waits_or_fences_inferred": False,
        },
        "evidence_source": _SOURCE_H2D_UNAVAILABLE,
        "stages": [],
        "stage_count": 0,
        "timestamp_lanes": [],
        "timestamp_axis": {
            "clock": _SOURCE_H2D_UNAVAILABLE,
            "start_ns": _SOURCE_H2D_UNAVAILABLE,
            "end_ns": _SOURCE_H2D_UNAVAILABLE,
        },
    }
    result.update({field: _SOURCE_H2D_UNAVAILABLE for field in _SOURCE_H2D_FIELDS})
    return result


def _source_h2d_number(value: Any) -> int | float | str:
    """Keep persisted scalar values, marking malformed values unavailable."""
    if isinstance(value, bool):
        return _SOURCE_H2D_UNAVAILABLE
    if isinstance(value, (int, float)):
        numeric = _safe_float(value, None)
        return value if numeric is not None and numeric >= 0 else _SOURCE_H2D_UNAVAILABLE
    return _SOURCE_H2D_UNAVAILABLE


def _source_h2d_first(container: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in container and container[key] is not None:
            return container[key]
    return None


def _source_h2d_candidates(
    runtime_result: Mapping[str, Any],
    sessions: Sequence[dict[str, Any]] = (),
    raw_evidence: Mapping[str, Any] | None = None,
) -> list[tuple[str, Mapping[str, Any]]]:
    """Find persisted Golden transport records, preserving their stage name."""
    roots: list[tuple[str, Any]] = []
    if isinstance(runtime_result, Mapping):
        for key in ("golden_telemetry", "telemetry"):
            if isinstance(runtime_result.get(key), Mapping):
                roots.append((key, runtime_result[key]))
        if any(key in runtime_result for key in ("actual_source", "actual_source_telemetry", "transport_stats", "stages")):
            roots.append(("runtime_result", runtime_result))

    candidates: list[tuple[str, Mapping[str, Any]]] = []
    seen: set[int] = set()
    # Copies of one record under the same traversal stage are duplicates.  The
    # same payload under different stage contexts is not: suppressing it would
    # make an ambiguous projection look like the first record was authoritative.
    seen_content: set[tuple[str, str]] = set()

    def add(stage: str, value: Any) -> None:
        if not isinstance(value, Mapping) or id(value) in seen:
            return
        content = value.get("actual_source", value.get("actual_source_telemetry", value))
        try:
            content_key = hashlib.sha256(
                json.dumps(content, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
            ).hexdigest()
        except Exception:
            content_key = ""
        context_stages = _source_h2d_stages_from_value(stage)
        context_key = "|".join(sorted(context_stages)) if context_stages else str(stage).strip().lower()
        content_identity = (content_key, context_key)
        if content_key and content_identity in seen_content:
            return
        seen.add(id(value))
        if content_key:
            seen_content.add(content_identity)
        candidates.append((stage or "golden_transport", value))

    def visit(value: Any, stage: str, depth: int = 0) -> None:
        if depth > 10 or not isinstance(value, Mapping):
            return
        named_stage = value.get("name")
        # Keep a useful parent traversal context when a transport wrapper has a
        # generic name such as ``transport_stats``.
        current_stage = (
            str(named_stage)
            if named_stage and _source_h2d_stages_from_value(named_stage)
            else stage
        )
        for key in ("transport_stats", "transport_telemetry"):
            child = value.get(key)
            if isinstance(child, Mapping):
                add(current_stage, child)
            elif isinstance(child, list):
                for item in child[:32]:
                    add(current_stage, item)
        for key in ("transport", "vae_load_decomposition"):
            child = value.get(key)
            if isinstance(child, Mapping):
                if key == "transport":
                    add(current_stage, child)
                else:
                    add(current_stage, child.get("transport"))
        if any(key in value for key in ("actual_source", "actual_source_telemetry")):
            add(current_stage, value)
        for key in ("stages", "details", "events", "data", "result"):
            child = value.get(key)
            if isinstance(child, Mapping):
                visit(child, current_stage, depth + 1)
            elif isinstance(child, list):
                for item in child[:64]:
                    visit(item, current_stage, depth + 1)

    for stage, root in roots:
        visit(root, stage)
    # A few Golden event copies are persisted in session_events rather than the
    # result summary.  They are still report-time evidence, not trace spans.
    for event in sessions:
        if not isinstance(event, Mapping):
            continue
        name = str(event.get("name", event.get("event_type", event.get("event", ""))))
        if name in {"vae_load_decomposition", "transport_stats", "golden_transport"}:
            visit(event, name)
    if isinstance(raw_evidence, Mapping):
        visit(raw_evidence, "golden_e27_source")
    return candidates


def _load_persisted_e27_raw(session_dir: Path | None) -> Mapping[str, Any] | None:
    """Read the bounded raw E27 artifact when the Golden copy is present."""
    if session_dir is None:
        return None
    path = session_dir / "raw" / "e27_source_mechanism.json"
    value = _json_load(path) if path.is_file() else None
    return value if isinstance(value, Mapping) else None


def _project_source_h2d_record(stage: str, record: Mapping[str, Any]) -> dict[str, Any]:
    actual = record.get("actual_source")
    if not isinstance(actual, Mapping):
        actual = record.get("actual_source_telemetry")
    if not isinstance(actual, Mapping):
        actual = record

    source_reads_value = actual.get("source_reads")
    source_reads: Mapping[str, Any] = source_reads_value if isinstance(source_reads_value, Mapping) else {}
    producer_report_value = actual.get("producer_report")
    producer_report: Mapping[str, Any] = producer_report_value if isinstance(producer_report_value, Mapping) else {}
    read_count = _source_h2d_first(actual, "source_read_count", "read_count")
    if read_count is None:
        read_count = _source_h2d_first(source_reads, "read_count", "copy_count")
    read_bytes = _source_h2d_first(actual, "source_bytes", "source_read_bytes", "read_bytes", "bytes_read")
    if read_bytes is None:
        read_bytes = source_reads.get("bytes")
    if read_count is None and producer_report:
        read_count = sum(
            int(row.get("read_count", 0))
            for row in producer_report.values()
            if isinstance(row, Mapping) and str(row.get("read_count", "")).isdigit()
        )
    if read_bytes is None and producer_report:
        read_bytes = sum(
            int(row.get("bytes", 0))
            for row in producer_report.values()
            if isinstance(row, Mapping) and str(row.get("bytes", "")).isdigit()
        )

    qd = actual.get("qd_occupancy_ms")
    if not isinstance(qd, Mapping):
        qd = actual.get("milliseconds_at_qd")
    if not isinstance(qd, Mapping):
        qd = record.get("producer_qd_occupancy")
    qd = dict(qd) if isinstance(qd, Mapping) else _SOURCE_H2D_UNAVAILABLE
    topology = actual.get("topology")
    topology = topology if isinstance(topology, Mapping) else {}
    def raw_value(*keys: str) -> Any:
        value = _source_h2d_first(actual, *keys)
        if value is None:
            value = _source_h2d_first(record, *keys)
        return value if value is not None else _SOURCE_H2D_UNAVAILABLE

    submitted = _source_h2d_first(actual, "h2d_submitted_bytes", "submitted_bytes")
    completed = _source_h2d_first(actual, "h2d_completed_bytes", "completed_bytes")
    if submitted is None:
        submitted = record.get("h2d_submitted_bytes")
    if completed is None:
        completed = record.get("h2d_completed_bytes")
    reconciliation_flag = actual.get("h2d_reconciliation_complete")
    if reconciliation_flag is None:
        reconciliation_flag = record.get("h2d_reconciliation_complete")
    reconciliation_details = actual.get("h2d_reconciliation")
    if not isinstance(reconciliation_details, Mapping):
        reconciliation_details = record.get("h2d_reconciliation")
    if reconciliation_flag is None and isinstance(reconciliation_details, Mapping):
        reconciliation_flag = _source_h2d_first(reconciliation_details, "complete", "ok")
    expected_h2d = _source_h2d_first(actual, "expected_h2d_bytes")
    if expected_h2d is None:
        topology_inputs = actual.get("topology_inputs")
        if isinstance(topology_inputs, Mapping):
            expected_h2d = topology_inputs.get("expected_h2d_bytes")
    if expected_h2d is None and isinstance(reconciliation_details, Mapping):
        expected_h2d = _source_h2d_first(reconciliation_details, "planned_bytes", "expected_bytes")
    if submitted is not None and completed is not None and submitted != completed:
        reconciliation_valid = False
    elif submitted is not None and expected_h2d is not None and submitted != expected_h2d:
        reconciliation_valid = False
    elif isinstance(reconciliation_flag, bool):
        reconciliation_valid = reconciliation_flag
    else:
        reconciliation_valid = None
    if reconciliation_valid is False:
        reconciliation_state = "invalid"
    elif reconciliation_valid is True:
        reconciliation_state = "valid"
    else:
        reconciliation_state = "unavailable"

    max_inflight = _source_h2d_first(actual, "max_actual_source_inflight", "max_inflight")
    if max_inflight is None:
        max_inflight = _source_h2d_first(record, "max_inflight")
    quiescence = _source_h2d_first(actual, "quiescence_evidence", "quiescence")
    if quiescence is None:
        quiescence = _source_h2d_first(actual, "quiescence_checkpoints")
    if quiescence is None:
        quiescence = _source_h2d_first(
            record, "quiescence_evidence", "quiescence", "qd_quiescence", "waits_quiescence"
        )
    fence = _source_h2d_first(actual, "source_fence_evidence", "source_fence_valid", "fence_evidence")
    if fence is None:
        fence = _source_h2d_first(record, "source_fence_evidence", "source_fence_valid", "fence_evidence")
    starvation = actual.get("starvation_gaps")
    if starvation is None:
        starvation = record.get("starvation_gaps")
    if not isinstance(starvation, list):
        starvation = _SOURCE_H2D_UNAVAILABLE

    def metric(*keys: str) -> Any:
        value = _source_h2d_first(actual, *keys)
        if value is None:
            value = _source_h2d_first(record, *keys)
        return _source_h2d_number(value)

    # H2D interval projections are valid only after the persisted event set has
    # reconciled.  Do not expose a partial interval as a complete transport.
    h2d_timing = reconciliation_state == "valid"
    projected = _source_h2d_unavailable(
        status="reconciliation_invalid" if reconciliation_state == "invalid" else "available",
        reason=(
            "persisted H2D submitted/completed bytes do not reconcile"
            if reconciliation_state == "invalid"
            else "persisted E27 source/H2D evidence"
        ),
    )
    projected.update({
        "status": projected["status"],
        "availability": projected["status"],
        "stage": stage,
        "role": _source_h2d_first(record, "role") or _source_h2d_first(actual, "role") or _SOURCE_H2D_UNAVAILABLE,
        "evidence_source": "golden_telemetry",
        "SOURCE_TOTAL_WALL_MS": metric("SOURCE_TOTAL_WALL_MS"),
        "SOURCE_SYSCALL_UNION_BUSY_MS": metric("SOURCE_SYSCALL_UNION_BUSY_MS"),
        "read_count": _source_h2d_number(read_count),
        "read_bytes": _source_h2d_number(read_bytes),
        "source_read_count": _source_h2d_number(read_count),
        "source_read_bytes": _source_h2d_number(read_bytes),
        "max_inflight": _source_h2d_number(max_inflight),
        "max_actual_source_inflight": _source_h2d_number(max_inflight),
        "qd_occupancy_ms": qd,
        "time_weighted_mean_qd": metric("time_weighted_mean_qd"),
        "QD_OCCUPANCY_MS": qd,
        "TIME_WEIGHTED_MEAN_QD": metric("time_weighted_mean_qd"),
        "h2d_submitted_bytes": _source_h2d_number(submitted),
        "h2d_completed_bytes": _source_h2d_number(completed),
        "H2D_SUBMITTED_BYTES": _source_h2d_number(submitted),
        "H2D_COMPLETED_BYTES": _source_h2d_number(completed),
        "h2d_reconciliation_complete": reconciliation_valid if reconciliation_valid is not None else _SOURCE_H2D_UNAVAILABLE,
        "reconciliation_state": reconciliation_state,
        "starvation_gaps": starvation,
        "quiescence": quiescence if quiescence is not None else _SOURCE_H2D_UNAVAILABLE,
        "quiescence_checkpoints": actual.get("quiescence_checkpoints", record.get("quiescence_checkpoints", _SOURCE_H2D_UNAVAILABLE)),
        "fence": fence if fence is not None else _SOURCE_H2D_UNAVAILABLE,
        "fallback": raw_value("fallback", "fallback_counts"),
        "poison": raw_value("poison", "poison_counts"),
        "region_coverage": topology.get("coverage_exact", _SOURCE_H2D_UNAVAILABLE),
        "region_gaps": topology.get("gaps", _SOURCE_H2D_UNAVAILABLE),
        "region_overlaps": topology.get("overlaps", _SOURCE_H2D_UNAVAILABLE),
        "region_duplicates": topology.get("unexpected_duplicates", _SOURCE_H2D_UNAVAILABLE),
        "reconciliation": {
            "state": reconciliation_state,
            "complete": reconciliation_valid if reconciliation_valid is not None else _SOURCE_H2D_UNAVAILABLE,
            "reason": "ok" if reconciliation_state == "valid" else (
                "submitted/completed bytes mismatch" if reconciliation_state == "invalid" else "persisted reconciliation flag unavailable"
            ),
            "submitted_bytes": _source_h2d_number(submitted),
            "completed_bytes": _source_h2d_number(completed),
        },
    })
    projected["h2d_reconciliation"] = projected["reconciliation"]
    projected["STARVATION_GAPS"] = projected["starvation_gaps"]
    projected["QUIESCENCE_EVIDENCE"] = projected["quiescence"]
    projected["FENCE_EVIDENCE"] = projected["fence"]
    lanes: list[dict[str, Any]] = []
    source_events = actual.get("actual_source_events", actual.get("source_events", []))
    if isinstance(source_events, list):
        for index, event in enumerate(source_events):
            if not isinstance(event, Mapping):
                continue
            start = _safe_int(event.get("syscall_enter_monotonic_ns", event.get("start_ns")), None)
            end = _safe_int(event.get("syscall_exit_monotonic_ns", event.get("end_ns")), None)
            if start is not None and end is not None and end >= start:
                lanes.append({
                    "lane": "source",
                    "label": f"producer={event.get('producer_id', index)}",
                    "start_ns": start,
                    "end_ns": end,
                    "duration_ms": round((end - start) / 1_000_000.0, 3),
                })
    h2d_events = actual.get("h2d_events", [])
    if isinstance(h2d_events, list):
        for index, event in enumerate(h2d_events):
            if not isinstance(event, Mapping):
                continue
            start = _safe_int(event.get("submit_ns", event.get("start_ns")), None)
            end = _safe_int(event.get("complete_ns", event.get("end_ns")), None)
            if start is not None and end is not None and end >= start:
                lanes.append({
                    "lane": "h2d",
                    "label": f"token={event.get('token', index)}",
                    "start_ns": start,
                    "end_ns": end,
                    "duration_ms": round((end - start) / 1_000_000.0, 3),
                })
    if lanes:
        projected["timestamp_axis"] = {
            "clock": "monotonic_ns",
            "start_ns": min(row["start_ns"] for row in lanes),
            "end_ns": max(row["end_ns"] for row in lanes),
            "source": "explicit *_monotonic_ns / submit_ns / complete_ns fields",
        }
    projected["timestamp_lanes"] = sorted(
        lanes, key=lambda item: (item["start_ns"], item["end_ns"], item["lane"], item["label"])
    )
    # Readable aggregate counters are derived only from persisted event rows or
    # explicit producer fields.  Missing values stay unavailable.
    producer_ids = sorted({
        str(event.get("producer_id")) for event in source_events
        if isinstance(event, Mapping) and event.get("producer_id") is not None
    }) if isinstance(source_events, list) else []
    projected["producer_count"] = _source_h2d_number(
        _source_h2d_first(actual, "producer_count")
        if _source_h2d_first(actual, "producer_count") is not None
        else (len(producer_ids) if producer_ids else None)
    )
    projected["observed_producer_count"] = len(producer_ids) if producer_ids else _SOURCE_H2D_UNAVAILABLE
    projected["producer_ids"] = producer_ids or _SOURCE_H2D_UNAVAILABLE
    projected["qd_peak"] = projected["max_actual_source_inflight"]
    projected["h2d_submission_count"] = (
        len(h2d_events) if isinstance(h2d_events, list) and h2d_events
        else _SOURCE_H2D_UNAVAILABLE
    )
    projected["h2d_completion_count"] = (
        sum(isinstance(row, Mapping) and row.get("complete_ns") is not None for row in h2d_events)
        if isinstance(h2d_events, list) and h2d_events else _SOURCE_H2D_UNAVAILABLE
    )
    for key in ("H2D_TOTAL_WALL_MS", "SOURCE_H2D_OVERLAP_MS", "SOURCE_TO_GPU_READY_MS", "POST_SOURCE_H2D_TAIL_MS"):
        projected[key] = metric(key) if h2d_timing else _SOURCE_H2D_UNAVAILABLE
    if projected["SOURCE_TOTAL_WALL_MS"] == _SOURCE_H2D_UNAVAILABLE:
        projected["status"] = "timestamps_unavailable" if reconciliation_state != "invalid" else "reconciliation_invalid"
        projected["availability"] = projected["status"]
        projected["reason"] = "persisted source interval timestamps are unavailable"
    return projected


def build_source_h2d_transport_projection(
    runtime_result: Mapping[str, Any] | None,
    *,
    sessions: Sequence[dict[str, Any]] = (),
    session_dir: Path | None = None,
) -> dict[str, Any]:
    """Project persisted E27 evidence without adding runtime instrumentation."""
    candidates = _source_h2d_candidates(
        runtime_result or {},
        sessions,
        _load_persisted_e27_raw(session_dir),
    )
    if not candidates:
        unavailable = _source_h2d_unavailable()
        unavailable["by_stage"] = {
            stage: _source_h2d_unavailable(
                reason=f"no persisted E27 transport record for {stage}"
            )
            for stage in _SOURCE_H2D_STAGE_ROLES
        }
        unavailable["by_role"] = {
            role: _source_h2d_unavailable(
                reason=f"no persisted E27 transport record for role {role}"
            )
            for role in _SOURCE_H2D_ROLES
        }
        return unavailable
    projections = [_project_source_h2d_record(stage, record) for stage, record in candidates]

    # Resolve identity independently from the measurements.  A projection is
    # usable only when one record has one canonical stage and its matching role;
    # there is deliberately no positional fallback here.
    identities: list[dict[str, Any]] = []
    for (stage_context, record), projection in zip(candidates, projections):
        stages, roles = _source_h2d_identity(stage_context, record)
        reason = ""
        if len(stages) > 1:
            reason = "ambiguous persisted E27 stage identity"
        elif len(roles) > 1:
            reason = "ambiguous persisted E27 role identity"
        elif not stages and len(roles) == 1 and next(iter(roles)) in _SOURCE_H2D_ROLE_STAGES:
            stages = {_SOURCE_H2D_ROLE_STAGES[next(iter(roles))]}
        elif not roles and len(stages) == 1:
            resolved_stage = next(iter(stages))
            if resolved_stage in _SOURCE_H2D_STAGE_ROLES:
                roles = {_SOURCE_H2D_STAGE_ROLES[resolved_stage]}
        if not stages or not roles:
            reason = reason or "persisted E27 stage/role identity is unavailable"
        elif len(stages) == 1 and len(roles) == 1:
            resolved_stage = next(iter(stages))
            resolved_role = next(iter(roles))
            if (
                resolved_stage not in _SOURCE_H2D_STAGE_ROLES
                or resolved_role not in _SOURCE_H2D_ROLES
                or _SOURCE_H2D_STAGE_ROLES[resolved_stage] != resolved_role
            ):
                reason = "persisted E27 stage and role disagree"
        identities.append({
            "stage": next(iter(stages)) if len(stages) == 1 else None,
            "role": next(iter(roles)) if len(roles) == 1 else None,
            "projection": projection,
            "reason": reason,
        })

    def get_transport_for_stage(
        stage: str,
        role: str,
    ) -> tuple[dict[str, Any] | None, str]:
        """Return the unique stage/role projection, or ``(None, reason)``."""
        expected_stage = stage if stage in _SOURCE_H2D_STAGE_ROLES else None
        expected_role = role if role in _SOURCE_H2D_ROLES else None
        if expected_stage is None or expected_role is None:
            return None, "requested E27 stage or role is not canonical"
        related = [
            identity for identity in identities
            if identity["stage"] == expected_stage or identity["role"] == expected_role
        ]
        reasons = sorted({str(identity["reason"]) for identity in related if identity["reason"]})
        matches = [
            identity for identity in related
            if identity["stage"] == expected_stage and identity["role"] == expected_role
        ]
        if len(matches) == 1 and len(related) == 1 and not reasons:
            projection = dict(matches[0]["projection"])
            projection["stage"] = expected_stage
            projection["role"] = expected_role
            return projection, ""
        if reasons:
            return None, reasons[0]
        if len(matches) > 1 or len(related) > 1:
            return None, f"ambiguous persisted E27 transport records for {expected_stage}/{expected_role}"
        return None, reasons[0] if reasons else f"no unique persisted E27 record for {expected_stage}/{expected_role}"

    def unavailable_mapping(stage: str, role: str, reason: str) -> dict[str, Any]:
        result = _source_h2d_unavailable(status="unavailable", reason=reason)
        result["stage"] = stage
        result["role"] = role
        return result

    by_stage: dict[str, dict[str, Any]] = {}
    by_role: dict[str, dict[str, Any]] = {}
    for stage, role in _SOURCE_H2D_STAGE_ROLES.items():
        match, reason = get_transport_for_stage(stage, role)
        value = match if match is not None else unavailable_mapping(stage, role, reason)
        by_stage[stage] = value
        by_role[role] = dict(value)

    # Keep every raw-derived projection auditable while exposing a direct
    # projection only when the complete candidate set has one unique identity.
    usable = [identity for identity in identities if not identity["reason"]]
    if len(usable) == 1 and len(identities) == 1:
        selected = dict(usable[0]["projection"])
        selected["stage"] = usable[0]["stage"]
        selected["role"] = usable[0]["role"]
    else:
        reason = (
            identities[0]["reason"]
            if len(identities) == 1 and identities[0]["reason"]
            else "ambiguous persisted E27 stage/role identities; use by_stage/by_role"
        )
        selected = _source_h2d_unavailable(
            reason=reason
        )
    selected["stages"] = projections
    selected["stage_count"] = len(projections)
    selected["by_stage"] = by_stage
    selected["by_role"] = by_role
    return selected


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

# Golden profiling deliberately lives in this report pipeline rather than in a
# second parser.  These names mirror golden_serial.STAGE_ORDER, but are kept
# local so that offline report generation remains stdlib-only.
_GOLDEN_ROOT_NAME = "golden_serial_execute"
_GOLDEN_STAGE_NAMES = (
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
_GOLDEN_PROFILE_THRESHOLD_MS = 50.0
_GOLDEN_PROFILE_RESIDUAL_MS = 25.0
_GOLDEN_PROFILE_RESIDUAL_PERCENT = 2.0


def _basename(name: Any) -> str:
    """Return the final component of a qualified trace name."""
    # VizTracer's ``VizEvent`` appends its source location to explicit spans:
    # ``name (file.py:line)``.  Keep that provenance in the raw call record,
    # but normalize only the semantic lookup name.
    value = str(name or "")
    if " (" in value:
        value = value.split(" (", 1)[0]
    return value.rsplit(".", 1)[-1]


def _golden_named_calls(
    calls: Sequence[dict[str, Any]], name: str,
) -> list[dict[str, Any]]:
    """Select one truthful spelling of a Golden span from raw calls.

    Explicit ``VizEvent`` spans are authoritative when present.  VizTracer's
    Python call hook may also record the same function on a resumed async
    context; preferring the explicit event avoids turning one real boundary
    into an ambiguity while retaining the hook-only compatibility path.
    """
    candidates = [call for call in calls if _basename(call.get("name")) == name]
    explicit = [call for call in candidates if call.get("category") == "FEE"]
    return explicit or candidates


def _golden_span(start_us: Any, end_us: Any) -> tuple[float, float] | None:
    """Return a valid interval, without manufacturing missing timestamps."""
    start = _safe_float(start_us, None)
    end = _safe_float(end_us, None)
    if start is None or end is None or end < start:
        return None
    return start, end


def _golden_same_context(left: Mapping[str, Any], right: Mapping[str, Any]) -> bool:
    """Return whether two trace records share the complete execution context."""
    if left.get("pid") is None or right.get("pid") is None:
        return False
    if left.get("tid") is None or right.get("tid") is None:
        return False
    return (
        left.get("pid") == right.get("pid")
        and left.get("tid") == right.get("tid")
        and str(left.get("task_id", "") or "") == str(right.get("task_id", "") or "")
    )


def _golden_union_ms(calls: Sequence[dict[str, Any]]) -> float:
    intervals = [
        (float(c["start_us"]), float(c["end_us"]))
        for c in calls
        if _golden_span(c.get("start_us"), c.get("end_us")) is not None
    ]
    return _ms(_total_interval_length(intervals))


def _golden_required_stages(
    trace_config: Mapping[str, Any],
    calls: Sequence[dict[str, Any]],
    *,
    context: Mapping[str, Any] | None = None,
) -> list[str]:
    """Resolve explicitly applicable canonical stages.

    A generic trace containing a function named ``golden_serial_execute`` is
    not assumed to have exercised every stage.  Producers can make the
    contract explicit with any of the established config spellings.  If a
    canonical stage is present, the trace is also treated as a canonical-stage
    claim and all non-durability stages are required.
    """
    configured: Any = None
    for key in (
        "required_canonical_stages",
        "golden_required_stages",
        "canonical_stages_required",
    ):
        if key in trace_config:
            configured = trace_config[key]
            break
    if isinstance(configured, (list, tuple)):
        requested = {_basename(v) for v in configured if str(v)}
        return [name for name in _GOLDEN_STAGE_NAMES if name in requested]
    if trace_config.get("golden_profile_require_canonical_stages") is True:
        strict = str(
            trace_config.get("output_durability_mode", trace_config.get("output_durability", ""))
        ).lower() == "strict"
        return [n for n in _GOLDEN_STAGE_NAMES if strict or n != "golden_durable_commit"]

    evidence_calls = (
        [c for c in calls if context is None or _golden_same_context(c, context)]
    )
    observed = {_basename(c.get("name")) for c in evidence_calls}
    if observed.intersection(_GOLDEN_STAGE_NAMES):
        strict = str(
            trace_config.get("output_durability_mode", trace_config.get("output_durability", ""))
        ).lower() == "strict"
        return [n for n in _GOLDEN_STAGE_NAMES if strict or n != "golden_durable_commit"]
    return []


def _golden_node(
    item: dict[str, Any],
    *,
    root_start_us: float,
    children: Sequence[dict[str, Any]],
    kind: str,
    parent: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build one auditable Golden profile span from an existing interval."""
    start = float(item["start_us"])
    end = float(item["end_us"])
    wall_ms = _ms(max(0.0, end - start))
    measured_children = [
        child for child in children
        if _golden_span(child.get("start_us"), child.get("end_us")) is not None
    ]
    child_sum_ms = sum(
        _ms(max(0.0, float(child["end_us"]) - float(child["start_us"])))
        for child in measured_children
    )
    child_union_ms = _golden_union_ms(measured_children)
    child_overlap_ms = child_sum_ms - child_union_ms
    residual_ms = wall_ms - child_union_ms
    coverage_pct = (child_union_ms / wall_ms * 100.0) if wall_ms > 0 else None
    subthreshold = [
        child for child in measured_children
        if _ms(max(0.0, float(child["end_us"]) - float(child["start_us"]))) <= _GOLDEN_PROFILE_THRESHOLD_MS
    ]
    displayed_children = [child for child in measured_children if child not in subthreshold]
    subthreshold_union_ms = _golden_union_ms(subthreshold)
    residual_pct = (residual_ms / wall_ms * 100.0) if wall_ms > 0 else None
    if not measured_children:
        residual_reason = "NO_TRACED_CHILDREN"
    elif displayed_children:
        residual_reason = "DISPLAYED_CHILDREN_GT50MS"
    else:
        residual_reason = "ONLY_SUBTHRESHOLD_CHILDREN"
    source = item.get("source_file") or (
        "session_events" if kind == "semantic" and item.get("source") == "session_event"
        else ("trace_call" if kind == "semantic" else "viztracer")
    )
    task_id = str(item.get("task_id", "") or "")
    pid = item.get("pid")
    tid = item.get("tid")
    thread_task = f"{pid}:{tid}" if pid is not None or tid is not None else ""
    if task_id:
        thread_task = f"{thread_task}/task:{task_id}" if thread_task else f"task:{task_id}"
    name = (
        str(item.get("operation_type"))
        if kind == "semantic"
        else _basename(item.get("name", ""))
    )
    complete = bool(item.get("complete", True)) and _golden_span(start, end) is not None
    needs_decomposition = (
        residual_ms > _GOLDEN_PROFILE_RESIDUAL_MS
        or (wall_ms > 0 and residual_ms / wall_ms * 100.0 > _GOLDEN_PROFILE_RESIDUAL_PERCENT)
    )
    return {
        "kind": kind,
        "name": name,
        "source": source,
        "source_file": item.get("source_file") or source,
        "source_line": item.get("source_line"),
        "event_index": item.get("event_index"),
        "parent_event_index": item.get("parent_event_index"),
        "parent_name": item.get("parent_name", "") if parent else "",
        "start_offset_ms": round(_ms(start - root_start_us), 3),
        "start_offset": round(_ms(start - root_start_us), 3),
        "start_offset_us": round(start - root_start_us, 3),
        "start_ms": round(_ms(start), 3),
        "end_ms": round(_ms(end), 3),
        "wall_ms": round(wall_ms, 3),
        "direct_child_count": len(measured_children),
        "direct_child_sum_ms": round(child_sum_ms, 3),
        "direct_child_union_ms": round(child_union_ms, 3),
        "direct_child_overlap_ms": round(child_overlap_ms, 3),
        "child_overlap_ms": round(child_overlap_ms, 3),
        "direct_children_sum_ms": round(child_sum_ms, 3),
        "direct_children_union_ms": round(child_union_ms, 3),
        "overlap_ms": round(child_overlap_ms, 3),
        "exclusive_residual_ms": round(residual_ms, 3),
        "residual_ms": round(residual_ms, 3),
        "residual_pct": round(residual_pct, 3) if residual_pct is not None else MEASUREMENT_UNAVAILABLE,
        "coverage_pct": round(coverage_pct, 3) if coverage_pct is not None else MEASUREMENT_UNAVAILABLE,
        "coverage": round(coverage_pct, 3) if coverage_pct is not None else MEASUREMENT_UNAVAILABLE,
        "coverage_ms": round(child_union_ms, 3),
        "subthreshold_child_count": len(subthreshold),
        "subthreshold_children_union_ms": round(subthreshold_union_ms, 3),
        "subthreshold_child_union_ms": round(subthreshold_union_ms, 3),
        "display_children_gt50ms": len(displayed_children),
        "traced_children": len(measured_children),
        "true_self_or_untraced_residual_ms": round(residual_ms, 3),
        "residual_reason": residual_reason,
        "pid": pid,
        "tid": tid,
        "task_id": task_id,
        "depth": item.get("depth", 0),
        "thread_task": thread_task,
        "complete": complete,
        "completeness": "complete" if complete else "incomplete",
        "needs_decomposition": needs_decomposition,
        "flag": "NEEDS_DECOMPOSITION" if needs_decomposition else "",
        # Upper-case aliases are the names used by the standalone and Modal
        # log projections.  Keep the established lower-case fields above for
        # JSON consumers that already read the Golden profile schema.
        "WALL_MS": round(wall_ms, 3),
        "DIRECT_CHILD_COUNT": len(measured_children),
        "DIRECT_CHILD_SUM_MS": round(child_sum_ms, 3),
        "DIRECT_CHILD_UNION_MS": round(child_union_ms, 3),
        "DIRECT_CHILD_OVERLAP_MS": round(child_overlap_ms, 3),
        "SUBTHRESHOLD_CHILD_COUNT": len(subthreshold),
        "SUBTHRESHOLD_CHILD_UNION_MS": round(subthreshold_union_ms, 3),
        "DISPLAY_CHILDREN_GT50MS": len(displayed_children),
        "TRACED_CHILDREN": len(measured_children),
        "RESIDUAL_MS": round(residual_ms, 3),
        "RESIDUAL_PCT": round(residual_pct, 3) if residual_pct is not None else MEASUREMENT_UNAVAILABLE,
        "TRUE_SELF_OR_UNTRACED_RESIDUAL_MS": round(residual_ms, 3),
        "RESIDUAL_REASON": residual_reason,
        "children": [],
    }


def _golden_refresh_display_summary(node: dict[str, Any]) -> None:
    """Align visibility fields with the tree after short wrappers are promoted."""
    for child in node.get("children", []):
        _golden_refresh_display_summary(child)

    displayed_count = len(node.get("children", []))
    residual_reason = (
        "NO_TRACED_CHILDREN"
        if node.get("traced_children", 0) == 0
        else (
            "DISPLAYED_CHILDREN_GT50MS"
            if displayed_count
            else "ONLY_SUBTHRESHOLD_CHILDREN"
        )
    )
    node["display_children_gt50ms"] = displayed_count
    node["DISPLAY_CHILDREN_GT50MS"] = displayed_count
    node["residual_reason"] = residual_reason
    node["RESIDUAL_REASON"] = residual_reason


def _golden_semantic_span(op: dict[str, Any]) -> dict[str, Any] | None:
    span = _golden_span(op.get("start_us"), op.get("end_us"))
    if span is None:
        return None
    start, end = span
    return {
        "operation_type": op.get("operation_type", ""),
        "name": op.get("operation_type", op.get("name", "")),
        "source": op.get("source", "semantic"),
        "source_file": op.get("source", "semantic"),
        "source_line": None,
        "start_us": start,
        "end_us": end,
        "duration_us": end - start,
        "pid": op.get("pid"),
        "tid": op.get("tid"),
        "task_id": op.get("task_id", ""),
        "complete": True,
    }


def _build_golden_profile(
    calls: list[dict[str, Any]],
    semantic_ops: list[dict[str, Any]],
    torch_events: list[dict[str, Any]],
    trace_config: Mapping[str, Any],
    *,
    trace_truncated: bool,
    raw_trace_nonempty: bool,
) -> dict[str, Any]:
    """Analyze one and only one claimed Golden serial root call."""
    roots = _golden_named_calls(calls, _GOLDEN_ROOT_NAME)
    configured_torch_enabled = trace_config.get("torch_enabled")
    if isinstance(configured_torch_enabled, bool):
        # An explicit setting is authoritative, including false.  A trace
        # artifact can exist as an empty/placeholder file without profiling
        # having been enabled.
        torch_enabled = configured_torch_enabled
    else:
        # Offline sessions from before torch_enabled was recorded use parsed
        # events (or the configured trace path) as the compatibility signal.
        torch_enabled = bool(torch_events) or bool(trace_config.get("torch_trace_path"))
    torch_disabled = not torch_enabled
    torch_state = "DISABLED" if torch_disabled else "ENABLED"
    reason = "complete"
    complete = True
    root: dict[str, Any] | None = None
    if len(roots) == 0:
        complete, reason = False, "missing golden_serial_execute root call"
    elif len(roots) != 1:
        complete, reason = False, f"ambiguous golden_serial_execute root call: found {len(roots)}"
    else:
        root = roots[0]
        if not bool(root.get("complete")) or _golden_span(root.get("start_us"), root.get("end_us")) is None:
            complete, reason = False, "incomplete golden_serial_execute root call"
        elif not raw_trace_nonempty:
            complete, reason = False, "raw VizTracer trace is empty"
        elif trace_truncated:
            complete, reason = False, "VizTracer trace is truncated"
        elif not torch_disabled and not torch_events:
            complete, reason = False, "Torch analysis failed: enabled trace is empty or invalid"

    if root is not None and complete:
        root_start = float(root["start_us"])
        root_end = float(root["end_us"])
        descendants = [
            c for c in calls
            if c is not root
            and c.get("start_us") is not None
            and c.get("end_us") is not None
            and root_start <= float(c["start_us"])
            and float(c["end_us"]) <= root_end
        ]
        incomplete_inside = [
            c for c in calls
            if c is not root and not c.get("complete", True)
            and (
                (c.get("start_us") is not None and root_start <= float(c["start_us"]) <= root_end)
                or (c.get("end_us") is not None and root_start <= float(c["end_us"]) <= root_end)
            )
        ]
        if incomplete_inside:
            bad = sorted(incomplete_inside, key=lambda c: (c.get("event_index", 0), c.get("name", "")))[0]
            complete = False
            reason = f"incomplete root-corrupting call: {bad.get('name', '')}"

        ambiguous = [
            c for c in descendants
            if c.get("parent_event_index") is None
            and c.get("pid") == root.get("pid")
            and c.get("tid") == root.get("tid")
            and abs(float(c["start_us"]) - root_start) < 0.001
            and abs(float(c["end_us"]) - root_end) < 0.001
        ]
        if complete and ambiguous:
            complete = False
            reason = f"ambiguous parenthood for call: {ambiguous[0].get('name', '')}"

        root_context_calls = [c for c in calls if _golden_same_context(c, root)]
        required = _golden_required_stages(
            trace_config,
            root_context_calls,
            context=root,
        )
        observed_stages = {
            _basename(c.get("name")) for c in descendants
            if _golden_same_context(c, root)
            and _basename(c.get("name")) in _GOLDEN_STAGE_NAMES
        }
        missing = [stage for stage in required if stage not in observed_stages]
        if complete and missing:
            complete = False
            reason = f"missing required canonical stage: {missing[0]}"

        parented_root_children = [
            c for c in descendants
            if c.get("parent_event_index") == root.get("event_index")
            and _golden_same_context(c, root)
        ]
        # Interval containment is useful accounting evidence even when the
        # existing reconstruction intentionally leaves an overlapping sibling
        # unparented.  Keep that call's parent blank; this is not async
        # ownership inference.  Cross-thread calls are excluded because their
        # relationship to this root is not established by the trace.
        ambiguous_root_children = [
            c for c in descendants
            if c.get("parent_event_index") is None
            and _golden_same_context(c, root)
            and c not in parented_root_children
        ]
        unparented_contained = [
            c for c in descendants
            if c.get("parent_event_index") is None and c not in parented_root_children
            and c.get("pid") == root.get("pid")
            and c.get("tid") == root.get("tid")
            and c.get("task_id", "") == root.get("task_id", "")
        ]
        root_children = parented_root_children + ambiguous_root_children
        root_intervals = [
            (float(c["start_us"]), float(c["end_us"]))
            for c in root_children
            if _golden_span(c.get("start_us"), c.get("end_us")) is not None
        ]
        root_union_ms = _ms(_total_interval_length(root_intervals))
        if complete and (root_end - root_start) < 0 or root_union_ms > _ms(root_end - root_start) + 0.001:
            complete = False
            reason = "invalid accounting: direct child union exceeds root wall"

        root_node = _golden_node(root, root_start_us=root_start, children=root_children, kind="python")

        calls_by_event_index = {
            c["event_index"]: c
            for c in calls
            if isinstance(c.get("event_index"), int)
        }
        children_by_parent: dict[int, list[dict[str, Any]]] = defaultdict(list)
        for child in descendants:
            parent_index = child.get("parent_event_index")
            parent = calls_by_event_index.get(parent_index) if isinstance(parent_index, int) else None
            if parent is not None and _golden_same_context(child, parent):
                children_by_parent[parent_index].append(child)

        def build_children(parent: dict[str, Any], parent_node: dict[str, Any]) -> None:
            direct = sorted(
                children_by_parent.get(parent.get("event_index"), [])
                + (unparented_contained if parent is root else []),
                key=lambda c: (float(c.get("start_us", 0)), float(c.get("end_us", 0)), str(c.get("name", "")), int(c.get("event_index", 0))),
            )
            def visit(child: dict[str, Any]) -> None:
                duration_ms = _ms(float(child["end_us"]) - float(child["start_us"]))
                if duration_ms <= _GOLDEN_PROFILE_THRESHOLD_MS:
                    # The threshold suppresses only the row, not its traced
                    # descendants.  Continue through hidden spans so a large
                    # operation is never lost merely because its wrapper is
                    # short.  It is still accounted by its actual parent via
                    # the direct-child interval union above.
                    hidden_children = sorted(
                        children_by_parent.get(child.get("event_index"), []),
                        key=lambda c: (
                            float(c.get("start_us", 0)),
                            float(c.get("end_us", 0)),
                            str(c.get("name", "")),
                            int(c.get("event_index", 0)),
                        ),
                    )
                    for hidden_child in hidden_children:
                        visit(hidden_child)
                    return
                child_node = _golden_node(
                    child,
                    root_start_us=root_start,
                    children=children_by_parent.get(child.get("event_index"), []),
                    kind="python",
                    parent=parent,
                )
                build_children(child, child_node)
                parent_node["children"].append(child_node)

            for child in direct:
                visit(child)

        build_children(root, root_node)
        _golden_refresh_display_summary(root_node)
        semantic_nodes: list[dict[str, Any]] = []
        for op in semantic_ops:
            span = _golden_semantic_span(op)
            if span is None:
                continue
            if not (root_start <= span["start_us"] and span["end_us"] <= root_end):
                continue
            if _ms(span["end_us"] - span["start_us"]) <= _GOLDEN_PROFILE_THRESHOLD_MS:
                continue
            semantic_nodes.append(
                _golden_node(span, root_start_us=root_start, children=[], kind="semantic")
            )
        semantic_nodes.sort(key=lambda n: (n["start_offset_ms"], n["end_ms"], n["name"], n.get("source", "")))
        canonical_spans = []
        for stage in _GOLDEN_STAGE_NAMES:
            for candidate in _golden_named_calls(descendants, stage):
                if not _golden_same_context(candidate, root):
                    continue
                canonical_node = _golden_node(
                    candidate,
                    root_start_us=root_start,
                    children=children_by_parent.get(candidate.get("event_index"), []),
                    kind="python",
                )
                build_children(candidate, canonical_node)
                _golden_refresh_display_summary(canonical_node)
                canonical_spans.append(canonical_node)
        canonical_spans.sort(key=lambda n: (n["start_offset_ms"], n["end_ms"], n["name"], n.get("event_index", 0)))
        return {
            "GOLDEN_PROFILE_COMPLETE": "YES" if complete else "NO",
            "GOLDEN_PROFILE_REASON": reason,
            "GOLDEN_PROFILE_TORCH": torch_state,
            "root": root_node,
            "nodes": root_node["children"] + semantic_nodes,
            "semantic_spans": semantic_nodes,
            "canonical_spans": canonical_spans,
            "required_canonical_stages": required,
            "observed_canonical_stages": sorted(observed_stages),
            "torch_cpu_ops": _build_torch_cpu_ops(torch_events),
            "torch_cuda_ops": _build_torch_cuda_ops(torch_events),
            "trace_truncated": trace_truncated,
            "raw_trace_nonempty": raw_trace_nonempty,
        }

    return {
        "GOLDEN_PROFILE_COMPLETE": "NO",
        "GOLDEN_PROFILE_REASON": reason,
        "GOLDEN_PROFILE_TORCH": torch_state,
        "root": None,
        "nodes": [],
        "semantic_spans": [],
        "canonical_spans": [],
        "required_canonical_stages": [],
        "observed_canonical_stages": [],
        "torch_cpu_ops": _build_torch_cpu_ops(torch_events),
        "torch_cuda_ops": _build_torch_cuda_ops(torch_events),
        "trace_truncated": trace_truncated,
        "raw_trace_nonempty": raw_trace_nonempty,
    }


def _golden_profile_json(profile: dict[str, Any]) -> dict[str, Any]:
    """Return the stable, JSON-facing Golden profile shape."""
    root = profile.get("root") or {}
    root_summary = {
        key: root.get(key, MEASUREMENT_UNAVAILABLE)
        for key in (
            "kind", "name", "source", "start_offset_ms", "start_offset", "wall_ms", "direct_child_sum_ms",
            "direct_child_union_ms", "direct_child_overlap_ms", "child_overlap_ms", "direct_children_sum_ms",
            "direct_children_union_ms", "overlap_ms", "exclusive_residual_ms",
            "residual_ms", "residual_pct", "coverage_pct", "coverage", "subthreshold_children_union_ms",
            "direct_child_count", "subthreshold_child_count", "subthreshold_child_union_ms",
            "display_children_gt50ms", "traced_children", "true_self_or_untraced_residual_ms",
            "residual_reason",
            "thread_task", "completeness", "needs_decomposition", "flag",
            "WALL_MS", "DIRECT_CHILD_COUNT", "DIRECT_CHILD_SUM_MS", "DIRECT_CHILD_UNION_MS",
            "DIRECT_CHILD_OVERLAP_MS", "SUBTHRESHOLD_CHILD_COUNT", "SUBTHRESHOLD_CHILD_UNION_MS",
            "DISPLAY_CHILDREN_GT50MS", "TRACED_CHILDREN", "RESIDUAL_MS", "RESIDUAL_PCT",
            "TRUE_SELF_OR_UNTRACED_RESIDUAL_MS", "RESIDUAL_REASON",
        )
    }
    if root:
        root_summary["children"] = root.get("children", [])
    complete = profile["GOLDEN_PROFILE_COMPLETE"] == "YES"
    root_wall = root.get("wall_ms") if root else MEASUREMENT_UNAVAILABLE
    needs_decomposition = bool(root.get("needs_decomposition")) if root else False

    def count_nodes(node_list: Sequence[dict[str, Any]]) -> int:
        return sum(1 + count_nodes(node.get("children", [])) for node in node_list)

    span_count = count_nodes(profile.get("nodes", []))
    return {
        "schema_version": "golden-profile/1",
        "GOLDEN_PROFILE_COMPLETE": profile["GOLDEN_PROFILE_COMPLETE"],
        "GOLDEN_PROFILE_REASON": profile["GOLDEN_PROFILE_REASON"],
        "GOLDEN_PROFILE_TORCH": profile["GOLDEN_PROFILE_TORCH"],
        "complete": complete,
        "reason": profile["GOLDEN_PROFILE_REASON"],
        "torch": profile["GOLDEN_PROFILE_TORCH"],
        "GOLDEN_PROFILE_ROOT_NAME": root.get("name") if root else MEASUREMENT_UNAVAILABLE,
        "GOLDEN_PROFILE_ROOT_WALL_MS": root_wall,
        "GOLDEN_PROFILE_SPAN_COUNT": span_count,
        "GOLDEN_PROFILE_NEEDS_DECOMPOSITION": needs_decomposition,
        "root": root_summary if root else None,
        "nodes": profile.get("nodes", []),
        "semantic_spans": profile.get("semantic_spans", []),
        "canonical_spans": profile.get("canonical_spans", []),
        "required_canonical_stages": profile.get("required_canonical_stages", []),
        "observed_canonical_stages": profile.get("observed_canonical_stages", []),
        "completeness": {
            "complete": complete,
            "reason": profile["GOLDEN_PROFILE_REASON"],
            "trace_truncated": profile.get("trace_truncated", False),
            "raw_trace_nonempty": profile.get("raw_trace_nonempty", False),
        },
        "VIZTRACER_CHILD_COVERAGE": profile.get("VIZTRACER_CHILD_COVERAGE", MEASUREMENT_UNAVAILABLE),
        "VIZTRACER_CHILD_COVERAGE_STATUS": profile.get(
            "VIZTRACER_CHILD_COVERAGE_STATUS", "unavailable"
        ),
        "CROSS_EVIDENCE_DECOMPOSITION": profile.get("CROSS_EVIDENCE_DECOMPOSITION", "NONE"),
        "sampling_temporal_rows": profile.get("sampling_temporal_rows", []),
        "unresolved_over_50ms": profile.get("unresolved_over_50ms", []),
        "sampling_reconciled": profile.get("sampling_reconciled", False),
        "sampling_decomposition_status": profile.get(
            "sampling_decomposition_status", "unavailable"
        ),
        "transport_reconciled": profile.get("transport_reconciled", False),
        "stage_evidence": profile.get("stage_evidence", {}),
    }


def _golden_bar(start_ms: float, end_ms: float, root_start_ms: float, root_end_ms: float) -> str:
    """Render a deterministic 100-column inclusive timeline bar."""
    width = 100
    span = root_end_ms - root_start_ms
    if span <= 0:
        return "█" + (" " * (width - 1))
    lo = max(0, min(width - 1, int(((start_ms - root_start_ms) / span) * width)))
    hi = max(lo + 1, min(width, int(((end_ms - root_start_ms) / span) * width + 0.999999)))
    return " " * lo + "█" * (hi - lo) + " " * (width - hi)


def _golden_profile_gantt(profile: dict[str, Any]) -> str:
    """Build the primary timestamped Golden Gantt."""
    lines = [
        "GOLDEN_PROFILE_COMPLETE=" + profile["GOLDEN_PROFILE_COMPLETE"],
        "GOLDEN_PROFILE_REASON=" + profile["GOLDEN_PROFILE_REASON"],
        "GOLDEN_PROFILE_TORCH=" + profile["GOLDEN_PROFILE_TORCH"],
        "VIZTRACER_CHILD_COVERAGE=" + str(profile.get("VIZTRACER_CHILD_COVERAGE", MEASUREMENT_UNAVAILABLE)),
        "VIZTRACER_CHILD_COVERAGE_STATUS=" + str(profile.get("VIZTRACER_CHILD_COVERAGE_STATUS", "unavailable")),
        "CROSS_EVIDENCE_DECOMPOSITION=" + str(profile.get("CROSS_EVIDENCE_DECOMPOSITION", "NONE")),
        "# Golden profile Gantt",
        "TIMELINE_COLUMNS=100",
    ]
    root = profile.get("root")
    if root:
        root_start = float(root["start_ms"])
        root_end = float(root["end_ms"])
        rows: list[tuple[int, float, float, str, str]] = [(0, root_start, root_end, root["name"], "root")]
        selected: dict[tuple[Any, ...], tuple[int, float, float, str, str]] = {}
        def select_node(node: dict[str, Any], level: int, *, preserve_existing: bool = False) -> None:
            key = (node.get("kind"), node.get("event_index"), node.get("name"), node.get("start_ms"))
            if not preserve_existing or key not in selected:
                selected[key] = (level, float(node["start_ms"]), float(node["end_ms"]), node["name"], node.get("kind", ""))
            for child in node.get("children", []):
                select_node(child, level + 1)

        for node in profile.get("nodes", []):
            select_node(node, 1)
        for node in profile.get("canonical_spans", []):
            select_node(node, max(1, int(node.get("depth", 1) or 1)), preserve_existing=True)
        rows.extend(selected.values())
        rows.sort(key=lambda row: (0 if row[4] == "root" else 1, row[0], row[1], row[2], row[3]))
        for level, start_ms, end_ms, name, kind in rows:
            label = ("  " * level) + name
            lines.append(f"{label} |{_golden_bar(start_ms, end_ms, root_start, root_end)}|")
            if name == "golden_sampling":
                for row in profile.get("sampling_temporal_rows", []):
                    start = _safe_float(row.get("start_ms"), None)
                    end = _safe_float(row.get("end_ms"), None)
                    if start is None or end is None:
                        continue
                    lines.append(
                        f"{('  ' * (level + 1))}{row.get('label', 'sampling evaluation')} |"
                        f"{_golden_bar(start, end, root_start, root_end)}|"
                    )
    else:
        lines.append("(no Golden root interval; timeline unavailable)")

    lines.extend([
        "",
        "TORCH_LANES=SEPARATE_CLOCK_DOMAIN_NOT_PLOTTED",
    ])
    return "\n".join(lines) + "\n"


def _sampling_breakdown_text(deep: Mapping[str, Any]) -> str:
    rows = deep.get("step_breakdown", [])
    rows = rows if isinstance(rows, list) else []
    human_rows, non_additive = _build_human_sampling_model_breakdown(deep)
    lines = [
        "SAMPLING SUMMARY",
        f"STATUS={deep.get('status', 'unavailable')}",
        f"RECORDS={deep.get('record_count', 0)} DUPLICATES_SUPPRESSED={deep.get('duplicate_count', 0)}",
        "FIRST_PASS_SEMANTICS=EXPLICIT_ONLY",
        f"TEMPORAL_ALIGNMENT={deep.get('temporal_alignment', 'unavailable')}",
        f"TEMPORAL_ALIGNMENT_REASON={deep.get('temporal_alignment_reason', 'no alignment evidence')}",
        "STEP | WALL_MS | SOURCE",
    ]
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        lines.append(
            f"{row.get('label', 'step')} | {row.get('wall_ms', MEASUREMENT_UNAVAILABLE)} | "
            f"{row.get('source', MEASUREMENT_UNAVAILABLE)}"
        )
    if not rows:
        lines.append(f"(unavailable) | {MEASUREMENT_UNAVAILABLE} | no persisted sampling breakdown")
    lines.extend([
        "",
        "DEEP SAMPLING BREAKDOWN",
        "MODEL_EVIDENCE=AGGREGATED_BY_STEP_EVALUATION_AND_PHASE",
        "TIMING_DOMAINS=HOST_MONOTONIC_AND_CUDA_DEVICE_ELAPSED_ARE_SEPARATE",
        "NON-ADDITIVE MODEL EVIDENCE=" + ("YES" if non_additive else "NO"),
        "STEP | EVAL | PHASE | COUNT | HOST_MONOTONIC_MS | CUDA_DEVICE_ELAPSED_MS | RANGE_MS",
    ])
    for row in human_rows:
        lines.append(
            f"{row.get('step', MEASUREMENT_UNAVAILABLE)} | "
            f"{row.get('eval_index', MEASUREMENT_UNAVAILABLE)} | "
            f"{row.get('phase', MEASUREMENT_UNAVAILABLE)} | {row.get('sample_count', 0)} | "
            f"{row.get('host_monotonic_ms', MEASUREMENT_UNAVAILABLE)} | "
            f"{row.get('cuda_device_ms', MEASUREMENT_UNAVAILABLE)} | "
            f"{row.get('host_min_ms', MEASUREMENT_UNAVAILABLE)}..{row.get('host_max_ms', MEASUREMENT_UNAVAILABLE)}"
        )
    if non_additive:
        lines.append("WARNING=MODEL TIMINGS MUST NOT BE SUMMED ACROSS PHASES OR CLOCK DOMAINS")
    if not human_rows:
        lines.append("(unavailable) | (unavailable) | (unavailable) | 0 | measurement_unavailable | measurement_unavailable | measurement_unavailable")
    return "\n".join(lines) + "\n"


def _transport_breakdown_text(transport: Mapping[str, Any]) -> str:
    lines = [
        "E27 TRANSPORT BREAKDOWN",
        f"STATUS={transport.get('status', MEASUREMENT_UNAVAILABLE)}",
        f"STAGE={transport.get('stage', MEASUREMENT_UNAVAILABLE)} ROLE={transport.get('role', MEASUREMENT_UNAVAILABLE)}",
        f"REASON={transport.get('reason', MEASUREMENT_UNAVAILABLE)}",
        "SUMMARY",
    ]
    for label, key in (
        ("SOURCE_TOTAL_WALL_MS", "SOURCE_TOTAL_WALL_MS"),
        ("SOURCE_SYSCALL_UNION_BUSY_MS", "SOURCE_SYSCALL_UNION_BUSY_MS"),
        ("SOURCE_READ_COUNT", "source_read_count"),
        ("SOURCE_READ_BYTES", "source_read_bytes"),
        ("OBSERVED_PRODUCER_COUNT", "observed_producer_count"),
        ("PRODUCERS", "producer_ids"),
        ("MAX_ACTUAL_SOURCE_INFLIGHT", "max_actual_source_inflight"),
        ("QD_PEAK", "qd_peak"),
        ("QD_MEAN", "time_weighted_mean_qd"),
        ("H2D_TOTAL_WALL_MS", "H2D_TOTAL_WALL_MS"),
        ("H2D_SUBMISSIONS", "h2d_submission_count"),
        ("H2D_COMPLETIONS", "h2d_completion_count"),
        ("H2D_SUBMITTED_BYTES", "h2d_submitted_bytes"),
        ("H2D_COMPLETED_BYTES", "h2d_completed_bytes"),
        ("SOURCE_H2D_OVERLAP_MS", "SOURCE_H2D_OVERLAP_MS"),
        ("POST_SOURCE_H2D_TAIL_MS", "POST_SOURCE_H2D_TAIL_MS"),
        ("FALLBACK", "fallback"),
        ("POISON", "poison"),
        ("REGION_COVERAGE", "region_coverage"),
        ("REGION_GAPS", "region_gaps"),
        ("REGION_OVERLAPS", "region_overlaps"),
        ("REGION_DUPLICATES", "region_duplicates"),
        ("RECONCILIATION_STATE", "reconciliation_state"),
    ):
        lines.append(f"{label}={transport.get(key, MEASUREMENT_UNAVAILABLE)}")
    lines.extend(["QD OCCUPANCY HISTOGRAM", "QD | OCCUPANCY_MS"])
    occupancy = transport.get("qd_occupancy_ms")
    if isinstance(occupancy, Mapping):
        for qd, value in sorted(occupancy.items(), key=lambda pair: str(pair[0])):
            lines.append(f"{qd} | {value}")
    else:
        lines.append(f"(unavailable) | {MEASUREMENT_UNAVAILABLE}")
    # Per-read/per-copy timestamps are machine evidence only.  Keeping them in
    # the JSON projection permits independent reconstruction without flooding
    # the human report with one line per transport event.
    lines.extend(["", "TIMESTAMP_LANES=JSON_ONLY"])
    axis = transport.get("timestamp_axis")
    if isinstance(axis, Mapping):
        axis_start = _sampling_number(axis.get("start_ns"))
        axis_end = _sampling_number(axis.get("end_ns"))
        if axis_start is not None and axis_end is not None:
            lines.append(
                f"TIMESTAMP_AXIS_CLOCK={axis.get('clock', MEASUREMENT_UNAVAILABLE)} "
                f"START_NS={axis_start} END_NS={axis_end}"
            )
    semantics = transport.get("timing_semantics")
    if isinstance(semantics, Mapping) and semantics.get("non_additive"):
        lines.append("WARNING=TRANSPORT OVERLAP IS A UNION; WALLS AND LANES ARE NOT ADDITIVE")
    return "\n".join(lines) + "\n"


def _augment_golden_profile(
    profile: dict[str, Any],
    deep: Mapping[str, Any],
    transport: Mapping[str, Any],
    trace_config: Mapping[str, Any],
) -> None:
    root = profile.get("root")
    sampling_node: Mapping[str, Any] | None = None
    if isinstance(root, Mapping):
        stack = [root]
        while stack:
            node = stack.pop()
            if node.get("name") == "golden_sampling":
                sampling_node = node
                break
            children = node.get("children")
            if isinstance(children, list):
                stack.extend(child for child in children if isinstance(child, Mapping))
    profile["sampling_temporal_rows"] = _sampling_temporal_rows(
        deep, trace_config, sampling_node,
    )
    deep["temporal_alignment"] = (
        "aligned" if profile["sampling_temporal_rows"]
        else ("unaligned" if deep.get("status") != "unavailable" else "unavailable")
    )
    deep["temporal_alignment_reason"] = (
        "explicit per-evaluation monotonic intervals mapped to Golden sampling"
        if profile["sampling_temporal_rows"]
        else "clock origin/alignment evidence unavailable; temporal rows not plotted"
    )
    root_coverage = _sampling_number(root.get("coverage_pct")) if isinstance(root, Mapping) else None
    profile["VIZTRACER_CHILD_COVERAGE"] = (
        round(root_coverage, 3) if root_coverage is not None
        else MEASUREMENT_UNAVAILABLE
    )
    profile["VIZTRACER_CHILD_COVERAGE_STATUS"] = (
        "complete" if profile.get("GOLDEN_PROFILE_COMPLETE") == "YES"
        else ("partial" if root is not None else "unavailable")
    )
    sampling_temporal_aligned = bool(profile["sampling_temporal_rows"])
    sampling_additive = _sampling_has_additive_reconciliation(deep)
    sampling_explained = sampling_temporal_aligned or sampling_additive
    lanes = transport.get("timestamp_lanes") if isinstance(transport, Mapping) else None
    lane_types = {
        str(row.get("lane")) for row in lanes
        if isinstance(row, Mapping)
    } if isinstance(lanes, list) else set()
    transport_explained = (
        transport.get("reconciliation_state") == "valid"
        and {"source", "h2d"}.issubset(lane_types)
        and _sampling_number(transport.get("SOURCE_TOTAL_WALL_MS")) is not None
        and _sampling_number(transport.get("H2D_TOTAL_WALL_MS")) is not None
    )
    if sampling_explained and transport_explained:
        decomposition = "ALIGNED_SAMPLING_AND_TRANSPORT"
    elif sampling_explained:
        decomposition = "ALIGNED_SAMPLING"
    elif transport_explained:
        decomposition = "ALIGNED_TRANSPORT"
    elif deep.get("status") != "unavailable" or transport.get("status") != "unavailable":
        decomposition = "UNALIGNED"
    else:
        decomposition = "NONE"
    profile["CROSS_EVIDENCE_DECOMPOSITION"] = decomposition
    profile["sampling_decomposition_status"] = (
        "aligned" if sampling_explained else (
            "unaligned" if deep.get("status") != "unavailable" else "unavailable"
        )
    )
    unresolved: list[dict[str, Any]] = []
    for node in _flatten_golden_nodes(root) if isinstance(root, Mapping) else []:
        wall = _sampling_number(node.get("wall_ms"))
        residual = _sampling_number(node.get("residual_ms", node.get("exclusive_residual_ms")))
        if wall is None or residual is None or wall <= _GOLDEN_PROFILE_THRESHOLD_MS or residual <= _GOLDEN_PROFILE_THRESHOLD_MS:
            continue
        name = str(node.get("name", ""))
        if name == "golden_sampling" and sampling_explained:
            continue
        if any(token in name.lower() for token in ("transport", "source", "h2d")) and transport_explained:
            continue
        unresolved.append({
            "name": name,
            "wall_ms": wall,
            "residual_ms": residual,
            "coverage": "VizTracer coverage",
            "evidence_source": "viztracer",
            "clock_domain": "host_monotonic",
            "reason": str(node.get("residual_reason", "untraced or self time")),
        })
    # Cross-evidence is intentionally not folded into VizTracer residuals.  If
    # persisted sampling/E27 data exists but cannot be aligned/reconciled, make
    # that limitation explicit; aligned regions are omitted from unresolved.
    if deep.get("status") not in {"unavailable", ""} and not sampling_explained:
        unresolved.append({
            "name": "sampling_window",
            "wall_ms": _sampling_number(deep.get("authoritative_sampling_window_ms")),
            "residual_ms": _sampling_number(deep.get("reconciliation", {}).get("sampling_residual_ms"))
            if isinstance(deep.get("reconciliation"), Mapping) else None,
            "coverage": "cross-evidence",
            "evidence_source": "sampling_deep_profile",
            "clock_domain": "monotonic_ns",
            "reason": str(deep.get("temporal_alignment_reason", "sampling clock alignment unavailable")),
        })
    if transport.get("status") not in {"unavailable", ""} and not transport_explained:
        unresolved.append({
            "name": "source/H2D transport",
            "wall_ms": _sampling_number(transport.get("SOURCE_TOTAL_WALL_MS")),
            "residual_ms": None,
            "coverage": "cross-evidence",
            "evidence_source": "E27 persisted transport",
            "clock_domain": "monotonic_ns",
            "reason": str(transport.get("reason", "E27 reconciliation or timestamp coverage unavailable")),
        })
    profile["unresolved_over_50ms"] = unresolved
    profile["sampling_reconciled"] = sampling_explained
    profile["transport_reconciled"] = transport_explained
    profile["stage_evidence"] = {
        stage: {
            "source": "VizTracer parent clock",
            "clock_domain": "host_monotonic",
            "transport_role": role,
            "transport_clock": "monotonic_ns separate local mini-Gantt"
            if role in {"clip", "unet", "vae"} else MEASUREMENT_UNAVAILABLE,
        }
        for stage, role in {
            "golden_clip_load": "clip",
            "golden_clip_forward": "clip",
            "golden_unet_load": "unet",
            "golden_sampler_prepare": "sampler",
            "golden_vae_load": "vae",
            "golden_sampling": "sampling_window",
            "golden_vae_decode": "vae_decode",
        }.items()
    }


def _flatten_golden_nodes(root: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    result: list[Mapping[str, Any]] = []
    stack: list[Mapping[str, Any]] = [root]
    while stack:
        node = stack.pop()
        result.append(node)
        children = node.get("children")
        if isinstance(children, list):
            stack.extend(child for child in children if isinstance(child, Mapping))
    return result


def _generate_golden_profile_report(profile: dict[str, Any]) -> str:
    """Generate the standalone Golden profile report."""
    data = _golden_profile_json(profile)
    lines = [
        "GOLDEN_PROFILE_COMPLETE=" + data["GOLDEN_PROFILE_COMPLETE"],
        "GOLDEN_PROFILE_REASON=" + data["GOLDEN_PROFILE_REASON"],
        "GOLDEN_PROFILE_TORCH=" + data["GOLDEN_PROFILE_TORCH"],
        "GOLDEN_PROFILE_ROOT_NAME=" + str(data["GOLDEN_PROFILE_ROOT_NAME"]),
        "GOLDEN_PROFILE_ROOT_WALL_MS=" + str(data["GOLDEN_PROFILE_ROOT_WALL_MS"]),
        "GOLDEN_PROFILE_SPAN_COUNT=" + str(data["GOLDEN_PROFILE_SPAN_COUNT"]),
        "GOLDEN_PROFILE_NEEDS_DECOMPOSITION=" + str(data["GOLDEN_PROFILE_NEEDS_DECOMPOSITION"]),
        "NEEDS_DECOMPOSITION="
        + ("YES" if data["GOLDEN_PROFILE_NEEDS_DECOMPOSITION"] else "NO"),
        "VIZTRACER_CHILD_COVERAGE=" + str(data.get("VIZTRACER_CHILD_COVERAGE", MEASUREMENT_UNAVAILABLE)),
        "VIZTRACER_CHILD_COVERAGE_STATUS=" + str(data.get("VIZTRACER_CHILD_COVERAGE_STATUS", "unavailable")),
        "CROSS_EVIDENCE_DECOMPOSITION=" + str(data.get("CROSS_EVIDENCE_DECOMPOSITION", "NONE")),
        "# Golden execution profile",
        "",
        "## Summary",
        f"- Root: {data['root']['name'] if data['root'] else MEASUREMENT_UNAVAILABLE}",
        f"- Required canonical stages: {', '.join(data['required_canonical_stages']) or '(none claimed)' }",
        f"- Observed canonical stages: {', '.join(data['observed_canonical_stages']) or '(none)' }",
        "",
        "## Spans over 50.000 ms",
        "",
        "| Name | Kind | Source | Start offset (ms) | WALL_MS | DIRECT_CHILD_COUNT | DIRECT_CHILD_SUM_MS | DIRECT_CHILD_UNION_MS | DIRECT_CHILD_OVERLAP_MS | SUBTHRESHOLD_CHILD_COUNT | SUBTHRESHOLD_CHILD_UNION_MS | DISPLAY_CHILDREN_GT50MS | TRACED_CHILDREN | RESIDUAL_MS | RESIDUAL_PCT | TRUE_SELF_OR_UNTRACED_RESIDUAL_MS | RESIDUAL_REASON | Thread/task | Completeness | Flag |",
        "|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---|---|---|",
    ]
    def add_node(node: dict[str, Any], level: int = 0) -> None:
        indent = "  " * level
        lines.append(
            f"| {indent}{node['name']} | {node['kind']} | {node['source']} | {node['start_offset_ms']} "
            f"| {node['WALL_MS']} | {node['DIRECT_CHILD_COUNT']} | {node['DIRECT_CHILD_SUM_MS']} "
            f"| {node['DIRECT_CHILD_UNION_MS']} | {node['DIRECT_CHILD_OVERLAP_MS']} "
            f"| {node['SUBTHRESHOLD_CHILD_COUNT']} | {node['SUBTHRESHOLD_CHILD_UNION_MS']} "
            f"| {node['DISPLAY_CHILDREN_GT50MS']} | {node['TRACED_CHILDREN']} | {node['RESIDUAL_MS']} "
            f"| {node['RESIDUAL_PCT']} | {node['TRUE_SELF_OR_UNTRACED_RESIDUAL_MS']} "
            f"| {node['RESIDUAL_REASON']} | {node['thread_task']} | {node['completeness']} "
            f"| {node['flag']} NEEDS_DECOMPOSITION={'YES' if node['needs_decomposition'] else 'NO'} |"
        )
        for child in node.get("children", []):
            add_node(child, level + 1)
    if data["root"]:
        add_node(data["root"])
        for node in data["semantic_spans"]:
            add_node(node, 1)
    else:
        unavailable = " | ".join(["measurement_unavailable"] * 15)
        lines.append(f"| (none) | (none) | (none) | {unavailable} | incomplete | measurement_unavailable |")
    lines.extend([
        "",
        "Residual is not causal. DIRECT_CHILD_OVERLAP_MS=DIRECT_CHILD_SUM_MS-DIRECT_CHILD_UNION_MS; "
        "RESIDUAL_MS=parent WALL_MS-DIRECT_CHILD_UNION_MS. Children at or below 50 ms "
        "remain in accounting but are not rendered as rows. TRACED_CHILDREN=0 and "
        "RESIDUAL_REASON=NO_TRACED_CHILDREN "
        "means no measured direct children; RESIDUAL_REASON=ONLY_SUBTHRESHOLD_CHILDREN "
        "means DISPLAY_CHILDREN_GT50MS=0; RESIDUAL_REASON=DISPLAYED_CHILDREN_GT50MS "
        "means larger descendants are rendered recursively.",
        "",
        "## Torch analysis",
        "",
        "Torch CPU/CUDA clock alignment is unproven; the Gantt keeps those lanes in a separate table.",
        "",
        "## UNRESOLVED >50ms AREAS",
    ])
    unresolved = data.get("unresolved_over_50ms", [])
    if unresolved:
        for area in unresolved:
            lines.append(
                f"- {area.get('name', '')}: {area.get('coverage', 'remaining')} "
                f"wall_ms={area.get('wall_ms')} residual_ms={area.get('residual_ms')} "
                f"clock={area.get('clock_domain', MEASUREMENT_UNAVAILABLE)} "
                f"reason={area.get('reason', 'not established')}"
            )
    else:
        lines.append("None; separately explained sampling and transport evidence is excluded.")
    return "\n".join(lines) + "\n"


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
    golden_profile: dict[str, Any] | None = None,
    sampling_deep_evidence: dict[str, Any] | None = None,
    source_h2d_transport: dict[str, Any] | None = None,
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

    # ── Golden serial profile ──
    if golden_profile is not None:
        _w("## Golden serial profile")
        _w("")
        _w(f"- **GOLDEN_PROFILE_COMPLETE**: {golden_profile.get('GOLDEN_PROFILE_COMPLETE', 'NO')}")
        _w(f"- **GOLDEN_PROFILE_REASON**: {golden_profile.get('GOLDEN_PROFILE_REASON', '')}")
        _w(f"- **GOLDEN_PROFILE_TORCH**: {golden_profile.get('GOLDEN_PROFILE_TORCH', 'DISABLED')}")
        _w(f"- Profile spans over 50 ms: {len(golden_profile.get('nodes', []))}")
        _w(f"- **VIZTRACER_CHILD_COVERAGE**: {golden_profile.get('VIZTRACER_CHILD_COVERAGE', MEASUREMENT_UNAVAILABLE)}")
        _w(f"- **VIZTRACER_CHILD_COVERAGE_STATUS**: {golden_profile.get('VIZTRACER_CHILD_COVERAGE_STATUS', 'unavailable')}")
        _w(f"- **CROSS_EVIDENCE_DECOMPOSITION**: {golden_profile.get('CROSS_EVIDENCE_DECOMPOSITION', 'NONE')}")
        _w("")
        _w("## Golden Gantt")
        _w("")
        _w("```text")
        lines.extend(_golden_profile_gantt(golden_profile).rstrip("\n").splitlines())
        _w("```")
        _w("")
        unresolved = golden_profile.get("unresolved_over_50ms", [])
        _w("## UNRESOLVED >50ms AREAS")
        _w("")
        if unresolved:
            _w("Areas below are residuals not separately explained by sampling or transport evidence.")
            for area in unresolved:
                _w(f"- {area.get('name', '')}: wall_ms={area.get('wall_ms')} residual_ms={area.get('residual_ms')}")
        else:
            _w("None; sampling and transport are separate evidence domains when available.")
        _w("")

    # E27 source/H2D evidence is a report-time projection of persisted Golden
    # telemetry.  It is deliberately not a VizTracer child or a Gantt lane:
    # overlap is a union/non-additive diagnostic, not a decomposition sum.
    transport = source_h2d_transport or _source_h2d_unavailable()
    _w("## SOURCE/H2D TRANSPORT")
    _w("")
    _w(f"- **status**: {transport.get('status', _SOURCE_H2D_UNAVAILABLE)}")
    _w(f"- **stage**: {transport.get('stage', _SOURCE_H2D_UNAVAILABLE)}")
    _w(f"- **role**: {transport.get('role', _SOURCE_H2D_UNAVAILABLE)}")
    _w(f"- **reason**: {transport.get('reason', _SOURCE_H2D_UNAVAILABLE)}")
    _w("")
    _w("| Metric | Value |")
    _w("|---|---:|")
    for field in _SOURCE_H2D_FIELDS:
        value = transport.get(field, _SOURCE_H2D_UNAVAILABLE)
        if isinstance(value, (dict, list)):
            value = json.dumps(value, sort_keys=True, separators=(",", ":"))
        _w(f"| {field} | {value} |")
    reconciliation = transport.get("reconciliation", {})
    _w(f"| reconciliation_state | {reconciliation.get('state', 'unavailable') if isinstance(reconciliation, Mapping) else 'unavailable'} |")
    _w("")
    _w("Timing semantics: SOURCE_H2D_OVERLAP_MS is an interval union and is non-additive with source/H2D walls. No waits, fences, or timestamps are inferred from a Golden stage wall; unavailable and reconciliation-invalid states remain explicit.")
    _w("")

    # Sampling deep evidence is intentionally a separate domain.  In
    # particular, none of these rows are calls, Golden nodes, child counts, or
    # Gantt spans: host and device clocks are not silently merged.
    deep = sampling_deep_evidence or {"status": "unavailable", "step_breakdown": [], "model_breakdown": []}
    _w("## SAMPLING SUMMARY")
    _w("")
    _w("```text")
    lines.extend(_sampling_breakdown_text(deep).rstrip("\n").splitlines())
    _w("```")
    _w("")
    _w("## STEP BREAKDOWN")
    _w("")
    _w(f"- **sampling_deep_profile**: {deep.get('status', 'unavailable')}")
    _w(f"- **records**: {deep.get('record_count', 0)}; duplicate copies suppressed: {deep.get('duplicate_count', 0)}")
    step_rows = deep.get("step_breakdown", [])
    if step_rows:
        _w("")
        _w("| Profile | Kind | Step/metric | Wall (host monotonic ms) | Source |")
        _w("|---:|---|---|---:|---|")
        for row in step_rows[:300]:
            label = row.get("label", "")
            wall = row.get("wall_ms", MEASUREMENT_UNAVAILABLE)
            _w(f"| {row.get('profile_index', '')} | {row.get('kind', '')} | {label} | {wall} | {row.get('source', '')} |")
    else:
        _w("No step breakdown available.")
    _w("")

    _w("## DEEP MODEL BREAKDOWN")
    _w("")
    _w("CUDA/device elapsed and host monotonic timings are shown in separate columns; rows are evidence only and are not trace hierarchy spans.")
    model_rows = deep.get("human_model_breakdown")
    if not isinstance(model_rows, list):
        model_rows, model_non_additive = _build_human_sampling_model_breakdown(deep)
    else:
        model_non_additive = bool(deep.get("model_non_additive"))
    if model_rows:
        if model_non_additive:
            _w("**NON-ADDITIVE MODEL EVIDENCE**: do not sum rows across model phases or host/device clock domains.")
        _w("")
        _w("| Profile | Step | Eval | Phase | Count | Host monotonic ms | CUDA/device elapsed ms | Range ms |")
        _w("|---:|---:|---:|---|---:|---:|---:|---|")
        for row in model_rows[:500]:
            _w(
                f"| {row.get('profile_index', '')} | {row.get('step', '')} | {row.get('eval_index', '')} "
                f"| {row.get('phase', '')} | {row.get('sample_count', '')} "
                f"| {row.get('host_monotonic_ms', MEASUREMENT_UNAVAILABLE)} | {row.get('cuda_device_ms', MEASUREMENT_UNAVAILABLE)} "
                f"| {row.get('host_min_ms', MEASUREMENT_UNAVAILABLE)}..{row.get('host_max_ms', MEASUREMENT_UNAVAILABLE)} |"
            )
    else:
        _w("No deep model breakdown available.")
    _w("")
    _w("## DEEP SAMPLING BREAKDOWN")
    _w("")
    _w("See the persisted `golden_sampling_breakdown.txt`; model rows are aggregated by step/evaluation and phase.")
    _w("")
    _w("## E27 TRANSPORT BREAKDOWN")
    _w("")
    _w("```text")
    lines.extend(_transport_breakdown_text(transport).rstrip("\n").splitlines())
    _w("```")
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

    # Derived files (exclude manifest.json from its own inventory).  Golden
    # stage Gantts live under derived/gantts/, so the inventory must recurse;
    # otherwise the manifest would claim a complete report while omitting the
    # seven per-stage artifacts.
    if derived_dir.exists():
        for fpath in sorted(derived_dir.rglob("*")):
            if fpath.is_file() and fpath.name != "manifest.json":
                entries.append({
                    "path": str(fpath.relative_to(derived_dir.parent)).replace("\\", "/"),
                    "category": "derived",
                    "size_bytes": fpath.stat().st_size,
                    "sha256": _sha256_file(fpath),
                })

    return entries


def _combine_profiler_artifacts(report: str, derived_dir: Path) -> str:
    """Embed the four canonical profiler artifacts in the human report."""
    parts = [report.rstrip("\n"), "", "## Persisted profiler artifacts", ""]
    for name in (
        "golden_profile_report.md",
        "golden_profile_gantt.txt",
        "golden_stage_gantts.txt",
        "golden_sampling_breakdown.txt",
        "e27_transport_breakdown.txt",
    ):
        path = derived_dir / name
        parts.extend([f"### {name}", "", "```text"])
        if path.is_file():
            parts.extend(path.read_text(encoding="utf-8").rstrip("\n").splitlines())
        else:
            parts.append(MEASUREMENT_UNAVAILABLE)
        parts.extend(["```", ""])
    stage_dir = derived_dir / "gantts"
    if stage_dir.is_dir():
        for path in sorted(stage_dir.glob("golden_*.txt")):
            parts.extend([f"### gantts/{path.name}", "", "```text"])
            parts.extend(path.read_text(encoding="utf-8").rstrip("\n").splitlines())
            parts.extend(["```", ""])
    return "\n".join(parts).rstrip("\n")


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
    golden_profile: dict[str, Any] | None = None,
    sampling_deep_evidence: dict[str, Any] | None = None,
    source_h2d_transport: dict[str, Any] | None = None,
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
        "derived_files": derived_files.get("files", []),
        "golden_profile": _golden_profile_json(golden_profile) if golden_profile is not None else None,
        "golden_profile_complete": (
            golden_profile.get("GOLDEN_PROFILE_COMPLETE") if golden_profile is not None else "NO"
        ),
        "golden_profile_reason": (
            golden_profile.get("GOLDEN_PROFILE_REASON") if golden_profile is not None else "not_generated"
        ),
        "golden_profile_torch": (
            golden_profile.get("GOLDEN_PROFILE_TORCH") if golden_profile is not None else "DISABLED"
        ),
        # Kept outside calls/timeline/Golden profile by contract.  This is a
        # structured projection of persisted diagnostic evidence, not inferred
        # trace work.
        "sampling_deep_profile": sampling_deep_evidence or {
            "status": "unavailable",
            "record_count": 0,
            "duplicate_count": 0,
            "records": [],
            "step_breakdown": [],
            "model_breakdown": [],
            "warnings": [],
            "hierarchy_included": False,
        },
        "source_h2d_transport": source_h2d_transport or _source_h2d_unavailable(),
    }
    deep = data["sampling_deep_profile"]
    human_model, model_non_additive = _build_human_sampling_model_breakdown(deep)
    data["sampling_deep_profile"]["human_model_breakdown"] = human_model
    data["sampling_deep_profile"]["model_non_additive"] = model_non_additive
    data["VIZTRACER_CHILD_COVERAGE"] = (
        golden_profile.get("VIZTRACER_CHILD_COVERAGE", "NO")
        if golden_profile is not None else "NO"
    )
    data["CROSS_EVIDENCE_DECOMPOSITION"] = (
        golden_profile.get("CROSS_EVIDENCE_DECOMPOSITION", "NONE")
        if golden_profile is not None else "NONE"
    )
    data["unresolved_over_50ms"] = (
        golden_profile.get("unresolved_over_50ms", [])
        if golden_profile is not None else []
    )

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

    # Parse this diagnostic domain independently of VizTracer calls.  In
    # particular, do not append its intervals to timeline or semantic ops.
    sampling_deep_evidence = _build_sampling_deep_evidence(
        sessions, runtime_result, warnings,
    )
    source_h2d_transport = build_source_h2d_transport_projection(
        runtime_result, sessions=sessions, session_dir=session_dir,
    )

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

    # ── Golden serial profile (reuses all normalized/derived evidence above) ──
    golden_profile = _build_golden_profile(
        calls,
        semantic_ops,
        torch_events,
        trace_config,
        trace_truncated=truncated,
        raw_trace_nonempty=bool(trace_events),
    )
    _augment_golden_profile(
        golden_profile, sampling_deep_evidence, source_h2d_transport, trace_config,
    )

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

    # Build one normalized machine-facing report first.  The human renderer is
    # then the sole owner of console/stage/Gantt presentation; Modal reads the
    # persisted console verbatim and never reconstructs it independently.
    derived_files_info = {
        "trace_entry_count": entry_count,
        "trace_entry_capacity": entry_capacity,
        "trace_truncated": truncated,
        "files": _build_manifest(raw_dir, derived_dir),
    }
    structured_report = _build_report_data(
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
        golden_profile=golden_profile,
        sampling_deep_evidence=sampling_deep_evidence,
        source_h2d_transport=source_h2d_transport,
    )
    from . import golden_human_report

    structured_report["human_artifacts"] = {
        "console": "derived/golden_profiler_console.txt",
        "summary": "derived/golden_profile_summary.json",
        "report": "derived/golden_profile_report.md",
        "overall_gantt": "derived/golden_profile_gantt.txt",
        "stage_gantts": "derived/golden_stage_gantts.txt",
        "sampling": "derived/golden_sampling_breakdown.txt",
        "transport": "derived/e27_transport_breakdown.txt",
        "stage_directory": "derived/gantts/",
    }

    golden_summary_path = derived_dir / "golden_profile_summary.json"
    golden_report_path = derived_dir / "golden_profile_report.md"
    golden_gantt_path = derived_dir / "golden_profile_gantt.txt"
    golden_stage_gantts_path = derived_dir / "golden_stage_gantts.txt"
    golden_console_path = derived_dir / "golden_profiler_console.txt"
    golden_sampling_path = derived_dir / "golden_sampling_breakdown.txt"
    e27_transport_path = derived_dir / "e27_transport_breakdown.txt"
    _write_json(golden_summary_path, _golden_profile_json(golden_profile))
    MODAL_HUMAN_REPORT = ""
    sampling_artifact = ""
    transport_artifact = ""
    try:
        MODAL_HUMAN_REPORT = golden_human_report.render_full_console(structured_report)
        stage_gantts = golden_human_report.render_stage_gantts(structured_report)
        overall_gantt = golden_human_report.render_overall_timeline(structured_report)
        _write_text_exact(golden_console_path, MODAL_HUMAN_REPORT)
        persisted_console = golden_console_path.read_text(encoding="utf-8")
        normalize_newlines = lambda value: value.replace("\r\n", "\n").replace("\r", "\n")
        if normalize_newlines(MODAL_HUMAN_REPORT) != normalize_newlines(persisted_console):
            raise RuntimeError("MODAL_HUMAN_REPORT does not match persisted console")
        _write_text_exact(golden_stage_gantts_path, stage_gantts)
        _write_text_exact(golden_gantt_path, overall_gantt + "\n" + stage_gantts)
        # The compact console uses dominant sampling rows.  The artifact and
        # report retain the complete bounded deep-profile breakdown.
        sampling_artifact = (
            golden_human_report.render_sampling_stage(structured_report)
            + "\n\n"
            + _sampling_breakdown_text(sampling_deep_evidence)
        )
        transport_artifact = (
            golden_human_report.render_transport_mini_gantt(source_h2d_transport)
            + "\n\n"
            + _transport_breakdown_text(source_h2d_transport)
        )
        _write_text_exact(golden_sampling_path, sampling_artifact)
        _write_text_exact(e27_transport_path, transport_artifact)
        gantt_dir = derived_dir / "gantts"
        stage_file_specs = (
            ("golden_clip_load", "CLIP LOAD", "clip"),
            ("golden_clip_forward", "CLIP FORWARD", "clip"),
            ("golden_unet_load", "UNET LOAD", "unet"),
            ("golden_sampler_prepare", "SAMPLER PREPARE", "sampler"),
            ("golden_vae_load", "VAE LOAD", "vae"),
            ("golden_sampling", "SAMPLING", "sampling"),
            ("golden_vae_decode", "VAE DECODE", "vae_decode"),
        )
        for stage_name, title, role in stage_file_specs:
            _write_text_exact(
                gantt_dir / f"{stage_name}.txt",
                golden_human_report.render_stage_artifact(
                    structured_report, title, stage_name, role=role,
                ) + "\n",
            )
        _write_text_exact(
            golden_report_path,
            _generate_golden_profile_report(golden_profile).rstrip("\n")
            + "\n\n## Detailed Golden stage Gantts\n\n"
            + stage_gantts.rstrip("\n")
            + "\n\n## Detailed sampling evidence\n\n"
            + sampling_artifact.rstrip("\n")
            + "\n\n## Detailed E27 transport evidence\n\n"
            + transport_artifact.rstrip("\n")
            + "\n",
        )
    except Exception as exc:
        golden_profile["GOLDEN_PROFILE_COMPLETE"] = "NO"
        golden_profile["GOLDEN_PROFILE_REASON"] = f"derived generation failed: {exc.__class__.__name__}"
        _write_json(golden_summary_path, _golden_profile_json(golden_profile))
    if not all(path.is_file() for path in (
        golden_summary_path, golden_report_path, golden_gantt_path,
        golden_stage_gantts_path, golden_console_path, golden_sampling_path,
        e27_transport_path,
    )):
        golden_profile["GOLDEN_PROFILE_COMPLETE"] = "NO"
        golden_profile["GOLDEN_PROFILE_REASON"] = "derived generation failed: missing Golden artifact"
        _write_json(golden_summary_path, _golden_profile_json(golden_profile))

    # Refresh the inventory after the complete Golden family exists.  The
    # structured report remains the same object used for rendering, while its
    # machine inventory now includes nested derived/gantts files as well.
    derived_files_info["files"] = _build_manifest(raw_dir, derived_dir)
    structured_report["derived_files"] = derived_files_info["files"]

    # ── Generate report.md ──
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
        golden_profile=golden_profile,
        sampling_deep_evidence=sampling_deep_evidence,
        source_h2d_transport=source_h2d_transport,
    )
    report_md = _combine_profiler_artifacts(report_md, derived_dir)

    report_path = derived_dir / "report.md"
    _write_text_exact(report_path, report_md)

    # ── Generate report_data.json ──
    report_data_path = derived_dir / "report_data.json"
    _write_json(report_data_path, structured_report)

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
        for p in derived_dir.rglob("*")
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
        "golden_profile_complete": golden_profile["GOLDEN_PROFILE_COMPLETE"],
        "golden_profile_reason": golden_profile["GOLDEN_PROFILE_REASON"],
        "golden_profile_torch": golden_profile["GOLDEN_PROFILE_TORCH"],
        "golden_profile_summary_path": str(golden_summary_path).replace("\\", "/"),
        "golden_profile_report_path": str(golden_report_path).replace("\\", "/"),
        "golden_profile_gantt_path": str(golden_gantt_path).replace("\\", "/"),
        "golden_stage_gantts_path": str(golden_stage_gantts_path).replace("\\", "/"),
        "golden_profiler_console_path": str(golden_console_path).replace("\\", "/"),
        "MODAL_HUMAN_REPORT": MODAL_HUMAN_REPORT,
        "golden_sampling_breakdown_path": str(golden_sampling_path).replace("\\", "/"),
        "e27_transport_breakdown_path": str(e27_transport_path).replace("\\", "/"),
        "source_h2d_transport": source_h2d_transport,
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
