# September UNET/CLIP Experiment 00 — Current-Bundle Baseline

PERFORMANCE_COMPARISON=NOT_PERFORMED

PERFORMANCE_VERDICT=NOT_PROVIDED

STATUS=COMPLETE

No cross-experiment comparison is made in this file. No performance verdict
of any kind exists here.

## 1. Identity and frozen bundle

| field | value |
|---|---|
| worktree | `C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal` |
| branch | `TESTING2` |
| implementation HEAD | `4ae7606111e7b801b4e3c51de85d65e48995afd8` |
| tracked diff at deploy | none (clean; `git diff` 0 bytes) |
| untracked at deploy | 8 pre-existing `EXPERIMENT_EVIDENCE_*.md`, 2 `RX9P_*.md`, `unetClipExperimentsSeptember/` (option-2 contaminated bundle, explicitly selected and recorded) |
| experiment/app | `sept-unetclip-00-baseline` (isolated; production `stable-modal-comfy-v2-golden-p1` untouched) |
| profile | `golden_p1` |
| class / method | `ModalRuntimeEntrypointV2` / `run_golden_serial_stream` |
| GPU / CPU / mem | `rtx-pro-6000` / 4 / 8192 MiB, `min_containers=0`, scaledown 4s |
| deploy fingerprint | `da2725b851d126ec06ba12cc6723a6a6f34041ccf6c62a334ff2b1330c0385cc` |
| deployment manifest | `.v2ctl/deployments/deploy_20260903-120412_da2725b8.json` |
| deployment receipt | `.v2ctl/deployments/receipt_3_da2725b851d126ec06ba12cc6723a6a6f34041ccf6c62a334ff2b1330c0385cc.json` |
| EXPERIMENT_ID / content generation | `ee753bfa1c0246ff8bf944e50964b13d` / `6d194f5faed9` |
| deployment combined hash (remote) | `55c2ad63e7d55b84` |
| run fingerprint (cohort) | `9cdc0fd2ad74b3bb530ef000d7f70b212c0f0aec8327626cedb38f82de36c8ae` |
| workflow SHA | `e44389ea2eda82ba5e2328acc08307b6879ed6d4ea4b030727ab044704c0d3b5` (expected == actual, check enabled, not bypassed) |
| model identity | CLIP `lumina2` (`qwen3_4b`, bf16 residency, 398 adopted params); UNET 453 tensors assign_true; VAE 244 params fp32; 60 workflow nodes; attention `pytorch`; SAGE `auto`→`baked_cuda`; QD arm `static_e27` |
| expected output SHA (profile/workload) | `8a92446890bebaecdc10eb5f207766a4b05af40ca3137108e25bfe88d9c1c44e` |
| skill-identity SHA (reference only) | `454dbda2939f4abadabd8ca6c524d3a615f384ce19873faf5adaf4693c1848da` |
| SHA policy | both recorded; current-bundle semantics retained; no new SHA gate introduced; every counted run matched expected SHA exactly |

Effective environment highlights: `COMFYMODAL_GOLDEN_QD_TRANSPORT=static_e27`,
`COMFYMODAL_GOLDEN_STAGE_DIAGNOSTICS=0`, `COMFYMODAL_V2_FULL_TRACE=1`,
`COMFYMODAL_V2_E27_FORENSICS=1`, `COMFYMODAL_SAMPLING_DEEP_PROFILE=blocks`,
`COMFYMODAL_SAGE_RUNTIME_MODE=auto`, `COMFYMODAL_OUTPUT_DURABILITY=off`,
`COMFYMODAL_V2_CLIP_SNAPSHOT_EXCLUDE_WEIGHTS=1`,
`COMFYMODAL_V2_SINGLE_USE_CONTAINERS=1`, `COMFYMODAL_MINIMAL_RESTORE=1`,
conditioning cache forced-miss, 35s inter-request gap. Runtime overrides: 0.
Deploy lock: none.

Post-deploy local changes (recorded, remote unaffected — image immutable):
`tools/v2_control/cli.py` gained `--acknowledge-volume-drift` (operator gate
acknowledgment; see Appendix F); `.opencode/skills/comfymodal-golden-ops/SKILL.md`
documents it; a concurrent lane edited runtime files mid-cohort (see Appendix E).

## 2. Attempt ledger (deployment da2725b8; all serial, one request per invocation)

| attempt | invocation | request | provider/region | guard record | role |
|---|---|---|---|---|---|
| PRE1 | `8088a8ce0adc44d0` | `golden-p1-0-4880cda674a0` | GCP asia-south1 | ELIGIBLE | PRE_CAPTURE_UNCOUNTED, retained |
| PRE2 | `7bf4f53dfd404c89` | `golden-p1-0-711b798468ff` | GCP us-east1 | ELIGIBLE | PRE_CAPTURE_UNCOUNTED, retained |
| PRE3 | `3916d2e167e94868` | `golden-p1-0-80eb013ed7c8` | GCP us-east1 | ELIGIBLE | PRE_CAPTURE_UNCOUNTED, retained |
| PRE4 | `b062782af4884be6` | `golden-p1-0-d1d2a5e1dfaf` | GCP us-east1 | ELIGIBLE | PRE_CAPTURE_UNCOUNTED, retained |
| S | `5fbe85f45830404f` | `golden-p1-0-794c5656f5d6` | AWS eu-south-2 | ELIGIBLE (disputed, see below) | OPERATOR-ASSERTED SNAPSHOT_CAPTURE; invalid, retained, not counted |
| P | `74920442013c440c` | `golden-p1-0-e56659ccc2cf` | GCP asia-south1 | ELIGIBLE | INVALID_DIRECTLY_AFTER_SNAPSHOT_CAPTURE by override boundary; retained, not counted |
| R1 | `74364aa898644799` | `golden-p1-0-da5db9a90465` | GCP us-east1 | ELIGIBLE | counted |
| R2 | `0474d478ce3245d6` | `golden-p1-0-a87e00599464` | GCP us-east1 | ELIGIBLE | counted |
| R3 | `0308695d024e41d5` | `golden-p1-0-0f8426679f32` | GCP us-east1 | ELIGIBLE | counted |
| R4 | `b55885b5864a47e1` | `golden-p1-0-b3abc38a8e5d` | GCP asia-south1 | ELIGIBLE | counted |
| R5 | `3a982925da824d2d` | `golden-p1-0-b9bdf55d330e` | GCP us-east1 | ELIGIBLE | counted |

Capture-boundary note: the authoritative `GoldenCaptureGuard` record for S reads
`ELIGIBLE/idle/no-transition`. The operator asserted a request-time snapshot
capture from external observation (first AWS eu-south-2 appearance — a provider/
region/worker switch, the classic capture trigger). Both facts are preserved:
S and P are classified by the operator-asserted boundary and excluded from all
statistics; the guard's disagreement is recorded, not hidden. No further capture
fired during R1–R5 (guard idle throughout), so no re-arm handling was needed.

R1–R5 ran with `--acknowledge-volume-drift` (manifest env
`COMFYMODAL_V2CTL_ACKNOWLEDGED_VOLUME_DRIFT=1`); S/P/PRE ran without it. The
flag changes no remote code path — all runs bind the same immutable receipt.

**Exact five eligible request IDs:** `golden-p1-0-da5db9a90465`,
`golden-p1-0-a87e00599464`, `golden-p1-0-0f8426679f32`,
`golden-p1-0-b3abc38a8e5d`, `golden-p1-0-b9bdf55d330e`.

## 3. Five-run stage table (ms unless noted; authoritative TOTAL walls)

| stage | R1 | R2 | R3 | R4 | R5 |
|---|---|---|---|---|---|
| provider / region | GCP us-east1 | GCP us-east1 | GCP us-east1 | GCP asia-south1 | GCP us-east1 |
| external restore (`restore_total_ms`) | 735.989 | 535.832 | 631.899 | 1446.984 | 569.961 |
| Golden restore (stage wall) | 8.328 | 8.348 | 9.503 | 9.290 | 9.414 |
| request setup | 1.100 | 1.380 | 1.611 | 1.501 | 1.152 |
| CLIP load | 3227.756 | 1951.873 | 2875.247 | 1547.067 | 1852.897 |
| CLIP forward | 1346.597 | 1489.939 | 1469.270 | 1341.982 | 1366.727 |
| UNET load | 3595.857 | 1826.549 | 3755.734 | 1863.564 | 3359.715 |
| sampler prepare | 430.496 | 347.667 | 315.671 | 289.731 | 299.698 |
| VAE load | 468.263 | 146.065 | 467.036 | 107.668 | 125.169 |
| sampling | 6102.154 | 6074.167 | 6170.684 | 6000.834 | 6015.135 |
| sampler tail | 0.014 | 0.015 | 0.013 | 0.011 | 0.015 |
| VAE decode | 505.925 | 532.119 | 531.549 | 524.723 | 524.622 |
| output / result preparation | 164.239 | 164.677 | 163.084 | 161.468 | 165.380 |
| durability boundary | FIRST_RESULT_READY (off; `result_durable=false`) | same | same | same | same |
| teardown | 0.164 | 0.179 | 0.173 | 0.150 | 0.147 |
| resume → FIRST_RESULT_READY | 16986.763 | 13465.888 | 16756.991 | 13881.148 | 14665.410 |
| Golden restore → teardown | 15864.631 | 12558.513 | 15775.040 | 11861.672 | 13736.385 |
| backend request wall | 480454.000 | 86062.000 | 169828.000 | 51672.000 | 39766.000 |

Notes: `golden_restore` stage wall (~8–9ms) is the observation-only Python span;
the 535–1447ms platform restore is the separate `external_restore_interval`
column — never substituted for each other. Backend wall is invoke→result
(queue-dominated; see statistics CV). Output: 3118036 bytes every run, SHA match.

## 4. Statistics table (five eligible runs only; no p90 from n=5)

| metric | R1 | R2 | R3 | R4 | R5 | min | max | range | mean | median | sample SD | CV |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| ext_restore | 735.989 | 535.832 | 631.899 | 1446.984 | 569.961 | 535.832 | 1446.984 | 911.152 | 784.133 | 631.899 | 378.281 | 0.4824 |
| backend_wall | 480454.000 | 86062.000 | 169828.000 | 51672.000 | 39766.000 | 39766.000 | 480454.000 | 440688.000 | 165556.400 | 86062.000 | 183229.000 | 1.1067 |
| resume_frr | 16986.763 | 13465.888 | 16756.991 | 13881.148 | 14665.410 | 13465.888 | 16986.763 | 3520.875 | 15151.240 | 14665.410 | 1630.733 | 0.1076 |
| restore_teardown | 15864.631 | 12558.513 | 15775.040 | 11861.672 | 13736.385 | 11861.672 | 15864.631 | 4002.959 | 13959.248 | 13736.385 | 1826.139 | 0.1308 |
| s_restore | 8.328 | 8.348 | 9.503 | 9.290 | 9.414 | 8.328 | 9.503 | 1.175 | 8.977 | 9.290 | 0.588 | 0.0655 |
| s_setup | 1.100 | 1.380 | 1.611 | 1.501 | 1.152 | 1.100 | 1.611 | 0.511 | 1.349 | 1.380 | 0.220 | 0.1631 |
| s_clipload | 3227.756 | 1951.873 | 2875.247 | 1547.067 | 1852.897 | 1547.067 | 3227.756 | 1680.689 | 2290.968 | 1951.873 | 720.977 | 0.3147 |
| s_clipfwd | 1346.597 | 1489.939 | 1469.270 | 1341.982 | 1366.727 | 1341.982 | 1489.939 | 147.957 | 1402.903 | 1366.727 | 71.011 | 0.0506 |
| s_unet | 3595.857 | 1826.549 | 3755.734 | 1863.564 | 3359.715 | 1826.549 | 3755.734 | 1929.185 | 2880.284 | 3359.715 | 955.561 | 0.3318 |
| s_samplerprep | 430.496 | 347.667 | 315.671 | 289.731 | 299.698 | 289.731 | 430.496 | 140.765 | 336.653 | 315.671 | 56.867 | 0.1689 |
| s_vae | 468.263 | 146.065 | 467.036 | 107.668 | 125.169 | 107.668 | 468.263 | 360.595 | 262.840 | 146.065 | 187.458 | 0.7132 |
| s_sampling | 6102.154 | 6074.167 | 6170.684 | 6000.834 | 6015.135 | 6000.834 | 6170.684 | 169.850 | 6072.595 | 6074.167 | 68.828 | 0.0113 |
| s_tail | 0.014 | 0.015 | 0.013 | 0.011 | 0.015 | 0.011 | 0.015 | 0.004 | 0.014 | 0.014 | 0.002 | 0.1230 |
| s_decode | 505.925 | 532.119 | 531.549 | 524.723 | 524.622 | 505.925 | 532.119 | 26.194 | 523.788 | 524.723 | 10.610 | 0.0203 |
| s_output | 164.239 | 164.677 | 163.084 | 161.468 | 165.380 | 161.468 | 165.380 | 3.912 | 163.770 | 164.239 | 1.533 | 0.0094 |
| s_teardown | 0.164 | 0.179 | 0.173 | 0.150 | 0.147 | 0.147 | 0.179 | 0.032 | 0.163 | 0.164 | 0.014 | 0.0859 |

Transport/decomposition statistics:

| metric | R1 | R2 | R3 | R4 | R5 | min | max | range | mean | median | sample SD | CV |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| clip_src | 2318.607 | 1222.090 | 1593.996 | 834.249 | 1111.634 | 834.249 | 2318.607 | 1484.358 | 1416.115 | 1222.090 | 573.379 | 0.4049 |
| clip_sys | 2282.007 | 1214.082 | 1567.949 | 828.890 | 1107.020 | 828.890 | 2282.007 | 1453.117 | 1399.990 | 1214.082 | 559.623 | 0.3997 |
| clip_h2d | 2104.174 | 1211.483 | 1397.403 | 824.774 | 1099.447 | 824.774 | 2104.174 | 1279.400 | 1327.456 | 1211.483 | 481.225 | 0.3625 |
| clip_s2g | 2320.575 | 1224.128 | 1596.514 | 836.968 | 1112.686 | 836.968 | 2320.575 | 1483.607 | 1418.174 | 1224.128 | 573.348 | 0.4043 |
| clip_ov | 424.303 | 407.260 | 533.864 | 359.463 | 402.291 | 359.463 | 533.864 | 174.401 | 425.436 | 407.260 | 65.147 | 0.1531 |
| clip_tail | 1.968 | 2.038 | 2.518 | 2.719 | 1.052 | 1.052 | 2.719 | 1.667 | 2.059 | 2.038 | 0.646 | 0.3137 |
| clip_gbs | 3.470 | 6.582 | 5.047 | 9.643 | 7.235 | 3.470 | 9.643 | 6.173 | 6.395 | 6.582 | 2.327 | 0.3639 |
| clip_sor | 2682.840 | 1383.794 | 2269.035 | 996.441 | 1265.784 | 996.441 | 2682.840 | 1686.399 | 1719.579 | 1383.794 | 719.615 | 0.4185 |
| clip_skel | 234.374 | 258.868 | 292.308 | 241.859 | 278.740 | 234.374 | 292.308 | 57.934 | 261.230 | 258.868 | 24.364 | 0.0933 |
| clip_adopt | 19.661 | 19.364 | 19.400 | 19.286 | 19.428 | 19.286 | 19.661 | 0.375 | 19.428 | 19.400 | 0.141 | 0.0072 |
| clip_proof | 2.724 | 2.832 | 3.030 | 2.848 | 2.750 | 2.724 | 3.030 | 0.306 | 2.837 | 2.832 | 0.120 | 0.0423 |
| clip_resid | 216.920 | 215.353 | 219.800 | 215.478 | 215.140 | 215.140 | 219.800 | 4.660 | 216.538 | 215.478 | 1.954 | 0.0090 |
| unet_src | 2866.641 | 1463.977 | 3225.079 | 1503.171 | 2875.198 | 1463.977 | 3225.079 | 1761.102 | 2386.813 | 2866.641 | 837.242 | 0.3508 |
| unet_sys | 2801.626 | 1458.266 | 3200.750 | 1491.507 | 2854.596 | 1458.266 | 3200.750 | 1742.484 | 2361.349 | 2801.626 | 823.698 | 0.3488 |
| unet_h2d | 2214.834 | 1452.565 | 2744.631 | 1494.275 | 2389.179 | 1452.565 | 2744.631 | 1292.066 | 2059.097 | 2214.834 | 567.906 | 0.2758 |
| unet_s2g | 2867.936 | 1465.964 | 3227.504 | 1504.204 | 2878.246 | 1465.964 | 3227.504 | 1761.540 | 2388.771 | 2867.936 | 837.659 | 0.3507 |
| unet_ov | 1038.945 | 691.214 | 908.155 | 631.010 | 672.880 | 631.010 | 1038.945 | 407.935 | 788.441 | 691.214 | 176.547 | 0.2239 |
| unet_tail | 1.295 | 1.987 | 2.425 | 1.033 | 3.048 | 1.033 | 3.048 | 2.015 | 1.958 | 1.987 | 0.822 | 0.4199 |
| unet_gbs | 4.294 | 8.409 | 3.817 | 8.189 | 4.280 | 3.817 | 8.409 | 4.592 | 5.798 | 4.294 | 2.293 | 0.3954 |
| unet_resid | 727.921 | 360.585 | 528.230 | 359.360 | 481.469 | 359.360 | 727.921 | 368.561 | 491.513 | 481.469 | 151.612 | 0.3085 |
| vae_src | 316.617 | 67.525 | 305.906 | 59.405 | 73.450 | 59.405 | 316.617 | 257.212 | 164.581 | 73.450 | 134.047 | 0.8145 |
| vae_h2d | 150.256 | 58.813 | 208.204 | 51.453 | 63.568 | 51.453 | 208.204 | 156.751 | 106.459 | 63.568 | 69.652 | 0.6543 |
| vae_s2g | 320.099 | 70.733 | 308.385 | 62.104 | 75.734 | 62.104 | 320.099 | 257.995 | 167.411 | 75.734 | 134.190 | 0.8016 |
| vae_gbs | 1.059 | 4.965 | 1.096 | 5.644 | 4.562 | 1.059 | 5.644 | 4.585 | 3.465 | 4.562 | 2.214 | 0.6388 |

All five valid runs are retained in every statistic, including the asia-south1 R4.

## 5. CLIP decomposition (per run; arm `static_e27`, 4 producers, offsets monotonic)

| field | R1 | R2 | R3 | R4 | R5 |
|---|---|---|---|---|---|
| `golden_clip_load` wall | 3227.756 | 1951.873 | 2875.247 | 1547.067 | 1852.897 |
| `source_open_read` phase | 2682.840 | 1383.794 | 2269.035 | 996.441 | 1265.784 |
| transport header/layout | `header_parse_count=1`, layout `{}` | same | same | same | same |
| staging/pinning allocation | 8 allocs / 268435456 B pinned, reuse 235, retained 0 | same (reuse 235) | same (reuse 235) | same (reuse 235) | same (reuse 235) |
| source total wall | 2318.607 | 1222.090 | 1593.996 | 834.249 | 1111.634 |
| source syscall busy union | 2282.007 | 1214.082 | 1567.949 | 828.890 | 1107.020 |
| source → GPU ready | 2320.575 | 1224.128 | 1596.514 | 836.968 | 1112.686 |
| host H2D span | 2104.174 | 1211.483 | 1397.403 | 824.774 | 1099.447 |
| source/H2D overlap | 424.303 | 407.260 | 533.864 | 359.463 | 402.291 |
| post-source H2D tail | 1.968 | 2.038 | 2.518 | 2.719 | 1.052 |
| H2D submit count / completed count | UNAVAILABLE (bytes reconciled submitted=completed=8044936192) | same | same | same | same |
| source read count / open count | 243 / 4 | 243 / 4 | 243 / 4 | 243 / 4 | 243 / 4 |
| effective source GB/s | 3.470 | 6.582 | 5.047 | 9.643 | 7.235 |
| producer QD occupancy | target 4; max/timeline UNAVAILABLE | same | same | same | same |
| lease / capacity wait | NOT RUN (dispatcher owns leases) | same | same | same | same |
| ready-queue / backpressure wait | NOT RUN | same | same | same | same |
| dispatcher reap | NOT RUN (event polling diagnostics disabled) | same | same | same | same |
| final drain | `{}` (joined, copies complete) | same | same | same | same |
| skeleton/patcher construction | 234.374 | 258.868 | 292.308 | 241.859 | 278.740 |
| storage adoption | 19.661 | 19.364 | 19.400 | 19.286 | 19.428 |
| compute-ready proof | 2.724 | 2.832 | 3.030 | 2.848 | 2.750 |
| owner-publish / handoff | 0.048 | 0.054 | 0.052 | 0.051 | 0.049 |
| residual (timing-window) | 216.920 | 215.353 | 219.800 | 215.478 | 215.140 |
| stage-vs-window delta | 71.189 | 71.608 | 71.622 | 71.103 | 71.005 |
| GPU copy active sum / union-span / idle-starvation | UNAVAILABLE | UNAVAILABLE | UNAVAILABLE | UNAVAILABLE | UNAVAILABLE |
| reusable event count / fresh CUDA event count | UNAVAILABLE | UNAVAILABLE | UNAVAILABLE | UNAVAILABLE | UNAVAILABLE |
| pinned arena allocations (request / transport) | UNAVAILABLE | UNAVAILABLE | UNAVAILABLE | UNAVAILABLE | UNAVAILABLE |

CLIP residency: bf16 requested/effective, CONTROL status, no fallback, no cast-once
attempt; 398/398 params adopted, storage proven, compute scope cuda:0/bf16.

## 6. UNET decomposition (per run)

| field | R1 | R2 | R3 | R4 | R5 |
|---|---|---|---|---|---|
| `golden_unet_load` wall | 3595.857 | 1826.549 | 3755.734 | 1863.564 | 3359.715 |
| `golden.unet.header_config_preflight` | UNAVAILABLE as timer (`header_parse_count=1`) | same | same | same | same |
| `golden.unet.skeleton_patcher_construction` | UNAVAILABLE as timer | same | same | same | same |
| `golden.unet.source_h2d_transport` | walls below | walls below | walls below | walls below | walls below |
| `golden.unet.assign_adoption` | 453/453 same-storage, `assign_true` (no separate timer) | same | same | same | same |
| `golden.unet.binding_validation` | UNAVAILABLE as timer | same | same | same | same |
| `golden.unet.transport_quiescence` | joined, `final_completion`, 0 live workers | same | same | same | same |
| safetensors header parse count | 1 | 1 | 1 | 1 | 1 |
| transport header parse count | 1 | 1 | 1 | 1 | 1 |
| source total wall | 2866.641 | 1463.977 | 3225.079 | 1503.171 | 2875.198 |
| source syscall union | 2801.626 | 1458.266 | 3200.750 | 1491.507 | 2854.596 |
| source → GPU ready | 2867.936 | 1465.964 | 3227.504 | 1504.204 | 2878.246 |
| host H2D span | 2214.834 | 1452.565 | 2744.631 | 1494.275 | 2389.179 |
| post-source H2D tail | 1.295 | 1.987 | 2.425 | 1.033 | 3.048 |
| source read count | 370 | 370 | 370 | 370 | 370 |
| H2D submission / completed count | UNAVAILABLE (bytes 12309817472 = 12309817472) | same | same | same | same |
| staging alloc count/bytes (reuse) | 8 / 268435456 (362) | same | same | same | same |
| lease / ready-backpressure wait | NOT RUN | NOT RUN | NOT RUN | NOT RUN | NOT RUN |
| dispatcher reap / final drain | NOT RUN / `{}` joined | same | same | same | same |
| producer QD occupancy | target 4 | 4 | 4 | 4 | 4 |
| E27 physical-source proof | YES | YES | YES | YES | YES |
| fallback count/reason | 0 / none | 0 | 0 | 0 | 0 |
| post-transport residual (skeleton+assign+validation+quiescence) | 727.921 | 360.585 | 528.230 | 359.360 | 481.469 |
| GPU copy active/union/idle; constructor overlap/join; plan reuse/parse | UNAVAILABLE | UNAVAILABLE | UNAVAILABLE | UNAVAILABLE | UNAVAILABLE |

## 7. VAE transport table (per run; same resource fields)

| field | R1 | R2 | R3 | R4 | R5 |
|---|---|---|---|---|---|
| `golden_vae_load` wall | 468.263 | 146.065 | 467.036 | 107.668 | 125.169 |
| source total / syscall / H2D / src2GPU | 316.617 / 312.822 / 150.256 / 320.099 | 67.525 / 64.759 / 58.813 / 70.733 | 305.906 / 300.404 / 208.204 / 308.385 | 59.405 / 57.065 / 51.453 / 62.104 | 73.450 / 70.432 / 63.568 / 75.734 |
| overlap / tail | 23.653 / 3.482 | 50.425 / 3.207 | 21.050 / 2.479 | 39.069 / 2.699 | 30.730 / 2.284 |
| reads / opens / bytes | 13 / 4 / 335278732 | same | same | same | same |
| effective GB/s | 1.059 | 4.965 | 1.096 | 5.644 | 4.562 |
| staging 8/268435456 reuse | 5 | 5 | 5 | 5 | 5 |
| H2D bytes submitted=completed | 335278732 | same | same | same | same |
| E27 proof | YES | YES | YES | **NO** (sole NO in cohort) | YES |
| coverage / recon / poison / owner / adopt / fallback | ok / ok / False / 1 / retained / 0 | same | same | same except E27 | same |
| `vae_load_decomposition` | None (UNAVAILABLE rows kept) | same | same | same | same |

VAE: 244 params, cuda:0, fp32. R4's E27-NO is recorded factually; the run is
otherwise fully valid (SHA match, quiescence joined) and retained in statistics.

## 8. Invariant table (per eligible run)

| invariant | R1 | R2 | R3 | R4 | R5 |
|---|---|---|---|---|---|
| exact coverage | ok | ok | ok | ok | ok |
| H2D reconciliation | ok | ok | ok | ok | ok |
| E27 source proof (CLIP/UNET/VAE) | YES/YES/YES | YES/YES/YES | YES/YES/YES | YES/YES/**NO** | YES/YES/YES |
| owner count / adoption | 1 / retained | 1 / retained | 1 / retained | 1 / retained | 1 / retained |
| pointer/storage proof | CLIP 398 proven; UNET 453/453; VAE 244 params | same | same | same | same |
| fallback count | 0 | 0 | 0 | 0 | 0 |
| poisoned | False | False | False | False | False |
| seriality violations | 0 | 0 | 0 | 0 | 0 |
| quiescence | joined | joined | joined | joined | joined |
| output SHA / expected | match `8a924468…c1c44e` | match | match | match | match |
| snapshot classification | ELIGIBLE | ELIGIBLE | ELIGIBLE | ELIGIBLE | ELIGIBLE |
| true-cold (`restore_count=1`, `request_count=1`) | true | true | true | true | true |
| teardown completion | ok (reconcile 0.0062ms) | ok (0.0078) | ok (0.0066) | ok (0.0060) | ok (0.0064) |

CLIP forward: 1341–1490ms, no conversions (all conversion counts None; residency
bf16 native). Sampling decomposition verified every run (3 disjoint children sum
to total; residual 0.0ms). Teardown releases staging owners, zero violations.

## 9. Structural notes (within-cohort facts only)

- S ran on AWS eu-south-2 while every other attempt ran on GCP; retained, not counted.
- R4 ran in GCP asia-south1 with external restore 1446.984ms (~2.3× cohort median 631.899) and the cohort's sole VAE E27-NO; valid and retained.
- Backend wall CV 1.107 is queue-dominated (39.8s–480.5s); stage-level sampling CV is 0.011.
- No fallback, no poisoning, no seriality violation, no DNF in the counted five.

## Appendix A — deployment console (verbatim)

```text
[v2ctl.deploy] profile=golden_p1 deploy_fingerprint=da2725b851d126ec06ba12cc6723a6a6f34041ccf6c62a334ff2b1330c0385cc
[v2ctl.deploy] command=modal deploy -m comfymodal_runtime.modal_app --name sept-unetclip-00-baseline
[custom_nodes.publish] decision=published reason=published_verified generation=6d194f5faed9 schema=2 policy=1
[v2ctl.golden.pre-deploy]
EXPERIMENT_ID=ee753bfa1c0246ff8bf944e50964b13d
MODAL_WORKSPACE=ws_eaef96004dac
MODAL_ENVIRONMENT=(default)
PUBLISHER_APP=comfyui-custom-nodes-publisher
PUBLISHER_EXISTS=YES
PUBLISHER_FUNCTION_EXISTS=YES
PUBLISHER_VERSION=8
LOCAL_CONTENT_GENERATION=6d194f5faed93f0aa0d21ced45dbf682dcf51ca45fdb783c030777f5fee46d99
REMOTE_CONTENT_GENERATION=6d194f5faed93f0aa0d21ced45dbf682dcf51ca45fdb783c030777f5fee46d99
PUBLICATION_DECISION=skip_exact
DEPLOY_LOCK=CLEAR
READY_FOR_CONSUMER_DEPLOY=YES
[v2ctl.deploy] exit=0 manifest=C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\.v2ctl\deployments\deploy_20260903-120412_da2725b8.json
[v2ctl.deploy] deployment_receipt=C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\.v2ctl\deployments\receipt_3_da2725b851d126ec06ba12cc6723a6a6f34041ccf6c62a334ff2b1330c0385cc.json
```

Pre-deploy status/doctor: fingerprint mismatch expected (stored `45a1c7de…`,
current `da2725b8…`), `ready=False`, overrides 0, lock none. Source-probe:
`PASS / MATCH` on all 11 modules (incl. `golden_serial a1920f3c…`,
`modal_app c156c662…`), image `im-GF7rQ3DlfQsEvYNoEPlrzW`, GPU `rtx-pro-6000`,
deployment hash `55c2ad63e7d55b84`. Post-deploy doctor: `OK`, fingerprint
match 1, target match 1.

## Appendix B — run consoles (verbatim, one invocation = one request)

R1/R2 (ack flag active; S/P/PRE ran without it):
```text
[v2ctl.run] WARNING: local deploy identity drifted after deployment; binding the immutable remote receipt (source drift is warning-only)
[v2ctl.run] WARNING: operator acknowledged volume drift; skipping exact-content publisher preflight gate
[v2ctl.run] profile=golden_p1 deploy_fingerprint=da2725b851d126ec06ba12cc6723a6a6f34041ccf6c62a334ff2b1330c0385cc run_fingerprint=9cdc0fd2ad74b3bb530ef000d7f70b212c0f0aec8327626cedb38f82de36c8ae
[v2ctl.run] command="...run_v2_single.bat" --run-count 1 --golden-p1-expected-output-sha 8a92446890bebaecdc10eb5f207766a4b05af40ca3137108e25bfe88d9c1c44e --attention-backend pytorch
[v2ctl.run] exit=0 manifest=.v2ctl/runs/run_20260903-125142_9cdc0fd2.json   (R1)
[v2ctl.run] evidence=EXPERIMENT_EVIDENCE_golden_p1_74364aa898644799_2026-09-03.md status=OK
[v2ctl.run] exit=0 manifest=.v2ctl/runs/run_20260903-125451_9cdc0fd2.json   (R2)
[v2ctl.run] evidence=EXPERIMENT_EVIDENCE_golden_p1_0474d478ce3245d6_2026-09-03.md status=OK
[v2ctl.run] exit=0 manifest=.v2ctl/runs/run_20260903-130037_9cdc0fd2.json   (R3)
[v2ctl.run] exit=0 manifest=.v2ctl/runs/run_20260903-130307_9cdc0fd2.json   (R4)
[v2ctl.run] exit=0 manifest=.v2ctl/runs/run_20260903-130501_9cdc0fd2.json   (R5)
```
One locally BLOCKED attempt between P and R1 (no remote request):
```text
[v2ctl.run] WARNING: local deploy identity drifted after deployment; binding the immutable remote receipt (source drift is warning-only)
ERROR: publisher preflight is not ready for consumer deploy: decision=publish_required bootstrap_required=False
```

## Appendix C — run manifests and capture records

Manifests (51,345–51,347 bytes each; `PATH` values truncated at 2906 chars):
R1 sha `9cb372275b388b08`, R2 `d86ec794c75cf369`, R3 `abd8f51c638137a6`,
R4 `41b9e4f95e1e0be4`, R5 `bf1bb93cf977c96c`; each carries
`COMFYMODAL_V2CTL_ACKNOWLEDGED_VOLUME_DRIFT=1`, deploy receipt binding,
`profile_config_fingerprint`, workload `expected_output_sha 8a924468…`,
`fresh_required=true`, `gap_seconds=35`. Full JSON retained at the manifest
paths in the ledger; PATH redaction is the only omission.

Capture-guard records: R1–R5 and PRE1–PRE4 all `ELIGIBLE/valid/counted/idle`;
S record `ELIGIBLE/idle/no-transition` with the operator-asserted
SNAPSHOT_CAPTURE override documented in section 2 (guard disagreement
preserved, not reconciled away).

Attempt artifacts (~18.2MB each; sha R1 `edd50ae4ffa26fbd`, R2 `3ab87913b948485e`,
R3 `e7a1a52ab0339073`, R4 `cfe59d8d0a75a8b2`, R5 `30d0d281a04b0fc0`) retained at
their cohort paths with `attempt_0_events.json` (~28.9MB),
`manifest.json`/`summary.json` (~20MB), and `attempt_0.json.v2ctl-provenance.json`
(25616 B). No `derived/` or `raw/` profiler subdirectories were produced in
this bundle — the embedded telemetry above is the complete decomposition
source; `viztracer.json.gz`/torch traces do not exist for these runs.

## Appendix D — superseded first deployment (retained, not mixed)

Deployment `45a1c7de…` (HEAD `23b42d23…` dirty, manifest
`deploy_20260903-111320_45a1c7de.json`): one PRE_CAPTURE run
(inv `f8514ab2fa8f49ea`, req `golden-p1-0-887fd16dbff5`, ELIGIBLE/valid/
true-cold, AWS) and one locally blocked attempt (concurrent edit of untracked
`golden_human_report.py` drifted the fingerprint; single-deployment rule at the
time forbade redeploy). Redeploy to `da2725b8` was later explicitly authorized;
observations across the two identities are never combined.

## Appendix E — concurrent-lane interference log (factual)

During the `da2725b8` cohort an authorized parallel lane (RX9P-M2, human
reporting) edited publishable files mid-cohort (`golden_serial.py`,
`golden_human_report.py`, `full_trace_report.py`; mtimes 17:31–17:36 UTC),
which tripped the exact-content publisher gate once (BLOCKED attempt, Appendix B).
An attempted quarantine (stash + file move, backups hash-recorded) was fully
reverted on operator order: stash popped cleanly, `golden_human_report.py`
restored byte-identical (hash `46d1a5a9…` verified). No concurrent content was
kept, altered, or lost by this experiment.

## Appendix F — `--acknowledge-volume-drift` control-plane change

`tools/v2_control/cli.py` only (3 minimal edits; default path unchanged):
1. `golden run` parser gained the flag with explicit help text.
2. `cmd_run` calls `run_publisher_preflight(..., require_ready=not ack)` with a
   loud stderr warning when skipped.
3. `COMFYMODAL_V2CTL_ACKNOWLEDGED_VOLUME_DRIFT=1` is injected into the backend
   env, landing in every run manifest. `.opencode/skills/comfymodal-golden-ops/
   SKILL.md` documents the flag and its limits (never overrides fingerprint,
   receipt, or output contract). Verified via `golden run --help` and 5/5
   flagged runs carrying the marker.
