# Playground Preset Draft Defaults — Design Spec

> **Status:** Draft for oracle review
> **Goal:** On first load of a preset in Playground, controls should come from the preset snapshot defaults; after that, the latest submitted/typed values for that preset+feature should become the new defaults and persist across reloads.
> **Principle:** Smallest frontend-only change that preserves existing preset snapshot defaults and adds per-preset draft persistence.

## Problem

The current Playground behavior in `web/studio-playground.js` is close, but the source-of-truth order is wrong for the requested UX.

- First load already supports preset snapshot defaults via `preset.defaults`
- Hydration also restores the latest completed run for a preset+feature and seeds `_hydratedControls`
- User edits live only in `state.playground.controls` and are not persisted per preset+feature

Requested behavior:

1. First run for a preset should use the snapshotted workflow graph values captured in the preset
2. Subsequent runs should use the latest values the user typed or submitted
3. Those later values should persist across page reloads

That means latest completed run values must stop being the authoritative fallback for defaults. The browser-persisted draft should be authoritative instead.

## Recommended Approach

Store a per-`presetId + featureId` draft in `localStorage` and hydrate controls from that draft before falling back to preset snapshot defaults.

Why this approach:

- Matches the requested semantics exactly: snapshot first, then latest typed/submitted values
- Survives reloads without backend/API changes
- Keeps scope bounded to Playground state and rendering
- Avoids coupling control defaults to run-history availability or run success

Rejected alternatives:

- Persist only the last submitted run payload: loses typed-but-not-run edits
- Persist on the backend: larger scope, unnecessary for the requirement

## Source of Truth Order

For any rendered control, resolve value in this order:

1. current in-memory edit from `state.playground.controls`
2. persisted per-preset-feature draft loaded into `_hydratedControls`
3. preset snapshot default from `preset.defaults`
4. registry fallback from `CONTROL_DEFS.defaultValue`

This preserves the existing visible-input behavior while replacing completed-run hydration as the persistent fallback.

## Data Model

Extend `web/studio-playground-state.js` with a second localStorage entry dedicated to control drafts.

- Keep existing selection storage unchanged:
  - `comfymodal.studio.playground.v1`
- Add draft storage key:
  - `comfymodal.studio.playground.drafts.v1`

Draft shape:

```json
{
  "presetA::txt2img": {
    "prompt": "a castle at dusk",
    "steps": 30,
    "guidance": 6.5
  },
  "presetA::img2img": {
    "strength": 0.45
  }
}
```

Scope rules:

- Drafts are isolated by preset and feature
- No cross-feature leakage
- No schema migration required

## Frontend Changes

### 1. Add draft helpers (`web/studio-playground-state.js`)

Add helpers:

- `makeDraftKey(presetId, featureId)`
- `loadControlDraft(presetId, featureId)`
- `saveControlDraft(presetId, featureId, controls)`
- `clearControlDraft(presetId, featureId)` (optional helper for tests/cleanup)

Behavior:

- Return `{}` on missing/invalid storage
- Only save plain object control maps
- Ignore storage errors just like selection persistence does now

### 2. Change hydration (`web/studio-playground.js`)

In `hydratePlayground(state, context)`:

- Continue restoring selected preset and feature from existing selection persistence
- Stop preferring latest completed run controls as the default hydration source
- After resolving the active preset+feature, load the persisted draft
- If a draft exists, assign it to `state.playground._hydratedControls`
- If no draft exists, seed `_hydratedControls` from `preset.defaults`
- Existing recent-runs/image restoration can remain for output preview/history selection, but not as default control authority

Important separation:

- Run preview/image restoration is still useful UX
- Control default restoration must no longer depend on latest completed run

Explicit split in the current Step 6 logic:

- **6a. Preview restoration:** restore `lastRunOutput` and `_selectedRun` from the latest completed matching run when available
- **6b. Control hydration:** restore `_hydratedControls` only from persisted draft or `preset.defaults`

Do not seed `_hydratedControls` from `latest.resolvedControls` or `latest.requestedControls` anymore.

### 3. Persist on user edits (`web/studio-playground.js`)

In `actions.setControl(ctrlId, value)`:

- Update `state.playground.controls` as today
- Determine current preset id and feature id
- Merge the new value into the effective draft for that preset+feature
- Save that draft immediately via `saveControlDraft(...)`

Use explicit read-merge-write behavior so a single changed control does not replace the entire draft object:

```javascript
const existing = loadControlDraft(presetId, featureId);
existing[ctrlId] = value;
saveControlDraft(presetId, featureId, existing);
```

Persist typed-but-not-run values across reloads, but coalesce writes so `localStorage.setItem(...)` does not run on every keystroke. A small debounce or equivalent coalescing mechanism is sufficient.

### 4. Preset/feature switching behavior

When `setFeature(featureId)` or `setBackend(backendId)` runs:

- Clear in-memory `controls`
- Clear stale `_selectedRun`
- Clear/replace `_hydratedControls`
- Rehydrate `_hydratedControls` from the target preset+feature draft if present
- Otherwise rehydrate from the target preset snapshot defaults

This ensures a switch immediately shows the correct defaults for the newly selected context instead of a blank panel until async render logic catches up.

Implementation note:

- `loadControlDraft(...)` is synchronous and can be called directly inside these actions
- `preset.defaults` may not yet be available synchronously for a newly selected preset because presets are loaded asynchronously in `renderControlPanel(...)`
- If `state.playground._currentPreset` is already available for the target preset, use its `defaults` as the no-draft fallback
- If not, a brief fallback to `CONTROL_DEFS.defaultValue` is acceptable until the async preset load completes and re-renders with snapshot defaults

### 5. Effective submission builder

`buildEffectiveControls(...)` should continue to submit all visible bound controls with this order:

1. `state.playground.controls`
2. `state.playground._hydratedControls`
3. `preset.defaults`

No backend payload change is required.

`renderControl(...)` must use the same precedence semantics as `buildEffectiveControls(...)`. Prefer explicit key existence checks over `??` so the render path and submit path cannot diverge for intentionally-set values.

Recommended rule:

```javascript
if (ctrlId in currentOverrides) return currentOverrides[ctrlId];
if (ctrlId in hydratedValues) return hydratedValues[ctrlId];
if (ctrlId in presetDefaults) return presetDefaults[ctrlId];
return def.defaultValue;
```

This keeps empty strings and any intentionally-set values authoritative.

### 6. Synchronous draft hydration before async preset fetch

To avoid races between async hydration and async preset rendering, load the persisted draft synchronously before the control panel's async preset fetch completes.

At the top of `renderControlPanel(...)`:

- resolve current `selectedBackendId` and `featureId`
- call `loadControlDraft(selectedBackendId, featureId)` synchronously
- if a draft exists, seed `_hydratedControls` immediately before the async `getRuntimePresets(...)` callback renders controls

This removes the window where controls might briefly render from snapshot defaults and then overwrite user-visible values after async hydration completes.

If no draft exists yet and no preset object is synchronously available, brief fallback rendering from `CONTROL_DEFS.defaultValue` is acceptable until the preset fetch resolves.

## Edge Cases

| Case | Behavior |
|------|----------|
| First load, no draft | Use `preset.defaults` from snapshot |
| Typed but never submitted | Persist immediately and use on next reload/run |
| Latest completed run differs from typed draft | Draft wins |
| Empty string value | Kept as user intent; does not fall back |
| Switching preset | Load that preset+feature draft or snapshot defaults |
| Switching feature | Load that preset+feature draft or snapshot defaults |
| Hidden/stale draft keys | Ignored by `buildEffectiveControls(...)` because it filters to visible control ids |
| Deleted preset | Orphaned draft is harmless; optional cleanup when invalid selection is cleared |
| localStorage unavailable | Fail soft, fall back to in-memory/session behavior |
| Experiment axis values change | Does not affect saved control drafts unless the user edits the underlying control value |

## Testing Strategy

Add tests covering both persistence helpers and the new precedence rules.

### State helper tests

1. save/load draft for `presetId::featureId`
2. missing storage returns empty object
3. malformed JSON returns empty object
4. different features do not collide

### Playground tests

1. first load with no draft shows preset snapshot defaults
2. user-typed value overrides snapshot default in rendered control
3. typed value is written to draft storage on input
4. reload restores draft instead of latest completed run controls
5. backend switch loads that backend's own draft/defaults
6. feature switch loads that feature's own draft/defaults
7. empty string persists and wins over snapshot default
8. preview restoration still uses latest completed run image without seeding control defaults from that run

## Implementation Boundaries

In scope:

- `web/studio-playground-state.js`
- `web/studio-playground.js`
- relevant tests

Out of scope:

- backend/API changes
- preset schema changes
- run-history storage changes
- server-side persistence

## Risks

1. **Race between async preset loading and draft hydration**
   - Mitigation: load draft synchronously in `renderControlPanel(...)` before async preset fetch completes, and re-resolve when the preset arrives

2. **Persisting stale keys for controls not visible in the current preset**
   - Mitigation: submission path already filters by visible controls; optional pruning is not required for this change

3. **Confusing coupling between preview restoration and control restoration**
   - Mitigation: explicitly separate image/run preview restoration from control-value hydration

4. **Synchronous localStorage writes on every keystroke**
   - Mitigation: debounce/coalesce draft persistence while keeping in-memory state updates immediate

## Self-Review

- No placeholders remain
- Scope is focused on a single frontend behavior change
- The design consistently uses draft persistence, not completed-run hydration, as the post-first-load authority
- The design now explicitly covers switch-time hydration, sync/async race handling, preview/control separation, and render-vs-submit precedence consistency
