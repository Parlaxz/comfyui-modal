"""Bounded offline forensic comparison of H100 and RTX 6000 Pro Golden runs.

Reads only retained local artifacts (no network, no Modal, no deploy, no
request execution, no mutation of files it does not own):

* H100 raw corpus under
  ``<h100-worktree>/artifacts/phase_p1_parallel_golden_v1/cohort_*/
  {attempt_0.json, attempt_0_events.json, manifest.json, summary.json}``.
  All 11 populated cohorts are emitted even though every one is
  exact-output-invalid (observed SHA differs from the expected RTX SHA);
  exclusions are retained, never dropped.  The authoritative endpoint latency
  is the ``FIRST_RESULT_READY`` event in ``golden_telemetry.events`` minus
  ``identity.parallel_method_entry_mono_ns``.
* H100 dossier/provenance under the worktree
  (``H100_GOLDEN_RUNS_EMAIL_2026-09-17.md`` embedded JSON block; the ``*_FULL``
  markdown is read as an index and its hash placeholders are treated as
  unavailable, not invented).
* RTX historical index ``GOLDEN_HISTORICAL_RUNS_MASTER.json`` / ``.csv`` plus
  the raw attempt paths the index names.  The best available exact-commit
  population is used (rows whose ``commit`` matches ``--rtx-commit`` and that
  are ``valid``); invalid rows are retained as exclusions.  Missing transport
  metrics are labelled as unavailable rather than synthesised.  The RTX
  ``FIRST_RESULT_READY`` endpoint is read from the same raw attempt JSON paths
  the index names (``golden_telemetry.events`` and ``identity``), never from the
  index summary, whose ``frr_ms`` is null for every commit row.

Every formula and every median/quantile is recomputed from raw fields.  All
throughput values are **decimal GB/s** (10^9 bytes / second) and are labelled
as such in the JSON and README.

Usage::

    python tools/analysis/h100_vs_rtx_forensics.py
    python tools/analysis/h100_vs_rtx_forensics.py --limit-rtx 3   # bounded

The script writes only the output filenames it owns and never writes or
deletes any other file.  It refreshes an existing report directory in place
(additive re-run); any unowned files beside the owned outputs are reported and
left untouched.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import re
import subprocess
import sys
from collections import Counter, OrderedDict
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Frozen configuration
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parents[2]

DEFAULT_H100_WORKTREE = Path(".slim/worktrees/authoritative-golden-core-sep14")
H100_CORPUS = Path("artifacts/phase_p1_parallel_golden_v1")
H100_DOSSIER_EMAIL = "H100_GOLDEN_RUNS_EMAIL_2026-09-17.md"
H100_DOSSIER_FULL = "H100_GOLDEN_RUNS_FULL_2026-09-17.md"

DEFAULT_RTX_INDEX = Path("GOLDEN_HISTORICAL_RUNS_MASTER.json")
DEFAULT_RTX_CSV = Path("GOLDEN_HISTORICAL_RUNS_MASTER.csv")
DEFAULT_RTX_COMMIT = "03ce24916958596717220167db496b1215544d09"
DEFAULT_OUT = Path("reports/h100_vs_rtx_forensics_2026-09-17")

# Every filename this script may write.  Files outside this set are never
# written or deleted; an existing output directory is refreshed in place and any
# unowned files beside the owned outputs are reported and left untouched.
OUTPUT_FILENAMES = frozenset(
    {
        "h100_per_run_rows.json",
        "h100_per_run_rows.csv",
        "rtx_reference_rows.json",
        "rtx_reference_rows.csv",
        "stage_transport_decomposition.json",
        "stage_transport_decomposition.csv",
        "provider_region_table.json",
        "provider_region_table.csv",
        "sha_analysis.json",
        "source_config_identity_inventory.json",
        "code_diff_inventory.json",
        "h100_read_latency_summary.json",
        "h100_read_latency_summary.csv",
        "h100_read_onset_recovery.json",
        "h100_read_onset_recovery.csv",
        "h100_same_request_contrasts.json",
        "h100_same_request_contrasts.csv",
        "h100_stage_comparison.json",
        "h100_endpoint_timings.json",
        "h100_endpoint_timings.csv",
        "README.md",
    }
)

ROLES = ("clip", "unet", "vae")

# Per-read analysis is restricted to the two source-bound roles; vae reads are
# retained in the transport decomposition but not in the read-level outputs.
READ_ROLES = ("clip", "unet")
READ_THRESHOLDS_MS = (250, 500, 1000)
# Canonical threshold for the onset/recovery classification, matching the
# born-sick/becomes-sick convention in tools/analysis/golden_sickness_derived.py.
CANONICAL_READ_THRESHOLD_MS = 500
# A read at or above this duration is reported as the first pathological read.
PATHOLOGICAL_READ_THRESHOLD_MS = 500
# One CLIP/UNET axis ratio at or above this factor counts as a dramatic reversal.
DRAMATIC_REVERSAL_FACTOR = 2.0

# Authoritative H100 endpoint timing: the FIRST_RESULT_READY event in
# golden_telemetry.events measured against the parallel-method entry boundary
# recorded in identity.parallel_method_entry_mono_ns.  Both are process
# monotonic nanosecond clocks, so the difference is a within-process latency.
ENDPOINT_EVENT_NAME = "FIRST_RESULT_READY"
ENDPOINT_BOUNDARY_FIELD = "parallel_method_entry_mono_ns"

# Transport scalars copied verbatim from each role's transport_stats record.
TRANSPORT_FIELDS = (
    "SOURCE_TOTAL_WALL_MS",
    "SOURCE_SYSCALL_UNION_BUSY_MS",
    "H2D_TOTAL_WALL_MS",
    "SOURCE_TO_GPU_READY_MS",
    "SOURCE_H2D_OVERLAP_MS",
    "POST_SOURCE_H2D_TAIL_MS",
    "GPU_COPY_ACTIVE_UNION_MS",
    "GPU_COPY_ACTIVE_SUM_MS",
    "GPU_COPY_STREAM_SPAN_MS",
    "GPU_COPY_IDLE_INSIDE_STREAM_SPAN_MS",
    "GPU_COPY_TIMING_AVAILABLE",
    "GPU_COPY_COUNT",
    "GPU_COPY_BYTES",
    "source_bytes",
    "source_read_count",
    "source_open_count",
    "source_block_count",
    "h2d_submit_count",
    "h2d_completion_count",
    "h2d_submission_count",
    "aggregated_submission_count",
    "non_aggregated_submission_count",
    "tail_submission_count",
    "arena_bytes",
    "E27_SOURCE_MECHANISM_PROVEN",
    "execution_arm",
)

# Fields that make up the cross-GPU execution match key.
MATCH_IDENTITY_FIELDS = (
    "golden_mode",
    "qd_transport_arm",
    "transport_block_bytes",
    "transport_staging_slots",
    "clip_residency",
    "attention_backend",
    "workflow_sha256",
)

# Stage names emitted by the Golden runner.
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

# Index scalar fields carried for RTX rows (best available metrics).
RTX_INDEX_FIELDS = (
    "run_key",
    "dataset",
    "raw_path",
    "request_id",
    "run_index",
    "v2ctl_invocation_id",
    "mode",
    "method",
    "golden_mode",
    "golden_arm",
    "profile",
    "app",
    "attention_backend_configured",
    "attention_backend_resolved",
    "cpu_qd2_prefetch",
    "deep_trace",
    "dispatch_iso",
    "start_ts",
    "end_ts",
    "duration_ms",
    "valid",
    "true_cold",
    "dnf",
    "error",
    "failures",
    "output_sha_match",
    "expected_output_sha",
    "observed_output_shas",
    "output_sha",
    "output_bytes",
    "frr_ms",
    "sampler_total_wall_ms",
    "clip_forward_total_ms",
    "non_sampling_total_ms",
    "restore_total_ms",
    "restore_count",
    "request_count",
    "snapshot_identity",
    "config_identity",
    "deployment_identity",
    "deployment_fingerprint",
    "run_fingerprint",
    "profile_config_fingerprint",
    "image_id",
    "cloud",
    "region",
    "runtime_shape_fingerprint",
    "cpu_request",
    "memory_request",
    "thread_policy",
    "worktree",
    "branch",
    "commit",
    "experiment_profile",
    "modal_app",
    "storage_path (V1/V2/other)",
    "read_primitive",
    "architecture",
    "queue_depth",
    "read_chunk_bytes",
    "fd_strategy",
    "staging_strategy",
    "clip_load_ms",
    "unet_load_ms",
    "vae_load_ms",
    "total_source_read_wall_ms",
    "overall_request_ms",
    "source_read_count",
    "stage_span_ms",
    "validity_notes",
    "validity/exclusion_reason",
)


# ---------------------------------------------------------------------------
# Generic helpers
# ---------------------------------------------------------------------------


def load_json(path: Path):
    with open(path, "r", encoding="utf-8-sig") as handle:
        return json.load(handle)


def finite(value):
    if value is None or isinstance(value, bool):
        return None
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(value) or math.isinf(value):
        return None
    return value


def r6(value):
    return None if value is None else round(value, 6)


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


def summarize(values):
    """Median/quantiles recomputed from the raw field values (no pre-baked stats)."""
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


def safe_div(numerator, denominator):
    if numerator is None or denominator in (None, 0):
        return None
    return numerator / denominator


def decimal_gbps(nbytes, wall_ms):
    """Decimal GB/s = bytes / 1e9 / (wall_ms / 1e3)."""
    if nbytes is None or wall_ms in (None, 0):
        return None
    return (nbytes / 1e9) / (wall_ms / 1e3)


def stage_wall_ms(stage_doc):
    if not isinstance(stage_doc, dict):
        return None
    entry = stage_doc.get("entry_monotonic_ns")
    end = stage_doc.get("end_monotonic_ns")
    if entry is None or end is None:
        return None
    return (end - entry) / 1e6


def write_json(path: Path, payload):
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=False, default=str)
        handle.write("\n")


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


def sha256_file(path: Path, chunk_size: int = 1024 * 1024):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        while True:
            chunk = handle.read(chunk_size)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def run_git(worktree: Path, args):
    """Read-only git invocation.  Returns (ok, stdout, stderr)."""
    try:
        proc = subprocess.run(
            ["git", "-C", str(worktree), *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=60,
        )
    except (OSError, subprocess.SubprocessError) as exc:  # pragma: no cover
        return False, "", str(exc)
    if proc.returncode != 0:
        return False, proc.stdout, proc.stderr.strip()
    return True, proc.stdout, ""


# ---------------------------------------------------------------------------
# Raw attempt extraction
# ---------------------------------------------------------------------------


def transport_records(stages):
    """Return {role: transport_stats} for every stage-carried transport record."""
    records = {}
    for stage in stages or []:
        if not isinstance(stage, dict):
            continue
        details = stage.get("details")
        if not isinstance(details, dict):
            continue
        stats = details.get("transport_stats")
        if stats is None:
            continue
        items = stats if isinstance(stats, list) else [stats]
        for item in items:
            if not isinstance(item, dict):
                continue
            role = item.get("role")
            if role in ROLES and role not in records:
                records[role] = item
    return records


DERIVED_TRANSPORT_KEYS = (
    "load_ms",
    "source_wall_ms",
    "syscall_union_ms",
    "h2d_span_ms",
    "source_to_gpu_ready_ms",
    "source_h2d_overlap_ms",
    "tail_ms",
    "copy_active_ms",
    "copy_stream_span_ms",
    "copy_idle_ms",
    "source_minus_syscall_ms",
    "load_minus_source_ms",
    "h2d_minus_copy_active_ms",
    "source_minus_h2d_ms",
    "copy_span_minus_active_ms",
    "overlap_frac_of_source",
    "syscall_frac_of_source",
    "h2d_frac_of_source",
    "source_gbps_decimal",
    "h2d_gbps_decimal",
    "copy_active_gbps_decimal",
)


def transport_row(gpu, run_key, role, record, load_ms):
    """Derive one role's stage/transport decomposition row from raw fields."""
    row = OrderedDict()
    row["gpu"] = gpu
    row["run_key"] = run_key
    row["role"] = role
    row["transport_present"] = record is not None
    for field in TRANSPORT_FIELDS:
        row[field] = record.get(field) if record else None
    row["load_ms"] = load_ms
    if not record:
        for key in DERIVED_TRANSPORT_KEYS:
            row[key] = None
        return row

    source_wall = finite(record.get("SOURCE_TOTAL_WALL_MS"))
    syscall_union = finite(record.get("SOURCE_SYSCALL_UNION_BUSY_MS"))
    h2d_span = finite(record.get("H2D_TOTAL_WALL_MS"))
    to_gpu_ready = finite(record.get("SOURCE_TO_GPU_READY_MS"))
    overlap = finite(record.get("SOURCE_H2D_OVERLAP_MS"))
    tail = finite(record.get("POST_SOURCE_H2D_TAIL_MS"))
    copy_active = finite(record.get("GPU_COPY_ACTIVE_UNION_MS"))
    copy_span = finite(record.get("GPU_COPY_STREAM_SPAN_MS"))
    copy_idle = finite(record.get("GPU_COPY_IDLE_INSIDE_STREAM_SPAN_MS"))

    row["source_wall_ms"] = source_wall
    row["syscall_union_ms"] = syscall_union
    row["h2d_span_ms"] = h2d_span
    row["source_to_gpu_ready_ms"] = to_gpu_ready
    row["source_h2d_overlap_ms"] = overlap
    row["tail_ms"] = tail
    row["copy_active_ms"] = copy_active
    row["copy_stream_span_ms"] = copy_span
    row["copy_idle_ms"] = copy_idle

    row["source_minus_syscall_ms"] = (
        r6(source_wall - syscall_union)
        if source_wall is not None and syscall_union is not None
        else None
    )
    row["load_minus_source_ms"] = (
        r6(load_ms - source_wall)
        if load_ms is not None and source_wall is not None
        else None
    )
    row["h2d_minus_copy_active_ms"] = (
        r6(h2d_span - copy_active)
        if h2d_span is not None and copy_active is not None
        else None
    )
    row["source_minus_h2d_ms"] = (
        r6(source_wall - h2d_span)
        if source_wall is not None and h2d_span is not None
        else None
    )
    row["copy_span_minus_active_ms"] = (
        r6(copy_span - copy_active)
        if copy_span is not None and copy_active is not None
        else None
    )
    row["overlap_frac_of_source"] = r6(safe_div(overlap, source_wall))
    row["syscall_frac_of_source"] = r6(safe_div(syscall_union, source_wall))
    row["h2d_frac_of_source"] = r6(safe_div(h2d_span, source_wall))

    source_bytes = finite(record.get("source_bytes"))
    copy_bytes = finite(record.get("GPU_COPY_BYTES"))
    row["source_gbps_decimal"] = r6(decimal_gbps(source_bytes, source_wall))
    row["h2d_gbps_decimal"] = r6(decimal_gbps(copy_bytes, h2d_span))
    row["copy_active_gbps_decimal"] = r6(decimal_gbps(copy_bytes, copy_active))
    return row


def transport_rows_for_attempt(gpu, run_key, attempt):
    """Return {role: transport_row} using each role's enclosing load stage wall."""
    records = transport_records(((attempt.get("golden_telemetry") or {}).get("stages")) or [])
    walls = stage_walls(attempt)
    return {
        role: transport_row(
            gpu, run_key, role, records.get(role), walls.get(f"golden_{role}_load")
        )
        for role in ROLES
    }


def stage_walls(attempt):
    stages = ((attempt.get("golden_telemetry") or {}).get("stages")) or []
    out = OrderedDict()
    for stage in stages:
        name = stage.get("name")
        if name:
            out[name] = stage_wall_ms(stage)
    return out


def run_identity(attempt):
    return ((attempt.get("golden_telemetry") or {}).get("run_identity")) or {}


def match_key(identity):
    return {field: identity.get(field) for field in MATCH_IDENTITY_FIELDS}


def match_key_signature(values):
    """Hashable tuple of the cross-GPU execution match dimensions."""
    return tuple(values.get(field) for field in MATCH_IDENTITY_FIELDS)


def output_stage(attempt):
    for stage in ((attempt.get("golden_telemetry") or {}).get("stages")) or []:
        if stage.get("name") == "golden_output":
            return stage.get("details") or {}
    return {}


# ---------------------------------------------------------------------------
# H100 extraction
# ---------------------------------------------------------------------------


def load_h100_dossier(worktree: Path):
    """Return the embedded dossier JSON block, or an availability record."""
    email_path = worktree / H100_DOSSIER_EMAIL
    full_path = worktree / H100_DOSSIER_FULL
    result = {
        "email_dossier_path": str(email_path.relative_to(REPO_ROOT))
        if email_path.exists()
        else None,
        "full_dossier_path": str(full_path.relative_to(REPO_ROOT))
        if full_path.exists()
        else None,
        "email_dossier_available": False,
        "email_dossier_error": None,
        "runs_by_cohort": {},
    }
    if not email_path.exists():
        result["email_dossier_error"] = "email dossier missing"
        return result
    text = email_path.read_text(encoding="utf-8")
    match = re.search(r"```json\s*(.*?)\s*```", text, re.S)
    if not match:
        result["email_dossier_error"] = "no fenced json block"
        return result
    try:
        payload = json.loads(match.group(1))
    except json.JSONDecodeError as exc:
        result["email_dossier_error"] = f"json decode error: {exc}"
        return result
    result["email_dossier_available"] = True
    result["summary"] = {
        key: payload.get(key)
        for key in (
            "title",
            "generated",
            "app",
            "profile",
            "worktree",
            "run_count",
            "hardware",
            "operator_observation",
            "interpretation",
            "omissions",
        )
    }
    for run in payload.get("runs") or []:
        cohort = run.get("cohort")
        if cohort:
            result["runs_by_cohort"][cohort] = run
    return result


def dossier_artifact_hashes(dossier_run):
    out = {}
    for item in (dossier_run or {}).get("artifact_inventory") or []:
        name = item.get("file")
        if name:
            out[name] = {"sha256": item.get("sha256"), "bytes": item.get("bytes")}
    return out


def compact_dossier_result(result):
    """Project the dossier result, dropping the redundant full telemetry payload."""
    if not isinstance(result, dict):
        return result
    return {k: v for k, v in result.items() if k != "golden_telemetry"}


def build_h100_row(cohort_dir: Path, dossier):
    attempt_path = cohort_dir / "attempt_0.json"
    attempt = load_json(attempt_path)
    manifest = load_json(cohort_dir / "manifest.json")
    summary = load_json(cohort_dir / "summary.json")

    telemetry = attempt.get("golden_telemetry") or {}
    identity = attempt.get("identity") or {}
    validation = attempt.get("validation") or {}
    request_setup = next(
        (s.get("details") or {} for s in (telemetry.get("stages") or [])
         if s.get("name") == "golden_request_setup"),
        {},
    )
    run_id = run_identity(attempt)
    output = output_stage(attempt)
    walls = stage_walls(attempt)
    transport = transport_rows_for_attempt("h100", attempt.get("request_id"), attempt)

    dossier_run = dossier["runs_by_cohort"].get(cohort_dir.name)

    row = OrderedDict()
    row["gpu"] = "h100"
    row["cohort"] = cohort_dir.name
    row["cohort_dir"] = str(
        (cohort_dir.relative_to(REPO_ROOT) if REPO_ROOT in cohort_dir.parents else cohort_dir)
    )
    row["request_id"] = attempt.get("request_id")
    row["run_index"] = attempt.get("run_index")
    row["v2ctl_invocation_id"] = attempt.get("v2ctl_invocation_id")
    row["mode"] = attempt.get("mode")
    row["method"] = attempt.get("method")
    row["golden_mode"] = attempt.get("golden_mode")
    row["golden_arm"] = attempt.get("golden_arm")
    row["cpu_qd2_prefetch"] = attempt.get("cpu_qd2_prefetch")
    row["deep_trace"] = attempt.get("deep_trace")
    row["dispatch_iso"] = attempt.get("dispatch_iso")
    row["start_ts"] = attempt.get("start_ts")
    row["end_ts"] = attempt.get("end_ts")
    row["duration_ms"] = finite(attempt.get("duration_ms"))
    row["event_count"] = attempt.get("event_count")

    row["provider"] = identity.get("cloud")
    row["cloud"] = identity.get("cloud")
    row["region"] = identity.get("region")
    row["device"] = None
    for stage in telemetry.get("stages") or []:
        details = stage.get("details") or {}
        if details.get("device"):
            row["device"] = details.get("device")
            break
    row["image_id"] = identity.get("image_id")
    row["attention_backend"] = identity.get("attention_backend")
    row["attention_backend_configured"] = attempt.get("attention_backend_configured")
    row["attention_backend_resolved"] = attempt.get("attention_backend_resolved")
    row["profile"] = manifest.get("profile")
    row["app"] = (manifest.get("deployment_identity") or {}).get("app_name")

    row["qd_transport_arm"] = run_id.get("qd_transport_arm")
    row["transport_block_bytes"] = run_id.get("transport_block_bytes")
    row["transport_staging_slots"] = run_id.get("transport_staging_slots")
    row["clip_residency"] = run_id.get("clip_residency")
    row["workflow_sha256"] = run_id.get("workflow_sha256")
    row["actual_workflow_sha256"] = request_setup.get("actual_workflow_sha256")
    row["expected_workflow_sha256"] = request_setup.get("expected_workflow_sha256")
    row["workflow_hash_check_bypassed"] = request_setup.get("workflow_hash_check_bypassed")

    row["deployment_identity"] = identity.get("deployment_identity")
    row["deployment_combined_hash"] = identity.get("deployment_combined_hash")
    row["deployment_fingerprint"] = identity.get("deployment_fingerprint")
    row["snapshot_identity"] = identity.get("snapshot_identity")
    row["config_identity"] = identity.get("config_identity")
    row["restore_count"] = identity.get("restore_count")
    row["request_count"] = identity.get("request_count")
    row["min_containers"] = identity.get("min_containers")
    row["single_use_containers"] = identity.get("single_use_containers")
    row["restored_instance_id"] = identity.get("restored_instance_id")
    row["restore_session_id"] = identity.get("restore_session_id")
    row["post_restore_nonce"] = identity.get("post_restore_nonce")
    row["boot_id"] = identity.get("boot_id")
    row["container_session_id"] = identity.get("container_session_id")
    row["container_task_id"] = identity.get("container_task_id")
    row["pid"] = identity.get("pid")
    row["runtime_shape_fingerprint"] = identity.get("runtime_shape_fingerprint")

    row["true_cold"] = attempt.get("true_cold")
    row["valid"] = attempt.get("valid")
    row["dnf"] = attempt.get("dnf")
    row["error"] = attempt.get("error")
    row["failures"] = attempt.get("failures")
    row["included_in_analysis"] = True
    row["exact_output_valid"] = bool(validation.get("output_sha_match"))
    exclusions = []
    if not validation.get("output_sha_match"):
        exclusions.append("output_sha_mismatch")
    for failure in attempt.get("failures") or []:
        exclusions.append(str(failure))
    row["exclusion_reasons"] = exclusions

    row["output_sha_match"] = validation.get("output_sha_match")
    row["observed_output_shas"] = validation.get("observed_output_shas")
    row["observed_output_byte_count"] = validation.get("observed_output_byte_count")
    row["output_stage_sha256"] = output.get("sha256")
    row["output_stage_expected_sha256"] = output.get("expected_sha256")
    row["output_stage_byte_count"] = output.get("byte_count")
    row["manifest_expected_output_sha"] = manifest.get("expected_output_sha")
    row["observed_flags"] = validation.get("observed_flags")

    row["cold_evidence"] = attempt.get("cold_evidence")

    row["clip_forward_total_ms"] = finite(telemetry.get("clip_forward_total_ms"))
    row["restore_total_ms"] = finite(
        ((telemetry.get("external_restore") or {}).get("restore_total_ms"))
    )
    row["sampler_total_wall_ms"] = finite(telemetry.get("sampler_total_wall_ms"))
    row["profile_config_fingerprint"] = manifest.get("profile_config_fingerprint")
    row["provenance_consistent"] = manifest.get("provenance_consistent")
    row["provenance_failures"] = manifest.get("provenance_failures")
    row["gap_seconds"] = manifest.get("gap_seconds")
    row["gap_before"] = attempt.get("gap_before")
    row["manifest_attempt_count"] = manifest.get("attempt_count")
    row["manifest_valid_count"] = manifest.get("valid_count")
    row["manifest_invalid_count"] = manifest.get("invalid_count")
    row["manifest_artifact_file_hashes"] = manifest.get("artifact_file_hashes")
    row["deployment_manifest_identity"] = manifest.get("deployment_identity")
    row["summary_present"] = bool(summary)

    row["stage_walls_ms"] = walls
    row["load_ms"] = {
        role: walls.get(f"golden_{role}_load") for role in ROLES
    }
    row["transport"] = transport

    if dossier_run:
        row["dossier_artifact_inventory"] = dossier_artifact_hashes(dossier_run)
        row["dossier_identity"] = dossier_run.get("identity")
        row["dossier_validation"] = dossier_run.get("validation")
        row["dossier_result"] = compact_dossier_result(dossier_run.get("result"))
    else:
        row["dossier_artifact_inventory"] = {}
        row["dossier_identity"] = None
        row["dossier_validation"] = None
        row["dossier_result"] = None

    input_files = OrderedDict()
    for name in (
        "attempt_0.json",
        "attempt_0_events.json",
        "manifest.json",
        "summary.json",
    ):
        path = cohort_dir / name
        entry: dict = {"present": path.exists()}
        if path.exists():
            entry["bytes"] = path.stat().st_size
        dossier_hash = row["dossier_artifact_inventory"].get(name)
        if dossier_hash:
            entry["sha256"] = dossier_hash.get("sha256")
            entry["dossier_bytes"] = dossier_hash.get("bytes")
        input_files[name] = entry
    row["input_files"] = input_files
    return row


def build_h100_rows(worktree: Path, limit=None):
    corpus = worktree / H100_CORPUS
    dossier = load_h100_dossier(worktree)
    cohort_dirs = sorted(
        p for p in corpus.glob("cohort_*") if p.is_dir() and (p / "attempt_0.json").exists()
    )
    if limit is not None:
        cohort_dirs = cohort_dirs[:limit]
    rows = [build_h100_row(cohort_dir, dossier) for cohort_dir in cohort_dirs]
    excluded_dirs = sorted(
        p.name
        for p in corpus.glob("cohort_*")
        if p.is_dir() and not (p / "attempt_0.json").exists()
    )
    return rows, dossier, excluded_dirs


# ---------------------------------------------------------------------------
# RTX extraction
# ---------------------------------------------------------------------------


def load_rtx_index(index_path: Path, csv_path: Path, commit: str):
    index = load_json(index_path)
    runs = index.get("runs") or []
    selected = [r for r in runs if str(r.get("commit", "")).startswith(commit[:7])]
    valid = [r for r in selected if r.get("valid") is True]
    invalid = [r for r in selected if r.get("valid") is not True]
    csv_cross_check = {
        "csv_path": str(csv_path),
        "csv_available": csv_path.exists(),
        "csv_rows_for_commit": None,
        "note": None,
    }
    if csv_path.exists():
        with open(csv_path, "r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            csv_rows = [
                r for r in reader if str(r.get("commit", "")).startswith(commit[:7])
            ]
        csv_cross_check["csv_rows_for_commit"] = len(csv_rows)
        csv_cross_check["note"] = (
            "csv row count for commit compared to json selection"
        )
    return index.get("metadata") or {}, selected, valid, invalid, csv_cross_check


def build_rtx_row(index_row, attempt_raw):
    row = OrderedDict()
    row["gpu"] = "rtx-pro-6000"
    for field in RTX_INDEX_FIELDS:
        row[field] = index_row.get(field)
    row["gpu_label_source"] = (index_row.get("GPU") or "index:GPU unavailable")

    row["included_in_analysis"] = True
    row["included_in_matched_population"] = True
    row["exclusion_reasons"] = (
        [str(index_row.get("validity/exclusion_reason"))]
        if index_row.get("validity/exclusion_reason")
        else []
    )

    raw_path = REPO_ROOT / str(index_row.get("raw_path") or "")
    row["raw_available"] = raw_path.exists()
    attempt = None
    raw_error = None
    if row["raw_available"]:
        try:
            attempt = load_json(raw_path)
        except (OSError, json.JSONDecodeError) as exc:
            raw_error = str(exc)
    row["raw_error"] = raw_error

    if attempt is None:
        row["transport"] = {
            role: transport_row("rtx-pro-6000", index_row.get("run_key"), role, None, None)
            for role in ROLES
        }
        row["metric_availability"] = {
            "index_stage_metrics": any(
                index_row.get(k) not in (None, "", [])
                for k in ("clip_load_ms", "unet_load_ms", "vae_load_ms")
            ),
            "transport_records_present": False,
            "source_transport_fields_available": False,
            "gpu_copy_fields_available": False,
            "copy_stream_span_available": False,
            "raw_available": row["raw_available"],
            "raw_error": raw_error,
        }
        row["match_key"] = None
        row["matched_to_h100"] = False
        return row

    identity = run_identity(attempt)
    walls = stage_walls(attempt)
    transport = transport_rows_for_attempt(
        "rtx-pro-6000", index_row.get("run_key"), attempt
    )

    row["match_key"] = match_key(identity)
    row["workflow_sha256"] = identity.get("workflow_sha256")
    row["qd_transport_arm"] = identity.get("qd_transport_arm")
    row["transport_block_bytes"] = identity.get("transport_block_bytes")
    row["transport_staging_slots"] = identity.get("transport_staging_slots")
    row["clip_residency"] = identity.get("clip_residency")
    row["attention_backend"] = identity.get("attention_backend")

    row["stage_walls_ms"] = walls
    row["load_ms"] = {role: walls.get(f"golden_{role}_load") for role in ROLES}
    row["transport"] = transport

    row["metric_availability"] = {
        "index_stage_metrics": any(
            index_row.get(k) not in (None, "", [])
            for k in ("clip_load_ms", "unet_load_ms", "vae_load_ms")
        ),
        "transport_records_present": all(
            transport.get(role, {}).get("transport_present") for role in ROLES
        ),
        "source_transport_fields_available": all(
            transport.get(role, {}).get("source_wall_ms") is not None for role in ROLES
        ),
        "gpu_copy_fields_available": all(
            transport.get(role, {}).get("copy_active_ms") is not None for role in ROLES
        ),
        "copy_stream_span_available": all(
            transport.get(role, {}).get("copy_stream_span_ms") is not None
            for role in ROLES
        ),
        "raw_available": True,
        "raw_error": None,
    }
    return row


def build_rtx_rows(valid_rows, limit=None, h100_signatures=None):
    if limit is not None:
        valid_rows = valid_rows[:limit]
    rows = [build_rtx_row(index_row, None) for index_row in valid_rows]
    if h100_signatures:
        for row in rows:
            signature = match_key_signature(row.get("match_key") or {})
            row["matched_to_h100"] = (
                all(v is not None for v in signature) and signature in h100_signatures
            )
    return rows


# ---------------------------------------------------------------------------
# Derived deliverables
# ---------------------------------------------------------------------------


def decomposition_rows(h100_rows, rtx_rows):
    rows = []
    for row in h100_rows:
        for role in ROLES:
            entry = dict(row["transport"].get(role) or {})
            entry.setdefault("gpu", "h100")
            entry.setdefault("run_key", row["request_id"])
            entry["role"] = role
            entry["region"] = row.get("region")
            entry["cloud"] = row.get("cloud")
            entry["exact_output_valid"] = row.get("exact_output_valid")
            rows.append(entry)
    for row in rtx_rows:
        for role in ROLES:
            entry = dict(row["transport"].get(role) or {})
            entry.setdefault("gpu", "rtx-pro-6000")
            entry.setdefault("run_key", row.get("run_key"))
            entry["role"] = role
            entry["region"] = row.get("region")
            entry["cloud"] = row.get("cloud")
            entry["exact_output_valid"] = bool(row.get("output_sha_match"))
            entry["transport_present"] = bool(entry) and any(
                entry.get(field) is not None for field in TRANSPORT_FIELDS
            )
            if not entry.get("transport_present"):
                for field in TRANSPORT_FIELDS:
                    entry.setdefault(field, None)
            rows.append(entry)
    return rows


def decomposition_summary(rows, gpu, role):
    subset = [r for r in rows if r.get("gpu") == gpu and r.get("role") == role]
    metrics = (
        "load_ms",
        "source_wall_ms",
        "syscall_union_ms",
        "source_minus_syscall_ms",
        "h2d_span_ms",
        "copy_active_ms",
        "copy_idle_ms",
        "tail_ms",
        "source_to_gpu_ready_ms",
        "source_h2d_overlap_ms",
        "load_minus_source_ms",
        "h2d_minus_copy_active_ms",
        "source_minus_h2d_ms",
        "source_gbps_decimal",
        "h2d_gbps_decimal",
        "copy_active_gbps_decimal",
    )
    block: dict = {
        "n_rows": len(subset),
        "n_with_transport": sum(1 for r in subset if r.get("transport_present")),
    }
    for metric in metrics:
        block[metric] = summarize(r.get(metric) for r in subset)
    return block


AVAILABILITY_FIELDS = (
    "SOURCE_TOTAL_WALL_MS",
    "SOURCE_SYSCALL_UNION_BUSY_MS",
    "H2D_TOTAL_WALL_MS",
    "SOURCE_TO_GPU_READY_MS",
    "SOURCE_H2D_OVERLAP_MS",
    "POST_SOURCE_H2D_TAIL_MS",
    "GPU_COPY_ACTIVE_UNION_MS",
    "GPU_COPY_STREAM_SPAN_MS",
    "GPU_COPY_IDLE_INSIDE_STREAM_SPAN_MS",
    "GPU_COPY_BYTES",
    "source_bytes",
    "source_read_count",
    "h2d_submit_count",
    "GPU_COPY_COUNT",
)


def build_decomposition_availability(dec_rows):
    availability = OrderedDict()
    for gpu in ("h100", "rtx-pro-6000"):
        availability[gpu] = OrderedDict()
        for role in ROLES:
            subset = [
                r for r in dec_rows if r.get("gpu") == gpu and r.get("role") == role
            ]
            availability[gpu][role] = {
                "n_rows": len(subset),
                "n_with_transport": sum(
                    1 for r in subset if r.get("transport_present")
                ),
                "fields": {
                    field: {
                        "present": sum(1 for r in subset if r.get(field) is not None),
                        "total": len(subset),
                    }
                    for field in AVAILABILITY_FIELDS
                },
            }
    return availability


def build_provider_region_table(h100_rows, rtx_rows):
    def aggregate(rows, gpu):
        groups = OrderedDict()
        for row in rows:
            key = (gpu, row.get("cloud"), row.get("region"))
            groups.setdefault(key, []).append(row)
        out = []
        for (g, cloud, region), group in groups.items():
            out.append(
                OrderedDict(
                    [
                        ("gpu", g),
                        ("cloud", cloud),
                        ("region", region),
                        ("n_runs", len(group)),
                        ("n_distinct_requests", len({r.get("request_id") or r.get("run_key") for r in group})),
                        ("duration_ms", summarize(r.get("duration_ms") for r in group)),
                        ("sampler_total_wall_ms", summarize(r.get("sampler_total_wall_ms") for r in group)),
                        ("clip_forward_total_ms", summarize(r.get("clip_forward_total_ms") for r in group)),
                        ("restore_total_ms", summarize(r.get("restore_total_ms") for r in group)),
                        ("clip_source_wall_ms", summarize(
                            (r.get("transport") or {}).get("clip", {}).get("source_wall_ms")
                            for r in group
                        )),
                        ("unet_source_wall_ms", summarize(
                            (r.get("transport") or {}).get("unet", {}).get("source_wall_ms")
                            for r in group
                        )),
                    ]
                )
            )
        return out

    return {
        "h100": aggregate(h100_rows, "h100"),
        "rtx": aggregate(rtx_rows, "rtx-pro-6000"),
    }


def sha_match_counts(rows):
    """Count exact-match truth values without collapsing unknown into false."""
    n_true = sum(1 for r in rows if r.get("output_sha_match") is True)
    n_false = sum(1 for r in rows if r.get("output_sha_match") is False)
    n_unknown = sum(1 for r in rows if r.get("output_sha_match") is None)
    return {
        "match_true": n_true,
        "match_false": n_false,
        "match_unknown": n_unknown,
        "all_match_true": n_false == 0 and n_unknown == 0,
    }


def build_sha_analysis(h100_rows, rtx_rows):
    h100_observed = Counter()
    h100_manifest_expected = Counter()
    h100_stage_expected = Counter()
    for row in h100_rows:
        for sha in row.get("observed_output_shas") or []:
            h100_observed[sha] += 1
        h100_manifest_expected[str(row.get("manifest_expected_output_sha"))] += 1
        h100_stage_expected[str(row.get("output_stage_expected_sha256"))] += 1

    rtx_observed = Counter()
    rtx_expected = Counter()
    for row in rtx_rows:
        observed = row.get("observed_output_shas")
        if isinstance(observed, str):
            observed = [observed]
        for sha in observed or []:
            rtx_observed[sha] += 1
        rtx_expected[str(row.get("expected_output_sha"))] += 1

    h100_obs_set = set(h100_observed)
    rtx_obs_set = set(rtx_observed)
    return {
        "units_note": "Hashes are SHA-256 hex digests of the encoded output image bytes.",
        "h100": {
            "rows": len(h100_rows),
            "observed_sha256_counts": dict(h100_observed),
            "manifest_expected_sha256_counts": dict(h100_manifest_expected),
            "output_stage_expected_sha256_counts": dict(h100_stage_expected),
            "distinct_observed_count": len(h100_obs_set),
            "output_sha_match_counts": sha_match_counts(h100_rows),
            "note": (
                "H100 manifest-level expected SHA and the in-run golden_output "
                "expected SHA disagree; both are recorded rather than reconciled."
                if len(h100_manifest_expected) > 1 or h100_manifest_expected != h100_stage_expected
                else "H100 expected SHA fields agree."
            ),
        },
        "rtx": {
            "rows": len(rtx_rows),
            "observed_sha256_counts": dict(rtx_observed),
            "expected_sha256_counts": dict(rtx_expected),
            "distinct_observed_count": len(rtx_obs_set),
            "output_sha_match_counts": sha_match_counts(rtx_rows),
        },
        "cross_gpu": {
            "observed_sha_overlap": sorted(h100_obs_set & rtx_obs_set),
            "h100_observed_subset_of_rtx_observed": h100_obs_set <= rtx_obs_set,
            "rtx_reference_expected_sha": sorted(rtx_expected.keys()),
        },
    }


def build_identity_inventory(h100_rows, rtx_rows, dossier, worktree, commit):
    def distinct(rows, field):
        return sorted(
            {str(r.get(field)) for r in rows if r.get(field) not in (None, "", [])}
        )

    h100 = {
        "rows": len(h100_rows),
        "distinct_deployment_identity": distinct(h100_rows, "deployment_identity"),
        "distinct_deployment_combined_hash": distinct(h100_rows, "deployment_combined_hash"),
        "distinct_snapshot_identity": distinct(h100_rows, "snapshot_identity"),
        "distinct_config_identity": distinct(h100_rows, "config_identity"),
        "distinct_image_id": distinct(h100_rows, "image_id"),
        "distinct_workflow_sha256": distinct(h100_rows, "workflow_sha256"),
        "distinct_profile_config_fingerprint": distinct(
            h100_rows, "profile_config_fingerprint"
        ),
        "attempt_vs_manifest_deployment_identity": [
            {
                "cohort": r.get("cohort"),
                "attempt_deployment_identity": r.get("deployment_identity"),
                "manifest_deployment_combined_hash": (
                    (r.get("deployment_manifest_identity") or {}).get(
                        "deployment_combined_hash"
                    )
                ),
                "equal": r.get("deployment_identity")
                == (r.get("deployment_manifest_identity") or {}).get(
                    "deployment_combined_hash"
                ),
            }
            for r in h100_rows
        ],
        "attempt_vs_manifest_note": (
            "The attempt-level frozen deployment identity and the manifest "
            "deployment_combined_hash are reported verbatim; they are not assumed "
            "to share a hash domain. Disagreement here is recorded, not resolved."
        ),
        "runtime_shape_fingerprints": distinct(h100_rows, "runtime_shape_fingerprint"),
        "dossier": {
            "email_dossier_path": dossier.get("email_dossier_path"),
            "full_dossier_path": dossier.get("full_dossier_path"),
            "email_dossier_available": dossier.get("email_dossier_available"),
            "email_dossier_error": dossier.get("email_dossier_error"),
            "summary": dossier.get("summary"),
        },
    }

    def rtx_distinct(field):
        return sorted(
            {str(r.get(field)) for r in rtx_rows if r.get(field) not in (None, "", [])}
        )

    rtx = {
        "rows": len(rtx_rows),
        "distinct_snapshot_identity": rtx_distinct("snapshot_identity"),
        "distinct_config_identity": rtx_distinct("config_identity"),
        "distinct_deployment_fingerprint": rtx_distinct("deployment_fingerprint"),
        "distinct_run_fingerprint": rtx_distinct("run_fingerprint"),
        "distinct_profile_config_fingerprint": rtx_distinct("profile_config_fingerprint"),
        "distinct_image_id": rtx_distinct("image_id"),
        "distinct_commit": rtx_distinct("commit"),
        "distinct_worktree": rtx_distinct("worktree"),
        "distinct_profile": rtx_distinct("profile"),
    }

    # Source-context (custom node) identity, when retained.
    context_manifest = worktree / ".last_custom_node_context_manifest.json"
    source_context = {"path": str(context_manifest.relative_to(REPO_ROOT)), "available": False}
    if context_manifest.exists():
        try:
            ctx = load_json(context_manifest)
            source_context = {
                "path": str(context_manifest.relative_to(REPO_ROOT)),
                "available": True,
                "context_hash": ctx.get("context_hash"),
                "file_count": ctx.get("file_count"),
                "total_bytes": ctx.get("total_bytes"),
                "node_dirs": ctx.get("node_dirs"),
                "top_20_largest": ctx.get("top_20_largest"),
                "file_hashes": ctx.get("file_hashes"),
            }
        except (OSError, json.JSONDecodeError) as exc:
            source_context = {
                "path": str(context_manifest.relative_to(REPO_ROOT)),
                "available": False,
                "error": str(exc),
            }

    return {
        "h100": h100,
        "rtx": rtx,
        "rtx_preferred_commit": commit,
        "source_context_manifest": source_context,
    }


def build_code_diff_inventory(worktree, rtx_commit):
    ok_head, head_out, head_err = run_git(worktree, ["rev-parse", "HEAD"])
    head = head_out.strip().splitlines()[0] if ok_head and head_out.strip() else None

    ok_log, log_out, log_err = run_git(
        worktree, ["log", "--oneline", f"{rtx_commit}..HEAD"]
    )
    commits = []
    if ok_log:
        for line in log_out.splitlines():
            parts = line.split(" ", 1)
            if len(parts) == 2:
                commits.append({"sha": parts[0], "subject": parts[1]})

    ok_numstat, numstat_out, numstat_err = run_git(
        worktree, ["diff", "--numstat", rtx_commit, "HEAD"]
    )
    files = []
    if ok_numstat:
        for line in numstat_out.splitlines():
            parts = line.split("\t")
            if len(parts) >= 3:
                files.append(
                    {
                        "insertions": None if parts[0] == "-" else int(parts[0]),
                        "deletions": None if parts[1] == "-" else int(parts[1]),
                        "path": parts[2],
                    }
                )

    reliable = bool(
        ok_head and ok_log and ok_numstat and head and not head_err and not log_err
    )
    return {
        "reliable": reliable,
        "h100_worktree": str(worktree),
        "h100_worktree_head": head,
        "rtx_reference_commit": rtx_commit,
        "commits_between": commits,
        "diff_files": files if reliable else [],
        "errors": {
            "rev_parse": head_err or None,
            "log": log_err or None,
            "numstat": numstat_err or None,
        },
        "note": (
            "Code-diff inventory computed read-only via git show/diff/numstat; "
            "no runtime files were changed."
        ),
    }


# ---------------------------------------------------------------------------
# Raw per-read analysis (H100 actual_source_events)
# ---------------------------------------------------------------------------
#
# Each H100 attempt carries, inside every load stage's
# ``details.transport_stats``, the raw source-read events under
# ``actual_source_events``.  ``transport_stats`` itself is a list for CLIP and a
# dict for UNET in this corpus, so ``transport_records`` above normalises both
# shapes before the reads are extracted.  Read ordering, duration, and the
# born-sick/becomes-sick/recovery semantics mirror the canonical implementation
# in ``tools/analysis/golden_sickness_forensic.py`` and
# ``tools/analysis/golden_sickness_derived.py`` so the two reports agree.


def normalize_source_events(events):
    """Order raw actual_source_events and derive each read's duration.

    Reads are stably ordered by ``syscall_enter_monotonic_ns``; events with a
    missing enter timestamp sort last, exactly as in the canonical forensic
    implementation, so ``read_seq`` is reproducible.
    """
    raw = [event for event in (events or []) if isinstance(event, dict)]
    indexed = []
    for fallback, event in enumerate(raw):
        enter = event.get("syscall_enter_monotonic_ns")
        indexed.append((enter if enter is not None else float("inf"), fallback, event))
    indexed.sort(key=lambda item: (item[0], item[1]))

    reads = []
    for seq, (_enter, _fallback, event) in enumerate(indexed):
        enter = event.get("syscall_enter_monotonic_ns")
        exit_ = event.get("syscall_exit_monotonic_ns")
        duration = (exit_ - enter) / 1e6 if enter is not None and exit_ is not None else None
        reads.append(
            OrderedDict(
                [
                    ("read_seq", seq),
                    ("producer_id", event.get("producer_id")),
                    ("region_id", event.get("region_id")),
                    ("source_offset", event.get("source_offset")),
                    ("destination_offset", event.get("destination_offset")),
                    ("requested_bytes", event.get("requested_bytes")),
                    ("returned_bytes", event.get("returned_bytes")),
                    ("retry_number", event.get("retry_number")),
                    ("short_read", event.get("short_read")),
                    ("error", event.get("error")),
                    ("physical_provenance", event.get("physical_provenance")),
                    ("syscall_enter_monotonic_ns", enter),
                    ("syscall_exit_monotonic_ns", exit_),
                    ("duration_ms", duration),
                ]
            )
        )
    return reads


def attempt_path_for_row(row):
    cohort_dir = Path(str(row.get("cohort_dir") or ""))
    if not cohort_dir.is_absolute():
        cohort_dir = REPO_ROOT / cohort_dir
    return cohort_dir / "attempt_0.json"


def load_attempt_reads(row):
    """Return {role: [normalized reads]} for clip/unet from the raw attempt."""
    try:
        attempt = load_json(attempt_path_for_row(row))
    except (OSError, json.JSONDecodeError):
        return {role: [] for role in READ_ROLES}
    records = transport_records(
        ((attempt.get("golden_telemetry") or {}).get("stages")) or []
    )
    return {
        role: normalize_source_events(
            (records.get(role) or {}).get("actual_source_events")
        )
        for role in READ_ROLES
    }


def first_pathological_read(reads, threshold=PATHOLOGICAL_READ_THRESHOLD_MS):
    """First read (by read_seq) whose duration is at or above ``threshold``."""
    for read in reads:
        duration = finite(read.get("duration_ms"))
        if duration is not None and duration >= threshold:
            return OrderedDict(
                [
                    ("read_seq", read.get("read_seq")),
                    ("duration_ms", r6(duration)),
                    ("threshold_ms", threshold),
                    ("producer_id", read.get("producer_id")),
                    ("region_id", read.get("region_id")),
                    ("source_offset", read.get("source_offset")),
                    ("returned_bytes", read.get("returned_bytes")),
                    ("retry_number", read.get("retry_number")),
                    ("error", read.get("error")),
                ]
            )
    return None


def read_latency_block(reads):
    """Latency quantiles, threshold counts, and first pathological read."""
    durations = sorted(
        d for d in (finite(r.get("duration_ms")) for r in reads) if d is not None
    )
    block = OrderedDict()
    block["read_count"] = len(reads)
    block["duration_null_count"] = len(reads) - len(durations)
    block["p50_ms"] = r6(quantile(durations, 0.50)) if durations else None
    block["p90_ms"] = r6(quantile(durations, 0.90)) if durations else None
    block["p95_ms"] = r6(quantile(durations, 0.95)) if durations else None
    block["p99_ms"] = r6(quantile(durations, 0.99)) if durations else None
    block["max_ms"] = r6(durations[-1]) if durations else None
    block["count_ge_250_ms"] = sum(1 for d in durations if d >= 250.0)
    block["count_ge_500_ms"] = sum(1 for d in durations if d >= 500.0)
    block["count_ge_1000_ms"] = sum(1 for d in durations if d >= 1000.0)
    first = first_pathological_read(reads)
    block["first_pathological_read"] = first
    block["first_pathological_ms"] = first["duration_ms"] if first else None
    block["first_pathological_seq"] = first["read_seq"] if first else None
    block["first_pathological_threshold_ms"] = PATHOLOGICAL_READ_THRESHOLD_MS
    return block


def threshold_episodes(flags):
    """Return (episode_count, longest_run) for the boolean >=threshold sequence."""
    episodes = 0
    longest = 0
    current = 0
    for flag in flags:
        if flag:
            current += 1
            longest = max(longest, current)
        elif current:
            episodes += 1
            current = 0
    if current:
        episodes += 1
    return episodes, longest


def read_threshold_stats(reads, threshold):
    """Counts/onset/episode stats for one read sequence at one threshold."""
    durations = [finite(r.get("duration_ms")) for r in reads]
    flags = [d is not None and d >= threshold for d in durations]
    n = len(reads)
    crossings = [i for i, flag in enumerate(flags) if flag]
    toggles = sum(1 for i in range(1, n) if flags[i] != flags[i - 1])
    episodes, longest = threshold_episodes(flags)
    first_seq = crossings[0] if crossings else None
    last_seq = crossings[-1] if crossings else None
    return OrderedDict(
        [
            ("count_ge", len(crossings)),
            ("first_seq_ge", first_seq),
            ("last_seq_ge", last_seq),
            ("first_ms_ge", durations[first_seq] if first_seq is not None else None),
            ("last_ms_ge", durations[last_seq] if last_seq is not None else None),
            ("toggles", toggles),
            ("episodes", episodes),
            ("longest_episode", longest),
            ("final_read_sick", flags[-1] if flags else None),
            ("fraction_ge", r6(safe_div(len(crossings), n))),
            ("recovered_before_final", bool(last_seq is not None and n > 0 and last_seq < n - 1)),
        ]
    )


def read_recovery_class(stats, read_count):
    """Recovery structure of the >=threshold sequence.

    Semantics copied from tools/analysis/golden_sickness_derived.py
    ``recovery_class``: none / persistent_ends_sick / contiguous_then_clear /
    single_episode / alternating.
    """
    if not stats.get("count_ge"):
        return "none"
    if stats.get("toggles") == 0:
        last_seq = stats.get("last_seq_ge")
        if last_seq is not None and read_count and last_seq >= read_count - 1:
            return "persistent_ends_sick"
        return "contiguous_then_clear"
    if stats.get("toggles") == 2:
        return "single_episode"
    return "alternating"


def build_read_latency_summary(h100_rows) -> tuple[dict, list]:
    """Per-role and per-request read-latency summary for H100 clip/unet."""
    pooled = {role: [] for role in READ_ROLES}
    pooled_source = {role: {"bytes": 0.0, "wall_ms": 0.0, "gbps": []} for role in READ_ROLES}
    per_request = []
    csv_rows = []

    for row in h100_rows:
        reads_by_role = load_attempt_reads(row)
        roles_block = OrderedDict()
        for role in READ_ROLES:
            reads = reads_by_role[role]
            pooled[role].extend(reads)
            transport = (row.get("transport") or {}).get(role) or {}
            block = read_latency_block(reads)
            block["source_bytes"] = finite(transport.get("source_bytes"))
            block["source_wall_ms"] = finite(transport.get("source_wall_ms"))
            block["source_gbps_decimal"] = finite(transport.get("source_gbps_decimal"))
            roles_block[role] = block
            if block["source_bytes"] is not None:
                pooled_source[role]["bytes"] += block["source_bytes"]
            if block["source_wall_ms"] is not None:
                pooled_source[role]["wall_ms"] += block["source_wall_ms"]
            if block["source_gbps_decimal"] is not None:
                pooled_source[role]["gbps"].append(block["source_gbps_decimal"])
            csv_rows.append(
                flatten_row(
                    OrderedDict(
                        [
                            ("scope", "request"),
                            ("request_id", row.get("request_id")),
                            ("cohort", row.get("cohort")),
                            ("role", role),
                            ("read_count", block["read_count"]),
                            ("p50_ms", block["p50_ms"]),
                            ("p90_ms", block["p90_ms"]),
                            ("p95_ms", block["p95_ms"]),
                            ("p99_ms", block["p99_ms"]),
                            ("max_ms", block["max_ms"]),
                            ("count_ge_250_ms", block["count_ge_250_ms"]),
                            ("count_ge_500_ms", block["count_ge_500_ms"]),
                            ("count_ge_1000_ms", block["count_ge_1000_ms"]),
                            ("first_pathological_ms", block["first_pathological_ms"]),
                            ("first_pathological_seq", block["first_pathological_seq"]),
                            ("first_pathological_threshold_ms", PATHOLOGICAL_READ_THRESHOLD_MS),
                            ("source_bytes", block["source_bytes"]),
                            ("source_wall_ms", block["source_wall_ms"]),
                            ("source_gbps_decimal", block["source_gbps_decimal"]),
                        ]
                    ),
                    READ_LATENCY_CSV_COLUMNS,
                )
            )
        per_request.append(
            OrderedDict(
                [
                    ("request_id", row.get("request_id")),
                    ("cohort", row.get("cohort")),
                    ("roles", roles_block),
                ]
            )
        )

    per_role = OrderedDict()
    for role in READ_ROLES:
        block = read_latency_block(pooled[role])
        if block["first_pathological_read"] is not None:
            # Pooled reads are concatenated in request order, so the first
            # request whose role block has a pathological read owns it.
            for entry in per_request:
                if entry["roles"][role]["first_pathological_read"] is not None:
                    block["first_pathological_request_id"] = entry["request_id"]
                    break
        gbps_values = sorted(pooled_source[role]["gbps"])
        block["source_bytes_total"] = r6(pooled_source[role]["bytes"])
        block["source_wall_ms_total"] = r6(pooled_source[role]["wall_ms"])
        block["source_gbps_decimal_pooled"] = r6(
            decimal_gbps(pooled_source[role]["bytes"], pooled_source[role]["wall_ms"])
        )
        block["source_gbps_decimal_median"] = (
            r6(quantile(gbps_values, 0.5)) if gbps_values else None
        )
        per_role[role] = block
        csv_rows.insert(
            0 if role == READ_ROLES[0] else 1,
            flatten_row(
                OrderedDict(
                    [
                        ("scope", "role"),
                        ("request_id", None),
                        ("cohort", None),
                        ("role", role),
                        ("read_count", block["read_count"]),
                        ("p50_ms", block["p50_ms"]),
                        ("p90_ms", block["p90_ms"]),
                        ("p95_ms", block["p95_ms"]),
                        ("p99_ms", block["p99_ms"]),
                        ("max_ms", block["max_ms"]),
                        ("count_ge_250_ms", block["count_ge_250_ms"]),
                        ("count_ge_500_ms", block["count_ge_500_ms"]),
                        ("count_ge_1000_ms", block["count_ge_1000_ms"]),
                        ("first_pathological_ms", block["first_pathological_ms"]),
                        ("first_pathological_seq", block["first_pathological_seq"]),
                        ("first_pathological_threshold_ms", PATHOLOGICAL_READ_THRESHOLD_MS),
                        ("source_bytes", block["source_bytes_total"]),
                        ("source_wall_ms", block["source_wall_ms_total"]),
                        ("source_gbps_decimal", block["source_gbps_decimal_pooled"]),
                    ]
                ),
                READ_LATENCY_CSV_COLUMNS,
            ),
        )

    payload = OrderedDict(
        [
            ("generated_by", "tools/analysis/h100_vs_rtx_forensics.py"),
            ("units", "milliseconds; gbps fields are decimal GB/s (10^9 bytes/s)"),
            ("source_evidence", {
                "field": "golden_telemetry.stages[*].details.transport_stats.actual_source_events",
                "roles": list(READ_ROLES),
                "per_read_duration_ms": "(syscall_exit_monotonic_ns - syscall_enter_monotonic_ns) / 1e6",
            }),
            ("definitions", [
                "read_count = number of actual_source_events for the role (all transports).",
                "p50/p90/p95/p99/max = recomputed from per-read duration_ms (linear interpolation).",
                "count_ge_<T>_ms = reads with duration_ms >= T.",
                f"first_pathological_read = first read_seq with duration_ms >= {PATHOLOGICAL_READ_THRESHOLD_MS} ms.",
                "source throughput = SOURCE bytes / SOURCE wall from the role's transport record (decimal GB/s).",
                "role-scope source_gbps_decimal_pooled = total source_bytes / total source_wall_ms; median is over per-request values.",
            ]),
            ("pathological_threshold_ms", PATHOLOGICAL_READ_THRESHOLD_MS),
            ("read_thresholds_ms", list(READ_THRESHOLDS_MS)),
            ("read_role_totals", {
                role: {
                    "read_count": per_role[role]["read_count"],
                    "count_ge_250_ms": per_role[role]["count_ge_250_ms"],
                    "count_ge_500_ms": per_role[role]["count_ge_500_ms"],
                    "count_ge_1000_ms": per_role[role]["count_ge_1000_ms"],
                }
                for role in READ_ROLES
            }),
            ("per_role", per_role),
            ("per_request", per_request),
        ]
    )
    return payload, csv_rows


def build_read_onset_recovery(h100_rows) -> tuple[dict, list]:
    """Born-sick vs becomes-sick, episode clustering, and recovery per request."""
    per_role_agg = {
        role: {
            "requests_with_reads": 0,
            "onset_class_counts": Counter(),
            "recovery_class_counts": Counter(),
            "episode_request_counts": Counter(),
            "transient_recovery_requests": 0,
            "final_read_sick_requests": 0,
        }
        for role in READ_ROLES
    }
    per_request = []
    csv_rows = []

    for row in h100_rows:
        reads_by_role = load_attempt_reads(row)
        roles_block = OrderedDict()
        for role in READ_ROLES:
            reads = reads_by_role[role]
            n = len(reads)
            durations = [finite(r.get("duration_ms")) for r in reads]
            thresholds = OrderedDict(
                (str(threshold), read_threshold_stats(reads, threshold))
                for threshold in READ_THRESHOLDS_MS
            )
            canonical = thresholds[str(CANONICAL_READ_THRESHOLD_MS)]
            if canonical["first_seq_ge"] is None:
                onset_class = "never_sick"
            elif canonical["first_seq_ge"] <= 1:
                onset_class = "born_sick"
            else:
                onset_class = "becomes_sick"
            recovery_class_value = read_recovery_class(canonical, n)
            block = OrderedDict(
                [
                    ("read_count", n),
                    ("max_ms", r6(max((d for d in durations if d is not None), default=None))
                     if any(d is not None for d in durations) else None),
                    ("thresholds", thresholds),
                    ("onset_class_500", onset_class),
                    ("recovery_class_500", recovery_class_value),
                    ("transient_recovery_500", recovery_class_value in ("contiguous_then_clear", "single_episode")),
                    ("final_read_sick_500", canonical["final_read_sick"]),
                    ("final_read_ms", r6(durations[-1]) if durations else None),
                ]
            )
            roles_block[role] = block

            agg = per_role_agg[role]
            agg["requests_with_reads"] += 1
            agg["onset_class_counts"][onset_class] += 1
            agg["recovery_class_counts"][recovery_class_value] += 1
            agg["episode_request_counts"][canonical["episodes"]] += 1
            if block["transient_recovery_500"]:
                agg["transient_recovery_requests"] += 1
            if block["final_read_sick_500"]:
                agg["final_read_sick_requests"] += 1

            csv_rows.append(
                flatten_row(
                    OrderedDict(
                        [
                            ("request_id", row.get("request_id")),
                            ("cohort", row.get("cohort")),
                            ("role", role),
                            ("read_count", n),
                            ("max_ms", block["max_ms"]),
                            ("onset_class_500", onset_class),
                            ("recovery_class_500", recovery_class_value),
                            ("transient_recovery_500", block["transient_recovery_500"]),
                            ("final_read_sick_500", block["final_read_sick_500"]),
                            ("final_read_ms", block["final_read_ms"]),
                            ("count_ge_250_ms", thresholds["250"]["count_ge"]),
                            ("count_ge_500_ms", thresholds["500"]["count_ge"]),
                            ("count_ge_1000_ms", thresholds["1000"]["count_ge"]),
                            ("first_seq_ge_250", thresholds["250"]["first_seq_ge"]),
                            ("first_seq_ge_500", thresholds["500"]["first_seq_ge"]),
                            ("first_seq_ge_1000", thresholds["1000"]["first_seq_ge"]),
                            ("last_seq_ge_500", thresholds["500"]["last_seq_ge"]),
                            ("toggles_ge_500", thresholds["500"]["toggles"]),
                            ("episodes_ge_250", thresholds["250"]["episodes"]),
                            ("episodes_ge_500", thresholds["500"]["episodes"]),
                            ("episodes_ge_1000", thresholds["1000"]["episodes"]),
                            ("longest_episode_ge_500", thresholds["500"]["longest_episode"]),
                            ("recovered_before_final_500", thresholds["500"]["recovered_before_final"]),
                        ]
                    ),
                    READ_ONSET_CSV_COLUMNS,
                )
            )
        per_request.append(
            OrderedDict(
                [
                    ("request_id", row.get("request_id")),
                    ("cohort", row.get("cohort")),
                    ("roles", roles_block),
                ]
            )
        )

    per_role = OrderedDict()
    for role in READ_ROLES:
        agg = per_role_agg[role]
        per_role[role] = OrderedDict(
            [
                ("requests_with_reads", agg["requests_with_reads"]),
                ("onset_class_counts", dict(agg["onset_class_counts"])),
                ("recovery_class_counts", dict(agg["recovery_class_counts"])),
                ("episode_request_counts", dict(sorted(agg["episode_request_counts"].items()))),
                ("transient_recovery_requests", agg["transient_recovery_requests"]),
                ("final_read_sick_requests", agg["final_read_sick_requests"]),
            ]
        )

    payload = OrderedDict(
        [
            ("generated_by", "tools/analysis/h100_vs_rtx_forensics.py"),
            ("units", "milliseconds"),
            ("source_evidence", {
                "field": "golden_telemetry.stages[*].details.transport_stats.actual_source_events",
                "roles": list(READ_ROLES),
            }),
            ("canonical_threshold_ms", CANONICAL_READ_THRESHOLD_MS),
            ("read_thresholds_ms", list(READ_THRESHOLDS_MS)),
            ("definitions", {
                "born_sick": "first read_seq with duration >= T is <= 1",
                "becomes_sick": "first read_seq with duration >= T is > 1",
                "never_sick": "no read reaches threshold T",
                "episodes": "number of contiguous runs of reads with duration >= T",
                "longest_episode": "longest such contiguous run",
                "persistent_ends_sick": "single contiguous >=T block reaching the final read",
                "contiguous_then_clear": "single contiguous >=T block clearing before the final read",
                "single_episode": "exactly one isolated off->on->off crossing",
                "alternating": "4+ transitions across the threshold",
                "transient_recovery_500": "sick at 500 ms but the block clears before the final read",
                "final_read_sick_500": "last read's duration >= 500 ms",
            }),
            ("per_role", per_role),
            ("per_request", per_request),
        ]
    )
    return payload, csv_rows


# ---------------------------------------------------------------------------
# Authoritative endpoint timing (FIRST_RESULT_READY), H100 and RTX
# ---------------------------------------------------------------------------
#
# The endpoint boundary is fixed by two retained fields on each raw attempt
# JSON:
#   * the first ``FIRST_RESULT_READY`` event in ``golden_telemetry.events``
#     (``monotonic_ns``), and
#   * the ``identity.parallel_method_entry_mono_ns`` monotonic clock captured at
#     parallel-method entry.
# Both GPUs record the identical field names, so one extractor serves both.
# H100 attempts are read from each cohort's ``attempt_0.json``; RTX attempts are
# read from the ``raw_path`` referenced by GOLDEN_HISTORICAL_RUNS_MASTER (the
# ``.slim/worktrees/.../cohort_*/attempt_0.json`` files).  The RTX *index* omits
# the timing (``frr_ms`` is null for every commit row), but the referenced raw
# attempt retains the event and boundary, so the endpoint is derived from raw
# evidence instead of the index summary.  A value is null only when its raw
# attempt, event, or boundary is genuinely missing, and then a per-row
# diagnostic records which one.

ENDPOINT_STAT_KEYS = (
    "n",
    "min",
    "q1",
    "median",
    "q3",
    "p90",
    "p95",
    "p99",
    "max",
    "mean",
)

# Raw evidence source and formula, reused verbatim in the JSON and README.
ENDPOINT_RAW_EVIDENCE = OrderedDict(
    [
        (
            "event",
            "golden_telemetry.events[*] where name == " + ENDPOINT_EVENT_NAME,
        ),
        ("boundary", "identity." + ENDPOINT_BOUNDARY_FIELD),
        (
            "formula",
            "endpoint_ms = (" + ENDPOINT_EVENT_NAME + ".monotonic_ns - "
            "identity." + ENDPOINT_BOUNDARY_FIELD + ") / 1e6",
        ),
        (
            "h100_raw_paths",
            "<h100-worktree>/artifacts/phase_p1_parallel_golden_v1/"
            "cohort_*/attempt_0.json",
        ),
        (
            "rtx_raw_paths",
            "raw_path referenced by GOLDEN_HISTORICAL_RUNS_MASTER.json/.csv "
            "for the selected commit (e.g. "
            ".slim/worktrees/golden-io-v2/artifacts/"
            "phase_p1_parallel_golden_v1/cohort_*/attempt_0.json)",
        ),
    ]
)

# Applies only to rows whose raw attempt/event/boundary is genuinely missing.
ENDPOINT_MISSING_ROW_NOTE = (
    "Only rows whose raw attempt JSON, FIRST_RESULT_READY event, or "
    "identity.parallel_method_entry_mono_ns boundary is genuinely missing are "
    "reported null, each with a per-row diagnostic. The RTX historical index "
    "omitting the timing (its frr_ms is null for every commit row) is not a "
    "reason to null a value: the referenced raw attempt retains the event and "
    "boundary. No endpoint value is estimated or borrowed from the other GPU."
)


def endpoint_timing_from_attempt(
    attempt,
    *,
    gpu,
    run_key,
    request_id,
    cohort,
    commit,
    raw_path,
    valid,
    load_error=None,
):
    """Return one request's authoritative FIRST_RESULT_READY latency.

    ``endpoint_ms = (FIRST_RESULT_READY.monotonic_ns
                     - identity.parallel_method_entry_mono_ns) / 1e6``

    Both operands are process-monotonic nanosecond timestamps, so the result is
    a within-process latency.  A missing raw attempt, event, or boundary is
    reported as null with a per-row diagnostic; nothing is estimated.
    """
    entry = OrderedDict()
    entry["gpu"] = gpu
    entry["run_key"] = run_key
    entry["request_id"] = request_id
    entry["cohort"] = cohort
    entry["commit"] = commit
    entry["raw_path"] = raw_path
    entry["valid"] = valid
    entry["endpoint_event_name"] = ENDPOINT_EVENT_NAME
    entry["boundary_identity_field"] = f"identity.{ENDPOINT_BOUNDARY_FIELD}"
    entry["attempt_event_count"] = attempt.get("event_count") if attempt else None
    entry["event_present"] = False
    entry["event_count"] = 0
    entry["first_result_ready_monotonic_ns"] = None
    entry["first_result_ready_wall_ns"] = None
    entry["parallel_method_entry_mono_ns"] = None
    entry["endpoint_ms"] = None
    entry["diagnostic"] = None

    if load_error is not None:
        entry["diagnostic"] = f"attempt load failed: {load_error}"
        return entry

    identity = attempt.get("identity") or {}
    entry["parallel_method_entry_mono_ns"] = identity.get(ENDPOINT_BOUNDARY_FIELD)

    events = ((attempt.get("golden_telemetry") or {}).get("events")) or []
    matches = [
        event
        for event in events
        if isinstance(event, dict) and event.get("name") == ENDPOINT_EVENT_NAME
    ]
    entry["event_count"] = len(matches)
    if not matches:
        entry["diagnostic"] = f"{ENDPOINT_EVENT_NAME} event absent"
    else:
        entry["event_present"] = True
        first = matches[0]
        entry["first_result_ready_monotonic_ns"] = first.get("monotonic_ns")
        entry["first_result_ready_wall_ns"] = first.get("wall_ns")
        if len(matches) > 1:
            entry["diagnostic"] = (
                f"{len(matches)} {ENDPOINT_EVENT_NAME} events; first used"
            )

    event_ns = finite(entry["first_result_ready_monotonic_ns"])
    entry_ns = finite(entry["parallel_method_entry_mono_ns"])
    if event_ns is not None and entry_ns is not None:
        entry["endpoint_ms"] = r6((event_ns - entry_ns) / 1e6)
    elif entry["diagnostic"] is None:
        entry["diagnostic"] = "endpoint boundary timestamp absent"
    return entry


def display_path(path: Path) -> str:
    """Repo-relative POSIX path for portable, comparable evidence labels."""
    try:
        return path.relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def attempt_endpoint_timing(row):
    """H100 endpoint entry read from the cohort's raw ``attempt_0.json``."""
    path = attempt_path_for_row(row)
    identifiers = {
        "gpu": "h100",
        "run_key": None,
        "request_id": row.get("request_id"),
        "cohort": row.get("cohort"),
        "commit": None,
        "raw_path": display_path(path),
        "valid": row.get("valid"),
    }
    try:
        attempt = load_json(path)
    except (OSError, json.JSONDecodeError) as exc:
        return endpoint_timing_from_attempt(
            None, load_error=str(exc), **identifiers
        )
    return endpoint_timing_from_attempt(attempt, **identifiers)


def rtx_attempt_endpoint_timing(row):
    """RTX endpoint entry read from the raw attempt ``raw_path`` in the index.

    The endpoint is derived from the referenced raw attempt, not from the index
    summary (whose ``frr_ms`` is null for every commit row).  A missing
    ``raw_path`` or an unloadable file yields a null entry with a diagnostic.
    """
    raw_rel = str(row.get("raw_path") or "")
    identifiers = {
        "gpu": "rtx-pro-6000",
        "run_key": row.get("run_key"),
        "request_id": row.get("request_id"),
        "cohort": row.get("cohort"),
        "commit": row.get("commit"),
        "raw_path": raw_rel or None,
        "valid": row.get("valid"),
    }
    if not raw_rel:
        return endpoint_timing_from_attempt(
            None, load_error="raw_path absent from index", **identifiers
        )
    raw_path = REPO_ROOT / raw_rel
    if not raw_path.exists():
        return endpoint_timing_from_attempt(
            None, load_error=f"raw attempt absent: {raw_rel}", **identifiers
        )
    try:
        attempt = load_json(raw_path)
    except (OSError, json.JSONDecodeError) as exc:
        return endpoint_timing_from_attempt(
            None, load_error=str(exc), **identifiers
        )
    return endpoint_timing_from_attempt(attempt, **identifiers)


def endpoint_stats_block(entries, population_label):
    """Recomputed endpoint quantiles plus population and missing-row labels."""
    summary = summarize(entry.get("endpoint_ms") for entry in entries)
    block: dict = OrderedDict()
    for key in ENDPOINT_STAT_KEYS:
        block[key] = summary.get(key)
    missing = [entry for entry in entries if entry.get("endpoint_ms") is None]
    block["population"] = population_label
    block["rows_in_population"] = len(entries)
    block["rows_with_endpoint"] = len(entries) - len(missing)
    block["rows_missing_endpoint"] = len(missing)
    block["missing_rows"] = [
        OrderedDict(
            [
                ("gpu", entry.get("gpu")),
                ("run_key", entry.get("run_key")),
                ("request_id", entry.get("request_id")),
                ("cohort", entry.get("cohort")),
                ("raw_path", entry.get("raw_path")),
                ("diagnostic", entry.get("diagnostic")),
            ]
        )
        for entry in missing
    ]
    return block


def build_endpoint_timings(
    h100_rows, rtx_rows, *, rtx_commit=None, rtx_population=None
) -> dict:
    """Separate H100 and RTX endpoint row sections plus recomputed stats.

    Each row is derived from its raw attempt JSON (H100 ``attempt_0.json``;
    RTX the ``raw_path`` referenced by GOLDEN_HISTORICAL_RUNS_MASTER).  Only
    genuinely missing rows are null, each carrying a diagnostic.
    """
    rtx_population = rtx_population or {}
    h100_entries = [attempt_endpoint_timing(row) for row in h100_rows]
    rtx_entries = [rtx_attempt_endpoint_timing(row) for row in rtx_rows]

    h100_stats = endpoint_stats_block(
        h100_entries,
        "H100 populated cohorts (all retained; exact-output-invalid included)",
    )
    rtx_stats = endpoint_stats_block(
        rtx_entries,
        "RTX valid rows for commit "
        f"{rtx_commit} ({rtx_population.get('valid_rows')} valid of "
        f"{rtx_population.get('json_rows_for_commit')} selected; "
        f"{rtx_population.get('invalid_rows_retained')} invalid retained as "
        "exclusions)",
    )
    rtx_stats["commit"] = rtx_commit
    rtx_stats["population_counts"] = rtx_population

    return OrderedDict(
        [
            ("generated_by", "tools/analysis/h100_vs_rtx_forensics.py"),
            ("units", "milliseconds"),
            (
                "authoritative_endpoint",
                "FIRST_RESULT_READY minus identity.parallel_method_entry_mono_ns "
                "(H100 and RTX raw attempts)",
            ),
            ("source_evidence", ENDPOINT_RAW_EVIDENCE),
            (
                "definitions",
                [
                    f"{ENDPOINT_EVENT_NAME} = the first event in "
                    "golden_telemetry.events whose name field equals "
                    "FIRST_RESULT_READY; it marks the first result ready. When "
                    "several are present the first is used.",
                    f"identity.{ENDPOINT_BOUNDARY_FIELD} = the process monotonic "
                    "clock (ns) captured at parallel-method entry; the endpoint "
                    "boundary for the request.",
                    "endpoint_ms = (FIRST_RESULT_READY.monotonic_ns - "
                    "identity.parallel_method_entry_mono_ns) / 1e6. Both operands "
                    "share the same process monotonic clock, so this is a "
                    "within-process latency.",
                    "min/q1/median/q3/p90/p95/p99/max = recomputed per GPU from "
                    "that GPU's per-row endpoint_ms values with linear "
                    "interpolation.",
                    "H100: all 11 populated cohorts contribute one row each; none "
                    "is dropped.",
                    "RTX: one row per valid row for the selected commit. The "
                    "endpoint is read from the raw attempt JSON referenced by the "
                    "index `raw_path`, not from the index summary: the index "
                    "`frr_ms` is null for every commit row, but the referenced "
                    "attempt retains FIRST_RESULT_READY and the parallel-method "
                    "entry boundary.",
                    ENDPOINT_MISSING_ROW_NOTE,
                ],
            ),
            ("h100_endpoint_stats", h100_stats),
            ("h100_rows", h100_entries),
            ("rtx_endpoint_stats", rtx_stats),
            ("rtx_rows", rtx_entries),
        ]
    )


def read_ratio(numerator, denominator):
    if numerator is None or denominator in (None, 0):
        return None
    return numerator / denominator


def ratio_magnitude(ratio):
    """Symmetric fold of a ratio: max(r, 1/r); None when undefined or non-positive."""
    if ratio is None or ratio <= 0:
        return None
    return max(ratio, 1.0 / ratio)


def faster_role(higher_value_is_faster, clip_value, unet_value):
    """Which role wins an axis; None when incomparable."""
    if clip_value is None or unet_value is None:
        return None
    if clip_value == unet_value:
        return "tie"
    if higher_value_is_faster:
        return "clip" if clip_value > unet_value else "unet"
    return "clip" if clip_value < unet_value else "unet"


def contrast_entry(row):
    """CLIP vs UNET source/active-H2D/load contrast for one request."""
    clip = (row.get("transport") or {}).get("clip") or {}
    unet = (row.get("transport") or {}).get("unet") or {}
    clip_source = finite(clip.get("source_gbps_decimal"))
    unet_source = finite(unet.get("source_gbps_decimal"))
    clip_active = finite(clip.get("copy_active_gbps_decimal"))
    unet_active = finite(unet.get("copy_active_gbps_decimal"))
    clip_h2d = finite(clip.get("h2d_gbps_decimal"))
    unet_h2d = finite(unet.get("h2d_gbps_decimal"))
    clip_load = finite(clip.get("load_ms"))
    unet_load = finite(unet.get("load_ms"))

    source_ratio = read_ratio(clip_source, unet_source)
    active_ratio = read_ratio(clip_active, unet_active)
    load_ratio = read_ratio(clip_load, unet_load)

    source_faster = faster_role(True, clip_source, unet_source)
    active_faster = faster_role(True, clip_active, unet_active)
    load_faster = faster_role(False, clip_load, unet_load)

    axes = OrderedDict(
        [
            ("source", (source_ratio, source_faster)),
            ("active_h2d", (active_ratio, active_faster)),
            ("load", (load_ratio, load_faster)),
        ]
    )
    magnitudes = {
        name: ratio_magnitude(ratio) for name, (ratio, _role) in axes.items()
    }
    dramatic_dimensions = [
        name for name, magnitude in magnitudes.items()
        if magnitude is not None and magnitude >= DRAMATIC_REVERSAL_FACTOR
    ]
    reversal_dimensions = []
    axis_names = list(axes)
    for i in range(len(axis_names)):
        for j in range(i + 1, len(axis_names)):
            first, second = axis_names[i], axis_names[j]
            role_a, role_b = axes[first][1], axes[second][1]
            if role_a and role_b and role_a != role_b and role_a != "tie" and role_b != "tie":
                reversal_dimensions.append(f"{first}_vs_{second}")

    return OrderedDict(
        [
            ("request_id", row.get("request_id")),
            ("cohort", row.get("cohort")),
            ("clip_source_gbps_decimal", r6(clip_source)),
            ("unet_source_gbps_decimal", r6(unet_source)),
            ("source_ratio_clip_over_unet", r6(source_ratio)),
            ("source_faster_role", source_faster),
            ("clip_active_h2d_gbps_decimal", r6(clip_active)),
            ("unet_active_h2d_gbps_decimal", r6(unet_active)),
            ("active_h2d_ratio_clip_over_unet", r6(active_ratio)),
            ("active_h2d_faster_role", active_faster),
            ("clip_h2d_span_gbps_decimal", r6(clip_h2d)),
            ("unet_h2d_span_gbps_decimal", r6(unet_h2d)),
            ("clip_load_ms", r6(clip_load)),
            ("unet_load_ms", r6(unet_load)),
            ("load_ratio_clip_over_unet", r6(load_ratio)),
            ("load_faster_role", load_faster),
            ("reversal_factor", r6(max((m for m in magnitudes.values() if m is not None), default=None)) if any(m is not None for m in magnitudes.values()) else None),
            ("dramatic_reversal", bool(dramatic_dimensions)),
            ("dramatic_reversal_dimensions", dramatic_dimensions),
            ("role_order_reversal_dimensions", reversal_dimensions),
        ]
    )


def build_same_request_contrasts(h100_rows) -> dict:
    entries = [contrast_entry(row) for row in h100_rows]
    dramatic = [e for e in entries if e.get("dramatic_reversal")]
    reversals = [e for e in entries if e.get("role_order_reversal_dimensions")]
    return OrderedDict(
        [
            ("generated_by", "tools/analysis/h100_vs_rtx_forensics.py"),
            ("units", "gbps fields are decimal GB/s (10^9 bytes/s); load in milliseconds"),
            ("source_evidence", {
                "field": "golden_telemetry.stages[*].details.transport_stats",
                "roles": list(READ_ROLES),
            }),
            ("definitions", {
                "source_gbps_decimal": "transport source_bytes / SOURCE_TOTAL_WALL_MS",
                "active_h2d_gbps_decimal": "GPU_COPY_BYTES / GPU_COPY_ACTIVE_UNION_MS",
                "load_ms": "enclosing golden_<role>_load stage wall",
                "reversal_factor": "max over the three CLIP/UNET ratios of max(r, 1/r)",
                "dramatic_reversal": f"any axis ratio magnitude >= {DRAMATIC_REVERSAL_FACTOR}",
                "role_order_reversal_dimensions": "axis pairs whose faster role differs within the same request",
            }),
            ("dramatic_reversal_factor", DRAMATIC_REVERSAL_FACTOR),
            ("counts", {
                "n_requests": len(entries),
                "n_dramatic_reversal": len(dramatic),
                "n_role_order_reversal": len(reversals),
            }),
            ("dramatic_reversal_requests", [
                {
                    "request_id": e["request_id"],
                    "cohort": e["cohort"],
                    "reversal_factor": e["reversal_factor"],
                    "dramatic_reversal_dimensions": e["dramatic_reversal_dimensions"],
                    "source_faster_role": e["source_faster_role"],
                    "clip_source_gbps_decimal": e["clip_source_gbps_decimal"],
                    "unet_source_gbps_decimal": e["unet_source_gbps_decimal"],
                    "clip_active_h2d_gbps_decimal": e["clip_active_h2d_gbps_decimal"],
                    "unet_active_h2d_gbps_decimal": e["unet_active_h2d_gbps_decimal"],
                }
                for e in dramatic
            ]),
            ("per_request", entries),
        ]
    )


def build_stage_comparison(h100_rows, rtx_rows) -> dict:
    """H100 stage/transport quantiles beside the available RTX quantiles."""
    h100_stages = OrderedDict(
        (stage, summarize((r.get("stage_walls_ms") or {}).get(stage) for r in h100_rows))
        for stage in STAGE_NAMES
    )
    rtx_stages = OrderedDict()
    for stage in STAGE_NAMES:
        values = [(r.get("stage_walls_ms") or {}).get(stage) for r in rtx_rows]
        available = [v for v in values if finite(v) is not None]
        summary = summarize(values)
        rtx_stages[stage] = OrderedDict(
            [
                ("n_total", len(rtx_rows)),
                ("n_available", len(available)),
                ("quantiles", summary if summary.get("n") else None),
            ]
        )

    def transport_summary(rows, role, field):
        return summarize(
            ((r.get("transport") or {}).get(role) or {}).get(field) for r in rows
        )

    h100_transport = OrderedDict()
    rtx_transport = OrderedDict()
    for role in ROLES:
        h100_transport[role] = OrderedDict(
            [
                ("load_ms", transport_summary(h100_rows, role, "load_ms")),
                ("source_wall_ms", transport_summary(h100_rows, role, "source_wall_ms")),
                ("h2d_span_ms", transport_summary(h100_rows, role, "h2d_span_ms")),
                ("copy_active_ms", transport_summary(h100_rows, role, "copy_active_ms")),
            ]
        )
        rtx_transport[role] = OrderedDict(
            [
                ("load_ms", transport_summary(rtx_rows, role, "load_ms")),
                ("source_wall_ms", None),
                ("h2d_span_ms", None),
                ("copy_active_ms", transport_summary(rtx_rows, role, "copy_active_ms")),
                ("nulled_fields", ["source_wall_ms", "h2d_span_ms"]),
                ("null_reason", (
                    "RTX raw transport_stats omit SOURCE_TOTAL_WALL_MS and "
                    "H2D_TOTAL_WALL_MS for every role; these fields are null, "
                    "not estimated or carried over from H100."
                )),
            ]
        )

    return OrderedDict(
        [
            ("generated_by", "tools/analysis/h100_vs_rtx_forensics.py"),
            ("units", "milliseconds; gbps fields are decimal GB/s (10^9 bytes/s)"),
            ("stage_names", list(STAGE_NAMES)),
            ("definitions", {
                "stage quantiles": "recomputed from golden_telemetry stage entry/end monotonic ns per attempt",
                "h100 rows": len(h100_rows),
                "rtx rows": len(rtx_rows),
                "unavailable": "explicitly null when the source field is absent; never synthesised",
            }),
            ("h100_stage_quantiles", h100_stages),
            ("rtx_stage_quantiles", rtx_stages),
            ("h100_transport_wall_quantiles", h100_transport),
            ("rtx_transport_wall_quantiles", rtx_transport),
        ]
    )


# ---------------------------------------------------------------------------
# Writers
# ---------------------------------------------------------------------------


def flatten_row(row, columns):
    flat = OrderedDict()
    for column in columns:
        value = row.get(column)
        if isinstance(value, (dict, list)):
            value = json.dumps(value, sort_keys=True, default=str)
        flat[column] = value
    return flat


H100_CSV_COLUMNS = (
    "cohort",
    "request_id",
    "run_index",
    "v2ctl_invocation_id",
    "mode",
    "method",
    "golden_mode",
    "golden_arm",
    "provider",
    "cloud",
    "region",
    "device",
    "image_id",
    "profile",
    "app",
    "dispatch_iso",
    "start_ts",
    "end_ts",
    "duration_ms",
    "qd_transport_arm",
    "transport_block_bytes",
    "transport_staging_slots",
    "clip_residency",
    "workflow_sha256",
    "actual_workflow_sha256",
    "expected_workflow_sha256",
    "deployment_identity",
    "deployment_combined_hash",
    "snapshot_identity",
    "config_identity",
    "runtime_shape_fingerprint",
    "profile_config_fingerprint",
    "restore_count",
    "request_count",
    "restore_total_ms",
    "clip_forward_total_ms",
    "sampler_total_wall_ms",
    "true_cold",
    "valid",
    "exact_output_valid",
    "output_sha_match",
    "observed_output_shas",
    "observed_output_byte_count",
    "output_stage_sha256",
    "output_stage_expected_sha256",
    "manifest_expected_output_sha",
    "included_in_analysis",
    "exclusion_reasons",
    "load_ms",
    "stage_walls_ms",
)

RTX_CSV_COLUMNS = (
    "run_key",
    "request_id",
    "dataset",
    "profile",
    "app",
    "commit",
    "worktree",
    "raw_path",
    "cloud",
    "region",
    "dispatch_iso",
    "start_ts",
    "end_ts",
    "duration_ms",
    "overall_request_ms",
    "sampler_total_wall_ms",
    "clip_forward_total_ms",
    "restore_total_ms",
    "clip_load_ms",
    "unet_load_ms",
    "vae_load_ms",
    "total_source_read_wall_ms",
    "source_read_count",
    "stage_span_ms",
    "true_cold",
    "valid",
    "output_sha_match",
    "expected_output_sha",
    "observed_output_shas",
    "snapshot_identity",
    "config_identity",
    "deployment_fingerprint",
    "run_fingerprint",
    "profile_config_fingerprint",
    "image_id",
    "workflow_sha256",
    "qd_transport_arm",
    "transport_block_bytes",
    "transport_staging_slots",
    "clip_residency",
    "matched_to_h100",
    "metric_availability",
    "included_in_analysis",
)

DECOMPOSITION_CSV_COLUMNS = (
    "gpu",
    "run_key",
    "role",
    "region",
    "cloud",
    "transport_present",
    "load_ms",
    "source_wall_ms",
    "syscall_union_ms",
    "source_minus_syscall_ms",
    "load_minus_source_ms",
    "h2d_span_ms",
    "copy_active_ms",
    "copy_idle_ms",
    "copy_stream_span_ms",
    "tail_ms",
    "source_to_gpu_ready_ms",
    "source_h2d_overlap_ms",
    "h2d_minus_copy_active_ms",
    "source_minus_h2d_ms",
    "copy_span_minus_active_ms",
    "overlap_frac_of_source",
    "syscall_frac_of_source",
    "h2d_frac_of_source",
    "source_bytes",
    "GPU_COPY_BYTES",
    "source_read_count",
    "h2d_submit_count",
    "GPU_COPY_COUNT",
    "source_gbps_decimal",
    "h2d_gbps_decimal",
    "copy_active_gbps_decimal",
)

PROVIDER_REGION_CSV_COLUMNS = (
    "gpu",
    "cloud",
    "region",
    "n_runs",
    "n_distinct_requests",
    "duration_ms",
    "sampler_total_wall_ms",
    "clip_forward_total_ms",
    "restore_total_ms",
    "clip_source_wall_ms",
    "unet_source_wall_ms",
)

READ_LATENCY_CSV_COLUMNS = (
    "scope",
    "request_id",
    "cohort",
    "role",
    "read_count",
    "p50_ms",
    "p90_ms",
    "p95_ms",
    "p99_ms",
    "max_ms",
    "count_ge_250_ms",
    "count_ge_500_ms",
    "count_ge_1000_ms",
    "first_pathological_ms",
    "first_pathological_seq",
    "first_pathological_threshold_ms",
    "source_bytes",
    "source_wall_ms",
    "source_gbps_decimal",
)

READ_ONSET_CSV_COLUMNS = (
    "request_id",
    "cohort",
    "role",
    "read_count",
    "max_ms",
    "onset_class_500",
    "recovery_class_500",
    "transient_recovery_500",
    "final_read_sick_500",
    "final_read_ms",
    "count_ge_250_ms",
    "count_ge_500_ms",
    "count_ge_1000_ms",
    "first_seq_ge_250",
    "first_seq_ge_500",
    "first_seq_ge_1000",
    "last_seq_ge_500",
    "toggles_ge_500",
    "episodes_ge_250",
    "episodes_ge_500",
    "episodes_ge_1000",
    "longest_episode_ge_500",
    "recovered_before_final_500",
)

CONTRAST_CSV_COLUMNS = (
    "request_id",
    "cohort",
    "clip_source_gbps_decimal",
    "unet_source_gbps_decimal",
    "source_ratio_clip_over_unet",
    "source_faster_role",
    "clip_active_h2d_gbps_decimal",
    "unet_active_h2d_gbps_decimal",
    "active_h2d_ratio_clip_over_unet",
    "active_h2d_faster_role",
    "clip_h2d_span_gbps_decimal",
    "unet_h2d_span_gbps_decimal",
    "clip_load_ms",
    "unet_load_ms",
    "load_ratio_clip_over_unet",
    "load_faster_role",
    "reversal_factor",
    "dramatic_reversal",
    "dramatic_reversal_dimensions",
    "role_order_reversal_dimensions",
)

ENDPOINT_CSV_COLUMNS = (
    "gpu",
    "run_key",
    "request_id",
    "cohort",
    "commit",
    "raw_path",
    "valid",
    "endpoint_event_name",
    "boundary_identity_field",
    "attempt_event_count",
    "event_present",
    "event_count",
    "first_result_ready_monotonic_ns",
    "first_result_ready_wall_ns",
    "parallel_method_entry_mono_ns",
    "endpoint_ms",
    "diagnostic",
)


def build_readme(context):
    lines = []
    lines.append("# H100 vs RTX 6000 Pro Golden forensics")
    lines.append("")
    lines.append(f"Generated: {context['generated_at']}")
    lines.append("")
    lines.append(
        "Machine-generated by `tools/analysis/h100_vs_rtx_forensics.py`. "
        "Read-only offline analysis of retained artifacts; no deploy, no Modal "
        "invocation, no request execution. The script refreshes only the output "
        "files it owns and never touches unowned files."
    )
    lines.append("")
    lines.append("## Units")
    lines.append("")
    lines.append(
        "All times are milliseconds. All throughput values are **decimal GB/s** "
        "(10^9 bytes per second), computed as `bytes / 1e9 / (ms / 1e3)` and "
        "suffixed `_gbps_decimal`. No binary GiB/s units are used."
    )
    lines.append("")
    lines.append("## Populations")
    lines.append("")
    pop = context["populations"]
    lines.append(
        f"- H100: {pop['h100_included']} populated cohorts included. "
        f"{pop['h100_exact_invalid']} of them are exact-output-invalid (observed "
        "SHA differs from expected); they are retained and flagged, not dropped."
    )
    lines.append(
        f"- RTX reference: best available exact-commit population from "
        f"`{pop['rtx_commit'][:12]}` - {pop['rtx_valid']} valid rows in the "
        f"population, {pop['rtx_rows_written']} written to the output tables; "
        f"{pop['rtx_invalid']} invalid rows retained as exclusions. "
        f"JSON rows for commit: {pop['rtx_json_rows_for_commit']}; "
        f"CSV rows for commit: {pop['rtx_csv_rows_for_commit']}."
    )
    lines.append(f"- H100 empty cohort directories (no attempt_0.json): {pop['h100_empty_dirs']}.")
    lines.append("")
    lines.append("## Metric definitions")
    lines.append("")
    for definition in context["definitions"]:
        lines.append(f"- {definition}")
    lines.append("")
    lines.append("## Outputs")
    lines.append("")
    for item in context["outputs"]:
        lines.append(f"- `{item['file']}`: {item['description']}")
    lines.append("")
    lines.append("## H100 per-read onset/recovery")
    lines.append("")
    lines.append(context["read_summary"])
    lines.append("")
    lines.append("## Authoritative endpoint (FIRST_RESULT_READY)")
    lines.append("")
    lines.append(context["endpoint_summary"])
    lines.append("")
    lines.append("## Raw evidence paths")
    lines.append("")
    for item in context["raw_evidence"]:
        lines.append(f"- {item}")
    lines.append("")
    lines.append("## SHA analysis")
    lines.append("")
    lines.append(context["sha_summary"])
    lines.append("")
    lines.append("## Metric availability / unavailable fields")
    lines.append("")
    for item in context["availability"]:
        lines.append(f"- {item}")
    lines.append("")
    lines.append("## Code-diff inventory")
    lines.append("")
    lines.append(context["code_diff_summary"])
    lines.append("")
    lines.append("## Reproduce")
    lines.append("")
    lines.append("```text")
    lines.append("python tools/analysis/h100_vs_rtx_forensics.py")
    lines.append("python tools/analysis/h100_vs_rtx_forensics.py --limit-rtx 3   # bounded")
    lines.append("```")
    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--h100-worktree", type=Path, default=DEFAULT_H100_WORKTREE)
    parser.add_argument("--rtx-index", type=Path, default=DEFAULT_RTX_INDEX)
    parser.add_argument("--rtx-csv", type=Path, default=DEFAULT_RTX_CSV)
    parser.add_argument("--rtx-commit", default=DEFAULT_RTX_COMMIT)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--limit-h100", type=int, default=None)
    parser.add_argument("--limit-rtx", type=int, default=None)
    parser.add_argument("--no-git", action="store_true")
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    out_dir = args.out if args.out.is_absolute() else REPO_ROOT / args.out
    worktree = (
        args.h100_worktree
        if args.h100_worktree.is_absolute()
        else REPO_ROOT / args.h100_worktree
    )
    index_path = args.rtx_index if args.rtx_index.is_absolute() else REPO_ROOT / args.rtx_index
    csv_path = args.rtx_csv if args.rtx_csv.is_absolute() else REPO_ROOT / args.rtx_csv

    if out_dir.exists():
        # Additive re-run: refresh only this script's own outputs.  Unowned
        # files are reported and left exactly as they are; the script only
        # writes names in OUTPUT_FILENAMES and never deletes anything.
        foreign = sorted(
            p.name
            for p in out_dir.iterdir()
            if p.is_file() and p.name not in OUTPUT_FILENAMES
        )
        if foreign:
            print(
                f"note: {out_dir} also contains unowned files that will be left "
                f"untouched: {', '.join(foreign)}",
                file=sys.stderr,
            )
    out_dir.mkdir(parents=True, exist_ok=True)

    h100_rows, dossier, h100_empty_dirs = build_h100_rows(
        worktree, limit=args.limit_h100
    )
    metadata, rtx_selected, rtx_valid, rtx_invalid, csv_cross = load_rtx_index(
        index_path, csv_path, args.rtx_commit
    )
    h100_signatures = {match_key_signature(r) for r in h100_rows}
    h100_signatures.discard(tuple([None] * len(MATCH_IDENTITY_FIELDS)))
    rtx_rows = build_rtx_rows(
        rtx_valid, limit=args.limit_rtx, h100_signatures=h100_signatures
    )

    # --- per-run canonical rows -------------------------------------------
    h100_payload = OrderedDict(
        [
            ("generated_by", "tools/analysis/h100_vs_rtx_forensics.py"),
            ("gpu", "h100"),
            ("source", str(worktree / H100_CORPUS)),
            ("row_count", len(h100_rows)),
            ("rows", list(h100_rows)),
        ]
    )
    write_json(out_dir / "h100_per_run_rows.json", h100_payload)
    write_csv(
        out_dir / "h100_per_run_rows.csv",
        [flatten_row(r, H100_CSV_COLUMNS) for r in h100_rows],
        H100_CSV_COLUMNS,
    )

    rtx_payload = OrderedDict(
        [
            ("generated_by", "tools/analysis/h100_vs_rtx_forensics.py"),
            ("gpu", "rtx-pro-6000"),
            ("source_index", str(index_path)),
            ("preferred_commit", args.rtx_commit),
            ("index_metadata", metadata),
            ("selected_rows_for_commit", len(rtx_selected)),
            ("valid_rows", len(rtx_valid)),
            ("invalid_rows_retained", len(rtx_invalid)),
            ("csv_cross_check", csv_cross),
            ("excluded_rows", [
                {
                    "run_key": r.get("run_key"),
                    "raw_path": r.get("raw_path"),
                    "valid": r.get("valid"),
                    "failures": r.get("failures"),
                    "validity/exclusion_reason": r.get("validity/exclusion_reason"),
                }
                for r in rtx_invalid
            ]),
            ("rows", list(rtx_rows)),
        ]
    )
    write_json(out_dir / "rtx_reference_rows.json", rtx_payload)
    write_csv(
        out_dir / "rtx_reference_rows.csv",
        [flatten_row(r, RTX_CSV_COLUMNS) for r in rtx_rows],
        RTX_CSV_COLUMNS,
    )

    # --- decomposition -----------------------------------------------------
    dec_rows = decomposition_rows(h100_rows, rtx_rows)
    aggregates = OrderedDict()
    for gpu in ("h100", "rtx-pro-6000"):
        aggregates[gpu] = OrderedDict(
            (role, decomposition_summary(dec_rows, gpu, role)) for role in ROLES
        )
    availability_by_gpu_role = build_decomposition_availability(dec_rows)
    dec_payload = OrderedDict(
        [
            ("generated_by", "tools/analysis/h100_vs_rtx_forensics.py"),
            (
                "units",
                "milliseconds; gbps fields are decimal GB/s (10^9 bytes/s)",
            ),
            (
                "definitions",
                [
                    "source_wall_ms = SOURCE_TOTAL_WALL_MS (source read+transport wall)",
                    "syscall_union_ms = SOURCE_SYSCALL_UNION_BUSY_MS (read-syscall busy union)",
                    "source_minus_syscall_ms = source_wall_ms - syscall_union_ms",
                    "load_ms = enclosing golden_<role>_load stage wall",
                    "load_minus_source_ms = load_ms - source_wall_ms (stage wall outside source)",
                    "h2d_span_ms = H2D_TOTAL_WALL_MS (host->device wall span)",
                    "copy_active_ms = GPU_COPY_ACTIVE_UNION_MS",
                    "copy_idle_ms = GPU_COPY_IDLE_INSIDE_STREAM_SPAN_MS",
                    "copy_stream_span_ms = GPU_COPY_STREAM_SPAN_MS",
                    "h2d_minus_copy_active_ms = h2d_span_ms - copy_active_ms",
                    "source_minus_h2d_ms = source_wall_ms - h2d_span_ms",
                    "tail_ms = POST_SOURCE_H2D_TAIL_MS",
                    "source_to_gpu_ready_ms = SOURCE_TO_GPU_READY_MS",
                    "source_h2d_overlap_ms = SOURCE_H2D_OVERLAP_MS",
                ],
            ),
            ("rows", dec_rows),
            ("aggregates_by_gpu_role", aggregates),
            ("availability_by_gpu_role", availability_by_gpu_role),
        ]
    )
    write_json(out_dir / "stage_transport_decomposition.json", dec_payload)
    write_csv(
        out_dir / "stage_transport_decomposition.csv",
        [
            flatten_row(r, DECOMPOSITION_CSV_COLUMNS)
            for r in dec_rows
        ],
        DECOMPOSITION_CSV_COLUMNS,
    )

    # --- provider/region ---------------------------------------------------
    provider_region = build_provider_region_table(h100_rows, rtx_rows)
    write_json(out_dir / "provider_region_table.json", provider_region)
    write_csv(
        out_dir / "provider_region_table.csv",
        [flatten_row(r, PROVIDER_REGION_CSV_COLUMNS) for r in provider_region["h100"] + provider_region["rtx"]],
        PROVIDER_REGION_CSV_COLUMNS,
    )

    # --- raw H100 per-read analysis (actual_source_events) ----------------
    read_latency, read_latency_csv = build_read_latency_summary(h100_rows)
    write_json(out_dir / "h100_read_latency_summary.json", read_latency)
    write_csv(
        out_dir / "h100_read_latency_summary.csv",
        read_latency_csv,
        READ_LATENCY_CSV_COLUMNS,
    )

    read_onset, read_onset_csv = build_read_onset_recovery(h100_rows)
    write_json(out_dir / "h100_read_onset_recovery.json", read_onset)
    write_csv(
        out_dir / "h100_read_onset_recovery.csv",
        read_onset_csv,
        READ_ONSET_CSV_COLUMNS,
    )

    # --- authoritative endpoint timing (H100 and RTX raw attempts) ---------
    endpoint_timings = build_endpoint_timings(
        h100_rows,
        rtx_rows,
        rtx_commit=args.rtx_commit,
        rtx_population={
            "json_rows_for_commit": len(rtx_selected),
            "valid_rows": len(rtx_valid),
            "invalid_rows_retained": len(rtx_invalid),
            "rows_written": len(rtx_rows),
        },
    )
    write_json(out_dir / "h100_endpoint_timings.json", endpoint_timings)
    write_csv(
        out_dir / "h100_endpoint_timings.csv",
        [
            flatten_row(r, ENDPOINT_CSV_COLUMNS)
            for r in (
                endpoint_timings["h100_rows"] + endpoint_timings["rtx_rows"]
            )
        ],
        ENDPOINT_CSV_COLUMNS,
    )

    contrasts = build_same_request_contrasts(h100_rows)
    write_json(out_dir / "h100_same_request_contrasts.json", contrasts)
    write_csv(
        out_dir / "h100_same_request_contrasts.csv",
        [
            flatten_row(e, CONTRAST_CSV_COLUMNS)
            for e in (contrasts.get("per_request") or [])
        ],
        CONTRAST_CSV_COLUMNS,
    )

    stage_comparison = build_stage_comparison(h100_rows, rtx_rows)
    write_json(out_dir / "h100_stage_comparison.json", stage_comparison)

    # --- SHA ---------------------------------------------------------------
    sha = build_sha_analysis(h100_rows, rtx_rows)
    write_json(out_dir / "sha_analysis.json", sha)

    # --- identity inventory / code diff -----------------------------------
    identity = build_identity_inventory(
        h100_rows, rtx_rows, dossier, worktree, args.rtx_commit
    )
    write_json(out_dir / "source_config_identity_inventory.json", identity)

    if args.no_git:
        code_diff = {
            "reliable": False,
            "note": "code-diff inventory disabled via --no-git",
        }
    else:
        code_diff = build_code_diff_inventory(worktree, args.rtx_commit)
    write_json(out_dir / "code_diff_inventory.json", code_diff)

    # --- README ------------------------------------------------------------
    h100_observed = sha["h100"]["observed_sha256_counts"]
    rtx_expected = sha["rtx"]["expected_sha256_counts"]
    sha_summary = (
        f"H100 observed SHA(s): {list(h100_observed)} across "
        f"{sha['h100']['rows']} rows; matches: "
        f"{sha['h100']['output_sha_match_counts']}. "
        f"RTX reference expected SHA(s): {list(rtx_expected)}; match counts: "
        f"{sha['rtx']['output_sha_match_counts']}. "
        f"Observed-SHA overlap between GPUs: "
        f"{sha['cross_gpu']['observed_sha_overlap'] or 'none'}."
    )
    availability = []
    for gpu, label in (("h100", "H100"), ("rtx-pro-6000", "RTX")):
        for role in ROLES:
            entry = availability_by_gpu_role[gpu][role]
            missing = [
                f"{field} ({counts['present']}/{counts['total']})"
                for field, counts in entry["fields"].items()
                if counts["present"] < counts["total"]
            ]
            if missing:
                availability.append(
                    f"{label} {role}: transport_stats present in "
                    f"{entry['n_with_transport']}/{entry['n_rows']} rows; partially "
                    f"populated or unavailable fields (present/total): "
                    f"{', '.join(missing)}."
                )
            else:
                availability.append(
                    f"{label} {role}: transport_stats present in "
                    f"{entry['n_with_transport']}/{entry['n_rows']} rows; every "
                    "tracked transport field is populated."
                )
    availability.append(
        "RTX index stage metrics (clip_load_ms, unet_load_ms, vae_load_ms, "
        "total_source_read_wall_ms, source_read_count) are populated for only a "
        "subset of commit rows; per-row `metric_availability.index_stage_metrics` "
        "states availability. No missing transport metric is synthesised."
    )
    availability.append(
        "Derived fields built from an unavailable input (for example "
        "copy_span_minus_active_ms when GPU_COPY_STREAM_SPAN_MS is absent) are "
        "null rather than estimated."
    )
    availability.append(
        "H100 parsed inputs per cohort: attempt_0.json, manifest.json, "
        "summary.json. attempt_0_events.json is retained and hash-inventoried in "
        "each row's `input_files` (and the dossier artifact inventory) but is not "
        "parsed because no required field exists only there."
    )
    availability.append(
        "H100 attempt-level frozen deployment identity and manifest "
        "deployment_combined_hash differ for all rows; both are retained verbatim "
        "in `source_config_identity_inventory.json` without assuming a shared "
        "hash domain."
    )
    availability.append(
        "In `h100_stage_comparison.json` every RTX transport wall field "
        "(source_wall_ms, h2d_span_ms) is explicitly null for all roles: RTX raw "
        "transport_stats omit SOURCE_TOTAL_WALL_MS and H2D_TOTAL_WALL_MS. They are "
        "null, not estimated or borrowed from H100."
    )
    availability.append(
        "In `h100_endpoint_timings.json/.csv` the endpoint for both GPUs is "
        "endpoint_ms = FIRST_RESULT_READY monotonic ns minus "
        "identity.parallel_method_entry_mono_ns, recomputed per row from raw "
        "attempt JSON. H100 reads each `cohort_*/attempt_0.json`; RTX reads the "
        "`raw_path` referenced by GOLDEN_HISTORICAL_RUNS_MASTER rather than the "
        "index summary, whose `frr_ms` is null for every commit row. A row is "
        "null only when its raw attempt/event/boundary is genuinely missing, each "
        "with a per-row diagnostic in the `missing_rows` list; no value is "
        "estimated or borrowed across GPUs."
    )
    code_diff_summary = (
        f"reliable={code_diff.get('reliable')}; H100 worktree head="
        f"{code_diff.get('h100_worktree_head')}; files changed since "
        f"{args.rtx_commit[:12]}: {len(code_diff.get('diff_files') or [])}."
    )
    read_role_totals = read_latency["read_role_totals"]
    reversal_counts = contrasts.get("counts") or {}
    read_summary = (
        "H100 per-read (clip/unet): "
        + "; ".join(
            f"{role} reads={v['read_count']} ge250={v['count_ge_250_ms']} "
            f"ge500={v['count_ge_500_ms']} ge1000={v['count_ge_1000_ms']}"
            for role, v in read_role_totals.items()
        )
        + "; dramatic CLIP/UNET reversals="
        + f"{reversal_counts.get('n_dramatic_reversal')}/{reversal_counts.get('n_requests')}."
    )
    h100_endpoint_stats = endpoint_timings["h100_endpoint_stats"]
    rtx_endpoint_stats = endpoint_timings["rtx_endpoint_stats"]
    endpoint_summary = (
        "endpoint_ms = FIRST_RESULT_READY.monotonic_ns - "
        "identity.parallel_method_entry_mono_ns (both process-monotonic ns). "
        f"H100: n={h100_endpoint_stats.get('n')}, "
        f"min={h100_endpoint_stats.get('min')} ms, "
        f"median={h100_endpoint_stats.get('median')} ms, "
        f"max={h100_endpoint_stats.get('max')} ms, "
        f"rows_missing={h100_endpoint_stats.get('rows_missing_endpoint')}. "
        f"RTX commit {args.rtx_commit[:12]}: "
        f"n={rtx_endpoint_stats.get('n')}, "
        f"min={rtx_endpoint_stats.get('min')} ms, "
        f"median={rtx_endpoint_stats.get('median')} ms, "
        f"max={rtx_endpoint_stats.get('max')} ms, "
        f"rows_missing={rtx_endpoint_stats.get('rows_missing_endpoint')}. "
        "RTX values are read from the raw attempt JSON referenced by the "
        "historical index `raw_path`, not from the index summary (its `frr_ms` "
        "is null for every commit row)."
    )
    rtx_raw_available = sum(1 for r in rtx_rows if r.get("raw_available"))
    raw_evidence = [
        f"H100 corpus root: `{worktree / H100_CORPUS}`.",
        "H100 per-attempt raw JSON: `cohort_*/attempt_0.json` for each populated "
        "cohort; companion `attempt_0_events.json`, `manifest.json`, and "
        "`summary.json` are hash-inventoried in each row's `input_files`.",
        f"H100 email dossier (embedded JSON index): `{dossier.get('email_dossier_path')}`; "
        f"`{dossier.get('full_dossier_path')}` is read as an index only.",
        f"RTX historical index: `{index_path}` (CSV cross-check `{csv_path}`).",
        f"RTX per-run raw attempts resolved from the index `raw_path` "
        f"({rtx_raw_available}/{len(rtx_rows)} available).",
        "Per-read evidence for the read-analysis outputs: "
        "`golden_telemetry.stages[*].details.transport_stats.actual_source_events` "
        "(clip and unet only; transport_stats is a list for clip and a dict for unet).",
        "Endpoint evidence for `h100_endpoint_timings.json/.csv` (both GPUs): "
        "`golden_telemetry.events[*]` (the FIRST_RESULT_READY event) and "
        "`identity.parallel_method_entry_mono_ns`. H100 reads each "
        "`cohort_*/attempt_0.json`; RTX reads the raw attempt JSON referenced by "
        "the GOLDEN_HISTORICAL_RUNS_MASTER `raw_path` "
        "(`.slim/worktrees/.../cohort_*/attempt_0.json`), not the index summary.",
    ]
    h100_exact_invalid = sum(1 for r in h100_rows if not r.get("exact_output_valid"))
    context = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "populations": {
            "h100_included": len(h100_rows),
            "h100_exact_invalid": h100_exact_invalid,
            "h100_empty_dirs": len(h100_empty_dirs),
            "rtx_commit": args.rtx_commit,
            "rtx_valid": len(rtx_valid),
            "rtx_invalid": len(rtx_invalid),
            "rtx_rows_written": len(rtx_rows),
            "rtx_json_rows_for_commit": len(rtx_selected),
            "rtx_csv_rows_for_commit": csv_cross.get("csv_rows_for_commit"),
        },
        "definitions": dec_payload["definitions"],
        "outputs": [
            {"file": "h100_per_run_rows.json/.csv", "description": "canonical H100 per-run rows (all 11, exclusions retained)"},
            {"file": "rtx_reference_rows.json/.csv", "description": "matched RTX reference rows from the preferred commit with metric availability"},
            {"file": "stage_transport_decomposition.json/.csv", "description": "per-run/per-role stage and transport decomposition with decimal GB/s and quantile aggregates"},
            {"file": "provider_region_table.json/.csv", "description": "provider/cloud x region aggregation"},
            {"file": "sha_analysis.json", "description": "observed vs expected SHA-256 analysis for both GPUs"},
            {"file": "source_config_identity_inventory.json", "description": "source/config identity hashes and per-row identity inventory"},
            {"file": "code_diff_inventory.json", "description": "read-only git diff inventory between the RTX reference commit and the H100 worktree head"},
            {"file": "h100_read_latency_summary.json/.csv", "description": "per-role and per-request H100 actual_source_events latency quantiles, >=250/500/1000 ms counts, first pathological read, and source throughput"},
            {"file": "h100_read_onset_recovery.json/.csv", "description": "born-sick vs becomes-sick onset classes, contiguous sick episodes, transient recovery and final-read state per request/role"},
            {"file": "h100_same_request_contrasts.json/.csv", "description": "within-request CLIP vs UNET source GB/s, active H2D GB/s, load, and dramatic reversals"},
            {"file": "h100_endpoint_timings.json/.csv", "description": "authoritative H100 and RTX endpoint latency: FIRST_RESULT_READY minus identity.parallel_method_entry_mono_ns, recomputed from raw attempt JSON (H100 cohort attempts; RTX the raw_path referenced by GOLDEN_HISTORICAL_RUNS_MASTER); separate per-row sections and per-GPU min/q1/median/q3/p90/p95/p99/max, with commit/population labels"},
            {"file": "h100_stage_comparison.json", "description": "H100 quantiles for every authoritative stage beside available RTX stage quantiles; unavailable RTX transport wall fields are explicitly null"},
            {"file": "README.md", "description": "this machine-generated index"},
        ],
        "sha_summary": sha_summary,
        "read_summary": read_summary,
        "endpoint_summary": endpoint_summary,
        "raw_evidence": raw_evidence,
        "availability": availability,
        "code_diff_summary": code_diff_summary,
    }
    (out_dir / "README.md").write_text(build_readme(context), encoding="utf-8")

    print(json.dumps({
        "out_dir": str(out_dir),
        "h100_rows": len(h100_rows),
        "h100_exact_invalid": h100_exact_invalid,
        "rtx_valid_population": len(rtx_valid),
        "rtx_rows_written": len(rtx_rows),
        "rtx_invalid_rows": len(rtx_invalid),
        "rtx_csv_rows_for_commit": csv_cross.get("csv_rows_for_commit"),
        "code_diff_reliable": code_diff.get("reliable"),
        "h100_empty_dirs": h100_empty_dirs,
        "h100_read_totals": read_latency.get("read_role_totals"),
        "dramatic_reversal_requests": (contrasts.get("counts") or {}).get(
            "n_dramatic_reversal"
        ),
        "h100_endpoint_ms_median": endpoint_timings["h100_endpoint_stats"].get(
            "median"
        ),
        "h100_endpoint_ms_min": endpoint_timings["h100_endpoint_stats"].get("min"),
        "h100_endpoint_ms_max": endpoint_timings["h100_endpoint_stats"].get("max"),
        "rtx_endpoint_n": endpoint_timings["rtx_endpoint_stats"].get("n"),
        "rtx_endpoint_ms_median": endpoint_timings["rtx_endpoint_stats"].get(
            "median"
        ),
        "rtx_endpoint_ms_min": endpoint_timings["rtx_endpoint_stats"].get("min"),
        "rtx_endpoint_ms_max": endpoint_timings["rtx_endpoint_stats"].get("max"),
        "rtx_endpoint_rows_missing": endpoint_timings["rtx_endpoint_stats"].get(
            "rows_missing_endpoint"
        ),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
