"""Pure Wave-2 logical-output and replay contract fixtures.

The logical-output fields are the expected additive projection for Phase E.
They are intentionally independent of the production History implementation;
the fake HTTP seed is state/UI evidence until the production projection lands.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any


HISTORY_ASSET_PREFIX = "/comfymodal/history-v2/assets/"
PREVIEW_OPTIONS = {"enabled": True, "codec": "webp", "quality": 70}


def _url(asset_id: str) -> str:
    return f"{HISTORY_ASSET_PREFIX}{asset_id}"


def _attempt(
    run_id: str,
    mode: str,
    status: str,
    *,
    logical_output_key: str,
    codec: str | None = None,
    quality: int | None = None,
    error: str | None = None,
) -> dict[str, Any]:
    terminal = status in {"completed", "failed", "canceled", "interrupted"}
    return {
        "run_id": run_id,
        "mode": mode,
        "status": status,
        "started_at": "2026-08-17T12:00:00.000Z",
        "finished_at": "2026-08-17T12:00:01.000Z" if terminal else None,
        "duration_ms": 1000 if terminal else None,
        "error": error,
        "timing": {"end_to_end_total_ms": 1000} if status == "completed" else None,
        "logical_output_key": logical_output_key,
        "codec": codec,
        "quality": quality,
    }


def _output(
    logical_output_key: str,
    *,
    thumb: bool = True,
    preview: bool = True,
    original_asset_ids: list[str] | None = None,
    attempt_ids: list[str] | None = None,
    original_failed: bool = False,
) -> dict[str, Any]:
    thumb_id = f"{logical_output_key}_thumb" if thumb else ""
    preview_id = f"{logical_output_key}_preview" if preview else ""
    originals = list(original_asset_ids or [])
    preferred_original = originals[-1] if originals else ""
    provenance: list[dict[str, str]] = []
    if thumb_id:
        provenance.append({"asset_id": thumb_id, "asset_type": "thumbnail", "attempt_id": (attempt_ids or [""])[0]})
    if preview_id:
        provenance.append({"asset_id": preview_id, "asset_type": "preview", "attempt_id": (attempt_ids or [""])[0]})
    for index, asset_id in enumerate(originals):
        provenance.append({
            "asset_id": asset_id,
            "asset_type": "original",
            "attempt_id": (attempt_ids or [""])[min(index + 1, len(attempt_ids or [""]) - 1)],
        })
    return {
        "index": 0,
        "logical_output_key": logical_output_key,
        "asset_id": preferred_original or preview_id or thumb_id,
        "thumb_url": _url(thumb_id) if thumb_id else "",
        "preview_url": _url(preview_id) if preview_id else "",
        "original_url": _url(preferred_original) if preferred_original else "",
        "original_urls": [_url(asset_id) for asset_id in originals],
        "original_failed": original_failed,
        "attempt_ids": list(attempt_ids or []),
        "asset_provenance": provenance,
        "preview_codec": "webp" if preview_id else "",
        "preview_quality": 70 if preview_id else None,
        "status": "success",
    }


def _generation(
    generation_id: str,
    attempts: list[dict[str, Any]],
    outputs: list[dict[str, Any]],
    *,
    featured_output_index: int = 0,
    featured_asset_id: str = "",
    status: str = "completed",
) -> dict[str, Any]:
    return {
        "id": generation_id,
        "kind": "generation",
        "status": status,
        "workflow_id": "wf_phase_e",
        "workflow_name": "Phase E Workflow",
        "workflow_version": "wv_phase_e",
        "preset_id": "preset_phase_e",
        "preset_name": "Phase E Preset",
        "prompt": "phase e wave 2 contract fixture",
        "created_at": "2026-08-17T12:00:00.000Z",
        "output_count": len(outputs),
        "has_image": bool(outputs),
        "preview_only": bool(outputs and any(o["preview_url"] for o in outputs) and not any(o["original_url"] for o in outputs)),
        "original_available": any(o["original_url"] for o in outputs),
        "featured_output_index": featured_output_index,
        "featured_asset_id": featured_asset_id,
        "outputs": outputs,
        "attempts": attempts,
        "errors": [
            {"code": "attempt_failed", "message": attempt["error"]}
            for attempt in attempts
            if attempt.get("error")
        ],
        "params": {},
        "workflow_json": {"3": {"class_type": "KSampler", "inputs": {"seed": 42}}},
    }


def logical_output_generation() -> dict[str, Any]:
    key = "gen_wave2_logical_o0"
    attempts = [
        _attempt("run_wave2_preview", "preview", "completed", logical_output_key=key, codec="webp", quality=70),
        _attempt("run_wave2_original_old", "original", "completed", logical_output_key=key),
        _attempt("run_wave2_original_new", "original", "completed", logical_output_key=key),
    ]
    return _generation(
        "gen_phase_e_wave2_logical",
        attempts,
        [_output(
            key,
            original_asset_ids=["gen_wave2_logical_old_orig", "gen_wave2_logical_new_orig"],
            attempt_ids=[attempt["run_id"] for attempt in attempts],
        )],
    )


def retry_generation() -> dict[str, Any]:
    key = "gen_wave2_retry_o0"
    attempts = [
        _attempt("run_wave2_retry_preview", "preview", "completed", logical_output_key=key, codec="webp", quality=70),
        _attempt("run_wave2_retry_original_failed", "original", "failed", logical_output_key=key, error="Original upload failed"),
        _attempt("run_wave2_retry_original", "original", "completed", logical_output_key=key),
    ]
    return _generation(
        "gen_phase_e_wave2_retry",
        attempts,
        [_output(
            key,
            original_asset_ids=["gen_wave2_retry_orig"],
            attempt_ids=[attempt["run_id"] for attempt in attempts],
        )],
    )


def two_logical_outputs_generation() -> dict[str, Any]:
    keys = ["gen_wave2_two_o0", "gen_wave2_two_o1"]
    attempts = [
        _attempt("run_wave2_two_preview", "preview", "completed", logical_output_key=keys[0], codec="webp", quality=70),
        _attempt("run_wave2_two_original", "original", "completed", logical_output_key=keys[0]),
    ]
    outputs = [
        _output(keys[0], original_asset_ids=["gen_wave2_two_o0_orig"], attempt_ids=[a["run_id"] for a in attempts]),
        _output(keys[1], thumb=True, preview=True, original_asset_ids=[], attempt_ids=[attempts[0]["run_id"]]),
    ]
    for index, output in enumerate(outputs):
        output["index"] = index
    return _generation("gen_phase_e_wave2_two", attempts, outputs)


def featured_variant_generation(variant: str) -> dict[str, Any]:
    keys = [f"gen_wave2_featured_{variant}_o0", f"gen_wave2_featured_{variant}_o1"]
    attempts = [
        _attempt("run_wave2_featured_preview", "preview", "completed", logical_output_key=keys[0], codec="webp", quality=70),
        _attempt("run_wave2_featured_original_old", "original", "completed", logical_output_key=keys[1]),
        _attempt("run_wave2_featured_original_new", "original", "completed", logical_output_key=keys[1]),
    ]
    outputs = [
        _output(keys[0], original_asset_ids=[f"{keys[0]}_orig"], attempt_ids=[attempts[0]["run_id"]]),
        _output(
            keys[1],
            original_asset_ids=[f"{keys[1]}_old_orig", f"{keys[1]}_new_orig"],
            attempt_ids=[attempt["run_id"] for attempt in attempts],
        ),
    ]
    for index, output in enumerate(outputs):
        output["index"] = index
    if variant == "thumbnail":
        featured_index, featured_asset = 0, outputs[0]["thumb_url"].rsplit("/", 1)[-1]
    elif variant == "preview":
        featured_index, featured_asset = 1, outputs[1]["preview_url"].rsplit("/", 1)[-1]
    elif variant == "older_original":
        featured_index, featured_asset = 1, f"{keys[1]}_old_orig"
    else:
        raise ValueError(f"unknown featured variant: {variant}")
    return _generation(
        f"gen_phase_e_wave2_featured_{variant}",
        attempts,
        outputs,
        featured_output_index=featured_index,
        featured_asset_id=featured_asset,
    )


def remote_original_only_generation() -> dict[str, Any]:
    key = "gen_wave2_remote_only_o0"
    attempt = _attempt("run_wave2_remote_original", "original", "completed", logical_output_key=key)
    return _generation(
        "gen_phase_e_wave2_remote_only",
        [attempt],
        [_output(
            key,
            thumb=False,
            preview=False,
            original_asset_ids=["gen_wave2_remote_only_orig"],
            attempt_ids=[attempt["run_id"]],
        )],
    )


def replay_complete_snapshot() -> dict[str, Any]:
    return {
        "workflow_json": {"3": {"class_type": "KSampler", "inputs": {"seed": 42}}},
        "workflow_hash": "a" * 64,
        "request_json": {"prompt": "immutable phase e request", "seed": 42},
        "execution_plan_json": {
            "workflow": {"3": {"class_type": "KSampler", "inputs": {"seed": 42}}},
            "workflow_hash": "a" * 64,
            "source_workflow_hash": "b" * 64,
            "execution_options": {"output_conversion_options": {"format": "original", "quality": None}},
        },
        "deployment_identity_json": {"app": "phase-e-test", "revision": "frozen"},
    }


def replay_experiment_cell_snapshot() -> dict[str, Any]:
    return {
        "generation_id": "gen_phase_e_wave2_cell_0",
        "experiment_id": "exp_phase_e_wave2",
        "cell_id": "cell_0",
        "request_snapshot": replay_complete_snapshot(),
    }


def missing_raw_hash_snapshot() -> dict[str, Any]:
    snapshot = replay_complete_snapshot()
    snapshot["execution_plan_json"] = deepcopy(snapshot["execution_plan_json"])
    snapshot["execution_plan_json"]["workflow_hash"] = ""
    return snapshot


def irreproducible_snapshot() -> dict[str, Any]:
    snapshot = replay_complete_snapshot()
    snapshot["request_json"] = {}
    snapshot["execution_plan_json"] = {}
    snapshot["deployment_identity_json"] = {}
    return snapshot


def output_intent_only_delta(snapshot: dict[str, Any]) -> dict[str, Any]:
    replay = deepcopy(snapshot)
    options = replay["execution_plan_json"]["execution_options"]["output_conversion_options"]
    options.update({"format": "webp_lossy", "quality": 70})
    return replay


def generate_original_placeholder_response(*, reused: bool = False) -> dict[str, Any]:
    return {
        "status": "ok",
        "generation_id": "gen_phase_e_wave2_logical",
        "run_id": "run_phase_e_wave2_original",
        "purpose": "original",
        "mode": "original",
        "attempt_status": "queued",
        "reused": reused,
    }
