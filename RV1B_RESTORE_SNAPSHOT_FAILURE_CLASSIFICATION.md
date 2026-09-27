# RV1B Restore/Snapshot Failure Classification

## Scope and constraints

This is a classification of the exact 29 failures recorded by the baseline
restore/snapshot run. It is diagnostic bookkeeping only: no source or test
files are changed here, no tests are run, and no Modal deployment or remote
invocation is authorized by this report. The validation owner is the
parent/orchestrator.

The baseline failure list is taken verbatim from
`C:\Users\parla\AppData\Local\rtk\tee\1788125712_pytest-failures.log`.
The baseline terminal result is taken from
`C:\Users\parla\AppData\Local\rtk\tee\1788125712_pytest.log`:

```text
29 failed, 795 passed, 3 subtests passed in 189.11s (0:03:09)
```

For the restore-suite accounting used by the reconciliation report, the
original baseline was **771 passed / 29 failed**. The current post-fix exact
restore-suite status from the latest rerun is **774 passed / 26 failed**. The
change in counts does not turn the remaining non-Golden failures into a clean
gate.

## Classification result

There is **no `REAL_CURRENT_REGRESSION` in this baseline**. `UNKNOWN=0`.
The aggregate counts sum exactly to 29:

| Classification | Count | Baseline rows |
|---|---:|---:|
| `LEGACY_NON_GOLDEN_PATH` | 3 | 1–3 |
| `STALE_TEST_EXPECTATION` | 4 | 4–5, 7, 29 |
| `LOCAL_ENVIRONMENT_DEPENDENCY` | 7 | 6, 8–13 |
| `MOCK/HARNESS_LIMITATION` | 15 | 14–28 |
| `REAL_CURRENT_REGRESSION` | 0 | none |
| `UNKNOWN` | 0 | none |
| **Total** | **29** | **1–29** |

## Explicit baseline failure table

| # | Test identifier | Observed failure/evidence | Classification | Authoritative current contract | Change status | Disposition |
|---:|---|---|---|---|---|---|
| 1 | `tests/test_restore_ordering_root_cause.py::TestCUDAWarmupTensorLifetime::test_done_log_includes_all_phases` | `AttributeError`: `_ComfyAPIMixin` has no attribute `_warmup_cuda` while `inspect.getsource(...)` runs. | `LEGACY_NON_GOLDEN_PATH` | The current production path does not expose the removed historical `_warmup_cuda` API. | Legacy assertion intentionally untouched. | Retain as historical/non-Golden debt; not a current restore regression. |
| 2 | `tests/test_restore_ordering_root_cause.py::TestCUDAWarmupTensorLifetime::test_tensors_destroyed_before_done_log` | Same missing `_ComfyAPIMixin._warmup_cuda` `AttributeError` during source inspection. | `LEGACY_NON_GOLDEN_PATH` | The current production path does not expose the removed historical `_warmup_cuda` API. | Legacy assertion intentionally untouched. | Retain as historical/non-Golden debt; not a current restore regression. |
| 3 | `tests/test_restore_ordering_root_cause.py::TestProductionOutputContract::test_production_request_still_module_level` | `AssertionError`: `hasattr(comfyapp, '_PROD_DIRECT_SINK_REQUEST')` is false. | `LEGACY_NON_GOLDEN_PATH` | Production output is governed by the current request/output contract, not the removed module-level direct-sink symbol. | Legacy assertion intentionally untouched. | Retain as historical/non-Golden debt; not a current restore regression. |
| 4 | `tests/test_v2_diagnosis_restore_timing.py::test_restore_timing_stage_timings_included_when_available` | Expected a `snapshot_restore` stage key; observed keys were `snapshot_callback_age_at_restore_ms`, `reload_runtime_state_ms`, `reload_models_ms`, `restore_gpu_state_ms`, `initialize_cuda_ms`, `snapshot_identity_checks_ms`, and `cpu_snapshot_retargeting_ms`. | `STALE_TEST_EXPECTATION` | Restore timing is published in the current typed result under `phase_durations_ms`; stage/event names are current-contract data, not the pre-fix assertion. | Already-authorized stale fix: timing test now uses `phase_durations_ms` and current typed events. | Treat baseline failure as stale; verify only in the owner’s next validation pass. |
| 5 | `tests/test_v2_diagnosis_restore_timing.py::test_restore_plan_read_events` | Expected `restore_plan_read_start`; observed current events include `snapshot_restore_start`, `restore_stage_classification`, `snapshot_restore_end`, and related typed lifecycle events, but not that historical name. | `STALE_TEST_EXPECTATION` | The current restore event contract uses typed restore-stage/lifecycle events; `restore_plan_read_start` is not authoritative. | Already-authorized stale event expectation fix. | Treat as stale suite drift; no runtime change implied. |
| 6 | `tests/test_v2_diagnosis_restore_timing.py::test_startup_phase_durations_exported` | `startup()` fails at `comfymodal_runtime/modal_app.py:10690`: CacheDiT preimport failure because `diffusers` cannot import `cached_download` from `huggingface_hub` and `cache_dit` is missing. | `LOCAL_ENVIRONMENT_DEPENDENCY` | Startup fail-closes at the CacheDiT preimport gate when required local dependencies are incompatible or absent. | No source change authorized for this baseline failure. | Repair the local dependency/cache environment or obtain an owner waiver; do not label a restore regression. |
| 7 | `tests/test_v2_diagnosis_restore_timing.py::test_restore_extends_preparation_when_handoff_fails` | Expected `preload_fallback_mode`; observed event list has no such event and otherwise contains current typed restore events. | `STALE_TEST_EXPECTATION` | Handoff/fallback reporting follows the current typed restore/preparation event contract, not the retired event name. | Already-authorized stale event expectation fix. | Treat as stale suite drift; no runtime change implied. |
| 8 | `tests/test_v2_diagnosis_restore_timing.py::test_startup_returns_restore_timing` | `startup()` fails at `comfymodal_runtime/modal_app.py:10690` with the same `cached_download` incompatibility and missing `cache_dit`. | `LOCAL_ENVIRONMENT_DEPENDENCY` | The CacheDiT preimport gate must pass before startup can return timing data. | No source change authorized for this baseline failure. | Repair dependencies/cache or obtain an owner waiver; not a current restore regression. |
| 9 | `tests/test_v2_diagnosis_restore_timing.py::test_startup_restore_timing_includes_stage_durations` | `startup()` fails at `comfymodal_runtime/modal_app.py:10690` with the same diffusers/`huggingface_hub` incompatibility and missing `cache_dit`. | `LOCAL_ENVIRONMENT_DEPENDENCY` | Startup cannot export restore timing until the required CacheDiT preimport contract is satisfied. | No source change authorized for this baseline failure. | Repair dependencies/cache or obtain an owner waiver; not a current restore regression. |
| 10 | `tests/test_v2_diagnosis_restore_timing.py::test_startup_sets_restore_timing_on_instance` | `startup()` fails at `comfymodal_runtime/modal_app.py:10690` with the same CacheDiT preimport error before instance state can be checked. | `LOCAL_ENVIRONMENT_DEPENDENCY` | Instance timing state is evaluated only after successful startup and dependency preimport. | No source change authorized for this baseline failure. | Repair dependencies/cache or obtain an owner waiver; not a current restore regression. |
| 11 | `tests/test_v2_diagnosis_restore_timing.py::test_startup_updates_process_local_fallback` | `startup()` fails at `comfymodal_runtime/modal_app.py:10690` with incompatible `diffusers`/`huggingface_hub` and absent `cache_dit`. | `LOCAL_ENVIRONMENT_DEPENDENCY` | Startup’s process-local fallback behavior is downstream of the mandatory CacheDiT preimport gate. | No source change authorized for this baseline failure. | Repair dependencies/cache or obtain an owner waiver; not a current restore regression. |
| 12 | `tests/test_v2_diagnosis_restore_timing.py::test_startup_trace_has_container_session_id` | `startup()` fails at `comfymodal_runtime/modal_app.py:10690` with the same CacheDiT preimport failure, before trace assertion. | `LOCAL_ENVIRONMENT_DEPENDENCY` | Container-session trace assertions require a successfully initialized startup environment. | No source change authorized for this baseline failure. | Repair dependencies/cache or obtain an owner waiver; not a current restore regression. |
| 13 | `tests/test_v2_diagnosis_restore_timing.py::test_startup_lifecycle_identity_in_trace_events` | `startup()` fails at `comfymodal_runtime/modal_app.py:10690` with the same diffusers/`huggingface_hub` and missing `cache_dit` errors. | `LOCAL_ENVIRONMENT_DEPENDENCY` | Lifecycle identity events are emitted only after the startup dependency gate succeeds. | No source change authorized for this baseline failure. | Repair dependencies/cache or obtain an owner waiver; not a current restore regression. |
| 14 | `tests/test_v2_clip_restore_lifecycle.py::TestCaptureExclusionFlow::test_capture_full_cpu_to_excluded` | Fails before lifecycle behavior: fake construction calls `torch.cuda.is_available()` at `tests/test_v2_clip_restore_lifecycle.py:142`; the mocked call reaches `comfymodal_runtime/modal_app.py:4748` and the preload-worker prohibition at `host_hardware_telemetry.py:972`. | `MOCK/HARNESS_LIMITATION` | The preload-worker fake must be constructible without violating the harness prohibition on `torch.cuda.is_available()`; lifecycle assertions are downstream. | No source change; harness failure is pre-behavior. | Repair/isolate the fake or mock, then rerun; do not classify as a production regression. |
| 15 | `tests/test_v2_clip_restore_lifecycle.py::TestCaptureExclusionFlow::test_capture_without_exclude_keeps_full_cpu` | Same pre-behavior `torch.cuda.is_available()` failure in the test fake, routed through production probe line 4748 and the preload-worker prohibition. | `MOCK/HARNESS_LIMITATION` | The fake must reach capture setup without invoking the forbidden CUDA availability probe from the preload worker. | No source change; harness failure is pre-behavior. | Repair/isolate the fake or mock, then rerun; do not classify as a production regression. |
| 16 | `tests/test_v2_clip_restore_lifecycle.py::TestCaptureExclusionFlow::test_exclusion_frees_original_storages` | Same pre-behavior `torch.cuda.is_available()` failure while constructing `_FakeClip`/`_FakePatcher`, with production probe line 4748 in the traceback. | `MOCK/HARNESS_LIMITATION` | Storage-release behavior is not observed until the fake can be built under the worker CUDA-probe contract. | No source change; harness failure is pre-behavior. | Repair/isolate the fake or mock, then rerun; do not classify as a production regression. |
| 17 | `tests/test_v2_clip_restore_lifecycle.py::TestEvictionReloadLifecycle::test_eviction_style_fresh_reload_without_reconcile_is_the_bug` | Same fake-construction failure at `torch.cuda.is_available()` before eviction/reload behavior, including `comfymodal_runtime/modal_app.py:4748`. | `MOCK/HARNESS_LIMITATION` | Eviction/reload semantics require a valid fake setup; the worker must not call the forbidden CUDA availability probe. | No source change; harness failure is pre-behavior. | Repair/isolate the fake or mock, then rerun; do not classify as a production regression. |
| 18 | `tests/test_v2_clip_restore_lifecycle.py::TestEvictionReloadLifecycle::test_reconcile_reattach_hydrates_on_demand` | Same pre-behavior fake-construction failure at `torch.cuda.is_available()` through production probe line 4748. | `MOCK/HARNESS_LIMITATION` | Reconcile/reattach hydration is evaluated only after the harness permits fake construction. | No source change; harness failure is pre-behavior. | Repair/isolate the fake or mock, then rerun; do not classify as a production regression. |
| 19 | `tests/test_v2_clip_restore_lifecycle.py::TestEvictionReloadLifecycle::test_reconcile_reattach_restores_exclusion` | Same pre-behavior `torch.cuda.is_available()` mock prohibition before reconcile behavior, with production probe line 4748. | `MOCK/HARNESS_LIMITATION` | Reconcile exclusion restoration is downstream of valid worker-safe fake initialization. | No source change; harness failure is pre-behavior. | Repair/isolate the fake or mock, then rerun; do not classify as a production regression. |
| 20 | `tests/test_v2_clip_restore_lifecycle.py::TestDemandLifecycle::test_cache_hit_zero_hydration` | Same pre-behavior fake-construction failure at `torch.cuda.is_available()` through `modal_app.py:4748`; demand behavior is never reached. | `MOCK/HARNESS_LIMITATION` | Cache-hit hydration assertions require the fake to be initialized without a forbidden worker CUDA probe. | No source change; harness failure is pre-behavior. | Repair/isolate the fake or mock, then rerun; do not classify as a production regression. |
| 21 | `tests/test_v2_clip_restore_lifecycle.py::TestDemandLifecycle::test_cache_miss_one_hydration_from_excluded` | Same pre-behavior failure at fake construction and production probe line 4748 before cache-miss hydration executes. | `MOCK/HARNESS_LIMITATION` | Cache-miss hydration is tested only after worker-safe fake setup. | No source change; harness failure is pre-behavior. | Repair/isolate the fake or mock, then rerun; do not classify as a production regression. |
| 22 | `tests/test_v2_clip_restore_lifecycle.py::TestDemandLifecycle::test_cpu_materialized_before_demand_is_never_called_already_fast_hydrated` | Same `torch.cuda.is_available()` prohibition during fake construction, before the demand-path assertion. | `MOCK/HARNESS_LIMITATION` | Already-materialized demand behavior is downstream of the harness CUDA-probe contract. | No source change; harness failure is pre-behavior. | Repair/isolate the fake or mock, then rerun; do not classify as a production regression. |
| 23 | `tests/test_v2_clip_restore_lifecycle.py::TestDemandLifecycle::test_encode_parity_after_hydration` | Same pre-behavior fake/mock failure at `torch.cuda.is_available()` through `modal_app.py:4748`; encode parity is not exercised. | `MOCK/HARNESS_LIMITATION` | Encode parity must be checked after valid lifecycle setup, not after a prohibited worker CUDA query. | No source change; harness failure is pre-behavior. | Repair/isolate the fake or mock, then rerun; do not classify as a production regression. |
| 24 | `tests/test_v2_clip_restore_lifecycle.py::TestNoInvalidModelEscapes::test_bare_full_cpu_no_manifest_fails_closed` | Same pre-behavior `torch.cuda.is_available()` failure in fake setup, routed through production probe line 4748 before fail-closed behavior. | `MOCK/HARNESS_LIMITATION` | Invalid-model fail-closed behavior is authoritative only when the harness reaches the model path. | No source change; harness failure is pre-behavior. | Repair/isolate the fake or mock, then rerun; do not classify as a production regression. |
| 25 | `tests/test_v2_clip_restore_lifecycle.py::TestNoInvalidModelEscapes::test_fallback_exactly_once` | Same pre-behavior CUDA availability mock prohibition before fallback behavior is entered. | `MOCK/HARNESS_LIMITATION` | Exactly-once fallback is evaluated after worker-safe fake construction. | No source change; harness failure is pre-behavior. | Repair/isolate the fake or mock, then rerun; do not classify as a production regression. |
| 26 | `tests/test_v2_clip_restore_lifecycle.py::TestNoInvalidModelEscapes::test_meta_only_model_never_escapes_to_encode` | Same fake/production-probe `torch.cuda.is_available()` failure before the meta-only model can reach encode. | `MOCK/HARNESS_LIMITATION` | Meta-only model containment is tested only after the harness permits the request path to execute. | No source change; harness failure is pre-behavior. | Repair/isolate the fake or mock, then rerun; do not classify as a production regression. |
| 27 | `tests/test_v2_clip_restore_lifecycle.py::TestRequestSummaryStates::test_summary_after_excluded_hydration_carries_state` | Same pre-behavior `torch.cuda.is_available()` failure through `modal_app.py:4748`; request summary is never produced. | `MOCK/HARNESS_LIMITATION` | Request summary state is emitted only after lifecycle execution reaches completion. | No source change; harness failure is pre-behavior. | Repair/isolate the fake or mock, then rerun; do not classify as a production regression. |
| 28 | `tests/test_v2_clip_restore_lifecycle.py::TestRequestSummaryStates::test_summary_includes_state` | Same pre-behavior fake/mock CUDA availability prohibition before summary generation. | `MOCK/HARNESS_LIMITATION` | Summary-state assertions require the worker-safe lifecycle path to run to summary publication. | No source change; harness failure is pre-behavior. | Repair/isolate the fake or mock, then rerun; do not classify as a production regression. |
| 29 | `tests/test_v2_snapshot_model_bridge.py::SnapshotDualClipSpecTests::test_duplicate_dual_workflow_key_and_spec_match` | `AssertionError`: `request key must match snapshot key for duplicate dual CLIP`; the fixture used a stale identity derivation. | `STALE_TEST_EXPECTATION` | Model identity is derived by the shared current `derive_model_key(workflow)` contract, with DualCLIP represented in the current restore key/spec. | Already-authorized stale fix: DualCLIP fixture now uses `derive_model_key(self.workflow)`. | Treat baseline failure as stale fixture drift; verify only in the owner’s next validation pass. |

The 15 rows in `MOCK/HARNESS_LIMITATION` are all
`TestCaptureExclusionFlow`, `TestEvictionReloadLifecycle`,
`TestDemandLifecycle`, `TestNoInvalidModelEscapes`, or
`TestRequestSummaryStates` failures. They fail before behavior at
`torch.cuda.is_available()` in the test fake or production probe line 4748;
the exact guard exception is `AssertionError: torch.cuda.is_available() must
not be called from preload worker`;
the baseline log also records the preload-worker guard at
`comfymodal_runtime/host_hardware_telemetry.py:972`.

The legacy assertions and fallback stale assertions are intentionally
untouched. The already-authorized stale fixes are limited to the timing
expectations (`phase_durations_ms` and current typed events) and the DualCLIP
fixture (`derive_model_key(self.workflow)`).

## Additional failures outside this 29-row baseline

The broader identity run has additional failures that must not be folded into
the 29-row accounting:

- 7 CacheDiT startup failures;
- 2 content-generation tests still asserting old MD5 behavior while the
  current shared publication generation uses SHA-256;
- 1 placement-cloud assertion observing environment `gcp`.

These are outside the requested baseline list and do not alter its exact
aggregate counts.

## Golden and deployment disposition

The Golden suite result is **277 passed / 1 skipped**. There is no known Golden
regression. The non-Golden baseline failures remain a release-gate concern:
remote deployment is **not approved** until the owner waives or resolves the
non-Golden failures.

## Evidence references

- Baseline failure list: `C:\Users\parla\AppData\Local\rtk\tee\1788125712_pytest-failures.log`.
- Baseline pytest result: `C:\Users\parla\AppData\Local\rtk\tee\1788125712_pytest.log:8157`.
- `RV1_SHARED_GOLDEN_DIAGNOSTIC_RECONCILIATION_REPORT.md:142-181` — Golden
  result, exact restore-suite baseline, and baseline failure families;
  `:205-231` — no-deploy/final disposition.
- `RA2_SNAPSHOT_RESTORE_TRUTH_AND_REPAIR_REPORT.md:152-183` — authoritative
  restore call path; `:185-217` — current timing decomposition;
  `:331-335` — local dependency incompatibility evidence.
- `RA2B_SNAPSHOT_RESTORE_CONTENT_TRUTH_REPORT.md:195-211` — restore-stage
  contract and timing evidence; `:234-247` — structural output/durability
  contract and its separation from snapshot-content classification.
- `comfymodal_runtime/modal_app.py:4748` — production GPU-allocation probe;
  `:10690` — CacheDiT startup preimport gate; `:10904`, `:13168`, `:14178`,
  and `:20532` — `phase_durations_ms` publication paths.
- `comfymodal_runtime/host_hardware_telemetry.py:951-972` — GPU identity
  probe and preload-worker guard.
- `comfymodal_runtime/restore_plan.py:226-244` — authoritative
  `derive_model_key(workflow)` contract; baseline DualCLIP failure is at
  `tests/test_v2_snapshot_model_bridge.py:354`.

`VALIDATION_OWNER=parent/orchestrator`
`TESTS_RUN_BY_THIS_REPORT=NO`
`REMOTE_DEPLOYMENT_APPROVED=NO`
