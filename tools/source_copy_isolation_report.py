"""Aggregate the P9 source/destination copy-isolation cohort.

Reads the invocation-bound Golden cohort manifests the control plane already
wrote, pulls the ``golden_source_copy_isolation`` event out of each attempt, and
produces the numbers the decision tree needs:

* per-arm / per-variant wall, thread-CPU and wall/cpu distributions
  (min/p50/p90/p95/p99/max/mean/SD/CV), pooled over containers and per container;
* stall-threshold counts at 100/250/500/1000 ms;
* the twenty slowest copies per arm;
* slot-identity and source-offset correlation for the slow copies, including
  whether the same slot or the same offset recurs as pathological across
  independent containers;
* the single-thread versus four-thread comparison for arms C and D.

Nothing here selects evidence by modification time and nothing here drops an
invalid attempt: every attempt found is listed with its validity, and only
attempts that are structurally valid AND report a complete arm are pooled.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from comfymodal_runtime.source_copy_isolation import (  # noqa: E402
    ARMS,
    STALL_THRESHOLDS_MS,
    describe,
    summarize_copies,
)

PROFILE = "golden_p1_parallel_p9_srccopy_iso_h100"
EVENT_NAME = "golden_source_copy_isolation"
SLOW_MS = 100.0


def _find_reports(node: Any) -> list[dict[str, Any]]:
    if isinstance(node, dict):
        if node.get("name") == EVENT_NAME:
            report = (node.get("fields") or {}).get("report")
            if isinstance(report, dict):
                return [report]
        found: list[dict[str, Any]] = []
        for value in node.values():
            found.extend(_find_reports(value))
        return found
    if isinstance(node, list):
        found = []
        for value in node:
            found.extend(_find_reports(value))
        return found
    return []


def load_attempts(root: Path, profile: str = PROFILE) -> list[dict[str, Any]]:
    """One row per cohort manifest found under the artifacts tree."""
    attempts: list[dict[str, Any]] = []
    for manifest_path in sorted(root.glob("artifacts/**/manifest.json")):
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(manifest, Mapping):
            continue
        if str(manifest.get("profile") or "") != profile:
            continue
        for attempt in manifest.get("attempts") or []:
            if not isinstance(attempt, Mapping):
                continue
            reports = _find_reports(attempt)
            row: dict[str, Any] = {
                "cohort_dir": str(manifest.get("cohort_dir") or ""),
                "request_id": str(attempt.get("request_id") or ""),
                "run_index": attempt.get("run_index"),
                "valid": bool(attempt.get("valid")),
                "dnf": bool(attempt.get("dnf")),
                "true_cold": bool(attempt.get("true_cold")),
                "duration_ms": attempt.get("duration_ms"),
                "failures": list(attempt.get("failures") or []),
                "deployment_fingerprint": str(
                    (attempt.get("identity") or {}).get("deployment_fingerprint") or ""
                ),
                "image_id": str((attempt.get("identity") or {}).get("image_id") or ""),
                "report": reports[0] if reports else None,
                "report_count": len(reports),
            }
            report = row["report"]
            if isinstance(report, dict):
                row["arm"] = str(report.get("arm") or "")
                row["arm_status"] = str(report.get("status") or "")
                row["variants_complete"] = report.get("variants_complete")
                row["variants_expected"] = report.get("variants_expected")
                row["teardown"] = report.get("teardown")
                row["host"] = report.get("host")
                row["identity"] = report.get("identity")
                row["source"] = report.get("source")
                row["destination"] = report.get("destination")
            else:
                row["arm"] = ""
                row["arm_status"] = "absent"
            attempts.append(row)
    return attempts


def attempt_is_usable(row: Mapping[str, Any]) -> bool:
    if not row.get("valid") or row.get("dnf"):
        return False
    if row.get("report_count") != 1:
        return False
    if row.get("arm_status") != "ok":
        return False
    report = row.get("report") or {}
    expected = int(report.get("variants_expected") or 0)
    if int(report.get("variants_complete") or 0) != expected or expected <= 0:
        return False
    # A pinned arm that failed to unregister would poison the Golden load that
    # follows it, so an unregistered teardown is never silently accepted.
    teardown = report.get("teardown")
    if isinstance(teardown, Mapping) and teardown.get("cuda_host_unregistered") is False:
        return False
    return True


def pooled_copies(rows: Iterable[Mapping[str, Any]], variant: str | None = None) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in rows:
        report = row.get("report") or {}
        for item in report.get("variants") or []:
            if variant is not None and str(item.get("variant")) != variant:
                continue
            out.extend(dict(copy) for copy in (item.get("copies") or []))
    return out


def variant_complete(rows: Sequence[Mapping[str, Any]], variant: str) -> bool:
    for row in rows:
        report = row.get("report") or {}
        for item in report.get("variants") or []:
            if str(item.get("variant")) == variant and not item.get("complete"):
                return False
    return True


def repeat_analysis(
    copies: Sequence[Mapping[str, Any]],
    key: str,
    *,
    containers: Sequence[Any],
) -> dict[str, Any]:
    """Is a slow-copy identity confined to one container, or does it recur?

    ``containers`` is the per-copy container index, aligned with ``copies``.  A
    slot or offset that is pathological in two independent containers is a
    placement property; one that only ever appears inside a single container is
    transient host state.
    """
    overall = Counter(item.get(key) for item in copies)
    slow = [item for item in copies if float(item.get("wall_ms") or 0.0) > SLOW_MS]
    slow_counter = Counter(item.get(key) for item in slow)
    per_identity: dict[Any, set] = {}
    for item, container in zip(slow, containers):
        per_identity.setdefault(item.get(key), set()).add(container)
    recurring = {
        str(identity): sorted(hits)
        for identity, hits in per_identity.items()
        if len(hits) >= 2
    }
    top_slow = [
        {"value": identity, "count": count,
         "mean_wall_ms": round(
             sum(
                 float(item.get("wall_ms") or 0.0)
                 for item in copies
                 if item.get(key) == identity
             ) / max(1, overall[identity]),
             4,
         )}
        for identity, count in slow_counter.most_common(10)
    ]
    return {
        "key": key,
        "distinct_overall": len(overall),
        "slow_copy_count": len(slow),
        "distinct_in_slow": len(slow_counter),
        "slowest_identities": top_slow,
        "recurring_across_containers": recurring,
        "repeats": bool(recurring),
    }


def arm_summary(rows: Sequence[Mapping[str, Any]], variant: str | None = None) -> dict[str, Any]:
    copies: list[dict[str, Any]] = []
    containers: list[Any] = []
    per_container: list[dict[str, Any]] = []
    for row in rows:
        report = row.get("report") or {}
        for item in report.get("variants") or []:
            if variant is not None and str(item.get("variant")) != variant:
                continue
            rows_here = [dict(copy) for copy in (item.get("copies") or [])]
            copies.extend(rows_here)
            # The container identity is the request id, not run_index: each
            # ``golden run`` is its own single-request cohort, so run_index is 0
            # for every request and would collapse the whole cohort into one
            # container.
            containers.extend([str(row.get("request_id") or "")] * len(rows_here))
            summary = summarize_copies(rows_here)
            per_container.append({
                "request_id": row.get("request_id"),
                "run_index": row.get("run_index"),
                "duration_ms": row.get("duration_ms"),
                "copies": len(rows_here),
                "p50_ms": summary["wall_ms"]["p50"],
                "p90_ms": summary["wall_ms"]["p90"],
                "p99_ms": summary["wall_ms"]["p99"],
                "max_ms": summary["wall_ms"]["max"],
                "cpu_p50_ms": summary["thread_cpu_ms"]["p50"],
                "ratio_p50": summary["wall_cpu_ratio"]["p50"],
                "over_thresholds": summary["over_thresholds"],
            })
    pooled = summarize_copies(copies) if copies else summarize_copies([])
    return {
        "variant": variant or "all",
        "container_count": len(per_container),
        "copy_count": len(copies),
        "wall_ms": pooled["wall_ms"],
        "thread_cpu_ms": pooled["thread_cpu_ms"],
        "wall_cpu_ratio": pooled["wall_cpu_ratio"],
        "over_thresholds": pooled["over_thresholds"],
        "slowest": pooled["slowest"],
        "distinct_source_offsets": pooled["distinct_source_offsets"],
        "distinct_dest_slots": pooled["distinct_dest_slots"],
        "per_container": per_container,
        "source_offset_repeat": repeat_analysis(copies, "source_offset", containers=containers),
        "dest_slot_repeat": repeat_analysis(copies, "dest_slot", containers=containers),
        "reader_repeat": repeat_analysis(copies, "reader", containers=containers),
        "ordinal_repeat": repeat_analysis(copies, "copy_ordinal", containers=containers),
    }


def host_evidence(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    gpus: Counter = Counter()
    bdf: Counter = Counter()
    pcie: Counter = Counter()
    clocks: Counter = Counter()
    pstate: Counter = Counter()
    affinity: Counter = Counter()
    regions: Counter = Counter()
    for row in rows:
        placement = ((row.get("host") or {}).get("placement") or {})
        gpu = placement.get("gpu") or {}
        gpus[str(gpu.get("name"))] += 1
        bdf[str(gpu.get("pci_bus_id"))] += 1
        nvml = gpu.get("nvml") or {}
        pcie[f"gen{nvml.get('pcie_generation')}x{nvml.get('pcie_width')}"] += 1
        clocks[f"sm{nvml.get('sm_clock_mhz')}/mem{nvml.get('mem_clock_mhz')}"] += 1
        pstate[str(nvml.get("performance_state"))] += 1
        affinity[str((placement.get("parent") or {}).get("cpu_affinity_count"))] += 1
        regions[str(((row.get("identity") or {}).get("region")))] += 1
    return {
        "gpu_names": dict(gpus),
        "pci_bus_ids": dict(bdf),
        "pcie_gen_width": dict(pcie),
        "sm_mem_clocks": dict(clocks),
        "performance_state": dict(pstate),
        "cpu_affinity_count": dict(affinity),
        "identity_region": dict(regions),
    }


def build(root: Path, profile: str = PROFILE) -> dict[str, Any]:
    attempts = load_attempts(root, profile)
    usable = [row for row in attempts if attempt_is_usable(row)]
    by_arm: dict[str, list[dict[str, Any]]] = {arm: [] for arm in ARMS}
    for row in usable:
        by_arm.setdefault(row["arm"], []).append(row)

    arms: dict[str, Any] = {}
    for arm, rows in by_arm.items():
        if not rows:
            arms[arm] = {"usable_containers": 0, "layout": None}
            continue
        report = rows[0]["report"]
        entry: dict[str, Any] = {
            "usable_containers": len(rows),
            "layout": report.get("arm_layout"),
            "source": report.get("source"),
            "destination": report.get("destination"),
            "host": host_evidence(rows),
            "pooled": arm_summary(rows),
            "variants": {},
        }
        for variant in report.get("arm_layout", {}).get("variants", []):
            if not variant_complete(rows, str(variant)):
                continue
            entry["variants"][str(variant)] = arm_summary(rows, str(variant))
        arms[arm] = entry
    return {
        "profile": profile,
        "attempt_count": len(attempts),
        "usable_count": len(usable),
        "attempts": [
            {
                "request_id": row["request_id"],
                "run_index": row["run_index"],
                "arm": row["arm"],
                "valid": row["valid"],
                "dnf": row["dnf"],
                "true_cold": row["true_cold"],
                "arm_status": row["arm_status"],
                "duration_ms": row["duration_ms"],
                "usable": attempt_is_usable(row),
                "failures": row["failures"],
                "variants_complete": row.get("variants_complete"),
                "variants_expected": row.get("variants_expected"),
                "teardown": row.get("teardown"),
            }
            for row in attempts
        ],
        "arms": arms,
    }


def classify(summary: Mapping[str, Any]) -> dict[str, Any]:
    """Apply the decision structure to the pooled per-arm evidence.

    ``pathological`` is defined on the pooled p99 against the control arm, and
    is only asserted when the arm has at least two usable containers; a single
    container cannot establish that a distribution is sick.
    """
    arms = summary.get("arms") or {}
    verdicts: dict[str, dict[str, Any]] = {}
    control = arms.get("A") or {}
    control_p99 = ((control.get("pooled") or {}).get("wall_ms") or {}).get("p99")
    for arm, entry in arms.items():
        pooled = entry.get("pooled") or {}
        p99 = (pooled.get("wall_ms") or {}).get("p99")
        containers = int(entry.get("usable_containers") or 0)
        pathological = bool(
            containers >= 2 and p99 is not None and control_p99 is not None
            and p99 > 3.0 * max(control_p99, 1e-9)
        )
        verdicts[arm] = {
            "usable_containers": containers,
            "p99_ms": p99,
            "max_ms": (pooled.get("wall_ms") or {}).get("max"),
            "over_250ms": (pooled.get("over_thresholds") or {}).get(">250ms"),
            "over_1000ms": (pooled.get("over_thresholds") or {}).get(">1000ms"),
            "pathological": pathological,
        }
    sick = {arm for arm, item in verdicts.items() if item["pathological"]}
    if not sick:
        outcome = "INCONCLUSIVE"
    elif sick == {"A"}:
        outcome = "INTERACTION_ONLY"
    elif sick == {"A", "B"} and not (sick & {"C", "D"}):
        outcome = "SOURCE_SIDE"
    elif sick == {"A", "C"} and not (sick & {"B", "D"}):
        outcome = "DESTINATION_SIDE"
    elif sick == set(ARMS):
        outcome = "HOST_MEMORY_GLOBAL"
    elif sick & {"C", "D"}:
        outcome = "MIXED"
    else:
        outcome = "MIXED"
    # Concurrency: a single-thread control healthy while its four-thread twin is
    # pathological is a distinct mechanism from any placement effect.
    for arm in ("C", "D"):
        entry = arms.get(arm) or {}
        variants = entry.get("variants") or {}
        single = ((variants.get("single") or {}).get("wall_ms") or {})
        four = ((variants.get("concurrent4") or {}).get("wall_ms") or {})
        single_p99 = single.get("p99")
        four_p99 = four.get("p99")
        if single_p99 and four_p99 and four_p99 > 3.0 * max(single_p99, 1e-9):
            outcome = "CONCURRENCY_SPECIFIC"
    return {"arm_verdicts": verdicts, "classification": outcome}


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".", help="repository root of the experiment worktree")
    parser.add_argument("--profile", default=PROFILE)
    parser.add_argument("--out", default="", help="optional JSON output path")
    args = parser.parse_args(argv)
    root = Path(args.root).resolve()
    summary = build(root, args.profile)
    summary["classification"] = classify(summary)
    text = json.dumps(summary, indent=2, sort_keys=True)
    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
