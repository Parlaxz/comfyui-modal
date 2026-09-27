# V2 Batch C4 — Hygiene Analyzer Semantic Fix Report

Status: **COMPLETE — TOOLS/TESTS ONLY.** No commits, no deploys, no Modal runs,
no remote work.  Modified exactly two files
(`tools/benchmark_v2_snapshot_hygiene_ab.py`,
`tests/test_benchmark_v2_snapshot_hygiene_ab.py`) plus this report.  All other
files read-only.

This report covers two analyzer semantic fixes and one **sanctioned
correction (v2)** to the freshness identity source after a genuine
runtime-artifact incompatibility was proven against real artifacts.

---

## 1. What changed

Three analyzer semantic changes, all confined to the offline A/B analyzer and
its test suite:

1. **Snapshot freshness now uses `container_session_id`** (the per-construction
   container session) corroborated by `runtime_state_generation_baseline`,
   instead of `snapshot_identity` (the stable model hash, intentionally
   identical across A/B and never a freshness proof).
2. **The primary command metric is now the accepted Batch-C3
   `non_scheduling_ms`** instead of the old placement-only subtraction
   (`command_response_ms − modal_scheduling`).
3. **Correction (v2):** the initially-shipped freshness discriminator
   `restore_session_id` was proven to be a **per-RESTORE uuid** (fresh on every
   request restore, `modal_app.py:9529`), not a per-construction identity.  It
   is demoted to per-restore correlation; freshness now uses
   `container_session_id` + `runtime_state_generation_baseline` corroboration.

---

## 2. Primary metric — exact BEFORE/AFTER semantics (UNCHANGED by v2)

| | BEFORE (old) | AFTER (new) |
|---|---|---|
| primary name | `command_without_scheduling_ms` | `non_scheduling_ms` |
| formula | `command_response_ms − scheduling_ms` (placement **only**) | Batch-C3: COMMAND → RESPONSE − scheduling time, where **scheduling time = (command → Modal enqueue) + (Modal scheduling / placement)** |
| primary source preference | n/a (single formula) | 1. `final_reconciled_waterfall.non_scheduling_ms` (the final reconciled C3 value as persisted in the artifact; also accepted from `waterfall_local`/`waterfall`); 2. **fallback arithmetic only when necessary**: `command_response_ms − command_to_enqueue_ms − placement scheduling_ms` (C3 vocabulary: scheduling = enqueue + placement; non-scheduling = total − scheduling) |
| placement-only subtraction | presented as "command without scheduling" | renamed `legacy_placement_excluded_ms`, **clearly labelled legacy/partial, informational only** |
| mixing C3 + legacy | n/a (only one metric existed) | **never mixed**: if either arm lacks the C3 sources (no reconciled `non_scheduling_ms` and no `command_to_enqueue_ms`), the C3 primary is unavailable for that arm and the report says so explicitly (`c3_primary_available_a/b` + a WARNING line in Protocol checks) |

Reference check (C3 contract report): `command_response=35168`,
`command_to_enqueue=19158`, `placement=854.266` → `scheduling_time=20012.266` →
`non_scheduling=15155.734`.  The analyzer reproduces this exactly, both from
the reconciled field and from the fallback arithmetic (test G).  Fix 2 was
**not touched** by the v2 correction.

### Preserved semantics (unchanged)

- 1–5 run support; no fake p90 from n=1 (`p90` only at n≥5, median/mean only
  at n≥2).
- RSS alone never establishes a performance win
  (`rss_drop_without_startup_win` guard unchanged).
- Explicit flag verification 0/1 (`flag_verified_a/b`); absent flag is
  UNVERIFIED, not invalid.
- Cold-run requirement (`restore_count==1 && request_count==1`).
- Batch-C structural validity (negative `command_response_ms` /
  `legacy_placement_excluded_ms` rejections).
- `scheduling_contamination` stays **informational context** — measured and
  reported, never subtracted.
- H2D / sampling / process-CPU secondary metrics unchanged.
- `modal_startup_ms` scheduling-inclusive and excluded from the verdict.
- `load_arm_runs` globs `run_*.json` unchanged (no dedup attempted; the
  warning is retained as the safe choice).

---

## 3. Snapshot freshness — exact BEFORE/AFTER source (v1 AND v2)

### v1 (original shipped fix)

| | BEFORE | AFTER (v1) |
|---|---|---|
| discriminator | persisted `snapshot_identity` (stable model hash) | `_restore_timing.restore_session_id` |
| within-arm check | from `snapshot_identity` set | from `restore_session_id` set |
| cross-arm check | disjoint `snapshot_identity` sets | disjoint `restore_session_id` sets |

### Correction (v2) — per-restore uuid discovery

**Proof** (real artifacts, repo root `..\..\comfymodal-data\benchmarks\runs\`):

- `comfymodal_runtime\modal_app.py:9529`:
  `restore_session_id = uuid.uuid4().hex` — a **fresh uuid on EVERY request
  restore**.
- Two runs 4 minutes apart restoring the **same** construction
  (`v2_2026-08-14_22-20-03\run_0.json` vs `v2_2026-08-14_22-24-00\run_0.json`):
  - share `container_session_id = 74aa5717dfed4bf7`
  - share `runtime_state_generation_baseline = ab86ef63ce1a4914b17f699cc3052a8a`
  - but have DIFFERENT `restore_session_id`
    (`0ba8891291e64a9aa91f97b2dbb617be` vs `3b112f97c90c434d852178594490f4e8`).
- Different constructions carry different `container_session_id` values
  (e.g. `68f839ff0fd84534`, `9d918f0a192243b8`, `74aa5717dfed4bf7`) and
  different baselines (`3ada6b56c91a47528436381d2b51f6ba` vs
  `ab86ef63ce1a4914b17f699cc3052a8a`).

| | AFTER (v1, WRONG) | AFTER (v2, CORRECT) |
|---|---|---|
| discriminator | `restore_session_id` (per-restore uuid — fresh per request) | `_restore_timing.container_session_id` (per-construction) |
| corroboration | none | `_restore_timing.runtime_state_generation_baseline` required on every valid run; a run with container present but baseline missing/inconsistent → **NOT READY** |
| within-arm check | one `restore_session_id` per arm (meaningless) | exactly **one** `container_session_id` per arm |
| cross-arm check | disjoint `restore_session_id` sets (falsely FRESH for same-construction runs) | disjoint `container_session_id` sets |
| `restore_session_id` role | (mis)used as construction identity | demoted to **per-restore correlation** — extracted and reported in the per-run table, never a freshness input |
| `snapshot_identity` role | lineage-only | lineage/model information only (unchanged) |
| missing construction identity | missing session → NOT READY | missing `container_session_id` AND baseline → `freshness_ready_a/b=False`, `snapshot_per_arm_fresh=None`, explicit `freshness_not_ready_reason`, report renders **"NOT READY — fail-closed"** (unchanged semantics, new source fields) |
| capture-time hygiene event + `effective_env` flag | supporting evidence | **unchanged** (still independent supporting evidence) |

New protocol keys: `container_sessions_a/b`, `baselines_a/b`,
`freshness_source`, `freshness_ready_a/b`, `freshness_not_ready_reason`,
`c3_primary_available_a/b`.  `restore_sessions_a/b` no longer exists.

---

## 4. Tests

### Added (14: A–F freshness, G–J C3, K–M real-artifact regressions)

| # | test | asserts |
|---|---|---|
| A | `test_freshness_same_snapshot_identity_different_containers_pass` | same `snapshot_identity` + different `container_session_id` across A/B → FRESH PASS |
| B | `test_freshness_same_container_across_arms_fails` | same `container_session_id` across A/B → FAIL |
| C | `test_freshness_multiple_runs_one_container_per_arm_pass` | several runs per arm, one construction container each → PASS |
| D | `test_freshness_multiple_containers_within_arm_fails` | multiple containers within one arm → within-arm consistency FAIL |
| E | `test_freshness_missing_construction_identity_not_ready_fail_closed` | missing `container_session_id` AND baseline → NOT READY / explicit, never silently fresh |
| F | `test_freshness_snapshot_identity_change_does_not_change_verdict` | changing only `snapshot_identity` (construction identity unchanged) does NOT change the freshness verdict |
| G | `test_c3_reference_arithmetic_reconciled_and_fallback` | 35168 / 19158 / 854.266 → scheduling 20012.266 → non-scheduling 15155.734 (reconciled **and** fallback) |
| H | `test_c3_enqueue_change_affects_scheduling_not_runtime` | enqueue delay moves scheduling_time only; underlying runtime stages + `non_scheduling_ms` invariant |
| I | `test_c3_different_enqueue_placement_identical_non_scheduling_zero_delta` | different enqueue/placement, identical C3 `non_scheduling_ms` → zero primary delta (legacy metric moves) |
| J | `test_c3_old_artifact_legacy_partial_not_equated` | old artifact lacking C3 fields → explicitly legacy/partial, C3 unavailable, never silently equivalent |
| K | `test_freshness_same_construction_different_restore_ids_fails` | **the exact bug case**: SAME `container_session_id` AND SAME baseline with DIFFERENT per-restore `restore_session_id`s → NOT FRESH / FAIL (uses the real 22-20 / 22-24 uuid values) |
| L | `test_freshness_different_containers_even_shared_restore_pattern_pass` | DIFFERENT `container_session_id` across arms (even with shared-looking `restore_session_id` patterns) → FRESH PASS |
| M | `test_freshness_same_container_missing_baseline_not_ready` | same container across arms but baseline missing on a run → NOT READY / explicit |
| M2 | `test_freshness_same_container_inconsistent_baseline_not_ready` | same container within an arm but DIFFERENT baselines across its runs → NOT READY / explicit inconsistency |

### Updated (only where they encoded the old semantics; intent preserved)

- `test_freshness_same_snapshot_identity_different_sessions_pass` → uses
  `container_session_id` (A).
- `test_freshness_same_session_across_arms_fails` → `container_session_id` (B).
- `test_freshness_multiple_runs_one_session_per_arm_pass` →
  `container_session_id` (C).
- `test_freshness_multiple_sessions_within_arm_fails` →
  `container_session_id` (D).
- `test_freshness_missing_session_not_ready_fail_closed` → missing construction
  identity (no container, no baseline) (E).
- `test_freshness_snapshot_identity_change_does_not_change_verdict` →
  construction identity unchanged (F).
- `test_experiment_record_shape_extracts` — record fixture now carries
  `container_session_id` + baseline; asserts extraction of all three identity
  fields.

### Unchanged

`test_n1_each_side_is_insufficient_no_fake_p90`,
`test_rss_drop_without_startup_win_no_claim`, `test_missing_rss_fields_handled`,
`test_invalid_structural_runs_excluded`, `test_no_claim_for_n1_p90_even_with_extremes`,
`test_arm_flag_absent_unverified_but_valid`, plus the four C3 tests G–J
(excluding the fixture rename of `session` → per-restore uuid).

---

## 5. Verification results

Run from repo root (PowerShell, `python`):

```
> python -m pytest tests/test_benchmark_v2_snapshot_hygiene_ab.py -q
24 passed in 5.88s          (10 existing + A–F + G–J + K, L, M, M2)

> python -m pytest tests/test_v2_waterfall_scheduling_contract.py tests/test_waterfall_scheduling_denominator.py -q
18 passed in 5.94s          (C3 scheduling-contract regression — UNCHANGED, 12 + 6)

> python -m pytest tests/test_v2_waterfall_contract.py -q
36 passed in 5.68s          (optional scheduling_time_ms/non_scheduling_ms contract — passes)
```

Exact pass/fail counts per file:

| file | result |
|---|---|
| `tests/test_benchmark_v2_snapshot_hygiene_ab.py` | **24 passed, 0 failed** |
| `tests/test_v2_waterfall_scheduling_contract.py` | **12 passed, 0 failed** |
| `tests/test_waterfall_scheduling_denominator.py` | **6 passed, 0 failed** |
| `tests/test_v2_waterfall_contract.py` | **36 passed, 0 failed** |

`python -m py_compile tools/benchmark_v2_snapshot_hygiene_ab.py` → OK.

### Real-artifact smoke test (unmodified artifacts, staged copies only)

Real `run_0.json` artifacts staged into clean temp dirs
(`C:\Users\parla\AppData\Local\Temp\opencode\c4_smoke*`), analyzer CLI run
`--arm-a <dirA> --arm-b <dirB> --out <tmp.md> --json <tmp.json>`:

| pair | arm A | arm B | result |
|---|---|---|---|
| (a) same construction | `v2_2026-08-14_22-20-03\run_0.json` | `v2_2026-08-14_22-24-00\run_0.json` | `snapshot_per_arm_fresh` = **False** (both share `container_session_id=74aa5717dfed4bf7`, same baseline) — correct FAIL |
| (b) different construction | `v2_2026-08-14_21-25-55\run_0.json` | `v2_2026-08-14_22-20-03\run_0.json` | `snapshot_per_arm_fresh` = **True** (containers `efed8d4cba054180` vs `74aa5717dfed4bf7`, different baselines) — correct fresh separation |

Notes from the smoke run:

- Both arms produced 1 valid run each (cold=True; `retained` absent → default
  retained).  The real `run_0.json` artifacts carry no `effective_env`
  hygiene key, so `flag_verified` is **UNVERIFIED (None)** on both sides —
  expected for these hygiene=0 arm-A runs; the runs stay valid.
- Per-run table now renders `container_session_id`, baseline, and the
  per-restore `restore_session_id` columns.
- No capture-time hygiene event on these arm-A artifacts → capture evidence
  shows count 0 / unavailable (never fabricated).

---

## 6. Scope guard

- Modified files: `tools/benchmark_v2_snapshot_hygiene_ab.py`,
  `tests/test_benchmark_v2_snapshot_hygiene_ab.py`, and this report.
- NOT modified: runtime, deploy scripts, `modal_app.py`, C5/C6 tools, Batch-C
  acceptance semantics, `experiment_result_store.py`, `v2_waterfall.py`.
- Real artifacts were only copied to temp dirs for smoke verification; never
  modified.
- **No commits.  No deploys.  No Modal runs.  No remote work.  CURRENT main
  only.**

## 7. Final response fields

- report path = `V2_BATCH_C4_HYGIENE_ANALYZER_SEMANTIC_FIX_REPORT.md`
- changed files = `tools/benchmark_v2_snapshot_hygiene_ab.py`,
  `tests/test_benchmark_v2_snapshot_hygiene_ab.py`
- commit = none · deploy count = 0 · Modal runs = 0
- freshness identity source = container_session_id + baseline corroboration = yes
- restore_session_id demoted to per-restore correlation = yes
- real-artifact smoke: same-construction pair verdict = NOT FRESH / FAIL
- real-artifact smoke: different-construction pair verdict = FRESH PASS
- C4 suite = 24 passed
- C3 contract suites = 18 passed unchanged (+ 36 contract tests)
- ready = yes
