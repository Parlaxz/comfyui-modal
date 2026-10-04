"""Backend adapter for Studio Workflow platform runs (modern Studio lane).

Bridges the Studio Workflow domain (``studio_domain``: workflows, immutable
versions, mappings, presets) into the canonical single-run execution path —
the SAME hard-stop boundary as the legacy Studio preset surface:

* **V2 (only engine, H12)** → ``comfymodal_runtime.playground_service.PlaygroundService``
  (injectable load/validate/build-plan/save-history hooks).  Requests that
  explicitly carry a retired engine (v1/legacy/shadow) are rejected with
  ``EXECUTION_MODE_RETIRED`` before acceptance; the former v1/shadow
  submission-time path was retired in H12.

All controls are validated verbatim (never coerced) against the version
mapping's control schema and applied verbatim into the executable prompt.
The version's derived runnable state is authoritative: an unrunnable version
fails closed before any plan is built.

Identity threading
------------------
Modern workflow runs never emit the legacy ``studio_preset_id`` /
``studio_snapshot_id`` / ``studio_preset_label`` meta keys (which would shadow
the real preset identity in ``history_v2_writer``).  Instead they carry:

    workflow_id, workflow_version_id, preset_id,
    workflow_name, preset_name, workflow_hash, studio_controls,
    studio_feature_id

These flow through ``plan.request_metadata`` → history meta → History V2's
``generations.workflow_id`` / ``generations.workflow_version_id`` /
``generations.preset_id`` / ``generations.preset_name`` columns.
"""
from __future__ import annotations

import copy
import json
import logging
import os
import time
import uuid
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Callable, Optional

_log = logging.getLogger(__name__)

# Values that are carried in the prompt bundle under custom keys (never
# dropped) and the set excluded from the bundle (mirrors
# ``playground_service._default_build_execution_plan``).
_BUNDLE_EXCLUDED_KEYS = frozenset({
    "prompt", "negative_prompt", "seed", "steps", "guidance", "cfg",
    "sampler", "scheduler", "denoise",
})


# ── Domain service construction (mirrors studio_workflow_routes.py) ──────


def _get_domain_service(node_dir: str | os.PathLike) -> Any:
    """Return a ``WorkflowDomainService`` over the store files under *node_dir*.

    Construction mirrors ``studio_workflow_routes.register_workflow_routes``:
    the same store root (``.studio_workflows.json`` / ``.studio_workflow_versions.json``
    / ``.studio_workflow_mappings.json`` / ``.studio_workflow_presets.json``)
    and the dependency resolver's ``reasons_for`` wired as the
    ``dependency_provider`` when available.  The resolver is lazily built and
    any construction failure degrades to ``dependency_provider=None`` (the
    same behaviour as the routes when no resolver is supplied).
    """
    from studio_domain.services import WorkflowDomainService

    resolver = None
    try:
        from dependency_resolver import DependencyResolver
        _nd = os.path.abspath(str(node_dir))
        resolver = DependencyResolver(_nd, os.path.dirname(os.path.dirname(_nd)))
    except Exception:
        resolver = None
    return WorkflowDomainService(
        str(node_dir),
        dependency_provider=(resolver.reasons_for if resolver is not None else None),
    )


# ── Bundle resolution ─────────────────────────────────────────────────────


def default_controls_from_version(
    executable_prompt: dict[str, Any],
    control_schema: dict[str, Any],
) -> dict[str, Any]:
    """Read each mapped role's current value out of the version's own prompt.

    This is the documented no-preset path: control defaults come from the
    version's ``executable_prompt`` rather than from a stored preset.  Values
    are read literally through each mapping entry's ``node_id`` +
    ``input_name``; a role that cannot be resolved is simply omitted rather
    than guessed, so required-control validation still fails closed on it.
    """
    defaults: dict[str, Any] = {}
    if not isinstance(executable_prompt, dict):
        return defaults
    for role, entry in (control_schema or {}).items():
        if not isinstance(entry, dict):
            continue
        node_id = str(entry.get("node_id", "") or "")
        input_name = str(entry.get("input_name", "") or "")
        if not node_id or not input_name:
            continue
        node = executable_prompt.get(node_id)
        if not isinstance(node, dict):
            continue
        inputs = node.get("inputs")
        if not isinstance(inputs, dict) or input_name not in inputs:
            continue
        defaults[str(role)] = copy.deepcopy(inputs[input_name])
    return defaults


def resolve_workflow_run_bundle(
    workflow_id: str,
    version_id: str,
    preset_id: str,
    node_dir: str | os.PathLike,
    *,
    allow_remote_execution: bool = False,
) -> dict[str, Any]:
    """Resolve and gate a workflow run: workflow + version + mapping + preset.

    Returns ``{"status": "ok", "workflow", "version", "mapping", "preset",
    "state", "executable_prompt", "control_schema"}`` or a fail-closed error
    dict (``{"status": "error", "error_code", "message", ...}``).

    * Version resolution: empty ``version_id`` → the workflow's latest version.
    * Runnable gate: the version's derived state must be ``runnable``; an
      incomplete version returns ``WORKFLOW_VERSION_NOT_RUNNABLE`` with the
      derivation reasons (never guessed).
    * Preset resolution: explicit ``preset_id`` (verified to belong to the
      version) else the workflow's ``default_preset_id`` else an error.
    """
    service = _get_domain_service(node_dir)
    workflow_id = str(workflow_id or "")
    preset_id = str(preset_id or "")
    version_id = str(version_id or "").strip()

    try:
        workflow = service.get_workflow(workflow_id)
    except Exception as exc:  # WorkflowNotFoundError and friends
        return {
            "status": "error",
            "error_code": "WORKFLOW_NOT_FOUND",
            "message": str(exc) or f"workflow {workflow_id!r} not found",
        }

    if not version_id:
        version_id = str(workflow.get("latest_version_id", "") or "")

    try:
        version = service.get_version(version_id)
    except Exception as exc:  # WorkflowVersionNotFoundError
        return {
            "status": "error",
            "error_code": "WORKFLOW_VERSION_NOT_FOUND",
            "message": str(exc) or f"workflow version {version_id!r} not found",
        }

    state = service.derive_version_state(version_id).to_dict()
    if not state.get("runnable"):
        reasons = [str(r) for r in (state.get("reasons") or [])]
        # Presets are optional in this domain (see the synthesized preset above),
        # so "no preset selected" never blocks a run on its own.
        reasons = [r for r in reasons if not r.startswith("no preset")]
        if allow_remote_execution:
            # A remote Golden run executes on the deployed Modal container, not
            # on this host.  Reasons about files and custom nodes missing from
            # THIS machine therefore say nothing about that run: the models and
            # the published custom-node set live remotely.  Only
            # host-independent reasons (an incomplete version, absent mapping,
            # undefined controls) may still refuse the request.
            #
            # Remote admission is not weakened by this filter.  Golden's own
            # ``resolve_golden_node_map`` remains fail-closed on structure
            # (exactly one CLIPLoader/UNETLoader/VAELoader/CLIPTextEncode/
            # VAEDecode and one sampler, with concrete declared model names),
            # and the deployment must already satisfy its published
            # custom-node contract for the run to be admitted at all.
            reasons = [
                r for r in reasons
                if not (
                    r.startswith("missing model ")
                    or r.startswith("required custom node ")
                )
            ]
        if reasons:
            return {
                "status": "error",
                "error_code": "WORKFLOW_VERSION_NOT_RUNNABLE",
                "message": "workflow version is not runnable",
                "reasons": reasons,
            }

    mapping = service.get_mapping(version_id)
    if mapping is None:
        return {
            "status": "error",
            "error_code": "WORKFLOW_MAPPING_MISSING",
            "message": f"workflow version {version_id!r} has no mapping",
        }

    preset: Optional[dict[str, Any]] = None
    if preset_id:
        try:
            preset = service.get_preset(preset_id)
        except Exception as exc:  # WorkflowPresetNotFoundError
            return {
                "status": "error",
                "error_code": "PRESET_NOT_FOUND",
                "message": str(exc) or f"preset {preset_id!r} not found",
            }
        if not isinstance(preset, dict):
            return {
                "status": "error",
                "error_code": "PRESET_NOT_FOUND",
                "message": f"preset {preset_id!r} not found",
            }
        if str(preset.get("workflow_version_id", "")) != version_id:
            return {
                "status": "error",
                "error_code": "PRESET_VERSION_MISMATCH",
                "message": (
                    f"preset {preset_id!r} belongs to a different workflow "
                    f"version; expected {version_id!r}"
                ),
            }
    else:
        default_id = str(workflow.get("default_preset_id", "") or "")
        if default_id:
            try:
                preset = service.get_preset(default_id)
            except Exception:
                preset = None
        if preset is None:
            # Presets are optional in this domain: control defaults are read
            # from the version's own ``executable_prompt`` (see
            # ``default_controls_from_version``).  A workflow with no default
            # preset therefore still runs with the version's own values
            # instead of being refused.
            preset = {
                "preset_id": "",
                "name": "",
                "values": {},
            }

    executable_prompt = version.get("executable_prompt") or {}
    control_schema: dict[str, Any] = {}
    for entry in mapping.get("entries") or []:
        if isinstance(entry, dict) and entry.get("semantic_role"):
            control_schema[str(entry["semantic_role"])] = entry

    # A synthesized (absent) preset carries no values of its own, so seed it
    # from the version's own executable prompt.  Without this the required
    # controls would read as missing even though the version defines them.
    if not str(preset.get("preset_id") or "").strip():
        seeded = default_controls_from_version(
            executable_prompt if isinstance(executable_prompt, dict) else {},
            control_schema,
        )
        preset = {**preset, "values": seeded}

    return {
        "status": "ok",
        "workflow": workflow,
        "version": version,
        "mapping": mapping,
        "preset": preset,
        "state": state,
        "executable_prompt": executable_prompt if isinstance(executable_prompt, dict) else {},
        "control_schema": control_schema,
    }


# ── Control validation / merge ───────────────────────────────────────────


def _is_numeric(value: Any) -> bool:
    """True for int/float (bool excluded) that can be compared numerically."""
    if isinstance(value, bool):
        return False
    if isinstance(value, (int, float)):
        return True
    if isinstance(value, str):
        try:
            float(value)
            return True
        except (TypeError, ValueError):
            return False
    return False


def validate_workflow_controls(
    controls: dict[str, Any],
    control_schema: dict[str, Any],
) -> list[dict[str, str]]:
    """Validate control values against the version mapping schema (STRICT).

    Returns a list of ``{"field", "message"}`` error dicts (``[]`` when valid).

    * Unknown controls are rejected (no silent drop).  ``prompt`` /
      ``negative_prompt`` are ordinary mapped roles here — providing them when
      unmapped is an error just like any other unknown control.
    * ``enum_options`` membership is exact and type-strict (``==``).
    * ``minimum`` / ``maximum`` are enforced numerically only when the value
      is numeric (``float()``); non-numeric values are left to the kind rules.
    * ``required`` rejects ``None`` and whitespace-only strings.
    * Values are never coerced: ``0``, ``0.0``, ``False``, ``""`` are valid
      unless enum/min/max/required say otherwise.
    """
    errors: list[dict[str, str]] = []
    for key, value in (controls or {}).items():
        entry = control_schema.get(key)
        if entry is None:
            errors.append({"field": key, "message": f"unknown control {key!r}"})
            continue

        enum_options = entry.get("enum_options") or []
        if enum_options:
            if value not in enum_options:
                errors.append({
                    "field": key,
                    "message": (
                        f"invalid value {value!r}; must be one of: "
                        + ", ".join(str(o) for o in enum_options)
                    ),
                })

        if _is_numeric(value):
            minimum = entry.get("minimum")
            maximum = entry.get("maximum")
            try:
                if minimum is not None and float(value) < float(minimum):
                    errors.append({
                        "field": key,
                        "message": f"value {value!r} must be >= {minimum}",
                    })
                if maximum is not None and float(value) > float(maximum):
                    errors.append({
                        "field": key,
                        "message": f"value {value!r} must be <= {maximum}",
                    })
            except (TypeError, ValueError):
                pass

        if entry.get("required"):
            if value is None or (isinstance(value, str) and value.strip() == ""):
                errors.append({
                    "field": key,
                    "message": f"required control {key!r} must not be empty",
                })
    return errors


def merge_workflow_controls(
    preset: dict[str, Any],
    overrides: dict[str, Any],
    control_schema: dict[str, Any],
) -> dict[str, Any]:
    """Merge preset values + request overrides and validate the result.

    Base = ``preset["values"]`` keyed by semantic role; for roles present in
    ``preset["model_choices"]`` the model choice wins.  Request overrides are
    applied on top (only keys present in *overrides*; overrides win).

    The merged dict is validated with ``validate_workflow_controls`` and any
    required mapping role missing from the merged values adds a
    ``"missing required control '<role>'"`` error.

    Returns ``{"values": merged, "errors": [...]}``.
    """
    preset = preset or {}
    overrides = overrides or {}
    control_schema = control_schema or {}

    base: dict[str, Any] = dict(preset.get("values") or {})
    for role, model_name in (preset.get("model_choices") or {}).items():
        if role in control_schema:
            base[role] = model_name

    merged: dict[str, Any] = dict(base)
    for key, value in overrides.items():
        merged[key] = value

    errors: list[dict[str, str]] = validate_workflow_controls(merged, control_schema)

    for role, entry in control_schema.items():
        if entry.get("required"):
            if role not in merged or merged.get(role) is None:
                errors.append({
                    "field": role,
                    "message": f"missing required control {role!r}",
                })

    return {"values": merged, "errors": errors}


# ── Legacy absorption bridge (abs-1) ─────────────────────────────────────


def prepare_legacy_run_controls(
    control_schema: dict[str, Any],
    legacy_preset: dict[str, Any] | None = None,
    overrides: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Translate legacy-keyed values, then merge+validate via the verified path.

    Inputs: ``control_schema`` — the bundle's canonical control schema (from
      ``resolve_workflow_run_bundle``); ``legacy_preset`` — a legacy preset
      PAYLOAD (``values``/``model_choices`` keyed by old roles; a bare
      values dict must be wrapped as ``{"values": ...}``); ``overrides`` —
      optional legacy-keyed request overrides (translated, then win per
      canonical key).
    Outputs: ``{"values": merged_canonical, "errors": [...]}`` — the exact
      shape ``merge_workflow_controls`` returns.  Translation is pure
      (``studio_domain.legacy_adapters``: renames per role table, unknown
      keys verbatim); validation stays STRICT (unknown controls error —
      visible, never silently dropped).  Run contract order:
      ``resolve_workflow_run_bundle`` → this → ``build_workflow_execution_plan``
      / ``handle_workflow_run_async``.
    """
    from studio_domain.legacy_adapters import (
        translate_model_choices,
        translate_values,
    )

    payload = legacy_preset if isinstance(legacy_preset, dict) else {}
    raw_values = payload.get("values")
    raw_models = payload.get("model_choices")
    canonical_preset = {
        "values": translate_values(raw_values if isinstance(raw_values, dict) else {}),
        "model_choices": translate_model_choices(
            raw_models if isinstance(raw_models, dict) else {}
        ),
    }
    translated_overrides = translate_values(
        overrides if isinstance(overrides, dict) else {}
    )
    return merge_workflow_controls(
        canonical_preset, translated_overrides, control_schema or {}
    )


# ── Prompt application ───────────────────────────────────────────────────


def _values_identical(a: Any, b: Any) -> bool:
    """Verbatim identity check used for read-back assertion (no coercion)."""
    if a is b:
        return True
    if type(a) is not type(b):
        return False
    try:
        return bool(a == b)
    except Exception:
        return False


def _plain_copy(value: Any) -> Any:
    """Recursively convert frozen plan containers to plain dicts/lists.

    ``ExecutionPlan`` freezes mappings into ``MappingProxyType`` (a
    ``collections.abc.Mapping``) which is not JSON-serializable and cannot be
    ``copy.deepcopy``-ed.  Every recursive ``Mapping`` (including
    ``MappingProxyType`` and plain ``dict``) becomes a plain dict, every
    ``tuple``/``list`` becomes a plain list, ordinary JSON scalars pass
    through untouched, and arbitrary unsupported objects pass through
    unchanged (never stringified) so a strict ``json.dumps`` check can still
    fail truthfully downstream.  Mirrors the semantics of ``contracts._thaw``
    for values read from a frozen plan.
    """
    if isinstance(value, Mapping):
        return {str(k): _plain_copy(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain_copy(v) for v in value]
    return value


def _build_plan_replay_meta(
    plan: Any,
    modal_options: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return History snapshot fields from the exact executed plan."""
    to_dict = getattr(plan, "to_dict", None)
    if not callable(to_dict):
        return {}
    try:
        serialized = to_dict()
    except Exception:
        return {}
    if not isinstance(serialized, dict):
        return {}

    request_metadata = _plain_copy(serialized.get("request_metadata") or {})
    if not isinstance(request_metadata, dict):
        request_metadata = {}
    controls = request_metadata.get("studio_controls")
    if not isinstance(controls, dict):
        controls = {}
    request = {
        "workflow_id": request_metadata.get("workflow_id", ""),
        "workflow_version_id": request_metadata.get("workflow_version_id", ""),
        "preset_id": request_metadata.get("preset_id", ""),
        "workflow_name": request_metadata.get("workflow_name", ""),
        "preset_name": request_metadata.get("preset_name", ""),
        "controls": controls,
        "prompt_bundle": _plain_copy(serialized.get("prompt_bundle") or {}),
        "model_stack": _plain_copy(serialized.get("model_stack") or {}),
        "execution_options": _plain_copy(
            serialized.get("execution_options") or {}
        ),
        "request_metadata": request_metadata,
    }
    if modal_options is not None:
        request["modal_options"] = _plain_copy(modal_options)

    return {
        "workflow_json": _plain_copy(serialized.get("workflow") or {}),
        "workflow_hash": str(serialized.get("workflow_hash") or ""),
        "request_json": request,
        "execution_plan_json": _plain_copy(serialized),
        "deployment_identity_json": _plain_copy(
            serialized.get("deployment_identity") or {}
        ),
        "model_stack": _plain_copy(serialized.get("model_stack") or {}),
    }


def apply_workflow_values_to_prompt(
    executable_prompt: dict[str, Any],
    control_schema: dict[str, Any],
    values: dict[str, Any],
) -> dict[str, Any]:
    """Apply control values VERBATIM into a deep copy of the executable prompt.

    Each (role, value) is resolved through the mapping entry's ``node_id`` +
    ``input_name``.  ``kind=="widget"`` entries store the widget value under
    ``node["inputs"][input_name]`` (ComfyUI API prompts keep widget values in
    ``inputs``).  Unresolvable mappings block with an error (never guessed).

    After all writes every written value is read back and asserted identical
    (``==`` with equal types); a mismatch is a hard error.

    Returns ``{"workflow": applied_prompt}`` or ``{"error": message}``.
    """
    if not isinstance(executable_prompt, dict):
        return {"error": "executable prompt is not a dict"}
    workflow = copy.deepcopy(executable_prompt)

    for role, value in (values or {}).items():
        entry = control_schema.get(role)
        if entry is None:
            return {"error": f"control {role!r} has no mapping entry; cannot resolve"}
        node_id = str(entry.get("node_id", "") or "")
        input_name = str(entry.get("input_name", "") or "")
        if not node_id or not input_name:
            return {"error": f"mapped control {role!r} has no node/input binding"}
        node = workflow.get(node_id)
        if not isinstance(node, dict):
            return {
                "error": (
                    f"mapped control {role!r} cannot be resolved: "
                    f"node {node_id} not present"
                ),
            }
        inputs = node.get("inputs")
        if not isinstance(inputs, dict) or input_name not in inputs:
            return {
                "error": (
                    f"mapped control {role!r} cannot be resolved: node {node_id} "
                    f"input {input_name!r} not present"
                ),
            }
        inputs[input_name] = value

    # Read back and assert verbatim identity.
    for role, value in (values or {}).items():
        entry = control_schema.get(role)
        if entry is None:
            return {
                "error": f"control {role!r} has no mapping entry; cannot resolve"
            }
        node_id = str(entry.get("node_id", "") or "")
        input_name = str(entry.get("input_name", "") or "")
        node = workflow.get(node_id)
        written = None
        if isinstance(node, dict):
            inputs = node.get("inputs")
            if isinstance(inputs, dict):
                written = inputs.get(input_name)
        if not _values_identical(written, value):
            return {
                "error": (
                    f"mapped control {role!r} read-back mismatch: wrote "
                    f"{value!r} but node {node_id} input {input_name!r} holds "
                    f"{written!r}"
                ),
            }

    return {"workflow": workflow}


# ── Studio metadata (modern identity — no legacy keys) ───────────────────


def _build_workflow_studio_meta(
    workflow_id: str,
    version_id: str,
    preset_id: str,
    workflow_name: str,
    preset_name: str,
    controls: dict[str, Any],
    workflow_hash: str,
    output_mode: str = "original",
) -> dict[str, Any]:
    """Build request metadata for a modern workflow run.

    Deliberately emits NO legacy keys (``studio_preset_id`` /
    ``studio_snapshot_id`` / ``studio_preset_label``): in ``history_v2_writer``
    the legacy keys take precedence and would shadow the real preset identity.
    """
    output_mode = str(output_mode or "original").strip().lower() or "original"
    return {
        "workflow_id": str(workflow_id or ""),
        "workflow_version_id": str(version_id or ""),
        "preset_id": str(preset_id or ""),
        "workflow_name": str(workflow_name or ""),
        "preset_name": str(preset_name or ""),
        "workflow_hash": str(workflow_hash or ""),
        "studio_controls": dict(controls or {}),
        "studio_feature_id": "workflow",
        "output_mode": output_mode,
        "variant": output_mode,
    }


# ── Execution plan ───────────────────────────────────────────────────────


def build_workflow_execution_plan(
    bundle: dict[str, Any],
    values: dict[str, Any],
    modal_options: dict[str, Any] | None = None,
    trace_ctx: dict[str, Any] | None = None,
    comfyui_root: str = "",
    gpu: Any = None,
) -> tuple[Any, str | None]:
    """Build a frozen ``ExecutionPlan`` for a workflow run.

    Returns ``(ExecutionPlan, None)`` on success or ``(None, error_message)``
    on failure.  Mirrors ``playground_service._default_build_execution_plan``
    (production compile via ``canonical_execution.build_execution_plan`` +
    ExecutionPlan rebuild) and the non-production direct plan construction.

    * ``output_node_ids`` is ALWAYS derived from the mapping's
      ``output_node_id`` (production and non-production — materialization
      depends on it).
    * ``workflow_hash`` uses ``workflow_metadata.prompt_sha256``.
    * ``request_metadata`` carries the modern workflow identity meta.

    F8: *gpu* is the GPU captured at request acceptance; it is frozen into
    ``request_metadata.selected_gpu`` so replay/resume/retry keep executing
    on the plan's own GPU regardless of later Settings changes.

    ``trace_ctx`` is accepted for signature parity with the legacy adapter;
    it is not consumed by plan construction.
    """
    try:
        from comfymodal_runtime.contracts import (
            ExecutionOptions,
            ExecutionPlan,
            normalize_output_intent_options,
        )
        from production_workflow import normalize_production_options
        from studio_run_adapter import (
            _repair_missing_clip_inputs,
            _repair_missing_vae_inputs,
        )
        from workflow_metadata import extract_model_stack, prompt_sha256

        applied = apply_workflow_values_to_prompt(
            bundle["executable_prompt"], bundle["control_schema"], values
        )
        if "error" in applied:
            return None, applied["error"]
        workflow = applied["workflow"]

        # Repair legacy missing CLIP/VAE inputs on the applied deep copy
        # (same helpers as _default_build_execution_plan / build_single_run_spec).
        _repair_missing_clip_inputs(workflow)
        _repair_missing_vae_inputs(workflow)

        # ── Prompt bundle (custom, mirrors _default_build_execution_plan) ──
        # The modern role for the positive prompt is ``positive_prompt``; map
        # it onto the canonical ``prompt`` bundle key (safe fallback to a
        # literal ``prompt`` value for legacy-shaped control sets) so History
        # V2's prompt extraction preserves the supplied positive prompt.
        custom_prompt_bundle: dict[str, Any] = {
            "prompt": values.get("positive_prompt", values.get("prompt", "")),
            "negative_prompt": values.get("negative_prompt", ""),
        }
        for ck, cv in values.items():
            if ck not in _BUNDLE_EXCLUDED_KEYS:
                custom_prompt_bundle[ck] = cv

        workflow_hash = prompt_sha256(workflow)
        effective_modal_options = normalize_output_intent_options(modal_options)
        output_mode = str(effective_modal_options.get("output_mode", "original"))
        _selected_gpu = str(gpu or "")
        studio_meta = _build_workflow_studio_meta(
            workflow_id=str(bundle.get("workflow", {}).get("workflow_id", "")),
            version_id=str(bundle.get("version", {}).get("workflow_version_id", "")),
            preset_id=str(bundle.get("preset", {}).get("preset_id", "")),
            workflow_name=str(bundle.get("workflow", {}).get("name", "")),
            preset_name=str(bundle.get("preset", {}).get("name", "")),
            controls=values,
            workflow_hash=workflow_hash,
            output_mode=output_mode,
        )
        studio_meta["selected_gpu"] = _selected_gpu

        output_node_id = str(bundle.get("mapping", {}).get("output_node_id", "") or "")
        if not output_node_id:
            return None, "workflow mapping has no output node id"
        output_node_ids: tuple[str, ...] = tuple([output_node_id])

        production_options = normalize_production_options(effective_modal_options)
        if production_options.get("enabled"):
            from canonical_execution import build_execution_plan as canonical_build_plan

            prod_options = production_options
            prod_options["output_node_ids"] = list(output_node_ids)

            plan = canonical_build_plan(
                workflow,
                prompt_id=str(uuid.uuid4().hex[:12]),
                modal_options=effective_modal_options,
                production_options=prod_options,
                gpu=_selected_gpu,
                request_metadata=studio_meta,
                comfyui_root=str(comfyui_root or ""),
                validate=False,
                # E7: freeze the plan-carried validation proof so the saved
                # snapshot stays replay-capable for Generate Original (E3B2
                # fail-closed replay validation requires a non-empty proof).
                collect_validation_proof=True,
            )
            # Rebuild overriding prompt_bundle (intentional — the modern
            # bundle) and overlaying the modern studio metadata onto the
            # canonical request_metadata so canonical keys (prompt_id,
            # client_id, selected_gpu, workspace_id, request_origin_info, ...)
            # survive the reconstruction.  Every other unaffected canonical
            # ExecutionPlan field — including the plan-carried ``validation``
            # proof and ``deployment_identity`` — is preserved verbatim, never
            # fabricated or recomputed; when the canonical plan carries no
            # identity (empty dicts) the rebuilt plan stays empty.
            plan_request_metadata = dict(plan.request_metadata or {})
            plan_request_metadata.update(studio_meta)
            plan = ExecutionPlan(
                schema_version=plan.schema_version,
                workflow=plan.workflow,
                workflow_hash=plan.workflow_hash,
                source_workflow_hash=plan.source_workflow_hash,
                production_report=plan.production_report,
                model_stack=plan.model_stack,
                prompt_bundle=custom_prompt_bundle,
                output_node_ids=plan.output_node_ids,
                input_images=plan.input_images,
                execution_options=plan.execution_options,
                request_metadata=plan_request_metadata,
                validation=plan.validation,
                deployment_identity=plan.deployment_identity,
            )
        else:
            plan = ExecutionPlan(
                workflow=workflow,
                workflow_hash=workflow_hash,
                model_stack=extract_model_stack(workflow),
                prompt_bundle=custom_prompt_bundle,
                output_node_ids=output_node_ids,
                execution_options=ExecutionOptions(
                    production_enabled=False,
                    output_mode=output_mode,
                    output_conversion_options=effective_modal_options.get(
                        "output_conversion_options", {}
                    ),
                ),
                request_metadata=studio_meta,
            )
        return plan, None
    except Exception as exc:
        _log.warning("Workflow execution plan build failed: %s", exc)
        return None, str(exc)[:500]


# ── Modern history capture + success commit ───────────────────────────────


async def _capture_modern_save_history(
    capture: dict[str, Any],
    plan: Any,
    result: dict[str, Any],
    run_history_id: str,
    status: str = "completed",
    completed_at: str = "",
    materialized_paths: list[str] | None = None,
) -> None:
    """Capture-only save callback injected into the PlaygroundService.

    The real service invokes this AFTER materialization but BEFORE it returns
    its Stage-9 result.  This callback deliberately writes NO History: it only
    records the raw result projection (``trace`` / ``_restore_timing`` /
    ``primary_asset_id`` / ``primary_output`` / ``_local_primary_output`` are
    all reachable through the raw result reference) plus the callback args so
    the handler can perform the actual History write AFTER the final result
    boundary.  That way a local post-execution failure (strict JSON, missing
    capture, history metadata preparation, output preflight) is recorded as a
    truthful failure instead of a completed→failed repair.
    """
    capture["plan"] = plan
    capture["result"] = result
    capture["run_history_id"] = str(run_history_id or "")
    capture["status"] = str(status or "completed")
    capture["completed_at"] = str(completed_at or "")
    capture["materialized_paths"] = (
        [str(p) for p in materialized_paths] if materialized_paths else None
    )


def _resolve_output_candidate(candidate: str) -> Path | None:
    """Resolve an output candidate EXACTLY as the V2 writer's asset attach does.

    Mirrors ``HistoryV2ProductionWriter._attach_output_assets``: a candidate
    resolves when ``Path(candidate).is_file()`` OR the basename under
    ``local_artifacts.get_studio_outputs_dir()`` is a file.  Returns the
    resolved path or None when the candidate is genuinely absent.  Never
    fabricates or rewrites candidates.
    """
    candidate_path = Path(candidate)
    if candidate_path.is_file():
        return candidate_path
    try:
        from local_artifacts import get_studio_outputs_dir
        resolved = get_studio_outputs_dir() / candidate_path.name
    except Exception:
        return None
    if resolved.is_file():
        return resolved
    return None


async def _modern_save_history_success(
    capture: dict[str, Any],
    *,
    started_at: str,
    mono_start: float,
    completed_at: str = "",
) -> None:
    """Commit captured post-materialization success data to History.

    Runs ONLY after the accepted execution result crossed the strict JSON
    boundary.  The accepted ``started_at`` drives ``record_run`` and
    ``duration_ms`` is derived from the accepted ``mono_start`` so the stored
    timing includes the full accepted wait (never frontend/output times).
    ``completed_at`` is the handler's terminal timestamp (captured after the
    execution await) — always >= ``started_at``; the service's captured value
    is only a fallback.

    Ordering (truthful asset association): the first history record uses the
    NONTERMINAL ``running`` status so the V2 writer creates the generation,
    request snapshot and output/featured asset association BEFORE the final
    ``completed`` update is applied.  The final ``completed`` status is only
    applied after every fallible metadata/output check (capture presence,
    output preflight resolution, strict ``json.dumps``) passed.

    Every fallible metadata/output check happens BEFORE the first history
    write; a failure there raises and the caller records a truthful failure
    with the same accepted run identity.  Once the ``running`` record exists,
    post-record ``update_run`` failures are loud/log-only and NEVER produce a
    second failure record or a second attempt (no completed→failed repair).

    Replicates ``comfymodal_runtime.playground_service._default_save_history``
    (REGISTRY record_run + update_run) AND persists ``workflow_json`` (plain
    copy of the executed plan workflow) so History V2 stores the request
    snapshot with ``workflow_version_id`` identity.
    """
    from datetime import datetime, timezone

    from experiment_service import REGISTRY

    plan = capture.get("plan")
    result = capture.get("result")
    run_history_id = str(capture.get("run_history_id") or "")
    materialized_paths = capture.get("materialized_paths") or None

    if plan is None or not isinstance(result, dict) or not run_history_id:
        raise ValueError(
            "v2 success history capture is missing or incomplete "
            "(save callback never invoked)"
        )

    if not completed_at:
        completed_at = str(capture.get("completed_at") or "")
    if not completed_at:
        completed_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    # ── Timings: raw result projection + accepted monotonic duration ──
    timings: dict[str, Any] = {"_run_type": "playground_direct"}
    ts = result.get("trace", {}) or {}
    if isinstance(ts, Mapping):
        stages = ts.get("stages", {}) or {}
        if isinstance(stages, Mapping):
            for mk in ("browser_run_click", "studio_route_received",
                       "production_compile_complete", "remote_submit",
                       "first_remote_event", "result_received",
                       "output_materialized"):
                mv = stages.get(mk)
                if mv is not None:
                    timings[mk] = mv

        deltas = ts.get("deltas_ms", {}) or {}
        if isinstance(deltas, Mapping):
            for ck, rk in (("clip_load_ms", "clip_load"),
                           ("clip_encode_ms", "clip_encode"),
                           ("sampling_ms", "sampler"),
                           ("vae_decode_ms", "vae_decode"),
                           ("image_io_ms", "image_io"),
                           ("remote_inference_total_ms", "inference_total")):
                rv = deltas.get(rk)
                if rv is not None:
                    timings[ck] = rv

        _raw_derived = ts.get("derived_ms")
        _derived = _raw_derived if isinstance(_raw_derived, Mapping) else {}
        _raw_meta = ts.get("metadata")
        _meta = _raw_meta if isinstance(_raw_meta, Mapping) else {}
        _v2_build = _derived.get("active_profile_build_ms")
        if _v2_build is not None:
            timings["active_profile_build_ms"] = _v2_build
        elif isinstance(_meta.get("local_active_profile_prepare_ms"), (int, float)):
            timings["active_profile_build_ms"] = max(
                0.0, float(_meta["local_active_profile_prepare_ms"])
            )
        _v2_call = _derived.get("active_profile_remote_call")
        if _v2_call is not None:
            timings["active_profile_remote_call"] = _v2_call
        elif _meta.get("active_profile_prepare_count"):
            timings["active_profile_remote_call"] = int(
                _meta["active_profile_prepare_count"]
            )
        _v2_remote_ms = _derived.get("active_profile_remote_ms")
        if _v2_remote_ms is not None:
            timings["active_profile_remote_ms"] = _v2_remote_ms
        elif isinstance(_meta.get("active_profile_remote_ms"), (int, float)):
            timings["active_profile_remote_ms"] = max(
                0.0, float(_meta["active_profile_remote_ms"])
            )

    restore = result.get("_restore_timing", {}) or {}
    if isinstance(restore, Mapping):
        rt = restore.get("restore_total_ms")
        if rt is not None:
            timings["restore_total_ms"] = rt

    if isinstance(result.get("trace"), Mapping):
        timings["trace"] = _plain_copy(result["trace"])

    timings["duration_ms"] = round((time.monotonic() - mono_start) * 1000.0, 3)

    # ── Meta: plain JSON-safe copies at every nesting level ──
    meta: dict[str, Any] = {
        "playground_run": True,
    }
    # The plan freezes mappings into MappingProxyType; thaw to plain dicts
    # so the stored meta stays JSON-safe at every nesting level.
    meta.update(_plain_copy(plan.request_metadata))
    meta["requested_controls"] = _plain_copy(plan.prompt_bundle)
    meta["experiment_id"] = run_history_id
    meta["workflow_hash"] = plan.workflow_hash

    replay_meta = _build_plan_replay_meta(
        plan, modal_options=capture.get("modal_options")
    )
    meta.update(replay_meta)

    # History V2: persist the exact executable workflow at completion so a
    # future Generate-Original can replay it without mutable UI state.
    try:
        meta["workflow_json"] = _plain_copy(plan.workflow)
    except Exception:
        pass

    # Promote the sampling/geometry controls to meta top level so History V2's
    # snapshot param extraction preserves them verbatim (``requested_controls``
    # carries the prompt bundle which deliberately excludes widget-exclusive
    # keys).  Falsy values (0 / 0.0 / False / "") are preserved untouched.
    _studio_controls = meta.get("studio_controls")
    if isinstance(_studio_controls, Mapping):
        for _key in ("seed", "steps", "guidance", "cfg", "sampler",
                     "scheduler", "denoise", "width", "height"):
            if _key in _studio_controls and _key not in meta:
                meta[_key] = _studio_controls[_key]

    primary_asset_id = ""
    if isinstance(result, dict):
        primary_asset_id = str(result.get("primary_asset_id", "") or "")
    if primary_asset_id:
        meta["primary_asset_id"] = primary_asset_id

    # E2C: optional Thumbnail derivative producer ids ride in meta so the
    # History writer can adopt them under the SAME logical output key as the
    # required primary asset.  Derivatives are never the required result.
    if isinstance(result, dict):
        raw_derivatives = result.get("derivative_asset_ids")
        if isinstance(raw_derivatives, (list, tuple)):
            derivative_ids = [str(value) for value in raw_derivatives if str(value)]
            if derivative_ids:
                meta["derivative_asset_ids"] = derivative_ids

    # ── Output candidates: only known/materialized outputs are attached;
    #    never fabricated assets.  Mirrors the PlaygroundService contract
    #    (no new zero-output mode is imposed). ──
    output_paths: list[str] = [str(p) for p in (materialized_paths or []) if str(p)]
    if not output_paths and not primary_asset_id:
        primary = result.get("primary_output") or result.get("_local_primary_output")
        if (
            isinstance(primary, Mapping)
            and primary.get("path")
            and Path(str(primary["path"])).is_file()
        ):
            # Keep the VERIFIED full path (never rewrite to a basename): the
            # writer attaches full paths directly and the preflight below must
            # be able to re-resolve the same candidate.
            output_paths = [str(primary["path"])]
    requires_output = bool(
        getattr(plan.execution_options, "production_enabled", False)
    ) or bool(plan.output_node_ids)

    # Output preflight (F1): EVERY non-empty materialized_paths candidate must
    # resolve exactly as history_v2_writer._attach_output_assets resolves it
    # (direct path OR basename under the studio outputs dir).  A missing
    # candidate is a truthful pre-terminal local failure — never a fabricated
    # asset and never a completed record.  Descriptor/primary_asset_id mode
    # (no local files) is preserved: it carries no candidates to verify.
    for _candidate in output_paths:
        if _resolve_output_candidate(_candidate) is None:
            raise ValueError(
                f"v2 output preflight failed: materialized output {_candidate!r} "
                "is not present (checked direct path and studio outputs dir)"
            )
    if requires_output and not output_paths and not primary_asset_id:
        raise ValueError(
            "v2 output preflight failed: required output has no known, "
            "materialized path or primary asset id"
        )
    if not output_paths and primary_asset_id:
        # Descriptor-only success: the primary producer asset must resolve in
        # the LeaseRegistry before any History write.  An unknown/unusable id
        # is a truthful pre-terminal local failure — the caller records a
        # failed Generation/Attempt with the repaired snapshot + duration,
        # never a completed→failed repair.  A usable ordinary path skips this
        # check (the path is itself a valid output).
        try:
            from history_v2_writer import preflight_producer_asset

            if not preflight_producer_asset(primary_asset_id):
                raise ValueError(
                    f"v2 output preflight failed: primary asset "
                    f"{primary_asset_id!r} does not resolve in the producer "
                    "asset registry"
                )
        except ImportError:
            raise ValueError(
                f"v2 output preflight failed: primary asset {primary_asset_id!r} "
                "cannot be verified (producer registry unavailable)"
            ) from None
    if output_paths:
        meta["output_paths"] = list(output_paths)
    top_level_output_path: str = output_paths[0] if output_paths else ""

    # Strict JSON check on the exact meta we are about to persist (no
    # ``default=str``): a failure here is a local metadata-preparation
    # failure, still before the first history write.
    try:
        json.dumps(meta)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"v2 history success meta is not JSON serializable: {str(exc)[:200]}"
        ) from exc

    # ── First history write: NONTERMINAL ``running`` (accepted started_at;
    #    timings ride along so the V2 mirror stores the full accepted
    #    duration).  The V2 writer creates the generation, request snapshot and
    #    output/featured asset association while the attempt is still running;
    #    the terminal ``completed`` status is applied only by the update below.
    record = REGISTRY.history().record_run(
        kind="playground_run",
        prompt_id=run_history_id,
        status="running",
        started_at=started_at,
        meta=meta,
        workflow_hash=str(plan.workflow_hash or ""),
        timings=timings if timings else None,
    )
    actual_run_id = record.get("run_id", run_history_id) if record else run_history_id

    # Completed => required History output association for modern
    # output-producing runs: the nonterminal ``running`` record must already
    # carry a visible output (path-attached original and/or adopted producer
    # asset).  A missing association is a truthful pre-terminal local failure
    # raised while the attempt is still running, so the caller records a
    # failed Generation/Attempt under the SAME accepted identity — never a
    # completed→failed repair.  Legitimate zero-output plans stay exempt, and
    # a usable ordinary path satisfies the check even when the producer id is
    # unknown.  When the V2 writer is unavailable (headless), skip the check.
    if requires_output:
        try:
            from history_v2_writer import get_writer
            v2_writer = get_writer()
        except ImportError:
            v2_writer = None
        if v2_writer is not None and not v2_writer.generation_has_output_association(
            actual_run_id
        ):
            raise ValueError(
                "v2 history finalization failed: output-producing run "
                f"{actual_run_id!r} has no associated History output"
            )

    # ── Post-record updates: the terminal ``completed`` write plus output/
    #    primary-asset association.  Failures here are loud/log-only, never a
    #    second failure record and never a second attempt. ──
    update_kwargs: dict[str, Any] = {
        "status": "completed",
        "completed_at": completed_at,
        "timings": timings if timings else None,
        "meta": meta,
    }
    if top_level_output_path:
        update_kwargs["output_path"] = top_level_output_path
    if primary_asset_id:
        update_kwargs["primary_asset_id"] = primary_asset_id
    try:
        REGISTRY.history().update_run(actual_run_id, **update_kwargs)
    except Exception as exc:
        _log.warning(
            "Failed to update workflow run %s history after the running "
            "record was written: %s", run_history_id, exc,
        )


async def _record_workflow_run_failure(
    bundle: dict[str, Any],
    values: dict[str, Any],
    error: str,
    *,
    started_at: str,
    completed_at: str,
    run_history_id: str = "",
    mono_start: float | None = None,
    plan: Any = None,
    modal_options: dict[str, Any] | None = None,
) -> None:
    """Record the accepted-modern-boundary failure for a workflow run (best effort).

    Called ONLY after bundle/controls validation succeeded and the V2
    execution attempt actually started.  Fully exception-isolated and lazily
    imports REGISTRY so a History failure can never mask the original
    execution error.

    ``run_history_id`` is the accepted run identity the PlaygroundService
    generated (captured by the injected save callback): a post-execution
    local failure records under the SAME identity so no second run record is
    ever made for one accepted run.  When no capture happened (the service
    never reached its completion hook) a fresh identity is generated.

    ``mono_start`` is the accepted ``time.monotonic()`` reading captured
    immediately before ``await service.execute``.  When supplied,
    ``duration_ms`` comes from ``time.monotonic() - mono_start`` so the stored
    duration reflects the FULL accepted wait (never truncated wall seconds).
    External callers without a monotonic reading fall back to the
    ``started_at`` → ``completed_at`` timestamp math.

    Builds the immutable final ``workflow_json`` from a deep copy of the
    bundle's executable prompt (values applied + the SAME CLIP/VAE repair
    helpers the plan builder uses); when apply fails it retains a plain copy
    of the raw immutable prompt rather than inventing data.  ``workflow_hash``
    is derived from the exact stored ``workflow_json`` via ``prompt_sha256``
    (never the version ``graph_hash``).  No ``output_path`` /
    ``primary_asset_id`` / fabricated asset data is ever included.
    """
    try:
        from datetime import datetime, timezone

        from experiment_service import REGISTRY
        from studio_run_adapter import (
            _repair_missing_clip_inputs,
            _repair_missing_vae_inputs,
        )
        from workflow_metadata import prompt_sha256

        replay_meta = _build_plan_replay_meta(plan, modal_options=modal_options)
        if replay_meta:
            workflow_json = replay_meta["workflow_json"]
            workflow_hash = replay_meta["workflow_hash"]
        else:
            workflow_json: dict[str, Any] = {}
            try:
                applied = apply_workflow_values_to_prompt(
                    bundle.get("executable_prompt") or {},
                    bundle.get("control_schema") or {},
                    values,
                )
                if "workflow" in applied:
                    workflow_json = applied["workflow"]
                    _repair_missing_clip_inputs(workflow_json)
                    _repair_missing_vae_inputs(workflow_json)
                else:
                    workflow_json = _plain_copy(bundle.get("executable_prompt") or {})
            except Exception:
                workflow_json = _plain_copy(bundle.get("executable_prompt") or {})

            workflow_hash = ""
            try:
                workflow_hash = prompt_sha256(workflow_json)
            except Exception:
                workflow_hash = ""

        run_history_id = str(run_history_id or "") or f"play_{uuid.uuid4().hex[:16]}"

        meta: dict[str, Any] = {
            "playground_run": True,
            "workflow_id": str(bundle.get("workflow", {}).get("workflow_id", "") or ""),
            "workflow_version_id": str(
                bundle.get("version", {}).get("workflow_version_id", "") or ""
            ),
            "preset_id": str(bundle.get("preset", {}).get("preset_id", "") or ""),
            "workflow_name": str(bundle.get("workflow", {}).get("name", "") or ""),
            "preset_name": str(bundle.get("preset", {}).get("name", "") or ""),
            "studio_feature_id": "workflow",
            "requested_controls": dict(values or {}),
            "experiment_id": run_history_id,
            "error": str(error or ""),
            "workflow_json": workflow_json,
            "workflow_hash": workflow_hash,
        }
        meta.update(replay_meta)
        if replay_meta.get("model_stack"):
            meta["model_stack"] = replay_meta["model_stack"]

        timings: dict[str, Any] = {"_run_type": "playground_direct"}
        if mono_start is not None:
            # Monotonic accepted-wait duration: exact, never truncated to
            # whole wall seconds (timestamp fallback below is for external
            # callers that do not capture a monotonic start).
            timings["duration_ms"] = round(
                (time.monotonic() - mono_start) * 1000.0, 3
            )
        else:
            try:
                _start = datetime.fromisoformat(str(started_at).replace("Z", "+00:00"))
                _end = datetime.fromisoformat(str(completed_at).replace("Z", "+00:00"))
                if _end >= _start:
                    timings["duration_ms"] = round(
                        (_end - _start).total_seconds() * 1000.0, 3
                    )
            except Exception:
                pass

        record = REGISTRY.history().record_run(
            kind="playground_run",
            prompt_id=run_history_id,
            status="error",
            started_at=started_at,
            meta=meta,
            workflow_hash=workflow_hash,
            timings=timings if timings else None,
        )
        actual_run_id = record.get("run_id", run_history_id) if record else run_history_id
        REGISTRY.history().update_run(
            actual_run_id,
            status="error",
            completed_at=completed_at,
            meta=meta,
            timings=timings,
        )
    except Exception:
        _log.warning("Failed to record workflow run failure for %s", error)


# ── Execution paths ──────────────────────────────────────────────────────


async def _workflow_v2_run(
    bundle: dict[str, Any],
    merged: dict[str, Any],
    preset_id: str,
    node_dir: str | os.PathLike,
    modal_options: dict[str, Any] | None,
    gpu: Any,
    workspace: dict[str, Any] | None,
    trace_ctx: dict[str, Any] | None,
) -> dict[str, Any]:
    """V2 direct single-run via the PlaygroundService (injectable hooks).

    Accepted-execution boundary flow:

    * The UTC ``started_at`` and a ``time.monotonic()`` reading are captured
      immediately before ``await service.execute`` so every duration (failure
      AND success) includes the full accepted wait.
    * The injected ``save_history_fn`` is CAPTURE-ONLY: it records the raw
      post-materialization result projection + callback args and writes NO
      History until after the final result boundary.
    * A successful dict result is normalized recursively, strict-JSON
      validated (``json.dumps`` without ``default=str``), and ONLY then is the
      modern History success preparation/commit performed (accepted
      ``started_at`` drives ``record_run``).  A non-dict accepted result is a
      truthful failure; a non-ok dict failure result is preserved unchanged.
    * Any post-execution local failure (strict JSON, missing capture, history
      metadata preparation, output preflight/association before the first
      history write) records a truthful failure under the same accepted run
      identity and returns ``{"status": "error", "message": <exact bounded
      error>}``.  A completed→failed repair is never allowed: post-record
      update failures are loud/log-only and never create a second attempt.
    """
    from datetime import datetime, timezone

    from comfymodal_runtime.playground_service import PlaygroundService

    version_id = str(bundle.get("version", {}).get("workflow_version_id", "") or "")
    workflow_id = str(bundle.get("workflow", {}).get("workflow_id", ""))
    values = merged.get("values") or {}

    async def _load_preset_fn(pid: str, nd: str) -> tuple[dict, dict, None]:
        snapshot = {
            "executable_prompt": bundle.get("executable_prompt", {}),
            "control_schema": bundle.get("control_schema", {}),
            "mapping": bundle.get("mapping", {}),
            "identity": {
                "workflow_id": workflow_id,
                "workflow_version_id": version_id,
                "preset_id": str(bundle.get("preset", {}).get("preset_id", "")),
                "workflow_name": str(bundle.get("workflow", {}).get("name", "")),
                "preset_name": str(bundle.get("preset", {}).get("name", "")),
            },
        }
        return bundle.get("preset", {}), snapshot, None

    async def _validate_fn(preset: dict, snapshot: dict, fid: str) -> None:
        # Runnable gating already happened in resolve_workflow_run_bundle.
        return None

    def _build_plan_fn(
        preset: dict,
        snapshot: dict,
        fid: str,
        ctrl: dict,
        *,
        modal_options: dict[str, Any] | None = None,
        gpu: Any = None,
    ) -> tuple[Any, str | None]:
        # The controls argument equals the request overrides; merged values
        # already contain preset + overrides, so use those verbatim.
        return build_workflow_execution_plan(
            bundle, values, modal_options=modal_options, trace_ctx=trace_ctx,
            comfyui_root=str(node_dir or ""), gpu=gpu,
        )

    # ── Post-materialization success capture (capture-only, no History write
    #    until AFTER the final result boundary) ──
    capture: dict[str, Any] = {
        "plan": None,
        "result": None,
        "run_history_id": "",
        "status": "completed",
        "completed_at": "",
        "materialized_paths": None,
        "modal_options": _plain_copy(modal_options) if modal_options is not None else None,
    }

    def _observe_plan(plan: Any) -> None:
        capture["plan"] = plan

    async def _capture_save_history(
        plan: Any,
        result: dict[str, Any],
        run_history_id: str,
        status: str = "completed",
        completed_at: str = "",
        materialized_paths: list[str] | None = None,
    ) -> None:
        await _capture_modern_save_history(
            capture, plan, result, run_history_id,
            status=status, completed_at=completed_at,
            materialized_paths=materialized_paths,
        )

    service = PlaygroundService(
        load_preset_fn=_load_preset_fn,
        validate_fn=_validate_fn,
        build_plan_fn=_build_plan_fn,
        save_history_fn=_capture_save_history,
        plan_observer_fn=_observe_plan,
    )

    # Accepted execution boundary: capture the UTC start and monotonic clock
    # immediately before awaiting the service so a failed attempt's duration
    # is based on helper start → terminal time, never frontend/output time.
    started_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    mono_start = time.monotonic()

    try:
        result = await service.execute(
            preset_id=preset_id or version_id,
            feature_id="workflow",
            controls=values,
            node_dir=node_dir,
            modal_options=modal_options,
            gpu=gpu,
            workspace=workspace,
            trace_ctx=trace_ctx,
            profile_setter=None,
            event_sink=None,
        )
    except Exception as exc:
        message = str(exc)[:500]
        _log.warning("Workflow V2 execution raised: %s", message)
        await _record_workflow_run_failure(
            bundle,
            values,
            message,
            started_at=started_at,
            completed_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            mono_start=mono_start,
            plan=capture.get("plan"),
            modal_options=modal_options,
        )
        return {"status": "error", "message": message}

    _completed_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    if not isinstance(result, dict):
        # A non-dict accepted result is a truthful failure (never fabricated).
        message = "v2 execution returned a non-dict result"
        _log.warning("Workflow V2 execution returned a non-dict result: %r", type(result))
        await _record_workflow_run_failure(
            bundle,
            values,
            message,
            started_at=started_at,
            completed_at=_completed_at,
            mono_start=mono_start,
            plan=capture.get("plan"),
            modal_options=modal_options,
        )
        return {"status": "error", "message": message}

    if result.get("status") != "ok":
        message = str(
            result.get("message") or result.get("error") or "v2 execution failed"
        )[:500]
        await _record_workflow_run_failure(
            bundle,
            values,
            message,
            started_at=started_at,
            completed_at=_completed_at,
            mono_start=mono_start,
            plan=capture.get("plan"),
            modal_options=modal_options,
        )
        return result

    # ── Success: normalize the Stage-9 response recursively and strict-JSON
    #    validate (no default=str) BEFORE any History write ──
    try:
        normalized = _plain_copy(result)
        json.dumps(normalized)
    except (TypeError, ValueError) as exc:
        message = f"v2 success result is not JSON serializable: {str(exc)[:200]}"
        _log.warning("Workflow V2 success result failed strict JSON: %s", message)
        await _record_workflow_run_failure(
            bundle,
            values,
            message,
            started_at=started_at,
            completed_at=_completed_at,
            run_history_id=str(capture.get("run_history_id") or ""),
            mono_start=mono_start,
            plan=capture.get("plan"),
            modal_options=modal_options,
        )
        return {"status": "error", "message": message}

    # ── Modern History success preparation/commit (the first history write
    #    happens only after every fallible metadata/output check passed) ──
    try:
        await _modern_save_history_success(
            capture,
            started_at=started_at,
            mono_start=mono_start,
            completed_at=_completed_at,
        )
    except Exception as exc:
        message = f"v2 history success commit failed: {str(exc)[:200]}"
        _log.warning("Workflow V2 history success commit failed: %s", message)
        await _record_workflow_run_failure(
            bundle,
            values,
            message,
            started_at=started_at,
            completed_at=_completed_at,
            run_history_id=str(capture.get("run_history_id") or ""),
            mono_start=mono_start,
            plan=capture.get("plan"),
            modal_options=modal_options,
        )
        return {"status": "error", "message": message}

    return normalized


# H12: the legacy Workflow V1 path (``_workflow_legacy_run`` + its
# submission-time history record and the hardcoded
# ``"execution_mode": "v1"`` compilation metadata) retired together with
# the non-V2 dispatch branch.  Every NEW Workflow run uses the canonical
# immutable V2 plan path via ``_workflow_v2_run``.


# ── Public entrypoint ────────────────────────────────────────────────────


async def handle_workflow_run_async(
    workflow_id: str,
    version_id: str,
    preset_id: str,
    feature_id: str,
    controls: dict[str, Any],
    node_dir: str | os.PathLike,
    trace_ctx: dict[str, Any] | None = None,
    *,
    gpu: Any = None,
    modal_options: dict[str, Any] | None = None,
    workspace: dict[str, Any] | None = None,
    allow_remote_execution: bool = False,
) -> dict[str, Any]:
    """Async handler for a single Studio Workflow run.

    1. Resolve + gate the workflow run bundle (version runnable state is
       authoritative; unrunnable → error with reasons).
    2. Merge preset + request overrides and validate controls STRICT.
    3. Resolve execution mode (request/env/server-setting/default, captured
       into ``trace_ctx``) exactly like ``handle_studio_run_async``; an
       explicitly retired engine is rejected (``EXECUTION_MODE_RETIRED``).
    4. V2-only: ``PlaygroundService.execute`` with injected hooks builds the
       immutable ExecutionPlan and dispatches through Modal V2 transport.

    Returns the same result dict shapes as the legacy adapter.
    """
    try:
        bundle = resolve_workflow_run_bundle(
            workflow_id, version_id, preset_id, node_dir,
            allow_remote_execution=allow_remote_execution,
        )
        if bundle.get("status") != "ok":
            return bundle

        merged = merge_workflow_controls(
            bundle["preset"], controls or {}, bundle["control_schema"]
        )
        if merged["errors"]:
            return {
                "status": "error",
                "error_code": "WORKFLOW_CONTROL_VALIDATION",
                "message": "; ".join(
                    f"{e['field']}: {e['message']}" for e in merged["errors"]
                ),
                "errors": merged["errors"],
            }

        # ── Execution-mode resolution (mirrors handle_studio_run_async) ──
        from execution_runtime import resolve_execution_mode, retired_mode_error

        _req_settings: dict = {}
        try:
            from __init__ import _load_modal_settings as _ls
            _req_settings = _ls()
        except Exception:
            pass
        resolved = resolve_execution_mode(
            modal_options=modal_options,
            modal_settings=_req_settings,
            extra=trace_ctx,
        )
        mode = resolved["mode"]

        # ── H12: V2-only execution ──
        # A NEW Workflow request explicitly carrying a retired engine
        # (v1/legacy/shadow) is rejected truthfully before acceptance.
        if resolved.get("retired"):
            return {
                "status": "error",
                "error_code": "EXECUTION_MODE_RETIRED",
                "message": retired_mode_error(mode),
            }

        _effective_modal_options = dict(modal_options or {})
        _effective_modal_options["execution_mode"] = mode

        if isinstance(trace_ctx, dict):
            trace_ctx["execution_mode"] = mode
            trace_ctx["execution_mode_source"] = resolved["source"]

        # ── F8: capture the GPU once at acceptance ──
        # Precedence: explicit request override → modal_options.gpu →
        # canonical persisted/default server GPU.  Frozen into the plan;
        # later Settings changes affect future submissions only.
        from studio_run_adapter import resolve_request_gpu as _resolve_request_gpu
        try:
            _selected_gpu, _gpu_source = _resolve_request_gpu(gpu, modal_options)
        except ValueError as exc:
            return {"status": "error", "message": str(exc)}
        if isinstance(trace_ctx, dict):
            trace_ctx["selected_gpu"] = _selected_gpu
            trace_ctx["selected_gpu_source"] = _gpu_source

        _preset_id = str(preset_id or "")
        # H12: V2 is the only executable Workflow path.
        return await _workflow_v2_run(
            bundle, merged, _preset_id, node_dir,
            _effective_modal_options, _selected_gpu, workspace, trace_ctx,
        )
    except Exception as exc:
        _log.warning("Workflow run failed: %s", exc)
        return {"status": "error", "message": str(exc)[:500]}
