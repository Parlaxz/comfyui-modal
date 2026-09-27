"""Synthetic benchmark for the E27 provenance-marker tracker.

The legacy arm rewrites every prior event when the same marker is observed;
the fixed arm records the marker on event creation and makes same-marker
updates constant time.  This benchmark is intentionally stdlib-only and does
not call Modal or a model runtime.
"""

from __future__ import annotations

import json
import statistics
import sys
import time
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from comfymodal_runtime.e27_source_mechanism import (  # noqa: E402
    ActualSourceTelemetry,
    SourceReadEvent,
)


MARKER = "benchmark.physical_syscall"
EVENT_COUNTS = (47, 123, 243, 370)


def _event(index: int, marker: str | None = None) -> SourceReadEvent:
    return SourceReadEvent(
        0, 0, index, 1, 1, 0, False, index, index + 1, index, None, marker
    )


def _legacy(count: int) -> tuple[int, int]:
    events: list[SourceReadEvent] = []
    marker: str | None = None
    started = time.perf_counter_ns()
    cpu_started = time.process_time_ns()
    for index in range(count):
        marker = MARKER
        events = [replace(event, physical_provenance=marker) for event in events]
        events.append(_event(index, marker))
    elapsed = time.perf_counter_ns() - started
    cpu_elapsed = time.process_time_ns() - cpu_started
    assert len(events) == count and all(event.physical_provenance == MARKER for event in events)
    return elapsed, cpu_elapsed


def _fixed(count: int) -> tuple[int, int]:
    telemetry = ActualSourceTelemetry()
    started = time.perf_counter_ns()
    cpu_started = time.process_time_ns()
    for index in range(count):
        telemetry.mark_physical_syscall_provenance(MARKER)
        call = telemetry.syscall_enter(0, index, 1, timestamp_ns=index)
        telemetry.syscall_exit(call, 1, timestamp_ns=index + 1)
    elapsed = time.perf_counter_ns() - started
    cpu_elapsed = time.process_time_ns() - cpu_started
    assert len(telemetry.events) == count
    assert all(event.physical_provenance == MARKER for event in telemetry.events)
    return elapsed, cpu_elapsed


def run(*, repetitions: int = 7) -> dict:
    if repetitions < 1:
        raise ValueError("repetitions must be positive")
    rows = []
    for count in EVENT_COUNTS:
        legacy_samples = [_legacy(count) for _ in range(repetitions)]
        fixed_samples = [_fixed(count) for _ in range(repetitions)]
        legacy = [sample[0] for sample in legacy_samples]
        fixed = [sample[0] for sample in fixed_samples]
        legacy_cpu = [sample[1] for sample in legacy_samples]
        fixed_cpu = [sample[1] for sample in fixed_samples]
        legacy_median = statistics.median(legacy)
        fixed_median = statistics.median(fixed)
        legacy_cpu_median = statistics.median(legacy_cpu)
        fixed_cpu_median = statistics.median(fixed_cpu)
        rows.append(
            {
                "events": count,
                "legacy_ns": legacy,
                "fixed_ns": fixed,
                "legacy_median_ns": legacy_median,
                "fixed_median_ns": fixed_median,
                "legacy_to_fixed_median_ratio": legacy_median / fixed_median,
                "legacy_cpu_ns": legacy_cpu,
                "fixed_cpu_ns": fixed_cpu,
                "legacy_cpu_median_ns": legacy_cpu_median,
                "fixed_cpu_median_ns": fixed_cpu_median,
                "legacy_to_fixed_cpu_median_ratio": (
                    legacy_cpu_median / fixed_cpu_median
                    if fixed_cpu_median else None
                ),
            }
        )
    return {
        "benchmark": "e27_provenance_tracker",
        "marker": MARKER,
        "event_counts": list(EVENT_COUNTS),
        "repetitions": repetitions,
        "rows": rows,
    }


def main() -> int:
    result = run()
    output_dir = ROOT / "unetClipExperimentsSeptember" / "07_c9_high_qd_recovery"
    if output_dir.is_dir():
        output_path = output_dir / "e27_provenance_tracker_microbenchmark.json"
        output_path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        result["output_path"] = str(output_path)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
