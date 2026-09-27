# RV1C Final Local Deploy Gate Report

## Decision

```text
READY_FOR_SINGLE_REMOTE_DIAGNOSTIC_DEPLOY=YES
```

The local gate is complete. No Modal deployment or invocation was performed.
The current Golden path and S4/RA3/RA6/RA7/RA8 contracts are green. The only
remaining red tests are three intentional historical assertions for retired
non-Golden architecture.

## Before/after failure accounting

| Point in validation | Passed | Failed | Disposition |
|---|---:|---:|---|
| RV1 exact restore/snapshot baseline | 771 | 29 | RV1B classified: 3 legacy, 4 stale, 7 local dependency, 15 harness; 0 real, 0 unknown |
| RV1B latest pre-RV1C rerun | 774 | 26 | Previously recorded after earlier authorized corrections |
| RV1C first full rerun before hermetic startup repair | 789 | 11 | 3 legacy, 7 local dependency, 1 stale fallback assertion |
| RV1C final exact restore/snapshot suite | 797 | 3 | All three are retained retired-symbol legacy tests |

Additional failures outside the original 29 were closed as follows:

- 2 old-MD5 content-generation assertions now use canonical full-publication
  SHA-256.
- 1 placement assertion is hermetic against ambient host metadata; `gcp` is a
  valid current runtime identity value.
- 15 CLIP lifecycle tests now execute past fixture construction; all pass.
- 7 CacheDiT startup tests now use a scoped dependency-family fixture and all
  pass without changing production dependency pins or fail-closed behavior.

## Changes made by RV1C

Only tests were changed by this lane:

- `tests/test_modal_app_identity.py` — both content-generation record tests
  now calculate/expect the canonical full-publication SHA-256 generation.
- `tests/test_v2_clip_restore_lifecycle.py` — the synthetic `_FakePatcher` is
  explicitly CPU-only and no longer calls `torch.cuda.is_available()`.
  The production preload-worker prohibition remains unchanged.
- `tests/test_v2_diagnosis_restore_timing.py` — current
  `phase_durations_ms`/typed restore-event assertions; scoped hermetic
  CacheDiT-family preimport fixture for startup tests; lifecycle-only typed
  completion assertion instead of the retired fallback event.
- `tests/test_v2_snapshot_restore_only.py` — clears ambient cloud/region
  environment for the local placement fixture.

`tests/test_v2_snapshot_model_bridge.py` was already dirty before RV1C. Its
DualCLIP fixture already used `derive_model_key(self.workflow)`; RV1C verified
that correction and did not overwrite the concurrent change.

No production source, pinned dependency, Modal state, branch, worktree, or
preload-worker CUDA guard was changed by RV1C. Existing concurrent S4/RA2B/RA3/
RA6/RA7/RA8 changes were preserved.

## Previously masked tests and behavioral result

The 15 CLIP restore lifecycle tests previously failed during `_FakePatcher`
construction because the fixture called the intentionally forbidden
`torch.cuda.is_available()` probe from the preload-worker path. The narrow
CPU-only fixture repair allowed all 15 previously masked behavior tests to
execute, plus the module's unchanged summary-default test. The final module
result was **16 passed**. No newly exposed lifecycle assertion failed.

The seven CacheDiT startup tests now execute with a scoped test seam around
the real preimport function. The workstation still has the incompatible
`diffusers`/`huggingface_hub` pair and no `cache_dit` installation, but the
production preimport gate remains fail-closed and the tests no longer confuse
that workstation condition with restore behavior.

## Remaining failures and waivers

The final exact RV1 restore/snapshot command has exactly three failures:

1. `TestCUDAWarmupTensorLifetime.test_done_log_includes_all_phases` —
   historical `_ComfyAPIMixin._warmup_cuda` symbol is retired.
2. `TestCUDAWarmupTensorLifetime.test_tensors_destroyed_before_done_log` —
   same retired `_warmup_cuda` symbol.
3. `TestProductionOutputContract.test_production_request_still_module_level` —
   historical `_PROD_DIRECT_SINK_REQUEST` symbol is retired.

These tests were intentionally left alone. They do not execute the current
Golden production path and do not represent restore regressions. No local
environment or harness failures remain in the final required suite. No current
behavioral failure or unknown classification was found.

## Classification closure

```text
REAL_CURRENT_REGRESSION=0
UNKNOWN=0
STALE_TESTS_REPAIRED=7
  = 4 RV1B stale failures + 2 old-MD5 tests + 1 ambient-placement assertion
HARNESS_TESTS_NOW_EXECUTING=15
LOCAL_ENVIRONMENT_FAILURES_REMAINING=0
LEGACY_FAILURES_REMAINING=3
```

The local dependency issue remains documented as workstation-specific evidence:
without the scoped test fixture, startup stops at
`comfymodal_runtime/modal_app.py:10690` before restore timing/state assertions.
The remote Golden image owns its compatible dependency environment; production
dependencies were not changed merely to satisfy this workstation.

## Required commands and results

All commands ran from the repository root. None contacted Modal.

### Exact RV1 restore/snapshot suite

```text
rtk pytest -q tests/test_restore_timing_data_flow.py tests/test_restore_plan_publication.py tests/test_restore_ordering_root_cause.py tests/test_modal_restore_boundary.py tests/test_minimal_restore.py tests/test_runtime_restore_plan.py tests/test_v2_diagnosis_restore_timing.py tests/test_v2_clip_restore_lifecycle.py tests/test_sageattention_restore_policy.py tests/test_v2_publish_restore_plan_registration.py tests/test_v2_snapshot_restore_only.py tests/test_cpu_snapshot_models.py tests/test_phase_e_single_snapshot_replay.py tests/test_v2_snapshot_seed_request_metadata.py tests/test_v2_snapshot_model_bridge.py tests/test_v2_snapshot_manifest_hygiene_extensions.py tests/test_v2_snapshot_capture_hygiene.py tests/test_v2_snapshot_build_manifest.py tests/test_v2_snapshot_age_accounting.py tests/test_v2_snapshot_activation_invariant.py tests/test_v2_production_snapshot_invariant.py tests/test_v2_manager_snapshot_offline.py tests/test_v2_loader_bridge_diagnostic_snapshot.py tests/test_v2_cpu_snapshot_lifecycle.py
797 passed, 3 failed
```

The three failures are the legacy tests listed above.

### Current contract and identity checks

```text
rtk pytest -q tests/test_v2_diagnosis_restore_timing.py
40 passed

rtk pytest -q tests/test_v2_snapshot_model_bridge.py
51 passed

rtk pytest -q tests/test_modal_app_identity.py -k "SyncActualSyncCreatesGenerationRecord" tests/test_v2_custom_node_generation_identity.py tests/test_custom_node_generation_parity.py tests/test_source_identity_publication.py
4 passed

rtk pytest -q tests/test_v2_snapshot_restore_only.py -k "probe_surfaces_restore_timing_and_entry"
1 passed

rtk python -m unittest tests.test_v2_clip_restore_lifecycle -v
16 passed
```

### Golden, S4, RA3, and RA6

```text
rtk pytest -q tests/test_p1_golden_serial.py tests/test_p2_golden_snapshot_adapter.py tests/test_p2_golden_observability.py tests/test_p2_golden_core_contract.py tests/test_p4_1_golden_identity_variance.py tests/test_p4_1_golden_identity_cold.py tests/test_golden_p1_wiring.py tests/test_golden_sampling_diagnostics.py tests/test_benchmark_v2_golden_acceptance.py tests/test_golden_aimdo_activation.py
277 passed, 1 skipped

rtk pytest -q tests/test_s2_golden_deploy.py tests/test_source_identity_publication.py tests/test_v2_custom_node_generation_identity.py tests/test_custom_node_generation_parity.py tests/test_s1_publisher_bootstrap.py tests/test_runtime_deployment_spec.py tests/test_golden_p1_wiring.py
156 passed, 2 skipped

rtk pytest -q tests/test_ra3_clip_truth_telemetry.py
9 passed

rtk pytest -q tests/test_v2_sampling_deep_profile.py tests/test_v2_sampling_deep_profile_wrapper.py tests/test_sampling_deep_profile_attention_observation.py
68 passed
```

### RA7/RA8 Golden Serial coverage

```text
rtk pytest -q tests/test_p1_golden_serial.py
106 passed
```

This is the current Golden Serial file containing the durable-commit and VAE
decomposition/schema coverage. It is also included in the 277-test Golden
suite above.

### Static validation

```text
rtk python -m py_compile comfyapp.py comfymodal_runtime/deployment_spec.py comfymodal_runtime/golden_serial.py comfymodal_runtime/publication_policy.py comfymodal_runtime/sampling_deep_profile.py tools/v2_control/custom_nodes.py tests/test_golden_p1_wiring.py tests/test_modal_app_identity.py tests/test_p1_golden_serial.py tests/test_s2_golden_deploy.py tests/test_v2_clip_restore_lifecycle.py tests/test_v2_custom_node_generation_identity.py tests/test_v2_diagnosis_restore_timing.py tests/test_v2_sampling_deep_profile.py tests/test_v2_snapshot_model_bridge.py tests/test_v2_snapshot_restore_only.py tests/test_ra3_clip_truth_telemetry.py
passed

rtk git diff --check
passed
```

## Final disposition

The final local gate authorizes the next step: one single remote diagnostic
deployment using a fresh isolated experimental app and the canonical Golden
control plane in `comfymodal-golden-ops`. This report does not authorize using
the protected production app, does not count as remote validation, and does
not claim remote output, durability, snapshot, or performance evidence.

```text
RV1C_COMPLETE=YES
REAL_CURRENT_REGRESSION=0
UNKNOWN=0
STALE_TESTS_REPAIRED=7
HARNESS_TESTS_NOW_EXECUTING=15
LOCAL_ENVIRONMENT_FAILURES_REMAINING=0
LEGACY_FAILURES_REMAINING=3
GOLDEN_SUITES_GREEN=YES
S4_SUITE_GREEN=YES
RA3_SUITE_GREEN=YES
RA6_SUITE_GREEN=YES
RA7_RA8_GOLDEN_SERIAL_GREEN=YES
READY_FOR_SINGLE_REMOTE_DIAGNOSTIC_DEPLOY=YES
REPORT=RV1C_FINAL_LOCAL_DEPLOY_GATE_REPORT.md
```
