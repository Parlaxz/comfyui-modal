"""Offline forensic analyzer for the dual-transport Golden sickness corpus.

Reads only pre-existing local artifacts (no network, no Modal, no deploy):

* ``artifacts/golden_p1_parallel_dual_*_evidence_*`` bundles, whose ``raw/``
  directories contain the retained per-run authority:
  ``*_attempt_0.json``, ``*_attempt_0_events.json``, ``*_manifest.json``,
  ``*_summary.json`` and ``*.v2ctl-provenance.json``.
* ``artifacts/dual_transport_carryover_20260916/**/*.decision.json`` decision
  ledgers (membership only; validity is always recomputed from the raw attempt).

The analyzer never trusts report labels (``valid``, ``valid_count``, verdict
strings).  It recomputes attempt/valid counts from the raw attempt plus an
independent validity proof, and records every exclusion / missing artifact
instead of dropping it.

Frozen sickness definitions (matching the retained audit scripts, never
re-derived here)::

    HARD_SICK_CLIP = clip_max_preadv_ms >= 1000 OR clip_load_ms >= 5000
    HARD_SICK_UNET = unet_max_preadv_ms >= 1000 OR unet_load_ms >= 5000
    SECONDARY_BANDS_MS = [500, 250]

Usage::

    python tools/analysis/golden_sickness_forensic.py \
        --corpus-root .slim/worktrees/resource-local-carryover-sep14 \
        --out reports/golden_sickness_forensic_2026-09-17

Bounded local validation (first 3 evidence bundles per arm)::

    python tools/analysis/golden_sickness_forensic.py --limit 3 --dual-limit 5
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import re
import sys
from collections import Counter, OrderedDict
from pathlib import Path

# ---------------------------------------------------------------------------
# Frozen configuration
# ---------------------------------------------------------------------------

DEFAULT_CORPUS_ROOT = Path(".slim/worktrees/resource-local-carryover-sep14")
DEFAULT_OUT_DIR = Path("reports/golden_sickness_forensic_2026-09-17")

EVIDENCE_GLOB = "artifacts/golden_p1_parallel_dual_*"
DUAL_ROOT = "artifacts/dual_transport_carryover_20260916"
PHASE1_ROOT = "artifacts/phase_p1_parallel_golden_v1"

HARD_SICK_MAX_PREADV_MS = 1000.0
HARD_SICK_LOAD_MS = 5000.0
SECONDARY_BANDS_MS = (500.0, 250.0)

EXPECTED_METHOD = "run_golden_parallel_stream"

# Stage names emitted by the Golden runner, in observed order.
STAGE_NAMES = (
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
    "golden_teardown",
)

# Diagnostic leaf keys we surface ("H2D and CPU/fault/context-switch
# diagnostics where present").  H2D fields are extracted by name from
# transport_stats; these patterns catch CPU scheduling / fault counters that
# may sit anywhere in the attempt document.
DIAG_KEY_RE = re.compile(
    r"(fault|context_switch|nvcsw|nivcsw|page_fault|block_input|io_delta"
    r"|active_read_|rss_bytes|max_rss|memlock|cpu_ticks|utime|stime)",
    re.IGNORECASE,
)

# H2D / transport diagnostic scalar fields copied per role.
TRANSPORT_SCALAR_FIELDS = (
    "schema",
    "role",
    "execution_arm",
    "poisoned",
    "poison_reason",
    "source_bytes",
    "source_read_count",
    "source_open_count",
    "header_parse_count",
    "duplicate_read_count",
    "owner_count",
    "adoption_result",
    "fallback_count",
    "fallback_reason",
    "arena_bytes",
    "slot_count",
    "slot_bytes",
    "logical_slot_count",
    "logical_slot_bytes",
    "pinned_arena_physical_allocation_count",
    "pinned_arena_physical_allocation_bytes",
    "created_vs_reused",
    "dedicated_h2d_stream_count",
    "event_object_count",
    "event_rerecord_count",
    "cuda_h2d_stream_object_count",
    "cuda_start_event_object_count",
    "cuda_end_event_object_count",
    "cuda_event_rerecord_count",
    "fresh_cuda_event_per_copy_count",
    "h2d_submit_count",
    "h2d_completion_count",
    "h2d_target_bytes",
    "h2d_min_submission_bytes",
    "h2d_max_submission_bytes",
    "h2d_mean_submission_bytes",
    "h2d_submission_count",
    "aggregated_submission_count",
    "non_aggregated_submission_count",
    "tail_submission_count",
    "aggregation_fallback_count",
    "source_block_count",
    "source_block_bytes",
    "GPU_COPY_ACTIVE_SUM_MS",
    "GPU_COPY_STREAM_SPAN_MS",
    "GPU_COPY_ACTIVE_UNION_MS",
    "GPU_COPY_IDLE_INSIDE_STREAM_SPAN_MS",
    "GPU_COPY_COUNT",
    "GPU_COPY_BYTES",
    "GPU_COPY_ACTIVE_UNION_PROVEN_SINGLE_STREAM_NON_OVERLAP",
    "GPU_COPY_TIMING_AVAILABLE",
    "SOURCE_TOTAL_WALL_MS",
    "SOURCE_SYSCALL_UNION_BUSY_MS",
    "H2D_TOTAL_WALL_MS",
    "SOURCE_TO_GPU_READY_MS",
    "SOURCE_H2D_OVERLAP_MS",
    "POST_SOURCE_H2D_TAIL_MS",
    "E27_SOURCE_MECHANISM_PROVEN",
    "producer_offset_monotonic",
    "producer_destination_offset_monotonic",
    "source_base",
    "destination_base",
    "h2d_event_completion_latency_ms",
)

TRANSPORT_DICT_FIELDS = (
    "coverage",
    "h2d_reconciliation",
    "staging",
    "source_reads",
    "producer_balance",
    "lease_wait",
    "ready_backpressure",
    "free_ready_depth",
    "fallback",
    "throughput",
    "quiescence_evidence",
    "post_transport_construction_adoption",
    "overlap",
)

# Scalar aggregate fields pulled out of the (bulky) ``experiment`` object.
# Raw submission-size lists are collapsed to summary stats to keep the
# canonical JSON small enough to cover the whole corpus.
EXPERIMENT_SCALARS = (
    "timing_scope",
    "total_entry_to_return_wall_ms",
    "source_aggregate_wall_ms",
    "source_wall_ms",
    "source_throughput_bytes_s",
    "source_bytes",
    "source_read_count",
    "h2d_submitted_bytes",
    "h2d_completed_bytes",
    "h2d_submitted_count",
    "h2d_completed_count",
    "h2d_submission_count",
    "h2d_target_bytes",
    "aggregation_enabled",
    "aggregation_wait_count",
)

# Scalar aggregate fields pulled out of the (large) ``actual_source`` object.
ACTUAL_SOURCE_SCALARS = (
    "arm",
    "producer_count",
    "SOURCE_TOTAL_WALL_MS",
    "SOURCE_SYSCALL_UNION_BUSY_MS",
    "source_active_wall_ms",
    "source_active_duration_ns",
    "max_actual_source_inflight",
    "physical_syscall_provenance",
)

PER_READ_COLUMNS = [
    "bundle",
    "arm",
    "request_id",
    "role",
    "read_seq",
    "producer_id",
    "region_id",
    "source_offset",
    "destination_offset",
    "requested_bytes",
    "returned_bytes",
    "retry_number",
    "short_read",
    "error",
    "physical_provenance",
    "slot_index",
    "syscall_enter_monotonic_ns",
    "syscall_exit_monotonic_ns",
    "duration_ms",
    "ge_250_ms",
    "ge_500_ms",
    "ge_1000_ms",
]

ONSET_COLUMNS = [
    "bundle",
    "arm",
    "request_id",
    "role",
    "read_count",
    "load_ms",
    "max_preadv_ms",
    "p50_ms",
    "p90_ms",
    "p95_ms",
    "p99_ms",
    "count_ge_250_ms",
    "count_ge_500_ms",
    "count_ge_1000_ms",
    "first_ge_250_ms",
    "first_ge_500_ms",
    "first_ge_1000_ms",
    "first_ge_250_seq",
    "first_ge_500_seq",
    "first_ge_1000_seq",
    "trigger_class",
]


# ---------------------------------------------------------------------------
# Generic helpers
# ---------------------------------------------------------------------------


def load_json(path: Path):
    with open(path, "r", encoding="utf-8-sig") as handle:
        return json.load(handle)


def finite(value):
    if value is None:
        return None
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(value) or math.isinf(value):
        return None
    return value


def quantile(sorted_values, frac):
    n = len(sorted_values)
    if n == 0:
        return None
    if n == 1:
        return sorted_values[0]
    pos = frac * (n - 1)
    low = int(math.floor(pos))
    high = min(low + 1, n - 1)
    return sorted_values[low] + (sorted_values[high] - sorted_values[low]) * (pos - low)


def bulk_summary(value):
    """Collapse a list of numbers to stats, or return None for non-numeric data."""
    if not isinstance(value, list) or not value:
        return None
    if not all(isinstance(item, (int, float)) and not isinstance(item, bool) for item in value):
        return None
    nums = sorted(float(item) for item in value)
    return {"n": len(nums), "min": nums[0], "max": nums[-1], "mean": sum(nums) / len(nums)}


def summarize(values):
    clean = sorted(v for v in (finite(x) for x in values) if v is not None)
    if not clean:
        return {"n": 0}
    return {
        "n": len(clean),
        "min": clean[0],
        "q1": quantile(clean, 0.25),
        "median": quantile(clean, 0.5),
        "q3": quantile(clean, 0.75),
        "p90": quantile(clean, 0.90),
        "p95": quantile(clean, 0.95),
        "p99": quantile(clean, 0.99),
        "max": clean[-1],
        "mean": sum(clean) / len(clean),
    }


def sha256_file(path: Path, chunk_size: int = 1024 * 1024):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        while True:
            chunk = handle.read(chunk_size)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def stage_wall_ms(stage_doc):
    if not stage_doc:
        return None
    entry = stage_doc.get("entry_monotonic_ns")
    end = stage_doc.get("end_monotonic_ns")
    if entry is None or end is None:
        return None
    return (end - entry) / 1e6


def event_fields(events):
    out = {}
    for event in events or []:
        name = event.get("name")
        if name and name not in out:
            out[name] = event.get("fields") or {}
    return out


def collect_leaf_paths(obj, prefix=""):
    """Return the set of dot-notation leaf paths (lists collapse to ``[]``)."""
    out = set()
    stack = [(obj, prefix)]
    while stack:
        node, path = stack.pop()
        if isinstance(node, dict):
            if not node:
                out.add(path + "{}" if path else "{}")
                continue
            for key, value in node.items():
                child = "%s.%s" % (path, key) if path else str(key)
                stack.append((value, child))
        elif isinstance(node, list):
            out.add(path + "[]" if path else "[]")
            for item in node[:1]:
                stack.append((item, path + "[]" if path else "[]"))
        else:
            out.add(path)
    return out


def collect_diagnostics(obj, prefix="", out=None):
    """Collect scalar diagnostic leaves (fault/context-switch/CPU) by path."""
    if out is None:
        out = {}
    if isinstance(obj, dict):
        for key, value in obj.items():
            child = "%s.%s" % (prefix, key) if prefix else str(key)
            if isinstance(value, (dict, list)):
                collect_diagnostics(value, child, out)
            else:
                leaf = str(key)
                if DIAG_KEY_RE.search(leaf):
                    out[child] = value
    elif isinstance(obj, list):
        # Only probe the first element; diagnostics are homogeneous records.
        for item in obj[:1]:
            collect_diagnostics(item, prefix + "[]", out)
    return out


# ---------------------------------------------------------------------------
# Transport / per-read extraction
# ---------------------------------------------------------------------------


def _first_transport_stats(details):
    if not isinstance(details, dict):
        return None
    stats = details.get("transport_stats")
    if isinstance(stats, list):
        stats = stats[0] if stats else None
    return stats if isinstance(stats, dict) else None


def transport_record(role, stage_doc):
    """Extract one role's transport metrics + per-read rows from a stage."""
    empty = {
        "role": role,
        "present": False,
        "load_ms": stage_wall_ms(stage_doc),
        "reads": [],
        "metrics": {},
        "diagnostics": {},
    }
    if not isinstance(stage_doc, dict):
        return empty
    details = stage_doc.get("details")
    stats = _first_transport_stats(details)
    if stats is None:
        if isinstance(details, dict):
            empty["diagnostics"] = collect_diagnostics(details, "stage_details")
        return empty

    empty["present"] = True
    metrics = {field: stats.get(field) for field in TRANSPORT_SCALAR_FIELDS}
    metrics["load_ms"] = stage_wall_ms(stage_doc)
    for field in TRANSPORT_DICT_FIELDS:
        value = stats.get(field)
        if value not in (None, {}, []):
            metrics[field] = value
    if isinstance(details, dict):
        for field in ("clip_page_faults", "h2d_completed_bytes", "source_read_count",
                      "qd_quiescence", "cuda_allocation_checkpoints",
                      "post_qd_allocation_delta_bytes", "skeleton_peak_delta_bytes",
                      "adoption_peak_delta_bytes", "assigned_count", "same_storage_count",
                      "assign_mode"):
            if field in details:
                metrics["detail_" + field] = details.get(field)

    actual_source = stats.get("actual_source")
    if isinstance(actual_source, dict):
        for field in ACTUAL_SOURCE_SCALARS:
            if actual_source.get(field) is not None:
                metrics["actual_source_" + field] = actual_source.get(field)

    experiment = stats.get("experiment")
    if isinstance(experiment, dict):
        exp = {field: experiment[field] for field in EXPERIMENT_SCALARS if experiment.get(field) is not None}
        for field, value in experiment.items():
            summary = bulk_summary(value)
            if summary is not None:
                exp[field + "_summary"] = summary
        metrics["experiment"] = exp

    # slot_index is carried by the blocks list, keyed by record_id.
    slot_by_record = {}
    for block in stats.get("blocks") or []:
        if isinstance(block, dict):
            record_id = block.get("record_id")
            if record_id is not None:
                slot_by_record[record_id] = block.get("slot_index")

    raw_events = [e for e in (stats.get("actual_source_events") or []) if isinstance(e, dict)]
    indexed = []
    for fallback_index, event in enumerate(raw_events):
        enter = event.get("syscall_enter_monotonic_ns")
        indexed.append((enter if enter is not None else float("inf"), fallback_index, event))
    indexed.sort(key=lambda item: (item[0], item[1]))

    reads = []
    durations = []
    for seq, (_enter, _fallback, event) in enumerate(indexed):
        enter = event.get("syscall_enter_monotonic_ns")
        exit_ = event.get("syscall_exit_monotonic_ns")
        duration = (exit_ - enter) / 1e6 if enter is not None and exit_ is not None else None
        if duration is not None:
            durations.append(duration)
        reads.append(
            {
                "role": role,
                "read_seq": seq,
                "producer_id": event.get("producer_id"),
                "region_id": event.get("region_id"),
                "source_offset": event.get("source_offset"),
                "destination_offset": event.get("destination_offset"),
                "requested_bytes": event.get("requested_bytes"),
                "returned_bytes": event.get("returned_bytes"),
                "retry_number": event.get("retry_number"),
                "short_read": event.get("short_read"),
                "error": event.get("error"),
                "physical_provenance": event.get("physical_provenance"),
                "slot_index": slot_by_record.get(seq),
                "syscall_enter_monotonic_ns": enter,
                "syscall_exit_monotonic_ns": exit_,
                "duration_ms": duration,
            }
        )

    durations_sorted = sorted(durations)
    metrics["read_durations"] = durations_sorted
    metrics["read_count_observed"] = len(reads)
    metrics["max_preadv_ms"] = durations_sorted[-1] if durations_sorted else None
    metrics["p50_preadv_ms"] = quantile(durations_sorted, 0.5)
    metrics["p90_preadv_ms"] = quantile(durations_sorted, 0.90)
    metrics["p95_preadv_ms"] = quantile(durations_sorted, 0.95)
    metrics["p99_preadv_ms"] = quantile(durations_sorted, 0.99)
    metrics["count_ge_250_ms"] = sum(1 for v in durations_sorted if v >= 250.0)
    metrics["count_ge_500_ms"] = sum(1 for v in durations_sorted if v >= 500.0)
    metrics["count_ge_1000_ms"] = sum(1 for v in durations_sorted if v >= 1000.0)
    metrics["count_short_read"] = sum(1 for r in reads if r.get("short_read"))
    metrics["count_retry"] = sum(1 for r in reads if (r.get("retry_number") or 0) > 0)
    metrics["count_error"] = sum(1 for r in reads if r.get("error"))
    producer_ids = sorted({r.get("producer_id") for r in reads if r.get("producer_id") is not None})
    metrics["producer_count"] = len(producer_ids)
    metrics["producer_ids"] = producer_ids
    metrics["destination_offset_min"] = min(
        (r.get("destination_offset") for r in reads if r.get("destination_offset") is not None),
        default=None,
    )
    metrics["destination_offset_max"] = max(
        (r.get("destination_offset") for r in reads if r.get("destination_offset") is not None),
        default=None,
    )
    metrics["diagnostics"] = collect_diagnostics(stats)
    empty["reads"] = reads
    empty["metrics"] = metrics
    return empty


# ---------------------------------------------------------------------------
# Raw bundle parsing
# ---------------------------------------------------------------------------


def classify_raw_files(bundle_dir: Path):
    files = {
        "attempt": None,
        "events": None,
        "manifest": None,
        "summary": None,
        "provenance": None,
    }
    raw_dir = bundle_dir / "raw"
    if not raw_dir.is_dir():
        return files, raw_dir, []
    listing = sorted(p for p in raw_dir.iterdir() if p.is_file())
    for path in listing:
        name = path.name
        if name.endswith(".v2ctl-provenance.json"):
            files["provenance"] = path
        elif name.endswith("_attempt_0_events.json"):
            files["events"] = path
        elif name.endswith("_attempt_0.json"):
            files["attempt"] = path
        elif name.endswith("_manifest.json"):
            files["manifest"] = path
        elif name.endswith("_summary.json"):
            files["summary"] = path
    return files, raw_dir, listing


def arm_from_bundle_name(name):
    if "_dual_sham_" in name:
        return "sham"
    if "_dual_split_" in name:
        return "split"
    return None


def build_raw_index_rows(bundle, arm, listing, index_path, hash_raw):
    """Index every retained file in a bundle, even when the attempt is missing."""
    rows = []
    for path in listing:
        rows.append(
            {
                "bundle": bundle,
                "arm": arm,
                "source_kind": raw_kind(path.name),
                "relative_path": str(path),
                "size_bytes": path.stat().st_size,
                "sha256": sha256_file(path) if hash_raw else None,
            }
        )
    if index_path is not None and index_path.is_file():
        rows.append(
            {
                "bundle": bundle,
                "arm": arm,
                "source_kind": "evidence_index",
                "relative_path": str(index_path),
                "size_bytes": index_path.stat().st_size,
                "sha256": sha256_file(index_path) if hash_raw else None,
            }
        )
    return rows


def recompute_validity(doc, identity_event, top_identity, external_restore, arm):
    """Independent raw-derived validity proof (never trusts the `valid` label)."""
    tel = doc.get("golden_telemetry") or {}
    warning_names = {e.get("name") for e in (tel.get("events") or [])}
    observed_shas = (doc.get("validation") or {}).get("observed_output_shas") or []
    expected_sha = (tel.get("run_identity") or {}).get("expected_output_sha")
    checks = OrderedDict()
    checks["method_run_golden_parallel_stream"] = doc.get("method") == EXPECTED_METHOD
    checks["true_cold"] = bool(doc.get("true_cold"))
    checks["restore_count_eq_1"] = (
        top_identity.get("restore_count") == 1 and external_restore.get("restore_count") == 1
    )
    checks["request_count_eq_1"] = top_identity.get("request_count") == 1
    checks["exact_output_sha"] = bool((doc.get("validation") or {}).get("output_sha_match"))
    checks["no_output_warning"] = "OUTPUT_SHA_MISMATCH_WARNING" not in warning_names
    checks["arm_determined"] = arm in ("sham", "split")
    checks["mode_routing"] = (identity_event or {}).get("mode") == arm
    checks["static_e27"] = (identity_event or {}).get("static_e27") is True
    checks["c0_inactive"] = (identity_event or {}).get("c0_active") is False
    checks["dual_identity_distinct"] = bool(
        (identity_event or {}).get("arena_data_ptrs_distinct")
        and not (identity_event or {}).get("arena_overlap")
        and (identity_event or {}).get("stream_identities_distinct")
        and (identity_event or {}).get("event_identities_distinct")
        and (identity_event or {}).get("pool_identities_distinct")
    )
    checks["vae_route_matches_clip"] = (
        (identity_event or {}).get("vae_resource") == (identity_event or {}).get("clip_resource")
    )
    checks["quiescent_before_unet"] = bool(
        ((identity_event or {}).get("clip_quiescent") or {}).get("quiescent")
    )
    checks["both_live_through_unet"] = (identity_event or {}).get("both_live_through_unet") is True
    if arm == "split":
        checks["split_route_distinct"] = (
            (identity_event or {}).get("clip_resource")
            != (identity_event or {}).get("other_resource")
        )
        checks["other_resource_pristine_before_unet"] = (
            (identity_event or {}).get("other_resource_before_unet_verified") is True
        )
    elif arm == "sham":
        checks["sham_route_same_resource"] = (
            (identity_event or {}).get("clip_resource")
            == (identity_event or {}).get("clip_resource")
        )
    return dict(checks), all(checks.values()), warning_names, observed_shas, expected_sha


def parse_evidence_bundle(
    bundle_dir: Path, corpus_root: Path, hash_raw: bool, parse_events: bool = True
):
    """Parse one evidence bundle into (record, exclusion, raw_rows, exclusions)."""
    bundle = bundle_dir.name
    arm = arm_from_bundle_name(bundle)
    files, raw_dir, listing = classify_raw_files(bundle_dir)
    record = OrderedDict(
        {
            "bundle": bundle,
            "ledger": "evidence",
            "arm": arm,
            "bundle_dir": str(bundle_dir),
            "raw_dir": str(raw_dir),
            "raw_file_count": len(listing),
            "source_files": {kind: (str(path) if path else None) for kind, path in files.items()},
        }
    )
    if files["attempt"] is None:
        index_path = bundle_dir / "evidence_index.json"
        return (
            None,
            {
                "source": "evidence",
                "bundle": bundle,
                "reason": "raw_attempt_missing",
                "detail": "no *_attempt_0.json under %s" % raw_dir,
                "raw_files": [p.name for p in listing],
            },
            build_raw_index_rows(bundle, arm, listing, index_path, hash_raw),
            [],
        )

    bundle_index = None
    index_path = bundle_dir / "evidence_index.json"
    if index_path.is_file():
        try:
            bundle_index = load_json(index_path)
        except (json.JSONDecodeError, OSError) as exc:
            bundle_index = {"_parse_error": str(exc)}
    record["evidence_index"] = {
        "evidence_status": (bundle_index or {}).get("EXPERIMENT_EVIDENCE_STATUS"),
        "verdict": (bundle_index or {}).get("EXPERIMENT_VERDICT"),
        "status": (bundle_index or {}).get("status"),
        "missing_artifacts": (bundle_index or {}).get("missing_artifacts"),
        "cohort_count": len((bundle_index or {}).get("cohorts") or []),
    }

    doc = load_json(files["attempt"])
    tel = doc.get("golden_telemetry") or {}
    identity_event = event_fields(tel.get("events") or []).get("dual_transport_identity") or {}
    top_identity = doc.get("identity") or {}
    external_restore = tel.get("external_restore") or {}

    provenance = {}
    if files["provenance"] is not None:
        try:
            provenance = load_json(files["provenance"])
        except (json.JSONDecodeError, OSError) as exc:
            record["provenance_parse_error"] = str(exc)
    env = provenance.get("effective_environment") or {}

    manifest = {}
    if files["manifest"] is not None:
        try:
            manifest = load_json(files["manifest"])
        except (json.JSONDecodeError, OSError) as exc:
            record["manifest_parse_error"] = str(exc)

    clip = transport_record("clip", next((s for s in (tel.get("stages") or []) if s.get("name") == "golden_clip_load"), {}))
    unet = transport_record("unet", next((s for s in (tel.get("stages") or []) if s.get("name") == "golden_unet_load"), {}))
    vae = transport_record("vae", next((s for s in (tel.get("stages") or []) if s.get("name") == "golden_vae_load"), {}))

    checks, computed_valid, warning_names, observed_shas, expected_sha = recompute_validity(
        doc, identity_event, top_identity, external_restore, arm
    )

    clip_metrics = clip["metrics"]
    unet_metrics = unet["metrics"]

    def trigger_class(metrics):
        preadv_hit = (metrics.get("max_preadv_ms") or -1) >= HARD_SICK_MAX_PREADV_MS
        load_hit = (metrics.get("load_ms") or -1) >= HARD_SICK_LOAD_MS
        if preadv_hit and load_hit:
            return "both"
        if preadv_hit:
            return "preadv_only"
        if load_hit:
            return "load_only"
        return "none"

    clip_trigger = trigger_class(clip_metrics)
    unet_trigger = trigger_class(unet_metrics)
    hard_clip = clip_trigger != "none"
    hard_unet = unet_trigger != "none"
    if hard_clip and hard_unet:
        sickness_class = "BOTH_SICK"
    elif hard_clip:
        sickness_class = "CLIP_SICK_ONLY"
    elif hard_unet:
        sickness_class = "UNET_SICK_ONLY"
    else:
        sickness_class = "NEITHER"

    cloud = top_identity.get("cloud")
    region = top_identity.get("region")
    deploy_fp = provenance.get("deploy_fingerprint") or (
        manifest.get("deployment_identity") or {}
    ).get("deploy_fingerprint")

    events_meta = {}
    if parse_events and files["events"] is not None:
        try:
            raw_events_doc = load_json(files["events"])
            # The retained file is a list-wrapped result envelope: [{type, data}].
            if isinstance(raw_events_doc, list):
                envelopes = [item for item in raw_events_doc if isinstance(item, dict)]
                envelope_count = len(raw_events_doc)
            elif isinstance(raw_events_doc, dict):
                envelopes = [raw_events_doc]
                envelope_count = 1
            else:
                envelopes = []
                envelope_count = 0
            events_meta = {"envelope_count": envelope_count}
            payload = None
            envelope_type = None
            for item in envelopes:
                candidate = item.get("data")
                if isinstance(candidate, dict):
                    payload = candidate
                    envelope_type = item.get("type")
                    break
            if isinstance(payload, dict):
                events_meta.update(
                    {
                        "envelope_type": envelope_type,
                        "request_id": payload.get("request_id"),
                        "image_sha256": payload.get("image_sha256"),
                        "byte_count": payload.get("byte_count"),
                        "width": payload.get("width"),
                        "height": payload.get("height"),
                        "golden_mode": payload.get("golden_mode"),
                        "telemetry_event_count": len(
                            ((payload.get("golden_telemetry") or {}).get("events")) or []
                        ),
                    }
                )
        except (json.JSONDecodeError, OSError) as exc:
            events_meta = {"parse_error": str(exc)}

    stage_info = OrderedDict()
    for stage_doc in tel.get("stages") or []:
        name = stage_doc.get("name")
        stage_info[name] = {
            "wall_ms": stage_wall_ms(stage_doc),
            "ok": stage_doc.get("ok"),
            "entry_wall_ns": stage_doc.get("entry_wall_ns"),
            "end_wall_ns": stage_doc.get("end_wall_ns"),
        }

    record.update(
        {
            "request_id": doc.get("request_id"),
            "method": doc.get("method"),
            "golden_mode": doc.get("golden_mode"),
            "golden_arm": doc.get("golden_arm") or manifest.get("golden_arm"),
            "v2ctl_invocation_id": provenance.get("v2ctl_invocation_id")
            or manifest.get("v2ctl_invocation_id")
            or doc.get("v2ctl_invocation_id"),
            "provider": cloud,
            "region": region,
            "provider_region": "%s/%s" % (cloud, region) if cloud else None,
            "execution_arm": clip_metrics.get("execution_arm"),
            "profile": provenance.get("profile") or manifest.get("profile"),
            "resources": provenance.get("resources") or manifest.get("resources"),
            "raw_valid_label": bool(doc.get("valid")),
            "true_cold": bool(doc.get("true_cold")),
            "dnf": bool(doc.get("dnf")),
            "error": doc.get("error"),
            "request_phase": doc.get("request_phase"),
            "request_pairing": doc.get("request_pairing"),
            "capture_guard": {
                "classification": (doc.get("capture_guard") or {}).get("classification"),
                "valid": (doc.get("capture_guard") or {}).get("valid"),
                "counted": (doc.get("capture_guard") or {}).get("counted"),
                "transition": (doc.get("capture_guard") or {}).get("transition"),
            },
            "deployment": {
                "deploy_fingerprint": deploy_fp,
                "deployment_identity": top_identity.get("deployment_identity"),
                "deployment_combined_hash": top_identity.get("deployment_combined_hash"),
                "snapshot_identity": top_identity.get("snapshot_identity"),
                "snapshot_target_fingerprint": top_identity.get("snapshot_target_fingerprint"),
                "config_identity": top_identity.get("config_identity"),
                "runtime_shape_fingerprint": top_identity.get("runtime_shape_fingerprint"),
                "deployed_at": (manifest.get("deployment_identity") or {}).get("deployed_at"),
            },
            "container": {
                "modal_task_id": top_identity.get("modal_task_id"),
                "modal_container_id": top_identity.get("modal_container_id"),
                "container_id": top_identity.get("container_id"),
                "container_session_id": top_identity.get("container_session_id"),
                "container_task_id": top_identity.get("container_task_id"),
                "restored_instance_id": top_identity.get("restored_instance_id"),
                "restore_session_id": top_identity.get("restore_session_id"),
                "post_restore_nonce": top_identity.get("post_restore_nonce"),
                "boot_id": top_identity.get("boot_id"),
                "pid": top_identity.get("pid"),
                "process_id": top_identity.get("process_id"),
                "modal_input_id": top_identity.get("modal_input_id"),
                "image_id": top_identity.get("image_id"),
            },
            "timestamps": {
                "dispatch_iso": doc.get("dispatch_iso"),
                "dispatch_unix_ms": doc.get("dispatch_unix_ms"),
                "start_ts": doc.get("start_ts"),
                "end_ts": doc.get("end_ts"),
                "duration_ms": doc.get("duration_ms"),
                "gap_before": doc.get("gap_before"),
                "manifest_started_utc": manifest.get("started_utc"),
                "manifest_completed_utc": manifest.get("completed_utc"),
                "manifest_gap_seconds": manifest.get("gap_seconds"),
                "manifest_gaps": manifest.get("gaps"),
                "manifest_gap_validation": manifest.get("gap_validation"),
            },
            "restore": {
                "restore_total_ms": external_restore.get("restore_total_ms"),
                "restore_count": external_restore.get("restore_count"),
                "lifecycle_status": external_restore.get("lifecycle_status"),
                "lifecycle_method": external_restore.get("lifecycle_method"),
                "models_symlink_ms": external_restore.get("models_symlink_ms"),
                "reload_runtime_state_ms": external_restore.get("reload_runtime_state_ms"),
                "backend_startup_ms": external_restore.get("backend_startup_ms"),
                "snapshot_restore_ms": external_restore.get("snapshot_restore_ms"),
                "observe_generations_ms": external_restore.get("observe_generations_ms"),
                "restore_to_parallel_method_entry_ms": top_identity.get(
                    "restore_return_to_parallel_method_entry_ms"
                ),
                "min_containers": top_identity.get("min_containers"),
                "single_use_containers": top_identity.get("single_use_containers"),
                "single_use_enabled": top_identity.get("single_use_enabled"),
                "generation_read_identity": tel.get("source_generation_identity"),
                "cold_basis": (doc.get("cold_evidence") or {}).get("basis"),
                "cold_missing_requirements": (doc.get("cold_evidence") or {}).get("missing_requirements"),
            },
            "correctness": {
                "output_sha_match": (doc.get("validation") or {}).get("output_sha_match"),
                "observed_output_shas": observed_shas,
                "expected_output_sha": expected_sha,
                "observed_output_byte_count": (doc.get("validation") or {}).get("observed_output_byte_count"),
                "output_warning": "OUTPUT_SHA_MISMATCH_WARNING" in warning_names,
                "failures": doc.get("failures"),
                "validity_checks": checks,
                "computed_valid": computed_valid,
            },
            "identity": {
                "mode": identity_event.get("mode"),
                "clip_resource": identity_event.get("clip_resource"),
                "other_resource": identity_event.get("other_resource"),
                "vae_resource": identity_event.get("vae_resource"),
                "unet_resource": identity_event.get("clip_resource")
                if identity_event.get("mode") == "sham"
                else identity_event.get("other_resource"),
                "static_e27": identity_event.get("static_e27"),
                "c0_active": identity_event.get("c0_active"),
                "slot_count": identity_event.get("slot_count"),
                "slot_bytes": identity_event.get("slot_bytes"),
                "arena_bytes_per_resource": identity_event.get("arena_bytes_per_resource"),
                "resource_object_ids": identity_event.get("resource_object_ids"),
                "arena_object_ids": identity_event.get("arena_object_ids"),
                "arena_data_ptrs": identity_event.get("arena_data_ptrs"),
                "arena_ranges": identity_event.get("arena_ranges"),
                "arena_data_ptrs_distinct": identity_event.get("arena_data_ptrs_distinct"),
                "arena_overlap": identity_event.get("arena_overlap"),
                "stream_identities_distinct": identity_event.get("stream_identities_distinct"),
                "event_identities_distinct": identity_event.get("event_identities_distinct"),
                "pool_identities_distinct": identity_event.get("pool_identities_distinct"),
                "both_live_through_unet": identity_event.get("both_live_through_unet"),
                "other_resource_before_unet_verified": identity_event.get(
                    "other_resource_before_unet_verified"
                ),
                "other_resource_source_fills_before_unet": identity_event.get(
                    "other_resource_source_fills_before_unet"
                ),
                "other_resource_h2d_ops_before_unet": identity_event.get(
                    "other_resource_h2d_ops_before_unet"
                ),
                "other_resource_slot_leases_before_unet": identity_event.get(
                    "other_resource_slot_leases_before_unet"
                ),
                "clip_quiescent": identity_event.get("clip_quiescent"),
                "activity": identity_event.get("activity"),
            },
            "stages": stage_info,
            "transport": {"clip": clip, "unet": unet, "vae": vae},
            "thresholds": {
                "HARD_SICK_CLIP": hard_clip,
                "HARD_SICK_UNET": hard_unet,
                "clip_trigger_class": clip_trigger,
                "unet_trigger_class": unet_trigger,
                "onset_pattern": "%s->%s" % (clip_trigger, unet_trigger),
                "sickness_class": sickness_class,
            },
            "onset": {
                "clip": onset_from_reads(clip["reads"]),
                "unet": onset_from_reads(unet["reads"]),
            },
            "clip_forward_total_ms": tel.get("clip_forward_total_ms"),
            "sampler_total_wall_ms": tel.get("sampler_total_wall_ms"),
            "diagnostics": collect_diagnostics(doc),
            "events_meta": events_meta,
        }
    )

    # The stage details also carry non-transport scalar fields worth indexing.
    record["stage_details_keys"] = {
        name: sorted((stage_doc.get("details") or {}).keys())
        for name, stage_doc in (
            (s.get("name"), s) for s in (tel.get("stages") or []) if isinstance(s, dict)
        )
        if name
    }

    raw_index_rows = build_raw_index_rows(bundle, arm, listing, index_path, hash_raw)

    exclusions = []
    if doc.get("valid") and not computed_valid:
        exclusions.append(
            {
                "source": "evidence",
                "bundle": bundle,
                "reason": "raw_valid_label_but_computed_invalid",
                "detail": [k for k, v in checks.items() if not v],
            }
        )
    return record, None, raw_index_rows, exclusions


def raw_kind(name):
    if name.endswith(".v2ctl-provenance.json"):
        return "provenance"
    if name.endswith("_attempt_0_events.json"):
        return "events"
    if name.endswith("_attempt_0.json"):
        return "attempt"
    if name.endswith("_manifest.json"):
        return "manifest"
    if name.endswith("_summary.json"):
        return "summary"
    if name.endswith(".json"):
        return "other_json"
    if name.endswith(".log") or name.endswith(".txt") or name.endswith(".md"):
        return "log_text"
    return "other"


def onset_from_reads(reads):
    ordered = sorted(reads, key=lambda r: r.get("read_seq", 0))
    out = {
        "read_count": len(ordered),
        "first_ge_250_ms": None,
        "first_ge_500_ms": None,
        "first_ge_1000_ms": None,
        "first_ge_250_seq": None,
        "first_ge_500_seq": None,
        "first_ge_1000_seq": None,
    }
    for band in (250.0, 500.0, 1000.0):
        for read in ordered:
            if read.get("duration_ms") is not None and read["duration_ms"] >= band:
                key = "first_ge_%d_ms" % int(band)
                out[key] = read["duration_ms"]
                out[key + "_seq"] = read.get("read_seq")
                break
    return out


# ---------------------------------------------------------------------------
# Decision ledger
# ---------------------------------------------------------------------------


def find_decision_files(corpus_root: Path):
    dual_root = corpus_root / DUAL_ROOT
    if not dual_root.is_dir():
        return []
    return sorted(dual_root.rglob("*.decision.json"))


def resolve_run_artifact(raw_path, corpus_root: Path):
    if not raw_path:
        return None
    candidate = Path(raw_path)
    if candidate.is_file():
        return candidate
    match = re.search(r"[\\/]artifacts[\\/](.*)$", str(raw_path))
    if match:
        relative = match.group(1).replace("\\", "/")
        fallback = corpus_root / "artifacts" / relative
        if fallback.is_file():
            return fallback
    # Last resort: same cohort directory name under the phase-1 root.
    fallback = corpus_root / PHASE1_ROOT / candidate.parent.name / candidate.name
    if fallback.is_file():
        return fallback
    return None


def parse_decision(path: Path, corpus_root: Path, hash_raw: bool):
    ledger_row = OrderedDict(
        {
            "decision_file": str(path),
            "relative_path": str(path.relative_to(corpus_root)).replace("\\", "/"),
        }
    )
    try:
        decision = load_json(path)
    except (json.JSONDecodeError, OSError) as exc:
        ledger_row.update({"parse_error": str(exc)})
        return ledger_row, None, {
            "source": "decision",
            "path": str(path),
            "reason": "decision_parse_error",
            "detail": str(exc),
        }, []

    run_artifact = decision.get("run_artifact")
    resolved = resolve_run_artifact(run_artifact, corpus_root)
    identity = decision.get("identity") or {}
    arm = identity.get("mode")
    ledger_row.update(
        {
            "request_id": decision.get("request_id"),
            "arm": arm,
            "label_valid": bool(decision.get("valid")),
            "label_reasons": decision.get("reasons"),
            "run_artifact": run_artifact,
            "run_artifact_resolved": str(resolved) if resolved else None,
            "run_artifact_exists": bool(resolved),
        }
    )
    exclusions = []
    if resolved is None:
        ledger_row["recomputed_valid"] = None
        ledger_row["label_vs_recomputed"] = "artifact_missing"
        exclusions.append(
            {
                "source": "decision",
                "path": str(path),
                "request_id": decision.get("request_id"),
                "reason": "run_artifact_missing",
                "detail": run_artifact,
            }
        )
        return ledger_row, None, exclusions, None

    # A light recomputation from the raw attempt without full bundle parsing.
    try:
        doc = load_json(resolved)
    except (json.JSONDecodeError, OSError) as exc:
        ledger_row["recomputed_valid"] = None
        ledger_row["label_vs_recomputed"] = "raw_parse_error"
        exclusions.append(
            {
                "source": "decision",
                "path": str(path),
                "request_id": decision.get("request_id"),
                "reason": "raw_parse_error",
                "detail": str(exc),
            }
        )
        return ledger_row, None, exclusions, None

    tel = doc.get("golden_telemetry") or {}
    identity_event = event_fields(tel.get("events") or []).get("dual_transport_identity") or {}
    top_identity = doc.get("identity") or {}
    external_restore = tel.get("external_restore") or {}
    checks, computed_valid, _warnings, _shas, _expected = recompute_validity(
        doc, identity_event, top_identity, external_restore, arm
    )
    ledger_row["raw_valid_label"] = bool(doc.get("valid"))
    ledger_row["recomputed_valid"] = computed_valid
    ledger_row["recomputed_failed_checks"] = [k for k, v in checks.items() if not v]
    ledger_row["label_vs_recomputed"] = (
        "match" if bool(decision.get("valid")) == computed_valid else "MISMATCH"
    )
    if ledger_row["label_vs_recomputed"] == "MISMATCH":
        exclusions.append(
            {
                "source": "decision",
                "path": str(path),
                "request_id": decision.get("request_id"),
                "reason": "label_vs_recomputed_mismatch",
                "detail": {
                    "label": bool(decision.get("valid")),
                    "recomputed": computed_valid,
                    "failed_checks": ledger_row["recomputed_failed_checks"],
                },
            }
        )
    artifact_row = None
    if hash_raw:
        artifact_row = {
            "bundle": "decision:%s" % path.parent.name,
            "arm": arm,
            "source_kind": "decision_referenced_attempt",
            "relative_path": str(resolved),
            "size_bytes": resolved.stat().st_size,
            "sha256": sha256_file(resolved),
        }
    return ledger_row, None, exclusions, artifact_row


# ---------------------------------------------------------------------------
# Writers
# ---------------------------------------------------------------------------


def write_csv(path: Path, rows, columns):
    with open(path, "w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            flat = {}
            for column in columns:
                value = row.get(column)
                if isinstance(value, (dict, list)):
                    value = json.dumps(value, sort_keys=True, default=str)
                flat[column] = value
            writer.writerow(flat)


def write_json(path: Path, payload):
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=False, default=str)
        handle.write("\n")


def flatten_request(record: dict):
    """Flatten a nested per-request record into scalar CSV columns."""
    flat = OrderedDict()
    flat["bundle"] = record.get("bundle")
    flat["ledger"] = record.get("ledger")
    flat["arm"] = record.get("arm")
    flat["golden_arm"] = record.get("golden_arm")
    flat["provider"] = record.get("provider")
    flat["region"] = record.get("region")
    flat["provider_region"] = record.get("provider_region")
    flat["request_id"] = record.get("request_id")
    flat["method"] = record.get("method")
    flat["golden_mode"] = record.get("golden_mode")
    flat["execution_arm"] = record.get("execution_arm")
    flat["v2ctl_invocation_id"] = record.get("v2ctl_invocation_id")
    flat["profile"] = record.get("profile")
    flat["raw_valid_label"] = record.get("raw_valid_label")
    flat["computed_valid"] = (record.get("correctness") or {}).get("computed_valid")
    flat["true_cold"] = record.get("true_cold")
    flat["dnf"] = record.get("dnf")
    flat["request_phase"] = record.get("request_phase")
    flat["error"] = record.get("error")

    deployment = record.get("deployment") or {}
    for key in (
        "deploy_fingerprint",
        "deployment_identity",
        "deployment_combined_hash",
        "snapshot_target_fingerprint",
        "config_identity",
        "runtime_shape_fingerprint",
        "deployed_at",
    ):
        flat["deploy_" + key] = deployment.get(key)
    container = record.get("container") or {}
    for key in (
        "modal_task_id",
        "modal_container_id",
        "container_id",
        "container_session_id",
        "restored_instance_id",
        "restore_session_id",
        "post_restore_nonce",
        "boot_id",
        "pid",
        "process_id",
        "modal_input_id",
        "image_id",
    ):
        flat["container_" + key] = container.get(key)

    timestamps = record.get("timestamps") or {}
    for key in (
        "dispatch_iso",
        "dispatch_unix_ms",
        "start_ts",
        "end_ts",
        "duration_ms",
        "gap_before",
        "manifest_started_utc",
        "manifest_completed_utc",
        "manifest_gap_seconds",
    ):
        flat["ts_" + key] = timestamps.get(key)
    flat["ts_gaps_count"] = len(timestamps.get("manifest_gaps") or [])

    restore = record.get("restore") or {}
    for key in (
        "restore_total_ms",
        "restore_count",
        "lifecycle_status",
        "models_symlink_ms",
        "reload_runtime_state_ms",
        "backend_startup_ms",
        "snapshot_restore_ms",
        "observe_generations_ms",
        "restore_to_parallel_method_entry_ms",
        "min_containers",
        "single_use_containers",
        "single_use_enabled",
        "generation_read_identity",
    ):
        flat["restore_" + key] = restore.get(key)

    correctness = record.get("correctness") or {}
    flat["output_sha_match"] = correctness.get("output_sha_match")
    flat["output_warning"] = correctness.get("output_warning")
    flat["observed_sha_count"] = len(correctness.get("observed_output_shas") or [])
    flat["observed_output_byte_count"] = correctness.get("observed_output_byte_count")

    identity = record.get("identity") or {}
    for key in (
        "clip_resource",
        "other_resource",
        "unet_resource",
        "vae_resource",
        "static_e27",
        "c0_active",
        "arena_data_ptrs_distinct",
        "arena_overlap",
        "stream_identities_distinct",
        "event_identities_distinct",
        "pool_identities_distinct",
        "both_live_through_unet",
        "other_resource_before_unet_verified",
    ):
        flat["route_" + key] = identity.get(key)

    for role in ("clip", "unet"):
        metrics = ((record.get("transport") or {}).get(role) or {}).get("metrics") or {}
        prefix = role + "_"
        for key in (
            "present",
            "load_ms",
            "SOURCE_TOTAL_WALL_MS",
            "SOURCE_SYSCALL_UNION_BUSY_MS",
            "H2D_TOTAL_WALL_MS",
            "SOURCE_TO_GPU_READY_MS",
            "SOURCE_H2D_OVERLAP_MS",
            "POST_SOURCE_H2D_TAIL_MS",
            "read_count_observed",
            "max_preadv_ms",
            "p50_preadv_ms",
            "p90_preadv_ms",
            "p95_preadv_ms",
            "p99_preadv_ms",
            "count_ge_250_ms",
            "count_ge_500_ms",
            "count_ge_1000_ms",
            "source_read_count",
            "source_open_count",
            "source_bytes",
            "source_block_count",
            "h2d_submit_count",
            "h2d_completion_count",
            "h2d_min_submission_bytes",
            "h2d_max_submission_bytes",
            "h2d_mean_submission_bytes",
            "aggregated_submission_count",
            "non_aggregated_submission_count",
            "tail_submission_count",
            "aggregation_fallback_count",
            "GPU_COPY_ACTIVE_SUM_MS",
            "GPU_COPY_STREAM_SPAN_MS",
            "GPU_COPY_ACTIVE_UNION_MS",
            "GPU_COPY_IDLE_INSIDE_STREAM_SPAN_MS",
            "GPU_COPY_COUNT",
            "GPU_COPY_BYTES",
            "slot_count",
            "slot_bytes",
            "arena_bytes",
            "producer_count",
            "created_vs_reused",
            "event_object_count",
            "event_rerecord_count",
            "E27_SOURCE_MECHANISM_PROVEN",
        ):
            flat[prefix + key] = metrics.get(key)
        flat[prefix + "count_short_read"] = metrics.get("count_short_read")
        flat[prefix + "count_retry"] = metrics.get("count_retry")
        flat[prefix + "count_error"] = metrics.get("count_error")
        onset = (record.get("onset") or {}).get(role) or {}
        for key in (
            "first_ge_250_ms",
            "first_ge_500_ms",
            "first_ge_1000_ms",
            "first_ge_250_seq",
            "first_ge_500_seq",
            "first_ge_1000_seq",
        ):
            flat[prefix + key] = onset.get(key)

    flat["clip_forward_ms"] = record.get("clip_forward_total_ms")
    flat["sampler_total_wall_ms"] = record.get("sampler_total_wall_ms")

    thresholds = record.get("thresholds") or {}
    flat["HARD_SICK_CLIP"] = thresholds.get("HARD_SICK_CLIP")
    flat["HARD_SICK_UNET"] = thresholds.get("HARD_SICK_UNET")
    flat["clip_trigger_class"] = thresholds.get("clip_trigger_class")
    flat["unet_trigger_class"] = thresholds.get("unet_trigger_class")
    flat["onset_pattern"] = thresholds.get("onset_pattern")
    flat["sickness_class"] = thresholds.get("sickness_class")

    for stage_name, info in (record.get("stages") or {}).items():
        flat["stage_%s_ms" % stage_name] = info.get("wall_ms")
        flat["stage_%s_ok" % stage_name] = info.get("ok")

    events_meta = record.get("events_meta") or {}
    flat["events_request_id"] = events_meta.get("request_id")
    flat["events_image_sha256"] = events_meta.get("image_sha256")
    flat["events_byte_count"] = events_meta.get("byte_count")
    flat["events_event_count"] = events_meta.get("telemetry_event_count")
    flat["attempt_clip_read_count"] = len(
        ((record.get("transport") or {}).get("clip") or {}).get("reads") or []
    )
    return flat


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------


def aggregate_counts(records):
    counts = OrderedDict()
    counts["total_records"] = len(records)
    for arm in ("sham", "split"):
        subset = [r for r in records if r.get("arm") == arm]
        counts[arm] = {
            "attempts": len(subset),
            "computed_valid": sum(1 for r in subset if (r.get("correctness") or {}).get("computed_valid")),
            "raw_valid_label": sum(1 for r in subset if r.get("raw_valid_label")),
            "hard_sick_clip": sum(1 for r in subset if (r.get("thresholds") or {}).get("HARD_SICK_CLIP")),
            "hard_sick_unet": sum(1 for r in subset if (r.get("thresholds") or {}).get("HARD_SICK_UNET")),
        }
    counts["unclassified_arm"] = sum(1 for r in records if r.get("arm") not in ("sham", "split"))
    return counts


def build_threshold_summary(records):
    groups = OrderedDict()
    groups["overall"] = records
    for arm in ("sham", "split"):
        groups["arm=%s" % arm] = [r for r in records if r.get("arm") == arm]
    for region in sorted({r.get("provider_region") for r in records if r.get("provider_region")}):
        groups["provider_region=%s" % region] = [
            r for r in records if r.get("provider_region") == region
        ]

    summary = OrderedDict()
    for label, subset in groups.items():
        entry = OrderedDict()
        entry["n"] = len(subset)
        entry["computed_valid"] = sum(
            1 for r in subset if (r.get("correctness") or {}).get("computed_valid")
        )
        entry["HARD_SICK_CLIP"] = sum(
            1 for r in subset if (r.get("thresholds") or {}).get("HARD_SICK_CLIP")
        )
        entry["HARD_SICK_UNET"] = sum(
            1 for r in subset if (r.get("thresholds") or {}).get("HARD_SICK_UNET")
        )
        entry["sickness_class_counts"] = dict(
            sorted(Counter((r.get("thresholds") or {}).get("sickness_class") for r in subset).items(), key=lambda kv: str(kv[0]))
        )
        entry["onset_pattern_counts"] = dict(
            sorted(Counter((r.get("thresholds") or {}).get("onset_pattern") for r in subset).items(), key=lambda kv: str(kv[0]))
        )
        entry["clip_trigger_class_counts"] = dict(
            sorted(Counter((r.get("thresholds") or {}).get("clip_trigger_class") for r in subset).items(), key=lambda kv: str(kv[0]))
        )
        entry["unet_trigger_class_counts"] = dict(
            sorted(Counter((r.get("thresholds") or {}).get("unet_trigger_class") for r in subset).items(), key=lambda kv: str(kv[0]))
        )
        for role in ("clip", "unet"):
            metrics = [((r.get("transport") or {}).get(role) or {}).get("metrics") or {} for r in subset]
            entry["%s_max_preadv_ms" % role] = summarize([m.get("max_preadv_ms") for m in metrics])
            entry["%s_load_ms" % role] = summarize([m.get("load_ms") for m in metrics])
            entry["%s_source_wall_ms" % role] = summarize([m.get("SOURCE_TOTAL_WALL_MS") for m in metrics])
            entry["%s_count_ge_250_ms" % role] = summarize([m.get("count_ge_250_ms") for m in metrics])
            entry["%s_count_ge_500_ms" % role] = summarize([m.get("count_ge_500_ms") for m in metrics])
            entry["%s_count_ge_1000_ms" % role] = summarize([m.get("count_ge_1000_ms") for m in metrics])
            entry["%s_ge_500_band_n" % role] = sum(
                1 for m in metrics if (m.get("max_preadv_ms") or -1) >= 500.0
            )
            entry["%s_ge_250_band_n" % role] = sum(
                1 for m in metrics if (m.get("max_preadv_ms") or -1) >= 250.0
            )
        summary[label] = entry
    return summary


def build_provider_region_summary(records):
    summary = OrderedDict()
    regions = sorted({r.get("provider_region") for r in records if r.get("provider_region")})
    if any(r.get("provider_region") is None for r in records):
        regions.append("UNKNOWN")
    for region in regions:
        subset = [
            r
            for r in records
            if (r.get("provider_region") or "UNKNOWN") == region
        ]
        summary[region] = {
            "n": len(subset),
            "provider": subset[0].get("provider") if subset else None,
            "region": subset[0].get("region") if subset else None,
            "arm_counts": dict(sorted(Counter(r.get("arm") for r in subset).items(), key=lambda kv: str(kv[0]))),
            "computed_valid": sum(1 for r in subset if (r.get("correctness") or {}).get("computed_valid")),
            "HARD_SICK_CLIP": sum(1 for r in subset if (r.get("thresholds") or {}).get("HARD_SICK_CLIP")),
            "HARD_SICK_UNET": sum(1 for r in subset if (r.get("thresholds") or {}).get("HARD_SICK_UNET")),
            "clip_max_preadv_ms": summarize(
                [
                    ((r.get("transport") or {}).get("clip") or {}).get("metrics", {}).get("max_preadv_ms")
                    for r in subset
                ]
            ),
            "unet_max_preadv_ms": summarize(
                [
                    ((r.get("transport") or {}).get("unet") or {}).get("metrics", {}).get("max_preadv_ms")
                    for r in subset
                ]
            ),
        }
    return summary


# ---------------------------------------------------------------------------
# Plots
# ---------------------------------------------------------------------------


def write_plots(records, out_dir: Path):
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception as exc:  # pragma: no cover - environment dependent
        return {"available": False, "reason": str(exc), "files": []}

    plots_dir = out_dir / "plots"
    plots_dir.mkdir(parents=True, exist_ok=True)
    files = []

    def series(role, arm):
        return [
            ((r.get("transport") or {}).get(role) or {}).get("metrics", {}).get("max_preadv_ms")
            for r in records
            if r.get("arm") == arm
        ]

    fig, axes = plt.subplots(1, 2, figsize=(11, 4.5), sharey=True)
    for ax, role in zip(axes, ("clip", "unet")):
        values = [v for arm in ("sham", "split") for v in series(role, arm) if v is not None]
        if values:
            bins = min(30, max(5, len(values) // 3))
            ax.hist(values, bins=bins, color="#4c72b0")
            ax.axvline(HARD_SICK_MAX_PREADV_MS, color="#c44e52", linestyle="--", linewidth=1)
        ax.set_title("%s max preadv (ms)" % role)
        ax.set_xlabel("ms")
    axes[0].set_ylabel("requests")
    fig.tight_layout()
    path = plots_dir / "max_preadv_hist.png"
    fig.savefig(path, dpi=110)
    plt.close(fig)
    files.append(str(path))

    fig, ax = plt.subplots(figsize=(5.5, 5))
    colors = {"sham": "#4c72b0", "split": "#dd8452"}
    for arm in ("sham", "split"):
        xs, ys = [], []
        for r in records:
            if r.get("arm") != arm:
                continue
            cm = ((r.get("transport") or {}).get("clip") or {}).get("metrics", {})
            um = ((r.get("transport") or {}).get("unet") or {}).get("metrics", {})
            if cm.get("load_ms") is not None and um.get("load_ms") is not None:
                xs.append(cm["load_ms"])
                ys.append(um["load_ms"])
        if xs:
            ax.scatter(xs, ys, label=arm, alpha=0.6, color=colors[arm], s=14)
    ax.set_xlabel("clip load ms")
    ax.set_ylabel("unet load ms")
    ax.legend(loc="best")
    fig.tight_layout()
    path = plots_dir / "clip_vs_unet_load.png"
    fig.savefig(path, dpi=110)
    plt.close(fig)
    files.append(str(path))

    region_counts = Counter(r.get("provider_region") or "UNKNOWN" for r in records)
    if region_counts:
        labels = sorted(region_counts)
        fig, ax = plt.subplots(figsize=(6, 4))
        ax.bar(range(len(labels)), [region_counts[label] for label in labels], color="#55a868")
        ax.set_xticks(range(len(labels)))
        ax.set_xticklabels(labels, rotation=30, ha="right")
        ax.set_ylabel("requests")
        ax.set_title("requests by provider/region")
        fig.tight_layout()
        path = plots_dir / "provider_region_counts.png"
        fig.savefig(path, dpi=110)
        plt.close(fig)
        files.append(str(path))

    return {"available": True, "files": files}


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus-root", default=str(DEFAULT_CORPUS_ROOT))
    parser.add_argument("--out", default=str(DEFAULT_OUT_DIR))
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="max evidence bundles per arm (deterministic, sorted by name)",
    )
    parser.add_argument(
        "--dual-limit",
        type=int,
        default=None,
        help="max decision files to inspect (deterministic, sorted by path)",
    )
    parser.add_argument(
        "--no-hash",
        action="store_true",
        help="skip sha256 hashing of raw artifacts (paths/sizes still indexed)",
    )
    parser.add_argument("--no-events", action="store_true", help="skip loading events JSON envelopes")
    parser.add_argument("--skip-plots", action="store_true")
    args = parser.parse_args(argv)

    corpus_root = Path(args.corpus_root).resolve()
    out_dir = Path(args.out)
    if not out_dir.is_absolute():
        out_dir = Path(__file__).resolve().parents[2] / out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    hash_raw = not args.no_hash

    if not corpus_root.is_dir():
        print("corpus root not found: %s" % corpus_root, file=sys.stderr)
        return 2

    bundle_dirs = sorted(p for p in corpus_root.glob(EVIDENCE_GLOB) if p.is_dir())
    by_arm = {"sham": [], "split": [], None: []}
    for bundle_dir in bundle_dirs:
        by_arm.setdefault(arm_from_bundle_name(bundle_dir.name), []).append(bundle_dir)

    selected = []
    for arm in ("sham", "split"):
        arm_dirs = by_arm.get(arm, [])
        if args.limit is not None:
            arm_dirs = arm_dirs[: args.limit]
        selected.extend(arm_dirs)
    selected.extend(by_arm.get(None, []))

    records = []
    exclusions = []
    raw_index_rows = []
    parse_failures = []
    field_present = Counter()
    field_present_by_arm = {"sham": Counter(), "split": Counter()}
    for bundle_dir in selected:
        try:
            result = parse_evidence_bundle(
                bundle_dir, corpus_root, hash_raw, parse_events=not args.no_events
            )
        except Exception as exc:  # noqa: BLE001 - forensic tool must not abort
            parse_failures.append({"bundle": bundle_dir.name, "error": repr(exc)})
            exclusions.append(
                {
                    "source": "evidence",
                    "bundle": bundle_dir.name,
                    "reason": "bundle_parse_exception",
                    "detail": repr(exc),
                }
            )
            continue
        record, exclusion, raw_rows, extra_exclusions = result
        raw_index_rows.extend(raw_rows)
        exclusions.extend(extra_exclusions)
        if record is None:
            exclusions.append(exclusion)
            continue
        # Events consistency cross-check.
        attempt_events = len(
            ((record.get("transport") or {}).get("clip", {}) or {}).get("reads") or []
        )
        record["events_meta"]["attempt_clip_read_count"] = attempt_events
        records.append(record)
        paths = collect_leaf_paths(record)
        for path in paths:
            field_present[path] += 1
            if record.get("arm") in field_present_by_arm:
                field_present_by_arm[record["arm"]][path] += 1

    # Decision ledger.
    decisions = find_decision_files(corpus_root)
    if args.dual_limit is not None:
        decisions = decisions[: args.dual_limit]
    ledger_rows = []
    for decision_path in decisions:
        try:
            ledger_row, _companion, extra_exclusions, artifact_row = parse_decision(
                decision_path, corpus_root, hash_raw
            )
        except Exception as exc:  # noqa: BLE001
            exclusions.append(
                {
                    "source": "decision",
                    "path": str(decision_path),
                    "reason": "decision_parse_exception",
                    "detail": repr(exc),
                }
            )
            continue
        ledger_rows.append(ledger_row)
        exclusions.extend(extra_exclusions)
        if artifact_row:
            raw_index_rows.append(artifact_row)

    # Severity (same deterministic composite as the retained audit).
    for record in records:
        clip_metrics = ((record.get("transport") or {}).get("clip") or {}).get("metrics") or {}
        score = 0.0
        used = 0.0
        for metric, weight in (
            ("max_preadv_ms", 1.0),
            ("load_ms", 1.0),
            ("count_ge_1000_ms", 1.0),
            ("SOURCE_TOTAL_WALL_MS", 0.5),
        ):
            value = clip_metrics.get(metric)
            if value is None:
                continue
            score += weight * math.log1p(max(0.0, float(value)))
            used += weight
        record["severity_score"] = (score / used) if used else None
    ordered = sorted(
        records,
        key=lambda r: (r["severity_score"] is None, -(r["severity_score"] or 0)),
    )
    for index, record in enumerate(ordered):
        record["severity_rank"] = index + 1

    # --- outputs ---
    per_request_csv = [flatten_request(record) for record in records]
    # Replace the placeholder attempt_event_count with the real raw value.
    for flat, record in zip(per_request_csv, records):
        flat["clip_read_count"] = len(
            ((record.get("transport") or {}).get("clip") or {}).get("reads") or []
        )
        flat["unet_read_count"] = len(
            ((record.get("transport") or {}).get("unet") or {}).get("reads") or []
        )
        flat["severity_score"] = record.get("severity_score")
        flat["severity_rank"] = record.get("severity_rank")
    per_request_columns = list(
        OrderedDict.fromkeys(
            key for row in per_request_csv for key in row.keys()
        )
    )
    write_csv(out_dir / "per_request.csv", per_request_csv, per_request_columns)
    write_json(out_dir / "per_request.json", records)

    write_csv(
        out_dir / "raw_artifact_index.csv",
        raw_index_rows,
        ["bundle", "arm", "source_kind", "relative_path", "size_bytes", "sha256"],
    )

    per_read_rows = []
    onset_rows = []
    for record in records:
        for role in ("clip", "unet", "vae"):
            role_record = (record.get("transport") or {}).get(role) or {}
            reads = role_record.get("reads") or []
            for read in reads:
                duration = read.get("duration_ms")
                per_read_rows.append(
                    {
                        "bundle": record.get("bundle"),
                        "arm": record.get("arm"),
                        "request_id": record.get("request_id"),
                        "role": role,
                        "read_seq": read.get("read_seq"),
                        "producer_id": read.get("producer_id"),
                        "region_id": read.get("region_id"),
                        "source_offset": read.get("source_offset"),
                        "destination_offset": read.get("destination_offset"),
                        "requested_bytes": read.get("requested_bytes"),
                        "returned_bytes": read.get("returned_bytes"),
                        "retry_number": read.get("retry_number"),
                        "short_read": read.get("short_read"),
                        "error": read.get("error"),
                        "physical_provenance": read.get("physical_provenance"),
                        "slot_index": read.get("slot_index"),
                        "syscall_enter_monotonic_ns": read.get("syscall_enter_monotonic_ns"),
                        "syscall_exit_monotonic_ns": read.get("syscall_exit_monotonic_ns"),
                        "duration_ms": duration,
                        "ge_250_ms": duration is not None and duration >= 250.0,
                        "ge_500_ms": duration is not None and duration >= 500.0,
                        "ge_1000_ms": duration is not None and duration >= 1000.0,
                    }
                )
            metrics = role_record.get("metrics") or {}
            onset = (record.get("onset") or {}).get(role) or {}
            onset_rows.append(
                {
                    "bundle": record.get("bundle"),
                    "arm": record.get("arm"),
                    "request_id": record.get("request_id"),
                    "role": role,
                    "read_count": len(reads),
                    "load_ms": metrics.get("load_ms"),
                    "max_preadv_ms": metrics.get("max_preadv_ms"),
                    "p50_ms": metrics.get("p50_preadv_ms"),
                    "p90_ms": metrics.get("p90_preadv_ms"),
                    "p95_ms": metrics.get("p95_preadv_ms"),
                    "p99_ms": metrics.get("p99_preadv_ms"),
                    "count_ge_250_ms": metrics.get("count_ge_250_ms"),
                    "count_ge_500_ms": metrics.get("count_ge_500_ms"),
                    "count_ge_1000_ms": metrics.get("count_ge_1000_ms"),
                    "first_ge_250_ms": onset.get("first_ge_250_ms"),
                    "first_ge_500_ms": onset.get("first_ge_500_ms"),
                    "first_ge_1000_ms": onset.get("first_ge_1000_ms"),
                    "first_ge_250_seq": onset.get("first_ge_250_seq"),
                    "first_ge_500_seq": onset.get("first_ge_500_seq"),
                    "first_ge_1000_seq": onset.get("first_ge_1000_seq"),
                    "trigger_class": (record.get("thresholds") or {}).get("%s_trigger_class" % role),
                }
            )
    write_csv(out_dir / "per_read.csv", per_read_rows, PER_READ_COLUMNS)
    write_csv(out_dir / "onset.csv", onset_rows, ONSET_COLUMNS)

    write_csv(
        out_dir / "dual_transport_decision_ledger.csv",
        ledger_rows,
        list(
            OrderedDict.fromkeys(key for row in ledger_rows for key in row.keys())
        )
        or ["decision_file", "relative_path"],
    )

    field_rows = []
    total_records = len(records)
    for path in sorted(field_present):
        field_rows.append(
            {
                "field_path": path,
                "present_total": field_present[path],
                "total_records": total_records,
                "present_pct": (field_present[path] / total_records * 100.0) if total_records else 0.0,
                "present_sham": field_present_by_arm["sham"][path],
                "present_split": field_present_by_arm["split"][path],
            }
        )
    write_csv(
        out_dir / "field_availability.csv",
        field_rows,
        ["field_path", "present_total", "total_records", "present_pct", "present_sham", "present_split"],
    )

    threshold_summary = build_threshold_summary(records)
    write_json(out_dir / "threshold_summary.json", threshold_summary)
    threshold_rows = []
    for label, entry in threshold_summary.items():
        flat = {"group": label}
        for key, value in entry.items():
            if isinstance(value, (dict, list)):
                flat[key] = json.dumps(value, sort_keys=True, default=str)
            else:
                flat[key] = value
        threshold_rows.append(flat)
    write_csv(
        out_dir / "threshold_summary.csv",
        threshold_rows,
        list(OrderedDict.fromkeys(key for row in threshold_rows for key in row.keys())),
    )

    provider_region_summary = build_provider_region_summary(records)
    write_json(out_dir / "provider_region_summary.json", provider_region_summary)

    counts = aggregate_counts(records)
    counts["evidence_bundles_enumerated"] = len(bundle_dirs)
    counts["evidence_bundles_selected"] = len(selected)
    counts["decision_files_inspected"] = len(decisions)
    counts["decision_files_parsed"] = len(ledger_rows)
    counts["parse_failures"] = len(parse_failures)
    counts["exclusions"] = len(exclusions)
    counts["raw_artifact_rows"] = len(raw_index_rows)
    counts["per_read_rows"] = len(per_read_rows)
    counts["onset_rows"] = len(onset_rows)
    counts["field_paths"] = len(field_rows)

    exclusions_payload = OrderedDict(
        [
            ("generated_by", "tools/analysis/golden_sickness_forensic.py"),
            ("corpus_root", str(corpus_root)),
            ("existing_ledgers_consumed_verbatim", []),
            ("exclusions", exclusions),
            ("parse_failures", parse_failures),
        ]
    )
    startup_exclusions = corpus_root / DUAL_ROOT / "startup_clip_forensics" / "exclusions.csv"
    if startup_exclusions.is_file():
        exclusions_payload["existing_ledgers_consumed_verbatim"].append(
            {
                "path": str(startup_exclusions),
                "sha256": sha256_file(startup_exclusions) if hash_raw else None,
                "note": "preserved reference only; never treated as authority",
            }
        )
    write_json(out_dir / "exclusions.json", exclusions_payload)

    write_json(out_dir / "counts.json", counts)

    plots = {"available": False, "reason": "skipped by flag", "files": []}
    if not args.skip_plots:
        plots = write_plots(records, out_dir)

    # Output file hashes (excluding this file itself, which is written last).
    output_hashes = OrderedDict()
    for path in sorted(out_dir.glob("*.csv")) + sorted(out_dir.glob("*.json")):
        if path.name == "source_hashes.json":
            continue  # self-reference would make reruns non-deterministic
        output_hashes[path.name] = {
            "size_bytes": path.stat().st_size,
            "sha256": sha256_file(path),
        }
    source_hashes = OrderedDict(
        [
            ("tool", "tools/analysis/golden_sickness_forensic.py"),
            ("tool_sha256", sha256_file(Path(__file__))),
            ("corpus_root", str(corpus_root)),
            ("evidence_bundles_enumerated", len(bundle_dirs)),
            ("evidence_bundles_selected", len(selected)),
            ("limit_per_arm", args.limit),
            ("dual_limit", args.dual_limit),
            ("hashing_enabled", hash_raw),
            ("events_parsed", not args.no_events),
            ("plots", plots),
            ("outputs", output_hashes),
        ]
    )
    write_json(out_dir / "source_hashes.json", source_hashes)

    print(
        json.dumps(
            {
                "out_dir": str(out_dir),
                "counts": counts,
                "plots": plots,
                "exclusions": len(exclusions),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
