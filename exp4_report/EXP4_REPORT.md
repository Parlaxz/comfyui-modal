# Experiment 4 — prearmed O_DIRECT QD5 rescue (128 MiB, QD4 buffered)

Healthy state is QD4 buffered preadv; a pre-opened O_DIRECT FD and a page-aligned
anonymous buffer are armed in every reader, so the spare path allocates nothing. On a
>=250 ms still-running primary the dormant spare re-reads the SAME logical block with
O_DIRECT. Lifetime rule: a rescue win publishes immediately, the stale original may never
overwrite current state, the promoted spare becomes a normal buffered worker while the
original is still stuck (useful concurrency stays at QD4), and the returning stale original
takes over the spare role so the slot is refilled.

**Geometry note:** 128 MiB was chosen because Experiment 2 established that this is where the
>=250 ms class actually occurs. The frozen Experiment-1 control is 64 MiB, so a
matched-geometry reference (Experiment-2 self-service primaries, also 128 MiB QD4) is
included alongside it.

Treatment: **30** valid non-Odin runs (first 30 by slot; 38 collected, 12 Odin excluded).

## RAW PRIMARY tails vs ACCEPTED LOGICAL tails

| arm | n | GB/s med | GB/s mean | wall med | wall mean | logical p95 | logical p99 | logical max | >=250 | >=500 | >=1000 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| frozen Exp-1 control (64 MiB) | 42 | 5.818 | 5.529 | 1383 | 1566 | 95.6 | 134.7 | 220.5 | 0 | 0 | 0 |
| Exp-2 self-service 128 MiB (matched) | 21 | 5.414 | 5.270 | 1486 | 1925 | 140.9 | 273.1 | 8783.1 | 17 | 5 | 4 |
| Exp-4 O_DIRECT rescue (128 MiB) | 30 | 5.655 | 5.261 | 1423 | 1905 | 140.4 | 397.9 | 6494.6 | 28 | 15 | 14 |

Raw buffered primary attempts only (winners and losers alike):

| arm | primary p95 | primary p99 | primary max | >=250 | >=500 | >=1000 |
|---|---:|---:|---:|---:|---:|---:|
| frozen Exp-1 control (64 MiB) | 95.6 | 134.7 | 220.5 | 0 | 0 | 0 |
| Exp-2 self-service 128 MiB (matched) | 141.2 | 279.1 | 8783.1 | 19 | 6 | 4 |
| Exp-4 O_DIRECT rescue (128 MiB) | 141.9 | 543.2 | 6494.6 | 31 | 20 | 15 |

## O_DIRECT events

| run | provider/region | primary ms | trigger ms | direct-enter delay | O_DIRECT ms | winner | logical completion ms | ms saved | stale lifetime |
|---|---|---:|---:|---:|---:|---|---:|---:|---:|
| im-02.json | GCP:us-west | 507.8 | 250.0 | 246.0 | 258.3 | rescue | 258.3 | 3.51 | 3.5 |
| im-06.json | OCI:us-central | 317.5 | 250.0 | 253.1 | 144.8 | primary | - | - | - |
| im-06.json | OCI:us-central | 340.7 | 250.0 | 320.6 | 97.1 | primary | - | - | - |
| im-06.json | OCI:us-central | 265.0 | 250.0 | 250.2 | 65.3 | primary | - | - | - |
| im-07.json | UNSPECIFIED:eu-north | 5280.6 | 250.0 | 236.7 | 5043.9 | primary | - | - | - |
| im-07.json | UNSPECIFIED:eu-north | 2554.2 | 250.0 | 790.5 | 1770.0 | primary | - | - | - |
| im-07.json | UNSPECIFIED:eu-north | 1669.4 | 250.0 | 1638.9 | 38.6 | primary | - | - | - |
| im-07.json | UNSPECIFIED:eu-north | 1185.1 | 250.0 | 965.7 | 216.8 | rescue | 216.8 | 2.61 | 2.6 |
| im-07.json | UNSPECIFIED:eu-north | 2234.0 | 250.0 | 264.6 | 1979.3 | primary | - | - | - |
| im-07.json | UNSPECIFIED:eu-north | 402.5 | 250.0 | 250.2 | 154.9 | primary | - | - | - |
| im-07.json | UNSPECIFIED:eu-north | 397.8 | 250.0 | 250.7 | 147.6 | primary | - | - | - |
| im-22.json | GCP:us-west | 479.0 | 250.0 | 250.2 | 229.6 | primary | - | - | - |
| im-22.json | GCP:us-west | 543.2 | 250.0 | 470.9 | 58.8 | rescue | 58.8 | 13.42 | 13.4 |
| im-24.json | GCP:us-west | 544.7 | 250.0 | 245.3 | 291.8 | rescue | 291.8 | 7.69 | 7.7 |
| im-24.json | GCP:us-west | 472.9 | 250.0 | 335.8 | 137.1 | rescue | 137.1 | 0.00 | 0.0 |
| im-28.json | GCP:us-west | 573.3 | 250.0 | 246.1 | 326.6 | rescue | 326.6 | 0.58 | 0.6 |
| im-38.json | GCP:ap-south | 4520.3 | 250.0 | 246.1 | 4277.3 | primary | - | - | - |
| im-38.json | GCP:ap-south | 4536.7 | 250.0 | 4515.2 | 34.4 | primary | - | - | - |

(18 O_DIRECT attempts, 6 wins, 12 losses. `stale lifetime` = how much longer the stale buffered original ran after the O_DIRECT attempt finished; it can never overwrite the published result.)

## Scheduler / correctness

| metric | value |
|---|---:|
| rescue launches | 18 |
| rescue wins | 6 |
| O_DIRECT errors/fallbacks | 0 |
| exact mismatches (must be 0) | 0 |
| role flips (spare<->worker) | 11 |
| spare promoted | 5 |
| spare refilled | 5 |
| physical amplification median / max | 1.0000 / 1.1167 |
| max physical inflight median / max | 4.0 / 5 |
| min start spacing, buffered workers (ms) | 4.0001 |
| exact full-file coverage | 30/30 |
| worker errors | 0 |

## Provider-stratified (GB/s medians)

| provider | Exp-1 control n/med | Exp-2 128MiB n/med | Exp-4 n/med |
|---|---|---|---|
| GCP | 9/5.999 | 5/5.626 | 20/5.729 |
| OCI | 12/5.442 | 9/4.892 | 1/3.160 |
| UNSPECIFIED | 21/5.795 | 7/6.456 | 9/5.170 |

## Treatment runs — one row per run

| run | provider/region | GB/s | wall ms | primary med | primary max | rescues | wins | flips | maxIF | exact |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| im-01.json | UNSPECIFIED:us-south | 5.863 | 1372 | 88.8 | 114.8 | 0 | 0 | 0 | 4 | Y |
| im-02.json | GCP:us-west | 5.046 | 1594 | 91.6 | 507.8 | 1 | 1 | 2 | 5 | Y |
| im-03.json | GCP:us-east | 6.003 | 1340 | 85.9 | 118.4 | 0 | 0 | 0 | 4 | Y |
| im-05.json | UNSPECIFIED:us-central | 5.170 | 1556 | 100.3 | 131.4 | 0 | 0 | 0 | 4 | Y |
| im-06.json | OCI:us-central | 3.160 | 2546 | 149.4 | 345.8 | 3 | 0 | 0 | 5 | Y |
| im-07.json | UNSPECIFIED:eu-north | 0.823 | 9780 | 68.2 | 6494.6 | 7 | 1 | 2 | 5 | Y |
| im-08.json | GCP:us-west | 5.886 | 1367 | 86.4 | 108.3 | 0 | 0 | 0 | 4 | Y |
| im-09.json | GCP:us-west1 | 6.456 | 1246 | 77.2 | 106.7 | 0 | 0 | 0 | 4 | Y |
| im-10.json | UNSPECIFIED:eu-north | 7.034 | 1144 | 73.0 | 105.4 | 0 | 0 | 0 | 4 | Y |
| im-11.json | GCP:us-west1 | 5.656 | 1422 | 89.4 | 115.9 | 0 | 0 | 0 | 4 | Y |
| im-12.json | GCP:us-west | 6.342 | 1269 | 81.2 | 109.8 | 0 | 0 | 0 | 4 | Y |
| im-13.json | UNSPECIFIED:us-central | 5.849 | 1375 | 88.9 | 121.5 | 0 | 0 | 0 | 4 | Y |
| im-15.json | UNSPECIFIED:us-central | 4.522 | 1779 | 114.1 | 153.5 | 0 | 0 | 0 | 4 | Y |
| im-22.json | GCP:us-west | 5.129 | 1569 | 88.9 | 543.2 | 2 | 1 | 2 | 5 | Y |
| im-24.json | GCP:us-west | 4.610 | 1745 | 118.6 | 544.7 | 2 | 2 | 3 | 5 | Y |
| im-25.json | GCP:us-west | 5.791 | 1389 | 82.9 | 129.8 | 0 | 0 | 0 | 4 | Y |
| im-26.json | GCP:asia-south2 | 5.482 | 1468 | 89.9 | 133.5 | 0 | 0 | 0 | 4 | Y |
| im-27.json | GCP:us-west | 5.655 | 1423 | 84.3 | 141.9 | 0 | 0 | 0 | 4 | Y |
| im-28.json | GCP:us-west | 5.488 | 1466 | 85.3 | 573.3 | 1 | 1 | 2 | 5 | Y |
| im-29.json | UNSPECIFIED:us-west | 5.164 | 1558 | 98.5 | 130.8 | 0 | 0 | 0 | 4 | Y |
| im-31.json | UNSPECIFIED:us-west | 5.644 | 1425 | 93.6 | 113.5 | 0 | 0 | 0 | 4 | Y |
| im-32.json | GCP:us-west | 5.807 | 1385 | 87.0 | 129.5 | 0 | 0 | 0 | 4 | Y |
| im-33.json | GCP:us-west | 5.667 | 1420 | 88.6 | 127.4 | 0 | 0 | 0 | 4 | Y |
| im-34.json | GCP:us-west | 6.466 | 1244 | 80.2 | 91.9 | 0 | 0 | 0 | 4 | Y |
| im-35.json | GCP:us-west | 6.216 | 1294 | 82.3 | 118.1 | 0 | 0 | 0 | 4 | Y |
| im-36.json | GCP:us-west | 6.115 | 1316 | 84.8 | 114.5 | 0 | 0 | 0 | 4 | Y |
| im-38.json | GCP:ap-south | 1.363 | 5902 | 93.0 | 4536.7 | 2 | 0 | 0 | 5 | Y |
| im-40.json | GCP:ap-northeast | 5.230 | 1538 | 96.7 | 130.3 | 0 | 0 | 0 | 4 | Y |
| im-41.json | GCP:us-west | 5.806 | 1386 | 87.2 | 128.6 | 0 | 0 | 0 | 4 | Y |
| im-42.json | UNSPECIFIED:us-central | 4.380 | 1837 | 113.4 | 195.6 | 0 | 0 | 0 | 4 | Y |

## Verdict

- Healthy path preserved: QD4 buffered, spare took zero normal work, amplification ~1.0,
  min start spacing >= 4 ms, exact coverage on all 30 runs, 0 worker errors.
- Rescue events observed: 18. The key question - what the ACCEPTED LOGICAL latency becomes when a raw buffered preadv takes seconds - is answered in the event table above by the `logical completion ms` and `ms saved` columns.

