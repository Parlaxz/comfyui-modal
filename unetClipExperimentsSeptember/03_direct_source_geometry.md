# September UNET/CLIP Experiment 03 - Direct-Source Geometry Sweep

PERFORMANCE_COMPARISON=NOT_PERFORMED

PERFORMANCE_VERDICT=NOT_PROVIDED

STATUS=COMPLETE

## Scope

Six direct-source geometry arms were collected with 12 eligible, non-snapshot/post-snapshot observations per value. The four newest observations in each arm are the requested additional runs and are retained separately as `EXTRA`; they are included in all arm summaries.

No performance winner or promotion decision is made by this report.

## Arm Inventory

| value | app | profile | deployment fingerprint | eligible | core | extra | geometry check |
|---:|---|---|---|---:|---:|---:|---|
| 32 | sept-unetclip-03-direct32 | golden_p1_direct32 | 33f737d5753a6d00afb0bdefb9a8c32e4d34c571e33545519de3ae5b9a79162c | 12 | 8 | 4 | PASS |
| 64 | sept-unetclip-03-direct64 | golden_p1_direct64 | 09d93bfe76b472e3bdd807d0d932b9bb9504faa2824e0760ae48c1da79893bb1 | 12 | 8 | 4 | PASS |
| 128 | sept-unetclip-03-direct128 | golden_p1_direct128 | e7058eeffa2cf0a909ae22922544bdda1241efc966e4d606bda199a83afacf9d | 12 | 8 | 4 | PASS |
| 256 | sept-unetclip-03-direct256 | golden_p1_direct256 | a23efcc7e5bccdaffebd07149bbd5f1abeea88c7fd5305d421ffdfb8d89bafee | 12 | 8 | 4 | PASS |
| 512 | sept-unetclip-03-direct512 | golden_p1_direct512 | 4de0c00f11de91ea99b8ce913f96a332b79720a1d18d34c039075104f84711c3 | 12 | 8 | 4 | PASS |
| 1024 | sept-unetclip-03-direct1024 | golden_p1_direct1024 | 5e455f65749b308d327acc5438edf01f3a335b11e203008f3a2cf23d4d56a144 | 12 | 8 | 4 | PASS |

## Per-Arm Statistics

| value | metric | min | max | range | mean | median | sample SD | CV |
|---:|---|---:|---:|---:|---:|---:|---:|---:|
| 32 | request wall (ms) | 32018.579 | 124791.554 | 92772.975 | 47294.814 | 35659.333 | 26959.819 | 0.570 |
| 32 | combined loader wall (ms) | 3413.410 | 4318.499 | 905.089 | 3774.852 | 3805.095 | 259.043 | 0.069 |
| 64 | request wall (ms) | 28736.475 | 253075.744 | 224339.269 | 67913.358 | 38460.868 | 64660.041 | 0.952 |
| 64 | combined loader wall (ms) | 3058.176 | 10301.226 | 7243.050 | 4865.613 | 3927.614 | 2332.438 | 0.479 |
| 128 | request wall (ms) | 27498.197 | 241004.215 | 213506.018 | 61499.155 | 30767.426 | 63492.484 | 1.032 |
| 128 | combined loader wall (ms) | 3274.677 | 5739.771 | 2465.094 | 3919.159 | 3692.151 | 772.973 | 0.197 |
| 256 | request wall (ms) | 25774.844 | 186325.952 | 160551.108 | 45843.484 | 28718.751 | 45571.493 | 0.994 |
| 256 | combined loader wall (ms) | 3049.238 | 9530.462 | 6481.224 | 4057.370 | 3568.433 | 1739.468 | 0.429 |
| 512 | request wall (ms) | 24461.874 | 129043.389 | 104581.515 | 40651.886 | 30062.431 | 29102.646 | 0.716 |
| 512 | combined loader wall (ms) | 3420.186 | 10366.527 | 6946.341 | 4368.957 | 3746.965 | 1917.448 | 0.439 |
| 1024 | request wall (ms) | 25330.058 | 128018.243 | 102688.185 | 52361.780 | 37752.005 | 35746.990 | 0.683 |
| 1024 | combined loader wall (ms) | 3845.253 | 7032.427 | 3187.174 | 4500.158 | 4306.723 | 847.852 | 0.188 |

## Additional Four Runs

The `EXTRA` rows below are the four newest eligible observations for each value and are included in the per-arm statistics above.

| attempt | value | request wall (ms) | artifact |
|---|---:|---:|---|
| 32_09 | 32 | 37737.611 | C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\artifacts\phase_p1_serial_golden_v1\cohort_2026-09-04_06-09-39_600eb6\attempt_0.json |
| 32_10 | 32 | 36119.034 | C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\artifacts\phase_p1_serial_golden_v1\cohort_2026-09-04_06-11-03_6ad888\attempt_0.json |
| 32_11 | 32 | 36255.931 | C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\artifacts\phase_p1_serial_golden_v1\cohort_2026-09-04_06-13-51_434b78\attempt_0.json |
| 32_12 | 32 | 34931.005 | C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\artifacts\phase_p1_serial_golden_v1\cohort_2026-09-04_06-15-08_502cff\attempt_0.json |
| 64_09 | 64 | 58401.669 | C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\artifacts\phase_p1_serial_golden_v1\cohort_2026-09-04_06-07-54_decad0\attempt_0.json |
| 64_10 | 64 | 32154.220 | C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\artifacts\phase_p1_serial_golden_v1\cohort_2026-09-04_06-09-39_bd2778\attempt_0.json |
| 64_11 | 64 | 77230.460 | C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\artifacts\phase_p1_serial_golden_v1\cohort_2026-09-04_06-11-03_798c40\attempt_0.json |
| 64_12 | 64 | 32612.650 | C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\artifacts\phase_p1_serial_golden_v1\cohort_2026-09-04_06-13-51_2e5c30\attempt_0.json |
| 128_09 | 128 | 29689.268 | C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\artifacts\phase_p1_serial_golden_v1\cohort_2026-09-04_06-09-38_0165f4\attempt_0.json |
| 128_10 | 128 | 41477.599 | C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\artifacts\phase_p1_serial_golden_v1\cohort_2026-09-04_06-11-03_411aad\attempt_0.json |
| 128_11 | 128 | 30172.494 | C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\artifacts\phase_p1_serial_golden_v1\cohort_2026-09-04_06-13-51_4a8329\attempt_0.json |
| 128_12 | 128 | 44464.102 | C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\artifacts\phase_p1_serial_golden_v1\cohort_2026-09-04_06-15-09_53c011\attempt_0.json |
| 256_09 | 256 | 28827.659 | C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\artifacts\phase_p1_serial_golden_v1\cohort_2026-09-04_06-11-03_6ef835\attempt_0.json |
| 256_10 | 256 | 28609.844 | C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\artifacts\phase_p1_serial_golden_v1\cohort_2026-09-04_06-13-51_3bf65b\attempt_0.json |
| 256_11 | 256 | 27515.449 | C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\artifacts\phase_p1_serial_golden_v1\cohort_2026-09-04_06-15-08_8b248b\attempt_0.json |
| 256_12 | 256 | 27540.914 | C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\artifacts\phase_p1_serial_golden_v1\cohort_2026-09-04_06-16-21_008d40\attempt_0.json |
| 512_09 | 512 | 27798.561 | C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\artifacts\phase_p1_serial_golden_v1\cohort_2026-09-04_06-13-51_e8af56\attempt_0.json |
| 512_10 | 512 | 36908.644 | C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\artifacts\phase_p1_serial_golden_v1\cohort_2026-09-04_06-15-08_e454c6\attempt_0.json |
| 512_11 | 512 | 25521.008 | C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\artifacts\phase_p1_serial_golden_v1\cohort_2026-09-04_06-16-21_9f887a\attempt_0.json |
| 512_12 | 512 | 24461.874 | C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\artifacts\phase_p1_serial_golden_v1\cohort_2026-09-04_06-17-10_f153a8\attempt_0.json |
| 1024_09 | 1024 | 27086.536 | C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\artifacts\phase_p1_serial_golden_v1\cohort_2026-09-04_06-13-51_298f89\attempt_0.json |
| 1024_10 | 1024 | 35987.025 | C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\artifacts\phase_p1_serial_golden_v1\cohort_2026-09-04_06-15-09_da8803\attempt_0.json |
| 1024_11 | 1024 | 26269.610 | C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\artifacts\phase_p1_serial_golden_v1\cohort_2026-09-04_06-16-21_c3cba3\attempt_0.json |
| 1024_12 | 1024 | 26671.749 | C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\artifacts\phase_p1_serial_golden_v1\cohort_2026-09-04_06-17-10_bc7854\attempt_0.json |

## Eligibility Ledger

| attempt | value | classification | counted | capture guard | true cold | valid | run manifest |
|---|---:|---|---|---|---|---|---|
| 32_01 | 32 | ELIGIBLE | true | ELIGIBLE | true | true | C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\.v2ctl\runs\run_20260904-001304_657b15fb.json |
| 32_02 | 32 | ELIGIBLE | true | ELIGIBLE | true | true | C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\.v2ctl\runs\run_20260904-001446_657b15fb.json |
| 32_03 | 32 | ELIGIBLE | true | ELIGIBLE | true | true | C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\.v2ctl\runs\run_20260904-001611_657b15fb.json |
| 32_04 | 32 | ELIGIBLE | true | ELIGIBLE | true | true | C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\.v2ctl\runs\run_20260904-003835_657b15fb.json |
| 32_05 | 32 | ELIGIBLE | true | ELIGIBLE | true | true | C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\.v2ctl\runs\run_20260904-005607_657b15fb.json |
| 32_06 | 32 | ELIGIBLE | true | ELIGIBLE | true | true | C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\.v2ctl\runs\run_20260904-010024_657b15fb.json |
| 32_07 | 32 | ELIGIBLE | true | ELIGIBLE | true | true | C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\.v2ctl\runs\run_20260904-010656_657b15fb.json |
| 32_08 | 32 | ELIGIBLE | true | ELIGIBLE | true | true | C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\.v2ctl\runs\run_20260904-010903_657b15fb.json |
| 32_09 | 32 | ELIGIBLE | true | ELIGIBLE | true | true | C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\.v2ctl\runs\run_20260904-011025_657b15fb.json |
| 32_10 | 32 | ELIGIBLE | true | ELIGIBLE | true | true | C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\.v2ctl\runs\run_20260904-011146_657b15fb.json |
| 32_11 | 32 | ELIGIBLE | true | ELIGIBLE | true | true | C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\.v2ctl\runs\run_20260904-011434_657b15fb.json |
| 32_12 | 32 | ELIGIBLE | true | ELIGIBLE | true | true | C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\.v2ctl\runs\run_20260904-011550_657b15fb.json |
| 64_01 | 64 | ELIGIBLE | true | ELIGIBLE | true | true | C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\.v2ctl\runs\run_20260904-002032_fb0b39df.json |
| 64_02 | 64 | ELIGIBLE | true | ELIGIBLE | true | true | C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\.v2ctl\runs\run_20260904-002326_fb0b39df.json |
| 64_03 | 64 | ELIGIBLE | true | ELIGIBLE | true | true | C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\.v2ctl\runs\run_20260904-002440_fb0b39df.json |
| 64_04 | 64 | ELIGIBLE | true | ELIGIBLE | true | true | C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\.v2ctl\runs\run_20260904-002600_fb0b39df.json |
| 64_05 | 64 | ELIGIBLE | true | ELIGIBLE | true | true | C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\.v2ctl\runs\run_20260904-003828_fb0b39df.json |
| 64_06 | 64 | ELIGIBLE | true | ELIGIBLE | true | true | C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\.v2ctl\runs\run_20260904-005543_fb0b39df.json |
| 64_07 | 64 | ELIGIBLE | true | ELIGIBLE | true | true | C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\.v2ctl\runs\run_20260904-010400_fb0b39df.json |
| 64_08 | 64 | ELIGIBLE | true | ELIGIBLE | true | true | C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\.v2ctl\runs\run_20260904-010647_fb0b39df.json |
| 64_09 | 64 | ELIGIBLE | true | ELIGIBLE | true | true | C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\.v2ctl\runs\run_20260904-010856_fb0b39df.json |
| 64_10 | 64 | ELIGIBLE | true | ELIGIBLE | true | true | C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\.v2ctl\runs\run_20260904-011016_fb0b39df.json |
| 64_11 | 64 | ELIGIBLE | true | ELIGIBLE | true | true | C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\.v2ctl\runs\run_20260904-011225_fb0b39df.json |
| 64_12 | 64 | ELIGIBLE | true | ELIGIBLE | true | true | C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\.v2ctl\runs\run_20260904-011428_fb0b39df.json |
| 128_01 | 128 | ELIGIBLE | true | ELIGIBLE | true | true | C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\.v2ctl\runs\run_20260904-002929_1a284482.json |
| 128_02 | 128 | ELIGIBLE | true | ELIGIBLE | true | true | C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\.v2ctl\runs\run_20260904-003042_1a284482.json |
| 128_03 | 128 | ELIGIBLE | true | ELIGIBLE | true | true | C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\.v2ctl\runs\run_20260904-003155_1a284482.json |
| 128_04 | 128 | ELIGIBLE | true | ELIGIBLE | true | true | C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\.v2ctl\runs\run_20260904-003824_1a284482.json |
| 128_05 | 128 | ELIGIBLE | true | ELIGIBLE | true | true | C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\.v2ctl\runs\run_20260904-005808_1a284482.json |
| 128_06 | 128 | ELIGIBLE | true | ELIGIBLE | true | true | C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\.v2ctl\runs\run_20260904-010348_1a284482.json |
| 128_07 | 128 | ELIGIBLE | true | ELIGIBLE | true | true | C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\.v2ctl\runs\run_20260904-010649_1a284482.json |
| 128_08 | 128 | ELIGIBLE | true | ELIGIBLE | true | true | C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\.v2ctl\runs\run_20260904-010827_1a284482.json |
| 128_09 | 128 | ELIGIBLE | true | ELIGIBLE | true | true | C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\.v2ctl\runs\run_20260904-011011_1a284482.json |
| 128_10 | 128 | ELIGIBLE | true | ELIGIBLE | true | true | C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\.v2ctl\runs\run_20260904-011148_1a284482.json |
| 128_11 | 128 | ELIGIBLE | true | ELIGIBLE | true | true | C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\.v2ctl\runs\run_20260904-011425_1a284482.json |
| 128_12 | 128 | ELIGIBLE | true | ELIGIBLE | true | true | C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\.v2ctl\runs\run_20260904-011556_1a284482.json |
| 256_01 | 256 | ELIGIBLE | true | ELIGIBLE | true | true | C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\.v2ctl\runs\run_20260904-003514_2b00bb9e.json |
| 256_02 | 256 | ELIGIBLE | true | ELIGIBLE | true | true | C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\.v2ctl\runs\run_20260904-003709_2b00bb9e.json |
| 256_03 | 256 | ELIGIBLE | true | ELIGIBLE | true | true | C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\.v2ctl\runs\run_20260904-003821_2b00bb9e.json |
| 256_04 | 256 | ELIGIBLE | true | ELIGIBLE | true | true | C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\.v2ctl\runs\run_20260904-005740_2b00bb9e.json |
| 256_05 | 256 | ELIGIBLE | true | ELIGIBLE | true | true | C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\.v2ctl\runs\run_20260904-010251_2b00bb9e.json |
| 256_06 | 256 | ELIGIBLE | true | ELIGIBLE | true | true | C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\.v2ctl\runs\run_20260904-010512_2b00bb9e.json |
| 256_07 | 256 | ELIGIBLE | true | ELIGIBLE | true | true | C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\.v2ctl\runs\run_20260904-010827_2b00bb9e.json |
| 256_08 | 256 | ELIGIBLE | true | ELIGIBLE | true | true | C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\.v2ctl\runs\run_20260904-011011_2b00bb9e.json |
| 256_09 | 256 | ELIGIBLE | true | ELIGIBLE | true | true | C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\.v2ctl\runs\run_20260904-011134_2b00bb9e.json |
| 256_10 | 256 | ELIGIBLE | true | ELIGIBLE | true | true | C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\.v2ctl\runs\run_20260904-011422_2b00bb9e.json |
| 256_11 | 256 | ELIGIBLE | true | ELIGIBLE | true | true | C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\.v2ctl\runs\run_20260904-011538_2b00bb9e.json |
| 256_12 | 256 | ELIGIBLE | true | ELIGIBLE | true | true | C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\.v2ctl\runs\run_20260904-011651_2b00bb9e.json |
| 512_01 | 512 | ELIGIBLE | true | ELIGIBLE | true | true | C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\.v2ctl\runs\run_20260904-005335_45da3cbb.json |
| 512_02 | 512 | ELIGIBLE | true | ELIGIBLE | true | true | C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\.v2ctl\runs\run_20260904-005422_45da3cbb.json |
| 512_03 | 512 | ELIGIBLE | true | ELIGIBLE | true | true | C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\.v2ctl\runs\run_20260904-005714_45da3cbb.json |
| 512_04 | 512 | ELIGIBLE | true | ELIGIBLE | true | true | C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\.v2ctl\runs\run_20260904-010014_45da3cbb.json |
| 512_05 | 512 | ELIGIBLE | true | ELIGIBLE | true | true | C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\.v2ctl\runs\run_20260904-010517_45da3cbb.json |
| 512_06 | 512 | ELIGIBLE | true | ELIGIBLE | true | true | C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\.v2ctl\runs\run_20260904-010850_45da3cbb.json |
| 512_07 | 512 | ELIGIBLE | true | ELIGIBLE | true | true | C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\.v2ctl\runs\run_20260904-011024_45da3cbb.json |
| 512_08 | 512 | ELIGIBLE | true | ELIGIBLE | true | true | C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\.v2ctl\runs\run_20260904-011314_45da3cbb.json |
| 512_09 | 512 | ELIGIBLE | true | ELIGIBLE | true | true | C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\.v2ctl\runs\run_20260904-011421_45da3cbb.json |
| 512_10 | 512 | ELIGIBLE | true | ELIGIBLE | true | true | C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\.v2ctl\runs\run_20260904-011547_45da3cbb.json |
| 512_11 | 512 | ELIGIBLE | true | ELIGIBLE | true | true | C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\.v2ctl\runs\run_20260904-011648_45da3cbb.json |
| 512_12 | 512 | ELIGIBLE | true | ELIGIBLE | true | true | C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\.v2ctl\runs\run_20260904-011736_45da3cbb.json |
| 1024_01 | 1024 | ELIGIBLE | true | ELIGIBLE | true | true | C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\.v2ctl\runs\run_20260904-005332_4aa2d332.json |
| 1024_02 | 1024 | ELIGIBLE | true | ELIGIBLE | true | true | C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\.v2ctl\runs\run_20260904-005421_4aa2d332.json |
| 1024_03 | 1024 | ELIGIBLE | true | ELIGIBLE | true | true | C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\.v2ctl\runs\run_20260904-005737_4aa2d332.json |
| 1024_04 | 1024 | ELIGIBLE | true | ELIGIBLE | true | true | C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\.v2ctl\runs\run_20260904-010052_4aa2d332.json |
| 1024_05 | 1024 | ELIGIBLE | true | ELIGIBLE | true | true | C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\.v2ctl\runs\run_20260904-010643_4aa2d332.json |
| 1024_06 | 1024 | ELIGIBLE | true | ELIGIBLE | true | true | C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\.v2ctl\runs\run_20260904-010849_4aa2d332.json |
| 1024_07 | 1024 | ELIGIBLE | true | ELIGIBLE | true | true | C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\.v2ctl\runs\run_20260904-011020_4aa2d332.json |
| 1024_08 | 1024 | ELIGIBLE | true | ELIGIBLE | true | true | C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\.v2ctl\runs\run_20260904-011313_4aa2d332.json |
| 1024_09 | 1024 | ELIGIBLE | true | ELIGIBLE | true | true | C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\.v2ctl\runs\run_20260904-011420_4aa2d332.json |
| 1024_10 | 1024 | ELIGIBLE | true | ELIGIBLE | true | true | C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\.v2ctl\runs\run_20260904-011546_4aa2d332.json |
| 1024_11 | 1024 | ELIGIBLE | true | ELIGIBLE | true | true | C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\.v2ctl\runs\run_20260904-011649_4aa2d332.json |
| 1024_12 | 1024 | ELIGIBLE | true | ELIGIBLE | true | true | C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\.v2ctl\runs\run_20260904-011738_4aa2d332.json |

## Identity and Disposition

- experiment id: `sept-unetclip-03-direct-source-geometry`
- expected output SHA: `8a92446890bebaecdc10eb5f207766a4b05af40ca3137108e25bfe88d9c1c44e`
- source identity: `All selected attempts are bound to their immutable per-arm deployment receipt. 32/64/128/256 were not redeployed after the later 512/1024 allowlist publication; v2ctl retained the immutable remote receipt and emitted source-drift warnings.`
- disposition: All six values have exactly 12 eligible observations. The four newest observations per value are the requested additional runs and are included. No performance winner or promotion decision is provided.

## Summary Artifact

`C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\unetClipExperimentsSeptember\03_direct_source_geometry_summary.json`

