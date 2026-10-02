#!/usr/bin/env python
"""Paired THREADS-vs-PROCESSES campaign: 10 fresh H100 runs per arm.

Runs the persisted paired schedule in order.  Each counted observation uses a
fresh single-use H100 container.

Provider pinning: when the schedule carries a (cloud, region) per round, BOTH
arms of that round are pinned to it via ``Function.with_options(cloud=...,
region=...)``.  Cloud is restricted to aws/gcp, so Modal's own regions (odin,
denver) and oci (us-chicago-1, us-ashburn-1) cannot appear, and each pair is
region-matched by construction.

Validity gate (both arms must prove the source geometry is unchanged):
  configured qd == 4, exactly 120 reads, exact once-only file coverage, no
  worker/barrier errors, max in-flight <= 4, the 4.0 ms global pacer floor
  honoured on claim-to-claim gaps, and the observed region/provider equal to
  the pinned values.
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parents[1]
_APP = "sept-clip-source-race-oracle"
_FN = "run_worker_model_h100"
_PROBE_FN = "probe_platform"
_QD = 4
_READ_MIB = 64
_GAP_MS = 4.0
_RUN_TIMEOUT_S = 1200
_ALLOWED_CLOUDS = ("aws", "gcp")
# Unpinned campaign rule: an odin run is not a usable observation.  It is
# preserved as evidence and the SAME slot is rerun.
_REJECT_REGIONS = ("odin",)
_MAX_ATTEMPTS = 6
# Bounded client-side wait.  A pinned region with no H100 capacity would
# otherwise block indefinitely; warm runs in this experiment complete in ~20 s.
_PER_RUN_TIMEOUT_S = 300.0


def _workspace() -> dict[str, Any]:
    import tomllib

    t = tomllib.loads((_ROOT / "config" / "v2" / "modal_target.toml").read_text("utf-8"))
    wanted = str((t.get("modal") or {}).get("workspace_id") or "").strip()
    for reg in (_ROOT / ".git" / "comfymodal" / "modal_workspaces.json",
                _ROOT / ".modal_workspaces.json"):
        if not reg.is_file():
            continue
        d = json.loads(reg.read_text("utf-8"))
        ws = next((w for w in d.get("workspaces", []) if str(w.get("id") or "") == wanted), None)
        if ws and ws.get("token_id") and ws.get("token_secret"):
            return ws
    raise RuntimeError(f"no credentials for workspace {wanted}")


def _norm_cloud(value: Any) -> str:
    """Modal reports the provider as the proto enum name, e.g. CLOUD_PROVIDER_AWS."""
    text = str(value or "").strip().lower()
    prefix = "cloud_provider_"
    if text.startswith(prefix):
        text = text[len(prefix):]
    return text


def _load(path: Path) -> dict[str, Any] | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _accept(r: dict[str, Any], arm: str, cloud: str, region: str) -> tuple[bool, list[str]]:
    if not isinstance(r, dict):
        return False, ["not_a_dict"]
    if r.get("status") != "ok":
        return False, [f"status={r.get('status')}:{r.get('error')}"]
    reasons: list[str] = []
    cfg = r.get("config") or {}
    cov = r.get("coverage") or {}
    ls = r.get("launch_spacing") or {}
    pac = r.get("pacer") or {}
    ident = r.get("identity") or {}

    if "H100" not in str(ident.get("observed_gpu") or ""):
        reasons.append("wrong_gpu")
    if str(r.get("worker_model") or cfg.get("worker_model")) != arm:
        reasons.append("arm_mismatch")
    if int(cfg.get("qd") or 0) != _QD:
        reasons.append(f"qd={cfg.get('qd')}")
    if int(r.get("physical_reads") or 0) != int(cov.get("reads_expected") or -1):
        reasons.append(f"reads={r.get('physical_reads')}")
    if not cov.get("covers_entire_file_exactly_once"):
        reasons.append("coverage")
    if not cov.get("bytes_match"):
        reasons.append("bytes")
    if r.get("worker_errors"):
        reasons.append(f"worker_errors={r.get('worker_errors')}")
    if r.get("barrier_error"):
        reasons.append(f"barrier={r.get('barrier_error')}")
    mif = ls.get("max_simultaneous_in_flight")
    if mif is not None and int(mif) > _QD:
        reasons.append(f"max_in_flight={mif}")
    gap = pac.get("observed_min_global_claim_gap_ms")
    if gap is None or float(gap) < _GAP_MS:
        reasons.append(f"claim_gap={gap}")
    if str(ident.get("region") or "") in _REJECT_REGIONS:
        reasons.append(f"rejected_region={ident.get('region')}")
    if cloud or region:
        obs_cloud = _norm_cloud(ident.get("provider"))
        if cloud and obs_cloud != cloud:
            reasons.append(f"cloud={obs_cloud}!={cloud}")
        if region and str(ident.get("region") or "") != region:
            reasons.append(f"region={ident.get('region')}!={region}")
        if cloud and cloud not in _ALLOWED_CLOUDS:
            reasons.append(f"disallowed_pin={cloud}")
        if obs_cloud and obs_cloud not in _ALLOWED_CLOUDS:
            reasons.append(f"disallowed_cloud={obs_cloud}")
    return (not reasons), reasons


def preflight(pairs: set[tuple[str, str]]) -> bool:
    import modal

    probe = modal.Function.from_name(_APP, _PROBE_FN)
    ok_all = True
    for cloud, region in sorted(pairs):
        if not cloud:
            continue
        try:
            r = probe.with_options(cloud=cloud, region=region).remote()
            hits = (r or {}).get("env_hits") or {}
            obs_cloud = _norm_cloud(hits.get("MODAL_CLOUD_PROVIDER", ""))
            obs_region = str(hits.get("MODAL_REGION", ""))
            good = obs_cloud == cloud and (not region or obs_region == region)
            ok_all = ok_all and good
            print(f"[pf] {cloud}:{region:<14} -> provider={obs_cloud!r} region={obs_region!r} "
                  f"{'OK' if good else 'MISMATCH'}", flush=True)
        except Exception as exc:
            ok_all = False
            print(f"[pf] {cloud}:{region:<14} -> FAILED {type(exc).__name__}:{str(exc)[:160]}",
                  flush=True)
    return ok_all


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-dir", default="worker_model_runs")
    parser.add_argument("--max-rounds", type=int, default=10)
    parser.add_argument("--from-round", type=int, default=1)
    parser.add_argument("--per-run-timeout", type=float, default=_PER_RUN_TIMEOUT_S)
    parser.add_argument("--preflight", action="store_true")
    args = parser.parse_args()

    per_run_timeout = float(args.per_run_timeout)

    out = _ROOT / args.out_dir
    schedule_path = out / "schedule.json"
    schedule = json.loads(schedule_path.read_text(encoding="utf-8"))
    pinned = bool(schedule.get("pinned"))

    os.environ["MODAL_TOKEN_ID"] = str(_workspace()["token_id"])
    os.environ["MODAL_TOKEN_SECRET"] = str(_workspace()["token_secret"])
    import modal

    out.mkdir(parents=True, exist_ok=True)
    print(f"[wm] schedule={schedule_path.name} seed={schedule['seed']} "
          f"rounds={schedule['rounds']} pinned={pinned} "
          f"threads_first={schedule['threads_first']} processes_first={schedule['processes_first']}",
          flush=True)
    if pinned:
        print(f"[wm] region_counts={schedule.get('region_counts')}", flush=True)

    pairs = {(str(s.get("cloud") or ""), str(s.get("region") or ""))
             for s in schedule["schedule"]}
    if args.preflight and pinned:
        print("[wm] preflight:", flush=True)
        if not preflight(pairs):
            print("[wm] PREFLIGHT FAILED — aborting before any counted run", flush=True)
            return 2

    base = modal.Function.from_name(_APP, _FN)
    handles: dict[tuple[str, str], Any] = {}

    def _handle_for(cloud: str, region: str):
        key = (cloud, region)
        if key not in handles:
            kwargs: dict[str, Any] = {"timeout": _RUN_TIMEOUT_S}
            if cloud:
                kwargs["cloud"] = cloud
            if region:
                kwargs["region"] = region
            handles[key] = base.with_options(**kwargs)
        return handles[key]

    def _invoke(handle, arm: str, round_no: int, ordinal: int,
                cloud: str, region: str) -> dict[str, Any]:
        call = handle.spawn(
            read_mib=_READ_MIB,
            qd=_QD,
            min_launch_gap_ms=_GAP_MS,
            worker_model=arm,
            attempt_id=f"wm-{arm}-r{round_no:02d}-o{ordinal:02d}",
            pin_cloud=cloud,
            pin_region=region,
        )
        try:
            return call.get(timeout=per_run_timeout)
        except BaseException:
            try:
                call.cancel()
            except BaseException:
                pass
            raise

    def _next_invalid_path(name: str) -> Path:
        n = 1
        while True:
            candidate = out / f"{name}-invalid{n}.json"
            if not candidate.exists():
                return candidate
            n += 1

    def run_slot(arm: str, round_no: int, ordinal: int,
                 cloud: str, region: str) -> tuple[dict[str, Any] | None, str]:
        stem = f"wm-{arm}-r{round_no:02d}"
        canonical = out / f"{stem}.json"
        if canonical.exists():
            cached = _load(canonical)
            if cached is not None:
                ok, reasons = _accept(cached, arm, cloud, region)
                if ok:
                    print(f"[wm] cached {arm} r{round_no:02d} "
                          f"region={(cached.get('identity') or {}).get('region')} "
                          f"gbps={cached.get('full_file_decimal_gbps')}", flush=True)
                    return cached, "cached"
                canonical.rename(_next_invalid_path(stem))
                print(f"[wm] cached {arm} r{round_no:02d} INVALID {reasons} -> preserved",
                      flush=True)

        handle = _handle_for(cloud, region)
        last: dict[str, Any] | None = None
        reasons: list[str] = ["no_attempt"]
        for attempt in range(1, _MAX_ATTEMPTS + 1):
            where = f"{cloud}:{region}" if cloud else "auto"
            print(f"[wm] start {arm} r{round_no:02d} ord={ordinal} attempt={attempt} "
                  f"pin={where} qd={_QD} read_mib={_READ_MIB} gap={_GAP_MS}", flush=True)
            try:
                r: dict[str, Any] = _invoke(handle, arm, round_no, ordinal, cloud, region)
                if not isinstance(r, dict):
                    raise RuntimeError(f"returned {type(r).__name__}")
            except Exception as exc:
                r = {"status": "error", "error": f"{type(exc).__name__}:{exc}"[:400],
                     "worker_model": arm, "attempt_id": f"{stem}"}
            last = r
            ok, reasons = _accept(r, arm, cloud, region)
            if ok:
                canonical.write_text(json.dumps(r, indent=2, sort_keys=True, default=str),
                                     encoding="utf-8")
                ident = r.get("identity") or {}
                print(f"[wm] done {arm} r{round_no:02d} "
                      f"provider={ident.get('provider')} region={ident.get('region')} "
                      f"wall={r.get('full_file_wall_ms')} gbps={r.get('full_file_decimal_gbps')} "
                      f"med={r.get('median_ms')} p95={r.get('p95_ms')} max={r.get('max_ms')} "
                      f"ge500={(r.get('thresholds') or {}).get('ge_500')} "
                      f"conc={(r.get('launch_spacing') or {}).get('mean_effective_concurrency')} "
                      f"claim_gap={(r.get('pacer') or {}).get('observed_min_global_claim_gap_ms')} "
                      f"exact={(r.get('coverage') or {}).get('covers_entire_file_exactly_once')} "
                      f"pids={r.get('worker_pids')}", flush=True)
                return r, f"accepted-attempt{attempt}"

            path = _next_invalid_path(stem)
            path.write_text(json.dumps(r, indent=2, sort_keys=True, default=str), encoding="utf-8")
            print(f"[wm] INVALID {arm} r{round_no:02d} attempt={attempt} reasons={reasons} "
                  f"-> preserved {path.name}", flush=True)

        return last, f"failed:{reasons}"

    accepted: list[tuple[str, int, dict[str, Any]]] = []
    problems: list[str] = []
    for entry in schedule["schedule"]:
        round_no = int(entry["round"])
        if round_no < args.from_round or round_no > args.max_rounds:
            continue
        cloud = str(entry.get("cloud") or "")
        region = str(entry.get("region") or "")
        for arm in entry["order"]:
            ordinal = int(entry["run_ordinals"][arm])
            r, status = run_slot(arm, round_no, ordinal, cloud, region)
            if r is None or not status.startswith(("accepted", "cached")):
                problems.append(f"{arm} r{round_no:02d}: {status}")
            else:
                accepted.append((arm, round_no, r))

    print(f"\n[wm] accepted {len(accepted)} / {args.max_rounds * 2}")
    for arm in ("threads", "processes"):
        rows = [r for a, _, r in accepted if a == arm]
        if not rows:
            print(f"  {arm:<10} NO RUNS")
            continue
        gbps = [float(r["full_file_decimal_gbps"]) for r in rows]
        wall = [float(r["full_file_wall_ms"]) for r in rows]
        print(f"  {arm:<10} n={len(rows)} gbps med={statistics.median(gbps):.3f} "
              f"mean={statistics.fmean(gbps):.3f} best={max(gbps):.3f} worst={min(gbps):.3f} | "
              f"wall med={statistics.median(wall):.0f} mean={statistics.fmean(wall):.0f} "
              f"best={min(wall):.0f} worst={max(wall):.0f}")
    regions: dict[str, int] = {}
    for _, _, r in accepted:
        key = f"{(r.get('identity') or {}).get('provider')}:{(r.get('identity') or {}).get('region')}"
        regions[key] = regions.get(key, 0) + 1
    print(f"  regions: {regions}")
    if problems:
        print(f"  PROBLEM SLOTS: {problems}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
