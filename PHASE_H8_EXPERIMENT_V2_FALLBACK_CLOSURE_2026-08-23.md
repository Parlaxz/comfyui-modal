# PHASE H8 — MODERN EXPERIMENT-V2 FALLBACK CLOSURE (2026-08-23)

**Batch type:** H-WAVE A4 implementation (H5 §14 step 1 + step 2). No deploy, no Modal, no GPU, no live generation, no commit/push/branch/worktree/reset.
**Authority:** `PHASE_H5_CONSOLIDATION_CONTRACT_FREEZE_2026-08-23.md` §14 (legacy experiment surface fate/order), §25 Wave A4, §28 invariants 14/19/22; H1 finding L6; H3 consumer analysis.

---

## 0. VERDICT

`H8 COMPLETE — modern Playground can no longer create a legacy experiment. Every normal modern Experiment path is experiment-v2. All gate lanes green.`

---

## 1. OLD FALLBACK BEHAVIOR (the defect)

H1/H2 finding (L6), verified in `web/studio-experiment-mode.js`:

- `experimentRunSurface()` returned `"legacy"` whenever no Workflow/Version was selected and no active/persisted modern experiment id existed — i.e. the NORMAL fresh Playground state.
- The `"legacy"` surface mounted `renderExperimentRunButton`, whose idle/completed/error branches offered a clickable creator wired through `buildExperimentClickHandler → executeExperimentRun → runStudioExperiment` → **POST `/comfymodal/studio/experiment`** (the legacy V1-era creator writing the `experiments/` JSON store).
- A user who simply enabled Experiment mode without a Workflow selection could therefore create NEW legacy experiments from the modern Playground — violating frozen H5 §14 ("Modern Experiments are authoritative"; legacy creator scheduled for retirement as a NEW-write authority).

## 2. NEW GATING BEHAVIOR

`experimentRunSurface(state)` now resolves as:

1. `"modern"` when `modernExperimentCanRun(state)` (Workflow **and** Version selected);
2. `"modern"` when an active or persisted modern experiment id exists (`_activeExperimentId` / `comfymodal.studio.experiment.active.v1`);
3. `"legacy"` ONLY for view/control compatibility while an already-active legacy experiment is in flight (`runState` non-terminal with an experiment/run id — statuses running/submitted/waiting/queued/in_progress). This state renders a disabled progress button + Cancel and can never create;
4. otherwise `"modern"` **gated**: the D5 section mounts with Run disabled and a visible reason. Terminal legacy states (completed/error/canceled/interrupted) fall through to the gated modern section — no re-run/retry creator exists anywhere.

Additional hardening:

- `executeModernExperimentRun` fails closed BEFORE any network activity when identity is missing (`{status:"error", gated:true, message:<reason>}`) — server 400 remains a backstop only.
- Rapid-click dedupe: new `pg._experimentSubmitInFlight` single-flight guard makes concurrent Run invocations submit exactly one definition (independent of controller state).
- `_mountSignature` now includes the gating flag so selecting/deselecting a Workflow/Version re-syncs the mounted section's button/reason within the existing 1200 ms watcher cadence (no remount needed).
- Gated section shows the contextual route **"Open Workflows"** via the pre-existing `context.setPage("workflows")` navigation (same pattern as the workflow gating line). No new deep-link infrastructure.
- `renderExperimentRunButton` idle/completed/error branches no longer render any creator button (read-only status / truthful gating note only); `buildExperimentClickHandler` is now unreachable from the mounted UI. The legacy API helper import (`runStudioExperiment`) is retained per H8 §13 for compatibility consumers.

## 3. EXACT REQUIRED MODERN IDENTITY

An experiment-v2 Run requires, resolved verbatim from `resolveModernWorkflowSelection` (workflow store → playground fallbacks):

- `workflowId` (non-empty string)
- `workflowVersionId` (non-empty string)

Optional but carried when present: `presetId`, `workflowName`, `presetName` (+ workflow snapshot from run context). If Mapping/Preset identity is absent the run is still allowed (planner-owned), matching the Phase D/F contract; nothing is synthesized client-side. Missing pieces produce truthful reasons:

- no Workflow: `Select a Workflow and Version before running an experiment.`
- Workflow without Version: `Select a Workflow Version before running an experiment.`

## 4. MODERN ROUTE PROOF

Fake Playwright `studio-fake-experiment-gating.spec.mjs` G2/G4, plus `studio-fake-modern-experiment-ui.spec.mjs` (unchanged, still green):

- Valid identity → exactly ONE `POST /comfymodal/studio/experiment-v2`; body carries `experiment_id` (`exp_v2_*`) and `definition.workflows[0] = {workflow_id: "wf_text2img", workflow_version_id: "wv1_latest", preset_id: "wpres_a"}`; no `cells`/`concurrency` keys.
- Live grid hydrates from `GET /history-v2/experiments/{id}/status`; completion appears through the existing History V2 projection (card visible on the History page).

## 5. ZERO-NEW-LEGACY-WRITE PROOF

Two independent instruments (H8 §16):

1. **Page-network instrumentation** (`page.on("request")`, exact regex `/\/comfymodal\/studio\/experiment$/`): zero matches across G1–G6 (gated state, valid run, switch-away, rapid-click+cancel, legacy reopen/cancel compat, single mode).
2. **Fake-engine creator log**: per-session `experimentCreateRequests[]` records EVERY creator POST server-side (`handleStudioExperiment` and `handleModernExperimentCreate`), exposed via `/__comfymodal_test/state` → `experimentCreateRequests`. In all modern scenarios: `count(POST /studio/experiment) == 0`, `count(POST /studio/experiment-v2) == expected`. In G5 the log contains exactly one legacy entry — the harness's own pre-mount seed — proving the UI produced none.

## 6. EXISTING LEGACY EXPERIMENT RECORDS (compatibility)

- Old records stay readable: `GET /comfymodal/experiments` list asserted in G5; recent-runs hydration untouched (Wave D owns it).
- Reopen/control compat preserved: seeding an old experiment and reopening it through the same in-session state path `loadExperimentIntoPlayground` produces mounts the legacy section with Running + Cancel (no enabled creator); Cancel drives `POST /experiments/{id}/stop-now` and the fake engine reports `stopped`. Legacy grid rendering coverage (two-cell grid, progressive independent cell updates, failed-cell persistence) is retained in the converted `studio-fake-experiments.spec.mjs` via seeded reopen.
- No destructive conversion: draft namespaces (`comfymodal.studio.experiment.draft.v1`, playground drafts/results) are never written by gating/reopen flows (unit test 16 asserts byte-identical draft state; browser G5 asserts drafts remain valid JSON objects). Old `experiments/` JSON, History mirrored rows, and active-state records are untouched — no data migration of any kind.

## 7. DEFERRED RECENT-RUNS DEPENDENCY (for Wave D)

Playground recent-runs still hydrates from `/run-history?limit=50`, `/history`, and `/experiments` (H5 §18 items 1/3), and the EXP-badge click path (`loadExperimentIntoPlayground`) still reopens legacy experiments read-only. **Exact next dependency for Wave D:** migrate Playground recent-runs hydration to History V2 projections (§23) BEFORE retiring legacy feed GETs; after that migration the remaining legacy surfaces in `studio-experiment-mode.js` (active-legacy compat renderer + `renderExperimentRunButton` running branch) and the playground legacy grid viewport become fully dead and can be removed together with the legacy creator route freeze (§14 steps 3–6).

## 8. TESTS

New focused coverage (H8 §15 items mapped):

| # | Requirement | Where |
|---|---|---|
| 1–2 | No identity → cannot Run; reason visible | Unit 12/16; Browser G1 |
| 3–4 | Zero POST `/studio/experiment`; zero V1 fallback | Browser G1–G6 (network + engine log); Unit 3/16/18 |
| 5–6 | Valid identity uses v2; body identity correct | Browser G2; Unit 3/11 |
| 7 | GPU frozen by existing modern contract | Unchanged F8 chain (`studio_phase_f8_gpu_reset_unit.mjs` green; modal_options captured once pre-submit — D5/E4 audits) |
| 8 | Rapid Run click dedupe | Unit 17; Browser G4 |
| 9 | Modern cancel stays modern | Browser G4 (`/history-v2/experiments/{id}/cancel`, zero stop-now) |
| 10 | History handoff intact | Browser G2; `studio-fake-modern-experiment-ui.spec.mjs` |
| 11–12 | Old record display/reopen; no destructive conversion | Browser G5; converted experiments spec a/b/c; Unit 16 |
| 13 | Single mode unaffected | Browser G6; `studio-fake-playground.spec.mjs`, workflow-run specs green |
| 14–15 | Invalid→valid enables; valid→invalid disables | Browser G2/G3 (signature-driven resync) |
| 16 | Suite-level zero Playground legacy creation | Engine log assertions in G1–G6 |

## 9. REGRESSION + FULL GATE

Ran (all green): existing modern Experiment fake specs (`studio-fake-experiment-v2`, `-modern-experiment-ui`), History Experiment specs, Workflow selection/handoff specs (`studio-fake-workflow-run` full file incl. converted test 28), Playground Single specs, new H8 tests. No H6/H7 failures touched.

```
python tests/run_studio_tests.py --fake
  python             run=1991  fail=0    error=0    skip=0
  node-unit          run=21    fail=0    error=0    skip=0
  fake-playwright    PASS   (199 tests in 22 files, 0 failed)
ALL STUDIO LANES GREEN
```

Baseline was Python 1991 / Node 21 / Fake 192. This lane adds +6 fake tests (gating spec); the remaining Fake delta (+1) comes from concurrently landed H6/H7 work in the shared tree, not this lane.

## 10. FILES MODIFIED BY THIS LANE

Production:
- `web/studio-experiment-mode.js` — surface fail-close, gating reasons, precondition backstop, single-flight dedupe, mount-signature gating resync, Workflows link, legacy renderer creator removal. (`web/studio-playground.js` NOT touched — the module contract expressed gating fully.)

Tests/fakes:
- `tests/browser/fake/studio-fake-experiment-gating.spec.mjs` (NEW — focused H8 spec G1–G6)
- `tests/browser/fake/fake-backend.mjs` — Experiment-region only: per-session `experimentCreateRequests` log (+ reset + dumpState exposure)
- `tests/browser/fake/scenarios.mjs` — additive `delayed_cells_wide` scenario (poll-cadence-spaced completions for deterministic reopen coverage)
- `tests/browser/fake/studio-fake-experiments.spec.mjs` — converted to post-H8 seeded-reopen compatibility coverage
- `tests/browser/fake/studio-fake-workflow-run.spec.mjs` — test 28 converted ("legacy experiment compatibility without the Playground fallback"); unused helper imports trimmed
- `tests/browser/fake/studio-fake-visual.spec.mjs` — "experiment grid" baseline converted to seeded reopen; snapshot `experiment-grid-fake-chromium-win32.png` regenerated (control panel now shows the gated V2 section)
- `tests/studio_experiment_v2_frontend_unit.mjs` — test 12 rewritten for H8 surface semantics; new tests 16 (fail-closed/zero-write), 17 (concurrent dedupe), 18 (helper retained/unreachable)
- `tests/test_testing_shell_integration.py`, `tests/test_testing_ui_wired.py` — two structural assertions updated to pin the H8 contract (no creator onclick in legacy renderer; reason rendered by the gated modern section)

Untouched by design: `web/studio-playground.js`, `web/studio-backend-api.js` (legacy helper retained), Backend/Settings/History modules, `tests/run_studio_tests.py`, all backend Python routes/data.

## 11. PASS CRITERIA CHECK

- Normal modern Playground cannot create a legacy experiment — YES (UI unreachable + action-level backstop + dual instrumentation).
- Missing modern identity fails closed in UI — YES (disabled Run + visible reason + Workflows route).
- Valid identity always uses experiment-v2 — YES (single POST, identity baked).
- Old records remain readable/reopenable — YES (list/read/reopen/cancel compat kept).
- No routes/data destructively removed — YES (additive fakes only; legacy routes intact).
- Single Playground unchanged — YES (G6 + existing specs green).
- Tests pass — YES (all lanes green).

Deploy / live / GPU / generation / commit / push by this batch: **NONE**.
