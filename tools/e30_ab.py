"""E30 A/B analysis tool: diff, extract, and compare.

Usage:
    python tools/e30_ab.py diff [--arm-a NAME] [--arm-b NAME] [--json] [--verbose]
    python tools/e30_ab.py extract RUN_ARTIFACT.json [--json]
    python tools/e30_ab.py compare ARM_A.json ARM_B.json [--json]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from v2_control.profiles import Profiles
from v2_control.registry import FlagRegistry
from v2_control.config import ConfigResolver

DEFAULT_ARM_A = "e30-clip-qd-arm-a"
DEFAULT_ARM_B = "e30-clip-qd-arm-b"

E31_FLAGS = (
    "COMFYMODAL_V2_CLIP_FP32_CAST_ONCE",
    "COMFYMODAL_V2_E31_FORENSICS",
    "COMFYMODAL_V2_E31_FORWARD_PROFILE",
)

EVT_CLIP_QD_SOURCE_SUBMIT_START = "clip_qd_source_submit_start"
EVT_CLIP_QD_DEVICE_READY = "clip_qd_device_ready"
EVT_CLIP_QD_STATS = "clip_qd_stats"
EVT_CLIP_QD_FALLBACK = "clip_qd_fallback"


# ── diff ────────────────────────────────────────────────────────────────────


def cmd_diff(args: argparse.Namespace) -> int:
    repo_root = Path(__file__).resolve().parents[1]
    profiles = Profiles()
    registry = FlagRegistry()
    resolver = ConfigResolver(repo_root, profiles, registry)

    config_a = resolver.resolve(profile_name=args.arm_a)
    config_b = resolver.resolve(profile_name=args.arm_b)

    flag_map_a: dict[str, str] = {f.name: f.value for f in config_a.flags}
    flag_map_b: dict[str, str] = {f.name: f.value for f in config_b.flags}
    all_names = sorted(set(flag_map_a) | set(flag_map_b))

    identical = []
    differing = []
    only_a = []
    only_b = []
    for name in all_names:
        va = flag_map_a.get(name)
        vb = flag_map_b.get(name)
        if va is None:
            only_b.append(name)
        elif vb is None:
            only_a.append(name)
        elif va == vb:
            identical.append((name, va))
        else:
            differing.append((name, va, vb))

    if args.json:
        data = {
            "arm_a": args.arm_a,
            "arm_b": args.arm_b,
            "identical": [{"name": n, "value": v} for n, v in identical],
            "differing": [{"name": n, "arm_a": va, "arm_b": vb} for n, va, vb in differing],
            "only_a": only_a,
            "only_b": only_b,
            "target": {
                "identical": config_a.target.__dict__ == config_b.target.__dict__,
                "arm_a": config_a.target.__dict__,
                "arm_b": config_b.target.__dict__,
            },
            "resources": {
                "identical": config_a.resources.__dict__ == config_b.resources.__dict__,
                "arm_a": config_a.resources.__dict__,
                "arm_b": config_b.resources.__dict__,
            },
            "workload": {
                "identical": config_a.workload.__dict__ == config_b.workload.__dict__,
                "arm_a": config_a.workload.__dict__,
                "arm_b": config_b.workload.__dict__,
            },
        }
        print(json.dumps(data, indent=2, default=str))
    else:
        print("E30 A/B Profile Diff")
        print("====================")
        print(f"ARM A: {args.arm_a}")
        print(f"ARM B: {args.arm_b}")
        print()

        if not args.verbose:
            print(f"Identical flags ({len(identical)}):")
            print("  (hidden, use --verbose to show)")
        else:
            print(f"Identical flags ({len(identical)}):")
            for name, val in identical:
                print(f"  {name}: {val}")
        print()

        print(f"Differing flags ({len(differing)}):")
        for name, va, vb in differing:
            print(f"  {name}: {va} (ARM A) -> {vb} (ARM B)")
        if only_a:
            print(f"\nOnly in ARM A ({len(only_a)}):")
            for name in only_a:
                print(f"  {name}: {flag_map_a[name]}")
        if only_b:
            print(f"\nOnly in ARM B ({len(only_b)}):")
            for name in only_b:
                print(f"  {name}: {flag_map_b[name]}")
        print()

        ta = config_a.target
        tb = config_b.target
        if ta.__dict__ == tb.__dict__:
            print(f"Target: IDENTICAL ({ta.app} / {ta.class_name} / {ta.method})")
        else:
            print("Target: DIFFERS")
            print(f"  ARM A: {ta.app} / {ta.class_name} / {ta.method}")
            print(f"  ARM B: {tb.app} / {tb.class_name} / {tb.method}")

        ra = config_a.resources
        rb = config_b.resources
        if ra.__dict__ == rb.__dict__:
            print(f"Resources: IDENTICAL ({ra.gpu} / {ra.cpu} cpu / {ra.memory_mb} MB)")
        else:
            print("Resources: DIFFERS")
            print(f"  ARM A: {ra.gpu} / {ra.cpu} cpu / {ra.memory_mb} MB")
            print(f"  ARM B: {rb.gpu} / {rb.cpu} cpu / {rb.memory_mb} MB")

        wa = config_a.workload
        wb = config_b.workload
        if wa.__dict__ == wb.__dict__:
            sha_short = (wa.expected_output_sha[:8] + "..." + wa.expected_output_sha[-5:]) if len(wa.expected_output_sha) > 13 else wa.expected_output_sha
            print(f"Workload: IDENTICAL (fresh={wa.fresh_required}, SHA={sha_short}, run_count={wa.run_count}, gap={wa.gap_seconds})")
        else:
            print("Workload: DIFFERS")
            print(f"  ARM A: fresh={wa.fresh_required}, SHA={wa.expected_output_sha}, run_count={wa.run_count}, gap={wa.gap_seconds}")
            print(f"  ARM B: fresh={wb.fresh_required}, SHA={wb.expected_output_sha}, run_count={wb.run_count}, gap={wb.gap_seconds}")

        e31_a = {f.name: f.value for f in config_a.flags if f.name in E31_FLAGS}
        e31_b = {f.name: f.value for f in config_b.flags if f.name in E31_FLAGS}
        e31_identical = all(e31_a.get(f) == e31_b.get(f) for f in E31_FLAGS)
        e31_off = all(v == "0" for v in e31_a.values()) and all(v == "0" for v in e31_b.values())
        if e31_identical:
            parts = ", ".join(f"{f}={e31_a.get(f, '?')}" for f in E31_FLAGS)
            if e31_off:
                print(f"E31 flags: OFF in both ({parts})")
            else:
                print(f"E31 flags: IDENTICAL ({parts})")
        else:
            print("E31 flags: DIFFERS (FAIL closed)")
            for f in E31_FLAGS:
                va = e31_a.get(f, "?")
                vb = e31_b.get(f, "?")
                if va != vb:
                    print(f"  {f}: {va} (ARM A) -> {vb} (ARM B)")

        print()

    fail_closed = False
    e31_diff_names = [f for f in E31_FLAGS if flag_map_a.get(f) != flag_map_b.get(f)]
    if e31_diff_names:
        fail_closed = True

    wa = config_a.workload
    wb = config_b.workload
    if wa.expected_output_sha != wb.expected_output_sha:
        fail_closed = True
    if wa.fresh_required != wb.fresh_required:
        fail_closed = True
    if wa.run_count != wb.run_count:
        fail_closed = True

    ra = config_a.resources
    rb = config_b.resources
    if ra.gpu != rb.gpu or ra.cpu != rb.cpu or ra.memory_mb != rb.memory_mb:
        fail_closed = True

    ta = config_a.target
    tb = config_b.target
    if ta.app != tb.app or ta.class_name != tb.class_name or ta.method != tb.method:
        fail_closed = True

    critical_diffs = [
        (n, va, vb) for n, va, vb in differing
        if n != "COMFYMODAL_V2_CLIP_QD_READER"
    ]

    if not args.json:
        if not fail_closed and not critical_diffs and not only_a and not only_b and len(differing) == 1 and differing[0][0] == "COMFYMODAL_V2_CLIP_QD_READER":
            print("A_B_CONFIG_DIFF = CLEAN -- only READER differs (0 -> 1)")
        elif fail_closed:
            print("A_B_CONFIG_DIFF = FAIL -- critical difference detected")
            for name in e31_diff_names:
                print(f"  E31 flag differs: {name}")
            if wa.expected_output_sha != wb.expected_output_sha:
                print("  expected_output_sha differs")
            if wa.fresh_required != wb.fresh_required:
                print("  fresh_required differs")
            if wa.run_count != wb.run_count:
                print("  run_count differs")
            if ra.gpu != rb.gpu or ra.cpu != rb.cpu or ra.memory_mb != rb.memory_mb:
                print("  resources differ")
            if ta.app != tb.app or ta.class_name != tb.class_name or ta.method != tb.method:
                print("  target differs")
        else:
            print("A_B_CONFIG_DIFF = MISMATCH -- unexpected differences")
            if critical_diffs:
                print("  Unexpected differing flags:")
                for name, va, vb in critical_diffs:
                    print(f"    {name}: {va} -> {vb}")
            if only_a:
                print(f"  Flags only in ARM A: {', '.join(only_a)}")
            if only_b:
                print(f"  Flags only in ARM B: {', '.join(only_b)}")

    if fail_closed or critical_diffs or only_a or only_b:
        return 1
    return 0


# ── extract ─────────────────────────────────────────────────────────────────


def _load_artifact(path: str) -> dict[str, Any]:
    p = Path(path)
    if not p.exists():
        print(f"ERROR: artifact not found: {path}", file=sys.stderr)
        sys.exit(1)
    with p.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def _find_event(events: list[dict], name: str) -> dict | None:
    for ev in events:
        if ev.get("name") == name or ev.get("event_name") == name:
            return ev
    return None


def _find_span(spans: list[dict], name: str) -> dict | None:
    for sp in spans:
        if sp.get("name") == name:
            return sp
    return None


def _find_spans(spans: list[dict], name: str) -> list[dict]:
    return [sp for sp in spans if sp.get("name") == name]


def _extract_metrics(artifact: dict[str, Any]) -> dict[str, Any]:
    metrics: dict[str, Any] = {}

    cl = artifact.get("canonical_ledger")
    ledger_status = artifact.get("canonical_ledger_status", "missing")
    endpoint_status = "missing"
    events: list[dict] = []
    spans: list[dict] = []

    if cl is not None:
        endpoint_status = cl.get("endpoint_status", "missing")
        events = cl.get("events", [])
        spans = cl.get("spans", [])

    metrics["LEDGER_STATUS"] = ledger_status
    metrics["ENDPOINT_STATUS"] = endpoint_status

    clip_qd_stats_ev = _find_event(events, EVT_CLIP_QD_STATS)
    clip_submit_start_ev = _find_event(events, EVT_CLIP_QD_SOURCE_SUBMIT_START)
    clip_device_ready_ev = _find_event(events, EVT_CLIP_QD_DEVICE_READY)
    clip_fallback_ev = _find_event(events, EVT_CLIP_QD_FALLBACK)
    all_clip_events = [e for e in events if str(e.get("name", "")).startswith("clip_qd_")]

    clip_source_ms = None
    if clip_qd_stats_ev is not None:
        meta = clip_qd_stats_ev.get("metadata", {})
        clip_source_ms = meta.get("total_source_wall_ms")
    if clip_source_ms is None:
        lane_start_ev = _find_event(events, "clip_speculative_lane_started")
        lane_end_ev = _find_event(events, "clip_speculative_lane_finished")
        if lane_start_ev is not None and lane_end_ev is not None:
            t_start = lane_start_ev.get("mono_ns")
            t_end = lane_end_ev.get("mono_ns")
            if t_start is not None and t_end is not None:
                clip_source_ms = round((int(t_end) - int(t_start)) / 1_000_000, 3)
    if clip_source_ms is None:
        span = _find_span(spans, "CLIP hydration")
        if span is not None:
            clip_source_ms = span.get("duration_ms")
    metrics["CLIP_SOURCE_MS"] = clip_source_ms

    clip_source_to_gpu_ready_ms = None
    if clip_submit_start_ev is not None and clip_device_ready_ev is not None:
        t_submit = clip_submit_start_ev.get("mono_ns")
        t_ready = clip_device_ready_ev.get("mono_ns")
        if t_submit is not None and t_ready is not None:
            clip_source_to_gpu_ready_ms = round((int(t_ready) - int(t_submit)) / 1_000_000, 3)
    metrics["CLIP_SOURCE_TO_GPU_READY_MS"] = clip_source_to_gpu_ready_ms

    configured_qd = None
    observed_max_outstanding = None
    if clip_qd_stats_ev is not None:
        meta = clip_qd_stats_ev.get("metadata", {})
        configured_qd = meta.get("configured_qd")
        observed_max_outstanding = meta.get("observed_max_outstanding")
    metrics["CONFIGURED_QD"] = configured_qd
    metrics["OBSERVED_MAX_OUTSTANDING"] = observed_max_outstanding
    metrics["QD_USED"] = len(all_clip_events) > 0
    metrics["QD_FALLBACK"] = clip_fallback_ev is not None

    serial_ledger = cl.get("serial_ledger") if cl is not None else None
    restore_total_ms = None
    remote_python_to_durable_ms = None
    if serial_ledger is not None:
        restore_total_ms = serial_ledger.get("total_ms")
        if endpoint_status == "ok":
            remote_python_to_durable_ms = serial_ledger.get("total_ms")
    metrics["RESTORE_TOTAL_MS"] = restore_total_ms
    metrics["REMOTE_PYTHON_TO_DURABLE_MS"] = remote_python_to_durable_ms

    output_sha = artifact.get("output_sha")
    if output_sha is None:
        od = artifact.get("output_descriptor", [])
        if isinstance(od, list) and od:
            first = od[0]
            if isinstance(first, dict):
                output_sha = first.get("asset_id") or first.get("identity")
                if isinstance(output_sha, str) and output_sha.startswith("sha256:"):
                    output_sha = output_sha[7:]
    metrics["OUTPUT_SHA"] = output_sha

    fresh = artifact.get("fresh")
    if fresh is None:
        canonical_status = artifact.get("canonical_ledger_status")
        restore_count = artifact.get("restore_count")
        request_count = artifact.get("request_count")
        if canonical_status == "ok" and restore_count is not None and request_count is not None:
            fresh = str(restore_count) == "1" and str(request_count or "1") == "1"
        else:
            env = artifact.get("effective_env", {})
            single_use = str(env.get("COMFYMODAL_V2_SINGLE_USE_CONTAINERS", "")).strip() == "1"
            snapshot_id = artifact.get("snapshot_identity")
            has_ledger = canonical_status == "ok"
            if single_use and has_ledger and snapshot_id:
                fresh = True
            else:
                fresh = "unknown"
    metrics["FRESH"] = fresh

    clip_hydration_ms = None
    span = _find_span(spans, "CLIP hydration")
    if span is not None:
        clip_hydration_ms = span.get("duration_ms")
    metrics["CLIP_HYDRATION_MS"] = clip_hydration_ms

    clip_forward_ms = None
    span = _find_span(spans, "CLIP forward")
    if span is not None:
        clip_forward_ms = span.get("duration_ms")
    metrics["CLIP_FORWARD_MS"] = clip_forward_ms

    unet_spans = _find_spans(spans, "model-mgmt:load_models_gpu")
    unet_pipeline_ms = None
    if unet_spans:
        durations = [s.get("duration_ms", 0.0) for s in unet_spans]
        unet_pipeline_ms = max(durations) if durations else 0.0
    metrics["UNET_PIPELINE_MS"] = unet_pipeline_ms

    total_unattributed_ms = None
    if serial_ledger is not None:
        total_unattributed_ms = serial_ledger.get("unattributed_ms")
    metrics["TOTAL_UNATTRIBUTED_MS"] = total_unattributed_ms

    qd_stats: dict[str, Any] = {}
    if clip_qd_stats_ev is not None:
        meta = clip_qd_stats_ev.get("metadata", {})
        for key in (
            "configured_qd", "observed_max_outstanding", "bytes_read",
            "file_bytes", "aggregate_gbps", "steady_state_gbps",
            "buffer_pool_wait_ms", "submit_count", "completion_count",
            "per_read_errors", "launch_policy", "syscall_mode",
        ):
            if key in meta:
                qd_stats[key] = meta[key]
    metrics["QD_STATS"] = qd_stats

    primary_required = [
        "CLIP_SOURCE_MS", "RESTORE_TOTAL_MS", "REMOTE_PYTHON_TO_DURABLE_MS",
        "OUTPUT_SHA", "FRESH",
    ]
    all_present = all(metrics.get(k) is not None and metrics.get(k) != "unknown" for k in primary_required)
    metrics["E30_EVIDENCE_STATUS"] = "OK" if all_present else "MISSING"

    return metrics


def cmd_extract(args: argparse.Namespace) -> int:
    artifact = _load_artifact(args.artifact)
    metrics = _extract_metrics(artifact)
    filename = Path(args.artifact).name

    if args.json:
        out = {
            "source": filename,
            "ledger_status": metrics["LEDGER_STATUS"],
            "endpoint_status": metrics["ENDPOINT_STATUS"],
            "primary_metrics": {
                "CLIP_SOURCE_MS": metrics["CLIP_SOURCE_MS"],
                "CLIP_SOURCE_TO_GPU_READY_MS": metrics["CLIP_SOURCE_TO_GPU_READY_MS"],
                "CONFIGURED_QD": metrics["CONFIGURED_QD"],
                "OBSERVED_MAX_OUTSTANDING": metrics["OBSERVED_MAX_OUTSTANDING"],
                "QD_USED": metrics["QD_USED"],
                "QD_FALLBACK": metrics["QD_FALLBACK"],
                "RESTORE_TOTAL_MS": metrics["RESTORE_TOTAL_MS"],
                "REMOTE_PYTHON_TO_DURABLE_MS": metrics["REMOTE_PYTHON_TO_DURABLE_MS"],
                "OUTPUT_SHA": metrics["OUTPUT_SHA"],
                "FRESH": metrics["FRESH"],
            },
            "secondary_diagnostics": {
                "CLIP_HYDRATION_MS": metrics["CLIP_HYDRATION_MS"],
                "CLIP_FORWARD_MS": metrics["CLIP_FORWARD_MS"],
                "UNET_PIPELINE_MS": metrics["UNET_PIPELINE_MS"],
                "TOTAL_UNATTRIBUTED_MS": metrics["TOTAL_UNATTRIBUTED_MS"],
            },
            "qd_stats": metrics["QD_STATS"],
            "e30_evidence_status": metrics["E30_EVIDENCE_STATUS"],
        }
        print(json.dumps(out, indent=2, default=str))
    else:
        print("E30 Artifact Extraction")
        print("=======================")
        print(f"SOURCE: {filename}")
        print(f"LEDGER_STATUS: {metrics['LEDGER_STATUS']}")
        print(f"ENDPOINT_STATUS: {metrics['ENDPOINT_STATUS']}")
        print()

        def _fmt(val: Any, none_str: str = "N/A") -> str:
            if val is None:
                return none_str
            if isinstance(val, str) and len(val) > 20:
                return val[:8] + "..." + val[-5:]
            return str(val)

        print("Primary Metrics:")
        print(f"  CLIP_SOURCE_MS:                {_fmt(metrics['CLIP_SOURCE_MS'])}")
        print(f"  CLIP_SOURCE_TO_GPU_READY_MS:   {_fmt(metrics['CLIP_SOURCE_TO_GPU_READY_MS'])}")
        print(f"  CONFIGURED_QD:                 {_fmt(metrics['CONFIGURED_QD'])}")
        print(f"  OBSERVED_MAX_OUTSTANDING:      {_fmt(metrics['OBSERVED_MAX_OUTSTANDING'])}")
        print(f"  QD_USED:                       {metrics['QD_USED']}")
        print(f"  QD_FALLBACK:                   {metrics['QD_FALLBACK']}")
        print(f"  RESTORE_TOTAL_MS:              {_fmt(metrics['RESTORE_TOTAL_MS'])}")
        print(f"  REMOTE_PYTHON_TO_DURABLE_MS:   {_fmt(metrics['REMOTE_PYTHON_TO_DURABLE_MS'])}")
        print(f"  OUTPUT_SHA:                    {_fmt(metrics['OUTPUT_SHA'])}")
        print(f"  FRESH:                         {metrics['FRESH']}")
        print()

        print("Secondary Diagnostics:")
        print(f"  CLIP_HYDRATION_MS:             {_fmt(metrics['CLIP_HYDRATION_MS'])}")
        print(f"  CLIP_FORWARD_MS:               {_fmt(metrics['CLIP_FORWARD_MS'])}")
        print(f"  UNET_PIPELINE_MS:              {_fmt(metrics['UNET_PIPELINE_MS'])}")
        print(f"  TOTAL_UNATTRIBUTED_MS:         {_fmt(metrics['TOTAL_UNATTRIBUTED_MS'])}")
        print()

        qd = metrics["QD_STATS"]
        if qd:
            print("E30 QD Stats:")
            for k, v in qd.items():
                print(f"  {k}: {v}")
            print()

        missing = []
        primary_required = [
            "CLIP_SOURCE_MS", "RESTORE_TOTAL_MS", "REMOTE_PYTHON_TO_DURABLE_MS",
            "OUTPUT_SHA", "FRESH",
        ]
        for k in primary_required:
            val = metrics.get(k)
            if val is None:
                missing.append(f"{k}: None")
            elif val == "unknown":
                missing.append(f"{k}: UNKNOWN")
            elif val == "missing":
                missing.append(f"{k}: MISSING")

        if metrics["E30_EVIDENCE_STATUS"] == "MISSING":
            print("E30_EVIDENCE_STATUS = MISSING")
            if metrics["LEDGER_STATUS"] != "ok":
                print(f"  LEDGER_STATUS = {metrics['LEDGER_STATUS']}")
            if metrics["OUTPUT_SHA"] is None:
                print("  OUTPUT_SHA = MISSING")
            if metrics["FRESH"] == "unknown":
                print("  FRESH = UNKNOWN")
            for item in missing:
                print(f"  MISSING: {item}")
        else:
            print("E30_EVIDENCE_STATUS = OK")

    if metrics["E30_EVIDENCE_STATUS"] == "MISSING":
        return 1
    return 0


# ── compare ─────────────────────────────────────────────────────────────────


def _pct_change(a: float | None, b: float | None) -> str | None:
    if a is None or b is None:
        return None
    if a == 0:
        return None
    pct = ((b - a) / a) * 100.0
    return f"{pct:+.1f}%"


def cmd_compare(args: argparse.Namespace) -> int:
    artifact_a = _load_artifact(args.arm_a)
    artifact_b = _load_artifact(args.arm_b)
    metrics_a = _extract_metrics(artifact_a)
    metrics_b = _extract_metrics(artifact_b)
    name_a = Path(args.arm_a).name
    name_b = Path(args.arm_b).name

    primary_keys = [
        ("CLIP_SOURCE_MS", "CLIP source"),
        ("CLIP_SOURCE_TO_GPU_READY_MS", "CLIP source->GPU ready"),
        ("CONFIGURED_QD", "Configured QD"),
        ("OBSERVED_MAX_OUTSTANDING", "Observed max O/S"),
        ("RESTORE_TOTAL_MS", "Restore total"),
        ("REMOTE_PYTHON_TO_DURABLE_MS", "Remote->durable"),
        ("CLIP_HYDRATION_MS", "CLIP hydration"),
        ("CLIP_FORWARD_MS", "CLIP forward"),
        ("UNET_PIPELINE_MS", "UNet pipeline"),
        ("TOTAL_UNATTRIBUTED_MS", "Unattributed"),
    ]

    if args.json:
        rows = []
        for key, label in primary_keys:
            va = metrics_a.get(key)
            vb = metrics_b.get(key)
            delta = None
            pct = None
            if isinstance(va, (int, float)) and isinstance(vb, (int, float)):
                delta = round(vb - va, 3)
                pct = _pct_change(va, vb)
            rows.append({
                "metric": key,
                "label": label,
                "arm_a": va,
                "arm_b": vb,
                "delta": delta,
                "pct_change": pct,
            })
        sha_match = (metrics_a.get("OUTPUT_SHA") == metrics_b.get("OUTPUT_SHA") and metrics_a.get("OUTPUT_SHA") is not None)
        verdict = _compute_verdict(metrics_a, metrics_b)
        out = {
            "arm_a": name_a,
            "arm_b": name_b,
            "metrics": rows,
            "sha_match": sha_match,
            "verdict": verdict,
        }
        print(json.dumps(out, indent=2, default=str))
    else:
        print("E30 A/B Comparison")
        print("==================")
        print(f"ARM A: {name_a}")
        print(f"ARM B: {name_b}")
        print()

        print(f"{'Metric':<32} {'ARM A':>12} {'ARM B':>12} {'Delta':>12} {'Change':>10}")
        print("-" * 82)
        for key, label in primary_keys:
            va = metrics_a.get(key)
            vb = metrics_b.get(key)
            delta_str = ""
            pct_str = ""
            if isinstance(va, (int, float)) and isinstance(vb, (int, float)):
                delta = round(vb - va, 3)
                delta_str = f"{delta:+.3f}"
                pct_str = _pct_change(va, vb) or ""
            fmt_a = f"{va:.3f}" if isinstance(va, float) else (str(va) if va is not None else "N/A")
            fmt_b = f"{vb:.3f}" if isinstance(vb, float) else (str(vb) if vb is not None else "N/A")
            print(f"  {label:<30} {fmt_a:>12} {fmt_b:>12} {delta_str:>12} {pct_str:>10}")
        print()

        sha_a = metrics_a.get("OUTPUT_SHA") or "MISSING"
        sha_b = metrics_b.get("OUTPUT_SHA") or "MISSING"
        sha_match = sha_a == sha_b and sha_a != "MISSING"
        print(f"  SHA verification:  {'PASS' if sha_match else 'FAIL'} ({sha_a[:12]}... vs {sha_b[:12]}...)")

        fresh_a = metrics_a.get("FRESH")
        fresh_b = metrics_b.get("FRESH")
        fresh_pass = (fresh_a in ("YES", True)) and (fresh_b in ("YES", True))
        print(f"  Freshness:         {'PASS' if fresh_pass else 'FAIL'} (A={fresh_a}, B={fresh_b})")
        print()

        clip_source_a = metrics_a.get("CLIP_SOURCE_MS")
        clip_source_b = metrics_b.get("CLIP_SOURCE_MS")
        if isinstance(clip_source_a, (int, float)) and isinstance(clip_source_b, (int, float)) and clip_source_a > 0:
            imp = ((clip_source_a - clip_source_b) / clip_source_a) * 100.0
            print(f"  CLIP_SOURCE_IMPROVEMENT:  {imp:.1f}% ({clip_source_a:.1f} ms vs {clip_source_b:.1f} ms)")

        restore_a = metrics_a.get("RESTORE_TOTAL_MS")
        restore_b = metrics_b.get("RESTORE_TOTAL_MS")
        if isinstance(restore_a, (int, float)) and isinstance(restore_b, (int, float)) and restore_a > 0:
            imp = ((restore_a - restore_b) / restore_a) * 100.0
            print(f"  RESTORE_IMPROVEMENT:      {imp:.1f}% ({restore_a:.1f} ms vs {restore_b:.1f} ms)")

        print(f"  SHA_VERIFICATION:         {'PASS' if sha_match else 'FAIL'}")
        print(f"  FRESHNESS:                {'PASS' if fresh_pass else 'FAIL'}")
        print()

        verdict = _compute_verdict(metrics_a, metrics_b)
        note = verdict.get("note", "")
        if note:
            print(f"  VERDICT = {verdict['verdict']} -- {verdict['reason']}")
            print(f"  NOTE: {note}")
        else:
            print(f"  VERDICT = {verdict['verdict']} -- {verdict['reason']}")

    return 0 if _compute_verdict(metrics_a, metrics_b)["verdict"] != "INVALID" else 1


def _compute_verdict(metrics_a: dict, metrics_b: dict) -> dict[str, str]:
    for key in ("CLIP_SOURCE_MS", "RESTORE_TOTAL_MS", "OUTPUT_SHA", "FRESH"):
        va = metrics_a.get(key)
        vb = metrics_b.get(key)
        if key == "OUTPUT_SHA" and (va is None or vb is None):
            return {
                "verdict": "INVALID",
                "reason": f"required evidence missing ({key})",
                "note": "",
            }
        if key == "FRESH" and (va == "unknown" or vb == "unknown"):
            return {
                "verdict": "INVALID",
                "reason": f"required evidence missing ({key})",
                "note": "",
            }

    if metrics_a.get("E30_EVIDENCE_STATUS") == "MISSING":
        return {
            "verdict": "INVALID",
            "reason": "required evidence missing from ARM A",
            "note": "",
        }
    if metrics_b.get("E30_EVIDENCE_STATUS") == "MISSING":
        return {
            "verdict": "INVALID",
            "reason": "required evidence missing from ARM B",
            "note": "",
        }

    fresh_a = metrics_a.get("FRESH")
    fresh_b = metrics_b.get("FRESH")
    if fresh_a not in ("YES", True) or fresh_b not in ("YES", True):
        return {
            "verdict": "INVALID",
            "reason": f"freshness fail (A={fresh_a}, B={fresh_b})",
            "note": "",
        }

    sha_a = metrics_a.get("OUTPUT_SHA")
    sha_b = metrics_b.get("OUTPUT_SHA")
    if sha_a is None or sha_b is None or sha_a != sha_b:
        return {
            "verdict": "INVALID",
            "reason": "SHA verification failed",
            "note": "",
        }

    clip_a = metrics_a.get("CLIP_SOURCE_MS")
    clip_b = metrics_b.get("CLIP_SOURCE_MS")
    restore_a = metrics_a.get("RESTORE_TOTAL_MS")
    restore_b = metrics_b.get("RESTORE_TOTAL_MS")

    timing_pairs = []
    if isinstance(clip_a, (int, float)) and isinstance(clip_b, (int, float)):
        timing_pairs.append(("clip_source", clip_a, clip_b))
    if isinstance(restore_a, (int, float)) and isinstance(restore_b, (int, float)):
        timing_pairs.append(("restore", restore_a, restore_b))

    if not timing_pairs:
        return {
            "verdict": "AMBIGUOUS",
            "reason": "insufficient timing data",
            "note": "",
        }

    improvements = []
    for label, a_val, b_val in timing_pairs:
        if a_val > 0:
            imp = ((a_val - b_val) / a_val) * 100.0
            improvements.append((label, imp))

    all_positive = all(imp > 2.0 for _, imp in improvements)
    all_negative = all(imp < -2.0 for _, imp in improvements)
    all_small = all(-2.0 <= imp <= 2.0 for _, imp in improvements)

    if all_positive:
        best = min(improvements, key=lambda x: x[1])
        return {
            "verdict": "DECISIVE",
            "reason": f"ARM B is better ({best[0]} improved by {best[1]:.1f}%)",
            "note": "",
        }
    if all_negative:
        best = max(improvements, key=lambda x: x[1])
        return {
            "verdict": "DECISIVE",
            "reason": f"ARM A is better ({best[0]} improved by {-best[1]:.1f}%)",
            "note": "",
        }
    if all_small:
        return {
            "verdict": "DECISIVE",
            "reason": "no meaningful timing difference",
            "note": "",
        }
    return {
        "verdict": "AMBIGUOUS",
        "reason": "contradictory or noise-dominated timing signals",
        "note": "Result is ambiguous. Consider reversing the run order: "
                "ARM B (QD ON) first, then ARM A (QD OFF), to test for ordering effects.",
    }


# ── main ────────────────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(description="E30 A/B Analysis Tool")
    sub = parser.add_subparsers(dest="command", required=True)

    p_diff = sub.add_parser("diff", help="Diff ARM A and ARM B profiles")
    p_diff.add_argument("--arm-a", default=DEFAULT_ARM_A, help="ARM A profile name")
    p_diff.add_argument("--arm-b", default=DEFAULT_ARM_B, help="ARM B profile name")
    p_diff.add_argument("--json", action="store_true", help="Output as JSON")
    p_diff.add_argument("--verbose", action="store_true", help="Show identical flags")

    p_extract = sub.add_parser("extract", help="Extract E30 metrics from artifact")
    p_extract.add_argument("artifact", help="Path to run artifact JSON")
    p_extract.add_argument("--json", action="store_true", help="Output as JSON")

    p_compare = sub.add_parser("compare", help="Compare two artifacts side by side")
    p_compare.add_argument("arm_a", help="Path to ARM A artifact JSON")
    p_compare.add_argument("arm_b", help="Path to ARM B artifact JSON")
    p_compare.add_argument("--json", action="store_true", help="Output as JSON")

    args = parser.parse_args()

    if args.command == "diff":
        rc = cmd_diff(args)
    elif args.command == "extract":
        rc = cmd_extract(args)
    elif args.command == "compare":
        rc = cmd_compare(args)
    else:
        parser.print_help()
        rc = 1

    sys.exit(rc)


if __name__ == "__main__":
    main()
