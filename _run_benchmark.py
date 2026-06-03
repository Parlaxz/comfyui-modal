"""Run 3 cold-start benchmarks against the deployed Modal app.

Usage:
    python _run_benchmark.py

Prerequisites:
    - `modal deploy comfyapp.py` has been run
    - Modal token is configured
"""

import json
import sys
import time
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
BENCHMARK_LOGS_DIR = REPO_ROOT / "benchmark_logs"
WORKFLOW_FILE = REPO_ROOT / "latest_benchmark_workflow.json"


def main() -> int:
    import modal

    BENCHMARK_LOGS_DIR.mkdir(parents=True, exist_ok=True)

    # ── Load workflow ────────────────────────────────────────────────
    with open(WORKFLOW_FILE, "r", encoding="utf-8") as f:
        snapshot = json.load(f)
    payload = snapshot.get("payload", snapshot)
    workflow = payload.get("prompt", payload)
    if not isinstance(workflow, dict):
        print(f"ERROR: cannot extract workflow from snapshot keys={list(snapshot.keys())[:5]}")
        return 1

    print(f"Workflow loaded: {len(workflow)} nodes")

    # ── Connect to deployed Modal app ────────────────────────────────
    # NOTE: Must use RTX PRO 6000 (Blackwell). A10G SageAttention kernels
    # are compiled for SM 12.0 and produce CUDA errors on Ampere GPUs.
    GPU_CLASS = "ComfyAPI_RTX_PRO_6000"
    api = modal.Cls.from_name("comfyui", GPU_CLASS)()
    print(f"Connected to Modal {GPU_CLASS} (Blackwell RTX PRO 6000)\n")

    # ── Run 3 cold benchmarks with 10s gaps ──────────────────────────
    results = []
    for i in range(3):
        label = f"RUN-{i + 1}"
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = BENCHMARK_LOGS_DIR / f"cachepreload_{ts}_{label}.json"

        wall_start = time.time()
        try:
            result = api.run_prompt.remote(workflow)
        except Exception as exc:
            print(f"[{label}] FAILED: {exc}")
            results.append({"run": label, "error": str(exc)})
            continue
        wall_s = round(time.time() - wall_start, 3)

        trace = result.get("trace", {})
        restore = result.get("_restore_timing", {})
        cache_diag = result.get("_cache_diagnostics", {})

        # Include cache diagnostics in the saved JSON
        output = {
            "timestamp": ts,
            "run": label,
            "wall_clock_s": wall_s,
            "restore_timing": restore,
            "trace": trace,
            "cache_diagnostics": cache_diag,
        }
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(output, f, indent=2, sort_keys=True)

        # Print key metrics
        deltas = trace.get("deltas_ms", {}) if isinstance(trace, dict) else {}
        t3b_to_t8 = deltas.get("t3b_to_t8", "?")
        infer_total = deltas.get("inference_total", "?")
        clip_load = deltas.get("clip_load", "?")
        sampler = deltas.get("sampler", "?")
        restore_total = restore.get("restore_total_ms", "?")
        warmup_preload = restore.get("warmup_preload_ms", "?")
        warmup_wf = restore.get("warmup_wf_ms", "?")
        saddle = restore.get("sage_mode", "?")

        # GPU cache eq stats from LIVE diagnostics (not stale restore copy)
        gpu_eq_live = cache_diag.get("gpu_eq", restore.get("gpu_cache_eq", {}))
        eq_hits = gpu_eq_live.get("class_hits", "?")
        eq_misses = gpu_eq_live.get("misses", "?")
        eq_calls = gpu_eq_live.get("calls", "?")
        eq_str = f"{eq_calls}c/{eq_hits}h/{eq_misses}m" if eq_hits != "?" else "?"

        # CPU cache stats
        cpu_hits = cache_diag.get("cpu_hits", {})
        cpu_str = f"cpu_hits={cpu_hits}" if cpu_hits else ""
        # CLIP cache stats
        clip_h = cache_diag.get("clip_cache_hits", 0)
        clip_m = cache_diag.get("clip_cache_misses", 0)
        clip_str = f"clip_h={clip_h}/m={clip_m}" if clip_h or clip_m else ""

        print(f"[{label}] wall={wall_s}s  "
              f"t3b_to_t8={t3b_to_t8}ms  "
              f"inference={infer_total}ms  "
              f"clip_load={clip_load}ms  "
              f"sampler={sampler}ms  "
              f"restore_total={restore_total}ms  "
              f"preload={warmup_preload}ms  "
              f"wf={warmup_wf}ms  "
              f"sage={saddle}  gpu_eq={eq_str}  {cpu_str}  {clip_str}")
        # Print per-file and phase timing
        for key, val in restore.items():
            if isinstance(val, (int, float)):
                if key.startswith("warmup_") and key.endswith("_ms") and key not in ("warmup_preload_ms", "warmup_wf_ms"):
                    print(f"  ├─ {key}={val}ms")
                if key.startswith("warmup_wf_") and key.endswith("_ms"):
                    print(f"  ├─ {key}={val}ms")
                if key in ("early_path_resolve_ms", "cpu_cache_hits", "cpu_cache_misses"):
                    print(f"  ├─ {key}={val}")
        # Print gpu cache eq details (from live diagnostics)
        _gpu_details = gpu_eq_live.get("details", {})
        if _gpu_details:
            print(f"  └─ gpu_eq_details: {_gpu_details}")
        print(f"     saved to {filename.name}")

        results.append(output)

        if i < 2:
            print(f"  → waiting 20s for container scaledown...")
            time.sleep(20)

    # ── Summary table ────────────────────────────────────────────────
    print("\n" + "=" * 80)
    print("BENCHMARK SUMMARY")
    print("=" * 80)
    for r in results:
        if r.get("error"):
            print(f"  {r['run']}: FAILED - {r['error']}")
            continue
        r_trace = r.get("trace", {}) or {}
        r_deltas = r_trace.get("deltas_ms", {}) or {}
        r_restore = r.get("restore_timing", {}) or {}
        r_cache = r.get("cache_diagnostics", {}) or {}
        print(f"  {r['run']}:")
        print(f"    wall_clock         = {r['wall_clock_s']:>8.1f}s")
        print(f"    t3b_to_t8 (primary)= {r_deltas.get('t3b_to_t8', '?'):>8}")
        print(f"    inference_total    = {r_deltas.get('inference_total', '?'):>8}ms")
        print(f"    clip_load          = {r_deltas.get('clip_load', '?'):>8}ms")
        print(f"    clip_encode        = {r_deltas.get('clip_encode', '?'):>8}ms")
        print(f"    sampler            = {r_deltas.get('sampler', '?'):>8}ms")
        print(f"    vae_decode         = {r_deltas.get('vae_decode', '?'):>8}ms")
        print(f"    graph_overhead     = {r_deltas.get('graph_overhead', '?'):>8}ms")
        print(f"    restore_total      = {r_restore.get('restore_total_ms', '?'):>8}ms")
        print(f"    warmup_preload     = {r_restore.get('warmup_preload_ms', '?'):>8}ms")
        print(f"    warmup_wf          = {r_restore.get('warmup_wf_ms', '?'):>8}ms")
        print(f"    early_path_resolve = {r_restore.get('early_path_resolve_ms', '?'):>8}ms")
        print(f"    sage_mode          = {r_restore.get('sage_mode', '?'):>8}")
        for k, v in sorted(r_restore.items()):
            if isinstance(v, (int, float)):
                if k.startswith("warmup_wf_") and k.endswith("_ms"):
                    print(f"      {k:<30} = {v:>8.1f}ms")
        # GPU cache eq stats from LIVE diagnostics (not stale restore copy)
        gpu_eq_live = r_cache.get("gpu_eq", r_restore.get("gpu_cache_eq", {}))
        if gpu_eq_live:
            print(f"    gpu_eq_calls       = {gpu_eq_live.get('calls', '?'):>8}")
            print(f"    gpu_eq_class_hits  = {gpu_eq_live.get('class_hits', '?'):>8}")
            print(f"    gpu_eq_modeltype   = {gpu_eq_live.get('modeltype_hits', '?'):>8}")
            print(f"    gpu_eq_misses      = {gpu_eq_live.get('misses', '?'):>8}")
        # CPU cache
        cpu_hits = r_cache.get("cpu_hits", {})
        cpu_misses = r_cache.get("cpu_misses", {})
        if cpu_hits or cpu_misses:
            print(f"    cpu_hits           = {cpu_hits}")
            print(f"    cpu_misses         = {cpu_misses}")
        # CLIP cache
        clip_h = r_cache.get("clip_cache_hits", 0)
        clip_m = r_cache.get("clip_cache_misses", 0)
        if clip_h or clip_m:
            print(f"    clip_cache_hits    = {clip_h}")
            print(f"    clip_cache_misses  = {clip_m}")
    print("=" * 80)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
