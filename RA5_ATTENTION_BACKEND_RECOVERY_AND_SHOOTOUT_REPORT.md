# RA5 attention-backend recovery and shootout report

## Executive result

The control-plane deployment, run, gate, and confirmation records bind to the
requested current fingerprint. Every attempt also carries an older embedded
runtime deployment identity, so runtime-level fingerprint equality is not
proven. The three request-local arms were exercised fairly enough for a
selection/timing comparison, but this is **not a native CUDA shootout**. The authoritative manifests prove selected
callables, 340 dispatches per request, true-cold lifecycle identity, durable
reopen, and strict seriality. They do not contain direct Sage or Comfy Kitchen
native-leaf counters, profiler evidence, or fallback counters because
`COMFYMODAL_SAMPLING_DEEP_PROFILE=off`.

The strongest defensible result is therefore:

* PyTorch selected `comfy.ldm.modules.attention.attention_pytorch` and produced
  the configured canonical SHA in all 11 requests.
* Sage selected `sageattention.sageattn` in all 11 requests, but all 11 output
  SHA values were `bfb360008914dbacbe594b22dc09fd2b7658fa4d63ed7c25364806ce0b2280ce`,
  not the configured SHA.
* Comfy Kitchen selected `attention_comfy_kitchen_int8` in all 11 requests,
  but all 11 output SHA values were
  `62fd9e62f36721847780e2ff9c98ddbc3a5b79e5113807d85110605723bc89a7`,
  not the configured SHA.

The mismatch is a warning-only output classification in the manifests, not a
structural invalidation. It must not be hidden or converted into an exactness
pass.

## Evidence boundary and deployment identity

The complete raw ledger is in
`RA5_ATTENTION_BACKEND_RAW_VALIDATION_LOG.md`. Its source set is limited to:

```text
.v2ctl/deployments/deploy_20260830-100940_2b69461c.json
.v2ctl/runs/run_20260830-101125_9ba0a609.json
.v2ctl/runs/run_20260830-101742_f53f9e2d.json
.v2ctl/runs/run_20260830-102259_c0867ba7.json
.v2ctl/gates/gate_20260830-151154_9ba0a609.json
.v2ctl/gates/gate_20260830-151845_f53f9e2d.json
.v2ctl/gates/gate_20260830-152332_c0867ba7.json
.v2ctl/confirmations/confirm_20260830-151715_9ba0a609.json
.v2ctl/confirmations/confirm_20260830-152226_f53f9e2d.json
.v2ctl/confirmations/confirm_20260830-153034_c0867ba7.json
artifacts/phase_p1_serial_golden_v1/cohort_2026-08-30_*/manifest.json
```

Every selected cohort manifest has the requested current deployment fingerprint
`2b69461c941a920030d29e947070a09af3611a374db724f6cb499a0a47046563`. The
deployment manifest records:

```text
app=batch-ra5-attention-shootout
class=ModalRuntimeEntrypointV2
profile=golden_p1
git_head=b578f77cfdabff73b3c1d66cb9d5c7fcc155ca22
profile_config_fingerprint=db93ed3f1bcee190489cb34661a2c3a6a5d48a731928ac9fdc664194dcc60fdf
source_identity_status=verified
runtime_health_status=verified
deployment_transport_status=deployed
```

The three confirmation records say `gate_valid=true`,
`provenance_validation_status=validated`, and `confirm_runs=9`. No standalone
source-probe transcript for this exact fingerprint is retained; the report
uses the deployment-manifest source identity result and does not borrow a
source probe from an older deployment.

### Runtime identity caveat

All 33 selected cohort manifests have the current fingerprint at their
top-level `deployment_identity`, and all control-plane records bind to it.
But all 33 embedded attempt identities and frozen cold-evidence deployment
identities report the older
`d5090136f3aa77cfc84f7bfb6501fa9b9ba6c11e02c6c6f92aa90bea11b4b8be`.
The manifests mark these requests structurally true-cold because the identity
tokens are present; that field is not an equality check against the current
control-plane fingerprint. This is an unresolved provenance limitation, not a
reason to rewrite the current fingerprint or to claim runtime identity match.

## Recovery record

### Failed pre-fix deploy

The retained pre-fix deployment attempts failed before transport at the Golden
publication gate:

| Artifact | Fingerprint | Failure |
|---|---|---|
| `artifacts/phase3_s1_e1_deploy.log` | `1217a640023f6502f84f31294123013c262ede1a2d7b55481a3274aae9f591f9` | `publication_incomplete` |
| `artifacts/phase3_s1_e1_deploy_file_fix.log` | `a0333ce2fa6cd0cf72a60c411516baac6195eebd5135caf5e8afca09b128efa7` | `publication_incomplete` |

### Fix and final landing

The recorded fix repaired the canonical custom-node publication/identity path
while preserving the fail-closed publication gate. The follow-up S1 manifest
`deploy_20260830-090243_6c5893f8.json` records the repaired exact-publication
path. The final RA5 deployment manifest records `published_verified` and the
current fingerprint. That is deployment evidence of the fix landing; it is not
a claim that this report changed source, profile, or registry state.

## Lifecycle and validity gates

All 33 selected requests satisfy the same structural lifecycle contract:

| Contract | Result |
|---|---:|
| Structurally valid | 33/33 |
| Invalid | 0 |
| DNF | 0 |
| True-cold | 33/33 |
| `restore_count=1` and `request_count=1` | 33/33 |
| Single-use containers and `min_containers=0` | 33/33 |
| Frozen deployment/snapshot/config identities present | 33/33 |
| Frozen deployment identity equals current control-plane fingerprint | 0/33 |
| `true_durable_marked` | 33/33 |
| Durable reopen verified | 33/33 |
| Strict seriality | 33/33 |
| Seriality violations | 0 |

The 33 requests are three screens, three gates, and 27 confirmation requests.
Each arm contributes 11 requests. The nine confirmation requests are the
comparison sample; screen and gate requests remain in the audit totals and in
the all-request statistics.

## Backend recovery evidence

The manifest event `attention_backend_selection` is consistent across every
request in an arm:

| Arm | Requested | Selected callable | Dispatches | What is proven | What is not proven |
|---|---|---|---:|---|---|
| Sage | `sage` | `sageattention.sageattn` | 340 × 11 | Request-local Sage callable selection | Native Sage2++ CUDA leaf, kernel activity, and zero fallback |
| Comfy Kitchen | `comfy_kitchen` | `attention_comfy_kitchen_int8` | 340 × 11 | Request-local Kitchen callable selection | Native Kitchen CUDA activity and zero fallback |
| PyTorch | `pytorch` | `comfy.ldm.modules.attention.attention_pytorch` | 340 × 11 | Request-local PyTorch callable selection and canonical output | Direct SDPA leaf counter; no custom native-kernel claim |

The direct evidence fields for fallback/native execution are absent from the
authoritative current manifests. They are consequently **unobserved**, not
zero. A callable label, import, timing, output, or dispatch count cannot be
promoted to native CUDA proof.

## Output classification

Expected SHA for all arms:

```text
8a92446890bebaecdc10eb5f207766a4b05af40ca3137108e25bfe88d9c1c44e
```

| Arm | Structurally valid | Exact SHA | Observed SHA(s) | Classification |
|---|---:|---:|---|---|
| Sage | 11/11 | 0/11 | `bfb360008914dbacbe594b22dc09fd2b7658fa4d63ed7c25364806ce0b2280ce` | warning-only mismatch; not canonical |
| Comfy Kitchen | 11/11 | 0/11 | `62fd9e62f36721847780e2ff9c98ddbc3a5b79e5113807d85110605723bc89a7` | warning-only mismatch; not canonical |
| PyTorch | 11/11 | 11/11 | `8a92446890bebaecdc10eb5f207766a4b05af40ca3137108e25bfe88d9c1c44e` | exact canonical SHA |

Structural validity means the request completed with the required terminal,
durability, identity, coldness, and seriality evidence. It does **not** mean
the PNG is byte-for-byte canonical. Exact SHA is an independent gate.

## Timing shootout

The raw timing table and derivation rules are in the companion log. The
following all-request statistics include screen, gate, and nine confirmations;
sample SD and CV are calculated over the 11 raw values.

| Arm | Metric | mean ms | median ms | min ms | max ms | range ms | sample SD | CV |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| Sage | total | 30861.756 | 20984.601 | 18004.458 | 111648.389 | 93643.931 | 27343.191 | 0.88599 |
| Sage | sampling | 5549.210 | 5531.340 | 5368.315 | 5766.630 | 398.315 | 111.519 | 0.02010 |
| Sage | restore | 994.472 | 819.733 | 620.824 | 2287.414 | 1666.590 | 521.677 | 0.52458 |
| Sage | durable | 1014.451 | 883.410 | 654.661 | 1785.355 | 1130.694 | 385.078 | 0.37959 |
| Comfy Kitchen | total | 24074.846 | 21792.013 | 16667.105 | 52177.880 | 35510.775 | 9495.798 | 0.39443 |
| Comfy Kitchen | sampling | 5529.228 | 5557.517 | 5349.158 | 5656.890 | 307.732 | 104.531 | 0.01891 |
| Comfy Kitchen | restore | 718.597 | 664.079 | 572.055 | 1006.354 | 434.299 | 159.466 | 0.22191 |
| Comfy Kitchen | durable | 898.300 | 936.648 | 739.485 | 1017.938 | 278.453 | 93.222 | 0.10378 |
| PyTorch | total | 39413.534 | 21707.907 | 17985.715 | 158436.589 | 140450.874 | 43418.893 | 1.10162 |
| PyTorch | sampling | 6003.958 | 5977.343 | 5846.403 | 6320.368 | 473.965 | 137.156 | 0.02284 |
| PyTorch | restore | 1049.926 | 923.152 | 678.887 | 1956.888 | 1278.001 | 401.794 | 0.38269 |
| PyTorch | durable | 1158.070 | 1049.670 | 755.743 | 2271.018 | 1515.275 | 513.821 | 0.44369 |

Confirmation-only medians are Sage `total=20984.601`, `sampling=5510.649`;
Comfy Kitchen `total=21792.013`, `sampling=5571.705`; and PyTorch
`total=22324.600`, `sampling=5970.039`. The unusually large total maxima are
visible in the raw ledger and are not removed from the statistics.

## Decision

The current artifacts support a **structurally valid request-local callable
selection comparison** and a reproducible exact-SHA PyTorch baseline. They do
not support declaring recovered native Sage or native Kitchen CUDA execution,
nor declaring either non-PyTorch arm a canonical-output pass. A follow-up
native shootout must deploy with the deep attention profiler/leaf diagnostics
enabled and retain direct native-kernel and fallback evidence for every arm;
the canonical SHA gate must remain independent.
