"""NUMA placement causal experiment runner (shadow app; one attempt at a time).

Deploys (or reuses) a dedicated shadow app whose image carries
``run_numa_experiment``, then:

  attempt 0  -- snapshot-builder call (discarded, creates the snapshot)
  gap        -- V2_OWNERSHIP_GAP_SECONDS (default 25 s) so attempt 1 lands on
                a fresh single-use restored container
  attempt 1  -- the measured NUMA cascade on the restored container

One attempt at a time by default (``--runs 1``); the caller decides whether
more attempts are needed after inspecting the result.

Usage:
  python tools/run_numa_experiment.py [--deploy] [--cloud gcp|aws|unpinned]
      [--app NAME] [--runs 1] [--gap 25] [--no-deploy]
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from comfymodal_runtime.modal_transport import ModalTransport, HandleCache

APP_NUMA = "stable-modal-comfy-v2-numa-shadow"
OUTPUT_ROOT = Path(os.environ.get(
    "COMFYMODAL_V2_OWNERSHIP_OUTPUT",
    str(Path(os.environ.get("LOCALAPPDATA", str(ROOT))) / "comfymodal-data" / "benchmarks" / "runs"),
))
GPU = os.environ.get("COMFYMODAL_V2_GPU", "rtx-pro-6000")


def _load_workspace() -> dict[str, Any]:
    data = json.loads((ROOT / ".modal_workspaces.json").read_text(encoding="utf-8"))
    active_id = data.get("active_workspace_id")
    for workspace in data.get("workspaces", []):
        if workspace.get("id") == active_id:
            if not workspace.get("token_id") or not workspace.get("token_secret"):
                raise RuntimeError("active Modal workspace has no credentials")
            os.environ["MODAL_TOKEN_ID"] = str(workspace["token_id"])
            os.environ["MODAL_TOKEN_SECRET"] = str(workspace["token_secret"])
            return workspace
    raise RuntimeError("active Modal workspace was not found")


def _base_env(app_name: str, cloud: str = "") -> dict[str, str]:
    env = dict(os.environ)
    env.update({
        "COMFYMODAL_V2_APP_NAME": app_name,
        "COMFYMODAL_V2_CLASS_NAME": "ModalRuntimeEntrypointV2",
        "COMFYMODAL_V2_GPU": GPU,
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
        "COMFYMODAL_V2_HOST_DIAGNOSTICS": "1",
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


def deploy(app_name: str, *, cloud: str = "") -> None:
    env = _base_env(app_name, cloud)
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


async def _call_remote(fn: Any, **kwargs: Any) -> Any:
    """Invoke a Modal-exposed method handle; returns the dict result."""
    remote = getattr(fn, "remote", None)
    if remote is not None and callable(getattr(remote, "aio", None)):
        result = remote.aio(**kwargs)
        if asyncio.iscoroutine(result):
            return await result
        return result
    if asyncio.iscoroutinefunction(fn):
        return await fn(**kwargs)
    return await asyncio.to_thread(fn, **kwargs)


def _key_numbers(res: dict[str, Any]) -> dict[str, Any]:
    t = res.get("topology") or {}
    out: dict[str, Any] = {
        "status": res.get("status", ""),
        "restore_count": res.get("restore_count"),
        "cloud": (res.get("identity") or {}).get("cloud", ""),
        "region": (res.get("identity") or {}).get("region", ""),
        "gpu": t.get("gpu_numa_node"),
        "numa_nodes": t.get("numa_nodes"),
        "affinity_nodes": t.get("affinity_nodes"),
        "cpu_model": (t.get("cpu") or {}).get("model_name", ""),
        "baseline_h2d_ms": (res.get("baseline_h2d") or {}).get("wall_ms"),
        "baseline_h2d_gbps": (res.get("baseline_h2d") or {}).get("gb_per_s"),
        "baseline_numa": (res.get("baseline_numa_exact") or {}).get("status_counts"),
        "manipulation_blocked": res.get("manipulation_blocked"),
        "blocked_errnos": res.get("blocked_errnos"),
        "local_node": res.get("local_node"),
        "remote_node": res.get("remote_node"),
        "fresh_control_h2d_ms": (res.get("fresh_control_h2d") or {}).get("wall_ms"),
        "fresh_control_gbps": (res.get("fresh_control_h2d") or {}).get("gb_per_s"),
        "seccomp": t.get("seccomp_mode"),
        "zoneinfo_nodes": t.get("zoneinfo_nodes"),
        "proc_visibility": t.get("proc_visibility"),
        "local_mig": {
            "verified": (res.get("local_migration") or {}).get("verified"),
            "fraction_on_target": (res.get("local_migration") or {}).get(
                "fraction_on_target"),
            "error": (res.get("local_migration") or {}).get("error"),
        },
        "local_h2d_ms": (res.get("local_h2d") or {}).get("wall_ms"),
        "remote_mig": {
            "verified": (res.get("remote_migration") or {}).get("verified"),
            "fraction_on_target": (res.get("remote_migration") or {}).get(
                "fraction_on_target"),
        },
        "remote_h2d_ms": (res.get("remote_h2d") or {}).get("wall_ms"),
        "bind_probe": {
            k: {
                "verified": (v or {}).get("mbind", {}).get("verified"),
                "h2d_ms": (v or {}).get("h2d_wall_ms"),
                "gbps": (v or {}).get("h2d_gb_per_s"),
                "err": (v or {}).get("mbind", {}).get("mbind_errno"),
            }
            for k, v in (res.get("bind_probe") or {}).items()
        },
        "byte_equality": (res.get("byte_equality") or {}).get("status"),
        "reason": res.get("reason", ""),
    }
    return out


def _print_summary(label: str, k: dict[str, Any]) -> None:
    print(f"[v2.numa] === {label} ===", flush=True)
    print(f"[v2.numa] status={k['status']} restore_count={k['restore_count']} "
          f"cloud={k['cloud']} region={k['region']} gpu={k['gpu']}", flush=True)
    print(f"[v2.numa] cpu={k['cpu_model']} numa_nodes={k['numa_nodes']} "
          f"affinity_nodes={k['affinity_nodes']}", flush=True)
    print(f"[v2.numa] baseline_h2d={k['baseline_h2d_ms']}ms "
          f"({k['baseline_h2d_gbps']} GB/s) numa={k['baseline_numa']}", flush=True)
    print(f"[v2.numa] blocked={k['manipulation_blocked']} "
          f"errnos={k['blocked_errnos']} local_node={k['local_node']} "
          f"remote_node={k['remote_node']}", flush=True)
    print(f"[v2.numa] fresh_control_h2d={k['fresh_control_h2d_ms']}ms "
          f"({k['fresh_control_gbps']} GB/s) seccomp={k['seccomp']} "
          f"zoneinfo_nodes={k['zoneinfo_nodes']}", flush=True)
    print(f"[v2.numa] local_mig verified={k['local_mig']['verified']} "
          f"frac={k['local_mig']['fraction_on_target']} "
          f"err={k['local_mig']['error']} h2d={k['local_h2d_ms']}ms", flush=True)
    print(f"[v2.numa] remote_mig verified={k['remote_mig']['verified']} "
          f"h2d={k['remote_h2d_ms']}ms", flush=True)
    print(f"[v2.numa] bind_probe={json.dumps(k['bind_probe'])}", flush=True)
    print(f"[v2.numa] byte_equality={k['byte_equality']}", flush=True)


async def _run(workspace: dict[str, Any], output_dir: Path, *,
               app_name: str, runs: int, gap: float) -> None:
    os.environ["COMFYMODAL_V2_APP_NAME"] = app_name
    transport = ModalTransport(handle_cache=HandleCache())
    handle = await asyncio.to_thread(
        transport._v2_handle, workspace=workspace, gpu=GPU,
    )
    for index in range(runs + 1):
        _run_id = f"numa-{index}-{uuid.uuid4().hex[:8]}"
        _req_id = f"v2-numa-{index}-{uuid.uuid4().hex[:12]}"
        _t0 = time.perf_counter()
        artifact: dict[str, Any] = {
            "run_index": index, "run_id": _run_id, "request_id": _req_id,
            "start_ts": datetime.now(timezone.utc).isoformat(),
        }
        try:
            result = await _call_remote(
                handle.run_numa_experiment, request_id=_req_id,
            )
            artifact["result"] = result if isinstance(result, dict) else {
                "raw": str(result)[:300]
            }
        except Exception as exc:  # noqa: BLE001
            artifact["error"] = (
                f"remote call failed: {type(exc).__name__}: {str(exc)[:300]}"
            )
            artifact["result"] = {}
        artifact["wall_ms"] = round((time.perf_counter() - _t0) * 1000.0, 1)
        _res = artifact.get("result") or {}
        artifact["excluded_snapshot_builder"] = index == 0
        artifact["measurement_valid"] = bool(
            index > 0
            and not artifact.get("error")
            and _res.get("status") == "ok"
            and _res.get("restore_count", 0) >= 1
            and isinstance(_res.get("baseline_h2d"), dict)
            and _res.get("baseline_h2d", {}).get("wall_ms") is not None
            and (_res.get("byte_equality") or {}).get("status") == "all_equal"
        )
        artifact_file = output_dir / f"attempt_{index:04d}.json"
        artifact_file.write_text(
            json.dumps(artifact, default=str, indent=2), encoding="utf-8"
        )
        _k = _key_numbers(_res)
        artifact["key_numbers"] = _k
        artifact_file.write_text(
            json.dumps(artifact, default=str, indent=2), encoding="utf-8"
        )
        if index == 0:
            print(
                f"[v2.numa] index=0 snapshot-builder status={_res.get('status', '')} "
                f"error={artifact.get('error', '')[:120]}",
                flush=True,
            )
        else:
            _print_summary(f"attempt {index}", _k)
        if index < runs:
            print(f"[v2.numa] phase=gap seconds={gap}", flush=True)
            await asyncio.sleep(gap)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--deploy", action="store_true",
                        help="deploy the NUMA shadow app first")
    parser.add_argument("--no-deploy", action="store_true",
                        help="reuse the existing deployment (no new image)")
    parser.add_argument("--cloud", default="gcp",
                        choices=["gcp", "aws", "unpinned"])
    parser.add_argument("--app", default=APP_NUMA)
    parser.add_argument("--runs", type=int, default=1,
                        help="measured attempts (each on a fresh restored "
                             "container); 1 by default — run one at a time")
    parser.add_argument("--gap", type=float,
                        default=float(os.environ.get("V2_OWNERSHIP_GAP_SECONDS", "25")))
    args = parser.parse_args()

    # Load workspace credentials FIRST so deploy() and the handle lookup use
    # the SAME active workspace (deploy without tokens goes to the CLI
    # default account, which is a different Modal workspace).
    workspace = _load_workspace()
    if args.deploy and not args.no_deploy:
        deploy(args.app, cloud=args.cloud)
    else:
        print(f"=== No-deploy: reusing {args.app} deployment ===", flush=True)

    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H-%M-%S")
    output_dir = OUTPUT_ROOT / f"v2_{stamp}_numa"
    output_dir.mkdir(parents=True, exist_ok=True)
    print(f"[v2.numa] app={args.app} runs={args.runs} output={output_dir}",
          flush=True)
    asyncio.run(_run(workspace, output_dir, app_name=args.app,
                     runs=args.runs, gap=args.gap))
    print(f"[v2.numa] output_dir={output_dir}", flush=True)


if __name__ == "__main__":
    main()
