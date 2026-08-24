"""E40 Lane B: single model-loader selection/observation authority.

One semantic model role (CLIP | UNET | VAE) has exactly one selection record:

  requested   - loader arm chosen by the resolved configuration
  effective   - loader arm the runtime intended to execute
  observed    - loader arm actually seen executing (from the central read
                tracker / arm-specific evidence)
  fallback_attempted / fallback_loader / fallback_reason

A fallback is NEVER nominal Golden execution: any fallback_attempted=True
must surface as RuntimeStatus=DEGRADED and reject the run from the nominal
performance cohort (enforced by tools/v2_control/validation.py).

This module is a passive registry: loader arms report; nothing here selects
a loader. Requested arms are derived exclusively from
``comfymodal_runtime.config_authority`` so an inherited environment variable
cannot change the reported truth without appearing in the resolved config.
"""

from __future__ import annotations

import threading

ROLES = ("clip", "unet", "vae")

# Canonical semantic loader-arm vocabulary per role. Raw tracker strings are
# normalized into these names so requested/effective/observed comparisons
# compare semantics, not spelling.
_CLIP_ARMS = ("snapshot_resident", "qd4_reader", "fastsafe_hydration",
              "fastsafetensors_direct_gpu", "staged_hydration",
              "speculative_clip", "native_comfy", "golden_qd4")
_UNET_ARMS = ("fastsafetensors", "meta_direct", "cpu_snapshot_native",
              "native_comfy", "golden_qd4")
_VAE_ARMS = ("policy_v1", "native_comfy", "golden_qd4")


def normalize_observed(role: str, raw: str) -> str:
    """Map a raw loader_type/owner string onto the canonical arm name."""
    text = str(raw or "").lower()
    if "golden_qd4" in text or "golden-qd4" in text:
        return "golden_qd4"
    if role == "clip":
        if "snapshot_resident" in text or (
            "snapshot" in text and "native" not in text
        ):
            return "snapshot_resident"
        if text == "fastsafetensors_direct_gpu" or "direct_gpu" in text:
            return "fastsafetensors_direct_gpu"
        if "qd" in text:
            return "qd4_reader"
        if "speculative" in text:
            return "speculative_clip"
        if "staged" in text:
            return "staged_hydration"
        if "fastsafe" in text or "hydrat" in text or "fast_hydration" in text:
            return "fastsafe_hydration"
        return "native_comfy"
    if role == "unet":
        if "meta" in text and "direct" in text:
            return "meta_direct"
        if "fastsafe" in text:
            return "fastsafetensors"
        if "cpu_snapshot" in text or "snapshot" in text:
            return "cpu_snapshot_native"
        return "native_comfy"
    if role == "vae":
        if "policy" in text or "v1" in text:
            return "policy_v1"
        return "native_comfy"
    return str(raw or "")


_LOCK = threading.Lock()
_SELECTIONS: dict[str, dict] = {}


def _blank() -> dict:
    return {
        "requested": "",
        "effective": "",
        "observed": "",
        "fallback_attempted": False,
        "fallback_loader": "",
        "fallback_reason": "",
    }


def reset_for_run() -> None:
    """Clear per-run selection state (call once per request/run start)."""
    with _LOCK:
        _SELECTIONS.clear()


def set_requested(role: str, loader: str) -> None:
    if role not in ROLES or not loader:
        return
    with _LOCK:
        _SELECTIONS.setdefault(role, _blank())["requested"] = str(loader)


def set_effective(role: str, loader: str) -> None:
    if role not in ROLES or not loader:
        return
    with _LOCK:
        _SELECTIONS.setdefault(role, _blank())["effective"] = str(loader)


def record_observed(role: str, loader: str, *, fallback_attempted: bool = False,
                    fallback_loader: str = "", fallback_reason: str = "") -> None:
    """Record the loader arm actually seen executing for *role*.

    ``loader`` may be a raw tracker string; it is normalized onto the
    canonical arm vocabulary for the role before recording.
    """
    if role not in ROLES:
        return
    canonical = normalize_observed(role, loader)
    if not canonical:
        return
    with _LOCK:
        entry = _SELECTIONS.setdefault(role, _blank())
        # R42A terminal-fallback stickiness: once a real native fallback was
        # recorded for this role, later observations (including a late Golden
        # success) may never erase it.  The request can never become nominal
        # again after a terminal native fallback executed.
        if entry.get("fallback_attempted"):
            return
        # First observation wins unless a fallback explicitly supersedes it:
        # the first successful arm is the effective one; later recovery arms
        # are recorded as fallbacks, never as the planned loader.
        # R42: when the observed arm MATCHES the effective (planned) loader,
        # always overwrite + clear stale PROVISIONAL state — a transient
        # native observation before the Golden path succeeded must not
        # poison the final contract.  A recorded fallback_attempted=True is
        # terminal and handled above (never cleared here).
        if canonical == entry.get("effective"):
            entry["observed"] = canonical
            entry["fallback_attempted"] = False
            entry["fallback_loader"] = ""
            entry["fallback_reason"] = ""
        elif not entry.get("observed"):
            entry["observed"] = canonical
            if fallback_attempted:
                entry["fallback_attempted"] = True
                entry["fallback_loader"] = canonical
                if fallback_reason:
                    entry["fallback_reason"] = str(fallback_reason)[:300]
        elif fallback_attempted and canonical != entry.get("observed"):
            entry["fallback_attempted"] = True
            entry["fallback_loader"] = canonical
            if fallback_reason:
                entry["fallback_reason"] = str(fallback_reason)[:300]


def seed_from_resolved(resolved_requested: dict[str, str]) -> None:
    """Seed requested+effective per role from the config authority.

    ``resolved_requested`` maps role -> semantic loader name as produced by
    ``config_authority.requested_loader``. Effective starts equal to
    requested; only an explicit runtime re-selection may change it, and any
    divergence must be recorded via :func:`record_observed` fallback fields.
    """
    for role, loader in (resolved_requested or {}).items():
        set_requested(role, loader)
        set_effective(role, loader)


def snapshot() -> dict:
    """Emit the pinned validator contract block (missing roles omitted)."""
    with _LOCK:
        return {role: dict(_SELECTIONS[role]) for role in ROLES if role in _SELECTIONS}


def mismatches() -> list[str]:
    """Human-readable reasons for requested/effective/observed divergence."""
    reasons: list[str] = []
    with _LOCK:
        for role, entry in sorted(_SELECTIONS.items()):
            if entry.get("fallback_attempted"):
                reasons.append(
                    f"loader_fallback_{role}:{entry.get('requested') or '?'}"
                    f"->{entry.get('fallback_loader') or '?'}"
                )
            if entry.get("observed") and entry.get("effective") \
                    and entry["observed"] != entry["effective"]:
                reasons.append(f"loader_observed_mismatch_{role}")
            if entry.get("requested") and entry.get("effective") \
                    and entry["requested"] != entry["effective"]:
                reasons.append(f"loader_effective_mismatch_{role}")
            if entry.get("requested") and not entry.get("observed"):
                reasons.append(f"loader_unobserved_{role}")
    return reasons
