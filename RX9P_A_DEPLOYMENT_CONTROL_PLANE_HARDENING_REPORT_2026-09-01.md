# RX9P-A — Golden Deployment Control-Plane Hardening

## Scope

This lane changed only deployment/control-plane behavior: explicit Modal
workspace/environment binding, publisher admission proof, and automatic
recovery of a stale lock from the same failed owner. No Modal, GPU, paid, or
production operation was performed.

## RX7 failure mapping

### Wrong or ambiguous Modal workspace

`tools/v2_control/cli.py` now resolves a workspace from the existing
`.modal_workspaces.json` registry and freezes its safe workspace ID and
environment in `WorkspaceBinding`. Native Golden deploy, publisher bootstrap,
custom-node publication, source probe, run, gate, and confirmation paths check
the frozen binding before remote work and reject a changed active workspace or
environment. Credentials are passed only to the child/client environment and
are not printed. Deployment manifests and Golden receipts retain the frozen
workspace/environment identity.

### Publisher existence/version/publication uncertainty

`run_publisher_preflight()` performs one deterministic admission probe and
writes a structured record under `.v2ctl/publisher_preflight`. It records
workspace, environment, publisher app and Function existence, version before,
local/remote content generations, decision, bootstrap requirement, and
consumer readiness. Decisions are `skip_exact`, `publish_required`,
`bootstrap_required`, or `invalid`.

Consumer deployment is blocked when bootstrap is required or the preflight is
not ready. Bootstrap verification requires app existence, the required
`sync_custom_nodes_to_volume` Function, and a real deployment-version advance;
exit code zero alone is insufficient. Exact generation matches skip
publication without requiring fake version advancement.

The Golden path prints a compact pre-deploy card with the frozen target,
publisher proof, generations, decision, lock state, and consumer readiness.

### Same-owner stale dead-process lock blocked doctor/deploy

`DeployLock.acquire(auto_recover=True)` now replaces a lock only when its
structure is valid, owner matches the current owner, host matches this host,
and a parseable PID is definitely dead. Replacement is atomic and records
owner, PID, host, target, acquisition timestamp, death proof, and recovery
action through `last_recovery` and the warning log. A cross-platform sidecar
interlock and conditional revalidation prevent a newer/deleted lock from being
overwritten or resurrected. Foreign owners, live or ambiguous PIDs, foreign
hosts, malformed records, and uncertain probes remain fail-closed. Manual lock
acquisition still requires explicit `--force`.

Automatic recovery is enabled on publisher bootstrap, deploy, and deploy-run;
the pre-deploy card reports `RECOVERED` when it occurred.

## Verification

Focused mocked/local checks:

```text
tests/test_rx9p_a_deployment_control_plane.py tests/test_v2ctl_locking.py tests/test_s1_publisher_bootstrap.py tests/test_v2ctl_cli.py tests/test_modal_workspaces.py tests/test_modal_client_workspaces.py tests/test_modal_workspace_backend.py tests/test_v2ctl_deployment_receipt.py
193 passed, 2 skipped
```

Python compilation and the focused suite completed successfully. A separate
full-suite invocation exceeded the local five-minute command timeout without
producing a result; it was inconclusive and no remote operation was started.

EXPLICIT_WORKSPACE_BINDING=YES
PUBLISHER_PREFLIGHT=YES
PUBLISHER_FUNCTION_PROOF=YES
PUBLISHER_VERSION_PROOF=YES
STALE_LOCK_AUTORECOVERY=YES
REMOTE_CALLS=0
PAID_RUNS=0
READY_FOR_RX9=YES
