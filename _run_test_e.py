"""Run Test E — No memory snapshot Blackwell cold starts.

Usage:
    modal deploy comfyapp.py   (first, to register PlatformTestE)
    python _run_test_e.py
"""

import json
import os
import sys
import time

import modal

N_RUNS = 5
GAP_S = 20


def load_workflow_with_images():
    with open("latest_benchmark_workflow.json") as f:
        snap = json.load(f)
    payload = snap.get("payload", snap)
    workflow = payload.get("prompt", payload)
    input_images = {}
    for ns in workflow.values():
        if isinstance(ns, dict) and ns.get("class_type") == "LoadImage":
            fn = ns.get("inputs", {}).get("image", "")
            if fn and fn not in input_images:
                input_images[fn] = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
    return workflow, input_images


def main():
    cls = modal.Cls.from_name("comfyui", "PlatformTestE")()
    wf, imgs = load_workflow_with_images()

    print("=" * 70)
    print("Test E — No memory snapshot Blackwell")
    print(f"Workflow: {len(wf)} nodes")
    if imgs:
        print(f"Input images: {len(imgs)}")
    print(f"Runs: {N_RUNS}, Gap: {GAP_S}s")
    print("=" * 70)

    all_results = []
    for i in range(N_RUNS):
        t0 = time.time()
        label = f"RUN-{i+1}"
        try:
            result = cls.run_prompt.remote(wf, input_images=imgs if imgs else None)
        except Exception as exc:
            print(f"[{label}] FAILED: {exc}")
            all_results.append({"run": label, "wall_ms": -1, "error": str(exc)[:200]})
            if i < N_RUNS - 1:
                time.sleep(GAP_S)
            continue
        t1 = time.time()

        rt = result.get("_restore_timing", {}) or {}
        total_wall = round((t1 - t0) * 1000, 1)
        startup_ms = rt.get("startup_ms", "?")
        exec_ms = rt.get("exec_ms", "?")
        imgs_out = len(result.get("images", []))

        # Payload size
        _payload_b64 = sum(len(img.get("data", "")) for img in result.get("images", []))
        _payload_mb = round(_payload_b64 / 1048576, 2)
        
        entry = {
            "run": label,
            "wall_ms": total_wall,
            "startup_ms": startup_ms,
            "exec_ms": exec_ms,
            "num_images": imgs_out,
            "payload_mb": _payload_mb,
            "error": None,
        }
        all_results.append(entry)
        print(f"[{label}] wall={total_wall}ms  startup={startup_ms}ms  exec={exec_ms}ms  images={imgs_out}  payload={_payload_mb}mb")

        if i < N_RUNS - 1:
            print(f"  → waiting {GAP_S}s...")
            time.sleep(GAP_S)

    # Summary
    print(f"\n{'='*70}")
    print("Test E — No Memory Snapshot — Summary")
    print(f"{'='*70}")
    print(f"{'Run':>8}  {'wall':>8}  {'startup':>8}  {'exec':>8}  {'imgs':>5}")
    print("-" * 70)
    for r in all_results:
        if r.get("error"):
            print(f"  {r['run']:>6}  FAILED: {r['error'][:80]}")
        else:
            print(f"  {r['run']:>6}  {r['wall_ms']:>8.0f}  {r['startup_ms']:>8}  {r['exec_ms']:>8}  {r.get('num_images',0):>5}")

    print()
    print("Compare with Config D (snapshot):")
    print("  Baseline: platform_restore~12-14s + app_restore~4s + remote_exec~5.4s = ~22s")
    print("  Test E:   startup replaces platform_restore+app_restore, exec replaces remote_exec")


if __name__ == "__main__":
    main()
