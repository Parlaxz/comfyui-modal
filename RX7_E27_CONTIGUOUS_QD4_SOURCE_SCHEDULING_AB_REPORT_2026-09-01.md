# RX7 E27 Contiguous QD4 Source Scheduling A/B Report

Date: 2026-09-01  
Experiment: RX7 only; no RX7 integration and no RX8 start.

## Verdict

**ACCEPT_STATIC_E27**

The isolated `static_e27` arm is accepted for this comparison. It completed
the required six-run confirmation cohort with exact output, valid true-cold
identity, no fallback, and no seriality violations. Its median total request
time and median CLIP-load time were lower than the dispatcher control.

This verdict does not claim a direct source-bandwidth or QD-occupancy win:
the current runtime artifact records `source_qd_target=4`, but source-QD
occupancy and source-wall timing fields are unavailable (`null`). The verdict
is based on the validated arm identity, contiguous static partition proof, and
equivalent end-to-end/CLIP-load timings.

## Frozen Identity

| Item | Value |
|---|---|
| Workspace | Modal `Testing 7` (`ws_eaef96004dac`) |
| Profile | `golden_p1` |
| Class / method | `ModalRuntimeEntrypointV2` / `run_golden_serial_stream` |
| GPU | `rtx-pro-6000` |
| Backend | explicit `pytorch` |
| Workflow SHA | `14f815f1916e075ae79de7325681f6b0ec2216b8ad86c45e9bfa18f6388f5ea9` |
| Expected output SHA | `8a92446890bebaecdc10eb5f207766a4b05af40ca3137108e25bfe88d9c1c44e` |
| Publisher generation | `2853bea2379ad48b85b54f9d10ae01677bded3191b0a85bd53cbd246eb47ebe2` |
| Control deployment | `rx7-e27-control`, `165997db2bd87600615524c122865b3bab06202dc0fc0dd0cb9ef5937c9cf2ae` |
| Static deployment | `rx7-e27-static`, `6f1a32acd2d42150c117ace4e2203867fad5023fedf76bc64579b15b1fcaa2c3` |

Both deployments passed doctor/source-probe checks. The profile was restored
to its baseline `legacy` value after confirmation; no deploy was performed
after the measurement cohorts.

## Confirmation Results

All twelve runs below were valid, true-cold, single-request runs with one
terminal result, exact output SHA, zero DNF, zero transport fallback, and
zero seriality violations.

### Total request duration (ms)

| Arm | Raw durations | Mean | Median | Min | Max | Range | Sample SD | CV |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| Dispatcher control | 29311.277, 74754.025, 36579.626, 23822.577, 25659.068, 24006.175 | 35688.791 | 27485.173 | 23822.577 | 74754.025 | 50931.448 | 19725.337 | 0.553 |
| Static E27 | 20204.488, 19806.117, 32825.490, 23551.067, 20204.805, 52563.720 | 28192.615 | 21877.936 | 19806.117 | 52563.720 | 32757.603 | 12922.127 | 0.458 |

Static E27 median total duration was **20.4% lower** than control; mean was
**21.0% lower**.

### Selected stage medians (ms)

| Stage | Control | Static E27 | Static vs control |
|---|---:|---:|---:|
| `golden_clip_load` | 1862.709 | 1623.743 | -12.8% |
| `golden_clip_forward` | 1676.857 | 1910.512 | +13.9% |
| `golden_unet_load` | 2098.561 | 1960.827 | -6.6% |
| `golden_vae_load` | 184.243 | 107.137 | -41.8% |
| `golden_sampling` | 5964.291 | 5895.927 | -1.1% |
| `golden_output` | 177.820 | 162.689 | -8.5% |

The CLIP-forward stage is slower for static E27, so the result is not a
universal improvement across every stage.

## Static Scheduling Proof

Each static confirmation artifact reports:

- `execution_arm=static_e27`;
- four producer IDs `[0, 1, 2, 3]`;
- four contiguous static regions covering the same `8,044,936,192` source
  bytes as control;
- 32 MiB QD4 block configuration;
- complete source/H2D reconciliation and zero fallback;
- monotonic producer source offsets;
- one owner and quiescence before bind/forward.

Control reports `execution_arm=dispatcher`, the same source byte total and
four producers, with dynamic producer regions and 240 reads. Static reports
243 reads because its four fixed region boundaries add three boundary reads;
all planned and completed bytes still reconcile exactly.

## Authoritative Artifacts

Confirmation manifests:

- Control: `.v2ctl/confirmations/confirm_20260901-170959_b561647c.json`
- Static: `.v2ctl/confirmations/confirm_20260901-171335_a6d4f18b.json`

Control cohort directories:

- `artifacts/phase_p1_serial_golden_v1/cohort_2026-09-01_17-06-15_5af272`
- `artifacts/phase_p1_serial_golden_v1/cohort_2026-09-01_17-06-47_5b0588`
- `artifacts/phase_p1_serial_golden_v1/cohort_2026-09-01_17-08-03_9d7245`
- `artifacts/phase_p1_serial_golden_v1/cohort_2026-09-01_17-08-42_13d865`
- `artifacts/phase_p1_serial_golden_v1/cohort_2026-09-01_17-09-07_3d012c`
- `artifacts/phase_p1_serial_golden_v1/cohort_2026-09-01_17-09-35_5d96be`

Static cohort directories:

- `artifacts/phase_p1_serial_golden_v1/cohort_2026-09-01_17-10-34_0b5ea0`
- `artifacts/phase_p1_serial_golden_v1/cohort_2026-09-01_17-10-58_c94483`
- `artifacts/phase_p1_serial_golden_v1/cohort_2026-09-01_17-11-19_d98b45`
- `artifacts/phase_p1_serial_golden_v1/cohort_2026-09-01_17-11-54_d1ac6e`
- `artifacts/phase_p1_serial_golden_v1/cohort_2026-09-01_17-12-20_c9fc2a`
- `artifacts/phase_p1_serial_golden_v1/cohort_2026-09-01_17-12-42_280411`

The earlier noncanonical `bfb360008914dbacbe594b22dc09fd2b7658fa4d63ed7c25364806ce0b2280ce`
attempts were retained as evidence and excluded from the accepted cohort.
