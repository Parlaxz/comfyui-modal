# V2 Production Defaults — 2026-08-13

Date: 2026-08-13
Status: ACCEPTED PRODUCTION CONFIGURATION (10 cold runs, 35 s cooldown — all runs `Fresh: YES`, `STATUS OK`)

---

## 1. Deployment identity

| Field | Value |
|---|---|
| Deployment hash | `b557b2401f293223` |
| Custom-node generation | `ff3a26d75ca51ece` |
| ComfyUI core | `f49bdb655707b979` (0.24.0) |
| App name | `stable-modal-comfy-v2-restore-only-shadow` |
| Class | `ModalRuntimeEntrypointV2` |
| GPU | `rtx-pro-6000` |
| CPU request | 12 |
| Memory request | 32768 MB |
| Cloud / Region | unrestricted (observed GCP/us-east1, GCP/us-east4, AWS/eu-south-2) |
| Container mode | single-use, cold (`min_containers=0`), no warm pool, no pins |

---

## 2. Deploy-side settings (baked into the image at deploy time)

The deployment is the **restore-only shadow app**: the UNET is EXCLUDED from the CPU snapshot, so every cold request performs a real request-time checkpoint read + GPU H2D (this is the accepted production-equivalent path).

| Env var | Value |
|---|---|
| `COMFYMODAL_V2_APP_NAME` | `stable-modal-comfy-v2-restore-only-shadow` |
| `COMFYMODAL_V2_CLASS_NAME` | `ModalRuntimeEntrypointV2` |
| `COMFYMODAL_V2_GPU` | `rtx-pro-6000` |
| `COMFYMODAL_V2_CPU_REQUEST` | `12` |
| `COMFYMODAL_V2_MEMORY_REQUEST` | `32768` |
| `COMFYMODAL_V2_MEMORY_MB` | `32768` |
| `COMFYMODAL_V2_BASELINE_CPU_REQUEST` | `12` |
| `COMFYMODAL_V2_BASELINE_MEMORY_REQUEST` | `32768` |
| `COMFYMODAL_V2_ENV_PROFILE` | `inherit` |
| `COMFYMODAL_V2_SNAPSHOT_MODEL_ORDER` | `O0` |
| `COMFYMODAL_V2_THREAD_POLICY` | `TBASE` |
| `COMFYMODAL_V2_CPU_MODEL_SNAPSHOT` | `1` |
| `COMFYMODAL_V2_SNAPSHOT_EXCLUDE_UNET` | `1` |
| `COMFYMODAL_V2_SNAPSHOT_CONSTRUCTION` | `1` |
| `COMFYMODAL_V2_NATIVE_FAST_DISK_UNET` | `1` |
| `COMFYMODAL_V2_EVICT_MODELS_BEFORE_SNAPSHOT` | `1` |
| `COMFYMODAL_V2_EVICT_RETAIN_ROLE` | `clip_vae` |
| `COMFYMODAL_V2_EVICT_RESTORE_IDLE_SECONDS` | `0` |
| `COMFYMODAL_V2_VAE_SNAPSHOT` | `1` |
| `COMFYMODAL_V2_CLIP_CONDITIONING_CACHE` | `1` |
| `COMFYMODAL_V2_UNET_ACTIVATION_MODE` | `late` |
| `COMFYMODAL_V2_VAE_ACTIVATION_MODE` | `sampling_end` |
| `COMFYMODAL_V2_VAE_POLICY` | `v1` |
| `COMFYMODAL_V2_PERSISTENT_LOCAL_HANDLE` | `1` |
| `COMFYMODAL_V2_PREFILL_LANES` | `critical` |
| `COMFYMODAL_V2_PREFILL_WAIT_FOR_UNET` | `0` |
| `COMFYMODAL_V2_RELEASE_GPU_AFTER_REQUEST` | `0` |
| `COMFYMODAL_V2_PUBLISH_RESTORE_PLAN` | `0` |
| `COMFYMODAL_V2_RESTORE_TORCH_THREADS` | (unset) |
| `COMFYMODAL_V2_FULL_TRACE` | `0` |
| `COMFYMODAL_V2_RESIDENCY_DIAGNOSTICS` | `0` |
| `COMFYMODAL_V2_DEEP_MODEL_DIAG` | `0` |
| `COMFYMODAL_V2_PAGEFAULT_TRACKING` | `0` |
| `COMFYMODAL_V2_VARIANCE_DIAGNOSTICS` | `0` |
| `COMFYMODAL_V2_UNET_PRETOUCH` | `0` |

Deployment mode: `V2_BENCHMARK_MODE=snapshot_restore_only` (snapshot construction invocation — deploys and exits WITHOUT issuing reuse probes; batches are run separately with `run_v2_single.bat`).

---

## 3. Run-side settings (the 10 cold runs)

| Env var | Value |
|---|---|
| `COMFYMODAL_V2_APP_NAME` | `stable-modal-comfy-v2-restore-only-shadow` |
| `COMFYMODAL_V2_ENV_PROFILE` | `inherit` |
| `V2_BENCHMARK_RUNS` | `10` |
| `V2_BENCHMARK_GAP_SECONDS` | `35` |
| `COMFYMODAL_V2_NATIVE_FAST_DISK_UNET` | `1` (echoed run-side; baked deploy-side) |

Benchmark mode: none set (plain single-batch benchmark). Every run in the batch was cold: unique restored instance ID, `Fresh: YES`, `STATUS OK`, reconciliation <= 5.7 ms.

---

## 4. Feature-flag defaults (production code defaults)

These are **defaults in code** (no env var needed; unset = enabled, explicit `0` = disabled, `1` = enabled):

| Feature | Default | Env override |
|---|---|---|
| Prompt signature memo (exec→cached) | **ON** | `COMFYMODAL_V2_PROMPT_SIGNATURE_CACHE` (0=off) |
| Topo-lazy memo (cached→first-node) | **ON** (same identity store as signature memo) | `COMFYMODAL_V2_PROMPT_SIGNATURE_CACHE` (0=off) |
| Conditioning cache prefetch (exact-hit) | **ON** | `COMFYMODAL_V2_CONDITIONING_CACHE_PREFETCH` (0=off) |
| PNG compression level | **1** | `COMFYMODAL_V2_PNG_COMPRESS_LEVEL` (valid {1,6}) |
| Restore-time folder warm | **ON** (advisory daemon) | — |
| Plan-receipt input-types warm | **ON** (advisory daemon) | — |

Measured steady-state results (production defaults, no manual flags):
- `exec→cached`: 5–14 ms (signature memo hit, source=volume)
- `cached→first-node`: 0.5–1.1 ms (`topo_lazy_hits=36`, no `INPUT_TYPES` paid)
- Conditioning exact-hit: 27–55 ms (`manifest_memory_hit=1`, `payload_memory_hit=1`, `prefetch_source=full`)

---

## 5. Exact replication steps

### Step 1 — Deploy (only after source/env changes)

```bat
:: from the repo root: C:\...\ComfyUI\custom_nodes\comfyui-modal
deploy_and_run_v2_single.bat
```

The deploy script now defaults to the accepted production configuration:
- `V2_BENCHMARK_MODE=snapshot_restore_only` (default in script)
- app = `stable-modal-comfy-v2-restore-only-shadow`
- UNET excluded from CPU snapshot, eviction `clip_vae`, `inherit` profile, `native_fast_disk_unet=1`
- Deploys, records the deployment identity (`.deployed_state.json`), then EXITS without probes.

Verify: the log ends with the "UNET-absent snapshot CONSTRUCTION invocation" banner and `deployment_combined_hash` is recorded (a NEW hash is expected for a fresh deploy — the memo/topo-lazy volume entries are per-identity, so the first post-deploy request is a compute miss and persists new entries; subsequent requests hit).

### Step 2 — Run the 10 cold runs with 35 s cooldown

```bat
run_v2_single.bat
```

No env vars are needed: the script defaults are `V2_BENCHMARK_RUNS=10`, `V2_BENCHMARK_GAP_SECONDS=35`, app = restore-only-shadow, profile = inherit. Each run is a fresh single-use cold container; a 35 s gap gives the teardown window enough time (a 20 s gap was demonstrated insufficient — warm-container reuse with `Fresh: NO` and `EXCEEDS_TOLERANCE`).

### Step 3 — Verify

For each of the 10 runs in `v2_c2f_10cold_35gap.log`:
- `Fresh: YES`, unique `Instance:` id, `STATUS OK`, `RECONCILIATION` <= ~6 ms
- `[v2.prompt_executor_breakdown]` shows `signature_cache_hit=True source=volume` and `c2f_cached_to_first_node_ms` < 2 ms
- `[v2.conditioning_exact_hit_breakdown]` shows `decision=exact_hit manifest_memory_hit=1 payload_memory_hit=1`
- `[v2.png_output]` shows `compress_level=1 ... bytes=3129718 sha=20b10e1f…` (byte-identical output)
- Checkpoint read + Synchronized H2D detail rows present under Pre-sampler execution

Artifacts: `comfymodal-data\benchmarks\runs\v2_<timestamp>\run_<i>.json` (10 files), `summary.json`, `campaign_manifest.json`.

### Step 4 — Known metric caveat (multi-run batches)

In a multi-run process, the harness subtracts the once-per-process host node-registry init (~19–21 s, paid only by run 1) from EVERY run's `production_adjusted_total_wall_ms`; runs 2–10 therefore show negative artifact values. Correct production-adjusted wall: run 1 = TOTAL WALL − registry init; runs 2+ = TOTAL WALL (no benchmark-only cost paid). The 10-run report (`V2_10_COLD_RUNS_35S_COOLDOWN.md`) uses the corrected values.

---

## 6. Reference results (this configuration, 10 cold runs)

| Metric | min | median | max |
|---|---:|---:|---:|
| Pre-Python snapshot restore | 0.809 s | 3.509 s | 6.487 s |
| Python restore | 0.387 s | 0.616 s | 1.535 s |
| Production-adjusted TOTAL WALL | 15.018 s | 15.582 s | 26.471 s |

- cached→first-node: 0.5–1.1 ms on every run
- Sampling: ~4.8 s (fixed)
- Sub-14 production-adjusted TOTAL WALL: **not consistently achievable** with this profile (best observed 15.0 s; application-after-resume alone ~12–13 s)

---

## 7. Explicitly out of scope (do not touch)

Sampling, CacheDiT, SageAttention, 8-step configuration, UNET pinned staging, VAE early overlap, async LRU, snapshot model composition, GPU type, CPU/RAM allocation, cloud/region pinning, warm containers, min_containers. PNG level 1 is the accepted default and remains unchanged.
