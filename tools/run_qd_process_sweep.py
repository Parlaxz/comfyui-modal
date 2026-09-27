#!/usr/bin/env python
"""QD5/6/7 process-architecture sweep: 10 valid non-Odin runs per arm.

Runs the persisted 3-arm schedule in order.  No provider or region pinning.
An odin run is preserved, marked INVALID_FOR_COUNTED_COHORT, and the SAME arm
in the SAME logical slot is rerun.

Architecture is unchanged from the validated process experiment: one reader
process per stream, one FD + one 64 MiB buffer + one static contiguous region
each, and ONE global process-shared 4.0 ms launch pacer across every physical
attempt (the pacer primitive is the same one already validated).

Validity gate (fail closed):
  qd matches the arm, 120 reads, exact once-only coverage, bytes match, no
  worker/barrier errors, max in-flight <= qd, 4.0 ms global claim floor, and
  the run did not land on odin.
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
_READ_MIB = 64
_GAP_MS = 4.0
_RUN_TIMEOUT_S = 1200
_WORKER_MODEL = "processes"
_REJECT_REGIONS = ("odin",)
_MAX_ATTEMPTS = 6
_EXPECTED_READS = 120
_PER_RUN_TIMEOUT_S = 240.0


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
    text = str(value or "").strip().lower()
    prefix = "cloud_provider_"
    return text[len(prefix):] if text.startswith(prefix) else text


def _load(path: Path) -> dict[str, Any] | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _accept(r: dict[str, Any], qd: int) -> tuple[bool, list[str]]:
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

    if str(ident.get("region") or "") in _REJECT_REGIONS:
        reasons.append(f"rejected_region={ident.get('region')}")
    if "H100" not in str(ident.get("observed_gpu") or ""):
        reasons.append("wrong_gpu")
    if str(r.get("worker_model") or cfg.get("worker_model")) != _WORKER_MODEL:
        reasons.append("worker_model_mismatch")
    if int(cfg.get("qd") or 0) != qd:
        reasons.append(f"qd={cfg.get('qd')}!={qd}")
    if int(r.get("physical_reads") or 0) != _EXPECTED_READS:
        reasons.append(f"reads={r.get('physical_reads')}")
    if int(cov.get("reads_expected") or -1) != _EXPECTED_READS:
        reasons.append(f"reads_expected={cov.get('reads_expected')}")
    if not cov.get("covers_entire_file_exactly_once"):
        reasons.append("coverage")
    if not cov.get("bytes_match"):
        reasons.append("bytes")
    if not cov.get("no_overlap"):
        reasons.append("overlap")
    if not cov.get("contiguous_cover"):
        reasons.append("contiguity")
    if not cov.get("all_reads_returned_full_length"):
        reasons.append("short_read")
    if not cov.get("all_workers_completed_region"):
        reasons.append("incomplete_region")
    if r.get("worker_errors"):
        reasons.append(f"worker_errors={r.get('worker_errors')}")
    if r.get("barrier_error"):
        reasons.append(f"barrier={r.get('barrier_error')}")
    mif = ls.get("max_simultaneous_in_flight")
    if mif is None or int(mif) > qd:
        reasons.append(f"max_in_flight={mif}>qd{qd}")
    gap = pac.get("observed_min_global_claim_gap_ms")
    if gap is None or float(gap) < _GAP_MS:
        reasons.append(f"claim_gap={gap}")
    return (not reasons), reasons


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-dir", default="qd_sweep_runs")
    parser.add_argument("--from-round", type=int, default=1)
    parser.add_argument("--max-rounds", type=int, default=10)
    parser.add_argument("--per-run-timeout", type=float, default=_PER_RUN_TIMEOUT_S)
    args = parser.parse_args()

    out = _ROOT / args.out_dir
    schedule = json.loads((out / "schedule.json").read_text(encoding="utf-8"))
    qd_by_arm = {str(k): int(v) for k, v in (schedule.get("qd_by_arm") or {}).items()}

    os.environ["MODAL_TOKEN_ID"] = str(_workspace()["token_id"])
    os.environ["MODAL_TOKEN_SECRET"] = str(_workspace()["token_secret"])
    import modal

    out.mkdir(parents=True, exist_ok=True)
    print(f"[qd] seed={schedule['seed']} rounds={schedule['rounds']} "
          f"qd_by_arm={qd_by_arm} pinned={schedule.get('pinned')}", flush=True)

    base = modal.Function.from_name(_APP, _FN).with_options(timeout=_RUN_TIMEOUT_S)
    per_run_timeout = float(args.per_run_timeout)

    def _invoke(arm: str, qd: int, round_no: int, ordinal: int) -> dict[str, Any]:
        call = base.spawn(
            read_mib=_READ_MIB,
            qd=qd,
            min_launch_gap_ms=_GAP_MS,
            worker_model=_WORKER_MODEL,
            attempt_id=f"qds-{arm}-r{round_no:02d}-o{ordinal:02d}",
            pin_cloud="",
            pin_region="",
        )
        try:
            return call.get(timeout=per_run_timeout)
        except BaseException:
            try:
                call.cancel()
            except BaseException:
                pass
            raise

    def _invalid_path(stem: str) -> Path:
        n = 1
        while True:
            candidate = out / f"{stem}-invalid{n}.json"
            if not candidate.exists():
                return candidate
            n += 1

    def run_slot(arm: str, qd: int, round_no: int, ordinal: int) -> tuple[dict[str, Any] | None, str]:
        stem = f"qd{qd}-r{round_no:02d}"
        canonical = out / f"{stem}.json"
        if canonical.exists():
            cached = _load(canonical)
            if cached is not None:
                ok, reasons = _accept(cached, qd)
                if ok:
                    print(f"[qd] cached {arm} r{round_no:02d} "
                          f"region={(cached.get('identity') or {}).get('region')} "
                          f"gbps={cached.get('full_file_decimal_gbps')}", flush=True)
                    return cached, "cached"
                canonical.rename(_invalid_path(stem))
                print(f"[qd] cached {arm} r{round_no:02d} INVALID {reasons} -> preserved",
                      flush=True)

        last: dict[str, Any] | None = None
        reasons: list[str] = ["no_attempt"]
        for attempt in range(1, _MAX_ATTEMPTS + 1):
            print(f"[qd] start {arm} r{round_no:02d} ord={ordinal} attempt={attempt} "
                  f"qd={qd} read_mib={_READ_MIB} gap={_GAP_MS}", flush=True)
            try:
                r: dict[str, Any] = _invoke(arm, qd, round_no, ordinal)
                if not isinstance(r, dict):
                    raise RuntimeError(f"returned {type(r).__name__}")
            except Exception as exc:
                r = {"status": "error", "error": f"{type(exc).__name__}:{exc}"[:400],
                     "worker_model": _WORKER_MODEL, "attempt_id": stem}
            last = r
            ok, reasons = _accept(r, qd)
            if ok:
                canonical.write_text(json.dumps(r, indent=2, sort_keys=True, default=str),
                                     encoding="utf-8")
                ident = r.get("identity") or {}
                ls = r.get("launch_spacing") or {}
                print(f"[qd] done {arm} r{round_no:02d} provider={_norm_cloud(ident.get('provider'))} "
                      f"region={ident.get('region')} wall={r.get('full_file_wall_ms')} "
                      f"gbps={r.get('full_file_decimal_gbps')} med={r.get('median_ms')} "
                      f"p95={r.get('p95_ms')} max={r.get('max_ms')} "
                      f"ge500={(r.get('thresholds') or {}).get('ge_500')} "
                      f"conc={ls.get('mean_effective_concurrency')} "
                      f"maxIF={ls.get('max_simultaneous_in_flight')} "
                      f"claim_gap={(r.get('pacer') or {}).get('observed_min_global_claim_gap_ms')} "
                      f"exact={(r.get('coverage') or {}).get('covers_entire_file_exactly_once')} "
                      f"pids={len(set(r.get('worker_pids') or []))}", flush=True)
                return r, f"accepted-attempt{attempt}"

            path = _invalid_path(stem)
            path.write_text(json.dumps(r, indent=2, sort_keys=True, default=str), encoding="utf-8")
            print(f"[qd] INVALID {arm} r{round_no:02d} attempt={attempt} reasons={reasons} "
                  f"-> preserved {path.name}", flush=True)

        return last, f"failed:{reasons}"

    accepted: list[tuple[str, int, int, dict[str, Any]]] = []
    problems: list[str] = []
    for entry in schedule["schedule"]:
        round_no = int(entry["round"])
        if round_no < args.from_round or round_no > args.max_rounds:
            continue
        for arm in entry["order"]:
            qd = qd_by_arm[arm]
            ordinal = int(entry["run_ordinals"][arm])
            r, status = run_slot(arm, qd, round_no, ordinal)
            if r is None or not status.startswith(("accepted", "cached")):
                problems.append(f"{arm} r{round_no:02d}: {status}")
            else:
                accepted.append((arm, qd, round_no, r))

    print(f"\n[qd] accepted {len(accepted)} / {(args.max_rounds - args.from_round + 1) * len(qd_by_arm)}")
    for arm, qd in sorted(qd_by_arm.items(), key=lambda kv: kv[1]):
        rows = [r for a, _, _, r in accepted if a == arm]
        if not rows:
            print(f"  {arm:<5} NO RUNS")
            continue
        gbps = [float(r["full_file_decimal_gbps"]) for r in rows]
        wall = [float(r["full_file_wall_ms"]) for r in rows]
        print(f"  {arm:<5} n={len(rows)} gbps med={statistics.median(gbps):.3f} "
              f"mean={statistics.fmean(gbps):.3f} best={max(gbps):.3f} worst={min(gbps):.3f} | "
              f"wall med={statistics.median(wall):.0f} mean={statistics.fmean(wall):.0f} "
              f"best={min(wall):.0f} worst={max(wall):.0f}")
    regions: dict[str, int] = {}
    for _, _, _, r in accepted:
        ident = r.get("identity") or {}
        key = f"{_norm_cloud(ident.get('provider'))}:{ident.get('region')}"
        regions[key] = regions.get(key, 0) + 1
    print(f"  regions: {regions}")
    if problems:
        print(f"  PROBLEM SLOTS: {problems}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
