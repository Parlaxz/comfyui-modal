# V2 Batch E24 Critical-Path Closure

Request: `v2-benchmark-0-7a3e908f6580`
Artifact: `comfymodal-data/benchmarks/runs/v2_2026-08-18_02-37-17/run_001_sample.json`
Mode: LOCAL READ-ONLY forensics. No runtime changes, no Modal deploy, no remote
requests, no commit.

## 1. Executive result

The 4525.710 ms "unexplained" residual is **not missing wall time**. The
artifact already contains a fully reconciled, non-double-counted waterfall
(`final_reconciled_waterfall`) whose exclusive top-level stages sum to
**16876.006 ms** against the authoritative no-scheduling wall of
**16865.854 ms** — a residual of **−10.152 ms** (0.06%), well inside the
25 ms ideal and the 50 ms hard ceiling.

The E23 critical-path list omitted four top-level stages and undercounted a
fifth:

- `remote_return_handoff` **1820.642 ms** (remote result emit → local receipt;
  cross-host transport) — absent from E23's list.
- `remote_method_setup` pre-graph portion **1472.095 ms** (method entry →
  graph start; run-plan handling, trace setup, speculative UNET prefetch
  launch, CPU-snapshot CLIP bind) — absent.
- `sampling` boundary undercount **1069.794 ms** — E23 used the legacy
  `sampler_ms` t6 window (3639.628 ms); the exclusive waterfall interval is
  the wrapper `sampling_start → sampling_end` (4709.422 ms).
- `restore_to_method_entry` **39.491 ms**, post-readiness UNET dispatch tail
  **102.883 ms**, `remote_local_return` **31.0 ms** — absent.
- Cross-clock reconciliation adjustment **−10.152 ms**.

Those components sum to 4525.753 ms ≈ 4525.710 ms (0.043 ms is E23's
3-decimal rounding). There is **no hidden 4.5 s bucket**: it is transport
handoff (40%), pre-graph remote setup (33%), a sampler boundary-semantics
difference (24%), and small tails (4%).

The E23 sampler statement is corrected: the 1.06 s historical/current sampling
difference is **not** sampler-node preparation (that interval is only
124.170 ms). It is the **wrapper-internal pre-first-step window**
(`sampling_start → first_sampler_step` = **1067.597 ms**) plus a 2.2 ms legacy
t6 boundary offset.

Revised 13 s assessment: the serial critical path is dominated by the
pre-sampler CLIP interval (5343.978 ms; CLIP encode 5185.42 ms), the sampling
wrapper (4709.422 ms), and the remote handoff (1820.642 ms). **Prefetch
redesign is no longer the top pick**: in ON #2 the UNET source prefetch
(2819 ms) was already fully overlapped inside the CLIP forward window, so the
serial model-readiness interval is CLIP-bound, not UNET-bound.

## 2. Authoritative timing endpoints

| Quantity | Event | Clock | Timestamp (ns) | Source |
|---|---|---|---|---|
| Command start | `command_start` (env `COMFYMODAL_COMMAND_START_UNIX_MS`) | wall:local | 1787020637430000000 | `effective_env` / host trace |
| Local receive | `local_run_request_received` | wall:local | 1787020637824915200 | full_trace event |
| Modal submission | `modal_first_iteration_start` / `modal_submission_attempt` | wall:local | 1787020637910791500 | full_trace event |
| Modal restore begin | `modal_restore_begin` (Modal app log) | wall | 1787020639552144896 | `modal_scheduling` stage end (modal_app_log provenance) |
| Python resume | `v2_startup_post_snapshot_restore_start` | wall | 1787020641011943680 | `pre_python_snapshot_restore` stage end |
| Remote method entry | `remote_method_entry` / `run_plan_method_first_line` | mono:remote | 1480832672235 | full_trace event |
| Graph execution start | `graph_execution_start` | mono:remote | 1482304767614 | full_trace event; `modal_app.py` (trace.emit) |
| Remote result emit | `remote_result_emit` | wall:remote + mono:remote | 1787020654577356620 / 1494099201052 | full_trace event |
| Local result receipt | `local_result_received` | wall:local + mono:local | 1787020656397998900 / 130997000000000 | full_trace event |
| Caller return | `execute_plan_return` | wall:local + mono:local | 1787020656417998700 / 130997031000000 | full_trace event |

**No-scheduling pair (authoritative):**

- `NO_SCHEDULING_START_EVENT` = `command_start` (env `COMFYMODAL_COMMAND_START_UNIX_MS=1787020637430`)
- `NO_SCHEDULING_START_CLOCK` = wall (local host)
- `NO_SCHEDULING_START_TIMESTAMP` = 1787020637430000000 ns
- `NO_SCHEDULING_END_EVENT` = `execute_plan_return` (caller return)
- `NO_SCHEDULING_END_CLOCK` = wall (local host)
- `NO_SCHEDULING_END_TIMESTAMP` = 1787020656417998700 ns
- command → response = 18987.9987 ms
- scheduling time = command_to_enqueue 480.7915 ms + modal_scheduling
  1641.353396 ms = 2122.144896 ms
- **no-scheduling = 18987.9987 − 2122.144896 = 16865.854 ms** (artifact
  `final_reconciled_waterfall.non_scheduling_ms = 16865.853804`; identical —
  not reconstructed from unrelated clocks).

## 3. Clock-domain map

| Domain | Used for | Alignment |
|---|---|---|
| wall:local | command start, local receive, submission, local receipt, caller return | consistent (single host) |
| wall (Modal app log) | `modal_restore_begin`, `pre_python_snapshot_restore` | Modal-reported wall; aligned to host wall via reconciliation |
| mono:remote | application restore → output persistence (all remote stages) | single CLOCK_MONOTONIC on the Modal host; the preferred domain |
| wall:remote | `remote_result_emit` (cross-process marker) | remote host wall |
| wall:local | `local_result_received` | local host wall |
| mono:local | `remote_local_return` (receipt → caller return) | separate local monotonic epoch (130997e12) — not comparable to mono:remote |

- `pre_python_snapshot_restore` is wall-only (Modal app log boundary) and is
  **UNALIGNABLE** to remote monotonic; it is a 1459.799 ms platform interval
  (restore begin → first restored Python line).
- `remote_return_handoff` (1820.642 ms) is a cross-host wall subtraction
  (remote emit wall → local receipt wall). The reconciliation residual of
  −10.152 ms proves the two wall domains agree to within ~10 ms, so the
  1820.642 ms handoff is real serial wall, not clock skew.
- `remote_local_return` (31.0 ms) is mono:local only.

## 4. Full absolute ON #2 event timeline (remote monotonic unless noted)

| Event | Process | mono_ns | wall_unix_ns |
|---|---|---|---|
| command_start | local | — | 1787020637430000000 |
| local_run_request_received | local | — | 1787020637824915200 |
| modal_first_iteration_start (submission) | local | — | 1787020637910791500 |
| modal_restore_begin (app log) | remote | — | 1787020639552144896 |
| python resume (`v2_startup_post_snapshot_restore_start`) | remote | 1480533793287 | 1787020641011943680 |
| snapshot_restore_start | remote | 1480562182220 | 1787020641040333961 |
| snapshot_restore_end (status=ok) | remote | 1480760789665 | 1787020641238941606 |
| v2_restore_finalize_end | remote | 1480793273056 | 1787020641271424557 |
| run_plan_method_first_line / remote_method_entry | remote | 1480832672235 | 1787020641310832896 |
| unet_execution_schedule / preload_submitted (UNET prefetch) | remote | 1480864809136 | 1787020641342960777 |
| unet_prepare_start / preload_worker_started | remote | 1480865477736 | 1787020641343628407 |
| (main-thread setup window ~1.16 s) clip_state_checkpoint | remote | 1482029898488 | 1787020642508053022 |
| snapshot_seed_request_derived | remote | 1482034267617 | 1787020642512423091 |
| run_plan_identity_capture / deserialize | remote | 1482050258892 | 1787020642528414257 |
| run_plan_trace_setup | remote | 1482065258547 | 1787020642543413873 |
| runtime_config_start → end | remote | 1482304699154 → 1482304728804 | 1787020642782854669 |
| graph_execution_start | remote | 1482304767614 | 1787020642782923319 |
| first_executing_node (Any Switch) | remote | 1482485128680 | — (metadata only) |
| prompt_executor_invoke_start | remote | 1482476988713 | 1787020642955144263 |
| execution_prefill_encode_start (CLIP encode) | remote | 1482492352358 | 1787020642970507639 |
| clip_hydration_gpu_start | remote | 1482518127661 | 1787020642996283322 |
| clip_hydration_gpu_end (1345.935 ms) | remote | 1483864071627 | 1787020644342227137 |
| clip_forward_start | remote | 1483864104317 | 1787020644342259977 |
| fast_cold_clip_forward_end (3313.016 ms) | remote | 1487179153071 | 1787020647657308317 |
| clip_forward_end (duration 3315.025) | remote | 1487179187410 | 1787020647657341877 |
| unet_gpu_transfer (fastsafetensors H2D 495 ms) | remote | 1487181399140 → 1487676571184 | 1787020647659554817 |
| execution_prefill_encode_end (5185.417 ms) | remote | 1487677769414 | 1787020648155923793 |
| unet_ready | remote | 1487726223640 (ready_at_ns 1487726178880) | 1787020648204378830 |
| model_readiness_gate (CLIP_READY_AT 1487180806780, UNET_READY_AT 1487726178880) | remote | 1487726273310 | 1787020648204428970 |
| graph_unet_demand | remote | 1487766483579 | 1787020648244639120 |
| first_sampler_node (ClownsharKSampler_Beta 1242) | remote | 1487829106582 | — (metadata only) |
| sampler_lane_wait_start | remote | 1487829295822 | 1787020648307451293 |
| graph_gpu_load / mp_load / load_models_gpu | remote | 1487884033767 → 1487927317605 | 1787020648362188399 |
| sampling_start (wrapper; steps=8) | remote | 1487953466298 | 1787020648431621830 |
| first_sampler_step (first completed step callback) | remote | 1489021062805 | 1787020649499217423 |
| sampling_end (wrapper, duration_ms=4709.447) | remote | 1492662888557 | 1787020653141044007 |
| vae_early_activation_scheduled / load_start | remote | 1492663188577 / 1492665377926 | 1787020653141344237 |
| vae_decode_start (1st) | remote | 1493501727313 | 1787020653979882886 |
| vae_early_activation_terminal / consumed | remote | 1493524266547 / 1493524480047 | 1787020654002421989 |
| vae_decode_start (2nd, decode_wall 326.472) | remote | 1493524591447 | 1787020654002747089 |
| vae_decode_end (1st / 2nd, duration 349.928) | remote | 1493851253543 / 1493851651163 | 1787020654329409099 |
| output_encode_start (PNG 1088×1920) | remote | 1493851936043 | 1787020654330091689 |
| output_encode_end (duration 161.779) | remote | 1494013723356 | 1787020654491879014 |
| output_persist_end (5.861) / output_collect_end | remote | 1494019656525 / 1494019818575 | 1787020654497811952 |
| graph_execution_end | remote | 1494020740074 | 1787020654498895472 |
| close_workers_end / fast_cold_orchestration | remote | 1494020839064 / 1494021487094 | 1787020654498994742 |
| remote_result_emit | remote | 1494099201052 | 1787020654577356620 |
| local_result_received | local | 130997000000000 | 1787020656397998900 |
| execute_plan_return (caller return) | local | 130997031000000 | 1787020656417998700 |

## 5. Consecutive critical-path segments

Segments tile the non-scheduling wall. All durations are the artifact's
measured top-level stages; start/end events are the boundaries above.

| START EVENT | END EVENT | DELTA_MS | CLASS | KNOWN WORK | OVERLAPPED | CONF |
|---|---|---|---|---|---|---|
| command_start | modal_restore_begin | 2122.145 | scheduling (excluded) | enqueue 480.79 + Modal placement 1641.35 | none | high |
| modal_restore_begin | python resume | 1459.799 | platform restore | Modal pre-Python snapshot restore | none | high (wall) |
| python resume | restore end | 259.388 | application restore | snapshot_restore 198.6, gpu_state 155.3 (inner overlap), finalize | inner | high |
| restore end | remote method entry | 39.491 | restore→method | finalize/handoff | none | high |
| remote method entry | prompt_executor_invoke | 1644.316 | remote method setup | run-plan handling, trace setup, UNET prefetch launch, CPU-snapshot CLIP bind, runtime shape/config | UNET source prefetch (worker) | high |
| prompt_executor_invoke | first executing node | 8.169 | cache setup | executor call→cached→first node (0.839+6.717+0.614) | none | high (derived) |
| first executing node | first sampler node | 5343.978 | pre-sampler execution | CLIP encode 5185.42 (hydration 1345.94 + forward 3313.02 + tokenize), conditioning-cache miss (lookup 1.511), UNET tail 545 | UNET source read 2819 (worker, inside CLIP window) | high (derived) |
| first sampler node | sampling_start | 124.170 | sampler pre-boundary | lane wait 0.195 + lane-acquired→stage 124.149 (window: lane→graph_gpu_load 54.7, graph_gpu_load/mp_load 32.1, load_models_gpu 70.6 overlapping inside, dispatch tail 26.5) | none | high |
| sampling_start | first_sampler_step | 1067.597 | sampler pre-first-step | wrapper setup, deep-profile begin, first UNET forward | VAE early-activation prep? (0) | high |
| first_sampler_step | sampling_end | 3641.826 | diffusion loop | steps 2–8 (8 steps total) | none | high |
| sampling_end | vae_decode_start (1st) | 838.839 | post-sampling transition | graph to VAEDecode, VAE early-activation schedule + load submit (load itself 858.9 overlaps vae stage) | VAE H2D (worker) | high |
| vae_decode_start (1st) | vae_decode_end (1st) | 349.526 | VAE decode | decode wall ~326.5 + ready wait | none | high |
| vae_decode_end | remote_result_emit | 247.265 | output persistence | PNG encode 161.787 + descriptor 5.933 + collect + teardown 79.4 | none | high |
| remote_result_emit | local_result_received | 1820.642 | remote handoff | Modal result transport (3.13 MB PNG) | none | medium (cross-host wall) |
| local_result_received | execute_plan_return | 31.000 | local return | result handling → caller return | none | high |
| **Total accounted** | | **16876.006** | | residual vs 16865.854 = **−10.152** | | |

No consecutive unexplained interval ≥ 25 ms remains: every interval ≥ 25 ms
has a row with identified work. The only sub-25 ms gaps are the −10.152 ms
reconciliation offset (cross-clock) and sub-ms stage seams.

## 6. 4525.710 ms residual decomposition

E23 sum = 12340.144 ms; no-scheduling = 16865.854 ms; residual = 4525.710 ms.

The residual decomposes exactly into components that were absent from or
undercounted by the E23 stage list:

| Component | ms | % of residual | Category | Proof |
|---|---:|---:|---|---|
| `remote_return_handoff` (emit → local receipt) | 1820.642 | 40.2% | remote output/return transport | `remote_result_emit` wall 1787020654577356620 → `local_result_received` wall 1787020656397998900 |
| `remote_method_setup` pre-graph (method entry → graph start) | 1472.095 | 32.5% | pre-graph execution wall | `remote_method_entry` 1480832672235 → `graph_execution_start` 1482304767614 (minus the 172.221 graph-setup tail inside invoke) |
| Sampling boundary undercount (wrapper 4709.422 − legacy sampler_ms 3639.628) | 1069.794 | 23.6% | sampler boundary mismatch | wrapper `sampling_start→sampling_end` vs legacy t6 window; see §7 |
| Post-readiness UNET dispatch tail (unet_ready → first_sampler_node) | 102.883 | 2.3% | model-ready → sampler entry | `unet_ready` 1487726223640 → `first_sampler_node` 1487829106582 |
| `restore_to_method_entry` | 39.491 | 0.9% | restore tail | stage measured |
| `remote_local_return` (receipt → caller return) | 31.000 | 0.7% | local handoff | stage measured |
| Cross-clock reconciliation adjustment | −10.152 | −0.2% | clock-origin adjustment | `final_reconciled_waterfall.residual_ms` |
| **Total** | **4525.753** | **100.0%** | | ≈ 4525.710 (0.043 ms = E23 3-decimal rounding) |

**Answer: multiple categories, no hidden bucket.** Pre-graph execution wall
(39.491 + 1472.095 = 1511.586 ms, 33.4%), remote output/return transport
(1820.642 ms, 40.2%), and the sampler boundary-semantics difference
(1069.794 ms, 23.6%) dominate. There is no double-counting or undercounting
inside the artifact's own waterfall; the E23 list simply was not exclusive
(it omitted 4 stages and used the legacy sampler window).

## 7. Sampler 945.624 ms discrepancy

Absolute timeline (mono:remote):

| Boundary | mono_ns | ms from graph start |
|---|---:|---:|
| first_sampler_node | 1487829106582 | 5524.34 |
| sampler_lane_wait_start | 1487829295822 | 5524.53 |
| **sampling_start** (wrapper) | 1487953466298 | 5648.70 |
| **first_sampler_step** (first completed step callback) | 1489021062805 | 6716.29 |
| **sampling_end** (wrapper) | 1492662888557 | 10357.82 |

- Historical-style wrapper interval `sampling_start → sampling_end` =
  **4709.422 ms** (`deltas_ms.sampling` = 4709.42; `sampling_end.duration_ms` =
  4709.447). Both events are emitted by the sampler wrapper
  (`runtime_executor.py:4694` start, `runtime_executor.py:4883` end).
- `sampler_ms` (legacy t6 window `t6_sampler_start → t6_sampler_end`) =
  **3639.628 ms**. The t6 boundary is emitted by the legacy stage-window
  recorder (`comfyapp.py:15604-15628`, `_commit_stage_windows_to_trace`),
  not the wrapper. Alignment check: `t6_sampler_start` wall 1787020649.4993932
  vs `first_sampler_step` wall 1787020649.4992175 (t6 starts **+0.176 ms after**
  first step); `t6_sampler_end` wall 1787020653.1390207 vs `sampling_end` wall
  1787020653.1410440 (t6 ends **−2.023 ms before** sampling_end). So
  `sampler_ms` ≈ `first_sampler_step → sampling_end` − 2.199 ms =
  3641.826 − 2.199 = 3639.627 ≈ 3639.628. **The legacy window is the
  diffusion loop from first completed step to wrapper return.**
- Wrapper interval = pre-first-step 1067.597 ms + first-step→end 3641.826 ms =
  4709.423 ≈ 4709.422.

Final values:

- `SAMPLER_VISIBLE_EXTRA_MS` = **1069.794** (4709.422 − 3639.628)
- `CONFIRMED_PRE_SAMPLE_MS` = **124.170** (sampler-node → sampling-start;
  lane wait 0.195 + lane-acquired→stage 124.149)
- `REMAINING_SAMPLER_BOUNDARY_GAP_MS` = **945.624** (1069.794 − 124.170)
- `REMAINING_GAP_CAUSE` = **wrapper-internal pre-first-step window**:
  `sampling_start → first_sampler_step` = 1067.597 ms (measured), minus the
  124.170 pre-wrapper node→start interval = 943.427 ms, plus the 2.199 ms
  legacy t6 boundary offset = **945.626 ms ≈ 945.624**. The gap lives
  **inside the sampler wrapper**, between the `sampling_start` event and the
  first completed step callback (`runtime_executor.py:4815` emitter), and is
  real serial wall: sampler setup, deep-profile begin, and the first UNET
  forward. It is **not** sampler-node preparation (which is only 124.170 ms)
  and is **not** removable boundary overhead; the 1067.6 ms is predominantly
  first-step model work (setup-vs-compute split UNKNOWN — no per-step deep
  profile in this artifact).

## 8. Model-readiness → sampling gap

- `unet_ready` = 1487726223640 (ready_at_ns 1487726178880)
- `clip_ready` = 1487180806780 (gate `CLIP_READY_AT`; orchestration
  `clip_ready_at` 1487.179100971 s)
- joint readiness = `unet_ready` (gated by UNET; `model_readiness_gate`
  `READINESS_GATED_BY=UNET`, `EXPOSED_MODEL_READINESS_MS=5426.35`)
- `JOINT_READY_TO_SAMPLER_NODE_MS` = **102.883** (`unet_ready` →
  `first_sampler_node`): graph_unet_demand (40.3 ms) + demand→consumed
  (0.2 ms) + consumed→first_sampler_node (62.4 ms) — graph-side dispatch and
  sampler-node entry after both models ready.
- `SAMPLER_NODE_TO_SAMPLING_START_MS` = **124.170** (measured; lane wait
  0.195 + graph_gpu_load/mp_load/load_models_gpu + dispatch ≈ 124.149).
- `JOINT_READY_TO_SAMPLING_START_MS` = **227.243** (102.883 + 124.360).
- `JOINT_READY_TO_FIRST_SAMPLER_STEP_MS` = **1294.839** (102.883 + 1067.597 +
  124.360) — i.e., 1.29 s after both models are ready before the first step
  completes, of which only 227 ms is pre-sampling dispatch and 1067.6 ms is
  wrapper-internal first-step work.

After model readiness the wall is modest (227 ms to sampling start); the large
pre-sampler interval (5343.978 ms) is **before** readiness and is dominated by
the CLIP encode (5185.42 ms).

## 9. Restore-end to graph-start

`RESTORE_END_TO_GRAPH_START_MS` = **1511.586 ms**
(application-restore end 1480793181546 → `graph_execution_start`
1482304767614).

Decomposition:

| Segment | ms | Content |
|---|---:|---|
| restore → method entry | 39.491 | finalize/handoff (`v2_restore_finalize` → `run_plan_method_first_line`) |
| method entry → graph start | 1472.095 | run-plan identity capture/deserialize (0.03), trace setup (6.0), `remote_setup_schedule`/first status yield, UNET execution-schedule + speculative prefetch launch (~33 ms), core/unet wrapper installs (~1 ms), a ~1.16 s main-thread window (unet_decompose_install → clip_state_checkpoint) coinciding with the UNET source prefetch running on workers, snapshot_seed request derive, runtime_shape, runtime_config (0.03), legacy_runtime_load (0.01) |
| graph start → invoke (graph_setup) | 172.221 | this tail is inside `remote_method_setup` and is not part of this gap |

So the 1511.586 ms is almost entirely (1472.095 ms) remote method pre-graph
setup — **not** hidden PromptExecutor/validation work (validation 0.02,
registry 0.035, pregraph 0.337, executor_reset 0.054 — all sub-ms). The
~1.16 s main-thread window is the dominant sub-component; the speculative UNET
prefetch runs concurrently on worker threads (prefetch wall 2819 ms, overlapped
with the CLIP window per `unet_prefetch_overlap_with_setup_ms=2819.289`), so it
is not the main-thread wait — the wait is the setup sequence itself
(snapshot-seed derive, runtime shape observation, trace setup).

## 10. Output-end to response

Remote application work after output collection:

- `output_encode_end` → `output_persist_end` = 5.933 ms (descriptor)
- `output_persist_end` → `output_collect_end` = 0.162 ms
- `output_collect_end` → `remote_result_emit` = **79.382 ms** (executor
  teardown, `close_workers`, `fast_cold_orchestration` finalize, result
  serialization)
- `OUTPUT_END_TO_REMOTE_RETURN_MS` = **78.461 ms** using
  `graph_execution_end` → `remote_result_emit` (or 79.382 from
  `output_collect_end`).

Transport/handoff:

- `REMOTE_RETURN_TO_LOCAL_RESPONSE_MS` = **1820.642 ms** (`remote_result_emit`
  wall → `local_result_received` wall) + **31.0 ms** local receipt → caller
  return = **1851.642 ms** total.

The 1820.642 ms is remote-application-to-local-receipt transport (Modal result
streaming of the 3.13 MB PNG) — **not** scheduling and **not** remote app
work. The reconciliation residual (−10.152 ms) confirms the cross-host wall
alignment, so this interval is real serial wall on the local measurement.

## 11. Corrected E23 sampler statement

E23 §7/§9 claimed the 1.06 s historical/current sampling difference is
"principally the sampler-node-to-actual-sampling preparation interval."
That is numerically inconsistent with the measured 124.170 ms pre-interval.

Corrected interpretation (ON #2):

- **CONFIRMED**: `sampler_node_to_sampling` = 124.170 ms (measured, lane wait
  0.195 + lane-acquired→stage 124.149).
- **CONFIRMED**: the wrapper contains a 1067.597 ms pre-first-step window
  (`sampling_start` → `first_sampler_step`, both measured events).
- **CONFIRMED**: the legacy `sampler_ms` window (3639.628 ms) is aligned to
  `first_sampler_step → sampling_end` − 2.199 ms (both alignment offsets
  measured to ±0.2 ms).
- **SUPPORTED INFERENCE**: the 1067.6 ms is predominantly first-UNET-forward
  and sampler setup (real serial wall), not removable node-boundary overhead;
  the removable boundary cost remains ≤ 124.170 ms.
- **UNKNOWN**: the exact setup-vs-compute split inside the 1067.6 ms window
  (no per-step deep profile captured in this artifact).

The historical 4.709–4.734 s "sampling" and the current 3.64–3.68 s
`sampler_ms` are **different spans** (wrapper interval vs diffusion loop), and
their 1.06 s difference is a boundary-semantics artifact, not a proven
1.1 s diffusion optimization. Do not treat the 1.06 s as removable.

## 12. Fully reconciled waterfall (ON #2, non-double-counted)

| # | Stage | Start event → End event | ms | % of 16865.854 | Critical-path | Optimization relevance |
|---|---|---|---:|---:|---|---|
| 1 | pre_python_snapshot_restore | modal_restore_begin → python resume | 1459.799 | 8.7% | yes (wall) | platform snapshot; region/host variable |
| 2 | application_restore | python resume → restore end | 259.388 | 1.5% | yes | snapshot_restore 198.6 + gpu_state 155.3 (inner overlap) |
| 3 | restore_to_method_entry | restore end → method entry | 39.491 | 0.2% | yes | small |
| 4 | remote_method_setup | method entry → executor invoke | 1644.316 | 9.8% | yes | pre-graph setup 1472.095; UNET prefetch launch; ~1.16 s main-thread window |
| 5 | prompt_executor_cache_setup | invoke → first node | 8.169 | 0.0% | yes | signature-cache hit; negligible |
| 6 | pre_sampler_execution | first node → first sampler node | 5343.978 | 31.7% | yes | CLIP encode 5185.42 (hydration 1345.94 + forward 3313.02); UNET source read overlapped on workers |
| 7 | sampler_node_to_sampling | sampler node → sampling_start | 124.170 | 0.7% | yes | lane wait + graph_gpu_load/mp_load/load_models_gpu |
| 8 | sampling (wrapper) | sampling_start → sampling_end | 4709.422 | 27.9% | yes | pre-first-step 1067.597 + diffusion loop 3641.826; legacy sampler_ms 3639.628 |
| 9 | post_sampling_transition | sampling_end → vae_decode_start | 838.839 | 5.0% | yes | graph→VAEDecode, VAE early-activation schedule; VAE H2D 858.9 overlaps the vae stage |
| 10 | vae | vae_decode_start → vae_decode_end | 349.526 | 2.1% | yes | decode ~326.5 + ready wait |
| 11 | output_persistence | output_encode_start → remote_result_emit | 247.265 | 1.5% | yes | PNG encode 161.787 + descriptor 5.933 + teardown 79.4 |
| 12 | remote_return_handoff | remote_result_emit → local_result_received | 1820.642 | 10.8% | yes (cross-host wall) | Modal result transport (3.13 MB PNG) |
| 13 | remote_local_return | local_result_received → caller return | 31.000 | 0.2% | yes (mono:local) | result handling |
| | **Total accounted** | | **16876.006** | 100.1% | | |
| | **Residual vs 16865.854** | | **−10.152** | −0.06% | | cross-clock alignment |

`FINAL_UNEXPLAINED_RESIDUAL_MS = −10.152` — meets the ≤ 25 ms ideal (10.15 ms)
and the ≤ 100 ms target with large margin. The boundary that prevents tighter
reconciliation is the cross-host wall pair `remote_result_emit` (remote wall)
→ `local_result_received` (local wall), plus the wall-only Modal restore
boundary; both are inherent clock-domain seams, and the artifact's own
reconciliation already resolves them to 10.15 ms.

## 13. Revised 13-second gap and ranking

- `CURRENT_NO_SCHEDULING_MS` = 16865.854
- `REQUIRED_SAVING_TO_13S_MS` = **3865.854**

Serial critical-path intervals containing that saving (from the reconciled
waterfall only; no Worker-B/accumulated credit):

| Rank | Interval | ms | Plausible saving | Basis |
|---|---|---:|---:|---|
| 1 | Pre-sampler CLIP interval (stage 6) | 5343.978 | 400–800 | CLIP encode 5185.42 = hydration 1345.94 + forward 3313.02 + tokenize 14.1. Hydration is load-side and overlap-able; conditioning-cache reuse. **UNET source prefetch already overlapped** (prefetch wall 2819 ms sits inside the CLIP forward window), so UNET-side prefetch redesign has little serial effect here. |
| 2 | Remote result handoff (stage 12) | 1820.642 | 0–1300 | Transport of a 3.13 MB PNG. Output streaming/compression/earlier emit. Confidence LOW–MEDIUM (Modal platform dependent). |
| 3 | Remote method setup pre-graph (stage 4) | 1472.095 | 0–700 | ~1.16 s main-thread setup window; overlap with restore, defer speculative launch. Confidence MEDIUM. |
| 4 | Sampler wrapper pre-first-step (inside stage 8) | 1067.597 | 100–400 | First-step setup/forward; removable boundary ≤ 124.170. Confidence MEDIUM. |
| 5 | Pre-Python restore (stage 1) | 1459.799 | 0–700 | Platform snapshot; region/host variable (E23: variable). Confidence MEDIUM. |

Even taking the top three plausible savings at their midpoints (~600 + 650 +
350), the path to 3865.854 ms requires aggressive cuts across **all** of:
CLIP pre-sampler wall, transport handoff, pre-graph setup, sampler pre-first-step,
and restore — no single interval contains the full gap.

**Prefetch redesign is no longer the top pick.** In ON #2 the UNET source
prefetch (2819 ms, fraction 1.0) completed **inside** the CLIP forward window
(`unet_prefetch_overlap_with_setup_ms=2819.289`; `unet_prefetch_end_at` 1486.689
< `clip_forward_end_at` 1487.179), so the exposed model-readiness interval
(5421.529 ms) is CLIP-bound, not UNET-source-bound. The 545 ms post-CLIP UNET
tail is fastsafetensors H2D + patcher — a real but modest (~500 ms) target.

## 14. Prefetch conclusions preserved (analysis-only, not implemented)

E23's prefetch assessment is carried forward unchanged; E24 makes no runtime
change to the loader, prefetch, snapshot, D15, sampler, VAE, output, or Modal
configuration:

- `PREFETCH_SOURCE_EFFECT` = **VARIABLE**
- `PREFETCH_CLIP_EFFECT` = **HARMFUL**
- `PREFETCH_NET_READINESS_EFFECT` = **VARIABLE**
- `ENGINEERING_DIRECTION` = **KEEP_CONCEPT_BUT_REDESIGN**

E24's contribution to the decision is a corrected serial-cost picture: in ON #2
the UNET source prefetch (2819.289 ms wall, fraction 1.0) completed entirely
inside the CLIP forward window (`unet_prefetch_end_at` 1486.688714895 <
`clip_forward_end_at` 1487.179100971), so the exposed model-readiness interval
is CLIP-bound — the prefetch already hides the UNET source read from the serial
wall. A redesign therefore cannot recover UNET-read time on this critical path;
the open CLIP-side serial costs are hydration (1345.94 ms) and forward
(3313.02 ms), plus the 545 ms post-CLIP UNET tail. The prefetch concept should
be retained only insofar as it can be re-aimed at CLIP-side cost without
starting a competing full-read on the CLIP critical path. **Do not implement in
E24** — E24's answer to the E23 question is that the model-readiness interval
is not the single best next implementation target; see §13.

## 15. Final fields

```text
E24_CRITICAL_PATH_CLOSURE_COMPLETE
REMOTE_DEPLOYS = 0
PAID_REQUESTS = 0
COMMIT = none

NO_SCHEDULING_MS = 16865.854
NO_SCHEDULING_START_EVENT = command_start (env COMFYMODAL_COMMAND_START_UNIX_MS)
NO_SCHEDULING_END_EVENT = execute_plan_return (caller return)

KNOWN_E23_STAGE_SUM_MS = 12340.144
INITIAL_UNEXPLAINED_RESIDUAL_MS = 4525.710

RESTORE_TOTAL_MS = 1719.187 (pre_python 1459.799 + application 259.388)
RESTORE_END_TO_GRAPH_START_MS = 1511.586 (restore_to_method 39.491 + method->graph 1472.095)

GRAPH_START_TO_JOINT_READY_MS = 5421.529 (graph_execution_start -> unet_ready; gated by UNET)
JOINT_READY_TO_SAMPLER_NODE_MS = 102.883
SAMPLER_NODE_TO_SAMPLING_START_MS = 124.170
JOINT_READY_TO_SAMPLING_START_MS = 227.243

SAMPLER_MS = 3639.628 (legacy t6 window = first_sampler_step->sampling_end - 2.199)
SAMPLER_VISIBLE_INTERVAL_MS = 4709.422 (wrapper sampling_start->sampling_end)
SAMPLER_VISIBLE_EXTRA_MS = 1069.794
KNOWN_PRE_SAMPLE_COMPONENT_MS = 124.170
PREVIOUSLY_UNEXPLAINED_SAMPLER_GAP_MS = 945.624
SAMPLER_GAP_CAUSE = wrapper-internal pre-first-step window (sampling_start->first_sampler_step = 1067.597, measured) minus 124.170 pre-interval plus 2.199 legacy t6 offset; real first-step serial wall, not sampler-node preparation

SAMPLING_END_TO_VAE_TRANSITION_END_MS = 838.839
VAE_TRANSITION_MS = 838.839
VAE_DECODE_MS = 349.526

PNG_OUTPUT_MS = 247.265

OUTPUT_END_TO_REMOTE_RETURN_MS = 78.461 (graph_execution_end -> remote_result_emit; 79.382 from output_collect_end)
REMOTE_RETURN_TO_LOCAL_RESPONSE_MS = 1820.642 (transport) + 31.000 (local handling) = 1851.642

FINAL_RECONCILED_STAGE_SUM_MS = 16876.006
FINAL_UNEXPLAINED_RESIDUAL_MS = -10.152

CLOCK_DOMAIN_LIMITATIONS = pre_python_snapshot_restore is wall-only (Modal app log) and not monotonic-alignable; remote_return_handoff is a cross-host wall subtraction (remote emit wall -> local receipt wall) whose ~10 ms alignment is proven by the reconciliation residual; remote_local_return is mono:local only

REQUIRED_SAVING_TO_13S_MS = 3865.854

TOP_SERIAL_BOTTLENECK_1 = pre-sampler CLIP interval (stage 6, 5343.978 ms; CLIP encode 5185.42)
BOTTLENECK_1_MS = 5343.978
PLAUSIBLE_SAVING_1_MS = 400-800

TOP_SERIAL_BOTTLENECK_2 = remote result handoff (stage 12)
BOTTLENECK_2_MS = 1820.642
PLAUSIBLE_SAVING_2_MS = 0-1300

TOP_SERIAL_BOTTLENECK_3 = remote method setup pre-graph (stage 4)
BOTTLENECK_3_MS = 1472.095
PLAUSIBLE_SAVING_3_MS = 0-700

PREFETCH_REDESIGN_STILL_NEXT = NO (UNET source prefetch was already fully overlapped inside the CLIP forward window in ON #2; the serial model-readiness interval is CLIP-bound, and the transport handoff + pre-graph setup are larger un-attacked serial costs)

NEXT_IMPLEMENTATION_BATCH = pre-sampler CLIP-readiness reduction (hydration overlap + conditioning-cache reuse; CLIP-side, not UNET-source), then output-handoff reduction; prefetch redesign only after CLIP-side accounting is closed
```

STOP. No remote work. No runtime modifications.
