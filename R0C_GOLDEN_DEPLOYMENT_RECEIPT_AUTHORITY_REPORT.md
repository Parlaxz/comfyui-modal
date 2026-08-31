# R0C Golden Deployment Receipt Authority Report

## Decision

The host-side Golden/v2ctl control plane now uses an immutable deployment
receipt as the authority for later `run`, `source-probe`, `gate`, and `confirm`
operations. Local source/configuration drift is recorded as a warning when the
receipt remains valid; it does not replace the receipt-bound deployment
identity. Missing, corrupt, ambiguous, mismatched, or incomplete authority
data fails closed.

This report covers implementation and repository verification only. No live
Modal deployment or Golden request was performed in this lane.

## Authority contents and lifecycle

Each successful native Golden deploy persists one receipt under
`.v2ctl/deployments/`, containing:

- profile, target app/class/method, deployment version, and deploy fingerprint;
- narrowed deployed environment and effective deploy configuration;
- deployment/source identity and expected source-probe hashes;
- image identity status, workflow/model contract, and full-content S4 identity;
- the deployment manifest path and digest;
- an integrity digest over the immutable payload.

Receipt creation is exclusive and never overwrites an existing receipt.
Source-probe evidence is stored separately under `.v2ctl/source-probes/`, is
bound to the receipt integrity digest and identity, and is also immutable.
Receipt-bound source/health operations do not rewrite the manifest or receipt.

## Admission and stop-gate behavior

- `run`, `source-probe`, `gate`, and `confirm` select only a valid receipt for
  the requested profile and target.
- The current app deployment version must equal the receipt version.
- Local deploy-fingerprint drift warns and continues against the receipt;
  source-probe evidence still compares remote bytes with the receipt's stored
  expected bytes.
- Source-probe requires every required module to be `MATCH`; `MISSING`,
  `MISMATCH`, and `UNEXPECTED_PATH` are nonzero failures.
- Receipt-bound runs require successful receipt-bound source-probe evidence,
  canonical target/version/fingerprint identity, runtime diagnostics, S4,
  coldness, seriality, durability, loader/adoption, artifact, and publication
  validation. Existing production safeguards remain on the unbound path.
- Environment projection rejects host, authentication, reserved, secret-shaped,
  redacted, and untrusted keys; request metadata is not treated as deployed
  configuration.
- The Golden backend remains the single `run_golden_serial_stream` dispatch;
  there is no fallback to `run_plan_stream`.

## Repository evidence

| Check | Result |
|---|---|
| Relevant v2ctl/receipt tests | 471 passed, 0 failed, 2 skipped |
| Python compile check | passed |
| `git diff --check` for owned files | passed |
| Full `pytest tests -q` | exceeded the 120-second verification timeout; no failure result available |
| Live Modal deploy/run | not performed |

The focused test command covered the v2ctl backend, CLI, config, environment,
fingerprint, invocation, locking, profiles, provenance, registry, runtime
override, source-probe, validation, and deployment-receipt suites.

## Changed implementation surface

- `tools/v2_control/deployment_receipt.py`
- `tools/v2_control/cli.py`
- `tools/v2_control/backend.py`
- `tools/v2_control/config.py`
- `tools/v2_control/source_probe.py`
- `tools/v2_control/validation.py`
- `tests/test_v2ctl_deployment_receipt.py`
- `tests/test_v2ctl_backend.py`
- `tests/test_v2ctl_cli.py`

Other pre-existing concurrent worktree changes were preserved and are not
included in this ownership statement.

## Remaining boundary

The code and host-side contracts are verified, but the decisive runtime claim
still requires an actual Golden deploy followed by `source-probe`, then
receipt-bound single-request validation. That live operation is intentionally
not claimed by this repository-only verification.
