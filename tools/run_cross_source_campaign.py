#!/usr/bin/env python
"""Cross-source localization campaign (H100, 64 MiB x QD4, no primer).

Fires one diagnostic probe set per pathological episode (trigger 250 ms) and a
clean-reference probe set at ~500 ms on the first 3 runs.  Hard cap 25 fresh
containers; stops early when >=3 pathological episodes and >=3 clean runs exist.

Diagnosis only.  No tuning, no geometry changes.
"""

from __future__ import annotations

import json
import os
import statistics
import sys
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parents[1]
_APP = "sept-clip-source-race-oracle"
_READ_MIB = 64
_QD = 4
_PROBE_MIB = 4
_TRIGGER_MS = 250
_CLEAN_PROBE_AT_MS = 500
_CLEAN_PROBE_RUNS = 3
_MAX_RUNS = 25
_NEED_EPISODES = 3
_NEED_CLEAN = 3
_RUN_TIMEOUT_S = 900
_FAST_MS = 100.0


def _workspace() -> dict[str, Any]:
    import tomllib

    target = tomllib.loads((_ROOT / "config" / "v2" / "modal_target.toml").read_text("utf-8"))
    wanted = str((target.get("modal") or {}).get("workspace_id") or "").strip()
    for registry in (
        _ROOT / ".git" / "comfymodal" / "modal_workspaces.json",
        _ROOT / ".modal_workspaces.json",
    ):
        if not registry.is_file():
            continue
        data = json.loads(registry.read_text("utf-8"))
        workspace = next(
            (w for w in data.get("workspaces", []) if str(w.get("id") or "") == wanted), None
        )
        if workspace and workspace.get("token_id") and workspace.get("token_secret"):
            return workspace
    raise RuntimeError(f"no credentials for destination workspace {wanted}")


def _valid(record: dict[str, Any]) -> bool:
    return bool(
        record.get("status") == "ok"
        and (record.get("env") or {}).get("syscall_impl") == "os.preadv"
        and record.get("physical_reads")
        and record.get("useful_bytes")
    )


def _probe_latency(probe_set: dict, name: str) -> float | None:
    entry = (probe_set.get("results") or {}).get(name)
    if not entry or entry.get("status") not in ("ok", "short"):
        return None
    return entry.get("latency_ms")


def _classify(r: dict) -> str:
    sets = [s for s in (r.get("probe_sets") or []) if s.get("kind") == "pathological"]
    if not sets:
        return "no-probe-set"
    ps = sets[0]
    a = _probe_latency(ps, "A_same_file_fresh_fd")
    b = _probe_latency(ps, "B_same_range_fresh_fd")
    c = _probe_latency(ps, "C_other_volume_file")
    d = _probe_latency(ps, "D_local_file")
    hb = r.get("heartbeat_max_gap_ms")
    hb_ok = (hb is None) or (hb < 200.0)
    blocked = ps.get("blocked") or {}
    # lead: did a diagnostic return before the blocked originals exited?
    reads = {str(x["worker"]): x for x in (r.get("reads") or [])}
    max_blocked_exit = None
    for w in blocked:
        rd = reads.get(str(w))
        if rd:
            max_blocked_exit = max(max_blocked_exit or 0, rd["preadv_exit_ns"])
    probe_ok = [v for v in (a, b, c, d) if v is not None]
    if not probe_ok:
        return "probe-failed"
    if b is not None and b < _FAST_MS and max_blocked_exit:
        return "CASE6_same_range_escaped"
    if a is not None and a < _FAST_MS and (c is None or c < _FAST_MS) and (d is None or d < _FAST_MS):
        return "CASE1_cohort_trapped" if hb_ok else "CASE5_sandbox_stall"
    if a is not None and a >= _FAST_MS and (c is None or c < _FAST_MS) and (d is None or d < _FAST_MS):
        return "CASE2_file_path"
    if a is not None and a >= _FAST_MS and c is not None and c >= _FAST_MS and (d is None or d < _FAST_MS):
        return "CASE3_volume_path"
    if d is not None and d >= _FAST_MS:
        return "CASE4_fs_path" if hb_ok else "CASE5_sandbox_stall"
    return "mixed"


def main() -> int:
    workspace = _workspace()
    os.environ["MODAL_TOKEN_ID"] = str(workspace["token_id"])
    os.environ["MODAL_TOKEN_SECRET"] = str(workspace["token_secret"])

    import modal

    out_dir = _ROOT / "cross_source_runs"
    out_dir.mkdir(exist_ok=True)
    fn = modal.Function.from_name(_APP, "run_cross_source_h100")
    try:
        handle = fn.with_options(timeout=_RUN_TIMEOUT_S)
    except Exception:
        handle = fn

    runs: list[dict[str, Any]] = []
    clean_probe_used = 0
    episodes = 0
    clean_runs = 0
    for i in range(1, _MAX_RUNS + 1):
        use_clean_probe = _CLEAN_PROBE_AT_MS if clean_probe_used < _CLEAN_PROBE_RUNS else 0
        attempt = f"cs-r{i:02d}"
        path = out_dir / f"{attempt}.json"
        if path.exists():
            try:
                existing = json.loads(path.read_text(encoding="utf-8"))
                if _valid(existing):
                    print(f"[cs] skip {attempt}", flush=True)
                    runs.append(existing)
                    continue
            except Exception:
                pass
        print(f"[cs] start {attempt} clean_probe_at={use_clean_probe}", flush=True)
        try:
            result = handle.remote(
                read_mib=_READ_MIB, qd=_QD, probe_mib=_PROBE_MIB,
                trigger_ms=_TRIGGER_MS, clean_probe_at_ms=use_clean_probe,
                attempt_id=attempt,
            )
            if not isinstance(result, dict):
                raise RuntimeError(f"returned {type(result).__name__}")
        except Exception as exc:
            result = {"status": "error", "error": f"{type(exc).__name__}:{exc}"[:400],
                      "attempt_id": attempt}
        if use_clean_probe:
            clean_probe_used += 1
        path.write_text(json.dumps(result, indent=2, sort_keys=True, default=str),
                        encoding="utf-8")
        runs.append(result)
        if result.get("status") == "ok":
            eps = len([s for s in (result.get("probe_sets") or [])
                       if s.get("kind") == "pathological"])
            episodes += eps
            if eps == 0:
                clean_runs += 1
        print(f"[cs] done {attempt} status={result.get('status')} "
              f"gbps={result.get('decimal_gbps')} max_ms={result.get('max_ms')} "
              f"probe_sets={result.get('probe_set_count')} episodes={episodes} clean={clean_runs}",
              flush=True)
        if episodes >= _NEED_EPISODES and clean_runs >= _NEED_CLEAN:
            print("[cs] goal met; stopping", flush=True)
            break

    ok = [r for r in runs if r.get("status") == "ok"]
    print()
    print("run | region | sick/clean | worst normal ms | workers sick at trigger | "
          "same-file ms | same-range ms | other-volume ms | local ms | hb max gap ms | "
          "originals exit after trigger ms | classification")
    for r in ok:
        psets = [s for s in (r.get("probe_sets") or []) if s.get("kind") == "pathological"]
        if psets:
            ps = psets[0]
            blocked = ps.get("blocked") or {}
            workers = sorted(blocked.keys(), key=int)
            reads = {str(x["worker"]): x for x in (r.get("reads") or [])}
            after = []
            for w in blocked:
                rd = reads.get(str(w))
                if rd:
                    after.append((rd["preadv_exit_ns"] - ps["trigger_ns"]) / 1e6)
            a = _probe_latency(ps, "A_same_file_fresh_fd")
            b = _probe_latency(ps, "B_same_range_fresh_fd")
            c = _probe_latency(ps, "C_other_volume_file")
            d = _probe_latency(ps, "D_local_file")
            fmt = lambda v: "-" if v is None else f"{v:.1f}"
            print(f"| {r.get('attempt_id')} | {r.get('provider')}/{r.get('region')} | SICK | "
                  f"{r.get('max_ms'):.0f} | {workers} | {fmt(a)} | {fmt(b)} | {fmt(c)} | {fmt(d)} | "
                  f"{(r.get('heartbeat_max_gap_ms') or 0):.1f} | "
                  f"{[round(x) for x in after]} | {_classify(r)} |")
        else:
            print(f"| {r.get('attempt_id')} | {r.get('provider')}/{r.get('region')} | clean | "
                  f"{r.get('max_ms'):.0f} | - | - | - | - | - | "
                  f"{(r.get('heartbeat_max_gap_ms') or 0):.1f} | - | - |")

    print()
    print("=== pathological episode detail ===")
    for r in ok:
        psets = [s for s in (r.get("probe_sets") or []) if s.get("kind") == "pathological"]
        if not psets:
            continue
        print(f"\n{r.get('attempt_id')} ({r.get('provider')}/{r.get('region')}) "
              f"gbps={r.get('decimal_gbps'):.3f} max={r.get('max_ms'):.0f} ms")
        reads = sorted(r["reads"], key=lambda x: x["preadv_enter_ns"])
        t0 = reads[0]["preadv_enter_ns"]
        for w in sorted({x["worker"] for x in reads}):
            for x in reads:
                if x["worker"] == w and x["preadv_ms"] >= 250:
                    print(f"  w{w} gen{x['gen']} enter={(x['preadv_enter_ns']-t0)/1e6:.0f} "
                          f"exit={(x['preadv_exit_ns']-t0)/1e6:.0f} ms={x['preadv_ms']:.1f} "
                          f"off={x['offset']}")
        for ps in psets:
            trig_rel = (ps["trigger_ns"] - t0) / 1e6
            print(f"  trigger at t={trig_rel:.0f} ms  blocked={ps.get('blocked')}")
            for name, entry in sorted((ps.get("results") or {}).items()):
                if entry.get("status") in ("ok", "short"):
                    rel = (entry["enter_ns"] - t0) / 1e6
                    print(f"    {name}: enter={rel:.0f} latency={entry['latency_ms']:.1f} ms "
                          f"path={entry.get('path')} off={entry.get('offset')} "
                          f"bytes={entry.get('bytes_returned')}")
                else:
                    print(f"    {name}: {entry.get('status')} {entry.get('error','')}")

    print()
    print("=== clean-reference probe sets ===")
    for r in ok:
        for ps in (r.get("probe_sets") or []):
            if ps.get("kind") != "clean_reference":
                continue
            parts = []
            for name, entry in sorted((ps.get("results") or {}).items()):
                parts.append(f"{name}={entry.get('latency_ms'):.1f}"
                             if entry.get("status") in ("ok", "short") else f"{name}={entry.get('status')}")
            print(f"  {r.get('attempt_id')} ({r.get('provider')}/{r.get('region')}): {parts}")

    print()
    print("=== heartbeat summary ===")
    for r in ok:
        print(f"  {r.get('attempt_id')}: samples={r.get('heartbeat_samples')} "
              f"median_gap={r.get('heartbeat_median_gap_ms'):.2f} ms "
              f"max_gap={(r.get('heartbeat_max_gap_ms') or 0):.1f} ms")
    return 0


if __name__ == "__main__":
    sys.exit(main())
