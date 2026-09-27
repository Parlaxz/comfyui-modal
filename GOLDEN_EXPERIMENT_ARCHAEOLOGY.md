# Golden / ComfyUI Modal historical experiment archaeology

**Archaeology date:** 2026-09-16  
**Repository root:** `C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal`

This is a read-only reconstruction. No benchmark, deployment, checkout, reset,
clean, or source-file mutation was performed. The only files created/updated
for this pass are the four datasets and this report.

## Executive findings

1. **The closest recoverable match to the remembered clean cohort is the frozen
   Sep-14 Golden Standard 27-run cohort**, not a 30-run cohort. It is raw-backed,
   true-cold, valid, and exact-SHA on all 27 runs. Its request wall is **16.390–
   33.540 s** (median **17.729 s**), so it is not a cohort with every request
   below 14 s. Twenty-four runs are in the 16.39–19.34 s mode band; runs 7, 16,
   and 23 are preserved outliers. Only run 16 has an enlarged measured stage
   span; the other two outliers are mostly outside the stage span.
2. **The likely historical architecture behind the cleanest cold behavior is
   C0 / `golden_p1_parallel_io_v2_c0_persistent_fds_preadv_sickness_v2`:** 512 MiB
   POSIX shared-pinned arena, static E27 QD transport, source geometry QD2/128,
   32 MiB H2D/source blocks, persistent positioned FDs, `comfy_kitchen`, two
   C0 reader workers, and minimal restore. This is observed from the Sep-14
   capsule/profile, not inferred from the name.
3. **A separate 15-run C0-FD-ready cohort is also clean in correctness terms:**
   15/15 valid, true-cold, exact-SHA. It uses the same broad C0 family but an
   older receipt-bound deployment (`1784e640…`), QD2/128, 128 MiB slots,
   persistent FDs, and a C0 child process with two reader threads. FRR is
   approximately 9.95–35.32 s (median 10.679 s); the fast nominal rows do not
   establish a <14 s overall-request streak.
4. **The apparent “30 clean runs” is probably a conflation.** The Sep-14 V1/V2
   reproduction has 30/30 true-cold, valid, and non-pathological runs under its
   definition (no individual read >=5 s), but every observed output SHA is
   `ab3c08a9…`, while the expected SHA is `790c3052…`; it therefore is not a
   clean canonical-output cohort. Overall walls range from **16.482–160.619 s**
   (the raw index stores these as 16,482–160,619 ms), with
   several 20–57 s runs and one 160.619 s V2 outlier.
5. **No recovered comparable cohort has a longest streak with every overall
   request <=14 s.** In the 27-run exact-SHA cohort, zero of 27 are <=14 s. The
   best contiguous request-wall windows are still high: best 10-run window max
   28.297 s, best 20-run window max 32.300 s, and the full 27-run window max
   33.540 s. The remembered threshold may refer to a different boundary (stage
   span, source-read wall, or an unrecovered campaign), not the full request
   wall.

## Master evidence products

| Product | Content |
|---|---|
| `GOLDEN_HISTORICAL_RUNS_MASTER.csv` | 1,367 unique request/run rows, 112 columns |
| `GOLDEN_HISTORICAL_RUNS_MASTER.json` | Same run rows plus provenance, coverage, parsing, and limitation metadata |
| `GOLDEN_HISTORICAL_READS_MASTER.csv` | 18 per-read rows; only evidence that exposed recoverable per-read records |
| `RAW_EVIDENCE_INDEX.csv` | 6,300 source-to-result mappings with raw/derived classification |

The run corpus contains 1,519 attempt artifacts, 1,354 unique request IDs from
attempts, 1,074 `.v2ctl` run manifests, and 13 manifest-only rows. Duplicate
worktree/evidence-bundle copies are collapsed by request ID while all paths are
retained. Large deep-trace files were scanned with bounded field extraction;
unknown remains unknown.

## Candidate clean streaks and windows

| Candidate | Size | What is clean | What prevents a stronger claim | Exact evidence |
|---|---:|---|---|---|
| Sep-14 Golden Standard | 27 | valid + true-cold + exact output SHA, 27/27 | full request wall >14 s on 27/27; 3 request outliers | `.slim/worktrees/golden-io-v2/artifacts/golden_standard_2026-09-14/evidence/cohort_table.json`, `series_stats.json`, `run_index.json` |
| C0-FD-ready confirmations | 15 | valid + true-cold + exact output SHA, 15/15 | FRR/request outliers; separate old receipt-bound deployment | `.slim/worktrees/golden-io-v2/artifacts/golden_parallel_c0_fd_ready_additional10/additional15_index.json` and each listed attempt/event/summary |
| Sep-14 V1/V2 reproduction | 30 | true-cold + valid + no pathological read >=5 s, 30/30 | all observed SHA differ from expected; several large overall walls | `.slim/worktrees/golden-sep14-repro/SEP14_V1_V2_15x15_RAW_INDEX.json` and 30 local logs |
| E37 clean-lane QD4 | 1 | source wall 1,043.514 ms, H2D host 127.399 ms | n=1; not a full request; validation residual exceeded tolerance | `E37_CLEAN_LANE_ALGORITHM_RECOVERY_REPORT.md`, E38L audit |
| post-eager-start private split | 8 | 8/8 UNET loads below 1.9 s in the reported subset | one CLIP 2.956 s outlier; separate deployment retained a 66.4 s outlier | commit `57a5168`, `REPORT_C0_QD2_TAIL_CURE_FINAL_SOURCE_ATTRIBUTION_2026-09-13.md` |

The only per-read thresholded cohort with a complete raw index is the V1/V2
reproduction. Its “clean” condition is explicitly only `max_individual_read_ms
< 5000`, not `<250`, `<500`, or `<1000`. The 18-row reads dataset is a derived
O_DIRECT-shadow event table, not a replacement for missing raw per-read data.

## Exact configuration of the strongest candidates

### Frozen Sep-14 Golden Standard

**Observed:** profile `golden_p1_parallel_io_v2_c0_persistent_fds_preadv_sickness_v2`,
app `batch-tripwire-v2-p2hb2`, branch `exp/golden-io-process-v2`, baseline/deployed
source capsule based at `03ce249…` with deployed-byte provenance, GCP `us-east1`,
RTX PRO 6000, 24,576 MB, `comfy_kitchen`, minimal restore, model-free snapshot,
single-use containers, `restore_count=1`, `request_count=1`, exact output SHA
`ab3c08a9…7104f`. Effective selectors record static-E27 transport, source QD 4,
capacity 8, 32 MiB source/direct/H2D blocks, H2D depth 4, C0 source geometry
QD2/128, POSIX backing, streaming, persistent FDs, and preadv-sickness V2.

The capsule documents the C0 geometry as a 512 MiB shared-pinned arena with two
workers/four slots. The source profile and capsule are the authority; the master
CSV leaves individual fields blank when the raw row did not expose them.

### C0-FD-ready 15-run cohort

**Observed:** profile `golden_p1_parallel_io_v2_c0_persistent_fds`, app
`batch-golden-c0-fd-ready`, branch `exp/golden-io-process-v2`, remote deployed
commit `1784e640…`, QD2/128, 128 MiB slots, persistent FDs, 512 MiB arena,
`shared_to_pinned=0`, two source workers, and a CUDA-sterile C0 child. This is an
old-deployment cohort and must not be mixed with later source revisions.

### Sep-14 V1/V2 comparison

**Observed:** V1 profile `golden_p1_parallel_sep14_v1_preadv_control` versus V2
`golden_p1_parallel_sep14_v2_preadv`, 15 rounds per arm, 158 source reads per
row, `os.preadv`, and raw per-read walls. The raw index binds deployment
manifests, receipts, attempts, event artifacts, and local command logs. Every
row is marked non-pathological under the >=5 s definition, but the expected and
observed canonical SHAs disagree on all 30 rows.

## Historical architecture timeline

| Period / revision | Architecture | Observed evidence | Difference / interpretation |
|---|---|---|---|
| 2026-05/06 | Loader-cache / early V2 paths | CLIP about 3.0–3.5 s, UNET about 0.10 s, sampler about 8.75–9.01 s; remote total about 13.0–13.9 s, projected about 9.6 s on cache hit | Cache reduced CLIP work, but this was not the later true-cold Golden contract. |
| 2026-06/07 | Pure-source QD and FastSafe probes | 16-observation source-ceiling campaign; QD256/FastSafe comparison was not a full integrated winner. QD4 integrated CLIP was later about 2.6–2.9 s, not the probe-local 40–45 GB/s claim. | Probe throughput was page-cache/overlap sensitive and not an endpoint result. |
| 2026-08 | Golden Serial / P4 baseline | P4-4 five-run serial evidence was 22.4–88.9 s and non-cold; descriptive only. | Serial reference path and later parallel path must not be conflated. |
| 2026-08/09 | V2 shared backing + preadv, QD experiments | Prefault was rejected: about 17.316 s extra. SysV backing was slower (median about 19.704 s vs 15.939 s POSIX control). Treatment B QD2/128 improved control by about 218 ms in n=3. | POSIX and geometry were retained; SysV and prefault were not winners. |
| 2026-09-12 | C0 shared-pinned streaming | 512 MiB arena, four 128 MiB slots, QD2, two workers, direct registered-arena H2D, no shared-to-pinned copy. | Established the C0 transport shape used by the later clean cohorts. |
| 2026-09-13 | Persistent-FD treatment | 12 exact/cold/DNF-free rows; opens fell 61→2 for CLIP and 93→2 for UNET, but mean FRR slightly worsened 12,479→12,550 ms. | FD reuse was proven, but no material performance lever was shown. |
| 2026-09-13 | QD4/64 treatment | Medians worsened: CLIP about 2,127→2,585 ms and UNET 2,400→2,821 ms; maxima improved, with per-read max <=102 ms in the reported cohort. | Queue depth/read size changed tail shape, not a demonstrated median win. |
| 2026-09-13 | Eager-start + private split | Removed a reported 3,412 ms `Thread.start` stall, reducing startup to about 1.0–1.7 ms; sickness was attributed to file→private preadv rather than private→SHM. | Strong diagnostic association, not proof of a universal cause. |
| 2026-09-13 | C0-FD-ready | 15/15 exact, valid, true-cold confirmations; nominal FRR about 10.3–10.7 s with preserved outliers. | Strong historical candidate, but old receipt/source identity. |
| 2026-09-14 | Frozen Golden Standard | 27/27 exact/valid/true-cold; duration median 17.729 s, max 33.540 s; stage-span median 10.658 s, 25/27 in about 10.36–10.98 s. | Best exact-SHA historical cohort recovered, but not <14 s full request wall. |
| 2026-09-15 | V1/V2 Sep-14 reproduction | 30/30 valid/true-cold and no read >=5 s by the campaign definition; output SHA mismatch on all 30. | Clean I/O criterion and canonical correctness diverged. |
| 2026-09-16 | O_DIRECT shadow design | Tripwire shadow design classifies `DIRECT_ESCAPE`, `SHARED_STALL`, and `DIRECT_ERROR`, with 1/5/10 ms separation goals. | No counted production result was recovered; design only. |

## Correlations and non-causal observations

- **Persistent FDs:** open-count reduction is directly observed, but the paired
  performance result was neutral/slightly worse. It should not be credited as
  the cause of the clean cohort.
- **QD/read geometry:** QD2/128 is common to the strongest C0 cohorts. QD4/64
  reduced reported maxima but worsened medians. This is an association across
  separate campaigns, not a causal proof.
- **Process/thread topology:** the strongest named cohorts differ: the frozen
  Sep-14 capsule describes two C0 workers, while the additional-15 index records
  a CUDA-sterile child process with two reader threads. Their results should not
  be pooled as one architecture without source identity normalization.
- **Ordering/startup:** eager start removed a measured thread-start stall. The
  remaining sick-run attribution points to file→private preadv, but producer
  identity/fill telemetry was incomplete.
- **Restore/orchestration:** OLD20 vs NEW30 reconciliation found a large
  difference in outlier frequency with no effective-config difference; old
  >20 s rows correlated with restore >=50 ms and extreme CLIP/UNET envelopes.
  Operator gaps and orchestration spacing also differed. This is not enough to
  claim restore or spacing caused the difference.
- **Container/image:** the 27-run capsule holds image, snapshot, runtime-shape,
  workspace, and source identity constant across the cohort, which makes it a
  good internal consistency cohort. It does not establish behavior across
  containers, regions, or images.
- **Telemetry boundaries:** the 27-run report explicitly distinguishes request
  duration, stage span, and sampler wall. The historical “11.5–12.2 s” claim
  was not found as a recorded field; it appears closest to a stage-boundary
  interpretation, not the request duration.

## Contradictions and validity decisions

1. **Report vs raw:** the Sep-14 capsule's raw-backed table is authoritative:
   24/27 request durations are 16.39–19.34 s, not 11.5–12.2 s. The report's
   reconciliation is preserved and not rewritten.
2. **V1/V2 summary vs canonical correctness:** “30/30 no pathological read” is
   retained, but the SHA mismatch makes it unsuitable as an exact-output clean
   cohort.
3. **E27 source throughput:** the older 40–45 GB/s statement is retained as a
   historical probe claim, but later audits identify page-cache/overlapped-worker
   effects and integrated CLIP QD4 around 2.6–2.9 s. It is not used as endpoint
   evidence.
4. **E37 clean-lane result:** 1,043 ms is retained as source-lane evidence, but
   E38L records failed residual reconciliation; it is not treated as a full
   request result.
5. **Identity gaps:** Sage resolved value, deploy-time image identity, S4
   identity, and some console captures are unavailable in the strongest capsule.
   They remain unknown rather than guessed.

## Coverage gaps and next useful historical states

- Archives were indexed by name but not opened: `golden_c0_qd2_viztracer_forensics.zip`,
  `tripwire_v2_p2_evidence_2026-09-15.zip`, `tripwire_v2_sick_vs_nonsick_*.zip`,
  `tripwire_v2_wavea_fallback_all_evidence_2026-09-15.zip`,
  `viztracer_h100_evidence_2026-09-15.zip`, and compressed/bundle formats.
- Large deep-trace files were only partially field-scanned; nested stage/read
  data beyond the scan window may still be recoverable.
- June `benchmark_runs` under `cold-start-wall-clock-opt-20260606` and
  `experiment-axis-repeated-fields` were inventoried but not deep-read. They
  are the highest-value remaining search area for an older <14 s boundary.
- The most useful source states to investigate next are the exact deployed-byte
  Sep-14 capsule, commit `1784e640…` behind the 15-run C0-FD-ready cohort,
  the QD2/128 Treatment-B commit/profile chain (`2861b9e`→`d089fcb`), and the
  eager-start/private-split chain (`514f1a0`→`57a5168`).
- The O_DIRECT shadow tip `02b623f`/`61dd666` is useful for future diagnosis but
  has no historical counted-run result in the recovered surface.

## Audit trail

### Worktrees inspected

Main tree:
`C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal`.

`.slim/worktrees`: `golden-io-v2` (`b6ecd06`), `golden-p4-8-durability`
(`e5eb5ec`), `golden-sep14-repro` (`03ce249`, detached),
`odirect-shadow-sep14` (`02b623f`), `rx3` (`6f889df`).

Excluded C9 tree: `comfyui-modal-agent1-full-trace`, `agent2`, `agent3`,
`aws-rtx6000`, `c1-c5-c6-c8-tail`, `dc8`, `east1-composition`,
`exact-clip-conditioning-cache`, `memory-regression-fix`, `pagesfile-probe`,
`persistent-modal-handle`, `persistent-submission-v2`, `restore-structure`,
`sub13-diagnostic`, `teardown-billing-tail`, `vae-runtime-path`,
`vae-snapshot-seed`, plus the typo directory `comyui-modal-pagesfile-probe`
(not a Git repository).

Superpowers tree: `agent4-v2-loader-diagnostic`, `cold-start-wall-clock-opt-20260606`,
`experiment-axis-repeated-fields`, `golden-minimal-io`,
`golden-minimal-restore`, `kernel-first-step-prebuild`,
`production-fast-cleanup`, `runtime-snapshot-shape`, `sampler-parity`,
`studio-history-grid-carousel`, `vae-activation-after-sampling`.

### Branches and refs inspected

The complete output of `git branch -a -vv`, `git show-ref`, tags, and stash was
used as the ref inventory. Important inspected refs include `TESTING2`, `main`,
`exp/golden-io-process-v2`, `exp/golden-minimal-io`,
`exp/golden-minimal-restore`, `exp/odirect-shadow-sep14`,
`omos/golden-clip-forward`, `omos/golden-gc-suppression-exp3`,
`omos/golden-p4-7`, `omos/golden-p4-7b`, `omos/golden-p4-8-durability`,
`omos/golden-post-loop-tail`, `omos/golden-post-loop-tail-exp2`,
`omos/golden-rk-coeff-controller`, `omos/golden-rk-coeff-controller-exp2`,
`omos/golden-sampler-ab-integration`, `omos/golden-unet-p4-5`,
`omos/p0-golden-shared-primitives`, `omos/p4-2-golden-snapshot-runtime`,
`omos/p4-3-golden-clip-load`, `omos/p4-6-golden-sampler`,
`omos/rx1-qd4-telemetry-repair`, `omos/rx2-golden-sampling-decomposition`,
`omos/rx3-clip-forward`, `omos/rx6-golden-log-cleanup`,
`omos/rx6b-golden-waterfall-routing`, `omos/rx7a-static-e27`,
`bench/aws-rtx6000-8runs`, `r41-deterministic-golden-pipeline`,
`r42-golden-reconciliation`, `reconcile/p4-golden`, `rx7-static-e27`,
`sidecar/rv2b-parallel-research`, `p1/golden-integration`,
`production/final-stable-v21622`, `production/final-micro-optimizations-v21624`,
`archive-v2.16.23-96ce004`, and tag `golden-canonical-2026-09-09`.

Reachable history included 677 commits. Reflog/stash visibility included stash
`2b1e847`; no checkout was used.

### Important source/artifact directories

- `.v2ctl/` and `artifacts/` in the main tree.
- `.slim/worktrees/golden-io-v2/.v2ctl/`, `artifacts/`, `golden_history/`,
  and `config/v2/profiles/`.
- `.slim/worktrees/golden-sep14-repro/.v2ctl/`, `artifacts/`, and its 30 local
  V1/V2 logs.
- `.slim/worktrees/odirect-shadow-sep14/.v2ctl/`, `artifacts/`, and the derived
  O_DIRECT event table.
- `.slim/worktrees/golden-p4-8-durability/artifacts/` and `.v2ctl/`.
- `.config/superpowers/worktrees/comfyui-modal/golden-minimal-io/` and
  `golden-minimal-restore/`, especially `unetClipExperimentsSeptember/`,
  `golden_history/`, and their Golden artifact cohorts.
- Excluded C9 `comfyui-modal-c1-c5-c6-c8-tail/docs/` and
  `comfyui-modal-aws-rtx6000/docs/` for older loader/GPUs findings.

For exact row-to-file reproduction, start from `RAW_EVIDENCE_INDEX.csv`, then
follow `exact_raw_artifact_paths` in the run master. Raw artifacts outrank all
derived reports; discrepancies above are intentionally preserved.
