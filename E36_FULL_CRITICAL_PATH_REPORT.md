# E36 Full Critical-Path Report

> **SUPERSESSION NOTICE (2026-08-30):** This historical timing report remains
> evidence for its original run. Its generated-output endpoint terminology is
> superseded by `docs/COMFYMODAL_OUTPUT_DURABILITY_POLICY.md`: output is
> result-ready by default; commit/reopen/hash proof is required only for an
> explicit strict run. S4 source publication durability remains mandatory.

## CURRENT AUTHORITATIVE STATUS

**Current decision:** The authoritative current-source result is the valid QD4
ARM-B run `v2_2026-08-21_16-00-22`. QD4 remains the recommendation. The
invalid snapshot-creation run `v2_2026-08-21_15-57-21` is excluded from all
timing decisions. The proof fix is a correctness/observability repair, not a
semantic performance change.

The current deployment is source-verified and identity-matched:

- Deploy fingerprint: `8e2f648656b10c1bda85b69c61a6c3498c9483c2360ddb8108d5aa961e490bea`
- Current gate profile fingerprint: `b3f54de4f27cd8d3bca7b8acd8c44f715c77be3ad4be832decd10d43366c64a3`
- Deployed profile: `e31-clip-fp32-qd4-arm-b`
- Source probe: `PASS/MATCH`
- Output SHA: `20b10e1f99831bc758d9df82f43ce0beb1cbc636a740d11a29eb2bffe90e5260`

## Objective and scope

E36 resolves the full critical path from remote Python resume through the first
durable result, while separating restore, pre-sampler, sampler, VAE, source-I/O,
host-to-device, proof, provenance, and post-durable effects. The scope is
measurement and safe proof/diagnostic repair; it does not authorize speculative
loader tuning or broad behavior changes.

The report consolidates the E36 read-only investigations (QD4, restore and
placement, proof, CLIP/UNET, VAE, and ledger), the approved local repair, the
canonical deployment evidence, and the comparable valid runs.

## Constraints and control-plane rules

- Branch: `TESTING2`.
- Baseline: `8e49d758c02e243e364eb3c3922cae747827c1de`.
- Preserve the existing E29-E35 worktree, including its extensive uncommitted
  changes.
- The remote owner is the coordinator. Remote operations use
  `python tools/v2ctl.py` and the canonical deploy/run control plane.
- No branch, worktree, stash, reset, clean, discard, commit, or push operation
  is permitted for this work.
- The evidence sequence is local proof/telemetry validation, one combined safe
  deployment, a gate and true-cold run, a placement A/B only if still needed,
  and a final cold run with SHA, schema-v2 provenance, cache-miss, proof,
  loader, restore, and first-durable evidence.

## Baseline and worktree state

The worktree began on `TESTING2` at the baseline above with extensive
uncommitted E35 changes. Those changes are intentionally preserved. The E36
local batch was limited to proof/registry diagnostics, the authoritative ledger
reset, and focused regressions. This report is the only new file created by
this reporting task; no source, profile, generated artifact, or existing
worktree file was changed for the report.

## Evidence taxonomy

1. **Authoritative:** canonical v2ctl artifacts from a source-matched deploy,
   with schema-v2 provenance and the canonical first-durable ledger endpoint.
2. **Valid comparison evidence:** runs whose terminal state and artifact set
   support timing comparison, including the ARM-A QD4 and FASTSAFE control
   runs.
3. **Local evidence:** source inspection, focused tests, compilation, and
   `git diff --check`; these establish implementation and proof behavior but
   are not remote performance measurements.
4. **Invalid/excluded evidence:** artifacts with a failed snapshot/container
   lifecycle, even if a control-plane manifest says the timing is valid. Such
   timing cannot be used to rank implementations.
5. **Unmeasured/inferential:** conclusions supported by mechanics or observed
   correlation but lacking a dedicated comparable A/B or device-side event.

## Chronology of work

1. E36-A through E36-E completed initial read-only lanes for QD4, restore and
   placement, proof, CLIP/UNET, VAE, and ledger behavior.
2. Oracle approved only a proof/diagnostic subset for implementation; broad
   behavior changes were deferred.
3. The local Phase 2 batch added fail-closed registry-manifest diagnostics,
   cleared authoritative ledger endpoints at fresh restore, and added focused
   regressions.
4. The proof-reason repair was then added: a consumed plan proof reports an
   empty reason instead of incorrectly carrying an ineligibility reason.
5. The current QD4 ARM-B source was deployed through the canonical control
   plane, passed the source probe, and produced the current gate and run
   artifacts.
6. The valid ARM-A QD4 and FASTSAFE control runs were compared with the valid
   ARM-B follow-up. The snapshot-creation failure was separately classified as
   invalid and removed from timing comparisons.

## Local implementation changes

The E36-specific local changes recorded in the authoritative memo are:

- `comfymodal_runtime/modal_app.py`
  - Corrected plan-proof decision-reason reporting: `consumed=true` now emits
    an empty reason.
  - Repaired registry-root symmetry by including the custom-nodes root in the
    manifest root set.
  - Published fail-closed registry-manifest error, root-count, and class-count
    diagnostics without inventing a manifest.
  - Kept registry-manifest completeness as a proof requirement and included
    the registry proof store in source identity handling.
- `comfymodal_runtime/critical_path_ledger.py`
  - `begin_restore()` now clears authoritative endpoints so a new restore
    cannot reuse endpoint state from an earlier request.
- `tests/test_deployment_proof.py`
  - Added regressions for manifest publication diagnostics and the consumed
    plan-proof reason behavior.

The existing E29-E35 worktree contains other pre-existing local changes; they
are not attributed to this report.

## Local validation

The memo records the following successful local validation:

- Focused proof suite: `23 passed in tests/test_deployment_proof.py`.
- Earlier focused E36 batch gate: `66 targeted tests passed`.
- `py_compile` passed for the proof-fix validation.
- `compileall` passed for the earlier local gate.
- `git diff --check` passed before this report was written, and was run again
  after writing as recorded at the end of this report.

These tests are local and do not substitute for the canonical remote gate or a
true-cold performance run.

## Deployment and source identity evidence

The current source was deployed with profile
`e31-clip-fp32-qd4-arm-b`. The deploy fingerprint,
`8e2f648656b10c1bda85b69c61a6c3498c9483c2360ddb8108d5aa961e490bea`, and the
gate profile fingerprint,
`b3f54de4f27cd8d3bca7b8acd8c44f715c77be3ad4be832decd10d43366c64a3`, are the
identities attached to the current evidence. The source probe returned
`PASS/MATCH`. The current valid run also carried the exact output SHA
`20b10e1f99831bc758d9df82f43ce0beb1cbc636a740d11a29eb2bffe90e5260`.

Proof findings for the current plan are:

- Plan proof decision: `consumed=true`.
- Consumed proof reason: empty.
- Plan/snapshot parity and provenance were present in the valid evidence.
- Output SHA matched the expected exact output identity.
- E31 cast-once proof: `398 NOOP_SAME_TENSOR`, zero real conversions, and zero
  new allocations.
- Registry diagnostics are fail-closed: manifest construction failures publish
  the error and root count rather than silently fabricating complete registry
  data.

## Artifact locations

Artifact root:

`C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\comfymodal-data\benchmarks\runs`

Relevant run artifacts:

- `v2_2026-08-21_15-24-02` (valid QD4 ARM-A):
  - `C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\comfymodal-data\benchmarks\runs\v2_2026-08-21_15-24-02\summary.json`
  - `C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\comfymodal-data\benchmarks\runs\v2_2026-08-21_15-24-02\run_001_sample.json`
- `v2_2026-08-21_15-34-44` (valid FASTSAFE control):
  - `C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\comfymodal-data\benchmarks\runs\v2_2026-08-21_15-34-44\summary.json`
  - `C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\comfymodal-data\benchmarks\runs\v2_2026-08-21_15-34-44\run_001_sample.json`
- `v2_2026-08-21_15-57-21` (invalid snapshot-creation run):
  - `C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\comfymodal-data\benchmarks\runs\v2_2026-08-21_15-57-21\summary.json`
  - `C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\comfymodal-data\benchmarks\runs\v2_2026-08-21_15-57-21\run_001_sample.json`
  - `C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\comfymodal-data\benchmarks\runs\v2_2026-08-21_15-57-21\run_001_sample.json.v2ctl-provenance.json`
  - `C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\comfymodal-data\benchmarks\runs\v2_2026-08-21_15-57-21\campaign_manifest.json`
- `v2_2026-08-21_16-00-22` (authoritative valid QD4 ARM-B):
  - `C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\comfymodal-data\benchmarks\runs\v2_2026-08-21_16-00-22\summary.json`
  - `C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\comfymodal-data\benchmarks\runs\v2_2026-08-21_16-00-22\run_001_sample.json`
  - `C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\comfymodal-data\benchmarks\runs\v2_2026-08-21_16-00-22\run_001_sample.json.v2ctl-provenance.json`
  - `C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\comfymodal-data\benchmarks\runs\v2_2026-08-21_16-00-22\campaign_manifest.json`

## Run comparison

| Run | Status / configuration | First durable (ms) | Wall (ms) | Restore (ms) | Pre-sampler (ms) | Sampler (ms) | VAE (ms) | QD source (ms) | Aggregate | Steady | H2D host issue (ms) | Other evidence |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| `v2_2026-08-21_15-24-02` | Valid QD4 ARM-A | 17,926.783 | 29,546.0 | 3,166.082 | 8,598.776 | 3,714.725 | 434.837 | 2,654.1844 | 3.031 GB/s | 1.9851 GB/s | 1,703.038 | — |
| `v2_2026-08-21_15-34-44` | Valid FASTSAFE control | 24,716.236 | 35,275.8 | 9,597.093 | 9,328.501 | 3,676.141 | 443.733 | — | — | — | — | CLIP loader-to-device-ready 491.372 ms; output SHA matching |
| `v2_2026-08-21_16-00-22` | **Authoritative valid current-source QD4 ARM-B** | 18,734.476 | 31,381.8 | 1,931.276 | 10,220.535 | 3,690.867 | 381.284 | 2,885.5178 | 2.788 GB/s | 1.5716 GB/s | 3,202.154 | 240/240 reads; 0 errors; max outstanding 4; buffer wait 2.6428 ms |
| `v2_2026-08-21_15-57-21` | **Invalid snapshot-creation/container failure** | Excluded | Excluded | — | — | — | — | — | — | — | — | Reported 52,972.4 ms is excluded |

### Why the current valid runs are worse

The current valid QD4 ARM-B result is slower than the valid ARM-A observation
by 807.693 ms to first durable and 1,835.8 ms wall. The evidence supports
variance, not a semantic regression from the proof repair:

- Remote/snapshot lifecycle timing varies materially; the FASTSAFE control
  shows restore at 9,597.093 ms versus 1,931.276 ms in the current QD4 run.
- QD source timing and throughput vary: current source time is 2,885.5178 ms
  versus 2,654.1844 ms, with lower aggregate and steady throughput.
- H2D host issue time varies sharply: 3,202.154 ms currently versus
  1,703.038 ms on ARM-A.
- Pre-sampler work varies: 10,220.535 ms currently versus 8,598.776 ms on
  ARM-A.
- Sampler and VAE are comparatively stable across the valid runs, so they do
  not explain the broad wall-time difference.

The 52.9724-second snapshot-creation run is not a slower valid run. It ended
with `terminate called without an active exception` / `SIGABRT` during
snapshot creation/container setup. Its v2ctl gate-valid marker is therefore
not sufficient evidence of a successful measured execution, and its timing is
explicitly excluded. The valid 31.3818-second ARM-B run is the relevant current
source result.

## Answers to the E36 questions

### Loader choice

Choose QD4 with `qd=4` and `32 MiB` blocks. QD4 wins the observed valid
first-durable and wall comparisons; earlier claims that FASTSAFE won are
superseded. This is an observed recommendation, not proof that every source or
remote lifecycle will have the same variance.

### QD concurrency

The current run confirms `max outstanding=4`, `240/240` reads, `0` errors, and
2.6428 ms buffer wait. The mechanics are confirmed, but the source limitation
versus downstream backpressure is not fully separated. Preserve QD4; do not
speculatively increase staging depth without slot-wait and source-to-GPU
evidence.

### Launch placement

No early-versus-late QD A/B was completed. Late launch remains **unmeasured**;
it must not be presented as a completed result or used as a reason to change
the recommendation.

### E31 cast-once

The cast-once proof is positive: 398 `NOOP_SAME_TENSOR`, zero real conversions,
and zero new allocations. Keep `FP32_CAST_ONCE=1`. The proof demonstrates
conversion/allocation elimination and correctness of the path; it is not a
claim that the proof instrumentation itself changes semantic performance.

### E31 forensics

Keep E31 forensics and profile diagnostics disabled in a production build unless
another evidence run specifically requires them. They remain useful for a
bounded investigation but are not needed to select QD4 here.

### Restore

Restore is a major variance boundary and must remain separately reported.
`restore_earliest` is recommended. The ledger reset prevents a fresh restore
from inheriting authoritative endpoints from an earlier request; no broad
restore rewrite is justified by the current evidence.

### Proof

The proof repair is correct and fail-closed. A consumed plan proof now reports
`reason=""`, while an unconsumed proof retains its actual reason or
`not_eligible`. Current evidence reports consumed proof, parity/provenance, and
the exact output SHA.

### Ledger

The canonical ledger is the account from remote Python resume to first durable
result. It uses explicit endpoints, preserves request identity, and labels
unexplained intervals as `UNATTRIBUTED` rather than guessing a stage. The
first-durable values in the table are therefore the decision endpoint; wall
time and post-durable tail must remain separate.

### UNET/VAE

UNET scheduling and H2D evidence support contention and an enqueue-versus-
transfer distinction, but do not establish overlap ownership without narrower
wait/stage events. For VAE, `load_models_gpu` is the main measured owner of the
transition. The valid sampler and VAE timings are stable enough that neither is
the primary explanation for the current slowdown.

### Host/remote timing

Remote lifecycle, snapshot creation, restore, QD source I/O, H2D host issues,
and pre-sampler work must be reported as separate boundaries. The reviewed
artifacts do not support attributing a claimed 5.5-second host plan-build cost
to the local plan builder. Report plan construction separately from
dispatch/registry and remote execution instead of optimizing an unsupported
boundary.

### What remains unmeasured

- Same-loader EARLY/LATE placement A/B, especially the late-launch case.
- A complete source-to-GPU/backpressure explanation for the QD throughput gap.
- Device duration for the current H2D path; the current artifact reports it as
  unavailable.
- A control-plane gate that reliably rejects snapshot/container failures before
  accepting a timing artifact.
- A final variance campaign broad enough to distinguish remote lifecycle noise
  from smaller source/pre-sampler effects.

## Limitations

The comparison is based on the recorded valid runs rather than a large,
fully-controlled statistical campaign. Restore and remote/snapshot lifecycle
variance are confounders. The invalid snapshot run exposes a control-plane
reliability gap: a gate-valid marker alone can pass an artifact whose process
terminated with SIGABRT. No late-launch A/B was completed, and no unsupported
raw-log values are inferred here.

## Report validation

Created: `E36_FULL_CRITICAL_PATH_REPORT.md`

Validation: `git diff --check` passed after writing.

## Final recommendation and next actions

**Decision:** retain QD4: `qd=4`, `32 MiB` blocks, `restore_earliest`, and
`FP32_CAST_ONCE=1`; keep E31 forensics/profile disabled for production.

**Next actions:** preserve source/provenance/output-SHA checks; make gate
classification reject snapshot/container aborts; collect narrow QD, H2D/device,
and restore evidence if another measurement is justified; and measure late
placement only as a same-loader, source-matched A/B.
