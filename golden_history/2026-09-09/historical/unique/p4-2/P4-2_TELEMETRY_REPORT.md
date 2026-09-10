# P4-2 Golden Snapshot — Telemetry Gate Report

**Worktree:** `C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\.slim\worktrees\p4-2-golden-snapshot-runtime`
**Branch:** `omos/p4-2-golden-snapshot-runtime` | **Base:** `8b385860824b52cf84b74f2c22bf65bbe07dcce6`
**Profile:** `golden_p1` (`stable-modal-comfy-v2-golden-p1`, `ModalRuntimeEntrypointV2::run_golden_serial_stream`)
**Date:** 2026-08-28
**Mode:** evidence-only telemetry gate (no runtime deploy, no cleanup)

## Goal

Measure true Golden pre-capture resident memory composition without conflating RSS with serialized snapshot size, then allow only evidence-backed Golden-owned slimming while improving restore attribution/determinism. Scope guard: never touch CLIP / UNET / VAE / sampling / output durability / workflow semantics / quiescence. Baseline proxy `4518584320` bytes was `process_rss_pre_capture_resident_memory_proxy`, not serialized bytes; restore baseline median ~809 ms, max 2672 ms, CV ~80% (`true_cold=false`).

## What Was Done

Closed three rounds of Oracle/auditor blockers via bounded, measurement-only telemetry:

1. **Canonical bootstrap wiring** — every V2 `RuntimeBootstrap` construction path in `comfymodal_runtime/modal_app.py` (`__init__`, `_configure_runtime` replacement, decorated V2/lazy `21323`) now wires `capture_runtime_memory` via `RuntimeBootstrap.set_runtime_memory_capture`.
2. **Lifecycle persistence** — `ModalRuntimeEntrypoint._capture_golden_runtime_memory` persists to `self._golden_runtime_memory_samples`, `self._restore_timing["golden_runtime_memory_samples"]`, and `RuntimeTrace` metadata/events; per-lifecycle reset via `_begin_golden_runtime_lifecycle`; merge at `modal_app.py:6414-6496` carries later restore `restore_session_id/restored_instance_id/trace_id/resource` with explicit precedence and deep-copied deduplicated sample lists without aliasing.
3. **Memory probe provenance** — `comfymodal_runtime/restore_state_probe.py:945-1093` now emits uniform JSON-safe schema for success/partial/error with per-field `source/status`, synchronized `rss_bytes/pss_bytes/swap_bytes` aliases, outer `status/error/extra`, and truthful `unavailable/partial` on bounded smaps (`max_mappings/max_bytes`, `byte_limit/mapping_limit`).
4. **Truthful boundaries** — distinct samples at `startup_first_line`, `after_custom_node_source_copy`, `after_custom_node_registration`, `pre_capture_quiescence`, `after_snapshot_content_proof`, `before_snapshot_capture`, `restore_first_line`, `after_cuda_runtime_initialization`, `after_restore`. Legacy `comfyapp.py` (+89 lines) remains non-canonical adapter only.
5. **Tests** — `tests/test_p4_golden_snapshot_runtime_memory.py` (16 tests) now exercises decorated `entrypoint.startup()` through `pre_capture_quiescence → after_snapshot_content_proof → before_snapshot_capture` with faked Modal/CacheDiT/quiescence/content-proof, plus schema parity, partial smaps fallback, exception, and merge tests.

## Changed Files (source-only diff)

- `comfyapp.py` | +89 (legacy gated probe calls, not canonical)
- `comfymodal_runtime/modal_app.py` | +251
- `comfymodal_runtime/restore_state_probe.py` | +1021
- `comfymodal_runtime/runtime_bootstrap.py` | +74
- `tests/test_p4_golden_snapshot_runtime_memory.py` | new (16 tests)

Generated ` .last_custom_node_context_manifest.json` / `.last_v2_dependency_cache_identity.json` restored to HEAD and excluded. `git diff --check` clean.

## Validation (direct, no subagents)

```
COMFYMODAL_LOCAL_CUSTOM_NODES=<worktree> rtk pytest -q \
  tests/test_p4_golden_snapshot_runtime_memory.py \
  tests/test_v2_snapshot_capture_hygiene.py \
  tests/test_v2_snapshot_build_manifest.py \
  tests/test_runtime_bootstrap.py \
  tests/test_v2_snapshot_restore_only.py
→ 138 passed

python -m compileall -q comfymodal_runtime → 0
rtk git diff --check → 0
python tools/v2ctl.py --profile golden_p1 --json doctor
→ control plane ok, runtime_override_policy=forbid, deploy.lock=none,
  deployment.manifest=none, no deployment performed
```

`tests/test_modal_app_identity.py` with worktree root: `137 passed, 7 failed` — all 7 fail at `modal_app.py:10505` `CacheDiT snapshot preimport FAILED: cannot import name 'cached_download' from 'huggingface_hub'` / `No package metadata was found for cache-dit` — pre-existing local `diffusers/huggingface_hub` incompatibility, predates this work, unrelated to telemetry probe (path emits only measurement).

Oracle `oracle` runner failed twice pre-execution (`FileSystem.writeFile info/exclude`); fallback `codebase-memory-auditor` (bounded, source-read-only, stale graph `2026-08-20` parent-only) initially BLOCKED on schema uniformity and `post-quiescence` coverage, then PASS-equivalent after final test-only fix (verified directly).

## Outstanding / Limitations

- No runtime deployment/shadow yet; therefore no private-memory reduction or restore-variance measurement. At least 3 valid runtime restores required before any cleanup candidate.
- No cleanup candidate implemented — P3 commit `8b38586` already proves zero tensors/parameter bytes/ModelPatcher/QD owners/readers/workers/futures; only profiler/diag payloads and generation-keyed validation state are eligible, and only after runtime composition identifies retained Golden-owned bytes.
- Local Windows cannot provide Linux `/proc` smaps/cgroup, CUDA runtime, or true snapshot capture; those fields remain honestly `unavailable/partial` locally.
- Browser snapshot fixtures omitted from worktree checkout due Windows path-length limits (tracked but not materialized).

## P4 Cross-Lane Infrastructure Issue Ledger

| ID | Category | Problem | Status | Shared? | Timing Risk | Correctness Risk | Recommended Owner |
| -- | -------- | ------- | ------ | ------- | ----------- | --------------- | ----------------- |
| P4-2-ISSUE-01 | ARTIFACT_DISCOVERY | Golden `deploy` rejects non-strict artifact discovery | unresolved control defect | probably shared P4 infrastructure | medium | high | v2ctl/backend owner |
| P4-2-ISSUE-02 | APP_IDENTITY | Required human-readable app name violates Modal slug rules | worked around | external Modal/platform | low | high | common app-name adapter |
| P4-2-ISSUE-03 | TEST_ENVIRONMENT | Worktree omitted ignored active-workspace registry | worked around | probably shared P4 infrastructure | low | high | worktree/deploy tooling |
| P4-2-ISSUE-04 | DEPLOY | Worktree omitted ignored benchmark workflow input | worked around | probably shared P4 infrastructure | low | high | worktree/deploy tooling |
| P4-2-ISSUE-05 | DEPLOY | v2ctl did not inherit local custom-node root | fixed by explicit inherit | shared P4 infrastructure | high | high | v2ctl environment policy |
| P4-2-ISSUE-06 | DEPLOY | Combined image copy auto-imported top-level helper probes | workaround pending retry | shared P4 infrastructure | high | high | image/source packaging owner |
| P4-2-ISSUE-07 | DEPLOY | Remote module reconstructed default Volume while class mounted lane Volume | fixed locally | shared P4 infrastructure | medium | high | common runtime env propagation |
| P4-2-ISSUE-08 | MODAL_PLATFORM | Aborted client left stale v2ctl deploy lock | repeated | probably shared P4 infrastructure | medium | medium | lock/timeout owner |
| P4-2-ISSUE-09 | ARTIFACT_DISCOVERY | Failed Golden startup produced no cohort path and no manifest | unresolved consequence | probably shared P4 infrastructure | high | high | Golden harness/v2ctl owner |
| P4-2-ISSUE-10 | DEPENDENCY_ENVIRONMENT | Local identity startup tests fail CacheDiT preimport | documented | lane-local environment | low | medium | dependency environment owner |
| P4-2-ISSUE-11 | TEST_ENVIRONMENT | Browser fixtures could not materialize under Windows path limits | documented | lane-local environment | low | low | worktree tooling owner |
| P4-2-ISSUE-12 | CONTROL_PLANE | Oracle review runner failed before execution on snapshot `info/exclude` write | unresolved tooling | probably shared P4 infrastructure | low | medium | agent runtime owner |
| P4-2-ISSUE-13 | DEPLOY | Nested worktree caused harness ComfyUI-root derivation to point at the wrong directory | workaround pending retry | probably shared P4 infrastructure | high | high | benchmark/v2ctl owner |
| P4-2-ISSUE-14 | GOLDEN_ROUTING | Package worktree source root produced an empty custom-node Volume and pre-dispatch missing workflow classes | workaround pending retry | probably shared P4 infrastructure | high | high | benchmark/source-root owner |
| P4-2-ISSUE-15 | DEPLOY | Nested worktree benchmark output mutated inside the Modal build context during upload | fixed in source; validation pending | shared harness/build-context boundary | high | high | benchmark artifact-root owner |
| P4-2-ISSUE-16 | DEPLOY | Installation-root packaging included mutable sibling `.slim\\worktrees` files | fixed in source; validation pending | shared custom-node packaging boundary | high | high | custom-node image owner |
| P4-2-ISSUE-17 | DEPLOY | Volume publisher recursively tarred a sibling worktree symlink/hardlink | fixed in source; validation pending | shared custom-node archive boundary | high | high | volume publisher owner |
| P4-2-ISSUE-18 | GOLDEN_ROUTING | Deploy wrapper set `golden_p1_serial` but fell through to generic `run_plan_stream` dispatch | fixed in source; validation pending | shared wrapper routing boundary | high | high | Golden wrapper owner |
| P4-2-ISSUE-19 | GOLDEN_ROUTING | Correct Golden dispatch lacked the profile expected-output SHA when invoked through `deploy-run` | fixed in source; validation pending | shared v2ctl/wrapper contract | high | high | v2ctl Golden contract owner |

### P4-2-ISSUE-01 — Golden deploy-only discovery requires strict binding

- **Category / status:** `ARTIFACT_DISCOVERY`; unresolved v2ctl defect.
- **Trigger:** `python tools/v2ctl.py --profile golden_p1 --app "Batch P4-2-snapshot-slimming" --owner p4-2-snapshot-slimming --json deploy`.
- **Expected:** deploy-only should deploy and write deployment state without requiring a Golden run cohort, or fail with an actionable mode-specific message.
- **Observed:** command failed before invocation with `ERROR: Golden artifact discovery requires canonical invocation binding` at `tools/v2_control/backend.py:1051`; `cmd_deploy()` passed `strict_canonical_discovery=False`, but Golden discovery unconditionally rejected it.
- **Reproducibility:** deterministic.
- **Scope/root cause:** probably shared P4 infrastructure; proven by source inspection of `backend.py:594-607,658-707,1029-1052`.
- **Workaround:** used canonical `deploy-run`, which requires strict binding and runs the Golden path.
- **Correctness/timing/variance:** correctness high (can block deployment); timing/variance indirect; cannot make a warm run valid, but can prevent valid deployment.
- **Permanent cleanup:** separate deploy-only artifact discovery from Golden run-cohort discovery, or make `deploy` use `capture=False`/deployment-only artifacts.
- **Evidence:** command output in session log; source lines above; `v2ctl doctor` reports no manifest after failure.

### P4-2-ISSUE-02 — Exact requested app name is invalid to Modal

- **Category / status:** `APP_IDENTITY`; worked around with `batch-p4-2-snapshot-slimming`.
- **Trigger:** `v2ctl ... --app "Batch P4-2-snapshot-slimming" deploy-run`.
- **Expected:** requested unique experimental app name should be accepted.
- **Observed:** Modal rejected `Invalid App name: 'Batch P4-2-snapshot-slimming'. Names may contain only alphanumeric characters, dashes, periods, and underscores...`.
- **Reproducibility:** deterministic.
- **Scope/root cause:** external Modal/platform; proven by Modal validation output.
- **Workaround:** confirmed by user and used slug `batch-p4-2-snapshot-slimming`; report retains requested logical name.
- **Correctness/timing/variance:** correctness high if silently normalized; timing/variance low.
- **Permanent cleanup:** v2ctl should accept a requested display name and emit/record a validated slug plus the original logical label.
- **Evidence:** deployment output showing Modal invalid-name box; no app was created for the invalid name.

### P4-2-ISSUE-03 — Ignored workspace registry absent from isolated worktree

- **Category / status:** `TEST_ENVIRONMENT`; worked around by copying the ignored registry from the main checkout without exposing credentials.
- **Trigger:** first `deploy-run` from the worktree.
- **Expected:** isolated deploy worktree should have the active workspace credentials required by the approved deploy script.
- **Observed:** `FileNotFoundError: [Errno 2] No such file or directory: '.modal_workspaces.json'`.
- **Reproducibility:** deterministic for this worktree checkout.
- **Scope/root cause:** probably shared P4 worktree/deploy infrastructure; proven by `Test-Path`: worktree false, main true, backup true.
- **Workaround/fix:** copied main ignored `.modal_workspaces.json` into the worktree; `git check-ignore` confirmed it remains ignored. No tracked file changed.
- **Correctness/timing/variance:** correctness high (no deployment); timing medium due wasted attempts; variance none.
- **Permanent cleanup:** provide a secure workspace-registry handoff for isolated worktrees or make v2ctl resolve the approved active registry without copying secrets.
- **Evidence:** deploy output; `.gitignore:34`; ignored registry paths checked without reading contents.

### P4-2-ISSUE-04 — Ignored benchmark workflow absent from worktree

- **Category / status:** `DEPLOY`; worked around by copying the existing ignored `latest_benchmark_workflow.json` from main.
- **Trigger:** retry after workspace registry was present.
- **Expected:** deploy script should find its required benchmark workflow input.
- **Observed:** `=== ERROR: Warmup profile derivation failed ===` and `benchmark workflow not found at ...\\latest_benchmark_workflow.json`.
- **Reproducibility:** deterministic for this checkout.
- **Scope/root cause:** probably shared P4 worktree/deploy infrastructure; proven by file existence checks (main true, worktree false).
- **Workaround/fix:** copied the existing workflow into the isolated worktree; no tracked file changed.
- **Correctness/timing/variance:** correctness high (blocks deploy); timing medium; variance indirect.
- **Permanent cleanup:** make required non-secret ignored inputs explicit in worktree setup and validate them in `v2ctl doctor`.
- **Evidence:** deploy output and path checks.

### P4-2-ISSUE-05 — Local custom-node root was not inherited

- **Category / status:** `DEPLOY`; fixed for this lane with `--inherit COMFYMODAL_LOCAL_CUSTOM_NODES`.
- **Trigger:** `v2ctl --profile golden_p1 --app "batch-p4-2-snapshot-slimming" ... deploy-run` without inheritance.
- **Expected:** child deployment should use the current worktree as local custom-node root.
- **Observed:** `Local custom-node root has no syncable nodes: ...\\.slim\\worktrees` while the intended root was the nested P4-2 worktree; image build then could not find the expected source context.
- **Reproducibility:** deterministic.
- **Scope/root cause:** shared v2ctl environment policy; proven by child logs and `v2ctl --dry-run` showing no `COMFYMODAL_LOCAL_CUSTOM_NODES` until explicit inheritance.
- **Workaround/fix:** set the exact worktree path and pass `--inherit COMFYMODAL_LOCAL_CUSTOM_NODES`.
- **Correctness/timing/variance:** correctness high; timing high due failed builds; variance indirect.
- **Permanent cleanup:** v2ctl should automatically bind the repository root or require-and-report the explicit source-root binding for deploys.
- **Evidence:** first deploy output; successful dry-run child environment after inheritance.

### P4-2-ISSUE-06 — Combined image copy imports helper probes as ComfyUI custom nodes

- **Category / status:** `DEPLOY`; workaround pending validation with `COMFYMODAL_CUSTOM_NODE_COPY_MODE=per_node`.
- **Trigger:** successful unique-app image deploy followed by Golden startup using default combined copy.
- **Expected:** helper source files used by the harness should not be auto-imported by ComfyUI as custom nodes.
- **Observed:** Golden startup crashed in `nodes.init_external_custom_nodes()` on `/root/comfy/ComfyUI/custom_nodes/probe_modal_health.py` (previous attempt: `probe_modal_prompt.py`) with `RuntimeError: asyncio.run() cannot be called from a running event loop`, followed by `SystemExit(2/3)`. The same image log showed `custom_node_copy_mode=combined`.
- **Reproducibility:** deterministic across two distinct helper files/attempts.
- **Scope/root cause:** probably shared P4 image/source packaging; strongly suspected/proven for combined copy because `comfyapp.py:8266-8272` copies the entire worktree into the auto-import directory, while `per_node` copies only accepted directories.
- **Workaround:** use `COMFYMODAL_CUSTOM_NODE_COPY_MODE=per_node` for this experimental deployment; do not weaken the Golden gate or edit other lanes.
- **Correctness/timing/variance:** correctness high (startup abort); timing high (wasted cold/deploy time); variance high if retries differ; invalid runs cannot be trusted as warm/non-Golden evidence.
- **Permanent cleanup:** exclude top-level helper scripts from combined custom-node image copy or make per-node copying the safe default for repository-root deployments.
- **Evidence:** remote logs supplied in session: 21:50:19 `probe_modal_prompt.py`, 22:18:21 `probe_modal_health.py`; `comfyapp.py:8266-8272`.

### P4-2-ISSUE-07 — Remote Volume handle did not match attached class Volume

- **Category / status:** `DEPLOY`; fixed locally as a shared-infrastructure blocker fix.
- **Trigger:** deploy-run with inherited `COMFYMODAL_CUSTOM_NODES_VOLUME=p4-2-snapshot-slimming-custom-nodes`.
- **Expected:** module-level `comfyapp.custom_nodes_vol` should reference the same deployment-scoped Volume attached by the V2 class.
- **Observed:** `RuntimeError: volume vo-pc7gvo9MXRPNCdcJMOjoVN not attached. Ensure volume is attached via @app.function(volumes={...})`; remote module had reconstructed the default volume because `_runtime_env()` did not propagate the custom volume name.
- **Reproducibility:** deterministic until fixed.
- **Scope/root cause:** shared P4 runtime infrastructure; proven by local `Volume.__dict__` names and source: `_register_remote_entrypoint()` mounted the inherited Volume, while `_runtime_env()` omitted `COMFYMODAL_CUSTOM_NODES_VOLUME`.
- **Fix:** `comfymodal_runtime/modal_app.py` now propagates `spec.custom_nodes_volume_name` in `_runtime_env()` and binds the legacy adapter handle in `_configure_runtime()`.
- **Tests:** local `138`-test regression remained green; no dedicated remote Volume test exists yet.
- **Correctness/timing/variance:** correctness high; timing medium; variance medium; invalid startup cannot be evidence.
- **Permanent cleanup:** merge the env propagation and add a deployment smoke test asserting attached/mounted Volume identity.
- **Evidence:** remote logs 22:01:16 and 22:09:42; `modal_app.py` `_runtime_env`, `_configure_runtime`, `_register_remote_entrypoint`.

### P4-2-ISSUE-08 — Aborted client left stale deploy locks

- **Category / status:** `MODAL_PLATFORM`/control-plane behavior; repeated after shell timeouts/user aborts.
- **Trigger:** long-running `v2ctl deploy-run` exceeding local command timeout or being aborted.
- **Expected:** lock should be released when the caller is terminated, or v2ctl should provide an unambiguous owned-lock recovery path.
- **Observed:** `v2ctl doctor` reported `deploy.lock.owner=p4-2-snapshot-slimming ... stale=1`, then later `deploy lock exists and appears stale ... pass --force`.
- **Reproducibility:** deterministic when the client is aborted; otherwise unknown.
- **Scope/root cause:** probably shared P4 control infrastructure; proven for lock persistence, root cause of process/cleanup interaction strongly suspected.
- **Workaround/fix:** verified owner/host and used `v2ctl lock force-release`; never removed another lane’s lock.
- **Correctness/timing/variance:** correctness medium (blocks future deploys); timing medium; variance low; does not make a run valid.
- **Permanent cleanup:** use a heartbeat/lease with PID liveness and expose a first-class timeout-safe cleanup path; preserve lock audit history.
- **Evidence:** `v2ctl doctor` outputs and lock commands in session.

### P4-2-ISSUE-09 — Failed Golden startup had no cohort path or manifest

- **Category / status:** `ARTIFACT_DISCOVERY`; unresolved consequence.
- **Trigger:** `deploy-run` after remote startup crash.
- **Expected:** failed attempts should preserve a bound attempt artifact/log path, even when no valid Golden result exists.
- **Observed:** v2ctl returned `ERROR: Golden backend did not identify the current cohort output directory`; deployment manifest remained absent, despite app/image deployment and detailed remote startup logs.
- **Reproducibility:** deterministic for failed startup attempts.
- **Scope/root cause:** probably shared Golden harness/artifact discovery; proven by v2ctl error and `deployment.manifest=none`; exact artifact writer behavior unknown.
- **Workaround:** preserved all remote logs supplied by Modal and recorded app/image IDs; did not treat the run as valid.
- **Correctness/timing/variance:** correctness high; timing high due inability to classify attempts; variance high if invalid attempts are omitted; no warm/non-Golden validity claim is safe.
- **Permanent cleanup:** write a failure artifact keyed by v2ctl invocation/deployment/image/request before discovery returns an error.
- **Evidence:** deployment outputs and remote logs; `v2ctl doctor` manifest none.

### P4-2-ISSUE-10 — Local CacheDiT dependency mismatch blocked identity startup tests

- **Category / status:** `DEPENDENCY_ENVIRONMENT`; documented, not fixed.
- **Trigger:** `COMFYMODAL_LOCAL_CUSTOM_NODES=<worktree> pytest -q tests/test_modal_app_identity.py`.
- **Expected:** local identity tests should reach startup assertions.
- **Observed:** `137 passed, 7 failed`; all seven failed at `modal_app.py:10505` with `cannot import name 'cached_download' from huggingface_hub` and missing `cache-dit` metadata/package.
- **Reproducibility:** deterministic in the local environment.
- **Scope/root cause:** lane-local dependency environment; proven by identical traceback and installed package paths.
- **Workaround:** ran all non-CacheDiT focused suites; did not change dependencies.
- **Correctness/timing/variance:** correctness medium for local test coverage; no deployed timing/variance claim.
- **Permanent cleanup:** pin/provision the identity-test dependency environment or skip only the unavailable integration gate with explicit status.
- **Evidence:** `C:\Users\parla\AppData\Local\rtk\tee\1787868289_pytest.log:909-959`.

### P4-2-ISSUE-11 — Windows path limits omitted browser fixtures

- **Category / status:** `TEST_ENVIRONMENT`; documented.
- **Trigger:** isolated worktree checkout.
- **Expected:** all tracked test fixtures should materialize.
- **Observed:** browser snapshot fixture paths were omitted because of Windows filename-length limits.
- **Reproducibility:** deterministic for this checkout/platform.
- **Scope/root cause:** lane-local Windows/worktree environment; proven by worktree setup record.
- **Workaround:** proceeded with non-browser tests; no fixture or source semantics changed.
- **Correctness/timing/variance:** low for this lane’s runtime evidence; browser coverage unavailable.
- **Permanent cleanup:** shorten fixture paths or enable long-path checkout support in worktree tooling.
- **Evidence:** `.slim/deepwork/p4-2-golden-snapshot-runtime.md:31`.

### P4-2-ISSUE-12 — Oracle review runner failed before execution

- **Category / status:** `CONTROL_PLANE`; unresolved agent tooling issue.
- **Trigger:** two read-only Oracle review launches.
- **Expected:** reviewer should start and return a verdict.
- **Observed:** both failed before execution with `Unknown: FileSystem.writeFile (...\\snapshot\\...\\info\\exclude)`.
- **Reproducibility:** deterministic across two retries.
- **Scope/root cause:** probably shared agent runtime; proven by identical pre-execution error and no review output.
- **Workaround:** used bounded direct source audit and local tests; did not claim an Oracle verdict.
- **Correctness/timing/variance:** review confidence/timing affected; no runtime validity effect.
- **Permanent cleanup:** fix snapshot setup error handling and provide a read-only review mode that does not require writing `info/exclude`.
- **Evidence:** task errors from the two Oracle sessions in this conversation.

### P4-2-ISSUE-13 — Harness derived the wrong ComfyUI root from nested worktree

- **Category / status:** `DEPLOY`; supported explicit-root workaround pending the next Golden run.
- **Trigger:** the successful per-node `deploy-run` reached the local benchmark harness from nested worktree `...\\custom_nodes\\comfyui-modal\\.slim\\worktrees\\p4-2-golden-snapshot-runtime` without `COMFYMODAL_V2_COMFYUI_ROOT`.
- **Expected:** harness should locate the actual ComfyUI checkout needed for registry-proof priming, or v2ctl should inject the canonical root.
- **Observed:** `[v2.harness] node_registry_init_failed error=RuntimeError: ComfyUI utils package not found at ...\\comfyui-modal\\.slim\\utils\\__init__.py`; run stopped before Golden request execution.
- **Reproducibility:** deterministic for this nested worktree when the root variable is absent.
- **Scope/root cause:** probably shared P4 worktree/benchmark infrastructure; proven by `tools/benchmark_v2_direct.py:41-52,320-329`, which uses `COMFYMODAL_V2_COMFYUI_ROOT` or a path relative to the script/repository layout.
- **Workaround:** inherit `COMFYMODAL_V2_COMFYUI_ROOT=C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI` through v2ctl; preserve registry-proof and Golden gates.
- **Correctness/timing/variance:** correctness high (blocks run); timing high; variance indirect; invalid run cannot be trusted as warm/non-Golden evidence.
- **Permanent cleanup:** make v2ctl resolve and pass the canonical ComfyUI root for nested worktrees, and have `doctor` validate it before deployment.
- **Evidence:** remote/local run output at 22:21:13; source lines above.

### P4-2-ISSUE-14 — Package worktree source root could not satisfy Golden workflow registry

- **Category / status:** `GOLDEN_ROUTING`; workaround pending the next Golden run.
- **Trigger:** successful per-node deployment followed by the required `deploy-run` benchmark execution with `COMFYMODAL_LOCAL_CUSTOM_NODES` set to the P4 package worktree.
- **Expected:** the Golden serial harness should resolve the same installed custom-node registry needed by `latest_benchmark_workflow.json` and dispatch `run_golden_serial_stream`.
- **Observed:** deployment completed, but the harness stopped before remote request dispatch with `RuntimeError: Workflow references missing custom node class(es): ['Any Switch (rgthree)', 'CacheDiT_Model_Optimizer', 'ClownOptions_ExtraOptions_Beta', 'ClownsharKSampler_Beta', 'ImpactIfNone', 'ImpactSwitch', 'JoinStrings', 'LGNoiseInjectionLatent', 'PathchSageAttentionKJ', 'SimpleMath+', 'StringToCombo|LP', 'easy float', 'easy ifElse', 'easy imageSize', 'easy indexAnything', 'easy int', 'easy stringToIntList']. Runtime repair is disabled.` Remote startup also logged `custom_node_filter ... volume_dirs=0`, confirming the deployed custom-node Volume had no source nodes for the workflow.
- **Reproducibility:** deterministic with the package worktree used as the custom-node source root.
- **Scope/root cause:** probably shared P4 source-root/harness configuration; strongly suspected/proven by the empty volume directory count, the source-root logs, and the harness’s missing-class pre-dispatch failure. The workflow requires the installation root `C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes`, not only the `comfyui-modal` package worktree.
- **Workaround:** use the existing installation `custom_nodes` root for custom-node publication and registry resolution while keeping `batch-p4-2-snapshot-slimming` and `p4-2-snapshot-slimming-custom-nodes` unique; retain runtime repair disabled.
- **Actual fix:** none yet; no source code changed for this issue.
- **Correctness/timing/variance:** correctness high (no request dispatched); timing high (deploy spend without a run); variance high if omitted as an invalid attempt; cannot make a warm/non-Golden run look valid because dispatch was refused.
- **Permanent cleanup:** v2ctl should validate that the configured source root contains every class referenced by the selected Golden workflow before deployment, and distinguish package source root from ComfyUI installation custom-node root.
- **Evidence:** 22:26:44 deploy-run output; `tools/benchmark_v2_direct.py` missing-class failure; remote `custom_node_sync_ran ... volume_dirs=0`.

### P4-2-ISSUE-15 — Live benchmark output mutated the Modal build context

- **Category / status:** `DEPLOY`; source workaround applied, deployment validation pending.
- **Trigger:** corrected source-root retry using `COMFYMODAL_LOCAL_CUSTOM_NODES=<ComfyUI>\\custom_nodes` and `COMFYMODAL_CUSTOM_NODE_COPY_MODE=per_node`.
- **Expected:** image upload should complete while the benchmark persists run artifacts independently.
- **Observed:** Modal aborted with `...\\.slim\\comfymodal-data\\benchmarks\\runs\\v2_2026-08-28_03-28-23\\run_009_sample.json was modified during build process.` The build otherwise saw `local_syncable_nodes=24` and `nodes_with_dep_files=22`, proving the source-root workaround progressed to image construction.
- **Reproducibility:** deterministic when the nested-worktree fallback is used and the benchmark runs concurrently with `modal deploy`.
- **Scope/root cause:** shared harness/build-context boundary; strongly proven by the output path being under the nested worktree's `.slim` directory and the Modal changed-file diagnostic.
- **Workaround/fix:** `tools/benchmark_v2_direct.py` now honors `COMFYMODAL_LOCAL_DATA_DIR` for all benchmark run directories; `tools/v2_control/backend.py` uses the same override for artifact discovery. The next invocation routes data to the canonical ComfyUI data root outside the deploy source tree.
- **Correctness/timing/variance:** correctness high (no Golden request accepted); timing high (24 per-node images built before abort); variance not measured.
- **Permanent cleanup:** retain one canonical artifact-root resolver for benchmark writers and v2ctl discovery; never place live run artifacts under a deploy source/build context.
- **Evidence:** 22:30:07 deploy-run output; `tools/benchmark_v2_direct.py`; `tools/v2_control/backend.py`.

### P4-2-ISSUE-16 — Installation-root packaging included mutable sibling lane worktrees

- **Category / status:** `DEPLOY`; source workaround applied, deployment validation pending.
- **Trigger:** retry after routing benchmark artifacts outside the nested worktree, with the real installation `ComfyUI\\custom_nodes` used as the source root.
- **Expected:** only production custom-node source should be uploaded.
- **Observed:** Modal aborted while uploading `...\\comfyui-modal\\.slim\\worktrees\\p4-3-golden-clip-load\\tests\\test_golden_p1_wiring.py`, reporting the file was modified during build. The same build had correctly discovered 24 nodes and 22 dependency manifests.
- **Reproducibility:** deterministic while the installation-root `comfyui-modal` directory contains active sibling worktrees and per-node packaging does not exclude `.slim`.
- **Scope/root cause:** shared custom-node packaging boundary; strongly proven by the changed path being a sibling lane under the packaged `comfyui-modal` node.
- **Workaround/fix:** add `.slim/` to the ComfyModal image ignore patterns (and the combined-root equivalent), preventing lane state, benchmark data, and sibling worktrees from entering the image.
- **Correctness/timing/variance:** correctness high (no Golden request accepted); timing high (24 image layers reached upload); variance not measured.
- **Permanent cleanup:** package only immutable production node source and keep all lane state/build metadata outside that source tree.
- **Evidence:** 22:48:06 deploy-run output; `comfyapp.py` custom-node ignore patterns.

### P4-2-ISSUE-17 — Volume publisher tarred mutable sibling worktree metadata

- **Category / status:** `DEPLOY`; source workaround applied, deployment validation pending.
- **Trigger:** retry after image-side `.slim` exclusion was added.
- **Expected:** custom-node Volume publication should archive only production custom-node contents and reject no valid source files.
- **Observed:** publication failed with `ValueError: Tar member 'comfyui-modal/.slim/worktrees/golden-p4-7b/.modal_workspaces.json' is a symlink/hardlink — not allowed`.
- **Reproducibility:** deterministic while the publisher’s recursive tar filter lacks `.slim`.
- **Scope/root cause:** shared custom-node archive boundary; strongly proven by the tar member path and the publisher’s independent exclude set.
- **Workaround/fix:** add `.slim` to the canonical `__init__` archive exclude set, the `comfyapp` fingerprint-generated-directory superset, and `tools/publish_custom_nodes_volume.py` so image, archive, and generation parity all exclude lane state.
- **Correctness/timing/variance:** correctness high (Volume publication rejected before remote run); timing high (image build completed, publication failed); variance not measured.
- **Permanent cleanup:** keep all worktree/control-plane state outside the recursively archived production node tree; preserve the three-way exclude-set parity test.
- **Evidence:** 23:25:04 deploy-run output; `__init__.py`, `comfyapp.py`, and `tools/publish_custom_nodes_volume.py` exclude sets.

### P4-2-ISSUE-18 — Deploy wrapper fell through from Golden mode to generic dispatch

- **Category / status:** `GOLDEN_ROUTING`; source fix applied, validation pending.
- **Trigger:** `v2ctl deploy-run --profile golden_p1` invoking `deploy_and_run_v2_single.bat golden_p1`.
- **Expected:** after deployment/preflight, the wrapper must invoke `tools\\benchmark_v2_direct.py --golden-p1`, whose remote method is `run_golden_serial_stream`.
- **Observed:** the wrapper set `V2_BENCHMARK_MODE=golden_p1_serial`, but its dispatch chain had no `golden_p1_serial` branch. It fell through to the generic fallback at the end of the chain, invoking `benchmark_v2_direct.py` without `--golden-p1`, which routes through `run_plan_stream`.
- **Reproducibility:** deterministic for deploy-wrapper Golden invocations before this fix.
- **Scope/root cause:** shared wrapper routing boundary; strongly proven by the mode assignment and missing dispatch branch.
- **Workaround/fix:** added an explicit `golden_p1_serial` branch that strips only the leading selector and invokes `--golden-p1`; added static wiring coverage so both wrappers must preserve the dedicated flag.
- **Correctness/timing/variance:** correctness invalid (generic run is not Golden evidence); timing high (remote work spent on the wrong method); variance not measured.
- **Permanent cleanup:** centralize Golden selector-to-command routing or keep equivalent branches in both wrappers covered by one contract test.
- **Evidence:** `deploy_and_run_v2_single.bat` lines 68 and 1136-1286; `run_v2_single.bat` lines 541-554; prior `run_plan_stream` execution output.

### P4-2-ISSUE-19 — Deploy-run omitted the Golden expected-output contract

- **Category / status:** `GOLDEN_ROUTING`; source fix applied, validation pending.
- **Trigger:** corrected deploy-wrapper Golden branch invoked by `v2ctl deploy-run`.
- **Expected:** the Golden profile's strict expected PNG SHA must reach `benchmark_v2_direct.py` so a matching durable output can be accepted.
- **Observed:** the run correctly used `method=run_golden_serial_stream`, but its manifest recorded `expected_output_sha: ""`; all five attempts failed closed with `no expected output SHA configured` despite observing SHA `454dbda2939f4abadabd8ca6c524d3a615f384ce19873faf5adaf4693c1848da`.
- **Reproducibility:** deterministic for Golden `deploy-run` before this fix.
- **Scope/root cause:** shared v2ctl/wrapper contract; strongly proven by the profile configuration already containing the SHA while `cmd_deploy_run` forwarded only the positional selector.
- **Workaround/fix:** `cmd_deploy_run` now appends `_validation_backend_args(config)` for `golden_p1`, forwarding `--run-count 1` and the profile SHA through the wrapper to `--golden-p1`.
- **Correctness/timing/variance:** correctness invalid only because admission metadata was omitted; timing high (five full Golden executions completed); variance not accepted.
- **Permanent cleanup:** centralize profile-to-backend argument construction so deploy-run and run-only cannot diverge.
- **Evidence:** cohort `cohort_2026-08-28_04-58-23_058c15/manifest.json`, `tools/v2_control/cli.py`, and `tests/test_v2ctl_cli.py`.

## Shared-Infrastructure Changes Made by This Lane

- `comfymodal_runtime/modal_app.py`: propagated deployment-scoped custom-node Volume name into remote class environment and rebound the legacy adapter’s Volume handle to the attached V2 resource. **Recommended:** merge globally; this is a correctness blocker for every lane using isolated Volumes.
- `comfymodal_runtime/modal_app.py`: canonical memory telemetry callback wiring, lifecycle metadata persistence/merge, and truthful boundary capture. **Recommended:** retain/merge as shared telemetry infrastructure after remote validation; not a stage optimization.
- `comfymodal_runtime/restore_state_probe.py`: uniform resident-memory composition/provenance schema. **Recommended:** retain as diagnostic-only shared infrastructure, but audit footprint after runtime measurement and downscope heavy mappings if unnecessary.
- `tests/test_p4_golden_snapshot_runtime_memory.py`: regression coverage for the above. **Recommended:** merge with telemetry implementation.
- `comfyapp.py`: legacy probe additions are non-canonical and should be **discarded after P4** unless another lane proves that path is required. They were not used as the V2 evidence path.
- Deployment invocation workaround: explicit `--inherit COMFYMODAL_LOCAL_CUSTOM_NODES`, `--inherit COMFYMODAL_CUSTOM_NODES_VOLUME`, copied ignored registry/workflow inputs, and `COMFYMODAL_CUSTOM_NODE_COPY_MODE=per_node`. **Recommended:** replace with common v2ctl/worktree setup; retain per-node packaging as the safe default for repository-root deployments if confirmed.

## Next Steps (gated)

1. `python tools/v2ctl.py --profile golden_p1 deploy` then `deploy-run` / `run` to collect ≥3 restores with `golden_runtime_memory_samples` and `restore_total_ms` / `restore_deep` decomposition.
2. Compare RSS/PSS/USS/private/file-backed/smaps categories at startup → registration → CUDA init → pre-capture → after-restore; attribute platform-controlled vs app-owned spans.
3. Propose one Golden-owned cleanup at a time, re-verify `138` + structural Golden + composition delta, re-gate with Oracle/auditor before screening.

## Repro

```powershell
Set-Location "C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\.slim\worktrees\p4-2-golden-snapshot-runtime"
$env:COMFYMODAL_LOCAL_CUSTOM_NODES=(Get-Location).Path
rtk pytest -q tests/test_p4_golden_snapshot_runtime_memory.py tests/test_v2_snapshot_capture_hygiene.py tests/test_v2_snapshot_build_manifest.py tests/test_runtime_bootstrap.py tests/test_v2_snapshot_restore_only.py
python -m compileall -q comfymodal_runtime
rtk git diff --check
python tools/v2ctl.py --profile golden_p1 --json doctor
python tools/v2ctl.py --profile golden_p1 --json config | Select-Object -First 80
```
