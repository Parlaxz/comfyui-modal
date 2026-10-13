"""Backend adapter for Studio Workflow platform runs (modern Studio lane).

Bridges the Studio Workflow domain (``studio_domain``: workflows, immutable
versions, mappings, presets) into the canonical single-run execution path —
the SAME hard-stop boundary as the legacy Studio preset surface:

* **V2 (only engine, H12)** → ``comfymodal_runtime.playground_service.PlaygroundService``
  (injectable load/validate/build-plan/save-history hooks).  Requests that
  explicitly carry a retired engine (v1/legacy/shadow) are rejected with
  ``EXECUTION_MODE_RETIRED`` before acceptance; the former v1/shadow
  submission-time path was retired in H12.

All controls are validated against the version mapping's control schema and
applied into the executable prompt without type coercion.  The one path-only
compatibility normalization is flattening model-loader subfolder names.
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

_MODEL_LOADER_INPUTS = {
    "CheckpointLoaderSimple": ("ckpt_name",),
    "CLIPLoader": ("clip_name",),
    "DualCLIPLoader": ("clip_name1", "clip_name2"),
    "UNETLoader": ("unet_name",),
    "VAELoader": ("vae_name",),
}


_MODEL_LOADER_FIELDS = frozenset(
    field for fields in _MODEL_LOADER_INPUTS.values() for field in fields
)


def _normalize_model_name(value: Any) -> Any:
    """Flatten a model-library path to the name exposed by the model volume."""
    if not isinstance(value, str):
        return value
    return value.strip().replace("\\", "/").rsplit("/", 1)[-1]


def _normalize_model_loader_names(workflow: dict[str, Any]) -> None:
    """Match model-library installs, which flatten loader subfolder names."""
    for node in workflow.values():
        if not isinstance(node, dict):
            continue
        fields = _MODEL_LOADER_INPUTS.get(str(node.get("class_type", "")), ())
        inputs = node.get("inputs")
        if not isinstance(inputs, dict):
            continue
        for field in fields:
            value = inputs.get(field)
            if isinstance(value, str):
                # UI controls can send the model-library subfolder prefix
                # (notably ``krea2\\...``), while the deployed model volume
                # exposes the installed basename to ComfyUI.
                inputs[field] = _normalize_model_name(value)


# ── Domain service construction (mirrors studio_workflow_routes.py) ──────


_DOMAIN_SERVICE_CACHE: dict[str, Any] = {}
_DOMAIN_SERVICE_SIG: dict[str, tuple] = {}

_STORE_FILENAMES = (
    ".studio_workflows.json",
    ".studio_workflow_versions.json",
    ".studio_workflow_mappings.json",
    ".studio_workflow_presets.json",
)


def _store_signature(node_dir: str | os.PathLike) -> tuple:
    """Fingerprint the store files so any write invalidates the cached service."""
    sig = []
    for name in _STORE_FILENAMES:
        try:
            st = os.stat(os.path.join(str(node_dir), name))
            sig.append((name, st.st_mtime_ns, st.st_size))
        except OSError:
            sig.append((name, 0, 0))
    return tuple(sig)


def invalidate_domain_service_cache() -> None:
    """Drop the cached WorkflowDomainService. Call after any store mutation."""
    _DOMAIN_SERVICE_CACHE.clear()
    _DOMAIN_SERVICE_SIG.clear()


def _get_domain_service(node_dir: str | os.PathLike) -> Any:
    """Return a ``WorkflowDomainService`` over the store files under *node_dir*.

    Construction mirrors ``studio_workflow_routes.register_workflow_routes``:
    the same store root (``.studio_workflows.json`` / ``.studio_workflow_versions.json``
    / ``.studio_workflow_mappings.json`` / ``.studio_workflow_presets.json``)
    and the dependency resolver's ``reasons_for`` wired as the
    ``dependency_provider`` when available.  The resolver is lazily built and
    any construction failure degrades to ``dependency_provider=None`` (the
    same behaviour as the routes when no resolver is supplied).

    The instance is memoised per *node_dir* because building a fresh service on
    every call discards its internal store cache, and re-reading the 1.4MB
    version store cost 2.5s on every run's critical path - before the request was
    even submitted. Measured on one instance: first ``get_version`` 2.499s,
    second 0.122s. The cache key includes the mtime+size of every store file, so
    any write rebuilds the service and no stale record can be served.
    """
    key = os.path.abspath(str(node_dir))
    sig = _store_signature(key)
    cached = _DOMAIN_SERVICE_CACHE.get(key)
    if cached is not None and _DOMAIN_SERVICE_SIG.get(key) == sig:
        return cached

    from studio_domain.services import WorkflowDomainService

    resolver = None
    try:
        from dependency_resolver import DependencyResolver
        _nd = key
        resolver = DependencyResolver(_nd, os.path.dirname(os.path.dirname(_nd)))
    except Exception:
        resolver = None
    service = WorkflowDomainService(
        key,
        dependency_provider=(resolver.reasons_for if resolver is not None else None),
    )
    _DOMAIN_SERVICE_CACHE[key] = service
    _DOMAIN_SERVICE_SIG[key] = sig
    return service


# ── Bundle resolution ─────────────────────────────────────────────────────


def resolve_workflow_run_bundle(
    workflow_id: str,
    version_id: str,
    node_dir: str | os.PathLike,
    *,
    remote_model_readiness: bool = False,
) -> dict[str, Any]:
    """Resolve and gate a workflow run: workflow + version + mapping.

    Returns ``{"status": "ok", "workflow", "version", "mapping", "state",
    "executable_prompt", "control_schema", "defaults"}`` or a fail-closed
    error dict (``{"status": "error", "error_code", "message", ...}``).

    * Version resolution: empty ``version_id`` → the workflow's latest version.
    * Runnable gate: the version's derived state must be ``runnable``; an
      incomplete version returns ``WORKFLOW_VERSION_NOT_RUNNABLE`` with the
      derivation reasons (never guessed).

    There is no preset: control defaults are read from the version's own
    ``executable_prompt`` (see ``default_controls_from_version``).
    """
    service = _get_domain_service(node_dir)
    workflow_id = str(workflow_id or "")
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
    if remote_model_readiness and not state.get("runnable"):
        # Golden resolves models in the deployed Modal volume. Host-local model
        # absence must not block a remote workflow before dispatch; all other
        # workflow/dependency/mapping reasons remain fail-closed.
        reasons = [
            reason for reason in (state.get("reasons") or [])
            if not str(reason).startswith("missing model ")
        ]
        state = {
            **state,
            "reasons": reasons,
            "runnable": not reasons,
            "status": "ready" if not reasons else "incomplete",
        }
    if not state.get("runnable"):
        return {
            "status": "error",
            "error_code": "WORKFLOW_VERSION_NOT_RUNNABLE",
            "message": "workflow version is not runnable",
            "reasons": list(state.get("reasons") or []),
        }

    mapping = service.get_mapping(version_id)
    if mapping is None:
        return {
            "status": "error",
            "error_code": "WORKFLOW_MAPPING_MISSING",
            "message": f"workflow version {version_id!r} has no mapping",
        }

    executable_prompt = version.get("executable_prompt") or {}
    if not isinstance(executable_prompt, dict):
        executable_prompt = {}
    control_schema: dict[str, Any] = {}
    for entry in mapping.get("entries") or []:
        if isinstance(entry, dict) and entry.get("semantic_role"):
            control_schema[str(entry["semantic_role"])] = entry
    bundle = {
        "status": "ok",
        "workflow": workflow,
        "version": version,
        "mapping": mapping,
        "state": state,
        "executable_prompt": executable_prompt,
        "control_schema": control_schema,
        "defaults": default_controls_from_version(executable_prompt, control_schema),
    }
    return _refresh_ui_workflow_bundle(bundle)


def _refresh_ui_workflow_bundle(bundle: dict[str, Any]) -> dict[str, Any]:
    """Rebuild the runtime bundle from a stored UI graph when one is present.

    Versions are immutable and may have been captured with an older widget
    ordering.  Keep the stored record intact, but make the run use one prompt,
    mapping, schema, and default set derived from the current UI graph.  API
    prompt versions are deliberately untouched so arbitrary workflows retain
    their existing behavior.

    Subgraph/group-nested graphs are never regenerated: the stored executable
    prompt (expanded ``"<outer>:<inner>"`` keys from live ``graphToPrompt``)
    is authoritative, while ``ui_graph_to_api_prompt`` only converts the
    top-level ``nodes`` list and would silently drop every nested node —
    wiping stored bindings and their defaults (e.g. ``missing required
    control 'clip'`` on subgraph workflows).
    """
    version = bundle.get("version") or {}
    graph_json = version.get("graph_json") if isinstance(version, dict) else None
    try:
        from studio_domain.graph import (
            derive_mapping_candidates,
            is_ui_workflow_format,
            ui_graph_has_nested_containers,
            ui_graph_to_api_prompt,
        )

        if not is_ui_workflow_format(graph_json):
            return bundle
        if ui_graph_has_nested_containers(graph_json):
            return bundle
        regenerated = ui_graph_to_api_prompt(graph_json)
        if not regenerated:
            return bundle
        # Safety net: never replace the stored prompt when regeneration
        # would drop a stored binding target (stale defs, unknown classes,
        # or any other conversion gap). Dropping the prompt also drops its
        # defaults, surfacing as ``missing required control`` at run time.
        try:
            stored_mapping = bundle.get("mapping") or {}
            stored_entries = stored_mapping.get("entries") or []
            if isinstance(stored_entries, dict):
                stored_entries = list(stored_entries.values())
            for stored in stored_entries:
                if not isinstance(stored, dict):
                    continue
                nid = str(stored.get("node_id") or "")
                iname = str(stored.get("input_name") or "")
                if not nid or not iname:
                    continue
                node = regenerated.get(nid)
                if not isinstance(node, dict):
                    return bundle
                inputs = node.get("inputs")
                if not isinstance(inputs, dict) or iname not in inputs:
                    return bundle
        except Exception:
            pass

        entries, output_node_id = derive_mapping_candidates({
            "graph_json": graph_json,
            "api_prompt_json": regenerated,
        })
        mapping = copy.deepcopy(bundle.get("mapping") or {})
        if entries:
            stored_entries = mapping.get("entries") or []
            if isinstance(stored_entries, dict):
                stored_entries = list(stored_entries.values())
            stored_entries = [
                copy.deepcopy(entry)
                for entry in stored_entries
                if isinstance(entry, dict) and entry.get("semantic_role")
            ]

            # Stored semantic roles are part of the public Studio contract.
            # The graph re-derivation only refreshes their binding metadata;
            # it must not rename aliases such as ``cfg_scale`` → ``cfg``.
            fresh_by_binding = {
                (
                    str(entry.node_id),
                    str(entry.input_name),
                ): entry.to_dict()
                for entry in entries.values()
                if entry.node_id and entry.input_name
            }
            fresh_by_role = {
                str(entry.semantic_role): entry.to_dict()
                for entry in entries.values()
                if entry.semantic_role
            }
            refreshed_entries: list[dict[str, Any]] = []
            stored_bindings: set[tuple[str, str]] = set()
            for stored in stored_entries:
                binding = (
                    str(stored.get("node_id") or ""),
                    str(stored.get("input_name") or ""),
                )
                fresh = fresh_by_binding.get(binding)
                if fresh is None:
                    # A stored catalog role can be the alias of the graph's
                    # role (and older records may have an empty binding).
                    # Reuse the fresh candidate while retaining the stored
                    # semantic_role used by the UI and persistence layer.
                    stored_role = str(stored["semantic_role"])
                    fresh = fresh_by_role.get(
                        stored_role,
                    ) or fresh_by_role.get(
                        _CONTROL_ROLE_ALIASES.get(stored_role, "")
                    )
                if fresh is not None:
                    alias = str(stored["semantic_role"])
                    refreshed_entry = copy.deepcopy(fresh)
                    refreshed_entry["semantic_role"] = alias
                    refreshed_entries.append(refreshed_entry)
                    refreshed_binding = (
                        str(refreshed_entry.get("node_id") or ""),
                        str(refreshed_entry.get("input_name") or ""),
                    )
                    if all(refreshed_binding):
                        stored_bindings.add(refreshed_binding)
                else:
                    refreshed_entries.append(stored)

            # New graph controls are useful only when their node/input has no
            # stored mapping.  This is also what keeps one fresh canonical
            # role from displacing several historical aliases on a binding.
            for binding, fresh in fresh_by_binding.items():
                if binding not in stored_bindings and not any(
                    (
                        str(entry.get("node_id") or ""),
                        str(entry.get("input_name") or ""),
                    ) == binding
                    for entry in stored_entries
                ):
                    refreshed_entries.append(copy.deepcopy(fresh))
            mapping["entries"] = refreshed_entries
        stored_output_node_id = str(mapping.get("output_node_id") or "")
        if stored_output_node_id in regenerated:
            # A stored mapping may intentionally target a non-first output
            # node.  Keep that user choice when the regenerated graph still
            # contains it; only fall back to the fresh candidate if it does
            # not.
            output_node_id = stored_output_node_id
        if output_node_id:
            mapping["output_node_id"] = output_node_id

        # A required input may be omitted by the UI→API conversion.  Let the
        # live node schema supply an explicit default before defaults are read;
        # inputs with no schema default remain absent and fail required
        # validation later.  In particular, never manufacture image data.
        _hydrate_missing_required_widget_defaults(regenerated)

        control_schema = {
            str(entry["semantic_role"]): entry
            for entry in (mapping.get("entries") or [])
            if isinstance(entry, dict) and entry.get("semantic_role")
        }
        refreshed = dict(bundle)
        refreshed["executable_prompt"] = regenerated
        refreshed["mapping"] = mapping
        refreshed["control_schema"] = control_schema
        refreshed["defaults"] = default_controls_from_version(
            regenerated, control_schema
        )
        return refreshed
    except Exception:
        # Keep the prior stored-prompt path as a compatibility fallback for a
        # malformed graph or an unavailable node registry.
        return bundle


# ── Control validation / merge ───────────────────────────────────────────


# The graph/domain layers historically used ``positive_prompt`` while the
# Studio catalog and request API use ``prompt``.  This is deliberately the
# only runtime role alias: stored mapping entries retain their original
# semantic_role for display and persistence.
_CONTROL_ROLE_ALIASES = {
    "prompt": "positive_prompt",
    "positive_prompt": "prompt",
}


def _control_schema_key(
    control_schema: dict[str, Any],
    role: str,
) -> str | None:
    """Resolve the requested role to the schema's stored role.

    Prefer an exact, usable binding.  If an old schema contains an empty
    catalog-role entry alongside a usable aliased entry, use the usable one;
    this prevents a stale ``prompt`` placeholder from masking
    ``positive_prompt`` (and vice versa).
    """
    if role in control_schema:
        entry = control_schema.get(role)
        if isinstance(entry, dict) and entry.get("node_id") and entry.get("input_name"):
            return role
        alias = _CONTROL_ROLE_ALIASES.get(role)
        if alias in control_schema:
            aliased = control_schema.get(alias)
            if isinstance(aliased, dict) and aliased.get("node_id") and aliased.get("input_name"):
                return alias
        return role
    alias = _CONTROL_ROLE_ALIASES.get(role)
    if alias in control_schema:
        return alias
    return None


def _normalize_controls_to_schema(
    controls: dict[str, Any],
    control_schema: dict[str, Any],
) -> dict[str, Any]:
    """Key request/default values by the schema's stored semantic roles."""
    normalized: dict[str, Any] = {}
    for role, value in (controls or {}).items():
        schema_role = _control_schema_key(control_schema, role)
        normalized[schema_role or role] = value
    return normalized


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


def _is_image_control(role: str, entry: dict[str, Any]) -> bool:
    """True for Source Image / Mask inputs.

    These reference files by name and the input directory changes on every
    upload, so a captured ``enum_options`` snapshot of its contents is never
    a closed vocabulary and must not gate the value.
    """
    if role in ("source_image", "mask"):
        return True
    return isinstance(entry, dict) and entry.get("control_kind") == "image"


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
        schema_key = _control_schema_key(control_schema, key)
        entry = control_schema.get(schema_key) if schema_key is not None else None
        if entry is None:
            errors.append({"field": key, "message": f"unknown control {key!r}"})
            continue

        enum_options = entry.get("enum_options") or []
        if enum_options and not _is_image_control(schema_key or key, entry):
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


def default_controls_from_version(
    executable_prompt: dict[str, Any],
    control_schema: dict[str, Any],
) -> dict[str, Any]:
    """Read each mapped control's current value out of the version's own graph.

    A workflow version is self-describing: the node inputs captured in
    ``executable_prompt`` already hold the values a run should start from, so
    no separate preset record is needed to supply defaults.

    Only roles that appear in ``control_schema`` are read, and only scalar
    widget values are copied (dicts/lists are node configuration, not control
    values). Roles with no matching node or widget are simply absent, which the
    required-control check in ``merge_workflow_controls`` then reports.
    """
    defaults: dict[str, Any] = {}
    if not isinstance(executable_prompt, dict):
        return defaults
    for role, entry in (control_schema or {}).items():
        if not isinstance(entry, dict):
            continue
        node_id = str(entry.get("node_id") or "")
        input_name = str(entry.get("input_name") or "")
        if not node_id or not input_name:
            continue
        node = executable_prompt.get(node_id)
        if not isinstance(node, dict):
            continue
        node_inputs = node.get("inputs")
        if not isinstance(node_inputs, dict) or input_name not in node_inputs:
            continue
        value = node_inputs.get(input_name)
        if isinstance(value, (dict, list)):
            continue
        if input_name in _MODEL_LOADER_FIELDS:
            value = _normalize_model_name(value)
        defaults[role] = value
    return defaults


def merge_workflow_controls(
    defaults: dict[str, Any],
    overrides: dict[str, Any],
    control_schema: dict[str, Any],
) -> dict[str, Any]:
    """Merge version-derived defaults + request overrides, then validate.

    Base = ``defaults`` keyed by semantic role (see
    ``default_controls_from_version``).  Request overrides are applied on top
    (only keys present in *overrides*; overrides win).

    The merged dict is validated with ``validate_workflow_controls`` and any
    required mapping role missing from the merged values adds a
    ``"missing required control '<role>'"`` error.

    Returns ``{"values": merged, "errors": [...]}``.
    """
    control_schema = control_schema or {}
    defaults = _normalize_controls_to_schema(defaults or {}, control_schema)
    overrides = _normalize_controls_to_schema(overrides or {}, control_schema)

    merged: dict[str, Any] = dict(defaults)
    for key, value in overrides.items():
        # The Studio UI serializes an untouched sampler selector as null.
        # Keep the value regenerated from the current graph in that case;
        # when no graph default exists, retaining None below still exercises
        # the normal required/enum validation path.
        entry = control_schema.get(key)
        if (
            value is None
            and key in defaults
            and isinstance(entry, dict)
            and str(entry.get("input_name") or "") == "sampler_name"
        ):
            continue
        if (
            isinstance(entry, dict)
            and str(entry.get("input_name") or "") in _MODEL_LOADER_FIELDS
        ):
            # Normalize before strict enum validation as well as again at the
            # executable-prompt seam.  Otherwise ``krea2\\name`` is rejected
            # against the live allowed basename ``name`` before the workflow
            # can reach the loader normalizer.
            value = _normalize_model_name(value)
        if (
            isinstance(value, str)
            and not _is_numeric(value)
            and isinstance(entry, dict)
            and str(entry.get("control_kind") or "") in ("number", "integer")
        ):
            # A non-numeric string can never be a legitimate value from our
            # own numeric controls — it is stale UI state (e.g. a
            # control_after_generate token surfacing as a numeric control).
            # ComfyUI would choke on it deep inside sampling, so drop the
            # override and let the graph-derived default win instead.
            continue
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
    request["skip_text_generate"] = bool(
        request_metadata.get("skip_text_generate", False)
    )
    request["text_generate_node_id"] = request_metadata.get(
        "text_generate_node_id"
    )
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
        "skip_text_generate": request_metadata.get("skip_text_generate", False),
        "text_generate_node_id": request_metadata.get("text_generate_node_id"),
    }


def _resolve_execution_target(
    workflow: dict[str, Any],
    executable_prompt: dict[str, Any],
    ui_graph: Any,
    node_id: str,
    input_name: str,
) -> tuple[str, str] | None:
    """Resolve a stored mapping target to its executable prompt key.

    Direct hits pass through. Subgraph UI ids resolve without guessing:
    outer containers via the subgraph ``inputNode`` mapping (needs
    ``ui_graph``) and inner-local ids via a unique ``":<id>"`` suffix match
    against the executable prompt. Returns ``(node_id, input_name)`` or None.
    Never raises.
    """
    try:
        if not node_id or not input_name:
            return None
        node = workflow.get(node_id)
        if isinstance(node, dict):
            inputs = node.get("inputs")
            if isinstance(inputs, dict) and input_name in inputs:
                return (node_id, input_name)
        if ":" in node_id:
            return None
        if ui_graph is not None:
            try:
                from studio_domain.graph import _resolve_outer_widget_to_expanded
            except Exception:
                _resolve_outer_widget_to_expanded = None  # type: ignore[assignment]
            if _resolve_outer_widget_to_expanded is not None:
                try:
                    expanded = _resolve_outer_widget_to_expanded(
                        executable_prompt, ui_graph, node_id, input_name
                    )
                except Exception:
                    expanded = None
                if expanded is not None:
                    return expanded
        suffix = f":{node_id}"
        matches: list[str] = []
        try:
            for key, candidate in workflow.items():
                if not isinstance(key, str) or not key.endswith(suffix):
                    continue
                if not isinstance(candidate, dict):
                    continue
                inputs = candidate.get("inputs")
                if isinstance(inputs, dict) and input_name in inputs:
                    matches.append(key)
        except Exception:
            matches = []
        if len(matches) == 1:
            return (matches[0], input_name)
    except Exception:
        pass
    return None


def apply_workflow_values_to_prompt(
    executable_prompt: dict[str, Any],
    control_schema: dict[str, Any],
    values: dict[str, Any],
    ui_graph: Any = None,
) -> dict[str, Any]:
    """Apply control values VERBATIM into a deep copy of the executable prompt.

    Each (role, value) is resolved through the mapping entry's ``node_id`` +
    ``input_name``.  ``kind=="widget"`` entries store the widget value under
    ``node["inputs"][input_name]`` (ComfyUI API prompts keep widget values in
    ``inputs``).  Unresolvable mappings block with an error (never guessed).

    Subgraph mappings stored as UI ids (outer ``"30"`` or inner-local
    ``"10"``) resolve to their expanded ``"30:10"`` executable key via
    ``_resolve_execution_target``; stored expanded ids pass through
    unchanged.

    After all writes every written value is read back and asserted identical
    (``==`` with equal types); a mismatch is a hard error.

    Returns ``{"workflow": applied_prompt}`` or ``{"error": message}``.
    """
    if not isinstance(executable_prompt, dict):
        return {"error": "executable prompt is not a dict"}
    workflow = copy.deepcopy(executable_prompt)

    resolved_targets: dict[str, tuple[str, str]] = {}
    for role, value in (values or {}).items():
        schema_role = _control_schema_key(control_schema, role)
        entry = control_schema.get(schema_role) if schema_role is not None else None
        if entry is None:
            return {"error": f"control {role!r} has no mapping entry; cannot resolve"}
        node_id = str(entry.get("node_id", "") or "")
        input_name = str(entry.get("input_name", "") or "")
        if not node_id or not input_name:
            return {"error": f"mapped control {role!r} has no node/input binding"}
        target = _resolve_execution_target(
            workflow, executable_prompt, ui_graph, node_id, input_name
        )
        if target is None:
            node = workflow.get(node_id)
            if not isinstance(node, dict):
                return {
                    "error": (
                        f"mapped control {role!r} cannot be resolved: "
                        f"node {node_id} not present"
                    ),
                }
            return {
                "error": (
                    f"mapped control {role!r} cannot be resolved: node {node_id} "
                    f"input {input_name!r} not present"
                ),
            }
        resolved_targets[role] = target
        node = workflow.get(target[0])
        if not isinstance(node, dict):
            return {
                "error": (
                    f"mapped control {role!r} cannot be resolved: "
                    f"node {target[0]} not present"
                ),
            }
        inputs = node.get("inputs")
        if not isinstance(inputs, dict) or target[1] not in inputs:
            return {
                "error": (
                    f"mapped control {role!r} cannot be resolved: node {target[0]} "
                    f"input {target[1]!r} not present"
                ),
            }
        inputs[target[1]] = value

    # Read back and assert verbatim identity.
    for role, value in (values or {}).items():
        target = resolved_targets.get(role)
        if target is None:
            schema_role = _control_schema_key(control_schema, role)
            entry = control_schema.get(schema_role) if schema_role is not None else None
            if entry is None:
                return {
                    "error": f"control {role!r} has no mapping entry; cannot resolve"
                }
            node_id = str(entry.get("node_id", "") or "")
            input_name = str(entry.get("input_name", "") or "")
            target = (node_id, input_name)
        node = workflow.get(target[0])
        written = None
        if isinstance(node, dict):
            inputs = node.get("inputs")
            if isinstance(inputs, dict):
                written = inputs.get(target[1])
        if not _values_identical(written, value):
            return {
                "error": (
                    f"mapped control {role!r} read-back mismatch: wrote "
                    f"{value!r} but node {target[0]} input {target[1]!r} holds "
                    f"{written!r}"
                ),
            }

    return {"workflow": workflow}


def _replace_text_generate_output_refs(
    value: Any, node_id: str, replacement: Any
) -> Any:
    """Replace ComfyUI links to one node's generated-text output."""
    if isinstance(value, (list, tuple)) and len(value) == 2:
        if str(value[0]) == node_id and value[1] == 0:
            return copy.deepcopy(replacement)
    if isinstance(value, dict):
        return {
            key: _replace_text_generate_output_refs(item, node_id, replacement)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_replace_text_generate_output_refs(item, node_id, replacement) for item in value]
    if isinstance(value, tuple):
        return tuple(
            _replace_text_generate_output_refs(item, node_id, replacement)
            for item in value
        )
    return value


def _contains_text_generate_ref(value: Any, node_id: str) -> bool:
    if isinstance(value, (list, tuple)) and len(value) == 2:
        try:
            return str(value[0]) == node_id
        except Exception:
            return False
    if isinstance(value, dict):
        return any(_contains_text_generate_ref(item, node_id) for item in value.values())
    if isinstance(value, (list, tuple)):
        return any(_contains_text_generate_ref(item, node_id) for item in value)
    return False


def _validate_text_generate_target(
    workflow: dict[str, Any], node_id: Any
) -> str | None:
    """Validate a stored TextGenerate bypass target against the effective graph."""
    if node_id is None or node_id == "":
        return "TextGenerate bypass is requested but the mapping has no bound node"
    if not isinstance(node_id, str):
        return "mapped text_generate_node_id must be a string or null"
    node = workflow.get(node_id)
    if not isinstance(node, dict):
        return f"mapped TextGenerate node {node_id!r} is not present in the executable prompt"
    if node.get("class_type") not in {"TextGenerate", "TextGenerateLTX2Prompt"}:
        return "mapped text_generate_node_id must target TextGenerate or TextGenerateLTX2Prompt"
    inputs = node.get("inputs")
    if not isinstance(inputs, dict) or "prompt" not in inputs:
        return f"mapped TextGenerate node {node_id!r} has no executable prompt input"
    declared_outputs = next(
        (node.get(key) for key in ("return_types", "output_types", "outputs")
         if node.get(key) is not None),
        None,
    )
    if declared_outputs is not None:
        first = (
            declared_outputs[0]
            if isinstance(declared_outputs, (list, tuple)) and declared_outputs
            else None
        )
        first_type = first.get("type") if isinstance(first, dict) else first
        first_name = first.get("name") if isinstance(first, dict) else None
        if str(first_type or "").upper() not in {"STRING", "STR"} or (
            first_name is not None and str(first_name) != "generated_text"
        ):
            return f"mapped TextGenerate node {node_id!r} output slot 0 is not generated text"
    # Both supported node classes expose generated text at slot 0.  Any
    # consumed secondary output would be lost by removing the node.
    for other in workflow.values():
        if isinstance(other, dict) and _contains_text_generate_ref(
            other.get("inputs"), node_id
        ):
            def _has_nonzero_ref(value: Any) -> bool:
                if isinstance(value, (list, tuple)) and len(value) == 2:
                    try:
                        return str(value[0]) == node_id and value[1] != 0
                    except Exception:
                        return False
                if isinstance(value, dict):
                    return any(_has_nonzero_ref(item) for item in value.values())
                if isinstance(value, (list, tuple)):
                    return any(_has_nonzero_ref(item) for item in value)
                return False
            if _has_nonzero_ref(other.get("inputs")):
                return f"TextGenerate node {node_id!r} has a consumed secondary output; it cannot be bypassed"
    return None


def prepare_effective_prompt(
    executable_prompt: dict[str, Any],
    control_schema: dict[str, Any],
    values: dict[str, Any],
    mapping: dict[str, Any] | None,
    modal_options: dict[str, Any] | None = None,
    ui_graph: Any = None,
) -> dict[str, Any]:
    """Apply controls, then perform the stored TextGenerate bypass if requested.

    The returned workflow is always a deep copy.  The mapping is the sole
    source of the bypass target; request options carry intent only.

    When skipping, downstream consumes the Playground shelf prompt (the
    merged ``prompt`` control value) — not the node's wired ``inputs.prompt``,
    which is often a template/formula output.  The node input is only the
    fallback when no shelf prompt value is present.
    """
    applied = apply_workflow_values_to_prompt(
        executable_prompt, control_schema, values, ui_graph=ui_graph
    )
    if "error" in applied:
        return applied
    options = {} if modal_options is None else modal_options
    if not isinstance(options, dict):
        return {"error": "modal_options must be an object"}
    skip = options.get("skip_text_generate", False)
    if type(skip) is not bool:
        return {"error": "modal_options.skip_text_generate must be a boolean"}
    target = (mapping or {}).get("text_generate_node_id")
    metadata = {
        "skip_text_generate": skip,
        "text_generate_node_id": target if target not in ("", None) else None,
    }
    workflow = applied["workflow"]
    _synced = _sync_mask_editor_widget_state(workflow, values)
    if _synced:
        _log.debug("Studio synced mask widget state on node(s): %s", _synced)
    if not skip:
        return {"workflow": workflow, "studio_meta": metadata}
    error = _validate_text_generate_target(workflow, target)
    if error:
        return {"error": error}
    node = workflow[str(target)]
    prompt_role = _control_schema_key(control_schema, "prompt")
    shelf_prompt = (
        values.get(prompt_role)
        if prompt_role is not None and isinstance(values, dict)
        else None
    )
    if isinstance(shelf_prompt, str):
        # Skip means "use exactly what I typed in the shelf", even when
        # empty — the node's wired template/formula output is bypassed too.
        replacement = copy.deepcopy(shelf_prompt)
        metadata["text_generate_prompt_source"] = "shelf"
    else:
        # Fall back to the node's pre-control prompt: apply() may already
        # have overwritten the applied copy with the unusable shelf value.
        original = executable_prompt.get(str(target)) if isinstance(executable_prompt, dict) else None
        original_inputs = original.get("inputs") if isinstance(original, dict) else None
        if isinstance(original_inputs, dict) and "prompt" in original_inputs:
            replacement = copy.deepcopy(original_inputs["prompt"])
        else:
            replacement = copy.deepcopy(node["inputs"]["prompt"])
        metadata["text_generate_prompt_source"] = "node_input"
    effective = _replace_text_generate_output_refs(workflow, str(target), replacement)
    if _contains_text_generate_ref(effective, str(target)):
        return {
            "error": (
                f"TextGenerate node {target!r} still has unsupported references "
                "after bypass"
            )
        }
    effective.pop(str(target), None)
    return {"workflow": effective, "studio_meta": metadata}


def _sync_mask_editor_widget_state(
    workflow: dict[str, Any], values: dict[str, Any]
) -> list[str]:
    """Mirror a Studio mask filename into Pixaroma-style editor widget state.

    PixaromaInpaintCrop's MASK *link* input only accepts MASK tensors:
    resolve_inpaint_mask() drops anything else, so a mask filename
    submitted there is silently ignored and the crop falls back to the
    whole image (a painted mask with a full-image edit). The node instead
    reads its own editor file via
    ``inputs["InpaintCropWidget"] = {"state_json": {"mask_path": ...}}``.

    The node_input mapping is kept as-is (the remote file collector keys
    off the ``mask`` input string to ship the bytes); this additionally
    writes ``mask_path`` into any InpaintCropWidget dict already present
    on the applied copy. No-op when the mask value is blank, the widget
    is absent, or its state cannot be merged into. Returns synced node
    ids (diagnostics only).
    """
    synced: list[str] = []
    if not isinstance(workflow, dict) or not isinstance(values, dict):
        return synced
    raw = values.get("mask", "")
    name = raw.strip() if isinstance(raw, str) else ""
    if not name:
        return synced
    # Strip annotated references ("file [input]") to the bare input-dir file.
    for suffix in (" [input]", " [output]", " [temp]"):
        if name.endswith(suffix):
            name = name[: -len(suffix)].rstrip()
            break
    if not name or "/" in name.replace("\\", "/") or name in (".", ".."):
        return synced
    for node_id, node in workflow.items():
        if not isinstance(node, dict):
            continue
        inputs = node.get("inputs")
        if not isinstance(inputs, dict):
            continue
        widget = inputs.get("InpaintCropWidget")
        if not isinstance(widget, dict):
            continue
        try:
            sj = widget.get("state_json", "{}")
            meta = json.loads(sj) if isinstance(sj, str) and sj.strip() else {}
            if not isinstance(meta, dict):
                continue
            meta["mask_path"] = name
            widget["state_json"] = json.dumps(meta, sort_keys=True)
            synced.append(str(node_id))
        except Exception:
            continue
    return synced


def _hydrate_missing_required_widget_defaults(
    workflow: dict[str, Any],
    *,
    node_ids: set[str] | None = None,
) -> dict[str, Any]:
    """Fill omitted API-prompt widgets from the live node schema defaults.

    Covers required inputs and optional inputs that declare an explicit
    default (e.g. TextGenerate ``mtp``): a stored ``None`` fails ComfyUI's
    value-in-list validation exactly like a missing key, while filling the
    schema's own default is semantically identical to leaving it unconnected.
    Optional inputs without a declared default are left untouched.
    """
    hydrated: list[dict[str, str]] = []
    try:
        import nodes
    except Exception:
        return {"hydrated": hydrated, "unavailable": True}
    mappings = getattr(nodes, "NODE_CLASS_MAPPINGS", {}) or {}
    for node_id, node in workflow.items():
        if node_ids is not None and str(node_id) not in node_ids:
            continue
        if not isinstance(node, dict):
            continue
        class_def = mappings.get(node.get("class_type"))
        input_types = getattr(class_def, "INPUT_TYPES", None)
        if not callable(input_types):
            continue
        try:
            schema = input_types() or {}
        except Exception:
            continue
        inputs = node.setdefault("inputs", {})
        if not isinstance(inputs, dict):
            continue
        candidates: list[tuple[str, Any]] = []
        if isinstance(schema, dict):
            for section_key in ("required", "optional"):
                section = schema.get(section_key)
                if isinstance(section, dict):
                    candidates.extend(section.items())
        for name, spec in candidates:
            if (
                not isinstance(spec, (tuple, list))
                or not spec
                or (name in inputs and inputs.get(name) is not None)
            ):
                continue
            options = spec[1] if len(spec) > 1 and isinstance(spec[1], dict) else {}
            # Only an explicit node-schema default is authoritative.  The
            # first enum option is not a default, and an IMAGE input must
            # never be filled with invented data.
            if "default" not in options or options.get("default") is None:
                continue
            default = options["default"]
            inputs[name] = copy.deepcopy(default)
            hydrated.append({"node_id": str(node_id), "input": str(name)})
    return {"hydrated": hydrated, "unavailable": False}


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


def _repair_empty_dropdown_links(workflow: dict[str, Any]) -> list[dict[str, Any]]:
    """Repair links fed by unconfigured dropdowns (same family as the CLIP/VAE
    repairs below: complete wiring the graph left incomplete, invent nothing).

    A PixaromaDropdown with empty DropdownState outputs ``""`` for every slot
    (verified: ``selected_values("") == ("", "", "", "")``). Linked into
    ``ImageScaleToTotalPixels.megapixels`` (FLOAT) that crashes remote
    execution with ``TypeError`` AFTER model loading — ``"" * 1048576`` is
    silently legal, so nothing fails earlier. The repair injects the LEAN
    state the browser itself would inject for a 1.0 float pick (Pixaroma's
    documented wire format: ``{"type": "float", "value": ...}``), matching the
    target node's own megapixel default of 1. Topology is preserved — no link
    is severed, renamed, or retargeted; only the provably-empty state blob is
    completed, exactly where the node reads it.

    Deliberately narrow (one source class, one target input, empty state
    only): anything outside this shape passes through untouched. Returns a
    list of repair records for request metadata so the substitution is
    auditable, never silent.
    """
    repairs: list[dict[str, Any]] = []
    if not isinstance(workflow, dict):
        return repairs
    for node_id, node in workflow.items():
        if not isinstance(node, dict):
            continue
        if node.get("class_type") != "ImageScaleToTotalPixels":
            continue
        inputs = node.get("inputs")
        if not isinstance(inputs, dict):
            continue
        mega = inputs.get("megapixels")
        if not (isinstance(mega, (list, tuple)) and len(mega) == 2):
            continue
        src = workflow.get(str(mega[0]))
        if not isinstance(src, dict) or src.get("class_type") != "PixaromaDropdown":
            continue
        src_inputs = src.get("inputs")
        if not isinstance(src_inputs, dict):
            continue
        state = src_inputs.get("DropdownState", "")
        if isinstance(state, str) and state.strip() in ("", "{}"):
            src_inputs["DropdownState"] = '{"type": "float", "value": 1.0}'
            repairs.append({
                "source_node_id": str(mega[0]),
                "target_node_id": str(node_id),
                "target_input": "megapixels",
                "injected": "float 1.0 (target's own megapixel default)",
            })
    return repairs


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

        runtime_bundle = _refresh_ui_workflow_bundle(bundle)
        executable_prompt = runtime_bundle["executable_prompt"]
        graph_json = (runtime_bundle.get("version") or {}).get("graph_json")
        is_ui_graph = False
        try:
            from studio_domain.graph import is_ui_workflow_format

            is_ui_graph = is_ui_workflow_format(graph_json)
        except Exception:
            pass
        prepared = prepare_effective_prompt(
            executable_prompt,
            runtime_bundle["control_schema"],
            values,
            runtime_bundle.get("mapping"),
            modal_options=modal_options,
            ui_graph=graph_json,
        )
        if "error" in prepared:
            return None, prepared["error"]
        workflow = prepared["workflow"]
        text_generate_meta = prepared.get("studio_meta") or {}
        # Repair links fed by unconfigured dropdowns (same family as the
        # CLIP/VAE repairs below: complete wiring the graph left incomplete).
        dropdown_repairs = _repair_empty_dropdown_links(workflow)
        if dropdown_repairs:
            _log.warning(
                "Studio repaired %d empty-dropdown link(s): %s",
                len(dropdown_repairs), dropdown_repairs,
            )

        # Repair legacy missing CLIP/VAE inputs on the applied deep copy
        # (same helpers as _default_build_execution_plan / build_single_run_spec).
        _repair_missing_clip_inputs(workflow)
        _repair_missing_vae_inputs(workflow)
        _normalize_model_loader_names(workflow)

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
            preset_id="",
            workflow_name=str(bundle.get("workflow", {}).get("name", "")),
            preset_name="",
            controls=values,
            workflow_hash=workflow_hash,
            output_mode=output_mode,
        )
        studio_meta["selected_gpu"] = _selected_gpu
        studio_meta.update(text_generate_meta)
        try:
            # Role transport for golden dispatch substitution: normalized
            # semantic-role -> node bindings travel in request metadata so
            # the worker can substitute golden stages at role-marked nodes.
            # Carried verbatim ({role: {node_id, input_name}}); the worker
            # verifies the node's actual loader class before substituting,
            # so a stale binding can never retarget silently. Never raises;
            # missing/empty mapping means native execution.
            _role_bindings: dict[str, dict[str, str]] = {}
            _mapping_entries = (runtime_bundle.get("mapping") or {}).get("entries") or []
            if isinstance(_mapping_entries, dict):
                _mapping_entries = list(_mapping_entries.values())
            for _entry in _mapping_entries or []:
                if not isinstance(_entry, dict):
                    continue
                _role = str(_entry.get("semantic_role") or "")
                _nid = str(_entry.get("node_id") or "")
                if _role and _nid and _role not in _role_bindings:
                    _role_bindings[_role] = {
                        "node_id": _nid,
                        "input_name": str(_entry.get("input_name") or ""),
                    }
            if _role_bindings:
                studio_meta["role_bindings"] = _role_bindings
            if dropdown_repairs:
                studio_meta["repaired_empty_dropdowns"] = dropdown_repairs
        except Exception:
            pass

        output_node_id = str(
            runtime_bundle.get("mapping", {}).get("output_node_id", "") or ""
        )
        if not output_node_id:
            return None, "workflow mapping has no output node id"
        output_node_ids: tuple[str, ...] = tuple([output_node_id])
        try:
            # Universal capture: collect EVERY image-capable node (custom
            # compare/preview outputs included), not just the single mapping
            # output. Explicit mapping output stays first; the collection
            # chain already accepts a tuple. Never breaks single-output plans.
            from studio_domain.graph import derive_output_node_ids_from_prompt

            _extra_outputs = derive_output_node_ids_from_prompt(
                workflow, explicit_output_id=output_node_id
            )
            if _extra_outputs:
                output_node_ids = tuple(_extra_outputs)
        except Exception:
            pass
        _hydrate_missing_required_widget_defaults(
            workflow,
            node_ids=None if is_ui_graph else {output_node_id},
        )

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
            # Non-production direct plan: image Tool Inputs still need their
            # bytes collected — otherwise source/mask filenames travel without
            # payloads and the remote loader finds nothing.
            try:
                from canonical_execution import _collect_input_images as _direct_collect_images
                _direct_images = _direct_collect_images(workflow, str(comfyui_root or ""))
            except Exception:
                _direct_images = {}
            plan = ExecutionPlan(
                workflow=workflow,
                workflow_hash=workflow_hash,
                model_stack=extract_model_stack(workflow),
                prompt_bundle=custom_prompt_bundle,
                output_node_ids=output_node_ids,
                input_images=_direct_images,
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

    # Bridge the run to its History V2 generation for the frontend: run
    # responses carry only run-scoped ids, while History renders by
    # generation id, and nothing else links the two.  Attached onto the
    # result dict so it flows into the strict-JSON-validated response below.
    if isinstance(result, dict) and isinstance(record, dict):
        _bridged_gen_id = record.get("history_generation_id")
        if _bridged_gen_id:
            result["history_generation_id"] = str(_bridged_gen_id)

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
                prepared = prepare_effective_prompt(
                    bundle.get("executable_prompt") or {},
                    bundle.get("control_schema") or {},
                    values,
                    bundle.get("mapping"),
                    modal_options=modal_options,
                    ui_graph=(bundle.get("version") or {}).get("graph_json"),
                )
                if "workflow" in prepared:
                    workflow_json = prepared["workflow"]
                    _repair_missing_clip_inputs(workflow_json)
                    _repair_missing_vae_inputs(workflow_json)
                    _repair_empty_dropdown_links(workflow_json)
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
            "preset_id": "",
            "workflow_name": str(bundle.get("workflow", {}).get("name", "") or ""),
            "preset_name": "",
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
                "preset_id": "",
                "workflow_name": str(bundle.get("workflow", {}).get("name", "")),
                "preset_name": "",
            },
        }
        return bundle.get("defaults") or {}, snapshot, None

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
        bundle = resolve_workflow_run_bundle(workflow_id, version_id, node_dir)
        if bundle.get("status") != "ok":
            return bundle

        merged = merge_workflow_controls(
            bundle.get("defaults") or {}, controls or {}, bundle["control_schema"]
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
