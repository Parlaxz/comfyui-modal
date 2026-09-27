"""Small, dependency-free helpers for runtime health telemetry.

The runtime status is intentionally a plain JSON-compatible mapping so it can
be embedded directly in a persisted run record.  Reason strings beginning with
or clearly describing a hard/fatal/failure condition are treated as hard
reasons; other reasons describe a degraded, but completed, run.
"""

from __future__ import annotations

import math
from enum import Enum
from numbers import Real
from typing import Any, Iterable


class RuntimeStatus(str, Enum):
    """The three states emitted in a run record's ``runtime_status``."""

    NOMINAL = "NOMINAL"
    DEGRADED = "DEGRADED"
    FAILED = "FAILED"


class Observation(str, Enum):
    """Classification of an observed value, including a real numeric zero."""

    ABSENT = "ABSENT"
    UNKNOWN = "UNKNOWN"
    UNOBSERVABLE = "UNOBSERVABLE"
    INVALID = "INVALID"
    ZERO = "ZERO"
    VALUE = "VALUE"


# Convenient constants for callers that prefer labels over enum members.
ABSENT = Observation.ABSENT
UNKNOWN = Observation.UNKNOWN
UNOBSERVABLE = Observation.UNOBSERVABLE
INVALID = Observation.INVALID
ZERO = Observation.ZERO
VALUE = Observation.VALUE


def classify(value: Any) -> Observation:
    """Classify a telemetry value without confusing ``0`` with no value.

    ``None`` means the observation was absent.  The two sentinel strings are
    preserved as distinct states.  Numeric NaN, infinity, and negative values
    are invalid (in particular for timing measurements); finite zero is a
    legitimate ``ZERO`` observation.
    """
    if value is None:
        return Observation.ABSENT
    if isinstance(value, str):
        sentinel = value.strip().upper()
        if sentinel == Observation.UNOBSERVABLE.value:
            return Observation.UNOBSERVABLE
        if sentinel == Observation.UNKNOWN.value:
            return Observation.UNKNOWN
        return Observation.UNKNOWN
    if isinstance(value, Real) and not isinstance(value, bool):
        numeric = float(value)
        if not math.isfinite(numeric) or numeric < 0:
            return Observation.INVALID
        if numeric == 0:
            return Observation.ZERO
        return Observation.VALUE
    return Observation.UNKNOWN


def _is_hard_reason(reason: str) -> bool:
    normalized = reason.strip().lower().replace("_", " ")
    if "non fatal" in normalized or "nonfatal" in normalized:
        return False
    return any(
        marker in normalized
        for marker in ("hard", "fatal", "failed", "failure")
    )


def _fallback_attempted(loader_selection: Any) -> bool:
    if not isinstance(loader_selection, dict):
        return False
    for selection in loader_selection.values():
        if not isinstance(selection, dict):
            continue
        attempted = selection.get("fallback_attempted")
        if attempted is True or (
            isinstance(attempted, str)
            and attempted.strip().lower() in {"1", "true", "yes", "on"}
        ):
            return True
    return False


def build_runtime_status(
    loader_selection: dict[str, Any] | None = None,
    reasons: Iterable[str] | None = None,
) -> dict[str, Any]:
    """Build the JSON object for the pinned ``runtime_status`` contract."""
    normalized_reasons = [str(reason) for reason in (reasons or ())]
    hard = any(_is_hard_reason(reason) for reason in normalized_reasons)
    degraded = _fallback_attempted(loader_selection) or bool(normalized_reasons)
    if hard:
        status = RuntimeStatus.FAILED
    elif degraded:
        status = RuntimeStatus.DEGRADED
    else:
        status = RuntimeStatus.NOMINAL
    return {"status": status.value, "reasons": normalized_reasons}
