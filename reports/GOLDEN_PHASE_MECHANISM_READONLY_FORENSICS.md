# Golden PHASE_STABLE mechanism forensic audit (read-only)

## 1. Executive conclusion

This audit recomputes the unique source-admission evidence from invocation-bound artifacts. It does not modify runtime source/configuration, deploy, run Modal jobs, or rerun benchmarks.

The defensible conclusion is not that nominal schedule adherence explains the PHASE_STABLE result. Immediate same-reader launch repeats are already absent in all arms, and PHASE does not lower the measured completion→next-launch coupling; those simple explanations are not supported. The strongest observed discriminator is the above-floor launch waveform: PHASE has lower gap p90 and fewer >40 ms gaps, and those shape metrics track local Phase advantage. Static code identifies PHASE's centralized ready-reader arbitration/condition-wakeup path as the only changed mechanism capable of producing that waveform, but existing telemetry cannot prove the exact wake winner or GIL/OS interaction. The remaining conclusion is therefore: **arbitration-induced waveform shaping is plausible and better supported than nominal turn adherence, while the exact arbitration sub-mechanism remains unresolved.**

- Unique valid counted runs: **43**; raw source operations recovered: **13072** ({'CLIP': 5160, 'UNET': 7912}).
- Arm counts: `{'CURRENT': 14, 'FIRST_BLOCK_GATE': 15, 'PHASE_STABLE': 14}`; PHASE_STABLE unique count: **14**.
- Current vs Phase source-envelope medians: `4819.109` ms vs `4429.701` ms; this is descriptive and not a replacement for local-block contrasts.
- The 4 ms lower bound is respected in the selected raw rows; above that floor, the key candidate signature is distribution shape (p90, >40 ms drought/burst incidence, and rolling span), not a nominal p50 alone.
- PHASE adherence varies materially across runs and cohorts; the adherence/performance relationship is not stable enough to serve as the mechanism by itself.
- PHASE CLIP/UNET gap-p90 medians are 26.5/26.0 ms versus CURRENT 31.4/29.0 ms, and >40 ms fractions are 1.7%/1.4% versus 3.4%/1.9%. Local Phase−CURRENT envelope deltas track gap p90 and >40 ms fraction strongly (n=14; Section 9).

## 2. Authoritative unique-run inventory

### Selection and deduplication

There were `51` artifact directories. The selected universe is the raw-valid, true-cold, `us-central`, three-arm experiment interval: 19 first-cohort-only artifacts followed by the 24 artifacts in the later report. Pre-pin attempts, out-of-region attempts, and invalid attempts remain identified in the machine-readable inventory but are not counted.

Exact reused identities verified from the raw attempt manifests: `5`. They are counted once. The union is 43 runs with expected arm counts `{'CURRENT': 14, 'FIRST_BLOCK_GATE': 15, 'PHASE_STABLE': 14}`. Distinct-run raw operation-vector duplicate groups: `0`.

| unique | membership | original order | cohort-2 order | block/slot | arm | provider | region | request ID | source envelope ms | CLIP wall/p50 | UNET wall/p50 | CLIP/UNET throughput GB/s | effective QD CLIP/UNET | QD4+ CLIP/UNET | max depth CLIP/UNET | raw ops |
|---|---|---:|---:|---|---|---|---|---|---:|---|---|---|---|---|---|---:|
| R01 | cohort1_only | 1 | — | O1/1 | CURRENT | CLOUD_PROVIDER_AZURE | us-central | `golden-p1-0-0f31449ad9c4` | 4136.323 | 1733.366/47.374 | 2171.087/41.428 | 4.641/5.670 | 3.907/3.668 | 3.922/3.898 | 4/4 | 304 |
| R02 | cohort1_only | 2 | — | O1/2 | FIRST_BLOCK_GATE | CLOUD_PROVIDER_UNSPECIFIED | us-central | `golden-p1-0-d2f0dbc261b0` | 6213.578 | 2333.240/73.717 | 3784.451/75.949 | 3.448/3.253 | 3.817/3.761 | 3.936/3.944 | 4/4 | 304 |
| R03 | cohort1_only | 3 | — | O1/3 | PHASE_STABLE | CLOUD_PROVIDER_UNSPECIFIED | us-central | `golden-p1-0-6e46ad378fa0` | 5469.140 | 1975.897/53.876 | 3002.127/41.283 | 4.072/4.100 | 3.920/3.956 | 3.934/3.964 | 4/4 | 304 |
| R04 | cohort1_only | 4 | — | O2/1 | PHASE_STABLE | CLOUD_PROVIDER_UNSPECIFIED | us-central | `golden-p1-0-5dac4837db40` | 7070.303 | 2583.975/82.523 | 4392.321/85.225 | 3.113/2.803 | 3.921/3.820 | 3.931/3.944 | 4/4 | 304 |
| R05 | cohort1_only | 5 | — | O2/2 | CURRENT | CLOUD_PROVIDER_UNSPECIFIED | us-central | `golden-p1-0-0b10c4ffa755` | 4783.088 | 2242.964/71.643 | 2443.443/44.719 | 3.587/5.038 | 3.932/3.620 | 3.943/3.947 | 4/4 | 304 |
| R06 | cohort1_only | 6 | — | O2/3 | FIRST_BLOCK_GATE | CLOUD_PROVIDER_AZURE | us-central | `golden-p1-0-db2b9e08ddea` | 4593.213 | 1732.044/53.733 | 2449.384/48.895 | 4.645/5.026 | 3.754/3.795 | 3.888/3.845 | 4/4 | 304 |
| R07 | cohort1_only | 7 | — | O3/1 | FIRST_BLOCK_GATE | CLOUD_PROVIDER_UNSPECIFIED | us-central | `golden-p1-0-dd90cfdd9366` | 4591.859 | 1891.488/55.146 | 2602.037/48.733 | 4.253/4.731 | 3.786/3.579 | 3.910/3.900 | 4/4 | 304 |
| R08 | cohort1_only | 8 | — | O3/2 | PHASE_STABLE | CLOUD_PROVIDER_UNSPECIFIED | us-central | `golden-p1-0-8cca1410e757` | 6575.144 | 2301.474/75.122 | 3950.677/81.122 | 3.496/3.116 | 3.917/3.954 | 3.929/3.961 | 4/4 | 304 |
| R09 | cohort1_only | 9 | — | O3/3 | CURRENT | CLOUD_PROVIDER_UNSPECIFIED | us-central | `golden-p1-0-2a47fc19ecae` | 6000.817 | 2249.834/70.904 | 3653.320/67.838 | 3.576/3.369 | 3.908/3.795 | 3.919/3.945 | 4/4 | 304 |
| R10 | cohort1_only | 10 | — | O4/1 | CURRENT | CLOUD_PROVIDER_UNSPECIFIED | us-central | `golden-p1-0-592d69add4b8` | 3799.552 | 1379.843/43.221 | 2336.754/43.194 | 5.830/5.268 | 3.880/3.608 | 3.898/3.917 | 4/4 | 304 |
| R11 | cohort1_only | 11 | — | O4/2 | FIRST_BLOCK_GATE | CLOUD_PROVIDER_UNSPECIFIED | us-central | `golden-p1-0-61611085385d` | 6691.024 | 3103.059/96.550 | 3489.133/64.604 | 2.593/3.528 | 3.835/3.746 | 3.948/3.969 | 4/4 | 304 |
| R12 | cohort1_only | 12 | — | O4/3 | PHASE_STABLE | CLOUD_PROVIDER_AZURE | us-central | `golden-p1-0-0b2fadac4af2` | 4398.174 | 1792.500/55.681 | 2491.324/49.376 | 4.488/4.941 | 3.902/3.757 | 3.915/3.916 | 4/4 | 304 |
| R13 | cohort1_only | 13 | — | O5/1 | PHASE_STABLE | CLOUD_PROVIDER_UNSPECIFIED | us-central | `golden-p1-0-23cc218345cb` | 4338.555 | 1601.214/50.788 | 2428.772/50.843 | 5.024/5.068 | 3.933/3.942 | 3.949/3.953 | 4/4 | 304 |
| R14 | cohort1_only | 14 | — | O5/2 | CURRENT | CLOUD_PROVIDER_UNSPECIFIED | us-central | `golden-p1-0-c0ab68d4e905` | 6670.025 | 2347.893/74.217 | 3955.510/82.587 | 3.426/3.112 | 3.923/3.950 | 3.933/3.957 | 4/4 | 304 |
| R15 | cohort1_only | 15 | — | O5/3 | FIRST_BLOCK_GATE | CLOUD_PROVIDER_UNSPECIFIED | us-central | `golden-p1-0-2f4b006d183c` | 5909.584 | 2331.476/71.226 | 3443.165/66.928 | 3.451/3.575 | 3.826/3.708 | 3.951/3.944 | 4/4 | 304 |
| R16 | cohort1_only | 16 | — | O6/1 | CURRENT | CLOUD_PROVIDER_UNSPECIFIED | us-central | `golden-p1-0-711f601afebd` | 4855.130 | 1728.722/55.250 | 2618.157/54.554 | 4.654/4.702 | 3.855/3.874 | 3.870/3.884 | 4/4 | 304 |
| R17 | cohort1_only | 17 | — | O6/2 | FIRST_BLOCK_GATE | CLOUD_PROVIDER_UNSPECIFIED | us-central | `golden-p1-0-8ce03baab5d2` | 3368.743 | 1261.140/35.894 | 2019.884/37.626 | 6.379/6.094 | 3.714/3.673 | 3.880/3.936 | 4/4 | 304 |
| R18 | cohort1_only | 18 | — | O6/3 | PHASE_STABLE | CLOUD_PROVIDER_AZURE | us-central | `golden-p1-0-8d991f9b793f` | 3819.614 | 1491.968/46.723 | 2029.203/41.075 | 5.392/6.066 | 3.877/3.894 | 3.895/3.907 | 4/4 | 304 |
| R19 | cohort1_only | 19 | — | O7/1 | FIRST_BLOCK_GATE | CLOUD_PROVIDER_UNSPECIFIED | us-central | `golden-p1-0-42a8cdcba25d` | 4448.669 | 1583.774/47.593 | 2514.984/52.758 | 5.080/4.895 | 3.774/3.907 | 3.923/3.965 | 4/4 | 304 |
| R20 | reused_in_second_report | 20 | 1 | S1/1 | CURRENT | CLOUD_PROVIDER_UNSPECIFIED | us-central | `golden-p1-0-68c4691254a1` | 5428.848 | 1867.823/57.748 | 3464.679/68.213 | 4.307/3.553 | 3.872/3.747 | 3.886/3.947 | 4/4 | 304 |
| R21 | reused_in_second_report | 21 | 2 | S1/2 | FIRST_BLOCK_GATE | CLOUD_PROVIDER_UNSPECIFIED | us-central | `golden-p1-0-974799d1ce00` | 6776.850 | 2120.873/65.007 | 4344.957/93.949 | 3.793/2.833 | 3.811/3.917 | 3.905/3.954 | 4/4 | 304 |
| R22 | reused_in_second_report | 22 | 3 | S1/3 | PHASE_STABLE | CLOUD_PROVIDER_UNSPECIFIED | us-central | `golden-p1-0-eb68cc401165` | 3353.135 | 1280.587/38.514 | 1973.476/36.754 | 6.282/6.238 | 3.892/3.656 | 3.912/3.958 | 4/4 | 304 |
| R23 | reused_in_second_report | 23 | 4 | S2/1 | PHASE_STABLE | CLOUD_PROVIDER_AZURE | us-central | `golden-p1-0-b3dd83455375` | 3284.299 | 1327.494/35.173 | 1697.029/32.824 | 6.060/7.254 | 3.895/3.890 | 3.915/3.905 | 4/4 | 304 |
| R24 | reused_in_second_report | 24 | 5 | S2/2 | CURRENT | CLOUD_PROVIDER_UNSPECIFIED | us-central | `golden-p1-0-ace7bacce749` | 4240.711 | 1516.647/46.716 | 2609.846/46.404 | 5.304/4.717 | 3.860/3.693 | 3.876/3.897 | 4/4 | 304 |
| R25 | cohort2_new | — | 6 | S2/3 | FIRST_BLOCK_GATE | CLOUD_PROVIDER_UNSPECIFIED | us-central | `golden-p1-0-43c1235dbf2a` | 5121.051 | 1989.433/52.444 | 2823.429/52.492 | 4.044/4.360 | 3.805/3.632 | 3.926/3.919 | 4/4 | 304 |
| R26 | cohort2_new | — | 7 | S3/1 | FIRST_BLOCK_GATE | CLOUD_PROVIDER_UNSPECIFIED | us-central | `golden-p1-0-d2aa6669a579` | 4396.404 | 1504.285/44.424 | 2332.108/41.720 | 5.348/5.278 | 3.761/3.811 | 3.888/3.922 | 4/4 | 304 |
| R27 | cohort2_new | — | 8 | S3/2 | PHASE_STABLE | CLOUD_PROVIDER_UNSPECIFIED | us-central | `golden-p1-0-d023eec82e6e` | 5990.810 | 2183.272/69.439 | 3487.434/73.952 | 3.685/3.530 | 3.930/3.948 | 3.942/3.955 | 4/4 | 304 |
| R28 | cohort2_new | — | 9 | S3/3 | CURRENT | CLOUD_PROVIDER_UNSPECIFIED | us-central | `golden-p1-0-09697d96352f` | 5070.823 | 2182.927/70.571 | 2593.833/53.782 | 3.685/4.746 | 3.929/3.934 | 3.940/3.943 | 4/4 | 304 |
| R29 | cohort2_new | — | 10 | S4/1 | CURRENT | CLOUD_PROVIDER_UNSPECIFIED | us-central | `golden-p1-0-649561530c89` | 6648.891 | 3302.562/101.235 | 3248.164/63.804 | 2.436/3.790 | 3.916/3.786 | 3.924/3.949 | 4/4 | 304 |
| R30 | cohort2_new | — | 11 | S4/2 | FIRST_BLOCK_GATE | CLOUD_PROVIDER_AZURE | us-central | `golden-p1-0-e23e716a7e60` | 6161.160 | 1846.349/54.219 | 3791.819/76.276 | 4.357/3.246 | 3.741/3.859 | 3.865/3.897 | 4/4 | 304 |
| R31 | cohort2_new | — | 12 | S4/3 | PHASE_STABLE | CLOUD_PROVIDER_UNSPECIFIED | us-central | `golden-p1-0-b49c908f3d52` | 4464.875 | 1681.069/52.109 | 2684.577/50.107 | 4.786/4.585 | 3.928/3.622 | 3.944/3.951 | 4/4 | 304 |
| R32 | cohort2_new | — | 13 | S5/1 | PHASE_STABLE | CLOUD_PROVIDER_UNSPECIFIED | us-central | `golden-p1-0-66a5391d5d89` | 4423.254 | 1695.170/54.119 | 2626.730/50.626 | 4.746/4.686 | 3.893/3.650 | 3.908/3.935 | 4/4 | 304 |
| R33 | cohort2_new | — | 14 | S5/2 | CURRENT | CLOUD_PROVIDER_UNSPECIFIED | us-central | `golden-p1-0-ba0db36dc589` | 4542.490 | 1803.713/44.783 | 2378.208/49.933 | 4.460/5.176 | 3.915/3.933 | 3.929/3.944 | 4/4 | 304 |
| R34 | cohort2_new | — | 15 | S5/3 | FIRST_BLOCK_GATE | CLOUD_PROVIDER_OCI | us-central | `golden-p1-0-5959b7081b20` | 4804.572 | 1771.840/51.196 | 2899.226/53.350 | 4.540/4.246 | 3.777/3.609 | 3.912/3.942 | 4/4 | 304 |
| R35 | cohort2_new | — | 16 | S6/1 | FIRST_BLOCK_GATE | CLOUD_PROVIDER_UNSPECIFIED | us-central | `golden-p1-0-654c0cbd895b` | 6104.284 | 2541.600/80.786 | 3239.940/66.024 | 3.165/3.799 | 3.849/3.893 | 3.954/3.945 | 4/4 | 304 |
| R36 | cohort2_new | — | 17 | S6/2 | PHASE_STABLE | CLOUD_PROVIDER_OCI | us-central | `golden-p1-0-f65314e3f4d7` | 4889.330 | 1863.757/56.539 | 2897.108/54.219 | 4.317/4.249 | 3.901/3.672 | 3.916/3.948 | 4/4 | 304 |
| R37 | cohort2_new | — | 18 | S6/3 | CURRENT | CLOUD_PROVIDER_UNSPECIFIED | us-central | `golden-p1-0-82d64a5342ee` | 5586.573 | 1988.235/62.086 | 3299.926/67.587 | 4.046/3.730 | 3.923/3.938 | 3.935/3.946 | 4/4 | 304 |
| R38 | cohort2_new | — | 19 | S7/1 | CURRENT | CLOUD_PROVIDER_OCI | us-central | `golden-p1-0-6a733b0d2424` | 4694.941 | 1696.342/53.061 | 2892.140/54.657 | 4.743/4.256 | 3.925/3.693 | 3.941/3.953 | 4/4 | 304 |
| R39 | cohort2_new | — | 20 | S7/2 | FIRST_BLOCK_GATE | CLOUD_PROVIDER_UNSPECIFIED | us-central | `golden-p1-0-0491b0e2f625` | 5953.608 | 2374.144/74.959 | 3249.249/67.982 | 3.389/3.789 | 3.831/3.876 | 3.920/3.922 | 4/4 | 304 |
| R40 | cohort2_new | — | 21 | S7/3 | PHASE_STABLE | CLOUD_PROVIDER_OCI | us-central | `golden-p1-0-0f826dd1b9b6` | 4266.879 | 1589.088/49.079 | 2580.985/50.046 | 5.063/4.769 | 3.913/3.635 | 3.929/3.933 | 4/4 | 304 |
| R41 | cohort2_new | — | 22 | S8/1 | PHASE_STABLE | CLOUD_PROVIDER_UNSPECIFIED | us-central | `golden-p1-0-6c21c8e160d4` | 4436.148 | 1439.077/42.356 | 2907.118/58.980 | 5.590/4.234 | 3.879/3.769 | 3.896/3.932 | 4/4 | 304 |
| R42 | cohort2_new | — | 23 | S8/2 | CURRENT | CLOUD_PROVIDER_AZURE | us-central | `golden-p1-0-8e306dca122f` | 4658.065 | 1693.963/52.563 | 2822.620/49.887 | 4.749/4.361 | 3.881/3.376 | 3.895/3.928 | 4/4 | 304 |
| R43 | cohort2_new | — | 24 | S8/3 | FIRST_BLOCK_GATE | CLOUD_PROVIDER_AZURE | us-central | `golden-p1-0-f814da6c8a4e` | 4862.540 | 1675.705/51.954 | 2638.248/54.796 | 4.801/4.666 | 3.773/3.851 | 3.893/3.910 | 4/4 | 304 |

Raw operation field recovery was checked independently for every selected row: model, ordinal, actual reader, scheduled reader where applicable, offset, bytes, launch/enter/exit/duration, depth, slot/generation, plan generation, admission sequence, previous launcher, start delta, wait, and reason. The JSON output preserves the artifact and request paths; the retained raw rows remain in each `attempt_0.json`/events artifact.

## 3. Arm-level recomputation (not the broken aggregate table)

### Source-envelope wall
| Arm | n | CLIP median | UNET median |
|---|---:|---:|---:|
| CURRENT | 14 | 1835.768 | 2720.389 |
| FIRST_BLOCK_GATE | 15 | 1891.488 | 2899.226 |
| PHASE_STABLE | 14 | 1688.120 | 2655.654 |

### Native p50
| Arm | n | CLIP median | UNET median |
|---|---:|---:|---:|
| CURRENT | 14 | 56.499 | 54.168 |
| FIRST_BLOCK_GATE | 15 | 54.219 | 54.796 |
| PHASE_STABLE | 14 | 52.993 | 50.367 |

### Throughput
| Arm | n | CLIP median | UNET median |
|---|---:|---:|---:|
| CURRENT | 14 | 4.384 | 4.531 |
| FIRST_BLOCK_GATE | 15 | 4.253 | 4.246 |
| PHASE_STABLE | 14 | 4.766 | 4.636 |

The values above are recomputed from raw native enter/exit and launch timestamps. They are not copied from the historical arm-level coherence/spacing table.

## 4. Natural round-robin-ness across all arms

For each model/run, actual native launch readers were sorted by the raw launch timestamp. The best cyclic ratio chooses only the best of the four rotations after the fact; it does not use PHASE's intended schedule. Expected-next is the fraction of transitions with `(reader+1) mod 4`. Cyclic distance 0/1/2/3 counts are emitted in JSON.

| arm | model | best cyclic match median | expected-next median | cyclic distance 0/1/2/3 (pooled transitions) |
|---|---|---:|---:|---|
| CURRENT | CLIP | 0.446 | 0.324 | 0.000/0.306/0.328/0.366 |
| CURRENT | UNET | 0.443 | 0.317 | 0.000/0.377/0.312/0.311 |
| FIRST_BLOCK_GATE | CLIP | 0.392 | 0.218 | 0.000/0.241/0.350/0.409 |
| FIRST_BLOCK_GATE | UNET | 0.386 | 0.262 | 0.000/0.338/0.343/0.319 |
| PHASE_STABLE | CLIP | 0.450 | 0.282 | 0.000/0.316/0.319/0.365 |
| PHASE_STABLE | UNET | 0.451 | 0.268 | 0.000/0.302/0.386/0.311 |

### CURRENT hypothetical round-robin audit

- CURRENT CLIP best cyclic match vs source_wall: n=14, Pearson r=-0.385, Spearman ρ=-0.288.
- CURRENT UNET best cyclic match vs source_wall: n=14, Pearson r=-0.041, Spearman ρ=0.103.
- CURRENT CLIP best cyclic match vs native_p50: n=14, Pearson r=-0.380, Spearman ρ=-0.306.
- CURRENT UNET best cyclic match vs native_p50: n=14, Pearson r=-0.086, Spearman ρ=0.147.
- CURRENT CLIP best cyclic match vs throughput: n=14, Pearson r=0.385, Spearman ρ=0.288.
- CURRENT UNET best cyclic match vs throughput: n=14, Pearson r=-0.005, Spearman ρ=-0.103.
- Historical replication check, CLIP best-RR vs source wall: original report `n=8, Pearson r=-0.404, Spearman ρ=-0.238`; second report `n=8, Pearson r=-0.262, Spearman ρ=0.000`. The signs are both negative Pearson but Spearman is not stable, so this is suggestive rather than established.
- Historical replication check, UNET best-RR vs source wall: original report `n=8, Pearson r=0.475, Spearman ρ=0.286`; second report `n=8, Pearson r=-0.287, Spearman ρ=-0.238`. The first report reverses sign, so reader order is not a stable cross-cohort explanation.

The cohort-specific results are in the JSON correlation table. In particular, a positive reader-order mechanism would require a consistent performance-consistent direction in CURRENT, and then replication in both time ranges/local contrasts. A pooled coefficient without that check is not causal evidence.

## 5. Reader race / reacquisition

| arm | model | same repeat | within 2 | within 3 | switch fraction | rolling-4 unique median | longest exact streak median | count CV median |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| CURRENT | CLIP | 0.000 | 0.000 | 0.047 | 1.000 | 3.949 | 1 | 0.027 |
| CURRENT | UNET | 0.000 | 0.000 | 0.050 | 1.000 | 3.948 | 1 | 0.018 |
| FIRST_BLOCK_GATE | CLIP | 0.000 | 0.000 | 0.051 | 1.000 | 3.949 | 1 | 0.027 |
| FIRST_BLOCK_GATE | UNET | 0.000 | 0.005 | 0.050 | 1.000 | 3.945 | 1 | 0.018 |
| PHASE_STABLE | CLIP | 0.000 | 0.000 | 0.038 | 1.000 | 3.962 | 1 | 0.027 |
| PHASE_STABLE | UNET | 0.000 | 0.000 | 0.039 | 1.000 | 3.961 | 1 | 0.018 |

The complete per-run transition matrices, normalized matrices, reader counts, streaks, and within-window unique-reader counts are in the machine-readable output. Correlations against CLIP/UNET walls, p50s, throughput, and envelope are included for all arms and for CURRENT/Phase cohort contexts.

- CURRENT CLIP: best RR vs source wall `n=14, Pearson r=-0.385, Spearman ρ=-0.288`; same-reader repeat vs source wall `n=14, Pearson r=—, Spearman ρ=—`; same-reader repeat vs native p50 `n=14, Pearson r=—, Spearman ρ=—`.
- CURRENT UNET: best RR vs source wall `n=14, Pearson r=-0.041, Spearman ρ=0.103`; same-reader repeat vs source wall `n=14, Pearson r=—, Spearman ρ=—`; same-reader repeat vs native p50 `n=14, Pearson r=—, Spearman ρ=—`.

Interpretation rule: PHASE materially reduces reacquisition only if its raw same-reader and completion-coupling measures move lower than CURRENT, with compatible local-block direction. If the arm medians move but local contrasts do not, call it unresolved rather than mechanism.

## 6. Completion → next-launch coupling

For every operation with a later launch after its native exit, the next launch was selected directly from timestamps. `most_recent_completer` is an observable proxy for completion-driven arbitration; ready/blocked state is not directly recorded and is marked unavailable rather than inferred.

| arm | model | n completion events | completing reader is next launcher | next is most recent completer | completion→next p50 ms | outstanding-at-completion p50 |
|---|---|---:|---:|---:|---:|---:|
| CURRENT | CLIP | 1624 | 0.991 | 0.983 | 0.323 | 3.000 |
| CURRENT | UNET | 2520 | 0.989 | 0.978 | 0.280 | 3.000 |
| FIRST_BLOCK_GATE | CLIP | 1740 | 0.966 | 0.940 | 0.307 | 3.000 |
| FIRST_BLOCK_GATE | UNET | 2702 | 0.978 | 0.967 | 0.288 | 3.000 |
| PHASE_STABLE | CLIP | 1624 | 0.991 | 0.983 | 0.333 | 3.000 |
| PHASE_STABLE | UNET | 2520 | 0.994 | 0.989 | 0.272 | 3.000 |

The completion-coupling values are recomputed from each raw model sequence; they are not the historical arm summary:
- CURRENT CLIP: same completion-next `0.991`; most-recent-completer `0.983`; completion→next p50 `0.323` ms.
- CURRENT UNET: same completion-next `0.989`; most-recent-completer `0.978`; completion→next p50 `0.280` ms.
- FIRST_BLOCK_GATE CLIP: same completion-next `0.966`; most-recent-completer `0.940`; completion→next p50 `0.307` ms.
- FIRST_BLOCK_GATE UNET: same completion-next `0.978`; most-recent-completer `0.967`; completion→next p50 `0.288` ms.
- PHASE_STABLE CLIP: same completion-next `0.991`; most-recent-completer `0.983`; completion→next p50 `0.333` ms.
- PHASE_STABLE UNET: same completion-next `0.994`; most-recent-completer `0.989`; completion→next p50 `0.272` ms.

A falling completion-next fraction and falling most-recent-completer fraction in PHASE would directly support the claim that PHASE breaks completion-driven selection. If those fields do not move, the traffic-controller explanation is not supported by this telemetry even if PHASE is faster.

## 7. Actual launch waveform

The floor is separated from above-floor shape. Each model/run has all start-to-start gaps, distribution quantiles, bins, tight-run lengths, drought, and rolling 4/8/16 spans in JSON.

| arm | model | gap p50 | p90 | p99 | CV | 4–6 ms fraction | >40 ms fraction | max drought ms | rolling-16 span CV median |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| CURRENT | CLIP | 12.131 | 31.353 | 49.666 | 0.759 | 0.244 | 0.034 | 67.472 | 0.127 |
| CURRENT | UNET | 11.275 | 28.980 | 46.671 | 1.069 | 0.276 | 0.019 | 177.162 | 0.140 |
| FIRST_BLOCK_GATE | CLIP | 11.861 | 32.118 | 58.663 | 0.766 | 0.235 | 0.034 | 71.597 | 0.144 |
| FIRST_BLOCK_GATE | UNET | 11.439 | 33.683 | 52.793 | 0.909 | 0.268 | 0.033 | 123.620 | 0.136 |
| PHASE_STABLE | CLIP | 10.436 | 26.544 | 40.754 | 0.727 | 0.256 | 0.017 | 51.941 | 0.140 |
| PHASE_STABLE | UNET | 10.303 | 26.019 | 42.491 | 0.984 | 0.251 | 0.014 | 169.245 | 0.158 |

Waveform/outcome correlations are emitted for all unique runs, CURRENT only, PHASE only, and each model. The preselected metrics are median/p90/CV gap, near-floor fraction, >40 ms drought fraction, maximum drought, and rolling-16 span CV; this avoids a significance hunt over arbitrary transformations.

## 8. PHASE schedule-adherence context

| phase run | cohort | overall | CLIP | UNET | CLIP thirds | UNET thirds | longest match/skip | match↔skip transitions |
|---|---|---:|---:|---:|---|---|---|---:|
| golden-p1-0-6e46ad378fa0 | cohort1_only | 0.444 | 0.775 | 0.228 | 0.425/0.900/1.000 | 0.097/0.475/0.115 | 57/4; 3/48 | 23/48 |
| golden-p1-0-5dac4837db40 | cohort1_only | 0.431 | 0.425 | 0.435 | 0.350/0.625/0.300 | 0.258/0.082/0.967 | 10/16; 59/44 | 48/39 |
| golden-p1-0-8cca1410e757 | cohort1_only | 0.444 | 0.758 | 0.239 | 0.800/0.975/0.500 | 0.323/0.262/0.131 | 59/2; 2/46 | 29/80 |
| golden-p1-0-0b2fadac4af2 | cohort1_only | 0.490 | 0.508 | 0.478 | 0.550/0.500/0.475 | 0.613/0.393/0.426 | 6/3; 14/3 | 105/132 |
| golden-p1-0-23cc218345cb | cohort1_only | 0.211 | 0.250 | 0.185 | 0.250/0.250/0.250 | 0.177/0.377/0.000 | 2/8; 2/66 | 58/50 |
| golden-p1-0-8d991f9b793f | cohort1_only | 0.194 | 0.400 | 0.060 | 0.200/0.500/0.500 | 0.177/0.000/0.000 | 2/18; 5/144 | 52/13 |
| golden-p1-0-eb68cc401165 | reused_in_second_report | 0.319 | 0.042 | 0.500 | 0.125/0.000/0.000 | 0.548/0.492/0.459 | 1/102; 10/6 | 10/87 |
| golden-p1-0-b3dd83455375 | reused_in_second_report | 0.349 | 0.508 | 0.245 | 0.525/0.500/0.500 | 0.226/0.262/0.246 | 17/16; 1/6 | 45/90 |
| golden-p1-0-d023eec82e6e | cohort2_new | 0.062 | 0.083 | 0.049 | 0.000/0.000/0.250 | 0.032/0.049/0.066 | 2/96; 1/80 | 10/18 |
| golden-p1-0-b49c908f3d52 | cohort2_new | 0.253 | 0.433 | 0.136 | 0.300/0.500/0.500 | 0.048/0.311/0.049 | 2/8; 1/52 | 62/50 |
| golden-p1-0-66a5391d5d89 | cohort2_new | 0.289 | 0.117 | 0.402 | 0.125/0.225/0.000 | 0.403/0.492/0.311 | 2/49; 2/16 | 26/83 |
| golden-p1-0-f65314e3f4d7 | cohort2_new | 0.161 | 0.100 | 0.201 | 0.300/0.000/0.000 | 0.258/0.246/0.098 | 1/92; 1/28 | 24/74 |
| golden-p1-0-0f826dd1b9b6 | cohort2_new | 0.135 | 0.025 | 0.207 | 0.075/0.000/0.000 | 0.226/0.033/0.361 | 1/104; 2/72 | 6/55 |
| golden-p1-0-6c21c8e160d4 | cohort2_new | 0.211 | 0.158 | 0.245 | 0.100/0.000/0.375 | 0.258/0.131/0.344 | 2/60; 11/44 | 23/50 |

The existing adherence audit's main result remains: adherence is not a stable performance predictor across all 14 Phase runs. Here it is joined to actual order, reacquisition, coupling, and waveform metrics rather than treated as the treatment itself.

## 9. Within-block normalization

Phase advantages are computed against the nearby CURRENT in the same local interleaved block; reused manifests use their actual second-report block. Negative wall/p50 deltas and positive throughput deltas favor Phase.

| phase ID | block | membership | adherence | envelope Δ ms | CLIP wall Δ | UNET wall Δ | CLIP p50 Δ | UNET p50 Δ | CLIP throughput Δ | UNET throughput Δ |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| golden-p1-0-6e46ad378fa0 | O1 | cohort1_only | 0.444 | 1332.817 | 242.531 | 831.040 | 6.501 | -0.145 | -0.570 | -1.570 |
| golden-p1-0-5dac4837db40 | O2 | cohort1_only | 0.431 | 2287.215 | 341.011 | 1948.879 | 10.880 | 40.506 | -0.473 | -2.235 |
| golden-p1-0-8cca1410e757 | O3 | cohort1_only | 0.444 | 574.328 | 51.641 | 297.358 | 4.218 | 13.284 | -0.080 | -0.254 |
| golden-p1-0-0b2fadac4af2 | O4 | cohort1_only | 0.490 | 598.622 | 412.657 | 154.570 | 12.460 | 6.183 | -1.342 | -0.327 |
| golden-p1-0-23cc218345cb | O5 | cohort1_only | 0.211 | -2331.469 | -746.679 | -1526.738 | -23.428 | -31.745 | 1.598 | 1.956 |
| golden-p1-0-8d991f9b793f | O6 | cohort1_only | 0.194 | -1035.516 | -236.754 | -588.954 | -8.527 | -13.479 | 0.738 | 1.365 |
| golden-p1-0-eb68cc401165 | S1 | reused_in_second_report | 0.319 | -2075.713 | -587.236 | -1491.202 | -19.234 | -31.459 | 1.975 | 2.685 |
| golden-p1-0-b3dd83455375 | S2 | reused_in_second_report | 0.349 | -956.412 | -189.154 | -912.817 | -11.543 | -13.580 | 0.756 | 2.537 |
| golden-p1-0-d023eec82e6e | S3 | cohort2_new | 0.062 | 919.987 | 0.345 | 893.601 | -1.132 | 20.170 | -0.001 | -1.216 |
| golden-p1-0-b49c908f3d52 | S4 | cohort2_new | 0.253 | -2184.017 | -1621.493 | -563.587 | -49.125 | -13.697 | 2.350 | 0.796 |
| golden-p1-0-66a5391d5d89 | S5 | cohort2_new | 0.289 | -119.236 | -108.544 | 248.522 | 9.336 | 0.694 | 0.286 | -0.490 |
| golden-p1-0-f65314e3f4d7 | S6 | cohort2_new | 0.161 | -697.243 | -124.478 | -402.818 | -5.546 | -13.369 | 0.270 | 0.519 |
| golden-p1-0-0f826dd1b9b6 | S7 | cohort2_new | 0.135 | -428.062 | -107.255 | -311.154 | -3.982 | -4.611 | 0.320 | 0.513 |
| golden-p1-0-6c21c8e160d4 | S8 | cohort2_new | 0.211 | -221.918 | -254.887 | 84.498 | -10.207 | 9.092 | 0.841 | -0.127 |

Selected local-advantage correlations (Phase-run behavior versus Phase−CURRENT delta) are in the JSON. The report deliberately keeps the cohort membership visible because the first and later time ranges show different raw rate regimes.

- CLIP rr vs local envelope delta: n=14, r=0.296, ρ=0.104.
- CLIP same_repeat vs local envelope delta: n=14, r=—, ρ=—.
- CLIP completion_same vs local envelope delta: n=14, r=-0.315, ρ=-0.418.
- CLIP gap_p90 vs local envelope delta: n=14, r=0.769, ρ=0.763.
- CLIP gap_cv vs local envelope delta: n=14, r=0.651, ρ=0.881.
- CLIP fraction_gt40 vs local envelope delta: n=14, r=0.708, ρ=0.739.
- CLIP drought vs local envelope delta: n=14, r=0.578, ρ=0.723.
- UNET rr vs local envelope delta: n=14, r=-0.152, ρ=-0.121.
- UNET same_repeat vs local envelope delta: n=14, r=0.345, ρ=0.378.
- UNET completion_same vs local envelope delta: n=14, r=-0.189, ρ=-0.244.
- UNET gap_p90 vs local envelope delta: n=14, r=0.693, ρ=0.569.
- UNET gap_cv vs local envelope delta: n=14, r=0.182, ρ=0.051.
- UNET fraction_gt40 vs local envelope delta: n=14, r=0.674, ρ=0.708.
- UNET drought vs local envelope delta: n=14, r=0.238, ρ=0.121.

## 10. Static CURRENT vs PHASE_STABLE code-path audit

The source implementation audited is `comfymodal_runtime/golden_source_threads.py` in the experiment worktree. Both arms share the same allocator, slots, whole-file mmap, reader loop, `execute_block`, and native `_MAPPER.memmove` boundary. The behavioral fork is inside `GlobalSourcePacer.paced_copy`.

### Shared path

`_run_reader_loop` → control `lock` → `claim_block` (global sequential range cursor + first free slot) → `execute_block` → `_paced_copy` → pacer admission → `_copy(mark_actual_start)` → raw `memmove` → publish READY under control lock → doorbell. No control lock is held through mmap/memmove; the pacer condition lock is released immediately before memmove.

### CURRENT

`claim_block` is first-ready/first-to-control-lock. `paced_copy` acquires the condition lock, waits only for the 4 ms floor, records `scheduled_reader=None`, `previous_source_reader`, admission sequence/wait/reason, invokes the callback, and releases the condition lock inside `mark_actual_start` immediately before `memmove`. The completing reader returns to the loop and races with other readers for the next claim/admission.

### PHASE_STABLE

`_phase_stable_copy` acquires the same condition lock, registers the reader in `_phase_ready_readers`, and notifies. It waits for the 4 ms floor, then chooses `_phase_candidate(_phase_next_reader, ready_set)`: the scheduled reader if ready, otherwise the first ready reader in a forward cyclic scan. If no candidate is ready, it condition-waits. If another reader is selected, this reader condition-waits. On selection, the scheduled sequence advances one turn, the selected reader is removed from the ready set, and the same lock is released immediately before native memmove. Telemetry records the intended scheduled reader and skip count, but ready-set occupancy and wake winner are not recorded.

### FIRST_BLOCK_GATE

The non-Phase branch is the same CURRENT admission after an ordinal-zero condition wait. On ordinal zero callback completion, `_first_block_complete` and `_gate_release_pending` are set and all waiters are notified. This separates only startup ordinal-zero release, not steady-state reader arbitration.

### Lock/wakeup implications

- Allocator selection and reader arbitration are separate: the reader claims the next global ordinal before entering the pacer. PHASE does not give a reader ownership of a file region and does not change source ordinal allocation.
- CURRENT has no ready-reader set at the pacer; after the 4 ms wait, whichever thread reaches the condition lock proceeds.
- PHASE adds a per-reader registration set, a cyclic expected-reader cursor, forward-scan fallback, condition waits for floor/readiness/turn, and notifications on registration, selection, actual-start release, and cleanup.
- The lock is not held across native copy in either arm. Therefore PHASE is not simply serializing memmove. It serializes the *admission decision and launch ownership* while preserving copy overlap.
- The telemetry cannot directly prove Python GIL scheduling, OS wake fairness, reader-ready status before registration, or exact wakeup winner. Those remain unresolved observability gaps.


### Static source references

- `golden_source_threads.py:2140-2214`: shared reader loop, control-lock claim, `execute_block` dispatch, and semaphore wake path.
- `golden_source_threads.py:1044-1081`: shared global range cursor/first-free-slot `claim_block` under the control lock.
- `golden_source_threads.py:343-549`: `GlobalSourcePacer` state, CURRENT/first-block behavior, actual-start recording, and condition notifications.
- `golden_source_threads.py:553-660`: PHASE ready-reader registration, cyclic forward candidate scan, condition waits, turn advancement, and release immediately before native copy.
- `golden_source_threads.py:2030-2112`: shared mmap/native `memmove`, raw operation record construction, READY publication, and doorbell.

## 11. Dynamic evidence versus static mechanisms

| candidate mechanism | static difference | expected signature | observed evidence in this audit | assessment |
|---|---|---|---|---|
| More natural cyclic reader order | CURRENT is first-ready; PHASE selects forward cyclic candidate | CURRENT best cyclic match should track faster wall/p50/throughput | See CURRENT hypothetical correlations and cohort splits in JSON | supported only if direction replicates; not assumed |
| Reduced same-reader reacquisition | PHASE removes selected reader from ready set until it re-registers; CURRENT has no ready set | lower same-reader repeat, higher switch/rolling diversity | Immediate same-reader repeats are zero in arm medians across all arms; no material reduction is observed | contradicted as the coarse launch-order mechanism |
| Reduced completion-driven next launch | PHASE chooses scheduled/forward-ready reader rather than whoever completes/races | lower completing-reader-next fraction and most-recent-completer fraction | Fractions remain about 0.97–0.99; PHASE is not lower and UNET is higher | contradicted by current telemetry proxy |
| Different above-floor waveform | PHASE adds condition waits and turn eligibility before the same 4 ms gate | different p90/CV/burst/drought/rolling-span shape | PHASE gap-p90 and >40 ms medians are lower; both track local Phase advantage | best-supported observable consequence |
| Allocator/range geometry | No static difference: shared global cursor and claim_block are shared | no arm difference in ordinal/offset geometry | raw operation identity checks | contradicted as primary explanation |
| Native copy implementation | No static difference: same execute_block/_copy/memmove | same native boundary; differences only via overlap/order/timing | same bytes/geometry and raw native boundary | contradicted as direct implementation change |
| Native QD alone | No direct arm-specific QD target; same slots/readers | Phase benefit should follow QD increase | effective QD summaries and local contrasts | unlikely if QD equivalent; unresolved if QD shifts |
| Ready-state fairness / wakeup arbitration | PHASE condition/ready-set notifications; CURRENT lock race | order/coupling differences without high nominal adherence | ready state itself not recorded; order/coupling are proxies | plausible, telemetry-limited |

## 12. Answers to the required questions

1. **Are naturally more round-robin CURRENT runs faster?** See the explicit CURRENT-only best-rotation correlations. A conclusion requires direction replication across both historical ranges; pooled n=14-style evidence is not enough.
2. **Does PHASE materially reduce same-reader reacquisition?** Use the raw repeat metrics above. If arm medians and local Phase−CURRENT contrasts both fall, yes; otherwise unresolved. The audit does not infer this from adherence.
3. **Does PHASE reduce completion-driven selection?** The decisive fields are completing-reader-next and most-recent-completer fractions. A lower PHASE value supports this mechanism directly.
4. **Does waveform differ beyond 4 ms?** Compare p90/CV, near-floor share, >40 ms share, drought, and rolling-span metrics; the floor alone is not a treatment difference.
5. **Which waveform characteristics track fast performance?** Use the preselected correlation table; report only directions replicated by cohort/local contrasts, not a single pooled coefficient.
6. **Does nominal adherence explain benefit?** No, not as a sufficient explanation: adherence varies and its Phase-only relationship is not stable across cohorts.
7. **If not, what actual behavior does?** The remaining evidence-bearing candidates are admission arbitration, reader reacquisition/completion coupling, and the resulting above-floor waveform.
8. **Is reader identity/order important?** It is a plausible mediator, but only CURRENT hypothetical-order correlations can distinguish order itself from centralized arbitration.
9. **Is centralized arbitration/reduced racing more likely?** Static code makes this the narrower mechanism: PHASE's unique behavior is in arbitration, while allocator, copy, mapping, slots, and floor are shared.
10. **What code differences remain plausible?** Ready-set registration, cyclic forward selection, condition waits/notifications, lock release timing at actual launch, and the resulting OS/GIL wakeup interaction.
11. **Which hypotheses are contradicted?** Changed ordinal allocator, reader-owned file regions, changed native copy, changed mmap lifecycle, and a simple QD increase are not supported by the static path/raw identity evidence.
12. **Which one or two mechanisms merit a later test?** Only after this audit's dynamic tables are reviewed: (a) completion/reacquisition arbitration as one mechanism, and (b) above-floor launch waveform shaping as its observable consequence. The smallest future test should separate these two, not re-test nominal adherence wholesale.


### Explicit dynamic determinations

- Same-reader launch reacquisition: **not a Phase-specific effect** in this corpus; immediate repeats are zero in the arm medians across all arms.
- Completion-driven next launch: **not reduced by Phase** in the available proxy; completing-reader-next and most-recent-completer fractions stay around 0.97–0.99.
- Above-floor waveform: **the strongest observed performance-linked difference**; Phase has lower gap p90 and fewer >40 ms gaps, and these metrics track local Phase advantage.
- Static mechanism left standing: **PHASE's centralized ready-reader/condition arbitration as a cause of waveform shaping**, not nominal schedule adherence itself. Exact wake/GIL/OS sub-causality remains unresolved.

## 13. Limitations and exact next uncertainty

- The operation rows record launch/completion/reader/admission state but not condition wait wake winner, ready-set membership over time, Python thread identity scheduling, GIL handoff, or allocator claim timestamp. Therefore the audit can establish signatures and eliminate some explanations, but cannot attribute every millisecond to a specific scheduler event.
- Provider labels vary inside the pinned region; provider is retained and cohort identity is preserved. The local-block contrasts reduce time drift but do not eliminate all infrastructure variance.
- Native operation samples are clustered within runs. Run-level correlations are the unit used for exploratory association; operation-level n is not treated as independent evidence.
- No new experiment is run or implemented here. The exact next experiment, if approved later, is a policy-isolation experiment: retain PHASE's condition/ready-set arbitration and 4 ms pacer, replace only cyclic expected-reader selection with a non-cyclic ready-reader policy, and add ready-set registration/selection/wakeup plus claim-to-pacer timestamps. Its purpose is to distinguish reader-order policy from arbitration-induced waveform shaping. This is a recommendation only, not an implementation or deployment.

## 14. Audit provenance

- Raw authority: `.slim/worktrees/golden-source-admission-state-ab/artifacts/phase_p1_parallel_golden_v1/*/{manifest.json,attempt_0.json,attempt_0_events.json}`.
- Static authority: `.slim/worktrees/golden-source-admission-state-ab/comfymodal_runtime/golden_source_threads.py` and the linked transport/payload sources.
- Derived files: `GOLDEN_PHASE_MECHANISM_RUN_METRICS.json`, `.csv`, and `GOLDEN_PHASE_MECHANISM_RAW_OPERATIONS.jsonl` in this worktree.
- Existing duplicated arm-level table was not used for calculations.
