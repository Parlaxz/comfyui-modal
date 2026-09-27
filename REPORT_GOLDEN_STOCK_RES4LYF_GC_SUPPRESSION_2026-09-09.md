# Golden stock RES4LYF GC suppression experiment

## Verdict

**ACCEPT as a proposed canonical Golden base.** The candidate reproduces
essentially the full external Lane A sampler win while leaving the tracked
RES4LYF tree completely stock. The implementation is isolated to
`comfyui-modal`; no Lane A, Lane B, or A+B RES4LYF commit was used.

## Frozen lane and ownership

- Base: `0ea9428636afe06adf3e6a05319898473ebdd64d`
- Worktree: `C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\.slim\worktrees\golden-gc-suppression-exp3`
- Branch: `omos/golden-gc-suppression-exp3`
- Final comfyui-modal HEAD: `4421610c1a40` (full SHA in Git)
- Candidate commits, all comfyui-modal only:
  - `74c6f5e79eae4103e0da49099af7445937aa441b` — suppression and tests
  - `309f2f0a4a23` — Modal class-environment forwarding and test
  - `4421610c1a40` — stock loader module-identity resolution and tests
- Stock RES4LYF checkout: `C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\RES4LYF`
- Stock RES4LYF HEAD: `119679d8d8d26e6db52757e705488abb6399d7d4`
- `git diff 119679d8..HEAD --quiet`: exit `0`; no tracked RES4LYF diff.
- RES4LYF has only pre-existing untracked `.slim/` metadata; no source file was
  modified, staged, committed, or cherry-picked.
- Candidate worktree had a clean tracked tree at deployment. Post-run
  untracked files are generated evidence only; `git diff` remains empty.

## Implementation

`comfymodal_runtime/golden_serial.py` wraps only the direct Golden sampler
closure, `runner.run_closure(node_map.sampler_id, include_target=True)`.

Before entering that closure it:

1. Reads the registered sampler class's exact `__module__` key.
2. Accepts only the stock dotted key or ComfyUI's absolute path-like loader key
   ending in `RES4LYF.beta.samplers`.
3. Resolves only `sys.modules[registered_class_module]`; it never imports,
   searches, or aliases a replacement module.
4. Verifies module name, real source path suffix
   `RES4LYF/beta/samplers.py`, exact `ClownsharKSampler_Beta` class identity,
   and module-local `gc is stdlib_gc`.
5. Replaces only that module's `gc` binding with a forwarding proxy whose
   `collect()` returns `0` and counts calls.
6. Restores the saved binding in `finally` on success, exception, and
   cancellation. Restoration failure is surfaced visibly.

A non-blocking process lock rejects overlapping suppression scopes fail-closed;
it does not mutate global `gc.collect`, automatic GC settings, or unrelated
workflows. The experiment is deploy-baked and forwarded explicitly through
`modal_app._runtime_env()`:

`COMFYMODAL_GOLDEN_RES4LYF_GC_SUPPRESSION=1`

The stock callsite being intercepted is `RES4LYF.beta.samplers`' module-local
`gc.collect()` in `SharkSampler.main` on the batch path, after batch processing
and before final stacking/state assembly.

## Local validation

- Focused suppression tests after final resolver: **15 passed**.
- Modal runtime-env focused tests: **7 passed**.
- `py_compile`: passed.
- TOML parsing/config assertions: passed.
- `git diff --check`: passed.
- Broad FAST_UNIT command was not accepted as a green gate: it exceeded the
  repository's 15-second watchdog during collection (`10.98 s` collection,
  `15.08 s` total). No timeout escalation was performed. The relevant focused
  tests passed.

## Deployment and source probe

- App: `batch-golden-gc-suppression-exp3`
- Workspace: Testing 6 / `ws_175a616152c5`
- Deployment manifest:
  `.v2ctl/deployments/deploy_20260909-002433_0a14fabb.json`
- Deployment receipt:
  `.v2ctl/deployments/receipt_4_0a14fabb22fb63fbcdfd38e1a937fb95443170538a638b329b9f9fec96266232.json`
- Deployment fingerprint:
  `0a14fabb22fb63fbcdfd38e1a937fb95443170538a638b329b9f9fec96266232`
- Source probe:
  `.v2ctl/source-probes/probe_4_0a14fabb22fb63fbcdfd38e1a937fb95443170538a638b329b9f9fec96266232.json`
- Source probe verdict: `PASS / MATCH`.
- Remote source probe confirmed `golden_serial.py` and `modal_app.py` hashes
  match the final committed candidate.
- Runtime: Golden Serial, Sage/baked CUDA, true-QD2 control arm, 4 CPU / 16
  GiB, exact 8-step `exponential/res_2s`, `bong_tangent`, deep profiler off,
  single-use containers, output durability off.

## Correctness smoke

Smoke manifest:

`.v2ctl/runs/run_20260909-002631_9f406aed.json`

Raw cohort:

`artifacts/phase_p1_serial_golden_v1/cohort_2026-09-09_05-25-54_90d3cd/`

Result: valid, true-cold, `restore_count=1`, `request_count=1`, seriality
violations `0`, exact output SHA, no relevant fallback. Suppression telemetry:

```text
status=applied
module_name=/root/comfy/ComfyUI/custom_nodes/RES4LYF.beta.samplers
expected_target=RES4LYF.beta.samplers
module_path=/root/comfy/ComfyUI/custom_nodes/RES4LYF/beta/samplers.py
intercepted_collect_count=1
restoration_state=restored
```

Expected and observed SHA:

`790c3052a9b4a5ed01369e81cf79eac389f1d69b25578be3aa033e673570e89d`

## Five-run true-cold timing cohort

The `last useful compute → sampler return` marker was **not emitted** by the
stock path with deep profiling off; it is reported as `N/A`, not inferred from
the sampler total. The authoritative sampler boundary is the
`GoldenSerialRunner` sampler function entry through return.

| run | sampler total (ms) | last useful compute → return | intercepted? | collect count | suppression wall (ms) | resume → FRR (ms) | SHA | true-cold | restore/request | seriality | fallbacks |
|---:|---:|---|---|---:|---:|---:|---|---|---|---:|---|
| 1 | 4693.666 | N/A | yes | 1 | 4694.278 | 11728.057 | exact | yes | 1 / 1 | 0 | none |
| 2 | 4649.837 | N/A | yes | 1 | 4650.325 | 11269.381 | exact | yes | 1 / 1 | 0 | none |
| 3 | 4621.677 | N/A | yes | 1 | 4622.223 | 11638.546 | exact | yes | 1 / 1 | 0 | none |
| 4 | 4616.347 | N/A | yes | 1 | 4616.862 | 11702.493 | exact | yes | 1 / 1 | 0 | none |
| 5 | 4655.343 | N/A | yes | 1 | 4655.885 | 11875.746 | exact | yes | 1 / 1 | 0 | none |

Aggregate timing statistics:

- Sampler total: mean `4647.374 ms`, median `4649.837 ms`, P90
  `4678.336 ms`, sample SD `30.966 ms`, CV `0.00666`.
- Suppression wall: mean `4647.915 ms`, median `4650.325 ms`, P90
  `4678.313 ms`, sample SD `30.997 ms`.
- Resume → FIRST_RESULT_READY: mean `11642.845 ms`, median `11702.493 ms`,
  P90 `11816.670 ms`, sample SD `226.139 ms`, CV `0.01942`.
- Every timing run recorded `status=applied`, `intercepted_collect_count=1`,
  `restoration_state=restored`, exact SHA, true-cold, one restore, one request,
  zero seriality violations, and no relevant fallback.

## Comparison

| cohort | sampler mean |
|---|---:|
| `0ea9428` | `5445.199 ms` |
| external Lane A reference | `4639.492 ms` |
| external A+B reference | `4618.451 ms` |
| **comfyui-modal-only suppression** | **`4647.374 ms`** |

The comfyui-modal-only candidate improves over `0ea9428` by `797.825 ms`
(`14.66%`) and recovers `99.02%` of Lane A's measured improvement. It is only
`7.882 ms` (`0.17%`) slower than external Lane A and `28.923 ms` (`0.63%`)
slower than external A+B. The candidate is therefore accepted as the proposed
new canonical Golden base, subject to the explicit requirement that the
RES4LYF repository remains stock.

## Raw run manifests and evidence

Five timing manifests:

- `.v2ctl/runs/run_20260909-002807_9f406aed.json`
- `.v2ctl/runs/run_20260909-002910_9f406aed.json`
- `.v2ctl/runs/run_20260909-003014_9f406aed.json`
- `.v2ctl/runs/run_20260909-003117_9f406aed.json`
- `.v2ctl/runs/run_20260909-003218_9f406aed.json`

Corresponding raw cohort directories, each retaining
`attempt_0.json`, `attempt_0_events.json`, `manifest.json`, and `summary.json`:

- `artifacts/phase_p1_serial_golden_v1/cohort_2026-09-09_05-27-33_1d6066/`
- `artifacts/phase_p1_serial_golden_v1/cohort_2026-09-09_05-28-38_025ef5/`
- `artifacts/phase_p1_serial_golden_v1/cohort_2026-09-09_05-29-41_55c7f1/`
- `artifacts/phase_p1_serial_golden_v1/cohort_2026-09-09_05-30-44_ba48c6/`
- `artifacts/phase_p1_serial_golden_v1/cohort_2026-09-09_05-31-46_7c0dbc/`

Per-run evidence reports:

- `EXPERIMENT_EVIDENCE_golden_p1_4f7a7df9e8e945d1_2026-09-09.md`
- `EXPERIMENT_EVIDENCE_golden_p1_35401f6fa93e4393_2026-09-09.md`
- `EXPERIMENT_EVIDENCE_golden_p1_a5daf49e60ea41fe_2026-09-09.md`
- `EXPERIMENT_EVIDENCE_golden_p1_3e5a665fdad74b3a_2026-09-09.md`
- `EXPERIMENT_EVIDENCE_golden_p1_27b771c5c7cb47ea_2026-09-09.md`

Retained invalid/setup attempts include:

- `run_20260908-234840_fdccb441.json` — pre-bridge smoke; suppression flag
  not forwarded, recorded `skipped`.
- `run_20260908-235920_48775359.json` — pre-resolver attempt; fail-closed
  module-path resolution.
- `run_20260909-001249_f276bdb0.json` — pre-loader-identity fix; fail-closed
  registered class-module identity.
- `EXPERIMENT_EVIDENCE_golden_p1_e0a6c1aa60644d68_2026-09-09.md`
- `EXPERIMENT_EVIDENCE_golden_p1_90c9816489e64292_2026-09-09.md`
- `EXPERIMENT_EVIDENCE_golden_p1_4f785cbfbd054a4a_2026-09-09.md`
- `EXPERIMENT_EVIDENCE_golden_p1_ec626a60385c47b2_2026-09-09.md`
- `EXPERIMENT_EVIDENCE_golden_p1_f3df09b619664452_2026-09-09.md`

These failures were not counted in the timing cohort and were retained for
auditability.

Do not merge or cherry-pick any external Lane A, Lane B, or A+B RES4LYF
commit. The only proposed canonical change is the comfyui-modal commit chain
ending at `4421610c1a40`.
