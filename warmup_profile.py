"""Shared active-next warmup-profile preparation.

Both the normal ComfyUI graph path (``__init__._execute_job``) and the
Studio run path (``studio_run_adapter._schedule_and_start`` →
``LocalRemoteInvoker.run_cell``) call ``prepare_active_next_profile``
so that model-stack extraction, profile-token generation, prompt-bundle
injection, and workspace-scoped dedup are unified in a single
dependency-light helper.

The helper never advances its dedup record when the ``setter`` call
fails — the caller is responsible for handling the error and the
dedup record is only updated on success.
"""

import hashlib
import json
import os
import time
import uuid

from workflow_metadata import extract_warmup_stack, stack_to_warmup_profile

# ── Module-global dedup state ───────────────────────────────────────────
# Shares the same semantics as __init__._last_written_stable_profile.
# Keyed by (workspace_id, stable_key) → last_write_timestamp.
_last_written_stable_profile: dict[tuple[str, str], float] = {}

# Default TTL (1 hour, matching __init__._ACTIVE_NEXT_PROFILE_TTL_S).
_ACTIVE_NEXT_PROFILE_TTL_S = int(os.environ.get(
    "COMFYMODAL_ACTIVE_NEXT_PROFILE_TTL_S", "3600",
))
_ACTIVE_NEXT_REFRESH_MIN_S = 30.0


# ── Helpers ─────────────────────────────────────────────────────────────

def _ws_id(workspace: dict | None) -> str:
    """Extract a stable workspace ID string (or ``"__default__"``)."""
    if isinstance(workspace, dict):
        wid = workspace.get("id") or workspace.get("workspace_id") or ""
        if wid:
            return str(wid)
    return "__default__"


def _normalize_stable_profile(warmup_profile: dict | None) -> dict:
    """Return a canonical warmup profile with only restore-relevant fields.

    Strips UUIDs, timestamps, workflow_hash, output nodes, and
    production-mode settings so identical model stacks always produce
    the same key regardless of workflow display state.
    """
    if not isinstance(warmup_profile, dict):
        return {}
    # Keep mode, unet, clip1, clip2, vae, clip_type — the fields the
    # Modal worker actually uses at restore time.
    _KEYS = frozenset({"mode", "unet", "clip1", "clip2", "vae", "clip_type"})
    return {k: warmup_profile.get(k) for k in _KEYS if k in warmup_profile}


def _compute_stable_key(warmup_profile: dict) -> str:
    """Return a deterministic hash of the restore-relevant profile fields."""
    stable = _normalize_stable_profile(warmup_profile)
    return hashlib.sha256(
        json.dumps(stable, sort_keys=True, separators=(",", ":"),
                   ensure_ascii=False).encode("utf-8")
    ).hexdigest()


def build_activation_payload(workflow, workflow_hash, production_options=None):
    """Public alias for compatibility with __init__ imports."""
    return _build_activation_payload(workflow, workflow_hash, production_options)


def _build_activation_payload(
    workflow: dict,
    workflow_hash: str,
    production_options: dict | None = None,
) -> dict:
    """Build the activation payload dict sent to ``set_active_warmup_profile``.

    Mirrors the body of ``__init__._build_next_warmup_activation``.
    """
    stack = extract_warmup_stack(workflow) if isinstance(workflow, dict) else {}
    profile = stack_to_warmup_profile(stack)
    # Normalize: collapse duplicate CLIP entries
    if profile and isinstance(profile, dict):
        p = dict(profile)
        if p.get("clip2") == p.get("clip1"):
            p["clip2"] = ""
        profile = p
    now = time.time()
    payload: dict = {
        "profile_token": str(uuid.uuid4()),
        "validation_token": str(uuid.uuid4()),
        "workflow_hash": workflow_hash,
        "created_at": now,
        "expires_at": now + _ACTIVE_NEXT_PROFILE_TTL_S,
        "mode": profile.get("mode", "none") if profile else "none",
        "model_stack": stack,
        "warmup_profile": profile,
        "disable_warmup": not bool(profile),
        "selected_at": None,
        "preflight_validated": True,
    }
    if production_options and production_options.get("enabled"):
        payload["production_enabled"] = True
        payload["production_profile_version"] = 1

    # Exact prompt bundle extraction
    _exact_or_persistent = (
        os.environ.get("COMFYMODAL_EXACT_CLIP_PREFILL", "1") == "1"
        or os.environ.get("COMFYMODAL_PERSISTENT_CLIP_CACHE", "0") == "1"
    )
    if _exact_or_persistent:
        try:
            from optimizations import extract_safe_prompt_bundle
            bundle_res = extract_safe_prompt_bundle(workflow)
            if bundle_res.get("eligible") and bundle_res.get("bundle"):
                payload["prompt_bundle"] = bundle_res["bundle"]
        except Exception:
            pass

    return payload


# ── Public entry point ──────────────────────────────────────────────────

async def prepare_active_next_profile(
    workflow: dict,
    workflow_hash: str,
    *,
    production_options: dict | None = None,
    workspace: dict | None = None,
    setter: object | None = None,
) -> dict:
    """Prepare and (if changed) write an active-next warmup profile.

    Parameters
    ----------
    workflow : dict
        The fully resolved execution workflow (after all overrides /
        injections applied).
    workflow_hash : str
        Stable workflow hash for the activation payload.
    production_options : dict or None
        Options dict with optional ``enabled`` key for production mode.
    workspace : dict or None
        Current workspace dict (used for dedup scoping and passed to
        the remote setter).
    setter : async callable or None
        An ``async setter(payload, workspace=None)`` used to persist
        the profile remotely.  When ``None``, the remote write is
        skipped entirely (test mode / dry run).

    Returns a dict with keys:
        status       : str — one of ``"skipped"``, ``"unchanged"``,
                       ``"written"``, ``"error"``.
        profile_key  : str — the stable dedup key.
        remote_call  : int — 1 if a remote setter call was made, else 0.
        payload_bytes: int — byte length of the serialised payload.
        changed      : bool — whether the remote reported a change.
    """
    # Global dedup state (must be declared before any use)
    global _last_written_stable_profile

    # Default result
    result: dict = {
        "status": "skipped",
        "profile_key": "",
        "remote_call": 0,
        "payload_bytes": 0,
        "changed": False,
    }

    if os.environ.get("DISABLE_ACTIVE_NEXT_WRITE"):
        return result

    if not callable(setter) and setter is not None:
        # setter is not None and not callable — caller error
        result["status"] = "error"
        return result

    # 1. Build activation payload
    production_options = production_options or {}
    payload = _build_activation_payload(workflow, workflow_hash, production_options)
    payload_bytes = len(json.dumps(payload, separators=(",", ":")))
    result["payload_bytes"] = payload_bytes

    # 2. Compute stable dedup key (pre-bundle)
    warmup_profile = payload.get("warmup_profile", {})
    profile_key = _compute_stable_key(warmup_profile)

    # Fold prompt bundle hash into key when present
    prompt_bundle = payload.get("prompt_bundle")
    if isinstance(prompt_bundle, dict):
        bundle_hash = str(prompt_bundle.get("bundle_hash", ""))
        if bundle_hash:
            profile_key = hashlib.sha256(
                (profile_key + ":" + bundle_hash).encode("utf-8")
            ).hexdigest()

    # Return the final (bundle-inclusive) key
    result["profile_key"] = profile_key[:16]

    # 3. Workspace-scoped dedup
    ws_id = _ws_id(workspace)
    dedup_key = (ws_id, profile_key)

    # Prune stale entries
    effective_ttl_s = max(2.0, float(_ACTIVE_NEXT_PROFILE_TTL_S))
    if len(_last_written_stable_profile) > 100:
        cutoff = time.time() - effective_ttl_s * 2
        _last_written_stable_profile = {
            k: v for k, v in _last_written_stable_profile.items()
            if v >= cutoff
        }

    # 4. Check if we can skip (key match + within refresh window)
    refresh_after_s = min(
        effective_ttl_s * 0.5,
        effective_ttl_s - 1.0,
    )
    refresh_after_s = max(1.0, refresh_after_s)

    last_write_ts = _last_written_stable_profile.get(dedup_key, 0.0)
    if last_write_ts > 0.0 and (time.time() - last_write_ts) < refresh_after_s:
        result["status"] = "unchanged"
        return result

    # 5. No setter — dry run / test mode
    if setter is None:
        result["status"] = "skipped"
        return result

    # 6. Write via setter
    result["remote_call"] = 1
    try:
        activation_result = await setter(payload, workspace=workspace or None)
        write_status = activation_result.get("status", "written")
        result["status"] = write_status
        result["changed"] = activation_result.get("changed", True)

        # Only advance dedup record on success
        if write_status not in ("error",):
            _last_written_stable_profile[dedup_key] = time.time()
    except Exception:
        result["status"] = "error"
        # Do NOT advance dedup record on error

    return result
