"""Fail-closed policy for the narrow defensive CUDA cache bypass."""

from __future__ import annotations

import math
import sys
from typing import Any, Callable

from .env import env_flag


EMPTY_CACHE_BYPASS_FLAG = "COMFYMODAL_V2_HIGH_HEADROOM_EMPTY_CACHE_BYPASS"

SOFT_CACHE_REASONS = frozenset(
    {
        "free_memory_after_unload",
        "free_memory_defensive_no_unload",
        "cleanup_models_gc_dead_model",
        "vae_oom_retry",
        "other",
    }
)


def bypass_enabled() -> bool:
    return env_flag(EMPTY_CACHE_BYPASS_FLAG, default=False)


def _known_number(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
        and float(value) >= 0
    )


def _known_count(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def evaluate_bypass(
    *,
    enabled: bool,
    soft_cache_reason: Any,
    models_unloaded_count: Any,
    physical_free_bytes: Any,
    operation_required_bytes: Any,
    minimum_required_bytes: Any,
    allocator_backend: Any,
    capture_active: Any,
    custom_allocator_active: Any,
    custom_pool_active: Any,
) -> dict[str, Any]:
    required_bytes = None
    headroom_ratio = None
    if _known_number(operation_required_bytes) and _known_number(minimum_required_bytes):
        required_bytes = max(
            float(operation_required_bytes), float(minimum_required_bytes)
        )
        if required_bytes > 0 and _known_number(physical_free_bytes):
            headroom_ratio = float(physical_free_bytes) / required_bytes

    reason_known = (
        isinstance(soft_cache_reason, str)
        and soft_cache_reason in SOFT_CACHE_REASONS
    )
    known = all(
        (
            reason_known,
            _known_count(models_unloaded_count),
            _known_number(physical_free_bytes),
            _known_number(operation_required_bytes),
            _known_number(minimum_required_bytes),
            isinstance(allocator_backend, str),
            isinstance(capture_active, bool),
            isinstance(custom_allocator_active, bool),
            isinstance(custom_pool_active, bool),
            required_bytes is not None and required_bytes > 0,
        )
    )
    physical_value = (
        float(physical_free_bytes) if _known_number(physical_free_bytes) else -1.0
    )
    required_value = float(required_bytes) if required_bytes is not None else -1.0
    eligible = bool(
        enabled
        and known
        and soft_cache_reason == "free_memory_defensive_no_unload"
        and models_unloaded_count == 0
        and allocator_backend == "native"
        and not capture_active
        and not custom_allocator_active
        and not custom_pool_active
        and physical_value >= 2.0 * required_value
    )
    return {
        "soft_cache_reason": soft_cache_reason,
        "eligible": eligible,
        "decision": "bypass_empty_cache" if eligible else "native",
        "physical_free_bytes": (
            int(physical_free_bytes) if _known_number(physical_free_bytes) else None
        ),
        "required_bytes": int(required_bytes) if required_bytes is not None else None,
        "minimum_required_bytes": (
            int(minimum_required_bytes)
            if _known_number(minimum_required_bytes)
            else None
        ),
        "headroom_ratio": headroom_ratio,
        "allocator_backend": allocator_backend
        if isinstance(allocator_backend, str)
        else None,
        "capture_active": capture_active if isinstance(capture_active, bool) else None,
        "custom_pool_active": (
            custom_pool_active if isinstance(custom_pool_active, bool) else None
        ),
        "custom_allocator_active": (
            custom_allocator_active
            if isinstance(custom_allocator_active, bool)
            else None
        ),
        "models_unloaded_count": (
            models_unloaded_count if _known_count(models_unloaded_count) else None
        ),
        "known": known,
    }


def _active_trace() -> Any:
    module = sys.modules.get("comfymodal_runtime.model_preload")
    if module is None:
        return None
    for name in ("_ACTIVE_REQUEST_TRACE", "_ACTIVE_LANE_TRACE"):
        variable = getattr(module, name, None)
        getter = getattr(variable, "get", None)
        if callable(getter):
            trace = getter()
            if trace is not None:
                return trace
    return None


def emit_decision(metadata: dict[str, Any]) -> None:
    try:
        trace = _active_trace()
        if trace is not None:
            trace.emit(
                "empty_cache_bypass_decision",
                phase="execution",
                metadata=dict(metadata),
            )
    except Exception:
        pass


def execute_soft_cache(
    decision: dict[str, Any],
    *,
    synchronize: Callable[[], Any],
    empty_cache: Callable[[], Any],
    ipc_collect: Callable[[], Any],
    event_sink: Callable[[dict[str, Any]], Any] | None = None,
) -> dict[str, Any]:
    empty_cache_executed = False
    status = "ok"
    try:
        synchronize()
        if not (
            decision.get("eligible", False) is True
            and decision.get("known", False) is True
        ):
            empty_cache_executed = True
            empty_cache()
        ipc_collect()
    except BaseException:
        status = "error"
        raise
    finally:
        event = {
            **decision,
            "empty_cache_executed": empty_cache_executed,
            "status": status,
        }
        try:
            if event_sink is not None:
                event_sink(event)
            else:
                emit_decision(event)
        except Exception:
            pass
    return event
