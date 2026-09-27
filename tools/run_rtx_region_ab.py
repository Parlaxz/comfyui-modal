"""Drive one arm of the two-arm RTX region A/B benchmark study.

Arm A: AWS only, region pinned to ``us-east-2``.
Arm B: AWS only, region unrestricted within AWS (no region pin).

Each arm deploys a dedicated variance-shadow Modal app with the cloud/region
pins, then runs the variance-cold sequence (7 requests: run_0 = post-deploy
snapshot-capture, EXCLUDED from measured results; runs 1-6 = measured true-cold
runs).

Placement is validated twice:
  1. at deploy time, from the ``[v2.region_pin]`` line the deploy prints;
  2. per-run, from the container-reported identity in each ``run_<i>.json``
     artifact (``identity.cloud`` / ``identity.region`` / ``identity.gpu`` /
     ``identity.cpu`` / ``identity.memory_mb``).

Only ``deploy_and_run_v2_single.bat`` and ``run_v2_single.bat`` are used for
deploy/run; the Modal CLI is never called directly here.

Usage:
    python tools/run_rtx_region_ab.py --arm A [--runs 7] [--gap-seconds 25]
        [--per-run-cap-seconds 900] [--skip-deploy]
        [--phase deploy|run|report] [--dry-run]
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DATA_ROOT = ROOT.parent.parent / "comfymodal-data" / "benchmarks"
RUNS_ROOT = DATA_ROOT / "runs"
ARM_ROOT = DATA_ROOT / "rtx_region_ab"

APP_NAME = "stable-modal-comfy-v2-variance-shadow"
GPU = "rtx-pro-6000"
CPU = 12
MEMORY_MB = 32768

DNF_EXIT = -999
DEPLOY_CAP_SECONDS = 2400
REGION_PIN_RE = re.compile(r"\[v2\.region_pin\]\s+region=(\S+)\s+cloud=(\S+)")

# Environment overrides shared by both arms (deploy AND run).
BASE_ENV: dict[str, str] = {
    "COMFYMODAL_V2_ENV_PROFILE": "production",
    "V2_BENCHMARK_MODE": "variance_cold",
    "COMFYMODAL_V2_GPU": GPU,
    "COMFYMODAL_V2_CPU_REQUEST": str(CPU),
    "COMFYMODAL_V2_MEMORY_REQUEST": str(MEMORY_MB),
    "COMFYMODAL_V2_MEMORY_MB": str(MEMORY_MB),
    "COMFYMODAL_V2_BASELINE_CPU_REQUEST": str(CPU),
    "COMFYMODAL_V2_BASELINE_MEMORY_REQUEST": str(MEMORY_MB),
    "COMFYMODAL_V2_CLOUD": "aws",
}

try:
    from tools.variance_report import extract_run_metrics, percentile
except Exception:  # pragma: no cover - helper import only
    extract_run_metrics = None
    percentile = None


def _num(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
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


def _normalize_cloud(cloud: str) -> str:
    c = (cloud or "").upper()
    if "AWS" in c:
        return "aws"
    if "GCP" in c:
        return "gcp"
    return (cloud or "").lower()


def _gpu_list(gpu: Any) -> list[str]:
    if isinstance(gpu, list):
        return [str(g) for g in gpu]
    if isinstance(gpu, str) and gpu:
        return [gpu]
    return []


def _has_verified_deploy(arm: str) -> bool:
    """Return True if any prior ``{arm}_*/manifest.json`` records a verified deploy.

    Used to gate ``--skip-deploy`` / ``--phase run|report`` so a resumed run or
    report never reuses a deployment that belongs to the other arm (both arms
    share the same app name).
    """
    if not ARM_ROOT.exists():
        return False
    for d in ARM_ROOT.iterdir():
        if not d.is_dir() or not d.name.startswith(f"{arm}_"):
            continue
        mf = d / "manifest.json"
        if not mf.exists():
            continue
        try:
            data = json.loads(mf.read_text(encoding="utf-8"))
        except Exception:
            continue
        deploy = data.get("deploy")
        if isinstance(deploy, dict) and deploy.get("verified") is True:
            return True
    return False


def _active_workspace() -> dict[str, str]:
    try:
        ws_file = ROOT / ".modal_workspaces.json"
        data = json.loads(ws_file.read_text(encoding="utf-8"))
        active_id = data.get("active_workspace_id")
        for ws in data.get("workspaces", []):
            if ws.get("id") == active_id:
                return {"workspace_id": active_id, "label": ws.get("label", "")}
        return {"workspace_id": active_id, "label": ""}
    except Exception:
        return {"workspace_id": "", "label": ""}


def _run_capped(cmd: list[str], log_path: Path, cap_s: int, env: dict[str, str]) -> tuple[int, float]:
    """Run a command with a hard wall cap; kills the process tree on timeout.

    Returns (exit_code, elapsed_s).  ``DNF_EXIT`` marks a timeout kill.
    """
    log_path.parent.mkdir(parents=True, exist_ok=True)
    started = time.time()
    with open(log_path, "w", encoding="utf-8") as log_fh:
        print(f"[ab] running: {' '.join(cmd)} (cap {cap_s}s)", flush=True)
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
            print(f"[ab] spawn error: {type(exc).__name__}: {exc}", flush=True)
            rc = DNF_EXIT
    elapsed = time.time() - started
    status = "dnf" if rc == DNF_EXIT else f"exit={rc}"
    print(f"[ab] result={status} elapsed={elapsed:.1f}s log={log_path}", flush=True)
    return rc, elapsed


def _parse_region_pin(log_path: Path) -> dict[str, str]:
    """Return {'region': ..., 'cloud': ...} parsed from the deploy log, or {}."""
    try:
        text = log_path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return {}
    for line in text.splitlines():
        m = REGION_PIN_RE.search(line)
        if m:
            return {"region": m.group(1), "cloud": m.group(2)}
    return {}


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


def _load_run_artifact(run_file: Path) -> dict[str, Any] | None:
    try:
        data = json.loads(run_file.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def _normalized_record(artifact: dict[str, Any]) -> dict[str, Any]:
    if extract_run_metrics is not None:
        try:
            rec = extract_run_metrics(artifact)
            return rec if isinstance(rec, dict) else {}
        except Exception:
            return {}
    return {}


def _report_metrics(rec: dict[str, Any]) -> dict[str, float | None]:
    """Extract the report metrics from a normalized variance record."""
    metrics = rec.get("metrics", {}) if isinstance(rec.get("metrics"), dict) else {}
    restore = metrics.get("restore", {}) or {}
    page = metrics.get("page_traversal", {}) or {}
    sampler = metrics.get("sampler", {}) or {}
    transfer = metrics.get("transfer", {}) or {}

    def _f(value: Any) -> float | None:
        return _num(value)

    py_to_result_parts = [
        _f(transfer.get("remote_python_resume_to_restore_start_ms")),
        _f(transfer.get("restore_to_method_entry_ms")),
        _f(transfer.get("first_remote_event_to_final_result_ms")),
    ]
    py_to_result = sum(0.0 if v is None else v for v in py_to_result_parts)

    return {
        "restore_ms": _f(restore.get("restore_total_ms")),
        "unet_activation_ms": _f(page.get("activation_total_ms")),
        "sampler_wait_ms": _f(sampler.get("sampler_lane_wait_ms")),
        "sampling_ms": _f(sampler.get("sampling_ms")),
        "py_to_result_ms": round(py_to_result, 3),
        "scheduling_ms": _f(transfer.get("pre_python_modal_scheduling_ms")),
        "wall_ms": _f(transfer.get("wall_ms")),
    }


def _validate_snapshot_capture(artifact: dict[str, Any], arm: str) -> dict[str, Any]:
    """Validate placement of the run_0 snapshot-capture request.

    The capture determines where the restored snapshot content was
    preloaded, so its placement is part of the arm contract even though its
    timing is excluded from measured stats.  Placement-only checks (no
    cold/registry/gpu requirements — run_0 legitimately lacks a CPU
    storage registry proof)."""
    result: dict[str, Any] = {"index": 0, "status": "ok", "failures": []}
    identity = artifact.get("identity", {}) if isinstance(artifact.get("identity"), dict) else {}
    cloud_raw = str(identity.get("cloud", ""))
    region_raw = str(identity.get("region", ""))
    cloud = _normalize_cloud(cloud_raw)
    result["cloud_raw"] = cloud_raw
    result["region_raw"] = region_raw
    result["cloud"] = cloud
    result["region"] = region_raw
    if cloud != "aws":
        result["status"] = "failed"
        result["failures"].append(f"snapshot-capture cloud mismatch: {cloud_raw!r} -> {cloud!r}")
    if arm == "A":
        if region_raw != "us-east-2":
            result["status"] = "failed"
            result["failures"].append(
                f"arm A snapshot-capture region mismatch: {region_raw!r} (expected us-east-2)"
            )
    else:
        if not region_raw:
            result["status"] = "failed"
            result["failures"].append("arm B snapshot-capture region empty")
        elif "GCP" in region_raw.upper():
            result["status"] = "failed"
            result["failures"].append(f"arm B snapshot-capture region contains GCP: {region_raw!r}")
    return result


def _validate_run(artifact: dict[str, Any], index: int, arm: str) -> dict[str, Any]:
    """Validate one measured run artifact. Returns a result dict (never raises)."""
    result: dict[str, Any] = {"index": index, "status": "ok", "failures": []}

    if artifact.get("error"):
        result["status"] = "failed"
        result["failures"].append("artifact error key present")

    variance = artifact.get("variance", {}) if isinstance(artifact.get("variance"), dict) else {}
    if variance.get("cold") is not True:
        result["status"] = "failed"
        result["failures"].append("variance.cold != True")
    if variance.get("cold_valid") is not True:
        result["status"] = "failed"
        result["failures"].append("variance.cold_valid != True")

    identity = artifact.get("identity", {}) if isinstance(artifact.get("identity"), dict) else {}
    cloud_raw = str(identity.get("cloud", ""))
    region_raw = str(identity.get("region", ""))
    cloud = _normalize_cloud(cloud_raw)
    result["cloud_raw"] = cloud_raw
    result["region_raw"] = region_raw
    result["cloud"] = cloud
    result["region"] = region_raw

    if cloud != "aws":
        result["status"] = "failed"
        result["failures"].append(f"cloud mismatch: {cloud_raw!r} -> {cloud!r}")

    if arm == "A":
        if region_raw != "us-east-2":
            result["status"] = "failed"
            result["failures"].append(f"arm A region mismatch: {region_raw!r} (expected us-east-2)")
    else:
        if not region_raw:
            result["status"] = "failed"
            result["failures"].append("arm B region empty")
        elif "GCP" in region_raw.upper():
            result["status"] = "failed"
            result["failures"].append(f"arm B region contains GCP: {region_raw!r}")

    gpus = _gpu_list(identity.get("gpu"))
    result["gpu"] = gpus
    if not any("RTX-PRO-6000" == str(g).upper() for g in gpus):
        result["status"] = "failed"
        result["failures"].append(f"gpu mismatch: {gpus!r} (expected RTX-PRO-6000)")

    cpu = _num(identity.get("cpu"))
    mem = _num(identity.get("memory_mb"))
    result["cpu"] = cpu
    result["memory_mb"] = mem
    if cpu != CPU:
        result["status"] = "failed"
        result["failures"].append(f"cpu mismatch: {identity.get('cpu')!r} (expected {CPU})")
    if mem != MEMORY_MB:
        result["status"] = "failed"
        result["failures"].append(f"memory_mb mismatch: {identity.get('memory_mb')!r} (expected {MEMORY_MB})")

    rec = _normalized_record(artifact)
    mv = rec.get("measurement_validity", {}) if isinstance(rec.get("measurement_validity"), dict) else {}
    registry_valid = mv.get("registry_valid")
    result["registry_valid"] = registry_valid
    if registry_valid is not True:
        result["status"] = "failed"
        result["failures"].append(
            f"registry_valid != True (registry_reason={mv.get('registry_reason', '?')})"
        )

    result["metrics"] = _report_metrics(rec)
    return result


def _fmt_ms(value: Any) -> str:
    n = _num(value)
    return "unavailable" if n is None else f"{n:,.3f}"


def _write_manifest(path: Path, manifest: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, indent=2, default=str), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--arm", required=True, choices=["A", "B"])
    parser.add_argument("--runs", type=int, default=7)
    parser.add_argument("--gap-seconds", type=int, default=25)
    # Prior worst client-observed single run was 824.7s; 900s left only ~9%
    # headroom, so default to 1200s per run.
    parser.add_argument("--per-run-cap-seconds", type=int, default=1200)
    parser.add_argument("--skip-deploy", action="store_true")
    parser.add_argument("--phase", choices=["deploy", "run", "report"], default=None)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    # Guard escape hatches against cross-arm deployment reuse.  Both arms share
    # the same app name, so a --skip-deploy / --phase run|report must only proceed
    # if THIS arm already has a verified deploy manifest.  dry-run is exempt.
    if not args.dry_run and (args.skip_deploy or args.phase in ("run", "report")):
        if not _has_verified_deploy(args.arm):
            print(
                f"[ab] ERROR: --skip-deploy/--phase requires a prior verified deploy "
                f"manifest for arm {args.arm}; refusing (both arms share the same app name)",
                flush=True,
            )
            return 2

    if args.runs < 2:
        print(f"[ab] ERROR: --runs must be >= 2 (run_0 snapshot excluded; need >=1 measured)", flush=True)
        return 2

    arm = args.arm
    cloud_pin = "aws"
    region_pin = "us-east-2" if arm == "A" else None

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    arm_dir = ARM_ROOT / f"{arm}_{stamp}"
    arm_dir.mkdir(parents=True, exist_ok=True)

    manifest: dict[str, Any] = {
        "arm": arm,
        "app_name": APP_NAME,
        "gpu": GPU,
        "cpu": CPU,
        "memory_mb": MEMORY_MB,
        "cloud_pin": cloud_pin,
        "region_pin": region_pin,
        "runs_requested": args.runs,
        "measured_runs_expected": args.runs - 1,
        "gap_seconds": args.gap_seconds,
        "per_run_cap_seconds": args.per_run_cap_seconds,
        "start_utc": stamp,
        "workspace": _active_workspace(),
        "deploy": None,
        "run": None,
        "runs": [],
        "measured_summary": None,
    }
    manifest_path = arm_dir / "manifest.json"

    # Build the per-arm env (deploy).  Arm B explicitly removes any inherited pin.
    env_deploy = dict(os.environ)
    env_deploy.update(BASE_ENV)
    env_deploy.update({
        "V2_VARIANCE_COLD_GAP_SECONDS": str(args.gap_seconds),
        "COMFYMODAL_DEPLOY_ONLY": "1",
    })
    if arm == "A":
        env_deploy["COMFYMODAL_V2_REGION"] = "us-east-2"
    else:
        env_deploy.pop("COMFYMODAL_V2_REGION", None)

    deploy_log = arm_dir / "deploy.log"
    run_log = arm_dir / "run.log"
    overall_ok = True
    failures: list[str] = []

    # ── Phase: deploy ────────────────────────────────────────────────
    if args.phase in (None, "deploy") and not args.skip_deploy:
        if args.dry_run:
            print(f"[ab][dry-run] would deploy: cmd /c .\\deploy_and_run_v2_single.bat")
            print(f"[ab][dry-run] env: COMFYMODAL_V2_CLOUD={env_deploy.get('COMFYMODAL_V2_CLOUD')} "
                  f"COMFYMODAL_V2_REGION={env_deploy.get('COMFYMODAL_V2_REGION', '<unset>')} "
                  f"COMFYMODAL_V2_ENV_PROFILE={env_deploy.get('COMFYMODAL_V2_ENV_PROFILE')}")
            print(f"[ab][dry-run] region_pin expectation: cloud=aws region={region_pin or 'unpinned'}")
        else:
            deploy_start = time.time()
            rc, elapsed = _run_capped(
                ["cmd", "/c", ".\\deploy_and_run_v2_single.bat"],
                deploy_log, DEPLOY_CAP_SECONDS, env_deploy,
            )
            pin = _parse_region_pin(deploy_log)
            deploy_verified = False
            deploy_fail = None
            if rc != 0:
                deploy_fail = f"deploy exit={rc} != 0"
            else:
                if not pin:
                    deploy_fail = "deploy log missing [v2.region_pin] line"
                else:
                    got_cloud = _normalize_cloud(pin.get("cloud", ""))
                    got_region = pin.get("region", "")
                    if got_cloud != "aws":
                        deploy_fail = f"deploy cloud mismatch: {pin.get('cloud')!r} -> {got_cloud!r}"
                    elif arm == "A" and got_region != "us-east-2":
                        deploy_fail = f"arm A region pin mismatch: {got_region!r} (expected us-east-2)"
                    elif arm == "B" and got_region != "unpinned":
                        deploy_fail = f"arm B region should be unpinned, got {got_region!r}"
                    else:
                        deploy_verified = True
            manifest["deploy"] = {
                "exit": rc,
                "elapsed_s": round(elapsed, 1),
                "region_pin_line": pin,
                "verified": deploy_verified,
                "error": deploy_fail,
            }
            _write_manifest(manifest_path, manifest)
            print(
                f"[ab] deploy verified={deploy_verified} "
                f"pin={pin if pin else 'MISSING'} "
                f"error={deploy_fail}",
                flush=True,
            )
            print(
                "[ab] notice: per-run placement will be validated from container-reported "
                "identity (identity.cloud / identity.region) in each run artifact.",
                flush=True,
            )
            if deploy_fail:
                print(f"[ab] FAIL deploy: {deploy_fail}", flush=True)
                overall_ok = False
                failures.append(deploy_fail)
                manifest["status"] = "failed"
                manifest["end_utc"] = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
                _write_manifest(manifest_path, manifest)
                print(f"[ab] manifest={manifest_path}", flush=True)
                print("[ab] FAIL: deploy not verified; refusing to run paid benchmark", flush=True)
                return 1
    elif args.skip_deploy:
        print("[ab] --skip-deploy: skipping deploy phase", flush=True)
    elif args.phase == "deploy" and args.dry_run:
        pass

    # ── Phase: run ───────────────────────────────────────────────────
    run_start_unix = time.time()
    run_dir: Path | None = None
    if args.phase in (None, "run"):
        env_run = dict(env_deploy)
        env_run.pop("COMFYMODAL_DEPLOY_ONLY", None)
        env_run["V2_VARIANCE_RUN_COUNT"] = str(args.runs)
        env_run["V2_BENCHMARK_RUNS"] = str(args.runs)

        if args.dry_run:
            print(f"[ab][dry-run] would run: cmd /c .\\run_v2_single.bat")
            print(f"[ab][dry-run] env: V2_BENCHMARK_MODE={env_run.get('V2_BENCHMARK_MODE')} "
                  f"V2_VARIANCE_RUN_COUNT={env_run.get('V2_VARIANCE_RUN_COUNT')} "
                  f"V2_VARIANCE_COLD_GAP_SECONDS={env_run.get('V2_VARIANCE_COLD_GAP_SECONDS')}")
        else:
            cap = args.per_run_cap_seconds * args.runs + 120
            rc, elapsed = _run_capped(
                ["cmd", "/c", ".\\run_v2_single.bat"], run_log, cap, env_run,
            )
            new_dir = _newest_run_dir(run_start_unix)
            run_dir = new_dir
            manifest["run"] = {
                "exit": rc,
                "elapsed_s": round(elapsed, 1),
                "output_dir": str(new_dir) if new_dir else None,
                "cap_seconds": cap,
            }
            _write_manifest(manifest_path, manifest)
            if rc != 0:
                print(f"[ab] FAIL run: exit={rc} (artifacts preserved at {new_dir})", flush=True)
                overall_ok = False
                failures.append(f"run exit={rc} != 0")
            elif new_dir is None:
                print("[ab] FAIL run: no v2_* runs directory produced", flush=True)
                overall_ok = False
                failures.append("no runs output directory produced")

    # ── Phase: report/validate ──────────────────────────────────────
    measured_runs: list[dict[str, Any]] = []
    if args.phase in (None, "report"):
        if args.dry_run:
            print(
                f"[ab][dry-run] would validate run_1.json..run_{args.runs-1}.json "
                f"(run_0 snapshot EXCLUDED); arm={arm} region_pin={region_pin or 'unpinned'}",
                flush=True,
            )
        else:
            target_dir = run_dir
            if target_dir is None:
                target_dir = _newest_run_dir(run_start_unix - 1)
            if target_dir is None:
                print("[ab] FAIL report: no runs output directory to validate", flush=True)
                overall_ok = False
                failures.append("no runs output directory to validate")
            else:
                print(f"[ab] validating runs in {target_dir}", flush=True)
                all_ok = True

                # run_0 snapshot-capture placement validation (placement only).
                run_0_file = target_dir / "run_0.json"
                if not run_0_file.exists():
                    manifest["run_0_snapshot_capture"] = {
                        "index": 0, "status": "failed",
                        "failures": ["run_0.json missing"],
                    }
                    all_ok = False
                    overall_ok = False
                    failures.append("run_0.json missing")
                    print("[ab] run_0 (snapshot capture): failed (run_0.json missing)", flush=True)
                else:
                    run_0_artifact = _load_run_artifact(run_0_file)
                    if run_0_artifact is None:
                        manifest["run_0_snapshot_capture"] = {
                            "index": 0, "status": "failed",
                            "failures": ["run_0.json unparseable"],
                        }
                        all_ok = False
                        overall_ok = False
                        failures.append("run_0.json unparseable")
                        print("[ab] run_0 (snapshot capture): failed (unparseable)", flush=True)
                    else:
                        snap_rec = _validate_snapshot_capture(run_0_artifact, arm)
                        manifest["run_0_snapshot_capture"] = snap_rec
                        if snap_rec["status"] != "ok":
                            all_ok = False
                            overall_ok = False
                            failures.append(
                                "run_0 snapshot capture failed: "
                                + "; ".join(snap_rec["failures"])
                            )
                        print(
                            f"[ab] run_0 (snapshot capture): {snap_rec['status']} "
                            f"cloud={snap_rec.get('cloud')} region={snap_rec.get('region_raw')}",
                            flush=True,
                        )

                for index in range(1, args.runs):
                    run_file = target_dir / f"run_{index}.json"
                    if not run_file.exists():
                        rec = {
                            "index": index, "status": "failed",
                            "failures": [f"run_{index}.json missing"],
                        }
                        measured_runs.append(rec)
                        all_ok = False
                        overall_ok = False
                        failures.append(f"run_{index}.json missing")
                        continue
                    artifact = _load_run_artifact(run_file)
                    if artifact is None:
                        rec = {
                            "index": index, "status": "failed",
                            "failures": ["run artifact unparseable"],
                        }
                        measured_runs.append(rec)
                        all_ok = False
                        overall_ok = False
                        failures.append(f"run_{index}.json unparseable")
                        continue
                    rec = _validate_run(artifact, index, arm)
                    measured_runs.append(rec)
                    if rec["status"] != "ok":
                        all_ok = False
                        overall_ok = False
                        failures.append(
                            f"run_{index} failed: {'; '.join(rec['failures'])}"
                        )
                    print(
                        f"[ab] run_{index}: {rec['status']} "
                        f"cloud={rec.get('cloud')} region={rec.get('region_raw')} "
                        f"gpu={rec.get('gpu')} cpu={rec.get('cpu')} mem={rec.get('memory_mb')} "
                        f"registry={rec.get('registry_valid')}",
                        flush=True,
                    )
                manifest["runs"] = measured_runs

                # Measured summary stats (p50/min/max over measured runs).
                ok_runs = [r for r in measured_runs if r["status"] == "ok"]
                summary_stats: dict[str, Any] = {}
                for metric_key in (
                    "restore_ms", "unet_activation_ms", "sampler_wait_ms",
                    "sampling_ms", "py_to_result_ms", "scheduling_ms", "wall_ms",
                ):
                    values: list[float] = [
                        v for v in (
                            _num(r.get("metrics", {}).get(metric_key)) for r in ok_runs
                        ) if v is not None
                    ]
                    values.sort()
                    if percentile is not None and values:
                        _p50 = percentile(values, 50)
                        summary_stats[metric_key] = {
                            "p50": round(_p50, 3) if _p50 is not None else None,
                            "min": round(min(values), 3),
                            "max": round(max(values), 3),
                        }
                    else:
                        summary_stats[metric_key] = {
                            "p50": None, "min": None, "max": None,
                        }
                manifest["measured_summary"] = {
                    "valid_runs": len(ok_runs),
                    "total_measured": len(measured_runs),
                    "all_valid": all_ok,
                    "stats": summary_stats,
                }
                _write_manifest(manifest_path, manifest)
                _write_report(arm_dir, manifest, measured_runs, summary_stats)

    # ── Final status ─────────────────────────────────────────────────
    manifest["end_utc"] = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    manifest["status"] = "ok" if overall_ok else "failed"
    manifest["failures"] = failures
    _write_manifest(manifest_path, manifest)

    if args.dry_run:
        print("[ab][dry-run] done. No subprocesses were executed.", flush=True)
        print(json.dumps({"arm": arm, "status": "dry-run",
                          "cloud_ok": True, "region_ok": True,
                          "measured_runs": args.runs - 1}, default=str), flush=True)
        return 0

    valid = sum(1 for r in measured_runs if r["status"] == "ok")
    cloud_ok = all(r.get("cloud") == "aws" for r in measured_runs)
    if arm == "A":
        region_ok = all(r.get("region_raw") == "us-east-2" for r in measured_runs)
    else:
        region_ok = all(
            (r.get("region_raw") or "") and "GCP" not in (r.get("region_raw") or "").upper()
            for r in measured_runs
        )

    result_line = {
        "arm": arm,
        "status": "ok" if overall_ok else "failed",
        "measured_runs": len(measured_runs),
        "valid_runs": valid,
        "cloud_ok": cloud_ok if measured_runs else False,
        "region_ok": region_ok if measured_runs else False,
        "deploy_verified": bool(manifest.get("deploy", {}).get("verified")),
    }
    print(json.dumps(result_line, default=str), flush=True)
    print(f"[ab] manifest={manifest_path}", flush=True)
    if not overall_ok:
        print("[ab] FAIL", flush=True)
        for f in failures:
            print(f"  - {f}", flush=True)
        return 1
    print("[ab] OK", flush=True)
    return 0


def _write_report(arm_dir: Path, manifest: dict[str, Any], measured_runs: list[dict[str, Any]],
                  summary_stats: dict[str, Any]) -> None:
    lines: list[str] = []
    lines.append(f"# RTX Region A/B — Arm {manifest['arm']} Report")
    lines.append("")
    lines.append(f"- App: `{manifest['app_name']}`")
    lines.append(f"- GPU: `{manifest['gpu']}` · CPU: `{manifest['cpu']}` · Memory: `{manifest['memory_mb']} MiB`")
    lines.append(f"- Cloud pin: `{manifest['cloud_pin']}` · Region pin: `{manifest['region_pin'] or 'unpinned'}`")
    lines.append(f"- Measured runs: `{len(measured_runs)}` (run_0 snapshot EXCLUDED)")
    lines.append("")
    lines.append("## Per-run results")
    lines.append("")
    lines.append("| run | cloud | region | restore ms | UNET activation/load ms | "
                 "sampler wait ms | sampling ms | Python→result ms | scheduling ms | "
                 "total wall ms | status |")
    lines.append("|---|---|---|---|---|---|---|---|---|---|---|")
    for r in measured_runs:
        m = r.get("metrics", {}) or {}
        lines.append(
            f"| {r.get('index')} | {r.get('cloud')} | {r.get('region_raw')} "
            f"| {_fmt_ms(m.get('restore_ms'))} | {_fmt_ms(m.get('unet_activation_ms'))} "
            f"| {_fmt_ms(m.get('sampler_wait_ms'))} | {_fmt_ms(m.get('sampling_ms'))} "
            f"| {_fmt_ms(m.get('py_to_result_ms'))} | {_fmt_ms(m.get('scheduling_ms'))} "
            f"| {_fmt_ms(m.get('wall_ms'))} | {r.get('status')} |"
        )
    lines.append("")
    lines.append("## Summary (measured runs)")
    lines.append("")
    lines.append("| metric | p50 | min | max |")
    lines.append("|---|---:|---:|---:|")
    for metric_key, label in (
        ("restore_ms", "restore ms"),
        ("unet_activation_ms", "UNET activation/load ms"),
        ("sampler_wait_ms", "sampler wait ms"),
        ("sampling_ms", "sampling ms"),
        ("py_to_result_ms", "Python→result ms"),
        ("scheduling_ms", "scheduling ms"),
        ("wall_ms", "total wall ms"),
    ):
        s = summary_stats.get(metric_key, {})
        lines.append(
            f"| {label} | {_fmt_ms(s.get('p50'))} | {_fmt_ms(s.get('min'))} "
            f"| {_fmt_ms(s.get('max'))} |"
        )
    lines.append("")
    report_path = arm_dir / "report.md"
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
