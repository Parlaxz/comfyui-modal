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
    _extract_images,
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
    # Worker terminal status must be ready (the future completed normally).
    checks["worker_terminal_ready"] = status == "ready"
    # Graph join outcome must be ready (join or already_ready with a ready
    # outcome); a join that timed out / adopted is a fallback, not the clean
    # ownership path.
    join_outcomes = [
        str(m.get("outcome_status", ""))
        for m in (ev.get("graph_joins") or [])
        if isinstance(m, dict)
    ]
    checks["graph_join_outcomes"] = join_outcomes
    checks["graph_join_ready"] = bool(
        join_outcomes and all(o == "ready" for o in join_outcomes)
    )
    # Snapshot fallback (early-activation fallback elected) is a retry, never
    # a valid cold run.
    checks["fallback_count"] = int(ev.get("fallback_count") or 0)
    checks["no_fallback"] = checks["fallback_count"] == 0
    # Graph load reduced to cache validation only: any request-scoped graph
    # UNET load must be a sub-100 ms cache check (the worker already loaded
    # the model), not a second migration.
    _graph_walls = ev.get("graph_unet_load_wall_ms_list") or []
    checks["graph_load_cache_only"] = bool(
        _graph_walls and all(w <= 100.0 for w in _graph_walls)
    )
    # No rehome or heavy diagnostic work (all shadow gates baked off).
    checks["rehome_clone_present"] = bool(ev.get("rehome_clone"))
    return checks


# ── Container env assertion ────────────────────────────────────────────────
# ``_runtime_env`` silently dropped new gates in an earlier deployment, so the
# deploy script alone is NOT proof.  The runner probes the deployed container's
# effective environment once (before any measured run) and aborts when any
# gate value is wrong.

_EXPECTED_GATE_ENV: dict[str, str] = {
    "COMFYMODAL_V2_UNET_EXCLUSIVE_OWNER": "1",
    "COMFYMODAL_V2_UNET_REHOME_AFTER_RESTORE": "",
    "COMFYMODAL_V2_PAGE_PATH_PROBE": "",
    "COMFYMODAL_V2_SYNTH_H2D_PROBE": "",
    "COMFYMODAL_V2_UNET_BACKING_VERIFY": "",
    "COMFYMODAL_V2_ANON_UNET_SNAPSHOT": "",
    "COMFYMODAL_V2_UNET_PRETOUCH": "",
    "COMFYMODAL_V2_UNET_QUIESCED_TRANSFER": "",
    "COMFYMODAL_V2_VARIANCE_DIAGNOSTICS": "",
    "COMFYMODAL_V2_HOST_DIAGNOSTICS": "",
    "COMFYMODAL_V2_FULL_TRACE": "",
    "COMFYMODAL_V2_PAGEFAULT_TRACKING": "",
    "COMFYMODAL_V2_CLOUD": "",
    "COMFYMODAL_V2_REGION": "",
    "COMFYMODAL_V2_ENV_PROFILE": "production",
    "COMFYMODAL_V2_UNET_ACTIVATION_MODE": "late",
    "COMFYMODAL_V2_VAE_ACTIVATION_MODE": "sampling_end",
    "COMFYMODAL_V2_CLIP_CONDITIONING_CACHE": "1",
    "COMFYMODAL_EXACT_CLIP_CONDITIONING_CACHE": "1",
    "COMFYMODAL_V2_THREAD_POLICY": "TBASE",
    "COMFYMODAL_V2_SNAPSHOT_MODEL_ORDER": "O0",
    "COMFYMODAL_V2_CPU_REQUEST": "16",
    "COMFYMODAL_V2_MEMORY_REQUEST": "49152",
    "COMFYMODAL_V2_MEMORY_MB": "49152",
    "COMFYMODAL_V2_SINGLE_USE_CONTAINERS": "1",
    "COMFYMODAL_V2_MINIMAL_GPU_TEARDOWN": "",
    "COMFYMODAL_V2_CPU_MODEL_SNAPSHOT": "1",
    "COMFYMODAL_V2_VAE_SNAPSHOT": "1",
    "COMFYMODAL_V2_RELEASE_GPU_AFTER_REQUEST": "1",
    "COMFYMODAL_V2_PREFILL_LANES": "critical",
    "COMFYMODAL_V2_PREFILL_WAIT_FOR_UNET": "",
}

_OFF_TRUTHS = frozenset({"", "0", "false", "no", "off"})


def _gate_off(value: Any) -> bool:
    return str(value or "").strip().lower() in _OFF_TRUTHS


def _assert_container_env(
    probe: dict[str, Any],
    *,
    app_name: str,
    gpu: str,
    expect_cloud: str = "",
    expect_region: str = "",
    expect_lean: str = "",
) -> list[str]:
    """Assert the container env probe matches the study configuration.

    Returns a list of failures (empty = pass).  Never raises by itself; the
    caller aborts the study when failures are present.

    ``expect_cloud`` / ``expect_region`` allow controlled restore-mode
    phases to pin the deployment (COMFYMODAL_V2_CLOUD=gcp etc.) without
    failing the assertion; the default (empty) keeps the study unpinned.
    ``expect_lean`` ("1"/"0") asserts COMFYMODAL_V2_LEAN_SNAPSHOT reached
    the container — the lean production candidate must prove it, not
    assume it.
    """
    failures: list[str] = []
    env = probe.get("env") or {}
    if not isinstance(env, dict):
        return ["env probe returned no env mapping"]
    expected = dict(_EXPECTED_GATE_ENV)
    if expect_cloud:
        expected["COMFYMODAL_V2_CLOUD"] = expect_cloud
    if expect_region:
        expected["COMFYMODAL_V2_REGION"] = expect_region
    for key, exp_val in expected.items():
        actual = str(env.get(key, "") or "")
        if exp_val == "":
            if not _gate_off(actual):
                failures.append(
                    f"{key}: expected OFF, container has {actual!r}"
                )
        elif actual != exp_val:
            failures.append(
                f"{key}: expected {exp_val!r}, container has {actual!r}"
            )
    if expect_lean == "1":
        _lean_actual = str(env.get("COMFYMODAL_V2_LEAN_SNAPSHOT", "") or "")
        if _lean_actual not in ("1", "true", "yes", "on"):
            failures.append(
                "COMFYMODAL_V2_LEAN_SNAPSHOT: expected ON, "
                f"container has {_lean_actual!r}"
            )
    elif expect_lean == "0":
        _lean_actual = str(env.get("COMFYMODAL_V2_LEAN_SNAPSHOT", "") or "")
        if not _gate_off(_lean_actual):
            failures.append(
                "COMFYMODAL_V2_LEAN_SNAPSHOT: expected OFF, "
                f"container has {_lean_actual!r}"
            )
    remote_app = str(env.get("COMFYMODAL_V2_APP_NAME", "") or "")
    if remote_app and remote_app != app_name:
        failures.append(
            f"COMFYMODAL_V2_APP_NAME: expected {app_name!r}, container has {remote_app!r}"
        )
    try:
        min_containers = int(probe.get("min_containers", -1))
        scaledown = int(probe.get("scaledown_window", -1))
    except (TypeError, ValueError):
        min_containers = scaledown = -1
    if min_containers != 0:
        failures.append(f"min_containers: expected 0, container has {min_containers}")
    if scaledown != 4:
        failures.append(f"scaledown_window: expected 4, container has {scaledown}")
    spec_single = str(probe.get("single_use_containers_spec", ""))
    if spec_single and spec_single.lower() not in ("true", "1", "yes"):
        failures.append(
            f"single_use_containers spec: expected True, container has {spec_single}"
        )
    gpu_list = probe.get("gpu") or []
    if gpu_list and gpu and not any(
        str(g).lower() == str(gpu).lower() for g in gpu_list
    ):
        failures.append(f"gpu: expected {gpu!r}, container has {gpu_list}")
    try:
        cpu = int(probe.get("cpu", -1))
        memory_mb = int(probe.get("memory_mb", -1))
    except (TypeError, ValueError):
        cpu = memory_mb = -1
    if cpu != 16:
        failures.append(f"cpu: expected 16, container has {cpu}")
    if memory_mb != 49152:
        failures.append(f"memory_mb: expected 49152, container has {memory_mb}")
    return failures


def _assert_output_correctness(result: dict[str, Any]) -> list[str]:
    """Output correctness: image descriptors with sha256 asset ids, zero
    base64 encode/decode on the output path, no usage warnings."""
    failures: list[str] = []
    images = _extract_images(result)
    if not images:
        failures.append("no image descriptors found in result")
    else:
        for img in images:
            if not isinstance(img, dict):
                continue
            asset_id = str(img.get("asset_id", "") or "")
            backend = str(img.get("backend_path", "") or "")
            if not asset_id and not backend:
                failures.append("image descriptor missing asset_id and backend_path")
            elif not asset_id:
                failures.append(f"image descriptor has empty asset_id ({backend[:60]})")
            elif len(asset_id) != 64:
                failures.append(f"asset_id is not a sha256 ({asset_id[:32]}...)")
    attempts = result.get("output_attempts", [])
    if isinstance(attempts, list):
        for attempt in attempts:
            if isinstance(attempt, dict) and (
                attempt.get("base64_encode_count", 0)
                or attempt.get("base64_decode_count", 0)
            ):
                failures.append("output path used base64 encode/decode")
    return failures


# ── Per-run total-wall stage metrics ───────────────────────────────────────
# The corrected waterfall makes sampler graph-join time and pre-Python Modal
# scheduling explicit stages.  These helpers flatten the waterfall stages into
# the required per-run metric names so the report can render the full
# attribution and the exact residual.

_STAGE_KEYS: tuple[str, ...] = (
    "local_preparation", "modal_handle_submission", "modal_scheduling",
    "application_restore", "restore_to_method_entry",
    "method_entry_to_unet_claim", "unet_claim_to_ready",
    "remote_method_setup", "prompt_executor_cache_setup",
    "first_node_to_clip", "clip_to_sampler_node",
    "sampler_graph_join_wait", "sampler_node_to_sampling",
    "sampling", "post_sampling_transition", "vae", "output_persistence",
    "remote_return_handoff", "remote_local_return",
)


def _waterfall_stage_duration(
    waterfall: dict[str, Any],
    key: str,
) -> float | None:
    for stage in waterfall.get("stages", []) if isinstance(waterfall, dict) else []:
        if isinstance(stage, dict) and stage.get("key") == key:
            value = stage.get("duration_ms")
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                return round(float(value), 3)
            return None
    return None


def _extract_total_wall_stages(artifact: dict[str, Any]) -> dict[str, Any]:
    """Extract the required per-run stage breakdown from the artifact.

    ``command_to_response_ms`` is the primary metric (local command
    submission → durable result returned locally).  The waterfall stages are
    the corrected explicit stages; the concurrent worker stages
    (method entry→claim, claim→ready) are reported but excluded from the
    accounted total.  ``total_accounted_ms`` / ``remaining_residual_ms`` come
    from the waterfall reconciliation.
    """
    timing = artifact.get("timing", {}) if isinstance(artifact.get("timing"), dict) else {}
    waterfall = artifact.get("waterfall", {})
    if not isinstance(waterfall, dict):
        waterfall = {}
    out: dict[str, Any] = {
        "command_to_response_ms": timing.get("command_to_response_ms"),
        "wall_ms": timing.get("wall_ms"),
    }
    for key in _STAGE_KEYS:
        out[f"stage_{key}_ms"] = _waterfall_stage_duration(waterfall, key)
    out["total_accounted_ms"] = waterfall.get("accounted_ms")
    out["remaining_residual_ms"] = waterfall.get("reconciliation_ms")
    out["waterfall_total_ms"] = waterfall.get("total_ms")
    out["waterfall_warnings"] = list(waterfall.get("warnings", []) or [])
    return out


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
    expect_cloud: str = "",
    expect_region: str = "",
    expect_lean: str = "",
    accept_under_ms: float = 13000.0,
    stop_after_bad: int = 0,
) -> dict[str, Any]:
    os.environ["COMFYMODAL_V2_APP_NAME"] = app_name
    prev_identity: dict[str, Any] | None = None
    records: list[dict[str, Any]] = []
    cold = 0
    _bad = 0
    # ── Container env assertion (BEFORE any measured run) ─────────────────
    # The deploy script is not proof: ``_runtime_env`` silently dropped new
    # gates once.  Probe the deployed container's effective environment and
    # abort when any gate value is wrong.
    env_probe: dict[str, Any] = {}
    env_failures: list[str] = []
    try:
        handle = await asyncio.to_thread(
            transport._v2_handle, workspace=workspace, gpu=GPU,
        )
        fn = getattr(handle, "run_env_probe", None)
        if fn is None:
            env_failures.append("deployed container has no run_env_probe method")
        else:
            remote = getattr(fn, "remote", None)
            if remote is not None and callable(getattr(remote, "aio", None)):
                probe = remote.aio(request_id="v2-env-probe")
                if asyncio.iscoroutine(probe):
                    probe = await probe
            elif asyncio.iscoroutinefunction(fn):
                probe = await fn(request_id="v2-env-probe")
            else:
                probe = await asyncio.to_thread(fn, request_id="v2-env-probe")
            if asyncio.iscoroutine(probe):
                probe = await probe
            if isinstance(probe, dict):
                env_probe = probe
                env_failures = _assert_container_env(
                    probe, app_name=app_name, gpu=GPU,
                    expect_cloud=expect_cloud, expect_region=expect_region,
                    expect_lean=expect_lean,
                )
            else:
                env_failures.append(
                    f"run_env_probe returned non-dict: {type(probe).__name__}"
                )
    except Exception as exc:  # noqa: BLE001
        env_failures.append(
            f"run_env_probe call failed: {type(exc).__name__}: {str(exc)[:300]}"
        )
    env_assert_record: dict[str, Any] = {
        "probe": env_probe,
        "failures": env_failures,
        "passed": not env_failures,
        "expected": dict(_EXPECTED_GATE_ENV),
        "expect_lean": expect_lean,
    }
    (output_dir / "container_env_assert.json").write_text(
        json.dumps(env_assert_record, default=str, indent=2), encoding="utf-8",
    )
    if env_failures:
        print("[v2.ownership] CONTAINER ENV ASSERTION FAILED:", flush=True)
        for _f in env_failures:
            print(f"  - {_f}", flush=True)
        raise RuntimeError(
            "ownership: container environment assertion failed; study aborted "
            "before any measured run (see container_env_assert.json)"
        )
    print(
        "[v2.ownership] container env assertion PASSED: "
        "exclusive-owner=1 rehome=off probes=off synth-h2d=off backing-verify=off "
        "pretouch=off quiesced=off variance=off host-diag=off full-trace=off "
        f"cloud={expect_cloud or 'unpinned'} region={expect_region or 'unpinned'} "
        "profile=production "
        f"cpu_request={env_probe.get('env', {}).get('COMFYMODAL_V2_CPU_REQUEST')} "
        f"memory_request={env_probe.get('env', {}).get('COMFYMODAL_V2_MEMORY_REQUEST')} "
        f"single_use={env_probe.get('env', {}).get('COMFYMODAL_V2_SINGLE_USE_CONTAINERS')} "
        f"min_containers={env_probe.get('min_containers')} "
        f"scaledown={env_probe.get('scaledown_window')} "
        f"single_use_spec={env_probe.get('single_use_containers_spec')}",
        flush=True,
    )

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
        artifact["output_correctness"] = _assert_output_correctness(result)
        artifact["page_path"] = _extract_page_path_probe(result)
        artifact["remote_entry_ts"] = _remote_entry_wall_iso(result)
        artifact["host_diagnostics"] = artifact.get("host_diagnostics", {})
        artifact["gpu_uuid"] = _host_gpu_uuid(artifact)
        artifact["total_wall_stages"] = _extract_total_wall_stages(artifact)
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
            "output_correctness": artifact["output_correctness"],
            "page_path": artifact["page_path"],
            "gpu_uuid": artifact["gpu_uuid"],
            "total_wall_stages": artifact["total_wall_stages"],
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
        # ── Invariant failures: stop IMMEDIATELY (duplicate migration,
        #    snapshot fallback, cancelled worker, sampler-absent-while-
        #    pending, output incorrect, graph join not ready).  Only runs
        #    that were actually exercised as cold candidates are gated;
        #    excluded snapshot-builders are not.
        if not artifact["excluded_snapshot_builder"]:
            _checks = artifact["ownership_checks"]
            _out_fail = artifact["output_correctness"]
            _invariant_failures: list[str] = []
            if not _checks["exactly_one_migration"]:
                _invariant_failures.append(
                    f"duplicate migration: worker_load_count="
                    f"{_checks.get('transfer_count', '?')}, "
                    f"expected exactly 1"
                )
            if _checks["suspected_duplicate_graph_load"]:
                _invariant_failures.append(
                    f"duplicate graph load: walls="
                    f"{_checks.get('graph_unet_load_wall_ms_list', [])}"
                )
            if not _checks["no_fallback"]:
                _invariant_failures.append(
                    f"snapshot/activation fallback: fallback_count="
                    f"{_checks['fallback_count']}"
                )
            if _checks["worker_cancelled"]:
                _invariant_failures.append("request-used worker ended cancelled")
            if not _checks["no_sampler_absent_while_pending"]:
                _invariant_failures.append(
                    f"sampler acquired with blocking_owner=absent while pending: "
                    f"{_checks['sampler_owner_absent_while_pending']}"
                )
            if not _checks["worker_terminal_ready"]:
                _invariant_failures.append(
                    f"worker terminal status not ready: "
                    f"{_checks.get('worker_terminal_status', '')}"
                )
            if not _checks["graph_join_ready"]:
                _invariant_failures.append(
                    f"graph join outcome not ready: "
                    f"{_checks.get('graph_join_outcomes', [])}"
                )
            if _out_fail:
                _invariant_failures.append(f"output incorrect: {_out_fail}")
            if _invariant_failures:
                _dump_crash_diagnostics(output_dir, artifact, "invariant_failure")
                summary = {
                    "mode": "ownership",
                    "app_name": app_name,
                    "phase": phase,
                    "target_cold": target_cold,
                    "max_attempts": max_attempts,
                    "skip_first": skip_first,
                    "gap_seconds": GAP_SECONDS,
                    "valid_cold": cold,
                    "aborted": True,
                    "abort_reason": "ownership_invariant_failure",
                    "invariant_failures": _invariant_failures,
                    "records": records,
                }
                (output_dir / "summary.json").write_text(
                    json.dumps({k: v for k, v in summary.items() if k != "records"}, default=str, indent=2),
                    encoding="utf-8",
                )
                raise RuntimeError(
                    f"ownership {phase}: ownership invariant failure at attempt "
                    f"{index}: {'; '.join(_invariant_failures)}; study stopped "
                    f"immediately; diagnosis in {output_dir / 'crash_diagnostics.json'}"
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
        # ── Early-stop gate: stop after ``stop_after_bad`` clearly failing
        #    VALID (non-excluded) cold runs for the same candidate (per the
        #    restore protocol: two consecutive misses on the same candidate
        #    mean the change is not worth more paid attempts).  Snapshot
        #    builders and their following request are excluded unconditionally
        #    and never count toward the gate.  Preserved attempts are never
        #    deleted.
        if (stop_after_bad > 0 and not artifact["excluded_snapshot_builder"]
                and artifact["classification"] == "cold"):
            _wall_v = artifact.get("total_wall_stages", {}).get("command_to_response_ms")
            if isinstance(_wall_v, (int, float)) and _wall_v >= accept_under_ms:
                _bad += 1
                if _bad >= stop_after_bad:
                    summary: dict[str, Any] = {
                        "mode": "ownership",
                        "app_name": app_name,
                        "phase": phase,
                        "target_cold": target_cold,
                        "max_attempts": max_attempts,
                        "skip_first": skip_first,
                        "gap_seconds": GAP_SECONDS,
                        "valid_cold": cold,
                        "accept_under_ms": accept_under_ms,
                        "stop_after_bad": stop_after_bad,
                        "aborted": True,
                        "abort_reason": f"early_stop:{_bad}_runs_over_{accept_under_ms:.0f}ms",
                        "records": records,
                    }
                    (output_dir / "summary.json").write_text(
                        json.dumps({k: v for k, v in summary.items() if k != "records"},
                                   default=str, indent=2),
                        encoding="utf-8",
                    )
                    print(
                        f"[v2.ownership] EARLY STOP: {_bad} valid-cold runs at or above "
                        f"{accept_under_ms:.0f} ms for the same candidate; attempts preserved",
                        flush=True,
                    )
                    return summary
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
        "accept_under_ms": accept_under_ms,
        "stop_after_bad": stop_after_bad,
        "expect_cloud": expect_cloud,
        "expect_region": expect_region,
        "expect_lean": expect_lean,
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


# ── Six-run total-wall report ──────────────────────────────────────────────

_STAGE_LABELS: tuple[tuple[str, str], ...] = (
    ("local_preparation", "local preparation"),
    ("modal_handle_submission", "modal handle and submission"),
    ("modal_scheduling", "command -> Python restore start (pre-Python Modal scheduling)"),
    ("application_restore", "restore"),
    ("restore_to_method_entry", "restore end -> method entry"),
    ("method_entry_to_unet_claim", "method entry -> UNET ownership claim (concurrent)"),
    ("unet_claim_to_ready", "UNET claim -> ready (worker load, concurrent)"),
    ("remote_method_setup", "remote method setup"),
    ("prompt_executor_cache_setup", "PromptExecutor/cache setup"),
    ("first_node_to_clip", "first node to CLIP"),
    ("clip_to_sampler_node", "CLIP to sampler node"),
    ("sampler_graph_join_wait", "sampler graph-join wait"),
    ("sampler_node_to_sampling", "sampler node to sampling"),
    ("sampling", "sampling"),
    ("post_sampling_transition", "post-sampling transition"),
    ("vae", "VAE"),
    ("output_persistence", "output persistence"),
    ("remote_return_handoff", "remote result handoff"),
    ("remote_local_return", "remote/local return"),
)


def _fmt_ms(value: Any) -> str:
    if value is None or value == "":
        return "-"
    try:
        return f"{float(value):,.1f}"
    except (TypeError, ValueError):
        return str(value)


def _num_stats(values: list[float | None]) -> dict[str, Any]:
    nums = sorted(float(v) for v in values if isinstance(v, (int, float)))
    if not nums:
        return {"count": 0, "min": None, "median": None, "p90": None, "max": None}
    n = len(nums)
    median = nums[n // 2] if n % 2 else (nums[n // 2 - 1] + nums[n // 2]) / 2.0
    p90 = nums[min(n - 1, int(n * 0.9))]
    return {
        "count": n,
        "min": round(nums[0], 1),
        "median": round(median, 1),
        "p90": round(p90, 1),
        "max": round(nums[-1], 1),
    }


def _render_total_wall_report(
    summary: dict[str, Any],
    *,
    output_dir: Path,
    commit_sha: str,
    files_changed: list[str],
) -> str:
    records = summary.get("records", []) or []
    valid = [r for r in records if r.get("cold") and not r.get("excluded_snapshot_builder")]
    accept_ms = float(summary.get("accept_under_ms", 13000.0) or 13000.0)
    expect_cloud = str(summary.get("expect_cloud", "") or "")
    expect_region = str(summary.get("expect_region", "") or "")
    expect_lean = str(summary.get("expect_lean", "") or "")
    _placement = (
        f"cloud={expect_cloud or 'unpinned'}"
        + (f", region={expect_region}" if expect_region else ", region unpinned")
    )
    _lines: list[str] = []
    if expect_lean == "1":
        _lines.append("# V2 Lean-Snapshot Direct Validation — Six-Run Report")
        _lines.append("")
        _lines.append("> Shadow deployment only. Lean production candidate: "
                      "`COMFYMODAL_V2_LEAN_SNAPSHOT=1` (UNET-backing diagnostic "
                      "deferred from the import-time surface), "
                      "`COMFYMODAL_V2_UNET_EXCLUSIVE_OWNER=1`, rehoming OFF, all "
                      "page-path/synthetic-H2D/backing-verify/pretouch/quiesced/"
                      "variance/host/manifest/full-trace diagnostics OFF, "
                      f"{_placement}, "
                      "single-use containers, minimal teardown.")
    else:
        _lines.append("# V2 Exclusive-Owner Total-Wall Validation — Six-Run Report")
        _lines.append("")
        _lines.append("> Shadow deployment only. Best-case production candidate: "
                      "`COMFYMODAL_V2_UNET_EXCLUSIVE_OWNER=1`, rehoming OFF, all "
                      "page-path/synthetic-H2D/backing-verify/pretouch/quiesced/"
                      "variance/host/full-trace diagnostics OFF, "
                      f"{_placement}, "
                      "single-use containers, minimal teardown.")
    _lines.append("")
    _lines.append("## Protocol")
    _lines.append("")
    _lines.append("- One clean shadow app deployed on `main`.")
    _lines.append("- Container env assertion (remote `run_env_probe`) before any measured run; "
                  "study aborts on any gate mismatch.")
    _lines.append("- Snapshot-build request and the immediately following request excluded.")
    _lines.append(f"- Target: **{summary.get('target_cold', 6)} valid cold single-use runs**; "
                  f"max {summary.get('max_attempts', 9)} post-deploy attempts; "
                  f"{summary.get('gap_seconds', 25)} s gaps.")
    _lines.append(f"- Acceptance gate: command → response **< {accept_ms:.0f} ms** on every run.")
    _lines.append("- Stop immediately on exit-139 / snapshot fallback / stream loss / "
                  "duplicate migration / incorrect output / ownership-invariant failure.")
    _lines.append("")
    _lines.append("## Container env assertion")
    _lines.append("")
    env_assert = {}
    try:
        env_assert = json.loads((output_dir / "container_env_assert.json").read_text(encoding="utf-8"))
    except Exception:
        env_assert = {}
    if env_assert.get("passed"):
        _lines.append("**PASSED** — every gate below was read from the deployed container "
                      "(`run_env_probe`), not assumed from the deploy script:")
        _lines.append("")
        _lines.append("| Gate | Effective (container) |")
        _lines.append("|---|---|")
        _env = (env_assert.get("probe") or {}).get("env") or {}
        for key in ("COMFYMODAL_V2_UNET_EXCLUSIVE_OWNER", "COMFYMODAL_V2_UNET_REHOME_AFTER_RESTORE",
                    "COMFYMODAL_V2_PAGE_PATH_PROBE", "COMFYMODAL_V2_SYNTH_H2D_PROBE",
                    "COMFYMODAL_V2_UNET_BACKING_VERIFY", "COMFYMODAL_V2_UNET_PRETOUCH",
                    "COMFYMODAL_V2_UNET_QUIESCED_TRANSFER", "COMFYMODAL_V2_VARIANCE_DIAGNOSTICS",
                    "COMFYMODAL_V2_HOST_DIAGNOSTICS", "COMFYMODAL_V2_FULL_TRACE",
                    "COMFYMODAL_V2_LEAN_SNAPSHOT", "COMFYMODAL_V2_SNAPSHOT_MANIFEST",
                    "COMFYMODAL_V2_CLOUD", "COMFYMODAL_V2_REGION"):
            _lines.append(f"| `{key}` | `{_env.get(key, '') or '(absent/empty)'}` |")
        _lines.append("")
        _lines.append(f"- min_containers=`{env_assert.get('probe', {}).get('min_containers')}`, "
                      f"scaledown_window=`{env_assert.get('probe', {}).get('scaledown_window')}`, "
                      f"single_use_containers=`{env_assert.get('probe', {}).get('single_use_containers_spec')}`")
    else:
        _lines.append("**FAILED** — " + "; ".join(env_assert.get("failures", ["probe unavailable"])))
        _lines.append("")
        _lines.append("The study was aborted before any measured run.")
    _lines.append("")
    _lines.append("## Every attempt (preserved)")
    _lines.append("")
    _lines.append("| attempt | class | cmd->resp (ms) | restore (ms) | join wait (ms) | worker term | join outcome | migrations | graph load wall (ms) | output |")
    _lines.append("|---|---|---:|---:|---:|---|---|---:|---:|---|")
    for r in sorted(records, key=lambda x: x.get("run_index", 0)):
        _checks = r.get("ownership_checks", {}) or {}
        _stages = r.get("total_wall_stages", {}) or {}
        _out = r.get("output_correctness", []) or []
        _tag = "SKIP" if r.get("excluded_snapshot_builder") else r.get("classification", "")
        _graph_walls = _checks.get("graph_unet_load_wall_ms_list") or []
        _lines.append(
            f"| {r.get('attempt_file', '')} | {_tag} "
            f"| {_fmt_ms(_stages.get('command_to_response_ms'))} "
            f"| {_fmt_ms(_stages.get('stage_application_restore_ms'))} "
            f"| {_fmt_ms(_stages.get('stage_sampler_graph_join_wait_ms'))} "
            f"| {_checks.get('worker_terminal_status', '-')} "
            f"| {','.join(_checks.get('graph_join_outcomes', []) or ['-'])} "
            f"| {_checks.get('transfer_count', '-')} "
            f"| {_fmt_ms(max(_graph_walls) if _graph_walls else None)} "
            f"| {'OK' if not _out else 'FAIL: ' + str(_out)} |"
        )
    _lines.append("")
    _lines.append("## Six-run distribution (valid cold runs)")
    _lines.append("")
    dist_keys = (
        ("command_to_response_ms", "command -> response (primary)"),
        ("stage_local_preparation_ms", "local preparation"),
        ("stage_modal_handle_submission_ms", "modal handle and submission"),
        ("stage_modal_scheduling_ms", "command -> Python restore start (pre-Python Modal scheduling)"),
        ("stage_application_restore_ms", "restore"),
        ("stage_restore_to_method_entry_ms", "restore end -> method entry"),
        ("stage_method_entry_to_unet_claim_ms", "method entry -> UNET ownership claim (concurrent)"),
        ("stage_unet_claim_to_ready_ms", "UNET claim -> ready (concurrent)"),
        ("stage_sampler_graph_join_wait_ms", "sampler graph-join wait"),
        ("stage_sampling_ms", "sampling"),
        ("stage_vae_ms", "VAE"),
        ("stage_output_persistence_ms", "output persistence"),
        ("total_accounted_ms", "total accounted"),
        ("remaining_residual_ms", "remaining residual"),
    )
    _lines.append("| metric | count | min | median | p90 | max |")
    _lines.append("|---|---:|---:|---:|---:|---:|")
    for key, label in dist_keys:
        stats = _num_stats([r.get("total_wall_stages", {}).get(key) for r in valid])
        if stats["count"] == 0:
            _lines.append(f"| {label} | 0 | - | - | - | - |")
            continue
        _lines.append(
            f"| {label} | {stats['count']} | {stats['min']} | {stats['median']} "
            f"| {stats['p90']} | {stats['max']} |"
        )
    _lines.append("")
    _lines.append("## Stage attribution per valid run (ms)")
    _lines.append("")
    _lines.append("| attempt | " + " | ".join(
        _label for _key, _label in _STAGE_LABELS) + " | total | residual |")
    _lines.append("|" + "---|" * (len(_STAGE_LABELS) + 3))
    for r in sorted(valid, key=lambda x: x.get("run_index", 0)):
        _stages = r.get("total_wall_stages", {}) or {}
        _cells = [_fmt_ms(_stages.get(f"stage_{key}_ms")) for key, _label in _STAGE_LABELS]
        _lines.append(
            f"| {r.get('attempt_file', '')} | " + " | ".join(_cells)
            + f" | {_fmt_ms(_stages.get('total_accounted_ms'))} "
            + f"| {_fmt_ms(_stages.get('remaining_residual_ms'))} |"
        )
    _lines.append("")
    _lines.append("## Per-run acceptance checks (valid cold runs)")
    _lines.append("")
    _lines.append(f"| attempt | <{accept_ms:.0f} ms | 1 migration | worker ready | join ready | "
                  "cache-only graph load | no fallback | no sampler-absent-pending | "
                  "no cancelled worker | output correct | residual <=100 ms |")
    _lines.append("|---|---|---|---|---|---|---|---|---|---|---|")
    for r in sorted(valid, key=lambda x: x.get("run_index", 0)):
        _stages = r.get("total_wall_stages", {}) or {}
        _checks = r.get("ownership_checks", {}) or {}
        _out = r.get("output_correctness", []) or []
        _wall = _stages.get("command_to_response_ms")
        _under_13 = bool(isinstance(_wall, (int, float)) and _wall < accept_ms)
        _residual = _stages.get("remaining_residual_ms")
        _residual_ok = bool(
            isinstance(_residual, (int, float)) and abs(_residual) <= 100
        )
        _lines.append(
            f"| {r.get('attempt_file', '')} | {'Y' if _under_13 else 'N'} "
            f"| {'Y' if _checks.get('exactly_one_migration') else 'N'} "
            f"| {'Y' if _checks.get('worker_terminal_ready') else 'N'} "
            f"| {'Y' if _checks.get('graph_join_ready') else 'N'} "
            f"| {'Y' if _checks.get('graph_load_cache_only') else 'N'} "
            f"| {'Y' if _checks.get('no_fallback') else 'N'} "
            f"| {'Y' if _checks.get('no_sampler_absent_while_pending') else 'N'} "
            f"| {'Y' if _checks.get('no_request_used_worker_cancelled') else 'N'} "
            f"| {'Y' if not _out else 'N'} "
            f"| {'Y' if _residual_ok else 'N'} |"
        )
    _lines.append("")
    _lines.append("## Pass / fail conclusion")
    _lines.append("")
    _primary = [r.get("total_wall_stages", {}).get("command_to_response_ms") for r in valid]
    _primary = [float(v) for v in _primary if isinstance(v, (int, float))]
    _all_under_13 = bool(_primary and all(v < accept_ms for v in _primary))
    _no_crash = not summary.get("aborted") or summary.get("abort_reason") in (None, "")
    _enough = len(valid) >= summary.get("target_cold", 6)
    _failures: list[str] = []
    if not _enough:
        _failures.append(f"only {len(valid)}/{summary.get('target_cold', 6)} valid cold runs")
    if not _all_under_13:
        _failures.append(
            f"command->response >= {accept_ms:.0f} ms on "
            f"{sum(1 for v in _primary if v >= accept_ms)} run(s)"
        )
    if not _no_crash:
        _failures.append(f"aborted: {summary.get('abort_reason')}")
    for r in valid:
        _checks = r.get("ownership_checks", {}) or {}
        _out = r.get("output_correctness", []) or []
        _residual = r.get("total_wall_stages", {}).get("remaining_residual_ms")
        if not _checks.get("exactly_one_migration"):
            _failures.append(f"{r.get('attempt_file')}: duplicate migration")
        if not _checks.get("worker_terminal_ready"):
            _failures.append(f"{r.get('attempt_file')}: worker terminal not ready")
        if not _checks.get("graph_join_ready"):
            _failures.append(f"{r.get('attempt_file')}: graph join not ready")
        if not _checks.get("no_fallback"):
            _failures.append(f"{r.get('attempt_file')}: snapshot fallback")
        if not _checks.get("no_sampler_absent_while_pending"):
            _failures.append(f"{r.get('attempt_file')}: sampler absent while pending")
        if not _checks.get("no_request_used_worker_cancelled"):
            _failures.append(f"{r.get('attempt_file')}: cancelled request-used worker")
        if not _checks.get("graph_load_cache_only"):
            _failures.append(f"{r.get('attempt_file')}: graph load not cache-only")
        if _out:
            _failures.append(f"{r.get('attempt_file')}: output incorrect ({_out})")
        if isinstance(_residual, (int, float)) and abs(_residual) > 100:
            _failures.append(f"{r.get('attempt_file')}: residual {_residual:.1f} ms > 100 ms")
    _pass = not _failures and _enough and _all_under_13
    _lines.append(f"- Valid cold runs collected: **{len(valid)}** / {summary.get('target_cold', 6)}")
    if _primary:
        _lines.append(f"- command->response distribution: min {min(_primary):.1f} ms, "
                      f"median {sorted(_primary)[len(_primary)//2]:.1f} ms, "
                      f"max {max(_primary):.1f} ms; all < {accept_ms:.0f} ms: "
                      f"{'yes' if _all_under_13 else 'no'}")
    if _failures:
        _lines.append("- Failures:")
        for _f in _failures:
            _lines.append(f"  - {_f}")
    _lines.append("")
    if _pass:
        _lines.append(f"**PASS** — the current best production candidate delivers "
                      f"command submission -> durable response under {accept_ms:.1f} ms "
                      "on every run, "
                      "with zero crashes, zero snapshot fallbacks, zero duplicate "
                      "migrations, and zero unexplained residual above 100 ms.")
    else:
        _lines.append("**FAIL** — see the failures above and the stage attribution to "
                      "identify the exact remaining stage.")
    _lines.append("")
    _lines.append("## Files changed")
    _lines.append("")
    if files_changed:
        for _f in files_changed:
            _lines.append(f"- `{_f}`")
    else:
        _lines.append("- (none)")
    _lines.append("")
    _lines.append(f"Final commit SHA: `{commit_sha}`")
    _lines.append("")
    return "\n".join(_lines)


def _git_sha() -> str:
    try:
        import subprocess
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True, cwd=str(ROOT),
        )
        return out.stdout.strip() or "unknown"
    except Exception:
        return "unknown"


def _write_total_wall_report(
    summary: dict[str, Any],
    *,
    output_dir: Path,
    report_name: str = "V2_EXCLUSIVE_OWNER_TOTAL_WALL_6_RUN_REPORT.md",
) -> Path:
    try:
        import subprocess
        out = subprocess.run(
            ["git", "diff", "--name-only", "HEAD"], capture_output=True, text=True, cwd=str(ROOT),
        )
        changed = [ln for ln in out.stdout.splitlines() if ln.strip()]
    except Exception:
        changed = []
    report_md = _render_total_wall_report(
        summary,
        output_dir=output_dir,
        commit_sha=_git_sha(),
        files_changed=changed,
    )
    report_path = ROOT / report_name
    report_path.write_text(report_md, encoding="utf-8")
    print(f"[v2.total_wall] report={report_path}", flush=True)
    return report_path


def _rebuild_summary_from_attempts(output_dir: Path) -> dict[str, Any]:
    """Rebuild an ownership-study summary from preserved attempt artifacts.

    Used by the offline report renderer so the final report can be
    regenerated after the code commit with the correct final SHA and
    files-changed list (attempt files never change after the run).
    """
    records: list[dict[str, Any]] = []
    for f in sorted(output_dir.glob("attempt_*.json")):
        try:
            artifact = json.loads(f.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            records.append({
                "run_index": len(records),
                "attempt_file": f.name,
                "classification": "invalid",
                "cold": False,
                "cold_valid": False,
                "excluded_snapshot_builder": True,
                "error": f"unreadable: {exc}",
                "identity": {},
                "timing": {},
                "ownership_checks": {},
                "ownership_evidence": {},
                "output_correctness": [],
                "page_path": None,
                "gpu_uuid": "",
                "total_wall_stages": {},
            })
            continue
        variance = artifact.get("variance", {}) if isinstance(artifact.get("variance"), dict) else {}
        records.append({
            "run_index": artifact.get("run_index"),
            "attempt_file": artifact.get("attempt_file", f.name),
            "phase": artifact.get("phase", ""),
            "classification": artifact.get("classification", ""),
            "cold_valid": bool(variance.get("cold_valid")),
            "cold": bool(variance.get("cold")),
            "excluded_snapshot_builder": bool(artifact.get("excluded_snapshot_builder")),
            "error": artifact.get("error", ""),
            "identity": artifact.get("identity", {}) or {},
            "timing": artifact.get("timing", {}) or {},
            "ownership_checks": artifact.get("ownership_checks", {}) or {},
            "ownership_evidence": artifact.get("ownership_evidence", {}) or {},
            "output_correctness": artifact.get("output_correctness", []) or [],
            "page_path": artifact.get("page_path"),
            "gpu_uuid": artifact.get("gpu_uuid", ""),
            "total_wall_stages": artifact.get("total_wall_stages", {}) or {},
        })
    valid_cold = sum(
        1 for r in records if r.get("cold") and not r.get("excluded_snapshot_builder")
    )
    return {
        "mode": "ownership",
        "app_name": os.environ.get("COMFYMODAL_V2_APP_NAME", ""),
        "phase": records[0].get("phase", "") if records else "",
        "target_cold": valid_cold,
        "max_attempts": len(records),
        "skip_first": sum(1 for r in records if r.get("excluded_snapshot_builder")),
        "gap_seconds": GAP_SECONDS,
        "valid_cold": valid_cold,
        "accept_under_ms": float(os.environ.get("V2_OWNERSHIP_ACCEPT_UNDER_MS", "13000") or 13000),
        "expect_cloud": os.environ.get("V2_OWNERSHIP_EXPECT_CLOUD", ""),
        "expect_region": os.environ.get("V2_OWNERSHIP_EXPECT_REGION", ""),
        "expect_lean": os.environ.get("V2_OWNERSHIP_EXPECT_LEAN", ""),
        "aborted": False,
        "records": records,
    }


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


async def _run_snapshot_ab_study(
    workspace: dict[str, Any],
    transport: ModalTransport,
    output_dir: Path,
    *,
    app_name: str,
    arm: str,
    runs: int,
    max_attempts: int,
    skip_first: int,
    expect_cloud: str = "",
    expect_region: str = "",
    expect_lean: str = "",
    expect_manifest: str = "",
) -> dict[str, Any]:
    """Same-image snapshot-composition A/B: entry-probe timing per arm.

    Calls the immediate-return ``run_entry_probe`` method N times and
    measures ``submission → first Python line`` (the same wall-clock
    boundary as the historical pre-Python metric) with no graph execution.
    The snapshot builder and the immediately following request are
    excluded, mirroring the restore-study protocol.
    """
    os.environ["COMFYMODAL_V2_APP_NAME"] = app_name
    handle = await asyncio.to_thread(
        transport._v2_handle, workspace=workspace, gpu=GPU,
    )
    # ── Container env assertion (same machinery as the ownership study) ──
    env_probe: dict[str, Any] = {}
    env_failures: list[str] = []
    try:
        fn = getattr(handle, "run_env_probe", None)
        if fn is None:
            env_failures.append("deployed container has no run_env_probe method")
        else:
            remote = getattr(fn, "remote", None)
            if remote is not None and callable(getattr(remote, "aio", None)):
                probe = remote.aio(request_id="v2-env-probe")
                if asyncio.iscoroutine(probe):
                    probe = await probe
            elif asyncio.iscoroutinefunction(fn):
                probe = await fn(request_id="v2-env-probe")
            else:
                probe = await asyncio.to_thread(fn, request_id="v2-env-probe")
            if asyncio.iscoroutine(probe):
                probe = await probe
            if isinstance(probe, dict):
                env_probe = probe
                env_failures = _assert_container_env(
                    probe, app_name=app_name, gpu=GPU,
                    expect_cloud=expect_cloud, expect_region=expect_region,
                )
            else:
                env_failures.append(
                    f"run_env_probe returned non-dict: {type(probe).__name__}"
                )
    except Exception as exc:  # noqa: BLE001
        env_failures.append(
            f"run_env_probe call failed: {type(exc).__name__}: {str(exc)[:300]}"
        )
    # Arm-specific gates: lean snapshot composition + manifest capture must
    # match the arm that was deployed.
    env = env_probe.get("env") or {}
    for key, expected in (
        ("COMFYMODAL_V2_LEAN_SNAPSHOT", expect_lean),
        ("COMFYMODAL_V2_SNAPSHOT_MANIFEST", expect_manifest),
    ):
        actual = str(env.get(key, "") or "")
        if expected == "0" and actual not in ("", "0", "false", "no", "off"):
            env_failures.append(f"{key}: expected OFF, container has {actual!r}")
        elif expected == "1" and actual not in ("1", "true", "yes", "on"):
            env_failures.append(f"{key}: expected ON, container has {actual!r}")
    if env_failures:
        print(
            f"[v2.snapshot_ab] arm={arm} CONTAINER ENV ASSERTION FAILED:", flush=True,
        )
        for _f in env_failures:
            print(f"  - {_f}", flush=True)
        raise RuntimeError(
            f"snapshot-ab: arm {arm} container env assertion failed "
            "(see container_env_assert.json)"
        )
    print(
        f"[v2.snapshot_ab] arm={arm} env assertion PASSED "
        f"lean={expect_lean or '0'} manifest={expect_manifest or '0'} "
        f"cloud={expect_cloud or 'unpinned'} region={expect_region or 'unpinned'}",
        flush=True,
    )
    (output_dir / f"container_env_assert_{arm}.json").write_text(
        json.dumps({"probe": env_probe, "failures": env_failures, "arm": arm},
                   default=str, indent=2), encoding="utf-8",
    )

    records: list[dict[str, Any]] = []
    valid = 0
    for index in range(max_attempts):
        _run_id = f"snapshot_ab_{arm}_{index}-{uuid.uuid4().hex[:8]}"
        _req_id = f"v2-snapab-{arm}-{index}-{uuid.uuid4().hex[:12]}"
        _start_ts = datetime.now(timezone.utc).isoformat()
        _t0_wall = time.time_ns()
        _t0_perf = time.perf_counter()
        artifact: dict[str, Any] = {
            "run_index": index, "run_id": _run_id, "request_id": _req_id,
            "arm": arm, "start_ts": _start_ts, "mode": "snapshot_ab",
        }
        try:
            fn = handle.run_entry_probe
            remote = getattr(fn, "remote", None)
            if remote is not None and callable(getattr(remote, "aio", None)):
                result = remote.aio(request_id=_req_id)
                if asyncio.iscoroutine(result):
                    result = await result
            elif asyncio.iscoroutinefunction(fn):
                result = await fn(request_id=_req_id)
            else:
                result = await asyncio.to_thread(fn, request_id=_req_id)
            if asyncio.iscoroutine(result):
                result = await result
            artifact["result"] = result if isinstance(result, dict) else {"raw": str(result)[:300]}
        except Exception as exc:  # noqa: BLE001
            artifact["error"] = f"remote call failed: {type(exc).__name__}: {str(exc)[:300]}"
            artifact["result"] = {}
        _res = artifact.get("result") or {}
        _entry_wall = _res.get("entry_wall_unix_ns")
        if isinstance(_entry_wall, (int, float)) and _entry_wall:
            artifact["submission_to_entry_wall_ms"] = round(
                max(0, int(_entry_wall) - _t0_wall) / 1_000_000.0, 3
            )
        else:
            artifact["submission_to_entry_wall_ms"] = None
        artifact["round_trip_wall_ms"] = round((time.perf_counter() - _t0_perf) * 1000.0, 1)
        artifact["end_ts"] = datetime.now(timezone.utc).isoformat()
        artifact["excluded_snapshot_builder"] = index == 0
        artifact["excluded_after_builder"] = index == 1
        artifact["image_id"] = _res.get("image_id", "")
        artifact["cloud"] = _res.get("cloud", "")
        artifact["region"] = _res.get("region", "")
        artifact["container_session_id"] = _res.get("container_session_id", "")
        artifact["valid_entry_probe"] = bool(
            not artifact.get("error")
            and artifact.get("submission_to_entry_wall_ms") is not None
            and not artifact["excluded_snapshot_builder"]
            and not artifact["excluded_after_builder"]
        )
        if artifact["valid_entry_probe"]:
            valid += 1
        artifact_path = output_dir / f"attempt_{index:04d}_{arm}.json"
        artifact_path.write_text(
            json.dumps(artifact, default=str, indent=2), encoding="utf-8",
        )
        records.append(artifact)
        print(
            f"[v2.snapshot_ab] arm={arm} index={index} "
            f"excluded={int(artifact['excluded_snapshot_builder'] or artifact['excluded_after_builder'])} "
            f"valid={int(artifact['valid_entry_probe'])} "
            f"submit_to_entry_ms={artifact['submission_to_entry_wall_ms']} "
            f"image={artifact['image_id']} cloud={artifact['cloud']} region={artifact['region']}",
            flush=True,
        )
        if valid >= runs:
            break
        if index < max_attempts - 1:
            print(
                f"[v2.snapshot_ab] arm={arm} sleeping {GAP_SECONDS}s before next probe",
                flush=True,
            )
            await asyncio.sleep(GAP_SECONDS)
    vals = sorted(
        a["submission_to_entry_wall_ms"] for a in records if a["valid_entry_probe"]
    )
    summary: dict[str, Any] = {
        "arm": arm,
        "runs_requested": runs,
        "valid_entry_probes": valid,
        "submission_to_entry_ms": {
            "min": vals[0] if vals else None,
            "median": vals[len(vals) // 2] if vals else None,
            "max": vals[-1] if vals else None,
        },
        "records": len(records),
    }
    (output_dir / f"summary_{arm}.json").write_text(
        json.dumps(summary, default=str, indent=2), encoding="utf-8",
    )
    print(f"[v2.snapshot_ab] arm={arm} summary={json.dumps(summary, default=str)}", flush=True)
    return summary


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
    expect_cloud: str = "",
    expect_region: str = "",
    accept_under_ms: float = 13000.0,
    stop_after_bad: int = 0,
) -> dict[str, Any]:
    return await _run_ownership_study(
        workflow, modal_options, workspace, transport, output_dir,
        app_name=app_name, phase="integrated", target_cold=target_cold,
        max_attempts=max_attempts, skip_first=skip_first,
        expect_cloud=expect_cloud, expect_region=expect_region,
        accept_under_ms=accept_under_ms, stop_after_bad=stop_after_bad,
    )


# ── CLI ───────────────────────────────────────────────────────────────────


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=["ownership", "rehoming", "integrated", "snapshot-ab", "render-report"])
    parser.add_argument("--app", required=True)
    parser.add_argument("--phase", default="probes_on",
                        choices=["probes_on", "probes_off"])
    parser.add_argument("--target-cold", type=int, default=4)
    parser.add_argument("--max-attempts", type=int, default=12)
    parser.add_argument("--skip-first", type=int, default=2)
    parser.add_argument("--runs", type=int, default=4)
    parser.add_argument("--arm", default="",
                        help="snapshot-ab arm label (current|lean) for artifact naming")
    parser.add_argument("--expect-lean", default="",
                        help="Expected COMFYMODAL_V2_LEAN_SNAPSHOT (1 or 0) in the "
                             "deployed container for the lean candidate")
    parser.add_argument("--expect-manifest", default="",
                        help="snapshot-ab: expected COMFYMODAL_V2_SNAPSHOT_MANIFEST (1 or 0)")
    parser.add_argument("--report", action="store_true",
                        help="Write V2_EXCLUSIVE_OWNER_TOTAL_WALL_6_RUN_REPORT.md "
                             "after the ownership/integrated study")
    parser.add_argument("--output-dir", default="",
                        help="Artifacts directory for render-report mode")
    parser.add_argument("--expect-cloud", default="",
                        help="Expected COMFYMODAL_V2_CLOUD in the deployed container "
                             "(e.g. gcp/aws) for controlled restore-mode phases; "
                             "default unpinned")
    parser.add_argument("--expect-region", default="",
                        help="Expected COMFYMODAL_V2_REGION in the deployed container "
                             "for controlled restore-mode phases; default unpinned")
    parser.add_argument("--accept-under-ms", type=float, default=13000.0,
                        help="Total-wall acceptance gate in ms (default 13000)")
    parser.add_argument("--stop-after-bad", type=int, default=0,
                        help="Stop early after N valid-cold runs at or above the "
                             "acceptance gate (0 = disabled)")
    parser.add_argument("--report-name", default="",
                        help="Report file name for --report / render-report "
                             "(default V2_EXCLUSIVE_OWNER_TOTAL_WALL_6_RUN_REPORT.md)")
    args = parser.parse_args()

    if args.mode == "render-report":
        if not args.output_dir:
            print("render-report requires --output-dir <artifacts dir>")
            sys.exit(1)
        output_dir = Path(args.output_dir)
        summary = _rebuild_summary_from_attempts(output_dir)
        _write_total_wall_report(
            summary, output_dir=output_dir,
            report_name=args.report_name or "V2_EXCLUSIVE_OWNER_TOTAL_WALL_6_RUN_REPORT.md",
        )
        print(f"[v2.total_wall] offline render done; valid_cold={summary['valid_cold']}", flush=True)
        return

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
    elif args.mode == "snapshot-ab":
        summary = await _run_snapshot_ab_study(
            workspace, transport, output_dir,
            app_name=args.app, arm=args.arm or "arm",
            runs=args.runs, max_attempts=args.max_attempts,
            skip_first=args.skip_first,
            expect_cloud=args.expect_cloud, expect_region=args.expect_region,
            expect_lean=args.expect_lean, expect_manifest=args.expect_manifest,
        )
    elif args.mode == "integrated":
        summary = await _run_integrated_study(
            workflow, modal_options, workspace, transport, output_dir,
            app_name=args.app,
            target_cold=args.target_cold, max_attempts=args.max_attempts,
            skip_first=args.skip_first,
            expect_cloud=args.expect_cloud, expect_region=args.expect_region,
            accept_under_ms=args.accept_under_ms,
            stop_after_bad=args.stop_after_bad,
        )
        if args.report:
            _write_total_wall_report(
                summary, output_dir=output_dir,
                report_name=args.report_name or "V2_EXCLUSIVE_OWNER_TOTAL_WALL_6_RUN_REPORT.md",
            )
    else:
        summary = await _run_ownership_study(
            workflow, modal_options, workspace, transport, output_dir,
            app_name=args.app, phase=args.phase,
            target_cold=args.target_cold, max_attempts=args.max_attempts,
            skip_first=args.skip_first,
            expect_cloud=args.expect_cloud, expect_region=args.expect_region,
            expect_lean=args.expect_lean,
            accept_under_ms=args.accept_under_ms,
            stop_after_bad=args.stop_after_bad,
        )
        if args.report:
            _write_total_wall_report(
                summary, output_dir=output_dir,
                report_name=args.report_name or "V2_EXCLUSIVE_OWNER_TOTAL_WALL_6_RUN_REPORT.md",
            )
    print(f"[v2.ownership_rehoming] output_dir={output_dir}", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
