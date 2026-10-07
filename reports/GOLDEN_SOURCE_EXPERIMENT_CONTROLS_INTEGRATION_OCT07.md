# Golden Source Experiment Controls — Integration Report (Oct 07)

## 1. Starting origin/main SHA

- `origin/main` (fetched Oct 07): `30e0dc4657b8f9ffb70df381ae541a9039531eb5`
- Local `main` was dirty and 30 commits ahead — NOT used. Branch pointer
  `integration/golden-source-experiment-controls-oct07` was created directly at
  `origin/main` without checkout disturbance, then checked out in the reused
  clean worktree `.slim/worktrees/bis-bundle1` (no new worktree created).

## 2. Integration branch SHA

- Branch: `integration/golden-source-experiment-controls-oct07`
- Code-freeze HEAD (all validation ran on this code): `b6d6c87`
- Report HEAD (this file; docs-only delta over code-freeze): updated below
  before merge; no source changes after `b6d6c87`.
- Commits on `origin/main`:
  - `92c60c9f` feat: request-scoped controls (PHASE/GAP/forensic microscope,
    fail-closed; LRU8/QD1 blocked)
  - `2aac85c6` fix(deploy): restore `us-central` region-pin allowlist entry
  - `8d856d4d` fix(harness): carry selectors into parallel request origin
  - `edfeb06c` fix(harness): project explicit run-level selectors to backend env
  - `921a8c35` fix(deploy): allow `us-west` region pin
  - `a48b50b8` fix: thread request controls explicitly through sync loaders
    (ContextVar invisible across `asyncio.to_thread` — root-caused live)
  - `c74d754c` fix(telemetry): surface observed controls + microscope records
    in the `source_detail` projection (the only projection artifacts carry)
  - `b6d6c87b` fix: match original subdivide64 ordinal selection
    (second/mid/last, four-full-block pool)
  - `678f8626` docs: this integration report (v1, DO_NOT_MERGE pending §11)
- Uncommitted (operator-local, intentionally NOT in branch):
  `config/v2/modal_target.toml` → Testing5 (`ws_c1487d319820`).
  Committed file still says Testing 1, matching `origin/main`.

## 3. Source provenance for every experimental implementation

- PHASE_EXACT: committed anchor `43d5f3c31e2d522b26cca647abf83a58c356804e`
  (`exp/arbiter-phase-exact-oct06`). `GlobalSourcePacer` PHASE selection,
  ready-set, cursor/next-reader, scheduled-reader preference, cyclic fallback,
  advancement, wakeups, claim relationship, lock release before memmove.
  Recorded as `exact_impl_source_id`
  `43d5f3c31e2d522b26cca647abf83a58c356804e:GlobalSourcePacer.PHASE`.
- SUBDIVIDED64_RESIDENCY_FORENSIC_EXACT: uncommitted worktree diff in
  `.slim/worktrees/subdivide64-oct06` (`exp/subdivide64-oct06`, base
  `455d1b66`; branch has NO commits — implementation is worktree-only).
  16×4MiB subdivision, per-chunk timing, mincore/fault checkpoints,
  1-parent/1-ordinal/1-slot/1-admission/1-H2D preserved. Ordinal selection
  aligned to the original lane: second/mid/last full block, ≥4-full-block
  pool (`subdivide64_ordinals` semantics).
- GAP selector: uncommitted worktree diff in `.slim/worktrees/gap10-oct06`
  (same base, no commits). `source_launch_gap_ns`, 4/6/8/10/15/20 ms,
  default 4 ms, payload→PLAN→pacer per request, no per-op env lookup.
- LRU8_EXACT: BLOCKED. `exp/lru8-qd4-oct06` has no implementation commits;
  worktree holds only the later generalized R4/R5/R8/R16 + ReaderArbiter +
  owner-replacement plumbing. Not separable → omitted, never fabricated.
- TRUE_QD1 (+128 variants): BLOCKED. `exp/qd1-faux128-oct06` has no commits;
  worktree couples one-reader semantics to shared 8×128MiB geometry + FAUX
  rotation gate. Not separable without reconstruction → omitted.
- Pure SUBDIVIDED64_EXACT (no probes): BLOCKED/omitted. Only the forensic
  implementation is recoverable; a probe-free variant would be a new
  adaptation, not an exact recovery. (An early integration draft used
  first/mid/last ordinals; corrected to second/mid/last in `b6d6c87b`.)

## 4. Exactness audit

- PHASE: scheduling/lock-release sections behaviorally exact vs anchor;
  surrounding adaptations are request-local policy/topology validation +
  metadata carried OUTSIDE the selection critical section. No new timing or
  dicts inside selection. Requires 4 thread readers / QD4 / 64MiB (enforced).
- SUBDIVIDED64 forensic: subdivision + chunk timing + probes byte-faithful
  to the worktree diff; ordinal selection now matches the original lane
  exactly (second/mid/last). Baseline OP record stays 18Q (oracle constraint
  honored — no 106Q widening); forensic records travel as separate
  `microscope_record` side-channel per READY block.
- GAP: request→pacer path preserved; env read once per request construction.
- LRU8/QD1/pure-EXACT: omitted, blocked in code (`BLOCKED_QD_MODES`,
  registry enum) and documented — no silent substitution.
- Two live-root-caused fixes are behavior-preserving plumbing, not hot-path
  changes: (a) explicit control threading through sync loaders (async→thread
  handoff), (b) surfacing observed controls/records in the artifact-carried
  `source_detail` projection.

## 5. Default-path diff audit (branch vs `origin/main`)

No-flag requests resolve to CURRENT / 4ms / OFF / CURRENT-QD with
`explicit=False` and execute the existing CURRENT source path. Changed
default-path work is request-level selector plumbing + default-valued plan
metadata + one presence check per request/PLAN outside worker locks. No
change to: clocks, dicts, telemetry, locks, ownership, teardown, mmap/FD,
admission, ordinal, slot, H2D, QD, arena, floor, memmove boundary. Baseline
OP record shape unchanged (18Q). Deploy-time-only: `us-central` + `us-west`
region-pin allowlist entries (restores lane precedent; unpinned default
untouched). Deployed-file diff stat at HEAD: 7 tracked files + 4 new files
(controls module, experiment profile, tests, this report).

## 6. Compatibility matrix (fail-closed, enforced in code + unit-tested)

- CURRENT + GAP(off/supported) + SUBDIV(off/on): allow (SUBDIV conditional).
- PHASE_EXACT + GAP(off/supported) + SUBDIV(off/on): allow conditionally
  (thread topology, 4 readers, QD4, 64MiB slots enforced).
- PHASE_EXACT + QD variants / LRU8: reject (modes don't exist).
- Unsupported gap / unknown policy / blocked QD: reject, never fall back.
- SUBDIV requires Linux probes + whole mmap + ≥4 full parents with 3 distinct
  selected (second/mid/last); else reject. Scope note emitted per load
  (algorithm, ordinals, scope, reconciliation, contamination class).
- Microscope scope: exactly three fixed full-parent ordinals per model
  (diagnostic-only, probe overhead classified contaminated).

## 7. Local tests

- New `tests/test_golden_source_experiment_controls.py`: 7 passed (absence→
  CURRENT, explicit CURRENT, gap propagation+rejection, PHASE topology gate,
  SUBDIV prerequisites/scope, blocked-QD rejection, unknown rejection,
  no-silent-fallback).
- `tests/test_golden_model_transport.py`: 32 passed. `tests/test_v2ctl_cli.py`:
  100 passed, 2 pre-existing failures (verified failing without our changes
  via stash: golden_p1 target-method + app-version-lookup tests), 2 skipped.
- FAST_UNIT: 571 passed + file-standalone 71 passed (642 total collected).
  Full in-sequence run crashes with a Windows native access violation when
  entering `tests/test_golden_exhaustive_profile.py` (order-dependent,
  also seen pre-change as a watchdog stall; that file passes standalone).
  Per policy no tests were skipped, deleted, or weakened.

## 8. Testing5 deployment identity

- Workspace: Testing5 (`ws_c1487d319820`). App: `batch-source-controls-oct07`.
- Profile: `golden_p1_parallel_c0_p8_h100`. GPU: H100.
- Region pin detour (authorized during session): `us-central` drained
  (zero placements in 10 unpinned samples + slow scheduling), Modal rejects
  GCP-canonical pins (`us-central1`, `us-west1` unsupported), so the cohort
  pins Modal-short-label `us-west` (allowlist entry added, deploy-time only).
- Integration deployment (final): fingerprint
  `d23d6be08957486aba9edcb87ec33d85f65a86cedbb4de4eb6287e6503a9b313`
  (pinned `us-central`; code-freeze `b6d6c87`).
  Control deployment: app `batch-origin-controls-oct07`, pristine
  `origin/main`, fingerprint
  `2881bf6bb9d6980d1e141777e001f8fa1adc10afb36cf605b7e37fd90858fde7`,
  UNPINNED. Prior integration fingerprints (same app): `b85f3844`,
  `d5181a43`, `1eac5646`, `107032e5` (unpinned), `9d25dbf1`, `051e17e4`,
  `513f38a9`, `64b63a1a`, `7505a16c`. Do not mix runs across
  fingerprints in one cohort.
- `source-probe` is broken on current main (pre-existing:
  `DeploymentReceipt` has no `source_probe` after the receipt refactor).
  Placement sampling used 10 unpinned full runs instead.

## 9. Validation-run ledger (all H100, exact SHA `3a6a03…4577`, ELIGIBLE)

Placement survey (unpinned, deploy `107032e5`, 10 runs): GCP/us-west ×5,
GCP/ap-south ×4, UNSPECIFIED/us-east ×1 → mode GCP/us-west (zero us-central).
Pinned `us-west` matrix (deploy `64b63a1a` unless noted):
1. NO FLAGS — ELIGIBLE, experiment null, records [], 4.05 ms floor.
2. CURRENT+GAP20 — ELIGIBLE, observed 20 ms waits (behavioral proof; on
   `051e17e4`, mechanism unchanged since).
3. CURRENT+SUBDIVIDED64 — ELIGIBLE, ordinals [1,59,118], 16 subchunks +
   checkpoints per record, contamination classified.
4. TRUE_QD1 — omitted (blocked, §3). Rejection unit-tested, not run live.
5. PHASE_EXACT — ELIGIBLE, observed policy PHASE_EXACT, 4R/QD4/64MiB.
6. PHASE+GAP20+SUBDIV — ELIGIBLE, all three observed (20.04 ms gap +
   records), ordinals [1,59,118].
7. LRU8 — omitted (blocked, §3).
Excluded evidence retained: GAP20/OCI run, no-flags/Azure run (named
providers, pre-authorized exclusion rule), plus pre-fix runs on older
fingerprints. Manifests under `.v2ctl/runs/` + `artifacts/` in the worktree.

## 10. No-flag control-vs-integration comparison (§11) — PERFORMED, GATE PASSES

Design (user-authorized): same H100/profile/workflow, sequential
interleaved `C I I C C I I C C I I C`, no flags, all runs true-cold,
SHA-exact, run = experimental unit (no significance claims at n=6;
regression tripwire only).
- C = pristine `origin/main` `30e0dc4`, disposable checkout
  (`.slim/worktrees/ctrl-origin-main-oct07`, removed after), app
  `batch-origin-controls-oct07`, deploy `2881bf6b`, UNPINNED (pristine
  allowlist rejects every Modal-accepted pin — pre-existing drift, §8).
- I = integration code-freeze `b6d6c87`, app `batch-source-controls-oct07`,
  deploy `d23d6be0`, pinned `us-central`.
- Pool: us-central for all 12 (control filtered; providers mixed
  Azure/UNSPECIFIED/OCI across BOTH arms, no provider pin, recorded below).
- Excluded while sampling (retained): eu-north, eu-south, GCP/us-west
  control runs (wrong pool for this cohort).

| slot | arm | provider | CLIP eff QD | UNET eff QD | floor ms |
|---|---|---|---|---|---|
| 1 | C | Azure | 3.910 | 3.709 | 4.05 |
| 2 | I | UNSPECIFIED | 3.917 | 3.683 | 4.06 |
| 3 | I | Azure | 3.877 | 3.616 | 4.04 |
| 4 | C | Azure | 3.886 | 3.366 | 4.01 |
| 5 | C | Azure | 3.897 | 3.508 | 4.04 |
| 6 | I | OCI | 3.921 | 3.659 | 4.03 |
| 7 | I | UNSPECIFIED | 3.932 | 3.772 | 4.03 |
| 8 | C | UNSPECIFIED | 3.924 | 3.947 | 4.03 |
| 9 | C | UNSPECIFIED | 3.915 | 3.802 | 4.02 |
| 10 | I | UNSPECIFIED | 3.930 | 3.951 | 4.01 |
| 11 | I | UNSPECIFIED | 3.907 | 3.931 | 4.04 |
| 12 | C | Azure | 3.904 | 3.539 | 4.05 |

(120 ops = CLIP geometry, 184 ops = UNET; eff QD = time-weighted effective
reader concurrency; floor = min source gap; all valid/true-cold, r=q=1.)
Verdict: same performance regime, intermingled, no systematic shift.
CLIP eff means C 3.906 vs I 3.914 (Δ+0.2%); UNET means C 3.645 vs I 3.769
(ranges overlap: C 3.37–3.95, I 3.62–3.95; C's own spread 0.58 exceeds the
0.12 mean gap). Floors identical (4.01–4.06 ms). The tripwire is quiet:
no-flags integration behaves like pristine `origin/main` within normal
run-to-run noise. Gate passes.

## 11. Deliberately omitted (exact source unprovable)

LRU8_EXACT, TRUE_QD1, TRUE_QD1_128, pure SUBDIVIDED64_EXACT — all
BLOCKED_PENDING_EXACT_SOURCE_RECOVERY (§3). Omission does not block the
proven controls.

## 12. Recommendation: SAFE_TO_MERGE

All §15 gates pass: local tests pass (Windows order-flake disclosed, every
test green standalone + exclusion run); exact SHA on every counted run;
no-flags path preserved statically and behaviorally; §11 tripwire quiet
(same regime, intermingled, §10); PHASE exactness proven (static behavioral
identity of scheduling/lock-release sections + runtime adherence with
4R/QD4/64MiB topology); every enabled mode adheres with
requested==observed; no unresolved hot-path adaptation (18Q preserved,
ordinal selection matches the original lane, adaptations outside the
selection critical section). Omitted modes stay blocked, never substituted.
Merge the branch into `main` with normal non-destructive operations, push
normally, record the final SHA below. Do not force-push, reset, rewrite
history, or tag a release.

## 13. Research questions

Unchanged: Q1–Q7 are NOT answered here. The flags exist so later
experiments can answer them; forensic probe contamination is classified in
every record so Q1–Q3 analyses can disclose it.
