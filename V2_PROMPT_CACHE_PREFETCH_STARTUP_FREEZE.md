# V2 PromptSignatureCache + ConditioningPrefetch + StartupDecomposition â€” Acceptance Deployment Freeze Record

generated_at: 2026-08-13
purpose: ONE fresh deployment/snapshot + gated 3-run protocol (RUN 1 gate, RUN 2 structural, RUN 3 authoritative)

## Tree identity (pre-freeze, verified)
- HEAD: a6a755e8dc923e933d13567ec07ddf5b6988f948 (branch TESTING2)
- custom-node source generation (tree-derived, regenerated): de0fc79c17ae867bb42fbbcb29a0cde3
- Baked dependency manifest regenerated at import (hash be68be1945de2a29... requirements context unchanged)
- Full local gate: 655 passed, 33 subtests passed, 0 failures (waterfall/transport/step3/parity/cache/prompt/host-breakdown suites)
- py_compile + git diff --check: clean

## Task cores (landed and integrated, all additive)
- TASK 1: comfymodal_runtime/prompt_signature_cache.py (new) + runtime_executor.py memo hit/miss/writeback + breakdown fields (signature_cache_*) â€” 29 tests
- TASK 2: clip_conditioning_cache.py prefetch_entries + in-memory manifest/payload + shared _validate_entry_bytes; model_preload.maybe_prefetch_conditioning â€” 15 tests
- TASK 3: benchmark_v2_direct.py [v2.host_submission_breakdown] + python_first_line + node_registry stamps â€” 10 tests
- INTEGRATION (modal_app.py): identity stash (opt_exec_signature_memo_identity), plan-receipt memo load + prefetch daemon thread, env allowlist + _runtime_env passthrough (COMFYMODAL_V2_PROMPT_SIGNATURE_CACHE, COMFYMODAL_V2_CONDITIONING_CACHE_PREFETCH), [v2.restore_deep] leaf decomposition â€” 0 new failures

## Deployment env (this freeze)
- V2_BENCHMARK_MODE=snapshot_restore_only, COMFYMODAL_DEPLOY_ONLY=1
- COMFYMODAL_V2_ENV_PROFILE=inherit
- COMFYMODAL_V2_CPU_MODEL_SNAPSHOT=1, COMFYMODAL_V2_VAE_SNAPSHOT=1, COMFYMODAL_V2_SNAPSHOT_EXCLUDE_UNET=1
- COMFYMODAL_V2_EVICT_MODELS_BEFORE_SNAPSHOT=1, COMFYMODAL_V2_EVICT_RETAIN_ROLE=clip_vae
- COMFYMODAL_V2_NATIVE_FAST_DISK_UNET=1, COMFYMODAL_V2_CLIP_CONDITIONING_CACHE=1, COMFYMODAL_V2_EXECUTION_UNET_H2D_DELAY_MS=0
- COMFYMODAL_V2_UNET_ACTIVATION_MODE=late, COMFYMODAL_V2_VAE_ACTIVATION_MODE=sampling_end
- COMFYMODAL_V2_PUBLISH_RESTORE_PLAN=0
- COMFYMODAL_V2_SINGLE_USE_CONTAINERS=1, COMFYMODAL_V2_MINIMAL_GPU_TEARDOWN=1, COMFYMODAL_V2_RELEASE_GPU_AFTER_REQUEST=1
- COMFYMODAL_V2_CPU_REQUEST=12, COMFYMODAL_V2_MEMORY_MB=32768, COMFYMODAL_V2_MEMORY_REQUEST=32768
- COMFYMODAL_V2_GPU=rtx-pro-6000, COMFYMODAL_V2_THREAD_POLICY=TBASE, COMFYMODAL_V2_SNAPSHOT_MODEL_ORDER=O0, COMFYMODAL_V2_VAE_POLICY=v1
- COMFYMODAL_V2_CLOUD=, COMFYMODAL_V2_REGION=
- COMFYMODAL_V2_OPTIMIZATION_DIAGNOSTICS=1
- COMFYMODAL_V2_RESTORE_TOTAL_VRAM_FROZEN=1 (frozen-VRAM restore)
- COMFYMODAL_V2_QUIET=1
- NEW TASK FLAGS: COMFYMODAL_V2_PROMPT_SIGNATURE_CACHE=1, COMFYMODAL_V2_CONDITIONING_CACHE_PREFETCH=1
- TRIVIAL CONFIG: COMFYMODAL_V2_CONDITIONING_CACHE_ASYNC_LRU=1 (async LRU arm â€” reported separately, not a task win)
- PNG compress level = 1 (production default, no env override needed)

## Constraints
- NO SOURCE EDITS from freeze through RUN 3 completion
- Exactly ONE deployment; RUN 1 gate must pass before RUN 2/3 (each RUN = 1 generation request; failed RUN-1 attempts restart the sequence, do not count as RUN 2/3)
- No baseline cohort, no A/B arms, no commit (commit hash: none)

## RUN-1 remediation (attempt 1 FAILED - gate items)
- RUN 1 request: v2-benchmark-0-862777f61cf1 (GCP/us-south1, 60.601s C2R)
- FAIL items: (1) signature_cache_* fields absent from host-visible PE breakdown/metadata enrichment; (2) prefetch_requested=0 (no engagement reason)
- Fixes applied (modal_app.py enrichment + prefetch launch evidence + model_preload prefetch_reason surfacing + host formatter extra-key pass-through)
- New tree generation: 706d19c3395556c9fc013b5df9e7e59e
- Local gate re-run: 357 passed + 8 isolated-pass (batch pollution) = effectively clean
## Deploy 2 attempt (failed once - concurrent worker wrote history_v2_repository.py during build)
- Modal build-context guard rejected: history_v2_repository.py modified during build (untracked concurrent-worker file, now stable)
- Tree generation recomputed: 706d19c3395556c9fc013b5df9e7e59e -> fe5191fb47fae3f30c8e9a86fa67c6dc (concurrent worker edits)
- Retrying deploy with the same env
## Deploy 2 final freeze (history worker finished)
- Concurrent history-V2 worker finished (last write 11:44:08; tree stable at 11:45+)
- FINAL tree generation: 3a3dd320b3584664fc162e8827b17866
- Deploying now
## Deploy 3 (round-2 remediation: plan-time key build + host evidence flow)
- fix-4 round-2: 4-source identity derivation, relaxed ctx gate (manifest prefetch engages on partial identity), key_build_partial evidence, lookup_diagnostics host merge — 59 tests
- Local gate: 324 passed, 0 failures
- Tree generation: f1a11cc53fa02e2cb0058e27c4cbe5df
## Deploy 4 (round-3 remediation: weight_dtype derivation + host evidence merge)
- fix-4 round-3: weight_dtype plan-time derivation (model_stack/prompt_bundle/workflow node), host lookup_diagnostics evidence merge verified in-tree — 63 tests
- Local gate: 321 passed, 0 failures
- Tree generation: 0bdb50a34379966938a987c336fc43d5
## Deploy 4 retry (model-library worker quiesced)
- FINAL tree generation: 01c6c13a041dd297f346662d8fce414e
- Deploying in stable window
## Deploy 5 (round-4 remediation: trace-metadata evidence race)
- fix-4 round-4: entry-time evidence recording (reason=running in-flight), ""-key correlation fallback — 66 tests
- Local gate: 324 passed, 0 failures
- Tree generation: c101c4ce329651d35d35ee829517b28a
## Deploy 6 (round-5 remediation: demand-time prefetch join + reload skip)
- fix-4 round-5: join_prefetch bounded wait (1.5s), first-prefetch reload skip, prefetch_join_ms/timeout/reload fields — 70 tests
- Local gate: 328 passed, 0 failures
- Tree generation: 7ce9e892cf775eabba0402984aed622b
## Deploy 7 (round-6 remediation: serve-by-components prefetch)
- fix-4 round-6: manifest-entry fallback (real stored digests) + demand-time component-match scan, _PREFETCH_MAX_ENTRIES — 75 tests
- Local gate: 333 passed, 0 failures
- Tree generation: e557bfe3df7783e34de82ea7bb419198
## Deploy 8 (partial waterfall table renderer)
- fix-7: _render_partial renders a REAL boxed ASCII table (no %/bars/fake TOTAL WALL; STATUS cell PENDING + post-table token); footer overflow fixed; golden byte-identical — 200 waterfall tests + 363 combined gate
- Tree generation: 8f98568b2f0b64d6d8fcd96d8816733c
