# OC3 — CLIP-Forward Timing-Boundary and Completeness Audit

Date: 2026-08-25 · Batch: OC3 (READ-ONLY audit; no deploy, no paid run, no source change, no architecture recommendation)
Scope: determine what historical CLIP-forward timings actually measure relative to a serialized GoldenClipForward part.
Deliverable pair: this file + `OC3_CLIP_FORWARD_TIMING_CLAIMS_2026-08-25.csv` (one row per timing claim).

---

## 0. Evidence-inventory caveat (read first)

Requested sources **not found anywhere on disk** (searched `comfyui-modal`, `comfyui-modal-r42`, `comfyui-modal-r41.disabled`, all of `AI HUB`, including hidden dirs, filenames and contents):

| Requested | Status on disk |
|---|---|
| reconciled Phase-O SoT | ABSENT (no file named/containing "Phase-O"; closest surviving reconciliation of the E37 serial chain is `E38B…AUDIT.md` §"Ledger serial chain", quoted in §7) |
| v2.1 | ABSENT |
| O3 / O6 / O7 / O8 | ABSENT as documents. Only surviving O-series fragment: the CLIP weight-storage owner table O1–O5 inside `E38A_SNAPSHOT_REACHABILITY_AND_CLIP_EXCLUSION_AUDIT.md` §4 (O3 = "External Comfy model-management entries", tier UNKNOWN). O6–O8 unrecoverable. |
| OB4 / OB7 / OB8 | ABSENT (no `OB*` files or references anywhere) |
| OC1 / OC2 (enum definitions) | ABSENT. The three classification labels are applied exactly as spelled in the batch brief; their OC1/OC2 formal definitions were not recoverable in this environment. |

Everything below is derived from primary artifacts (`run_001_sample.json` ledgers/traces), exact source text, and the surviving E37/E38/K-series reports. Nothing was manufactured.

---

## 1. Evidence inventory

### 1.1 Run artifacts (canonical ledger + full trace)

| Run dir (`comfymodal-data\benchmarks\runs\`) | Request | Class | CLIP forward ledger span |
|---|---|---|---|
| `v2_2026-08-21_22-35-45` | `v2-benchmark-0-c9ac6e750942` | E37 healthy clean-lane QD4 (anchor) | s17 `CLIP forward` **1110.221 ms** |
| `v2_2026-08-21_16-00-22` | `v2-benchmark-0-ff69a4c9f3da` | E36 QD4 ARM-B **full normal path** (slow-vs-clean comparator) | s18 `CLIP forward` **5985.017 ms** |
| `v2_2026-08-21_22-34-15` | `v2-benchmark-0-c76e8bc0e7c6` | bad clean-lane run (same profile as E37) | s17 `CLIP forward` **4413.902 ms** |
| `v2_2026-08-25_02-55-12` | `v2-benchmark-0-61b4e2bd9f9e` | REF current-class pre-K1 (GCP us-east1) | s15 `CLIP forward` **1865.112 ms** |
| `v2_2026-08-25_06-51-50` | `v2-benchmark-0-8e43af5eed14` | K1 Run 1 selected path (GCP us-east1) | s15 `CLIP forward` **2037.321 ms** |
| `v2_2026-08-25_15-34-30` | `v2-benchmark-0-d31bdac8de3c` | K5 RUN1 (us-east1, unpinned) | s15 `CLIP forward` **4890.316 ms** |
| `v2_2026-08-25_16-00-31` | `v2-benchmark-0-ffab0ae32e31` | K5 RUN2 (us-west1, unpinned) | s15 `CLIP forward` **3545.669 ms** |
| `v2_2026-08-25_16-04-15` | `v2-benchmark-0-55a7945a5d6e` | K5 RUN3 (us-west1, unpinned) | s15 `CLIP forward` **2006.763 ms** |

### 1.2 Source code

| File | Role |
|---|---|
| `comfy/sd.py` (host core copy; remote image ships its own — provenance caveat §9) | `encode_from_tokens` (load_model → load_models_gpu OUTSIDE span → `cuda_device_context` → `cond_stage_model.encode_token_weights` INSIDE span → cond/pooled assembly OUTSIDE) |
| `comfymodal_runtime/model_preload.py` @ r42 lane HEAD `6040c45` (`B6EA9DBD…`) | `_make_clip_span_wrapper` (9038–9295): opens ledger span `"CLIP forward"` when `before==0 and span_name=="clip_forward"`; `_install_clip_span_wrappers` (9322–9372) wraps `CLIP.tokenize/load_model/encode_from_tokens/encode_from_tokens_scheduled/encode_token_weights`; `_ensure_clip_forward_wrapper` (9298–9313) wraps `cond_stage_model.encode_token_weights`; both share depth var `_clip_forward_depth` |
| same file @ commit `36b895d` (2026-08-21 19:57:05, blob `7483c2bf…`, extracted copy SHA256 `EF5AD2DE…`) | E37-era wrapper: boundary semantics IDENTICAL (same ledger `begin_span("CLIP forward")`, same preamble order: E31 timer → `_CLIP_FORWARD_STARTED` → ledger begin → clean-lane mark → `mark_clip_forward_start` → trace emit). Later additions (golden-bridge timer arming, R44D forced-miss block, K5 exec-state hooks) are additive telemetry only |
| `comfymodal_runtime/gpu_lane_coordination.py` (r42 :668–694; orchestration repo :520–546) | emits the OTHER `clip_forward_start` event: `end_clip_hydration` fires a lane marker named `clip_forward_start` with `reason="after_clip_hydration"` when hydration ends during an in-flight encode. This is NOT the timer boundary |

### 1.3 Reports read

`E37_CLEAN_LANE_ALGORITHM_RECOVERY_REPORT.md` (`A8A93BB4…`), `K1_GOLDEN_RESTORE_QUIESCENCE_SEAM_RECOVERY_REPORT.md` (`E2372A7C…`), r42 `K4_PYTHON_TO_DURABLE_TRUTH_AND_E37_DELTA_REPORT.md` (`523400FE…`), r42 `K5_MATCHED_PLACEMENT_CLIP_FORWARD_EXECUTION_STATE_REPORT.md` (`CF551814…`), r42 `E38B_CANONICAL_TIMING_AND_VALIDATION_CONTRACT_AUDIT.md` (`005EC4BB…`), r42 `E38O_INDEPENDENT_FULL_REPOSITORY_AUDIT.md` (`683ECC8E…`, §21 slow-vs-clean), r42 `E38A_SNAPSHOT_REACHABILITY_AND_CLIP_EXCLUSION_AUDIT.md` (`61A1C41C…`, O1–O5 fragment).

---

## 2. Exact GoldenClipForward contract (derived from the real call chain)

Derived from source, not assumed. Starting from the output of the credible CLIP-load candidate and ending where the next serialized Golden part (UNET/sampling) can consume conditioning:

```
[credible CLIP-load candidate output]
    E37 class:  clip_qd_device_ready / clip_device_ready  (QD read+H2D+bind, same-storage)
    modern:     clip_fast_load_end (FastSafe native same-storage assign, 398/398)
        ↓  (all inside CLIPTextEncode node)
1. conditioning-cache lookup/decision        — candidate-owned, BEFORE everything (E37: bypassed,
                                               clean_lane_forced_miss, mono 217523605383/217523825133)
2. tokenize (clip.tokenize)                  — own wrapper `clip_tokenize`; E37 8.125 ms
                                               (217524126153→217532251151); REF 13.498 ms
3. encode_from_tokens_scheduled wrapper      — clip_scheduled_conditioning span opens
4. encode_from_tokens (comfy/sd.py:380):
   a. reset_clip_options / set_clip_options  — µs
   b. self.load_model(tokens)                — comfy model-management:
                                               load_models_gpu(CLIP) — OWN wrapper `clip_gpu_prepare`
                                               + ledger span `model-mgmt:load_models_gpu`
                                               (E37 s16 = 0.803 ms; REF gpu_prepare 9.604;
                                                K5 gpu_prepare 11.5–18.3 ms)
   c. set execution_device
   d. with cuda_device_context(device):
        cond_stage_model.encode_token_weights(tokens)
        ← THE ONLY SECTION THE HISTORICAL TIMER BRACKETS:
          token weighting/embedding → transformer forward (Z-Image TE = Qwen3-4B via llama.py,
          36 TransformerBlocks, attention_basic, manual BF16 casts incl. first-block cast)
          → pooling → output processing   [+ µs-class telemetry preamble inside the wrapper,
                                           before original() runs]
   e. unpack cond/pooled; dict assembly; add_hooks_to_dict   — AFTER timer
5. conditioning list publication ([[cond, {pooled_output,…}]]) — AFTER timer (~0.5–1.4 ms to
   clip_scheduled_conditioning_end)
6. conditioning persistence/decision tail    — AFTER timer (E37 persisted_count=0)
        ↓
[next serialized Golden part (UNET/sampler) consumes conditioning]
```

**Contract definition:** GoldenClipForward = steps 1–6 (candidate-output → conditioning published for sampler).
The historical timer measures **step 4d only**.

No generic substages were invented; every listed step exists at a named wrapper/event boundary above.

---

## 3. E37 call-chain reconstruction (raw, request `v2-benchmark-0-c9ac6e750942`)

All stamps remote-process `monotonic_ns` from `run_001_sample.json` (`4B83BAD9…`):

| # | Boundary | mono_ns | Evidence |
|---|---|---|---|
| 1 | conditioning cache lookup / decision (bypassed, forced miss) | 217523605383 / 217523825133 | trace events |
| 2 | clip_tokenize_start → clip_tokenize_end (**8.125 ms**) | 217524126153 → 217532251151 | trace events (outside timer) |
| 3 | clip_scheduled_conditioning_start | 217533373851 | wrapper span opens |
| 4 | clip_raw_encode_start (`encode_from_tokens` enters) | 217534012821 | wrapper span opens |
| 5 | clip_loader_start / QD submit start (block 32 MiB, qd=4, preadv, n_ranges=240) | 217540371130 / 217557183787 | ledger events (candidate-owned, before timer) |
| 6 | QD last completion / copy end (source wall 1043.514 ms; h2d_cuda 27.316 ms) | 218632560669 / 218635832288 | ledger |
| 7 | clip_qd_device_ready → bind → clip_device_ready | 218637607918 … 218685180002 | ledger |
| 8 | clip_gpu_prepare (CLIP.load_model incl. load_models_gpu) 2.13 ms; `load_models_gpu_duration` 0.71 ms; ledger s16 `model-mgmt:load_models_gpu` **0.803 ms** | 218692414441 → 218694544301 | trace + ledger (before timer) |
| 9 | `clip_hydration_gpu_end` (hydration bracket closes, dur 1161.187) | 218695207401 | trace |
| 10 | `clip_forward_start` **lane marker** (`reason=after_clip_hydration`, emitted by `gpu_lane_coordination.end_clip_hydration`) | 218695225601 | trace — NOT a timer |
| 11 | `clip_forward_start` **wrapper stamp** (`metadata.clip_span="clip_forward"`) — gap vs marker **86,580 ns = 0.087 ms** | 218695312181 | trace |
| 12 | **ledger span s17 `CLIP forward` = 1110.221 ms** (218695575911 → 219805800150) | — | canonical_ledger.spans |
| 13 | clean_lane_proof (inside window, telemetry) | 219806185300 | trace |
| 14 | inner `clip_forward_end` (dur 1110.979; **thread_cpu 590 ms, process_cpu 990 ms**, cuda_no_sync=true, faults 0/0) | 219806290960 | trace |
| 15 | clip_raw_encode_end (dur 2273.477; tcpu 750, pcpu 2100) | 219806850920 | trace |
| 16 | clip_scheduled_conditioning_end (dur 2274.747) | 219807394600 | trace — conditioning assembled |
| 17 | outer `clip_forward_end` (`forward_ms=1112.455`) | 219807661780 | trace |
| 18 | sampler_lane_wait 0.055 ms; UNET demand; UNET commit = next serialized part | 219878262710 / 219897830537 … | ledger/trace |

Inside-window occupants (218695225601→219807661780): only the encode itself + `clean_lane_proof`. **Zero other-worker events.** No waits/locks/futures visible inside the interval. No GPU-block-busy telemetry exists in this era (no `opt_clip_forward_cuda`/`clip_forward_evidence`/exec-state events in the artifact). Forbidden-activity attempts recorded earlier in the request (restore_complete 217042654893, prompt_executor_start 217125369281, plan_time_unet_source_h2d 217180139733) all PRECEDE executor invoke (217213014937) — none overlap the window.

Un-attributed residue: process_cpu − thread_cpu ≈ **400 ms** of non-forward-thread CPU inside the inner window. Producer not identified by any artifact → per the critical rule this stays UNKNOWN; it is NOT evidence of an external worker stealing the interval, and no "wall − busy = waste" computation is performed (GPU-busy telemetry does not exist here anyway).

---

## 4. Historical timing audits (per class)

Boundary identity across eras is established first (§4.0), then each class.

### 4.0 Same-boundary equivalence (code-level)

- E37-era (`36b895d` blob `7483c2bf…`) and current r42 (`B6EA9DBD…`) `_make_clip_span_wrapper` open/close the ledger span `"CLIP forward"` at the identical position around `encode_token_weights`, identical preamble order, identical `before==0` depth guard. Diffs since are additive telemetry (golden-bridge arming, R44D raw-encode forced-miss emit, K5 exec-state collectors, measured ≤0.051 ms warm).
- Both eras also wrap `tokenize`, `load_model`, `encode_from_tokens`, `encode_from_tokens_scheduled` separately — tokenization and model-management are provably outside the forward span in BOTH eras.
- The second, non-timer `clip_forward_start` event (`reason=after_clip_hydration`) comes from `gpu_lane_coordination.end_clip_hydration` in both trees. Marker→wrapper-entry gaps observed raw: E37 **0.087 ms**, REF **34.67 ms**, K1R1 **44.27 ms**, K5 **35.1/43.7/51.8 ms**.
- ⚠ Discrepancy: K5 report §3 states the outer→inner preamble was "87 ms in E37, ~442 ms in K1R1, ~517–611 ms in K5". Raw artifact arithmetic gives **0.087 ms / 44.27 ms / 35–52 ms** respectively (stamps in §3, §4.3–4.5). The K5 prose magnitudes could not be reproduced from any stamped pair inspected; treat K5's preamble numbers as unverified. This does not affect the ledger-span values themselves.

### 4.1 E37 healthy (anchor) — `1110.221 ms`

- Exact boundary: ledger span s17 opened/closed inside `_make_clip_span_wrapper` around outermost `encode_token_weights`.
- Entry state: CLIP weights GPU-resident same-storage via QD bind ~10 ms earlier; `load_models_gpu` 0.803 ms near-no-op; tokenizer already run (8.125 ms, outside).
- Model-management inside timer: none (s16 outside).
- Candidate-owned work before timer: QD source read 1043.5 ms + H2D 27.3 ms + bind + prepare (§3 items 5–8). After timer: cond/pooled assembly ~1.1 ms + cache decision (persisted 0).
- Other workers/H2D during interval: none recorded. Waits/locks/futures inside: none visible. GPU-busy telemetry: absent (era limitation). Perturbation: µs-class wrapper overhead only.
- Classification: **MEASURED_OPERATION_COMPLETENESS** for "outermost encode_token_weights execution". Not CONTAMINATION on current evidence (un-attributed 400 ms other-thread CPU remains UNKNOWN, disclosed).

### 4.2 E36 full normal path (slow-vs-clean comparator) — `5985.017 ms`

`s18` of `v2_2026-08-21_16-00-22` (req ff69a4c9f3da); hydration s16 1593.466 ms; lmg(CLIP) s17 11.031 ms before it. Inner end metadata: `duration_ms=6017.72, thread_cpu_ms=5100, process_cpu_ms=27950`; `opt_clip_forward_cuda wall_ms=6016.229` (cuda_event unrealized — sync gate off). Raw_encode window 7665.961 ms (tcpu 5910, pcpu 34150).
- Boundary: same wrapper mechanism (era code lineage; ledger began ~1.5 ms after wrapper entry — same preamble family).
- Inside the interval: forward thread burned 5100 ms CPU (85% of wall) AND ~22.85 core-seconds of non-forward-thread process CPU ran concurrently. Producer threads are NOT itemized in the artifact (startup-concurrency era per E38O §21 hypothesis B) → composition UNKNOWN, but heavy concurrent process activity is PROVEN at counter level.
- Classification: boundary-equivalent measurement (MEASURED_OPERATION_COMPLETENESS semantics) whose interval is **CONTAMINATED for intrinsic implementation comparison** while remaining the actual request-forward wall observed in that run. Both facts reported; no wall-minus-busy arithmetic performed (cuda_event empty).

### 4.3 Bad clean-lane run — `4413.902 ms`

`s17` of `v2_2026-08-21_22-34-15` (req c76e8bc0e7c6, same profile as E37). Structure identical to E37 (lmg 0.662 ms; marker→wrapper gap 80,062 ns = 0.080 ms; UNET lmg after = 18 543 ms). Inner end: `dur=4414.605 tcpu=2140 pcpu=2610`; raw_encode 5597.649 (tcpu 2320, pcpu 3350).
- Key fact: the FORWARD THREAD itself consumed 2140 ms CPU — ~3.6× E37's 590 ms — so the excess is mostly extra work/spin inside the timed operation, not provable external starvation (other-thread residue only ≈470 ms, producer unidentified).
- Classification: MEASURED_OPERATION_COMPLETENESS, same boundary as E37 (semantically equivalent — comparable number, different regime); CONTAMINATION NOT proven. Root cause out of scope (no architecture/kernel recommendations).

### 4.4 REF current-class — `1865.112 ms` (ledger) / `1865.898 ms` (event pair)

`v2_2026-08-25_02-55-12` (req 61b4e2bd9f9e, GCP us-east1). Wrapper start 1869353646004; inner end 1871219543621 (`dur=1865.898 tcpu=1230 pcpu=4350`). Tokenize 13.498 ms; gpu_prepare 9.604 ms; FastSafe transport era (CLIP fast_load before forward). Non-forward-thread CPU inside window ≈3120 ms; concurrent early-UNET-prep reader active (J1-era dirty state; K4 §8/§9 document 100% prep overlap for this class, join after forward end).
- Classification: MEASURED_OPERATION_COMPLETENESS boundary-wise; interval **CONTAMINATED for intrinsic comparison** (proven concurrent reader + large un-attributed CPU), while being the real observed wall.

### 4.5 K1R1 selected path — `2037.321 ms` (ledger) / `2037.941 ms` (event pair)

`v2_2026-08-25_06-51-50` (req 8e43af5eed14, GCP us-east1). Per K4 §4/§9 (raw stamps quoted there): tokenize 9.87 ms; gpu_prepare 20.73 ms; **load_models_gpu(CLIP) 91.7 ms** (outside timer, between marker 77889834817* and wrapper entry 77934103687 — *marker label per K4 prose); UNET prep reader armed at setup (prep_start 74253885047), overlapped **100% of the forward window** (`unet_prep_overlap_ms=2084.487` against the outer bound), joined only AFTER forward end (80103445199); forward tcpu 1220 / pcpu 5850 (K5 §7 table) ⇒ ≈4630 ms non-forward-thread CPU inside window; page faults 0; CUDA alloc Δ +33.55 MB.
- Classification: MEASURED_OPERATION_COMPLETENESS boundary-wise; **CONTAMINATED for intrinsic comparison** — producer of concurrent activity explicitly identified and proven (early_model_prep reader state + counters), satisfying the brief's "wait/future/lock producer proven" bar for classification of the concurrency channel; still the actual observed forward wall of that run.

### 4.6 K5 slow draws — RUN1 `4890.316` / RUN2 `3545.669` / RUN3 `2006.763` ms (ledger)

Requests d31bdac8de3c / ffab0ae32e31 / 55a7945a5d6e (event-pair walls 4891.064 / 3548.095 / 2008.939). Exec-state (first time live-probed, RUN3 raw fields verified in artifact): `model_class=ZImageTEModel_`, `attention_backend=comfy.ldm.modules.attention.attention_basic`, xformers/sage/flash unavailable, `autocast_enabled=false`, weights BF16 + manual cast, `comfy_cast_weights_present=true`, FastSafe resolved threads=8/block 256 MiB/bbuf 512 MiB (`unet_fastsafe_source="env"`), **`prep_armed=true, prep_parked=false, prep_bytes_read=6.19 GB at entry`** → 100% overlap of every TRUE forward window, 12,309,866,400 B reached by exit; forward tcpu 1250/1110/1250 vs pcpu 4990/4300/5710; page faults 0.
- GPU-block-busy telemetry (present for the first time): RUN2 transformer-core GPU window 3424.068 ms with Σ per-block busy 213.067 ms; RUN3 1903.881 ms / 197.738 ms ⇒ ≈3080 / ≈1590 ms GPU-idle bubbles INSIDE the forward window while block compute is ~200 ms (+~120 ms first-block casts). The IDLE is co-measured with the armed, actively-reading prep reader and multi-core non-forward CPU burn — correlation proven run-over-run; per the critical rule the causal split between "reader starves GPU feed" vs other runtime state is NOT decomposed beyond what K5 states.
- Perturbation: collector cost measured 0.001–0.051 ms; probes lazy/no-sync; RUN1 layer probes dead (disclosed, absent-not-fabricated).
- Classification: MEASURED_OPERATION_COMPLETENESS boundary-wise; **CONTAMINATED for intrinsic comparison** (producer-proven concurrent reader + measured CPU theft); each value is simultaneously the genuine request-forward wall of its draw. Placement variance (unpinned us-east1/us-west1) additionally limits comparability to E37 (us-south1, quiet-lane profile).

---

## 5. Same-boundary equivalence matrix

| Class | Timer boundary | Tokenize inside? | load_models_gpu(CLIP) inside? | cond assembly inside? | Concurrent-worker proof inside interval | Boundary equivalent to E37? | Value comparable to 1110.221? |
|---|---|---|---|---|---|---|---|
| E37 healthy s17 | wrapper on encode_token_weights | NO (8.125 ms out) | NO (0.803 ms out) | NO (~1.1 ms out) | none recorded; 400 ms other-thread CPU UNKNOWN | — (reference) | reference |
| E36 full path s18 | same mechanism | NO | NO (11.031 ms out) | NO | PROVEN heavy (pcpu Δ 27 950 ms / 6.0 s window), threads unnamed | YES | NO — contaminated interval (still the true observed wall) |
| Bad clean-lane s17 | same mechanism (gap 0.080 ms) | NO | NO (0.662 ms out) | NO | NOT proven; forward-thread CPU itself 2140 ms | YES | YES numerically; regime differs (not "bad CLIP forward" — different execution state, cause unresolved) |
| REF s15 | same mechanism | NO (13.498 out) | NO (gpu_prepare 9.604 out) | NO | PROVEN (prep reader 100% overlap class; pcpu−tcpu ≈3120 ms) | YES | NO — contaminated interval |
| K1R1 s15 | same mechanism | NO (9.87 out) | NO (91.7 out) | NO | PROVEN (prep reader 100%, 2084.487 ms overlap, join after end) | YES | NO — contaminated interval |
| K5 R1–R3 s15 | same mechanism | NO | NO (gpu_prepare 11.5–18.3 out) | NO | PROVEN (prep_parked=false, bytes advance across window; exec-state fields) | YES | NO — contaminated interval; placement also unmatched (us-south1 vs east/west) |

All classes measure the SAME operation; none measures the full GoldenClipForward contract. Calling slower classes "bad CLIP forward" without the contamination qualifier would be wrong: their intervals are semantically equivalent to E37's span but carry proven concurrent activity that E37's did not.

---

## 6. Contamination / wait evidence summary

- Proven producers (classifiable): early-UNET-source-prep Volume reader (K1R1/K5/REF-era): armed before forward, `prep_parked=false`, byte/read counters advance across the window, joins after forward end; overlap fractions exactly 100% of the TRUE window in every modern observation.
- Measured-but-unattributed: non-forward-thread CPU burn inside the window in EVERY class (E37 ≈400 ms; bad-clean ≈470 ms; REF ≈3120 ms; K1R1 ≈4630 ms; K5 ≈3190–4460 ms; E36 full-path ≈22.85 core-s over 6.0 s). No artifact names those threads → UNKNOWN per critical rule.
- Waits/locks/futures inside the interval: none visible in any audited window (no wait events, no lock contention records). The only in-window non-encode event ever observed is `clean_lane_proof` (telemetry, E37/bad-clean).
- GPU-idle ≠ external starvation: E37 has no GPU telemetry at all; K5's idle bubbles co-occur with the proven reader but causality is not decomposed → UNKNOWN split, stated as such.
- Enclosing-wall note (per brief): e.g., E36's 6.0 s forward is CONTAMINATED for intrinsic comparison AND simultaneously the actual request wall observed in that run; both facts hold together.

## 7. Total/partial verdicts (explicit)

**Primary answer:**

> **E37 `CLIP forward` duration_ms = 1110.221 is PARTIAL for the proposed serialized GoldenClipForward contract** — because the span is opened and closed inside `_make_clip_span_wrapper` exactly around the outermost `cond_stage_model.encode_token_weights` call under `cuda_device_context` (ledger `begin_span("CLIP forward", …)` at `before==0`; source `model_preload.py` @ `36b895d` lines 8549–8561 = r42 lines 9086–9098; call site `comfy/sd.py::encode_from_tokens` step 4d). It therefore covers token weighting/embedding + full transformer forward + pooling + output processing (+µs telemetry preamble) but EXCLUDES required contract work proven at named boundaries: conditioning-cache lookup/decision (217523605383/217523825133), tokenization 8.125 ms (217524126153→217532251151), `CLIP.load_model`→`load_models_gpu(CLIP)` 0.803 ms (ledger s16) within clip_gpu_prepare 2.13 ms (218692414441→218694544301), and post-return cond/pooled dict + conditioning-list publication ~1.1–1.4 ms (inner end 219806290960 → clip_scheduled_conditioning_end 219807394600). Missing serial pieces ≈11–13 ms in this run. It is NOT merely "the transformer wall" either: pooling/output processing and the manual-cast work sit inside it, and no sub-span isolates the transformer in this era.

Per-class verdicts:

| Class | Value (ms) | vs GoldenClipForward contract | Classification |
|---|---|---|---|
| E37 healthy s17 | 1110.221 | PARTIAL (excl. ≈11–13 ms contract tail/head, itemized above) | MEASURED_OPERATION_COMPLETENESS |
| E37 raw_encode window | 2273.477 | PARTIAL (adds load path + assembly; still excludes tokenize 8.125 + cache lookup) | MEASURED_OPERATION_COMPLETENESS |
| E37 scheduled_conditioning | 2274.747 | PARTIAL (closest single enclosure of load→publication; tokenize/cache still outside) | GOLDEN_PART_COMPLETENESS (nearest available enclosure; not emitted as one authoritative span) |
| E36 full-path s18 | 5985.017 | PARTIAL (same exclusions) | MEASURED_OPERATION_COMPLETENESS + CONTAMINATION (intrinsic-comparison sense); actual observed wall |
| Bad clean-lane s17 | 4413.902 | PARTIAL (same exclusions) | MEASURED_OPERATION_COMPLETENESS; contamination unproven; cause unresolved |
| REF s15 | 1865.112 | PARTIAL | MEASURED_OPERATION_COMPLETENESS + CONTAMINATION (proven reader overlap) |
| K1R1 s15 | 2037.321 | PARTIAL | MEASURED_OPERATION_COMPLETENESS + CONTAMINATION (proven reader overlap) |
| K5 RUN1/2/3 s15 | 4890.316 / 3545.669 / 2006.763 | PARTIAL | MEASURED_OPERATION_COMPLETENESS + CONTAMINATION (proven reader overlap + exec-state proof); placement-unmatched |
| K5 RUN2/3 transformer-core GPU windows | 3424.068 / 1903.881 | Sub-intervals of the span; not contract measures | diagnostic sub-measurements |
| Σ per-block GPU busy (RUN2/3) | 213.067 / 197.738 | GPU-executing fraction only | diagnostic sub-measurement |

**No historical timing equals TOTAL for GoldenClipForward.** The smallest faithful TOTAL-style reconstruction for E37 is the sum of named serial pieces: cache-decision tail + tokenize 8.125 + scheduled_conditioning 2274.747 ≈ 2283–2284 ms (assembled from adjacent spans; never emitted as one span by any era).

Closest surviving SoT statement (since Phase-O SoT is absent): `E38B` §Ledger serial chain — E37 axis tiled zero-gap: … `CLIP hydration 1149.953, load_models_gpu 0.803, CLIP forward 1110.221, load_models_gpu 840.785, sampling 4748.2 …` total python_resume→durable 10562.860481 ms.

---

## 8. Unresolved gaps

1. Missing requested docs: Phase-O SoT, v2.1, O3/O6/O7/O8, OB4/OB7/OB8, OC1/OC2 enum definitions (§0). O3 (external Comfy model-management retention) remains UNKNOWN exactly as E38A left it.
2. K5 §3 preamble magnitudes ("87/442/517–611 ms") not reproducible from raw stamps; actual marker→entry gaps 0.087 / 34.7 / 44.3 / 35–52 ms. One side mislabels units or boundaries; unresolved here.
3. Identity of non-forward threads burning CPU inside every forward window (400 ms … 22.8 core-s) — unnamed in all artifacts → UNKNOWN ownership; blocks any "external waste" attribution.
4. Remote container ships its own comfy core; no pin exists to diff host `sd.py` against the E37-era remote core (K5 flags the same UNKNOWN). Boundary reasoning uses the host core + era wrapper code, which is the code deployed alongside.
5. E37 had a single paid run, no confirmation runs (its own report says so); E36-full-path and bad-clean-lane are n=1 each. All cross-era comparisons inherit placement/state mismatch (E37 GCP us-south1 quiet-lane vs modern unpinned draws).
6. No clean-room (quiet-host) modern draw exists, so whether the modern forward would return to ~1.1 s under E37-like conditions is unresolved (K5 §13 residual).
7. Conditioning-cache-hit forwards emit no forward span at all (cache-hit requests never reach `encode_token_weights`); no timing class exists for that path.

---

## 9. Raw evidence appendix (verbatim key fields)

### A. E37 ledger spans (`v2_2026-08-21_22-35-45/run_001_sample.json`, SHA256 `4B83BAD962DB2A216AB0A03ACF8A200A66EB14A238394D38CF3215FCACD8B560`)
```
{"span_id":"s15","name":"CLIP hydration","duration_ms":1149.953}
{"span_id":"s16","name":"model-mgmt:load_models_gpu","duration_ms":0.803}
{"span_id":"s17","name":"CLIP forward","duration_ms":1110.221,"accounted_ms":1110.221,"delta_ms":0.0}
{"span_id":"s18","name":"model-mgmt:load_models_gpu","duration_ms":840.785}
{"span_id":"s19","name":"sampling","duration_ms":4748.2}
```

### B. E37 forward-window trace events (mono_ns, name, selected metadata)
```
218692414441 clip_gpu_prepare_start
218693973761 load_models_gpu_duration {duration_ms:0.71, caller_classification:"graph_model_loading", memory_required:0, gpu_request_invocation_count:1, model_identity_hash:"da0c871257791540"}
218694544301 clip_gpu_prepare_end {duration_ms:2.13}
218695207401 clip_hydration_gpu_end {duration_ms:1161.187, reason:"clip_load_model"}
218695225601 clip_forward_start {reason:"after_clip_hydration"}                      ← lane marker
218695312181 clip_forward_start {clip_span:"clip_forward"}                           ← timer wrapper
219806185300 clean_lane_proof
219806290960 clip_forward_end {duration_ms:1110.979, thread_cpu_ms:590.0, process_cpu_ms:990.0, status:"ok"}
219806850920 clip_raw_encode_end {duration_ms:2273.477, thread_cpu_ms:750.0, process_cpu_ms:2100.0}
219807394600 clip_scheduled_conditioning_end {duration_ms:2274.747}
219807661780 clip_forward_end {forward_ms:1112.455, cache_state:"cache_miss", coordination:"CLIP_GPU_CRITICAL_ACTIVE", success:true}
```
Inner-end CUDA context fields (same artifact): `cuda_no_sync:true`, faults 0/0, allocated delta 0 across lmg; `region:"us-south1"`, provider GCP.

### C. E37 pre-timer candidate-owned events
```
217523605383 clip_conditioning_cache_lookup {lookup_status:"bypassed", reason:"clean_lane_forced_miss"}
217523825133 clip_conditioning_cache_decision {reason:"clean_lane_forced_miss"}
217524126153→217532251151 clip_tokenize_start/end {duration_ms:8.125}
217557183787 clip_qd_source_submit_start … 218632560669 last_completion (QD wall 1043.514 ms; aggregate 7.7095 GB/s; h2d_host_issue 127.399; h2d_cuda 27.3155)
218685180002 clip_device_ready
```

### D. Comparator artifacts (SHA256 of each `run_001_sample.json`)
```
4B83BAD962DB2A216AB0A03ACF8A200A66EB14A238394D38CF3215FCACD8B560  v2_2026-08-21_22-35-45 (E37)
9C202CD4C1D454241CFD329DC0215FFEB22ED340919342CB3C4DB3651334D13D  v2_2026-08-21_16-00-22 (E36 full path)
F467FF5E9518AC6EDB64A43597E11C7724937C2176998AA3E267A0E0B28F708B  v2_2026-08-21_22-34-15 (bad clean-lane)
B24E119EF3DB18996922B9D87DEF790599E7DA1216D8D3AD86F8C9EB1EF2BC0E  v2_2026-08-25_02-55-12 (REF)
CC22C089FFFF347432F1F72245EFB9FF261B87D156D64936A8B904090176D0D7  v2_2026-08-25_06-51-50 (K1R1)
B7E494F1810CF44161AEBE4C681BB07DF9ACAE8AE097EBC0F9E0308EFCBA7216  v2_2026-08-25_15-34-30 (K5 R1)
64A238AB63F5293622CF9AFF819F141035130A80FC31EA3AFFA58CBCB49B3F15  v2_2026-08-25_16-00-31 (K5 R2)
15CCA0DD8A61EE2436E0B0706553444861E57E431D4D55E730A69AC546D28BA6  v2_2026-08-25_16-04-15 (K5 R3)
```

### E. Comparator forward-window extracts (mono_ns / name / fields)
```
E36 full path (16-00-22):
458131778832 clip_forward_start ; 458131841789 clip_forward_start ; 458133254293 fast_cold_clip_forward_start
464118322118 clip_forward_evidence ; 464149561549 clip_forward_end {duration_ms:6017.72, thread_cpu_ms:5100.0, process_cpu_ms:27950.0}
464149545677 opt_clip_forward_cuda {wall_ms:6016.229} ; 464151136177 clip_raw_encode_end {duration_ms:7665.961, tcpu:5910, pcpu:34150}
ledger: s16 hydration 1593.466 ; s17 lmg 11.031 ; s18 CLIP forward 5985.017 (458133213634→464118231332)

bad clean-lane (22-34-15):
149083455430 clip_forward_start(marker) ; 149083535492 clip_forward_start(wrapper)  [gap 80,062 ns]
153498140262 clip_forward_end {duration_ms:4414.605, tcpu:2140.0, pcpu:2610.0}
153499378058 clip_raw_encode_end {duration_ms:5597.649, tcpu:2320, pcpu:3350}
ledger: s15 hydration 1168.867 ; s16 lmg 0.662 ; s17 CLIP forward 4413.902 ; s18 lmg(UNET) 18543.321

REF (02-55-12):
1869318972450 clip_forward_start(marker) ; 1869353646004 clip_forward_start(wrapper)  [gap 34.67 ms]
1871219543621 clip_forward_end {duration_ms:1865.898, tcpu:1230.0, pcpu:4350.0}
1869318997520→1869332495064 tokenize {13.498} ; gpu_prepare 9.604 ; ledger s15 CLIP forward 1865.112

K5 (marker→wrapper gaps 51.77 / 35.14 / 43.75 ms; ledger s15 above; event walls/tcpu):
RUN1 311885022113 / 311936796006 … 316827860319 end {4891.064, tcpu:1250}
RUN2 248857917956 / 248893062236 … 252441157163 end {3548.095, tcpu:1110}
RUN3 455321727744 / 455365473362 … 457374412527 end {2008.939, tcpu:1250}

K5 RUN3 clip_forward_exec_state_start (verbatim selection):
{model_class:"ZImageTEModel_", model_module:"comfy.text_encoders.z_image",
 attention_backend:"comfy.ldm.modules.attention.attention_basic", flash_available:false,
 sage_available:false, xformers_available:false, autocast_enabled:false, autocast_dtype:"torch.float16",
 param_dtype:"torch.float32", token_embed_dtype:"torch.bfloat16", comfy_cast_weights_present:true,
 first_linear_class:"Linear", prep_armed:true, prep_parked:false, prep_paused_total_ms:0.0,
 prep_bytes_read:6190792704, prep_read_calls:738, prep_joined:false,
 clip_fastsafe:{threads:8, block_bytes:268435456, bbuf_kb:524288, nogds:true},
 unet_fastsafe:{threads:8, block_bytes:268435456, bbuf_kb:524288}, unet_fastsafe_source:"env",
 collect_cost_ms:0.049, attention_probe_source:"computed_first_call",
 cuda_allocated_bytes:8044936704, native_thread_count:58, omp_num_threads:12, mkl_num_threads:12}
```

### F. Source hashes / refs
```
git 36b895db1992fde285735ac9e59c63bb238a6e0a (2026-08-21 19:57:05 -0500) blob 7483c2bf49c64ea9637d58c797b3827d22655d74
  comfymodal_runtime/model_preload.py  → extracted-copy SHA256 EF5AD2DEC4DDC8F504DBBD79076D5C79DD612A3C272A493E83C2A6706B31000A
r42 lane HEAD 6040c459f2766f2ccb2f97799c08ff53b616d54a
  comfymodal_runtime/model_preload.py  SHA256 B6EA9DBD94091BBDA7799910383C8B0AE60C03763317C584EA65DE8371A96D26
orchestration repo HEAD 0c59f46 (branch TESTING2)
host comfy core ..\..\comfy\sd.py     SHA256 C1186A37DFBB91B75A478B137142A8FF408E178B1D100A409CA61352D8719E58
Reports: E37 A8A93BB4… ; K1 E2372A7C… ; K4 523400FE… ; K5 CF551814… ; E38B 005EC4BB… ; E38O 683ECC8E… ; E38A 61A1C41C…
gpu_lane_coordination.py marker emitter: r42 :668–694 (end_clip_hydration → clip_forward_start reason="after_clip_hydration")
```

### G. Boundary-relevant source shape (host `comfy/sd.py`, `encode_from_tokens`)
```
reset_clip_options(); set_clip_options({layer/projected_pooled}); 
self.load_model(tokens);                       ← load_models_gpu(CLIP): OUTSIDE timer
device = self.patcher.load_device; set_clip_options({"execution_device": device});
with model_management.cuda_device_context(device):
    o = self.cond_stage_model.encode_token_weights(tokens)   ← LEDGER SPAN s17/s15 EXACTLY HERE
cond, pooled = o[:2]; dict assembly; add_hooks_to_dict(out)   ← OUTSIDE timer
```

*End of appendix. No architecture recommendations made; no code changed; nothing deployed.*
