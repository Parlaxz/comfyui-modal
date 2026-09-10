# Independent Golden Serial sampler lanes

Both lanes were run independently from canonical base `0ea9428`; neither lane
was merged into the other.

## Common identity

- Workspace: Testing 6 / `ws_175a616152c5`
- Runtime: Golden Serial, Sage / baked CUDA, true-QD2, 4 CPU / 16 GiB
- Workflow SHA: `e44389ea2eda82ba5e2328acc08307b6879ed6d4ea4b030727ab044704c0d3b5`
- Exact output SHA: `790c3052a9b4a5ed01369e81cf79eac389f1d69b25578be3aa033e673570e89d`
- Deep profiler request/effective state: `deep_trace=false` / `off`
- Every counted smoke/timing run: exact SHA, `valid=true`, `true_cold=true`,
  `restore_count=1`, `request_count=1`, seriality violations `0`, no runtime
  fallback.

## Lane A — post-loop tail

### Identity and commits

- Worktree: `C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\.slim\worktrees\golden-post-loop-tail-exp2`
- Branch: `omos/golden-post-loop-tail-exp2`
- comfyui-modal commit: `6711b6b`
- RES4LYF worktree: `C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\RES4LYF\.slim\worktrees\golden-post-loop-tail-exp2\RES4LYF`
- RES4LYF branch/commit: `omos/golden-post-loop-tail-res4lyf-exp2` / `b2108e6`
- Deployment: `deploy_20260908-200024_3c014139.json`
- Deployment fingerprint: `3c014139b4e04ddf325ec553d31bfb246009820bba3054431475b3c90a659407`
- Source probe: `probe_6_3c014139b4e04ddf325ec553d31bfb246009820bba3054431475b3c90a659407.json` — `PASS / MATCH`
- Final dirty diff: no tracked code diff after the two commits; generated
  evidence remains untracked in the lane worktree.

### Proven diagnosis

The diagnostic smoke split the active batch path. After the final useful RK
evaluation, the large tail was in `gc.collect()`:

`sampler_result_state_processing_end -> shark_batch_gc_start -> shark_batch_gc_end`

was approximately `822.598 ms`; all final evaluation, `.to()`, callback,
state assembly, and stacking intervals were small. The fix removed only that
active-path `gc.collect()` and its unused import. RK coefficient logic was not
changed.

### Final smoke and five timing runs

Times are milliseconds. `last compute → sampler return` is the last real RK
model evaluation end to `clownshark_beta_return`.

| run | sampler total | last compute → sampler return | final eval | RK state | x/eps finalization | progress close | callback | state processing | GC | stacking | resume → FRR | exact SHA / fallback / validity |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| 1 | 4592.398 | 18.663 | 1.616 | 0.013 | 0.008 | 0.194 | 0.060 | 3.804 | 0.029 | 8.615 | 11978.639 | `790c3052a9b4a5ed01369e81cf79eac389f1d69b25578be3aa033e673570e89d` / none / valid, true-cold |
| 2 | 4570.527 | 20.119 | 1.526 | 0.013 | 0.008 | 0.200 | 0.054 | 4.165 | 0.010 | 9.276 | 11909.998 | `790c3052a9b4a5ed01369e81cf79eac389f1d69b25578be3aa033e673570e89d` / none / valid, true-cold |
| 3 | 4665.633 | 21.822 | 1.944 | 0.018 | 0.008 | 0.151 | 0.047 | 4.440 | 0.011 | 9.917 | 12225.055 | `790c3052a9b4a5ed01369e81cf79eac389f1d69b25578be3aa033e673570e89d` / none / valid, true-cold |
| 4 | 4679.770 | 21.591 | 2.380 | 0.018 | 0.027 | 0.245 | 0.068 | 4.730 | 0.036 | 8.909 | 11937.833 | `790c3052a9b4a5ed01369e81cf79eac389f1d69b25578be3aa033e673570e89d` / none / valid, true-cold |
| 5 | 4689.133 | 20.958 | 2.200 | 0.017 | 0.009 | 0.305 | 0.087 | 3.825 | 0.021 | 9.230 | 12305.159 | `790c3052a9b4a5ed01369e81cf79eac389f1d69b25578be3aa033e673570e89d` / none / valid, true-cold |

Means: sampler total `4639.492 ms`; last compute → sampler return
`20.631 ms`; GC `0.021 ms`; resume → FRR `12071.337 ms`.

### Lane A before/after

| metric | `0ea9428` cohort | Lane A after | delta |
|---|---:|---:|---:|
| sampler total mean | 5445.199 ms | 4639.492 ms | **-805.707 ms / -14.80%** |
| resume → FRR mean | 12770.200 ms | 12071.337 ms | **-698.863 ms / -5.47%** |
| post-loop GC | ~822.598 ms diagnostic | 0.021 ms | ~-822.6 ms |

Lane A is a clear whole-endpoint win and is committed only on its isolated
branches.

## Lane B — RK `.item()` / coefficient-controller path

### Identity and commits

- Worktree: `C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\.slim\worktrees\golden-rk-coeff-controller-exp2`
- Branch: `omos/golden-rk-coeff-controller-exp2`
- comfyui-modal commit: `4577213`
- RES4LYF worktree: `C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\RES4LYF\.slim\worktrees\golden-rk-coeff-controller-exp2\RES4LYF`
- RES4LYF branch/commit: `omos/golden-rk-coeff-controller-res4lyf-exp2` / `0311b37`
- Final deployment: `deploy_20260908-185028_bd1210d4.json`
- Deployment fingerprint: `bd1210d4117a45de9bf97637c45842d4a07bff0e210e674eeac6fb0c584960cc`
- Final source probe: `probe_7_bd1210d4117a45de9bf97637c45842d4a07bff0e210e674eeac6fb0c584960cc.json` — `PASS / MATCH`
- Final dirty diff: no tracked code diff after the two commits; generated
  evidence remains untracked in the lane worktree.

The active module routing was proven as
`/root/comfy/ComfyUI/custom_nodes/RES4LYF.beta.samplers` with adjacent
coefficient module import success. RK events are persisted in Golden telemetry.
The conservative fix replaces the active `res_2s` CUDA row-offset reduction
with CPU-native classification of the already-built Python tableau; analytic
`h` extraction remains unchanged. No sampler equation, schedule, step count,
CacheDiT cadence, precision, post-loop path, or output contract changed.

### Final smoke and five timing runs

Row gaps are row0 model-return → row1 model-call-start for steps 0–7. The
instrumented `.item()` count is 8 per run; coefficient wall is the sum of
`RK.set_coeff` start→end intervals.

| run | sampler total | row gaps 0..7 (ms) | `.item()` count / wall | coefficient wall | derivation wall | resume → FRR | exact SHA / fallback / validity |
|---:|---:|---|---:|---:|---:|---:|---|
| 1 | 5490.977 | 69.825, 16.904, 15.740, 16.394, 16.297, 1.588, 1.414, 2.127 | 8 / 0.124 ms | 6.301 ms | 3.592 ms | 12390.034 | `790c3052a9b4a5ed01369e81cf79eac389f1d69b25578be3aa033e673570e89d` / none / valid, true-cold |
| 2 | 5410.505 | 64.195, 17.382, 14.922, 14.653, 14.982, 1.341, 1.259, 1.306 | 8 / 0.119 ms | 6.183 ms | 3.539 ms | 12887.924 | `790c3052a9b4a5ed01369e81cf79eac389f1d69b25578be3aa033e673570e89d` / none / valid, true-cold |
| 3 | 5431.575 | 64.051, 15.647, 15.193, 15.397, 14.716, 1.424, 1.321, 1.302 | 8 / 0.130 ms | 6.438 ms | 3.673 ms | 12336.499 | `790c3052a9b4a5ed01369e81cf79eac389f1d69b25578be3aa033e673570e89d` / none / valid, true-cold |
| 4 | 5385.542 | 65.787, 14.920, 14.922, 15.560, 15.667, 1.480, 1.246, 1.695 | 8 / 0.116 ms | 6.101 ms | 3.377 ms | 13135.091 | `790c3052a9b4a5ed01369e81cf79eac389f1d69b25578be3aa033e673570e89d` / none / valid, true-cold |
| 5 | 5430.869 | 69.494, 14.621, 14.313, 14.298, 14.308, 1.131, 1.121, 1.291 | 8 / 0.124 ms | 5.709 ms | 3.198 ms | 12857.344 | `790c3052a9b4a5ed01369e81cf79eac389f1d69b25578be3aa033e673570e89d` / none / valid, true-cold |

Means: sampler total `5429.894 ms`; row-gap means by step are
`66.670, 15.895, 15.018, 15.260, 15.194, 1.393, 1.272, 1.544 ms`;
`.item()` wall `0.123 ms`; coefficient wall `6.147 ms`; derivation wall
`3.476 ms`; resume → FRR `12721.379 ms`.

### Lane B before/after

| metric | `0ea9428` cohort | Lane B after | delta |
|---|---:|---:|---:|
| sampler total mean | 5445.199 ms | 5429.894 ms | -15.305 ms / -0.28% |
| resume → FRR mean | 12770.200 ms | 12721.379 ms | **-48.821 ms / -0.38%** |
| `.item()` synchronization | active row-offset reduction plus schedule extraction | 8 schedule extractions; row classification CPU-native | row-offset sync removed |

Lane B is a narrow whole-endpoint win with exact output and no validity,
seriality, or fallback regression. It remains independently committed and is
not integrated with Lane A.

## Raw evidence

### Lane A

- Deployment: `.slim/worktrees/golden-post-loop-tail-exp2/.v2ctl/deployments/deploy_20260908-200024_3c014139.json`
- Receipt: `.slim/worktrees/golden-post-loop-tail-exp2/.v2ctl/deployments/receipt_6_3c014139b4e04ddf325ec553d31bfb246009820bba3054431475b3c90a659407.json`
- Diagnostic smoke: `.slim/worktrees/golden-post-loop-tail-exp2/.v2ctl/runs/run_20260908-195016_d433766a.json`
- Final smoke: `.slim/worktrees/golden-post-loop-tail-exp2/.v2ctl/runs/run_20260908-200354_d433766a.json`
- Timing run manifests: `run_20260908-200632_d433766a.json`, `run_20260908-200724_d433766a.json`, `run_20260908-200817_d433766a.json`, `run_20260908-200910_d433766a.json`, `run_20260908-201014_d433766a.json` under the same `.v2ctl/runs/` directory.
- Final evidence reports: `EXPERIMENT_EVIDENCE_golden_p1_3ca42217370540dd_2026-09-09.md`, `EXPERIMENT_EVIDENCE_golden_p1_835a3f331a0c49f9_2026-09-09.md`, `EXPERIMENT_EVIDENCE_golden_p1_4cb4090c30a84365_2026-09-09.md`, `EXPERIMENT_EVIDENCE_golden_p1_4443bc194aeb4429_2026-09-09.md`, `EXPERIMENT_EVIDENCE_golden_p1_bedd28478d384ff2_2026-09-09.md`, `EXPERIMENT_EVIDENCE_golden_p1_72b7283f888f4b3d_2026-09-09.md` under the A worktree.
- Raw attempt directories: `artifacts/phase_p1_serial_golden_v1/cohort_2026-09-09_01-02-04_596e9a/` and `cohort_2026-09-09_01-04-37_262586/`, `01-06-59_193af6/`, `01-07-51_0225cb/`, `01-08-44_d1a27e/`, `01-09-47_d49b3a/`.

### Lane B

- Deployment: `.slim/worktrees/golden-rk-coeff-controller-exp2/.v2ctl/deployments/deploy_20260908-185028_bd1210d4.json`
- Receipt: `.slim/worktrees/golden-rk-coeff-controller-exp2/.v2ctl/deployments/receipt_7_bd1210d4117a45de9bf97637c45842d4a07bff0e210e674eeac6fb0c584960cc.json`
- Final smoke: `.slim/worktrees/golden-rk-coeff-controller-exp2/.v2ctl/runs/run_20260908-185235_a98ecdac.json`
- Timing run manifests: `run_20260908-185350_a98ecdac.json`, `run_20260908-185445_a98ecdac.json`, `run_20260908-185557_a98ecdac.json`, `run_20260908-185652_a98ecdac.json`, `run_20260908-185747_a98ecdac.json` under the same `.v2ctl/runs/` directory.
- Final evidence reports: `EXPERIMENT_EVIDENCE_golden_p1_21d77ddee7384958_2026-09-08.md`, `EXPERIMENT_EVIDENCE_golden_p1_7025e5026a2147c3_2026-09-08.md`, `EXPERIMENT_EVIDENCE_golden_p1_efd48c624ffe4108_2026-09-08.md`, `EXPERIMENT_EVIDENCE_golden_p1_782803d9b2c64ffc_2026-09-09.md`, `EXPERIMENT_EVIDENCE_golden_p1_da94d60a8a46490d_2026-09-09.md`, `EXPERIMENT_EVIDENCE_golden_p1_57fe3366308d49b2_2026-09-09.md` under the B worktree.
- Raw attempt directories: `artifacts/phase_p1_serial_golden_v1/cohort_2026-09-08_23-52-02_067d27/`, `23-53-23_f8d1f4/`, `23-54-19_448c79/`, `23-55-31_313725/`, `23-56-26_5232b0/`, `23-57-20_dcf24c/`.

Earlier invalid/inconclusive Lane B control-plane attempts and the pre-persistence
smokes are retained in the B worktree evidence directories and were not used in
the five-run timing cohort.

## Combined A+B integration lane

This lane is experimental/reference only. It is **not canonical** and neither
modified RES4LYF commit is promoted to the normal RES4LYF checkout or branch.

- Worktree: `C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\.slim\worktrees\golden-sampler-ab-integration`
- Branch: `omos/golden-sampler-ab-integration`
- comfyui-modal HEAD: `f3c5171ddf8f9a1ff1855314d6c29e44e5c1fe3a`
- RES4LYF worktree: `C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\RES4LYF\.slim\worktrees\golden-sampler-ab-integration\RES4LYF`
- RES4LYF HEAD: `338fd796be794675ecaf1b7141c090fb6b733630`
- Deployment: `.slim/worktrees/golden-sampler-ab-integration/.v2ctl/deployments/deploy_20260908-203904_39d18609.json`
- Receipt: `.slim/worktrees/golden-sampler-ab-integration/.v2ctl/deployments/receipt_1_39d1860929f5292c99d8e88f9d7a0ce6435fbb511a2597f49dd2989814d3f276.json`
- Source probe: `.slim/worktrees/golden-sampler-ab-integration/.v2ctl/source-probes/probe_1_39d1860929f5292c99d8e88f9d7a0ce6435fbb511a2597f49dd2989814d3f276.json` — `PASS / MATCH`

The first timing-run attempt is retained as
`EXPERIMENT_EVIDENCE_golden_p1_974ddb00554e474a_2026-09-09.md`; it failed at
artifact serialization with `OSError: [Errno 28] No space left on device` and
is not counted.

| run | sampler total | last useful compute → sampler return | post-loop GC | row gaps 0..7 (ms) | coefficient wall | resume → FRR | exact SHA / validity |
|---:|---:|---:|---:|---|---:|---:|---|
| 1 | 4579.764 | 17.184 | 0.022 | 64.348, 16.269, 15.320, 15.110, 15.004, 1.383, 1.228, 1.596 | 6.338 | 11652.815 | `790c3052a9b4a5ed01369e81cf79eac389f1d69b25578be3aa033e673570e89d` / valid, true-cold |
| 2 | 4606.459 | 21.488 | 0.012 | 62.493, 16.864, 16.252, 15.627, 16.052, 1.739, 1.735, 1.442 | 6.518 | 14778.064 | `790c3052a9b4a5ed01369e81cf79eac389f1d69b25578be3aa033e673570e89d` / valid, true-cold |
| 3 | 4591.295 | 23.008 | 0.046 | 65.242, 15.488, 14.549, 14.594, 14.392, 1.551, 2.186, 1.513 | 6.120 | 11821.489 | `790c3052a9b4a5ed01369e81cf79eac389f1d69b25578be3aa033e673570e89d` / valid, true-cold |
| 4 | 4736.641 | 19.885 | 0.011 | 116.883, 16.364, 16.888, 14.627, 14.458, 2.212, 1.995, 2.301 | 8.376 | 12592.468 | `790c3052a9b4a5ed01369e81cf79eac389f1d69b25578be3aa033e673570e89d` / valid, true-cold |
| 5 | 4578.094 | 18.695 | 0.010 | 65.065, 16.324, 15.918, 15.288, 15.862, 1.316, 1.331, 1.320 | 6.637 | 11696.705 | `790c3052a9b4a5ed01369e81cf79eac389f1d69b25578be3aa033e673570e89d` / valid, true-cold |

Means: sampler `4618.451 ms`, last useful compute → return `20.052 ms`,
post-loop GC `0.020 ms`, coefficient construction `6.798 ms`, resume → FRR
`12508.308 ms`; medians are `4591.295 ms`, `19.885 ms`, `0.012 ms`,
`6.518 ms`, and `11821.489 ms`. Descriptive n=5 P90 values are sampler
`4684.568 ms` and resume → FRR `13903.826 ms`.

| cohort | sampler mean | sampler median | resume → FRR mean | resume → FRR median | resume → FRR P90 |
|---|---:|---:|---:|---:|---:|
| `0ea9428` | 5445.199 ms | 5421.473 ms | 12770.200 ms | 12774.000 ms | 13078.600 ms |
| Lane A only | 4639.492 ms | 4665.633 ms | 12071.337 ms | 11978.639 ms | 12273.118 ms |
| Lane B only | 5429.894 ms | 5430.869 ms | 12721.379 ms | 12857.344 ms | 13036.224 ms |
| **A+B** | **4618.451 ms** | **4591.295 ms** | **12508.308 ms** | **11821.489 ms** | **13903.826 ms** |

A+B retains essentially all of Lane A’s sampler recovery and adds about
`21.041 ms` mean sampler improvement over Lane A. It is `2.05%` faster than
the `0ea9428` E2E mean and has a better median than Lane A, but one valid
`14778.064 ms` outlier makes its mean `436.971 ms` slower than Lane A and its
P90 materially worse. The outlier is retained; this is a performance-variance
warning, not discarded evidence. No exactness, fallback, QD2, or seriality
regression occurred.

The active stock RES4LYF callsite for Lane A’s removed work is
`RES4LYF/beta/samplers.py`, `SharkSampler.main`, the batch-path `gc.collect()`
after batch processing and before stacking/state assembly (around line 1194
in the stock file), with `import gc` at the module top. The narrowest future
comfyui-modal-only reproduction is a request-scoped wrapper around the active
Golden sampler call that temporarily replaces only that module’s `gc` binding
with a no-op `collect`, restores it in `finally`, and leaves stock RES4LYF
files untouched. This was not implemented here.

Lane B can likewise be reproduced from comfyui-modal in principle with a
request-scoped adapter around the active `RK_Method_Beta.set_coeff`/coefficient
dispatch: preserve the stock coefficient generation, classify the already-known
Python `res_2s` tableau on CPU, and set only `row_offset` without the CUDA row
reduction. The adapter would need to bind to the actual RES4LYF class/module at
Golden sampler entry and restore the original binding in `finally`; it was not
implemented here.

Combined raw run manifests:

- Smoke: `.slim/worktrees/golden-sampler-ab-integration/.v2ctl/runs/run_20260908-204133_40511208.json`
- Timing 1: `.slim/worktrees/golden-sampler-ab-integration/.v2ctl/runs/run_20260908-204309_40511208.json`
- Failed timing attempt: evidence report above; no run manifest was written.
- Timing 2: `.slim/worktrees/golden-sampler-ab-integration/.v2ctl/runs/run_20260908-210434_40511208.json`
- Timing 3: `.slim/worktrees/golden-sampler-ab-integration/.v2ctl/runs/run_20260908-210532_40511208.json`
- Timing 4: `.slim/worktrees/golden-sampler-ab-integration/.v2ctl/runs/run_20260908-210632_40511208.json`
- Timing 5: `.slim/worktrees/golden-sampler-ab-integration/.v2ctl/runs/run_20260908-210740_40511208.json`

Combined raw attempt directories are the corresponding `attempt_0.json` and
`attempt_0_events.json` files under:
`cohort_2026-09-09_01-41-06_3c1fbc`,
`01-42-43_d77289`, `02-04-05_10cb95`, `02-05-06_f67757`,
`02-06-05_48ce6c`, and `02-07-14_65e439` in
`artifacts/phase_p1_serial_golden_v1/`.

The integration lane is complete for audit only. Do not merge it into the
main/canonical branch or promote either RES4LYF commit.
