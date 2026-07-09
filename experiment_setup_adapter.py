"""Backend authoritative adapter for the Modal GPU experiment-setup redesign.

Validates normalised drafts, normalises legacy profiles, provides stale
profile detection, null controlled-value normalisation helpers, and stable
dimension attachment.

Owns final translation semantics. The frontend is NOT authoritative.
"""
from __future__ import annotations

from typing import Any


# ── Public API — normalised-draft validation ───────────────────────────

# ── Valid generation types and pairing modes ───────────────────────────

_VALID_GENERATION_TYPES = frozenset({"t2i", "img2img"})
_VALID_PAIRING_MODES = frozenset({"cartesian", "paired", "none"})
_VALID_COMPATIBILITY_MODES = frozenset({"standard", "strict", "relaxed"})


def validate_normalized_draft(draft: dict) -> dict:
    """Validate a normalised experiment draft.

    Checks structural completeness of the full normalised schema
    (including ``generation_type``, ``prompt_image_pairing``,
    ``variable_modes``, ``tested_values``, ``controlled_values``,
    ``compatibility_mode``, ``advanced_execution``) and rejects
    malformed drafts with a structured error report.

    Also accepts the simpler early test-fixture shape (``profile_type``
    instead of ``generation_type``) for backward compatibility.

    Returns ``{"valid": True, "errors": ""}`` on success,
    ``{"valid": False, "errors": "..."}`` on failure.
    """
    errors: list[str] = []

    if not isinstance(draft, dict):
        return {"valid": False, "errors": "draft must be a dict"}

    experiment_id = draft.get("experiment_id", "")
    if not isinstance(experiment_id, str) or not experiment_id:
        errors.append("experiment_id must be a non-empty string")

    if "revision" not in draft:
        errors.append("revision is required")

    # ── generation_type ────────────────────────────────────────────────
    generation_type = draft.get("generation_type")
    if generation_type is not None:
        if not isinstance(generation_type, str) or generation_type not in _VALID_GENERATION_TYPES:
            errors.append(
                f"generation_type must be one of {sorted(_VALID_GENERATION_TYPES)}, "
                f"got {generation_type!r}"
            )
    else:
        # Backward compat: accept profile_type as generation_type proxy.
        profile_type = draft.get("profile_type", "")
        if profile_type and profile_type not in ("t2i", "img2img", "legacy_default"):
            errors.append(f"unknown profile_type: {profile_type!r}")

    # ── prompt_image_pairing ───────────────────────────────────────────
    pairing = draft.get("prompt_image_pairing")
    if pairing is not None and pairing not in _VALID_PAIRING_MODES:
        errors.append(
            f"prompt_image_pairing must be one of {sorted(_VALID_PAIRING_MODES)}, "
            f"got {pairing!r}"
        )

    # ── workflows ──────────────────────────────────────────────────────
    workflows = draft.get("workflows", [])
    if not isinstance(workflows, list):
        errors.append("workflows must be a list")
    elif not workflows:
        errors.append("at least one workflow is required")
    else:
        for idx, wf in enumerate(workflows):
            if not isinstance(wf, dict):
                errors.append(f"workflows[{idx}] must be a dict")
                continue
            stacks = wf.get("stacks")
            if stacks is not None:
                if not isinstance(stacks, list) or not stacks:
                    errors.append(f"workflows[{idx}].stacks must be a non-empty list")
                else:
                    for si, stack in enumerate(stacks):
                        if not isinstance(stack, dict):
                            errors.append(f"workflows[{idx}].stacks[{si}] must be a dict")
                        if "main_triple" not in stack:
                            errors.append(f"workflows[{idx}].stacks[{si}] missing main_triple")
            else:
                if "main_triple" not in wf:
                    errors.append(f"workflows[{idx}] missing main_triple")

    # ── variable_modes ─────────────────────────────────────────────────
    variable_modes = draft.get("variable_modes")
    if variable_modes is not None:
        if not isinstance(variable_modes, dict):
            errors.append("variable_modes must be a dict")

    # ── tested_values ──────────────────────────────────────────────────
    tested_values = draft.get("tested_values")
    if tested_values is not None:
        if not isinstance(tested_values, dict):
            errors.append("tested_values must be a dict")

    # ── controlled_values ──────────────────────────────────────────────
    controlled_values = draft.get("controlled_values")
    if controlled_values is not None:
        if not isinstance(controlled_values, dict):
            errors.append("controlled_values must be a dict")

    # ── compatibility_mode ─────────────────────────────────────────────
    compat = draft.get("compatibility_mode")
    if compat is not None and not isinstance(compat, str):
        errors.append(f"compatibility_mode must be a string, got {type(compat).__name__}")

    # ── advanced_execution ─────────────────────────────────────────────
    advanced = draft.get("advanced_execution")
    if advanced is not None:
        if not isinstance(advanced, dict):
            errors.append("advanced_execution must be a dict")

    if errors:
        return {"valid": False, "errors": "; ".join(errors)}
    return {"valid": True, "errors": ""}


# ── Public API — legacy profile normalisation ──────────────────────────

def normalize_legacy_profile(profile: dict) -> dict:
    """Normalise a legacy profile (schema_version < 2) in memory.

    Returns a *copy* of the profile with ``profile_type`` set
    deterministically:

    - ``"t2i"`` — the profile has ``txt2img`` capability AND no
      ``input_image`` slot mapping (source is ``"legacy_normalized"``).
    - ``"legacy_default"`` — everything else.

    Also extracts ``lora_entries`` from ``model_stack.lora`` when present.

    Idempotent: calling twice on the same input returns the same result.
    """
    result = dict(profile)

    # Already normalised — pass through unchanged.
    if result.get("profile_type") in ("t2i", "img2img", "legacy_default"):
        return result

    capabilities = result.get("capabilities", {}) or {}
    slots = result.get("slots", {}) or {}
    model_stack = result.get("model_stack", {}) or {}

    # Deterministic T2I detection.
    has_txt2img = bool(capabilities.get("txt2img"))
    input_image_slot = slots.get("input_image")
    has_input_image = bool(
        isinstance(input_image_slot, dict)
        and input_image_slot.get("node_id")
    )

    if has_txt2img and not has_input_image:
        result["profile_type"] = "t2i"
    else:
        result["profile_type"] = "legacy_default"

    result["source"] = "legacy_normalized"

    # Extract LoRA entries from model stack when present.
    lora_raw = model_stack.get("lora", [])
    if lora_raw:
        result["lora_entries"] = list(lora_raw)

    return result


# ── Public API — no-rewrite-on-load ────────────────────────────────────

def load_legacy_profile(profile_data: dict) -> dict:
    """Load a profile dict and apply in-memory normalisation.

    Returns ``{"profile": <normalised dict>, "rewritten": False}``.
    The ``rewritten`` flag is always ``False`` — no disk I/O is performed
    and the file on disk is never modified. Normalisation is entirely
    in-memory.
    """
    normalized = normalize_legacy_profile(profile_data)
    return {
        "profile": normalized,
        "rewritten": False,
    }


# ── Public API — stale profile detection ───────────────────────────────

def is_profile_stale(profile: dict, current: dict) -> bool:
    """Return ``True`` if *profile* is stale relative to *current*.

    Staleness is determined by revision number *or* workflow hash
    mismatch.  Does **not** mutate either input.
    """
    p_rev = int(profile.get("revision", 0))
    c_rev = int(current.get("revision", 0))
    if p_rev < c_rev:
        return True

    p_hash = profile.get("workflow_hash", "")
    c_hash = current.get("workflow_hash", "")
    if p_hash != c_hash:
        return True

    return False


# ── Public API — null controlled-value handling ────────────────────────

def normalize_controlled_values(spec: dict) -> dict:
    """Normalise controlled values, handling ``None`` gracefully.

    ``None`` values are silently dropped at every nesting level.
    Never raises ``TypeError`` or ``IndexError`` on null inputs.
    Returns a new dict (input is not mutated).
    """
    result: dict = {}

    for key, value in spec.items():
        if value is None:
            # Drop null controlled values.
            continue

        if isinstance(value, dict):
            result[key] = normalize_controlled_values(value)
        elif isinstance(value, list):
            cleaned: list[Any] = []
            for item in value:
                if item is None:
                    continue
                if isinstance(item, dict):
                    cleaned.append(normalize_controlled_values(item))
                else:
                    cleaned.append(item)
            result[key] = cleaned
        else:
            result[key] = value

    return result


# ── Public API — dimension attachment ──────────────────────────────────

def attach_profile_dimensions(draft: dict, profile: dict) -> dict:
    """Attach resolution ``(width, height)`` from *profile* onto *draft*.

    Priority (first wins):
    1. Existing ``resolution`` key on *draft* (preserved).
    2. ``saved_state.width`` / ``saved_state.height`` on *profile*.
    3. ``default_width`` / ``default_height`` on *profile*.

    Validates that dimensions are positive integers.  Raises
    ``ValueError`` (or ``AssertionError``) for invalid stored values.

    Returns the (possibly modified) *draft* dict.
    """
    result = dict(draft)

    # 1. Already has resolution — do not override.
    if "resolution" in result:
        return result

    # 2. Saved state (takes priority over defaults).
    saved_state = profile.get("saved_state")
    if isinstance(saved_state, dict):
        w = saved_state.get("width")
        h = saved_state.get("height")
        if w is not None and h is not None:
            _validate_positive_dimensions(w, h)
            result["resolution"] = (int(w), int(h))
            return result

    # 3. Default width / height.
    w = profile.get("default_width")
    h = profile.get("default_height")
    if w is not None and h is not None:
        _validate_positive_dimensions(w, h)
        result["resolution"] = (int(w), int(h))
        return result

    return result


# ── Public API — normalised draft → compiler spec translation ─────────

def normalized_draft_to_compiler_spec(draft: dict) -> dict:
    """Convert a normalised experiment draft to the current compiler spec.

    The normalised draft uses per-workflow ``stacks`` with per-stack
    ``lora_selections``.  This function translates them into the compiler
    spec format while preserving the stacks structure (the compiler now
    supports stacks natively).

    Rich schema fields (``generation_type``, ``prompt_image_pairing``,
    ``variable_modes``, ``tested_values``, ``controlled_values``,
    ``compatibility_mode``, ``advanced_execution``) are passed through as
    top-level keys on the returned spec so the compiler can consume them
    or forward them to downstream consumers.

    The returned spec includes flat backward-compat fields pointing to
    the first stack so the compiler can fall back gracefully.
    """
    spec: dict = {
        "experiment_id": draft.get("experiment_id", ""),
        "revision": draft.get("revision", 1),
        "workflows": [],
        "prompts": draft.get("prompts", {"items": []}),
        "images": draft.get("images", {"mode": "cartesian", "items": []}),
        "loras": {"selections": []},
        "axes": draft.get("axes", {}),
    }

    # Pass through rich schema fields (may be consumed by compiler or
    # forwarded to downstream consumers / results grouping).
    for _key in ("generation_type", "prompt_image_pairing", "variable_modes",
                 "tested_values", "controlled_values", "compatibility_mode",
                 "advanced_execution"):
        _val = draft.get(_key)
        if _val is not None:
            spec[_key] = _val

    for wf in draft.get("workflows", []):
        new_wf: dict = {
            "profile_id": wf.get("profile_id", ""),
            "stacks": [],
            "lora_slots": [],
        }
        for stack in wf.get("stacks", []):
            main_triple = dict(stack.get("main_triple", {}))
            if "id" not in main_triple:
                main_triple["id"] = "main"
            new_stack: dict = {
                "stack_id": stack.get("stack_id", "s1"),
                "loader_target_group_id": stack.get(
                    "loader_target_group_id", "g_default"),
                "main_triple": main_triple,
                "subprofile_triples": stack.get("subprofile_triples", []),
                "selected_triple_ids": stack.get(
                    "selected_triple_ids", ["main"]),
                "lora_selections": stack.get("lora_selections", []),
            }
            new_wf["stacks"].append(new_stack)

        # Flat backward-compat fields pointing to the first stack.
        if new_wf["stacks"]:
            first = new_wf["stacks"][0]
            new_wf["loader_target_group_id"] = first["loader_target_group_id"]
            new_wf["main_triple"] = first["main_triple"]
            new_wf["subprofile_triples"] = first["subprofile_triples"]
            new_wf["selected_triple_ids"] = first["selected_triple_ids"]

        spec["workflows"].append(new_wf)

    # Ensure mandatory top-level keys exist.
    spec.setdefault("prompts", {"items": []})
    spec.setdefault("images", {"mode": "cartesian", "items": []})
    spec.setdefault("loras", {"selections": []})
    spec.setdefault("axes", {})

    return spec


# ── Public API — normalised runtime profile view ───────────────────────

def build_normalized_runtime_profile(profile: dict) -> dict:
    """Build a lightweight normalised runtime view of a profile.

    Returns a dict with only the fields the frontend Setup workflow
    selector needs — no full legacy payload duplication, no disk I/O.

    Keys returned:
    - ``runtime_profile_type`` — ``"t2i"``, ``"img2img"``, or
      ``"legacy_default"``
    - ``capabilities`` — inferred capability flags
    - ``synthesized_stacks`` — default stack list from the model stack
    - ``lora_config`` — basic LoRA metadata
    - ``dimensions`` — default resolution if available
    """
    normalized = normalize_legacy_profile(profile)
    capabilities = _infer_capabilities_from_profile(profile)
    stacks = _synthesize_default_stacks(profile)
    lora_config = _extract_lora_config(profile)
    dimensions = _extract_dimensions(profile)

    return {
        "runtime_profile_type": normalized.get("profile_type", "legacy_default"),
        "capabilities": capabilities,
        "synthesized_stacks": stacks,
        "lora_config": lora_config,
        "dimensions": dimensions,
    }


# ── Internal helpers ───────────────────────────────────────────────────

def _infer_capabilities_from_profile(profile: dict) -> dict:
    """Infer capability flags from a profile's slots and capabilities."""
    slots = profile.get("slots", {}) or {}
    caps = profile.get("capabilities", {}) or {}
    has_input_image = bool(
        isinstance(slots.get("input_image"), dict)
        and slots["input_image"].get("node_id")
    )
    return {
        "txt2img": bool(caps.get("txt2img", True)),
        "img2img": bool(caps.get("img2img", has_input_image)),
        "supports_negative_prompt": bool(
            isinstance(slots.get("negative_prompt"), dict)
            and slots["negative_prompt"].get("node_id")
        ),
        "supports_seed_override": bool(
            isinstance(slots.get("seed"), dict)
            and slots["seed"].get("node_id")
        ),
        "supports_steps_override": bool(
            isinstance(slots.get("steps"), dict)
            and slots["steps"].get("node_id")
        ),
        "supports_guidance_override": bool(
            isinstance(slots.get("guidance"), dict)
            and slots["guidance"].get("node_id")
        ),
    }


def _synthesize_default_stacks(profile: dict) -> list:
    """Synthesise a default stack list from the profile's model stack.

    Returns a list with one stack per checkpoint in the model stack.
    For legacy profiles with a flat model stack, a single default stack
    is returned.
    """
    model_stack = profile.get("model_stack", {}) or {}
    checkpoints = model_stack.get("checkpoint", [])
    unets = model_stack.get("unet", [])
    clips = model_stack.get("clip", [])
    vaes = model_stack.get("vae", [])

    stacks: list[dict] = []

    if checkpoints:
        # One stack per checkpoint (legacy flat mode).
        for ck in checkpoints:
            stacks.append({
                "stack_id": "stack_default",
                "loader_target_group_id": "g_default",
                "models": {
                    "checkpoint": ck if isinstance(ck, str) else "",
                },
            })
    elif unets or clips or vaes:
        # Split-mode: one stack from the first unet/clip/vae.
        stacks.append({
            "stack_id": "stack_default",
            "loader_target_group_id": "g_default",
            "models": {
                "unet": unets[0] if unets else "",
                "clip": clips[0] if clips else "",
                "vae": vaes[0] if vaes else "",
            },
        })

    if not stacks:
        # Fallback: empty stack placeholder.
        stacks.append({
            "stack_id": "stack_default",
            "loader_target_group_id": "g_default",
            "models": {},
        })

    return stacks


def _extract_lora_config(profile: dict) -> dict:
    """Extract basic LoRA configuration metadata from the profile.

    Returns ``{"entries": [...], "slot_count": N}``.  The entries are
    determined from ``lora_entries`` (legacy normalised), ``lora_slots``
    (v2+ profiles), or the legacy ``model_stack.lora`` list.
    """
    # Prefer normalised lora_entries (from normalize_legacy_profile).
    lora_entries = profile.get("lora_entries")
    if isinstance(lora_entries, list) and lora_entries:
        return {
            "entries": [{"file": e} if isinstance(e, str) else e
                        for e in lora_entries],
            "slot_count": len(lora_entries),
        }

    # Fall back to lora_slots (v2+ profiles).
    lora_slots = profile.get("lora_slots", []) or []
    if lora_slots:
        return {
            "entries": lora_slots,
            "slot_count": len(lora_slots),
        }

    # Legacy model_stack.lora.
    model_stack = profile.get("model_stack", {}) or {}
    raw = model_stack.get("lora", [])
    if raw:
        return {
            "entries": [{"file": e} if isinstance(e, str) else e
                        for e in raw],
            "slot_count": len(raw),
        }

    return {"entries": [], "slot_count": 0}


def _extract_dimensions(profile: dict) -> dict | None:
    """Extract default dimensions from a profile, if available."""
    w = profile.get("default_width")
    h = profile.get("default_height")
    if w is not None and h is not None:
        try:
            return {"width": int(w), "height": int(h)}
        except (TypeError, ValueError):
            pass
    return None


def _validate_positive_dimensions(width: Any, height: Any) -> None:
    """Validate that *width* and *height* are positive integers.

    Raises ``ValueError`` if dimensions are not positive integers.
    """
    try:
        w = int(width)
        h = int(height)
    except (TypeError, ValueError):
        raise ValueError(
            f"invalid dimensions: width={width!r}, height={height!r}"
        )
    if w <= 0 or h <= 0:
        raise ValueError(
            f"dimensions must be positive: width={w}, height={h}"
        )
