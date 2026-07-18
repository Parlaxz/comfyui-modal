"""wall_clock_trace_v3 — Honest end-to-end wall-clock tracing for ComfyUI x Modal.

Trace version ``3.0.0``.

Purpose
-------
Provide a single source of truth for button-to-image wall time so that
optimisations cannot claim wins by moving work inside restore/warmup without
reducing the total user-visible timer.

Every generation produces a ``wall_clock_trace`` dict attached to the returned
result under a stable key.  The dict includes epoch-second stages, derived
deltas, critical-path attribution, per-model actual-load metrics, warmup
relocation attribution, and data-quality warnings.

Design
------
- Timestamps are ``time.time()`` (unix seconds, cross-process comparable).
- Monotonic clocks (``time.perf_counter``) are used only for local deltas
  inside the same process and are NEVER mixed across processes.
- Negative deltas are recorded under ``data_quality.invalid_deltas`` and
  produce a warning rather than being silently discarded.
- The trace distinguishes *work performed* from *critical-path wall time*.
  Background load overlap is NOT counted as sequential wall time.
"""

import json
import os
import time
import uuid
from typing import Any

TRACE_VERSION = "3.1.0"
PROFILE_VERSION = "4.0.0"

# ── Profile level ──────────────────────────────────────────────────────────
_VALID_LEVELS = ("off", "summary", "detailed", "trace", "trace_verbose")
_PROFILE_CONFIG_PATH = os.path.join(os.path.dirname(__file__), ".profile_config.json")


def _load_profile_level() -> str:
    level = os.environ.get("COMFYMODAL_PROFILE_LEVEL", "").strip().lower()
    if level in _VALID_LEVELS:
        return level
    try:
        with open(_PROFILE_CONFIG_PATH, "r") as _f:
            cfg = json.loads(_f.read())
        level = (cfg.get("level") or "").strip().lower()
        if level in _VALID_LEVELS:
            return level
    except Exception:
        pass
    return "summary"


_PROFILE_LEVEL = _load_profile_level()


def get_profile_level() -> str:
    return _PROFILE_LEVEL


def set_profile_level(level: str) -> None:
    global _PROFILE_LEVEL
    level = level.strip().lower()
    if level in _VALID_LEVELS:
        _PROFILE_LEVEL = level


def profile_enabled(level: str = "summary") -> bool:
    if _PROFILE_LEVEL == "off":
        return False
    order = {"off": 0, "summary": 1, "detailed": 2, "trace": 3, "trace_verbose": 4}
    return order.get(_PROFILE_LEVEL, 0) >= order.get(level, 1)


CLOCK_MODEL_V4 = {
    "version": PROFILE_VERSION,
    "wall_clock": "time.time_ns",
    "monotonic_clock": "time.perf_counter_ns",
    "cross_process_delta_clock": "wall_unix_ns",
    "same_process_delta_clock": "mono_ns",
    "notes": [
        "Never subtract mono_ns across processes.",
        "Cross-machine wall time can include clock skew.",
        "Modal/local clock skew is estimated when possible.",
    ],
}


def _generate_trace_id() -> str:
    return uuid.uuid4().hex[:16]


def _safe_delta_ms(a: float | None, b: float | None, label: str = "") -> float | None:
    """Return ``(b - a) * 1000`` or ``None`` if either is missing."""
    if a is None or b is None:
        return None
    return round((b - a) * 1000, 2)


def _round_ms(seconds: float) -> float:
    return round(seconds * 1000, 2)


# ── Stage key definitions ──────────────────────────────────────────────────
# Local/client side
STAGE_CLIENT_PRESS = "t0_client_press"
STAGE_LOCAL_NODE_START = "t0a_local_node_start"
STAGE_LOCAL_BRIDGE_RECEIVED = "t1_local_bridge_received"
STAGE_LOCAL_PAYLOAD_PARSE_START = "t1a_local_payload_parse_start"
STAGE_LOCAL_PAYLOAD_PARSE_END = "t1b_local_payload_parse_end"
STAGE_LOCAL_PREFLIGHT_START = "t1c_local_preflight_start"
STAGE_LOCAL_PREFLIGHT_END = "t1d_local_preflight_end"
STAGE_ACTIVE_PROFILE_WRITE_START = "t1e_active_profile_write_start"
STAGE_ACTIVE_PROFILE_WRITE_END = "t1f_active_profile_write_end"

# ── New: detailed local pre-dispatch stages ───────────────────────────
STAGE_BODY_READ_START = "t1g_body_read_start"
STAGE_BODY_READ_END = "t1h_body_read_end"
STAGE_JSON_PARSE_START = "t1i_json_parse_start"
STAGE_JSON_PARSE_END = "t1j_json_parse_end"
STAGE_PAYLOAD_NORMALIZE_START = "t1k_payload_normalize_start"
STAGE_PAYLOAD_NORMALIZE_END = "t1l_payload_normalize_end"
STAGE_TRACE_STRIP_START = "t1m_trace_strip_start"
STAGE_TRACE_STRIP_END = "t1n_trace_strip_end"
STAGE_PROMPT_EXTRACT_START = "t1o_prompt_extract_start"
STAGE_PROMPT_EXTRACT_END = "t1p_prompt_extract_end"
STAGE_STACK_EXTRACT_START = "t1q_stack_extract_start"
STAGE_STACK_EXTRACT_END = "t1r_stack_extract_end"
STAGE_INPUT_COLLECT_START = "t1s_input_collect_start"
STAGE_INPUT_COLLECT_END = "t1t_input_collect_end"
STAGE_LOCAL_PREFLIGHT_START = "t1u_local_preflight_start"
STAGE_LOCAL_PREFLIGHT_END = "t1v_local_preflight_end"
STAGE_ACTIVE_NEXT_WRITE_START = "t1w_active_next_write_start"
STAGE_ACTIVE_NEXT_WRITE_END = "t1x_active_next_write_end"
STAGE_MODAL_HANDLE_RESOLVE_START = "t1y_modal_handle_resolve_start"
STAGE_MODAL_HANDLE_RESOLVE_END = "t1z_modal_handle_resolve_end"
STAGE_MODAL_CALL_CONSTRUCT_START = "t1aa_modal_call_construct_start"
STAGE_MODAL_CALL_CONSTRUCT_END = "t1ab_modal_call_construct_end"
STAGE_DEEPCOPY_START = "t1ac_deepcopy_start"
STAGE_DEEPCOPY_END = "t1ad_deepcopy_end"
STAGE_PROFILE_WRITE_VOLUME_START = "t1ae_profile_write_volume_start"
STAGE_PROFILE_WRITE_VOLUME_END = "t1af_profile_write_volume_end"
STAGE_LOCAL_PROMPT_ACK_RETURNED = "t2d_local_prompt_ack_returned"

STAGE_LOCAL_MODAL_SUBMIT_START = "t2_local_modal_submit_start"
STAGE_LOCAL_MODAL_CALL_CONSTRUCTED = "t2a_modal_call_constructed"
STAGE_LOCAL_MODAL_SUBMIT_RETURNED = "t2b_local_modal_submit_returned_or_stream_open"
STAGE_LOCAL_FIRST_REMOTE_EVENT_RECEIVED = "t2c_first_remote_event_received"
STAGE_LOCAL_BRIDGE_RESPONSE_RECEIVED = "t9_local_bridge_response_received"
STAGE_LOCAL_RESULT_DESERIALIZE_START = "t9a_local_result_deserialize_start"
STAGE_LOCAL_RESULT_DESERIALIZE_END = "t9b_local_result_deserialize_end"
STAGE_LOCAL_BASE64_DECODE_START = "t9c_local_base64_decode_start"
STAGE_LOCAL_BASE64_DECODE_END = "t9d_local_base64_decode_end"
STAGE_LOCAL_FILE_WRITE_START = "t9e_local_file_write_start"
STAGE_LOCAL_FILE_WRITE_END = "t9f_local_file_write_end"
STAGE_LOCAL_MATERIALIZED = "t10_local_materialized"
STAGE_LOCAL_RESPONSE_TO_COMFY_START = "t10a_local_response_to_comfy_start"
STAGE_LOCAL_RESPONSE_TO_COMFY_END = "t10b_local_response_to_comfy_end"
STAGE_LOCAL_UI_DONE = "t11_local_ui_done"

# Remote/Modal side
STAGE_MODAL_ENTRY = "t3_modal_entry"
STAGE_REMOTE_PAYLOAD_PARSE_START = "t3a1_remote_payload_parse_start"
STAGE_REMOTE_PAYLOAD_PARSE_END = "t3a2_remote_payload_parse_end"
STAGE_REMOTE_PREFLIGHT_START = "t3a_remote_preflight_start"
STAGE_REMOTE_PREFLIGHT_DONE = "t3b_remote_preflight_done"
STAGE_REMOTE_CUSTOM_NODE_SYNC_START = "t3c1_custom_node_sync_start"
STAGE_REMOTE_CUSTOM_NODE_SYNC_END = "t3c2_custom_node_sync_end"
STAGE_REMOTE_DEPENDENCY_VALIDATION_START = "t3c3_dep_validation_start"
STAGE_REMOTE_DEPENDENCY_VALIDATION_END = "t3c4_dep_validation_end"
STAGE_REMOTE_ACTIVE_PROFILE_READ_START = "t3c5_active_profile_read_start"
STAGE_REMOTE_ACTIVE_PROFILE_READ_END = "t3c6_active_profile_read_end"
STAGE_REMOTE_PREP_DONE = "t3c_remote_prep_done"
STAGE_REMOTE_PREDISPATCH_DONE = "t3k_predispatch_done"
STAGE_RESTORE_START = "t_restore_start"
STAGE_RESTORE_END = "t_restore_end"
STAGE_PROMPT_START = "t_prompt_start"
STAGE_ACTUAL_LOAD_SUBMIT_START = "t4a_actual_load_submit_start"
STAGE_ACTUAL_LOAD_SUBMIT_END = "t4b_actual_load_submit_end"
STAGE_COMFY_VALIDATE_START = "t4c_comfy_validate_start"
STAGE_COMFY_VALIDATE_END = "t4d_comfy_validate_end"
STAGE_GRAPH_EXECUTION_START = "t4e_graph_execution_start"
STAGE_SAMPLER_START = "t_sampler_start"
STAGE_SAMPLER_END = "t_sampler_end"
STAGE_VAE_DECODE_START = "t6a_vae_decode_start"
STAGE_VAE_DECODE_END = "t6b_vae_decode_end"
STAGE_OUTPUTS_COLLECTION_START = "t_outputs_collection_start"
STAGE_HISTORY_FETCH_START = "t7a_history_fetch_start"
STAGE_HISTORY_FETCH_END = "t7b_history_fetch_end"
STAGE_OUTPUT_FILE_SCAN_START = "t7c_output_file_scan_start"
STAGE_OUTPUT_FILE_SCAN_END = "t7d_output_file_scan_end"
STAGE_OUTPUT_FILE_READ_START = "t7e_output_file_read_start"
STAGE_OUTPUT_FILE_READ_END = "t7f_output_file_read_end"
STAGE_IMAGE_CONVERT_START = "t7g_image_convert_start"
STAGE_IMAGE_CONVERT_END = "t7h_image_convert_end"
STAGE_OUTPUTS_COLLECTED = "t_outputs_collected"
STAGE_RESULT_ENRICH_START = "t8a_result_enrich_start"
STAGE_RESULT_ENRICH_END = "t8b_result_enrich_end"
STAGE_RETURN_PACKAGING_START = "t8c_return_packaging_start"
STAGE_RETURN_PACKAGING_END = "t8d_return_packaging_end"
STAGE_REMOTE_RETURN_START = "t_remote_return_start"
STAGE_REMOTE_RETURN_DONE = "t_remote_return_done"

# Legacy aliases (used in existing timing_trace)
_LEGACY_TO_V3 = {
    "t0_client_press": STAGE_CLIENT_PRESS,
    "t0a_local_node_start": STAGE_LOCAL_NODE_START,
    "t1_local_recv": STAGE_LOCAL_BRIDGE_RECEIVED,
    "t1a_local_payload_parse_start": STAGE_LOCAL_PAYLOAD_PARSE_START,
    "t1b_local_payload_parse_end": STAGE_LOCAL_PAYLOAD_PARSE_END,
    "t1c_local_preflight_start": STAGE_LOCAL_PREFLIGHT_START,
    "t1d_local_preflight_end": STAGE_LOCAL_PREFLIGHT_END,
    "t1e_active_profile_write_start": STAGE_ACTIVE_PROFILE_WRITE_START,
    "t1f_active_profile_write_end": STAGE_ACTIVE_PROFILE_WRITE_END,
    # New detailed pre-dispatch aliases
    "t1g_body_read_start": STAGE_BODY_READ_START,
    "t1h_body_read_end": STAGE_BODY_READ_END,
    "t1i_json_parse_start": STAGE_JSON_PARSE_START,
    "t1j_json_parse_end": STAGE_JSON_PARSE_END,
    "t1k_payload_normalize_start": STAGE_PAYLOAD_NORMALIZE_START,
    "t1l_payload_normalize_end": STAGE_PAYLOAD_NORMALIZE_END,
    "t1m_trace_strip_start": STAGE_TRACE_STRIP_START,
    "t1n_trace_strip_end": STAGE_TRACE_STRIP_END,
    "t1o_prompt_extract_start": STAGE_PROMPT_EXTRACT_START,
    "t1p_prompt_extract_end": STAGE_PROMPT_EXTRACT_END,
    "t1q_stack_extract_start": STAGE_STACK_EXTRACT_START,
    "t1r_stack_extract_end": STAGE_STACK_EXTRACT_END,
    "before_stack_extract": STAGE_STACK_EXTRACT_START,
    "after_stack_extract": STAGE_STACK_EXTRACT_END,
    "before_active_next_write": STAGE_ACTIVE_NEXT_WRITE_START,
    "after_active_next_write": STAGE_ACTIVE_NEXT_WRITE_END,
    "before_gpu_spawn": STAGE_LOCAL_MODAL_SUBMIT_START,
    "first_gpu_response": STAGE_LOCAL_FIRST_REMOTE_EVENT_RECEIVED,
    "t1s_input_collect_start": STAGE_INPUT_COLLECT_START,
    "t1t_input_collect_end": STAGE_INPUT_COLLECT_END,
    "t1u_local_preflight_start": STAGE_LOCAL_PREFLIGHT_START,
    "t1v_local_preflight_end": STAGE_LOCAL_PREFLIGHT_END,
    "t1w_active_next_write_start": STAGE_ACTIVE_NEXT_WRITE_START,
    "t1x_active_next_write_end": STAGE_ACTIVE_NEXT_WRITE_END,
    "t1y_modal_handle_resolve_start": STAGE_MODAL_HANDLE_RESOLVE_START,
    "t1z_modal_handle_resolve_end": STAGE_MODAL_HANDLE_RESOLVE_END,
    "t1aa_modal_call_construct_start": STAGE_MODAL_CALL_CONSTRUCT_START,
    "t1ab_modal_call_construct_end": STAGE_MODAL_CALL_CONSTRUCT_END,
    "t1ac_deepcopy_start": STAGE_DEEPCOPY_START,
    "t1ad_deepcopy_end": STAGE_DEEPCOPY_END,
    "t1ae_profile_write_volume_start": STAGE_PROFILE_WRITE_VOLUME_START,
    "t1af_profile_write_volume_end": STAGE_PROFILE_WRITE_VOLUME_END,
    "t2d_local_prompt_ack_returned": STAGE_LOCAL_PROMPT_ACK_RETURNED,
    "t2_local_dispatch": STAGE_LOCAL_MODAL_SUBMIT_START,
    "t2a_modal_call_constructed": STAGE_LOCAL_MODAL_CALL_CONSTRUCTED,
    "t2b_modal_handle_resolved": STAGE_LOCAL_MODAL_SUBMIT_RETURNED,
    "t2c_modal_call_start": STAGE_LOCAL_MODAL_SUBMIT_RETURNED,
    "t2c_first_remote_event_received": STAGE_LOCAL_FIRST_REMOTE_EVENT_RECEIVED,
    "t3_modal_entry": STAGE_MODAL_ENTRY,
    "t3a1_remote_payload_parse_start": STAGE_REMOTE_PAYLOAD_PARSE_START,
    "t3a2_remote_payload_parse_end": STAGE_REMOTE_PAYLOAD_PARSE_END,
    "t3b_validate_done": STAGE_REMOTE_PREFLIGHT_DONE,
    "t3c1_custom_node_sync_start": STAGE_REMOTE_CUSTOM_NODE_SYNC_START,
    "t3c2_custom_node_sync_end": STAGE_REMOTE_CUSTOM_NODE_SYNC_END,
    "t3c3_dep_validation_start": STAGE_REMOTE_DEPENDENCY_VALIDATION_START,
    "t3c4_dep_validation_end": STAGE_REMOTE_DEPENDENCY_VALIDATION_END,
    "t3c5_active_profile_read_start": STAGE_REMOTE_ACTIVE_PROFILE_READ_START,
    "t3c6_active_profile_read_end": STAGE_REMOTE_ACTIVE_PROFILE_READ_END,
    "t3c_prep_done": STAGE_REMOTE_PREP_DONE,
    "t3k_predispatch_done": STAGE_REMOTE_PREDISPATCH_DONE,
    "t3d_prompt_start": STAGE_PROMPT_START,
    "t4a_actual_load_submit_start": STAGE_ACTUAL_LOAD_SUBMIT_START,
    "t4b_actual_load_submit_end": STAGE_ACTUAL_LOAD_SUBMIT_END,
    "t4c_comfy_validate_start": STAGE_COMFY_VALIDATE_START,
    "t4d_comfy_validate_end": STAGE_COMFY_VALIDATE_END,
    "t4e_graph_execution_start": STAGE_GRAPH_EXECUTION_START,
    "t6_sampler_start": STAGE_SAMPLER_START,
    "t6_sampler_end": STAGE_SAMPLER_END,
    "t6a_vae_decode_start": STAGE_VAE_DECODE_START,
    "t6b_vae_decode_end": STAGE_VAE_DECODE_END,
    "t7b_collect_start": STAGE_OUTPUTS_COLLECTION_START,
    "t7a_history_fetch_start": STAGE_HISTORY_FETCH_START,
    "t7b_history_fetch_end": STAGE_HISTORY_FETCH_END,
    "t7c_output_file_scan_start": STAGE_OUTPUT_FILE_SCAN_START,
    "t7d_output_file_scan_end": STAGE_OUTPUT_FILE_SCAN_END,
    "t7e_output_file_read_start": STAGE_OUTPUT_FILE_READ_START,
    "t7f_output_file_read_end": STAGE_OUTPUT_FILE_READ_END,
    "t7g_image_convert_start": STAGE_IMAGE_CONVERT_START,
    "t7h_image_convert_end": STAGE_IMAGE_CONVERT_END,
    "t8b_outputs_collected": STAGE_OUTPUTS_COLLECTED,
    "t8a_result_enrich_start": STAGE_RESULT_ENRICH_START,
    "t8b_result_enrich_end": STAGE_RESULT_ENRICH_END,
    "t8c_return_packaging_start": STAGE_RETURN_PACKAGING_START,
    "t8d_return_packaging_end": STAGE_RETURN_PACKAGING_END,
    "t_remote_return_start": STAGE_REMOTE_RETURN_START,
    "t9_modal_return": STAGE_REMOTE_RETURN_DONE,
    "t9a_local_result_deserialize_start": STAGE_LOCAL_RESULT_DESERIALIZE_START,
    "t9b_local_result_deserialize_end": STAGE_LOCAL_RESULT_DESERIALIZE_END,
    "t9c_local_base64_decode_start": STAGE_LOCAL_BASE64_DECODE_START,
    "t9d_local_base64_decode_end": STAGE_LOCAL_BASE64_DECODE_END,
    "t9e_local_file_write_start": STAGE_LOCAL_FILE_WRITE_START,
    "t9f_local_file_write_end": STAGE_LOCAL_FILE_WRITE_END,
    "t9b_local_result_received": STAGE_LOCAL_BRIDGE_RESPONSE_RECEIVED,
    "t10_local_materialized": STAGE_LOCAL_MATERIALIZED,
    "t10a_local_response_to_comfy_start": STAGE_LOCAL_RESPONSE_TO_COMFY_START,
    "t10b_local_response_to_comfy_end": STAGE_LOCAL_RESPONSE_TO_COMFY_END,
    "t10b_local_save_start": "t10b_local_save_start",
    "t11_local_ui_done": STAGE_LOCAL_UI_DONE,
}


def _resolve_aliases(stages: dict[str, float]) -> dict[str, float]:
    """Map legacy stage names to v3 names when v3 name is absent."""
    out = dict(stages)
    for legacy, v3 in _LEGACY_TO_V3.items():
        if v3 not in out and legacy in out and out[legacy] is not None:
            out[v3] = out[legacy]
    return out


# ── Build the wall-clock trace ─────────────────────────────────────────────


def build_wall_clock_trace(
    trace_id: str | None = None,
    client_stages: dict[str, float] | None = None,
    remote_stages: dict[str, float] | None = None,
    restore_timing: dict[str, Any] | None = None,
    execution_timing: dict[str, Any] | None = None,
    output_timing: dict[str, Any] | None = None,
    actual_load_per_model: list[dict] | None = None,
    preload_stall_info: dict[str, Any] | None = None,
    warmup_info: dict[str, Any] | None = None,
    request_seq: int = 0,
    container_session_id: str = "",
    restore_session_id: str = "",
    container_import_unix_s: float = 0.0,
    restore_count: int = 0,
) -> dict[str, Any]:
    """Build a complete ``wall_clock_trace`` result dict.

    Parameters are the raw inputs; merging and alias resolution happen inside.
    """
    if trace_id is None:
        trace_id = _generate_trace_id()

    merged_stages: dict[str, float] = {}
    if client_stages:
        merged_stages.update(client_stages)
    if remote_stages:
        merged_stages.update(remote_stages)

    merged_stages = _resolve_aliases(merged_stages)

    if restore_timing:
        _rs = restore_timing.get("restore_start_unix_s")
        if _rs is not None and STAGE_RESTORE_START not in merged_stages:
            merged_stages[STAGE_RESTORE_START] = float(_rs)
        _re = restore_timing.get("restore_end_unix_s")
        if _re is not None and STAGE_RESTORE_END not in merged_stages:
            merged_stages[STAGE_RESTORE_END] = float(_re)

    result: dict[str, Any] = {
        "trace_version": TRACE_VERSION,
        "profile_version": PROFILE_VERSION,
        "trace_id": trace_id,
        "clock_domain": "unix_s_time.time",
        "clock_model": CLOCK_MODEL_V4,
        "profile_level": _PROFILE_LEVEL,
        "container_session_id": container_session_id,
        "restore_session_id": restore_session_id,
        "container_import_unix_s": container_import_unix_s,
        "restore_count": restore_count,
        "request_seq": request_seq,
        "stages_unix_s": dict(merged_stages),
        "deltas_ms": {},
        "critical_path": {
            "known_ms": 0.0,
            "unknown_or_unattributed_ms": 0.0,
            "phases": [],
            "submit_to_remote_done_ms": None,
            "local_button_to_materialized_ms": None,
            "remote_visible_ms": None,
            "submit2entry_ms": None,
            "restore_included_in_submit2entry": False,
            "restore_total_ms_info_only": None,
            "known_non_overlapping_ms": None,
            "unexplained_local_wall_ms": None,
            "double_count_guard_applied": True,
            "warnings": [],
            "note": "The sum of internal worker times is NOT wall-clock time. "
                     "known_ms is the non-overlapping critical path estimate.",
        },
        "attribution": {},
        "data_quality": {
            "missing_stages": [],
            "invalid_deltas": [],
            "clock_domain_notes": "All timestamps use time.time() (unix seconds). "
                                   "Monotonic clocks are never mixed between processes.",
            "warnings": [],
        },
        "warnings": [],
        "warmup_relocation": {
            "restore_preload_ms": 0.0,
            "direct_clip_load_ms": 0.0,
            "direct_clip_encode_ms": 0.0,
            "prompt_clip_load_ms": 0.0,
            "prompt_clip_encode_ms": 0.0,
            "relocated_work_ms_estimate": 0.0,
            "net_wall_time_claim_allowed": False,
        },
        "actual_load_summary": {
            "enabled": False,
            "models_started": 0,
            "models_ready_before_graph": 0,
            "models_waited_by_graph": 0,
            "total_background_work_ms": 0.0,
            "estimated_critical_path_saved_ms": 0.0,
            "remaining_graph_wait_ms": 0.0,
            "duplicate_reads_prevented": 0,
            "per_model": [],
        },
        "post_sampler_summary": {
            "sampler_end_to_outputs_collected_ms": 0.0,
            "vae_decode_ms": 0.0,
            "output_collection_total_ms": 0.0,
            "image_conversion_total_ms": 0.0,
            "file_read_total_ms": 0.0,
            "return_packaging_ms": 0.0,
            "unattributed_post_sampler_ms": 0.0,
        },
        "preload_stall_summary": {},
    }

    # ── Compute deltas ──────────────────────────────────────────────────
    deltas = _compute_deltas(merged_stages, result["data_quality"])
    result["deltas_ms"] = deltas

    # ── Critical path ────────────────────────────────────────────────────
    result["critical_path"] = _build_critical_path(merged_stages, deltas, result["data_quality"])

    # ── Warmup relocation ────────────────────────────────────────────────
    if warmup_info:
        result["warmup_relocation"].update(_build_warmup_relocation(warmup_info))

    # ── Actual-load per-model records ────────────────────────────────────
    if actual_load_per_model:
        al_summary = _build_actual_load_summary(actual_load_per_model)
        result["actual_load_summary"].update(al_summary)
        result["actual_load_summary"]["per_model"] = actual_load_per_model

    # ── Preload stall ────────────────────────────────────────────────────
    if preload_stall_info:
        result["preload_stall_summary"] = dict(preload_stall_info)
        if preload_stall_info.get("preload_failed"):
            result["warnings"].append(
                "restore preload failed; this run is degraded and must not be "
                "used as proof of normal performance"
            )
            result["data_quality"]["warnings"].append(
                "restore preload failed; degraded run"
            )

    # ── Post-sampler attribution ─────────────────────────────────────────
    if output_timing:
        result["post_sampler_summary"] = _build_post_sampler_summary(
            merged_stages, deltas, output_timing
        )

    # ── Missing local timestamps warning ─────────────────────────────────
    _check_missing_local_stages(merged_stages, result["data_quality"], result["warnings"])

    # ── No-baseline warning ──────────────────────────────────────────────
    result["warnings"].append(
        "no baseline comparison was performed; wall-time win claims require "
        "a measured baseline"
    )

    return result


# ── Delta computation ──────────────────────────────────────────────────────


def _compute_deltas(
    stages: dict[str, float],
    data_quality: dict[str, Any],
) -> dict[str, float]:
    """Compute all derived deltas from stage timestamps.

    Never silently produces negative deltas — those go to invalid_deltas.
    """
    d: dict[str, float] = {}
    invalid: list[dict] = data_quality.get("invalid_deltas", [])
    missing: list[str] = data_quality.get("missing_stages", [])

    _ALLOWED_MISSING = {
        STAGE_CLIENT_PRESS, STAGE_LOCAL_NODE_START, STAGE_LOCAL_BRIDGE_RECEIVED,
        STAGE_LOCAL_PAYLOAD_PARSE_START, STAGE_LOCAL_PAYLOAD_PARSE_END,
        STAGE_LOCAL_PREFLIGHT_START, STAGE_LOCAL_PREFLIGHT_END,
        STAGE_ACTIVE_PROFILE_WRITE_START, STAGE_ACTIVE_PROFILE_WRITE_END,
        # New detailed pre-dispatch stages (optional)
        STAGE_BODY_READ_START, STAGE_BODY_READ_END,
        STAGE_JSON_PARSE_START, STAGE_JSON_PARSE_END,
        STAGE_PAYLOAD_NORMALIZE_START, STAGE_PAYLOAD_NORMALIZE_END,
        STAGE_TRACE_STRIP_START, STAGE_TRACE_STRIP_END,
        STAGE_PROMPT_EXTRACT_START, STAGE_PROMPT_EXTRACT_END,
        STAGE_STACK_EXTRACT_START, STAGE_STACK_EXTRACT_END,
        STAGE_INPUT_COLLECT_START, STAGE_INPUT_COLLECT_END,
        STAGE_LOCAL_PREFLIGHT_START, STAGE_LOCAL_PREFLIGHT_END,
        STAGE_ACTIVE_NEXT_WRITE_START, STAGE_ACTIVE_NEXT_WRITE_END,
        STAGE_MODAL_HANDLE_RESOLVE_START, STAGE_MODAL_HANDLE_RESOLVE_END,
        STAGE_MODAL_CALL_CONSTRUCT_START, STAGE_MODAL_CALL_CONSTRUCT_END,
        STAGE_DEEPCOPY_START, STAGE_DEEPCOPY_END,
        STAGE_PROFILE_WRITE_VOLUME_START, STAGE_PROFILE_WRITE_VOLUME_END,
        STAGE_LOCAL_PROMPT_ACK_RETURNED,
        STAGE_LOCAL_MODAL_SUBMIT_START, STAGE_LOCAL_MODAL_CALL_CONSTRUCTED,
        STAGE_LOCAL_MODAL_SUBMIT_RETURNED, STAGE_LOCAL_FIRST_REMOTE_EVENT_RECEIVED,
        STAGE_LOCAL_BRIDGE_RESPONSE_RECEIVED,
        STAGE_LOCAL_RESULT_DESERIALIZE_START, STAGE_LOCAL_RESULT_DESERIALIZE_END,
        STAGE_LOCAL_BASE64_DECODE_START, STAGE_LOCAL_BASE64_DECODE_END,
        STAGE_LOCAL_FILE_WRITE_START, STAGE_LOCAL_FILE_WRITE_END,
        STAGE_LOCAL_RESPONSE_TO_COMFY_START, STAGE_LOCAL_RESPONSE_TO_COMFY_END,
        STAGE_LOCAL_UI_DONE,
        STAGE_REMOTE_PAYLOAD_PARSE_START, STAGE_REMOTE_PAYLOAD_PARSE_END,
        STAGE_REMOTE_PREFLIGHT_START, STAGE_REMOTE_PREFLIGHT_DONE,
        STAGE_REMOTE_CUSTOM_NODE_SYNC_START, STAGE_REMOTE_CUSTOM_NODE_SYNC_END,
        STAGE_REMOTE_DEPENDENCY_VALIDATION_START, STAGE_REMOTE_DEPENDENCY_VALIDATION_END,
        STAGE_REMOTE_ACTIVE_PROFILE_READ_START, STAGE_REMOTE_ACTIVE_PROFILE_READ_END,
        STAGE_REMOTE_PREP_DONE, STAGE_REMOTE_PREDISPATCH_DONE,
        STAGE_RESTORE_START, STAGE_RESTORE_END,
        STAGE_ACTUAL_LOAD_SUBMIT_START, STAGE_ACTUAL_LOAD_SUBMIT_END,
        STAGE_COMFY_VALIDATE_START, STAGE_COMFY_VALIDATE_END,
        STAGE_GRAPH_EXECUTION_START,
        STAGE_VAE_DECODE_START, STAGE_VAE_DECODE_END,
        STAGE_HISTORY_FETCH_START, STAGE_HISTORY_FETCH_END,
        STAGE_OUTPUT_FILE_SCAN_START, STAGE_OUTPUT_FILE_SCAN_END,
        STAGE_OUTPUT_FILE_READ_START, STAGE_OUTPUT_FILE_READ_END,
        STAGE_IMAGE_CONVERT_START, STAGE_IMAGE_CONVERT_END,
        STAGE_RESULT_ENRICH_START, STAGE_RESULT_ENRICH_END,
        STAGE_RETURN_PACKAGING_START, STAGE_RETURN_PACKAGING_END,
        STAGE_REMOTE_RETURN_START,
    }

    pairs = [
        ("local_button_to_materialized_ms", STAGE_CLIENT_PRESS, STAGE_LOCAL_MATERIALIZED),
        ("local_pre_modal_ms", STAGE_CLIENT_PRESS, STAGE_LOCAL_MODAL_SUBMIT_START),
        ("local_bridge_to_submit_ms", STAGE_LOCAL_BRIDGE_RECEIVED, STAGE_LOCAL_MODAL_SUBMIT_START),
        ("local_preflight_ms", STAGE_LOCAL_PREFLIGHT_START, STAGE_LOCAL_PREFLIGHT_END),
        ("local_active_profile_write_ms", STAGE_ACTIVE_PROFILE_WRITE_START, STAGE_ACTIVE_PROFILE_WRITE_END),
        # New detailed pre-dispatch deltas
        ("body_read_ms", STAGE_BODY_READ_START, STAGE_BODY_READ_END),
        ("json_parse_ms", STAGE_JSON_PARSE_START, STAGE_JSON_PARSE_END),
        ("payload_normalize_ms", STAGE_PAYLOAD_NORMALIZE_START, STAGE_PAYLOAD_NORMALIZE_END),
        ("trace_strip_ms", STAGE_TRACE_STRIP_START, STAGE_TRACE_STRIP_END),
        ("prompt_extract_ms", STAGE_PROMPT_EXTRACT_START, STAGE_PROMPT_EXTRACT_END),
        ("stack_extract_ms", STAGE_STACK_EXTRACT_START, STAGE_STACK_EXTRACT_END),
        ("input_collect_ms", STAGE_INPUT_COLLECT_START, STAGE_INPUT_COLLECT_END),
        ("deepcopy_ms", STAGE_DEEPCOPY_START, STAGE_DEEPCOPY_END),
        ("profile_write_volume_ms", STAGE_PROFILE_WRITE_VOLUME_START, STAGE_PROFILE_WRITE_VOLUME_END),
        ("local_recv_to_body_read_start_ms", STAGE_LOCAL_BRIDGE_RECEIVED, STAGE_BODY_READ_START),
        ("local_recv_to_stack_extract_start_ms", STAGE_LOCAL_BRIDGE_RECEIVED, STAGE_STACK_EXTRACT_START),
        ("local_stack_extract_to_dispatch_ms", STAGE_STACK_EXTRACT_END, STAGE_LOCAL_MODAL_SUBMIT_START),
        ("local_recv_to_dispatch_ms", STAGE_LOCAL_BRIDGE_RECEIVED, STAGE_LOCAL_MODAL_SUBMIT_START),
        ("local_recv_to_ack_returned_ms", STAGE_LOCAL_BRIDGE_RECEIVED, STAGE_LOCAL_PROMPT_ACK_RETURNED),
        ("modal_submit_to_entry_ms", STAGE_LOCAL_MODAL_SUBMIT_START, STAGE_MODAL_ENTRY),
        ("first_remote_event_latency_ms", STAGE_LOCAL_MODAL_SUBMIT_START, STAGE_LOCAL_FIRST_REMOTE_EVENT_RECEIVED),
        ("modal_entry_to_prompt_start_ms", STAGE_MODAL_ENTRY, STAGE_PROMPT_START),
        ("restore_total_ms", STAGE_RESTORE_START, STAGE_RESTORE_END),
        ("restore_end_to_prompt_start_ms", STAGE_RESTORE_END, STAGE_PROMPT_START),
        ("payload_parse_ms", STAGE_REMOTE_PAYLOAD_PARSE_START, STAGE_REMOTE_PAYLOAD_PARSE_END),
        ("custom_node_sync_ms", STAGE_REMOTE_CUSTOM_NODE_SYNC_START, STAGE_REMOTE_CUSTOM_NODE_SYNC_END),
        ("dep_validation_ms", STAGE_REMOTE_DEPENDENCY_VALIDATION_START, STAGE_REMOTE_DEPENDENCY_VALIDATION_END),
        ("active_profile_read_ms", STAGE_REMOTE_ACTIVE_PROFILE_READ_START, STAGE_REMOTE_ACTIVE_PROFILE_READ_END),
        ("prep_to_predispatch_ms", STAGE_REMOTE_PREP_DONE, STAGE_REMOTE_PREDISPATCH_DONE),
        ("predispatch_to_prompt_start_ms", STAGE_REMOTE_PREDISPATCH_DONE, STAGE_PROMPT_START),
        ("actual_load_submit_ms", STAGE_ACTUAL_LOAD_SUBMIT_START, STAGE_ACTUAL_LOAD_SUBMIT_END),
        ("comfy_validate_ms", STAGE_COMFY_VALIDATE_START, STAGE_COMFY_VALIDATE_END),
        ("graph_execution_start_to_sampler_ms", STAGE_GRAPH_EXECUTION_START, STAGE_SAMPLER_START),
        ("prompt_start_to_sampler_start_ms", STAGE_PROMPT_START, STAGE_SAMPLER_START),
        ("sampler_ms", STAGE_SAMPLER_START, STAGE_SAMPLER_END),
        ("vae_decode_ms", STAGE_VAE_DECODE_START, STAGE_VAE_DECODE_END),
        ("sampler_to_vae_decode_ms", STAGE_SAMPLER_END, STAGE_VAE_DECODE_START),
        ("sampler_end_to_outputs_collected_ms", STAGE_SAMPLER_END, STAGE_OUTPUTS_COLLECTED),
        ("vae_decode_to_outputs_collected_ms", STAGE_VAE_DECODE_END, STAGE_OUTPUTS_COLLECTED),
        ("output_collection_total_ms", STAGE_OUTPUTS_COLLECTION_START, STAGE_OUTPUTS_COLLECTED),
        ("history_fetch_ms", STAGE_HISTORY_FETCH_START, STAGE_HISTORY_FETCH_END),
        ("file_scan_ms", STAGE_OUTPUT_FILE_SCAN_START, STAGE_OUTPUT_FILE_SCAN_END),
        ("file_read_total_ms", STAGE_OUTPUT_FILE_READ_START, STAGE_OUTPUT_FILE_READ_END),
        ("image_conversion_total_ms", STAGE_IMAGE_CONVERT_START, STAGE_IMAGE_CONVERT_END),
        ("result_enrich_ms", STAGE_RESULT_ENRICH_START, STAGE_RESULT_ENRICH_END),
        ("return_packaging_ms", STAGE_RETURN_PACKAGING_START, STAGE_RETURN_PACKAGING_END),
        ("remote_return_ms", STAGE_REMOTE_RETURN_START, STAGE_REMOTE_RETURN_DONE),
        ("remote_return_to_local_materialized_ms", STAGE_REMOTE_RETURN_DONE, STAGE_LOCAL_MATERIALIZED),
        ("local_deserialize_ms", STAGE_LOCAL_RESULT_DESERIALIZE_START, STAGE_LOCAL_RESULT_DESERIALIZE_END),
        ("local_base64_decode_ms", STAGE_LOCAL_BASE64_DECODE_START, STAGE_LOCAL_BASE64_DECODE_END),
        ("local_file_write_ms", STAGE_LOCAL_FILE_WRITE_START, STAGE_LOCAL_FILE_WRITE_END),
        ("local_response_to_comfy_ms", STAGE_LOCAL_RESPONSE_TO_COMFY_START, STAGE_LOCAL_RESPONSE_TO_COMFY_END),
        ("remote_total_visible_ms", STAGE_MODAL_ENTRY, STAGE_REMOTE_RETURN_DONE),
        ("modal_to_return_ms", STAGE_MODAL_ENTRY, STAGE_REMOTE_RETURN_DONE),
        ("modal_to_local_ms", STAGE_MODAL_ENTRY, STAGE_LOCAL_MATERIALIZED),
        ("submit_to_remote_done_ms", STAGE_LOCAL_MODAL_SUBMIT_START, STAGE_REMOTE_RETURN_DONE),
        ("remote_entry_to_return_ms", STAGE_MODAL_ENTRY, STAGE_REMOTE_RETURN_DONE),
    ]

    for label, start_key, end_key in pairs:
        sv = stages.get(start_key)
        ev = stages.get(end_key)
        if sv is None and start_key not in _ALLOWED_MISSING:
            if start_key not in missing:
                missing.append(start_key)
        if ev is None and end_key not in _ALLOWED_MISSING:
            if end_key not in missing:
                missing.append(end_key)
        if sv is not None and ev is not None:
            val_ms = (ev - sv) * 1000
            if val_ms < 0:
                invalid.append({
                    "delta_key": label,
                    "start_key": start_key,
                    "end_key": end_key,
                    "start_val": sv,
                    "end_val": ev,
                    "delta_ms": round(val_ms, 2),
                    "note": "negative delta — possible clock skew or out-of-order events",
                })
            else:
                d[label] = round(val_ms, 2)

    data_quality["missing_stages"] = missing
    data_quality["invalid_deltas"] = invalid

    return d


# ── Critical path ──────────────────────────────────────────────────────────


def _build_critical_path(
    stages: dict[str, float],
    deltas: dict[str, float],
    data_quality: dict[str, Any],
) -> dict[str, Any]:
    """Build a non-overlapping critical path from available stages.

    Correctness rule: when ``submit2entry`` (local submit → Modal entry) and
    ``remote_visible`` (Modal entry → remote return) both exist, the known
    non-overlapping wall time is their sum.  Restore is NOT added separately
    because it happens before Modal method entry and is already inside
    ``submit2entry``.  Adding restore separately would double-count.

    When ``submit2entry`` or ``remote_visible`` is missing, fall back to
    individual phases and mark quality as ``fallback/partial``.
    """
    phases: list[dict[str, Any]] = []
    warnings: list[str] = []

    has_submit2entry = (
        STAGE_LOCAL_MODAL_SUBMIT_START in stages and STAGE_MODAL_ENTRY in stages
    )
    has_remote_visible = (
        STAGE_MODAL_ENTRY in stages and STAGE_REMOTE_RETURN_DONE in stages
    )
    has_restore = STAGE_RESTORE_START in stages and STAGE_RESTORE_END in stages
    has_local_materialized = STAGE_LOCAL_MATERIALIZED in stages

    submit2entry_ms = deltas.get("modal_submit_to_entry_ms")
    remote_visible_ms = deltas.get("remote_total_visible_ms")
    restore_total_ms = deltas.get("restore_total_ms")
    local_btn_to_mat_ms = deltas.get("local_button_to_materialized_ms")

    # ── Primary path: submit2entry + remote_visible (non-overlapping) ──
    known_nonoverlap = None
    submit_to_remote_done_ms = None
    restore_included_in_submit2entry = False

    if submit2entry_ms is not None and remote_visible_ms is not None:
        submit_to_remote_done_ms = submit2entry_ms + remote_visible_ms
        known_nonoverlap = submit_to_remote_done_ms

        phases.append({
            "phase": "submit_to_remote_done",
            "start_stage": STAGE_LOCAL_MODAL_SUBMIT_START,
            "end_stage": STAGE_REMOTE_RETURN_DONE,
            "duration_ms": round(submit_to_remote_done_ms, 2),
            "source": "submit2entry_ms + remote_visible_ms",
            "note": "non-overlapping: covers submit → entry + entry → return",
        })

        if has_restore and restore_total_ms is not None:
            restore_included_in_submit2entry = True
            phases.append({
                "phase": "restore_info_only",
                "start_stage": STAGE_RESTORE_START,
                "end_stage": STAGE_RESTORE_END,
                "duration_ms": restore_total_ms,
                "source": "deltas_ms",
                "note": "restore is included in submit2entry; not added to known_nonoverlap",
            })
            warnings.append(
                "Restore is included in submit2entry; not added separately to critical path."
            )

        # Breakdown phases (info-only, not added to known_nonoverlap)
        _add_info_phase(phases, "submit2entry_breakdown", submit2entry_ms, "info-only")
        if remote_visible_ms is not None:
            _add_info_phase(phases, "remote_visible_breakdown", remote_visible_ms, "info-only")

    else:
        # ── Fallback: additive phases ──
        known_nonoverlap_fb: float = 0.0
        fallback_used = True

        def _add(label, start_key, end_key, delta_key=None):
            nonlocal known_nonoverlap_fb
            sv = stages.get(start_key)
            ev = stages.get(end_key)
            if sv is not None and ev is not None:
                ms = max(0.0, (ev - sv) * 1000)
                phases.append({"phase": label, "start_stage": start_key,
                               "end_stage": end_key, "duration_ms": round(ms, 2),
                               "source": "stage_delta"})
                known_nonoverlap_fb += ms
            elif delta_key and delta_key in deltas:
                ms = deltas[delta_key]
                phases.append({"phase": label, "start_stage": start_key,
                               "end_stage": end_key, "duration_ms": ms,
                               "source": "deltas_ms"})
                known_nonoverlap_fb += ms

        _add("local_pre_modal", STAGE_CLIENT_PRESS, STAGE_LOCAL_MODAL_SUBMIT_START,
             delta_key="local_pre_modal_ms")

        if has_submit2entry:
            _add("modal_queue_or_start_gap", STAGE_LOCAL_MODAL_SUBMIT_START,
                 STAGE_MODAL_ENTRY, delta_key="modal_submit_to_entry_ms")

        if has_restore and restore_total_ms is not None:
            phases.append({
                "phase": "restore", "start_stage": STAGE_RESTORE_START,
                "end_stage": STAGE_RESTORE_END, "duration_ms": restore_total_ms,
                "source": "deltas_ms",
                "note": "fallback path: no submit2entry available, restore counted separately",
            })
            known_nonoverlap_fb += restore_total_ms

        if has_restore:
            _add("post_restore_pre_prompt", STAGE_RESTORE_END, STAGE_PROMPT_START,
                 delta_key="restore_end_to_prompt_start_ms")
        else:
            _add("modal_entry_to_prompt_start", STAGE_MODAL_ENTRY, STAGE_PROMPT_START,
                 delta_key="modal_entry_to_prompt_start_ms")

        _add("prompt_pre_sampler", STAGE_PROMPT_START, STAGE_SAMPLER_START,
             delta_key="prompt_start_to_sampler_start_ms")
        _add("sampler", STAGE_SAMPLER_START, STAGE_SAMPLER_END, delta_key="sampler_ms")
        _add("post_sampler", STAGE_SAMPLER_END, STAGE_OUTPUTS_COLLECTED,
             delta_key="sampler_end_to_outputs_collected_ms")
        _add("remote_return_to_local", STAGE_REMOTE_RETURN_DONE, STAGE_LOCAL_MATERIALIZED,
             delta_key="remote_return_to_local_materialized_ms")
        known_nonoverlap = known_nonoverlap_fb

    # ── Unexplained local wall time ──
    unexplained_local_wall_ms = None
    if local_btn_to_mat_ms is not None and known_nonoverlap is not None:
        unexplained_local_wall_ms = max(0.0, local_btn_to_mat_ms - known_nonoverlap)

    # ── Unknown / unattributed ──
    unknown_or_unattributed_ms = 0.0
    if known_nonoverlap is not None and local_btn_to_mat_ms is not None:
        unknown_or_unattributed_ms = max(0.0, local_btn_to_mat_ms - known_nonoverlap)

    # ── Missing local stage warning ──
    if not has_local_materialized:
        warnings.append(
            "t10_local_materialized missing; cannot explain browser/local timer gap"
        )

    return {
        "known_ms": round(known_nonoverlap, 2) if known_nonoverlap is not None else 0.0,
        "unknown_or_unattributed_ms": round(unknown_or_unattributed_ms, 2),
        "phases": phases,
        "submit_to_remote_done_ms": round(submit_to_remote_done_ms, 2) if submit_to_remote_done_ms is not None else None,
        "local_button_to_materialized_ms": local_btn_to_mat_ms,
        "remote_visible_ms": remote_visible_ms,
        "submit2entry_ms": submit2entry_ms,
        "restore_included_in_submit2entry": restore_included_in_submit2entry,
        "restore_total_ms_info_only": restore_total_ms if restore_included_in_submit2entry else None,
        "known_non_overlapping_ms": round(known_nonoverlap, 2) if known_nonoverlap is not None else None,
        "unexplained_local_wall_ms": round(unexplained_local_wall_ms, 2) if unexplained_local_wall_ms is not None else None,
        "double_count_guard_applied": True,
        "warnings": warnings,
        "note": "The sum of internal worker times is NOT wall-clock time. "
                "known_ms is the non-overlapping critical path estimate.",
    }


def _add_info_phase(
    phases: list[dict], label: str, ms: float | None, note: str = ""
) -> None:
    """Add an info-only phase that does NOT contribute to known_ms."""
    if ms is not None:
        phases.append({
            "phase": label,
            "duration_ms": round(ms, 2),
            "source": "info_only",
            "note": note,
        })


# ── Warmup relocation ──────────────────────────────────────────────────────


def _build_warmup_relocation(warmup_info: dict[str, Any]) -> dict[str, Any]:
    """Estimate how much work was moved from prompt into restore/warmup."""
    restore_preload_ms = warmup_info.get("warmup_preload_ms", 0.0) or 0.0
    direct_clip_load_ms = warmup_info.get("warmup_direct_clip_load_ms", 0.0) or 0.0
    direct_clip_encode_ms = warmup_info.get("warmup_direct_clip_encode_ms", 0.0) or 0.0
    prompt_clip_load_ms = warmup_info.get("clip_load_ms", 0.0) or 0.0
    prompt_clip_encode_ms = warmup_info.get("clip_encode_ms", 0.0) or 0.0

    relocated_work_ms = restore_preload_ms + direct_clip_load_ms + direct_clip_encode_ms
    return {
        "restore_preload_ms": round(restore_preload_ms, 2),
        "direct_clip_load_ms": round(direct_clip_load_ms, 2),
        "direct_clip_encode_ms": round(direct_clip_encode_ms, 2),
        "prompt_clip_load_ms": round(prompt_clip_load_ms, 2),
        "prompt_clip_encode_ms": round(prompt_clip_encode_ms, 2),
        "relocated_work_ms_estimate": round(relocated_work_ms, 2),
        "net_wall_time_claim_allowed": False,
        "note": "Lower CLIP prompt time is not a wall-clock win if restore "
                "increased by the same amount. Claim requires end-to-end timer.",
    }


# ── Actual-load per-model records ──────────────────────────────────────────


def make_actual_load_record(
    loader_type: str,
    canonical_key: str,
    actual_load_start_unix_s: float | None = None,
    actual_load_done_unix_s: float | None = None,
    graph_requested_model_unix_s: float | None = None,
    graph_wait_start_unix_s: float | None = None,
    graph_wait_done_unix_s: float | None = None,
    cache_source: str = "original_loader_volume",
    object_cache_hit: bool = False,
    future_hit: bool = False,
    cpu_cache_hit: bool = False,
    volume_read: bool = False,
    duplicate_read_prevented: bool = False,
) -> dict[str, Any]:
    """Create a per-model actual-load record with computed critical-path metrics.

    Definitions
    -----------
    *head_start_ms* is positive only if background load started before graph
    needed the model.

    *critical_path_saved_ms* = min(actual_load_duration_ms,
    max(0, graph_requested - actual_load_start)).  Capped at load duration,
    floored at zero.

    *remaining_wait_ms* = actual graph wait time (if observed).
    """
    record: dict[str, Any] = {
        "loader_type": loader_type,
        "canonical_key": canonical_key[:120] if canonical_key else "",
        "actual_load_start_unix_s": actual_load_start_unix_s,
        "actual_load_done_unix_s": actual_load_done_unix_s,
        "actual_load_duration_ms": 0.0,
        "graph_requested_model_unix_s": graph_requested_model_unix_s,
        "graph_wait_start_unix_s": graph_wait_start_unix_s,
        "graph_wait_done_unix_s": graph_wait_done_unix_s,
        "graph_wait_ms": 0.0,
        "head_start_ms": 0.0,
        "overlap_ms": 0.0,
        "critical_path_saved_ms": 0.0,
        "remaining_wait_ms": 0.0,
        "cache_source": cache_source,
        "object_cache_hit": object_cache_hit,
        "future_hit": future_hit,
        "cpu_cache_hit": cpu_cache_hit,
        "volume_read": volume_read,
        "duplicate_read_prevented": duplicate_read_prevented,
    }

    load_duration = _safe_delta_ms(actual_load_start_unix_s, actual_load_done_unix_s, "actual_load")
    if load_duration is not None:
        record["actual_load_duration_ms"] = load_duration

    graph_wait = _safe_delta_ms(graph_wait_start_unix_s, graph_wait_done_unix_s, "graph_wait")
    if graph_wait is not None:
        record["graph_wait_ms"] = graph_wait
        record["remaining_wait_ms"] = graph_wait

    if actual_load_start_unix_s is not None and graph_requested_model_unix_s is not None:
        head_start = (graph_requested_model_unix_s - actual_load_start_unix_s) * 1000
        record["head_start_ms"] = round(max(0.0, head_start), 2)

        if load_duration is not None and load_duration > 0:
            saved = min(load_duration, max(0.0, head_start))
            record["critical_path_saved_ms"] = round(saved, 2)

        if load_duration is not None and head_start > 0:
            overlap = min(load_duration, head_start)
            record["overlap_ms"] = round(overlap, 2)

    return record


def _build_actual_load_summary(
    per_model: list[dict],
) -> dict[str, Any]:
    """Aggregate per-model actual-load records into summary fields."""
    started = 0
    ready_before = 0
    waited = 0
    total_bg_ms = 0.0
    total_saved_ms = 0.0
    total_remaining_ms = 0.0
    dups = 0

    for m in per_model:
        if m.get("actual_load_start_unix_s") is not None:
            started += 1
            d_ms = m.get("actual_load_duration_ms", 0.0) or 0.0
            total_bg_ms += d_ms
        if m.get("head_start_ms", 0.0) > 0 and not m.get("graph_wait_ms", 0.0):
            ready_before += 1
        if (m.get("graph_wait_ms") or 0.0) > 0.01:
            waited += 1
        total_saved_ms += m.get("critical_path_saved_ms", 0.0) or 0.0
        total_remaining_ms += m.get("remaining_wait_ms", 0.0) or 0.0
        if m.get("duplicate_read_prevented"):
            dups += 1

    return {
        "enabled": started > 0,
        "models_started": started,
        "models_ready_before_graph": ready_before,
        "models_waited_by_graph": waited,
        "total_background_work_ms": round(total_bg_ms, 2),
        "estimated_critical_path_saved_ms": round(total_saved_ms, 2),
        "remaining_graph_wait_ms": round(total_remaining_ms, 2),
        "duplicate_reads_prevented": dups,
    }


# ── Post-sampler summary ────────────────────────────────────────────────────


def _build_post_sampler_summary(
    stages: dict[str, float],
    deltas: dict[str, float],
    output_timing: dict[str, Any],
) -> dict[str, Any]:
    """Attribution for the wall time after sampler finishes."""
    s2o = deltas.get("sampler_end_to_outputs_collected_ms", 0.0)
    vae_ms = output_timing.get("vae_decode_ms", 0.0) or 0.0
    collect_ms = output_timing.get("output_collection_total_ms", 0.0) or 0.0
    convert_ms = output_timing.get("image_conversion_total_ms", 0.0) or 0.0
    file_read_ms = output_timing.get("file_read_total_ms", 0.0) or 0.0
    packaging_ms = output_timing.get("return_packaging_ms", 0.0) or 0.0

    attributed = vae_ms + collect_ms + convert_ms + file_read_ms + packaging_ms
    unattributed = max(0.0, s2o - attributed)

    if s2o > 0 and unattributed == 0 and (s2o - attributed) < -1.0:
        # Small negative noise is clamped; large negative values are suspicious
        pass

    return {
        "sampler_end_to_outputs_collected_ms": round(s2o, 2),
        "vae_decode_ms": round(vae_ms, 2),
        "output_collection_total_ms": round(collect_ms, 2),
        "image_conversion_total_ms": round(convert_ms, 2),
        "file_read_total_ms": round(file_read_ms, 2),
        "return_packaging_ms": round(packaging_ms, 2),
        "unattributed_post_sampler_ms": round(unattributed, 2),
    }


# ── Data quality helpers ────────────────────────────────────────────────────


def _check_missing_local_stages(
    stages: dict[str, float],
    data_quality: dict[str, Any],
    warnings: list[str],
) -> None:
    """Emit warnings when local (client-side) stages are missing."""
    local_mandatory = [STAGE_LOCAL_MATERIALIZED]
    missing_local = [k for k in local_mandatory if k not in stages]

    if STAGE_CLIENT_PRESS not in stages:
        warnings.append(
            "t0_client_press missing: no browser/client press timestamp "
            "available. End-to-end wall-clock measurement is incomplete."
        )
        data_quality["warnings"].append("t0 missing")

    if STAGE_LOCAL_MODAL_SUBMIT_START not in stages:
        data_quality["missing_stages"].append(STAGE_LOCAL_MODAL_SUBMIT_START)


# ── Merge helper ────────────────────────────────────────────────────────────


def merge_wall_clock_trace(
    existing_client_trace: dict[str, Any] | None,
    remote_stages: dict[str, float] | None,
    restore_timing: dict[str, Any] | None,
    execution_timing: dict[str, Any] | None,
    output_timing: dict[str, Any] | None,
    actual_load_per_model: list[dict] | None = None,
    preload_stall_info: dict[str, Any] | None = None,
    warmup_info: dict[str, Any] | None = None,
    request_seq: int = 0,
    container_session_id: str = "",
    restore_session_id: str = "",
    container_import_unix_s: float = 0.0,
    restore_count: int = 0,
) -> dict[str, Any]:
    """Merge client-side trace with remote-side data to produce final trace.

    Never overwrites an existing stage with None.
    Preserves raw stage timestamps.
    """
    client_stages: dict[str, float] = {}
    trace_id: str | None = None

    if existing_client_trace:
        trace_id = existing_client_trace.get("trace_id") or _generate_trace_id()
        for k, v in existing_client_trace.items():
            if k.startswith("t") and isinstance(v, (int, float)):
                client_stages[k] = float(v)
    else:
        trace_id = _generate_trace_id()

    return build_wall_clock_trace(
        trace_id=trace_id,
        client_stages=client_stages or None,
        remote_stages=remote_stages,
        restore_timing=restore_timing,
        execution_timing=execution_timing,
        output_timing=output_timing,
        actual_load_per_model=actual_load_per_model,
        preload_stall_info=preload_stall_info,
        warmup_info=warmup_info,
        request_seq=request_seq,
        container_session_id=container_session_id,
        restore_session_id=restore_session_id,
        container_import_unix_s=container_import_unix_s,
        restore_count=restore_count,
    )


# ── Compact summary log line ────────────────────────────────────────────────


def make_summary_log_line(trace: dict[str, Any]) -> str:
    """One-line JSON summary for the [wall_trace.summary] log prefix."""
    deltas = trace.get("deltas_ms", {})
    al_summary = trace.get("actual_load_summary", {})
    ps_summary = trace.get("post_sampler_summary", {})
    data_q = trace.get("data_quality", {})
    cp = trace.get("critical_path", {})

    profile_level = trace.get("profile_level", _PROFILE_LEVEL)
    parts = [
        f"trace_id={trace.get('trace_id', '?')[:12]}",
        f"profile={profile_level}",
        f"req_seq={trace.get('request_seq', 0)}",
    ]

    lb2m = deltas.get("local_button_to_materialized_ms")
    if lb2m is not None:
        parts.append(f"btn2mat={lb2m}ms")

    m2e = deltas.get("modal_submit_to_entry_ms")
    if m2e is not None:
        parts.append(f"submit2entry={m2e}ms")

    r = deltas.get("restore_total_ms")
    if r is not None:
        parts.append(f"restore={r}ms")

    p2s = deltas.get("prompt_start_to_sampler_start_ms")
    if p2s is not None:
        parts.append(f"pre_sampler={p2s}ms")

    al_saved = al_summary.get("estimated_critical_path_saved_ms", 0.0)
    parts.append(f"actual_load_saved={al_saved}ms")

    s = deltas.get("sampler_ms")
    if s is not None:
        parts.append(f"sampler={s}ms")

    ps = ps_summary.get("sampler_end_to_outputs_collected_ms", 0.0)
    parts.append(f"post_sampler={ps}ms")

    rtv = deltas.get("remote_total_visible_ms")
    if rtv is not None:
        parts.append(f"remote_visible={rtv}ms")

    kn = cp.get("known_non_overlapping_ms")
    if kn is not None:
        parts.append(f"known_nonoverlap={kn}ms")

    ulw = cp.get("unexplained_local_wall_ms")
    if ulw is not None:
        parts.append(f"unexplained_local={ulw}ms")

    vae = deltas.get("vae_decode_ms")
    if vae is not None:
        parts.append(f"vae_decode={vae}ms")

    pa = deltas.get("return_packaging_ms")
    if pa is not None:
        parts.append(f"return_pkg={pa}ms")

    lw = deltas.get("local_file_write_ms")
    if lw is not None:
        parts.append(f"local_write={lw}ms")

    dq = data_q.get("missing_stages", [])
    if dq:
        parts.append(f"missing_stages={dq}")

    iq = data_q.get("invalid_deltas", [])
    if iq:
        parts.append(f"invalid_deltas={len(iq)}")

    ri = cp.get("restore_included_in_submit2entry", False)
    if ri:
        parts.append("restore_incl_in_submit2entry=1")

    return "[wall_trace.summary] " + " ".join(parts)


# ── Compact top-level result summary ────────────────────────────────────────


def make_wall_clock_summary(trace: dict[str, Any]) -> dict[str, Any]:
    """Compact top-level summary for ``result['_wall_clock_summary']``."""
    deltas = trace.get("deltas_ms", {})
    al_summary = trace.get("actual_load_summary", {})
    cp = trace.get("critical_path", {})
    return {
        "trace_id": trace.get("trace_id", ""),
        "local_button_to_materialized_ms": deltas.get("local_button_to_materialized_ms"),
        "remote_total_visible_ms": deltas.get("remote_total_visible_ms"),
        "actual_load_estimated_saved_ms": al_summary.get("estimated_critical_path_saved_ms", 0.0),
        "sampler_ms": deltas.get("sampler_ms"),
        "unexplained_local_wall_ms": cp.get("unexplained_local_wall_ms"),
        "can_claim_wall_time_win": False,
    }
