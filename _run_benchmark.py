"""Run 3 cold-start benchmarks against the deployed Modal app.

Usage:
    python _run_benchmark.py

Prerequisites:
    - `modal deploy comfyapp.py` has been run
    - Modal token is configured
"""

import json
import os
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

    # ── Optional preload mode ────────────────────────────────────────
    _preload_mode = os.environ.get("COMFYMODAL_PRELOAD_MODE", "").strip().lower()
    if _preload_mode:
        try:
            _r = modal.Function.from_name("comfyui", "set_preload_mode").remote(_preload_mode)
            print(f"Preload mode set: {_r}")
        except Exception as exc:
            print(f"WARNING: could not set preload_mode={_preload_mode}: {exc}")

    # ── Optional warmup CLIP encode toggle ──────────────────────────
    _wce_env = os.environ.get("COMFYMODAL_WARMUP_CLIP_ENCODE", "").strip().lower()
    if _wce_env:
        _wce_val = _wce_env in ("1", "true", "on")
        try:
            _r = modal.Function.from_name("comfyui", "set_warmup_clip_encode").remote(_wce_val)
            print(f"WCE set: {_r}")
        except Exception as exc:
            print(f"WARNING: could not set WCE={_wce_val}: {exc}")

    # ── P1 direct warmup runtime flags ──────────────────────────────
    for _flag in ("DIRECT_WARMUP_LOAD_UNET", "DIRECT_WARMUP_LOAD_CLIP",
                  "DIRECT_WARMUP_CLIP_ENCODE", "DIRECT_WARMUP_REQUIRE_CPU_CACHE_HIT"):
        _val = os.environ.get(f"COMFYMODAL_{_flag}", "").strip().lower()
        if _val in ("0", "1"):
            try:
                _r = modal.Function.from_name("comfyui", "set_runtime_flag").remote(_flag, _val)
                print(f"Runtime flag {_flag}={_val}: {_r}")
            except Exception as exc:
                print(f"WARNING: could not set {_flag}={_val}: {exc}")

    # ── P2 Sage runtime config ──────────────────────────────────────
    _sage_mode = os.environ.get("COMFYMODAL_SAGE_RUNTIME_MODE", "").strip().lower()
    if _sage_mode in ("baked_cuda", "triton_fallback", "auto"):
        try:
            _r = modal.Function.from_name("comfyui", "set_sage_runtime_mode").remote(_sage_mode)
            print(f"Sage runtime mode set: {_r}")
        except Exception as exc:
            print(f"WARNING: could not set sage_runtime_mode={_sage_mode}: {exc}")

    _sage_probe = os.environ.get("COMFYMODAL_SAGE_RUNTIME_PROBE_ON_RESTORE", "").strip().lower()
    if _sage_probe in ("0", "1"):
        _sp_val = _sage_probe == "1"
        try:
            _r = modal.Function.from_name("comfyui", "set_sage_runtime_probe").remote(_sp_val)
            print(f"Sage runtime probe set: {_r}")
        except Exception as exc:
            print(f"WARNING: could not set sage_runtime_probe={_sp_val}: {exc}")

    # ── Optional return mode ────────────────────────────────────────
    _return_mode = os.environ.get("COMFYMODAL_RETURN_MODE", "").strip().lower()
    if _return_mode:
        try:
            _r = modal.Function.from_name("comfyui", "set_return_mode").remote(_return_mode)
            print(f"Return mode set: {_r}")
        except Exception as exc:
            print(f"WARNING: could not set return_mode={_return_mode}: {exc}")

    # ── Optional CLIP encode cache clear ────────────────────────────
    _cache_clear = os.environ.get("COMFYMODAL_CLEAR_CLIP_ENCODE_CACHE", "").strip().lower()
    if _cache_clear:
        _cc_val = _cache_clear in ("1", "true", "on")
        try:
            _r = modal.Function.from_name("comfyui", "set_clear_clip_encode_cache").remote(_cc_val)
            print(f"CLIP cache clear set: {_r}")
        except Exception as exc:
            print(f"WARNING: could not set clear_clip_encode_cache={_cc_val}: {exc}")

    # ── Optional executor profiling toggle ──────────────────────────
    _exec_profile_env = os.environ.get("COMFYMODAL_EXEC_PROFILE", "").strip().lower()
    if _exec_profile_env:
        _ep_val = _exec_profile_env in ("1", "true", "on")
        try:
            _r = modal.Function.from_name("comfyui", "set_exec_profile").remote(_ep_val)
            print(f"Exec profile set: {_r}")
        except Exception as exc:
            print(f"WARNING: could not set exec_profile={_ep_val}: {exc}")

    # ── Optional sampler profiling toggle ───────────────────────────
    _sampler_profile_env = os.environ.get("COMFYMODAL_SAMPLER_PROFILE", "").strip().lower()
    if _sampler_profile_env:
        _sp_val = _sampler_profile_env in ("1", "true", "on")
        try:
            _r = modal.Function.from_name("comfyui", "set_sampler_profile").remote(_sp_val)
            print(f"Sampler profile set: {_r}")
        except Exception as exc:
            print(f"WARNING: could not set sampler_profile={_sp_val}: {exc}")

    # ── Optional guider profiling toggle ────────────────────────────
    _guider_profile_env = os.environ.get("COMFYMODAL_GUIDER_PROFILE", "").strip().lower()
    if _guider_profile_env:
        _gp_val = _guider_profile_env in ("1", "true", "on")
        try:
            _r = modal.Function.from_name("comfyui", "set_guider_profile").remote(_gp_val)
            print(f"Guider profile set: {_r}")
        except Exception as exc:
            print(f"WARNING: could not set guider_profile={_gp_val}: {exc}")

    # ── Optional deep profiling toggle ──────────────────────────────
    _deep_profile_env = os.environ.get("COMFYMODAL_DEEP_PROFILE", "").strip().lower()
    if _deep_profile_env:
        _dp_val = _deep_profile_env in ("1", "true", "on")
        try:
            _r = modal.Function.from_name("comfyui", "set_deep_profile").remote(_dp_val)
            print(f"Deep profile set: {_r}")
        except Exception as exc:
            print(f"WARNING: could not set deep_profile={_dp_val}: {exc}")

    # ── Optional LMG fast-path dry-run toggle ───────────────────────
    _lmg_dryrun_env = os.environ.get("COMFYMODAL_LMG_FASTPATH_DRYRUN", "").strip().lower()
    if _lmg_dryrun_env:
        _ld_val = _lmg_dryrun_env in ("1", "true", "on")
        try:
            _r = modal.Function.from_name("comfyui", "set_lmg_fastpath_dryrun").remote(_ld_val)
            print(f"LMG fastpath dry-run set: {_r}")
        except Exception as exc:
            print(f"WARNING: could not set lmg_fastpath_dryrun={_ld_val}: {exc}")

    # ── Optional LMG fast-path active toggle ────────────────────────
    _lmg_fp_env = os.environ.get("COMFYMODAL_LMG_FASTPATH", "").strip().lower()
    if _lmg_fp_env:
        _lf_val = _lmg_fp_env in ("1", "true", "on")
        try:
            _r = modal.Function.from_name("comfyui", "set_lmg_fastpath").remote(_lf_val)
            print(f"LMG fastpath set: {_r}")
        except Exception as exc:
            print(f"WARNING: could not set lmg_fastpath={_lf_val}: {exc}")

    # ── Optional ModelPatcher cache toggles ─────────────────────────
    _mp_cache_env = os.environ.get("COMFYMODAL_MODELPATCHER_CACHE", "").strip().lower()
    if _mp_cache_env:
        _mc_val = _mp_cache_env in ("1", "true", "on")
        try:
            _r = modal.Function.from_name("comfyui", "set_modelpatcher_cache").remote(_mc_val)
            print(f"ModelPatcher cache set: {_r}")
        except Exception as exc:
            print(f"WARNING: could not set modelpatcher_cache={_mc_val}: {exc}")
    _mp_dryrun_env = os.environ.get("COMFYMODAL_MODELPATCHER_CACHE_DRYRUN", "").strip().lower()
    if _mp_dryrun_env:
        _md_val = _mp_dryrun_env in ("1", "true", "on")
        try:
            _r = modal.Function.from_name("comfyui", "set_modelpatcher_cache_dryrun").remote(_md_val)
            print(f"ModelPatcher cache dry-run set: {_r}")
        except Exception as exc:
            print(f"WARNING: could not set modelpatcher_cache_dryrun={_md_val}: {exc}")
    _mp_trace_env = os.environ.get("COMFYMODAL_MODELPATCHER_TRACE", "").strip().lower()
    if _mp_trace_env:
        _mt_val = _mp_trace_env in ("1", "true", "on")
        try:
            _r = modal.Function.from_name("comfyui", "set_modelpatcher_trace").remote(_mt_val)
            print(f"ModelPatcher trace set: {_r}")
        except Exception as exc:
            print(f"WARNING: could not set modelpatcher_trace={_mt_val}: {exc}")

    # ── Load workflow ────────────────────────────────────────────────
    with open(WORKFLOW_FILE, "r", encoding="utf-8") as f:
        snapshot = json.load(f)
    payload = snapshot.get("payload", snapshot)
    workflow = payload.get("prompt", payload)
    if not isinstance(workflow, dict):
        print(f"ERROR: cannot extract workflow from snapshot keys={list(snapshot.keys())[:5]}")
        return 1

    print(f"Workflow loaded: {len(workflow)} nodes")

    # ── Build input_images for LoadImage nodes ───────────────────────
    # Scan the workflow for LoadImage nodes and create a dummy black
    # image for each referenced file.  This avoids workflow validation
    # failures when the expected image isn't on the container.
    _input_images: dict[str, str] = {}
    for _nid, _nspec in workflow.items():
        if isinstance(_nspec, dict) and _nspec.get("class_type") == "LoadImage":
            _fname = _nspec.get("inputs", {}).get("image", "")
            if _fname:
                import base64, io
                from PIL import Image
                _img = Image.new("RGB", (512, 768), color=(0, 0, 0))
                _buf = io.BytesIO()
                _img.save(_buf, format="PNG")
                _b64 = base64.b64encode(_buf.getvalue()).decode("ascii")
                _input_images[_fname] = _b64
                print(f"Created dummy input image: {_fname} (512x768 black PNG, {len(_b64)} b64 chars)")
    if _input_images:
        print(f"Total input images prepared: {len(_input_images)}")

    # ── Set warmup profile from workflow models ──────────────────────
    # Extract UNET/CLIP/VAE from the workflow so preload + direct warmup
    # actually loads models during restore.
    _warmup_profile = {"mode": "split", "clip_type": "flux"}
    _warmup_profile_models = {}
    for _nspec in workflow.values():
        if isinstance(_nspec, dict):
            _ct = _nspec.get("class_type", "")
            _inp = _nspec.get("inputs", {}) or {}
            if _ct == "UNETLoader":
                _warmup_profile["unet"] = _inp.get("unet_name", "")
            elif _ct == "CLIPLoader":
                _warmup_profile["clip1"] = _inp.get("clip_name", "")
                _warmup_profile["clip2"] = _inp.get("clip_name", "")  # same for flux
                _warmup_profile_models["clip_type"] = _inp.get("type", "flux")
            elif _ct == "VAELoader":
                _warmup_profile["vae"] = _inp.get("vae_name", "")
    _clip_t = _warmup_profile_models.get("clip_type", "flux")
    if _clip_t:
        _warmup_profile["clip_type"] = _clip_t
    has_models = bool(_warmup_profile.get("unet") and _warmup_profile.get("clip1"))
    if has_models:
        _wp_payload = {
            "warmup_profile": _warmup_profile,
            "workflow_hash": snapshot.get("workflow_hash", "benchmark"),
            "model_stack": {
                "unet": [_warmup_profile.get("unet", "")],
                "clip": [_warmup_profile.get("clip1", ""), _warmup_profile.get("clip2", "")],
                "vae": [_warmup_profile.get("vae", "")],
            },
            "profile_token": f"benchmark_{int(time.time())}",
            "disable_warmup": False,
        }
        try:
            _r = modal.Function.from_name("comfyui", "set_active_warmup_profile").remote(_wp_payload)
            print(f"Warmup profile set: {_r} | split unet={_warmup_profile.get('unet','')} clip1={_warmup_profile.get('clip1','')}")
        except Exception as exc:
            print(f"WARNING: could not set warmup profile: {exc}")
    else:
        print("WARNING: could not extract warmup profile from workflow — no UNET/CLIP found")

    # ── Connect to deployed Modal app ────────────────────────────────
    # NOTE: Must use RTX PRO 6000 (Blackwell). A10G SageAttention kernels
    # are compiled for SM 12.0 and produce CUDA errors on Ampere GPUs.
    GPU_CLASS = os.environ.get("COMFYMODAL_BENCHMARK_GPU_CLASS", "ComfyAPI_RTX_PRO_6000").strip()
    # Map shorthand names
    _gpu_map = {
        "rtx6000": "ComfyAPI_RTX_PRO_6000",
        "a10g": "ComfyAPI",
        "l4": "ComfyAPI_L4",
        "l40s": "ComfyAPI_L40S",
    }
    GPU_CLASS = _gpu_map.get(GPU_CLASS.lower(), GPU_CLASS)
    api = modal.Cls.from_name("comfyui", GPU_CLASS)()
    print(f"Connected to Modal {GPU_CLASS}\n")

    # ── Run 3 cold benchmarks with 20s gaps ──────────────────────────
    results = []
    for i in range(3):
        label = f"RUN-{i + 1}"
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = BENCHMARK_LOGS_DIR / f"cachepreload_{ts}_{label}.json"

        # ── Local benchmark timestamps ──
        bench_t0_start = time.time()

        bench_t1_workflow_loaded = time.time()

        bench_t2_before_modal_call = time.time()
        try:
            result = api.run_prompt.remote(workflow, input_images=_input_images if _input_images else None)
        except Exception as exc:
            print(f"[{label}] FAILED: {exc}")
            results.append({"run": label, "error": str(exc)})
            continue
        bench_t3_after_modal_call = time.time()

        trace = result.get("trace", {})
        restore = result.get("_restore_timing", {})
        cache_diag = result.get("_cache_diagnostics", {})
        t8b_breakdown = result.get("_t8b_breakdown", {})
        return_payload_info = result.get("_return_payload_info", {})
        # Add return_mode if not present (pre-2.11.0 compatibility)
        if "return_mode" not in return_payload_info:
            return_payload_info["return_mode"] = "full_base64"

        # Capture WCE info from restore_timing
        wce_enabled = restore.get("wce_enabled", "?")
        wce_source = restore.get("wce_source", "?")
        warmup_clip_encode_ms = restore.get("warmup_direct_clip_encode_ms", "?")

        bench_t4_after_result_parse = time.time()

        # Compute local timings
        workflow_load_ms = round((bench_t1_workflow_loaded - bench_t0_start) * 1000, 1)
        modal_call_wall_ms = round((bench_t3_after_modal_call - bench_t2_before_modal_call) * 1000, 1)
        result_parse_ms = round((bench_t4_after_result_parse - bench_t3_after_modal_call) * 1000, 1)

        # ── Waterfall from Modal container timestamps ──
        # app_restore_start/end from restore_timing (unix seconds)
        app_restore_start_ts = restore.get("restore_start_unix_s")
        app_restore_end_ts = restore.get("restore_end_unix_s")
        # remote_execute start/end from trace stages (unix seconds)
        _stages = trace.get("stages", {}) if isinstance(trace, dict) else {}
        remote_exec_start_ts = _stages.get("t3_modal_entry")
        remote_exec_end_ts = _stages.get("t9_modal_return")

        # Compute waterfall components (all in ms)
        platform_restore_ms = 0.0
        if app_restore_start_ts and bench_t2_before_modal_call:
            platform_restore_ms = round((app_restore_start_ts - bench_t2_before_modal_call) * 1000, 1)
        app_restore_ms = restore.get("restore_total_ms", 0.0) or 0.0
        remote_execute_ms = 0.0
        if remote_exec_start_ts and remote_exec_end_ts:
            remote_execute_ms = round((remote_exec_end_ts - remote_exec_start_ts) * 1000, 1)

        # Time from Modal return to benchmark receiving result
        modal_return_to_client_ms = round((bench_t3_after_modal_call - (remote_exec_end_ts or bench_t3_after_modal_call)) * 1000, 1) if remote_exec_end_ts else 0.0

        # Local post-processing time (result saved, printed, etc. — measured after)
        bench_t5_done = time.time()
        local_postprocess_ms = round((bench_t5_done - bench_t4_after_result_parse) * 1000, 1)

        app_controlled_ms = round(app_restore_ms + remote_execute_ms, 1)
        known_cold_ms = round(platform_restore_ms + app_restore_ms + remote_execute_ms, 1)
        benchmark_wall_ms = round((bench_t5_done - bench_t0_start) * 1000, 1)
        untracked_after_platform_ms = round(max(0.0, benchmark_wall_ms - known_cold_ms), 1)

        # Build waterfall dict
        waterfall = {
            "benchmark_wall_ms": benchmark_wall_ms,
            "workflow_load_ms": workflow_load_ms,
            "platform_restore_ms": platform_restore_ms,
            "app_restore_ms": app_restore_ms,
            "remote_execute_ms": remote_execute_ms,
            "modal_return_to_client_ms": modal_return_to_client_ms,
            "local_postprocess_ms": local_postprocess_ms,
            "app_controlled_ms": app_controlled_ms,
            "known_cold_ms": known_cold_ms,
            "untracked_after_platform_ms": untracked_after_platform_ms,
        }

        # Include cache diagnostics in the saved JSON
        _exec_profile = result.get("_exec_profile", {})
        output = {
            "timestamp": ts,
            "run": label,
            "wall_clock_s": round(benchmark_wall_ms / 1000, 3),
            "restore_timing": restore,
            "trace": trace,
            "cache_diagnostics": cache_diag,
            "t8b_breakdown": t8b_breakdown,
            "return_payload_info": return_payload_info,
            "exec_profile": _exec_profile,
            "sampler_profile": result.get("_sampler_profile", {}),
            "guider_profile": result.get("_guider_profile", {}),
            "deep_profile": result.get("_deep_profile", {}),
            "modelpatcher_trace": result.get("_modelpatcher_trace", []),
            "waterfall": waterfall,
        }
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(output, f, indent=2, sort_keys=True)

        # Print key metrics
        deltas = trace.get("deltas_ms", {}) if isinstance(trace, dict) else {}
        t3b_to_t8 = deltas.get("t3b_to_t8", "?")
        infer_total = deltas.get("inference_total", "?")
        clip_load = deltas.get("clip_load", "?")
        sampler = deltas.get("sampler", "?")
        graph_overhead = deltas.get("graph_overhead", "?")
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

        remote_total_ms = deltas.get("remote_total", "?")
        preload_mode = restore.get("preload_mode", "?")

        print(f"[{label}] wall={round(benchmark_wall_ms/1000,1)}s  "
              f"remote={remote_total_ms}ms  "
              f"restore={restore_total}ms  "
              f"inference={infer_total}ms  "
              f"clip_load={clip_load}ms  "
              f"sampler={sampler}ms  "
              f"graph_oh={graph_overhead}ms  "
              f"preload={warmup_preload}ms  "
              f"wf={warmup_wf}ms  "
              f"sage={saddle}  mode={preload_mode}  gpu_eq={eq_str}  {cpu_str}  {clip_str}")
        # Print per-file and phase timing
        for key, val in restore.items():
            if isinstance(val, (int, float)):
                if key.startswith("warmup_") and key.endswith("_ms") and key not in ("warmup_preload_ms", "warmup_wf_ms"):
                    print(f"  ├─ {key}={val}ms")
                if key.startswith("warmup_wf_") and key.endswith("_ms"):
                    print(f"  ├─ {key}={val}ms")
                if key in ("early_path_resolve_ms", "cpu_cache_hits", "cpu_cache_misses"):
                    print(f"  ├─ {key}={val}")
        # Print t8b breakdown
        _graph_oh = deltas.get("graph_overhead", "?")
        if t8b_breakdown:
            _gv = t8b_breakdown.get('graph_validate_ms')
            _gv_str = f" graph_validate={_gv}" if _gv is not None else ""
            print(f"  ├─ t8b: {t8b_breakdown.get('t8b_total_ms','?')}ms "
                  f"save={t8b_breakdown.get('t8b_save_stack_ms','?')} "
                  f"diag={t8b_breakdown.get('t8b_diagnostics_ms','?')} "
                  f"print={t8b_breakdown.get('t8b_profile_print_ms','?')} "
                  f"enrich={t8b_breakdown.get('t8b_enrich_ms','?')} "
                  f"diag_print={t8b_breakdown.get('t8b_diag_print_ms','?')}"
                  f"{_gv_str}"
                  f" graph_oh={_graph_oh}"
                  f" unk={t8b_breakdown.get('t8b_unknown_ms','?')}")
        # Print waterfall summary
        bucket = "excellent" if platform_restore_ms < 2000 else "normal" if platform_restore_ms < 4000 else "bad"
        _payload_str = ""
        if return_payload_info:
            _payload_str = f" imgs={return_payload_info.get('image_count','?')} b64_mb={round(return_payload_info.get('b64_bytes',0)/1048576,2)}"
        print(f"  └─ waterfall: wall={benchmark_wall_ms:.0f}ms "
              f"load={workflow_load_ms}ms "
              f"platform_restore={platform_restore_ms:.0f}ms[{bucket}] "
              f"app_restore={app_restore_ms:.0f} "
              f"remote_exec={remote_execute_ms:.0f} "
              f"return_to_client={modal_return_to_client_ms:.0f} "
              f"postprocess={local_postprocess_ms:.0f} "
              f"app_controlled={app_controlled_ms:.0f} "
              f"known_cold={known_cold_ms:.0f} "
              f"untracked={untracked_after_platform_ms:.0f}"
              f"{_payload_str}")
        # Print WCE info
        if wce_enabled != "?":
            print(f"     ├─ wce: enabled={wce_enabled} source={wce_source} warmup_encode_ms={warmup_clip_encode_ms}")
        # Print return mode info
        _ret_mode = return_payload_info.get("return_mode", "full_base64")
        _ret_b64 = return_payload_info.get("b64_bytes", 0)
        _ret_imgs = return_payload_info.get("image_count", 0)
        _ret_cache_size = return_payload_info.get("clip_cache_size_before_prompt", None)
        _cc_line = f" return_mode={_ret_mode} b64_mb={round(_ret_b64/1048576,2)} imgs={_ret_imgs}"
        if _ret_cache_size is not None:
            _cc_line += f" clip_cache_size={_ret_cache_size}"
        print(f"     ├─ return:{_cc_line}")
        # Print cache size from restore timing
        _cs_start = restore.get("clip_cache_size_at_start")
        _cs_after = restore.get("clip_cache_size_after_warmup")
        if _cs_start is not None or _cs_after is not None:
            _cls_line = "clip_cache_sizes:"
            if _cs_start is not None:
                _cls_line += f" at_restore_start={_cs_start}"
            if _cs_after is not None:
                _cls_line += f" after_warmup={_cs_after}"
            print(f"     ├─ {_cls_line}")
        # Print gpu cache eq details (from live diagnostics)
        _gpu_details = gpu_eq_live.get("details", {})
        if _gpu_details:
            print(f"     └─ gpu_eq_details: {_gpu_details}")
        # Print executor profile
        _exec_prof = result.get("_exec_profile", {})
        if _exec_prof:
            _exec_resid = _exec_prof.get("executor_residual_ms")
            _exec_total = _exec_prof.get("total_node_ms")
            _exec_wall = _exec_prof.get("execute_wall_ms")
            print(f"     ├─ exec: total_node={_exec_total}ms wall={_exec_wall}ms residual={_exec_resid}ms")
            _prof_parts = [f"{k}={v}" for k, v in _exec_prof.items() if k not in ("node_counts", "total_node_ms", "execute_wall_ms", "executor_residual_ms")]
            if _prof_parts:
                print(f"     ├─ exec_profile: {' '.join(_prof_parts)}")
            _nc = _exec_prof.get("node_counts", {})
            if _nc:
                print(f"     ├─ node_counts: {_nc}")
        # Print sampler profile
        _sampler_prof = result.get("_sampler_profile", {})
        if _sampler_prof:
            _sp_total = _sampler_prof.get("total_ms", 0)
            _sp_setup = _sampler_prof.get("setup_ms", 0)
            _sp_teardown = _sampler_prof.get("teardown_ms", 0)
            _sp_steps = {k: round(v, 2) for k, v in _sampler_prof.items() if k.startswith("step_")}
            print(f"     ├─ sampler: total={_sp_total:.1f}ms setup={_sp_setup:.1f} teardown={_sp_teardown:.1f}")
            if _sp_steps:
                _step_line = " ".join([f"{k}={v}ms" for k, v in sorted(_sp_steps.items())])
                print(f"     ├─ sampler_steps: {_step_line}")
        # Print guider profile
        _guider_prof = result.get("_guider_profile", {})
        if _guider_prof:
            _gp_line = " ".join([f"{k}={round(v,1)}ms" for k, v in sorted(_guider_prof.items())])
            print(f"     ├─ guider: {_gp_line}")
        # Print deep profile
        _deep_prof = result.get("_deep_profile", {})
        if _deep_prof:
            for _dp_section, _dp_data in sorted(_deep_prof.items()):
                if isinstance(_dp_data, dict):
                    _dp_line = " ".join([f"{k}={v}ms" if not k.startswith("sca_") else f"{k}={v:.1f}ms" for k, v in sorted(_dp_data.items())])
                    print(f"     ├─ {_dp_section}: {_dp_line}")
                elif isinstance(_dp_data, list):
                    for _i, _call in enumerate(_dp_data):
                        _simple = {k: v for k, v in _call.items() if not isinstance(v, (list, dict))}
                        _call_line = " ".join([f"{k}={v}" for k, v in sorted(_simple.items())])
                        print(f"     ├─ lmg_call_{_i}: {_call_line}")
                        _identity = _call.get("identity", [])
                        for _ent in _identity:
                            if isinstance(_ent, dict):
                                _id_line = " ".join([f"{k}={v}" for k, v in sorted(_ent.items())])
                                print(f"     │   └─ identity: {_id_line}")
                else:
                    print(f"     ├─ {_dp_section}: {_dp_data}")
        print(f"     saved to {filename.name}")

        results.append(output)

        if i < 2:
            print(f"  → waiting 20s for container scaledown...")
            time.sleep(20)

    # ── Waterfall table ──────────────────────────────────────────────
    print("\n" + "=" * 150)
    print("WATERFALL TABLE")
    print("=" * 150)
    hdr = f"{'Run':>6}  {'wall':>7}  {'load':>6}  {'platform':>10}  {'app_res':>8}  {'rem_exe':>8}  {'ret_cli':>8}  {'post':>6}  {'app_ctrl':>9}  {'known_cold':>10}  {'untracked':>10}  {'ret_mode':>14}  {'payload_mb':>10}"
    print(hdr)
    print("-" * 150)
    for r in results:
        if r.get("error"):
            print(f"  {r['run']:>6}  FAILED")
            continue
        wf = r.get("waterfall", {})
        _rpi = r.get("return_payload_info", {})
        _rmode = _rpi.get("return_mode", "full_base64")
        _pmb = round(_rpi.get("b64_bytes", 0) / 1048576, 2)
        print(f"{r['run']:>6}  "
              f"{wf.get('benchmark_wall_ms',0):>7.0f}  "
              f"{wf.get('workflow_load_ms',0):>6.1f}  "
              f"{wf.get('platform_restore_ms',0):>10.0f}  "
              f"{wf.get('app_restore_ms',0):>8.0f}  "
              f"{wf.get('remote_execute_ms',0):>8.0f}  "
              f"{wf.get('modal_return_to_client_ms',0):>8.0f}  "
              f"{wf.get('local_postprocess_ms',0):>6.1f}  "
              f"{wf.get('app_controlled_ms',0):>9.0f}  "
              f"{wf.get('known_cold_ms',0):>10.0f}  "
              f"{wf.get('untracked_after_platform_ms',0):>10.0f}  "
              f"{_rmode:>14}  {_pmb:>10.2f}")
    print("=" * 150)
    print("Field legend:")
    print("  wall       = benchmark wall clock (t0 → t5)")
    print("  load       = workflow file load time")
    print("  platform   = Modal platform restore (pre-app) [excellent<2s | normal 2-4s | bad 4s+]")
    print("  app_res    = app_restore_ms (lifecycle_restore)")
    print("  rem_exe    = remote_execute_ms (t3 → t9 inside Modal)")
    print("  ret_cli    = time from t9_modal_return to benchmark receiving result")
    print("  post       = local result parse + save + print")
    print("  app_ctrl   = app_restore + remote_execute (app-controlled total)")
    print("  known_cold = platform + app_restore + remote_execute (known total)")
    print("  untracked  = wall − known_cold (everything else)")
    print()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
