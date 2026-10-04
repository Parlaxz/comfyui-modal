"""Aggregate the Agent-1 treatment and control cohorts into one table.

Usage: python tools/p10a1_stats.py <treatment_paths.txt> <control_paths.txt>
"""
from __future__ import annotations

import json
import statistics
import sys
from typing import Any

EXPECTED_SHA = "3a6a03064c7e6e01ede339ada63daaea4cbf793f387f4faadbb101a787024577"


def _get(obj: Any, *path: str, default: Any = None) -> Any:
    cur = obj
    for key in path:
        if not isinstance(cur, dict) or key not in cur:
            return default
        cur = cur[key]
    return cur


def _last_event_fields(gt: Any, name: str) -> dict:
    found: dict = {}
    for event in _get(gt, "events") or []:
        if isinstance(event, dict) and event.get("name") == name:
            if isinstance(event.get("fields"), dict):
                found = event["fields"]
    return found


def _stage_walls(gt: Any) -> dict:
    walls: dict = {}
    for record in _get(gt, "stages") or []:
        if not isinstance(record, dict):
            continue
        name = record.get("name") or record.get("stage")
        wall = record.get("wall_ms")
        if wall is None:
            start, end = record.get("entry_monotonic_ns"), record.get("end_monotonic_ns")
            if isinstance(start, int) and isinstance(end, int):
                wall = (end - start) / 1e6
        if name and wall is not None:
            walls[name] = float(wall)
    return walls


def load(path: str) -> dict:
    d = json.load(open(path, encoding="utf-8"))
    gt = d.get("golden_telemetry") or {}
    clip = _last_event_fields(gt, "golden_metadata_cache_result")
    unet = _last_event_fields(gt, "unet_layout_preresolve")
    vae = _last_event_fields(gt, "vae_dynamicvram_activation_result")
    return {
        "request_id": d.get("request_id"),
        "valid": bool(d.get("valid")),
        "true_cold": bool(d.get("true_cold")),
        "restore_count": _get(d, "identity", "restore_count"),
        "request_count": _get(d, "identity", "request_count"),
        "fallback": _get(gt, "fallback_reason"),
        "fatal_failure": bool(gt.get("fatal_failure")),
        "sha": (_get(d, "validation", "observed_output_shas") or [None])[0],
        "duration_ms": d.get("duration_ms"),
        "clip_hit": clip.get("clip_meta_cache_hit"),
        "layout_source": clip.get("layout_cache_source"),
        "layout_lookup_ms": clip.get("layout_lookup_ms"),
        "hydration_ms": clip.get("metadata_cache_hydration_ms"),
        "identity_match": clip.get("metadata_cache_identity_match"),
        "unet_preresolve_ms": unet.get("preresolve_ms"),
        "unet_join_completed": unet.get("unet_layout_preresolve_join_completed"),
        "unet_before_clip_forward": unet.get("completed_before_clip_forward"),
        "unet_layout_cache_hit": unet.get("layout_cache_hit"),
        "vae_status": vae.get("status"),
        "vae_activation_ms": vae.get("activation_ms"),
        "vae_inside_sampling": vae.get("inside_sampling"),
        "vae_hidden_ms": vae.get("hidden_by_sampling_ms"),
        "vae_registry_vae_after_restore": vae.get(
            "registry_entries_after_restore_vae_count"),
        "vae_registry_restored": vae.get("registry_restored"),
        "decode_wall_ms": _stage_walls(gt).get("golden_vae_decode"),
        "root_wall_ms": d.get("duration_ms"),
    }


def stats(values: list) -> str:
    clean = [v for v in values if isinstance(v, (int, float))]
    if not clean:
        return "n/a"
    text = f"n={len(clean)} min={min(clean):.3f} p50={statistics.median(clean):.3f}"
    text += f" mean={statistics.mean(clean):.3f} max={max(clean):.3f}"
    if len(clean) > 1:
        text += f" sd={statistics.stdev(clean):.3f}"
    return text


def report(label: str, rows: list) -> None:
    print(f"\n================ {label} (n={len(rows)})")
    ok = [r for r in rows if r["valid"] and r["true_cold"]]
    print(f"  valid+true_cold        : {len(ok)}/{len(rows)}")
    print(f"  restore_count==1       : {sum(1 for r in rows if r['restore_count'] == 1)}/{len(rows)}")
    print(f"  request_count==1       : {sum(1 for r in rows if r['request_count'] == 1)}/{len(rows)}")
    print(f"  fallback is None       : {sum(1 for r in rows if r['fallback'] is None)}/{len(rows)}")
    print(f"  fatal_failure False    : {sum(1 for r in rows if not r['fatal_failure'])}/{len(rows)}")
    print(f"  exact expected SHA     : {sum(1 for r in rows if r['sha'] == EXPECTED_SHA)}/{len(rows)}")
    for field, name in (
        ("clip_hit", "CLIP cache hit"),
        ("identity_match", "CLIP identity match"),
        ("layout_source", "CLIP layout source"),
        ("unet_join_completed", "UNET bounded join completed"),
        ("unet_before_clip_forward", "UNET done before CLIP fwd"),
        ("unet_layout_cache_hit", "UNET layout cache hit"),
        ("vae_status", "VAE activation status"),
        ("vae_inside_sampling", "VAE inside sampling"),
        ("vae_registry_restored", "VAE registry restored"),
    ):
        values = [r[field] for r in rows]
        distinct = sorted({str(v) for v in values})
        print(f"  {name:24s}: {', '.join(distinct)}")
    print(f"  VAE registry VAE count after restore: "
          f"{sorted({r['vae_registry_vae_after_restore'] for r in rows}, key=str)}")
    for field, name in (
        ("duration_ms", "root wall ms"),
        ("hydration_ms", "CLIP hydration ms"),
        ("layout_lookup_ms", "CLIP layout lookup ms"),
        ("unet_preresolve_ms", "UNET preresolve ms"),
        ("vae_activation_ms", "VAE activation ms"),
        ("vae_hidden_ms", "VAE hidden by sampling ms"),
        ("decode_wall_ms", "golden_vae_decode wall ms"),
    ):
        print(f"  {name:28s}: {stats([r[field] for r in rows])}")


if __name__ == "__main__":
    treat = [load(p) for p in open(sys.argv[1], encoding="utf-8").read().split("\n") if p.strip()]
    ctrl = [load(p) for p in open(sys.argv[2], encoding="utf-8").read().split("\n") if p.strip()]
    report("TREATMENT  app=p10a1-cache-vae-unet  fp=5b2e43f0", treat)
    report("CONTROL     app=p10a1-ctrl-novae    fp=cc73efd5 (CLIP cache + UNET only)", ctrl)
