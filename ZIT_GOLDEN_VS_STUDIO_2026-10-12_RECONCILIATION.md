# ZIT Golden (v2ctl) vs Studio — Full ms Reconciliation — 2026-10-12

## 1. Identity / artifacts (proof)

| Item | Golden — v2ctl 8.23s outer | Studio — ~14.64s COMMAND→RESPONSE | Δ / note |
|---|---|---|---|
| Log window | Oct 12 12:00:24.455 → 12:00:32.686 | Oct 12 12:06:31.600 → 12:06:48.104 | different runs, ~6min apart |
| Request ID | `golden-p1-0-982c707f7736` | `7f5f1379-2ca5-45f6-b49c-f2b0f98292af` | — |
| Manifest | `.v2ctl/runs/run_20261012-120048_1ec658d7.json` | n/a (generic `studio_workflow_run.py`) | studio has no v2ctl artifact |
| Attempt / summary | `artifacts/phase_p1_parallel_golden_v1/cohort_2026-10-12_16-52-14_313c16/attempt_0.json`, `summary.json` | remote log + `V2 COLD WATERFALL` + `V2 REMOTE GANTT` | — |
| Deploy | `bebe107d…` v99, app `batch-c0-p8-h100`, `golden_p1_parallel_c0_p8_h100` | combined hash `d25236f022e8fd78` | same family, different invocation |
| Workflow | `e44389ea…`, 60 nodes, `run_golden_parallel_stream` | `20d41d72…`, 44 reachable / 44 static | **different graph — contaminated comparison** |
| Output SHA | observed `3a6a0306…`, `output_sha_match=true`; log warns `expected=790c3052… observed=3a6a0306…` | not recorded | proves different revisions |
| GPU | H100, `comfy_kitchen`, `clip bf16` | H100 80GB HBM3, CUDA 13.0, torch 2.14.1+cu130 | same class |

> `attempt_0.json duration_ms=499783.916` / `backend.elapsed_seconds=501.36` = Modal queue, not execution. True execution = `outer_wall_ms=8231.075`.

Boundary authority: Golden geometry `modal_app.py:1871,1929-2071`; stages `golden_serial.py:10291,12558,13672,14706,15408,16146,16383,16929`; markers `golden_parallel.py:118-134,388-601`; transport `golden_model_transport.py:1277-1341,1501-1570,1902-1935` emitted `golden_serial.py:12753-12824,14997-15049`; outer `golden_parallel.py:271-309`, `modal_app.py:23494-23518`. Studio Gantt `gantt_telemetry.py:552-582,721-755`; executor `runtime_executor.py:2232-2414`; pre-sampler `modal_app.py:17660-18098`; critical path `modal_app.py:295-383`; cpu_owner `runtime_executor.py:1891-2087`; generic loaders/ticket `golden_generic_loaders.py:2482-2494,2812-2869,3128-3130`; sampler boundary `runtime_executor.py:4582-4740,4948-5238`; waterfall `v2_waterfall.py:1025-1080,1328-1350,1588-1665`.

## 2. End-to-end (critical-path basis)

| Component | Golden (ms) | Studio (ms) | Δ Studio−Golden (ms) |
|---|---|---|---|
| External / Python restore | 1166.678 (adapter boundary, outside span) | 1163.794 + 42.117 restore→method | −2.884 restore itself (noise); +42.117 dispatch gap |
| Method setup to graph | ~22 (restore-obs 17.394 + setup 1.824 + gaps) | 2000.414 (entry→graph 1499.04: graph_setup 501.438 + cert 164.151/vol-reload 163.586 + validation 119.944 + pregraph 112.853) | **+~3020** |
| PromptExecutor / cache setup | 0 (fixed 60-node plan, hash check bypassed) | 2232.614 (exec→cached 1194.418: signature_keys 1192.132; cached→first 1037.814: topo_walk 1035.344 = input_info 181.282 + other 854.062; cache hit=0) | **+2232.614** |
| Golden call wall / Studio setup subtotal | call wall 8160.456 (span 8096.154 + pre 20.735 + post 43.568) | setup subtotal 5439 (1164+42+2000+2233) | — |
| Outer / COMMAND→RESPONSE | **8231.075** (call + 70.619 seam) | **14642** (remote window 15522) | **+6410.925** |

## 3. Model IO — transport (byte-exact proof)

| Component | Golden (ms) | Studio (ms) | Δ Studio−Golden (ms) |
|---|---|---|---|
| CLIP source read (8044936192 B) | 1243.643 @ 6.468848 Gbps (8044936192/1.243642766 ✓) | 1549.564 @ 5.191743 Gbps (8044936192/1.549563675 ✓) | **+305.921** storage variance, same file |
| CLIP gpu_ready / total_load | 1285.295 / 1291.450 | 1567.671 / 1575.164 | +282.376 / +283.714 |
| CLIP load wall | 1353.070 (read 1318.144 + skeleton 0.481 + bind 10.638 + adoption 16.344 + proof 2.307 + residual 15.515; layout_resolve 31.795; arena created, cache miss) | 1735.756 (`generic_attempt_walls`; + fp8_dequant 3.0 + `load_models_gpu CLIP 83.326`) | **+382.686** (= +305.921 IO + 83.326 GPU-load + 3.0 − ~9.6 noise) |
| UNET source read (12309817472 B) | 2260.526 @ 5.445554 Gbps (12309817472/2.260526286 ✓), gpu_ready 2271.088, total 2278.323, arena reused, layout hit | 2107.017 @ 5.842297 Gbps (12309817472/2.107016857 ✓), gpu_ready 2349.400, total 2410.546 via `unet_ticket_launched` hidden behind CLIP encode | −153.509 source (studio faster) / +78.312 tail |
| UNET load wall counted | 2301.800 (stage-sum, overlapped with forward) | 61.475 critical path (background 2410.546 overlapped) | **−2240.325 on paper, ~0 real** — accounting illusion |
| Overlap proof | window 1376.845→3680.766 = 2303.921; 2301.800+2028.220−2303.921 = **2026.099 overlapped** | CLIP encode 7.625→9.751s overlaps UNET ticket `2903088ns`; critical UNET only 61ms | both overlap; golden counts it in sum, studio hides it in Gantt |

## 4. Encode / forward / sampling / decode / output

| Component | Golden (ms) | Studio (ms) | Δ Studio−Golden (ms) |
|---|---|---|---|
| CLIP forward / CLIPTextEncode | 2028.220 | 2129.639 (`CLIP.encode_from_tokens 2115.944`) | **+101.419** |
| Sampler prep / node→sampling gap | 25.619 prepare | 1274 gap (lane 0.366 + aura 3.7 + CacheDiT 0.8 + Sage 0.7 + LGNoise 0.5 + `load_models_gpu 74.537` + ~1193 dispatch residual) | **+1248** |
| Sampling | 3659.600 total (sampler_total 3625.704 + residual 33.897 ✓) | 2549 partial; node total 4694 (= 1274+2549+871.115 ✓); Gantt 4658 | **+~999 node-total** (denoise loop only +112: golden 29.017→31.85s = 2.833s @2.39it/s vs studio 41.148→44.093s = 2.945s @2.23it/s; rest = `kitchen_attention 340 calls` + wrapper) |
| Post-sampling transition / tail | 0.026 tail (VAE 437.248 hidden: 3659.600+437.248−3661.664 = 435.184 overlapped) | 871.115 transition (+ `load_models_gpu 39.928`) | **+871** |
| VAE decode | 492.294 | 676.207 (Gantt 14.529→15.205s ✓) | **+183.913** |
| Output | 243.157 single encode | 588.730 sum (PNG 315.743 + descriptor 272.988; Production 315.531 + comparer 235.373) / ~316 span (15.206→15.522s) | **+~73 span / +346 sum** — use span for wall, sum for work |
| Teardown / post | teardown 0.625 + persist 17.888 (18.111 by markers) + seam 70.619 | cert commit 1266.367 deferred post-response (excluded) | n/a |

## 5. Overlap closure (math correction)

| Check | Golden (ms) | Studio (ms) | Δ / note |
|---|---|---|---|
| Stage/node sum | 10543.580 (0.172+1.741+1353.070+2301.800+2028.220+25.619+3659.600+437.248+0.026+492.294+243.157+0.625 = 10543.572 + 0.008 rounding ✓) | sampler node 4694 = 1274+2549+871.115 ✓; output 315.743+272.988 = 588.731 ✓ | prior “missing ~835ms” was the transition term; prior output double-count fixed |
| Span | 8096.154 | 15522 remote (1164+42+2000+2233+4396+4694+676+316 = 15521 ✓, 1ms rounding) | using output span; sum-basis gives 15794 (+272 descriptor double-count) |
| Sum − span | 2447.426 = measured overlap 2461.283 (2026.099 + 435.184) − 13.857 intra-span gaps (1.020 + 0.035 + persist gaps) | — | “~2447ms overlap” without the 13.857ms gap term was incomplete |
| Call/outer | 8096.154+20.735+43.568 = 8160.457 ≈ 8160.456 ✓; 8231.075−8160.456 = 70.619 seam ✓ | 14642 COMMAND→RESPONSE; 15522−14642 = 880 scheduling/receipt | — |

## 6. Conclusion

| Cause | ms | Share of +6411 |
|---|---|---|
| Method/cert/graph setup Golden skips | ~+3020 | ~47% |
| PromptExecutor/signature/topo Golden skips | +2233 | ~35% |
| Sampler-dispatch gap (25ms → 1274ms) | +1248 | ~19% |
| Sampling wrapper (only 112 denoise) | +~999 | ~16% |
| Post-sampling transition | +871 | ~14% |
| CLIP IO storage variance (byte-exact) | +306 | ~5% |
| VAE decode | +184 | ~3% |
| Output span (sum +346) | +~73 | ~1% |
| UNET accounting illusion | −2240 on paper | offsets the naive sum back to +6411 ✓ |

Shares exceed 100% before the UNET accounting offset — that is the closure check. Same ZIT models, different workload revisions; do not treat as apples-to-apples.

## 7. Implementation status (2026-10-12 session)

- **#1 versioned static plan cache — implemented, locally verified.**
  `prompt_signature_cache.py`: `is_link_value`, `structure_fingerprint`, `static_identity`, `apply_memo_partial` (ancestor-aware partial reuse; full-hit path untouched). `runtime_executor.py`: `_static_store_key`, write-back `skip`, patch tries static-partial → legacy-full fallback → original compute; `key_hash` overridden to static so topo-lazy co-locates. Tests: `tests/test_v2_prompt_signature_cache.py` 51 passed (12 new: stability, topology sensitivity, completeness, full/partial reuse, ancestor poisoning, mid-graph change, fail-closed, non-requested ancestors, pre-computed keys).
- **#2 early CLIP fetch — implemented, locally verified (join needs live run).**
  `golden_serial.py`: `_adapt_m2_loaded` extracted (sync path byte-identical), `_join_generic_clip_ticket` awaits the ticket and adapts with the exact adapter (canonical runs untouched — attribute never set). `golden_generic_loaders.py`: `_match_clip_ticket`, `_overlap_launch_clip_load` (gated: eligible plan, clip spec, complete deployment identity, loop, transport; same async `transport.load(role="clip")` vehicle as the UNET ticket; UNET still launches after CLIP dispatch so generations stay sequential), install-time launch + trace, dispatch join, stage `clip_ticket` kwarg + session attach (single-path only), teardown cancel. `modal_app.py`: passes `plan.deployment_identity` through. Kill switch: existing overlap switch (ineligible plan → no ticket). Tests: `tests/test_golden_generic_substitution.py` 80 passed (8 new). The in-`golden_serial` await path requires torch/CUDA — covered by a live validation run, not unit tests.
- **Verification notes.** Canonical `tools/test_perf.py` wrapper crashes in this checkout with an access violation inside ComfyUI's custom-node archive scan (`comfyapp.py:8523 collect_semantic_files` ← repo-root `__init__.py:8458`, triggered by pytest's default import mode + `tests/__init__.py` + `pythonpath=.`); pre-existing, unrelated to this diff. Tests above ran via `rtk pytest --import-mode=importlib` (bypasses the repo-root entry import): memo 51 passed, substitution 80 passed, `test_v2_e26_concrete_cold_wins.py` 22 passed.
- **Next (needs live evidence, not done here).** #3 residual attribution (854ms topo + ~1193ms dispatch) needs a profile run (`v2ctl golden profile`); #4 VAE overlap + #2 join-path proof need one isolated `golden run` on an experimental app per `comfymodal-golden-ops` (single request, structural classification, no production app).

## 9. Finish-all session (code-complete, live proof pending user runs)

## 10. 21:52 Studio run reconciliation (request f17b7bcf, Testing 6)

Proven live: both ticket launchers are deployed and firing (`clip_ticket_launched` at install/pregraph, `vae_ticket_launched` at sampler dispatch), the signature memo served a full hit (`exec_to_cached 25ms` vs 1194ms cold, `is_changed` absent so the original computation never ran, `topo_lazy_hits=41`), and the topo probe renders (`c2f_topo_walk_max_ms=0.545` vs sum `0.723` — ratio 0.75, so nesting double-count is small and the noon 854ms remainder was real cold-discovery cost now skipped by lazy replay, not an accounting artifact).
Two corrections from this run:
1. Static-vs-legacy key kind is still unresolved from logs: the new `key_kind`/`partial`/`reused` state fields were never added to the breakdown renderer, so the next run could not name the key type. Added now (renderer tuples, telemetry-only). The hit on a never-before-seen prompt hash still favors static keys, pending the explicit field.
2. Neither ticket was consumed (CLIP wall 2180ms ≈ full sync read; VAE 370ms; no join prints). Two distinct causes:
   - CLIP: #1's success starved #2's overlap window — install-to-dispatch was 42ms because executor setup collapsed to 27ms, so joining only awaited the same 2s read. The ticket is pure overhead on memo-hit runs and keeps its full value on memo-miss (cold) runs. A method-entry launch point could restore ~1.2s on warm runs; deferred pending evidence it matters.
   - VAE: this workflow dispatches VAE *before* the sampler, so the sampler trigger fires after the consumption point (pure waste, teardown-cancelled). Fixed with two guards: launch is refused while a UNET transport generation is still running (`transport_busy_unet_inflight` — the shared transport serves one generation at a time, so clip-chaining was rejected as unsafe), and the sampler trigger skips when the VAE node already dispatched (`vae_already_dispatched`). Late-VAE workflows keep the original behavior.
Suites: 180/180 green (memo 51, substitution 89+10 new VAE-gate tests, e26 22, durability 16+3).- **#4 dependency-gated VAE overlap — implemented, locally verified.**
  All in `golden_generic_loaders.py` (zero `golden_serial`/`modal_app` changes): `_match_vae_ticket`, `_overlap_launch_vae_load` (same async `transport.load(path)` vehicle the stage itself calls — no role override, so a joined result is telemetry-identical), `_overlap_maybe_launch_vae_on_dispatch` trigger on sampler dispatch, `overlap_vae_spec` at install (live workflow inputs, so dynamic filenames are never speculated), ticket threading through `_run_substituted_loader` → `_substitute_unet_vae_loader(vae_ticket=)` → `compose_generic_vae_load(vae_ticket=)` which awaits and feeds the stage's existing `preloaded_transport` contract (branch agreement enforced with the stage's own `_golden_model_transport_enabled` + `_session_source_policy` predicates on the same session), teardown cancel. Kill switch: existing overlap switch. Tests: 9 new in `test_golden_generic_substitution.py`.
- **#3 safe half — implemented.** `c2f_topo_walk_max_ms` (max single `add_node` wall) now tracks next to the accumulating sum and renders in the breakdown line, so the next Studio run directly shows whether the 854ms remainder is nesting double-count (max ≪ sum) or real walk cost. No behavior change — telemetry only. Sampler-dispatch cleanup stays gated on the deep-trace split from the live profile (deliberately not cut blind).
- **Verification (this session).** `rtk pytest --import-mode=importlib`: substitution 89, memo 51, e26 22 — **161 passed, 0 failed**. (Canonical wrapper AV note in §7 still applies.)
- **Awaiting user runs.** When you post the completed v2ctl + Studio runs, read off: `c2f_topo_walk_max_ms` vs `c2f_topo_walk_ms`, `signature_cache_*` (static hits + `*_reused`/`*_partial`), `clip_ticket_launched/consumed` + CLIP wall, `vae_ticket_launched/consumed` + VAE wall, sampler wrapper split. Then: fix topo accounting if max ≪ sum, cut only probe-proven dispatch fat, and confirm/refine the savings ledger.
- **Workspace correction (same day).** The noon baselines ran on Legacy (`ws_32ea683e1b7c`, receipt_99). Legacy is now out of credits: the lane moved to **Testing 6** (`ws_175a616152c5`) — first by another lane's 13:51/14:15 deploys (receipts 1–2, dirty/unverified; the 14:19–14:21 failures ran on receipt_2), now adopted as our lane too. A mistaken revert to Legacy was immediately undone. Legacy receipts remain valid historical evidence only; all future deploys/runs target Testing 6.
- **Validation-run incident + fix (same day).** A fresh parallel run on Testing-6 receipt_2 (`golden-p1-0-573750ddaa2b`, cohort `...20-04-32_c45198`) executed correctly — exact SHA `3a6a0306…`, 3083864 bytes — but the harness marked it invalid: `output durability evidence invoked or claimed in off mode`. Root cause: the other lane's bytes-transport feature (default `COMFYMODAL_GOLDEN_RESULT_TRANSPORT=bytes`) records a `byte_sidecar` wire receipt that the off-mode validator classified as durability evidence — the harness flagging its own receipt. Fixed harness-side with zero remote impact: `byte_sidecar` family excluded from the durability classifier (`tools/v2_control/validation.py`) and from the event-claim visitor (`tools/benchmark_v2_direct.py`); `scan["sidecar"]` is consumed only by that gate, so nothing else changes. Proven by re-running the backend's exact scan+validate path over the failed cohort's artifacts: `valid=True`, no failures, SHA match — no GPU spent. Tests: 3 new in `test_ra7b_output_durability_validation.py` (16 passed); real markers (commit/reopen/fsync/asset_write) still fail the gate as before.

## 8. Residual attribution — static half (no GPU needed)

### 8a. 854ms topo remainder (`topo_walk 1035.344 − input_info 181.282`)

What the number IS: `opt_exec_topo_walk_ms` accumulates (`+=`) every `TopologicalSort.add_node` call (`runtime_executor.py:3383`), including nested ones — `add_node` fans out per link through `add_strong_link → add_node` (`comfy_execution/graph.py:142,175-176`). It is a nested SUM, not a critical-path union: an upper bound that double-counts shared subgraphs across the 3 output walks (nodes 107, 9, 935:931) and nested link calls (guarded cheap by `pendingNodes`, `graph.py:154`, but still accumulated). Part of the 854ms may be accounting, not work.
Narrowed suspects (all inside the timed region):
1. Repeated full-graph walks — one per output node; walks 2–3 mostly guard-hit but still summed (`runtime_executor.py:3367-3408`).
2. `get_input_info`-adjacent work outside the 181ms sub-split: `NODE_CLASS_MAPPINGS` lookups, `dynprompt.get_node`, exception paths (`graph.py:125-128`).
3. Synchronous `_persist_topo_lazy` (file write + fsync) firing INSIDE the first top-level walk (`runtime_executor.py:3400-3406`) — ~10–50ms, one-off.
4. Loader `INPUT_TYPES()` folder scans that escape the lazy replay (anything not covered by `topo_lazy`, `runtime_executor.py:3546-3665`).
Live probes that close it (one run): read `opt_exec_topo_nodes` (call count), per-call max vs sum (add max-tracking next to the `+=`), and the pendingNodes guard-hit rate. If max ≪ sum, the remainder is double-count — fix the accounting (union), not the walk.

### 8b. ~1193ms sampler-dispatch residual

What the number IS: `sampling_end` (`runtime_executor.py:5203-5225`, explicitly `UNATTRIBUTED` residual) through lane release + VAE activation (`:5320-5351`), plus wrapper setup/lane acquire (`:4892-4920`, `:5158-5182`). Measured inside: `load_models_gpu other 74.537ms`; todo the rest.
Narrowed suspects:
1. Deep-profile finalization after `sampling_end` before lane release (`runtime_executor.py:5265-5351`) — inspect first.
2. VAE CPU-page prefetch scheduling + readiness slack, explicitly non-mutating (`runtime_executor.py:5003-5031`, gates `:4911-4918,5120-5133,5332-5349`).
3. Backend callable resolution + kitchen scope apply/restore per sampler invocation (`golden_generic_loaders.py:2552-2593`).
4. Redundant readiness/diagnostic checks around lane acquisition (`runtime_executor.py:4892-4897`).
Live probes: deep-trace span split of wrapper-setup vs post-`sampling_end` finalization; diagnostics-off A/B (variance/diagnostics flags) to separate required sync from observability overhead. Cleanup rule stays: remove only what the probes prove redundant — dispatch semantics, scoped ownership, and required VAE readiness are inherent.
