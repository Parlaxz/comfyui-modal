# Modal GPU Experiment Setup Workflow Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the current Setup flow with a five-section experiment builder that edits a normalized user-intent draft, compiles through a backend authoritative adapter into the existing compiler, preserves legacy T2I profiles safely, and presents results by workflow-oriented experimental dimensions.

**Architecture:** Add one backend authoritative setup adapter (`experiment_setup_adapter.py`) and one frontend UI adapter (`web/testing-setup-adapter.js`). The frontend edits and persists only normalized intent; the backend validates, normalizes profiles, translates to the current compiler input shape, and attaches stable normalized dimensions to compiled cells. Results grouping becomes a presentation adapter over unchanged technical checkpoint execution data.

**Tech Stack:** Python backend routes and compiler helpers, plain ES module frontend DOM code, existing ComfyUI modal shell, Python structural/unit tests, Playwright/manual browser verification.

---

### Task 1: Add failing representability and adapter tests first

**Files:**
- Create: `tests/test_experiment_setup_adapter.py`
- Modify: `tests/test_matrix_compiler.py`
- Modify: `tests/test_testing_setup_js.py`
- Modify: `tests/test_testing_results_js.py`
- Modify: `tests/test_testing_profiles_js.py`

- [ ] Add backend failing tests for normalized-draft validation, legacy profile T2I default normalization, no-rewrite-on-load behavior, stale profile revision/hash detection, null controlled-value handling, and normalized dimension attachment.
- [ ] Add compiler representability tests for the ten required stack–LoRA pairing cases: two stacks with no LoRA, one stack with three LoRA configurations, shared LoRAs across stacks, LoRAs on only one stack, different per-stack LoRAs, separate workflow-local stack/LoRA sets, No LoRA + explicit LoRA, Workflow Default + explicit LoRA, LoRA strength sweeps, and per-workflow controlled LoRA.
- [ ] Add/update frontend structural tests for five Setup sections, tri-state labels, no nine-section labels, no global model-axis wording, workflow-oriented Results grouping hooks, and mode-aware profile labels.
- [ ] Run focused tests and confirm they fail for expected missing adapter/UI reasons.

### Task 2: Implement backend authoritative setup adapter and schema validation

**Files:**
- Create: `experiment_setup_adapter.py`
- Modify: `__init__.py`
- Modify: `matrix_compiler.py`
- Modify: `experiment_models.py`

- [ ] Implement normalized draft defaults, schema validators, and migration helpers in `experiment_setup_adapter.py`.
- [ ] Implement the only authoritative Python translation path from normalized draft → current compiler spec.
- [ ] Add backend preview/compile helpers that accept normalized draft payloads directly, invoke the adapter, then call the existing `compile_experiment()`.
- [ ] Update `/comfymodal/experiments/compile` and experiment create/start routes to accept normalized setup draft payloads and reject malformed bypass payloads.
- [ ] Extend compiled checkpoint/cell payloads with stable normalized dimensions, adapter schema version, workflow revision/hash, and stack–LoRA pairing identity.
- [ ] Keep the existing compiler authoritative for exact totals and cell generation.

### Task 3: Implement profile normalization, migration-safe persistence, and stale-profile checks

**Files:**
- Modify: `comparison.py`
- Modify: `__init__.py`
- Modify: `tests/test_experiment_setup_adapter.py`
- Modify: `tests/test_comparison_extended_mappings.py`
- Modify: `tests/test_testing_profiles_js.py`

- [ ] Add normalized runtime-profile builders that expose setup-safe metadata without duplicating full legacy payloads.
- [ ] Normalize legacy profiles with missing `workflow_mode` deterministically to `t2i` with `workflow_mode_source="legacy_default"` and no on-load rewrite.
- [ ] Synthesize one in-memory `Default` model stack from the current main triple when richer stack metadata is absent.
- [ ] Synthesize `Workflow Default` and `No LoRA` when explicit configuration metadata is absent, without inventing extra LoRA configurations.
- [ ] Implement mode-aware mapping capability summaries (`common`, `t2i`, `i2i`) and partial incompatibility reasons.
- [ ] Persist explicit normalized profile metadata only on validate/edit/confirm/update-from-canvas with atomic non-destructive merge and backup/reversible legacy preservation.
- [ ] Add revision/hash increments or equivalent stale-profile tracking fields used by the normalized draft.

### Task 4: Extend compiler representation only as needed for exact stack–LoRA pairing semantics

**Files:**
- Modify: `matrix_compiler.py`
- Modify: `experiment_setup_adapter.py`
- Modify: `tests/test_matrix_compiler.py`
- Modify: `tests/test_experiment_setup_adapter.py`

- [ ] Audit the current compiler input shape against the ten representability cases.
- [ ] If exact stack–LoRA pairing cannot be represented today, add the smallest compiler-schema extension necessary to represent explicit workflow configurations without broadening combinations.
- [ ] Preserve workflow-owned defaults, per-workflow identities, and LoRA strength sweep determinism.
- [ ] Ensure the compiler never produces unintended stack × global-LoRA Cartesian expansion when explicit pairings were requested.
- [ ] Verify exact cell totals for every representability case.

### Task 5: Build frontend normalized draft adapter and runtime preview state

**Files:**
- Create: `web/testing-setup-adapter.js`
- Modify: `web/testing-api.js`
- Modify: `web/modal-testing.js`
- Modify: `tests/test_testing_setup_js.py`

- [ ] Implement normalized frontend draft defaults, draft migration helpers, runtime preview state, and UI-safe API response normalization in `web/testing-setup-adapter.js`.
- [ ] Keep transient preview/loading/error state out of persisted drafts.
- [ ] Add debounced/cancellable backend preview requests that send normalized draft payloads to the backend compile/preview route.
- [ ] Extend `web/testing-api.js` with setup preview/create/run helper calls that operate on normalized drafts, not legacy compiler fragments.
- [ ] Update `web/modal-testing.js` draft persistence so modal close/reopen and tab switches preserve the normalized draft and runtime-safe experiment context.

### Task 6: Replace Setup UI with the five-section experiment builder

**Files:**
- Modify: `web/testing-setup.js`
- Modify: `web/testing-styles.js`
- Modify: `tests/test_testing_setup_js.py`
- Modify: `tests/test_testing_ui_wired.py`

- [ ] Replace the current nine-section Setup implementation with five visible sections: Generation Type, What Changes?, Workflows, Test Values, Review & Run.
- [ ] Implement accessible tri-state variable tiles with visible state labels, keyboard support, direct-state menu, shift-reverse cycling, reset-all, and category resets.
- [ ] Hide irrelevant controls by generation type and variable mode.
- [ ] Keep Prompt mandatory, Input Image I2I-only, Model Stack workflow-specific, and LoRA Configuration workflow-specific.
- [ ] Add sticky summary navigation showing generation type, tested variables, controlled variables, workflow count, total cells, and validation state.

### Task 7: Implement workflow cards, model-stack selection, LoRA configuration UX, and pairing scopes

**Files:**
- Modify: `web/testing-setup.js`
- Modify: `web/testing-profiles.js`
- Modify: `web/testing-styles.js`
- Modify: `tests/test_testing_setup_js.py`
- Modify: `tests/test_testing_profiles_js.py`

- [ ] Render workflow cards filtered by generation type and capability requirements, with hidden incompatible-workflow disclosure.
- [ ] Show mode badges, migration badges, default model stack summary, stack count, LoRA slot count, saved LoRA configuration count, revision/hash hint, compatibility state, and per-workflow cell estimates.
- [ ] Implement workflow-local model-stack selection for Default vs Testing, with synthesized Default stack fallback and one-value variation warnings.
- [ ] Implement discriminated LoRA configuration objects (`workflow_default`, `no_lora`, `explicit`) and workflow-local selection UI.
- [ ] Implement stack–LoRA scope modes: all selected stacks, selected stacks with explicit fallback, and advanced per-stack matrix.
- [ ] Enforce slot-capacity validation, deterministic strength-combination counts, and exact stack–LoRA pairing preview semantics.

### Task 8: Implement Test Values and authoritative Review & Run flow

**Files:**
- Modify: `web/testing-setup.js`
- Modify: `web/testing-api.js`
- Modify: `tests/test_testing_setup_js.py`
- Modify: `tests/test_experiment_setup_adapter.py`

- [ ] Show only Testing and Controlled variables in Test Values.
- [ ] Implement prompt items with optional paired `negative_override` values and controlled negative semantics (`null` vs explicit empty string).
- [ ] Implement I2I prompt-image pairing modes: cartesian, paired, fixed-image-per-workflow.
- [ ] Enforce explicit pairing data and actionable blocking errors for missing pairs.
- [ ] Implement authoritative Review & Run auto-preview with per-workflow multiplication summaries, fairness summary, compatibility summary, large-matrix warning, and secondary advanced execution settings.
- [ ] Ensure Run always revalidates through the backend adapter even after a successful preview.

### Task 9: Implement workflow-oriented Results grouping adapter

**Files:**
- Modify: `web/testing-results.js`
- Modify: `web/testing-api.js`
- Modify: `tests/test_testing_results_js.py`
- Modify: `tests/test_testing_shell_integration.py`

- [ ] Add a presentation adapter that reads stable normalized dimensions from compiled cells/events/results payloads.
- [ ] Default to Workflow as the top-level group and derive row/column axes from Testing dimensions only.
- [ ] Keep Controlled values in fairness/summary treatment and Default values in metadata.
- [ ] Preserve the existing A/B comparison workflow and add explicit Technical checkpoint view fallback.
- [ ] Ensure one-axis experiments render as a readable strip/list rather than inventing a technical second axis.

### Task 10: Verify end-to-end behavior in tests and the real browser

**Files:**
- Modify: `tests/browser/modal_testing_suite_smoke.mjs`
- Add or update screenshot outputs under `.playwright-mcp/` or approved output paths

- [ ] Run focused backend/frontend tests for setup adapter, matrix compiler, profile normalization, setup/results JS, and shell integration.
- [ ] Run the broad relevant suite to catch regression across compiler, scheduler persistence, results, and profile routes.
- [ ] Open the real ComfyUI Modal GPU experience, perform the required T2I and I2I checklist flows, verify the old nine-section Setup is gone, and confirm workflow-oriented Results grouping.
- [ ] Capture screenshots for T2I tri-state grid, I2I tri-state grid, workflow cards, model-stack selector, LoRA all-stack mode, LoRA per-stack matrix, Test Values, Review & Run, and workflow-oriented Results.
- [ ] Record any remaining limitations honestly.

### Execution notes

- Do not commit unless the user explicitly asks.
- Preserve existing backend execution semantics unless a minimal compiler-shape extension is required for exact pairing representation.
- Keep profile migration non-destructive and idempotent.
- Do not let UI components construct legacy compiler-schema fragments directly.
