# RX7 Deployment-Failure Reconstruction Manifest

**Date:** 2026-09-01  
**Bundle root:** `artifacts/rx7_deployment_reconstruction_2026-09-01/`  
**Primary source worktree:** `.slim/worktrees/rx7`

This manifest describes the ignored raw reconstruction bundle. It is an
evidence manifest, not a deployment manifest. No secrets, tokens, or repeated
large attempt payloads are included.

## Exact bundle paths

### Inventory and index

- `artifacts/rx7_deployment_reconstruction_2026-09-01/source_inventory.json`
- `artifacts/rx7_deployment_reconstruction_2026-09-01/cohorts/cohort_index.json`
- `artifacts/rx7_deployment_reconstruction_2026-09-01/cohorts/README.txt`

`cohort_index.json` covers all 36 directories named below. Thirty-five have
source `manifest.json` and `summary.json` records represented in the compact
index; `cohort_2026-09-01_16-28-33_b6f376` is preserved as an
empty/incomplete directory entry.

### Copied `.v2ctl` files

The following paths are relative to
`artifacts/rx7_deployment_reconstruction_2026-09-01/`; they preserve the
`.v2ctl` layout from
`.slim/worktrees/rx7/.v2ctl`.

**Deployments and receipts**

- `raw/v2ctl/deployments/deploy_20260901-105209_83ec05f4.json`
- `raw/v2ctl/deployments/deploy_20260901-105947_6f1a32ac.json`
- `raw/v2ctl/deployments/deploy_20260901-112409_165997db.json`
- `raw/v2ctl/deployments/receipt_1_165997db2bd87600615524c122865b3bab06202dc0fc0dd0cb9ef5937c9cf2ae.json`
- `raw/v2ctl/deployments/receipt_1_83ec05f43a2b183f15d1adc41808072b9ba2477b1d62dcf14f074a3779cd7462.json`
- `raw/v2ctl/deployments/receipt_2_6f1a32acd2d42150c117ace4e2203867fad5023fedf76bc64579b15b1fcaa2c3.json`

**Source probes**

- `raw/v2ctl/source-probes/probe_1_165997db2bd87600615524c122865b3bab06202dc0fc0dd0cb9ef5937c9cf2ae.json`
- `raw/v2ctl/source-probes/probe_1_83ec05f43a2b183f15d1adc41808072b9ba2477b1d62dcf14f074a3779cd7462.json`
- `raw/v2ctl/source-probes/probe_2_6f1a32acd2d42150c117ace4e2203867fad5023fedf76bc64579b15b1fcaa2c3.json`

**Runs**

- `raw/v2ctl/runs/run_20260901-111653_a6d4f18b.json`
- `raw/v2ctl/runs/run_20260901-112706_b561647c.json`
- `raw/v2ctl/runs/run_20260901-113139_b561647c.json`
- `raw/v2ctl/runs/run_20260901-113543_a6d4f18b.json`

**Gates**

- `raw/v2ctl/gates/gate_20260901-162940_b561647c.json`
- `raw/v2ctl/gates/gate_20260901-163657_b561647c.json`
- `raw/v2ctl/gates/gate_20260901-163832_a6d4f18b.json`

**Confirmations**

- `raw/v2ctl/confirmations/confirm_20260901-164121_b561647c.json`
- `raw/v2ctl/confirmations/confirm_20260901-164451_a6d4f18b.json`
- `raw/v2ctl/confirmations/confirm_20260901-170438_b561647c.json`
- `raw/v2ctl/confirmations/confirm_20260901-170959_b561647c.json`
- `raw/v2ctl/confirmations/confirm_20260901-171335_a6d4f18b.json`

**RX7 logs**

- `raw/v2ctl/rx7/control-confirm-6-pytorch.log`
- `raw/v2ctl/rx7/control-confirm-6.log`
- `raw/v2ctl/rx7/control-confirm-testing7.log`
- `raw/v2ctl/rx7/control-gate-testing7.log`
- `raw/v2ctl/rx7/control-smoke-pytorch-testing7.log`
- `raw/v2ctl/rx7/control-smoke-testing7.log`
- `raw/v2ctl/rx7/doctor-after-bootstrap-timeout.log`
- `raw/v2ctl/rx7/golden-deploy-control-testing7.log`
- `raw/v2ctl/rx7/golden-deploy-static-testing7.log`
- `raw/v2ctl/rx7/golden-deploy-testing7.log`
- `raw/v2ctl/rx7/publisher-bootstrap-isolated-inherit.log`
- `raw/v2ctl/rx7/publisher-bootstrap-isolated.log`
- `raw/v2ctl/rx7/publisher-bootstrap-testing7.log`
- `raw/v2ctl/rx7/publisher-bootstrap.log`
- `raw/v2ctl/rx7/source-probe-static-testing7.log`
- `raw/v2ctl/rx7/source-probe-testing7.log`
- `raw/v2ctl/rx7/static-confirm-6-pytorch.log`
- `raw/v2ctl/rx7/static-confirm-testing7.log`
- `raw/v2ctl/rx7/static-gate-testing7.log`
- `raw/v2ctl/rx7/static-smoke-pytorch-testing7.log`
- `raw/v2ctl/rx7/static-smoke-testing7-retry.log`
- `raw/v2ctl/rx7/static-smoke-testing7.log`
- `raw/v2ctl/rx7/test-diagnostic-deploy.log`
- `raw/v2ctl/rx7/test-diagnostic-doctor.log`

The source root contains exactly 3 deployment manifests, 3 receipts, 3 source
probes, 4 runs, 3 gates, 5 confirmations, and 24 RX7 logs in these groups.

### Cohort index

The compact index at
`artifacts/rx7_deployment_reconstruction_2026-09-01/cohorts/cohort_index.json`
records all 36 current-period cohort directories discovered under
`.slim/worktrees/rx7/artifacts/phase_p1_serial_golden_v1/`. It preserves the
attempt-level identity, timing, output classification, and failure fields
needed for reconstruction. The 36 directory names are:

```text
cohort_2026-09-01_16-15-16_2bfab1
cohort_2026-09-01_16-25-43_000ad1
cohort_2026-09-01_16-28-33_a184ea
cohort_2026-09-01_16-28-33_b6f376
cohort_2026-09-01_16-31-17_6739dd
cohort_2026-09-01_16-31-51_d5f674
cohort_2026-09-01_16-36-32_1dc2b6
cohort_2026-09-01_16-37-30_c0d411
cohort_2026-09-01_16-38-54_c54cd4
cohort_2026-09-01_16-39-18_cedace
cohort_2026-09-01_16-39-56_7e0f89
cohort_2026-09-01_16-40-22_dfedeb
cohort_2026-09-01_16-41-00_8abb35
cohort_2026-09-01_16-41-33_c81fdd
cohort_2026-09-01_16-42-20_3dc1ae
cohort_2026-09-01_16-43-12_20f2c2
cohort_2026-09-01_16-43-59_32e821
cohort_2026-09-01_16-44-23_d00e1d
cohort_2026-09-01_17-02-04_e289f1
cohort_2026-09-01_17-02-30_b6229d
cohort_2026-09-01_17-02-57_b24b9b
cohort_2026-09-01_17-03-24_72208c
cohort_2026-09-01_17-03-50_aa1ed3
cohort_2026-09-01_17-04-16_56fae5
cohort_2026-09-01_17-06-15_5af272
cohort_2026-09-01_17-06-47_5b0588
cohort_2026-09-01_17-08-03_9d7245
cohort_2026-09-01_17-08-42_13d865
cohort_2026-09-01_17-09-07_3d012c
cohort_2026-09-01_17-09-35_5d96be
cohort_2026-09-01_17-10-34_0b5ea0
cohort_2026-09-01_17-10-58_c94483
cohort_2026-09-01_17-11-19_d98b45
cohort_2026-09-01_17-11-54_d1ac6e
cohort_2026-09-01_17-12-20_c9fc2a
cohort_2026-09-01_17-12-42_280411
```

The empty/incomplete directory is represented only by its index row, with no
fabricated manifest or summary.

### Copied source reports/logs

The bundle preserves copied source reports and failure-history files beneath:

- `artifacts/rx7_deployment_reconstruction_2026-09-01/raw/reports-and-logs/`

The authoritative member-to-source mapping is `source_inventory.json`; it is
deliberately used instead of inferring source membership from filenames. The
`raw/v2ctl/rx7/` log set above is separately enumerated because it is the raw
control-plane/runtime evidence set.

## Original source roots

- Primary evidence worktree: `.slim/worktrees/rx7`
- Raw control-plane records: `.slim/worktrees/rx7/.v2ctl`
- Cohort records: `.slim/worktrees/rx7/artifacts/phase_p1_serial_golden_v1`
- Source reports and logs: `.slim/worktrees/rx7` and the exact relative paths
  recorded in `source_inventory.json`

## Excluded repeated payloads

The full repeated `attempt_0.json` and `attempt_0_events.json` payloads are not
copied. They are large, repeated per-cohort payloads and do not add necessary
independent evidence beyond the cohort manifests/summaries and retained
attempt-level facts. Their original source paths are recorded in
`cohort_index.json` and/or `source_inventory.json`; no path is silently
repointed or discarded.

The compact index preserves the facts needed to distinguish exact accepted
cohorts, the nine `bfb360…` mismatch cohorts, and the empty/incomplete cohort.

## Excluded scope

- RX7A is explicitly excluded.
- RX8 was not started and is not represented as a result.
- No source, tests, config, artifacts outside the ignored reconstruction
  bundle, or deployment state are changed by this documentation task.

## Repository-safety note

Only the two repository-root markdown files named below are authored by this
task:

- `RX7_DEPLOYMENT_FAILURE_RECONSTRUCTION_2026-09-01.md`
- `RX7_DEPLOYMENT_FAILURE_RECONSTRUCTION_MANIFEST_2026-09-01.md`

The reconstruction bundle is planned under the ignored `artifacts/` path. No
commit is made, no deploy or rerun is performed, and validation remains the
orchestrator's responsibility.
