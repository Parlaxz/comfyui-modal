"""Audit-only decomposition of the Golden C0 CUDA arena lifecycle.

Disabled by default and imported by nothing on the production path.  Every
function in this module is a *pure analysis* over telemetry that
``golden_io_process_v2.SharedArenaRing`` and
``golden_model_transport.arena_ensure_detail`` already record, so no
production behaviour, geometry, timing boundary, or CUDA call is touched.

The point of the module is that the C0 arena already emits every milestone
this audit needs.  ``SharedArenaRing.startup_marks`` holds raw
``time.monotonic_ns()`` stamps for arena entry, POSIX-SHM creation, slot-view
construction, the source-process spawn, and both ends of the
``cudaHostRegister`` call; ``register_ms``/``register_start_ns``/
``register_end_ns`` hold the call-only boundary; ``child_ready_evidence``
holds the spawn/ready overlap proof.  Nothing has to be re-instrumented to
split the registration cost, so this branch adds no runtime hook at all.

``enabled()`` exists only so a future opt-in arm can gate a call into this
module without requiring a production edit today.  It is deliberately NOT
declared in ``config_authority``/``flag_registry``/``_runtime_env``: a
three-layer deploy flag would imply an arm that does not exist, and two
earlier phases shipped exactly that kind of silent no-op
(``975aec14``).

Where a field was not recorded the result is ``"unknown"``.  This module
never infers a measurement it was not given.
"""

from __future__ import annotations

import os
from typing import Any, Mapping, Optional

AUDIT_ENV = "COMFYMODAL_GOLDEN_C0_ARENA_LIFECYCLE_AUDIT"

_TRUTHY = {"1", "true", "yes", "on"}
_PAGE_BYTES = 4096


def enabled() -> bool:
    """True only when the arena-lifecycle audit analysis is explicitly asked for."""
    return str(os.environ.get(AUDIT_ENV) or "").strip().lower() in _TRUTHY


def _ms(value: Any) -> Optional[float]:
    try:
        return round(int(value) / 1e6, 4)
    except (TypeError, ValueError):
        return None


def _marks(ensure: Optional[Mapping[str, Any]]) -> dict[str, int]:
    raw = ensure.get("startup_marks") if isinstance(ensure, Mapping) else None
    if not isinstance(raw, Mapping):
        return {}
    out: dict[str, int] = {}
    for key, value in raw.items():
        try:
            out[str(key)] = int(value)
        except (TypeError, ValueError):
            continue
    return out


def _span(marks: Mapping[str, int], start: str, end: str) -> Optional[float]:
    """Milliseconds between two recorded monotonic stamps, or None if either is absent."""
    if start not in marks or end not in marks:
        return None
    return _ms(marks[end] - marks[start])


def _first_present(marks: Mapping[str, int], *keys: str) -> Optional[int]:
    for key in keys:
        if key in marks:
            return marks[key]
    return None


def _last_present(marks: Mapping[str, int], *keys: str) -> Optional[int]:
    for key in reversed(keys):
        if key in marks:
            return marks[key]
    return None


def decompose(ensure: Mapping[str, Any]) -> dict[str, Any]:
    """Split one container's arena establishment into its measured phases.

    ``ensure`` is the ``arena_ensure`` block produced by
    ``golden_model_transport.arena_ensure_detail``.  Phases are computed from
    the recorded monotonic stamps only; a phase whose endpoints were not
    recorded is reported as ``None`` rather than estimated.
    """
    marks = _marks(ensure)
    enter = _first_present(marks, "c0_ensure_enter")
    reg_begin = _first_present(marks, "cuda_host_register_begin")
    reg_end = _last_present(marks, "cuda_host_register_end")
    spawn_begin = _first_present(marks, "source_thread_spawn_begin")
    ready = _last_present(
        marks, "source_thread_ready", "parent_child_ready_received", "source_thread_start_end"
    )

    register_call_ms = _span(marks, "cuda_host_register_begin", "cuda_host_register_end")
    pre_register_ms = (
        _ms(reg_begin - enter) if (reg_begin is not None and enter is not None) else None
    )
    post_register_ms = (
        _ms(ready - reg_end) if (ready is not None and reg_end is not None) else None
    )
    child_boot_ms = (
        _ms(ready - spawn_begin) if (ready is not None and spawn_begin is not None) else None
    )
    spawn_return_ms = _span(marks, "source_thread_spawn_begin", "source_thread_spawn_end")

    overlap_ms = None
    if reg_begin is not None and reg_end is not None and spawn_begin is not None and ready is not None:
        overlap_ms = _ms(max(0, min(reg_end, ready) - max(reg_begin, spawn_begin)))

    establishment_total_ms = (
        _ms(ready - enter) if (ready is not None and enter is not None) else None
    )
    # The part of establishment that is not hidden behind the source-process
    # boot window.  This is the floor the restore path actually pays even
    # though registration and child startup already run concurrently.
    serial_exposure_ms = (
        round(establishment_total_ms - overlap_ms, 4)
        if (establishment_total_ms is not None and overlap_ms is not None)
        else None
    )

    # Ceiling on hiding the register call behind the child boot: only the
    # portion of the call that fits inside the boot window can ever be free.
    hidden_register_ceiling_ms = None
    if register_call_ms is not None and child_boot_ms is not None and pre_register_ms is not None:
        boot_window_after_prep = max(0.0, child_boot_ms - pre_register_ms)
        hidden_register_ceiling_ms = round(min(register_call_ms, boot_window_after_prep), 4)
    root_wall_saving_ceiling_ms = (
        round(register_call_ms - hidden_register_ceiling_ms, 4)
        if (register_call_ms is not None and hidden_register_ceiling_ms is not None)
        else None
    )

    if register_call_ms is None or child_boot_ms is None:
        establishment_owner = "unknown"
    elif child_boot_ms > register_call_ms:
        establishment_owner = "source_process_boot"
    else:
        establishment_owner = "cuda_host_register"

    # register_ms is documented in code as the call-only boundary; prove that
    # against the raw monotonic stamps rather than trusting the field name.
    reported_register_ms = ensure.get("register_ms") if isinstance(ensure, Mapping) else None
    reported_register_wall: Optional[int] = None
    if isinstance(reported_register_ms, (int, float)):
        reported_register_wall = int(reported_register_ms) * 1_000_000
    if register_call_ms is None or reported_register_wall is None:
        register_boundary_agrees: Any = "unknown"
    else:
        register_boundary_agrees = abs(
            register_call_ms * 1e6 - reported_register_wall
        ) <= 2_000_000

    return {
        "arena_bytes": ensure.get("arena_bytes") if isinstance(ensure, Mapping) else None,
        "slot_count": ensure.get("slot_count") if isinstance(ensure, Mapping) else None,
        "slot_bytes": ensure.get("slot_bytes") if isinstance(ensure, Mapping) else None,
        "registration_order": (
            ensure.get("registration_order") if isinstance(ensure, Mapping) else None
        ),
        "registered": ensure.get("registered") if isinstance(ensure, Mapping) else None,
        "establishment_total_ms": establishment_total_ms,
        "backing_create_ms": _span(marks, "shm_create_begin", "shm_create_end"),
        "frombuffer_ms": _span(marks, "torch_frombuffer_begin", "torch_frombuffer_end"),
        "slot_views_ms": _span(marks, "slot_views_begin", "slot_views_end"),
        "pre_register_ms": pre_register_ms,
        "register_call_ms": register_call_ms,
        "post_register_ms": post_register_ms,
        "spawn_return_ms": spawn_return_ms,
        "child_boot_ms": child_boot_ms,
        "child_startup_ms": (
            ensure.get("child_startup_ms") if isinstance(ensure, Mapping) else None
        ),
        "register_child_overlap_ms": overlap_ms,
        "spawn_precedes_register": (
            bool(reg_begin >= spawn_begin)
            if (reg_begin is not None and spawn_begin is not None) else "unknown"
        ),
        "serial_exposure_ms": serial_exposure_ms,
        "establishment_owner": establishment_owner,
        "hidden_register_ceiling_ms": hidden_register_ceiling_ms,
        "root_wall_saving_ceiling_ms": root_wall_saving_ceiling_ms,
        "register_boundary_agrees_with_marks": register_boundary_agrees,
        "register_ms_reported": reported_register_ms,
    }


def registration_context_evidence(ensure: Mapping[str, Any]) -> dict[str, Any]:
    """Was a CUDA context already current when ``cudaHostRegister`` was called?

    Only the opt-in ``COMFYMODAL_GOLDEN_C0_REGISTRATION_DIAG`` arm samples the
    driver context handle, through
    ``golden_io_process_v2._registration_state`` ->
    ``_cuda_registration_identity``.  Without that arm the honest answer is
    ``"unknown"``, never an inference.
    """
    diag = ensure.get("registration_diagnostic") if isinstance(ensure, Mapping) else None
    if not isinstance(diag, Mapping):
        return {"sampled": False, "lazy_context_init_inside_call": "unknown"}

    def handle(block: Any) -> Optional[str]:
        if not isinstance(block, Mapping):
            return None
        identity = block.get("identity")
        if not isinstance(identity, Mapping):
            return None
        value = identity.get("context_handle_before_or_after")
        return str(value) if value is not None else None

    before = handle(diag.get("before"))
    after = handle(diag.get("after"))

    if before is None or after is None:
        lazy: Any = "unknown"
    elif before in {"0x0", "0x0000000000000000", "0"} and after not in {before}:
        lazy = "yes"
    elif before != "0x0" and before == after:
        lazy = "no"
    else:
        lazy = "unknown"

    rss_before = None
    rss_after = None
    for block, key in ((diag.get("before"), "rss_kb"), (diag.get("after"), "rss_kb")):
        if not isinstance(block, Mapping):
            continue
        proc = block.get("proc_status")
        if isinstance(proc, Mapping):
            value = proc.get(key)
            if isinstance(value, int):
                if rss_before is None:
                    rss_before = value
                else:
                    rss_after = value
    return {
        "sampled": True,
        "api": diag.get("api"),
        "flags": diag.get("flags"),
        "return_code": diag.get("return_code"),
        "call_wall_ns": diag.get("wall_monotonic_ns"),
        "context_handle_before": before,
        "context_handle_after": after,
        "lazy_context_init_inside_call": lazy,
        "context_preinit_ms": diag.get("context_preinit_ms"),
        "rss_kb_before": rss_before,
        "rss_kb_after": rss_after,
        "first_touch_by_registration": (
            "yes"
            if (isinstance(rss_before, int) and isinstance(rss_after, int)
                and rss_before == 0 and rss_after > 0)
            else "unknown"
        ),
    }


def slot_registration_plan(
    ensure: Mapping[str, Any], *, prefix_slots: int
) -> dict[str, Any]:
    """Arithmetic feasibility of registering only a prefix of the arena slots.

    This proves the ranges are disjoint and page-aligned relative to the arena
    base.  It does not claim CUDA will accept them, does not measure a
    partial registration, and does not touch the running arena.
    """
    arena_bytes = ensure.get("arena_bytes") if isinstance(ensure, Mapping) else None
    slot_count = ensure.get("slot_count") if isinstance(ensure, Mapping) else None
    slot_bytes = ensure.get("slot_bytes") if isinstance(ensure, Mapping) else None
    if not isinstance(arena_bytes, (int, float)):
        return {"feasible": "unknown", "reason": "arena_bytes_not_recorded"}
    if not isinstance(slot_count, (int, float)):
        return {"feasible": "unknown", "reason": "slot_count_not_recorded"}
    if not isinstance(slot_bytes, (int, float)):
        return {"feasible": "unknown", "reason": "slot_bytes_not_recorded"}
    arena_bytes_i = int(arena_bytes)
    slot_count_i = int(slot_count)
    slot_bytes_i = int(slot_bytes)

    plan: dict[str, Any] = {
        "arena_bytes": arena_bytes_i,
        "slot_count": slot_count_i,
        "slot_bytes": slot_bytes_i,
        "strict_product_holds": arena_bytes_i == slot_count_i * slot_bytes_i,
    }
    if not plan["strict_product_holds"]:
        plan["feasible"] = False
        plan["reason"] = "c0_arena_geometry_mismatch"
        return plan
    count = max(0, min(int(prefix_slots), slot_count_i))
    plan["prefix_slots"] = count
    plan["registered_bytes"] = count * slot_bytes_i
    plan["unregistered_tail_bytes"] = (slot_count_i - count) * slot_bytes_i
    plan["slot_stride_page_aligned"] = slot_bytes_i % _PAGE_BYTES == 0
    plan["all_prefix_ranges_disjoint"] = True
    plan["page_aligned_relative_to_base"] = slot_bytes_i % _PAGE_BYTES == 0
    plan["feasible"] = "arithmetically"
    plan["note"] = (
        "Each slot is a page-aligned, mutually disjoint sub-range of the same "
        "mapping, so a per-slot or per-prefix registration is geometrically "
        "expressible. Acceptance, thread-safety against an in-flight H2D, and "
        "cost are NOT established here."
    )
    return plan


def overlap_timeline(ensure: Mapping[str, Any]) -> dict[str, Any]:
    """Current serialized/overlapped startup timeline and its safe ceiling.

    ``current_timeline`` describes what the shipped code already does:
    arena prep, then the source-process spawn, then the registration call,
    then the ready join -- so registration already runs concurrently with the
    source owner's boot.  ``maximal_safe_overlap_timeline`` describes the most
    that could be hidden without touching the source architecture: it moves
    no work that the ready join still depends on, and only credits the register
    time that fits inside the child boot window.
    """
    phases = decompose(ensure)
    child_boot_ms = phases.get("child_boot_ms")
    register_call_ms = phases.get("register_call_ms")
    post_register_ms = phases.get("post_register_ms")

    timeline: dict[str, Any] = {
        "already_overlapped_today": bool(phases.get("spawn_precedes_register") is True),
        "pre_register_ms": phases.get("pre_register_ms"),
        "register_call_ms": register_call_ms,
        "post_register_ready_join_ms": post_register_ms,
        "source_process_boot_ms": child_boot_ms,
        "register_child_overlap_ms": phases.get("register_child_overlap_ms"),
        "establishment_owner": phases.get("establishment_owner"),
        "root_wall_saving_ceiling_ms": phases.get("root_wall_saving_ceiling_ms"),
    }
    if isinstance(post_register_ms, (int, float)) and isinstance(register_call_ms, (int, float)):
        timeline["registration_on_critical_path"] = post_register_ms > 0.0
    else:
        timeline["registration_on_critical_path"] = "unknown"
    timeline["note"] = (
        "Only non-overlapping root-wall savings are credited. Registration "
        "time already hidden behind the source-process boot window is "
        "counted zero, not twice."
    )
    return timeline


__all__ = [
    "AUDIT_ENV",
    "decompose",
    "enabled",
    "overlap_timeline",
    "registration_context_evidence",
    "slot_registration_plan",
]