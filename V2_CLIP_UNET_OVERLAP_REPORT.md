# V2_CLIP_UNET_OVERLAP_REPORT

V2 execution-phase CLIP prefill ↔ native fast-disk UNET preparation overlap.

- **Date:** 2026-08-12 (UTC+7 local)
- **Config:** integrated — UNET-absent clip_vae CPU snapshot, native fast-disk UNET, exact-conditioning cache, critical prefill lanes, `COMFYMODAL_SAMPLING_DEEP_PROFILE=blocks`
- **Shape:** RTX PRO 6000 / CPU 12 / RAM 32768 MiB, provider+region unpinned (GCP, 3 different regions observed)
- **Baseline:** `REAL_CLIP_CACHE_MISS_REPORT.md` (3 cold runs) + direct re-measure of pre-change artifact `v2_2026-08-12_03-04-09/run_0.json`
- **Change:** `comfymodal_runtime/model_preload.py` (+111) and `comfymodal_runtime/modal_app.py` (+41), 152 lines, additive — **work in progress by concurrent agents was preserved** (no reset/stash/revert; `git diff` re-inspected before every edit and at close).

---

# Executive conclusion

Overlap now works: in all 3 valid runs the **entire native fast-disk UNET load (4.30–4.37 s) completed 1.07–1.89 s before the CLIP prefill finished**, so **zero** UNET-load time remains on the pre-sampling critical path. The graph demand joins the prepared patcher in **0.18–0.36 ms** (was a full 3.28 s serial load on the graph thread), and the post-prefill graph gap shrank from **0.98–1.07 s to 44–59 ms**. Exactly one UNET construction/read/H2D per request, one ModelPatcher, all native fast-disk guards/fallbacks intact (decision=complete, bind_assign=True, native_assign=False, 453 BF16 CUDA params, 0 CPU), snapshot invariants pass in every run, and output parity holds.

**Measured net effect (critical-path wall, prefill-schedule → UNET consumed):**

| | Baseline (03-04-09) | Run 1 | Run 2 | Run 3 |
|---|---|---|---|---|
| Pre-sampling critical path | 7159 ms | 5485 ms | 5964 ms | 6250 ms |
| vs baseline | — | **−1674 ms (−23.4 %)** | **−1195 ms (−16.7 %)** | **−909 ms (−12.7 %)** |

The win is smaller than the naive sum (prefill + load) because **concurrency measurably slows both stages** (see CLIP contention / UNET I/O-H2D contention): CLIP encode +39–62 %, UNET H2D +18–23 %, bind +7–10×. All figures carry unpinned-host variance (us-east1 / us-south1 / us-central1); the mechanism itself (join wait, completed-before-demand, load-inside-prefill) is deterministic and confound-free.

---

# Previous serialization

Measured across the 3 cold unique-prompt runs in `REAL_CLIP_CACHE_MISS_REPORT.md` (integrated config, provider/region unpinned):

| Stage | Window | Duration |
|---|---|---|
| exact-conditioning prefill | `execution_prefill_scheduled` → `execution_prefill_completed` | 2380.969–3359.881 ms |
| graph progression gap | `execution_prefill_encode_end` → `unet_fast_disk_defer` (incl. file read + model build) | +980 / +1049 / +1069 ms |
| native fast-disk bind | `unet_fast_disk_bind_start/end` | 17.667–19.746 ms |
| native fast-disk to(cuda) | `unet_fast_disk_to_start/end` | 2225.089–2279.842 ms |
| **CLIP ↔ UNET overlap** | max(0, min(enc_end, load_end) − max(enc_start, load_start)) | **0.0 ms in all runs** |

Independent re-measure of the pre-change artifact `v2_2026-08-12_03-04-09/run_0.json` (us-east1): prefill 3867.1 ms (encode 3580.0 ms), graph-time serial UNET load 3283.5 ms (read 1095.5 + get_model ≈13 + bind 18.6 + to 2125.3), load began 8.8 ms after prefill end, overlap 0.0 ms, pre-sampling critical path ≈ 7159 ms.

Root cause: prefill runs on the coordinator pool (concurrent with graph setup), but the **fast-disk UNET load runs inline on the graph thread** when the graph reaches UNETLoader (`_consume_unet` → future absent → `_LOADER_MISS` → original loader). The graph cannot reach UNETLoader before consuming CLIPTextEncode, so the two big stages were strictly serialized by the graph's own dependency order.

---

# Implementation

Smallest safe change, additive, 2 files. No modification to the fast-disk machinery (`model_preload.py:3278–4080`), loaders, snapshot/eviction design, cache persistence, output persistence, sampling, CacheDiT, or active-profile logic.

1. **`comfymodal_runtime/model_preload.py` — `ModelPreloadCoordinator.schedule_execution_unet` (line 8119)**
   Mirror of the existing single-flight `schedule_prefill`: atomic check-and-set under `_pool_lock`; submits only when `preparation.unet_future is None`; lane `"unet"`, phase `"execution"`, `expected_read_count=1`. Reuses `_submit`, which installs `_ensure_core_wrappers` + `_ensure_unet_decompose_wrappers` (the fast-disk path) for the lane — exactly the restore-time UNET lane contract.

2. **`comfymodal_runtime/model_preload.py` — `V2LoaderBridge.schedule_execution_unet` (line 9607)**
   Guards, in order: no preparation → skip (`missing_preparation`); future already present (restore-time lane / retained snapshot UNET) → no-op return True (idempotent); no `unet_identity` → skip; no UNET loader request in the plan → skip. Otherwise submits `self._load_unet(prep.model_key)` — the exact bridge restore lane loader, so the native fast-disk single-pass load, its guards and fallbacks apply unchanged. Emits `unet_execution_schedule` / `unet_execution_skip` events.

3. **`comfymodal_runtime/modal_app.py` — `_run_in_process` (line 10512), immediately after `schedule_execution_prefill`**
   Gate: `_snapshot_unet_absent` = CPU-snapshot active **and** snapshot UNET is None — the integrated configuration where the graph would otherwise fast-disk load at UNETLoader. The gate never fires when the snapshot retains a UNET (future present anyway) or in legacy no-snapshot paths (legacy background UNET defer stays the sole owner), preserving **exactly one UNET construction/load per request** in every config. Adds `[v2.execution_unet]` print + trace metadata (`_execution_unet_scheduled`, `_execution_unet_gate`).

**Join path (unchanged code):** graph reaches UNETLoader → `_consume_unet` → `_consume_model_impl` → `coordinator.wait_unet` joins the now-present future → `(result,)` served to the graph. The subsequent sampler `load_models_gpu` remains a cache validation. Any worker failure surfaces at demand as `_LOADER_MISS` → original loader (identical fallback to today). Release: `close_workers()` at request end and container teardown wait the same futures as before; the fast-disk deferral record is dropped on every path.

---

# Correctness proof

Gate run 1 (deterministic) passed every check; runs 2–3 confirm stability. No invariant/parity failure; hard stop after 3 valid generations.

| Invariant | Run 1 | Run 2 | Run 3 |
|---|---|---|---|
| One UNET construction/load | single `unet_loader_start`, single patcher ctor, single `unet_load_torch_file`, single bind+to, single `unet_fast_disk_complete` — no second load | same | same |
| One ModelPatcher | `patcher_class=comfy.model_patcher.ModelPatcher`, `patcher_dynamic=false`, ctor once | same | same |
| No second file read / H2D | 1 read (unet_load_torch_file_start/end ×1), 1 H2D (`unet_fast_disk_to_*` ×1) | same | same |
| Native fast-disk guards/fallbacks | `decision=complete reason=ok native_assign=false bind_assign=true`, 0 skips | same | same |
| 453 BF16, CUDA, 0 CPU | 453 × torch.bfloat16, devices {cuda: 453}, cpu_param_count=0 | same | same |
| UNET-absent snapshot | `snapshot_activation_invariant status=pass`, unet_present=0, clip_present=1, cpu_snapshot_active=1, loader_bridge_active=1 | same | same |
| CLIP/VAE retained snapshot state | CLIP served from snapshot (`prepared_result_consumed lane=CLIP`, completed_before_demand 1737–1809 ms); VAE activated at sampling end (lane=vae submit ≈9.8–11.3 s) | same | same |
| Loader bridge + exact-conditioning | cache `miss_stored` hit=0 miss=1 encode=1; prefill consumed `outcome=prepared` | same | same |
| Sampling / CacheDiT unchanged | sampling 4913.7 ms (baseline 4913.7) | 4818.2 ms | 4864.9 ms |
| Output parity | valid output, output_hash_count=1, benchmark completed | same | same |
| Ownership/release | graph join 0.18 ms; `close_workers` + teardown wait futures; fast-disk record dropped | same | same |

Determinism note: each run uses a unique prompt token by protocol, so output SHAs differ across runs by design (identical to the prior 3-run/6-run series); per-run output presence + hash count are the parity gate.

---

# Run table

3 valid cold unique-prompt generations (run 1 = correctness gate). Provider+region unpinned. Artifact root: `comfymodal-data\benchmarks\runs\`.

| | Run 1 (gate) | Run 2 | Run 3 |
|---|---|---|---|
| Artifact dir | v2_2026-08-12_03-43-09 | v2_2026-08-12_03-56-09 | v2_2026-08-12_04-00-47 |
| Region | GCP us-east1 | GCP us-south1 | GCP us-central1 |
| Cache decision | miss_stored (hit=0 miss=1) | miss_stored (hit=0 miss=1) | miss_stored (hit=0 miss=1) |
| Prefill total (encode) ms | 5438.3 (4990.8) | 5919.97 (5253.2) | 6190.9 (5787.4) |
| UNET load total ms | 4367.9 | 4317.8 | 4297.5 |
| — file read ms | 1236.8 | 1371.7 | 1199.3 |
| — bind ms | 161.4 | 180.3 | 125.5 |
| — to(cuda) H2D ms | 2618.7 | 2503.0 | 2533.2 |
| Load complete before prefill end | 1068.1 ms | 1600.0 ms | 1890.9 ms |
| Prefill-end → UNET demand gap | 46.8 ms | 43.9 ms | 58.8 ms |
| Graph join wait | 0.179 ms | 0.212 ms | 0.363 ms |
| `prepared_result_consumed` UNET | completed_before_demand 1112 ms, graph_wait 0.013 ms | 1642 ms, 0.019 ms | 1947 ms, 0.009 ms |
| Command → response ms | 171444 | 146572 | 190826 |

Excluded run (protocol): `v2_2026-08-12_03-47-48` — prompt token was not injected before launch, so the conditioning cache **hit** (hit=1 miss=0, prefill 780 ms). Not a cold unique-prompt run; discarded. It still demonstrates the join on the cache-hit path: graph demanded at +1709 ms and waited 2431.6 ms for the in-flight load (`prepared_result_consumed UNET graph_wait 2431.557 ms`) — correct single-load behavior, no duplicate construction.

---

# Direct overlap measurements

Overlap = max(0, min(A.end, B.end) − max(A.start, B.start)) on same-process monotonic timestamps. Load window = `unet_loader_start` → `unet_fast_disk_complete`.

| Overlap pair | Run 1 | Run 2 | Run 3 |
|---|---|---|---|
| cache lookup ↔ UNET load | 7.3 ms of 7.3 ms (**100.0 %**) | 18.2 of 18.2 (**100.0 %**) | 13.6 of 13.6 (**100.0 %**) |
| CLIP forward ↔ UNET load | 3797.9 of 4220.5 (**90.0 %**) | 3581.1 of 3995.9 (**89.6 %**) | 3731.6 of 4176.1 (**89.4 %**) |
| cache store ↔ UNET load | 0.0 of 642.3 (**0.0 %**) | 0.0 of 1181.3 (**0.0 %**) | 0.0 of 1443.3 (**0.0 %**) |
| full prefill ↔ UNET load | 4367.9 of 5438.3 (**80.3 %**) | 4317.8 of 5919.97 (**72.9 %**) | 4297.5 of 6190.9 (**69.4 %**) |
| **Load on critical path** | **0.0 ms** | **0.0 ms** | **0.0 ms** |

Interpretation:
- Lookup and CLIP forward fully overlap the load — the load's H2D competes with the forward for GPU time (see contention sections).
- Cache store shows 0.0 % by construction: the store runs post-forward inside the prefill worker, and the load's H2D always completed before the forward ended (load done 1068–1891 ms before prefill end). Store is not a defect — it sits on the prefill tail, not on a load dependency.
- The load is **fully contained inside the prefill window in all runs**, i.e. the previously serial 3.28 s graph-time load now contributes zero wall time to pre-sampling.

---

# CLIP contention

Does concurrency slow the CLIP encode? Yes — measurable, consistent direction (absolute values carry unpinned-host variance; baseline = pre-change artifact 03-04-09, us-east1).

| Metric | Baseline | Run 1 | Run 2 | Run 3 | Delta vs baseline |
|---|---|---|---|---|---|
| CLIP forward (encode core) ms | 1857.3 | 4220.5 | 3995.9 | 4176.1 | +115–127 % |
| Encode loop (encode_ms) ms | 3580.0 | 4990.8 | 5253.2 | 5787.4 | +39.4 / +46.7 / +61.7 % |
| Cache lookup ms | 278.7 | 407.8 | 695.9* | 367.0 | +32 % (r1/r3); *r2 incl. volume-read variance |
| Cache store ms | 1703.8 | 642.3 | 1181.3 | 1443.3 | mixed (host/volume dependent) |
| Prefill total ms | 3867.1 | 5438.3 | 5919.97 | 6190.9 | +40.6 / +53.1 / +60.1 % |

The encode slowdown (+1.4–2.2 s) is attributed to GPU time sharing with the concurrent fast-disk `to(cuda)` H2D (2.5–2.6 s of page-in traffic) plus CPU thread sharing for tokenization/attention on the same pool; host/region variance is a confound (3 different regions). Prefill's own reconciliation (`unattributed_ms` 436–663 ms, status `unmeasured_gap`) is the pre-existing lookup/store accounting split, unchanged.

---

# UNET I/O/H2D contention

Does concurrency slow the UNET file servicing / H2D? Yes — same caveats.

| Metric | Baseline | Run 1 | Run 2 | Run 3 | Delta vs baseline |
|---|---|---|---|---|---|
| File read (load_torch_file) ms | 1095.5 | 1236.8 | 1371.7 | 1199.3 | +9.5 / +25.2 / +9.5 % |
| Bind (assign loop, CPU) ms | 18.6 | 161.4 | 180.3 | 125.5 | **+6.7× / +9.7× / +6.7×** |
| H2D to(cuda) ms | 2125.3 | 2618.7 | 2503.0 | 2533.2 | +23.2 / +17.8 / +19.2 % |
| Total fast-disk load ms | 3283.5 | 4367.9 | 4317.8 | 4297.5 | +30.9 / +31.5 / +30.9 % |

Bind is the worst hit (7–10×): the safetensors→param assign loop competes for the shared torch intraop CPU threads with the concurrent CLIP encode CPU work. H2D +18–23 % from GPU traffic sharing with the forward. Total pre-sampling critical path is still shorter (next section) because the whole load moved off the critical path, but contention is the main cost of the overlap.

---

# Before vs after critical path

Pre-sampling critical path = `execution_prefill_scheduled` → `graph_unet_consumed` (the point sampling becomes unblocked).

| Run | Prefill | Post-prefill gap | Load on critical path | Join | **Critical path** | vs baseline |
|---|---|---|---|---|---|---|
| Baseline 03-04-09 | 3867.1 | 8.8 | 3283.5 (serial graph-thread load) | n/a (no future) | **7159.4 ms** | — |
| REAL_CLIP runs 1–3 | 2381–3360 | 980–1069 (incl. read+build) | 2243–2299 (bind+to) | n/a | ≈5603–6728 ms | — |
| Run 1 (us-east1) | 5438.3 | 46.8 | **0.0** | 0.18 ms | **5485.3 ms** | **−1674 ms (−23.4 %)** |
| Run 2 (us-south1) | 5919.97 | 43.9 | **0.0** | 0.21 ms | **5964.1 ms** | **−1195 ms (−16.7 %)** |
| Run 3 (us-central1) | 6190.9 | 58.8 | **0.0** | 0.36 ms | **6250.0 ms** | **−909 ms (−12.7 %)** |

Mechanism gain vs contention: the load removal alone is worth the full 3283–4368 ms that used to be serial; the observed net saving is 909–1674 ms because the contended stages grew (encode +1.4–2.2 s, load +1.0 s). Optimizing wall, not percentage: every ms of the load is off the wall; the remaining cost is the slowdown of the two now-concurrent stages.

Waterfall note: runs 2–3 report `captured_timeline_gap` residuals (+929.6 / +1233.8 ms) with the sequential waterfall's tolerance warnings. This is a platform/host clock-domain artifact of unpinned scheduling (mixed wall/mono boundaries on different regions — the same runs show local/platform stage splits of 11.9 s/119.3 s vs 19 ms/157.6 s), **not** a pre-sampling gap: the waterfall's own stage-overlap detector flagged no INVALID overlaps, and all pre-sampling intervals used here are same-process monotonic and contiguous.

---

# Remaining serial work

After this change, the pre-sampling critical path is composed of:

1. **CLIP prefill encode + store: 5438–6191 ms (≈99.7 % of critical path)** — now the single dominant serial block; cache store (642–1443 ms) runs on its tail and never overlaps the load.
2. **Graph gap prefill-end → UNET demand: 43.9–58.8 ms** (was 980–1069 ms).
3. **Join wait: 0.18–0.36 ms** — effectively free.
4. Post-UNET: sampler-node→sampling ≈122–130 ms and sampling ≈4.8–4.9 s (unchanged, out of scope).

---

# Recommended next action

Attack the contention that currently eats most of the overlap gain — target the H2D↔encode interference:

1. **Move file read + bind to restore time.** Read (1.2–1.4 s) and bind (0.13–0.18 s) are CPU/disk-bound and contend badly (bind 7–10× slower) without needing the graph. Reading + binding into the fast-disk window at restore leaves only the 2.5 s H2D to overlap prefill — removes ~1.4–1.6 s of contended CPU work and shrinks the load window that must be hidden.
2. **Start the H2D replay on a dedicated CUDA stream** (or after `clip_forward_start`). The forward is 4.0–4.2 s vs H2D 2.5 s — delaying H2D start by ~0.5–1.0 s loses little overlap while cutting concurrent GPU traffic; a side stream removes the ~18–23 % H2D and ~40–60 % encode penalties.
3. **A/B with an env gate** (e.g. `COMFYMODAL_V2_EXECUTION_UNET=0/1` for the schedule; restore-time variant gated separately), re-measuring the same four overlap pairs and both contention tables; run on the same unpinned protocol with 3 runs and note region per run.
4. Verify the restore-time read/bind variant does not regress restore latency beyond the wall savings (restore is off the request critical path in this config, so it is expected to be net-free).

---

*Data: `comfymodal-data\benchmarks\runs\v2_2026-08-12_03-43-09|03-56-09|04-00-47\run_0.json` (after), `v2_2026-08-12_03-04-09\run_0.json` (baseline re-measure), `REAL_CLIP_CACHE_MISS_REPORT.md` (baseline series), `FULL_RUN_LOGS.md` (prior series context). All timings from same-process monotonic trace events.*

---

# H2D Timing-Control Experiment (post-async-cache)

Experiment: can delaying the native fast-disk UNET H2D reduce CLIP↔H2D contention enough to improve total pre-sampling wall? Implemented env-gated, measured on the post-async-cache architecture. 3 valid cold unique-prompt generations total (control + 2 delay arms). Hard stop after 3.

# Post-cache baseline

The async exact-conditioning-cache persistence agent's work was confirmed present and complete in the checkout before this experiment (background persistence thread + coalesced batch commit + throttled reload + teardown flush + enqueued/persisted counters — `clip_conditioning_cache.py`, wired at `modal_app.py` exit and the `model_preload.py` store call site), and its effect is live in every run below:

| Stage | Pre-cache series (2026-08-12 03:43–04:00) | **Post-cache control (04:19, us-west1)** |
|---|---|---|
| cache lookup | 367–696 ms (sync reload) | **8.5 ms** (throttled reload) |
| cache store | 642–1443 ms (sync commit) | **10.1 ms** (enqueue-only) |
| CLIP forward | 3996–4220 ms | 4521.0 ms |
| encode | 4991–5787 ms | 4640.6 ms |
| prefill total | 5438–6191 ms | 5138.8 ms |
| UNET read / bind / H2D | 1199–1372 / 126–180 / 2503–2619 ms | 1291.1 / 285.6 / 2764.4 ms |
| **Completion slack** (demand − unet_complete) | 1068–1891 ms | **458.9 ms** |
| post-prefill graph gap | 44–59 ms | **5.1 ms** |
| join wait | 0.18–0.36 ms | 0.164 ms |
| pre-sampling CP (schedule → consumed) | 5485–6250 ms | **5144.1 ms** |

The cache changes shortened the prefill tail exactly as designed: slack fell from 1.07–1.89 s to **459 ms** and the post-prefill demand gap to ~5 ms. The old slack is no longer a valid delay budget — arms were chosen against the fresh 459 ms figure.

# H2D timing-control implementation

Smallest safe mechanism, additive, env-gated. Zero changes to the loader, fast-disk machinery, snapshot, cache, sampling, or output paths. One construction / one ModelPatcher / one read / one bind / one H2D preserved in every run (see Correctness proof).

1. **`comfymodal_runtime/model_preload.py` — module gate** (near line 150): `_EXECUTION_UNET_H2D_DELAY_MS` parsed from `COMFYMODAL_V2_EXECUTION_UNET_H2D_DELAY_MS` (float, default 0 = immediate, the proven baseline); `_EXECUTION_UNET_LANE_START_MONO` marker; `_CLIP_FORWARD_STARTED` milestone `threading.Event`.
2. **Lane-start capture** in `V2LoaderBridge.schedule_execution_unet`'s `_execution_unet` callback: stamps `_EXECUTION_UNET_LANE_START_MONO` at entry, clears the milestone, and clears the marker in `finally` (request-scoped; a later request or the graph-time path never inherits a stale anchor).
3. **Delay in `_fast_disk_replay_to`** (the single deferred-H2D replay point, before the measured `to_wall_ms` window): when the delay > 0 AND the CLIP forward milestone has fired (i.e. a real encode is running — cache-hit requests never pay the delay) AND an execution lane marker exists, sleep until `lane_start + delay_ms`; emits `unet_h2d_delay_start/end` (`delay_ms`, `waited_ms`). Graph-time fast-disk loads (no lane marker) are byte-for-byte unchanged.
4. **Milestone** in `_make_clip_span_wrapper`: fires `_CLIP_FORWARD_STARTED` at the outermost real `clip_forward` span start — the exact contention-window boundary, preferred over an arbitrary sleep anchor (see Delay-arm selection for why a pure forward-start trigger cannot create a delay on the miss path).
5. **`comfymodal_runtime/modal_app.py` — `_runtime_env`**: explicit passthrough of `COMFYMODAL_V2_EXECUTION_UNET_H2D_DELAY_MS` (the deploy-time env dict is an allowlist; without this the gate silently defaults to 0 in the container).

Rollback: unset the env (or set 0) → immediate H2D, byte-for-byte the prior behavior. The gate is milestone-gated so cache-hit requests (no forward) skip the delay entirely.

# Delay-arm selection

Measured anchors from the post-cache control: lane start ≈ prefill schedule +1 ms; H2D replay sits at ~1915 ms after lane start (read 1291 + bind 286 + ~340 ms get_model/defer overhead); forward starts ~605 ms in; demand at +5144 ms; slack 459 ms.

Two hard constraints shaped the arms:

- **The delay engages only when the budget exceeds the read+bind position (~1915 ms)** — the wait happens at the replay point, so a budget under ~1.9 s is a no-op. A "wait until CLIP forward start" trigger is therefore not a viable delay on the miss path: the forward starts at ~605 ms, long before the replay runs, so the milestone is used as the eligibility gate (cache-hit exclusion) rather than the delay anchor.
- **The demand deadline is ~5144 ms; uncontended H2D is ~2.5 s**, so a budget that gives the forward a meaningful head start pushes `h2d_end` toward the deadline. Arms: **D1 = 2200 ms** (≈252 ms effective delay, ~290 ms projected slack) and **D2 = 2500 ms** (≈585 ms effective delay, ~190 ms projected slack). Both exceed the 1915 ms engagement floor and stay nominally inside the 459 ms slack budget — the measured outcome (below) shows D2's projection was wrong because the forward's speedup changes the deadline it protects against.

# Run table

3 valid cold unique-prompt generations (control first, then the two arms). Provider+region unpinned. Artifacts: `comfymodal-data\benchmarks\runs\`.

| | Control (D=0) | D1 (2200 ms) | D2 (2500 ms) |
|---|---|---|---|
| Artifact dir | v2_2026-08-12_04-19-47 | v2_2026-08-12_04-29-21 | v2_2026-08-12_04-33-11 |
| Region | GCP us-west1 | GCP us-south1 | GCP us-east1 |
| Cache decision | miss_stored (enc 1) | miss_stored (enc 1) | miss_stored (enc 1) |
| Cache lookup ms | 8.5 | 12.8 | 7.3 |
| CLIP forward ms | 4521.0 | 4523.1 | **2127.8** |
| Encode ms | 4640.6 | 4656.6 | **2242.2** |
| Prefill total ms | 5138.8 | 5057.5 | **2491.3** |
| Store ms (async) | 10.1 | 10.4 | 9.9 |
| UNET read ms | 1291.1 | 1294.6 | 1251.3 |
| Bind ms | 285.6 | 209.2 | 187.1 |
| H2D ms | 2764.4 | 2616.9 | 2532.0 |
| H2D delay waited ms | — | 251.9 | 670.3 |
| Total UNET prep ms | 4681.5 | 4821.8 | 5045.2 |
| Forward ↔ H2D overlap | 2764.4 ms (100 % of H2D) | 2616.9 ms (100 %) | **0.0 ms** |
| Prefill ↔ UNET overlap | 4681.5 ms (91.1 %) | 4821.8 ms (95.3 %) | 2488.8 ms (99.9 %) |
| **Completion slack** | **+458.9 ms** | **+239.0 ms** | **−2467.1 ms** |
| Graph join wait | 0.164 ms | 0.147 ms | **2470.1 ms** |
| **Pre-sampling CP** | **5144.1 ms** | **5063.0 ms** | **5050.8 ms** |
| vs control | — | **−81.1 ms** | **−93.3 ms** |
| Sampling (regression) | 4967.6 ms | 5034.2 ms | 5012.8 ms |
| Output hash | 1 | 1 | 1 |
| Command → response | 335.2 s (slow host) | 128.2 s | 134.1 s |

# Contention vs overlap tradeoff

| | Control | D1 | D2 |
|---|---|---|---|
| Contention reduction (forward speedup vs control) | — | 0 ms (forward unchanged) | **−2393 ms** |
| Overlap lost (forward↔H2D) | 0 | 147 ms | 2764 ms (all) |
| Graph wait introduced | 0 | 0 | **+2470 ms** |
| Net CP change vs control | — | **−81 ms** | −93 ms (wait +2470 > CLIP gain 2393) |

D1: delaying H2D by 252 ms shortened the H2D by 147 ms but left the forward untouched (4523 vs 4521 ms) — the forward's inflation is not sensitive to that modest shift; the −81 ms CP delta comes from non-encode prefill segments (host variance across unpinned regions; encode was actually 16 ms slower). **D1's win is noise-level and not attributable to the mechanism.**

D2: pushing the H2D entirely out of the forward's window (0 ms overlap) restored the forward to its uncontended ~2.1 s — a **−2393 ms contention reduction**, the largest observed. But the fixed-cost H2D (2532 ms) then finished 2467 ms past demand: graph wait +2470 ms exceeds the CLIP gain, so **by the criterion, D2 does not win** — it is a mechanism proof, not a policy.

# Completion slack and graph wait

`unet_completion_slack_ms = graph_unet_demand − unet_complete`:

- Control: **+459 ms** (UNET completed early; join 0.16 ms).
- D1 (2200): **+239 ms** — delay absorbed ~220 ms of slack; still positive; join 0.15 ms.
- D2 (2500): **−2467 ms** — the delay overshot: the forward's own speedup (prefill ended at 2491 ms, demand at 2581 ms) shrank the real deadline far below the nominal 5144 ms budget, and the graph stalled 2470 ms behind the load.

The D2 overshoot is the experiment's central finding: a time-budget delay anchored to the pre-delay timeline cannot track the deadline's contraction once the forward speeds up. The safe budget is bounded by the *fast* prefill end (~2500 ms), i.e. a delay must keep `h2d_end ≤ ~2500 ms`, which leaves no room for any forward head start at all (uncontended H2D alone is 2532 ms).

# Critical-path comparison

Pre-sampling CP = `execution_prefill_scheduled → graph_unet_consumed`:

| Run | CP | vs control |
|---|---|---|
| Baseline (pre-overlap, 03-04-09) | 7159 ms | — |
| Pre-cache overlap series | 5485–6250 ms | — |
| **Post-cache control (D=0)** | **5144.1 ms** | — |
| D1 (2200 ms) | 5063.0 ms | −81.1 ms (−1.6 %) |
| D2 (2500 ms) | 5050.8 ms | −93.3 ms (−1.8 %) |

Both arms reduce the headline CP, but neither does so robustly: D1's delta is within unpinned-host variance (mechanism-visible forward/H2D behavior unchanged), and D2's delta is achieved by trading a 2.47 s stall for a 2.39 s forward gain — a near-zero net at the edge of the deadline. There is no delay value between 2200 and 2500 that reliably beats the control: the forward's speedup curve is near-binary (overlap vs no overlap) while the H2D cost is fixed at ~2.5 s, so the optimum band (H2D starting in the forward's final ~1.5 s, ending exactly at demand) is a knife-edge that host variance alone can tip into a stall.

# Correctness proof

All 3 runs pass every invariant — the delay mechanism never compromised the single-load architecture:

| Invariant | Control | D1 | D2 |
|---|---|---|---|
| One UNET construction/load | single loader/read/bind/H2D/complete | same | same |
| One ModelPatcher | `ModelPatcher`, dynamic=false, ctor once | same | same |
| No second file read / H2D | 1 read, 1 H2D | same | same |
| Native fast-disk guards | complete, bind_assign=True, native_assign=False | same | same |
| 453 BF16, CUDA, 0 CPU | ✓ | ✓ | ✓ |
| UNET-absent snapshot | invariant pass (unet_present=0, clip_present=1, snapshot+bridge active) | same | same |
| CLIP/VAE retained | snapshot CLIP served; VAE sampling-end activation | same | same |
| Cache semantics | miss_stored, enc 1, store 9.9–10.4 ms enqueue | same | same |
| Sampling/CacheDiT | 4967.6 ms (unchanged range) | 5034.2 | 5012.8 |
| Output parity | hash=1 each run | same | same |
| Delay gating | not engaged (D=0) | engaged 251.9 ms | engaged 670.3 ms |
| Release/teardown | close_workers + flush + fast-disk record drop | same | same |

The D2 graph wait is bounded (join waits the future, then serves the prepared patcher; the run completes correctly) — a wall-time cost, never a correctness or duplicate-load hazard. The milestone gate means cache-hit requests (no forward) never pay the delay, so the mechanism is neutral on the warm path.

# Final scheduling policy

**Immediate (D=0) remains the winner and the deployed default.** The delay gate (`COMFYMODAL_V2_EXECUTION_UNET_H2D_DELAY_MS`) stays implemented, env-gated, and safe — but no delay value was found that beats the fresh post-cache control robustly:

- D1 (2200 ms): −81 ms, mechanism-visible components unchanged → within unpinned-host variance.
- D2 (2500 ms): −93 ms but with +2470 ms graph wait > +2393 ms CLIP gain → disqualified by the success criterion.
- The uncontended H2D (~2.53 s) cannot finish before demand if it starts after the forward's midpoint; a time-budget delay therefore cannot capture the D2-proven contention win without a stall.

The control itself (post-async-cache, immediate overlap, CP 5144 ms vs 7159 ms pre-overlap baseline) remains the correct production behavior: −2015 ms (−28.2 %) from the original serial architecture, with zero graph wait and full invariants.

# Recommended next action

**Dedicated CUDA-stream H2D is now strongly justified; restore-time read/bind remains worthwhile.** The D2 arm proved the CLIP forward's contention cost is real and large (−2393 ms when the H2D is moved fully out of its window) and that the only blocker is that the H2D (~2.53 s) and the forward (~2.13 s uncontended) cannot both fit before the ~2.6 s demand when serialized. The two structural fixes, in priority order:

1. **H2D replay on a dedicated CUDA stream** (target the `_fast_disk_replay_to` `original_to(model, ...)` call): the forward's kernels stop being stalled by concurrent page-in traffic while the H2D keeps full overlap — the D2 forward speedup with the control's zero graph wait, i.e. the missing ~2.0–2.4 s of critical path. This was explicitly out of scope for this task and remains unimplemented.
2. **Restore-time read + bind** (CPU/disk-only, off the request path): removes ~1.3–1.5 s of read and ~0.2 s of bind from the on-path load window, shrinking the H2D deadline problem itself; the H2D then overlaps prefill alone. Also out of scope here.

Re-run the same 3-run protocol (control + 2 arms) after either change; the delay gate can then be retired or repurposed as the stream-start offset.

*Data: `comfymodal-data\benchmarks\runs\v2_2026-08-12_04-19-47|04-29-21|04-33-11\run_0.json` (post-cache control / D1 / D2). All timings from same-process monotonic trace events; regions recorded per run (us-west1 / us-south1 / us-east1, unpinned).*
