# RTX PRO 6000 — frozen-baseline cohort (20 runs) + the historical 10+ GB/s test

## Part 1 — 20 RTX runs on the best (frozen) configuration

Configuration = the frozen canonical baseline, unchanged except the GPU wrapper:
fresh exact-window mmap · MAP_PRIVATE · 64 MiB · QD4 / 4 eager reader processes ·
persistent FD per reader · self-service allocator · 4 ms global spacing · native libc memcpy ·
synchronous munmap · MAP_POPULATE removed · pure CPU source I/O · `run_worker_model_rtx`
(`gpu=rtx-pro-6000`). Same `qwen_3_4b.safetensors`. Serial (`--parallel 1`), no interleave
(single arm). Raw: `rtx_best/` (20 slots).

Verified in-artifact: **20/20** runs report
`observed_gpu = "NVIDIA RTX PRO 6000 Blackwell Server Edition"`, and **20/20** report
`read_mib=64, qd=4, lifecycle=fresh, map_shared=False, populate=False`. All 20 have
`_validity_flags = []` (clean).

Counting rule (unchanged): per arm, regions with >=3 runs count; <3-run regions dropped; Odin
excluded but retained; no US-only filter. Result: **19 counted**, 1 dropped (AWS:eu-south, n=1).

### Whole-run

| metric | value |
|---|---:|
| n (counted) | 19 |
| median GB/s | **6.167** |
| mean GB/s | 6.186 |
| p10 | 5.522 |
| p90 | 6.879 |
| best | 7.128 |
| worst | 5.478 |
| wall median ms | 1305 |
| wall mean ms | 1309 |
| SD | 0.5050 |
| CV | **0.0816** |
| MAD | 0.4240 |
| p90−p10 | 1.356 |

### Operation distribution

| ops | med | p95 | p99 | worst | >=100 | >=150 | >=250 | >=500 | >=1s | >=2s | affected runs |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 2280 | 42.6 | 57.6 | 84.1 | 116.8 | 4 | 0 | **0** | 0 | 0 | 0 | **0/19 (0%)** |

**No operation reached 250 ms at all** — the heaviest single operation across the whole cohort
was 116.8 ms. Normalized tails: (1) pooled worst/pooled med **2.74**; (2) max per-run
worst/own med **3.19**.

### Execution

| eff conc | max conc | finish spread ms | map_ms | memcpy_ms | unmap_ms | op_wall_ms | min spacing |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 3.869 | 4 | 1264 | 0.0509 | 40.2 | 2.1035 | 42.6 | 4.001 |

### Per provider:region (n>=3)

| provider:region | n | median GB/s | CV | MAD | p10 | p90 | affected |
|---|---:|---:|---:|---:|---:|---:|---:|
| GCP:us-east | 14 | 6.390 | 0.0747 | 0.3980 | 5.753 | 6.885 | 0 |
| AWS:ap-southeast | 5 | 5.555 | 0.0457 | 0.2133 | 5.517 | 6.070 | 0 |

### Guards (all counted runs)

| check | result |
|---|---|
| exact full-file coverage | **19/19** |
| amplification <= 1.0 | **19/19** |
| max physical QD == 4 | **19/19** |
| worker errors | 0 |
| map errors / unmap errors | 0 / 0 |
| barrier errors | 0 |

**Reading:** on RTX the frozen baseline is tight and clean (CV 0.082, zero ops >=250 ms), but
its median (6.17 GB/s) sits in the same band as H100 (6.29 for the P4 sync control), i.e. the
full-file mmap path does **not** exploit RTX's higher raw read capability.

---

## Part 2 — the historical 10+ GB/s RTX test

**It is `source_roll_runs/roll-rtx.json`** — the rolling-source probe
(`kind = "rolling_source_probe"`, engine `run_source_roll_*`, `os.preadv`).

| item | value |
|---|---|
| GPU | NVIDIA RTX PRO 6000 Blackwell Server Edition (`rtx-pro-6000`) |
| provider:region | GCP:us-east |
| file | `/root/models/text_encoders/qwen_3_4b.safetensors` (8,044,982,048 B) |
| read_bytes | **134,217,728 (128 MiB)** |
| blocks_per_worker | 6 |
| workers tested | 1, 2, 4, 8 |
| syscall | `os.preadv` |
| container | `ta-01M33YYDGPVKZGW6E24TDVFBPR`, image `im-HlP2QOdVAKGmyAtd14jCoz` |

### The two >=10 GB/s batches

| workers | blocks/worker | total reads | bytes read | source wall ms | **GB/s** |
|---:|---:|---:|---:|---:|---:|
| 4 | 6 | 24 | 3,221,225,472 (3 GiB) | 292.02 | **11.031** |
| 8 | 6 | 48 | 6,442,450,944 (6 GiB) | 638.61 | **10.088** |

### Why this is NOT comparable to the 6.17 GB/s full-file mmap baseline

Four material differences, all of which must be stated before any comparison:

1. **Partial coverage, not full-file.** These batches read **3 GiB and 6 GiB** of the 7.5 GiB
   file. The frozen mmap baseline reads the **entire 8,044,982,048 bytes** once. A 3 GiB span is
   far more likely to be cache-resident and avoids the file's slow tail regions.
2. **Different engine.** `os.preadv` (rolling probe), not mmap + memcpy.
3. **Different block size.** **128 MiB** blocks, not 64 MiB.
4. **Single runs, not a counted cohort.** One run per config — no n, no CV, no tail statistics.

Cross-check within the same probe: the H100 counterpart `roll-h100.json` maxed at **5.73 GB/s**
(vs 11.03 on RTX), so on this probe RTX was ~1.9x H100 — while on the full-file mmap baseline
RTX (6.17) and H100 (6.29) are level. The gap is therefore in the *probe geometry*
(128 MiB blocks over a partial span), not proof that the full-file path can reach 11 GB/s.

**So the 10+ GB/s number is real and it is this test — but it was measured over a 3–6 GiB span
with 128 MiB preadv blocks, and does not establish that the full-file 64 MiB mmap baseline can
reach it.** Testing whether 128 MiB blocks / partial-span geometry transfers to the mmap path is
a new experiment and was **not** started.

---

## Part 3 — 6 RTX runs at 128 MiB blocks (follow-up)

`run_worker_model_rtx`, fresh-window mmap, MAP_PRIVATE, **128 MiB**, QD4, 8 ms (byte-normalized
rm/16), serial. Raw: `rtx_128/` (6 slots). Verified: 6/6 `observed_gpu = NVIDIA RTX PRO 6000
Blackwell Server Edition`, 6/6 `read_mib=128, qd=4, fresh, private`, `physical_reads = 60`
(= ceil(8,044,982,048 / 134,217,728)), `_validity_flags = []`.

All six landed in **GCP:us-east**, so this is a same-region comparison.

| metric | 128 MiB (n=6, us-east) | 64 MiB (n=14, us-east) |
|---|---:|---:|
| median GB/s | **6.506** | 6.390 |
| mean | 6.479 | — |
| p10 / p90 | 5.879 / 7.052 | 5.753 / 6.885 |
| best / worst | 7.487 / 5.755 | — / — |
| wall med ms | 1237 | — |
| SD / CV / MAD / p90−p10 | 0.5459 / 0.0843 / 0.3915 / 1.173 | / 0.0747 / — |
| ops med / p95 / p99 / worst ms | 77.0 / 117.8 / 141.9 / 171.1 | 42.6 / 57.6 / 84.1 / 116.8 |
| ≥250 ms | **0** | 0 |
| affected runs | 0/6 | 0/14 |
| tails (1) / (2) | **2.22 / 2.39** | 2.74 / 3.19 |
| eff conc / max conc | 3.865 / 4 | 3.869 / 4 |
| map / memcpy / unmap / op_wall ms | 0.0649 / 72.7 / 3.5997 / 77.0 | 0.0509 / 40.2 / 2.1035 / 42.6 |

**Result: 128 MiB is +1.8% vs 64 MiB within the same region (6.506 vs 6.390) — within noise.**
It does not approach the roll probe's 11.03 GB/s.

Note the `>=100 ms` count (60/360 = 16.7%) is **size-biased**: a 128 MiB op is 2x the work, so
its absolute duration is ~2x (op median 77.0 vs 42.6 ms). The *relative* tails are actually
better at 128 MiB (2.22/2.39 vs 2.74/3.19).

**Conclusion: the 10+ GB/s figure is span/coverage-dependent, not block-size-dependent.** Reading
the full file with 128 MiB blocks still yields ~6.5 GB/s on RTX. The roll probe's advantage came
from reading only a 3–6 GiB span, not from the block size.

