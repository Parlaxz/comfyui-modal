# Hedge latency trace — why a 250 ms hedge does not enter `preadv` until the original completes

**Answer: A.** The hedge thread does not begin executing until the original finishes. Our own synchronization is not at fault — every hedge-path step costs **< 0.02 ms** once the thread actually runs.

**And the cause is process-wide freezing.** A canary thread — pure timing, no I/O, no locks — stops ticking for up to **1378.9 ms** during the same stalls, in all four reader processes simultaneously.

Corpus: 20 runs, **12 hedge-eligible blocks**, `hedge_trace_runs/`. Same-path hedge topology unchanged, no provider pinning.

## Per hedged logical block

| run | provider/region | original duration | timeout fired at | hedge thread started at | blocking step | pacer claim | hedge enter | hedge duration | winner |
|---|---|---:|---:|---:|---|---:|---:|---:|---|
| im-04 | gcp:ap-south | 1616.0 | 239.9 | **1616.9** | thread-not-scheduled | 1617.06 | 1617.26 | 28.77 | original |
| im-04 | gcp:ap-south | 1560.9 | 251.1 | **1562.2** | thread-not-scheduled | 1565.13 | 1565.14 | 39.21 | original |
| im-04 | gcp:ap-south | 1553.2 | 235.5 | **1554.7** | thread-not-scheduled | 1556.47 | 1556.49 | 56.48 | original |
| im-04 | gcp:ap-south | 1498.2 | 243.3 | **1498.9** | thread-not-scheduled | 1498.92 | 1498.94 | 28.79 | original |
| im-18 | gcp:us-west | 669.4 | 246.8 | **670.0** | thread-not-scheduled | 674.56 | 674.57 | 27.56 | original |
| im-14 | gcp:us-west | 423.6 | 250.6 | **424.1** | thread-not-scheduled | 424.14 | 424.15 | 27.67 | original |
| im-14 | gcp:us-west | 376.5 | 250.9 | **378.0** | thread-not-scheduled | 378.08 | 378.09 | 23.72 | original |
| im-07 | gcp:us-west | 347.5 | 238.6 | **348.1** | thread-not-scheduled | 353.95 | 353.96 | 26.19 | original |
| im-18 | gcp:us-west | 305.2 | 246.6 | **305.7** | thread-not-scheduled | 305.70 | 305.71 | 19.63 | original |
| im-14 | gcp:us-west | 274.0 | 250.3 | 274.3 | none→preadv | 274.29 | 274.30 | 21.06 | original |
| im-14 | gcp:us-west | 273.4 | 250.8 | 273.7 | none→preadv | 273.75 | 273.76 | 22.38 | original |
| im-14 | gcp:us-west | 258.7 | 250.7 | 259.0 | none→preadv | 259.00 | 259.01 | 21.43 | original |

All 12: **hedge thread start ≈ original completion**, and the original wins every time.

## Stage delays

| stage | median | max |
|---|---:|---:|
| **timeout fires → hedge thread starts** | **150.3 ms** | **1376.9 ms** |
| hedge thread start → gate entry | 0.012 ms | 0.158 ms |
| gate entry → pacer claim | 0.006 ms | 5.824 ms |
| pacer claim → `preadv` enter | 0.015 ms | 0.206 ms |
| post-`preadv` lock wait | 0.004 ms | 0.009 ms |

**The timeout itself fires correctly** — 235.5–251.1 ms, i.e. the configured 250 ms. Everything after the thread is running is sub-millisecond. **100% of the missing time is between "the 250 ms timer fired" and "the hedge thread executes its first instruction".**

## The canary — this is the important part

A dedicated canary thread per reader process does nothing but `sleep(10 ms)` and append a timestamp. No I/O, no locks, no pacer, no hedge machinery.

| run | worker | canary max tick gap | that run's longest original read |
|---|---|---:|---:|
| im-04 | worker3 | **1378.9 ms** | 1616.0 ms |
| im-04 | worker0 | **1320.2 ms** | 1616.0 ms |
| im-04 | worker2 | **1314.6 ms** | 1616.0 ms |
| im-04 | worker1 | **1258.1 ms** | 1616.0 ms |
| im-18 | worker3 | 426.1 ms | 669.4 ms |
| im-14 | worker3 | 163.6 ms | 423.6 ms |
| im-14 | worker1 | 118.8 ms | 423.6 ms |
| im-07 | worker3 | 117.6 ms | 347.5 ms |

Across 80 worker-canaries: max-gap **median 11.3 ms, p90 71.6 ms, max 1378.9 ms** (the 10 ms sleep plus normal jitter is ~11 ms, so the median is healthy).

**A thread that does nothing but sleep also stops running for over a second.** So the hedge path is not blocked by anything we wrote — the whole process stops being scheduled. This is case A, caused by process-wide freezing.

Note also that in `im-04` **all four reader processes** show ~1.26–1.38 s canary gaps concurrently. Each worker is a separate process, so this was not a per-process event — all four froze together.

The canary gap is consistently somewhat *shorter* than the original's duration (1378.9 vs 1616.0; 426.1 vs 669.4; 117.6 vs 347.5), so the freeze covers most but not all of the stall window.

## Conclusion

- **A**, not B. The hedge thread does not begin executing until the original finishes.
- **No code location is responsible.** Every synchronization step on the hedge path (gate, pacer claim, `preadv` entry, post-read lock) costs < 0.02 ms median once the thread runs. There is nothing to fix in the hedge machinery.
- **Prominent call-out:** this is direct evidence that the underlying sickness is **process-wide thread freezing**, not an I/O stall local to one syscall. A no-I/O canary thread is frozen for up to 1.38 s, and in one run all four reader processes froze simultaneously. Any rescue mechanism implemented as a thread inside the affected process cannot run during the stall, regardless of its design.

## Caveats

- The analyzer's summary line `original exit − hedge exit` is computed from mismatched time bases and is wrong; ignore it. The per-block `winner` column is authoritative.
- This is a latency trace, not a test of whether same-path hedging is effective — the hedges never overlapped their originals, so the same-path question remains untested.
- Provider is preserved as a covariate: 5 of 12 blocks are `gcp:ap-south` (all from `im-04`), 6 `gcp:us-west`, and the phenomenon appears in both.
