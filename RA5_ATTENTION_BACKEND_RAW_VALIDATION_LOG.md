# RA5 attention-backend raw validation log

**Validation date:** 2026-08-30  
**Deployment under test:** `batch-ra5-attention-shootout`  
**Deployment fingerprint:** `2b69461c941a920030d29e947070a09af3611a374db724f6cb499a0a47046563`

This log is reconstructed from the authoritative deployment, run, gate,
confirmation, and cohort manifests. Cohorts were selected by their manifest
deployment identity and by the three confirmation paths, not by filesystem
mtime.

## 1. Exact identity and configuration

Authoritative deployment manifest:

```text
.v2ctl/deployments/deploy_20260830-100940_2b69461c.json
```

Recorded deployment command and identity:

```text
modal deploy -m comfymodal_runtime.modal_app --name batch-ra5-attention-shootout
app=batch-ra5-attention-shootout
class=ModalRuntimeEntrypointV2
profile=golden_p1
git_head=b578f77cfdabff73b3c1d66cb9d5c7fcc155ca22
profile_config_fingerprint=db93ed3f1bcee190489cb34661a2c3a6a5d48a731928ac9fdc664194dcc60fdf
deploy_fingerprint=2b69461c941a920030d29e947070a09af3611a374db724f6cb499a0a47046563
```

The manifest records transport `deployed`, `exit_code=0`,
`runtime_health_status=verified`, and `source_identity_status=verified`.
Publication was `published_verified`, generation
`6fccd8ee77fe8f99677761bdb608236f`, 4,273 files, 497,501,933 bytes, manifest
digest `8a0980f6239eebbb2237db88baa2c111b4c3e2305ae8fb789422b5782c26f66e`.

Relevant effective configuration was identical across the three arms unless
noted below: GPU `rtx-pro-6000`, CPU 12, memory 32,768 MiB,
`min_containers=0`, `single_use_containers=1`, `COMFYMODAL_V2_GOLDEN_ENABLE_DYNAMIC_VRAM=1`,
`COMFYMODAL_V2_GOLDEN_WORKFLOW_HASH_CHECK=1`, `COMFYMODAL_V2_SAMPLING_DEEP_PROFILE=off`,
`COMFYMODAL_V2_CPU_MODEL_SNAPSHOT=0`, `COMFYMODAL_V2_SNAPSHOT_MODEL_ORDER=O0`,
`COMFYMODAL_V2_THREAD_POLICY=TBASE`, `COMFYMODAL_V2_RELEASE_GPU_AFTER_REQUEST=1`,
and runtime override policy `forbid`.

Configured expected output SHA:

```text
8a92446890bebaecdc10eb5f207766a4b05af40ca3137108e25bfe88d9c1c44e
```

Configured workflow capture hash was
`14f815f1916e075ae79de7325681f6b0ec2216b8ad86c45e9bfa18f6388f5ea9`.
Every run also recorded the same effective runtime workflow hash
`e44389ea2eda82ba5e2328acc08307b6879ed6d4ea4b030727ab044704c0d3b5`.

The three authoritative `v2ctl` run records preserve the exact arm commands:

| Arm | Run record | Exact backend command | Run/profile identity |
|---|---|---|---|
| Sage | `.v2ctl/runs/run_20260830-101125_9ba0a609.json` | `"C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\run_v2_single.bat" --run-count 1 --golden-p1-expected-output-sha 8a92446890bebaecdc10eb5f207766a4b05af40ca3137108e25bfe88d9c1c44e --attention-backend sage` | run `9ba0a609700ba10afff279a7d3126f1b8839efa222de790680ccb098439b53ea`; profile `6a89350b13f48701439d2c8fe18dc8c9da2761421a289c638fb1b8c7858f2e8f` |
| Comfy Kitchen | `.v2ctl/runs/run_20260830-101742_f53f9e2d.json` | `"C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\run_v2_single.bat" --run-count 1 --golden-p1-expected-output-sha 8a92446890bebaecdc10eb5f207766a4b05af40ca3137108e25bfe88d9c1c44e --attention-backend comfy_kitchen` | run `f53f9e2dbd1ba59c6e2a17172911db5b2c2bc5fa6bc97b72f7a7c93a5441dada`; profile `8a9e8374f8e81028cdd3aadedf867718608bf7c70448ea1bc8b2d24abfb51eb2` |
| PyTorch | `.v2ctl/runs/run_20260830-102259_c0867ba7.json` | `"C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\run_v2_single.bat" --run-count 1 --golden-p1-expected-output-sha 8a92446890bebaecdc10eb5f207766a4b05af40ca3137108e25bfe88d9c1c44e --attention-backend pytorch` | run `c0867ba70173d69a1b8e1cdb32fac6d2a8e3d70c50d07988dff9847d0127ec01`; profile `db93ed3f1bcee190489cb34661a2c3a6a5d48a731928ac9fdc664194dcc60fdf` |

## 2. Deployment and source-probe evidence

The current deployment manifest is the authoritative current identity record:
it says `deployment_transport_status=deployed`,
`runtime_health_status=verified`, and `source_identity_status=verified`, with
the exact fingerprint above. The three current gate manifests and three
current confirmation manifests all bind to that same fingerprint and have
`provenance_validation_status=validated`.

There is an important manifest-level identity caveat. The top-level deployment
identity in all 33 selected cohort manifests and the control-plane run/gate/
confirmation records is the requested current fingerprint. However, every
attempt's embedded `identity.deployment_fingerprint` and
`cold_evidence.frozen_identities.deployment` is the older value
`d5090136f3aa77cfc84f7bfb6501fa9b9ba6c11e02c6c6f92aa90bea11b4b8be` (33/33),
with snapshot identity
`bf9435704a92c188c1f2534eb0a56b1ae8d2fe653d4b3aa2931578ec390fc3cb`.
The structural cold validator checks that those frozen identity fields are
present; it does not make them equal to the current control-plane fingerprint.
This unresolved discrepancy is retained here and prevents claiming a
runtime-level fingerprint match. It does not change the manifest `valid` or
`true_cold` fields.

There is no separately retained current-fingerprint `source-probe` transcript
in the repository. Accordingly, this log records the manifest-level source
identity result, but does not substitute a stale source-probe transcript from
another deployment. The current deployment manifest and the confirmation
provenance fields are positive deployment/source identity evidence; they are
not native-kernel evidence.

## 3. Failed pre-fix deploy and fix record

The retained pre-fix control-plane attempts are:

| Artifact | Attempted fingerprint | Result |
|---|---|---|
| `artifacts/phase3_s1_e1_deploy.log` | `1217a640023f6502f84f31294123013c262ede1a2d7b55481a3274aae9f591f9` | failed before transport: `Golden deploy requires verified custom-node publication: publication_incomplete` |
| `artifacts/phase3_s1_e1_deploy_file_fix.log` | `a0333ce2fa6cd0cf72a60c411516baac6195eebd5135caf5e8afca09b128efa7` | same publication gate failure |

The recorded fix was to repair the canonical custom-node publication/identity
path and retain the publication verification gate. The successful follow-up
manifest `deploy_20260830-090243_6c5893f8.json` records the repaired
`skip_exact` publication path. The final RA5 deployment above records
`published_verified`; no source, profile, or registry files were changed for
this report.

## 4. Cohort selection and raw per-request evidence

Each arm has 11 manifest-bound requests: one screen, one gate, and nine
confirmation requests. Confirmation paths are:

```text
.v2ctl/confirmations/confirm_20260830-151715_9ba0a609.json  (Sage)
.v2ctl/confirmations/confirm_20260830-152226_f53f9e2d.json  (Comfy Kitchen)
.v2ctl/confirmations/confirm_20260830-153034_c0867ba7.json  (PyTorch)
```

All three have `confirm_runs=9`, `gate_valid=true`, and a gate manifest bound
to the same current deployment fingerprint. In the table below, `total` is
the manifest `duration_ms`; `sampling` is the measured
`golden_sampling` stage; `restore` is `external_restore.restore_total_ms`;
and `durable` is derived from the raw `VOLUME_COMMIT_START` to
`durable_reopen_verified` monotonic timestamps. `resume→durable` is derived
from the raw remote Python resume timestamp to `TRUE_FIRST_DURABLE_RESULT`.

| Arm / role | Cohort | Request ID | total ms | sampling ms | restore ms | durable ms | resume→durable ms | Structural | SHA classification |
|---|---|---|---:|---:|---:|---:|---:|---|---|
| Sage / screen | `15-10-59_416198` | `golden-p1-0-42e80f082e39` | 25406.714 | 5678.234 | 2287.414 | 1681.064 | 17437.892 | valid, cold, durable, serial | mismatch: `bfb360008914dbacbe594b22dc09fd2b7658fa4d63ed7c25364806ce0b2280ce` |
| Sage / gate | `15-11-35_e341e6` | `golden-p1-0-4fb698f2704e` | 18004.458 | 5766.630 | 725.837 | 817.128 | 14654.770 | valid, cold, durable, serial | mismatch: `bfb360008914dbacbe594b22dc09fd2b7658fa4d63ed7c25364806ce0b2280ce` |
| Sage / confirm | `15-12-04_128969` | `golden-p1-0-6d670903ebc2` | 18155.027 | 5536.644 | 623.422 | 883.410 | 14908.759 | valid, cold, durable, serial | mismatch: `bfb360008914dbacbe594b22dc09fd2b7658fa4d63ed7c25364806ce0b2280ce` |
| Sage / confirm | `15-12-23_473f05` | `golden-p1-0-660ec0c7378b` | 111648.389 | 5368.315 | 878.994 | 654.661 | 12427.507 | valid, cold, durable, serial | mismatch: `bfb360008914dbacbe594b22dc09fd2b7658fa4d63ed7c25364806ce0b2280ce` |
| Sage / confirm | `15-14-17_92cee7` | `golden-p1-0-4ae53db74f71` | 23644.905 | 5531.340 | 1688.206 | 1785.355 | 16142.649 | valid, cold, durable, serial | mismatch: `bfb360008914dbacbe594b22dc09fd2b7658fa4d63ed7c25364806ce0b2280ce` |
| Sage / confirm | `15-14-44_7c7ba2` | `golden-p1-0-f7871cfa0686` | 20513.116 | 5579.612 | 952.120 | 721.365 | 14796.957 | valid, cold, durable, serial | mismatch: `bfb360008914dbacbe594b22dc09fd2b7658fa4d63ed7c25364806ce0b2280ce` |
| Sage / confirm | `15-15-06_63220a` | `golden-p1-0-a3e4c0326433` | 20615.159 | 5639.043 | 819.733 | 728.633 | 14560.312 | valid, cold, durable, serial | mismatch: `bfb360008914dbacbe594b22dc09fd2b7658fa4d63ed7c25364806ce0b2280ce` |
| Sage / confirm | `15-15-29_a8175d` | `golden-p1-0-f427479a1ae2` | 21733.107 | 5494.474 | 803.970 | 1084.283 | 12999.944 | valid, cold, durable, serial | mismatch: `bfb360008914dbacbe594b22dc09fd2b7658fa4d63ed7c25364806ce0b2280ce` |
| Sage / confirm | `15-15-52_2b86ae` | `golden-p1-0-25c204b108e7` | 20899.232 | 5510.649 | 902.981 | 750.492 | 13043.195 | valid, cold, durable, serial | mismatch: `bfb360008914dbacbe594b22dc09fd2b7658fa4d63ed7c25364806ce0b2280ce` |
| Sage / confirm | `15-16-15_9463c4` | `golden-p1-0-de2e54fac7ae` | 20984.601 | 5450.314 | 620.824 | 1116.296 | 13292.734 | valid, cold, durable, serial | mismatch: `bfb360008914dbacbe594b22dc09fd2b7658fa4d63ed7c25364806ce0b2280ce` |
| Sage / confirm | `15-16-37_472a18` | `golden-p1-0-1c4b003eb467` | 37874.609 | 5486.054 | 635.689 | 936.269 | 12711.577 | valid, cold, durable, serial | mismatch: `bfb360008914dbacbe594b22dc09fd2b7658fa4d63ed7c25364806ce0b2280ce` |
| Comfy Kitchen / screen | `15-17-25_4073b4` | `golden-p1-0-b67ac870b7ea` | 16667.105 | 5349.158 | 606.148 | 944.958 | 12556.722 | valid, cold, durable, serial | mismatch: `62fd9e62f36721847780e2ff9c98ddbc3a5b79e5113807d85110605723bc89a7` |
| Comfy Kitchen / gate | `15-17-52_ff07bf` | `golden-p1-0-e34b880cce2c` | 52177.880 | 5401.366 | 664.079 | 812.805 | 12575.335 | valid, cold, durable, serial | mismatch: `62fd9e62f36721847780e2ff9c98ddbc3a5b79e5113807d85110605723bc89a7` |
| Comfy Kitchen / confirm | `15-18-53_f49b0f` | `golden-p1-0-71b35e16a4f9` | 21922.932 | 5656.890 | 598.243 | 998.442 | 13301.957 | valid, cold, durable, serial | mismatch: `62fd9e62f36721847780e2ff9c98ddbc3a5b79e5113807d85110605723bc89a7` |
| Comfy Kitchen / confirm | `15-19-18_1d448b` | `golden-p1-0-6b042c000d22` | 22856.752 | 5557.517 | 609.071 | 856.409 | 15624.314 | valid, cold, durable, serial | mismatch: `62fd9e62f36721847780e2ff9c98ddbc3a5b79e5113807d85110605723bc89a7` |
| Comfy Kitchen / confirm | `15-19-43_d8f186` | `golden-p1-0-25ad09c22c47` | 20466.208 | 5547.137 | 613.576 | 766.623 | 12762.497 | valid, cold, durable, serial | mismatch: `62fd9e62f36721847780e2ff9c98ddbc3a5b79e5113807d85110605723bc89a7` |
| Comfy Kitchen / confirm | `15-20-05_560ad4` | `golden-p1-0-bba9448a8e11` | 21184.984 | 5571.705 | 691.635 | 936.648 | 13303.936 | valid, cold, durable, serial | mismatch: `62fd9e62f36721847780e2ff9c98ddbc3a5b79e5113807d85110605723bc89a7` |
| Comfy Kitchen / confirm | `15-20-29_ada20d` | `golden-p1-0-97e6163401c8` | 20098.064 | 5446.201 | 572.055 | 945.477 | 13173.124 | valid, cold, durable, serial | mismatch: `62fd9e62f36721847780e2ff9c98ddbc3a5b79e5113807d85110605723bc89a7` |
| Comfy Kitchen / confirm | `15-20-50_5ffe1f` | `golden-p1-0-78bd6a1bef02` | 21674.343 | 5590.145 | 905.861 | 969.275 | 13391.558 | valid, cold, durable, serial | mismatch: `62fd9e62f36721847780e2ff9c98ddbc3a5b79e5113807d85110605723bc89a7` |
| Comfy Kitchen / confirm | `15-21-14_5b9f03` | `golden-p1-0-ca434a554430` | 21792.013 | 5643.186 | 675.557 | 893.243 | 13334.586 | valid, cold, durable, serial | mismatch: `62fd9e62f36721847780e2ff9c98ddbc3a5b79e5113807d85110605723bc89a7` |
| Comfy Kitchen / confirm | `15-21-38_c48aca` | `golden-p1-0-451ca8c52cee` | 23451.332 | 5623.123 | 1006.354 | 739.485 | 16247.163 | valid, cold, durable, serial | mismatch: `62fd9e62f36721847780e2ff9c98ddbc3a5b79e5113807d85110605723bc89a7` |
| Comfy Kitchen / confirm | `15-22-03_f5949b` | `golden-p1-0-7d684597b3c0` | 22531.693 | 5435.082 | 961.989 | 1017.938 | 13223.106 | valid, cold, durable, serial | mismatch: `62fd9e62f36721847780e2ff9c98ddbc3a5b79e5113807d85110605723bc89a7` |
| PyTorch / screen | `15-22-39_17af1b` | `golden-p1-0-92c33b01b368` | 19128.361 | 6097.442 | 924.948 | 829.116 | 15375.430 | valid, cold, durable, serial | exact: `8a92446890bebaecdc10eb5f207766a4b05af40ca3137108e25bfe88d9c1c44e` |
| PyTorch / gate | `15-23-13_2efd76` | `golden-p1-0-cb460a30a014` | 17985.715 | 5996.879 | 885.612 | 809.780 | 13654.999 | valid, cold, durable, serial | exact: `8a92446890bebaecdc10eb5f207766a4b05af40ca3137108e25bfe88d9c1c44e` |
| PyTorch / confirm | `15-23-45_a76986` | `golden-p1-0-25d545e48f09` | 21072.950 | 5846.403 | 1669.866 | 2043.742 | 16938.557 | valid, cold, durable, serial | exact: `8a92446890bebaecdc10eb5f207766a4b05af40ca3137108e25bfe88d9c1c44e` |
| PyTorch / confirm | `15-24-07_952598` | `golden-p1-0-d1f34e89038c` | 81384.721 | 5891.999 | 678.887 | 1120.621 | 13612.017 | valid, cold, durable, serial | exact: `8a92446890bebaecdc10eb5f207766a4b05af40ca3137108e25bfe88d9c1c44e` |
| PyTorch / confirm | `15-25-30_79db52` | `golden-p1-0-139de3bdc13a` | 23692.047 | 5970.039 | 923.152 | 1096.896 | 14273.191 | valid, cold, durable, serial | exact: `8a92446890bebaecdc10eb5f207766a4b05af40ca3137108e25bfe88d9c1c44e` |
| PyTorch / confirm | `15-25-56_ff15b4` | `golden-p1-0-88ee8fee218f` | 158436.589 | 5950.629 | 735.541 | 773.577 | 15538.420 | valid, cold, durable, serial | exact: `8a92446890bebaecdc10eb5f207766a4b05af40ca3137108e25bfe88d9c1c44e` |
| PyTorch / confirm | `15-28-36_ab6452` | `golden-p1-0-2cf1c1c66eb7` | 22324.600 | 5855.032 | 892.997 | 1049.670 | 15071.266 | valid, cold, durable, serial | exact: `8a92446890bebaecdc10eb5f207766a4b05af40ca3137108e25bfe88d9c1c44e` |
| PyTorch / confirm | `15-29-00_f2a2f3` | `golden-p1-0-5804768337ac` | 20533.622 | 6011.301 | 785.371 | 933.880 | 15035.447 | valid, cold, durable, serial | exact: `8a92446890bebaecdc10eb5f207766a4b05af40ca3137108e25bfe88d9c1c44e` |
| PyTorch / confirm | `15-29-22_5bf17c` | `golden-p1-0-c7288cf5b7bb` | 21377.768 | 5977.343 | 954.008 | 755.743 | 14582.003 | valid, cold, durable, serial | exact: `8a92446890bebaecdc10eb5f207766a4b05af40ca3137108e25bfe88d9c1c44e` |
| PyTorch / confirm | `15-29-45_d486de` | `golden-p1-0-df25d1ef0ebe` | 21707.907 | 6126.099 | 1141.914 | 1054.722 | 16046.158 | valid, cold, durable, serial | exact: `8a92446890bebaecdc10eb5f207766a4b05af40ca3137108e25bfe88d9c1c44e` |
| PyTorch / confirm | `15-30-08_505634` | `golden-p1-0-cbc9a469dd0a` | 25904.591 | 6320.368 | 1956.888 | 2271.018 | 18337.857 | valid, cold, durable, serial | exact: `8a92446890bebaecdc10eb5f207766a4b05af40ca3137108e25bfe88d9c1c44e` |

## 5. Backend evidence and limitations

Every run recorded 340 selections from
`active_unet_model_patcher_transformer_options`:

| Requested arm | Selected callable in all 11 manifests | Fallback evidence | Native-CUDA evidence |
|---|---|---|---|
| Sage | `sageattention.sageattn` | No fallback counter/leaf trace retained; **unobserved** | No profiler, kernel marker, or direct native-leaf counter retained; **unobserved** |
| Comfy Kitchen | `attention_comfy_kitchen_int8` | No fallback counter/leaf trace retained; **unobserved** | No profiler, kernel marker, or direct native-leaf counter retained; **unobserved** |
| PyTorch | `comfy.ldm.modules.attention.attention_pytorch` | No fallback counter/leaf trace retained; **unobserved** | No native custom-kernel claim; selected callable evidence only |

`COMFYMODAL_SAMPLING_DEEP_PROFILE=off` is recorded in the authoritative run
manifests. Therefore a selected callable and 340 dispatches prove request-local
selection, not execution of a Sage or Kitchen CUDA leaf. No arm is silently
classified as native. This is also why fallback counts are `unobserved`, not
zero.

## 6. Summary statistics

Statistics use all 11 manifest-bound requests per arm. SD is **sample** SD and
CV is sample SD divided by the mean. `resume→durable` is a derived timing, not
a backend-kernel timing.

| Arm | Metric (ms) | n | mean | median | min | max | range | sample SD | CV |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Sage | total | 11 | 30861.756 | 20984.601 | 18004.458 | 111648.389 | 93643.931 | 27343.191 | 0.88599 |
| Sage | sampling | 11 | 5549.210 | 5531.340 | 5368.315 | 5766.630 | 398.315 | 111.519 | 0.02010 |
| Sage | restore | 11 | 994.472 | 819.733 | 620.824 | 2287.414 | 1666.590 | 521.677 | 0.52458 |
| Sage | durable | 11 | 1014.451 | 883.410 | 654.661 | 1785.355 | 1130.694 | 385.078 | 0.37959 |
| Sage | resume→durable | 11 | 14270.572 | 14560.312 | 12427.507 | 17437.892 | 5010.385 | 1560.672 | 0.10936 |
| Comfy Kitchen | total | 11 | 24074.846 | 21792.013 | 16667.105 | 52177.880 | 35510.775 | 9495.798 | 0.39443 |
| Comfy Kitchen | sampling | 11 | 5529.228 | 5557.517 | 5349.158 | 5656.890 | 307.732 | 104.531 | 0.01891 |
| Comfy Kitchen | restore | 11 | 718.597 | 664.079 | 572.055 | 1006.354 | 434.299 | 159.466 | 0.22191 |
| Comfy Kitchen | durable | 11 | 898.300 | 936.648 | 739.485 | 1017.938 | 278.453 | 93.222 | 0.10378 |
| Comfy Kitchen | resume→durable | 11 | 13590.391 | 13301.957 | 12556.722 | 16247.163 | 3690.441 | 1206.596 | 0.08878 |
| PyTorch | total | 11 | 39413.534 | 21707.907 | 17985.715 | 158436.589 | 140450.874 | 43418.893 | 1.10162 |
| PyTorch | sampling | 11 | 6003.958 | 5977.343 | 5846.403 | 6320.368 | 473.965 | 137.156 | 0.02284 |
| PyTorch | restore | 11 | 1049.926 | 923.152 | 678.887 | 1956.888 | 1278.001 | 401.794 | 0.38269 |
| PyTorch | durable | 11 | 1158.070 | 1049.670 | 755.743 | 2271.018 | 1515.275 | 513.821 | 0.44369 |
| PyTorch | resume→durable | 11 | 15315.031 | 15071.266 | 13612.017 | 18337.857 | 4725.840 | 1406.333 | 0.09183 |

Confirmation-only (`n=9`, excluding the screen and gate) total/sampling
statistics are:

| Arm | Metric | mean | median | min | max | range | sample SD | CV |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| Sage | total ms | 32896.461 | 20984.601 | 18155.027 | 111648.389 | 93493.362 | 30091.887 | 0.91475 |
| Sage | sampling ms | 5510.716 | 5510.649 | 5368.315 | 5639.043 | 270.729 | 76.739 | 0.01393 |
| Comfy Kitchen | total ms | 21775.369 | 21792.013 | 20098.064 | 23451.332 | 3353.268 | 1087.332 | 0.04993 |
| Comfy Kitchen | sampling ms | 5563.443 | 5571.705 | 5435.082 | 5656.890 | 221.808 | 79.023 | 0.01420 |
| PyTorch | total ms | 44048.311 | 22324.600 | 20533.622 | 158436.589 | 137902.967 | 47154.046 | 1.07051 |
| PyTorch | sampling ms | 5994.357 | 5970.039 | 5846.403 | 6320.368 | 473.965 | 149.373 | 0.02492 |

## 7. Totals and validity interpretation

```text
arms=3
screen_runs=3
gate_runs=3
confirmation_runs=27
total_requests=33
structurally_valid=33
invalid=0
dnf=0
true_cold=33
true_durable_marked=33
durable_reopen_verified=33
strict_serial=33
seriality_violations=0
exact_SHA_matches=11 (PyTorch 11, Sage 0, Comfy Kitchen 0)
SHA_warnings=22 (Sage 11, Comfy Kitchen 11)
```

Structural validity and exact PNG SHA are separate gates. The Sage and Comfy
Kitchen rows are structurally valid, durable, and serial, while every one has
the recorded warning-only SHA mismatch. They are not canonical-output passes.
The PyTorch rows are both structurally valid and exact-SHA matches.
