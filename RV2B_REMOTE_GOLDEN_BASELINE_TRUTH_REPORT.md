# RV2B Remote Golden Baseline Truth Report

## Decision

RV2B is complete. Five eligible true-cold observations were collected
serially from one frozen Modal deployment/version. No optimization was
performed. The configured expected PNG SHA mismatch was retained as the
authorized warning-only condition: every attempt was otherwise structurally
valid, durable, reopened and verified, and serial.

## Authority and deployment

S4B was verified before measurement and remains closed. Its historical
full-content generation was
`f4c12e9b7573fb5d45d0a4b5a83fa33dccc788f6ff07edf859055588ae8f1014` with
matching desired, publisher, committed Volume readback and receipt records.
The current deployment performed a verified publication of the current
full-content generation
`e4671089280ad6cc1558b1859baec58f6fa5f22e1ba74bdb6b8e55c208b7fa58`.
The cohort is bound to this current deployment generation and does not mix
historical deployment versions.

| item | value |
|---|---|
| app | `batch-rv2b-golden-measurement` |
| target | `ModalRuntimeEntrypointV2.run_golden_serial_stream` |
| profile | `golden_p1` |
| deployment number | 3 for this app/campaign |
| v2ctl deployment fingerprint | `3afb957ba2e1275eddca2be82b9dfe54fcf0b80c77f66d8fdab1478436d765d9` |
| Modal deployment/version identity | `aaba80156dc559e591fc7379836991059f7ecc31b107875b0635de94e8ac9a48` |
| image | `im-kgisSW1st7TzVVWiuyOwvJ` |
| deployment manifest | `.v2ctl/deployments/deploy_20260830-215842_3afb957b.json` |
| profile/config fingerprint | `e869f612a019b0b7046eb4d0acd5cbb321a959ddaebdf3afa4524bc739bb2358` |
| run fingerprint | `2b2bd68996a2b73d6ee8c2294f20c81eda7ca839082ef5b512417becb2ad04c3` |
| GPU | `rtx-pro-6000` |
| source probe | `PASS / MATCH`; remote class and source modules matched |
| S4 current publication generation | `e4671089280ad6cc1558b1859baec58f6fa5f22e1ba74bdb6b8e55c208b7fa58` |
| diagnostics | `COMFYMODAL_GOLDEN_STAGE_DIAGNOSTICS=1` |
| sampling deep profile | `COMFYMODAL_SAMPLING_DEEP_PROFILE=off` |

Deployment manifest effective environment proves diagnostics `1` and deep
profiling `off`. The first request and all four following request manifests
carry the same effective values. The first request emitted the complete
Golden stage set plus CLIP, VAE, durability and result-marker events, proving
that diagnostics were active in the remote runtime rather than only selected
locally.

The local registry/profile metadata was not used as a runtime gate. A narrow
one-off host admission bypass supplied the stored deployment and run
identity and allowed the same deployed surface to execute; runtime validators,
target, durability, seriality, coldness and artifact validation were not
bypassed. Local Git drift after deployment is recorded as a warning only.

## Canonical sequence and accounting

Preflight status and doctor, deployment, source probe, post-deploy status and
post-deploy doctor were preserved. Deployment #3 returned transport success,
source probe matched, and its manifest carried the effective diagnostic
configuration. The stale local status after restoring host bookkeeping is not
used as runtime evidence.

The request sequence was five separate single-request invocations. No
`SNAPSHOT_CAPTURE` event occurred; every capture guard was idle and every
request was true-cold. Two local PowerShell/Python quoting failures occurred
before the first backend request; they are retained in the raw log and are
not Golden attempts or failed remote runs.

| counter | value |
|---|---:|
| deployment command attempts | 3 |
| transport-successful deployments | 3 |
| eligible replacement deployment | #3 |
| backend Golden requests | 5 |
| capture-invalid requests retained | 0 |
| directly-following invalid requests retained | 0 |
| failed Golden runs retained | 0 |
| eligible runs | 5 |
| same-deployment cohort | YES |
| production app touched | NO |

All five attempts have `valid=true`, `dnf=false`, `true_cold=true`,
`restore_count=1`, `request_count=1`, one request ID, true durable result,
reopen verification, commit-before-reopen ordering, zero seriality
violations, completed teardown, and validated provenance. All observed output
SHA values were
`bfb360008914dbacbe594b22dc09fd2b7658fa4d63ed7c25364806ce0b2280ce`; the
configured expected value differed and was recorded only as a warning.

## Runtime identities and models

The runtime deployment identity, image, snapshot identity
`c4a6e18929b61ff6e463d59d3cc1c640b9064c209c912413cf5092772fb713ab`, and
config identity `66908100ca42525c09e7c1522f750785dc34957c269488dfaa29497ba9d79f14`
were identical across all five attempts. The runtime workflow hash was
`e44389ea2eda82ba5e2328acc08307b6879ed6d4ea4b030727ab044704c0d3b5` in all
five request identities. The local campaign manifest also contains a stale
input hash `14f815f1916e075ae79de7325681f6b0ec2216b8ad86c45e9bfa18f6388f5ea9`;
the runtime request's actual and expected hashes matched and are the cohort
authority.

The CLIP was `qwen_3_4b.safetensors`, type `lumina2`; selected Qwen compute
scope was `qwen3_4b.transformer.model`. VAE telemetry reports 244 float32
parameters and 335,278,732 source/H2D bytes. A checkpoint name for the UNET
was not emitted by the Golden artifact schema; its dynamic patcher/adoption
proof is present in every attempt. Snapshot proof reported no retained model
weights or model patchers.

## Five-run authoritative wall table

All values are milliseconds. `Golden restore -> teardown` is the relevant
Golden wall from the first Golden stage boundary through teardown. `Python ->
true durable` uses the recorded remote Python-resume wall and the first true
durable result boundary. Provider/region are runtime-selected per request and
do not change the deployment/version identity.

| run | provider / region | external restore | restore | setup | CLIP load | CLIP forward | UNET load | sampler prepare | VAE load | sampling | tail | decode | output | durable | teardown | Python/resume -> true durable | Golden restore -> teardown | backend request |
|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | AWS / us-east-2 | 1420.019 | 4.602 | 2.300 | 3552.975 | 2426.741 | 5565.893 | 307.595 | 535.583 | 5689.258 | 0.014 | 684.477 | 214.686 | 1041.859 | 0.249 | 21832.587 | 20027.969 | 62277.478 |
| 2 | GCP / us-west1 | 1338.529 | 4.291 | 1.185 | 1273.686 | 1273.474 | 1907.662 | 158.329 | 92.617 | 5253.376 | 0.010 | 500.477 | 168.041 | 1833.185 | 0.224 | 14154.156 | 12468.333 | 22188.101 |
| 3 | AWS / us-east-2 | 1082.076 | 5.525 | 3.105 | 1803.373 | 2060.000 | 2030.812 | 324.018 | 232.046 | 5619.835 | 0.015 | 601.330 | 211.171 | 774.737 | 0.220 | 15306.431 | 13668.022 | 20438.250 |
| 4 | GCP / us-west1 | 965.274 | 3.609 | 1.346 | 1512.919 | 1454.382 | 1927.175 | 233.706 | 108.842 | 5463.582 | 0.014 | 544.687 | 184.701 | 1306.947 | 0.245 | 14207.589 | 12744.195 | 19395.284 |
| 5 | GCP / us-east1 | 754.707 | 4.891 | 3.981 | 1372.133 | 1542.970 | 1598.201 | 207.445 | 116.276 | 5585.380 | 0.014 | 559.687 | 170.395 | 1011.675 | 0.239 | 13324.038 | 12175.604 | 17740.764 |

### Five-run statistics

| stage | min | median | max | range | sample CV |
|---|---:|---:|---:|---:|---:|
| external restore | 754.707 | 1082.076 | 1420.019 | 665.312 | 0.245 |
| Golden restore | 3.609 | 4.602 | 5.525 | 1.916 | 0.155 |
| CLIP load | 1273.686 | 1512.919 | 3552.975 | 2279.289 | 0.496 |
| CLIP forward | 1273.474 | 1542.970 | 2426.741 | 1153.267 | 0.273 |
| UNET load | 1598.201 | 1927.175 | 5565.893 | 3967.692 | 0.638 |
| VAE load | 92.617 | 116.276 | 535.583 | 442.966 | 0.859 |
| sampling | 5253.376 | 5585.380 | 5689.258 | 435.882 | 0.031 |
| durable commit | 774.737 | 1041.859 | 1833.185 | 1058.448 | 0.339 |
| Python/resume -> true durable | 13324.038 | 14207.589 | 21832.587 | 8508.549 | 0.220 |
| Golden restore -> teardown | 12175.604 | 12744.195 | 20027.969 | 7852.365 | 0.232 |
| backend request | 17740.764 | 20438.250 | 62277.478 | 44536.714 | 0.669 |

These are descriptive n=5 statistics only. The first request is a large
backend-wall outlier; the authoritative Golden-stage decomposition identifies
where its measured stage time occurs without attributing the remaining
backend wall to a specific hidden service phase.

## ASCII Gantt charts

Scale: one `█` is approximately 200 ms. Bars are visual guides; the numeric
authoritative walls above are the source of truth.

### Run 1 — Golden wall 20027.969 ms

```text
golden_restore         █ 4.602 ms
golden_request_setup   █ 2.300 ms
golden_clip_load       ██████████████████ 3552.975 ms
golden_clip_forward    ████████████ 2426.741 ms
golden_unet_load       ████████████████████████████ 5565.893 ms
golden_sampler_prepare ██ 307.595 ms
golden_vae_load        ███ 535.583 ms
golden_sampling        ████████████████████████████ 5689.258 ms
golden_sampler_tail    █ 0.014 ms
golden_vae_decode      ███ 684.477 ms
golden_output          █ 214.686 ms
golden_durable_commit  █████ 1041.859 ms
golden_teardown        █ 0.249 ms
```

### Run 2 — Golden wall 12468.333 ms

```text
golden_restore         █ 4.291 ms
golden_request_setup   █ 1.185 ms
golden_clip_load       ██████ 1273.686 ms
golden_clip_forward    ██████ 1273.474 ms
golden_unet_load       ██████████ 1907.662 ms
golden_sampler_prepare █ 158.329 ms
golden_vae_load        █ 92.617 ms
golden_sampling        ██████████████████████████ 5253.376 ms
golden_sampler_tail    █ 0.010 ms
golden_vae_decode      ███ 500.477 ms
golden_output          █ 168.041 ms
golden_durable_commit  █████████ 1833.185 ms
golden_teardown        █ 0.224 ms
```

### Run 3 — Golden wall 13668.022 ms

```text
golden_restore         █ 5.525 ms
golden_request_setup   █ 3.105 ms
golden_clip_load       █████████ 1803.373 ms
golden_clip_forward    ██████████ 2060.000 ms
golden_unet_load       ██████████ 2030.812 ms
golden_sampler_prepare ██ 324.018 ms
golden_vae_load        █ 232.046 ms
golden_sampling        ████████████████████████████ 5619.835 ms
golden_sampler_tail    █ 0.015 ms
golden_vae_decode      ███ 601.330 ms
golden_output          █ 211.171 ms
golden_durable_commit  ████ 774.737 ms
golden_teardown        █ 0.220 ms
```

### Run 4 — Golden wall 12744.195 ms

```text
golden_restore         █ 3.609 ms
golden_request_setup   █ 1.346 ms
golden_clip_load       ████████ 1512.919 ms
golden_clip_forward    ███████ 1454.382 ms
golden_unet_load       ██████████ 1927.175 ms
golden_sampler_prepare █ 233.706 ms
golden_vae_load        █ 108.842 ms
golden_sampling        ███████████████████████████ 5463.582 ms
golden_sampler_tail    █ 0.014 ms
golden_vae_decode      ███ 544.687 ms
golden_output          █ 184.701 ms
golden_durable_commit  ███████ 1306.947 ms
golden_teardown        █ 0.245 ms
```

### Run 5 — Golden wall 12175.604 ms

```text
golden_restore         █ 4.891 ms
golden_request_setup   █ 3.981 ms
golden_clip_load       ███████ 1372.133 ms
golden_clip_forward    ████████ 1542.970 ms
golden_unet_load       ████████ 1598.201 ms
golden_sampler_prepare █ 207.445 ms
golden_vae_load        █ 116.276 ms
golden_sampling        ████████████████████████████ 5585.380 ms
golden_sampler_tail    █ 0.014 ms
golden_vae_decode      ███ 559.687 ms
golden_output          █ 170.395 ms
golden_durable_commit  █████ 1011.675 ms
golden_teardown        █ 0.239 ms
```

## RA3 — CLIP load and forward

The authoritative CLIP load walls were 3552.975, 1273.686, 1803.373,
1512.919 and 1372.133 ms. Every run reported the same selected scope:

- device `cuda:0`; dtype `torch.bfloat16`;
- storage identity proven and compute-ready true;
- 398 selected Qwen tensors, 240 source reads and 8,044,936,192 completed H2D bytes;
- dynamic patcher/adoption/publish handoff proven; owner retained;
- QD worker waits: workers joined, H2D events waited, copies complete and operation not live;
- one outer scalar, `qwen3_4b.logit_scale`, 4 bytes on CPU.

The CPU scalar is an outer extra and does not classify the selected Qwen
compute scope as CPU. The actual pointer value is not emitted, but same-storage
and storage-proof fields are true. Event order proves QD owner creation,
patcher construction, adoption, publication and quiescence.

The artifact records source-read count and completed H2D bytes, but does not
provide separate authoritative header/layout, staging-allocation,
CPU-to-pinned, H2D enqueue, CUDA-event transfer time/throughput, or worker
wait walls. Those fields are explicitly unavailable rather than inferred.

CLIP forward was encoded successfully in every run. Walls were 2426.741,
1273.474, 2060.000, 1454.382 and 1542.970 ms. Conditioning packaging was
completed by the Golden path; cache status was `not_used`. Deferred forward
materialization and repeated-cast work were `UNPROVEN` in every artifact.
Page-fault tracking was disabled (`COMFYMODAL_V2_PAGEFAULT_TRACKING=0`), so
stage/first-compute page-fault deltas and any page-residency correlation are
unavailable. No causality is inferred from the restore/page-residency data.

RA3 classifications:

- selected Qwen compute on CPU: **DISPROVEN**;
- CLIP-load variance has a supported observed outlier, but its internal cause:
  **UNPROVEN**;
- deferred materialization or repeated casts as the forward cause:
  **UNPROVEN**;
- page faults as a cause: **UNPROVEN**;
- meaningful causal correlation from this cohort: **UNPROVEN**.

## RA8 — VAE load

VAE load walls were 535.583, 92.617, 232.046, 108.842 and 116.276 ms. Every
run reported:

- 244 parameters, final device `cuda:0`, dtype `torch.float32`;
- 10 source reads, 335,278,732 source bytes and identical completed H2D bytes;
- VAE QD owner creation, dynamic patcher identity and 244/244 same-storage adoption;
- zero copied storage and complete worker/event quiescence.

Separate header/layout, staging allocation count/time, staging reuse/retention,
prior CLIP/UNET staging state, source throughput, CPU-to-pinned time, H2D
enqueue/CUDA-event time, RSS, memlock, allocator and page-fault observations
were not emitted by this configuration. Overlap/union is therefore only
bounded by the serial stage ordering; its component timings are unavailable.

The historical approximately 105 ms versus 290 ms pattern did not reproduce
as a clean two-level split. This cohort ranged from 92.617 to 535.583 ms,
including one 535.583 ms outlier and one 232.046 ms observation.

No measured component tracks VAE wall variance: source-read count/bytes and
H2D bytes are constant, while the needed component sub-times are absent.
This is a measurement limitation, not a causal claim.

| RA8 hypothesis | classification | evidence |
|---|---|---|
| fresh approximately 256 MiB staging allocation/page-lock | **UNPROVEN** | allocation/page-lock telemetry absent |
| retained approximately 512 MiB CLIP+UNET staging | **UNPROVEN** | retained-staging and prior-stage residency telemetry absent |
| source I/O | **UNPROVEN** | reads/bytes are constant, but source sub-time is absent |
| H2D | **UNPROVEN** | H2D bytes are constant, but transfer sub-time is absent |
| event/wait behavior | **UNPROVEN** | quiescence is proven, wait duration is absent |
| construction/adoption | **UNPROVEN** | adoption is constant and successful, construction timing is absent |
| host/page-fault conditions | **UNPROVEN** | RSS/memlock/page-fault telemetry was not enabled |

The shared QD staging pool was not implemented.

## RA7 — durability

All five attempts prove real ordering: asset write, `golden_durable_commit`,
opaque blocking `Volume.commit`, return-to-reopen, reopen/open, stat, readback,
readback SHA-256, byte-count verification, close/finalize, then the separate
true-durable result-marker publication. The durable content SHA and byte count
were verified on reopen. No server-side `Volume.commit` subphases were
invented.

| run | pre-bookkeeping | Volume.commit call | return -> reopen | reopen open | stat | readback | readback SHA | byte/content | close/finalize | result marker |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 2.482 | 1027.817 | 6.390 | 0.486 | 0.031 | 2.258 | 2.015 | 0.006 | 0.033 | 0.004 |
| 2 | 0.705 | 1826.074 | 1.974 | 0.218 | 0.019 | 1.274 | 2.574 | 0.005 | 0.034 | 0.004 |
| 3 | 2.041 | 764.019 | 2.688 | 1.714 | 0.034 | 2.029 | 1.879 | 0.004 | 0.032 | 0.003 |
| 4 | 0.780 | 1300.565 | 1.911 | 0.226 | 0.028 | 1.390 | 1.678 | 0.006 | 0.037 | 0.003 |
| 5 | 0.985 | 1004.942 | 2.039 | 0.276 | 0.036 | 1.329 | 1.677 | 0.006 | 0.034 | 0.003 |

The `Volume.commit` call is the span that explains the observed durability
variance: min 764.019 ms, median 1027.817 ms, max 1826.074 ms, range
1062.055 ms, sample CV 0.343. The surrounding reopen/readback/verification
spans are small by comparison. This is **SUPPORTED**, not proof of a hidden
server-side cause; `Volume.commit` remains opaque. No durability optimization
was performed.

## RA6 sanity

The deployment and every invocation carried `COMFYMODAL_SAMPLING_DEEP_PROFILE=off`.
Every attempt emitted ordinary `golden_sampling`; no blocks arm, steps hook or
deep sampling profile event was active. The sampling wrapper event identifies
the ordinary Golden sampling runner, not the RA6 blocks arm. RA6 A/B was not
run in this lane.

## Raw evidence

`RV2B_REMOTE_GOLDEN_BASELINE_RAW_LOG.md` contains the prior stop evidence, the
replacement2 registry-admission attempt, replacement3 preflight/deployment and
direct invocation logs, all local command failures, the deployment manifest,
all five v2ctl run manifests, cohort manifests, attempt artifacts, event
streams, summaries and provenance siblings. The generated raw log was checked
after assembly; complete artifact files are retained in their original paths.

Primary evidence directories:

- `RV2B_REMOTE_MEASUREMENT_RAW_EVIDENCE_20260830T000000Z`
- `RV2B_REMOTE_MEASUREMENT_RAW_EVIDENCE_20260830T000000Z_REPLACEMENT2`
- `RV2B_REMOTE_MEASUREMENT_RAW_EVIDENCE_20260830T000000Z_REPLACEMENT3`

Eligible attempt artifacts:

- `artifacts/phase_p1_serial_golden_v1/cohort_2026-08-31_03-03-36_41efe9/`
- `artifacts/phase_p1_serial_golden_v1/cohort_2026-08-31_03-05-53_a835fa/`
- `artifacts/phase_p1_serial_golden_v1/cohort_2026-08-31_03-07-06_a774f5/`
- `artifacts/phase_p1_serial_golden_v1/cohort_2026-08-31_03-08-20_450e13/`
- `artifacts/phase_p1_serial_golden_v1/cohort_2026-08-31_03-09-19_ea74e7/`

## No optimization and readiness

No shared staging pool, transfer dispatcher, cast-once path, CLIP/UNET
overlap, `empty_cache` change, page touch/prewarm, durability optimization,
sampler/attention/CacheDiT change, or snapshot/runtime redesign was performed.

The baseline is ready for a separately controlled RA6 remote A/B. The RA9
decision can use this baseline, but the evidence does not prove that a shared
pool will improve VAE variance; RA9 implementation remains deferred.

```text
RV2B_COMPLETE=YES
DEPLOYMENTS_PERFORMED=3
ELIGIBLE_RUNS=5
INVALID_CAPTURE_RUNS_RETAINED=0
FAILED_RUNS_RETAINED=0
SAME_DEPLOYMENT_COHORT=YES
S4_REMOTE_SMOKE_CONFIRMED=YES
RA3_REMOTE_DIAG_COMPLETE=YES
RA7_REMOTE_DIAG_COMPLETE=YES
RA8_REMOTE_DIAG_COMPLETE=YES
RA6_DEEP_PROFILE_EFFECTIVE_MODE=off
RAW_LOG_COMPLETE=YES
READY_FOR_RA6_REMOTE_AB=YES
READY_FOR_RA9_DECISION=YES
REPORT=RV2B_REMOTE_GOLDEN_BASELINE_TRUTH_REPORT.md
RAW_LOG=RV2B_REMOTE_GOLDEN_BASELINE_RAW_LOG.md
```
