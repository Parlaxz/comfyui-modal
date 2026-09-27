"""Run the GPU-snapshot compatibility gates for comfyui-modal V2.

Deploys the isolated shadow app (``comfymodal_runtime.gpu_snapshot_shadow``)
and runs Gate 1 (minimal CUDA canary) then Gate 3 (full-stack UNET + CLIP +
VAE GPU snapshot + one real workflow), strictly ONE paid attempt at a time.

Before deploy the runner provisions ``latest_benchmark_workflow.json`` onto
the ``comfymodal-runtime-config`` volume (as ``gpu_snapshot_workflow.json``)
so the snapshot build can pre-run dependency preflight, graph validation and
CacheDiT preparation with the exact benchmark topology.

Stop conditions (task):
  1. minimal CUDA GPU snapshot itself is incompatible -> stop, diagnose
  2. minimal works but full-stack UNET/CLIP/VAE snapshot/restore incompatible
     -> stop
  3. models restore but cannot execute correctly -> stop with failing stage
  4. full-stack GPU snapshot restores and completes a correct real workflow
     -> run ONE additional restored attempt with a DIFFERENT prompt and seed
     (same model stack) to prove the snapshot is reusable model/runtime
     state rather than baked prompt-specific execution state.

Usage:
    python tools/run_gpu_snapshot_gates.py [--deploy-only] [--gate 1|2]
                                           [--app APP_NAME] [--no-deploy]
    python tools/run_gpu_snapshot_gates.py --runs N   # N restored attempts,
        banner-based timing (scheduling excluded, restore included)
"""

from __future__ import annotations

import asyncio
import datetime
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

SHADOW_APP_DEFAULT = "stable-modal-comfy-v2-gpu-snapshot-shadow"
RUNTIME_CONFIG_VOLUME = "comfymodal-runtime-config"
SHADOW_WORKFLOW_REMOTE = "gpu_snapshot_workflow.json"

# Set by --evict on the command line: propagates
# COMFYMODAL_V2_EVICT_MODELS_BEFORE_SNAPSHOT=1 to the deployed app (CPU
# eviction flag).  On the GPU shadow build this is expected to be a no-op
# (no CpuSnapshotModels container exists); the build emits
# ``gpu_snapshot_evict_flag`` evidence per capture.
_EVICT_GPU_FLAG = False


def _load_workspace() -> dict[str, Any]:
    ws_path = ROOT / ".modal_workspaces.json"
    ws = json.loads(ws_path.read_text(encoding="utf-8"))
    aid = ws.get("active_workspace_id")
    entry = next((w for w in ws.get("workspaces", []) if w.get("id") == aid), None)
    if not entry or not entry.get("token_id") or not entry.get("token_secret"):
        raise RuntimeError("could not load active Modal workspace credentials")
    return entry


def _provision_workflow() -> None:
    """Upload the benchmark workflow to the runtime-config volume so the
    snapshot build can pre-run request-independent preparation with the exact
    benchmark topology.  Failure is non-fatal (the snapshot degrades to
    request-time preflight/validation, which still works)."""
    local = ROOT / "latest_benchmark_workflow.json"
    if not local.is_file():
        print("=== WARNING: latest_benchmark_workflow.json missing; snapshot "
              "will not prebuild preflight/validation state ===", flush=True)
        return
    try:
        import modal as _m
        client = _m.Client.from_credentials(ws["token_id"], ws["token_secret"])
        vol = _m.Volume.from_name(RUNTIME_CONFIG_VOLUME, create_if_missing=True, client=client)
        batch = getattr(vol, "batch_upload", None)
        if batch is None:
            print("=== WARNING: modal.Volume.batch_upload unavailable; skipping "
                  "workflow provisioning ===", flush=True)
            return
        with batch(force=True) as upload:
            upload.put_file(str(local), SHADOW_WORKFLOW_REMOTE)
        print(f"=== Provisioned {SHADOW_WORKFLOW_REMOTE} on {RUNTIME_CONFIG_VOLUME} ===", flush=True)
    except Exception as exc:  # noqa: BLE001
        print(f"=== WARNING: workflow provisioning failed ({exc}); snapshot "
              "will not prebuild preflight/validation state ===", flush=True)


def _build_prompt_variant_workflow(workflow: dict[str, Any]) -> dict[str, Any]:
    """Return a copy of *workflow* with a DIFFERENT prompt and seed (same
    model stack), for the prompt-dynamic second restored attempt.

    The benchmark workflow routes prompt text through node 1497
    (``PrimitiveStringMultiline``, input key ``value``) into the positive
    CLIPTextEncode, and the seed is a direct input of the sampler node 1242
    (``ClownsharKSampler_Beta``).  Only those values change; the model stack
    (UNETLoader / CLIPLoader / VAELoader) is untouched so the bridge
    identities still match the snapshot.
    """
    out = json.loads(json.dumps(workflow))
    _new_prompt = (
        "A serene mountain lake at dawn, mist rising off the water, "
        "snow-capped peaks reflecting in the still surface, a small wooden "
        "pier reaching into the lake with an old rowboat tied to it, "
        "soft golden morning light breaking through scattered clouds, "
        "lush pine forest lining the shoreline, ultra-detailed "
        "photorealistic landscape, crisp reflections, gentle color grading."
    )
    _new_seed = 987654321012345
    changed = {"prompt_node": "", "seed_node": ""}
    for nid, spec in out.items():
        if not isinstance(spec, dict):
            continue
        inputs = spec.get("inputs", {})
        if not isinstance(inputs, dict):
            continue
        if spec.get("class_type") == "PrimitiveStringMultiline" and isinstance(inputs.get("value"), str):
            inputs["value"] = _new_prompt
            changed["prompt_node"] = str(nid)
        elif spec.get("class_type") == "ClownsharKSampler_Beta" and isinstance(inputs.get("seed"), int):
            inputs["seed"] = _new_seed
            changed["seed_node"] = str(nid)
    print(f"=== prompt variant built: {changed} ===", flush=True)
    return out


def _base_env(app_name: str) -> dict[str, str]:
    env = dict(os.environ)
    env.update({
        "MODAL_TOKEN_ID": str(ws["token_id"]),
        "MODAL_TOKEN_SECRET": str(ws["token_secret"]),
        "COMFYMODAL_V2_APP_NAME": app_name,
        "COMFYMODAL_V2_GPU": "rtx-pro-6000",
        "COMFYMODAL_V2_ENV_PROFILE": "production",
        "COMFYMODAL_V2_CPU_REQUEST": "16",
        "COMFYMODAL_V2_MEMORY_REQUEST": "49152",
        "COMFYMODAL_V2_MEMORY_MB": "49152",
        "COMFYMODAL_V2_SINGLE_USE_CONTAINERS": "1",
        "COMFYMODAL_ENABLE_GPU_SNAPSHOT": "1",
        # Boring test: all heavy diagnostics OFF.
        "COMFYMODAL_V2_FULL_TRACE": "0",
        "COMFYMODAL_V2_RESIDENCY_DIAGNOSTICS": "0",
        "COMFYMODAL_V2_DEEP_MODEL_DIAG": "0",
        "COMFYMODAL_V2_PAGEFAULT_TRACKING": "0",
        "COMFYMODAL_V2_EVICT_MODELS_BEFORE_SNAPSHOT": "1" if _EVICT_GPU_FLAG else "0",
        "COMFYMODAL_V2_PREFILL_LANES": "critical",
        "COMFYMODAL_V2_CPU_MODEL_SNAPSHOT": "0",
        "COMFYMODAL_V2_VAE_SNAPSHOT": "0",
        "COMFYMODAL_V2_UNET_EXCLUSIVE_OWNER": "0",
        "COMFYMODAL_V2_UNET_REHOME_AFTER_RESTORE": "0",
        "COMFYMODAL_V2_PAGE_PATH_PROBE": "0",
        "COMFYMODAL_V2_SYNTH_H2D_PROBE": "0",
        "COMFYMODAL_V2_UNET_BACKING_VERIFY": "0",
        "COMFYMODAL_V2_ANON_UNET_SNAPSHOT": "0",
        "COMFYMODAL_V2_VARIANCE_DIAGNOSTICS": "0",
        "COMFYMODAL_V2_HOST_DIAGNOSTICS": "0",
        "COMFYMODAL_V2_TORCH_COMPILE": "0",
        "COMFYMODAL_ENABLE_TORCH_COMPILE": "0",
        "PYTHONIOENCODING": "utf-8",
        "PYTHONUTF8": "1",
    })
    return env


def _with_warmup_profile(env: dict[str, str]) -> dict[str, str]:
    prof = subprocess.run(
        [sys.executable, str(ROOT / "tools" / "extract_warmup_profile.py")],
        capture_output=True, text=True, cwd=str(ROOT),
    )
    if prof.returncode != 0:
        raise RuntimeError(f"warmup profile derivation failed: {prof.stderr}")
    for line in prof.stdout.splitlines():
        if "=" in line:
            k, _, v = line.partition("=")
            env[k.strip()] = v.strip()
    return env


def deploy(app_name: str, env: dict[str, str]) -> None:
    print(f"=== Deploying {app_name} ===", flush=True)
    _provision_workflow()
    run = subprocess.run(
        ["modal", "deploy", "-m", "comfymodal_runtime.gpu_snapshot_shadow"],
        cwd=str(ROOT), env=env, text=True,
    )
    if run.returncode != 0:
        print(f"=== ERROR: deploy of {app_name} failed ===")
        sys.exit(run.returncode)
    print(f"=== Deploy verified OK: {app_name} ===", flush=True)


def _handle(app_name: str, class_name: str) -> Any:
    import modal
    client = modal.Client.from_credentials(ws["token_id"], ws["token_secret"])
    return modal.Cls.from_name(app_name, class_name, client=client)()


def _logs_env() -> dict[str, str]:
    """Env for Modal CLI subprocesses: workspace creds + UTF-8 (the rich log
    output contains emoji that crashes the Windows cp1252 console codec)."""
    env = dict(os.environ)
    if "ws" in globals():
        env.update({
            "MODAL_TOKEN_ID": str(ws["token_id"]),
            "MODAL_TOKEN_SECRET": str(ws["token_secret"]),
        })
    env.setdefault("PYTHONIOENCODING", "utf-8")
    env.setdefault("PYTHONUTF8", "1")
    return env


def _fetch_logs_tail(app_name: str, lines: int = 200) -> str:
    """Fetch recent Modal logs for crash marker diagnosis (workspace creds)."""
    try:
        run = subprocess.run(
            ["modal", "app", "logs", app_name, "--tail", str(lines)],
            cwd=str(ROOT), capture_output=True, text=True, timeout=60,
            env=_logs_env(), encoding="utf-8", errors="replace",
        )
        text = (run.stdout or "") + (run.stderr or "")
    except Exception as exc:  # noqa: BLE001
        return f"<log fetch failed: {exc}>"
    return "\n".join(text.splitlines()[-lines:])


def _parse_log_timestamp(line: str) -> float | None:
    """Extract the ``--timestamps`` prefix (ISO-local seconds) as epoch ms."""
    import datetime
    import re
    m = re.match(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}(?:[+-]\d{2}:\d{2})?)\s+", line)
    if not m:
        return None
    try:
        dt = datetime.datetime.fromisoformat(m.group(1))
        if dt.tzinfo is None:
            dt = dt.astimezone()
        return dt.timestamp() * 1000.0
    except Exception:  # noqa: BLE001
        return None


async def _fetch_banner_timing(app_name: str, request_id: str) -> dict[str, Any] | None:
    """Fetch the app logs and extract THIS request's restore boundaries.

    Uses the Modal client API (``modal._logs.tail_logs``) for millisecond
    precision and anchors on the request's own
    ``gpu_snapshot_request_method_entry request_id=...`` line so attempts
    can never be cross-matched (the previous last-occurrence heuristic
    produced garbage when a just-finished run's final markers had not yet
    been ingested).

    Returns epoch-ms timestamps (log-server side):
      banner        — Modal "Restoring Function from memory snapshot."
      first_line    — ``gpu_snapshot_post_restore_enter``
      method_entry  — the request's ``gpu_snapshot_request_method_entry``
      gen_complete  — the next ``gpu_snapshot_generation_complete``
    Retries briefly to absorb log-ingestion lag; None on persistent failure.
    """
    import modal as _m
    from modal.cli.app import resolve_app_identifier
    from modal._logs import tail_logs
    from modal.client import _Client
    client = await _Client.from_credentials(ws["token_id"], ws["token_secret"])
    app_id, _, _ = await resolve_app_identifier(app_name, None, client)
    anchor = f"request_method_entry request_id={request_id}"
    for _attempt in range(6):
        entries: list[tuple[float, str]] = []
        try:
            async for batch in tail_logs(client, app_id, 4000):
                for item in batch.items:
                    ts = getattr(item, "timestamp", None)
                    if ts is None:
                        continue
                    raw = getattr(item, "data", b"")
                    if isinstance(raw, str):
                        text = raw
                    else:
                        text = (raw or b"").decode("utf-8", "replace")
                    entries.append((float(ts) * 1000.0, text))
        except Exception as exc:  # noqa: BLE001
            print(f"=== banner timing fetch error: {exc} ===", flush=True)
            return None
        if not entries:
            await asyncio.sleep(2.0)
            continue
        idx = next((i for i, (_t, l) in enumerate(entries) if anchor in l), None)
        gi = None
        if idx is not None:
            gi = next((i for i in range(idx + 1, len(entries))
                       if "gpu_snapshot_generation_complete" in entries[i][1]), None)
        if idx is None or gi is None:
            await asyncio.sleep(2.0)
            continue
        fi = max((i for i in range(idx) if "gpu_snapshot_post_restore_enter" in entries[i][1]),
                 default=None)
        bi = None
        if fi is not None:
            bi = max((i for i in range(fi)
                      if "Restoring Function from memory snapshot." in entries[i][1]),
                     default=None)
        if fi is None or bi is None:
            await asyncio.sleep(2.0)
            continue
        return {
            "banner_epoch_ms": entries[bi][0],
            "first_line_epoch_ms": entries[fi][0],
            "method_entry_epoch_ms": entries[idx][0],
            "gen_complete_epoch_ms": entries[gi][0],
        }
    print("=== banner timing: could not pair request markers after retries ===", flush=True)
    return None


def _markers_from(evidence: dict[str, Any]) -> list[dict[str, Any]]:
    markers = evidence.get("markers") or []
    return [m for m in markers if isinstance(m, dict)]


def _last_marker(evidence: dict[str, Any]) -> str:
    markers = _markers_from(evidence)
    return str(markers[-1].get("marker", "")) if markers else "<none>"


def _marker_names(evidence: dict[str, Any]) -> list[str]:
    return [str(m.get("marker", "")) for m in _markers_from(evidence)]


def _marker_wall_ns(evidence: dict[str, Any], marker: str) -> int | None:
    for m in _markers_from(evidence):
        if m.get("marker") == marker:
            try:
                return int(m.get("wall_unix_ns", 0)) or None
            except (TypeError, ValueError):
                return None
    return None


def _print_waterfall_presence(result: dict[str, Any]) -> None:
    """Print a concise waterfall presence/total/reconciliation line.

    The full waterfall dict is kept in the returned artifacts (and the giant
    ``result_summary`` line excludes it to stay readable); this is the compact
    log footprint of the attached direct-path report.
    """
    wf = result.get("waterfall")
    if not isinstance(wf, dict):
        print("waterfall=absent", flush=True)
        return
    total = wf.get("total_ms")
    rec = wf.get("reconciliation_ms")
    print(
        f"waterfall=present stages={len(wf.get('stages', []) or [])} "
        f"total_ms={total if total is not None else '-'} "
        f"reconciliation_ms={rec if rec is not None else '-'}",
        flush=True,
    )


def _timing_summary(evidence: dict[str, Any], restore_marker: str) -> dict[str, Any]:
    """Compute restore-banner->python-first-line and restore->done deltas.

    ``submit_wall_unix_ns`` (the local runner's submission wall clock) to the
    restored container's FIRST Python line is the closest cross-process
    proxy for Modal's restore banner -> Python first line (it includes Modal
    scheduling + restore + process resume).  The delta from the restore first
    line to the terminal marker is measured entirely inside the container.
    """
    submit = evidence.get("submit_wall_unix_ns") or 0
    entry = evidence.get("entry_wall_unix_ns") or 0
    restore_ns = _marker_wall_ns(evidence, restore_marker)
    method_ns = _marker_wall_ns(evidence, "gpu_snapshot_request_method_entry")
    terminal_ns = _marker_wall_ns(evidence, "gpu_snapshot_generation_complete") or _marker_wall_ns(
        evidence, "canary_complete"
    )
    out: dict[str, Any] = {}
    if submit and restore_ns:
        out["submission_to_restore_python_first_line_ms"] = round((restore_ns - submit) / 1_000_000, 1)
    if submit and entry:
        out["submission_to_method_entry_ms"] = round((entry - submit) / 1_000_000, 1)
    if restore_ns and terminal_ns:
        out["restore_first_line_to_terminal_ms"] = round((terminal_ns - restore_ns) / 1_000_000, 1)
    if method_ns and terminal_ns:
        # In-container span from the request method entry (post-restore
        # setup complete) through generation complete — the shadow-side
        # "placement-excluded" proxy (platform restore time not included).
        out["method_entry_to_generation_complete_ms"] = round((terminal_ns - method_ns) / 1_000_000, 1)
    if method_ns and restore_ns:
        out["python_post_restore_setup_ms"] = round((method_ns - restore_ns) / 1_000_000, 1)
    return out


async def _invoke_remote(fn: Any, **kwargs: Any) -> Any:
    """Invoke a Modal method handle.  Prefer the async ``.aio`` entry; fall
    back to the sync ``.remote`` run in a thread (Modal 1.4 patterns)."""
    aio = getattr(fn, "aio", None)
    if callable(aio):
        result = aio(**kwargs)
        if asyncio.iscoroutine(result):
            return await result
    remote = getattr(fn, "remote", None)
    if remote is None:
        raise RuntimeError(f"method handle has no .remote/.aio: {fn}")
    return await asyncio.to_thread(remote, **kwargs)


async def run_gate1(app_name: str, attempts: int = 3) -> dict[str, Any]:
    """Gate 1: minimal CUDA canary.  Attempt 1 builds the snapshot; the next
    cold attempt is the restored one.  Returns classification."""
    print("=" * 70, flush=True)
    print("GATE 1 — minimal CUDA GPU-snapshot canary", flush=True)
    print("=" * 70, flush=True)
    handle = _handle(app_name, "GpuSnapshotCanary")
    fn = getattr(handle, "run_canary", None)
    if fn is None:
        raise RuntimeError("deployed canary has no run_canary method")
    gate: dict[str, Any] = {"attempts": [], "conclusion": "inconclusive"}
    for i in range(attempts):
        req_id = f"gpu-snap-gate1-{i:02d}-{uuid4hex()}"
        submit_ns = int(time.time() * 1_000_000_000)
        print(f"\n--- Gate 1 attempt {i + 1} (request {req_id}) ---", flush=True)
        t0 = time.perf_counter()
        try:
            ev = await _invoke_remote(fn, request_id=req_id, submit_wall_unix_ns=submit_ns)
        except Exception as exc:  # noqa: BLE001
            wall_ms = (time.perf_counter() - t0) * 1000.0
            print(f"ATTEMPT {i + 1} FAILED: {type(exc).__name__}: {str(exc)[:400]}", flush=True)
            gate["attempts"].append({
                "index": i, "status": "error", "error": f"{type(exc).__name__}: {str(exc)[:300]}",
                "wall_ms": round(wall_ms, 1),
            })
            logs = _fetch_logs_tail(app_name)
            gate["logs_tail"] = logs
            gate["conclusion"] = classify_gate1_crash(gate, logs)
            break
        wall_ms = (time.perf_counter() - t0) * 1000.0
        phase = str(ev.get("phase", "unknown"))
        markers = _marker_names(ev)
        verify = ev.get("verification", {}) or {}
        print(f"phase={phase} last_marker={_last_marker(ev)}", flush=True)
        print(f"markers={markers}", flush=True)
        print(f"verification={json.dumps(verify, default=str)}", flush=True)
        print(f"versions={json.dumps(ev.get('versions', {}), default=str)}", flush=True)
        if ev.get("build_state"):
            print(f"canary_build_state={json.dumps(ev['build_state'], default=str)}", flush=True)
        if ev.get("restore_state"):
            print(f"canary_restore_state={json.dumps(ev['restore_state'], default=str)}", flush=True)
        timing = _timing_summary(ev, "gpu_snapshot_restore_python_enter")
        if timing:
            print(f"timing={json.dumps(timing, default=str)}", flush=True)
        gate["attempts"].append({
            "index": i, "status": "ok", "phase": phase,
            "markers": markers, "last_marker": _last_marker(ev),
            "verification": verify,
            "versions": ev.get("versions", {}),
            "build_state": ev.get("build_state", {}),
            "restore_state": ev.get("restore_state", {}),
            "entry_wall_unix_ns": ev.get("entry_wall_unix_ns"),
            "submit_wall_unix_ns": ev.get("submit_wall_unix_ns"),
            "timing": timing,
            "wall_ms": round(wall_ms, 1),
        })
        if phase == "restore":
            ok = bool(verify.get("tensor_sum_matches"))
            gate["conclusion"] = "PASS" if ok else "FAIL_RESTORE_VERIFY"
            gate["restore_ok"] = ok
            print(f"\nGATE 1 {'PASSED' if ok else 'FAILED'} (restored canary)", flush=True)
            break
        # build attempt (snapshot creation) — keep going for the restored one
        gate["snapshot_created"] = phase == "build"
    if gate["conclusion"] == "inconclusive":
        gate["conclusion"] = "NO_RESTORED_ATTEMPT"
    return gate


def classify_gate1_crash(gate: dict[str, Any], logs: str) -> str:
    """Classify a Gate 1 crash from markers found in the logs."""
    last = ""
    for line in logs.splitlines():
        if "[gpu_snapshot]" in line:
            parts = line.split("]", 1)[-1].strip().split()
            if parts:
                last = parts[0]
    if not last:
        return "CRASH_NO_MARKERS"
    if last in ("gpu_snapshot_enter_start", "cuda_initialized", "canary_tensor_created",
                "cuda_sync_before_snapshot_complete"):
        return "CRASH_SNAPSHOT_BUILD_WORKLOAD"
    if last == "gpu_snapshot_enter_returning":
        return "CRASH_CHECKPOINT_RESTORE"
    if last in ("gpu_snapshot_restore_python_enter", "canary_tensor_verified",
                "post_restore_cuda_operation_verified"):
        return "CRASH_RESTORED_CUDA_STATE"
    return f"CRASH_OTHER_LAST_MARKER={last}"


async def run_gate2(app_name: str, attempts: int = 3, workflow: dict | None = None,
                    modal_options: dict | None = None) -> dict[str, Any]:
    """Gate 3: full-stack (UNET+CLIP+VAE) GPU snapshot + one real workflow."""
    print("=" * 70, flush=True)
    print("GATE 3 — full-stack UNET+CLIP+VAE GPU snapshot + real workflow", flush=True)
    print("=" * 70, flush=True)
    wf = workflow
    opts = modal_options
    if wf is None:
        wf_json = json.loads((ROOT / "latest_benchmark_workflow.json").read_text(encoding="utf-8"))
        wf = wf_json.get("payload", {}).get("prompt", {})
        opts = wf_json.get("payload", {}).get("modal_options", {}) or {}
    if not wf:
        raise RuntimeError("latest_benchmark_workflow.json has no payload.prompt")
    handle = _handle(app_name, "GpuSnapshotUnetShadow")
    fn = getattr(handle, "run_gpu_snapshot_workflow", None)
    if fn is None:
        raise RuntimeError("deployed shadow has no run_gpu_snapshot_workflow method")
    gate: dict[str, Any] = {"attempts": [], "conclusion": "inconclusive"}
    for i in range(attempts):
        req_id = f"gpu-snap-gate2-{i:02d}-{uuid4hex()}"
        submit_ns = int(time.time() * 1_000_000_000)
        print(f"\n--- Gate 2 attempt {i + 1} (request {req_id}) ---", flush=True)
        t0 = time.perf_counter()
        try:
            ev = await _invoke_remote(
                fn,
                workflow=wf, modal_options=opts,
                request_id=req_id, submit_wall_unix_ns=submit_ns,
            )
        except Exception as exc:  # noqa: BLE001
            wall_ms = (time.perf_counter() - t0) * 1000.0
            print(f"ATTEMPT {i + 1} FAILED: {type(exc).__name__}: {str(exc)[:400]}", flush=True)
            gate["attempts"].append({
                "index": i, "status": "error", "error": f"{type(exc).__name__}: {str(exc)[:300]}",
                "wall_ms": round(wall_ms, 1),
            })
            logs = _fetch_logs_tail(app_name)
            gate["logs_tail"] = logs
            gate["conclusion"] = classify_gate2_crash(gate, logs)
            break
        wall_ms = (time.perf_counter() - t0) * 1000.0
        phase = str(ev.get("phase", "unknown"))
        markers = _marker_names(ev)
        result = ev.get("result", {}) or {}
        verify = ev.get("verification", {}) or {}
        print(f"phase={phase} last_marker={_last_marker(ev)}", flush=True)
        print(f"markers={markers}", flush=True)
        print(f"verification={json.dumps(verify, default=str)}", flush=True)
        timing = _timing_summary(ev, "gpu_snapshot_post_restore_enter")
        if timing:
            print(f"timing={json.dumps(timing, default=str)}", flush=True)
        _print_waterfall_presence(result)
        print(f"result_summary={json.dumps({k: v for k, v in result.items() if k not in ('image_verification', 'stage_timing', 'file_rereads', 'waterfall')}, default=str)}", flush=True)
        if result.get("image_verification"):
            print(f"image_verification={json.dumps(result['image_verification'], default=str)}", flush=True)
        if result.get("file_rereads"):
            print(f"file_rereads={json.dumps(result['file_rereads'], default=str)}", flush=True)
        if result.get("stage_timing"):
            print(f"stage_timing={json.dumps(result['stage_timing'], default=str)}", flush=True)
        gate["attempts"].append({
            "index": i, "status": "ok", "phase": phase,
            "markers": markers, "last_marker": _last_marker(ev),
            "verification": verify,
            "result": result,
            "entry_wall_unix_ns": ev.get("entry_wall_unix_ns"),
            "submit_wall_unix_ns": ev.get("submit_wall_unix_ns"),
            "timing": timing,
            "wall_ms": round(wall_ms, 1),
        })
        if phase == "restore":
            ok = bool(
                verify.get("unet_already_cuda_resident")
                and verify.get("clip_already_cuda_resident")
                and verify.get("vae_already_cuda_resident")
                and result.get("images_count", 0) > 0
                and (result.get("image_verification") or {}).get("valid_png")
                and not result.get("unet_transferred_h2d")
                and not result.get("clip_transferred_h2d")
                and not result.get("vae_transferred_h2d")
                and result.get("file_rereads", {}).get("unet", {}).get("reads", 1) == 0
                and result.get("file_rereads", {}).get("clip", {}).get("reads", 1) == 0
                and result.get("file_rereads", {}).get("vae", {}).get("reads", 1) == 0
                and not result.get("error")
            )
            gate["conclusion"] = "PASS" if ok else "FAIL_RESTORE_WORKFLOW"
            gate["restore_ok"] = ok
            print(f"\nGATE 3 {'PASSED' if ok else 'FAILED'} (restored workflow)", flush=True)
            break
        gate["snapshot_created"] = phase == "build"
    if gate["conclusion"] == "inconclusive":
        gate["conclusion"] = "NO_RESTORED_ATTEMPT"
    return gate


async def run_gate2_prompt_variant(app_name: str) -> dict[str, Any]:
    """ONE restored attempt with a DIFFERENT prompt and seed (same model
    stack): proves the snapshot is reusable model/runtime state rather than
    baked prompt-specific execution state."""
    print("=" * 70, flush=True)
    print("PROMPT VARIANT — different prompt+seed, same model stack", flush=True)
    print("=" * 70, flush=True)
    wf_json = json.loads((ROOT / "latest_benchmark_workflow.json").read_text(encoding="utf-8"))
    wf = _build_prompt_variant_workflow(wf_json.get("payload", {}).get("prompt", {}))
    modal_options = wf_json.get("payload", {}).get("modal_options", {}) or {}
    return await run_gate2(app_name, attempts=2, workflow=wf, modal_options=modal_options)


async def run_gate2_repeats(app_name: str, n_runs: int = 5) -> dict[str, Any]:
    """N consecutive restored attempts on the SAME deployed snapshot.

    Every invocation is a fresh cold container; the first invocation
    rebuilds the snapshot after a deploy, the remaining ones restore from it.
    Per run, the Modal restore banner timestamp is parsed from the live app
    logs so scheduling time (submission -> banner) can be EXCLUDED while the
    platform restore time (banner -> first Python line) is INCLUDED in the
    primary metric:

      placement_excluded_total = banner -> generation complete
      restore_platform         = banner -> first Python line
      python_post_restore      = first line -> generation complete

    All boundaries use log-server timestamps from the same stream (no
    cross-clock skew); container wall markers are reported alongside.
    """
    print("=" * 70, flush=True)
    print(f"REPEAT EXPERIMENT — {n_runs} restored attempts, banner-based timing", flush=True)
    print("=" * 70, flush=True)
    wf_json = json.loads((ROOT / "latest_benchmark_workflow.json").read_text(encoding="utf-8"))
    wf = wf_json.get("payload", {}).get("prompt", {})
    modal_options = wf_json.get("payload", {}).get("modal_options", {}) or {}
    handle = _handle(app_name, "GpuSnapshotUnetShadow")
    fn = getattr(handle, "run_gpu_snapshot_workflow", None)
    if fn is None:
        raise RuntimeError("deployed shadow has no run_gpu_snapshot_workflow method")
    runs: list[dict[str, Any]] = []
    for i in range(n_runs):
        req_id = f"gpu-snap-repeat-{i:02d}-{uuid4hex()}"
        submit_ns = int(time.time() * 1_000_000_000)
        print(f"\n--- Repeat run {i + 1}/{n_runs} (request {req_id}) ---", flush=True)
        t0 = time.perf_counter()
        try:
            ev = await _invoke_remote(
                fn, workflow=wf, modal_options=modal_options,
                request_id=req_id, submit_wall_unix_ns=submit_ns,
            )
        except Exception as exc:  # noqa: BLE001
            wall_ms = (time.perf_counter() - t0) * 1000.0
            print(f"RUN {i + 1} FAILED: {type(exc).__name__}: {str(exc)[:400]}", flush=True)
            runs.append({"index": i, "status": "error", "error": f"{type(exc).__name__}: {str(exc)[:300]}",
                         "wall_ms": round(wall_ms, 1)})
            break
        wall_ms = (time.perf_counter() - t0) * 1000.0
        phase = str(ev.get("phase", "unknown"))
        result = ev.get("result", {}) or {}
        verify = ev.get("verification", {}) or {}
        markers = _marker_names(ev)
        ok = bool(
            phase == "restore"
            and verify.get("unet_already_cuda_resident")
            and verify.get("clip_already_cuda_resident")
            and verify.get("vae_already_cuda_resident")
            and result.get("images_count", 0) > 0
            and (result.get("image_verification") or {}).get("valid_png")
            and not result.get("unet_transferred_h2d")
            and not result.get("clip_transferred_h2d")
            and not result.get("vae_transferred_h2d")
            and result.get("file_rereads", {}).get("unet", {}).get("reads", 1) == 0
            and result.get("file_rereads", {}).get("clip", {}).get("reads", 1) == 0
            and result.get("file_rereads", {}).get("vae", {}).get("reads", 1) == 0
            and not result.get("error")
        )
        banner = await _fetch_banner_timing(app_name, req_id)
        timing: dict[str, Any] = {"ok": ok}
        if banner:
            b = float(banner["banner_epoch_ms"])
            f = float(banner["first_line_epoch_ms"])
            m = float(banner["method_entry_epoch_ms"])
            g = float(banner["gen_complete_epoch_ms"])
            timing["scheduling_submit_to_banner_ms"] = round(b - submit_ns / 1_000_000, 1)
            timing["placement_excluded_total_ms"] = round(g - b, 1)
            timing["restore_platform_banner_to_python_ms"] = round(f - b, 1)
            timing["post_restore_setup_ms"] = round(m - f, 1)
            timing["python_post_restore_ms"] = round(g - f, 1)
        else:
            timing["banner_parse"] = "unavailable"
        container = _timing_summary(ev, "gpu_snapshot_post_restore_enter")
        timing["container_proxy"] = container
        timing["stage_timing"] = result.get("stage_timing", [])
        boundaries = ev.get("boundaries") or {}
        print(f"phase={phase} ok={int(ok)} last_marker={_last_marker(ev)}", flush=True)
        print(f"banner_timing={json.dumps(timing, default=str)}", flush=True)
        for _bname in ("gpu_snapshot_final_pre_capture",
                       "gpu_snapshot_first_python_after_restore",
                       "gpu_snapshot_post_restore_verified"):
            _b = boundaries.get(_bname) or {}
            if _b:
                _pm = _b.get("process_memory", {}) or {}
                _cu = _b.get("cuda_memory", {}) or {}
                _cpu_st = _b.get("cpu_storage", {}) or {}
                _cuda_st = _b.get("cuda_storage", {}) or {}
                print(f"boundary {_bname} cgroup_mib={_pm.get('cgroup_current_mib')} "
                      f"cuda_alloc_mib={_cu.get('allocated_mib')} "
                      f"cuda_resv_mib={_cu.get('reserved_mib')} "
                      f"cpu_model_bytes={_cpu_st.get('total_unique_model_bytes')} "
                      f"cuda_model_bytes={_cuda_st.get('total_unique_model_bytes')} "
                      f"cpu_snap_models={_b.get('cpu_snapshot_models_present')}",
                      flush=True)
        _print_waterfall_presence(result)
        print(f"result_summary={json.dumps({k: v for k, v in result.items() if k in ('images_count', 'generation_wall_ms', 'file_rereads_total', 'unet_transferred_h2d', 'clip_transferred_h2d', 'vae_transferred_h2d')}, default=str)}", flush=True)
        runs.append({
            "index": i, "status": "ok", "phase": phase, "ok": ok,
            "markers": markers, "last_marker": _last_marker(ev),
            "verification": verify, "result": result,
            "boundaries": boundaries,
            "banner_timing": timing, "wall_ms": round(wall_ms, 1),
        })
    # ── Aggregate the banner-based primary metric over successful runs ──
    agg: dict[str, Any] = {"runs": len(runs), "successful": sum(1 for r in runs if r.get("ok"))}
    for key in ("placement_excluded_total_ms", "restore_platform_banner_to_python_ms",
                "python_post_restore_ms", "scheduling_submit_to_banner_ms"):
        vals = [float(r["banner_timing"][key]) for r in runs
                if r.get("ok") and r.get("banner_timing", {}).get(key) is not None]
        if vals:
            vals_sorted = sorted(vals)
            agg[key] = {
                "min_ms": round(vals_sorted[0], 1),
                "median_ms": round(vals_sorted[len(vals_sorted) // 2], 1),
                "mean_ms": round(sum(vals) / len(vals), 1),
                "max_ms": round(vals_sorted[-1], 1),
                "samples": len(vals),
            }
    print("\n=== REPEAT EXPERIMENT AGGREGATE (banner-based) ===", flush=True)
    print(json.dumps(agg, indent=2), flush=True)
    return {"runs": runs, "aggregate": agg,
            "conclusion": "PASS" if agg.get("successful") == n_runs else "PARTIAL"}


def _workflow_run_ok(phase: str, verify: dict[str, Any], result: dict[str, Any]) -> bool:
    """True when a restored E2E workflow run is fully valid: restore phase,
    all three models CUDA-resident, valid PNG, zero H2D, zero rereads, no
    error."""
    return bool(
        phase == "restore"
        and verify.get("unet_already_cuda_resident")
        and verify.get("clip_already_cuda_resident")
        and verify.get("vae_already_cuda_resident")
        and result.get("images_count", 0) > 0
        and (result.get("image_verification") or {}).get("valid_png")
        and not result.get("unet_transferred_h2d")
        and not result.get("clip_transferred_h2d")
        and not result.get("vae_transferred_h2d")
        and result.get("file_rereads", {}).get("unet", {}).get("reads", 1) == 0
        and result.get("file_rereads", {}).get("clip", {}).get("reads", 1) == 0
        and result.get("file_rereads", {}).get("vae", {}).get("reads", 1) == 0
        and not result.get("error")
    )


def _capture_id_of(evidence: dict[str, Any]) -> int | None:
    """Derive the capture identity retained in the snapshot: the wall
    timestamp of the build's final-pre-capture boundary.  Modal exposes no
    snapshot ID; this value is unique per capture and identical for every
    restore served from that exact capture."""
    try:
        fc = (evidence.get("boundaries") or {}).get("gpu_snapshot_final_pre_capture") or {}
        raw = fc.get("capture_wall_unix_ns") or 0
        return int(raw) or None
    except Exception:  # noqa: BLE001
        return None


async def run_capture_bucket_deployment(
    app_name: str, max_invocations: int, gap_seconds: float,
) -> dict[str, Any]:
    """One fresh deployment; up to *max_invocations* true E2E restores,
    bucketed by the actual capture each restore served from.

    Modal churns multiple snapshot variants on unpinned deployments (a new
    capture appears every ~1-3 min), so a single deployment cannot
    guarantee 5 restores from one capture.  Buckets are never mixed; the
    population is not terminated on variant change — the runs are grouped
    by their retained capture identity instead.
    """
    wf_json = json.loads((ROOT / "latest_benchmark_workflow.json").read_text(encoding="utf-8"))
    wf = wf_json.get("payload", {}).get("prompt", {})
    modal_options = wf_json.get("payload", {}).get("modal_options", {}) or {}
    handle = _handle(app_name, "GpuSnapshotUnetShadow")
    fn = getattr(handle, "run_gpu_snapshot_workflow", None)
    if fn is None:
        raise RuntimeError("deployed shadow has no run_gpu_snapshot_workflow method")
    runs: list[dict[str, Any]] = []
    recaptures: list[str] = []
    for i in range(1, max_invocations + 1):
        req_id = f"gpu-cap-bucket-{uuid4hex()}-{i:02d}"
        submit_ns = int(time.time() * 1_000_000_000)
        print(f"\n--- bucket-deployment invocation {i}/{max_invocations} "
              f"(request {req_id}) ---", flush=True)
        t0 = time.perf_counter()
        try:
            ev = await _invoke_remote(
                fn, workflow=wf, modal_options=modal_options,
                request_id=req_id, submit_wall_unix_ns=submit_ns,
            )
        except Exception as exc:  # noqa: BLE001
            print(f"INVOCATION {i} FAILED: {type(exc).__name__}: {str(exc)[:300]}", flush=True)
            continue
        phase = str(ev.get("phase", "unknown"))
        this_capture_id = _capture_id_of(ev)
        if phase == "build":
            recaptures.append(str(this_capture_id))
            print(f"=== invocation {i} was a BUILD (capture {this_capture_id}); "
                  f"not a restore, not counted ===", flush=True)
            continue
        verify = ev.get("verification", {}) or {}
        result = ev.get("result", {}) or {}
        ok = _workflow_run_ok(phase, verify, result)
        banner = await _fetch_banner_timing(app_name, req_id)
        timing: dict[str, Any] = {"ok": ok}
        if banner:
            b = float(banner["banner_epoch_ms"])
            f = float(banner["first_line_epoch_ms"])
            m = float(banner["method_entry_epoch_ms"])
            g = float(banner["gen_complete_epoch_ms"])
            timing["scheduling_submit_to_banner_ms"] = round(b - submit_ns / 1_000_000, 1)
            timing["placement_excluded_total_ms"] = round(g - b, 1)
            timing["restore_platform_banner_to_python_ms"] = round(f - b, 1)
            timing["post_restore_setup_ms"] = round(m - f, 1)
            timing["python_post_restore_ms"] = round(g - f, 1)
        else:
            timing["banner_parse"] = "unavailable"
        timing["container_proxy"] = _timing_summary(ev, "gpu_snapshot_post_restore_enter")
        fp = verify.get("worker_fingerprint") or {}
        img_sha = ((result.get("image_verification") or {}).get("sha256") or [""])[0]
        record = {
            "index": i, "request_id": req_id, "phase": phase, "ok": ok,
            "capture_id": this_capture_id,
            "modal_task_id": str(fp.get("modal_task_id", "")),
            "modal_region": str(fp.get("modal_region", "")),
            "image_id": str(fp.get("modal_image_id", "")),
            "gpu_uuid": str((fp.get("gpu") or {}).get("gpu_uuid", "")),
            "timing": timing,
            "wall_ms": round((time.perf_counter() - t0) * 1000.0, 1),
            "image_sha256": img_sha,
            "images_count": result.get("images_count", 0),
            "generation_wall_ms": result.get("generation_wall_ms"),
            "verification": verify,
            "result": result,
            "boundaries": ev.get("boundaries") or {},
        }
        print(f"phase={phase} ok={int(ok)} capture_id={this_capture_id}", flush=True)
        print(f"timing={json.dumps(timing, default=str)}", flush=True)
        _print_waterfall_presence(result)
        runs.append(record)
        if gap_seconds > 0:
            await asyncio.sleep(gap_seconds)
    buckets: dict[str, list[dict[str, Any]]] = {}
    for r in runs:
        buckets.setdefault(str(r.get("capture_id") or "unknown"), []).append(r)
    return {
        "runs": runs,
        "buckets": buckets,
        "recaptures": recaptures,
        "first_capture_id": str(runs[0].get("capture_id")) if runs else "",
    }


def _bucket_verdict(bucket: list[dict[str, Any]]) -> str:
    return _population_verdict({"runs": bucket})


async def run_capture_buckets(
    n_deployments: int, app_name: str, env: dict[str, str],
    gap_seconds: float, max_invocations: int = 6,
) -> dict[str, Any]:
    """N fresh deployments (fresh capture per deploy), each with up to
    *max_invocations* true E2E restores, bucketed by the actual capture
    each restore served from.  Captures are never mixed; no population
    termination — Modal's unpinned variant churn is recorded and grouped."""
    print("=" * 70, flush=True)
    print(f"CAPTURE BUCKETS — {n_deployments} fresh deployments x up to "
          f"{max_invocations} true E2E restores, AWS-wide unpinned", flush=True)
    print("=" * 70, flush=True)
    deployments: list[dict[str, Any]] = []
    for d in range(1, n_deployments + 1):
        print(f"\n######## DEPLOYMENT {d}/{n_deployments} ########", flush=True)
        _deploy_ok = False
        for _d_attempt in range(3):
            try:
                deploy(app_name, env)
                _deploy_ok = True
                break
            except SystemExit:
                print(f"=== deploy attempt {_d_attempt + 1} failed (build-context "
                      f"conflict?); retrying ===", flush=True)
                time.sleep(20)
        if not _deploy_ok:
            print(f"=== DEPLOYMENT {d} ABORTED: deploy failed 3x ===", flush=True)
            continue
        dep = await run_capture_bucket_deployment(app_name, max_invocations, gap_seconds)
        deployments.append(dep)
        print(f"\n=== deployment {d}: {len(dep['runs'])} restores, "
              f"{len(dep['buckets'])} capture variants, "
              f"{len(dep['recaptures'])} build invocations ===", flush=True)
    # ── Report ──
    print("\n" + "=" * 70, flush=True)
    print("CAPTURE-VARIANT x RESTORE REPORT (restore_platform banner->Python, s)", flush=True)
    print("=" * 70, flush=True)
    rows: list[dict[str, Any]] = []
    for dep in deployments:
        for cid, bucket in dep["buckets"].items():
            vals = [float(r["timing"]["restore_platform_banner_to_python_ms"])
                    for r in bucket if r.get("ok")
                    and r.get("timing", {}).get("restore_platform_banner_to_python_ms")]
            if not vals:
                continue
            s = sorted(vals)
            rows.append({
                "capture_id": cid,
                "n": len(vals),
                "times_ms": vals,
                "median_ms": round(s[len(s) // 2], 1),
                "max_ms": round(s[-1], 1),
                "min_ms": round(s[0], 1),
                "verdict": _bucket_verdict(bucket),
            })
    print(f"{'Capture':<14} {'n':>2} {'R values (s)':<36} {'Median':>7} {'Max':>7}  Verdict", flush=True)
    for row in sorted(rows, key=lambda r: -r["n"]):
        vals_s = " ".join(f"{v/1000.0:.1f}" for v in row["times_ms"])
        print(f"{row['capture_id'][-10:]:<14} {row['n']:>2} {vals_s:<36} "
              f"{row['median_ms']/1000.0:>7.1f} {row['max_ms']/1000.0:>7.1f}  "
              f"{row['verdict']}", flush=True)
    judged = [r for r in rows if r["n"] >= 4]
    if judged and any(r["verdict"] == "GOOD" for r in judged):
        overall = "GOOD — a capture variant repeatedly restores ~4-5 s; find what makes those variants/pools good"
    elif judged and all(r["verdict"] == "MARGINAL" for r in judged):
        overall = "MARGINAL — capture variants settle 6-8 s; ~14-16 s E2E without more work"
    elif judged:
        overall = "BAD — restore swings 5 -> 15+ s even within single captures"
    else:
        overall = "insufficient_n — no capture variant reached 4 restores"
    print(f"\nGO/NO-GO: {overall}", flush=True)
    summary = {
        "n_deployments": n_deployments, "max_invocations": max_invocations,
        "overall": overall, "rows": rows, "deployments": deployments,
    }
    out_dir = ROOT / "matrix_runs" / datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / "capture_buckets.json"
    out_file.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    print(f"\n=== ARTIFACT: {out_file} ===", flush=True)
    return summary


def _population_verdict(population: dict[str, Any]) -> str:
    """Good: restores cluster ~4-5 s (>=4 of 5 <= 6 s, median <= 5.5 s).
    Marginal: every capture settles 6-8 s.  Bad: swings 5 -> 15+ s."""
    vals = [float(r["timing"]["restore_platform_banner_to_python_ms"])
            for r in population["runs"] if r.get("ok")
            and r.get("timing", {}).get("restore_platform_banner_to_python_ms")]
    if len(vals) < 4:
        return "insufficient_valid_restores"
    s = sorted(vals)
    median = s[len(s) // 2]
    le6 = sum(1 for v in s if v <= 6000.0)
    mx = s[-1]
    if median <= 5500.0 and le6 >= 4:
        return "GOOD"
    if 6000.0 <= median <= 8000.0 and mx <= 10000.0:
        return "MARGINAL"
    if mx - s[0] > 8000.0 or mx > 15000.0:
        return "BAD"
    return "MARGINAL"


def classify_gate2_crash(gate: dict[str, Any], logs: str) -> str:
    last = ""
    for line in logs.splitlines():
        if "[gpu_snapshot]" in line:
            parts = line.split("]", 1)[-1].strip().split()
            if parts:
                last = parts[0]
    if not last:
        return "CRASH_NO_MARKERS"
    if last in ("gpu_snapshot_enter_start", "gpu_snapshot_comfy_init_start",
                "gpu_snapshot_comfy_init_complete", "gpu_snapshot_cuda_init_complete",
                "gpu_snapshot_instrumentation_installed",
                "gpu_snapshot_workflow_provisioned",
                "gpu_snapshot_dependency_preflight_complete",
                "gpu_snapshot_unet_load_start", "gpu_snapshot_unet_load_complete",
                "gpu_snapshot_unet_cuda_verified", "gpu_snapshot_clip_load_start",
                "gpu_snapshot_clip_load_complete", "gpu_snapshot_clip_cuda_verified",
                "gpu_snapshot_vae_load_start", "gpu_snapshot_vae_load_complete",
                "gpu_snapshot_vae_cuda_verified", "gpu_snapshot_cachedit_prepared",
                "gpu_snapshot_graph_prevalidation_complete",
                "gpu_snapshot_pre_capture_verified", "gpu_snapshot_cuda_memory"):
        return "CRASH_SNAPSHOT_BUILD_WORKLOAD"
    if last in ("gpu_snapshot_pre_capture_sync_complete", "gpu_snapshot_enter_returning"):
        return "CRASH_CHECKPOINT_RESTORE"
    if last in ("gpu_snapshot_post_restore_enter", "gpu_snapshot_post_restore_cuda_verified",
                "gpu_snapshot_post_restore_models_verified"):
        return "CRASH_RESTORED_CUDA_STATE"
    if last == "gpu_snapshot_post_restore_verify_complete":
        return "CRASH_RESTORED_MODEL_STATE"
    if last in ("gpu_snapshot_h2d_bypass_verified", "gpu_snapshot_no_reread_verified",
                "gpu_snapshot_request_method_entry", "gpu_snapshot_sampler_start"):
        return "CRASH_WORKFLOW_EXECUTION"
    return f"CRASH_OTHER_LAST_MARKER={last}"


def uuid4hex() -> str:
    import uuid
    return uuid.uuid4().hex[:8]


async def main() -> None:
    args = sys.argv[1:]
    global _EVICT_GPU_FLAG
    app_name = SHADOW_APP_DEFAULT
    gate_filter: str | None = None
    deploy_only = "--deploy-only" in args
    no_deploy = "--no-deploy" in args
    _EVICT_GPU_FLAG = "--evict" in args
    n_repeats = 0
    n_captures = 0
    if "--app" in args:
        app_name = args[args.index("--app") + 1]
    if "--gate" in args:
        gate_filter = args[args.index("--gate") + 1]
    if "--runs" in args:
        n_repeats = int(args[args.index("--runs") + 1])
    if "--captures" in args:
        n_captures = int(args[args.index("--captures") + 1])

    global ws
    ws = _load_workspace()
    env = _base_env(app_name)

    if n_captures > 0:
        # Fresh captures per population: a deploy is required before each.
        if no_deploy:
            raise SystemExit("--captures requires a fresh capture per population; "
                             "--no-deploy is not supported in this mode")
        # The GPU snapshot build loads the models by COMFYMODAL_WARMUP_*
        # names; without the warmup profile the capture build fails with
        # "COMFYMODAL_WARMUP_UNET is not set".  Fail fast locally instead of
        # burning a paid build invocation.
        env = _with_warmup_profile(env)
        if not env.get("COMFYMODAL_WARMUP_UNET"):
            raise SystemExit("warmup profile did not set COMFYMODAL_WARMUP_UNET; "
                             "refusing to deploy")
        await run_capture_buckets(
            n_deployments=n_captures, app_name=app_name,
            env=env, gap_seconds=15.0, max_invocations=6,
        )
        return

    if not no_deploy:
        env = _with_warmup_profile(env)
        deploy(app_name, env)
        if deploy_only:
            print("=== Deploy-only requested; gates skipped ===")
            return
    else:
        print("=== --no-deploy: using existing deployment ===")

    if n_repeats > 0:
        # Repeat experiment: N restored attempts, banner-based timing
        # (scheduling excluded, platform restore included).
        repeat = await run_gate2_repeats(app_name, n_runs=n_repeats)
        print("\n=== REPEAT EXPERIMENT RESULT ===", flush=True)
        print(json.dumps(repeat, default=str, indent=2), flush=True)
        return

    if gate_filter in (None, "1"):
        gate1 = await run_gate1(app_name)
        print("\nGATE 1 RESULT:", gate1["conclusion"], flush=True)
        if gate1["conclusion"] not in ("PASS",):
            print("\n=== STOP: Gate 1 did not pass; ComfyUI work stops ===", flush=True)
            print(json.dumps(gate1, default=str, indent=2), flush=True)
            return
    if gate_filter in (None, "2"):
        gate2 = await run_gate2(app_name)
        print("\nGATE 3 RESULT:", gate2["conclusion"], flush=True)
        if gate2["conclusion"] == "PASS":
            # ONE second restored attempt with a DIFFERENT prompt and seed
            # (same model stack) to prove the snapshot is reusable model /
            # runtime state rather than baked prompt-specific execution
            # state.  Build-phase attempts in between (Modal recaptures
            # snapshots for worker-type coverage) do not count as restored
            # attempts.
            print("\n=== PROMPT-VARIANT: second restored attempt ===", flush=True)
            gate2c = await run_gate2_prompt_variant(app_name)
            gate2["prompt_variant"] = gate2c
            print("PROMPT-VARIANT RESULT:", gate2c["conclusion"], flush=True)
        print("\n=== FINAL ===", flush=True)
        print(json.dumps(gate2, default=str, indent=2), flush=True)


if __name__ == "__main__":
    asyncio.run(main())
