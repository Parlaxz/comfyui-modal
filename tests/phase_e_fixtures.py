"""Pure Phase-E wire-contract fixtures.

These builders describe the expected History V2 API shapes. They do not create
or mutate a History repository and deliberately keep remote producer URIs out
of browser-facing payloads.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any


HISTORY_ASSET_PREFIX = "/comfymodal/history-v2/assets/"
REMOTE_ORIGIN = "modal://phase-e/fake/gen_phase_e_remote_original_o0_orig"
PREVIEW_DEFAULTS = {"enabled": False, "codec": "webp", "quality": 70}
GLOBAL_CONCURRENCY = 6


def _attempt(
    run_id: str,
    mode: str,
    status: str,
    *,
    error: str | None = None,
) -> dict[str, Any]:
    terminal = status in {"completed", "failed", "canceled", "interrupted"}
    return {
        "run_id": run_id,
        "mode": mode,
        "status": status,
        "started_at": "2026-08-10T12:00:00.000Z",
        "finished_at": "2026-08-10T12:00:01.000Z" if terminal else None,
        "duration_ms": 1000 if terminal else None,
        "error": error,
        "timing": {"end_to_end_total_ms": 1000} if status == "completed" else None,
    }


def _output(
    generation_id: str,
    *,
    preview: bool = False,
    original: bool = False,
    original_failed: bool = False,
) -> dict[str, Any]:
    base = f"{HISTORY_ASSET_PREFIX}{generation_id}"
    preview_url = f"{base}/preview"
    original_url = f"{base}/original" if original else ""
    return {
        "index": 0,
        "asset_id": f"{generation_id}_original" if original else f"{generation_id}_preview",
        "thumb_url": f"{base}/thumbnail",
        "preview_url": preview_url if preview else "",
        "original_url": original_url,
        "original_failed": original_failed,
        "status": "success",
    }


def _generation(
    generation_id: str,
    attempts: list[dict[str, Any]],
    output: dict[str, Any] | None,
    *,
    status: str = "completed",
    params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    outputs = [] if output is None else [output]
    return {
        "id": generation_id,
        "kind": "generation",
        "status": status,
        "workflow_id": "wf_phase_e",
        "workflow_name": "Phase E Workflow",
        "workflow_version": "wv_phase_e",
        "preset_id": "preset_phase_e",
        "preset": "Phase E Preset",
        "preset_name": "Phase E Preset",
        "prompt": "phase e contract fixture",
        "negative_prompt": "",
        "created_at": "2026-08-10T12:00:00.000Z",
        "started_at": "2026-08-10T12:00:00.000Z",
        "completed_at": "2026-08-10T12:00:01.000Z" if status == "completed" else None,
        "duration_ms": 1000 if status == "completed" else None,
        "favorite": False,
        "note": "",
        "tags": [],
        "models": [],
        "output_count": len(outputs),
        "has_image": bool(outputs),
        "preview_only": bool(outputs and outputs[0]["preview_url"] and not outputs[0]["original_url"]),
        "original_available": bool(outputs and outputs[0]["original_url"]),
        "featured_output_index": 0,
        "outputs": outputs,
        "attempts": attempts,
        "errors": [
            {"code": "attempt_failed", "message": attempt["error"]}
            for attempt in attempts
            if attempt.get("error")
        ],
        "export_state": "none",
        "params": {} if params is None else params,
        "timing": next(
            (attempt.get("timing") for attempt in reversed(attempts) if attempt.get("timing")),
            None,
        ),
        "workflow_json": None,
    }


def preview_only_generation() -> dict[str, Any]:
    generation_id = "gen_phase_e_preview_only"
    return _generation(
        generation_id,
        [_attempt("run_phase_e_preview", "preview", "completed")],
        _output(generation_id, preview=True),
        params={},
    )


def preview_failed_original_generation() -> dict[str, Any]:
    generation_id = "gen_phase_e_preview_failed_original"
    return _generation(
        generation_id,
        [
            _attempt("run_phase_e_preview", "preview", "completed"),
            _attempt("run_phase_e_original", "original", "failed", error="Original replay failed"),
        ],
        _output(generation_id, preview=True, original_failed=True),
        params={},
    )


def preview_successful_original_generation() -> dict[str, Any]:
    generation_id = "gen_phase_e_preview_original"
    return _generation(
        generation_id,
        [
            _attempt("run_phase_e_preview", "preview", "completed"),
            _attempt("run_phase_e_original", "original", "completed"),
        ],
        _output(generation_id, preview=True, original=True),
    )


def original_rerender_failed_generation() -> dict[str, Any]:
    generation_id = "gen_phase_e_rerender_failed"
    return _generation(
        generation_id,
        [
            _attempt("run_phase_e_preview", "preview", "completed"),
            _attempt("run_phase_e_original", "original", "completed"),
            _attempt("run_phase_e_rerender", "original", "failed", error="Rerender timed out"),
        ],
        _output(generation_id, preview=True, original=True),
    )


def remote_original_generation() -> dict[str, Any]:
    generation_id = "gen_phase_e_remote_original"
    return _generation(
        generation_id,
        [_attempt("run_phase_e_remote_original", "original", "completed")],
        _output(generation_id, original=True),
    )


def sparse_generation(status: str = "failed") -> dict[str, Any]:
    return _generation(
        "gen_phase_e_sparse",
        [_attempt("run_phase_e_sparse", "original", status, error="sparse fixture failure" if status == "failed" else None)],
        None,
        status=status,
        params={},
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
            "execution_options": {"output_conversion_options": {"format": "original"}},
        },
        "deployment_identity_json": {"app": "phase-e-test", "revision": "frozen"},
    }


def irreproducible_snapshot() -> dict[str, Any]:
    snapshot = replay_complete_snapshot()
    snapshot["request_json"] = {}
    snapshot["execution_plan_json"] = {}
    snapshot["deployment_identity_json"] = {}
    return snapshot


def modern_experiment_definition() -> dict[str, Any]:
    return {
        "name": "Phase E Preview Sweep",
        "feature_id": "txt2img",
        "axis_labels": {"x": "seed", "y": "steps"},
        "axes": {
            "seed": {"enabled": True, "values": [111, 222]},
            "steps": {"enabled": True, "values": [20]},
        },
        "defaults": {"seed": 111, "steps": 20},
        "modal_options": deepcopy(PREVIEW_DEFAULTS) | {"enabled": True},
        "workflows": [
            {
                "workflow_id": "wf_phase_e",
                "workflow_version_id": "wv_phase_e",
                "preset_id": "preset_phase_e",
                "workflow_name": "Phase E Workflow",
                "preset_name": "Phase E Preset",
            }
        ],
    }


def generate_original_placeholder_response(*, reused: bool = False) -> dict[str, Any]:
    return {
        "status": "ok",
        "generation_id": "gen_phase_e_preview_only",
        "run_id": "run_phase_e_original",
        "purpose": "original",
        "mode": "original",
        "attempt_status": "queued",
        "reused": reused,
    }
