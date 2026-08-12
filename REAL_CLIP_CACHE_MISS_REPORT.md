# REAL CLIP Cache-Miss Benchmark — Run Report

**3-run experiment COMPLETED (n = 3).** All three runs executed the integrated
configuration end-to-end and produced valid outputs. Every number below is measured;
where **min / median / max** is reported it is over the 3 runs. Stage durations are
computed from event pairs in the artifacts unless a metadata duration is cited.

Source artifacts parsed (read-only):
- **R1:** `comfymodal-data/benchmarks/runs/v2_2026-08-12_00-38-13/run_0.json`
- **R2:** `comfymodal-data/benchmarks/runs/v2_2026-08-12_00-43-08/run_0.json`
- **R3:** `comfymodal-data/benchmarks/runs/v2_2026-08-12_00-45-21/run_0.json`
- **Deep profiles:** `C:\Users\parla\AppData\Local\Temp\opencode\deep_profile_v2_2026-08-12_00-38-13.json`
  and `_00-43-08.json`, `_00-45-21.json` (dumped from the `sampling_deep_profile` events).

Validated integrated configuration (identical in all runs):
`COMFYMODAL_V2_ENV_PROFILE=inherit`, `CPU_MODEL_SNAPSHOT=1`, `VAE_SNAPSHOT=1`,
`SNAPSHOT_EXCLUDE_UNET=1`, `EVICT_MODELS_BEFORE_SNAPSHOT=1`,
`EVICT_RETAIN_ROLE=clip_vae`, `EVICT_RESTORE_IDLE_SECONDS=0`,
`NATIVE_FAST_DISK_UNET=1`, CPU 12, RAM 32768, `rtx-pro-6000`, provider/region
UNPINNED, `CLIP_CONDITIONING_CACHE=1`, `COMFYMODAL_SAMPLING_DEEP_PROFILE=blocks`.
Post-restore `unet_present=0` with CLIP+VAE retained; request-time clip-only bridge
activation (`cpu_snapshot_clip_vae_bind` status=ok) published the retained CLIP on the
loader bridge; graph-time native fast-disk UNETLoader engaged.

---

# Executive conclusion

**Real CLIP-miss cost (measured, 3 runs).** On a genuine cold-cache miss the
exact-conditioning path costs:

- Cache lookup **≈0.16–0.47 s** (`lookup_wall_ms` 162.962 / 213.84 / 472.854; the
  variation is Modal `Volume.reload` + manifest-read RPC latency),
- CLIP encode node **≈1.27–1.45 s** (`loader_invoke` CLIPTextEncode
  1271.832 / 1385.929 / 1454.204 ms),
- Cache store **≈0.93–1.67 s** (`cache_store_wall_ms` 928.605 / 1668.254 / 932.587;
  ≈98% of it is the Modal `Volume.commit` RPC),
- Prefill total **≈2.38–3.36 s** (`prefill_total_ms` 2380.969 / 2812.933 / 3359.881).

**Does the CLIP work hide the native fast-disk UNET loading? No.** The fast-disk UNET
load (bind + `to` cuda:0) costs **≈2.25–2.30 s** (`to_wall_ms` 2225.089 / 2230.805 /
2279.842). Direct mono-clock overlap between the CLIP encode window and the fast-disk
load window is **0.0 ms in all 3 runs** — the two are **strictly serial**:

> CLIP encode/store → fast-disk bind+to → Sampling

The encode_end → `unet_fast_disk_defer` gap (980.0 / 1048.9 / 1068.9 ms) is pure
scheduling time to the graph UNETLoader node; the fast-disk transfer is bandwidth-bound
and CPU-light and could in principle overlap the prefill, but currently hides **none**
of it. The real miss cost to users is therefore **prefill + serial fast-disk load**,
i.e. ≈2.38–3.36 s + ≈2.25–2.30 s before sampling can start.

---

# Correctness and cache-miss proof

**All three runs are true cold misses.** Each ran in a fresh container with
`restore_count=1`, `request_count=1`, `hit_count=0`, `miss_count=1`, `encode_calls=1`,
`encoded_count=1`, `decision=miss_stored`, `stored_count=1`, and a unique prompt
proven by **three distinct `key_hash` values**: R1 `1aa4b719c6519b8d…`, R2
`ac335fb85ef0835e…`, R3 `a4024351c8f04be1…` — no hit path was possible, and exactly
one encode ran per run.

| Check | R1 | R2 | R3 |
|---|---|---|---|
| Cloud / region | CLOUD_PROVIDER_GCP / us-east4 (unpinned) | same | same |
| `restored_instance_id` | 799f6b155c8a483d85acf7e0b3d67892 | ff5ca3effbaf42f1b689b84cec7d13db | 2b443c4bbdd4490dbb7ec5d52c7202d6 |
| `image_id` | im-lGdF6dxWv1c8uvnsoRZyX9 (prior deploy, identical working tree) | im-ntCM3vGYwC4IoaCclnvk21 (canonical shadow deploy) | im-ntCM3vGYwC4IoaCclnvk21 |
| restore_count / request_count | 1 / 1 | 1 / 1 | 1 / 1 |
| cache lookup | hit=0, miss=1, `lookup_wall_ms` 472.854 | hit=0, miss=1, 213.84 | hit=0, miss=1, 162.962 |
| cache decision | miss_stored, encode_calls=1, stored_count=1 | same | same |
| invariant profile | inherit, status=pass | same | same |
| `unet_present` / `clip_present` | 0 / 1 | 0 / 1 | 0 / 1 |
| `cpu_snapshot_active` / `loader_bridge_active` | 1 / 1 | 1 / 1 | 1 / 1 |
| `cpu_snapshot_clip_vae_bind` | status=ok (clip+vae from cpu_snapshot, unet normal_loader) | status=ok | status=ok |
| native fast-disk | defer reason=ok stage=to → bind → to → complete | same | same |
| fast-disk params | 453 BF16 on cuda:0, 0 CPU params/buffers | same | same |
| `unet_fast_disk_skip` | 0 occurrences | 0 | 0 |
| deep profile | present, status=ok (see section below) | present, status=ok | present, status=ok |
| output SHA-256 (asset identity) | bce9b6f05cd136f1f58af5926f82bc67f2743df9accd46f748f9dd29be1d6abb | 94fe5ebb59dfdbeb45d03f61ecdf1f2358128b3957b2980270819fa34c189514 | 97eba69f5966be8ddb98ff57ab57f057cef10dbf6d95ba65fe770077e2ff9549 |

**Native fast-disk proof (identical in all runs).** `unet_fast_disk_defer`
(decision=defer, reason=ok, stage=to, target=cuda:0, HIGH_VRAM, get_model ≈31–33 ms,
ctor ≈0.14–0.17 ms) → `bind` (`bind_assign=True`, `native_assign=False`, 17.667 /
18.726 / 19.746 ms) → `to` cuda:0 (wall 2225.089 / 2230.805 / 2279.842 ms; device
2224.953 / 2230.677 / 2279.672 ms, `measurement=wall_and_synchronized_device`) →
`complete` at `load_model_weights` with **param_count=453,
`dtype_distribution={torch.bfloat16:453}`, `device_distribution={cuda:453}`,
`cpu_param_count=0`, `cpu_buffer_count=0`** and **zero `unet_fast_disk_skip`** events.

**Semantics unchanged.** `unet_runtime_state` stage=snapshot_created reports
ModelPatcher / Lumina2 / NextDiT with bf16 compute and RTX-PRO-6000 target in all 3
runs (same `param_distribution_hash` `96e377c80251860d…`). SageAttention was patched
at snapshot time (`sage_snapshot_identity` present) and CacheDiT was prepared
(`v2_startup_cachedit_preparation`, ≈943–971 ms during startup) in all runs.

---

# Run table

| Run | Cloud | Region | Restore | CLIP total | UNET loader | CLIP↔UNET overlap | Sampling | VAE/output | Command→response |
|---|---|---|---|---|---|---|---|---|---|
| 1 | GCP | us-east4 | 476.994 ms | encode loop incl. store **2315.093 ms** | bind 19.746 + to 2225.089 = **2244.835 ms** | **0.0 ms** | **4917.456 ms** (event pair) | 380.235 decode + 1443.092 collect = 1823.327 ms | 115652.8 ms |
| 2 | GCP | us-east4 | 611.847 ms | **3129.082 ms** | bind 17.667 + to 2230.805 = **2248.472 ms** | **0.0 ms** | **4882.549 ms** | 372.476 + 836.1 = 1208.576 ms | 108254.0 ms |
| 3 | GCP | us-east4 | 554.0 ms | **2205.073 ms** | bind 18.726 + to 2279.842 = **2298.568 ms** | **0.0 ms** | **4905.126 ms** | 363.225 + 847.82 = 1211.045 ms | 35888.7 ms |

- **CLIP total** = `encode_loop_wall_ms` from the cache decision (encode start → decision,
  includes the store), the authoritative prefill CLIP figure.
- **UNET loader** = native fast-disk `bind` + `to` (sum shown); the `to` is wall and
  synchronized-device measured.
- **Overlap** = direct mono-clock math: `max(0, min(enc_end, load_end) − max(enc_start,
  load_start))` = 0 in all runs (strictly serial).
- **Sampling** = authoritative `sampling_start` → `sampling_end` event pair (metadata
  `duration_ms`). The legacy `timing.sampler_ms` (3728.579 / 3699.01 / 3718.43) is
  anchored at `first_sampler_step` (+1186.1 / +1181.0 / +1184.0 ms into sampling) and is
  **rejected** as the sampling duration.
- **VAE/output** = `vae_decode_end.decode_wall_ms` + `timing.output_collection_ms`.

---

# CLIP decomposition

**Cache lookup** (`clip_conditioning_cache_lookup`; R1/R2/R3 raw then min/med/max):

| Component | R1 | R2 | R3 | min | med | max |
|---|---|---|---|---|---|---|
| `lookup_wall_ms` | 472.854 | 213.84 | 162.962 | 162.962 | 213.84 | 472.854 |
| total (lookup_diagnostics) | 472.673 | 213.575 | 162.794 | 162.794 | 213.575 | 472.673 |
| volume_reload_ms | 218.127 | 84.873 | 160.638 | 84.873 | 160.638 | 218.127 |
| manifest_read_ms | 254.304 | 128.446 | 1.917 | 1.917 | 128.446 | 254.304 |
| key_build_digest_ms | 0.188 | 0.201 | 0.188 | ≈0.2 | ≈0.2 | ≈0.2 |
| residual_ms | 0.05 | 0.05 | 0.048 | ≈0.05 | ≈0.05 | ≈0.05 |
| lock_wait_ms | 0.001 | 0.002 | 0.001 | negligible | | |
| entry/header/data reads | header=0, data=0 bytes (pure miss — manifest only) | same | same | | | |

**Cache store** (`clip_conditioning_cache_decision` → `store_diagnostics`; R1/R2/R3 then
min/med/max):

| Component | R1 | R2 | R3 | min | med | max |
|---|---|---|---|---|---|---|
| `cache_store_wall_ms` | 928.605 | 1668.254 | 932.587 | 928.605 | 932.587 | 1668.254 |
| total (store_diagnostics) | 928.576 | 1668.22 | 932.561 | 928.576 | 932.561 | 1668.22 |
| commit_ms (≈98% of store) | 909.597 | 1648.847 | 914.553 | 909.597 | 914.553 | 1648.847 |
| serialize_ms | 9.192 | 8.852 | 7.697 | 7.697 | 8.852 | 9.192 |
| data_write_ms | 4.027 | 4.147 | 4.006 | ≈4.0 | ≈4.0 | ≈4.0 |
| header_write_ms | 1.315 | 1.574 | 1.396 | ≈1.4 | ≈1.4 | ≈1.4 |
| manifest_write_ms | 1.356 | 1.434 | 1.376 | ≈1.4 | ≈1.4 | ≈1.4 |
| fsync_ms (fsync_count=6) | 0.222 | 0.19 | 0.193 | ≈0.2 | ≈0.2 | ≈0.2 |
| residual_ms | 0.174 | 0.179 | 0.201 | ≈0.2 | ≈0.2 | ≈0.2 |
| payload_bytes_written | 3,094,896 | 3,094,896 | 3,094,896 | | | |
| header_bytes / manifest_bytes | 3815 / 6598 | 3815 / 6754 | 3815 / 6910 | | | |

**CLIP encode spans** (computed from `clip_*_start/end` event pairs; R1/R2/R3 in ms):

| Span | R1 | R2 | R3 | min | med | max |
|---|---|---|---|---|---|---|
| tokenize | 12.615 | 12.781 | 10.498 | 10.5 | 12.6 | 12.8 |
| gpu_prepare | 1.274 | 2.6 | 7.341 | 1.3 | 2.6 | 7.3 |
| forward | 1369.259 | 1433.906 | 1238.483 | 1238.5 | 1369.3 | 1433.9 |
| raw_encode | 1372.184 | 1438.383 | 1259.639 | 1259.6 | 1372.2 | 1438.4 |
| scheduled conditioning | 1372.686 | 1439.8 | 1260.073 | 1260.1 | 1372.7 | 1439.8 |
| `loader_invoke` (CLIPTextEncode node) | 1385.929 | 1454.204 | 1271.832 | 1271.8 | 1385.9 | 1454.2 |
| **encode loop** (encode_start→decision incl. store) | 2315.093 | 3129.082 | 2205.073 | 2205.1 | 2315.1 | 3129.1 |
| **prefill total** (`clip_prefill_reconciliation`) | 2812.933 | 3359.881 | 2380.969 | 2381.0 | 2812.9 | 3359.9 |

Prefill reconciliation detail (R1/R2/R3): queue_ms 10.312 / 8.58 / 7.867; readiness_ms
0.516 / 0.692 / 0.484; encode_ms 2315.412 / 3123.354 / 2205.264; completion_ms 0.037 /
0.07 / 0.058; unattributed_ms 486.656 / 227.185 / 167.296 (`reconciliation_status=
unmeasured_gap`).

**Measured cache I/O finding (no optimization performed).**
- **Lookup cost = Modal `Volume.reload` RPC + manifest metadata read.** Both are
  network-RPC / latency dominated: `volume_reload_ms` 84.9–218.1 and `manifest_read_ms`
  1.9–254.3 (the manifest is 6,442–6,754 bytes; the RPC latency, not the parse, dominates
  and swings the total 0.16–0.47 s). The CPU work is negligible: `key_build_digest_ms`
  ≈0.2 ms and residual ≈0.05 ms. On a pure miss no entry bytes are opened
  (`header_bytes_read=0`, `data_bytes_read=0`, `lru_touch_ms=0`).
- **Store cost ≈98% Modal `Volume.commit` RPC** (`commit_ms` 909.6–1648.8 of
  928.6–1668.2 total). Serialize ≈7.7–9.2 ms; local atomic writes ≈6–7 ms total
  (data ≈4.0 + header ≈1.4 + manifest ≈1.4); fsync ≈0.2 ms — all negligible.
- **Backing store:** Modal Volume **`comfymodal-prompt-encoding-cache`** at
  **`/root/prompt_cache_vol`**; per-entry files **`<key_hash>.data.bin`** +
  **`.header.json`** plus **`manifest.json`**; a store writes payload + header +
  manifest. These are the intrinsic durability/persist contract operations; the
  currently-observed cost drivers are the **reload/commit RPCs**, not the local work.

---

# Timeline

R1 representative (full `wall_unix_ns`; Δ = wall delta in ms on the same cross-process
clock; R2/R3 key deltas below). The chain is explicitly serial — no stage overlaps the
next.

| Event | wall_unix_ns (start → end) | Δ (ms) |
|---|---|---|
| local_run_request_received (request entry) | 1786495093507272192 | 0 |
| execute_plan_call_start | 1786495093511273984 | +4.0 |
| restore_plan_publish_start | 1786495109605986500 | +16,094.7 |
| restore_plan_publish_end / modal_submit_start | 1786495187798484100 | publish span **78,188.0** (timing `restore_publish_ms`) |
| modal_first_remote_event | 1786495187996610900 | +198.1 |
| run_plan_stream remote_method_entry | 1786495188670031104 | +673.4 |
| cpu_snapshot_clip_vae_bind (status=ok) | 1786495188698989657 | +29.0 |
| snapshot_activation_invariant (status=pass) | 1786495188699288857 | +0.3 |
| execution_prefill_scheduled | 1786495188699340036 | +0.1 |
| clip_conditioning_cache_lookup | 1786495189196311961 | +496.9 (lookup **472.854**) |
| execution_prefill_encode_start | 1786495189196823301 | +0.5 |
| loader_invoke_start (CLIPTextEncode) | 1786495189196896471 | +0.1 |
| clip_tokenize_start → end | 1786495189196920711 → 1786495189209535340 | **12.615** |
| clip_gpu_prepare_start → end | 1786495189210207320 → 1786495189211481069 | **1.274** |
| clip_forward_start → end | 1786495189211773048 → 1786495190581030699 | **1369.259** |
| clip_raw_encode_end | 1786495190582217628 | raw encode 1372.184 |
| clip_scheduled_conditioning_end | 1786495190582619058 | scheduled 1372.686 |
| loader_invoke_end (CLIPTextEncode) | 1786495190582834407 | loader **1385.929** |
| clip_conditioning_cache_decision (miss_stored) | 1786495191511972727 | store **928.605**; encode loop **2315.093** |
| execution_prefill_encode_end (encoded_count=1) | 1786495191512235517 | +0.3 |
| execution_prefill_completed | 1786495191512272687 | +0.0 |
| clip_prefill_reconciliation | 1786495191512947966 | prefill total **2812.933** |
| unet_fast_disk_defer (reason=ok, stage=to) | 1786495192561100065 | **+1048.9** after encode_end (graph scheduling gap) |
| unet_fast_disk_bind_start → end | 1786495192562610354 → 1786495192582417137 | **19.746** |
| unet_fast_disk_to_start → end | 1786495192582698377 → 1786495194807731128 | **2225.089** (wall; device 2224.953) |
| unet_fast_disk_complete (453 BF16 CUDA / 0 CPU) | 1786495194809270617 | +1.5 |
| sampler_lane_wait_start → end | 1786495194854762118 → 1786495194854816368 | **0.054** (mono delta) |
| graph_gpu_load_start → end | 1786495194920066303 → 1786495194963748587 | **43.682** (+182.6 after complete) |
| sampling_start | 1786495194991834083 | +28.1 |
| unet_first_cuda_op | 1786495195069020338 | elapsed **136.346** (after demand; +77.2 after sampling_start) |
| first_sampler_step | 1786495196177971896 | **+1186.1** after sampling_start |
| sampling_end | 1786495199909288248 | window **4917.454** (metadata 4917.456) |
| vae_decode_start (node 175) → vae_decode_end | 1786495200808626236 → 1786495201211723334 | decode **380.235** (`decode_wall_ms`; timing `vae_decode_ms` 403.097) |
| output_collect_start | 1786495201802189687 | +591.0 |
| output_persist_start → end | 1786495201804170846 → 1786495201815109107 | **10.868** (hashes=1, items=1) |
| output_collect_end | 1786495203245282012 | collection **1443.092** |
| final_result_received | 1786495208687788700 | command → response **115,652.8** ms |

**R2 / R3 key deltas (same serial chain, same event order):**
- R2 (request `…-f07b52741389`): lookup 213.84; encode loop 3129.082; store 1668.254;
  prefill 3359.881; bind 17.667 + to 2230.805; graph gap after encode_end **+1068.9**;
  complete→sampling_start 191.1; sampling 4882.549; decode 372.476; collect 836.1;
  restore 611.847; c2r 108254.0.
- R3 (request `…-cf1174c2f501`): lookup 162.962; encode loop 2205.073; store 932.587;
  prefill 2380.969; bind 18.726 + to 2279.842; graph gap after encode_end **+980.0**;
  complete→sampling_start 180.1; sampling 4905.126; decode 363.225; collect 847.82;
  restore 554.0; **c2r 35888.7** (−79.8 s vs R1 — platform scheduling variance, not
  measured compute).

Restore window (R1): `v2_bootstrap_restore_start` 1786495186124659760 →
`v2_bootstrap_restore_end` 1786495186575188205, snapshot restore
1786495186124865630 → 1786495186575070075; `timing.restore_total_ms=476.994`
(authoritative; `snapshot_restore_ms=450.2`). All 3 runs cold: `restore_count=1`.

---

# Overlap analysis

**Current overlap: 0 ms (measured).** Direct math on mono timestamps (same clock):

```
overlap = max(0, min(enc_end, load_end) − max(enc_start, load_start))
```

with `enc_start/enc_end` = `execution_prefill_encode_start` /
`clip_conditioning_cache_decision` and `load_start/load_end` = `unet_fast_disk_bind_start` /
`unet_fast_disk_to_end`:

| Run | enc window (wall ns) | load window (wall ns) | overlap |
|---|---|---|---|
| R1 | 1786495189196823301 → 1786495191511972727 | 1786495192562610354 → 1786495194807731128 | **0.0 ms** |
| R2 | 1786495481998021118 → 1786495485121052935 | 1786495486192060093 → 1786495488440809486 | **0.0 ms** |
| R3 | 1786495543803095145 → 1786495546008056086 | 1786495546989821791 → 1786495549288684365 | **0.0 ms** |

The CLIP window ends well before the fast-disk `bind` even starts (R1: decision ends
1,049 ms before `defer`), so the transfer is entirely post-prefill.

**How much additional overlap is safely possible.** The fast-disk `to()` is
bandwidth-bound and CPU-light (the CPU phase of the load is get_model ≈31–33 ms +
ctor ≈0.14 ms; the 2.2–2.3 s is H2D transfer). It could in principle be started
concurrently with the prefill encode/store. The `encode_end → defer` gap
(980.0 / 1048.9 / 1068.9 ms) is scheduling time to the graph UNETLoader node — dead
time that overlap would eliminate. Remaining **serial critical path** after any such
change: bind ≈18–20 ms + to ≈2.23–2.28 s + graph GPU load ≈44 ms + sampling warmup
(first CUDA op 117.6–136.3 ms; first sampler step +1.18 s).

**Answer: none of the UNET loader is currently hidden by CLIP work.** The 2.25–2.30 s
transfer is fully exposed between prefill completion and graph sampling readiness.

---

# Production latency implication

**New-prompt budget from measured values only** (min/max across the 3 runs):

| Stage | Measured range | Class |
|---|---|---|
| Cache lookup | 0.16–0.47 s | potentially overlappable (RPC wait) |
| CLIP encode node | 1.27–1.45 s | potentially overlappable |
| Cache store | 0.93–1.67 s | potentially overlappable |
| **Prefill total** | **2.38–3.36 s** | serial block today |
| Native fast-disk UNET bind+to | **2.25–2.30 s** | serial block today; the high-value target |
| Sampling (8 steps) | **4.88–4.92 s** | unavoidable serial compute |
| VAE decode | ≈0.36–0.38 s | unavoidable serial compute |
| Output collection | ≈0.8–1.4 s | measured work |
| **Request-side compute** | **≈10.8–12.6 s** | sum of the above |
| Command→response | **35.9–115.7 s** | dominated by platform scheduling (restore-plan publish / cold-container scheduling: R1 78.2 s publish, R3 far faster), not measured compute |

Notes:
- **Measured work:** the prefill, fast-disk load, sampling, VAE, and output numbers above.
- **Potentially overlappable:** lookup, CLIP encode, and store (≈3–4 s today) could run
  concurrently with the fast-disk `to()`, which is CPU-light.
- **Unavoidable serial:** sampling 4.88–4.92 s + VAE ≈0.38 s + output ≈0.8–1.4 s
  (≈6.2–6.6 s floor) plus bind ≈20 ms + graph GPU load ≈44 ms.
- **Scheduling (not compute):** c2r variance 35.9 → 115.7 s is platform/restore-plan
  publish dominated; R3's faster scheduling shows the same code path completing the
  same work in a third of the wall time.

---

# Recommended next action

**One action: run a gated experiment that starts the native fast-disk UNET bind+to at
execution-prefill start (concurrent with CLIP encode/store) instead of at the graph
UNETLoader node, and re-measure the direct-timestamp overlap.**

This is the single highest-value next step: today the CLIP↔UNET overlap is measured at
**0 ms** and the fast-disk `to()` is a **2.25–2.30 s serial** block that starts only
after the prefill ends and the graph reaches the UNETLoader node (plus the 980–1069 ms
scheduling gap). The transfer is bandwidth-bound and CPU-light, so starting it when the
prefill lane begins could hide most of it under the CLIP miss work. The change and its
implementation remain loader-agent-owned; this task measured only, and the next run must
again verify overlap from raw mono timestamps (same formula as above).

---

# Integrated Sampling Deep Profile

Artifact present and `status=ok`, `level=blocks`, `schema_version=1` in all 3 runs
(`sampling_deep_profile` events; full JSONs dumped alongside the run artifacts).
**8 steps**, **17 evals** = **10 compute / 7 skip / 0 unknown**, matching the expected
17 / 10 / 7 exactly in every run.

**Reconciliation (R1/R2/R3):** `sampling_total_ms` 4917.454 / 4882.541 / 4905.120 —
reconciles exactly with the authoritative `sampling_start → sampling_end` event pair
(4917.456 / 4882.549 / 4905.126). setup_ms 57.359 / 50.005 / 51.02; teardown_ms
6.78 / 7.377 / 5.707 (incl. `teardown_final_eval_ms` 2.615 / 3.016 / 1.981);
`sampling_residual_ms=0.0`, `residual_status=ok`.

**Per-step totals (R1/R2/R3, ms):**
R1 `[1128.7, 926.9, 469.7, 475.4, 470.5, 459.1, 459.0, 463.9]`
R2 `[1130.9, 921.1, 468.9, 467.7, 467.6, 456.5, 456.7, 455.6]`
R3 `[1133.0, 931.4, 471.0, 469.7, 470.0, 458.6, 456.5, 458.3]`

**Per-step decomposition (R1, from `reconciliation.steps_ms`):**

| Step | pre_model | eval0 | gap | eval1 | post_model | total |
|---|---|---|---|---|---|---|
| 0 | 0.0 | 618.6 | 45.8 | 462.5 | 1.8 | 1128.7 |
| 1 | 3.6 | 451.6 | 13.0 | 457.4 | 1.3 | 926.9 |
| 2 | 2.3 | 3.3 | 12.8 | 450.4 | 0.9 | 469.7 |
| 3 | 2.2 | 8.0 | 13.4 | 450.8 | 1.2 | 475.4 |
| 4 | 1.9 | 2.9 | 13.3 | 450.9 | 1.6 | 470.5 |
| 5 | 2.3 | 3.0 | 1.4 | 451.3 | 1.2 | 459.1 |
| 6 | 2.5 | 3.3 | 1.3 | 450.6 | 1.2 | 459.0 |
| 7 | 2.6 | 7.4 | 1.7 | 451.0 | 1.2 | 463.9 |

**Per-eval (R1; ms / compute-or-skip):**

| Eval | ms | compute/skip | Eval | ms | compute/skip |
|---|---|---|---|---|---|
| e0 | 618.6 | compute | e9 | 450.9 | compute |
| e1 | 462.5 | compute | e10 | 3.0 | skip |
| e2 | 451.6 | compute | e11 | 451.3 | compute |
| e3 | 457.4 | compute | e12 | 3.3 | skip |
| e4 | 3.3 | skip | e13 | 450.6 | compute |
| e5 | 450.4 | compute | e14 | 7.4 | skip |
| e6 | 8.0 | skip | e15 | 451.0 | compute |
| e7 | 450.8 | compute | e16 | 2.6 | skip (final teardown eval) |
| e8 | 2.9 | skip | | | |

**Pattern (identical in all 3 runs):** compute evals **e0–e3, e5, e7, e9, e11, e13,
e15** (10); skip evals **e4, e6, e8, e10, e12, e14, e16** (7). CacheDiT
`discoverable=True`, `call_count=17`, `compute_count=10`, `skip_count=7`,
`warmup_steps=3`, `skip_interval=2`, expected `17/10/7` pinned True — all runs.

**Compute vs skip timing totals (ms):** R1 compute 4695.1 / skip 30.5; R2 4682.2 /
15.4; R3 4699.6 / 16.1.

**NextDiT block categories (R1/R2/R3):**

| Category | R1 | R2 | R3 |
|---|---|---|---|
| attention | 728.183 | 724.77 | 728.644 |
| mlp | 268.785 | 268.947 | 266.684 |
| norm | 70.919 | 65.122 | 64.903 |
| embeddings | 61.877 | 62.391 | 63.328 |
| refiner | 106.771 | 104.171 | 111.471 |
| output | 4.663 | 4.239 | 4.572 |
| norm_gate_residual (**DERIVED**) | 670.951 | 689.303 | 689.585 |

`norm_gate_residual_ms` is **derived** (`total − attention − mlp − norm`), not directly
timed — it covers unhookable gate/modulate/residual-add ops and launch/other gaps.

**CUDA per-block timings (30 NextDiT blocks):** per-block total ≈139–140 ms
(attention ≈77.2 ms, mlp ≈55.7 ms, norm ≈1.95 ms; block 0 slightly higher: total
139.5–140.3, attn 77.3–77.8, mlp 55.8–56.2, norm 2.1–2.15). Embedders:
`t_embedder` ≈55.6–58.6, `cap_embedder` ≈3.6–4.4, `x_embedder` ≈1.1–1.4 ms.
Refiner: `noise:0` ≈144–148, `noise:1` ≈133–134, `context:0` ≈75–81, `context:1`
≈6.2–6.5 ms. `output:final_layer` ≈1.4 ms. Forward total ≈4648–4656 ms.

**Observation-only note:** the deep profile adds **one** `torch.cuda.synchronize` after
`sampling_end` (`placement=post_sampling_end_cleanup`, cuda_sync_ms 0.026–0.036, no
inner syncs during the window) and does not touch CacheDiT tensors (CUDA events are
recorded around GPU-bearing spans only, realized after the authoritative sampling_end
event, outside the sampling window).
