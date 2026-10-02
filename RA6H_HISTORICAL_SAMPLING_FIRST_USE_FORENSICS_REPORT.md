# RA6H Historical Sampling + First-Use Forensics

**Status:** read-only historical reconstruction for the RA6 remote off-vs-blocks experiment  
**Scope:** repository history, retained benchmark reports, raw logs, event streams, profiler artifacts, and first-use probes  
**Important:** no deployment was performed and no source file was changed for this report. Existing uncommitted work was left untouched.

## Executive conclusion

The historical record contains several different intervals that were all called
"sampling":

* **~3.7 s is not safe as a total.** The strongest directly aligned examples
  (`sampling_ms=3,719.513` and `3,668.282 ms`) begin at or near the first
  sampler step and omit the measured pre-first-step interval. The same magnitude
  also appears in older baseline tables without a raw boundary contract. The
  defensible classification is **MIXED: known partial in some records, otherwise
  unproven—not total**.
* **~4.9 s is the later authoritative sampling class when backed by
  `sampling_start → sampling_end`.** The three deep-profile runs measured
  4,917.454, 4,882.541, and 4,905.120 ms and reconciled to the event pair. The
  4.709–4.734 s E24 records are also complete wrapper spans, but are not the
  same span as the 3.64–3.68 s diffusion-loop metric. Classification:
  **TOTAL for the event-pair/wrapper class; MIXED if the label alone is used**.
* **~5.4–5.8 s is a real but heterogeneous class.** It includes later
  wrapper/variant sampler spans and an A100 median; it must not be folded into
  the ~4.9 s class without matching boundaries.
* **~6.3 s is not established as a historical Golden sampling wall.** The
  retained evidence does not contain a credible matching run for the cited
  PyTorch 4.497 → Golden 6.320 pair. The exact `6.3203` occurrence found in
  retained material is not a sampling duration. The pair remains
  **unproven as a repository-backed historical run**.

The later deep profile is the most useful RA6 comparator because it measures a
single host-clock interval and reconciles setup, per-step evaluations, and
teardown. It still does not directly time every controller, callback, residual,
or first native kernel event.

## Measurement rule used in this report

For every result, "authoritative sampling wall" means a named start/end pair,
preferably `sampling_start → sampling_end`, on one monotonic clock. A progress
bar, a `sampler_ms` field, a node-to-node interval, or a profiler category is
not promoted to total sampling without a boundary proof.

The current deep-profile contract explicitly uses the same monotonic clock as
the authoritative sampling events, records setup/per-step/teardown, and places
CUDA-event realization after `sampling_end`
(`comfymodal_runtime/sampling_deep_profile.py:6-17,37-45`). Its pinned workflow
expects 17 evaluations: 10 computes and 7 skips
(`comfymodal_runtime/sampling_deep_profile.py:79-83`).

## Authoritative historical table

`UNKNOWN` means the inspected retained evidence does not prove the value. A
cohort row is used where the source reports a bounded set of equivalent runs;
individual values are retained in the timing column.

| Date / commit | Backend | GPU / provider | Steps | Eval count | CacheDiT compute / skip | Visible tqdm | Authoritative sampling wall | Known first-pass contribution | Known post-loop contribution | Exact-output status | Profiler active? | Timing status | Confidence |
|---|---|---|---:|---:|---:|---:|---:|---|---|---|---|---|---|
| 2026-08-03 / `33d676d` (Phase-0 cold 1) | UNKNOWN | GCP; GPU name UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN / UNKNOWN | UNKNOWN | `3,703.695 ms` sampler field | UNKNOWN; no first-eval event | UNKNOWN | UNKNOWN | UNKNOWN | **UNPROVEN total**; stable sampler field only | Medium-high for value; low for boundary |
| 2026-08-03 / `33d676d` (Phase-0 cold 2) | UNKNOWN | GCP; GPU name UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN / UNKNOWN | UNKNOWN | `3,708.902 ms` sampler field | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | **UNPROVEN total** | Medium-high for value; low for boundary |
| 2026-08-03 / `33d676d` (Phase-0 replacement) | UNKNOWN | GCP; GPU name UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN / UNKNOWN | UNKNOWN | `3,717.706 ms` sampler field | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | **UNPROVEN total** | Medium-high for value; low for boundary |
| 2026-08-12 / `a6a755e` lineage, REAL CLIP R1 | UNKNOWN / RES4LYF present | GCP; exact region UNKNOWN | 8 | 17 | 10 / 7 | UNKNOWN | **4,917.454 ms**, event pair; metadata 4,917.456 | setup `57.359 ms`; step 0 total `1,128.7 ms`; `sampling_start → first_sampler_step` `1,186.1 ms` | teardown `6.78 ms`, final eval `2.615 ms` | Exact SHA recorded for run; prompt-specific hashes differ across R1–R3 | **Yes, blocks; status ok** | **TOTAL authoritative** | High |
| 2026-08-12 / `a6a755e` lineage, REAL CLIP R2 | UNKNOWN / RES4LYF present | GCP; exact region UNKNOWN | 8 | 17 | 10 / 7 | UNKNOWN | **4,882.541 ms**, event pair 4,882.549 | setup `50.005 ms`; first-step window represented; exact split not separately tabulated | teardown `7.377 ms`, final eval `3.016 ms` | Exact output recorded; hash differs by prompt | **Yes, blocks; status ok** | **TOTAL authoritative** | High |
| 2026-08-12 / `a6a755e` lineage, REAL CLIP R3 | UNKNOWN / RES4LYF present | GCP; exact region UNKNOWN | 8 | 17 | 10 / 7 | UNKNOWN | **4,905.120 ms**, event pair 4,905.126 | setup `51.02 ms`; first-step window represented | teardown `5.707 ms`, final eval `1.981 ms` | Exact output recorded; hash differs by prompt | **Yes, blocks; status ok** | **TOTAL authoritative** | High |
| Historical E24 ON #2 / report committed near `0ba7000` | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | **4,709–4,734 ms wrapper** | `1,067.597 ms` `sampling_start → first_sampler_step`; setup/compute split UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | **TOTAL wrapper, not comparable to loop field** | High for boundary distinction |
| Historical E24 ON #2 / same artifact | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | `3,639.628 ms` legacy `sampler_ms` | Omitted the pre-first-step window | UNKNOWN | UNKNOWN | UNKNOWN | **PARTIAL diffusion-loop span** | High |
| 2026-08-16 / D11 report artifact, Run 2 | UNKNOWN | RTX PRO 6000; provider/region not fully fixed in cited table | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | `4,758 ms` reported sampling | UNKNOWN | UNKNOWN | Exact SHA `20b10e…` | Profiler status UNKNOWN | Likely total report stage; raw boundary not retained in cited report | High for value; medium for semantics |
| 2026-08-16 / D11 report artifact, Run 5 | UNKNOWN | RTX PRO 6000; provider/region not fully fixed in cited table | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | `4,704 ms` reported sampling | UNKNOWN | UNKNOWN | Identical exact SHA | Profiler status UNKNOWN | Likely total report stage; boundary caveat | High for value; medium for semantics |
| 2026-08-16 / D11 report artifact, Run 6 | UNKNOWN | RTX PRO 6000; AWS/us-east-1 noted for run 6 | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | `4,937 ms` reported sampling | UNKNOWN | UNKNOWN | Identical exact SHA | Profiler status UNKNOWN | Likely total report stage; boundary caveat | High for value; medium for semantics |
| 2026-08-09 / `2909edb` GPU cohort, RTX arm | UNKNOWN | GCP; RTX PRO 6000 | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | `~3.75 s` median/class | UNKNOWN | UNKNOWN | Exactness reported 8/8 | UNKNOWN | Total arm-level sampler value; internal boundary UNKNOWN | High for value; medium for attribution |
| 2026-08-09 / `2909edb` GPU cohort, A100 arm | UNKNOWN | GCP; A100 | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | `~5.70 s` median/class | UNKNOWN | UNKNOWN | Exactness 3/3 | UNKNOWN | Total arm-level sampler value; platform effects present | High for value; medium |
| 2026-08-09 / `2909edb` GPU cohort, H100 arm | UNKNOWN | GCP; H100 | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | `~2.45 s` median/class | UNKNOWN | UNKNOWN | Exactness 3/3 | UNKNOWN | Total arm-level sampler value; application wall affected by transfer wait | High for value; medium |
| 2026-08-09 / `2909edb` GPU cohort, H200 arm | UNKNOWN | GCP; H200 | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | `~2.32 s` median/class | UNKNOWN | UNKNOWN | Exactness 3/3 | UNKNOWN | Total arm-level sampler value; application wall affected by transfer wait | High for value; medium |
| 2026-08-30 / `b578f77c…`, RA5 PyTorch | PyTorch / SDPA seam | RTX PRO 6000; GCP us-west1 | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | **6,233.634 ms** | UNKNOWN | UNKNOWN | Canonical SHA **pass** | Not requested for custom leaf | Authoritative request-local sampling wall; `n=1` | High |
| 2026-08-30 / `b578f77c…`, RA5 Comfy Kitchen | Comfy Kitchen native leaf | RTX PRO 6000; GCP us-east4 | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | **5,701.638 ms** | UNKNOWN | UNKNOWN | Canonical SHA **fail** (`62fd9e…`) | Native leaf captured, one event | Authoritative request-local sampling wall; `n=1` | High |
| 2026-08-30 / `b578f77c…`, RA5 Sage | Sage native SM89 leaf | RTX PRO 6000; GCP us-east4 | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | **5,538.917 ms** | UNKNOWN | UNKNOWN | Canonical SHA **fail** (`bfb360…`) | Native leaf captured, one event | Authoritative request-local sampling wall; `n=1` | High |

### Table interpretation

The table intentionally does not turn every report's `sampling` field into a
total. For example, D11 reports a credible stage value, but the retained cited
report does not expose the same event-pair contract as REAL CLIP R1–R3. The
RA5 rows are authoritative request-local windows but are one request per arm,
with different regions for PyTorch versus the two custom backends. Their total
request times are not attention timings.

## Best-supported additive decomposition

Only the following R1 decomposition is safe to treat as additive at the
top-level because the artifact explicitly reconciles it to one clock:

```text
sampling_start → sampling_end                         4,917.454 ms
  setup before first evaluation                          57.359 ms
  step 0 total                                          1,128.7 ms
    eval 0 / first actual compute                       618.6 ms
    gap                                                   45.8 ms
    eval 1 / later compute                               462.5 ms
    post-model                                             1.8 ms
  step 1 total                                           926.9 ms
    pre-model 3.6 + eval0 451.6 + gap 13.0
    + eval1 457.4 + post-model 1.3
  step 2 total                                           469.7 ms
  step 3 total                                           475.4 ms
  step 4 total                                           470.5 ms
  step 5 total                                           459.1 ms
  step 6 total                                           459.0 ms
  step 7 total                                           463.9 ms
  teardown                                                 6.78 ms
    final teardown eval                                   2.615 ms
  residual                                                 0.0 ms; status=ok
```

The displayed step rows and setup/teardown reconcile to the authoritative
window in `REAL_CLIP_CACHE_MISS_REPORT.md:333-345`. The per-evaluation cadence
is:

```text
compute: e0 e1 e2 e3 e5 e7 e9 e11 e13 e15       10
skip:    e4 e6 e8 e10 e12 e14 e16                7
```

`e16` is explicitly the final teardown eval
(`REAL_CLIP_CACHE_MISS_REPORT.md:364-381`). Compute totals were 4,695.1 ms
(R1), 4,682.2 ms (R2), and 4,699.6 ms (R3); skip totals were 30.5, 15.4, and
16.1 ms.

### Nested block evidence — not an additive second waterfall

Across the same R1–R3 deep profiles, reported NextDiT category totals were:

| Category | R1 | R2 | R3 | Status |
|---|---:|---:|---:|---|
| Attention | 728.183 ms | 724.770 ms | 728.644 ms | Directly measured hooked category |
| MLP | 268.785 ms | 268.947 ms | 266.684 ms | Directly measured hooked category |
| Norm | 70.919 ms | 65.122 ms | 64.903 ms | Directly measured hooked category |
| Embeddings | 61.877 ms | 62.391 ms | 63.328 ms | Directly measured category |
| Refiner | 106.771 ms | 104.171 ms | 111.471 ms | Directly measured category |
| Output | 4.663 ms | 4.239 ms | 4.572 ms | Directly measured category |
| `norm_gate_residual` | 670.951 ms | 689.303 ms | 689.585 ms | **Derived residual, not directly timed** |

The derived residual includes unhookable gate/modulate/residual operations and
launch/other gaps (`REAL_CLIP_CACHE_MISS_REPORT.md:386-406`). These category
rows are nested inside evaluations and must not be added to setup, steps, and
teardown or presented as an independent wall decomposition.

### Components that remain UNKNOWN inside the authoritative wall

* distinct RES4LYF/controller initialization and per-eval controller time;
* individual progress callback bodies and progress transport;
* exact first-native-kernel setup versus ordinary first-forward work;
* compiler/JIT duration or compile cache hit/miss;
* all unhookable transformer operations;
* full Golden internal sampler nesting outside the deep-profile artifacts;
* cleanup after `sampling_end` beyond the recorded final eval/teardown.

## Reconciliation of the historical timing classes

### ~3.7 s

Known direct examples:

* `c4_armA_retry4.log:411-419`: `sampling_ms=3,719.513 ms` versus
  `sampling_wall_ms=4,945.024 ms`.
* `c4_armA_retry6.log:388-396`: `sampling_ms=3,668.282 ms` versus
  `sampling_wall_ms=4,878.020 ms`.
* `V2_PHASE0_STEP3_BASELINE.md:56-73`: three stable sampler fields of
  3,703.695–3,717.706 ms, but no retained first-eval/event-pair proof in the
  table.

E24 resolves the boundary for its corresponding class: the 3,639.628 ms
legacy field aligns to `first_sampler_step → sampling_end`, while the wrapper
contains a measured 1,067.597 ms `sampling_start → first_sampler_step`
interval (`V2_BATCH_E24_CRITICAL_PATH_CLOSURE.md:330-348`). Therefore the
3.7 s class cannot be used as a total without an artifact-specific boundary
proof. It is **MIXED**, with the known console/log examples **PARTIAL**.

### ~4.9 s

The strongest evidence is the R1–R3 deep profile: 4.8825–4.9175 s from
`sampling_start` to `sampling_end`, with exact event reconciliation and
residual zero (`REAL_CLIP_CACHE_MISS_REPORT.md:333-345`). D11 independently
reports 4.704–4.937 s across a valid cold cohort
(`V2_D11_3_RUN_PERFORMANCE_2026-08-16.md:30-47`).

This is the appropriate historical **total sampling** class when the event
pair or equivalent wrapper contract is retained. It is not evidence that the
3.7 s number was an optimization of 1.2 s: E24 explicitly identifies the
difference as boundary semantics, not a proven diffusion-loop improvement.

### ~5.4–5.8 s

This class is credible but heterogeneous:

* D11 reports 4.704–4.937 s for its sampling stage, while its broader
  sampler-node-to-sampling preparation is 124.1–155.1 ms
  (`V2_D11_3_RUN_PERFORMANCE_2026-08-16.md:39-43`).
* Full-run variants include deep-profile values around 5.370 and 5.520 s.
* The Aug-9 GPU cohort reports an A100 class around 5.70 s.
* E24's 5.418 s sampler-node-to-sampling value is a broader node/interval
  boundary, not automatically pure sampling.

The class should remain a separate comparison bucket until steps, backend,
host/provider, profiler state, and start/end events are matched.

### ~6.3 s and faster/larger outliers

The RA5 authoritative PyTorch row is 6,233.634 ms, but it is a 2026-08-30
one-request native-backend diagnostic, not proof that the cited historical
Golden value was 6.320 s. The retained Aug-9 cohort reports faster sampler
classes on H100/H200 (2.45/2.32 s) and a slower A100 class (5.70 s), while
application walls were affected by transfer/platform waits
(`COMFYUI_MODAL_V2_AUG9_RESOURCE_GPU_OPTIMIZATION_REPORT.md:205-214,233-243`).
These are credible outliers, not interchangeable baselines.

## The cited visible-vs-Golden comparisons

The requested pairs are:

```text
PyTorch visible tqdm       ~4.497 s
Golden sampling            ~6.320 s
gap                        ~1.823 s

Kitchen visible tqdm       ~3.935 s
Golden sampling            ~5.435 s
gap                        ~1.500 s
```

### What the retained evidence proves

The exact pair, with a matching workflow identity, backend, host/provider,
steps, raw event stream, and profiler artifact, was **not found** in the
inspected repository evidence. Consequently the exact two gaps cannot be
causally assigned.

The historical record does establish mechanisms that can live outside a
visible later-loop progress interval:

1. **First-evaluation/first-step work is real.** R1 step 0 totals 1,128.7 ms,
   including a 618.6 ms first compute, 45.8 ms gap, and 462.5 ms second
   compute. Later step rows are generally about 459–476 ms
   (`REAL_CLIP_CACHE_MISS_REPORT.md:346-375`).
2. **The wrapper begins before the first sampler step.** The measured E24
   pre-first-step window is 1,067.597 ms, and the historical 3.64 s loop field
   starts at the first step rather than at `sampling_start`
   (`V2_BATCH_E24_CRITICAL_PATH_CLOSURE.md:334-343`).
3. **A small sampler-node boundary is distinct from that first-step window.**
   The measured removable node interval is 124.170 ms; it cannot explain a
   1.5–1.8 s gap by itself.
4. **Post-loop work exists, but is small in the deep profile.** R1–R3 teardown
   is 5.707–7.377 ms, with final teardown eval 1.981–3.016 ms. VAE/output
   stages occur after sampling and are not part of the authoritative sampling
   wall (`REAL_CLIP_CACHE_MISS_REPORT.md:228-232,340-344`).
5. **Older logs explicitly show RES4LYF registration**, but do not expose a
   distinct controller span (`deploy2_now.log:126-128`). Controller and
   callback time must therefore remain UNKNOWN, not be silently assigned to
   the gap.

### Gap verdict

**VISIBLE_LOOP_GAP_EXPLAINED=PARTIAL.** The measured first-step/wrapper
boundary explains roughly 1.07 s of the kind of difference that a later-loop
tqdm interval can omit, and the deep profile demonstrates a roughly 1.13 s
first step. The cited 1.50–1.82 s gaps are larger than that measured component;
without their raw streams, the remaining 0.4–0.8 s could be first-use,
controller/callback, or another telemetry boundary, but assigning it would be
guessing. No additive claim is made.

## First-use forensics

| Candidate cause | Historical measurement | What it proves | What it does not prove |
|---|---|---|---|
| Native checkpoint read/page-in | `1,623.7 ms` read for the 12.31 GB UNET payload; 1.35 s page-in component supported by zero-copy views and byte reconciliation (`V2_BATCH_C13_NATIVE_FAST_DISK_FORENSIC_AUDIT.md:21-29,74-96`) | Cold read is a large serial pre-sampling component | It is outside `sampling_start` in the cited native timeline; not a first sampler kernel cost |
| Construction / allocator warm-up | `get_model=383.4 ms` cold vs `35–83 ms` warm; fresh pre-read construction `2,390 ms`, warm `749 ms`, post-read `851 ms` (`C13:24,86`) | Allocator-sensitive first construction is measured | Exact allocator sub-operation and whether it occurs in a cited visible-vs-Golden pair are UNKNOWN |
| ModelPatcher work | C13 ctor `2.2 ms`, bind `109.6 ms` cold / `16–28 ms` warm; OC4 demand breakdown `837.042 ms`, including `821.083 ms` residual and `810 ms` thread CPU | Patcher/transfer-related work can be large and cold-sensitive | The residual is not line-by-line attributed; scopes differ from older `patcher_bookkeeping_ms=855.799 ms` and `9,610.763 ms` records |
| H2D | `2,468 ms` native H2D, `to_wall≈to_device`, no missing-page host stall (`C13:24-27,113-117`) | Native read and H2D are two serial passes | It is not hidden sampling work in the cited timeline |
| CUDA initialization | `cuda_init_ms` examples 74.550/79.840 ms and 3.550–9.500 ms in restore telemetry | CUDA init spans were observed | They are restore/setup spans, not module-specific first-kernel timing |
| Compilation | Sage + `torch.compile`: sampler `5,260 → 5,671 ms`, 8% slower (`working_optimizations.md:179-206`) | Compile can add overhead in this stack; Sage graph breaks are documented | No compile-start/end or first-eval compile duration was measured |
| CacheDiT startup | `cachedit_preparation=1,823.559 ms`; CacheDiT 1.2.3 import and preparation recorded (`deploy2_now.log:210-220`) | CacheDiT initialization can be a substantial setup interval | It is before the cited sampling window; no historic first-forward compute/skip timing in that log |
| CacheDiT first-forward cadence | Deep profile proves 17 calls / 10 computes / 7 skips and e0 is compute; skips are 2.6–8.0 ms and computes about 450–619 ms (`REAL_CLIP_CACHE_MISS_REPORT.md:364-384`) | First compute is slower and skips are materially cheaper | It does not isolate CacheDiT's own first-forward overhead from model/kernel warm-up |
| Attention backend first-use | Sage policy patch `5.5 ms`; CUDA import of `sageattention._fused` was blocked during snapshot (`deploy2_now.log:112-125,175-178`) | Backend setup/import state was observed | No first native attention-call duration or complete native profiler workload count |
| Sampler/controller init | Sampler-node-to-sampling `109–191 ms` in C5 and `132.655 ms` in generic first-node study; lane waits `0.06–0.09 ms` (`V2_GENERIC_FIRST_NODE_PRESAMPLER_DELAY_RESEARCH.md:138-146,189-203`) | Broad sampler boundary and tiny lane wait are measured | Controller construction and callback body are not isolated |
| Same-process contention | ImpactSwitch first pass 624.564/736.999/1,091 ms lies inside UNET read; implementation itself is microsecond-scale (`V2_GENERIC_FIRST_NODE_PRESAMPLER_DELAY_RESEARCH.md:130-146,189-203`) | A visible node timer can be inflated by contention during concurrent read/allocate | Exact GIL/scheduler/page-cache mechanism is unproven; do not transfer this number into sampling |
| VAE first-step activation | Transfer-only pre-copy `70.221 ms`, overlap `3,775.785 ms`, join wait `0.008 ms`; sampling 5,212.5 vs 4,797.7 ms in the A/B (`V2_BATCH_C5_VAE_FIRST_STEP_AB_REPORT.md:94-123,174-197`) | A 70 ms VAE transfer can be placed under sampling | The 759 ms A-path full-load worker is a different scope and cannot explain sampler gaps additively |

### First-use conclusion

The historical evidence supports real first-use effects, especially first
UNET/model evaluation, allocator-sensitive construction, CacheDiT startup, and
backend/import setup. It does **not** provide a complete first-eval causal
ledger for any cited 1.50–1.82 s visible-vs-Golden pair.

## RA5 native truth and Amdahl-style limits

RA5 is valuable because it closes the native-dispatch question for one
three-arm cohort:

| Arm | Native truth | Sampling | Relative to PyTorch | Exact output |
|---|---|---:|---:|---|
| PyTorch | 340 calls through shared SDPA seam | 6,233.634 ms | baseline | Canonical SHA pass |
| Comfy Kitchen | `comfy_kitchen::int8_attention` leaf observed; 340 public calls | 5,701.638 ms | 532.0 ms / 8.54% lower | SHA mismatch |
| Sage | SM89 native leaf observed; 1,246 `sageattn` calls | 5,538.917 ms | 694.7 ms / 11.15% lower | SHA mismatch |

Source: `RA5_NATIVE_ATTENTION_DIAGNOSTIC_RAW_LOG.md:47-78,91-106`.

This is **n=1 per arm**, with PyTorch in us-west1 and Kitchen/Sage in
us-east4. The native profiler captured one requested custom leaf event; it is
direct native evidence, not a full-workload kernel count. The prior 11-run
shootout had deep profiling off and proved callable selection, not native
execution (`RA5_ATTENTION_BACKEND_RAW_VALIDATION_LOG.md:168-181,207-242`).

Measured historical limits:

* In the R1–R3 blocks profile, direct attention category time is about
  725–729 ms inside a 4,882–4,917 ms sampling wall. If all of that category
  could disappear with no replacement cost, its arithmetic ceiling is about
  15% of that sampling wall. This is an upper bound, not an attainable claim:
  categories are nested, native leaf coverage is incomplete, and other work
  remains.
* The measured native RA5 reductions are 8.54% and 11.15% of the PyTorch
  sampling window. They are below that measured ceiling and are consistent with
  non-attention work limiting total improvement.
* R1 step 0 is 1,128.7 ms versus later step rows around 459–476 ms. Even if a
  backend made attention free, the first-step/setup, gaps, non-attention
  transformer work, callbacks/controller, and later compute would remain.
* The deep profile's `norm_gate_residual` is derived rather than directly
  timed; it must not be treated as a separately optimizable additive bucket.
* The older compile experiment made sampling 8% slower, so compile is not a
  measured source of headroom for this Sage-backed stack.

These statements use measured component sizes only. They do not claim that the
observed RA5 delta is caused entirely by attention, nor do they sum nested
spans into a fake waterfall.

## Questions RA6 remote blocks mode must answer

### Boundary and completeness

1. What exact events bound the authoritative wall: `sampling_start`,
   `sampling_end`, and any wrapper/node alternatives?
2. Is the reported value total or partial, and what interval is omitted if
   partial?
3. Does the artifact reconcile setup + every step + teardown to the event pair,
   with residual status and a single clock?
4. Are visible tqdm start/end events recorded separately from the authoritative
   wall?
5. Is final eval/teardown inside the wall, and is post-loop cleanup outside it?

### First evaluation and first use

6. What are setup-before-first-eval, pre-model gap, eval 0, post-model gap,
   later evals, and teardown values?
7. Is first native CUDA work separately identified from ordinary first forward?
8. Are CUDA module-load/JIT/compile events available from profiler, Nsight, or
   CUPTI rather than inferred from a slow first eval?
9. Is `torch.compile` enabled, and is compile start/end or cache hit/miss
   recorded?
10. Are allocator allocated/reserved/inactive/segment snapshots available
    before and after first evaluation?
11. Is ModelPatcher ctor/bind/load/transfer split from residual CPU work?
12. Is CacheDiT startup separated from its first forward, with per-eval
    compute/skip classification and timings?
13. Is attention backend import/policy setup separated from the first native
    attention call?
14. Is sampler/controller initialization separated from sampler-node boundary,
    callbacks, progress transport, and lane waits?

### Backend, reproducibility, and output

15. Which backend actually executed on the first call and on later calls:
    SDPA, native Kitchen, native Sage specialized leaf, generic Sage, or
    fallback?
16. Are native leaf counts full-workload counts or one-shot diagnostic captures?
17. Are steps, eval count, CacheDiT expected/actual counts, warmup, and skip
    interval recorded?
18. Are host GPU, provider, region, image/runtime identity, workflow, seed,
    profiler mode, and CacheDiT/Sage configuration frozen across arms?
19. Is the remote output byte-exact against the PyTorch/canonical reference?
20. Are invalid selector, warm-container, retry, and deployment-mismatch
    attempts explicitly excluded?

### Accounting guardrails

21. Are controller/callback/attention/non-attention spans nested or additive?
22. Are derived residuals labeled as derived and excluded from additive sums?
23. Are CUDA event realizations outside the sampling boundary, as required by
    the current contract?
24. Can every claimed visible-vs-authoritative gap be reproduced from raw event
    timestamps rather than a progress bar?
25. If a 1.5–1.8 s gap remains, which measured span accounts for it, and what
    remains explicitly UNKNOWN?

## Evidence index and limitations

Primary evidence:

* `REAL_CLIP_CACHE_MISS_REPORT.md:189-244,333-412` — raw event timeline,
  authoritative R1–R3 walls, evals, CacheDiT counts, block categories, and
  post-boundary CUDA synchronization.
* `V2_PHASE0_STEP3_BASELINE.md:52-73` — 2026-08-03 stable 3.70–3.72 s
  sampler fields and cold-run context.
* `V2_D11_3_RUN_PERFORMANCE_2026-08-16.md:30-65` — 4.704–4.937 s cohort,
  exact SHA, provider note, and invalid-run exclusions.
* `V2_BATCH_E24_CRITICAL_PATH_CLOSURE.md:330-348` — wrapper versus loop
  boundary proof and 1,067.597 ms pre-first-step interval.
* `c4_armA_retry4.log:411-419` and `c4_armA_retry6.log:388-396` — direct
  3.7 s versus 4.88–4.95 s mismatches.
* `RA5_NATIVE_ATTENTION_DIAGNOSTIC_REPORT.md:48-111` and
  `RA5_NATIVE_ATTENTION_DIAGNOSTIC_RAW_LOG.md:36-106` — native backend truth,
  timing, output gates, and n=1 limits.
* `V2_BATCH_C13_NATIVE_FAST_DISK_FORENSIC_AUDIT.md:20-29,74-96,121-153` —
  read/allocator/bind/H2D first-use measurements.
* `V2_BATCH_C5_VAE_FIRST_STEP_AB_REPORT.md:94-123,174-204` — measured
  first-step overlap and scope caveat.
* `V2_GENERIC_FIRST_NODE_PRESAMPLER_DELAY_RESEARCH.md:125-203` — first-node
  contention and sampler-node boundary measurements.
* `deploy2_now.log:112-128,175-220` — Sage import/policy and CacheDiT startup.
* `working_optimizations.md:179-209` — compile experiment.

Coverage is substantial but not exhaustive: ignored/remote-only artifacts and
older logs may not exist in this worktree; several current files were modified
after the knowledge-graph generation. Native source reads were used for the
material claims. Absence therefore means **not found in inspected retained
repository evidence**, not proof that a remote-only artifact never existed.

## Final status

RA6H_COMPLETE=YES  
HISTORICAL_3_7S_CLASSIFICATION=MIXED  
HISTORICAL_4_9S_CLASSIFICATION=TOTAL  
FIRST_EVAL_OVERHEAD_HISTORICALLY_QUANTIFIED=YES  
VISIBLE_LOOP_GAP_EXPLAINED=PARTIAL  
AUTHORITATIVE_HISTORICAL_TABLE_READY=YES  
RA6_REMOTE_QUESTIONS_READY=YES  
REPORT=RA6H_HISTORICAL_SAMPLING_FIRST_USE_FORENSICS_REPORT.md
