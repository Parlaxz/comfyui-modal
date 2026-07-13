# Studio QA Defect Repairs Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Repair the Playwright-discovered Studio preset, Playground, execution, progress, experiment, History, annotation, and restoration defects without breaking existing persisted data.

**Architecture:** Preserve the backend as the source of truth. Normalize the preset/snapshot contract and all scalar controls before the browser renders or execution mutates a workflow. Keep browser state as an origin-scoped cache only, synchronize mutations through shared run records, and test every repaired contract at Python and browser layers.

**Tech Stack:** Python, aiohttp ComfyUI routes, vanilla ES modules, localStorage, pytest, Node.js, Playwright.

---

### Task 1: Establish normalized preset controls before rendering

**Files:**
- Modify: `studio_run_adapter.py`
- Modify: `web/studio-feature-registry.js`
- Modify: `web/studio-playground.js`
- Modify: `web/studio-playground-state.js`
- Test: `tests/test_studio_backend.py`
- Test: `tests/browser/studio-playground.spec.mjs`

- [ ] **Step 1: Write failing backend and browser tests**

Add a Python test that loads a preset referencing a snapshot and asserts its returned defaults are scalar values, including `steps`, `scheduler`, `width`, and `height`:

```python
result = load_preset_and_snapshot("preset_test", stores)
assert result["defaults"]["steps"] == 8
assert result["defaults"]["scheduler"] == "bong_tangent"
assert result["defaults"]["width"] == 1920
assert result["defaults"]["height"] == 1088
```

Add a browser test that selects the fixture preset before first control render and asserts the corresponding number inputs/selects contain those values.

- [ ] **Step 2: Run the focused tests to verify RED**

Run:

```powershell
pytest tests/test_studio_backend.py -q
npm run test:playwright -- --grep "preset defaults"
```

Expected: the new default/control assertions fail.

- [ ] **Step 3: Implement minimal normalized preset defaults**

Update `load_preset_and_snapshot()` and its response builders to merge explicit preset defaults with snapshot-derived defaults only when the explicit key is absent. Preserve scalar widget values rather than node-reference tuples.

In `web/studio-feature-registry.js`, register `width` and `height` as integer controls with graph-provided bounds and steps. Retain dynamic schema option lists for sampler and scheduler; do not fall back to unrelated generic enum defaults.

In Playground hydration, resolve the active preset object before calling `hydrateControlsForSelection()`. Hydration precedence must be:

```javascript
persistedDraft > latestSuccessfulControlsForSamePresetAndFeature > preset.defaults > controlDefinition.defaultValue
```

Use property-existence checks rather than truthiness so `0` and `false` survive.

- [ ] **Step 4: Run focused tests to verify GREEN**

Run:

```powershell
pytest tests/test_studio_backend.py -q
npm run test:playwright -- --grep "preset defaults"
```

Expected: PASS.

### Task 2: Validate controls and required bindings before queueing

**Files:**
- Modify: `studio_models.py`
- Modify: `studio_run_adapter.py`
- Modify: `experiment_runner.py`
- Test: `tests/test_studio_runtime.py`
- Test: `tests/test_experiment_runner.py`
- Test: `tests/browser/studio-playground.spec.mjs`

- [ ] **Step 1: Write failing validation tests**

Add tests for all of the following:

```python
with pytest.raises(ValueError, match="prompt.*required"):
    validate_controls_against_schema({"prompt": ""}, schemas, required={"prompt"})

with pytest.raises(ValueError, match="steps.*integer"):
    validate_controls_against_schema({"steps": [8]}, schemas)

assert validate_controls_against_schema({"seed": 0, "guidance": 0, "denoise": 0}, schemas) == {
    "seed": 0, "guidance": 0, "denoise": 0,
}
```

Add a Playwright assertion that empty prompt submission remains on `RUN`, shows a prompt-specific error, and sends no Studio-run POST.

- [ ] **Step 2: Run focused tests to verify RED**

Run:

```powershell
pytest tests/test_studio_runtime.py tests/test_experiment_runner.py -q
npm run test:playwright -- --grep "required prompt|invalid scalar"
```

Expected: missing required-value and list-valued scalar tests fail.

- [ ] **Step 3: Implement schema-driven coercion and validation**

Require nonblank values for required string bindings after trimming. For scalar integer, number, boolean, and enum schemas, reject arrays and objects with a field-specific validation error. Coerce only valid scalar strings/numbers according to the target schema before `_apply_controls_to_workflow()` and before `resolve_and_inject_cell()` calls `int()`.

Keep LoRA combination lists isolated to their dedicated LoRA controls; never map them to scalar canonical controls such as `steps` or `seed`.

- [ ] **Step 4: Run focused tests to verify GREEN**

Run:

```powershell
pytest tests/test_studio_runtime.py tests/test_experiment_runner.py -q
npm run test:playwright -- --grep "required prompt|invalid scalar"
```

Expected: PASS.

### Task 3: Produce run-scoped live progress and truthful timing metadata

**Files:**
- Modify: `studio_run_adapter.py`
- Modify: `experiment_runner.py`
- Modify: `timing_trace.py`
- Modify: `web/studio-playground.js`
- Modify: `web/studio-run-normalizer.js`
- Test: `tests/test_studio_progress_tracker.py`
- Test: `tests/test_studio_timing_integration.py`
- Test: `tests/browser/studio-playground.spec.mjs`

- [ ] **Step 1: Write failing progress and timing tests**

Add tests asserting a Studio event contains its run/experiment identity and independently populated queue, workflow, sampler, and elapsed fields:

```python
assert event["run_id"] == "r_test"
assert event["experiment_id"] == "exp_test"
assert event["workflow_progress"] == {"current": 2, "total": 8}
assert event["sampler_progress"] == {"current": 4, "total": 20}
```

Add timing assertions that scheduler wall-clock is labelled `scheduler_execution_ms`, unavailable stages remain absent, and no derived `sampling_ms` is emitted without a genuine source.

- [ ] **Step 2: Run focused tests to verify RED**

Run:

```powershell
pytest tests/test_studio_progress_tracker.py tests/test_studio_timing_integration.py -q
npm run test:playwright -- --grep "scoped progress|timing metadata"
```

Expected: the new identity/progress and timing-label assertions fail.

- [ ] **Step 3: Implement scoped progress normalization**

Emit only events whose `run_id` or `experiment_id` matches the active Studio submission. Maintain queue/startup progress separately from workflow-node and sampler progress. Update elapsed time from the submission monotonic start time. Normalize and render timing keys with explicit source and quality fields; omit unavailable stage values.

- [ ] **Step 4: Run focused tests to verify GREEN**

Run:

```powershell
pytest tests/test_studio_progress_tracker.py tests/test_studio_timing_integration.py -q
npm run test:playwright -- --grep "scoped progress|timing metadata"
```

Expected: PASS.

### Task 4: Repair experiment compatibility and axis feedback

**Files:**
- Modify: `web/studio-preset-capabilities.js`
- Modify: `web/studio-experiment-mode.js`
- Modify: `web/studio-playground.js`
- Test: `tests/test_studio_backend.py`
- Test: `tests/browser/studio-playground.spec.mjs`

- [ ] **Step 1: Write failing experiment eligibility tests**

Create two normalized fixture presets with bound `steps` and `seed`. Assert selecting both enables those axes and produces the exact expected matrix count:

```javascript
await selectComparePresets(["preset-a", "preset-b"]);
await expect(axis("steps")).toBeEnabled();
await expect(matrixSummary()).toContain("Estimated runs: 4");
```

Also assert an unavailable control is disabled with a reason naming the preset or missing binding.

- [ ] **Step 2: Run focused tests to verify RED**

Run:

```powershell
pytest tests/test_studio_backend.py -q
npm run test:playwright -- --grep "experiment axis"
```

Expected: supported axes remain incorrectly disabled.

- [ ] **Step 3: Implement capability-based eligibility**

Evaluate selected runnable presets after their snapshot contracts are normalized. An axis is eligible only when every selected preset supports the exact control binding and schema. Recalculate immediately after selection changes and render the concrete ineligibility explanation beside disabled controls.

- [ ] **Step 4: Run focused tests to verify GREEN**

Run:

```powershell
pytest tests/test_studio_backend.py -q
npm run test:playwright -- --grep "experiment axis"
```

Expected: PASS.

### Task 5: Correct History filtering, pagination, and shared annotations

**Files:**
- Modify: `experiment_service.py`
- Modify: `__init__.py`
- Modify: `web/studio-history.js`
- Modify: `web/studio-playground.js`
- Test: `tests/test_studio_backend.py`
- Test: `tests/browser/studio-playground.spec.mjs`

- [ ] **Step 1: Write failing History contract tests**

Add backend tests that create records with `kind`, prompt, note, preset ID, feature ID, image path, and timestamps. Assert filters and pagination exactly match:

```python
page = history.list_runs(kind="run", search="needle", date_from="2026-07-12", date_to="2026-07-12", limit=50, offset=0)
assert page["total"] == 1
assert page["runs"][0]["run_id"] == "r_needle"
```

Add browser tests ensuring the next button is disabled at the last valid offset; History annotation success updates the active Playground record; a failed PATCH retains persisted note/favorite values and displays `Save failed`.

- [ ] **Step 2: Run focused tests to verify RED**

Run:

```powershell
pytest tests/test_studio_backend.py -q
npm run test:playwright -- --grep "history filter|history pagination|annotation"
```

Expected: type/search/date/pagination or cross-view annotation assertions fail.

- [ ] **Step 3: Implement exact query and annotation semantics**

Keep the route and service filter keys aligned. Interpret `date_to` as the next date's exclusive boundary or as `T23:59:59.999999` before filtering. Render `data.total` exactly; disable Prev at `offset === 0` and Next when `offset + runs.length >= total`. Debounce all free-text fields.

On successful annotation PATCH, update the canonical in-memory run record used by both History and Playground. On failure, retain the editor draft, preserve last persisted annotation state, and display a failure message.

- [ ] **Step 4: Run focused tests to verify GREEN**

Run:

```powershell
pytest tests/test_studio_backend.py -q
npm run test:playwright -- --grep "history filter|history pagination|annotation"
```

Expected: PASS.

### Task 6: Make reload and deleted-preset restoration deterministic

**Files:**
- Modify: `web/studio-playground-state.js`
- Modify: `web/studio-playground.js`
- Test: `tests/browser/studio-playground.spec.mjs`

- [ ] **Step 1: Write failing browser restoration tests**

Use a single browser origin. Select a preset, enter zero-like controls, complete a fixture run, reload, and assert all persisted state returns:

```javascript
await page.reload();
await expect(selectedPreset()).toHaveText("Fixture preset");
await expect(control("seed")).toHaveValue("0");
await expect(resultImage()).toHaveAttribute("src", /fixture-output/);
await expect(metadata()).toContain("Run ID:");
```

Delete that selected preset through the Backend fixture and assert the selector moves to a remaining runnable preset or the empty state.

- [ ] **Step 2: Run focused test to verify RED**

Run:

```powershell
npm run test:playwright -- --grep "reload restoration|deleted preset"
```

Expected: selected preset or result metadata is missing after reload.

- [ ] **Step 3: Implement origin-scoped state restoration**

Persist only serializable selection, per-preset/per-feature controls, and selected successful run identity. During hydration, load the server preset list first, validate the saved selection, then resolve and restore the referenced run. Do not clear a valid last successful result merely because a selected preset was removed; clear only unavailable selections and preserve an explicit empty-state reason.

- [ ] **Step 4: Run focused test to verify GREEN**

Run:

```powershell
npm run test:playwright -- --grep "reload restoration|deleted preset"
```

Expected: PASS.

### Task 7: Re-run the full regression and live Playwright checklist

**Files:**
- Verify only

- [ ] **Step 1: Run all targeted Python regressions**

Run:

```powershell
pytest tests/test_studio_backend.py tests/test_studio_runtime.py tests/test_studio_progress_tracker.py tests/test_studio_timing_integration.py tests/test_experiment_runner.py -q
```

Expected: PASS.

- [ ] **Step 2: Run deterministic and mocked browser regressions**

Run:

```powershell
npm run test:deterministic
npm run test:playwright
```

Expected: PASS.

- [ ] **Step 3: Run live Playwright validation**

Run:

```powershell
npm run test:playwright:live
```

Expected: PASS for preset defaults, required-field rejection, zero values, progress isolation, metadata/timings, experiments, History, annotations, reload restoration, and deleted-preset fallback.

- [ ] **Step 4: Recheck repository hygiene**

Run:

```powershell
git status --short
```

Expected: no generated Studio image, run-history, experiment-state, or local-settings artifact is tracked or untracked. Preserve pre-existing source changes and do not commit unless explicitly requested.
