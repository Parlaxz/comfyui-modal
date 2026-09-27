# V2_BATCH_D9_INPUT_TYPES_WARM_FORENSICS.md

**Batch:** D9 · **Mode:** ZERO-SPEND local/static investigation · **Date:** 2026-08-16
**Scope:** `input_types_warm` (production key `COMFYMODAL_V2_INPUT_TYPES_WARM`) — what it does, what it costs, what state it creates, whether it can be removed/cached/snapshotted/deferred.
**Status:** `INPUT_TYPES_WARM_CONTENTION` = **SUPPORTED HYPOTHESIS, NOT CONFIRMED** → this batch: **NOT SUPPORTED LOCALLY** (see §10).

No Modal deploy, no Modal request, no paid benchmark, no remote OFF arm, no commit. All measurements local (ComfyUI 0.24.0, torch 2.8.0+cu128, Python 3.11.9, 12 cores, NTFS).

---

## 1. Executive conclusion

`input_types_warm` is an **advisory, fire-and-forget, off-critical-path cache warmer**. It enumerates the distinct `class_type` values in the incoming compiled workflow (31 for the benchmark workflow) and calls `INPUT_TYPES()` on each — the exact call the `TopologicalSort` walk pays per link on the first request of a cold container. It creates **no correctness-critical state**: every artifact it warms (folder listings via `folder_paths.filename_list_cache`, one-time schema/module-import work, class-spec results) is recomputable and is consumed only as an acceleration inside the same request's topo walk.

Key findings:

1. **The class set is workflow-derived, not hardcoded** — 31 = the distinct class types of the production-compiled benchmark workflow (43 nodes after output-107 reachability trimming from a 60-node/39-class source workflow). Verified against the D1 registry proof store (31/31, fingerprint-matched).
2. **The cost is overwhelmingly one-time and filesystem-dependent.** Locally: cold pass **23.96 ms** (≈22.6 ms one-time schema/import work + ≈2.1 ms folder listings), warm pass **1.39 ms**, third pass **0.97 ms**. In production the Modal-volume listing cost scales it to **0.8–3.6 s** cold (log evidence: 19.7 ms warm-cache-hit → 3593 ms cold). Only 3 of 31 classes touch the filesystem (CLIPLoader, UNETLoader, VAELoader); everything else is sub-ms static or in-memory registry work.
3. **Nothing functionally depends on it.** Omission test (local): deferred pass with cleared caches = **3.29 ms**, **zero schema mismatches** — omission merely moves identical work to the first consumer (the topo walk), where it lands **on the critical path**. That is the only real argument for keeping it.
4. **Contention is not supported locally.** With a production-like warm duration simulated (1 s per folder listing → 6 s warm), the meta-like CPU lane and the file-read lane showed **zero wall inflation**; the warm thread consumed **0.0–0.3 % CPU** (0–16 ms thread CPU over 6 s — pure IO wait). Production temporal overlap (2974 ms vs meta, 2875 ms vs fastsafe, scope=complete) remains *concurrence*, not *causation*.
5. **Best fix: do NOT delete.** The realistic options are (F) deploy-time folder-cache priming (the only expensive part, already implemented as `warm_registered_folders`) and (I) keep the in-request class warm as a cheap backstop. The persisted/snapshot options (D/E) are architecturally consistent with D1 for the *class-spec* portion but cannot remove the expensive portion (folder listings are volume-state-dependent).
6. **The remote ON/OFF A/B remains required** to settle causal contention (defined in §13). It was **not run** in this batch.

---

## 2. Why `input_types_warm` exists

Root cause it addresses (from code comments, D4 forensics, runtime_executor): on a **cold container**, the first request's `PromptExecutor` topo walk pays cold `class_def.INPUT_TYPES()` per link, and loader `*_name` inputs trigger cold `folder_paths.get_filename_list` → `recursive_search` over the **Modal volume** (network FS). This was the "cached→first-node 1177 ms" root cause on memo-hit runs. The warm pre-populates:

- `folder_paths.filename_list_cache` + strong cache (the cold volume walk),
- one-time schema generation / module-level first-call work for `io.ComfyNode` classes,
- nothing else (it does not touch the request-scoped `get_input_info` memo — that is per-request executor state; it only makes the underlying calls cheap).

It exists because the warm daemon runs **concurrently with** UNET meta/CLIP hydration (off critical path), so the first topo walk finds warm caches. `warm_registered_folders` (execution_warm.py:30-61) is the sibling warmer covering every registered folder.

---

## 3. Exact call graph

```
host (benchmark_v2_direct) ── POST /run ──> container: run_plan_stream (modal_app.py:16300)
  └─ _run_plan_stream_impl (modal_app.py:16469)
       ├─ plan receipt (ExecutionPlan; plan.workflow = frozen compiled workflow)
       ├─ conditioning prefetch scheduling (modal_app.py:166xx)          [Task-0, daemon]
       ├─ ── Task-1 input-types warm ────────────────────────────────────
       │   env gate: COMFYMODAL_V2_INPUT_TYPES_WARM (env_flag, default True)  (modal_app.py:16742)
       │   prompt source: plan.prompt or _thaw(plan.workflow)            (modal_app.py:16732-16736)
       │   threading.Thread(daemon=True, name="comfymodal-input-types-warm").start()  (17045-17049)
       │     └─ _run_input_types_warm()                                  (16780-17043)
       │          └─ warm_classes_input_types(prompt)                    (execution_warm.py:64-101)
       │               for distinct class_type in prompt:
       │                 nodes.NODE_CLASS_MAPPINGS[ct].INPUT_TYPES()     (per-class try/except, swallowed)
       │          evidence: stdout [v2.input_types_warm] + trace metadata (input_types_warm_*)
       │                    + register_forensic_interval("input_types_warm") → trace.forensic_intervals
       │                    + overlap vs fastsafe_worker_a/b intervals   (16961-16993)
       ├─ _derive_request_snapshot_seed (17087)                          [NOT gated on warm]
       ├─ status yield plan_received (17452)
       └─ self.executor.stream(plan, context)  (17460)  ── PromptExecutor.execute_async
            └─ TopologicalSort walk (runtime_executor patched get_input_info, 3490-3576)
                 ├─ (a) request-scoped memo keyed (class_type, input_name) → triple
                 ├─ (b) persisted topo-lazy fast path (signature-memo identity) → (None,None,{"lazy":bool})
                 │     WITHOUT calling INPUT_TYPES (deterministic on memo-hit runs)
                 └─ (c) original get_input_info → class_def.INPUT_TYPES()   ← warm makes this cheap
```

**Ordering (relative to request lifecycle):**

| Event | Order | Depends on warm? |
|---|---|---|
| request start / plan receipt | 0 | no |
| remote setup schedule (`remote_setup_schedule` event) | after warm scheduling | no |
| D1 plan/registry proof | independent host-side / startup path | no |
| UNET meta Worker A / fastsafe Worker B | starts around/after scheduling | no (runs concurrently) |
| CLIP hydration / conditioning prefetch | concurrent | no |
| `input_types_warm` thread start | right after scheduling site | n/a |
| PromptExecutor → topo walk | immediately after executor.stream | **benefits only** (never blocks on warm) |
| sampler | after topo walk | no |

**Facts:** fire-and-forget (daemon thread, no handle retained, no `.join()` anywhere). Returns `(count, elapsed_ms)` consumed only as evidence. Per-class failures swallowed; import/thread-start failure → `scheduled=0 reason=unavailable`, never fabricated, never propagates. Completion is **not awaited**; a slow/incomplete warm simply means the request pays the original cold cost in the topo walk.

---

## 4. 31-class inventory

Derivation (verified): `benchmark_v2_direct` loads `c5_latest_benchmark_workflow.json` (60 nodes, 39 distinct classes) → `canonical_execution.build_execution_plan` → `production_workflow.compile_production_workflow(output_node_ids=["107"], direct_output_sink=true)` → **43 nodes / 31 distinct classes**. 10 source classes trimmed by output-107 reachability (Anything Everywhere, CombineHooks8, Image Comparer, PurgeVRAM V2, ModelPatchLoader, PrimitiveFloat, SaveImage, SystemNotification, easy globalSeed, easy showAnything); 2 added by production compile (ClownOptions_ExtraOptions_Beta, ComfyModalProductionImageComparerOutput). The same 31 names are frozen in `.cache/v2_registry_proof_store.json` (D1, fingerprint-matched 31/31). **No hardcoded list in code; count = len(deduped class_types).**

| # | class_type | module | why included | INPUT_TYPES location |
|---|---|---|---|---|
| 1 | Any Switch (rgthree) | rgthree-comfy/py/any_switch.py | workflow switch node | any_switch.py:21-25 |
| 2 | CLIPLoader | ComfyUI nodes.py | loader (FS) | nodes.py:970-976 |
| 3 | CLIPTextEncode | ComfyUI nodes.py | conditioning | nodes.py:60-66 |
| 4 | CacheDiT_Model_Optimizer | ComfyUI-CacheDiT/nodes.py | model optimizer | nodes.py:850+ (preset registry) |
| 5 | ClownOptions_ExtraOptions_Beta | RES4LYF/samplers_extensions.py | sampler options (compile-injected) | samplers_extensions.py:596-605 |
| 6 | ClownsharKSampler_Beta | RES4LYF/beta/samplers.py | sampler | beta/samplers.py:1704-1731 |
| 7 | ComfyModalProductionImageComparerOutput | comfyui-modal comfyapp.py | output comparer (compile rewrite) | comfyapp.py:949-961 |
| 8 | ConditioningZeroOut | ComfyUI nodes.py | conditioning | nodes.py:254-256 |
| 9 | CustomCombo | comfy_extras/nodes_logic.py (io.ComfyNode) | logic | generated (comfy_api/_io.py:2058) |
| 10 | EmptyImage | ComfyUI nodes.py | image gen | nodes.py:1938-1944 |
| 11 | EmptySD3LatentImage | comfy_extras/nodes_sd3.py (io.ComfyNode) | latent gen | generated (define_schema) |
| 12 | ImageRotate | comfy_extras/nodes_images.py (io.ComfyNode) | image op | generated (define_schema) |
| 13 | ImpactIfNone | comfyui-impact-pack logics.py | switch logic | logics.py:158-163 |
| 14 | ImpactSwitch | comfyui-impact-pack util_nodes.py | switch | util_nodes.py:17-41 (stack-inspect) |
| 15 | JoinStrings | ComfyUI-KJNodes nodes.py | string op | nodes.py:257-266 |
| 16 | LGNoiseInjectionLatent | comfyui_lg_samplingutils | sampling | noise_injection.py:228+ |
| 17 | ModelSamplingAuraFlow | comfy_extras/nodes_model_advanced.py | model sampling | nodes_model_advanced.py:147-150 |
| 18 | PairConditioningSetProperties | comfy_extras/nodes_hooks.py | hooks | nodes_hooks.py:22-35 |
| 19 | PathchSageAttentionKJ | ComfyUI-KJNodes model_optimization_nodes.py | attention | model_optimization_nodes.py:102-110 |
| 20 | PrimitiveStringMultiline | comfy_extras/nodes_primitive.py (io.ComfyNode) | primitive | generated (define_schema) |
| 21 | SimpleMath+ | comfyui_essentials misc.py | math | misc.py:11-20 |
| 22 | StringToCombo\|LP | comfyui-levelpixel convert_LP.py | conversion | convert_LP.py:120-125 |
| 23 | UNETLoader | ComfyUI nodes.py | loader (FS) | nodes.py:945-948 |
| 24 | VAEDecode | ComfyUI nodes.py | decode | nodes.py:295-301 |
| 25 | VAELoader | ComfyUI nodes.py | loader (FS) | nodes.py:787-788 (vae_list) |
| 26 | easy float | comfyui-easy-use logic.py | primitive | logic.py:168-171 |
| 27 | easy ifElse | comfyui-easy-use logic.py | logic | logic.py:1071-1078 |
| 28 | easy imageSize | comfyui-easy-use image.py | image util | image.py:153-158 |
| 29 | easy indexAnything | comfyui-easy-use logic.py | logic | logic.py:1340-1350 |
| 30 | easy int | comfyui-easy-use logic.py | primitive | logic.py:99-102 |
| 31 | easy stringToIntList | comfyui-easy-use logic.py | conversion | logic.py:1573-1578 |

**Local mapping:** 31/31 reproduced locally (init_extra_nodes with DummyServer bootstrap + UTF-8 console + comfyui-modal class registration mirroring comfyapp.py:18372-18374; total mappings 2192). Local-only deltas vs production were environmental: `PromptServer.instance` absent, cp1252 console ('charmap'), missing local deps (fal_client, sam3, guidedFilter) — none affect the 31.

---

## 5. Per-class cost table (local measurements, cold = first call in fresh process)

| class | cold ms | warm ms | FS (gfl/rs) | result bytes | classification |
|---|---|---|---|---|---|
| ImpactSwitch | 0.521 | 0.468 | 0/0 | 735 | CHEAP_DYNAMIC (inspect.stack) |
| ClownsharKSampler_Beta | 0.146 | 0.027 | 0/0 | 4968 | REGISTRY_DEPENDENT |
| UNETLoader | 0.143 | 0.106 | 1/0 | 398 | FILESYSTEM_DEPENDENT |
| CLIPLoader | 0.125 | 0.085 | 1/0 | 573 | FILESYSTEM_DEPENDENT |
| VAELoader | 0.110 | 0.087 | 2/0 | 199 | FILESYSTEM_DEPENDENT |
| CustomCombo | 0.051 | 0.021 | 0/0 | 74 | PURE_STATIC (schema-gen) |
| PrimitiveStringMultiline | 0.044 | 0.020 | 0/0 | 56 | PURE_STATIC (schema-gen) |
| EmptySD3LatentImage | 0.030 | 0.023 | 0/0 | 225 | PURE_STATIC (schema-gen) |
| ImageRotate | 0.021 | 0.015 | 0/0 | 150 | PURE_STATIC (schema-gen) |
| CacheDiT_Model_Optimizer | 0.006 | 0.004 | 0/0 | 1162 | REGISTRY_DEPENDENT |
| Any Switch (rgthree) | 0.005 | 0.003 | 0/0 | 32 | PURE_STATIC (dynamic optional) |
| CLIPTextEncode | 0.005 | 0.002 | 0/0 | 194 | PURE_STATIC |
| ClownOptions_ExtraOptions_Beta | 0.003 | 0.002 | 0/0 | 117 | PURE_STATIC |
| ComfyModalProductionImageComparerOutput | 0.003 | 0.003 | 0/0 | 110 | PURE_STATIC |
| LGNoiseInjectionLatent | 0.003 | 0.002 | 0/0 | 678 | PURE_STATIC |
| ModelSamplingAuraFlow | 0.003 | 0.001 | 0/0 | 113 | PURE_STATIC |
| PairConditioningSetProperties | 0.003 | 0.001 | 0/0 | 295 | PURE_STATIC |
| PathchSageAttentionKJ | 0.003 | 0.001 | 0/0 | 613 | PURE_STATIC |
| EmptyImage | 0.002 | 0.002 | 0/0 | 311 | PURE_STATIC |
| ImpactIfNone | 0.002 | 0.002 | 0/0 | 67 | PURE_STATIC |
| JoinStrings | 0.002 | 0.002 | 0/0 | 211 | PURE_STATIC |
| SimpleMath+ | 0.002 | 0.001 | 0/0 | 188 | PURE_STATIC |
| StringToCombo\|LP | 0.002 | 0.001 | 0/0 | 73 | PURE_STATIC |
| VAEDecode | 0.002 | 0.001 | 0/0 | 155 | PURE_STATIC |
| easy float | 0.002 | 0.001 | 0/0 | 123 | PURE_STATIC |
| easy ifElse | 0.002 | 0.001 | 0/0 | 107 | PURE_STATIC |
| easy indexAnything | 0.002 | 0.001 | 0/0 | 171 | PURE_STATIC |
| ConditioningZeroOut | 0.001 | 0.001 | 0/0 | 48 | PURE_STATIC |
| easy imageSize | 0.001 | 0.001 | 0/0 | 34 | PURE_STATIC |
| easy int | 0.001 | 0.001 | 0/0 | 79 | PURE_STATIC |
| easy stringToIntList | 0.001 | 0.001 | 0/0 | 79 | PURE_STATIC |

Full-pass context: cold pass **23.96 ms** (FS: 4 get_filename_list / 3 recursive_search ≈ 2.1 ms), warm pass **1.39 ms** (4 gfl / 0 rs ≈ 0.3 ms), third pass **0.97 ms**. `warm_registered_folders`: 388 ms / 29 folders / 14 recursive searches. Loader listings cold: diffusion_models 0.90 ms (7 files), text_encoders 0.34 ms (5), vae 0.19 ms (4), vae_approx 0.26 ms (8); warm 0.15/0.09/0.05/0.08 ms. Threads 7→7; RSS 1270→1273 MB; process CPU ≈ 9 s for the whole measure run. No locks observed; no CUDA touch in warm work (torch.cuda init at harness start is a comfyapp-import artifact of the local harness, not of INPUT_TYPES).

**Wall-by-category (local):** FILESYSTEM_DEPENDENT ≈ 2.1 ms of 23.96 ms cold ≈ **8.8 %**; one-time first-call schema/import work ≈ 21.8 ms ≈ **91 %**; PURE_STATIC/REGISTRY ≈ 0.4 ms ≈ **1.7 %**. Remote (production): the volume-walk component dominates the 0.8–3.6 s — category split shifts to ≈ **90 %+ FILESYSTEM_DEPENDENT** on cold containers, ≈100 % cache-hit/stat on warm ones.

---

## 6. Cold vs repeated evaluation

| pass | wall | delta | driver |
|---|---|---|---|
| 1 (cold, fresh process) | 23.96 ms | — | one-time schema/import + cold volume listings (locally: NTFS) |
| 2 (warm) | 1.39 ms | −94 % | filename_list_cache hit (mtime-validated), module caches warm |
| 3 (warm) | 0.97 ms | −30 % | fully warm |
| per-class repeat (4th/5th call) | 0.001–0.38 ms | ~0 | pure cache hits |

Cost is **first-import dominated** (~22.6 ms one-time local) plus **filesystem-cache dominated** cold listings (2.1 ms local; seconds on Modal volume). Not "repeated every time" in any significant way. **Avoidable repeat cost ≈ 1.0–1.4 ms per additional request in the same container** (production warm-hit evidence: 19.7 ms vs 791–3593 ms cold). Python module cache: 0 (all modules already imported at container boot before the warm thread starts). Registry construction: one-time, µs-scale, cached in class attributes/registries.

---

## 7. Dependency/consumer audit

Warmed artifacts and their consumers:

| artifact | consumer | req. before request? | req. before plan build? | req. before PromptExecutor? | UI/schema only? | safe to persist? | identity/invalidation key |
|---|---|---|---|---|---|---|---|
| `folder_paths.filename_list_cache` + strong cache (text_encoders, diffusion_models, vae, vae_approx) | loader `INPUT_TYPES` during topo walk (get_input_info) | no | no | no (acceleration only) | no | **yes** — the cache itself is mtime-validated per request | folder name + per-dir mtimes |
| one-time schema state (io.ComfyNode class attrs) | INPUT_TYPES / RETURN_TYPES consumers | no | no | no | no | yes (in-process) | class + registry fingerprint |
| `INPUT_TYPES()` results (spec dicts) | request-scoped `get_input_info` memo (runtime_executor 3490-3576) | no | no | no | no | partially — see §9 | (class_type, input_name) per request |
| persisted topo-lazy flags (opt_exec_topo_lazy) | patched get_input_info fast path (b) | no | no | no | no | **yes — already persisted** | signature-memo key hash |

**Bottom line: no later execution path *depends* on the warm.** The request-scoped memo and the persisted topo-lazy store already collapse repeat lookups; the warm only avoids the *first* cold `INPUT_TYPES()`/listing per (class, input) in a cold container. If the warm never ran, the identical work happens in the topo walk of the first request (on the critical path), then all subsequent requests are equally fast. Nothing in plan build, D1 proof, PromptExecutor, or sampler reads warm state.

---

## 8. Omission behavior (local test, production defaults untouched)

Harness `omit` mode: warm once → snapshot schemas → **clear all warmable caches** → re-run pass → compare.

- deferred cold pass (cache-cleared, modules warm): **3.29 ms**, count 31
- **schema mismatch count: 0** (all 31 class schemas byte-identical warm vs cold)
- per-input `get_input_info`-style lookup cost: ≤1 ms/class for all classes
- no failures, no changed plans, no changed schemas, no late work beyond the deferred pass

**Conclusion:** omission does not change any observable output; it **defers the same work to the first topo-walk consumer**, i.e., it moves the 1–3.6 s (remote) from an off-path daemon thread onto the **first-request critical path** (the exact 1177 ms D4 root cause the warm exists to hide). This is the decisive trade-off: *delete* is functionally safe but latency-negative for the first request; the folder listings are re-warmed by the topo walk itself, so warm containers are unaffected.

---

## 9. Cache/snapshot/persist options

| option | saving potential | correctness risk | invalidation | deployment identity deps | custom-node compat | fresh-process behavior | complexity |
|---|---|---|---|---|---|---|---|
| A. DELETE | removes 0.8–3.6 s off-path wall; **adds ~same on first-request critical path** | none (advisory) | n/a | none | n/a | first request pays cold in topo walk | trivial |
| B. WORKFLOW-SCOPE ONLY | already workflow-scoped (classes from plan); could skip classes covered by persisted topo-lazy | none | per-plan class set | none | n/a | unchanged | low |
| C. MEMOIZE IN PROCESS | repeat-cost 1.4 ms (already achieved by folder cache + request memo) | **unsafe cross-request** for full specs (folder contents change) — must stay keyed by mtime | mtime per dir | none | n/a | unchanged | low |
| D. SNAPSHOT RESULT | schema portion only (lazy flags, structure) — **not** the expensive folder listings | low if keyed correctly | registry_fingerprint + deployment_hash + per-class identity + workflow hash | **yes — all present in D1 proof store** (identity_anchor: comfyui_commit/version/deployment_hash/generation; per-class identity hashes) | class-spec portion only | warm-free; persisted store serves | medium |
| E. PERSIST D1-STYLE PROOF/CACHE | same as D; D1 already persists per-class identities + registry fingerprint (schema_version 1) | low | same as D + volume folder-state NOT covered | same as D | consistent with D1 architecture | same | medium-high |
| F. DEPLOY-TIME PRIME | **the real saving**: volume listing cost moves to container boot (0.8–3.6 s removed from first request) | none (same mtime-validated cache) | volume snapshot / boot | deploy image | n/a — core folder_paths | container boots with warm folder cache | low (`warm_registered_folders` already exists; call at boot) |
| G. LAZY ON FIRST CONSUMER | 0 (same work, on critical path) | none | n/a | none | n/a | identical to A | trivial |
| H. RUN AFTER CRITICAL-PATH LOADERS | **negative** — warm would finish after the topo walk needs it; first-request benefit lost | none | n/a | none | n/a | cold topo walk | trivial |
| I. KEEP CURRENT | hides 0.8–3.6 s off-path on cold containers; repeat cost 1.4 ms | none (advisory, swallow-all) | n/a | none | n/a | current behavior | none |

**D1 identity analysis:** INPUT_TYPES class-spec results are deterministic under (deployment_hash, ComfyUI commit, custom-node fingerprint, per-class identity) — D1 already computes and stores all four (proof store `identity_anchor` + `registry_fingerprint` + per-class identity hashes, schema_version 1). A persisted class-spec store keyed on registry_fingerprint is therefore architecturally safe and consistent with D1. **However** the expensive component (loader folder listings) is *not* covered by any registry identity — it depends on volume contents, which is exactly why ComfyUI core re-validates by mtime and why D/E cannot remove the cost. D/E are therefore not worth their complexity for this problem; F is the targeted fix. Nothing from this section was merged into D1 or production.

---

## 10. Local concurrency findings

Method: 12-core Windows host; lanes = warm (real `warm_classes_input_types`, caches cleared per iteration), meta-like CPU (torch CPU matmul + sha256 churn, ~2 s), file-read (357.7 MB model read, chunked). 3 iterations; also a **sim** run with 1 s injected per `recursive_search` (warm ≈ 6 s, emulating Modal-volume latency).

| scenario | meta wall | fileread wall | warm wall | warm thread CPU |
|---|---|---|---|---|
| each alone | 2000–2001 ms | 117–150 ms | 2.7–21.5 ms (cold 39 ms) | 0–31 ms |
| warm+meta | 2000–2014 ms (Δ≈0) | — | 3.4–9.3 ms | 0 ms |
| warm+fileread | — | 110–205 ms (Δ≈0) | 2.7–3.7 ms | 15.6 ms |
| warm+meta+fileread | 2000–2074 ms (Δ≈0) | 287–326 ms* | 4.0–8.8 ms | 0 ms |
| **sim 1s/rs:** warm alone | — | — | 6029–6030 ms | **0–15.6 ms (0.0–0.3 %)** |
| **sim:** warm+meta | 2000 ms (Δ=0) | — | 6014–6011 ms | 0 ms |
| **sim:** warm+fileread | — | 114–176 ms (Δ≈0) | 6007 ms | 0 ms |
| **sim:** warm+meta+fileread | 2000 ms (Δ=0) | 287–326 ms* | 6008 ms | 0 ms |

*fileread inflation in the 3-lane combos tracks the **meta lane** (CPU churn), not the warm lane: warm+fileread without meta shows no inflation, in both normal and sim runs.

**Result: CONTENTION_NOT_SUPPORTED_LOCALLY.** Even with a production-like 6 s warm, the warm thread is ~99.7 % IO-wait (0–16 ms thread CPU over 6 s) and neither the CPU-bound meta lane nor the file-read lane shows any wall inflation attributable to it. On the production temporal evidence (warm 3593 ms overlapping meta 2974 ms / fastsafe 2875 ms, scope=complete) the most parsimonious reading is **independent IO wait**, not CPU/threadpool contention: the warm's own production `effective_cores` were not captured in the old logs, but the meta worker's own effective_cores=0.138 (low CPU) shows the loaders are IO-bound too. This does **not** prove the production hypothesis wrong (Modal-volume IO scheduling and container core allocation differ from this host); it removes the local plausibility for CPU-side contention. Causal test remains remote (§13).

---

## 11. Direct vs indirect performance impact

- **Direct exposed cost: ≈ 0.** The warm is never awaited; its wall (0.8–3.6 s remote) never blocks the request path. Its *hidden* cost is IO-wait on the Modal volume.
- **If removed entirely:** direct wall "saved" ≈ 0 (nothing was exposed); **first-request critical path grows by ~0.8–3.6 s** (topo walk pays the cold listings) — a *negative* saving.
- **If merely moved (F, deploy-time):** first-request critical path shrinks by up to **0.8–3.6 s** (listings already warm at boot); nothing exposed remains in-request.
- **Indirect (contention) saving: HYPOTHESIS ONLY — not supported locally.** If production contention were real (unproven), plausible saving on Worker A/B is bounded by the warm's CPU usage (≈0.1–0.3 effective cores at worst, from the log equation cpu_ms/wall_ms; unobserved directly) — order **0–300 ms**, speculative. Label: HYPOTHESIS.

---

## 12. Recommended architecture

**Keep the warm; add deploy-time folder priming (F + I).**

1. **F — deploy-time prime (primary):** invoke `warm_registered_folders()` during container boot (the existing deploy_warmup/bootstrap path), so the volume listings — the only expensive component — are warm *before* any request. This removes the 0.8–3.6 s race entirely without touching request-path scheduling.
2. **I — keep in-request class warm (backstop):** the class pass costs ~1.4 ms warm / one-time schema work only; keeping it covers schema/first-call work and any folders not registered at boot. Env-gated as today.
3. **Do NOT delete, do NOT move later (A/G/H are latency-negative or useless for the first request).**
4. **B optional:** skip classes already covered by the persisted topo-lazy store (they are served deterministically without INPUT_TYPES); saves the class loop only — minor.
5. **D/E deferred:** architecturally consistent with D1 (identity keys already frozen: deployment_hash, comfyui_commit, registry_fingerprint, per-class identity) but cannot remove the expensive folder-list portion; revisit only if volume-listing cost must be eliminated from cold boots without F.
6. **Observability:** keep `input_types_warm_*` metadata + overlap forensics; add `cpu_ms`/`effective_cores` to the console line (old logs lack them — that gap is why §10's remote read stays partial).

Nothing above was merged into production in this batch.

---

## 13. Future remote ON/OFF experiment definition (still required)

**Goal:** settle causal contention (SUPPORTED → CONFIRMED/REFUTED).

- **Design:** two sequential cohorts of the standard benchmark workflow, same deploy identity (same deployment_hash), N=5+ runs each:
  - Arm ON: `COMFYMODAL_V2_INPUT_TYPES_WARM=1` (current default)
  - Arm OFF: `COMFYMODAL_V2_INPUT_TYPES_WARM=0`
- **Measurements:** per-run trace keys `input_types_warm_*`, `meta_worker_*`, fastsafe worker spans, `method_entry_to_prompt_executor_ms`, topo-walk span, sampler start; plus host wall.
- **Primary outcome:** Δ(meta/fastsafe worker wall + CPU) between arms on **cold containers only** (warm containers are unaffected by definition — 19.7 ms warm evidence).
- **Secondary outcome:** Δ first-request topo-walk span (OFF should show the deferred cold cost; quantifies §8's latency-negative claim).
- **Success criteria:** REFUTED if OFF shows no meta/fastsafe wall or CPU change; CONFIRMED only if ON slows Worker A/B wall *and* CPU materially and repeatably (≥1 SD across 5 runs); otherwise SUPPORTED (unresolved).
- **Constraints (carried from this batch):** no C4, no INPUT_TYPES_WARM=0 speculative production change outside the arm, proof-store identity captured per run, report both wall and thread-CPU per lane.

---

## Appendix A — files created/modified and evidence

- `tools/d9_input_types_warm_forensics.py` (new) — harness: `measure`/`omit`/`bench`/`imports` modes, `--sim-fs-ms` production-latency simulation. Zero Modal calls.
- `tools/d9_measurements.json` (new, evidence) — all local runs: 1× imports, 2× measure, 1× omit, 2× bench (default + sim).
- `tests/test_v2_d9_input_types_warm.py` (new) — 16 tests: enumeration determinism, failure swallowing, absence behavior, omission determinism, class-set determinism vs D1 proof store, diagnostics import safety. **16/16 pass.**
- Affected suites re-run: `test_v2_d6_deploy_profile.py`, `test_v2_batch_d1_registry_proof_store.py`, `test_v2_d1_store_isolation.py` — **32/32 pass**. `py_compile` clean on all touched Python files.
- No production files modified. No deploy. No commit.

## Appendix B — final summary

```
INPUT_TYPES_WARM_PURPOSE = advisory off-critical-path warming of folder listings + one-time
                           INPUT_TYPES/schema work for the first topo walk of a cold container;
                           consumed only as an acceleration by folder_paths caches and the
                           request-scoped get_input_info memo; zero functional dependencies
CLASS_COUNT = 31 (dynamic: distinct class_types of the production-compiled benchmark workflow;
               verified vs D1 registry proof store 31/31)
TOTAL_COLD_WALL = local 23.96 ms (NTFS); production 791–3593 ms (Modal volume; log evidence,
                  worst 3593 ms / D6)
TOTAL_WARM_WALL = local 0.97–1.39 ms; production 19.7 ms warm-cache-hit (log evidence)
LARGEST_CLASSES = CLIPLoader/UNETLoader/VAELoader (FS listings), ImpactSwitch (stack inspect),
                  ClownsharKSampler_Beta + CacheDiT (registry), io.ComfyNode schema-gen classes
FILESYSTEM_COST = local ≈2.1 ms cold / ≈0.3 ms warm (4 listings, 3 recursive searches);
                  remote dominates the cold wall (Modal-volume walk)
IMPORT_COST = one-time ≈22.6 ms local (first-call schema/module work); container-boot import
              cost (24.6 s local analog) is NOT per-request
RESULT_CONSUMER = first topo-walk get_input_info within the same request (memo + folder cache);
                  nothing else reads warm state
SAFE_TO_REMOVE = functionally YES (omission proven: 0 schema mismatches, identical outputs) but
                 NOT recommended — it moves 0.8–3.6 s onto the first-request critical path
SAFE_TO_CACHE = YES in-process (already is: mtime-validated folder cache + request memo);
                a cross-request full-spec memo is NOT safe (folder contents change)
SAFE_TO_SNAPSHOT = class-spec portion YES under D1 identity keys (deployment_hash, comfy
                   commit, registry_fingerprint, per-class identity); folder-list portion NO
SAFE_TO_DEPLOY_PRIME = YES — the expensive folder listings are volume-snapshot deterministic
                       (warm_registered_folders already implements the primitives)
LOCAL_CONTENTION_RESULT = CONTENTION_NOT_SUPPORTED_LOCALLY (0.0–0.3 % CPU during 6 s
                          simulated warm; zero meta/fileread lane-wall inflation in every combo)
DIRECT_EXPOSED_COST = ≈0 (never awaited; off-path)
PLAUSIBLE_INDIRECT_COST = 0–300 ms HYPOTHESIS ONLY (bounded by warm's ~0.1–0.3 effective
                          cores at worst; unmeasured remotely; not reproduced locally)
BEST_FIX = keep in-request warm (I) + deploy-time folder-cache prime (F); do not delete (A)
           or delay (H); D/E deferred as not worth complexity (cannot remove the expensive part)
EXPECTED_SAVING = F: up to 0.8–3.6 s off the first-request path (moved to boot);
                  A would cost ~0.8–3.6 s on the first-request critical path (negative);
                  contention saving ≈ 0 locally (unproven remotely)
NEEDS_REMOTE_OFF_AB = YES (§13 definition; not run in this batch)
FILES_CREATED = tools/d9_input_types_warm_forensics.py, tools/d9_measurements.json,
                tests/test_v2_d9_input_types_warm.py, V2_BATCH_D9_INPUT_TYPES_WARM_FORENSICS.md
FILES_MODIFIED = none (production untouched)
TESTS = 16 new D9 tests (16/16 pass) + 32 affected-suite tests (32/32 pass) + py_compile clean
MODAL_DEPLOYS = 0
MODAL_REQUESTS = 0
COMMIT = none
```
