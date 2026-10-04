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
* the single-thread versus four-thread comparison for arms C and D;
* for the population arms A2 and A3, the setup cost of the treatment itself and
  the ordinal-0..7 head/tail split, so a fast copy loop cannot hide a slow setup.

Cohorts are keyed by **deployment fingerprint**, not by arm and not by profile.
Arm A was run from three different deployments across the two phases, and a
profile is not a deployment: one profile was deployed twice.  Pooling across
deployments would silently present two different code states as one homogeneous
cohort, which is the one thing the deployment-identity rule exists to prevent.

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
    ordinal_head,
    summarize_copies,
)

PROFILE_PREFIX = "golden_p1_parallel_p9_srccopy_iso"
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


def load_attempts(root: Path, profile_prefix: str = PROFILE_PREFIX) -> list[dict[str, Any]]:
    """One row per cohort manifest found under the artifacts tree."""
    attempts: list[dict[str, Any]] = []
    for manifest_path in sorted(root.glob("artifacts/**/manifest.json")):
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(manifest, Mapping):
            continue
        if not str(manifest.get("profile") or "").startswith(profile_prefix):
            continue
        for attempt in manifest.get("attempts") or []:
            if not isinstance(attempt, Mapping):
                continue
            reports = _find_reports(attempt)
            row: dict[str, Any] = {
                "cohort_dir": str(manifest.get("cohort_dir") or ""),
                "profile": str(manifest.get("profile") or ""),
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
        "ordinal_head": ordinal_head(copies),
        "per_container": per_container,
        "source_offset_repeat": repeat_analysis(copies, "source_offset", containers=containers),
        "dest_slot_repeat": repeat_analysis(copies, "dest_slot", containers=containers),
        "reader_repeat": repeat_analysis(copies, "reader", containers=containers),
        "ordinal_repeat": repeat_analysis(copies, "copy_ordinal", containers=containers),
    }


def population_evidence(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """What each container's arm payload says about the population treatment.

    Aggregated rather than taken from one row because the interesting failure
    mode is "the treatment landed in some containers and not others", which a
    single row would hide.
    """
    arms: Counter = Counter()
    fadvise_counts: Counter = Counter()
    fadvise_return_codes: Counter = Counter()
    mmap_flags: Counter = Counter()
    reasons: Counter = Counter()
    errors: Counter = Counter()
    warm_primitives: Counter = Counter()
    warm_completed: Counter = Counter()
    warm_bytes_requested: list[int] = []
    warm_bytes_read: list[int] = []
    warm_total_ms: list[float] = []
    warm_gbps: list[float] = []
    fadvise_wall_ms: list[float] = []
    mmap_wall_ms: list[float] = []
    plan_build_ms: list[float] = []
    for row in rows:
        population = (row.get("report") or {}).get("population") or {}
        arms[str(population.get("arm") or "")] += 1
        fadvise_counts[str(population.get("fadvise_call_count"))] += 1
        fadvise_return_codes[str(population.get("fadvise_return_code"))] += 1
        mmap_flags[str(population.get("mmap_flags"))] += 1
        if population.get("reason"):
            reasons[str(population["reason"])] += 1
        if population.get("error"):
            errors[str(population["error"])] += 1
        if population.get("warm_read_called"):
            warm_primitives[str(population.get("warm_primitive"))] += 1
            warm_completed[str(bool(population.get("warm_complete")))] += 1
            for key, sink in (
                ("warm_bytes_requested", warm_bytes_requested),
                ("warm_bytes_read", warm_bytes_read),
            ):
                value = population.get(key)
                if isinstance(value, int):
                    sink.append(value)
            for key, sink in (
                ("warm_total_ms", warm_total_ms),
                ("warm_effective_gbps", warm_gbps),
            ):
                value = population.get(key)
                if isinstance(value, (int, float)):
                    sink.append(float(value))
        for key, sink in (
            ("fadvise_wall_ms", fadvise_wall_ms),
            ("mmap_wall_ms", mmap_wall_ms),
            ("plan_build_total_ms", plan_build_ms),
        ):
            value = population.get(key)
            if isinstance(value, (int, float)):
                sink.append(float(value))
    warm_proven = bool(warm_bytes_read) and all(
        read == requested for read, requested in zip(warm_bytes_read, warm_bytes_requested)
    ) and warm_completed.get("True", 0) == len(warm_bytes_read)
    return {
        "containers": len(rows),
        "arm_names": dict(arms),
        "fadvise_call_count": dict(fadvise_counts),
        "fadvise_return_code": dict(fadvise_return_codes),
        "mmap_flags": dict(mmap_flags),
        "reasons": dict(reasons),
        "errors": dict(errors),
        "warm": {
            "containers_with_a_warm_read": len(warm_bytes_read),
            "primitives": dict(warm_primitives),
            "complete": dict(warm_completed),
            # FULL_READ_PROVEN in the report: every container that claims a warm
            # read consumed exactly the file size it declared, and said so.
            "every_warm_read_exact": warm_proven,
            "bytes_requested": sorted(set(warm_bytes_requested)),
            "bytes_read": sorted(set(warm_bytes_read)),
            "total_ms": summarize_copies(
                [{"wall_ms": value} for value in warm_total_ms]
            )["wall_ms"] if warm_total_ms else None,
            "effective_gbps": summarize_copies(
                [{"wall_ms": value} for value in warm_gbps]
            )["wall_ms"] if warm_gbps else None,
        },
        "fadvise_wall_ms": summarize_copies(
            [{"wall_ms": value} for value in fadvise_wall_ms]
        )["wall_ms"] if fadvise_wall_ms else None,
        "mmap_wall_ms": summarize_copies(
            [{"wall_ms": value} for value in mmap_wall_ms]
        )["wall_ms"] if mmap_wall_ms else None,
        "plan_build_total_ms": summarize_copies(
            [{"wall_ms": value} for value in plan_build_ms]
        )["wall_ms"] if plan_build_ms else None,
    }


def warm_read_evidence(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """The A4 warm-read distribution, pooled and per container.

    The warm read is evidence in its own right: it is the first real measurement
    of the positioned-read primitive over a whole 12.31 GB checkpoint on this
    Volume, which is the candidate replacement source path.  It is reported as
    blocks (one per syscall group) and as a total, because a primitive can have a
    healthy median and still carry the pathological tail this experiment is
    hunting.
    """
    blocks: list[dict[str, Any]] = []
    totals: list[float] = []
    gbps: list[float] = []
    bytes_read: list[int] = []
    bytes_requested: list[int] = []
    calls: list[int] = []
    retries: list[int] = []
    per_container: list[dict[str, Any]] = []
    for row in rows:
        population = (row.get("report") or {}).get("population") or {}
        if not population.get("warm_read_called"):
            continue
        container_blocks = [
            dict(item) for item in (population.get("warm_blocks") or [])
        ]
        blocks.extend(container_blocks)
        for key, sink in (
            ("warm_total_ms", totals),
            ("warm_effective_gbps", gbps),
        ):
            value = population.get(key)
            if isinstance(value, (int, float)):
                sink.append(float(value))
        for key, sink in (
            ("warm_bytes_read", bytes_read),
            ("warm_bytes_requested", bytes_requested),
            ("warm_read_calls", calls),
            ("warm_short_read_retries", retries),
        ):
            value = population.get(key)
            if isinstance(value, int):
                sink.append(value)
        walls = [
            float(item["wall_ms"]) for item in container_blocks
            if isinstance(item.get("wall_ms"), (int, float))
        ]
        if walls:
            container_summary = summarize_copies([{"wall_ms": w} for w in walls])
            per_container.append({
                "request_id": row.get("request_id"),
                "blocks": len(container_blocks),
                "warm_ms": population.get("warm_total_ms"),
                "effective_gbps": population.get("warm_effective_gbps"),
                "wall_ms": container_summary["wall_ms"],
                "thread_cpu_ms": summarize_copies([
                    {"wall_ms": float(item["thread_cpu_ms"])}
                    for item in container_blocks
                    if isinstance(item.get("thread_cpu_ms"), (int, float))
                ])["wall_ms"] if container_blocks else None,
                "over_thresholds": container_summary["over_thresholds"],
                "slowest_blocks": container_summary["slowest"],
                # Per-container, not pooled: this is the number that decides
                # whether the warm reads themselves carry the pathological tail.
                "pathological_blocks": sum(
                    1 for item in container_blocks
                    if float(item.get("wall_ms") or 0.0) > WARM_READ_PATHOLOGICAL_MS
                ),
            })
    pooled = summarize_copies(
        [{"wall_ms": float(item["wall_ms"])} for item in blocks
         if isinstance(item.get("wall_ms"), (int, float))]
    )
    total_ms = sum(totals) if totals else None
    total_bytes = sum(bytes_read) if bytes_read else None
    return {
        "containers": len(per_container),
        "block_count": len(blocks),
        "block_bytes": (
            blocks[0].get("requested_bytes") if blocks else None
        ),
        "wall_ms": pooled["wall_ms"],
        "over_thresholds": pooled["over_thresholds"],
        "total_ms": total_ms,
        "bytes_read": total_bytes,
        "bytes_requested": sum(bytes_requested) if bytes_requested else None,
        # Pooled over containers, so a slow read shows up as low throughput
        # rather than being divided away.
        "effective_gbps": (
            (total_bytes / 1e9) / (total_ms / 1e3)
            if (total_ms and total_bytes) else None
        ),
        "per_container_gbps": summarize_copies(
            [{"wall_ms": value} for value in gbps]
        )["wall_ms"] if gbps else None,
        "read_calls": calls,
        "short_read_retries": retries,
        "pathological_block_ms": WARM_READ_PATHOLOGICAL_MS,
        "pathological_containers": sum(
            1 for item in per_container if item["pathological_blocks"] > 0
        ),
        "per_container": per_container,
        "ordinal_head": ordinal_head([
            {"copy_ordinal": item.get("ordinal"), "wall_ms": item.get("wall_ms"),
             "source_offset": item.get("source_offset")}
            for item in blocks
            if isinstance(item.get("wall_ms"), (int, float))
        ]),
        "offset_repeat": repeat_analysis(
            [
                {"source_offset": item.get("source_offset"),
                 "wall_ms": item.get("wall_ms")}
                for item in blocks
                if isinstance(item.get("wall_ms"), (int, float))
            ],
            "source_offset",
            containers=[str(item.get("request_id")) for item in blocks],
        ),
    }


def setup_cost_evidence(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Per-container treatment cost, taken from the payload's own accounting.

    A prefetch that made the copies fast while spending seconds in ``mmap`` would
    otherwise read as a win, because the copy loop is what the arm measures.  The
    numbers are read from ``report["variants"][*]["setup_costs"]`` as the
    container computed them rather than recomputed here: the boundaries were
    taken inside the container that ran the arm, and re-deriving them from
    artifact fields would invent a different measurement.
    """
    costs: list[dict[str, Any]] = []
    for row in rows:
        report = row.get("report") or {}
        population = report.get("population") or {}
        per_variant = []
        for item in report.get("variants") or []:
            computed = item.get("setup_costs")
            if not isinstance(computed, Mapping):
                continue
            per_variant.append({
                "variant": str(item.get("variant")),
                "setup_costs": dict(computed),
                "variant_wall_ms": item.get("wall_ms"),
                "copy_count": len(item.get("copies") or []),
            })
        costs.append({
            "request_id": row.get("request_id"),
            "declared_arm": population.get("declared_arm"),
            "observed_arm": population.get("observed_arm"),
            "contract_satisfied": population.get("satisfied"),
            "mapped_bytes": population.get("mapped_bytes"),
            "fd_open_wall_ms": population.get("fd_open_wall_ms"),
            "fadvise_wall_ms": population.get("fadvise_wall_ms"),
            "mmap_wall_ms": population.get("mmap_wall_ms"),
            "plan_build_total_ms": population.get("plan_build_total_ms"),
            "variants": per_variant,
        })
    return costs


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


def build(root: Path, profile_prefix: str = PROFILE_PREFIX) -> dict[str, Any]:
    attempts = load_attempts(root, profile_prefix)
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
            "population": population_evidence(rows),
            "pooled": arm_summary(rows),
            "variants": {},
            "cohorts": {},
        }
        by_deployment: dict[str, list[Mapping[str, Any]]] = {}
        for row in rows:
            by_deployment.setdefault(
                str(row.get("deployment_fingerprint") or "unknown"), []
            ).append(row)
        for fingerprint, deploy_rows in sorted(by_deployment.items()):
            deploy_pooled = arm_summary(deploy_rows)
            entry["cohorts"][fingerprint] = {
                "deploy_fingerprint": fingerprint,
                "profiles": sorted({
                    str(row.get("profile") or "") for row in deploy_rows
                }),
                "usable_containers": len(deploy_rows),
                "images": sorted({
                    str(row.get("image_id") or "") for row in deploy_rows
                }),
                "request_ids": [
                    str(row.get("request_id") or "") for row in deploy_rows
                ],
                "pooled": deploy_pooled,
                "setup_costs": setup_cost_evidence(deploy_rows),
                "warm_read": warm_read_evidence(deploy_rows),
                "pathological": is_pathological(deploy_pooled, len(deploy_rows)),
            }
        for variant in report.get("arm_layout", {}).get("variants", []):
            if not variant_complete(rows, str(variant)):
                continue
            entry["variants"][str(variant)] = arm_summary(rows, str(variant))
        arms[arm] = entry
    return {
        "profile_prefix": profile_prefix,
        "attempt_count": len(attempts),
        "usable_count": len(usable),
        "attempts": [
            {
                "request_id": row["request_id"],
                "run_index": row["run_index"],
                "profile": row["profile"],
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


# Absolute, not relative.  "Pathological" has to mean the regime Phase-1
# measured (rare copies from ~100 ms to seconds), not "slower than some other
# arm", because the arm that happens to be slowest is itself a candidate for the
# mechanism.  A copy over 100 ms is 2x a healthy 50 ms copy and 12x a resident
# anonymous one, and Phase-1 saw the same copies run to 1460 ms.
SLOW_FRACTION_FLOOR = 0.01
PATHOLOGICAL_P99_MS = 100.0

# A4's warm-read pathological threshold, fixed BEFORE any A4 container was run.
#
# The copy rule is "any single 64 MiB copy over 100 ms is pathological", because
# a healthy 64 MiB copy is 50 ms.  A positioned read of the same 64 MiB has a very
# different natural cost: it moves the same bytes but through the syscall and
# page-cache path rather than through a mapped page, so its floor is higher.  At
# 250 ms a 64 MiB read is running below 0.27 GB/s, which is the same order of
# pathology as a 100 ms mmap copy and not something a healthy primitive does
# occasionally.  So a warm-read block over 250 ms is what counts as pathological
# here, and it is deliberately NOT the copy's 100 ms: using 100 ms would classify
# a merely-slower-than-mmap primitive as broken and manufacture CASE 3.
WARM_READ_PATHOLOGICAL_MS = 250.0


def is_pathological(pooled: Mapping[str, Any], containers: int) -> bool:
    """One arm's pooled distribution, judged on its own absolute shape."""
    if int(containers) < 2:
        # A single container cannot establish that a distribution is sick.
        return False
    wall = (pooled.get("wall_ms") or {})
    count = int(wall.get("count") or 0)
    p99 = wall.get("p99")
    if count <= 0 or p99 is None:
        return False
    over_100 = int((pooled.get("over_thresholds") or {}).get(">100ms") or 0)
    slow_fraction = over_100 / count
    return bool(
        slow_fraction >= SLOW_FRACTION_FLOOR and p99 >= PATHOLOGICAL_P99_MS
    )


def classify(summary: Mapping[str, Any]) -> dict[str, Any]:
    """Apply the decision structure to the pooled per-arm evidence."""
    arms = summary.get("arms") or {}
    verdicts: dict[str, dict[str, Any]] = {}
    for arm, entry in arms.items():
        pooled = entry.get("pooled") or {}
        containers = int(entry.get("usable_containers") or 0)
        wall = (pooled.get("wall_ms") or {})
        count = int(wall.get("count") or 0)
        over_100 = int((pooled.get("over_thresholds") or {}).get(">100ms") or 0)
        verdicts[arm] = {
            "usable_containers": containers,
            "copy_count": count,
            "p50_ms": wall.get("p50"),
            "p99_ms": wall.get("p99"),
            "max_ms": wall.get("max"),
            "over_100ms": over_100,
            "over_100ms_fraction": round(over_100 / count, 6) if count else None,
            "over_250ms": (pooled.get("over_thresholds") or {}).get(">250ms"),
            "over_1000ms": (pooled.get("over_thresholds") or {}).get(">1000ms"),
            "pathological": is_pathological(pooled, containers),
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


# The population question is narrower than the placement question above, so it
# gets its own rule instead of being forced through the A/B/C/D structure.  A is
# the control: same mapped source, no treatment.  A2 adds one POSIX_FADV_WILLNEED
# and A3 adds MAP_POPULATE.  "Pathological" keeps the identical absolute rule, so
# a treatment is only credited with removing the stall, never with being slow.
POPULATION_CONTROL_ARM = "A"
POPULATION_ARMS_BY_TREATMENT = {"A2": "WILLNEED", "A3": "MAP_POPULATE"}
FULLREAD_ARM = "A4"


def pathological_containers(per_container: Sequence[Mapping[str, Any]]) -> int:
    """How many individual containers showed the pathological regime at all.

    The pooled decision rule is a statement about a distribution.  A mechanism
    that fires in one container out of five is invisible to a pooled p99 diluted
    by four healthy containers, so a treatment can clear the pooled thresholds
    while its own arm still contains a full-blown pathological container.  This
    count is what separates "the treatment removed the stall" from "the
    treatment was lucky", and it is the number the decision has to respect.
    """
    total = 0
    for container in per_container:
        thresholds = container.get("over_thresholds") or {}
        if int(thresholds.get(">100ms") or 0) > 0:
            total += 1
    return total


def classify_population(summary: Mapping[str, Any]) -> dict[str, Any]:
    """Did forcing the backing pages in remove the mapped-source copy stall?

    Read off the per-deployment cohorts, because an arm name is not a deployment
    and this decision must not be taken across two code states.
    """
    arms = summary.get("arms") or {}
    verdicts: dict[str, Any] = {}
    control_sick: bool | None = None
    for arm in (POPULATION_CONTROL_ARM, *sorted(POPULATION_ARMS_BY_TREATMENT)):
        cohorts = (arms.get(arm) or {}).get("cohorts") or {}
        records: list[dict[str, Any]] = []
        for fingerprint, cohort in sorted(cohorts.items()):
            pooled = cohort.get("pooled") or {}
            wall = pooled.get("wall_ms") or {}
            count = int(wall.get("count") or 0)
            over_100 = int((pooled.get("over_thresholds") or {}).get(">100ms") or 0)
            records.append({
                "deploy_fingerprint": fingerprint,
                "profiles": cohort.get("profiles"),
                "usable_containers": cohort.get("usable_containers"),
                "images": cohort.get("images"),
                "copy_count": count,
                "p50_ms": wall.get("p50"),
                "p90_ms": wall.get("p90"),
                "p99_ms": wall.get("p99"),
                "max_ms": wall.get("max"),
                "over_100ms": over_100,
                "over_100ms_fraction": round(over_100 / count, 6) if count else None,
                "over_250ms": (pooled.get("over_thresholds") or {}).get(">250ms"),
                "over_1000ms": (pooled.get("over_thresholds") or {}).get(">1000ms"),
                "pathological": cohort.get("pathological"),
                "pathological_containers": pathological_containers(
                    (cohort.get("pooled") or {}).get("per_container") or []
                ),
                "containers": cohort.get("usable_containers"),
                "ordinal_head": pooled.get("ordinal_head"),
                "setup_costs": cohort.get("setup_costs"),
                "population": (arms.get(arm) or {}).get("population"),
            })
        verdicts[arm] = {"deployments": records}
        if arm == POPULATION_CONTROL_ARM and records:
            # More than one control deployment means the cohort is not a single
            # code state; say so instead of picking one silently.
            control_sick = any(item.get("pathological") for item in records)
            verdicts[arm]["multiple_deployments"] = len(records) > 1
    def _sick_container_count(arm: str) -> int:
        records = verdicts[arm]["deployments"]
        return int(records[-1].get("pathological_containers") or 0) if records else 0

    pooled_healthy = {
        arm for arm in POPULATION_ARMS_BY_TREATMENT
        if verdicts[arm]["deployments"]
        and not verdicts[arm]["deployments"][-1].get("pathological")
    }
    pooled_sick = set(POPULATION_ARMS_BY_TREATMENT) - pooled_healthy
    control_records = verdicts[POPULATION_CONTROL_ARM]["deployments"]
    control_sick_containers = _sick_container_count(POPULATION_CONTROL_ARM)
    treatment_sick_containers = {
        arm: _sick_container_count(arm) for arm in POPULATION_ARMS_BY_TREATMENT
    }
    # A treatment is only credited when its own arm contains no pathological
    # container.  Clearing the pooled thresholds is not enough, because the
    # mechanism is intermittent: an arm with one catastrophic container out of
    # five still has that catastrophic container.
    healthy = {arm for arm in pooled_healthy if treatment_sick_containers[arm] == 0}
    sick = set(POPULATION_ARMS_BY_TREATMENT) - healthy
    reasons: list[str] = []
    if control_sick is None:
        outcome = "INCONCLUSIVE_CURRENT_COHORT"
        reasons.append("no_control_cohort")
    elif not control_sick:
        outcome = "INCONCLUSIVE_CURRENT_COHORT"
        reasons.append("control_did_not_reproduce_the_stall")
    elif control_sick_containers == 0:
        outcome = "INCONCLUSIVE_CURRENT_COHORT"
        reasons.append("control_has_no_pathological_container_to_explain")
    elif healthy == {"A2"}:
        outcome = "WILLNEED_ONLY_EFFECTIVE"
    elif healthy:
        outcome = "BACKING_POPULATION_CONFIRMED"
    elif pooled_sick == set(POPULATION_ARMS_BY_TREATMENT) and all(
        count >= control_sick_containers for count in treatment_sick_containers.values()
    ):
        outcome = "PREFETCH_FAMILY_FAILED"
        reasons.append(
            "every_treatment_arm_still_contains_a_pathological_container"
        )
    elif pooled_healthy - healthy:
        outcome = "INCONCLUSIVE_CURRENT_COHORT"
        reasons.append(
            "pooled_thresholds_and_per_container_evidence_disagree"
        )
    else:
        outcome = "MIXED"
    if control_records and len(control_records) > 1:
        reasons.append("control_spans_multiple_deployments")
    return {
        "arm_verdicts": verdicts,
        "classification": outcome,
        "healthy_treatment_arms": sorted(healthy),
        "pooled_healthy_treatment_arms": sorted(pooled_healthy),
        "pathological_treatment_arms": sorted(sick),
        "pathological_containers": {
            POPULATION_CONTROL_ARM: control_sick_containers,
            **treatment_sick_containers,
        },
        "reasons": reasons,
    }


def classify_fullread(summary: Mapping[str, Any]) -> dict[str, Any]:
    """A4's question: did synchronously consuming the file fix the mapped copy?

    Read off the per-deployment cohorts, because an arm name is not a deployment
    and this decision must not be taken across two code states.  The two arms are
    required to come from the SAME deployment fingerprint; if they do not, there
    is no contemporaneous control and the answer is inconclusive by construction.

    Per-container, never pooled-only.  The A2/A3 phase produced the exact trap
    this guards: a treatment cleared the pooled thresholds while its own arm still
    contained a 2.1 s copy, because one sick container in five is diluted by four
    healthy ones.
    """
    arms = summary.get("arms") or {}
    cohorts: dict[str, dict[str, Any]] = {}
    for arm in (POPULATION_CONTROL_ARM, FULLREAD_ARM):
        for fingerprint, cohort in sorted(
            ((arms.get(arm) or {}).get("cohorts") or {}).items()
        ):
            cohorts.setdefault(arm, {})[fingerprint] = cohort

    def newest(arm: str) -> dict[str, Any] | None:
        entries = cohorts.get(arm) or {}
        if not entries:
            return None
        # One cohort per arm is the expected shape; if a profile was redeployed
        # the newest fingerprint is the contemporaneous one and the older ones
        # stay visible in the arm's own record.
        return entries[sorted(entries)[-1]]

    control = newest(POPULATION_CONTROL_ARM)
    treated = newest(FULLREAD_ARM)
    result: dict[str, Any] = {
        "arm_verdicts": {},
        "reasons": [],
        "full_read_proven": None,
        "postwarm_mmap_clean": None,
        "positioned_read_replacement_justified": "unknown",
    }
    if control is None or treated is None:
        missing = [
            name for name, cohort in (
                (POPULATION_CONTROL_ARM, control), (FULLREAD_ARM, treated)
            ) if cohort is None
        ]
        result["classification"] = "INCONCLUSIVE_CURRENT_COHORT"
        result["reasons"].append(f"missing_cohort:{','.join(missing)}")
        return result

    control_fp = sorted(cohorts[POPULATION_CONTROL_ARM])[-1]
    treated_fp = sorted(cohorts[FULLREAD_ARM])[-1]
    result["contemporaneous"] = control_fp == treated_fp
    if control_fp != treated_fp:
        result["classification"] = "INCONCLUSIVE_CURRENT_COHORT"
        result["reasons"].append("control_and_treatment_are_different_deployments")
        return result

    def verdict(arm: str, cohort: Mapping[str, Any]) -> dict[str, Any]:
        pooled = cohort.get("pooled") or {}
        wall = pooled.get("wall_ms") or {}
        count = int(wall.get("count") or 0)
        over_100 = int((pooled.get("over_thresholds") or {}).get(">100ms") or 0)
        per_container = pooled.get("per_container") or []
        return {
            "deploy_fingerprint": sorted(cohorts[arm])[-1],
            "profiles": cohort.get("profiles"),
            "images": cohort.get("images"),
            "usable_containers": cohort.get("usable_containers"),
            "copy_count": count,
            "p50_ms": wall.get("p50"),
            "p90_ms": wall.get("p90"),
            "p95_ms": wall.get("p95"),
            "p99_ms": wall.get("p99"),
            "max_ms": wall.get("max"),
            "over_100ms": over_100,
            "over_100ms_fraction": round(over_100 / count, 6) if count else None,
            "over_250ms": (pooled.get("over_thresholds") or {}).get(">250ms"),
            "over_500ms": (pooled.get("over_thresholds") or {}).get(">500ms"),
            "over_1000ms": (pooled.get("over_thresholds") or {}).get(">1000ms"),
            "pooled_pathological": cohort.get("pathological"),
            "pathological_containers": pathological_containers(per_container),
            "per_container": per_container,
            "ordinal_head": pooled.get("ordinal_head"),
            "setup_costs": cohort.get("setup_costs"),
            "warm_read": cohort.get("warm_read"),
        }

    control_verdict = verdict(POPULATION_CONTROL_ARM, control)
    treated_verdict = verdict(FULLREAD_ARM, treated)
    result["arm_verdicts"] = {
        POPULATION_CONTROL_ARM: control_verdict,
        FULLREAD_ARM: treated_verdict,
    }

    warm = treated_verdict.get("warm_read") or {}
    full_read_proven = bool(
        warm.get("containers")
        and warm.get("containers") == treated_verdict["usable_containers"]
        and warm.get("every_warm_read_exact")
    )
    result["full_read_proven"] = full_read_proven
    if not full_read_proven:
        result["classification"] = "INCONCLUSIVE_CURRENT_COHORT"
        result["reasons"].append("the_warm_read_was_not_proven_on_every_container")
        return result

    control_sick = control_verdict["pathological_containers"]
    treated_sick = treated_verdict["pathological_containers"]
    warm_sick = int(warm.get("pathological_containers") or 0)
    result["pathological_containers"] = {
        POPULATION_CONTROL_ARM: control_sick,
        FULLREAD_ARM: treated_sick,
        "A4_warm_reads": warm_sick,
    }
    postwarm_clean = treated_sick == 0
    result["postwarm_mmap_clean"] = postwarm_clean

    if control_sick == 0:
        # CASE 4. The control did not reproduce the pathology, so there is nothing
        # for the warm read to have removed, and A4 is not evidence either way.
        result["classification"] = "INCONCLUSIVE_CURRENT_COHORT"
        result["reasons"].append("control_did_not_reproduce_the_pathology")
        return result
    if postwarm_clean:
        # CASE 1.
        result["classification"] = "BACKING_AVAILABILITY_CONFIRMED"
        result["reasons"].append(
            "control_pathological_and_no_treatment_container_pathological"
        )
    elif warm_sick == 0:
        # CASE 2. The source data was definitely consumed through another path and
        # the mapped reads are still pathological, while the positioned reads
        # themselves look healthy.  That is the evidence that would justify
        # replacing mmap -> memmove with positioned read -> arena.
        result["classification"] = "MMAP_PATH_CONFIRMED"
        result["positioned_read_replacement_justified"] = "yes"
        result["reasons"].append(
            "mmap_still_pathological_after_a_proven_full_read_while_the_"
            "positioned_reads_themselves_are_clean"
        )
    elif warm_sick < control_sick:
        # Neither arm is clean, but the warm reads are materially healthier than
        # the control's mapped copies.  Reporting a decisive mechanism here would
        # over-read a small cohort.
        result["classification"] = "MIXED"
        result["reasons"].append(
            "both_access_paths_show_a_tail_but_the_positioned_reads_are_fewer"
        )
    else:
        # CASE 3. Both primitives suffer, so the problem is not the mmap syscall.
        result["classification"] = "BROADER_SOURCE_BACKEND_PATHOLOGY"
        result["reasons"].append(
            "positioned_reads_show_the_same_pathological_tail_as_the_mapped_copies"
        )
    return result


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".", help="repository root of the experiment worktree")
    parser.add_argument("--profile-prefix", default=PROFILE_PREFIX)
    parser.add_argument("--out", default="", help="optional JSON output path")
    args = parser.parse_args(argv)
    root = Path(args.root).resolve()
    summary = build(root, args.profile_prefix)
    summary["classification"] = classify(summary)
    summary["population_decision"] = classify_population(summary)
    summary["fullread_decision"] = classify_fullread(summary)
    text = json.dumps(summary, indent=2, sort_keys=True)
    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
