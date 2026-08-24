# R44E — Exhaustive R44D Existing-Evidence Inventory (pre-implementation, HARD GATE)

Batch: R44E · Worktree `../comfyui-modal-r42` · Branch `r42-golden-reconciliation` · HEAD `0c59f46e3238f421378e8852ebc548da815b70af`
Written BEFORE any R44E code change. Every value below was read directly from a persisted artifact in this session (not from any prior summary).

Artifacts exhaustively mined:
- `R44D_FASTSAFE_ACTIVATION_COLD_GATE_REPORT.md`, `R44D_FASTSAFE_ACTIVATION_COLD_GATE_RAW_LOG.txt` (full read)
- `R44D_GATE_CONSOLE_LOG.txt`, `R44D_DEPLOY_CONSOLE_LOG.txt` (full read)
- `.v2ctl/gates/gate_20260824-010534_194ee7dc.json` (gate_valid=true, reasons=[], SHA match verified)
- `.v2ctl/deployments/deploy_20260823-200344_7fc24208.json` (fingerprint `7fc24208…e2c24f`)
- Run dir `C:\...\ComfyUI\comfymodal-data\benchmarks\runs\v2_2026-08-24_01-04-43\`: `run_0.json` (incl. trace rows + cpu_owner_records + active_read_records + canonical_ledger), `run_001_sample.json` (waterfall stages, t4–t8, structured report), `summary.json` (full), `campaign_manifest.json` (full), `run_001_sample.json.v2ctl-provenance.json`
- `R44A/R44B/R44C` reports + performance-history handoff (context)
- Keyword sweeps across all of the above for: `clip_fast_load`, `unet_fastsafe_pipeline`, `request_fastpath_begin/end`, `unet_request_ordering`, `bind_mode`, `storage_identity`, `same_storage`, `prepare_join`, `fadvise`, `readinto`, `page_cache`, `source_prep`, `get_keys`, `get_tensor`, `state_dict`, `descriptor`, `cpu_owner`, `active_read`, `UNET H2D`, `Synchronized H2D`, `H2D end -> UNET ready`, `gantt`, `waterfall`, `prewarm`, `prep`

Clock domains: epoch seconds (`t4_*` keys), mono ns (trace rows / clean-lane ordering). Epoch↔mono anchor from run_0.json: `remote_result_emit_wall_unix_ns=1787533513139986450` ↔ `remote_result_emit_mono_ns=268003115574`.

---

## 3A. Restore / request setup

| Metric | Value | Source artifact | Exact event/key | Persisted? | Confidence |
|---|---:|---|---|---|---|
| restore_total | 1113.273 ms | run_001_sample.json | `timing.restore_total_ms` | YES | high |
| application restore | 1530.895292 ms | run_001_sample.json | waterfall stage `application_restore` | YES | high |
| restore→method entry | 47.548942 ms | run_001_sample.json | waterfall `restore_to_method_entry` | YES | high |
| method/setup | 711.624832 ms | run_001_sample.json | waterfall `remote_method_setup` | YES | high |
| PromptExecutor cache setup | 236.731 ms | run_001_sample.json | waterfall `prompt_executor_cache_setup` | YES | high |
| graph-start timing | restore_return_ns 246533525268; plan_identity_complete_ns 246604724541 (mono ns) | run_0.json | `clean_lane_proof.ordering` | YES | high |
| generation check wall | 399.256 ms (+ models 3.796 ms) | raw log §J | `runtime_state_reload_decision.check_ms` | YES | high |
| generation expected/current | `1e02514e9e1580da5ab8a1002f9e669a` == same | raw log §J | `runtime_state_reload_decision` | YES | high |
| reload yes/no | decision `skipped_generation_match/exact_match`; runtime_state_reload_invoked=0; callback_called=0 | raw log §J | same | YES | high |
| scheduling | modal_scheduling 6170.1 ms (raw-log waterfall) / 4102.771292 ms (run_001 waterfall key) | both sinks | `modal_scheduling` | YES | high (two sink values recorded) |
| command→response | 53179.4 ms (waterfall) / user_equivalent_trigger_to_response_ms=53179.353 (gate manifest) | run_001 + gate json | `command_to_response_ms` | YES | high |
| app wall | 28222.5 ms | summary.json | `wall_ms` | YES | high |
| pre_sampler | 15780.195 ms | summary.json | `pre_sampler_ms` | YES | high |

## 3B. CLIP loader

| Metric | Value | Source artifact | Exact event/key | Persisted? | Confidence |
|---|---:|---|---|---|---|
| CLIPLoader node wall (`t4_clip_load`) | **6462.066 ms** (1787533493.189352→1787533499.651418) | run_001_sample.json | `t4_clip_load_start/end` | YES | high |
| `load_models_gpu role=CLIP` | **1103.880 ms** wall, process_cpu 1290.0 ms, eff_cores 1.169, threads 52→53→52 | run_0.json | `cpu_owner_records[0]` operation=`load_models_gpu` role=`CLIP` | YES | high |
| FastSafe observed arm | clip requested/effective/observed = `fastsafetensors_direct_gpu`, fallback false | run_0.json (raw log §G) | `loader_selection.clip` | YES | high |
| active read (native, VAE lane) | 349.605 ms, 335 304 388 bytes, owner=`graph_loader`, ends 1787533493.0213888 (BEFORE CLIP node start ⇒ NOT the CLIP payload) | run_0.json | `active_read_records[0]` | YES | high |
| source path / size (CLIP) | ABSENT as telemetry (only basename would have been in unpersisted `clip_fast_load_start.paths`) | — | — | NO | — |
| memory allocation during CLIP load | ABSENT (would have been in unpersisted `clip_fast_load_end.cuda_alloc_delta_bytes`) | — | — | NO | — |
| FastSafe physical-copy wall (CLIP) | ABSENT (unpersisted `clip_fast_load_end.file_to_gpu_wall_ms`) | — | — | NO | — |
| descriptor events (CLIP) | ABSENT (never instrumented) | — | — | NO | — |
| safetensors/H2D/owner/bind events (CLIP) | ABSENT from durable sinks (histogram count 0; see raw log §K note) | — | — | NO | — |
| `request_fastpath_begin` | emitted to diagnostics only; string absent from all persisted artifacts | raw log §K | — | NO | certain |

Where the 1103.880 ms sits: `t4_clip_load_end == t5_text_encode_start == 1787533499.651418` exactly, so `load_models_gpu(CLIP)` runs INSIDE the encode window (Comfy calls it on the encode path), i.e. after CLIP node end, before/at raw-encode start — NOT inside the CLIPLoader node window.

## 3C. CLIP encode / forward

| Metric | Value | Source artifact | Exact event/key | Persisted? | Confidence |
|---|---:|---|---|---|---|
| CLIPTextEncode outer wall | 3092.524 ms (cpu_owner) / 3092.656 ms (pre-sampler nodes list) | run_0.json + run_001 | `cpu_owner_records[2]`, `clip_text_encode_nodes[0].duration_ms` | YES | high |
| t5 text-encode window | 3090.935 ms (1787533499.651418→1787533502.7423534) | run_001 | `t5_text_encode_start/end` | YES | high |
| `encode_from_tokens` wall | 3080.853 ms (cpu_owner) / `clip_raw_encode_ms` 3081.092 (pre-sampler) / 3079.49 (structured report) | run_0.json + run_001 | three sinks agree ±1.6 ms | YES | high |
| inner `clip_forward` | **1973.478 ms** (span `clip_forward_end.duration_ms`; GPU row `CLIP forward` 255628861599→257602339399 = 1973.478 ms) | run_0.json | two independent sinks agree exactly | YES | high |
| tokenization/input prep | derived residual only (see below); no dedicated event | — | — | DERIVED | medium |
| allocated/reserved before→after forward | alloc 16146645504→16180199936 (Δ+33 554 432 B = +33.5 MB); reserved 16150167552→16389242880 (Δ+239 075 328 B) | raw log §J | `clip_forward_end.cuda_*` | YES | high |
| CPU time / threads in forward | thread_cpu 1020 ms, process_cpu 1300 ms, faults 0, cuda_no_sync=true | raw log §J | `clip_forward_end` | YES | high |
| conditioning proof | lookup bypassed hit=false miss_count=1; decision `miss_not_stored` encode_calls=1 persisted_count=0 | raw log §J | `clip_conditioning_cache_lookup/decision` | YES | high |
| clean-lane ordering | restore 246.53→identity 246.60→forward_start 255.629144461→forward_end 257.601371750 (mono ns, sorted) | raw log §J | `clean_lane_proof.ordering` | YES | high |

**Mathematical reconciliation (required by batch §3C):**
`load_models_gpu(CLIP) + inner_forward = 1103.880 + 1973.478 = 3077.358 ms`
`encode_from_tokens = 3080.853 ms` ⇒ **residual = 3.495 ms (0.11%)** ⇒ the hypothesis
`load_models_gpu + inner_forward ≈ encode_from_tokens` is CONFIRMED.
The “~3.08 s forward” framing is wrong: forward compute is 1.973 s; device-prep is 1.104 s; ~3.5 ms is tokenize/other.
Node-level: CLIPTextEncode 3092.524 − encode_from_tokens 3080.853 = 11.671 ms node-wrapper overhead.

## 3D. UNET

| Metric | Value | Source artifact | Exact event/key | Persisted? | Confidence |
|---|---:|---|---|---|---|
| UNETLoader node wall (`t4b_unet_load`) | **3910.982 ms** (1787533502.802215→1787533506.7131968) | run_001 | `t4b_unet_load_start/end` | YES | high |
| **Broad UNET H2D** | **2719.655 ms** (start_mono_ns 258856247904 → end_mono_ns 261575903066, lane GPU) | run_0.json trace rows | `"name": "UNET H2D"` | YES | high |
| what broad H2D includes | unet_transfer_start→unet_transfer_end window = FastSafe copy_files_to_device + get_keys/get_tensor instantiate + adoption bind (per `_run_gpu_phase` structure) | code `_run_gpu_phase` | interval semantics | YES (structural) | high |
| exact FastSafe `copy_files_to_device` wall | MEASURED AT RUNTIME but NOT persisted: `metrics["fastsafe_file_gpu_wall_ms"]` (unet_fastsafetensors.py:907) was carried in `timings["fastsafe_metrics"]` and dropped by `_publish_success_telemetry` | code + absent-from-artifacts | `unet_fastsafe_pipeline` (absent) | NO (runtime-only) | certain |
| `load_models_gpu role=other` ×2 | 42.608 ms and 71.862 ms | run_0.json | `cpu_owner_records[3],[4]` | YES | high |
| FastSafe observed arm (UNET) | requested/effective/observed = `fastsafetensors`, fallback false | run_0.json | `loader_selection.unet` | YES | high |
| model-detection/native-load timing | ABSENT (inside unpersisted adopt metrics) | — | — | NO | — |
| prewarm event | none persisted (`active_profile_prepare=0.0`, count 0) | run_001 | `active_profile_prepare*` | YES (zero) | high |
| storage identity counts | ABSENT (unpersisted) | — | — | NO | — |
| CUDA allocation change (UNET) | ABSENT | — | — | NO | — |

Epoch↔mono reconciliation inside the UNET node: node entry ≈ mono 257 665 143 124 (via anchor) → transfer-window start 258 856 247 904 ⇒ **≈1191 ms of node time precedes the H2D window** (prep-arm + prep-join + D15 gate); transfer window 2719.655 ms; total ≈3911 ms ✓ consistent with the node wall.

## 3E. UNET source preparation

| Metric | Value | Source artifact | Exact event/key | Persisted? | Confidence |
|---|---:|---|---|---|---|
| prep armed | at UNETLoader entry only (R44D report §7.1; structural) | report + code | `arm_unet_source_prep` sole call site request_unet_fastsafe.py:472 | YES (structural) | high |
| overlap with CLIP forward | **0 ms** — PROVEN from timestamps: forward_end mono 257 601 371 750 < UNET node entry ≈257 665 143 124 < prep arm; sequential graph order CLIPLoader→CLIPTextEncode→UNETLoader | run_0.json rows + t-keys | derived | YES | high |
| did prep begin earlier but go unmeasured? | **NO.** Code proof: `FastPathRequestContext.mark_clip_forward_start()` (request_fastpath.py:290-294) records t0 ONLY — it contains NO arming call. The R44B report’s claim “forward-start arms UNET source prep” was never implemented. The only arm site is inside the UNET wrapper. Also `plan_time_unet_source_h2d` appears once in `clean_lane_proof.forbidden_activity_attempts` at 246604735223 (plan-identity instant) — an observational clean-lane record of a plan-time prefetch attempt, not the request prep (which did not exist yet); clean-lane records don’t block, and no prep reader ran then (no prewarm events, `active_profile_prepare_count=0`). | code + run_0.json | — | YES | high |
| prep threads/chunk resolved remotely | 4 threads / 8 MiB (env truth) | raw log §H | `COMFYMODAL_V2_CHECKPOINT_PREWARM_THREADS/CHUNK_MB` | YES | high |
| prep bytes/read-count/join wall | ABSENT (CheckpointPrewarmer tracks them via `as_dict()` but nothing persisted them) | code checkpoint_prewarm.py:812 | — | NO | — |

Conclusion for §3E: case **A** (prep really did not begin until UNETLoader) is proven by code structure AND timestamps; there is no hidden earlier prep.

## 3F. Sampling / VAE / output

| Metric | Value | Source artifact | Exact event/key | Persisted? | Confidence |
|---|---:|---|---|---|---|
| sampler-node→sampling | 1432.444025 ms | run_001 | waterfall `sampler_node_to_sampling` | YES | high |
| sampling | 3713.402368 ms (t6 1787533508.2075493→1787533511.9209518 = 3713.4025 ✓) | run_001 | `sampling`, `t6_sampler_*` | YES | high |
| post-sampling transition | 382.212472 ms | run_001 | waterfall | YES | high |
| VAE load (native) | 519.0 ms (t4c 1787533492.6676333→1787533493.1867633 = 519.13) | run_001 | `t4c_vae_load_*` | YES | high |
| VAE decode | 502.387295 ms (GPU row agrees: 267166293158→267668680453) | run_001 + run_0 | `vae_decode_ms`, GPU row | YES | high |
| PNG/output encode | 273.878 ms (GPU row `output encode`); t8c 273.878 ✓ | run_0 + run_001 | `output_encode` | YES | high |
| output persistence | 334.016547 ms (t8bb 7.637 ms persist + collect) | run_001 | waterfall `output_persistence`, `t8bb_*` | YES | high |
| output_collection | 9.857 ms | summary.json | `output_collection_ms` | YES | high |

---

## 4. Evidence classification

### DATA_ALREADY_PRESENT_AND_USABLE (prior summaries under-surfaced)
1. `load_models_gpu role=CLIP` = 1103.880 ms (+CPU/threads) — run_0.json cpu_owner_records.
2. `encode_from_tokens` = 3080.853 ms vs inner forward 1973.478 ms vs node 3092.524 ms — decomposition identity CLOSES with 3.5 ms residual (see 3C).
3. **Broad UNET H2D = 2719.655 ms with exact mono start/end** — run_0.json trace rows (the R44D Gantt row was derived from THIS).
4. CPU ownership records for all five wrapped ops incl. two `load_models_gpu[other]`.
5. CUDA alloc/reserved deltas across CLIP forward (+33.5 MB / +239 MB).
6. Full t4–t8 epoch stage table; waterfall stage map; gantt rows; canonical ledger event list; clean-lane ordering stamps; active_read record proving the only native graph-loader read (335 MB) is the VAE, not CLIP/UNET.
7. Inside-UNET-node phase split: ≈1191 ms pre-transfer vs 2719.655 ms transfer window (derived via epoch↔mono anchor).
8. Remote env truth for every knob (threads/blocks/bbuf/prewarm).

### DATA_PRESENT_BUT_TOO_BROAD
1. **UNET H2D 2719.655 ms** = transfer WINDOW: includes FastSafe copy + get_keys/get_tensor instantiate + adoption bind. Narrower boundary needed: exact `copy_files_to_device` wall — ALREADY MEASURED at runtime (`fastsafe_file_gpu_wall_ms`) but dropped before persistence.
2. **CLIPLoader node 6462.066 ms** = transport + served-dict construction combined; sub-boundaries not split anywhere.
3. `modal_scheduling`: 6170.1 (raw-log waterfall) vs 4102.771 (run_001 key) — two sink definitions preserved, both cited.

### DATA_GENUINELY_MISSING (drives R44E instrumentation)
1. CLIP exact FastSafe `copy_files_to_device` wall (+ setup/get_keys/get_tensor-loop splits) — never measured (wiring `_fastsafe_load` has no timing).
2. CLIP descriptor wall + header-parse + cache-hit flag — never measured.
3. CLIP bind_mode + sampled same/non-same-storage counts — computed at runtime (`_storage_bind_mode`) but discarded beyond the mode string and never persisted.
4. CLIP served-dict seam counters (native-reader shadow hits / pass-throughs / duplicate physical reads) — never counted.
5. CLIP CUDA alloc/reserved at the four closure points (before FastSafe / after FastSafe / after construction / before forward) — never captured.
6. UNET persistence of already-measured walls (setup/copy/instantiate/adopt/storage-identity/final-validation) — measured, dropped by `_publish_success_telemetry`.
7. All R44B ctx.telemetry events (clip_fast_load_*, unet_fastsafe_pipeline, request_fastpath_begin/end, fallback/ordering) — diagnostics-only, zero durable persistence.
8. Source-prep durable metrics (armed/start/join timestamps, touched bytes, read count, stop reason, overlap derivation) — tracked in memory (`as_dict()`), never emitted.
9. What `load_models_gpu(CLIP)` does physically: no CUDA alloc/reserved delta across it (cpu_owner has wall/CPU/threads only).

---

R44E_EVIDENCE_RECONCILIATION_COMPLETE = YES

Instrumentation added in R44E is restricted to the nine genuinely-missing items above. Nothing already present is re-instrumented or duplicated: existing broad UNET H2D row, cpu_owner records, t4–t8 keys, loader_selection, ledger, and waterfall are consumed as-is.
