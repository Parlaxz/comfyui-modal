# Modal GPU Setup + Results Clarity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild the Setup and Results pages so they feel guided, calm, and operationally clear while fixing the broken Setup step-rail navigation inside the popup.

**Architecture:** Keep the existing Modal GPU popup, API wiring, and experiment behavior intact. Refactor the Setup and Results renderers to emit cleaner structural hooks, then expand `web/testing-styles.js` with stronger layout utilities and page-specific rules so the two screens gain better spacing, grouping, and action hierarchy without backend changes.

**Tech Stack:** Plain ES modules, DOM APIs, shared stylesheet injection, Python structural tests, Playwright/manual browser verification.

---

### File map

**Primary UI files**
- `web/testing-setup.js` — Setup rail behavior, section ordering, contextual toolbars, section layout hooks, compile/run finish zone
- `web/testing-results.js` — Results command bar, summary/progress/grouping structure, cleaner result-card markup, comparison workspace grouping
- `web/testing-styles.js` — Shared spacing/layout tokens plus Setup/Results-specific page rules and responsive behavior

**Support file if needed**
- `web/modal-testing.js` — only for minimal wrapper class hooks if Setup/Results need an extra page shell marker

**Tests**
- `tests/test_testing_setup_js.py`
- `tests/test_testing_results_js.py`
- `tests/test_testing_shell_integration.py`
- `tests/test_testing_ui_wired.py`

### Task 1: Add failing tests for the Setup navigation and structure rebuild

**Files:**
- Modify: `tests/test_testing_setup_js.py`
- Modify: `tests/test_testing_shell_integration.py`
- Modify: `tests/test_testing_ui_wired.py`

- [ ] Add failing tests that require popup-scroll-aware Setup navigation hooks in `web/testing-setup.js`.

```python
def test_setup_uses_popup_scroll_navigation_helpers(self):
    self.assertIn("findSetupScrollContainer(", self.js)
    self.assertIn("scrollSetupSectionIntoView(", self.js)
    self.assertIn("data-scroll-target", self.js)

def test_setup_uses_scroll_container_aware_observer(self):
    self.assertIn("root: scrollContainer", self.js)
    self.assertIn("rootMargin:", self.js)
```

- [ ] Add failing tests that require the new Setup structural markers for contextual toolbars, grouped sections, and finish zone.

```python
def test_setup_contains_contextual_profile_toolbar_marker(self):
    self.assertIn("testing-setup-profile-toolbar", self.js)

def test_setup_contains_finish_zone_marker(self):
    self.assertIn("testing-setup-finish-zone", self.js)

def test_setup_contains_field_grid_marker(self):
    self.assertIn("testing-setup-field-grid", self.js)
```

- [ ] Run the focused Setup tests and confirm they fail before implementation.

```powershell
python run_tests.py tests.test_testing_setup_js tests.test_testing_shell_integration tests.test_testing_ui_wired
```

Expected: new assertions fail because the new hooks do not exist yet.

### Task 2: Add failing tests for the Results hierarchy rebuild

**Files:**
- Modify: `tests/test_testing_results_js.py`
- Modify: `tests/test_testing_shell_integration.py`
- Modify: `tests/test_testing_ui_wired.py`

- [ ] Add failing tests that require grouped command-bar and summary-zone hooks in `web/testing-results.js`.

```python
def test_results_contains_command_bar_groups(self):
    self.assertIn('data-section="command-bar"', self.js)
    self.assertIn("testing-results-command-main", self.js)
    self.assertIn("testing-results-command-danger", self.js)

def test_results_contains_summary_zone(self):
    self.assertIn('data-section="summary"', self.js)
    self.assertIn("testing-results-summary-card", self.js)
```

- [ ] Add failing tests that require new gallery and comparison workspace hooks.

```python
def test_results_contains_gallery_and_workspace_hooks(self):
    self.assertIn("testing-results-gallery", self.js)
    self.assertIn("testing-results-compare-workspace", self.js)
    self.assertIn("testing-results-empty-state", self.js)
```

- [ ] Run the focused Results tests and confirm they fail before implementation.

```powershell
python run_tests.py tests.test_testing_results_js tests.test_testing_shell_integration tests.test_testing_ui_wired
```

Expected: new assertions fail because the new Results structure is not implemented yet.

### Task 3: Expand shared styles for breathing room and clearer hierarchy

**Files:**
- Modify: `web/testing-styles.js`
- Test: `tests/test_testing_shell_integration.py`

- [ ] Add failing tests for the new shared style hooks before changing CSS.

```python
def test_styles_include_setup_results_clarity_utilities(self):
    self.assertIn(".testing-setup-field-grid", self.css)
    self.assertIn(".testing-setup-finish-zone", self.css)
    self.assertIn(".testing-results-command-main", self.css)
    self.assertIn(".testing-results-summary-card", self.css)
    self.assertIn(".testing-results-gallery", self.css)
```

- [ ] Implement minimal CSS additions for calmer page spacing, grouped toolbars, field grids, finish zone, command groups, summary cards, checkpoint cards, gallery rhythm, and comparison workspace.

```js
.testing-setup-field-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: var(--space-md);
}

.testing-setup-finish-zone {
  display: flex;
  flex-direction: column;
  gap: var(--space-md);
  padding: var(--space-lg);
  background: var(--color-bg-raised);
  border: 1px solid var(--color-border-strong);
  border-radius: var(--radius-lg);
}

.testing-results-command-main,
.testing-results-command-danger {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-sm);
}
```

- [ ] Run the focused style-related tests and confirm they pass.

```powershell
python run_tests.py tests.test_testing_shell_integration
```

Expected: style hook assertions pass.

### Task 4: Rebuild Setup structure and fix step-rail navigation

**Files:**
- Modify: `web/testing-setup.js`
- Test: `tests/test_testing_setup_js.py`
- Test: `tests/test_testing_ui_wired.py`

- [ ] Implement the popup-scroll-aware rail navigation helpers.

```js
function findSetupScrollContainer(rootEl) {
  return rootEl.closest(".comfymodal-testing-body") || rootEl.parentElement || rootEl;
}

function scrollSetupSectionIntoView(scrollContainer, section) {
  const containerRect = scrollContainer.getBoundingClientRect();
  const sectionRect = section.getBoundingClientRect();
  const offset = sectionRect.top - containerRect.top + scrollContainer.scrollTop - 12;
  scrollContainer.scrollTo({ top: Math.max(0, offset), behavior: "smooth" });
}
```

- [ ] Wire the rail to use the correct container and add a dedicated scroll target marker.

```js
const item = el("button", {
  class: classes.join(" "),
  "data-step-key": key,
  "data-scroll-target": `testing-setup-section-${key}`,
  type: "button",
});
```

- [ ] Refactor Setup so workflow/profile actions are contextual and no longer feel duplicated.

```js
return sectionCard(SECTION_LABELS.workflows, [
  el("div", { class: "testing-setup-profile-toolbar comfymodal-utility-toolbar" }, toolbarChildren),
  list,
], "workflows");
```

- [ ] Rework Axes, Execution, and Review & Run into calmer grouped layouts with field-grid and finish-zone hooks.

```js
return sectionCard(SECTION_LABELS.axes, [
  el("div", { class: "testing-setup-field-grid" }, fieldNodes),
], "axes");

return sectionCard(SECTION_LABELS.preview, [
  el("div", { class: "testing-setup-finish-zone" }, [summaryEl, compileBtn]),
], "preview");
```

- [ ] Update the active-step observer to use the popup scroll container as the root.

```js
const scrollContainer = findSetupScrollContainer(rootEl);
observer = new IntersectionObserver(onEntries, {
  root: scrollContainer,
  rootMargin: "-12% 0px -55% 0px",
  threshold: [0.2, 0.45, 0.7],
});
```

- [ ] Run the focused Setup tests and confirm they pass.

```powershell
python run_tests.py tests.test_testing_setup_js tests.test_testing_ui_wired tests.test_testing_shell_integration
```

Expected: Setup navigation and structure tests pass.

### Task 5: Rebuild Results into clearer operational zones

**Files:**
- Modify: `web/testing-results.js`
- Test: `tests/test_testing_results_js.py`
- Test: `tests/test_testing_ui_wired.py`

- [ ] Refactor the top of Results into grouped command-bar zones.

```js
function commandBarSection(apiBase, experimentId) {
  return el("section", { class: "testing-results-command-bar", "data-section": "command-bar" }, [
    el("div", { class: "testing-results-command-main" }, [experimentPicker(apiBase, experimentId), reloadButton()]),
    el("div", { class: "testing-results-command-main" }, routineControls(apiBase, experimentId)),
    el("div", { class: "testing-results-command-danger" }, dangerControls(apiBase, experimentId)),
  ]);
}
```

- [ ] Add a dedicated run summary zone separate from checkpoint activity.

```js
function summarySection() {
  return el("section", { class: "testing-results-summary", "data-section": "summary" }, [
    el("div", { class: "testing-results-summary-card", "data-testid": "summary-card" }),
  ]);
}
```

- [ ] Rework the grid and comparison areas into explicit gallery/workspace structure with calmer empty states.

```js
function gridSection() {
  return el("section", { class: "testing-results-gallery", "data-section": "grid" }, [
    el("div", { class: "testing-results-grid-body", "data-testid": "grid-body" }),
  ]);
}

function comparisonSlotSection(apiBase) {
  return el("section", { class: "testing-results-compare-workspace", "data-section": "compare" }, [
    el("div", { class: "testing-results-compare-body", "data-testid": "compare-body" }),
  ]);
}
```

- [ ] Keep existing control semantics, polling, comparison behavior, and result-card data while improving structure only.

```js
const shell = el("div", { class: "testing-results-root" });
shell.appendChild(commandBarSection(apiBase, experimentId));
shell.appendChild(summarySection());
shell.appendChild(progressSection());
shell.appendChild(gridSection());
shell.appendChild(comparisonSlotSection(apiBase));
```

- [ ] Run the focused Results tests and confirm they pass.

```powershell
python run_tests.py tests.test_testing_results_js tests.test_testing_ui_wired tests.test_testing_shell_integration
```

Expected: Results structure tests pass.

### Task 6: Full verification and live browser check

**Files:**
- Verify: `web/testing-setup.js`
- Verify: `web/testing-results.js`
- Verify: `web/testing-styles.js`

- [ ] Run the full focused suite covering Setup, Results, wiring, and shell integration.

```powershell
python run_tests.py tests.test_testing_shell_integration tests.test_testing_ui_wired tests.test_testing_results_js tests.test_testing_setup_js
```

Expected: all targeted tests pass.

- [ ] Run syntax checks on changed frontend files.

```powershell
node --check "web/testing-styles.js"
node --check "web/testing-setup.js"
node --check "web/testing-results.js"
```

Expected: no syntax errors.

- [ ] Verify the live popup manually or with Playwright against `http://127.0.0.1:8188/`.

```text
1. Open Modal GPU sidebar tab
2. Click Open Testing Suite
3. Open Setup and click steps 1, 4, 8
4. Confirm the popup body scrolls to the correct sections and current-step styling follows scroll
5. Open Results and confirm command groups, summary zone, checkpoint area, gallery, and comparison workspace feel visually distinct
```

- [ ] Report refresh instructions, what changed visually, and any remaining limitations.
