"""Batch-C acceptance harness validator (Batch C2 - plan fast-path lane).

Pure, offline validation wrapper for the strict Batch-C fast-path acceptance
gates.  Batch-C WRAPS ``tools/batch_b_acceptance.validate_batch_b`` (imported
and reused, never duplicated, never re-implemented) and adds an OPTIONAL
strict fast-path expectation flag::

    COMFYMODAL_V2_BATCH_C_EXPECT_PLAN_FAST_PATH=1

When the flag is ON every fast-path observable must be present (NOT READY is a
fail-closed FAIL) and must agree with the plan-validation fast-path contract.
When the flag is OFF the fast-path gates are reported only and never fail the
run (the run degrades to a report-only verification of the fast-path lane).

It consumes the same single run artifact dict shape as
``tools/batch_a_acceptance.py`` / ``tools/batch_b_acceptance.py`` (the
``run_<i>.json`` files persisted by ``benchmark_v2_direct.py``).  This module
NEVER executes Modal, never imports the repo runtime, never spawns processes
and never touches the network: it is a pure dict-in/dict-out validator (stdlib
plus imports of ``tools.batch_a_acceptance`` / ``tools.batch_b_acceptance``
only).

Source of truth - runtime-emitted evidence
------------------------------------------
All evidence lives as trace events in ``artifact["result"]["trace"]["events"]``
(each event ``{"name": ..., "phase": ..., "metadata": {...}}``) plus
record-style fallbacks at the result top level / ``result._restore_timing`` /
``result.trace.metadata`` (the same record resolution
``batch_b_acceptance._snapshot_manifest`` uses).  The authoritative runtime
emission sites (modal_app.py) and contract (comfymodal_runtime/contracts.py):

1.  ``plan_snapshot_parity`` (phase="setup", modal_app.py:12242, contract
    contracts.py:677-742): metadata ``snapshot_proof_present`` /
    ``snapshot_proof_complete`` / ``snapshot_proof_valid`` /
    ``plan_deployment_complete`` / ``deployment_hash_match`` /
    ``custom_nodes_generation_match`` / ``workflow_registry_match`` /
    ``registry_fingerprint_match`` / ``dependency_proof_match`` /
    ``future_fast_path_eligible`` /
    ``future_fast_path_ineligible_reason`` (comma-joined reasons).
2.  ``plan_proof_decision`` (phase="setup", modal_app.py:12897-12901):
    metadata ``consumed`` (bool), ``decision``
    (``"plan_validation_fast_path"`` | ``"legacy_validation_fallback"``),
    ``reason`` (the ineligible reason string).
3.  ``certificate_read_outcome`` - fast-path spelling (phase="setup",
    modal_app.py:12347-12350): ``cert_source="plan_validation"``,
    ``cert_decision="plan_validation_fast_path"``, ``hit=True``,
    ``preflight_skip=True``, ``consumed=True``.  Legacy/cert spellings
    (phase="execution", modal_app.py:12629-12652): ``cert_source`` in
    {snapshot_memory, process_cache, volume}, ``cert_decision`` in
    {snapshot_exact_reuse, cache_reuse, volume_read} plus ``cert_identity``,
    ``cert_cache_hit``, ``cert_volume_reload_ms``, ``cert_file_read_ms``,
    ``cert_json_parse_validate_ms``, ``cert_total_ms``.  An outcome with
    ``cert_decision=="volume_read"`` or ``cert_source=="volume"`` is the
    volume fallback.
4.  ``certificate_reload_start`` / ``certificate_reload_end``
    (phase="execution", modal_app.py:12567-12625): real volume reload markers;
    presence = volume fallback.
5.  ``prompt_validation_end`` (phase="execution", modal_app.py:12849-12872):
    metadata ``valid`` / ``output_count`` / ``cert_hit`` / ``preflight_skip`` /
    ``preflight_ran`` / ``cert_volume_reload_ms`` / ``cert_total_ms`` /
    ``legacy_preflight_ms`` / ``prompt_validation_ms`` (informational).
6.  ``plan_validation_payload`` (phase="setup"): step-1 instrumentation with
    ``consumed=False``; informational only, never gated.

The motivating run printed Batch-B ``OVERALL: PASS`` while the campaign
evidence check invalidated it: ``plan_proof_decision.decision ==
"legacy_validation_fallback"``, ``consumed == False`` and
``certificate_read_outcome cert_source=="volume"`` /
``cert_decision=="volume_read"``.  Batch-C exists to catch exactly this: the
Batch-B structural gates cannot see the fast-path lane, so Batch-C adds the
eight fast-path gates below and fails closed on missing evidence.

Batch-C gates (each a GateCheck):

1.  fast_path_parity_eligible - ``plan_snapshot_parity.future_fast_path_eligible``
    must be True.
2.  fast_path_decision - ``plan_proof_decision.decision`` must be
    ``"plan_validation_fast_path"``.
3.  fast_path_consumed - ``plan_proof_decision.consumed`` must be True
    (normalized via ``_boolish``); a ``certificate_read_outcome`` with
    ``cert_source=="plan_validation"`` and ``consumed=False`` is a conflict and
    fails the gate (primary gate vs cert contract disagree).
4.  no_legacy_validation_fallback - no ``plan_proof_decision`` with
    ``decision=="legacy_validation_fallback"`` (ready when the decision key is
    present).
5.  no_cert_volume_read_fallback - no ``certificate_read_outcome`` with
    ``cert_decision=="volume_read"`` or ``cert_source=="volume"`` AND no
    ``certificate_reload_start``/``certificate_reload_end`` events (ready when
    at least one certificate_read_outcome exists or any certificate_reload
    event exists).
6.  deployment_hash_match - ``plan_snapshot_parity.deployment_hash_match``
    must be True.
7.  custom_nodes_generation_match -
    ``plan_snapshot_parity.custom_nodes_generation_match`` must be True.
8.  dependency_proof_match - ``plan_snapshot_parity.dependency_proof_match``
    must be True.

Expectation semantics (copied from the Batch-B gate-2/5 pattern):

- expectation ON: a gate is ``ok=False`` when NOT READY (detail
  ``NOT READY: no <observable> anywhere - fail closed, evidence must not be
  inferred``) or when the evidence contradicts the fast-path contract.
- expectation OFF: every fast-path gate is ``ok=True`` with detail
  ``expectation OFF (COMFYMODAL_V2_BATCH_C_EXPECT_PLAN_FAST_PATH unset):
  <observed or NOT READY> - reported only, never fails``.  The observed values
  are still filled into the result fields.

Fallback diagnosis (the "important distinction"): when
``plan_proof_decision.decision == "legacy_validation_fallback"`` (or
``consumed`` is False) the reason string is keyword-scanned into:
``identity_transition`` (plan/snapshot identity incomplete or brand-new -
contains any of ``plan_identity_incomplete``, ``snapshot_proof_incomplete``,
``snapshot_proof_invalid_or_unsupported``, ``deployment_hash_mismatch``,
``snapshot_state_unavailable``, ``identity_mismatch``); ``repair`` (contains
``repair_changed`` or ``repair``); ``mismatch`` (component parity mismatch -
contains any of ``custom_nodes_generation_mismatch``,
``dependency_proof_mismatch``, ``workflow_registry_mismatch``,
``registry_fingerprint_mismatch``, ``validation_hash_mismatch``,
``workflow_hash_mismatch``); else ``unknown``.  Identity-transition wins over
mismatch: a brand-new snapshot/deployment identity is diagnosable and distinct
from a component parity mismatch even when both keyword classes appear.

TOTAL WALL is never an acceptance gate: it is reported as informational only
and explicitly marked "TOTAL WALL NOT AN ACCEPTANCE GATE".
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any

# Batch-A helpers are reused, never duplicated (the same import pattern
# tools/batch_b_acceptance.py uses).
from tools.batch_a_acceptance import (
    _boolish,
    _deep_get,
    _events,
    _num,
)
# Batch-B core is reused, never duplicated: Batch-C wraps validate_batch_b.
from tools.batch_b_acceptance import (
    GateCheck,
    _env_truthy,
    _first_value,
    batch_b_config_from_env,
    validate_batch_b,
    validate_batch_b_file,
)

# ── Canonical runtime event / field names (current checkout) ─────────────
PLAN_SNAPSHOT_PARITY_EVENT = "plan_snapshot_parity"
PLAN_PROOF_DECISION_EVENT = "plan_proof_decision"
CERTIFICATE_READ_OUTCOME_EVENT = "certificate_read_outcome"
CERTIFICATE_RELOAD_EVENT_NAMES = ("certificate_reload_start", "certificate_reload_end")
# Informational observables (never gated).
PROMPT_VALIDATION_END_EVENT = "prompt_validation_end"
PLAN_VALIDATION_PAYLOAD_EVENT = "plan_validation_payload"

FAST_PATH_DECISION = "plan_validation_fast_path"
LEGACY_FALLBACK_DECISION = "legacy_validation_fallback"

# ── Fallback reason classification keyword sets ──────────────────────────
# identity_transition: the plan/snapshot identity is incomplete or brand-new
# (a new snapshot/deployment identity legitimately cannot reuse the previous
# validation).  Scanned FIRST so a mixed reason string classifies as
# identity_transition, never as mismatch.
IDENTITY_TRANSITION_KEYWORDS = frozenset({
    "plan_identity_incomplete",
    "snapshot_proof_incomplete",
    "snapshot_proof_invalid_or_unsupported",
    "deployment_hash_mismatch",
    "snapshot_state_unavailable",
    "identity_mismatch",
})
REPAIR_KEYWORDS = frozenset({"repair_changed", "repair"})
MISMATCH_KEYWORDS = frozenset({
    "custom_nodes_generation_mismatch",
    "dependency_proof_mismatch",
    "workflow_registry_mismatch",
    "registry_fingerprint_mismatch",
    "validation_hash_mismatch",
    "workflow_hash_mismatch",
})

# The eight fast-path gate keys.
FAST_PATH_GATE_KEYS = (
    "fast_path_parity_eligible",
    "fast_path_decision",
    "fast_path_consumed",
    "no_legacy_validation_fallback",
    "no_cert_volume_read_fallback",
    "deployment_hash_match",
    "custom_nodes_generation_match",
    "dependency_proof_match",
)


# ── Small private helpers ────────────────────────────────────────────────
def _event_metas(result: dict, name: str) -> list[dict]:
    """All metadata dicts of trace events named *name* (any phase)."""
    metas: list[dict] = []
    for _e in _events(result):
        if not isinstance(_e, dict) or _e.get("name") != name:
            continue
        _m = _e.get("metadata")
        if isinstance(_m, dict):
            metas.append(_m)
    return metas


def _record_dicts(result: dict, name: str) -> list[dict]:
    """Record-style fallbacks for *name* at result / _restore_timing /
    trace.metadata (the same record resolution batch_b_acceptance uses for
    snapshot_manifest / snapshot_capture_hygiene)."""
    _records: list[dict] = []
    for _path in (name, f"_restore_timing.{name}", f"trace.metadata.{name}"):
        _r = _deep_get(result, _path)
        if isinstance(_r, dict) and _r:
            _records.append(_r)
    return _records


def _evidence_meta(result: dict, name: str, key: str) -> Any:
    """First non-None metadata[key] across trace events then record
    fallbacks.  Falsy-but-valid values (False/0/"") are values, not misses."""
    for _m in _event_metas(result, name):
        if _m.get(key) is not None:
            return _m[key]
    for _r in _record_dicts(result, name):
        if _r.get(key) is not None:
            return _r[key]
    return None


def _classify_fallback_reason(reason: str) -> str:
    """Keyword-scan a legacy-fallback reason string.

    identity_transition wins over mismatch: a brand-new snapshot/deployment
    identity (snapshot_proof_incomplete, deployment_hash_mismatch, ...) is
    diagnosable and distinct from a component parity mismatch even when both
    keyword classes appear in the comma-joined reason string.
    """
    if not reason:
        return "unknown"
    for _kw in IDENTITY_TRANSITION_KEYWORDS:
        if _kw in reason:
            return "identity_transition"
    for _kw in REPAIR_KEYWORDS:
        if _kw in reason:
            return "repair"
    for _kw in MISMATCH_KEYWORDS:
        if _kw in reason:
            return "mismatch"
    return "unknown"


# ── Fast-path observables ────────────────────────────────────────────────
def _resolve_fast_path_observables(artifact: dict) -> dict[str, Any]:
    """Resolve the fast-path observables ONLY from real evidence.

    Sources: event metadata (``plan_snapshot_parity`` / ``plan_proof_decision``
    / ``certificate_read_outcome`` trace events), then record-style fallbacks
    at result / result._restore_timing / result.trace.metadata.  Absence is
    NEVER inferred as success: every ``*_ready`` flag records whether the key
    was actually observable.
    """
    _result = artifact.get("result") or {}
    if not isinstance(_result, dict):
        _result = {}

    def _parity(key: str) -> Any:
        return _evidence_meta(_result, PLAN_SNAPSHOT_PARITY_EVENT, key)

    def _decision(key: str) -> Any:
        return _evidence_meta(_result, PLAN_PROOF_DECISION_EVENT, key)

    _eligible_raw = _parity("future_fast_path_eligible")
    _decision_raw = _decision("decision")
    _consumed_raw = _decision("consumed")
    _dep_hash_raw = _parity("deployment_hash_match")
    _gen_raw = _parity("custom_nodes_generation_match")
    _dep_proof_raw = _parity("dependency_proof_match")
    _reason_raw = _decision("reason")
    _ineligible_reason_raw = _parity("future_fast_path_ineligible_reason")

    # plan_proof_decision: all event metas + record fallbacks.
    _decision_all = (
        _event_metas(_result, PLAN_PROOF_DECISION_EVENT)
        + _record_dicts(_result, PLAN_PROOF_DECISION_EVENT)
    )
    _decision_key_present = any(
        isinstance(_m, dict) and _m.get("decision") is not None
        for _m in _decision_all
    )
    _legacy_outcomes = [
        _m for _m in _decision_all
        if isinstance(_m, dict)
        and _m.get("decision") == LEGACY_FALLBACK_DECISION
    ]

    # certificate_read_outcome: all event metas + record fallbacks.
    _cert_all = (
        _event_metas(_result, CERTIFICATE_READ_OUTCOME_EVENT)
        + _record_dicts(_result, CERTIFICATE_READ_OUTCOME_EVENT)
    )
    _cert_outcome_exists = bool(_cert_all)
    _cert_reload_present = any(
        isinstance(_e, dict) and _e.get("name") in CERTIFICATE_RELOAD_EVENT_NAMES
        for _e in _events(_result)
    )
    _cert_volume_fallback_ready = _cert_outcome_exists or _cert_reload_present
    _volume_outcomes = [
        _m for _m in _cert_all
        if _m.get("cert_decision") == "volume_read" or _m.get("cert_source") == "volume"
    ]
    _cert_volume_fallback: bool | None
    if _cert_volume_fallback_ready:
        _cert_volume_fallback = bool(_volume_outcomes) or _cert_reload_present
    else:
        _cert_volume_fallback = None
    # Fast-path certificate contract: a plan_validation-sourced cert outcome
    # with consumed=False contradicts plan_proof_decision.consumed=True.
    _plan_val_outcomes = [
        _m for _m in _cert_all if _m.get("cert_source") == "plan_validation"
    ]
    _plan_val_consumed_conflict = bool(_plan_val_outcomes) and any(
        not _boolish(_m.get("consumed")) for _m in _plan_val_outcomes
    )

    return {
        "plan_parity_eligible": (
            _boolish(_eligible_raw) if _eligible_raw is not None else None
        ),
        "plan_parity_eligible_ready": _eligible_raw is not None,
        "parity_ineligible_reason": (
            str(_ineligible_reason_raw)
            if _ineligible_reason_raw is not None else None
        ),
        "plan_proof_decision": (
            str(_decision_raw) if _decision_raw is not None else None
        ),
        "plan_proof_decision_ready": _decision_raw is not None,
        "consumed": _boolish(_consumed_raw) if _consumed_raw is not None else None,
        "consumed_ready": _consumed_raw is not None,
        "legacy_fallback": (
            bool(_legacy_outcomes) if _decision_key_present else None
        ),
        "legacy_fallback_ready": _decision_key_present,
        "cert_volume_fallback": _cert_volume_fallback,
        "cert_volume_fallback_ready": _cert_volume_fallback_ready,
        "deployment_hash_match": (
            _boolish(_dep_hash_raw) if _dep_hash_raw is not None else None
        ),
        "deployment_hash_ready": _dep_hash_raw is not None,
        "custom_nodes_generation_match": (
            _boolish(_gen_raw) if _gen_raw is not None else None
        ),
        "custom_nodes_generation_ready": _gen_raw is not None,
        "dependency_proof_match": (
            _boolish(_dep_proof_raw) if _dep_proof_raw is not None else None
        ),
        "dependency_proof_ready": _dep_proof_raw is not None,
        "fallback_reason": str(_reason_raw) if _reason_raw is not None else None,
        "cert_plan_validation_consumed_conflict": _plan_val_consumed_conflict,
    }


# ── Result container ─────────────────────────────────────────────────────
@dataclass
class BatchCAcceptanceResult:
    # Expectation / wrapped Batch-B result.
    expect_plan_fast_path: bool
    batch_b: Any  # the wrapped BatchBAcceptanceResult
    fast_path_ready: bool
    fast_path_ok: bool
    # Fast-path observables (None / ready flags; ready=True means the
    # observable was present in real evidence, never inferred).
    plan_parity_eligible: bool | None
    plan_parity_eligible_ready: bool
    plan_proof_decision: str | None
    plan_proof_decision_ready: bool
    consumed: bool | None
    consumed_ready: bool
    legacy_fallback: bool | None
    legacy_fallback_ready: bool
    cert_volume_fallback: bool | None
    cert_volume_fallback_ready: bool
    deployment_hash_match: bool | None
    deployment_hash_ready: bool
    custom_nodes_generation_match: bool | None
    custom_nodes_generation_ready: bool
    dependency_proof_match: bool | None
    dependency_proof_ready: bool
    # Fallback diagnosis.
    fallback_reason: str | None
    fallback_classification: str | None
    checks: list[GateCheck] = field(default_factory=list)
    passed: bool = False
    verdict: str = "REPORT_ONLY"  # "PASS" | "FAIL" | "REPORT_ONLY"


# ── Configuration ────────────────────────────────────────────────────────
def batch_c_config_from_env() -> dict[str, Any]:
    """Resolve the Batch-C acceptance configuration from the environment.

    Starts from ``batch_b_config_from_env()`` (Batch-B flags are inherited
    unchanged) and adds:
      COMFYMODAL_V2_BATCH_C_EXPECT_PLAN_FAST_PATH - require the plan
          validation fast-path lane: all eight fast-path gates must be READY
          and agree (NOT READY is a fail-closed FAIL).  Unset => the fast-path
          gates are reported only and never fail the run.
    """
    _cfg = batch_b_config_from_env()
    _cfg["expect_plan_fast_path"] = _env_truthy(
        "COMFYMODAL_V2_BATCH_C_EXPECT_PLAN_FAST_PATH"
    )
    return _cfg


# ── Validator ────────────────────────────────────────────────────────────
def validate_batch_c(
    artifact: dict,
    *,
    expect_plan_fast_path: bool,
    **batch_b_kwargs: Any,
) -> BatchCAcceptanceResult:
    """Validate the Batch-C fast-path acceptance lane.

    Wraps ``validate_batch_b`` (never modified, never duplicated): Batch-B is
    evaluated FIRST with the given Batch-B kwargs (any Batch-B flag left
    unspecified is resolved from the environment via
    ``batch_b_config_from_env``, mirroring ``validate_batch_b_file``).  When
    Batch-B fails, Batch-C fails unconditionally (check key
    ``batch_b_acceptance``) regardless of the fast-path fields.

    ``passed = batch_b.passed AND (not expect_plan_fast_path OR fast_path_ok)``;
    verdict is ``FAIL`` when not passed, ``REPORT_ONLY`` when passed with the
    expectation OFF, ``PASS`` when passed with the expectation ON.
    """
    if not isinstance(artifact, dict):
        artifact = {}
    expect_plan_fast_path = _boolish(expect_plan_fast_path)

    # Resolve any unspecified Batch-B kwargs from the environment (same pattern
    # as validate_batch_b_file).
    _bb_cfg = batch_b_config_from_env()
    for _key, _value in _bb_cfg.items():
        batch_b_kwargs.setdefault(_key, _value)

    # Batch-B FIRST: never modified, never duplicated.
    batch_b = validate_batch_b(artifact, **batch_b_kwargs)

    checks: list[GateCheck] = []

    # ── Wrapper gate: Batch-B acceptance (unconditional) ──────────────────
    if not batch_b.passed:
        _first_failing = [c.key for c in batch_b.checks if not c.ok]
        checks.append(GateCheck(
            "batch_b_acceptance", False, None,
            "Batch B failed: " + ", ".join(_first_failing),
        ))
    else:
        checks.append(GateCheck(
            "batch_b_acceptance", True, None, "Batch B passed all gates",
        ))

    # ── Fast-path observables (real evidence only; absence = NOT READY) ───
    _obs = _resolve_fast_path_observables(artifact)

    def _report_only_detail(label: str, ready: bool, observed: Any) -> str:
        """Expectation-OFF detail: observed (or NOT READY), never fails."""
        return (
            "expectation OFF (COMFYMODAL_V2_BATCH_C_EXPECT_PLAN_FAST_PATH "
            f"unset): {label}="
            + (str(observed) if ready else "NOT READY")
            + " - reported only, never fails"
        )

    # ── Gate 1: fast-path parity eligible ────────────────────────────────
    _g1_ok = False
    if expect_plan_fast_path:
        if not _obs["plan_parity_eligible_ready"]:
            _g1_detail = (
                "NOT READY: no future_fast_path_eligible observable anywhere "
                "(no plan_snapshot_parity event/record) - fail closed, "
                "evidence must not be inferred"
            )
        elif _obs["plan_parity_eligible"] is not True:
            _g1_detail = (
                "plan_snapshot_parity.future_fast_path_eligible="
                f"{_obs['plan_parity_eligible']!r} (expected True)"
            )
            if _obs["parity_ineligible_reason"]:
                _g1_detail += (
                    f"; ineligible reason: {_obs['parity_ineligible_reason']}"
                )
        else:
            _g1_ok = True
            _g1_detail = "plan_snapshot_parity.future_fast_path_eligible=True"
    else:
        _g1_ok = True
        _g1_detail = _report_only_detail(
            "future_fast_path_eligible",
            _obs["plan_parity_eligible_ready"],
            _obs["plan_parity_eligible"],
        )
    checks.append(GateCheck(
        "fast_path_parity_eligible", _g1_ok,
        _obs["plan_parity_eligible"], _g1_detail,
    ))

    # ── Gate 2: fast-path decision ───────────────────────────────────────
    _g2_ok = False
    if expect_plan_fast_path:
        if not _obs["plan_proof_decision_ready"]:
            _g2_detail = (
                "NOT READY: no plan_proof_decision.decision observable anywhere "
                "(no plan_proof_decision event/record) - fail closed, evidence "
                "must not be inferred"
            )
        elif _obs["plan_proof_decision"] != FAST_PATH_DECISION:
            _g2_detail = (
                "plan_proof_decision.decision="
                f"{_obs['plan_proof_decision']!r} "
                f"(expected {FAST_PATH_DECISION!r})"
            )
        else:
            _g2_ok = True
            _g2_detail = (
                f"plan_proof_decision.decision={FAST_PATH_DECISION!r}"
            )
    else:
        _g2_ok = True
        _g2_detail = _report_only_detail(
            "plan_proof_decision",
            _obs["plan_proof_decision_ready"],
            _obs["plan_proof_decision"],
        )
    checks.append(GateCheck(
        "fast_path_decision", _g2_ok,
        _obs["plan_proof_decision"], _g2_detail,
    ))

    # ── Gate 3: fast-path consumed ───────────────────────────────────────
    _g3_conflict = _obs["cert_plan_validation_consumed_conflict"]
    _g3_ok = False
    if expect_plan_fast_path:
        if not _obs["consumed_ready"]:
            _g3_detail = (
                "NOT READY: no plan_proof_decision.consumed observable anywhere "
                "(no plan_proof_decision event/record) - fail closed, evidence "
                "must not be inferred"
            )
        elif _obs["consumed"] is not True:
            _g3_detail = (
                "plan_proof_decision.consumed="
                f"{_obs['consumed']!r} (expected True; the plan proof was NOT "
                "consumed - legacy validation ran)"
            )
        elif _g3_conflict:
            _g3_detail = (
                "conflict: certificate_read_outcome(cert_source='plan_validation') "
                "consumed=False contradicts plan_proof_decision.consumed=True "
                "(primary gate vs cert contract disagree)"
            )
        else:
            _g3_ok = True
            _g3_detail = "plan_proof_decision.consumed=True"
    else:
        _g3_ok = True
        _g3_detail = _report_only_detail(
            "consumed", _obs["consumed_ready"], _obs["consumed"],
        )
        if _g3_conflict:
            _g3_detail += (
                " (note: certificate_read_outcome(cert_source='plan_validation') "
                "consumed=False contradicts the decision - reported only)"
            )
    checks.append(GateCheck(
        "fast_path_consumed", _g3_ok, _obs["consumed"], _g3_detail,
    ))

    # ── Gate 4: no legacy validation fallback ────────────────────────────
    _g4_ok = False
    if expect_plan_fast_path:
        if not _obs["legacy_fallback_ready"]:
            _g4_detail = (
                "NOT READY: no plan_proof_decision.decision observable anywhere "
                "(no plan_proof_decision event/record) - fail closed, evidence "
                "must not be inferred"
            )
        elif _obs["legacy_fallback"] is True:
            _g4_detail = (
                "plan_proof_decision.decision='legacy_validation_fallback' "
                "observed (plan proof NOT consumed; legacy validation ran)"
            )
        else:
            _g4_ok = True
            _g4_detail = (
                "no plan_proof_decision with decision='legacy_validation_fallback'"
            )
    else:
        _g4_ok = True
        _g4_detail = _report_only_detail(
            "legacy_fallback",
            _obs["legacy_fallback_ready"],
            _obs["legacy_fallback"],
        )
    checks.append(GateCheck(
        "no_legacy_validation_fallback", _g4_ok,
        _obs["legacy_fallback"], _g4_detail,
    ))

    # ── Gate 5: no certificate volume-read fallback ──────────────────────
    _g5_ok = False
    if expect_plan_fast_path:
        if not _obs["cert_volume_fallback_ready"]:
            _g5_detail = (
                "NOT READY: no certificate_read_outcome event/record and no "
                "certificate_reload_start/certificate_reload_end event anywhere "
                "- fail closed, evidence must not be inferred"
            )
        elif _obs["cert_volume_fallback"] is True:
            _g5_detail = (
                "certificate_read_outcome cert_decision='volume_read'/"
                "cert_source='volume' or certificate_reload_start/end present "
                "(volume fallback: the certificate was re-read from the volume)"
            )
        else:
            _g5_ok = True
            _g5_detail = (
                "no certificate volume-read fallback: no volume_read cert "
                "outcome and no certificate_reload_start/end events"
            )
    else:
        _g5_ok = True
        _g5_detail = _report_only_detail(
            "cert_volume_fallback",
            _obs["cert_volume_fallback_ready"],
            _obs["cert_volume_fallback"],
        )
    checks.append(GateCheck(
        "no_cert_volume_read_fallback", _g5_ok,
        _obs["cert_volume_fallback"], _g5_detail,
    ))

    # ── Gates 6-8: plan_snapshot_parity match booleans ───────────────────
    for _key, _label, _ready_key in (
        ("deployment_hash_match", "deployment_hash_match", "deployment_hash_ready"),
        ("custom_nodes_generation_match", "custom_nodes_generation_match",
         "custom_nodes_generation_ready"),
        ("dependency_proof_match", "dependency_proof_match", "dependency_proof_ready"),
    ):
        _g_ok = False
        if expect_plan_fast_path:
            if not _obs[_ready_key]:
                _g_detail = (
                    f"NOT READY: no plan_snapshot_parity.{_key} observable "
                    "anywhere (no plan_snapshot_parity event/record) - fail "
                    "closed, evidence must not be inferred"
                )
            elif _obs[_key] is not True:
                _g_detail = (
                    f"plan_snapshot_parity.{_key}={_obs[_key]!r} (expected True)"
                )
            else:
                _g_ok = True
                _g_detail = f"plan_snapshot_parity.{_key}=True"
        else:
            _g_ok = True
            _g_detail = _report_only_detail(
                _label, _obs[_ready_key], _obs[_key],
            )
        checks.append(GateCheck(
            _key, _g_ok, _obs[_key], _g_detail,
        ))

    # ── Fallback diagnosis ───────────────────────────────────────────────
    # Classify the ineligible reason when the run actually fell back to legacy
    # validation (decision=legacy_validation_fallback) or the plan proof was
    # not consumed - never on a healthy fast-path run.
    fallback_reason: str | None = None
    fallback_classification: str | None = None
    if _obs["legacy_fallback"] is True or _obs["consumed"] is False:
        fallback_reason = _obs["fallback_reason"]
        fallback_classification = _classify_fallback_reason(fallback_reason or "")

    # ── Aggregate ────────────────────────────────────────────────────────
    fast_path_ready = (
        _obs["plan_parity_eligible_ready"]
        and _obs["plan_proof_decision_ready"]
        and _obs["consumed_ready"]
        and _obs["legacy_fallback_ready"]
        and _obs["cert_volume_fallback_ready"]
        and _obs["deployment_hash_ready"]
        and _obs["custom_nodes_generation_ready"]
        and _obs["dependency_proof_ready"]
    )
    _fast_path_gates = [
        c for c in checks if c.key in FAST_PATH_GATE_KEYS
    ]
    fast_path_ok = all(c.ok for c in _fast_path_gates)

    passed = batch_b.passed and (not expect_plan_fast_path or fast_path_ok)
    if not passed:
        verdict = "FAIL"
    elif not expect_plan_fast_path:
        verdict = "REPORT_ONLY"
    else:
        verdict = "PASS"

    return BatchCAcceptanceResult(
        expect_plan_fast_path=expect_plan_fast_path,
        batch_b=batch_b,
        fast_path_ready=fast_path_ready,
        fast_path_ok=fast_path_ok,
        plan_parity_eligible=_obs["plan_parity_eligible"],
        plan_parity_eligible_ready=_obs["plan_parity_eligible_ready"],
        plan_proof_decision=_obs["plan_proof_decision"],
        plan_proof_decision_ready=_obs["plan_proof_decision_ready"],
        consumed=_obs["consumed"],
        consumed_ready=_obs["consumed_ready"],
        legacy_fallback=_obs["legacy_fallback"],
        legacy_fallback_ready=_obs["legacy_fallback_ready"],
        cert_volume_fallback=_obs["cert_volume_fallback"],
        cert_volume_fallback_ready=_obs["cert_volume_fallback_ready"],
        deployment_hash_match=_obs["deployment_hash_match"],
        deployment_hash_ready=_obs["deployment_hash_ready"],
        custom_nodes_generation_match=_obs["custom_nodes_generation_match"],
        custom_nodes_generation_ready=_obs["custom_nodes_generation_ready"],
        dependency_proof_match=_obs["dependency_proof_match"],
        dependency_proof_ready=_obs["dependency_proof_ready"],
        fallback_reason=fallback_reason,
        fallback_classification=fallback_classification,
        checks=checks,
        passed=passed,
        verdict=verdict,
    )


# ── Offline file validation ──────────────────────────────────────────────
def validate_batch_c_file(
    run_json_path: str,
    *,
    expect_plan_fast_path: bool | None = None,
    **batch_b_kwargs: Any,
) -> BatchCAcceptanceResult:
    """Load a persisted ``run_<i>.json`` artifact and validate it offline.

    ``expect_plan_fast_path`` defaults to the current environment
    (``batch_c_config_from_env``); unspecified Batch-B flags are resolved from
    the environment by ``validate_batch_c`` (same pattern as
    ``validate_batch_b_file``).
    """
    with open(run_json_path, "r", encoding="utf-8") as _fh:
        artifact = json.load(_fh)
    _cfg = batch_c_config_from_env()
    return validate_batch_c(
        artifact,
        expect_plan_fast_path=(
            _cfg["expect_plan_fast_path"]
            if expect_plan_fast_path is None
            else expect_plan_fast_path
        ),
        **batch_b_kwargs,
    )


# ── Rendering ────────────────────────────────────────────────────────────
def render_batch_c_block(res: BatchCAcceptanceResult) -> str:
    """Render the exact BATCH C ACCEPTANCE block.

    One line per fast-path observable (YES/NO/n/a), the fallback diagnosis,
    and TOTAL WALL explicitly marked as informational only (TOTAL WALL is
    NEVER an acceptance gate).  On FAIL a compact 'FAILED CHECKS:' list follows
    with one line per failing gate.  Report-only runs (verdict REPORT_ONLY)
    are clearly not a strict fast-path PASS.
    """

    def _ms(v: float | None) -> str:
        return "n/a" if v is None else f"{v:.1f}"

    def _yn(v: bool | None) -> str:
        return "n/a" if v is None else ("YES" if v else "NO")

    def _val(v: Any) -> str:
        return "n/a" if v is None else str(v)

    _lane = "READY" if res.fast_path_ready else "NOT READY"

    lines = [
        "BATCH C ACCEPTANCE",
        f"Batch B: {'PASS' if res.batch_b.passed else 'FAIL'}",
    ]
    if res.verdict == "REPORT_ONLY":
        lines.append(
            "fast-path expectation: 0 (report-only — not a strict fast-path PASS)"
        )
    else:
        lines.append(
            f"fast-path expectation: {'1' if res.expect_plan_fast_path else '0'}"
        )
    lines.extend([
        f"fast-path lane: {_lane}",
        f"plan parity eligible: {_yn(res.plan_parity_eligible)}",
        f"plan proof decision: {_val(res.plan_proof_decision)}",
        f"consumed: {_yn(res.consumed)}",
        f"legacy validation fallback: {_yn(res.legacy_fallback)}",
        f"cert volume fallback: {_yn(res.cert_volume_fallback)}",
        f"deployment hash match: {_yn(res.deployment_hash_match)}",
        f"custom nodes generation match: {_yn(res.custom_nodes_generation_match)}",
        f"dependency proof match: {_yn(res.dependency_proof_match)}",
        "",
        f"fallback reason: {_val(res.fallback_reason)}",
        f"fallback classification: {_val(res.fallback_classification)}",
        "",
        f"TOTAL WALL: {_ms(res.batch_b.total_wall_ms)} (informational only)",
        "",
        "TOTAL WALL NOT AN ACCEPTANCE GATE",
        "",
        f"OVERALL: {res.verdict}",
    ])
    if not res.passed:
        lines.append("")
        lines.append("FAILED CHECKS:")
        for _c in res.checks:
            if not _c.ok:
                lines.append(f"  {_c.key}: {_c.detail}")
    return "\n".join(lines)
