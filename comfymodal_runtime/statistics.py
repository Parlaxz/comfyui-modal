"""Small dependency-free statistics helpers shared by runtime and reports."""

from __future__ import annotations

import math
from collections.abc import Sequence

PERCENTILE_METHOD = "linear_interpolation"


def percentile(values: Sequence[float], p: float) -> float | None:
    """Return the linearly interpolated percentile of *values*."""
    if not values:
        return None
    ordered = sorted(float(value) for value in values)
    if p <= 0:
        return ordered[0]
    if p >= 100:
        return ordered[-1]
    position = (len(ordered) - 1) * (p / 100.0)
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    fraction = position - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * fraction
