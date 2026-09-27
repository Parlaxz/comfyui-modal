# September UNET/CLIP Experiment 06: Source Block x QD Matrix

STATUS=COMPLETE
DECISION_METRIC=SOURCE_WALL_MS
SECONDARY_METRIC=EFFECTIVE_GBPS

## Best Source Configuration

| model | block MiB | QD | SOURCE median ms | effective GB/s |
|---|---:|---:|---:|---:|
| CLIP | 256 | 8 | 6220.806 | 1.293230 |
| UNET | 256 | 8 | 10015.473 | 1.229080 |

Top two observed source configurations are also recorded in `best_two_source_configurations` in the JSON report.

Best means the lowest median SOURCE_WALL_MS among observed cells. Historical integrated artifacts are retained separately and are not part of this cohort.

## Performance By Block Size At Each QD

| model | QD | block MiB | SOURCE median ms | effective GB/s |
|---|---:|---:|---:|---:|
| CLIP | 1 | 32 | 11605.3571485 | 0.6932088421802525 |
| CLIP | 2 | 32 | 6955.1381975 | 1.1566896247858487 |
| CLIP | 4 | 32 | 6865.4337935 | 1.1718030402706263 |
| CLIP | 8 | 32 | 6981.777275 | 1.1522762579102754 |
| CLIP | 1 | 64 | 13552.19442 | 0.5936260905560414 |
| CLIP | 2 | 64 | 9293.539316 | 0.8656482657957477 |
| CLIP | 4 | 64 | 6499.2606635 | 1.2378232861439993 |
| CLIP | 8 | 64 | 6258.910276500001 | 1.2853573284483557 |
| CLIP | 1 | 128 | 12572.5082375 | 0.6398831513988896 |
| CLIP | 2 | 128 | 10481.8939815 | 0.7675078765535023 |
| CLIP | 4 | 128 | 6318.062001 | 1.2733234005501493 |
| CLIP | 8 | 128 | 7854.211531999999 | 1.024283107123222 |
| CLIP | 1 | 256 | 12002.848142 | 0.6702522681970293 |
| CLIP | 2 | 256 | 6440.7810855 | 1.249062199942085 |
| CLIP | 4 | 256 | 6300.6603065 | 1.2768401724023337 |
| CLIP | 8 | 256 | 6220.806454 | 1.2932304278373874 |
| UNET | 1 | 32 | 18862.8083745 | 0.6525972817834078 |
| UNET | 2 | 32 | 12915.70544 | 0.9530890534152658 |
| UNET | 4 | 32 | 12589.7681515 | 0.9777636350303524 |
| UNET | 8 | 32 | 11224.089623 | 1.0967319297571507 |
| UNET | 1 | 64 | 18066.3944465 | 0.6813654771267755 |
| UNET | 2 | 64 | 12057.179286 | 1.0209533407447418 |
| UNET | 4 | 64 | 10992.557742500001 | 1.1198319590723769 |
| UNET | 8 | 64 | 10956.671946499999 | 1.1234996842204672 |
| UNET | 1 | 128 | 19155.5787475 | 0.6426231039146525 |
| UNET | 2 | 128 | 13097.7005525 | 0.9398456944910368 |
| UNET | 4 | 128 | 11228.527356499999 | 1.0962984798602338 |
| UNET | 8 | 128 | 11747.213226 | 1.04789257121466 |
| UNET | 1 | 256 | 17412.0592185 | 0.7069708021048448 |
| UNET | 2 | 256 | 12456.88342 | 0.9881940014174107 |
| UNET | 4 | 256 | 11471.8784075 | 1.0730428823192701 |
| UNET | 8 | 256 | 10015.472503500001 | 1.2290800526583463 |

## Performance By QD At Each Block Size

| model | block MiB | QD | SOURCE median ms | effective GB/s |
|---|---:|---:|---:|---:|
| CLIP | 32 | 1 | 11605.3571485 | 0.6932088421802525 |
| CLIP | 32 | 2 | 6955.1381975 | 1.1566896247858487 |
| CLIP | 32 | 4 | 6865.4337935 | 1.1718030402706263 |
| CLIP | 32 | 8 | 6981.777275 | 1.1522762579102754 |
| CLIP | 64 | 1 | 13552.19442 | 0.5936260905560414 |
| CLIP | 64 | 2 | 9293.539316 | 0.8656482657957477 |
| CLIP | 64 | 4 | 6499.2606635 | 1.2378232861439993 |
| CLIP | 64 | 8 | 6258.910276500001 | 1.2853573284483557 |
| CLIP | 128 | 1 | 12572.5082375 | 0.6398831513988896 |
| CLIP | 128 | 2 | 10481.8939815 | 0.7675078765535023 |
| CLIP | 128 | 4 | 6318.062001 | 1.2733234005501493 |
| CLIP | 128 | 8 | 7854.211531999999 | 1.024283107123222 |
| CLIP | 256 | 1 | 12002.848142 | 0.6702522681970293 |
| CLIP | 256 | 2 | 6440.7810855 | 1.249062199942085 |
| CLIP | 256 | 4 | 6300.6603065 | 1.2768401724023337 |
| CLIP | 256 | 8 | 6220.806454 | 1.2932304278373874 |
| UNET | 32 | 1 | 18862.8083745 | 0.6525972817834078 |
| UNET | 32 | 2 | 12915.70544 | 0.9530890534152658 |
| UNET | 32 | 4 | 12589.7681515 | 0.9777636350303524 |
| UNET | 32 | 8 | 11224.089623 | 1.0967319297571507 |
| UNET | 64 | 1 | 18066.3944465 | 0.6813654771267755 |
| UNET | 64 | 2 | 12057.179286 | 1.0209533407447418 |
| UNET | 64 | 4 | 10992.557742500001 | 1.1198319590723769 |
| UNET | 64 | 8 | 10956.671946499999 | 1.1234996842204672 |
| UNET | 128 | 1 | 19155.5787475 | 0.6426231039146525 |
| UNET | 128 | 2 | 13097.7005525 | 0.9398456944910368 |
| UNET | 128 | 4 | 11228.527356499999 | 1.0962984798602338 |
| UNET | 128 | 8 | 11747.213226 | 1.04789257121466 |
| UNET | 256 | 1 | 17412.0592185 | 0.7069708021048448 |
| UNET | 256 | 2 | 12456.88342 | 0.9881940014174107 |
| UNET | 256 | 4 | 11471.8784075 | 1.0730428823192701 |
| UNET | 256 | 8 | 10015.472503500001 | 1.2290800526583463 |

## Performance Versus Nominal Outstanding Source Bytes

| model | nominal MiB | configurations | SOURCE medians ms | FILE_TO_CUDA medians ms |
|---|---:|---|---|---|
| CLIP | 32.0 | 32x1 | 32x1=11605.3571485 | 32x1=UNAVAILABLE |
| CLIP | 64.0 | 32x2, 64x1 | 32x2=6955.1381975; 64x1=13552.19442 | 32x2=UNAVAILABLE; 64x1=UNAVAILABLE |
| CLIP | 128.0 | 32x4, 64x2, 128x1 | 32x4=6865.4337935; 64x2=9293.539316; 128x1=12572.5082375 | 32x4=UNAVAILABLE; 64x2=UNAVAILABLE; 128x1=UNAVAILABLE |
| CLIP | 256.0 | 32x8, 64x4, 128x2, 256x1 | 32x8=6981.777275; 64x4=6499.2606635; 128x2=10481.8939815; 256x1=12002.848142 | 32x8=UNAVAILABLE; 64x4=UNAVAILABLE; 128x2=UNAVAILABLE; 256x1=UNAVAILABLE |
| CLIP | 512.0 | 64x8, 128x4, 256x2 | 64x8=6258.910276500001; 128x4=6318.062001; 256x2=6440.7810855 | 64x8=UNAVAILABLE; 128x4=UNAVAILABLE; 256x2=UNAVAILABLE |
| CLIP | 1024.0 | 128x8, 256x4 | 128x8=7854.211531999999; 256x4=6300.6603065 | 128x8=UNAVAILABLE; 256x4=UNAVAILABLE |
| CLIP | 2048.0 | 256x8 | 256x8=6220.806454 | 256x8=UNAVAILABLE |
| UNET | 32.0 | 32x1 | 32x1=18862.8083745 | 32x1=UNAVAILABLE |
| UNET | 64.0 | 32x2, 64x1 | 32x2=12915.70544; 64x1=18066.3944465 | 32x2=UNAVAILABLE; 64x1=UNAVAILABLE |
| UNET | 128.0 | 32x4, 64x2, 128x1 | 32x4=12589.7681515; 64x2=12057.179286; 128x1=19155.5787475 | 32x4=UNAVAILABLE; 64x2=UNAVAILABLE; 128x1=UNAVAILABLE |
| UNET | 256.0 | 32x8, 64x4, 128x2, 256x1 | 32x8=11224.089623; 64x4=10992.557742500001; 128x2=13097.7005525; 256x1=17412.0592185 | 32x8=UNAVAILABLE; 64x4=UNAVAILABLE; 128x2=UNAVAILABLE; 256x1=UNAVAILABLE |
| UNET | 512.0 | 64x8, 128x4, 256x2 | 64x8=10956.671946499999; 128x4=11228.527356499999; 256x2=12456.88342 | 64x8=UNAVAILABLE; 128x4=UNAVAILABLE; 256x2=UNAVAILABLE |
| UNET | 1024.0 | 128x8, 256x4 | 128x8=11747.213226; 256x4=11471.8784075 | 128x8=UNAVAILABLE; 256x4=UNAVAILABLE |
| UNET | 2048.0 | 256x8 | 256x8=10015.472503500001 | 256x8=UNAVAILABLE |

## Cohort Audit

- New attempts retained: 503; eligible: 320; invalid: 183.
- Eligible observations retained: 320.

## Invalid Attempts And Raw Evidence

| attempt | status | error | raw artifact |
|---|---|---|---|
| clip_b128_qd1_R1_A2 | error | TypeError:run_source_ceiling_oracle() takes from 3 to 4 positional arguments but 6 were given | `unetClipExperimentsSeptember/06_source_only_runs/clip_b128_qd1_R1_A2.json` |
| clip_b128_qd1_R1_A3 | error | TypeError:run_source_ceiling_oracle() takes from 3 to 4 positional arguments but 6 were given | `unetClipExperimentsSeptember/06_source_only_runs/clip_b128_qd1_R1_A3.json` |
| clip_b128_qd1_R2_A2 | error | TypeError:run_source_ceiling_oracle() takes from 3 to 4 positional arguments but 6 were given | `unetClipExperimentsSeptember/06_source_only_runs/clip_b128_qd1_R2_A2.json` |
| clip_b128_qd1_R2_A3 | error | TypeError:run_source_ceiling_oracle() takes from 3 to 4 positional arguments but 6 were given | `unetClipExperimentsSeptember/06_source_only_runs/clip_b128_qd1_R2_A3.json` |
| clip_b128_qd1_R3_A2 | error | TypeError:run_source_ceiling_oracle() takes from 3 to 4 positional arguments but 6 were given | `unetClipExperimentsSeptember/06_source_only_runs/clip_b128_qd1_R3_A2.json` |
| clip_b128_qd2_R1_A2 | error | TypeError:run_source_ceiling_oracle() takes from 3 to 4 positional arguments but 6 were given | `unetClipExperimentsSeptember/06_source_only_runs/clip_b128_qd2_R1_A2.json` |
| clip_b128_qd2_R1_A3 | error | TypeError:run_source_ceiling_oracle() takes from 3 to 4 positional arguments but 6 were given | `unetClipExperimentsSeptember/06_source_only_runs/clip_b128_qd2_R1_A3.json` |
| clip_b128_qd2_R2_A2 | error | TypeError:run_source_ceiling_oracle() takes from 3 to 4 positional arguments but 6 were given | `unetClipExperimentsSeptember/06_source_only_runs/clip_b128_qd2_R2_A2.json` |
| clip_b128_qd2_R2_A3 | error | TypeError:run_source_ceiling_oracle() takes from 3 to 4 positional arguments but 6 were given | `unetClipExperimentsSeptember/06_source_only_runs/clip_b128_qd2_R2_A3.json` |
| clip_b128_qd2_R3_A2 | error | TypeError:run_source_ceiling_oracle() takes from 3 to 4 positional arguments but 6 were given | `unetClipExperimentsSeptember/06_source_only_runs/clip_b128_qd2_R3_A2.json` |
| clip_b128_qd4_R1_A2 | error | TypeError:run_source_ceiling_oracle() takes from 3 to 4 positional arguments but 6 were given | `unetClipExperimentsSeptember/06_source_only_runs/clip_b128_qd4_R1_A2.json` |
| clip_b128_qd4_R1_A3 | error | TypeError:run_source_ceiling_oracle() takes from 3 to 4 positional arguments but 6 were given | `unetClipExperimentsSeptember/06_source_only_runs/clip_b128_qd4_R1_A3.json` |
| clip_b128_qd4_R2_A2 | error | TypeError:run_source_ceiling_oracle() takes from 3 to 4 positional arguments but 6 were given | `unetClipExperimentsSeptember/06_source_only_runs/clip_b128_qd4_R2_A2.json` |
| clip_b128_qd4_R2_A3 | error | TypeError:run_source_ceiling_oracle() takes from 3 to 4 positional arguments but 6 were given | `unetClipExperimentsSeptember/06_source_only_runs/clip_b128_qd4_R2_A3.json` |
| clip_b128_qd4_R3_A2 | error | TypeError:run_source_ceiling_oracle() takes from 3 to 4 positional arguments but 6 were given | `unetClipExperimentsSeptember/06_source_only_runs/clip_b128_qd4_R3_A2.json` |
| clip_b128_qd8_R1_A2 | error | TypeError:run_source_ceiling_oracle() takes from 3 to 4 positional arguments but 6 were given | `unetClipExperimentsSeptember/06_source_only_runs/clip_b128_qd8_R1_A2.json` |
| clip_b128_qd8_R1_A3 | error | TypeError:run_source_ceiling_oracle() takes from 3 to 4 positional arguments but 6 were given | `unetClipExperimentsSeptember/06_source_only_runs/clip_b128_qd8_R1_A3.json` |
| clip_b128_qd8_R2_A2 | error | TypeError:run_source_ceiling_oracle() takes from 3 to 4 positional arguments but 6 were given | `unetClipExperimentsSeptember/06_source_only_runs/clip_b128_qd8_R2_A2.json` |
| clip_b128_qd8_R2_A3 | error | TypeError:run_source_ceiling_oracle() takes from 3 to 4 positional arguments but 6 were given | `unetClipExperimentsSeptember/06_source_only_runs/clip_b128_qd8_R2_A3.json` |
| clip_b128_qd8_R3_A2 | error | TypeError:run_source_ceiling_oracle() takes from 3 to 4 positional arguments but 6 were given | `unetClipExperimentsSeptember/06_source_only_runs/clip_b128_qd8_R3_A2.json` |
| clip_b256_qd1_R1_A2 | error | TypeError:run_source_ceiling_oracle() takes from 3 to 4 positional arguments but 6 were given | `unetClipExperimentsSeptember/06_source_only_runs/clip_b256_qd1_R1_A2.json` |
| clip_b256_qd1_R1_A3 | error | TypeError:run_source_ceiling_oracle() takes from 3 to 4 positional arguments but 6 were given | `unetClipExperimentsSeptember/06_source_only_runs/clip_b256_qd1_R1_A3.json` |
| clip_b256_qd1_R2_A2 | error | TypeError:run_source_ceiling_oracle() takes from 3 to 4 positional arguments but 6 were given | `unetClipExperimentsSeptember/06_source_only_runs/clip_b256_qd1_R2_A2.json` |
| clip_b256_qd1_R2_A3 | error | TypeError:run_source_ceiling_oracle() takes from 3 to 4 positional arguments but 6 were given | `unetClipExperimentsSeptember/06_source_only_runs/clip_b256_qd1_R2_A3.json` |
| clip_b256_qd1_R3_A2 | error | TypeError:run_source_ceiling_oracle() takes from 3 to 4 positional arguments but 6 were given | `unetClipExperimentsSeptember/06_source_only_runs/clip_b256_qd1_R3_A2.json` |
| clip_b256_qd2_R1_A2 | error | TypeError:run_source_ceiling_oracle() takes from 3 to 4 positional arguments but 6 were given | `unetClipExperimentsSeptember/06_source_only_runs/clip_b256_qd2_R1_A2.json` |
| clip_b256_qd2_R1_A3 | error | TypeError:run_source_ceiling_oracle() takes from 3 to 4 positional arguments but 6 were given | `unetClipExperimentsSeptember/06_source_only_runs/clip_b256_qd2_R1_A3.json` |
| clip_b256_qd2_R2_A2 | error | TypeError:run_source_ceiling_oracle() takes from 3 to 4 positional arguments but 6 were given | `unetClipExperimentsSeptember/06_source_only_runs/clip_b256_qd2_R2_A2.json` |
| clip_b256_qd2_R2_A3 | error | TypeError:run_source_ceiling_oracle() takes from 3 to 4 positional arguments but 6 were given | `unetClipExperimentsSeptember/06_source_only_runs/clip_b256_qd2_R2_A3.json` |
| clip_b256_qd2_R3_A2 | error | TypeError:run_source_ceiling_oracle() takes from 3 to 4 positional arguments but 6 were given | `unetClipExperimentsSeptember/06_source_only_runs/clip_b256_qd2_R3_A2.json` |
| clip_b256_qd4_R1_A2 | error | TypeError:run_source_ceiling_oracle() takes from 3 to 4 positional arguments but 6 were given | `unetClipExperimentsSeptember/06_source_only_runs/clip_b256_qd4_R1_A2.json` |
| clip_b256_qd4_R1_A3 | error | TypeError:run_source_ceiling_oracle() takes from 3 to 4 positional arguments but 6 were given | `unetClipExperimentsSeptember/06_source_only_runs/clip_b256_qd4_R1_A3.json` |
| clip_b256_qd4_R2_A2 | error | TypeError:run_source_ceiling_oracle() takes from 3 to 4 positional arguments but 6 were given | `unetClipExperimentsSeptember/06_source_only_runs/clip_b256_qd4_R2_A2.json` |
| clip_b256_qd4_R2_A3 | error | TypeError:run_source_ceiling_oracle() takes from 3 to 4 positional arguments but 6 were given | `unetClipExperimentsSeptember/06_source_only_runs/clip_b256_qd4_R2_A3.json` |
| clip_b256_qd4_R3_A2 | error | TypeError:run_source_ceiling_oracle() takes from 3 to 4 positional arguments but 6 were given | `unetClipExperimentsSeptember/06_source_only_runs/clip_b256_qd4_R3_A2.json` |
| clip_b256_qd8_R1_A2 | error | TypeError:run_source_ceiling_oracle() takes from 3 to 4 positional arguments but 6 were given | `unetClipExperimentsSeptember/06_source_only_runs/clip_b256_qd8_R1_A2.json` |
| clip_b256_qd8_R1_A3 | error | TypeError:run_source_ceiling_oracle() takes from 3 to 4 positional arguments but 6 were given | `unetClipExperimentsSeptember/06_source_only_runs/clip_b256_qd8_R1_A3.json` |
| clip_b256_qd8_R2_A2 | error | TypeError:run_source_ceiling_oracle() takes from 3 to 4 positional arguments but 6 were given | `unetClipExperimentsSeptember/06_source_only_runs/clip_b256_qd8_R2_A2.json` |
| clip_b256_qd8_R2_A3 | error | TypeError:run_source_ceiling_oracle() takes from 3 to 4 positional arguments but 6 were given | `unetClipExperimentsSeptember/06_source_only_runs/clip_b256_qd8_R2_A3.json` |
| clip_b256_qd8_R3_A2 | error | TypeError:run_source_ceiling_oracle() takes from 3 to 4 positional arguments but 6 were given | `unetClipExperimentsSeptember/06_source_only_runs/clip_b256_qd8_R3_A2.json` |
| clip_b32_qd1_R1_A2 | error | TypeError:run_source_ceiling_oracle() takes from 3 to 4 positional arguments but 6 were given | `unetClipExperimentsSeptember/06_source_only_runs/clip_b32_qd1_R1_A2.json` |
| clip_b32_qd1_R1_A3 | error | TypeError:run_source_ceiling_oracle() takes from 3 to 4 positional arguments but 6 were given | `unetClipExperimentsSeptember/06_source_only_runs/clip_b32_qd1_R1_A3.json` |
| clip_b32_qd1_R2_A2 | error | TypeError:run_source_ceiling_oracle() takes from 3 to 4 positional arguments but 6 were given | `unetClipExperimentsSeptember/06_source_only_runs/clip_b32_qd1_R2_A2.json` |
| clip_b32_qd1_R2_A3 | error | TypeError:run_source_ceiling_oracle() takes from 3 to 4 positional arguments but 6 were given | `unetClipExperimentsSeptember/06_source_only_runs/clip_b32_qd1_R2_A3.json` |
| clip_b32_qd1_R3_A2 | error | TypeError:run_source_ceiling_oracle() takes from 3 to 4 positional arguments but 6 were given | `unetClipExperimentsSeptember/06_source_only_runs/clip_b32_qd1_R3_A2.json` |
| clip_b32_qd1_R3_A3 | error | TypeError:run_source_ceiling_oracle() takes from 3 to 4 positional arguments but 6 were given | `unetClipExperimentsSeptember/06_source_only_runs/clip_b32_qd1_R3_A3.json` |
| clip_b32_qd1_R4_A2 | error | TypeError:run_source_ceiling_oracle() takes from 3 to 4 positional arguments but 6 were given | `unetClipExperimentsSeptember/06_source_only_runs/clip_b32_qd1_R4_A2.json` |
| clip_b32_qd2_R1_A2 | error | TypeError:run_source_ceiling_oracle() takes from 3 to 4 positional arguments but 6 were given | `unetClipExperimentsSeptember/06_source_only_runs/clip_b32_qd2_R1_A2.json` |
| clip_b32_qd2_R1_A3 | error | TypeError:run_source_ceiling_oracle() takes from 3 to 4 positional arguments but 6 were given | `unetClipExperimentsSeptember/06_source_only_runs/clip_b32_qd2_R1_A3.json` |
| clip_b32_qd2_R2_A2 | error | TypeError:run_source_ceiling_oracle() takes from 3 to 4 positional arguments but 6 were given | `unetClipExperimentsSeptember/06_source_only_runs/clip_b32_qd2_R2_A2.json` |
| clip_b32_qd2_R2_A3 | error | TypeError:run_source_ceiling_oracle() takes from 3 to 4 positional arguments but 6 were given | `unetClipExperimentsSeptember/06_source_only_runs/clip_b32_qd2_R2_A3.json` |
| clip_b32_qd2_R3_A2 | error | TypeError:run_source_ceiling_oracle() takes from 3 to 4 positional arguments but 6 were given | `unetClipExperimentsSeptember/06_source_only_runs/clip_b32_qd2_R3_A2.json` |
| clip_b32_qd2_R3_A3 | error | TypeError:run_source_ceiling_oracle() takes from 3 to 4 positional arguments but 6 were given | `unetClipExperimentsSeptember/06_source_only_runs/clip_b32_qd2_R3_A3.json` |
| clip_b32_qd2_R4_A2 | error | TypeError:run_source_ceiling_oracle() takes from 3 to 4 positional arguments but 6 were given | `unetClipExperimentsSeptember/06_source_only_runs/clip_b32_qd2_R4_A2.json` |
| clip_b32_qd4_R1_A2 | error | TypeError:run_source_ceiling_oracle() takes from 3 to 4 positional arguments but 6 were given | `unetClipExperimentsSeptember/06_source_only_runs/clip_b32_qd4_R1_A2.json` |
| clip_b32_qd4_R1_A3 | error | TypeError:run_source_ceiling_oracle() takes from 3 to 4 positional arguments but 6 were given | `unetClipExperimentsSeptember/06_source_only_runs/clip_b32_qd4_R1_A3.json` |
| clip_b32_qd4_R2_A2 | error | TypeError:run_source_ceiling_oracle() takes from 3 to 4 positional arguments but 6 were given | `unetClipExperimentsSeptember/06_source_only_runs/clip_b32_qd4_R2_A2.json` |
| clip_b32_qd4_R2_A3 | error | TypeError:run_source_ceiling_oracle() takes from 3 to 4 positional arguments but 6 were given | `unetClipExperimentsSeptember/06_source_only_runs/clip_b32_qd4_R2_A3.json` |
| clip_b32_qd4_R3_A2 | error | TypeError:run_source_ceiling_oracle() takes from 3 to 4 positional arguments but 6 were given | `unetClipExperimentsSeptember/06_source_only_runs/clip_b32_qd4_R3_A2.json` |
| clip_b32_qd4_R3_A3 | error | TypeError:run_source_ceiling_oracle() takes from 3 to 4 positional arguments but 6 were given | `unetClipExperimentsSeptember/06_source_only_runs/clip_b32_qd4_R3_A3.json` |
| clip_b32_qd4_R4_A2 | error | TypeError:run_source_ceiling_oracle() takes from 3 to 4 positional arguments but 6 were given | `unetClipExperimentsSeptember/06_source_only_runs/clip_b32_qd4_R4_A2.json` |
| clip_b32_qd8_R1_A2 | error | TypeError:run_source_ceiling_oracle() takes from 3 to 4 positional arguments but 6 were given | `unetClipExperimentsSeptember/06_source_only_runs/clip_b32_qd8_R1_A2.json` |
| clip_b32_qd8_R1_A3 | error | TypeError:run_source_ceiling_oracle() takes from 3 to 4 positional arguments but 6 were given | `unetClipExperimentsSeptember/06_source_only_runs/clip_b32_qd8_R1_A3.json` |
| clip_b32_qd8_R2_A2 | error | TypeError:run_source_ceiling_oracle() takes from 3 to 4 positional arguments but 6 were given | `unetClipExperimentsSeptember/06_source_only_runs/clip_b32_qd8_R2_A2.json` |
| clip_b32_qd8_R2_A3 | error | TypeError:run_source_ceiling_oracle() takes from 3 to 4 positional arguments but 6 were given | `unetClipExperimentsSeptember/06_source_only_runs/clip_b32_qd8_R2_A3.json` |
| clip_b32_qd8_R3_A2 | error | TypeError:run_source_ceiling_oracle() takes from 3 to 4 positional arguments but 6 were given | `unetClipExperimentsSeptember/06_source_only_runs/clip_b32_qd8_R3_A2.json` |
| clip_b32_qd8_R3_A3 | error | TypeError:run_source_ceiling_oracle() takes from 3 to 4 positional arguments but 6 were given | `unetClipExperimentsSeptember/06_source_only_runs/clip_b32_qd8_R3_A3.json` |
| clip_b32_qd8_R4_A2 | error | TypeError:run_source_ceiling_oracle() takes from 3 to 4 positional arguments but 6 were given | `unetClipExperimentsSeptember/06_source_only_runs/clip_b32_qd8_R4_A2.json` |
| clip_b64_qd1_R1_A2 | error | TypeError:run_source_ceiling_oracle() takes from 3 to 4 positional arguments but 6 were given | `unetClipExperimentsSeptember/06_source_only_runs/clip_b64_qd1_R1_A2.json` |
| clip_b64_qd1_R1_A3 | error | TypeError:run_source_ceiling_oracle() takes from 3 to 4 positional arguments but 6 were given | `unetClipExperimentsSeptember/06_source_only_runs/clip_b64_qd1_R1_A3.json` |
| clip_b64_qd1_R2_A2 | error | TypeError:run_source_ceiling_oracle() takes from 3 to 4 positional arguments but 6 were given | `unetClipExperimentsSeptember/06_source_only_runs/clip_b64_qd1_R2_A2.json` |
| clip_b64_qd1_R2_A3 | error | TypeError:run_source_ceiling_oracle() takes from 3 to 4 positional arguments but 6 were given | `unetClipExperimentsSeptember/06_source_only_runs/clip_b64_qd1_R2_A3.json` |
| clip_b64_qd1_R3_A2 | error | TypeError:run_source_ceiling_oracle() takes from 3 to 4 positional arguments but 6 were given | `unetClipExperimentsSeptember/06_source_only_runs/clip_b64_qd1_R3_A2.json` |
| clip_b64_qd1_R3_A3 | error | TypeError:run_source_ceiling_oracle() takes from 3 to 4 positional arguments but 6 were given | `unetClipExperimentsSeptember/06_source_only_runs/clip_b64_qd1_R3_A3.json` |
| clip_b64_qd1_R4_A2 | error | TypeError:run_source_ceiling_oracle() takes from 3 to 4 positional arguments but 6 were given | `unetClipExperimentsSeptember/06_source_only_runs/clip_b64_qd1_R4_A2.json` |
| clip_b64_qd2_R1_A2 | error | TypeError:run_source_ceiling_oracle() takes from 3 to 4 positional arguments but 6 were given | `unetClipExperimentsSeptember/06_source_only_runs/clip_b64_qd2_R1_A2.json` |
| clip_b64_qd2_R1_A3 | error | TypeError:run_source_ceiling_oracle() takes from 3 to 4 positional arguments but 6 were given | `unetClipExperimentsSeptember/06_source_only_runs/clip_b64_qd2_R1_A3.json` |
| clip_b64_qd2_R2_A2 | error | TypeError:run_source_ceiling_oracle() takes from 3 to 4 positional arguments but 6 were given | `unetClipExperimentsSeptember/06_source_only_runs/clip_b64_qd2_R2_A2.json` |
| clip_b64_qd2_R2_A3 | error | TypeError:run_source_ceiling_oracle() takes from 3 to 4 positional arguments but 6 were given | `unetClipExperimentsSeptember/06_source_only_runs/clip_b64_qd2_R2_A3.json` |
| clip_b64_qd2_R3_A2 | error | TypeError:run_source_ceiling_oracle() takes from 3 to 4 positional arguments but 6 were given | `unetClipExperimentsSeptember/06_source_only_runs/clip_b64_qd2_R3_A2.json` |
| clip_b64_qd2_R4_A2 | error | TypeError:run_source_ceiling_oracle() takes from 3 to 4 positional arguments but 6 were given | `unetClipExperimentsSeptember/06_source_only_runs/clip_b64_qd2_R4_A2.json` |
| clip_b64_qd4_R1_A2 | error | TypeError:run_source_ceiling_oracle() takes from 3 to 4 positional arguments but 6 were given | `unetClipExperimentsSeptember/06_source_only_runs/clip_b64_qd4_R1_A2.json` |
| clip_b64_qd4_R1_A3 | error | TypeError:run_source_ceiling_oracle() takes from 3 to 4 positional arguments but 6 were given | `unetClipExperimentsSeptember/06_source_only_runs/clip_b64_qd4_R1_A3.json` |
| clip_b64_qd4_R2_A2 | error | TypeError:run_source_ceiling_oracle() takes from 3 to 4 positional arguments but 6 were given | `unetClipExperimentsSeptember/06_source_only_runs/clip_b64_qd4_R2_A2.json` |
| clip_b64_qd4_R2_A3 | error | TypeError:run_source_ceiling_oracle() takes from 3 to 4 positional arguments but 6 were given | `unetClipExperimentsSeptember/06_source_only_runs/clip_b64_qd4_R2_A3.json` |
| clip_b64_qd4_R3_A2 | error | TypeError:run_source_ceiling_oracle() takes from 3 to 4 positional arguments but 6 were given | `unetClipExperimentsSeptember/06_source_only_runs/clip_b64_qd4_R3_A2.json` |
| clip_b64_qd4_R4_A2 | error | TypeError:run_source_ceiling_oracle() takes from 3 to 4 positional arguments but 6 were given | `unetClipExperimentsSeptember/06_source_only_runs/clip_b64_qd4_R4_A2.json` |
| clip_b64_qd8_R1_A2 | error | TypeError:run_source_ceiling_oracle() takes from 3 to 4 positional arguments but 6 were given | `unetClipExperimentsSeptember/06_source_only_runs/clip_b64_qd8_R1_A2.json` |
| clip_b64_qd8_R1_A3 | error | TypeError:run_source_ceiling_oracle() takes from 3 to 4 positional arguments but 6 were given | `unetClipExperimentsSeptember/06_source_only_runs/clip_b64_qd8_R1_A3.json` |
| clip_b64_qd8_R2_A2 | error | TypeError:run_source_ceiling_oracle() takes from 3 to 4 positional arguments but 6 were given | `unetClipExperimentsSeptember/06_source_only_runs/clip_b64_qd8_R2_A2.json` |
| clip_b64_qd8_R2_A3 | error | TypeError:run_source_ceiling_oracle() takes from 3 to 4 positional arguments but 6 were given | `unetClipExperimentsSeptember/06_source_only_runs/clip_b64_qd8_R2_A3.json` |
| clip_b64_qd8_R3_A2 | error | TypeError:run_source_ceiling_oracle() takes from 3 to 4 positional arguments but 6 were given | `unetClipExperimentsSeptember/06_source_only_runs/clip_b64_qd8_R3_A2.json` |
| unet_b128_qd1_R1_A2 | error | TypeError:run_source_ceiling_oracle() takes from 3 to 4 positional arguments but 6 were given | `unetClipExperimentsSeptember/06_source_only_runs/unet_b128_qd1_R1_A2.json` |
| unet_b128_qd1_R1_A3 | error | TypeError:run_source_ceiling_oracle() takes from 3 to 4 positional arguments but 6 were given | `unetClipExperimentsSeptember/06_source_only_runs/unet_b128_qd1_R1_A3.json` |
| unet_b128_qd1_R2_A2 | error | TypeError:run_source_ceiling_oracle() takes from 3 to 4 positional arguments but 6 were given | `unetClipExperimentsSeptember/06_source_only_runs/unet_b128_qd1_R2_A2.json` |
| unet_b128_qd1_R2_A3 | error | TypeError:run_source_ceiling_oracle() takes from 3 to 4 positional arguments but 6 were given | `unetClipExperimentsSeptember/06_source_only_runs/unet_b128_qd1_R2_A3.json` |
| unet_b128_qd1_R3_A2 | error | TypeError:run_source_ceiling_oracle() takes from 3 to 4 positional arguments but 6 were given | `unetClipExperimentsSeptember/06_source_only_runs/unet_b128_qd1_R3_A2.json` |
| unet_b128_qd2_R1_A2 | error | TypeError:run_source_ceiling_oracle() takes from 3 to 4 positional arguments but 6 were given | `unetClipExperimentsSeptember/06_source_only_runs/unet_b128_qd2_R1_A2.json` |
| unet_b128_qd2_R1_A3 | error | TypeError:run_source_ceiling_oracle() takes from 3 to 4 positional arguments but 6 were given | `unetClipExperimentsSeptember/06_source_only_runs/unet_b128_qd2_R1_A3.json` |
| unet_b128_qd2_R2_A2 | error | TypeError:run_source_ceiling_oracle() takes from 3 to 4 positional arguments but 6 were given | `unetClipExperimentsSeptember/06_source_only_runs/unet_b128_qd2_R2_A2.json` |
| unet_b128_qd2_R2_A3 | error | TypeError:run_source_ceiling_oracle() takes from 3 to 4 positional arguments but 6 were given | `unetClipExperimentsSeptember/06_source_only_runs/unet_b128_qd2_R2_A3.json` |
| unet_b128_qd2_R3_A2 | error | TypeError:run_source_ceiling_oracle() takes from 3 to 4 positional arguments but 6 were given | `unetClipExperimentsSeptember/06_source_only_runs/unet_b128_qd2_R3_A2.json` |
| unet_b128_qd4_R1_A2 | error | TypeError:run_source_ceiling_oracle() takes from 3 to 4 positional arguments but 6 were given | `unetClipExperimentsSeptember/06_source_only_runs/unet_b128_qd4_R1_A2.json` |
| unet_b128_qd4_R1_A3 | error | TypeError:run_source_ceiling_oracle() takes from 3 to 4 positional arguments but 6 were given | `unetClipExperimentsSeptember/06_source_only_runs/unet_b128_qd4_R1_A3.json` |
| unet_b128_qd4_R2_A2 | error | TypeError:run_source_ceiling_oracle() takes from 3 to 4 positional arguments but 6 were given | `unetClipExperimentsSeptember/06_source_only_runs/unet_b128_qd4_R2_A2.json` |
| unet_b128_qd4_R2_A3 | error | TypeError:run_source_ceiling_oracle() takes from 3 to 4 positional arguments but 6 were given | `unetClipExperimentsSeptember/06_source_only_runs/unet_b128_qd4_R2_A3.json` |
| unet_b128_qd4_R3_A2 | error | TypeError:run_source_ceiling_oracle() takes from 3 to 4 positional arguments but 6 were given | `unetClipExperimentsSeptember/06_source_only_runs/unet_b128_qd4_R3_A2.json` |
| unet_b128_qd8_R1_A2 | error | TypeError:run_source_ceiling_oracle() takes from 3 to 4 positional arguments but 6 were given | `unetClipExperimentsSeptember/06_source_only_runs/unet_b128_qd8_R1_A2.json` |
| unet_b128_qd8_R1_A3 | error | TypeError:run_source_ceiling_oracle() takes from 3 to 4 positional arguments but 6 were given | `unetClipExperimentsSeptember/06_source_only_runs/unet_b128_qd8_R1_A3.json` |
| unet_b128_qd8_R2_A2 | error | TypeError:run_source_ceiling_oracle() takes from 3 to 4 positional arguments but 6 were given | `unetClipExperimentsSeptember/06_source_only_runs/unet_b128_qd8_R2_A2.json` |
| unet_b128_qd8_R2_A3 | error | TypeError:run_source_ceiling_oracle() takes from 3 to 4 positional arguments but 6 were given | `unetClipExperimentsSeptember/06_source_only_runs/unet_b128_qd8_R2_A3.json` |
| unet_b128_qd8_R3_A2 | error | TypeError:run_source_ceiling_oracle() takes from 3 to 4 positional arguments but 6 were given | `unetClipExperimentsSeptember/06_source_only_runs/unet_b128_qd8_R3_A2.json` |
| unet_b256_qd1_R1_A2 | error | TypeError:run_source_ceiling_oracle() takes from 3 to 4 positional arguments but 6 were given | `unetClipExperimentsSeptember/06_source_only_runs/unet_b256_qd1_R1_A2.json` |
| unet_b256_qd1_R1_A3 | error | TypeError:run_source_ceiling_oracle() takes from 3 to 4 positional arguments but 6 were given | `unetClipExperimentsSeptember/06_source_only_runs/unet_b256_qd1_R1_A3.json` |
| unet_b256_qd1_R2_A2 | error | TypeError:run_source_ceiling_oracle() takes from 3 to 4 positional arguments but 6 were given | `unetClipExperimentsSeptember/06_source_only_runs/unet_b256_qd1_R2_A2.json` |
| unet_b256_qd1_R2_A3 | error | TypeError:run_source_ceiling_oracle() takes from 3 to 4 positional arguments but 6 were given | `unetClipExperimentsSeptember/06_source_only_runs/unet_b256_qd1_R2_A3.json` |
| unet_b256_qd1_R3_A2 | error | TypeError:run_source_ceiling_oracle() takes from 3 to 4 positional arguments but 6 were given | `unetClipExperimentsSeptember/06_source_only_runs/unet_b256_qd1_R3_A2.json` |
| unet_b256_qd2_R1_A2 | error | TypeError:run_source_ceiling_oracle() takes from 3 to 4 positional arguments but 6 were given | `unetClipExperimentsSeptember/06_source_only_runs/unet_b256_qd2_R1_A2.json` |
| unet_b256_qd2_R1_A3 | error | TypeError:run_source_ceiling_oracle() takes from 3 to 4 positional arguments but 6 were given | `unetClipExperimentsSeptember/06_source_only_runs/unet_b256_qd2_R1_A3.json` |
| unet_b256_qd2_R2_A2 | error | TypeError:run_source_ceiling_oracle() takes from 3 to 4 positional arguments but 6 were given | `unetClipExperimentsSeptember/06_source_only_runs/unet_b256_qd2_R2_A2.json` |
| unet_b256_qd2_R2_A3 | error | TypeError:run_source_ceiling_oracle() takes from 3 to 4 positional arguments but 6 were given | `unetClipExperimentsSeptember/06_source_only_runs/unet_b256_qd2_R2_A3.json` |
| unet_b256_qd2_R3_A2 | error | TypeError:run_source_ceiling_oracle() takes from 3 to 4 positional arguments but 6 were given | `unetClipExperimentsSeptember/06_source_only_runs/unet_b256_qd2_R3_A2.json` |
| unet_b256_qd4_R1_A2 | error | TypeError:run_source_ceiling_oracle() takes from 3 to 4 positional arguments but 6 were given | `unetClipExperimentsSeptember/06_source_only_runs/unet_b256_qd4_R1_A2.json` |
| unet_b256_qd4_R1_A3 | error | TypeError:run_source_ceiling_oracle() takes from 3 to 4 positional arguments but 6 were given | `unetClipExperimentsSeptember/06_source_only_runs/unet_b256_qd4_R1_A3.json` |
| unet_b256_qd4_R2_A2 | error | TypeError:run_source_ceiling_oracle() takes from 3 to 4 positional arguments but 6 were given | `unetClipExperimentsSeptember/06_source_only_runs/unet_b256_qd4_R2_A2.json` |
| unet_b256_qd4_R2_A3 | error | TypeError:run_source_ceiling_oracle() takes from 3 to 4 positional arguments but 6 were given | `unetClipExperimentsSeptember/06_source_only_runs/unet_b256_qd4_R2_A3.json` |
| unet_b256_qd4_R3_A2 | error | TypeError:run_source_ceiling_oracle() takes from 3 to 4 positional arguments but 6 were given | `unetClipExperimentsSeptember/06_source_only_runs/unet_b256_qd4_R3_A2.json` |
| unet_b256_qd8_R1_A2 | error | TypeError:run_source_ceiling_oracle() takes from 3 to 4 positional arguments but 6 were given | `unetClipExperimentsSeptember/06_source_only_runs/unet_b256_qd8_R1_A2.json` |
| unet_b256_qd8_R1_A3 | error | TypeError:run_source_ceiling_oracle() takes from 3 to 4 positional arguments but 6 were given | `unetClipExperimentsSeptember/06_source_only_runs/unet_b256_qd8_R1_A3.json` |
| unet_b256_qd8_R2_A2 | error | TypeError:run_source_ceiling_oracle() takes from 3 to 4 positional arguments but 6 were given | `unetClipExperimentsSeptember/06_source_only_runs/unet_b256_qd8_R2_A2.json` |
| unet_b256_qd8_R2_A3 | error | TypeError:run_source_ceiling_oracle() takes from 3 to 4 positional arguments but 6 were given | `unetClipExperimentsSeptember/06_source_only_runs/unet_b256_qd8_R2_A3.json` |
| unet_b256_qd8_R3_A2 | error | TypeError:run_source_ceiling_oracle() takes from 3 to 4 positional arguments but 6 were given | `unetClipExperimentsSeptember/06_source_only_runs/unet_b256_qd8_R3_A2.json` |
| unet_b32_qd1_R1_A2 | error | TypeError:run_source_ceiling_oracle() takes from 3 to 4 positional arguments but 6 were given | `unetClipExperimentsSeptember/06_source_only_runs/unet_b32_qd1_R1_A2.json` |
| unet_b32_qd1_R1_A3 | error | TypeError:run_source_ceiling_oracle() takes from 3 to 4 positional arguments but 6 were given | `unetClipExperimentsSeptember/06_source_only_runs/unet_b32_qd1_R1_A3.json` |
| unet_b32_qd1_R2_A2 | error | TypeError:run_source_ceiling_oracle() takes from 3 to 4 positional arguments but 6 were given | `unetClipExperimentsSeptember/06_source_only_runs/unet_b32_qd1_R2_A2.json` |
| unet_b32_qd1_R2_A3 | error | TypeError:run_source_ceiling_oracle() takes from 3 to 4 positional arguments but 6 were given | `unetClipExperimentsSeptember/06_source_only_runs/unet_b32_qd1_R2_A3.json` |
| unet_b32_qd1_R3_A2 | error | TypeError:run_source_ceiling_oracle() takes from 3 to 4 positional arguments but 6 were given | `unetClipExperimentsSeptember/06_source_only_runs/unet_b32_qd1_R3_A2.json` |
| unet_b32_qd1_R3_A3 | error | TypeError:run_source_ceiling_oracle() takes from 3 to 4 positional arguments but 6 were given | `unetClipExperimentsSeptember/06_source_only_runs/unet_b32_qd1_R3_A3.json` |
| unet_b32_qd1_R4_A2 | error | TypeError:run_source_ceiling_oracle() takes from 3 to 4 positional arguments but 6 were given | `unetClipExperimentsSeptember/06_source_only_runs/unet_b32_qd1_R4_A2.json` |
| unet_b32_qd2_R1_A2 | error | TypeError:run_source_ceiling_oracle() takes from 3 to 4 positional arguments but 6 were given | `unetClipExperimentsSeptember/06_source_only_runs/unet_b32_qd2_R1_A2.json` |
| unet_b32_qd2_R1_A3 | error | TypeError:run_source_ceiling_oracle() takes from 3 to 4 positional arguments but 6 were given | `unetClipExperimentsSeptember/06_source_only_runs/unet_b32_qd2_R1_A3.json` |
| unet_b32_qd2_R2_A2 | error | TypeError:run_source_ceiling_oracle() takes from 3 to 4 positional arguments but 6 were given | `unetClipExperimentsSeptember/06_source_only_runs/unet_b32_qd2_R2_A2.json` |
| unet_b32_qd2_R2_A3 | error | TypeError:run_source_ceiling_oracle() takes from 3 to 4 positional arguments but 6 were given | `unetClipExperimentsSeptember/06_source_only_runs/unet_b32_qd2_R2_A3.json` |
| unet_b32_qd2_R3_A2 | error | TypeError:run_source_ceiling_oracle() takes from 3 to 4 positional arguments but 6 were given | `unetClipExperimentsSeptember/06_source_only_runs/unet_b32_qd2_R3_A2.json` |
| unet_b32_qd2_R3_A3 | error | TypeError:run_source_ceiling_oracle() takes from 3 to 4 positional arguments but 6 were given | `unetClipExperimentsSeptember/06_source_only_runs/unet_b32_qd2_R3_A3.json` |
| unet_b32_qd2_R4_A2 | error | TypeError:run_source_ceiling_oracle() takes from 3 to 4 positional arguments but 6 were given | `unetClipExperimentsSeptember/06_source_only_runs/unet_b32_qd2_R4_A2.json` |
| unet_b32_qd4_R1_A2 | error | TypeError:run_source_ceiling_oracle() takes from 3 to 4 positional arguments but 6 were given | `unetClipExperimentsSeptember/06_source_only_runs/unet_b32_qd4_R1_A2.json` |
| unet_b32_qd4_R1_A3 | error | TypeError:run_source_ceiling_oracle() takes from 3 to 4 positional arguments but 6 were given | `unetClipExperimentsSeptember/06_source_only_runs/unet_b32_qd4_R1_A3.json` |
| unet_b32_qd4_R2_A2 | error | TypeError:run_source_ceiling_oracle() takes from 3 to 4 positional arguments but 6 were given | `unetClipExperimentsSeptember/06_source_only_runs/unet_b32_qd4_R2_A2.json` |
| unet_b32_qd4_R2_A3 | error | TypeError:run_source_ceiling_oracle() takes from 3 to 4 positional arguments but 6 were given | `unetClipExperimentsSeptember/06_source_only_runs/unet_b32_qd4_R2_A3.json` |
| unet_b32_qd4_R3_A2 | error | TypeError:run_source_ceiling_oracle() takes from 3 to 4 positional arguments but 6 were given | `unetClipExperimentsSeptember/06_source_only_runs/unet_b32_qd4_R3_A2.json` |
| unet_b32_qd4_R3_A3 | error | TypeError:run_source_ceiling_oracle() takes from 3 to 4 positional arguments but 6 were given | `unetClipExperimentsSeptember/06_source_only_runs/unet_b32_qd4_R3_A3.json` |
| unet_b32_qd4_R4_A2 | error | TypeError:run_source_ceiling_oracle() takes from 3 to 4 positional arguments but 6 were given | `unetClipExperimentsSeptember/06_source_only_runs/unet_b32_qd4_R4_A2.json` |
| unet_b32_qd8_R1_A2 | error | TypeError:run_source_ceiling_oracle() takes from 3 to 4 positional arguments but 6 were given | `unetClipExperimentsSeptember/06_source_only_runs/unet_b32_qd8_R1_A2.json` |
| unet_b32_qd8_R1_A3 | error | TypeError:run_source_ceiling_oracle() takes from 3 to 4 positional arguments but 6 were given | `unetClipExperimentsSeptember/06_source_only_runs/unet_b32_qd8_R1_A3.json` |
| unet_b32_qd8_R2_A2 | error | TypeError:run_source_ceiling_oracle() takes from 3 to 4 positional arguments but 6 were given | `unetClipExperimentsSeptember/06_source_only_runs/unet_b32_qd8_R2_A2.json` |
| unet_b32_qd8_R2_A3 | error | TypeError:run_source_ceiling_oracle() takes from 3 to 4 positional arguments but 6 were given | `unetClipExperimentsSeptember/06_source_only_runs/unet_b32_qd8_R2_A3.json` |
| unet_b32_qd8_R3_A2 | error | TypeError:run_source_ceiling_oracle() takes from 3 to 4 positional arguments but 6 were given | `unetClipExperimentsSeptember/06_source_only_runs/unet_b32_qd8_R3_A2.json` |
| unet_b32_qd8_R3_A3 | error | TypeError:run_source_ceiling_oracle() takes from 3 to 4 positional arguments but 6 were given | `unetClipExperimentsSeptember/06_source_only_runs/unet_b32_qd8_R3_A3.json` |
| unet_b32_qd8_R4_A2 | error | TypeError:run_source_ceiling_oracle() takes from 3 to 4 positional arguments but 6 were given | `unetClipExperimentsSeptember/06_source_only_runs/unet_b32_qd8_R4_A2.json` |
| unet_b64_qd1_R1_A2 | error | TypeError:run_source_ceiling_oracle() takes from 3 to 4 positional arguments but 6 were given | `unetClipExperimentsSeptember/06_source_only_runs/unet_b64_qd1_R1_A2.json` |
| unet_b64_qd1_R1_A3 | error | TypeError:run_source_ceiling_oracle() takes from 3 to 4 positional arguments but 6 were given | `unetClipExperimentsSeptember/06_source_only_runs/unet_b64_qd1_R1_A3.json` |
| unet_b64_qd1_R2_A2 | error | TypeError:run_source_ceiling_oracle() takes from 3 to 4 positional arguments but 6 were given | `unetClipExperimentsSeptember/06_source_only_runs/unet_b64_qd1_R2_A2.json` |
| unet_b64_qd1_R2_A3 | error | TypeError:run_source_ceiling_oracle() takes from 3 to 4 positional arguments but 6 were given | `unetClipExperimentsSeptember/06_source_only_runs/unet_b64_qd1_R2_A3.json` |
| unet_b64_qd1_R3_A2 | error | TypeError:run_source_ceiling_oracle() takes from 3 to 4 positional arguments but 6 were given | `unetClipExperimentsSeptember/06_source_only_runs/unet_b64_qd1_R3_A2.json` |
| unet_b64_qd1_R3_A3 | error | TypeError:run_source_ceiling_oracle() takes from 3 to 4 positional arguments but 6 were given | `unetClipExperimentsSeptember/06_source_only_runs/unet_b64_qd1_R3_A3.json` |
| unet_b64_qd1_R4_A2 | error | TypeError:run_source_ceiling_oracle() takes from 3 to 4 positional arguments but 6 were given | `unetClipExperimentsSeptember/06_source_only_runs/unet_b64_qd1_R4_A2.json` |
| unet_b64_qd2_R1_A2 | error | TypeError:run_source_ceiling_oracle() takes from 3 to 4 positional arguments but 6 were given | `unetClipExperimentsSeptember/06_source_only_runs/unet_b64_qd2_R1_A2.json` |
| unet_b64_qd2_R1_A3 | error | TypeError:run_source_ceiling_oracle() takes from 3 to 4 positional arguments but 6 were given | `unetClipExperimentsSeptember/06_source_only_runs/unet_b64_qd2_R1_A3.json` |
| unet_b64_qd2_R2_A2 | error | TypeError:run_source_ceiling_oracle() takes from 3 to 4 positional arguments but 6 were given | `unetClipExperimentsSeptember/06_source_only_runs/unet_b64_qd2_R2_A2.json` |
| unet_b64_qd2_R2_A3 | error | TypeError:run_source_ceiling_oracle() takes from 3 to 4 positional arguments but 6 were given | `unetClipExperimentsSeptember/06_source_only_runs/unet_b64_qd2_R2_A3.json` |
| unet_b64_qd2_R3_A2 | error | TypeError:run_source_ceiling_oracle() takes from 3 to 4 positional arguments but 6 were given | `unetClipExperimentsSeptember/06_source_only_runs/unet_b64_qd2_R3_A2.json` |
| unet_b64_qd2_R4_A2 | error | TypeError:run_source_ceiling_oracle() takes from 3 to 4 positional arguments but 6 were given | `unetClipExperimentsSeptember/06_source_only_runs/unet_b64_qd2_R4_A2.json` |
| unet_b64_qd4_R1_A2 | error | TypeError:run_source_ceiling_oracle() takes from 3 to 4 positional arguments but 6 were given | `unetClipExperimentsSeptember/06_source_only_runs/unet_b64_qd4_R1_A2.json` |
| unet_b64_qd4_R1_A3 | error | TypeError:run_source_ceiling_oracle() takes from 3 to 4 positional arguments but 6 were given | `unetClipExperimentsSeptember/06_source_only_runs/unet_b64_qd4_R1_A3.json` |
| unet_b64_qd4_R2_A2 | error | TypeError:run_source_ceiling_oracle() takes from 3 to 4 positional arguments but 6 were given | `unetClipExperimentsSeptember/06_source_only_runs/unet_b64_qd4_R2_A2.json` |
| unet_b64_qd4_R2_A3 | error | TypeError:run_source_ceiling_oracle() takes from 3 to 4 positional arguments but 6 were given | `unetClipExperimentsSeptember/06_source_only_runs/unet_b64_qd4_R2_A3.json` |
| unet_b64_qd4_R3_A2 | error | TypeError:run_source_ceiling_oracle() takes from 3 to 4 positional arguments but 6 were given | `unetClipExperimentsSeptember/06_source_only_runs/unet_b64_qd4_R3_A2.json` |
| unet_b64_qd8_R1_A2 | error | TypeError:run_source_ceiling_oracle() takes from 3 to 4 positional arguments but 6 were given | `unetClipExperimentsSeptember/06_source_only_runs/unet_b64_qd8_R1_A2.json` |
| unet_b64_qd8_R1_A3 | error | TypeError:run_source_ceiling_oracle() takes from 3 to 4 positional arguments but 6 were given | `unetClipExperimentsSeptember/06_source_only_runs/unet_b64_qd8_R1_A3.json` |
| unet_b64_qd8_R2_A2 | error | TypeError:run_source_ceiling_oracle() takes from 3 to 4 positional arguments but 6 were given | `unetClipExperimentsSeptember/06_source_only_runs/unet_b64_qd8_R2_A2.json` |
| unet_b64_qd8_R2_A3 | error | TypeError:run_source_ceiling_oracle() takes from 3 to 4 positional arguments but 6 were given | `unetClipExperimentsSeptember/06_source_only_runs/unet_b64_qd8_R2_A3.json` |
| unet_b64_qd8_R3_A2 | error | TypeError:run_source_ceiling_oracle() takes from 3 to 4 positional arguments but 6 were given | `unetClipExperimentsSeptember/06_source_only_runs/unet_b64_qd8_R3_A2.json` |

## Per-Cell Statistics And Ten Values

| model | block MiB | QD | SOURCE values ms | FILE_TO_CUDA values ms | SOURCE median | SOURCE mean | SOURCE SD | effective GB/s | proof YES/NO |
|---|---:|---:|---|---|---:|---:|---:|---:|---|
| CLIP | 32 | 1 | 11497.877, 11633.216, 8930.591, 11539.382, 16493.424, 12295.153, 11577.498, 11536.033, 11726.909, 28516.651 |  | 11605.357 | 13574.673 | 5565.471 | 0.693209 | None=10 |
| CLIP | 32 | 2 | 5318.579, 6923.400, 14331.170, 6406.228, 6635.806, 6986.876, 12583.065, 7347.111, 6739.271, 7280.974 |  | 6955.138 | 8055.248 | 2931.951 | 1.156690 | None=10 |
| CLIP | 32 | 4 | 15798.370, 7041.747, 5528.076, 6120.838, 13511.131, 7523.427, 6457.253, 6689.121, 13566.197, 5754.250 |  | 6865.434 | 8799.041 | 3883.211 | 1.171803 | None=10 |
| CLIP | 32 | 8 | 6284.054, 10237.988, 9955.513, 5950.790, 6172.387, 17104.131, 6080.989, 6470.690, 12211.301, 7492.864 |  | 6981.777 | 8796.071 | 3649.628 | 1.152276 | None=10 |
| CLIP | 64 | 1 | 8485.307, 73829.455, 11193.115, 11124.152, 16151.235, 25360.408, 15911.274, 26629.565, 11180.622, 11129.284 |  | 13552.194 | 21099.442 | 19536.687 | 0.593626 | None=10 |
| CLIP | 64 | 2 | 13279.174, 6361.637, 6982.545, 6454.329, 11826.675, 11093.649, 7493.430, 12074.693, 11933.888, 6295.858 |  | 9293.539 | 9379.588 | 2875.162 | 0.865648 | None=10 |
| CLIP | 64 | 4 | 6727.884, 5752.409, 12001.250, 4285.485, 6789.134, 5543.515, 6270.638, 4608.707, 7830.072, 16381.151 |  | 6499.261 | 7619.024 | 3760.774 | 1.237823 | None=10 |
| CLIP | 64 | 8 | 69686.703, 5430.278, 6339.555, 5930.769, 8029.247, 6178.265, 5343.607, 11179.786, 5258.828, 8821.819 |  | 6258.910 | 13219.886 | 19930.702 | 1.285357 | None=10 |
| CLIP | 128 | 1 | 18035.144, 11792.695, 11133.994, 11137.201, 12747.773, 13882.578, 13123.949, 12397.244, 22858.966, 8893.987 |  | 12572.508 | 13600.353 | 4019.920 | 0.639883 | None=10 |
| CLIP | 128 | 2 | 9029.551, 8100.225, 6132.501, 6363.142, 11934.237, 25324.171, 65622.246, 13174.577, 17255.317, 6370.979 |  | 10481.894 | 16930.695 | 18137.386 | 0.767508 | None=10 |
| CLIP | 128 | 4 | 7247.540, 6513.703, 5856.828, 5817.107, 6086.302, 11653.085, 10732.241, 5810.574, 6122.421, 8365.495 |  | 6318.062 | 7420.530 | 2152.531 | 1.273323 | None=10 |
| CLIP | 128 | 8 | 11080.672, 5763.920, 6615.245, 6275.383, 5635.867, 8838.549, 12597.741, 7599.258, 8109.165, 18992.875 |  | 7854.212 | 9150.868 | 4144.405 | 1.024283 | None=10 |
| CLIP | 256 | 1 | 11029.055, 8343.602, 10891.373, 27777.632, 16608.329, 8486.062, 8736.483, 25686.375, 22851.685, 12976.642 |  | 12002.848 | 15338.724 | 7477.884 | 0.670252 | None=10 |
| CLIP | 256 | 2 | 6971.681, 6291.351, 6166.472, 6571.789, 18341.067, 19494.160, 6309.773, 17192.788, 5880.927, 5992.549 |  | 6440.781 | 9921.256 | 5844.315 | 1.249062 | None=10 |
| CLIP | 256 | 4 | 6153.114, 6069.717, 5874.257, 11821.592, 12598.658, 14011.889, 6448.207, 7711.419, 5767.153, 4396.609 |  | 6300.660 | 8085.261 | 3398.357 | 1.276840 | None=10 |
| CLIP | 256 | 8 | 6611.853, 5129.419, 5470.146, 12338.743, 16934.426, 15580.310, 4191.517, 9001.416, 5702.771, 5829.760 |  | 6220.806 | 8679.036 | 4637.538 | 1.293230 | None=10 |
| UNET | 32 | 1 | 20258.444, 19488.972, 19696.492, 18953.093, 14603.498, 18176.033, 18400.079, 18772.523, 17271.308, 43816.893 |  | 18862.808 | 20943.734 | 8190.885 | 0.652597 | None=10 |
| UNET | 32 | 2 | 26349.851, 59918.814, 13812.297, 11991.407, 18739.450, 12894.765, 11261.488, 11805.088, 12936.646, 9949.375 |  | 12915.705 | 18965.918 | 15173.302 | 0.953089 | None=10 |
| UNET | 32 | 4 | 21696.696, 13045.985, 14325.530, 19869.500, 15981.925, 9358.189, 9467.610, 12133.552, 10451.815, 8985.817 |  | 12589.768 | 13531.662 | 4468.969 | 0.977764 | None=10 |
| UNET | 32 | 8 | 14999.216, 9521.310, 10391.742, 13752.970, 12029.749, 10886.073, 11562.107, 15542.418, 10697.637, 10028.490 |  | 11224.090 | 11941.171 | 2116.842 | 1.096732 | None=10 |
| UNET | 64 | 1 | 17850.405, 59619.257, 17359.016, 18784.909, 17018.142, 18217.820, 16743.419, 17914.969, 21855.952, 18622.313 |  | 18066.394 | 22398.620 | 13155.424 | 0.681365 | None=10 |
| UNET | 64 | 2 | 11927.541, 12070.561, 12870.087, 10333.179, 37812.880, 12145.181, 9948.332, 12504.109, 12043.797, 9996.148 |  | 12057.179 | 14165.182 | 8376.370 | 1.020953 | None=10 |
| UNET | 64 | 4 | 14922.364, 11228.218, 14806.186, 8808.611, 10756.898, 6681.319, 9186.842, 8244.437, 12506.122, 13635.305 |  | 10992.558 | 11077.630 | 2857.155 | 1.119832 | None=10 |
| UNET | 64 | 8 | 13880.953, 11398.850, 7831.108, 11420.665, 9757.244, 10514.494, 9001.996, 9072.674, 17156.872, 11676.091 |  | 10956.672 | 11171.095 | 2712.850 | 1.123500 | None=10 |
| UNET | 128 | 1 | 19970.439, 22605.666, 13418.427, 17751.863, 26987.649, 19043.375, 23344.573, 18549.187, 19267.782, 18448.915 |  | 19155.579 | 19938.788 | 3668.174 | 0.642623 | None=10 |
| UNET | 128 | 2 | 27866.028, 8613.872, 13055.830, 13139.571, 14590.680, 14918.806, 15252.167, 12618.971, 9752.926, 11999.505 |  | 13097.701 | 14180.836 | 5262.971 | 0.939846 | None=10 |
| UNET | 128 | 4 | 12529.698, 18977.245, 10940.068, 10684.525, 13199.812, 9792.188, 7959.579, 12604.507, 11516.987, 8783.882 |  | 11228.527 | 11698.849 | 3063.960 | 1.096298 | None=10 |
| UNET | 128 | 8 | 11332.543, 10534.819, 66503.163, 10942.912, 7935.418, 6541.443, 12161.884, 30432.170, 13774.174, 19290.924 |  | 11747.213 | 18944.945 | 18056.624 | 1.047893 | None=10 |
| UNET | 256 | 1 | 19545.493, 13990.990, 13127.221, 17914.529, 42055.863, 17923.738, 16368.914, 17891.927, 16932.191, 14224.305 |  | 17412.059 | 18997.517 | 8360.091 | 0.706971 | None=10 |
| UNET | 256 | 2 | 95728.839, 27061.271, 67839.805, 8930.034, 12845.966, 12045.196, 8164.090, 12067.801, 8741.944, 29545.753 |  | 12456.883 | 28297.070 | 29893.940 | 0.988194 | None=10 |
| UNET | 256 | 4 | 10896.612, 11365.099, 11375.997, 21004.963, 15103.177, 11567.760, 11348.739, 13960.994, 11704.249, 8556.685 |  | 11471.878 | 12688.428 | 3405.715 | 1.073043 | None=10 |
| UNET | 256 | 8 | 10936.478, 22222.472, 8646.996, 10764.224, 9075.750, 6021.566, 9266.721, 11570.143, 8935.561, 11394.503 |  | 10015.473 | 10883.441 | 4315.845 | 1.229080 | None=10 |

## Deployment And Fixed Contract

- Worktree: `C:/Users/parla/OneDrive/Documents/AI HUB/ComfyUI June Install/ComfyUI/custom_nodes/comfyui-modal`; branch: `TESTING2`; HEAD: `UNAVAILABLE`.
- App: `sept-unetclip-04-source-ceiling-oracle`; workspace/environment: `UNAVAILABLE` / `UNAVAILABLE`.
- Source blocks: 32, 64, 128, 256 MiB; QD values: 1, 2, 4, 8; scheduling: serial, round-major.
- Model construction, CUDA, H2D, and full Golden generation were not run.

## Raw Evidence Paths

- `unetClipExperimentsSeptember/06_source_only_runs`
- `unetClipExperimentsSeptember/06_source_only_runs_batch1_clip`
- `unetClipExperimentsSeptember/06_source_only_runs_batch2_unet_small`
- `unetClipExperimentsSeptember/06_source_only_runs_batch3_unet_large`
- `unetClipExperimentsSeptember/06_source_only_runs_clip_32_64`
- `unetClipExperimentsSeptember/06_source_only_runs_clip_128_256`
- `unetClipExperimentsSeptember/06_source_only_runs_unet_32_64`
- `unetClipExperimentsSeptember/06_source_only_runs_unet_128_256`
- Historical integrated evidence: `unetClipExperimentsSeptember/05_qd2_qd4_qd8_additional10.json`
- Machine-readable report: `unetClipExperimentsSeptember/06_source_block_qd_matrix_pure_source.json`
