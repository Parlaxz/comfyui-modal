# V2_BATCH_D13_REQUEST_ENTRY_SETUP_FORENSICS.md

**Date:** 2026-08-16 (analysis session)
**Scope:** Explain why D11 cold specimens (runs 2/5/6) each spend ~1.45–1.72 s between Modal
method entry and `prompt_executor_invoke_start`; enumerate every span, map to exact code,
rank serial components, assess movability to snapshot / plan-receipt / post-worker-start /
deferral. **Forensics only — no fixes implemented.**
**Specimens:** deployment `2305b0b3bbdf3fbe02904527`, runtime 12 CPU / 32768 MiB, profile
TBASE, generation O0, fingerprint `f504e296c398bdcb2c4c07e2`; runs 2/5 on GCP `us-east4`,
run 6 on AWS `us-east-1`. Cold containers (first request after snapshot restore, snapshot
UNET absent, snapshot active=0).

---

## 1. Headline results

| Metric (ms) | Run 2 | Run 5 | Run 6 | Mean |
|---|---|---|---|---|
| **REMOTE_METHOD_SETUP** (official waterfall, method first line → `prompt_executor_invoke_start`) | **1722.217** | **1492.731** | **1454.114** | ~1556 |
| `method_entry_to_first_remote_event_ms` (critical_path_metrics) | 1640.238 | 1404.152 | 1176.811 | — |
| PromptExecutor/cache setup (waterfall row 5) | 10.1 | 139.6 | 6.9 | 52.2 |

**Verdict:** ~65–72 % of the 1.45–1.72 s setup window is ONE serial block — the
plan-receipt “schedule region” that runs between the Batch-A G1 UNET lane submission and
the first status yield (`_setup_schedule_start_ns` bracket, officially
`remote_setup_schedule.schedule_ms` = **1248.5 / 1108.9 / 987.8**). Inside that bracket the
main thread performs snapshot-seed derivation (`build_invocation_seed_payload` +
`hydrate_snapshot_seed_payload`), the first prompt-signature store load
(`load_store_from_disk`), context/trace construction, and `validate_torch_thread_policy`
— while two daemon threads (input-types warm 4.88–5.56 s, conditioning prefetch) and the
fastsafetensors UNET lane reader compete for CPU/GIL. The next-largest blocks are the
status-yield → executor-stream resume gap (17–206 ms), the request-bound → model-validation
checkpoint gap (3–188 ms, same code path in all three runs), and D11 row-5 cache setup
(7–140 ms).

---

## 2. Method & alignment

- Traces: `comfymodal-data\benchmarks\runs\v2_2026-08-16_18-26-58\run_001_sample.json` (R2),
  `...\18-29-25\` (R5), `...\18-30-19\` (R6) — `full_trace.events` (~543 events each),
  all request-phase events share one `monotonic_ns` clock (pid=2). Restore-phase events
  (34–48 s region) are a *different* clock domain and are excluded; the setup window is
  defined on the request clock between
  `run_plan_method_first_line`/`remote_method_entry` (method) and
  `prompt_executor_invoke_start` (execution).
- Emitters verified by source: `trace.emit` wrappers in `comfymodal_runtime\trace.py`;
  lane worker events in `model_preload.py:11290-11446` (`f"{name}_prepare_start"` =
  `unet_prepare_start` is the **UNET lane worker's first instruction**, not a main-thread
  event); `pre_sampler_{op}` in `runtime_executor.py:645-650` (so
  `pre_sampler_cache_key_build` is the PreSamplerCache `build_cache_key` op,
  `duration_ms≈0.002` — the work is trivial; the gap around it is everything else in the
  stream head); `container_entry`/`remote_setup_schedule` at
  `modal_app.py:17429-17449`; `clip_state_checkpoint` at
  `clip_fast_hydration_wiring.py:218-310` (diagnostic-only, gated on
  `clip_fast_hydration_enabled() or clip_snapshot_exclude_weights_enabled()`).
- Cross-check: `final_reconciled_waterfall.remote_method_setup` == D11 report row 4
  (1.722 / 1.493 / 1.454 s) exactly; reconciliation status OK, residual ≤ 10 ms.

---

## 3. Aligned setup timelines (request clock, ms from method first line)

Legend: `Δ` = delta from previous event. Setup total = last `Δ` column sum → invoke.

### 3.1 Run 2 (GCP, total 1722.2)

| Δ (ms) | Cumulative | Event | Meaning / code |
|---|---|---|---|
| 0 | 0 | `run_plan_method_first_line` / `remote_method_entry` (method) | `modal_app.py:16470-16483`; `_method_first_line_ns` first line of `run_prompt` |
| +16 | 16 | identity capture end | `_capture_remote_identity()` `modal_app.py:16491` (capture_ms 0.44) |
| +0.8 | 17 | `run_plan_deserialize_end` | `ExecutionPlan.from_dict` `modal_app.py:16628` (deserialize_ms 0.79) |
| +14 | 31 | `unet_execution_plan_receipt_schedule` | Batch-A G1 schedule preamble `modal_app.py:16641-16645` → `_maybe_schedule_execution_unet_at_plan_receipt` (7749): lazy-init snapshot state, `derive_model_key`/`derive_prefill_key`/`build_restore_model_spec`, role-match gate, bridge `_init_ready_preparation`, plan-receipt trace create |
| +0.7 | 32 | `unet_prepare_start` / `preload_worker_started` (lane=unet) | lane submit (`bridge.schedule_execution_unet` 7868-7873); worker picked up in 0.6-0.7 ms |
| — | — | `core_wrapper_install` ×24, `unet_sd_wrapper_install`, `unet_decompose_install` ×13 | worker-thread wrapper installs `model_preload.py:11376-11383` (~30 ms) |
| **+1212** | **1244** | `clip_state_checkpoint(conditioning_prefetch_worker_start)` | **GAP1.** See §4.1. The prefetch thread's first instruction ran 1211 ms after `Thread.start()` — proof of extended CPU/GIL saturation during this region |
| +4.6 | 1249 | `snapshot_seed_request_derived` | seed attach + emit `modal_app.py:17087-17193` (region end) |
| +51.7 | 1301 | `container_entry`, `remote_setup_schedule` (`schedule_ms`: **1248.5**) | trace metadata, `validate_torch_thread_policy` (17210-17214), pre-trace event merge (17245), emits (17429-17449). Official G1 bracket: 16641→17439 |
| +0 | 1301 | `run_plan_first_status_yield` (`plan_received`) | first async yield `modal_app.py:17452-17459` → host round trip |
| **+206.4** | **1507** | `pre_sampler_cache_key_build` | **GAP3** stream-resume: host consumes status → `__anext__` → `executor.stream(plan)` head `17460-17464` → RuntimeExecutor preamble → PreSamplerCache attach/`build_cache_key` (runtime_executor.py:695, op cost 0.002 ms). Everything in this gap is un-instrumented |
| +0.16 | 1508 | `snapshot_seed_consumed` (status=match) | executor seed hook (install `modal_app.py:14805`) |
| +8.1 | 1516 | `cpu_snapshot_models_request_bound` (bound, clip_vae_only, dur 2.1) | runtime_config (`modal_app.py:11418-11420`, ~0.05 ms), legacy_runtime_load, `graph_execution_start` (11430), retarget, `cpu_snapshot_clip_vae_bind` (clip+VAE, 2.1 ms) |
| **+187.8** | **1704** | `clip_state_checkpoint(restore_after_snapshot_model_validation)` | **GAP2.** Identical code path as R6's 3.0 ms — see §4.3. Contains only the ~30 lines 11764-11892 (bound emit, checkpoint call, retained-identity record/verify) + `_enforce_snapshot_activation_invariant` (11921) |
| +1.2 | 1706 | `snapshot_activation_invariant` (ok) | invariant recorded |
| +3.0 | 1709 | execution-prefill lane `preload_worker_started` | prefill scheduled (11933+), worker pickup 2.98 ms |
| +0.24 | 1709 | `unet_execution_schedule` reason=**already_prepared** | **G1 payoff:** no second UNET schedule needed at graph time |
| +10.3 | 1719 | `plan_proof_*`, validation, `res4lyf` | proof 1.1 ms, plan_proof_decision 0.4 ms, res4lyf 0.9 ms, missing-node repair 0.07, prompt_validation 0.02 |
| +5.4 | 1725 | `legacy_preload_check_end` | preload check start→end 5.4 ms (R6 5.9; R5 110.9 — see §4.4) |
| +0.1 | 1725 | pregraph/registry/executor reset | `production_registry_setup` 0.03-0.06 ms, `executor_reset` 0.05 ms (`modal_app.py:13222-13327`) |
| +2.4 | **1727** | `prompt_executor_invoke_start` | `modal_app.py:13607` (quiesce request 2.4 ms before) |

(Small deltas round — official total 1722.217.)

### 3.2 Run 5 (GCP, total 1492.7)

Method head **18.1** → G1 lane (worker start 802888.84) → **GAP1 +1087.3** →
`plan_received` tail +34.6 → **GAP3 +126.3** (`pre_sampler_cache_key_build`
804137.139) → seed consume +5.8 → **GAP2 +92.5** (`restore_after_snapshot_model_validation`
804235.498) → invariant/prefill/proofs +7.5 → **legacy_preload_check 110.9** →
invoke tail +2.9. `schedule_ms` = **1108.9**.

### 3.3 Run 6 (AWS, total 1454.1)

Method head **20.4** → G1 lane (worker start 162995.0) → **GAP1 +962.6** →
`plan_received` tail +39.1 → **GAP3 +17.1** (smallest of the three) → seed consume →
**+216.4 until `runtime_config_start`** (executor head inflated; seed consumed at
164013.944, runtime_config at 164227.694 — the stream-head block absorbed ~214 ms,
largest of the three) → request_bound → **GAP2 +3.0** (smallest — proof the block is
contention, not serial work) → invariant → **execution-prefill worker QUEUED 120.4 ms**
(`queue_wait_ms` 120.409 — pool busy with the still-loading UNET lane) → proofs +
**legacy_preload_check 5.9** → **unet_quiesce→invoke +58.2**. `schedule_ms` = **987.8**.

---

## 4. Component forensics

### 4.1 GAP1 — plan-receipt schedule region (963 – 1212 ms; mean ~1087) ★ BIGGEST

Main thread, between lane submit completion and the pf-checkpoint before seed emit
(`modal_app.py:16647 – 17449`), holding the GIL:

1. `load_store_from_disk()` — **first** prompt-signature store load, volume file read +
   decode (`modal_app.py:16647-16655`; module-guarded once per container). Not
   micro-instrumented; volume first access est. 50–200 ms. **Snapshot-movable.**
2. Conditioning-prefetch daemon thread start (`16657-16712`, ~0.5 ms) — off critical
   path; worker's own first line starved 0.96–1.21 s (its checkpoint fires at GAP1 END).
3. Input-types warm daemon thread start (`16714-16880+`, ~0.5-1 ms) — off critical
   path; warm itself runs **4877 / 5103 / 5562 ms** starting HERE, i.e. it spans the
   entire setup window and the first ~3-4 s of execution, stealing GIL.
4. `_derive_request_snapshot_seed(plan)` (`17087`, impl `16096-16221`) →
   `build_invocation_seed_payload(workflow, ...)` + `state.hydrate_snapshot_seed_payload`
   — pure-Python 43-node workflow graph analysis (static signatures, loader/sampler
   node classification, reachability, stable hashes). Est. 150–400 ms. **Plan-dependent;
   movable to a background thread or cached by `workflow_hash` per container.**
5. `ExecutionContext(...)` construction (`17167-17181`), `_attach_snapshot_seed_metadata`
   (`17184`), seed observability emit (`17189-17193`), trace `set_metadata` with large
   dicts (`17194-17208`), `validate_torch_thread_policy` (`17210-17214`, enforce=True),
   `_pre_trace_events` merge + emissions (`17240-17245+`), `container_entry`
   (`17429-17436`), `remote_setup_schedule` (`17438-17449`).
6. **Contention:** UNET lane worker (fastsafetensors checkpoint read + model
   construction ~6.2-7.4 s total) + ITW warm + prefetch thread all active; the
   prefetch-thread starvation (item 2) is direct evidence of extended saturation.

**Why it is NOT the lane read itself:** the lane submit is fire-and-forget (`bridge
.schedule_execution_unet` returns a bool); the worker's events (wrappers) finish within
~30 ms; no main-thread join or future-wait exists before the seed emit.

**Classification:** ~40 % serial enrichment (items 1, 4), ~30 % trace/context/validation
(item 5), ~30 % GIL contention (items 2/3/6). Of the serial parts: store load is
snapshot-movable; seed derivation is request-derived but deferrable via background thread
(join at `snapshot_seed_consumed`, which is not reached until ~1500 ms in) or per-workflow
cache; `validate_torch_thread_policy` + metadata emissions are smallish but purely
serial bookkeeping.

### 4.2 GAP3 — status-yield → executor-stream head (17 – 206 ms; mean ~117)

`run_plan_first_status_yield` → `pre_sampler_cache_key_build`. Contents: host receives
`plan_received`, calls `__anext__`, Modal gRPC round trip, `guard_remote_cancel_stream`
wrap, `RuntimeExecutor.stream(plan, context)` head (prompt-operations preflight, trace
reuse checks, cache attach). **Entirely platform + executor preamble; R6's 17.1 ms is
likely the floor.** The PreSampler cache-key op itself is 0.002 ms. The 100-200 ms
excess in R2/R5 is host↔Modal resume latency + contention.

### 4.3 GAP2 — request-bound → model-validation checkpoint (3 – 188 ms; mean ~95)

Between `cpu_snapshot_models_request_bound` emit (`modal_app.py:11764-11780`) and
`clip_state_checkpoint("restore_after_snapshot_model_validation")` (`11781-11792`), plus
the checkpoint function itself (`clip_fast_hydration_wiring.py:218-310`: resolve clip,
`clip_hydration_state`, ONE `print(..., flush=True)`, `_emit`). The block after the
checkpoint (retained-identity chain `11878-11915`, invariant `11921`) measures 1.2 ms.
Same ~30 lines produce 187.8 / 92.5 / 3.0 ms across runs ⇒ **not serial work** — the
variance is CPU/GIL (fastsafetensors lane + ITW warm) and a `flush=True` stdout write
under load. The checkpoint + print + identity chain are **diagnostics-only and
deferrable** (the invariant gate at 11921 is the only functional bit).

### 4.4 Legacy preload check (5.4 / 110.9 / 5.9 ms)

`legacy_preload_check_start→end` (`modal_app.py:12625`, interval read at 14055). Waits on
the prefill lane readiness. R5's 111 ms is an outlier — prefill readiness/clip state not
yet settled at check time (contention-dependent); R2/R6 ~5-6 ms. **Deferrable behind
first sampler node** (check outcome is observational; correctness is preserved by
prefill's own readiness gates).

### 4.5 Everything else (inspect-and-dismiss)

| Span | Time | Code | Verdict |
|---|---|---|---|
| Method head (identity, env profile, from_dict, G1 preamble) | 17–32 | 16470-16645 | required; near-floor |
| `cpu_snapshot_clip_vae_bind` | 0.2-2.3 | 11751-11790 | snapshot-served; already bind-only (no loader IO) |
| `runtime_config` + legacy_runtime_load | ~0.05+0.02 | 11418-11421 | required, trivial |
| `unet_execution_schedule` at graph time | 0.2 (no-op) | 11430+ | **G1 design working** |
| Plan proof / D1 consumption | 1.1-2.5 | 13222-13327 area | deferrable (observational) |
| `production_registry_setup` | 0.03-0.06 | 13256-13327 | required, trivial |
| Executor `reset` | 0.05 | 13607 area | required, trivial |
| Generation identity / host memory probes | 0.2-0.4 (request-time) | 16491; `runtime_shape_observed` | host probes run at restore, not request |
| `unet_quiesce_request` → invoke | 2.4 / 2.9 / 58.2 | 13607 | R6 outlier: lane still loading |

---

## 5. Reconciliation with the official waterfall & D11

- `final_reconciled_waterfall.remote_method_setup` = 1722.217 / 1492.731 / 1454.114 —
  matches D11 row 4 (1.722 / 1.493 / 1.454). Status OK, residual −8…+10 ms.
- `prompt_executor_cache_setup` (row 5) = 10.1 / 139.6 / 6.9 — this is exactly
  GAP3 + PreSampler/first-hook region starting from status yield; R5's 139.6 explains
  the row-5 spike.
- `critical_path_metrics` (`method_entry_to_first_remote_event_ms` 1640 / 1404 / 1177)
  measures to the **first remote event** (executor head work), which is why it sits
  ~40-280 ms below the setup total that runs to invoke.
- `schedule_ms` (1248.5 / 1108.9 / 987.8) = the official G1 bracket — internally
  consistent with GAP1 + plan_received tail (1221-1245 ± few).

---

## 6. Component ranking (serial, mean over 3 runs)

1. **GAP1 plan-receipt schedule region — ~1087 ms (63 %)** — biggest serial component.
   Serial core: snapshot-seed derivation (~150-400), signature-store first load
   (~50-200), context/trace/validate (~100-250); remainder GIL contention.
2. **GAP3 stream resume + executor head — ~117 ms (7 %)** — platform floor ~17 ms.
3. **PromptExecutor/cache setup (row 5, GAP3 tail) — ~52 ms mean** (6.9-139.6).
4. **GAP2 bound→validation diagnostics — ~95 ms mean (3-188; zero serial content).**
5. **Legacy preload check — ~41 ms mean (5.4-110.9; deferrable).**
6. Method head 22, quiesce 21, proofs ~10, bind 1.5, reset/prod-registry <0.2.

**BIGGEST_SERIAL_COMPONENT:** GAP1 (plan-receipt schedule region, `modal_app.py:
16647-17449`), dominated by request seed derivation + first store load under lane/ITW
contention. **SECOND_BIGGEST:** the status-yield → executor-stream head block (GAP3 +
row-5 cache setup; `modal_app.py:17452-17464` + `runtime_executor.py` stream preamble),
mean ~169 ms combined.

---

## 7. Movability & best next fix (assessment only)

| Component | Est. (ms) | Movable to | Mechanism |
|---|---|---|---|
| Signature-store first load | 50-200 | **Snapshot/restore** | load at restore-time warmup (module-guarded — call exists) |
| Seed derivation (`build_invocation_seed_payload`+hydrate) | 150-400 | **Background thread at method entry; join at `snapshot_seed_consumed`** (or cache by `workflow_hash` per container) | pure graph analysis, no executor dependency |
| `validate_torch_thread_policy` + trace metadata | 50-150 | post-worker-start (defer to executor head) | replayable metadata |
| GAP2 checkpoint + prints + identity chain | 3-188 | **defer to post-invoke** (observability) | keep only the invariant gate |
| Legacy preload check | 5-111 | post-first-sampler-node (observational) | keep readiness gates |
| Plan proof / validation | ~10 | post-invoke (observational) | keep fail-closed parity path |
| Execution-prefill pool queue (R6) | 0-120 | dedicated prefill pool / priority lane | queued behind UNET fastsafetensors lane |
| ITW warm CPU theft | 100-300 of GAP1/GAP2 | throttle / lower torch threads / start after invoke | concurrent CPU amplification |
| Platform floor (GAP3 resume) | ~17-30 | not movable | Modal transport |

**BEST_NEXT_FIX (one):** move `_derive_request_snapshot_seed` (seed derivation + hydrate)
off the request critical path — background thread launched at method entry, joined at
`snapshot_seed_consumed` (unreachable until ~1.5 s in), plus one-line per-container
`workflow_hash` cache — combined with moving `load_store_from_disk` to restore-time.
This targets the 60-65 % serial core of GAP1 without changing any correctness gate.

**EXPECTED_SAVING_MS:** ~450-700 (seed derivation hidden ~250-400, store load at restore
~50-200, GAP2 diagnostics deferred ~90, legacy check deferred ~40, ITW throttle ~100
secondary). Optimistic setup: 1.45-1.72 s → **~0.65-0.80 s**; confident floor with the
single fix alone: **~1.0-1.2 s**.

---

## 8. Metrics block (final)

```
RUN2_SETUP_MS = 1722.2        # D11 R2 remote method setup
RUN5_SETUP_MS = 1492.7        # D11 R5
RUN6_SETUP_MS = 1454.1        # D11 R6
BIGGEST_SERIAL_COMPONENT = GAP1 plan-receipt schedule region (mean 1087 ms;
  seed derivation + signature-store first load + trace/validate under lane/ITW GIL
  contention); official schedule_ms 1248.5/1108.9/987.8
SECOND_BIGGEST_SERIAL_COMPONENT = status-yield -> executor-stream head block
  (GAP3 17-206 ms + waterfall row-5 cache setup 6.9-139.6 ms; mean ~169 ms)
SNAPSHOT_MOVABLE_MS = ~50-200 (signature-store first load to restore-time)
DEFERRABLE_MS = ~250-700 (seed derivation via background thread+workflow-hash cache
  150-400; GAP2 diagnostics 3-188; legacy preload check 5-111; plan proof ~10;
  prefill pool queue 0-120)
PURE_OVERHEAD_MS = ~60-90 (trace emissions, prints incl. flush=True, method-entry
  syscalls, executor reset, registry setup, status-yield mechanics)
UNATTRIBUTED_MS = ~150-250 (un-instrumented interior of GAP1 serial work split and
  GAP3 host round trip; R5 preload-check 111 ms outlier)
BEST_NEXT_FIX = background-thread seed derivation joined at snapshot_seed_consumed +
  per-container workflow_hash cache; move load_store_from_disk to restore-time
  (GAP1 serial core; no correctness-gate changes)
EXPECTED_SAVING_MS = ~450-700 (setup 1.45-1.72 s -> ~0.65-0.80 s optimistic;
  >= ~250-400 with the single seed-derivation fix alone)
CONFIDENCE = High for structure/attribution (same-clock trace + source-verified
  emitters + waterfall reconciliation residual <10 ms; GAP1/GAP2 interior splits
  are estimates)
FILES_CHANGED = report only (V2_BATCH_D13_REQUEST_ENTRY_SETUP_FORENSICS.md)
MODAL_DEPLOYS = 0
MODAL_REQUESTS = 0
COMMIT = none
STOP
```