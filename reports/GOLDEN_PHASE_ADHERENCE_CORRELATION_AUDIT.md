# Golden PHASE_STABLE turn-adherence correlation audit

Read-only recomputation from retained invocation-bound artifacts; no deployment, Modal job, benchmark rerun, code change, or alteration of prior experiment evidence was performed.

## Question and method

- Question: does stronger adherence to PHASE_STABLE's intended reader-turn schedule correlate with better source performance?
- Authority: raw `source_operation_records` from each retained `attempt_0.json` (with `attempt_0_events.json` only as the parser's fallback when needed). The repeated arm-level aggregate table from the earlier report is not used.
- A match is `actual reader == scheduled_reader` for a raw operation row. Overall/model/third fractions use only rows with a non-null scheduled reader; total operations is the raw operation count.
- Native p50/p90 are recomputed from raw `native_duration_ns`; model source wall is first actual launch to last native exit for that model; source-envelope wall is first launch to last native exit across CLIP and UNET; throughput is model bytes divided by model source wall.
- Pearson and Spearman are descriptive only. p-values are two-sided scipy values; bootstrap intervals use 2,000 deterministic resamples; permutation p uses 3,000 deterministic permutations. Small n and outliers dominate uncertainty.

## Cohort identity and deduplication

The repository's prior report (`GOLDEN_SOURCE_ADMISSION_STATE_AB.md` at the preceding report commit) contains the original 24-run list: 19 manifests collected before the final five, followed by the five manifests that begin the current second-cohort report. The current report contains the second 24-run list. Identity was checked by exact `.v2ctl` run-manifest path and request ID; the same five path/request pairs occur in both lists.

| Evidence set | Valid runs in report/list | Unique after dedup | CURRENT | FIRST_BLOCK_GATE | PHASE_STABLE |
|---|---:|---:|---:|---:|---:|
| Original cohort | 24 | 24 | 8 | 8 | 8 |
| Second cohort | 24 | 24 | 8 | 8 | 8 |
| Overlap | 5 | counted once | 2 | 1 | 2 |
| Unique union | 43 | 43 | 14 | 15 | 14 |

### Reused manifests (count once)

| Manifest/request identity | Original order | Cohort 2 order | Arm |
|---|---:|---:|---|
| `run_20261006-164829_97d1739e.json` / `golden-p1-0-68c4691254a1` | 20 | 1 | CURRENT |
| `run_20261006-164929_fd4a1c8f.json` / `golden-p1-0-974799d1ce00` | 21 | 2 | FIRST_BLOCK_GATE |
| `run_20261006-165012_4b6931ae.json` / `golden-p1-0-eb68cc401165` | 22 | 3 | PHASE_STABLE |
| `run_20261006-165126_4b6931ae.json` / `golden-p1-0-b3dd83455375` | 23 | 4 | PHASE_STABLE |
| `run_20261006-165156_97d1739e.json` / `golden-p1-0-ace7bacce749` | 24 | 5 | CURRENT |

Result of identity check: **43 unique runs and 14 unique PHASE_STABLE runs**, consistent with the requested expected counts. All 43 selected runs are valid/true-cold and `us-central` under the existing parser's evidence gates.

## Exact unique-run dataset

`original_order` and `cohort2_order` preserve each report's collection order. `block/triplet` is a deterministic local grouping of three consecutive collection positions. The five reused manifests inherit their real cohort-2 block because their original-report tail placement is not a complete triplet. The raw artifact manifest path is included in addition to the `.v2ctl` run manifest.

| ID | Cohort membership | Original order | Cohort 2 order | Block/slot | Arm | Provider | Region | Request ID | Run manifest | Raw artifact manifest | Source envelope ms | CLIP wall ms | UNET wall ms | CLIP p50/p90 ms | UNET p50/p90 ms | CLIP GB/s | UNET GB/s | abs CLIP-UNET p50 split ms |
|---|---|---:|---:|---|---|---|---|---|---|---|---:|---:|---:|---|---|---:|---:|---:|
| R01 | original | 1 | - | O1/1 | CURRENT | CLOUD_PROVIDER_AZURE | us-central | golden-p1-0-0f31449ad9c4 | .v2ctl\runs\run_20261006-160408_c45c9dff.json | C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\.slim\worktrees\golden-source-admission-state-ab\artifacts\phase_p1_parallel_golden_v1\cohort_2026-10-06_21-02-59_f25bf4\manifest.json | 4136.323 | 1733.366 | 2171.087 | 47.374/65.067 | 41.428/50.401 | 4.641 | 5.670 | 5.947 |
| R02 | original | 2 | - | O1/2 | FIRST_BLOCK_GATE | CLOUD_PROVIDER_UNSPECIFIED | us-central | golden-p1-0-d2f0dbc261b0 | .v2ctl\runs\run_20261006-160605_cca432d0.json | C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\.slim\worktrees\golden-source-admission-state-ab\artifacts\phase_p1_parallel_golden_v1\cohort_2026-10-06_21-05-00_278d02\manifest.json | 6213.578 | 2333.240 | 3784.451 | 73.717/88.664 | 75.949/95.722 | 3.448 | 3.253 | 2.233 |
| R03 | original | 3 | - | O1/3 | PHASE_STABLE | CLOUD_PROVIDER_UNSPECIFIED | us-central | golden-p1-0-6e46ad378fa0 | .v2ctl\runs\run_20261006-160800_3e946465.json | C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\.slim\worktrees\golden-source-admission-state-ab\artifacts\phase_p1_parallel_golden_v1\cohort_2026-10-06_21-07-38_9d941b\manifest.json | 5469.140 | 1975.897 | 3002.127 | 53.876/76.528 | 41.283/60.638 | 4.072 | 4.100 | 12.593 |
| R04 | original | 4 | - | O2/1 | PHASE_STABLE | CLOUD_PROVIDER_UNSPECIFIED | us-central | golden-p1-0-5dac4837db40 | .v2ctl\runs\run_20261006-160833_3e946465.json | C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\.slim\worktrees\golden-source-admission-state-ab\artifacts\phase_p1_parallel_golden_v1\cohort_2026-10-06_21-08-14_552045\manifest.json | 7070.303 | 2583.975 | 4392.321 | 82.523/113.173 | 85.225/121.621 | 3.113 | 2.803 | 2.701 |
| R05 | original | 5 | - | O2/2 | CURRENT | CLOUD_PROVIDER_UNSPECIFIED | us-central | golden-p1-0-0b10c4ffa755 | .v2ctl\runs\run_20261006-160906_c45c9dff.json | C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\.slim\worktrees\golden-source-admission-state-ab\artifacts\phase_p1_parallel_golden_v1\cohort_2026-10-06_21-08-47_ca21f0\manifest.json | 4783.088 | 2242.964 | 2443.443 | 71.643/89.268 | 44.719/51.338 | 3.587 | 5.038 | 26.925 |
| R06 | original | 6 | - | O2/3 | FIRST_BLOCK_GATE | CLOUD_PROVIDER_AZURE | us-central | golden-p1-0-db2b9e08ddea | .v2ctl\runs\run_20261006-161006_cca432d0.json | C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\.slim\worktrees\golden-source-admission-state-ab\artifacts\phase_p1_parallel_golden_v1\cohort_2026-10-06_21-09-20_d6200f\manifest.json | 4593.213 | 1732.044 | 2449.384 | 53.733/64.588 | 48.895/58.608 | 4.645 | 5.026 | 4.837 |
| R07 | original | 7 | - | O3/1 | FIRST_BLOCK_GATE | CLOUD_PROVIDER_UNSPECIFIED | us-central | golden-p1-0-dd90cfdd9366 | .v2ctl\runs\run_20261006-161041_cca432d0.json | C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\.slim\worktrees\golden-source-admission-state-ab\artifacts\phase_p1_parallel_golden_v1\cohort_2026-10-06_21-10-24_8cef05\manifest.json | 4591.859 | 1891.488 | 2602.037 | 55.146/76.659 | 48.733/58.866 | 4.253 | 4.731 | 6.414 |
| R08 | original | 8 | - | O3/2 | PHASE_STABLE | CLOUD_PROVIDER_UNSPECIFIED | us-central | golden-p1-0-8cca1410e757 | .v2ctl\runs\run_20261006-161119_3e946465.json | C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\.slim\worktrees\golden-source-admission-state-ab\artifacts\phase_p1_parallel_golden_v1\cohort_2026-10-06_21-10-59_6029df\manifest.json | 6575.144 | 2301.474 | 3950.677 | 75.122/88.105 | 81.122/114.582 | 3.496 | 3.116 | 6.000 |
| R09 | original | 9 | - | O3/3 | CURRENT | CLOUD_PROVIDER_UNSPECIFIED | us-central | golden-p1-0-2a47fc19ecae | .v2ctl\runs\run_20261006-161152_c45c9dff.json | C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\.slim\worktrees\golden-source-admission-state-ab\artifacts\phase_p1_parallel_golden_v1\cohort_2026-10-06_21-11-33_5b842d\manifest.json | 6000.817 | 2249.834 | 3653.320 | 70.904/92.976 | 67.838/103.158 | 3.576 | 3.369 | 3.065 |
| R10 | original | 10 | - | O4/1 | CURRENT | CLOUD_PROVIDER_UNSPECIFIED | us-central | golden-p1-0-592d69add4b8 | .v2ctl\runs\run_20261006-161221_c45c9dff.json | C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\.slim\worktrees\golden-source-admission-state-ab\artifacts\phase_p1_parallel_golden_v1\cohort_2026-10-06_21-12-05_6ab979\manifest.json | 3799.552 | 1379.843 | 2336.754 | 43.221/54.868 | 43.194/52.324 | 5.830 | 5.268 | 0.028 |
| R11 | original | 11 | - | O4/2 | FIRST_BLOCK_GATE | CLOUD_PROVIDER_UNSPECIFIED | us-central | golden-p1-0-61611085385d | .v2ctl\runs\run_20261006-161259_cca432d0.json | C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\.slim\worktrees\golden-source-admission-state-ab\artifacts\phase_p1_parallel_golden_v1\cohort_2026-10-06_21-12-39_914c82\manifest.json | 6691.024 | 3103.059 | 3489.133 | 96.550/133.903 | 64.604/100.083 | 2.593 | 3.528 | 31.946 |
| R12 | original | 12 | - | O4/3 | PHASE_STABLE | CLOUD_PROVIDER_AZURE | us-central | golden-p1-0-0b2fadac4af2 | .v2ctl\runs\run_20261006-161330_3e946465.json | C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\.slim\worktrees\golden-source-admission-state-ab\artifacts\phase_p1_parallel_golden_v1\cohort_2026-10-06_21-13-12_535263\manifest.json | 4398.174 | 1792.500 | 2491.324 | 55.681/77.904 | 49.376/59.803 | 4.488 | 4.941 | 6.305 |
| R13 | original | 13 | - | O5/1 | PHASE_STABLE | CLOUD_PROVIDER_UNSPECIFIED | us-central | golden-p1-0-23cc218345cb | .v2ctl\runs\run_20261006-161516_3e946465.json | C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\.slim\worktrees\golden-source-admission-state-ab\artifacts\phase_p1_parallel_golden_v1\cohort_2026-10-06_21-14-58_f62632\manifest.json | 4338.555 | 1601.214 | 2428.772 | 50.788/63.737 | 50.843/56.682 | 5.024 | 5.068 | 0.054 |
| R14 | original | 14 | - | O5/2 | CURRENT | CLOUD_PROVIDER_UNSPECIFIED | us-central | golden-p1-0-c0ab68d4e905 | .v2ctl\runs\run_20261006-161558_c45c9dff.json | C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\.slim\worktrees\golden-source-admission-state-ab\artifacts\phase_p1_parallel_golden_v1\cohort_2026-10-06_21-15-39_2e2500\manifest.json | 6670.025 | 2347.893 | 3955.510 | 74.217/99.005 | 82.587/107.573 | 3.426 | 3.112 | 8.371 |
| R15 | original | 15 | - | O5/3 | FIRST_BLOCK_GATE | CLOUD_PROVIDER_UNSPECIFIED | us-central | golden-p1-0-2f4b006d183c | .v2ctl\runs\run_20261006-161637_cca432d0.json | C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\.slim\worktrees\golden-source-admission-state-ab\artifacts\phase_p1_parallel_golden_v1\cohort_2026-10-06_21-16-18_ad1efb\manifest.json | 5909.584 | 2331.476 | 3443.165 | 71.226/94.216 | 66.928/81.972 | 3.451 | 3.575 | 4.297 |
| R16 | original | 16 | - | O6/1 | CURRENT | CLOUD_PROVIDER_UNSPECIFIED | us-central | golden-p1-0-711f601afebd | .v2ctl\runs\run_20261006-161733_c45c9dff.json | C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\.slim\worktrees\golden-source-admission-state-ab\artifacts\phase_p1_parallel_golden_v1\cohort_2026-10-06_21-17-00_274daf\manifest.json | 4855.130 | 1728.722 | 2618.157 | 55.250/66.035 | 54.554/63.717 | 4.654 | 4.702 | 0.695 |
| R17 | original | 17 | - | O6/2 | FIRST_BLOCK_GATE | CLOUD_PROVIDER_UNSPECIFIED | us-central | golden-p1-0-8ce03baab5d2 | .v2ctl\runs\run_20261006-161811_cca432d0.json | C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\.slim\worktrees\golden-source-admission-state-ab\artifacts\phase_p1_parallel_golden_v1\cohort_2026-10-06_21-17-55_8f5a23\manifest.json | 3368.743 | 1261.140 | 2019.884 | 35.894/52.864 | 37.626/49.002 | 6.379 | 6.094 | 1.731 |
| R18 | original | 18 | - | O6/3 | PHASE_STABLE | CLOUD_PROVIDER_AZURE | us-central | golden-p1-0-8d991f9b793f | .v2ctl\runs\run_20261006-161843_3e946465.json | C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\.slim\worktrees\golden-source-admission-state-ab\artifacts\phase_p1_parallel_golden_v1\cohort_2026-10-06_21-18-25_46f5a9\manifest.json | 3819.614 | 1491.968 | 2029.203 | 46.723/58.238 | 41.075/54.096 | 5.392 | 6.066 | 5.647 |
| R19 | original | 19 | - | O7/1 | FIRST_BLOCK_GATE | CLOUD_PROVIDER_UNSPECIFIED | us-central | golden-p1-0-42a8cdcba25d | .v2ctl\runs\run_20261006-161920_cca432d0.json | C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\.slim\worktrees\golden-source-admission-state-ab\artifacts\phase_p1_parallel_golden_v1\cohort_2026-10-06_21-19-02_e2206a\manifest.json | 4448.669 | 1583.774 | 2514.984 | 47.593/60.097 | 52.758/62.400 | 5.080 | 4.895 | 5.166 |
| R20 | original+cohort2 (reused) | 20 | 1 | S1/1 | CURRENT | CLOUD_PROVIDER_UNSPECIFIED | us-central | golden-p1-0-68c4691254a1 | .v2ctl\runs\run_20261006-164829_97d1739e.json | C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\.slim\worktrees\golden-source-admission-state-ab\artifacts\phase_p1_parallel_golden_v1\cohort_2026-10-06_21-47-25_c5cbf0\manifest.json | 5428.848 | 1867.823 | 3464.679 | 57.748/79.073 | 68.213/92.453 | 4.307 | 3.553 | 10.465 |
| R21 | original+cohort2 (reused) | 21 | 2 | S1/2 | FIRST_BLOCK_GATE | CLOUD_PROVIDER_UNSPECIFIED | us-central | golden-p1-0-974799d1ce00 | .v2ctl\runs\run_20261006-164929_fd4a1c8f.json | C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\.slim\worktrees\golden-source-admission-state-ab\artifacts\phase_p1_parallel_golden_v1\cohort_2026-10-06_21-49-09_f59417\manifest.json | 6776.850 | 2120.873 | 4344.957 | 65.007/83.259 | 93.949/132.330 | 3.793 | 2.833 | 28.942 |
| R22 | original+cohort2 (reused) | 22 | 3 | S1/3 | PHASE_STABLE | CLOUD_PROVIDER_UNSPECIFIED | us-central | golden-p1-0-eb68cc401165 | .v2ctl\runs\run_20261006-165012_4b6931ae.json | C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\.slim\worktrees\golden-source-admission-state-ab\artifacts\phase_p1_parallel_golden_v1\cohort_2026-10-06_21-49-44_3bf51e\manifest.json | 3353.135 | 1280.587 | 1973.476 | 38.514/55.308 | 36.754/39.623 | 6.282 | 6.238 | 1.760 |
| R23 | original+cohort2 (reused) | 23 | 4 | S2/1 | PHASE_STABLE | CLOUD_PROVIDER_AZURE | us-central | golden-p1-0-b3dd83455375 | .v2ctl\runs\run_20261006-165126_4b6931ae.json | C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\.slim\worktrees\golden-source-admission-state-ab\artifacts\phase_p1_parallel_golden_v1\cohort_2026-10-06_21-50-22_830b66\manifest.json | 3284.299 | 1327.494 | 1697.029 | 35.173/63.861 | 32.824/48.817 | 6.060 | 7.254 | 2.349 |
| R24 | original+cohort2 (reused) | 24 | 5 | S2/2 | CURRENT | CLOUD_PROVIDER_UNSPECIFIED | us-central | golden-p1-0-ace7bacce749 | .v2ctl\runs\run_20261006-165156_97d1739e.json | C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\.slim\worktrees\golden-source-admission-state-ab\artifacts\phase_p1_parallel_golden_v1\cohort_2026-10-06_21-51-40_36156e\manifest.json | 4240.711 | 1516.647 | 2609.846 | 46.716/59.139 | 46.404/76.784 | 5.304 | 4.717 | 0.312 |
| R25 | cohort2-new | - | 6 | S2/3 | FIRST_BLOCK_GATE | CLOUD_PROVIDER_UNSPECIFIED | us-central | golden-p1-0-43c1235dbf2a | .v2ctl\runs\run_20261006-165236_fd4a1c8f.json | C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\.slim\worktrees\golden-source-admission-state-ab\artifacts\phase_p1_parallel_golden_v1\cohort_2026-10-06_21-52-19_3b75a2\manifest.json | 5121.051 | 1989.433 | 2823.429 | 52.444/83.892 | 52.492/69.068 | 4.044 | 4.360 | 0.048 |
| R26 | cohort2-new | - | 7 | S3/1 | FIRST_BLOCK_GATE | CLOUD_PROVIDER_UNSPECIFIED | us-central | golden-p1-0-d2aa6669a579 | .v2ctl\runs\run_20261006-165307_fd4a1c8f.json | C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\.slim\worktrees\golden-source-admission-state-ab\artifacts\phase_p1_parallel_golden_v1\cohort_2026-10-06_21-52-52_99fe60\manifest.json | 4396.404 | 1504.285 | 2332.108 | 44.424/58.695 | 41.720/75.736 | 5.348 | 5.278 | 2.703 |
| R27 | cohort2-new | - | 8 | S3/2 | PHASE_STABLE | CLOUD_PROVIDER_UNSPECIFIED | us-central | golden-p1-0-d023eec82e6e | .v2ctl\runs\run_20261006-165341_4b6931ae.json | C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\.slim\worktrees\golden-source-admission-state-ab\artifacts\phase_p1_parallel_golden_v1\cohort_2026-10-06_21-53-22_64836c\manifest.json | 5990.810 | 2183.272 | 3487.434 | 69.439/88.989 | 73.952/89.543 | 3.685 | 3.530 | 4.513 |
| R28 | cohort2-new | - | 9 | S3/3 | CURRENT | CLOUD_PROVIDER_UNSPECIFIED | us-central | golden-p1-0-09697d96352f | .v2ctl\runs\run_20261006-165409_97d1739e.json | C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\.slim\worktrees\golden-source-admission-state-ab\artifacts\phase_p1_parallel_golden_v1\cohort_2026-10-06_21-53-51_341349\manifest.json | 5070.823 | 2182.927 | 2593.833 | 70.571/87.683 | 53.782/64.673 | 3.685 | 4.746 | 16.790 |
| R29 | cohort2-new | - | 10 | S4/1 | CURRENT | CLOUD_PROVIDER_UNSPECIFIED | us-central | golden-p1-0-649561530c89 | .v2ctl\runs\run_20261006-165443_97d1739e.json | C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\.slim\worktrees\golden-source-admission-state-ab\artifacts\phase_p1_parallel_golden_v1\cohort_2026-10-06_21-54-23_b69060\manifest.json | 6648.891 | 3302.562 | 3248.164 | 101.235/165.789 | 63.804/81.412 | 2.436 | 3.790 | 37.431 |
| R30 | cohort2-new | - | 11 | S4/2 | FIRST_BLOCK_GATE | CLOUD_PROVIDER_AZURE | us-central | golden-p1-0-e23e716a7e60 | .v2ctl\runs\run_20261006-170225_fd4a1c8f.json | C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\.slim\worktrees\golden-source-admission-state-ab\artifacts\phase_p1_parallel_golden_v1\cohort_2026-10-06_21-54-59_d6b6e4\manifest.json | 6161.160 | 1846.349 | 3791.819 | 54.219/71.988 | 76.276/116.117 | 4.357 | 3.246 | 22.057 |
| R31 | cohort2-new | - | 12 | S4/3 | PHASE_STABLE | CLOUD_PROVIDER_UNSPECIFIED | us-central | golden-p1-0-b49c908f3d52 | .v2ctl\runs\run_20261006-170348_4b6931ae.json | C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\.slim\worktrees\golden-source-admission-state-ab\artifacts\phase_p1_parallel_golden_v1\cohort_2026-10-06_22-02-36_04ec6c\manifest.json | 4464.875 | 1681.069 | 2684.577 | 52.109/68.782 | 50.107/62.317 | 4.786 | 4.585 | 2.002 |
| R32 | cohort2-new | - | 13 | S5/1 | PHASE_STABLE | CLOUD_PROVIDER_UNSPECIFIED | us-central | golden-p1-0-66a5391d5d89 | .v2ctl\runs\run_20261006-170543_4b6931ae.json | C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\.slim\worktrees\golden-source-admission-state-ab\artifacts\phase_p1_parallel_golden_v1\cohort_2026-10-06_22-04-04_b6e736\manifest.json | 4423.254 | 1695.170 | 2626.730 | 54.119/66.770 | 50.626/58.329 | 4.746 | 4.686 | 3.493 |
| R33 | cohort2-new | - | 14 | S5/2 | CURRENT | CLOUD_PROVIDER_UNSPECIFIED | us-central | golden-p1-0-ba0db36dc589 | .v2ctl\runs\run_20261006-170826_97d1739e.json | C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\.slim\worktrees\golden-source-admission-state-ab\artifacts\phase_p1_parallel_golden_v1\cohort_2026-10-06_22-05-57_5145a2\manifest.json | 4542.490 | 1803.713 | 2378.208 | 44.783/81.421 | 49.933/56.355 | 4.460 | 5.176 | 5.150 |
| R34 | cohort2-new | - | 15 | S5/3 | FIRST_BLOCK_GATE | CLOUD_PROVIDER_OCI | us-central | golden-p1-0-5959b7081b20 | .v2ctl\runs\run_20261006-170904_fd4a1c8f.json | C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\.slim\worktrees\golden-source-admission-state-ab\artifacts\phase_p1_parallel_golden_v1\cohort_2026-10-06_22-08-39_5e01e7\manifest.json | 4804.572 | 1771.840 | 2899.226 | 51.196/75.420 | 53.350/69.185 | 4.540 | 4.246 | 2.153 |
| R35 | cohort2-new | - | 16 | S6/1 | FIRST_BLOCK_GATE | CLOUD_PROVIDER_UNSPECIFIED | us-central | golden-p1-0-654c0cbd895b | .v2ctl\runs\run_20261006-171226_fd4a1c8f.json | C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\.slim\worktrees\golden-source-admission-state-ab\artifacts\phase_p1_parallel_golden_v1\cohort_2026-10-06_22-09-17_db43d0\manifest.json | 6104.284 | 2541.600 | 3239.940 | 80.786/109.399 | 66.024/78.899 | 3.165 | 3.799 | 14.761 |
| R36 | cohort2-new | - | 17 | S6/2 | PHASE_STABLE | CLOUD_PROVIDER_OCI | us-central | golden-p1-0-f65314e3f4d7 | .v2ctl\runs\run_20261006-171301_4b6931ae.json | C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\.slim\worktrees\golden-source-admission-state-ab\artifacts\phase_p1_parallel_golden_v1\cohort_2026-10-06_22-12-40_b6421a\manifest.json | 4889.330 | 1863.757 | 2897.108 | 56.539/77.231 | 54.219/64.437 | 4.317 | 4.249 | 2.321 |
| R37 | cohort2-new | - | 18 | S6/3 | CURRENT | CLOUD_PROVIDER_UNSPECIFIED | us-central | golden-p1-0-82d64a5342ee | .v2ctl\runs\run_20261006-171334_97d1739e.json | C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\.slim\worktrees\golden-source-admission-state-ab\artifacts\phase_p1_parallel_golden_v1\cohort_2026-10-06_22-13-14_b61450\manifest.json | 5586.573 | 1988.235 | 3299.926 | 62.086/83.114 | 67.587/96.062 | 4.046 | 3.730 | 5.501 |
| R38 | cohort2-new | - | 19 | S7/1 | CURRENT | CLOUD_PROVIDER_OCI | us-central | golden-p1-0-6a733b0d2424 | .v2ctl\runs\run_20261006-171741_97d1739e.json | C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\.slim\worktrees\golden-source-admission-state-ab\artifacts\phase_p1_parallel_golden_v1\cohort_2026-10-06_22-13-49_a82701\manifest.json | 4694.941 | 1696.342 | 2892.140 | 53.061/68.961 | 54.657/67.321 | 4.743 | 4.256 | 1.596 |
| R39 | cohort2-new | - | 20 | S7/2 | FIRST_BLOCK_GATE | CLOUD_PROVIDER_UNSPECIFIED | us-central | golden-p1-0-0491b0e2f625 | .v2ctl\runs\run_20261006-171810_fd4a1c8f.json | C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\.slim\worktrees\golden-source-admission-state-ab\artifacts\phase_p1_parallel_golden_v1\cohort_2026-10-06_22-17-50_b918dc\manifest.json | 5953.608 | 2374.144 | 3249.249 | 74.959/94.154 | 67.982/81.750 | 3.389 | 3.789 | 6.977 |
| R40 | cohort2-new | - | 21 | S7/3 | PHASE_STABLE | CLOUD_PROVIDER_OCI | us-central | golden-p1-0-0f826dd1b9b6 | .v2ctl\runs\run_20261006-171848_4b6931ae.json | C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\.slim\worktrees\golden-source-admission-state-ab\artifacts\phase_p1_parallel_golden_v1\cohort_2026-10-06_22-18-26_1aaa82\manifest.json | 4266.879 | 1589.088 | 2580.985 | 49.079/74.139 | 50.046/58.984 | 5.063 | 4.769 | 0.967 |
| R41 | cohort2-new | - | 22 | S8/1 | PHASE_STABLE | CLOUD_PROVIDER_UNSPECIFIED | us-central | golden-p1-0-6c21c8e160d4 | .v2ctl\runs\run_20261006-171914_4b6931ae.json | C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\.slim\worktrees\golden-source-admission-state-ab\artifacts\phase_p1_parallel_golden_v1\cohort_2026-10-06_22-18-59_2b3c6f\manifest.json | 4436.148 | 1439.077 | 2907.118 | 42.356/61.987 | 58.980/71.758 | 5.590 | 4.234 | 16.624 |
| R42 | cohort2-new | - | 23 | S8/2 | CURRENT | CLOUD_PROVIDER_AZURE | us-central | golden-p1-0-8e306dca122f | .v2ctl\runs\run_20261006-171942_97d1739e.json | C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\.slim\worktrees\golden-source-admission-state-ab\artifacts\phase_p1_parallel_golden_v1\cohort_2026-10-06_22-19-24_33e126\manifest.json | 4658.065 | 1693.963 | 2822.620 | 52.563/72.741 | 49.887/58.691 | 4.749 | 4.361 | 2.676 |
| R43 | cohort2-new | - | 24 | S8/3 | FIRST_BLOCK_GATE | CLOUD_PROVIDER_AZURE | us-central | golden-p1-0-f814da6c8a4e | .v2ctl\runs\run_20261006-172014_fd4a1c8f.json | C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\.slim\worktrees\golden-source-admission-state-ab\artifacts\phase_p1_parallel_golden_v1\cohort_2026-10-06_22-19-55_9a8cda\manifest.json | 4862.540 | 1675.705 | 2638.248 | 51.954/61.485 | 54.796/63.281 | 4.801 | 4.666 | 2.843 |

## PHASE_STABLE raw adherence and schedule-shape dataset

These are the exact aligned vectors used below. Rows are ordered by unique-dataset ID; `operations` includes every raw CLIP+UNET operation. Thirds are actual native-launch order thirds within each model. `after-QD4` begins at/after the first raw interval point where reconstructed native depth reaches four.

| ID | Original order | Cohort2 order | Block | Cohort membership | Request ID | Overall matches/ops | Overall fraction | CLIP matches/ops | CLIP frac | UNET matches/ops | UNET frac | CLIP first/mid/final frac | UNET first/mid/final frac | CLIP first16 | UNET first16 | CLIP after-QD4 | UNET after-QD4 | CLIP max match/skip streak | UNET max match/skip streak | CLIP transitions | UNET transitions |
|---|---:|---:|---|---|---|---|---:|---|---:|---|---:|---|---|---:|---:|---:|---:|---|---|---:|---:|
| R03 | 3 | - | O1 | original | golden-p1-0-6e46ad378fa0 | 135/304 | 0.4441 | 93/120 | 0.7750 | 42/184 | 0.2283 | 0.4250/0.9000/1.0000 | 0.0968/0.4754/0.1148 | 0.4375 | 0.1250 | 0.7863 | 0.2320 | 57/4 | 3/48 | 23 | 48 |
| R04 | 4 | - | O2 | original | golden-p1-0-5dac4837db40 | 131/304 | 0.4309 | 51/120 | 0.4250 | 80/184 | 0.4348 | 0.3500/0.6250/0.3000 | 0.2581/0.0820/0.9672 | 0.3125 | 0.3750 | 0.4188 | 0.4365 | 10/16 | 59/44 | 48 | 39 |
| R08 | 8 | - | O3 | original | golden-p1-0-8cca1410e757 | 135/304 | 0.4441 | 91/120 | 0.7583 | 44/184 | 0.2391 | 0.8000/0.9750/0.5000 | 0.3226/0.2623/0.1311 | 0.6250 | 0.5000 | 0.7521 | 0.2320 | 59/2 | 2/46 | 29 | 80 |
| R12 | 12 | - | O4 | original | golden-p1-0-0b2fadac4af2 | 149/304 | 0.4901 | 61/120 | 0.5083 | 88/184 | 0.4783 | 0.5500/0.5000/0.4750 | 0.6129/0.3934/0.4262 | 0.6875 | 0.8750 | 0.4957 | 0.4696 | 6/3 | 14/3 | 105 | 132 |
| R13 | 13 | - | O5 | original | golden-p1-0-23cc218345cb | 64/304 | 0.2105 | 30/120 | 0.2500 | 34/184 | 0.1848 | 0.2500/0.2500/0.2500 | 0.1774/0.3770/0.0000 | 0.3125 | 0.0000 | 0.2393 | 0.1878 | 2/8 | 2/66 | 58 | 50 |
| R18 | 18 | - | O6 | original | golden-p1-0-8d991f9b793f | 59/304 | 0.1941 | 48/120 | 0.4000 | 11/184 | 0.0598 | 0.2000/0.5000/0.5000 | 0.1774/0.0000/0.0000 | 0.0000 | 0.4375 | 0.4103 | 0.0442 | 2/18 | 5/144 | 52 | 13 |
| R22 | 22 | 3 | S1 | original+cohort2 (reused) | golden-p1-0-eb68cc401165 | 97/304 | 0.3191 | 5/120 | 0.0417 | 92/184 | 0.5000 | 0.1250/0.0000/0.0000 | 0.5484/0.4918/0.4590 | 0.2500 | 0.6250 | 0.0342 | 0.4917 | 1/102 | 10/6 | 10 | 87 |
| R23 | 23 | 4 | S2 | original+cohort2 (reused) | golden-p1-0-b3dd83455375 | 106/304 | 0.3487 | 61/120 | 0.5083 | 45/184 | 0.2446 | 0.5250/0.5000/0.5000 | 0.2258/0.2623/0.2459 | 1.0000 | 0.1875 | 0.4957 | 0.2486 | 17/16 | 1/6 | 45 | 90 |
| R27 | - | 8 | S3 | cohort2-new | golden-p1-0-d023eec82e6e | 19/304 | 0.0625 | 10/120 | 0.0833 | 9/184 | 0.0489 | 0.0000/0.0000/0.2500 | 0.0323/0.0492/0.0656 | 0.0000 | 0.0625 | 0.0855 | 0.0442 | 2/96 | 1/80 | 10 | 18 |
| R31 | - | 12 | S4 | cohort2-new | golden-p1-0-b49c908f3d52 | 77/304 | 0.2533 | 52/120 | 0.4333 | 25/184 | 0.1359 | 0.3000/0.5000/0.5000 | 0.0484/0.3115/0.0492 | 0.4375 | 0.0000 | 0.4359 | 0.1381 | 2/8 | 1/52 | 62 | 50 |
| R32 | - | 13 | S5 | cohort2-new | golden-p1-0-66a5391d5d89 | 88/304 | 0.2895 | 14/120 | 0.1167 | 74/184 | 0.4022 | 0.1250/0.2250/0.0000 | 0.4032/0.4918/0.3115 | 0.1250 | 0.2500 | 0.1026 | 0.4033 | 2/49 | 2/16 | 26 | 83 |
| R36 | - | 17 | S6 | cohort2-new | golden-p1-0-f65314e3f4d7 | 49/304 | 0.1612 | 12/120 | 0.1000 | 37/184 | 0.2011 | 0.3000/0.0000/0.0000 | 0.2581/0.2459/0.0984 | 0.4375 | 0.2500 | 0.0940 | 0.1989 | 1/92 | 1/28 | 24 | 74 |
| R40 | - | 21 | S7 | cohort2-new | golden-p1-0-0f826dd1b9b6 | 41/304 | 0.1349 | 3/120 | 0.0250 | 38/184 | 0.2065 | 0.0750/0.0000/0.0000 | 0.2258/0.0328/0.3607 | 0.1875 | 0.1875 | 0.0256 | 0.2044 | 1/104 | 2/72 | 6 | 55 |
| R41 | - | 22 | S8 | cohort2-new | golden-p1-0-6c21c8e160d4 | 64/304 | 0.2105 | 19/120 | 0.1583 | 45/184 | 0.2446 | 0.1000/0.0000/0.3750 | 0.2581/0.1311/0.3443 | 0.1875 | 0.0625 | 0.1624 | 0.2486 | 2/60 | 11/44 | 23 | 50 |

## B. Primary Phase-only correlations

Direction is interpreted as performance-consistent when adherence has a negative coefficient for walls/p50/split and a positive coefficient for throughput. Every result is descriptive; no coefficient is treated as proof.

| Context | Outcome | Pearson r | Spearman rho | Direction/strength | Performance-consistent? |
|---|---|---|---|---|---|
| original cohort (8 Phase runs) | source_envelope_wall_ms | n=8; r=0.552 (p=0.156, 95% bootstrap [0.193,0.900], perm p=0.141) | rho=0.563 (p=0.146) | positive/strong | no/mixed |
| original cohort (8 Phase runs) | CLIP_source_wall_ms | n=8; r=0.599 (p=0.117, 95% bootstrap [0.309,0.907], perm p=0.111) | rho=0.587 (p=0.126) | positive/strong | no/mixed |
| original cohort (8 Phase runs) | UNET_source_wall_ms | n=8; r=0.547 (p=0.161, 95% bootstrap [0.196,0.880], perm p=0.15) | rho=0.563 (p=0.146) | positive/strong | no/mixed |
| original cohort (8 Phase runs) | CLIP_native_p50_ms | n=8; r=0.504 (p=0.202, 95% bootstrap [0.079,0.829], perm p=0.201) | rho=0.599 (p=0.117) | positive/strong | no/mixed |
| original cohort (8 Phase runs) | UNET_native_p50_ms | n=8; r=0.408 (p=0.316, 95% bootstrap [-0.330,0.789], perm p=0.302) | rho=0.347 (p=0.399) | positive/moderate | no/mixed |
| original cohort (8 Phase runs) | CLIP_throughput_Gbps | n=8; r=-0.594 (p=0.12, 95% bootstrap [-0.933,-0.290], perm p=0.126) | rho=-0.587 (p=0.126) | negative/strong | no/mixed |
| original cohort (8 Phase runs) | UNET_throughput_Gbps | n=8; r=-0.542 (p=0.165, 95% bootstrap [-0.900,-0.130], perm p=0.165) | rho=-0.563 (p=0.146) | negative/strong | no/mixed |
| original cohort (8 Phase runs) | CLIP_UNET_abs_p50_split_ms | n=8; r=0.497 (p=0.21, 95% bootstrap [-0.166,0.950], perm p=0.218) | rho=0.719 (p=0.0446) | positive/moderate | no/mixed |
| cohort 2 genuinely new (6 Phase runs) | source_envelope_wall_ms | n=6; r=-0.722 (p=0.106, 95% bootstrap [-0.998,0.931], perm p=0.112) | rho=-0.371 (p=0.468) | negative/very strong | yes |
| cohort 2 genuinely new (6 Phase runs) | CLIP_source_wall_ms | n=6; r=-0.620 (p=0.189, 95% bootstrap [-0.988,0.930], perm p=0.185) | rho=-0.314 (p=0.544) | negative/strong | yes |
| cohort 2 genuinely new (6 Phase runs) | UNET_source_wall_ms | n=6; r=-0.713 (p=0.111, 95% bootstrap [-0.999,0.685], perm p=0.0963) | rho=-0.371 (p=0.468) | negative/very strong | yes |
| cohort 2 genuinely new (6 Phase runs) | CLIP_native_p50_ms | n=6; r=-0.566 (p=0.242, 95% bootstrap [-0.975,0.975], perm p=0.224) | rho=-0.314 (p=0.544) | negative/strong | yes |
| cohort 2 genuinely new (6 Phase runs) | UNET_native_p50_ms | n=6; r=-0.713 (p=0.112, 95% bootstrap [-0.992,0.835], perm p=0.11) | rho=-0.314 (p=0.544) | negative/very strong | yes |
| cohort 2 genuinely new (6 Phase runs) | CLIP_throughput_Gbps | n=6; r=0.552 (p=0.256, 95% bootstrap [-0.861,0.991], perm p=0.26) | rho=0.314 (p=0.544) | positive/strong | yes |
| cohort 2 genuinely new (6 Phase runs) | UNET_throughput_Gbps | n=6; r=0.689 (p=0.13, 95% bootstrap [-0.684,0.999], perm p=0.123) | rho=0.371 (p=0.468) | positive/strong | yes |
| cohort 2 genuinely new (6 Phase runs) | CLIP_UNET_abs_p50_split_ms | n=6; r=0.108 (p=0.839, 95% bootstrap [-0.885,0.959], perm p=0.872) | rho=0.029 (p=0.957) | positive/weak | no/mixed |
| all unique Phase runs (14) | source_envelope_wall_ms | n=14; r=0.235 (p=0.419, 95% bootstrap [-0.546,0.705], perm p=0.396) | rho=0.137 (p=0.642) | positive/weak | no/mixed |
| all unique Phase runs (14) | CLIP_source_wall_ms | n=14; r=0.283 (p=0.326, 95% bootstrap [-0.361,0.757], perm p=0.311) | rho=0.229 (p=0.431) | positive/weak | no/mixed |
| all unique Phase runs (14) | UNET_source_wall_ms | n=14; r=0.193 (p=0.51, 95% bootstrap [-0.572,0.672], perm p=0.525) | rho=0.073 (p=0.805) | positive/weak | no/mixed |
| all unique Phase runs (14) | CLIP_native_p50_ms | n=14; r=0.215 (p=0.461, 95% bootstrap [-0.496,0.689], perm p=0.468) | rho=0.170 (p=0.562) | positive/weak | no/mixed |
| all unique Phase runs (14) | UNET_native_p50_ms | n=14; r=0.045 (p=0.878, 95% bootstrap [-0.731,0.606], perm p=0.872) | rho=-0.150 (p=0.609) | positive/negligible | no/mixed |
| all unique Phase runs (14) | CLIP_throughput_Gbps | n=14; r=-0.225 (p=0.439, 95% bootstrap [-0.714,0.382], perm p=0.448) | rho=-0.229 (p=0.431) | negative/weak | no/mixed |
| all unique Phase runs (14) | UNET_throughput_Gbps | n=14; r=-0.080 (p=0.785, 95% bootstrap [-0.596,0.472], perm p=0.778) | rho=-0.073 (p=0.805) | negative/negligible | no/mixed |
| all unique Phase runs (14) | CLIP_UNET_abs_p50_split_ms | n=14; r=0.201 (p=0.49, 95% bootstrap [-0.213,0.712], perm p=0.504) | rho=0.383 (p=0.176) | positive/weak | no/mixed |

### Primary result details and exact vectors

For each context below, `x` is overall Phase turn adherence and each `y_*` array is aligned to the listed IDs. The tables above give coefficients; this appendix gives the exact data vectors used.

**original cohort (8 Phase runs)**; IDs=`R03, R04, R08, R12, R13, R18, R22, R23`
- x_adherence = [0.4441, 0.4309, 0.4441, 0.4901, 0.2105, 0.1941, 0.3191, 0.3487]
- y_source_envelope_wall_ms = [5469.1397, 7070.3028, 6575.1442, 4398.1741, 4338.5553, 3819.6135, 3353.1345, 3284.2990]
- y_CLIP_source_wall_ms = [1975.8973, 2583.9750, 2301.4742, 1792.4996, 1601.2140, 1491.9680, 1280.5867, 1327.4935]
- y_UNET_source_wall_ms = [3002.1272, 4392.3213, 3950.6772, 2491.3245, 2428.7720, 2029.2031, 1973.4765, 1697.0287]
- y_CLIP_native_p50_ms = [53.8759, 82.5234, 75.1221, 55.6811, 50.7883, 46.7228, 38.5138, 35.1729]
- y_UNET_native_p50_ms = [41.2828, 85.2248, 81.1222, 49.3764, 50.8428, 41.0753, 36.7535, 32.8241]
- y_CLIP_throughput_Gbps = [4.0715, 3.1134, 3.4956, 4.4881, 5.0243, 5.3922, 6.2822, 6.0602]
- y_UNET_throughput_Gbps = [4.1004, 2.8026, 3.1159, 4.9411, 5.0683, 6.0663, 6.2376, 7.2537]
- y_CLIP_UNET_abs_p50_split_ms = [12.5931, 2.7014, 6.0001, 6.3047, 0.0544, 5.6475, 1.7603, 2.3488]

**cohort 2 genuinely new (6 Phase runs)**; IDs=`R27, R31, R32, R36, R40, R41`
- x_adherence = [0.0625, 0.2533, 0.2895, 0.1612, 0.1349, 0.2105]
- y_source_envelope_wall_ms = [5990.8101, 4464.8746, 4423.2545, 4889.3303, 4266.8791, 4436.1477]
- y_CLIP_source_wall_ms = [2183.2719, 1681.0693, 1695.1698, 1863.7575, 1589.0875, 1439.0768]
- y_UNET_source_wall_ms = [3487.4335, 2684.5773, 2626.7301, 2897.1081, 2580.9852, 2907.1183]
- y_CLIP_native_p50_ms = [69.4392, 52.1094, 54.1192, 56.5395, 49.0788, 42.3561]
- y_UNET_native_p50_ms = [73.9517, 50.1070, 50.6262, 54.2185, 50.0457, 58.9796]
- y_CLIP_throughput_Gbps = [3.6848, 4.7856, 4.7458, 4.3165, 5.0626, 5.5903]
- y_UNET_throughput_Gbps = [3.5298, 4.5854, 4.6864, 4.2490, 4.7694, 4.2344]
- y_CLIP_UNET_abs_p50_split_ms = [4.5125, 2.0024, 3.4931, 2.3210, 0.9668, 16.6235]

**all unique Phase runs (14)**; IDs=`R03, R04, R08, R12, R13, R18, R22, R23, R27, R31, R32, R36, R40, R41`
- x_adherence = [0.4441, 0.4309, 0.4441, 0.4901, 0.2105, 0.1941, 0.3191, 0.3487, 0.0625, 0.2533, 0.2895, 0.1612, 0.1349, 0.2105]
- y_source_envelope_wall_ms = [5469.1397, 7070.3028, 6575.1442, 4398.1741, 4338.5553, 3819.6135, 3353.1345, 3284.2990, 5990.8101, 4464.8746, 4423.2545, 4889.3303, 4266.8791, 4436.1477]
- y_CLIP_source_wall_ms = [1975.8973, 2583.9750, 2301.4742, 1792.4996, 1601.2140, 1491.9680, 1280.5867, 1327.4935, 2183.2719, 1681.0693, 1695.1698, 1863.7575, 1589.0875, 1439.0768]
- y_UNET_source_wall_ms = [3002.1272, 4392.3213, 3950.6772, 2491.3245, 2428.7720, 2029.2031, 1973.4765, 1697.0287, 3487.4335, 2684.5773, 2626.7301, 2897.1081, 2580.9852, 2907.1183]
- y_CLIP_native_p50_ms = [53.8759, 82.5234, 75.1221, 55.6811, 50.7883, 46.7228, 38.5138, 35.1729, 69.4392, 52.1094, 54.1192, 56.5395, 49.0788, 42.3561]
- y_UNET_native_p50_ms = [41.2828, 85.2248, 81.1222, 49.3764, 50.8428, 41.0753, 36.7535, 32.8241, 73.9517, 50.1070, 50.6262, 54.2185, 50.0457, 58.9796]
- y_CLIP_throughput_Gbps = [4.0715, 3.1134, 3.4956, 4.4881, 5.0243, 5.3922, 6.2822, 6.0602, 3.6848, 4.7856, 4.7458, 4.3165, 5.0626, 5.5903]
- y_UNET_throughput_Gbps = [4.1004, 2.8026, 3.1159, 4.9411, 5.0683, 6.0663, 6.2376, 7.2537, 3.5298, 4.5854, 4.6864, 4.2490, 4.7694, 4.2344]
- y_CLIP_UNET_abs_p50_split_ms = [12.5931, 2.7014, 6.0001, 6.3047, 0.0544, 5.6475, 1.7603, 2.3488, 4.5125, 2.0024, 3.4931, 2.3210, 0.9668, 16.6235]

## C. Model-specific correlations

The x variable is model-local adherence; outcomes are the same model's wall, native p50, or throughput.

| Context | Model | Outcome | Pearson r (p) | Spearman rho (p) | Direction/strength |
|---|---|---|---|---|---|
| original cohort (8 Phase runs) | CLIP | wall | 0.542 (0.165) | 0.563 (0.146) | positive/strong |
| original cohort (8 Phase runs) | CLIP | p50 | 0.426 (0.293) | 0.395 (0.333) | positive/moderate |
| original cohort (8 Phase runs) | CLIP | throughput | -0.617 (0.103) | -0.563 (0.146) | negative/strong |
| original cohort (8 Phase runs) | UNET | wall | 0.185 (0.662) | -0.024 (0.955) | positive/weak |
| original cohort (8 Phase runs) | UNET | p50 | 0.172 (0.683) | -0.071 (0.867) | positive/weak |
| original cohort (8 Phase runs) | UNET | throughput | -0.158 (0.708) | 0.024 (0.955) | negative/weak |
| cohort 2 genuinely new (6 Phase runs) | CLIP | wall | -0.187 (0.723) | -0.314 (0.544) | negative/weak |
| cohort 2 genuinely new (6 Phase runs) | CLIP | p50 | -0.181 (0.732) | -0.314 (0.544) | negative/weak |
| cohort 2 genuinely new (6 Phase runs) | CLIP | throughput | 0.153 (0.772) | 0.314 (0.544) | positive/weak |
| cohort 2 genuinely new (6 Phase runs) | UNET | wall | -0.661 (0.153) | -0.486 (0.329) | negative/strong |
| cohort 2 genuinely new (6 Phase runs) | UNET | p50 | -0.609 (0.2) | -0.257 (0.623) | negative/strong |
| cohort 2 genuinely new (6 Phase runs) | UNET | throughput | 0.649 (0.163) | 0.486 (0.329) | positive/strong |
| all unique Phase runs (14) | CLIP | wall | 0.361 (0.205) | 0.321 (0.263) | positive/moderate |
| all unique Phase runs (14) | CLIP | p50 | 0.266 (0.358) | 0.185 (0.527) | positive/weak |
| all unique Phase runs (14) | CLIP | throughput | -0.355 (0.214) | -0.321 (0.263) | negative/moderate |
| all unique Phase runs (14) | UNET | wall | 0.022 (0.941) | -0.110 (0.708) | positive/negligible |
| all unique Phase runs (14) | UNET | p50 | -0.026 (0.929) | -0.139 (0.637) | negative/negligible |
| all unique Phase runs (14) | UNET | throughput | 0.040 (0.893) | 0.110 (0.708) | positive/negligible |

### First/middle/final-third local checks

Each x is adherence within that model/third; each y is that same model/third native p50.

| Context | Model | Third | Pearson r (p) | Spearman rho (p) | Direction/strength |
|---|---|---|---|---|---|
| original cohort (8 Phase runs) | CLIP | first | 0.374 (0.362) | 0.595 (0.12) | positive/moderate |
| original cohort (8 Phase runs) | CLIP | middle | 0.597 (0.118) | 0.659 (0.0757) | positive/strong |
| original cohort (8 Phase runs) | CLIP | final | 0.126 (0.766) | 0.220 (0.601) | positive/weak |
| original cohort (8 Phase runs) | UNET | first | -0.206 (0.624) | -0.108 (0.799) | negative/weak |
| original cohort (8 Phase runs) | UNET | middle | -0.271 (0.516) | -0.060 (0.888) | negative/weak |
| original cohort (8 Phase runs) | UNET | final | 0.618 (0.103) | 0.180 (0.67) | positive/strong |
| cohort 2 genuinely new (6 Phase runs) | CLIP | first | -0.310 (0.55) | 0.058 (0.913) | negative/moderate |
| cohort 2 genuinely new (6 Phase runs) | CLIP | middle | 0.064 (0.905) | -0.034 (0.949) | positive/negligible |
| cohort 2 genuinely new (6 Phase runs) | CLIP | final | -0.091 (0.864) | -0.273 (0.6) | negative/negligible |
| cohort 2 genuinely new (6 Phase runs) | UNET | first | -0.455 (0.364) | -0.232 (0.658) | negative/moderate |
| cohort 2 genuinely new (6 Phase runs) | UNET | middle | -0.499 (0.314) | -0.314 (0.544) | negative/moderate |
| cohort 2 genuinely new (6 Phase runs) | UNET | final | -0.477 (0.339) | -0.429 (0.397) | negative/moderate |
| all unique Phase runs (14) | CLIP | first | 0.199 (0.494) | 0.421 (0.134) | positive/weak |
| all unique Phase runs (14) | CLIP | middle | 0.434 (0.121) | 0.305 (0.289) | positive/moderate |
| all unique Phase runs (14) | CLIP | final | 0.065 (0.826) | 0.052 (0.861) | positive/negligible |
| all unique Phase runs (14) | UNET | first | -0.263 (0.363) | -0.024 (0.934) | negative/weak |
| all unique Phase runs (14) | UNET | middle | -0.313 (0.276) | -0.286 (0.321) | negative/moderate |
| all unique Phase runs (14) | UNET | final | 0.437 (0.118) | 0.004 (0.988) | positive/moderate |

Exact model/third vectors are reconstructable from the PHASE table above plus the raw per-run p50 values in the unique-run table; the following compact aligned vector lists make the tested values explicit.
**original cohort (8 Phase runs)** IDs=`R03, R04, R08, R12, R13, R18, R22, R23`
- CLIP_first: adherence=[0.4250, 0.3500, 0.8000, 0.5500, 0.2500, 0.2000, 0.1250, 0.5250]; p50_ms=[71.1223, 93.1260, 69.2313, 69.0450, 53.6869, 55.4504, 52.4882, 61.8356]
- CLIP_middle: adherence=[0.9000, 0.6250, 0.9750, 0.5000, 0.2500, 0.5000, 0.0000, 0.5000]; p50_ms=[50.7696, 78.3305, 75.6615, 53.3355, 49.5327, 44.1947, 38.3640, 35.1729]
- CLIP_final: adherence=[1.0000, 0.3000, 0.5000, 0.4750, 0.2500, 0.5000, 0.0000, 0.5000]; p50_ms=[53.3211, 75.0421, 76.3848, 52.0314, 50.6863, 45.4860, 37.8254, 33.4868]
- UNET_first: adherence=[0.0968, 0.2581, 0.3226, 0.6129, 0.1774, 0.1774, 0.5484, 0.2258]; p50_ms=[52.7593, 79.6669, 83.2611, 46.2748, 51.3587, 44.3988, 37.3709, 44.7178]
- UNET_middle: adherence=[0.4754, 0.0820, 0.2623, 0.3934, 0.3770, 0.0000, 0.4918, 0.2623]; p50_ms=[40.6798, 83.9157, 97.7677, 49.2987, 50.3516, 35.3269, 36.2689, 32.1924]
- UNET_final: adherence=[0.1148, 0.9672, 0.1311, 0.4262, 0.0000, 0.0000, 0.4590, 0.2459]; p50_ms=[38.6857, 97.0439, 69.4098, 53.1887, 50.9357, 49.8214, 36.4807, 33.4024]

**cohort 2 genuinely new (6 Phase runs)** IDs=`R27, R31, R32, R36, R40, R41`
- CLIP_first: adherence=[0.0000, 0.3000, 0.1250, 0.3000, 0.0750, 0.1000]; p50_ms=[82.0892, 62.0563, 61.5221, 67.9587, 60.4481, 56.8804]
- CLIP_middle: adherence=[0.0000, 0.5000, 0.2250, 0.0000, 0.0000, 0.0000]; p50_ms=[63.0052, 51.5011, 53.1005, 55.0692, 44.5314, 40.4396]
- CLIP_final: adherence=[0.2500, 0.5000, 0.0000, 0.0000, 0.0000, 0.3750]; p50_ms=[67.0260, 51.7213, 51.8480, 55.5654, 49.4755, 44.2531]
- UNET_first: adherence=[0.0323, 0.0484, 0.4032, 0.2581, 0.2258, 0.2581]; p50_ms=[72.3668, 50.3970, 52.8341, 54.1110, 53.6998, 58.8282]
- UNET_middle: adherence=[0.0492, 0.3115, 0.4918, 0.2459, 0.0328, 0.1311]; p50_ms=[74.7981, 49.8529, 52.2979, 55.9424, 50.8541, 60.0034]
- UNET_final: adherence=[0.0656, 0.0492, 0.3115, 0.0984, 0.3607, 0.3443]; p50_ms=[75.1611, 46.8185, 45.9413, 51.8703, 39.8817, 56.1036]

**all unique Phase runs (14)** IDs=`R03, R04, R08, R12, R13, R18, R22, R23, R27, R31, R32, R36, R40, R41`
- CLIP_first: adherence=[0.4250, 0.3500, 0.8000, 0.5500, 0.2500, 0.2000, 0.1250, 0.5250, 0.0000, 0.3000, 0.1250, 0.3000, 0.0750, 0.1000]; p50_ms=[71.1223, 93.1260, 69.2313, 69.0450, 53.6869, 55.4504, 52.4882, 61.8356, 82.0892, 62.0563, 61.5221, 67.9587, 60.4481, 56.8804]
- CLIP_middle: adherence=[0.9000, 0.6250, 0.9750, 0.5000, 0.2500, 0.5000, 0.0000, 0.5000, 0.0000, 0.5000, 0.2250, 0.0000, 0.0000, 0.0000]; p50_ms=[50.7696, 78.3305, 75.6615, 53.3355, 49.5327, 44.1947, 38.3640, 35.1729, 63.0052, 51.5011, 53.1005, 55.0692, 44.5314, 40.4396]
- CLIP_final: adherence=[1.0000, 0.3000, 0.5000, 0.4750, 0.2500, 0.5000, 0.0000, 0.5000, 0.2500, 0.5000, 0.0000, 0.0000, 0.0000, 0.3750]; p50_ms=[53.3211, 75.0421, 76.3848, 52.0314, 50.6863, 45.4860, 37.8254, 33.4868, 67.0260, 51.7213, 51.8480, 55.5654, 49.4755, 44.2531]
- UNET_first: adherence=[0.0968, 0.2581, 0.3226, 0.6129, 0.1774, 0.1774, 0.5484, 0.2258, 0.0323, 0.0484, 0.4032, 0.2581, 0.2258, 0.2581]; p50_ms=[52.7593, 79.6669, 83.2611, 46.2748, 51.3587, 44.3988, 37.3709, 44.7178, 72.3668, 50.3970, 52.8341, 54.1110, 53.6998, 58.8282]
- UNET_middle: adherence=[0.4754, 0.0820, 0.2623, 0.3934, 0.3770, 0.0000, 0.4918, 0.2623, 0.0492, 0.3115, 0.4918, 0.2459, 0.0328, 0.1311]; p50_ms=[40.6798, 83.9157, 97.7677, 49.2987, 50.3516, 35.3269, 36.2689, 32.1924, 74.7981, 49.8529, 52.2979, 55.9424, 50.8541, 60.0034]
- UNET_final: adherence=[0.1148, 0.9672, 0.1311, 0.4262, 0.0000, 0.0000, 0.4590, 0.2459, 0.0656, 0.0492, 0.3115, 0.0984, 0.3607, 0.3443]; p50_ms=[38.6857, 97.0439, 69.4098, 53.1887, 50.9357, 49.8214, 36.4807, 33.4024, 75.1611, 46.8185, 45.9413, 51.8703, 39.8817, 56.1036]

## D. Within-block normalized correlation

For each Phase run, Phase-baseline is in milliseconds and percent of the same-block baseline. `O#` blocks are the original-only 3-run windows; `S#` blocks are cohort-2 3-run windows. Reused manifests use their S block so they are compared against the actual local triplet that produced their retained evidence.

| ID | Block | Original order | Cohort2 order | Overall adherence | Current baseline ID | Phase-Current envelope ms/% | CLIP wall ms/% | UNET wall ms/% | CLIP p50 ms/% | UNET p50 ms/% | First-block baseline ID | Phase-First envelope ms/% | CLIP wall ms/% | UNET wall ms/% | CLIP p50 ms/% | UNET p50 ms/% |
|---|---|---:|---:|---:|---|---|---|---|---|---|---|---|---|---|---|---|
| R03 | O1 | 3 | - | 0.4441 | R01 | 1332.817/32.22% | 242.531/13.99% | 831.040/38.28% | 6.501/13.72% | -0.145/-0.35% | R02 | -744.439/-11.98% | -357.343/-15.32% | -782.324/-20.67% | -19.841/-26.91% | -34.666/-45.64% |
| R04 | O2 | 4 | - | 0.4309 | R05 | 2287.215/47.82% | 341.011/15.20% | 1948.879/79.76% | 10.880/15.19% | 40.506/90.58% | R06 | 2477.089/53.93% | 851.931/49.19% | 1942.938/79.32% | 28.791/53.58% | 36.329/74.30% |
| R08 | O3 | 8 | - | 0.4441 | R09 | 574.328/9.57% | 51.641/2.30% | 297.358/8.14% | 4.218/5.95% | 13.284/19.58% | R07 | 1983.285/43.19% | 409.986/21.68% | 1348.640/51.83% | 19.976/36.22% | 32.389/66.46% |
| R12 | O4 | 12 | - | 0.4901 | R10 | 598.622/15.76% | 412.657/29.91% | 154.570/6.61% | 12.460/28.83% | 6.183/14.31% | R11 | -2292.849/-34.27% | -1310.560/-42.23% | -997.809/-28.60% | -40.869/-42.33% | -15.227/-23.57% |
| R13 | O5 | 13 | - | 0.2105 | R14 | -2331.469/-34.95% | -746.679/-31.80% | -1526.738/-38.60% | -23.428/-31.57% | -31.745/-38.44% | R15 | -1571.028/-26.58% | -730.262/-31.32% | -1014.393/-29.46% | -20.437/-28.69% | -16.085/-24.03% |
| R18 | O6 | 18 | - | 0.1941 | R16 | -1035.516/-21.33% | -236.754/-13.70% | -588.954/-22.49% | -8.527/-15.43% | -13.479/-24.71% | R17 | 450.871/13.38% | 230.828/18.30% | 9.319/0.46% | 10.828/30.17% | 3.450/9.17% |
| R22 | S1 | 22 | 3 | 0.3191 | R20 | -2075.713/-38.23% | -587.236/-31.44% | -1491.202/-43.04% | -19.234/-33.31% | -31.459/-46.12% | R21 | -3423.716/-50.52% | -840.287/-39.62% | -2371.480/-54.58% | -26.493/-40.75% | -57.196/-60.88% |
| R23 | S2 | 23 | 4 | 0.3487 | R24 | -956.412/-22.55% | -189.154/-12.47% | -912.817/-34.98% | -11.543/-24.71% | -13.580/-29.26% | R25 | -1836.752/-35.87% | -661.939/-33.27% | -1126.400/-39.89% | -17.272/-32.93% | -19.668/-37.47% |
| R27 | S3 | - | 8 | 0.0625 | R28 | 919.987/18.14% | 0.345/0.02% | 893.601/34.45% | -1.132/-1.60% | 20.170/37.50% | R26 | 1594.406/36.27% | 678.987/45.14% | 1155.325/49.54% | 25.015/56.31% | 32.231/77.26% |
| R31 | S4 | - | 12 | 0.2533 | R29 | -2184.017/-32.85% | -1621.493/-49.10% | -563.587/-17.35% | -49.125/-48.53% | -13.697/-21.47% | R30 | -1696.286/-27.53% | -165.279/-8.95% | -1107.242/-29.20% | -2.110/-3.89% | -26.169/-34.31% |
| R32 | S5 | - | 13 | 0.2895 | R33 | -119.236/-2.62% | -108.544/-6.02% | 248.522/10.45% | 9.336/20.85% | 0.694/1.39% | R34 | -381.318/-7.94% | -76.670/-4.33% | -272.496/-9.40% | 2.923/5.71% | -2.724/-5.11% |
| R36 | S6 | - | 17 | 0.1612 | R37 | -697.243/-12.48% | -124.478/-6.26% | -402.818/-12.21% | -5.546/-8.93% | -13.369/-19.78% | R35 | -1214.953/-19.90% | -677.843/-26.67% | -342.832/-10.58% | -24.246/-30.01% | -11.806/-17.88% |
| R40 | S7 | - | 21 | 0.1349 | R38 | -428.062/-9.12% | -107.255/-6.32% | -311.154/-10.76% | -3.982/-7.50% | -4.611/-8.44% | R39 | -1686.729/-28.33% | -785.056/-33.07% | -668.264/-20.57% | -25.880/-34.53% | -17.936/-26.38% |
| R41 | S8 | - | 22 | 0.2105 | R42 | -221.918/-4.76% | -254.887/-15.05% | 84.498/2.99% | -10.207/-19.42% | 9.092/18.23% | R43 | -426.393/-8.77% | -236.628/-14.12% | 268.870/10.19% | -9.598/-18.47% | 4.183/7.63% |

### Correlations against local relative advantages

A negative coefficient means higher adherence is associated with a more negative Phase-baseline delta, i.e. a larger local Phase advantage. Exact x and y vectors are listed after the results.

| Context | Baseline | Delta outcome | Pearson r (p) | Spearman rho (p) | Direction/strength |
|---|---|---|---|---|---|
| original cohort (8 Phase runs) | CURRENT | source_envelope_ms ms | 0.785 (0.0209) | 0.743 (0.0349) | positive/very strong |
| original cohort (8 Phase runs) | CURRENT | CLIP_source_wall_ms ms | 0.835 (0.00986) | 0.850 (0.00747) | positive/very strong |
| original cohort (8 Phase runs) | CURRENT | UNET_source_wall_ms ms | 0.690 (0.0582) | 0.635 (0.0909) | positive/strong |
| original cohort (8 Phase runs) | CURRENT | CLIP_p50_ms ms | 0.837 (0.00949) | 0.778 (0.0229) | positive/very strong |
| original cohort (8 Phase runs) | CURRENT | UNET_p50_ms ms | 0.696 (0.0551) | 0.671 (0.0687) | positive/strong |
| original cohort (8 Phase runs) | FIRST_BLOCK_GATE | source_envelope_ms ms | 0.185 (0.661) | 0.024 (0.955) | positive/weak |
| original cohort (8 Phase runs) | FIRST_BLOCK_GATE | CLIP_source_wall_ms ms | 0.013 (0.975) | -0.048 (0.91) | positive/negligible |
| original cohort (8 Phase runs) | FIRST_BLOCK_GATE | UNET_source_wall_ms ms | 0.285 (0.494) | 0.263 (0.528) | positive/weak |
| original cohort (8 Phase runs) | FIRST_BLOCK_GATE | CLIP_p50_ms ms | -0.037 (0.931) | -0.108 (0.799) | negative/negligible |
| original cohort (8 Phase runs) | FIRST_BLOCK_GATE | UNET_p50_ms ms | 0.193 (0.648) | 0.132 (0.756) | positive/weak |
| cohort 2 genuinely new (6 Phase runs) | CURRENT | source_envelope_ms ms | -0.576 (0.232) | -0.257 (0.623) | negative/strong |
| cohort 2 genuinely new (6 Phase runs) | CURRENT | CLIP_source_wall_ms ms | -0.467 (0.351) | -0.657 (0.156) | negative/moderate |
| cohort 2 genuinely new (6 Phase runs) | CURRENT | UNET_source_wall_ms ms | -0.425 (0.401) | -0.257 (0.623) | negative/moderate |
| cohort 2 genuinely new (6 Phase runs) | CURRENT | CLIP_p50_ms ms | -0.257 (0.623) | -0.143 (0.787) | negative/weak |
| cohort 2 genuinely new (6 Phase runs) | CURRENT | UNET_p50_ms ms | -0.465 (0.353) | -0.371 (0.468) | negative/moderate |
| cohort 2 genuinely new (6 Phase runs) | FIRST_BLOCK_GATE | source_envelope_ms ms | -0.483 (0.332) | -0.200 (0.704) | negative/moderate |
| cohort 2 genuinely new (6 Phase runs) | FIRST_BLOCK_GATE | CLIP_source_wall_ms ms | -0.244 (0.642) | 0.143 (0.787) | negative/weak |
| cohort 2 genuinely new (6 Phase runs) | FIRST_BLOCK_GATE | UNET_source_wall_ms ms | -0.602 (0.206) | -0.314 (0.544) | negative/strong |
| cohort 2 genuinely new (6 Phase runs) | FIRST_BLOCK_GATE | CLIP_p50_ms ms | -0.161 (0.761) | 0.143 (0.787) | negative/weak |
| cohort 2 genuinely new (6 Phase runs) | FIRST_BLOCK_GATE | UNET_p50_ms ms | -0.553 (0.255) | -0.314 (0.544) | negative/strong |
| all unique Phase runs (14) | CURRENT | source_envelope_ms ms | 0.394 (0.163) | 0.355 (0.213) | positive/moderate |
| all unique Phase runs (14) | CURRENT | CLIP_source_wall_ms ms | 0.370 (0.192) | 0.436 (0.119) | positive/moderate |
| all unique Phase runs (14) | CURRENT | UNET_source_wall_ms ms | 0.286 (0.322) | 0.236 (0.417) | positive/weak |
| all unique Phase runs (14) | CURRENT | CLIP_p50_ms ms | 0.384 (0.175) | 0.407 (0.148) | positive/moderate |
| all unique Phase runs (14) | CURRENT | UNET_p50_ms ms | 0.253 (0.382) | 0.170 (0.562) | positive/weak |
| all unique Phase runs (14) | FIRST_BLOCK_GATE | source_envelope_ms ms | 0.022 (0.94) | -0.117 (0.691) | positive/negligible |
| all unique Phase runs (14) | FIRST_BLOCK_GATE | CLIP_source_wall_ms ms | -0.092 (0.754) | -0.075 (0.799) | negative/negligible |
| all unique Phase runs (14) | FIRST_BLOCK_GATE | UNET_source_wall_ms ms | -0.004 (0.989) | -0.139 (0.636) | negative/negligible |
| all unique Phase runs (14) | FIRST_BLOCK_GATE | CLIP_p50_ms ms | -0.094 (0.75) | -0.075 (0.799) | negative/negligible |
| all unique Phase runs (14) | FIRST_BLOCK_GATE | UNET_p50_ms ms | -0.065 (0.825) | -0.117 (0.691) | negative/negligible |

### Exact local correlation vectors
**original cohort (8 Phase runs)** IDs=`R03, R04, R08, R12, R13, R18, R22, R23`
- x_adherence = [0.4441, 0.4309, 0.4441, 0.4901, 0.2105, 0.1941, 0.3191, 0.3487]
- y_CURRENT_source_envelope_ms = [1332.8167, 2287.2150, 574.3276, 598.6221, -2331.4695, -1035.5162, -2075.7134, -956.4124]
- y_CURRENT_CLIP_source_wall_ms = [242.5309, 341.0106, 51.6405, 412.6567, -746.6793, -236.7544, -587.2360, -189.1537]
- y_CURRENT_UNET_source_wall_ms = [831.0399, 1948.8788, 297.3575, 154.5704, -1526.7383, -588.9543, -1491.2022, -912.8174]
- y_CURRENT_CLIP_p50_ms = [6.5014, 10.8800, 4.2184, 12.4597, -23.4283, -8.5268, -19.2341, -11.5433]
- y_CURRENT_UNET_p50_ms = [-0.1449, 40.5062, 13.2839, 6.1826, -31.7447, -13.4791, -31.4592, -13.5799]
- y_FIRST_BLOCK_GATE_source_envelope_ms = [-744.4385, 2477.0894, 1983.2848, -2292.8494, -1571.0283, 450.8707, -3423.7157, -1836.7519]
- y_FIRST_BLOCK_GATE_CLIP_source_wall_ms = [-357.3427, 851.9306, 409.9865, -1310.5596, -730.2617, 230.8282, -840.2867, -661.9394]
- y_FIRST_BLOCK_GATE_UNET_source_wall_ms = [-782.3237, 1942.9377, 1348.6397, -997.8086, -1014.3930, 9.3193, -2371.4802, -1126.3999]
- y_FIRST_BLOCK_GATE_CLIP_p50_ms = [-19.8407, 28.7907, 19.9757, -40.8687, -20.4373, 10.8285, -26.4928, -17.2715]
- y_FIRST_BLOCK_GATE_UNET_p50_ms = [-34.6663, 36.3294, 32.3894, -15.2273, -16.0854, 3.4497, -57.1955, -19.6681]

**cohort 2 genuinely new (6 Phase runs)** IDs=`R27, R31, R32, R36, R40, R41`
- x_adherence = [0.0625, 0.2533, 0.2895, 0.1612, 0.1349, 0.2105]
- y_CURRENT_source_envelope_ms = [919.9871, -2184.0169, -119.2356, -697.2429, -428.0616, -221.9175]
- y_CURRENT_CLIP_source_wall_ms = [0.3446, -1621.4931, -108.5437, -124.4779, -107.2546, -254.8865]
- y_CURRENT_UNET_source_wall_ms = [893.6006, -563.5866, 248.5220, -402.8178, -311.1543, 84.4982]
- y_CURRENT_CLIP_p50_ms = [-1.1322, -49.1254, 9.3363, -5.5464, -3.9822, -10.2068]
- y_CURRENT_UNET_p50_ms = [20.1701, -13.6965, 0.6936, -13.3687, -4.6111, 9.0923]
- y_FIRST_BLOCK_GATE_source_envelope_ms = [1594.4060, -1696.2858, -381.3179, -1214.9534, -1686.7294, -426.3928]
- y_FIRST_BLOCK_GATE_CLIP_source_wall_ms = [678.9867, -165.2794, -76.6701, -677.8430, -785.0560, -236.6281]
- y_FIRST_BLOCK_GATE_UNET_source_wall_ms = [1155.3252, -1107.2417, -272.4960, -342.8317, -668.2639, 268.8703]
- y_FIRST_BLOCK_GATE_CLIP_p50_ms = [25.0154, -2.1098, 2.9228, -24.2461, -25.8804, -9.5975]
- y_FIRST_BLOCK_GATE_UNET_p50_ms = [32.2315, -26.1687, -2.7237, -11.8058, -17.9364, 4.1832]

**all unique Phase runs (14)** IDs=`R03, R04, R08, R12, R13, R18, R22, R23, R27, R31, R32, R36, R40, R41`
- x_adherence = [0.4441, 0.4309, 0.4441, 0.4901, 0.2105, 0.1941, 0.3191, 0.3487, 0.0625, 0.2533, 0.2895, 0.1612, 0.1349, 0.2105]
- y_CURRENT_source_envelope_ms = [1332.8167, 2287.2150, 574.3276, 598.6221, -2331.4695, -1035.5162, -2075.7134, -956.4124, 919.9871, -2184.0169, -119.2356, -697.2429, -428.0616, -221.9175]
- y_CURRENT_CLIP_source_wall_ms = [242.5309, 341.0106, 51.6405, 412.6567, -746.6793, -236.7544, -587.2360, -189.1537, 0.3446, -1621.4931, -108.5437, -124.4779, -107.2546, -254.8865]
- y_CURRENT_UNET_source_wall_ms = [831.0399, 1948.8788, 297.3575, 154.5704, -1526.7383, -588.9543, -1491.2022, -912.8174, 893.6006, -563.5866, 248.5220, -402.8178, -311.1543, 84.4982]
- y_CURRENT_CLIP_p50_ms = [6.5014, 10.8800, 4.2184, 12.4597, -23.4283, -8.5268, -19.2341, -11.5433, -1.1322, -49.1254, 9.3363, -5.5464, -3.9822, -10.2068]
- y_CURRENT_UNET_p50_ms = [-0.1449, 40.5062, 13.2839, 6.1826, -31.7447, -13.4791, -31.4592, -13.5799, 20.1701, -13.6965, 0.6936, -13.3687, -4.6111, 9.0923]
- y_FIRST_BLOCK_GATE_source_envelope_ms = [-744.4385, 2477.0894, 1983.2848, -2292.8494, -1571.0283, 450.8707, -3423.7157, -1836.7519, 1594.4060, -1696.2858, -381.3179, -1214.9534, -1686.7294, -426.3928]
- y_FIRST_BLOCK_GATE_CLIP_source_wall_ms = [-357.3427, 851.9306, 409.9865, -1310.5596, -730.2617, 230.8282, -840.2867, -661.9394, 678.9867, -165.2794, -76.6701, -677.8430, -785.0560, -236.6281]
- y_FIRST_BLOCK_GATE_UNET_source_wall_ms = [-782.3237, 1942.9377, 1348.6397, -997.8086, -1014.3930, 9.3193, -2371.4802, -1126.3999, 1155.3252, -1107.2417, -272.4960, -342.8317, -668.2639, 268.8703]
- y_FIRST_BLOCK_GATE_CLIP_p50_ms = [-19.8407, 28.7907, 19.9757, -40.8687, -20.4373, 10.8285, -26.4928, -17.2715, 25.0154, -2.1098, 2.9228, -24.2461, -25.8804, -9.5975]
- y_FIRST_BLOCK_GATE_UNET_p50_ms = [-34.6663, 36.3294, 32.3894, -15.2273, -16.0854, 3.4497, -57.1955, -19.6681, 32.2315, -26.1687, -2.7237, -11.8058, -17.9364, 4.1832]

## Uncertainty details for model-specific, third-specific, and local correlations

The primary table above already reports Pearson bootstrap intervals and permutation p-values. This compact companion reports the same uncertainty fields for every model-specific, same-third, and within-block correlation; vectors are the exact lists immediately above each result section.

| Context | Tested pair | n | Pearson r (p) | Pearson 95% bootstrap CI | Spearman rho (p) | Permutation p |
|---|---|---:|---|---|---|---:|
| original cohort (8 Phase runs) | third CLIP_final | 8 | 0.126 (0.766) | [-0.577, 0.715] | 0.220 (0.601) | 0.77 |
| original cohort (8 Phase runs) | third CLIP_first | 8 | 0.374 (0.362) | [-0.408, 0.962] | 0.595 (0.12) | 0.366 |
| original cohort (8 Phase runs) | third CLIP_middle | 8 | 0.597 (0.118) | [0.134, 0.907] | 0.659 (0.0757) | 0.109 |
| original cohort (8 Phase runs) | third UNET_final | 8 | 0.618 (0.103) | [-0.752, 0.937] | 0.180 (0.67) | 0.109 |
| original cohort (8 Phase runs) | third UNET_first | 8 | -0.206 (0.624) | [-0.819, 0.836] | -0.108 (0.799) | 0.7 |
| original cohort (8 Phase runs) | third UNET_middle | 8 | -0.271 (0.516) | [-0.998, 0.505] | -0.060 (0.888) | 0.529 |
| original cohort (8 Phase runs) | local CURRENT_CLIP_p50_ms | 8 | 0.837 (0.00949) | [0.573, 0.991] | 0.778 (0.0229) | 0.014 |
| original cohort (8 Phase runs) | local CURRENT_CLIP_source_wall_ms | 8 | 0.835 (0.00986) | [0.584, 0.988] | 0.850 (0.00747) | 0.0117 |
| original cohort (8 Phase runs) | local CURRENT_UNET_p50_ms | 8 | 0.696 (0.0552) | [0.462, 0.946] | 0.671 (0.0687) | 0.057 |
| original cohort (8 Phase runs) | local CURRENT_UNET_source_wall_ms | 8 | 0.690 (0.0582) | [0.430, 0.932] | 0.635 (0.0909) | 0.0556 |
| original cohort (8 Phase runs) | local CURRENT_source_envelope_ms | 8 | 0.785 (0.021) | [0.557, 0.947] | 0.743 (0.0349) | 0.0273 |
| original cohort (8 Phase runs) | local FIRST_BLOCK_GATE_CLIP_p50_ms | 8 | -0.037 (0.931) | [-0.847, 0.755] | -0.108 (0.799) | 0.917 |
| original cohort (8 Phase runs) | local FIRST_BLOCK_GATE_CLIP_source_wall_ms | 8 | 0.013 (0.975) | [-0.794, 0.807] | -0.048 (0.91) | 0.976 |
| original cohort (8 Phase runs) | local FIRST_BLOCK_GATE_UNET_p50_ms | 8 | 0.193 (0.648) | [-0.645, 0.746] | 0.132 (0.756) | 0.657 |
| original cohort (8 Phase runs) | local FIRST_BLOCK_GATE_UNET_source_wall_ms | 8 | 0.285 (0.494) | [-0.424, 0.780] | 0.263 (0.528) | 0.506 |
| original cohort (8 Phase runs) | local FIRST_BLOCK_GATE_source_envelope_ms | 8 | 0.185 (0.661) | [-0.536, 0.810] | 0.024 (0.955) | 0.65 |
| cohort 2 genuinely new (6 Phase runs) | third CLIP_final | 6 | -0.091 (0.864) | [-0.947, 0.969] | -0.273 (0.6) | 0.887 |
| cohort 2 genuinely new (6 Phase runs) | third CLIP_first | 6 | -0.310 (0.55) | [-0.967, 0.951] | 0.058 (0.913) | 0.627 |
| cohort 2 genuinely new (6 Phase runs) | third CLIP_middle | 6 | 0.064 (0.905) | [-0.919, 0.932] | -0.034 (0.949) | 0.966 |
| cohort 2 genuinely new (6 Phase runs) | third UNET_final | 6 | -0.477 (0.339) | [-1.000, 0.592] | -0.429 (0.397) | 0.378 |
| cohort 2 genuinely new (6 Phase runs) | third UNET_first | 6 | -0.455 (0.364) | [-0.984, 0.899] | -0.232 (0.658) | 0.396 |
| cohort 2 genuinely new (6 Phase runs) | third UNET_middle | 6 | -0.499 (0.314) | [-1.000, 0.482] | -0.314 (0.544) | 0.332 |
| cohort 2 genuinely new (6 Phase runs) | local CURRENT_CLIP_p50_ms | 6 | -0.257 (0.623) | [-0.996, 0.867] | -0.143 (0.787) | 0.647 |
| cohort 2 genuinely new (6 Phase runs) | local CURRENT_CLIP_source_wall_ms | 6 | -0.467 (0.351) | [-0.996, 0.249] | -0.657 (0.156) | 0.356 |
| cohort 2 genuinely new (6 Phase runs) | local CURRENT_UNET_p50_ms | 6 | -0.465 (0.353) | [-0.996, 0.704] | -0.371 (0.468) | 0.366 |
| cohort 2 genuinely new (6 Phase runs) | local CURRENT_UNET_source_wall_ms | 6 | -0.425 (0.401) | [-0.979, 0.949] | -0.257 (0.623) | 0.399 |
| cohort 2 genuinely new (6 Phase runs) | local CURRENT_source_envelope_ms | 6 | -0.576 (0.232) | [-0.999, 0.966] | -0.257 (0.623) | 0.213 |
| cohort 2 genuinely new (6 Phase runs) | local FIRST_BLOCK_GATE_CLIP_p50_ms | 6 | -0.161 (0.761) | [-0.933, 0.998] | 0.143 (0.787) | 0.78 |
| cohort 2 genuinely new (6 Phase runs) | local FIRST_BLOCK_GATE_CLIP_source_wall_ms | 6 | -0.244 (0.642) | [-0.961, 1.000] | 0.143 (0.787) | 0.649 |
| cohort 2 genuinely new (6 Phase runs) | local FIRST_BLOCK_GATE_UNET_p50_ms | 6 | -0.553 (0.255) | [-0.972, 0.968] | -0.314 (0.544) | 0.256 |
| cohort 2 genuinely new (6 Phase runs) | local FIRST_BLOCK_GATE_UNET_source_wall_ms | 6 | -0.602 (0.206) | [-0.987, 0.643] | -0.314 (0.544) | 0.21 |
| cohort 2 genuinely new (6 Phase runs) | local FIRST_BLOCK_GATE_source_envelope_ms | 6 | -0.483 (0.332) | [-0.962, 0.989] | -0.200 (0.704) | 0.353 |
| all unique Phase runs (14) | third CLIP_final | 14 | 0.065 (0.826) | [-0.326, 0.454] | 0.052 (0.861) | 0.83 |
| all unique Phase runs (14) | third CLIP_first | 14 | 0.199 (0.494) | [-0.239, 0.765] | 0.421 (0.134) | 0.48 |
| all unique Phase runs (14) | third CLIP_middle | 14 | 0.434 (0.121) | [-0.212, 0.785] | 0.305 (0.289) | 0.119 |
| all unique Phase runs (14) | third UNET_final | 14 | 0.437 (0.118) | [-0.592, 0.835] | 0.004 (0.988) | 0.118 |
| all unique Phase runs (14) | third UNET_first | 14 | -0.263 (0.363) | [-0.683, 0.373] | -0.024 (0.934) | 0.376 |
| all unique Phase runs (14) | third UNET_middle | 14 | -0.313 (0.276) | [-0.780, 0.146] | -0.286 (0.321) | 0.282 |
| all unique Phase runs (14) | local CURRENT_CLIP_p50_ms | 14 | 0.384 (0.175) | [-0.034, 0.755] | 0.407 (0.148) | 0.171 |
| all unique Phase runs (14) | local CURRENT_CLIP_source_wall_ms | 14 | 0.370 (0.192) | [-0.077, 0.798] | 0.436 (0.119) | 0.202 |
| all unique Phase runs (14) | local CURRENT_UNET_p50_ms | 14 | 0.253 (0.382) | [-0.355, 0.692] | 0.170 (0.562) | 0.39 |
| all unique Phase runs (14) | local CURRENT_UNET_source_wall_ms | 14 | 0.286 (0.322) | [-0.307, 0.707] | 0.236 (0.417) | 0.316 |
| all unique Phase runs (14) | local CURRENT_source_envelope_ms | 14 | 0.394 (0.163) | [-0.211, 0.773] | 0.355 (0.213) | 0.172 |
| all unique Phase runs (14) | local FIRST_BLOCK_GATE_CLIP_p50_ms | 14 | -0.094 (0.75) | [-0.704, 0.636] | -0.075 (0.799) | 0.756 |
| all unique Phase runs (14) | local FIRST_BLOCK_GATE_CLIP_source_wall_ms | 14 | -0.092 (0.754) | [-0.722, 0.646] | -0.075 (0.799) | 0.756 |
| all unique Phase runs (14) | local FIRST_BLOCK_GATE_UNET_p50_ms | 14 | -0.065 (0.825) | [-0.702, 0.536] | -0.117 (0.691) | 0.833 |
| all unique Phase runs (14) | local FIRST_BLOCK_GATE_UNET_source_wall_ms | 14 | -0.004 (0.988) | [-0.691, 0.518] | -0.139 (0.636) | 0.989 |
| all unique Phase runs (14) | local FIRST_BLOCK_GATE_source_envelope_ms | 14 | 0.022 (0.94) | [-0.654, 0.624] | -0.117 (0.691) | 0.937 |

## F. Secondary schedule-shape metrics

These are secondary descriptors, not replacements for overall adherence. Streaks/transitions are computed over scheduled raw operations in actual launch order; first16 is the first 16 model operations; after-QD4 uses operations at/after the first reconstructed QD4 point.

| ID | Model | Longest match streak | Longest skip streak | Match-skip transitions | First16 adherence | After-QD4 adherence |
|---|---|---:|---:|---:|---:|---:|
| R03 | CLIP | 57 | 4 | 23 | 0.4375 | 0.7863 |
| R03 | UNET | 3 | 48 | 48 | 0.1250 | 0.2320 |
| R04 | CLIP | 10 | 16 | 48 | 0.3125 | 0.4188 |
| R04 | UNET | 59 | 44 | 39 | 0.3750 | 0.4365 |
| R08 | CLIP | 59 | 2 | 29 | 0.6250 | 0.7521 |
| R08 | UNET | 2 | 46 | 80 | 0.5000 | 0.2320 |
| R12 | CLIP | 6 | 3 | 105 | 0.6875 | 0.4957 |
| R12 | UNET | 14 | 3 | 132 | 0.8750 | 0.4696 |
| R13 | CLIP | 2 | 8 | 58 | 0.3125 | 0.2393 |
| R13 | UNET | 2 | 66 | 50 | 0.0000 | 0.1878 |
| R18 | CLIP | 2 | 18 | 52 | 0.0000 | 0.4103 |
| R18 | UNET | 5 | 144 | 13 | 0.4375 | 0.0442 |
| R22 | CLIP | 1 | 102 | 10 | 0.2500 | 0.0342 |
| R22 | UNET | 10 | 6 | 87 | 0.6250 | 0.4917 |
| R23 | CLIP | 17 | 16 | 45 | 1.0000 | 0.4957 |
| R23 | UNET | 1 | 6 | 90 | 0.1875 | 0.2486 |
| R27 | CLIP | 2 | 96 | 10 | 0.0000 | 0.0855 |
| R27 | UNET | 1 | 80 | 18 | 0.0625 | 0.0442 |
| R31 | CLIP | 2 | 8 | 62 | 0.4375 | 0.4359 |
| R31 | UNET | 1 | 52 | 50 | 0.0000 | 0.1381 |
| R32 | CLIP | 2 | 49 | 26 | 0.1250 | 0.1026 |
| R32 | UNET | 2 | 16 | 83 | 0.2500 | 0.4033 |
| R36 | CLIP | 1 | 92 | 24 | 0.4375 | 0.0940 |
| R36 | UNET | 1 | 28 | 74 | 0.2500 | 0.1989 |
| R40 | CLIP | 1 | 104 | 6 | 0.1875 | 0.0256 |
| R40 | UNET | 2 | 72 | 55 | 0.1875 | 0.2044 |
| R41 | CLIP | 2 | 60 | 23 | 0.1875 | 0.1624 |
| R41 | UNET | 11 | 44 | 50 | 0.0625 | 0.2486 |

## Evidence limitations

- n is 14 pooled unique Phase runs, 8 in the original report cohort, and 6 genuinely new Phase runs in cohort 2. This is too small for causal or proof-level claims; bootstrap intervals are correspondingly wide.
- The original cohort's final five records are the first five records of cohort 2 and are retained once in the union. They remain members of the original cohort for the required cohort-specific view, but are excluded from the 'genuinely new cohort 2' view.
- Provider labels vary inside the pinned `us-central` pool. This audit records provider but does not attribute effects to provider.
- The earlier arm-level 'Reader coherence, native concurrency, spacing, and admission wait' aggregate is suspected to repeat values across arms; it was intentionally not used. All adherence and performance quantities here come from raw per-operation rows.
- No optimization recommendation is made. This is evidence collection and interpretation only.

## Direction replication check

| Outcome | Original cohort Pearson direction | Cohort2-new Pearson direction | Pooled Pearson direction | Direction replicates? |
|---|---|---|---|---|
| source_envelope_wall_ms | positive | negative | positive | no |
| CLIP_source_wall_ms | positive | negative | positive | no |
| UNET_source_wall_ms | positive | negative | positive | no |
| CLIP_native_p50_ms | positive | negative | positive | no |
| UNET_native_p50_ms | positive | negative | positive | no |
| CLIP_throughput_Gbps | negative | positive | negative | no |
| UNET_throughput_Gbps | negative | positive | negative | no |
| CLIP_UNET_abs_p50_split_ms | positive | positive | positive | yes |

## Evidence-bounded conclusion

**TURN ADHERENCE HAS NO CLEAR RELATIONSHIP WITH PERFORMANCE**

The pooled coefficients are descriptive and do not establish a reliable relationship: the signs and strengths vary by outcome and by cohort, with important relationships reversing between the original and genuinely new cohort-2 Phase runs. Model-local and within-third checks do not supply a stable cross-cohort direction, and the small samples/outliers produce wide uncertainty. The data therefore do not support calling stronger adherence consistently better or worse.
