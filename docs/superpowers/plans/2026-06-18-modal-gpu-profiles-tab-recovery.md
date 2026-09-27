# Modal GPU Profiles Tab Recovery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restore the old workflow profile authoring system as a dedicated top-level Profiles tab in the unified Modal GPU modal while keeping Setup focused on experiment composition.

**Architecture:** Add a new `testing-profiles.js` renderer and wire it into `modal-testing.js` as a first-class tab. Reuse/adapt profile-management logic from `modal-comparison.js`, then simplify `testing-setup.js` so it only selects and configures saved profiles for experiments. Preserve existing comparison/profile APIs and legacy compatibility paths where possible.

**Tech Stack:** Plain ES modules, DOM APIs, shared stylesheet injection, existing `/comfymodal/comparison/profiles*` APIs, Python structural tests, focused browser verification.

---

### File map

**Primary UI files**
- Create: `web/testing-profiles.js` — new dedicated Profiles tab renderer
- Modify: `web/modal-testing.js` — add Profiles tab constant, nav button, lazy mounting
- Modify: `web/testing-setup.js` — reduce to experiment-facing profile selection only
- Modify: `web/testing-styles.js` — Profiles layout + editor workspace styling

**Reference / compatibility file**
- Read / possibly lightly modify: `web/modal-comparison.js` — source of truth for legacy profile behavior

**Tests**
- Modify: `tests/test_testing_results_js.py` — shell tab expectations currently live here
- Create or modify: `tests/test_testing_profiles_js.py`
- Modify: `tests/test_testing_setup_js.py`

### Task 1: Add failing structural tests for the new Profiles tab

**Files:**
- Modify: `tests/test_testing_results_js.py`
- Create: `tests/test_testing_profiles_js.py`

- [ ] Add a shell-level failing assertion for the new tab label in `tests/test_testing_results_js.py`.

```python
def test_six_tabs(self):
    for tab in ("Dashboard", "Setup", "Profiles", "Results", "History", "Settings"):
        with self.subTest(tab=tab):
            self.assertIn(tab, self.m.text)
```

- [ ] Add a new structural test module for `web/testing-profiles.js`.

```python
class ProfilesTabTests(unittest.TestCase):
    def setUp(self) -> None:
        self.m = _JsModule(REPO_ROOT / "web" / "testing-profiles.js")
        if not self.m.text:
            self.skipTest("web/testing-profiles.js missing")

    def test_exports_profiles_tab_render(self):
        self.assertTrue(self.m.has_export("profiles_tab_render"))

    def test_contains_create_from_canvas_controls(self):
        self.assertIn("Create from Canvas", self.m.text)
        self.assertIn("Profile name", self.m.text)

    def test_contains_saved_profiles_workspace_markers(self):
        self.assertIn("testing-profiles-list", self.m.text)
        self.assertIn("testing-profiles-editor", self.m.text)

    def test_contains_mapping_assistant_markers(self):
        self.assertIn("Mapping Assistant", self.m.text)
        self.assertIn("Save Mappings", self.m.text)
```

- [ ] Run the focused tests and verify they fail.

Run: `python -m pytest tests/test_testing_results_js.py tests/test_testing_profiles_js.py -v`

Expected: FAIL because the Profiles tab and renderer do not exist yet.

### Task 2: Add the new Profiles tab to the modal shell

**Files:**
- Modify: `web/modal-testing.js`
- Test: `tests/test_testing_results_js.py`

- [ ] Add the new tab constant and lazy module entry.

```js
const TAB_PROFILES = "profiles";

const TAB_MODULES = {
  [TAB_DASHBOARD]: { path: "./testing-dashboard.js", fn: "dashboard_tab_render" },
  [TAB_SETUP]:    { path: "./testing-setup.js", fn: "setup_tab_render" },
  [TAB_PROFILES]: { path: "./testing-profiles.js", fn: "profiles_tab_render" },
  [TAB_RESULTS]:  { path: "./testing-results.js", fn: "results_tab_render" },
  [TAB_HISTORY]:  { path: "./testing-history.js", fn: "history_tab_render" },
  [TAB_SETTINGS]: { path: "./testing-settings.js", fn: "settings_tab_render" },
};
```

- [ ] Add the nav button between Setup and Results.

```js
el("button", { class: "comfymodal-testing-nav-btn", "data-tab": TAB_PROFILES, text: "Profiles" }),
```

- [ ] Add a page wrapper class for the Profiles tab.

```js
[TAB_PROFILES]: "testing-profiles-page",
```

- [ ] Run the shell-focused tests.

Run: `python -m pytest tests/test_testing_results_js.py -v`

Expected: PASS on the new tab expectation, other new Profiles tests still failing.

### Task 3: Build the Profiles tab skeleton and failing profile-structure tests

**Files:**
- Create: `web/testing-profiles.js`
- Test: `tests/test_testing_profiles_js.py`

- [ ] Create the minimal renderer export and root structure.

```js
export function profiles_tab_render(rootEl, api, options = {}) {
  if (!rootEl) throw new Error("profiles_tab_render: rootEl is required");
  while (rootEl.firstChild) rootEl.removeChild(rootEl.firstChild);
  const root = document.createElement("div");
  root.className = "testing-profiles-root";
  root.appendChild(document.createElement("div")).className = "testing-profiles-create-card";
  root.appendChild(document.createElement("div")).className = "testing-profiles-workspace";
  rootEl.appendChild(root);
  return { rootEl: root, stop() {} };
}
```

- [ ] Add structural hooks for list and editor panes.

```js
const workspace = el("div", { class: "testing-profiles-workspace" }, [
  el("div", { class: "testing-profiles-list", "data-testid": "profiles-list" }),
  el("div", { class: "testing-profiles-editor", "data-testid": "profiles-editor" }),
]);
```

- [ ] Run the Profiles tests.

Run: `python -m pytest tests/test_testing_profiles_js.py -v`

Expected: some tests pass, feature-detail tests still fail until behavior is added.

### Task 4: Port create-from-canvas profile creation from legacy UI

**Files:**
- Modify: `web/testing-profiles.js`
- Read for reference: `web/modal-comparison.js:164-276`
- Test: `tests/test_testing_profiles_js.py`

- [ ] Add the create card controls and labels.

```js
const nameInput = el("input", {
  type: "text",
  placeholder: "Profile name (e.g. Flux2 Klein FP8)",
  class: "testing-profiles-name-input comfymodal-input",
});

const createBtn = el("button", {
  class: "comfymodal-primary-btn testing-profiles-create-btn",
  text: "Create from Canvas",
});
```

- [ ] Implement the create flow using the existing comparison profile API.

```js
const graphData = await app.graphToPrompt();
const data = await fetchJson(`${apiBase}/comparison/profiles`, {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ name, workflow_api: graphData.output, workflow: graphData.workflow || null }),
});
await fetchJson(`${apiBase}/comparison/profiles/${encodeURIComponent(data.profile.id)}/detect-slots`, {
  method: "POST",
});
```

- [ ] Add a failing/passing structural test for API endpoint usage.

```python
def test_uses_comparison_profile_create_api(self):
    self.assertIn('/comparison/profiles', self.m.text)
    self.assertIn('detect-slots', self.m.text)
```

- [ ] Run the Profiles tests.

Run: `python -m pytest tests/test_testing_profiles_js.py -v`

Expected: PASS on create-flow assertions.

### Task 5: Port the saved profiles list and lifecycle actions

**Files:**
- Modify: `web/testing-profiles.js`
- Read for reference: `web/modal-comparison.js:341-508`
- Test: `tests/test_testing_profiles_js.py`

- [ ] Implement profile list loading from the existing API.

```js
const data = await fetchJson(`${apiBase}/comparison/profiles`);
const profiles = data.profiles || [];
```

- [ ] Render each row with name, status badge, model summary, and actions.

```js
el("button", { class: "comfymodal-secondary-btn", text: "Edit" })
el("button", { class: "comfymodal-secondary-btn", text: "Validate" })
el("button", { class: "comfymodal-secondary-btn", text: "Duplicate" })
el("button", { class: "comfymodal-destructive-btn", text: "Delete" })
```

- [ ] Implement duplicate and delete against existing endpoints.

```js
await fetchJson(`${apiBase}/comparison/profiles/${encodeURIComponent(profileId)}/duplicate`, { method: "POST" });
await fetchJson(`${apiBase}/comparison/profiles/${encodeURIComponent(profileId)}`, { method: "DELETE" });
```

- [ ] Implement rename if the old API still supports it.

```js
await fetchJson(`${apiBase}/comparison/profiles/${encodeURIComponent(profileId)}`, {
  method: "PUT",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ name: nextName }),
});
```

- [ ] Add structural tests for lifecycle actions.

```python
def test_contains_profile_lifecycle_actions(self):
    for label in ("Edit", "Validate", "Duplicate", "Delete"):
        with self.subTest(label=label):
            self.assertIn(label, self.m.text)
```

- [ ] Run the Profiles tests.

Run: `python -m pytest tests/test_testing_profiles_js.py -v`

Expected: PASS on lifecycle-action assertions.

### Task 6: Build the selected-profile editor and mapping assistant

**Files:**
- Modify: `web/testing-profiles.js`
- Read for reference: `web/modal-comparison.js:533-737`
- Test: `tests/test_testing_profiles_js.py`

- [ ] Add selected-profile editor regions.

```js
const editor = el("div", { class: "testing-profiles-editor" }, [
  el("div", { class: "testing-profiles-editor-header" }),
  el("div", { class: "testing-profiles-model-section" }),
  el("div", { class: "testing-profiles-mapping-section" }),
  el("div", { class: "testing-profiles-validation-section" }),
]);
```

- [ ] Port the mapping assistant slot coverage and save flow.

```js
const SLOT_KEYS = [
  "prompt", "negative_prompt", "seed", "steps",
  "guidance", "width", "height", "input_image",
];

await fetchJson(`${apiBase}/comparison/profiles/${encodeURIComponent(profileId)}/detect-slots`, { method: "POST" });
await fetchJson(`${apiBase}/comparison/profiles/${encodeURIComponent(profileId)}/slots`, {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ slots }),
});
```

- [ ] Keep explicit “Save Mappings” action and “Mapping Assistant” label.

```js
el("button", { class: "comfymodal-primary-btn", text: "Save Mappings" })
```

- [ ] Add structural tests for mapping hooks.

```python
def test_contains_mapping_slot_keys(self):
    for key in ("prompt", "negative_prompt", "seed", "steps", "guidance", "width", "height", "input_image"):
        with self.subTest(key=key):
            self.assertIn(key, self.m.text)
```

- [ ] Run the Profiles tests.

Run: `python -m pytest tests/test_testing_profiles_js.py -v`

Expected: PASS on mapping-assistant assertions.

### Task 7: Recover the profile-facing model configuration editor

**Files:**
- Modify: `web/testing-profiles.js`
- Modify: `web/testing-setup.js`
- Test: `tests/test_testing_profiles_js.py`
- Test: `tests/test_testing_setup_js.py`

- [ ] Move model-triple editing ownership from Setup into the selected-profile editor.

```js
el("label", { class: "testing-profiles-field" }, [
  el("span", { class: "testing-profiles-field-label", text: "UNet" }),
  el("input", { class: "testing-profiles-model-unet comfymodal-input", type: "text" }),
])
```

- [ ] Keep Setup focused on profile selection only by removing the dedicated model-profiles authoring section.

```js
const SECTION_LABELS = {
  experiment: "Experiment",
  workflows: "Workflows",
  loras: "LoRAs",
  prompts: "Prompts",
  images: "Images",
  axes: "Axes",
  containers: "Execution",
  preview: "Review & Run",
};
```

- [ ] Replace Setup’s authoring affordances with a redirective hint.

```js
el("div", { class: "testing-setup-section-help", text: "Need to create or repair a workflow profile? Use the Profiles tab." })
```

- [ ] Add structural tests that Setup is no longer the primary profile-authoring surface.

```python
def test_setup_no_longer_contains_model_profiles_section(self):
    self.assertNotIn("Model Profiles", self.m.text)

def test_setup_points_users_to_profiles_tab(self):
    self.assertIn("Profiles tab", self.m.text)
```

- [ ] Run Setup + Profiles tests.

Run: `python -m pytest tests/test_testing_setup_js.py tests/test_testing_profiles_js.py -v`

Expected: PASS on the new ownership split.

### Task 8: Style the new Profiles workspace and page shell

**Files:**
- Modify: `web/testing-styles.js`
- Test: `tests/test_testing_profiles_js.py`

- [ ] Add Profiles page wrapper classes.

```css
.testing-profiles-page,
.testing-profiles-root {
  height: 100%;
}
```

- [ ] Add workspace layout and editor styling hooks.

```css
.testing-profiles-workspace {
  display: grid;
  grid-template-columns: 320px minmax(0, 1fr);
  gap: var(--space-md);
  min-height: 0;
}

.testing-profiles-list,
.testing-profiles-editor,
.testing-profiles-create-card {
  background: var(--color-bg-surface);
  border: 1px solid var(--color-border-default);
  border-radius: var(--radius-lg);
}
```

- [ ] Add list-row, badge, model-editor, and mapping-section rules.

```css
.testing-profiles-row-actions { display: flex; gap: var(--space-xs); flex-wrap: wrap; }
.testing-profiles-model-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: var(--space-sm); }
.testing-profiles-mapping-section { display: flex; flex-direction: column; gap: var(--space-sm); }
```

- [ ] Run the Profiles tests.

Run: `python -m pytest tests/test_testing_profiles_js.py -v`

Expected: structural hooks still pass after styling additions.

### Task 9: Preserve or redirect legacy profile entry points

**Files:**
- Modify: `web/modal-comparison.js`
- Modify: `web/testing-dashboard.js` if needed

- [ ] Decide the compatibility path: keep legacy overlay available temporarily or redirect open actions to the new tab.

```js
window.openComparisonProfilesOverlay = function () {
  if (typeof window.open_testing_modal === "function") {
    window.open_testing_modal("profiles");
    return;
  }
  return openProfilesOverlayLegacy();
};
```

- [ ] Preserve context-menu slot assignment integration.

```js
// keep existing app.canvas.getNodeMenuOptions wrapper in place
// until the new Profiles tab is fully verified
```

- [ ] Run focused tests plus a manual smoke check that legacy entry still reaches Profiles.

Run: `python -m pytest tests/test_testing_results_js.py tests/test_testing_profiles_js.py -v`

Expected: PASS, plus manual nav opens Profiles tab.

### Task 10: Final verification

**Files:**
- Verify: `web/modal-testing.js`
- Verify: `web/testing-profiles.js`
- Verify: `web/testing-setup.js`
- Verify: `web/testing-styles.js`
- Verify: `web/modal-comparison.js`
- Verify: `tests/test_testing_setup_js.py`
- Verify: `tests/test_testing_results_js.py`
- Verify: `tests/test_testing_profiles_js.py`

- [ ] Run syntax checks.

Run:

```powershell
node -c web/testing-profiles.js
node -c web/testing-setup.js
node -c web/modal-testing.js
node -c web/testing-styles.js
```

Expected: no output.

- [ ] Run focused structural tests.

Run:

```powershell
python -m pytest tests/test_testing_setup_js.py tests/test_testing_results_js.py tests/test_testing_profiles_js.py -v
```

Expected: all pass.

- [ ] Perform live browser smoke verification.

Checklist:
- open Modal GPU modal
- confirm Profiles tab appears between Setup and Results
- create a profile from canvas
- select profile in Profiles workspace
- validate profile
- duplicate profile
- delete a test profile
- open mapping assistant and save mappings
- confirm Setup still selects saved profiles for experiment composition

- [ ] If everything passes, summarize any remaining compatibility gaps explicitly.
