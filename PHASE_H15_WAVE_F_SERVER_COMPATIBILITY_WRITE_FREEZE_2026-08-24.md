# PHASE H15 — WAVE-F SERVER COMPATIBILITY & LEGACY WRITE FREEZE (F-SRV) (2026-08-24)

**Batch type:** H-WAVE F implementation, lane **F-SRV** (sole writer to `__init__.py` for the batch window). No deploy, no Modal invocation, no GPU/live generation, no commit/push/branch/worktree/reset/stash/clean. Shared tree intentionally dirty; H16 ran concurrently owning ONLY `web/studio-settings.js` + its two `/studio/backends` Settings count-row pins in `tests/test_studio_backend.py` — zero overlap with this lane's files.
**Authority:** `PHASE_H5_CONSOLIDATION_CONTRACT_FREEZE_2026-08-23.md` H5 Follow-Up D (**FD-1…FD-26 final authority**, esp. FD-9/10/11/12/14/15/16/17/18/20/21/22), `PHASE_H5D_WAVE_E_CONVERGENCE_WAVE_F_FREEZE_2026-08-24.md`, `PHASE_H14_LEGACY_SETTINGS_COMPARISON_RETIREMENT_2026-08-24.md`, `PHASE_H13_RECENT_RUNS_HISTORY_V2_AND_LEGACY_EXPERIMENT_RETIREMENT_2026-08-24.md`, `PHASE_H12_V2_ONLY_EXECUTION_CONSOLIDATION_2026-08-24.md`.

---

## 0. VERDICT

`H15 COMPLETE — WAVE F SERVER FREEZE LANED GREEN. Every FD RETIRED_WRITE target is inert with the exact 409 class and every FD RETIRED_EXECUTION target is inert with the exact 410 class; zero retired request mutates any store (hash-proven); zero retired execution reaches a scheduler/model/deploy/streaming path; all ten Comparison COMPAT_READ routes survive with validate/detect-slots still pure compute; /comparison/run stays 410 COMPARISON_RETIRED; protected GET /experiments/{id} + stop-now are byte-untouched; /studio/experiment-v2 survives; warmup can no longer execute while shared run_prompt_stream survives for V2 ModalTransport; /auth/setup can no longer write/deploy; legacy .presets writes freeze with reads alive; /studio/backends writers freeze with GET alive; /studio/presets* stays fully live; Workflow Presets stay distinct; run-history reads survive AND annotations/save remain COMPAT_WRITE; no route was deleted. FULL GATE: Python 1974 · Node-unit 21 files · Fake Playwright 211/211 — ALL GREEN.`

---

## 1. PRE/POST ROUTE TABLE (exact disposition; post-edit `__init__.py` lines)

Response standard = frozen FD-17: EXECUTION retirement → HTTP 410 `{"status":"error","error_code":"<FEATURE>_RETIRED","message":…}`; WRITE retirement on readable compat data → HTTP 409 `{"status":"error","error_code":"<FEATURE>_READ_ONLY or frozen code","message":…}`. All responses are deterministic bounded JSON, returned BEFORE body parsing where the body is irrelevant, before any store access, with no stack trace.

### Comparison (FD-9/FD-10/FD-11)
| # | Method+Path | Pre class | Post behavior | Post :line |
|---|---|---|---|---|
| 1 | GET /comparison/profiles | COMPAT_READ | UNCHANGED | :5427 |
| 2 | POST /comparison/profiles | RETIRED_WRITE | **409 COMPARISON_READ_ONLY** (body ignored) | :5435 |
| 3 | GET /comparison/profiles/{id} | COMPAT_READ | UNCHANGED | :5448 |
| 4 | PUT /comparison/profiles/{id} | RETIRED_WRITE | **409 COMPARISON_READ_ONLY** | :5459 |
| 5 | DELETE /comparison/profiles/{id} | RETIRED_WRITE | **409 COMPARISON_READ_ONLY** | :5472 |
| 6 | POST …/{id}/duplicate | RETIRED_WRITE | **409 COMPARISON_READ_ONLY** | :5485 |
| 7 | POST …/{id}/validate | COMPAT_READ (pure compute) | UNCHANGED (still executes compute, NOT 409) | :5498 |
| 8 | POST …/{id}/detect-slots | COMPAT_READ (pure compute) | UNCHANGED (still executes compute, NOT 409) | :5507 |
| 9 | POST …/{id}/slots | RETIRED_WRITE | **409 COMPARISON_READ_ONLY** | :5518 |
| 10 | POST /comparison/run | RETIRED_EXECUTION | UNCHANGED — still **410 COMPARISON_RETIRED** (H14 body preserved verbatim) | :5531 |
| 11–15,17 | GET results · results/{id} · workflow/nodes · workflow · config · gallery/{id} | COMPAT_READ | UNCHANGED | :5553/:5561/:5572/:5583/:5594/:5615 |
| 16 | POST /comparison/config | RETIRED_WRITE | **409 COMPARISON_READ_ONLY** | :5602 |

Frozen message (all six): `"Comparison stores are read-only compatibility data (Phase H Wave F). Stored profiles and historical results remain readable."`

### Legacy Experiment family (FD-12/FD-13)
| Route | Pre class | Post behavior | Post :line |
|---|---|---|---|
| POST /experiments/compile | ZERO_CALLER pure compute | **UNCHANGED** per FD-12/batch §6 (no invented retirement) | :5726 |
| POST /experiments (create) | RETIRED_EXECUTION | **410 EXPERIMENT_RETIRED** before body parse/store/V2-ensure/scheduler | :5770 |
| GET /experiments | COMPAT_READ | UNCHANGED | :5791 |
| GET /experiments/{id} | TRANSITIONAL_MODERN `WAVE_F_DO_NOT_FREEZE=TRUE` | **BYTE-UNTOUCHED** (handler proven by source pin) | :5820 |
| GET /{id}/events | COMPAT_READ | UNCHANGED | :5837 |
| POST /{id}/start | RETIRED_EXECUTION | **410 EXPERIMENT_RETIRED** (warmup gate + CheckpointStreamInvoker + scheduler start unreachable) | :5856 |
| POST /{id}/pause | RETIRED_WRITE | **409 EXPERIMENT_READ_ONLY** | :6185 |
| POST /{id}/stop-after-current | RETIRED_WRITE | **409 EXPERIMENT_READ_ONLY** | :6198 |
| POST /{id}/stop-now | TRANSITIONAL_MODERN PROTECTED | **BYTE-UNTOUCHED** (scheduler-stop/pending-stop/404 pinned) | :6211 |
| POST /{id}/resume | RETIRED_EXECUTION | **410 EXPERIMENT_RETIRED** | :6231 |
| POST /{id}/clone | RETIRED_WRITE | **409 EXPERIMENT_READ_ONLY** | :6245 |
| POST /{id}/run-missing | RETIRED_EXECUTION | **410 EXPERIMENT_RETIRED** | :6258 |
| POST checkpoints continue/restart/restart-from | RETIRED_EXECUTION ×3 | **410 EXPERIMENT_RETIRED** ×3 | :6272/:6286/:6300 |
| POST checkpoints skip/unskip | RETIRED_WRITE ×2 | **409 EXPERIMENT_READ_ONLY** ×2 | :6314/:6327 |
| GET checkpoints logs · cells/{cell}(+/attempts) | COMPAT_READ | UNCHANGED | :6340/:6358/:6370 |
| POST cells/{cell}/rerun | RETIRED_EXECUTION | **410 EXPERIMENT_RETIRED** | :6374 |
| POST /{id}/rerun-selected | RETIRED_EXECUTION | **410 EXPERIMENT_RETIRED** | :6388 |

Execution-retired message: `"Legacy experiment [creation|execution] was retired in Phase H (Wave F). Modern experiments run through /studio/experiment-v2; historical experiment records remain readable."` Write-retired message: `"Legacy experiment stores are read-only compatibility data (Phase H Wave F). Historical experiment records remain readable."`

### Adjacent + other families
| Route | Pre class | Post behavior | Post :line |
|---|---|---|---|
| POST /studio/experiment | RETIRED_EXECUTION (zero modern callers) | **410 EXPERIMENT_RETIRED** before preset load/validation/REGISTRY/History-V2/scheduler (`handle_studio_experiment` no longer referenced anywhere in the handler) | :7275 |
| POST /studio/experiment-v2 | MODERN_LIVE | UNTOUCHED (route registered; zero freeze codes in `experiment_modern_routes.py`) | experiment_modern_routes.py |
| GET /deploy-warmup/status | ZERO_CALLER diagnostic read | **UNCHANGED** per FD-14/batch §14 | :7296 |
| POST /deploy-warmup/run | RETIRED_EXECUTION | **410 WARMUP_RETIRED** before workflow resolve / stream / state mutation | :7304 |
| POST /deploy-warmup/invalidate | RETIRED_WRITE | **409 WARMUP_RETIRED** (odd code name intentional, frozen by FD-17); zero WarmupState mutation | :7325 |
| POST /auth/setup | RETIRED_WRITE | **409 AUTH_SETUP_RETIRED** before token validation / `_write_modal_toml` / workspace upsert / deploy thread | :3577 |
| GET /studio/backends (+`?kind=comparable`) | hidden COMPAT_READ | **UNCHANGED** — still answers stored data incl. comparable filter | :7034 |
| POST/PATCH/DELETE/duplicate /studio/backends | RETIRED_WRITE ×4 | **409 BACKENDS_READ_ONLY** ×4 | :7066/:7079/:7092/:7105 |
| `.presets/prompts` create/update/delete/duplicate/import | RETIRED_WRITE ×5 | **409 LEGACY_PRESETS_READ_ONLY** ×5 | :6407/:6428/:6441/:6454/:6467 |
| `.presets/images` create/update/delete | RETIRED_WRITE ×3 | **409 LEGACY_PRESETS_READ_ONLY** ×3 | :6485/:6506/:6519 |
| `.presets/prompts|images` list/get-by-id | COMPAT_READ | UNCHANGED | :6403/:6420/:6481/:6498 |

LEGACY_PRESETS message: `"Legacy prompt/image preset stores are read-only compatibility data (Phase H Wave F). Stored presets remain readable."` BACKENDS message: `"The legacy backend registry is read-only compatibility data (Phase H Wave F). Stored entries remain readable via GET /studio/backends."`

**Routes deleted: ZERO. Decorators deleted: ZERO.** Registry proof below.

## 2. BYTE-INTEGRITY / NO-MUTATION EVIDENCE

All proofs are isolated temp-store hash sweeps in `tests/test_h15_wave_f_server_freeze.py` (36 tests, direct-run; runner registration untouched):

- **Comparison**: temp store seeded via `comparison.create_profile` + `save_comparison_config`; SHA-256 of every file identical before/after invoking all six frozen writers AND `/comparison/run` (statuses `[409×6, 410]`). Real user stores never touched.
- **Experiment REGISTRY**: temp experiments root injected via `experiment_service.experiments_root` patch; snapshot equality across all 14 retired execution/write requests.
- **Warmup state file**: real `.deploy_warmup_state.json` SHA-256 + mtime identical across invalidate (409) and run (410).
- **`.presets/`**: temp node dir seeded via presets service; full-tree SHA-256 identical after all eight writer calls.
- **`.studio_backends.json`**: real-file SHA-256 + mtime identical after all four writer calls.
- **`modal.toml`**: SHA/mtime unchanged through auth/setup (plus tripwires proving `_write_modal_toml`, workspace upsert, and `_run_deploy_background` are unreachable).

## 3. PROTECTED SEAMS (FD-13)

- `GET /experiments/{id}`: unknown id → 404 unchanged; seeded id → 200 `{status, definition, snapshot, events}` shape unchanged; handler region contains neither `EXPERIMENT_RETIRED` nor `EXPERIMENT_READ_ONLY`.
- `POST .../stop-now`: unknown id → 404 unchanged; handler region still contains exactly `REGISTRY.get_scheduler` → `clear_pending_stop` → `sched.stop_now()` → definition-exists branch `request_pending_stop` → 404 fallthrough (source pin).
- Frontend wiring untouched (`getStudioRunStatus` poll / `stopExperiment` cancel remain in `web/studio-playground.js` — pinned by the existing H14 suite, green).

## 4. FAKE `/STUDIO/EXPERIMENT` PARITY (batch §11)

- `tests/browser/fake/fake-server.mjs`: mirror now returns fake-equivalent **410 `{"status":"error","error_code":"EXPERIMENT_RETIRED",…}`** with zero experiment creation (`engine.handleStudioExperiment` no longer called from the route).
- Harness-only additive control endpoint `POST /__comfymodal_test/legacy-experiment-seed` delegates to the engine creator so stale-record specs can still seed WITHOUT the retired route (never called by product code).
- `studio-fake-experiment-gating.spec.mjs` G5: seed re-pointed to the control endpoint; NEW focused parity assertion proves the retired route answers 410 `EXPERIMENT_RETIRED` and the engine creator log stays at exactly the one harness seed.
- Untouched: `/studio/experiment-v2`, GET `/experiments/{id}`, stop-now, run-history mirrors, preset CRUD mirrors.

## 5. `run_prompt_stream` CENSUS (batch §15)

Post-freeze production call/import classification:

| Caller | Class |
|---|---|
| `execute_plan` → `ModalTransport` (`comfymodal_runtime/modal_transport.py`) → `modal_client.run_prompt_stream` | **MODERN_V2_TRANSPORT — intact (hard requirement met)** |
| `_execute_comparison_profile` (`__init__.py`, textual `async for _msg in run_prompt_stream(`) | DEAD_RESIDUE (def-only occurrence, zero call sites since H14; Wave G deletes) |
| warmup route direct call (`ev`) | **RETIRED_ROUTE_UNREACHABLE** — removed by this freeze; census regex now finds exactly `["_msg"]` |
| `canonical_execution.execute_modal_prompt` / `LocalRemoteInvoker` | DEAD_RESIDUE (pre-existing post-H12; untouched per no-Wave-G rule) |
| UNKNOWN | none |

Census pin updated in the owned H14 suite test (`test_warmup_is_sole_reachable_direct_stream_caller_in_init`): expected direct calls `["_msg"]` (was `["_msg","ev"]` pre-F). `modal_client.run_prompt_stream` def + transport reference pinned green.

## 6. LIVE-FAMILY NEGATIVE GUARDS (anti-over-freeze)

- **Backend/Runtime Presets (FD-6)**: end-to-end CRUD driven against `studio_routes.register_studio_routes` in a temp dir — create → PATCH update → duplicate → list(≥2) → delete all 200; `studio_routes.py` contains zero freeze codes. Full-gate backend-preset/wizard/runtime specs green.
- **Workflow Presets (FD-7)**: version-scoped routes still registered; `studio_workflow_routes.py` contains zero freeze codes; no merge/rename/cross-freeze.
- **Run-history (FD-4/FD-5)**: reads list/detail/logs/timing answer from a seeded temp store; **PATCH annotations actually mutates** the temp record (`annotations.favorite=true`, `note="keep"` persisted to meta.json); **POST save actually performs its pipeline delegation** (stubbed `save_run_history_output` invoked once with the right run/output_index and its `persist_state_fn` persists `extra.output_saved=true` into meta.json). Handlers byte-untouched.
- **Compile**: still pure-compute 200 (untouched per FD-12).
- **Warmup status**: still 200 `{status, state}`.

## 7. TESTS — CHANGES BY THIS LANE

- **NEW** `tests/test_h15_wave_f_server_freeze.py` (36 tests; run directly via `python -m unittest tests.test_h15_wave_f_server_freeze`; NOT registered in `tests/run_studio_tests.py` per ownership rules).
- `tests/test_routes_registered.py::ExperimentCreateDetailNormalizedDraftTests` rewritten for the retired create route: 410-bounded-response + zero-store-mutation proof; detail tests now seed via `REGISTRY.store` directly (same filesystem surface the old create used) and keep their original normalized_draft intent. Registration pins untouched.
- `tests/test_h14_wave_e_retirement.py`: single owned-pin update — warmup census expectation `["_msg","ev"]` → `["_msg"]` (the intended FD-14 outcome), docstring states the Wave-F cause.
- Fake lane: `fake-server.mjs` (mirror freeze + seed endpoint), `studio-fake-experiment-gating.spec.mjs` (G5 seed path + parity assertion).
- NOT edited: `tests/run_studio_tests.py`, H16-owned `web/studio-settings.js` and the two H16 count-row pins in `tests/test_studio_backend.py`.

## 8. GATE + EXACT COUNTS

Focused: `python -m unittest tests.test_routes_registered tests.test_h14_wave_e_retirement tests.test_h15_wave_f_server_freeze` → **Ran 124 tests — OK** (includes the 36-test H15 suite).

FULL GATE `python tests/run_studio_tests.py --fake`:
```
STUDIO GATE SUMMARY
  python             run=1974  fail=0    error=0    skip=0
  node-unit          run=21    fail=0    error=0    skip=0
  fake-playwright    run=1     fail=0    error=0    skip=0
ALL STUDIO LANES GREEN
```

Exact fake count (mandated command):
```
npx playwright test --config=playwright.fake.config.mjs --reporter=line
  211 passed (3.8m)   / 211
```
Delta vs FD-1 baseline (1974/21/211): **±0 on all three lanes** — count-neutral because the focused H15 suite is intentionally unregistered and every edited in-gate test stayed 1:1.

## 9. CONCURRENT H16 OWNERSHIP TRUTH

H16 ran concurrently owning `web/studio_settings.js` + two `test_studio_backend.py` count-row pins. This lane observed H16's landed comment at `tests/test_studio_backend.py:459–464` ("H16 Wave F removes the Settings-side /studio/backends fetch") and did not touch those files. No failure in any lane targeted an H16-owned file; no ownership conflict occurred; `__init__.py` had exactly one writer throughout.

## 10. FILES MODIFIED BY THIS LANE ONLY

- Production: `__init__.py` (frozen regions only: comparison writers, experiment writers/executors except the two protected handlers, `/studio/experiment`, warmup run/invalidate, auth/setup, backends writers, `.presets` writers), `tests/browser/fake/fake-server.mjs`.
- Tests: `tests/test_h15_wave_f_server_freeze.py` (NEW), `tests/test_routes_registered.py` (one class rewritten), `tests/test_h14_wave_e_retirement.py` (one census pin), `tests/browser/fake/studio-fake-experiment-gating.spec.mjs` (G5 seed + parity assertion).
- Report: this document.
- Deleted: NONE (Wave-G owns all residue deletion; `_execute_comparison_profile`, dead helper bodies, `LocalRemoteInvoker`, `execute_modal_prompt`, `direct_studio_run_completion`, warmup code, legacy preset service functions all left in place).

Deploy / live / GPU / generation / commit / push by this batch: **NONE**.
