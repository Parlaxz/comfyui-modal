# Golden Serial DynamicVRAM-before-QD2 report

## Decision

The isolated reorder wins the measured critical-path boundary and is committed
as `0ea9428` (`Reorder Golden DynamicVRAM before QD2`). The candidate completed
one QD2 correctness smoke and five separate true-cold timing requests. All six
QD2/Sage observations were exact, valid, true-cold, serial, and fallback-free.

The direct activation-start and activation-duration fields requested below are
not emitted by the current telemetry schema. The report does not infer them.
It reports the emitted activation return timestamp and the resulting measured
boundary to QD2 allocation.

## Frozen experiment identity

| item | value |
|---|---|
| worktree | `C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal` |
| commit lineage | `7794fbf` ancestor; candidate commit `0ea9428` |
| app | `batch-golden-dvram-q2-reorder` |
| workspace | `Testing 6` / `ws_175a616152c5` |
| profile | `golden_p1` |
| target | `ModalRuntimeEntrypointV2.run_golden_serial_stream` |
| GPU / CPU / memory | `rtx-pro-6000` / `4` / `16384 MiB` |
| attention | Sage; configured `sage`, resolved `sage`, runtime `baked_cuda` |
| true-QD2 | `cpu_raw_qd2_preadv_prefetch`, `qd=2` |
| deep profiler | request `deep_trace=false`, effective `off`; deploy-baked sampling decomposition remained `COMFYMODAL_SAMPLING_DEEP_PROFILE=blocks` |
| output SHA | `790c3052a9b4a5ed01369e81cf79eac389f1d69b25578be3aa033e673570e89d` |
| workflow SHA | `e44389ea2eda82ba5e2328acc08307b6879ed6d4ea4b030727ab044704c0d3b5` |
| deployment fingerprint | `4bf268fd192bbaeaff546b6634b09177a0281ada3c206b73f64245708e48a8b5` |
| remote deployment combined hash | `0c9fd2b9f5255b1a1c9a530bd27a610b52ded3a5eb2a688fa8392d6075e12d60` |
| image | `im-ReioLICvpoM5JHz6p1FLbm` |
| source probe | `PASS / MATCH` |

## Candidate timing runs

All relative times are milliseconds from the emitted remote Python restore end.
`DynamicVRAM return` is the emitted `activation.activated_monotonic_ns`.
`QD2 source start` is the first emitted source-worker start. `Golden call
start` is the emitted `golden_request_setup` stage entry, the closest persisted
boundary to the wrapper's non-persisted `golden_call_start` timestamp.

| run | restore | restore end → DynamicVRAM start | activation duration | restore end → DynamicVRAM return | DynamicVRAM return → backing allocation start | backing allocation | QD2 source start | first extent ready | Golden call start | resume → FRR | exact SHA / fallback / validity |
|---:|---:|---|---|---:|---:|---:|---:|---:|---:|---:|---|
| 1 | 840.566 | not emitted | not emitted | 55.533 | 7.615 | 751.578 | 855.814 | 885.255 | 895.133 | 13164.850 | `790c3052a9b4a5ed01369e81cf79eac389f1d69b25578be3aa033e673570e89d` / none / valid=true, true_cold=true |
| 2 | 801.809 | not emitted | not emitted | 47.569 | 5.614 | 700.058 | 794.345 | 825.849 | 862.262 | 12773.788 | `790c3052a9b4a5ed01369e81cf79eac389f1d69b25578be3aa033e673570e89d` / none / valid=true, true_cold=true |
| 3 | 641.701 | not emitted | not emitted | 45.740 | 5.230 | 660.620 | 744.252 | 789.104 | 754.196 | 12446.539 | `790c3052a9b4a5ed01369e81cf79eac389f1d69b25578be3aa033e673570e89d` / none / valid=true, true_cold=true |
| 4 | 672.782 | not emitted | not emitted | 48.783 | 5.042 | 664.155 | 758.570 | 796.117 | 805.522 | 12516.104 | `790c3052a9b4a5ed01369e81cf79eac389f1d69b25578be3aa033e673570e89d` / none / valid=true, true_cold=true |
| 5 | 1106.761 | not emitted | not emitted | 101.789 | 5.866 | 671.823 | 820.822 | 852.248 | 830.176 | 12949.052 | `790c3052a9b4a5ed01369e81cf79eac389f1d69b25578be3aa033e673570e89d` / none / valid=true, true_cold=true |

Candidate summary: DynamicVRAM return after restore mean `59.883 ms`
(median `48.783`, range `45.740–101.789`); activation-return → backing-start
mean `5.873 ms` (median `5.614`, range `5.042–7.615`); backing allocation mean
`689.647 ms`; resume → FRR mean `12770.067 ms` (median `12773.788`).

Every candidate run had `restore_count=1`, `request_count=1`, a unique restored
identity, `qd=2`, `cpu_backing_bytes=8044936192`, `bytes_prefetched=8044936192`,
`ready_extent_count=60`, `source_provenance=actual_os_preadv`,
`seriality.count=0`, `output_sha_match=true`, and `first_result_ready_marked=true`.
The top-level runtime fallback was false/none. The E27 evaluator contains a
diagnostic `predicates.fallback=true`, but its actual source report is
`fallback=0`; no runtime QD2/loader/transport fallback occurred.

## Current-order comparison

The available five-run current-order comparator is the same workflow SHA,
true-cold QD2 and 4 CPU/16 GiB shape, but its historical deployment resolved
PyTorch rather than Sage and produced output SHA
`8a92446890bebaecdc10eb5f207766a4b05af40ca3137108e25bfe88d9c1c44e`. It is
therefore contextual rather than a perfectly matched Sage control.

| current-order metric | five-run comparator |
|---|---:|
| restore mean | `917.788 ms` |
| restore end → DynamicVRAM return mean | `1811.394 ms` |
| backing allocation mean | `774.412 ms` |
| backing allocation end → DynamicVRAM return mean | `987.629 ms` |
| restore end → Golden call mean | `1817.846 ms` |
| resume → FRR mean | `13686.224 ms` |

The candidate changes the observable ordering from `allocation → DynamicVRAM`
to `DynamicVRAM return → allocation`. It removes the approximately `987.629 ms`
post-allocation DynamicVRAM delay from the pre-Golden critical path and reduces
restore-end → Golden-call mean from `1817.846 ms` to `829.458 ms` in the
available comparison. Because the comparator is PyTorch rather than Sage, the
strict causal claim is limited; the ordering claim itself is directly proven by
the candidate event timestamps and source test.

## Code change and local validation

Only these tracked files changed in the commit:

- `comfymodal_runtime/modal_app.py`: moved the existing DynamicVRAM activation
  block before the existing CPU QD2 prefetch call; QD2, allocation, transport,
  loader, and profiler implementations were not changed.
- `tests/test_v2_full_trace_lifecycle.py`: asserts activation < QD2 prefetch <
  GPU readiness < Golden call.

Checks:

- `python -m py_compile comfymodal_runtime/modal_app.py tests/test_v2_full_trace_lifecycle.py` — pass.
- Focused ordering test — pass.
- Focused Golden Serial stage-order test with `PYTHONPATH=..\\..` — pass.
- Unqualified Golden Serial test collection on the host failed before execution
  because `comfy_api` is absent; with the ComfyUI root on `PYTHONPATH`, the
  focused stage-order test passed.

## Raw evidence paths

Candidate deployment/source evidence:

- `.v2ctl/deployments/deploy_20260908-122155_4bf268fd.json`
- `.v2ctl/deployments/receipt_1_4bf268fd192bbaeaff546b6634b09177a0281ada3c206b73f64245708e48a8b5.json`
- `.v2ctl/source-probes/probe_1_4bf268fd192bbaeaff546b6634b09177a0281ada3c206b73f64245708e48a8b5.json`

Correctness smoke (QD2, not counted in the five timing runs):

- `EXPERIMENT_EVIDENCE_golden_p1_fd86a5bc07a5464d_2026-09-08.md`
- `.v2ctl/runs/run_20260908-122916_fe6ffb0b.json`
- `artifacts/phase_p1_serial_golden_v1/cohort_2026-09-08_17-26-52_6a1cda/attempt_0.json`
- `artifacts/phase_p1_serial_golden_v1/cohort_2026-09-08_17-26-52_6a1cda/attempt_0_events.json`

Timing runs 1–5:

- `EXPERIMENT_EVIDENCE_golden_p1_6f7ec619c9b94362_2026-09-08.md`
- `.v2ctl/runs/run_20260908-124719_fe6ffb0b.json`
- `artifacts/phase_p1_serial_golden_v1/cohort_2026-09-08_17-46-52_1d90ca/attempt_0.json`
- `artifacts/phase_p1_serial_golden_v1/cohort_2026-09-08_17-46-52_1d90ca/attempt_0_events.json`
- `EXPERIMENT_EVIDENCE_golden_p1_73e079cac3ae424f_2026-09-08.md`
- `.v2ctl/runs/run_20260908-130241_fe6ffb0b.json`
- `artifacts/phase_p1_serial_golden_v1/cohort_2026-09-08_17-59-55_a4940c/attempt_0.json`
- `artifacts/phase_p1_serial_golden_v1/cohort_2026-09-08_17-59-55_a4940c/attempt_0_events.json`
- `EXPERIMENT_EVIDENCE_golden_p1_85fb99b266714b27_2026-09-08.md`
- `.v2ctl/runs/run_20260908-130755_fe6ffb0b.json`
- `artifacts/phase_p1_serial_golden_v1/cohort_2026-09-08_18-03-16_5a6e87/attempt_0.json`
- `artifacts/phase_p1_serial_golden_v1/cohort_2026-09-08_18-03-16_5a6e87/attempt_0_events.json`
- `EXPERIMENT_EVIDENCE_golden_p1_45ddaa7d91944fec_2026-09-08.md`
- `.v2ctl/runs/run_20260908-130855_fe6ffb0b.json`
- `artifacts/phase_p1_serial_golden_v1/cohort_2026-09-08_18-08-23_96b03d/attempt_0.json`
- `artifacts/phase_p1_serial_golden_v1/cohort_2026-09-08_18-08-23_96b03d/attempt_0_events.json`
- `EXPERIMENT_EVIDENCE_golden_p1_9dd0ec15fddb4220_2026-09-08.md`
- `.v2ctl/runs/run_20260908-131312_fe6ffb0b.json`
- `artifacts/phase_p1_serial_golden_v1/cohort_2026-09-08_18-12-43_1a4eb5/attempt_0.json`
- `artifacts/phase_p1_serial_golden_v1/cohort_2026-09-08_18-12-43_1a4eb5/attempt_0_events.json`

Current-order comparator raw artifacts:

- `artifacts/phase_p1_serial_golden_v1/cohort_2026-09-06_23-35-17_d0eab2/attempt_0.json`
- `artifacts/phase_p1_serial_golden_v1/cohort_2026-09-06_23-36-15_566228/attempt_0.json`
- `artifacts/phase_p1_serial_golden_v1/cohort_2026-09-06_23-36-48_f9d210/attempt_0.json`
- `artifacts/phase_p1_serial_golden_v1/cohort_2026-09-06_23-37-19_3c3e02/attempt_0.json`
- `artifacts/phase_p1_serial_golden_v1/cohort_2026-09-06_23-37-50_ceeea6/attempt_0.json`

Control-plane gate:

- `.v2ctl/gates/gate_20260908-182623_957e0f08.json`
- `EXPERIMENT_EVIDENCE_golden_p1_f3c36372c70d9abe_2026-09-08.md`

The two 300-second scheduler timeouts during collection are retained in the
session transcript; neither produced a backend request or run artifact. The
initial non-QD2 smoke is retained at
`EXPERIMENT_EVIDENCE_golden_p1_e7c202ce749c413d_2026-09-08.md` and was not
counted in the QD2 cohort.
