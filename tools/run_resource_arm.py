"""Run one resource/GPU experiment arm end-to-end.

Deploys a dedicated app with the arm's CPU/RAM/GPU request, runs the
excluded warmup pair, then measured true-cold generations with a hard
per-run DNF cap (default 10 minutes), and writes an arm manifest under
``comfymodal-data/benchmarks/resource_experiments/``.

Rules:
- every run is a separate single-run invocation (V2_BENCHMARK_RUNS=1) so a
  hung run can be killed without blocking the remaining runs
- a run that exceeds the per-run cap is marked DNF (process tree killed)
- at most 2 runs per arm may be DNF/failed; the arm needs >= 3 valid runs
  (stop early once 3 valid are collected)
- ``COMFYMODAL_V2_HOST_DIAGNOSTICS=1`` so the deployed container records
  the true physical GPU (nvidia-smi name) in each run artifact

Usage:
    python tools/run_resource_arm.py ^
        --arm h100 --gpu h100 --cpu 8 --memory 28672 ^
        --runs 5 --warmup 2 --gap-seconds 20
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DATA_ROOT = ROOT.parent.parent / "comfymodal-data" / "benchmarks"
RUNS_ROOT = DATA_ROOT / "runs"
ARM_ROOT = DATA_ROOT / "resource_experiments"

BASE_ENV: dict[str, str] = {
    "COMFYMODAL_V2_ENV_PROFILE": "production",
    "COMFYMODAL_V2_CLOUD": "aws",
    "COMFYMODAL_V2_SINGLE_USE_CONTAINERS": "1",
    "COMFYMODAL_V2_RESOURCE_TELEMETRY": "1",
    "COMFYMODAL_V2_HOST_DIAGNOSTICS": "1",
    "COMFYMODAL_V2_ALLOW_MULTI_AXIS": "1",
    "COMFYMODAL_V2_THREAD_POLICY": "TBASE",
    "COMFYMODAL_V2_SNAPSHOT_MODEL_ORDER": "O0",
    "COMFYMODAL_V2_CPU_MODEL_SNAPSHOT": "1",
    "COMFYMODAL_V2_VAE_SNAPSHOT": "1",
    "COMFYMODAL_V2_CLIP_CONDITIONING_CACHE": "1",
    "COMFYMODAL_V2_UNET_ACTIVATION_MODE": "late",
    "COMFYMODAL_V2_VAE_ACTIVATION_MODE": "sampling_end",
    "COMFYMODAL_V2_PREFILL_LANES": "critical",
    "COMFYMODAL_V2_VAE_POLICY": "v1",
    "COMFYMODAL_V2_RELEASE_GPU_AFTER_REQUEST": "1",
    "COMFYMODAL_V2_PERSISTENT_LOCAL_HANDLE": "1",
}

DNF_EXIT = -999


def _run_capped(cmd: list[str], log_path: Path, cap_s: int, env: dict[str, str]) -> tuple[int, float]:
    """Run a command with a hard wall cap; kills the tree on timeout.

    Returns (exit_code, elapsed_s).  ``DNF_EXIT`` marks a timeout kill.
    """
    log_path.parent.mkdir(parents=True, exist_ok=True)
    started = time.time()
    with open(log_path, "w", encoding="utf-8") as log_fh:
        print(f"[arm] running: {' '.join(cmd)} (cap {cap_s}s)", flush=True)
        try:
            proc = subprocess.Popen(
                cmd, cwd=str(ROOT), env=env, stdout=log_fh, stderr=subprocess.STDOUT,
                creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
            )
            try:
                rc = proc.wait(timeout=cap_s)
            except subprocess.TimeoutExpired:
                try:
                    subprocess.run(
                        ["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                        capture_output=True, timeout=20,
                    )
                except Exception:
                    pass
                rc = DNF_EXIT
        except Exception as exc:
            print(f"[arm] spawn error: {type(exc).__name__}: {exc}", flush=True)
            rc = DNF_EXIT
    elapsed = time.time() - started
    status = "dnf" if rc == DNF_EXIT else f"exit={rc}"
    print(f"[arm] result={status} elapsed={elapsed:.1f}s log={log_path}", flush=True)
    return rc, elapsed


def _newest_run_dir(after_unix_s: float) -> Path | None:
    if not RUNS_ROOT.exists():
        return None
    dirs = [
        p for p in RUNS_ROOT.iterdir()
        if p.is_dir() and p.name.startswith("v2_")
        and p.stat().st_mtime >= after_unix_s - 5
    ]
    if not dirs:
        return None
    return max(dirs, key=lambda p: p.stat().st_mtime)


def _run_file_valid(path: Path) -> bool:
    """Light inline validity check of a freshly written run artifact."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        identity = data.get("identity") or {}
        result = data.get("result") or {}
        ok = (
            int(identity.get("restore_count", -1)) == 1
            and int(identity.get("request_count", -1)) == 1
            and bool(result.get("images"))
            and not result.get("error")
        )
        return ok
    except Exception:
        return False


def _active_workspace() -> dict[str, str]:
    ws_file = ROOT / ".modal_workspaces.json"
    data = json.loads(ws_file.read_text(encoding="utf-8"))
    active_id = data.get("active_workspace_id")
    for ws in data.get("workspaces", []):
        if ws.get("id") == active_id:
            return {"workspace_id": active_id, "label": ws.get("label", "")}
    return {"workspace_id": active_id, "label": ""}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--arm", required=True)
    parser.add_argument("--gpu", default="rtx-pro-6000")
    parser.add_argument("--cpu", type=int, default=16)
    parser.add_argument("--memory", type=int, default=49152)
    parser.add_argument("--runs", type=int, default=5)
    parser.add_argument("--warmup", type=int, default=2)
    parser.add_argument("--gap-seconds", type=int, default=20)
    parser.add_argument("--per-run-cap-seconds", type=int, default=600)
    parser.add_argument("--min-valid", type=int, default=3)
    parser.add_argument("--max-dnf", type=int, default=2)
    parser.add_argument("--skip-deploy", action="store_true")
    parser.add_argument("--skip-warmup", action="store_true")
    parser.add_argument("--phase", choices=["deploy", "warmup", "measured"], default=None)
    args = parser.parse_args()

    app_name = f"stable-modal-comfy-v2-res-{args.arm}"
    env = dict(os.environ)
    env.update(BASE_ENV)
    env.update({
        "COMFYMODAL_V2_APP_NAME": app_name,
        "V2_DEPLOY_IDENT": app_name,
        "COMFYMODAL_V2_GPU": args.gpu,
        "COMFYMODAL_V2_CPU_REQUEST": str(args.cpu),
        "COMFYMODAL_V2_MEMORY_REQUEST": str(args.memory),
        "COMFYMODAL_V2_MEMORY_MB": str(args.memory),
        "COMFYMODAL_V2_BASELINE_CPU_REQUEST": "16",
        "COMFYMODAL_V2_BASELINE_MEMORY_REQUEST": "49152",
    })

    ARM_ROOT.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    manifest: dict[str, Any] = {
        "arm": args.arm, "app_name": app_name, "gpu": args.gpu,
        "cpu_request": args.cpu, "memory_request": args.memory,
        "runs_requested": args.runs, "warmup_requested": args.warmup,
        "per_run_cap_seconds": args.per_run_cap_seconds,
        "min_valid": args.min_valid, "max_dnf": args.max_dnf,
        "gap_seconds": args.gap_seconds, "start_utc": stamp,
        "workspace": _active_workspace(),
        "logs": {}, "runs": [], "warmup_runs": [],
    }
    manifest_path = ARM_ROOT / f"{args.arm}_{stamp}.json"
    start_unix = time.time()

    def _run_bat(bat: str, cap_s: int) -> tuple[int, float, Path | None]:
        log_path = ARM_ROOT / f"{args.arm}_{'deploy' if bat.startswith('deploy') else 'run'}_{int(time.time())}.log"
        before = time.time()
        env_run = dict(env)
        env_run["V2_BENCHMARK_RUNS"] = "1"
        env_run["V2_BENCHMARK_GAP_SECONDS"] = "0"
        if bat.startswith("deploy"):
            env_run["COMFYMODAL_DEPLOY_ONLY"] = "1"
        rc, elapsed = _run_capped(["cmd", "/c", f".\\{bat}"], log_path, cap_s, env_run)
        new_dir = _newest_run_dir(before - 1) if not bat.startswith("deploy") else None
        return rc, elapsed, new_dir

    try:
        # -- deploy ---------------------------------------------------------
        if args.phase in (None, "deploy") and not args.skip_deploy:
            rc, elapsed, _ = _run_bat("deploy_and_run_v2_single.bat", cap_s=2400)
            manifest["deploy"] = {"exit": rc, "elapsed_s": round(elapsed, 1)}
            if rc != 0:
                manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
                print(f"[arm] DEPLOY FAILED exit={rc}", flush=True)
                return rc

        # -- warmup ---------------------------------------------------------
        if args.phase in (None, "warmup") and not args.skip_warmup:
            warm_ok = 0
            for i in range(args.warmup):
                rc, elapsed, new_dir = _run_bat(
                    "run_v2_single.bat", cap_s=args.per_run_cap_seconds + 120,
                )
                rec: dict[str, Any] = {
                    "index": i, "exit": rc, "elapsed_s": round(elapsed, 1),
                    "run_dir": str(new_dir) if new_dir else None,
                }
                if rc == 0 and new_dir is not None:
                    rec["status"] = "ok"
                    warm_ok += 1
                elif rc == DNF_EXIT:
                    rec["status"] = "dnf"
                else:
                    rec["status"] = "failed"
                manifest["warmup_runs"].append(rec)
            manifest["warmup"] = {"ok": warm_ok, "total": args.warmup}
            if warm_ok == 0:
                manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
                print("[arm] WARMUP: no warmup run completed; snapshot may not exist", flush=True)

        # -- measured -------------------------------------------------------
        if args.phase in (None, "measured"):
            valid = 0
            dnf = 0
            failed = 0
            for i in range(args.runs):
                if valid >= args.min_valid:
                    manifest["runs"].append({
                        "index": i, "status": "skipped_min_valid_met",
                    })
                    continue
                rc, elapsed, new_dir = _run_bat(
                    "run_v2_single.bat", cap_s=args.per_run_cap_seconds + 120,
                )
                rec: dict[str, Any] = {
                    "index": i, "exit": rc, "elapsed_s": round(elapsed, 1),
                    "run_dir": str(new_dir) if new_dir else None,
                }
                run_file = None
                if new_dir is not None:
                    cand = new_dir / "run_0.json"
                    if cand.exists():
                        run_file = str(cand)
                        rec["run_file"] = run_file
                if rc == DNF_EXIT:
                    rec["status"] = "dnf"
                    dnf += 1
                elif rc == 0 and run_file and _run_file_valid(Path(run_file)):
                    rec["status"] = "valid"
                    valid += 1
                else:
                    rec["status"] = "failed"
                    failed += 1
                manifest["runs"].append(rec)
                if args.gap_seconds and i < args.runs - 1 and valid < args.min_valid:
                    time.sleep(args.gap_seconds)
            manifest["measured"] = {
                "valid": valid, "dnf": dnf, "failed": failed,
                "requested": args.runs,
            }
            if valid < args.min_valid:
                print(
                    f"[arm] MEASURED: valid={valid} < min {args.min_valid} "
                    f"(dnf={dnf} failed={failed})",
                    flush=True,
                )
    except KeyboardInterrupt:
        print("[arm] interrupted", flush=True)
        manifest["interrupted"] = True
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        return 130

    manifest["end_utc"] = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"[arm] manifest={manifest_path}", flush=True)
    m = manifest.get("measured") or {}
    print(f"[arm] done. valid={m.get('valid')} dnf={m.get('dnf')} failed={m.get('failed')}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
