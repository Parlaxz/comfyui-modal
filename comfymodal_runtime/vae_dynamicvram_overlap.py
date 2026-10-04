"""Relocate the VAE's required DynamicVRAM activation under the sampling window.

The audit (``reports/P9_VAE_RESIDENCY_AUDIT.md``, classification ``REQUIRED``)
established that the work ``VAE.decode`` performs is *not* redundant with
``golden_vae_load``:

* ``golden_vae_load`` proves byte-level residency and stops.  It never invokes
  the GPU load path on the VAE patcher -- its only patcher operations are
  ``CoreModelPatcher`` construction and ``load_state_dict(assign=True)``.
* ``ModelPatcherDynamic.__init__`` leaves ``dynamic_pins[dev]`` with
  ``hostbufs_initialized=False`` and ``active=False``, and the patcher is absent
  from ``model_management.current_loaded_models``.

So the ``partially_load`` inside ``VAE.decode`` is the *first and only*
DynamicVRAM activation of that patcher.  It cannot be removed; the only lever is
**when** it happens.  This module performs that same canonical activation during
the existing ``sampling || vae_load`` overlap window, so its cost is hidden
behind sampling instead of sitting on the post-sampling critical path.

Three properties make the relocation safe rather than merely early:

1. **Same call, no bypass.**  Activation goes through
   ``model_management.load_models_gpu([patcher], ...)`` exactly as ``VAE.decode``
   does.  No upstream semantics are altered, no state flag is faked, and the
   in-decode canonical path remains the fallback for every failure.
2. **Registry-neutral.**  ``load_models_gpu`` ends with an *unconditional*
   ``current_loaded_models.insert(0, loaded_model)`` (pristine upstream
   ``model_management.py``).  ``VAE.decode`` calls it again unconditionally, so
   leaving our entry in place would register the same ``LoadedModel`` twice.
   That is not cosmetic: at teardown ``free_memory(1e30)`` walks the registry and
   calls ``model_unload`` once per entry; ``model_unload`` sets
   ``self.model_finalizer = None`` on its first call, so the second call raises
   ``AttributeError`` on ``None.detach()``.  This module therefore restores the
   registry to its exact pre-call contents.  The patcher's DynamicVRAM state
   (AIMDO host buffers, vbar, ``active=True``) survives, which is precisely the
   expensive first-time setup being hidden; the decode-time canonical call then
   re-derives its own single registry entry exactly as it does today.
3. **Fail-soft, never breaks inference.**  Any missing precondition, exception or
   failed postcondition returns a visible record and leaves the canonical
   decode-time activation to run unchanged.
"""

from __future__ import annotations

import time
from typing import Any, Optional


# Status vocabulary.  ``activated`` is the only value that means "the patcher's
# DynamicVRAM state is now warm and decode will not pay for first-time setup".
STATUS_ACTIVATED = "activated"
STATUS_NOT_ATTEMPTED = "not_attempted"
STATUS_GUARD_FAILED = "guard_failed"
STATUS_POSTCONDITION_FAILED = "postcondition_failed"
STATUS_ERROR = "error"


def capture_identity(session: Any) -> dict[str, Any]:
    """Snapshot the identity the guard will re-check before activating.

    Captured immediately after ``golden_vae_load`` returns, i.e. once the VAE and
    its patcher exist and ``validate_qd_adoption`` has already proven the
    parameters are the transport's CUDA views.
    """
    vae = getattr(session, "vae", None)
    patcher = getattr(vae, "patcher", None) if vae is not None else None
    return {
        "vae_present": vae is not None,
        "patcher_present": patcher is not None,
        # ``id`` is the audited identity test: it detects a different VAE object
        # or a re-patched/replaced patcher without depending on == semantics.
        "vae_id": id(vae) if vae is not None else 0,
        "patcher_id": id(patcher) if patcher is not None else 0,
        "load_device": str(getattr(patcher, "load_device", "") or ""),
        "is_dynamic": _is_dynamic(patcher),
        "captured_monotonic_ns": time.monotonic_ns(),
    }


def _is_dynamic(patcher: Any) -> bool:
    checker = getattr(patcher, "is_dynamic", None)
    try:
        return bool(callable(checker) and checker())
    except Exception:
        return False


def _guard_preconditions(session: Any, identity: dict[str, Any]) -> tuple[bool, str]:
    """Audited §17 preconditions.  Returns ``(ok, reason)``.

    Deliberately omits a "no intervening eviction" clause: the audit's §5 proves
    the VAE cannot be evicted before decode, and a vacuous condition would read
    like a guarantee it does not provide.
    """
    if not identity.get("vae_present") or not identity.get("patcher_present"):
        return False, "vae_or_patcher_missing"
    vae = getattr(session, "vae", None)
    patcher = getattr(vae, "patcher", None) if vae is not None else None
    if vae is None or patcher is None:
        return False, "vae_or_patcher_missing"
    if id(vae) != identity.get("vae_id"):
        return False, "vae_identity_changed"
    if id(patcher) != identity.get("patcher_id"):
        return False, "patcher_identity_changed"
    if not _is_dynamic(patcher):
        return False, "patcher_not_dynamic"
    load_device = str(getattr(patcher, "load_device", "") or "")
    if not identity.get("load_device") or load_device != identity.get("load_device"):
        return False, "load_device_changed"
    return True, "ok"


def _loaded_size_bytes(patcher: Any) -> Optional[int]:
    """``patcher.loaded_size()`` as an int, or ``None`` if it is unavailable."""
    loaded_size = getattr(patcher, "loaded_size", None)
    if not callable(loaded_size):
        return None
    try:
        return int(loaded_size())
    except Exception:
        return None


def _resident(patcher: Any) -> bool:
    size = _loaded_size_bytes(patcher)
    return size is not None and size > 0


def _on_load_device(vae: Any, patcher: Any) -> bool:
    """Every first-stage parameter must sit on the patcher's load device."""
    load_device = getattr(patcher, "load_device", None)
    if load_device is None:
        return False
    try:
        wanted = str(load_device)
        first_stage = getattr(vae, "first_stage_model", None)
        params = list(first_stage.parameters()) if first_stage is not None else []
        if not params:
            return False
        return all(str(param.device) == wanted for param in params)
    except Exception:
        return False


def _registry_count(model_management: Any, patcher: Any) -> int:
    """How many registry entries refer to ``patcher``.

    Upstream stores ``LoadedModel`` objects and defines
    ``LoadedModel.__eq__`` as ``self.model is other.model``, while
    ``ModelPatcher`` defines no ``__eq__`` at all.  Comparing by identity
    directly is what that ``__eq__`` *means*, and it cannot be broken by
    reflected-equality behaviour or by a future ``__eq__`` on either class.
    """
    try:
        registry = getattr(model_management, "current_loaded_models", []) or []
        return sum(1 for entry in registry if getattr(entry, "model", None) is patcher)
    except Exception:
        return -1


def _registered(model_management: Any, patcher: Any) -> bool:
    return _registry_count(model_management, patcher) > 0


def early_activate(session: Any, identity: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    """Run the required DynamicVRAM activation now, under sampling.

    Never raises.  Returns a telemetry record whose ``status`` is
    :data:`STATUS_ACTIVATED` only when the guard held, the canonical call
    returned, and every postcondition is proven.  Any other outcome means the
    canonical decode-time activation is still owed and will run unchanged.
    """
    record: dict[str, Any] = {
        "status": STATUS_NOT_ATTEMPTED,
        "reason": "not_attempted",
        "sampling_active_at_start": None,
        "activation_start_ns": None,
        "activation_end_ns": None,
        "activation_ms": None,
        "registry_entries_before": None,
        "registry_entries_after_restore": None,
        "registry_restored": None,
        "registered": False,
        "resident": False,
        "on_load_device": False,
        "loaded_size_bytes": None,
        "load_device": str((identity or {}).get("load_device", "") or ""),
    }
    identity = identity if isinstance(identity, dict) else {}
    ok, reason = _guard_preconditions(session, identity)
    if not ok:
        record.update({"status": STATUS_GUARD_FAILED, "reason": f"precondition:{reason}"})
        return record

    try:
        import comfy.model_management as model_management  # upstream, allowed import
    except Exception as exc:
        record.update(
            {"status": STATUS_ERROR, "reason": f"import:{type(exc).__name__}"}
        )
        return record

    vae = getattr(session, "vae", None)
    patcher = getattr(vae, "patcher", None)

    # Snapshot the registry so the canonical decode-time call re-derives its own
    # single entry.  See the module docstring: leaving ours behind would
    # double-register the LoadedModel and raise at teardown.
    registry = getattr(model_management, "current_loaded_models", None)
    snapshot: Optional[list] = None
    if registry is not None:
        try:
            snapshot = list(registry)
            record["registry_entries_before"] = len(snapshot)
        except Exception:
            snapshot = None

    record["activation_start_ns"] = time.monotonic_ns()
    try:
        # The same canonical entry point VAE.decode uses, with the same default
        # arguments.  ``force_full_load`` is read from the VAE so a VAE that
        # disabled offload keeps its exact semantics.
        force_full_load = bool(getattr(vae, "disable_offload", False))
        model_management.load_models_gpu(
            [patcher], force_full_load=force_full_load
        )
    except Exception as exc:
        record["activation_end_ns"] = time.monotonic_ns()
        record["activation_ms"] = (
            record["activation_end_ns"] - record["activation_start_ns"]
        ) / 1e6
        _restore_registry(registry, snapshot, record)
        record.update(
            {"status": STATUS_ERROR, "reason": f"activation:{type(exc).__name__}:{str(exc)[:120]}"}
        )
        return record
    record["activation_end_ns"] = time.monotonic_ns()
    record["activation_ms"] = (
        record["activation_end_ns"] - record["activation_start_ns"]
    ) / 1e6

    # Postconditions are evaluated against the live state, then the registry is
    # restored.  Order matters: ``registered`` is only true while our entry is
    # still present, so the two facts are both observable in the record.
    record["registered"] = _registered(model_management, patcher)
    record["resident"] = _resident(patcher)
    record["on_load_device"] = _on_load_device(vae, patcher)
    record["loaded_size_bytes"] = _loaded_size_bytes(patcher)
    record["registry_entries_during"] = _registry_count(model_management, patcher)

    _restore_registry(registry, snapshot, record)
    record["registry_entries_after_restore_vae_count"] = _registry_count(
        model_management, patcher
    )

    if record["registered"] and record["resident"] and record["on_load_device"]:
        record.update({"status": STATUS_ACTIVATED, "reason": "ok"})
    else:
        record.update(
            {
                "status": STATUS_POSTCONDITION_FAILED,
                "reason": "postcondition:"
                + ",".join(
                    name
                    for name, ok_flag in (
                        ("registered", record["registered"]),
                        ("resident", record["resident"]),
                        ("on_load_device", record["on_load_device"]),
                    )
                    if not ok_flag
                ),
            }
        )
    return record


def _restore_registry(
    registry: Any, snapshot: Optional[list], record: dict[str, Any]
) -> None:
    """Put ``current_loaded_models`` back exactly as the call found it."""
    if registry is None or snapshot is None:
        record["registry_restored"] = None
        return
    try:
        registry[:] = snapshot
        record["registry_restored"] = list(registry) == snapshot
        record["registry_entries_after_restore"] = len(registry)
    except Exception:
        record["registry_restored"] = False


def annotate_sampling_overlap(record: dict[str, Any], evidence: dict[str, Any]) -> dict[str, Any]:
    """Prove whether the activation actually ran *inside* the sampling window.

    ``evidence`` is the ``sampling_vae`` stage-pair record, whose ``owner_*``
    bounds are ``golden_sampling``.  Overlap is reported from monotonic
    timestamps rather than assumed, so "moved earlier but not hidden" stays
    visible instead of looking like a win.
    """
    if not isinstance(record, dict) or not isinstance(evidence, dict):
        return record
    start = record.get("activation_start_ns")
    end = record.get("activation_end_ns")
    sampling_start = evidence.get("owner_start_ns")
    sampling_end = evidence.get("owner_end_ns")
    if None in (start, end, sampling_start, sampling_end):
        record["sampling_active_at_start"] = None
        record["inside_sampling"] = None
        record["hidden_by_sampling_ms"] = None
        return record
    start_i, end_i = int(start), int(end)
    sampling_start_i, sampling_end_i = int(sampling_start), int(sampling_end)
    intersection = max(0, min(end_i, sampling_end_i) - max(start_i, sampling_start_i))
    record["sampling_active_at_start"] = bool(start_i < sampling_end_i)
    record["inside_sampling"] = bool(intersection > 0)
    record["hidden_by_sampling_ms"] = intersection / 1e6
    return record


__all__ = [
    "STATUS_ACTIVATED",
    "STATUS_ERROR",
    "STATUS_GUARD_FAILED",
    "STATUS_NOT_ATTEMPTED",
    "STATUS_POSTCONDITION_FAILED",
    "annotate_sampling_overlap",
    "capture_identity",
    "early_activate",
]