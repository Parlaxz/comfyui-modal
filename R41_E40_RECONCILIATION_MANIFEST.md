# R41 ↔ E40 Reconciliation Manifest

Batch: **R41** · Date: 2026-08-22 · Branch: `r41-deterministic-golden-pipeline` (base: E39 `0c59f46`)
Companion to `R41_DETERMINISTIC_GOLDEN_QD4_PIPELINE_REPORT.md`.

## 0. Headline

**R41 modified ZERO shared files.** Every R41 artifact is new: `comfymodal_runtime/golden/**`, `tests/golden/**`, `tools/golden_local_benchmark.py`, this manifest, the R41 report, and `R41_LOCAL_BENCHMARK_EVIDENCE.json`. There is nothing in R41 that can textually conflict with E40's canonical rewrite of `comfyapp.py` or any existing module. Integration is achieved through three documented hunks plus optional wiring, all listed below.

---

## 1. Shared-file modifications by R41

| File | Modified? | Notes |
|---|---|---|
| `comfyapp.py` | **NO** | byte-untouched on this branch |
| `comfymodal_runtime/clip_qd_reader.py` | NO | audited only; superseded for Golden roles but retained as production fallback until reconciliation |
| `comfymodal_runtime/model_preload.py` | NO | ownership contract mirrored, not modified |
| `comfymodal_runtime/empty_cache_bypass.py` | NO | policy consumer documented (M-06) |
| `config/v2/profiles/*` | NO | new profile is an E40-side addition (M-07) |

Expected E40 conflicts from R41: **none** (no overlapping edits).

---

## 2. New modules and their public interfaces

### `comfymodal_runtime/golden/contracts.py` (interface freeze v1)
- Enums: `ModelRole`, `ResourceDomain`, `LifecyclePhase`, `GoldenEvent`, `RuntimeStatus`, `DegradedReason`, `DestinationKind`, `OwnershipState`, `JoinDecision`, `QDDropReason`.
- Exceptions: `GoldenError`, `GoldenQDFailure` (+`SourceReadError`, `ShortReadError`, `WorkerCrashedError`, `CoverageReconciliationError`, `BindError`), `ForbiddenOverlapError`, `QuiescenceViolationError`, `ImmutableStateAbsentError`.
- Static plan: `TensorMapEntry`, `SafetensorsLayout`, `CopySegment`, `BlockPlan`, `QDRangePlan.build(layout, block_bytes, buffer_mode="contiguous"|"per_tensor")`, `RoleManifest`, `DestinationPlan.validate(manifest)`.
- Contracts: `ConditioningContract` / `DEFAULT_CONDITIONING_CONTRACT`; `EXACT_OUTPUT_SHA`; `DEFAULT_BLOCK_BYTES`; `GOLDEN_QUEUE_DEPTH`.
- Seams: `TransferBackend`, `AsyncCompletion`, `LedgerEventSink`, `InMemoryLedgerSink`, `NULL_LEDGER_SINK`.
- Telemetry: `GoldenQDTelemetry.to_dict()`; `LoadResult`; `DegradationRecord`.

### `comfymodal_runtime/golden/qd_engine.py`
- `parse_safetensors_header(path) -> SafetensorsLayout`
- `QD4EngineConfig(queue_depth=4, staging_slots=8, occupancy_sample_ms=1.0, enable_occupancy_sampler=True, slot_wait_timeout_s=120, overall_timeout_s=600)`
- `CudaTransferBackend(device)` / `CpuCopyBackend(copy_latency_s=None)`
- `GoldenQD4Loader(config, backend).load(manifest, destination, ledger_sink=None, label=...) -> LoadResult`
  - raises typed `GoldenQDFailure` subclasses with `.telemetry` attached
  - ledger events: `<label>_submit_start`, `<label>_source_first_completion`, `<label>_source_last_completion`, `<label>_stats`, `<label>_device_ready`

### `comfymodal_runtime/golden/model_owner.py`
- `GoldenModelOwner(role, identity_hash)`: `publish_device_ready(payload)` / `publish_failure(exc)` / `mark_bind_ready()` / `mark_published()` / `join(timeout_s) -> JoinDecision` / `take(reason) -> OwnerHandle` / `release()`; `state`, `payload`, `take_ledger`.
- `GoldenOwnerRegistry`: `register` (one live owner per role), `get`, `clear_role`, `join_or_adopt(role, timeout_s) -> (JoinDecision, Optional[owner])`.

### `comfymodal_runtime/golden/resource_scheduler.py`
- Activity labels: `ACT_CLIP_QD_SOURCE`, `ACT_CLIP_QD_H2D`, `ACT_CHEAP_REQUEST_SETUP`, `ACT_CLIP_FORWARD`, `ACT_CLIP_GPU_CRITICAL`, `ACT_UNET_METADATA_PREP`, `ACT_UNET_BULK_SOURCE`, `ACT_UNET_H2D`, `ACT_UNET_GPU_COMMIT`, `ACT_SAMPLING`, `ACT_VAE_QD`, `ACT_VAE_GPU_MUTATION`, `ACT_OUTPUT_DELIVERY`.
- `OverlapMatrix.check(active_labels, request_label) -> OverlapDecision` / `.require(...)` (raises `ForbiddenOverlapError`).
- `GoldenResourceScheduler(ledger_sink=None)`: `begin_minimal_restore()`, `transition(GoldenEvent) -> LifecyclePhase`, `acquire(label, domains) -> Grant`, `release(grant)`, `active_labels()`, `snapshot_state()`, flags `unet_prepare_allowed` / `clip_storage_released` / `vae_qd_armed`, `forced_releases`, `phase_history`.

### `comfymodal_runtime/golden/snapshot.py`
- `REQUIRED_STATIC_ENTRIES`, `FORBIDDEN_SNAPSHOT_ENTRIES`
- `assert_quiescent(**flags) -> QuiescenceReport` (raises `QuiescenceViolationError`)
- `SnapshotAccounting`, `validate_exclusions(accounting)`
- `build_snapshot_manifest(model_manifests, extra_static=None) -> dict` (deterministic sha256)
- `immutable_metadata_present(required: Mapping[str, bool])`

### `comfymodal_runtime/golden/pipeline.py`
- `GOLDEN_ROLE_LOADER_POLICY` (frozen: CLIP/UNET/VAE → "QD4")
- `RoleBinding(role, manifest, destination_factory)`
- `GoldenPipeline(scheduler, ledger_sink=NULL_LEDGER_SINK, conditioning=DEFAULT_CONDITIONING_CONTRACT, owner_registry=None, join_timeout_s=120.0)`:
  `begin_restore`, `restore_ready`, `run_role_load(role, loader, binding, label_prefix)`, `begin_clip_forward`, `clip_forward_complete`, `clip_storage_release_proof`, `clip_gpu_critical_done`, `unet_prepare(binding)`, `run_unet_commit(loader, binding)`, `sampling_started`, `first_sampler_step_proven`, `run_vae_qd(loader, binding)`, `vae_decode_demand(timeout?)`, `vae_gpu_mutation_begin`, `complete_output`, `check_conditioning_observed(...)`.
- `classify_hard_failure(exc)`, `final_status(ok, degradation)`, `assert_fallback_never_nominal(degradation)`.

### `comfymodal_runtime/golden/integration.py`
- `golden_pipeline_enabled()` — env gate `COMFYMODAL_GOLDEN_PIPELINE` (deploy-time enablement ONLY; not runtime algorithm selection).
- `install_golden_seams(pipeline) -> {"clip_golden_load", "unet_golden_prepare", "unet_golden_commit", "unet_demand_join", "vae_golden_qd", "vae_demand_join"}` — fail-closed callables.

---

## 3. REQUIRED integration hunks (E40 side, post-merge)

### M-01 · CLIP Golden routing
- File: `comfyapp.py` (clean-lane CLIP QD invocation seam; post-E39 anchor: the synchronous `clip_qd_load` call site reached via `clip_fast_hydration_wiring.py`).
- Symbol: the clean-lane CLIP loader dispatch.
- Change: when `golden_pipeline_enabled()`, route through `seams["clip_golden_load"]` with a `RoleBinding` built from the request's CLIP manifest; otherwise existing behavior unchanged.
- Required: YES for Golden runs; OPTIONAL for other profiles.
- Expected E40 conflict: LOW — E40 is consolidating arm selection (`ClipLoader` policy); insert as one arm of that policy rather than a parallel branch.
- Semantic requirement: QD4 remains the only nominal arm; FastSafe/native remain fail-closed fallbacks that force DEGRADED.

### M-02 · UNET adoption at `load_models_gpu`
- File: `comfyapp.py` (single remaining observation-boundary wrapper around `comfy.model_management.load_models_gpu`) or its E40 successor module.
- Symbol: layer-1 `load_models_gpu` wrapper.
- Change: before native migration, consult `registry.join_or_adopt(ModelRole.UNET, timeout)`; on JOINED/ALREADY_READY validate identity and adopt (cache-validation only, no transfer); ADOPTED/FAILED/TIMEOUT proceed natively AND mark run DEGRADED via `classify_hard_failure`/typed records.
- Required: YES — this is what makes "no duplicate graph migration" true in production.
- Expected E40 conflict: MEDIUM — E40 owns the load_models_gpu boundary consolidation; the consult must survive into whatever single wrapper E40 lands.
- Semantic requirement: producer failure/timeout can recover output but never as ACCEPTED_NOMINAL.

### M-03 · VAE demand join at VAEDecode
- File: `comfyapp.py` / `model_preload.py` `_consume_vae_decode` path (whichever E40 canonizes).
- Symbol: VAEDecode consume hook.
- Change: call `seams["vae_demand_join"]` first; JOINED/ALREADY_READY decode from the Golden owner; otherwise native decode + DEGRADED record.
- Required: YES for the Golden timeline; native path remains the fallback.
- Expected E40 conflict: LOW/MEDIUM — deferred-VAE coordinator already exists; add the Golden consult ahead of it.
- Semantic requirement: no second VAE read after a successful Golden VAE QD4.

### M-04 · Ledger sink bridge
- File: `critical_path_ledger.py` consumer site chosen by E40.
- Change: pass a thin adapter implementing `emit(event_name, **fields)` onto the canonical ledger so Golden events (`restore_ready`, `clip_device_ready`, …, `first_durable_result`, `<label>_qd_stats`) appear in the canonical zero-gap ledger.
- Required: YES for gate predicates that assert event presence.
- Expected E40 conflict: LOW — pure addition at the sink boundary.
- Semantic requirement: event names are stable strings; do not rename without updating tests/benchmark.

### M-05 · RuntimeStatus vocabulary mapping
- File: E40's canonical status/ledger module.
- Change: map `golden.contracts.RuntimeStatus`/`DegradedReason` onto E40's canonical enum at ONE boundary; R41 guarantees the mapping direction (fallback ⇒ never nominal).
- Required: YES before gates consume statuses.
- Expected E40 conflict: LOW.

### M-06 · Empty-cache deterministic routing
- File: VAE-transition cleanup branch in `comfyapp.py` (or E40 successor).
- Change: route the `torch.cuda.empty_cache()` decision through the existing `empty_cache_bypass.py` predicate deterministically at the VAE transition; record executed/not-executed in telemetry.
- Required: RECOMMENDED (performance hygiene; correctness-neutral).
- Expected E40 conflict: LOW — guard already exists; this only fixes WHO calls it and WHEN.

### M-07 · Profile + config truth
- File: `config/v2/profiles/` (new profile e.g. `r41-golden-qd4` extending `e37-clean-lane-qd4` with `COMFYMODAL_GOLDEN_PIPELINE=1`) and ResolvedConfig projection of the env gate.
- Required: YES for remote validation.
- Expected E40 conflict: NONE if added after E40's config consolidation; the gate is a single deploy-time key.

---

## 4. Assumptions R41 made that E40 may change

1. Event-name strings (§2 pipeline/qd_engine lists) are stable identifiers used by tests and the benchmark; renaming requires synchronized updates.
2. `RuntimeStatus`/`DegradedReason` are R41-local until M-05 maps them.
3. Ownership lease-token namespace: R41 uses per-request `GoldenOwnerRegistry` instances and does NOT touch the known `restore_clip_loader` vs `restore_preload` owner-key mismatch (E40 §21/E39 debt item). If E40 unifies lease tokens, M-02/M-03 consults should use the unified namespace.
4. Destination strategies assume safetensors layouts whose tensor map covers the data region contiguously enough for block segmentation (inter-tensor padding tolerated; overlaps rejected).
5. `COMFYMODAL_GOLDEN_PIPELINE` is deploy-time only; if E40 prefers profile-native enablement, replace the env read inside `integration.golden_pipeline_enabled()` — single function, single test update.
6. CpuCopyBackend exists for deterministic local proof; production always constructs `CudaTransferBackend`. If E40 wants device-string plumbing from config, extend `QD4EngineConfig`/backend construction at the M-01..03 call sites.

## 5. Post-reconciliation validation order (describe-only)

1. Land M-01..M-05 (+M-06/07) on the merged checkout; run `pytest tests\golden` (must stay 58/58) plus E40's focused suites.
2. One remote deploy + structural gate (exact SHA, event sequence, forced-miss, no-fallback).
3. ≥6 true-cold cohort with occupancy telemetry; classify any slow-QD4 by drop reason.
4. VAE-slack perturbation arm. No step was executed by R41.
