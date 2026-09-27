# Task 3 — persistent mmap M0 as a tail rescue (128 MiB, QD4 buffered, paired rescuers)

- 62 valid non-Odin runs (both stopping conditions met: >=60 runs and >=5 >=1 s events)
- M0 rescue attempts: **73**, wins **66**
- primary >=1 s events: **53**; primary 250 ms-1 s events: 20

Design note: every primary has its OWN paired dormant M0 rescuer (persistent mmap + private
destination, prearmed before timed work), so no rescue can ever queue behind another.

## Every primary >=1 s event

| run | provider/region | block | primary final ms | threshold | M0 enter rel threshold | M0 ms | primary alive at M0 exit | winner | ms saved |
|---|---|---:|---:|---:|---:|---:|---|---|---:|
| im-59.json | CLOUD_PROVIDER_UNSPECIFIED:us-east1-a | 30 | 21801.4 | 250 ms | 0.53 | 21550.2 | True | m0 | 0.7 |
| im-59.json | CLOUD_PROVIDER_UNSPECIFIED:us-east1-a | 15 | 21477.8 | 250 ms | 0.48 | 21226.7 | True | m0 | 0.7 |
| im-59.json | CLOUD_PROVIDER_UNSPECIFIED:us-east1-a | 45 | 19915.5 | 250 ms | 0.22 | 19662.3 | True | m0 | 3.0 |
| im-59.json | CLOUD_PROVIDER_UNSPECIFIED:us-east1-a | 22 | 16583.6 | 250 ms | 0.59 | 16330.6 | True | m0 | 2.5 |
| im-59.json | CLOUD_PROVIDER_UNSPECIFIED:us-east1-a | 23 | 16490.6 | 250 ms | 0.43 | 16235.9 | True | m0 | 4.3 |
| im-59.json | CLOUD_PROVIDER_UNSPECIFIED:us-east1-a | 21 | 16413.4 | 250 ms | 0.73 | 16162.1 | True | m0 | 0.6 |
| im-59.json | CLOUD_PROVIDER_UNSPECIFIED:us-east1-a | 24 | 16397.9 | 250 ms | 0.21 | 16145.4 | True | m0 | 2.2 |
| im-59.json | CLOUD_PROVIDER_UNSPECIFIED:us-east1-a | 42 | 16389.8 | 250 ms | 0.91 | 16136.3 | True | m0 | 2.6 |
| im-59.json | CLOUD_PROVIDER_UNSPECIFIED:us-east1-a | 25 | 16338.8 | 250 ms | 0.30 | 16088.2 | True | m0 | 0.3 |
| im-59.json | CLOUD_PROVIDER_UNSPECIFIED:us-east1-a | 43 | 16176.7 | 250 ms | 0.46 | 15921.3 | True | m0 | 4.9 |
| im-59.json | CLOUD_PROVIDER_UNSPECIFIED:us-east1-a | 59 | 16139.8 | 250 ms | 0.53 | 15886.1 | True | m0 | 3.1 |
| im-59.json | CLOUD_PROVIDER_UNSPECIFIED:us-east1-a | 0 | 16139.5 | 250 ms | 0.26 | 15888.0 | True | m0 | 1.3 |
| im-59.json | CLOUD_PROVIDER_UNSPECIFIED:us-east1-a | 58 | 16087.8 | 250 ms | 0.90 | 15836.2 | True | m0 | 0.7 |
| im-59.json | CLOUD_PROVIDER_UNSPECIFIED:us-east1-a | 41 | 16002.0 | 250 ms | 0.84 | 15750.3 | True | m0 | 0.9 |
| im-59.json | CLOUD_PROVIDER_UNSPECIFIED:us-east1-a | 26 | 15831.8 | 250 ms | 1.12 | 15580.5 | True | m0 | 0.2 |
| im-59.json | CLOUD_PROVIDER_UNSPECIFIED:us-east1-a | 47 | 12338.5 | 250 ms | 0.78 | 12084.2 | True | m0 | 3.5 |
| im-59.json | CLOUD_PROVIDER_UNSPECIFIED:us-east1-a | 32 | 11808.8 | 250 ms | 1.05 | 11556.8 | True | m0 | 0.9 |
| im-59.json | CLOUD_PROVIDER_UNSPECIFIED:us-east1-a | 17 | 11689.5 | 250 ms | 0.31 | 11439.0 | True | m0 | 0.3 |
| im-59.json | CLOUD_PROVIDER_UNSPECIFIED:us-east1-a | 54 | 11582.1 | 250 ms | 0.98 | 11328.1 | True | m0 | 3.0 |
| im-59.json | CLOUD_PROVIDER_UNSPECIFIED:us-east1-a | 18 | 11568.2 | 250 ms | 0.63 | 11316.4 | True | m0 | 1.2 |
| im-59.json | CLOUD_PROVIDER_UNSPECIFIED:us-east1-a | 48 | 11559.2 | 250 ms | 0.32 | 11305.7 | True | m0 | 3.2 |
| im-59.json | CLOUD_PROVIDER_UNSPECIFIED:us-east1-a | 31 | 11514.1 | 250 ms | 0.72 | 11261.1 | True | m0 | 2.3 |
| im-59.json | CLOUD_PROVIDER_UNSPECIFIED:us-east1-a | 2 | 11424.4 | 250 ms | 1.16 | 11173.0 | True | m0 | 0.2 |
| im-59.json | CLOUD_PROVIDER_UNSPECIFIED:us-east1-a | 50 | 11406.8 | 250 ms | 0.55 | 11154.2 | True | m0 | 2.1 |
| im-59.json | CLOUD_PROVIDER_UNSPECIFIED:us-east1-a | 16 | 11273.1 | 250 ms | 0.20 | 11021.0 | True | m0 | 1.9 |
| im-59.json | CLOUD_PROVIDER_UNSPECIFIED:us-east1-a | 38 | 11245.3 | 250 ms | 1.12 | 10993.1 | True | m0 | 1.0 |
| im-59.json | CLOUD_PROVIDER_UNSPECIFIED:us-east1-a | 1 | 11145.6 | 250 ms | 0.28 | 10895.5 | False | primary | -0.2 |
| im-59.json | CLOUD_PROVIDER_UNSPECIFIED:us-east1-a | 19 | 11139.3 | 250 ms | 0.32 | 10887.9 | True | m0 | 1.1 |
| im-59.json | CLOUD_PROVIDER_UNSPECIFIED:us-east1-a | 9 | 11127.3 | 250 ms | 0.44 | 10888.8 | False | primary | -11.9 |
| im-59.json | CLOUD_PROVIDER_UNSPECIFIED:us-east1-a | 49 | 11079.6 | 250 ms | 0.50 | 10825.1 | True | m0 | 4.0 |
| im-59.json | CLOUD_PROVIDER_UNSPECIFIED:us-east1-a | 34 | 11014.0 | 250 ms | 0.15 | 10761.9 | True | m0 | 1.9 |
| im-59.json | CLOUD_PROVIDER_UNSPECIFIED:us-east1-a | 20 | 10954.0 | 250 ms | 0.54 | 10702.6 | True | m0 | 0.9 |
| im-59.json | CLOUD_PROVIDER_UNSPECIFIED:us-east1-a | 52 | 10923.7 | 250 ms | 0.16 | 10672.7 | True | m0 | 0.8 |
| im-59.json | CLOUD_PROVIDER_UNSPECIFIED:us-east1-a | 39 | 10912.4 | 250 ms | 1.03 | 10660.6 | True | m0 | 0.8 |
| im-59.json | CLOUD_PROVIDER_UNSPECIFIED:us-east1-a | 56 | 10899.6 | 250 ms | 0.55 | 10648.0 | True | m0 | 1.0 |
| im-59.json | CLOUD_PROVIDER_UNSPECIFIED:us-east1-a | 44 | 10876.5 | 250 ms | 1.01 | 10624.6 | True | m0 | 0.9 |
| im-59.json | CLOUD_PROVIDER_UNSPECIFIED:us-east1-a | 53 | 10847.5 | 250 ms | 0.55 | 10594.9 | True | m0 | 2.1 |
| im-59.json | CLOUD_PROVIDER_UNSPECIFIED:us-east1-a | 51 | 10839.7 | 250 ms | 0.43 | 10587.6 | True | m0 | 1.7 |
| im-59.json | CLOUD_PROVIDER_UNSPECIFIED:us-east1-a | 35 | 10837.1 | 250 ms | 0.96 | 10585.7 | True | m0 | 0.4 |
| im-59.json | CLOUD_PROVIDER_UNSPECIFIED:us-east1-a | 33 | 10809.1 | 250 ms | 1.08 | 10553.1 | True | m0 | 4.9 |
| im-59.json | CLOUD_PROVIDER_UNSPECIFIED:us-east1-a | 8 | 10802.6 | 250 ms | 0.75 | 10555.9 | False | primary | -4.1 |
| im-59.json | CLOUD_PROVIDER_UNSPECIFIED:us-east1-a | 37 | 10779.0 | 250 ms | 0.88 | 10525.0 | True | m0 | 3.2 |
| im-59.json | CLOUD_PROVIDER_UNSPECIFIED:us-east1-a | 36 | 10771.9 | 250 ms | 0.44 | 10520.6 | True | m0 | 0.9 |
| im-59.json | CLOUD_PROVIDER_UNSPECIFIED:us-east1-a | 46 | 10742.9 | 250 ms | 0.74 | 10491.9 | True | m0 | 0.3 |
| im-59.json | CLOUD_PROVIDER_UNSPECIFIED:us-east1-a | 55 | 10605.9 | 250 ms | 0.13 | 10352.8 | True | m0 | 2.9 |
| im-59.json | CLOUD_PROVIDER_UNSPECIFIED:us-east1-a | 27 | 10552.3 | 250 ms | 0.84 | 10295.7 | True | m0 | 5.8 |
| im-59.json | CLOUD_PROVIDER_UNSPECIFIED:us-east1-a | 40 | 10550.6 | 250 ms | 0.27 | 10299.0 | True | m0 | 1.4 |
| im-59.json | CLOUD_PROVIDER_UNSPECIFIED:us-east1-a | 57 | 10510.2 | 250 ms | 0.38 | 10255.6 | True | m0 | 4.2 |
| im-59.json | CLOUD_PROVIDER_UNSPECIFIED:us-east1-a | 12 | 5571.9 | 250 ms | 0.78 | 5311.7 | True | m0 | 9.5 |
| im-22.json | CLOUD_PROVIDER_GCP:ap-south | 30 | 2392.8 | 250 ms | 1.02 | 2125.3 | True | m0 | 16.5 |
| im-22.json | CLOUD_PROVIDER_GCP:ap-south | 45 | 2381.0 | 250 ms | 0.19 | 2131.8 | False | primary | -0.9 |
| im-22.json | CLOUD_PROVIDER_GCP:ap-south | 15 | 2365.4 | 250 ms | 0.74 | 2110.6 | True | m0 | 4.0 |
| im-22.json | CLOUD_PROVIDER_GCP:ap-south | 0 | 2360.1 | 250 ms | 0.88 | 2098.9 | True | m0 | 10.4 |

## Aggregate by primary severity

| primary band | events | M0 ms median | M0 ms max | ms saved median | ms saved max | M0 healthy (<100 ms)? |
|---|---:|---:|---:|---:|---:|---|
| 250 ms-1 s | 20 | 114.1 | 614.7 | 5.3 | 26.5 | 9/20 |
| 1-5 s | 4 | 2118.0 | 2131.8 | 7.2 | 16.5 | 0/4 |
| >=5 s | 49 | 11021.0 | 21550.2 | 1.3 | 9.5 | 0/49 |

## The three questions for >=1 s events

1. **Did M0 enter promptly near the threshold?** Yes. Threshold-detection latency median **0.54 ms**, max 1.15 ms; M0 entered 0.55 ms (median) after the 250 ms mark.
2. **Did M0 stay healthy (~tens of ms)?** **No.** M0 duration median **10895.5 ms**, max 21550.2 ms, against a primary median 11145.6 ms. M0 took >=100 ms in 53/53 of these events.
3. **Photo-finish or co-stall?** Co-stall. M0 finished only **1.4 ms** (median) from the primary - a 0.01% difference on a ~11.15 s read.

**Meaningful escapes (primary >=1000 ms and M0 >=100 ms earlier): 0.**

## Other QD readers during the >=1 s events

For each run containing a >=1 s primary, the other primary reads in the SAME run:

| run | >=1 s events | other primary reads | other median ms | other max ms |
|---|---:|---:|---:|---:|
| im-22.json | 4 | 56 | 94.8 | 117.9 |
| im-59.json | 49 | 11 | 65.9 | 683.3 |

## Amplification / inflight / correctness

| metric | value |
|---|---:|
| rescue amplification (attempts / blocks) median / max | 1.0000 / 1.8333 |
| max physical inflight median / max | 4.0 / 8 |
| min start spacing, primaries (ms) | 4.0044 |
| M0 errors | 0 |
| exact full-file coverage | 62/62 |
| worker errors | 0 |

## Pathological-run concentration

| region | >=1 s events |
|---|---:|
| us-east1-a | 49 |
| ap-south | 4 |

## Verdict

**M0 does not escape.** It detects the stall almost perfectly (sub-millisecond) and then
co-stalls with the primary: on 1-5 s primaries its own duration is ~2.1 s and it finishes
only tens of milliseconds earlier. Because the M0 path never touches the page cache
(persistent mapping + C memcpy) yet stalls identically, the stall is below the page cache
in the underlying fetch - the same conclusion as the O_DIRECT result.

Per the Step 4 gate ('meaningful' = M0 completes hundreds of ms earlier on a >=1 s primary),
there is **no meaningful escape**, so the M0-rescue direction is closed without optimisation.

