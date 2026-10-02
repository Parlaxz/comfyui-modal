# V2 Cached→First-Node Production Defaults and Restore Characterization

Accepted deployment: `b557b2401f293223` (custom-node generation `ff3a26d75ca51ece`, ComfyUI `f49bdb655707b979`, restore-only shadow app, UNET excluded from CPU snapshot, RTX PRO 6000 / 12 CPU / 32768 MB, cloud/region unrestricted, single-use cold).

## Executive result

1. **cached→first-node: 1471 ms → 0.8 ms (RUN 3, memo-hit).** The ~1.47 s interval was proven to be **shifted work, not new work (option B/C)**: the prompt-signature memo hit skipped `add_keys`, which used to implicitly warm `folder_paths`/`INPUT_TYPES` caches; the topo walk then paid the cold Modal-volume `INPUT_TYPES()` cost (~1471 ms, reproduced on RUN 2 of the first sequence). Fix: restore-time folder warm + plan-receipt input-types warm (advisory) **plus a deterministic per-identity `topo_lazy` memo** persisted in the signature-memo store. RUN 3: `c2f_cached_to_first_node_ms=0.814`, `c2f_topo_input_info_ms=0.125`, `topo_lazy_hits=36`.
2. **Both proven optimizations are now production defaults:** `COMFYMODAL_V2_PROMPT_SIGNATURE_CACHE` and `COMFYMODAL_V2_CONDITIONING_CACHE_PREFETCH` are **enabled when unset**, disabled only by explicit `0`. Live proof without any manual flag: RUN 3 `signature_cache_hit=True source=volume` and conditioning `exact_hit manifest_memory_hit=1 payload_memory_hit=1`.
3. **Restore characterization (5 ordinary production-equivalent runs):** pre-Python snapshot restore min/median/max = **2.477 / 3.602 / 6.166 s**; Python restore = **0.953 / 1.145 / 3.214 s**; production-adjusted TOTAL WALL = **15.857 / 16.821 / 39.388 s** (the 39.4 s run is a valid slow-host outlier on GCP/us-east4 with 101.3 s scheduling).
4. **Sub-14 assessment: NOT consistently achievable on the measured set.** Best production-adjusted wall observed is 15.857 s (R2) and 16.734 s (RUN 3). Even with platform restore at its healthy floor (~2.5 s), application-after-resume alone is ~12.3 s (sampling 4.8 s + H2D 2.2 s + checkpoint read 1.2 s + VAE/PNG/handoff ~3 s), putting the realistic floor at ~15.5–16 s. Sub-14 is blocked by the combination of platform restore latency and the current application-after-resume profile, not by any remaining PromptExecutor cost (now 0.8 ms).

---

## Pre-flight PNG artifact reconciliation

### Stale metadata root cause

The previous task's report (`V2_PROMPT_CACHE_CONDITIONING_PREFETCH_AND_STARTUP_REPORT.md`, "Exact result artifacts" section) listed the RUN 3 artifact as `2,874,640 B / sha 895deda228cc…`. That value is the **level-6 reference size** (per the PNG task report: "the accepted level-1 size signature (+8.9% vs the level-6 reference 2,874,640 B)"). The RUN 3 log line and the run artifact both carry the level-1 values; the artifact-summary section in the previous report was stale report-only metadata (level-6 reference pasted into the RUN-3 summary).

### Correct authoritative output identity

Authoritative RUN 3 (previous task, request `v2-benchmark-0-f6b195e0536b`) output identity, cross-checked across three sources:

| Source | compress_level | bytes | SHA-256 prefix |
|---|---|---|---|
| `v2_pcc_run_3_final_capture.log` `[v2.png_output]` | 1 | 3,129,718 | `20b10e1f…` |
| `run_0.json` asset_id / byte_count | 1 | 3,129,718 | `20b10e1f…` |
| Previous report diagnostic section | 1 | 3,129,718 | `20b10e1f…` |

**Correct identity = 3,129,718 B / `20b10e1f99831bc758d9df82f43ce0beb1cbc636a740d11a29eb2bffe90e5260` / 1088×1920 / compress_level=1.** The `895deda…/2,874,640 B` line in the previous report's artifact-summary section was corrected to the authoritative values (report-only fix; no code change; PNG behavior untouched — level 1 remains the production default).

---

## Task 1 — cached to first node

### Exact code path

Boundary events (custom-node milestone wrappers in `modal_app.py`): `execution_cached` closes `execution→cached`; the first `send_sync("executing")` closes `cached→first-node`. Between them the parent `execution.py:758-774` runs:

```
ExecutionList(dynamic_prompt, caches.outputs)      # graph.py:193-203
for node_id in execute_outputs: execution_list.add_node(node_id)
    TopologicalSort.add_node                       # graph.py:138-166
        per link: self.get_input_info(...)         # graph.py:158 → class_def.INPUT_TYPES()
                  + output_cache.get_local(...)    # graph.py:206 → keys/`in self.cache`
while not is_empty: stage_node_execution()         # graph.py:236-267
execute(...) → get_input_data → send_sync("executing")
```

The dominant cost is `TopologicalSort.add_node`'s per-link `get_input_info` → `class_def.INPUT_TYPES()` → `folder_paths.get_filename_list` → **cold Modal-volume `recursive_search`** (a local SSD probe proved the walk itself is ~6 ms with warm caches; the container paid ~30 ms per unique class/input pair).

### Breakdown

RUN 3 (authoritative):

```
[ v2.prompt_executor_breakdown ] exec_to_cached_ms=13.455
  dynamic_prompt=0.004  is_changed=absent  signature_keys=absent  clean_unused=0.016
  cache_gather=0.131  cleanup_gc=1.181  residual=12.123
  c2f_cached_to_first_node_ms=0.814
    c2f_topo_walk_ms=0.594   (c2f_topo_input_info=0.125 + c2f_topo_other=0.469)
    c2f_stage_ms=1.323  c2f_first_node_prefix_ms=0.192  c2f_residual_ms=-1.295
  signature_cache_hit=True source=volume reuse_ms=3.473  topo_lazy_hits=36
```

Children reconcile: 0.594 + 1.323 + 0.192 = 2.109 vs parent 0.814 → residual −1.295 ms (boundary overlap of the stage stamp; within tolerance).

### Root cause

**B/C — work that existed before, moved by the signature-cache control flow.** Total PromptExecutor/cache setup was ~1.46–1.48 s both before and after the signature memo; only the attribution window moved:

- Before memo (compute path): `exec_to_cached` ≈ 1.34 s (`signature_keys`, which implicitly warmed `folder_paths` via `include_unique_id_in_input` → `INPUT_TYPES()`), then topo walk 112–506 ms (warm).
- After memo hit (RUN 2 of the first sequence): `exec_to_cached` ≈ 6–11 ms, topo walk **1086–1471 ms** (cold `INPUT_TYPES()` folder scans; the memo hit skipped the implicit warming).

Not new CPU work (local probe: walk = 6 ms), not a measurement bug (breakdown reconciles), not pure variance (five memo-hit runs all ≥1086 ms). The `folder_paths` strong cache is empty at restore; `get_filename_list` falls through to `recursive_search` on the Modal volume.

### Was the 1.47 s real, shifted, or variance?

**Real, shifted (B/C), reproducible, and fully removable.** The work always existed; the signature memo's hit path moved it into the topo walk. The first optimization attempt (daemon warm threads + request-scoped `get_input_info` memo) only partially fixed it: RUN 1 of that sequence (compute miss) showed 139.5 ms because the compute-miss `add_keys` warmed the caches; RUN 2 (memo hit) regressed to 1177 ms because the warm threads **lost the race** against the executor. Per the task protocol this was treated as a structural gap: STOP → fix → restart from RUN 1.

### Optimization design

Same philosophy as the signature memo — **exact identity, fail closed, legacy fallback, no semantic weakening**:

1. **Restore-time folder warm** (`execution_warm.warm_registered_folders`, daemon at `restore()`): calls `folder_paths.get_filename_list` for every registered folder. Advisory.
2. **Plan-receipt input-types warm** (`warm_classes_input_types`, daemon at plan receipt): calls `INPUT_TYPES()` for every distinct class in the prompt. Advisory.
3. **Deterministic `topo_lazy` memo** (the actual gate): the topo walk consumes **only** `extra_info["lazy"]` from `get_input_info` (graph.py:158-159). On the compute-miss request the patch accumulates `(class_type, input_name) → lazy` and persists it once, atomically, under the **same identity_hash** as the signature memo (`{identity: {"nodes": …, "topo_lazy": {class_type: {input_name: {"lazy": bool}}}}}`). On memo-hit requests the patched `TopologicalSort.get_input_info` returns `(None, None, {"lazy": bool})` **without calling `INPUT_TYPES()`**. Any missing entry, identity drift, malformed store, or exception → original `INPUT_TYPES()` path. The module-level `graph.get_input_info` used by execution.py validation is untouched.

### Correctness gates

- Lazy flag is a structural property of the class definition (registry-proof-gated by the same identity); folder contents never influence it — memoizing it is semantically safe.
- Only the walk's consumption (`extra_info["lazy"]`) is replayed; the triple shape `(None, None, {"lazy": …})` is behavior-identical for `add_node`.
- Fail-closed on: missing entry, `identity_hash` absent, non-bool stored value, any exception.
- Everything not memoized (exec→cached cache setup, `clean_unused`, gather walk, staging) still runs unmodified.

### RUN 1

`v2-benchmark-0-62e83ee5bc25` · GCP/us-east1 · **first request on the new deployment** (expected signature-cache compute miss; memo + `topo_lazy` persisted). `exec_to_cached=1981.8 ms` (signature_keys 1973.2, fallback=no_entry), `c2f=763.5 ms` (includes the one-time `topo_lazy` atomic persist write-back, 240.8 ms, inside the walk timer), `topo_lazy_pending=36`. All gate items PASS: waterfall formatting, scheduling excluded (1.337 s), reconciliation 7.786 ms, real checkpoint read 2.220 s, real H2D 2.844 s, PNG level1 byte-identical, Step-3 `plan_validation_fast_path consumed=true`.

### RUN 2

`v2-benchmark-0-863067b3e311` · GCP/us-east1 · **structural proof of the deterministic path:** `signature_cache_hit=True source=volume`, `exec_to_cached=5.584 ms`, **`c2f=0.563 ms`** (`c2f_topo_input_info_ms=0.079` — no `INPUT_TYPES` paid), conditioning `exact_hit` 53.429 ms with `manifest_memory_hit=1 payload_memory_hit=1 payload_memory_source=key_hit prefetch_source=full`, Step-3 consumed, PNG byte-identical, real checkpoint read 1.145 s + H2D 2.227 s. **RUN 2 STRUCTURAL CHECK: PASS.**

### RUN 3

`v2-benchmark-0-1e4dd9f0c110` · GCP/us-east1 · **authoritative real capture** (full waterfall printed at the end of this report). **RUN 3 REAL CAPTURE: PASS.**

### Before/after

| Metric | Before (previous task RUN 3) | RUN 3 (this task) | Saving |
|---|---:|---:|---:|
| exec→cached (signature keys) | 1341.8 ms compute / 6.1 ms memo-hit | 13.455 ms (hit) | memo proven |
| cached→first-node (topo walk) | **1471.0 ms** | **0.814 ms** | **~1.47 s** |
| of which `INPUT_TYPES` | 1470.99 ms | 0.125 ms | ~1.47 s |
| PromptExecutor/cache setup (stage 7) | 1.478 s | 15.081 ms | ~1.46 s |

### Remaining cost

~0.8 ms cached→first-node = 0.47 ms graph-walk rest + 0.13 ms memoized input-info + 1.3 ms stage + prefix; the topo-lazy persist write-back (~240 ms) is paid once per deployment on the compute-miss request only (same as the signature memo write-back).

---

## Task 2 — production defaults

### Prompt signature cache

`_signature_memo_enabled()` (runtime_executor.py) now reads `env_flag("COMFYMODAL_V2_PROMPT_SIGNATURE_CACHE", default=True)`; the `_runtime_env` deploy-time passthrough default is `"1"`. The fail-closed path is unchanged: identity completeness, `inputs_hash` match, non-False `is_changed` revalidation, atomic volume persistence, and original `add_keys` fallback on any uncertainty.

### Conditioning prefetch

`maybe_prefetch_conditioning` (model_preload.py) now gates on `env_flag(ENV_PREFETCH, default=True)`; the deploy-time passthrough and the container evidence read default to `"1"`. All correctness machinery preserved: canonical-key validation, model-identity validation, payload SHA, per-tensor integrity, bounded join (1.5 s default), cold fallback, serve-by-components.

### Default semantics

| Env value | Signature cache | Conditioning prefetch |
|---|---|---|
| unset | **enabled** | **enabled** |
| `0` | disabled (original add_keys) | disabled (`env_off`) |
| `1` | enabled | enabled |

### Disable overrides

Explicit `0` disables each feature independently (verified in tests and preserved in the allowlist + `_runtime_env` passthrough). No other value semantics changed.

### Tests

`tests/test_v2_prompt_signature_cache.py` — 4 new default-semantics tests (UNSET→enabled, UNSET+missing identity→fail closed, `0`→disabled, `1`→enabled); `tests/test_v2_conditioning_prefetch.py` — new `TestMaybePrefetchConditioningEnvDefault` (UNSET→attempted, `0`→env_off, `1`→enabled) exercising the real env var (no `env_flag` patch). **1500 passed** across the required suite; the topo-lazy store gained 5 tests (round-trip, persist/reload, old-format compat, fail-closed) and the breakdown line 1 test (fields render/absent).

### Live proof

RUN 3 (no manual flag anywhere in the deployment or run environment): `signature_cache_requested=True eligible=True hit=True source=volume` and conditioning `decision=exact_hit prefetch_requested=1 prefetch_source=full manifest_memory_hit=1 payload_memory_hit=1`.

---

## Task 3 — restore characterization

### Timing definitions

- **Scheduling** = submission attempt → Modal restore-begin (`scheduling_source=modal_app_log`), excluded from TOTAL WALL.
- **Pre-Python snapshot restore** = restore-begin → Python resume (platform-only).
- **Python restore** = Python resume → restore end (`[v2.restore_deep]` decomposition).
- **TOTAL WALL** = command→response minus scheduling.
- **Production-adjusted TOTAL WALL** = TOTAL WALL − benchmark-only `node_registry_init` (host registry load; the only benchmark-only startup cost; scheduling is NOT subtracted again, and pre-Python/Python restore and application work are NOT subtracted).
- **Application after Python resume** = TOTAL WALL − registry − pre-Python restore − Python restore (the production-relevant application path).

### Scheduling

Excluded everywhere (never in TOTAL WALL). Observed 1.606–101.311 s across the 5 runs; the 101.3 s run (us-east4) is platform admission variance, valid evidence, not discarded.

### Pre-Python restore

2.477–6.166 s across the 5 runs (median 3.602 s). Platform-side; only non-invasively enriched this task (trace metadata now surfaces `cpu_request`/`gpu_type` alongside the existing provider/region/image/container-task/RSS fields; snapshot_id remains unavailable per Modal 1.4.3 — documented limitation).

### Python restore

0.953–3.214 s (median 1.145 s). Decomposed by `[v2.restore_deep]` (identity, configure_runtime, bootstrap_restore, restore_finalize, residual). The 3.214 s run's expand is bootstrap/restore_finalize on a slow host (same run as the 39.4 s wall outlier). No single run exceeded 2 s on a healthy host; the one >2 s run is reported as-is, not conflated with platform restore.

### Production relevance

All five runs used the same accepted production config: restore-only shadow app, snapshot CLIP+VAE retained / UNET excluded (→ real request-time checkpoint read), native fast-disk UNET, single-use cold containers, RTX PRO 6000 / 12 CPU / 32768 MB, cloud/region unrestricted, no pins, no warm pool, PNG level 1. Benchmark-only costs (registry init 18.2–21.7 s) are subtracted in the production-adjusted figure only.

### RUN 3

`v2-benchmark-0-1e4dd9f0c110` · GCP/us-east1 · scheduling 2.704 s (excluded) · pre-Python restore 2.839 s · Python restore 2.014 s · application-after-resume ≈ 11.88 s · raw TOTAL WALL 38.941 s · production-adjusted 16.734 s.

### Five ordinary restore runs

| Run | Provider/Region | Scheduling | Registry init | Pre-Python restore | Python restore | App after resume | Raw TOTAL WALL | Production-adjusted TOTAL WALL |
| --- | --------------- | ---------: | ------------: | -----------------: | -------------: | ---------------: | -------------: | -----------------------------: |
| R1 | GCP/us-east1 | 1.998 s | 21,740.5 ms | 3,188.0 ms | 1,145.0 ms | 12,064.5 ms | 38.138 s | 16.398 s |
| R2 | GCP/us-east1 | 4.377 s | 21,395.8 ms | 2,477.0 ms | 1,076.0 ms | 12,304.2 ms | 37.253 s | 15.857 s |
| R3 | GCP/us-east4 | 101.311 s | 21,108.9 ms | 6,166.0 ms | 3,214.0 ms | 30,008.1 ms | 60.497 s | 39.388 s |
| R4 | GCP/us-east1 | 52.240 s | 18,188.8 ms | 3,602.0 ms | 1,287.0 ms | 13,214.2 ms | 36.292 s | 18.103 s |
| R5 | GCP/us-east1 | 1.606 s | 19,427.2 ms | 4,100.0 ms | 952.9 ms | 11,769.0 ms | 36.249 s | 16.821 s |

### Distribution

```
Pre-Python restore:
min = 2477.0 ms
median = 3602.0 ms
max = 6166.0 ms

Python restore:
min = 952.9 ms
median = 1145.0 ms
max = 3214.0 ms

Production-adjusted TOTAL WALL:
min = 15857.2 ms
median = 16821.5 ms
max = 39388.1 ms
```

Sorted production-adjusted values: 15.857 / 16.398 / 16.821 / 18.103 / 39.388 s (five runs — too small for p95; no p95 presented).

### Provider/region observations

R3 (us-east4) is the only non-us-east1 run and the only extreme outlier on every axis (101.3 s scheduling, 6.2 s pre-Python restore, 3.2 s Python restore, 39.4 s production-adjusted). The four us-east1 runs are tight: production-adjusted 15.86–18.10 s. This is consistent with region/host variance; it is valid evidence and was not discarded.

---

## Production-adjusted TOTAL WALL

For each run: `production_adjusted = TOTAL WALL − node_registry_init` (registry init is the only benchmark-only startup cost; scheduling is already excluded from TOTAL WALL; restores and application work are production-relevant and kept). The metric is computed from the host-reconciled waterfall's `total_wall_ms` (the fixer's first version used the execute_plan perf base, which included scheduling; corrected mid-sequence and the sequence restarted from RUN 1 per protocol).

```
min = 15.857 s   median = 16.821 s   max = 39.388 s   (5 runs)
RUN 3 (authoritative) = 16.734 s
```

## Sub-14 assessment

**Can production-adjusted non-scheduling TOTAL WALL plausibly be consistently <14 s? NO — not with the measured set.**

Breakdown of the healthy floor (RUN 3 and R1/R2/R5, all us-east1):

| Component | Healthy range (4 runs) | RUN 3 |
|---|---:|---:|
| Pre-Python restore (platform) | 2.477–4.100 s | 2.839 s |
| Python restore | 0.953–1.287 s | 2.014 s |
| Application after Python resume | 11.769–13.214 s | ~11.88 s |
| **Production-adjusted TOTAL WALL** | **15.857–18.103 s** | **16.734 s** |

The application-after-resume block alone is ~12 s on healthy runs (sampling 4.8 s + UNET H2D 2.2 s + checkpoint read 1.2 s + VAE/PNG/handoff ~3 s — all production-real). Adding the platform restore floor (~2.5 s) and Python restore (~1 s) puts the realistic floor at **~15.5–16 s**. Even a zero-latency restore would leave ~13 s of application work — barely under 14 s and only on the luckiest host. Conclusion: **sub-14 production-adjusted is not currently achievable; it is blocked by the combination of platform pre-Python restore latency (2.5–6.2 s) and the current application-after-resume profile (~12–13 s)**. It is not "already achievable" and not merely "plausible with healthier restores" on this evidence.

## Final recommendations

1. **Keep** the `topo_lazy` memo + warm threads (proven: cached→first-node 0.8 ms, fail-closed, identity-gated). 
2. **Keep** both production defaults (signature cache ON, conditioning prefetch ON; explicit `0` still disables).
3. **Do not** reopen Sampling, CacheDiT, SageAttention, 8-step, UNET pinned staging, VAE early overlap, async LRU, PNG, snapshot composition, GPU/CPU/RAM, cloud/region, warm pools, min_containers.
4. Sub-14 requires platform-side restore reduction (the only remaining lever in the measured model) plus a ~1–2 s application-after-resume trim; with the current set, the honest production floor is ~16 s (healthy host) with 18 s typical and occasional 39 s region outliers.

---

# Final RUN 3 waterfall (exactly as captured)

```
WATERFALL (host-reconciled)
V2 COLD WATERFALL - run 1 (local reconcile)
Request: v2-benchmark-0-1e4dd9f0c110  Instance: d8e493273b224322b676b61c0aa70c6f  GPU: ['RTX-PRO-6000']  Fresh: YES
Provider/Region: GCP/us-east1
TOTAL WALL:           38.941s   (command->response minus Modal scheduling)
COMMAND->RESPONSE:    41.645s

+-----+------------------------------------------------+------------+------------+----------+------------------------------------------+
|   # | Stage                                          |   Duration |       Cum. |        % | Relative wall (TOTAL WALL)               |
+-----+------------------------------------------------+------------+------------+----------+------------------------------------------+
|   1 | Local preparation                              | 511.513 ms | 511.513 ms |   1.314% | #                                        |
|   2 | Modal handle and submission                    |    22.340s |    22.852s |  57.369% | #######################                  |
|   3 | Modal pre-Python snapshot restoration          |     2.839s |    25.690s |   7.289% | ###                                      |
|   4 | Python/application restore                     |     2.014s |    27.704s |   5.172% | ##                                       |
|   5 | Restore-to-method entry                        |  32.802 ms |    27.737s |   0.084% | #                                        |
|   6 | Remote method setup                            | 370.300 ms |    28.107s |   0.951% | #                                        |
|     |   method entry to graph start                  | 285.644 ms |            |          |                                          |
|     |   method entry to runtime configuration        | 285.606 ms |            |          |                                          |
|     |   graph setup                                  |  84.656 ms |            |          |                                          |
|   7 | PromptExecutor/cache setup                     |  15.081 ms |    28.123s |   0.039% | #                                        |
|   8 | Pre-sampler execution                          |     3.501s |    31.623s |   8.990% | ####                                     |
|     |   Conditioning cache exact_hit lookup=37.626ms |  37.626 ms |            |          |                                          |
|     |   CLIP encode skipped (cache hit)              |          - |            |          |                                          |
|     |   Node: ImpactSwitch                           | 704.574 ms |            |          |                                          |
|     |   Node: ImpactSwitch                           |  29.796 ms |            |          |                                          |
|     |   Node: ClownsharKSampler_Beta                 | 116.062 ms |            |          |                                          |
|     |   Checkpoint read                              |     1.155s |            |          |                                          |
|     |   Read end -> construction done                |   0.157 ms |            |          |                                          |
|     |   UNET get_model                               |  43.360 ms |            |          |                                          |
|     |   Bind                                         |  20.645 ms |            |          |                                          |
|     |   Synchronized H2D (5.5 GB/s)                  |     2.248s |            |          |                                          |
|     |   H2D end -> UNET ready                        |   1.501 ms |            |          |                                          |
|   9 | Sampler node to sampling                       | 109.480 ms |    31.733s |   0.281% | #                                        |
|     |   lane acquired to actual stage                | 109.434 ms |            |          |                                          |
|  10 | Sampling                                       |     4.820s |    36.553s |  12.378% | #####                                    |
|  11 | Post-sampling / VAE transition                 | 726.650 ms |    37.279s |   1.866% | #                                        |
|  12 | VAE decode                                     | 383.077 ms |    37.663s |   0.984% | #                                        |
|     |   VAE load/H2D                                 | 746.846 ms |            |          |                                          |
|  13 | Output encode / descriptor                     | 245.556 ms |    37.908s |   0.631% | #                                        |
|     |   PNG encode                                   | 171.159 ms |            |          |                                          |
|  14 | Remote result handoff                          |     1.015s |    38.923s |   2.607% | #                                        |
|  15 | Local result handling / caller return          |  15.000 ms |    38.938s |   0.039% | #                                        |
+-----+------------------------------------------------+------------+------------+----------+------------------------------------------+
|     | SCHEDULING                                     |     2.704s |            |          |                                          |
|     | RECONCILIATION                                 |   2.721 ms |            |          |                                          |
|     | STATUS                                         |         OK |            |          |                                          |
+-----+------------------------------------------------+------------+------------+----------+------------------------------------------+
```

Captured diagnostics (RUN 3): `[v2.prompt_executor_breakdown]` exec_to_cached 13.455 / signature hit=True source=volume reuse 3.473 / c2f 0.814 (topo 0.594 = input_info 0.125 + other 0.469; stage 1.323; prefix 0.192; residual −1.295) / `topo_lazy_hits=36`. `[v2.conditioning_exact_hit_breakdown]` exact_hit lookup 37.626 / manifest_memory_hit=1 payload_memory_hit=1 payload_memory_source=key_hit prefetch_source=full prefetch_join 22.918 prefetch_join_timeout=0. `[v2.png_output]` compress_level=1 encode 171.147 compress 165.206 bytes=3129718 sha=`20b10e1f…`. Step-3 `plan_validation_fast_path consumed=true`. `[v2.folder_warm]` 1715.959 ms/29 · `[v2.input_types_warm]` 1097.004 ms/31. `production_adjusted_total_wall_ms=16733.654`.

### RUN 3 table

| Metric                         | RUN 3 |
| ------------------------------ | ----: |
| Scheduling                     | 2.704 s |
| Benchmark registry init        | 22.207 s |
| Pre-Python snapshot restore    | 2.839 s |
| Python restore                 | 2.014 s |
| PromptExecutor/cache setup     | 15.081 ms |
| execution→cached               | 13.455 ms |
| cached→first-node              | 0.814 ms |
| Conditioning exact-hit         | 37.626 ms |
| Pre-sampler                    | 3.501 s |
| Sampling                       | 4.820 s |
| VAE/post-sampling              | 726.650 ms |
| VAE decode                     | 383.077 ms |
| PNG                            | 245.556 ms |
| Result handoff                 | 1.015 s |
| Raw TOTAL WALL                 | 38.941 s |
| Production-adjusted TOTAL WALL | 16.734 s |

---

## Completion output

- Report path: `V2_CACHED_FIRST_NODE_PRODUCTION_DEFAULTS_AND_RESTORE_CHARACTERIZATION.md`
- Changed files: `comfymodal_runtime/execution_warm.py` (new), `comfymodal_runtime/prompt_signature_cache.py` (topo_lazy section), `comfymodal_runtime/runtime_executor.py` (topo-lazy patch, defaults, breakdown fields), `comfymodal_runtime/modal_app.py` (warm threads, defaults, metadata), `comfymodal_runtime/model_preload.py` (prefetch default), `tools/benchmark_v2_direct.py` (production-adjusted metric), `tests/test_v2_prompt_signature_cache.py`, `tests/test_v2_conditioning_prefetch.py`, `tests/test_v2_prompt_executor_breakdown.py`, `tests/test_v2_host_breakdown_lines.py`, `V2_PROMPT_CACHE_CONDITIONING_PREFETCH_AND_STARTUP_REPORT.md` (stale PNG metadata fix), evidence logs `v2_c2f_deploy_{1..5}.log`, `v2_c2f_run_{1_validation,2_post_snapshot,3_final_capture}.log`, `v2_c2f_restore_char_{1..5}.log`
- Commit hash: **none**
- Deployment count (this task): 5 invocations, 3 successful (deploy 2 `b636acdc5dfc7b79` superseded; deploy 4 `c20de18bd2b4165d` pre-topo-lazy; deploy 5 `b557b2401f293223` accepted)
- Generation-request count (this task): 11 (3 gate-sequence runs on deploy 2/4 incl. the structural-restart pair + RUN 1/2/3 on deploy 5 + 5 characterization runs)
- Failed RUN-1 gate attempts: 1 (first RUN 1 on the main shadow app, `v2-benchmark-0-d0b3a539a400` — gate failed on missing checkpoint-read/H2D rows because that deployment included the UNET in the snapshot; redeployed with the accepted restore-only composition)
- Accepted RUN-1 ID: `v2-benchmark-0-62e83ee5bc25`
- RUN-2 ID: `v2-benchmark-0-863067b3e311`
- RUN-3 ID: `v2-benchmark-0-1e4dd9f0c110`
- Restore-characterization run IDs: `v2-benchmark-0-b8c2f40a0791`, `v2-benchmark-0-3399313692ed`, `v2-benchmark-0-cd6e5a69bce1`, `v2-benchmark-0-e4c59be3dcc6`, `v2-benchmark-0-e3723247fb92`

```
RUN 1 GATE: PASS
RUN 2 STRUCTURAL CHECK: PASS
RUN 3 REAL CAPTURE: PASS
```

```
TASK 1 — CACHED -> FIRST NODE
before = 1471 ms
after = 0.814 ms (RUN 3 memo-hit; 0.563 ms RUN 2)
root cause = shifted work (B/C): memo-hit skipped add_keys, whose INPUT_TYPES()/folder_paths calls used to warm the caches; the topo walk then paid cold Modal-volume INPUT_TYPES() (1471 ms)
saving = ~1.47 s on the memo-hit path (PromptExecutor/cache setup 1.478 s → 15.081 ms)
correctness = exact identity, fail-closed, legacy fallback; lazy-flag-only replay; Step-3 consumed; PNG byte-identical; reconciliation ≤ 2.7 ms

TASK 2 — PRODUCTION DEFAULTS
prompt signature memo default = ON (unset→enabled; 0→disabled; 1→enabled)
conditioning prefetch default = ON (unset→enabled; 0→disabled; 1→enabled)
explicit disable verified = YES (tests + preserved env semantics)

TASK 3 — RESTORE CHARACTERIZATION
pre-Python restore min/median/max = 2.477 / 3.602 / 6.166 s
Python restore min/median/max = 0.953 / 1.145 / 3.214 s
production-adjusted TOTAL WALL min/median/max = 15.857 / 16.821 / 39.388 s
sub-14 assessment = NOT consistently achievable on the measured set (healthy floor ~15.9–16.8 s; app-after-resume alone ~12–13 s; blocked by platform restore 2.5–6.2 s + application profile)
```
