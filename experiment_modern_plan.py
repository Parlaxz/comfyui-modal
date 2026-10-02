"""Pure modern Experiment cell-plan generation (modern Studio experiment lane).

Accepts ONE modern Experiment definition and deterministically expands it
into an ordered, immutable list of cell plans.  Every executable cell is
routed through the exact modern workflow seam (``studio_workflow_run``)::

    resolve_workflow_run_bundle
      -> merge_workflow_controls
      -> apply_workflow_values_to_prompt
      -> build_workflow_execution_plan

Nothing is duplicated: the legacy ``resolve_and_inject_cell`` slot-path graph
mutation is never reused.  Workflow-only ``latest_version_id`` /
``default_preset_id`` resolution happens exactly once, at plan time, and the
resolved ids are frozen into every cell; execution never re-resolves them.

Public API
----------
* ``build_cell_plan`` — one definition -> frozen ``ExperimentCellPlan``.
* ``resolve_workflow_axis_value`` — resolve one workflow axis value.
* ``validate_cell_controls`` — cell-level control validation (seam reuse).
* ``cell_plan_hash`` / ``cell_id_for`` / ``cell_key_for`` — deterministic
  plan/cell hashing (``cell_key`` is the additive raw digest behind the
  stable public ``cell_id``).
"""
from __future__ import annotations

import copy
import hashlib
import itertools
import json
import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Optional

import studio_workflow_run as _seam
from comfymodal_runtime.contracts import (
    ExecutionPlan,
    normalize_output_intent_options,
)


# ── Constants ──────────────────────────────────────────────────────────────

EXPERIMENT_CONCURRENCY_DEFAULT = 6

# Canonical JSON serialisation (matches the repo's canonical hashing style:
# sort keys, compact separators, no NaN).
_CANONICAL_JSON_KWARGS = {
    "sort_keys": True,
    "separators": (",", ":"),
    "ensure_ascii": False,
    "allow_nan": False,
}

# Reserved workflow-axis labels; the recorded label is always canonicalised
# to "workflow".
_WORKFLOW_AXIS_LABELS = frozenset({"workflow", "workflows"})
_WORKFLOW_AXIS_LABEL = "workflow"

# Well-known experiment axis labels that differ from the canonical mapping
# roles.  An alias is applied ONLY when the label itself is not exposed by
# the version's mapping (verbatim labels always win).
_AXIS_ROLE_ALIASES = MappingProxyType({
    "prompt": "positive_prompt",
    "guidance": "cfg",
})

_VERSION_ALIAS_KEYS = ("workflow_version_id", "version_id", "version")
_PRESET_ALIAS_KEYS = ("preset_id", "preset")


# ── Errors ─────────────────────────────────────────────────────────────────


class ExperimentDefinitionError(ValueError):
    """A globally malformed experiment definition (raise before any cell)."""


# ── JSON / immutability helpers ────────────────────────────────────────────


def _canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(value, **_CANONICAL_JSON_KWARGS).encode("utf-8")


def _json_safe(value: Any) -> bool:
    try:
        json.dumps(value, allow_nan=False)
        return True
    except (TypeError, ValueError):
        return False


def _freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType({str(k): _freeze(v) for k, v in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(v) for v in value)
    if isinstance(value, set):
        return tuple(sorted(_freeze(v) for v in value))
    return value


def _plain_copy(value: Any) -> Any:
    """Recursively thaw frozen containers into plain dicts/lists.

    Mirrors ``studio_workflow_run._plain_copy``: MappingProxyType and every
    Mapping become plain dicts, tuples/lists become plain lists, scalars pass
    through untouched (never stringified) so a strict ``json.dumps`` check
    can still fail truthfully downstream.
    """
    if isinstance(value, Mapping):
        return {str(k): _plain_copy(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain_copy(v) for v in value]
    return value


def _deep_plain(value: Any) -> Any:
    """Deep copy *value* into plain dict/list form (never frozen containers).

    Used for the workflow-run bundle snapshot: the seam deep-copies
    ``executable_prompt`` and canonical-hashes applied prompts, both of which
    fail on MappingProxyType, so the snapshot must stay plain.
    """
    return copy.deepcopy(value) if _json_safe(value) else _plain_copy(value)


def _first_present(mapping: Mapping, keys: tuple[str, ...]) -> Optional[str]:
    for key in keys:
        value = mapping.get(key)
        if isinstance(value, str):
            value = value.strip()
            if value:
                return value
        elif value is not None:
            return str(value)
    return None


# ── Axis value expansion (pure modern) ─────────────────────────────────────


# Hard cap so a pathological but mathematically-finite float range (huge
# magnitude with a tiny step) can never hang the planner; ordinary ranges
# keep the legacy inclusive behavior unchanged.
_MAX_RANGE_VALUES = 1_000_000


def _range_values(defn: Mapping) -> list[Any]:
    start = defn.get("start", 0)
    end = defn.get("end", 0)
    step = defn.get("step", 1)
    for key, value in (("start", start), ("end", end), ("step", step)):
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ExperimentDefinitionError(
                f"range axis {key!r} must be a number, got {value!r}"
            )
    if step == 0:
        return [start]
    # Index-based accumulation: ``start + i*step`` never drifts the way a
    # repeated ``v += step`` loop does for decimal steps, and the loop is
    # bounded (each iteration moves |step| monotonically toward the bound).
    if step > 0:
        count = 0
        while start + count * step <= end + 1e-9:
            count += 1
            if count > _MAX_RANGE_VALUES:
                raise ExperimentDefinitionError(
                    "range axis exceeds the maximum expansion bound "
                    f"({_MAX_RANGE_VALUES} values)"
                )
    else:
        count = 0
        while start + count * step >= end - 1e-9:
            count += 1
            if count > _MAX_RANGE_VALUES:
                raise ExperimentDefinitionError(
                    "range axis exceeds the maximum expansion bound "
                    f"({_MAX_RANGE_VALUES} values)"
                )
    if count == 0:
        raise ExperimentDefinitionError(
            "range axis expands to zero values "
            f"(start {start!r}, end {end!r}, step {step!r})"
        )
    return [start + i * step for i in range(count)]


def _expand_axis_values(label: str, raw: Any) -> list[Any]:
    """Deterministic expansion of one axis definition (list or range).

    Values are preserved verbatim (``0`` / ``0.0`` / ``False`` / ``""`` /
    ``None`` included).  Range semantics mirror the legacy compiler's
    inclusive ``_axis_values`` loop.
    """
    if isinstance(raw, list):
        axis_def = {"mode": "list", "values": list(raw)}
    elif isinstance(raw, dict):
        axis_def = dict(raw)
    else:
        raise ExperimentDefinitionError(
            f"axis {label!r} must be a dict or list, got {type(raw).__name__}"
        )

    if "values" in axis_def:
        values = axis_def.get("values", [None])
        if not isinstance(values, list):
            raise ExperimentDefinitionError(
                f"axis {label!r} 'values' must be a list"
            )
        if not values:
            raise ExperimentDefinitionError(
                f"axis {label!r} has an empty value list"
            )
        return list(values)

    mode = axis_def.get("mode")
    if mode is None and any(k in axis_def for k in ("start", "end", "step")):
        mode = "range"
    if mode == "list":
        values = axis_def.get("values", [None])
        if not isinstance(values, list):
            raise ExperimentDefinitionError(
                f"axis {label!r} 'values' must be a list"
            )
        if not values:
            raise ExperimentDefinitionError(
                f"axis {label!r} has an empty value list"
            )
        return list(values)
    if mode == "range":
        return _range_values(axis_def)
    raise ExperimentDefinitionError(
        f"axis {label!r} has unsupported mode {mode!r}"
    )


# ── Workflow axis value normalisation ──────────────────────────────────────


def _normalize_workflow_targets(entry: Any) -> list[dict[str, Any]]:
    """Normalise one workflow value into a list of target specs.

    Each target spec is ``{"workflow_id", "workflow_version_id", "preset_id"}``
    with ``None`` for unpinned ids.  A value may pin version/preset directly
    or expand via ``versions`` / ``presets`` lists (cartesian when both).
    """
    if isinstance(entry, str):
        value = entry.strip()
        if not value:
            raise ExperimentDefinitionError("workflow value cannot be empty")
        return [{"workflow_id": value, "workflow_version_id": None, "preset_id": None}]
    if not isinstance(entry, dict):
        raise ExperimentDefinitionError(
            "workflow value must be a string or dict, got "
            f"{type(entry).__name__}"
        )

    wf_id = entry.get("workflow_id", entry.get("workflow"))
    if not isinstance(wf_id, str) or not wf_id.strip():
        raise ExperimentDefinitionError(
            "workflow entry is missing a 'workflow_id'"
        )
    wf_id = wf_id.strip()

    versions = entry.get("versions")
    presets = entry.get("presets")
    if versions is not None and not isinstance(versions, list):
        raise ExperimentDefinitionError("'versions' must be a list")
    if presets is not None and not isinstance(presets, list):
        raise ExperimentDefinitionError("'presets' must be a list")

    version_pin = _first_present(entry, _VERSION_ALIAS_KEYS)
    preset_pin = _first_present(entry, _PRESET_ALIAS_KEYS)

    def _version_pin(item: Any) -> Optional[str]:
        if isinstance(item, str):
            return item.strip() or version_pin
        if isinstance(item, dict):
            return _first_present(item, _VERSION_ALIAS_KEYS) or version_pin
        raise ExperimentDefinitionError(
            "workflow 'versions' entries must be strings or dicts"
        )

    def _preset_pin(item: Any) -> Optional[str]:
        if isinstance(item, str):
            return item.strip() or preset_pin
        if isinstance(item, dict):
            return _first_present(item, _PRESET_ALIAS_KEYS) or preset_pin
        raise ExperimentDefinitionError(
            "workflow 'presets' entries must be strings or dicts"
        )

    if versions is None and presets is None:
        return [{
            "workflow_id": wf_id,
            "workflow_version_id": version_pin,
            "preset_id": preset_pin,
        }]
    if versions is None:
        if not presets:
            raise ExperimentDefinitionError("workflow 'presets' must not be empty")
        return [{
            "workflow_id": wf_id,
            "workflow_version_id": _version_pin(p),
            "preset_id": _preset_pin(p),
        } for p in presets]
    if presets is None:
        if not versions:
            raise ExperimentDefinitionError("workflow 'versions' must not be empty")
        return [{
            "workflow_id": wf_id,
            "workflow_version_id": _version_pin(v),
            "preset_id": _preset_pin(v),
        } for v in versions]
    if not versions or not presets:
        raise ExperimentDefinitionError(
            "workflow 'versions' and 'presets' must not be empty"
        )
    return [
        {
            "workflow_id": wf_id,
            "workflow_version_id": _version_pin(v),
            "preset_id": _preset_pin(p),
        }
        for v in versions
        for p in presets
    ]


# ── Public types ───────────────────────────────────────────────────────────


@dataclass(frozen=True)
class WorkflowResolution:
    """One frozen workflow-axis resolution (resolved exactly once at plan time).

    ``status == "ok"`` carries the resolved ids/names plus the immutable
    run-bundle snapshot (plain deep copy — the seam deep-copies
    ``executable_prompt`` and canonical-hashes applied prompts, both of which
    fail on frozen containers).  ``status == "error"`` carries the
    fail-closed resolution error and rejects only the affected cells.
    """

    status: str
    workflow_id: str = ""
    workflow_version_id: str = ""
    preset_id: str = ""
    workflow_name: str = ""
    preset_name: str = ""
    version_number: int = 0
    error_code: str = ""
    message: str = ""
    reasons: tuple[str, ...] = ()
    bundle: Optional[Mapping] = None
    control_schema: Mapping = field(default_factory=dict)
    executable_prompt: Mapping = field(default_factory=dict)
    source_workflow_hash: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "workflow_id", str(self.workflow_id or ""))
        object.__setattr__(self, "workflow_version_id", str(self.workflow_version_id or ""))
        object.__setattr__(self, "preset_id", str(self.preset_id or ""))
        object.__setattr__(self, "workflow_name", str(self.workflow_name or ""))
        object.__setattr__(self, "preset_name", str(self.preset_name or ""))
        object.__setattr__(self, "version_number", int(self.version_number or 0))
        object.__setattr__(self, "error_code", str(self.error_code or ""))
        object.__setattr__(self, "message", str(self.message or ""))
        object.__setattr__(self, "reasons", tuple(str(r) for r in (self.reasons or ())))
        object.__setattr__(self, "bundle", _deep_plain(self.bundle) if self.bundle is not None else None)
        object.__setattr__(self, "control_schema", _freeze(self.control_schema or {}))
        object.__setattr__(self, "executable_prompt", _deep_plain(self.executable_prompt or {}))
        object.__setattr__(self, "source_workflow_hash", str(self.source_workflow_hash or ""))

    @property
    def ok(self) -> bool:
        return self.status == "ok"

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "workflow_id": self.workflow_id,
            "workflow_version_id": self.workflow_version_id,
            "preset_id": self.preset_id,
            "workflow_name": self.workflow_name,
            "preset_name": self.preset_name,
            "version_number": self.version_number,
            "error_code": self.error_code,
            "message": self.message,
            "reasons": list(self.reasons),
            "control_schema": _plain_copy(self.control_schema),
            "source_workflow_hash": self.source_workflow_hash,
        }


@dataclass(frozen=True)
class CellPlan:
    """One immutable, deterministic experiment cell."""

    experiment_id: str
    cell_id: str
    position: int
    cell_key: str = ""
    axis_labels: tuple[str, ...] = ()
    axis_values: Mapping = field(default_factory=dict)
    axis_to_control: Mapping = field(default_factory=dict)
    workflow_id: str = ""
    workflow_version_id: str = ""
    preset_id: str = ""
    workflow_name: str = ""
    preset_name: str = ""
    version_number: int = 0
    controls: Mapping = field(default_factory=dict)
    merged_values: Mapping = field(default_factory=dict)
    execution_plan: Optional[ExecutionPlan] = None
    execution_plan_dict: Optional[Mapping] = None
    workflow_hash: str = ""
    source_workflow_hash: str = ""
    plan_hash: str = ""
    modal_options: Mapping = field(default_factory=dict)
    output_mode: str = "original"
    error: Optional[str] = None
    error_code: Optional[str] = None
    errors: tuple[dict[str, str], ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "experiment_id", str(self.experiment_id or ""))
        object.__setattr__(self, "cell_id", str(self.cell_id or ""))
        object.__setattr__(self, "cell_key", str(self.cell_key or ""))
        object.__setattr__(self, "position", int(self.position))
        object.__setattr__(self, "axis_labels", tuple(str(a) for a in (self.axis_labels or ())))
        object.__setattr__(self, "axis_values", _freeze(self.axis_values or {}))
        object.__setattr__(self, "axis_to_control", _freeze(self.axis_to_control or {}))
        object.__setattr__(self, "workflow_id", str(self.workflow_id or ""))
        object.__setattr__(self, "workflow_version_id", str(self.workflow_version_id or ""))
        object.__setattr__(self, "preset_id", str(self.preset_id or ""))
        object.__setattr__(self, "workflow_name", str(self.workflow_name or ""))
        object.__setattr__(self, "preset_name", str(self.preset_name or ""))
        object.__setattr__(self, "version_number", int(self.version_number or 0))
        object.__setattr__(self, "controls", _freeze(self.controls or {}))
        object.__setattr__(self, "merged_values", _freeze(self.merged_values or {}))
        object.__setattr__(self, "execution_plan_dict",
                          _deep_plain(self.execution_plan_dict)
                          if self.execution_plan_dict is not None else None)
        object.__setattr__(self, "workflow_hash", str(self.workflow_hash or ""))
        object.__setattr__(self, "source_workflow_hash", str(self.source_workflow_hash or ""))
        object.__setattr__(self, "plan_hash", str(self.plan_hash or ""))
        object.__setattr__(self, "modal_options", _freeze(self.modal_options or {}))
        object.__setattr__(self, "output_mode", str(self.output_mode or "original"))
        object.__setattr__(self, "error", str(self.error) if self.error else None)
        object.__setattr__(self, "error_code", str(self.error_code) if self.error_code else None)
        object.__setattr__(self, "errors", tuple(
            {"field": str(e.get("field", "")), "message": str(e.get("message", ""))}
            for e in (self.errors or ())
        ))

    @property
    def ok(self) -> bool:
        return self.error is None

    def to_dict(self) -> dict[str, Any]:
        return {
            "experiment_id": self.experiment_id,
            "cell_id": self.cell_id,
            "cell_key": self.cell_key,
            "position": self.position,
            "axis_labels": list(self.axis_labels),
            "axis_values": _plain_copy(self.axis_values),
            "axis_to_control": _plain_copy(self.axis_to_control),
            "workflow_id": self.workflow_id,
            "workflow_version_id": self.workflow_version_id,
            "preset_id": self.preset_id,
            "workflow_name": self.workflow_name,
            "preset_name": self.preset_name,
            "version_number": self.version_number,
            "controls": _plain_copy(self.controls),
            "merged_values": _plain_copy(self.merged_values),
            "execution_plan": _plain_copy(self.execution_plan_dict)
            if self.execution_plan_dict is not None else None,
            "workflow_hash": self.workflow_hash,
            "source_workflow_hash": self.source_workflow_hash,
            "plan_hash": self.plan_hash,
            "modal_options": _plain_copy(self.modal_options),
            "output_mode": self.output_mode,
            "error": self.error,
            "error_code": self.error_code,
            "errors": [dict(e) for e in self.errors],
        }


@dataclass(frozen=True)
class ExperimentCellPlan:
    """The full deterministic experiment plan: ordered immutable cell list."""

    experiment_id: str
    cells: tuple[CellPlan, ...] = ()
    axis_labels: tuple[str, ...] = ()
    concurrency: int = EXPERIMENT_CONCURRENCY_DEFAULT
    modal_options: Mapping = field(default_factory=dict)
    workflow_branches: tuple[dict[str, Any], ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "experiment_id", str(self.experiment_id or ""))
        object.__setattr__(self, "cells", tuple(self.cells))
        object.__setattr__(self, "axis_labels", tuple(str(a) for a in (self.axis_labels or ())))
        object.__setattr__(self, "concurrency", int(self.concurrency or EXPERIMENT_CONCURRENCY_DEFAULT))
        object.__setattr__(self, "modal_options", _freeze(self.modal_options or {}))
        object.__setattr__(self, "workflow_branches", tuple(dict(b) for b in (self.workflow_branches or ())))

    @property
    def expected_cell_count(self) -> int:
        return len(self.cells)

    @property
    def cell_ordering(self) -> tuple[str, ...]:
        return tuple(cell.cell_id for cell in self.cells)

    def __iter__(self):
        return iter(self.cells)

    def __len__(self) -> int:
        return len(self.cells)

    def to_dict(self) -> dict[str, Any]:
        return {
            "experiment_id": self.experiment_id,
            "expected_cell_count": self.expected_cell_count,
            "cell_ordering": list(self.cell_ordering),
            "axis_labels": list(self.axis_labels),
            "concurrency": self.concurrency,
            "modal_options": _plain_copy(self.modal_options),
            "workflow_branches": [dict(b) for b in self.workflow_branches],
            "cells": [cell.to_dict() for cell in self.cells],
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), **_CANONICAL_JSON_KWARGS)


# ── Public hashing / validation API ────────────────────────────────────────


def cell_key_for(
    experiment_id: str,
    position: int,
    axis_values: Mapping[str, Any],
) -> str:
    """Deterministic durable cell identity digest (sha256 hex, no prefix).

    Additive identity separate from the public ``cell_id``:
    ``cell_id_for`` returns ``"cell_" + cell_key_for(...)``.  ``cell_key`` is
    the raw digest used as the durable identity (e.g. History V2 ``cell_key``
    meta / D3-D4 identity threading); the public ``cell_id`` scheme is
    unchanged and stable across attempts, retry, and resume.
    """
    payload = {
        "experiment_id": str(experiment_id or ""),
        "position": int(position),
        "axis_values": dict(axis_values or {}),
    }
    return hashlib.sha256(_canonical_json_bytes(payload)).hexdigest()


def cell_id_for(
    experiment_id: str,
    position: int,
    axis_values: Mapping[str, Any],
) -> str:
    """Deterministic stable cell id: ``cell_`` + sha256(position + axis values).

    Stable across attempts, retry, and resume — the resolved axis values
    (including the resolved workflow target) are baked at plan time.
    """
    return "cell_" + cell_key_for(experiment_id, position, axis_values)


def cell_plan_hash(cell: CellPlan | Mapping[str, Any]) -> str:
    """Complete, deterministic plan/content hash of one cell.

    Accepts a ``CellPlan`` or its ``to_dict()`` mapping.  ``plan_hash`` (its
    own output) and ``execution_plan`` (whose ``production_report`` may carry
    runtime cache diagnostics from the seam's canonical production path) are
    excluded from the hash input; the executed content's stable identity is
    covered by ``workflow_hash``.  The hash is therefore stable across
    rebuilds of an identical definition against an identical store.  Raises
    ``ValueError`` when the cell content is not strictly JSON-serializable
    (no stringification).
    """
    if isinstance(cell, CellPlan):
        data = cell.to_dict()
    elif isinstance(cell, Mapping):
        data = dict(cell)
    else:
        raise TypeError(
            f"cell_plan_hash expects a CellPlan or mapping, got {type(cell).__name__}"
        )
    data = _plain_copy(data)
    data.pop("plan_hash", None)
    data.pop("execution_plan", None)
    return hashlib.sha256(_canonical_json_bytes(data)).hexdigest()


def validate_cell_controls(
    controls: Mapping[str, Any],
    control_schema: Mapping[str, Any],
) -> list[dict[str, str]]:
    """Cell-level control validation against the version mapping schema.

    Reuses the seam's strict ``validate_workflow_controls``: unknown /
    unmapped controls, enum membership, numeric min/max, and required are
    enforced; values are never coerced (``0`` / ``0.0`` / ``False`` / ``""``
    are valid unless the schema says otherwise).  Missing-required checks for
    the FULL merged value set are performed by ``merge_workflow_controls``.
    """
    return list(_seam.validate_workflow_controls(
        dict(controls or {}), dict(control_schema or {})
    ))


# ── Workflow axis resolution ───────────────────────────────────────────────


def resolve_workflow_axis_value(
    workflow_value: Any,
    node_dir: str | os.PathLike,
) -> WorkflowResolution:
    """Resolve ONE workflow axis value exactly once (fail-closed, never raises).

    Reuses ``resolve_workflow_run_bundle`` verbatim, so the workflow-only
    fallback rule is identical to the modern single-run path: empty
    ``workflow_version_id`` -> ``workflow.latest_version_id``; empty
    ``preset_id`` -> ``workflow.default_preset_id``.

    * A single-target value (string or dict pinning ids) is resolved and
      returned as a frozen ``WorkflowResolution``.
    * Domain failures (workflow/version/preset missing, unrunnable version,
      mapping missing, preset mismatch) return ``status == "error"`` — the
      caller rejects only the affected cells.
    * A value that expands to multiple targets (``versions``/``presets``
      lists) or that is structurally malformed raises
      ``ExperimentDefinitionError``.
    """
    targets = _normalize_workflow_targets(workflow_value)
    if len(targets) != 1:
        raise ExperimentDefinitionError(
            "workflow value expands to multiple targets; use build_cell_plan "
            "for workflow-axis expansion"
        )
    target = targets[0]
    bundle = _seam.resolve_workflow_run_bundle(
        target["workflow_id"],
        target["workflow_version_id"] or "",
        target["preset_id"] or "",
        node_dir,
    )
    return _resolution_from_bundle(target, bundle)


def _resolution_from_bundle(
    target: dict[str, Any],
    bundle: dict[str, Any],
) -> WorkflowResolution:
    if bundle.get("status") != "ok":
        return WorkflowResolution(
            status="error",
            workflow_id=str(target.get("workflow_id") or ""),
            error_code=str(bundle.get("error_code", "") or ""),
            message=str(bundle.get("message", "") or "workflow run resolution failed"),
            reasons=tuple(str(r) for r in (bundle.get("reasons") or [])),
        )
    workflow = bundle.get("workflow") or {}
    version = bundle.get("version") or {}
    preset = bundle.get("preset") or {}
    return WorkflowResolution(
        status="ok",
        workflow_id=str(workflow.get("workflow_id", "") or ""),
        workflow_version_id=str(version.get("workflow_version_id", "") or ""),
        preset_id=str(preset.get("preset_id", "") or ""),
        workflow_name=str(workflow.get("name", "") or ""),
        preset_name=str(preset.get("name", "") or ""),
        version_number=int(version.get("version_number", 0) or 0),
        bundle=bundle,
        control_schema=bundle.get("control_schema") or {},
        executable_prompt=bundle.get("executable_prompt") or {},
        source_workflow_hash=str(version.get("graph_hash", "") or ""),
    )


# ── Cell planning internals ────────────────────────────────────────────────


def _extract_workflow_axis(axes: Mapping) -> Optional[list[dict[str, Any]]]:
    declared = [k for k in axes if k in _WORKFLOW_AXIS_LABELS]
    if not declared:
        return None
    if len(declared) > 1:
        raise ExperimentDefinitionError(
            "declare only one workflow axis "
            f"({'/'.join(sorted(_WORKFLOW_AXIS_LABELS))})"
        )
    raw = axes[declared[0]]
    if isinstance(raw, dict) and (
        "mode" in raw or "values" in raw or "start" in raw or "end" in raw or "step" in raw
    ):
        if raw.get("mode") == "range" or "start" in raw or "end" in raw:
            raise ExperimentDefinitionError(
                "the workflow axis cannot use range mode"
            )
        entries = _expand_axis_values(_WORKFLOW_AXIS_LABEL, raw)
    else:
        entries = _expand_axis_values(_WORKFLOW_AXIS_LABEL, [raw] if not isinstance(raw, list) else raw)
    targets: list[dict[str, Any]] = []
    for entry in entries:
        targets.extend(_normalize_workflow_targets(entry))
    if not targets:
        raise ExperimentDefinitionError("workflow axis expands to zero targets")
    return targets


def _top_level_workflow_targets(experiment_def: Mapping) -> list[dict[str, Any]]:
    raw = experiment_def.get("workflows", experiment_def.get("workflow"))
    if raw is None:
        raise ExperimentDefinitionError(
            "experiment definition must declare workflows (top-level "
            "'workflows'/'workflow') or a 'workflow' axis"
        )
    if isinstance(raw, list):
        entries = list(raw)
    elif isinstance(raw, dict) and (
        "mode" in raw or "values" in raw or "start" in raw or "end" in raw or "step" in raw
    ):
        raise ExperimentDefinitionError(
            "top-level 'workflows' must be a list of workflow entries, "
            "not an axis definition"
        )
    else:
        entries = [raw]
    if not entries:
        raise ExperimentDefinitionError("top-level 'workflows' must not be empty")
    targets: list[dict[str, Any]] = []
    for entry in entries:
        targets.extend(_normalize_workflow_targets(entry))
    return targets


def _axis_label_to_role(label: str, control_schema: Mapping) -> str:
    if label in control_schema:
        return label
    alias = _AXIS_ROLE_ALIASES.get(label)
    if alias and alias in control_schema:
        return alias
    return label


def _workflow_axis_value(target: dict[str, Any], resolution: WorkflowResolution) -> dict[str, Any]:
    if resolution.ok:
        return {
            "workflow_id": resolution.workflow_id,
            "workflow_version_id": resolution.workflow_version_id,
            "preset_id": resolution.preset_id,
        }
    return {
        "workflow_id": str(target.get("workflow_id") or ""),
        "workflow_version_id": str(target.get("workflow_version_id") or ""),
        "preset_id": str(target.get("preset_id") or ""),
    }


def _build_cell(
    *,
    experiment_id: str,
    position: int,
    axis_labels: tuple[str, ...],
    axis_values: dict[str, Any],
    axis_to_control: dict[str, str],
    target: dict[str, Any],
    resolution: WorkflowResolution,
    modal_options: Mapping,
) -> CellPlan:
    error: Optional[str] = None
    error_code: Optional[str] = None
    errors: list[dict[str, str]] = []
    plan: Optional[ExecutionPlan] = None
    plan_dict: Optional[Mapping] = None
    workflow_hash = ""
    merged_values: dict[str, Any] = {}
    controls: dict[str, Any] = {}
    bundle: dict[str, Any] = dict(resolution.bundle or {})

    if not resolution.ok:
        error = resolution.message or "workflow axis resolution failed"
        error_code = resolution.error_code or "WORKFLOW_RESOLUTION"
        errors = [{"field": "workflow", "message": error}]
    else:
        schema: dict[str, Any] = dict(_plain_copy(resolution.control_schema))
        for label, value in axis_values.items():
            if label == _WORKFLOW_AXIS_LABEL:
                continue
            role = _axis_label_to_role(label, resolution.control_schema)
            controls[role] = value
            if role != label:
                axis_to_control[label] = role

        control_errors = validate_cell_controls(controls, schema)
        merged = _seam.merge_workflow_controls(
            dict(bundle.get("preset") or {}), controls, schema
        )
        merged_values = dict(merged.get("values") or {})
        all_errors = list(control_errors) + list(merged.get("errors") or [])
        if all_errors:
            error = "; ".join(f"{e['field']}: {e['message']}" for e in all_errors)
            error_code = "WORKFLOW_CONTROL_VALIDATION"
            errors = all_errors
        elif not _json_safe(merged_values):
            merged_values = {}
            error = "merged control values are not JSON serializable"
            error_code = "WORKFLOW_CONTROL_NOT_SERIALIZABLE"
        else:
            # build_workflow_execution_plan is the sole apply+build seam: it
            # invokes apply_workflow_values_to_prompt internally (exactly the
            # modern single-run chain), so no standalone apply call here.
            plan, plan_error = _seam.build_workflow_execution_plan(
                bundle,
                merged_values,
                modal_options=dict(_plain_copy(modal_options)) or None,
            )
            if plan is None:
                error = str(plan_error or "workflow execution plan build failed")
                error_code = "WORKFLOW_PLAN_BUILD"
            else:
                    try:
                        plan_dict = plan.to_dict()
                        json.dumps(plan_dict, allow_nan=False)
                    except (TypeError, ValueError) as exc:
                        plan_dict = None
                        plan = None
                        error = (
                            "execution plan is not strict-JSON serializable: "
                            f"{str(exc)[:200]}"
                        )
                        error_code = "WORKFLOW_PLAN_NOT_SERIALIZABLE"
                    if plan_dict is not None:
                        workflow_hash = str(plan.workflow_hash or "")

    cell_key = cell_key_for(experiment_id, position, axis_values)
    cell_id = cell_id_for(experiment_id, position, axis_values)
    cell = CellPlan(
        experiment_id=experiment_id,
        cell_id=cell_id,
        cell_key=cell_key,
        position=position,
        axis_labels=axis_labels,
        axis_values=axis_values,
        axis_to_control=axis_to_control,
        workflow_id=resolution.workflow_id,
        workflow_version_id=resolution.workflow_version_id,
        preset_id=resolution.preset_id,
        workflow_name=resolution.workflow_name,
        preset_name=resolution.preset_name,
        version_number=resolution.version_number,
        controls=controls,
        merged_values=merged_values,
        execution_plan=plan,
        execution_plan_dict=plan_dict,
        workflow_hash=workflow_hash,
        source_workflow_hash=resolution.source_workflow_hash,
        modal_options=modal_options,
        output_mode=str(
            dict(_plain_copy(modal_options)).get("output_mode", "original")
        ),
        error=error,
        error_code=error_code,
        errors=tuple(errors),
    )
    object.__setattr__(cell, "plan_hash", cell_plan_hash(cell.to_dict()))
    return cell


# ── Public entry point ─────────────────────────────────────────────────────


def build_cell_plan(
    experiment_def: dict[str, Any],
    node_dir: str | os.PathLike,
    *,
    modal_options: Optional[dict[str, Any]] = None,
    concurrency: int = EXPERIMENT_CONCURRENCY_DEFAULT,
) -> ExperimentCellPlan:
    """Build the full immutable cell plan for ONE modern Experiment definition.

    * Deterministic: same definition + same store -> same ordered cells.
    * Deterministic ordering: workflow targets outermost, non-seed axes in
      their declared relative order, and the canonical ``seed`` axis
      innermost (pinned regardless of its declared position, matching the
      legacy cheap-axis ordering).
    * Workflow-only ``latest``/``default`` resolution happens exactly once per
      distinct workflow target and is baked into every cell.
    * Globally malformed definitions raise ``ExperimentDefinitionError``
      before any cell is returned; per-version resolution/validation failures
      reject only the affected cell (cell-local ``error`` / ``error_code`` /
      ``errors``).
    * Every executable cell is routed through
      ``resolve_workflow_run_bundle -> merge_workflow_controls ->
      apply_workflow_values_to_prompt -> build_workflow_execution_plan``.

    Accepts the aliases ``workflows``/``workflow`` (top level), ``axes``/
    ``axis`` (axis container), and version/preset pinning via
    ``workflow_version_id``/``version_id``/``version`` and
    ``preset_id``/``preset`` (plus ``versions``/``presets`` expansion lists
    on a workflow value).
    """
    if not isinstance(experiment_def, dict):
        raise ExperimentDefinitionError("experiment definition must be a dict")

    experiment_id = experiment_def.get("experiment_id", "")
    if not isinstance(experiment_id, str) or not experiment_id.strip():
        raise ExperimentDefinitionError("experiment_id is required")
    experiment_id = experiment_id.strip()

    axes = experiment_def.get("axes", experiment_def.get("axis"))
    if axes is None:
        axes = {}
    if not isinstance(axes, dict):
        raise ExperimentDefinitionError("'axes' must be a dict")

    raw_concurrency = experiment_def.get("concurrency", concurrency)
    if (
        isinstance(raw_concurrency, bool)
        or not isinstance(raw_concurrency, int)
        or raw_concurrency <= 0
    ):
        raise ExperimentDefinitionError("'concurrency' must be a positive integer")
    effective_concurrency = int(raw_concurrency)

    raw_modal_options = experiment_def.get("modal_options")
    effective_modal_options: dict[str, Any] = {}
    if raw_modal_options is not None:
        if not isinstance(raw_modal_options, dict):
            raise ExperimentDefinitionError("'modal_options' must be a dict")
        effective_modal_options = dict(raw_modal_options)
    elif modal_options is not None:
        if not isinstance(modal_options, dict):
            raise ExperimentDefinitionError("modal_options must be a dict")
        effective_modal_options = dict(modal_options)
    effective_modal_options = normalize_output_intent_options(effective_modal_options)
    if not _json_safe(effective_modal_options):
        raise ExperimentDefinitionError("'modal_options' must be JSON-serializable")

    has_top_level = (
        "workflows" in experiment_def or "workflow" in experiment_def
    )
    workflow_targets = _extract_workflow_axis(axes)
    if workflow_targets is not None and has_top_level:
        raise ExperimentDefinitionError(
            "declare workflows either at top level or via a 'workflow' axis, "
            "not both"
        )
    if workflow_targets is None:
        workflow_targets = _top_level_workflow_targets(experiment_def)

    other_axis_labels: list[str] = []
    other_axis_value_lists: list[list[Any]] = []
    for label, raw in axes.items():
        if label in _WORKFLOW_AXIS_LABELS:
            continue
        if not isinstance(label, str) or not label.strip():
            raise ExperimentDefinitionError("axis labels must be non-empty strings")
        label = label.strip()
        values = _expand_axis_values(label, raw)
        for value in values:
            if not _json_safe(value):
                raise ExperimentDefinitionError(
                    f"axis {label!r} value {value!r} is not JSON-serializable"
                )
        other_axis_labels.append(label)
        other_axis_value_lists.append(values)

    # Pure ordering layer (no legacy logic): pin the canonical 'seed' axis as
    # the innermost factor, matching matrix_compiler's documented/tested
    # cheap-axis ordering (seed innermost) even when the input axes mapping
    # declares seed first.  Workflow targets stay outermost; every other
    # axis keeps its declared relative order.  Reordering both the labels and
    # value lists keeps ``axis_labels`` / ``axis_values`` consistent, so the
    # combo assignment below pairs each label with its own value.
    if "seed" in other_axis_labels and other_axis_labels[-1] != "seed":
        seed_index = other_axis_labels.index("seed")
        other_axis_labels.append(other_axis_labels.pop(seed_index))
        other_axis_value_lists.append(other_axis_value_lists.pop(seed_index))

    other_combos: list[tuple[Any, ...]] = list(itertools.product(*other_axis_value_lists))
    if not other_combos:
        other_combos = [()]

    resolution_cache: dict[tuple[str, str, str], WorkflowResolution] = {}
    cells: list[CellPlan] = []
    branches: list[dict[str, Any]] = []
    position = 0

    axis_labels: list[str] = []
    if workflow_targets is not None and any(k in axes for k in _WORKFLOW_AXIS_LABELS):
        axis_labels.append(_WORKFLOW_AXIS_LABEL)
    axis_labels.extend(other_axis_labels)

    for target in workflow_targets:
        cache_key = (
            str(target.get("workflow_id") or ""),
            str(target.get("workflow_version_id") or ""),
            str(target.get("preset_id") or ""),
        )
        resolution = resolution_cache.get(cache_key)
        if resolution is None:
            resolution = resolve_workflow_axis_value(target, node_dir)
            resolution_cache[cache_key] = resolution
        branch = {
            "workflow_id": resolution.workflow_id,
            "workflow_version_id": resolution.workflow_version_id,
            "preset_id": resolution.preset_id,
            "workflow_name": resolution.workflow_name,
            "preset_name": resolution.preset_name,
        }
        if not any(b == branch for b in branches):
            branches.append(branch)

        for combo in other_combos:
            axis_values: dict[str, Any] = {}
            if any(k in axes for k in _WORKFLOW_AXIS_LABELS):
                axis_values[_WORKFLOW_AXIS_LABEL] = _workflow_axis_value(target, resolution)
            for index, label in enumerate(other_axis_labels):
                axis_values[label] = combo[index]

            cell = _build_cell(
                experiment_id=experiment_id,
                position=position,
                axis_labels=tuple(axis_labels),
                axis_values=axis_values,
                axis_to_control={},
                target=target,
                resolution=resolution,
                modal_options=effective_modal_options,
            )
            cells.append(cell)
            position += 1

    if not cells:
        raise ExperimentDefinitionError("experiment definition expands to zero cells")

    return ExperimentCellPlan(
        experiment_id=experiment_id,
        cells=tuple(cells),
        axis_labels=tuple(axis_labels),
        concurrency=effective_concurrency,
        modal_options=effective_modal_options,
        workflow_branches=tuple(branches),
    )
