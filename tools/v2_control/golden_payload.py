"""Small, dependency-free helpers for constructing Golden requests."""

from __future__ import annotations

import copy
from typing import Any


GOLDEN_P1_MODE = "golden_p1_serial"
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
    invocation_id: str | None = None,
    cpu_qd2_prefetch: bool = False,
) -> dict[str, Any]:
    if not isinstance(cpu_qd2_prefetch, bool):
        raise ValueError("golden_cpu_qd2_prefetch_must_be_bool")
    if cpu_qd2_prefetch and _contains_true_selector(source, "instant_tensor"):
        raise ValueError("golden_cpu_qd2_prefetch_instant_tensor_conflict")
    payload = {
        "request_id": request_id,
        "prompt": copy.deepcopy(source["prompt"]),
        "extra_data": copy.deepcopy(source["extra_data"]),
        "modal_options": copy.deepcopy(source["modal_options"]),
        "request_origin_info": {
            "benchmark_mode": GOLDEN_P1_MODE,
            "golden_p1_run_index": index,
            "golden_p1_request_id": request_id,
            "serial": True,
        },
    }
    if attention_backend is not None:
        normalized = str(attention_backend).strip().lower()
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
    if invocation_id:
        payload["request_origin_info"]["v2ctl_invocation_id"] = str(invocation_id)
    return payload
