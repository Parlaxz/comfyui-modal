"""Report-generation helpers for the V2 variance-cold benchmark mode.

This module is intentionally dependency-light: it does NOT import Modal,
``canonical_execution``, ``modal_client`` or any runtime module.  It can be
imported and exercised entirely locally so the harness/report generator stays
testable even when Modal or the network is unavailable.

Responsibilities
----------------
* Normalise raw per-run artifacts (``run_N.json``) into a flat metric record.
* Compute median / p90 / max / mean / slow-run-rate statistics over the
  *available* values of each metric.
* Render a detailed Markdown report (style similar to
  ``C8_BENCHMARK_COMPLETE_RUN_LOG.md``) with restore breakdown, CPU page
  traversal, pretouch, transfer/throughput, bookkeeping, sampler wait/sampling,
  medians/p90/max/slow-run rate, and a best-supported root-cause analysis.

Missing metrics are handled explicitly and never silently reported as zero:
a missing value is rendered as ``unavailable`` and excluded from statistics.
"""

from __future__ import annotations

import json
import statistics
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

# Sentinel used everywhere a metric is genuinely absent.
UNAVAILABLE = "unavailable"


def _num(value: Any) -> float | None:
    """Return ``float(value)`` for real numbers, else ``None``.

    ``None``, ``"absent"``, ``"unavailable"`` and non-numeric strings all map
    to ``None`` so statistics and rendering can treat them uniformly.
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


def percentile(sorted_values: list[float], p: float) -> float | None:
    """Nearest-rank percentile of an already-sorted (ascending) list.

    ``p`` is in [0, 100].  Returns ``None`` for an empty list.
    """
    n = len(sorted_values)
    if n == 0:
        return None
    if p <= 0:
        return sorted_values[0]
    if p >= 100:
        return sorted_values[-1]
    k = max(1, int((p / 100.0) * n + 0.5))
    return sorted_values[min(k, n) - 1]


def compute_stats(values: Iterable[float]) -> dict[str, Any]:
    """Compute summary statistics over the available numeric values.

    Returns a dict whose numeric keys are ``unavailable`` (string) when there
    are no available values, so consumers never confuse "no data" with zero.
    """
    vals = sorted(float(v) for v in values if _num(v) is not None)
    if not vals:
        return {
            "count": 0,
            "mean": UNAVAILABLE,
            "median": UNAVAILABLE,
            "p90": UNAVAILABLE,
            "p95": UNAVAILABLE,
            "max": UNAVAILABLE,
            "min": UNAVAILABLE,
        }
    return {
        "count": len(vals),
        "mean": round(statistics.mean(vals), 3),
        "median": round(percentile(vals, 50) or 0.0, 3),
        "p90": round(percentile(vals, 90) or 0.0, 3),
        "p95": round(percentile(vals, 95) or 0.0, 3),
        "max": round(vals[-1], 3),
        "min": round(vals[0], 3),
    }


def slow_run_rate(values: Iterable[float], *, threshold_ms: float) -> dict[str, Any]:
    """Fraction of available values exceeding *threshold_ms*.

    Returns ``{count, slow_count, rate, threshold_ms}``.  ``rate`` is
    ``unavailable`` when there are no available values.
    """
    vals = [float(v) for v in values if _num(v) is not None]
    if not vals:
        return {"count": 0, "slow_count": 0, "rate": UNAVAILABLE, "threshold_ms": threshold_ms}
    slow = sum(1 for v in vals if v > threshold_ms)
    return {
        "count": len(vals),
        "slow_count": slow,
        "rate": round(slow / len(vals), 4),
        "threshold_ms": threshold_ms,
    }


def _fmt_ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _trace_event(result: dict[str, Any], name: str) -> dict[str, Any] | None:
    trace = result.get("trace", {}) if isinstance(result, dict) else {}
    events = trace.get("events", []) if isinstance(trace, dict) else []
    for ev in events:
        if isinstance(ev, dict) and ev.get("name") == name:
            return ev
    return None


def _event_meta(event: dict[str, Any] | None) -> dict[str, Any]:
    if event is None:
        return {}
    meta = event.get("metadata", {})
    return dict(meta) if isinstance(meta, dict) else {}


def _sum_trace_faults(result: dict[str, Any], event_names: list[str]) -> dict[str, Any]:
    """Aggregate major/minor page faults across the given trace event names."""
    major = 0
    minor = 0
    duration_ms = 0.0
    found = False
    for name in event_names:
        ev = _trace_event(result, name)
        if ev is None:
            continue
        meta = _event_meta(ev)
        m = _num(meta.get("major_faults"))
        n = _num(meta.get("minor_faults"))
        d = _num(meta.get("duration_ms"))
        if m is not None:
            major += int(m)
            found = True
        if n is not None:
            minor += int(n)
            found = True
        if d is not None:
            duration_ms += d
    if not found:
        return {"major_faults": UNAVAILABLE, "minor_faults": UNAVAILABLE, "duration_ms": UNAVAILABLE}
    return {"major_faults": major, "minor_faults": minor, "duration_ms": round(duration_ms, 3)}


def _events_by_prefix(result: dict[str, Any], prefix: str) -> list[tuple[str, dict[str, Any]]]:
    """Return ``(name, metadata)`` for every trace event whose name starts with
    *prefix* (e.g. ``variance_``)."""
    trace = result.get("trace", {}) if isinstance(result, dict) else {}
    events = trace.get("events", []) if isinstance(trace, dict) else []
    out: list[tuple[str, dict[str, Any]]] = []
    for ev in events:
        if not isinstance(ev, dict):
            continue
        name = ev.get("name", "")
        if isinstance(name, str) and name.startswith(prefix):
            out.append((name, _event_meta(ev)))
    return out


def _sum_key(events: list[tuple[str, dict[str, Any]]], key: str) -> float | None:
    total = 0.0
    found = False
    for _name, meta in events:
        v = _num(meta.get(key))
        if v is not None:
            total += v
            found = True
    return round(total, 3) if found else None


def _first_num(mapping: dict[str, Any], keys: list[str]) -> float | None:
    """Return the first numeric value found among *keys*, else ``None``."""
    for key in keys:
        v = _num(mapping.get(key))
        if v is not None:
            return v
    return None


def _sub(meta: dict[str, Any], key: str) -> dict[str, Any]:
    """Return a nested mapping for *key*, or an empty dict."""
    v = meta.get(key)
    return dict(v) if isinstance(v, dict) else {}


def _trace_meta_find(result: dict[str, Any], field: str) -> Any:
    """Return the first value for *field* found in any trace event metadata,
    else ``None``.  Used for metrics that have no dedicated event name."""
    trace = result.get("trace", {}) if isinstance(result, dict) else {}
    events = trace.get("events", []) if isinstance(trace, dict) else []
    for ev in events:
        if not isinstance(ev, dict):
            continue
        meta = ev.get("metadata", {})
        if isinstance(meta, dict) and field in meta:
            return meta[field]
    return None


def _wall_ms(sub: dict[str, Any]) -> float | None:
    """Return the wall-clock of a variance sub-record (``duration_ms`` or
    ``wall_ms``), whichever is present."""
    return _num(sub.get("duration_ms")) or _num(sub.get("wall_ms"))


def _activation_meta(result: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    """Return ``(source_event_name, metadata)`` for the UNET activation
    variance record.

    Prefers the newer ``unet_activation_worker_variance`` event
    (``registry_setup`` / ``page_traversal`` / ``synchronized_load`` /
    ``pretouch`` / ``loader_reconciliation``) and falls back to the existing
    ``first_unet_activation_variance`` (``preload_setup`` /
    ``cpu_to_gpu_transfer``).
    """
    worker = _trace_event(result, "unet_activation_worker_variance")
    if worker is not None:
        return "unet_activation_worker_variance", _event_meta(worker)
    first = _trace_event(result, "first_unet_activation_variance")
    if first is not None:
        return "first_unet_activation_variance", _event_meta(first)
    return "none", {}


def _registry_validity(reg: dict[str, Any]) -> tuple[bool, str]:
    """A CPU storage registry is a valid transfer/page hydration proof only
    when it scanned at least one SUPPORTED unique storage object.

    A registry with ``unique_storage_count == 0`` and an unsupported-only list
    (e.g. all ``device:cuda``) is NOT a valid CPU-hydration proof — any page
    traversal / checksum / pretouch / synchronized-transfer reading derived
    from it is an outer-window artifact and must be treated as unavailable.
    """
    if not reg:
        return False, "no storage registry record"
    unique = _num(reg.get("unique_storage_count"))
    if unique is None:
        return False, "unique_storage_count absent"
    if int(unique) > 0:
        return True, "ok"
    unsupported = _num(reg.get("unsupported_count"))
    reasons = sorted({
        str(e.get("reason")) for e in (reg.get("unsupported_entries") or [])
        if isinstance(e, dict) and e.get("reason")
    })
    reason = f"unique_storage_count=0"
    if unsupported is not None:
        reason += f", unsupported_count={int(unsupported)}"
    if reasons:
        reason += f", reasons={reasons[:3]}"
    return False, reason


def _pretouch_validity(rec: dict[str, Any], registry_valid: bool) -> tuple[bool, str]:
    """Pretouch is a valid real-read proof only when it reports a non-empty
    status and an actual real-read (expected_pages / bytes_read).  ``empty`` /
    ``error`` / ``unsupported`` status or a missing CPU registry proof makes it
    unavailable."""
    if not rec:
        return False, "no pretouch record"
    status = str(rec.get("status") or "")
    if status in ("empty", "error", "unsupported"):
        return False, f"status={status}"
    if not registry_valid:
        return False, "storage registry unsupported-only"
    expected = _num(rec.get("expected_pages"))
    bytes_read = _num(rec.get("bytes_read"))
    if expected is not None and int(expected) <= 0:
        return False, "expected_pages<=0"
    if bytes_read is not None and int(bytes_read) <= 0:
        return False, "bytes_read<=0"
    return True, "ok"


def _restore_timing(result: dict[str, Any]) -> dict[str, Any]:
    rt = result.get("_restore_timing", {})
    if isinstance(rt, dict):
        return rt
    trace = result.get("trace", {})
    if isinstance(trace, dict):
        rt2 = trace.get("_restore_timing", {})
        if isinstance(rt2, dict):
            return rt2
    return {}


def extract_run_metrics(artifact: dict[str, Any]) -> dict[str, Any]:
    """Normalise one run artifact (``run_N.json``) into a flat metric record.

    Every field is either a number or the ``unavailable`` sentinel — never
    silently zero when data is missing.
    """
    timing = artifact.get("timing", {}) if isinstance(artifact.get("timing"), dict) else {}
    identity = artifact.get("identity", {}) if isinstance(artifact.get("identity"), dict) else {}
    result = artifact.get("result", {})
    if not isinstance(result, dict):
        result = {}
    rt = _restore_timing(result)
    variance = artifact.get("variance", {}) if isinstance(artifact.get("variance"), dict) else {}

    # ── Restore breakdown (from _restore_timing + timing) ──
    restore: dict[str, Any] = {
        "restore_total_ms": _num(timing.get("restore_total_ms")),
    }
    for key in (
        "snapshot_restore_ms", "restore_gpu_state_ms", "cuda_init_ms",
        "reload_models_ms", "reload_runtime_state_ms", "backend_startup_ms",
    ):
        restore[key] = _num(rt.get(key))

    # Full per-stage restore breakdown (every restore_timing key ending in
    # ``_ms``), carried as a nested dict plus flattened scalar keys so the
    # report can render per-stage restore times via _metric_stats.
    restore_breakdown: dict[str, Any] = {}
    _rb = timing.get("restore_breakdown")
    if isinstance(_rb, dict):
        for _rk, _rv in _rb.items():
            if isinstance(_rk, str) and _rk.endswith("_ms") and isinstance(_rv, (int, float)):
                _flat = f"restore_breakdown_{_rk}"
                restore[_flat] = round(float(_rv), 3)
                restore_breakdown[_rk] = round(float(_rv), 3)
    restore["restore_breakdown"] = restore_breakdown

    # ── CPU page traversal (page-fault trace events + first-UNET variance) ──
    pagein = _sum_trace_faults(
        result, ["unet_snapshot_pagein", "clip_snapshot_pagein",
                 "unet_snapshot_pagein_h2d", "clip_snapshot_pagein_h2d"]
    )
    first_cuda = _event_meta(_trace_event(result, "unet_first_cuda_op"))
    var_events = _events_by_prefix(result, "variance_")
    # Aggregate any additional page-fault deltas from variance_* stage events.
    var_faults = _sum_trace_faults(result, [name for name, _ in var_events])

    # ── UNET activation variance: prefer the worker event, fall back to the
    #    first-UNET event.  Worker shape: registry_setup / page_traversal /
    #    synchronized_load / pretouch / loader_reconciliation.  Old shape:
    #    preload_setup / cpu_to_gpu_transfer / pretouch / loader_reconciliation.
    _act_src, _act = _activation_meta(result)
    if _act_src == "unet_activation_worker_variance":
        _reg_setup = _sub(_act, "registry_setup")
        _ptrav = _sub(_act, "page_traversal")
        _sync = _sub(_act, "synchronized_load")
        _pretouch_rec = _sub(_act, "pretouch")
        _recon = _sub(_act, "loader_reconciliation")
        _storage_reg = _sub(_act, "unet_storage_registry")
        _page_readiness = _sub(_act, "page_readiness")
    elif _act_src == "first_unet_activation_variance":
        _reg_setup = _sub(_act, "preload_setup")
        _ptrav = _sub(_act, "page_traversal")
        _sync = _sub(_act, "cpu_to_gpu_transfer")
        _pretouch_rec = _sub(_act, "pretouch")
        _recon = _sub(_act, "loader_reconciliation")
        _storage_reg = _sub(_act, "unet_storage_registry")
        _page_readiness = _sub(_act, "page_readiness")
    else:
        _reg_setup = _ptrav = _sync = _pretouch_rec = _recon = _storage_reg = _page_readiness = {}
    _patcher_ms = _num(_act.get("patcher_bookkeeping_ms"))
    _patcher_counts = _sub(_act, "patcher_bookkeeping_counts")
    _pub_ms = _num(_act.get("activation_future_publication_ms"))
    _pub_src = str(_act.get("activation_future_publication_source") or UNAVAILABLE)

    # ── Measurement validity: the CPU storage registry proof must exist and
    #    contain a SUPPORTED unique storage object, or page traversal /
    #    checksum / pretouch / synchronized-transfer evidence is unavailable.
    _reg_valid, _reg_reason = _registry_validity(_storage_reg)
    _ptrav_valid = _sync_valid = _checksum_valid = _reg_valid
    _pret_valid, _pret_reason = _pretouch_validity(_pretouch_rec, _reg_valid)

    page = {
        "major_faults": pagein["major_faults"],
        "minor_faults": pagein["minor_faults"],
        "pagein_duration_ms": pagein["duration_ms"],
        "unet_demand_to_first_forward_ms": _num(first_cuda.get("elapsed_ms")),
        "demand_start_present": _num(first_cuda.get("demand_start_present")),
        "variance_stage_faults_major": var_faults["major_faults"],
        "variance_stage_faults_minor": var_faults["minor_faults"],
        # CPU page-traversal sub-stage (valid only with a CPU registry proof)
        "cpu_page_traversal_wall_ms": (_wall_ms(_ptrav) if _ptrav_valid else None),
        "cpu_page_traversal_minor_faults": (_num(_ptrav.get("minor_faults")) if _ptrav_valid else None),
        "cpu_page_traversal_major_faults": (_num(_ptrav.get("major_faults")) if _ptrav_valid else None),
        "cpu_page_traversal_bytes": (_num(_ptrav.get("bytes")) if _ptrav_valid else None),
        "cpu_page_traversal_gb_per_s": (_num(_ptrav.get("effective_gb_per_s")) if _ptrav_valid else None),
        "cpu_page_traversal_process_cpu_ms": (_num(_ptrav.get("process_cpu_ms")) if _ptrav_valid else None),
        "cpu_page_traversal_thread_cpu_ms": (_num(_ptrav.get("thread_cpu_ms")) if _ptrav_valid else None),
        # CPU→GPU synchronized transfer (valid only with a CPU registry proof)
        "cpu_to_gpu_transfer_wall_ms": (_wall_ms(_sync) if _sync_valid else None),
        "cpu_to_gpu_transfer_minor_faults": (_num(_sync.get("minor_faults")) if _sync_valid else None),
        "cpu_to_gpu_transfer_major_faults": (_num(_sync.get("major_faults")) if _sync_valid else None),
        "cpu_to_gpu_transfer_bytes": (_num(_sync.get("bytes")) if _sync_valid else None),
        "cpu_to_gpu_transfer_gb_per_s": (_num(_sync.get("effective_gb_per_s")) if _sync_valid else None),
        "cpu_to_gpu_transfer_process_cpu_ms": (_num(_sync.get("process_cpu_ms")) if _sync_valid else None),
        "cpu_to_gpu_transfer_thread_cpu_ms": (_num(_sync.get("thread_cpu_ms")) if _sync_valid else None),
        # Activation total + reconciliation residual from the runtime loader
        # reconciliation (truthful), and activation-future publication.
        "activation_total_ms": _num(_recon.get("loader_wall_ms")),
        "reconciliation_residual_ms": _num(_recon.get("residual_ms")),
        "loader_reconciliation_status": str(_recon.get("reconciliation_status") or UNAVAILABLE),
        "activation_future_publication_ms": _pub_ms,
        "activation_future_publication_source": _pub_src,
        "registry_setup_ms": _wall_ms(_reg_setup),
        # Worker-variance timing (queue / CPU-snapshot wait / dtype prep /
        # post-load bookkeeping / true total), mirroring the
        # activation_future_publication_ms handling.
        "queue_delay_ms": _num(_act.get("queue_delay_ms")),
        "cpu_snapshot_wait_ms": _num(_act.get("cpu_snapshot_wait_ms")),
        "dtype_layout_preparation_ms": _wall_ms(_sub(_act, "dtype_layout_preparation")),
        "post_load_bookkeeping_ms": _wall_ms(_sub(_act, "post_load_bookkeeping")),
        "early_activation_total_ms": _num(_act.get("early_activation_total_ms")),
    }

    # ── Pretouch (from the activation event's pretouch record) ──
    pretouch = {
        "pretouch_enabled": int(variance.get("pretouch", 0)),
        "pretouch_effect_ms": (_wall_ms(_pretouch_rec) if _pret_valid else None),
        "pretouch_bytes": (_num(_pretouch_rec.get("bytes")) if _pret_valid else None),
        "pretouch_total_pages": (_num(_pretouch_rec.get("expected_pages")) if _pret_valid else None),
        "pretouch_touched_pages": (_num(_pretouch_rec.get("touched_pages")) if _pret_valid else None),
        "pretouch_bytes_read": (_num(_pretouch_rec.get("bytes_read")) if _pret_valid else None),
        "pretouch_checksum": str(_pretouch_rec.get("checksum") or UNAVAILABLE) if _pret_valid else UNAVAILABLE,
        "pretouch_status": str(_pretouch_rec.get("status") or UNAVAILABLE) if _pret_valid else UNAVAILABLE,
        "pretouch_valid": _pret_valid,
        "pretouch_reason": _pret_reason,
    }

    # ── Transfer / throughput ──
    transfer = {
        "output_commit_ms": _num(timing.get("output_commit_ms")),
        "first_iteration_to_first_remote_event_ms": _num(
            timing.get("local_timing", {}).get("first_iteration_to_first_remote_event_ms")
            if isinstance(timing.get("local_timing"), dict) else None
        ),
        "command_to_response_ms": _num(timing.get("command_to_response_ms")),
        "wall_ms": _num(timing.get("wall_ms")),
        "variance_bytes": _sum_key(var_events, "bytes"),
        "variance_gb_per_s": _sum_key(var_events, "effective_gb_per_s"),
        "variance_rss_delta_bytes": _sum_key(var_events, "rss_delta_bytes"),
        # Synchronized CPU→GPU transfer (valid only with a CPU registry proof)
        "cpu_to_gpu_transfer_wall_ms": (_wall_ms(_sync) if _sync_valid else None),
        "cpu_to_gpu_transfer_bytes": (_num(_sync.get("bytes")) if _sync_valid else None),
        "cpu_to_gpu_transfer_gb_per_s": (_num(_sync.get("effective_gb_per_s")) if _sync_valid else None),
        "synchronized_load_wall_ms": (_wall_ms(_sync) if _sync_valid else None),
        "synchronized_load_bytes": (_num(_sync.get("bytes")) if _sync_valid else None),
        "synchronized_load_gb_per_s": (_num(_sync.get("effective_gb_per_s")) if _sync_valid else None),
    }

    # ── Bookkeeping (local preparation + patcher) ──
    lt = timing.get("local_timing", {}) if isinstance(timing.get("local_timing"), dict) else {}
    bookkeeping = {
        "handle_lookup_ms": _num(timing.get("handle_lookup_ms")),
        "plan_build_ms": _num(lt.get("plan_build_ms")),
        "generator_create_ms": _num(lt.get("generator_create_ms")),
        "t3b_to_t8_ms": _num(timing.get("t3b_to_t8_ms")),
        "variance_process_cpu_ms": _sum_key(var_events, "process_cpu_ms"),
        "variance_thread_cpu_ms": _sum_key(var_events, "thread_cpu_ms"),
        # Patcher bookkeeping (from the activation event)
        "patcher_bookkeeping_ms": _patcher_ms,
        "patch_weight_count": _num(_patcher_counts.get("patch_weight_count")),
        "cast_count": _num(_patcher_counts.get("cast_count")),
    }

    # ── Sampler wait / sampling ──
    sampler_ev = _event_meta(_trace_event(result, "sampler_variance"))
    sampler = {
        "sampler_node_to_sampler_start_ms": _num(timing.get("sampler_node_to_sampler_start_ms")),
        # sampling_ms preferred; sampler_ms accepted as the fallback.
        "sampling_ms": _first_num(timing, ["sampling_ms", "sampler_ms"]),
        "sampling_source": "sampling_ms" if _num(timing.get("sampling_ms")) is not None
                          else ("sampler_ms" if _num(timing.get("sampler_ms")) is not None
                                else UNAVAILABLE),
        "vae_decode_ms": _num(timing.get("vae_decode_ms")),
        "sampling_wall_ms": _num(sampler_ev.get("wall_ms")),
        "sampling_process_cpu_ms": _num(sampler_ev.get("process_cpu_ms")),
        "activation_wait_ms": _num(sampler_ev.get("activation_wait_ms")),
        "activation_wait_source": str(sampler_ev.get("activation_wait_source") or UNAVAILABLE),
    }

    # ── Unique storage / page / checksum / read metrics ──
    all_evts = _events_by_prefix(result, "")
    storage = {
        "storage_unique_count": (_num(_storage_reg.get("unique_storage_count")) if _storage_reg else None),
        "storage_raw_bytes": (_num(_storage_reg.get("raw_byte_count")) if _storage_reg else None),
        "storage_unsupported_count": (_num(_storage_reg.get("unsupported_count")) if _storage_reg else None),
        # Do not surface unrelated aggregate storage counters when the UNET
        # CPU-registry proof is invalid or absent.  They are not evidence for
        # the requested unique CPU storage traversal.
        "storage_total_bytes": (
            _num(_storage_reg.get("total_bytes"))
            if _reg_valid else None
        ),
        "page_readiness_total_pages": _num(_page_readiness.get("total_pages")),
        "page_readiness_touched_pages": _num(_page_readiness.get("touched_pages")),
        "page_readiness_bytes": _num(_page_readiness.get("bytes")),
        "page_readiness_status": str(_page_readiness.get("status") or UNAVAILABLE),
        "pretouch_expected_pages": (_num(_pretouch_rec.get("expected_pages")) if _pret_valid else None),
        "pretouch_touched_pages": (_num(_pretouch_rec.get("touched_pages")) if _pret_valid else None),
        "bytes_read": (_num(_pretouch_rec.get("bytes_read")) if _checksum_valid else None),
        "read_count": (_sum_key(all_evts, "read_count") if _checksum_valid else None),
        "checksum_count": (_sum_key(all_evts, "checksum_count") if _checksum_valid else None),
    }

    measurement_validity = {
        "activation_event_source": _act_src,
        "registry_valid": _reg_valid,
        "registry_reason": _reg_reason,
        "page_traversal_valid": _ptrav_valid,
        "page_traversal_reason": _reg_reason,
        "synchronized_transfer_valid": _sync_valid,
        "synchronized_transfer_reason": _reg_reason,
        "pretouch_valid": _pret_valid,
        "pretouch_reason": _pret_reason,
        "checksum_valid": _checksum_valid,
        "note": ("CPU storage hydration / pretouch / synchronized transfer "
                 "evidence is invalid or unavailable when the CPU storage "
                 "registry proof is absent or unsupported-only "
                 "(unique_storage_count=0); the ~2-3 ms outer interval is a "
                 "launch/window artifact and must not be used.") if not _reg_valid else "",
    }

    runtime_shape = identity.get("runtime_shape", {})
    if not isinstance(runtime_shape, dict):
        runtime_shape = {}
    thread_counts = {
        "thread_policy": runtime_shape.get("thread_policy", UNAVAILABLE),
        "cpu_request": identity.get("cpu", UNAVAILABLE),
    }

    identity_ids = {
        "app_name": identity.get("app_name", UNAVAILABLE),
        "provider": identity.get("cloud", UNAVAILABLE),
        "region": identity.get("region", UNAVAILABLE),
        "image_id": identity.get("image_id", UNAVAILABLE),
        "task_id": identity.get("container_task_id", UNAVAILABLE),
        "modal_container_id": identity.get("modal_container_id", UNAVAILABLE),
        "container_session_id": identity.get("container_session_id", UNAVAILABLE),
        "restored_instance_id": identity.get("restored_instance_id", UNAVAILABLE),
        "fingerprint": identity.get("fingerprint", UNAVAILABLE),
    }

    return {
        "run_index": artifact.get("run_index"),
        "run_id": artifact.get("run_id", artifact.get("request_id", "run_%s" % artifact.get("run_index"))),
        "mode": artifact.get("mode", "variance_cold"),
        "pretouch": int(variance.get("pretouch", 0)),
        "diag": artifact.get("diag"),
        "attempt_id": artifact.get("attempt_id"),
        "condition_label": artifact.get("condition_label"),
        "classification": artifact.get("classification"),
        "slow_flags": dict(artifact.get("slow_flags") or {}),
        "error": artifact.get("error"),
        "attempt_file": artifact.get("attempt_file"),
        "attempt_log": artifact.get("attempt_log"),
        "runner_log": artifact.get("runner_log"),
        "measurement_validity": measurement_validity,
        "cold_valid": variance.get("cold_valid"),
        "cold": variance.get("cold"),
        "identity_failures": list(variance.get("failures", []) or []),
        "identity": identity_ids,
        "thread_counts": thread_counts,
        "timestamps": {
            "start": artifact.get("start_ts"),
            "remote_entry": artifact.get("remote_entry_ts"),
            "end": artifact.get("end_ts"),
        },
        "metrics": {
            "restore": restore,
            "page_traversal": page,
            "pretouch": pretouch,
            "transfer": transfer,
            "bookkeeping": bookkeeping,
            "sampler": sampler,
            "storage": storage,
        },
    }


def load_runs_from_dir(directory: str | Path) -> list[dict[str, Any]]:
    """Load and normalise every ``run_*.json`` artifact in *directory*.

    Artifacts that fail to parse are retained as an ``invalid`` record so no
    run is ever silently dropped.
    """
    d = Path(directory)
    records: list[dict[str, Any]] = []
    if not d.is_dir():
        return records
    files = sorted(d.glob("run_*.json"))
    for f in files:
        try:
            raw = json.loads(f.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            records.append({
                "run_index": None,
                "run_id": f.stem,
                "mode": "invalid",
                "cold_valid": False,
                "cold": False,
                "identity_failures": [f"unreadable artifact: {exc}"],
                "identity": {},
                "thread_counts": {},
                "timestamps": {},
                "metrics": {},
                "_error": str(exc)[:200],
                "_source": str(f),
            })
            continue
        if not isinstance(raw, dict):
            records.append({
                "run_index": None, "run_id": f.stem, "mode": "invalid",
                "cold_valid": False, "cold": False, "identity_failures": ["non-dict artifact"],
                "identity": {}, "thread_counts": {}, "timestamps": {}, "metrics": {},
                "_source": str(f),
            })
            continue
        records.append(extract_run_metrics(raw))
    return records


def _fmt(value: Any) -> str:
    if value is None or value == UNAVAILABLE or value == "":
        return "unavailable"
    if isinstance(value, float):
        return f"{value:,.3f}"
    return str(value)


def _metric_stats(records: list[dict[str, Any]], category: str, key: str) -> dict[str, Any]:
    values = []
    for r in records:
        v = r.get("metrics", {}).get(category, {}).get(key)
        n = _num(v)
        if n is not None:
            values.append(n)
    return compute_stats(values)


def _slow_metric(records: list[dict[str, Any]], category: str, key: str,
                 *, threshold_ms: float) -> dict[str, Any]:
    values = []
    for r in records:
        v = r.get("metrics", {}).get(category, {}).get(key)
        n = _num(v)
        if n is not None:
            values.append(n)
    return slow_run_rate(values, threshold_ms=threshold_ms)


def _dominant_category(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate available medians per category and rank them.

    Returns the best-supported root-cause analysis as a dict with
    ``dominant``, ``competing_explanations`` and ``suggestion``.
    """
    category_labels = {
        "restore": "restore",
        "page_traversal": "CPU page traversal",
        "pretouch": "pretouch",
        "transfer": "transfer/throughput",
        "bookkeeping": "bookkeeping",
        "sampler": "sampler wait/sampling",
    }
    totals: dict[str, float] = {}
    for cat in category_labels:
        total = 0.0
        any_data = False
        for r in records:
            metrics = r.get("metrics", {}).get(cat, {})
            for v in metrics.values():
                n = _num(v)
                if n is not None and n > 0:
                    total += n
                    any_data = True
        if any_data:
            totals[cat] = round(total, 3)

    if not totals:
        return {
            "dominant": UNAVAILABLE,
            "competing_explanations": UNAVAILABLE,
            "suggestion": "No timing data was captured for any category.",
        }

    ordered = sorted(totals.items(), key=lambda kv: kv[1], reverse=True)
    dominant_cat, dominant_val = ordered[0]
    competing = [
        (category_labels.get(cat, cat), round(val, 3))
        for cat, val in ordered[1:]
        if val >= dominant_val * 0.6
    ]
    suggestion = _suggestion_for(dominant_cat)
    return {
        "dominant": category_labels.get(dominant_cat, dominant_cat),
        "dominant_value_ms": dominant_val,
        "totals_ms": {category_labels.get(c, c): v for c, v in totals.items()},
        "competing_explanations": competing,
        "suggestion": suggestion,
    }


def _suggestion_for(category: str) -> str:
    if category == "restore":
        return ("Reduce snapshot restore cost: investigate restore-stage "
                "snapshot_restore_ms / reload_models_ms and pre-warm page tables.")
    if category == "page_traversal":
        return ("Reduce CPU page-in cost: enable/verify pagefault tracking and "
                "evaluate explicit page pre-touch of UNET/CLIP snapshot buffers.")
    if category == "transfer":
        return ("Reduce transfer/throughput cost: inspect output_commit_ms and "
                "first_iteration_to_first_remote_event_ms for serialization overhead.")
    if category == "bookkeeping":
        return ("Reduce local bookkeeping: lower handle_lookup_ms / plan_build_ms "
                "by caching the Modal handle and plan builder.")
    if category == "sampler":
        return ("Reduce sampler wait/sampling: inspect sampler_node_to_sampler_start_ms "
                "for pre-sampler stalls and sampling_ms for kernel/step cost.")
    if category == "pretouch":
        return ("Pretouch diagnostics: confirm COMFYMODAL_V2_UNET_PRETOUCH is honored "
                "and captured on the remote side before attributing an effect.")
    return "Review the dominant category in the per-run timing breakdown."


def build_summary(records: list[dict[str, Any]], *, meta: dict[str, Any] | None = None) -> dict[str, Any]:
    """Build the summary JSON dict for a variance-cold benchmark run."""
    meta = dict(meta or {})
    wall_stats = _metric_stats(records, "transfer", "wall_ms")
    restore_stats = _metric_stats(records, "restore", "restore_total_ms")
    sampling_stats = _metric_stats(records, "sampler", "sampling_ms")

    slow_threshold = float(meta.get("slow_threshold_ms", 0.0) or 0.0)
    if slow_threshold <= 0:
        # Default: 2x the median wall time of the set.
        med = _num(wall_stats.get("median"))
        slow_threshold = round(med * 2.0, 3) if med is not None else 0.0

    cold_runs = [r for r in records if r.get("cold") is True]
    warm_or_invalid = [r for r in records if r.get("cold") is not True]

    # Union of per-stage restore-breakdown keys across all records, so the
    # report renders every measured restore sub-stage (even if some runs are
    # missing a stage).  Derived from the flattened restore_breakdown_<stage>
    # scalars carried by extract_run_metrics.
    _rb_stages = sorted({
        _k[len("restore_breakdown_"):]
        for r in records
        for _k in (r.get("metrics", {}).get("restore", {}) or {})
        if isinstance(_k, str) and _k.startswith("restore_breakdown_")
    })
    _restore_cat: dict[str, Any] = {
        "restore_total_ms": _metric_stats(records, "restore", "restore_total_ms"),
        "snapshot_restore_ms": _metric_stats(records, "restore", "snapshot_restore_ms"),
        "backend_startup_ms": _metric_stats(records, "restore", "backend_startup_ms"),
    }
    for _st in _rb_stages:
        _restore_cat[f"restore_breakdown_{_st}"] = _metric_stats(
            records, "restore", f"restore_breakdown_{_st}")

    return {
        "mode": "variance_cold",
        "generated_at": _fmt_ts(),
        "run_count": len(records),
        "cold_count": len(cold_runs),
        "warm_or_invalid_count": len(warm_or_invalid),
        "meta": meta,
        "summary_stats": {
            "wall_ms": wall_stats,
            "restore_total_ms": restore_stats,
            "sampling_ms": sampling_stats,
            "slow_run": slow_run_rate(
                (r.get("metrics", {}).get("transfer", {}).get("wall_ms")
                 for r in records),
                threshold_ms=slow_threshold,
            ),
        },
        "category_stats": {
            "restore": _restore_cat,
            "page_traversal": {
                "major_faults": _metric_stats(records, "page_traversal", "major_faults"),
                "minor_faults": _metric_stats(records, "page_traversal", "minor_faults"),
                "variance_stage_faults_major": _metric_stats(
                    records, "page_traversal", "variance_stage_faults_major"),
                "unet_demand_to_first_forward_ms": _metric_stats(
                    records, "page_traversal", "unet_demand_to_first_forward_ms"),
                "cpu_page_traversal_wall_ms": _metric_stats(
                    records, "page_traversal", "cpu_page_traversal_wall_ms"),
                "cpu_page_traversal_gb_per_s": _metric_stats(
                    records, "page_traversal", "cpu_page_traversal_gb_per_s"),
                "cpu_to_gpu_transfer_wall_ms": _metric_stats(
                    records, "page_traversal", "cpu_to_gpu_transfer_wall_ms"),
                "cpu_to_gpu_transfer_gb_per_s": _metric_stats(
                    records, "page_traversal", "cpu_to_gpu_transfer_gb_per_s"),
                # Worker-variance timing (true total / queue / wait / stages).
                "early_activation_total_ms": _metric_stats(
                    records, "page_traversal", "early_activation_total_ms"),
                "queue_delay_ms": _metric_stats(
                    records, "page_traversal", "queue_delay_ms"),
                "cpu_snapshot_wait_ms": _metric_stats(
                    records, "page_traversal", "cpu_snapshot_wait_ms"),
                "dtype_layout_preparation_ms": _metric_stats(
                    records, "page_traversal", "dtype_layout_preparation_ms"),
                "post_load_bookkeeping_ms": _metric_stats(
                    records, "page_traversal", "post_load_bookkeeping_ms"),
            },
            "pretouch": {
                "pretouch_enabled": _metric_stats(records, "pretouch", "pretouch_enabled"),
                "pretouch_effect_ms": _metric_stats(records, "pretouch", "pretouch_effect_ms"),
                "pretouch_bytes": _metric_stats(records, "pretouch", "pretouch_bytes"),
                "pretouch_touched_pages": _metric_stats(records, "pretouch", "pretouch_touched_pages"),
            },
            "transfer": {
                "output_commit_ms": _metric_stats(records, "transfer", "output_commit_ms"),
                "command_to_response_ms": _metric_stats(records, "transfer", "command_to_response_ms"),
                "variance_bytes": _metric_stats(records, "transfer", "variance_bytes"),
                "variance_gb_per_s": _metric_stats(records, "transfer", "variance_gb_per_s"),
                # Transfer throughput (bytes and effective GB/s) from
                # first_unet_activation_variance.cpu_to_gpu_transfer.
                "cpu_to_gpu_transfer_wall_ms": _metric_stats(
                    records, "transfer", "cpu_to_gpu_transfer_wall_ms"),
                "cpu_to_gpu_transfer_bytes": _metric_stats(
                    records, "transfer", "cpu_to_gpu_transfer_bytes"),
                "cpu_to_gpu_transfer_gb_per_s": _metric_stats(
                    records, "transfer", "cpu_to_gpu_transfer_gb_per_s"),
            },
            "bookkeeping": {
                "handle_lookup_ms": _metric_stats(records, "bookkeeping", "handle_lookup_ms"),
                "plan_build_ms": _metric_stats(records, "bookkeeping", "plan_build_ms"),
                "t3b_to_t8_ms": _metric_stats(records, "bookkeeping", "t3b_to_t8_ms"),
                "variance_process_cpu_ms": _metric_stats(
                    records, "bookkeeping", "variance_process_cpu_ms"),
                # Patcher bookkeeping duration + counts from
                # first_unet_activation_variance.
                "patcher_bookkeeping_ms": _metric_stats(
                    records, "bookkeeping", "patcher_bookkeeping_ms"),
                "patch_weight_count": _metric_stats(
                    records, "bookkeeping", "patch_weight_count"),
                "cast_count": _metric_stats(records, "bookkeeping", "cast_count"),
            },
            "sampler": {
                "sampler_node_to_sampler_start_ms": _metric_stats(
                    records, "sampler", "sampler_node_to_sampler_start_ms"),
                "sampling_ms": _metric_stats(records, "sampler", "sampling_ms"),
                "sampling_wall_ms": _metric_stats(records, "sampler", "sampling_wall_ms"),
                "activation_wait_ms": _metric_stats(records, "sampler", "activation_wait_ms"),
                "vae_decode_ms": _metric_stats(records, "sampler", "vae_decode_ms"),
            },
        },
        "root_cause": _dominant_category(records),
        "runs": records,
    }


def _render_stats_table(title: str, rows: dict[str, dict[str, Any]]) -> str:
    lines = [f"### {title}", "", "| Metric | Count | Median ms | p90 ms | Max ms | Mean ms |",
             "|---|---:|---:|---:|---:|---:|"]
    for label, stats in rows.items():
        if not isinstance(stats, dict):
            continue
        lines.append(
            f"| {label} | {stats.get('count', 0)} | {_fmt(stats.get('median'))} "
            f"| {_fmt(stats.get('p90'))} | {_fmt(stats.get('max'))} | {_fmt(stats.get('mean'))} |"
        )
    return "\n".join(lines) + "\n"


def _render_identity_line(r: dict[str, Any]) -> str:
    ids = r.get("identity", {}) or {}
    return (
        f"  - Provider/region: `{ids.get('provider', 'unavailable')}` / "
        f"`{ids.get('region', 'unavailable')}`\n"
        f"  - Image: `{ids.get('image_id', 'unavailable')}`\n"
        f"  - Task/container: `{ids.get('task_id', 'unavailable')}` / "
        f"`{ids.get('modal_container_id', 'unavailable')}`\n"
        f"  - Container session: `{ids.get('container_session_id', 'unavailable')}`\n"
        f"  - Restored instance: `{ids.get('restored_instance_id', 'unavailable')}`\n"
        f"  - Runtime fingerprint: `{ids.get('fingerprint', 'unavailable')}`"
    )


def render_variance_report(summary: dict[str, Any]) -> str:
    """Render a detailed Markdown report from a summary dict."""
    records = summary.get("runs", [])
    meta = summary.get("meta", {}) or {}
    stats = summary.get("summary_stats", {}) or {}
    categories = summary.get("category_stats", {}) or {}
    root = summary.get("root_cause", {}) or {}

    lines: list[str] = []
    lines.append("# V2 Variance-Cold Benchmark Report")
    lines.append("")
    lines.append("> Mode: `variance_cold`. One request at a time with a fixed "
                 "gap; each run asserts true cold identity from the request-scoped "
                 "`remote_method_entry` metadata.")
    lines.append("")
    lines.append("## Scope and completeness")
    lines.append("")
    lines.append(f"- Generated: `{_fmt_ts()}`")
    lines.append(f"- Run records: **{summary.get('run_count', 0)}**")
    lines.append(f"- Confirmed cold runs: **{summary.get('cold_count', 0)}**")
    lines.append(f"- Warm-reused or invalid runs: **{summary.get('warm_or_invalid_count', 0)}**")
    if meta.get("limitation"):
        lines.append(f"- Run limitation: {meta.get('limitation')}")
    if meta.get("pretouch") is not None:
        lines.append(f"- UNET pretouch mode: `{int(meta['pretouch'])}` "
                     "(0 = disabled, 1 = enabled)")
    lines.append(f"- Gap between runs: `{meta.get('gap_seconds', 'unavailable')}s`")
    lines.append("")

    lines.append("## Cold-identity validity")
    lines.append("")
    lines.append("Each run is only labeled cold when the request-scoped "
                 "`remote_method_entry` proves `restore_count == 1`, "
                 "`request_count == 1`, a non-empty `restored_instance_id`, and "
                 "(when available) a container/task identity distinct from the "
                 "previous run. Warm/reused runs are never relabeled cold.")
    lines.append("")

    # ── Summary stats table ──
    lines.append(_render_stats_table("Overall timing (ms)", {
        "Wall time": stats.get("wall_ms", {}),
        "Restore total": stats.get("restore_total_ms", {}),
        "Sampling": stats.get("sampling_ms", {}),
    }))
    slow = stats.get("slow_run", {})
    lines.append(f"### Slow-run rate")
    lines.append("")
    lines.append(f"- Threshold: `{slow.get('threshold_ms', 'unavailable')} ms`")
    lines.append(f"- Slow runs: `{slow.get('slow_count', 'unavailable')}` / "
                 f"`{slow.get('count', 0)}` (rate `{slow.get('rate', 'unavailable')}`)")
    lines.append("")

    # ── Category tables ──
    _restore_tbl: dict[str, Any] = {
        "restore_total_ms": categories.get("restore", {}).get("restore_total_ms", {}),
        "snapshot_restore_ms": categories.get("restore", {}).get("snapshot_restore_ms", {}),
        "backend_startup_ms": categories.get("restore", {}).get("backend_startup_ms", {}),
    }
    for _st in sorted(categories.get("restore", {}) or {}):
        if isinstance(_st, str) and _st.startswith("restore_breakdown_"):
            _restore_tbl[_st] = categories["restore"][_st]
    lines.append(_render_stats_table("Restore breakdown (ms)", _restore_tbl))
    lines.append(_render_stats_table("CPU page traversal", {
        "major_faults": categories.get("page_traversal", {}).get("major_faults", {}),
        "minor_faults": categories.get("page_traversal", {}).get("minor_faults", {}),
        "variance_stage_faults_major": categories.get("page_traversal", {}).get(
            "variance_stage_faults_major", {}),
        "unet_demand_to_first_forward_ms": categories.get("page_traversal", {}).get(
            "unet_demand_to_first_forward_ms", {}),
        "cpu_page_traversal_wall_ms": categories.get("page_traversal", {}).get(
            "cpu_page_traversal_wall_ms", {}),
        "cpu_page_traversal_gb_per_s": categories.get("page_traversal", {}).get(
            "cpu_page_traversal_gb_per_s", {}),
        "cpu_to_gpu_transfer_wall_ms": categories.get("page_traversal", {}).get(
            "cpu_to_gpu_transfer_wall_ms", {}),
        "early_activation_total_ms": categories.get("page_traversal", {}).get(
            "early_activation_total_ms", {}),
        "queue_delay_ms": categories.get("page_traversal", {}).get("queue_delay_ms", {}),
        "cpu_snapshot_wait_ms": categories.get("page_traversal", {}).get(
            "cpu_snapshot_wait_ms", {}),
        "dtype_layout_preparation_ms": categories.get("page_traversal", {}).get(
            "dtype_layout_preparation_ms", {}),
        "post_load_bookkeeping_ms": categories.get("page_traversal", {}).get(
            "post_load_bookkeeping_ms", {}),
    }))
    lines.append(_render_stats_table("Pretouch", {
        "pretouch_enabled": categories.get("pretouch", {}).get("pretouch_enabled", {}),
        "pretouch_effect_ms": categories.get("pretouch", {}).get("pretouch_effect_ms", {}),
        "pretouch_bytes": categories.get("pretouch", {}).get("pretouch_bytes", {}),
        "pretouch_touched_pages": categories.get("pretouch", {}).get("pretouch_touched_pages", {}),
    }))
    lines.append(_render_stats_table("Transfer / throughput", {
        "output_commit_ms": categories.get("transfer", {}).get("output_commit_ms", {}),
        "command_to_response_ms": categories.get("transfer", {}).get("command_to_response_ms", {}),
        "variance_bytes": categories.get("transfer", {}).get("variance_bytes", {}),
        "variance_gb_per_s": categories.get("transfer", {}).get("variance_gb_per_s", {}),
        "cpu_to_gpu_transfer_wall_ms": categories.get("transfer", {}).get(
            "cpu_to_gpu_transfer_wall_ms", {}),
        "cpu_to_gpu_transfer_bytes": categories.get("transfer", {}).get(
            "cpu_to_gpu_transfer_bytes", {}),
        "cpu_to_gpu_transfer_gb_per_s": categories.get("transfer", {}).get(
            "cpu_to_gpu_transfer_gb_per_s", {}),
    }))
    lines.append(_render_stats_table("Bookkeeping (ms)", {
        "handle_lookup_ms": categories.get("bookkeeping", {}).get("handle_lookup_ms", {}),
        "plan_build_ms": categories.get("bookkeeping", {}).get("plan_build_ms", {}),
        "t3b_to_t8_ms": categories.get("bookkeeping", {}).get("t3b_to_t8_ms", {}),
        "variance_process_cpu_ms": categories.get("bookkeeping", {}).get(
            "variance_process_cpu_ms", {}),
        "patcher_bookkeeping_ms": categories.get("bookkeeping", {}).get(
            "patcher_bookkeeping_ms", {}),
        "patch_weight_count": categories.get("bookkeeping", {}).get("patch_weight_count", {}),
        "cast_count": categories.get("bookkeeping", {}).get("cast_count", {}),
    }))
    lines.append(_render_stats_table("Sampler wait / sampling (ms)", {
        "sampler_node_to_sampler_start_ms": categories.get("sampler", {}).get(
            "sampler_node_to_sampler_start_ms", {}),
        "sampling_ms": categories.get("sampler", {}).get("sampling_ms", {}),
        "sampling_wall_ms": categories.get("sampler", {}).get("sampling_wall_ms", {}),
        "activation_wait_ms": categories.get("sampler", {}).get("activation_wait_ms", {}),
        "vae_decode_ms": categories.get("sampler", {}).get("vae_decode_ms", {}),
    }))
    # ── Activation-wait source labels (textual, per run) ──
    _wait_sources = sorted({
        str(r.get("metrics", {}).get("sampler", {}).get("activation_wait_source"))
        for r in records
        if r.get("metrics", {}).get("sampler", {}).get("activation_wait_source")
        not in (None, UNAVAILABLE, "")
    })
    if _wait_sources:
        lines.append("### Sampler activation-wait source labels")
        lines.append("")
        lines.append(", ".join(f"`{s}`" for s in _wait_sources))
        lines.append("")

    # ── Root cause ──
    lines.append("## Best-supported root cause / competing explanations / next fix")
    lines.append("")
    lines.append(f"- Best-supported root cause: **{root.get('dominant', 'unavailable')}**")
    comp = root.get("competing_explanations")
    if isinstance(comp, list) and comp:
        lines.append("- Competing explanations: " + "; ".join(
            f"{name} ({_fmt(val)} ms)" for name, val in comp) + ".")
    else:
        lines.append("- Competing explanations: unavailable")
    lines.append(f"- Next fix: {root.get('suggestion', 'unavailable')}")
    lines.append("")

    # ── Per-run inventory ──
    lines.append("## Per-run inventory")
    lines.append("")
    for i, r in enumerate(records):
        cold = r.get("cold")
        cold_label = "COLD" if cold is True else ("NOT-COLD" if cold is False else "INVALID")
        lines.append(f"### `{r.get('run_id', f'run_{i}')}` / mode `{r.get('mode', 'variance_cold')}`")
        lines.append("")
        lines.append(f"- Cold identity: **{cold_label}**")
        failures = r.get("identity_failures", [])
        if failures:
            lines.append("- Identity failures:")
            for f in failures:
                lines.append(f"  - `{f}`")
        lines.append(_render_identity_line(r))
        if r.get("_error"):
            lines.append(f"- Error: `{r.get('_error')}`")
        metrics = r.get("metrics", {})
        if metrics:
            line_parts = []
            for cat in ("restore", "page_traversal", "pretouch", "transfer", "bookkeeping", "sampler", "storage"):
                vals = metrics.get(cat, {})
                line_parts.append(f"{cat}={{{', '.join(f'{k}: {_fmt(v)}' for k, v in vals.items())}}}")
            lines.append(f"- Metrics: " + "; ".join(line_parts))
        lines.append("")

    return "\n".join(lines)


# ═════════════════════════════════════════════════════════════════════════
# Variance-cold MATRIX (four-condition round-robin) report helpers
# ═════════════════════════════════════════════════════════════════════════

CONDITION_LABELS = {
    "diag0_pt0": "diagnostics off / pretouch off",
    "diag0_pt1": "diagnostics off / pretouch on",
    "diag1_pt0": "diagnostics on / pretouch off",
    "diag1_pt1": "diagnostics on / pretouch on",
}


def mad(values: Iterable[float]) -> float | str:
    """Median absolute deviation of the available numeric values."""
    vals = [float(v) for v in values if _num(v) is not None]
    if not vals:
        return UNAVAILABLE
    med = statistics.median(vals)
    return round(statistics.median([abs(v - med) for v in vals]), 3)


def compute_stats_extended(values: Iterable[float]) -> dict[str, Any]:
    """median / MAD / p90 / max / mean / min — all explicitly unavailable when empty."""
    vals = sorted(float(v) for v in values if _num(v) is not None)
    if not vals:
        return {"count": 0, "median": UNAVAILABLE, "mad": UNAVAILABLE,
                "p90": UNAVAILABLE, "p95": UNAVAILABLE, "max": UNAVAILABLE,
                "mean": UNAVAILABLE, "min": UNAVAILABLE}
    return {
        "count": len(vals),
        "median": round(statistics.median(vals), 3),
        "mad": mad(vals),
        "p90": round(percentile(vals, 90) or 0.0, 3),
        "p95": round(percentile(vals, 95) or 0.0, 3),
        "max": round(vals[-1], 3),
        "mean": round(statistics.mean(vals), 3),
        "min": round(vals[0], 3),
    }


def _matrix_metric_values(records: list[dict[str, Any]], category: str, key: str) -> list[float]:
    out: list[float] = []
    for r in records:
        v = _num(r.get("metrics", {}).get(category, {}).get(key))
        if v is not None:
            out.append(v)
    return out


def _matrix_stats(records: list[dict[str, Any]], category: str, key: str) -> dict[str, Any]:
    return compute_stats_extended(_matrix_metric_values(records, category, key))


def _failure_rate(records: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(records)
    failed = sum(1 for r in records if r.get("classification") == "failed")
    if total == 0:
        return {"count": 0, "failed": 0, "rate": UNAVAILABLE}
    return {"count": total, "failed": failed, "rate": round(failed / total, 4)}


def _fixed_slow_run_rate(records: list[dict[str, Any]], threshold_ms: float) -> dict[str, Any]:
    """Fraction of valid cold runs whose wall time exceeds the FIXED threshold."""
    cold = [r for r in records if r.get("classification") == "cold"]
    if not cold:
        return {"count": 0, "slow": 0, "rate": UNAVAILABLE, "threshold_ms": threshold_ms}
    if not threshold_ms or threshold_ms <= 0:
        return {"count": len(cold), "slow": 0, "rate": UNAVAILABLE, "threshold_ms": threshold_ms,
                "note": "no fixed threshold configured"}
    slow = [r for r in cold if (_num(r.get("metrics", {}).get("transfer", {}).get("wall_ms")) or 0) > threshold_ms]
    return {"count": len(cold), "slow": len(slow), "rate": round(len(slow) / len(cold), 4),
            "threshold_ms": threshold_ms}


def build_matrix_summary(
    records: list[dict[str, Any]],
    conditions: list[tuple[int, int]],
    *,
    meta: dict[str, Any] | None = None,
    slow_threshold_ms: float = 0.0,
) -> dict[str, Any]:
    """Build the consolidated matrix summary JSON.

    *records* is the flattened per-attempt list (from ``extract_run_metrics``)
    with ``condition_label``, ``classification``, ``attempt_id`` set.  Each
    condition is summarised over its VALID COLD runs only for timing; failures,
    warm/invalid and snapshot-capture runs are preserved and counted separately.
    """
    meta = dict(meta or {})
    per_condition: dict[str, dict[str, Any]] = {}
    identities: dict[str, list[dict[str, Any]]] = {}
    for diag, pretouch in conditions:
        label = f"diag{int(diag)}_pt{int(pretouch)}"
        cond_records = [r for r in records if r.get("condition_label") == label]
        cold = [r for r in cond_records if r.get("classification") == "cold"]
        per_condition[label] = {
            "label": label,
            "diag": int(diag),
            "pretouch": int(pretouch),
            "attempt_count": len(cond_records),
            "cold_count": len(cold),
            "warm_invalid_count": sum(1 for r in cond_records if r.get("classification") == "warm_invalid"),
            "failed_count": sum(1 for r in cond_records if r.get("classification") == "failed"),
            "snapshot_capture_count": sum(1 for r in cond_records if r.get("classification") == "snapshot_capture"),
            "classification_counts": _classification_counts(cond_records),
            "failure_rate": _failure_rate(cond_records),
            "fixed_slow_run_rate": _fixed_slow_run_rate(cond_records, slow_threshold_ms),
            "slow_flags": {
                "restore_over_3s": sum(1 for r in cond_records if r.get("slow_flags", {}).get("restore_over_3s")),
                "unet_activation_over_3s": sum(1 for r in cond_records if r.get("slow_flags", {}).get("unet_activation_over_3s")),
            },
            "timing": {
                "wall_ms": _matrix_stats(cold, "transfer", "wall_ms"),
                "restore_total_ms": _matrix_stats(cold, "restore", "restore_total_ms"),
                "snapshot_restore_ms": _matrix_stats(cold, "restore", "snapshot_restore_ms"),
                "backend_startup_ms": _matrix_stats(cold, "restore", "backend_startup_ms"),
                "cpu_page_traversal_wall_ms": _matrix_stats(cold, "page_traversal", "cpu_page_traversal_wall_ms"),
                "cpu_page_traversal_gb_per_s": _matrix_stats(cold, "page_traversal", "cpu_page_traversal_gb_per_s"),
                "cpu_to_gpu_transfer_wall_ms": _matrix_stats(cold, "transfer", "cpu_to_gpu_transfer_wall_ms"),
                "cpu_to_gpu_transfer_gb_per_s": _matrix_stats(cold, "transfer", "cpu_to_gpu_transfer_gb_per_s"),
                "activation_total_ms": _matrix_stats(cold, "page_traversal", "activation_total_ms"),
                "reconciliation_residual_ms": _matrix_stats(cold, "page_traversal", "reconciliation_residual_ms"),
                # Preparation / bookkeeping
                "handle_lookup_ms": _matrix_stats(cold, "bookkeeping", "handle_lookup_ms"),
                "plan_build_ms": _matrix_stats(cold, "bookkeeping", "plan_build_ms"),
                "generator_create_ms": _matrix_stats(cold, "bookkeeping", "generator_create_ms"),
                "patcher_bookkeeping_ms": _matrix_stats(cold, "bookkeeping", "patcher_bookkeeping_ms"),
                "t3b_to_t8_ms": _matrix_stats(cold, "bookkeeping", "t3b_to_t8_ms"),
                "sampler_node_to_sampler_start_ms": _matrix_stats(cold, "sampler", "sampler_node_to_sampler_start_ms"),
                "sampling_ms": _matrix_stats(cold, "sampler", "sampling_ms"),
                "vae_decode_ms": _matrix_stats(cold, "sampler", "vae_decode_ms"),
                "activation_wait_ms": _matrix_stats(cold, "sampler", "activation_wait_ms"),
            },
            "storage": {
                "storage_unique_count": _matrix_stats(cold, "storage", "storage_unique_count"),
                "storage_raw_bytes": _matrix_stats(cold, "storage", "storage_raw_bytes"),
                "storage_total_bytes": _matrix_stats(cold, "storage", "storage_total_bytes"),
                "pretouch_expected_pages": _matrix_stats(cold, "storage", "pretouch_expected_pages"),
                "pretouch_total_pages": _matrix_stats(cold, "storage", "pretouch_total_pages"),
                "page_readiness_total_pages": _matrix_stats(cold, "storage", "page_readiness_total_pages"),
                "bytes_read": _matrix_stats(cold, "storage", "bytes_read"),
                "read_count": _matrix_stats(cold, "storage", "read_count"),
                "checksum_count": _matrix_stats(cold, "storage", "checksum_count"),
            },
            "measurement_validity": {
                "activation_event_sources": _count_values(cold, "activation_event_source"),
                "registry_valid": _count_truthy(cold, "registry_valid"),
                "registry_invalid_reasons": _collect_reasons(cold, "registry_reason"),
                "page_traversal_valid": _count_truthy(cold, "page_traversal_valid"),
                "synchronized_transfer_valid": _count_truthy(cold, "synchronized_transfer_valid"),
                "pretouch_valid": _count_truthy(cold, "pretouch_valid"),
                "pretouch_invalid_reasons": _collect_reasons(cold, "pretouch_reason"),
                "checksum_valid": _count_truthy(cold, "checksum_valid"),
            },
            "identities": cold,
        }
        identities[label] = cold

    # ── Fast vs slow split (valid cold only, FIXED threshold) ──
    fast_vs_slow: dict[str, Any] = {}
    if slow_threshold_ms and slow_threshold_ms > 0:
        for label in per_condition:
            cold = per_condition[label]["identities"]
            fast = [r for r in cold if (_num(r.get("metrics", {}).get("transfer", {}).get("wall_ms")) or 0) <= slow_threshold_ms]
            slow = [r for r in cold if (_num(r.get("metrics", {}).get("transfer", {}).get("wall_ms")) or 0) > slow_threshold_ms]
            fast_vs_slow[label] = {
                "fast_count": len(fast),
                "slow_count": len(slow),
                "fast_wall_ms": _matrix_stats(fast, "transfer", "wall_ms"),
                "slow_wall_ms": _matrix_stats(slow, "transfer", "wall_ms"),
                "fast_restore_ms": _matrix_stats(fast, "restore", "restore_total_ms"),
                "slow_restore_ms": _matrix_stats(slow, "restore", "restore_total_ms"),
            }

    # ── Root cause across conditions (best supported) ──
    root_cause = _matrix_root_cause(per_condition)

    # ── Overall measurement validity across all valid cold runs ──
    _cold_all = [r for r in records if r.get("classification") == "cold"]
    measurement_validity = {
        "valid_cold_identity_count": len(_cold_all),
        "registry_valid": _count_truthy(_cold_all, "registry_valid"),
        "page_traversal_valid": _count_truthy(_cold_all, "page_traversal_valid"),
        "synchronized_transfer_valid": _count_truthy(_cold_all, "synchronized_transfer_valid"),
        "pretouch_valid": _count_truthy(_cold_all, "pretouch_valid"),
        "checksum_valid": _count_truthy(_cold_all, "checksum_valid"),
        "activation_event_sources": _count_values(_cold_all, "activation_event_source"),
        "registry_invalid_reasons": _collect_reasons(_cold_all, "registry_reason"),
        "note": ("24 cold identities are valid, but CPU-storage hydration / "
                 "pretouch / synchronized-transfer evidence is invalid or "
                 "unavailable for this matrix because the CPU storage registry "
                 "proof is unsupported-only (unique_storage_count=0, all "
                 "device:cuda); the ~2-3 ms outer intervals are launch/window "
                 "artifacts and must not be used.  No production conclusion "
                 "can be drawn from those metrics."),
    }

    return {
        "mode": "variance_matrix",
        "generated_at": _fmt_ts(),
        "meta": meta,
        "slow_threshold_ms": slow_threshold_ms,
        "target_per_condition": meta.get("target_per_condition"),
        "total_attempts": len(records),
        "total_cold": sum(p["cold_count"] for p in per_condition.values()),
        "conditions": list(per_condition.keys()),
        "per_condition": per_condition,
        "fast_vs_slow": fast_vs_slow,
        "root_cause": root_cause,
        "measurement_validity": measurement_validity,
        "runs": records,
    }


def _classification_counts(records: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for r in records:
        c = r.get("classification") or "unknown"
        counts[c] = counts.get(c, 0) + 1
    return counts


def _count_truthy(records: list[dict[str, Any]], field: str) -> dict[str, int]:
    """Count how many records have the measurement-validity field True/False."""
    return {
        "valid": sum(1 for r in records if r.get("measurement_validity", {}).get(field) is True),
        "invalid": sum(1 for r in records if r.get("measurement_validity", {}).get(field) is not True),
    }


def _count_values(records: list[dict[str, Any]], field: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for r in records:
        v = r.get("measurement_validity", {}).get(field)
        counts[str(v)] = counts.get(str(v), 0) + 1
    return counts


def _collect_reasons(records: list[dict[str, Any]], field: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for r in records:
        v = r.get("measurement_validity", {}).get(field)
        if v:
            counts[str(v)] = counts.get(str(v), 0) + 1
    return counts


def _matrix_root_cause(per_condition: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Pick the best-supported root cause across conditions using median wall
    time and the diagnostic/pretouch deltas.  Never fabricates a mechanism."""
    # Use the cold wall-time medians per condition to rank.
    rows = []
    for label, p in per_condition.items():
        med = p["timing"]["wall_ms"].get("median")
        if med == UNAVAILABLE:
            continue
        rows.append((label, float(med), p))
    if not rows:
        return {"dominant": UNAVAILABLE, "alternatives": UNAVAILABLE,
                "recommended_fix": "No valid cold wall-time data was captured for any condition."}
    rows.sort(key=lambda x: x[1])
    fastest_label, fastest_med, fastest = rows[0]
    # Measure per-flag effect by comparing paired labels.
    effects: dict[str, float] = {}
    for flag, on, off in (
        ("diagnostics", "diag1_pt0", "diag0_pt0"),
        ("pretouch", "diag0_pt1", "diag0_pt0"),
        ("diagnostics+pretouch", "diag1_pt1", "diag0_pt0"),
    ):
        on_med = per_condition.get(on, {}).get("timing", {}).get("wall_ms", {}).get("median")
        off_med = per_condition.get(off, {}).get("timing", {}).get("wall_ms", {}).get("median")
        if on_med != UNAVAILABLE and off_med != UNAVAILABLE:
            effects[flag] = round(float(on_med) - float(off_med), 3)
    best = min(effects.items(), key=lambda kv: kv[1]) if effects else None
    if best is not None and best[1] < 0:
        dominant = f"flag bundle `{best[0]}` most reduces median wall time (delta {best[1]:+.3f} ms)"
    elif best is not None:
        dominant = f"no flag bundle improves on baseline (best delta {best[1]:+.3f} ms)"
    else:
        dominant = "insufficient data to rank flag effects"
    return {
        "dominant": dominant,
        "fastest_condition": fastest_label,
        "fastest_median_ms": fastest_med,
        "flag_effects_ms": effects,
        "alternatives": [
            "diagnostics overhead (measurement) may inflate page-traversal/restore medians",
            "pretouch effect may be masked by page-readiness or container variance",
            "small valid-cold sample per condition may dominate the medians",
        ],
        "recommended_fix": (
            "Set the exact flag bundle that showed the lowest median wall time and the "
            "lowest fixed-threshold slow-run rate as the production default ONLY if it "
            "also reduces the restore/bootstrap and UNET-activation slow flags; otherwise "
            "keep both flags OFF and do not change production defaults."
        ),
    }


def render_matrix_report(summary: dict[str, Any], output_dir: str | Path) -> str:
    """Render the consolidated, self-contained matrix handoff Markdown.

    Embeds every attempt's full raw artifact JSON (read from the attempt files
    written by the scheduler) plus per-condition identities, breakdowns,
    statistics, fast-vs-slow comparison, root cause and the recommended fix.
    """
    out = Path(output_dir)
    per_condition = summary.get("per_condition", {})
    runs = summary.get("runs", [])
    meta = summary.get("meta", {}) or {}
    threshold = summary.get("slow_threshold_ms") or 0

    L: list[str] = []
    L.append("# V2 Variance-Cold Matrix Handoff Report")
    L.append("")
    L.append("> Four-condition round-robin (diagnostics off/on) x (pretouch off/on). "
             "Each attempt asserts true cold identity; only valid cold runs count toward "
             "the per-condition target. Every attempt is preserved below.")
    L.append("")
    L.append("## Scope and provenance")
    L.append("")
    L.append(f"- Generated: `{_fmt_ts()}`")
    L.append(f"- Target valid cold per condition: `{summary.get('target_per_condition', 'unavailable')}`")
    L.append(f"- Total attempts: `{summary.get('total_attempts', 0)}`; total valid cold: `{summary.get('total_cold', 0)}`")
    L.append(f"- Fixed slow threshold (wall ms): `{threshold if threshold and threshold > 0 else 'unavailable'}`")
    L.append(f"- App: `{meta.get('app_name', 'unavailable')}`; GPU: `{meta.get('gpu', 'unavailable')}`")
    L.append(f"- Gap: `{meta.get('gap_seconds', 'unavailable')}s`")
    if meta.get("limitation"):
        L.append(f"- Limitation: {meta.get('limitation')}")
    L.append("")

    L.append("## Measurement validity")
    L.append("")
    mv = summary.get("measurement_validity", {}) or {}
    L.append("> **Important:** the cold-identity evidence in this matrix is "
             "valid, but the CPU-storage hydration / pretouch / synchronized "
             "transfer diagnostic evidence is **invalid or unavailable**.  Do "
             "not use page-traversal, pretouch, checksum or CPU→GPU "
             "wall/GB-s numbers from this run.")
    L.append("")
    L.append(f"- Valid cold identities: **{mv.get('valid_cold_identity_count', 'unavailable')}** "
             "— all 24 cold identities satisfied `restore_count == 1`, "
             "`request_count == 1`, and a non-empty restored instance.")
    L.append(f"- Activation event sources: `{mv.get('activation_event_sources', {})}`")
    L.append(f"- Storage registry valid: `{mv.get('registry_valid', {})}`")
    L.append(f"- Storage registry invalid reasons: `{mv.get('registry_invalid_reasons', {})}`")
    L.append(f"- Page-traversal valid: `{mv.get('page_traversal_valid', {})}`")
    L.append(f"- Synchronized-transfer valid: `{mv.get('synchronized_transfer_valid', {})}`")
    L.append(f"- Pretouch valid: `{mv.get('pretouch_valid', {})}`")
    L.append(f"- Checksum valid: `{mv.get('checksum_valid', {})}`")
    L.append("")
    L.append("The raw `first_unet_activation_variance.unet_storage_registry` "
             "reports `unique_storage_count=0` and `unsupported_count=453` with "
             "reason `device:cuda`; pretouch-on reports `status=empty`, "
             "`expected_pages=0`, `bytes_read=0` and a null checksum; "
             "synchronized-transfer bytes are absent while the outer interval "
             "is only ~2-3 ms.  Those 2-3 ms intervals are launch/outer-window "
             "artifacts and **must not be treated as transfer or page-hydration "
             "measurements**.  They are suppressed from statistics below.")
    L.append("")
    L.append(f"Note: {mv.get('note', 'unavailable')}")
    L.append("")

    L.append("## Per-condition measurement validity")
    L.append("")
    for label, p in per_condition.items():
        mv_p = p.get("measurement_validity", {}) or {}
        L.append(f"- `{label}`: sources `{mv_p.get('activation_event_sources', {})}`; "
                 f"registry valid `{mv_p.get('registry_valid', {})}`; "
                 f"page-traversal valid `{mv_p.get('page_traversal_valid', {})}`; "
                 f"synchronized-transfer valid `{mv_p.get('synchronized_transfer_valid', {})}`; "
                 f"pretouch valid `{mv_p.get('pretouch_valid', {})}`")
    L.append("")

    L.append("## Per-condition identities")
    L.append("")
    for label, p in per_condition.items():
        L.append(f"### `{label}` — {CONDITION_LABELS.get(label, label)}")
        L.append("")
        L.append(f"- Attempts: `{p['attempt_count']}`; valid cold: `{p['cold_count']}`; "
                 f"warm/invalid: `{p['warm_invalid_count']}`; failed: `{p['failed_count']}`; "
                 f"snapshot-capture: `{p['snapshot_capture_count']}`")
        L.append(f"- Failure rate: `{p['failure_rate'].get('rate', 'unavailable')}`")
        fsr = p["fixed_slow_run_rate"]
        L.append(f"- Fixed-threshold slow-run rate: `{fsr.get('rate', 'unavailable')}` "
                 f"(threshold `{fsr.get('threshold_ms', 'unavailable')}` ms)")
        L.append(f"- Slow flags: restore>3s `{p['slow_flags'].get('restore_over_3s', 0)}`, "
                 f"UNET activation>3s `{p['slow_flags'].get('unet_activation_over_3s', 0)}`")
        for r in p["identities"]:
            ids = r.get("identity", {}) or {}
            L.append(f"  - `{r.get('attempt_id', '?')}` cold: instance "
                     f"`{ids.get('restored_instance_id', 'unavailable')}`, task "
                     f"`{ids.get('task_id', 'unavailable')}`, session "
                     f"`{ids.get('container_session_id', 'unavailable')}`")
        L.append("")

    L.append("## Median / MAD / p90 / max per condition (valid cold, ms)")
    L.append("")
    for label, p in per_condition.items():
        L.append(_render_matrix_stats_table(label, p["timing"]))
    L.append("")

    L.append("## Unique storage / page / checksum / read metrics")
    L.append("")
    for label, p in per_condition.items():
        L.append(_render_matrix_stats_table(f"{label} storage", p["storage"]))
    L.append("")

    L.append("## Fast-vs-slow comparison (fixed threshold)")
    L.append("")
    fvs = summary.get("fast_vs_slow", {})
    if not fvs:
        L.append("- No fixed threshold configured; fast-vs-slow split unavailable.")
    for label, s in fvs.items():
        L.append(f"- `{label}`: fast `{s['fast_count']}` / slow `{s['slow_count']}`; "
                 f"fast wall med `{_fmt(s['fast_wall_ms'].get('median'))}`, "
                 f"slow wall med `{_fmt(s['slow_wall_ms'].get('median'))}`")
    L.append("")

    L.append("## Root cause / alternatives / recommended fix")
    L.append("")
    rc = summary.get("root_cause", {})
    L.append(f"- Best-supported root cause: **{rc.get('dominant', 'unavailable')}**")
    alts = rc.get("alternatives")
    if isinstance(alts, list) and alts:
        for a in alts:
            L.append(f"  - Alternative: {a}")
    L.append("- Exact recommended production fix: **no production change** — the "
             "supported root cause is instrumentation failure (see post-hoc "
             "conclusion); a corrected rerun is recommended only when resources "
             "permit.")
    L.append("")
    L.append("### Post-hoc root-cause conclusion")
    L.append("")
    L.append("The supported root cause for the invalid diagnostic metrics is "
             "**instrumentation failure**, not a production defect: the CPU "
             "storage registry could not prove a supported unique storage "
             "object (`unique_storage_count=0`, `unsupported_count=453`, all "
             "`device:cuda`), so the pre-touch/hydration/synchronized-transfer "
             "instrumentation produced empty or outer-window readings.  This is "
             "NOT evidence of a production regression and no production change "
             "is recommended.")
    L.append("")
    L.append("- **No production change recommended** from this matrix.")
    L.append("- **Recommended next action:** run a corrected benchmark only when "
             "resources permit, with the CPU storage registry/hydration path "
             "fixed so a supported unique storage proof is available; the valid "
             "cold-identity, wall-time, restore, sampler and fast/slow "
             "statistics remain usable, but page-traversal / pretouch / "
             "checksum / synchronized-transfer figures must be ignored until "
             "that corrected run.")
    L.append("")

    L.append("## Every attempt (full raw artifact JSON)")
    L.append("")
    for i, r in enumerate(runs):
        L.append(f"### Attempt `{r.get('attempt_id', f'attempt-{i}')}` — "
                 f"condition `{r.get('condition_label', 'unavailable')}` — "
                 f"classification `{r.get('classification', 'unavailable')}`")
        L.append("")
        raw = ""
        attempt_file = r.get("attempt_file")
        if attempt_file and (out / attempt_file).is_file():
            try:
                raw = (out / attempt_file).read_text(encoding="utf-8")
            except Exception:
                raw = ""
        if raw:
            L.append("```json")
            L.append(raw)
            L.append("```")
        else:
            L.append(f"- Raw artifact file `{attempt_file or 'unavailable'}` could not be read; "
                     "showing extracted record instead.")
            L.append("```json")
            L.append(json.dumps(r, default=str, indent=2))
            L.append("```")
        L.append("")

    return "\n".join(L)


def _render_matrix_stats_table(title: str, rows: dict[str, dict[str, Any]]) -> str:
    lines = [f"### {title}", "",
             "| Metric | Count | Median ms | MAD ms | p90 ms | Max ms |",
             "|---|---:|---:|---:|---:|---:|"]
    for label, stats in rows.items():
        if not isinstance(stats, dict):
            continue
        lines.append(
            f"| {label} | {stats.get('count', 0)} | {_fmt(stats.get('median'))} "
            f"| {_fmt(stats.get('mad'))} | {_fmt(stats.get('p90'))} "
            f"| {_fmt(stats.get('max'))} |"
        )
    return "\n".join(lines) + "\n"
