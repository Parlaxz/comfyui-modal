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

# ── Module-global dedup cache ──────────────────────────────────────────
# Keyed by (app_identity, workspace_id, stable_key) → record.
# Record: {"ts": float, "token": str, "stable_key_short": str}
_last_stable_profile_cache: dict[tuple[str, str, str], dict] = {}
_last_cache_app_identity: str = ""
_last_cache_ws_id: str = ""


def _reset_last_stable_profile_cache() -> None:
    """Clear the process-local stable profile cache (test / teardown only)."""
    global _last_stable_profile_cache, _last_cache_app_identity, _last_cache_ws_id
    global _last_prefill_identity_map
    _last_stable_profile_cache.clear()
    _last_prefill_identity_map.clear()
    _last_cache_app_identity = ""
    _last_cache_ws_id = ""


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
    """Return only restore-relevant identity fields (model stack + config).

    Follows the same mode-specific rules as
    ``__init__._normalize_stable_warmup_profile``:

    * Always includes ``mode`` and ``disable_warmup``.
    * ``mode=checkpoint`` preserves ``checkpoint`` and clears split fields.
    * ``mode=split`` preserves ``unet``/``clip1``/``clip2``/``vae``/``clip_type``
      and clears checkpoint.
    * Duplicate ``clip2 == clip1`` is collapsed to ``""``.
    * Loader configuration fields (e.g. ``weight_dtype``, ``unet_dtype``) are
      included only when **explicitly present** in the profile.

    Excludes all production hashes, output/bypass IDs, metadata/direct-output
    flags, schema/compiler versions, seeds, tokens, timestamps, and UI fields.
    These are preserved in the full payload for tracing but never affect the
    stable restore key.
    """
    if not isinstance(warmup_profile, dict):
        warmup_profile = {}
    stable: dict[str, object] = {
        "mode": str(warmup_profile.get("mode", "")).strip(),
        "checkpoint": "",
        "unet": "",
        "clip1": "",
        "clip2": "",
        "vae": "",
        "clip_type": "",
        "disable_warmup": bool(warmup_profile.get("disable_warmup", False)),
    }
    _mode = stable["mode"]
    if _mode == "checkpoint":
        stable["checkpoint"] = str(warmup_profile.get("checkpoint", "")).strip()
    elif _mode == "split":
        stable["unet"] = str(warmup_profile.get("unet", "")).strip()
        stable["clip1"] = str(warmup_profile.get("clip1", "")).strip()
        stable["clip2"] = str(warmup_profile.get("clip2", "")).strip()
        stable["vae"] = str(warmup_profile.get("vae", "")).strip()
        stable["clip_type"] = str(warmup_profile.get("clip_type", "")).strip()
    # Collapse duplicate CLIP
    if stable["clip2"] and stable["clip2"] == stable["clip1"]:
        stable["clip2"] = ""
    # Include loader-config fields only when explicitly present
    for _k in ("weight_dtype", "unet_dtype", "model_structure"):
        _v = warmup_profile.get(_k)
        if _v is not None and _v != "":
            stable[_k] = _v
    return stable


def _compute_stable_key(warmup_profile: dict, *, bundle_hash: str | None = None) -> str:
    """Return a deterministic hash of the restore-relevant profile fields.

    When *bundle_hash* is provided (and non-empty) the prompt-bundle
    digest participates in the key, so a changed eligible prompt text
    produces a different restore identity.
    """
    stable = _normalize_stable_profile(warmup_profile)
    if bundle_hash:
        stable["bundle_hash"] = bundle_hash
    return hashlib.sha256(
        json.dumps(stable, sort_keys=True, separators=(",", ":"),
                   ensure_ascii=False).encode("utf-8")
    ).hexdigest()


def _app_identity() -> str:
    """Current app identity used for cache scoping.

    Prefers ``COMFYMODAL_V2_APP_NAME`` to match canonical/transport scoping,
    then falls back to ``COMFYMODAL_APP_NAME`` for backward compatibility,
    then to ``"comfyui"``.  This ensures app scoping never diverges between
    the warmup-profile cache and the V2 transport lookup.
    """
    app = os.environ.get("COMFYMODAL_V2_APP_NAME", "").strip()
    if not app:
        app = os.environ.get("COMFYMODAL_APP_NAME", "").strip()
    return app or "comfyui"


def _check_cache_identity(ws_id: str = "") -> None:
    """Clear the process-local cache when the app or workspace identity changes.

    The caller should pass ``ws_id`` (from ``_ws_id(workspace)``) to ensure
    a workspace switch invalidates stale cache entries for the prior workspace.
    When called without arguments (e.g. from tests) only the app identity
    is checked.

    Note: the initial sentinel values are ``""`` so that every identity
    transition — including the first call from ``""`` to a real identity —
    unambiguously clears stale entries.  The ``ws_id and`` guard preserves
    the no-argument test path without skipping real workspace transitions.
    """
    global _last_cache_app_identity, _last_cache_ws_id, _last_stable_profile_cache
    current_app = _app_identity()
    changed = False
    if _last_cache_app_identity != current_app:
        changed = True
    if ws_id and _last_cache_ws_id != ws_id:
        changed = True
    if changed:
        _last_stable_profile_cache.clear()
    _last_cache_app_identity = current_app
    if ws_id:
        _last_cache_ws_id = ws_id


def _exact_prefill_enabled() -> bool:
    """True when exact CLIP prefill (bundle-hash identity participation) is active.

    Default ``"1"`` matches ``_build_activation_payload`` and comfyapp env defaults
    so that prompt-text changes by default produce a different restore identity
    and trigger a new warmup publication.
    """
    return os.environ.get("COMFYMODAL_EXACT_CLIP_PREFILL", "1") == "1"


def _persistent_cache_enabled() -> bool:
    """True when persistent CLIP cache is enabled."""
    return os.environ.get("COMFYMODAL_PERSISTENT_CLIP_CACHE", "0") == "1"


def _emit_publish_log(decision: str, stable_key_short: str) -> None:
    """Emit exactly one concise line per prepare call."""
    print(
        f"[active_profile.publish] "
        f"decision={decision} "
        f"stable_key={stable_key_short} "
        f"storage=runtime_config"
    )


def _finalize_timing(result: dict, build_start: float) -> None:
    """Set timing fields at return.

    Decomposes the active-profile operation into four non-overlapping
    components:

      total_ms = cache_lookup_ms + checker_ms + setter_ms + local_ms

    * *cache_lookup_ms* — time to probe the process-local dedup cache.
    * *checker_ms* — time to call the remote read-only identity seam.
    * *setter_ms* — time to call the remote writer.
    * *local_ms* — everything else (extraction, hashing, payload build).

    On cache-hit paths, cache_lookup_ms is nonzero while checker and
    setter are zero.  On checker-matched paths, checker_ms is nonzero,
    setter is zero.  On setter-written paths, setter_ms is nonzero.
    Exceptions/timeouts never advance the cache and never contribute
    nonzero checker/setter on the subsequent retry.
    """
    total_ms = round((time.time() - build_start) * 1000, 2)
    result["active_profile_total_ms"] = total_ms
    cache_lookup_ms = result.get("cache_lookup_ms", 0.0)
    checker_ms = result.get("active_profile_checker_ms", 0.0)
    setter_ms = result.get("active_profile_setter_ms", 0.0)
    local_ms = round(max(0.0, total_ms - max(0.0, cache_lookup_ms) - max(0.0, checker_ms) - max(0.0, setter_ms)), 2)
    result["active_profile_local_ms"] = local_ms
    result["local_active_profile_prepare_ms"] = local_ms
    result["active_profile_cache_lookup_ms"] = cache_lookup_ms


# ── Identity-change tracking ──────────────────────────────────────────
_last_prefill_identity_map: dict[tuple[str, str], dict] = {}


def _get_known_identity(ws_id: str = "") -> dict:
    """Return last known identity record for (app, ws) or {}."""
    app_id = _app_identity()
    return _last_prefill_identity_map.get((app_id, ws_id), {})


def _update_known_identity(ws_id: str, model_profile_key: str, prefill_key: str) -> None:
    """Record successfully known identity for (app, ws)."""
    app_id = _app_identity()
    _last_prefill_identity_map[(app_id, ws_id)] = {
        "model_profile_key": model_profile_key,
        "prefill_key": prefill_key,
    }


def build_activation_payload(workflow, workflow_hash, production_options=None):
    """Public alias for compatibility with __init__ imports."""
    return _build_activation_payload(workflow, workflow_hash, production_options)


def _build_activation_payload(
    workflow: dict,
    workflow_hash: str,
    production_options: dict | None = None,
    *,
    precomputed: dict | None = None,
) -> dict:
    """Build the activation payload dict sent to ``set_active_warmup_profile``.

    Mirrors the body of ``__init__._build_next_warmup_activation``.
    Generates UUIDs for ``profile_token`` and ``validation_token``.
    Production identity fields are carried on the payload for tracing
    and diagnostics but do NOT participate in the stable restore key.

    When *precomputed* is provided (from ``prepare_active_next_profile``),
    the stack and bundle result are reused rather than re-extracted.
    """
    if precomputed is not None:
        stack = precomputed["stack"]
    else:
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
        # Production identity fields are preserved on the profile/payload
        # for tracing and diagnostics.  They do NOT participate in the
        # stable restore key (see _normalize_stable_profile).
        profile["production_enabled"] = True
        prod_out = production_options.get("output_node_ids", [])
        prod_byp = production_options.get("bypass_node_ids", [])
        # Always write production identity fields for tracing/diagnostics.
        # These do NOT participate in the stable restore key (production
        # and non-production profiles with the same model stack share the
        # same restore key now).
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
        # Schema version fields on the profile for tracing diagnostics.
        # NOT consumed by _normalize_stable_profile (stable restore key).
        profile["compiler_version"] = production_options.get("compiler_version", COMPILER_SCHEMA_VERSION)
        profile["hash_schema_version"] = production_options.get("hash_schema_version", HASH_SCHEMA_VERSION)
        profile["production_plan_schema_version"] = production_options.get("production_plan_schema_version", PRODUCTION_PLAN_SCHEMA_VERSION)
        # Production content hashes on the profile for tracing/reporting.
        # NOT consumed by _normalize_stable_profile (stable restore key
        # includes only model identity, never workflow content hashes).
        profile["source_workflow_hash"] = production_options.get("source_workflow_hash", "")
        profile["compiled_workflow_hash"] = production_options.get("compiled_workflow_hash", "")
        profile["production_plan_hash"] = production_options.get("production_plan_hash", "")
        # Production identity fields carried on the payload for tracing.
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

    # Exact prompt bundle extraction (reuse precomputed when available)
    if precomputed is not None and precomputed.get("bundle_result") is not None:
        bundle_res = precomputed["bundle_result"]
        if bundle_res.get("eligible") and bundle_res.get("bundle"):
            payload["prompt_bundle"] = bundle_res["bundle"]
    else:
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


# ── Lightweight key computation (no caching, no remote) ────────────────

def compute_profile_identity_keys(workflow: dict) -> tuple[str, str]:
    """Compute ``model_profile_key`` and ``prefill_key`` from *workflow*.

    Pure local computation with no side effects and no remote calls.
    Produces the same values that ``prepare_active_next_profile`` would
    produce from the same input.  Used by ``canonical_execution.execute_plan``
    to derive cache keys **before** deciding whether to enter the full
    profile-preparation path.

    Returns
    -------
    ``(model_profile_key: str, prefill_key: str)``
    """
    stack = extract_warmup_stack(workflow) if isinstance(workflow, dict) else {}
    profile = stack_to_warmup_profile(stack)
    if profile and isinstance(profile, dict):
        p = dict(profile)
        if p.get("clip2") == p.get("clip1"):
            p["clip2"] = ""
        profile = p
    normalized = _normalize_stable_profile(profile)
    model_profile_key = hashlib.sha256(
        json.dumps(normalized, sort_keys=True, separators=(",", ":"),
                   ensure_ascii=False).encode("utf-8")
    ).hexdigest()
    prefill_key = ""
    _need_bundle = _exact_prefill_enabled() or _persistent_cache_enabled()
    if _need_bundle:
        try:
            from optimizations import extract_safe_prompt_bundle
            bundle_res = extract_safe_prompt_bundle(workflow)
            if bundle_res.get("eligible") and bundle_res.get("bundle"):
                bundle_hash = bundle_res["bundle"].get("bundle_hash") or ""
                if bundle_hash and _exact_prefill_enabled():
                    prefill_key = bundle_hash
        except Exception:
            pass
    return model_profile_key, prefill_key


# ── Public entry point ──────────────────────────────────────────────────

async def prepare_active_next_profile(
    workflow: dict,
    workflow_hash: str,
    *,
    production_options: dict | None = None,
    workspace: dict | None = None,
    setter: object | None = None,
    checker: object | None = None,
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
    checker : async callable or None
        An ``async checker(stable_key, workspace=None)`` used as a
        read-only identity seam to check whether the durable runtime-config
        volume already carries a profile matching *stable_key*.
        When the checker returns ``{"matched": True, ...}`` the setter
        is skipped entirely.  When ``None`` (or errored) the setter is
        called as usual (fail-open).  Expected signature::

            async def checker(
                stable_key: str,
                *,
                workspace: dict | None = None,
            ) -> dict:
                ...

    Returns a dict with keys:
        status       : str — one of ``"skipped"``, ``"unchanged"``,
                       ``"written"``, ``"error"``.
        profile_key  : str — the stable dedup key (first 16 hex chars).
        remote_call  : int — 1 if a remote setter call was made, else 0.
        payload_bytes: int — byte length of the serialised payload.
        changed      : bool — whether the remote reported a change.
        active_profile_build_ms   : float — wall-clock ms to construct payload & compute key.
        active_profile_dedup_status : str — final dedup/setter outcome (same semantics as
                                    status but always set even on early returns).
        active_profile_remote_call : int — 1 if a remote setter call was made, else 0.
        active_profile_remote_ms   : float — wall-clock ms spent awaiting the setter, or 0.
        local_active_profile_prepare_ms : float — alias for active_profile_build_ms.
        active_profile_publish_decision : str — ``"published"`` or ``"skipped_unchanged"``.
        active_profile_stable_key       : str — the full stable key hex digest.
        active_profile_token            : str — the profile token (from cache or newly created).
    """
    global _last_stable_profile_cache

    # Measure build time from entry
    _build_start = time.time()

    # Default result (includes all backward-compat keys + new keys)
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
        # New fields (lane A)
        "local_active_profile_prepare_ms": 0.0,
        "active_profile_publish_decision": "skipped_unchanged",
        "active_profile_stable_key": "",
        "active_profile_token": "",
        # New unambiguous timing fields
        "active_profile_local_ms": 0.0,
        "active_profile_cache_lookup_ms": 0.0,
        "active_profile_checker_ms": 0.0,
        "active_profile_setter_ms": 0.0,
        "active_profile_total_ms": 0.0,
        "cache_lookup_ms": 0.0,
        # Reuse booleans
        "profile_cache_hit": False,
        "profile_checker_performed": False,
        "profile_checker_matched": False,
        "profile_setter_performed": False,
        # Identity-change report fields
        "model_profile_key": "",
        "prefill_key": "",
        "model_identity_changed": False,
        "prefill_identity_changed": False,
    }

    if os.environ.get("DISABLE_ACTIVE_NEXT_WRITE"):
        _ms = round((time.time() - _build_start) * 1000, 2)
        result["active_profile_build_ms"] = _ms
        result["local_active_profile_prepare_ms"] = _ms
        _finalize_timing(result, _build_start)
        return result

    if not callable(setter) and setter is not None:
        # setter is not None and not callable — caller error
        result["status"] = "error"
        result["active_profile_dedup_status"] = "error"
        result["active_profile_publish_decision"] = "published"
        _ms = round((time.time() - _build_start) * 1000, 2)
        result["active_profile_build_ms"] = _ms
        result["local_active_profile_prepare_ms"] = _ms
        _finalize_timing(result, _build_start)
        _emit_publish_log("published", "")
        return result

    # ── 1. Extract warmup profile from workflow ─────────────────────
    stack = extract_warmup_stack(workflow) if isinstance(workflow, dict) else {}
    profile = stack_to_warmup_profile(stack)
    if profile and isinstance(profile, dict):
        p = dict(profile)
        if p.get("clip2") == p.get("clip1"):
            p["clip2"] = ""
        profile = p

    # ── 2. Extract prompt bundle (exact prefill or persistent cache) ────
    bundle_res: dict | None = None
    bundle_hash: str | None = None
    _need_bundle = _exact_prefill_enabled() or _persistent_cache_enabled()
    if _need_bundle:
        try:
            from optimizations import extract_safe_prompt_bundle
            bundle_res = extract_safe_prompt_bundle(workflow)
            if bundle_res.get("eligible") and bundle_res.get("bundle"):
                bundle_hash = bundle_res["bundle"].get("bundle_hash") or None
        except Exception:
            pass

    # ── 3a. Compute model_profile_key and prefill_key ───────────────
    normalized = _normalize_stable_profile(profile)
    model_profile_key = hashlib.sha256(
        json.dumps(normalized, sort_keys=True, separators=(",", ":"),
                   ensure_ascii=False).encode("utf-8")
    ).hexdigest()
    prefill_key = bundle_hash if (bundle_hash and _exact_prefill_enabled()) else ""

    # ── 3b. Compute stable restore key (bundle participates only when exact prefill) ──
    stable_bundle_hash = bundle_hash if _exact_prefill_enabled() else None
    stable_key = _compute_stable_key(profile, bundle_hash=stable_bundle_hash)
    stable_key_short = stable_key[:16]
    result["profile_key"] = stable_key_short
    result["active_profile_stable_key"] = stable_key

    _prepare_ms = round((time.time() - _build_start) * 1000, 2)
    result["active_profile_build_ms"] = _prepare_ms

    # ── 3c. Build analysis for payload reuse ────────────────────
    _analysis = {
        "stack": stack,
        "bundle_result": bundle_res,
        "model_profile_key": model_profile_key,
        "prefill_key": prefill_key,
    }

    # ── 3d. Identity-change flags ─────────────────────────
    ws_id = _ws_id(workspace)
    _check_cache_identity(ws_id)
    app_id = _app_identity()
    known = _get_known_identity(ws_id)
    first_unknown = not bool(known)
    model_identity_changed = (
        not first_unknown and model_profile_key != known.get("model_profile_key", "")
    )
    prefill_identity_changed = (
        not first_unknown and prefill_key != known.get("prefill_key", "")
    )
    result["model_profile_key"] = model_profile_key
    result["prefill_key"] = prefill_key
    result["model_identity_changed"] = model_identity_changed
    result["prefill_identity_changed"] = prefill_identity_changed

    # ── 4. Check bounded process-local cache BEFORE token/payload creation ──
    cache_key = (app_id, ws_id, stable_key)

    # Prune stale entries
    effective_ttl_s = max(2.0, float(_ACTIVE_NEXT_PROFILE_TTL_S))
    if len(_last_stable_profile_cache) > 100:
        cutoff = time.time() - effective_ttl_s * 2
        _last_stable_profile_cache = {
            k: v for k, v in _last_stable_profile_cache.items()
            if v.get("ts", 0) >= cutoff
        }

    # 4a. Cache hit → return cached token, no UUID generation, no setter
    refresh_after_s = max(1.0, min(
        effective_ttl_s * 0.5,
        effective_ttl_s - 1.0,
    ))
    _cache_lookup_start_ns = time.perf_counter_ns()
    cached = _last_stable_profile_cache.get(cache_key)
    _cache_lookup_ms = round((time.perf_counter_ns() - _cache_lookup_start_ns) / 1_000_000, 3)
    result["cache_lookup_ms"] = _cache_lookup_ms
    if cached is not None and (time.time() - cached["ts"]) < refresh_after_s:
        result["status"] = "unchanged"
        result["active_profile_dedup_status"] = "unchanged"
        result["active_profile_publish_decision"] = "skipped_unchanged"
        result["active_profile_token"] = cached["token"]
        result["model_identity_changed"] = False
        result["prefill_identity_changed"] = False
        result["profile_cache_hit"] = True
        result["profile_checker_performed"] = False
        result["profile_setter_performed"] = False
        _finalize_timing(result, _build_start)
        _emit_publish_log("skipped_unchanged", stable_key_short)
        return result

    # 4b. No setter — dry run / test mode (no cache advance)
    if setter is None:
        result["status"] = "skipped"
        result["active_profile_dedup_status"] = "skipped"
        result["active_profile_publish_decision"] = "skipped_unchanged"
        result["profile_cache_hit"] = False
        result["profile_checker_performed"] = False
        result["profile_setter_performed"] = False
        _finalize_timing(result, _build_start)
        _emit_publish_log("skipped_unchanged", stable_key_short)
        return result

    # 4c. Cold-safe check via read-only identity seam (volume-backed).
    #     When the checker confirms the volume already carries a profile
    #     with this stable key, skip the setter entirely.  The process-
    #     local cache is populated so subsequent requests in the same
    #     process hit step 4a without any remote call.
    if checker is not None:
        print(f"[warmup_profile] phase=checker_start stable_key={stable_key_short}", flush=True)
        _checker_start = time.time()
        try:
            _check_result = await checker(stable_key, workspace=workspace)
            _checker_ms = round((time.time() - _checker_start) * 1000, 2)
            result["active_profile_checker_ms"] = _checker_ms
            result["profile_checker_performed"] = True
            if isinstance(_check_result, dict) and _check_result.get("matched"):
                _token = _check_result.get("profile_token", "")
                result["status"] = "unchanged"
                result["active_profile_dedup_status"] = "unchanged"
                result["active_profile_publish_decision"] = "skipped_unchanged"
                result["active_profile_token"] = _token
                result["profile_cache_hit"] = False
                result["profile_checker_performed"] = True
                result["profile_checker_matched"] = True
                result["profile_setter_performed"] = False
                # Advance process-local cache so subsequent requests
                # skip both checker and setter.
                _last_stable_profile_cache[cache_key] = {
                    "ts": time.time(),
                    "token": _token,
                    "stable_key_short": stable_key_short,
                }
                # Advance known identity (checker confirmed volume has it)
                _update_known_identity(ws_id, model_profile_key, prefill_key)
                _finalize_timing(result, _build_start)
                _emit_publish_log("skipped_unchanged", stable_key_short)
                print(f"[warmup_profile] phase=checker_done stable_key={stable_key_short} matched=True", flush=True)
                return result
        except TimeoutError:
            _checker_ms = round((time.time() - _checker_start) * 1000, 2)
            result["active_profile_checker_ms"] = _checker_ms
            # Do NOT swallow TimeoutError — propagate immediately so the
            # caller can distinguish a hung platform from a genuine miss
            # and avoid falling through into a second long setter wait.
            print(f"[warmup_profile] phase=checker_done stable_key={stable_key_short} timeout=True", flush=True)
            raise
        except Exception:
            _checker_ms = round((time.time() - _checker_start) * 1000, 2)
            result["active_profile_checker_ms"] = _checker_ms
            # Fail-open: if the checker itself raises, proceed to the
            # setter as if no check was performed.
            result["profile_checker_performed"] = True
            print(f"[warmup_profile] phase=checker_done stable_key={stable_key_short} fail_open=True", flush=True)
            pass

    # ── 5. Build activation payload (UUIDs created here) ─────────────────
    production_options = production_options or {}
    payload = _build_activation_payload(workflow, workflow_hash, production_options, precomputed=_analysis)
    payload_bytes = len(json.dumps(payload, separators=(",", ":")))
    result["payload_bytes"] = payload_bytes

    # Stamp the stable restore key onto the payload so the remote worker
    # can log it in startup/restore diagnostics.  This field is NOT used
    # in the dedup key (the remote uses the profile_token to look up the
    # warmup profile).
    payload["stable_restore_key"] = stable_key

    # ── 6. Write via setter ──────────────────────────────────────────────
    result["remote_call"] = 1
    result["active_profile_remote_call"] = 1
    result["profile_cache_hit"] = False
    result["profile_setter_performed"] = True
    _setter_start = time.time()
    profile_token = payload.get("profile_token", "")
    print(f"[warmup_profile] phase=setter_start stable_key={stable_key_short}", flush=True)
    try:
        activation_result = await setter(payload, workspace=workspace or None)
        _setter_ms = round((time.time() - _setter_start) * 1000, 2)
        result["active_profile_setter_ms"] = _setter_ms
        result["active_profile_remote_ms"] = _setter_ms
        write_status = activation_result.get("status", "written")
        result["status"] = write_status
        result["active_profile_dedup_status"] = write_status
        result["changed"] = activation_result.get("changed", True)

        # Only advance cache and identity on success
        if write_status not in ("error",):
            _last_stable_profile_cache[cache_key] = {
                "ts": time.time(),
                "token": profile_token,
                "stable_key_short": stable_key_short,
            }
            _update_known_identity(ws_id, model_profile_key, prefill_key)
            result["active_profile_token"] = profile_token
            result["active_profile_publish_decision"] = "published"
        else:
            result["active_profile_token"] = profile_token
            result["active_profile_publish_decision"] = "published"
            # Do NOT advance identity on error
    except Exception:
        _setter_ms = round((time.time() - _setter_start) * 1000, 2)
        result["active_profile_setter_ms"] = _setter_ms
        result["active_profile_remote_ms"] = _setter_ms
        result["status"] = "error"
        result["active_profile_dedup_status"] = "error"
        result["active_profile_publish_decision"] = "published"
        result["active_profile_token"] = profile_token
        # Do NOT advance cache or identity on error
    finally:
        print(f"[warmup_profile] phase=setter_done stable_key={stable_key_short}", flush=True)

    _finalize_timing(result, _build_start)
    _emit_publish_log(result["active_profile_publish_decision"], stable_key_short)
    return result
