# RA2 Snapshot / Restore Truth and Repair Report

## 1. Executive verdict

RA2 non-deployment implementation work is complete. The current source now
provides a bounded, fail-closed Golden snapshot proof, authoritative
custom-node generation checking, restore-stage classification, and guarded
reload decisions. A real fail-open defect was found and repaired: restore could
trust a stale generation token restored in memory and skip synchronization even
when the mounted custom-node Volume had changed.

RA2 is **not accepted**. The final source was deployed and three serial
observations were collected on the isolated app
`batch-ra2-publisher-skip-check`. All three prove true-cold restore, durability,
reopen ordering, and zero seriality violations, but none matches the authorized
current profile output SHA, so none is an accepted RA2 observation.

## 2. Intended Golden snapshot manifest from source

The Golden entrypoint is `ModalRuntimeEntrypoint.startup`, decorated with
`_modal.enter(snap=_resolve_enable_memory_snapshot())` in
`comfymodal_runtime/modal_app.py`. The Golden serial branch is selected by
`_golden_serial_profile_active()`.

At the intended CPU snapshot boundary the process may retain:

- the initialized Python interpreter and imported runtime modules;
- ComfyUI/custom-node registries;
- immutable runtime configuration;
- deployment/source/generation identity;
- validation and proof metadata;
- intentionally lightweight static workflow/seed metadata;
- quiescent coordinator objects and other selected diagnostic surfaces.

The Golden branch calls `_clear_cpu_snapshot_state_for_golden()` before taking
its proof. It clears CPU snapshot model objects, active flags, UNET/CLIP
storage registries, retained eviction models, eviction metadata, and markers.

The following are forbidden by the Golden contract and proof:

- CLIP, UNET, or VAE weights/tensors;
- model patchers and retained model references;
- QD owners and pinned H2D buffers;
- open payload readers;
- preload/model-load workers and unresolved futures;
- active request IDs, output state, or mutable request caches;
- CUDA state in the CPU snapshot path.

The proof surfaces are intentionally selected from the current runtime:
`_legacy_api`, `_preload_bridge`, `bootstrap`, snapshot slots, storage
registries, and preload/runtime coordinators.

Evidence: `RA1-3set.md:511-647`,
`comfymodal_runtime/modal_app.py:9457-9551,10104-10126`.

## 3. Physical capture-time memory composition

The implementation records bounded `/proc/self/status`,
`/proc/self/smaps_rollup`, `/proc/self/maps`, cgroup memory, module, thread,
file-descriptor, and selected-root information through
`comfymodal_runtime/snapshot_build_manifest.py`.

The implementation correctly labels these as resident/mapping telemetry, not
Modal serialized snapshot bytes. Modal serialized byte count is unavailable.
No fresh RA2 deployment was authorized in this pass, so current capture
values and a capture RSS median are **unknown**.

The available fields distinguish, when the platform exposes them:

- RSS/PSS;
- anonymous, private, and shared pages;
- virtual mapping totals;
- anonymous versus file-backed mappings;
- bounded dominant mapped paths;
- cgroup current/peak memory.

Historical R0 reports must not be substituted for a current RA2 capture
cohort.

Evidence: `comfymodal_runtime/snapshot_build_manifest.py:73-212,433-453`,
`comfymodal_runtime/restore_state_probe.py:44-117`,
`R0_GOLDEN_OPERATIONS_HARDENING_REPORT.md:15-18`.

## 4. Hidden/nested reference audit

The selected-root census is bounded and diagnostic-only. It traverses only
explicitly supplied roots, registries, and coordinators using fixed limits:

- maximum depth: 2;
- maximum visited nodes: 128;
- maximum children per container: 32;
- maximum tensor records: 32;
- maximum root inputs per category: 32.

It records type counts, nested tensor-like references, bounded tensor device,
dtype, shape, numel, and deduplicated storage bytes, plus model-patcher-like
references. It does not use `gc.get_referents()`, copy tensors, import CUDA,
invoke arbitrary properties, or serialize object contents.

Hardening added during RA2:

- subclassed top-level list/tuple inputs are rejected before iteration;
- custom `__dict__` descriptors are not invoked;
- all three bounded root categories are traversed rather than silently
  discarding categories after the first 32 total roots;
- input and traversal truncation/fail-closed reasons are surfaced.

Limitations remain explicit: reaching the depth limit does not mean the full
object graph was inspected; `__slots__`, dictionary keys, malformed containers,
and capped fail-closed reason categories can remain unexamined. This is not a
universe-wide heap or Modal serializer proof.

Evidence: `comfymodal_runtime/snapshot_build_manifest.py:218-450`,
`tests/test_v2_snapshot_manifest_hygiene_extensions.py:209-282`,
`comfymodal_runtime/golden_serial.py:2211-2390`.

## 5. Proof of model-free capture

The Golden pre-capture path is:

```text
startup(snap=True)
  -> clear CPU snapshot state
  -> inventory selected surfaces
  -> close snapshot build pools
  -> passive quiescence proof
  -> runtime-state generation baseline
  -> optional diagnostic manifest/hygiene
  -> bounded Golden content proof
  -> startup callback return/ready
  -> Modal capture
```

`_run_golden_snapshot_content_proof()` requires a positive surface count and
zero values for:

`tensor_count`, `parameter_bytes`, `model_patcher_count`, `qd_owner_count`,
`open_payload_reader_count`, `preload_worker_count`, and `future_count`.

Any proof failure raises before the ready/return marker. Passive mode does not
stop workers, flush persistence, or mutate cache state. Allocator hygiene is
optional, disabled by default, and nonfatal.

The source proves the selected bounded contract, not every object Modal might
serialize. Because no new RA2 capture was performed, a live model-free proof is
not claimed here.

Evidence: `comfymodal_runtime/modal_app.py:9553-9703,10668-10789`,
`comfymodal_runtime/snapshot_capture_hygiene.py:211-308`,
`comfymodal_runtime/golden_serial.py:2211-2390`.

## 6. Current restore call graph

The application-visible restore path is:

```text
Modal restore entry
  -> ModalRuntimeEntrypoint._configure_runtime
  -> restore callback wiring
  -> RuntimeBootstrap.restore
```

`RuntimeBootstrap.restore()` currently runs:

1. `restore_gpu_state` — restore in-process GPU state.
2. `initialize_cuda` — initialize/validate CUDA after restore.
3. Sage identity/policy — validate snapshot identity and perform fresh Golden
   selection when required after CUDA initialization.
4. Runtime-state Volume generation/manifest guard — skip only on exact match;
   otherwise reload.
5. Models Volume generation guard — skip only on exact match; otherwise reload.
6. Custom-node identity/guard — read the freshly reloaded mounted generation
   record and skip full synchronization only for a trusted exact match.
7. Generation observation after fallback synchronization.
8. Snapshot execution seed hydration, or honest minimal seed reconstruction.
9. Restore completion and request/preload preparation.

The restore method itself is lifecycle-only. Request-specific workflow, model,
prompt, sampler, and output decisions arrive later through
`run_golden_serial_stream`.

Evidence: `comfymodal_runtime/runtime_bootstrap.py:1984-2751`,
`comfymodal_runtime/modal_app.py:9043-9474,11289-11629,20988`.

## 7. Current restore timing decomposition

Existing instrumentation records the following restore stages and decisions:

- remote Python resume and method entry markers where available;
- restore GPU state;
- CUDA initialization;
- Sage identity read/verification/policy;
- runtime-state local guard and optional Volume reload;
- models local guard and optional Volume reload;
- custom-node identity check and optional synchronization;
- generation observation;
- seed read/hydration or minimal reconstruction;
- host resource snapshot and restore completion.

The current source also emits an additive restore decomposition when its
diagnostic flag is enabled. CPU monotonic enclosing timing is authoritative;
nested diagnostics must not be summed as independent wall time.

No fresh RA2 run was authorized, so the following required RA2 values are
unknown:

- restore mean, median, min, max, range, sample SD, and CV;
- current restore wall from remote Python resume through request-ready;
- current residual against the 3,000 ms target.

Prior lineage values recorded in the execution ledger are context only, not
RA2 acceptance evidence: R0 representative `restore_total_ms=845.829` and
`snapshot_restore_ms=826.47`; RA1 representative `restore_total_ms=495.887`
and `snapshot_restore_ms=473.98`.

Evidence: `.slim/deepwork/ra1-ra2-ra3-execution.md:66-114`,
`comfymodal_runtime/runtime_bootstrap.py:2673-2750`.

## 8. Restored-versus-reconstructed table

| State or work | Classification | Current proof |
|---|---|---|
| GPU/process snapshot state | `RESTORED_THEN_VALIDATED` | Restore callback is invoked and classified. |
| CUDA context | `RESTORED_THEN_MUTATED` / validated | CUDA is initialized after restore. |
| Sage patch identity | `RESTORED_THEN_VALIDATED` when sentinel matches | Identity is checked; Golden may freshly select after CUDA. |
| Runtime-state Volume | `RESTORED_UNCHANGED` on exact generation+manifest match; otherwise `RELOADED_FROM_VOLUME` | Fail-closed local guard. |
| Models Volume | `RESTORED_UNCHANGED` on exact generation match; otherwise `RELOADED_FROM_VOLUME` | Fail-closed local guard. |
| Custom nodes | `RESTORED_UNCHANGED` on trusted mounted exact match; otherwise synchronized/reloaded | Fresh authoritative mounted record. |
| Custom-node generation | `RESTORED_THEN_VALIDATED`; refreshed after fallback sync | Generation observer and persisted identity. |
| Snapshot execution seed | `RESTORED_UNCHANGED` when publisher payload hydrates; otherwise `RECONSTRUCTED` | Minimal schema-v2 fallback. |
| Request workflow/model/output state | `INTENTIONALLY_NEW_AFTER_RESTORE` | Restore never consumes a global current plan. |
| Golden sampler/request setup | `INTENTIONALLY_NEW_AFTER_RESTORE` | Request-specific serial runner. |

## 9. Synchronization and runtime-state analysis

Runtime-state and models reloads are guarded by construction-time generation
and content identity. Missing, corrupt, stale, or unverifiable state reloads;
only an exact local match skips the callback.

Custom-node synchronization required a repair. Before RA2 remediation,
`_resolve_custom_nodes_generation()` preferred the restored API field
`_custom_nodes_generation_seen`. That field can be stale after a Volume change.
The restore reader now:

1. reloads the custom-node Volume;
2. reads only the mounted persisted generation record with
   `authoritative_only=True`;
3. validates generation, schema, source, and deployment identity;
4. skips the expensive full sync only on a trusted exact match;
5. falls back to synchronization on uncertainty or mismatch.

The restore-scoped epoch/one-shot cache reuses this authoritative read for a
mismatch fallback, avoiding a duplicate Volume reload. It is disabled during
construction and ordinary requests, reset at restore start, consumed once, and
cleared in `finally`.

No fixed sleep or `gc.collect()` exists inside `RuntimeBootstrap.restore()`.
The restore decomposition records GC as `0.0` because restore does not invoke
it.

## 10. Application-owned waste discovered

Historical evidence showed custom-node synchronization could dominate restore,
including a historical `sync_custom_nodes_ms` of approximately 2,007.950 ms.
That is not current RA2 evidence and cannot be assumed to remain true.

The current implementation eliminates the unsafe identity shortcut and avoids
the duplicate reload on mismatch fallback. A remaining remote measurement is
required to determine whether the single authoritative Volume reload or any
other application-owned stage materially exceeds the target.

No additional optimization was made merely because a stage might be slow.

## 11. Changes implemented

- Added authoritative-only custom-node generation resolution in `comfyapp.py`.
- Made the restore identity reader reload the mounted custom-node Volume before
  deciding whether full synchronization may be skipped.
- Added an epoch-bound one-shot identity handoff to avoid duplicate fallback
  reloads.
- Hardened selected-root census traversal and nested tensor/model-patcher
  detection in `snapshot_build_manifest.py`.
- Added focused stale-identity, exact-match, mismatch, duplicate-reload,
  hostile-input, nested-reference, truncation, and CPU-only regressions.
- Preserved non-Golden behavior and fail-closed fallback paths.
- Moved custom-node publication ownership to the shared resource-scoped
  `comfyui-custom-nodes-publisher` authority with receipt-first exact skips and
  receipt-only generation recovery.

Changed implementation/test paths include:

`comfyapp.py`, `comfymodal_runtime/modal_app.py`,
`comfymodal_runtime/runtime_bootstrap.py`,
`comfymodal_runtime/snapshot_build_manifest.py`,
`comfymodal_runtime/golden_serial.py`,
`config/v2/profiles/golden_p1.toml`,
`tests/test_modal_app_identity.py`,
`tests/test_v2_snapshot_manifest_hygiene_extensions.py`, and
`tests/test_p1_golden_serial.py`.

## 12. Tests and exact counts

Final focused validation:

```text
python -m pytest tests/test_v2_snapshot_manifest_hygiene_extensions.py \
  tests/test_modal_app_identity.py \
  -k "ResolveCustomNodesGeneration or CustomNodeRestoreExactSkipAuthority or ModalCustomNodeRestoreReloadHandoff or selected_root_census" -q
21 passed, 149 deselected

python -m unittest tests.test_runtime_state_reload_guard
Ran 32 tests
OK

python -m compileall -q comfymodal_runtime comfyapp.py
pass

git diff --check
pass
```

Additional implementation-lane validation was recorded as:

- identity tests: 11 passed;
- census tests: 4 passed;
- snapshot manifest tests: 24 passed;
- Golden proof tests: 10 passed;
- P1/P2 Golden suites: 127 passed, 1 skipped;
- compilation and diff checks: passed.

The broader local environment remains noisy because installed `diffusers`
cannot import `cached_download` from the installed `huggingface_hub`, and
`cache_dit` is unavailable. The combined diagnostic-timing suite therefore
had unrelated environment/suite-drift failures; that result is retained and
not represented as RA2 acceptance.

## 13. Remote attempts and deployment boundary

Remote work existed in the pre-existing RA2 artifact ledger. Those attempts
are retained but none count as accepted RA2 observations because they preceded
the final remediation and/or failed source, identity, output, or lifecycle
gates.

Relevant retained attempt groups are:

| Group | Evidence paths |
|---|---|
| Profile dry runs | `artifacts/ra2_profile_dry_run_20260829.log`, `artifacts/ra2_profile_dry_run_after_probe_20260829.log` |
| Deploy attempts | `artifacts/ra2_remote_deploy_20260829.log`, `ra2_remote_deploy_quick_20260829.log`, `ra2_remote_deploy_retry_2_20260829.log`, `ra2_remote_deploy_retry_after_sage_20260829.log`, `ra2_remote_deploy_sage_selector_20260829.log` |
| Redeploy attempts | `artifacts/ra2_remote_redeploy_cache_fix_20260829.log`, `ra2_remote_redeploy_final_source_20260829.log`, `ra2_remote_redeploy_frozen_20260829.log`, `ra2_remote_redeploy_stable_source_20260829.log` |
| Source probes | `artifacts/ra2_remote_source_probe_20260829.log`, `ra2_remote_source_probe_after_cache_fix_20260829.log`, `ra2_remote_source_probe_after_quick_deploy_20260829.log`, `ra2_remote_source_probe_retry_2_20260829.log`, `ra2_remote_source_probe_sage_selector_20260829.log` |
| Doctor checks | `artifacts/ra2_remote_doctor_after_deploy_20260829.log`, `ra2_remote_doctor_after_probe_20260829.log`, `ra2_remote_doctor_after_quick_deploy_20260829.log`, `ra2_remote_doctor_retry_2_20260829.log`, `ra2_remote_doctor_sage_selector_20260829.log` |
| Status checks | `artifacts/ra2_remote_status_before_20260829.log`, `ra2_remote_status_after_deploy_20260829.log`, `ra2_remote_status_after_probe_20260829.log`, `ra2_remote_status_after_quick_deploy_20260829.log`, `ra2_remote_status_after_timeout_20260829.log`, `ra2_remote_status_retry_2_20260829.log`, `ra2_remote_status_sage_selector_20260829.log` |
| Requests | `artifacts/ra2_remote_attempt_001_20260829.log`, `artifacts/ra2_remote_attempt_sage_001_20260829.log` |
| Lock/abort handling | `artifacts/ra2_remote_lock_after_timeout_20260829.log`, `artifacts/ra2_remote_lock_force_release_20260829.log`, `artifacts/ra2_remote_lock_force_release_after_abort_20260829.log` |

The current user-authorized validation pass used the supported Golden commands.
The shared publisher was bootstrapped once, then the first consumer deployment
published generation `4a42bb4c…`; a second unchanged-content consumer
deployment returned `decision=skip_exact` without publisher bootstrap. Its
source probe was `PASS / MATCH` and doctor was `OK`.

The final RA2 deployment on `batch-ra2-restore-truth` also returned
`decision=skip_exact`, with source probe `PASS / MATCH` and doctor `OK`.
The user then selected the new isolated consumer app for requests. The three
serial request artifacts are:

| Request | Request ID | Restore (ms) | Output SHA | SHA match | Structural state |
|---|---|---:|---|---|---|
| `cohort_2026-08-30_18-07-21_aafe33` | `golden-p1-0-c70556a11b31` | 1,586.070 | `bfb36000…` | no | true-cold, durable, reopened, seriality clean |
| `cohort_2026-08-30_18-08-36_262ad0` | `golden-p1-0-88c6ece5a992` | 780.863 | `bfb36000…` | no | true-cold, durable, reopened, seriality clean |
| `cohort_2026-08-30_18-09-15_e04654` | `golden-p1-0-955d5e2a17f7` | 1,422.522 | `bfb36000…` | no | true-cold, durable, reopened, seriality clean |

Full raw artifacts are retained under
`artifacts/phase_p1_serial_golden_v1/` and the corresponding `.v2ctl/runs/`
manifests.

## 14. Three accepted observations

None. `VALID_RUNS=0` under the exact output-SHA acceptance contract. The three
new artifacts are retained as structurally valid but output-mismatching
observations.

The earlier invalid/partial attempts are not confirmations. Three new eligible
serial observations remain required after deployment of this final source.

## 15. Raw evidence paths

- `RA1-3set.md:437-886`
- `.slim/deepwork/ra1-ra2-ra3-execution.md:66-114`
- `RA1_SAMPLER_NEXTDIT_DECOMPOSITION_AND_REPAIR_REPORT.md`
- `R0_GOLDEN_OPERATIONS_HARDENING_REPORT.md`
- `E37_CLEAN_LANE_ALGORITHM_RECOVERY_REPORT.md`
- `E38A_SNAPSHOT_REACHABILITY_AND_CLIP_EXCLUSION_AUDIT.md`
- `K1_GOLDEN_RESTORE_QUIESCENCE_SEAM_RECOVERY_REPORT.md`
- `comfymodal_runtime/modal_app.py`
- `comfymodal_runtime/runtime_bootstrap.py`
- `comfymodal_runtime/snapshot_build_manifest.py`
- `comfymodal_runtime/snapshot_capture_hygiene.py`
- `comfymodal_runtime/restore_state_probe.py`
- `comfymodal_runtime/golden_serial.py`
- `tests/test_modal_app_identity.py`
- `tests/test_v2_snapshot_manifest_hygiene_extensions.py`
- `tests/test_runtime_state_reload_guard.py`
- `artifacts/ra2_*.log`

## 16. Remaining unavoidable/unknown behavior

- Modal serialized snapshot byte count is unavailable; RSS/PSS/mappings are
  proxies only.
- The selected census cannot prove absence outside its bounded roots/depth.
- Current remote Python-resume-to-request-ready timing is available in the three
  retained request artifacts.
- The three restore values are 1,586.070 ms, 780.863 ms, and 1,422.522 ms;
  median 1,422.522 ms, all below the 3,000 ms restore-stage target. They are
  not an accepted cohort because output SHA matching failed.
- The current tree and historical R0/RA1 report contain different configured
  output SHA values (`8a9244...` in the current `golden_p1` profile versus
  `454dbd...` in older R0/RA1 evidence). The final deployment acceptance
  contract must be resolved before counting observations.
- Modal scheduling/host restoration behavior remains outside application-owned
  timing and requires fresh raw evidence for attribution.
- RA3 remains gated on `RA2_ACCEPTED=YES` and must not start.

RA2_IMPLEMENTATION_COMPLETE=YES
RA2_ACCEPTED=NO
MODEL_FREE_SNAPSHOT_PROVED=NO
CAPTURE_RSS_MEDIAN_BYTES=UNKNOWN
SERIALIZED_SNAPSHOT_BYTES=UNKNOWN
RESTORE_MEDIAN_MS=1422.522
RESTORE_TARGET_LE_3000MS=YES_STRUCTURAL_ONLY
DOMINANT_RESTORE_STAGE=REMOTE_BACKEND_STARTUP_OR_PLATFORM_RESUME
EXPECTED_SHA_MATCH=NO
VALID_RUNS=0
REPORT=RA2_SNAPSHOT_RESTORE_TRUTH_AND_REPAIR_REPORT.md
