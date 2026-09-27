# V2 Batch E10 Phase-E Integration A/B

Date: 2026-08-16
Status: E10_BUCKET_FIRST_REPRO_CHECK_STRUCTURAL_FAILURE
Commit: none

## Scope

Phase-E staged safetensors integration was deployed through the canonical
`.bat` wrappers and exercised with exactly one initial full workflow request per
arm. Provider and region were intentionally left unpinned. After the initial B
failure, B was repaired and validated with B-only requests; one fresh A/B pair
was then attempted. The pair was stopped before any performance claim because
its validity gates failed.

## Arm Configuration

| Arm | App | Staged transport | Staged settings | CLIP staged hydration | E5 bypass | D15 |
|---|---|---:|---|---:|---:|---:|
| A | `stable-modal-comfy-v2-restore-only-shadow` | off | canonical baseline | off | off | on |
| B | `stable-modal-comfy-v2-restore-only-staged-shadow` | on | 4 producers, 1024 MiB pool, 256 MiB buckets, CPU cast on, async H2D on, contiguous GPU buckets on | on | on | on |

The intended pair used D10 integration validation, the same GPU request
(`rtx-pro-6000`), 12 CPUs, 32768 MiB memory, runtime-shape fingerprint
`f504e296c398bdcb2c4c07e2`, workflow hash `2e43d4c0ba3b82c0`, and a fresh
conditioning-cache nonce. The initial request artifacts were later found to
have the D10 fast-path flags off; the corrected D10/staged profile is recorded
under Repair Validation. The E1 local safety result authorized contiguous GPU
buckets for B.

## Deployment Evidence

| Arm | Deployment identity | Image | Placement observed |
|---|---|---|---|
| A | `stable-modal-comfy-v2-restore-only-shadow` | `im-Bx2RzTZeX6JJb9oJHoRowr` | `CLOUD_PROVIDER_GCP/us-east1` |
| B | `stable-modal-comfy-v2-restore-only-staged-shadow` | `im-zDmnlLU3joXNryNXpg2WxW` | `CLOUD_PROVIDER_GCP/us-east4` |

Both deploy logs reported `region=unpinned cloud=unpinned`. Modal selected
different regions, so the provider/region-equality gate failed. These values are
recorded observations, not deployment pins.

## Request Evidence

Artifacts:

- A: `comfymodal-data/benchmarks/runs/v2_2026-08-16_23-14-05/run_0.json`
- B: `comfymodal-data/benchmarks/runs/v2_2026-08-16_23-19-42/run_0.json`

| Gate | A | B |
|---|---:|---:|
| Fresh structural identity | PASS, `restore_count=1`, `request_count=1` | PASS, `restore_count=1`, `request_count=1` |
| Output SHA-256 | `20b10e1f99831bc758d9df82f43ce0beb1cbc636a740d11a29eb2bffe90e5260` | same |
| Readiness gate | `6343.407 ms` | `7317.086 ms` |
| Command without scheduling | `17736 ms` | `20732 ms` |
| Waterfall reconciliation | `OK` | `OK` |

`MODEL_READINESS_GATE` was internally consistent in both arms:
`MODEL_READINESS_GATE_AT = max(CLIP_READY_AT, UNET_READY_AT)`, with UNET as the
gating model. D15 evidence was present as `coordination=CLIP_GPU_CRITICAL_ACTIVE`.

## Failed Gates

B did not satisfy the no-fallback requirement:

- CLIP staged hydration emitted `ok=false` with
  `clip_staged_fallback_reason=RuntimeError: staged result contained no tensor state dicts`.
- UNET staged transport emitted `fallback_count=1` with
  `unet_staged_fallback_reason=RuntimeError:staged_result:native_pin_budget_unavailable:`.
- Both staged H2D and bind timings were null after fallback.

The observed B readiness metric regressed by `973.679 ms` versus A. Command
without scheduling regressed by approximately `16.9%` (`20732 ms` versus
`17736 ms`). Because the staged path fell back, placement differed, and the
performance gates failed, no success or causal performance claim is valid.

## Repair Validation

The first post-deploy B retry was excluded from structural evidence:

- Artifact: `comfymodal-data/benchmarks/runs/v2_2026-08-16_23-37-49/run_0.json`
- Its effective environment had `COMFYMODAL_V2_UNET_FASTSAFETENSORS=0`,
  `COMFYMODAL_V2_CLIP_FAST_HYDRATION=0`, and
  `COMFYMODAL_V2_CLIP_SNAPSHOT_EXCLUDE_WEIGHTS=0`; it did not exercise the
  requested D10/staged profile.

B was then redeployed with D10 plus the requested staged profile. The final
B-only structural artifact was:

- `comfymodal-data/benchmarks/runs/v2_2026-08-16_23-54-30/run_0.json`

| Gate | B repair result |
|---|---:|
| Effective D10/staged profile | PASS |
| Fresh structural identity | PASS, `restore_count=1`, `request_count=1` |
| Output SHA-256 | `20b10e1f99831bc758d9df82f43ce0beb1cbc636a740d11a29eb2bffe90e5260` |
| CLIP staged path | PASS, fallback empty |
| CLIP staged timings | prepare `110.350 ms`, commit `3871.242 ms`, H2D `3539.356 ms`, bind `85.522 ms` |
| UNET staged path | PASS, `staged_transport=true`, fallback empty |
| UNET staged timings | prepare `102.583 ms`, commit `3497.694 ms`, H2D `3470.029 ms`, bind `6.109 ms` |
| Native pin budget | unavailable; local bounded pool used; rejected `false` |
| Peak pinned pool | `1073741824` bytes |
| Contiguous GPU buckets | PASS |

The CLIP H2D telemetry mapping was corrected to publish
`h2d_device_ms`/`h2d_enqueue_ms` as `clip_staged_h2d_ms`. Focused validation
then passed with `52 passed, 10 subtests passed`.

## Fresh Pair Attempt

The fresh pair used D10 on both arms, staged transport off for A and on for B,
one shared nonce, identical runtime shape, and unpinned placement:

- A: `comfymodal-data/benchmarks/runs/v2_2026-08-17_00-00-21/run_0.json`
- B: `comfymodal-data/benchmarks/runs/v2_2026-08-17_00-06-02/run_0.json`

| Gate | A | B |
|---|---:|---:|
| Fresh structural identity | PASS, `1/1` | PASS, `1/1` |
| Output SHA-256 | same expected SHA | same expected SHA |
| Placement | `CLOUD_PROVIDER_GCP/asia-south1` | `CLOUD_PROVIDER_GCP/us-east1` |
| Conditioning cache | `miss_stored` | `exact_hit`, CLIP encode skipped |
| Readiness gate | `5727.106 ms` | `4797.442 ms` |
| Command without scheduling | `30065 ms` | `17958 ms` |

The pair is invalid for causal comparison. Modal selected different regions,
and the shared conditioning-cache nonce allowed B to reuse A's shared-volume
entry, so B did not perform a fresh CLIP staged hydration in this pair. The
timing values are recorded observations only and must not be interpreted as a
staged performance result.

## Validation

```text
python -m pytest -q tests/test_v2_staged_safetensors_core.py tests/test_v2_e2_clip_staged_hydration.py tests/test_v2_e3_unet_staged_transport.py tests/test_v2_batch_e5_empty_cache_bypass.py tests/test_v2_batch_d15_critical_gpu_lane_coordination.py
52 passed, 10 subtests passed
```

## Packed Host-Bucket Transport Fix

The transport rewrite was deployed through the canonical
`deploy_and_run_v2_single.bat` path and validated with exactly one cold B
request through `run_v2_single.bat`.

Implementation:

- The existing contiguous GPU layout remains the sole packed owner/layout.
- Packed mode now walks that layout once, fills reusable pinned slabs, and
  queues one H2D operation per packed destination window.
- Tensor ranges crossing a window are split by byte range; alignment gaps are
  not exposed through views and are not bulk-zeroed.
- Four reusable slabs remain bounded by the configured 1 GiB pool cap.
- Slab reuse remains event-protected on the single CUDA copy stream.
- `host_slab_is_pinned_all` and per-slot pin checks are allocation-time API
  evidence; an unconfirmed or false result fails closed before publication.
- Per-bucket CUDA timing is summed as `h2d_dma_busy_ms`; the compatibility
  `h2d_device_ms` value is retained and exposed as `h2d_stream_span_ms`.
- Packed bucket work is partitioned into balanced, disjoint ranges across the
  configured producer workers; positional GPU destinations keep delivery order
  independent of producer completion order.
- Packed final-bucket telemetry uses the greatest destination offset rather than
  queue arrival order.

### Local Validation

The focused suite covers tiny multi-tensor buckets, tensor boundary crossing,
multiple crossings, final partial buckets, alignment gaps, exact packed CUDA
views and owner retention, event-protected slab reuse, the four-slab hard cap,
pin failure fallback, bucket-count scaling, StageResult cleanup, E2, E3, E5,
and D15 compatibility.

```text
python -m pytest -q tests/test_v2_staged_safetensors_core.py tests/test_v2_e2_clip_staged_hydration.py tests/test_v2_e3_unet_staged_transport.py tests/test_v2_batch_e5_empty_cache_bypass.py tests/test_v2_batch_d15_critical_gpu_lane_coordination.py
65 passed, 10 subtests passed
python -m py_compile comfymodal_runtime/staged_safetensors.py comfymodal_runtime/clip_fast_hydration_wiring.py comfymodal_runtime/unet_fastsafetensors.py tests/test_v2_staged_safetensors_core.py
PASS
git diff --check -- touched E10 files
PASS
```

The local producer-feed follow-up is covered by a balanced partition test, a
configured-worker dispatch test, and the CUDA packed-view parity test. It keeps
the existing four-slab pool, one-copy-stream contract, and event-protected slab
reuse unchanged. A concurrent pool-wait counter update was also made under the
pool condition lock. The remote B artifact below predates this follow-up and
must not be used as post-fix performance evidence.

### Baseline Remote B Validation (Before Producer Parallelism)

Artifact:

- `comfymodal-data/benchmarks/runs/v2_2026-08-17_00-53-37/run_0.json`

Request nonce: `6aafbecd-84fe-466e-b2b5-f6618a32c268`

| Gate | Result |
|---|---:|
| App / class | `stable-modal-comfy-v2-restore-only-staged-shadow` / `ModalRuntimeEntrypointV2` |
| Fresh structural identity | PASS, `restore_count=1`, `request_count=1`, `Fresh=YES` |
| Conditioning cache | PASS, `decision=miss_stored`, `encode_calls=1` |
| Canonical output SHA | PASS, `20b10e1f99831bc758d9df82f43ce0beb1cbc636a740d11a29eb2bffe90e5260` |
| CLIP staged / fallback | `YES` / none |
| UNET staged / fallback | `YES` / none |
| Contiguous GPU owner | active, one packed owner |
| Residual meta tensors | `0` |
| Host slabs | `4`, all slots `true` |
| Peak pinned pool | `1073741824` bytes |
| Provider / region | `CLOUD_PROVIDER_GCP` / `us-east1` |
| Command without scheduling | `34990.852 ms` (`34.991 s`) |

### Packed Transport Telemetry

| Field | CLIP | UNET |
|---|---:|---:|
| packed model bytes | `8044936192` | `12309817472` |
| checkpoint bytes | `8044982048` | `12309866400` |
| exact-copy bytes | `8044936192` | `12309817472` |
| CPU-cast bytes | `0` | `0` |
| configured host bucket | `268435456` | `268435456` |
| H2D bucket count | `30` | `46` |
| full bucket count | `29` | `45` |
| final bucket bytes | `260307968` | `230221952` |
| min / median / max H2D bytes | `260307968 / 268435456 / 268435456` | `230221952 / 268435456 / 268435456` |
| H2D enqueue ms | `4836.003` | `5378.285` |
| commit ms | `5245.594` | `6150.131` |
| H2D stream span ms | `4835.307` | `5389.756` |
| H2D DMA busy ms | `188.125` | `242.773` |
| H2D stream idle estimate ms | `4647.182` | `5146.983` |
| H2D DMA GB/s | `39.8269` | `47.2228` |
| H2D span GB/s | `1.5495` | `2.1271` |
| producer wait ms | `0.0` | `0.0` |
| consumer wait ms | `4020.0` | `4420.0` |
| slab reuse wait ms | `0.0` | `0.0` |
| H2D copy calls | `30` | `46` |
| tensor count | `398` | `453` |

The expected O(model-bytes / 256 MiB) submission property is proven. The
large stream-idle estimates, zero slab-reuse waits, and multi-second
`disk_to_stage_ms` values show that the copy stream is usually waiting for the
single bounded packer/file-staging producer. DMA is not the dominant measured
cost in this B request.

`MODEL_READINESS_GATE` was not emitted by this request artifact. The source
contains per-model `model_ready_wall_unix_ns` timestamps, but the exact gate
baseline/event needed for the exposed readiness metric is absent, so
`B_MODEL_GATE_MS=UNKNOWN` rather than an inferred value.

### E5 Secondary Evidence

The request emitted `soft_cache_reason=model_management_soft_empty_cache`.
The first load-model soft-cache sequence executed `empty_cache` with
`empty_cache_ms=0.009` and `soft_empty_cache_total_ms=0.919`; later cleanup
sequences are separately recorded, including a `936.784 ms` empty-cache
operation. No `empty_cache_bypass_decision` event was emitted and the bypass
flag was not present in the effective request environment, so the bypass
decision is `UNKNOWN` rather than inferred.

### Decision

The real packed host-bucket primitive is implemented and structurally healthy
remotely. The existing B request predates the local producer-feed fix, so its
stream-starvation values are baseline evidence only. Issue one canonical
deployment and one cold B validation to measure the follow-up. Do not run an
A+B pair unless that fresh B has complete readiness-gate telemetry and passes
all structural checks.

```text
E10_LOCAL_FEED_PARALLELIZED_REMOTE_RETRY_PENDING
PACKED_HOST_BUCKETS_IMPLEMENTED=YES
HOST_SLAB_IS_PINNED_ALL=YES
CLIP_BYTES=8044936192
CLIP_H2D_BUCKET_COUNT=30
CLIP_MEDIAN_COPY_BYTES=268435456
CLIP_DMA_BUSY_MS=188.125
CLIP_STREAM_SPAN_MS=4835.307
CLIP_STREAM_IDLE_MS=4647.182
CLIP_DMA_GBPS=39.8269
CLIP_SPAN_GBPS=1.5495
UNET_BYTES=12309817472
UNET_H2D_BUCKET_COUNT=46
UNET_MEDIAN_COPY_BYTES=268435456
UNET_DMA_BUSY_MS=242.773
UNET_STREAM_SPAN_MS=5389.756
UNET_STREAM_IDLE_MS=5146.983
UNET_DMA_GBPS=47.2228
UNET_SPAN_GBPS=2.1271
PINNED_POOL_PEAK=1073741824
CPU_CAST_BYTES_CLIP=0
CPU_CAST_BYTES_UNET=0
B_MODEL_GATE_MS=UNKNOWN (model_readiness_gate event absent)
B_NO_SCHEDULING_S=34.991
B_STRUCTURALLY_VALID=YES
E5_SOFT_CACHE_REASON=model_management_soft_empty_cache
E5_BYPASS_DECISION=UNKNOWN (decision event absent; bypass flag not requested)
E5_EMPTY_CACHE_EXECUTED=YES
E5_EMPTY_CACHE_MS=0.009 first load-model sequence; later cleanup 936.784
A_B_PAIR_PERFORMED=NO
A_NONCE=NOT_RUN
B_NONCE=6aafbecd-84fe-466e-b2b5-f6618a32c268
NONCES_DIFFERENT=NOT_APPLICABLE
PROVIDER_A=NOT_RUN
REGION_A=NOT_RUN
PROVIDER_B=CLOUD_PROVIDER_GCP
REGION_B=us-east1
PLACEMENT_MATCH=NOT_APPLICABLE
A_MODEL_GATE_MS=NOT_RUN
B_PAIR_MODEL_GATE_MS=NOT_RUN
MODEL_GATE_DELTA_MS=NOT_COMPARABLE
PHASE_E_RESULT=E10_REMOTE_BUCKETED_TRANSPORT_VALIDATED_STREAM_STARVATION
NEXT_STEP=one canonical deploy plus one cold B validation; no remote A/B yet
LOCAL_TESTS=65 passed, 10 subtests passed; py_compile and diff checks passed
MODAL_DEPLOYS=1
MODAL_REQUESTS=1
DIRECT_PYTHON_REMOTE_INVOKE_USED=NO
COMMIT=none
```

The canonical `run_v2_single.bat` restore-only branch was minimally corrected
to forward CLI arguments, allowing the fresh nonce/suffix to reach the
benchmark harness. No direct Python remote invocation was used. No commit was
created.

### Post-Fix Remote B Validation

The local producer-feed fix was deployed once through the canonical wrapper as
`stable-modal-comfy-v2-restore-only-staged-shadow`, image
`im-cooEa5IsndTUfnq8HJ5mAQ`, with D10 and the staged profile active. A
preliminary `snapshot_restore_only` probe was valid but intentionally had
`graph_executed=false`; it is excluded from transport evidence. The one normal
graph request used a fresh conditioning nonce and produced:

- Artifact: `comfymodal-data/benchmarks/runs/v2_2026-08-17_01-19-22/run_0.json`
- Request: `v2-benchmark-0-c7bb2367f0fc`
- Nonce: `d4e8f6a1-71b0-4cc7-8d5f-6b31d9c42a7e`
- Fresh identity: PASS, `restore_count=1`, `request_count=1`
- Output SHA: PASS, `20b10e1f99831bc758d9df82f43ce0beb1cbc636a740d11a29eb2bffe90e5260`
- Placement: `CLOUD_PROVIDER_GCP/us-east4`, unpinned
- CLIP and UNET staged paths: PASS, fallback empty
- Host slabs: 4, every slot pinned; peak pool `1073741824` bytes
- H2D shape: CLIP 30 buckets, UNET 46 buckets; both median copies
  `268435456` bytes

| Metric | Baseline B | Post-fix B |
|---|---:|---:|
| CLIP H2D stream span ms | `4835.307` | `3831.382` |
| CLIP H2D DMA busy ms | `188.125` | `258.855` |
| CLIP stream idle estimate ms | `4647.182` | `3572.527` |
| CLIP consumer wait ms | `4020.0` | `2650.0` |
| UNET H2D stream span ms | `5389.756` | `3656.188` |
| UNET H2D DMA busy ms | `242.773` | `295.460` |
| UNET stream idle estimate ms | `5146.983` | `3360.728` |
| UNET consumer wait ms | `4420.0` | `2680.0` |

The producer feed improved materially, but the copy stream remains mostly idle
because whole-tensor reads still precede bucket publication. UNET producer
slab-reuse wait was `8502.689 ms`, showing the four workers now reach the
bounded pool instead of leaving the consumer starved. The remote sample's
`exact_copy_bytes` overcounted tensors crossing producer partitions; a local
follow-up now records each tensor's transfer bytes once. That accounting fix
does not alter the positional H2D copies or their measured timings and was not
remotely redeployed.

`MODEL_READINESS_GATE` and `empty_cache_bypass_decision` were absent from this
artifact, so `B_MODEL_GATE_MS=UNKNOWN` and `E5_BYPASS_DECISION=UNKNOWN`. No A
arm or A+B pair was run. Stop remote experimentation until the readiness-gate
telemetry is restored; a future remote run should redeploy the accounting fix
only if exact transfer-byte telemetry is required.

```text
E10_REMOTE_FEED_PARALLELIZED_VALIDATED
PACKED_HOST_BUCKETS_IMPLEMENTED=YES
PACKED_PRODUCER_WORKERS=4
HOST_SLAB_IS_PINNED_ALL=YES
CLIP_H2D_BUCKET_COUNT=30
CLIP_MEDIAN_COPY_BYTES=268435456
CLIP_DMA_BUSY_MS=258.855
CLIP_STREAM_SPAN_MS=3831.382
CLIP_STREAM_IDLE_MS=3572.527
UNET_H2D_BUCKET_COUNT=46
UNET_MEDIAN_COPY_BYTES=268435456
UNET_DMA_BUSY_MS=295.460
UNET_STREAM_SPAN_MS=3656.188
UNET_STREAM_IDLE_MS=3360.728
B_STRUCTURALLY_VALID=YES
B_MODEL_GATE_MS=UNKNOWN
E5_BYPASS_DECISION=UNKNOWN
A_B_PAIR_PERFORMED=NO
MODAL_DEPLOYS=1
MODAL_REQUESTS=2 (one restore-only structural probe, one normal graph request)
DIRECT_PYTHON_REMOTE_INVOKE_USED=NO
COMMIT=none
NEXT_STEP=STOP remote; restore MODEL_READINESS_GATE telemetry before any A/B
```

### Post-Bucket-First Remote B Validation

The bucket-first exact source-fill follow-up was deployed once through the
canonical `deploy_and_run_v2_single.bat` path and exercised with exactly one
normal cold B request through `run_v2_single.bat`. This is the authoritative
post-fix artifact:

- Artifact: `comfymodal-data/benchmarks/runs/v2_2026-08-17_01-44-24/run_0.json`
- Request: `v2-benchmark-0-7a2e7440782b`
- Nonce: `01091575-1dda-4622-bbfc-6228a45fc1ed`
- Deployment image: `im-w6b9tTm5YMwMu7PbScFTzI`
- Placement: `CLOUD_PROVIDER_AWS/us-east-1`, unpinned
- This validation accounting: `MODAL_DEPLOYS=1`, `MODAL_REQUESTS=1`

#### Structural Gates

| Gate | Result |
|---|---|
| Fresh structural identity | PASS, `restore_count=1`, `request_count=1`, `fresh=true` |
| Runtime shape | PASS, `f504e296c398bdcb2c4c07e2`, RTX PRO 6000, 12 CPUs, 32768 MiB |
| Canonical output SHA | PASS, `20b10e1f99831bc758d9df82f43ce0beb1cbc636a740d11a29eb2bffe90e5260` |
| Conditioning cache | PASS, `decision=miss_stored`, `encode_calls=1`, fresh nonce |
| CLIP staged path | PASS, `ok=true`, fallback count `0`, zero-copy `398/398` keys |
| UNET staged path | PASS, `status=ok`, fallback count `0`, staged transport true |
| Residual meta tensors | PASS, `0` after validation |
| Host slabs | PASS, `4`, all slots pinned |
| Pinned pool | PASS, peak `1073741824` bytes |
| Bucket geometry | PASS, 256 MiB configured; CLIP `30` buckets; UNET `46` buckets |
| Copy stream | PASS, one stream; GPU owner remains one contiguous packed owner |
| Transport reconciliation | PASS, `unet_fastsafetensors_reconcile=OK`; remote return waterfall `OK`, `validation_status=COMPLETE` |
| Readiness gate | PASS, `MODEL_READINESS_GATE_MS=19781.742`, gated by UNET |

The artifact also records `CLIP_READY_AT=78743014030`,
`UNET_READY_AT=87118873731`, `MODEL_READINESS_GATE_AT=87118873731`, and
`coordination=CLIP_GPU_CRITICAL_ACTIVE`. The explicit readiness gate is now
present in the normal graph request.

#### Bucket-First Telemetry

| Metric | CLIP | UNET |
|---|---:|---:|
| staged wall ms | `6287.825` | `19781.7245` pipeline |
| prepare ms | `649.058` | `212.7896` |
| commit ms | `5399.066` | `8093.167` |
| H2D stream span ms | `4981.626` | `7343.481` |
| H2D DMA busy ms | `369.394` | `755.435` |
| H2D stream idle estimate ms | `4612.232` | `6588.046` |
| producer wait ms | `1611.676` | `2081.155` |
| consumer wait ms | `4357.877` | `6066.406` |
| source read ms | `12387.882` | `19209.903` |
| source materialization ms | `0.0` | `0.0` |
| bucket pack CPU ms | `5513.775` | `7321.745` |
| bucket ready wait ms | `4357.877` | `6066.406` |
| exact-copy bytes | `8044936192` | `12309817472` |
| median H2D copy bytes | `268435456` | `268435456` |
| H2D DMA GB/s | `20.2830` | `15.1759` |

Compared with the immediately preceding post-producer baseline B, stream
starvation regressed:

| Metric | Baseline B | Bucket-first B | Delta |
|---|---:|---:|---:|
| CLIP H2D stream span ms | `3831.382` | `4981.626` | `+1150.244` |
| CLIP H2D stream idle ms | `3572.527` | `4612.232` | `+1039.705` |
| CLIP consumer wait ms | `2650.000` | `4357.877` | `+1707.877` |
| UNET H2D stream span ms | `3656.188` | `7343.481` | `+3687.293` |
| UNET H2D stream idle ms | `3360.728` | `6588.046` | `+3227.318` |
| UNET consumer wait ms | `2680.000` | `6066.406` | `+3386.406` |

The new source-read and bucket-pack telemetry confirms that the bucket-first
producer path was active, but the bounded consumer still waited substantially
for bucket publication in this sample. The result is therefore a measured feed
regression, not evidence of a successful E10 performance improvement.

#### Reconciliation and E5 Caveats

The transport-specific and remote-return reconciliation records are `OK` and
complete. Separately, the artifact's top-level `timing.local_timing` record is
`reconciliation_status=incomplete` because `local_receive_to_enqueue_ms` is
missing; one alternate partial waterfall also reports
`missing_modal_restore_begin`. Those local submission/restore accounting gaps
are recorded rather than inferred away.

`empty_cache` operations were observed, but no explicit
`empty_cache_bypass_decision` event was present. Therefore
`E5_BYPASS_DECISION=UNKNOWN`, not inferred from the cleanup timings.

#### Decision

```text
E10_BUCKET_FEED_REGRESSION
PACKED_HOST_BUCKETS_IMPLEMENTED=YES
BUCKET_FIRST_SOURCE_FILL=YES
PACKED_PRODUCER_WORKERS=4
HOST_SLAB_IS_PINNED_ALL=YES
CLIP_H2D_BUCKET_COUNT=30
CLIP_MEDIAN_COPY_BYTES=268435456
CLIP_DMA_BUSY_MS=369.394
CLIP_STREAM_SPAN_MS=4981.626
CLIP_STREAM_IDLE_MS=4612.232
CLIP_SOURCE_READ_MS=12387.882
CLIP_BUCKET_PACK_CPU_MS=5513.775
UNET_H2D_BUCKET_COUNT=46
UNET_MEDIAN_COPY_BYTES=268435456
UNET_DMA_BUSY_MS=755.435
UNET_STREAM_SPAN_MS=7343.481
UNET_STREAM_IDLE_MS=6588.046
UNET_SOURCE_READ_MS=19209.903
UNET_BUCKET_PACK_CPU_MS=7321.745
PINNED_POOL_PEAK=1073741824
CPU_CAST_BYTES_CLIP=0
CPU_CAST_BYTES_UNET=0
B_MODEL_GATE_MS=19781.742
SAMPLER_GATED_BY=UNET
TRANSPORT_RECONCILIATION=OK
REMOTE_RETURN_RECONCILIATION=OK
LOCAL_TIMING_RECONCILIATION=incomplete (missing local_receive_to_enqueue_ms)
E5_BYPASS_DECISION=UNKNOWN (decision event absent)
B_STRUCTURALLY_VALID=YES
FEED_RESULT=REGRESSION
A_B_PAIR_PERFORMED=NO
A_NONCE=NOT_RUN
B_NONCE=01091575-1dda-4622-bbfc-6228a45fc1ed
PROVIDER_B=CLOUD_PROVIDER_AWS
REGION_B=us-east-1
MODAL_DEPLOYS=1
MODAL_REQUESTS=1
DIRECT_PYTHON_REMOTE_INVOKE_USED=NO
NEXT_STEP=STOP remote; do not run A/B after this regressed B
COMMIT=none
```

### Bucket-First Reproducibility Check

The read-only Modal app list showed no deployed
`stable-modal-comfy-v2-restore-only-staged-shadow` app, so the requested
redeploy exception applied. The canonical `deploy_and_run_v2_single.bat`
wrapper redeployed the staged B app once, and `run_v2_single.bat` then issued
exactly one graph request with a fresh conditioning nonce.

RUN1 artifact:

- `comfymodal-data/benchmarks/runs/v2_2026-08-17_02-03-23/run_001_sample.json`
- Request: `v2-benchmark-0-131abf83cd54`
- Nonce: `a9c690e7-87d8-4c09-b91f-019be527b91e`
- Image: `im-3fV5XXb2scdA6sNBpM4rzo`
- Placement: `CLOUD_PROVIDER_GCP/us-east4`

#### RUN1 Structural Result

The request was not valid bucket-first evidence and the reproducibility check
stopped:

| Gate | Result |
|---|---|
| Fresh identity | PASS, `fresh=true`, `restore_count=1`, `request_count=1` |
| Conditioning cache | PASS, `decision=miss_stored`, `encode_calls=1` |
| Canonical output SHA | PASS, `20b10e1f99831bc758d9df82f43ce0beb1cbc636a740d11a29eb2bffe90e5260` |
| Readiness gate | PRESENT, `MODEL_READINESS_GATE_MS=7482.685` |
| UNET staged path | PASS, staged transport true, fallback count `0`, 46 buckets |
| CLIP bucket-first path | FAIL, `fastsafetensors_direct_gpu` was used instead of `staged_safetensors`; bucket-first CLIP telemetry was absent |
| Structural validity | FAIL; request is excluded from performance evidence |

The artifact's effective request environment recorded
`COMFYMODAL_V2_CLIP_FAST_HYDRATION=0` and
`COMFYMODAL_V2_UNET_FASTSAFETENSORS=0`. `COMFYMODAL_V2_STAGED_SAFETENSORS=1`
was present, but that did not make the CLIP path the required bucket-first
staged path. This is a request-profile failure, not evidence that bucket-first
is fast or slow.

#### Explicit RUN1 Telemetry

CLIP bucket-first fields were not emitted and remain unknown:

| Metric | CLIP |
|---|---:|
| prepare ms | `UNKNOWN` |
| commit ms | `UNKNOWN` |
| source read ms | `UNKNOWN` |
| bucket pack CPU ms | `UNKNOWN` |
| bucket ready wait ms | `UNKNOWN` |
| consumer wait ms | `UNKNOWN` |
| producer wait ms | `UNKNOWN` |
| slab reuse wait ms | `UNKNOWN` |
| H2D DMA busy ms | `UNKNOWN` |
| H2D stream span ms | `UNKNOWN` |
| H2D stream idle ms | `UNKNOWN` |

UNET emitted staged transport telemetry, but it is not counted as RUN1
performance evidence because the paired CLIP structural gate failed:

| Metric | UNET |
|---|---:|
| prepare ms | `96.013` |
| commit ms | `3651.133` |
| source read ms | `8236.206237` |
| bucket pack CPU ms | `3411.838394` |
| bucket ready wait ms | `2688.740226` |
| consumer wait ms | `2688.740226` |
| producer wait ms | `1233.804581` |
| slab reuse wait ms | `1233.804581` |
| H2D DMA busy ms | `420.504` |
| H2D stream span ms | `3254.358` |
| H2D stream idle ms | `2833.854` |

The explicit end-to-end fields available in the invalid request were:

- No-scheduling command-to-response: `17134.41274 ms`
- Sampling: `3662.703 ms`

#### Timing Interpretation

`source_read_ms` is the accumulated sum of each worker's direct source-range
read intervals. `bucket_pack_cpu_ms` is the accumulated sum of each worker's
CPU slab-copy intervals. `producer_wait_ms` is the accumulated bounded-pool
wait time, and `consumer_wait_ms`/`bucket_ready_wait_ms` is the accumulated
consumer queue wait time. These fields are summed worker/component times and
must not be added together as serial request wall time; producer work overlaps.

`h2d_stream_span_ms` is the CUDA copy-stream wall interval, while
`h2d_dma_busy_ms` is the accumulated per-copy CUDA timing. The authoritative
end-to-end model metric remains `MODEL_READINESS_GATE_MS`, but RUN1 cannot be
used to classify bucket-first behavior because its CLIP path was wrong.

#### Decision

```text
E10_BUCKET_FIRST_REPRO_CHECK_COMPLETE
RUN1_REQUEST=v2-benchmark-0-131abf83cd54
RUN1_PROVIDER=CLOUD_PROVIDER_GCP
RUN1_REGION=us-east4
RUN1_MODEL_GATE_MS=7482.685 (present, but structurally invalid request)
RUN1_CLIP_SOURCE_READ_MS=UNKNOWN (CLIP fastsafetensors_direct_gpu path)
RUN1_CLIP_BUCKET_PACK_MS=UNKNOWN (not emitted)
RUN1_CLIP_STREAM_IDLE_MS=UNKNOWN (not emitted)
RUN1_UNET_SOURCE_READ_MS=8236.206237 (not performance evidence)
RUN1_UNET_BUCKET_PACK_MS=3411.838394 (not performance evidence)
RUN1_UNET_STREAM_IDLE_MS=2833.854 (not performance evidence)
RUN2_PERFORMED=NO (RUN1 structural failure)
RUN2_REQUEST=NOT_RUN
RUN2_PROVIDER=NOT_RUN
RUN2_REGION=NOT_RUN
RUN2_MODEL_GATE_MS=NOT_RUN
RUN2_CLIP_SOURCE_READ_MS=NOT_RUN
RUN2_CLIP_BUCKET_PACK_MS=NOT_RUN
RUN2_CLIP_STREAM_IDLE_MS=NOT_RUN
RUN2_UNET_SOURCE_READ_MS=NOT_RUN
RUN2_UNET_BUCKET_PACK_MS=NOT_RUN
RUN2_UNET_STREAM_IDLE_MS=NOT_RUN
TIMING_FIELDS_ARE_SUMMED_OR_WALL=source_read,bucket_pack_cpu,producer_wait,consumer_wait are summed worker/component fields; h2d_stream_span is copy-stream wall interval; MODEL_READINESS_GATE_MS is end-to-end model readiness
RESULT=STRUCTURAL_FAILURE_STOPPED; no performance classification
NEXT_STEP=STOP; do not count RUN1 as evidence; do not modify loader in this continuation
MODAL_DEPLOYS=1
MODAL_REQUESTS=1
DIRECT_PYTHON_REMOTE_INVOKE_USED=NO
COMMIT=none
```

## Historical Decision Before Packed Fix

`STOPPED_INVALID_AB`. B is structurally valid after repair, but the fresh pair
failed the equivalent-placement and fresh-conditioning gates. Do not interpret
the pair timing or expand the cohort. A future comparison must use independent
fresh conditioning-cache nonces because the cache is shared through the Volume,
and must still pass the unpinned provider/region equality gate.

## Historical Remote Staged-H2D Forensics

The authoritative staged B artifact remains:

- `comfymodal-data/benchmarks/runs/v2_2026-08-16_23-54-30/run_0.json`

No deployment or Modal request was made during this forensic pass.

### Transport Reconstruction

| Field | CLIP | UNET |
|---|---:|---:|
| checkpoint bytes | `8,044,982,048` | `12,309,866,400` |
| prepared bytes | `8,044,936,192` | `12,309,817,472` |
| CPU-cast bytes | `0` | `0` |
| exact-copy bytes | `8,044,936,192` | `12,309,817,472` |
| tensor count | `UNKNOWN` in artifact; zero-copy evidence has `398/398` bound keys | `453` |
| host transfer bucket count | `UNKNOWN`; four reusable slabs allocated | `UNKNOWN`; four reusable slabs allocated |
| allocated host slabs | `4 x 256 MiB` | `4 x 256 MiB` |
| GPU bucket count | `1` packed backing allocation; no 256 MiB GPU buckets | `1` packed backing allocation; no 256 MiB GPU buckets |
| H2D copy calls | `400` | `453` |
| bytes per H2D call | `UNKNOWN` per-call; mean `20,112,340.48` (derived) | `UNKNOWN` per-call; mean `27,173,990.00` (derived) |
| median H2D copy bytes | `UNKNOWN` | `UNKNOWN` |
| maximum H2D copy bytes | `UNKNOWN` | `UNKNOWN` |
| H2D enqueue ms | `3,547.459` | `3,472.180` |
| H2D device ms | `3,539.356` | `3,470.029` |
| commit ms | `3,871.242` | `3,497.694` |
| producer wait ms | `5,582.525` | `2,319.934` |
| consumer wait ms | `20.000` | `20.000` |
| effective H2D GB/s | `2.1169` | `3.3038` |

`prepared_bytes` equals `exact_copy_bytes` because both valid transfers used
same-dtype copies and reported zero CPU-cast bytes. The artifact does not carry
per-copy sizes, so median and maximum sizes are intentionally not inferred.

### H2D Timer Semantics

`H2D_DEVICE_TIMER_START` is `start_event.record(copy_stream)` immediately
before the queue-consumer loop. GPU output allocation, packed-buffer allocation,
tensor-view creation, producer file reads, host slab fills, and CPU casts occur
before this event or on producer threads.

`H2D_DEVICE_TIMER_END` is `end_event.record(copy_stream)` after the queue is
empty and all producer futures have completed. The timed stream interval
contains every queued `copy_` call and one non-timing completion-event record
after each copy.

`h2d_device_ms` does not include CUDA allocation, GPU packed-buffer allocation,
host staging, CPU casting, producer slot-reuse waits, final
`current_stream.wait_stream`, final `end_event.synchronize()`, binding, or
owner cleanup. It is not the broader commit interval.

`H2D_DEVICE_MS_IS_PURE_DMA=NO` in the literal sense because event-record work
is inside the CUDA event interval. It is otherwise a narrow copy-stream
execution interval, not a hidden commit-wall timer.

### Host Pinning

| Field | Finding |
|---|---|
| host pool allocation API | `torch.empty(size, dtype=torch.uint8, pin_memory=True)` in `staged_safetensors._allocate_pinned` |
| CUDA pinned confirmed by API | `NO` for the historical artifact; the API was requested but `is_pinned()` was not recorded |
| CUDA host-register used | `NO` by E1; no `cudaHostRegister` call exists in the staged core |
| pin-memory flag | `True` |
| `is_pinned()` check available | `YES` on the PyTorch tensor API |
| `is_pinned()` check recorded in historical artifact | `NO` |
| historical host pool actually pinned | `UNKNOWN` |

The local fix adds `host_slab_is_pinned` to the bounded pool, `StageResult`,
CLIP telemetry, and UNET telemetry. It checks every slab once at allocation
without changing the transport path. The historical B artifact therefore
cannot be retroactively upgraded from requested pinning to proven pinning.

### Contiguous-Bucket Shape

`COMFYMODAL_V2_STAGED_CONTIGUOUS_GPU_BUCKETS=1` creates one dense packed GPU
backing owner and typed tensor views. It does not pack host tensors into
256 MiB transfer ranges. `_produce` acquires a slab per tensor chunk, copies
that chunk into the slab, and queues a `_Chunk`; commit then submits one H2D
copy for each queued chunk.

Therefore the live shape is:

- `H2D_COPY_CALLS_CLIP=400`
- `H2D_COPY_CALLS_UNET=453`
- `MEDIAN_H2D_COPY_BYTES=UNKNOWN`
- `MAX_H2D_COPY_BYTES=UNKNOWN`
- contiguous GPU storage: active
- contiguous 256 MiB host-to-device DMA: not active

This is shape B from the requested classification: many per-tensor H2D
operations from reusable host slabs. The `bucket_bytes` telemetry is a slab
capacity, not the submitted copy size.

### Slot and Event Pipeline

| Field | Finding |
|---|---|
| maximum host slabs in flight | `4` |
| CUDA copy streams | `1` |
| event wait location | producer-side `_PinnedSlabPool.acquire`, on pending slab reuse |
| event wait blocks consumer | `NO`; consumer queues copies and records completion events |
| event wait blocks producer | `YES`; `pending.synchronize()` is used when no slab is reclaimable |
| per-slab synchronization | `YES`, only when a producer must reuse a slab whose event is incomplete |
| per-tensor synchronization | `NO`; there is an event record per copy, but no tensor-level synchronize |

The implementation can enqueue multiple copies before a producer stalls, but
all H2D work is ordered on one CUDA stream. It is not literally
`copy 256 MiB -> wait -> copy 256 MiB` in the consumer; it is a one-stream
sequence of tensor-sized copies with four event-protected reusable slabs.

### Other Synchronizations

The staged core has no success-path `torch.cuda.synchronize`, `empty_cache`,
`ipc_collect`, `cudaMemGetInfo`, `.item()`, or `.cpu()` call. The relevant
operations are:

- producer-side pending-slab `event.synchronize()` during slot reuse;
- failure/owner-release `copy_stream.synchronize()` cleanup;
- one final `current_stream.wait_stream(copy_stream)` readiness fence;
- one final `end_event.synchronize()` to realize the result event;
- CLIP's post-bind `torch.cuda.synchronize()` final readiness fence;
- UNET's post-bind final `torch.cuda.synchronize()` before final validation.

The last two are outside E1 `h2d_device_ms`; they are post-bind readiness
operations. No per-tensor device-wide synchronization was found.

### E4 Comparison

`E4_PATH_EQUIVALENT_TO_REMOTE=PARTIAL`.

Common elements are `torch.empty(..., pin_memory=True)`, non-blocking
`copy_`, one CUDA stream, 256 MiB configured geometry, and CUDA event timing.
Material differences are:

- E4 uses one contiguous 1 GiB pinned pool and explicitly submits four 256 MiB ranges.
- E1 uses four separate 256 MiB slabs and submits one range per tensor chunk.
- E4 records `pool_is_pinned=true`; the historical remote artifact did not record an `is_pinned()` result.
- E4's staged benchmark uses synthetic prefilled data; E1 includes safetensors reads, per-tensor CPU copies, queueing, and slab recycling.
- E4's comparison GPU was an RTX 3070; B observed an RTX PRO 6000 Blackwell Server Edition.

The remote 2.1169/3.3038 GB/s values are therefore not a like-for-like
reproduction of E4's four-copy bucketed path.

### Decision

`ROOT_CAUSE=E1 bucket_bytes limits reusable slab/chunk capacity but does not
aggregate tensor chunks into bucket-sized H2D submissions; contiguous mode
only packs GPU storage. The resulting 400/453-copy, one-stream shape explains
why both transfers show multi-second device intervals.`

`FIX_IMPLEMENTED=Added low-overhead host_slab_is_pinned telemetry and a core
regression test. No transport rewrite or performance tuning was performed.`

`LOCAL_TESTS=53 passed, 10 subtests passed; py_compile passed.`

`REMOTE_RETRY_PERFORMED=NO`

`B_STRUCTURALLY_VALID=YES` from the preserved repair artifact; no new B
request was issued.

`A_B_PAIR_PERFORMED=NO` in this forensic pass. The prior fresh pair remains
excluded: A was `CLOUD_PROVIDER_GCP/asia-south1`, B was
`CLOUD_PROVIDER_GCP/us-east1`, and the pair reused one conditioning nonce.

For that excluded pair only, the observed descriptive values were A
`5727.106 ms` and B `4797.442 ms`; they are not a performance comparison.

`A_NONCE_FRESH=YES` (prior A request), `B_NONCE_FRESH=NO` (prior B reused the
shared entry), `A_B_NONCES_DIFFERENT=NO`.

`PHASE_E_RESULT=E10_STAGE_DESIGN_REGRESSION`

`NEXT_STEP=Implement and locally validate a real bounded host-bucket packer
that submits approximately 256 MiB H2D ranges while retaining the four-slab
hard cap and owner/event safety. Only after that local change should one B
structural request and, if valid, one A/B pair with independent fresh nonces
be considered.`

```text
E10_H2D_FORENSICS_COMPLETE
H2D_DEVICE_MS_IS_PURE_DMA=NO
HOST_POOL_ACTUALLY_PINNED=UNKNOWN
HOST_POOL_ALLOCATION_API=torch.empty(pin_memory=True)
CLIP_BYTES=8044936192
CLIP_H2D_MS=3539.356
CLIP_EFFECTIVE_GBPS=2.1169
CLIP_H2D_COPY_CALLS=400
UNET_BYTES=12309817472
UNET_H2D_MS=3470.029
UNET_EFFECTIVE_GBPS=3.3038
UNET_H2D_COPY_CALLS=453
MEDIAN_H2D_COPY_BYTES=UNKNOWN
MAX_H2D_COPY_BYTES=UNKNOWN
MAX_H2D_IN_FLIGHT_BUCKETS=4 host slabs; 1 CUDA copy stream
PER_BUCKET_SYNC_FOUND=YES at slab reuse
PER_TENSOR_SYNC_FOUND=NO
E4_PATH_EQUIVALENT_TO_REMOTE=PARTIAL
ROOT_CAUSE=per-tensor H2D submissions, not packed 256 MiB host buckets
FIX_IMPLEMENTED=host_slab_is_pinned telemetry only
LOCAL_TESTS=53 passed, 10 subtests passed; py_compile passed
REMOTE_RETRY_PERFORMED=NO
B_STRUCTURALLY_VALID=YES
A_B_PAIR_PERFORMED=NO
A_NONCE_FRESH=YES
B_NONCE_FRESH=NO
A_B_NONCES_DIFFERENT=NO
PROVIDER_A=CLOUD_PROVIDER_GCP
REGION_A=asia-south1
PROVIDER_B=CLOUD_PROVIDER_GCP
REGION_B=us-east1
PLACEMENT_MATCH=NO
A_MODEL_GATE_MS=NOT_COMPARED (prior invalid pair: 5727.106)
B_MODEL_GATE_MS=NOT_COMPARED (prior invalid pair: 4797.442)
MODEL_GATE_DELTA_MS=NOT_COMPARABLE
PHASE_E_RESULT=E10_STAGE_DESIGN_REGRESSION
NEXT_STEP=bounded host-bucket packing local fix, then B structural retry
DIRECT_PYTHON_REMOTE_INVOKE_USED=NO
COMMIT=none
```

## Corrected Bucket-First Reproducibility Check

This section supersedes the stopped check above for the corrected canonical E10
B profile. The CLIP request profile used staged hydration, and both requests
used the required staged CLIP+UNET transport path. No A/B pair was run.

The single successful deployment used image `im-MapfWW6mMr6c842EcsbtTA`.
Both requests ran on `CLOUD_PROVIDER_GCP/us-east1`; their restored instance IDs
differed, so this is a same-placement two-request threshold check, not a
provider-isolated experiment.

### Corrected Request Artifacts

RUN1:

- `comfymodal-data/benchmarks/runs/v2_2026-08-17_02-27-30/run_001_sample.json`
- Request: `v2-benchmark-0-e617724954ec`
- Cache nonce: `ceb9e102-a3af-43e4-ada2-7683fe1da38c`
- Identity: `fresh=true`, `restore_count=1`, `request_count=1`
- Conditioning cache: `decision=miss_stored`, `encode_calls=1`
- Output SHA: `20b10e1f99831bc758d9df82f43ce0beb1cbc636a740d11a29eb2bffe90e5260`

RUN2:

- `comfymodal-data/benchmarks/runs/v2_2026-08-17_02-31-33/run_001_sample.json`
- Request: `v2-benchmark-0-8f93d967b376`
- Cache nonce: `281d838e-345a-4ece-b3ed-2a338414f8fd`
- Identity: `fresh=true`, `restore_count=1`, `request_count=1`
- Conditioning cache: `decision=miss_stored`, `encode_calls=1`
- Output SHA: `20b10e1f99831bc758d9df82f43ce0beb1cbc636a740d11a29eb2bffe90e5260`

### Corrected Structural Gates

| Gate | RUN1 | RUN2 |
|---|---|---|
| CLIP hydration decision | PASS, `staged_path` | PASS, `staged_path` |
| CLIP transport mode | `staged_safetensors` | `staged_safetensors` |
| CLIP buckets | 30, fallback `0` | 30, fallback `0` |
| UNET staged transport | PASS, 46 buckets, fallback `0` | PASS, 46 buckets, fallback `0` |
| Host slabs | 4, all pinned | 4, all pinned |
| Producers | 4 | 4 |
| CPU cast bytes | `0` | `0` |
| Structural validity | PASS | PASS |

Both artifacts also report `pinned_fast_path_active=true`, one stream, one
contiguous GPU backing allocation, and the same canonical output SHA. The
UNET final validation reports all parameters on `cuda:0` and
`residual_meta_count=0` in both requests.

### Explicit CLIP Telemetry

| Metric | RUN1 | RUN2 |
|---|---:|---:|
| prepare ms | `187.669` | `632.43` |
| commit ms | `2419.816` | `2442.736` |
| source read ms | `5422.95224` | `6002.710389` |
| bucket pack CPU ms | `2092.842892` | `2497.472976` |
| bucket ready wait ms | `1714.672407` | `1986.950868` |
| consumer wait ms | `1714.672407` | `1986.950868` |
| producer wait ms | `687.383486` | `677.459144` |
| slab reuse wait ms | `687.383486` | `677.459144` |
| H2D DMA busy ms | `243.18` | `227.772` |
| H2D stream span ms | `2094.206` | `2263.252` |
| H2D stream idle ms | `1851.026` | `2035.48` |

### Explicit UNET Telemetry

| Metric | RUN1 | RUN2 |
|---|---:|---:|
| prepare ms | `74.7602` | `87.0591` |
| commit ms | `3424.119` | `3510.0075` |
| source read ms | `7823.989786` | `7769.090619` |
| bucket pack CPU ms | `3375.985573` | `3731.499223` |
| bucket ready wait ms | `2568.220664` | `2636.553347` |
| consumer wait ms | `2568.220664` | `2636.553347` |
| producer wait ms | `987.963013` | `1043.671239` |
| slab reuse wait ms | `987.963013` | `1043.671239` |
| H2D DMA busy ms | `426.914` | `390.257` |
| H2D stream span ms | `3095.146` | `3147.297` |
| H2D stream idle ms | `2668.232` | `2757.04` |

These source-read, bucket-pack, producer-wait, consumer-wait, and slab-reuse
values are accumulated worker/component fields. They are not serial request
wall time. H2D stream span is a copy-stream wall interval; H2D DMA busy is the
accumulated per-copy CUDA timing.

### Readiness, Sampling, and E5 Observations

| Field | RUN1 | RUN2 |
|---|---:|---:|
| `MODEL_READINESS_GATE_MS` | `10163.222` | `9947.728` |
| `SAMPLER_GATED_BY` | `UNET` | `UNET` |
| `CLIP_READY_AT` | `168507201250` | `411567960369` |
| `UNET_READY_AT` | `172062505122` | `415213453076` |
| `command_response_ms` | `63563.7247` | `171937.4851` |
| `non_scheduling_ms` | `UNKNOWN` (`null`) | `UNKNOWN` (`null`) |
| `sampling_ms` key | `UNKNOWN` (absent) | `UNKNOWN` (absent) |
| `critical_path_metrics.sampler_ms` | `3683.827` | `3710.2` |
| `sampling_boundary_ms` | `3683.827` | `3710.2` |

The command-response values above are recorded as emitted and are not used as
substitutes for the missing `non_scheduling_ms` field. The sampler and
sampling-boundary values are recorded under their explicit artifact field
names; no missing `sampling_ms` value is inferred.

E5 observations in both artifacts:

- `diagnostic_bypass_cpu_snapshot_unet=0`
- `cpu_snapshot_unet_reused=0`
- `demand_wrapper_present=true` at the bound CLIP snapshot model
- `coordination=CLIP_GPU_CRITICAL_ACTIVE`
- Explicit E5 bypass decision event: `UNKNOWN` (not emitted)

### Corrected Decision

```text
E10_CORRECTED_BUCKET_FIRST_REPRO_CHECK_COMPLETE
RUN1_STRUCTURALLY_VALID=YES
RUN2_STRUCTURALLY_VALID=YES
RUN1_MODEL_GATE_MS=10163.222
RUN2_MODEL_GATE_MS=9947.728
RUN1_BELOW_10000_MS=NO
RUN2_BELOW_10000_MS=YES
SAME_PROVIDER=CLOUD_PROVIDER_GCP
SAME_REGION=us-east1
A_B_PAIR_PERFORMED=NO
RESULT=BUCKET_FIRST_HIGH_VARIANCE_OR_PROVIDER_SENSITIVE
INTERPRETATION=RUN1 crossed the 10000 ms threshold while RUN2 was healthy; two requests cannot isolate host variance from provider sensitivity
MODAL_DEPLOYS=1
MODAL_REQUESTS=2
DIRECT_PYTHON_REMOTE_INVOKE_USED=NO
LOADER_CHANGES_IN_THIS_CONTINUATION=NO
COMMIT=none
```
