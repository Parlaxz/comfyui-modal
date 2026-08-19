"""Offline causal A/B analysis for ``COMFYMODAL_V2_SNAPSHOT_ALLOCATOR_HYGIENE``.

Arm A = hygiene OFF (flag ``"0"`` or absent); arm B = hygiene ON (flag ``"1"``).
This module is a pure, dependency-light analysis tool: it never executes a
benchmark and imports only the Python standard library.  It parses existing
benchmark run artifacts (``run_*.json`` written by ``tools/benchmark_v2_direct.py``
or experiment-run records persisted by ``comfymodal_runtime.experiment_result_store``),
validates their structural soundness, computes per-run + per-arm statistics
under a strict "median only when meaningful, p90 only when n>=5" policy,
classifies the evidence (CONFIRMED / SUPPORTED INFERENCE / INSUFFICIENT DATA)
and renders a Markdown report.

The primary command metric is the Batch-C3 ``non_scheduling_ms``
(COMMAND->RESPONSE minus scheduling time, where scheduling time = command->
enqueue + Modal placement), taken from the reconciled waterfall
(``final_reconciled_waterfall.non_scheduling_ms``) with a C3-exact fallback
arithmetic (``command_response_ms - command_to_enqueue_ms - placement``) only
when the reconciled field is absent.  The OLD placement-only subtraction is
kept as the clearly-labelled legacy/partial ``legacy_placement_excluded_ms``
(informational only, never mixed into the C3 comparison).  Snapshot freshness
is proven via ``_restore_timing.container_session_id`` (the per-construction
container session), corroborated by ``runtime_state_generation_baseline``;
``restore_session_id`` is a PER-RESTORE uuid (fresh per request,
``modal_app.py:9529``) and is demoted to per-restore correlation — never a
freshness input.  A missing construction identity is fail-closed NOT READY.
``snapshot_identity`` is lineage/model information only and never proves
fresh construction.  The modal startup metric is informational only.  An RSS
drop never alone constitutes a startup win — the causal verdict uses only the
scheduling-free primary timing metrics.  Supported range: 1-5 valid runs per arm.

Missing values are never silently zero: a missing metric is ``None`` and is
excluded from statistics (mirrors ``tools/variance_report.py``).
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path
from typing import Any

ENV_FLAG = "COMFYMODAL_V2_SNAPSHOT_ALLOCATOR_HYGIENE"
TRUTHY = {"1", "true", "yes", "on"}
UNAVAILABLE = "unavailable"

STAGE_MODAL_SCHEDULING = "modal_scheduling"
STAGE_PRE_PYTHON_RESTORE = "pre_python_snapshot_restore"
STAGE_APPLICATION_RESTORE = "application_restore"

_CAPTURE_KEYS = (
    "delta_rss_kb",
    "before_rss_kb",
    "after_rss_kb",
    "hygiene_wall_ms",
    "gc_collected",
    "cgroup_delta_bytes",
)
_SECONDARY_KEYS = ("h2d_ms", "sampling_ms", "process_cpu_ms")


# ────────────────────────────────────────────────────────────────────────────
# Primitive extraction helpers (all defensive, none raise)
# ────────────────────────────────────────────────────────────────────────────


def _num(value: Any) -> float | None:
    """Return ``float(value)`` for real numbers, else ``None``.

    ``None``, booleans, ``"absent"``, ``"unavailable"`` and non-numeric
    strings all map to ``None`` so statistics and rendering can treat them
    uniformly (same semantics as ``tools/variance_report.py:_num``).
    """
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        s = value.strip().lower()
        if s in {"", "none", "absent", "unavailable", "nan", "null", "-", "--"}:
            return None
        try:
            return float(s)
        except (TypeError, ValueError):
            return None
    return None


def _first_num(mapping: dict[str, Any], keys: list[str]) -> float | None:
    """First numeric value found among *keys*, else ``None``."""
    if not isinstance(mapping, dict):
        return None
    for key in keys:
        v = _num(mapping.get(key))
        if v is not None:
            return v
    return None


def _first_str(mapping: dict[str, Any], keys: list[str]) -> str | None:
    """First non-empty string value found among *keys*, else ``None``."""
    if not isinstance(mapping, dict):
        return None
    for key in keys:
        v = mapping.get(key)
        if v is None or isinstance(v, bool):
            continue
        s = str(v).strip()
        if s:
            return s
    return None


def _str_if_present(value: Any) -> str:
    if value is None or value == "":
        return ""
    return str(value)


def _deep_candidates(artifact: dict[str, Any]) -> list[dict[str, Any]]:
    """Ordered candidate mappings for ``_deep_first`` (root first).

    Order: artifact root, ``result``, ``timing``, ``timing.local_timing``,
    ``trace``, ``trace.metadata``, ``source_identity``, ``identity``,
    ``full_trace``, ``full_trace.metadata``.
    """
    if not isinstance(artifact, dict):
        return []
    cands: list[dict[str, Any]] = [artifact]
    result = artifact.get("result")
    if isinstance(result, dict):
        cands.append(result)
    timing = artifact.get("timing")
    if isinstance(timing, dict):
        cands.append(timing)
        local = timing.get("local_timing")
        if isinstance(local, dict):
            cands.append(local)
    trace = artifact.get("trace")
    if isinstance(trace, dict):
        cands.append(trace)
        meta = trace.get("metadata")
        if isinstance(meta, dict):
            cands.append(meta)
    source_id = artifact.get("source_identity")
    if isinstance(source_id, dict):
        cands.append(source_id)
    identity = artifact.get("identity")
    if isinstance(identity, dict):
        cands.append(identity)
    full_trace = artifact.get("full_trace")
    if isinstance(full_trace, dict):
        cands.append(full_trace)
        meta = full_trace.get("metadata")
        if isinstance(meta, dict):
            cands.append(meta)
    return cands


def _deep_first(artifact: dict[str, Any], keys: list[str]) -> Any:
    """First non-``None`` value for any of *keys* across the standard sources."""
    for cand in _deep_candidates(artifact):
        for key in keys:
            v = cand.get(key)
            if v is not None:
                return v
    return None


def _deep_first_num(artifact: dict[str, Any], keys: list[str]) -> float | None:
    return _num(_deep_first(artifact, keys))


def _hygiene_flag_value(artifact: dict[str, Any]) -> tuple[Any, str]:
    """Return ``(raw_flag_value_or_None, source_label)`` for the hygiene env
    flag.  Only dict containers are accepted; an absent flag anywhere yields
    ``(None, "unavailable")``."""
    if not isinstance(artifact, dict):
        return (None, UNAVAILABLE)
    result = artifact.get("result")
    result = result if isinstance(result, dict) else None
    timing = artifact.get("timing")
    timing = timing if isinstance(timing, dict) else None
    steps = (
        (artifact.get("effective_env"), "effective_env"),
        (result.get("effective_env") if result is not None else None, "result.effective_env"),
        (timing.get("effective_env") if timing is not None else None, "timing.effective_env"),
        (artifact.get("env"), "env"),
        (artifact.get("runtime_env"), "runtime_env"),
        (result.get("runtime_env") if result is not None else None, "result.runtime_env"),
    )
    for mapping, source in steps:
        if isinstance(mapping, dict) and ENV_FLAG in mapping:
            return (mapping[ENV_FLAG], source)
    return (None, UNAVAILABLE)


def _hygiene_enabled(value: Any) -> bool:
    """Truthy-set gate semantics: ``{"1","true","yes","on"}`` after
    ``strip().lower()``; absent/empty/off → False."""
    if value is None:
        return False
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        s = value.strip().lower()
        if s in TRUTHY:
            return True
        try:
            return float(s) != 0
        except (TypeError, ValueError):
            return False
    return False


def _flag_matches(raw: Any, expected: str) -> bool | None:
    """``None`` when the flag is unverifiable; else whether *raw* matches the
    arm expectation (``"0"`` → falsy required, ``"1"`` → truthy required)."""
    if raw is None:
        return None
    if expected == "0":
        return not _hygiene_enabled(raw)
    if expected == "1":
        return _hygiene_enabled(raw)
    return None


def _waterfall(artifact: dict[str, Any]) -> dict[str, Any] | None:
    """First waterfall dict among the standard locations, else ``None``."""
    if not isinstance(artifact, dict):
        return None
    result = artifact.get("result")
    result = result if isinstance(result, dict) else None
    candidates = (
        artifact.get("waterfall_local"),
        artifact.get("final_reconciled_waterfall"),
        artifact.get("waterfall"),
        result.get("waterfall_local") if result is not None else None,
        result.get("waterfall") if result is not None else None,
    )
    for cand in candidates:
        if isinstance(cand, dict):
            return cand
    return None


def _stage_ms(waterfall: dict[str, Any] | None, key: str) -> float | None:
    """``duration_ms`` of the first stage matching *key*, ``None`` when the
    stage is missing or carries a non-measured status."""
    if not isinstance(waterfall, dict):
        return None
    stages = waterfall.get("stages")
    if not isinstance(stages, list):
        return None
    for item in stages:
        if not isinstance(item, dict):
            continue
        if item.get("key") != key:
            continue
        status = str(item.get("status") or "").lower()
        if status in {"unavailable", "invalid", "non_applicable"}:
            return None
        return _num(item.get("duration_ms"))
    return None


def _reconciled_waterfall(artifact: dict[str, Any]) -> dict[str, Any] | None:
    """The canonical reconciled waterfall: ``final_reconciled_waterfall`` at
    the artifact root, else the host-reconciled ``waterfall_local``, else the
    remote ``waterfall`` dict."""
    if not isinstance(artifact, dict):
        return None
    result = artifact.get("result")
    result = result if isinstance(result, dict) else None
    candidates = (
        artifact.get("final_reconciled_waterfall"),
        artifact.get("waterfall_local"),
        artifact.get("waterfall"),
        result.get("final_reconciled_waterfall") if result is not None else None,
        result.get("waterfall_local") if result is not None else None,
        result.get("waterfall") if result is not None else None,
    )
    for cand in candidates:
        if isinstance(cand, dict):
            return cand
    return None


def _c3_scheduling(artifact: dict[str, Any], command_response_ms: float | None) -> tuple[float | None, float | None, float | None, str]:
    """Batch-C3 scheduling-contract quantities.

    Returns ``(non_scheduling_ms, command_to_enqueue_ms, scheduling_time_ms,
    source)`` where:

    - ``non_scheduling_ms`` — the accepted C3 primary: COMMAND -> RESPONSE
      minus scheduling time.  Preference: (1) the reconciled waterfall field
      ``non_scheduling_ms`` (the final reconciled C3 value as persisted);
      (2) C3-exact fallback arithmetic only when necessary:
      ``command_response_ms - command_to_enqueue_ms - placement_scheduling``
      (scheduling time = command->enqueue + placement).
    - ``command_to_enqueue_ms`` — the enqueue component (informational).
    - ``scheduling_time_ms`` — enqueue + placement (informational).
    - ``source`` — ``"reconciled"`` or ``"fallback_arithmetic"`` (``""`` when
      unavailable).

    The OLD placement-only subtraction is NEVER used here; callers expose it
    separately as the clearly-labelled legacy metric.
    """
    waterfall = _reconciled_waterfall(artifact)
    enqueue = _first_num(waterfall, ["command_to_enqueue_ms"]) if isinstance(waterfall, dict) else None
    if enqueue is None:
        enqueue = _deep_first_num(artifact, ["command_to_enqueue_ms"])
    placement = _deep_first_num(artifact, ["scheduling_ms"])
    if placement is None:
        placement = _stage_ms(waterfall, STAGE_MODAL_SCHEDULING)
    non_sched = _first_num(waterfall, ["non_scheduling_ms"]) if isinstance(waterfall, dict) else None
    source = ""
    if non_sched is not None:
        source = "reconciled"
    elif (
        command_response_ms is not None
        and enqueue is not None
        and placement is not None
        and enqueue >= 0
        and placement >= 0
        and command_response_ms >= 0
    ):
        non_sched = command_response_ms - enqueue - placement
        source = "fallback_arithmetic"
    scheduling_time_ms: float | None = None
    if enqueue is not None and placement is not None:
        scheduling_time_ms = enqueue + placement
    return non_sched, enqueue, scheduling_time_ms, source


def _hygiene_event(artifact: dict[str, Any]) -> dict[str, Any] | None:
    """Locate the ``snapshot_capture_hygiene`` event dict across the known
    candidate paths, else ``None``."""
    if not isinstance(artifact, dict):
        return None
    result = artifact.get("result")
    result = result if isinstance(result, dict) else None
    result_trace = result.get("trace") if result is not None else None
    result_trace = result_trace if isinstance(result_trace, dict) else None
    trace = artifact.get("trace")
    trace = trace if isinstance(trace, dict) else None
    full_trace = artifact.get("full_trace")
    full_trace = full_trace if isinstance(full_trace, dict) else None
    timing = artifact.get("timing")
    timing = timing if isinstance(timing, dict) else None

    def _inner(cand: Any) -> dict[str, Any] | None:
        if isinstance(cand, dict):
            ev = cand.get("snapshot_capture_hygiene")
            if isinstance(ev, dict):
                return ev
        return None

    for cand in (
        result.get("_restore_timing") if result is not None else None,
        result_trace.get("_restore_timing") if result_trace is not None else None,
        artifact.get("_restore_timing"),
        trace.get("_restore_timing") if trace is not None else None,
        full_trace.get("_restore_timing") if full_trace is not None else None,
        timing.get("_restore_timing") if timing is not None else None,
        result,
        artifact,
    ):
        ev = _inner(cand)
        if ev is not None:
            return ev

    # Scan trace-event metadata dicts for a key named snapshot_capture_hygiene.
    for container in (result_trace, full_trace):
        if container is None:
            continue
        events = container.get("events")
        if not isinstance(events, list):
            continue
        for ev in events:
            if not isinstance(ev, dict):
                continue
            meta = ev.get("metadata")
            if not isinstance(meta, dict):
                continue
            val = meta.get("snapshot_capture_hygiene")
            if isinstance(val, dict):
                return val
    return None


def _trace_event_metadata(artifact: dict[str, Any], event_names: tuple[str, ...]) -> dict[str, Any]:
    """First ``metadata`` dict among the trace-event locations whose event
    ``name`` matches any of *event_names*, else ``{}``.

    Scan order: ``result.trace.events``, ``result.full_trace_artifact`` events
    (dict or list container), ``trace.events``, ``full_trace.events``,
    ``timing.events`` — each a list of ``{"name": ..., "metadata": {...}}``.
    """
    if not isinstance(artifact, dict):
        return {}
    result = artifact.get("result")
    result = result if isinstance(result, dict) else None
    trace = artifact.get("trace")
    trace = trace if isinstance(trace, dict) else None
    full_trace = artifact.get("full_trace")
    full_trace = full_trace if isinstance(full_trace, dict) else None
    timing = artifact.get("timing")
    timing = timing if isinstance(timing, dict) else None

    def _scan(container: Any) -> dict[str, Any] | None:
        events = None
        if isinstance(container, dict):
            events = container.get("events")
        elif isinstance(container, list):
            events = container
        if not isinstance(events, list):
            return None
        for ev in events:
            if not isinstance(ev, dict):
                continue
            if str(ev.get("name") or "") not in event_names:
                continue
            meta = ev.get("metadata")
            if isinstance(meta, dict):
                return meta
        return None

    for cand in (
        result.get("trace") if result is not None else None,
        result.get("full_trace_artifact") if result is not None else None,
        trace,
        full_trace,
        timing,
    ):
        meta = _scan(cand)
        if meta is not None:
            return meta
    return {}


def _snapshot_identity(artifact: dict[str, Any], result: dict[str, Any] | None) -> str:
    v = artifact.get("snapshot_identity")
    if v is None and result is not None:
        v = result.get("snapshot_identity")
    if v is None:
        source = artifact.get("source_identity")
        if isinstance(source, dict):
            v = source.get("restore_session_id")
    if v is None or v == "":
        return ""
    return str(v)


def _restore_session_id(artifact: dict[str, Any]) -> str:
    """Per-RESTORE correlation id (``_restore_timing.restore_session_id``).

    ``modal_app.py`` ``startup()`` issues a fresh ``uuid.uuid4().hex`` on
    EVERY request restore (``modal_app.py:9529``) — it is a per-restore
    correlation token, NOT a per-construction identity.  It is extracted and
    reported (per-run table) but is NEVER used for freshness/consistency
    verdicts (see ``container_session_id`` / ``runtime_state_generation_baseline``).
    """
    return _restore_timing_field(artifact, "restore_session_id")


def _container_session_id(artifact: dict[str, Any]) -> str:
    """The real per-construction snapshot identity.

    ``result._restore_timing.container_session_id`` is fixed per constructed
    snapshot / restored container and is stable across every request restore
    that reuses the same construction (unlike ``restore_session_id``, which is
    a fresh uuid per request).  This is the freshness discriminator.
    """
    return _restore_timing_field(artifact, "container_session_id")


def _runtime_state_generation_baseline(artifact: dict[str, Any]) -> str:
    """Corroboration for the construction identity.

    ``result._restore_timing.runtime_state_generation_baseline`` is frozen
    into the snapshot at construction (``RuntimeBootstrap``); different
    constructions carry different baselines.  A run whose baseline is missing
    or inconsistent with its arm's baseline makes the arm NOT READY
    (fail-closed corroboration).
    """
    return _restore_timing_field(artifact, "runtime_state_generation_baseline")


def _restore_timing_field(artifact: dict[str, Any], key: str) -> str:
    """Locate ``_restore_timing`` across the known paths and return the first
    non-empty scalar for *key*, else ``""``."""
    if not isinstance(artifact, dict):
        return ""
    result = artifact.get("result")
    result = result if isinstance(result, dict) else None
    result_trace = result.get("trace") if result is not None else None
    result_trace = result_trace if isinstance(result_trace, dict) else None
    trace = artifact.get("trace")
    trace = trace if isinstance(trace, dict) else None
    full_trace = artifact.get("full_trace")
    full_trace = full_trace if isinstance(full_trace, dict) else None
    timing = artifact.get("timing")
    timing = timing if isinstance(timing, dict) else None

    def _inner(cand: Any) -> str:
        if not isinstance(cand, dict):
            return ""
        rt = cand.get("_restore_timing")
        if not isinstance(rt, dict):
            return ""
        v = rt.get(key)
        if v is None or isinstance(v, bool):
            return ""
        s = str(v).strip()
        return s

    for cand in (
        result,
        result_trace,
        artifact,
        trace,
        full_trace,
        timing,
    ):
        s = _inner(cand)
        if s:
            return s

    # Fallbacks for serialized / record-style shapes: a direct key on the
    # artifact or the identity dicts.
    for cand in (artifact, result, trace, full_trace, timing):
        if not isinstance(cand, dict):
            continue
        v = cand.get(key)
        if v is not None and not isinstance(v, bool):
            s = str(v).strip()
            if s:
                return s
    for container in ("source_identity", "identity"):
        m = artifact.get(container)
        if not isinstance(m, dict):
            continue
        v = m.get(key)
        if v is not None and not isinstance(v, bool):
            s = str(v).strip()
            if s:
                return s
    return ""


def _cold(artifact: dict[str, Any]) -> bool | None:
    """True when restore_count == 1 AND request_count == 1 in the first
    identity-like source that carries both; None when unverifiable."""
    if not isinstance(artifact, dict):
        return None
    candidates: list[dict[str, Any]] = []
    for key in ("identity", "source_identity"):
        m = artifact.get(key)
        if isinstance(m, dict):
            candidates.append(m)
    result = artifact.get("result")
    if isinstance(result, dict):
        for key in ("identity", "source_identity"):
            m = result.get(key)
            if isinstance(m, dict):
                candidates.append(m)
    for tkey in ("trace", "full_trace"):
        t = artifact.get(tkey)
        if isinstance(t, dict):
            meta = t.get("metadata")
            if isinstance(meta, dict):
                candidates.append(meta)
    for cand in candidates:
        rc = _num(cand.get("restore_count"))
        rq = _num(cand.get("request_count"))
        if rc is not None and rq is not None:
            return bool(rc == 1 and rq == 1)
    return None


def _modal_startup_ms(artifact: dict[str, Any], waterfall: dict[str, Any] | None) -> float | None:
    v = _deep_first_num(artifact, ["submission_to_remote_python_resume_ms"])
    if v is None:
        v = _deep_first_num(artifact, ["pre_python_modal_scheduling_ms"])
    if v is None:
        s = _stage_ms(waterfall, STAGE_MODAL_SCHEDULING)
        p = _stage_ms(waterfall, STAGE_PRE_PYTHON_RESTORE)
        if s is not None and p is not None:
            v = s + p
    return v


def _h2d_ms(artifact: dict[str, Any], result: dict[str, Any] | None) -> float | None:
    v = _deep_first_num(artifact, ["synchronized_transfer_ms", "cpu_to_gpu_transfer_ms"])
    if v is not None:
        return v
    trace = result.get("trace") if result is not None else None
    if not isinstance(trace, dict):
        return None
    events = trace.get("events")
    if not isinstance(events, list):
        return None
    for ev in events:
        if not isinstance(ev, dict):
            continue
        if "h2d" not in str(ev.get("name") or "").lower():
            continue
        meta = ev.get("metadata")
        if isinstance(meta, dict):
            v = _first_num(meta, ["duration_ms", "elapsed_ms"])
            if v is not None:
                return v
    return None


# ────────────────────────────────────────────────────────────────────────────
# Per-run normalization
# ────────────────────────────────────────────────────────────────────────────


def _record_template(arm_label: str, source_path: str) -> dict[str, Any]:
    return {
        "valid": False,
        "invalid_reasons": [],
        "run_id": Path(source_path).stem or "unknown",
        "arm": arm_label,
        "source_path": source_path,
        "hygiene_flag_raw": None,
        "hygiene_flag_ok": None,
        "snapshot_identity": "",
        "restore_session_id": "",
        "container_session_id": "",
        "runtime_state_generation_baseline": "",
        "image_id": "",
        "provider": "",
        "region": "",
        "gpu": "",
        "cpu": "",
        "ram": "",
        "workflow_hash_prefix": "",
        "cold": None,
        "retained": True,
        "discard_reason": "",
        "command_response_ms": None,
        "scheduling_ms": None,
        "non_scheduling_ms": None,
        "non_scheduling_source": "",
        "command_to_enqueue_ms": None,
        "scheduling_time_ms": None,
        "legacy_placement_excluded_ms": None,
        "modal_startup_ms": None,
        "modal_startup_scheduling_inclusive": True,
        "pre_python_snapshot_restore_ms": None,
        "application_restore_ms": None,
        "total_wall_ms": None,
        "hygiene_event_present": False,
        "hygiene_enabled": None,
        "before_rss_kb": None,
        "after_rss_kb": None,
        "delta_rss_kb": None,
        "before_rss_anon_kb": None,
        "after_rss_anon_kb": None,
        "before_rss_file_kb": None,
        "after_rss_file_kb": None,
        "cgroup_before_bytes": None,
        "cgroup_after_bytes": None,
        "cgroup_delta_bytes": None,
        "hygiene_wall_ms": None,
        "gc_collected": None,
        "malloc_trim_result": None,
        "malloc_trim_available": None,
        "h2d_ms": None,
        "sampling_ms": None,
        "process_cpu_ms": None,
        "host_fingerprint": "",
        "host_cpu_model": "",
        "gpu_name": "",
        "runtime_state_reload_decision": "",
        "runtime_state_reload_check_ms": None,
        "runtime_state_reload_invoked": None,
        "reload_runtime_state_ms": None,
        "restore_bootstrap_ms": None,
        "restore_gpu_state_ms": None,
        "restore_residual_ms": None,
    }


def extract_run(
    artifact: dict[str, Any],
    *,
    arm_label: str,
    expected_flag: str,
    source_path: str = "",
) -> dict[str, Any]:
    """Normalise ONE artifact into a flat record (never raises).

    ``expected_flag`` is ``"0"`` for arm A and ``"1"`` for arm B.  A flag that
    is absent anywhere leaves ``hygiene_flag_ok`` unverifiable (``None``) and
    is NOT an invalidation.  ``modal_startup_ms`` is always scheduling-inclusive
    and never satisfies "no primary timing data".
    """
    rec = _record_template(arm_label, source_path)
    if not isinstance(artifact, dict):
        rec["invalid_reasons"].append("non-dict artifact")
        return rec

    result = artifact.get("result")
    result = result if isinstance(result, dict) else None
    waterfall = _waterfall(artifact)

    # run_id
    rid = artifact.get("request_id")
    if rid is None and result is not None:
        rid = result.get("request_id")
    if rid is None:
        rid = artifact.get("prompt_id")
    if rid is None:
        rid = artifact.get("run_id")
    if rid is None:
        rid = Path(source_path).stem
    rec["run_id"] = str(rid or Path(source_path).stem)

    # Env-flag verification.
    raw_flag, _flag_source = _hygiene_flag_value(artifact)
    rec["hygiene_flag_raw"] = raw_flag
    rec["hygiene_flag_ok"] = _flag_matches(raw_flag, expected_flag)

    # Identity fields.
    rec["snapshot_identity"] = _snapshot_identity(artifact, result)
    # restore_session_id is PER-RESTORE correlation only (modal_app.py:9529);
    # never used for freshness.  container_session_id is the per-construction
    # identity; runtime_state_generation_baseline corroborates it.
    rec["restore_session_id"] = _restore_session_id(artifact)
    rec["container_session_id"] = _container_session_id(artifact)
    rec["runtime_state_generation_baseline"] = _runtime_state_generation_baseline(artifact)
    rec["image_id"] = _str_if_present(_deep_first(artifact, ["image_id"]))
    rec["provider"] = _str_if_present(_deep_first(artifact, ["provider", "cloud"]))
    rec["region"] = _str_if_present(_deep_first(artifact, ["region"]))
    rec["gpu"] = _str_if_present(_deep_first(artifact, ["gpu"]))
    rec["cpu"] = _str_if_present(_deep_first(artifact, ["cpu"]))
    rec["ram"] = _str_if_present(_deep_first(artifact, ["ram"]))
    rec["workflow_hash_prefix"] = _str_if_present(_deep_first(artifact, ["workflow_hash_prefix"]))
    rec["cold"] = _cold(artifact)

    # Retention.
    retained = artifact.get("retained", True)
    rec["retained"] = bool(retained)
    rec["discard_reason"] = str(artifact.get("discard_reason") or "")

    # Primary timing.
    rec["command_response_ms"] = _deep_first_num(artifact, ["command_response_ms"])
    if rec["command_response_ms"] is None:
        rec["command_response_ms"] = _deep_first_num(artifact, ["command_to_response_ms"])
    sched = _deep_first_num(artifact, ["scheduling_ms"])
    if sched is None:
        sched = _stage_ms(waterfall, STAGE_MODAL_SCHEDULING)
    rec["scheduling_ms"] = sched
    # ── Batch-C3 scheduling contract ──────────────────────────────────────
    # Accepted C3 semantics (V2_BATCH_C3_WATERFALL_CONTRACT_REPORT.md):
    #   Scheduling time = (command -> Modal enqueue) + (Modal scheduling /
    #   placement); Command (without scheduling) -> Response = COMMAND ->
    #   RESPONSE - Scheduling time.
    # Primary source preference:
    #   1. final_reconciled_waterfall.non_scheduling_ms (the final reconciled
    #      C3 value as persisted in the artifact);
    #   2. fallback arithmetic only when necessary:
    #      command_response_ms - command_to_enqueue_ms - placement_scheduling.
    # The OLD placement-only subtraction is NEVER the primary: it is exposed
    # as the clearly-named legacy/partial metric legacy_placement_excluded_ms
    # and is never silently mixed with true C3 non_scheduling_ms.
    c3_non_sched, c3_enqueue, c3_sched_time, c3_source = _c3_scheduling(
        artifact, rec["command_response_ms"]
    )
    rec["non_scheduling_ms"] = c3_non_sched
    rec["non_scheduling_source"] = c3_source
    rec["command_to_enqueue_ms"] = c3_enqueue
    rec["scheduling_time_ms"] = c3_sched_time
    # Legacy placement-only subtraction (informational; labelled as legacy).
    if rec["command_response_ms"] is not None and rec["scheduling_ms"] is not None:
        rec["legacy_placement_excluded_ms"] = rec["command_response_ms"] - rec["scheduling_ms"]
    rec["modal_startup_scheduling_inclusive"] = True
    rec["modal_startup_ms"] = _modal_startup_ms(artifact, waterfall)
    pp = _stage_ms(waterfall, STAGE_PRE_PYTHON_RESTORE)
    if pp is None:
        pp = _deep_first_num(artifact, ["pre_python_snapshot_restore_ms"])
    rec["pre_python_snapshot_restore_ms"] = pp
    app = _stage_ms(waterfall, STAGE_APPLICATION_RESTORE)
    if app is None:
        app = _deep_first_num(artifact, ["restore_total_ms"])
    rec["application_restore_ms"] = app
    rec["total_wall_ms"] = _deep_first_num(artifact, ["total_wall_ms"])

    # Capture-time (allocator hygiene) evidence.
    event = _hygiene_event(artifact)
    if event is not None:
        rec["hygiene_event_present"] = True
        en = _num(event.get("enabled"))
        rec["hygiene_enabled"] = int(en) if en is not None else None
        before_rss = _first_num(event, ["before_rss_kb", "rss_kb_before"])
        if before_rss is None:
            mb = _num(event.get("rss_mb_before"))
            if mb is not None:
                before_rss = mb * 1024
        after_rss = _first_num(event, ["after_rss_kb", "rss_kb_after"])
        if after_rss is None:
            mb = _num(event.get("rss_mb_after"))
            if mb is not None:
                after_rss = mb * 1024
        rec["before_rss_kb"] = before_rss
        rec["after_rss_kb"] = after_rss
        delta = _first_num(event, ["delta_rss_kb"])
        if delta is None and before_rss is not None and after_rss is not None:
            delta = before_rss - after_rss
        rec["delta_rss_kb"] = delta
        rec["before_rss_anon_kb"] = _num(event.get("before_rss_anon_kb"))
        rec["after_rss_anon_kb"] = _num(event.get("after_rss_anon_kb"))
        rec["before_rss_file_kb"] = _num(event.get("before_rss_file_kb"))
        rec["after_rss_file_kb"] = _num(event.get("after_rss_file_kb"))
        rec["cgroup_before_bytes"] = _num(event.get("cgroup_memory_current_before_bytes"))
        rec["cgroup_after_bytes"] = _num(event.get("cgroup_memory_current_after_bytes"))
        rec["cgroup_delta_bytes"] = _num(event.get("cgroup_memory_current_delta_bytes"))
        rec["hygiene_wall_ms"] = _first_num(event, ["hygiene_wall_ms", "hygiene_wall_cost_ms"])
        rec["gc_collected"] = _first_num(event, ["gc_collected", "gc_collected_count"])
        rec["malloc_trim_result"] = _first_str(event, ["malloc_trim_result", "malloc_trim_status", "malloc_trim"])
        ta = _num(event.get("malloc_trim_available"))
        rec["malloc_trim_available"] = int(ta) if ta is not None else None

    # Secondary metrics.
    rec["h2d_ms"] = _h2d_ms(artifact, result)
    rec["sampling_ms"] = _deep_first_num(artifact, ["sampling_ms", "sampler_ms"])
    rec["process_cpu_ms"] = _deep_first_num(artifact, ["process_cpu_ms", "variance_process_cpu_ms"])

    # ── Host / B1 / restore-tail stratification (informational) ──
    # These fields are recorded so a future A/B can stratify by host, region or
    # restore-tail, and so the operator-side B1 gate can be checked.  They are
    # never inputs to validity or classification.
    fp_meta = _trace_event_metadata(artifact, ("host_hardware_fingerprint",))
    ht = _reconciled_waterfall(artifact)
    ht = ht.get("host_telemetry") if isinstance(ht, dict) else None
    fp = fp_meta.get("cpuinfo_fingerprint_hash") or fp_meta.get("fingerprint_hash")
    if not fp and isinstance(ht, dict):
        fp = "/".join(
            str(ht.get(k) or "").strip()
            for k in ("cpu_vendor", "cpu_family", "cpu_model")
            if str(ht.get(k) or "").strip()
        )
    rec["host_fingerprint"] = str(fp or "")
    cpu_model = fp_meta.get("cpu_model_name") or ""
    if not cpu_model:
        cpu_model = ht.get("cpu_model") if isinstance(ht, dict) else None
    rec["host_cpu_model"] = str(cpu_model or "")
    gpu_name = ht.get("gpu_name") if isinstance(ht, dict) else None
    if not gpu_name:
        gpu_name = _deep_first(artifact, ["gpu", "gpu_name"])
    rec["gpu_name"] = str(gpu_name or "")

    b1_ev = _trace_event_metadata(artifact, ("runtime_state_reload_decision",))
    rec["runtime_state_reload_decision"] = str(b1_ev.get("decision") or "")
    rec["runtime_state_reload_check_ms"] = _num(b1_ev.get("check_ms"))
    b1_invoked = b1_ev.get("runtime_state_reload_invoked")
    if b1_invoked is None:
        b1_invoked = b1_ev.get("callback_called")
    if b1_invoked is None:
        b1_invoked = _num(_restore_timing_field(artifact, "reload_runtime_state_invoked"))
    rec["runtime_state_reload_invoked"] = b1_invoked
    rec["reload_runtime_state_ms"] = _num(_restore_timing_field(artifact, "reload_runtime_state_ms"))

    rec["restore_gpu_state_ms"] = _num(_restore_timing_field(artifact, "restore_gpu_state_ms"))
    rec["restore_bootstrap_ms"] = _num(_restore_timing_field(artifact, "bootstrap_ms"))
    if rec["restore_bootstrap_ms"] is None:
        rec["restore_bootstrap_ms"] = _num(_restore_timing_field(artifact, "bootstrap_restore_ms"))
    if rec["restore_bootstrap_ms"] is None:
        start = _trace_event_metadata(artifact, ("v2_bootstrap_restore_start",))
        end = _trace_event_metadata(artifact, ("v2_bootstrap_restore_end",))
        d = _first_num(end, ["duration_ms", "elapsed_ms"])
        if d is None:
            d = _first_num(start, ["duration_ms", "elapsed_ms"])
        if d is not None:
            rec["restore_bootstrap_ms"] = d
        elif start and end:
            s_ns = _first_num(start, ["mono_ns", "monotonic_ns"])
            e_ns = _first_num(end, ["mono_ns", "monotonic_ns"])
            if s_ns is not None and e_ns is not None:
                rec["restore_bootstrap_ms"] = round((e_ns - s_ns) / 1_000_000.0, 3)

    total = _num(_restore_timing_field(artifact, "restore_total_ms"))
    if total is not None:
        children = 0.0
        for k in (
            "reload_runtime_state_ms",
            "reload_models_ms",
            "restore_gpu_state_ms",
            "initialize_cuda_ms",
            "cuda_init_ms",
            "snapshot_identity_checks_ms",
            "cpu_snapshot_retargeting_ms",
            "sync_custom_nodes_ms",
            "observe_generations_ms",
            "backend_startup_ms",
            "snapshot_restore_ms",
            "v2_startup_snapshot_execution_seed_ms",
        ):
            v = _num(_restore_timing_field(artifact, k))
            if v is not None:
                children += v
        rec["restore_residual_ms"] = round(total - children, 3)

    # ── Validity ──
    valid = True
    reasons: list[str] = []
    if not retained:
        valid = False
        reasons.append(f"discarded record: {rec['discard_reason']}")
    has_primary = (
        rec["command_response_ms"] is not None
        or rec["pre_python_snapshot_restore_ms"] is not None
        or rec["application_restore_ms"] is not None
        or waterfall is not None
    )
    if not has_primary:
        valid = False
        reasons.append("no primary timing data")
    if rec["legacy_placement_excluded_ms"] is not None and rec["legacy_placement_excluded_ms"] < -1.0:
        valid = False
        reasons.append("negative legacy_placement_excluded_ms")
    if rec["command_response_ms"] is not None and rec["command_response_ms"] < -1.0:
        valid = False
        reasons.append("negative command_response_ms")
    if raw_flag is not None and rec["hygiene_flag_ok"] is False:
        valid = False
        reasons.append(f"hygiene flag mismatch: expected {expected_flag} but artifact shows {raw_flag}")
    if rec["cold"] is False:
        valid = False
        reasons.append("warm run")
    rec["valid"] = valid
    rec["invalid_reasons"] = reasons
    return rec


def load_arm_runs(
    path: str | Path,
    arm_label: str,
    expected_flag: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Load every run artifact under *path* (a directory of ``run_*.json`` or
    a single ``.json`` file) into ``(valid_records, excluded_records)``.

    Unreadable / non-JSON files become excluded records so no run is silently
    dropped.
    """
    p = Path(path)
    files: list[Path] = []
    if p.is_dir():
        files = sorted(p.glob("run_*.json"))
    elif p.is_file() and p.suffix.lower() == ".json":
        files = [p]
    else:
        return [], []

    records: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []
    for f in files:
        try:
            raw = json.loads(f.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            excluded.append({
                "valid": False,
                "invalid_reasons": [f"unreadable artifact: {exc}"],
                "run_id": f.stem,
                "arm": arm_label,
                "source_path": str(f),
            })
            continue
        rec = extract_run(raw, arm_label=arm_label, expected_flag=expected_flag, source_path=str(f))
        if rec["valid"]:
            records.append(rec)
        else:
            excluded.append(rec)
    return records, excluded


# ────────────────────────────────────────────────────────────────────────────
# Statistics and classification
# ────────────────────────────────────────────────────────────────────────────


def _percentile(sorted_values: list[float], p: float) -> float | None:
    """Nearest-rank percentile of an already-sorted (ascending) list."""
    n = len(sorted_values)
    if n == 0:
        return None
    if p <= 0:
        return sorted_values[0]
    if p >= 100:
        return sorted_values[-1]
    k = max(1, int((p / 100.0) * n + 0.5))
    return sorted_values[min(k, n) - 1]


def compute_arm_stats(runs: list[dict[str, Any]], metric_key: str) -> dict[str, Any]:
    """Summary statistics over the available (non-``None``) values of
    *metric_key* from valid *runs*.

    Policy: ``median`` and ``mean`` are only reported when n >= 2 (they are
    ``None`` for n == 1); ``p90`` is only reported when n >= 5.  ``min``/``max``
    are always reported for n >= 1.  n == 0 yields ``None`` everywhere and
    both meaningful-flags ``False`` — never a fabricated zero.
    """
    values: list[float] = []
    for r in runs:
        v = _num(r.get(metric_key))
        if v is not None:
            values.append(v)
    values.sort()
    n = len(values)
    median_meaningful = n >= 2
    p90_meaningful = n >= 5
    stats: dict[str, Any] = {
        "count": n,
        "values": values,
        "median": None,
        "mean": None,
        "min": None,
        "max": None,
        "p90": None,
        "median_meaningful": median_meaningful,
        "p90_meaningful": p90_meaningful,
    }
    if n == 0:
        return stats
    stats["min"] = round(values[0], 3)
    stats["max"] = round(values[-1], 3)
    if median_meaningful:
        stats["median"] = round(statistics.median(values), 3)
        stats["mean"] = round(statistics.mean(values), 3)
    if p90_meaningful:
        stats["p90"] = round(_percentile(values, 90) or 0.0, 3)
    return stats


def classify_metric(
    arm_a_runs: list[dict[str, Any]],
    arm_b_runs: list[dict[str, Any]],
    metric_key: str,
    *,
    noise_floor_ms: float = 1.0,
    min_confirmed: int = 3,
) -> dict[str, Any]:
    """Classify one metric's evidence across both arms.

    ``stats_a`` / ``stats_b`` are additive extras (the ``compute_arm_stats``
    results) carried for rendering and tests.
    """
    stats_a = compute_arm_stats(arm_a_runs, metric_key)
    stats_b = compute_arm_stats(arm_b_runs, metric_key)
    count_a = stats_a["count"]
    count_b = stats_b["count"]
    median_a = stats_a["median"]
    median_b = stats_b["median"]
    result: dict[str, Any] = {
        "metric": metric_key,
        "count_a": count_a,
        "count_b": count_b,
        "median_a": median_a,
        "median_b": median_b,
        "delta_ms": None,
        "direction": "none",
        "classification": "INSUFFICIENT DATA",
        "reason": "",
        "scheduling_inclusive": metric_key == "modal_startup_ms",
        "stats_a": stats_a,
        "stats_b": stats_b,
    }
    if count_a == 0 or count_b == 0:
        result["reason"] = "metric missing on one side"
        return result
    if count_a < 2 or count_b < 2:
        result["reason"] = "n<2 on one side (median not meaningful)"
        return result

    delta = median_b - median_a  # both medians meaningful here
    result["delta_ms"] = delta
    if delta == 0 or abs(delta) <= noise_floor_ms:
        result["direction"] = "none"
        result["reason"] = f"no measurable difference within {noise_floor_ms:g} ms floor"
        return result

    result["direction"] = "B faster" if delta < 0 else "B slower"
    vals_a = stats_a["values"]
    vals_b = stats_b["values"]
    fully_separated = max(vals_a) < min(vals_b) or max(vals_b) < min(vals_a)
    if count_a >= min_confirmed and count_b >= min_confirmed and fully_separated:
        result["classification"] = "CONFIRMED"
        result["reason"] = "fully separated ranges at n>=min_confirmed per arm"
    else:
        result["classification"] = "SUPPORTED INFERENCE"
        result["reason"] = "overlapping ranges / below confirmation bar"
    return result


# ────────────────────────────────────────────────────────────────────────────
# Aggregate analysis
# ────────────────────────────────────────────────────────────────────────────


def _partition(records: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    valid = [r for r in records if r.get("valid")]
    excluded = [r for r in records if not r.get("valid")]
    return valid, excluded


def _flag_verified(valid_runs: list[dict[str, Any]]) -> bool | None:
    has_true = any(r.get("hygiene_flag_ok") is True for r in valid_runs)
    has_false = any(r.get("hygiene_flag_ok") is False for r in valid_runs)
    if has_false:
        return False
    if has_true:
        return True
    return None


def _unique_nonempty(valid_runs: list[dict[str, Any]], key: str) -> list[str]:
    out = sorted({str(r.get(key) or "").strip() for r in valid_runs if str(r.get(key) or "").strip()})
    return out


def _cold_verified(valid_runs: list[dict[str, Any]]) -> bool | None:
    if not valid_runs:
        return None
    colds = [r.get("cold") for r in valid_runs]
    if any(c is False for c in colds):
        return False
    if all(c is True for c in colds):
        return True
    return None


def _consistency(unique: list[str]) -> bool | None:
    if not unique:
        return None
    return len(unique) == 1


def analyze(
    arm_a_runs: list[dict[str, Any]],
    arm_b_runs: list[dict[str, Any]],
    *,
    noise_floor_ms: float = 1.0,
    min_confirmed: int = 3,
) -> dict[str, Any]:
    """Full A/B analysis.

    Each arm argument is the full per-arm record list (valid and invalid, as
    produced by concatenating ``load_arm_runs``'s two returns); records are
    partitioned internally so callers may also pass only valid runs.
    """
    valid_a, excluded_a = _partition(arm_a_runs)
    valid_b, excluded_b = _partition(arm_b_runs)

    primary_metrics = [
        "non_scheduling_ms",
        "pre_python_snapshot_restore_ms",
        "application_restore_ms",
    ]

    metrics: dict[str, dict[str, Any]] = {}
    for key in primary_metrics:
        metrics[key] = classify_metric(
            valid_a, valid_b, key,
            noise_floor_ms=noise_floor_ms, min_confirmed=min_confirmed,
        )
    metrics["modal_startup_ms"] = classify_metric(
        valid_a, valid_b, "modal_startup_ms",
        noise_floor_ms=noise_floor_ms, min_confirmed=min_confirmed,
    )
    # Legacy placement-only subtraction: informational only, clearly labelled,
    # never a primary and never mixed with true C3 non_scheduling_ms.
    metrics["legacy_placement_excluded_ms"] = classify_metric(
        valid_a, valid_b, "legacy_placement_excluded_ms",
        noise_floor_ms=noise_floor_ms, min_confirmed=min_confirmed,
    )

    # ── Protocol checks ──
    flag_verified_a = _flag_verified(valid_a)
    flag_verified_b = _flag_verified(valid_b)
    # Freshness discriminator is the per-construction container session
    # (result._restore_timing.container_session_id), corroborated by the
    # runtime-state generation baseline
    # (result._restore_timing.runtime_state_generation_baseline).  restore_
    # session_id is a PER-RESTORE uuid (modal_app.py:9529, fresh per request)
    # and is demoted to per-restore correlation — reported, never a freshness
    # input.  snapshot_identity is the stable model hash — arm-invariant
    # lineage info only, never a freshness proof.
    snap_a = _unique_nonempty(valid_a, "snapshot_identity")
    snap_b = _unique_nonempty(valid_b, "snapshot_identity")
    containers_a = _unique_nonempty(valid_a, "container_session_id")
    containers_b = _unique_nonempty(valid_b, "container_session_id")
    baselines_a = _unique_nonempty(valid_a, "runtime_state_generation_baseline")
    baselines_b = _unique_nonempty(valid_b, "runtime_state_generation_baseline")

    # Fail-closed freshness readiness: every valid run in an arm must carry
    # container_session_id AND a consistent runtime_state_generation_baseline.
    # A run with container_session_id present but baseline missing, or a
    # baseline inconsistent with the arm's, is NOT READY — never silently fresh.
    def _freshness_ready(runs: list[dict[str, Any]], label: str) -> tuple[bool, str]:
        if not runs:
            return False, f"arm {label}: no valid runs"
        missing_container = [
            r.get("run_id") for r in runs if not (r.get("container_session_id") or "").strip()
        ]
        if missing_container:
            return False, (
                f"arm {label}: container_session_id missing on "
                f"{len(missing_container)} of {len(runs)} valid runs "
                f"({', '.join(str(m) for m in missing_container[:3])})"
            )
        missing_baseline = [
            r.get("run_id") for r in runs if not (r.get("runtime_state_generation_baseline") or "").strip()
        ]
        if missing_baseline:
            return False, (
                f"arm {label}: runtime_state_generation_baseline missing on "
                f"{len(missing_baseline)} of {len(runs)} valid runs "
                f"({', '.join(str(m) for m in missing_baseline[:3])}) — "
                f"container_session_id present but construction baseline not corroborated"
            )
        return True, ""

    freshness_ready_a, freshness_reason_a = _freshness_ready(valid_a, "A")
    freshness_ready_b, freshness_reason_b = _freshness_ready(valid_b, "B")
    if freshness_ready_a and freshness_ready_b:
        # Corroboration: each arm must carry exactly ONE runtime-state
        # generation baseline, and it must be shared by all its runs.
        if len(baselines_a) > 1 or len(baselines_b) > 1:
            snapshot_per_arm_fresh: bool | None = None
            baseline_inconsistency = "; ".join(
                r
                for r in (
                    f"arm A: {len(baselines_a)} distinct runtime_state_generation_baseline values"
                    if len(baselines_a) > 1 else "",
                    f"arm B: {len(baselines_b)} distinct runtime_state_generation_baseline values"
                    if len(baselines_b) > 1 else "",
                )
                if r
            )
            freshness_not_ready_reason = (
                f"inconsistent runtime_state_generation_baseline within an arm ({baseline_inconsistency})"
            )
        else:
            snapshot_per_arm_fresh = bool(set(containers_a).isdisjoint(containers_b))
            freshness_not_ready_reason = ""
    else:
        snapshot_per_arm_fresh = None
        freshness_not_ready_reason = "; ".join(
            r for r in (freshness_reason_a, freshness_reason_b) if r
        )
    snapshot_consistent_within_arm = {
        "A": _consistency(containers_a) if freshness_ready_a else None,
        "B": _consistency(containers_b) if freshness_ready_b else None,
    }
    # C3 primary availability: if either arm lacks the C3 source entirely, the
    # C3 primary is unavailable for that arm and the report says so explicitly
    # (legacy metric stays informational and clearly labelled).
    c3_available_a = any(r.get("non_scheduling_ms") is not None for r in valid_a)
    c3_available_b = any(r.get("non_scheduling_ms") is not None for r in valid_b)
    image_ids = _unique_nonempty(valid_a + valid_b, "image_id")
    lineage_consistent = _consistency(image_ids)
    wf_prefixes = _unique_nonempty(valid_a + valid_b, "workflow_hash_prefix")
    workflow_consistent = _consistency(wf_prefixes)
    cold_verified = _cold_verified(valid_a + valid_b)

    # Host / B1 stratification context (informational; never validity inputs).
    host_fps_a = _unique_nonempty(valid_a, "host_fingerprint")
    host_fps_b = _unique_nonempty(valid_b, "host_fingerprint")

    def _b1_reload_any(runs: list[dict[str, Any]]) -> bool | None:
        if not runs:
            return None
        return any(
            r.get("runtime_state_reload_invoked")
            or (_num(r.get("reload_runtime_state_ms")) or 0) > 0
            for r in runs
        )

    b1_reload_any_a = _b1_reload_any(valid_a)
    b1_reload_any_b = _b1_reload_any(valid_b)

    # Scheduling contamination: computed AFTER primary classification.
    sched_stats_a = compute_arm_stats(valid_a, "scheduling_ms")
    sched_stats_b = compute_arm_stats(valid_b, "scheduling_ms")
    sched_med_a = sched_stats_a["median"]
    sched_med_b = sched_stats_b["median"]
    primary_deltas = [
        abs(metrics[m]["delta_ms"])
        for m in primary_metrics
        if metrics[m].get("delta_ms") is not None
    ]
    max_primary_delta = max(primary_deltas) if primary_deltas else 0.0
    sched_delta = abs(sched_med_b - sched_med_a) if sched_med_a is not None and sched_med_b is not None else None
    if (
        sched_med_a is not None
        and sched_med_b is not None
        and sched_delta is not None
        and sched_delta > 0
        and sched_delta > max_primary_delta
    ):
        sched_flag = True
        sched_reason = (
            f"scheduling medians differ by {sched_delta:.3f} ms, which exceeds the "
            f"max primary-metric delta of {max_primary_delta:.3f} ms"
        )
    else:
        sched_flag = False
        sched_reason = (
            f"scheduling medians differ by "
            f"{'unavailable' if sched_delta is None else f'{sched_delta:.3f} ms'} "
            f"(max primary-metric delta {max_primary_delta:.3f} ms)"
        )
    scheduling_contamination = {
        "median_scheduling_a": sched_med_a,
        "median_scheduling_b": sched_med_b,
        "flag": sched_flag,
        "reason": sched_reason,
    }

    # ── Capture-time evidence ──
    capture_evidence: dict[str, Any] = {}
    for label, runs in (("A", valid_a), ("B", valid_b)):
        arm_cap: dict[str, Any] = {}
        for key in _CAPTURE_KEYS:
            arm_cap[key] = compute_arm_stats(runs, key)
        arm_cap["malloc_trim_results"] = sorted(
            {str(r.get("malloc_trim_result")) for r in runs if r.get("malloc_trim_result") is not None}
        )
        capture_evidence[label] = arm_cap
    capture_evidence["note"] = (
        "Allocator/RSS evidence alone never constitutes startup evidence; the "
        "causal verdict uses only the scheduling-free primary timing metrics."
    )

    # ── Secondary ──
    secondary: dict[str, Any] = {}
    for label, runs in (("A", valid_a), ("B", valid_b)):
        arm_sec: dict[str, Any] = {}
        for key in _SECONDARY_KEYS:
            arm_sec[key] = compute_arm_stats(runs, key)
        arm_sec["providers"] = _unique_nonempty(runs, "provider")
        arm_sec["regions"] = _unique_nonempty(runs, "region")
        secondary[label] = arm_sec

    # ── Overall verdict (primary metrics only; modal startup excluded) ──
    primary_cls = [metrics[m] for m in primary_metrics]
    confirmed = [c for c in primary_cls if c["classification"] == "CONFIRMED"]
    supported = [c for c in primary_cls if c["classification"] == "SUPPORTED INFERENCE"]
    confirmed_dirs = {c["direction"] for c in confirmed}
    if confirmed and len(confirmed_dirs) == 1:
        classification = "CONFIRMED"
    elif supported and not confirmed:
        classification = "SUPPORTED INFERENCE"
    else:
        classification = "INSUFFICIENT DATA"

    present_dirs = [c["direction"] for c in primary_cls if c["direction"] != "none"]
    if not present_dirs:
        direction = "none"
    elif "B faster" in present_dirs and "B slower" in present_dirs:
        direction = "mixed"
    else:
        direction = (
            "B faster" if present_dirs.count("B faster") >= present_dirs.count("B slower") else "B slower"
        )

    sufficient_for_conclusion = classification in {"CONFIRMED", "SUPPORTED INFERENCE"}

    if classification == "CONFIRMED":
        stop_recommendation = "STOP — clear A/B difference (CONFIRMED)"
    elif classification == "SUPPORTED INFERENCE":
        stop_recommendation = "consider expanding toward 5 valid runs/arm only if consistency requires it"
    elif (
        len(valid_a) >= 2
        and len(valid_b) >= 2
        and all(
            c.get("delta_ms") is not None and abs(c["delta_ms"]) <= noise_floor_ms
            for c in primary_cls
        )
    ):
        stop_recommendation = "STOP — no measurable difference within noise floor"
    else:
        stop_recommendation = "expand to at least 3 valid runs per arm (max 5) before concluding"

    # ── RSS-drop-without-startup-claim flag ──
    cap_delta_a = capture_evidence["A"]["delta_rss_kb"]
    cap_delta_b = capture_evidence["B"]["delta_rss_kb"]
    med_a = cap_delta_a["median"] if cap_delta_a.get("median_meaningful") else None
    med_b = cap_delta_b["median"] if cap_delta_b.get("median_meaningful") else None
    rss_reduced = med_b is not None and (med_a is None or med_b < med_a)
    startup_win_b = classification in {"CONFIRMED", "SUPPORTED INFERENCE"} and direction == "B faster"
    rss_drop_without_startup_win = bool(rss_reduced and not startup_win_b)

    return {
        "run_count_a": len(arm_a_runs),
        "run_count_b": len(arm_b_runs),
        "valid_count_a": len(valid_a),
        "valid_count_b": len(valid_b),
        "excluded_a": excluded_a,
        "excluded_b": excluded_b,
        "protocol": {
            "flag_verified_a": flag_verified_a,
            "flag_verified_b": flag_verified_b,
            "snapshot_identities_a": snap_a,
            "snapshot_identities_b": snap_b,
            "container_sessions_a": containers_a,
            "container_sessions_b": containers_b,
            "baselines_a": baselines_a,
            "baselines_b": baselines_b,
            "freshness_source": "container_session_id (+ runtime_state_generation_baseline corroboration); restore_session_id is per-restore correlation only",
            "freshness_ready_a": freshness_ready_a,
            "freshness_ready_b": freshness_ready_b,
            "freshness_not_ready_reason": freshness_not_ready_reason,
            "snapshot_per_arm_fresh": snapshot_per_arm_fresh,
            "snapshot_consistent_within_arm": snapshot_consistent_within_arm,
            "c3_primary_available_a": c3_available_a,
            "c3_primary_available_b": c3_available_b,
            "lineage_consistent": lineage_consistent,
            "workflow_consistent": workflow_consistent,
            "cold_verified": cold_verified,
            "scheduling_contamination": scheduling_contamination,
            "host_fingerprints_a": host_fps_a,
            "host_fingerprints_b": host_fps_b,
            "b1_reload_invoked_any_a": b1_reload_any_a,
            "b1_reload_invoked_any_b": b1_reload_any_b,
        },
        "primary_metrics": primary_metrics,
        "metrics": metrics,
        "capture_evidence": capture_evidence,
        "secondary": secondary,
        "overall": {
            "classification": classification,
            "direction": direction,
            "sufficient_for_conclusion": sufficient_for_conclusion,
            "stop_recommendation": stop_recommendation,
            "rss_drop_without_startup_win": rss_drop_without_startup_win,
        },
        "arms": {
            "A": {"valid": valid_a, "excluded": excluded_a},
            "B": {"valid": valid_b, "excluded": excluded_b},
        },
    }


# ────────────────────────────────────────────────────────────────────────────
# Rendering
# ────────────────────────────────────────────────────────────────────────────


def _fmt(value: Any) -> str:
    if value is None or value == UNAVAILABLE or value == "":
        return "unavailable"
    if isinstance(value, float):
        return f"{value:,.3f}"
    return str(value)


def _bool_text(value: Any) -> str:
    if value is True:
        return "yes"
    if value is False:
        return "no"
    return "unavailable"


def _stats_table_rows(arm_label: str, stats: dict[str, Any]) -> str:
    return (
        f"| {arm_label} | {stats.get('count', 0)} | {_fmt(stats.get('median'))} "
        f"| {_fmt(stats.get('mean'))} | {_fmt(stats.get('min'))} | {_fmt(stats.get('max'))} "
        f"| {_fmt(stats.get('p90'))} |"
    )


def _protocol_check_line(name: str, value: Any, explanation: str) -> str:
    if value is True:
        return f"- **{name}**: **True** — {explanation}"
    if value is False:
        return f"- **{name}**: **False** — **WARNING** — {explanation}"
    if value is None:
        return f"- **{name}**: **None** — **UNVERIFIED** — {explanation}"
    return f"- **{name}**: `{value}` — {explanation}"


def render_report(analysis: dict[str, Any]) -> str:
    """Render the full Markdown report (style mirrors ``variance_report.py``)."""
    overall = analysis["overall"]
    protocol = analysis["protocol"]
    arms = analysis["arms"]
    lines: list[str] = []

    lines.append("# V2 Snapshot-Allocator Hygiene A/B — Analysis Report")
    lines.append("")
    lines.append(
        "Protocol: **A** = `COMFYMODAL_V2_SNAPSHOT_ALLOCATOR_HYGIENE=0` (or absent), "
        "**B** = `COMFYMODAL_V2_SNAPSHOT_ALLOCATOR_HYGIENE=1`.  Hygiene acts at snapshot "
        "capture time, so a fresh snapshot is required per arm.  The primary command metric is "
        "the Batch-C3 `non_scheduling_ms` (COMMAND -> RESPONSE minus scheduling time, where "
        "scheduling time = command->Modal enqueue + Modal placement); the legacy placement-only "
        "subtraction is informational only and never mixed in.  RSS evidence never constitutes "
        "startup evidence."
    )
    lines.append("")
    lines.append(
        "Freshness is proven by the per-construction container session "
        "(`_restore_timing.container_session_id`), corroborated by the runtime-state generation "
        "baseline (`_restore_timing.runtime_state_generation_baseline`).  `restore_session_id` "
        "is a PER-RESTORE uuid (fresh per request, `modal_app.py:9529`) and is demoted to "
        "per-restore correlation — never a freshness input.  `snapshot_identity` (stable model "
        "hash, intentionally identical across A/B) is lineage-only.  A missing construction "
        "identity (no `container_session_id` and no baseline, or an inconsistent baseline) is a "
        "**NOT READY** fail-closed state — never silently fresh."
    )
    lines.append("")

    # ── Run records ──
    lines.append("## Run records")
    lines.append("")
    lines.append(
        "| run_id | arm | valid | flag | cold | container | baseline | restore session | snapshot | "
        "cmd→resp ms | sched ms | C3 non-sched ms | legacy excl ms | modal startup ms | "
        "pre-python restore ms | app restore ms | before RSS kB | Δ RSS kB | hygiene wall ms | "
        "sampling ms | host fp | region | B1 decision | bootstrap ms | gpu-state ms | residual ms |"
    )
    lines.append("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    all_records = arms["A"]["valid"] + arms["A"]["excluded"] + arms["B"]["valid"] + arms["B"]["excluded"]
    for r in all_records:
        lines.append(
            f"| {r.get('run_id', 'unavailable')} | {r.get('arm', 'unavailable')} | "
            f"{'yes' if r.get('valid') else 'no'} | {_fmt(r.get('hygiene_flag_raw'))} | "
            f"{_bool_text(r.get('cold'))} | {_fmt(r.get('container_session_id'))} | "
            f"{_fmt(r.get('runtime_state_generation_baseline'))} | {_fmt(r.get('restore_session_id'))} | "
            f"{_fmt(r.get('snapshot_identity'))} | "
            f"{_fmt(r.get('command_response_ms'))} | {_fmt(r.get('scheduling_ms'))} | "
            f"{_fmt(r.get('non_scheduling_ms'))} | {_fmt(r.get('legacy_placement_excluded_ms'))} | "
            f"{_fmt(r.get('modal_startup_ms'))} | "
            f"{_fmt(r.get('pre_python_snapshot_restore_ms'))} | {_fmt(r.get('application_restore_ms'))} | "
            f"{_fmt(r.get('before_rss_kb'))} | {_fmt(r.get('delta_rss_kb'))} | "
            f"{_fmt(r.get('hygiene_wall_ms'))} | {_fmt(r.get('sampling_ms'))} | "
            f"{_fmt(str(r.get('host_fingerprint') or '')[:12])} | "
            f"{_fmt(r.get('region'))} | "
            f"{_fmt(r.get('runtime_state_reload_decision'))} | "
            f"{_fmt(r.get('restore_bootstrap_ms'))} | "
            f"{_fmt(r.get('restore_gpu_state_ms'))} | "
            f"{_fmt(r.get('restore_residual_ms'))} |"
        )
    excluded_all = arms["A"]["excluded"] + arms["B"]["excluded"]
    if excluded_all:
        lines.append("")
        lines.append("#### Excluded runs")
        for r in excluded_all:
            reasons = "; ".join(r.get("invalid_reasons", [])) or "no reason"
            lines.append(f"- `{r.get('run_id', 'unavailable')}` ({r.get('source_path', 'unavailable')}): {reasons}")
    lines.append("")

    # ── Protocol checks ──
    lines.append("## Protocol checks")
    lines.append("")
    lines.append(_protocol_check_line(
        "flag_verified (A)", protocol["flag_verified_a"],
        "every valid A run's captured flag is falsy/absent as expected (\"0\" or absent)",
    ))
    lines.append(_protocol_check_line(
        "flag_verified (B)", protocol["flag_verified_b"],
        "every valid B run's captured flag is truthy as expected (\"1\")",
    ))
    fresh_ready_a = protocol.get("freshness_ready_a")
    fresh_ready_b = protocol.get("freshness_ready_b")
    if fresh_ready_a is True and fresh_ready_b is True:
        lines.append(_protocol_check_line(
            "snapshot_per_arm_fresh", protocol["snapshot_per_arm_fresh"],
            "both arms carry one consistent container_session_id per run, corroborated by a single "
            "runtime_state_generation_baseline per arm, and the arm container sets are disjoint "
            "(fresh snapshot per arm, proven by the per-construction container session)",
        ))
        lines.append(_protocol_check_line(
            "snapshot_consistent_within_arm", protocol["snapshot_consistent_within_arm"],
            "each arm uses exactly one construction container (container_session_id)",
        ))
    else:
        reason = protocol.get("freshness_not_ready_reason") or "container_session_id / baseline missing"
        lines.append(
            f"- **snapshot_per_arm_fresh**: **NOT READY** — **fail-closed** — {reason}. "
            "Construction-session freshness cannot be claimed: at least one valid run is missing "
            "`_restore_timing.container_session_id` (or its `runtime_state_generation_baseline` is "
            "missing/inconsistent). Never treat this as a proven fresh-snapshot experiment."
        )
        lines.append(_protocol_check_line(
            "snapshot_consistent_within_arm", None,
            "within-arm consistency unverifiable while the construction identity is missing",
        ))
    lines.append(
        f"- **freshness_source**: `container_session_id` + `runtime_state_generation_baseline` "
        f"corroboration (`restore_session_id` is per-restore correlation only; `snapshot_identity` "
        f"is lineage/model information only). Containers A=`{_fmt(', '.join(protocol['container_sessions_a']) or 'unavailable')}`, "
        f"B=`{_fmt(', '.join(protocol['container_sessions_b']) or 'unavailable')}`; baselines "
        f"A=`{_fmt(', '.join(protocol['baselines_a']) or 'unavailable')}`, "
        f"B=`{_fmt(', '.join(protocol['baselines_b']) or 'unavailable')}`."
    )
    lines.append(_protocol_check_line(
        "lineage_consistent", protocol["lineage_consistent"],
        "exactly one unique image_id across both arms",
    ))
    lines.append(_protocol_check_line(
        "workflow_consistent", protocol["workflow_consistent"],
        "exactly one unique workflow_hash_prefix across both arms",
    ))
    lines.append(_protocol_check_line(
        "cold_verified", protocol["cold_verified"],
        "every valid run is a cold run (restore_count==1 and request_count==1)",
    ))
    c3_a = protocol.get("c3_primary_available_a")
    c3_b = protocol.get("c3_primary_available_b")
    if c3_a is False or c3_b is False:
        c3_side = "A" if c3_a is False else "B"
        lines.append(
            f"- **c3_primary_available**: A={'yes' if c3_a else 'NO'}, B={'yes' if c3_b else 'NO'} — "
            f"**WARNING**: arm {c3_side} lacks the C3 sources (no reconciled `non_scheduling_ms` and no "
            f"`command_to_enqueue_ms` for the fallback), so the C3 primary is unavailable on that arm. "
            f"The legacy placement-excluded metric is informational and clearly labelled and is never "
            f"mixed into the C3 comparison."
        )
    else:
        lines.append(
            f"- **c3_primary_available**: A=`{'yes' if c3_a else 'no'}`, B=`{'yes' if c3_b else 'no'}` — "
            f"C3 `non_scheduling_ms` resolved on both arms (reconciled waterfall or C3 fallback arithmetic)."
        )
    sched = protocol["scheduling_contamination"]
    sched_line = (
        f"- **scheduling_contamination**: median scheduling A=`{_fmt(sched.get('median_scheduling_a'))}`, "
        f"B=`{_fmt(sched.get('median_scheduling_b'))}`; flag **{sched.get('flag')}** — {sched.get('reason')}"
    )
    if sched.get("flag"):
        sched_line += " — **WARNING: scheduling dominates the observed timing differences**"
    lines.append(sched_line)
    lines.append("")

    # ── Host / region stratification (informational) ──
    lines.append("## Host / region stratification")
    lines.append("")
    lines.append(
        "> Informational only — never changes validity or classification.  Stratification "
        "context for a future A/B and operator-side B1 gate checks."
    )
    lines.append("")
    lines.append(
        "| run_id | arm | provider | region | host fingerprint | cpu model | "
        "non_scheduling_ms | application_restore_ms | B1 decision |"
    )
    lines.append("|---|---|---|---|---|---|---|---|---|")
    for r in all_records:
        lines.append(
            f"| {r.get('run_id', 'unavailable')} | {r.get('arm', 'unavailable')} | "
            f"{_fmt(r.get('provider'))} | {_fmt(r.get('region'))} | "
            f"{_fmt(str(r.get('host_fingerprint') or '')[:12])} | {_fmt(r.get('host_cpu_model'))} | "
            f"{_fmt(r.get('non_scheduling_ms'))} | {_fmt(r.get('application_restore_ms'))} | "
            f"{_fmt(r.get('runtime_state_reload_decision'))} |"
        )
    lines.append("")
    for label in ("A", "B"):
        regions = analysis["secondary"].get(label, {}).get("regions") or []
        fps = protocol.get(f"host_fingerprints_{label.lower()}") or []
        lines.append(
            f"- Arm {label} regions: {', '.join(regions) if regions else 'unavailable'}; "
            f"host fingerprints: {', '.join(fps) if fps else 'unavailable'}"
        )
        if len(regions) > 1 or len(fps) > 1:
            lines.append(
                f"  - **WARNING**: Arm {label} spans multiple regions/host fingerprints — "
                "observed differences must NOT be attributed to the hygiene flag without stratification."
            )
    b1_runs = [
        r for r in all_records
        if r.get("valid")
        and (r.get("runtime_state_reload_invoked") or (_num(r.get("reload_runtime_state_ms")) or 0) > 0)
    ]
    if b1_runs:
        reload_ms = ", ".join(_fmt(r.get("reload_runtime_state_ms")) for r in b1_runs)
        lines.append(
            f"- **WARNING**: B1 runtime-state volume reload observed on {len(b1_runs)} valid run(s) "
            f"(reload_ms={reload_ms}) — operator-side B1 gate (invoked=False, reload <= 10 ms) must "
            "be checked before treating the run as structurally valid."
        )
    lines.append("")

    # ── Primary metrics ──
    lines.append("## Primary metrics")
    lines.append("")
    lines.append("> median only when n>=2; p90 only when n>=5.")
    lines.append("")
    lines.append(
        "> `non_scheduling_ms` is the Batch-C3 primary: COMMAND -> RESPONSE minus scheduling "
        "time (scheduling time = command->Modal enqueue + Modal placement), taken from the "
        "reconciled waterfall (`final_reconciled_waterfall.non_scheduling_ms`) or the C3 "
        "fallback arithmetic. The legacy placement-only metric is reported separately as "
        "informational and is never mixed into this comparison."
    )
    lines.append("")
    for metric in analysis["primary_metrics"]:
        m = analysis["metrics"][metric]
        lines.append(f"### {metric}")
        lines.append("")
        lines.append("| arm | n | median | mean | min | max | p90 |")
        lines.append("|---|---:|---:|---:|---:|---:|---:|")
        lines.append(_stats_table_rows("A", m["stats_a"]))
        lines.append(_stats_table_rows("B", m["stats_b"]))
        lines.append("")
        lines.append(
            f"B − A delta: {_fmt(m.get('delta_ms'))} ms — direction: `{m.get('direction')}` — "
            f"classification: **{m.get('classification')}**"
        )
        lines.append(f"Reason: {m.get('reason')}")
        lines.append("")

    # ── Legacy placement-only metric (informational) ──
    lines.append("### legacy_placement_excluded_ms (legacy/partial — informational only)")
    lines.append("")
    lines.append(
        "> Old pre-C3 metric: `command_response_ms − placement scheduling_ms`.  This is "
        "placement-only subtraction and is NOT the accepted Batch-C3 metric.  It is clearly "
        "labelled as legacy/partial and is NEVER silently mixed with the true C3 "
        "`non_scheduling_ms` in one A/B comparison — if either arm lacks the C3 sources the C3 "
        "primary is unavailable for that arm (see Protocol checks) and this metric stays "
        "informational."
    )
    lines.append("")
    lm = analysis["metrics"]["legacy_placement_excluded_ms"]
    lines.append("| arm | n | median | mean | min | max | p90 |")
    lines.append("|---|---:|---:|---:|---:|---:|---:|")
    lines.append(_stats_table_rows("A", lm["stats_a"]))
    lines.append(_stats_table_rows("B", lm["stats_b"]))
    lines.append("")
    lines.append(
        f"B − A delta: {_fmt(lm.get('delta_ms'))} ms — direction: `{lm.get('direction')}` — "
        f"classification: **{lm.get('classification')}**"
    )
    lines.append(f"Reason: {lm.get('reason')}")
    lines.append("")

    # ── Modal startup (informational) ──
    lines.append("### Modal startup (scheduling-inclusive, excluded from verdict)")
    lines.append("")
    lines.append(
        "> `modal_startup_ms` includes platform scheduling and is informational only — it is "
        "excluded from the causal verdict."
    )
    lines.append("")
    mm = analysis["metrics"]["modal_startup_ms"]
    lines.append("| arm | n | median | mean | min | max | p90 |")
    lines.append("|---|---:|---:|---:|---:|---:|---:|")
    lines.append(_stats_table_rows("A", mm["stats_a"]))
    lines.append(_stats_table_rows("B", mm["stats_b"]))
    lines.append("")
    lines.append(
        f"B − A delta: {_fmt(mm.get('delta_ms'))} ms — direction: `{mm.get('direction')}` — "
        f"classification: **{mm.get('classification')}**"
    )
    lines.append(f"Reason: {mm.get('reason')}")
    lines.append("")

    # ── Capture-time evidence ──
    lines.append("## Capture-time evidence (allocator hygiene)")
    lines.append("")
    ce = analysis["capture_evidence"]
    for label in ("A", "B"):
        lines.append(f"### Arm {label}")
        lines.append("")
        lines.append("| metric | n | median | mean | min | max | p90 |")
        lines.append("|---|---:|---:|---:|---:|---:|---:|")
        for key in _CAPTURE_KEYS:
            lines.append(_stats_capture_row(key, ce[label][key]))
        trim_results = ce[label].get("malloc_trim_results") or []
        lines.append("")
        lines.append(f"- malloc_trim results: {', '.join(trim_results) if trim_results else 'unavailable'}")
        lines.append("")
    lines.append(f"> {ce.get('note')}")
    if overall.get("rss_drop_without_startup_win"):
        lines.append("> RSS dropped under hygiene (B) but the startup verdict is not based on RSS — see classification above.")
    lines.append("")

    # ── Secondary metrics ──
    lines.append("## Secondary metrics")
    lines.append("")
    lines.append("> median only when n>=2; p90 only when n>=5.")
    lines.append("")
    secondary = analysis["secondary"]
    for label in ("A", "B"):
        lines.append(f"### Arm {label}")
        lines.append("")
        lines.append("| metric | n | median | mean | min | max | p90 |")
        lines.append("|---|---:|---:|---:|---:|---:|---:|")
        for key in _SECONDARY_KEYS:
            lines.append(_stats_capture_row(key, secondary[label][key]))
        providers = secondary[label].get("providers") or []
        regions = secondary[label].get("regions") or []
        lines.append("")
        lines.append(
            f"- Providers: {', '.join(providers) if providers else 'unavailable'}; "
            f"regions: {', '.join(regions) if regions else 'unavailable'}"
        )
        lines.append("")

    # ── Verdict ──
    lines.append("## Verdict")
    lines.append("")
    lines.append(f"- Classification: **{overall['classification']}**")
    lines.append(f"- Direction: `{overall['direction']}`")
    lines.append(f"- Sufficient for conclusion: `{overall['sufficient_for_conclusion']}`")
    lines.append(f"- Recommendation: {overall['stop_recommendation']}")
    lines.append("")
    lines.append("## Limitations")
    lines.append("")
    lines.append("- **Flag unverified**: no `effective_env`/`env`/`runtime_env` flag value was found "
                 "in at least one run; an absent flag is unverifiable, not a validation failure.")
    lines.append("- **Freshness NOT READY**: at least one valid run was missing "
                 "`_restore_timing.container_session_id` (or its "
                 "`runtime_state_generation_baseline` was missing/inconsistent); construction-session "
                 "freshness could not be established and is never claimed silently (fail-closed). "
                 "`restore_session_id` is per-restore correlation only and is not a freshness input. "
                 "`snapshot_identity` is the stable model hash and is not a freshness proof.")
    lines.append("- **C3 primary unavailable**: at least one arm lacked the C3 sources (no "
                 "reconciled `non_scheduling_ms` and no `command_to_enqueue_ms` for the fallback), so "
                 "the C3 primary could not be computed for that arm; legacy placement-excluded values "
                 "are informational only.")
    lines.append("- **Cold unverified**: some valid runs did not prove `restore_count==1`/`request_count==1`.")
    lines.append("- **n=1 median policy**: medians/means require at least 2 samples and p90 requires "
                 "at least 5; a single sample never yields a meaningful median or p90.")
    lines.append("- **Scheduling-inclusive modal startup**: `modal_startup_ms` includes platform "
                 "scheduling and is excluded from the causal verdict.")
    lines.append("")
    return "\n".join(lines)


def _stats_capture_row(label: str, stats: dict[str, Any]) -> str:
    return (
        f"| {label} | {stats.get('count', 0)} | {_fmt(stats.get('median'))} "
        f"| {_fmt(stats.get('mean'))} | {_fmt(stats.get('min'))} | {_fmt(stats.get('max'))} "
        f"| {_fmt(stats.get('p90'))} |"
    )


# ────────────────────────────────────────────────────────────────────────────
# CLI
# ────────────────────────────────────────────────────────────────────────────


def _summary_block(analysis: dict[str, Any]) -> str:
    overall = analysis["overall"]
    lines = [
        f"valid runs: A={analysis['valid_count_a']} B={analysis['valid_count_b']}",
        f"overall: {overall['classification']} ({overall['direction']})",
        "primary: " + "; ".join(
            f"{m} → {analysis['metrics'][m]['classification']}" for m in analysis["primary_metrics"]
        ),
        f"recommendation: {overall['stop_recommendation']}",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    # The report uses Unicode (arrows/deltas); force UTF-8 on consoles that
    # would otherwise choke on cp1252 and raise UnicodeEncodeError.
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    parser = argparse.ArgumentParser(
        prog="benchmark_v2_snapshot_hygiene_ab",
        description=(
            "Offline causal A/B analysis for COMFYMODAL_V2_SNAPSHOT_ALLOCATOR_HYGIENE "
            "(A = hygiene off / flag 0 or absent, B = hygiene on / flag 1). Primary command "
            "metric is Batch-C3 non_scheduling_ms; snapshot freshness uses container_session_id "
            "with runtime_state_generation_baseline corroboration (fail-closed). Never executes benchmarks."
        ),
    )
    parser.add_argument("--arm-a", required=True, metavar="PATH",
                        help="arm A input: a directory of run_*.json artifacts or a single run JSON")
    parser.add_argument("--arm-b", required=True, metavar="PATH",
                        help="arm B input: a directory of run_*.json artifacts or a single run JSON")
    parser.add_argument("--out", default=None, metavar="PATH",
                        help="write the Markdown report to PATH (default: stdout)")
    parser.add_argument("--json", default=None, dest="json_out", metavar="PATH",
                        help="write the analysis dict as JSON to PATH")
    parser.add_argument("--noise-floor-ms", type=float, default=1.0,
                        help="difference floor below which a delta is not measurable (default: 1.0)")
    parser.add_argument("--min-confirmed", type=int, default=3,
                        help="min per-arm samples for CONFIRMED (default: 3)")
    args = parser.parse_args(argv)

    records_a, excluded_a = load_arm_runs(args.arm_a, "A", "0")
    records_b, excluded_b = load_arm_runs(args.arm_b, "B", "1")
    analysis = analyze(
        records_a + excluded_a,
        records_b + excluded_b,
        noise_floor_ms=args.noise_floor_ms,
        min_confirmed=args.min_confirmed,
    )
    report = render_report(analysis)
    if args.out:
        Path(args.out).write_text(report, encoding="utf-8")
    else:
        print(report)
    if args.json_out:
        Path(args.json_out).write_text(
            json.dumps(analysis, indent=2, sort_keys=True), encoding="utf-8"
        )
    print("")
    print("── Summary ─────────────────────────────────────────────")
    print(_summary_block(analysis))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
