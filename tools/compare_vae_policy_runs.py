#!/usr/bin/env python3
"""Offline VAE policy run comparator.

Consumes a baseline V0 run manifest plus candidate run manifests (or a plain
JSON list of run records), locates the per-run image path, asserts
policy/applied-policy metadata, compares each candidate against the V0
baseline with explicit gates, and checks same-policy asset SHA determinism.
Writes a JSON result with metrics and pass/fail gates.

This tool NEVER auto-selects a winner.  It reports pass/fail and warnings only.

Explicit default gates:
    psnr_min              >= 30 dB
    ssim_min              >= 0.95
    mad_max               <= 2/255
    max_ad_max            <= 12/255
    decode_regression_max <= 25% (candidate may be at most 25% slower than V0)
    no NaN/Inf/blank/shape change

Usage:
    python tools/compare_vae_policy_runs.py \\
        --baseline baseline_run.json --candidate v1_run.json --out result.json
"""

import argparse
import hashlib
import json
import os
from typing import Any, Dict, List, Optional

try:
    from tools.image_metrics import compute_metrics
except ImportError:
    from image_metrics import compute_metrics

DEFAULT_GATES: Dict[str, float] = {
    "psnr_min": 30.0,
    "ssim_min": 0.95,
    "mad_max": 2.0 / 255.0,
    "max_ad_max": 12.0 / 255.0,
    "decode_regression_max": 25.0,
}


def load_run_records(path: str) -> List[Dict[str, Any]]:
    """Load a run manifest / plain list / single record into a list of dicts."""
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, dict):
        if "runs" in data and isinstance(data["runs"], list):
            return data["runs"]
        return [data]
    if isinstance(data, list):
        return data
    raise ValueError(f"unsupported run file shape: {path}")


def locate_image_path(record: Dict[str, Any]) -> Optional[str]:
    """Resolve the image path for a run record."""
    for key in ("image_path", "image", "path"):
        val = record.get(key)
        if isinstance(val, str) and val:
            return val
    outputs = record.get("outputs")
    if isinstance(outputs, list) and outputs:
        first = outputs[0]
        if isinstance(first, str):
            return first
        if isinstance(first, dict):
            for key in ("path", "filename", "image_path"):
                if isinstance(first.get(key), str) and first[key]:
                    return first[key]
    return None


def get_decode_ms(record: Dict[str, Any]) -> Optional[float]:
    """Extract decode duration in ms from a run record."""
    raw = record.get("decode_ms")
    if raw is not None:
        return _to_float(raw)
    metrics = record.get("metrics")
    if isinstance(metrics, dict):
        for key in ("decode_ms", "vae_decode_ms"):
            if metrics.get(key) is not None:
                return _to_float(metrics[key])
    return None


def _to_float(value: Any) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def asset_sha(path: str) -> Optional[str]:
    """Return the sha256 hex digest of a file's bytes, or None."""
    try:
        with open(path, "rb") as f:
            return hashlib.sha256(f.read()).hexdigest()
    except (OSError, FileNotFoundError):
        return None


def _resolve_image_path(path: str, image_root: Optional[str]) -> Optional[str]:
    """Resolve a (possibly relative) asset path against an optional root."""
    if not path:
        return None
    if image_root and not os.path.isabs(path):
        return os.path.join(image_root, path)
    return path


def recover_applied_policy(record: Dict[str, Any]) -> Any:
    """Recover the applied VAE policy from runtime trace events, or None.

    Reads the `cpu_snapshot_vae_policy_ready` event metadata from
    record.result.trace.events, preferring the explicit policy mode and
    otherwise reconstructing a tuple from the concrete dtypes/memory format.
    """
    result = record.get("result")
    if not isinstance(result, dict):
        return None
    trace = result.get("trace")
    events = trace.get("events") if isinstance(trace, dict) else None
    if not isinstance(events, list):
        return None
    for ev in events:
        if not isinstance(ev, dict):
            continue
        if ev.get("name") != "cpu_snapshot_vae_policy_ready":
            continue
        md = ev.get("metadata")
        if not isinstance(md, dict):
            return None
        mode = md.get("vae_policy_mode")
        weight = md.get("vae_weight_dtype") or md.get("weight_dtype")
        compute = md.get("vae_compute_dtype") or md.get("compute_dtype")
        memfmt = md.get("vae_memory_format") or md.get("memory_format")
        if mode:
            return mode
        if weight and compute and memfmt:
            return f"tuple:{weight}:{compute}:{memfmt}"
    return None


def _extract_nested_image_path(record: Dict[str, Any], image_root: Optional[str]) -> Optional[str]:
    """Locate an image path, supporting record.result.images assets."""
    for key in ("image_path", "image", "path"):
        val = record.get(key)
        if isinstance(val, str) and val:
            return _resolve_image_path(val, image_root)
    result = record.get("result")
    if isinstance(result, dict):
        images = result.get("images")
        if isinstance(images, list):
            for img in images:
                if not isinstance(img, dict):
                    continue
                for key in ("path", "backend_path"):
                    v = img.get(key)
                    if isinstance(v, str) and v:
                        return _resolve_image_path(v, image_root)
        elif isinstance(images, dict):
            for v in images.values():
                if not isinstance(v, dict):
                    continue
                for key in ("path", "backend_path"):
                    p = v.get(key)
                    if isinstance(p, str) and p:
                        return _resolve_image_path(p, image_root)
    outputs = record.get("outputs")
    if isinstance(outputs, list) and outputs:
        first = outputs[0]
        if isinstance(first, str):
            return _resolve_image_path(first, image_root)
        if isinstance(first, dict):
            for key in ("path", "filename", "image_path"):
                if isinstance(first.get(key), str) and first[key]:
                    return _resolve_image_path(first[key], image_root)
    return None


def _extract_decode_ms(record: Dict[str, Any]) -> Optional[float]:
    """Extract decode duration in ms, including record.timing.vae_decode_ms."""
    raw = record.get("decode_ms")
    if raw is not None:
        return _to_float(raw)
    timing = record.get("timing")
    if isinstance(timing, dict) and timing.get("vae_decode_ms") is not None:
        return _to_float(timing["vae_decode_ms"])
    metrics = record.get("metrics")
    if isinstance(metrics, dict):
        for key in ("decode_ms", "vae_decode_ms"):
            if metrics.get(key) is not None:
                return _to_float(metrics[key])
    return None


def normalize_record(record: Dict[str, Any], image_root: Optional[str] = None) -> Dict[str, Any]:
    """Normalize a raw or already-normalized run record into comparison form.

    Idempotent: normalized fields pass through.  For raw nested records,
    images are located under record.result.images, timing under
    record.timing.vae_decode_ms, and the applied policy is recovered from
    trace events.  The requested policy is NEVER invented; it is taken only
    from the manifest/arm metadata present on the record, so a missing or
    mismatched requested policy fails.
    """
    norm = dict(record)
    norm["requested_policy"] = record.get("requested_policy", record.get("policy"))
    applied = record.get("applied_policy")
    if applied is None:
        applied = recover_applied_policy(record)
    norm["applied_policy"] = applied
    norm["image_path"] = _extract_nested_image_path(record, image_root)
    norm["decode_ms"] = _extract_decode_ms(record)
    return norm


def _canonical_policy(value: Any) -> Any:
    """Return a canonical, comparable form of a policy (dicts via JSON keys)."""
    if isinstance(value, dict):
        return json.dumps(value, sort_keys=True, separators=(",", ":"))
    return value


def assert_policy_metadata(record: Dict[str, Any]) -> Dict[str, Any]:
    """Assert that requested and applied policy metadata are present and equal.

    Policies may be scalars or dicts; dicts are compared via canonical JSON
    keys.  Returns ok/errors without mutating the record.
    """
    requested = record.get("requested_policy", record.get("policy"))
    applied = record.get("applied_policy")
    errors = []
    if requested is None and applied is None:
        errors.append("missing requested_policy and applied_policy")
    elif requested is None:
        errors.append("requested_policy missing")
    elif applied is None:
        errors.append("applied_policy missing")
    elif _canonical_policy(requested) != _canonical_policy(applied):
        errors.append("applied_policy does not match requested_policy")
    return {
        "requested_policy": requested,
        "applied_policy": applied,
        "ok": not errors,
        "errors": errors,
    }


def evaluate_gate(name: str, value: Optional[float], op: str, limit: float) -> Dict[str, Any]:
    if value is None:
        # Missing data is not a failure; it is "not applicable".
        return {"gate": name, "ok": True, "value": None, "limit": limit, "status": "na"}
    if op == "gte":
        ok = value >= limit
    elif op == "lte":
        ok = value <= limit
    else:
        ok = False
    return {"gate": name, "ok": bool(ok), "value": value, "limit": limit, "status": "pass" if ok else "fail"}


def evaluate_candidate(
    baseline: Dict[str, Any],
    candidate: Dict[str, Any],
    gates: Dict[str, float],
    image_root: Optional[str] = None,
) -> Dict[str, Any]:
    """Compare a candidate run record against the V0 baseline record."""
    baseline = normalize_record(baseline, image_root)
    candidate = normalize_record(candidate, image_root)
    meta = assert_policy_metadata(candidate)
    base_img = locate_image_path(baseline)
    cand_img = locate_image_path(candidate)

    if base_img is None or cand_img is None:
        return {
            "arm": candidate.get("arm"),
            "requested_policy": meta["requested_policy"],
            "applied_policy": meta["applied_policy"],
            "metadata_ok": meta["ok"],
            "metadata_errors": meta["errors"],
            "baseline_image": base_img,
            "candidate_image": cand_img,
            "metrics": None,
            "gates": [],
            "pass": False,
            "warnings": ["missing image path(s); no comparison performed"],
        }

    metrics = compute_metrics(base_img, cand_img)

    checks = metrics["checks"]
    shape_ok = checks["same_size"] and checks["same_channels"]
    blank_or_nonfinite = (
        checks["blank_a"] or checks["blank_b"] or checks["nan_a"]
        or checks["nan_b"] or checks["inf_a"] or checks["inf_b"]
    )

    base_decode = get_decode_ms(baseline)
    cand_decode = get_decode_ms(candidate)
    decode_regression = None
    if base_decode is not None and cand_decode is not None and base_decode > 0:
        decode_regression = (cand_decode - base_decode) / base_decode * 100.0

    gates_result = []
    gates_result.append(evaluate_gate("psnr", metrics["psnr"], "gte", gates["psnr_min"]))
    gates_result.append(evaluate_gate("ssim", metrics["ssim"], "gte", gates["ssim_min"]))
    gates_result.append(evaluate_gate("mad", metrics["mean_abs_diff"], "lte", gates["mad_max"]))
    gates_result.append(evaluate_gate("max_ad", metrics["max_abs_diff"], "lte", gates["max_ad_max"]))
    gates_result.append(evaluate_gate(
        "decode_regression_pct", decode_regression, "lte", gates["decode_regression_max"]
    ))

    warnings: List[str] = []
    if not shape_ok:
        warnings.append("shape/channel change detected")
    if blank_or_nonfinite:
        warnings.append("blank or non-finite pixels detected")
    if metrics["psnr"] is None and not metrics["identical"]:
        warnings.append("psnr unavailable (invalid images)")
    if decode_regression is None:
        warnings.append("decode timing missing; decode_regression gate not evaluated")

    all_ok = meta["ok"] and shape_ok and not blank_or_nonfinite and all(g["ok"] for g in gates_result)
    return {
        "arm": candidate.get("arm"),
        "requested_policy": meta["requested_policy"],
        "applied_policy": meta["applied_policy"],
        "metadata_ok": meta["ok"],
        "metadata_errors": meta["errors"],
        "baseline_image": base_img,
        "candidate_image": cand_img,
        "baseline_decode_ms": base_decode,
        "candidate_decode_ms": cand_decode,
        "decode_regression_pct": decode_regression,
        "metrics": {
            "mean_abs_diff": metrics["mean_abs_diff"],
            "max_abs_diff": metrics["max_abs_diff"],
            "rmse": metrics["rmse"],
            "psnr": metrics["psnr"],
            "ssim": metrics["ssim"],
            "identical": metrics["identical"],
        },
        "checks": checks,
        "gates": gates_result,
        "pass": bool(all_ok),
        "warnings": warnings,
    }


def check_same_policy_sha(candidates: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Group candidates by applied_policy and verify asset SHA determinism.

    Applied policies may be dicts; they are grouped via canonical JSON keys.
    """
    groups: Dict[str, List[Dict[str, Any]]] = {}
    applied_labels: Dict[str, Any] = {}
    for cand in candidates:
        applied = cand.get("applied_policy")
        if applied is None:
            continue
        key = _canonical_policy(applied)
        groups.setdefault(key, []).append(cand)
        applied_labels.setdefault(key, applied)

    violations = []
    for key, members in sorted(groups.items()):
        shas = {}
        for m in members:
            img = locate_image_path(m)
            m["asset_sha"] = asset_sha(img) if img else None
            shas.setdefault(m.get("asset_sha"), []).append(m.get("arm"))
        if len(shas) > 1:
            violations.append({
                "applied_policy": applied_labels[key],
                "distinct_asset_shas": len(shas),
                "arms_by_sha": {k: v for k, v in shas.items()},
            })

    return {
        "groups": {k: len(v) for k, v in groups.items()},
        "deterministic": not violations,
        "violations": violations,
    }


def run_comparison(
    baseline_path: str,
    candidate_paths: List[str],
    gates: Optional[Dict[str, float]] = None,
    image_root: Optional[str] = None,
) -> Dict[str, Any]:
    if gates is None:
        gates = dict(DEFAULT_GATES)

    baseline_records = [normalize_record(r, image_root) for r in load_run_records(baseline_path)]
    baseline = baseline_records[0]

    candidates: List[Dict[str, Any]] = []
    for p in candidate_paths:
        candidates.extend(
            normalize_record(r, image_root) for r in load_run_records(p)
        )

    results = [evaluate_candidate(baseline, c, gates, image_root=image_root) for c in candidates]
    sha_check = check_same_policy_sha(candidates)

    return {
        "schema": "comfymodal.v2_vae_policy_run.comparison.v1",
        "baseline": baseline_path,
        "candidates": candidate_paths,
        "gates": gates,
        "same_policy_sha": sha_check,
        "results": results,
        "overall_pass": bool(
            all(r["pass"] for r in results) and sha_check["deterministic"]
        ),
        "warning": "Tool reports pass/fail only; it never auto-selects a winner.",
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Compare VAE policy run records against a V0 baseline."
    )
    parser.add_argument("--baseline", required=True, help="V0 baseline run manifest")
    parser.add_argument("--candidate", nargs="+", required=True, help="candidate run manifest(s)")
    parser.add_argument(
        "--image-root", default=None,
        help="optional root dir for resolving relative asset paths",
    )
    parser.add_argument("--out", default=None, help="write JSON result to path")
    parser.add_argument("--print", dest="print_result", action="store_true", help="print result JSON")
    args = parser.parse_args()

    result = run_comparison(args.baseline, args.candidate, image_root=args.image_root)
    text = json.dumps(result, indent=2, sort_keys=True, allow_nan=False)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(text + "\n")
    if args.print_result:
        print(text)


if __name__ == "__main__":
    main()
