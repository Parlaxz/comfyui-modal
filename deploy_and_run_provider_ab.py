"""Deploy the AWS/GCP provider shadow apps and run the interleaved cold study.

Arm aws = cloud-pinned AWS (``COMFYMODAL_V2_CLOUD=aws``, no region pin).
Arm gcp = cloud-pinned GCP (``COMFYMODAL_V2_CLOUD=gcp``, no region pin).

Both share the verified production config (CPU 16 / mem 49152 MiB, TBASE/O0,
single-use containers, minimal teardown, VAE snapshot, exact CLIP
conditioning cache, UNET activation `late`, diagnostics off by default) plus
the study-only gates: variance diagnostics (synchronized transfer
measurement), host diagnostics (provider/region/CPU/GPU UUID/task id) and the
per-run page-path probe (mincore residency, native one-byte-per-page
traversal, real UNET H2D, 12.31 GB contiguous synthetic H2D, 454-storage
synthetic H2D).  The legacy 2 GiB synth probe is OFF so it cannot prewarm the
real transfer.

Usage:
    python deploy_and_run_provider_ab.py [target_cold] [max_per_arm]
    (or set V2_PROVIDER_AB_TARGET_COLD / V2_PROVIDER_AB_MAX_ATTEMPTS_PER_ARM)
    --deploy-only deploys without running the benchmark.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
APP_AWS = "stable-modal-comfy-v2-provider-aws-shadow"
APP_GCP = "stable-modal-comfy-v2-provider-gcp-shadow"

ws = json.loads((ROOT / ".modal_workspaces.json").read_text(encoding="utf-8"))
aid = ws.get("active_workspace_id")
entry = next((w for w in ws.get("workspaces", []) if w.get("id") == aid), None)
if not entry or not entry.get("token_id") or not entry.get("token_secret"):
    print("ERROR: could not load workspace credentials")
    sys.exit(1)


def base_env(app_name: str, cloud: str) -> dict[str, str]:
    env = dict(os.environ)
    env.update({
        "MODAL_TOKEN_ID": str(entry["token_id"]),
        "MODAL_TOKEN_SECRET": str(entry["token_secret"]),
        "COMFYMODAL_V2_APP_NAME": app_name,
        "COMFYMODAL_V2_CLASS_NAME": "ModalRuntimeEntrypointV2",
        "COMFYMODAL_V2_GPU": "rtx-pro-6000",
        "COMFYMODAL_V2_CLOUD": cloud,
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
        "COMFYMODAL_V2_VARIANCE_DIAGNOSTICS": "1",
        "COMFYMODAL_V2_HOST_DIAGNOSTICS": "1",
        "COMFYMODAL_V2_PAGE_PATH_PROBE": "1",
        "COMFYMODAL_V2_SYNTH_H2D_PROBE": "0",
        "COMFYMODAL_V2_UNET_BACKING_VERIFY": "1",
        "COMFYMODAL_V2_ANON_UNET_SNAPSHOT": "0",
        "PYTHONIOENCODING": "utf-8",
        "PYTHONUTF8": "1",
    })
    return env


def deploy(app_name: str, cloud: str) -> None:
    env = base_env(app_name, cloud)
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
    print(f"=== Deploying {app_name} (cloud={cloud}) ===", flush=True)
    deploy = subprocess.run(
        ["modal", "deploy", "-m", "comfymodal_runtime.modal_app"],
        cwd=str(ROOT), env=env, text=True,
    )
    if deploy.returncode != 0:
        print(f"=== ERROR: deploy of {app_name} failed ===")
        sys.exit(deploy.returncode)
    print(f"=== Deploy verified OK: {app_name} ===", flush=True)


target = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("V2_PROVIDER_AB_TARGET_COLD", "7")
max_per_arm = sys.argv[2] if len(sys.argv) > 2 else os.environ.get("V2_PROVIDER_AB_MAX_ATTEMPTS_PER_ARM", "12")

deploy(APP_AWS, cloud="aws")
deploy(APP_GCP, cloud="gcp")

if "--deploy-only" in sys.argv:
    print("=== Deploy-only requested; benchmark skipped ===")
    sys.exit(0)

env = base_env(APP_AWS, cloud="aws")
env.update({
    "COMFYMODAL_V2_PROVIDER_AWS_APP": APP_AWS,
    "COMFYMODAL_V2_PROVIDER_GCP_APP": APP_GCP,
    "V2_PROVIDER_AB_TARGET_COLD": target,
    "V2_PROVIDER_AB_MAX_ATTEMPTS_PER_ARM": max_per_arm,
    "V2_VARIANCE_COLD_GAP_SECONDS": "25",
})
print(f"=== Running interleaved provider AWS-vs-GCP study (target {target}/arm) ===", flush=True)
bench = subprocess.run(
    [sys.executable, str(ROOT / "tools" / "benchmark_v2_direct.py"),
     "--provider-ab", "--teardown", "minimal"],
    cwd=str(ROOT), env=env, text=True,
)
if bench.returncode != 0:
    print(f"=== ERROR: provider_ab benchmark failed with exit code {bench.returncode} ===")
    sys.exit(bench.returncode)
print("=== Provider AWS-vs-GCP study completed successfully ===", flush=True)
sys.exit(0)
