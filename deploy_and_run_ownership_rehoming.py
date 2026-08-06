"""Deploy the ownership + post-restore rehoming shadow apps and run the study.

Apps (all shadow-only, never production):

  stable-modal-comfy-v2-ownership-gcp-probes-shadow    GCP pin, exclusive UNET
                                                       owner ON, page-path
                                                       probes ON (Experiment 1
                                                       arm A)
  stable-modal-comfy-v2-ownership-gcp-noprobes-shadow  GCP pin, exclusive UNET
                                                       owner ON, probes OFF
                                                       (Experiment 1 arm B)
  stable-modal-comfy-v2-rehoming-shadow                GCP pin, rehoming
                                                       shadow method only
                                                       (Experiment 2)
  stable-modal-comfy-v2-rehome-integrated-shadow       UNPINNED, exclusive
                                                       owner + post-restore
                                                       rehoming, all heavy
                                                       diagnostics OFF
                                                       (Experiment 3)
  stable-modal-comfy-v2-exclusive-owner-total-wall     UNPINNED, exclusive UNET
                                                       owner ON, rehoming OFF,
                                                       every page-path/synth
                                                       H2D/backing-verify/
                                                       pretouch/quiesced/
                                                       variance/host/full-trace
                                                       diagnostic OFF
                                                       (six-run total-wall
                                                       validation)

Usage:
    python deploy_and_run_ownership_rehoming.py [--deploy-only]
    python deploy_and_run_ownership_rehoming.py ownership --phase probes_on [target_cold]
    python deploy_and_run_ownership_rehoming.py rehoming [runs]
    python deploy_and_run_ownership_rehoming.py integrated [target_cold]
    python deploy_and_run_ownership_rehoming.py total-wall [target_cold] [--deploy-only]
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
APP_OWNERSHIP_PROBES = "stable-modal-comfy-v2-ownership-gcp-probes-shadow"
APP_OWNERSHIP_NOPROBES = "stable-modal-comfy-v2-ownership-gcp-noprobes-shadow"
APP_REHOMING = "stable-modal-comfy-v2-rehoming-shadow"
APP_INTEGRATED = "stable-modal-comfy-v2-rehome-integrated-shadow"
APP_TOTAL_WALL = "stable-modal-comfy-v2-exclusive-owner-total-wall"

ws = json.loads((ROOT / ".modal_workspaces.json").read_text(encoding="utf-8"))
aid = ws.get("active_workspace_id")
entry = next((w for w in ws.get("workspaces", []) if w.get("id") == aid), None)
if not entry or not entry.get("token_id") or not entry.get("token_secret"):
    print("ERROR: could not load workspace credentials")
    sys.exit(1)


def base_env(app_name: str, cloud: str = "") -> dict[str, str]:
    env = dict(os.environ)
    env.update({
        "MODAL_TOKEN_ID": str(entry["token_id"]),
        "MODAL_TOKEN_SECRET": str(entry["token_secret"]),
        "COMFYMODAL_V2_APP_NAME": app_name,
        "COMFYMODAL_V2_CLASS_NAME": "ModalRuntimeEntrypointV2",
        "COMFYMODAL_V2_GPU": "rtx-pro-6000",
        "COMFYMODAL_V2_ENV_PROFILE": "production",
        "COMFYMODAL_V2_FULL_TRACE": "0",
        "COMFYMODAL_V2_RESIDENCY_DIAGNOSTICS": "0",
        "COMFYMODAL_V2_DEEP_MODEL_DIAG": "0",
        "COMFYMODAL_V2_PAGEFAULT_TRACKING": "0",
        "COMFYMODAL_V2_EVICT_MODELS_BEFORE_SNAPSHOT": "0",
        "COMFYMODAL_V2_EVICT_RESTORE_IDLE_SECONDS": "0",
        "COMFYMODAL_V2_PREFILL_LANES": "critical",
        "COMFYMODAL_V2_PREFILL_WAIT_FOR_UNET": "0",
        "COMFYMODAL_V2_CPU_MODEL_SNAPSHOT": "1",
        "COMFYMODAL_V2_VAE_SNAPSHOT": "1",
        "COMFYMODAL_V2_CLIP_CONDITIONING_CACHE": "1",
        "COMFYMODAL_EXACT_CLIP_CONDITIONING_CACHE": "1",
        "COMFYMODAL_V2_UNET_ACTIVATION_MODE": "late",
        "COMFYMODAL_V2_VAE_ACTIVATION_MODE": "sampling_end",
        "COMFYMODAL_V2_PERSISTENT_LOCAL_HANDLE": "1",
        "COMFYMODAL_V2_THREAD_POLICY": "TBASE",
        "COMFYMODAL_V2_SNAPSHOT_MODEL_ORDER": "O0",
        "COMFYMODAL_V2_MEMORY_MB": "49152",
        "COMFYMODAL_V2_VAE_POLICY": "v1",
        "COMFYMODAL_V2_BASELINE_CPU_REQUEST": "16",
        "COMFYMODAL_V2_BASELINE_MEMORY_REQUEST": "49152",
        "COMFYMODAL_V2_RELEASE_GPU_AFTER_REQUEST": "1",
        "COMFYMODAL_V2_SINGLE_USE_CONTAINERS": "1",
        "COMFYMODAL_V2_VARIANCE_DIAGNOSTICS": "0",
        "COMFYMODAL_V2_HOST_DIAGNOSTICS": "0",
        "COMFYMODAL_V2_PAGE_PATH_PROBE": "0",
        "COMFYMODAL_V2_SYNTH_H2D_PROBE": "0",
        "COMFYMODAL_V2_UNET_BACKING_VERIFY": "0",
        "COMFYMODAL_V2_ANON_UNET_SNAPSHOT": "0",
        "COMFYMODAL_V2_UNET_EXCLUSIVE_OWNER": "0",
        "COMFYMODAL_V2_UNET_REHOME_AFTER_RESTORE": "0",
        "PYTHONIOENCODING": "utf-8",
        "PYTHONUTF8": "1",
    })
    if cloud:
        env["COMFYMODAL_V2_CLOUD"] = cloud
    return env


def deploy(app_name: str, *, cloud: str = "", extra: dict[str, str] | None = None) -> None:
    env = base_env(app_name, cloud)
    if extra:
        env.update(extra)
    prof = subprocess.run(
        [sys.executable, str(ROOT / "tools" / "extract_warmup_profile.py")],
        capture_output=True, text=True, cwd=str(ROOT), env=env,
    )
    if prof.returncode != 0:
        print("Warmup profile derivation failed:", prof.stderr)
        sys.exit(1)
    for line in prof.stdout.splitlines():
        if "=" in line:
            k, _, v = line.partition("=")
            env[k.strip()] = v.strip()
    print(f"=== Deploying {app_name} (cloud={cloud or 'unpinned'}) ===", flush=True)
    deploy_run = subprocess.run(
        ["modal", "deploy", "-m", "comfymodal_runtime.modal_app"],
        cwd=str(ROOT), env=env, text=True,
    )
    if deploy_run.returncode != 0:
        print(f"=== ERROR: deploy of {app_name} failed ===")
        sys.exit(deploy_run.returncode)
    print(f"=== Deploy verified OK: {app_name} ===", flush=True)


def run_study(mode: str, args: list[str], env_extra: dict[str, str]) -> None:
    env = dict(os.environ)
    env.update(env_extra)
    print(f"=== Running {mode} study ===", flush=True)
    bench = subprocess.run(
        [sys.executable, str(ROOT / "tools" / "run_ownership_rehoming_study.py"),
         mode] + args,
        cwd=str(ROOT), env=env, text=True,
    )
    if bench.returncode != 0:
        print(f"=== ERROR: {mode} study failed with exit code {bench.returncode} ===")
        sys.exit(bench.returncode)
    print(f"=== {mode} study completed successfully ===", flush=True)


def main() -> None:
    args = sys.argv[1:]
    if args and args[0] == "total-wall" and "--deploy-only" in args:
        deploy(APP_TOTAL_WALL, cloud="", extra={
            "COMFYMODAL_V2_UNET_EXCLUSIVE_OWNER": "1",
        })
        print("=== Total-wall deploy-only requested; study skipped ===")
        return
    if "--deploy-only" in args:
        deploy(APP_OWNERSHIP_PROBES, cloud="gcp", extra={
            "COMFYMODAL_V2_UNET_EXCLUSIVE_OWNER": "1",
            "COMFYMODAL_V2_VARIANCE_DIAGNOSTICS": "1",
            "COMFYMODAL_V2_HOST_DIAGNOSTICS": "1",
            "COMFYMODAL_V2_PAGE_PATH_PROBE": "1",
            "COMFYMODAL_V2_UNET_BACKING_VERIFY": "1",
        })
        deploy(APP_OWNERSHIP_NOPROBES, cloud="gcp", extra={
            "COMFYMODAL_V2_UNET_EXCLUSIVE_OWNER": "1",
            "COMFYMODAL_V2_VARIANCE_DIAGNOSTICS": "1",
            "COMFYMODAL_V2_HOST_DIAGNOSTICS": "1",
        })
        deploy(APP_REHOMING, cloud="gcp", extra={
            "COMFYMODAL_V2_HOST_DIAGNOSTICS": "1",
        })
        deploy(APP_INTEGRATED, cloud="", extra={
            "COMFYMODAL_V2_UNET_EXCLUSIVE_OWNER": "1",
            "COMFYMODAL_V2_UNET_REHOME_AFTER_RESTORE": "1",
        })
        print("=== Deploy-only requested; studies skipped ===")
        return
    if not args:
        print(__doc__)
        sys.exit(1)
    mode = args[0]
    rest = args[1:]
    if mode == "ownership":
        phase = rest[0] if rest and rest[0] in ("probes_on", "probes_off") else "probes_on"
        if phase in rest:
            rest.remove(phase)
        target = rest[0] if rest else "4"
        app = APP_OWNERSHIP_PROBES if phase == "probes_on" else APP_OWNERSHIP_NOPROBES
        env_extra = {
            "MODAL_TOKEN_ID": str(entry["token_id"]),
            "MODAL_TOKEN_SECRET": str(entry["token_secret"]),
            "COMFYMODAL_V2_APP_NAME": app,
            "COMFYMODAL_V2_GPU": "rtx-pro-6000",
            "COMFYMODAL_V2_ENV_PROFILE": "production",
            "V2_OWNERSHIP_GAP_SECONDS": "25",
        }
        run_study("ownership", ["--app", app, "--phase", phase, "--target-cold", target], env_extra)
    elif mode == "rehoming":
        runs = rest[0] if rest else "4"
        env_extra = {
            "MODAL_TOKEN_ID": str(entry["token_id"]),
            "MODAL_TOKEN_SECRET": str(entry["token_secret"]),
            "COMFYMODAL_V2_APP_NAME": APP_REHOMING,
            "COMFYMODAL_V2_GPU": "rtx-pro-6000",
            "COMFYMODAL_V2_ENV_PROFILE": "production",
            "V2_OWNERSHIP_GAP_SECONDS": "25",
        }
        run_study("rehoming", ["--app", APP_REHOMING, "--runs", runs], env_extra)
    if mode == "total-wall":
        deploy(APP_TOTAL_WALL, cloud="", extra={
            "COMFYMODAL_V2_UNET_EXCLUSIVE_OWNER": "1",
        })
        if "--deploy-only" in args:
            print("=== Total-wall deploy-only requested; study skipped ===")
            return
        env_extra = {
            "MODAL_TOKEN_ID": str(entry["token_id"]),
            "MODAL_TOKEN_SECRET": str(entry["token_secret"]),
            "COMFYMODAL_V2_APP_NAME": APP_TOTAL_WALL,
            "COMFYMODAL_V2_GPU": "rtx-pro-6000",
            "COMFYMODAL_V2_ENV_PROFILE": "production",
            "V2_OWNERSHIP_GAP_SECONDS": "25",
        }
        target = rest[0] if rest and rest[0].isdigit() else "6"
        run_study(
            "ownership",
            ["--app", APP_TOTAL_WALL, "--phase", "probes_off",
             "--target-cold", target, "--max-attempts", "9",
             "--skip-first", "2", "--report"],
            env_extra,
        )
    elif mode == "integrated":
        target = rest[0] if rest else "7"
        env_extra = {
            "MODAL_TOKEN_ID": str(entry["token_id"]),
            "MODAL_TOKEN_SECRET": str(entry["token_secret"]),
            "COMFYMODAL_V2_APP_NAME": APP_INTEGRATED,
            "COMFYMODAL_V2_GPU": "rtx-pro-6000",
            "COMFYMODAL_V2_ENV_PROFILE": "production",
            "V2_OWNERSHIP_GAP_SECONDS": "25",
        }
        run_study("integrated", ["--app", APP_INTEGRATED, "--target-cold", target], env_extra)
    else:
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
