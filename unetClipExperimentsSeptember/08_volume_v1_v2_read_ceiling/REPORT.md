# Modal VolumeFS V1 vs V2 Read Ceiling

Status: complete from preserved local evidence. No remote benchmark, deploy, or API call was run during this correction.

## Scope

- Experiment: absolute read ceiling for Modal VolumeFS V1 versus V2.
- Source: `diffusion_models/z_image_turbo_bf16.safetensors`.
- Source size: `12,309,866,400` bytes.
- Source SHA-256: `2407613050b809ffdff18a4ac99af83ea6b95443ecebdf80e064a79c825574a6`.
- Workspace: Testing 7 (`ws_eaef96004dac`).
- Function shape: 12 requested CPUs, 16 GiB memory, `rtx-pro-6000`, single-use containers.
- CPU note: capability affinity count `[28]` is informational only; it is not an allocation claim.

## Results

### 32 MiB QD curve

| QD | V1 median GB/s | V2 median GB/s | V1 wall ms | V2 wall ms |
|---:|---:|---:|---:|---:|
| 1 | 4.474 | 4.346 | 2752.253 | 2833.113 |
| 2 | 7.596 | 7.442 | 1622.942 | 1654.149 |
| 4 | 6.510 | 6.997 | 1891.130 | 1759.987 |
| 8 | 5.649 | 5.153 | 2181.034 | 2394.837 |
| 16 | 5.583 | 5.505 | 2205.273 | 2238.033 |

### Best raw source ceiling

| Metric | V1 | V2 |
|---|---:|---:|
| Best block | 128 MiB | 128 MiB |
| Best QD | 2 | 2 |
| Block-search median | 7.899 GB/s | 7.894 GB/s |
| Confirmation median | 7.529 GB/s | 7.500 GB/s |
| Fastest valid observation | 8.911 GB/s | 9.089 GB/s |
| Confirmation CV | 0.015 | 0.229 |
| Approximately 40 GB/s observed | No | No |
| Approximately 40 GB/s repeatable | No | No |

The authoritative repeatable comparison is the six-run confirmation at the same `128 MiB/QD2` geometry. V2 was `-0.382%` versus V1, so no meaningful V2 advantage was demonstrated at the common optimum.

### Full-file final-RAM materialization

| Metric | V1 | V2 |
|---|---:|---:|
| Geometry | 128 MiB/QD2 | 128 MiB/QD2 |
| Allocation median | 0.027 ms | 0.081 ms |
| Prefault median | 15283.877 ms | 15244.950 ms |
| Read wall median | 2519.336 ms | 2508.937 ms |
| Read median | 4.889 GB/s | 4.907 GB/s |
| End-to-end RAM-ready median | 17816.750 ms | 17644.851 ms |

Allocation, prefault, read wall, and end-to-end time are reported separately. The full-RAM result is not a pure storage ceiling because materialization and prefault are included.

### Secondary common-geometry comparison

At the secondary `32 MiB/QD8` geometry, V2 measured `5.153 GB/s` versus V1 `5.649 GB/s`, a difference of `-8.790%`. This is not the common optimum and is not used as the primary conclusion.

## Conclusions

1. Both backends selected `128 MiB/QD2` in the preserved block search.
2. The six-run confirmation at `128 MiB/QD2` measured V1 `7.529 GB/s` and V2 `7.500 GB/s`.
3. The fastest valid individual observations were V1 `8.911 GB/s` and V2 `9.089 GB/s`; they are not repeatable-ceiling estimates.
4. No approximately 40 GB/s result was observed or repeatable.
5. The evidence does not establish a causal reason for the small V2 difference.
6. The measured isolated raw source path leaves approximately `0.119-0.619 s` for V1 and `0.146-0.646 s` for V2 against a `1.5-2.0 s` source-path target. This comparison assigns no cause to the remaining gap.

## Provenance

The authoritative preserved evidence remains in `../../../modal-volume-read-ceiling/results/`. See `EVIDENCE_INDEX.md` for exact artifact pointers and the distinction between raw evidence and derived files.
