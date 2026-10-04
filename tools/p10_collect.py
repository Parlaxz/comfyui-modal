"""Collect P10 2x2 run metrics from v2ctl run manifests into one JSON ledger.

Usage:  python tools/p10_collect.py <arm> <run-manifest.json>

The v2ctl run manifest names the cohort output dir, which holds the authoritative
attempt_0.json.  Nothing here selects or interprets evidence by mtime: the caller
passes the manifest for the request it just ran.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def _find(obj, key):
    """Depth-first search for the first value stored under ``key``."""
    if isinstance(obj, dict):
        if key in obj:
            return obj[key]
        for value in obj.values():
            found = _find(value, key)
            if found is not None:
                return found
    elif isinstance(obj, list):
        for value in obj:
            found = _find(value, key)
            if found is not None:
                return found
    return None


def collect(manifest_path: Path) -> dict:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    out_dir = Path(manifest["artifacts"]["output_dir"])
    attempt = json.loads((out_dir / "attempt_0.json").read_text(encoding="utf-8"))

    validation = attempt.get("validation") or {}
    telemetry = attempt["golden_telemetry"] or {}
    stages = {s["name"]: s for s in telemetry.get("stages", [])}

    def stage_ms(name: str):
        stage = stages.get(name)
        if not stage:
            return None
        entry, end = stage.get("entry_monotonic_ns"), stage.get("end_monotonic_ns")
        if entry is None or end is None:
            return None
        return round((end - entry) / 1e6, 4)

    def stage_detail(name: str):
        return (stages.get(name) or {}).get("details") or {}

    restore_details = stage_detail("golden_restore")
    interval = restore_details.get("external_restore_interval") or {}
    preinit = interval.get("context_preinit_after_join") or {}

    # The arena's own evidence record is published as an event field, not as a
    # stage detail, so it is read from the golden_model_transport_load event that
    # carries arena_ensure.  Slot-capacity counters are siblings of arena_ensure
    # under the same source_detail.
    arena = {}
    source_detail = {}
    for event in telemetry.get("events") or []:
        detail = (event.get("fields") or {}).get("source_detail") or {}
        if detail.get("arena_ensure"):
            source_detail = detail
            arena = detail["arena_ensure"]
            break
    concurrency = source_detail.get("source_concurrency") or {}
    latency = source_detail.get("source_latency") or {}
    diag = arena.get("registration_diagnostic") or {}
    arm = arena.get("experiment_arm") or diag.get("experiment_arm") or {}
    marks = arena.get("startup_marks") or {}

    establish_ms = arena.get("arena_establish_wall_ms")
    if establish_ms is None and marks.get("c0_ensure_enter"):
        ready = marks.get("source_thread_ready") or marks.get("source_thread_start_end")
        if ready:
            establish_ms = round((int(ready) - int(marks["c0_ensure_enter"])) / 1e6, 4)

    clip_details = stage_detail("golden_clip_load")
    unet_details = stage_detail("golden_unet_load")
    clip_stats = clip_details.get("transport_stats") or {}
    unet_stats = unet_details.get("transport_stats") or {}

    def source_span_ms(details, stats):
        for key in ("source_fill_wall_ms", "source_span_ms", "source_wall_ms"):
            if isinstance(stats, dict) and stats.get(key) is not None:
                return stats[key]
        for key in ("source_span_ms", "source_wall_ms"):
            if details.get(key) is not None:
                return details[key]
        return None

    # registration_diagnostic is the authoritative record of what join()
    # returned, including whether the worker really ran off-thread and how long
    # the caller then waited.  The restore-interval snapshot is the non-blocking
    # view, which cannot report a join wait at all, so diag wins where present.
    preinit_mode = diag.get("context_preinit_mode") or preinit.get("context_preinit_mode")
    preinit_join_ms = diag.get("context_preinit_join_wait_ms")
    if preinit_join_ms is None:
        preinit_join_ms = preinit.get("context_preinit_join_wait_ms")
    preinit_wall = diag.get("context_preinit_ms")
    if preinit_wall is None:
        preinit_wall = preinit.get("context_preinit_wall_ms")

    record = {
        "arm": None,
        "request_id": attempt.get("request_id"),
        "profile": attempt.get("profile"),
        "valid": attempt.get("valid"),
        "true_cold": attempt.get("true_cold"),
        "dnf": attempt.get("dnf"),
        "error": attempt.get("error"),
        "failures": attempt.get("failures"),
        "capture_classification": (attempt.get("capture_guard") or {}).get("classification"),
        "capture_counted": (attempt.get("capture_guard") or {}).get("counted"),
        "output_sha_match": validation.get("output_sha_match"),
        "observed_output_shas": validation.get("observed_output_shas"),
        "output_endpoint": validation.get("output_endpoint"),
        "durability_mode": validation.get("output_durability_mode"),
        "fatal_failure": telemetry.get("fatal_failure"),
        "fallback_reason": telemetry.get("fallback_reason"),
        "fallback_source": telemetry.get("fallback_source"),
        "restore_count": _find(attempt, "restore_count"),
        "request_count": _find(attempt, "request_count"),
        "root_wall_ms": attempt.get("duration_ms"),
        "restore_total_ms": interval.get("minimal_restore_total_ms"),
        "restore_wall_excl_sched_ms": interval.get("restore_wall_ms_excluding_scheduling"),
        "context_preinit_launch": interval.get("context_preinit_launch"),
        "context_preinit_after_join": preinit,
        "preinit_mode": preinit_mode,
        "preinit_wall_ms": preinit_wall,
        "preinit_thread_cpu_ms": preinit.get("context_preinit_thread_cpu_ms"),
        "preinit_join_wait_ms": preinit_join_ms,
        "preinit_start_ns": preinit.get("context_preinit_start"),
        "preinit_end_ns": preinit.get("context_preinit_end"),
        "restore_setup_ms": interval.get("source_thread_restore_setup_ms"),
        "mutable_state_reset_ms": interval.get("mutable_state_reset_ms"),
        "logical_gpu_repair_ms": interval.get("logical_gpu_repair_ms"),
        "models_generation_check_ms": interval.get("models_generation_check_ms"),
        "stage_wall_ms": {name: stage_ms(name) for name in stages},
        "clip_load_wall_ms": stage_ms("golden_clip_load"),
        "unet_load_wall_ms": stage_ms("golden_unet_load"),
        "clip_source_wall_ms": source_span_ms(clip_details, clip_stats),
        "unet_source_wall_ms": source_span_ms(unet_details, unet_stats),
        "clip_transport_stats": clip_stats,
        "unet_transport_stats": unet_stats,
        "arena": arena,
        "run_manifest": str(manifest_path),
        "output_dir": str(out_dir),
    }
    if isinstance(arena, dict) and arena:
        record["slot_count"] = arena.get("slot_count")
        record["slot_bytes"] = arena.get("slot_bytes")
        record["arena_bytes"] = arena.get("arena_bytes")
        record["declared_slot_count"] = diag.get("declared_slot_count")
        record["declared_slot_bytes"] = diag.get("declared_slot_bytes")
        record["declared_arena_bytes"] = diag.get("declared_arena_bytes")
        record["registered"] = arena.get("registered")
        record["registration_order"] = arena.get("registration_order")
        record["context_preinit_enabled"] = diag.get("context_preinit")
        record["context_preinit_state"] = diag.get("context_preinit")
        record["context_preinit_diag_ms"] = diag.get("context_preinit_ms")
        record["context_preinit_diag_mode"] = diag.get("context_preinit_mode")
        record["context_preinit_diag_join_ms"] = diag.get("context_preinit_join_wait_ms")
        record["experiment_arm"] = arm
        record["register_ms"] = arena.get("register_ms")
        record["backing_create_ms"] = arena.get("backing_create_ms")
        record["arena_establish_wall_ms"] = establish_ms
        record["startup_marks"] = marks
        record["child_ready_evidence"] = arena.get("child_ready_evidence")
        record["slot_wait_count"] = concurrency.get("slot_wait_count")
        record["all_slots_occupied_count"] = concurrency.get("all_slots_occupied_count")
        record["capacity_wait_count"] = concurrency.get("capacity_wait_count")
        record["slot_wait_ms"] = latency.get("slot_wait_ms")
        record["capacity_wait_ms"] = latency.get("capacity_wait_ms")
        record["source_fill_wall_ms"] = latency.get("source_fill_wall_ms")
        record["max_concurrent_fills"] = concurrency.get("max_concurrent_fills")
        record["max_source_inflight"] = concurrency.get("max_source_inflight")
    return record


if __name__ == "__main__":
    arm = sys.argv[1]
    out = Path(sys.argv[3]) if len(sys.argv) > 3 else None
    rec = collect(Path(sys.argv[2]))
    rec["arm"] = arm
    text = json.dumps(rec, indent=1)
    if out:
        out.write_text(text, encoding="utf-8")
    print(text)