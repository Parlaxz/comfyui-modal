# Phase E5 Test and Regression Gate Audit

Date: 2026-08-17
Status: Read-only audit complete; production changes intentionally not made.

## Scope And Evidence

This audit covers the current Studio test topology, the deterministic release
gate, fake-backend to production parity, History V2 and modern Experiment
regression coverage, stale test classification, the proposed E6 deterministic
acceptance gate, and the minimal E7 live proof boundary.

The requested authoritative handoff
`COMFY_AI_HUB_STUDIO_POST_PHASE_D_ZERO_CONTEXT_HANDOFF_2026-08-17.md` was not
present under the available workspace. Conclusions therefore use the current
source, the existing Phase E1-E4 audits, current test files, and observed
deterministic test output. The worktree was already heavily dirty. No existing
file was reverted, edited, staged, committed, deployed, or used for a live
generation by this audit.

Primary current gate files:

- `tests/run_studio_tests.py`
- `package.json`
- `playwright.fake.config.mjs`
- `STUDIO_TEST_GATE.md`
- `tests/browser/fake/fake-server.mjs`
- `tests/browser/fake/fake-backend.mjs`
- `tests/browser/fake/scenarios.mjs`
- `tests/browser/fake/FAKE_BACKEND_GUIDE.md`

Primary production contract files:

- `history_v2_models.py`
- `history_v2_routes.py`
- `history_v2_repository.py`
- `history_v2_writer.py`
- `experiment_modern_routes.py`
- `experiment_modern_plan.py`
- `experiment_modern_scheduler.py`
- `web/history-v2-repository.js`
- `web/studio-history-v2-detail.js`
- `web/studio-history-v2-experiment.js`
- `web/studio-settings.js`
- `web/studio-experiment-mode.js`

## Executive Verdict

| Question | Verdict | Classification |
|---|---|---|
| Is there a current deterministic Studio release signal? | Yes. The explicit allowlisted Python/Node/fake gate passed in the observed run. | VERIFIED CURRENT BEHAVIOR |
| Does the checked-in gate document describe the current gate? | No. It still says Python 1419, Node 6 files, and fake Playwright 52 tests; the current runner has a larger allowlist and the observed fake suite has 94 tests. | UNKNOWN / NEEDS DOCUMENTATION UPDATE |
| Does the fake harness exercise real Studio frontend modules? | Yes. `fake-server.mjs` serves the real `web/` modules and the harness mounts the real Studio shell against fake HTTP and event-bus seams. | VERIFIED CURRENT BEHAVIOR |
| Is fake/prod parity complete for Preview and Generate Original? | No. The fake scenarios model Preview/Original payload shapes, but production Preview request propagation and Generate Original are not implemented end to end. | UNKNOWN / NEEDS IMPLEMENTATION PROOF |
| Are current stale failures evidence that the deterministic Studio gate is red? | No. They are outside the explicit allowlist and reference superseded symbols/contracts. | VERIFIED CURRENT BEHAVIOR |
| Is the E6 managed Preview/Original acceptance gate passable today? | No. The required production behavior is intentionally deferred or absent, and there is no authoritative E6 result. | UNKNOWN / NEEDS IMPLEMENTATION PROOF |
| Was the E7 live proof performed? | No. No deployment, live service, GPU work, or live image generation was performed. | UNKNOWN / NEEDS IMPLEMENTATION PROOF |

The current safe conclusion is therefore: **the deterministic Studio regression
foundation is green, but it is not evidence that the Preview/Original product
contract is implemented or live-ready.**

## Current Test Topology

### Explicit deterministic gate

`tests/run_studio_tests.py` is the authoritative entrypoint for the current
Studio-owned deterministic gate. It deliberately avoids global discovery of
unrelated runtime and Modal tests (`tests/run_studio_tests.py:1-18`). The
Python lane is an explicit module allowlist (`:40-74`), the Node lane is an
explicit file allowlist (`:82-96`), and fake Playwright is opt-in through
`--fake` (`:158-172,209-218`). The process returns non-zero if any included
lane fails (`:220-228`).

The current Node allowlist contains 11 files, including the modern Experiment,
History V2 Experiment, workflow-run, playground-run, and deterministic browser
completion unit modules. This is different from the stale six-file count in
`STUDIO_TEST_GATE.md:40-45`.

### Fake browser topology

`playwright.fake.config.mjs` runs only
`tests/browser/fake/studio-fake-*.spec.mjs`, with one Chromium worker,
`retries: 0`, a self-hosted server, and no ComfyUI or Modal dependency
(`playwright.fake.config.mjs:18-55`). The fake server:

1. Starts an isolated session for each test.
2. Serves the real `web/` modules under the extension path.
3. Exposes fake REST endpoints and the tracker event queue.
4. Provides explicit test-control endpoints for scenario selection, history
   seeding, event injection, and state inspection.

The scenario engine is in-memory and session-scoped
(`tests/browser/fake/fake-backend.mjs:83-123`). It applies declarative
timeline entries, poll-count transitions, terminal transitions, journal
events, tracker events, and deterministic PNG bytes. The extension guide
documents the same topology and identifies the real frontend mount and event
pump (`tests/browser/fake/FAKE_BACKEND_GUIDE.md:14-68`).

The fake harness is deterministic in scenario data, timing, seeded history,
and asset bytes. Experiment, run, prompt, checkpoint, attempt, and asset IDs
are deliberately generated per submission, so deterministic behavior must not
be interpreted as byte-for-byte stable identifiers
(`fake-backend.mjs:21-64`).

### Production topology

The production History V2 route surface is under
`/comfymodal/history-v2` and includes feed, generation detail, Experiment
detail, annotation mutations, and managed asset serving
(`history_v2_routes.py:11-24`). The modern Experiment surface is additive:

- `POST /comfymodal/studio/experiment-v2`
- `GET /comfymodal/history-v2/experiments/{id}/status`
- cancel, resume, and cell retry actions

`experiment_modern_routes.py:1-18` documents that contract. Its accepted
matrix is persisted before scheduler dispatch and status is projected from
durable attempts (`experiment_modern_routes.py:18-63`).

The production persistence boundary is materially different from the fake:
History V2 uses a SQLite store, immutable request snapshots, append-only
Attempts, asset rows, and writer-side output adoption. The fake stores derived
records in session memory and can register assets directly. Fake HTTP shape
parity is therefore useful, but it does not prove production writer,
filesystem, remote `modal://`, transaction, or scheduler behavior.

## Observed Verification

The following evidence was collected without deployment or live generation:

| Command or check | Observed result | Meaning |
|---|---|---|
| `python tests/run_studio_tests.py --fake` | Python 1471, Node 11 files, fake Playwright 94 tests passed | Current deterministic Studio gate is green |
| `npx playwright test --config=playwright.fake.config.mjs --list` | 94 fake tests discovered | Current fake discovery count |
| `python -m unittest` History V2 targeted group | 148/148 passed | Current History V2 API/repository/writer/migration/pagination/modern Experiment coverage |
| `python -m unittest` Workflow/domain/run targeted group | 94/94 passed | Current workflow and run-model coverage |
| Cancellation/output supplementary suites | Non-failing in the observed run | Supplementary evidence only; not the authoritative gate |
| `tests.test_output_contract` under unittest discovery | 0 tests discovered | Module-level pytest-style tests are not a unittest signal |
| `tests.test_restore_ordering_root_cause` | 18 tests, 1 failure, 2 errors | Historical/diagnostic suite; outside the current Studio allowlist |
| `tests.test_experiment_runner` subset | Four setup errors from absent current materialization symbols | Superseded runner contract, not a current gate failure |

The commands above are narrow and deterministic. The global test discovery
command remains intentionally excluded because it mixes Studio coverage with
unrelated V2/runtime/Modal tests.

## Gate Documentation Drift

`STUDIO_TEST_GATE.md` is an existing untracked document and was not changed by
this audit. Its instructions still state:

- Python: 1419 tests;
- Node: 6 files;
- fake Playwright: 52 tests.

The executable source of truth is now `tests/run_studio_tests.py` plus the
Playwright fake config. The stale counts should be treated as documentation
drift, not as a reason to expand the release gate or repair unrelated tests.
Updating that document is a separate later write and is not part of this
read-only audit deliverable.

## Fake/Production Parity Matrix

| Contract area | Fake implementation | Production implementation | Assessment |
|---|---|---|---|
| Session isolation | Per-session in-memory maps, reset/delete helpers, cookie or explicit session selection | Process/database and runtime ownership | Fake isolation is strong; it does not prove production persistence isolation |
| History V2 feed | Seeded generation/Experiment records, mixed V2 cursor, order/status/filter behavior | SQLite-backed repository and route projection | Shape and query coverage are aligned; persistence and writer paths need Python tests |
| History detail | Attempts, cells, output groups, missing assets, original failure shapes | `history_v2_repository.py` plus `history_v2_routes.py` | Fake covers UI states; remote asset liveness and attempt-derived failure require production proof |
| Asset serving | Deterministic PNG bytes, explicit missing asset 404s, output filename serving | Managed local paths and `modal://` remote references | Transport shape is aligned; fake bypasses writer/materialization and remote fetch logic |
| Single lifecycle | Declarative queued/running/terminal journal and tracker timelines | Studio workflow/run service and runtime callbacks | Fake covers event ordering and UI handling; it cannot prove runtime association ordering |
| Modern Experiment acceptance | Scenario-driven legacy/modern records and UI REST interactions | Server-owned cell planning, one transaction, scheduler dispatch | API/UI shape is covered; durable SQLite and scheduler recovery remain production-owned |
| Cancel/retry/resume | Test-control scenarios and fake action endpoints | Atomic repository action seams plus scheduler capability checks | Fake can exercise UI states; it cannot prove remote cancellation truthfulness |
| Settings | Deploy status, profile level, and local settings persistence endpoints | `/comfymodal/config` ordinary output settings | Settings UI is covered, but Preview fields are not in current production requests |
| Preview | `preview_result`, `original_result`, and failure scenarios model payload shape and asset 200/404 behavior | Preview mode/asset propagation is not complete | Recommended contract only; do not label as implemented |
| Generate Original | History UI exposes an unavailable action; no fake successful replay contract | Repository supports Attempts, but UI/API action is unavailable | Deliberately deferred; no E6 pass claim is possible |

The scenario file explicitly says the Preview scenarios model realistic payload
shape rather than an implemented production Preview preference
(`tests/browser/fake/scenarios.mjs:42-53`). That note is important: a passing
fake Preview scenario proves frontend handling of a shape, not production
compression, immutable request capture, or asset persistence.

## Current Coverage Matrix

| Scenario | Current deterministic coverage | Production status | Classification |
|---|---|---|---|
| History feed pagination and mixed generations/Experiments | Python repository/API tests and `studio-fake-history-v2.spec.mjs` | Implemented route/repository path | VERIFIED CURRENT BEHAVIOR |
| Status aliases and terminal projections | Model tests, route tests, fake seeded statuses | Implemented with derived status rules in `history_v2_models.py:131-221` | VERIFIED CURRENT BEHAVIOR |
| Multi-output, Preview-only, missing Original, failed/interrupted/canceled records | Fake seeded History V2 matrix and route tests | Projection exists, but remote/failure semantics have known E1 issues | VERIFIED CURRENT BEHAVIOR with production limitations |
| First-terminal-wins and stale-attempt protection | Repository and modern Experiment tests | Implemented at repository boundary | VERIFIED CURRENT BEHAVIOR |
| Modern Experiment one-definition submission | Node unit tests, fake modern Experiment specs, Python modern Experiment tests | Server-owned plan and durable matrix exist | VERIFIED CURRENT BEHAVIOR |
| Experiment cancel/retry/resume | Fake lifecycle/modern specs and Python route/repository tests | Scheduler capability and durable action seams exist | VERIFIED CURRENT BEHAVIOR for current contract; live transport unknown |
| Settings persistence and profile level | Fake settings spec and structural/Node tests | Ordinary output config exists; Preview values remain UI-only | VERIFIED CURRENT BEHAVIOR for existing settings; Preview gap |
| Preview enabled/codec/quality captured on Single | No authoritative passing contract test | `buildStudioModalOptions` omits Preview fields | UNKNOWN / NEEDS IMPLEMENTATION PROOF |
| Preview enabled/codec/quality frozen on Experiment cells | No authoritative passing contract test | Modern definition currently omits `modal_options` | UNKNOWN / NEEDS IMPLEMENTATION PROOF |
| Preview direct-sink compression and asset association | No deterministic end-to-end gate | E2 found direct sink as the preferred seam but not a complete Preview pipeline | UNKNOWN / NEEDS IMPLEMENTATION PROOF |
| Generate Original from Generation Detail | Button is visibly unavailable; repository returns unavailable | No route/replay service | UNKNOWN / NEEDS IMPLEMENTATION PROOF |
| Generate Original from Experiment cell | Button is visibly disabled | No action route/replay service | UNKNOWN / NEEDS IMPLEMENTATION PROOF |
| Sparse/empty Generation Detail | Placeholder paths exist, but nullable sections may reach `appendChild(null)` | Known renderer bug from E4 | UNKNOWN / NEEDS IMPLEMENTATION PROOF |
| Live Modal output bytes and deployment identity | Not run by instruction | Requires deployment and GPU-backed service | UNKNOWN / NEEDS IMPLEMENTATION PROOF |

## Stale and Excluded Test Classification

These findings are classification only. No stale test was modified.

| Suite or file | Observed issue | Classification | Correct handling |
|---|---|---|---|
| `STUDIO_TEST_GATE.md` | Counts do not match `tests/run_studio_tests.py` or current fake discovery | Documentation drift | Update separately after the gate is intentionally frozen |
| `tests/test_experiment_runner.py` | Expects `_MATERIALIZED_FILES_BY_INVOCATION`, while current production uses the newer direct-sink/materialization seams | Superseded runner contract | Keep outside Studio release gate; do not add compatibility symbols solely for this suite |
| `tests/test_production_phase3b1.py` | Expects singular `_PROD_DIRECT_SINK_REQUEST`; current code uses `_PROD_DIRECT_SINK_REQUESTS` | Stale production contract | Reconcile only in a dedicated production contract task |
| `tests/test_comfyapp_auto_warmup.py` | Expects `_warmup_cuda`, which is not a current production function | Stale warmup contract | Do not use as current Studio evidence |
| `tests/test_restore_ordering_root_cause.py` | 1 failure and 2 errors in an 18-test forensic suite | Historical diagnostic suite | Preserve as diagnostic evidence; do not count as release gate |
| `tests/test_output_contract.py` | Module-level tests are not discovered by unittest | Runner mismatch | If needed, run through its intended pytest-style runner in a separate task |
| `tests/test_studio_timing_integration.py` `*RED` classes | Intentionally failing TDD placeholders | Intentional exclusion | `tests/run_studio_tests.py` filters classes ending in `RED` |
| `tests/test_studio_live_progress.py` | Entirely RED/TDD and excluded | Intentional exclusion | Track until the feature lands |
| Runtime web progress tests | Own `web/comfymodal-progress.js` or runtime event internals | Ownership exclusion | Keep outside the Studio-owned release gate |

The stale failures are valuable migration evidence. They are not evidence that
the current explicit Studio gate is unreliable, provided the gate remains an
allowlist and the stale suites remain clearly classified.

## E6 Deterministic Acceptance Gate

E6 should be a new deterministic contract gate, not a relabeling of the
current green gate. It becomes authoritative only after the product seams
exist and the following cases pass against the real History V2 repository and
the real Studio frontend modules.

### Required E6 cases

1. Preview defaults are globally owned, default OFF, and captured at request
   creation time.
2. A Preview-enabled Single request carries immutable Preview codec and quality
   options in its request snapshot.
3. A Preview-enabled Experiment carries one immutable options object in the
   accepted definition, and every planned cell receives the frozen values.
4. Preview execution uses an explicit Preview Attempt mode and creates a
   Preview asset association before terminal success.
5. Preview bytes are served through the managed History asset endpoint, and a
   missing Original does not erase a valid Preview.
6. Original failure after Preview success is represented as a failed Original
   Attempt while preserving the Preview and showing a truthful failure state.
7. Generate Original creates a new `original` Attempt under the same
   Generation, or the same Experiment cell Generation, without changing the
   immutable request snapshot or prior Attempts.
8. Generate Original does not re-resolve mutable Workflow, Preset, mapping, or
   current Settings state.
9. Original asset association completes before terminal success. Duplicate
   terminal events and stale attempt writes remain rejected.
10. Cancellation, retry, and resume preserve current-attempt identity and do
    not fabricate remote cancellation success.
11. Zero-output, sparse, failed, interrupted, and missing-asset detail records
    render without a frontend exception.
12. Existing Original/default output behavior remains unchanged when Preview is
    OFF.

### Required E6 evidence

The minimum non-duplicative evidence should be:

- Python model/repository/writer/route tests for attempts, assets, snapshots,
  ordering, idempotency, and status derivation.
- Node unit tests for request option capture, Experiment definition freeze,
  repository action results, and sparse detail rendering.
- Fake Playwright tests using real `web/` modules for Preview-only, Preview plus
  failed Original, same-Generation Original replay, cancellation, and visual
  empty/sparse detail states.
- A direct managed-asset assertion that checks the expected HTTP status and
  bytes for Preview and Original references.

Current E6 status: **not runnable as an implementation gate**. The current
frontend deliberately disables Generate Original
(`web/studio-history-v2-experiment.js:197-224,640-650`), the repository bridge
returns unavailable for `generateOriginal`
(`web/history-v2-repository.js:422-443`), and Preview defaults are defined in
Settings without being attached to requests
(`web/studio-settings.js:22-35`).

## E7 Minimal Live Proof Boundary

E7 must remain blocked until E6 is green. It is not a replacement for
deterministic coverage and must not be used to discover basic contract bugs.

The smallest credible live proof, after explicit approval for deployment and
GPU use, is:

1. Submit one Preview-enabled Single request with a unique request identity.
   Capture the accepted request options, the durable Generation/Preview
   Attempt, the managed asset URL response, and the terminal ordering.
2. From that History record, request Generate Original using the same immutable
   snapshot. Verify same Generation identity, a new Original Attempt, retained
   Preview asset, served Original bytes, and terminal success only after asset
   association.
3. If the implementation includes an intentional Original failure injection,
   run one controlled failure and verify Preview retention plus truthful
   Original failure. Otherwise this remains a deterministic E6-only case.

E7 must record deployment identity, request/Generation/Attempt IDs, asset IDs,
HTTP status and MIME type, and the final History projection. It must not rely
on a screenshot alone. No E7 proof was performed in this audit.

## Ownership And Merge-Conflict Buckets

No later-write ownership was changed. Future implementation should use these
boundaries:

| Concern | Primary owner files |
|---|---|
| Settings persistence and Preview controls | `web/studio-settings.js`, `web/studio-output-preferences.js`, `/comfymodal/config` handlers in `__init__.py` |
| Single request snapshot | `web/studio-playground.js`, `web/studio-workflow-run.js`, backend request metadata path |
| Experiment definition and freeze | `web/studio-experiment-mode.js`, `experiment_modern_routes.py`, `experiment_modern_plan.py` |
| Preview codec/direct output | `comfyapp.py`, `comfymodal_runtime/modal_app.py`, output delivery/converter seams |
| Attempts, snapshots, assets, status | `history_v2_models.py`, `history_v2_repository.py`, `history_v2_writer.py`, `history_v2_routes.py` |
| Generate Original replay service | New route/service behind `history_v2_routes.py`, using canonical execution and existing snapshot fields |
| History detail and cell actions | `web/history-v2-repository.js`, `web/studio-history-v2-detail.js`, `web/studio-history-v2-experiment.js` |
| Deterministic evidence | `tests/browser/fake/`, `tests/test_history_v2*.py`, modern Experiment unit tests, `tests/run_studio_tests.py` |

Highest conflict-risk buckets in the current dirty worktree:

- Already-modified production/runtime files, including `__init__.py`,
  `comfyapp.py`, runtime modules, and several Studio frontend modules.
- Untracked History V2, modern Experiment, workflow, and fake-backend modules
  that are part of the current Phase E work.
- Existing test additions and artifacts from prior Phase D/V2 work.
- Existing Phase E audit documents and the stale `STUDIO_TEST_GATE.md`.

This audit adds only its own Markdown file. It does not reconcile or overwrite
any of those buckets.

## Final Classification

### VERIFIED CURRENT BEHAVIOR

- The explicit Studio gate is allowlisted and green in the observed run:
  Python 1471, Node 11 files, and fake Playwright 94 tests.
- The fake browser harness serves the real Studio frontend modules.
- History V2 model, route, repository, pagination, status, and modern
  Experiment deterministic tests are present and passing in the targeted runs.
- Modern Experiment acceptance is server-owned and durable before dispatch.
- Current stale failures are outside the explicit gate and reference old
  production symbols/contracts.

### RECOMMENDED PHASE-E CONTRACT

- Keep `tests/run_studio_tests.py --fake` as the baseline deterministic gate.
- Update gate documentation counts in a separate controlled write.
- Add E6 Preview/Original tests only when the implementation carries immutable
  request intent through execution, asset persistence, and History projection.
- Require same-Generation/new-Attempt semantics for Generate Original.
- Keep Preview/Original cases in the fake harness only as shape/state tests
  until production implementation proof exists.
- Require E7 live proof to capture durable IDs, asset responses, and terminal
  ordering rather than screenshots alone.

### UNKNOWN / NEEDS IMPLEMENTATION PROOF

- Production Preview request propagation, direct-sink semantics, codec timing,
  and History asset association.
- Production Generate Original route, replay service, and same-Generation
  Attempt behavior.
- Sparse/empty Generation Detail behavior until nullable section append paths
  are covered by a browser or Node test.
- Live remote asset serving and deployment identity for the proposed E7 proof.

## Audit Boundary

The original E5 audit was read-only. The implementation follow-up below is
limited to test-owned files, fake-backend state, gate wiring, and this audit.
No production code, `web/` code, runtime code, deployment file, snapshot,
stale test, live service, or GPU-backed path was changed.

## E5 IMPLEMENTATION FOLLOW-UP A

Date: 2026-08-17
Owner: deterministic test and fake-harness lane
Verdict: **E5A deterministic harness ready; E6 NOT GREEN**

### New Fixtures, Scenarios, And Tests

Added pure Python contract builders in `tests/phase_e_fixtures.py` for:

- Preview-only Generation with a `preview` Attempt and Preview asset;
- Preview plus failed Original;
- Preview plus successful Original;
- successful Original followed by failed Original rerender;
- remote-backed Original represented only through a managed History URL;
- sparse failed/interrupted records;
- replay-complete and irreproducible request snapshots;
- frozen modern Experiment definition and the future Generate Original
  response placeholder.

Added Python assertions in:

- `tests/test_phase_e_contract.py`;
- `tests/test_phase_e_fake_parity.py`.

The Python module includes two explicitly skipped tests for production Preview
request propagation and Generate Original replay. They are pending evidence,
not weakened assertions.

Added `tests/studio_phase_e_contract_unit.mjs`, which runs the real History V2
frontend normalizer against Preview-only, failed Original, successful Original,
managed remote URL, one-definition Experiment, and placeholder response shapes.
It does not call or implement a Generate Original endpoint.

Added `tests/browser/fake/studio-fake-phase-e.spec.mjs` with scenarios A-G:

- Preview-only state and managed Preview bytes;
- failed Original with retained Preview and truthful failure;
- successful Original with both assets retained;
- failed rerender with earlier Original still available;
- remote-backed Original served through `/comfymodal/history-v2/assets/{id}`;
- sparse failed/interrupted API shapes;
- one modern Experiment definition with frozen Preview options, stable cell
  Generation IDs, and no client `cells` or `concurrency` field.

The sparse detail overlay test is marked `fixme` pending the known E4 nullable
section append fix. The API shape test for the same records runs and passes.

### Fake API Contract Shapes

The Phase-E fake seed is selected with
`POST /__comfymodal_test/history-seed` and scenario
`history_v2_phase_e`. It uses the existing production-shaped History V2 routes:

- `GET /comfymodal/history-v2/generations/{id}` returns the normal `item`
  detail envelope;
- each attempt exposes `run_id`, `mode`, `status`, timestamps, `duration_ms`,
  `error`, and `timing`;
- each output exposes `thumb_url`, `preview_url`, `original_url`, and
  `original_failed`;
- asset bytes are fetched only through the managed History URL and return
  deterministic `image/png` bytes;
- remote producer origin is held only in fake internal state as `modal://...`
  and never appears in browser-facing JSON.

The modern Experiment test sends exactly `{experiment_id, name, definition}`.
Preview options are frozen in `definition.modal_options` as
`{enabled: true, codec: "webp", quality: 70}`. Matrix cells are server-derived,
and global concurrency remains the backend policy `6`, not a request field.

The eventual Generate Original response is defined only as a test contract:
`status`, `generation_id`, `run_id`, `purpose`, `mode`, `attempt_status`, and
`reused`. No fake endpoint or frontend consumer was added.

### Fake Harness Changes

`tests/browser/fake/scenarios.mjs` adds the `history_v2_phase_e` seed.
`tests/browser/fake/fake-backend.mjs` adds exact custom Attempt support, an
internal remote asset-origin marker, the Phase-E History V2 records, and a
test-control diagnostic for frozen modern `modal_options`. Existing browser
wire shapes remain unchanged; raw producer origins are not exposed through
the application routes.

### Gate Documentation And Wiring

`tests/run_studio_tests.py` now includes the two Python Phase-E modules and the
Node Phase-E contract unit in its explicit allowlist. No existing lane was
removed or broadened.

`STUDIO_TEST_GATE.md` no longer claims the stale Python `1419`, Node `6`, or
fake Playwright `52` counts. It records the E5 baseline of Python `1471`, Node
`11`, and fake Playwright `94`, plus the observed E5A totals: Python `1484`
with `2` skips, Node `12`, and fake Playwright `102` tests with `1` pending
sparse-detail test. The executable runner and Playwright config remain the
authority as counts evolve.

### Tests Run And Results

All modified lanes passed:

```text
python -m unittest -q tests.test_phase_e_contract tests.test_phase_e_fake_parity
Ran 13 tests ... OK (skipped=2)

node tests/studio_phase_e_contract_unit.mjs
6 contract checks passed

npx playwright test --config=playwright.fake.config.mjs studio-fake-phase-e.spec.mjs
7 passed, 1 skipped

npx playwright test --config=playwright.fake.config.mjs --list
Total: 102 tests in 13 files

python tests/run_studio_tests.py --fake
Python: 1484 run, 0 failures, 0 errors, 2 skips
Node: 12 files passed
Fake Playwright: passed
ALL STUDIO LANES GREEN
```

The full gate emitted existing diagnostic logs from unrelated test fixtures,
including runtime failure-path messages and host-reconciliation notices, but
returned zero with no failures or errors. No cross-agent production failure
was observed in the authoritative gate.

### Pending Tests Waiting On Production

- Preview settings must be copied into a Single request snapshot and modern
  Experiment definition.
- Preview execution must persist an explicit `preview` Attempt and Preview
  asset before terminal success.
- Generate Original must create a same-Generation, new `original` Attempt and
  replay the exact immutable saved ExecutionPlan.
- Failed Original must preserve Preview and any earlier successful Original.
- Remote `modal://` assets need production writer and managed-route proof.
- Sparse Generation Detail must render without `appendChild(null)`; the fake
  UI test is intentionally pending until E4 fixes that production frontend.

### E6 Readiness

E6 remains **NOT GREEN**. E5A establishes deterministic contract fixtures,
production-shaped fake HTTP state, real frontend normalization coverage, and a
repeatable pending-test boundary. It does not establish production writer
persistence, SQLite transactions, codec behavior, remote Modal output, or
Generate Original replay. E7 was not performed and remains outside this batch.

## E5 Implementation Follow-Up B - Wave-2 Harness

Date: 2026-08-17
Owner: deterministic test and fake-harness lane
Verdict: **Wave-2 deterministic coverage added; E6 NOT GREEN**

### Wave-2 Scope

This follow-up extends the E5A fake and fixture layer for logical output
identity, Preview variant metadata, featured derivative selection, remote
Original-only presentation, replay-core snapshots, and History detail behavior.
It does not add a fake Generate Original route and does not claim that fake
state proves the production writer, SQLite transactions, codec execution, or
remote Modal reads.

### Logical-Output Fixtures

`tests/phase_e_wave2_fixtures.py` adds pure builders for:

- one logical output with Thumbnail, Preview, two successful Original assets,
  and three Attempt provenance IDs;
- Preview followed by failed Original and successful retry;
- two logical output keys whose `output_count` is `2` despite five derivative
  assets;
- featured Thumbnail, featured Preview, and featured older Original cases;
- Original-only remote output with no Thumbnail or Preview and no false
  `original_failed` flag;
- replay-complete Single and Experiment-cell snapshots, missing raw hash,
  irreproducible legacy snapshot, exact plan round-trip, and output-intent-only
  delta;
- the future Generate Original response shape, still a placeholder only.

The expected additive output projection is one output object per logical key:

```text
logical_output_key, asset_id, thumb_url, preview_url, original_url,
original_urls, original_failed, attempt_ids, asset_provenance,
preview_codec, preview_quality
```

`asset_provenance` retains derivative type and Attempt identity while
`original_url` selects the newest successful Original. This is a
**RECOMMENDED PHASE-E CONTRACT**, not a claim that the current production
History route already emits every field.

### Fake API And Seed

`tests/browser/fake/scenarios.mjs` adds the `history_v2_phase_e_wave2` seed.
`tests/browser/fake/fake-backend.mjs` projects the seed through the existing
History V2 feed/detail and managed asset routes rather than adding a parallel
test endpoint. The fake now supports multiple Original asset IDs under one
logical output, derivative provenance, featured-asset matching across
Thumbnail/Preview/Original IDs, optional Preview `codec`/`quality` Attempt
fields, and frozen Experiment `modal_options` with stable cell Generation IDs.

The browser-facing fake never emits the internal `modal://` producer origin.
Remote-only Original bytes still use deterministic fake PNG data and the
managed `/comfymodal/history-v2/assets/{id}` URL. This preserves transport/UI
coverage while making clear that `preview_codec: webp` metadata is not proof of
actual WebP encoding or compression quality.

### New Tests

`tests/test_phase_e_wave2_contract.py` covers logical-output count, derivative
provenance, Preview mode/WebP/70 metadata, failed Original retry retention,
featured derivative identity, remote-only projection, replay completeness,
missing-hash fail-closed behavior, and the future route placeholder. The one
same-Generation/new-Attempt production assertion is explicitly skipped until
E3B2 provides the production route/service.

`tests/studio_phase_e_wave2_unit.mjs` runs against the real
`web/history-v2-repository.js` adapter and covers:

- one versus two logical outputs;
- Thumbnail then Preview fallback;
- Original-only feed placeholder with no automatic full-Original URL;
- featured derivative selection by logical output index;
- Preview Attempt and WebP/70 wire metadata;
- future Generate Original response keys.

`tests/browser/fake/studio-fake-phase-e-wave2.spec.mjs` uses the real Studio
History UI against the fake HTTP server and covers:

- one logical output with multiple Attempts/assets;
- `output_count` of two for two logical keys;
- Preview Attempt mode and Preview metadata;
- failed Original followed by retained successful retry;
- featured Thumbnail, Preview, and older Original selection;
- remote Original-only feed placeholder with no automatic asset request and
  explicit `View Original` load;
- Preview badge presentation;
- frozen Experiment Preview options and stable cell Generation IDs.

The new fake spec passes all 8 tests. The existing E5A sparse-detail `fixme`
remains separately pending; it was not weakened or removed.

### Gate Wiring And Counts

`tests/run_studio_tests.py` adds `tests.test_phase_e_wave2_contract` and
`tests/studio_phase_e_wave2_unit.mjs` to the explicit allowlists. No existing
lane was removed and no broad discovery was introduced. `STUDIO_TEST_GATE.md`
now documents the Wave-2 seed/spec, current discovery count, explicit
Original-load behavior, and the fact that the full gate is not currently green.

### Verification

Focused commands and observed results:

```text
python -m unittest -q tests.test_phase_e_wave2_contract
Ran 11 tests ... OK (skipped=1)

node tests/studio_phase_e_wave2_unit.mjs
All Wave-2 contract sections passed

npx playwright test --config=playwright.fake.config.mjs studio-fake-phase-e-wave2.spec.mjs
8 passed

npx playwright test --config=playwright.fake.config.mjs --list
Total: 110 tests in 14 files
```

The full requested command was also run:

```text
python tests/run_studio_tests.py --fake
Python: 1495 run, 0 failures, 0 errors, 3 skips
Node: 13 files passed
Fake Playwright: 107 passed, 1 skipped, 2 failed
Gate result: FAILED LANES: fake-playwright
```

Failure classification is:

| Failure | Classification | Evidence and handling |
|---|---|---|
| `tests/browser/fake/studio-fake-phase-e.spec.mjs:128` expects eager `img[alt="Original"]` | D. TRANSIENT FILE BEING EDITED CONCURRENTLY | Current `web/studio-history-v2-detail.js:361-391` deliberately renders an Original availability placeholder and loads it only after `View Original`; the existing E5A assertion still expects eager loading. No existing spec was changed in this lane. |
| `tests/browser/fake/studio-fake-visual.spec.mjs:94` history screenshot mismatch | D. TRANSIENT FILE BEING EDITED CONCURRENTLY | The History UI is concurrently changing and the checked-in visual baseline was not regenerated or weakened by this lane. The focused Wave-2 visual-independent spec passes. |

No A. E5 harness bug was observed in the new Python, Node, fake backend, or
Wave-2 Playwright coverage. No C. genuine production regression was declared
from these two failures because both are current-worktree ownership/baseline
reconciliation issues. The full gate must be rerun after the owning frontend
and existing fake-test lanes reconcile the explicit Original-load contract and
visual baseline.

### Pending Generate Original Case

The pending route contract remains exactly:

```text
status, generation_id, run_id, purpose=original, mode=original,
attempt_status, reused
```

It is not exposed by `fake-server.mjs`, not consumed by the frontend, and not
counted as production-green. Production proof still requires same Generation,
new Attempt, unchanged immutable ExecutionPlan/request snapshot, retained
Preview, newest successful Original preference, and truthful failed retry.

### E6 Readiness

E6 remains **NOT GREEN**. The Wave-2 harness provides deterministic evidence
for the intended logical-output and History presentation contract, but the
following blockers remain:

- production Preview mode/type/codec/quality must persist through execution and
  asset association;
- production output grouping must collapse Thumbnail/Preview/Original and
  retries to stable logical output identity with correct `output_count`;
- production featured derivative mapping must be deterministic for every
  derivative type;
- production Generate Original route/service must create a new Original
  Attempt under the same Generation and replay the exact saved plan;
- production remote `modal://` adoption and managed asset serving need route,
  writer, and failure-semantics proof;
- the existing E5A explicit Original-load assertion and visual baseline need
  owning-lane reconciliation, and sparse detail remains pending;
- the full `python tests/run_studio_tests.py --fake` command must return
  `ALL STUDIO LANES GREEN` after those reconciliations.

E7 was not performed. No deployment, live generation, GPU operation, or commit
was performed in this follow-up.
