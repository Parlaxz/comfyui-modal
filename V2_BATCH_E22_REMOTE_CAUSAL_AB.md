# V2 Batch E22 Remote Causal A/B

## Remote Execution Recovery

The canonical wrapper invocation was repaired and locally proven through
`cmd.exe /d /c call` with both E22 selectors. The original blocker was shell
interop: the agent shell working directory was not inherited by `cmd.exe`, and
an attempted 8.3 short-name command used the nonexistent `DEPLOY~2.BAT`.

The corrected local proof used the quoted repository path and relative batch
execution after `pushd`. Both arms returned exit code 0, printed `PROFILE
ACCEPTED`, and printed `MODAL_DEPLOY_SKIPPED=1` in preflight-only mode.

## Remote Outcome

Arm A was started with `E22_PREFETCH_OFF`. The wrapper deployed the V2 app and
then entered the benchmark's default loop. The wrapper change selected the
single-run branch, but `benchmark_v2_direct.py` defaulted to its configured
multi-run count of 10. The user aborted after six completed requests.

Arm B was not started.

This is not a valid E22 causal A/B and must not be interpreted as an
inconclusive performance result.

| Field | Result |
|---|---|
| Remote status | BLOCKED_AFTER_ARM_A_HARNESS_ERROR |
| Arm A | E22_PREFETCH_OFF, E19_FINAL_COLD_LOADER |
| Arm B | NOT RUN |
| Deployments | 1 V2 deployment observed |
| Paid requests | 6 completed Arm A requests observed |
| Authorized maximum | 2 deployments, 2 paid requests |
| Budget status | EXCEEDED by wrapper benchmark-count bug |
| Fresh cold samples | 1 initial conditioning miss; later requests were exact cache hits |
| Provider / region | GCP; observed us-east1 and us-east4 |
| GPU | RTX PRO 6000 Blackwell |
| Image | im-cd2wMjbshYUsAmIGJyZVIl |
| Deployment identity | f83cc58772c808247d126dde127f3735064865d168d79255ed8dcbec387b39e3 |
| Runtime fingerprint | af84b9629a4205598f76dc6382c8f0f20da0eec9012254def7222c04405f613f |
| Output SHA on completed requests | 20b10e1f99831bc758d9df82f43ce0beb1cbc636a740d11a29eb2bffe90e5260 |

## Measurements

No Arm B measurements exist. Arm A request 1 reported a CLIP encode of about
6.527 s and a canonical output SHA match. Requests 2 through 6 reported CLIP
encode skipped because conditioning exact-hit cache entries were reused.

Worker B, UNET readiness, joint readiness, and prefetch deltas are not valid
for causal comparison because there is no ON arm and the request sequence was
not the authorized one-request-per-arm design.

## Final Classification

```text
E22_REMOTE_AB_COMPLETE = NO
E22_REMOTE_STATUS = BLOCKED_BEFORE_ARM_B_INFERENCE_BY_REGISTRY_PRIMING_GUARD
ARM_A_STRUCTURAL_VALIDITY = VALID
ARM_B_STRUCTURAL_VALIDITY = NOT RUN (deployment succeeded; pre-inference harness gate failed)
PREFETCH_RESULT = NOT MEASURED
PRIMARY_CAUSAL_FINDING = NONE
DIRECT_PYTHON_REMOTE_INVOKE_USED = NO
REMOTE_BUDGET_EXCEEDED = YES (historical prior attempt; current authorization not exceeded)
COMMIT = none
```

## Final Authoritative Completion (Supersedes Pre-Inference Block)

The user authorized one additional Arm B run. The repaired `--run-only` path
reused the already-deployed V2 identity, primed the local registry-proof store,
and issued exactly one fresh remote inference. No second request or deployment
was issued.

```text
E22_REMOTE_AB_COMPLETE = YES
ARM_A_REQUEST_1_SALVAGEABLE = YES
ARM_A_STRUCTURAL_VALIDITY = VALID
ARM_B_STRUCTURAL_VALIDITY = VALID
ARM_A_REQUEST_ID = v2-benchmark-0-0116896eac02
ARM_B_REQUEST_ID = v2-benchmark-0-d8ab91a70ce9
ARM_A_PROVIDER = GCP
ARM_A_REGION = us-east1
ARM_B_PROVIDER = GCP
ARM_B_REGION = us-east4
ARM_B_IMAGE_ID = im-pZlX9BuQFzYwc44UXI8p3D
ARM_B_DEPLOYED_IDENTITY = c510367e44b4c13e
ARM_B_FRESH_RESTORE = true
ARM_B_REQUEST_COUNT = 1
ARM_B_RESTORE_COUNT = 1
ARM_A_PREFETCH = 0
ARM_B_PREFETCH = 1
ARM_A_CLIP_LOADER_IDENTITY = fastsafetensors_direct_gpu (salvaged artifact)
ARM_B_CLIP_LOADER_IDENTITY = direct-GPU CLIP path; no fallback
ARM_A_UNET_LOADER_IDENTITY = fastsafetensors
ARM_B_UNET_LOADER_IDENTITY = fastsafetensors
ARM_A_CLIP_FORWARD_MS = 2775.666
ARM_B_CLIP_FORWARD_MS = 4650.688
CLIP_COST_MS = 1875.022
CLIP_COST_PERCENT = 67.5%
ARM_A_WORKER_B_WALL_MS = 5019.5027
ARM_B_WORKER_B_WALL_MS = 5596.8852
WORKER_B_VALUE_MS = -577.3825
WORKER_B_VALUE_PERCENT = -11.5%
ARM_A_CLIP_READY_FROM_GRAPH_START_MS = 4672.437
ARM_B_CLIP_READY_FROM_GRAPH_START_MS = 6917.516
ARM_A_UNET_READY_FROM_GRAPH_START_MS = 6815.863
ARM_B_UNET_READY_FROM_GRAPH_START_MS = 7524.382
UNET_READINESS_VALUE_MS = -708.519
ARM_A_MODEL_READINESS_FROM_GRAPH_START_MS = 6815.863
ARM_B_MODEL_READINESS_FROM_GRAPH_START_MS = 7524.382
NET_PREFETCH_VALUE_MS = -708.519
ARM_A_POST_CLIP_UNET_TAIL_MS = 2143.427
ARM_B_POST_CLIP_UNET_TAIL_MS = 606.866
ARM_B_PREFETCH_EXECUTED = true
ARM_B_PREFETCH_BYTES = 12309866400
ARM_B_PREFETCH_FRACTION = 1.0
ARM_B_PREFETCH_WALL_MS = 4105.848
ARM_B_PREFETCH_STOP_REASON = completed
ARM_B_PREFETCH_CLIP_FORWARD_OVERLAP_MS = 0.0
ARM_B_SOURCE_FENCE_VALID = true
ARM_B_WORKERS_ALIVE_AT_DEMAND_START = 0
ARM_B_PREFETCH_DEMAND_COLLISION = false
ARM_B_UNET_GPU_OVERLAP_WITH_CLIP_CRITICAL_MS = 0.0
ARM_A_OUTPUT_SHA_MATCH = true
ARM_B_OUTPUT_SHA_MATCH = true
ARM_A_COMMAND_RESPONSE_S = 23.966761
ARM_B_COMMAND_RESPONSE_S = 23.595500
ARM_A_NO_SCHEDULING_S = 22.435829
ARM_B_NO_SCHEDULING_S = 22.727233
ARM_A_SCHEDULING_S = 0.911955
ARM_B_SCHEDULING_S = 0.371140
ARM_A_SAMPLING_MS = NOT SEPARATELY REPORTED
ARM_B_SAMPLING_MS = NOT SEPARATELY REPORTED
ARM_A_VAE_EMPTY_CACHE_MS = NOT SEPARATELY REPORTED
ARM_B_VAE_EMPTY_CACHE_MS = NOT SEPARATELY REPORTED
PLACEMENT_COMPARABILITY = LIMITED (same GCP provider, us-east1 vs us-east4)
QWEN_PREFETCH_OFF_BASELINE_MS = 2775.666
ARM_A_C3_RECONCILIATION_STATUS = historical fields do not fully reconcile
ARM_B_C3_RECONCILIATION_STATUS = internally reconciled; residual 2.697 ms
PREFETCH_RESULT = INCONCLUSIVE
PREFETCH_RESULT_EVIDENCE = ON was slower for joint readiness by 708.519 ms and CLIP by 1875.022 ms, but one sample per arm used different GCP regions.
PRIMARY_CAUSAL_FINDING = No defensible causal KEEP decision; ON showed negative observed readiness delta under limited placement comparability.
TOP_REMAINING_PHASE_E_BOTTLENECK = Phase-E harness/publication and registry-proof orchestration, not runtime prefetch performance
NEXT_ACTION = STOP; no more E22 remote work authorized or required
```

The historical accidental Arm A overrun remains unchanged: one prior
deployment and six prior paid requests. The final authorized completion used
one new deployment total and one new paid request total; the extra run itself
used zero deployments and one paid request.

## Additional Authorized Runs

The user subsequently authorized two additional paid requests. Both used the
existing deployed Arm B app through separate canonical `--run-only` wrapper
invocations. Neither invocation deployed, looped, retried, or issued a warm
follow-up.

```text
ADDITIONAL_AUTHORIZED_PAID_REQUESTS = 2
ADDITIONAL_DEPLOYMENTS = 0
ADDITIONAL_REQUEST_1_ID = v2-benchmark-0-7a3e908f6580
ADDITIONAL_REQUEST_2_ID = v2-benchmark-0-6101fbc931ef
ADDITIONAL_REQUEST_1_COUNT = 1
ADDITIONAL_REQUEST_2_COUNT = 1
ADDITIONAL_REQUEST_1_CONDITIONING = miss_stored
ADDITIONAL_REQUEST_2_CONDITIONING = miss_stored
ADDITIONAL_REQUEST_1_OUTPUT_SHA_MATCH = true
ADDITIONAL_REQUEST_2_OUTPUT_SHA_MATCH = true
ADDITIONAL_REQUESTS_LIMIT_EXCEEDED = NO
```

These extra ON-only observations are recorded for variance context and do not
replace the pre-registered one-sample-per-arm causal comparison.

The original Arm A classification above is superseded by the salvaged request-1
analysis below. The prior publication failure is also superseded for the
single authorized Arm B attempt, which proved exact generation reuse and did
not upload an archive. No additional deployments or paid requests may be made
under this E22 authorization.

## Salvaged Arm A Request 1

Request 1 is independently salvageable. Its state at request time proves the
E22 OFF environment, one fresh restore, one request, one restore, a
`miss_stored` conditioning decision with `encode_calls=1`, direct-GPU CLIP,
fastsafetensors UNET, zero fallbacks, valid source fences, zero UNET/CLIP
critical overlap, and the canonical output SHA. Requests 2-6 remain excluded.

```text
ARM_A_REQUEST_1_SALVAGEABLE = YES
ARM_A_REQUEST_ID = v2-benchmark-0-0116896eac02
ARM_A_PROVIDER = CLOUD_PROVIDER_GCP
ARM_A_REGION = us-east1
ARM_A_IMAGE_ID = im-cd2wMjbshYUsAmIGJyZVIl
ARM_A_RUNTIME_FINGERPRINT = af84b9629a4205598f76dc6382c8f0f20da0eec9012254def7222c04405f613f
ARM_A_RESTORE_SESSION_ID = a308ff3c13fb476dac0c25c4ed7e9981
ARM_A_RESTORED_INSTANCE_ID = 91f661e408b542c68432063f8fc2c467
ARM_A_PREFETCH = 0
ARM_A_CLIP_FORWARD_MS = 2775.666
ARM_A_CLIP_HYDRATION_WALL_MS = 1613.168
ARM_A_WORKER_B_WALL_MS = 5019.5027
ARM_A_FASTSAFE_PIPELINE_WALL_MS = 7035.1978
ARM_A_FASTSAFE_FILE_TO_GPU_WALL_MS = 2084.8063
ARM_A_GRAPH_EXECUTION_START_MONOTONIC_S = 92.965297554
ARM_A_CLIP_READY_AT_MONOTONIC_S = 97.637734243
ARM_A_UNET_READY_AT_MONOTONIC_S = 99.781160887
ARM_A_UNET_READY_FROM_GRAPH_START_MS = 6815.863
ARM_A_MODEL_READINESS_FROM_GRAPH_START_MS = 6815.863
ARM_A_POST_CLIP_UNET_TAIL_MS = 2143.427
ARM_A_COMMAND_RESPONSE_MS = 23966.761
ARM_A_COMMAND_WITHOUT_SCHEDULING_MS = 22435.829
ARM_A_SCHEDULING_MS = 911.955
ARM_A_OUTPUT_SHA_MATCH = true
```

The artifact carries the exact Worker B wall field but not the raw worker
start/end timestamps. The direct raw pipeline metadata identifies
`unet_fastsafetensors_pipeline`, `worker_b_wall_ms=5019.5027`, and
`total_pipeline_wall_ms=7035.1978`.

## Single-Run Harness Repair

The actual default loop count is `RUN_COUNT = int(V2_BENCHMARK_RUNS, "1")`.
The wrapper now sets `V2_BENCHMARK_RUNS=1` for either E22 arm and invokes the
actual CLI option `--run-count 1`. The benchmark also rejects an active E22 arm
unless both the CLI count and environment count are exactly 1.

Local canonical proofs:

```text
ARM_A_WRAPPER_PREFLIGHT = PASS
ARM_B_WRAPPER_PREFLIGHT = PASS
ARM_A_BENCHMARK_COMMAND = python tools\benchmark_v2_direct.py --run-count 1 --conditioning-cache-nonce <fresh>
ARM_B_BENCHMARK_COMMAND = python tools\benchmark_v2_direct.py --run-count 1 --conditioning-cache-nonce <fresh>
NEGATIVE_COUNT_2_GUARD = PASS (exit 1, no deploy/request)
FOCUSED_TESTS = 37 passed
PYCOMPILE = PASS
TARGETED_DIFF_CHECK = PASS (pre-existing unrelated whitespace warning only)
```

## Salvaged Arm A + Arm B Attempt (Superseded Historical Entry)

The first new Arm B command was invoked exactly once through the canonical
wrapper. It reached custom-node Volume publication but failed locally with
repeated `MemoryError` SSL transport failures while uploading to object
storage. The later repaired attempt supersedes this entry: it reused the
already-proven Volume generation, deployed V2, and stopped before inference at
the registry-proof run-count guard.

```text
NEW_ARM_B_DEPLOYMENTS = 1 (final repaired attempt; historical failed attempt used 0)
NEW_ARM_B_PAID_REQUESTS = 0
ARM_B_STRUCTURAL_VALIDITY = NOT RUN
ARM_B_FAILURE = LOCAL_PUBLISH_CUSTOM_NODES_MEMORY_ERROR
ARM_B_PREFETCH = 1 (configured, not measured)
PLACEMENT_COMPARABILITY = NOT APPLICABLE
PREFETCH_RESULT = NOT MEASURED
E22_REMOTE_AB_COMPLETE = NO
```

Historical and new work are intentionally reported separately:

```text
PREVIOUS_FAILED_ATTEMPT_DEPLOYS = 1
PREVIOUS_FAILED_ATTEMPT_PAID_REQUESTS = 6
PREVIOUS_BUDGET_EXCEEDED = YES
NEW_AUTHORIZED_COMPLETION_DEPLOY_LIMIT = 1
NEW_AUTHORIZED_COMPLETION_REQUEST_LIMIT = 1
NEW_DEPLOYS_USED = 1
NEW_PAID_REQUESTS_USED = 0
NEW_REMOTE_LIMIT_EXCEEDED = NO
```

## Volume Publication Failure

The failed prior Arm B attempt reached the unconditional publisher before any
Modal V2 deployment. The exact path was:

```text
deploy_and_run_v2_single.bat
  -> python tools\\publish_custom_nodes_volume.py
  -> modal_client.sync_custom_nodes
  -> sync_custom_nodes_to_volume.remote(archive_data)
  -> aiohttp SSL payload write to Cloudflare object storage
```

The publisher builds the entire custom-node tar.gz in an in-memory
`io.BytesIO`, converts it to `bytes`, and passes that bytes object as the Modal
function argument. The first causal failure was confirmed as:

```text
MemoryError
  C:\\Program Files\\Python311\\Lib\\asyncio\\sslproto.py:694
  _do_write -> _process_outgoing -> _outgoing.read()
```

The first SSL transport error was the consequence of that failed outbound
payload drain. The subsequent `ClientConnectionError` and `WinError 10038`
socket teardown errors were secondary. The exact archive byte size and host
process memory watermark were not logged. No explicit publisher retry loop was
found; the repeated SSL callbacks were transport teardown behavior.

```text
PUBLICATION_COMMAND = python tools\\publish_custom_nodes_volume.py
PUBLICATION_STAGE = Modal SDK bytes payload upload
FIRST_MEMORY_ERROR_STACK = asyncio.sslproto._do_write/_process_outgoing/_outgoing.read
FIRST_SSL_ERROR_STACK = aiohttp ClientConnectionError while writing BytesIO payload
PROCESS_MEMORY_NEAR_FAILURE = UNKNOWN (not logged)
FILE_OR_BATCH_BEING_UPLOADED = full custom-node tar.gz archive
BYTES_BEING_HANDLED = exact size UNKNOWN; archive was materialized as bytes
RETRY_BEHAVIOR = no explicit publisher retry; repeated transport teardown callbacks
FAILURE_EXIT_CODE = wrapper stopped before V2 deploy; publisher failure path exit 1
ROOT_CAUSE_CONFIDENCE = CONFIRMED: unbounded in-memory archive/payload buffering
```

## Volume Publication Repair

The salvaged Arm A artifact proves `custom_nodes_generation_match=true`, and
the local source generation exactly matches the prior container readback:
`4119a1259800fcc64a9b3989048964f9`. The E22 wrapper now fails closed unless
that exact match is present, then reuses the already-published Volume instead
of constructing or uploading the redundant archive. The local canonical
preflight printed `reuse_proven=1`; the remote Arm B log printed the same
generation and did not enter the publisher. This is a reuse proof, not a
general publication optimization.

```text
PUBLICATION_REPAIR = E22-only exact-generation reuse; mismatch refuses deployment
PUBLICATION_MEMORY_BEHAVIOR_AFTER_REPAIR = bounded; archive upload skipped
```

## Exactly-One-Run Arm B

The canonical Arm B wrapper passed local preflight with E19, prewarm `1`, a
fresh nonce, and explicit `--run-count 1`. The intentional count-2 preflight
exited nonzero before deployment. The single authorized remote attempt then
deployed V2 successfully and recorded deployment identity, but failed during
the existing registry-proof priming step because that internal verifier call
did not pass the explicit run count and was rejected by the benchmark-side E22
guard. No benchmark request artifact, paid inference request, or Arm B runtime
sample was produced. The hard no-retry rule was honored.

```text
ARM_A_REQUEST_1_SALVAGEABLE = YES
ARM_A_STRUCTURAL_VALIDITY = VALID
ARM_B_STRUCTURAL_VALIDITY = NOT RUN
ARM_B_DEPLOYMENT = SUCCEEDED (one new deployment)
ARM_B_PAID_REQUESTS = 0
ARM_B_FAILURE = PRE_INFERENCE_REGISTRY_PRIMING_RUN_COUNT_GUARD
ARM_B_PREFETCH = 1 (configured, not measured)
PREFETCH_RESULT = NOT MEASURED
E22_REMOTE_STATUS = BLOCKED_BEFORE_ARM_B_INFERENCE_BY_REGISTRY_PRIMING_GUARD
```

## Final Causal A/B

No causal A/B exists because Arm B issued no inference request. The salvaged
Arm A request-1 baseline remains authoritative and the six later Arm A cache
hit requests remain excluded. No Arm B provider, region, runtime metrics,
prefetch bytes, output SHA, readiness delta, or causal decision is available.

```text
E22_REMOTE_AB_COMPLETE = NO
ARM_A_PROVIDER = GCP
ARM_A_REGION = us-east1
ARM_B_PROVIDER = NOT MEASURED
ARM_B_REGION = NOT MEASURED
ARM_A_CLIP_FORWARD_MS = 2775.666
ARM_B_CLIP_FORWARD_MS = NOT MEASURED
ARM_A_WORKER_B_WALL_MS = 5019.5027
ARM_B_WORKER_B_WALL_MS = NOT MEASURED
ARM_A_UNET_READY_FROM_GRAPH_START_MS = 6815.863
ARM_B_UNET_READY_FROM_GRAPH_START_MS = NOT MEASURED
ARM_A_MODEL_READINESS_FROM_GRAPH_START_MS = 6815.863
ARM_B_MODEL_READINESS_FROM_GRAPH_START_MS = NOT MEASURED
ARM_A_POST_CLIP_UNET_TAIL_MS = 2143.427
ARM_B_POST_CLIP_UNET_TAIL_MS = NOT MEASURED
ARM_B_PREFETCH_BYTES = NOT MEASURED
ARM_B_PREFETCH_FRACTION = NOT MEASURED
ARM_B_PREFETCH_WALL_MS = NOT MEASURED
ARM_A_OUTPUT_SHA_MATCH = true
ARM_B_OUTPUT_SHA_MATCH = NOT MEASURED
PLACEMENT_COMPARABILITY = NOT APPLICABLE
QWEN_PREFETCH_OFF_BASELINE_MS = 2775.666
NET_PREFETCH_VALUE_MS = NOT MEASURED
PRIMARY_CAUSAL_FINDING = NONE
TOP_REMAINING_PHASE_E_BOTTLENECK = NOT RE-ranked; E22 remained a harness blocker
NEXT_ACTION = STOP; requires separate authorization and repair of registry-proof priming
```

## Final Verification

```text
SINGLE_RUN_GUARD_PRESERVED = YES
BENCHMARK_EXPLICIT_RUN_COUNT = 1
NEGATIVE_COUNT_2_GUARD = PASS
ARM_B_LOCAL_WRAPPER_PREFLIGHT = PASS
FOCUSED_TESTS = 68 passed
PYCOMPILE = PASS
TARGETED_DIFF_CHECK = PASS (pre-existing unrelated whitespace warning only)
PREVIOUS_FAILED_ATTEMPT_DEPLOYS = 1
PREVIOUS_FAILED_ATTEMPT_PAID_REQUESTS = 6
NEW_ARM_B_DEPLOYMENTS = 1
NEW_ARM_B_PAID_REQUESTS = 0
NEW_REMOTE_LIMIT_EXCEEDED = NO
DIRECT_PYTHON_REMOTE_INVOKE_USED = NO
COMMIT = none
```
