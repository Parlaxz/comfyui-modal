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
    stable-modal-comfy-v2-shadow (restore mode)          THE LONG-LIVED shadow
                                                         app lineage from the
                                                         historical fast runs,
                                                         redeployed with
                                                         exclusive UNET owner ON
                                                         and all diagnostics OFF.
                                                         Restores the fast path
                                                         (platform entry ~0.2-0.4 s
                                                         vs 4.4-38.3 s on the new
                                                         six-run app lineage).
    stable-modal-comfy-v2-shadow (lean mode)             The same long-lived
                                                         shadow lineage with
                                                         lean snapshot ON
                                                         (COMFYMODAL_V2_LEAN_SNAPSHOT=1,
                                                         UNET-backing diagnostic
                                                         deferred from import
                                                         time), exclusive UNET
                                                         owner ON, all heavy
                                                         diagnostics OFF.  This
                                                         is the direct lean
                                                         production candidate
                                                         validated by
                                                         V2_LEAN_SNAPSHOT_DIRECT_
                                                         VALIDATION_REPORT.md.


Usage:
    python deploy_and_run_ownership_rehoming.py [--deploy-only]
    python deploy_and_run_ownership_rehoming.py ownership --phase probes_on [target_cold]
    python deploy_and_run_ownership_rehoming.py rehoming [runs]
    python deploy_and_run_ownership_rehoming.py integrated [target_cold]
    python deploy_and_run_ownership_rehoming.py total-wall [target_cold] [--deploy-only]
    python deploy_and_run_ownership_rehoming.py restore [gcp|aws|unpinned] [target_cold] [--deploy-only]
    python deploy_and_run_ownership_rehoming.py lean [gcp|aws|unpinned] [--deploy-only] [--no-deploy]
    python deploy_and_run_ownership_rehoming.py snapshot-ab [current|lean] [--region us-east4] [--no-deploy] [--deploy-only] [--manifest]
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
# Restore-mode shadow: the LONG-LIVED V2 shadow app lineage (first deployed
# 2026-07-26) that produced the historical 9.2-10.2 s total-wall runs before
# the ownership/rehoming studies.  Reusing the app identity preserves the
# snapshot/image distribution behavior that the six-run study's brand-new
# app lineage lost.
APP_RESTORE = "stable-modal-comfy-v2-shadow"

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
    if "--deploy-only" in args and (not args or args[0] not in ("total-wall", "snapshot-ab", "lean")):
        # Legacy no-mode --deploy-only: redeploys the four ownership study
        # apps.  total-wall / snapshot-ab / lean handle --deploy-only in
        # their own branches and must NOT be intercepted here.
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
    elif mode == "restore":
        # Restore mode: redeploy the LONG-LIVED shadow app lineage with
        # exclusive ownership ON and every heavy diagnostic OFF.  Placement is
        # controlled per step: gcp / aws cloud pin (optionally plus a region
        # pin) first, then unpinned for the final six-run validation.
        # ``--no-deploy`` re-runs the study against the existing deployment
        # (same image/snapshot lineage) without creating a new image —
        # required for fair repeated sampling.
        cloud = rest[0] if rest and rest[0] in ("gcp", "aws", "unpinned") else "gcp"
        if cloud in rest:
            rest.remove(cloud)
        if cloud == "unpinned":
            cloud = ""
        region = ""
        if rest and rest[0] == "--region":
            rest.pop(0)
            if rest:
                region = rest.pop(0)
        target = rest[0] if rest and rest[0].isdigit() else "3"
        if "--no-deploy" in args:
            print(f"=== Restore no-deploy: reusing existing {APP_RESTORE} deployment ===")
        else:
            deploy(APP_RESTORE, cloud=cloud, extra={
                "COMFYMODAL_V2_UNET_EXCLUSIVE_OWNER": "1",
                **({"COMFYMODAL_V2_REGION": region} if region else {}),
            })
        if "--deploy-only" in args:
            print("=== Restore deploy-only requested; study skipped ===")
            return
        env_extra = {
            "MODAL_TOKEN_ID": str(entry["token_id"]),
            "MODAL_TOKEN_SECRET": str(entry["token_secret"]),
            "COMFYMODAL_V2_APP_NAME": APP_RESTORE,
            "COMFYMODAL_V2_GPU": "rtx-pro-6000",
            "COMFYMODAL_V2_ENV_PROFILE": "production",
            "V2_OWNERSHIP_GAP_SECONDS": "25",
            "V2_OWNERSHIP_EXPECT_CLOUD": cloud,
            "V2_OWNERSHIP_ACCEPT_UNDER_MS": "13500",
        }
        study_args = [
            "--app", APP_RESTORE, "--phase", "probes_off",
            "--target-cold", target, "--max-attempts", "8",
            "--skip-first", "2", "--expect-cloud", cloud,
            "--accept-under-ms", "13500", "--stop-after-bad", "2",
            "--report",
        ]
        if region:
            study_args += ["--expect-region", region]
            env_extra["V2_OWNERSHIP_EXPECT_REGION"] = region
        run_study("ownership", study_args, env_extra)
    elif mode == "lean":
        # Lean production snapshot candidate: the long-lived shadow lineage
        # redeployed with the lean import gate ON (UNET-backing diagnostic
        # deferred from the import-time surface) + exclusive UNET owner ON
        # and every heavy diagnostic OFF.  One clean deployment; the study
        # then collects 6 valid cold single-use generations with 25 s gaps.
        # Region pins are NOT allowed for this candidate — placement is
        # left to Modal (cloud may be pinned to gcp/aws or left unpinned).
        # ``--no-deploy`` re-samples the same deployment (no new image).
        cloud = rest[0] if rest and rest[0] in ("gcp", "aws", "unpinned") else "gcp"
        if cloud in rest:
            rest.remove(cloud)
        if cloud == "unpinned":
            cloud = ""
        if "--no-deploy" in args:
            print(f"=== Lean no-deploy: reusing existing {APP_RESTORE} deployment ===")
        else:
            deploy(APP_RESTORE, cloud=cloud, extra={
                "COMFYMODAL_V2_UNET_EXCLUSIVE_OWNER": "1",
                "COMFYMODAL_V2_LEAN_SNAPSHOT": "1",
            })
        if "--deploy-only" in args:
            print("=== Lean deploy-only requested; study skipped ===")
            return
        env_extra = {
            "MODAL_TOKEN_ID": str(entry["token_id"]),
            "MODAL_TOKEN_SECRET": str(entry["token_secret"]),
            "COMFYMODAL_V2_APP_NAME": APP_RESTORE,
            "COMFYMODAL_V2_GPU": "rtx-pro-6000",
            "COMFYMODAL_V2_ENV_PROFILE": "production",
            "V2_OWNERSHIP_GAP_SECONDS": "25",
            "V2_OWNERSHIP_EXPECT_CLOUD": cloud,
            "V2_OWNERSHIP_EXPECT_LEAN": "1",
            "V2_OWNERSHIP_ACCEPT_UNDER_MS": "13500",
        }
        study_args = [
            "--app", APP_RESTORE, "--phase", "probes_off",
            "--target-cold", "6", "--max-attempts", "10",
            "--skip-first", "2", "--expect-cloud", cloud,
            "--expect-lean", "1", "--accept-under-ms", "13500",
            "--stop-after-bad", "0",
            "--report", "--report-name", "V2_LEAN_SNAPSHOT_DIRECT_VALIDATION_REPORT.md",
        ]
        run_study("ownership", study_args, env_extra)
    elif mode == "snapshot-ab":
        # Same-image snapshot-composition A/B: one deployment per arm, SAME
        # modal.Image + code revision, resources, region and test window.
        # Arm "current" = production snapshot composition (lean off).
        # Arm "lean"    = production snapshot with the default-off UNET
        #                 backing diagnostic deferred from import time
        #                 (COMFYMODAL_V2_LEAN_SNAPSHOT=1), reproducing the
        #                 last-known-fast import surface.
        # Entry probes measure submission → first Python line only.
        # ``--manifest`` bakes the snapshot-build manifest ON (composition
        # evidence runs only; NEVER on measured latency runs).
        arm = rest[0] if rest and rest[0] in ("current", "lean") else "current"
        if arm in rest:
            rest.remove(arm)
        region = ""
        if rest and rest[0] == "--region":
            rest.pop(0)
            if rest:
                region = rest.pop(0)
        manifest = "--manifest" in args
        no_deploy = "--no-deploy" in args
        cloud = "gcp"  # same region-pinned pool for causal isolation
        app = APP_RESTORE if arm == "current" else f"{APP_RESTORE}-lean"
        if "--app-name" in args:
            # Explicit app-name override (e.g. a dedicated arm-B deployment
            # name so the A/B cannot disturb the production app lineage).
            _idx = args.index("--app-name")
            if _idx + 1 < len(args) and args[_idx + 1].strip():
                app = args[_idx + 1].strip()
        extra: dict[str, str] = {
            "COMFYMODAL_V2_UNET_EXCLUSIVE_OWNER": "1",
            "COMFYMODAL_V2_LEAN_SNAPSHOT": "1" if arm == "lean" else "0",
            "COMFYMODAL_V2_SNAPSHOT_MANIFEST": "1" if manifest else "0",
        }
        if region:
            extra["COMFYMODAL_V2_REGION"] = region
        if no_deploy:
            print(f"=== snapshot-ab no-deploy: reusing {app} deployment ===")
        else:
            deploy(app, cloud=cloud, extra=extra)
        if "--deploy-only" in args:
            print("=== snapshot-ab deploy-only requested; study skipped ===")
            return
        env_extra = {
            "MODAL_TOKEN_ID": str(entry["token_id"]),
            "MODAL_TOKEN_SECRET": str(entry["token_secret"]),
            "COMFYMODAL_V2_APP_NAME": app,
            "COMFYMODAL_V2_GPU": "rtx-pro-6000",
            "COMFYMODAL_V2_ENV_PROFILE": "production",
            "V2_OWNERSHIP_GAP_SECONDS": "25",
        }
        study_args = [
            "--app", app, "--arm", arm, "--runs", "3", "--max-attempts", "6",
            "--skip-first", "2", "--expect-cloud", cloud,
            "--expect-lean", "1" if arm == "lean" else "0",
            "--expect-manifest", "1" if manifest else "0",
        ]
        if region:
            study_args += ["--expect-region", region]
        run_study("snapshot-ab", study_args, env_extra)
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
