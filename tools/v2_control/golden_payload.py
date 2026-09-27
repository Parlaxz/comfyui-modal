"""Small, dependency-free helpers for constructing Golden requests."""

from __future__ import annotations

import copy
from typing import Any


GOLDEN_P1_MODE = "golden_p1_serial"
GOLDEN_PARALLEL_MODE = "golden_p1_parallel"
GOLDEN_ATTENTION_BACKENDS = ("pytorch", "sage", "comfy_kitchen")


def _contains_true_selector(value: Any, selector: str) -> bool:
    """Find a truthy selector in request-owned metadata without mutating it."""
    if isinstance(value, dict):
        for key, child in value.items():
            if str(key).strip().lower() == selector and child is True:
                return True
            if _contains_true_selector(child, selector):
                return True
    elif isinstance(value, (list, tuple)):
        return any(_contains_true_selector(child, selector) for child in value)
    return False


def _golden_p1_request_payload(
    source: dict[str, Any],
    *,
    request_id: str,
    index: int,
    attention_backend: str | None = None,
    golden_mode: str = "serial",
    invocation_id: str | None = None,
    cpu_qd2_prefetch: bool = False,
    deep_trace: bool = False,
) -> dict[str, Any]:
    if not isinstance(cpu_qd2_prefetch, bool):
        raise ValueError("golden_cpu_qd2_prefetch_must_be_bool")
    if not isinstance(deep_trace, bool):
        raise ValueError("golden_deep_trace_must_be_bool")
    if cpu_qd2_prefetch and _contains_true_selector(source, "instant_tensor"):
        raise ValueError("golden_cpu_qd2_prefetch_instant_tensor_conflict")
    mode = str(golden_mode).strip().lower()
    if mode not in {"serial", "parallel"}:
        raise ValueError("golden_mode_invalid")
    payload = {
        "request_id": request_id,
        "prompt": copy.deepcopy(source["prompt"]),
        "extra_data": copy.deepcopy(source["extra_data"]),
        "modal_options": copy.deepcopy(source["modal_options"]),
        "request_origin_info": {
            "benchmark_mode": GOLDEN_P1_MODE if mode == "serial" else GOLDEN_PARALLEL_MODE,
            "golden_mode": mode,
            "golden_p1_run_index": index,
            "golden_p1_request_id": request_id,
            "serial": mode == "serial",
        },
    }
    normalized = (
        "sage"
        if attention_backend is None
        else str(attention_backend).strip().lower()
    )
    if normalized not in GOLDEN_ATTENTION_BACKENDS:
        raise ValueError(
            "golden attention backend must be one of: "
            + ", ".join(GOLDEN_ATTENTION_BACKENDS)
        )
    payload["attention_backend"] = normalized
    # Keep the control payload byte-compatible: the optional request selector
    # is emitted only for the explicit QD2 arm.
    if cpu_qd2_prefetch:
        payload["cpu_qd2_prefetch"] = True
        payload["request_origin_info"]["golden_arm"] = "cpu_qd2_prefetch"
    if deep_trace:
        payload["deep_trace"] = True
        payload["request_origin_info"]["golden_deep_trace"] = True
    if invocation_id:
        payload["request_origin_info"]["v2ctl_invocation_id"] = str(invocation_id)
    return payload
