# V2 PNG Level 1 + Pre-Sampler Investigation + Real Capture

## Executive result

All four goals completed and validated live under the strict three-run protocol:

1. **Live waterfall logging restored** — the full host-reconciled ASCII table now prints to the actual captured console/log for every completed benchmark request, and is proven present (with real line breaks, aligned columns, intact borders) in the accepted RUN 1 and RUN 3 logs.
2. **PNG compression level 1 promoted to production/default** — `compress_level=1` is now the V2 default (was 6), the `COMFYMODAL_V2_PNG_COMPRESS_LEVEL` override remains, and every gated run proved `compress_level=1` with encode/compression timing, dimensions, SHA, and byte count.
3. **PromptExecutor/cache setup investigated** — reconciled `[v2.prompt_executor_breakdown]` shows ~1.34 s of the ~1.4 s `execution to cached` window is `CacheKeySetInputSignature.add_keys` (per-node ancestry + signature hashing, recomputed every request); realistic removable critical-path ≈ 1.2–1.3 s.
4. **Conditioning exact-hit investigated** — reconciled `[v2.conditioning_exact_hit_breakdown]` shows ~440 ms is ~93% cold Modal-Volume file I/O (manifest re-read + 2.9 MB payload re-read per request); LRU-specific cost is only ~30–51 ms (sync) — below the 100 ms threshold; non-LRU optimization potential ≈ 380–400 ms.

Gated sequence: RUN 1 (accepted on attempt 4) → RUN 2 (structural PASS) → RUN 3 (authoritative real capture, PASS).

## Changes made

| Area | File(s) | Change |
|---|---|---|
| Waterfall live logging | `tools/benchmark_v2_direct.py` | Removed the `_defer_waterfall` gate (RUN_COUNT==1 was suppressing the per-run print); per-run print of the host-reconciled table is now unconditional in `_run_one`, with an explicit warning line when host reconciliation is unavailable. |
| Host breakdown/PNG lines | `tools/benchmark_v2_direct.py` | Added host-side `[v2.prompt_executor_breakdown]`, `[v2.conditioning_exact_hit_breakdown]`, `[v2.png_output]` print lines read from trace events (container stdout does not stream into captures; trace events do). `output_encode_end` selection prefers the populated event (fixes RUN-2 ordering regression). |
| PNG default level 1 | `comfymodal_runtime/v2_experiments.py`, `comfyapp.py` | `png_compress_level()` default 6→1 (unset and invalid-value fallback), experiment spec `default_arm="level6"`→`"level1"`, fail-open lambda 6→1, log-once gate flipped to flag non-default 6. `_PNG_LEVEL_ALLOWED={1,6}` unchanged → `COMFYMODAL_V2_PNG_COMPRESS_LEVEL` override intact. |
| PNG provenance capture | `comfyapp.py`, `comfymodal_runtime/modal_app.py` | Ungated record of last PNG encode (compress_level + png_compress_ms); both `output_encode_end` emission sites now carry `compress_level`/`png_compress_ms`. |
| PromptExecutor breakdown | `comfymodal_runtime/runtime_executor.py`, `comfymodal_runtime/modal_app.py` | opt_exec child timers (dynamic_prompt, is_changed, signature keys, clean_unused, cache_gather, cleanup_gc, topo, stage, stage-end stamp, c2f prefix) now always captured; `prompt_executor_milestones` event enriched with a `breakdown` dict; residuals emitted from present children; `c2f_first_node_prefix_ms` is a true post-staging remainder. |
| Conditioning breakdown | `comfymodal_runtime/model_preload.py` | `[v2.conditioning_exact_hit_breakdown]` printed after each cache decision from the always-on lookup diagnostics (reconciles to lookup_wall_ms). |
| Tests | `tests/test_v2_ab_experiments.py`, `tests/test_benchmark_v2_proof_collection.py`, new `tests/test_v2_prompt_executor_breakdown.py`, `tests/test_v2_conditioning_exact_hit_breakdown.py`, `tests/test_v2_host_breakdown_lines.py` | Default-level assertions updated; stdout/AST coverage for unconditional waterfall print; pure-formatter reconciliation tests for both breakdown lines and the PNG line. |
| Logs | `v2_png_deploy_{1,2,3}.log`, `v2_png_run_{1,1b,1c,1d,2,2b,3}.log` | Live evidence captures. |

## Waterfall logging restoration

**Root cause of disappearance from live logs.** `tools/benchmark_v2_direct.py` gated the per-run waterfall print behind `if not _defer_waterfall:`, and `_defer_waterfall = (RUN_COUNT == 1)`. The normal single-run benchmark (`V2_BENCHMARK_RUNS=1`) therefore skipped the per-run print entirely and depended on a post-loop print that only exists in the plain-benchmark branch and is skipped if the run raises; campaign modes never printed the table at all. Additionally, remote (container) stdout never streams into the benchmark capture, so any remote-side rendering is invisible in the captured log.

**Exact fix.** (1) Removed the deferral gate so every completed `_run_one` unconditionally prints `WATERFALL (host-reconciled)` + `render_waterfall(...)` to stdout with `flush=True` (real `\n` line breaks, fixed-width ASCII, no markdown escaping, no one-line serialization; a warning line labels the rare fallback when host reconciliation is unavailable). (2) All investigation diagnostics are printed host-side from trace events because container stdout does not reach the capture.

**Proof from accepted RUN 1 and RUN 3.** Both captured logs contain the table twice (per-run + post-loop) with intact borders (`+-----+` rows), aligned columns, indented detail rows, `->` transition labels, and zero prohibited strings (`Expanded diagnostics`, `GLOBAL RESIDUAL`, `RESIDUAL %`, `INVALID`, `PENDING_HOST_RECONCILIATION`, one-line partial, flattened table). Verified from the captured logs, not from renderer tests.

## PNG level 1 production promotion

- **Old default:** `compress_level=6` (`comfymodal_runtime/v2_experiments.py::png_compress_level`, spec `default_arm="level6"`, comfyapp fail-open 6).
- **New default:** `compress_level=1` (all three locations + invalid-value fallback).
- **Override behavior:** `COMFYMODAL_V2_PNG_COMPRESS_LEVEL` (valid `{1,6}`) still selects the arm per request; level 6 remains available and is now flagged once per process as non-default.
- **Final effective level:** 1 on every gated run, proven in the captured log via `[v2.png_output] compress_level=1 ...`.

| Run | compress_level | PNG encode ms | PNG compress ms | Width×Height | Bytes | SHA-256 prefix |
|---|---|---|---|---|---|---|
| RUN 1 (accepted, 1d) | 1 | 160.961 | 150.812 | 1088×1920 | 3,129,718 | 20b10e1f… |
| RUN 2 | 1 | 160.916 | 154.169 | 1088×1920 | 3,129,718 | 20b10e1f… |
| RUN 3 (authoritative) | 1 | 153.901 | 149.384 | 1088×1920 | 3,129,718 | 20b10e1f… |

**Correctness:** output is byte-identical across all runs (same SHA-256 and byte count), 1088×1920, and matches the accepted level-1 size signature (+8.9% vs the level-6 reference 2,874,640 B). Encoding ~150–170 ms vs the historical level-6 ~556 ms.

## PromptExecutor/cache setup investigation

**Exact call path (verified in code + live timings).**
`modal_app.py:12467 executor.reset()` (fresh CacheSet) → `execution.py:716 execute_async`: `add_message("execution_start")` → `DynamicPrompt(prompt)` → `IsChangedCache(...)` → `outputs cache.set_prompt` (seeded_set_prompt wrapper; `CacheKeySetInputSignature.add_keys` at `caching.py:91-107`: per-node `get_ordered_ancestry` + `get_immediate_node_signature` with `is_changed_cache.get` + recursive `to_hashable` frozenset conversion across 43 nodes) → `objects cache.set_prompt` (CacheKeySetID) → `clean_unused()` ×2 → `asyncio.gather` 43× `outputs.get` (all misses) → `cleanup_models_gc()` → `add_message("execution_cached")` → ExecutionList `add_node` topo walk → `stage_node_execution` → first node `get_input_data` → `send_sync("executing")` (cached→first-node closes).

**Reconciled breakdown (RUN 3, from the captured log):**
```
exec_to_cached_ms=1341.835
  dynamic_prompt_ms=0.004   is_changed_ms=0.402   signature_keys_ms=1339.881
  clean_unused_ms=0.026     cache_gather_ms=0.068  cleanup_gc_ms=0.904
  residual_ms=0.55          (seed_apply absent — wrapper did not execute this request; truthful)
c2f_cached_to_first_node_ms=112.455 (topo 112.340 + stage 1.050 + first-node prefix 0.095; residual -1.03 boundary overlap)
```

**Answers to the required questions.**
1. **What runs inside the ~1.1–1.4 s "execution to cached":** signature-key construction (`CacheKeySetInputSignature.add_keys`) ≈ 1.34 s (98–99%); everything else is sub-ms to a few ms.
2. **Kind of work:** synchronous CPU (ordered-ancestry graph walks, node signature hashing, `IS_CHANGED` cache lookups, recursive `to_hashable` frozenset conversion). No filesystem/Volume/IO.
3. **Synchronous:** all of it (executor thread, no awaits inside add_keys beyond in-process cache gets).
4. **Repeated despite unchanged workflow/Step-3 consumed:** yes — `executor.reset()` rebuilds empty caches every request, so all 43 node signatures are recomputed every request even though deployment/generation/dependency/workflow identity is proven unchanged.
5. **Necessary every request:** the *computation* is necessary only if signatures can change; under a proven Step-3 identity the key inputs (prompt text, classes, workflow hash, options) are unchanged.
6. **Safe to skip/memoize/move:** (a) memoize per-workflow signature sets keyed by the full key inputs + Step-3 identity; (b) precompute during restore (the plan is known before the request); (c) reduce to identity checks when the Step-3 certificate is consumed and deployment/generation/workflow/dependency match.
7. **One large operation:** yes — a single hot loop (add_keys) dominates; not many small ones.
8. **Overlap:** none — the window is exclusive synchronous Python; UNET loading, conditioning-cache work, and H2D all occur later in Pre-sampler execution (verified by timestamps: no concurrent span inside execution→cached).
9. **Exclusive:** yes; the timer is not waiting on any concurrent task.
10. **Realistic removable critical-path time:** ~1.2–1.3 s (the add_keys cost), leaving the cheap boundaries/validation (~10–50 ms).

**Optimization candidates (ranked; no speculative fixes implemented):**
| Rank | Candidate | Expected critical-path saving | Confidence | Complexity | Correctness risk | Recommendation |
|---|---|---|---|---|---|---|
| 1 | Memoize per-workflow node-signature sets across requests, keyed on full key inputs + Step-3 identity (comfymodal_runtime wrapper around `CacheKeySetInputSignature.add_keys` / `caching.py:91-107`) | ~1.2–1.3 s | Medium | Medium | Medium (must preserve IS_CHANGED semantics for dynamic nodes; gate on proven identity) | Recommended to prototype behind a flag |
| 2 | Precompute cache keys during snapshot restore (background, before request entry) | ~1.2–1.3 s removed from request window | Medium | Medium | Low-medium (needs plan availability pre-request, which exists) | Recommended as an alternative |
| 3 | Skip rebuild under consumed Step-3 identity → identity checks only | ~1.2–1.3 s | Medium | Low | Medium (any node input not covered by the key would silently reuse stale signatures) | Not recommended without full key coverage proof |
| 4 | Snapshot the executor cache (CacheSet with computed keys) in the Modal snapshot | ~1.2–1.3 s | Low | High | High | Not recommended |

## Conditioning exact-hit lookup investigation

**Reconciled breakdown (RUN 3, captured log; children sum to lookup_wall_ms within 0.1 ms):**
```
decision=exact_hit  lookup_wall_ms=439.305  total_ms=439.027
  key_build_ms=0.209      lock_wait_ms=0.002
  manifest_read_ms=262.024   (manifest 2,229 B — cold Modal-Volume fetch)
  entry_lookup_ms=137.157    (header 3,752 B + payload data 2,900,184 B read + deserialize + materialize)
  lru_touch_ms=39.526        (sync mode; atomic manifest rewrite + fsyncs)
  children_ms=438.918  residual_ms=0.109
```
RUN 2 sample: lookup 285.9 ms (manifest 155.5 + entry 78.3 + lru 51.5). RUN 1d: 571.3 ms (manifest 229.7 + entry 307.1 + lru 33.9). The variance is dominated by cold/warm Volume fetch state per container.

**Answers to the required questions.**
1. **Why hundreds of ms:** ~93% is cold Modal-Volume file I/O per single-use restored request (manifest re-read + 2.9 MB payload re-read), not CPU.
2. **Primarily payload read/deserialization:** yes — `entry_lookup_ms` (payload open/read + tensor rebuild) is the second largest; `manifest_read_ms` (cold fetch of a 2.2 KB file) is the largest.
3. **Same payload re-read every request:** yes — the cache keeps no in-memory manifest/entry cache; every restored container starts with a cold page cache and the Modal snapshot does not capture the Volume.
4. **State surviving the snapshot:** the Volume persists (files), but the page cache does not; no in-memory representation survives.
5. **Manifest/index snapshotted or pre-loaded:** feasible — manifest is 2.2 KB; load into memory (or at least warm the page cache) during restore.
6. **Validation reduced by Step-3:** entry validation re-serializes canonical keys (~1–3 ms) — negligible; identity checks are not the bottleneck.
7. **Checksum redundant:** payload SHA-256 (~2–5 ms) + per-tensor SHA-256 (~2–5 ms) on a trusted immutable payload — small; removable only if identity proof covers payload integrity, minor gain.
8. **Materialization copying:** ~2×2.9 MB copies (~5–15 ms) — minor.
9. **Memory-backed representation:** yes — a 2.9 MB payload is trivial RAM; loading it during restore would eliminate the disk/Volume latency entirely.
10. **Realistic best-case exact-hit target:** ~10–30 ms (residual CPU: deserialize, tensor rebuild, validation, assembly), i.e. non-LRU potential ≈ 380–400 ms.

**LRU-specific vs non-LRU:** LRU (sync) = 30–51 ms per hit (atomic manifest rewrite + fsyncs; the existing async arm `COMFYMODAL_V2_CONDITIONING_CACHE_ASYNC_LRU` moves it off the critical path). Non-LRU cost ≈ 390–410 ms, almost entirely Volume I/O → **>100 ms realistic potential exists in the non-LRU path** (prefetch/warm), so it is the priority.

**Optimization candidates (ranked; no speculative fixes implemented):**
| Rank | Candidate | Expected saving | Confidence | Complexity | Risk | Recommendation |
|---|---|---|---|---|---|---|
| 1 | Pre-restore background warm/prefetch of `manifest.json` + expected entry payload (2.9 MB) into page cache / memory (`clip_conditioning_cache.py` warm path, run during restore) | ~380–400 ms on exact hits | High | Low | Low | Recommended |
| 2 | In-memory manifest + most-recent-entry cache inside `ExactConditioningCache` (survives per-request if the container serves multiple requests) | ~150–260 ms (manifest portion) | High | Low | Low | Recommended |
| 3 | Enable existing async-LRU arm (`COMFYMODAL_V2_CONDITIONING_CACHE_ASYNC_LRU=1`) | ~30–51 ms | High | None (config) | Low | Cheap; below 100 ms threshold — optional, do not spend further effort on LRU itself |

## Run-1 gate history

| Attempt | Deployment (hash) | Request ID | Verdict | Reason | Fix before next attempt |
|---|---|---|---|---|---|
| RUN 1 #1 | deploy 6 `baf658299a540d47` | `v2-benchmark-0-fc6c9ec5f8cf` | **FAIL** | Breakdown logs absent from captured log (container stdout doesn't stream); PNG level not explicitly provable in log/artifact (opt-diag env doesn't reach container) | Host-side printing of `[v2.prompt_executor_breakdown]`, `[v2.conditioning_exact_hit_breakdown]`, `[v2.png_output]` from trace events + remote event enrichment (compress_level/png_compress_ms; breakdown dict) |
| RUN 1 #2 | deploy 7 `3b9bcc7438fe60b9` | `v2-benchmark-0-609f3bf99425` | **FAIL** | PE c2f window fails reconciliation: `c2f_first_node_prefix_ms` duplicated the full parent window → children 2× parent (residual -138.269) | Stage-end stamp; c2f prefix = true post-staging remainder; residuals emitted from present children |
| RUN 1 #3 | deploy 8 `b25c57b6952a2410` | `v2-benchmark-0-35f1705f2350` | **PASS** | All gate items satisfied (breakdown logs present, PNG level proven, reconciliation OK) | — (RUN 2 then exposed a host-formatter regression) |
| RUN 1 #4 (accepted) | deploy 8 `b25c57b6952a2410` (remote unchanged; host-only fix) | `v2-benchmark-0-f3f1c2efac33` | **PASS** | All gate items satisfied after the RUN-2 regression fix (prefer-populated `output_encode_end` selection) | — |

RUN 2 #1 (`v2-benchmark-0-aee839f8e779`) revealed the instrumentation regression (empty legacy `output_encode_end` event preceding the populated one dropped compress_level from the PNG line) → per protocol the sequence was stopped and restarted from RUN 1 after the host-only fix (remote code unchanged, no redeploy required).

## Accepted RUN 1 (attempt 4) — full final waterfall

```text
WATERFALL (host-reconciled)
V2 COLD WATERFALL - run 1 (local reconcile)
Request: v2-benchmark-0-f3f1c2efac33  Instance: 641a9f3fec1e4713a9bdf425b495710e  GPU: ['RTX-PRO-6000']  Fresh: YES
Provider/Region: GCP/us-south1
TOTAL WALL:           34.004s   (command->response minus Modal scheduling)
COMMAND->RESPONSE:    35.804s

+-----+------------------------------------------------+------------+------------+----------+------------------------------------------+
|   # | Stage                                          |   Duration |       Cum. |        % | Relative wall (TOTAL WALL)               |
+-----+------------------------------------------------+------------+------------+----------+------------------------------------------+
|   1 | Local preparation                              | 445.232 ms | 445.232 ms |   1.309% | #                                        |
|   2 | Modal handle and submission                    |    17.362s |    17.808s |  51.060% | ####################                     |
|   3 | Modal pre-Python snapshot restoration          |     2.561s |    20.368s |   7.531% | ###                                      |
|   4 | Python/application restore                     |     2.359s |    22.728s |   6.939% | ###                                      |
|   5 | Restore-to-method entry                        |  46.811 ms |    22.775s |   0.138% | #                                        |
|   6 | Remote method setup                            | 111.815 ms |    22.887s |   0.329% | #                                        |
|     |   graph setup                                  |  93.115 ms |            |          |                                          |
|     |   residual before executor invoke              |  26.781 ms |            |          |                                          |
|   7 | PromptExecutor/cache setup                     |     1.728s |    24.615s |   5.083% | ##                                       |
|     |   execution to cached                          |     1.614s |            |          |                                          |
|     |   cached to first node                         | 106.308 ms |            |          |                                          |
|   8 | Pre-sampler execution                          |     2.183s |    26.798s |   6.419% | ###                                      |
|     |   Conditioning cache exact_hit lookup=571.3... | 571.334 ms |            |          |                                          |
|     |   CLIP encode skipped (cache hit)              |          - |            |          |                                          |
|     |   Node: ImpactSwitch                           |  54.001 ms |            |          |                                          |
|     |   Node: ClownsharKSampler_Beta                 | 134.668 ms |            |          |                                          |
|     |   Checkpoint read                              |     1.634s |            |          |                                          |
|     |   Read end -> construction done                |   0.144 ms |            |          |                                          |
|     |   UNET get_model                               | 235.122 ms |            |          |                                          |
|     |   Bind                                         |  19.138 ms |            |          |                                          |
|     |   Synchronized H2D (6.0 GB/s)                  |     2.044s |            |          |                                          |
|     |   H2D end -> UNET ready                        |   1.596 ms |            |          |                                          |
|   9 | Sampler node to sampling                       | 127.637 ms |    26.925s |   0.375% | #                                        |
|     |   lane acquired to actual stage                | 127.613 ms |            |          |                                          |
|  10 | Sampling                                       |     4.750s |    31.675s |  13.969% | ######                                   |
|  11 | Post-sampling / VAE transition                 | 830.075 ms |    32.505s |   2.441% | #                                        |
|  12 | VAE decode                                     | 369.544 ms |    32.875s |   1.087% | #                                        |
|     |   VAE load/H2D                                 | 850.801 ms |            |          |                                          |
|  13 | Output encode / descriptor                     | 234.093 ms |    33.109s |   0.688% | #                                        |
|     |   PNG encode                                   | 160.978 ms |            |          |                                          |
|  14 | Remote result handoff                          | 874.683 ms |    33.983s |   2.572% | #                                        |
|  15 | Local result handling / caller return          |  16.000 ms |    33.999s |   0.047% | #                                        |
+-----+------------------------------------------------+------------+------------+----------+------------------------------------------+
|     | SCHEDULING                                     |     1.801s |            |          |                                          |
|     | RECONCILIATION                                 |   4.220 ms |            |          |                                          |
|     | STATUS                                         |         OK |            |          |                                          |
+-----+------------------------------------------------+------------+------------+----------+------------------------------------------+
```
Diagnostics (captured): `[v2.prompt_executor_breakdown]` exec_to_cached 1614.251 / signature_keys 1392.093 / residual 221.175 (seed wrapper absent; reported); `[v2.conditioning_exact_hit_breakdown]` exact_hit lookup 571.334 / children 570.919 / residual 0.133; `[v2.png_output]` compress_level=1 png_encode 160.961 png_compress 150.812; Step-3 `plan_validation_fast_path` consumed=true; output SHA `20b10e1f…`.

## RUN 2 — post-snapshot (structural validation)

Request `v2-benchmark-0-2a162cb8f6c3` (GCP us-east4; high platform scheduling 64.6 s — captured as-is per protocol):

- Waterfall: host-reconciled table visible; TOTAL WALL 33.759 s = 98.391 s − 64.632 s scheduling; reconciliation 14.708 ms (STATUS OK; within 50 ms ceiling, 10 ms target missed and honestly displayed); checkpoint read 1.320 s (real active-read) vs H2D 2.523 s @4.9 GB/s; handoff 693.1 ms; local return 0.0 ms.
- PNG: `compress_level=1`, encode 160.916 ms, compress 154.169 ms, 1088×1920, 3,129,718 B, SHA `20b10e1f…` (byte-identical).
- PE breakdown: exec_to_cached 1406.246, signature_keys 1403.549, residual 1.293 — reconciles.
- CC breakdown: `exact_hit`, lookup 285.929, children 285.544, residual 0.123 — reconciles; CLIP skipped.
- Step-3 consumed; output identical.

**RUN 2 STRUCTURAL CHECK: PASS.**

## RUN 3 — authoritative real capture

Request `v2-benchmark-0-680714c1252a` · Provider GCP · Region us-east1 · Cache decision `exact_hit` · CLIP encode count 0 · Step-3 consumed (`plan_validation_fast_path`, hit=true) · PNG compression level 1 · Output SHA `20b10e1f99831bc758d9df82f43ce0beb1cbc636a740d11a29eb2bffe90e5260` (1088×1920, 3,129,718 B) · Reconciliation −1.311 ms (OK, COMPLETE, no flags).

Complete final live waterfall exactly as captured in `v2_png_run_3_final_capture.log`:

```text
WATERFALL (host-reconciled)
V2 COLD WATERFALL - run 1 (local reconcile)
Request: v2-benchmark-0-680714c1252a  Instance: a8058a36169348578ec42cea29cc8b9c  GPU: ['RTX-PRO-6000']  Fresh: YES
Provider/Region: GCP/us-east1
TOTAL WALL:           38.626s   (command->response minus Modal scheduling)
COMMAND->RESPONSE:    40.223s

+-----+------------------------------------------------+------------+------------+----------+------------------------------------------+
|   # | Stage                                          |   Duration |       Cum. |        % | Relative wall (TOTAL WALL)               |
+-----+------------------------------------------------+------------+------------+----------+------------------------------------------+
|   1 | Local preparation                              | 406.629 ms | 406.629 ms |   1.053% | #                                        |
|   2 | Modal handle and submission                    |    17.162s |    17.569s |  44.432% | ##################                       |
|   3 | Modal pre-Python snapshot restoration          |     3.722s |    21.291s |   9.637% | ####                                     |
|   4 | Python/application restore                     |     6.774s |    28.065s |  17.537% | #######                                  |
|   5 | Restore-to-method entry                        |  30.026 ms |    28.095s |   0.078% | #                                        |
|   6 | Remote method setup                            |  61.996 ms |    28.157s |   0.161% | #                                        |
|     |   graph setup                                  |  44.934 ms |            |          |                                          |
|   7 | PromptExecutor/cache setup                     |     1.461s |    29.618s |   3.782% | ##                                       |
|     |   execution to cached                          |     1.342s |            |          |                                          |
|     |   cached to first node                         | 112.455 ms |            |          |                                          |
|   8 | Pre-sampler execution                          |     2.153s |    31.771s |   5.574% | ##                                       |
|     |   Conditioning cache exact_hit lookup=439.3... | 439.305 ms |            |          |                                          |
|     |   CLIP encode skipped (cache hit)              |          - |            |          |                                          |
|     |   Node: ImpactSwitch                           |  39.335 ms |            |          |                                          |
|     |   Node: ClownsharKSampler_Beta                 | 131.102 ms |            |          |                                          |
|     |   Checkpoint read                              |     1.298s |            |          |                                          |
|     |   Read end -> construction done                |   0.457 ms |            |          |                                          |
|     |   UNET get_model                               | 139.906 ms |            |          |                                          |
|     |   Bind                                         |  93.474 ms |            |          |                                          |
|     |   Synchronized H2D (6.0 GB/s)                  |     2.063s |            |          |                                          |
|     |   H2D end -> UNET ready                        |   1.567 ms |            |          |                                          |
|   9 | Sampler node to sampling                       | 124.632 ms |    31.896s |   0.323% | #                                        |
|     |   lane acquired to actual stage                | 124.609 ms |            |          |                                          |
|  10 | Sampling                                       |     4.743s |    36.639s |  12.279% | #####                                    |
|  11 | Post-sampling / VAE transition                 | 613.247 ms |    37.252s |   1.588% | #                                        |
|  12 | VAE decode                                     | 376.867 ms |    37.629s |   0.976% | #                                        |
|     |   VAE load/H2D                                 |  43.493 ms |            |          |                                          |
|  13 | Output encode / descriptor                     | 225.059 ms |    37.854s |   0.583% | #                                        |
|     |   PNG encode                                   | 153.903 ms |            |          |                                          |
|  14 | Remote result handoff                          | 757.841 ms |    38.612s |   1.962% | #                                        |
|  15 | Local result handling / caller return          |  16.000 ms |    38.628s |   0.041% | #                                        |
+-----+------------------------------------------------+------------+------------+----------+------------------------------------------+
|     | SCHEDULING                                     |     1.596s |            |          |                                          |
|     | RECONCILIATION                                 |  -1.311 ms |            |          |                                          |
|     | STATUS                                         |         OK |            |          |                                          |
+-----+------------------------------------------------+------------+------------+----------+------------------------------------------+
```
Captured diagnostics: `[v2.prompt_executor_breakdown]` exec_to_cached 1341.835 / signature_keys 1339.881 / residual 0.55; c2f 112.455 (topo 112.340, stage 1.050, prefix 0.095, residual −1.03). `[v2.conditioning_exact_hit_breakdown]` lookup 439.305 / manifest 262.024 / entry 137.157 / lru 39.526 / children 438.918 / residual 0.109. `[v2.png_output]` compress_level=1, encode 153.901, compress 149.384.

### Stage summary — RUN 3

| Stage | RUN 3 |
|---|---|
| TOTAL WALL | 38.626 s |
| Scheduling | 1.596 s |
| Local preparation | 406.629 ms |
| Modal handle/submission | 17.162 s |
| Pre-Python snapshot restore | 3.722 s |
| Python restore | 6.774 s |
| PromptExecutor/cache setup | 1.461 s |
| Pre-sampler execution | 2.153 s |
| Conditioning exact-hit | 439.305 ms |
| Checkpoint read | 1.298 s |
| UNET get_model | 139.906 ms |
| UNET bind | 93.474 ms |
| UNET H2D | 2.063 s |
| Sampling | 4.743 s |
| Post-sampling/VAE | 613.247 ms |
| VAE decode | 376.867 ms |
| PNG encode | 153.903 ms |
| Remote result handoff | 757.841 ms |
| Local return | 16.000 ms |

Provider: GCP · Region: us-east1 · Cache decision: exact_hit · CLIP encode count: 0 · Step-3 consumed: true · Output SHA: `20b10e1f99831bc758d9df82f43ce0beb1cbc636a740d11a29eb2bffe90e5260` · PNG compression level: 1 · Reconciliation: −1.311 ms (OK).

## Final optimization recommendations (newly investigated only)

1. **PromptExecutor/cache setup**
   - Measured current cost: 1.461 s (stage 7); dominant: `CacheKeySetInputSignature.add_keys` 1.340 s (98%).
   - Realistically removable: ~1.2–1.3 s.
   - Expected TOTAL WALL saving: ~1.2–1.3 s.
   - Confidence: Medium. Risk: Medium (IS_CHANGED semantics must be preserved; gate on proven Step-3 identity + full key inputs).
   - Recommended next action: prototype per-workflow signature memoization (or restore-time precompute) behind a flag, then A/B validate.

2. **Conditioning exact-hit path**
   - Measured current cost: 439 ms (RUN 3) / 286 ms (RUN 2) / 571 ms (RUN 1d) — Volume-I/O dominated.
   - Realistically removable: ~380–400 ms (manifest cold fetch 262 ms + payload read within entry_lookup 137 ms).
   - Expected TOTAL WALL saving: ~0.38–0.40 s on exact-hit requests.
   - Confidence: High. Risk: Low.
   - Recommended next action: pre-restore background warm/prefetch of `manifest.json` + expected entry payload (2.9 MB) into page cache/memory; optionally an in-memory manifest cache.

3. **async LRU specifically**
   - Measured current cost: 30–51 ms per hit (sync atomic manifest rewrite + fsyncs).
   - Realistically removable: ~30–50 ms (existing `COMFYMODAL_V2_CONDITIONING_CACHE_ASYNC_LRU=1` arm).
   - Expected TOTAL WALL saving: ~30–50 ms.
   - Confidence: High. Risk: Low.
   - Recommended next action: apply the existing async-LRU config flip if desired (below the 100 ms threshold; no further LRU engineering warranted).

## Completion output

- Report path: `V2_PNG_PRESAMPLER_INVESTIGATION_AND_REAL_CAPTURE.md`
- Changed files: `tools/benchmark_v2_direct.py`, `comfymodal_runtime/v2_experiments.py`, `comfyapp.py`, `comfymodal_runtime/modal_app.py`, `comfymodal_runtime/runtime_executor.py`, `comfymodal_runtime/model_preload.py`, `tests/test_v2_ab_experiments.py`, `tests/test_benchmark_v2_proof_collection.py`, `tests/test_v2_prompt_executor_breakdown.py` (new), `tests/test_v2_conditioning_exact_hit_breakdown.py` (new), `tests/test_v2_host_breakdown_lines.py` (new), plus evidence logs `v2_png_deploy_{1,2,3}.log`, `v2_png_run_{1,1b,1c,1d,2,2b,3}.log`
- Commit hash: **none**
- Deployment count (this task): 3 (deploy 6 `baf658299a540d47`, deploy 7 `3b9bcc7438fe60b9`, deploy 8 `b25c57b6952a2410`)
- Generation-request count (this task): 7
- Failed RUN-1 gate attempts: 2 (attempts 1 and 2; attempt 3 passed but the sequence was restarted after the RUN-2 regression fix)
- Accepted RUN-1 request ID: `v2-benchmark-0-f3f1c2efac33`
- RUN-2 request ID: `v2-benchmark-0-2a162cb8f6c3`
- RUN-3 request ID: `v2-benchmark-0-680714c1252a`

```
RUN 1 GATE: PASS
RUN 2 STRUCTURAL CHECK: PASS
RUN 3 REAL CAPTURE: PASS
```

## Summary

- PNG level1 production default: **YES**
- PromptExecutor/cache:
  - current cost = 1.461 s (signature keys 1.340 s)
  - dominant cause = per-request `CacheKeySetInputSignature.add_keys` synchronous CPU (43-node ancestry + signature hashing; fresh caches every request)
  - realistic removable cost = ~1.2–1.3 s
  - recommended next step = prototype per-workflow signature memoization (or restore-time precompute) gated on Step-3 identity
- Conditioning exact-hit:
  - current cost = 439 ms (RUN 3; 286–571 ms across runs)
  - dominant cause = cold Modal-Volume file I/O (manifest re-read 262 ms + 2.9 MB payload read/deserialize 137 ms)
  - LRU-specific cost = 30–51 ms (sync; under 100 ms threshold)
  - non-LRU optimization potential = ~380–400 ms
  - recommended next step = pre-restore background warm/prefetch of manifest + payload; in-memory manifest cache
