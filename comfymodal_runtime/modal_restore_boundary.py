"""Modal snapshot-restore-begin boundary ingestion.

Pure, dependency-free helpers that resolve the Modal platform boundary
``Restoring Function from memory snapshot`` — the instant the Modal scheduler
hands the restored container to the (not yet resumed) Python process — from
either structured Modal log records or raw log lines.

This module deliberately does **not** import Modal (it is fully unit-testable
offline) and has zero side effects at import time.

The platform boundary is observable only in the Modal app log, not in-process.
Real runs tail the app log (see ``tools/fetch_matrix_stage_lines.py`` for the
credentials/app-resolve pattern); this module only turns log lines into a wall
timestamp and never guesses a boundary.
"""

from __future__ import annotations

import re
import time
from datetime import datetime, time as _dt_time, timezone
from typing import Any, Mapping, Sequence

KEY = "modal_restore_begin_wall_unix_ns"
"""The canonical result/timing dict key carrying the resolved boundary (ns)."""

_MESSAGE_MARKER = "restoring function from memory snapshot"
_HALF_DAY_NS = 12 * 3600 * 1_000_000_000
_DAY_NS = 24 * 3600 * 1_000_000_000

# A raw log line: leading timestamp (date-carrying or time-only) followed by
# the message.  The date form also accepts ``YYYY-MM-DDTHH:MM:SS`` (ISO) and
# optional ``Z`` / ``±HH[:MM]`` offsets.
_LINE_RE = re.compile(
    r"^\s*(?P<stamp>"
    r"(?:\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-]\d{2}:?\d{2})?)"
    r"|(?:\d{1,2}:\d{2}:\d{2}(?:\.\d{1,6})?)"
    r")\s+(?P<message>.+)$",
)

_TIME_ONLY_RE = re.compile(r"^(\d{1,2}):(\d{2}):(\d{2})(?:\.(\d{1,6}))?$")

_UTC_OFFSET_RE = re.compile(r"([+-]\d{2})(\d{2})$")


def _iso_to_ns(text: str) -> int | None:
    """Parse a date-carrying timestamp string (ISO8601 or space form) to ns."""
    normalized = text.strip()
    if not normalized:
        return None
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    offset = _UTC_OFFSET_RE.search(normalized)
    if offset is not None:
        normalized = (
            normalized[: offset.start()]
            + offset.group(1)
            + ":"
            + offset.group(2)
        )
    try:
        parsed = datetime.fromisoformat(normalized)
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    try:
        return int(parsed.timestamp() * 1_000_000_000)
    except (OverflowError, OSError, ValueError):
        return None


def _resolve_time_only_ns(text: str, anchor_ns: int | None) -> int | None:
    """Resolve an ``HH:MM:SS.mmm`` time-of-day against *anchor_ns*.

    The candidate is the anchor's UTC date at that time-of-day.  If the
    candidate is more than 12h before the anchor a day is added; if more than
    12h after, a day is subtracted.  The guess never exceeds 12h.  When
    *anchor_ns* is ``None`` ``time.time()`` is used as the anchor.
    """
    match = _TIME_ONLY_RE.match(text.strip())
    if match is None:
        return None
    hour = int(match.group(1))
    minute = int(match.group(2))
    second = int(match.group(3))
    frac = (match.group(4) or "").ljust(6, "0")[:6]
    micro = int(frac) if frac else 0
    if hour > 23 or minute > 59 or second > 59:
        return None
    try:
        tod = _dt_time(hour, minute, second, micro)
    except ValueError:
        return None
    if anchor_ns is None:
        anchor_ns = int(time.time() * 1_000_000_000)
    anchor_dt = datetime.fromtimestamp(anchor_ns / 1_000_000_000, tz=timezone.utc)
    candidate = datetime.combine(anchor_dt.date(), tod, tzinfo=timezone.utc)
    candidate_ns = int(candidate.timestamp() * 1_000_000_000)
    if candidate_ns < anchor_ns - _HALF_DAY_NS:
        candidate_ns += _DAY_NS
    elif candidate_ns > anchor_ns + _HALF_DAY_NS:
        candidate_ns -= _DAY_NS
    return candidate_ns


def _timestamp_value_to_ns(value: Any, anchor_ns: int | None) -> int | None:
    """Convert a timestamp value (epoch s/ms/ns or timestamp string) to ns."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        if value < 1e12:  # epoch seconds
            return int(value * 1_000_000_000)
        if value < 1e15:  # epoch milliseconds
            return int(value * 1_000_000)
        return int(value)  # epoch nanoseconds
    if isinstance(value, str):
        iso = _iso_to_ns(value)
        if iso is not None:
            return iso
        return _resolve_time_only_ns(value, anchor_ns)
    return None


def _record_to_candidate(
    record: Mapping[str, Any], anchor_ns: int | None,
) -> dict[str, Any] | None:
    """Convert one structured log record into a candidate dict, or ``None``."""
    if not isinstance(record, Mapping):
        return None
    message = record.get("message")
    if message is None:
        message = record.get("text")
    if message is None:
        message = record.get("data")
    if message is None or not str(message).strip():
        return None
    raw_ts = record.get("timestamp_ns")
    if raw_ts is None:
        raw_ts = record.get("wall_unix_ns")
    if raw_ts is None:
        raw_ts = record.get("timestamp")
    timestamp_ns = _timestamp_value_to_ns(raw_ts, anchor_ns)
    if timestamp_ns is None:
        return None
    task_field = record.get("task_id")
    return {
        "timestamp_ns": timestamp_ns,
        "message": str(message),
        "task_id": str(task_field) if task_field not in (None, "") else "",
        "source_line": str(message),
    }


def _line_to_candidate(line: str, anchor_ns: int | None) -> dict[str, Any] | None:
    """Convert one raw log line into a candidate dict, or ``None``."""
    if not isinstance(line, str):
        return None
    match = _LINE_RE.match(line)
    if match is None:
        return None
    timestamp_ns = _timestamp_value_to_ns(match.group("stamp"), anchor_ns)
    if timestamp_ns is None:
        return None
    return {
        "timestamp_ns": timestamp_ns,
        "message": match.group("message").strip(),
        "task_id": "",
        "source_line": line.strip(),
    }


def parse_modal_restore_begin(
    lines: Sequence[Any] | None,
    *,
    task_id: str = "",
    window_start_unix_ns: int | None = None,
    window_end_unix_ns: int | None = None,
) -> dict[str, Any]:
    """Find the Modal snapshot-restore-begin boundary in *lines*.

    Accepts BOTH structured records (dicts with ``timestamp`` / ``message``
    and optionally ``task_id``) and raw strings (leading timestamp + message,
    e.g. ``"01:12:57.388  Restoring Function from memory snapshot"``).  A
    record/line matches when its message contains "Restoring Function from
    memory snapshot" (case-insensitive; also tolerates the plain
    "Restoring Function" / "from memory snapshot" halves).

    Timestamp formats handled:
      * ``HH:MM:SS.mmm`` (also 1-2 digit hours) — resolved against
        ``window_start_unix_ns`` (or ``time.time()``) at that time-of-day,
        with a ±1-day snap that never guesses beyond 12h.
      * ``YYYY-MM-DD HH:MM:SS.mmm`` and ISO8601 (``datetime.fromisoformat``).

    Task association: when *task_id* is given, records whose structured
    ``task_id`` field equals it OR whose message mentions it are preferred
    (``matched_task=True`` only for such a line).  If none, the LAST in-window
    match is taken (``matched_task=False``).  When a window is given, a match
    outside it is never returned.  No match → all ``None``.

    Returns::

        {
            "modal_restore_begin_wall_unix_ns": int | None,
            "matches": int,
            "matched_task": bool,
            "source_line": str,
        }
    """
    anchor_ns = window_start_unix_ns
    candidates: list[dict[str, Any]] = []
    for line in lines or ():
        candidate = (
            _record_to_candidate(line, anchor_ns)
            if isinstance(line, Mapping)
            else _line_to_candidate(line, anchor_ns)
        )
        if candidate is None:
            continue
        if _MESSAGE_MARKER not in candidate["message"].lower():
            continue
        candidates.append(candidate)

    def _in_window(candidate: dict[str, Any]) -> bool:
        ts = candidate["timestamp_ns"]
        if window_start_unix_ns is not None and ts < window_start_unix_ns:
            return False
        if window_end_unix_ns is not None and ts > window_end_unix_ns:
            return False
        return True

    in_window = [c for c in candidates if _in_window(c)]
    if not in_window:
        return {
            KEY: None,
            "matches": len(candidates),
            "matched_task": False,
            "source_line": "",
        }

    wanted_task = str(task_id).strip()
    task_match: list[dict[str, Any]] = []
    if wanted_task:
        task_match = [
            c
            for c in in_window
            if c["task_id"] == wanted_task or wanted_task in c["message"]
        ]

    if task_match:
        selected = task_match[-1]
        matched_task = True
    else:
        selected = in_window[-1]
        matched_task = False
    return {
        KEY: selected["timestamp_ns"],
        "matches": len(in_window),
        "matched_task": matched_task,
        "source_line": selected["source_line"],
    }


def extract_restore_begin_from_result(
    result: Mapping[str, Any] | None, timing: Mapping[str, Any] | None = None,
) -> int | None:
    """Read the restore-begin boundary already carried in *result* / *timing*.

    First found wins across: the result root key
    ``modal_restore_begin_wall_unix_ns``, then the *timing* dict, then
    ``result["local_timing"]``, then trace metadata nested under
    ``result["trace"]["metadata"]``.  Returns ``None`` when absent/invalid
    (never raises).
    """
    if not isinstance(result, Mapping):
        return None
    sources: list[Any] = [result]
    if isinstance(timing, Mapping):
        sources.append(timing)
    local_timing = result.get("local_timing")
    if isinstance(local_timing, Mapping):
        sources.append(local_timing)
    trace = result.get("trace")
    if isinstance(trace, Mapping):
        metadata = trace.get("metadata")
        if isinstance(metadata, Mapping):
            sources.append(metadata)
    for source in sources:
        value = source.get(KEY)
        if value is None or isinstance(value, bool):
            continue
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            continue
        if parsed > 0:
            return parsed
    return None


__all__ = [
    "KEY",
    "parse_modal_restore_begin",
    "extract_restore_begin_from_result",
]
