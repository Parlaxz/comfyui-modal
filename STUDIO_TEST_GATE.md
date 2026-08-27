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
| History V2 / Phase-E contracts | test_history_v2_api, test_history_v2_migration, test_history_v2_mixed_pagination, test_history_v2_repository, test_history_v2_production_writer, test_history_v2_replay_core, test_history_v2_generate_original, test_history_v2_modern_experiment, test_phase_e_contract, test_phase_e_fake_parity, test_phase_e_wave2_contract, test_phase_e_logical_output_integration (E1C), test_e2d_preview_method_contract (E2D) |
| Workflows | test_workflow_domain, test_workflow_routes, test_workflow_metadata, test_workflow_run_integration, test_studio_workflow_manifest-adjacent identity coverage via test_workflow_run_integration |
| Model Library | test_model_library, test_model_library_routes, test_dependency_resolver |
| Portability | test_portability_risk_engine, test_portability_backend, test_portability_roundtrip, test_portability_cache_integration, test_portability_contract, test_portability_target_rules, test_portability_fixtures, test_portability_cache (pytest-style) |
| Studio backend/routes/persistence | test_routes_registered, test_studio_backend, test_studio_direct_run, test_studio_error_contract (pytest-style shim), test_studio_history_v2_js, test_studio_progress_tracker, test_studio_runtime, test_studio_timing_integration (RED classes excluded — see below) |
| Execution V2-only (H20 registration) | test_phase8_execution_mode, test_h12_v2_only_consolidation |
| Run-history authority (H20 registration) | test_run_history, test_task2_run_history_extensions, test_run_history_save |
| UI architecture (H20 registration) | test_modal_workspace_ui_ast |
| Progress/annotations (H20 registration; renamed from test_task3_progress_annotations) | test_studio_progress_annotations |
| Wave freezes | test_f8_gpu_authority, test_h14_wave_e_retirement, test_h15_wave_f_server_freeze |
| Presets | test_presets_images, test_presets_prompts |
| Testing-suite frontend (structural) | test_testing_profiles_js, test_testing_results_js, test_testing_settings_js, test_testing_setup_js, test_testing_shell_integration, test_testing_ui_wired |

Node units registered since the table above was first written include the H6
Backend operations unit (`studio_backend_operations_unit.mjs`), the H7 Model
Library parity unit (`studio_model_library_parity_unit.mjs`), the Settings
compat authority unit (`studio_settings_compat_authority_unit.mjs`, renamed
from `studio_legacy_settings_authority_unit.mjs` in H20), and the E4D Retry
Original unit (`studio_phase_e4d_original_retry_unit.mjs`, H20). The
executable allowlists in `tests/run_studio_tests.py` remain authoritative.

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

Observed after E5 follow-up C (Generate Original / E6 preflight): the E3B2
backend routes and E4C frontend action landed concurrently and are now
covered end to end. The Python allowlist adds the green production suites
`test_history_v2_replay_core`, `test_history_v2_generate_original`, and
`test_history_v2_modern_experiment`; the Node allowlist adds
`studio_phase_e4c_generate_original_unit.mjs`,
`studio_phase_e_preview_settings_unit.mjs`, and
`studio_phase_e_history_presentation_unit.mjs`. The fake harness gains
`tests/browser/fake/studio-fake-phase-e-original.spec.mjs` with a new seed
`history_v2_phase_e_original` and an exact mirror of the landed Generate
Original contract (`POST /comfymodal/history-v2/generations/{id}/original`
plus `/original/retry`), scripted via `/__comfymodal_test/original-script`.
The old eager-Original assertion was replaced with the explicit
`View Original` contract, and only the `history-grid` visual baseline was
regenerated for the intentional "No image" placeholder presentation change.

Full-gate totals observed after follow-up C: Python `1584` run with `1` skip
(E2C production Preview persistence remains pending), Node `16` files,
fake Playwright `124` discovered in `15` files with `122` passed, `2`
skipped (`fixme`: sparse-detail overlay; UI retry completion pending the
frontend consuming `retry_required`/`/original/retry`), `0` failed, and
wrapper exit code `0` — ALL STUDIO LANES GREEN. The executable runner and
Playwright config remain authoritative as counts evolve.

Observed after E5 follow-up D1 (E2C reconciliation + sparse-detail closure):
the stale E2C production-pending Python skip was RETIRED and replaced by an
executable cross-layer contract test (`test_phase_e_contract.PhaseEE2CPreviewHandoffTests`)
that drives the real History V2 writer/result handoff end to end: preview-mode
Attempt, Preview asset type, no managed Original in Preview-only mode,
persisted `logical_output_key`, Thumbnail sharing the same logical key, and
the required Preview association existing before terminal completion. The
dedicated seam suite `tests/test_e2c_history_handoff.py` (32 tests) was
evaluated for gate membership and deliberately kept OUTSIDE the allowlist:
its runtime (~40s) is dominated by torch/comfyapp-gated producer thumbnail
encoding tests, which would import torch into the deterministic Studio gate;
its non-torch writer/repository/routes seam is pinned by the allowlisted
cross-layer contract test above. Revisit if that module is ever split.

The sparse-detail browser blocker was root-caused to TEST harness staleness,
not production: the default feed hides `failed`/`canceled` statuses
(`web/history-v2-view-state.js` `DEFAULT_HIDDEN_STATUSES`), so the sparse
failed card never rendered and the old click timed out. The former `fixme`
was replaced by two executable cases in `studio-fake-phase-e.spec.mjs` (F2
sparse-failed with the Failed toggle enabled; F3 sparse-interrupted visible
by default) asserting overlay opens, terminal/error state, zero-output/zero-
asset/no-params rendering, clean close, and no console errors.

Full-gate totals observed after follow-up D1: Python `1584` run with `0`
skips, Node `16` files passed, fake Playwright `125` discovered in `15`
files with `124` passed, `1` skipped (`fixme`: UI retry completion, owned by
E4D), `0` failed, wrapper exit code `0` — ALL STUDIO LANES GREEN.

Observed after E5 follow-up D2 (FINAL E6 reconciliation): the last stale
E4C-era Retry assertion in `studio-fake-phase-e-original.spec.mjs` was
replaced with the landed E4D contract and the adjacent retry `fixme` now
executes. The Python allowlist adds the E1C production integration suite
`test_phase_e_logical_output_integration` (16 tests, ~2.5s, sqlite/tempfile
only — closes the former featured/variant-grouping blocker inside the gate)
and the new lightweight `test_e2d_preview_method_contract` (9 tests, ~0.2s,
no torch) proving the frozen Preview contract (webp_lossy / q70 / fast),
the effort→method vocabulary with `fast → method 0`, the fallback converter
seam, and Experiment cell-plan freezing. The full production-seam suite
`tests/test_e2_preview_effort.py` (15 tests, ~24s, comfyapp/torch-gated)
remains focused diagnostic evidence OUTSIDE the deterministic gate — same
treatment as the E2C seam suite in D1. The historical E1B-pending skip in
`test_phase_e_history_projection.py` was retired into an executable
logical-output grouping projection test. No Phase-E implementation-pending
skip or fixme remains anywhere in the fake lane.

## Phase-E E6 Status — HISTORICAL (E5 follow-ups C/D1, superseded by D2)

The green E5 deterministic baseline did not mean Phase E or E6 was complete
at that time. E6 was **NOT GREEN** until every deterministic blocker below was
reconciled against the real History V2 repository and frontend, including
immutable Preview settings, Preview/Original Attempts and assets, remote
`modal://` asset projection, same-Generation Original replay, terminal
ordering, and sparse detail rendering.

After E5 follow-up C the Generate Original backend (E3B2) and frontend action
(E4C) are landed and deterministically covered at every layer: production
route/service/repository tests (`test_history_v2_generate_original`,
`test_history_v2_replay_core`), frontend contract units
(`studio_phase_e4c_generate_original_unit.mjs`), and fake Playwright flows
(`studio-fake-phase-e-original.spec.mjs`) covering create/reuse/rerender/
retry-required/busy/irreproducible/failure/success plus the Experiment-cell
same-Generation action.

After E5 follow-up D1 the E2C production Preview persistence seam is proven
by executable cross-layer coverage (real writer/result handoff; see the D1
totals above), and the sparse-detail browser case is executable (test-side
root cause: default-hidden failed status filter). The open items at that
time, with ownership:

1. Frontend retry wiring — the Retry control POSTs `/original`, receives
   `retry_required`, and never calls `/original/retry`, so no new Attempt is
   created (documented by an executable current-behavior test plus `fixme`).
   `pending E4D`.
2. Featured/variant-grouping production coverage is partial. `pending E1C`.

Taxonomy correction (D1): live remote `modal://` transport is classified as

> **E7 LIVE-ONLY PROOF** — required before Phase E live closure, not a
> deterministic E6 blocker.

The deterministic gate CAN prove URI-aware projection, route shape, the
fake/production reader contract, and that no local `Path.is_file()` misuse
exists; it inherently CANNOT prove an actual live remote producer fetch.
Listing live transport as an E6 blocker was therefore wrong: it weakens
nothing in E7, which retains full ownership of live remote-read evidence.

FINAL E6 VERDICT DEFERRED UNTIL E1C + E2D + E4D RECONCILIATION.

## Phase-E E6 Status — FINAL (E5 follow-up D2, 2026-08-22)

**E6 GREEN — deterministic Phase-E gate complete** (see
`PHASE_E6_DETERMINISTIC_RELEASE_GATE_2026-08-22.md` for the full 49-item
acceptance matrix).

Every earlier E5 blocker list above (E5C, E5D1) was a point-in-time
observation. Their items are all reconciled as of D2:

1. ~~Frontend retry wiring~~ — CLOSED by E4D. The Retry control POSTs the
   dedicated bodyless `/original/retry` route; ordinary `/original` on a
   failed-only Generation returns machine-readable `retry_required` and the
   frontend never auto-retries. Proven at Node-contract level
   (`studio_phase_e4d_original_retry_unit.mjs`) and browser level
   (`studio-fake-phase-e-original.spec.mjs`: no auto-retry on open, exactly
   one `/original/retry` POST per explicit click, zero ordinary `/original`
   POSTs for that action, durable new Attempt, failed Attempt + Preview
   retained, success without eager Original load).
2. ~~Featured/variant-grouping production coverage is partial~~ — CLOSED by
   E1C. The allowlisted `test_phase_e_logical_output_integration` proves the
   canonical logical-output key, one-group variant semantics, retry/rerender
   grouping, `output_count`, featured derivative membership, newest-winner,
   remote `modal://` keyed Originals, legacy compatibility, and Experiment
   parity against real repository/writer/route seams.
3. ~~E2C Preview persistence pending~~ — CLOSED by E5D1's executable
   cross-layer proof (retained; see D1 totals above).
4. ~~Sparse-detail overlay~~ — CLOSED by E5D1 (executable F2/F3 cases;
   retained).

E2D semantic gate coverage: the deterministic gate proves the frozen Preview
accepted options (`format=webp_lossy`, `quality=70`,
`webp_lossless_compression=fast`) and the method-selection contract
(`fast → method 0`, `balanced → 4`, `max → 6`) via
`test_e2d_preview_method_contract`. Encoder latency benchmarking is
diagnostic evidence, not deterministic acceptance; actual remote
CPU/libwebp behavior is E7 live-only proof.

LIVE-E7-ONLY (NOT deterministic blockers): actual remote Modal producer
writes a real `modal://` Preview; actual remote `modal://` Original
replay/fetch; actual container libwebp effective method 0; actual live
Preview `output_codec_ms`; actual live Preview→Generate Original
same-Generation sequence. These are required for Phase-E live closure but
never force deterministic E6 red.

The Phase-E follow-up fake scenarios are UI/state-machine evidence only. They do
not prove production writer persistence, SQLite transaction semantics, remote
Modal output, real codec latency, or live generation behavior.

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

## Post-E7 Reconciliation (Follow-Up A, 2026-08-22 — offline, deterministic)

E7 live validation exercised the real Modal backend and discovered three narrow
production defects. They were fixed with focused deterministic coverage before the
final successful Preview→Original pair. Because production changed after the E6
gate, this offline batch reconciles those fixes against the full deterministic gate.

**Three production fixes (E7):**
- `studio_workflow_run.py` — freeze plan-carried validation proof for modern Singles
  (`collect_validation_proof=True, comfyui_root=node_dir`, preserved verbatim
  through rebuild; non-empty `validated true` + `validated_workflow_hash` now
  frozen in snapshot, survives `to_dict/from_dict` and `RequestSnapshot`).
- `history_v2_replay.py` — wire Modal workspace credentials into replay dispatch
  (`_resolve_replay_workspace(plan)` prefers `request_metadata.workspace_id` else
  active fallback, fail-closed; `_default_replay_executor(..., workspace=...)` →
  `execute_plan(..., workspace=workspace)`; `GenerateOriginalService` ensures
  dispatch before claim and marks failed truthfully, never orphan queued).
- `experiment_lease.py` — content-hash lease collision refresh (`UPDATE ... WHERE
  created_at < ?`): `asset_id` = immutable content identity, `path` = mutable
  current `modal://` location; newer `created_at` wins, older never regresses,
  equal tie first-wins deterministically.

**New regression module (this batch):**
- `tests/test_e7_followup_reconciliation.py` (34 tests): validation-proof 10-point
  regression, clean first `/original` path, workspace precedence A–F + no-leak +
  no-mutate, transaction no-orphan, asset collision A–H + Preview/Thumbnail
  agnostic + asset-identity vs location, History ownership invariant, security
  per-user scope, replay+asset integration, old-workspace regression.

**Focused re-verification (all green, offline):**
`test_studio_workflow_run_plan_identity` 6 + `test_history_v2_replay_core`/`generate_original` 46 + `test_experiment_lease` 38 + `test_phase_e_contract`/`logical_output` 25 + `test_e7_followup_reconciliation` 34 = **152 focused** (~10 s); plus `test_workflow_run_integration` harness patch (stub `canonical_execution._collect_plan_validation_proof` headless) to keep the E7 proof-collection fix deterministic-green.

**Full wrapper (mandatory, authoritative, after E7 fixes):**

```
python tests/run_studio_tests.py --fake
Python 1609 run, 0 fail, 0 error, 0 skip
Node 16 files, 16 passed
Fake Playwright 126 discovered (15 files), 126 passed, 0 skip/fixme
Wrapper exit 0 — ALL STUDIO LANES GREEN
```

Observed counts are authoritative (allowlist unchanged `STUDIO_PY_MODULES`; the 34 new
reconciliation tests are the post-E7 companion proof outside the wrapper). No
Phase-E implementation-pending skip/fixme remains.

**Security/scope:** registry is per-user/local (`leases.db` + `.modal_workspaces.json`
workspaces all same user `ahassan2102/main`); globally mutable hash→location is
correct for single-user deduplication, not a multi-tenant leak. History ownership
is orthogonal to registry path refresh.

**Final Phase-E closure verdict:** `PHASE E COMPLETE — deterministic and live gates
green.` (see `PHASE_E_FINAL_CLOSURE_2026-08-22.md` for the 19-item closure State).

**Additional harness patch in this batch (test-only):**
`tests/test_workflow_run_integration.py` now stubs `_collect_plan_validation_proof`
in `setUp` for headless runs (mirrors `test_studio_workflow_run_plan_identity`),
preserving the E6 gate after the E7 proof-collection change. No production semantics
changed.

**Deployment/live/commit in this Follow-Up A:** NONE (offline only; already-collected
E7 live evidence `gen_f4e1...` remains authoritative; worktree left dirty per spec).
