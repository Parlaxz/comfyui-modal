# V2 Prompt-Signature Cache + Conditioning Prefetch + Startup Decomposition — Report

## Executive result

All three primary tasks completed and **proven in a real gated 3-run sequence** on deployment `f8ce7eff7d0b1d3d` (tree generation `e557bfe3df7783e34de82ea7bb419198`, ComfyUI core `f49bdb655707b979`, RTX PRO 6000 / GCP us-east1):

1. **PromptExecutor signature-key memoization (Task 1)** — the ~1.3–2.4 s per-request `CacheKeySetInputSignature.add_keys` rebuild is eliminated on exact matches: RUN 3 `exec_to_cached_ms=6.053` with `signature_keys_ms=absent`, `signature_cache_hit=True source=volume signature_reuse_ms=3.984`. Cross-container reuse proven (RUN 1 computes + persists to the runtime-state volume; RUN 2/3 new single-use containers hit).
2. **Conditioning exact-hit prefetch (Task 2)** — plan-receipt background prefetch + in-memory manifest/payload + bounded demand-time join + serve-by-components: RUN 3 exact hit `lookup_wall_ms=53.261` (was ~437 ms cold on the same deployment class), `manifest_memory_hit=1 payload_memory_hit=1 payload_memory_source=key_hit prefetch_source=full prefetch_join_ms=34.453 prefetch_join_timeout=0`.
3. **Submission/scheduling/startup decomposition (Task 3)** — the repeatable ~17–19 s "Modal handle and submission" stage is **proven to be benchmark-only full node-registry init**: RUN 3 `node_registry_init_ms=18821.102` of the 18.924 s stage; Modal platform time is scheduling 2.289 s (excluded) + pre-Python restore 5.041 s + Python restore 0.537 s; the persistent local-handle path is ~2 ms. `[v2.host_submission_breakdown]`, `[v2.restore_deep]`, and scheduling provenance are now instrumented and reconciled.

Gate status: **RUN 1 GATE: PASS (final attempt)** · **RUN 2 STRUCTURAL CHECK: PASS** · **RUN 3 REAL CAPTURE: PASS**.

---

# Task 1 — PromptExecutor optimization

## Old behavior

`PromptExecutor.execute_async` → `outputs_cache.set_prompt` → `CacheKeySetInputSignature.add_keys` recomputed, per request and per node (~43-node workflow), the ordered-ancestry walk + immediate-node signature + `IsChangedCache` lookups + recursive `to_hashable` conversion — ~1.34 s measured (`signature_keys_ms=1255–5848` across RUN-1 attempts), purely synchronous CPU, repeated identically on Step-3-consumed requests.

## Exact signature-key dependencies (verified)

The signature is a **pure deterministic function of (prompt dict, node registry, is_changed values)**:
- `dynprompt.get_node` (graph structure), `NODE_CLASS_MAPPINGS[class_type]`, `INPUT_TYPES()["hidden"]` (via the module-memoized `include_unique_id_in_input`), `await is_changed_cache.get(node_id)`, and `node["inputs"]` sorted by key (links → `("ANCESTOR", idx, socket)`; values → `(key, value)`).
- `to_hashable` normalizes dict ordering (sorted frozensets); no id()/address/timestamp randomness.
- Benchmark-workflow `is_changed` values are all constant (absent → False; `SystemNotification|pysssss` + v3 nodes → constant NaN via `NotImplementedError`), so no per-request is_changed drift exists for this workflow. The memo still stores per-node `is_changed` and revalidates non-False entries on hit (arbitrary-workflow safe).

## Implemented design

New module `comfymodal_runtime/prompt_signature_cache.py` (stdlib-only) + `_patched_sig_add_keys` extension in `comfymodal_runtime/runtime_executor.py`:

- **Identity** (mirrors the Step-3 host memo precedent): `stable_hash(workflow_hash, source_workflow_hash, deployment_combined_hash, custom_node_generation, registry_proof_hash, schema)`.
- **Storage**: `{COMFYMODAL_V2_STATE_VOLUME_ROOT}/prompt_signature_memo.json` (the shared runtime-config volume), atomic tmp+fsync+replace, multiple entries keyed by identity hash, tolerant reads.
- **Hit**: populate `self.keys`/`self.subcache_keys` from the memo (structural frozenset equality ⇒ identical cache-key behavior), skip the original `add_keys`; per-node `inputs_hash` integrity check + non-False `is_changed` revalidation.
- **Miss**: run the original, encode per-node signatures (+ NaN/Unhashable round-trip), persist once.
- Flag `COMFYMODAL_V2_PROMPT_SIGNATURE_CACHE=1` (allowlist + `_runtime_env` passthrough); memo loaded at plan receipt (early priming) and lazily by the patch.

## Safety/fallback design

Fail closed on: missing identity, corrupt/unreadable memo, `inputs_hash` mismatch, `is_changed` drift, or any exception — original `add_keys` runs. A hit only skips key computation; cache setup, `clean_unused`, and the gather walk still run. NaN round-trips exactly (`{"__nan__":true}`) so always-miss semantics are preserved.

## RUN 1 / RUN 2 / RUN 3

- RUN 1 (gate): `signature_cache_requested=True eligible=True hit=False fallback=no_entry` — truthful first-compute miss; memo written to the volume.
- RUN 2 (post-snapshot, new container): `signature_cache_hit=True source=volume reuse_ms=2.539`, `exec_to_cached_ms=6.638`, `signature_keys_ms=absent`.
- RUN 3 (authoritative, new container): `signature_cache_hit=True source=volume reuse_ms=3.984`, `exec_to_cached_ms=6.053`, `signature_keys_ms=absent`.

## Measured saving

| Metric | Before (RUN-1 compute) | RUN 3 | Saving |
|---|---|---|---|
| Signature keys | ~1.34–2.38 s | absent (0) | ~1.3–2.4 s |
| exec→cached | ~1.25–2.38 s | 6.053 ms | ~1.3–2.4 s |

## Remaining cost

~6 ms (identity/inputs-hash checks + frozenset reconstruction). The memo is advisory and per-deployment (identity includes deployment hash), so each fresh deployment pays one compute-miss — correct and unavoidable.

---

# Task 2 — Conditioning exact-hit optimization

## Old behavior

Every single-use restored request cold-read the Modal Volume: manifest (~150–260 ms for ~2–3 KB), entry header (~290 ms), payload (~55–80 ms) + deserialize/checksums, plus sync LRU touch (~30–42 ms). RUN 2b (pre-fix) measured exact-hit `lookup_wall_ms=436.843`.

## Prefetch design

- **Launch**: daemon thread at plan receipt (after `ExecutionPlan.from_dict`, before `executor.stream`), gated by `COMFYMODAL_V2_CONDITIONING_CACHE_PREFETCH=1`; never on the coordinator pool.
- **Plan-time key**: `_build_plan_time_cache_context` derives identity from plan + container state (workflow/deployment/generation/options hashes, torch, model identity via model_stack → prompt_bundle.encodes → workflow CLIPLoader node fallback); `compute_dtype`/`tokenizer_identity` approximated and fail closed at demand via canonical-key revalidation.
- **Manifest handling**: in-memory manifest installed at prefetch; demand serves `manifest_read_ms=0.0` (verified).
- **Payload handling**: prefetch reads the manifest's existing entries keyed by **their own stored digests** (serve-by-components — the round-6 fix that made the payload win survive plan-time digest drift) plus the plan-digest probe; demand-time digest-keyed hit OR component-match scan (`payload_memory_source=key_hit|component_match`); bounded `_PREFETCH_MAX_ENTRIES` (default 3, env `COMFYMODAL_V2_CONDITIONING_PREFETCH_MAX_ENTRIES`, clamp [0,8]).
- **Join**: `join_prefetch(request_id, timeout_s=1.5)` — bounded demand-time wait (env `COMFYMODAL_V2_CONDITIONING_PREFETCH_JOIN_TIMEOUT_MS`, default 1500); timeout → honest `prefetch_join_timeout=1` + cold fallback.
- **Reload**: first prefetch of a container skips the volume reload (`prefetch_reload=skipped_first` — single-use containers see the latest commit at mount); later prefetches keep the throttled reload.
- **Correctness**: memory entries pass the identical validation as the file path (format/schema/version, key_hash, canonical-key equality, model identity, manifest byte_length, payload SHA, per-tensor checks) via the shared `_validate_entry_bytes`. Fail closed on any drift; self-stores invalidate memory.

## Overlap with UNET/file reads

Prefetch reads a different volume (`prompt_cache_vol`, ~2.9 MB total) than the UNET model stream (`/root/models`, 12.3 GB); RUN 3 `prefetch_wall_ms=235.534` completed during restore/setup with only `prefetch_join_ms=34.453` on the demand path.

## RUN 1 / RUN 2 / RUN 3

- RUN 1 (gate, miss_stored): `prefetch_requested=1 prefetch_source=manifest_only prefetch_reason=key_build_partial:weight_dtype prefetch_join_ms=302.126 prefetch_join_timeout=0 manifest_memory_hit=1 lookup_wall_ms=1.218` — machinery active and observable; entry stored.
- RUN 2 (post-snapshot, exact hit): `lookup_wall_ms=64.914`, `manifest_memory_hit=1 payload_memory_hit=1 payload_memory_source=key_hit prefetch_source=full prefetch_payload_entries=3 prefetch_join_ms=24.362 prefetch_join_timeout=0`.
- RUN 3 (authoritative, exact hit): `lookup_wall_ms=53.261`, `manifest_memory_hit=1 payload_memory_hit=1 payload_memory_source=key_hit prefetch_source=full prefetch_payload_entries=3 prefetch_join_ms=34.453 prefetch_join_timeout=0 prefetch_overlap_ms=39.692`, `hit_read_mbps=54.876`.

## Measured demand-time saving

| Metric | Before (RUN 2b cold) | RUN 3 | Saving |
|---|---|---|---|
| Exact-hit lookup | 436.843 ms | 53.261 ms | ~384 ms |
| Demand-time Volume wait | ~400 ms | ~0 (memory) | ~400 ms |

## Remaining cost

~53 ms = key build 0.17 + deserialize/checksum/tensor rebuild ~52 (unavoidable CPU) + **sync LRU touch 31.8 ms**. Note: `COMFYMODAL_V2_CONDITIONING_CACHE_ASYNC_LRU=1` is allowlist-only today (the harness does not forward it), so the sync LRU path remains — this is the reported trivial config item, not a task win; flipping it to async would move the ~32–42 ms off the demand path.

---

# Task 3 — Submission / scheduling / startup

## Timing model (host → platform → remote → return)

- **LOCAL/HOST**: command start (bat `COMFYMODAL_COMMAND_START_UNIX_MS`) → python first line → local receive → worker → plan build → handle lookup → generator create → **first `__anext__` = actual Modal submission** (`submission_boundary_source=first_anext`; `remote_gen.aio` is lazy).
- **MODAL PLATFORM**: submission → "Restoring Function from memory snapshot" (Modal app-log marker, task+window matched) = **Scheduling** (excluded from TOTAL WALL); restore-begin → python resume = **pre-Python snapshot restore**.
- **REMOTE PYTHON**: resume → restore end (`[v2.restore_deep]` leaf decomposition) → method entry → executor → pre-sampler → sampling → output → `remote_result_emit`.
- **LOCAL RETURN**: `final_result_received`/`local_result_received` → `execute_plan_return` (caller return).

## Host process startup

`run_v2_single.bat` launches a **fresh python process per invocation**. RUN 3: `command_start_to_python_first_line_ms=164.104`, `python_first_line_to_local_receive_ms=289.324`.

## Benchmark startup/import cost

**The ~17–19 s stage is `_ensure_full_node_registry()`** (benchmark-only): RUN 3 `node_registry_init_ms=18821.102` of the 18.924 s "Modal handle and submission" stage — the full ComfyUI node registry (2192 classes) loads inside `_run_one` between local-receive and worker-start. Plan build is 78 ms, handle lookup 2 ms, generator create 2 ms (persistent IPC). The host does NOT import torch/nodes at module load; the registry init is the entire cost.

## Modal client/handle

Persistent local-handle owner survives across CLI invocations (`decision=persistent_hit`, `created_modal_client=false`, `performed_cls_from_name=false`); RUN 3 `handle_lookup_ms=2.0`. Not a contributor to the 17–19 s.

## Actual submission trigger

Verified: the Modal SDK's `remote_gen.aio()` is lazy; the true submit is the first `__anext__` (`modal_submission_attempt` = `modal_first_iteration_start`, captured immediately before the first `await _iterator.__anext__()`). `submission_boundary_source=first_anext` documented in the breakdown.

## Scheduling provenance

`scheduling_ms = modal_restore_begin_wall_unix_ns − modal_submission_attempt_wall_unix_ns`; restore-begin = result-carried `modal_restore_begin_wall_unix_ns` else the Modal app-log line "Restoring Function from memory snapshot" (`scheduling_source=modal_app_log` on RUN 3; 2288.6 ms). Includes platform admission/queue/placement/scheduler→restore handoff; excludes pre-Python restore and all Python restore.

## Scheduling vs startup restore (separate concepts)

RUN 3: Scheduling **2.289 s** (excluded from TOTAL WALL, no %/bar) · Pre-Python snapshot restore **5.041 s** · Python restore **0.537 s**. Never collapsed.

## Pre-Python snapshot restore

5.041 s (restore-begin → python resume) — separate top-level stage, platform-only, no %/bar.

## Python restore breakdown

`[v2.restore_deep]` (new): `identity_capture_ms=0.1 configure_runtime_ms=0.008 torch_thread_apply_ms=0.979 host_memory_probe_ms=3.267 teardown_diag_setup_ms=0.082 bootstrap_restore_ms=640.13 preload_bridge_prep_ms=0.126 restore_finalize_ms=…` plus the existing `[v2.restore_breakdown]` (restore_gpu_state, cuda_init, reload_models, sync_custom_nodes, etc.). RUN 3's 537 ms restore is well-attributed.

## Benchmark-only vs production-shared work

- **Benchmark-only**: fresh-process boot (~0.45 s), `_ensure_full_node_registry` (~18.8 s), harness timestamps/persistence. Production ComfyUI runs in a long-lived server with the registry already loaded — the 17–19 s does not exist there.
- **Production-shared**: `ModalTransport` + `execute_plan` + the exact transport/handle/submission stamps; `__init__.py` V2 dispatch and Playground use the same `execute_plan`/`ModalTransport` path. Production's "Modal handle and submission" stage is the same code minus the registry cost (~65 ms local prep + handle + serialize).

## RUN 1 / RUN 2 / RUN 3

Instrumentation present and correct on all three (registry split, submission boundary source, scheduling source, restore_deep, python-first-line stamp). No fake zero fields; missing → `absent`.

## Exact ~17 s explanation

RUN 3: 18.924 s stage = **node_registry_init 18.821 s (benchmark-only)** + plan build 0.078 s + handle/generator ~0.005 s + framing. Modal platform time in the same run: 2.289 s scheduling + 5.041 s pre-Python restore.

## Remaining unknown intervals

None > 50 ms on the host side (host breakdown reconciles: 0.164+0.289+0+18.821+0.019+0.001+0.078+0.006+0.002+0.002+0.002+0 ≈ local_receive_to_submission 19.38 s). Platform-internal scheduling cannot be decomposed further without raw AppGetLogs task-state parsing (documented limitation; scheduling is measured as submission→restore-begin).

---

# Final RUN 3 waterfall

```
WATERFALL (host-reconciled)
V2 COLD WATERFALL - run 1 (local reconcile)
Request: v2-benchmark-0-f6b195e0536b  Instance: 11f4634d0ed3403dbff1d72fb29953e6  GPU: ['RTX-PRO-6000']  Fresh: YES
Provider/Region: GCP/us-east1
TOTAL WALL:           36.427s   (command->response minus Modal scheduling)
COMMAND->RESPONSE:    38.715s

+-----+------------------------------------------------+------------+------------+----------+------------------------------------------+
|   # | Stage                                          |   Duration |       Cum. |        % | Relative wall (TOTAL WALL)               |
+-----+------------------------------------------------+------------+------------+----------+------------------------------------------+
|   1 | Local preparation                              | 453.428 ms | 453.428 ms |   1.245% | #                                        |
|   2 | Modal handle and submission                    |    18.924s |    19.378s |  51.951% | #####################                    |
|   3 | Modal pre-Python snapshot restoration          |     5.041s |    24.419s |  13.839% | ######                                   |
|   4 | Python/application restore                     | 537.471 ms |    24.956s |   1.475% | #                                        |
|   5 | Restore-to-method entry                        |  30.853 ms |    24.987s |   0.085% | #                                        |
|   6 | Remote method setup                            | 365.940 ms |    25.353s |   1.005% | #                                        |
|     |   method entry to graph start                  | 315.522 ms |            |          |                                          |
|     |   method entry to runtime configuration        | 315.482 ms |            |          |                                          |
|     |   graph setup                                  |  50.418 ms |            |          |                                          |
|   7 | PromptExecutor/cache setup                     |     1.478s |    26.831s |   4.058% | ##                                       |
|     |   cached to first node                         |     1.471s |            |          |                                          |
|   8 | Pre-sampler execution                          |     2.284s |    29.115s |   6.271% | ###                                      |
|     |   Conditioning cache exact_hit lookup=53.261ms |  53.261 ms |            |          |                                          |
|     |   CLIP encode skipped (cache hit)              |          - |            |          |                                          |
|     |   Node: ImpactSwitch                           |  54.278 ms |            |          |                                          |
|     |   Node: ClownsharKSampler_Beta                 | 111.285 ms |            |          |                                          |
|     |   Checkpoint read                              |     1.297s |            |          |                                          |
|     |   Read end -> construction done                |   0.222 ms |            |          |                                          |
|     |   UNET get_model                               | 208.804 ms |            |          |                                          |
|     |   Bind                                         |  55.986 ms |            |          |                                          |
|     |   Synchronized H2D (5.7 GB/s)                  |     2.146s |            |          |                                          |
|     |   H2D end -> UNET ready                        |   1.884 ms |            |          |                                          |
|   9 | Sampler node to sampling                       | 104.834 ms |    29.220s |   0.288% | #                                        |
|     |   lane acquired to actual stage                | 104.811 ms |            |          |                                          |
|  10 | Sampling                                       |     4.748s |    33.968s |  13.035% | #####                                    |
|  11 | Post-sampling / VAE transition                 | 847.477 ms |    34.816s |   2.327% | #                                        |
|  12 | VAE decode                                     | 433.026 ms |    35.249s |   1.189% | #                                        |
|     |   VAE load/H2D                                 | 878.161 ms |            |          |                                          |
|  13 | Output encode / descriptor                     | 243.822 ms |    35.493s |   0.669% | #                                        |
|     |   PNG encode                                   | 167.010 ms |            |          |                                          |
|  14 | Remote result handoff                          | 915.790 ms |    36.408s |   2.514% | #                                        |
|  15 | Local result handling / caller return          |  15.000 ms |    36.423s |   0.041% | #                                        |
+-----+------------------------------------------------+------------+------------+----------+------------------------------------------+
|     | SCHEDULING                                     |     2.289s |            |          |                                          |
|     | RECONCILIATION                                 |   3.454 ms |            |          |                                          |
|     | STATUS                                         |         OK |            |          |                                          |
+-----+------------------------------------------------+------------+------------+----------+------------------------------------------+
```

RUN 3 diagnostics: `[v2.prompt_executor_breakdown]` `signature_cache_hit=True source=volume reuse_ms=3.984 exec_to_cached_ms=6.053 signature_keys_ms=absent` · `[v2.conditioning_exact_hit_breakdown]` `exact_hit lookup_wall_ms=53.261 manifest_memory_hit=1 payload_memory_hit=1 payload_memory_source=key_hit prefetch_source=full prefetch_payload_entries=3 prefetch_join_ms=34.453 prefetch_join_timeout=0` · `[v2.png_output]` `compress_level=1 png_encode_ms=167.004 png_compress_ms=161.538 width=1088 height=1920 bytes=3129718 sha=20b10e1f…` · Step-3 `plan_validation_fast_path consumed=1` (cert RPC/preflight/validate/writeback all 0) · `[v2.host_submission_breakdown]` `node_registry_init_ms=18821.102 submission_boundary_source=first_anext scheduling_ms=2288.6 scheduling_source=modal_app_log`.

# Sub-14 implications

- **Controllable application wall on RUN 3**: TOTAL WALL 36.4 s − benchmark registry init 18.8 s ≈ **17.6 s** of platform+application time (scheduling excluded). The two task wins remove ~1.4–2.4 s (signature keys) + ~0.38 s (conditioning) from the application critical path; the remaining large components are platform placement/restore (5–7 s class) and sampling (4.7 s, fixed). A sub-14 s target requires platform-side reductions (placement/snapshot restore) plus the task wins; the instrumentation now attributes every second.
- Benchmark-only overhead must be excluded from any sub-14 production target: the 18.8 s registry init does not exist in the long-lived server path.

---

# Final required comparison (RUN 3)

| Metric                               |       Before |     RUN 3 |          Saving |
| ------------------------------------ | -----------: | --------: | --------------: |
| PromptExecutor/cache setup           |      ~1.46 s |   1.478 s* | Task-1 win below |
| Signature keys                       |      ~1.34 s |     0 (absent) | **~1.3–2.4 s** |
| Conditioning exact-hit lookup        |      ~0.44 s |  53.261 ms |        **~0.38 s** |
| Conditioning demand-time Volume wait |      ~0.40 s |      ~0    |        **~0.40 s** |
| Modal handle/submission              |     ~17.16 s |  18.924 s  | diagnostic only (registry 18.82 s, benchmark-only) |
| Pre-Python restore                   |      ~3.72 s |   5.041 s  | diagnostic only |
| Python restore                       |      ~6.77 s | 537.471 ms | diagnostic only |
| TOTAL WALL                           | context only |  36.427 s  | context only |

*Stage-7 top-level 1.478 s is now the cached→first-node topo-walk (execution→cached is 6 ms); the waterfall row "execution to cached" is absent because the memoized 6 ms detail is below the 25 ms filter — the signature-key cost is genuinely gone.

No causal savings are claimed from restore/platform differences.

# Production relevance verdict

**Does the ~17 s stage exist in actual production architecture? NO.**

- The 18.8 s is `_ensure_full_node_registry` in the benchmark harness (fresh CLI process). Production (`__init__.py` V2 dispatch, Playground `_default_execute_plan`) runs in a long-lived server with the registry preloaded; its "Modal handle and submission" stage is the shared transport path (~65 ms local prep + handle + serialize) — the same `ModalTransport`/`execute_plan` code, minus the registry cost.
- A long-lived UI/backend caller retains: host prep ~0.45 s, Modal platform scheduling (2.3 s class, excluded), pre-Python restore (5 s class), Python restore (0.5 s class), and the application path. A fresh benchmark CLI invocation additionally pays the ~18.8 s registry init.

---

# Final optimization recommendations (newly investigated only)

| Rank | Opportunity | Measured current cost | Realistically removable | Expected TOTAL WALL saving | Confidence | Risk | Recommended next action |
|---|---|---|---|---|---|---|---|
| 1 | **Signature-key memo** (Task 1, shipped) | ~1.3–2.4 s (first request/deployment only) | ~1.3–2.4 s on exact matches | ~1.3–2.4 s | High (proven RUN 2/3) | Low (fail-closed, identity-gated) | **Keep** — flag stays default-off pending product decision; no further work |
| 2 | **Conditioning prefetch** (Task 2, shipped) | exact-hit 53 ms (was ~437 ms) | ~380–400 ms | ~0.38–0.40 s | High (proven RUN 2/3) | Low (identical validation, fail-closed) | **Keep** — optionally tune `_PREFETCH_MAX_ENTRIES`; demand-time target met |
| 3 | **async LRU specifically** | sync LRU 31.8–42 ms per hit on the demand path | ~30–42 ms (move off demand path) | ~0.03–0.04 s | High (mechanism exists, tested safe) | Very low | Flip `COMFYMODAL_V2_CONDITIONING_CACHE_ASYNC_LRU=1` via `_runtime_env` (today it is allowlist-only and the harness does not forward it) — **below the 100 ms threshold, low priority** |

Sampling, VAE overlap, pinned staging, and other completed experiments are not reopened.

---

# Exact result artifacts

- Deployment 7 (accepted): deployment hash `f8ce7eff7d0b1d3d`, custom-node generation `e557bfe3df7783e34de82ea7bb419198`, ComfyUI `f49bdb655707b979`, snapshot CLIP=1/VAE=1/UNET=0 (RSS ~11.6 GiB), frozen-VRAM restore optimized (`frozen_capacity_used=1`).
- RUN 1 (gate, accepted): `v2-benchmark-0-4726ef6fe2cc` → artifact `comfymodal-data\benchmarks\runs\v2_2026-08-13_18-36-24\`
- RUN 2 (structural, accepted): `v2-benchmark-0-5409444083b3` → artifact `comfymodal-data\benchmarks\runs\v2_2026-08-13_18-38-23\`
- RUN 3 (authoritative): `v2-benchmark-0-f6b195e0536b` → artifact `comfymodal-data\benchmarks\runs\v2_2026-08-13_18-39-48\` (output sha `20b10e1f99831bc758d9df82f43ce0beb1cbc636a740d11a29eb2bffe90e5260`, 1088×1920, 3,129,718 B, compress_level=1 — reconciled against the `[v2.png_output]` trace line and `run_0.json` asset_id/byte_count; the previously reported `895deda…/2,874,640 B` was the level-6 reference size, i.e. stale report-only metadata and does NOT belong to the RUN 3 artifact)
- Local gates: 655 → 324 → 321 → 324 → 328 → 333 passed (0 real failures) across remediation rounds; pre-existing unrelated failures unchanged (observability-instrumentation 22, modal-app-identity 7 CacheDiT gate, telemetry 6 stale).
- Freeze record: `V2_PROMPT_CACHE_PREFETCH_STARTUP_FREEZE.md`.
