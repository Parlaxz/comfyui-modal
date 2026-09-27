# V2 Remaining Optimization Diagnostics

**Purpose:** measurement-only instrumentation for every remaining V2 application-side optimization target. This document explains what work is happening per region, what the new instrumentation measures, what the baseline run says, and what the next experiments must be.

**Status:** instrumentation implemented, locally verified (515 tests green), integrated cold run **not yet executed** (see §Run status).

---

# Executive remaining bottlenecks

| Rank | Bottleneck | Baseline raw cost | Critical-path cost (baseline estimate) | Instrumented? |
| ---- | ---------- | ----------------- | --------------------------------------- | ------------- |
| 1 | UNET H2D transfer mechanics (`exec_start_to_cached` unknown, H2D 1–2.2 s variance) | 2.214 s | likely 0.5–1.0 s wall (demand-slack bound) | ✅ Lane 1 |
| 2 | VAE activation starts only at `sampling_end` (post-sampling transition 0.837 s) | 0.837 s | 0.837 s serial | ✅ Lane 4 |
| 3 | PNG encode (PIL level-6) | 0.596 s | 0.596 s serial | ✅ Lane 7 |
| 4 | Python restore (gpu_state 236 ms of 549 ms) | 0.549 s | 0.549 s serial | ✅ Lane 8 |
| 5 | PromptExecutor `exec_start_to_cached` | 0.999 s | 0–0.3 s (UNET-bound; near zero until H2D fixed) | ✅ Lane 3 |
| 6 | Certificate/validation on request path | 0.151 s | 0.151 s serial | in flight (Agent 1) |
| 7 | Conditioning-cache cold exact-hit read | 1.8–2.06 s (bad hit) | variance-dependent, 0 on warm hits | ✅ Lane 6 |

**Sampling 4.8–5.0 s — intentionally fixed / out of scope.**

The single biggest unknown — `exec_start_to_cached ~999 ms` — is now decomposed by instrumented sub-spans (Lane 3). The second unknown — H2D mechanics — is now measured at the tensor/storage and CUDA-event level (Lane 1).

---

# UNET transfer mechanics (Lane 1)

## Baseline (supplied `Pasted markdown(20260812-142808).md` run; matches run4 log, GCP us-east1)

```text
execution_unet scheduled
→ checkpoint/mmap read      ~1.047 s   (safetensors mmap via comfy.utils.load_torch_file)
→ get_model                 ~271 ms
→ bind                      ~158 ms   (66.9 ms in one log sample — variance)
→ H2D (12.31 GB)            ~2.214 s  (historical 1.0–2.3 s range)
→ ready
```

## What the real path is (code-verified)

- Loader: `V2LoaderBridge` native fast-disk UNET (`model_preload.py`), gate `COMFYMODAL_V2_NATIVE_FAST_DISK_UNET`.
- Read: ComfyUI safetensors **mmap** path — page-fault-driven hydration.
- H2D: **one deferred `nn.Module.to(device="cuda")`** (`_fast_disk_replay_to`, `model_preload.py:3888`), which issues **one async copy per parameter tensor** (~454 storages, uniform dtype), **pageable source, `non_blocking=False` by default** — torch's pageable→device fallback is a synchronous staged copy. No CUDA streams anywhere in the real path. CUDA events already bracket the transfer with one `torch.cuda.synchronize()` (reused by the new probe — **no additional sync**).

## New instrumentation (all gated by `COMFYMODAL_V2_OPTIMIZATION_DIAGNOSTICS`)

Event `opt_unet_h2d_transfer` (emitted at `model_preload.py:4106`, inside `_fast_disk_replay_to`):

| Output | Source |
| ------ | ------ |
| `cpu_wall_ms` | mono-ns bracket (reuses existing sync at :3975) |
| `cuda_event_ms` | new `OptCudaInterval` end event, realized via the existing sync |
| `effective_gbps` | bytes / (cuda or cpu) duration |
| `source_pinned` / `pinned_frac` | per-tensor `is_pinned()` scan of parameters+buffers |
| `tensor_stats` | aggregated: count, total bytes, by-dtype bytes, contiguous count, mmap-backed count, first-16 + largest-8 storage detail, size buckets — **bounded, never per-tensor log spam** |
| `non_blocking`, `copy_api` | `False`, `module.to (per-parameter async copy chain)` |
| `stream` | `opt_stream_info()`: current stream id, priority, device `asyncEngineCount`, name |
| `minor_fault_delta`, `major_fault_delta`, `thread_cpu_ms`, `process_cpu_ms`, `effective_cores`, `rss_delta_bytes`, `io_*` deltas | `host_snapshot`/`host_deltas` (guarded; `/proc` + getrusage; Windows-safe None) |

Plus existing events retained: `unet_fast_disk_to_start/end` (wall + synchronized device), `unet_fast_disk_complete` (parameter accounting), `unet_snapshot_pagein`, `unet_h2d` pagefault event, comfyapp `[v2.active_read_diag]`.

## What the integrated run will answer

- **Is bad H2D PCIe/DMA-limited?** → `effective_gbps` vs device theoretical (~30+ GB/s for RTX PRO 6000 PCIe). Baseline 12.31 GB / 2.214 s ≈ **5.6 GB/s — consistent with pageable staged copy, not DMA limit**.
- **Page-fault limited?** → `minor_fault_delta` during H2D vs mmap read window.
- **CPU memcpy/staging limited?** → `thread_cpu_ms` vs `cpu_wall_ms` ratio (staged copy burns CPU).
- **Snapshot hydration limited?** → pagein events + `rss_delta_bytes`.
- **Tensor-loop overhead?** → storage count (454) × per-copy launch cost is amortized inside `.to()`; `cpu_wall_ms` vs `cuda_event_ms` gap reveals enqueue vs device time.
- **Contention?** → Lane 2 overlap events.

---

# UNET vs CLIP contention (Lane 2)

## New instrumentation

- `opt_clip_forward_cuda` (`model_preload.py:5471`, in `_make_clip_span_wrapper`): CUDA-event pair around the real `clip_forward` **without synchronization** (never syncs on the sampling-critical path; `cuda_event_ms` realized only when `COMFYMODAL_V2_OPT_DIAG_SYNC_CUDA=1`, else wall-only). Mono-ns bracket always recorded → `_OPT_CLIP_FORWARD_MONO`.
- `opt_unet_clip_overlap` (`model_preload.py:11039`, at `graph_unet_demand`): `wall_overlap_ms(unet_h2d, clip_forward)` — overlap ms, coverage fractions; plus `unet_device_ms`.
- `opt_unet_readiness` (same site): `slack_ms = (ready − demand)` — **positive = UNET early, negative = sampler waits**. `_OPT_UNET_READY_MONO_NS` set in `ModelLaneTrace.ready` (:6404), `_OPT_UNET_DEMAND_MONO_NS` at `graph_unet_demand`.
- `opt_sampler_demand_slack` (`runtime_executor.py:3591`, after `sampling_start`): ready vs actual sampling start.
- `opt_stream_info()` inside the transfer event exposes stream identity + `asyncEngineCount` (copy engine availability, no Nsight needed).

## Contention mechanism hypothesis (to confirm, not act on)

GPU mutation is serialized by the **MutationLane** (`model_preload.py:5948-6004`): the `load_models_gpu` wrapper acquires per-owner lane (UNET/CLIP/prefill/VAE/sampler). CLIP forward and UNET H2D both commit through this lane. If the lane serializes them, overlap is structurally impossible and the "delay UNET → CLIP faster, UNET waits" evidence is explained by **lane holding, not device contention**. The new events distinguish: wall-overlap ≈ 0 with positive slack → lane-serialized (next experiment = dedicated stream/pinned staging, options B/C/D); wall-overlap > 0 → true device contention.

**Next experiment decision table (do NOT implement yet):**

| Evidence from run | Next experiment |
| ----------------- | --------------- |
| `source_pinned=false` + `effective_gbps` ≈ 5–8 GB/s + CPU thread burn | B. pinned staging (`COMFYMODAL_V2_PIN_UNET_TRANSFER`) or C. chunked/paced H2D |
| overlap≈0 + slack≈0 (lane-serialized) | A. dedicated CUDA stream (needs lane policy change — Agent 1 coordination) |
| overlap > 0 (device contention) | D. B+C combination |
| H2D fast, slack large, sampler still late | E. none — contention elsewhere (use `opt_executor_decomposition`) |

---

# PromptExecutor decomposition (Lane 3)

## Baseline

```text
PromptExecutor/cache setup      ~1.227 s
exec_start_to_cached            ~0.999 s   ← the big unknown
cached_to_first_node            ~0.227 s
```

## Code path (verified)

`modal_app._execute_v2_prompt_executor` (:11104) → `executor.execute` (:12310) → patched ComfyUI `execution.PromptExecutor.execute_async` (`runtime_executor.py:2433`). Inside `execute_async` (`execution.py:716-821`):

| Sub-step | Baseline contribution | Now measured by |
| -------- | --------------------- | --------------- |
| `execution_start` message + RAM headroom + `DynamicPrompt` + `IsChangedCache` | small | `opt_exec_dynamic_prompt_ms` (patch 5f) |
| per-cache `set_prompt` + `clean_unused` loop (execution.py:741-743) | part of 999 ms | `opt_exec_set_prompt_ms`, `opt_exec_clean_unused_ms` (patches 5a/5b) |
| **`asyncio.gather` cache walk over all node ids** (execution.py:745-752) | **likely dominant** | `opt_exec_cache_gather_ms` (split in `_patched_cache_get`, :2654) |
| `cleanup_models_gc` (execution.py:754) | part of 999 ms | `opt_exec_cleanup_gc_ms` (patch 5e) |
| `execution_cached` boundary | — | (existing milestone capture) |
| `ExecutionList` construction + `TopologicalSort.add_node` recursive walk (execution.py:762-765) | part of 227 ms | `opt_exec_topo_walk_ms`, `opt_exec_topo_nodes` (patch 5c) |
| first `stage_node_execution` + first node execute preamble (execution.py:768-774) | part of 227 ms | `opt_exec_stage_ms`, `opt_exec_first_stage_mono_ns` (patch 5d) |
| residual (event-loop scheduling, GC, locks, misc) | remainder | `residual_ms` (computed, clamped ≥ 0) |

Emitted as one **`opt_executor_decomposition`** event (in `_patched_exec_async` finally, :2560-2623) with `total_ms`, all sub-spans, `stage_count`, `first_stage_lag_ms`, `measured_sum_ms`, `residual_ms` — target **≥ 98% accounted** for the 999 ms span.

## Critical-path analysis to report after run

- `opt_executor_decomposition.total_ms` (raw span saving if removed).
- **Actual request-wall saving** must be computed against `opt_unet_readiness.slack_ms`: if UNET is the binding constraint, executor savings ≈ 0 until H2D is fixed. Both numbers will be reported side by side.

---

# VAE activation (Lane 4)

## Baseline timeline

```text
sampling_end ──→ VAE scheduled ──→ worker start ──→ load_models_gpu (~871 ms)
   ──→ ready ──→ graph demand ──→ join_wait (~37.5 ms) ──→ decode (~388 ms)
Post-sampling transition total: 0.837 s
```

## Code-verified facts

- Activation mode `sampling_end` is real: VAE submit happens at `model_preload.py:15679` (schedule), the actual GPU commit (`_mm_load_models_gpu`) runs in the VAE lane worker (`_run_early_vae_activation` :15506).
- The `unet_h2d` metric event (:2283-2299) shows VAE-lane H2D at **870–950 ms** across runs (FULL_RUN_LOGS.md:881/2591/4301) — the 871 ms "VAE GPU preparation" is a **VAE H2D transfer**.
- **Key structural fact:** the MutationLane is held by the **sampler** until `sampling_end` (released at `model_preload.py:15651-15667` in VAE-sampling_end mode). Therefore VAE activation **cannot** start during sampling without a lane/stream policy change — the 0.837 s is structurally serial today.

## New instrumentation

- `opt_vae_worker_started` (:15736), `opt_vae_join_demand` / `opt_vae_join_completed` (:10823/:10840) — previously state-only timestamps, now events.
- `opt_vae_h2d_transfer` (:2557): VAE-lane commit — bytes (parameter storages), pinned status, source device, stream info, device/wall durations.
- Existing: `vae_early_activation_scheduled` (:15841), `vae_early_activation_load_start` (:15591), `vae_early_activation_terminal` (:15412), `vae_early_activation_consumed` (:10677, join_wait), `vae_decode_start/end` (:10154/:10166), `sampler_lane_released_at_sampling_end` (:15664).

## Theoretical hiding windows (compute after run from measured durations — do not move now)

| Start before sampling_end | Hidden | Remaining transition | GPU contention risk |
| ------------------------- | ------ | -------------------- | ------------------- |
| 250 ms | up to 250 ms (H2D tail) | ~590 ms | low |
| 500 ms | up to 500 ms | ~340 ms | low-moderate (H2D DMA vs sampler kernels) |
| 750 ms | up to 750 ms | ~90 ms | moderate |
| 1000 ms | ~871 ms (full H2D) | ~0 ms + join | moderate-high (needs lane release or stream) |

Max plausible hiding: **~0.83 s** (the entire transition minus join/decode demand), contingent on solving lane serialization. Sampling slowdown from concurrent H2D is measured by comparing `sampling` durations across the experiment — that measurement does not exist yet; `opt_clip_forward_cuda`/`opt_unet_clip_overlap` provide the overlap baseline.

---

# Snapshot composition / pre-Python restoration trade (Lane 5)

## Facts

- Current snapshot: CLIP+VAE retained (UNET absent), RSS ~11.5 GiB after restore (11–13.6 GiB observed).
- Pre-Python gap is **entirely Modal scheduling**, not restore: `remote_python_resume_to_restore_start_ms=0.0` and `submission_to_remote_python_resume_ms` = 10.67 s (run4) / 22.76 s (run2) / **203.19 s (run3)** — the giant variance is container-start/snapshot-download, not Python.
- Per-role bytes: `snapshot_build_manifest._capture_retained_models` (:256) records per-role `storage_bytes` (bounded 64 storages) when `COMFYMODAL_V2_SNAPSHOT_MANIFEST=1`; `cpu_snapshot_models.sample_storage_residency` (mincore) available for resident-vs-total. **Enable `COMFYMODAL_V2_SNAPSHOT_MANIFEST=1` on the integrated run** (already passthrough-wired in `_runtime_env`).

## Feasibility calculation (estimates — to be filled with per-role bytes from the run)

| Composition | Snapshot bytes removed vs current | New request-time load work | Overlap potential | Critical-path delta |
| ----------- | --------------------------------- | -------------------------- | ----------------- | ------------------- |
| CLIP+VAE (current) | 0 | 0 | — | baseline |
| CLIP-only | VAE (~0.3–0.5 GB resident, small vs 11.5 GiB) | VAE H2D ~0.87 s at sampling end | VAE already hidden behind sampling (Lane 4) | ≈ 0 wall if Lane 4 solved; +0.87 s otherwise |
| VAE-only | CLIP (~1.5–2.5 GB) | CLIP forward recompute + H2D at request start | CLIP prefill already overlaps UNET | +CLIP load on pre-sampler path (~0.2–0.5 s est.) |
| runtime-only/minimal | ~11 GiB → smallest snapshot | ALL model loads | limited | large negative — not viable while fast-disk UNET loader exists |

**Conclusion:** snapshot composition is not the next lever. The 10.7–203 s pre-Python variance dwarfs anything snapshot composition can remove (~0.3–0.9 s), and it is not addressable from application-side code. Document it; do not experiment on composition.

---

# Conditioning cache read path (Lane 6)

## Baseline

```text
normal exact hit      ~140–150 ms
fresh cold exact hit  ~2.06 s
3.1 MB entry read     ~1.84 s on the bad hit
```

## Code path (verified; Agent 3's async-persistence in flight, untouched)

`lookup_many` (:900-970) → `_read_manifest` (:775-798) → per-entry `_lookup_entry` (:972-1019: header open/read :986-991, parse :992, validate incl. **full canonical-key compare** :995-1008, data open/read :1009-1012, byte-length cross-check :1013) → `deserialize_conditioning` (:505-553: payload sha256 :519, per-tensor sha256 :492-493, numpy rebuild :341-351, materialize :525-551). Volume reload is already off the lookup path (Agent 3); **`_persist_lru_touch` (:1022-1043) still does foreground Volume I/O (manifest rewrite with 2 fsyncs) on every hit** — a likely variance contributor.

## New instrumentation (all inside the existing `_diag` dict; optional `_diag` params default None → store path unchanged)

| New key | Meaning |
| ------- | ------- |
| `entry_header_open_read_ms` / `entry_header_parse_ms` / `entry_header_validate_ms` | header chain incl. canonical-key compare |
| `entry_data_open_read_ms` | payload open+read (dominant on bad hits) |
| `entry_deserialize_ms` | whole deserialize call |
| `deser_payload_sha_ms` / `deser_tensor_sha_ms` / `deser_tensor_rebuild_ms` / `deser_materialize_ms` | inside `deserialize_conditioning`/`_deserialize_tensor_descriptor`/`_bytes_to_tensor` |
| `deser_tensor_count` / `deser_tensors_bytes` | reconstructed tensor stats |
| `hit_read_bytes` / `hit_read_mbps` | effective read throughput |
| `cold_vs_warm_hint` | `"unknown"` (cannot infer page-cache state from inside) |

Exposed via `opt_last_lookup_diag()`; the model_preload caller (`clip_conditioning_cache_lookup` event) can attach it, or the report reads it directly.

## Decision input for next solution (do not implement)

- If `entry_data_open_read_ms` dominates on cold hits with low MB/s → Volume/network latency (candidates: single packed blob, compressed format, object store, or local snapshot-carried cache).
- If `deser_*_sha_ms` dominates → checksum cost (payload 519 + per-tensor 492 = two full sha256 of 3.1 MB): candidates: single checksum, faster hash, manifest redesign.
- If `lru_touch_ms` is large on every hit → foreground fsync rewrite per hit; candidate: batch/async LRU touch (consistent with Agent 3's async persistence pattern).
- `manifest_read_ms`/parse on 64-entry manifest is expected small.

---

# PNG/output encoding (Lane 7)

## Baseline

```text
~586 ms (573.96 / 582.83 / 569.65 ms across runs)
1920×1088, ~2.94 MB output, PIL PNG compress_level=6 (default), optimizer=False
GPU→CPU at comfyapp.py:525 (detach().cpu()), encode synchronous on executor thread
```

## New instrumentation

- `opt_output_encode_decomposition` (comfyapp.py, in `encode_image_tensor_batch`/`_clamp_image_tensor`): `gpu_to_cpu_ms`, `clamp_scale_ms`, `dtype_convert_ms`, `numpy_view_ms`, `pil_create_ms`, `png_compress_ms`, `raw_bytes_ms`, `total_ms`, `width/height/channels`, `output_bytes`, `compress_level`, `backend="PIL"`, `optimizer=False`. Printed as `[v2.opt.output_encode]`; trace event via `request_execution_trace_scope` contextvar.
- `[v2.opt.output_delivery] hash_ms= descriptor_ms=` (output_delivery.py: sha256 at :390-392, descriptor build :213-256).
- `[v2.opt.gpu_state] total_memory_ms=` (comfyapp.py:20199, the `get_total_memory` CUDA call — feeds Lane 8).

## Estimated candidate wins (do not implement)

- `compress_level` 6 → 1: PIL PNG level 1 is typically 2–3× faster (~0.3 s saving), output bytes +10–20% (quality unchanged — lossless). **No quality/format change.**
- Parallel hashing while encoding: sha256 of 2.94 MB is small (~10–30 ms) — minor.
- Faster PNG backend (pngwriter/oxipng-style): bigger change, medium risk.

---

# Python restore (Lane 8)

## Baseline

```text
restore 549 ms, bootstrap 529 ms
known: gpu_state 236 ms, CUDA context 2 ms, seed 4 ms, custom-node check ≈ negligible
```

## Code path (verified) and new instrumentation

`RuntimeBootstrap.restore` (runtime_bootstrap.py:1545-1900) — existing `variance_stage` timers + **new gap brackets**, all aggregated into one `opt_restore_decomposition` event at :2006-2070 with `bootstrap_total_ms`, per-stage ms, `measured_sum_ms`, `residual_ms` (clamped ≥0), `coverage_pct` (target ≥ 98%):

| Stage | Baseline | Instrumented as |
| ----- | -------- | --------------- |
| GPU-state restore (incl. `get_total_memory` CUDA call) | ~236 ms | existing + `total_memory_ms` sub-bracket (comfyapp) |
| CUDA context init | ~2 ms | existing |
| Fast-disk UNET wrapper install | untimed gap | `opt_restore_fastdisk_wrapper_ms` |
| Identity metadata capture | untimed gap | `opt_restore_metadata_ms` |
| Sage identity read + verify | read untimed | `opt_restore_sage_identity_read_ms` (+ existing `_sage_verify_ms`) |
| Runtime state reload (volume) | untimed | existing variance_stage |
| Models volume reload | untimed | existing variance_stage |
| Prescan identity restore | untimed gap | `opt_restore_prescan_identity_ms` |
| Custom-node identity check | `_check_ms` printed only | `opt_restore_custom_node_check_ms` |
| Seed hydration (file read) | ~4 ms | `opt_restore_seed_read_ms` |
| GC barriers | none in restore (verified) | constant 0.0 + note |

**Optimization candidate (do not implement):** `get_total_memory` (a CUDA query) dominates gpu_state; if it can be cached across restores in the same container, ~200 ms of the 549 ms restore is removable with minimal risk.

---

# Concurrent critical path (Lane 9)

## Baseline

```text
first node → sampler node ~2.378 s (much overlaps UNET)
pre-sampler total 3.947 s; measured children 3.890 s; residual 0.058 s
```

## New instrumentation (authoritative slack)

- `opt_unet_readiness`: `UNET_ready_minus_demand_ms` — **positive = UNET early by X ms; negative = sampler waits X ms** (emitted at `graph_unet_demand`).
- `opt_sampler_demand_slack`: ready vs actual `sampling_start`.
- `opt_unet_clip_overlap`: foreground/background overlap facts.
- `opt_executor_decomposition` sub-spans (foreground) alongside UNET lane events (background) → per-lane start/end/duration/overlap/critical-slack table in the run report.

This makes the `UNET_ready_minus_sampler_demand_ms` metric authoritative for all future UNET decisions (including the existing H2D-delay experiment gate `COMFYMODAL_V2_EXECUTION_UNET_H2D_DELAY_MS`, which is untouched).

---

# Theoretical application-wall floor (Lane 10)

Baseline app-controlled path (excludes pre-Python Modal scheduling 10.67 s): ≈ **11.57 s** (restore 0.55 + method setup 0.21 + pre-sampler 3.95 + sampling 4.88 + transition 0.84 + VAE 0.39 + output 0.60 + handoff 0.12).

| Scenario | Saving source | Raw saving | Respects concurrency → **wall saving** |
| -------- | ------------- | ---------- | --------------------------------------- |
| Current measured | — | — | 11.57 s |
| Agent 5 fast path only | cert 0.151 s + validation/preflight | ~0.15 s | **~0.15 s** (serial stage) |
| Healthy UNET H2D only | 2.214 → ~0.6–1.0 s | 1.2–1.6 s | **0.5–1.0 s** (bounded by demand slack; executor becomes next constraint) |
| VAE fully hidden only | 0.837 s transition | 0.837 s | **~0.83 s** (needs lane/stream change; contention risk) |
| PromptExecutor 999 ms removed only | 0.999 s raw | 0.999 s | **0–0.3 s** (UNET-bound; near zero until H2D fixed) |
| PNG optimized only | level 6→1 | ~0.3 s | **~0.25–0.35 s** (serial) |
| Restore gpu_state cached only | ~0.2 s | ~0.2 s | **~0.2 s** (serial) |
| **Best mutually compatible combination** | H2D 0.5–1.0 + VAE 0.83 + PNG 0.3 + cert 0.15 + gpu_state 0.2 + executor 0.1–0.3 | — | **~1.6–2.6 s → 8.9–10.0 s app-controlled** |

**Floor:** with Sampling fixed at 4.8–5.0 s, the realistic best app-controlled wall is **~9.0–10.0 s** (from 11.57 s) on the current architecture, before pre-Python scheduling. Command→response with a healthy 10 s scheduling gap ≈ 19–20 s; the 203 s scheduling outlier (run3) is out of application control.

---

# Ranked next optimizations

| Rank | Optimization lane | Current raw cost | Critical-path cost | Variance | Best likely approach | Expected real wall saving | Confidence | Required next experiment |
| ---- | ----------------- | ---------------: | -----------------: | -------: | -------------------- | ------------------------: | ---------- | ------------------------ |
| 1 | UNET H2D transfer | 2.214 s baseline / 4.15 s measured | **0.5–1.0 s (measured: sampler waited 995 ms for UNET)** | 1.0–2.3 s | pinned staging or chunked/paced H2D (B/C) — measured: pageable, non_blocking=False, 2.98 GB/s, ~1.5 eff cores, 0 faults | 0.5–1.0 s | **high (measured staging-limited signature)** | E2 A/B: `COMFYMODAL_V2_PIN_UNET_TRANSFER=1` vs baseline; recheck `opt_unet_h2d_transfer.effective_gbps` + `opt_unet_readiness.slack_ms` |
| 2 | VAE activation hidden | 0.526–0.837 s transition | 0.526–0.837 s serial | low | start H2D during final sampling portion via lane/stream change | 0.5–0.83 s | medium-high (measured VAE H2D 554 ms pageable; join only 41 ms) | E3 lane-release/stream A/B at X ∈ {250,500,750,1000} ms; measure sampling slowdown |
| 3 | PNG encode | 0.596 s baseline / 0.621 s measured | 0.621 s serial | low | compress_level 1 or faster backend — **measured: PNG compress = 97.6% of encode (605.8 ms)** | 0.3–0.4 s | **high** | E4 level 1 vs 6 A/B; recheck `png_compress_ms` |
| 4 | Restore gpu_state | 0.236 s baseline / 0.339 s measured | 0.339 s serial | low | cache `get_total_memory` across restores | ~0.2–0.3 s | high | `total_memory_ms` + `opt_restore_decomposition` (coverage 99.95% already) |
| 5 | Certificate/validation fast path | 0.151 s baseline / 0.300 s + validation 1.717 s measured | 0.15–0.3 s | low | Agent 1 plan-proof path (in flight) | ~0.15–0.3 s | high | already implemented by Agent 1 |
| 6 | PromptExecutor 999 ms | 0.999 s baseline / **54 ms measured** | 0–0.3 s | **high (54 ms vs 999 ms)** | remove cache-walk/set_prompt overhead | 0–0.3 s (variance-dependent) | medium | rerun with fixed `opt_executor_decomposition` emit; split set_prompt/clean_unused/gather/GC |
| 7 | Cache cold-hit read | 1.8–2.06 s (bad hit) | variance-dependent | high | packed blob / fewer checksums / async LRU touch | 0–1.8 s (worst-hit) | medium | `opt_last_lookup_diag()` sub-splits on a cold-hit run |

**Sampling ~4.8–5.0 s — intentionally fixed / out of scope.**

Note: measured run host (AWS eu-central-1) was degraded (165 s scheduling, 26 s snapshot age, 24.6 s backend startup, checkpoint read 4.14 s vs 1.05 s baseline) — mechanics are host-independent, but absolute savings should be re-baselined on a healthy host run.

---

# Exact next experiments

## E1 — One integrated cold request (instrumentation validation; primary)

```bat
REM deploy (snapshot construction, UNET-absent, clip_vae retain):
set V2_BENCHMARK_MODE=snapshot_restore_only
set COMFYMODAL_V2_OPTIMIZATION_DIAGNOSTICS=1
set COMFYMODAL_V2_SNAPSHOT_MANIFEST=1
set COMFYMODAL_V2_NATIVE_FAST_DISK_UNET=1
set COMFYMODAL_V2_ENV_PROFILE=inherit
call deploy_and_run_v2_single.bat

REM run (one valid probe; keep V2_RESTORE_ONLY_RUN_COUNT at default 6 or set 1):
set V2_BENCHMARK_MODE=snapshot_restore_only
set COMFYMODAL_V2_OPTIMIZATION_DIAGNOSTICS=1
set COMFYMODAL_V2_SNAPSHOT_MANIFEST=1
set COMFYMODAL_V2_NATIVE_FAST_DISK_UNET=1
call run_v2_single.bat
```

Flags note: both new flags are now in `modal_app._runtime_env` passthrough (verified). `COMFYMODAL_V2_OPT_DIAG_SYNC_CUDA` stays **off** — the fast-disk path reuses its existing sync; CLIP-interval stays wall-only.

Expected artifacts: `opt_unet_h2d_transfer`, `opt_clip_forward_cuda`, `opt_unet_clip_overlap`, `opt_unet_readiness`, `opt_vae_h2d_transfer`, `opt_vae_worker_started`, `opt_vae_join_demand/completed`, `opt_executor_decomposition`, `opt_sampler_demand_slack`, `opt_restore_decomposition`, `opt_output_encode_decomposition`, `[v2.opt.output_delivery]`, `[v2.opt.gpu_state]`, `[v2.opt.output_encode]`, snapshot manifest per-role bytes, plus `opt_last_lookup_diag()` on cache hit.

Acceptance: `opt_unet_h2d_transfer.effective_gbps` in range; `opt_executor_decomposition.measured_sum_ms + residual_ms ≈ total_ms`; `opt_restore_decomposition.coverage_pct ≥ 98`; `opt_unet_readiness.slack_ms` signed correctly; zero `opt_*` events when flag off (already proven in 515 tests).

## E2 — UNET H2D A/B (after E1)

- A: `COMFYMODAL_V2_PIN_UNET_TRANSFER=1` (existing gate; pinned staging) vs baseline. Measure `effective_gbps`, `cpu_wall_ms` vs `cuda_event_ms`, slack.
- B: chunked/paced H2D — requires new experiment gate (not implemented).
- Decision rule: adopt the variant that maximizes `slack_ms` without increasing sampling/CLIP durations.

## E3 — VAE lane experiment (after E1; needs design, do not implement here)

- Start VAE H2D X ms before `sampling_end` with a separate stream or early lane release; measure X ∈ {250, 500, 750, 1000} against sampling duration change and `opt_vae_h2d_transfer`/join metrics.

## E4 — PNG level A/B (after E1)

- `compress_level` 1 vs 6 on the same request shape; compare `png_compress_ms` and output bytes (quality identical — lossless).

---

# Measured results — integrated cold run (2026-08-12, executed)

**Run 1 (restore-only probe, `snapshot_restore_only` mode):** 1/1 VALID cold probe, **GCP us-central1**, RTX PRO 6000, 12 CPU, 32768 MB. prePy 3815.8 ms, pyRestore 1076.4 ms, resume2entry 2218.6 ms, RSS 12999 MiB (status VmRSS). Invariant: UNET absent, CLIP+VAE retained, eviction role clip_vae — all correct.

**Run 2 (full request, single trial):** VALID, **AWS eu-central-1** (unpinned placement; horrible 165.1 s pre-Python scheduling — per task rule this is not a reason to repeat). Command→response 205.23 s, controllable app wall 40.13 s (inflated by a degraded host: snapshot age 26 s, backend startup 24.6 s, checkpoint read 4.14 s vs baseline 1.05 s). **Mechanics are host-independent; absolute durations on this host are pessimistic.**

All 16 instrumentation events fired; measured values:

## UNET H2D transfer mechanics (measured)

| Field | Value | Meaning |
| ----- | ----- | ------- |
| `cpu_wall_ms` | 4151.3 | full `.to(cuda)` window |
| `cuda_event_ms` | 4136.8 | device time (reused existing sync, no new sync) |
| `effective_gbps` | **2.976** | 12.31 GB in 4.14 s |
| `source_pinned` | **false** (`pinned_frac` 0.0) | pageable source |
| `non_blocking` | **false** | torch `Module.to` default |
| `copy_api` | `module.to` (per-parameter async chain) | 454 storages, 12.31 GB, bf16, 100% contiguous |
| `thread_cpu_ms` / `process_cpu_ms` | 3510.0 / 5240.0 | **effective_cores 1.49** |
| `minor/major_fault_delta` | **0 / 0** | no page-fault cost inside H2D (faults happen during mmap read) |
| `io_read_delta` / `io_syscr_delta` | 0 / 3 | no disk I/O during transfer |
| `rss_delta_bytes` | −12.0 MB | no hydration during H2D |
| `device_vs_cpu_wall_ratio` | 0.9965 | CPU enqueue ≈ device time → **staged synchronous copy** |
| size buckets | 250 <1 MiB, 33 1–8 MiB, 35 8–64 MiB, 136 64–256 MiB | largest 8 × 84.4 MiB |

**Verdict: CPU memcpy/staging limited, not PCIe/DMA limited, not page-fault limited.** 2.98 GB/s is far below the RTX PRO 6000 PCIe capability; the pageable→pinned staged path burns ~1.5 effective cores. This is the definitive signature that **pinned staging (B) or chunked/paced H2D (C) is the right next experiment** — expected H2D 4.15 s → ~1.5–2.5 s on this host class (mechanics-level).

## UNET/CLIP contention (measured)

- `opt_clip_forward_cuda`: wall 6945.5 ms (degraded host; `cuda_event_ms` unrealized by design — no sync on sampling path), stream id 0, priority 0.
- `opt_unet_clip_overlap`: UNET H2D (4141.5 ms) **fully contained** inside the CLIP forward window (b_within_a_frac 1.0, overlap 4141.5 ms) → the two genuinely overlap in wall time (separate lanes).
- `opt_unet_readiness`: **slack −741.7 ms** (UNET ready 742 ms AFTER graph demand).
- `opt_sampler_demand_slack`: **slack −995.0 ms** → **the sampler waited ~1.0 s for UNET** — UNET readiness is on the critical path this run.

## PromptExecutor (measured top-level; sub-decomposition event pending fixed emit)

- `prompt_executor_milestones`: `execution_start_to_cached_ms` **54.3** (baseline 999 ms — massive variance signal), `cached_to_first_node_ms` 128.3, `first_node_to_clip_ms` 5.6, `clip_to_sampler_node_ms` 5021.6 (degraded host).
- **The 999 ms baseline did NOT reproduce (54 ms this run)** — exec_start_to_cached is highly variable; the next run (with the fixed `opt_executor_decomposition` emit, which now captures the trace at entry) will split it into set_prompt/clean_unused/gather/GC spans.

## VAE activation (measured)

- `opt_vae_h2d_transfer`: 167.6 MB / 244 params, **device 554.3 ms** (0.30 GB/s — same pageable-staging signature), pinned false, source cpu, stream 0, caller `restore_vae_preparation`.
- `opt_vae_worker_started` → `join_demand` → `join_completed`: join_wait **41.3 ms** (VAE ready before demand). Post-sampling transition 526 ms this run (baseline 837 ms).
- **Max hiding if VAE H2D ran during sampling tail: ~526 ms on this run (the whole transition minus join), contingent on lane/stream change.**

## Conditioning cache (measured)

- `clip_conditioning_cache_lookup` fired (exact hit path exercised). The `_lookup_entry` sub-splits are available via `opt_last_lookup_diag()`; this run did not log the pathological 1.8–2.06 s cold hit (variance-dependent).

## PNG/output encode (measured)

- `opt_output_encode_decomposition`: total **620.7 ms**; **`png_compress_ms` 605.8 (97.6% of encode!)**, gpu_to_cpu 0.008, clamp_scale 3.2, dtype 0.9, numpy 0.03, pil_create 14.3, raw_bytes 0.6. 1920×1088×3, 2.873 MB, compress_level 6, backend PIL, optimizer false.
- **PNG compression IS the encode** — level 6→1 or a faster backend is a near-certain ~0.3 s saving; hash/descriptor ~17 ms total.

## Python restore (measured)

- `opt_restore_decomposition`: **coverage 99.95%** (residual 0.74 ms of 1567.7 ms). This run: gpu_state 339.3, cuda_init 183.4, runtime_state 790.2 (volume reload, degraded host), models 252.2, seed 1.2, all gap fields <0.3 ms each, gc 0.0. Restore total 1598.97 ms on this host (baseline 549 ms).
- `get_total_memory` caching candidate: gpu_state ≈ 339 ms this run.

## Concurrent critical path (measured)

- **UNET readiness slack −995 ms at sampling start → UNET is the binding pre-sampler constraint on this run** (and H2D is staging-limited). Fixing H2D first is confirmed as rank-1.
- UNET H2D fully overlapped CLIP forward; CLIP forward was heavily degraded (6.9 s) — consistent with device contention from the concurrent staged H2D copy (or degraded host; distinguished by the E2 A/B experiment).

---

# Run status

- **Real run: YES — executed 2026-08-12.** Provider/region: probe on **GCP us-central1** (1 valid restore-only probe); full request on **AWS eu-central-1** (unpinned; 165 s pre-Python scheduling — not repeated per task rule).
- Baseline used: numbers supplied in the task brief (`Pasted markdown(20260812-142808).md` — file not found on disk; values match run4 log, GCP us-east1) + measured values above.
- All instrumentation verified locally (515 tests green) and exercised end-to-end in the real run (16/16 event types, 468 trace events). One emit gap found in the real run (`opt_executor_decomposition` trace resolution) — **fixed** (trace captured at entry) and re-verified (42 tests OK); the next run will capture Lane 3 sub-spans.

---

# Verification evidence

- `tests/test_optimization_diagnostics.py` (21 tests): flag-off no-ops, synthetic stage timings, no-CUDA-sync-default, aggregation boundedness, `/proc`-graceful host snapshots, env-flag parsing audit.
- Regression (flag off): 410 tests across executor/sampler/cache/restore/waterfall/variance/full-trace — OK.
- Flag-on smoke: 105 tests — OK.
- All changes additive; `git diff` reviewed per file; no commits made.
