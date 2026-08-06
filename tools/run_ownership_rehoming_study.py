"""Ownership + post-restore rehoming study runner (shadow deployments only).

Modes:

  ownership  -- cold-run study against one ownership shadow app (GCP):
                validates exclusive UNET ownership (worker claim/release,
                graph join-or-adopt, exactly one migration, no cancelled
                request-used workers, no sampler acquire while a future is
                pending, zero SIGSEGV).  ``--phase probes_on|probes_off``
                selects the page-path probe arm (env baked at deploy).
  rehoming   -- paired post-restore rehoming measurements via the dedicated
                shadow method ``run_rehoming_experiment`` (no graph
                execution): original restored-storage H2D vs fresh-clone
                H2D, alternating order, byte-equality proof.
  integrated -- 7 valid unpinned cold requests with exclusive ownership +
                post-restore rehoming + all heavy diagnostics off.

Usage:
  python tools/run_ownership_rehoming_study.py ownership --app NAME [--phase probes_on] [--target-cold 4] [--max-attempts 12] [--skip-first 2]
  python tools/run_ownership_rehoming_study.py rehoming --app NAME [--runs 4]
  python tools/run_ownership_rehoming_study.py integrated --app NAME [--target-cold 7] [--max-attempts 12] [--skip-first 2]
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from canonical_execution import build_execution_plan, execute_plan
from modal_client import check_active_warmup_profile, set_active_warmup_profile
from comfymodal_runtime.modal_transport import ModalTransport, HandleCache
from comfymodal_runtime.restore_plan import RemoteRestorePlanPublisher
from comfymodal_runtime.trace import RuntimeTrace
from production_workflow import normalize_production_options
from tools.benchmark_v2_direct import (
    _classify_attempt,
    _extract_page_path_probe,
    _host_gpu_uuid,
    _identity,
    _remote_entry_wall_iso,
    _run_one,
    _timing,
    _validate_cold_identity,
    _variance_origin,
)

WORKFLOW_PATH = ROOT / "latest_benchmark_workflow.json"
WORKSPACES_PATH = ROOT / ".modal_workspaces.json"
GAP_SECONDS = float(os.environ.get("V2_OWNERSHIP_GAP_SECONDS", "25"))
OUTPUT_ROOT = Path(os.environ.get(
    "COMFYMODAL_V2_OWNERSHIP_OUTPUT",
    str(Path(os.environ.get("LOCALAPPDATA", str(ROOT))) / "comfymodal-data" / "benchmarks" / "runs"),
))
GPU = os.environ.get("COMFYMODAL_V2_GPU", "rtx-pro-6000")


def _load_workspace() -> dict[str, Any]:
    data = json.loads(WORKSPACES_PATH.read_text(encoding="utf-8"))
    active_id = data.get("active_workspace_id")
    for workspace in data.get("workspaces", []):
        if workspace.get("id") == active_id:
            if not workspace.get("token_id") or not workspace.get("token_secret"):
                raise RuntimeError("active Modal workspace has no credentials")
            os.environ["MODAL_TOKEN_ID"] = str(workspace["token_id"])
            os.environ["MODAL_TOKEN_SECRET"] = str(workspace["token_secret"])
            return workspace
    raise RuntimeError("active Modal workspace was not found")


def _load_workflow() -> tuple[dict[str, Any], dict[str, Any]]:
    snapshot = json.loads(WORKFLOW_PATH.read_text(encoding="utf-8"))
    payload = snapshot.get("payload", snapshot)
    workflow = payload.get("prompt", payload)
    modal_options = payload.get("modal_options", {})
    if not isinstance(workflow, dict):
        raise RuntimeError("workflow prompt must be an object")
    if not isinstance(modal_options, dict):
        modal_options = {}
    return workflow, modal_options


def _new_output_dir(mode: str) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H-%M-%S")
    out = OUTPUT_ROOT / f"v2_{stamp}_{mode}"
    out.mkdir(parents=True, exist_ok=True)
    return out


# ── Trace extraction helpers ──────────────────────────────────────────────


def _event_list(result: dict[str, Any]) -> list[dict[str, Any]]:
    trace = result.get("trace", {}) if isinstance(result, dict) else {}
    events = trace.get("events", []) if isinstance(trace, dict) else []
    return [e for e in events if isinstance(e, dict)]


def _events_named(result: dict[str, Any], name: str) -> list[dict[str, Any]]:
    return [e for e in _event_list(result) if e.get("name") == name]


def _first_meta(result: dict[str, Any], name: str) -> dict[str, Any] | None:
    for e in _events_named(result, name):
        m = e.get("metadata")
        if isinstance(m, dict):
            return m
    return None


def _extract_ownership_evidence(result: dict[str, Any]) -> dict[str, Any]:
    """Extract exclusive-ownership evidence from the request trace."""
    ev: dict[str, Any] = {}
    claim = _first_meta(result, "unet_ownership_claim")
    release = _first_meta(result, "unet_ownership_release")
    joins = _events_named(result, "unet_graph_join")
    reconciliation = _first_meta(result, "unet_early_activation_reconciliation")
    terminal = _first_meta(result, "unet_early_activation_terminal")
    ev["ownership_claim"] = claim
    ev["ownership_release"] = release
    ev["graph_joins"] = [m for m in (e.get("metadata") for e in joins) if isinstance(m, dict)]
    ev["reconciliation"] = reconciliation
    ev["worker_terminal"] = terminal
    ev["sampler_boundaries"] = []
    for e in _events_named(result, "sampler_lane_wait_start"):
        m = e.get("metadata")
        if isinstance(m, dict):
            ev["sampler_boundaries"].append({
                "mono_ns": e.get("monotonic_ns"),
                "blocking_owner": m.get("blocking_owner", ""),
            })
    # Load accounting.
    ev["worker_load_count"] = len(_events_named(result, "unet_early_activation_load_start"))
    ev["consumed_count"] = len(_events_named(result, "unet_early_activation_consumed"))
    ev["fallback_count"] = len(_events_named(result, "unet_early_activation_fallback"))
    graph_loads: list[dict[str, Any]] = []
    for e in _events_named(result, "graph_gpu_load_start"):
        m = e.get("metadata")
        if isinstance(m, dict) and m.get("contains_registered_unet"):
            graph_loads.append({
                "mono_ns": e.get("monotonic_ns"),
                "caller": m.get("caller_classification", ""),
            })
    ev["graph_unet_load_count"] = len(graph_loads)
    ev["graph_unet_loads"] = graph_loads
    # Graph load wall (potential duplicate migration detector).
    _graph_walls: list[float] = []
    for s in _events_named(result, "graph_gpu_load_start"):
        for en in _events_named(result, "graph_gpu_load_end"):
            pass
    starts = _events_named(result, "graph_gpu_load_start")
    ends = _events_named(result, "graph_gpu_load_end")
    for s, en in zip(starts, ends):
        sm = s.get("metadata") or {}
        em = en.get("metadata") or {}
        if not sm.get("contains_registered_unet"):
            continue
        sn = s.get("monotonic_ns")
        en_ns = en.get("monotonic_ns")
        if isinstance(sn, (int, float)) and isinstance(en_ns, (int, float)) and en_ns >= sn:
            _graph_walls.append(round((en_ns - sn) / 1_000_000, 3))
    ev["graph_unet_load_wall_ms_list"] = _graph_walls
    # Worker synchronized transfer (state/event based).
    ls = _first_meta(result, "unet_early_activation_load_start")
    le = _first_meta(result, "unet_early_activation_load_end")
    if isinstance(ls, dict) and isinstance(le, dict):
        ev["worker_transfer_wall_ms"] = le.get("load_wall_ms")
    rehome = reconciliation.get("rehome_clone") if isinstance(reconciliation, dict) else None
    ev["rehome_clone"] = rehome
    return ev


def _ownership_checks(ev: dict[str, Any]) -> dict[str, Any]:
    """Acceptance checks for the exclusive-ownership arms."""
    checks: dict[str, Any] = {}
    rec = ev.get("reconciliation") or {}
    term = ev.get("worker_terminal") or {}
    status = str(term.get("status", "") or rec.get("status", "") or "")
    checks["worker_terminal_status"] = status
    checks["worker_cancelled"] = bool(rec.get("cancelled")) or status == "cancelled"
    checks["transfer_count"] = rec.get("transfer_count", term.get("transfer_count", 0))
    checks["exactly_one_migration"] = bool(
        ev.get("worker_load_count") == 1 and checks["transfer_count"] == 1
    )
    # Duplicate graph load: any request-scoped graph UNET load taking >1.5 s
    # after the worker claimed ownership is a second real migration.
    _graph_walls = ev.get("graph_unet_load_wall_ms_list") or []
    checks["graph_unet_load_wall_ms_list"] = _graph_walls
    checks["suspected_duplicate_graph_load"] = bool(
        _graph_walls and max(_graph_walls) > 1500.0
    )
    # No sampler acquire while a future was pending:
    # a sampler wait_start with blocking_owner absent is only valid when the
    # worker ownership was ALREADY released (future terminal).
    _claim = ev.get("ownership_claim") or {}
    _release = ev.get("ownership_release") or {}
    _claim_ns = _claim.get("claimed_mono_ns", 0) or 0
    _release_ns = _release.get("released_mono_ns", 0) or 0
    violations = []
    for sb in ev.get("sampler_boundaries") or []:
        if sb.get("blocking_owner"):
            continue
        _wait_ns = sb.get("mono_ns") or 0
        if _claim_ns and _release_ns and _wait_ns and _wait_ns < _release_ns:
            violations.append({
                "mono_ns": _wait_ns,
                "reason": "sampler acquired with owner=absent while worker ownership was still held",
            })
    checks["sampler_owner_absent_while_pending"] = violations
    checks["no_sampler_absent_while_pending"] = not violations
    # No request-used worker ending cancelled.
    checks["no_request_used_worker_cancelled"] = not checks["worker_cancelled"]
    return checks


# ── Crash detection ─────────────────────────────────────────────────────
# The runner must stop IMMEDIATELY on a crashed container (exit 139 /
# snapshot-restore failure / stream loss) and dump a diagnosis instead of
# silently retrying through the crash.

_CRASH_PATTERNS: tuple[str, ...] = (
    "segmentation fault",
    "segfault",
    "exit code 139",
    "exit code: 139",
    "exit 139",
    "signal 11",
    "SIGSEGV",
    "Transient snapshot error",
    "failed to restore container from snapshot",
    "stream_failed",
    "Server has lost track of input",
    "missing output for previous input",
    "ServiceError",
    "Runner failed with exit code: 1",
)


def _crash_signature(error_text: str) -> str:
    """Return the first crash pattern found in *error_text*, or ""."""
    for pattern in _CRASH_PATTERNS:
        if pattern.lower() in str(error_text).lower():
            return pattern
    return ""


def _dump_crash_diagnostics(output_dir: Path, artifact: dict[str, Any], signature: str) -> None:
    """Write a crash-diagnostics pack and a marker file, then print the
    diagnosis.  Called by every study mode BEFORE aborting the run."""
    crash: dict[str, Any] = {
        "detected": True,
        "signature": signature,
        "artifact": artifact,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "recommended_action": (
            "STOPPED: container crashed in the UNET load path.  Inspect the "
            "attempt artifact + this pack; do not continue the study through "
            "the crash."
        ),
    }
    (output_dir / "crash_diagnostics.json").write_text(
        json.dumps(crash, default=str, indent=2), encoding="utf-8"
    )
    (output_dir / "CRASH_DETECTED").write_text(
        f"{signature}\n{datetime.now(timezone.utc).isoformat()}\n",
        encoding="utf-8",
    )
    print(
        f"[v2.ownership_rehoming] CRASH DETECTED: {signature}\n"
        f"[v2.ownership_rehoming] crash_diagnostics={output_dir / 'crash_diagnostics.json'}\n"
        f"[v2.ownership_rehoming] request_id={artifact.get('request_id', '') or artifact.get('run_id', '')}\n"
        f"[v2.ownership_rehoming] error={str(artifact.get('error', ''))[:500]}",
        flush=True,
    )


def _check_attempt_crash(
    output_dir: Path, artifact: dict[str, Any],
) -> str:
    """Detect a crashed container in *artifact*; when found, dump the crash
    pack and return the signature (else "")."""
    error_text = " ".join([
        str(artifact.get("error", "") or ""),
        str(artifact.get("variance", {}).get("failures", [])),
    ])
    signature = _crash_signature(error_text)
    if signature:
        _dump_crash_diagnostics(output_dir, artifact, signature)
    return signature


# ── ownership mode ────────────────────────────────────────────────────────


async def _run_ownership_study(
    workflow: dict[str, Any],
    modal_options: dict[str, Any],
    workspace: dict[str, Any],
    transport: ModalTransport,
    output_dir: Path,
    *,
    app_name: str,
    phase: str,
    target_cold: int,
    max_attempts: int,
    skip_first: int,
) -> dict[str, Any]:
    os.environ["COMFYMODAL_V2_APP_NAME"] = app_name
    prev_identity: dict[str, Any] | None = None
    records: list[dict[str, Any]] = []
    cold = 0
    for index in range(max_attempts):
        _run_id = f"ownership-{phase}-{index}-{uuid.uuid4().hex[:8]}"
        _start_ts = datetime.now(timezone.utc).isoformat()
        origin = _variance_origin(
            index, pretouch=0, app_name=app_name, teardown="minimal",
        )
        origin["variance_mode"] = f"ownership_{phase}"
        artifact: dict[str, Any] = {}
        try:
            artifact = await _run_one(
                index=index, workflow=workflow, modal_options=modal_options,
                workspace=workspace, transport=transport, output_dir=output_dir,
                _extra_origin=origin, _defer_waterfall=True,
            )
        except Exception as exc:  # noqa: BLE001
            artifact = {
                "run_index": index, "run_id": _run_id, "request_id": "",
                "identity": {}, "result": {}, "timing": {},
                "variance": {"cold_valid": False, "cold": False,
                             "failures": [f"run raised: {str(exc)[:300]}"]},
                "start_ts": _start_ts, "end_ts": datetime.now(timezone.utc).isoformat(),
                "mode": f"ownership_{phase}", "error": str(exc)[:300],
            }
        identity = artifact.get("identity", {}) or {}
        result = artifact.get("result", {}) if isinstance(artifact.get("result"), dict) else {}
        timing = artifact.get("timing", {}) or {}
        if not timing:
            timing = _timing(
                result,
                artifact.get("wall_ms", 0.0),
                command_start_unix_ms=artifact.get("command_start_unix_ms"),
                response_received_unix_ns=artifact.get("response_received_unix_ns"),
            )
        cold_check = _validate_cold_identity(
            identity, run_index=index, pretouch=0, prev_identity=prev_identity,
        )
        artifact["run_id"] = _run_id
        artifact["attempt_file"] = f"attempt_{index:04d}.json"
        artifact["phase"] = phase
        artifact["excluded_snapshot_builder"] = index < skip_first
        if not artifact.get("error"):
            artifact["variance"] = {
                "cold_valid": cold_check["cold_valid"],
                "cold": cold_check["cold"],
                "failures": cold_check["failures"],
                "freshness_checked": cold_check["freshness_checked"],
            }
        artifact["classification"] = _classify_attempt(artifact)
        artifact["ownership_evidence"] = _extract_ownership_evidence(result)
        artifact["ownership_checks"] = _ownership_checks(artifact["ownership_evidence"])
        artifact["page_path"] = _extract_page_path_probe(result)
        artifact["remote_entry_ts"] = _remote_entry_wall_iso(result)
        artifact["host_diagnostics"] = artifact.get("host_diagnostics", {})
        artifact["gpu_uuid"] = _host_gpu_uuid(artifact)
        record = {
            "run_index": index,
            "attempt_file": artifact["attempt_file"],
            "phase": phase,
            "classification": artifact["classification"],
            "cold_valid": bool(artifact["variance"].get("cold_valid")),
            "cold": bool(artifact["variance"].get("cold")),
            "excluded_snapshot_builder": artifact["excluded_snapshot_builder"],
            "error": artifact.get("error", ""),
            "identity": identity,
            "timing": timing,
            "ownership_checks": artifact["ownership_checks"],
            "ownership_evidence": artifact["ownership_evidence"],
            "page_path": artifact["page_path"],
            "gpu_uuid": artifact["gpu_uuid"],
        }
        records.append(record)
        (output_dir / artifact["attempt_file"]).write_text(
            json.dumps(artifact, default=str, indent=2), encoding="utf-8"
        )
        # ── Crash detection: stop IMMEDIATELY on a crashed container ──
        _crash = _check_attempt_crash(output_dir, artifact)
        if _crash:
            summary: dict[str, Any] = {
                "mode": "ownership",
                "app_name": app_name,
                "phase": phase,
                "target_cold": target_cold,
                "max_attempts": max_attempts,
                "skip_first": skip_first,
                "gap_seconds": GAP_SECONDS,
                "valid_cold": cold,
                "aborted": True,
                "abort_reason": f"crash_detected:{_crash}",
                "records": records,
            }
            (output_dir / "summary.json").write_text(
                json.dumps({k: v for k, v in summary.items() if k != "records"}, default=str, indent=2),
                encoding="utf-8",
            )
            raise RuntimeError(
                f"ownership {phase}: container crash detected ({_crash}) at "
                f"attempt {index}; study stopped immediately; diagnosis in "
                f"{output_dir / 'crash_diagnostics.json'}"
            )
        if index < skip_first:
            status = "SKIPPED(snapshot-builder)"
        elif artifact["classification"] == "cold":
            cold += 1
            prev_identity = identity
            status = "COLD"
        else:
            status = artifact["classification"].upper()
        print(
            f"[v2.ownership] phase={phase} index={index} id={_run_id} "
            f"status={status} cold={cold}/{target_cold} "
            f"error={artifact.get('error', '') or 'absent'}",
            flush=True,
        )
        if cold >= target_cold:
            break
        if index < max_attempts - 1:
            print(f"[v2.ownership] phase=gap seconds={GAP_SECONDS}", flush=True)
            await asyncio.sleep(GAP_SECONDS)
    summary: dict[str, Any] = {
        "mode": "ownership",
        "app_name": app_name,
        "phase": phase,
        "target_cold": target_cold,
        "max_attempts": max_attempts,
        "skip_first": skip_first,
        "gap_seconds": GAP_SECONDS,
        "valid_cold": cold,
        "records": records,
    }
    (output_dir / "summary.json").write_text(
        json.dumps({k: v for k, v in summary.items() if k != "records"}, default=str, indent=2),
        encoding="utf-8",
    )
    print(json.dumps({
        "output_dir": str(output_dir), "mode": "ownership", "phase": phase,
        "valid_cold": cold, "target_cold": target_cold,
    }, default=str), flush=True)
    return summary


# ── rehoming mode ─────────────────────────────────────────────────────────


async def _run_rehoming_study(
    workspace: dict[str, Any],
    transport: ModalTransport,
    output_dir: Path,
    *,
    app_name: str,
    runs: int,
) -> dict[str, Any]:
    os.environ["COMFYMODAL_V2_APP_NAME"] = app_name
    handle = await asyncio.to_thread(
        transport._v2_handle, workspace=workspace, gpu=GPU,
    )
    records: list[dict[str, Any]] = []
    orders = ["original_first", "clone_first"]
    attempts = runs + 1  # first attempt is the snapshot builder
    for index in range(attempts):
        order = orders[index % len(orders)]
        _run_id = f"rehoming-{index}-{uuid.uuid4().hex[:8]}"
        _start_ts = datetime.now(timezone.utc).isoformat()
        _req_id = f"v2-rehoming-{index}-{uuid.uuid4().hex[:12]}"
        _t0 = time.perf_counter()
        artifact: dict[str, Any] = {
            "run_index": index, "run_id": _run_id, "request_id": _req_id,
            "order": order, "start_ts": _start_ts, "mode": "rehoming",
        }
        try:
            fn = handle.run_rehoming_experiment
            remote = getattr(fn, "remote", None)
            if remote is not None and callable(getattr(remote, "aio", None)):
                result = remote.aio(order=order, request_id=_req_id)
                if asyncio.iscoroutine(result):
                    result = await result
            elif asyncio.iscoroutinefunction(fn):
                result = await fn(order=order, request_id=_req_id)
            else:
                result = await asyncio.to_thread(fn, order=order, request_id=_req_id)
            if asyncio.iscoroutine(result):
                result = await result
            artifact["result"] = result if isinstance(result, dict) else {"raw": str(result)[:300]}
        except Exception as exc:  # noqa: BLE001
            artifact["error"] = f"remote call failed: {type(exc).__name__}: {str(exc)[:300]}"
            artifact["result"] = {}
        artifact["wall_ms"] = round((time.perf_counter() - _t0) * 1000.0, 1)
        artifact["end_ts"] = datetime.now(timezone.utc).isoformat()
        _res = artifact.get("result") or {}
        identity = dict(_res.get("identity") or {})
        artifact["identity"] = identity
        artifact["excluded_snapshot_builder"] = index == 0
        _ok = bool(
            not artifact.get("error")
            and _res.get("status") == "ok"
            and (_res.get("cuda") or {}).get("available")
            and isinstance(_res.get("original_h2d"), dict)
            and isinstance(_res.get("clone_h2d"), dict)
            and isinstance(_res.get("clone"), dict)
        )
        _eq = _res.get("byte_equality_original_gpu_vs_clone") or {}
        _eq_ok = bool(_eq.get("status") == "all_equal" and _eq.get("equal", 0) > 0)
        artifact["measurement_valid"] = bool(_ok and _eq_ok)
        artifact["byte_equality"] = _eq
        artifact["attempt_file"] = f"attempt_{index:04d}.json"
        (output_dir / artifact["attempt_file"]).write_text(
            json.dumps(artifact, default=str, indent=2), encoding="utf-8"
        )
        _orig = _res.get("original_h2d") or {}
        _clone = _res.get("clone_h2d") or {}
        _cl = _res.get("clone") or {}
        record = {
            "run_index": index,
            "attempt_file": artifact["attempt_file"],
            "order": order,
            "excluded_snapshot_builder": artifact["excluded_snapshot_builder"],
            "valid": artifact["measurement_valid"],
            "status": _res.get("status", ""),
            "error": artifact.get("error", "") or _res.get("reason", ""),
            "identity": identity,
            "original_h2d_ms": _orig.get("wall_ms"),
            "original_h2d_gbps": _orig.get("gb_per_s"),
            "clone_h2d_ms": _clone.get("wall_ms"),
            "clone_h2d_gbps": _clone.get("gb_per_s"),
            "clone_wall_ms": _cl.get("wall_ms"),
            "clone_process_cpu_ms": _cl.get("process_cpu_ms"),
            "clone_bytes": _cl.get("bytes"),
            "combined_clone_plus_h2d_ms": (
                round(float(_cl.get("wall_ms") or 0.0) + float(_clone.get("wall_ms") or 0.0), 3)
                if _cl.get("wall_ms") and _clone.get("wall_ms") else None
            ),
            "byte_equality": _eq,
            "residency_after_clone": _cl.get("residency"),
            "backing_after_clone": _cl.get("backing", {}).get("counts"),
            "faults": _cl.get("faults"),
            "rss_mib": _cl.get("rss_mib"),
            "wall_ms": artifact["wall_ms"],
        }
        records.append(record)
        (output_dir / artifact["attempt_file"]).write_text(
            json.dumps(artifact, default=str, indent=2), encoding="utf-8"
        )
        # ── Crash detection: stop IMMEDIATELY on a crashed container ──
        _crash = _check_attempt_crash(output_dir, artifact)
        if _crash:
            summary: dict[str, Any] = {
                "mode": "rehoming",
                "app_name": app_name,
                "target_valid": runs,
                "valid": sum(1 for r in records if r.get("valid")),
                "aborted": True,
                "abort_reason": f"crash_detected:{_crash}",
                "records": records,
            }
            (output_dir / "summary.json").write_text(
                json.dumps({k: v for k, v in summary.items() if k != "records"}, default=str, indent=2),
                encoding="utf-8",
            )
            raise RuntimeError(
                f"rehoming: container crash detected ({_crash}) at attempt "
                f"{index}; study stopped immediately; diagnosis in "
                f"{output_dir / 'crash_diagnostics.json'}"
            )
        status = "SKIPPED(snapshot-builder)" if index == 0 else (
            "VALID" if artifact["measurement_valid"] else "INVALID"
        )
        print(
            f"[v2.rehoming] index={index} order={order} status={status} "
            f"orig_h2d={record['original_h2d_ms']}ms "
            f"clone_h2d={record['clone_h2d_ms']}ms "
            f"clone={record['clone_wall_ms']}ms "
            f"combined={record['combined_clone_plus_h2d_ms']}ms "
            f"eq={_eq.get('status', 'absent')}",
            flush=True,
        )
        if index < attempts - 1:
            print(f"[v2.rehoming] phase=gap seconds={GAP_SECONDS}", flush=True)
            await asyncio.sleep(GAP_SECONDS)
    valid = sum(1 for r in records if r.get("valid"))
    summary: dict[str, Any] = {
        "mode": "rehoming",
        "app_name": app_name,
        "target_valid": runs,
        "valid": valid,
        "records": records,
    }
    (output_dir / "summary.json").write_text(
        json.dumps({k: v for k, v in summary.items() if k != "records"}, default=str, indent=2),
        encoding="utf-8",
    )
    print(json.dumps({
        "output_dir": str(output_dir), "mode": "rehoming",
        "valid": valid, "target": runs,
    }, default=str), flush=True)
    return summary


# ── integrated mode ───────────────────────────────────────────────────────


async def _run_integrated_study(
    workflow: dict[str, Any],
    modal_options: dict[str, Any],
    workspace: dict[str, Any],
    transport: ModalTransport,
    output_dir: Path,
    *,
    app_name: str,
    target_cold: int,
    max_attempts: int,
    skip_first: int,
) -> dict[str, Any]:
    return await _run_ownership_study(
        workflow, modal_options, workspace, transport, output_dir,
        app_name=app_name, phase="integrated", target_cold=target_cold,
        max_attempts=max_attempts, skip_first=skip_first,
    )


# ── CLI ───────────────────────────────────────────────────────────────────


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=["ownership", "rehoming", "integrated"])
    parser.add_argument("--app", required=True)
    parser.add_argument("--phase", default="probes_on",
                        choices=["probes_on", "probes_off"])
    parser.add_argument("--target-cold", type=int, default=4)
    parser.add_argument("--max-attempts", type=int, default=12)
    parser.add_argument("--skip-first", type=int, default=2)
    parser.add_argument("--runs", type=int, default=4)
    args = parser.parse_args()

    workspace = _load_workspace()
    workflow, modal_options = _load_workflow()
    output_dir = _new_output_dir(args.mode)
    transport = ModalTransport(handle_cache=HandleCache())
    print(
        f"[v2.ownership_rehoming] mode={args.mode} app={args.app} "
        f"output={output_dir} gap={GAP_SECONDS}s",
        flush=True,
    )
    if args.mode == "rehoming":
        await _run_rehoming_study(
            workspace, transport, output_dir,
            app_name=args.app, runs=args.runs,
        )
    elif args.mode == "integrated":
        await _run_integrated_study(
            workflow, modal_options, workspace, transport, output_dir,
            app_name=args.app,
            target_cold=args.target_cold, max_attempts=args.max_attempts,
            skip_first=args.skip_first,
        )
    else:
        await _run_ownership_study(
            workflow, modal_options, workspace, transport, output_dir,
            app_name=args.app, phase=args.phase,
            target_cold=args.target_cold, max_attempts=args.max_attempts,
            skip_first=args.skip_first,
        )
    print(f"[v2.ownership_rehoming] output_dir={output_dir}", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
