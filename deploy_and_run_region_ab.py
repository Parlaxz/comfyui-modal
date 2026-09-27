"""Deploy the shadow app pinned to a region and run the region-pinned A/B.

Usage:
    python deploy_and_run_region_ab.py us-east-2
    python deploy_and_run_region_ab.py us-east4
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REGION = (sys.argv[1] if len(sys.argv) > 1 else os.environ.get("COMFYMODAL_V2_REGION", "")).strip()
if not REGION:
    print("ERROR: pass a region (us-east-2 / us-east4 / ap-northeast-1)")
    sys.exit(1)

ws = json.loads((ROOT / ".modal_workspaces.json").read_text(encoding="utf-8"))
aid = ws.get("active_workspace_id")
entry = next((w for w in ws.get("workspaces", []) if w.get("id") == aid), None)
if not entry or not entry.get("token_id") or not entry.get("token_secret"):
    print("ERROR: could not load workspace credentials")
    sys.exit(1)

env = dict(os.environ)
env.update({
    "MODAL_TOKEN_ID": str(entry["token_id"]),
    "MODAL_TOKEN_SECRET": str(entry["token_secret"]),
    "COMFYMODAL_V2_APP_NAME": "stable-modal-comfy-v2-shadow",
    "COMFYMODAL_V2_CLASS_NAME": "ModalRuntimeEntrypointV2",
    "COMFYMODAL_V2_GPU": "rtx-pro-6000",
    "COMFYMODAL_V2_DEEP_MODEL_DIAG": "1",
    "COMFYMODAL_V2_CPU_MODEL_SNAPSHOT": "1",
    "COMFYMODAL_V2_MEMORY_MB": "49152",
    "COMFYMODAL_V2_BASELINE_MEMORY_REQUEST": "49152",
    "COMFYMODAL_V2_SINGLE_USE_CONTAINERS": "1",
    "COMFYMODAL_V2_VAE_SNAPSHOT": "1",
    "COMFYMODAL_EXACT_CLIP_CONDITIONING_CACHE": "1",
    "COMFYMODAL_V2_REGION": REGION,
    "PYTHONIOENCODING": "utf-8",
    "PYTHONUTF8": "1",
})

# Warmup profile env from the benchmark workflow
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

print(f"=== Deploying shadow app pinned to region {REGION} ===", flush=True)
deploy = subprocess.run(
    ["modal", "deploy", "-m", "comfymodal_runtime.modal_app"],
    cwd=str(ROOT), env=env, text=True,
)
if deploy.returncode != 0:
    print("=== ERROR: deploy failed ===")
    sys.exit(deploy.returncode)
print("=== Deploy verified OK ===", flush=True)

env.update({
    "COMFYMODAL_V2_VARIANCE_APP_NAME": "stable-modal-comfy-v2-shadow",
    "COMFYMODAL_V2_ENV_PROFILE": "production",
    "V2_VARIANCE_COLD_GAP_SECONDS": "25",
    "V2_REGION_AB_TARGET_COLD": "10",
    "V2_REGION_AB_MAX_ATTEMPTS": "15",
})
print(f"=== Running region-pinned A/B for {REGION} ===", flush=True)
bench = subprocess.run(
    [sys.executable, str(ROOT / "tools" / "benchmark_v2_direct.py"),
     "--region-ab", REGION, "--teardown", "minimal"],
    cwd=str(ROOT), env=env, text=True,
)
if bench.returncode != 0:
    print(f"=== ERROR: region_ab benchmark failed with exit code {bench.returncode} ===")
    sys.exit(bench.returncode)
print(f"=== Region {REGION} completed successfully ===", flush=True)
sys.exit(0)
