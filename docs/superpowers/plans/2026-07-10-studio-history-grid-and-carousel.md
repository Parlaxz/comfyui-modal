# Studio History Grid and Carousel Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Convert Studio History into an image grid with preview overlay and convert the Playground strip into an image carousel that updates the main canvas.

**Architecture:** Add a shared frontend run normalizer so History and Playground derive image URLs and metadata the same way. Keep `web/studio-history.js` and `web/studio-playground.js` as page owners, extend shell state just enough for History preview and carousel selection, and add additive styles in `web/studio-styles.js` for the grid, overlay, and carousel.

**Tech Stack:** Plain JavaScript DOM modules, existing `/comfymodal/run-history` and asset/output routes, Studio shell state in `web/studio-shell.js`, Python unittest structural tests.

---

### Task 1: Lock the new UI contract with focused structural tests

**Files:**
- Create: `tests/test_studio_history_grid_js.py`
- Modify: `tests/test_studio_backend.py`

- [ ] **Step 1: Write failing tests for the new shared normalizer and History grid contract**

```python
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
WEB = REPO_ROOT / "web"


class StudioHistoryGridJsTests(unittest.TestCase):
    def test_normalizer_module_exists(self):
        self.assertTrue((WEB / "studio-run-normalizer.js").exists())

    def test_history_imports_normalizer(self):
        text = (WEB / "studio-history.js").read_text(encoding="utf-8")
        self.assertIn('from "./studio-run-normalizer.js"', text)

    def test_history_uses_grid_and_overlay_markers(self):
        text = (WEB / "studio-history.js").read_text(encoding="utf-8")
        for needle in (
            "comfymodal-studio-history-grid",
            "comfymodal-studio-history-card",
            "comfymodal-studio-history-overlay",
            "comfymodal-studio-history-preview-image",
        ):
            self.assertIn(needle, text)

    def test_history_uses_placeholder_copy(self):
        text = (WEB / "studio-history.js").read_text(encoding="utf-8")
        self.assertIn("No preview", text)
```

- [ ] **Step 2: Extend existing Studio tests for shell state and carousel behavior**

```python
class StudioShellCarouselContractTests(unittest.TestCase):
    def test_shell_history_state_has_preview_run(self):
        text = (WEB / "studio-shell.js").read_text(encoding="utf-8")
        self.assertIn("previewRun", text)

    def test_shell_playground_state_has_carousel_state(self):
        text = (WEB / "studio-shell.js").read_text(encoding="utf-8")
        self.assertIn("carouselRuns", text)
        self.assertIn("carouselIndex", text)

    def test_playground_imports_normalizer(self):
        text = (WEB / "studio-playground.js").read_text(encoding="utf-8")
        self.assertIn('from "./studio-run-normalizer.js"', text)

    def test_filmstrip_click_no_longer_navigates_to_history(self):
        text = (WEB / "studio-playground.js").read_text(encoding="utf-8")
        self.assertNotIn('context.setPage("history")', text)
        self.assertIn("selectCarouselRun", text)

    def test_playground_contains_carousel_markers(self):
        text = (WEB / "studio-playground.js").read_text(encoding="utf-8")
        for needle in (
            "comfymodal-studio-carousel",
            "comfymodal-studio-carousel-track",
            "comfymodal-studio-carousel-item",
            "comfymodal-studio-carousel-arrow",
        ):
            self.assertIn(needle, text)
```

- [ ] **Step 3: Run the targeted structural tests and verify they fail before implementation**

Run: `python -m pytest tests/test_studio_history_grid_js.py tests/test_studio_backend.py -q`
Expected: FAIL because the normalizer module, overlay markers, and carousel state do not exist yet.

### Task 2: Add a shared Studio run normalizer and shell state for preview/carousel selection

**Files:**
- Create: `web/studio-run-normalizer.js`
- Modify: `web/studio-shell.js`
- Test: `tests/test_studio_history_grid_js.py`
- Test: `tests/test_studio_backend.py`

- [ ] **Step 1: Implement the shared run normalizer module**

```javascript
function firstOutputPath(run, extra) {
  if (Array.isArray(run && run.outputs) && run.outputs.length > 0) {
    const first = run.outputs[0];
    if (typeof first === "string") return first;
    if (first && typeof first.path === "string") return first.path;
    if (first && typeof first.output_path === "string") return first.output_path;
  }
  if (typeof (run && run.output_path) === "string") return run.output_path;
  if (Array.isArray(extra && extra.output_paths) && extra.output_paths.length > 0) {
    return extra.output_paths[0];
  }
  return "";
}

export function resolveStudioRunImageUrl(run, apiBase = "/comfymodal") {
  const extra = (run && run.extra) || {};
  if (extra.primary_asset_id) {
    return `${apiBase}/assets/${encodeURIComponent(extra.primary_asset_id)}`;
  }
  if (run && run.asset_id) {
    return `${apiBase}/assets/${encodeURIComponent(run.asset_id)}`;
  }
  const outputPath = firstOutputPath(run, extra);
  if (outputPath) {
    return `${apiBase}/studio/outputs/${encodeURIComponent(outputPath)}`;
  }
  return "";
}

export function normalizeStudioRun(run, apiBase = "/comfymodal") {
  const extra = (run && run.extra) || {};
  const studioMeta = run.studio_meta || extra.studio_meta || extra.studio_metadata || (run.metadata && run.metadata.studio_meta) || {};
  const imageUrl = resolveStudioRunImageUrl(run, apiBase);
  return {
    raw: run,
    id: run.id || run.run_id || run.experiment_id || extra.experiment_id || "unknown",
    experimentId: run.experiment_id || run.experimentId || extra.experiment_id || "",
    status: run.status || run.state || "unknown",
    featureId: studioMeta.studio_feature_id || extra.studio_feature_id || "studio",
    presetLabel: studioMeta.studio_preset_id || extra.studio_preset_id || "",
    promptText: (extra.prompt || run.prompt || (run.params && run.params.prompt) || "Run").substring(0, 120),
    timestamp: run.created_at || run.started_at || run.timestamp || run.created || "",
    duration: run.duration || "",
    imageUrl,
    hasImage: !!imageUrl,
  };
}
```

- [ ] **Step 2: Extend Studio shell state for overlay and carousel selection**

```javascript
const state = {
  activePage: "playground",
  playground: {
    featureId: "txt2img",
    experimentMode: false,
    selectedBackendId: "",
    compareBackendIds: [],
    controls: {},
    experimentAxes: {},
    carouselRuns: [],
    carouselIndex: 0,
  },
  history: {
    selectedRunId: "",
    previewRun: null,
    filters: { query: "", kind: "all", status: "all" },
  },
  settings: {
    activeSection: "studio",
    activeLegacyTab: "",
  },
};
```

- [ ] **Step 3: Re-run the targeted tests to verify the normalizer module and shell state now exist**

Run: `python -m pytest tests/test_studio_history_grid_js.py tests/test_studio_backend.py -q`
Expected: still FAIL, but only on History/Playground UI markers that are not implemented yet.

### Task 3: Rebuild History as an image grid with preview overlay

**Files:**
- Modify: `web/studio-history.js`
- Modify: `web/studio-styles.js`
- Test: `tests/test_studio_history_grid_js.py`

- [ ] **Step 1: Refactor History rendering to normalize runs before grouping**

```javascript
import { normalizeStudioRun } from "./studio-run-normalizer.js";

const runList = Array.isArray(runs) ? runs.map((run) => normalizeStudioRun(run, apiBase)) : [];

runList.forEach((item) => {
  const expId = item.experimentId || "";
  if (expId) {
    if (!grouped[expId]) grouped[expId] = [];
    grouped[expId].push(item);
  } else {
    ungrouped.push(item);
  }
});
```

- [ ] **Step 2: Replace row rendering with image-card grid rendering and overlay hooks**

```javascript
function renderRunCard(parent, item, state, rerender) {
  const card = document.createElement("button");
  card.className = "comfymodal-studio-history-card";
  card.type = "button";
  card.addEventListener("click", function () {
    state.history.previewRun = item;
    rerender();
  });

  const media = document.createElement("div");
  media.className = "comfymodal-studio-history-card-media";
  if (item.hasImage) {
    const img = document.createElement("img");
    img.className = "comfymodal-studio-history-card-image";
    img.src = item.imageUrl;
    img.alt = item.promptText || item.featureId || "History preview";
    media.appendChild(img);
  } else {
    const empty = document.createElement("div");
    empty.className = "comfymodal-studio-history-card-placeholder";
    empty.textContent = "No preview";
    media.appendChild(empty);
  }
  card.appendChild(media);

  const meta = document.createElement("div");
  meta.className = "comfymodal-studio-history-card-meta";
  meta.appendChild(document.createTextNode(item.featureId));
  if (item.presetLabel) meta.appendChild(document.createTextNode(` • ${item.presetLabel}`));
  if (item.timestamp) meta.appendChild(document.createTextNode(` • ${item.timestamp}`));
  card.appendChild(meta);
  parent.appendChild(card);
}
```

- [ ] **Step 3: Add overlay renderer and additive styles for grid, cards, and overlay**

```javascript
function renderPreviewOverlay(state, rerender) {
  const item = state.history.previewRun;
  if (!item) return null;

  const overlay = document.createElement("div");
  overlay.className = "comfymodal-studio-history-overlay";
  overlay.addEventListener("click", function (ev) {
    if (ev.target === overlay) {
      state.history.previewRun = null;
      rerender();
    }
  });
  return overlay;
}
```

```css
.comfymodal-studio-history-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
  gap: 12px;
}

.comfymodal-studio-history-card-media,
.comfymodal-studio-history-card-placeholder,
.comfymodal-studio-history-card-image {
  aspect-ratio: 4 / 3;
}

.comfymodal-studio-history-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.72);
  display: flex;
  align-items: center;
  justify-content: center;
}
```

- [ ] **Step 4: Run the focused History tests and verify the grid/overlay contract passes**

Run: `python -m pytest tests/test_studio_history_grid_js.py -q`
Expected: PASS.

### Task 4: Replace the filmstrip with a carousel that updates the main canvas

**Files:**
- Modify: `web/studio-playground.js`
- Modify: `web/studio-styles.js`
- Modify: `tests/test_studio_backend.py`

- [ ] **Step 1: Add Playground actions for carousel selection and completion auto-selection**

```javascript
selectCarouselRun(run, index) {
  state.playground.carouselRuns = state.playground.carouselRuns || [];
  state.playground.carouselIndex = typeof index === "number" ? index : 0;
  state.playground.lastRunOutput = run && run.imageUrl ? run.imageUrl : "";
},
setCarouselRuns(runs) {
  state.playground.carouselRuns = Array.isArray(runs) ? runs : [];
  if (!state.playground.carouselRuns.length) {
    state.playground.carouselIndex = 0;
    return;
  }
  if (!state.playground.lastRunOutput) {
    state.playground.carouselIndex = 0;
    state.playground.lastRunOutput = state.playground.carouselRuns[0].imageUrl;
  }
},
```

- [ ] **Step 2: Refactor `renderFilmstrip` into a horizontal carousel fed by normalized image runs**

```javascript
import { normalizeStudioRun } from "./studio-run-normalizer.js";

const normalized = entries.map((run) => normalizeStudioRun(run, apiBase));
const imageRuns = normalized.filter((item) => item.hasImage);
actions.setCarouselRuns(imageRuns);

const track = el("div", { class: "comfymodal-studio-carousel-track" });
imageRuns.forEach(function (item, index) {
  const tile = el("button", {
    class: `comfymodal-studio-carousel-item${index === state.playground.carouselIndex ? " active" : ""}`,
    onclick: function () {
      actions.selectCarouselRun(item, index);
      if (context && context.setPage) context.setPage("playground");
    },
  });
  track.appendChild(tile);
});
```

- [ ] **Step 3: Add carousel styles and arrow controls without changing backend contracts**

```css
.comfymodal-studio-carousel {
  display: grid;
  grid-template-columns: auto 1fr auto;
  gap: 8px;
  align-items: center;
}

.comfymodal-studio-carousel-track {
  display: flex;
  gap: 8px;
  overflow-x: auto;
  scroll-snap-type: x mandatory;
}

.comfymodal-studio-carousel-item {
  min-width: 132px;
  scroll-snap-align: start;
}

.comfymodal-studio-carousel-arrow {
  border: 1px solid #2a2a2a;
  background: #111;
}
```

- [ ] **Step 4: Run the targeted Studio tests and verify the carousel contract passes**

Run: `python -m pytest tests/test_studio_history_grid_js.py tests/test_studio_backend.py -q`
Expected: PASS.

### Task 5: Verify the integrated Studio surfaces end-to-end

**Files:**
- Modify: none
- Test: `tests/test_studio_history_grid_js.py`
- Test: `tests/test_studio_backend.py`
- Test: `tests/test_testing_ui_wired.py`

- [ ] **Step 1: Run the broader Studio/UI regression set**

Run: `python -m pytest tests/test_studio_history_grid_js.py tests/test_studio_backend.py tests/test_testing_ui_wired.py -q`
Expected: PASS.

- [ ] **Step 2: Perform manual smoke verification in the Studio modal**

Run:

```text
1. Open Modal Studio.
2. Confirm History shows image cards instead of text rows.
3. Click a History card and confirm the preview overlay opens and closes.
4. Return to Playground and confirm the strip is now a thumbnail carousel.
5. Click a carousel thumbnail and confirm the main canvas image changes.
6. Confirm non-image runs still appear in History as fallback cards.
```

Expected: The visual contract in the approved spec is met without changing backend routes.
