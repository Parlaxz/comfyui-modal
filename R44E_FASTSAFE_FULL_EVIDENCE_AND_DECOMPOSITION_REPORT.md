# R44E — Full Evidence Reconciliation, Durable Decomposition, and UNET-Prep Overlap Repair

Batch: R44E · Owner: R44E (single deployment owner) · Worktree `../comfyui-modal-r42` · Branch `r42-golden-reconciliation` · HEAD `0c59f46e…` (no commits/push/merge/reset)
Profile `r44-request-fastsafe` (controls frozen) · Exactly ONE valid deployment (`8951dfd9…`) · Exactly ONE paid cold request · STOPPED after the gate.
Gate: `.v2ctl/gates/gate_20260824-025048_2da1a436.json` **valid=1, reasons []** · request `v2-benchmark-0-d5df02fd8dba` · SHA exact ✓ · RuntimeStatus NOMINAL · ledger ok/zero-gap.

Companion raw log: `R44E_FASTSAFE_FULL_EVIDENCE_AND_DECOMPOSITION_RAW_LOG.txt` (all payloads verbatim).
Pre-implementation gate file: `R44E_R44D_EXISTING_EVIDENCE_INVENTORY.md` (`R44E_EVIDENCE_RECONCILIATION_COMPLETE = YES` written before any code change).

---

## A. What R44D already knew but its summary omitted  (REQUIRED section)

All of the following existed in persisted R44D artifacts and was absent or under-emphasized in the R44D Markdown summary:

| Existing R44D evidence | Value | Where it lived |
|---|---:|---|
| `load_models_gpu role=CLIP` wall + CPU + threads | **1103.880 ms**, process_cpu 1290 ms, threads 52→53→52 | run_0.json `cpu_owner_records[0]` |
| `encode_from_tokens` vs inner forward vs node | **3080.853 / 1973.478 / 3092.524 ms** — the decomposition identity CLOSES with 3.495 ms residual; “CLIP forward ≈3.08 s” framing was wrong | run_0.json cpu_owner + spans |
| **Broad UNET H2D with exact boundaries** | **2719.655 ms**, mono 258856247904→261575903066 — the R44D Gantt row was derived from this persisted trace row; “UNET transfer unavailable” claims were never true | run_0.json GPU-lane rows |
| Inside-UNET-node phase split (derivable) | ≈1191 ms pre-transfer (prep-arm+join+gate) vs 2719.655 ms transfer window — reconciles the 3911 ms node wall exactly | derived via epoch↔mono anchor |
| CUDA alloc/reserved across CLIP forward | +33.5 MB / +239 MB, cuda_no_sync=true, thread/process CPU 1020/1300 ms | run_0.json `clip_forward_end` |
| The only native graph-loader read | 349.605 ms / 335,304,388 B = the VAE (ends BEFORE CLIP node start) — proves CLIP/UNET did no native full reads | run_0.json `active_read_records` |
| Two extra `load_models_gpu[other]` walls | 42.608 ms and 71.862 ms | run_0.json cpu_owner_records |
| Clean-lane ordering stamps | restore→identity→forward_start→forward_end in mono ns | run_0.json `clean_lane_proof` |
| `plan_time_unet_source_h2d` forbidden-attempt record | observational only at plan-identity instant; NOT the request prep and NOT a blocker | run_0.json clean_lane_proof |

This section exists so future agents re-read artifacts before declaring metrics “unavailable”.

## B. R44D evidence inventory

Full table preserved in `R44E_R44D_EXISTING_EVIDENCE_INVENTORY.md` (sections 3A–3F cover restore/setup, CLIP loader, CLIP encode, UNET, source-prep, sampling/VAE/output; every row carries value, source artifact, exact key, persistence flag, confidence). Classification outcome:

- **DATA_ALREADY_PRESENT_AND_USABLE**: 9 categories (see §A).
- **DATA_PRESENT_BUT_TOO_BROAD**: broad UNET H2D (includes copy+instantiate+adopt); CLIP node window (transport+construction fused); dual `modal_scheduling` sink values (6170.1 vs 4102.771).
- **DATA_GENUINELY_MISSING** (the only drivers of new code): CLIP FastSafe sub-walls; CLIP descriptor wall/cache-hit; CLIP bind_mode + sampled storage counts; seam counters; CLIP four-point CUDA capture; UNET persistence of already-measured walls; durability of ALL ctx.telemetry events; prep durable metrics; CUDA deltas across `load_models_gpu`.

## C. Truly missing telemetry before R44E

Exactly the nine items above — each proven absent by direct keyword sweeps of every artifact (raw log §K histogram: `clip_fast_load*`, `unet_fastsafe_pipeline`, `bind_mode`, `storage_identity`, `request_fastpath_*` appeared **0 times** in all R44D persisted files).

## D. R44E instrumentation additions → question answered

| New durable event/field | Missing question it answers |
|---|---|
| `clip_fast_load_end.fastsafe_copy_wall_ms` (+setup/get_keys/get_tensor_loop) | Exact CLIP `copy_files_to_device` boundary inside the old fused transport number |
| `clip_fast_load_end.descriptor_wall_ms / descriptor_cache_hits` | Descriptor/header cost and cache behavior |
| `clip_fast_load_end.bind_mode + sampled_{tensor,same_storage,non_same_storage}_count` | Did comfy actually bind served CUDA storages? |
| `clip_fast_load_end.seam_served_hits / seam_passthrough_calls` | Single-physical-read proof (native reader shadowing) |
| `clip_fast_load_end.cuda_{allocated,reserved}_{before,after_fastsafe,after_construction}` | Four-point CLIP VRAM closure |
| `unet_fastsafe_pipeline.fastsafe_{setup,copy,instantiate}_wall_ms` | Persist the ALREADY-MEASURED but previously-dropped UNET copy wall |
| `unet_fastsafe_pipeline.{header_detect,skeleton,bind,identity_validation}_wall_ms` | Adoption internals behind the old single `adopt_ms` |
| `unet_fastsafe_pipeline.copied_count / final_validation_all_params_on_target` | 453-point storage truth |
| `unet_source_prep_armed/joined` (+ stamps, touched bytes, read count, stop reason) | Durable prep lifecycle |
| `unet_fastsafe_pipeline.unet_prep_overlap_ms / pct / tails` + raw mono stamps | Overlap contract verification without summary-only claims |
| `_CpuTimer.cuda_{allocated,reserved}_delta_bytes` (all roles) | What `load_models_gpu(CLIP)` physically does |
| Dual-emission in `FastPathRequestContext.telemetry` (ONE payload → diagnostics + canonical RuntimeTrace) | The R44D diagnostics-sink persistence hole |

No duplicate instrumentation: existing broad H2D row, cpu_owner records, t4–t8 keys, loader_selection, ledger, waterfall are consumed as-is; nothing already measured was re-instrumented.

## E. CLIP load closure (R44E measured)

```text
CLIPLoader node (t4_clip_load)                    = 4825.536 ms
  descriptor/header work                          =   27.547 ms  (cache_hits 0)
  FastSafe physical file→CUDA                     = 2117.326 ms
      setup 11.272 + copy_files_to_device 1934.712
      + get_keys 0.018 + get_tensor loop 0.317
      bytes 8,044,982,048 (qwen_3_4b.safetensors, 398 tensors)
      effective copy throughput = 4.159 GB/s
  tensor/view/state-dict assembly                 =    (inside construction below)
  original Comfy CLIP construction over served dict = 2670.544 ms  (bind_ms; seam_served_hits=1,
                                                    passthrough=0 ⇒ exactly one physical read)
  binding/owner work                              = owner_attach_count 1, owner_retained true
  RESIDUAL                                        =   10.119 ms  (0.21%)  ✓ closes (<250 ms, <5%)
```

**bind/storage verdict (measured, not inferred):** `bind_mode = COPY_CUDA`, sampled 8/8 non-same-storage.
CUDA: before FastSafe 0 → after FastSafe 8,044,936,192 → after construction 8,044,936,192 → **before inner forward 16,146,645,504**.
⇒ The served FastSafe storages stay pinned by the retained owner while comfy materializes a SECOND full copy during encode — full double residency (~2×7.5 GiB). `R44D_CLIP_NO_SECOND_H2D=YES` was a structural claim; measurement now shows the second materialization happens later, inside `load_models_gpu`.

## F. CLIP encode closure (R44E measured)

```text
encode_from_tokens                = 4625.382 ms (span) / 4628.329 (cpu_owner)
  model/device preparation        = 2283.612 ms  load_models_gpu(CLIP)
     cuda_allocated Δ +8,101,709,312 B ; reserved Δ +8,103,395,328 B  ← MODEL-SIZED ALLOCATION
  transformer forward (inner)     = 2330.498 ms  (alloc Δ +33.5 MB, reserved Δ +239 MB,
                                    cuda_no_sync=true, process_cpu 6110 ms ⇒ ~2.6 effective cores)
  other measured work (tokenize…) = residual
  RESIDUAL                        =   11.272 ms (0.24%)  ✓ closes
outer encode wrapper              = 4689.879 ms (alloc Δ +8,135,263,744) — consistent
```

What `load_models_gpu(CLIP)` does — answered by measurement: it performs a **model-sized device (re)materialization** (+8.10 GB allocated), not bookkeeping (the two `[other]` calls moved ≤174 MB). Combined with E’s COPY_CUDA verdict, CLIP currently pays for its weights on device TWICE: once by FastSafe transport (1934.7 ms), once again inside `load_models_gpu` (2283.6 ms).

## G. UNET node closure (R44E measured)

```text
UNETLoader node (t4b_unet_load)       =  819.495 ms   (R44D: 3911 ms → −77%)
  entry→join segment                  =   75.258 ms  (eligibility + descriptor + path resolution)
  prep join                           =    0.049 ms  (readers had ALREADY completed)
  GPU gate wait                       =    1.089 ms
  FastSafe setup                      =    3.859 ms
  FastSafe exact file→CUDA            =  624.677 ms   bytes 12,309,866,400 ⇒ 19.706 GB/s (page-cache warm)
  instantiate (keys+tensor views)     =    0.355 ms
  adoption total                      =  111.888 ms
     detection 5.526 + skeleton 80.832 + assign=True bind 13.669 + identity/validation 11.839 (=111.866 ✓)
  RESIDUAL                            =    2.320 ms (0.28%)  ✓ closes
Storage identity: 453/453 same-storage, copied_count 0, owner retained, final_validation all-on-target TRUE
```

Broad-vs-exact reconciliation (BOTH preserved): persisted GPU-lane row `UNET H2D = 741.786 ms`
(mono 225474623207→226216409280) is the transfer WINDOW = exact copy 624.677 + instantiate 0.355 + adopt 111.888 ≈ 736.92 + inter-boundary edges ≈ 741.786 ✓. The R44D-era broad number (2719.655 ms cold) and this run’s exact number are different, both real, measurements of different boundaries under different cache states.

## H. UNET overlap (exact timestamps, mono ns)

```text
CLIP outer-forward start   220645206105   (encode wrapper entry)
prep armed/start           220645216105   trigger="clip_forward_start"  (10 µs after forward start)
CLIP outer-forward end     225335086492   (4689.880 ms window)
join start (demand)        225472751458   join end 225472803237 (wall 0.049 ms — nothing left to read)
UNET transfer-window start 225474623207
prep touched               12,309,866,400 B (FULL file), read_count 1468, stop_reason "completed",
                           finished_before_demand true, source_fence_valid true
overlap with CLIP forward  4689.870 ms  = 97.15 % of prep span
tail remaining at forward end 137.717 ms ; tail at demand 137.665 ms (graph transition +
                           in-node pre-join work — NOT unread bytes)
```

Contract compliance (§12): prep armed AFTER CLIP FastSafe transport ended (220645216105 > transport end ≈215962400780) — overlap is with CLIP COMPUTE (load_models_gpu + forward), never competing checkpoint I/O. Root cause of the R44D zero-overlap defect: `mark_clip_forward_start()` never armed prep (arming existed only inside the UNET wrapper); fixed by storing plan-derived immutable UNET source identity pre-graph (`build_restore_model_spec` walker over ExecutionPlan workflow inputs + node-identical path resolution + stat; fail-closed on ambiguity) and arming at forward start. Disclosure: `unet_source_identity_resolved` itself remains diagnostics-local (emitted before trace activation); its effect is durably proven by the armed event above.

## I. Complete waterfall (R44E, one cold request)

restore_total 818.357 · application_restore 905.965 · restore→method_entry 49.866 · method/setup 109.956 · PromptExecutor/cache setup 263.623 · pre_sampler_execution 10793.307 · **CLIP load decomposition (§E)** · CLIP model-management `load_models_gpu(CLIP)` 2283.612 · CLIP forward 2330.498 inner / 4689.879 outer · UNET prep (armed@forward-start, 97.15 % overlapped) · UNET transfer 624.677 exact / 741.786 broad · UNET adoption 111.888 · sampler_node→sampling 1461.501 · sampling 3727.396 · post_sampling_transition 649.850 · VAE decode 494.346 · output_persistence 363.472 · remote_local_return 16.0 · app wall_ms 59169.2 · command→response 74363.8 · scheduling 34232.862.

Platform-variance warning: this run drew an unusually large modal_scheduling (34.23 s vs R44D 6.17 s); app-wall comparisons must exclude platform time. In-application critical path improved decisively: CLIP node 4825.536 vs 6462.066 (−1636.5 ms) and UNET node 819.495 vs 3910.982 (−3091.5 ms) against R44D, with identical frozen controls and exact SHA.

### Historical comparison (single samples; no distribution claims)

| Metric | R44E | R44D | R44C native | Historical |
|---|---:|---:|---:|---:|
| CLIP node | 4825.5 | 6462.1 | 4771 | E37 hydration ~1160 |
| load_models_gpu(CLIP) | 2283.6 | 1103.9 | — | — |
| encode_from_tokens | 4625.4–4628.3 | 3080.9 | forward ~3425 | E37 forward ~1110 |
| inner forward | 2330.5 | 1973.5 | — | — |
| UNET node | 819.5 | 3911.0 | 9334 | E28 file→GPU ~477; R42 construct/adopt ~140 |
| UNET exact copy | 624.7 (warm) | (broad 2719.7 cold) | — | E24 prep ~2819 hidden |
| sampling | 3727.4 | 3713.4 | — | ~3700 |

Note: this run’s CLIP numbers are higher than R44D’s partly because the outer/inner boundaries are now measured separately and CPU contention differs (process_cpu 14.5 s during encode); do not overclaim from one request.

### ASCII Gantt (measured, █, origin = CLIPLoader node start; 1 char ≈ 156 ms)

```text
scale: 1 char = 156 ms | axis 17.2 s | origin = t4_clip_load_start
CLIP descriptor          █                                                                                                   27.5 ms @0
CLIP FastSafe copy       ████████████▋                                                                                     1934.7 ms @42
CLIP construct(served)               ██████████████████▊                                                                   2670.9 ms @2148
prep armed@fwdstart                                  ▌                                                                        0 ms @4826
load_models_gpu(CLIP)                                ███████████████▎                                                      2283.6 ms @4900
CLIP inner forward                                                  ██████████████▏                                        2329.7 ms @7184
UNET entry..join                                                                █▍                                          75.3 ms @9578
UNET gate                                                                         █                                         1.9 ms @9653
UNET FastSafe copy                                                                ████                                      624.7 ms @9655
UNET adopt                                                                            █▌                                   117.1 ms @10280
sampling                                                                                  ████████████████████████▍       3727.4 ms @11924
VAE decode                                                                                                            ███  494.3 ms @16302
output persist                                                                                                           ██▎ 363.5 ms @16796
```

True overlaps shown: UNET source prep ran 4826→9515 (under `load_models_gpu(CLIP)` + inner forward rows, 97.15 % overlap); UNET GPU phase strictly after CLIP forward end (D15 clean).

## J. Raw evidence appendix (foundational facts — full payloads in the companion raw log)

- SHA expected == actual == `20b10e1f99831bc758d9df82f43ce0beb1cbc636a740d11a29eb2bffe90e5260`; backend_exit_code 0; reasons [].
- Generation: `skipped_generation_match/exact_match`, reload invoked 0 (runtime state AND models).
- Loader selection: clip/unet requested==effective==observed FastSafe arms, fallback_attempted false ×3; RuntimeStatus NOMINAL, reasons []; canonical ledger ok, zero_gap true.
- Conditioning: forced miss path intact (decision miss_not_stored, encode_calls 1, persist 0); clean-lane ordering sorted; no forbidden overlap.
- Key payload excerpts (verbatim): see raw log §§G–K — clip_fast_load_start/end, unet_source_prep_armed/joined, unet_fastsafe_pipeline, cpu_owner records incl. CUDA deltas, UNET H2D row, clean-lane ordering, t4–t8 keys, waterfall stages, clock anchor.

Local verification: **168 passed / 0 failed** across the seven focused suites (incl. NEW `tests/test_r44e_evidence_durability.py`: dual-emission same-payload, no duplicate emission when sinks coincide, lazy active-trace resolution, identity-set-alone does not arm, forward-start arms with trigger proof, no arm during transport/pre-forward, arm acquires no GPU gate, interval-overlap math never double-counts, pipeline payload persists bind mode/counts/copied, summary carries identity). py_compile clean ×6 modules; TOML parse OK; Level-1 dry-run env proof pass; deployment attempt 1 valid (no failed preflight this batch).

---

## 22. Decision for NEXT batch — ONE target

**Largest proven avoidable bottleneck: CLIP second materialization.**
Measured chain: FastSafe delivers 8.045 GB to CUDA in 1934.7 ms → construction binds them only transiently (`bind_mode=COPY_CUDA`, 8/8 sampled mismatch) → owners pin the served copy → `load_models_gpu(CLIP)` allocates another model-sized 8.10 GB in 2283.6 ms → 16.15 GB resident before forward. UNET proves the fix pattern works on this stack (assign=True ⇒ 453/453 same-storage, copied 0, adopt 112 ms).

**Recommendation: CLIP zero-copy/construction redesign — make the served-dict seam bind same-storage (assign-style) so `load_models_gpu(CLIP)` becomes bookkeeping. Expected saving ≥2.28 s of device work and ~8 GB VRAM; secondary effect: makes the remaining 1934.7 ms transport (4.16 GB/s vs UNET’s 19.7 GB/s warm) the next retune candidate.**

Not recommended now: CLIP transport retune (copy is not the dominant term), UNET work (node already 819 ms, 453/453), scheduling/platform (out of scope).

## 24. Final verdict fields

```text
R44E_R44D_EVIDENCE_EXHAUSTIVELY_RECONCILED = YES
R44E_EXISTING_DATA_NOT_DISCARDED = YES
R44E_GENUINELY_MISSING_METRICS_IDENTIFIED = YES
R44E_DURABLE_FASTSAFE_EVENTS = YES

R44E_CLIP_NODE_MS = 4825.536
R44E_CLIP_FASTSAFE_COPY_MS = 1934.712
R44E_CLIP_CONSTRUCTION_MS = 2670.544
R44E_CLIP_BIND_MODE = COPY_CUDA
R44E_CLIP_LOAD_MODELS_GPU_MS = 2283.612
R44E_CLIP_INNER_FORWARD_MS = 2330.498
R44E_CLIP_OUTER_ENCODE_MS = 4689.879
R44E_CLIP_NODE_RESIDUAL_MS = 10.119

R44E_UNET_NODE_MS = 819.495
R44E_UNET_PREP_MS = 4827.587
R44E_UNET_PREP_OVERLAP_MS = 4689.870
R44E_UNET_BROAD_H2D_MS = 741.786
R44E_UNET_FASTSAFE_COPY_MS = 624.677
R44E_UNET_STORAGE_MATCH = 453/453
R44E_UNET_CONSTRUCTION_BIND_VERIFY_MS = 111.888
R44E_UNET_NODE_RESIDUAL_MS = 2.320

R44E_GENERATION_MATCH = YES
R44E_EXACT_SHA = YES
R44E_RUNTIME_STATUS_NOMINAL = YES
R44E_GATE_VALID = YES
R44E_ONE_COLD_GATE_COMPLETE = YES
R44E_NEXT_SINGLE_TARGET = CLIP second materialization in load_models_gpu (same-storage bind of served CUDA tensors; saves ~2.28 s device work + ~8 GB VRAM)
R44E_READY_FOR_TARGETED_OPTIMIZATION = YES
```

— R44E, stopped after the single cold gate. No tuning performed; controls remain frozen for the next batch.
