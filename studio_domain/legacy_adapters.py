"""Legacy-preset to workflow adapters (Studio Workflow legacy absorption).

Single-purpose translation layer between the unscoped legacy Studio preset
surface (``.studio_presets.json`` payloads whose ``values`` / ``model_choices``
are keyed by OLD semantic roles) and the workflows domain
(``studio_domain``: version-scoped presets / run-context shapes keyed by
CANONICAL bindable-input keys).

Durable authority
-----------------
The ``WorkflowDomainStore`` (``.studio_workflows.json`` /
``.studio_workflow_versions.json`` / ``.studio_workflow_mappings.json`` /
``.studio_workflow_presets.json``) stays the SOLE durable authority.  This
module performs NO I/O, NO store access, and NO old-data migration: every
function here is pure (dict in → dict out, inputs never mutated).

Adapter surface (exact — downstream lanes consume this without guessing)
------------------------------------------------------------------------
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
     (documented, deterministic — never silent at the preset level): when
     two input keys map to the same canonical key, input-order last-wins;
     ``translate_legacy_preset`` / ``resolve_legacy_run_context`` additionally
     surface every such collision in ``role_collisions``.

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

5. ``translate_legacy_preset(legacy_preset)``
   Inputs:  ``legacy_preset`` — unscoped legacy preset payload (``name`` or
     ``label``, ``description``, ``values``, ``model_choices``; any other
     top-level keys ignored except the verbatim passthroughs below).
   Outputs: workflow preset SHAPE (still unscoped — the caller supplies the
     version scope)::

         {
           "name": <legacy name else legacy label else "">,
           "description": <str, "">,
           "values": <canonical values dict>,
           "model_choices": <canonical model_choices dict>,
           "lora_values": <verbatim passthrough, NOT role-translated>,
           "exposed_controls": <verbatim passthrough, NOT role-translated>,
           "recommended_values": <verbatim passthrough, NOT role-translated>,
           "favorite": <bool>,
           "tags": <list[str]>,
           "unmapped_roles": <sorted unknown keys, visible>,
           "role_collisions": <{canonical: sorted([source keys])}>,
         }

     The name fallback order is explicit and never invents content: an empty
     name is passed through as ``""`` so ``create_preset`` still raises its
     truthful validation error.  ``lora_values`` / ``exposed_controls`` /
     ``recommended_values`` pass through verbatim by contract scope (this
     lane translates ``values`` / ``model_choices`` only).

6. ``resolve_legacy_run_context(legacy_preset, *, workflow_id,
   workflow_version_id, overrides=None, preset_id="")``
   Inputs:  a legacy preset payload + the version scope + optional legacy-
     keyed control overrides + optional originating preset id.
   Outputs: the SINGLE run-contract dict that Shelf/Experiment submissions
     resolve through (workflow run-context + the run route)::

         {
           "workflow_id": <str>,
           "workflow_version_id": <str>,
           "preset_id": <str>,
           "values": <canonical preset values overlaid with translated
                      overrides — overrides win per canonical key; this is
                      the exact ``controls`` argument for
                      ``handle_workflow_run_async`` / ``merge_workflow_controls``>,
           "model_choices": <canonical preset model choices>,
           "unmapped_roles": <sorted unknown keys across preset+overrides>,
           "role_collisions": <{canonical: sorted([source keys])}>,
         }

     Pure: no store access.  Overrides are translated with the same table
     before merging, so legacy callers keep sending old role names end to
     end while the domain only ever sees canonical keys.
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
      (two sources → one canonical key) input-order last-wins; the
      collision is surfaced by ``translate_legacy_preset`` /
      ``resolve_legacy_run_context`` via ``role_collisions``.
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


def translate_legacy_preset(legacy_preset: dict[str, Any] | None) -> dict[str, Any]:
    """Translate an unscoped legacy preset payload to a workflow preset shape.

    Inputs:  ``legacy_preset`` — unscoped legacy payload with ``name`` or
      ``label``, ``description``, ``values``, ``model_choices`` (all
      optional; ``None`` → ``{}``).
    Outputs: workflow preset shape dict (see module docstring §5): canonical
      ``values`` / ``model_choices``; ``lora_values`` / ``exposed_controls``
      / ``recommended_values`` verbatim (out of this lane's scope);
      ``unmapped_roles`` naming every unknown key; ``role_collisions``
      naming every multi-source canonical key.  Pure: the input is never
      mutated.  Raises ``TypeError`` for a non-dict, non-None payload.
    """
    if legacy_preset is None:
        legacy_preset = {}
    if not isinstance(legacy_preset, dict):
        raise TypeError(
            "translate_legacy_preset requires a legacy preset dict, "
            f"got {type(legacy_preset).__name__}"
        )

    raw_name = legacy_preset.get("name")
    raw_label = legacy_preset.get("label")
    if isinstance(raw_name, str) and raw_name.strip():
        name = raw_name.strip()
    elif isinstance(raw_label, str) and raw_label.strip():
        name = raw_label.strip()
    else:
        name = ""
    raw_description = legacy_preset.get("description", "")
    description = raw_description if isinstance(raw_description, str) else ""

    raw_values = legacy_preset.get("values")
    raw_models = legacy_preset.get("model_choices")
    raw_values = raw_values if isinstance(raw_values, dict) else {}
    raw_models = raw_models if isinstance(raw_models, dict) else {}

    values, values_collisions = _translate_mapping(raw_values)
    model_choices, models_collisions = _translate_mapping(raw_models)
    collisions: dict[str, list[str]] = {}
    for target in sorted(set(values_collisions) | set(models_collisions)):
        sources: list[str] = []
        for bucket in (values_collisions.get(target, []), models_collisions.get(target, [])):
            for source in bucket:
                if source not in sources:
                    sources.append(source)
        collisions[target] = sorted(sources)

    raw_loras = legacy_preset.get("lora_values")
    raw_exposed = legacy_preset.get("exposed_controls")
    raw_recommended = legacy_preset.get("recommended_values")
    raw_tags = legacy_preset.get("tags")

    return {
        "name": name,
        "description": description,
        "values": values,
        "model_choices": model_choices,
        "lora_values": copy.deepcopy(raw_loras) if isinstance(raw_loras, dict) else {},
        "exposed_controls": list(raw_exposed) if isinstance(raw_exposed, list) else [],
        "recommended_values": copy.deepcopy(raw_recommended) if isinstance(raw_recommended, dict) else {},
        "favorite": bool(legacy_preset.get("favorite", False)),
        "tags": [t for t in raw_tags if isinstance(t, str)] if isinstance(raw_tags, list) else [],
        "unmapped_roles": unmapped_roles(raw_values, raw_models),
        "role_collisions": collisions,
    }


def resolve_legacy_run_context(
    legacy_preset: dict[str, Any] | None,
    *,
    workflow_id: str,
    workflow_version_id: str,
    overrides: dict[str, Any] | None = None,
    preset_id: str = "",
) -> dict[str, Any]:
    """Resolve a legacy Shelf/Experiment submission to the single run contract.

    Inputs:  ``legacy_preset`` — legacy preset payload (``values`` /
      ``model_choices`` keyed by old roles); ``workflow_id`` /
      ``workflow_version_id`` — the version scope (caller-supplied; this
      function never guesses or migrates scope); ``overrides`` — optional
      legacy-keyed request control overrides; ``preset_id`` — optional
      originating preset id carried through for tracing.
    Outputs: run-contract dict (see module docstring §6) whose ``values``
      are the exact canonical ``controls`` argument for
      ``resolve_workflow_run_bundle`` → ``merge_workflow_controls`` →
      ``handle_workflow_run_async`` (preset values translated, then
      translated overrides applied on top — overrides win per canonical
      key).  ``model_choices`` stay separate (the domain merge overlays them
      onto mapped roles).  Unknown keys from preset AND overrides pass
      through into ``values`` verbatim and are named in ``unmapped_roles``;
      multi-source canonical keys are named in ``role_collisions``.  Pure:
      all inputs deep-copied on read, never mutated.
    """
    translated_preset = translate_legacy_preset(legacy_preset)
    raw_overrides = overrides if isinstance(overrides, dict) else {}
    translated_overrides, overrides_collisions = _translate_mapping(raw_overrides)

    values: dict[str, Any] = dict(translated_preset["values"])
    values.update(translated_overrides)

    collisions: dict[str, list[str]] = dict(translated_preset["role_collisions"])
    for target, sources in overrides_collisions.items():
        merged = list(collisions.get(target, []))
        for source in sources:
            if source not in merged:
                merged.append(source)
        collisions[target] = sorted(merged)

    unmapped: set[str] = set(translated_preset["unmapped_roles"])
    for key in raw_overrides:
        if key not in _KNOWN_KEYS:
            unmapped.add(key)

    return {
        "workflow_id": str(workflow_id or ""),
        "workflow_version_id": str(workflow_version_id or ""),
        "preset_id": str(preset_id or ""),
        "values": values,
        "model_choices": dict(translated_preset["model_choices"]),
        "unmapped_roles": sorted(unmapped),
        "role_collisions": collisions,
    }
