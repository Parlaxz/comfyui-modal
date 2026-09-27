# RA5 native attention diagnostic raw log

**Validation date:** 2026-08-30  
**Application:** `batch-ra5-attention-shootout`  
**Profile:** `golden_p1`  
**Class/method:** `ModalRuntimeEntrypointV2.run_golden_serial_stream`  
**GPU:** `rtx-pro-6000`

This log records the one-request-per-arm diagnostic cohort after the required
redeploy. The control-plane deployment fingerprint is
`bca54c8265f35c9c9c945344737a418a3d4a101b134fc45693c1e4bb409a0a42`.

## Deployment evidence

```text
.v2ctl/deployments/deploy_20260830-135515_bca54c82.json
source probe: PASS / MATCH
doctor: OK
deployment transport: deployed
runtime health: verified
source identity: verified
profile config fingerprint: 61e78501239e6ef65709af80a53249f505af17a834b6f689f94457377a3a6390
git head: b578f77cfdabff73b3c1d66cb9d5c7fcc155ca22
git branch: TESTING2
git dirty: true
COMFYMODAL_SAMPLING_DEEP_PROFILE=blocks
runtime override policy: forbid
```

The remote source probe reported the same image and runtime deployment identity
for all three requests. The embedded runtime identity is
`7501bf53e9bf0a761cc15f3440ab9d3d3d7631c186f0f780180a6f4ffa90c5be`; this is
distinct from the control-plane source/deployment fingerprint and is retained
as an identity caveat rather than normalized away.

## Authoritative run records

| Arm | Run manifest | Cohort | Request ID | Exact selector |
|---|---|---|---|---|
| Comfy Kitchen | `.v2ctl/runs/run_20260830-135908_3c729a8e.json` | `artifacts/phase_p1_serial_golden_v1/cohort_2026-08-30_18-58-48_c29038/` | `golden-p1-0-a16b8e23563a` | `--attention-backend comfy_kitchen` |
| PyTorch | `.v2ctl/runs/run_20260830-140005_b147c216.json` | `artifacts/phase_p1_serial_golden_v1/cohort_2026-08-30_18-59-25_9abc96/` | `golden-p1-0-2b4fd627988d` | `--attention-backend pytorch` |
| Sage | `.v2ctl/runs/run_20260830-140122_dfe04135.json` | `artifacts/phase_p1_serial_golden_v1/cohort_2026-08-30_19-00-44_85e15e/` | `golden-p1-0-d20a44fb26d2` | `--attention-backend sage` |

Each command used `--run-count 1` and the configured expected output SHA
`8a92446890bebaecdc10eb5f207766a4b05af40ca3137108e25bfe88d9c1c44e`.

## Raw per-request results

The authoritative files are each cohort's `attempt_0.json` and
`attempt_0_events.json`.

| Arm | Run fingerprint | Region | Total ms | Sampling window ms | Restore ms | Native profiler | Native leaf evidence | Dispatch evidence | Observed SHA |
|---|---|---:|---:|---:|---:|---|---|---|---|
| Comfy Kitchen | `3c729a8e22e35186f94a39f7018be1644b7ca5037b54525cdcba610e569672ef` | `us-east4` | 19065.885 | 5701.638 | 1037.143 | captured | `comfy_kitchen::int8_attention`, count 1, device 176.288 us | Kitchen override 300; public `int8_attention` 340; PyTorch SDPA 0; Sage 0 | `62fd9e62f36721847780e2ff9c98ddbc3a5b79e5113807d85110605723bc89a7` |
| PyTorch | `b147c216ab7ede15f5a7cbeb68a98c735a6aa229872d03151559bc8c4bcc1c8a` | `us-west1` | 39408.980 | 6233.634 | 1516.241 | not requested | No custom native leaf claim; shared SDPA seam observed | PyTorch override 300; SDPA 340; Kitchen 0; Sage 0 | `8a92446890bebaecdc10eb5f207766a4b05af40ca3137108e25bfe88d9c1c44e` |
| Sage | `dfe04135eccb02aea012329177516fc409f748f6eac393d74c72644ecf5ce670` | `us-east4` | 36771.300 | 5538.917 | 764.068 | captured | `sageattention_sm89::qk_int8_sv_f8_accum_f16_fuse_v_scale_attn_inst_buf`, count 1, device 37.797 us | Sage override 300; `sageattention.sageattn` 1246; PyTorch SDPA 0; Kitchen 0 | `bfb360008914dbacbe594b22dc09fd2b7658fa4d63ed7c25364806ce0b2280ce` |

All three requests recorded:

```text
valid=true
dnf=false
error=null
restore_count=1
request_count=1
true_cold=true
true_durable=true
durable_reopen_verified=true
commit_reopen_ordering_ok=true
seriality.ok=true
seriality.violations=[]
fallback_counts: attention_split=0, attention_sub_quad=0, attention_xformers=0
```

The profiler is a one-shot capture around the first requested public Sage or
Kitchen call. Its native count is direct evidence that a native leaf was seen,
not a full-request kernel count. The enumerated fallback counters were zero in
each artifact; unlisted or unobservable paths are not inferred to be zero.

## Retained invalid/non-cohort attempts

These attempts remain on disk and are excluded from the three-arm comparison:

* `.v2ctl/runs/run_20260830-135805_b147c216.json` was launched with an ambient
  environment assignment, but its effective manifest selector was `pytorch`,
  not Kitchen. It is an invalid selector attempt, not a second Kitchen arm.
* `.v2ctl/runs/run_20260830-134139_170df9e2.json` is the earlier Sage request
  under deployment fingerprint `81cc48a...`; it predates the required redeploy
  and is not mixed into this homogeneous cohort.

## Timing interpretation

This is `n=1` per arm, so no mean, standard deviation, CV, or significance claim
is appropriate. Relative to the PyTorch sampling window:

```text
Comfy Kitchen: 532.0 ms faster, 8.54% lower
Sage:          694.7 ms faster, 11.15% lower
Sage vs Kitchen: Sage 162.7 ms faster, 2.85% lower than Kitchen
```

The total request numbers include restore, startup, and durability work and are
not backend-kernel timings. The roughly 7% improvement discussed in the prior
shootout is directionally consistent with this result, but this single-request
cohort cannot establish a stable percentage or assign the whole difference to
the native attention leaf.
