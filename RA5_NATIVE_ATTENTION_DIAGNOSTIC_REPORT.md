# RA5 native attention diagnostic report

## Executive result

The current three-arm Golden cohort provides direct native-leaf evidence for
both requested custom attention backends:

* **Sage:** native profiler leaf observed:
  `sageattention_sm89::qk_int8_sv_f8_accum_f16_fuse_v_scale_attn_inst_buf`.
* **Comfy Kitchen:** native profiler leaf observed:
  `comfy_kitchen::int8_attention`.
* **PyTorch:** request-local PyTorch selection and 340 calls through the shared
  SDPA seam were observed; no custom native-leaf claim is made.

All three requests passed the structural Golden lifecycle checks, including
true-cold identity, durability/reopen, and strict seriality. Only PyTorch
produced the configured canonical PNG SHA. Sage and Comfy Kitchen completed
structurally but produced stable warning-only SHA mismatches.

## Evidence boundary

The raw evidence and exact paths are in
`RA5_NATIVE_ATTENTION_DIAGNOSTIC_RAW_LOG.md`.

Deployment:

```text
.v2ctl/deployments/deploy_20260830-135515_bca54c82.json
deploy_fingerprint=bca54c8265f35c9c9c945344737a418a3d4a101b134fc45693c1e4bb409a0a42
source-probe=PASS / MATCH
doctor=OK
```

Run records:

```text
.v2ctl/runs/run_20260830-135908_3c729a8e.json   # Comfy Kitchen
.v2ctl/runs/run_20260830-140005_b147c216.json   # PyTorch
.v2ctl/runs/run_20260830-140122_dfe04135.json   # Sage
```

The embedded runtime deployment identity was identical across the three
requests (`7501bf53...`) but differs from the control-plane fingerprint
(`bca54c826...`). This is retained as a provenance caveat. The source probe
passed, and the three requests were collected from the same deployment and
snapshot identity.

## Native execution verdict

| Arm | Requested | Observed dispatch | Native evidence | Fallback counters | Verdict |
|---|---|---:|---|---|---|
| Sage | `sage` | 300 override / 1246 `sageattn` calls | 1 profiler event for the Sage SM89 leaf | Enumerated Comfy fallbacks all 0 | Native Sage leaf observed; full-request fallback exclusion not proven |
| Comfy Kitchen | `comfy_kitchen` | 300 override / 340 public `int8_attention` calls | 1 profiler event for `comfy_kitchen::int8_attention` | Enumerated Comfy fallbacks all 0 | Native Kitchen leaf observed; full-request fallback exclusion not proven |
| PyTorch | `pytorch` | 300 override / 340 SDPA calls | Shared SDPA seam observed; profiler not requested | Enumerated Comfy fallbacks all 0 | PyTorch path observed; no custom native-kernel claim |

The native profiler count is intentionally not treated as a full-workload count:
it captures the first requested public custom-backend call. The dispatch and
call counts cover the request's observed attention calls. Missing or unlisted
paths remain unproven rather than being silently classified as zero.

## Structural and output gates

| Gate | Sage | Comfy Kitchen | PyTorch |
|---|---:|---:|---:|
| Valid request | pass | pass | pass |
| True-cold lifecycle | pass | pass | pass |
| `restore_count=1`, `request_count=1` | pass | pass | pass |
| Durable and reopen verified | pass | pass | pass |
| Commit-before-reopen | pass | pass | pass |
| Strict seriality / violations | pass / 0 | pass / 0 | pass / 0 |
| Canonical output SHA | fail: `bfb360...` | fail: `62fd9e...` | pass: `8a9244...` |

Configured expected SHA:

```text
8a92446890bebaecdc10eb5f207766a4b05af40ca3137108e25bfe88d9c1c44e
```

The mismatches are warning-only in the Golden artifacts and do not invalidate
the lifecycle evidence. They do prevent Sage and Kitchen from being called
canonical-output passes.

## Timing result and the approximately 7% question

The authoritative sampling windows were:

| Arm | Sampling ms | Total ms |
|---|---:|---:|
| Sage | 5538.917 | 36771.300 |
| Comfy Kitchen | 5701.638 | 19065.885 |
| PyTorch | 6233.634 | 39408.980 |

For this one request per arm, sampling was 8.54% lower for Kitchen and 11.15%
lower for Sage than PyTorch. The custom backends therefore show the expected
direction and a difference in the rough 7% range, but `n=1` is insufficient for
a stable performance claim. Total request time is dominated by lifecycle and
durability components and should not be attributed to attention.

The direct causal claim is limited to this: native custom leaves were observed,
and the corresponding request-local sampling windows were lower than PyTorch's
in this cohort. A larger same-deployment confirmation cohort is required to
estimate a reliable gain and to separate attention work from restore/startup
variance.

## Decision

The native diagnostic objective is met at the observation level: Sage and
Comfy Kitchen both reached a concrete native CUDA leaf, while PyTorch provides
the exact-output baseline. The result is not a canonical-output win for either
custom backend, and the approximately 7% performance figure should remain a
single-shot directional observation rather than a production performance claim.
