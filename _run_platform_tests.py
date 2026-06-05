"""Run 5 cold-container restores per platform test and print a comparison table.

Usage:
    # Deploy first
    modal deploy _test_platform_a.py
    modal deploy comfyapp.py

    # Run all tests
    python _run_platform_tests.py

    # Run specific tests
    python _run_platform_tests.py --tests A,B,D
"""

import json
import os
import sys
import time
from datetime import datetime

import modal

N_RUNS = 5
GAP_S = 20


def _load_workflow_with_images() -> tuple[dict, dict]:
    with open("latest_benchmark_workflow.json") as f:
        snap = json.load(f)
    payload = snap.get("payload", snap)
    workflow = payload.get("prompt", payload)
    input_images = {}
    for _nspec in workflow.values():
        if isinstance(_nspec, dict) and _nspec.get("class_type") == "LoadImage":
            _fn = _nspec.get("inputs", {}).get("image", "")
            if _fn and _fn not in input_images:
                input_images[_fn] = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
    return workflow, input_images


def _ping_simple(cls, n_runs: int, label: str) -> list[dict]:
    """Call ``ping`` on *cls* (simple test classes)."""
    results = []
    for i in range(n_runs):
        t0 = time.time()
        result = cls.ping.remote()
        t1 = time.time()
        rss = result.get("restore_start_unix_s", 0) or 0
        rse = result.get("restore_end_unix_s", 0) or 0
        _restore_count = result.get("restore_count", 0)

        _now = time.time()
        _restore_is_recent = (rss > 0) and (_now - rss) < 15.0
        if _restore_is_recent:
            platform_ms = round((rss - t0) * 1000, 1)
            app_ms = round((rse - rss) * 1000, 1) if rse > 0 else -1
        else:
            platform_ms = -2
            app_ms = -2
        wall_ms = round((t1 - t0) * 1000, 1)

        entry = {
            "run": f"RUN-{i+1}",
            "platform_restore_ms": platform_ms,
            "app_restore_ms": app_ms,
            "wall_ms": wall_ms,
            "restore_count": _restore_count,
        }
        results.append(entry)

        if _restore_is_recent:
            status = "cold_blob" if platform_ms > 30000 else "cached"
            print(f"  [{label} {entry['run']}] platform={platform_ms:>7.0f}ms  "
                  f"app={app_ms:>7.0f}ms  wall={wall_ms:>7.0f}ms  [{status}]")
        else:
            print(f"  [{label} {entry['run']}] container reused — skipping")
        if i < n_runs - 1:
            time.sleep(GAP_S)
    return results


def _ping_runprompt(cls, n_runs: int, label: str) -> list[dict]:
    """Call ``run_prompt`` with benchmark workflow on *cls* for *n_runs*."""
    _wf, _imgs = _load_workflow_with_images()
    results = []
    for i in range(n_runs):
        t0 = time.time()
        try:
            result = cls.run_prompt.remote(_wf, input_images=_imgs if _imgs else None)
        except Exception as exc:
            if i < n_runs - 1:
                time.sleep(GAP_S)
            results.append({"run": f"RUN-{i+1}", "platform_restore_ms": -1, "app_restore_ms": -1, "wall_ms": -1, "error": str(exc)[:100]})
            print(f"  [{label} RUN-{i+1}] FAILED: {str(exc)[:100]}")
            continue
        t1 = time.time()
        rt = result.get("_restore_timing", {}) or {}
        rss = rt.get("restore_start_unix_s", 0) or 0
        rse = rt.get("restore_end_unix_s", 0) or 0

        _now = time.time()
        _restore_is_recent = (rss > 0) and (_now - rss) < 15.0
        if _restore_is_recent:
            platform_ms = round((rss - t0) * 1000, 1)
            app_ms = round((rse - rss) * 1000, 1) if rse > 0 else -1
        else:
            platform_ms = -2
            app_ms = -2
        wall_ms = round((t1 - t0) * 1000, 1)

        entry = {
            "run": f"RUN-{i+1}",
            "platform_restore_ms": platform_ms,
            "app_restore_ms": app_ms,
            "wall_ms": wall_ms,
            "preload_mode": rt.get("preload_mode", "?"),
            "warmup_preload_ms": rt.get("warmup_preload_ms", 0),
            "restore_was_recent": _restore_is_recent,
            "raw": result,
        }
        results.append(entry)

        if _restore_is_recent:
            status = "cold_blob" if platform_ms > 30000 else "cached"
            pbar = f" preload={rt.get('warmup_preload_ms','?')}ms" if rt.get("warmup_preload_ms", 0) > 0 else ""
            print(f"  [{label} {entry['run']}] platform={platform_ms:>7.0f}ms  "
                  f"app={app_ms:>7.0f}ms  wall={wall_ms:>7.0f}ms  [{status}]"
                  f" mode={rt.get('preload_mode','?')}{pbar}")
        else:
            print(f"  [{label} {entry['run']}] container reused — skipping")
        if i < n_runs - 1:
            time.sleep(GAP_S)
    return results


def print_table(all_results: dict[str, list[dict]]):
    print()
    print("=" * 140)
    print("PLATFORM RESTORE COMPARISON — 5 cold-container restores per test")
    print("=" * 140)
    hdr = f"{'Test':>20}  {'RUN-1':>8}  {'RUN-2':>8}  {'RUN-3':>8}  {'RUN-4':>8}  {'RUN-5':>8}  {'cached range':>16}  {'cached median':>16}"
    print(hdr)
    print("-" * 140)
    for label, runs in all_results.items():
        cached = [r["platform_restore_ms"] for r in runs if isinstance(r["platform_restore_ms"], (int, float)) and 0 < r["platform_restore_ms"] < 30000]
        r1 = runs[0]["platform_restore_ms"] if len(runs) > 0 else "?"
        r2 = runs[1]["platform_restore_ms"] if len(runs) > 1 else ""
        r3 = runs[2]["platform_restore_ms"] if len(runs) > 2 else ""
        r4 = runs[3]["platform_restore_ms"] if len(runs) > 3 else ""
        r5 = runs[4]["platform_restore_ms"] if len(runs) > 4 else ""
        cr = f"{min(cached):.0f}–{max(cached):.0f}" if cached else "all cold"
        med = f"{sorted(cached)[len(cached)//2]:.0f}" if cached else "N/A"
        _r1s = f"{r1:.0f}" if isinstance(r1, float) else str(r1)
        _r2s = f"{r2:.0f}" if isinstance(r2, float) else str(r2)
        _r3s = f"{r3:.0f}" if isinstance(r3, float) else str(r3)
        _r4s = f"{r4:.0f}" if isinstance(r4, float) else str(r4)
        _r5s = f"{r5:.0f}" if isinstance(r5, float) else str(r5)
        print(f"  {label:>18}  {_r1s:>8}  {_r2s:>8}  {_r3s:>8}  {_r4s:>8}  {_r5s:>8}  {cr:>16}  {med:>16}")
    print("-" * 140)
    print("  cold_blob = first deploy, no cached snapshot yet  |  cached = snapshot already on Modal infra")
    print()


def _set_warmup_profile():
    """Extract models from the benchmark workflow and set a warmup profile."""
    wf, _ = _load_workflow_with_images()
    profile = {"mode": "split", "clip_type": "flux"}
    for ns in wf.values():
        if isinstance(ns, dict):
            ct = ns.get("class_type", "")
            inp = ns.get("inputs", {}) or {}
            if ct == "UNETLoader":
                profile["unet"] = inp.get("unet_name", "")
            elif ct == "CLIPLoader":
                profile["clip1"] = inp.get("clip_name", "")
                profile["clip2"] = inp.get("clip_name", "")
                clip_t = inp.get("type", "flux")
                if clip_t:
                    profile["clip_type"] = clip_t
            elif ct == "VAELoader":
                profile["vae"] = inp.get("vae_name", "")
    if not profile.get("unet") or not profile.get("clip1"):
        print("  WARNING: could not extract warmup profile from workflow")
        return
    payload = {
        "warmup_profile": profile,
        "workflow_hash": "platform_test",
        "model_stack": {
            "unet": [profile.get("unet", "")],
            "clip": [profile.get("clip1", ""), profile.get("clip2", "")],
            "vae": [profile.get("vae", "")],
        },
        "profile_token": f"ptest_{int(time.time())}",
        "disable_warmup": False,
    }
    try:
        modal.Function.from_name("comfyui", "set_active_warmup_profile").remote(payload)
    except Exception as exc:
        print(f"  WARNING: could not set warmup profile: {exc}")


def main():
    tests = set(sys.argv[sys.argv.index("--tests") + 1].split(",")) if "--tests" in sys.argv else {"A", "B", "C", "D"}
    print(f"Running tests: {tests}")

    all_results: dict[str, list[dict]] = {}

    # ── Test A: Tiny Blackwell ────────────────────────────────────────
    if "A" in tests:
        print(f"\n{'='*60}")
        print("Test A — Tiny image Blackwell (minimal app, no Comfy)")
        print(f"{'='*60}")
        cls_a = modal.Cls.from_name("comfyui-platform-a", "TinyBlackwell")()
        all_results["A: Tiny Blackwell"] = _ping_simple(cls_a, N_RUNS, "A")

    # ── Test B: Production image, minimal function ──────────────────
    if "B" in tests:
        print(f"\n{'='*60}")
        print("Test B — Production image, minimal fn (no Comfy imports)")
        print(f"{'='*60}")
        cls_b = modal.Cls.from_name("comfyui", "PlatformTestB")()
        all_results["B: Prod image, no Comfy"] = _ping_simple(cls_b, N_RUNS, "B")

    # ── Test C: Production image + Comfy imports only ───────────────
    if "C" in tests:
        print(f"\n{'='*60}")
        print("Test C — Production image + Comfy imports only (no warmup)")
        print(f"{'='*60}")
        cls_c = modal.Cls.from_name("comfyui", "ComfyAPI_RTX_PRO_6000")()
        try:
            modal.Function.from_name("comfyui", "set_preload_mode").remote("off")
        except Exception:
            pass
        all_results["C: Prod+Comfy, no warmup"] = _ping_runprompt(cls_c, N_RUNS, "C")

    # ── Test D: Current Config D ─────────────────────────────────────
    if "D" in tests:
        print(f"\n{'='*60}")
        print("Test D — Config D (workers_2, direct warmup, no CLIP encode)")
        print(f"{'='*60}")
        cls_d = modal.Cls.from_name("comfyui", "ComfyAPI_RTX_PRO_6000")()
        try:
            modal.Function.from_name("comfyui", "set_preload_mode").remote("workers_2")
            modal.Function.from_name("comfyui", "set_runtime_flag").remote("DIRECT_WARMUP_LOAD_UNET", "1")
            modal.Function.from_name("comfyui", "set_runtime_flag").remote("DIRECT_WARMUP_LOAD_CLIP", "1")
            modal.Function.from_name("comfyui", "set_runtime_flag").remote("DIRECT_WARMUP_CLIP_ENCODE", "0")
            modal.Function.from_name("comfyui", "set_runtime_flag").remote("DIRECT_WARMUP_REQUIRE_CPU_CACHE_HIT", "0")
            modal.Function.from_name("comfyui", "set_sage_runtime_mode").remote("baked_cuda")
            modal.Function.from_name("comfyui", "set_sage_runtime_probe").remote(False)
        except Exception:
            pass
        _set_warmup_profile()
        all_results["D: Config D (prod)"] = _ping_runprompt(cls_d, N_RUNS, "D")

    # ── Print comparison table ────────────────────────────────────────
    print_table(all_results)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
