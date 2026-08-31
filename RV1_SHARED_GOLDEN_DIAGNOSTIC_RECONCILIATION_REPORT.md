# RV1 Shared Golden Diagnostic Reconciliation

> **SUPERSESSION NOTICE (2026-08-30):** Historical reconciliation report;
> preserve its evidence and source-publication findings, but use
> `docs/COMFYMODAL_OUTPUT_DURABILITY_POLICY.md` for current generated-output
> semantics. Output durability is off by default; strict commit/reopen/hash
> proof is opt-in. S4 source publication durability remains mandatory.

## Scope

RV1 reconciled the completed S4, RA2B, RA3, RA6, RA7, and RA8 local work into
one Golden Serial diagnostic source. No branch or worktree was created. No
reset, stash, clean, revert, Modal deploy, or Modal invocation was performed.

The authoritative source reports reviewed were:

- `S4_CUSTOM_NODE_FULL_CONTENT_PUBLICATION_TRUST_REPORT.md`
- `RA2B_SNAPSHOT_RESTORE_CONTENT_TRUTH_REPORT.md`
- `RA3_CLIP_LOAD_FORWARD_TRUTH_AND_RECOVERY_REPORT.md`
- `RA6_GOLDEN_SAMPLING_DECOMPOSITION_REPORT.md`
- `RA7_DURABLE_COMMIT_VARIANCE_AND_DECOMPOSITION_REPORT.md`
- `RA8_VAE_LOAD_VARIANCE_REPORT.md`

The current `comfy-modal-core` and `comfymodal-golden-ops` skills were also
reviewed.

## Concurrent changes reconciled

`comfymodal_runtime/golden_serial.py` now contains one coherent combination of:

- RA3 selected-Qwen compute-scope adoption/readiness proof, CLIP load/forward
  timing, reversible forward observation, and observational page-fault data.
- RA6 sampling decomposition bridge and its independent `off`/`steps`/`blocks`
  selector.
- RA7 durable commit/reopen decomposition and post-commit marker event.
- RA8 VAE and QD transport decomposition, allocator/memory visibility, and
  staging observations.
- RV1 gating and helper reconciliation.

The RA7 event contract was retained. `DURABLE_COMMIT_SUBSPANS` remains emitted
after commit/reopen proof and before `golden_durable_commit` ends. The stale
pre-RA7 event-list assumptions are represented by the current updated Golden
tests; the event was not moved or deleted. `TRUE_FIRST_DURABLE_RESULT` and its
separate `DURABLE_RESULT_MARKER_PUBLICATION` remain after successful commit and
reopen, outside the durable stage.

S4 files retain the canonical full semantic publication set and generation.
RA2B remains observational: RSS, mappings, and page faults are not presented
as serialized Modal snapshot bytes or as causal proof. No prewarming, page
touching, or snapshot redesign was added.

## Conflicts and duplicate-helper audit

### Resolved within the Golden runtime

- Page faults: `_process_page_faults()` is the single raw reader. It uses
  `resource.getrusage(RUSAGE_SELF)` and Linux `/proc/self/stat` fallback, with
  unavailable dimensions left as `None`. `_clip_page_fault_snapshot()` and the
  CLIP delta shape are compatibility adapters over that reader, not separate
  counter definitions. The VAE path uses the same raw reader.
- QD timing: `read_file_qd_gpu()` owns the physical transport accounting and
  `build_qd_transport_diagnostics()` is one projection of those stats. The
  host wait implementation is `_wait_event_host_ns()` with the millisecond
  wrapper `_wait_event_host()`; it is not two timing implementations.
- RA7 timing uses the recorder-injected monotonic clock for its nine spans and
  preserves the exact commit-return/reopen boundary.

### Intentionally retained, not semantically duplicate

- `sampling_deep_profile.py` keeps its lightweight process-residency snapshot
  schema because Golden Serial is intentionally self-contained and must not
  import the historical runtime stack. Its `off` path also must not import or
  patch sampler/model classes. Its RSS-plus-availability schema is different
  from Golden's raw page-fault adapter.
- Golden `_allocator_state()` includes optional allocator statistics, while the
  gated sampling profile snapshot is a smaller unsynchronized observation.
  They are different scopes, not interchangeable definitions.
- Golden's `_safe_diagnostic_value()` intentionally drops unknown values rather
  than stringifying counters. Whole-document persistence uses the existing
  `json.dumps(..., default=str)` boundary for a different persistence contract;
  these are not silently substituted for one another.
- The legacy `clip_qd_reader.py` and other historical runtime modules retain
  their own non-Golden diagnostics. They are outside the self-contained Golden
  implementation and were not merged into its path.

## Authoritative stage boundaries

The following stage walls remain actual function entry through return/raise:

- `golden_clip_load`
- `golden_clip_forward`
- `golden_unet_load`
- `golden_vae_load`
- `golden_sampling`
- `golden_durable_commit`

Nested CLIP, QD, VAE, sampling, CUDA-event, and durability spans explain those
walls and are explicitly non-additive where workers or hooks overlap. No work
was moved outside a heavy-stage boundary, and no child diagnostic replaced an
authoritative wall.

## Observer-effect audit

| Diagnostic | Classification | Final behavior |
|---|---|---|
| Required stage entry/exit marks and recorder monotonic marks | negligible always-on boundary mark | Retained for authoritative stage evidence. |
| Required QD completion events, worker joins, and completion waits | correctness machinery, not optional measurement | Retained; completion events use `enable_timing=False`. |
| RA3 temporary CLIP wrappers and selected-Qwen hooks | diagnostic-only/gated | Installed only when `COMFYMODAL_GOLDEN_STAGE_DIAGNOSTICS` is enabled; removed in `finally`. |
| CLIP/VAE page-fault, RSS, memlock, and allocator queries | diagnostic-only/gated | No process queries on the default CLIP/VAE path. Values are never used for readiness or causality. |
| RA8 QD source-read, CPU-to-pinned, H2D enqueue, CUDA-event, and wait timing | potentially material | Gated by `COMFYMODAL_GOLDEN_STAGE_DIAGNOSTICS`; timing CUDA start events do not exist when off. |
| RA8 per-read/per-copy diagnostic fields and aggregations | potentially material | Omitted from off-path records/stats; correctness byte/worker records remain. |
| RA8 VAE decomposition and memory snapshots | diagnostic-only/gated | Enabled only by the stage diagnostic selector. |
| RA6 steps/blocks hooks and CUDA event realization | potentially material | Controlled by `COMFYMODAL_SAMPLING_DEEP_PROFILE`; canonical default/missing/invalid is `off`. Any optional CUDA realization is after `sampling_end`. |
| JSON snapshots/deep-copy of emitted RA7 event payloads | negligible always-on event-boundary protection | Retained to make raw event snapshots immutable after emission. |
| Existing sampler timing wrapper | negligible always-on boundary instrumentation | Not the RA6 deep profiler; no RA6 hooks or sync are enabled by this alone. |

There are **no potentially material diagnostics left always-on**. The normal
Golden path retains only required correctness work and inexpensive boundary
marks. The diagnostic campaign enables
`COMFYMODAL_GOLDEN_STAGE_DIAGNOSTICS=1`; RA6 remains independently selected by
`COMFYMODAL_SAMPLING_DEEP_PROFILE=steps|blocks`.

## Contract checks

- **RA6:** `off` is canonical in `golden_p1.toml`; missing and invalid values
  resolve to `off`; steps and blocks are explicit; blocks hooks do not execute
  in off mode; normal sampling has no device-wide synchronization. The one
  optional blocks-mode CUDA realization is post-`sampling_end` cleanup.
- **RA3:** compute readiness is the selected adopted Qwen scope's device,
  dtype, pointer/storage proof, with explicit tiny outer extras retained
  separately. It is not the outer wrapper's first generic parameter.
- **RA8/RA9 boundary:** CLIP/UNET/VAE storage ownership and retained staging
  are unchanged; no cross-owner pool or early reuse was introduced;
  `release_storage()` is not used while adopted tensors are live.
- **RA7:** real Volume commit and reopen verification remain mandatory; all nine
  host subspans are non-overlapping; the commit API remains opaque; reopened
  content SHA/byte count is strict; configured expected SHA mismatch remains a
  warning-only observation; result-marker publication remains outside the
  durable stage.
- **S4:** one semantic walker/file set and one full published-content generation
  remain authoritative. Narrow deployment/source identity cannot authorize
  receipt recovery. Exact unchanged receipt matches still skip republishing,
  and publisher ownership remains the stable shared publisher rather than a
  consumer app.
- **RA2B:** page faults/RSS remain observational only. No page touching,
  prewarming, or snapshot-content inference was added.

## Local validation

All commands were run from the repository root and did not contact Modal.

### Green focused and required suites

```text
rtk pytest -q tests/test_p1_golden_serial.py tests/test_p2_golden_snapshot_adapter.py tests/test_p2_golden_observability.py tests/test_p2_golden_core_contract.py tests/test_p4_1_golden_identity_variance.py tests/test_p4_1_golden_identity_cold.py tests/test_golden_p1_wiring.py tests/test_golden_sampling_diagnostics.py tests/test_benchmark_v2_golden_acceptance.py tests/test_golden_aimdo_activation.py
277 passed, 1 skipped

rtk pytest -q tests/test_s2_golden_deploy.py tests/test_source_identity_publication.py tests/test_v2_custom_node_generation_identity.py tests/test_custom_node_generation_parity.py tests/test_s1_publisher_bootstrap.py tests/test_runtime_deployment_spec.py tests/test_golden_p1_wiring.py
156 passed, 2 skipped

rtk pytest -q tests/test_v2_sampling_deep_profile.py tests/test_v2_sampling_deep_profile_wrapper.py tests/test_sampling_deep_profile_attention_observation.py tests/test_ra3_clip_truth_telemetry.py tests/test_ra5_attention_backend.py tests/test_clip_vae_request_activation.py
117 passed

rtk pytest -q tests/test_p1_golden_serial.py tests/test_ra3_clip_truth_telemetry.py tests/test_v2_sampling_deep_profile.py tests/test_v2_sampling_deep_profile_wrapper.py tests/test_sampling_deep_profile_attention_observation.py tests/test_ra5_attention_backend.py tests/test_clip_vae_request_activation.py
223 passed
```

### Restore/snapshot validation and unresolved failures

```text
rtk pytest -q tests/test_restore_timing_data_flow.py tests/test_restore_plan_publication.py tests/test_restore_ordering_root_cause.py tests/test_modal_restore_boundary.py tests/test_minimal_restore.py tests/test_runtime_restore_plan.py tests/test_v2_diagnosis_restore_timing.py tests/test_v2_clip_restore_lifecycle.py tests/test_sageattention_restore_policy.py tests/test_v2_publish_restore_plan_registration.py tests/test_v2_snapshot_restore_only.py tests/test_cpu_snapshot_models.py tests/test_phase_e_single_snapshot_replay.py tests/test_v2_snapshot_seed_request_metadata.py tests/test_v2_snapshot_model_bridge.py tests/test_v2_snapshot_manifest_hygiene_extensions.py tests/test_v2_snapshot_capture_hygiene.py tests/test_v2_snapshot_build_manifest.py tests/test_v2_snapshot_age_accounting.py tests/test_v2_snapshot_activation_invariant.py tests/test_v2_production_snapshot_invariant.py tests/test_v2_manager_snapshot_offline.py tests/test_v2_loader_bridge_diagnostic_snapshot.py tests/test_v2_cpu_snapshot_lifecycle.py
771 passed, 29 failed
```

The 29 failures are outside the RV1-owned Golden diagnostic changes:

- restore-ordering tests expect removed/renamed historical `comfyapp` symbols;
- several restore timing expectations target pre-existing event names;
- startup tests fail in this local environment at the existing CacheDiT
  preimport gate because `diffusers`/`huggingface_hub` and `cache_dit` are not
  compatible/installed;
- clip restore lifecycle tests trip a worker mock's existing
  `torch.cuda.is_available()` prohibition before exercising RV1 code.

They are retained as unresolved local validation issues, not accepted as a
green repository-wide result and not masked by focused-suite success. No
restore/snapshot source was changed by RV1.

### Static checks

```text
python -m py_compile comfyapp.py comfymodal_runtime/deployment_spec.py comfymodal_runtime/golden_serial.py comfymodal_runtime/publication_policy.py comfymodal_runtime/sampling_deep_profile.py tools/v2_control/custom_nodes.py tests/test_p1_golden_serial.py tests/test_ra3_clip_truth_telemetry.py
passed

rtk git diff --check
passed
```

## Exact RV1 file list

Files edited by the RV1 reconciliation lane:

- `comfymodal_runtime/golden_serial.py`
- `tests/test_p1_golden_serial.py`
- `tests/test_ra3_clip_truth_telemetry.py`
- `RV1_SHARED_GOLDEN_DIAGNOSTIC_RECONCILIATION_REPORT.md`

The other dirty files and reports listed by `git status` are concurrent S4,
RA2B, RA3, RA6, RA7, RA8, or unrelated pre-existing work and were preserved.

## Final disposition

The Golden diagnostic source is internally homogeneous for the requested
remote-validation campaign: required stage and durability semantics are
preserved, material diagnostics are explicitly opt-in, and the selected
readiness/ownership/publication models remain authoritative. Remote
validation itself remains pending and must use the canonical isolated-app
Golden control plane from `comfymodal-golden-ops`; this batch did not deploy.

Because the broad restore/snapshot validation still has 29 unresolved local
failures, the tree should **not** be declared unconditionally safe for a
single commit/deploy gate until those pre-existing failures are separately
resolved or explicitly waived by the owner. RV1 itself introduces no known
Golden diagnostic blocker.

```text
RV1_RECONCILIATION_COMPLETE=YES
SHARED_GOLDEN_TESTS_GREEN=YES
DUPLICATE_DIAGNOSTIC_HELPERS_RESOLVED=YES
RA6_PROFILER_DEFAULT_OFF=YES
POTENTIALLY_MATERIAL_ALWAYS_ON_DIAGNOSTICS=NONE
S4_TRUST_MODEL_PRESERVED=YES
RA3_READINESS_MODEL_PRESERVED=YES
RA7_DURABILITY_MODEL_PRESERVED=YES
RA8_RA9_BOUNDARY_PRESERVED=YES
READY_FOR_SINGLE_REMOTE_DIAGNOSTIC_DEPLOY=NO
REPORT=RV1_SHARED_GOLDEN_DIAGNOSTIC_RECONCILIATION_REPORT.md
```
