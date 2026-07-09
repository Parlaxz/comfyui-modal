# Modal GPU Progressive Clarity Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild the Modal GPU popup shell, dashboard, setup, results, and history surfaces so the UI feels stable, calmer, and easier to scan, with progressive disclosure in Setup and clearer emphasis everywhere else.

**Architecture:** Keep the current modal ownership, tabs, APIs, and experiment flows intact. Implement the redesign by (1) tightening shell dimensions and header chrome in `web/modal-testing.js`, (2) expanding `web/testing-styles.js` into stronger page-level layout primitives, and (3) refactoring dashboard/setup/results/history renderers to emit better hierarchy hooks, progressive-collapse structure, and lower-clutter action groupings without changing backend semantics.

**Tech Stack:** Plain ES modules, DOM APIs, shared stylesheet injection, Python structural tests, Playwright/manual browser verification.

---

### File map

**Primary UI files**
- `web/modal-testing.js` — stable shell size, header cleanup, tab/body structure hooks
- `web/testing-styles.js` — shell sizing, page-level surfaces, collapsed setup card styling, dashboard hierarchy, results zone styling, skim-friendly history rows
- `web/testing-dashboard.js` — strong CTA hierarchy, healthy-state cleanup, supporting metrics layout
- `web/testing-setup.js` — progressive collapse, simplified phase rail, lower-clutter profile actions, advanced sections, finish zone styling
- `web/testing-results.js` — results zone layering, clearer summary emphasis, quieter routine controls vs separated destructive controls
- `web/testing-history.js` — two-line skim layout and lower-clutter metadata grouping

**Tests**
- `tests/test_testing_shell_integration.py`
- `tests/test_testing_ui_wired.py`
- `tests/test_testing_setup_js.py`
- `tests/test_testing_results_js.py`

### Task 1: Add failing shell and dashboard hierarchy tests

**Files:**
- Modify: `tests/test_testing_shell_integration.py`
- Modify: `tests/test_testing_ui_wired.py`

- [ ] Add failing structural tests for fixed shell sizing, subtitle removal, and new shell hooks.

```python
def test_shell_uses_fixed_modal_dimensions(self):
    self.assertIn("width: 1200px", self.css)
    self.assertIn("height: 780px", self.css)

def test_modal_header_does_not_render_cloud_subtitle(self):
    self.assertNotIn("Cloud execution and testing", self.modal_js)
```

- [ ] Add failing tests for dashboard emphasis and removal of the healthy-state deploy strip.

```python
def test_dashboard_uses_primary_cta_group_marker(self):
    self.assertIn("testing-dashboard-primary-actions", self.dashboard_js)

def test_dashboard_removes_healthy_deploy_strip(self):
    self.assertNotIn("comfymodal-deploy-strip", self.dashboard_js)
```

- [ ] Run the focused shell/dashboard tests and verify the new assertions fail.

```powershell
python run_tests.py tests.test_testing_shell_integration tests.test_testing_ui_wired
```

Expected: FAIL on the new shell sizing, subtitle, and dashboard marker assertions.

### Task 2: Add failing Setup progressive-collapse tests

**Files:**
- Modify: `tests/test_testing_setup_js.py`
- Modify: `tests/test_testing_ui_wired.py`

- [ ] Add failing tests for phase rail, collapsed card hooks, advanced fold markers, and de-emphasized profile utility actions.

```python
def test_setup_uses_phase_rail_marker(self):
    self.assertIn("testing-setup-phase-rail", self.js)

def test_setup_uses_collapsible_section_markers(self):
    self.assertIn("testing-setup-section-collapsible", self.js)
    self.assertIn("data-collapsed", self.js)

def test_setup_uses_advanced_axes_marker(self):
    self.assertIn("testing-setup-advanced-toggle", self.js)

def test_setup_uses_profile_menu_marker(self):
    self.assertIn("testing-setup-profile-menu", self.js)
```

- [ ] Run Setup tests and verify they fail before implementation.

```powershell
python run_tests.py tests.test_testing_setup_js tests.test_testing_ui_wired
```

Expected: FAIL because the new progressive-collapse hooks do not exist yet.

### Task 3: Add failing Results and History clarity tests

**Files:**
- Modify: `tests/test_testing_results_js.py`
- Modify: `tests/test_testing_shell_integration.py`
- Modify: `tests/test_testing_ui_wired.py`

- [ ] Add failing tests for stronger results-zone markers and quieter routine vs separated destructive controls.

```python
def test_results_uses_emphasized_summary_value_marker(self):
    self.assertIn("testing-results-summary-primary", self.js)

def test_results_uses_separated_danger_controls_marker(self):
    self.assertIn("testing-results-command-danger", self.js)
    self.assertIn("testing-results-command-routine", self.js)
```

- [ ] Add failing tests for the new history skim-row structure.

```python
def test_history_uses_two_line_row_markers(self):
    self.assertIn("testing-history-row-main", self.history_js)
    self.assertIn("testing-history-row-meta", self.history_js)
```

- [ ] Run the focused Results/History tests and verify they fail.

```powershell
python run_tests.py tests.test_testing_results_js tests.test_testing_shell_integration tests.test_testing_ui_wired
```

Expected: FAIL on the new results/history structure hooks.

### Task 4: Build the fixed shell and page-level styling system

**Files:**
- Modify: `web/testing-styles.js`
- Modify: `web/modal-testing.js`
- Test: `tests/test_testing_shell_integration.py`

- [ ] Update the shell to use a stable modal frame and remove the subtitle from the header.

```js
const header = el("div", { class: "comfymodal-testing-header" }, [
  el("h2", { text: "Modal GPU" }),
  el("button", { class: "comfymodal-testing-close", text: "✕" }),
]);
```

- [ ] Add fixed modal dimensions and page-shell styling in `web/testing-styles.js`.

```js
.comfymodal-testing-modal {
  width: 1200px;
  height: 780px;
  max-width: calc(100vw - 48px);
  max-height: calc(100vh - 48px);
}

.comfymodal-testing-body {
  min-height: 0;
  overflow: hidden;
}
```

- [ ] Add page-level surface primitives for dashboard/setup/results/history rather than relying on inline styles.

```js
.testing-dashboard-page,
.testing-setup-page,
.testing-results-page,
.testing-history-page {
  height: 100%;
  overflow: auto;
  padding: var(--space-xl);
}
```

- [ ] Run focused shell tests and verify they pass.

```powershell
python run_tests.py tests.test_testing_shell_integration tests.test_testing_ui_wired
```

Expected: shell/header tests pass.

### Task 5: Rebuild the dashboard hierarchy

**Files:**
- Modify: `web/testing-dashboard.js`
- Modify: `web/testing-styles.js`
- Test: `tests/test_testing_shell_integration.py`
- Test: `tests/test_testing_ui_wired.py`

- [ ] Refactor healthy-state dashboard markup to remove the deploy strip and expose stronger primary action group hooks.

```js
function buildHealthyHeader(spec) {
  return el("section", { class: "testing-dashboard-primary-actions" }, [
    el("button", { class: "comfymodal-primary-btn testing-dashboard-cta-main", text: "New Experiment", onclick: openSetupTab }),
    el("div", { class: "testing-dashboard-secondary-actions" }, [
      spec.activeExpCount > 0 ? el("button", { class: "comfymodal-secondary-btn", text: `Resume Active (${spec.activeExpCount})`, onclick: openResultsTab }) : null,
      el("button", { class: "comfymodal-secondary-btn", text: "Open Results", onclick: openResultsTab }),
    ]),
  ]);
}
```

- [ ] Move utility actions into a visually subordinate group.

```js
function buildUtilityToolbar() {
  return el("div", { class: "testing-dashboard-utility-toolbar" }, [
    el("button", { class: "comfymodal-secondary-btn", text: "Comparison Profiles", onclick: openComparisonProfiles }),
    el("button", { class: "comfymodal-secondary-btn", text: "Quick Comparison", onclick: openComparisonRunner }),
  ]);
}
```

- [ ] Restyle metrics so Experiments is visually dominant and Workers/Last Run are supporting cards.

```js
el("div", { class: "testing-dashboard-metrics" }, [
  el("article", { class: "testing-dashboard-metric testing-dashboard-metric-primary" }, [/* experiments */]),
  el("article", { class: "testing-dashboard-metric" }, [/* workers */]),
  el("article", { class: "testing-dashboard-metric" }, [/* last run */]),
]);
```

- [ ] Run dashboard-focused tests and verify they pass.

```powershell
python run_tests.py tests.test_testing_shell_integration tests.test_testing_ui_wired
```

Expected: dashboard hierarchy tests pass.

### Task 6: Rebuild Setup with progressive collapse and reduced clutter

**Files:**
- Modify: `web/testing-setup.js`
- Modify: `web/testing-styles.js`
- Test: `tests/test_testing_setup_js.py`
- Test: `tests/test_testing_ui_wired.py`

- [ ] Replace the loud step rail with calmer phase-rail markup.

```js
const PHASES = [
  { key: "define", label: "Define" },
  { key: "configure", label: "Configure" },
  { key: "modifiers", label: "Modifiers" },
  { key: "review", label: "Review" },
];
```

- [ ] Add collapsible section-card state so only the active section opens by default.

```js
function setSectionCollapsed(sectionEl, collapsed) {
  sectionEl.setAttribute("data-collapsed", collapsed ? "true" : "false");
  sectionEl.classList.toggle("testing-setup-section-collapsible", true);
}
```

- [ ] Make Create from Canvas the main workflow action and tuck lower-priority actions into a compact profile menu.

```js
const profileMenu = el("details", { class: "testing-setup-profile-menu" }, [
  el("summary", { text: "More actions" }),
  menuBody,
]);
```

- [ ] Convert Axes advanced controls into a lower-emphasis expandable area.

```js
const advancedAxes = el("details", { class: "testing-setup-advanced-toggle" }, [
  el("summary", { text: "Advanced axes" }),
  advancedFieldGrid,
]);
```

- [ ] Keep the working popup-scroll-aware navigation and active-step sync, but remap them to the calmer phase/section model.

```js
const activePhase = getPhaseForSectionKey(currentStep);
phaseRail.querySelectorAll("[data-phase-key]").forEach(/* update active */);
```

- [ ] Give Review & Run a visually distinct finish surface and cleaner summary.

```js
el("div", { class: "testing-setup-finish-zone testing-setup-finish-zone-prominent" }, [summaryEl, compileBtn]);
```

- [ ] Run Setup-focused tests and verify they pass.

```powershell
python run_tests.py tests.test_testing_setup_js tests.test_testing_ui_wired tests.test_testing_shell_integration
```

Expected: Setup collapse, phase rail, menu, and advanced-toggle tests pass.

### Task 7: Strengthen Results zone hierarchy and action emphasis

**Files:**
- Modify: `web/testing-results.js`
- Modify: `web/testing-styles.js`
- Test: `tests/test_testing_results_js.py`
- Test: `tests/test_testing_ui_wired.py`

- [ ] Split routine vs destructive controls with clearer structure hooks.

```js
el("div", { class: "testing-results-command-routine" }, routineButtons)
el("div", { class: "testing-results-command-danger" }, dangerButtons)
```

- [ ] Make the summary zone visually dominant with a clear primary value hook.

```js
el("div", { class: "testing-results-summary-primary" }, [
  el("span", { class: "summary-stat-value", text: completedText }),
]);
```

- [ ] Keep existing data semantics but improve empty states, zone spacing, and surface contrast.

```js
el("div", { class: "testing-results-empty-state", text: "Choose an experiment to see live progress and outputs." })
```

- [ ] Run Results-focused tests and verify they pass.

```powershell
python run_tests.py tests.test_testing_results_js tests.test_testing_ui_wired tests.test_testing_shell_integration
```

Expected: results emphasis and command-group tests pass.

### Task 8: Rebuild History into skim-friendly two-line rows

**Files:**
- Modify: `web/testing-history.js`
- Modify: `web/testing-styles.js`
- Test: `tests/test_testing_shell_integration.py`
- Test: `tests/test_testing_ui_wired.py`

- [ ] Replace the current dense row layout with explicit main/meta row markers.

```js
return el("div", { class: "testing-history-row comfymodal-history-row" }, [
  el("div", { class: "testing-history-row-main" }, [thumb, nameEl]),
  el("div", { class: "testing-history-row-meta" }, [statusEl, timeEl, durationEl, modelEl]),
]);
```

- [ ] Use tooltips or lower-emphasis secondary text for supporting metadata instead of equal-weight columns.

```js
el("span", { class: "testing-history-model", title: run.model || run.profile || "", text: shortModelLabel })
```

- [ ] Run focused history-related tests and verify they pass.

```powershell
python run_tests.py tests.test_testing_shell_integration tests.test_testing_ui_wired
```

Expected: history skim-layout tests pass.

### Task 9: Full verification and live browser review

**Files:**
- Verify: `web/modal-testing.js`
- Verify: `web/testing-styles.js`
- Verify: `web/testing-dashboard.js`
- Verify: `web/testing-setup.js`
- Verify: `web/testing-results.js`
- Verify: `web/testing-history.js`

- [ ] Run the full focused frontend suite.

```powershell
python run_tests.py tests.test_testing_shell_integration tests.test_testing_ui_wired tests.test_testing_results_js tests.test_testing_setup_js
```

Expected: all targeted tests pass.

- [ ] Run syntax checks on all changed frontend files.

```powershell
node --check "web/modal-testing.js"
node --check "web/testing-styles.js"
node --check "web/testing-dashboard.js"
node --check "web/testing-setup.js"
node --check "web/testing-results.js"
node --check "web/testing-history.js"
```

Expected: no syntax errors.

- [ ] Verify in the live browser against `http://127.0.0.1:8188/`.

```text
1. Open Modal GPU sidebar tab
2. Open Testing Suite
3. Confirm the shell size stays visually constant across Dashboard, Setup, Results, History, Settings
4. Confirm the subtitle is gone
5. Confirm Dashboard emphasizes New Experiment first and no healthy deployment strip is shown
6. Confirm Setup no longer opens as a wall of equally weighted content
7. Confirm Results zones are clearly separated and destructive controls recede appropriately
8. Confirm History rows are easier to skim
```

- [ ] Report exactly what changed and any remaining limitations.
