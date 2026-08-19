# Studio Test Gate

Deterministic, repeatable release gate for **Studio-only** functionality in comfyui-modal.

This gate exists because the global `python run_tests.py` discovery sweeps in
every `tests/test_*.py` (80+ V2/runtime/Modal test modules) and is not a Studio
signal. This gate is an explicit allowlist of Studio-owned suites only.

## Fast deterministic gate (no live services)

Requires: `python` 3.11+, `node` 25+, Playwright 1.60+ (chromium installed),
aiohttp.

Run everything (Python + Node units + fake Playwright) from the repo root:

```
python tests/run_studio_tests.py --fake
```

Or lane by lane:

```
python tests/run_studio_tests.py          # current E5 lane: Python + Node allowlists
npm run test:fake                         # current E5 lane: fake Playwright allowlist
```

Exit code 0 only when every lane is green.

### Python lane and Node unit lane

The E5 baseline observed before the Phase-E follow-up was Python 1471 tests and
11 Node unit files. The executable allowlist in `tests/run_studio_tests.py` is
authoritative and may evolve as dedicated contract lanes are added.

Phase-E follow-up A adds `tests.test_phase_e_contract` and
`tests.test_phase_e_fake_parity` to the Python allowlist, including explicitly
skipped production-pending tests. It also adds
`tests/studio_phase_e_contract_unit.mjs` to the Node allowlist.

Observed after E5 follow-up A: Python `1484` tests with `2` skips, `12` Node
unit files, and `102` fake Playwright tests with `1` explicitly pending sparse
detail case. These totals are current evidence, not a permanent contract.

Phase-E follow-up B adds `tests.test_phase_e_wave2_contract` and
`tests/studio_phase_e_wave2_unit.mjs`, plus the dedicated fake spec
`tests/browser/fake/studio-fake-phase-e-wave2.spec.mjs`. The Wave-2 fake seed
is `history_v2_phase_e_wave2`; it models logical-output identity, derivative
provenance, Preview metadata, featured derivatives, remote Original-only
presentation, and frozen Experiment cell identities. The executable runner
and Playwright config remain authoritative for the resulting totals.

| Subsystem | Modules |
|---|---|
| History V2 / Phase-E contracts | test_history_v2_api, test_history_v2_migration, test_history_v2_mixed_pagination, test_history_v2_repository, test_history_v2_production_writer, test_phase_e_contract, test_phase_e_fake_parity, test_phase_e_wave2_contract |
| Workflows | test_workflow_domain, test_workflow_routes, test_workflow_metadata |
| Model Library | test_model_library, test_model_library_routes, test_dependency_resolver |
| Studio backend/routes/persistence | test_routes_registered, test_studio_backend, test_studio_direct_run, test_studio_error_contract (pytest-style shim), test_studio_history_v2_js, test_studio_progress_tracker, test_studio_runtime, test_studio_timing_integration (RED classes excluded — see below) |
| Presets | test_presets_images, test_presets_prompts |
| Testing-suite frontend (structural) | test_testing_profiles_js, test_testing_results_js, test_testing_settings_js, test_testing_setup_js, test_testing_shell_integration, test_testing_ui_wired |

### Node unit lane — 11 baseline files plus two Phase-E follow-up files

`tests/studio_run_model_unit.mjs`, `tests/studio_playground_run_unit.mjs`,
`tests/studio_workflow_run_unit.mjs`,
`tests/studio_history_v2_persisted_status_unit.mjs`,
`tests/studio_experiment_v2_unit.mjs`,
`tests/studio_experiment_v2_frontend_unit.mjs`,
`tests/studio_history_v2_experiment_unit.mjs`,
`tests/get_axis_eligibility_unit.mjs`, `tests/get_steps_recommendation_unit.mjs`,
`tests/get_seed_insertion_unit.mjs`,
`tests/browser/studio_completion_deterministic.mjs`
(also `npm run test:deterministic`).

Phase-E follow-up files: `tests/studio_phase_e_contract_unit.mjs` and
`tests/studio_phase_e_wave2_unit.mjs`.

### Fake Playwright lane — 94-test E5 baseline

`npm run test:fake` (config `playwright.fake.config.mjs`) drives the real
`web/` modules against the deterministic fake backend
(`tests/browser/fake/`) — no ComfyUI, Modal, GPU, or `:8188` required.

Phase-E follow-up adds `tests/browser/fake/studio-fake-phase-e.spec.mjs`.
Its sparse-detail UI case is explicitly marked pending until the E4 nullable
section fix lands. Counts are expected to change as pending implementation
tests become runnable; the runner and Playwright config remain executable
authority.

Wave-2 adds `tests/browser/fake/studio-fake-phase-e-wave2.spec.mjs` with
logical-output, Preview presentation, retained retry, featured-derivative,
remote Original-only, and Experiment detail cases. The remote Original case
asserts that the feed does not request the full asset and that the detail view
loads it only after the explicit `View Original` action. The Preview badge case
is executable against the current fake/real-frontend seam; the existing
sparse-detail case remains the only explicitly pending Phase-E browser case.

Observed after E5 follow-up B: Python `1495` tests with `3` skips, `13` Node
unit files, and `110` fake Playwright tests discovered. The focused Wave-2
spec passed `8/8`; the full fake lane observed `107` passed, `1` skipped, and
`2` failures from existing concurrent-worktree UI/baseline drift. Therefore
the current full deterministic gate is not green until those existing failures
are reconciled by the owning frontend/test lane.

## Phase-E E6 Status

The green E5 deterministic baseline does not mean Phase E or E6 is complete.
E6 is **NOT GREEN** until the production Preview and Generate Original seams
exist and the required cases pass against the real History V2 repository and
frontend, including immutable Preview settings, Preview/Original Attempts and
assets, remote `modal://` asset projection, same-Generation Original replay,
terminal ordering, and sparse detail rendering.

The Phase-E follow-up fake scenarios are UI/state-machine evidence only. They do
not prove production writer persistence, SQLite transaction semantics, remote
Modal output, real codec latency, or live generation behavior. The eventual
Generate Original response placeholder is documented in the dedicated Node
contract test but is not consumed by the frontend or exposed as a fake endpoint.

## Studio Live Smoke Gate (requires live services)

Run only when explicitly validating against real services. Required:
local ComfyUI at `:8188` (set `COMFYUI_URL`), a deployed Modal backend with GPU.

```
# Live E2E (real Modal backend + GPU + ComfyUI) — 1 test, gated by env flag
$env:COMFYMODAL_LIVE_E2E="1"; npm run test:playwright:live

# "Mocked" project — 71 tests; needs ComfyUI at :8188 to host the page + web/ files.
# /comfymodal/** requests are page-route mocked; no Modal/GPU required.
npm run test:playwright

# Cold-start benchmark — real Modal GPU; self-skips unless enabled
$env:COMFYMODAL_COLD_BENCHMARK="1"; npm run test:playwright --grep "cold"

# Smoke script against a running ComfyUI host
npm run test:playwright:smoke
```

`tests/browser/studio-cold-benchmark.spec.mjs` lives inside the mocked project
but always self-skips unless `COMFYMODAL_COLD_BENCHMARK=1`.

## What is intentionally excluded

The deterministic gate does NOT validate:

- Modal performance / submission optimization
- snapshot restore / bootstrap timing
- GPU preload / teardown
- V2 benchmark performance (`tools/benchmark_v2_direct.py`, benchmark harnesses)
- PromptExecutor / conditioning-cache optimization
- run-pipeline preflight (`tests/test_api_prompt_validator.py` — bridge-side)

Those retain their own specialized gates and are outside the Studio gate
by design.

Also excluded from the deterministic gate (documented, not failures):

- **Intentionally-RED TDD suites.** `tests/test_studio_timing_integration.py`
  contains 29 `*RED` classes (94 tests) written as TDD placeholders that "MUST
  fail against current production code"; the gate skips them (3 still fail =
  TDD backlog; the rest pass/skip). `tests/test_studio_live_progress.py` is an
  entirely-RED suite (23 tests) — excluded until the feature lands.
- **Runtime web/ internal contracts** (`tests/browser/test_frontend_tracker.mjs`,
  `tests/browser/studio_live_progress_tracker.mjs`,
  `tests/browser/test_queue_prompt_timing.mjs`) — they import
  `web/comfymodal-progress.js` / re-implement `modal-node.js` capture/consume,
  which are runtime-owned, not Studio-owned.

## Canonical Playground regression coverage (16 checks)

`web/studio-playground-run.js` controller + `web/studio-run-model.js` are
covered by `tests/studio_playground_run_unit.mjs` (19 sections) and
`tests/studio_run_model_unit.mjs` (14 sections), plus the fake lifecycle spec
(14 browser tests):

1. successful Single run → playground-run §1, model §1, fake-lifecycle #1
2. failed Single run → playground-run §2, fake-lifecycle #2
3. canceled Single run → playground-run §3, model §5, fake-lifecycle #3
4. interrupted Single run → playground-run §4, model §6, fake-lifecycle #4
5. canceled never shows success → playground-run §5, fake-lifecycle #14
6. duplicate completion → playground-run §6, §19, model §2, fake-lifecycle #5
7. late progress ignored → playground-run §7, fake-lifecycle #6
8. out-of-order events → playground-run §8, model §3, fake-lifecycle #7
9. stale previous-run event ignored → playground-run §9, fake-lifecycle #8
10. foreign Experiment event ignored → playground-run §10, fake-lifecycle #9
11. sampler progress isolation → playground-run §11, model §10, fake-lifecycle #10
12. workflow progress isolation → playground-run §12, fake-lifecycle #11
13. sequential runs clean → playground-run §13, model §8, fake-lifecycle #12
14. correct result/run association → playground-run §14, fake-playground f.
15. retry receives fresh identity → playground-run §15, model §7
16. terminal lock → playground-run §16, model §4, §12
17. ordered timing marks → playground-run §17, fake-lifecycle #13

## History V2 production contracts

Covered by `test_history_v2_repository` (21), `test_history_v2_mixed_pagination`
(22), `test_history_v2_production_writer` (28), `test_history_v2_api` (16),
`test_history_v2_migration` (6) and the fake spec `studio-fake-history-v2.spec.mjs`
(16): six feed orders (newest/oldest/fastest/slowest/workflow_asc/workflow_desc),
V2 mixed cursors `{"v":2,"g","e"}` (no `gs/es` skip counts), immutable request
snapshots, first-terminal-wins idempotency, multi-output assets, distinct
canceled/interrupted, truthful `workflow_name` and Experiment axis values.

## Workflows / Model Library / Settings contracts

`test_workflow_domain` (39): immutable Versions, immutable Mapping, revision
creates Version, Presets, default Preset, duplicate, copy-forward, dependency
gating. `test_model_library` (9), `test_model_library_routes` (8),
`test_dependency_resolver` (9): hash identity, explicit scans only, missing
dependencies, custom-node revision, compatible model choices. Settings:
`test_testing_settings_js`, `test_studio_backend.Settings*` + fake settings
spec (deploy status, profile level persistence, 7-section page).
