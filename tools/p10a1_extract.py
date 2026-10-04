"""Extract the Agent-1 evidence fields from one Golden attempt artifact.

Usage: python tools/p10a1_extract.py <attempt.json> [...]
Prints one compact block per artifact so a cohort can be compared at a glance.
"""
from __future__ import annotations

import json
import sys
from typing import Any


def _get(obj: Any, *path: str, default: Any = None) -> Any:
    cur = obj
    for key in path:
        if not isinstance(cur, dict) or key not in cur:
            return default
        cur = cur[key]
    return cur


def _f(value: Any) -> str:
    if isinstance(value, float):
        return f"{value:.3f}"
    return str(value)


def _events(gt: Any) -> list:
    events = _get(gt, "events")
    return events if isinstance(events, list) else []


def _last_event_fields(gt: Any, name: str) -> dict:
    """Last event called ``name`` wins; earlier ones are pre-state snapshots."""
    found: dict = {}
    for event in _events(gt):
        if event.get("name") == name and isinstance(event.get("fields"), dict):
            found = event["fields"]
    return found


def _merge_event(gt: Any, name: str, prefix: str, keys: tuple[str, ...]) -> dict:
    fields = _last_event_fields(gt, name)
    out = {}
    for key in keys:
        if key in fields:
            out[f"{prefix}.{key}"] = _f(fields[key])
    return out


def summarize(path: str) -> None:
    d = json.load(open(path, encoding="utf-8"))
    gt = d.get("golden_telemetry") or {}
    val = d.get("validation") or {}
    ident = d.get("identity") or {}
    out: dict[str, Any] = {
        "request_id": d.get("request_id"),
        "valid": d.get("valid"),
        "true_cold": d.get("true_cold"),
        "dnf": d.get("dnf"),
        "error": d.get("error"),
        "duration_ms": _f(d.get("duration_ms")),
        "restore_count": ident.get("restore_count"),
        "request_count": ident.get("request_count"),
        "fallback": _get(gt, "fallback_reason"),
        "fatal_failure": gt.get("fatal_failure"),
        "output_sha_match": val.get("output_sha_match"),
        "observed_output_shas": ",".join(val.get("observed_output_shas") or []),
        "capture_guard_state": _get(d, "capture_guard", "state"),
    }
    # ---- CLIP persistent cache (post-load result event) -------------------
    out.update(_merge_event(
        gt, "golden_metadata_cache_result", "clip",
        ("clip_meta_cache_hit", "layout_cache_source", "layout_lookup_ms",
         "metadata_cache_entry_hit", "metadata_cache_identity_match",
         "metadata_cache_hydration_ms", "metadata_cache_schema",
         "metadata_cache_file_bytes", "residual_meta_build_ms",
         "meta_blueprint_lookup_ms"),
    ))
    # ---- UNET bounded pre-resolve (join stage is the informative one) -----
    out.update(_merge_event(
        gt, "unet_layout_preresolve", "unet",
        ("preresolve_ms", "status", "layout_cache_hit",
         "unet_layout_preresolve_joined",
         "unet_layout_preresolve_join_completed",
         "completed_before_clip_forward", "path_basename"),
    ))
    # ---- VAE DynamicVRAM early activation ---------------------------------
    out.update(_merge_event(
        gt, "vae_dynamicvram_activation_result", "vae",
        ("status", "reason", "activation_ms", "inside_sampling",
         "sampling_active_at_start", "hidden_by_sampling_ms", "registered",
         "resident", "on_load_device", "registry_restored",
         "registry_entries_before", "registry_entries_during",
         "registry_entries_after_restore",
         "registry_entries_after_restore_vae_count", "loaded_size_bytes",
         "load_device"),
    ))
    # ---- stage walls ------------------------------------------------------
    # Stage records carry monotonic bounds rather than a precomputed wall_ms.
    stage_walls: dict[str, float] = {}
    for record in _get(gt, "stages") or []:
        if not isinstance(record, dict):
            continue
        name = record.get("name") or record.get("stage") or "?"
        wall = record.get("wall_ms")
        if wall is None:
            start = record.get("entry_monotonic_ns")
            end = record.get("end_monotonic_ns")
            if isinstance(start, int) and isinstance(end, int):
                wall = (end - start) / 1e6
        if wall is not None:
            stage_walls[name] = float(wall)
            out[f"stage.{name}"] = _f(wall)
    # Golden root = union of the stages, since they overlap.
    if stage_walls:
        out["stage_unions_wall_ms"] = _f(sum(stage_walls.values()))
    root = _get(gt, "sampler_total_wall_ms")
    if root is not None:
        out["sampler_total_wall_ms"] = _f(root)
    sv = _get(gt, "sampling_vae_overlap") or {}
    if isinstance(sv, dict):
        for key in ("true_overlap", "overlap_intersection_ms",
                    "wall_hidden_by_overlap_ms", "vae_load_wall_ms",
                    "sampling_wall_ms"):
            if sv.get(key) is not None:
                out[f"sampling_vae.{key}"] = _f(sv.get(key))

    print(f"--- {path}")
    for k, v in out.items():
        print(f"    {k} = {v}")
    # Machine-readable tail so a cohort can be aggregated without re-parsing.
    print("    JSON " + json.dumps({
        "request_id": out.get("request_id"),
        "valid": d.get("valid"), "true_cold": d.get("true_cold"),
        "output_sha": (val.get("observed_output_shas") or [None])[0],
        "duration_ms": d.get("duration_ms"),
        "clip_hit": _get(gt, "events", default=None) is not None
        and _last_event_fields(gt, "golden_metadata_cache_result").get(
            "clip_meta_cache_hit"),
        "hydration_ms": _last_event_fields(
            gt, "golden_metadata_cache_result").get("metadata_cache_hydration_ms"),
        "layout_lookup_ms": _last_event_fields(
            gt, "golden_metadata_cache_result").get("layout_lookup_ms"),
        "unet_preresolve_ms": _last_event_fields(
            gt, "unet_layout_preresolve").get("preresolve_ms"),
        "unet_join_completed": _last_event_fields(
            gt, "unet_layout_preresolve").get(
                "unet_layout_preresolve_join_completed"),
        "vae_activation_ms": _last_event_fields(
            gt, "vae_dynamicvram_activation_result").get("activation_ms"),
        "vae_inside_sampling": _last_event_fields(
            gt, "vae_dynamicvram_activation_result").get("inside_sampling"),
        "vae_hidden_ms": _last_event_fields(
            gt, "vae_dynamicvram_activation_result").get("hidden_by_sampling_ms"),
        "vae_registry_vae_count_after_restore": _last_event_fields(
            gt, "vae_dynamicvram_activation_result").get(
                "registry_entries_after_restore_vae_count"),
        "vae_decode_wall_ms": stage_walls.get("golden_vae_decode"),
        "sampler_tail_wall_ms": stage_walls.get("golden_sampler_tail"),
        "sampling_stage_wall_ms": stage_walls.get("golden_sampling"),
        "vae_load_stage_wall_ms": stage_walls.get("golden_vae_load"),
        "restore_wall_ms": stage_walls.get("golden_restore"),
        "clip_load_wall_ms": stage_walls.get("golden_clip_load"),
        "unet_load_wall_ms": stage_walls.get("golden_unet_load"),
        "output_wall_ms": stage_walls.get("golden_output"),
    }))


if __name__ == "__main__":
    for argument in sys.argv[1:]:
        summarize(argument)