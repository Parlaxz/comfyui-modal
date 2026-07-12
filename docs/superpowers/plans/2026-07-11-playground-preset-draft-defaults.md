# Playground Preset Draft Defaults Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Playground use preset snapshot defaults on first load, then persist and reuse the latest typed/submitted values per preset+feature across reloads.

**Architecture:** Keep the change frontend-only. Add a per-preset-feature draft store in `web/studio-playground-state.js`, hydrate `_hydratedControls` from that draft synchronously and during async hydration, and stop using latest completed run controls as the authoritative default source.

**Tech Stack:** Vanilla JavaScript frontend, localStorage persistence, Python `unittest` structural/source tests.

---

### Task 1: Add failing persistence/state tests

**Files:**
- Modify: `tests/test_studio_backend.py`
- Test target: `pytest tests/test_studio_backend.py -q`

- [ ] **Step 1: Write failing tests for draft persistence helpers**

Add assertions that `web/studio-playground-state.js` contains:

```python
self.assertIn("comfymodal.studio.playground.drafts.v1", state_text)
self.assertIn("loadControlDraft", state_text)
self.assertIn("saveControlDraft", state_text)
```

and that `web/studio-playground.js` contains:

```python
self.assertIn("loadControlDraft", pg_text)
self.assertIn("saveControlDraft", pg_text)
```

- [ ] **Step 2: Write failing tests for new precedence/hydration behavior**

Add assertions that `web/studio-playground.js`:

```python
self.assertIn("state.playground._hydratedControls = draft", self.text)
self.assertIn("loadControlDraft", self.text)
self.assertIn("saveControlDraft", self.text)
self.assertIn("lastRunOutput", self.text)
self.assertIn("_selectedRun", self.text)
```

and does **not** seed `_hydratedControls` from completed run controls anymore:

```python
self.assertNotIn("latest.resolvedControls || latest.requestedControls", self.text)
```

- [ ] **Step 3: Run the test to verify it fails**

Run: `pytest tests/test_studio_backend.py -q`

Expected: FAIL because the new helpers and hydration strings do not exist yet.

- [ ] **Step 4: Commit**

Do not commit unless explicitly requested by the user.

### Task 2: Implement draft persistence helpers

**Files:**
- Modify: `web/studio-playground-state.js`
- Test: `tests/test_studio_backend.py`

- [ ] **Step 1: Write minimal helper implementation**

Add:

```javascript
const DRAFTS_STORAGE_KEY = "comfymodal.studio.playground.drafts.v1";

function makeDraftKey(presetId, featureId) {
  return `${presetId || ""}::${featureId || ""}`;
}

export function loadControlDraft(presetId, featureId) {
  try {
    const raw = localStorage.getItem(DRAFTS_STORAGE_KEY);
    const parsed = raw ? JSON.parse(raw) : {};
    if (!parsed || typeof parsed !== "object") return {};
    const draft = parsed[makeDraftKey(presetId, featureId)];
    return draft && typeof draft === "object" ? draft : {};
  } catch (e) {
    return {};
  }
}

export function saveControlDraft(presetId, featureId, controls) {
  try {
    const raw = localStorage.getItem(DRAFTS_STORAGE_KEY);
    const parsed = raw ? JSON.parse(raw) : {};
    const next = parsed && typeof parsed === "object" ? parsed : {};
    next[makeDraftKey(presetId, featureId)] = controls && typeof controls === "object" ? controls : {};
    localStorage.setItem(DRAFTS_STORAGE_KEY, JSON.stringify(next));
  } catch (e) {
  }
}
```

- [ ] **Step 2: Run the targeted test**

Run: `pytest tests/test_studio_backend.py -q`

Expected: still FAIL because playground integration is not implemented yet.

- [ ] **Step 3: Commit**

Do not commit unless explicitly requested by the user.

### Task 3: Implement playground hydration and persistence behavior

**Files:**
- Modify: `web/studio-playground.js`
- Test: `tests/test_studio_backend.py`

- [ ] **Step 1: Import the new helpers**

Update the state import to include:

```javascript
import {
  saveSelection,
  loadSelection,
  clearSelection,
  loadControlDraft,
  saveControlDraft,
} from "./studio-playground-state.js";
```

- [ ] **Step 2: Add a small helper for effective hydrated defaults**

Add a focused helper such as:

```javascript
function hydrateControlsForSelection(state, presetId, featureId, preset) {
  const draft = presetId && featureId ? loadControlDraft(presetId, featureId) : {};
  if (draft && Object.keys(draft).length > 0) {
    state.playground._hydratedControls = draft;
    return;
  }
  state.playground._hydratedControls = ((preset && preset.defaults) || {});
}
```

- [ ] **Step 3: Update `hydratePlayground(...)`**

Keep latest completed run preview restoration:

```javascript
state.playground.lastRunOutput = latest.imageUrl;
state.playground._selectedRun = latest;
```

but remove completed-run control seeding and instead call the new helper after active preset resolution:

```javascript
const preset = presets.find(function (p) { return (p.id || p.label || "") === targetPresetId; });
hydrateControlsForSelection(state, targetPresetId, featureId, preset);
```

- [ ] **Step 4: Update `renderControlPanel(...)` for synchronous draft hydration**

Before async preset loading completes, synchronously seed `_hydratedControls` from the current preset+feature draft when available.

- [ ] **Step 5: Update `setFeature(...)` and `setBackend(...)`**

After clearing in-memory `controls`, immediately rehydrate `_hydratedControls` for the target preset+feature using the helper and current preset when available.

- [ ] **Step 6: Persist user edits with coalesced writes**

In `setControl(...)`:

```javascript
state.playground.controls[ctrlId] = value;
const presetId = state.playground.selectedBackendId;
const featureId = state.playground.featureId;
clearTimeout(state.playground._draftSaveTimer);
state.playground._draftSaveTimer = setTimeout(function () {
  const existing = loadControlDraft(presetId, featureId);
  existing[ctrlId] = value;
  saveControlDraft(presetId, featureId, existing);
}, 300);
```

- [ ] **Step 7: Unify render and submit precedence**

Change `renderControl(...)` to use explicit key existence checks instead of `??`, matching `buildEffectiveControls(...)` semantics.

- [ ] **Step 8: Run the targeted test to verify it passes**

Run: `pytest tests/test_studio_backend.py -q`

Expected: PASS.

- [ ] **Step 9: Commit**

Do not commit unless explicitly requested by the user.

### Task 4: Verify the change end-to-end

**Files:**
- Verify only

- [ ] **Step 1: Run focused tests**

Run: `pytest tests/test_studio_backend.py -q`

Expected: PASS.

- [ ] **Step 2: Run broader regression coverage**

Run: `pytest tests/test_testing_ui_wired.py tests/test_modal_workspace_ui_ast.py -q`

Expected: PASS.

- [ ] **Step 3: Review requirements against the spec**

Check that the implementation satisfies:

```text
first load -> preset snapshot defaults
subsequent typed/submitted values -> persisted draft wins
reloads -> persisted draft restored
completed run preview restoration -> kept, but no longer seeds defaults
```

- [ ] **Step 4: Commit**

Do not commit unless explicitly requested by the user.
