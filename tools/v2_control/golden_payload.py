"""Small, dependency-free helpers for constructing Golden requests."""

from __future__ import annotations

import copy
from typing import Any


GOLDEN_P1_MODE = "golden_p1_serial"
GOLDEN_ATTENTION_BACKENDS = ("pytorch", "sage", "comfy_kitchen")


def _golden_p1_request_payload(
    source: dict[str, Any],
    *,
    request_id: str,
    index: int,
    attention_backend: str | None = None,
    invocation_id: str | None = None,
) -> dict[str, Any]:
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
    if invocation_id:
        payload["request_origin_info"]["v2ctl_invocation_id"] = str(invocation_id)
    return payload
