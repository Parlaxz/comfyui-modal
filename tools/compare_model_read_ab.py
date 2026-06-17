#!/usr/bin/env python3
"""
Local-only A/B log comparison tool for model-read coordinator experiments.

Parses structured diagnostic lines from cold-start runs and compares
Configuration A (coordinator disabled) vs Configuration B (coordinator enabled).

Usage:
    python tools/compare_model_read_ab.py \\
        --a a1.txt a2.txt a3.txt \\
        --b b1.txt b2.txt b3.txt

Required report columns:
    config, valid, invalid_reason, restore_ms, clip_preload_ms,
    clip_preload_gbps, exact_prefill_encode_ms, validation_ms,
    unet_coordinator_wait_ms, unet_coordinator_hold_ms,
    unet_active_read_ms, unet_future_total_ms, graph_unet_wait_ms,
    vae_coordinator_wait_ms, vae_coordinator_hold_ms,
    vae_active_read_ms, vae_loader_ms,
    unet_vae_observed_overlap_ms, sampler_first_progress_ms,
    sampler_ms, remote_entry_to_return_ms, known_non_overlap_ms,
    user_visible_wall_ms

Outputs per-run rows, group medians, and paired differences.
Never declares a winner automatically.
"""

import argparse
import json
import re
import sys
from collections import defaultdict
from typing import Any, Dict, List, Optional, Tuple


# ── Regex patterns for diagnostic lines ───────────────────────────────────────

RE_CRITICAL_PATH_FLAGS = re.compile(
    r"\[critical_path\.flags\]\s+"
    r"critical_path=(?P<critical_path>\d+)\s+"
    r"unet_phase=(?P<unet_phase>\d+)\s+"
    r"validation_phase=(?P<validation_phase>\d+)\s+"
    r"coordinator=(?P<coordinator>\d+)\s+"
    r"coordinator_diag=(?P<coordinator_diag>\d+)\s+"
    r"source=(?P<source>\S+)"
)

RE_WATERFALL_TOTAL = re.compile(
    r"\[waterfall\] OK\s+full_wall_ms\s+(?P<ms>[\d.]+)"
)

RE_RESTORE_TOTAL = re.compile(
    r"\[waterfall\] OK\s+app_restore_total\s+(?P<ms>[\d.]+)"
)

RE_COORDINATOR_EVENT = re.compile(
    r"\[model_read_coordinator\]\s+"
    r"event=(?P<event>\S+)\s+"
    r"owner=(?P<owner>\S+)\s+"
    r"loader=(?P<loader>\S+)\s+"
    r"path_digest=(?P<path_digest>\S+)\s+"
    r"wait_ms=(?P<wait_ms>[\d.]+)\s+"
    r"hold_ms=(?P<hold_ms>[\d.]+)\s+"
    r"degraded=(?P<degraded>\d+)\s+"
    r"contention=(?P<contention>\d+)"
)

RE_COORDINATOR_SUMMARY = re.compile(
    r"\[model_read_coordinator\.summary\]\s+"
    r"enabled=(?P<enabled>\d+)\s+"
    r"acquisitions=(?P<acquisitions>\d+)\s+"
    r"waited=(?P<waited>\d+)\s+"
    r"total_wait_ms=(?P<total_wait_ms>[\d.]+)\s+"
    r"total_hold_ms=(?P<total_hold_ms>[\d.]+)\s+"
    r"peak_wait_ms=(?P<peak_wait_ms>[\d.]+)\s+"
    r"timeout_fail_open=(?P<timeout_fail_open>\d+)\s+"
    r"production_unet_hold_ms=(?P<production_unet_hold_ms>[\d.]+)\s+"
    r"graph_vae_wait_ms=(?P<graph_vae_wait_ms>[\d.]+)\s+"
    r"graph_vae_hold_ms=(?P<graph_vae_hold_ms>[\d.]+)"
)

RE_ACTIVE_READ = re.compile(
    r"\[active_read\] registered\s+"
    r"owner=(?P<owner>\S+)\s+"
    r"key=(?P<key>\S+)"
)

RE_ACTIVE_READ_COMPLETED = re.compile(
    r"\[active_read\] completed\s+"
    r"owner=(?P<owner>\S+)\s+"
    r"key=(?P<key>\S+)"
)

RE_CRITICAL_PATH_OBSERVED = re.compile(
    r"\[critical_path\.observed\]\s+"
    r"restore_session=(?P<restore_session>\S+)\s+"
    r"request_seq=(?P<request_seq>\d+)\s+"
    r"validation_start_ms=(?P<validation_start_ms>[\d.]+|null)\s+"
    r"validation_end_ms=(?P<validation_end_ms>[\d.]+|null)\s+"
    r"clip_ready_ms=(?P<clip_ready_ms>[\d.]+|null)\s+"
    r"unet_submit_ms=(?P<unet_submit_ms>[\d.]+|null)\s+"
    r"unet_future_done_ms=(?P<unet_future_done_ms>[\d.]+|null)\s+"
    r"graph_unet_wait_start_ms=(?P<graph_unet_wait_start_ms>[\d.]+|null)\s+"
    r"graph_unet_wait_end_ms=(?P<graph_unet_wait_end_ms>[\d.]+|null)\s+"
    r"sampler_first_progress_ms=(?P<sampler_first_progress_ms>[\d.]+|null)"
)

RE_CRITICAL_PATH_INTERVALS = re.compile(
    r"\[critical_path\.observed\.intervals\]\s+"
    r"validation_duration_ms=(?P<validation_duration_ms>[\d.]+|null)\s+"
    r"exact_prefill_seed_duration_ms=(?P<exact_prefill_seed_duration_ms>[\d.]+|null)\s+"
    r"graph_clip_lookup_duration_ms=(?P<graph_clip_lookup_duration_ms>[\d.]+|null)\s+"
    r"unet_future_total_ms=(?P<unet_future_total_ms>[\d.]+|null)\s+"
    r"graph_unet_wait_duration_ms=(?P<graph_unet_wait_duration_ms>[\d.]+|null)\s+"
    r"validation_unet_observed_overlap_ms=(?P<validation_unet_observed_overlap_ms>[\d.]+|null)\s+"
    r"exact_prefill_unet_observed_overlap_ms=(?P<exact_prefill_unet_observed_overlap_ms>[\d.]+|null)"
)

RE_CLIP_PRELOAD = re.compile(
    r"\[restore\.preload\.strategy\]\s+role=(?P<role>\S+)"
)

RE_VAE_LOADER = re.compile(
    r"\[loader_future\]\s+(?P<event>\S+)"
)

RE_EXACT_PREFILL = re.compile(
    r"\[exact_prefill\.remote\]\s+enabled=(?P<enabled>\d+)"
)

RE_SAMPLER = re.compile(
    r"\[sampler\]"
)

RE_WATERFALL_KNOWN_NONOVERLAP = re.compile(
    r"\[waterfall\] SUM\s+known_nonoverlap_total\s+(?P<ms>[\d.]+)"
)


# ── Data structures ───────────────────────────────────────────────────────────

REQUIRED_COLUMNS = [
    "config", "valid", "invalid_reason",
    "restore_ms", "clip_preload_ms", "clip_preload_gbps",
    "exact_prefill_encode_ms", "validation_ms",
    "unet_coordinator_wait_ms", "unet_coordinator_hold_ms",
    "unet_active_read_ms", "unet_future_total_ms", "graph_unet_wait_ms",
    "vae_coordinator_wait_ms", "vae_coordinator_hold_ms",
    "vae_active_read_ms", "vae_loader_ms",
    "unet_vae_observed_overlap_ms",
    "sampler_first_progress_ms", "sampler_ms",
    "remote_entry_to_return_ms", "known_non_overlap_ms",
    "user_visible_wall_ms",
]


def _null(v: Any) -> Optional[float]:
    """Convert 'null' string or None to None, else float."""
    if v is None or v == "null":
        return None
    try:
        return float(v)
    except (ValueError, TypeError):
        return None


def _parse_log_file(path: str) -> Dict[str, Any]:
    """Parse a single log file and return a structured result dict.

    Returns dict with columns from REQUIRED_COLUMNS plus extra fields.
    Missing values are None. 'valid' (bool) and 'invalid_reason' (str)
    indicate whether the log contains all required diagnostics.
    """
    result: Dict[str, Any] = {c: None for c in REQUIRED_COLUMNS}
    result["valid"] = False
    result["invalid_reason"] = ""
    result["_flags_ok"] = True
    result["_config_ok"] = True
    result["_lines"] = []

    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
    except FileNotFoundError:
        result["invalid_reason"] = f"file not found: {path}"
        return result
    except Exception as e:
        result["invalid_reason"] = f"read error: {e}"
        return result

    result["_lines"] = [l.rstrip("\n\r") for l in lines]

    # ── Parse all diagnostic lines ──────────────────────────────────────
    for line in result["_lines"]:
        # Critical path flags
        m = RE_CRITICAL_PATH_FLAGS.search(line)
        if m:
            _cp = m.group("critical_path")
            _up = m.group("unet_phase")
            _vp = m.group("validation_phase")
            _coord = m.group("coordinator")
            _coord_diag = m.group("coordinator_diag")
            result["_critical_path"] = _cp
            result["_unet_phase"] = _up
            result["_validation_phase"] = _vp
            result["_coordinator"] = _coord
            result["_coordinator_diag"] = _coord_diag
            continue

        # Waterfall total
        m = RE_WATERFALL_TOTAL.search(line)
        if m:
            result["user_visible_wall_ms"] = _null(m.group("ms"))
            continue

        # Restore total
        m = RE_RESTORE_TOTAL.search(line)
        if m:
            result["restore_ms"] = _null(m.group("ms"))
            continue

        # Known non-overlap
        m = RE_WATERFALL_KNOWN_NONOVERLAP.search(line)
        if m:
            result["known_non_overlap_ms"] = _null(m.group("ms"))
            continue

        # Coordinator events
        m = RE_COORDINATOR_EVENT.search(line)
        if m:
            _event = m.group("event")
            _owner = m.group("owner")
            _wait_ms = _null(m.group("wait_ms"))
            _hold_ms = _null(m.group("hold_ms"))
            _key = (_owner, _event)
            if _key not in result.setdefault("_coord_events", {}):
                result["_coord_events"][_key] = []
            result["_coord_events"][_key].append({
                "wait_ms": _wait_ms, "hold_ms": _hold_ms,
                "degraded": m.group("degraded"),
                "contention": m.group("contention"),
            })
            # Aggregate by owner
            if _event == "acquired":
                _w = _null(m.group("wait_ms"))
                if _w is not None:
                    key = f"{_owner}_coordinator_wait_ms"
                    result[key] = (result.get(key) or 0.0) + _w
            elif _event == "released":
                _h = _null(m.group("hold_ms"))
                if _h is not None:
                    key = f"{_owner}_coordinator_hold_ms"
                    result[key] = (result.get(key) or 0.0) + _h
            continue

        # Coordinator summary
        m = RE_COORDINATOR_SUMMARY.search(line)
        if m:
            result["_coord_summary"] = {
                "enabled": m.group("enabled"),
                "acquisitions": m.group("acquisitions"),
                "waited": m.group("waited"),
                "total_wait_ms": _null(m.group("total_wait_ms")),
                "total_hold_ms": _null(m.group("total_hold_ms")),
                "peak_wait_ms": _null(m.group("peak_wait_ms")),
                "timeout_fail_open": m.group("timeout_fail_open"),
                "production_unet_hold_ms": _null(m.group("production_unet_hold_ms")),
                "graph_vae_wait_ms": _null(m.group("graph_vae_wait_ms")),
                "graph_vae_hold_ms": _null(m.group("graph_vae_hold_ms")),
            }
            continue

        # Critical path observed
        m = RE_CRITICAL_PATH_OBSERVED.search(line)
        if m:
            result["_cp_observed"] = {
                "restore_session": m.group("restore_session"),
                "request_seq": m.group("request_seq"),
                "validation_start_ms": _null(m.group("validation_start_ms")),
                "validation_end_ms": _null(m.group("validation_end_ms")),
                "clip_ready_ms": _null(m.group("clip_ready_ms")),
                "unet_submit_ms": _null(m.group("unet_submit_ms")),
                "unet_future_done_ms": _null(m.group("unet_future_done_ms")),
                "graph_unet_wait_start_ms": _null(m.group("graph_unet_wait_start_ms")),
                "graph_unet_wait_end_ms": _null(m.group("graph_unet_wait_end_ms")),
                "sampler_first_progress_ms": _null(m.group("sampler_first_progress_ms")),
            }
            continue

        # Critical path intervals
        m = RE_CRITICAL_PATH_INTERVALS.search(line)
        if m:
            result["_cp_intervals"] = {
                "validation_duration_ms": _null(m.group("validation_duration_ms")),
                "exact_prefill_seed_duration_ms": _null(m.group("exact_prefill_seed_duration_ms")),
                "graph_clip_lookup_duration_ms": _null(m.group("graph_clip_lookup_duration_ms")),
                "unet_future_total_ms": _null(m.group("unet_future_total_ms")),
                "graph_unet_wait_duration_ms": _null(m.group("graph_unet_wait_duration_ms")),
                "validation_unet_observed_overlap_ms": _null(m.group("validation_unet_observed_overlap_ms")),
                "exact_prefill_unet_observed_overlap_ms": _null(m.group("exact_prefill_unet_observed_overlap_ms")),
            }
            continue

        # Active read events
        m = RE_ACTIVE_READ.search(line)
        if m:
            result.setdefault("_active_reads", []).append({
                "owner": m.group("owner"),
                "key": m.group("key"),
            })
            continue

        m = RE_ACTIVE_READ_COMPLETED.search(line)
        if m:
            result.setdefault("_active_reads_completed", []).append({
                "owner": m.group("owner"),
                "key": m.group("key"),
            })
            continue

    # ── Map parsed values to report columns ─────────────────────────────

    # unet_coordinator_wait_ms / hold_ms
    _unet_wait = result.get("restore_background_unet_coordinator_wait_ms") or \
                 result.get("restore_preload_coordinator_wait_ms") or 0.0
    result["unet_coordinator_wait_ms"] = _unet_wait

    _unet_hold = result.get("restore_background_unet_coordinator_hold_ms") or 0.0
    result["unet_coordinator_hold_ms"] = _unet_hold

    # vae_coordinator_wait_ms / hold_ms
    _vae_wait = result.get("graph_vae_coordinator_wait_ms") or \
                result.get("actual_load_coordinator_wait_ms") or 0.0
    result["vae_coordinator_wait_ms"] = _vae_wait

    _vae_hold = result.get("graph_vae_coordinator_hold_ms") or \
                result.get("actual_load_coordinator_hold_ms") or 0.0
    result["vae_coordinator_hold_ms"] = _vae_hold

    # Critical path observed intervals
    _cpi = result.get("_cp_intervals", {})
    result["validation_ms"] = _cpi.get("validation_duration_ms")
    result["unet_future_total_ms"] = _cpi.get("unet_future_total_ms")
    result["graph_unet_wait_ms"] = _cpi.get("graph_unet_wait_duration_ms")
    result["unet_vae_observed_overlap_ms"] = _cpi.get("validation_unet_observed_overlap_ms")

    _cpo = result.get("_cp_observed", {})
    result["sampler_first_progress_ms"] = _cpo.get("sampler_first_progress_ms")

    # Summary values
    _cs = result.get("_coord_summary", {})
    if result["unet_coordinator_hold_ms"] is None or result["unet_coordinator_hold_ms"] == 0.0:
        result["unet_coordinator_hold_ms"] = _cs.get("production_unet_hold_ms")
    if result["vae_coordinator_wait_ms"] is None or result["vae_coordinator_wait_ms"] == 0.0:
        result["vae_coordinator_wait_ms"] = _cs.get("graph_vae_wait_ms")
    if result["vae_coordinator_hold_ms"] is None or result["vae_coordinator_hold_ms"] == 0.0:
        result["vae_coordinator_hold_ms"] = _cs.get("graph_vae_hold_ms")

    # ── Validate ────────────────────────────────────────────────────────
    _missing = []
    for _col in REQUIRED_COLUMNS:
        if _col in ("config", "valid", "invalid_reason"):
            continue
        if result.get(_col) is None:
            _missing.append(_col)
    if _missing:
        result["invalid_reason"] = f"missing_fields: {', '.join(_missing)}"
        return result

    result["valid"] = True
    return result


def _median(values: List[Optional[float]]) -> Optional[float]:
    """Return median of non-None values. Returns None if no values."""
    _clean = [v for v in values if v is not None]
    if not _clean:
        return None
    _sorted = sorted(_clean)
    n = len(_sorted)
    if n % 2 == 0:
        return (_sorted[n // 2 - 1] + _sorted[n // 2]) / 2.0
    return _sorted[n // 2]


def _mean(values: List[Optional[float]]) -> Optional[float]:
    _clean = [v for v in values if v is not None]
    if not _clean:
        return None
    return sum(_clean) / len(_clean)


def _min_max(values: List[Optional[float]]) -> Tuple[Optional[float], Optional[float]]:
    _clean = [v for v in values if v is not None]
    if not _clean:
        return None, None
    return min(_clean), max(_clean)


def _format_ms(v: Optional[float]) -> str:
    if v is None:
        return "---"
    return f"{v:.1f}"


def _print_run_table(label: str, runs: List[Dict[str, Any]], columns: List[str]) -> None:
    """Print a table of run data."""
    print(f"\n{'=' * 80}")
    print(f" {label}")
    print(f"{'=' * 80}")
    # Header
    header = f"{'run':>5}  " + "  ".join(f"{c:>26}" for c in columns)
    print(header)
    print("-" * len(header))
    for i, r in enumerate(runs):
        row = f"{i+1:>5}  "
        for c in columns:
            row += f"{_format_ms(r.get(c)):>26}"
        print(row)
    print()

    # Median row
    med_row = f"{'med':>5}  "
    for c in columns:
        vals = [r.get(c) for r in runs]
        med_row += f"{_format_ms(_median(vals)):>26}"
    print(med_row)

    # Min/Max row
    mm_row = f"{'min':>5}  "
    for c in columns:
        vals = [r.get(c) for r in runs]
        _mn, _mx = _min_max(vals)
        mm_row += f"{_format_ms(_mn):>26}"
    print(mm_row)
    mx_row = f"{'max':>5}  "
    for c in columns:
        vals = [r.get(c) for r in runs]
        _mn, _mx = _min_max(vals)
        mx_row += f"{_format_ms(_mx):>26}"
    print(mx_row)


def _print_paired_differences(a_runs: List[Dict[str, Any]], b_runs: List[Dict[str, Any]], columns: List[str]) -> None:
    """Print paired A-B differences when ordered pairs are supplied."""
    n = min(len(a_runs), len(b_runs))
    if n < 1:
        print("\n[paired] no valid pairs (need equal or more runs in both groups)")
        return
    print(f"\n{'=' * 80}")
    print(f" Paired A-B differences (A then B): {n} pairs")
    print(f"{'=' * 80}")
    header = f"{'pair':>5}  " + "  ".join(f"{c:>26}" for c in columns)
    print(header)
    print("-" * len(header))
    diffs = {}
    for c in columns:
        diffs[c] = []
    for i in range(n):
        row = f"{i+1:>5}  "
        for c in columns:
            _a = a_runs[i].get(c)
            _b = b_runs[i].get(c)
            if _a is not None and _b is not None:
                _d = _b - _a
                diffs[c].append(_d)
                row += f"{_format_ms(_d):>26}"
            else:
                row += f"{'N/A':>26}"
        print(row)
    # Median diff
    print()
    md_row = f"{'med':>5}  "
    for c in columns:
        if diffs[c]:
            md_row += f"{_format_ms(_median(diffs[c])):>26}"
        else:
            md_row += f"{'N/A':>26}"
    print(md_row)
    # Min/Max diff
    mm_row = f"{'min':>5}  "
    for c in columns:
        if diffs[c]:
            mm_row += f"{_format_ms(min(diffs[c])):>26}"
        else:
            mm_row += f"{'N/A':>26}"
    print(mm_row)
    mx_row = f"{'max':>5}  "
    for c in columns:
        if diffs[c]:
            mx_row += f"{_format_ms(max(diffs[c])):>26}"
        else:
            mx_row += f"{'N/A':>26}"
    print(mx_row)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Compare A/B model-read coordinator experiment logs."
    )
    parser.add_argument("--a", nargs="+", required=True, help="Configuration A log files")
    parser.add_argument("--b", nargs="+", required=True, help="Configuration B log files")
    args = parser.parse_args()

    # Parse all logs
    a_runs_raw = [_parse_log_file(p) for p in args.a]
    b_runs_raw = [_parse_log_file(p) for p in args.b]

    # Filter to valid runs only
    a_runs = [r for r in a_runs_raw if r.get("valid")]
    b_runs = [r for r in b_runs_raw if r.get("valid")]

    # Report invalid runs
    for group, raw, paths in [("A", a_runs_raw, args.a), ("B", b_runs_raw, args.b)]:
        for i, r in enumerate(raw):
            if not r.get("valid"):
                print(f"[{group}] WARNING: run {i+1} ({paths[i]}) INVALID: {r.get('invalid_reason', 'unknown')}")

    if not a_runs and not b_runs:
        print("\nNo valid runs in either group.")
        sys.exit(1)

    # Report columns (numerical metrics, not identity)
    metric_columns = [
        "restore_ms", "clip_preload_ms", "clip_preload_gbps",
        "exact_prefill_encode_ms", "validation_ms",
        "unet_coordinator_wait_ms", "unet_coordinator_hold_ms",
        "unet_active_read_ms", "unet_future_total_ms", "graph_unet_wait_ms",
        "vae_coordinator_wait_ms", "vae_coordinator_hold_ms",
        "vae_active_read_ms", "vae_loader_ms",
        "unet_vae_observed_overlap_ms",
        "sampler_first_progress_ms", "sampler_ms",
        "remote_entry_to_return_ms", "known_non_overlap_ms",
        "user_visible_wall_ms",
    ]

    print(f"\n{'=' * 80}")
    print(f" MODEL-READ COORDINATOR A/B COMPARISON")
    print(f" Group A: {len(a_runs)}/{len(a_runs_raw)} valid runs (coordinator disabled)")
    print(f" Group B: {len(b_runs)}/{len(b_runs_raw)} valid runs (coordinator enabled)")
    print(f"{'=' * 80}")

    if a_runs:
        _print_run_table("Configuration A (coordinator=0)", a_runs, metric_columns)

    if b_runs:
        _print_run_table("Configuration B (coordinator=1)", b_runs, metric_columns)

    if a_runs and b_runs:
        # Compute group medians and differences
        print(f"\n{'=' * 80}")
        print(f" GROUP COMPARISON (medians)")
        print(f"{'=' * 80}")
        header = f"{'metric':>30}  {'A-med':>10}  {'B-med':>10}  {'B-A':>10}  {'A-spread':>12}  {'B-spread':>12}"
        print(header)
        print("-" * len(header))
        for c in metric_columns:
            a_vals = [r.get(c) for r in a_runs]
            b_vals = [r.get(c) for r in b_runs]
            a_med = _median(a_vals)
            b_med = _median(b_vals)
            a_mn, a_mx = _min_max(a_vals)
            b_mn, b_mx = _min_max(b_vals)
            diff = (b_med - a_med) if a_med is not None and b_med is not None else None
            a_spread = (a_mx - a_mn) if a_mn is not None and a_mx is not None else None
            b_spread = (b_mx - b_mn) if b_mn is not None and b_mx is not None else None
            diff_str = f"{diff:+.1f}" if diff is not None else "---"
            a_spread_str = _format_ms(a_spread)
            b_spread_str = _format_ms(b_spread)
            print(f"{c:>30}  {_format_ms(a_med):>10}  {_format_ms(b_med):>10}  {diff_str:>10}  {a_spread_str:>12}  {b_spread_str:>12}")

        # Paired differences where order matches
        if len(a_runs) == len(b_runs):
            _print_paired_differences(a_runs, b_runs, metric_columns)

    print(f"\n{'=' * 80}")
    print(" NOTE: This tool reports observed differences only.")
    print(" It does NOT declare a winner. Causal claims require")
    print(" reviewing the full context — see the A/B run protocol.")
    print(f"{'=' * 80}")


if __name__ == "__main__":
    main()
