"""Run one resource/GPU experiment arm end-to-end.

Deploys a dedicated app with the arm's CPU/RAM/GPU request, runs the
excluded warmup pair, then the measured true-cold generations, and writes
an arm manifest (artifact dirs, app identity, logs) under
``comfymodal-data/benchmarks/resource_experiments/``.

Usage:
    python tools/run_resource_arm.py ^
        --arm ram28 --gpu rtx-pro-6000 --cpu 16 --memory 28672 ^
        --runs 4 --warmup 2 --gap-seconds 20

Env overrides pass through to the deploy/run bats (which only set
defaults when a variable is undefined), so the production env profile is
preserved and experiment arms stay on their own app identities.

Measured runs are strictly sequential (single-use containers, one request
per run, gap between runs) so the experiments do not create artificial
scheduling contention.
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


def _run(cmd: list[str], log_path: Path, timeout_s: int, env: dict[str, str]) -> int:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with open(log_path, "w", encoding="utf-8") as log_fh:
        print(f"[arm] running: {' '.join(cmd)} (timeout {timeout_s}s)", flush=True)
        proc = subprocess.run(
            cmd, cwd=str(ROOT), env=env, stdout=log_fh, stderr=subprocess.STDOUT,
            timeout=timeout_s,
        )
        log_fh.flush()
        print(f"[arm] exit={proc.returncode} log={log_path}", flush=True)
        return proc.returncode


def _newest_run_dirs(after_unix_s: float) -> list[Path]:
    if not RUNS_ROOT.exists():
        return []
    dirs = [
        p for p in RUNS_ROOT.iterdir()
        if p.is_dir() and p.name.startswith("v2_")
        and p.stat().st_mtime >= after_unix_s - 5
    ]
    return sorted(dirs, key=lambda p: p.stat().st_mtime)


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
    parser.add_argument("--arm", required=True, help="arm id, e.g. ram28 / cpu4 / a100-80")
    parser.add_argument("--gpu", default="rtx-pro-6000")
    parser.add_argument("--cpu", type=int, default=16)
    parser.add_argument("--memory", type=int, default=49152)
    parser.add_argument("--runs", type=int, default=4)
    parser.add_argument("--warmup", type=int, default=2)
    parser.add_argument("--gap-seconds", type=int, default=20)
    parser.add_argument("--skip-deploy", action="store_true")
    parser.add_argument("--phase", choices=["deploy", "warmup", "measured"], default=None,
                        help="run only one phase (default: all)")
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
        "gap_seconds": args.gap_seconds, "start_utc": stamp,
        "workspace": _active_workspace(),
        "logs": {}, "warmup_dir": None, "measured_dir": None,
    }
    manifest_path = ARM_ROOT / f"{args.arm}_{stamp}.json"

    start_unix = time.time()

    def _phase(phase: str, runs: int, deploy_only: bool) -> int:
        ph_env = dict(env)
        ph_env["V2_BENCHMARK_RUNS"] = str(runs)
        ph_env["V2_BENCHMARK_GAP_SECONDS"] = str(args.gap_seconds)
        if deploy_only:
            ph_env["COMFYMODAL_DEPLOY_ONLY"] = "1"
        log_path = ARM_ROOT / f"{args.arm}_{phase}.log"
        manifest["logs"][phase] = str(log_path)
        cmd = ["cmd", "/c", ".\\deploy_and_run_v2_single.bat" if deploy_only else ".\\run_v2_single.bat"]
        return _run(cmd, log_path, timeout_s=2400, env=ph_env)

    try:
        if args.phase in (None, "deploy") and not args.skip_deploy:
            rc = _phase("deploy", 1, deploy_only=True)
            if rc != 0:
                manifest["deploy_exit"] = rc
                manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
                print(f"[arm] DEPLOY FAILED exit={rc}", flush=True)
                return rc
            manifest["deploy_exit"] = 0

        if args.phase in (None, "warmup"):
            rc = _phase("warmup", args.warmup, deploy_only=False)
            if rc != 0:
                manifest["warmup_exit"] = rc
                manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
                print(f"[arm] WARMUP FAILED exit={rc}", flush=True)
                return rc
            manifest["warmup_exit"] = 0
            after = time.time()
            dirs = _newest_run_dirs(start_unix)
            manifest["warmup_candidates"] = [str(p) for p in dirs]

        if args.phase in (None, "measured"):
            rc = _phase("measured", args.runs, deploy_only=False)
            if rc != 0:
                manifest["measured_exit"] = rc
                manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
                print(f"[arm] MEASURED FAILED exit={rc}", flush=True)
                return rc
            manifest["measured_exit"] = 0
            dirs = _newest_run_dirs(start_unix)
            manifest["run_dirs"] = [str(p) for p in dirs]
            # Warmup dirs = all run dirs before the last one (measured writes last).
            if len(dirs) >= 2:
                manifest["warmup_dir"] = str(dirs[-2])
                manifest["measured_dir"] = str(dirs[-1])
            elif dirs:
                manifest["measured_dir"] = str(dirs[-1])
    except subprocess.TimeoutExpired:
        print("[arm] TIMEOUT during arm execution", flush=True)
        manifest["timeout"] = True
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        return 2

    manifest["end_utc"] = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"[arm] manifest={manifest_path}", flush=True)
    print(f"[arm] done. measured_dir={manifest.get('measured_dir')}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
