# V2 Batch D10 — Phase-D Integration Validation

**Date:** 2026-08-16 · **commit:** none · **C4:** NOT RUN · **Outcome:** `STOP_CAPTURE_GATE`

**Authorized budget:** EXACTLY ONE deploy · AT MOST ONE true-cold request

**Actual spend:** 1 deploy (v43) · 0 inference requests

---

## 1. Executive verdict

**STOP_CAPTURE_GATE — the single authorized deployment executed once and
reached a Modal memory snapshot, but the capture-side final-state gate
(Gate D) FAILED: `capture_pre_snapshot_return state=INVALID/PARTIAL` with
`meta_params=0 total_params=0 manifest_eligible=False` instead of the required
`EXCLUDED_PLACEHOLDER cpu_bytes=0 meta_params=399 manifest_eligible=true`.
Per the hard gates (Part 6 Gate D, Part 8), the ONE cold request was NOT
issued. No second deploy, no second request, no retries.**

Positive results this run:

- D1 dispatch gap: identity record completed (60 s) against the NEW deployment
  identity `d679332c551f0cad` — differs from every stale anchor
  (`e8f269ee…`, `3a156e5d…`).
- D3/D6 capture exclusion: physically effective — `capture_post_exclusion`
  `EXCLUDED_PLACEHOLDER cpu_bytes=0 meta_params=399`.
- Old CLIP dies: `original_clip_alive_after_full_eviction=0` — the D6 F-B
  `_LAST_CLIP` weakref fix holds in the real Modal container.
- Post-eviction reconcile ran: `status=excluded_after_eviction_reload
  wrapper_installed=installed params_replaced=399`.
- Platform snapshot: `Snapshot created. Restoring Function from memory
  snapshot.` (16:01:41.510Z) followed by a successful restore
  (`restore_count=1`, `restore_status=success`).

The failure is strictly the final capture-boundary object state: between the
eviction reconcile event (16:01:29.809Z) and the startup ready-return
checkpoint (16:01:29.853Z) the retained CLIP shell shows zero parameters and
no manifest. This is a NEW structural failure mode (distinct from the D6
eviction-crash) and is exactly what the capture gates exist to catch. The
snapshot exists, but the retained CLIP object is not the excluded placeholder
with an attached manifest, so the restore-side hydration contract is not
trustworthy. NO REQUEST.

## 2. Spend accounting

| Item | Count | Notes |
|---|---|---|
| `modal deploy` | **1** | v43, `stable-modal-comfy-v2-restore-only-shadow`, 68.742 s, success |
| identity record (construction trigger) | 1 | `get_deployment_identity_static` remote readback, 60 s, status=ok |
| `--prime-registry-proof` | 0 | NOT run (capture gate failed first; per Part 7/8 no prime on gate failure) |
| true-cold inference request | **0** | not authorized |
| deploys attempted again | 0 | — |

## 3. Effective profile (verified, `--verify-d6-profile`)

```
[v2.d6_deploy_profile]
profile=d10_integration_validation
unet_fastsafetensors=1
clip_fast_hydration=1
clip_snapshot_exclude_weights=1
clip_cold_forensics=1
clip_cold_forensics_cast=1
clip_cold_forensics_sync_cuda=0
input_types_warm=1
unet_forensics=0
validation=PASS
```

Container-side proof the flags baked (construction session):
`clip_fh_capture` exclusion present; forensics status installed (D10 profile
baked at deploy via `_runtime_env()`); `[v2.clip_state]` checkpoints emitted.

D10 profile = D6 profile minus `CLIP_COLD_FORENSICS_SYNC_CUDA` (D6's SYNC=1
installs a global `torch.cuda.synchronize` wrapper + CUDA-event realize per
`ModelPatcher.load/partially_load` — INTRUSIVE per the Part-1 audit). D10 keeps
all structural diagnostics with production sync semantics only.

## 4. Measurement-integrity audit (Part 1)

| Feature | Flag | Class | Sync on request path |
|---|---|---|---|
| CLIP cold forensics (main) | 1 | LOW_OVERHEAD (wall/CPU timers + `_clip_identity` scans, ~0.3–2.5 ms/encode) | none |
| CLIP cast forensics | 1 | LOW_OVERHEAD (counter/histogram, ~1–3 µs/op) | none |
| CLIP cold forensics SYNC_CUDA | **0** | (would be INTRUSIVE) | n/a — OFF |
| UNET forensics | 0 | OFF (deep profiler skipped) | n/a |
| Fast hydration | 1 | production feature; one sync only when hydration actually executes | inherent |
| UNET fastsafetensors | 1 | production loader; stage timestamps + memory snapshots, no CUDA events | 1 inherent final sync |
| input_types_warm | 1 | background daemon, off-critical-path | none |
| Lifecycle checkpoints / trace | — | PASSIVE (µs-scale emits) | none |
| Pagefault tracking | default ON | LOW_OVERHEAD (getrusage on load path only) | none |

**AUTHORITATIVE_TIMING_INSTRUMENTATION = PASS**
**INTRUSIVE_SYNC_IN_CRITICAL_PATH = NO**
**DEEP_PROFILER = OFF**
**PASSIVE_CUDA_EVENTS = YES (inherent loader events only; no diagnostic sync)**
**CAST_INSTRUMENTATION_OVERHEAD = low (counter-only; measured locally as 1–3 µs/op)**

## 5. Crash-loop watchdog result (Part 5)

**CRASH_LOOP_DETECTED = NO.** Exactly one startup attempt in the construction
session (`snap_true_enter event=start` 16:00:53.192Z; single
`method=startup`), no `Runner failed` lines, no repeated identical failures,
no `RuntimeError` in the window. The previous D6 broken-deploy fingerprint
(`original_clip_alive_after_full_eviction=1` + `RuntimeError('Full eviction
failed...')`) does NOT appear anywhere in the v43 window.

**CRASH_FINGERPRINT = none**

## 6. Snapshot capture gates (Part 6)

| Gate | Expected | Observed (UTC) | Result |
|---|---|---|---|
| A capture_pre_exclusion | `CPU_NATIVE_MATERIALIZED` | `state=CPU_NATIVE_MATERIALIZED cpu_bytes=8044936196 cpu_params=399` (16:01:25.890) | **PASS** |
| A capture_post_exclusion | `EXCLUDED_PLACEHOLDER cpu_bytes=0 meta_params=399 manifest_eligible=true` | `state=EXCLUDED_PLACEHOLDER cpu_bytes=0 cuda_params=0 meta_params=399 cpu_params=0 manifest_eligible=True` (16:01:25.935) | **PASS** |
| B old CLIP dies | `original_clip_alive_after_full_eviction=0` | `status=full_eviction_complete ... original_clip_alive_after_full_eviction=0` (16:01:28.319) | **PASS (HARD GATE)** |
| C eviction reconcile | `status=excluded_after_eviction_reload wrapper_installed=installed` | `[v2.clip_fh] eviction_reconcile status=excluded_after_eviction_reload wrapper_installed=installed manifest_eligible=1 params_replaced=399 payload_bytes_removed=8044936196 clip_reloaded_fresh=1` (16:01:29.809) | **PASS** |
| D capture_pre_snapshot_return | `state=EXCLUDED_PLACEHOLDER cpu_bytes=0 cpu_params=0 meta_params=399 manifest_eligible=true` | `state=INVALID/PARTIAL cpu_bytes=0 cuda_params=0 meta_params=0 cpu_params=0 total_params=0 manifest_eligible=False` (16:01:29.853) | **FAIL** |
| E Snapshot created | platform `Snapshot created` | `Snapshot created. Restoring Function from memory snapshot.` (16:01:41.510) + restore `restore_count=1 restore_total_ms=622.816 restore_status=success` (16:01:44.236) | **PASS** |

**Gate D failure detail:** reconcile ran at 16:01:29.809Z claiming
`manifest_eligible=1 params_replaced=399` on the reloaded object, but 44 ms
later the `capture_pre_snapshot_return` checkpoint (which inspects
`self._cpu_snapshot_models` at the ready boundary) reports an object with
`total_params=0` and `manifest_eligible=False`. The retained shell at capture
has NEITHER CPU params NOR meta params — the excluded-placeholder
reconstruction (strip + manifest + wrapper on the NEW object) did not survive
onto the object actually retained for capture, or a subsequent strip cleared
the meta markers. Also notable in the eviction ready line:
`floor_failures=2 floor_failures_details=full_eviction_rss_drop=1005.2;
final_reduction=-3340.8` (RSS floor check failed twice; reload RSS exceeded
full-model RSS), `patcher_cleanup_errors=1`.

Per Part 6: Gate D is mandatory — the deployment logs did NOT prove the full
required logical sequence. **NO REQUEST.**

## 7. D1 identity / proof (Part 7)

- Identity record: `tools\record_deployment_identity.py` ran ONCE, bounded,
  60 s, `status=ok`.
- **NEW deployment identity = `d679332c551f0cad`** (`deployment_combined_hash`),
  `custom_nodes_generation=32ffaf27…`, `overall_dependency_hash=be68be19…`,
  `comfyui_core_match=1`, manifest_classes=2399, written to
  `.deployed_state.json` (`deployed_at=2026-08-16T16:01:44.647471+00:00`,
  `source=container_readback`).
- Differs from stale prior anchor `e8f269ee…` AND the cancel-proof lane's
  `3a156e5d…` — no stale identity can qualify.
- **D1 prime: NOT RUN.** Per Part 7/8, priming is authorized only after
  snapshot health is proven; Gate D failed, so the store was intentionally
  NOT primed for this identity (a proof entry for a broken capture would be
  misleading).

## 8. Restore CLIP state chain

**NOT OBSERVED** — the request was not issued, so restore-side checkpoints
(`restore_first_instruction` … `conditioning_prefetch_worker_start`) and the
hydration chain were not exercised. A platform restore DID run once at the
end of the construction session (`method=restore restore_count=1
restore_total_ms=622.816 restore_status=success`), but the captured CLIP
state is INVALID/PARTIAL, so no restore-side structural claim is made.

## 9. CLIP direct-GPU hydration

**N/A — no request.** The snapshot's retained CLIP failed Gate D, so the
demand-hydration path was never reached.

## 10. Clean production encoder forward

**N/A — no request.**

## 11. Generic cast-tax evidence

**N/A — no request.** (Cast forensics remained enabled in the baked profile,
ready for the next valid run.)

## 12. UNET fastsafetensors

**N/A — no request.** (UNET is absent from the retained snapshot by design —
`snapshot_exclude_unet=1` — and would load via fastsafetensors at request
time; not exercised.)

## 13. Meta worker reconciliation

**N/A — no request.**

## 14. input_types_warm

**N/A at request time.** Enabled (baked `1`); the input-types warm thread runs
at request activation, which never happened.

## 15. D5 critical path / overlap

**N/A — no request.**

## 16. Restore measurement

Only the construction-session restore was observed: `restore_total_ms=622.816`,
`restore_status=success` (16:01:44.236Z). Request-time restore was not
exercised.

## 17. Sampling

**N/A.**

## 18. VAE/output

**N/A.**

## 19. Correctness

**No output produced (no request).** Canonical SHA
`20b10e1f99831bc758d9df82f43ce0beb1cbc636a740d11a29eb2bffe90e5260` not
applicable.

## 20. Permanent footer

```
COMMAND -> RESPONSE:                       N/A (no request)
Command (without scheduling) -> Response:  N/A
Scheduling time:                           N/A
```

## 21. 12-second budget

**N/A** — no request; no production-scale timings were obtained. The
planning-budget comparison is deferred to the next valid run.

## 22. Phase-D remaining bottlenecks

1. **NEW: post-reconcile capture-state loss (Gate D).** The reloaded CLIP's
   excluded-placeholder reconstruction (manifest + strip + wrapper) does not
   survive onto the object observed at `capture_pre_snapshot_return`
   (`total_params=0`, `manifest_eligible=False`). This must be root-caused
   locally (eviction reload → reconcile → capture boundary object identity)
   before any further remote spend.
2. D6's eviction weakref crash: **FIXED and proven in-container** (Gate B = 0).
3. Unknown until a valid request: hydration wall, clean encoder forward,
   cast tax at 4B+ scale, UNET fastsafe remote timing, meta worker behavior,
   input_types_warm overlap, D5 critical path.

## 23. Exact next experiment recommendation

**Next batch: D10-F (local, zero spend) — reconcile-to-capture object audit.**

1. Reproduce locally with the real wiring: eviction reload → `_reconcile` →
   `capture_pre_snapshot_return` boundary; assert the SAME object identity
   (`reloaded_model_id` vs the object `clip_state_checkpoint` inspects) and
   that meta params + manifest survive to the boundary.
2. Add a local test asserting: after eviction reconcile, the
   `_cpu_snapshot_models` clip attribute is the reconciled new object with
   `meta_params=399`, `manifest_eligible=True` at the ready-return boundary
   (i.e., exactly the Gate-D expectation), failing on the current tree if the
   bug reproduces locally.
3. Only after the local Gate-D-equivalent test passes: ONE redeploy + gates
   A–E + identity record + prime + ONE true-cold request with fresh nonce.
   Reuse the D10 profile (SYNC_CUDA=0).

---

## Artifacts preserved (do not overwrite)

- `v2_d10_deploy_1.log` / `v2_d10_deploy_1.err.log` — deploy command output (v43)
- `v2_d10_applogs_full.txt` — construction session app logs (gates A–E evidence)
- `v2_d10_applogs_v41_deploy3.txt` / `v2_d10_applogs_v42_deploy4.txt` —
  historical healthy/broken windows (reference)
- `v2_d10_applogs_info_snapshot.txt`, `v2_d10_applogs_info_v2.txt`,
  `v2_d10_applogs_stdout_v2.txt`, `v2_d10_applogs_all_stdout.txt` — scoped log queries
- `v2_d10_identity_record.out.txt` / `.err.txt` — identity record output
- `v2_d10_applist_full.json` — app inventory
- `.deployed_state.json` — new identity `d679332c551f0cad` (container readback)
- Prior D6 evidence untouched.

## Environment / provider fingerprint

- Workspace `Testing 4` (ws_f1a4990a74fd), environment `main`
- App `stable-modal-comfy-v2-restore-only-shadow`, deployment v43
- modal client 1.4.3; image `im-cNyUNfPut7XEY7r5k0mOBY` (fastsafetensors 0.3.3 baked)
- Construction session: `container_session=49800b889c184479`, snapshot at
  16:01:41.510Z, restore 16:01:44.236Z, `restore_total_ms=622.816`
- CUDA/Torch identity from construction log: torch 2.13.0+cu130 (baked);
  GPU identity not exercised at request time (no request)

---

# Gate-D Reconcile-to-Capture Root Cause

*(Appended 2026-08-16 — zero-spend local investigation. The STOP_CAPTURE_GATE
verdict above remains unchanged as historical evidence.)*

## Root-cause class

**CHECKPOINT_TARGET_MISMATCH** — the reconciled CLIP never disappeared. Gate D
observed the WRONG HOLDER.

## What the 44 ms actually contained

| Boundary | Time (UTC) | Event | Object probed |
|---|---|---|---|
| Reconcile | 16:01:29.809 | clip_fh_eviction_reconcile status=excluded_after_eviction_reload wrapper_installed=installed manifest_eligible=1 params_replaced=399 payload_bytes_removed=8044936196 | fresh reloaded CLIP (id 46640790350864) |
| status=ready | 16:01:29.819 | eloaded_model_id=46640790350864 reloaded_model_is_new_object=1 original_clip_alive_after_full_eviction=0 | same object via container.clip |
| Gate D | 16:01:29.853 | capture_pre_snapshot_return state=INVALID/PARTIAL total_params=0 manifest_eligible=False | **CpuSnapshotModels CONTAINER** |

modal_app.py:9296-9300 passes self._cpu_snapshot_models (the container
dataclass) to clip_state_checkpoint as the `clip` argument.
clip_hydration_state() (clip_fast_hydration.py:923-1084) walks the passed
object LITERALLY — no .clip unwrap. A container has no cond_stage_model,
no _comfymodal_clip_fh_manifest, no markers, no patcher → the walk yields
exactly params.total=0, manifest_eligible=False, classification falls
through to INVALID/PARTIAL. That is the observed Gate-D line, byte for byte.

The reconciled CLIP (id 46640790350864) was alive, healthy, and still assigned
to _cpu_snapshot_models.clip at Gate D — it is the canonical retained
object the restore path consumes (_activate_clip_vae_only_request_binding
publishes models.clip; restore-side demand wrapper re-install targets the
same holder). The ordered call graph between 6946 and 9296 contains **zero**
operations touching the CLIP or its manifest/wrapper (only VAE metadata
writes, RSS reads, floor prints, marker stores, del locals).

## Holder table (both boundaries)

| Holder | Reconcile | Gate D | Same? | Intentional? |
|---|---|---|---|---|
| _cpu_snapshot_models.clip (= _container_retained.clip = cpu_models.clip) | fresh CLIP id …350864 | same object | **YES** | YES — canonical retention root |
| _reloaded_model local | fresh CLIP | deleted (7221) | n/a | YES (non-owning after) |
| _snapshot_eviction_retained_model | None (clip_vae role) | None | YES | YES |
| _LAST_CLIP (wiring) | weakref | weakref | n/a | YES — non-rooting |
| _preload_bridge | cleared | cleared | YES | YES |
| Comfy model_management | — | fresh reload not registered here | n/a | n/a |

## Patcher cleanup error (patcher_cleanup_errors=1)

Counters from modal_app.py:6441-6493 — best-effort cleanup()/detach(True)
hygiene on the ORIGINAL objects (CLIP/UNET/VAE) BEFORE the fresh reload, with
bare except Exception increments. ModelPatcher.cleanup()/detach() never
clear patcher.model or remove modules/params. **Cannot touch the reconciled
CLIP. Classification: UNRELATED** (synthetic local repro proves a cleanup
error path leaves the reconciled clip's Gate-D state intact).

## RSS floor failures (full_eviction_rss_drop=1005.2, final_reduction=-3340.8)

Floor gates are diagnostic-only and non-fatal (modal_app.py:7020-7082).
RSS above baseline is allocator/page-cache artifact: the original CLIP was
already stripped at startup, full eviction frees only ~1 GB (freed UNET pages
stay resident in glibc/torch caches; malloc_trim(0) trims arena tops only),
then the fresh reload allocates the full 8.38 GB CLIP payload (anonymous,
DISABLE_MMAP) + VAE, and the reconcile strip frees it without a subsequent
gc/malloc_trim — so the pages remain resident at measurement time.
selected_storage_total_mib=7991.996 (pre-strip registry) proves the fresh
CLIP+VAE carried the payload; storage identity remains authoritative.
**Classification: EXPECTED_ALLOCATOR_BEHAVIOR.**

## Fix (landed, generic, default-OFF preserved)

comfymodal_runtime/clip_fast_hydration_wiring.py:

1. **esolve_capture_clip(holder)** — deterministic, capability-based holder
   resolver: None -> ("none"); cond_stage_model only -> ("direct");
   clip attr only -> ("cpu_snapshot_models.clip"); both -> ("ambiguous")
   fail closed; else ("unsupported"). Returns the object + holder source;
   stores nothing; never roots; never mutates.
2. **clip_state_checkpoint(trace, name, holder)** now resolves the canonical
   clip first, emits value-only object IDs (clip_object_id,
   cond_stage_model_object_id, patcher_object_id,
   underlying_model_object_id), holder_source, manifest_present,
   manifest_eligible, demand_wrapper_present, hydration_marker_present
   alongside the existing counts. Cleared/absent holder -> state=no_clip
   (fail closed, never fabricated INVALID). All 6 modal_app call sites
   (Gate D + 5 restore-side checkpoints) are fixed centrally — Gate D now
   inspects the ACTUAL canonical object restore consumes.

Gate D is NOT weakened: with the fix the boundary reports the true state
(EXCLUDED_PLACEHOLDER, meta_params=399, manifest_eligible=true) because the
canonical object genuinely satisfies the contract.

## Local reproduction (real sequence, Gate-D equivalent)

New TestGateDReconcileToCapture in tests/test_v2_clip_eviction_lifecycle.py:
capture -> original dies -> fresh CPU reload -> reconcile -> post-reconcile
cleanup/finalization -> capture_pre_snapshot_return against the CONTAINER.
Results: same object id survives; EXCLUDED_PLACEHOLDER, meta=full, cpu=0,
cpu_bytes=0, manifest present+eligible, wrapper present; cleared-holder and
ambiguous-holder cases fail closed; strip idempotent; patcher-cleanup-error
path harmless; telemetry non-rooting (weakref contract preserved);
capture/restore consume the same holder (AST proof).

Also TestD10QuarantinedIdentityUnprimed in tests/test_v2_d1_stale_identity.py:
identity d679332c551f0cad lookup fails closed on the unprimed store and can
never consume another anchor's entry.

## Evidence

`
RECONCILE_OBJECT_ID = 46640790350864
GATE_D_OBJECT_ID    = 46640790350864 (same object; container.clip)
SAME_OBJECT         = YES
CANONICAL_CAPTURE_HOLDER = _cpu_snapshot_models.clip
`

## Test counts (this investigation)

- clip lifecycle + reconcile + hydration states + restore lifecycle + fast
  hydration production: 110 OK (1 skip)
- cpu snapshot lifecycle/models + snapshot restore-only + preload bridge +
  phase-d telemetry: 462 OK (1 skip)
- D1 stale identity (incl. new D10 quarantine tests) + registry proof +
  dispatch hash + store isolation + local dispatch + D6/D10 profile +
  plan validation + deployment proof: 93 OK
- py_compile (wiring + both extended test files): OK
- Total: 665 OK / 2 skips / 0 failures — no unexplained failures

## Next step (not executed — awaiting authorization)

ONE redeploy with the D10 production-semantics profile
(CLIP_COLD_FORENSICS_SYNC_CUDA=0, UNET_FORENSICS=0), then the same hard
gates A-E; Gate D must now print
state=EXCLUDED_PLACEHOLDER cpu_bytes=0 meta_params=399 total_params=399
manifest_eligible=True holder_source=cpu_snapshot_models.clip. Then identity
record + D1 prime + ONE true-cold request with a fresh nonce.

---

# Corrected Gate-D Remote Integration Validation

*(Appended 2026-08-16 — final authorized run. Prior STOP_CAPTURE_GATE and
Gate-D root-cause sections remain unchanged as historical evidence.)*

## Outcome

**MEASUREMENT_INVALID — MODAL_REQUEST_COUNT = 1.** The corrected deploy (v44)
passed every capture/identity/prime gate; the single authorized true-cold
request WAS issued and executed remotely, but the local harness rejected the
run artifact at its C8 runtime-shape validation gate, so no valid measurement
artifact (run_0.json / waterfall / output SHA) was produced. Per the batch
rules ("Never rerun", "If request occurs: Modal request count must be exactly
1"), NO second request was issued.

## Gates (all PASS before the request)

| Gate | Evidence | Result |
|---|---|---|
| PROFILE | profile=d10_integration_validation validation=PASS | PASS |
| NO_CRASH_LOOP | single startup attempt; no failures | PASS |
| A1 | capture_pre_exclusion CPU_NATIVE_MATERIALIZED cpu_params=399 cpu_bytes=8044936196 | PASS |
| A2 | capture_post_exclusion EXCLUDED_PLACEHOLDER cpu_bytes=0 meta_params=399 manifest_eligible=True | PASS |
| B | original_clip_alive_after_full_eviction=0 | PASS |
| C | eviction_reconcile status=excluded_after_eviction_reload wrapper_installed=installed params_replaced=399 clip_reloaded_fresh=1 | PASS |
| D state | capture_pre_snapshot_return EXCLUDED_PLACEHOLDER cpu_bytes=0 meta_params=399 total_params=399 manifest_present=True manifest_eligible=True demand_wrapper_present=True holder_source=cpu_snapshot_models.clip | PASS |
| D identity | clip_object_id=46737471981200 at reconcile AND Gate D | PASS |
| E | Snapshot created. Restoring Function from memory snapshot. + restore_count=1 success | PASS |
| IDENTITY | deployment_combined_hash=7064c683e2dd141f (≠ e8f269ee…/d679332c551f0cad) | PASS |
| D1 PRIME | prime_ok=true store_entry_persisted=true anchor=7064c683e2dd141f workflow_hash=2e43d4c0… validated=True | PASS |

Restore-side chain (identity-record construction restore, 16:40:31Z):
estore_first_instruction state=EXCLUDED_PLACEHOLDER cpu_bytes=0 meta_params=399
total_params=399 manifest_eligible=True holder_source=cpu_snapshot_models.clip
clip_object_id=46737471981200 manifest_present=True demand_wrapper_present=True.

## The one request (issued, executed remotely, artifact rejected locally)

- Fresh nonce 8828427e-33ad-4843-a657-0b63e1ed4f55, V2_BENCHMARK_RUNS=1.
- **Vehicle defect fixed first (zero-spend):** the cancel-proof lane's
  control-queue wiring passed a LAZY unhydrated modal.Queue handle
  (modal SDK 1.4.3 Queue.from_name) as a emote_gen.aio kwarg, failing
  client-side serialization before submission. Repaired by forcing hydration
  in both resolvers (local_handle_owner._resolve_control_queue_sync sync
  form; modal_transport._resolve_control_queue .aio form), with the
  documented contract preserved (unhydratable -> channel unavailable -> path
  unaffected). Verified: hydration probes (sync + async) OK, 104 transport/
  cancel tests OK, py_compile OK. A stale pre-fix owner daemon was recycled.
- Request evidence (v2_d10_corrected_request.out.txt): modal_input_id=
  in-01M05RQZPJX4HFKFH2P89A83CR:1786900119250-0, emote_python_resume
  (snapshot restore), prompt_executor_invoke_start, full result stream
  returned, local_receive_to_result_return_ms=26590.838,
  [v2.benchmark] persistence drains joined=1.
- **Local rejection:** C8 runtime-shape validation failed: deployed
  cpu_request=12 requested=16; deployed memory_request=32768 requested=49152;
  deployed runtime_shape_fingerprint='f504e296…' requested='7a4753e1…'.
  Cause: the launcher pins COMFYMODAL_V2_CPU_REQUEST=12 /
  COMFYMODAL_V2_MEMORY_MB=32768; the direct benchmark invocation omitted
  them, so the harness planned 16 CPU / 49152 MB against the deployed
  12 CPU / 32768 MB container. Vehicle-environment mismatch — NOT a Phase-D
  gate failure; no artifact written; no rerun permitted.

## Request-only metrics

N/A — the harness aborted before writing run artifacts; nothing fabricated.

## Fixes landed this batch (default-OFF / contract-preserving)

- comfymodal_runtime/local_handle_owner.py — force-hydrate the control
  Queue (blocking form) before caching/passing to the remote generator.
- comfymodal_runtime/modal_transport.py — _resolve_control_queue /
  _direct_fallback_channel async + force-hydrate via .aio; call sites
  awaited.
- Prior Gate-D checkpoint fix (holder resolution) unchanged.

## Artifacts (not overwriting prior D10 evidence)

- 2_d10_deploy_corrected_1.log (v44 deploy) · 2_d10_corrected_identity.out.txt
- 2_d10_corrected_prime.out.txt · 2_d10_corrected_request.out.txt
- 2_d10_applogs_full.txt / 2_d10_corrected_request_applogs.txt
- .deployed_state.json (7064c683e2dd141f) · 2_d10_applist_full.json

## Next (awaiting authorization)

Redeploy is NOT required (v44 snapshot is healthy and fully gated). The next
batch only needs to re-issue the single request with the launcher's resource
pins (COMFYMODAL_V2_CPU_REQUEST=12, COMFYMODAL_V2_MEMORY_MB=32768,
COMFYMODAL_V2_BASELINE_CPU_REQUEST=12,
COMFYMODAL_V2_BASELINE_MEMORY_REQUEST=32768) and a fresh nonce, then run the
Part 11–29 structural/measurement gates. One request only.

---

# Resource-Shape Fix + Final Single Request

*(Appended 2026-08-16 — final authorized request. Prior sections unchanged.)*

## Outcome

**INVALID_REQUEST_STRUCTURE — MODAL_REQUESTS = 1.** The single authorized
true-cold request was issued against the healthy v44 deployment with the
resource pins corrected (CPU 12 / 32768 MB) and a fresh nonce. It executed
remotely, restored from snapshot, and produced the EXACT canonical output SHA
(20b10e1f…) — but the conditioning cache **HIT** (decision=exact_hit,
encode_calls=0) instead of the required miss_stored/encode_calls=1.
Per Part 11 the request is structurally INVALID; no replacement request is
permitted.

## Preflight (zero-spend, before submission)

`
planned_cpu_request=12  planned_memory_request=32768
planned_runtime_shape_fingerprint=f504e296c398bdcb2c4c07e2
deployment_identity=7064c683e2dd141fdd359cc9d5fcd14f7a67a1fc3d27fb1768267c49ff5de0cd
workflow_hash=2e43d4c0ba3b82c0a96edef5decfc861e756718c7adce3ba91559203231c0f77
d1_proof_covers=True
RUNTIME_SHAPE_PREFLIGHT = PASS
`
Transport/cancel contract recheck: 104 OK (hydration fix holds).

## The one request (run v2_2026-08-16_17-18-07)

- Nonce d96c9bee-8f4a-4a21-a27c-589962df3723, V2_BENCHMARK_RUNS=1, exit 0.
- Fresh=YES · restore_count=1 · request_count=1 · D1 store hit (memo=hit,
  registry skipped) · runtime_shape requested==deployed==observed
  (504e296…, 12 CPU / 32768 MB).
- Output: esult.images[0].asset_id = 20b10e1f99831bc758d9df82f43ce0beb1cbc636a740d11a29eb2bffe90e5260
  → OUTPUT_SHA_EXACT = YES.
- **Structural gate FAILURE**: clip_conditioning_cache_lookup
  hit_count=1/miss_count=0; clip_conditioning_cache_decision
  decision=exact_hit key_hash=4089c022… encode_calls=0 entry_count=1
  (second entry miss_not_stored encode_calls=0). Waterfall:
  "Conditioning cache exact_hit lookup=9.805ms | CLIP encode skipped
  (cache hit)". cache_nonce=None in decision metadata despite the nonce
  being present in trace request_origin — the nonce did not reach the
  cache-key context, so the canonical entry stored by the earlier 17:08
  C8-rejected remote execution was hit.
- Consequence: no CLIP hydration (CLIP never demanded), no clean encoder
  forward, no cast-tax observation possible from this request.

## Measured (factual, from the run artifact — reported for evidence only)

`
COMMAND -> RESPONSE:                       20.913s
Command (without scheduling) -> Response:  19.002s
Scheduling time:                           1.911s
restore_total_ms=1695.675 (pre-Python 4.715s + Python 1.702s + entry 899ms)
sampling (actual stage 8) = 4.898s
VAE transition 759.804ms + VAE decode 384.255ms + output encode 231.309ms
+ remote result handoff 2.861s = post-sampling ≈ 4.236s
`
These numbers describe an INVALID (cache-hit) run and are NOT Phase-D
measurements. 12 s budget reconciliation and bottleneck ranking are N/A.

## Vehicle defect to fix before ANY next authorized request

The semantic-neutral --conditioning-cache-nonce did not isolate the
conditioning-cache key remotely: ctx["cache_nonce"] was empty at lookup
(cache_nonce=None in the decision metadata) although the nonce was carried
in equest_origin_info. Root-cause the nonce injection path
(model_preload.py _read_conditioning_cache_nonce → ctx["cache_nonce"]
at 17951/18295 vs the lookup path actually executed) locally, add a
nonce-isolation regression test, and only then issue a new single request.

## Artifacts

- 2_d10_final_request.out.txt (request stdout incl. waterfall/footer)
- 2_d10_shape_preflight.py result (RUNTIME_SHAPE_PREFLIGHT = PASS)
- run dir comfymodal-data\benchmarks\runs\v2_2026-08-16_17-18-07\run_0.json
- transport hydration fix + 104 OK (prior batch, unchanged)

---

# Nonce Isolation Root Cause + Repair

*(Appended 2026-08-16 — zero-spend local investigation. Prior sections unchanged.)*

## Root cause

**ROOT_CAUSE_SIDE = LOCAL_CLIENT (vehicle mis-targeting).**

The D10 "final" request was served by the **legacy default app**
stable-modal-comfy-v2-shadow (image im-Z3hBG3elYnLtnl8O93ojIA, deployed
2026-08-13), NOT by v44 stable-modal-comfy-v2-restore-only-shadow (image
im-Pm1Zx4yf6Qbv8kNS6uHEHD, deployment 7064c683e2dd141f).

- The direct benchmark invocation set COMFYMODAL_V2_RESTORE_ONLY_APP_NAME
  but NOT COMFYMODAL_V2_APP_NAME.  The transport resolves the handle by
  COMFYMODAL_V2_APP_NAME with the default stable-modal-comfy-v2-shadow
  (modal_transport.py:940) — so the request silently targeted the OLD app.
  The standing vehicle (un_v2_single.bat:6) pins
  COMFYMODAL_V2_APP_NAME=stable-modal-comfy-v2-restore-only-shadow; the
  direct python tools\benchmark_v2_direct.py invocation bypassed it.
- The old deployment's baked runtime predates the D6 nonce key isolation, so
  its demand-time cache-context builder never reads the nonce:
  ctx["cache_nonce"] stayed unset, the canonical (nonce-less) key was used,
  and the warm canonical entry (stored by the 17:08 C8-rejected run, which
  also went to the same old app) served decision=exact_hit, encode_calls=0,
  cache_nonce=None.
- The current tree's demand path is CORRECT: _build_clip_conditioning_cache_
  context reads _read_conditioning_cache_nonce(trace) and sets
  ctx["cache_nonce"] when the trace carries equest_origin_info
  (proven locally: DEMAND_PATH_NONCE_PROPAGATES = PASS; absent nonce
  preserves legacy byte-identical keys).  v44 bakes the current tree, so the
  remote runtime was never at fault.

## Evidence (deployed-container identity, run v2_2026-08-16_17-18-07)

`
identity.app_name  = stable-modal-comfy-v2-shadow     # served app (OLD)
identity.image_id  = im-Z3hBG3elYnLtnl8O93ojIA        # served image (OLD)
handle_lookup_app_name = stable-modal-comfy-v2-shadow # local transport target
v44 construction   = image im-Pm1Zx4yf6Qbv8kNS6uHEHD, hash 7064c683e2dd141f
trace.metadata.request_origin_info.conditioning_cache_nonce = d96c9bee-…
cache decision     = exact_hit, encode_calls=0, cache_nonce=None
`

NONCE_LAST_PRESENT_AT = served trace metadata equest_origin_info
NONCE_FIRST_MISSING_AT = served (OLD) container's cache-context builder
(baked code predates _read_conditioning_cache_nonce; ctx never got the
nonce → canonical key)

## Fix (landed, vehicle-side, fail-closed, request-scoped)

	ools/benchmark_v2_direct.py:

1. _resolve_nonce_target_app() — when a conditioning-cache nonce is active:
   - nonce inactive -> '' (no-op; legacy behavior unchanged)
   - env app unset + D1-primed identity -> resolve COMFYMODAL_V2_APP_NAME
     from .deployed_state.json app_name (never the legacy default)
   - env app == primed -> OK
   - env app != primed -> **raise** (fail closed: a nonce measurement against
     the wrong deployment is invalid)
   - no primed identity -> **raise** (fail closed)
2. Wired into _run_one at the nonce injection site — every nonce-carrying
   request now targets the D1-primed deployment or aborts before submission.

The fix requires NO remote code change: v44 already bakes the correct
plumbing. **V44_REUSABLE_AFTER_FIX = YES — no redeploy needed.**

## Regression tests (tests/test_v2_conditioning_cache_nonce.py, +9)

- A no-nonce legacy unchanged (key bytes identical)
- B nonce A first lookup miss / D nonce B distinct / C same-nonce hit
  permitted / H key hash differs A vs B
- E nonce from request_origin reaches demand ctx (the missing coverage)
- F telemetry (key summary) carries the exact nonce
- G semantic inputs unchanged (existing suite)
- I request-scoped, no global sticky nonce
- Vehicle guard: unset app resolves primed identity; mismatched app fails
  closed; no primed identity fails closed; nonce inactive no-op
- Prior-failure reproduction: trace WITHOUT request_origin_info reproduces the
  D10 signature (canonical key, no nonce); trace WITH it propagates (PASS)

## Verification

- test_v2_conditioning_cache_nonce 23 OK; conditioning_exact_hit_breakdown +
  conditioning_prefetch + unique_prompt_suffix + D1 (stale/registry/dispatch/
  store/local) + D6 profile + phase-d telemetry 97 OK (1 skip);
  D1 isolation + local dispatch + plan/deployment proof + transport boundaries
  + remote cancel 109 OK; py_compile OK. No unexplained failures.
- Local probe: DEMAND_PATH_NONCE_PROPAGATES = PASS,
  LEGACY_ABSENT_NONCE = PASS (current tree behavior = v44 baked behavior).

## Next (NOT executed — awaiting authorization)

ONE request, NO redeploy, against the healthy D1-primed v44:

`
set COMFYMODAL_V2_APP_NAME=stable-modal-comfy-v2-restore-only-shadow
set COMFYMODAL_V2_CLASS_NAME=ModalRuntimeEntrypointV2
set COMFYMODAL_V2_CPU_REQUEST=12
set COMFYMODAL_V2_MEMORY_MB=32768
set COMFYMODAL_V2_BASELINE_CPU_REQUEST=12
set COMFYMODAL_V2_BASELINE_MEMORY_REQUEST=32768
set V2_BENCHMARK_RUNS=1
python tools\benchmark_v2_direct.py --conditioning-cache-nonce <FRESH_UUID>
`

The new guard enforces the primed target; the demand path propagates the
nonce; expectation: miss_stored, encode_calls=1, CLIP hydration exercised,
cache_nonce=<UUID> in decision metadata. One request only.

---

## Canonical Batch-File Deploy + Run (D11) — VALID_PHASE_D_INTEGRATION

2026-08-16. Exactly ONE deploy (`deploy_and_run_v2_single.bat`) and exactly
ONE request (`run_v2_single.bat --conditioning-cache-nonce <fresh uuid>`),
both through the canonical `.bat` wrappers under the D10 profile
(`V2_D10_INTEGRATION_VALIDATION=1`). Direct python benchmark: NEVER used.
Logs preserved: `v2_d11_deploy_1.log`, `v2_d11_request_1.log`; deployment
state: `.deployed_state.json`; persisted run:
`comfymodal-data/benchmarks/runs/v2_2026-08-16_18-18-11/`.

### Fail-closed instrumentation added (this batch)

1. `tools/record_deployment_identity.py` — the deploy identity record now
   also persists the deployed runtime shape (computed under the deploy-batch
   env: CPU/MEM, baselines, fingerprint, TBASE/O0) + `class_name`, with
   `runtime_shape_recorded` flag; shape failures never fail the record
   (the run preflight fails closed instead).
2. `tools/benchmark_v2_direct.py` — new `--verify-run-preflight` CLI +
   `_run_run_preflight_cli()`: local-only (zero Modal calls, zero spend)
   gate run BEFORE dispatch. Checks state identity/app/class vs request env
   (`TARGET_MATCH`), CPU/MEM/baseline parity, planned vs deployed runtime-shape
   fingerprint, D1 store coverage (`_registry_proof_store_covers` mirroring
   `_prime_registry_proof` exactly), RUN_COUNT==1 under nonce, and nonce
   target-app resolution via `_resolve_nonce_target_app()` (D10 failure class:
   silent legacy-app targeting).
3. `run_v2_single.bat` — default branch now runs the preflight and aborts
   with exit 1 BEFORE any Modal submission when the preflight fails.

### Deploy results (gates A1/A2/C)

- V1 app exists -> deploy bat took the single-deploy V1 branch; exactly one
  V2 deploy (`App deployed in 86.629s`), `=== V2 deploy verified OK ===` at
  deploy log line 489; bat exit 0.
- D10 profile enforced at deploy: `profile=d10_integration_validation`,
  `clip_cold_forensics_sync_cuda=0`, `d10_integration_validation=1`.
- NEW identity recorded: `deployment_combined_hash=2305b0b3bbdf3fbe…`
  (v44 `7064c683e2dd141f` quarantined/replaced), generation
  `68ffe7ef8d914c9a`, comfyui `0.24.0` (commit f49bdb65), `comfyui_core_match=1`,
  manifest classes 2399.
- Runtime shape recorded in state: fingerprint `f504e296c398bdcb2c4c07e2`
  (== the planned pre-deploy fingerprint), cpu 12 / mem 32768, baselines
  12/32768, TBASE, O0, class `ModalRuntimeEntrypointV2`.
- Registry-proof priming via deploy bat: `prime_ok=true`,
  `store_entry_persisted=true`, `registry_load_ms=22064.6`.

### Request results (gates B/D/E)

- Run batch preflight: `FINAL_REQUEST_PREFLIGHT=PASS` with
  TARGET_APP/TARGET_CLASS matches, `TARGET_DEPLOYMENT=2305b0b3bbdf3fbe…`,
  CPU/MEM/baseline parity, `RUNTIME_FINGERPRINT=f504e296c398bdcb2c4c07e2 ==
  deployed f504e296c398bdcb2c4c07e2`, `D1_PROOF_COVERS=true`, `RUN_COUNT=1`;
  bat exit 0 (no rerun, no retry).
- Nonce `31c0eb09-0178-4e59-8691-ea2f87d012bb` active:
  `[v2.conditioning_cache_nonce]` propagated; request goal achieved:
  conditioning cache `decision=miss_stored` (lookup 1.03 ms),
  `CLIP encode (1 calls)` (7.473s incl. loader), CLIP cold path exercised
  with `clip_object_id=47094363197456` object-id parity and
  `holder_source=direct` on every CLIP state checkpoint.
- UNET: `cpu_snapshot_unet_mode=reuse`, `unet_prepare=6961ms`,
  preload completion before demand (`unet_work_completed_before_demand_ms
  =2529.295`), `_execution_unet_gate=True`.
- Freshness: `Fresh: YES`, `restore_count=1`, `request_count=1`, instance
  `cd685f3ceb4a4105a9d73d2ee43b69ed` (GCP/us-east4, RTX PRO 6000, 12 CPU/
  32768 MiB, fingerprint match in identity).
- Output: `[v2.png_output]` bytes=3129718,
  `sha=20b10e1f99831bc758d9df82f43ce0beb1cbc636a740d11a29eb2bffe90e5260`
  (exact gate match). Footer `=== Single V2 benchmark completed ===`,
  command-to-response 32.291s.
- Reconciliation: `STATUS OK` (6.771 ms), host-reconciled waterfall.

### Verification

- Focused suites green: nonce 23 OK; D1 (registry-proof store, stale
  identity, store isolation, local dispatch, dispatch hash) + D6/D10 profile
  + transport cancellation + persistent handle 55+ OK; py_compile OK.
- Pre-existing (NOT caused by this batch; deliberate D-series bat contract
  drift, tracked test never updated): 5 failures in
  `tests/test_v2_batch_profiles.py` (RUNS=10 default, MEMORY_MB=32768,
  restore-only app name, host_ab branch first-match) — unchanged
  here; flagged for a future test-contract update.

MODAL_DEPLOYS=1, MODAL_REQUESTS=1, DIRECT_PYTHON_BENCHMARK_USED=NO,
NONCE=truemiss, ENCODE_CALLS=1, IDENTITY=2305b0b3bbdf3fbe (new),
PRIME_OK=true, COVERS=true, PREFLIGHT=PASS, REQUESTS_STOPPED=1.
