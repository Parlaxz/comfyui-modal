# Modal Studio Shell Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the old testing-suite shell with a real Modal Studio shell that defaults to Playground, exposes real History and Settings pages, and preserves all old testing modules under Settings > Legacy without rewriting backend experiment/history infrastructure.

**Architecture:** Keep `web/modal-testing.js` as the single ComfyUI entrypoint responsible only for lifecycle, launchers, diagnostics, and shell mounting. Move Studio state and page routing into new `web/studio-*.js` modules, and preserve legacy `web/testing-*.js` modules behind a `studio-legacy.js` wrapper that handles their existing option contracts and cleanup hooks.

**Tech Stack:** ComfyUI frontend extensions, plain JavaScript DOM modules, existing `/comfymodal/*` backend routes, Python unittest structural tests.

---

### Task 1: Add failing structural tests for the Studio shell contract

**Files:**
- Modify: `tests/test_testing_shell_integration.py`
- Modify: `tests/test_testing_ui_wired.py`

- [ ] **Step 1: Write failing tests for the new top nav and Studio module surface**

```python
class StudioShellContractTests(unittest.TestCase):
    def test_main_nav_uses_playground_history_settings_only(self):
        text = (WEB / "modal-testing.js").read_text(encoding="utf-8")
        self.assertIn('Playground', text)
        self.assertIn('History', text)
        self.assertIn('Settings', text)

    def test_old_primary_tabs_not_in_main_nav(self):
        text = (WEB / "modal-testing.js").read_text(encoding="utf-8")
        self.assertNotIn('text: "Dashboard"', text)
        self.assertNotIn('text: "Setup"', text)
        self.assertNotIn('text: "Profiles"', text)
        self.assertNotIn('text: "Results"', text)

    def test_studio_modules_exist(self):
        for name in [
            "studio-shell.js",
            "studio-playground.js",
            "studio-history.js",
            "studio-settings.js",
            "studio-feature-registry.js",
            "studio-experiment-mode.js",
            "studio-legacy.js",
            "studio-styles.js",
        ]:
            self.assertTrue((WEB / name).exists(), f"missing {name}")
```

- [ ] **Step 2: Run the shell/UI structural tests to verify they fail**

Run: `python -m pytest tests/test_testing_shell_integration.py tests/test_testing_ui_wired.py -q`
Expected: FAIL because the new Studio shell modules and nav contract do not exist yet.

- [ ] **Step 3: Extend tests for Legacy reachability and truthful placeholders**

```python
class StudioLegacyContractTests(unittest.TestCase):
    def test_settings_legacy_mentions_all_old_tabs(self):
        text = (WEB / "studio-settings.js").read_text(encoding="utf-8")
        for needle in [
            "Legacy Dashboard",
            "Legacy Setup",
            "Legacy Profiles",
            "Legacy Results",
            "Legacy History",
            "Legacy Settings",
        ]:
            self.assertIn(needle, text)

    def test_playground_uses_honest_future_placeholder_copy(self):
        text = (WEB / "studio-playground.js").read_text(encoding="utf-8")
        self.assertTrue(
            "future work" in text.lower() or "not implemented yet" in text.lower()
        )
```

- [ ] **Step 4: Re-run the targeted structural tests and verify they still fail for the expected missing Studio implementation**

Run: `python -m pytest tests/test_testing_shell_integration.py tests/test_testing_ui_wired.py -q`
Expected: FAIL with missing Studio files/strings, proving the tests are exercising the new contract.

### Task 2: Build the Studio shell, styles, registry, and page modules

**Files:**
- Modify: `web/modal-testing.js`
- Create: `web/studio-shell.js`
- Create: `web/studio-playground.js`
- Create: `web/studio-history.js`
- Create: `web/studio-settings.js`
- Create: `web/studio-feature-registry.js`
- Create: `web/studio-experiment-mode.js`
- Create: `web/studio-styles.js`
- Create: `web/studio-api.js` (only if needed)

- [ ] **Step 1: Implement the minimal shell API in `web/studio-shell.js`**

```javascript
export function mountStudioShell(rootEl, context = {}) {
  const state = {
    activePage: "playground",
    playground: {
      featureId: "txt2img",
      experimentMode: false,
      selectedBackendId: "",
      compareBackendIds: [],
      controls: {},
      experimentAxes: {},
    },
    history: {
      selectedRunId: "",
      filters: { query: "", kind: "all", status: "all" },
    },
    settings: {
      activeSection: "studio",
      activeLegacyTab: "",
    },
  };

  return {
    destroy() {},
    setPage(nextPage) { state.activePage = nextPage; },
  };
}
```

- [ ] **Step 2: Refactor `web/modal-testing.js` to mount the Studio shell instead of the old six-tab nav**

```javascript
import { ensureStudioStyles } from "./studio-styles.js";
import { mountStudioShell } from "./studio-shell.js";

function buildShell() {
  const overlay = el("div", { class: "comfymodal-testing-overlay" });
  const modal = el("div", { class: "comfymodal-studio-modal" });
  const header = el("div", { class: "comfymodal-studio-header" }, [
    el("h2", { text: "Modal Studio" }),
    el("button", { class: "comfymodal-testing-close", text: "✕" }),
  ]);
  const body = el("div", { class: "comfymodal-studio-body", "data-testid": "body" });
  modal.appendChild(header);
  modal.appendChild(body);
  overlay.appendChild(modal);
  return { overlay, modal, header, body };
}

export function open_testing_modal() {
  ensureHost();
  ensureTestingStyles();
  ensureStudioStyles();
  // mountStudioShell(shell.body, stableContext)
}
```

- [ ] **Step 3: Implement the feature registry and the real Playground layout**

```javascript
export const FEATURE_SPECS = [
  {
    id: "txt2img",
    label: "Txt2Img",
    supportsImageCanvas: false,
    controls: ["prompt", "steps", "guidance", "denoise", "seed", "lora", "lora_strength"],
  },
  {
    id: "object_remove",
    label: "Object Remove",
    supportsImageCanvas: true,
    futureTools: ["SAM click selection", "Text object selection", "Brush refine"],
  },
  {
    id: "object_replace",
    label: "Object Replace",
    supportsImageCanvas: true,
    futureTools: ["SAM click selection", "Text object selection", "Reference image"],
  },
];
```

- [ ] **Step 4: Implement experiment mode as an overlay on existing controls, not a separate page**

```javascript
export function renderExperimentToggle(state, actions) {
  return {
    label: state.playground.experimentMode ? "Exit Experiment" : "Experiment",
    onClick() {
      actions.setExperimentMode(!state.playground.experimentMode);
    },
  };
}
```

- [ ] **Step 5: Run the targeted structural tests and verify they now pass**

Run: `python -m pytest tests/test_testing_shell_integration.py tests/test_testing_ui_wired.py -q`
Expected: PASS for the new Studio shell/module contract tests.

### Task 3: Add Studio history/settings wiring and the Legacy wrapper with cleanup

**Files:**
- Create: `web/studio-legacy.js`
- Modify: `web/studio-history.js`
- Modify: `web/studio-settings.js`
- Modify: `web/modal-testing.js`
- Modify: `__init__.py` (only if thin Studio adapters are needed)

- [ ] **Step 1: Write failing tests for Legacy loading and cleanup-sensitive wiring**

```python
class StudioLegacyWiringTests(unittest.TestCase):
    def test_legacy_wrapper_references_old_tab_modules(self):
        text = (WEB / "studio-legacy.js").read_text(encoding="utf-8")
        for needle in [
            "testing-dashboard.js",
            "testing-setup.js",
            "testing-profiles.js",
            "testing-results.js",
            "testing-history.js",
            "testing-settings.js",
        ]:
            self.assertIn(needle, text)

    def test_legacy_wrapper_stops_previous_controller(self):
        text = (WEB / "studio-legacy.js").read_text(encoding="utf-8")
        self.assertTrue("stop(" in text or "destroy(" in text)
```

- [ ] **Step 2: Run the targeted tests to verify they fail before the Legacy wrapper is implemented**

Run: `python -m pytest tests/test_testing_shell_integration.py tests/test_testing_ui_wired.py -q`
Expected: FAIL because `studio-legacy.js` cleanup and module references are not implemented yet.

- [ ] **Step 3: Implement `web/studio-legacy.js` with explicit controller cleanup and old-module option contracts**

```javascript
let currentLegacyController = null;

function stopLegacyController() {
  if (!currentLegacyController) return;
  if (typeof currentLegacyController.stop === "function") currentLegacyController.stop();
  if (typeof currentLegacyController.destroy === "function") currentLegacyController.destroy();
  currentLegacyController = null;
}

export async function mountLegacyTab(rootEl, legacyTab, context) {
  stopLegacyController();
  // resolve old module, build options with apiBase/draft/preview/experimentId/onDraftChange/onRun,
  // mount old render fn, store returned controller if any
}
```

- [ ] **Step 4: Implement real History and Settings wiring using existing data or thin truthful adapters**

```javascript
export async function loadStudioHistory(apiBase) {
  const res = await fetch(`${apiBase}/run-history?limit=50`);
  if (!res.ok) throw new Error(`History request failed: ${res.status}`);
  return await res.json();
}
```

- [ ] **Step 5: If existing endpoints are insufficient, add only thin backend adapters and route tests**

```python
def test_routes_include_optional_studio_endpoints(self):
    text = (REPO_ROOT / "__init__.py").read_text(encoding="utf-8")
    self.assertIn("/comfymodal/studio/", text)
```

- [ ] **Step 6: Run the structural tests again and verify they pass**

Run: `python -m pytest tests/test_testing_shell_integration.py tests/test_testing_ui_wired.py tests/test_routes_registered.py -q`
Expected: PASS for updated shell/UI/route structure.

### Task 4: Verify the full redesign against preserved backend/frontend contracts

**Files:**
- Modify: `tests/test_routes_registered.py` (if new routes are added)
- Verify: `tests/test_run_history.py`
- Verify: `tests/test_experiment_store.py`
- Verify: `tests/test_matrix_compiler.py`

- [ ] **Step 1: Run the focused frontend structural suite**

Run: `python -m pytest tests/test_testing_shell_integration.py tests/test_testing_ui_wired.py tests/test_routes_registered.py -q`
Expected: PASS.

- [ ] **Step 2: Run preserved backend history/experiment regression tests**

Run: `python -m pytest tests/test_run_history.py tests/test_experiment_store.py tests/test_matrix_compiler.py -q`
Expected: PASS, confirming the redesign did not break preserved backend infrastructure.

- [ ] **Step 3: If failures appear, apply the smallest fix and re-run the exact failing command until green**

```text
Adjust only the failing shell, wrapper, or thin-adapter code.
Do not rewrite old testing modules or backend experiment infrastructure.
```

- [ ] **Step 4: Report exact verification evidence before claiming completion**

```text
List the commands run, whether they passed, and any remaining disabled-but-honest behavior such as Run / Run Experiment or image-edit placeholders.
```
