"""2x2 restore matrix runner: CPU/GPU snapshot x AWS us-east-2 / GCP us-east4.

Restore-causality experiment — the ONLY paid work this runner does is cold
single-use container restores.  No workflow execution, no CLIP encode, no
sampling, no VAE decode, no image output: each measured attempt restores
the snapshot and returns a tiny JSON probe.

Protocol (interleaved to reduce time-window/pool confounding):

    cycle n:  cpu-aws → cpu-gcp → gpu-aws → gpu-gcp   (one attempt each)

Deploys all four arms once up front (deploys are free; the first attempt
per arm CAPTURES the snapshot and is never counted as a restore).  After
two full cycles the distributions are inspected and the run may stop
early (decisive separation or negligible variance); per arm the maximum
is 4 valid restored measurements.  Snapshot builders are recorded
separately, never as restores.

Usage:
    python tools/run_restore_matrix.py [--deploy-only] [--no-deploy]
        [--max-valid-per-arm N] [--max-cycles N] [--gap-seconds S]
        [--evict-cpu]
        [--gpu-dist N] [--gap-seconds S]

    --evict-cpu  corrected-CPU-arm experiment: deploys separate apps
                 (``*-cpu-evict-restore-matrix-{aws,gcp}``) with
                 COMFYMODAL_V2_EVICT_MODELS_BEFORE_SNAPSHOT=1 and
                 COMFYMODAL_V2_EVICT_RETAIN_ROLE unset (none).  A valid
                 restore in this mode requires the models to be ABSENT
                 after restore (eviction marker present at capture).
                 Baseline (eviction=0) runs are never mixed with it.

    --gpu-dist N  PART C distribution study: AWS us-east-2 ONLY, restore-only
                  probes, one invocation at a time, ~25 s gaps, same-capture
                  (no redeploy between measurements; use --no-deploy unless a
                  fresh capture is explicitly wanted).  Interleaves the full-
                  payload CPU and evicted-CPU apps as same-window controls
                  (3 each max).  N = target VALID GPU restores (default 8,
                  max 12 without asking).  First invocation after a deploy
                  captures the snapshot and is never counted.
"""

from __future__ import annotations

import asyncio
import datetime
import json
import os
import statistics
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

RUNTIME_CONFIG_VOLUME = "comfymodal-runtime-config"
SHADOW_WORKFLOW_REMOTE = "gpu_snapshot_workflow.json"

# ── The four arms ─────────────────────────────────────────────────────────
ARMS = {
    "cpu-aws": {
        "snapshot_type": "cpu",
        "provider": "aws",
        "region": "us-east-2",
        "app": "stable-modal-comfy-v2-cpu-restore-matrix-aws",
        "class": "CpuSnapshotRestoreShadow",
        "method": "run_cpu_snapshot_restore_probe",
        "entry_anchor": "cpu_snapshot_restore_probe_entry",
        "first_line": "cpu_snapshot_post_restore_enter",
        "complete": "cpu_snapshot_restore_probe_complete",
    },
    "cpu-gcp": {
        "snapshot_type": "cpu",
        "provider": "gcp",
        "region": "us-east4",
        "app": "stable-modal-comfy-v2-cpu-restore-matrix-gcp",
        "class": "CpuSnapshotRestoreShadow",
        "method": "run_cpu_snapshot_restore_probe",
        "entry_anchor": "cpu_snapshot_restore_probe_entry",
        "first_line": "cpu_snapshot_post_restore_enter",
        "complete": "cpu_snapshot_restore_probe_complete",
    },
    "gpu-aws": {
        "snapshot_type": "gpu",
        "provider": "aws",
        "region": "us-east-2",
        "app": "stable-modal-comfy-v2-gpu-restore-matrix-aws",
        "class": "GpuSnapshotUnetShadow",
        "method": "run_gpu_snapshot_restore_probe",
        "entry_anchor": "gpu_snapshot_restore_probe_entry",
        "first_line": "gpu_snapshot_post_restore_enter",
        "complete": "gpu_snapshot_restore_probe_complete",
    },
    "gpu-gcp": {
        "snapshot_type": "gpu",
        "provider": "gcp",
        "region": "us-east4",
        "app": "stable-modal-comfy-v2-gpu-restore-matrix-gcp",
        "class": "GpuSnapshotUnetShadow",
        "method": "run_gpu_snapshot_restore_probe",
        "entry_anchor": "gpu_snapshot_restore_probe_entry",
        "first_line": "gpu_snapshot_post_restore_enter",
        "complete": "gpu_snapshot_restore_probe_complete",
    },
}
CYCLE_ORDER = ["cpu-aws", "cpu-gcp", "gpu-aws", "gpu-gcp"]
# Decisive-separation threshold (ms): if all AWS restores of a snapshot
# type are faster than all GCP restores (or vice versa) with at least this
# gap after two cycles, stop early instead of consuming all 16 calls.
_DECISIVE_GAP_MS = 1000.0

# ── PART C: AWS GPU restore-distribution arms (same-window CPU controls) ──
# Three existing AWS us-east-2 apps, all deployed by this runner's earlier
# experiments with retained snapshots.  No redeploy between measurements.
GPU_DIST_ARMS = {
    "gpu-aws": ARMS["gpu-aws"],
    "cpu-aws": ARMS["cpu-aws"],
    "cpu-evict-aws": {
        "snapshot_type": "cpu",
        "provider": "aws",
        "region": "us-east-2",
        "app": "stable-modal-comfy-v2-cpu-evict-restore-matrix-aws",
        "class": "CpuSnapshotRestoreShadow",
        "method": "run_cpu_snapshot_restore_probe",
        "entry_anchor": "cpu_snapshot_restore_probe_entry",
        "first_line": "cpu_snapshot_post_restore_enter",
        "complete": "cpu_snapshot_restore_probe_complete",
        "evict": "1",
    },
}


def _gpu_dist_sequence(max_gpu: int, max_cpu_full: int = 3,
                       max_cpu_evicted: int = 3) -> list[str]:
    """Interleaved same-window sequence: G, G, CE, CF, G, G, CE, CF, ...

    Mirrors the conceptual ordering ``GPU CPU-full GPU GPU CPU-evicted ...``
    with controls capped at 3 each; the important property is same time
    window, not exact order.
    """
    seq: list[str] = []
    g = cf = ce = 0
    first = True
    while g < max_gpu:
        if not first and cf < max_cpu_full:
            seq.append("cpu-aws")
            cf += 1
        first = False
        seq.append("gpu-aws")
        g += 1
        if g >= max_gpu:
            break
        seq.append("gpu-aws")
        g += 1
        if g >= max_gpu:
            break
        if ce < max_cpu_evicted:
            seq.append("cpu-evict-aws")
            ce += 1
    return seq


def _gpu_dist_report(valid_ms: list[float]) -> dict[str, Any]:
    """Descriptive population report with the PART C bucket counts."""
    out = _agg(valid_ms)
    if not valid_ms:
        return out
    s = sorted(valid_ms)
    out["p50_ms"] = round(s[len(s) // 2], 1)
    out["p75_ms"] = round(s[min(len(s) - 1, int(round(len(s) * 0.75)))], 1)
    if len(s) >= 5:
        out["p90_ms"] = round(s[min(len(s) - 1, int(round(len(s) * 0.9)))], 1)
    out["raw_values_ms"] = [round(v, 1) for v in s]
    out["count_le_5s"] = sum(1 for v in s if v <= 5000.0)
    out["count_le_6s"] = sum(1 for v in s if v <= 6000.0)
    out["count_le_7s"] = sum(1 for v in s if v <= 7000.0)
    out["count_7_to_10s"] = sum(1 for v in s if 7000.0 < v <= 10000.0)
    out["count_gt_10s"] = sum(1 for v in s if v > 10000.0)
    out["count_gt_15s"] = sum(1 for v in s if v > 15000.0)
    out["straggler_rate_gt15_pct"] = round(
        100.0 * out["count_gt_15s"] / len(s), 1
    )
    # ── Pattern classification (descriptive, small-n) ──
    if len(s) < 4:
        out["pattern"] = "insufficient_n"
        return out
    median = out["median_ms"]
    _gt15 = out["count_gt_15s"]
    _core = [v for v in s if v <= 10000.0]
    _spread_ratio = (s[-1] - s[0]) / median if median else 0.0
    if _core and _gt15 == 0 and (s[-1] - s[0]) <= 3.5 * median:
        out["pattern"] = "pattern1_healthy_core_no_straggler"
    elif _core and _gt15 > 0 and len(_core) >= 0.6 * len(s):
        out["pattern"] = "pattern1_healthy_core_with_straggler"
    elif _gt15 and len(_core) < 0.6 * len(s):
        out["pattern"] = "pattern2_continuously_broad"
    else:
        out["pattern"] = "pattern3_or_4_ambiguous_window_shift_or_multimodal"
    return out


def _gpu_dist_classify(new_gpu: dict[str, Any], historical_vals: list[float]) -> str:
    """Choose between the four PART C distribution interpretations.

    Descriptive only — never causal from n<8.
    """
    n = new_gpu.get("n", 0)
    if n < 4:
        return "insufficient_n"
    median = new_gpu.get("median_ms", 0.0)
    hist_median = sorted(historical_vals)[len(historical_vals) // 2] if historical_vals else None
    pattern = new_gpu.get("pattern", "")
    if pattern.startswith("pattern1"):
        return "pattern1_healthy_core_plus_straggler_tail"
    if pattern.startswith("pattern2"):
        return "pattern2_continuously_broad_no_stable_mode"
    if hist_median is not None and abs(median - hist_median) > 0.4 * hist_median:
        return "pattern3_window_shift_vs_historical"
    return "pattern4_or_ambiguous_limited_n"


async def run_gpu_distribution(
    target_valid_gpu: int, gap_seconds: float, *, do_deploy: bool,
) -> dict[str, Any]:
    """PART C: AWS us-east-2 only; one invocation at a time; ~25 s gaps;
    same-capture restores (no redeploy between measurements); restore-only
    probes; interleaved CPU controls (full-payload + evicted)."""
    print("=" * 70, flush=True)
    print(f"GPU DISTRIBUTION STUDY — AWS us-east-2, target {target_valid_gpu} "
          f"valid GPU restores + same-window CPU controls", flush=True)
    print("=" * 70, flush=True)
    if do_deploy:
        _provision_workflow()
        for key in ("gpu-aws", "cpu-aws", "cpu-evict-aws"):
            arm = GPU_DIST_ARMS[key]
            deploy(arm["app"], _arm_env(arm, arm["app"]))
    seq = _gpu_dist_sequence(target_valid_gpu)
    print(f"sequence={json.dumps(seq)}", flush=True)
    runs: list[dict[str, Any]] = []
    valid_gpu = 0
    gpu_attempts = 0
    for idx, arm_key in enumerate(seq):
        arm = GPU_DIST_ARMS[arm_key]
        record = await run_attempt(arm, idx + 1, gap_seconds)
        record["arm_key"] = arm_key
        runs.append(record)
        if arm_key == "gpu-aws":
            gpu_attempts += 1
            if record.get("valid_restore"):
                valid_gpu += 1
                print(f"--- valid GPU restores so far: {valid_gpu}/{target_valid_gpu} "
                      f"(attempts {gpu_attempts}) ---", flush=True)
                if valid_gpu >= target_valid_gpu:
                    break
    # ── Bounded top-up: guarantee `target_valid_gpu` valid GPU restores
    #    unless the app is genuinely failing (recaptures/errors never
    #    count; never redeploy; controls already interleaved above). ──
    _topup_index = len(seq) + 1
    while valid_gpu < target_valid_gpu and gpu_attempts < target_valid_gpu + 4:
        arm = GPU_DIST_ARMS["gpu-aws"]
        record = await run_attempt(arm, _topup_index, gap_seconds)
        record["arm_key"] = "gpu-aws"
        runs.append(record)
        _topup_index += 1
        gpu_attempts += 1
        if record.get("valid_restore"):
            valid_gpu += 1
            print(f"--- valid GPU restores so far: {valid_gpu}/{target_valid_gpu} "
                  f"(attempts {gpu_attempts}) ---", flush=True)
    # ── Populations: new same-capture GPU vs historical existing samples ──
    gpu_ms = [float(r["timing"]["platform_restore_banner_to_python_ms"])
              for r in runs if r.get("arm_key") == "gpu-aws"
              and r.get("valid_restore")
              and r.get("timing", {}).get("platform_restore_banner_to_python_ms")]
    cpu_full_ms = [float(r["timing"]["platform_restore_banner_to_python_ms"])
                   for r in runs if r.get("arm_key") == "cpu-aws"
                   and r.get("valid_restore")
                   and r.get("timing", {}).get("platform_restore_banner_to_python_ms")]
    cpu_evict_ms = [float(r["timing"]["platform_restore_banner_to_python_ms"])
                    for r in runs if r.get("arm_key") == "cpu-evict-aws"
                    and r.get("valid_restore")
                    and r.get("timing", {}).get("platform_restore_banner_to_python_ms")]
    new_gpu_report = _gpu_dist_report(gpu_ms)
    # Historical AWS full-stack GPU samples (existing evidence, separate
    # population — do not pool blindly; images/captures differ).
    historical_gpu_aws = [6309.2, 17833.6, 7124.9, 6798.1, 4440.4, 5314.2]
    classification = _gpu_dist_classify(new_gpu_report, historical_gpu_aws)
    summary = {
        "started_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "scope": "AWS us-east-2 restore-only, same-capture population",
        "target_valid_gpu": target_valid_gpu,
        "sequence": seq,
        "gap_seconds": gap_seconds,
        "new_gpu_population": new_gpu_report,
        "historical_gpu_aws_existing": {
            "raw_values_ms": historical_gpu_aws,
            "note": "separate captures/images (im-z0sKCZ.. baseline 4 + "
                    "im-XWRWnfy1sK5AbuxeEBPruf evict-window controls 2); "
                    "not pooled with the new population",
        },
        "cpu_full_control_population": _gpu_dist_report(cpu_full_ms),
        "cpu_evicted_control_population": _gpu_dist_report(cpu_evict_ms),
        "classification": classification,
        "runs": runs,
        "notes": {
            "platform_restore_ms": "banner->first-python-line, log-server clock",
            "submit_to_restore_banner_ms": "recorded separately, never combined",
            "snapshot_capture_attempts": "phase=build, not valid restores",
            "max_valid_gpu": "target 8; extend same capture with "
                             "--gpu-dist 12 --no-deploy (max 12 without asking)",
        },
    }
    out_dir = ROOT / "matrix_runs" / datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / "gpu_distribution.json"
    out_file.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    print("\n=== NEW GPU POPULATION (banner->Python, AWS us-east-2) ===", flush=True)
    print(json.dumps(new_gpu_report, default=str, indent=2), flush=True)
    print(f"\n=== CLASSIFICATION: {classification} ===", flush=True)
    print(f"\n=== CPU CONTROLS (same window) ===", flush=True)
    print(f"cpu-full: {json.dumps(_gpu_dist_report(cpu_full_ms), default=str)}", flush=True)
    print(f"cpu-evicted: {json.dumps(_gpu_dist_report(cpu_evict_ms), default=str)}", flush=True)
    print(f"\n=== ARTIFACT: {out_file} ===", flush=True)
    return summary


def _load_workspace() -> dict[str, Any]:
    ws_path = ROOT / ".modal_workspaces.json"
    ws = json.loads(ws_path.read_text(encoding="utf-8"))
    aid = ws.get("active_workspace_id")
    entry = next((w for w in ws.get("workspaces", []) if w.get("id") == aid), None)
    if not entry or not entry.get("token_id") or not entry.get("token_secret"):
        raise RuntimeError("could not load active Modal workspace credentials")
    return entry


def _provision_workflow() -> None:
    local = ROOT / "latest_benchmark_workflow.json"
    if not local.is_file():
        print("=== WARNING: latest_benchmark_workflow.json missing; GPU snapshot "
              "build will skip preflight/prevalidation prebuild ===", flush=True)
        return
    try:
        import modal as _m
        client = _m.Client.from_credentials(ws["token_id"], ws["token_secret"])
        vol = _m.Volume.from_name(RUNTIME_CONFIG_VOLUME, create_if_missing=True, client=client)
        batch = getattr(vol, "batch_upload", None)
        if batch is None:
            return
        with batch(force=True) as upload:
            upload.put_file(str(local), SHADOW_WORKFLOW_REMOTE)
        print(f"=== Provisioned {SHADOW_WORKFLOW_REMOTE} on {RUNTIME_CONFIG_VOLUME} ===", flush=True)
    except Exception as exc:  # noqa: BLE001
        print(f"=== WARNING: workflow provisioning failed ({exc}) ===", flush=True)


def _arm_env(arm: dict[str, Any], app_name: str) -> dict[str, str]:
    env = dict(os.environ)
    env.update({
        "MODAL_TOKEN_ID": str(ws["token_id"]),
        "MODAL_TOKEN_SECRET": str(ws["token_secret"]),
        "COMFYMODAL_V2_GPU_SNAPSHOT_APP": app_name,
        "COMFYMODAL_V2_APP_NAME": app_name,
        "COMFYMODAL_V2_GPU": "rtx-pro-6000",
        "COMFYMODAL_V2_ENV_PROFILE": "production",
        "COMFYMODAL_V2_CPU_REQUEST": "16",
        "COMFYMODAL_V2_MEMORY_REQUEST": "49152",
        "COMFYMODAL_V2_MEMORY_MB": "49152",
        "COMFYMODAL_V2_SINGLE_USE_CONTAINERS": "1",
        "COMFYMODAL_V2_CLOUD": arm["provider"],
        "COMFYMODAL_V2_REGION": arm["region"],
        "COMFYMODAL_ENABLE_GPU_SNAPSHOT": "1" if arm["snapshot_type"] == "gpu" else "0",
        # CPU baseline = CURRENT production configuration (eviction disabled);
        # --evict-cpu flips it to 1 for the corrected-CPU experiment only.
        "COMFYMODAL_V2_EVICT_MODELS_BEFORE_SNAPSHOT": "1" if arm.get("evict") else "0",
        "COMFYMODAL_V2_EVICT_RESTORE_IDLE_SECONDS": "0",
        "COMFYMODAL_V2_EVICT_RETAIN_ROLE": "",
        "COMFYMODAL_V2_CPU_MODEL_SNAPSHOT": "1",
        "COMFYMODAL_V2_VAE_SNAPSHOT": "1",
        "COMFYMODAL_V2_VAE_POLICY": "v1",
        "COMFYMODAL_V2_PREFILL_LANES": "critical",
        "COMFYMODAL_V2_UNET_EXCLUSIVE_OWNER": "0",
        "COMFYMODAL_V2_UNET_REHOME_AFTER_RESTORE": "0",
        "COMFYMODAL_V2_PAGE_PATH_PROBE": "0",
        "COMFYMODAL_V2_SYNTH_H2D_PROBE": "0",
        "COMFYMODAL_V2_UNET_BACKING_VERIFY": "0",
        "COMFYMODAL_V2_ANON_UNET_SNAPSHOT": "0",
        "COMFYMODAL_V2_FULL_TRACE": "0",
        "COMFYMODAL_V2_RESIDENCY_DIAGNOSTICS": "0",
        "COMFYMODAL_V2_DEEP_MODEL_DIAG": "0",
        "COMFYMODAL_V2_PAGEFAULT_TRACKING": "0",
        "COMFYMODAL_V2_VARIANCE_DIAGNOSTICS": "0",
        "COMFYMODAL_V2_HOST_DIAGNOSTICS": "0",
        "COMFYMODAL_V2_SNAPSHOT_MANIFEST": "0",
        "COMFYMODAL_V2_TORCH_COMPILE": "0",
        "COMFYMODAL_ENABLE_TORCH_COMPILE": "0",
        "PYTHONIOENCODING": "utf-8",
        "PYTHONUTF8": "1",
    })
    # Warmup profile (COMFYMODAL_WARMUP_*: UNET/CLIP1/CLIP_TYPE/VAE/PROFILE).
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
    env = dict(os.environ)
    if "ws" in globals():
        env.update({
            "MODAL_TOKEN_ID": str(ws["token_id"]),
            "MODAL_TOKEN_SECRET": str(ws["token_secret"]),
        })
    env.setdefault("PYTHONIOENCODING", "utf-8")
    env.setdefault("PYTHONUTF8", "1")
    return env


async def _fetch_banner_timing(arm: dict[str, Any], request_id: str) -> dict[str, Any] | None:
    """Fetch app logs; return banner/first-line/method-entry/complete
    epoch-ms (log-server clock).  Anchored on this request's own
    ``{entry_anchor} request_id=...`` line so attempts never cross-match."""
    import modal as _m
    from modal.cli.app import resolve_app_identifier
    from modal._logs import tail_logs
    from modal.client import _Client
    client = await _Client.from_credentials(ws["token_id"], ws["token_secret"])
    app_id, _, _ = await resolve_app_identifier(arm["app"], None, client)
    anchor = f"{arm['entry_anchor']} request_id={request_id}"
    for _attempt in range(8):
        entries: list[tuple[float, str]] = []
        try:
            async for batch in tail_logs(client, app_id, 4000):
                for item in batch.items:
                    ts = getattr(item, "timestamp", None)
                    if ts is None:
                        continue
                    raw = getattr(item, "data", b"")
                    text = raw if isinstance(raw, str) else (raw or b"").decode("utf-8", "replace")
                    entries.append((float(ts) * 1000.0, text))
        except Exception as exc:  # noqa: BLE001
            print(f"=== banner timing fetch error: {exc} ===", flush=True)
            return None
        if not entries:
            await asyncio.sleep(2.0)
            continue
        idx = next((i for i, (_t, l) in enumerate(entries) if anchor in l), None)
        if idx is None:
            await asyncio.sleep(2.0)
            continue
        ci = next((i for i in range(idx + 1, len(entries))
                   if arm["complete"] in entries[i][1]), None)
        if ci is None:
            await asyncio.sleep(2.0)
            continue
        fi = max((i for i in range(idx) if arm["first_line"] in entries[i][1]), default=None)
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
            "complete_epoch_ms": entries[ci][0],
        }
    print(f"=== banner timing: could not pair request markers ({arm['app']}) ===", flush=True)
    return None


async def _invoke_remote(fn: Any, **kwargs: Any) -> Any:
    aio = getattr(fn, "aio", None)
    if callable(aio):
        result = aio(**kwargs)
        if asyncio.iscoroutine(result):
            return await result
    remote = getattr(fn, "remote", None)
    if remote is None:
        raise RuntimeError(f"method handle has no .remote/.aio: {fn}")
    return await asyncio.to_thread(remote, **kwargs)


def _marker_names(evidence: dict[str, Any]) -> list[str]:
    return [str(m.get("marker", "")) for m in (evidence.get("markers") or []) if isinstance(m, dict)]


def _fingerprint_hash(verification: dict[str, Any]) -> str:
    fp = verification.get("worker_fingerprint") or {}
    identity = {
        "cloud": fp.get("modal_cloud_provider", ""),
        "region": fp.get("modal_region", ""),
        "task": fp.get("modal_task_id", ""),
        "image": fp.get("modal_image_id", ""),
        "host": fp.get("hostname", ""),
        "cpu": (fp.get("cpu") or {}).get("model_name", ""),
        "flags": (fp.get("cpu") or {}).get("flags_hash", ""),
        "affinity": (fp.get("cpu") or {}).get("affinity_hash", ""),
        "gpu": (fp.get("gpu") or {}).get("gpu_name", ""),
        "gpu_uuid": (fp.get("gpu") or {}).get("gpu_uuid", ""),
        "driver": (fp.get("gpu") or {}).get("driver_version", ""),
    }
    import hashlib
    return hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:12]


def _run_is_valid(arm: dict[str, Any], evidence: dict[str, Any]) -> bool:
    verify = evidence.get("verification") or {}
    if arm["snapshot_type"] == "cpu":
        if arm.get("evict"):
            # Evicted-CPU arms: a valid restore has NO models (they were
            # evicted before capture) and the eviction flag carried over.
            return bool(
                evidence.get("phase") == "restore"
                and verify.get("evict_enabled") == 1
                and not verify.get("models_container_present")
            )
        return bool(
            verify.get("models_container_present")
            and verify.get("unet_object_present")
            and verify.get("clip_object_present")
            and verify.get("vae_object_present")
        )
    return bool(
        verify.get("unet_already_cuda_resident")
        and verify.get("clip_already_cuda_resident")
        and verify.get("vae_already_cuda_resident")
    )


async def run_attempt(arm: dict[str, Any], index: int, gap_seconds: float) -> dict[str, Any]:
    handle = _handle(arm["app"], arm["class"])
    fn = getattr(handle, arm["method"], None)
    if fn is None:
        raise RuntimeError(f"deployed {arm['app']} has no {arm['method']} method")
    req_id = f"restore-matrix-{arm['snapshot_type']}-{arm['provider']}-{index:02d}-{uuid.uuid4().hex[:8]}"
    submit_ns = int(time.time() * 1_000_000_000)
    print(f"\n--- {arm['snapshot_type'].upper()} {arm['provider'].upper()} "
          f"attempt {index} (request {req_id}) ---", flush=True)
    t0 = time.perf_counter()
    try:
        ev = await _invoke_remote(fn, request_id=req_id, submit_wall_unix_ns=submit_ns)
    except Exception as exc:  # noqa: BLE001
        wall_ms = (time.perf_counter() - t0) * 1000.0
        return {
            "arm": f"{arm['snapshot_type']}-{arm['provider']}",
            "snapshot_type": arm["snapshot_type"], "provider": arm["provider"],
            "region": arm["region"], "attempt": index, "request_id": req_id,
            "status": "error", "error": f"{type(exc).__name__}: {str(exc)[:300]}",
            "wall_ms": round(wall_ms, 1), "phase": "error",
            "valid_restore": False,
        }
    wall_ms = (time.perf_counter() - t0) * 1000.0
    phase = str(ev.get("phase", "unknown"))
    verify = ev.get("verification", {}) or {}
    valid = _run_is_valid(arm, ev)
    banner = await _fetch_banner_timing(arm, req_id)
    timing: dict[str, Any] = {}
    if banner:
        b = float(banner["banner_epoch_ms"])
        f = float(banner["first_line_epoch_ms"])
        c = float(banner["complete_epoch_ms"])
        timing["submit_to_restore_banner_ms"] = round(b - submit_ns / 1_000_000, 1)
        timing["platform_restore_banner_to_python_ms"] = round(f - b, 1)
        timing["python_after_restore_ms"] = round(c - f, 1)
    else:
        timing["banner_parse"] = "unavailable"
    pm = verify.get("process_memory") or verify.get("process_memory_after_restore") or {}
    cuda = verify.get("cuda_memory") or verify.get("cuda_after_restore") or {}
    record = {
        "arm": f"{arm['snapshot_type']}-{arm['provider']}",
        "snapshot_type": arm["snapshot_type"], "provider": arm["provider"],
        "region": arm["region"], "attempt": index, "request_id": req_id,
        "phase": phase,
        "status": "ok",
        "valid_restore": bool(valid and phase == "restore"),
        "snapshot_capture": phase == "build",
        "markers": _marker_names(ev),
        "timing": timing,
        "wall_ms": round(wall_ms, 1),
        "cpu_rss_mib_after_restore": pm.get("rss_mib"),
        "cpu_pss_mib_after_restore": pm.get("pss_mib"),
        "cpu_anonymous_mib_after_restore": pm.get("anonymous_mib"),
        "cgroup_current_mib_after_restore": pm.get("cgroup_current_mib"),
        "cuda_allocated_mib_after_restore": cuda.get("allocated_mib"),
        "cuda_reserved_mib_after_restore": cuda.get("reserved_mib"),
        "total_model_bytes_after_restore": (
            verify.get("model_storage") or verify.get("cuda_model_storage")
            or verify.get("model_storage_after_restore") or verify.get("cuda_model_storage_after_restore")
            or {}
        ).get("total_unique_model_bytes"),
        "evict_enabled": verify.get("evict_enabled"),
        "retain_role": verify.get("retain_role"),
        "cpu_fingerprint_hash": _fingerprint_hash(verify),
        "gpu_fingerprint": {
            "name": (verify.get("worker_fingerprint") or {}).get("gpu", {}).get("gpu_name", ""),
            "uuid": (verify.get("worker_fingerprint") or {}).get("gpu", {}).get("gpu_uuid", ""),
            "driver": (verify.get("worker_fingerprint") or {}).get("gpu", {}).get("driver_version", ""),
        },
        "worker_fingerprint": verify.get("worker_fingerprint", {}),
        "verification_identity": {
            "unet": verify.get("unet_identity", ""),
            "clip": verify.get("clip_identity", ""),
            "vae": verify.get("vae_identity", ""),
        },
        "build_stage_count": len(ev.get("build_stages") or {}),
        "build_fingerprint": ev.get("build_fingerprint", {}),
        "build_reference_holders": ev.get("build_reference_holders", {}),
    }
    print(f"phase={phase} valid_restore={int(record['valid_restore'])} "
          f"snapshot_capture={int(record['snapshot_capture'])}", flush=True)
    print(f"timing={json.dumps(timing, default=str)}", flush=True)
    print(f"rss_mib={record['cpu_rss_mib_after_restore']} "
          f"cuda_allocated_mib={record['cuda_allocated_mib_after_restore']} "
          f"model_bytes={record['total_model_bytes_after_restore']}", flush=True)
    if gap_seconds > 0:
        await asyncio.sleep(gap_seconds)
    return record


def _agg(vals: list[float]) -> dict[str, Any]:
    if not vals:
        return {"n": 0}
    s = sorted(vals)
    n = len(s)
    mean = sum(s) / n
    std = statistics.pstdev(s) if n > 1 else 0.0
    cv = (std / mean * 100.0) if mean else 0.0
    return {
        "n": n, "min_ms": round(s[0], 1), "median_ms": round(s[n // 2], 1),
        "mean_ms": round(mean, 1), "p90_ms": round(s[min(n - 1, int(round(n * 0.9)))], 1),
        "max_ms": round(s[-1], 1), "range_ms": round(s[-1] - s[0], 1),
        "cv_pct": round(cv, 1), "stddev_ms": round(std, 1),
        "fastest_ms": round(s[0], 1), "slowest_ms": round(s[-1], 1),
        "small_n_descriptive_only": n < 5,
    }


def _decisive_separation(arm_runs: dict[str, list[dict[str, Any]]]) -> bool:
    """After two cycles: for each snapshot type, if AWS and GCP restore
    sets are non-overlapping with >= _DECISIVE_GAP_MS gap, stop early."""
    for snap_type in ("cpu", "gpu"):
        aws = [float(r["timing"]["platform_restore_banner_to_python_ms"])
               for r in arm_runs.get(f"{snap_type}-aws", []) if r.get("valid_restore")]
        gcp = [float(r["timing"]["platform_restore_banner_to_python_ms"])
               for r in arm_runs.get(f"{snap_type}-gcp", []) if r.get("valid_restore")]
        if not aws or not gcp:
            continue
        aws_max, gcp_min = max(aws), min(gcp)
        gcp_max, aws_min = max(gcp), min(aws)
        if gcp_min - aws_max >= _DECISIVE_GAP_MS or aws_min - gcp_max >= _DECISIVE_GAP_MS:
            return True
    return False


async def main() -> None:
    args = sys.argv[1:]
    deploy_only = "--deploy-only" in args
    no_deploy = "--no-deploy" in args
    evict_cpu = "--evict-cpu" in args
    gpu_dist = 0
    if "--gpu-dist" in args:
        gpu_dist = int(args[args.index("--gpu-dist") + 1])
    max_valid_per_arm = 4
    max_cycles = 6
    gap_seconds = 25.0
    if "--max-valid-per-arm" in args:
        max_valid_per_arm = int(args[args.index("--max-valid-per-arm") + 1])
    if "--max-cycles" in args:
        max_cycles = int(args[args.index("--max-cycles") + 1])
    if "--gap-seconds" in args:
        gap_seconds = float(args[args.index("--gap-seconds") + 1])

    global ws
    ws = _load_workspace()

    if gpu_dist > 0:
        if gpu_dist > 12:
            raise SystemExit("--gpu-dist maximum is 12 valid GPU restores "
                             "(ask before exceeding)")
        await run_gpu_distribution(
            target_valid_gpu=gpu_dist,
            gap_seconds=gap_seconds,
            do_deploy=not no_deploy,
        )
        return

    if evict_cpu:
        ARMS["cpu-aws"]["app"] = "stable-modal-comfy-v2-cpu-evict-restore-matrix-aws"
        ARMS["cpu-gcp"]["app"] = "stable-modal-comfy-v2-cpu-evict-restore-matrix-gcp"
        ARMS["cpu-aws"]["evict"] = "1"
        ARMS["cpu-gcp"]["evict"] = "1"
        print("=== --evict-cpu: corrected-CPU arms (eviction=1, retain=none), "
              "separate apps, baseline untouched ===", flush=True)

    if not no_deploy:
        _provision_workflow()
        for arm_key in CYCLE_ORDER:
            arm = ARMS[arm_key]
            deploy(arm["app"], _arm_env(arm, arm["app"]))
        if deploy_only:
            print("=== Deploy-only requested; attempts skipped ===")
            return
    else:
        print("=== --no-deploy: using existing deployments ===")

    arm_runs: dict[str, list[dict[str, Any]]] = {k: [] for k in ARMS}
    arm_failed: dict[str, str] = {}
    stop_reason = "max-valid-reached"
    print("=" * 70, flush=True)
    print("2x2 RESTORE MATRIX — interleaved cycles", flush=True)
    print("=" * 70, flush=True)
    for cycle in range(1, max_cycles + 1):
        print(f"\n######## CYCLE {cycle} ########", flush=True)
        for arm_key in CYCLE_ORDER:
            if arm_key in arm_failed:
                continue
            arm = ARMS[arm_key]
            valid = [r for r in arm_runs[arm_key] if r.get("valid_restore")]
            if len(valid) >= max_valid_per_arm:
                continue
            try:
                record = await run_attempt(arm, len(arm_runs[arm_key]) + 1, gap_seconds)
            except Exception as exc:  # noqa: BLE001
                record = {
                    "arm": arm_key, "snapshot_type": arm["snapshot_type"],
                    "provider": arm["provider"], "region": arm["region"],
                    "attempt": len(arm_runs[arm_key]) + 1, "status": "error",
                    "error": f"{type(exc).__name__}: {str(exc)[:300]}",
                    "phase": "error", "valid_restore": False,
                }
            arm_runs[arm_key].append(record)
            if record.get("status") == "error":
                errs = [r for r in arm_runs[arm_key] if r.get("status") == "error"]
                if len(errs) >= 2:
                    arm_failed[arm_key] = "two_consecutive_errors"
                    print(f"=== STOP {arm_key}: {arm_failed[arm_key]} ===", flush=True)
        valid_counts = {
            k: len([r for r in v if r.get("valid_restore")]) for k, v in arm_runs.items()
        }
        print(f"\n--- after cycle {cycle}: valid restores {valid_counts} ---", flush=True)
        if all(len([r for r in arm_runs[k] if r.get("valid_restore")]) >= 2 for k in ARMS):
            if _decisive_separation(arm_runs):
                stop_reason = "decisive-separation-after-2-cycles"
                print(f"=== EARLY STOP: {stop_reason} ===", flush=True)
                break
            all_ranges_small = True
            for k in ARMS:
                vals = [float(r["timing"]["platform_restore_banner_to_python_ms"])
                        for r in arm_runs[k] if r.get("valid_restore")]
                if vals and (max(vals) - min(vals)) > 500.0:
                    all_ranges_small = False
            if all_ranges_small:
                stop_reason = "negligible-variance-after-2-cycles"
                print(f"=== EARLY STOP: {stop_reason} ===", flush=True)
                break
        if all(len([r for r in arm_runs[k] if r.get("valid_restore")]) >= max_valid_per_arm
               for k in ARMS):
            stop_reason = "max-valid-per-arm-reached"
            break
        if len(arm_failed) == len(ARMS):
            stop_reason = "all-arms-failed"
            break

    # ── Aggregate + artifact ──
    agg: dict[str, Any] = {}
    for k in CYCLE_ORDER:
        valid = [float(r["timing"]["platform_restore_banner_to_python_ms"])
                 for r in arm_runs[k]
                 if r.get("valid_restore") and r.get("timing", {}).get("platform_restore_banner_to_python_ms")]
        agg[k] = _agg(valid)
    summary = {
        "started_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "stop_reason": stop_reason,
        "arms": {k: ARMS[k] for k in ARMS},
        "max_valid_per_arm": max_valid_per_arm,
        "aggregate": agg,
        "arm_failed": arm_failed,
        "runs": [r for k in CYCLE_ORDER for r in arm_runs[k]],
        "notes": {
            "platform_restore_ms": "banner->first-python-line, log-server clock",
            "submit_to_restore_banner_ms": "recorded separately, never combined",
            "snapshot_capture_attempts": "phase=build, not valid restores",
            "small_n": "statistics are descriptive only at n<=4",
        },
    }
    out_dir = ROOT / "matrix_runs" / datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / "matrix_run.json"
    out_file.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    print("\n=== AGGREGATE (platform_restore_ms, banner->Python) ===", flush=True)
    for k in CYCLE_ORDER:
        print(f"{k}: {json.dumps(agg[k], default=str)}", flush=True)
    print(f"\n=== ARTIFACT: {out_file} ===", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
