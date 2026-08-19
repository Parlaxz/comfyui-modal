"""Batch-B acceptance harness validator (Batch B4 - integrated RUN 1 gate).

Pure, offline validation core for the strict Batch-B structural/stage
acceptance gates.  It consumes the same single run artifact dict shape as
``tools/batch_a_acceptance.py`` (the ``run_<i>.json`` files persisted by
``benchmark_v2_direct.py``)::

    {
      "run_index": int,
      "request_id": str,
      "identity": {...},
      "timing": {...},
      "result": {
          "trace": {"events": [...], "metadata": {...}},
          "_restore_timing": {...},
          "pre_sampler_structured_report": {...},
          ...
      },
      "waterfall": {...},
      "waterfall_local": {...},
      "host_diagnostics": {...},
      "runtime_shape": {...},
    }

This module NEVER executes Modal, never imports the repo runtime, never spawns
processes and never touches the network: it is a pure dict-in/dict-out
validator.  Every gate FAILS with an explicit "not observable" detail when
neither the exact Batch-B field nor any documented runtime equivalent exists -
a pass is never faked.

Batch-A preservation is delegated to ``tools.batch_a_acceptance.validate_batch_a``
(imported/reused, never duplicated), with the host-telemetry and slow-forensic
checks re-evaluated under the Batch-B Tier-A/Tier-B contract (see gate 1).

Batch-B gates validated here:

1.  Batch-A preserved: every ``validate_batch_a`` invariant (fresh identity,
    STATUS OK, reconciliation <= 50 ms, G1 single-execution proof, models
    reload skip, node timestamps, terminal cleanup stamps, subprocess
    forensics) EXCEPT the two host-telemetry checks, which are re-evaluated
    by the Batch-B Tier-A/Tier-B telemetry + slow-H2D forensic contract
    below.  Batch-B NEVER rejects a legitimately slow H2D (>= slow
    threshold) merely because ``host_forensic_slow_h2d`` exists.
2.  Runtime-state guard (``COMFYMODAL_V2_BATCH_B_EXPECT_RUNTIME_STATE_SKIP``):
    when the expectation is enabled the runtime-state reload lane must
    conclude ``skipped_generation_match``, must not invoke a reload
    (``runtime_state_reload_invoked == false``), must cost 0 ms or be
    local-check-only, must carry a generation check, and the check must be
    local (no remote decision RPC).  **Evidence may come ONLY from fields and
    events that unambiguously describe runtime state** (``runtime_state_*`` /
    ``reload_runtime_state_*`` names, including restore-decomposition fields
    explicitly named for runtime_state).  Models-volume guard evidence
    (``models_reload_decision``, ``reload_models_invoked``,
    ``reload_models_ms``, ``reload_models_reason``, ``reload_models_start``)
    is NEVER runtime-state evidence: those fields describe the Batch-A MODELS
    volume lane and can report a clean skip while the runtime-state reload
    still executes normally.  When the runtime-state lane is NOT READY (no
    runtime-state-specific observables) and the expectation is ON, the gate
    FAILS (expected skip missing); with the expectation OFF it reports the
    observed state / NOT READY and never fails merely because the
    optimization is unavailable.
3.  Snapshot hygiene (``COMFYMODAL_V2_SNAPSHOT_ALLOCATOR_HYGIENE``): when
    enabled, exactly one ``snapshot_capture_hygiene`` record is required with
    enabled=1, before/after RSS measurements, a valid ``hygiene_wall_ms``,
    a gc result, and a malloc_trim status/result.  RSS deltas are REPORTED,
    never gated (measurement experiment; RSS is not required to decrease).
    Explicitly-recorded "unavailable" (e.g. malloc_trim on a platform that
    lacks it) is accepted.
4.  Snapshot manifest (``COMFYMODAL_V2_SNAPSHOT_MANIFEST``): when enabled, a
    manifest status/result must be present.  An unavailable smaps/anonymous
    split is allowed when explicitly recorded unavailable.  Fails when the
    instrumentation silently omits status.
5.  Stage-13 decomposition (``output_stage13_breakdown`` or the actual
    runtime field equivalent): children must be nonnegative, the stage total
    must be valid, and sum(children) must reconcile the parent Stage 13 total
    within ``STAGE13_TOLERANCE_MS`` (default 10 ms).  The largest child is
    reported.  No performance win is required.  With
    ``COMFYMODAL_V2_BATCH_B_EXPECT_STAGE13=1`` a missing decomposition is a
    FAIL (and any present-but-malformed breakdown always fails); with the
    expectation off, a missing decomposition reports NOT READY and does not
    fail the run.
6.  Host telemetry - Tier A / Tier B split:
    - healthy H2D (< slow threshold): Tier-A overhead <= 20 ms REQUIRED and
      the slow-trigger (Tier-B) probe must be 0;
    - slow H2D (>= slow threshold): Tier-A overhead <= 20 ms required, the
      Tier-B forensic cost is reported separately, and the TOTAL probe wall
      may exceed 20 ms (the excess is the legitimate slow-trigger forensic
      probe - NOT a failure);
    - slow H2D + ``host_forensic_slow_h2d`` event => forensic-correctness
      PASS (the event is EXPECTED on a genuinely slow transfer);
    - healthy H2D + forensic event => FAIL;
    - slow H2D without a forensic event => FAIL only when
      ``COMFYMODAL_V2_BATCH_B_EXPECT_SLOW_H2D_FORENSIC=1`` (the slow-trigger
      runtime is expected to be enabled and observable); otherwise reported,
      not a failure;
    - when the decomposition is insufficient to distinguish Tier A from
      Tier B on a slow run, the telemetry-overhead gate reports NOT
      OBSERVABLE rather than falsely failing on a total > 20 ms.

TOTAL WALL is never an acceptance gate: it is reported as informational only
and explicitly marked "TOTAL WALL NOT AN ACCEPTANCE GATE".
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any

# Batch-A core is reused, never duplicated: the preservation gate delegates to
# validate_batch_a, and the private helpers below are shared verbatim.
from tools.batch_a_acceptance import (
    HOST_PROBE_EVENT_NAMES,
    HOST_TELEMETRY_MAX_PROBE_WALL_MS,
    RECONCILIATION_HARD_MS,
    SLOW_FORENSIC_EVENT_NAMES,
    SLOW_H2D_THRESHOLD_MS,
    _boolish,
    _count_events,
    _deep_get,
    _event_metadata_value,
    _events,
    _num,
    validate_batch_a,
)

# ── Hard gates / thresholds ──────────────────────────────────────────────
STAGE13_TOLERANCE_MS = float(
    os.environ.get("COMFYMODAL_V2_BATCH_B_STAGE13_TOLERANCE_MS", "10") or 10
)
# Local generation-check budget: a skipped runtime-state reload may only cost
# as much as an O(1) local generation-record read+compare.  Anything larger
# than this is a real reload, which contradicts skipped_generation_match.
LOCAL_CHECK_BUDGET_MS = 10.0

# ── Canonical runtime event / field names (current checkout) ─────────────
# Runtime-state evidence is STRICTLY runtime-state-specific: only fields and
# events whose names unambiguously describe the runtime-state lane
# (``runtime_state_*`` / ``reload_runtime_state_*``) or restore-decomposition
# fields explicitly named for runtime_state (e.g. ``runtime_state_ms`` at
# runtime_bootstrap.py:2201-2215).  Models-volume guard evidence from Batch A
# (models_reload_decision / reload_models_*) is NEVER runtime-state evidence.
RELOAD_RUNTIME_STATE_EVENT_NAMES = ("reload_runtime_state_start", "reload_runtime_state_end")
RESTORE_DECOMPOSITION_EVENT = "restore_decomposition"
SNAPSHOT_CAPTURE_HYGIENE_EVENT = "snapshot_capture_hygiene"
SNAPSHOT_MANIFEST_EVENT_NAMES = ("snapshot_manifest", "v2_snapshot_manifest")
SNAPSHOT_HYGIENE_EVENT_NAMES = ("snapshot_capture_hygiene", "capture_hygiene", "snapshot_hygiene")
STAGE13_BREAKDOWN_EVENT_NAMES = ("output_stage13_breakdown", "stage13_breakdown", "stage_13_breakdown")
# The eight stage-13 children, in runtime emit order.  The runtime spells the
# breakdown as a flat dict keyed ``{child_name}_ms`` plus a ``children_order``
# list; these names are the fallback when no children_order is present.
STAGE13_CHILD_NAMES = (
    "output_collection",
    "asset_local_write",
    "descriptor_build",
    "trace_enrichment",
    "interval_build",
    "resource_enrichment",
    "waterfall_build",
    "other_pre_emit",
)

# Tier-A host probe events: every host probe EXCEPT the Tier-B slow-trigger
# forensic event (host_hardware_fingerprint + host_resource_snapshot).
TIER_A_HOST_PROBE_EVENT_NAMES = tuple(
    n for n in HOST_PROBE_EVENT_NAMES if n not in SLOW_FORENSIC_EVENT_NAMES
)
# Batch-A checks that are re-evaluated under the Batch-B telemetry contract
# (never duplicated; simply excluded from the delegated result).
_BATCH_A_TELEMETRY_CHECK_KEYS = ("host_telemetry_overhead", "host_slow_forensic")


# ── Small private helpers ────────────────────────────────────────────────
def _first_value(*candidates: Any) -> Any:
    """First non-None candidate (0/False are values, not misses)."""
    for c in candidates:
        if c is not None:
            return c
    return None


def _env_truthy(name: str, default: bool = False) -> bool:
    """env_flag-like truthiness for the Batch-B acceptance flags.

    Pure stdlib (no runtime import): ``1/true/yes/on`` are truthy.
    """
    if name not in os.environ:
        return default
    return os.environ.get(name, "").strip().lower() in ("1", "true", "yes", "on")


def batch_b_config_from_env() -> dict[str, Any]:
    """Resolve the Batch-B acceptance configuration from the environment.

    Flags (all opt-in; flag off => the corresponding gate is not enforced):
      COMFYMODAL_V2_BATCH_B_EXPECT_RUNTIME_STATE_SKIP - require the
          runtime-state reload lane to conclude skipped_generation_match.
      COMFYMODAL_V2_BATCH_B_EXPECT_STAGE13 - require the stage-13
          decomposition (missing => FAIL; the integration enables this).
      COMFYMODAL_V2_BATCH_B_EXPECT_SLOW_H2D_FORENSIC - require the
          host_forensic_slow_h2d event whenever H2D >= the slow threshold.
      COMFYMODAL_V2_SNAPSHOT_ALLOCATOR_HYGIENE - require the
          snapshot_capture_hygiene record.
      COMFYMODAL_V2_SNAPSHOT_MANIFEST - require a snapshot manifest
          status/result.
      COMFYMODAL_V2_BATCH_B_STAGE13_TOLERANCE_MS - stage-13 reconciliation
          tolerance (default 10 ms).
    """
    return {
        "expect_runtime_state_skip": _env_truthy(
            "COMFYMODAL_V2_BATCH_B_EXPECT_RUNTIME_STATE_SKIP"
        ),
        "expect_stage13": _env_truthy("COMFYMODAL_V2_BATCH_B_EXPECT_STAGE13"),
        "expect_slow_h2d_forensic": _env_truthy(
            "COMFYMODAL_V2_BATCH_B_EXPECT_SLOW_H2D_FORENSIC"
        ),
        "snapshot_hygiene_enabled": _env_truthy(
            "COMFYMODAL_V2_SNAPSHOT_ALLOCATOR_HYGIENE"
        ),
        "snapshot_manifest_enabled": _env_truthy(
            "COMFYMODAL_V2_SNAPSHOT_MANIFEST"
        ),
        "stage13_tolerance_ms": float(
            os.environ.get("COMFYMODAL_V2_BATCH_B_STAGE13_TOLERANCE_MS", "10") or 10
        ),
    }


# ── Result containers ────────────────────────────────────────────────────
@dataclass
class GateCheck:
    key: str
    ok: bool
    value: Any
    detail: str


@dataclass
class BatchBAcceptanceResult:
    # Gate 1 - Batch-A preserved (delegated, telemetry checks re-evaluated).
    batch_a_preserved: bool
    batch_a_fresh: str
    batch_a_reconciliation_ms: float | None
    batch_a_detail: str
    # Gate 2 - runtime-state guard (runtime-state evidence ONLY).
    runtime_state_expectation: bool
    runtime_state_ready: bool
    runtime_state_evidence: str
    runtime_state_decision: str | None
    runtime_state_invoked: bool | None
    runtime_state_reload_ms: float | None
    runtime_state_generation_check: bool | None
    runtime_state_local_only: bool | None
    runtime_state_ok: bool
    # Gate 3 - snapshot hygiene.
    snapshot_hygiene_enabled: bool
    snapshot_hygiene_present: bool
    hygiene_rss_before: float | None
    hygiene_rss_after: float | None
    hygiene_rss_delta: float | None
    hygiene_rss_anon_before: float | None
    hygiene_rss_anon_after: float | None
    hygiene_rss_anon_delta: float | None
    hygiene_wall_ms: float | None
    hygiene_gc: Any
    hygiene_malloc_trim: Any
    hygiene_ok: bool
    # Gate 4 - snapshot manifest.
    snapshot_manifest_enabled: bool
    snapshot_manifest_present: bool
    manifest_status: Any
    manifest_smaps_unavailable: bool | None
    manifest_ok: bool
    # Gate 5 - stage-13 decomposition.
    stage13_expectation: bool
    stage13_ready: bool
    stage13_total: float | None
    stage13_children: list[dict[str, Any]]
    stage13_largest_child: dict[str, Any] | None
    stage13_reconciliation_ms: float | None
    stage13_ok: bool
    # Gate 6 - host telemetry (Tier A / Tier B split).
    host_telemetry_tier_a_ms: float | None
    host_telemetry_total_ms: float | None
    slow_trigger_probe_ms: float | None
    host_telemetry_not_observable: bool
    host_telemetry_ok: bool
    slow_forensic_triggered: bool
    slow_forensic_expected_missing: bool | None
    slow_forensic_expectation: bool
    slow_forensic_ok: bool
    # Informational.
    total_wall_ms: float | None
    checks: list[GateCheck] = field(default_factory=list)
    passed: bool = False


# ── Runtime-state guard ──────────────────────────────────────────────────
# Runtime-state evidence is resolved ONLY from runtime-state-specific fields
# and events.  Models-volume guard fields (Batch A) are deliberately excluded:
# a clean models decision says nothing about the runtime-state reload lane.
def _restore_decomp_meta(result: dict) -> dict:
    """Metadata of the restore_decomposition trace event ({} when absent)."""
    for _e in _events(result):
        if not isinstance(_e, dict) or _e.get("name") != RESTORE_DECOMPOSITION_EVENT:
            continue
        _m = _e.get("metadata")
        if isinstance(_m, dict):
            return _m
    return {}


def _restore_phase_events(result: dict, names: tuple[str, ...]) -> list[dict]:
    """Trace events named in *names* that belong to the RESTORE lane only
    (``phase == "restore"``).

    The construction container legitimately emits
    ``reload_runtime_state_start``/``reload_runtime_state_end`` with
    ``phase="startup"`` unconditionally (runtime_bootstrap.py), and the merged
    run trace carries them.  Such construction-time events must NEVER count as
    restore-lane reload evidence - only phase="restore" events do.
    """
    return [
        e for e in _events(result)
        if isinstance(e, dict)
        and e.get("name") in names
        and e.get("phase") == "restore"
    ]


def _runtime_state_observables(artifact: dict) -> dict[str, Any]:
    """Resolve the runtime-state reload lane observables from the artifact.

    Sources are strictly runtime-state-specific:
      - exact fields ``runtime_state_reload_decision`` /
        ``runtime_state_reload_invoked`` / ``runtime_state_reload_ms`` /
        ``reload_runtime_state_ms`` / ``runtime_state_generation_check`` /
        ``runtime_state_reload_remote_calls`` (result top level,
        ``_restore_timing``, ``trace.metadata``);
      - restore-decomposition fields EXPLICITLY named for runtime_state
        (``runtime_state_ms`` and the ``runtime_state_*`` reload fields);
      - runtime-state-named events (``reload_runtime_state_start`` /
        ``reload_runtime_state_end``, ``runtime_state_reload_decision``).
        Event evidence is RESTORE-PHASE ONLY (``phase == "restore"``): the
        construction container legitimately emits
        ``reload_runtime_state_start``/``end`` with ``phase="startup"``
        unconditionally and the merged run trace carries them, so those must
        never count as restore-lane reload evidence.
    Models-volume guard fields are NEVER accepted as runtime-state evidence.
    """
    _result = artifact.get("result") or {}
    if not isinstance(_result, dict):
        _result = {}
    _dec_meta = _restore_decomp_meta(_result)
    _evidence: list[str] = []

    def _rt_deep_get(*keys: str) -> Any:
        """First runtime-state-named hit across the exact key spellings."""
        return _first_value(*(_deep_get(_result, k) for k in keys))

    # Decision: skipped_generation_match is the required conclusion.
    _decision = _rt_deep_get(
        "runtime_state_reload_decision",
        "_restore_timing.runtime_state_reload_decision",
        "trace.metadata.runtime_state_reload_decision",
        "runtime_state_decision",
        "_restore_timing.runtime_state_decision",
        "trace.metadata.runtime_state_decision",
    )
    if _decision is None:
        _decision = _first_value(
            _dec_meta.get("runtime_state_reload_decision"),
            _dec_meta.get("runtime_state_decision"),
        )
    # The runtime emits a single runtime_state_reload_decision trace event
    # (phase="restore") whose metadata also carries
    # runtime_state_reload_invoked (0/1) and check_ms (the O(1) local
    # generation-check guard cost).
    _event_invoked = None
    _event_check_ms = None
    for _e in _restore_phase_events(
        _result, ("runtime_state_reload_decision", "runtime_state_reload")
    ):
        _dm = _e.get("metadata")
        if not isinstance(_dm, dict):
            continue
        if _dm.get("decision") is not None:
            _decision = _dm.get("decision")
        if _event_invoked is None:
            _event_invoked = _dm.get("runtime_state_reload_invoked")
        if _event_check_ms is None:
            _event_check_ms = _dm.get("check_ms")
    if _decision is not None:
        _evidence.append("decision")

    # Invoked: false is the required state.  Exact field, then runtime-state
    # reload events (a reload start event means the callback ran), then
    # inference from a clean runtime-state skip decision only.
    _invoked = _rt_deep_get(
        "runtime_state_reload_invoked",
        "_restore_timing.runtime_state_reload_invoked",
        "_restore_timing.reload_runtime_state_invoked",
        "trace.metadata.runtime_state_reload_invoked",
        "runtime_state_invoked",
        "_restore_timing.runtime_state_invoked",
        "trace.metadata.runtime_state_invoked",
    )
    _invoked_source = "exact"
    if _invoked is None:
        _invoked = _dec_meta.get("runtime_state_reload_invoked")
        if _invoked is not None:
            _invoked_source = "restore_decomposition runtime_state_reload_invoked"
    if _invoked is None:
        # Runtime decision-event metadata also carries runtime_state_reload_invoked
        # (an int 0/1 when the runtime field spelling is used).
        _invoked = _event_invoked
        if _invoked is not None:
            _invoked_source = (
                "runtime_state_reload_decision event metadata "
                "runtime_state_reload_invoked"
            )
    if _invoked is None:
        # RESTORE-lane reload events only: construction-time (phase="startup")
        # reload_runtime_state_start/end are unconditional and must never count.
        _start_events = _restore_phase_events(
            _result, RELOAD_RUNTIME_STATE_EVENT_NAMES
        )
        if _start_events:
            _invoked = True
            _invoked_source = (
                "restore-phase reload_runtime_state_start/end event present "
                "(runtime-state lane executed)"
            )
        elif _decision == "skipped_generation_match":
            _invoked = False
            _invoked_source = (
                "inferred: runtime-state decision=skipped_generation_match "
                "and no restore-phase runtime-state reload events"
            )
    # Normalize non-bool spellings (the runtime emits an int 0/1 in the
    # decision-event metadata).
    if _invoked is not None and not isinstance(_invoked, bool):
        _invoked_source = (
            f"normalized {_invoked_source}: {_invoked!r} -> {_boolish(_invoked)!r}"
        )
        _invoked = _boolish(_invoked)
    if _invoked is not None:
        _evidence.append("invoked")

    # Reload ms: 0 / absent is the required state (local-check-only allowed).
    _reload_ms = _rt_deep_get(
        "runtime_state_reload_ms",
        "_restore_timing.runtime_state_reload_ms",
        "trace.metadata.runtime_state_reload_ms",
        "reload_runtime_state_ms",
        "_restore_timing.reload_runtime_state_ms",
        "trace.metadata.reload_runtime_state_ms",
        "_restore_timing.runtime_state_ms",
        "trace.metadata.runtime_state_ms",
    )
    if _reload_ms is None:
        _reload_ms = _dec_meta.get("runtime_state_ms")
    if _reload_ms is not None:
        _evidence.append("reload_ms")

    # Generation check present (runtime-state-named only).
    _generation_check = _rt_deep_get(
        "runtime_state_generation_check",
        "_restore_timing.runtime_state_generation_check",
        "trace.metadata.runtime_state_generation_check",
    )
    if _generation_check is None:
        _generation_check = _dec_meta.get("runtime_state_generation_check")
    if _generation_check is None:
        _check_ms = _rt_deep_get(
            "runtime_state_reload_check_ms",
            "_restore_timing.runtime_state_reload_check_ms",
            "trace.metadata.runtime_state_reload_check_ms",
        )
        if _check_ms is None:
            _check_ms = _dec_meta.get("runtime_state_reload_check_ms")
        if _check_ms is not None:
            _generation_check = True
        else:
            # Runtime decision-event metadata: check_ms is the O(1) local
            # generation-check guard cost (a nonnegative number).
            _event_check_num = _num(_event_check_ms)
            if _event_check_num is not None and _event_check_num >= 0:
                _generation_check = True
    if _generation_check is not None:
        _evidence.append("generation_check")

    # Local / no remote decision RPC (runtime-state-named only).
    _remote_rpc = _rt_deep_get(
        "runtime_state_reload_remote_calls",
        "_restore_timing.runtime_state_reload_remote_calls",
        "trace.metadata.runtime_state_reload_remote_calls",
    )
    if _remote_rpc is None:
        _remote_rpc = _dec_meta.get("runtime_state_reload_remote_calls")
    _local_only = True
    _local_only_evidence = "no runtime-state remote counter/event observable"
    if _remote_rpc is not None and _num(_remote_rpc) is not None:
        _local_only = _num(_remote_rpc) == 0
        _local_only_evidence = f"runtime_state_reload_remote_calls={_remote_rpc!r}"
    elif _invoked is True:
        _local_only = False
        _local_only_evidence = "runtime-state reload invoked (a reload is not a local check)"
    elif _restore_phase_events(_result, RELOAD_RUNTIME_STATE_EVENT_NAMES):
        _local_only = False
        _local_only_evidence = (
            "restore-phase reload_runtime_state_start/end event present"
        )

    return {
        "decision": str(_decision) if _decision is not None else None,
        "invoked": _invoked,
        "invoked_source": _invoked_source,
        "reload_ms": _num(_reload_ms) if _reload_ms is not None else None,
        "generation_check": _generation_check,
        "local_only": _local_only,
        "local_only_evidence": _local_only_evidence,
        "evidence": ", ".join(_evidence) if _evidence else "none",
        "ready": bool(_evidence),
    }


# ── Snapshot hygiene ─────────────────────────────────────────────────────
def _snapshot_hygiene_record(artifact: dict) -> dict[str, Any] | None:
    """Locate the snapshot_capture_hygiene record (exact key or event)."""
    _result = artifact.get("result") or {}
    if not isinstance(_result, dict):
        _result = {}
    _record = _first_value(
        _deep_get(_result, "snapshot_capture_hygiene",
                  "_restore_timing.snapshot_capture_hygiene",
                  "trace.metadata.snapshot_capture_hygiene"),
        _deep_get(_result, "snapshot_allocator_hygiene",
                  "_restore_timing.snapshot_allocator_hygiene",
                  "trace.metadata.snapshot_allocator_hygiene"),
    )
    if _record is not None and isinstance(_record, dict):
        return _record
    for _event in _events(_result):
        if not isinstance(_event, dict):
            continue
        if _event.get("name") not in SNAPSHOT_HYGIENE_EVENT_NAMES:
            continue
        _meta = _event.get("metadata")
        if isinstance(_meta, dict) and _meta:
            return _meta
    return None


# ── Snapshot manifest ────────────────────────────────────────────────────
def _snapshot_manifest(artifact: dict) -> dict[str, Any] | None:
    """Locate the snapshot manifest record (exact key or event)."""
    _result = artifact.get("result") or {}
    if not isinstance(_result, dict):
        _result = {}
    _manifest = _first_value(
        _deep_get(_result, "snapshot_manifest",
                  "_restore_timing.snapshot_manifest",
                  "trace.metadata.snapshot_manifest"),
    )
    if _manifest is not None and isinstance(_manifest, dict):
        return _manifest
    for _event in _events(_result):
        if not isinstance(_event, dict):
            continue
        if _event.get("name") not in SNAPSHOT_MANIFEST_EVENT_NAMES:
            continue
        _meta = _event.get("metadata")
        if isinstance(_meta, dict) and _meta:
            return _meta
    return None


# ── Stage-13 decomposition ───────────────────────────────────────────────
def _stage13_child_key(name: str) -> str:
    """Normalize a child name to its runtime flat key ``{name}_ms``.

    The runtime's ``children_order`` entries already carry the ``_ms`` suffix
    (stage13_breakdown.py emits ``list(CHILD_NAMES)`` where CHILD_NAMES end in
    ``_ms``), so they must be used as-is; the fallback child names (and any
    legacy spelling) do not and get the suffix appended.
    """
    return name if name.endswith("_ms") else f"{name}_ms"


def _stage13_breakdown(artifact: dict) -> dict[str, Any] | None:
    """Locate the stage-13 breakdown (exact key or event metadata)."""
    _result = artifact.get("result") or {}
    if not isinstance(_result, dict):
        _result = {}
    _breakdown = _first_value(
        _deep_get(_result, "output_stage13_breakdown",
                  "_restore_timing.output_stage13_breakdown",
                  "trace.metadata.output_stage13_breakdown"),
        _deep_get(_result, "stage13_breakdown",
                  "_restore_timing.stage13_breakdown",
                  "trace.metadata.stage13_breakdown"),
        _deep_get(_result, "stage_13_breakdown",
                  "_restore_timing.stage_13_breakdown",
                  "trace.metadata.stage_13_breakdown"),
        _deep_get(_result, "stage13",
                  "_restore_timing.stage13",
                  "trace.metadata.stage13"),
    )
    if _breakdown is not None and isinstance(_breakdown, dict):
        return _breakdown
    for _event in _events(_result):
        if not isinstance(_event, dict):
            continue
        if _event.get("name") not in STAGE13_BREAKDOWN_EVENT_NAMES:
            continue
        _meta = _event.get("metadata")
        if isinstance(_meta, dict) and _meta:
            return _meta
    return None


# ── Telemetry / H2D helpers ──────────────────────────────────────────────
def _h2d_durations_ms(artifact: dict) -> list[float]:
    """Real fast-disk H2D durations: unet_fast_disk_complete to_wall_ms /
    to_device_ms plus lane-scoped unet_h2d deltas (same evidence the
    Batch-A harness uses)."""
    _result = artifact.get("result") or {}
    if not isinstance(_result, dict):
        _result = {}
    _durations = [
        _num((e.get("metadata") or {}).get("to_wall_ms"))
        for e in _events(_result)
        if isinstance(e, dict) and e.get("name") == "unet_fast_disk_complete"
    ]
    _durations += [
        _num((e.get("metadata") or {}).get("duration_ms"))
        for e in _events(_result)
        if isinstance(e, dict) and e.get("name") == "unet_h2d"
        and str((e.get("metadata") or {}).get("lane", "")).upper() == "UNET"
    ]
    return [d for d in _durations if d is not None]


def _slow_trigger_probe_ms(artifact: dict) -> float | None:
    """Tier-B slow-trigger forensic probe cost: explicit field first, else the
    summed probe_wall_ms of the host_forensic_slow_h2d event(s)."""
    _result = artifact.get("result") or {}
    if not isinstance(_result, dict):
        _result = {}
    _explicit = _num(_first_value(
        _deep_get(_result, "slow_trigger_probe_ms",
                  "_restore_timing.slow_trigger_probe_ms",
                  "trace.metadata.slow_trigger_probe_ms"),
        _deep_get(_result, "host_telemetry_slow_trigger_probe_ms",
                  "_restore_timing.host_telemetry_slow_trigger_probe_ms",
                  "trace.metadata.host_telemetry_slow_trigger_probe_ms"),
    ))
    if _explicit is not None:
        return _explicit
    _probe_sum = 0.0
    for _e in _events(_result):
        if not isinstance(_e, dict) or _e.get("name") not in SLOW_FORENSIC_EVENT_NAMES:
            continue
        _pm = _num((_e.get("metadata") or {}).get("probe_wall_ms"))
        if _pm is not None:
            _probe_sum += _pm
    return _probe_sum if _probe_sum > 0 else None


def _telemetry_overhead_ms(artifact: dict) -> float | None:
    """Total probe wall ms: explicit aggregate first, else the summed
    probe_wall_ms over ALL host probe events."""
    _result = artifact.get("result") or {}
    if not isinstance(_result, dict):
        _result = {}
    _total = _num(_first_value(
        _deep_get(_result, "host_telemetry_total_probe_wall_ms",
                  "resource_telemetry.host_telemetry_total_probe_wall_ms",
                  "trace.metadata.host_telemetry_total_probe_wall_ms"),
    ))
    if _total is not None:
        return _total
    _probe_sum = 0.0
    _any_probe = False
    for _name in HOST_PROBE_EVENT_NAMES:
        for _e in _events(_result):
            if not isinstance(_e, dict) or _e.get("name") != _name:
                continue
            _pm = _num((_e.get("metadata") or {}).get("probe_wall_ms"))
            if _pm is not None:
                _probe_sum += _pm
                _any_probe = True
    return _probe_sum if _any_probe else None


def _tier_a_overhead_ms(artifact: dict) -> float | None:
    """Tier-A overhead: explicit Tier-A aggregate, else total minus the
    Tier-B slow probe, else the summed probe_wall_ms over Tier-A host probe
    events.  Returns None when Tier A cannot be distinguished."""
    _result = artifact.get("result") or {}
    if not isinstance(_result, dict):
        _result = {}
    _explicit_tier_a = _num(_first_value(
        _deep_get(_result, "host_telemetry_tier_a_ms",
                  "_restore_timing.host_telemetry_tier_a_ms",
                  "trace.metadata.host_telemetry_tier_a_ms"),
        _deep_get(_result, "tier_a_ms",
                  "_restore_timing.tier_a_ms",
                  "trace.metadata.tier_a_ms"),
        _deep_get(_result, "host_telemetry_tier_a_probe_wall_ms",
                  "_restore_timing.host_telemetry_tier_a_probe_wall_ms",
                  "trace.metadata.host_telemetry_tier_a_probe_wall_ms"),
    ))
    if _explicit_tier_a is not None:
        return _explicit_tier_a
    _total = _telemetry_overhead_ms(artifact)
    if _total is not None:
        _slow_probe = _slow_trigger_probe_ms(artifact)
        if _slow_probe is not None:
            # The only aggregate includes the slow probe: subtract it.
            return _total - _slow_probe if _total >= _slow_probe else _total
        return None  # resolved by the caller using run health
    _tier_a_sum = 0.0
    _any = False
    for _name in TIER_A_HOST_PROBE_EVENT_NAMES:
        for _e in _events(_result):
            if not isinstance(_e, dict) or _e.get("name") != _name:
                continue
            _pm = _num((_e.get("metadata") or {}).get("probe_wall_ms"))
            if _pm is not None:
                _tier_a_sum += _pm
                _any = True
    return _tier_a_sum if _any else None


# ── Validator ────────────────────────────────────────────────────────────
def validate_batch_b(
    artifact: dict,
    *,
    expect_runtime_state_skip: bool,
    snapshot_hygiene_enabled: bool,
    snapshot_manifest_enabled: bool,
    stage13_tolerance_ms: float | None = None,
    expect_stage13: bool = False,
    expect_slow_h2d_forensic: bool = False,
) -> BatchBAcceptanceResult:
    if not isinstance(artifact, dict):
        artifact = {}
    if stage13_tolerance_ms is None:
        stage13_tolerance_ms = STAGE13_TOLERANCE_MS
    checks: list[GateCheck] = []
    _result = artifact.get("result") or {}
    if not isinstance(_result, dict):
        _result = {}

    # ── Gate 1: Batch-A preserved (reused; telemetry checks re-evaluated) ─
    # Every Batch-A invariant is preserved EXCEPT the two host-telemetry
    # checks, which are re-evaluated by the Batch-B Tier-A/Tier-B telemetry
    # and slow-H2D forensic contract below (a legitimately slow H2D with a
    # forensic event must never fail structural Batch-B acceptance).
    _bga = validate_batch_a(artifact)
    _bga_remaining = [
        c for c in _bga.checks if c.key not in _BATCH_A_TELEMETRY_CHECK_KEYS
    ]
    batch_a_preserved = all(c.ok for c in _bga_remaining)
    batch_a_detail = (
        f"validate_batch_a preserved {sum(1 for c in _bga_remaining if c.ok)}/"
        f"{len(_bga_remaining)} non-telemetry checks; "
        f"fresh={_bga.fresh}, "
        f"reconciliation_ms={_bga.reconciliation_ms if _bga.reconciliation_ms is not None else 'n/a'} "
        f"(hard cap {RECONCILIATION_HARD_MS:g} ms); "
        "host_telemetry_overhead/host_slow_forensic re-evaluated under the "
        "Batch-B Tier-A/Tier-B contract"
    )
    checks.append(
        GateCheck("batch_a_preserved", batch_a_preserved, batch_a_preserved,
                  batch_a_detail)
    )

    # ── Gate 2: runtime-state guard (runtime-state evidence ONLY) ─────────
    _rt = _runtime_state_observables(artifact)
    runtime_state_ok = True
    runtime_state_detail = _rt["local_only_evidence"]
    if not expect_runtime_state_skip:
        runtime_state_detail = (
            "expectation OFF (COMFYMODAL_V2_BATCH_B_EXPECT_RUNTIME_STATE_SKIP "
            "unset): runtime-state state reported (or NOT READY), reload is "
            "permitted - never fails"
        )
    elif not _rt["ready"]:
        runtime_state_ok = False
        runtime_state_detail = (
            "runtime-state lane NOT READY: no runtime-state-specific "
            "decision/invoked/reload-ms/generation-check observable anywhere "
            "(models-volume evidence is NEVER runtime-state evidence) - "
            "expected skipped_generation_match skip is missing"
        )
    else:
        _problems = []
        if _rt["decision"] != "skipped_generation_match":
            _problems.append(
                f"decision={_rt['decision']!r} != skipped_generation_match"
            )
        if _rt["invoked"] is not False:
            _problems.append(
                f"invoked={_rt['invoked']!r} (expected False; source: "
                f"{_rt['invoked_source']})"
            )
        _reload_ok = (
            _rt["reload_ms"] is None
            or _rt["reload_ms"] <= 0.0
            or (
                _rt["invoked"] is False
                and _rt["generation_check"] is True
                and _rt["reload_ms"] <= LOCAL_CHECK_BUDGET_MS
            )
        )
        if not _reload_ok:
            _problems.append(
                f"reload_runtime_state_ms={_rt['reload_ms']!r} "
                "is neither 0 nor local-check-only "
                f"(local check budget {LOCAL_CHECK_BUDGET_MS:g} ms)"
            )
        if _rt["generation_check"] is not True:
            _problems.append("generation check missing/not present")
        if _rt["local_only"] is not True:
            _problems.append(
                f"generation check is not local: {_rt['local_only_evidence']}"
            )
        if _problems:
            runtime_state_ok = False
        runtime_state_detail = (
            f"evidence={_rt['evidence']!r}, "
            f"decision={_rt['decision']!r}, invoked={_rt['invoked']!r} "
            f"(source: {_rt['invoked_source']}), "
            f"reload_ms={_rt['reload_ms']!r}, "
            f"generation_check={_rt['generation_check']!r}, "
            f"local_only={_rt['local_only']!r} ({_rt['local_only_evidence']})"
        ) + (f"; FAILED: {'; '.join(_problems)}" if _problems else "")
    checks.append(
        GateCheck("runtime_state_guard", runtime_state_ok, None,
                  runtime_state_detail)
    )

    # ── Gate 3: snapshot hygiene ─────────────────────────────────────────
    hygiene_ok = True
    hygiene_detail = "flag off - not enforced"
    hygiene_present = False
    rss_before = rss_after = rss_anon_before = rss_anon_after = None
    hygiene_wall_ms = hygiene_gc = hygiene_malloc_trim = None
    _hygiene = _snapshot_hygiene_record(artifact)
    if snapshot_hygiene_enabled:
        if _hygiene is None:
            hygiene_ok = False
            hygiene_present = False
            hygiene_detail = (
                "COMFYMODAL_V2_SNAPSHOT_ALLOCATOR_HYGIENE=1 but no "
                "snapshot_capture_hygiene record/event observable anywhere"
            )
        else:
            hygiene_present = True
            _problems = []
            _hygiene_enabled = _hygiene.get("enabled")
            if _hygiene_enabled is not None and not _boolish(_hygiene_enabled):
                _problems.append(f"record enabled={_hygiene_enabled!r} != 1")
            rss_before = _num(_first_value(
                _hygiene.get("rss_before"), _hygiene.get("before"),
                _hygiene.get("rss_mb_before"), _hygiene.get("rss_kb_before"),
                _hygiene.get("before_rss_kb"),
            ))
            if rss_before is None:
                _problems.append("before RSS measurement missing")
            rss_after = _num(_first_value(
                _hygiene.get("rss_after"), _hygiene.get("after"),
                _hygiene.get("rss_mb_after"), _hygiene.get("rss_kb_after"),
                _hygiene.get("after_rss_kb"),
            ))
            if rss_after is None:
                _problems.append("after RSS measurement missing")
            hygiene_wall_ms = _num(_hygiene.get("hygiene_wall_ms"))
            if hygiene_wall_ms is None or hygiene_wall_ms < 0:
                _problems.append(
                    f"hygiene_wall_ms={hygiene_wall_ms!r} not a valid "
                    "nonnegative duration"
                )
            hygiene_gc = _first_value(
                _hygiene.get("gc"), _hygiene.get("gc_result"),
                _hygiene.get("gc_collected"),
            )
            if hygiene_gc is None:
                _problems.append("gc result missing")
            hygiene_malloc_trim = _first_value(
                _hygiene.get("malloc_trim"), _hygiene.get("malloc_trim_status"),
                _hygiene.get("malloc_trim_result"),
                _hygiene.get("malloc_trim_available"),
            )
            if hygiene_malloc_trim is None:
                _problems.append("malloc_trim status/result missing")
            rss_anon_before = _num(_first_value(
                _hygiene.get("rss_anon_before"),
                _hygiene.get("before_rss_anon_kb"),
            ))
            rss_anon_after = _num(_first_value(
                _hygiene.get("rss_anon_after"),
                _hygiene.get("after_rss_anon_kb"),
            ))
            hygiene_detail = (
                f"rss_before={rss_before!r}, rss_after={rss_after!r}, "
                f"hygiene_wall_ms={hygiene_wall_ms!r}, "
                f"gc={'present' if hygiene_gc is not None else 'absent'}, "
                f"malloc_trim={hygiene_malloc_trim!r}"
            )
            if _problems:
                hygiene_ok = False
                hygiene_detail += "; FAILED: " + "; ".join(_problems)
    checks.append(
        GateCheck("snapshot_hygiene", hygiene_ok, None, hygiene_detail)
    )
    rss_delta = (
        (rss_after - rss_before)
        if rss_before is not None and rss_after is not None
        else None
    )
    rss_anon_delta = (
        (rss_anon_after - rss_anon_before)
        if rss_anon_before is not None and rss_anon_after is not None
        else None
    )

    # ── Gate 4: snapshot manifest ────────────────────────────────────────
    manifest_ok = True
    manifest_detail = "flag off - not enforced"
    manifest_present = False
    manifest_status: Any = None
    manifest_smaps_unavailable: bool | None = None
    _manifest = _snapshot_manifest(artifact)
    if snapshot_manifest_enabled:
        if _manifest is None:
            manifest_ok = False
            manifest_present = False
            manifest_detail = (
                "COMFYMODAL_V2_SNAPSHOT_MANIFEST=1 but no snapshot manifest "
                "status/result observable anywhere (instrumentation silently "
                "omits status)"
            )
        else:
            manifest_present = True
            manifest_status = _first_value(
                _manifest.get("status"), _manifest.get("result"),
                _manifest.get("manifest_status"), _manifest.get("manifest_result"),
            )
            _smaps = _manifest.get("smaps_rollup")
            _smaps_status = _manifest.get("smaps_status")
            _smaps_unavailable = _manifest.get("smaps_unavailable")
            manifest_smaps_unavailable = (
                _smaps_status == "unavailable"
                or _boolish(_smaps_unavailable)
                or (isinstance(manifest_status, str)
                    and "unavailable" in manifest_status.lower())
                or (isinstance(manifest_status, dict)
                    and _boolish(manifest_status.get("smaps_unavailable")))
            )
            if manifest_status is None:
                manifest_ok = False
                manifest_detail = (
                    "snapshot manifest present but no status/result key "
                    "(instrumentation silently omits status)"
                )
            else:
                if _smaps is None and not manifest_smaps_unavailable:
                    manifest_detail = (
                        f"manifest status={manifest_status!r}; smaps/anonymous "
                        "split absent WITHOUT an explicit 'unavailable' "
                        "marker (informational, not a gate failure)"
                    )
                elif manifest_smaps_unavailable:
                    manifest_detail = (
                        f"manifest status={manifest_status!r}; smaps/anonymous "
                        "split explicitly recorded unavailable (gVisor-blocked "
                        "field, allowed)"
                    )
                else:
                    manifest_detail = (
                        f"manifest status={manifest_status!r} with smaps_rollup "
                        "present"
                    )
    checks.append(
        GateCheck("snapshot_manifest", manifest_ok, None, manifest_detail)
    )

    # ── Gate 5: stage-13 decomposition ───────────────────────────────────
    stage13_ok = True
    stage13_ready = False
    stage13_total: float | None = None
    stage13_children: list[dict[str, Any]] = []
    stage13_largest_child: dict[str, Any] | None = None
    stage13_reconciliation_ms: float | None = None
    _s13 = _stage13_breakdown(artifact)
    if _s13 is None:
        if expect_stage13:
            stage13_ok = False
            stage13_detail = (
                "COMFYMODAL_V2_BATCH_B_EXPECT_STAGE13=1 but no "
                "output_stage13_breakdown or runtime equivalent observable "
                "(stage-13 decomposition is a required Batch-B lane)"
            )
        else:
            stage13_detail = (
                "stage-13 breakdown NOT READY: no output_stage13_breakdown or "
                "runtime equivalent observable (reported; expectation flag "
                "off)"
            )
    else:
        stage13_ready = True
        _problems = []
        stage13_total = _num(_first_value(
            _s13.get("stage13_total_ms"), _s13.get("stage13_total"),
            _s13.get("total_ms"), _s13.get("total"),
        ))
        if stage13_total is None or stage13_total < 0:
            _problems.append(
                f"stage13_total={stage13_total!r} not a valid nonnegative value"
            )
        _raw_children = _s13.get("children")
        _children_order = _s13.get("children_order")
        if not isinstance(_raw_children, list):
            # Runtime spelling: the breakdown is a flat dict keyed
            # ``{child_name}_ms`` with ``children_order`` naming the eight
            # children (result key ``output_stage13_breakdown``).  The runtime
            # emits children_order entries that already END in ``_ms``, so each
            # entry is used as-is via ``_stage13_child_key`` (the fallback
            # child names get the suffix appended).  Names whose flat value is
            # absent are skipped.  Fall back to the eight known child names
            # when no children_order is present.
            _child_names: list[str] = []
            if isinstance(_children_order, list) and _children_order:
                _child_names = [
                    _name for _name in _children_order
                    if _num(_s13.get(_stage13_child_key(_name))) is not None
                ]
            else:
                _child_names = [
                    _name for _name in STAGE13_CHILD_NAMES
                    if _num(_s13.get(_stage13_child_key(_name))) is not None
                ]
            for _child_name in _child_names:
                _child_ms = _num(_s13.get(_stage13_child_key(_child_name)))
                if _child_ms is None or _child_ms < 0:
                    _problems.append(
                        f"child {_child_name!r} has invalid/negative "
                        f"duration ({_child_ms!r})"
                    )
                    _child_ms = 0.0
                stage13_children.append(
                    {"name": _child_name, "ms": _child_ms, "_ms": _child_ms}
                )
            if not stage13_children:
                _problems.append("children list missing")
        else:
            for _child in _raw_children:
                if not isinstance(_child, dict):
                    _problems.append("child record is not a dict")
                    continue
                _child_ms = _num(_first_value(
                    _child.get("ms"), _child.get("duration_ms"),
                    _child.get("wall_ms"), _child.get("value"),
                ))
                if _child_ms is None or _child_ms < 0:
                    _problems.append(
                        f"child {_child.get('name', '?')!r} has invalid/"
                        f"negative duration ({_child_ms!r})"
                    )
                    _child_ms = 0.0
                _child["_ms"] = _child_ms
                stage13_children.append(_child)
        _children_sum = sum(
            float(c.get("_ms", 0.0)) for c in stage13_children
        )
        if stage13_total is not None:
            stage13_reconciliation_ms = abs(_children_sum - stage13_total)
            if stage13_reconciliation_ms > stage13_tolerance_ms:
                _problems.append(
                    f"sum(children)={_children_sum:g} does not reconcile "
                    f"stage13_total={stage13_total:g} "
                    f"(delta {stage13_reconciliation_ms:g} ms > tolerance "
                    f"{stage13_tolerance_ms:g} ms)"
                )
        if stage13_children:
            stage13_largest_child = max(
                stage13_children, key=lambda c: float(c.get("_ms", 0.0))
            )
        stage13_detail = (
            f"total={stage13_total!r}, children={len(stage13_children)}, "
            f"sum(children)={_children_sum:g}, "
            f"largest_child="
            f"{stage13_largest_child.get('name', '?') if stage13_largest_child else 'n/a'}"
            f"={stage13_largest_child.get('_ms', 0.0):g} ms, "
            if stage13_largest_child
            else "largest_child=n/a, "
            f"reconciliation={stage13_reconciliation_ms if stage13_reconciliation_ms is not None else 'n/a'} ms"
        )
        if _problems:
            stage13_ok = False
            stage13_detail += "; FAILED: " + "; ".join(_problems)
    checks.append(
        GateCheck("stage13_breakdown", stage13_ok, None, stage13_detail)
    )

    # ── Stage-13 boundaries hygiene (informational, NON-GATING) ───────────
    # The private _stage13_boundaries key must NEVER survive into the final
    # yielded result (modal_app pops it before emitting the event).  Its
    # presence anywhere in the artifact result / trace events is a
    # malformed-state signal: the check FAILS, but it does not flip the
    # overall acceptance verdict (informational, non-gating).
    _boundaries_present = (
        _first_value(
            _deep_get(_result, "_stage13_boundaries"),
            _deep_get(_result, "_restore_timing._stage13_boundaries"),
            _deep_get(_result, "trace.metadata._stage13_boundaries"),
        )
        is not None
        or any(
            isinstance(_e, dict)
            and (
                _e.get("name") == "_stage13_boundaries"
                or (
                    isinstance(_e.get("metadata"), dict)
                    and "_stage13_boundaries" in _e["metadata"]
                )
            )
            for _e in _events(_result)
        )
    )
    checks.append(
        GateCheck(
            "stage13_boundaries_absence",
            not _boundaries_present,
            _boundaries_present,
            (
                "OK: _stage13_boundaries absent from the artifact result "
                "(runtime pops it before emitting the event)"
                if not _boundaries_present
                else "FAIL: _stage13_boundaries survived into the artifact "
                "result (malformed-state signal; runtime must pop it before "
                "emitting the event)"
            ),
        )
    )

    # ── Gate 6: host telemetry (Tier A / Tier B split) + forensic rule ────
    _h2d_durations = _h2d_durations_ms(artifact)
    _h2d_max = max(_h2d_durations) if _h2d_durations else None
    _h2d_slow = _h2d_max is not None and _h2d_max >= SLOW_H2D_THRESHOLD_MS

    total_ms = _telemetry_overhead_ms(artifact)
    slow_probe_ms = _slow_trigger_probe_ms(artifact)
    tier_a_ms = _tier_a_overhead_ms(artifact)

    host_telemetry_not_observable = False
    if _h2d_slow:
        # Slow H2D: Tier-A <= 20 ms required; the Tier-B forensic cost is
        # separate and the total may legitimately exceed 20 ms.  When the
        # decomposition cannot distinguish Tier A from Tier B, report NOT
        # OBSERVABLE rather than falsely failing on the total.
        if tier_a_ms is None:
            host_telemetry_not_observable = True
            host_telemetry_ok = True
            host_telemetry_detail = (
                "telemetry-overhead gate NOT OBSERVABLE: slow H2D "
                f"({_h2d_max:g} ms >= {SLOW_H2D_THRESHOLD_MS:g} ms) but the "
                "decomposition cannot separate Tier-A overhead from the "
                "Tier-B slow-trigger forensic probe"
            )
        else:
            host_telemetry_ok = tier_a_ms <= HOST_TELEMETRY_MAX_PROBE_WALL_MS
            host_telemetry_detail = (
                f"Tier-A overhead={tier_a_ms:g} ms vs hard cap "
                f"{HOST_TELEMETRY_MAX_PROBE_WALL_MS:g} ms on slow H2D "
                f"({_h2d_max:g} ms); Tier-B forensic probe "
                f"{slow_probe_ms if slow_probe_ms is not None else 0.0:g} ms "
                f"reported separately; total probe {total_ms if total_ms is not None else 'n/a'} ms "
                "may exceed the cap"
            )
    else:
        # Healthy H2D: Tier-A <= 20 ms AND the slow-trigger probe must be 0.
        if tier_a_ms is None and total_ms is not None:
            tier_a_ms = total_ms  # no Tier-B possible on a healthy run
        _slow_ok = slow_probe_ms is None or slow_probe_ms <= 0.0
        host_telemetry_not_observable = tier_a_ms is None
        host_telemetry_ok = (
            tier_a_ms is not None
            and tier_a_ms <= HOST_TELEMETRY_MAX_PROBE_WALL_MS
            and _slow_ok
        )
        host_telemetry_detail = (
            f"Tier-A overhead={tier_a_ms if tier_a_ms is not None else 'n/a'} ms "
            f"vs hard cap {HOST_TELEMETRY_MAX_PROBE_WALL_MS:g} ms on healthy "
            f"H2D ({_h2d_max if _h2d_max is not None else 'n/a'} ms); "
            f"slow-trigger probe={slow_probe_ms if slow_probe_ms is not None else 0.0:g} ms "
            "(must be 0 on healthy)"
        )
        if host_telemetry_not_observable:
            host_telemetry_ok = False
            host_telemetry_detail = (
                "host telemetry overhead not observable on a healthy run "
                "(no Tier-A evidence anywhere)"
            )
    checks.append(
        GateCheck("host_telemetry_overhead", host_telemetry_ok, tier_a_ms,
                  host_telemetry_detail)
    )

    slow_forensic_triggered = (
        _count_events(_result, SLOW_FORENSIC_EVENT_NAMES[0]) > 0
    )
    slow_forensic_expected_missing: bool | None = None
    if slow_forensic_triggered:
        slow_forensic_ok = _h2d_slow
        slow_forensic_detail = (
            f"host_forensic_slow_h2d event present; h2d max "
            f"{_h2d_max if _h2d_max is not None else 'n/a'} ms vs slow "
            f"threshold {SLOW_H2D_THRESHOLD_MS:g} ms "
            f"({'expected on slow H2D' if _h2d_slow else 'unexpected on healthy H2D'})"
        )
    else:
        if _h2d_slow and expect_slow_h2d_forensic:
            slow_forensic_ok = False
            slow_forensic_expected_missing = True
            slow_forensic_detail = (
                "no host_forensic_slow_h2d event on slow H2D "
                f"({_h2d_max:g} ms >= {SLOW_H2D_THRESHOLD_MS:g} ms) while "
                "COMFYMODAL_V2_BATCH_B_EXPECT_SLOW_H2D_FORENSIC=1 "
                "(slow-trigger runtime expected enabled/observable)"
            )
        else:
            slow_forensic_ok = True
            slow_forensic_expected_missing = (
                False if _h2d_slow else None
            )
            slow_forensic_detail = (
                "no host_forensic_slow_h2d event present"
                + (f"; slow H2D {_h2d_max:g} ms without forensic event "
                   "(trigger not expected/observable - reported, not a failure)"
                   if _h2d_slow else "")
            )
    checks.append(
        GateCheck("host_slow_forensic", slow_forensic_ok,
                  slow_forensic_triggered, slow_forensic_detail)
    )

    # ── Informational: TOTAL WALL (never a gate) ─────────────────────────
    total_wall_ms = _num(_first_value(
        (artifact.get("timing") or {}).get("wall_ms"),
        _deep_get(artifact, "waterfall_local.total_wall_ms"),
        _deep_get(artifact, "waterfall.total_wall_ms"),
        _deep_get(artifact, "waterfall_local.production_adjusted_total_wall_ms"),
        _deep_get(artifact, "waterfall.production_adjusted_total_wall_ms"),
        artifact.get("production_adjusted_total_wall_ms"),
    ))

    passed = all(
        c.ok for c in checks if c.key != "stage13_boundaries_absence"
    )

    return BatchBAcceptanceResult(
        batch_a_preserved=batch_a_preserved,
        batch_a_fresh=_bga.fresh,
        batch_a_reconciliation_ms=_bga.reconciliation_ms,
        batch_a_detail=batch_a_detail,
        runtime_state_expectation=expect_runtime_state_skip,
        runtime_state_ready=_rt["ready"],
        runtime_state_evidence=_rt["evidence"],
        runtime_state_decision=_rt["decision"],
        runtime_state_invoked=_rt["invoked"],
        runtime_state_reload_ms=_rt["reload_ms"],
        runtime_state_generation_check=_rt["generation_check"],
        runtime_state_local_only=_rt["local_only"],
        runtime_state_ok=runtime_state_ok,
        snapshot_hygiene_enabled=snapshot_hygiene_enabled,
        snapshot_hygiene_present=hygiene_present,
        hygiene_rss_before=rss_before,
        hygiene_rss_after=rss_after,
        hygiene_rss_delta=rss_delta,
        hygiene_rss_anon_before=rss_anon_before,
        hygiene_rss_anon_after=rss_anon_after,
        hygiene_rss_anon_delta=rss_anon_delta,
        hygiene_wall_ms=hygiene_wall_ms,
        hygiene_gc=hygiene_gc,
        hygiene_malloc_trim=hygiene_malloc_trim,
        hygiene_ok=hygiene_ok,
        snapshot_manifest_enabled=snapshot_manifest_enabled,
        snapshot_manifest_present=manifest_present,
        manifest_status=manifest_status,
        manifest_smaps_unavailable=manifest_smaps_unavailable,
        manifest_ok=manifest_ok,
        stage13_expectation=expect_stage13,
        stage13_ready=stage13_ready,
        stage13_total=stage13_total,
        stage13_children=stage13_children,
        stage13_largest_child=stage13_largest_child,
        stage13_reconciliation_ms=stage13_reconciliation_ms,
        stage13_ok=stage13_ok,
        host_telemetry_tier_a_ms=tier_a_ms,
        host_telemetry_total_ms=total_ms,
        slow_trigger_probe_ms=slow_probe_ms,
        host_telemetry_not_observable=host_telemetry_not_observable,
        host_telemetry_ok=host_telemetry_ok,
        slow_forensic_triggered=slow_forensic_triggered,
        slow_forensic_expected_missing=slow_forensic_expected_missing,
        slow_forensic_expectation=expect_slow_h2d_forensic,
        slow_forensic_ok=slow_forensic_ok,
        total_wall_ms=total_wall_ms,
        checks=checks,
        passed=passed,
    )


# ── Offline file validation ──────────────────────────────────────────────
def validate_batch_b_file(
    run_json_path: str,
    *,
    expect_runtime_state_skip: bool | None = None,
    snapshot_hygiene_enabled: bool | None = None,
    snapshot_manifest_enabled: bool | None = None,
    expect_stage13: bool | None = None,
    expect_slow_h2d_forensic: bool | None = None,
) -> BatchBAcceptanceResult:
    """Load a persisted ``run_<i>.json`` artifact and validate it offline.

    Flag parameters default to the current environment (batch_b_config_from_env).
    """
    with open(run_json_path, "r", encoding="utf-8") as _fh:
        artifact = json.load(_fh)
    _cfg = batch_b_config_from_env()
    return validate_batch_b(
        artifact,
        expect_runtime_state_skip=(
            _cfg["expect_runtime_state_skip"]
            if expect_runtime_state_skip is None
            else expect_runtime_state_skip
        ),
        snapshot_hygiene_enabled=(
            _cfg["snapshot_hygiene_enabled"]
            if snapshot_hygiene_enabled is None
            else snapshot_hygiene_enabled
        ),
        snapshot_manifest_enabled=(
            _cfg["snapshot_manifest_enabled"]
            if snapshot_manifest_enabled is None
            else snapshot_manifest_enabled
        ),
        expect_stage13=(
            _cfg["expect_stage13"] if expect_stage13 is None else expect_stage13
        ),
        expect_slow_h2d_forensic=(
            _cfg["expect_slow_h2d_forensic"]
            if expect_slow_h2d_forensic is None
            else expect_slow_h2d_forensic
        ),
        stage13_tolerance_ms=_cfg["stage13_tolerance_ms"],
    )


# ── Rendering ────────────────────────────────────────────────────────────
def render_batch_b_block(res: BatchBAcceptanceResult) -> str:
    """Render the exact BATCH B ACCEPTANCE block.

    TOTAL WALL is explicitly marked as informational only.  On FAIL a compact
    'FAILED CHECKS:' list follows with one line per failing gate.
    """

    def _ms(v: float | None) -> str:
        return "n/a" if v is None else f"{v:.1f}"

    def _yn(v: bool | None) -> str:
        return "n/a" if v is None else ("YES" if v else "NO")

    def _val(v: Any) -> str:
        return "n/a" if v is None else str(v)

    _rt_ready = "READY" if res.runtime_state_ready else "NOT READY"
    _s13_ready = "READY" if res.stage13_ready else "NOT READY"

    lines = [
        "BATCH B ACCEPTANCE",
        "",
        "Batch A preserved:",
        f"{'PASS' if res.batch_a_preserved else 'FAIL'}",
        "",
        "Runtime-state guard:",
        f"lane: {_rt_ready}",
        f"expectation: {'1' if res.runtime_state_expectation else '0'}",
        f"evidence: {_val(res.runtime_state_evidence)}",
        f"decision: {_val(res.runtime_state_decision)}",
        f"invoked: {_yn(res.runtime_state_invoked)}",
        f"reload ms: {_ms(res.runtime_state_reload_ms)}",
        f"generation check: {_yn(res.runtime_state_generation_check)}",
        f"local only: {_yn(res.runtime_state_local_only)}",
        "",
        "Snapshot hygiene:",
        f"enabled: {'1' if res.snapshot_hygiene_enabled else '0'}",
        f"before RSS: {_val(res.hygiene_rss_before)}",
        f"after RSS: {_val(res.hygiene_rss_after)}",
        f"delta: {_val(res.hygiene_rss_delta)}",
        f"trim status: {_val(res.hygiene_malloc_trim)}",
        f"manifest status: {_val(res.manifest_status)}",
        "",
        "Stage 13:",
        f"gate: {_s13_ready}",
        f"expectation: {'1' if res.stage13_expectation else '0'}",
        f"total: {_ms(res.stage13_total)}",
        f"children: {len(res.stage13_children)}",
        f"largest child: "
        f"{_val(res.stage13_largest_child.get('name') if res.stage13_largest_child else None)}"
        f"={_ms(float(res.stage13_largest_child.get('_ms', 0.0))) if res.stage13_largest_child else 'n/a'}",
        f"reconciliation: {_ms(res.stage13_reconciliation_ms)}",
        "",
        "Host telemetry:",
        f"overhead (Tier A): {_ms(res.host_telemetry_tier_a_ms)}",
        f"Tier B forensic probe: {_ms(res.slow_trigger_probe_ms)}",
        f"total probe: {_ms(res.host_telemetry_total_ms)}",
        f"forensic trigger: {'YES' if res.slow_forensic_triggered else 'NO'}",
        "",
        f"TOTAL WALL: {_ms(res.total_wall_ms)} (informational only)",
        "",
        "TOTAL WALL NOT AN ACCEPTANCE GATE",
        "",
        f"OVERALL: {'PASS' if res.passed else 'FAIL'}",
    ]
    if not res.passed:
        lines.append("")
        lines.append("FAILED CHECKS:")
        for _c in res.checks:
            if not _c.ok:
                lines.append(f"  {_c.key}: {_c.detail}")
    return "\n".join(lines)
