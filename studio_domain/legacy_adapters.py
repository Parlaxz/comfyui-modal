"""Legacy control-role to canonical-role translation (canvas compatibility).

Single-purpose, PURE translation layer from the OLD Studio control role names
still emitted by the legacy canvas/prompt path to the CANONICAL bindable-input
keys the workflows domain speaks.

Durable authority
-----------------
The ``WorkflowDomainStore`` (``.studio_workflows.json`` /
``.studio_workflow_versions.json`` / ``.studio_workflow_mappings.json``) is the
SOLE durable authority. This module performs NO I/O, NO store access, and NO
data migration: every function here is pure (dict in → dict out, inputs are
never mutated).

Role mapping (old → canonical):

    positive_prompt → prompt
    steps           → step_count
    cfg             → cfg_scale
    guidance        → cfg_scale
    model           → model_unet
    unet            → model_unet

Already-canonical keys pass through unchanged: prompt, seed, step_count,
cfg_scale, sampler, model_unet, vae, clip.

Any other key is UNKNOWN: it passes through VERBATIM (same value, never
dropped, never invented) and is reported visibly via ``unmapped_roles``.

Functions (name, inputs, outputs):

1. ``canonical_role(role)``
   Inputs:  ``role`` — one legacy role string.
   Outputs: the canonical bindable-input key (renamed per the table above,
     identity otherwise).  Non-string input is returned unchanged.

2. ``translate_values(values)``
   Inputs:  ``values`` — legacy ``values`` dict keyed by old semantic roles
     (``None`` → ``{}``).
   Outputs: NEW dict keyed by canonical roles (deep-copied values).  Known
     roles renamed; unknown keys passed through verbatim.  Collision rule
     (documented, deterministic — never silent): when two input keys map to
     the same canonical key, input-order last-wins.  Callers that must surface
     such collisions use ``unmapped_roles`` / their own merge pass.

3. ``translate_model_choices(model_choices)``
   Inputs:  ``model_choices`` — legacy ``model_choices`` dict keyed by old
     semantic roles (``None`` → ``{}``).
   Outputs: NEW dict keyed by canonical roles; same rename / passthrough /
     collision semantics as ``translate_values`` (kept as a separate
     function so model-specific rules have an explicit home).

4. ``unmapped_roles(values, model_choices=None)``
   Inputs:  ``values`` (+ optional ``model_choices``) dicts.
   Outputs: sorted ``list[str]`` of keys that are neither canonical nor
     known-legacy (i.e. the keys that pass through as unknown).  ``[]``
     when everything is known.
"""

from __future__ import annotations

import copy
from typing import Any


# ── Role contract ─────────────────────────────────────────────────────────
# ADAPTER ROLE MAPPING (old → canonical).  Downstream lanes: read this table,
# do not re-derive it.  ``guidance`` is the legacy Studio control id for the
# CFG widget (cf. ``studio_run_adapter._CONTROL_WIDGET_ALIASES``); both
# ``cfg`` and ``guidance`` canonically mean ``cfg_scale``.  ``unet`` is the
# short legacy alias for the model selector (cf. ``services._ROLE_ALIASES``).

LEGACY_ROLE_MAP: dict[str, str] = {
    "positive_prompt": "prompt",
    "steps": "step_count",
    "cfg": "cfg_scale",
    "guidance": "cfg_scale",
    "model": "model_unet",
    "unet": "model_unet",
}

# Canonical bindable-input keys (cf. ``services.BINDABLE_INPUT_CATALOG``).
CANONICAL_KEYS: frozenset[str] = frozenset({
    "prompt",
    "seed",
    "step_count",
    "cfg_scale",
    "sampler",
    "model_unet",
    "vae",
    "clip",
})

# Every key this adapter understands without flagging: canonical keys plus
# every known legacy source role.  Anything else is unknown (passthrough +
# reported in ``unmapped_roles``).
_KNOWN_KEYS: frozenset[str] = CANONICAL_KEYS | frozenset(LEGACY_ROLE_MAP)


def canonical_role(role: Any) -> Any:
    """Map one legacy role to its canonical bindable-input key.

    Inputs:  ``role`` — a legacy role string.
    Outputs: the canonical key per ``LEGACY_ROLE_MAP``; already-canonical
      and unknown strings return unchanged; non-string input returns
      unchanged (never raises, never invents).
    """
    if not isinstance(role, str):
        return role
    return LEGACY_ROLE_MAP.get(role, role)


def _translate_mapping(container: dict[str, Any]) -> tuple[dict[str, Any], dict[str, list[str]]]:
    """Shared rename engine for ``translate_values`` / ``translate_model_choices``.

    Returns ``(translated, collisions)`` where ``collisions`` maps each
    canonical key that had >1 distinct source key to its sorted sources.
    Input-order last-wins on collision (deterministic); the collision map
    keeps it visible so callers never silently drop a value.
    """
    translated: dict[str, Any] = {}
    sources: dict[str, list[str]] = {}
    for key, value in container.items():
        target = canonical_role(key)
        translated[target] = copy.deepcopy(value)
        bucket = sources.setdefault(target, [])
        if key not in bucket:
            bucket.append(key)
    collisions = {
        target: sorted(keys) for target, keys in sources.items() if len(keys) > 1
    }
    return translated, collisions


def translate_values(values: dict[str, Any] | None) -> dict[str, Any]:
    """Translate a legacy ``values`` dict to canonical bindable-input keys.

    Inputs:  ``values`` — dict keyed by old semantic roles (``None`` → ``{}``).
    Outputs: NEW dict keyed by canonical roles (deep-copied values).  Known
      roles renamed per ``LEGACY_ROLE_MAP``; unknown keys passed through
      verbatim (never dropped, never invented).  On key collision
      (two sources → one canonical key) input-order last-wins; callers that
      must surface such collisions read the canonical dict themselves.
    """
    if values is None:
        return {}
    if not isinstance(values, dict):
        return {}
    translated, _ = _translate_mapping(values)
    return translated


def translate_model_choices(model_choices: dict[str, Any] | None) -> dict[str, Any]:
    """Translate a legacy ``model_choices`` dict to canonical keys.

    Inputs:  ``model_choices`` — dict keyed by old semantic roles
      (``None`` → ``{}``); e.g. ``{"model": "krea.safetensors"}``.
    Outputs: NEW dict keyed by canonical roles (``model``/``unet`` →
      ``model_unet``); unknown keys passed through verbatim.  Same rename /
      passthrough / collision semantics as ``translate_values``.
    """
    if model_choices is None:
        return {}
    if not isinstance(model_choices, dict):
        return {}
    translated, _ = _translate_mapping(model_choices)
    return translated


def unmapped_roles(
    values: dict[str, Any] | None,
    model_choices: dict[str, Any] | None = None,
) -> list[str]:
    """List the unknown keys that pass through translation untouched.

    Inputs:  ``values`` (+ optional ``model_choices``) dicts.
    Outputs: sorted ``list[str]`` of keys in neither ``CANONICAL_KEYS`` nor
      ``LEGACY_ROLE_MAP`` — exactly the keys ``translate_values`` /
      ``translate_model_choices`` carry over verbatim.  ``[]`` when every
      key is known.  This is the visibility companion to passthrough:
      unknown roles stay present in outputs AND named here.
    """
    unknown: set[str] = set()
    for container in (values, model_choices):
        if not isinstance(container, dict):
            continue
        for key in container:
            if key not in _KNOWN_KEYS:
                unknown.add(key)
    return sorted(unknown)

