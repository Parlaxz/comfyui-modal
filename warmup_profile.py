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
from production_workflow import HASH_SCHEMA_VERSION, COMPILER_SCHEMA_VERSION, PRODUCTION_PLAN_SCHEMA_VERSION

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
    """Return a canonical warmup profile with production-identity fields.

    Includes restore-relevant fields plus production identity (output IDs,
    bypass IDs, direct_output_sink, metadata_mode) so that a same-stack
    non-production profile does NOT suppress writing a production profile.

    The identity fields are only included when production_enabled=True on
    the incoming profile (or when ``_production_enabled`` is passed).
    """
    if not isinstance(warmup_profile, dict):
        return {}
    # Always include model-stack fields the Modal worker uses at restore.
    _KEYS = frozenset({"mode", "unet", "clip1", "clip2", "vae", "clip_type"})
    stable = {k: warmup_profile.get(k) for k in _KEYS if k in warmup_profile}
    # Include production identity when enabled so a same-stack non-production
    # profile produces a different key and cannot suppress the production write.
    if warmup_profile.get("production_enabled"):
        stable["_production_enabled"] = True
        stable["_production_output_ids"] = str(
            sorted(warmup_profile.get("output_node_ids", []))
        )
        stable["_production_bypass_ids"] = str(
            sorted(warmup_profile.get("bypass_node_ids", []))
        )
        stable["_production_metadata_mode"] = str(
            warmup_profile.get("metadata_mode", "none")
        )
        stable["_production_direct_output_sink"] = bool(
            warmup_profile.get("direct_output_sink", True)
        )
        stable["_production_allow_rewrite"] = bool(
            warmup_profile.get("allow_direct_output_rewrite", True)
        )
        stable["_production_allow_rgthree"] = bool(
            warmup_profile.get("allow_rgthree_comparer_rewrite", True)
        )
        # Schema versions ensure the dedup key changes when the compiler
        # or hash schema version is bumped.
        stable["_production_compiler_version"] = warmup_profile.get("compiler_version", COMPILER_SCHEMA_VERSION)
        stable["_production_hash_schema_version"] = warmup_profile.get("hash_schema_version", HASH_SCHEMA_VERSION)
        stable["_production_plan_schema_version"] = warmup_profile.get("production_plan_schema_version", PRODUCTION_PLAN_SCHEMA_VERSION)
        # Production content hashes so two otherwise-identical production
        # payloads with different hashed workflow content produce distinct
        # dedup keys and trigger a setter call.
        stable["_production_source_workflow_hash"] = str(
            warmup_profile.get("source_workflow_hash", "")
        )
        stable["_production_compiled_workflow_hash"] = str(
            warmup_profile.get("compiled_workflow_hash", "")
        )
        stable["_production_plan_hash"] = str(
            warmup_profile.get("production_plan_hash", "")
        )
    return stable


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
    When production is enabled the warmup_profile carries production
    identity fields so the dedup key distinguishes production from
    non-production profiles with the same model stack.
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
        # Carry production identity into the warmup_profile so the
        # dedup key changes when production state changes.
        profile["production_enabled"] = True  # consumed by _normalize_stable_profile
        prod_out = production_options.get("output_node_ids", [])
        prod_byp = production_options.get("bypass_node_ids", [])
        # Always write production identity fields — not gated on truthy
        # output list — so even empty output_node_ids distinguishes production
        # from non-production profiles with the same model stack.
        if isinstance(prod_out, (list, tuple)):
            profile["output_node_ids"] = list(prod_out)
            profile["bypass_node_ids"] = list(prod_byp) if isinstance(prod_byp, (list, tuple)) else []
        else:
            profile["output_node_ids"] = []
            profile["bypass_node_ids"] = []
        profile["metadata_mode"] = str(production_options.get("metadata_mode", "none"))
        profile["direct_output_sink"] = bool(production_options.get("direct_output_sink", True))
        profile["allow_direct_output_rewrite"] = bool(production_options.get("allow_direct_output_rewrite", True))
        profile["allow_rgthree_comparer_rewrite"] = bool(production_options.get("allow_rgthree_comparer_rewrite", True))
        # Schema version fields on the profile so _normalize_stable_profile
        # includes them in the stable dedup key.
        profile["compiler_version"] = production_options.get("compiler_version", COMPILER_SCHEMA_VERSION)
        profile["hash_schema_version"] = production_options.get("hash_schema_version", HASH_SCHEMA_VERSION)
        profile["production_plan_schema_version"] = production_options.get("production_plan_schema_version", PRODUCTION_PLAN_SCHEMA_VERSION)
        # Production content hashes on the profile so the dedup key
        # changes when the compiled or hashed workflow changes, even if
        # the model stack / production option flags are identical.
        profile["source_workflow_hash"] = production_options.get("source_workflow_hash", "")
        profile["compiled_workflow_hash"] = production_options.get("compiled_workflow_hash", "")
        profile["production_plan_hash"] = production_options.get("production_plan_hash", "")
        # Production identity fields carried on the payload for
        # the activation/adapter to use in production.profile diagnostics.
        # Legacy prefixed aliases (backward compat during migration)
        payload["production_output_ids"] = list(prod_out) if isinstance(prod_out, (list, tuple)) else []
        payload["production_source_workflow_hash"] = production_options.get("source_workflow_hash", "")
        payload["production_compiled_workflow_hash"] = production_options.get("compiled_workflow_hash", "")
        payload["production_plan_hash"] = production_options.get("production_plan_hash", "")
        payload["production_compiler_version"] = production_options.get("compiler_version", COMPILER_SCHEMA_VERSION)
        # Direct un-prefixed aliases (canonical forward field names)
        payload["source_workflow_hash"] = production_options.get("source_workflow_hash", "")
        payload["compiled_workflow_hash"] = production_options.get("compiled_workflow_hash", "")
        payload["production_plan_hash"] = production_options.get("production_plan_hash", "")
        payload["compiler_version"] = production_options.get("compiler_version", COMPILER_SCHEMA_VERSION)
        payload["hash_schema_version"] = production_options.get("hash_schema_version", HASH_SCHEMA_VERSION)
        payload["production_plan_schema_version"] = production_options.get("production_plan_schema_version", PRODUCTION_PLAN_SCHEMA_VERSION)
        payload["output_node_ids"] = list(prod_out) if isinstance(prod_out, (list, tuple)) else []

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
        active_profile_build_ms   : float — wall-clock ms to construct payload & compute key.
        active_profile_dedup_status : str — final dedup/setter outcome (same semantics as
                                    status but always set even on early returns).
        active_profile_remote_call : int — 1 if a remote setter call was made, else 0.
        active_profile_remote_ms   : float — wall-clock ms spent awaiting the setter, or 0.
    """
    # Global dedup state (must be declared before any use)
    global _last_written_stable_profile

    # Measure build time from entry
    _build_start = time.time()

    # Default result (includes new honest fields)
    result: dict = {
        "status": "skipped",
        "profile_key": "",
        "remote_call": 0,
        "payload_bytes": 0,
        "changed": False,
        "active_profile_build_ms": 0.0,
        "active_profile_dedup_status": "skipped",
        "active_profile_remote_call": 0,
        "active_profile_remote_ms": 0.0,
    }

    if os.environ.get("DISABLE_ACTIVE_NEXT_WRITE"):
        result["active_profile_build_ms"] = round(
            (time.time() - _build_start) * 1000, 2
        )
        return result

    if not callable(setter) and setter is not None:
        # setter is not None and not callable — caller error
        result["status"] = "error"
        result["active_profile_dedup_status"] = "error"
        result["active_profile_build_ms"] = round(
            (time.time() - _build_start) * 1000, 2
        )
        return result

    # 1. Build activation payload
    production_options = production_options or {}
    payload = _build_activation_payload(workflow, workflow_hash, production_options)
    payload_bytes = len(json.dumps(payload, separators=(",", ":")))
    result["payload_bytes"] = payload_bytes

    # 2. Compute stable dedup key (model-stack only — no bundle_hash).
    #    prompt_bundle is still extracted inside _build_activation_payload for
    #    request-time/optimization use, but is NOT folded into the dedup key so
    #    prompt-only changes (same model stack, different prompt text) produce
    #    the same key and return unchanged without invoking the setter.
    warmup_profile = payload.get("warmup_profile", {})
    profile_key = _compute_stable_key(warmup_profile)

    result["profile_key"] = profile_key[:16]

    # Record build time (payload construction + key computation)
    _build_ms = round((time.time() - _build_start) * 1000, 2)
    result["active_profile_build_ms"] = _build_ms

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
        result["active_profile_dedup_status"] = "unchanged"
        return result

    # 5. No setter — dry run / test mode
    if setter is None:
        result["status"] = "skipped"
        result["active_profile_dedup_status"] = "skipped"
        return result

    # 6. Write via setter
    result["remote_call"] = 1
    result["active_profile_remote_call"] = 1
    _remote_start = time.time()
    try:
        activation_result = await setter(payload, workspace=workspace or None)
        _remote_ms = round((time.time() - _remote_start) * 1000, 2)
        result["active_profile_remote_ms"] = _remote_ms
        write_status = activation_result.get("status", "written")
        result["status"] = write_status
        result["active_profile_dedup_status"] = write_status
        result["changed"] = activation_result.get("changed", True)

        # Only advance dedup record on success
        if write_status not in ("error",):
            _last_written_stable_profile[dedup_key] = time.time()
    except Exception:
        _remote_ms = round((time.time() - _remote_start) * 1000, 2)
        result["active_profile_remote_ms"] = _remote_ms
        result["status"] = "error"
        result["active_profile_dedup_status"] = "error"
        # Do NOT advance dedup record on error

    return result
