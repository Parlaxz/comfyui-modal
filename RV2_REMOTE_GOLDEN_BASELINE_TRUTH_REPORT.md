# RV2 Remote Golden Baseline Truth Report

**Date:** 2026-08-30  
**Disposition:** STOPPED before a usable Golden deployment

## Executive disposition

The single canonical RV2 deployment attempt stopped at the S4 custom-node publication precondition. The publisher returned `status=ok`, but the publication was not verifiable:

```text
expected_generation=e9c604ad4d43e95a
result_generation=7fc71a1f6e08ad80
readback_generation=null
```

Per the S4 contract, this is a hard stop. It is not Golden runtime evidence and not evidence of a Golden runtime failure. No source probe, Golden request, gate, confirmation cohort, or timing measurement was run. No patch, bootstrap, second deployment, or shared-volume mutation was attempted after the stop.

Complete command output is retained in [RV2_REMOTE_GOLDEN_BASELINE_RAW_LOG.md](RV2_REMOTE_GOLDEN_BASELINE_RAW_LOG.md), including the preflight, the one deployment attempt, and post-failure status/doctor checks.

## Authority and operating contract

This lane used the current `comfy-modal-core` and `comfymodal-golden-ops` skills and treated the following as authority:

- `RV1_SHARED_GOLDEN_DIAGNOSTIC_RECONCILIATION_REPORT.md`
- `RV1B_RESTORE_SNAPSHOT_FAILURE_CLASSIFICATION.md`
- `RV1C_FINAL_LOCAL_DEPLOY_GATE_REPORT.md`
- `S4_CUSTOM_NODE_FULL_CONTENT_PUBLICATION_TRUST_REPORT.md`
- `RA2B_SNAPSHOT_RESTORE_CONTENT_TRUTH_REPORT.md`
- `RA3_CLIP_LOAD_FORWARD_TRUTH_AND_RECOVERY_REPORT.md`
- `RA6_GOLDEN_SAMPLING_DECOMPOSITION_REPORT.md`
- `RA7_DURABLE_COMMIT_VARIANCE_AND_DECOMPOSITION_REPORT.md`
- `RA8_VAE_LOAD_VARIANCE_REPORT.md`

The protected app was not used.

## Frozen attempted identity

| Field | Recorded value | Status |
|---|---|---|
| app | `batch-rv2-golden-baseline` | isolated experimental target |
| profile | `golden_p1` | selected |
| class | `ModalRuntimeEntrypointV2` | selected |
| method | `run_golden_serial_stream` | selected |
| branch / git head | `TESTING2` / `02f1845a37c7c602bb598afb7e33cab938044e99` | dirty source tree, recorded |
| deploy fingerprint | `f3d14d161578fecc66f5c39d6de9ac3095dba546f74d69ded6ff09d8d8020190` | resolver output |
| run fingerprint | `39d28da2617b67bbc732dd3cfe9891194fbade7d06da6c576607695a15554e61` | resolver output |
| profile config fingerprint | `49e0aee8f23228422962e5408c88a04a365d4fd217842ca2e41403cc1ce58b9b` | resolver output |
| GPU | `rtx-pro-6000` | selected |
| CPU / memory | `12` / `32768 MiB` | selected |
| provider / region | empty / empty | provider defaults; no usable deployment identity |
| image identity | unavailable | deployment stopped before usable image identity |
| deployment identity | unavailable | no deployment manifest created |
| snapshot identity | unavailable | no request or usable deployment |
| custom-node desired generation | `e9c604ad4d43e95a` prefix | publication gate input |
| custom-node result generation | `7fc71a1f6e08ad80` prefix | did not equal desired |
| custom-node readback generation | `null` | authoritative readback unavailable |
| workflow / model identities | unavailable | no request reached runtime |
| seed/request contract | unavailable | no request reached runtime |
| stage diagnostics | requested `COMFYMODAL_GOLDEN_STAGE_DIAGNOSTICS=1` | not remotely verified |
| sampling deep profile | requested `COMFYMODAL_SAMPLING_DEEP_PROFILE=off` | not remotely verified; no runtime existed |

The profile's configured historical expected output SHA is `8a9245...c44e`; the operational skill's canonical reference SHA is `454dbd...48da`. No output was produced, so the user-authorized warning-only output-SHA rule was not reached.

## Preflight and deployment result

Preflight status selected the intended isolated app and showed no active lock. Doctor reported the expected absence of a deployment manifest before deployment. The complete evidence is in the raw log.

The one deployment command was:

```powershell
python tools/v2ctl.py --profile golden_p1 --set COMFYMODAL_GOLDEN_STAGE_DIAGNOSTICS=1 golden deploy --app batch-rv2-golden-baseline
```

It failed closed at the canonical publication check with `publication_incomplete`. The native Modal deployment was not established as usable. Post-failure status proves:

- `deployment_manifest=None`;
- `ready=False`;
- `runtime_health_status=unverified`;
- `source_identity_status=unverified`;
- `remote_checks=not_performed`;
- the existing local deployed state still belonged to `batch-ra2-active-patcher`, not this app;
- no Golden request occurred.

## S4 publication smoke

The S4 contract requires one full semantic-content generation to agree across desired identity, publication, Volume readback, and receipt recovery. The attempted deployment did not establish that equality. The result is therefore:

- Stable publisher ownership: **expected by control-plane contract; remote proof not established**.
- Full semantic-content generation as canonical identity: **not established remotely**.
- Narrow source/deployment identity used as publication generation: **not proven from this failed invocation**.
- Publish / exact skip / receipt recovery classification: **publication incomplete**.
- Exact skip/recovery authorized by full-generation equality: **not established**.
- Deployed Golden custom-node source matching intended generation: **not established**.

`S4_REMOTE_SMOKE_COMPLETE=NO`.

## RA3, RA7, and RA8 remote evidence

No runtime was available, so none of the requested stage walls, child spans, CUDA events, page-fault deltas, pointer/storage proofs, durability ordering, or VAE overlap/reconciliation evidence exists for RV2. No summary values, distributions, Gantt charts, or causal claims are manufactured.

### RA3 CLIP

No `golden_clip_load`, `golden_clip_forward`, CLIP diagnostic events, compute-scope proof, deferred-materialization proof, or page-fault comparison was captured.

All RA3 hypotheses remain **UNPROVEN** by this lane. `RA3_REMOTE_DIAG_COMPLETE=NO`.

### RA7 durability

No output was generated. Consequently there is no `golden_durable_commit` wall, opaque `Volume.commit` call interval, reopen/readback/hash/byte-count proof, true-first-durable proof, or separate result-marker publication event.

All RA7 variance hypotheses remain **UNPROVEN** by this lane. Historical ~0.95 s and ~2.27 s observations are not mixed into an RV2 distribution. `RA7_REMOTE_DIAG_COMPLETE=NO`.

### RA8 VAE

No `golden_vae_load` wall or VAE/QD source, staging, H2D, worker wait, adoption, host-memory, page-fault, or overlap evidence was captured.

All RA8 hypotheses remain **UNPROVEN** by this lane. The prior ~105 ms versus ~290 ms variance is neither reproduced nor disproven. `RA8_REMOTE_DIAG_COMPLETE=NO`.

## RA6 sanity

The resolver selected `COMFYMODAL_SAMPLING_DEEP_PROFILE=off`. Because deployment stopped before runtime initialization, remote effective mode, absence of RA6 hooks/artifacts, and the ordinary `golden_sampling` wall were not verified. No RA6 steps/blocks run was attempted.

`RA6_DEEP_PROFILE_EFFECTIVE_MODE=off` records the requested canonical selector; it is not a claim of remote runtime observation. The clean remote A/B baseline is not available.

## Cohort and statistics

No cohort exists. Therefore no min, median, max, range, coefficient of variation, or ASCII Gantt is applicable. The requested timeline fields were not emitted because no Golden request reached runtime.

| Observation class | Count | Treatment |
|---|---:|---|
| Deployment attempts | 1 | retained; failed before usable deployment |
| Snapshot captures | 0 | none |
| Invalid request attempts | 0 | none |
| Failed Golden requests | 0 | none |
| Eligible observations | 0 | no same-deployment cohort |

## Completion decision

```text
RV2_COMPLETION=STOPPED
RV2_STOP=YES
RV2_STOP_REASON=S4_PUBLICATION_INCOMPLETE
RV2_DEPLOY_COMMAND_ATTEMPTS=1
RV2_USABLE_DEPLOYMENT=NO
RV2_SUCCESSFUL_DEPLOYMENTS=0
RV2_GOLDEN_REQUESTS=0
RV2_REMOTE_BASELINE=NOT_COMPLETED
S4_IMPLEMENTATION_COMPLETE=YES_LOCAL_ONLY
S4_REMOTE_PUBLICATION_PROOF=NOT_ESTABLISHED
VALIDATION_OWNER=ORCHESTRATOR

RV2_COMPLETE=NO
DEPLOYMENTS_PERFORMED=1
ELIGIBLE_RUNS=0
INVALID_CAPTURE_RUNS_RETAINED=0
FAILED_RUNS_RETAINED=0
SAME_DEPLOYMENT_COHORT=NO
S4_REMOTE_SMOKE_COMPLETE=NO
RA3_REMOTE_DIAG_COMPLETE=NO
RA7_REMOTE_DIAG_COMPLETE=NO
RA8_REMOTE_DIAG_COMPLETE=NO
RA6_DEEP_PROFILE_EFFECTIVE_MODE=off
RAW_LOG_COMPLETE=YES
READY_FOR_RA6_REMOTE_AB=NO
READY_FOR_RA9_DECISION=NO
REPORT=RV2_REMOTE_GOLDEN_BASELINE_TRUTH_REPORT.md
RAW_LOG=RV2_REMOTE_GOLDEN_BASELINE_RAW_LOG.md
```
