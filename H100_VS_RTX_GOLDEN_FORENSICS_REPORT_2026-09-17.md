# H100 vs RTX 6000 Pro Golden forensics — 2026-09-17

## 1. Executive diagnosis

The H100 runs are not explained by “H100 is slower.” The evidence separates at
least three effects:

1. **H100 load is source/read dominated.** In the H100 telemetry,
   `SOURCE_TOTAL_WALL_MS` is almost entirely
   `SOURCE_SYSCALL_UNION_BUSY_MS` (median residual 3.53 ms for CLIP and 3.55
   ms for UNET). The observed read latency has clustered pathological episodes:
   9 CLIP reads and 7 UNET reads were >=1000 ms; these occur in 3/11 and 1/11
   requests respectively. This proves where the H100 wall is, not whether the
   latency originates in remote storage, the host kernel, or destination-side
   buffer work.
2. **The H2D stream is mostly waiting, not copying.** H100 median CLIP H2D
   span is 1875.98 ms, but active copy is 245.82 ms and idle inside the copy
   stream is 1698.72 ms. UNET is 2979.67 / 413.64 / 2524.70 ms. The copy
   engine is therefore source-starved. Post-source tails are only 2.73 ms
   (CLIP) and 2.28 ms (UNET).
3. **The H100 has a separate CLIP-forward regression/measurement question.**
   H100 `clip_forward_total_ms` median is 2122.65 ms versus 1433.98 ms for the
   RTX reference, while H100 sampling is faster: 3725.40 versus 4641.50 ms.
   Existing H100 forward conversion diagnostics are `NOT RUN` and compute dtype
   is `UNPROVEN`; the current boundary is a wall interval around the wrapped
   encode path, not proof of pure GPU kernel time.

The strongest conclusion is therefore: **H100 load stages are currently
source-stalled and placement/transport-sensitive, while sustained sampler
compute is healthy.** An H100-specific storage, PCIe, NUMA, or copy-engine
hardware conclusion is not yet established because the RTX reference lacks
source/H2D wall telemetry and uses materially different transport geometry and
runtime source.

## 2. Identity, populations, and validity

### H100 deployed identity

- Analysis worktree: `C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal`
- H100 evidence worktree: `.slim/worktrees/authoritative-golden-core-sep14`
- H100 app: `batch-tripwire-v2-p2hb2`, method `run_golden_parallel_stream`
- Deployed source commit: `d1fffd2f5da108f0a718ea80da56152ae29f9c57`
- Deployment receipt fingerprint: `668b088e9a8c4d03b2f4c6eda50666e5e85306ac47d7824557e796230a09d1c0`
- H100 run identity: deployment `fd5d4012…`, snapshot
  `38c8a05a…`, config `ad50bef8…`, image `im-ZWhbnmH2ESAt0RqaMnZg8Q`
- Profile: `golden_p1_parallel`; observed GPU: `NVIDIA H100 80GB HBM3`
- Workflow SHA: `e44389ea2eda82ba5e2328acc08307b6879ed6d4ea4b030727ab044704c0d3b5`
- Attention: configured/resolved `comfy_kitchen`; residency `bf16`; Sage input
  `baked_cuda`, resolved value empty; compute dtype proof `UNPROVEN`
- Transport: `static_e27`, block `33554432` bytes, 8 staging slots, E27 proof
  `YES`; true-cold proof is present for every populated row.

The deployment manifest records `git_head=d1fffd2…`, dirty
`config/v2/modal_target.toml`, and source-probe module hashes. Its provenance
validation status was `not_checked`; image identity was not observed at deploy;
those are provenance limitations, not reasons to discard the timing rows.

### Populations

- H100: 11 populated true-cold requests, all retained for performance analysis;
  all have `restore_count=1`, `request_count=1`, `min_containers=0`, and
  single-use containers.
- RTX: 84 valid rows from the exact reference commit
  `03ce24916958596717220167db496b1215544d09`; 2 invalid rows are retained as
  exclusions. The RTX index has 86 rows for that commit.
- RTX rows share logical workflow/backend/block/slot/bf16 match keys, but not
  identical runtime source, profile, image, snapshot, or transport geometry.

## 3. Stage comparison

Medians are over H100 n=11 and RTX n=84. Times are ms. `sampler_total_wall_ms`
is used for the sampler control; it is not added to nested stage children.

| Metric | RTX | H100 | delta | delta % | status |
|---|---:|---:|---:|---:|---|
| restore total | 3.289 | 3.387 | +0.098 | +3.0% | comparable boundary; no regression established |
| CLIP load | 1813.514 | 3673.497 | +1859.983 | +102.6% | H100 slower |
| CLIP forward | 1433.984 | 2122.655 | +688.671 | +48.0% | boundary not pure GPU proof |
| UNET load | 1685.063 | 3343.692 | +1658.629 | +98.4% | H100 slower |
| sampler total | 4641.497 | 3725.400 | -916.097 | -19.7% | H100 faster |
| VAE load | 86.466 | 195.346 | +108.880 | +125.9% | H100 slower; source-sensitive tail exists |
| VAE decode | 537.320 | 551.174 | +13.854 | +2.6% | effectively similar |
| FIRST_RESULT_READY from parallel entry | 10841.708 | 16984.897 | +6143.189 | +56.7% | same raw event/boundary; H100 slower |

The raw `FIRST_RESULT_READY` event, measured from the parallel method entry, is
12,269.18–29,996.90 ms for H100 (median 16,984.90; p90 20,693.48) and
10,286.16–24,382.19 ms for RTX (median 10,841.71; p90 15,996.99). The RTX
summary index omits this field, but the raw attempts referenced by the index
retain the same event and boundary; the canonical endpoint file parses those
raw attempts directly. `overall_request_ms`/`duration_ms` remains a separate
enclosing metric and is not substituted for first-result time.

RTX source-wall, syscall-union, H2D-wall, overlap, and post-source-tail fields
are unavailable in 84/84 RTX rows. Consequently there is **no valid RTX-vs-H100
source-throughput delta** in this corpus. RTX stage-effective throughput can be
computed from model bytes divided by enclosing load, but it must not be called
source throughput.

## 4. H100 source-read and H2D decomposition

Decimal GB/s means bytes / 10^9 / seconds.

| role | load median | source wall | syscall union | H2D span | active copy | idle in span | post-source tail | source GB/s | active-copy GB/s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| CLIP | 3673.50 | 1927.21 | 1923.80 | 1875.98 | 245.82 | 1698.72 | 2.73 | 4.17 | 32.73 |
| UNET | 3343.69 | 3035.41 | 3033.13 | 2979.67 | 413.64 | 2524.70 | 2.28 | 4.06 | 29.76 |

The enclosing-load residuals are 1147.85 ms for CLIP and 324.17 ms for UNET;
they are real stage residuals, not source or copy time. H2D span is 97–98% of
source wall. Active copy is only about 13% of H2D span in both roles; the rest
is stream starvation/idle. `SOURCE_H2D_OVERLAP_MS` medians are 450.15 ms CLIP
and 690.15 ms UNET. This is why H2D wall must not be described as the time the
GPU needs to copy the model.

Direct RTX active-copy telemetry is available, but is not an apples-to-apples
hardware test: RTX uses 61 CLIP / 93 UNET submissions, a 512 MiB arena, zero
source opens in the retained rows, and 3 tail submissions; H100 uses 243 / 370
submissions, a 256 MiB arena, 4 source opens, and 7 tail submissions. The RTX
active-copy medians are 148.20 ms / 54.28 GB/s CLIP and 225.19 ms / 54.66
GB/s UNET. These numbers establish a transport-geometry difference and a
capability contrast, not a silicon-only conclusion.

## 5. Raw read sickness analysis

Across the 11 H100 requests there are 2673 CLIP and 4070 UNET source reads.
The aggregate read-latency distributions are:

| role | p50 | p90 | p95 | p99 | max | reads >=250 | >=500 | >=1000 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| CLIP | 21.07 | 33.09 | 39.78 | 456.70 | 3927.61 | 43 | 25 | 9 |
| UNET | 22.41 | 33.01 | 38.72 | 115.21 | 3101.37 | 27 | 17 | 7 |

At request level, CLIP has max-read >=250/500/1000 ms in 6/6/3 of 11 requests
and load >=5000 ms in 4/11. UNET has max-read >=250/500/1000 ms in 5/4/1
requests and load >=5000 ms in 2/11. The episodes are clustered rather than a
uniformly slow read population. Examples include healthy CLIP followed by sick
UNET (`sines-2`), sick CLIP followed by healthy UNET (`CANADA-2`), and both
roles with healthy or pathological episodes in the same request. This directly
supports a transient request/stage state, not a fixed “all H100 storage is 1
GB/s” explanation.

The exact RTX sickness comparison is unavailable: the RTX index does not retain
the corresponding syscall wall/read-latency stream. Therefore “more frequent or
more severe on H100” is not proven against the RTX corpus; it is only observed
inside H100.

At the canonical 500 ms threshold, CLIP onset is born-sick 3, becomes-sick 3,
never-sick 5; UNET is born-sick 1, becomes-sick 3, never-sick 7. No request
ends on a sick read. The onset/recovery derivation records alternating episodes
in 5 CLIP and 3 UNET requests, plus one single-episode request in each role;
the complete classifications are in `h100_read_onset_recovery.json`.

## 6. Provider/region natural experiment

All 11 H100 requests are visible below. `src` is source GB/s and `copy` is
active-copy GB/s; both are decimal. Small cells are descriptive only.

| request | provider / region | CLIP load / src / copy | UNET load / src / copy | CLIP fwd | sampler |
|---|---|---:|---:|---:|---:|
| a4f66843ed5b | AWS / us-west-2 | 5384.8 / 2.71 / 13.59 | 5486.5 / 3.55 / 13.48 | 3059.5 | 4038.3 |
| bd8ea2348bd5 | unspecified / CANADA-2 | 8891.6 / 1.03 / 43.84 | 2280.6 / 6.26 / 46.31 | 1813.3 | 3698.2 |
| a157324ed1d0 | GCP / asia-northeast1 | 2632.0 / 5.02 / 24.17 | 2783.8 / 5.00 / 26.62 | 2122.7 | 3725.4 |
| 4a3a9df54ab7 | GCP / asia-northeast1 | 2512.4 / 5.70 / 24.74 | 2431.8 / 5.84 / 25.44 | 2107.5 | 3656.9 |
| 94a52e483709 | unspecified / sines-2 | 2454.0 / 6.03 / 32.73 | 12950.7 / 0.97 / 43.39 | 5023.6 | 3743.5 |
| f98520a50bf1 | Azure / centralus | 5089.1 / 2.24 / 45.23 | 4031.5 / 3.52 / 45.14 | 2500.2 | 3757.1 |
| 2a264d69ee85 | GCP / us-east4 | 2917.3 / 4.55 / 24.40 | 3105.5 / 4.48 / 24.99 | 2136.4 | 3855.7 |
| 207a82424ea6 | GCP / asia-northeast1 | 2535.4 / 5.72 / 26.55 | 2576.3 / 5.46 / 26.40 | 2144.3 | 3783.9 |
| 5ad28bce7dd5 | unspecified / chicago | 3673.5 / 4.17 / 45.42 | 4301.2 / 3.97 / 29.76 | 1632.2 | 3548.9 |
| 65b7ddf18846 | OCI / us-chicago-1 | 4788.8 / 2.30 / 42.23 | 3343.7 / 4.06 / 38.73 | 2100.3 | 3647.5 |
| bf1abb3bd594 | unspecified / denver | 7806.6 / 1.38 / 43.58 | 4871.3 / 2.92 / 39.58 | 1937.0 | 3655.6 |

The same-request reversals are decisive against a single fixed host-rate story:
CANADA-2 is CLIP 1.03 GB/s versus UNET 6.26 GB/s, while sines-2 is CLIP
6.03 GB/s versus UNET 0.97 GB/s. Placement association is supported; provider
ownership or causal region claims are not. Eight cells have n=1 and the only
repeated cell has n=3.

## 7. CLIP forward

The source boundary is `golden_clip_forward` / the wrapped CLIP encode ledger:
forward entry to forward return, with a separate `clip_forward_gpu_ms` field
when available. The code path is in `golden_serial.py` and
`clip_forward_forensics.py`; the H100 corpus has `clip_forward_conversion` and
parameter-scope diagnostics marked `NOT RUN`, so the raw corpus does not split:

`entry -> CPU preparation -> first CUDA submit -> first completion -> encoder
kernels -> synchronization -> output materialization -> return`.

H100 forward has no useful evidence of correlation with source/load: the small
sample is dominated by mixed placement and timing boundaries. It does show a
faster sampler alongside a slower forward, which weakens “H100 GPU compute is
intrinsically slow” and leaves CPU preparation, first-use library/JIT work,
backend behavior, synchronization, and measurement scope unresolved. SM90 JIT,
NUMA, and CPU-side preprocessing are hypotheses, not findings.

## 8. Sampling control

All H100 runs report 8 effective sampler steps, `comfy_kitchen` attention, and
`res4lyf_gc_suppression` applied. Sampler totals are 3548.85–4038.27 ms (median
3725.40), much tighter than CLIP/UNET load. The sampler is faster than the RTX
median by 916.10 ms. This is positive control evidence that sustained workload
execution on the H100 is healthy; it does not prove that every earlier CUDA
operation is healthy or that CLIP forward has the same boundary.

## 9. Code/config drift

The H100 source is three commits after the RTX reference:

| difference | classification | effect |
|---|---|---|
| `modal_app.py`: minimal restore became Golden-profile default; restore probes/canary suppressed | performance-relevant | changes restore path and restore measurement; observed restore medians remain similar |
| `model_preload.py`: optional host-info probe omitted on minimal restore | performance-relevant only for restore | cannot explain model-load wall from current evidence |
| `tools/benchmark_v2_direct.py`: bounded 900 s stream consumption | likely irrelevant to stage timing | client-side hang protection, not remote load/sampling work |
| added tests and restore audit document | irrelevant | no runtime path |

`golden_serial.py`, the core H100/RTX logical workflow, backend label, block
size, staging-slot count, residency label, and workflow SHA are reported equal
at the logical identity layer. But the deployed source is not the RTX source,
transport geometry is different, and RTX has multiple profiles/images/snapshots.
The H100 deployment also has an unresolved attempt deployment identity versus
manifest combined hash (`fd5d40…` versus `668b08…`); the extractor preserves
both without assuming equal hash domains. No timing delta is attributed to GPU
silicon until these differences are controlled.

## 10. Output SHA analysis

- H100 observed SHA: exactly one value, `3a6a03064c7e6e01ede339ada63daaea4cbf793f387f4faadbb101a787024577`, in 11/11 requests.
- H100 manifest expected SHA: `ab3c08a952521a2d20e2ca31a2deff3c72a45e9aacf95365e62a436cdac7104f`, in 11/11.
- H100 in-run `golden_output` expected SHA is separately recorded as
  `790c3052a9b4a5ed01369e81cf79eac389f1d69b25578be3aa033e673570e89d`; this
  internal expectation disagreement is unresolved.
- RTX observed SHA is the old expected SHA in 84/84 indexed valid rows (one
  output-match field is unknown), with no overlap with H100 observed SHA.

The single deterministic H100 output across all 11 requests is consistent with
a deterministic architecture/backend/source-path numerical variant and is not
evidence of random corruption. It does not prove architecture is the cause
because H100 source/config drift remains. Performance rows remain useful because
the SHA failure is an exactness-validity failure, not a missing request or a
transport failure. Do not redefine the expected SHA.

## 11. Theory matrix

| theory | classification | evidence / limit |
|---|---|---|
| H100 compute intrinsically slower | contradicted for sampler; unresolved for CLIP forward | sampler is 19.7% faster; forward boundary is contaminated/undivided |
| H100 source path slower | supported within H100; cross-GPU unresolved | source dominates H100 load, but RTX source wall is absent |
| source sickness more frequent/severe on H100 | unresolved cross-GPU | H100 has clustered >=250/500/1000 ms reads; RTX read stream unavailable |
| provider/region placement effect | supported as association, causal effect unresolved | 5–6x H100 source spread; n=1 cells and mixed RTX regions |
| active H2D slower | unresolved as hardware claim | H100 active copy is lower than RTX, but geometry and code differ |
| H2D merely source-starved | supported within H100 | idle is 85–91% of H2D span and source/H2D walls nearly coincide |
| PCIe/topology/NUMA | unresolved | no controlling topology/NUMA evidence |
| pinned-memory behavior / QD / block mismatch | supported as confounder; causal winner unresolved | 256 MiB vs 512 MiB arenas, 243/370 vs 61/93 submissions |
| code/config drift | supported blocker | H100 is `d1fffd2`, RTX is `03ce249`; restore path changed |
| CLIP first-use/JIT/library initialization | unresolved | forward diagnostics were not run |
| attention/dtype/Sage difference | weakened but not closed | attention and requested bf16 match; compute dtype and Sage resolution are unproven |
| restore regression | weakened | restore totals are near-equal; H100 source/load dominates |
| snapshot regression | unresolved for platform restore; weakened for Python restore | snapshot/image proof is incomplete, Python restore is small |
| CPU-side CLIP work | unresolved | no CPU interval instrumentation |
| measurement artifact | supported as a risk for forward/total; not sufficient for load decomposition | semantic boundaries are known, sub-boundaries are not |
| multiple independent regressions | supported | source sickness/placement, transport geometry, and CLIP-forward scope coexist while sampling is stable |

## 12. High-confidence findings and remaining unknowns

### High confidence

- The 11 H100 requests are true-cold, retained, and performance-usable despite
  exact-output invalidity.
- H100 CLIP/UNET load walls are source/syscall dominated; H2D spans are mostly
  waiting; actual copy active time is a minority of the span.
- H100 read sickness is clustered and can reverse between CLIP and UNET in the
  same request.
- Sampling is faster and materially tighter on H100 than on the RTX population.
- The H100 source identity differs from the RTX reference and has restore-path
  changes; current HEAD is neither reference identity.
- H100 output variation is deterministic across this corpus.

### Remaining unknowns

- remote-source versus destination/kernel cause of each `preadv` stall;
- whether H100 active-copy differences survive identical transport geometry;
- whether provider/region, PCIe, NUMA, pinned allocation, or QD causes the
  placement spread;
- what fraction of CLIP forward is CPU preparation, first-use initialization,
  actual encode, synchronization, or output materialization;
- whether the H100 SHA is architecture-specific or caused by the source/config
  delta; and which of the two H100 expected SHA values is authoritative.

## 13. Minimum next action

Do not start the frozen 20+20 resource experiment. The smallest decisive next
measurement is one controlled paired request on one fixed region and one exact
source/config/profile, with both GPU paths emitting the same per-read source
wall, syscall union, H2D span, active copy, idle, tail, transport geometry, and
the six CLIP-forward boundaries. This is a measurement/identity repair, not an
optimization campaign. Until it exists, the highest-leverage action is to fix
the missing RTX source-wall telemetry and audit the CLIP-forward boundary.

## Audit manifest

- Starting analysis commit: `711f7cfb932e2d44f7dc285441e9cd5f827cdd30`, dirty
  worktree; no unrelated changes were reset.
- RTX reference commit: `03ce24916958596717220167db496b1215544d09`.
- H100 deployed commit: `d1fffd2f5da108f0a718ea80da56152ae29f9c57`.
- Resulting analysis commit: none.
- Report: `H100_VS_RTX_GOLDEN_FORENSICS_REPORT_2026-09-17.md`.
- Extractor: `tools/analysis/h100_vs_rtx_forensics.py`.
- Canonical derived dataset: `reports/h100_vs_rtx_forensics_2026-09-17/`.
- H100 raw dossiers: `.slim/worktrees/authoritative-golden-core-sep14/H100_GOLDEN_RUNS_EMAIL_2026-09-17.md` and `H100_GOLDEN_RUNS_FULL_2026-09-17.md`.
- H100 raw artifacts: `.slim/worktrees/authoritative-golden-core-sep14/artifacts/phase_p1_parallel_golden_v1/cohort_*/{attempt_0.json,attempt_0_events.json,manifest.json,summary.json}`.
- H100 deployment/source evidence: `.slim/worktrees/authoritative-golden-core-sep14/.v2ctl/deployments/receipt_5_668b088e9a8c4d03b2f4c6eda50666e5e85306ac47d7824557e796230a09d1c0.json`, matching deploy manifest, and `.v2ctl/source-probes/probe_5_668b088e9a8c4d03b2f4c6eda50666e5e85306ac47d7824557e796230a09d1c0.json`.
- RTX raw index: `GOLDEN_HISTORICAL_RUNS_MASTER.json` / `.csv`; raw artifacts are the `exact_raw_artifact_paths` named by those rows, principally under `.slim/worktrees/golden-io-v2/artifacts/phase_p1_parallel_golden_v1/cohort_*/` and `.slim/worktrees/golden-sep14-repro/artifacts/phase_p1_parallel_golden_v1/cohort_*/`.
- Derived outputs: `h100_per_run_rows.{json,csv}`, `rtx_reference_rows.{json,csv}`, `stage_transport_decomposition.{json,csv}`, `provider_region_table.{json,csv}`, `h100_endpoint_timings.{json,csv}`, `sha_analysis.json`, `source_config_identity_inventory.json`, `code_diff_inventory.json`, plus the read/onset/contrast files generated by the extractor.
- Proposed instrumentation (not applied/deployed/invoked): `reports/h100_vs_rtx_forensics_2026-09-17/proposed_clip_forward_boundaries.patch` and its `proposed_clip_forward_boundaries_README.md`; `git apply --check` and offline CPU/compile validation passed against `d1fffd2`.
- Exclusions: H100 exact-output mismatch is retained, not dropped; two empty H100 cohort directories are reported; RTX has 2 invalid exact-commit rows excluded from valid medians but retained in the index; RTX source/H2D wall fields are unavailable and never synthesized; no deployment, Modal invocation, request, optimization, or frozen experiment was run.
