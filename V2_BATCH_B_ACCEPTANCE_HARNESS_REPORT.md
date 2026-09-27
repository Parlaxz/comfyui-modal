# V2 Batch-B Acceptance Harness Report (B4)

Status: HARNESS READY FOR INTEGRATION (pending concurrent runtime-lane field emission)
Date: 2026-08-14
Mode: fixture/mock validation only — **no Modal execution, no deploy, no commit, no generation**

## 1. Purpose

Prepare ONE strict Batch-B integrated RUN 1 validator for the structural/stage
acceptance gates: Batch-A preservation, the runtime-state reload skip guard,
snapshot allocator hygiene, the snapshot manifest, the stage-13 decomposition
reconciliation, and host telemetry (Tier A / Tier B split).  The harness adds
no optimization, alters no benchmark timing semantics, and never judges
success from TOTAL WALL — a slow or weird validation run is acceptable when
the requested stage invariants are correct.

Revision (B4 follow-up) fixes four acceptance-contract problems found during
review: (1) models-volume evidence was falsely satisfying the runtime-state
gate; (2) legitimately slow H2D transfers were failing on forensic events;
(3) the <= 20 ms cap was applied to the TOTAL probe wall instead of Tier A
only; (4) stage-13 absence was never strict once Batch B is integrated.

## 2. Deliverables

| File | Role |
|---|---|
| `tools/batch_b_acceptance.py` (NEW, revised) | Pure, offline Batch-B validator: run-artifact dict in → `BatchBAcceptanceResult` out. Stdlib only; never imports repo runtime, never contacts Modal. Reuses `tools/batch_a_acceptance.validate_batch_a` + its helpers (never duplicated). |
| `tools/benchmark_v2_direct.py` (EDITED, additive) | `--batch-b-acceptance` flag + `COMFYMODAL_V2_BATCH_B_ACCEPTANCE=1` env alias; validates the RUN-1 artifact, prints the BATCH B ACCEPTANCE block, raises (non-zero exit) on FAIL. No hidden retry, no extra sample, no automatic second run. |
| `tests/test_batch_b_acceptance.py` (NEW, revised) | 45 unittest cases: all-pass + every required failure mode, fixture-driven, no Modal. |
| `V2_BATCH_B_ACCEPTANCE_HARNESS_REPORT.md` (this file) | Required report. |

Runtime production files were NOT modified: `modal_app.py`, `model_preload.py`,
`runtime_bootstrap.py`, `comfyapp.py`, `runtime_executor.py`,
`snapshot_build_manifest.py`, `resource_telemetry.py`,
`host_hardware_telemetry.py`, `__init__.py`, `*.bat`, `comfymodal_runtime/*`.

## 3. RUN 1 gates and their data sources

Every gate prefers the exact Batch-B field name (emitted by the concurrent
Batch-B runtime lanes) and falls back to the documented current-checkout
equivalents.  **A gate never fakes a pass**: when neither the exact field nor
any fallback exists it FAILS with an explicit "not observable" detail (or
reports NOT READY for the lane-readiness gates below).

### 3.1 Batch-A preserved (delegated, telemetry checks re-evaluated)

`validate_batch_a(artifact)` must pass every invariant EXCEPT the two
host-telemetry checks (`host_telemetry_overhead`, `host_slow_forensic`), which
are re-evaluated under the Batch-B Tier-A/Tier-B telemetry and slow-H2D
forensic contract (§3.6).  Preserved as-is: Fresh:YES, STATUS OK,
reconciliation <= 50 ms, G1 (plan-receipt schedule present, exactly 1 UNET
read / 1 bind / 1 H2D, later-scheduler no-op, identity match), models-volume
`skipped_generation_match` with 0 remote reload calls, positioned node
timestamps, valid terminal cleanup stamps, subprocess forensics.

### 3.2 Runtime-state guard — `COMFYMODAL_V2_BATCH_B_EXPECT_RUNTIME_STATE_SKIP`

**Models-volume evidence is NEVER runtime-state evidence.**  The Batch-A
models guard fields (`models_reload_decision`, `reload_models_invoked`,
`reload_models_ms`, `reload_models_reason`, `reload_models_start`,
`callback_called`, `models_ms`, `models_reload_check_ms`) describe the MODELS
volume lane and can report a clean skip while the runtime-state reload still
executes normally.  They are deliberately removed from the runtime-state
fallback chain; a runtime-state PASS can never be fabricated from them.

Runtime-state evidence may come ONLY from fields/events that unambiguously
describe runtime state:

| Required | Exact field (lane-emitted) | Fallback (current checkout) | Strict rule |
|---|---|---|---|
| Decision | `runtime_state_reload_decision` / `runtime_state_decision` | restore-decomposition fields explicitly named for runtime_state (`runtime_state_reload_decision` / `runtime_state_decision`) or a `runtime_state_reload_decision`-named event | `== "skipped_generation_match"` |
| Invoked | `runtime_state_reload_invoked` / `runtime_state_invoked` | restore-decomposition `runtime_state_reload_invoked`; `reload_runtime_state_start`/`end` event presence (=> True); inference from a runtime-state `skipped_generation_match` decision only | `== false` |
| Reload ms | `runtime_state_reload_ms` / `reload_runtime_state_ms` | `_restore_timing.runtime_state_ms` / restore-decomposition `runtime_state_ms` (existing production key) | `0` or local-check-only: `invoked==false` + generation check present + `ms <= LOCAL_CHECK_BUDGET_MS` (10 ms) |
| Generation check | `runtime_state_generation_check` | `runtime_state_reload_check_ms` / `runtime_state_check_ms` (runtime-state-named only) | present |
| Local / no remote RPC | `runtime_state_reload_remote_calls` | restore-decomposition `runtime_state_reload_remote_calls`; runtime-state reload events | no remote decision RPC observable |

Lane readiness: when NO runtime-state-specific observables exist the lane is
NOT READY; with the expectation ON that is a FAIL ("expected runtime-state
skip missing").  With the expectation OFF the gate reports the observed
state / NOT READY and never fails merely because the optimization is
unavailable (the integration leaves the env expectation off).

Regression fixtures prove: (a) clean models skip fields alone can NOT satisfy
the runtime-state gate; (b) a real runtime-state reload
(`reload_runtime_state_ms=82` + `reload_runtime_state_start/end`) can NOT be
hidden by clean models fields — the runtime-state skip MUST NOT PASS.

### 3.3 Snapshot hygiene — `COMFYMODAL_V2_SNAPSHOT_ALLOCATOR_HYGIENE`

Requires exactly one `snapshot_capture_hygiene` record (key or event; aliases
`snapshot_allocator_hygiene` / `capture_hygiene` / `snapshot_hygiene`) with:

- `enabled == 1`
- before RSS measurement present, after RSS measurement present
- `hygiene_wall_ms` valid (numeric, >= 0)
- gc result present (`gc` / `gc_result`)
- malloc_trim status/result present (`malloc_trim` / `malloc_trim_status` /
  `malloc_trim_result`); an explicitly-recorded `"unavailable"` is accepted

RSS is a measurement experiment: `rss_before`, `rss_after`, `rss_delta` (and
`rss_anon_*` when available) are REPORTED, never gated — RSS is NOT required
to decrease.  Missing fields are never fabricated.  Flag ON + record missing
=> FAIL.  Flag OFF => not enforced.

### 3.4 Snapshot manifest — `COMFYMODAL_V2_SNAPSHOT_MANIFEST`

Requires a manifest status/result present (exact `snapshot_manifest` key or
event; status from `status` / `result` / `manifest_status` /
`manifest_result`).  Unavailable smaps/anonymous split is allowed when
explicitly recorded unavailable (`smaps_status=="unavailable"` /
`smaps_unavailable` / status text).  Fails when instrumentation silently
omits status.  Flag OFF => not enforced.

### 3.5 Stage-13 decomposition — strict under `COMFYMODAL_V2_BATCH_B_EXPECT_STAGE13`

Requires `output_stage13_breakdown` (or `stage13_breakdown` /
`stage_13_breakdown` / `stage13`, key or event) with:

- children nonnegative (numeric `ms` / `duration_ms` / `wall_ms` / `value`)
- `stage13_total` valid (numeric, >= 0)
- `sum(children)` reconciles the parent Stage 13 total within
  `COMFYMODAL_V2_BATCH_B_STAGE13_TOLERANCE_MS` (default 10 ms)
- largest child reported by name + ms

No performance win is required.  Readiness contract is EXPLICIT, not guessed
from file presence:

- `COMFYMODAL_V2_BATCH_B_EXPECT_STAGE13=1` (integration enables this — B2 is
  part of Batch B): missing decomposition => FAIL; present-but-malformed
  always FAILS; reconciliation > tolerance => FAIL.
- expectation OFF: missing decomposition reports NOT READY and does not fail
  the run (report-only).

### 3.6 Host telemetry — Tier A budget and Tier-B forensic cost are SEPARATE

The production contract: healthy Tier-A telemetry <= 20 ms; Tier B may add
~100–200 ms ONLY after abnormal H2D.  The <= 20 ms cap therefore applies to
TIER A, never to the total on a slow run.

Tier-A overhead resolution (most exact decomposition first):

1. explicit Tier-A aggregate (`host_telemetry_tier_a_ms` / `tier_a_ms` /
   `host_telemetry_tier_a_probe_wall_ms`);
2. total minus the slow-trigger probe (`tier_a = total - slow_trigger_probe_ms`)
   when both are available and the aggregate includes the slow probe;
3. summed `probe_wall_ms` over Tier-A host probe events
   (`host_hardware_fingerprint` + `host_resource_snapshot`, never the
   forensic event).

Tier-B slow-trigger probe: explicit `slow_trigger_probe_ms` /
`host_telemetry_slow_trigger_probe_ms`, else the summed `probe_wall_ms` of the
`host_forensic_slow_h2d` event(s).  Never fabricated.

Rules:

- healthy H2D (< slow threshold, default 4000 ms): Tier-A <= 20 ms REQUIRED
  and the slow-trigger probe must be 0;
- slow H2D (>= threshold): Tier-A <= 20 ms required; Tier-B forensic cost
  reported separately; the TOTAL probe wall may exceed 20 ms — the excess is
  the legitimate slow-trigger forensic probe, NOT a failure;
- slow H2D + `host_forensic_slow_h2d` event => forensic-correctness PASS (the
  event is EXPECTED on a genuinely slow transfer — expected, not a failure);
- healthy H2D + forensic event => FAIL;
- slow H2D + NO forensic event => FAIL only when
  `COMFYMODAL_V2_BATCH_B_EXPECT_SLOW_H2D_FORENSIC=1` (the slow-trigger
  runtime is expected to be enabled and observable); otherwise reported, not
  a failure;
- insufficient decomposition on a slow run (cannot distinguish Tier A from
  Tier B) => telemetry-overhead gate reports NOT OBSERVABLE, never a false
  failure on a total > 20 ms.

### 3.7 TOTAL WALL — informational only, NEVER a gate

`timing.wall_ms` / `waterfall*.total_wall_ms` is printed as informational and
explicitly marked `TOTAL WALL NOT AN ACCEPTANCE GATE`.  A 60 s RUN 1 with all
structural gates correct PASSES (fixture-tested), including with a legitimate
slow-H2D forensic event.

## 4. Strict RUN 1 behavior preserved — YES

The hook validates only the `index == 0` artifact (the normal RUN 1), prints
the BATCH B ACCEPTANCE block, and raises immediately on FAIL (non-zero exit,
aborting remaining runs).  No hidden retry, no extra sample, no automatic
second run.  With the flag off the hook short-circuits and normal benchmark
behavior is unchanged.  Both `--batch-a-acceptance` and
`--batch-b-acceptance` can run together; Batch-B re-validates Batch-A
internally.

## 5. Output block (exact, healthy run)

```
BATCH B ACCEPTANCE

Batch A preserved:
PASS

Runtime-state guard:
lane: READY
expectation: 1
evidence: decision, invoked, reload_ms, generation_check
decision: skipped_generation_match
invoked: NO
reload ms: 0.0
generation check: YES
local only: YES

Snapshot hygiene:
enabled: 1
before RSS: 1234.5
after RSS: 1220.0
delta: -14.5
trim status: ok
manifest status: {'vmrss': 1234, 'vmhwm': 1250, 'vmsize': 2600}

Stage 13:
gate: READY
expectation: 1
total: 250.0
children: 3
largest child: output_encode=150.0
reconciliation: 0.0

Host telemetry:
overhead (Tier A): 10.0
Tier B forensic probe: n/a
total probe: 10.0
forensic trigger: NO

TOTAL WALL: 60000.0 (informational only)

TOTAL WALL NOT AN ACCEPTANCE GATE

OVERALL: PASS
```

Slow-H2D run (H2D=9000 ms, TierA=11 ms, slow probe=155 ms, total=166 ms,
forensic present) renders the same block with
`overhead (Tier A): 11.0 / Tier B forensic probe: 155.0 / total probe: 166.0 /
forensic trigger: YES` and OVERALL: PASS.  On FAIL a `FAILED CHECKS:` list
follows, one line per failing gate.

## 6. Tests

`python -m unittest tests.test_batch_b_acceptance -v` — 45 cases, all green
(0.05 s, no Modal, no network).  Combined with the Batch-A suite (25 cases):
**70 tests OK**.

New/proven regression coverage:

1. Batch-A models skip cannot satisfy runtime-state skip
   (models evidence alone => lane NOT READY; expectation ON => FAIL).
2. Actual runtime-state reload cannot be hidden by models fields
   (`reload_runtime_state_ms=82` + reload events => runtime-state skip MUST
   NOT PASS).
3. Healthy H2D (2.5 s) + forensic event => FAIL.
4. Slow H2D (4.1 s / 9.2 s) + forensic event => PASS.
5. Slow H2D (9.0 s) + Tier-B overhead > 20 ms (166 ms total, 155 ms slow
   probe) => PASS when Tier A (11 ms) <= 20 ms; Tier-A-via-subtraction
   variant also PASSES.
6. Healthy Tier-A > 20 ms => FAIL (explicit aggregate and total variants).
7. Stage13 missing + expectation ON => FAIL; present-but-malformed always
   FAILS.
8. Stage13 missing + expectation OFF => NOT READY, reported, still PASSES.
9. 60 s TOTAL WALL remains irrelevant (all-pass fixture) and also PASSES
   with a legitimate slow-H2D forensic event.
10. Slow H2D + no forensic: FAIL with `EXPECT_SLOW_H2D_FORENSIC=1`, PASS
    (reported) with the flag off; slow-trigger probe > 0 on healthy H2D
    FAILS; insufficient slow-run decomposition => NOT OBSERVABLE, PASSES.
11. Snapshot hygiene/manifest gates, telemetry probe-sum fallback, render
    block, config-from-env, file roundtrip — retained.

## 7. Completion output

```
report path = V2_BATCH_B_ACCEPTANCE_HARNESS_REPORT.md
changed files = tools/batch_b_acceptance.py (revised),
                tools/benchmark_v2_direct.py (call-site: 2 new expectation flags),
                tests/test_batch_b_acceptance.py (revised),
                V2_BATCH_B_ACCEPTANCE_HARNESS_REPORT.md (revised)
commit = none
deploy count = 0
Modal runs = 0

models fields removed from runtime-state fallback = YES
runtime-state false-pass regression covered = YES

healthy H2D forensic event fails = YES
slow H2D forensic event passes = YES
missing slow forensic on >=threshold fails when observable = YES

Tier-A <=20 ms enforced separately = YES
Tier-B forensic overhead excluded from healthy cap = YES

Stage13 expectation flag added = YES
Stage13 missing + expectation ON fails = YES

TOTAL WALL still not acceptance gate = YES

tests = 45 Batch-B + 25 Batch-A = 70 OK (python -m unittest
        tests.test_batch_b_acceptance tests.test_batch_a_acceptance)
ready for integration = YES
```
