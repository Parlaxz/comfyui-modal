"""V2 Batch D9 — input_types_warm forensics harness (ZERO-SPEND, local only).

Three modes, all local and read-only with respect to Modal:

  measure  cold/warm/repeated per-class INPUT_TYPES timing for the 31-class
           production set, plus FS-access probes, result sizes, CUDA/RSS/thread
           checks.
  omit     omission simulation: clear all warmable caches, re-measure the full
           pass (the cost the first consumer would pay), and prove output
           determinism (identical schemas with and without warm).
  bench    concurrency micro-benchmark: warm lane vs meta-like CPU lane vs
           file-read lane, alone and in combinations, to test for local
           contention (Part 8).

No Modal calls. No deploy. No writes outside tools/d9_measurements.json.
"""

from __future__ import annotations

import argparse
import asyncio
import gc
import hashlib
import json
import os
import sys
import threading
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_COMFYUI_ROOT = REPO_ROOT.parent.parent  # ...\ComfyUI June Install\ComfyUI
PROOF_STORE = REPO_ROOT / ".cache" / "v2_registry_proof_store.json"
BENCH_WORKFLOW = REPO_ROOT / "c5_latest_benchmark_workflow.json"
OUT_JSON = REPO_ROOT / "tools" / "d9_measurements.json"

_FS_PROBE = {"get_filename_list": 0, "recursive_search": 0, "gfl_ms": 0.0, "rs_ms": 0.0}
_ORIG = {}
_PROBE_CLASS = {"current": None}
_PER_CLASS_FS: dict[str, dict] = {}


# ── shared setup ────────────────────────────────────────────────────────────

def setup_comfy(comfyui_root: str | None = None) -> tuple[object, object]:
    root = Path(comfyui_root or os.environ.get("COMFYMODAL_COMFYUI_ROOT") or DEFAULT_COMFYUI_ROOT)
    if not (root / "nodes.py").exists():
        raise SystemExit(f"ComfyUI root not found at {root}")
    sys.path.insert(0, str(root))
    import folder_paths  # noqa: F401
    import nodes
    # Importing nodes can mutate sys.path (e.g. prepend ComfyUI\comfy), which
    # shadows the top-level ``utils`` package with comfy/utils.py and breaks
    # server.py's ``from utils.install_util import ...`` during node loading.
    # Re-assert the ComfyUI root so ``utils`` resolves to the real package.
    sys.path.insert(0, str(root))

    if not getattr(nodes, "_d9_extra_nodes_loaded", False):
        # Custom nodes reference ``PromptServer.instance`` at import time
        # (route registration etc.).  Production boots a minimal in-process
        # PromptServer before ``init_extra_nodes`` (comfyapp.py DummyServer);
        # replicate that so the same node modules import locally.
        try:
            import server as comfy_server
            _loop = asyncio.new_event_loop()
            asyncio.set_event_loop(_loop)

            class _DummyServer(comfy_server.PromptServer):
                def __init__(self, loop):
                    try:
                        super().__init__(loop)
                    except Exception:
                        pass
                    comfy_server.PromptServer.instance = self
                    self.client_id = "in-process"

            _DummyServer(_loop)
        except Exception as exc:
            print(f"[d9] DummyServer bootstrap warning: {exc!r}")
        try:
            asyncio.run(nodes.init_extra_nodes(init_custom_nodes=True, init_api_nodes=True))
        except Exception as exc:  # pragmatic: keep going with whatever registered
            print(f"[d9] init_extra_nodes warning: {exc!r}")
        nodes._d9_extra_nodes_loaded = True  # type: ignore[attr-defined]
        # Mirror the production backend's final registration step
        # (comfyapp.py:18372-18374) so the comfyui-modal classes are mapped.
        try:
            import comfyapp  # local import; no Modal calls

            for _name in ("ComfyModalProductionOutput", "ComfyModalProductionImageComparerOutput"):
                _cls = getattr(comfyapp, _name, None)
                if _cls is not None:
                    nodes.NODE_CLASS_MAPPINGS[_name] = _cls
        except Exception as exc:
            print(f"[d9] comfyui-modal class registration warning: {exc!r}")
    return folder_paths, nodes


def load_production_class_set() -> list[str]:
    """The frozen 31-class set from the D1 registry proof store (production)."""
    try:
        data = json.loads(PROOF_STORE.read_text(encoding="utf-8"))
        for entry in (data.get("entries") or {}).values():
            classes = (entry.get("registry_proof") or {}).get("classes")
            if isinstance(classes, list) and classes:
                return list(classes)
    except Exception:
        pass
    # Fallback: derive distinct class types from the benchmark workflow prompt.
    try:
        payload = json.loads(BENCH_WORKFLOW.read_text(encoding="utf-8"))
        prompt = payload.get("prompt") or {}
        seen: list[str] = []
        for node in prompt.values():
            ct = node.get("class_type") if isinstance(node, dict) else None
            if isinstance(ct, str) and ct and ct not in seen:
                seen.append(ct)
        if seen:
            return seen
    except Exception:
        pass
    raise SystemExit("no class set available (proof store and workflow missing)")


def build_prompt_from_classes(classes: list[str]) -> dict[str, dict]:
    return {str(i + 1): {"class_type": ct} for i, ct in enumerate(classes)}


def install_fs_probes(folder_paths) -> None:
    """Count/time the two filesystem primitives loader INPUT_TYPES rely on."""
    for name, counter in (("get_filename_list", "gfl_ms"), ("recursive_search", "rs_ms")):
        orig = getattr(folder_paths, name, None)
        if orig is None or not callable(orig):
            continue
        _ORIG[name] = orig

        def make_wrapper(orig_fn, n=name, cnt=counter):
            def wrapper(*a, **k):
                t0 = time.perf_counter()
                try:
                    return orig_fn(*a, **k)
                finally:
                    _FS_PROBE[n] += 1
                    _FS_PROBE[cnt] += (time.perf_counter() - t0) * 1000.0
                    cur = _PROBE_CLASS.get("current")
                    if cur:
                        slot = _PER_CLASS_FS.setdefault(cur, {"get_filename_list": 0, "recursive_search": 0, "gfl_ms": 0.0, "rs_ms": 0.0})
                        slot[n] += 1
                        slot[cnt] += (time.perf_counter() - t0) * 1000.0
            return wrapper

        setattr(folder_paths, name, make_wrapper(orig))


def uninstall_fs_probes(folder_paths) -> None:
    for name, orig in _ORIG.items():
        setattr(folder_paths, name, orig)
    _ORIG.clear()


def snapshot_system() -> dict:
    out = {
        "thread_count": threading.active_count(),
        "rss_mb": None,
        "cuda_initialized": None,
        "process_cpu_ms": None,
    }
    try:
        import psutil
        out["rss_mb"] = round(psutil.Process().memory_info().rss / 1048576.0, 1)
        out["process_cpu_ms"] = round(psutil.Process().cpu_times().user * 1000.0, 1)
    except Exception:
        pass
    try:
        import torch
        out["cuda_initialized"] = bool(torch.cuda.is_initialized())
    except Exception:
        out["cuda_initialized"] = None
    return out


def clear_warmable_caches(folder_paths) -> None:
    """Return the process to the pre-warm cache state (for omission/bench)."""
    try:
        folder_paths.filename_list_cache.clear()
    except Exception:
        pass
    try:
        folder_paths.cache_helper.clear()
    except Exception:
        try:
            folder_paths.cache_helper.cache.clear()
        except Exception:
            pass
    gc.collect()


# ── measure mode ────────────────────────────────────────────────────────────

def per_class_pass(classes, folder_paths, nodes, with_probes=True) -> dict:
    if with_probes:
        for k in _FS_PROBE:
            _FS_PROBE[k] = 0
    results = {}
    for ct in classes:
        cls = nodes.NODE_CLASS_MAPPINGS.get(ct)
        if cls is None:
            results[ct] = {"error": "not_mapped"}
            continue
        _PROBE_CLASS["current"] = ct
        t0 = time.perf_counter()
        try:
            spec = cls.INPUT_TYPES()
            ok = True
            err = None
        except Exception as exc:
            spec = None
            ok = False
            err = f"{type(exc).__name__}: {exc}"
        wall_ms = (time.perf_counter() - t0) * 1000.0
        _PROBE_CLASS["current"] = None
        size = None
        if ok and isinstance(spec, dict):
            try:
                size = len(json.dumps(spec))
            except Exception:
                size = -1
        results[ct] = {
            "ok": ok,
            "wall_ms": round(wall_ms, 3),
            "result_bytes": size,
            "result_keys": len(spec) if ok and isinstance(spec, dict) else None,
            "error": err,
            "fs": _PER_CLASS_FS.pop(ct, {"get_filename_list": 0, "recursive_search": 0, "gfl_ms": 0.0, "rs_ms": 0.0}),
        }
    results["_fs"] = dict(_FS_PROBE)
    return results


def full_pass(classes, prompt, nodes, folder_paths, with_probes=True) -> dict:
    if with_probes:
        for k in _FS_PROBE:
            _FS_PROBE[k] = 0
    from comfymodal_runtime.execution_warm import warm_classes_input_types

    t0 = time.perf_counter()
    count, elapsed_ms = warm_classes_input_types(prompt)
    wall_ms = (time.perf_counter() - t0) * 1000.0
    return {
        "count": count,
        "warm_fn_ms": elapsed_ms,
        "caller_wall_ms": round(wall_ms, 3),
        "fs": dict(_FS_PROBE),
    }


def run_measure(comfyui_root: str | None) -> dict:
    t_import = time.perf_counter()
    folder_paths, nodes = setup_comfy(comfyui_root)
    import_cost_ms = (time.perf_counter() - t_import) * 1000.0
    classes = load_production_class_set()
    prompt = build_prompt_from_classes(classes)
    mapped = sum(1 for c in classes if c in nodes.NODE_CLASS_MAPPINGS)
    install_fs_probes(folder_paths)

    sys_before = snapshot_system()
    out: dict = {
        "comfyui_root": str(folder_paths.__file__ if hasattr(folder_paths, "__file__") else ""),
        "classes": classes,
        "class_count": len(classes),
        "mapped_count": mapped,
        "unmapped": [c for c in classes if c not in nodes.NODE_CLASS_MAPPINGS],
        "import_cost_ms": round(import_cost_ms, 1),
        "cuda_initialized_at_start": sys_before["cuda_initialized"],
        "threads_at_start": sys_before["thread_count"],
        "rss_mb_at_start": sys_before["rss_mb"],
        "pass1_cold": full_pass(classes, prompt, nodes, folder_paths),
        "per_class_pass1": per_class_pass(classes, folder_paths, nodes),
        "pass2_warm": full_pass(classes, prompt, nodes, folder_paths),
        "per_class_pass2": per_class_pass(classes, folder_paths, nodes),
        "pass3_warm": full_pass(classes, prompt, nodes, folder_paths),
        "per_class_pass3": per_class_pass(classes, folder_paths, nodes),
    }
    # repeated per-class calls (4th/5th evaluation)
    repeated = {}
    for ct in classes:
        cls = nodes.NODE_CLASS_MAPPINGS.get(ct)
        if cls is None:
            continue
        times = []
        for _ in range(2):
            t0 = time.perf_counter()
            try:
                cls.INPUT_TYPES()
                times.append((time.perf_counter() - t0) * 1000.0)
            except Exception:
                times.append(-1.0)
        repeated[ct] = {"call4_ms": round(times[0], 3), "call5_ms": round(times[1], 3)}
    out["per_class_repeated"] = repeated

    # sibling folder warmer
    from comfymodal_runtime.execution_warm import warm_registered_folders

    for k in _FS_PROBE:
        _FS_PROBE[k] = 0
    t0 = time.perf_counter()
    fcount, fms = warm_registered_folders()
    out["warm_registered_folders"] = {
        "folder_count": fcount,
        "warm_fn_ms": fms,
        "caller_wall_ms": round((time.perf_counter() - t0) * 1000.0, 3),
        "fs": dict(_FS_PROBE),
    }

    # explicit cold loader listings (clear cache first for true cold numbers)
    clear_warmable_caches(folder_paths)
    loader_listings = {}
    for folder_name in ("diffusion_models", "text_encoders", "vae", "vae_approx"):
        t0 = time.perf_counter()
        try:
            files = folder_paths.get_filename_list(folder_name)
            loader_listings[folder_name] = {
                "cold_ms": round((time.perf_counter() - t0) * 1000.0, 3),
                "file_count": len(files),
            }
        except Exception as exc:
            loader_listings[folder_name] = {"cold_ms": None, "error": str(exc)}
        t0 = time.perf_counter()
        try:
            folder_paths.get_filename_list(folder_name)
            loader_listings[folder_name]["warm_ms"] = round(
                (time.perf_counter() - t0) * 1000.0, 3
            )
        except Exception:
            loader_listings[folder_name]["warm_ms"] = None
    out["loader_listings"] = loader_listings

    sys_after = snapshot_system()
    out["sys_after"] = sys_after
    uninstall_fs_probes(folder_paths)
    return out


# ── omit mode ───────────────────────────────────────────────────────────────

def run_omit(comfyui_root: str | None) -> dict:
    folder_paths, nodes = setup_comfy(comfyui_root)
    classes = load_production_class_set()
    prompt = build_prompt_from_classes(classes)
    install_fs_probes(folder_paths)

    out: dict = {"classes": classes}
    # Determinism: warm once, snapshot schemas.
    from comfymodal_runtime.execution_warm import warm_classes_input_types

    warm_classes_input_types(prompt)
    warm_schemas = {}
    for ct in classes:
        cls = nodes.NODE_CLASS_MAPPINGS.get(ct)
        if cls is None:
            continue
        try:
            warm_schemas[ct] = cls.INPUT_TYPES()
        except Exception as exc:
            warm_schemas[ct] = {"__error__": str(exc)}

    # Omission: clear every warmable cache, then measure what the first
    # consumer (topo walk / get_input_info) would pay instead.
    clear_warmable_caches(folder_paths)
    for k in _FS_PROBE:
        _FS_PROBE[k] = 0
    t0 = time.perf_counter()
    count, elapsed_ms = warm_classes_input_types(prompt)
    out["deferred_cold_pass_ms"] = round((time.perf_counter() - t0) * 1000.0, 3)
    out["deferred_fs"] = dict(_FS_PROBE)
    out["deferred_count"] = count

    # Determinism equality: schemas after cache-clear must equal warm schemas.
    mismatches = []
    for ct, warm_spec in warm_schemas.items():
        cls = nodes.NODE_CLASS_MAPPINGS.get(ct)
        if cls is None:
            continue
        try:
            cold_spec = cls.INPUT_TYPES()
        except Exception as exc:
            mismatches.append({"class": ct, "error": str(exc)})
            continue
        if isinstance(warm_spec, dict) and "__error__" not in warm_spec:
            if cold_spec != warm_spec:
                mismatches.append({"class": ct, "reason": "schema_mismatch"})
    out["schema_mismatch_count"] = len(mismatches)
    out["schema_mismatches"] = mismatches

    # Per-input lookup cost model: for every class, the cost of one
    # get_input_info-style lookup per declared input (the topo-walk link cost).
    lookup_costs = {}
    for ct, warm_spec in warm_schemas.items():
        cls = nodes.NODE_CLASS_MAPPINGS.get(ct)
        if cls is None or not isinstance(warm_spec, dict):
            continue
        input_count = sum(len(v) for k, v in warm_spec.items() if isinstance(v, dict))
        t0 = time.perf_counter()
        for section in ("required", "optional", "hidden"):
            for name in (warm_spec.get(section) or {}):
                try:
                    from comfy_execution.graph import get_input_info as gii
                    gii(cls, name)
                except Exception:
                    pass
        lookup_costs[ct] = {
            "input_count": input_count,
            "walk_per_input_ms": round((time.perf_counter() - t0) * 1000.0, 3),
        }
    out["lookup_costs"] = lookup_costs
    uninstall_fs_probes(folder_paths)
    return out


# ── bench mode ──────────────────────────────────────────────────────────────

def _lane_warm(nodes, prompt, events, results, idx):
    from comfymodal_runtime.execution_warm import warm_classes_input_types

    events[idx]["start"].set()
    events[idx]["go"].wait()
    t0 = time.perf_counter()
    c0 = time.thread_time()
    count, ms = warm_classes_input_types(prompt)
    results[idx] = {
        "wall_ms": round((time.perf_counter() - t0) * 1000.0, 3),
        "cpu_ms": round(max(0.0, time.thread_time() - c0) * 1000.0, 3),
        "count": count,
        "warm_fn_ms": ms,
    }


def _lane_meta(events, results, idx, seconds=2.0):
    """CPU-heavy lane resembling UNET get_model meta construction
    (torch CPU math + pure-Python hashing churn)."""
    events[idx]["start"].set()
    events[idx]["go"].wait()
    t0 = time.perf_counter()
    c0 = time.thread_time()
    import torch

    end = time.perf_counter() + seconds
    i = 0
    while time.perf_counter() < end:
        if i % 3 == 0:
            a = torch.rand(512, 512)
            _ = a @ a
        else:
            for _ in range(2000):
                hashlib.sha256(b"comfymodal-meta-churn").digest()
        i += 1
    results[idx] = {
        "wall_ms": round((time.perf_counter() - t0) * 1000.0, 3),
        "cpu_ms": round(max(0.0, time.thread_time() - c0) * 1000.0, 3),
    }


def _lane_fileread(model_path, events, results, idx):
    """File-read lane resembling fastsafetensors IO (chunked read of a model)."""
    events[idx]["start"].set()
    events[idx]["go"].wait()
    t0 = time.perf_counter()
    c0 = time.thread_time()
    total = 0
    with open(model_path, "rb") as fh:
        while True:
            chunk = fh.read(1 << 20)
            if not chunk:
                break
            total += len(chunk)
    results[idx] = {
        "wall_ms": round((time.perf_counter() - t0) * 1000.0, 3),
        "cpu_ms": round(max(0.0, time.thread_time() - c0) * 1000.0, 3),
        "bytes_read_mb": round(total / 1048576.0, 1),
    }


def _pick_model_file(comfyui_root) -> Path:
    root = Path(comfyui_root or DEFAULT_COMFYUI_ROOT)
    best = None
    models_dir = root / "models"
    if models_dir.is_dir():
        for f in models_dir.rglob("*"):
            if f.is_file():
                try:
                    size = f.stat().st_size
                except Exception:
                    continue
                if size > 50 * 1048576 and (best is None or size > best.stat().st_size):
                    best = f
    if best is None:
        raise SystemExit("no model file >= 50MB found for file-read lane")
    return best


def run_bench(comfyui_root: str | None, iterations: int, sim_fs_ms: float = 0.0) -> dict:
    folder_paths, nodes = setup_comfy(comfyui_root)
    classes = load_production_class_set()
    prompt = build_prompt_from_classes(classes)
    model_file = _pick_model_file(comfyui_root)

    # Optional production-like simulation: inject latency into
    # folder_paths.recursive_search so the warm lane's FS work costs what the
    # Modal volume costs remotely (~1s+ per listing) instead of ~1ms on local
    # NTFS.  Lets us measure contention with a warm lane that actually lasts.
    _orig_rs = getattr(folder_paths, "recursive_search", None)
    if sim_fs_ms > 0 and _orig_rs is not None:

        def _slow_rs(*a, **k):
            time.sleep(sim_fs_ms / 1000.0)
            return _orig_rs(*a, **k)

        folder_paths.recursive_search = _slow_rs

    combos = ["warm", "meta", "fileread", "warm+meta", "warm+fileread", "warm+meta+fileread"]
    runs: dict = {
        "iterations": iterations,
        "model_file": str(model_file),
        "sim_fs_ms": sim_fs_ms,
    }
    for combo in combos:
        runs[combo] = []
    for i in range(iterations):
        for combo in combos:
            lanes = combo.split("+")
            clear_warmable_caches(folder_paths)  # cold warm each iteration
            events = {j: {"start": threading.Event(), "go": threading.Event()} for j in range(len(lanes))}
            results: dict = {}
            threads = []
            for j, lane in enumerate(lanes):
                if lane == "warm":
                    th = threading.Thread(
                        target=_lane_warm, args=(nodes, prompt, events, results, j),
                        name=f"d9-warm-{i}", daemon=True,
                    )
                elif lane == "meta":
                    th = threading.Thread(
                        target=_lane_meta, args=(events, results, j),
                        name=f"d9-meta-{i}", daemon=True,
                    )
                else:
                    th = threading.Thread(
                        target=_lane_fileread, args=(model_file, events, results, j),
                        name=f"d9-fileread-{i}", daemon=True,
                    )
                threads.append(th)
            for j, th in enumerate(threads):
                th.start()
            for j in range(len(lanes)):
                events[j]["start"].wait(10)
            t_sys0 = time.perf_counter()
            for j in range(len(lanes)):
                events[j]["go"].set()
            for th in threads:
                th.join(timeout=120)
            sys_wall = (time.perf_counter() - t_sys0) * 1000.0
            entry = {"combo": combo, "iter": i, "lanes": {}, "sys_wall_ms": round(sys_wall, 3)}
            for j, lane in enumerate(lanes):
                entry["lanes"][f"{lane}_{j}"] = results.get(j, {"error": "no_result"})
            entry["sys"] = snapshot_system()
            runs[combo].append(entry)
            print(f"[d9] bench iter={i} combo={combo} sys_wall={entry['sys_wall_ms']}ms "
                  f"lanes={json.dumps(entry['lanes'])}", flush=True)
    return runs


# ── imports mode ────────────────────────────────────────────────────────────

def run_imports_diag(comfyui_root: str | None) -> dict:
    """Full node-loading diagnostics: total mappings after the production
    bootstrap path (DummyServer + init_extra_nodes) and the 31-class mapping
    report.  Class-count deltas vs production are explained by local-only
    missing deps (reported via init_extra_nodes stderr warnings)."""
    folder_paths, nodes = setup_comfy(comfyui_root)
    classes = load_production_class_set()
    total = len(nodes.NODE_CLASS_MAPPINGS)
    mapped = [c for c in classes if c in nodes.NODE_CLASS_MAPPINGS]
    unmapped = [c for c in classes if c not in nodes.NODE_CLASS_MAPPINGS]
    return {
        "class_set": classes,
        "class_count": len(classes),
        "total_mappings": total,
        "mapped": mapped,
        "mapped_count": len(mapped),
        "unmapped": unmapped,
    }


# ── entry point ─────────────────────────────────────────────────────────────

def _append_out(mode: str, data: dict) -> None:
    existing = {}
    if OUT_JSON.exists():
        try:
            existing = json.loads(OUT_JSON.read_text(encoding="utf-8"))
        except Exception:
            existing = {}
    existing.setdefault("runs", []).append(
        {"mode": mode, "ts_unix": time.time(), "data": data}
    )
    OUT_JSON.write_text(json.dumps(existing, indent=2, default=str), encoding="utf-8")
    print(f"[d9] appended {mode} result -> {OUT_JSON}")


def main() -> None:
    # Custom-node modules print non-ASCII (emoji etc.) to the console; on
    # Windows cp1252 that raises 'charmap' codec errors during import.  Force
    # UTF-8 so the production node modules import identically to the container.
    for _stream in (sys.stdout, sys.stderr):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    ap = argparse.ArgumentParser(description="D9 input_types_warm forensics (local, zero-spend)")
    ap.add_argument("mode", choices=["measure", "omit", "bench", "imports"])
    ap.add_argument("--comfyui-root", default=None)
    ap.add_argument("--iterations", type=int, default=3)
    ap.add_argument("--sim-fs-ms", type=float, default=0.0,
                    help="bench: inject per-call latency into folder_paths.recursive_search "
                         "to emulate Modal-volume FS cost")
    args = ap.parse_args()

    if args.mode == "measure":
        data = run_measure(args.comfyui_root)
    elif args.mode == "omit":
        data = run_omit(args.comfyui_root)
    elif args.mode == "imports":
        data = run_imports_diag(args.comfyui_root)
    else:
        data = run_bench(args.comfyui_root, args.iterations, sim_fs_ms=args.sim_fs_ms)
    _append_out(args.mode, data)
    print(json.dumps(data, indent=2, default=str)[:4000])


if __name__ == "__main__":
    main()
