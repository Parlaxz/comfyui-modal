# Auto-Derive Playground Control Options from Workflow — Design Spec

> **Status:** Approved after oracle review
> **Goal:** Playground dropdowns and numeric fields get their options, defaults, and run-time slot mappings automatically from the workflow's KSampler node — even when the control is not explicitly bound in `nodeBindings`.
> **Principle:** Single backend registry + shared helper; three call sites; no frontend changes; no migration.

## Problem

Playground controls like `sampler`, `scheduler`, `steps`, `guidance`, `seed`, and `denoise` are **never explicitly bound** in `nodeBindings`. Three backend functions only process bound controls:

1. **`derive_control_schemas_from_snapshot()`** — iterates `nodeBindings` only → no enum options for unbound controls → frontend renders disabled empty `<select>`.
2. **`extract_defaults_from_snapshot()`** — iterates `nodeBindings` only → no default values for unbound controls → UI shows `CONTROL_DEFS.defaultValue` instead of the workflow's actual value.
3. **`map_studio_bindings_to_slots()`** — iterates `nodeBindings` only → user's dropdown selection is silently ignored at run time because no slot exists to write the value back into the workflow.

The result: dropdowns are empty, defaults are wrong, and even if the user picks a value it doesn't affect the run.

## Solution

Add a single backend registry `_AUTO_DERIVE_CONTROLS` mapping control IDs to candidate node types and widget names. Add one shared helper `_find_node_for_control(workflow, ctrl_id)` that scans the workflow for the first matching node. Use that helper in all three call sites to fill in schemas, defaults, and slots for controls that aren't explicitly bound.

### Resolution priority

```
1. Captured schema from snapshot.controlSchemas  (existing — bound controls)
2. Explicit nodeBindings mapping                 (existing — bound controls)
3. Auto-derived workflow mapping                 (NEW — unbound controls)
4. Unresolved fallback                           (existing — no match)
```

Steps 1–2 are unchanged. Step 3 is the new layer. Step 4 is the existing safety net.

## Changes

### 1. New registry (`studio_run_adapter.py`)

```python
_AUTO_DERIVE_CONTROLS: dict[str, dict] = {
    "sampler":   {"node_types": ["KSampler", "KSamplerAdvanced"], "widget": "sampler_name"},
    "scheduler": {"node_types": ["KSampler", "KSamplerAdvanced"], "widget": "scheduler"},
    "steps":     {"node_types": ["KSampler", "KSamplerAdvanced"], "widget": "steps"},
    "guidance":  {"node_types": ["KSampler", "KSamplerAdvanced"], "widget": "cfg"},
    "seed":      {"node_types": ["KSampler", "KSamplerAdvanced"], "widget": "seed"},
    "denoise":   {"node_types": ["KSampler", "KSamplerAdvanced"], "widget": "denoise"},
}
```

Each entry declares:
- `node_types` — ordered list of ComfyUI node types to search for
- `widget` — the widget/input name inside that node type

### 2. New shared helper (`studio_run_adapter.py`)

```python
def _find_node_for_control(workflow: dict, ctrl_id: str) -> dict | None:
    """Find the workflow node + widget for an unbound control via auto-derive registry.

    Returns {"node_id", "node_type", "widget_name", "value"} or None.
    Scans workflow nodes in insertion order for the first node whose
    class_type matches one of the control's candidate node types.
    """
    spec = _AUTO_DERIVE_CONTROLS.get(ctrl_id)
    if not spec or not isinstance(workflow, dict):
        return None
    widget_name = spec["widget"]
    for node_id, node_data in workflow.items():
        if not isinstance(node_data, dict):
            continue
        class_type = node_data.get("class_type", "")
        if class_type not in spec["node_types"]:
            continue
        inputs = node_data.get("inputs", {})
        if not isinstance(inputs, dict):
            continue
        if widget_name not in inputs:
            continue
        return {
            "node_id": str(node_id),
            "node_type": class_type,
            "widget_name": widget_name,
            "value": inputs.get(widget_name),
        }
    return None
```

### 3. Schema derivation (`derive_control_schemas_from_snapshot()`)

**Critical restructure:** The current Phase 4 path has an unconditional early return when `captured` is non-empty. This blocks auto-derive for mixed snapshots (captured schemas for some controls, but not others). The function must be restructured to merge captured schemas into a local dict and fall through to auto-derive, rather than returning early.

Restructured function:

```python
def derive_control_schemas_from_snapshot(snapshot: dict) -> dict[str, dict]:
    schemas: dict[str, dict] = {}
    bindings = snapshot.get("nodeBindings", {}) or {}
    workflow = _get_executable_workflow(snapshot.get("apiPromptJson"))

    # ── Phase 4: captured schemas from browser widget metadata ──
    captured = snapshot.get("controlSchemas", {}) or {}
    if captured:
        schemas = copy.deepcopy(captured)
        for ctrl_id, schema in schemas.items():
            if isinstance(schema, dict):
                schema.setdefault("schemaResolved", True)
                schema.setdefault("field", ctrl_id)

    # ── Legacy fallback: derive from static registry (only if no captured) ──
    if not captured:
        for ctrl_id, binding in bindings.items():
            # ... existing legacy loop unchanged ...
            # (lines 168-229 from current code, filling `schemas`)
            pass  # placeholder — existing code stays

    # ── Auto-derive schemas for unbound controls (always runs) ──
    if isinstance(workflow, dict):
        for ctrl_id in _AUTO_DERIVE_CONTROLS:
            if ctrl_id in schemas:
                continue  # already resolved via binding or captured schema
            found = _find_node_for_control(workflow, ctrl_id)
            if found is None:
                continue
            node_type = found["node_type"]
            widget_name = found["widget_name"]
            widget_schema = _NODE_WIDGET_SCHEMAS.get(node_type, {}).get(widget_name)
            schema: dict = {
                "field": ctrl_id,
                "nodeId": found["node_id"],
                "nodeType": node_type,
                "widgetName": widget_name,
            }
            if widget_schema:
                schema.update(widget_schema)
                schema["schemaResolved"] = True
            else:
                actual_value = found["value"]
                if isinstance(actual_value, bool):
                    schema["kind"] = "boolean"
                elif isinstance(actual_value, int):
                    schema["kind"] = "integer"
                elif isinstance(actual_value, float):
                    schema["kind"] = "number"
                else:
                    schema["kind"] = "string"
                schema["default"] = actual_value
                schema["schemaResolved"] = True
            schemas[ctrl_id] = schema

    return schemas
```

**Key change:** `workflow` is computed unconditionally (moved above captured check). Captured schemas are merged into `schemas` (not returned early). Legacy fallback only runs when no captured schemas. Auto-derive always runs last, filling gaps for both paths.

### 4. Default extraction (`extract_defaults_from_snapshot()`)

After the existing bound-control loop, add:

```python
# ── Auto-derive defaults for unbound controls ──
for ctrl_id in _AUTO_DERIVE_CONTROLS:
    if ctrl_id in defaults:
        continue  # already extracted via binding
    found = _find_node_for_control(workflow, ctrl_id)
    if found is not None and found["value"] is not None:
        defaults[ctrl_id] = found["value"]
```

### 5. Run-time slot auto-creation

In `_build_single_run_workflow()` (single run) and the experiment flow, after `slots = map_studio_bindings_to_slots(node_bindings)`, add:

```python
# ── Auto-derive slots for unbound controls ──
workflow_for_derive = workflow  # already deep-copied
for ctrl_id in _AUTO_DERIVE_CONTROLS:
    if ctrl_id in slots:
        continue  # already mapped via binding
    found = _find_node_for_control(workflow_for_derive, ctrl_id)
    if found is None:
        continue
    slots[ctrl_id] = {
        "node_id": found["node_id"],
        "field": found["widget_name"],
        "path": ["inputs", found["widget_name"]],
    }
```

This ensures user-selected values from the playground are written into the workflow at run time.

**Placement:** Extract this into a small helper `_augment_slots_with_auto_derive(slots, workflow)` to avoid duplicating the loop in both single-run and experiment paths.

**Call site 1 — Single run** (`_build_single_run_workflow`, ~line 720):
```python
slots = map_studio_bindings_to_slots(node_bindings)
slots = _augment_slots_with_auto_derive(slots, workflow)
```

**Call site 2 — Experiment** (~line 907):
```python
slots_map[profile_id] = map_studio_bindings_to_slots(
    copy.deepcopy(snapshot.get("nodeBindings", {})) or {}
)
slots_map[profile_id] = _augment_slots_with_auto_derive(
    slots_map[profile_id], workflow_map[profile_id]
)
```

### 6. No frontend changes

The frontend already renders schemas correctly when they exist:
- `schemaKind === "enum"` path renders a `<select>` with `schema.options`
- `schemaKind === "integer"` / `"number"` paths render `<input type="number">` with min/max/step
- The static `def.type === "select"` + `dynamicOptions` fallback path also works when `schema.kind === "enum"` and `schema.options` are present

Once the backend produces schemas for unbound controls, the frontend will render them correctly with no changes.

## Edge Cases

| Case | Behavior |
|------|----------|
| Control is explicitly bound | Binding takes precedence; auto-derive skipped (`if ctrl_id in schemas/defaults/slots: continue`) |
| Workflow has no KSampler | `_find_node_for_control()` returns None; control omitted; frontend falls back to static CONTROL_DEFS |
| Workflow has multiple KSamplers | First match (insertion order) wins; consistent with "one sampler per preset" assumption |
| Captured schema exists for some controls but not others | Captured schemas used for those controls; auto-derive fills in the rest |
| Legacy snapshot with no `controlSchemas` | Legacy path runs for bound controls; auto-derive fills in unbound controls |
| Control value is `0` or `False` | Preserved — `found["value"] is not None` check allows falsy values |
| `prompt` / `negative_prompt` | NOT auto-derived — both map to `CLIPTextEncode.text`, ambiguous without binding |
| `lora` / `model` / `vae` | NOT auto-derived — require model-list resolution, out of scope |

## Test Plan

### Backend tests (`test_studio_run_adapter.py`)

1. **`test_auto_derive_schema_for_unbound_sampler`** — Workflow with KSampler, no bindings → `derive_control_schemas_from_snapshot()` returns schema with `kind: "enum"` and full sampler options.
2. **`test_auto_derive_schema_for_unbound_scheduler`** — Same for scheduler.
3. **`test_auto_derive_schema_for_unbound_steps`** — Returns `kind: "integer"` with min/max from registry.
4. **`test_auto_derive_default_for_unbound_sampler`** — Workflow with `sampler_name: "dpmpp_2m"` → `extract_defaults_from_snapshot()` returns `{"sampler": "dpmpp_2m"}`.
5. **`test_auto_derive_default_for_unbound_steps`** — Workflow with `steps: 30` → defaults includes `{"steps": 30}`.
6. **`test_auto_derive_slot_for_unbound_sampler`** — `map_studio_bindings_to_slots()` + auto-derive → slots includes `sampler` mapping to the KSampler node.
7. **`test_bound_control_takes_precedence_over_auto_derive`** — Binding for `sampler` to a different node → binding wins, auto-derive skipped.
8. **`test_auto_derive_no_ksampler_returns_none`** — Workflow without KSampler → no auto-derived entries.
9. **`test_auto_derive_multiple_ksamplers_first_wins`** — Two KSampler nodes → first in insertion order is used.
10. **`test_auto_derive_falsy_value_preserved`** — `steps: 0` in workflow → default extracted as `0`, not skipped.
11. **`test_apply_controls_with_auto_derived_slots`** — Full round-trip: auto-derived slot + control override → workflow actually updated.
12. **`test_auto_derive_mixed_captured_and_unbound`** — Snapshot has `controlSchemas` for `seed` and `steps` but no schemas for `sampler`, `scheduler`. Verify captured schemas for seed/steps AND auto-derived schemas for sampler/scheduler are all returned.