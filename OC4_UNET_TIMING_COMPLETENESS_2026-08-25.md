# OC4 — Batch UNET Candidate-Specific Timing-Completeness Audit

Date: 2026-08-25 · Mode: READ-ONLY forensic audit. No deploy, no Modal runs, no source changes, no implementation or architecture selection. Only files created: this report + `OC4_UNET_TIMING_CLAIMS_2026-08-25.csv`.

Purpose: for each exact historical UNET candidate, read the exact implementation, establish what must be true before the resulting UNET is usable by the serialized sampler, identify all candidate-owned work wherever it occurs, and determine whether each historical timing is TOTAL, PARTIAL, or CONTAMINATED. No universal breakdown is imposed; each candidate gets a bespoke narrative.

Companion CSV: `OC4_UNET_TIMING_CLAIMS_2026-08-25.csv` (one row per timing claim).

---

## 0. Authoritative-input status (READ FIRST list)

| Required input | Status on disk | Consequence |
|---|---|---|
| Reconciled Phase-O SoT | **NOT FOUND** anywhere in the repo (searched `*.md`, `.slim/`, `docs/`, `reports/`, hidden dirs) | Phase-O-reconciled numbers that cannot be re-derived from raw artifacts are marked REPORT_ONLY |
| v2.1 amendment (inclusive-cost correction) | NOT FOUND | Inclusive-cost corrections are applied here only where raw clocks in artifacts permit; otherwise UNKNOWN |
| O4 / O6 / O7 / O8 | NOT FOUND | Not relied upon |
| OB3 candidate/evidence/interface matrices | NOT FOUND | Candidate set rebuilt from primary sources (code + run artifacts) per the task's minimum set |
| OB7 interfaces/resource/composability | NOT FOUND | Composability statements derive from code reading only |
| OB8 red team | NOT FOUND | Red-team function performed fresh in §7 |
| Exact sources/logs | PRESENT and used throughout | All classifications below are grounded in these |

No Phase-O/OB document was available to this audit. Every conclusion below stands on repository-local source code, embedded run artifacts, and the two raw evidence files listed in §1. Where the task supplied candidate labels/numbers (K5 363.260/415.655/406.694 ms, R42 ~0.878 s, J1 ~0.4–0.7 s) that could not be located in any on-disk artifact, they are carried as REPORT_ONLY and classified UNKNOWN — they are never promoted to raw-evidence conclusions.

---

## 1. Evidence inventory

### 1.1 Source of truth for each candidate

| File | Role |
|---|---|
| `comfymodal_runtime/unet_fastsafetensors.py` (2198 lines) | C9 / E28 / current-request FastSafe pipeline: `_fs_try_pipeline`, `_fs_fastsafe_load` (`unet_fastsafetensors.py:882`), `_fs_meta_construct` (:700), bind/sweep/validate/patcher/owner (:1859–:2064), `_FastsafeOwner` (:2188) |
| `comfymodal_runtime/unet_qd_probe.py` | E27 QD probe: `gpu_transfer_phase` (`unet_qd_probe.py:1006`) |
| `comfymodal_runtime/model_preload.py` | `_load_unet` branch ordering (:14084–:14250), `load_models_gpu` wrapper + E25 proven-ready fast return (:4141–:4207), `unet_gpu_demand_start` stamping (:4368–:4380), lane lifecycle + `_consume_model_impl` demand path (:9737–:9753, :14694–:14823), loader-selection precedence consumer |
| `comfymodal_runtime/fast_cold_orchestration.py` | `before_unet_demand` → `wait_for_unet_commit` CLIP-forward fence (:701–:767), storage-owner state machine, `record_unet_ready` (:1197), model_readiness_gate record fields (:362–:365) |
| `comfymodal_runtime/gpu_lane_coordination.py` | D15 UNET GPU token, `record_clip_ready`/`record_unet_ready`/`_readiness` gate emission (:273–:337) |
| `comfymodal_runtime/config_authority.py` | Loader-selection precedence: UNET = `fastsafetensors` first, then `meta_direct`, then `cpu_snapshot_native`, else `native_comfy` (:342–:349); flag default OFF (:78) |

### 1.2 Raw evidence artifacts

| Artifact | Contents used |
|---|---|
| `..\..\comfymodal-data\benchmarks\runs\v2_2026-08-21_22-35-45\run_001_sample.json` (SHA-256 `4b83bad9…8b560`) | E37 canonical ledger spans incl. `model-mgmt:load_models_gpu 840.785`; full_trace events `graph_gpu_load_start/end`, `mp_load_start/end`, `model_patcher_load_breakdown`, `cpu_snapshot_models_retargeted`; effective_env proving `COMFYMODAL_V2_UNET_FASTSAFETENSORS=0`, `COMFYMODAL_V2_NATIVE_FAST_DISK_UNET=1` |
| `_e27_unet_qd_evidence.json` | E27 QD4/32 `gpu_transfer` section verbatim (1020.8782 ms wall etc.) |
| `V2_BATCH_C9_FASTSAFETENSORS_INTEGRATION_REPORT.md` §6/§8/§9 | C9 valid-run pipeline telemetry table (2172.92 file→GPU, 2743.40 total, bind 9.54, meta 2292.86 cold outlier) + second-cold-run addendum |
| `V2_BATCH_E28_CRITICAL_PATH_IMPLEMENTATION_AND_VALIDATION.md` (embedded complete `run_0.json`) | Final-form FastSafe runs `v2-benchmark-0-fad442b2f11b` and `v2-benchmark-0-5f3702b75dfb`: full `unet_fastsafetensors_pipeline` metrics, `model_readiness_gate`, `unet_gpu_commit_wait_ms` series |
| `E38B_CANONICAL_TIMING_AND_VALIDATION_CONTRACT_AUDIT.md` | Clock-domain registry (D1–D10), ledger serial-chain semantics for the E37 run, union-accounting rules |
| `E37_CLEAN_LANE_ALGORITHM_RECOVERY_REPORT.md` | E37 profile identity (`e37-clean-lane-qd4`), CLIP QD4 semantics, "UNET sampling follows CLIP bind" ordering |

### 1.3 Evidence-language convention
CONFIRMED (source+artifact proven) · SUPPORTED INFERENCE · HYPOTHESIS · UNKNOWN · UNOBSERVABLE · REPORT_ONLY (value asserted by the Phase-O brief; no on-disk artifact found).

---

## 2. Candidate inclusion table

| ID | Candidate / timing class | Implementation locus | Included? | Form decision | Reason |
|---|---|---|---|---|---|
| C9 | True-first-touch production FastSafe (run `v2_2026-08-15_18-32-47`, fs threads=16/1 GiB blocks) | `unet_fastsafetensors.py::_fs_try_pipeline` | YES | COMPLETE_PRODUCTION_STAGE | Validated end-to-end with byte-identical output SHA; returns sampler-consumable ModelPatcher |
| E27 | QD4 full storage→pinned→async-H2D probe | `unet_qd_probe.py::gpu_transfer_phase` | YES (as component) | PROBE_ONLY | Produces byte buffers in temporary CUDA allocations; no model object exists; buffers freed at probe exit |
| E28 | FastSafe final form, cold container runs (`fad442b2f11b`, `5f3702b75dfb`; T8/256 MiB/512 MiB bbuf) | same as C9 after E28 tuning + D15 fix + E29 ledger events | YES | COMPLETE_PRODUCTION_STAGE | Two PASS cold runs, exact SHA; but totals carry a proven CLIP-forward fence wait (§7.2) |
| E37 | ~840.785 ms model-management/load_models_gpu-class interval | native fast-disk CPU-snapshot arm at demand time (env: FASTSAFETENSORS=0, NATIVE_FAST_DISK_UNET=1) | YES | COMPLETE_BUT_STATE_DEPENDENT | Interval is real demand-time work reaching sampler-usability, but only because restore/bootstrap pre-materialized weights to CPU RAM |
| K5 | 363.260 / 415.655 / 406.694 ms post-prep demand FastSafe | (Phase-O label) mechanics exist at `model_preload.py:4141–:4207` (demand bookkeeping over resident model) | YES as class | OVERLAP_DEPENDENT_STAGE (mechanics CONFIRMED in code; numbers REPORT_ONLY) | Numbers not found in any on-disk artifact; completeness UNKNOWN |
| R42 | ~0.878 s cache-served commit class | none located | CONDITIONAL — included as REPORT_ONLY row only | UNKNOWN | No supporting artifact found. Caution: `modal_logs.txt:71` contains an unrelated `restore_total_ms: 878.2` (restore-method wall, different boundary) — explicitly not conflated |
| J1 | ~0.4–0.7 s warm-commit class | none located | CONDITIONAL — included as REPORT_ONLY row only | UNKNOWN | Nearest code mechanism is the prefetch-lane commit consumed at `graph_unet_demand` (`model_preload.py:14694+`); no artifact matches the range |
| CUR | Current/request FastSafe implementation (HEAD) | `unet_fastsafetensors.py` at audited HEAD + `model_preload.py:14119–:14158` branch | YES | COMPLETE_PRODUCTION_STAGE (flag-gated, default OFF) | Same lineage as C9/E28; latest whole-stage evidence is the E28 final pair; E25 demand interplay documented |
| — | Pinned-ring, meta-direct, salvage probes, staged transport, unet_backing, historical single-pass fast-disk loader | various | EXCLUDED from claim rows | — | Dead/flagged-off or strictly component-level; including them would add no comparable timing claim. Staged transport survives only as an in-pipeline component behind `COMFYMODAL_V2_STAGED_SAFETENSORS` |

This is not a quality ranking. Component candidates (E27) remain valid components.

---

## 3. GoldenUnetLoad completion contract (derived from the actual consumer)

The target question is not "when did a tensor copy finish" but "when has this candidate fulfilled everything required for the next serialized sampler to safely consume the intended UNET".

Actual consumer boundary (traced, CONFIRMED):

```
UNETLoader node output (ModelPatcher)
  → graph execution → KSampler-side comfy.model_management.load_models_gpu
      (wrapped at model_preload.py:4141; emits unet_gpu_demand_start :4377,
       ledger span model-mgmt:load_models_gpu, graph_gpu_load_* events)
  → ModelPatcher.load bookkeeping (mp_load_start/end;
     model_patcher_load_breakdown = traversal + patch_weight + residual)
  → sampler ops issued on the same CUDA stream ⇒ stream-ordering makes any
    earlier same-stream copy visible before first forward
```

GoldenUnetLoad is COMPLETE for a candidate iff ALL of:

- **G1 Exact returned/published object** — a `comfy.model_patcher.ModelPatcher` wrapping the intended ZImage diffusion model is what flows out of the loader into node/graph state (C9/E28/CUR: `_fs_try_pipeline` returns `(_patcher,)` and flows through the unchanged `_load_unet` tail, `unet_fastsafetensors.py:2164`; `model_preload.py:14193`).
- **G2 Storage ownership** — every parameter's backing storage is guaranteed for the model lifetime. FastSafe: `FilesBufferOnDevice` owns gbuf; views from `get_tensor` are valid only while open; owner retained via `patcher._comfymodal_fastsafe_owner` (`_FastsafeOwner`, :2001–:2009, :2188–:2198); close() only on failure. Native/snapshot: tensors owned by the module itself.
- **G3 Model construction state** — meta construction finished outside-inference-context with `model_sampling` repaired (zero poisoned tensors; `_fs_meta_construct` :806–:832) — required because a poisoned `model_sampling` breaks the sampler before any weight matters.
- **G4 Model patcher state** — plain (non-dynamic) ModelPatcher mirroring sd.py, `load_device=target`, `offload_device=unet_offload_device` (:1982–:1992).
- **G5 Validation state** — post-bind gates held: key-set, spot-check, byte-total parity, transform INDEPENDENT, data_ptr zero-copy sample, residual-meta sweep = 0, final validation all-params-on-target (:1812–:1981). Any failure ⇒ fail-closed fallback to native, i.e., NOT Golden-complete.
- **G6 Device readiness** — one of: `torch.cuda.synchronize()` (default), scoped stream `wait_event` on the recorded copy event when enabled (:1948–:1962), or (native paths) same-stream ordering plus ComfyUI's own load_models_gpu completion.
- **G7 Required model-management mutation** — the patcher is registered such that the sampler's `load_models_gpu` either completes its bookkeeping (mp_load) or takes the E25 proven-ready fast return under its six fail-closed conditions (`before==0`, opt-in env, request trace present, no mutation lane, registered UNET present, all params CUDA-resident, no force flags, CLIP-critical inactive; :4151–:4207). Until that point the loader output alone does NOT satisfy the serialized-sampler boundary.
- **G8 Fences/events/pending workers/futures** — both worker threads joined; no pending future whose failure can invalidate the published object; fallback state emitted exactly once (`unet_fastsafetensors_pipeline` event); D15 GPU token released in `finally` (:2170–:2185).
- **G9 Fallback state** — `fallback_count==0` and `loader_execution_identity="fastsafetensors"` for the claim to describe THIS algorithm; any fallback means the timed span describes a different algorithm.
- **G10 Native reread/replay possibility** — none permitted for a FastSafe claim: C9 proved `unet_fast_disk_skip=1` and zero native H2D replay; if a native reread occurred the interval is describing the native chain instead.

Candidates are audited against G1–G10 individually in §5.

---

## 4. Exact consumer/sampler-handoff requirement

Serialized-sampler consumption requires, in order, all of the following (all CONFIRMED from wrapper instrumentation):

1. `load_models_gpu(models, …)` entry (outermost; becomes ledger span `model-mgmt:load_models_gpu`; stamps `unet_gpu_demand_start` once per request for a registered UNET, `model_preload.py:4368–:4380`).
2. Optional E25 proven-ready fast return (pure bookkeeping skip, telemetry-preserving; never while CLIP critical section active; :4156–:4207) — otherwise full ModelPatcher.load walk.
3. ModelPatcher.load decomposition measured by `model_patcher_load_breakdown` = `traversal_wall_ms` + `patch_weight_wall_ms` + `residual_wall_ms` (observed live in E37; see §5.4).
4. Return ⇒ sampler may issue first UNET op; correctness thereafter rests on stream ordering (no separate fence exists at this boundary).

Therefore the earliest defensible "UNET ready for serialized sampler" wall point for a candidate is: **candidate publish point (patcher attached + unet_device_ready/record_unet_ready) AND subsequent load_models_gpu completion**. Any historical number that ends earlier measures less than the contract; any that starts later omits prerequisite candidate-owned work.

---

## 5. Bespoke algorithm narratives (per candidate)

### 5.1 E27 — QD4 storage→pinned→async-H2D probe (`gpu_transfer_phase`)

Exact behavior (`unet_qd_probe.py:1006–:1094`): opens the safetensors file raw; partitions the payload into QD static segments; allocates per-worker pinned slots and equal-sized temporary CUDA uint8 destinations; loops `preadv` into pinned then `dst.copy_(src, non_blocking=True)` issuing H2D; CUDA events around the whole issue loop; ONE `synchronize()`; computes `storage_plus_h2d_wall_ms`, `h2d_device_ms` (event delta), host-issue stats; frees pinned + dests, `empty_cache()`. It reads the FULL 12,309,817,472-byte payload.

Where it stops: bytes-on-GPU-in-temporary-buffers. There is no header/config derivation, no meta construction, no state dict, no bind, no ModelPatcher, no validation, no ownership retention, no model-management registration. The dest buffers are destroyed inside the probe.

Verdicts:
- ~1020.9 ms (`storage_plus_h2d_wall_ms=1020.8782`) is **TOTAL_FOR_MEASURED_OPERATION** (the transport probe itself; internally consistent: h2d_device 1020.7964 ≈ wall − host-issue 5.6668; combined 12.06 GB/s over the full file).
- For GoldenUnetLoad it is **PARTIAL**. Missing Golden-part work: everything in G1–G10 except transport — meta construction, sampling repair, bind, sweep, patcher, owner retention, validation, readiness publication, model-management handoff. By the C9/E28 measured anatomy those missing stages historically cost O(100–2300+) ms more (bind alone 6–9.5 ms; meta construction 19.5–2292.9 ms band; eligibility up to 1370 ms; plus patcher/owner/readiness).
- The probe's capability (raw ceiling of pinned+async-H2D transport at QD4/32) remains valid as a COMPONENT.

### 5.2 C9 — true-first-touch production FastSafe (historical run)

Exact path (single-threaded orchestration + two workers):
1. Ledger span `unet:lane-pipeline` begins; eligibility (header-only config derivation; ZImage-only; param-count/bf16/value-probe gates) — cheap in this era.
2. Worker A thread: meta construction on device("meta"), param validation, model_sampling poison detect/repair.
3. Worker B thread: source fence (`before_unet_demand`) → `_fs_fastsafe_load` = loader setup + `copy_files_to_device` (timed `fastsafe_file_gpu_wall_ms`) + `get_tensor` view instantiation → D15 GPU-token acquire → transfer-start event → optional copy-event record.
4. Join; optional scoped copy-event wait; post-load gates (key set, spot check, byte total vs 12,309,817,472); transform-INDEPENDENT gate.
5. Bind `load_state_dict(assign=True)` zero-copy; data_ptr proof; memory snapshots; residual meta sweep; bounded final `.to()` (>500 ms ⇒ fail "duplicate transfer"); single `torch.cuda.synchronize()`; final validation.
6. ModelPatcher construction; `_FastsafeOwner(loader, fb)` attach; `record_unet_ready` + ledger `unet_device_ready`; emit; reconcile; return `(patcher,)`.

Historical numbers (run `v2_2026-08-15_18-32-47`, fs 0.3.3, threads=16, block=1 GiB): header 14.49; value probe 0.94; meta get_model 2292.86 (cold-host outlier; C8 band 19.5–199.9); sampling fix 12.61; setup 21.89; **file→GPU 2172.92 (5.67 GB/s)**; instantiate 0.57; worker A/B/join 2306.3/2195.4/2298.1 (A∥B overlap ≈ 1758 ms hidden); bind 9.54; sweep+to 43.45; sync 0.05; **total pipeline wall 2743.40**. Second cold run (different region): file→GPU 2499.30 (4.93 GB/s).

Verdicts:
- `fastsafe_file_gpu_wall_ms=2172.92` ("FILE_TO_CUDA") measures ONLY the `copy_files_to_device` call inside worker B. Loader setup (21.89), view instantiation (0.57), the meta construction running concurrently, eligibility, header config, bind, sweep, patcher — all OUTSIDE it. ⇒ **PARTIAL** for GoldenUnetLoad; TOTAL only for its own call. Whether any required work occurred BEFORE this timer: yes — eligibility/header/target/mem-baseline serially precede worker B, and worker B's own fence/setup precede the timer start.
- `total_pipeline_wall_ms=2743.40` is **TOTAL** for the candidate pipeline (t0→owner attached→ready published) and satisfies G1–G10 (fallback_count=0, SHA-exact generation, no native reread). Whether it equals complete UNET_MODEL_READY wall depends on whether the request's model-management handoff (§4 step 1–3) is counted inside or after it — the C9-era artifacts do not expose a demand-side mp_load decomposition for this run, so reconstructing the full wall to post-`load_models_gpu` precision is **not possible from raw evidence** (missing boundary: demand-side mp_load breakdown for that request).
- Contamination of 2743.40: NONE_PROVEN for external blocking (workers joined internally; join ≈ max(A,B)); the A∥B overlap (~1758 ms) means summing stage walls would double-count — union accounting already applied by the report.
- INPUT_STATE_DEBT: true-cold file (report asserts standalone battery's 924 ms was cache-warm by comparison), cold host for meta construction (outlier).

### 5.3 E28 — FastSafe warm-class/final form, cold runs

Same algorithm as C9 with: T8/256 MiB/512 MiB-bbuf tuning; D15 token moved to GPU-committing section only (gate wait 250 ms → 0.1 ms); E29 ledger events; earliest-CLIP restore-time hydration co-running.

Final-run raw metrics (embedded `run_0.json`):

Run `fad442b2f11b`: eligibility 513.87; header 72.67; meta worker A 136.81 (CPU 110); **worker B wall 6206.89**; **join 6206.94**; **file→GPU 452.82 (27.19 GB/s)**; instantiate 0.53; bind 6.06; sweep/to/sync small (final_to 13.92, final_sync 0.0 via stream.wait_event); **pipeline total 6870.45**; MODEL_READINESS_GATE_MS = EXPOSED_MODEL_READINESS_MS = 6870.438; SAMPLER_GATED_BY=UNET; **`unet_gpu_commit_wait_ms=5746.928`**.

Run `5f3702b75dfb`: eligibility 1370.86; worker A 463.04; worker B wall 4265.81; join 4255.86; file→GPU 465.07 (26.47 GB/s); bind 6.30; pipeline 5995.19; **`unet_gpu_commit_wait_ms=3794.59`**.

The decisive internal fact: worker-B wall exceeds its own I/O metric by ~5754 ms / ~3800 ms, and `wait_for_unet_commit` (`fast_cold_orchestration.py:701–:711`) BLOCKS worker B at `before_unet_demand` until CLIP forward completes (timeout default 10 s; earlier E28 cycles show 10000.5–10001.2 ms timeout hits). The wait is accumulated into `unet_gpu_commit_wait_ms`.

Verdicts:
- `fastsafe_file_gpu_wall_ms` (452.8 / 465.1): **TOTAL_FOR_MEASURED_OPERATION**, and CLEAN — it executes AFTER the fence, so it carries no CLIP-forward waiting. PARTIAL for GoldenUnetLoad (same exclusions as C9's file→GPU).
- `worker_b_wall_ms` / `join_delay_ms`: **CONTAMINATED — EXTERNAL_BLOCKING** (proven: fence wait quantified at 5746.928 / 3794.59 ms). These are NOT candidate-owned compute walls.
- `total_pipeline_wall_ms` (6870.45 / 5995.19): **TOTAL for the measured operation** (whole candidate pipeline) but **CONTAMINATED — MIXED**: candidate-owned work (eligibility 513.9/1370.9 + meta ∥ transport 452.8/465.1 + post-gates/bind/validation ≈ tens of ms) PLUS proven external blocking (commit fence 5746.9/3794.6) PLUS small unattributed remainder. As a GoldenUnetLoad number it is PARTIAL-with-contamination: it does include the full candidate-owned chain to sampler-publishable state (G1–G10 met; exact SHA), so GOLDEN_PART_COMPLETENESS = PARTIAL only in the sense that the demand-side mp_load handoff (§4) is outside it — same missing boundary as C9.
- Historical critical-path exposure: the readiness gate proves the ENTIRE pipeline (including the fence wait) sat exposed on the request critical path (EXPOSED_MODEL_READINESS_MS == pipeline total == 6870.438; SAMPLER_GATED_BY=UNET). Its historical form is therefore SERIAL (overlap-dependent only internally: A∥B ≈ 130 ms; the CLIP-commit wait is anti-overlap by design — the D15/no-forbidden-overlap invariant forces UNET GPU commit after CLIP forward).
- "Warm-class": within these cold-container runs the file→GPU rate (26–27 GB/s vs C9's 5.67 cold / 2499 ms second-cold) indicates page-cache-warm file content relative to C9's true-cold runs. The warm STATE = OS page cache / volume cache residency of the same file earlier in the same container lifecycle. This state debt is named, not hidden: the 452–465 ms numbers are NOT comparable to C9's 2172.92 without stating cache state.

### 5.4 E37 — ~840.785 ms model-management/load_models_gpu interval

State context (raw, CONFIRMED): profile `e37-clean-lane-qd4`; env `COMFYMODAL_V2_UNET_FASTSAFETENSORS=0`, `COMFYMODAL_V2_NATIVE_FAST_DISK_UNET=1`; fresh restored container; `cpu_snapshot_models_retargeted` fired at mono 217187694522 (request scope, reason ok) — i.e., snapshot-carried models were retargeted to the request BEFORE the interval. Ledger chain: … CLIP forward end 219805800150 → [gap 91.76 ms unattributed] → `model-mgmt:load_models_gpu` [219897561067..220738351509] = **840.785 ms** → [gap 27.35 ms] → sampling start 220765701915.

Inside the interval (full_trace, same mono axis):
- `graph_gpu_load_start` (invocation #2, `contains_registered_unet=1`, memory_required≈28.75 GB) at 219897680377.
- `mp_load_start` 219900940257 → `model_patcher_load_breakdown`: **wall 837.042 = traversal 11.046 + patch_weight 4.913 (451 weights) + residual 821.083**; process_cpu 870 ms; thread_cpu 810 ms.
- `mp_load_end` duration 837.224; `graph_gpu_load_end` host_wall 840.687; `load_models_gpu_duration` 840.72.

What the interval represents: demand-time model-management movement of an ALREADY-CONSTRUCTED ModelPatcher whose weights were resident in CPU RAM (snapshot bootstrap materialized them during restore; the interval itself performs NO source read, NO model construction, NO patcher creation). The residual 821 ms is unattributed INSIDE the mp_load wrapper but is CPU/copy-busy (thread_cpu 810 ms ≈ 97% of residual wall) — consistent with CPU→GPU weight transfer of ~12.31 GB (~15 GB/s) plus sync; sub-op attribution beyond the three-way breakdown does not exist in the artifact ⇒ residual composition is SUPPORTED INFERENCE, not CONFIRMED line-by-line.

Verdicts:
- 840.785 is **TOTAL_FOR_MEASURED_OPERATION** (the outermost load_models_gpu call) and internally reconciles with mp_load 837.2 (+~3.5 ms wrapper overhead).
- For GoldenUnetLoad: **PARTIAL** — it reaches "weights on GPU, sampler may proceed" (contract §4 steps 1–3 satisfied) but excludes: source read, meta construction, sampling repair, patcher construction, owner concerns, and the entire restore/bootstrap prerequisite that PUT the weights into CPU RAM (restore:bootstrap 250.764 ms ledger child is part of a much larger snapshot-materialization cost outside the ledger's request axis).
- Contamination: NONE_PROVEN — no external wait identified inside the interval (thread-CPU-bounded); the 91.76 ms gap BEFORE it is outside the interval and unattributed.
- INPUT_STATE_DEBT (must be stated, not hidden): CPU-RAM-resident weights from snapshot restore + retarget; without that state this interval would include disk source I/O and be far larger.
- Do NOT call 840.785 "the UNET load time". It is the demand-time weights-to-GPU leg of a state-dependent native path.

### 5.5 K5 — post-prep demand FastSafe (363.260 / 415.655 / 406.694 ms) — REPORT_ONLY

Mechanics (code, CONFIRMED): once a FastSafe pipeline has published an all-CUDA-resident patcher, the sampler's `load_models_gpu` re-runs ModelPatcher.load bookkeeping over an already-resident model — "real serial work with no transfers" (unpatch_hooks, load-list walk, patch accounting) unless the E25 proven-ready fast return (opt-in, six fail-closed conditions) skips it (`model_preload.py:4156–:4207`). A demand interval of this shape has:
- REQUIRED_WORK_BEFORE: the entire FastSafe pipeline (its numbers belong to the C9/E28/CUR classes, not to K5);
- INSIDE the measured interval: bookkeeping only (plausibly clean; analogous to E37 invocation #1 which measured 0.71 ms for a CLIP-resident model — showing bookkeeping magnitude varies enormously with model count/state);
- AFTER: nothing candidate-owned.

Verdicts: the three values are REPORT_ONLY — no matching artifact found on disk (searched exact and fuzzy forms across md/txt/log/json). MEASURED_OPERATION_COMPLETENESS: UNKNOWN. GOLDEN_PART_COMPLETENESS: PARTIAL *by definition of the class* (post-prep suffix; prerequisite ran earlier) — but even that rests on the class name, so conservatively UNKNOWN pending the SoT. Contamination: UNKNOWN. If these numbers are demand-interval-only, comparing them against C9/E28 pipeline totals or E37's 840.785 is invalid (different boundaries).

### 5.6 R42 — ~0.878 s cache-served commit class — REPORT_ONLY

No implementation or artifact producing a ~0.878 s UNET cache-served commit was found. The only 878-ms-shaped value on disk (`modal_logs.txt:71`, `restore_total_ms: 878.2`) is a restore-method wall from a different lifecycle segment and different clock domain — explicitly rejected as evidence for this class. Warm state unnamed ⇒ per instructions the state cannot be hidden, it must be named; it cannot be named ⇒ class stays UNKNOWN. All classifications UNKNOWN; REPORT_ONLY.

### 5.7 J1 — ~0.4–0.7 s warm-commit class — REPORT_ONLY

Nearest code mechanism: prefetch-lane commit consumed at `graph_unet_demand` (`_consume_model_impl`, `model_preload.py:14694+`; lane lifecycle `cache_publish_*`/`done_event_set`/`ready` at :9714–:9753). A "warm commit" in that machinery = consuming an already-published cache object at demand; its duration would exclude all preparation by construction (OVERLAP_DEPENDENT_STAGE). No artifact matching 400–700 ms found. All classifications UNKNOWN; REPORT_ONLY.

### 5.8 CUR — current/request FastSafe implementation (HEAD)

Same `_fs_try_pipeline` lineage; selected FIRST for role=unet when `COMFYMODAL_V2_UNET_FASTSAFETENSORS` resolves truthy (`config_authority.py:342–:349`; flag spec default False at :78); `_load_unet` tries ring → meta-direct → fastsafe → `_invoke_original` native, exactly once, fail-closed (`model_preload.py:14085–:14161`). Differences vs C9 historical form: E28 tuned defaults, D15 token scope narrowed, E29 ledger events, staged-transport component hook, scoped-readiness option, E25 demand interplay. Latest whole-stage raw evidence = the E28 final pair (§5.3). Classifications inherit §5.3 with the note that HEAD code also permits the E25 demand fast-return, which (when active) moves the §4 handoff cost to near-zero and makes any K5-style demand number inapplicable simultaneously (the fast return and the bookkeeping walk are mutually exclusive per call).

---

## 6. Timing-claim completeness table

Full machine-readable version in the CSV. Summary:

| Claim (value) | Candidate | Measured-operation completeness | Golden-part completeness | Contamination | Candidate form |
|---|---|---|---|---|---|
| file→GPU 2172.92 ms | C9 | TOTAL_FOR_MEASURED_OPERATION | PARTIAL | NONE_PROVEN | COMPLETE_PRODUCTION_STAGE |
| meta get_model 2292.86 ms | C9 | TOTAL_FOR_MEASURED_OPERATION | PARTIAL (component of pipeline) | NONE_PROVEN (cold-host outlier noted) | COMPLETE_PRODUCTION_STAGE |
| bind 9.54 ms | C9 | TOTAL_FOR_MEASURED_OPERATION | PARTIAL | NONE_PROVEN | COMPLETE_PRODUCTION_STAGE |
| pipeline total 2743.40 ms | C9 | TOTAL_FOR_MEASURED_OPERATION | PARTIAL (missing demand-handoff boundary; G1–G10 otherwise met) | NONE_PROVEN | COMPLETE_PRODUCTION_STAGE |
| QD4 transport 1020.8782 ms | E27 | TOTAL_FOR_MEASURED_OPERATION | PARTIAL (probe stops at bytes-on-GPU) | NONE_PROVEN | PROBE_ONLY |
| file→GPU 452.8152 / 465.0659 ms | E28 | TOTAL_FOR_MEASURED_OPERATION | PARTIAL | NONE_PROVEN (post-fence) | COMPLETE_PRODUCTION_STAGE |
| worker_b_wall 6206.89 / join 6206.94 ms | E28 | TOTAL_FOR_MEASURED_OPERATION | PARTIAL | EXTERNAL_BLOCKING (fence 5746.93) | COMPLETE_PRODUCTION_STAGE |
| pipeline 6870.45 / 5995.19 ms | E28 | TOTAL_FOR_MEASURED_OPERATION | PARTIAL | MIXED (fence + candidate work) | COMPLETE_PRODUCTION_STAGE |
| eligibility 513.87 / 1370.86 ms | E28 | TOTAL_FOR_MEASURED_OPERATION | PARTIAL (in-pipeline prerequisite) | NONE_PROVEN | COMPLETE_PRODUCTION_STAGE |
| MODEL_READINESS_GATE / EXPOSED 6870.438 ms | E28 | TOTAL_FOR_MEASURED_OPERATION | PARTIAL | MIXED | COMPLETE_PRODUCTION_STAGE |
| load_models_gpu 840.785 ms (ledger) | E37 | TOTAL_FOR_MEASURED_OPERATION | PARTIAL | NONE_PROVEN | COMPLETE_BUT_STATE_DEPENDENT |
| mp_load 837.224 / residual 821.083 / traversal 11.046 / patch_weight 4.913 ms | E37 | TOTAL / PARTIAL(residual composition) | PARTIAL | NONE_PROVEN (CPU-busy) | COMPLETE_BUT_STATE_DEPENDENT |
| 363.260 / 415.655 / 406.694 ms | K5 | UNKNOWN | UNKNOWN | UNKNOWN | OVERLAP_DEPENDENT_STAGE (mechanics confirmed; numbers REPORT_ONLY) |
| ~0.878 s cache-served commit | R42 | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN |
| ~0.4–0.7 s warm commit | J1 | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN |

---

## 7. Blocking / overlap / prerequisite analysis

### 7.1 Method
For every long span: "what candidate-owned work executed inside, and what was it waiting for?" Waits are subtracted ONLY where exact code/event evidence identifies them; otherwise UNKNOWN.

### 7.2 Proven blocked walls

1. **E28 worker-B wall — waiting on CLIP forward (CONFIRMED).** `before_unet_demand` → `wait_for_unet_commit()` blocks until `clip_forward_done` (or 10 s timeout), `fast_cold_orchestration.py:701–:711`. Quantified per-run by `unet_gpu_commit_wait_ms`: fad442b2f11b = **5746.928 ms**; 5f3702b75dfb = **3794.59 ms**; four earlier E28 cycles show full **~10000.5–10001.2 ms timeouts** (fallback path). Consequently: pipeline totals 6870.45/5995.19 and EXPOSED_MODEL_READINESS 6870.438 contain seconds of waiting for another golden part (CLIP forward). They must never be quoted as UNET transport capability.
2. **E28-era D15 gate history (documented in-report).** Before the fix, `begin_unet_gpu_phase` covered the whole ~12.5 s pipeline and blocked graph CLIP encode (`clip_gpu_critical_enter wait_ms=11615`); after the fix the token covers only the GPU-committing section and measured gate wait dropped to 0.1 ms. Applies to interpreting any PRE-fix E28-cycle numbers (12.53 s pipeline era).
3. **E37 pre-interval gap (UNATTRIBUTED, outside the span).** 91.76 ms between CLIP-forward end and load_models_gpu start; 27.35 ms between span end and sampling start. Not subtracted from anything; flagged as unattributed seams.

### 7.3 Non-blocked long spans
- E37 840.785 ms: thread_cpu 810 ms / process_cpu 870 ms inside mp_load ⇒ busy, not blocked; contamination NONE_PROVEN at the granularity the artifact supports (sub-op composition of the 821.083 residual remains UNKNOWN).
- C9 2743.40 ms: workers joined internally; no external dependency evidenced; join ≈ max(worker walls).

### 7.4 Overlap / prerequisite accounting (per candidate)

Legend: REQ_BEFORE / REQ_INSIDE / REQ_AFTER relative to the measured interval; CPE = historical critical-path exposure; OVLP = historical overlap with other golden parts; ISD = input-state debt.

**C9 (interval = 2743.40 pipeline):**
- REQ_BEFORE: eligibility/header/parity/target/mem (serial, inside pipeline t0 but before workers — counted inside); restore-time CLIP hydration NOT a prerequisite of this candidate.
- REQ_INSIDE: meta construction (A) ∥ fence+setup+file→GPU+views (B), join, post-gates, bind, sweep, final .to, sync, validation, patcher, owner attach, readiness publish.
- REQ_AFTER: sampler-side load_models_gpu handoff (bookkeeping or E25 fast-return) — outside; boundary not instrumented for THIS run ⇒ complete UNET_MODEL_READY wall not reconstructible from raw evidence (exact missing boundary: demand-side mp_load breakdown + gap seams).
- CPE: exposed (loader runs on request path; non-scheduling request wall 18.33 s context).
- OVLP: internal A∥B only (≈1758 ms hidden; union ≠ sum). With other golden parts: none proven.
- ISD: true-cold file + cold host (meta outlier 2292.86).

**E28 (interval = pipeline totals):**
- REQ_BEFORE: as C9, plus eligibility ballooning (513.9/1370.9 ms) INSIDE the pipeline; earliest-CLIP hydration runs concurrently earlier in the lifecycle (separate golden part).
- REQ_INSIDE: candidate chain as C9 PLUS proven fence wait (external) 5746.9/3794.6 ms.
- REQ_AFTER: demand handoff (E25-eligible at HEAD; not exercised in these runs' artifacts).
- CPE: fully exposed (EXPOSED_MODEL_READINESS == pipeline total; SAMPLER_GATED_BY=UNET). Serial form.
- OVLP: internal A∥B ≈ 130–260 ms; with CLIP forward: forbidden-by-design (fence enforces zero overlap of UNET GPU commit with CLIP critical).
- ISD: page-cache-warm file content within container lifecycle (26–27 GB/s transport vs C9 5.67 cold).

**E37 (interval = 840.785):**
- REQ_BEFORE: snapshot bootstrap/materialization of UNET weights to CPU RAM + retarget at request scope (restore:bootstrap 250.764 ledger child; `cpu_snapshot_models_retargeted`); CLIP hydration+forward completed before interval.
- REQ_INSIDE: mp_load = traversal 11.046 + patch_weight 4.913 + residual 821.083 (weights CPU→GPU + sync; sub-op UNKNOWN).
- REQ_AFTER: none candidate-owned; sampling starts 27.35 ms later.
- CPE: fully exposed on serial ledger axis (zero-gap chain member).
- OVLP: none (clean-lane forbids overlap; none observed).
- ISD: CPU-RAM-resident weights from restore snapshot — the entire reason the interval is sub-second.

**K5:** REQ_BEFORE = whole FastSafe pipeline (elsewhere); REQ_INSIDE = bookkeeping-only walk (or E25 skip ⇒ interval absent); REQ_AFTER = none. CPE: unknown (REPORT_ONLY). OVLP: by definition the class hides prep elsewhere ⇒ overlap-dependent. ISD: GPU-resident FastSafe-bound model.

**R42/J1:** all five fields UNKNOWN (no artifacts).

### 7.5 Union rule
Overlapping candidate-owned intervals (A∥B) are union-accounted only where raw clocks allow (C9/E28 publish worker start/end mono stamps and `worker_ab_overlap_ms`; E28 fad442b A∥B overlap ≈ 130.7 ms from A-end 322153… vs B-start — computed from worker walls: A 136.81 ending ≈ join−start_delay; exact union from stamps). Total candidate-owned wall for E28 pipeline excluding the proven fence wait = pipeline_total − commit_wait (6870.45−5746.93 = **1123.52 ms**; 5995.19−3794.59 = **2200.60 ms**) — arithmetic on raw clocks is legitimate because the fence wait is measured on the same monotonic axis and accumulates inside worker B before the I/O timer starts; residual unattributed slack remains inside these unions and is not further decomposable.

---

## 8. Same-boundary comparability matrix

Rows/columns share a semantic completion condition ⇔ cell = COMPARABLE. All off-diagonal cells are NON-COMPARABLE unless noted. Input-state semantics noted explicitly.

| Boundary → | B1 raw transport (bytes→temp GPU bufs) | B2 copy_files_to_device call | B3 candidate pipeline → sampler-publishable patcher | B4 demand weights-to-GPU from CPU-RAM snapshot | B5 demand bookkeeping over GPU-resident model | B6 warm/cache-served commit (unnamed state) |
|---|---|---|---|---|---|---|
| **E27** 1020.8782 | COMPARABLE (self) | — | — | — | — | — |
| **C9** 2172.92 / 2499.30 | — | COMPARABLE (self; NOTE C9 true-cold vs E28 cache-warm input states) | — | — | — | — |
| **C9** 2743.40 | — | — | COMPARABLE (self; cold-host meta outlier inflates) | — | — | — |
| **E28** 452.82/465.07 | — | COMPARABLE to C9 file→GPU ONLY with cache-state annotation (warm vs cold) | — | — | — | — |
| **E28** 6870.45/5995.19 | — | — | COMPARABLE to C9 2743.40 ONLY after removing proven fence wait (1123.52 / 2200.60 residuals) and noting eligibility/meta variance; raw values NOT comparable | — | — | — |
| **E37** 840.785 | — | — | — | COMPARABLE (self) | — | — |
| **K5** 363.26/415.66/406.69 | — | — | — | — | REPORT_ONLY; comparable only to other B5 measurements (none on disk) | — |
| **R42** ~0.878 s | — | — | — | — | — | UNDEFINED (state unnamed) |
| **J1** 0.4–0.7 s | — | — | — | — | — | UNDEFINED (state unnamed) |

Explicit non-comparabilities (do NOT casually compare): source-only vs file_to_cuda vs model-management vs demand commit vs model-ready vs warm/cache-served vs post-prep demand suffix. Cross-cell comparisons that WOULD be tempting and are INVALID: E27 1020.9 vs E28 452.8 (probe temp-bufs+free vs production owned buffers, different QD configs, cache states); K5 demand suffix vs E37 840.785 (bookkeeping-only vs physical H2D); R42 0.878 vs E37-era restore 878.2 (different lifecycle segments entirely).

---

## 9. Candidate capability matrix

| Capability | E27 probe | C9 FastSafe | E28 FastSafe | CUR FastSafe (HEAD) | E37 native snapshot-demand | K5 class | R42/J1 |
|---|---|---|---|---|---|---|---|
| Produces ModelPatcher (G1) | ✗ | ✓ | ✓ | ✓ | ✓ (pre-existing) | n/a (suffix) | ? |
| Storage ownership for lifetime (G2) | ✗ (frees bufs) | ✓ loader_retained | ✓ loader_retained | ✓ | ✓ module-owned | inherited | ? |
| Meta construction + sampling repair (G3) | ✗ | ✓ | ✓ | ✓ | done pre-interval | inherited | ? |
| Fail-closed validation gates (G5) | partial (hash windows elsewhere in probe battery) | ✓ | ✓ | ✓ | ComfyUI-native only | inherited | ? |
| Device readiness fence (G6) | ✓ (probe sync) | ✓ synchronize / scoped wait_event | ✓ (stream.wait_event observed) | ✓ | stream-ordering + mm completion | inherited | ? |
| Model-management mutation (G7) | ✗ | ✓ via normal graph flow; E25-eligible at HEAD | ✓ | ✓ + E25 fast-return option | ✓ (this IS the mm step) | ✓ (this IS the suffix) | ? |
| Byte-exact output proof | n/a | ✓ SHA exact | ✓ SHA exact (both runs) | inherits lineage | ✓ SHA exact | ? | ? |
| Whole-stage historical timing exists | ✗ | ✓ 2743.40 | ✓ 6870.45/5995.19 (fence-contaminated) | = E28 latest | ✓ 840.785 (partial-scope) | REPORT_ONLY | none |
| Reusable WITHOUT being whole stage | ✓ transport ceiling component | ✓ | ✓ | ✓ | ✓ (state-dependent leg) | ✓ (suffix semantics) | unknown |

---

## 10. Missing evidence that must be captured in serial validation

1. **Demand-side handoff closure for FastSafe claims**: for every FastSafe whole-stage claim, capture the subsequent `graph_gpu_load_start/end`, `mp_load_start/end`, and `model_patcher_load_breakdown` (or explicit `graph_gpu_load_fast_return` event) with mono stamps on the same axis, plus the seam gaps. Without these, pipeline-total claims can never close to the §4 contract.
2. **Fence-wait attribution inside worker B**: emit `before_unet_demand` enter/exit stamps (not just the cumulative `unet_gpu_commit_wait_ms`) so worker_b_wall decomposes exactly into fence-wait + setup + copy + instantiate + gate-acquire.
3. **Eligibility cost breakdown**: eligibility_wall_ms reached 1370.86 ms with no internal decomposition (path resolution vs header parse vs probe). Capture child stamps.
4. **Cache-state proof for transport numbers**: record page-cache/volume-cache state (e.g., read-twice delta or cgroup/storage counters) alongside `fastsafe_file_gpu_wall_ms` so cold/warm classes are provable, not asserted.
5. **E37 residual sub-op attribution**: instrument inside ModelPatcher.load (weight-to-device loop vs sync vs allocator events) to resolve the 821.083 ms residual composition.
6. **Seam accounting around load_models_gpu**: the 91.76/27.35 ms unattributed seams adjacent to the E37 span need named owners.
7. **K5/R42/J1 provenance**: locate or regenerate raw artifacts for the Phase-O classes; until then they stay REPORT_ONLY and must not enter cohorts.
8. **Inclusive-cost correction inputs (v2.1)**: per-worker start/end mono stamps were sufficient here; ensure every future candidate publishes interval endpoints (not just durations) so union math is always possible.
9. **Readiness-gate symmetry**: `MODEL_READINESS_GATE_MS` currently equals exposure-from-start; also record gate→sampling-entry latency so "ready" and "consumed" are separately provable.
10. **Clock metadata per run** (per E38B §14): get_clock_info + micro version in-container, so cross-artifact unions stay same-domain.

---

## 11. Raw evidence appendix (verbatim)

### 11.1 E27 QD4/32 gpu_transfer (`_e27_unet_qd_evidence.json`, sections.gpu_transfer)
```json
{
    "kind":  "gpu",
    "qd":  4,
    "block_mib":  32,
    "status":  "ok",
    "total_bytes":  12309817472,
    "storage_plus_h2d_wall_ms":  1020.8782,
    "h2d_device_ms":  1020.7964,
    "h2d_host_issue_total_ms":  5.6668,
    "h2d_host_issue_max_ms":  0.1008,
    "storage_gbps":  150657.5985,
    "combined_gbps":  12.0581,
    "pinned_bytes":  134217728,
    "gpu_temp_bytes":  134217728,
    "issue_count":  368
}
```
Report narrative (E27 forensics MD): "GPU transfer phase (QD4/32): storage→pinned→async H2D full file 1020.9 ms combined 12.06 GB/s; `h2d_device_ms=1020.8` — the device copy dominates and the storage read is fully hidden under it; `h2d_host_issue_total=5.7 ms`."

### 11.2 C9 valid-run pipeline telemetry (V2_BATCH_C9_FASTSAFETENSORS_INTEGRATION_REPORT.md §6 table, verbatim rows)
```
| header/config wall | 14.49 ms |
| value probe wall | 0.94 ms |
| meta get_model wall | 2292.86 ms (cold-host outlier; C8 band 19.5–199.9 ms) |
| sampling fix wall | 12.61 ms (1 poisoned tensor repaired) |
| fastsafe setup wall | 21.89 ms |
| fastsafe file→GPU wall | 2172.92 ms (5.67 GB/s) - true-cold (standalone battery's 924 ms/13.3 GB/s was cache-warm) |
| fastsafe instantiate wall | 0.57 ms |
| worker A / worker B / join | 2306.3 / 2195.4 / 2298.1 ms (concurrent; join ≈ worker A) |
| bind wall | 9.54 ms (zero-copy assign; native 109.6 ms) |
| final sweep+to wall | 43.45 ms |
| final sync | 0.05 ms |
| total pipeline wall | 2743.40 ms |
```
Run identity: v2_2026-08-15_18-32-47 · deployment d0c3dfefc3ba4742 · fallback_count=0 · output SHA sha256:20b10e1f99831bc758d9df82f43ce0beb1cbc636a740d11a29eb2bffe90e5260 (EXACT) · unet_fast_disk_skip=1 · threads=16 / block 1 GiB.
Second cold run (addendum §9, ap-northeast-1): fastsafe file→GPU 2499.30 ms (4.93 GB/s).

### 11.3 E28 final run `fad442b2f11b` — `unet_fastsafetensors_pipeline` metadata (embedded run_0.json, verbatim subset)
```json
"loader_version": "0.3.3", "threads": 8, "max_copy_block_size_bytes": 268435456,
"header_config_wall_ms": 72.6653, "meta_get_model_wall_ms": 132.1625,
"fastsafe_setup_wall_ms": 6.0178, "fastsafe_file_gpu_wall_ms": 452.8152,
"fastsafe_instantiate_wall_ms": 0.527, "worker_a_wall_ms": 136.8117,
"worker_b_wall_ms": 6206.8911, "join_delay_ms": 6206.9429,
"total_bytes": 12309817472, "fastsafe_gbps": 27.1851, "bind_wall_ms": 6.064,
"copy_event_recorded": true, "copy_event_waited": true,
"copy_event_sync_method": "stream.wait_event", "owner_mode": "loader_retained",
"data_ptr_sample_match": true, "final_to_wall_ms": 13.9201, "final_sync_wall_ms": 0.0,
"fallback_count": 0, "total_pipeline_wall_ms": 6870.4504, "status": "ok",
"eligibility_wall_ms": 513.8731, "cpu_affinity_count": 28
```
Readiness gate (same run):
```json
"name": "model_readiness_gate",
"CLIP_READY_AT": 322009633733, "UNET_READY_AT": 322285764974,
"MODEL_READINESS_GATE_AT": 322285764974, "SAMPLER_GATED_BY": "UNET",
"MODEL_READINESS_GATE_MS": 6870.438, "EXPOSED_MODEL_READINESS_MS": 6870.438
```
Commit-fence wait (same run): `"unet_gpu_commit_wait_ms": 5746.928`

### 11.4 E28 final run `5f3702b75dfb` — verbatim subset
```json
"fastsafe_file_gpu_wall_ms": 465.0659, "worker_a_wall_ms": 463.0365,
"worker_b_wall_ms": 4265.8079, "join_delay_ms": 4255.8631,
"fastsafe_gbps": 26.469, "bind_wall_ms": 6.3022, "total_pipeline_wall_ms": 5995.1936,
"eligibility_wall_ms": 1370.8611, "cpu_affinity_count": 28
```
Commit-fence wait: `"unet_gpu_commit_wait_ms": 3794.59`
Timeout-era waits (earlier E28 cycles): `unet_gpu_commit_wait_ms` = 10000.556 / 10000.698 / 10001.03 / 10001.163.

Pre-fix blocked-CLIP evidence (E28 MD §1): "the graph CLIP encode waited (`clip_gpu_critical_enter wait_ms=11615`) … Measured gate wait: 250 ms → 0.1 ms."

### 11.5 E37 ledger spans (run_001_sample.json, canonical_ledger.spans verbatim subset)
```
CLIP forward                1110.221 ms  [218695575911..219805800150]
model-mgmt:load_models_gpu   840.785 ms  [219897561067..220738351509]
sampling                    4748.2    ms  [220765701915..225513922007]
model-mgmt:load_models_gpu    57.792  ms  [226283853637..226341643699]
model-mgmt:load_models_gpu     0.803  ms  [218693211531..218694021961]
restore:bootstrap            250.764  ms  [217180914871..217031664445]
```
E37 effective_env (verbatim subset): `COMFYMODAL_V2_UNET_FASTSAFETENSORS=0`, `COMFYMODAL_V2_NATIVE_FAST_DISK_UNET=1`, `COMFYMODAL_V2_SNAPSHOT_EXCLUDE_UNET=0`, `COMFYMODAL_V2_PIN_UNET_TRANSFER=0`.
full_trace events (verbatim metadata subsets):
```
cpu_snapshot_models_retargeted  mono 217187694522  {"reason":"ok","stage":"request_time"}
graph_gpu_load_start (#2)       mono 219897680377  {"contains_registered_unet":1,"memory_required":28749437337.6,"force_full_load":false,"caller_classification":"graph_model_loading"}
mp_load_start                   mono 219900940257  {"model_type":"ModelPatcher"}
model_patcher_load_breakdown    mono 220738095949  {"wall_ms":837.042,"traversal_wall_ms":11.046,"traversal_process_cpu_ms":10.0,"patch_weight_count":451,"patch_weight_wall_ms":4.913,"cast_count":0,"cast_wall_ms":0.0,"residual_wall_ms":821.083,"process_cpu_ms":870.0,"thread_cpu_ms":810.0}
mp_load_end                     mono 220738154779  {"duration_ms":837.224,"model_type":"ModelPatcher"}
graph_gpu_load_end (#2)         mono 220738287049  {"host_wall_duration_ms":840.687,"thread_cpu_duration_ms":810.0}
load_models_gpu_duration        mono 220738325679  {"duration_ms":840.72,"gpu_request_invocation_count":2}
graph_gpu_load_start (#1)       mono 218693362881  {"contains_registered_unet":0,"memory_required":0}
load_models_gpu_duration (#1)   mono 218693973761  {"duration_ms":0.71}
graph_gpu_load_start (#3)       mono 226283976046  {"contains_registered_unet":0,"memory_required":9099509760.0}   // VAE
load_models_gpu_duration (#3)   mono 226341612919  {"duration_ms":57.723}
```

### 11.6 Consumer-boundary code (verbatim excerpts)
E25 proven-ready fast return precondition rationale — `model_preload.py:4156–:4162`: "The fastsafetensors/execution UNET lane already bound + validated every parameter on the target device. The sampler's subsequent load_models_gpu re-runs ComfyUI's ModelPatcher.load bookkeeping (unpatch_hooks, load-list walk, patch accounting) over an already resident model — real serial work with no transfers."
Demand stamp — `model_preload.py:4368–:4377`: "Always-on UNET first-CUDA demand start … `set_unet_gpu_demand_start(...)`; emit `unet_gpu_demand_start`".
Fence — `fast_cold_orchestration.py:701–:711`: `wait_for_unet_commit` blocks on `self._clip_forward_done.wait(timeout=…)`, accumulating `unet_gpu_commit_wait_ms`.
Readiness gate — `gpu_lane_coordination.py:282–:305`: `gate_ns = max(clip_ready, unet_ready)`; `SAMPLER_GATED_BY`; `EXPOSED_MODEL_READINESS_MS = gate_ns − started_ns`.

### 11.7 REPORT_ONLY values (no raw artifact found; carried from the Phase-O brief)
```
K5: 363.260 ms ; 415.655 ms ; 406.694 ms   (post-prep demand FastSafe)
R42: ~0.878 s                              (cache-served commit class)
J1: ~0.4–0.7 s                             (warm-commit class)
```
Rejected look-alike: `modal_logs.txt:71` `restore_total_ms': 878.2` — restore-method wall, different lifecycle segment and boundary; NOT R42 evidence.

---

## 12. Exact source/body hashes (SHA-256)

Files (full, as audited at this working tree):

| SHA-256 | Bytes | Path |
|---|---|---|
| bd4aa4327773b54894b7bb6baeb95a4dd6b1e993fe3f679e0ad59339a995a50c | 100206 | comfymodal_runtime/unet_fastsafetensors.py |
| ef65a75c9b703031428ac6a51f0a1d097c4f8c8f710c7e5597db03139266311b | 66029 | comfymodal_runtime/unet_qd_probe.py |
| 4affe1e06a3acc240418584d4e08a2210243b7de3f50e3ffe73c177c8eceeeed | 1018301 | comfymodal_runtime/model_preload.py |
| c5f510f5c7bc1b3771d4f96883d772a86d391366dd63c6674ee876f695d0fa8a | 22166 | comfymodal_runtime/gpu_lane_coordination.py |
| 066631118edf1c65e412e43efd62eaefb4edbd236095574b74ba3b11c8370014 | 26951 | comfymodal_runtime/config_authority.py |
| 3fe8b8e885f5feae01a68c98d7387a2190d06d6fdd96c36c363489981921989c | 19323 | V2_BATCH_C9_FASTSAFETENSORS_INTEGRATION_REPORT.md |
| e71efb5bc91f4debee6fe330aed6b0e2cecda1fa988d4c8c6bbe4c7dd2ba1df1 | 440644 | V2_BATCH_E27_FIVE_TARGET_CRITICAL_PATH_FORENSICS.md |
| 522419ad195ba2f8af1a6ae1094d643195d77568b4c0ca9f748cfdc4deecd14f | 12846926 | V2_BATCH_E28_CRITICAL_PATH_IMPLEMENTATION_AND_VALIDATION.md |
| 3f953a32adf2ff9cfa35a8d87854ad93bd92febee75188b03ed62a97ad88893c | 39736 | E38B_CANONICAL_TIMING_AND_VALIDATION_CONTRACT_AUDIT.md |
| a8a93bb47077c4a5ea5d8d4dc5eea0397d95381ce8e13e0a3a0962ed15918687 | 3150 | E37_CLEAN_LANE_ALGORITHM_RECOVERY_REPORT.md |
| ca50c804e6d5f4139ba76eb0560c419283c1c1bc1a0fab245c60edcc699fcaa4 | 172176 | _e27_unet_qd_evidence.json |
| 4b83bad962db2a216ab0a03acf8a200a66eb14a238394d38cf3215fcacd8b560 | 783156 | ..\..\comfymodal-data\benchmarks\runs\v2_2026-08-21_22-35-45\run_001_sample.json |

Key bodies (line ranges in the hashed files above):

| Body | Location |
|---|---|
| `_fs_fastsafe_load` | unet_fastsafetensors.py:882–:920 |
| `_fs_try_pipeline` (orchestrator; workers, join, bind, sweep, validate, patcher, owner, readiness) | unet_fastsafetensors.py:1098–:2185 |
| `_FastsafeOwner` | unet_fastsafetensors.py:2188–:2198 |
| `gpu_transfer_phase` | unet_qd_probe.py:1006–:1094 |
| `load_models_gpu` wrapper + E25 fast return | model_preload.py:4141–:4207 |
| `unet_gpu_demand_start` stamping | model_preload.py:4368–:4380 |
| `_consume_model_impl` (graph demand/wait/slack) | model_preload.py:14694–:14823 |
| `wait_for_unet_commit` / `before_unet_demand` | fast_cold_orchestration.py:701–:767 |
| `_readiness` / `record_unet_ready` | gpu_lane_coordination.py:273–:337 |
| UNET loader-selection precedence | config_authority.py:321–:354 |

— End of OC4 audit. Evidence only; no GoldenUnetLoad_v1 selection, no QD adapter recommendation, no redesign.
