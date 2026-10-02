# H100 bad-run note — full-file geometry replication

Scope: the 45 H100 full-file runs (9 geometries x 5 fresh containers) from the
replication sweep. RTX had no catastrophic runs and is not covered here.

"Bad" = full-file GB/s < 2.0 or >= 5 reads >= 1000 ms in one run.

## The 8 bad runs

| combo | run | region | GB/s | wall ms | median ms | max ms | >=250 | >=500 | >=1000 | shape |
|---|---|---|---|---|---|---|---|---|---|---|
| 128 MiB x QD8 | rep3 | us-east1-a | 0.258 | 31221 | 219.6 | 25254.1 | 26 | 24 | 21 | broad + extreme tail |
| 64 MiB x QD4 | rep1 | denver | 0.767 | 10493 | 37.5 | 7255.5 | 9 | 9 | 9 | tail-only |
| 32 MiB x QD8 | rep2 | odin | 1.049 | 7669 | 35.0 | 6466.1 | 18 | 14 | 12 | tail-only |
| 64 MiB x QD4 | rep2 | odin | 1.052 | 7649 | 30.1 | 3514.7 | 12 | 9 | 8 | tail-only |
| 32 MiB x QD4 | rep2 | odin | 1.135 | 7088 | 18.1 | 2283.7 | 14 | 11 | 8 | tail-only |
| 64 MiB x QD8 | rep2 | odin | 1.171 | 6872 | 79.3 | 5880.2 | 15 | 14 | 14 | broad + tail |
| 32 MiB x QD8 | rep4 | odin | 1.176 | 6844 | 41.2 | 5724.6 | 18 | 17 | 13 | tail-only |
| 32 MiB x QD8 | rep3 | odin | 1.182 | 6804 | 31.9 | 5669.4 | 20 | 17 | 12 | tail-only |

Milder but notable: 32xQD2 base (chicago) 2.054 GB/s with max 1528.8 ms and
1 read >= 1000 ms; 32xQD2 rep3 (europe-west9) max 525.5 ms; 128xQD8 base/rep1/
rep2/rep4 each carried 0-2 reads >= 1000 ms.

## Oddities

1. **Region concentration.** 6 of the 8 bad runs ran in region `odin`. Across
   the whole H100 set, `odin` hosted 17 runs and 6 were bad (35%), versus 2 bad
   out of 28 runs elsewhere (7%) - a ~5x risk multiplier.
2. **But `odin` is not deterministic.** The same region also hosted 11 clean
   runs, including all four 64 MiB x QD2 reps (3.95-4.48 GB/s) and 64 MiB x QD4
   rep3/rep4 (6.06/6.02 GB/s). So `odin` is a risk multiplier, not a cause.
3. **Concurrency-dependent.** Bad runs concentrate in higher-QD / smaller-read
   combos: 32 x QD8 3/5, 64 x QD4 2/5, 128 x QD8 1/5 catastrophic, 32 x QD4 1/5,
   64 x QD8 1/5. The QD2 combos produced no bad runs at all.
4. **Two distinct failure shapes.**
   - *Tail-only*: per-run median stays normal (18-41 ms) while a small number of
     reads block for seconds (e.g. 32 x QD8 rep2: median 35.0 ms, max 6466 ms).
   - *Broad degradation*: median itself is elevated and the tail is heavy
     (64 x QD8 rep2 median 79.3 ms; 128 x QD8 rep3 median 219.6 ms).
   Most bad runs are tail-only; only those two are broad.
5. **Worst run in the entire study** is 128 MiB x QD8 rep3 (us-east1-a):
   31.2 s full-file wall, 25.25 s single read, 21 of 60 reads >= 1000 ms.
6. **Median distortion.** 32 MiB x QD8's headline median (1.182 GB/s) is
   effectively the median of its three bad runs, so that geometry's number
   reflects failure rate rather than achievable speed.
7. **QD was healthy even in the bad runs.** `effective_qd_min` stayed at QD-1 and
   median refill gaps stayed ~0.01-0.02 ms in all of them. Concurrency was not
   collapsing; individual reads were simply blocked for seconds.
8. **H100-specific.** No RTX run was catastrophic; the worst RTX run was
   2.411 GB/s (64 x QD2, AWS ap-northeast) with 2 reads >= 1000 ms.

## Carry-forward implication

H100 128 MiB x QD4 is the only H100 geometry with zero bad runs, zero reads
>= 1000 ms and SD 0.525 (10% of its median). The higher-QD H100 combos should be
treated as unsafe until the `odin`/placement interaction is understood.
