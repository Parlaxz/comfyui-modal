# V2 — Result Handoff, Python Restore, and Remote Setup: Remaining-Cost Research

Date: 2026-08-13 (following `V2_10_COLD_RUNS_35S_COOLDOWN.md`, deployment `b557b2401f293223`, RTX PRO 6000 / 12 CPU / 32768 MB, PNG level 1, 10 cold runs, 35 s gap)

Scope: READ-ONLY investigation. No code changed, no deployment, no generation. Revision 2 corrects the stage-14 boundary accounting, quantifies terminal cleanup from existing evidence, reclassifies frozen-VRAM and the Volume-reload skip, and rebuilds the optimization budget conservatively.

Evidence bases: working-tree source (`comfymodal_runtime/modal_app.py`, `runtime_bootstrap.py`, `modal_transport.py`, `runtime_executor.py`, `model_preload.py`, `output_delivery.py`, `result_delivery.py`, `canonical_execution.py`, `comfyapp.py`, `restore_memory_arm.py`, `__init__.py`), the 10-run log `v2_c2f_10cold_35gap.log` (per-run timing JSON + `restore_breakdown`), `docs/v2-single-use-container-teardown.md`, `V2_EXCLUSIVE_OWNER_TOTAL_WALL_6_RUN_REPORT.md`, `V2_SINGLE_INVOCATION_PLAN_EXECUTION_REPORT.md`, `V2_FINAL_OPTIMIZATION_AB_RESULTS.md`, `V2_STEP3_PERSISTENT_IPC_TRANSPORT_ACCEPTANCE.md`, `V2_PRODUCTION_DEFAULTS_2026-08-13.md`, `V2_GRAPH_CERT_SETUP_DECOMPOSITION.md`, `V2_VARIANCE_COLD_AB_REPORT.md`, and the N=1 frozen-arm validation artifact `runs/v2_2026-08-13_04-02-15/run_001_validation_discard.json`.

---

## 1. Executive summary

The three remaining stages account for roughly 1.8 s of median wall (handoff ~0.98 s + Python restore ~0.62 s + setup ~0.19 s). After the correction pass, the accounting is:

| Stage | Median-ish cost | Proven removable (measured) | Plausible removable | Status |
|---|---|---|---|---|
| 1. Remote result handoff | ~976 ms (GCP), 1302 ms (AWS) | **~0–30 ms** (terminal cleanup in-window is near-zero in the benchmark config) | 30–100 ms pre-stamp (stage-13 attributed); 200–600 ms direct-return **unproven** | Mostly platform transport; needs 2 new stamps to prove app-side content |
| 2. Python restore | 610 ms (385–1533) | **~179 ms median** (Volume reloads: 97.0 models + 81.9 runtime-state) | +variance flattening | Models reload: READY; runtime-state: guard first |
| 3. Remote method setup | ~190 ms (124–806) | 0 (stage 6 already tiles with zero residual) | ~10 ms | ALREADY SOLVED at existing granularity |

**Stage-14 boundary correction (Issue 1):** the emit stamp (`modal_app.py:16710`) is taken **after** the entire enrichment block (trace merge, waterfall, `full_trace_artifact`, raw_timestamps, clock_scopes, gpu_allocation — all at `:16338-16704`) and immediately before the inner yield (`:16716`). Therefore all enrichment is **pre-stamp** work attributed to stage 13 ("Output encode / descriptor"), NOT inside `remote_result_emit_to_local_receipt_ms`. The measured window contains only: inner yield → outer-wrapper receive → terminal cleanup (`:15612`) → outer yield (`:15616`) → Modal platform delivery → host receipt. In the benchmark cohort the in-window cleanup is **near-zero** (see Issue 2), so the ~976 ms is overwhelmingly **unobserved Modal transport time**, not application work.

**Terminal cleanup (Issue 2):** in the 10-run cohort `COMFYMODAL_V2_RELEASE_GPU_AFTER_REQUEST=0` (`v2_c2f_10cold_35gap.log`), so `_release_gpu_after_request` was skipped entirely, and `_run_pending_production_cleanup` was a no-op (the pending record is stashed only in the inner generator's `finally`, which has not run while it is suspended at `:16716`). Measured in-window cleanup ≈ 0 ms; the only documented teardown datapoint is the exit hook ≈ 30 ms (`docs/v2-single-use-container-teardown.md:24`). Per-stage cleanup timing was never captured (`COMFYMODAL_V2_TEARDOWN_DIAGNOSTICS` off in all runs) — UNKNOWN beyond that.

**Frozen-VRAM (Issue 5):** PHASE-SHIFT ONLY. Measured N=1: `restore_gpu_state_ms` 194–1317 → 4.13, but `cuda_init_ms` 4.2 → 242.9; the stage pair is invariant (~247 vs ~260 ms). TOTAL WALL impact UNRESOLVED (no controlled A/B — the deploy-2 cohort was stopped on a wiring bug). Do **not** enable by default.

**Volume reloads (Issue 6):** `reload_models` (median 97.0 ms) is SAFE TO SKIP WITH EXISTING IDENTITY (`models_generation.json` + `_should_reload_models_volume` exist but the V2 bootstrap path ignores them). `reload_runtime_state` (median 81.9 ms) is SAFE WITH NEW GUARD (no writers between capture and request when `COMFYMODAL_V2_PUBLISH_RESTORE_PLAN=0`, but mounts can lag — the frozen-capacity file proved it). Combined ~179 ms median, the largest **proven** removable on the critical path.

**Direct-return (Issue 4):** PLAUSIBLE BUT UNPROVEN. No clean direct-RPC baseline exists (publish_restore_plan numbers are cold-start-tainted; `read_output_asset` unmeasured; the only clean transport numbers are 16–31 ms local submission and the ~976 ms streaming handoff itself). Excluded from the budget.

**Setup (Issue 7):** stage 6 is already closed — `method_entry_to_graph_start` + `graph_setup` tile `modal_method_entry_to_executor_ms` with residual ≈ 0 on all 10 runs. Interior splitting of `graph_setup` is possible from existing full-artifact stamps (6 timestamps need surfacing into the per-run JSON). No new batch needed.

**Conservative budget:** proven ≈ 179 ms (Volume reload skip, models part alone ~97 ms); plausible additional ≈ 30–100 ms (pre-stamp enrichment trim, stage-13 attributed) + variance flattening (frozen-VRAM A/B) + cleanup measurement. Median 15.58 s → ~15.2–15.4 s proven; sub-14 s requires the unproven handoff levers (instrumentation + direct-return experiment) and/or out-of-scope pre-sampler items (ImpactSwitch 0.55–0.74 s, checkpoint read 1.1–1.7 s).

---

## 2. Result handoff exact timeline

### 2.1 Measured evidence (10 cold runs, `v2_c2f_10cold_35gap.log`)

Stage 14 "Remote result handoff" is byte-identical to the in-repo field `remote_result_emit_to_local_receipt_ms`:

| Run | Provider | Handoff (ms) | `output_collection_ms` | Envelope bytes |
|---|---|---|---|---|
| 1 | GCP/us-east4 | 1036.9 | 9.2 | 2208–2220 |
| 2 | GCP/us-east4 | 994.3 | 8.7 | ~2200 |
| 3 | GCP/us-east1 | 1032.3 | 9.4 | ~2200 |
| 4 | GCP/us-east4 | 967.9 | 9.5 | ~2200 |
| 5 | GCP/us-east4 | 963.1 | 8.2 | ~2200 |
| 6 | GCP/us-east1 | 1029.7 | 7.6 | ~2200 |
| 7 | AWS/eu-south-2 | 1302.1 | 9.6 | ~2200 |
| 8 | GCP/us-east4 | 971.6 | 7.6 | ~2200 |
| 9 | GCP/us-east4 | 975.5 | 7.5 | ~2200 |
| 10 | GCP/us-east4 | 976.2 | 7.0 | ~2200 |

GCP min 963.1, median ≈ 975.8, max 1036.9; AWS +330 ms. Envelope is descriptor-only JSON (no PNG bytes; `use_descriptors=True`, `include_base64=False`). All 10 runs used the persistent-IPC path (`decision=persistent_hit`, `handle_lookup_ms=0.0`) — the ~1 s is the streaming round-trip itself, not handle lookup or V1-vs-V2 artifacts.

### 2.2 Exact boundary classification (Issue 1)

Verified ordering in `modal_app.py` + `canonical_execution.py`. Every item classified:

| # | Item | File:line | Class |
|---|---|---|---|
| 1 | Output collection (`pop_outputs`, DirectOutputSink attempt) | `modal_app.py:13743-13787` | **A** — pre-stamp |
| 2 | Asset local write (`_persist_output_assets`, sync container-local disk write; commit fired async, unawaited) | `modal_app.py:14426-14517` | **A** — pre-stamp |
| 3 | Descriptor construction (`attempt_to_descriptor_result`) + `serialized_result_bytes` measure | `output_delivery.py:295-385`, `modal_app.py:13944-13954` | **A** — pre-stamp |
| 4 | Envelope enrichment: trace merge, identity enrichment, `_restore_timing` | `modal_app.py:16338-16427` | **A** — pre-stamp |
| 5 | Envelope enrichment: `raw_timestamps`, `intervals_ms`, `clock_scopes` | `modal_app.py:16526-16577` | **A** — pre-stamp |
| 6 | `full_trace_artifact` construction (`asyncio.to_thread` volume write when full-trace enabled) | `modal_app.py:16622-16644` | **A** — pre-stamp (gated; envelope size proves off in cohort) |
| 7 | `resource_telemetry`, `gpu_allocation`, **waterfall construction + attach** | `modal_app.py:16646-16704` | **A** — pre-stamp |
| 8 | **`_stamp_remote_result_emit`** — window start | `modal_app.py:16710-16715` | **B** — boundary |
| 9 | Inner `yield event` (terminal result) | `modal_app.py:16716` | **B** — adjacent, sub-ms |
| 10 | Outer wrapper receive + terminal detection + `request_terminal_start` | `modal_app.py:15600-15611` | **C** — in-window |
| 11 | `_run_terminal_cleanup_sync`: `_run_pending_production_cleanup` (no-op — record not yet stashed) + `_release_gpu_after_request` (skipped when `COMFYMODAL_V2_RELEASE_GPU_AFTER_REQUEST` falsy) | `modal_app.py:15612-15615` (`:15506`, `:15510`, gate `:5473`) | **C** — in-window; **≈0 ms in cohort** |
| 12 | Outer `yield event` | `modal_app.py:15616` | **C** — in-window |
| 13 | Modal SDK serialization (~2.2 KB) + platform transport + host event dispatch | (SDK, unobserved) | **C** — in-window, unobserved |
| 14 | Host receipt stamp (`local_result_received`) — window end | `canonical_execution.py:2164-2170` | **C/D** — boundary |
| 15 | Stream `aclose()` → background persistence drain | `canonical_execution.py:2155`, `modal_transport.py:1175` | **D** — post-receipt, off-path |
| 16 | Remote generator tail: `_finalize_deferred_commit` + `persistence` event | `modal_app.py:16718-16741` | **D** — post-receipt (host already broke out; drained in background) |
| 17 | Host merge/interval math, `execute_plan_return`, caller return (stage 15 = 15–16 ms) | `canonical_execution.py:2172-2994`, `__init__.py:2486-2541` | **D** — post-receipt |

**Consequences:**
- All enrichment (items 4–7) is **pre-stamp** → its optimization reduces stage 13 ("Output encode / descriptor", 236–261 ms in cohort) and TOTAL WALL, but must NOT be credited to stage 14.
- The only application code inside the stage-14 window is item 11 (cleanup, ≈0 ms in cohort) plus sub-ms event-loop hops (items 9–10, 12).
- Stage-14 savings from application code are therefore bounded by cleanup cost — near-zero in the current production config.

---

## 3. Modal transport mechanics

- `ModalTransport.run_plan_stream` (`modal_transport.py:627-1182`): `handle.run_plan_stream.remote_gen.aio(...)` (`:823`, persistent-IPC `:814`, retries `:838-876`); first `__anext__` at `:958`; events re-yielded verbatim (`:1125, :1151`); `final_result_received` + waterfall attach on result (`:1112-1125`).
- No application-level chunking/framing — the Modal SDK streams serialized dicts over gRPC; the only size signals are `serialized_result_bytes` (~2.2 KB) and request `payload_bytes` (~19.3 KB).
- Stream-close is already off-path: host `aclose()` (`canonical_execution.py:2155`) spawns a shielded background drain (`modal_transport.py:1175`, `:138-181`) joined only at teardown; remote generator tail (deferred commit + `persistence` event) runs after the host has the result.

### Direct-return possibility (Issue 4 — analysis only, NOT implemented)

A Modal method is either a generator or a plain function; a direct terminal would require two methods (progress stream + `get_result` RPC) or a non-generator result fetch. Building blocks exist (`publish_restore_plan` pattern `modal_transport.py:1240-1342`; `read_output_asset` `modal_client.py:598-609` / remote `modal_app.py:14657-14679`).

**Evidence check against a second RPC:**
- `publish_restore_plan` measured 74–188 s — **cold-start/snapshot-build tainted** (the publish invocation cold-started and built the snapshot); explicitly "historical references only (NOT a same-cohort A/B)" (`V2_SINGLE_INVOCATION_PLAN_EXECUTION_REPORT.md:64-65, 108, 242-248`). Not usable.
- `read_output_asset`: no measured timings anywhere (fires only when `auto_save_local=True`; bounds are 3 retries / 0.25–0.5 s sleeps / 120 s timeout). UNKNOWN.
- Step-3 persistent IPC: host-reconciled global residual 0.88 ms; local submission overhead `local_receive_to_actual_submission_ms` 16–31 ms clean; `generator_create_ms` 1–2 ms.
- The ~976 ms streaming handoff already runs on the persistent-hit path.

A second RPC would itself incur submission, router/scheduler path, RTT, plus progress-stream/result-store synchronization and new race/error semantics. The only clean data point (16–31 ms local submission) says submission is cheap, but the remote-side delivery cost of a direct RPC is unmeasured — it could be far below or above 976 ms.

**Ranking: PLAUSIBLE BUT UNPROVEN. Do not count its savings toward the optimization budget.**

---

## 4. Host receive path

- `execute_plan` (`canonical_execution.py:1372-2995`): `async for` (`:2139`); error → raise (`:2143`); result → capture + `break` (`:2145-2147`); `finally` → awaited `aclose()` (`:2155`, background drain).
- `local_result_received` (`:2164-2170`) ends the handoff window (class D starts here).
- Post-receipt host CPU (merge, intervals, waterfall attach) is inside stage 15 (15–16 ms) — negligible.
- `auto_save_local` (if enabled) adds a `read_output_asset` RPC after receipt — verify off in wall-time runs.

---

## 5. Handoff optimization candidates (corrected)

1. **Terminal cleanup deferral** (`modal_app.py:15612`): in the benchmark/production config (`COMFYMODAL_V2_RELEASE_GPU_AFTER_REQUEST=0`) the in-window cleanup is already a no-op — **deferral saves ≈ 0 ms in this config**. It only matters if GPU release is enabled (then the ~30 ms exit-hook-scale cost lands in-window). Value: near-zero; still worth the 2-stamp instrumentation (below) to prove it.
2. **Pre-stamp enrichment trimming** (`modal_app.py:16338-16704`): reduces stage 13 and TOTAL WALL (delays the yield), NOT stage 14. Envelope is only ~2.2 KB in the cohort, so trace merge + waterfall + interval math are the cost; `full_trace_artifact` is gated (off in cohort). Plausible 30–100 ms TOTAL WALL win, requires a stage-13 sub-split to prove; low risk (make waterfall/trace lazy or flag-gated).
3. **Direct-return/two-method**: PLAUSIBLE BUT UNPROVEN (see §3). Prototype + measure before any budget credit.
4. **Keep:** descriptor-only delivery, off-path commit, immediate host break + shielded `aclose` — all already correct.
5. **Instrumentation (the actual next step):** two always-on stamps, following the `_stamp_remote_result_emit` pattern, riding in `event["data"]`:
   - `terminal_cleanup_start_wall/mono_ns` at `modal_app.py:15603` (terminal event received, before cleanup);
   - `terminal_cleanup_end_wall/mono_ns` at `:15615` (after `_run_terminal_cleanup_sync`, immediately before the outer yield).
   Derived: `remote_cleanup_ms` (same-process mono diff) and `transport_ms` (`local_result_received_wall − terminal_cleanup_end_wall`). Two stamps fully separate cleanup from platform transport; no new host code needed. <1 ms overhead.

---

## 6. Handoff expected savings (corrected)

Measured window `remote_result_emit → local_result_received` ≈ 975.8 ms GCP median:

- **MEASURED APPLICATION TIME in-window:** item-11 cleanup ≈ 0 ms (release gate off) + sub-ms event-loop hops. Total measured app time ≈ **<5 ms**.
- **MEASURED NETWORK/REGION EFFECT:** AWS − GCP ≈ +330 ms (region-dependent component).
- **UNOBSERVED MODAL TRANSPORT TIME:** ≈ **~970 ms GCP** (SDK serialization + platform delivery + host dispatch; no stamps exist between outer yield and receipt).
- **INFERENCE (explicitly labeled):** no Modal-internal mechanism (finalization handshake, stream teardown, polling) is asserted — there is no source/timestamp evidence for any specific mechanism. The only provable statement is: *remote actual-yield vicinity → host receipt ≈ ~976 ms with a ~2.2 KB payload, of which application code is <5 ms and the remainder is unobserved platform time.*

Savings: minimum plausible **~0–30 ms** (cleanup, config-dependent); likely **30–100 ms** (pre-stamp trim, credited to stage 13, TOTAL WALL win); maximum plausible **200–600 ms** (direct-return) — **unproven, not budgeted**. The previous 300–500 ms stage-14 claim is withdrawn.

---

## 7. Python restore decomposition

Measured field: `restore_total_ms` (`modal_app.py:10593-10641`), window `_restore_perf_start` (`:9187`) → finalize (`:10587`). Python-side only; pre-Python snapshot restore is a separate platform stage (`v2_waterfall.py:959-962`).

Per-run `restore_breakdown` from the 10-run log (ms):

| Run | restore_total | restore_gpu_state | cuda_init | reload_models | reload_runtime_state | TOTAL WALL (s) |
|---|---|---|---:|---:|---:|---:|
| 0 | 385.3 | 194.4 | 4.16 | 68.7 | 83.3 | 17.0 |
| 1 | 618.2 | 422.8 | 4.17 | 88.5 | 71.5 | 17.1 |
| 2 | 468.8 | 183.3 | 3.89 | 116.8 | 128.8 | 41.3 |
| 3 | 1532.5 | 1317.5 | 4.88 | 90.3 | 80.6 | 28.8 |
| 4 | 528.4 | 282.0 | 3.95 | 98.2 | 76.4 | 21.3 |
| 5 | 601.8 | 262.7 | 4.18 | 103.1 | 150.5 | 18.0 |
| 6 | 953.7 | 221.9 | 3.41 | 388.2 | 263.8 | 78.9 |
| 7 | 942.0 | 249.0 | 2.62 | 69.6 | 77.2 | 16.5 |
| 8 | 1075.1 | 729.3 | 5.05 | 98.7 | 164.5 | 18.4 |
| 9 | 460.4 | 248.7 | 4.55 | 95.8 | 74.3 | 15.7 |
| **median** | **610.0** | **255.9** | **4.17** | **97.0** | **81.9** | — |

(Matches the waterfall's Python-restore distribution 387–1535 / median 616; minor boundary rounding. `sync_custom_nodes_ms` in the log is a construction-carried startup stage, NOT a per-restore cost — restore-time custom-node sync is `snapshot_exact_skip`, `callback_called=0`.)

In-window ordered work (`[v2.restore_breakdown]` `modal_app.py:10680-10688`, `[v2.restore_deep]` `:10698-10736`, `opt_restore_decomposition` `runtime_bootstrap.py:2006-2070`):

| # | Step | Loc | Class |
|---|---|---|---|
| 1 | Host memory probe + cgroup sampler start | `modal_app.py:9204-9211` | consistent, ~2–10 ms |
| 2 | Identity capture (`modal.current_input_id()`) | `:9226/:1879-1889` | variable, ~1–20 ms |
| 3 | `_configure_runtime()` (short-circuits on restored instance) | `:9235/:7514-7515` | consistent, ~0 |
| 4 | Torch thread limit apply | `:9298/:8854` | consistent, ~1–5 ms |
| 5 | `bootstrap.restore()` — dominant block | `:9422`, `runtime_bootstrap.py:1589` | variable |
| 5a | **restore_gpu_state** (`restore_gpu_state_ms`) — `torch.cuda.mem_get_info()` = first CUDA touch | `:1658-1667`, `comfyapp.py:20363-20404` | **variable, 183–1317 ms** |
| 5b | **initialize_cuda** (`cuda_init_ms`) — unconditional `torch.cuda.synchronize` | `:1669-1687`, `comfyapp.py:18812-18833` | consistent, 2.6–5.1 ms (baseline) |
| 5c | Sage identity verify (exact-skip) | `:1689-1774` | consistent, ~1–10 ms |
| 5d | **reload_runtime_state** — Volume `reload()` RPC | `:1776-1785`, `modal_app.py:7546` | **variable, 71.5–263.8 ms** |
| 5e | **reload_models** — Volume `reload()` RPC | `:1787-1796`, `modal_app.py:7541` | **variable, 68.7–388.2 ms** |
| 5f | custom-node identity check (O(1), exact-skip) + sync (skip) | `:1817-1902` | consistent, ~1–5 ms |
| 5g | snapshot_seed (minimal; publish-plan off) | `:1946-1979` | consistent, ~1–5 ms |
| 6 | CPU-snapshot activation (retarget/validation; gated) | `modal_app.py:9593-10325` | variable, 50–400 ms |
| 7 | Preload bridge prep (`close_workers()` wait; skipped on CPU-snapshot path) | `:10341-10567`, `model_preload.py:8967, 10164-10218` | variable; dominant tail when active |
| 8 | Finalization + packaging + return marker | `:10574-10843` | consistent, ~5–20 ms |

## 8. Python restore variance

The 385→1533 ms spread is explained by measured per-run fields:

1. **`restore_gpu_state` (183–1317 ms, median 255.9)** — the `mem_get_info()` first-CUDA-touch; dominates the spread. Note: it is ALSO the CUDA context initializer, so removing it phase-shifts context-init into `cuda_init` (see Issue 5 / §9).
2. **`reload_models` (68.7–388.2, median 97.0)** and **`reload_runtime_state` (71.5–263.8, median 81.9)** — two network RPCs; run 6 (388/264) is the tail driver.
3. **CPU-snapshot activation + preload bridge** — variable 50–400 ms; dominant tail when the CPU-snapshot path does not activate.
4. Identity capture + scheduler/process noise — small.

Consistent floor ≈ 50–120 ms (items 1,3,4,5b,5c,5f,5g,8). Known confound: enabling variance diagnostics + pretouch added ~53% to restore (A 896.6 vs B 1373.4 ms, `V2_VARIANCE_COLD_AB_REPORT.md:50-51`).

## 9. Python restore candidates (corrected)

1. **Volume reload skip — models (`reload_models`)**: **SAFE WITH EXISTING IDENTITY.** The models volume already has a generation record (`models_generation.json` + `_should_reload_models_volume`, `comfyapp.py:20415`), but the V2 bootstrap path calls `vol.reload()` unconditionally (`modal_app.py:7541-7544`, invoked at `runtime_bootstrap.py:1787-1796`). In the single-use protocol nothing writes the models volume between snapshot capture and request (deploy-time writes only). Guard the reload with the existing generation compare (O(1) local file read — no RPC). **Measured saving: median 97.0 ms/run.**
2. **Volume reload skip — runtime-state (`reload_runtime_state`)**: **SAFE WITH NEW GUARD.** No external writer runs between capture and request when `COMFYMODAL_V2_PUBLISH_RESTORE_PLAN=0` (default; host publisher off). But the restored mount CAN lag: the frozen-VRAM construction restore did not see the freshly written `gpu_capacity_frozen.json` until a reload (`V2_FINAL_OBSERVABILITY_AND_RESTORE_COMPLETION.md:49`) — so skipping unconditionally is NOT safe. Write a construction-time `runtime_config_generation` marker (alongside `gpu_capacity_frozen.json`), compare at restore (O(1) read). Caveat: the cert-path 900 s reload-dedup marker (`_RUNTIME_STATE_VOLUME_RELOADED_MONO`) precondition must be re-checked. **Measured saving: median 81.9 ms/run.** Combined with #1: **~179 ms median.**
3. **Frozen-VRAM (`COMFYMODAL_V2_RESTORE_TOTAL_VRAM_FROZEN`)**: **PHASE-SHIFT ONLY — do NOT enable by default.** N=1 measured: `restore_gpu_state_ms` 194–1317 → 4.13, but `cuda_init_ms` 4.17 → 242.91 (`sync_ms` 177.9–208.9 frozen vs 1.6–5.0 baseline); stage pair invariant (~247 vs ~260 ms). It flattens the gpu_state spread (variance benefit) but does not remove the ~240 ms context-init. TOTAL WALL impact UNRESOLVED — the deploy-2 A/B was stopped by a wiring bug (state-volume root not baked; `frozen_capacity_path()` empty → arm fell back to baseline) and never re-run; the only active-arm run is an unpaired validation/discard. Needs a paired A/B reporting `gpu_state+cuda_init` as the stage-pair metric.
4. **CUDA synchronize adjustment**: **REJECT.** Baseline `cuda_init` is 2.6–5.1 ms (median 4.17) — the earlier "10–200 ms" figure belonged to the frozen arm where context-init relocates into the sync. The sync is cheap in the baseline because `mem_get_info` already initialized the context; skipping it saves ~4 ms and would not reduce total wall (implicit sync before first GPU use anyway).
5. **Diagnostics gating**: keep expensive breakdown prints behind `COMFYMODAL_V2_OPTIMIZATION_DIAGNOSTICS` (already the pattern; verify nothing unconditional remains in `:10664-10843`).

## 10. Remote method setup decomposition

Stage 6 in the 10-run data: 124.6–806 ms (AWS outlier 806.1; GCP median ≈ 190 ms). Two sub-rows tile it exactly:

- `method_entry_to_graph_start` (84.5–258.9 ms GCP, 633.6 AWS; median ≈ 137 ms) = `remote_method_entry` → `graph_execution_start` (`modal_app.py:13486`).
- `graph_setup` (36.8–390.8 ms; median ≈ 51.5; run-0 outlier 390.8 dominated by `cpu_snapshot_models_retargeted` ≈ 205.7 + wrapper installs) = `graph_execution_start` → `prompt_executor_invoke_start` (`modal_app.py:13485`).

Verified: `entry_to_graph + graph_setup == modal_method_entry_to_executor_ms` on all 10 runs (residual ≈ 0). The three >100 ms items (certificate 150.7, preflight 145.1, `validate_prompt` 149.1) are already eliminated on the Step-3 fast path (`decision=plan_validation_fast_path consumed=1`, 0 RPCs, `V2_STEP3_PERSISTENT_IPC_TRANSPORT_ACCEPTANCE.md`). PromptExecutor/cache setup (stage 7) is solved at 5–17 ms; conditioning exact-hit 34–95 ms; PNG encode 163–180 ms.

## 11. Setup candidates (corrected)

1. **Residual: already closed at existing granularity** — entry→graph + graph_setup tile stage 6 with zero residual. What remains unattributed is the **interior of graph_setup**, which `pre_sampler_stages` already splits into named children (certificate/preflight/validation/pregraph_setup/executor_reset/residual_before_invoke/invoke_to_execution/cached_to_first_node) in the **full run artifacts** (`runs/v2_2026-08-13_23-06-56/run_N.json`, 764 KB, 437 events) — the small per-run timing JSON just drops them. **No new batch needed.**
2. **Minimal stamp surfacing (6 timestamps, all already emitted as trace events)** — copy into the per-run timing dict: `plan_received` (run_plan_first_status_yield), `seed_derived` (snapshot_seed_request_derived), `trace_ready` (run_plan_trace_setup_end), `graph_execution_start`, `cpu_snapshot_retargeted`, `prompt_executor_invoke_start`. This closes the log-level attribution of the ~137 ms entry→graph window (currently dominated by trace construction/prints + identity + plan deserialize).
3. **CPU-snapshot binding memo (derive keys/role-match per workflow_hash, `modal_app.py:10926-11100`)**: ~5–10 ms — below the sub-50 ms bar; **skip** unless the surfaced stamps show otherwise.
4. **Do not touch:** fast-path trust gate (`:11999-12106`), memoized signature/topo machinery (already hitting on all 10 runs).

---

## 12. Ranked remaining wins (conservative budget)

| Candidate | Current exposed cost | Proven removable | Plausible removable | End-to-end evidence | Confidence | Needs instrumentation | Implement now? |
|---|---|---|---|---|---|---|---|
| Volume reload skip — models | 97.0 ms median inside restore_total | **97.0 ms** (measured per-run) | up to 388 ms tail | per-run `reload_models_ms` ×10; generation record exists (`comfyapp.py:20415`); no writers between capture/request | High | No (guard exists, unused) | **YES** |
| Volume reload skip — runtime-state | 81.9 ms median inside restore_total | — (guard missing) | 82 ms + 264 ms tail | per-run `reload_runtime_state_ms` ×10; no writers when publish off; mount-lag proven (frozen-capacity case) | Medium | Yes — new construction-time marker + cert-dedup precondition check | MEASURE FIRST |
| Pre-stamp enrichment trim | inside stage 13 (236–261 ms total) | — | 30–100 ms TOTAL WALL (stage-13 attributed) | code ordering verified (all pre-stamp); cohort envelope only 2.2 KB → trace/waterfall math is the cost | Low–Medium | Yes — stage-13 sub-split stamps | MEASURE FIRST |
| Terminal cleanup deferral | ~0 ms in cohort (release gate off) | ~0 | 30 ms if GPU release enabled | log line `release_gpu_after_request=0`; teardown doc exit-hook ≈30 ms | High | Yes — 2 stamps (`:15603`/`:15615`) | MEASURE FIRST (stamps only; deferral value ≈0) |
| Direct-return / two-method | n/a | — | 200–600 ms (unproven) | no clean direct-RPC baseline; publish numbers cold-start-tainted; read_output_asset unmeasured | Low | Yes — prototype + A/B | MEASURE FIRST (experiment; no budget credit) |
| Frozen VRAM | 183–1317 ms gpu_state (median 255.9) | 0 net (phase-shift) | variance flattening only | N=1: gpu_state+cuda_init ≈247 vs ≈260 invariant; TOTAL WALL A/B never collected (deploy-2 wiring bug) | High (shift) / Low (wall win) | Yes — paired A/B, stage-pair metric | MEASURE FIRST; do NOT enable by default |
| CUDA synchronize adjustment | 4.17 ms median | 0 | 0 | per-run `cuda_init_ms` ×10 | High | No | **REJECT** |
| Setup residual (entry→graph interior) | residual 0 at stage-6 granularity; interior ≈50–100 ms trace/prints | 0 | ~10–50 ms (trace/print trim, low value) | tiling verified ×10; `pre_sampler_stages` exists in full artifacts | High | Yes — surface 6 existing stamps | MEASURE FIRST (stamps only) |
| CPU-snapshot binding memo | ~5–10 ms | — | ~5–10 ms | code trace | Medium | No | **REJECT** (sub-50 ms) |

No speculative maxima are combined. **Proven budget: ~97 ms; plausible additional: ~30–180 ms; unproven: 200–600 ms (direct-return) + variance flattening (frozen A/B).**

---

## 13. Recommended implementation order

1. **Volume reload skip — models (READY, ~97 ms median):** guard `vol.reload()` at `runtime_bootstrap.py:1787-1796` / `modal_app.py:7541-7544` with the existing `models_generation.json` compare. Re-run the 10-run 35 s-gap batch.
2. **Volume reload skip — runtime-state (MEASURE FIRST):** add construction-time `runtime_config_generation` marker; compare at restore; verify the cert-path 900 s dedup precondition (`_RUNTIME_STATE_VOLUME_RELOADED_MONO`) still holds when the reload is skipped. (~82 ms median.)
3. **Handoff instrumentation (2 stamps, ~1 h of work):** `terminal_cleanup_start/end` at `modal_app.py:15603/:15615`; next batch reports `remote_cleanup_ms` and `transport_ms` — this decides whether any stage-14 lever beyond cleanup exists.
4. **Pre-stamp enrichment trim:** add stage-13 sub-split (or reuse surfaced stamps); trim trace/waterfall build if shown >50 ms; credit to TOTAL WALL, not stage 14.
5. **Frozen-VRAM paired A/B (once 1–2 land):** report `gpu_state+cuda_init` stage pair + restore_total + TOTAL WALL; enable only on measured NET WIN.
6. **Direct-return prototype:** only if step 3 shows transport ≈ 950+ ms with cleanup ≈ 0 (i.e., platform-dominated) AND the experiment is budgeted separately; never counted toward the main budget.
7. Re-rank with fresh medians; then decide whether out-of-scope pre-sampler items (ImpactSwitch 0.55–0.74 s, checkpoint read 1.1–1.7 s, H2D 2.2–2.5 s) must join the sub-14 plan.

---

## 14. Implementation-ready conclusions

Per candidate, exactly one status:

| Candidate | Status | Basis |
|---|---|---|
| Volume reload skip — models | **READY** | Cost (97 ms median) inside restore_total on cold-run critical path; removal changes total wall; generation-identity semantics understood (`models_generation.json` compare, O(1) local read); savings measured per-run |
| Volume reload skip — runtime-state | **MEASURE FIRST** | Measured cost (82 ms) but correctness guard (new construction marker + cert-dedup precondition) not yet built/validated |
| Pre-stamp enrichment trim | **MEASURE FIRST** | Real TOTAL WALL candidate (stage-13 attributed) but un-split in current logs; needs sub-split stamps before claiming |
| Terminal cleanup deferral | **MEASURE FIRST** (value ≈0 in current config) | In-window cost ≈0 with release gate off; 2 stamps first to prove config-dependent value |
| Direct-return / two-method | **MEASURE FIRST** (experiment, no budget credit) | No clean baseline; plausible but unproven |
| Frozen VRAM | **MEASURE FIRST** (A/B; do NOT enable by default) | Phase-shift only per N=1; TOTAL WALL UNRESOLVED |
| CUDA synchronize adjustment | **REJECT** | 4.17 ms median; phase-shifts with frozen arm; net ≈0 |
| CPU-snapshot binding memo | **REJECT** | ~5–10 ms; sub-50 ms bar |
| Setup residual (stage-6 attribution) | **ALREADY SOLVED** | Tiles with zero residual; interior split available from existing full-artifact stamps |
| PromptExecutor/cache setup, conditioning exact-hit, PNG encode | **ALREADY SOLVED** (per original baseline) | 5–17 ms / 34–95 ms / ~170 ms measured |

READY = 1 (models reload skip, ~97 ms). Everything else of value is MEASURE-FIRST with cheap, already-specified instrumentation. The research lane is complete; the outstanding items are implementation-phase (stamps, guards, one A/B), not research.

---

## Sources

- `V2_10_COLD_RUNS_35S_COOLDOWN.md` (baseline tables, metrics, distributions)
- `v2_c2f_10cold_35gap.log` (per-run timing JSON: `remote_result_emit_to_local_receipt_ms`, `output_collection_ms`, `restore_breakdown` fields, `release_gpu_after_request`, persistent-hit decisions)
- `docs/v2-single-use-container-teardown.md` (exit hook ≈ 30 ms)
- `V2_EXCLUSIVE_OWNER_TOTAL_WALL_6_RUN_REPORT.md` (output persistence 593–601 ms, pre-stamp)
- `V2_SINGLE_INVOCATION_PLAN_EXECUTION_REPORT.md` (publish RPC 74–188 s, cold-start-tainted; removed by design)
- `V2_FINAL_OPTIMIZATION_AB_RESULTS.md`, `V2_FINAL_OBSERVABILITY_AND_RESTORE_COMPLETION.md` (frozen-VRAM deploy-2 wiring bug; mount-lag evidence), `runs/v2_2026-08-13_04-02-15/run_001_validation_discard.json` (N=1 frozen run)
- `V2_STEP3_PERSISTENT_IPC_TRANSPORT_ACCEPTANCE.md` (fast path, 0 RPCs, residual 0.88 ms)
- `V2_PRODUCTION_DEFAULTS_2026-08-13.md`, `V2_GRAPH_CERT_SETUP_DECOMPOSITION.md`, `V2_VARIANCE_COLD_AB_REPORT.md`
- Working-tree traces: `comfymodal_runtime/modal_app.py`, `runtime_bootstrap.py`, `modal_transport.py`, `runtime_executor.py`, `model_preload.py`, `output_delivery.py`, `result_delivery.py`, `canonical_execution.py`, `comfyapp.py`, `restore_memory_arm.py`, `__init__.py`
