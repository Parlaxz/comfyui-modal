#!/usr/bin/env python
"""QD4 static-partition imbalance campaign: 25 fresh valid non-Odin H100 runs.

Architecture is frozen at the current winning process path: 4 reader processes,
1 stream each, 1 FD + 1 buffer + 1 static contiguous region each, 64 MiB reads,
one global process-shared 4.0 ms launch pacer.

No provider/region pinning.  An odin run is preserved, marked invalid for the
counted cohort, and the SAME logical slot is rerun.

No architecture change: no work stealing, no dynamic assignment, no hedging,
no QD change, no block-size change, no pacing change.
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
_QD = 4
_READ_MIB = 64
_GAP_MS = 4.0
_WORKER_MODEL = "processes"
_HEDGED_MODEL = "processes_hedged"
_SLOTS = 25
_EXPECTED_READS = 120
_REJECT_REGIONS = ("odin",)
# Odin rejection rate is highly variable (observed ~30% and ~67% in different
# windows), so a slot must be allowed many retries before it is abandoned.
_MAX_ATTEMPTS = 30
# Odin rejection is a transient region lottery and is worth many retries.
# Every OTHER validity failure is DETERMINISTIC (an engine/schema defect or a
# genuine run defect) and will fail identically forever.  Those get NO retry.
_NONODIN_ATTEMPTS = 1
# Campaign-level circuit breaker: if this many slots in a row fail for
# deterministic reasons, the campaign itself is broken -> abort entirely.
# This bounds the cost of any systematic defect to a couple of runs instead of
# slots x attempts.
_CAMPAIGN_ABORT_AFTER = 1
# The engine result MUST carry these keys for the shared validity gate to work.
# A missing key is reported as a distinct schema failure, not a run failure.
_REQUIRED_RESULT_KEYS = (
    "status", "worker_model", "physical_reads", "coverage", "reads",
    "pacer", "launch_spacing",
)
_RUN_TIMEOUT_S = 1200
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


def _accept(r: dict[str, Any], expect_model: str, maxif_cap: int,
            expect_qd: int = _QD, expect_reads: int | None = None,
            expect_gap_ms: float = _GAP_MS,
            expect_gpu: str = "H100") -> tuple[bool, list[str]]:
    if not isinstance(r, dict):
        return False, ["not_a_dict"]
    if r.get("status") != "ok":
        return False, [f"status={r.get('status')}:{r.get('error')}"]
    reasons: list[str] = []
    missing = [k for k in _REQUIRED_RESULT_KEYS if k not in r]
    if missing:
        reasons.append(f"schema_missing={missing}")
    cfg = r.get("config") or {}
    cov = r.get("coverage") or {}
    ls = r.get("launch_spacing") or {}
    pac = r.get("pacer") or {}
    ident = r.get("identity") or {}

    if str(ident.get("region") or "") in _REJECT_REGIONS:
        reasons.append(f"rejected_region={ident.get('region')}")
    if expect_gpu.lower() not in str(ident.get("observed_gpu") or "").lower():
        reasons.append("wrong_gpu")
    if str(r.get("worker_model") or cfg.get("worker_model")) != expect_model:
        reasons.append("worker_model_mismatch")
    if int(cfg.get("qd") or 0) != expect_qd:
        reasons.append(f"qd={cfg.get('qd')}")
    if expect_reads is not None and int(r.get("physical_reads") or 0) != expect_reads:
        reasons.append(f"reads={r.get('physical_reads')}")
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
    # Only meaningful if the engine actually reports the field: the mmap
    # lifecycle engine does not emit all_workers_completed_region, and an
    # absent key must not be recorded as a completeness failure.
    if "all_workers_completed_region" in cov and not cov.get("all_workers_completed_region"):
        reasons.append("incomplete_region")
    if r.get("worker_errors"):
        reasons.append(f"worker_errors={r.get('worker_errors')}")
    if r.get("barrier_error"):
        reasons.append(f"barrier={r.get('barrier_error')}")
    mif = ls.get("max_simultaneous_in_flight")
    if mif is None or int(mif) > maxif_cap:
        reasons.append(f"max_in_flight={mif}>{maxif_cap}")
    gap = pac.get("observed_min_global_claim_gap_ms")
    if gap is None or float(gap) < expect_gap_ms:
        reasons.append(f"claim_gap={gap}")
    return (not reasons), reasons


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-dir", default="imbalance_runs")
    parser.add_argument("--from-slot", type=int, default=1)
    parser.add_argument("--to-slot", type=int, default=_SLOTS)
    parser.add_argument("--per-run-timeout", type=float, default=_PER_RUN_TIMEOUT_S)
    parser.add_argument("--hedge-delay-ms", type=float, default=0.0)
    parser.add_argument("--hedge-slots", type=int, default=3)
    parser.add_argument("--witness", action="store_true")
    parser.add_argument("--hedge-process", action="store_true")
    parser.add_argument("--hedge-alt-file", default="")
    parser.add_argument("--hedge-shift-blocks", type=int, default=0)
    parser.add_argument("--allocator", action="store_true")
    parser.add_argument("--selfservice", action="store_true")
    parser.add_argument("--split-arm", default="none", choices=["none", "2x64", "4x32"])
    parser.add_argument("--mmap-mode", default="none", choices=["none", "m0", "m1", "m2"])
    parser.add_argument("--odirect", action="store_true")
    parser.add_argument("--wall-profile", action="store_true")
    parser.add_argument("--m0-rescue", action="store_true")
    parser.add_argument("--mmap-src", default="none", choices=["none", "persistent", "window"])
    parser.add_argument("--consume-mode", default="memcpy",
                        choices=["memcpy", "d0", "d1", "d2"])
    parser.add_argument("--touch-ahead", type=int, default=0, choices=[0, 1, 2])
    parser.add_argument("--touch-pattern", action="store_true",
                        help="assign touch_ahead per slot from the balanced T0/T1/T2 schedule")
    parser.add_argument("--mmap-pattern", action="store_true",
                        help="assign mmap_src per slot (persistent/window) in a balanced interleave")
    parser.add_argument("--consume-pattern", action="store_true",
                        help="assign consume_mode per slot (memcpy/d0/d1/d2) in a balanced interleave")
    parser.add_argument("--source-pattern", action="store_true",
                        help="alternate ENGINE per slot: preadv (P) vs exact-window mmap (M2)")
    parser.add_argument("--fn", default=_FN, help="Modal function name to target")
    parser.add_argument("--lifecycle", default="none",
                        choices=["none", "whole", "segmented", "fresh"])
    parser.add_argument("--populate", action="store_true")
    parser.add_argument("--populate-pattern", action="store_true",
                        help="alternate MAP_POPULATE on/off per slot (inert-flag sanity check)")
    parser.add_argument("--parallel", type=int, default=1,
                        help=("concurrent Modal containers for slot fan-out. DEFAULT 1 (serial): "
                              "the source path is placement/backend sensitive, so running many "
                              "containers at once risks backend contention contaminating the very "
                              "throughput and tail measurements we are taking. Raise only if "
                              "contention is explicitly being studied."))
    parser.add_argument("--size-pattern", action="store_true",
                        help=("assign (read_mib, gap_ms) per slot from the balanced size sweep: "
                              "32/2ms, 64/4ms, 128/8ms, 256/16ms"))
    parser.add_argument("--deferred-unmap", action="store_true",
                        help=("fresh-window mmap with munmap moved OFF the source critical path: "
                              "mmap -> memcpy -> enqueue retire -> continue, with a bounded "
                              "in-process reaper thread (max --max-retired per reader) doing the "
                              "munmap. Geometry stays LOCKED at 64 MiB / QD4. Reports both the "
                              "source-ready wall and the fully-drained wall."))
    parser.add_argument("--max-retired", type=int, default=2,
                        help="max retired mappings queued per reader before the source worker "
                             "waits for retirement capacity (deferred-unmap only).")
    parser.add_argument("--map-shared", action="store_true",
                        help=("use read-only MAP_SHARED instead of MAP_PRIVATE for the fresh-window "
                              "mmap. Everything else identical."))
    parser.add_argument("--cpu-instrument", action="store_true",
                        help=("record per-block memcpy CPU time and CPU fraction around the memcpy "
                              "(per-thread CPU time, falling back to process CPU time). OPT-IN: with "
                              "this off the source path is byte-identical."))
    parser.add_argument("--mapshare-pattern", action="store_true",
                        help=("MAP_PRIVATE vs MAP_SHARED arms, 30 rounds of 2 cells, each round a "
                              "different permutation (seed 20261004). Geometry stays LOCKED at "
                              "64 MiB / QD4 / 4 ms / fresh-window."))
    parser.add_argument("--affinity", action="store_true",
                        help="pin each reader process to its own distinct allowed CPU.")
    parser.add_argument("--fixed-va", action="store_true",
                        help=("reserve one private 64 MiB VA slot per reader and replace the file "
                              "window in it via MAP_FIXED (one final munmap)."))
    parser.add_argument("--affinity-pattern", action="store_true",
                        help=("A=no affinity vs B=per-reader CPU pin, 30 balanced rounds "
                              "(seed 20261005). Geometry LOCKED."))
    parser.add_argument("--fixedva-pattern", action="store_true",
                        help=("A=normal mmap/munmap vs B=owned fixed-VA window replacement, "
                              "30 balanced rounds (seed 20261006). Geometry LOCKED."))
    parser.add_argument("--matrix", action="store_true",
                        help=("full geometry matrix: {32,64,128,256} MiB x QD{4,6,8}, 20 rounds of "
                              "12 cells, each round a different permutation so no arm runs in a "
                              "contiguous batch. Spacing stays byte-normalized (rm/16 ms)."))
    parser.add_argument("--matrix2", action="store_true",
                        help=("targeted geometry matrix #2 (extend the ACTIVE mmap boundaries): "
                              "16MiB QD6/8/10/12, 32MiB QD8/10/12, 64MiB QD4/5/6/7. 20 rounds of "
                              "11 cells, each round a different permutation (seed 20261002), so no "
                              "arm runs in a contiguous batch. Spacing stays byte-normalized "
                              "(rm/16 ms: 16->1, 32->2, 64->4). 128/256 MiB are NOT revisited."))
    parser.add_argument("--pace-pattern", action="store_true",
                        help=("pacing arms P0/P2/P4 = 0/2/4 ms intentional global start spacing, "
                              "geometry LOCKED at 64 MiB / QD4 / fresh-window. 30 rounds of 3 arms, "
                              "each round a different permutation (seed 20261003), so no pacing arm "
                              "gets one particular time/placement section. 0 ms removes ONLY the "
                              "spacing floor (_alloc_gate returns immediately at gap_ns=0); nothing "
                              "else changes."))
    parser.add_argument("--lifecycle-pattern", action="store_true",
                        help="assign lifecycle per slot (whole/segmented/fresh) in a balanced interleave")
    parser.add_argument("--gap-ms", type=float, default=None,
                        help="override the global minimum physical-start spacing")
    parser.add_argument("--gap-pattern", action="store_true",
                        help="assign per-slot spacing from the predetermined balanced schedule")
    parser.add_argument("--read-mib", type=int, default=_READ_MIB)
    parser.add_argument("--qd", type=int, default=_QD)
    parser.add_argument("--no-sticky-lanes", action="store_true")
    args = parser.parse_args()

    hedge_delay_ms = float(args.hedge_delay_ms)
    hedge_slots = int(args.hedge_slots)
    hedged = hedge_delay_ms > 0.0
    witness = bool(args.witness)
    hedge_process = bool(args.hedge_process)
    allocator = bool(args.allocator)
    selfservice = bool(args.selfservice)
    split_arm = str(args.split_arm)
    mmap_mode = str(args.mmap_mode)
    odirect = bool(args.odirect)
    wall_profile = bool(args.wall_profile)
    m0_rescue = bool(args.m0_rescue)
    mmap_src = str(args.mmap_src)
    consume_mode = str(args.consume_mode)
    touch_ahead = int(args.touch_ahead)
    read_mib = int(args.read_mib)
    qd = int(args.qd)
    if args.deferred_unmap:
        expect_model = "deferred_unmap"
        maxif_cap = qd
    elif str(args.lifecycle) in ("whole", "segmented", "fresh"):
        expect_model = "mmap_lifecycle"
        maxif_cap = qd
    elif mmap_src in ("persistent", "window"):
        expect_model = "mmap_source"
        maxif_cap = qd
    elif m0_rescue:
        expect_model = "m0_rescue"
        maxif_cap = 2 * qd
    elif wall_profile:
        expect_model = "wall_profile"
        maxif_cap = qd
    elif odirect:
        expect_model = "odirect_rescue"
        maxif_cap = qd + 1
    elif mmap_mode in ("m0", "m1", "m2"):
        expect_model = "mmap_path"
        maxif_cap = qd
    elif split_arm in ("2x64", "4x32"):
        expect_model = "split_rescue"
        maxif_cap = qd
    elif selfservice:
        expect_model = "selfservice_allocator"
        maxif_cap = qd
    elif allocator:
        expect_model = "greedy_allocator"
        maxif_cap = qd
    elif witness:
        expect_model = "processes_witness"
        maxif_cap = _QD
    elif hedge_process:
        # qd originals + at most 1 in-flight hedge served by the 5th process
        expect_model = "processes_hedge_process"
        maxif_cap = _QD + 1
    elif hedged:
        expect_model = _HEDGED_MODEL
        maxif_cap = _QD * (1 + hedge_slots)
    else:
        expect_model = _WORKER_MODEL
        maxif_cap = _QD

    out = _ROOT / args.out_dir
    out.mkdir(parents=True, exist_ok=True)
    plan_path = out / "plan.json"
    if not plan_path.exists():
        plan_path.write_text(json.dumps({
            "kind": "qd4_static_partition_imbalance",
            "slots": _SLOTS,
            "qd": _QD,
            "worker_model": expect_model,
            "read_mib": _READ_MIB,
            "min_launch_gap_ms": _GAP_MS,
            "hedge_delay_ms": hedge_delay_ms,
            "hedge_slots_per_worker": hedge_slots,
            "pinned": False,
            "reject_regions": list(_REJECT_REGIONS),
            "note": ("Static QD4 process regions, unchanged. "
                     + (f"Delayed hedging ON at {hedge_delay_ms:.0f} ms."
                        if hedged else "Hedging OFF.")),
        }, indent=2, sort_keys=True), encoding="utf-8")

    os.environ["MODAL_TOKEN_ID"] = str(_workspace()["token_id"])
    os.environ["MODAL_TOKEN_SECRET"] = str(_workspace()["token_secret"])
    import modal

    base = modal.Function.from_name(_APP, str(args.fn)).with_options(timeout=_RUN_TIMEOUT_S)
    per_run_timeout = float(args.per_run_timeout)
    print(f"[im] qd={_QD} model={_WORKER_MODEL} read_mib={_READ_MIB} gap={_GAP_MS} "
          f"slots={args.from_slot}..{args.to_slot} pinned=False", flush=True)

    # Predetermined balanced interleave: 3x5 ms and 3x6 ms per 6 slots.
    _GAP_PATTERN = (5.0, 6.0, 6.0, 5.0, 5.0, 6.0)
    # Predetermined balanced interleave for the T0/T1/T2 toucher arms.
    _TOUCH_PATTERN = (0, 1, 2, 2, 1, 0)

    def _touch_for(slot: int) -> int:
        if args.touch_pattern:
            return _TOUCH_PATTERN[(slot - 1) % len(_TOUCH_PATTERN)]
        return int(args.touch_ahead)

    # Balanced M0/M2 interleave.
    _MMAP_PATTERN = ("persistent", "window", "window", "persistent")

    def _mmap_for(slot: int) -> str:
        if args.mmap_pattern:
            return _MMAP_PATTERN[(slot - 1) % len(_MMAP_PATTERN)]
        return str(args.mmap_src)

    # Balanced memcpy/D0/D1/D2 interleave.
    _CONSUME_PATTERN = ("memcpy", "d0", "d1", "d2", "d2", "d1", "d0", "memcpy")

    def _consume_for(slot: int) -> str:
        if args.consume_pattern:
            return _CONSUME_PATTERN[(slot - 1) % len(_CONSUME_PATTERN)]
        return str(args.consume_mode)

    # Balanced engine interleave: preadv (P) vs exact-window mmap (M2).
    _SOURCE_PATTERN = ("preadv", "m2", "m2", "preadv", "preadv", "m2")

    def _source_for(slot: int):
        if args.source_pattern:
            return _SOURCE_PATTERN[(slot - 1) % len(_SOURCE_PATTERN)]
        return None

    # Balanced A/B/C lifecycle interleave.
    _LIFECYCLE_PATTERN = ("whole", "segmented", "fresh", "fresh", "segmented", "whole")

    def _lifecycle_for(slot: int) -> str:
        if args.lifecycle_pattern:
            return _LIFECYCLE_PATTERN[(slot - 1) % len(_LIFECYCLE_PATTERN)]
        return str(args.lifecycle)

    def _populate_for(slot: int) -> bool:
        if args.populate_pattern:
            return ((slot - 1) % 2) == 0
        return bool(args.populate)

    # Balanced mmap window-size sweep.  Spacing scales with window size so the
    # byte launch rate stays ~constant; this is geometry isolation, NOT a pacing
    # optimum (pacing is optimised separately later).
    _SIZE_ARMS = ((32, 2.0), (64, 4.0), (128, 8.0), (256, 16.0))
    _SIZE_PATTERN = (0, 1, 2, 3, 3, 2, 1, 0)

    def _size_for(slot: int):
        if args.size_pattern:
            return _SIZE_ARMS[_SIZE_PATTERN[(slot - 1) % len(_SIZE_PATTERN)]]
        return (int(args.read_mib), None)

    # Full geometry matrix: 20 rounds, each round a different permutation of all 12
    # cells, so no arm ever runs in a long contiguous batch and no arm is
    # systematically early or late.  Seeded so the launch sequence is reproducible.
    import random as _random
    _MATRIX_CELLS = [(rm, q) for rm in (32, 64, 128, 256) for q in (4, 6, 8)]
    _MATRIX_SCHEDULE: list = []
    _rng = _random.Random(20261001)
    for _round in range(20):
        _cells = list(_MATRIX_CELLS)
        _rng.shuffle(_cells)
        _MATRIX_SCHEDULE.extend(_cells)

    def _matrix_for(slot: int):
        rm, q = _MATRIX_SCHEDULE[(slot - 1) % len(_MATRIX_SCHEDULE)]
        return (rm, q, float(rm) / 16.0)

    # Targeted geometry matrix #2: extend the ACTIVE mmap geometry boundaries.
    # 16 MiB was never tested; 32 MiB was still improving at the QD8 boundary;
    # 64 MiB has a QD4-6-8 knee worth probing at QD5/QD7.  128/256 MiB are NOT
    # revisited (their high-QD behaviour is already characterised).
    # Same interleave discipline as the 12-cell matrix: 20 rounds, each round a
    # different permutation of all 11 cells, so no arm runs in a contiguous
    # batch and no arm is systematically early or late.  Spacing stays
    # byte-normalized (rm/16 ms) so this isolates GEOMETRY, not pacing.
    _MATRIX2_CELLS = [
        (16, 6), (16, 8), (16, 10), (16, 12),
        (32, 8), (32, 10), (32, 12),
        (64, 4), (64, 5), (64, 6), (64, 7),
    ]
    _MATRIX2_SCHEDULE: list = []
    _rng2 = _random.Random(20261002)
    for _round in range(20):
        _cells2 = list(_MATRIX2_CELLS)
        _rng2.shuffle(_cells2)
        _MATRIX2_SCHEDULE.extend(_cells2)

    def _matrix2_for(slot: int):
        rm, q = _MATRIX2_SCHEDULE[(slot - 1) % len(_MATRIX2_SCHEDULE)]
        return (rm, q, float(rm) / 16.0)

    # Pacing arms P0/P2/P4 = 0/2/4 ms intentional global start spacing.  Geometry
    # stays LOCKED at 64 MiB / QD4 / fresh-window; only the spacing floor moves.
    # Strong interleave: 30 rounds, each round a different permutation of the 3
    # arms (seed 20261003), so no arm gets a particular time/placement section.
    _PACE_ARMS = (0.0, 2.0, 4.0)
    _PACE_SCHEDULE: list = []
    _rng3 = _random.Random(20261003)
    for _round in range(30):
        _arms = list(_PACE_ARMS)
        _rng3.shuffle(_arms)
        _PACE_SCHEDULE.extend(_arms)

    def _pace_for(slot: int) -> float:
        return float(_PACE_SCHEDULE[(slot - 1) % len(_PACE_SCHEDULE)])

    # MAP_PRIVATE (A) vs read-only MAP_SHARED (B): geometry LOCKED, only the map
    # flag moves.  30 rounds, each round a different permutation of the 2 arms
    # (seed 20261004), so neither arm gets stuck in one placement/time section.
    _MAPSHARE_ARMS = (False, True)
    _MAPSHARE_SCHEDULE: list = []
    _rng4 = _random.Random(20261004)
    for _round in range(30):
        _arms = list(_MAPSHARE_ARMS)
        _rng4.shuffle(_arms)
        _MAPSHARE_SCHEDULE.extend(_arms)

    def _mapshare_for(slot: int) -> bool:
        return bool(_MAPSHARE_SCHEDULE[(slot - 1) % len(_MAPSHARE_SCHEDULE)])

    # A=no affinity vs B=per-reader CPU pin (seed 20261005), 30 balanced rounds.
    _AFF_ARMS = (False, True)
    _AFF_SCHEDULE: list = []
    _rng5 = _random.Random(20261005)
    for _round in range(30):
        _arms = list(_AFF_ARMS)
        _rng5.shuffle(_arms)
        _AFF_SCHEDULE.extend(_arms)

    def _affinity_for(slot: int) -> bool:
        return bool(_AFF_SCHEDULE[(slot - 1) % len(_AFF_SCHEDULE)])

    # A=normal mmap/munmap vs B=owned fixed-VA window replacement (seed 20261006).
    _FVA_ARMS = (False, True)
    _FVA_SCHEDULE: list = []
    _rng6 = _random.Random(20261006)
    for _round in range(30):
        _arms = list(_FVA_ARMS)
        _rng6.shuffle(_arms)
        _FVA_SCHEDULE.extend(_arms)

    def _fixedva_for(slot: int) -> bool:
        return bool(_FVA_SCHEDULE[(slot - 1) % len(_FVA_SCHEDULE)])

    def _gap_for(slot: int) -> float:
        if args.pace_pattern:
            return _pace_for(slot)
        if args.gap_pattern:
            return _GAP_PATTERN[(slot - 1) % len(_GAP_PATTERN)]
        if args.gap_ms is not None:
            return float(args.gap_ms)
        return float(_GAP_MS)

    def _cell_for(slot: int) -> tuple[int, int, float]:
        """(read_mib, qd, expected_gap_ms) this slot runs, for gate expectations."""
        if args.matrix:
            _rm, _q, _gm = _matrix_for(slot)
            return int(_rm), int(_q), float(_gm)
        if args.matrix2:
            _rm, _q, _gm = _matrix2_for(slot)
            return int(_rm), int(_q), float(_gm)
        return int(args.read_mib), int(qd), _gap_for(slot)

    def _invoke(slot: int) -> dict[str, Any]:
        src = _source_for(slot)
        if src == "preadv":
            (_model, _ss, _ms, _alloc, _mm, _split, _od, _wp, _m0) = (
                "selfservice_allocator", True, "none", False, "none", "none",
                False, False, False)
        elif src == "m2":
            (_model, _ss, _ms, _alloc, _mm, _split, _od, _wp, _m0) = (
                "mmap_source", False, "window", False, "none", "none",
                False, False, False)
        else:
            (_model, _ss, _ms) = (expect_model, selfservice, _mmap_for(slot))
            (_alloc, _mm, _split, _od, _wp, _m0) = (
                allocator, mmap_mode, split_arm, odirect, wall_profile, m0_rescue)
        lc = _lifecycle_for(slot)
        if lc != "none":
            (_model, _ss, _ms, _alloc, _mm, _split, _od, _wp, _m0) = (
                "mmap_lifecycle", False, "none", False, "none", "none",
                False, False, False)
        if args.matrix:
            _rm, _qd, _gm2 = _matrix_for(slot)
        elif args.matrix2:
            _rm, _qd, _gm2 = _matrix2_for(slot)
        else:
            _rm, _gm2 = _size_for(slot)
            _qd = qd
        call = base.spawn(
            read_mib=_rm, qd=_qd,
            min_launch_gap_ms=(_gm2 if _gm2 is not None else _gap_for(slot)),
            worker_model=_model, attempt_id=f"im-{slot:02d}",
            pin_cloud="", pin_region="",
            hedge_delay_ms=hedge_delay_ms, hedge_slots_per_worker=hedge_slots,
            witness=witness, hedge_process=hedge_process,
            hedge_alt_file=str(args.hedge_alt_file or ""),
            hedge_shift_blocks=int(args.hedge_shift_blocks),
            allocator=_alloc,
            sticky_lanes=not bool(args.no_sticky_lanes),
            selfservice=_ss,
            split_arm=_split,
            mmap_mode=_mm,
            odirect=_od,
            wall_profile=_wp,
            m0_rescue=_m0,
            mmap_src=_ms,
            consume_mode=_consume_for(slot),
            touch_ahead=_touch_for(slot),
            lifecycle=lc,
            populate=_populate_for(slot),
            deferred_unmap=bool(args.deferred_unmap),
            max_retired=int(args.max_retired),
            map_shared=(bool(_mapshare_for(slot)) if args.mapshare_pattern
                        else bool(args.map_shared)),
            cpu_instrument=bool(args.cpu_instrument),
            affinity=(bool(_affinity_for(slot)) if args.affinity_pattern
                      else bool(args.affinity)),
            fixed_va=(bool(_fixedva_for(slot)) if args.fixedva_pattern
                      else bool(args.fixed_va)),
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

    def run_slot(slot: int) -> tuple[dict[str, Any] | None, str]:
        stem = f"im-{slot:02d}"
        canonical = out / f"{stem}.json"
        if canonical.exists():
            cached = _load(canonical)
            if cached is not None:
                print(f"[im] cached {stem} "
                      f"region={(cached.get('identity') or {}).get('region')} "
                      f"gbps={cached.get('full_file_decimal_gbps')}", flush=True)
                return cached, "cached"

        print(f"[im] start {stem}", flush=True)
        try:
            r: dict[str, Any] = _invoke(slot)
            if not isinstance(r, dict):
                raise RuntimeError(f"returned {type(r).__name__}")
        except Exception as exc:
            r = {"status": "error", "error": f"{type(exc).__name__}:{exc}"[:400],
                 "worker_model": expect_model, "attempt_id": stem}

        # NO VALIDITY GATE IN THE CONTROL FLOW.
        # Exactly one invocation per slot: no retries, no aborts, so a defect
        # can never multiply into a retry storm.  The gate is now a RECORDER -
        # it writes advisory flags into the file and filtering happens at
        # analysis time, where it belongs.
        _rm_exp, _qd_exp, _gap_exp = _cell_for(slot)
        _fs = int(((r.get("coverage") or {}).get("file_size")) or 0)
        _rb = max(1, _rm_exp) * 1048576
        _reads_exp = ((_fs + _rb - 1) // _rb) if _fs else None
        _expect_gpu = "rtx" if "rtx" in str(args.fn).lower() else "H100"
        _, reasons = _accept(r, expect_model, _qd_exp, _qd_exp, _reads_exp,
                             _gap_exp, _expect_gpu)
        r["_validity_flags"] = reasons
        r["_is_odin"] = str((r.get("identity") or {}).get("region") or "") == "odin"
        canonical.write_text(json.dumps(r, indent=2, sort_keys=True, default=str),
                             encoding="utf-8")
        ident = r.get("identity") or {}
        ls = r.get("launch_spacing") or {}
        reads = r.get("reads") or r.get("logical_reads") or []
        worst = max((float(x.get("preadv_ms") or 0) for x in reads), default=0.0)
        print(f"[im] done {stem} provider={_norm_cloud(ident.get('provider'))} "
              f"region={ident.get('region')} wall={r.get('full_file_wall_ms')} "
              f"gbps={r.get('full_file_decimal_gbps')} worst={worst:.1f}ms "
              f"maxIF={ls.get('max_simultaneous_in_flight')} "
              f"flags={reasons if reasons else 'none'}", flush=True)
        return r, "accepted"

    accepted: list[dict[str, Any]] = []
    problems: list[str] = []
    # Slots are independent Modal containers, so run them concurrently.  This was
    # previously a serial loop, which made every cohort cost (n x container-start)
    # of wall time.  ex.map preserves input order, so results stay deterministic.
    from concurrent.futures import ThreadPoolExecutor

    slots = list(range(args.from_slot, args.to_slot + 1))
    _workers = max(1, int(getattr(args, "parallel", 8)))
    print(f"[im] launching {len(slots)} slots with parallel={_workers}", flush=True)
    with ThreadPoolExecutor(max_workers=_workers) as _ex:
        for slot, (r, status) in zip(slots, _ex.map(run_slot, slots)):
            if r is None:
                problems.append(f"slot{slot:02d}: {status}")
            else:
                accepted.append(r)

    print(f"\n[im] accepted {len(accepted)} / {args.to_slot - args.from_slot + 1}")
    if accepted:
        gbps = [float(r["full_file_decimal_gbps"]) for r in accepted]
        wall = [float(r["full_file_wall_ms"]) for r in accepted]
        print(f"  gbps med={statistics.median(gbps):.3f} mean={statistics.fmean(gbps):.3f} "
              f"best={max(gbps):.3f} worst={min(gbps):.3f}")
        print(f"  wall med={statistics.median(wall):.0f} mean={statistics.fmean(wall):.0f}")
        regions: dict[str, int] = {}
        for r in accepted:
            ident = r.get("identity") or {}
            key = f"{_norm_cloud(ident.get('provider'))}:{ident.get('region')}"
            regions[key] = regions.get(key, 0) + 1
        print(f"  regions: {regions}")
    if problems:
        print(f"  PROBLEM SLOTS: {problems}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
