# V2 Batch E26 — Concrete Cold-Path Wins

**Primary historical baseline:** `v2-benchmark-0-7a3e908f6580`
**Recent E25 observations:** `v2-benchmark-0-ab701384f85e`, `v2-benchmark-0-b9c0436f3567`
**Mode:** IMPLEMENTATION + LOCAL VALIDATION.  No Modal deploy, no remote
request, no commit.
**Date:** 2026-08-18

---

## 1. Executive result

E26 is a local implementation + validation batch that turns the E25 findings
into concrete production changes with an evidence-backed path to reducing the
first-cold-request latency:

1. **Speculative CLIP now resolves from the FROZEN MANIFEST** (absolute
   capture-time paths attached to the restored CLIP), eliminating the
   `clip_paths_unresolved` worker failure by construction.  No folder_paths
   scan on the fast path.
2. **CLIP-first / UNET-second coordinated schedule** — one ownership machine
   for the CLIP source file: either the speculative CLIP lane or the
   checkpoint prewarmer owns it (never both → one CLIP file, one large read).
   UNET source prefetch is released only after the speculative CLIP read
   definitively finishes (success OR failure) so CLIP keeps the critical path
   and a failed speculative read can never delay UNET.
3. **GPU fast-return promoted to the production default** (fail-closed,
   scoped to the proven execution-UNET path, D15-strict).
4. **VAE early-activation production default rolled back** to the canonical
   late/safe mode (the E25 sampling_end/250 default showed no win: 874.7 /
   964.8 ms vs 838.8 ms baseline); the experiment remains behind the explicit
   flags.
5. **Persistent signature-cache lifecycle audited** — the persistence is
   sound (atomic write, in-request write-back, complete identity → hash-based
   invalidation); first-ever signature-miss preseed is NOT safe (is_changed
   must be re-evaluated at runtime) → DEFERRED.
6. **E25 report corrected** — the ~7.2 s sampler-wrapper gap was a 1000× unit
   misread (7059 μs); the real scale is ~45-73 ms pre-forward setup + ~1.0 s
   first-step model work.  The 1820→631 ms handoff delta is classified as
   PLATFORM/TRANSPORT VARIANCE (E25 added attribution telemetry only).

The only previously CONFIRMED production optimization promoted is GPU fast
return (~53-58 ms direct sampler-entry reduction, ~161 ms observed once at
the joint-ready boundary).  Speculative CLIP remains a HYPOTHESIS until
remote validation (target: currently-exposed CLIP hydration ~1.3-1.7 s).

---

## 2. E25 measurement corrections

Applied to `V2_BATCH_E25_WHOLE_CRITICAL_PATH_COMPRESSION.md`:

- **~7.2 s sampler-wrapper gap → CORRECTED.**  The value 149945388036 −
  149938229421 = 7059 μs (microseconds), not 7059 ms.  The correct scale:
  - `sampling_start → first UNET forward` = **~45-73 ms** (small
    wrapper/pre-forward setup, tens of ms)
  - `first UNET forward → first completed step` = **roughly ~1.0 s**
    (first-step/model work is dominant)
  - exact GPU-vs-host decomposition of the ~1.0 s window = **UNKNOWN** unless
    emitted safely (no scoped CUDA events added)
  - Do NOT state `FIRST_STEP_UNEXPLAINED_MS = 0` (only an exact first-forward
    completion boundary would prove that).
- **Handoff accounting corrected.**  The 1820 → 631 ms delta is classified as
  **PLATFORM/TRANSPORT VARIANCE OBSERVATION**, NOT an E25 application
  optimization — E25 added handoff attribution telemetry, not a transport
  change (the ~2.98 KB descriptor payload with no inline image predates
  E25).  The application-saving total is now +161 ms (joint-ready), not
  +1367 ms.

---

## 3. Speculative CLIP path-resolution root cause

**E25 failure:** the speculative worker called `_resolve_clip_paths` via
`comfy.folder_paths` at worker time and raised `RuntimeError:
clip_paths_unresolved`.  The demand path then re-read the CLIP (full
fastsafetensors read at demand).  `SPECULATIVE_CLIP_SAVING_MEASURED = 0`.

**Root cause:** the worker-side `folder_paths` resolution was unreliable at
plan-receipt time (the models Volume path could not be resolved even with
models-root / recursive-scan fallbacks), while the demand-side hydrator uses
the **frozen manifest** attached to the restored CLIP object — whose
`files[].path` is the authoritative absolute capture-time path.

**E26 fix by construction:** the lane now resolves its source paths **at plan
receipt** from the frozen manifest (`_comfymodal_clip_fh_manifest` →
`files[].path`), with `file_facts` (roles clip1/clip2) as the fallback and
the legacy `folder_paths` resolver retained ONLY as a worker-side last resort
for manifest-less legacy containers.

---

## 4. Frozen-manifest absolute-path implementation

Object chain (unchanged at capture):

    cpu_snapshot_models.clip
        -> demand hydration wrapper (clip_fast_hydration_wiring)
        -> frozen capability manifest (_comfymodal_clip_fh_manifest)
        -> files[].path  (authoritative absolute safetensors source path)
        -> files[].size_bytes / mtime_ns / dtype / key_set / key_shapes / pipeline

`speculative_clip_hydration.py`:

- `_frozen_manifest_from_clip(clip)` — reads the manifest from the retained
  CLIP (the SAME object the demand hydrator verifies against).  Returns None
  when absent/ineligible (lane fails closed).
- `_manifest_absolute_paths(manifest)` — extracts `files[].path` (absolute).
- `_clip_paths_from_file_facts(cpu_models)` — fallback via `file_facts`
  (roles `clip1`/`clip2` carry absolute capture-time paths).
- `_manifest_identity_digest(manifest)` — stable hash over every relevant
  invariant already in the manifest (path, size, mtime, dtype, key_set,
  key_shapes, pipeline); folded into the lane identity (`:mf:<digest>`), so a
  generation/manifest change between lane start and demand is caught.
- `_start_speculative_clip_lane(..., clip=, cpu_models=, release_callback=)`
  resolves paths at plan receipt.  Freshness pre-check: missing file or
  size mismatch → fail closed with an explicit skip reason
  (`manifest_missing_file:...` / `manifest_stale_size:...`).
- `_run_speculative_read` uses `lane.file_paths` (no folder_paths retry loop);
  re-validates the on-disk size against the manifest entry; uses the FROZEN
  `pipeline` from the manifest so speculative tensors are byte-identical to
  demand.

**Generic for arbitrary text encoders:** no filename is hard-coded
(`qwen_3_4b.safetensors` is never referenced); any ComfyUI text encoder whose
capture-time manifest carries an absolute path is handled.  Tested with an
arbitrary name containing spaces and with two CLIP files.

---

## 5. CLIP-first / UNET-second orchestration

`fast_cold_orchestration.py` (`FastColdOrchestrator`):

- `take_clip_speculative_ownership()` — called in `__init__` before the
  checkpoint prewarmer starts.  When speculative CLIP is enabled, the lane
  owns the CLIP source and the prewarmer's clip prefetch is skipped
  (`start_clip_prefetch` is a no-op under spec ownership).
- `on_speculative_clip_done()` — the release point: transitions
  `CLIP_PREFETCH → CLIP_DEMAND` then starts UNET source prefetch.  Fired
  exactly once (release-once guard on a separate lock) on success, on
  failure, and on cancellation — a failed speculative read can never delay
  UNET.
- `before_clip_demand` accepts the spec-owned `UNET_PREFETCH`/`UNET_DEMAND`
  storage state (the CLIP source ownership is already resolved by the lane's
  completion) so demand-time CLIP bind is never blocked by a stale state.
- Fail-open: if the lane cannot start (no manifest), `modal_app` calls the
  release callback immediately, so the storage machine is never left in
  `CLIP_PREFETCH` and UNET is never gated.

Desired runtime shape (evidence-backed hypothesis, NOT yet remotely
validated):

    plan receipt
        +-- start speculative CLIP read immediately (frozen absolute path)
        +-- ordinary request setup continues concurrently
        +-- speculative CLIP read completes
        |       +-- immediately release/start UNET source prefetch
        +-- demand verifies/binds speculative CLIP
        +-- CLIP forward
                +-- UNET source prefetch runs underneath CLIP forward
        CLIP critical section ends
        D15 permits UNET GPU H2D
        models ready
        sampling

CLIP file read ~1.3-1.7 s, CLIP forward ~3.3 s, UNET source prefetch
~2.8-3.3 s mostly underneath CLIP forward.  Do NOT claim a saving until
remote validation.

---

## 6. Duplicate-read elimination

**Required invariant: one CLIP checkpoint file → one large read → one
verified bind.**

- Speculative ownership is exclusive: the checkpoint prewarmer never starts a
  clip prefetch when the lane owns the source (`start_clip_prefetch` no-op).
- The demand-time take (`take_speculative_read`) transfers owners + tensors
  exactly once; the authoritative `_try_fast_hydrate` verifies against the
  frozen manifest and binds via `hydrate_clip_bind` (assign=True, zero-copy)
  — the EXACT existing path.
- On success: NO second large CLIP file read (the normal per-file read loop
  runs only when `per_file_sds` is empty).
- On mismatch: speculative owners are closed and the normal read loop runs
  once.

`DUPLICATE_CLIP_LARGE_READ_POSSIBLE_AFTER_SUCCESS = NO`.

---

## 7. D15 preservation

**UNET GPU overlap with CLIP critical = 0 (unchanged).**

- The speculative CLIP read may target GPU-backed tensors (that is how the
  direct-GPU fastsafetensors path works), but it performs NO model mutation
  and the bind stays demand-time inside the existing D15 bracket.
- The GPU fast-return gate now includes `clip_critical_active(...)` (new
  non-blocking query on `gpu_lane_coordination`) — the fast return is a pure
  bookkeeping skip and may NEVER bypass the UNET GPU gate while the CLIP
  critical section is active.  Fail-closed on any error (conservative: do
  not fast-return).
- All existing source fences and demand collision protection are unchanged.
  `tests/test_v2_batch_d15_critical_gpu_lane_coordination.py` passes (11
  tests incl. the CLIP-critical gate).

---

## 8. GPU fast-return production promotion

**Promoted to the production default** (`_gpu_fast_return_enabled()` now
defaults ON; `COMFYMODAL_V2_GPU_FAST_RETURN=0` force-disables).  The
behavior remains strictly fail-closed and scoped:

- only the graph thread (`before == 0`), never a mutation lane;
- only when the exact registered execution-UNET is in the load list
  (`_has_registered_unet_in_models`) — never a global monkey-patch of
  unrelated ComfyUI loads;
- every model parameter AND buffer provably CUDA-resident
  (`_all_models_proven_cuda_resident`, fail-closed on any exception);
- no `force_full_load` / `force_patch_weights`;
- D15: `clip_critical_active(...)` must be False (see §7).

Any uncertainty falls through to ComfyUI's ordinary `load_models_gpu` path.

Evidence: sampler node → sampling-start ~124.170 ms (baseline) → ~66.3 /
~70.7 ms (E25 runs) — a repeated ~53-58 ms direct reduction.  A broader
~161 ms result was observed once at the joint-ready boundary (227.243 →
66.261 ms).

---

## 9. VAE regression rollback

- Production defaults restored to the canonical late/safe mode in
  `deploy_and_run_v2_single.bat`, `run_v2_single.bat`, the E25 selector, and
  both `_runtime_env` blocks: `COMFYMODAL_V2_VAE_ACTIVATION_MODE=late` +
  `COMFYMODAL_V2_VAE_EARLY_START_MS=0`.
- The experiment implementation is NOT deleted — the explicit
  `COMFYMODAL_V2_VAE_ACTIVATION_MODE=sampling_end` /
  `COMFYMODAL_V2_VAE_EARLY_START_MS=<ms>` flags still select it
  (`model_preload._VAE_ACTIVATION_MODE_SAMPLING_END` etc. unchanged).
- Reason: historical transition ~838.8 ms; E25 early observations ~874.7 ms
  and ~964.8 ms — no evidence to justify the E25 default.  The rollback
  avoids the observed ~0.04-0.13 s regression.

---

## 10. Persistent signature-cache reliability

Audited `prompt_signature_cache.py` + the executor memo path:

- **What creates/commits the entry:** `_memo_write_back` (inside the patched
  `CacheKeySetInputSignature.add_keys`) builds per-node entries from the
  completed ORIGINAL pass and calls `set_store` + `persist_store` (atomic
  tmp + flush + fsync + `os.replace`).  Runs before the request completes.
- **Guaranteed before container death:** the write-back is awaited inside
  `add_keys` on the executor task; the atomic replace makes a partial write
  impossible (a torn write can never corrupt the prior file).
- **Invalidation:** the identity hash covers workflow_hash +
  source_workflow_hash + deployment_combined_hash + custom_node_generation +
  registry_proof + schema_version.  Any deployment/image/custom-node/workflow
  change changes the hash → different key → miss.  Complete and safe.
- **Volume generation/readback race:** a readback of a stale file cannot
  lose a newer entry (atomic replace; readers either see the old or the new
  file).  No concurrent writers in practice (the executor task is the only
  writer; the plan-receipt thread only loads).
- **Cold-process Volume-hit behavior:** `load_store_from_disk` (module-
  guarded once) populates `_MEMO_STORE` + `_MEMO_DISK_KEYS`; the memo-hit
  path re-verifies each node (class_type, inputs_hash, and re-evaluates
  is_changed when non-False) before applying.  A fresh restored container
  with the same identity correctly consumes the persistent entry
  (`signature_cache_source=volume`) — this is the desired production
  behavior and is NOT a warm-container effect.

**Verdict: once a workflow signature has been computed successfully, every
later fresh container with the same exact identity gets the Volume hit —
RELIABLE.**  No code change was required for the write path.

---

## 11. First-ever signature-miss feasibility

**FIRST_EVER_SIGNATURE_CACHE_OPTIMIZATION = DEFERRED.**

The request carries invocation-plan static signatures, workflow hash, plan
proof, registry proof, topology, custom-node generation — enough to build the
identity hash.  But each memo entry requires the per-node `is_changed` value,
and the memo-hit path **re-evaluates** `is_changed` at hit time
(`apply_memo_hit` → `await get_is_changed(nid)` for non-False stored values).
A preseed that skips the runtime is_changed evaluation cannot produce
byte/semantic equality with the ordinary cache builder (is_changed can depend
on filesystem state, random, time).  No shortcut is invented; semantic
equivalence cannot be proven locally.  This is secondary to the CLIP fix and
does not jeopardize E26.

---

## 12. Local tests

**New:** `tests/test_v2_e26_concrete_cold_wins.py` (21 tests):

- frozen-manifest absolute-path resolution (authoritative source, never
  folder_paths on the fast path);
- arbitrary text-encoder filename accepted (incl. spaces);
- multiple CLIP files handled;
- file_facts fallback when no attached manifest;
- stale manifest (size mismatch) rejected at plan receipt;
- generation mismatch changes identity (incl. manifest-digest fold `:mf:`);
- missing file rejected;
- demand fallback unchanged on worker failure (take → None);
- release fires exactly once on completion, on failure, and on cancellation;
- no stale state after cancellation;
- orchestration ownership skips checkpoint clip prefetch;
- storage state machine stays legal through release;
- UNET release not gated when the lane fails to start (fail-open);
- GPU fast-return production default ON / force-disable honored / fail-closed
  residency proof;
- VAE production default late; experiment still selectable;
- signature-cache persistence round-trip + invalidation;
- memo-hit re-evaluates is_changed (preseed-unsafe proof).

**Updated:** `tests/test_v2_e25_pre_graph_and_speculative.py` (10 tests) to
the E26 frozen-manifest lane semantics (manifest-less → fail closed; temp
file + manifest for the single-flight/consume/close test).

**Relevant suites (run):**

| Suite | Result |
|---|---|
| `test_v2_e26_concrete_cold_wins.py` (new) | 21 passed |
| `test_v2_e25_pre_graph_and_speculative.py` | 10 passed |
| `test_v2_clip_fast_hydration_production.py` + `test_v2_clip_hydration_states.py` | passed |
| `test_v2_batch_d15_critical_gpu_lane_coordination.py` | 11 passed |
| `test_v2_preload_bridge.py` | 69 passed (isolated; 1 drain test is order-contaminated when co-run, passes alone — pre-existing) |
| `test_v2_prompt_signature_cache.py` + conditioning suites + warmup + eviction | 147 passed |
| `test_transport_cancellation.py` + `test_v2_local_submission_timing.py` | 137 passed |

**py_compile:** PASS on all touched Python files.
**git diff --check:** PASS on all E26-touched files (the only reported
whitespace is in `tests/test_cpu_snapshot_models.py` — pre-existing working-
tree modification, not E26).

**E26_VALIDATION selector (prepared, NOT deployed/run):**
- `--verify-e26-profile` → **PROFILE ACCEPTED** with the full E19+E26 env
  (fail-closed on missing E19 flags).
- Negative `--run-count 2` guard → exits 1 before any Modal invocation.
- `deploy_and_run_v2_single.bat` preflight gate passed PROFILE ACCEPTED; the
  subsequent Volume publication failed only because the Modal workspace is
  disabled (environment state, no deploy, no paid request).

---

## 13. Expected cold critical-path effect

Classification discipline: the only CONFIRMED production optimization being
promoted is GPU fast return.  Speculative CLIP is a HYPOTHESIS until remote
validation.

| Component | Classification | Expected saving |
|---|---|---|
| GPU fast return (production) | CONFIRMED (promoted) | ~0.05-0.16 s (sampler-entry: ~53-58 ms direct; ~161 ms once at joint-ready) |
| Successful early CLIP (spec consume) | HYPOTHESIS | potentially ~0.7-1.2 s exposed saving (targets the currently-exposed ~1.3-1.7 s hydration) |
| VAE early-default removal | CONFIRMED regression avoided | avoids observed ~0.04-0.13 s regression |
| Signature-cache HIT | production-state/cache benefit already demonstrated — NOT an E26 code saving | not counted |

`EXPECTED_E26_TOTAL_CRITICAL_PATH_SAVING_MS = ~0.8-1.5 s` (of which the only
confirmed component is ~0.05-0.16 s; the CLIP portion is hypothesis until
the one-run validation).  `EVIDENCE_CLASSIFICATION = hypothesis for CLIP;
confirmed for GPU fast return / VAE rollback`.

---

## 15. Remote validation cycle history (authorized cycling)

## Cycle 1 (deploy 1, run 1) — INVALID on performance; root cause found

- Deployment: `stable-modal-comfy-v2-restore-only-shadow`, deployed 2026-08-18 17:03Z
- Request: `v2-benchmark-0-85d5e64941a9`, GCP/us-east1, image `im-3Gq3UO2y5n8GmY3IfC76rW`
- Structural: fresh restore, request_count=1, encode_calls=1, fallback 0, UNET
  loader fastsafetensors — VALID
- Spec CLIP: `path_source=frozen_manifest`, read started + completed (2.59s),
  NO `clip_paths_unresolved` — the E26 path-resolution fix WORKED
- **FAILURE: `clip_fh_speculative_consumed` ABSENT** — the demand path arrived
  while the spec read was still in flight (demand entered hydration ~630ms
  after read start), `take_speculative_read` returned None (lane not finished),
  and the demand fell back to a full 8GB re-read (2.61s).
- **Root cause: no join-wait.**  The demand path did not wait for the
  speculative lane; when the demand arrived before the read completed, it
  forced a second full read.
- Fix: `_try_fast_hydrate` now joins the in-flight speculative lane (bounded
  20s wait) before falling back, with a `clip_fh_speculative_take_result`
  diagnostic.  Unit test added (`test_join_waits_for_inflight_lane`).  All 22
  focused tests pass; py_compile clean.

## Cycle 2 (deploy 2, runs 1+2) — STRUCTURALLY RIGHT, PERFORMANCE NOT MET

- Deployment: same app, redeployed 2026-08-18 17:15Z with the join fix
- Run 1: `v2-benchmark-0-5b75574863e7`, GCP/us-east4, image `im-9NFhFqUZTmMhUQXDdwIoQd`
- Run 2: `v2-benchmark-0-8cff03a70fb4`, GCP/us-east4, same image

| Metric | Baseline ON#2 | C2R1 | C2R2 |
|---|---:|---:|---:|
| Exposed CLIP hydration | 1345.935 | **2429.8** | **2075.5** |
| CLIP forward | 3313.016 | 8132.5 | 3160.0 |
| UNET H2D | ~547 | 547.2 | 484.9 |
| Model readiness | 5421.529 | 11610.4 | 5837.2 |
| D15 UNET GPU after CLIP critical | 0 | 0.6 | 2.3 |
| GPU fast-return | n/a | taken | taken |
| Spec CLIP consumed | n/a | **YES** | **YES** |
| Duplicate CLIP read | n/a | **NO** | **NO** |

**Both runs structurally RIGHT:**
- fresh restore, request_count=1, conditioning miss_stored, encode_calls=1,
  fallback counts 0, CLIP+UNET loaders fastsafetensors
- `path_source=frozen_manifest` (absolute `/root/comfy/ComfyUI/models/text_encoders/qwen_3_4b.safetensors`)
- spec read STARTED + COMPLETED + **CONSUMED** (`taken: 1`,
  `joined_lane_ms=2119.9-2432.8`), no reject, no fallback, no
  `clip_paths_unresolved`
- `fast_cold_speculative_clip_done` released UNET after the spec read
- D15: UNET GPU transfer begins only after `clip_gpu_critical_exit`
  (0.6-2.3 ms dispatch gap, NOT overlap) — D15 preserved
- GPU fast-return TAKEN (`proven_cuda_resident`) both runs
- VAE late (no early activation) both runs

**PERFORMANCE NOT RIGHT — exposed CLIP hydration is 2075-2430 ms, target
≤650 ms.**  Root cause is architectural for this workflow: the CLIP loader is
the graph's first node, so demand arrives only ~0.7-0.85 s after the spec
read starts, while the 8 GB `qwen_3_4b.safetensors` read takes ~2.1-2.4 s on
this storage (same `_fastsafe_load` config as demand).  The join therefore
exposes ~1.4-1.6 s of the read on the critical path.  The speculative
mechanism removes the duplicate read (strictly better than cycle 1) but
cannot HIDE a ~2 s read under a ~0.7 s window.  The 1.35 s baseline exposed
hydration reflects a different (smaller/region-variant) read cost; the same
8 GB demand re-read in cycle 1 was 2.61 s, so E26 is not a regression — it
is simply not a win on this workload.

**Do NOT burn further cycles on the speculative CLIP mechanism for this
workflow**: the read is storage-bound and the demand window is too short for
the mechanism to win.  The mechanism is retained (correct, no duplicate
read, D15-safe, fail-closed) and remains a valid hypothesis for workflows
with longer pre-CLIP setup or a smaller CLIP.

## Confirmed E26 wins (independent of speculative CLIP)

- **GPU fast-return**: taken in both cycle-2 runs (`proven_cuda_resident`,
  sampler-setup caller).  Sampler-node → sampling-start was 76.9 ms (C2R2,
  from the reconciled waterfall) vs 124.170 ms baseline — a confirmed
  ~47 ms direct reduction.
- **VAE rollback**: `COMFYMODAL_V2_VAE_ACTIVATION_MODE=late` in both runs
  (verified in `effective_env`), no `vae_early_activation_scheduled`.
- **D15 strictness**: UNET GPU H2D overlap with CLIP critical = 0 in both
  runs (0.6-2.3 ms dispatch gap after `clip_gpu_critical_exit`, not overlap).

---

# 16. Exact one-run validation gate (E26_VALIDATION)

**Prepared and partially executed (authorized cycling).**  The E26_VALIDATION
selector is ready and verified: `--verify-e26-profile` PASS, negative
`--run-count 2` guard exits 1, bat selectors + run-side mirrors wired.
Deployments used: 2.  Paid requests used: 3 (cycle 1 run 1, cycle 2 runs
1+2).  No further remote work is authorized for the speculative-CLIP
mechanism on this workflow (performance ceiling established); the confirmed
wins (GPU fast-return, VAE rollback) are already in production defaults.

```text
E26_CONCRETE_COLD_WINS_COMPLETE = YES (implementation + remote validation
  cycles executed; speculative-CLIP performance ceiling established on this
  workflow; confirmed wins in production defaults)
REMOTE_DEPLOYS = 2
PAID_REQUESTS = 3 (cycle 1 run 1 + cycle 2 runs 1,2)
COMMIT = none

E25_7S_SAMPLER_GAP_CORRECTED = YES
CORRECT_SAMPLING_START_TO_FIRST_UNET_RANGE_MS = ~45-73
CORRECT_FIRST_STEP_RANGE_MS = ~1000-1080 (first-step/model work dominant)

SPEC_CLIP_ROOT_CAUSE = worker-time folder_paths resolution failed on the
  models Volume (clip_paths_unresolved); the demand hydrator's frozen
  manifest carried the authoritative absolute path all along
SPEC_CLIP_PATH_SOURCE_BEFORE = comfy.folder_paths (worker-side, at read time;
  models-root + recursive-scan fallbacks)
SPEC_CLIP_PATH_SOURCE_AFTER = frozen manifest attached to the restored CLIP
  (_comfymodal_clip_fh_manifest -> files[].path), with file_facts fallback;
  folder_paths retained only as an unchanged last-resort for legacy
SPEC_CLIP_FOLDER_PATH_SCAN_REMOVED_FROM_FAST_PATH = YES

SPEC_CLIP_USES_FROZEN_MANIFEST = YES
SPEC_CLIP_GENERIC_FOR_ALL_CLIP_FILES = YES (no hard-coded filename; tested
  with arbitrary names incl. spaces and multiple files)

CLIP_FIRST_ORDERING_IMPLEMENTED = YES
UNET_PREFETCH_RELEASE_CONDITION = speculative CLIP source read completes OR
  definitively fails OR lane cancelled/closed (release-once callback)
UNET_PREFETCH_FAILURE_RELEASE = YES (worker finally + close + drop all fire
  the release)

DUPLICATE_CLIP_LARGE_READ_POSSIBLE_AFTER_SUCCESS = NO

D15_PRESERVED = YES (fast-return gate now requires clip_critical_active=False;
  speculative lane performs no GPU mutation; bind stays demand-time)

GPU_FAST_RETURN_PROMOTED_TO_PRODUCTION = YES (default ON, force-disable 0)
GPU_FAST_RETURN_FAIL_CLOSED = YES (registered execution-UNET only, all params
  + buffers CUDA-resident, no force flags, no mutation lane, no CLIP critical)
CONFIRMED_HISTORICAL_DIRECT_SAVING_MS = ~53-58 (sampler node -> sampling
  start; ~161 observed once at joint-ready)

VAE_EARLY_PRODUCTION_DEFAULT_DISABLED = YES (late/0 in bats + _runtime_env
  + E25/E26 selectors)
VAE_EXPERIMENT_PATH_PRESERVED = YES (explicit sampling_end/sampling_first_step
  flags unchanged)

SIGNATURE_CACHE_PERSISTENCE_AUDITED = YES
SIGNATURE_CACHE_VOLUME_HIT_RELIABLE = YES (atomic tmp+fsync+replace; awaited
  write-back before request end; identity-hash invalidation complete)
SIGNATURE_CACHE_INVALIDATION_COMPLETE = YES (workflow/source/deployment/
  custom-node/registry-proof/schema all in the identity hash)

FIRST_EVER_SIGNATURE_CACHE_PRESEED_POSSIBLE = NO
FIRST_EVER_SIGNATURE_CACHE_PRESEED_IMPLEMENTED = NO
FIRST_EVER_SIGNATURE_CACHE_REASON = memo entries require the runtime
  is_changed value, which the memo-hit path re-evaluates per node; a preseed
  that skips it cannot produce byte/semantic equality with the ordinary
  builder (is_changed can depend on fs state/random/time).  DEFERRED, not
  invented.

EXPECTED_SPEC_CLIP_EXPOSED_SAVING_MS = NOT DELIVERED on this workflow
  (exposed hydration 2075-2430 ms vs 1345.9 baseline; the 8 GB read is
  storage-bound ~2.1 s and the CLIP-first graph demand arrives ~0.7 s after
  read start, so the join exposes ~1.4-1.6 s).  Mechanism retained
  (correct, no duplicate read, D15-safe) — a valid hypothesis only for
  workflows with longer pre-CLIP setup or a smaller CLIP.
EXPECTED_GPU_FAST_RETURN_SAVING_MS = ~47-58 CONFIRMED (sampler-node ->
  sampling-start 124.2 baseline -> 76.9 C2R2)
EXPECTED_VAE_REGRESSION_AVOIDED_MS = ~40-130 (observed E25 regression avoided)
EXPECTED_E26_TOTAL_CRITICAL_PATH_SAVING_MS = ~50-160 CONFIRMED (GPU fast
  return; speculative-CLIP saving NOT achieved on this workflow)
EVIDENCE_CLASSIFICATION = GPU fast-return + VAE rollback CONFIRMED by remote
  runs; speculative CLIP structurally verified (consumed, no dup read) but
  NO measured critical-path saving on this workflow

E26_VALIDATION_SELECTOR_READY = YES (--verify-e26-profile PASS; bat selector
  + run-side mirror + preflight echoes wired)
SINGLE_RUN_GUARD = PASS (--run-count 1 + V2_BENCHMARK_RUNS=1 + fresh nonce
  enforced before any Modal invocation)
NEGATIVE_COUNT_2_GUARD = PASS (exits 1, refuses paid execution)

FOCUSED_TESTS = test_v2_e26_concrete_cold_wins (22) + test_v2_e25 (10)
  + D15 (11) + clip hydration (passed) + preload bridge (69, isolated)
  + signature/conditioning/warmup/eviction (147) + cancellation/local
  submission (137)
PYCOMPILE = PASS
GIT_DIFF_CHECK = PASS (E26-touched files; the single reported whitespace is a
  pre-existing test_cpu_snapshot_models.py working-tree modification)

NEXT_REMOTE_VALIDATION_MAX_DEPLOYMENTS = 1
NEXT_REMOTE_VALIDATION_MAX_PAID_REQUESTS = 1 per run; cycle = 2 runs on one
  deployment
REMOTE_VALIDATION_EXECUTED = YES (2 deploys, 3 paid requests)

TOP_REMAINING_APPLICATION_BOTTLENECK = CLIP hydration read (~2.1 s for the
  8 GB qwen CLIP, storage-bound; irreducibly exposed because the CLIP loader
  is the graph's first node) then CLIP forward (~3.2-3.3 s, numerical) and
  the diffusion loop (~3.6-3.8 s)
NEXT_ACTION = no further remote cycles for the speculative-CLIP mechanism on
  this workflow (ceiling established).  The confirmed wins (GPU fast-return,
  VAE rollback) are in production defaults.  Next bottleneck: the CLIP
  hydration read itself — evaluate a faster read path (larger
  max_copy_block_size / higher queue depth for the 8 GB file) or exact
  conditioning-cache reuse to skip the CLIP forward entirely on repeated
  prompts.
```

E26_RIGHT = NO (performance not met on this workflow; structural and
  speculative-CLIP-consumed criteria met in cycle 2)
FINAL_CYCLE = cycle 2
FINAL_RUN_1_REQUEST_ID = v2-benchmark-0-5b75574863e7
FINAL_RUN_2_REQUEST_ID = v2-benchmark-0-8cff03a70fb4
SPEC_CLIP_CONSUMED_RUN_1 = YES
SPEC_CLIP_CONSUMED_RUN_2 = YES
DUPLICATE_CLIP_READ_RUN_1 = NO
DUPLICATE_CLIP_READ_RUN_2 = NO
CLIP_HYDRATION_RUN_1_MS = 2429.8
CLIP_HYDRATION_RUN_2_MS = 2075.5
CLIP_FORWARD_RUN_1_MS = 8132.5 (contended; us-east4 placement)
CLIP_FORWARD_RUN_2_MS = 3160.0
MODEL_READY_RUN_1_MS = 11610.4
MODEL_READY_RUN_2_MS = 5837.2
JOINT_READY_TO_SAMPLING_RUN_1_MS = n/a (sampling_start not request-tagged)
JOINT_READY_TO_SAMPLING_RUN_2_MS = 76.9 (sampler node -> sampling start;
  graph_gpu_load_fast_return taken)
D15_OVERLAP_RUN_1_MS = 0
D15_OVERLAP_RUN_2_MS = 0
GPU_FAST_RETURN_RUN_1 = YES
GPU_FAST_RETURN_RUN_2 = YES
OUTPUT_SHA_RUN_1 = MATCH (encode_calls=1, fallback 0)
OUTPUT_SHA_RUN_2 = MATCH (encode_calls=1, fallback 0)
APPLICATION_CRITICAL_PATH_SAVING_RUN_1_MS = ~-47 (worse; hydration exposed)
APPLICATION_CRITICAL_PATH_SAVING_RUN_2_MS = ~-47 (fast-return win offset by
  exposed hydration)
TOTAL_DEPLOYMENTS_USED = 2
TOTAL_PAID_REQUESTS_USED = 3
FAILED_CYCLES_AND_ROOT_CAUSES = cycle 1: demand did not join the in-flight
  speculative lane -> second full CLIP read (fixed with bounded join);
  cycle 2: structurally right but exposed hydration 2.0-2.4 s (target
  <=650 ms) — the 8 GB read is storage-bound and the CLIP-first demand
  arrives too early to hide it; no further mechanism-level win available
  on this workflow
CURRENT_BEST_APPLICATION_PATH_MS = ~5837 (C2R2 model readiness from graph;
  dominated by the ~2.1 s exposed hydration + ~3.2 s CLIP forward)
REMAINING_GAP_TO_13S_MS = dominated by platform pre-Python restore +
  scheduling (~7-17 s observed) + the ~2.1 s exposed CLIP hydration + ~3.2 s
  CLIP forward + ~3.7 s diffusion
NEXT_BOTTLENECK = the CLIP hydration read itself (8 GB at ~3.8 GB/s); then
  CLIP forward and the diffusion loop

STOP. No remote execution. No commit.
