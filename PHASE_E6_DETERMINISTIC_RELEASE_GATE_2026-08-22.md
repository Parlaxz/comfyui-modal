# Phase E6 — Deterministic Release Gate (2026-08-22)

Batch: E5 Implementation Follow-Up D2 (final E6 reconciliation).
Lane: tests / harness / documentation only.

## Executive verdict

**E6 GREEN — deterministic Phase-E gate complete.**

The authoritative Studio deterministic wrapper exits zero with every lane
green and no Phase-E implementation-pending skip or fixme remaining:

```text
python tests/run_studio_tests.py --fake
STUDIO GATE SUMMARY
  python             run=1609  fail=0    error=0    skip=0
  node-unit          run=16    fail=0    error=0    skip=0
  fake-playwright    run=1     fail=0    error=0    skip=0
ALL STUDIO LANES GREEN            (exit code 0)
```

Fake Playwright detail (`npm run test:fake`, config
`playwright.fake.config.mjs`): **126 discovered in 15 files, 126 passed,
0 skipped/fixme, 0 failed** (2.6 min).

## Proven architecture

- **Preview semantics.** Preview is globally default-OFF
  (`PREVIEW_DEFAULTS = {enabled: False, codec: webp, quality: 70}`);
  enabling it freezes an immutable semantic output mode whose accepted
  options are `format=webp_lossy`, `quality=70`,
  `webp_lossless_compression=fast` (effort vocabulary `fast→method 0`,
  `balanced→4`, `max→6`) through `ExecutionOptions`, canonical round-trips,
  Single capture, and Experiment definition/cell plans.
- **Logical outputs.** Canonical identity
  `node:<node_id>:slot:<output_key>:item:<output_index>`; Preview +
  Thumbnail + Original variants of one key are ONE logical output;
  retries/rerenders never inflate it; `output_count` counts groups; featured
  Thumbnail/Preview/older Original resolve through group membership and stay
  stable when the winning Original changes; newest usable Original wins; a
  later failed rerender retains the prior success; legacy unkeyed rows stay
  readable without fabricating identities.
- **Generate Original.** `POST /comfymodal/history-v2/generations/{id}/original`
  over the SAME Generation from the immutable snapshot: new append-only
  Original Attempt only when required; active reuse serializes duplicates;
  successful reuse avoids execution by default; busy/irreproducible are
  machine-readable refusals with zero writes; canonical
  `ExecutionPlan.from_dict` replay through the canonical execution engine
  (`canonical_execution.execute_plan`); raw snapshot validated before any
  deserialization/write; no mutable Workflow/Preset/Settings reconstruction.
- **Retry.** Dedicated bodyless
  `POST .../generations/{id}/original/retry`: only a failed newest Original
  Attempt is retryable; appends ONE new Attempt under the SAME Generation;
  failed Attempt, Preview, and prior assets remain retained; ordinary
  `/original` on failed-only state returns `retry_required` and the frontend
  never auto-retries.
- **Rerender.** Generate Again is the ONLY rerender path:
  ordinary `/original` with exactly `{rerender: true}`; newest success wins;
  earlier successes retained.
- **History presentation.** Feed/grid/detail never eager-load full Original
  bytes; only explicit `View Original` fetches them; remote `modal://`
  references project URI-aware and are not falsely failed; sparse failed and
  interrupted records render truthful terminal/error states (with the Failed
  toggle activated intentionally where the default filter hides them).
- **Experiment parity.** Cells carry their own `generationId`; cell actions
  use the same Generation-scoped routes as Single; one dispatch per action,
  no browser fanout, no second experiment engine.
- **Terminal ordering.** Output attachment precedes completed; terminal
  statuses drive polling stops; required terminal/error states remain
  visible.

## Acceptance matrix

Deterministic items 1–44: PASS = proven by current executable evidence in
the gate (or its documented focused companion runs). Items 45–49 are
LIVE-E7-ONLY and do not block E6.

| # | Item | Verdict | Evidence |
|---|---|---|---|
| 1 | Preview global default OFF | PASS | `test_phase_e_contract.test_preview_defaults_are_global_and_distinct_from_thumbnail`; `ExecutionOptions` default mode `original` |
| 2 | Preview ON freezes immutable semantic output mode | PASS | `test_e2d_preview_method_contract.PreviewFreezeContractTests`; round-trip stability |
| 3 | Preview codec freezes WebP lossy | PASS | `conversion["format"] == "webp_lossy"` (gate module + `test_e2_preview_effort`) |
| 4 | Preview quality freezes 70 | PASS | same modules |
| 5 | Encoder effort freezes fast / method 0 | PASS | `WEBP_EFFORT_METHODS` fast→0; fallback converter method 0 (gate); direct tensor sink method 0 (`test_e2_preview_effort`, focused) |
| 6 | Preview settings captured into Single before execution | PASS | `studio_phase_e_preview_settings_unit.mjs`; `test_phase_e_contract` |
| 7 | Preview settings freeze into Experiment definition/cell plans | PASS | `ExperimentPlanRoundTripTests` (gate module); preview-settings unit |
| 8 | Preview-mode Attempt persists | PASS | `PhaseEE2CPreviewHandoffTests` (cross-layer writer handoff) |
| 9 | Preview Asset type persists | PASS | same |
| 10 | Preview-only creates no managed Original | PASS | same |
| 11 | Thumbnail derivative persists under same logical key | PASS | same; `E2CDescriptorHandoffTests` (E1C integration) |
| 12 | Required Preview/Original association before completed | PASS | `PhaseEE2CPreviewHandoffTests` |
| 13 | Stable canonical logical-output identity persists | PASS | `test_phase_e_logical_output_integration` (MultipleOutputs, keyed metadata derivation) |
| 14 | Variants/retries remain one logical output | PASS | `ProducerVariantGroupingTests`, retry-grouping test |
| 15 | `output_count` counts logical groups | PASS | E1C integration projections (1/2/3-group cases) |
| 16 | Featured derivative maps to logical group | PASS | `FeaturedDerivativeMembershipTests` |
| 17 | Newest usable Original wins | PASS | `two_successful_originals_newest_wins_via_writer`; projection newest-wins test |
| 18 | Later failed rerender retains prior successful Original | PASS | `later_failed_rerender_retains_earlier_winner`; fake spec failed-rerender case |
| 19 | Remote `modal://` URI-aware in deterministic projection, not falsely failed | PASS | `RemoteKeyedOriginalTests`; `test_modal_original_is_structurally_available_without_fetch`; Wave-2 remote browser case |
| 20 | Generate Original uses same Generation | PASS | fake spec create case (feed count 1, attempts append); `test_history_v2_generate_original` |
| 21 | New Original Attempt only when required | PASS | decision policy suites + fake create/reuse matrix |
| 22 | Duplicate suppression/reuse works | PASS | active-reuse serialization (fake + backend) |
| 23 | Successful Original default reuse avoids execution | PASS | successful-reuse cases (fake + backend) |
| 24 | Immutable replay validates raw snapshot before deserialization/write | PASS | `test_history_v2_replay_core` |
| 25 | Replay does not resolve mutable Workflow/Preset/Settings | PASS | `test_history_v2_replay_core` / `test_history_v2_generate_original` |
| 26 | Original replay uses canonical execution path | PASS | `executor == "canonical_execution.execute_plan"` asserted (fake + backend) |
| 27 | Failed-only ordinary Generate returns `retry_required` | PASS | fake API case; backend suite; Node unit §5 |
| 28 | Explicit Retry uses `/original/retry` | PASS | rewritten browser case (exactly one POST, zero ordinary); Node unit §2/§8 |
| 29 | Retry creates a new append-only Original Attempt | PASS | durable-state assertions (fake + backend) |
| 30 | Retry keeps same Generation | PASS | generation id + single feed record assertions; Node §8 |
| 31 | Failed Attempt remains retained | PASS | attempts-map assertions after success |
| 32 | Retry never retries Preview as Original | PASS | retry route refusals (`retry_not_available`/`generation_busy`); purpose always `original` |
| 33 | Generate Again uses explicit rerender semantics | PASS | UI interception case: body exactly `{rerender: true}`, never `/original/retry` |
| 34 | Preview remains after Original failure | PASS | execution-failure fake case; E1C failure parity |
| 35 | Previous successful Original remains after later rerender failure | PASS | failed-rerender fake case; E1C retention test |
| 36 | Single and Experiment cell Generate/Retry parity | PASS | E1C `ExperimentParityTests`; cell browser case; Node §8/§15 |
| 37 | No browser fanout for Experiment Original actions | PASS | interception count == 1 per action; single call sites (Node §15) |
| 38 | Original is never eager-loaded | PASS | UI cases for generate/retry/rerender success; Node §12; Wave-2 remote case |
| 39 | Explicit `View Original` remains available | PASS | View Original clicks render Original in all lifecycle cases |
| 40 | Sparse failed Generation detail renders | PASS | `studio-fake-phase-e.spec.mjs` F2 (Failed toggle enabled intentionally) |
| 41 | Sparse interrupted Generation detail renders | PASS | F3 |
| 42 | Required terminal/error states remain visible | PASS | status chips + error text assertions (F2/F3, history-v2 spec) |
| 43 | Deterministic wrapper exits zero | PASS | observed exit code 0 (counts above) |
| 44 | No Phase-E acceptance test skipped/fixme pending implementation | PASS | wrapper skips=0; fake lane 0 fixme/skip; historical E1B-pending skip retired executable |

LIVE-E7-ONLY items (required for Phase-E live closure; NOT E6 blockers):

| # | Item | Verdict |
|---|---|---|
| 45 | Actual remote Modal producer writes a real `modal://` Preview | LIVE-E7-ONLY |
| 46 | Actual remote Modal `modal://` Original replay/fetch works | LIVE-E7-ONLY |
| 47 | Actual Modal/container libwebp uses effective method 0 | LIVE-E7-ONLY |
| 48 | Actual live Preview `output_codec_ms` | LIVE-E7-ONLY |
| 49 | Actual live Preview → Generate Original same-Generation sequence | LIVE-E7-ONLY |

## Test results (exact commands and counts)

Focused pre-gate runs (all green):

```text
python -m unittest tests.test_phase_e_logical_output_integration   # 16 passed (~2.5s)
tests.test_phase_e_contract.PhaseEE2CPreviewHandoffTests           # 1 passed
python -m unittest tests.test_history_v2_replay_core
       tests.test_history_v2_generate_original                     # 46 passed
python -m unittest tests.test_e2d_preview_method_contract          # 9 passed (~0.16s)
python -m unittest tests.test_e2_preview_effort                    # 15 passed (~24s, focused diagnostic only)
python -m unittest tests.test_phase_e_history_projection           # 10 passed, 0 skips
node tests/studio_phase_e4c_generate_original_unit.mjs             # pass
node tests/studio_phase_e4d_original_retry_unit.mjs                # pass
npx playwright test --config playwright.fake.config.mjs
    studio-fake-phase-e-original.spec.mjs                          # 15 passed
npx playwright test --config playwright.fake.config.mjs
    studio-fake-phase-e.spec.mjs                                   # 9 passed
```

Authoritative wrapper:

```text
python tests/run_studio_tests.py --fake
Python lane:        1609 run, 0 failures, 0 errors, 0 skips
Node unit lane:     16 files, 16 passed, 0 failed
Fake Playwright:    126 discovered (15 files), 126 passed,
                    0 skipped/fixme, 0 failed
Wrapper exit code:  0 — ALL STUDIO LANES GREEN
```

Delta vs D1 baseline (1584 Python / 125 Playwright): +25 Python from the two
newly allowlisted modules (E1C integration 16, E2D contract 9); +1 Playwright
(the former retry fixme now executes) +1 new rerender-distinction case =
126. The retired E1B skip lives outside the allowlist and does not change
wrapper counts.

Documented non-blockers outside the allowlist: intentionally-RED TDD suites
(`test_studio_timing_integration` RED classes, `test_studio_live_progress`),
runtime-owned browser specs, bridge-side `test_api_prompt_validator`, and
the torch/comfyapp-gated seam suites (`test_e2c_history_handoff.py`,
`test_e2_preview_effort.py`) kept outside the gate for determinism/runtime
by documented decision.

## Remaining E7 live-only proofs

Clearly separated from E6; their absence never forces deterministic red:

1. Real Modal producer writes a real `modal://` Preview asset.
2. Real remote `modal://` Original replay/fetch end to end.
3. Container libwebp actually applies effective method 0 for the fast
   effort remotely.
4. Live Preview `output_codec_ms` telemetry.
5. Live Preview → Generate Original on THAT SAME Generation (new Original
   Attempt, immutable replay, retained Preview, explicit-only Original
   fetch).

Recommended later E7 shape (DO NOT RUN as part of E6): one Preview-enabled
Single → inspect → Generate Original on that same Generation → inspect;
Experiment live only if a genuinely Experiment-specific question remains.

## No-live statement

E6 did NOT deploy, did NOT run Modal, did NOT use any GPU, and did NOT
perform any live generation. All evidence above is deterministic and local.
No commit or push was made by this batch.

## Files modified by this lane (E5D2)

- `tests/browser/fake/studio-fake-phase-e-original.spec.mjs` (stale Retry
  assertion replaced with the E4D contract; fixme activated; Generate Again
  interception case added; same-Generation proof strengthened)
- `tests/test_phase_e_history_projection.py` (historical E1B-pending skip
  retired into an executable grouping assertion)
- `tests/test_e2d_preview_method_contract.py` (NEW)
- `tests/run_studio_tests.py` (allowlist += E1C integration, E2D contract)
- `STUDIO_TEST_GATE.md` (final E6 status; stale blockers superseded with
  history preserved)
- `PHASE_E5_TEST_REGRESSION_GATE_AUDIT_2026-08-17.md` (D2 section appended)
- `PHASE_E6_DETERMINISTIC_RELEASE_GATE_2026-08-22.md` (NEW, this file)

All other dirty worktree content belongs to other lanes (V2/E40/runtime and
prior Phase-E batches) and was left untouched.
