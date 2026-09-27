# RX9P-A Audit Handoff

This is an evidence index, not a success report. It does not treat the RX9P-A
report as evidence for its own claims.

## Identity

- Lane: `RX9P-A`
- Base commit before this lane: `dc94449b5161c5374a8c777011a5c3964cb15aa9`
- Implementation commit 1: `55da5390ae89f168bada5b73987aca9e542ca3d7`
- Implementation commit 2: `86be2fe93a184c132c3a714b40e0d5f23fad4989`
- Final RX9P-A implementation commit: `86be2fe93a184c132c3a714b40e0d5f23fad4989`
- Branch head when this handoff was prepared: `1bd0728` (later concurrent work;
  not part of the RX9P-A implementation range)
- Exact report: `RX9P_A_DEPLOYMENT_CONTROL_PLANE_HARDENING_REPORT_2026-09-01.md`

## Exact implementation files

The complete `dc94449..86be2fe` range contains exactly:

```text
RX9P_A_DEPLOYMENT_CONTROL_PLANE_HARDENING_REPORT_2026-09-01.md
tests/test_rx9p_a_deployment_control_plane.py
tests/test_v2ctl_locking.py
tools/v2_control/cli.py
tools/v2_control/locking.py
```

## Evidence mapping for report claims

Raw test output was printed to the terminal and not saved. Each raw-output
entry below is therefore explicitly `MISSING`; the source and test are
available in the implementation commits.

| Report claim | Source function(s) | Test(s) | Raw artifact/log proving it |
|---|---|---|---|
| `EXPLICIT_WORKSPACE_BINDING=YES` | `tools/v2_control/cli.py`: `WorkspaceBinding`, `resolve_workspace_binding`, `assert_workspace_binding_current`, `_workspace_process_environment`, `_FrozenWorkspaceBackendRunner` | `tests/test_rx9p_a_deployment_control_plane.py`: `test_explicit_workspace_and_environment_are_frozen`, `test_missing_workspace_fails_before_backend_probe`, `test_active_workspace_change_fails_before_probe`, `test_frozen_process_environment_restores_parent`, `test_gate_and_confirm_backend_wrapper_injects_frozen_environment` | `MISSING` — no persisted raw test output or remote receipt was produced |
| `PUBLISHER_PREFLIGHT=YES` | `tools/v2_control/cli.py`: `_publisher_probe`, `run_publisher_preflight`, `_verify_publisher_after_bootstrap`, `_write_publisher_preflight`, `cmd_deploy` | `test_publisher_missing_requires_bootstrap`, `test_publisher_function_missing_requires_bootstrap`, `test_require_ready_rejects_publish_required_and_unknown_generation`, `test_exact_skip_does_not_require_version_advancement` | `MISSING` — `.v2ctl/publisher_preflight` was not produced by the temporary-directory tests |
| `PUBLISHER_FUNCTION_PROOF=YES` | `tools/v2_control/cli.py`: `_publisher_function_exists`, `_publisher_probe`, `cmd_publisher_bootstrap` postflight verification | `test_unknown_function_probe_is_not_treated_as_absent`, `test_publisher_function_missing_requires_bootstrap`, `test_bootstrap_success_requires_version_advancement` | `MISSING` — no persisted mocked Modal probe transcript |
| `PUBLISHER_VERSION_PROOF=YES` | `tools/v2_control/cli.py`: `_app_version_number`, `_call_version_probe`, `_verify_publisher_after_bootstrap`, `cmd_publisher_bootstrap`, `cmd_deploy` pre/post version checks | `test_bootstrap_success_requires_version_advancement`, `test_exit_zero_without_version_advancement_fails`, `test_exact_skip_does_not_require_version_advancement` | `MISSING` — no persisted mocked version transcript |
| `STALE_LOCK_AUTORECOVERY=YES` | `tools/v2_control/locking.py`: `DeployLock.acquire`, `_acquire_interlock`, `_recover_if_proven`, `_validate_recovery_status`, `_atomic_replace`; `tools/v2_control/cli.py`: automatic `auto_recover=True` call sites | `tests/test_v2ctl_locking.py`: `TestAutomaticRecovery.test_same_owner_dead_pid_recovers_and_records_proof`, `test_auto_recovery_rejects_unproven_lock`, `test_auto_recovery_rejects_malformed_lock`, `test_auto_recovery_does_not_overwrite_or_resurrect_after_validation` | `MISSING` — no persisted raw lock-recovery log; `.v2ctl/.deploy.lock.interlock` exists but is an ignored runtime artifact, not proof of this test run |
| `REMOTE_CALLS=0` | Test scope uses injected probes and temporary paths; no source function was invoked against Modal in verification | All commands in the Verification section below | `MISSING` — no persisted invocation transcript; this claim is bounded to the recorded local commands |
| `PAID_RUNS=0` | No Golden deploy/run command was issued by this lane | All commands in the Verification section below | `MISSING` — no persisted provider/billing log |
| `READY_FOR_RX9=YES` | The preceding five control-plane source areas and tests; no additional implementation surface | Combined focused command below | `MISSING` — aggregate status was terminal-only, not a durable artifact |

## Exact test commands

Working directory for every command was the repository root:
`C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal`

Commands actually run:

```text
rtk pytest tests/test_rx9p_a_deployment_control_plane.py tests/test_v2ctl_locking.py tests/test_s1_publisher_bootstrap.py -q
rtk pytest tests/test_v2ctl_cli.py tests/test_modal_workspaces.py tests/test_modal_client_workspaces.py tests/test_modal_workspace_backend.py tests/test_v2ctl_deployment_receipt.py -q
rtk pytest tests/test_rx9p_a_deployment_control_plane.py tests/test_v2ctl_locking.py tests/test_s1_publisher_bootstrap.py tests/test_v2ctl_cli.py tests/test_modal_workspaces.py tests/test_modal_client_workspaces.py tests/test_modal_workspace_backend.py tests/test_v2ctl_deployment_receipt.py -q
python -m py_compile tools/v2_control/cli.py tools/v2_control/locking.py tests/test_rx9p_a_deployment_control_plane.py tests/test_v2ctl_locking.py
rtk pytest -q
rtk pytest -q
```

Observed terminal results:

```text
43 passed
142 passed, 2 skipped
193 passed, 2 skipped
py_compile passed
The two full-suite invocations exceeded 120 seconds and 300 seconds respectively without output.
```

Raw output paths for all six commands: `MISSING`.

Reproduction command for the final focused verification:

```powershell
rtk pytest tests/test_rx9p_a_deployment_control_plane.py tests/test_v2ctl_locking.py tests/test_s1_publisher_bootstrap.py tests/test_v2ctl_cli.py tests/test_modal_workspaces.py tests/test_modal_client_workspaces.py tests/test_modal_workspace_backend.py tests/test_v2ctl_deployment_receipt.py -q
```

## Diff and commit inspection commands

Complete RX9P-A implementation diff, excluding later concurrent commits:

```powershell
git diff --no-ext-diff --find-renames dc94449b5161c5374a8c777011a5c3964cb15aa9..86be2fe93a184c132c3a714b40e0d5f23fad4989
```

Commit/file audit:

```powershell
git show --format=fuller --stat --name-status 55da5390ae89f168bada5b73987aca9e542ca3d7
git show --format=fuller --stat --name-status 86be2fe93a184c132c3a714b40e0d5f23fad4989
git diff --name-status dc94449b5161c5374a8c777011a5c3964cb15aa9..86be2fe93a184c132c3a714b40e0d5f23fad4989
```

## Synthetic, raw, derived, and ignored artifacts

### Synthetic fixtures

- RX9P-A dedicated synthetic fixture file: `MISSING` — tests use pytest
  `tmp_path` and inline mappings; temporary directories were removed.
- `EXPERIMENT_EVIDENCE_SYNTHETIC_FIXTURE.md`: exists in the worktree but is
  RX9P-B-owned and was not used as RX9P-A evidence.

### Raw evidence

- RX9P-A test-output logs: `MISSING`.
- RX9P-A Modal/provider/receipt logs: `MISSING` — no remote calls were made.
- Context-only historical RX7 raw logs (not proof of the RX9P-A fix):
  `RA7B_REMOTE_STEP1_EVIDENCE_20260831T000000Z/02_doctor_status_predeploy.log`
  and `RA7B_REMOTE_STEP1_EVIDENCE_20260831T000000Z/03_deploy.log`.

### Derived evidence

- `RX9P_A_DEPLOYMENT_CONTROL_PLANE_HARDENING_REPORT_2026-09-01.md` — derived
  lane report; not used as proof in the mapping above.
- `.v2ctl/publisher_preflight/publisher_<safe-workspace-id>.json`: `MISSING`
  for the RX9P-A test run; real deploy output would be ignored runtime state.
- Golden deployment receipt under `.v2ctl/deployments/`: existing directory,
  but no RX9P-A receipt was produced; RX9P-A receipt evidence is `MISSING`.

### Generated/ignored state required for an operational audit

- `.modal_workspaces.json`: present and ignored; contains credentials and must
  be inspected only with secrets redacted.
- `.v2ctl/.deploy.lock.interlock`: present and ignored; runtime interlock only,
  not a historical test artifact.
- `.v2ctl/deploy.lock`: absent (`MISSING`).
- `.v2ctl/publisher_preflight`: absent (`MISSING`).
- `.pytest_cache`: absent (`MISSING`).

## Handoff commit

This file is the only file to be committed for this audit handoff. The handoff
commit SHA is intentionally recorded after the commit is created.
