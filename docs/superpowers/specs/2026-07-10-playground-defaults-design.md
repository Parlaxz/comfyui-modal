# Playground Defaults from Snapshot — Design Spec

> **Status:** Approved after oracle review
> **Goal:** Playground controls show the preset's captured snapshot values unless the user explicitly overrides them
> **Principle:** Smallest possible change — ~20 lines net, no migration, no new fields

## Problem

The playground renders control inputs using hardcoded `CONTROL_DEFS.defaultValue` (e.g., steps=20, guidance=7.0). But each preset's snapshot workflow may have different widget values (e.g., steps=30). The user sees wrong numbers in the UI, and the initial run silently uses the snapshot's workflow values — a visual/runtime mismatch.

## Solution

Enrich the preset response's `defaults` field at read time by extracting widget values from the linked snapshot, then use those in the playground UI.

### Source of truth: snapshot values

The preset's `defaults` field is populated from the linked snapshot's `apiPromptJson` workflow, using `nodeBindings` as the address map. This ensures the UI always reflects what the snapshot actually runs.

## Changes

### 1. Backend — New extraction function (`studio_run_adapter.py`)

```python
def extract_defaults_from_snapshot(snapshot: dict) -> dict:
    """Extract flat {controlId: value} from snapshot nodeBindings + apiPromptJson."""
    workflow = snapshot.get("apiPromptJson", {}) or {}
    bindings = snapshot.get("nodeBindings", {}) or {}
    defaults = {}
    for ctrl_id, binding in bindings.items():
        if not isinstance(binding, dict):
            continue
        kind = binding.get("kind", "")
        if kind == "widget":
            name_key = "widgetName"
        elif kind == "input":
            name_key = "inputName"
        else:
            continue  # skip "node" and "output" kinds
        node_id = binding.get("nodeId", "")
        widget_name = binding.get(name_key, "")
        if not node_id or not widget_name:
            continue
        node = workflow.get(node_id, {})
        inputs = node.get("inputs", {})
        if widget_name in inputs:
            defaults[ctrl_id] = inputs[widget_name]
    return defaults
```

Handles both `kind: "widget"` (uses `widgetName`) and `kind: "input"` (uses `inputName`). Skips `"node"` and `"output"` kinds. Gracefully handles missing keys via `.get()` chains.

### 2. Backend — Enrich at read time (`studio_routes.py`)

In the `GET /comfymodal/studio/presets` response enrichment block (lines ~283-290), when a snapshot is found:

```python
if snapshot is not None:
    from studio_run_adapter import extract_defaults_from_snapshot
    normalized["defaults"] = extract_defaults_from_snapshot(snapshot)
    # ... existing enrichments unchanged
```

Also enrich in the POST (create) and PATCH (update) response handlers so the client never sees a brief `defaults: {}` after creating/editing a preset.

No data migration needed — the existing `defaults` field already exists on every preset and passes through `make_preset`/`update_preset` unchanged.

### 3. Frontend — Use preset defaults in render (`studio-playground.js`)

In `renderControl()`, change value resolution (line ~577):

```javascript
const presetDefaults = (preset && preset.defaults) || {};
const currentOverrides = (state.playground && state.playground.controls) || {};
const value = currentOverrides[def.id] ?? presetDefaults[def.id] ?? def.defaultValue;
```

In `renderControlPanel()`, pass `preset` through to `renderControl` (line ~285).

### 4. Frontend — Experiment axis initialization (optional consistency fix)

`toggleExperimentAxis` (line ~390-401) currently reads `CONTROL_DEFS[ctrlId].defaultValue`. Change to read from `preset.defaults` first. Store `_currentPreset` on `state.playground` when the preset loads.

## Edge Cases

| Case | Behavior |
|------|----------|
| Missing snapshot (import/legacy) | No defaults, falls back to `CONTROL_DEFS` |
| Binding widget missing from workflow JSON | Key omitted from defaults |
| `kind: "node"` or `kind: "output"` binding | Skipped — no scalar value to extract |
| Preset switch | `setBackend()` clears `controls`, fresh preset defaults apply |
| Feature switch | `setFeature()` clears `controls` |
| User clears field to `""` | `"" ?? presetDefault ?? defDefault` → `""` (user intent kept) |
| Extra keys in defaults not in CONTROL_DEFS | Harmless — filtered by `visibleControlIds` |
| POST/PATCH returning stale `defaults: {}` | Mitigated: enrich in those handlers too |

## Test Plan

1. `test_extract_defaults_from_snapshot_basic` — Known apiPromptJson + bindings → expected flat dict
2. `test_extract_defaults_from_snapshot_input_kind` — Binding with kind="input" and inputName
3. `test_extract_defaults_from_snapshot_missing_widget` — Binding references widget not in workflow → omitted
4. `test_extract_defaults_from_snapshot_node_kind_skipped` — kind="node" → skipped
5. `test_extract_defaults_from_snapshot_empty` — Empty workflow / empty bindings → `{}`
6. `test_presets_api_enriches_defaults` — GET presets returns `defaults` dict for snapshot-linked presets
7. `test_playground_shows_preset_defaults` — Mock preset with defaults, render shows them
8. `test_playground_user_override_takes_precedence` — User override > preset default > CONTROL_DEFS
