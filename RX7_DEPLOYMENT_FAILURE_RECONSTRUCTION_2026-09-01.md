# RX7 Deployment-Failure Reconstruction

**Date:** 2026-09-01  
**Scope:** RX7 / E27 only. RX7A is excluded; RX8 was not started.  
**Primary evidence worktree:** `.slim/worktrees/rx7`  
**Validation owner:** orchestrator

## Conclusion

The RX7 sequence had real control-plane, publication, and harness failures, but
it ultimately produced accepted deployments and accepted runs. The static E27
aggregate winner is supported by the direct final cohort records. That result
does **not** establish a mechanism-level source-QD occupancy or source-wall
win: those fields are `null` in the final runtime artifacts. The exact accepted
A/B result is bounded by this artifact set and must not be generalized beyond
this cohort.

The static E27 arm is accepted for this comparison. The six accepted static
runs and six accepted dispatcher-control runs are valid, true-cold, exact,
single-request results with zero DNF, fallback, and seriality violations.

## Evidence boundary and identity note

**Direct raw artifact evidence** consists of the `.v2ctl` manifests, receipts,
source probes, run records, gates, confirmations, and the cohort
`manifest.json`/`summary.json` records in the primary worktree. The copied
reconstruction bundle contains the complete `.v2ctl` set plus a compact
per-cohort index; its exact contents are recorded in
`RX7_DEPLOYMENT_FAILURE_RECONSTRUCTION_MANIFEST_2026-09-01.md`.

**Aggregate-report claims** are treated as corroboration, not as a substitute
for the raw records. In particular, the aggregate report says that all twelve
final runs are valid, true-cold, exact, and free of DNF/fallback/seriality
violations; the direct final cohort summaries corroborate those fields.

There is an identity discrepancy that is not, by itself, evidence of failure:
the local deployment fingerprints are static E27
`6f1a32acd2d42150c117ace4e2203867fad5023fedf76bc64579b15b1fcaa2c3` and
dispatcher control
`165997db2bd87600615524c122865b3bab06202dc0fc0dd0cb9ef5937c9cf2ae`, while
the source-probe runtime deployment identity begins `8e3ccfeb`. The source
probe independently reports `RESULT=PASS`, `source_identity=MATCH`, remote
image `im-CVXSh71EM5xCs0DJ25bNli`, and class `ModalRuntimeEntrypointV2`.

## Frozen experiment identity

| Item | Value |
|---|---|
| Workspace | Testing 7 (`ws_eaef96004dac`) |
| Profile | `golden_p1` |
| GPU | `rtx-pro-6000` |
| Backend | explicit `pytorch` |
| Class / method | `ModalRuntimeEntrypointV2` / `run_golden_serial_stream` |
| Workflow SHA | `14f815f1916e075ae79de7325681f6b0ec2216b8ad86c45e9bfa18f6388f5ea9` |
| Expected output SHA | `8a92446890bebaecdc10eb5f207766a4b05af40ca3137108e25bfe88d9c1c44e` |
| Historical published generation | `2853bea2379ad48b85b54f9d10ae01677bded3191b0a85bd53cbd246eb47ebe2` |
| Control deployment | `rx7-e27-control`; `165997db…` |
| Static deployment | `rx7-e27-static`; `6f1a32ac…` |

## Chronological ledger

| Time / phase | Event | Result and interpretation |
|---|---|---|
| Before the final deploys | Publisher bootstrap, diagnostics, and doctor checks | Bootstrap reported `Local custom-node root has no syncable nodes`; a publisher success did not advance the deployment version. A diagnostic deploy reported a missing `sync_custom_nodes_to_volume` Function and publisher app not found. Doctor reported a stale deploy lock. |
| 15:52Z | Static legacy deploy `83ec05f43a2b…` | Deploy exit `0`; a valid recorded deployment attempt, not proof that publication/runtime identity was fully reconciled. |
| 15:59Z | Static E27 deploy `6f1a32acd2d4…` | Deploy exit `0`. Exact-match publication was skipped; the earlier published generation remained `2853bea…`. |
| 16:15Z | First current-period mismatch observation | `cohort_2026-09-01_16-15-16_2bfab1` observed output SHA `bfb360008914dbacbe594b22dc09fd2b7658fa4d63ed7c25364806ce0b2280ce` despite a warning-only `valid=true` summary. It is not silently classified as exact. |
| 16:24Z | Dispatcher-control deploy `165997db2bd8…` | Deploy exit `0`; this became the control identity for the final comparison. |
| 16:25–16:44Z | Further early current-period cohort observations | Two further observed output SHA mismatches used `bfb360008914dbacbe594b22dc09fd2b7658fa4d63ed7c25364806ce0b2280ce` despite warning-only `valid=true` summaries. The `16-28-33_b6f376` directory is empty/incomplete. These are not silently classified as exact. |
| 17:02–17:04Z | Final pre-acceptance mismatch observations | Six further cohorts observed the same `bfb360…` SHA mismatch with warning-only `valid=true` summaries. They were excluded from the exact accepted cohort. |
| During smoke/gate setup | Static smoke attempt | Initial smoke could not identify the cohort output and raised `FileNotFoundError` for the current cohort output directory. The retry succeeded. |
| After deployment/probe checks | Source and acceptance checks | Source probe passed. Smoke, gate, and confirmation records reported `valid=1`; confirmation logs warned that local deploy identity had drifted and instructed binding the immutable remote receipt. Deploy logs warned about unregistered explicit flags. |
| 17:06:15–17:09:35Z | Six control confirmation cohorts | Six exact final control cohorts accepted. |
| 17:10:34–17:12:42Z | Six static E27 confirmation cohorts | Six exact final static cohorts accepted. The profile was restored to baseline `legacy`; no deploy followed measurement. |

## Deployment-failure taxonomy

1. **Publication/version advancement:** the publisher could report success
   while the deployment version did not advance; exact-match E27 publication
   was skipped and the prior generation remained authoritative.
2. **Publisher/bootstrap reachability:** the local custom-node root was
   reported as having no syncable nodes; a diagnostic path could not find the
   sync Function or publisher app.
3. **Lock/state hygiene:** doctor found a stale deployment lock.
4. **Harness/observability:** the first static smoke looked for a missing
   current-cohort output directory and raised `FileNotFoundError`; the retry
   completed successfully.
5. **Identity binding:** confirmations warned of local deployment identity
   drift and required binding the immutable remote receipt. This explains an
   evidence-reconciliation concern, not an automatic runtime failure.
6. **Flag registration:** deploy logs warned that explicit flags were
   unregistered. This is an operational/configuration warning, not evidence
   that the accepted final runs failed.
7. **Output correctness classification:** the nine `bfb360…` cohorts were
   warning-only `valid=true` observations but had a SHA mismatch. They remain
   noncanonical and are excluded from the accepted exact cohort.

## What changed between attempts

- The operational comparison moved from the static legacy deployment to the
  static E27 deployment and then to the dispatcher control deployment; no
  source-code change is asserted by this reconstruction.
- Publication was not treated as authoritative merely because a publisher
  command returned success. The historical published generation and immutable
  deployment receipts were retained as separate identities.
- The failed first static smoke was retried after the cohort-output lookup
  problem; the retry produced usable evidence.
- Acceptance was narrowed to six exact final cohorts per arm. Earlier
  warning-only SHA-mismatch cohorts and the empty/incomplete directory were
  retained as evidence but excluded from the A/B winner.
- The final source probe and gates were required before confirmation. The
  profile was restored to `legacy` after confirmation, with no post-measurement
  deploy.

## Accepted deployment and cohort identities

| Arm | Run fingerprint | Deployment identity | Accepted cohort directories |
|---|---|---|---|
| Dispatcher control | `b561647cab3ae1c5dbadd71ee1e132251a2f2757a700f20a4cc9b4b82f3bf581` | `165997db2bd87600615524c122865b3bab06202dc0fc0dd0cb9ef5937c9cf2ae` | `17-06-15_5af272`, `17-06-47_5b0588`, `17-08-03_9d7245`, `17-08-42_13d865`, `17-09-07_3d012c`, `17-09-35_5d96be` |
| Static E27 | `a6d4f18b7a9a348f2f5fafdb9477b9ac5a3a1ef89ab025c7baddab2bf9a7937b` | `6f1a32acd2d42150c117ace4e2203867fad5023fedf76bc64579b15b1fcaa2c3` | `17-10-34_0b5ea0`, `17-10-58_c94483`, `17-11-19_d98b45`, `17-11-54_d1ac6e`, `17-12-20_c9fc2a`, `17-12-42_280411` |

The full source-relative paths are under
`artifacts/phase_p1_serial_golden_v1/` in the primary worktree and are copied
under the reconstruction bundle named in the manifest.

## Run summary

All twelve accepted runs are reported by the final summaries and aggregate
report as valid, true-cold, exact, one-terminal-result executions with zero
DNF, zero transport fallback, and zero seriality violations.

### Total request duration (ms)

| Arm | Six durations | Mean | Median |
|---|---|---:|---:|
| Dispatcher control | 29311.277, 74754.025, 36579.626, 23822.577, 25659.068, 24006.175 | 35688.791 | 27485.173 |
| Static E27 | 20204.488, 19806.117, 32825.490, 23551.067, 20204.805, 52563.720 | 28192.615 | 21877.936 |

Static E27 is 20.4% lower on median total duration and 21.0% lower on mean.
The selected stage medians also show a mixed result: CLIP load, UNet load,
VAE load, sampling, and output were lower for static, while CLIP forward was
13.9% higher. This is not a universal stage-by-stage improvement.

The static scheduling records report four producer IDs `[0, 1, 2, 3]`, four
contiguous regions covering `8,044,936,192` source bytes, 32 MiB QD4 blocks,
complete source/H2D reconciliation, zero fallback, monotonic offsets, and
quiescence before bind/forward. Control reports the same source total and four
producers with dynamic regions. Static has 243 reads versus control's 240
because its four fixed boundaries add three boundary reads; planned and
completed bytes reconcile in both arms.

## Noncanonical mismatch observations

The following nine current-period cohorts observed
`bfb360008914dbacbe594b22dc09fd2b7658fa4d63ed7c25364806ce0b2280ce` rather
than the expected output SHA. Their summaries may say `valid=true` with a
warning, but they are not exact and are excluded from the accepted result:

- `cohort_2026-09-01_16-15-16_2bfab1`
- `cohort_2026-09-01_16-25-43_000ad1`
- `cohort_2026-09-01_16-28-33_a184ea`
- `cohort_2026-09-01_17-02-04_e289f1`
- `cohort_2026-09-01_17-02-30_b6229d`
- `cohort_2026-09-01_17-02-57_b24b9b`
- `cohort_2026-09-01_17-03-24_72208c`
- `cohort_2026-09-01_17-03-50_aa1ed3`
- `cohort_2026-09-01_17-04-16_56fae5`

`cohort_2026-09-01_16-28-33_b6f376` is empty/incomplete and is also excluded.

## Evidence gaps and limits

- The compact index preserves cohort-level facts from the primary-worktree
  `manifest.json`/`summary.json` records, but repeated `attempt_0.json` and
  `attempt_0_events.json` payloads are not copied; their original paths are
  recorded in the bundle inventory/index.
- Mechanism-level source-QD occupancy and source-wall fields are `null` in the
  final runtime artifacts. The accepted result therefore supports the
  observed end-to-end A/B result, not a causal QD occupancy claim.
- The local deployment fingerprint versus remote runtime identity discrepancy
  remains an identity-reconciliation limitation. It is not independently a
  failure classification because the source probe passed and final cohort
  records are valid.
- The evidence covers RX7/E27 only. It says nothing about RX7A or RX8.

## Copied-artifact pointer

The planned raw bundle is
`artifacts/rx7_deployment_reconstruction_2026-09-01/`. Its exact file list,
source roots, exclusions, and repository-safety constraints are in
`RX7_DEPLOYMENT_FAILURE_RECONSTRUCTION_MANIFEST_2026-09-01.md`.

## No-code / no-rerun statement

This reconstruction changes no source, tests, configuration, or runtime
artifacts and performs no deploy, run, smoke, gate, or confirmation rerun. It
is documentation-only; validation remains owned by the orchestrator.
