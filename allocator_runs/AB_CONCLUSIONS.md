# Greedy allocator A/B — conclusions

Tables: `allocator_runs/AB_REPORT.md` (main summary, tail summary, scheduler detail, provider-stratified, one row per run for both arms).

## Headline

| arm | n | GB/s median | mean | p10 | p90 | best | worst | wall median | wall mean |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| static (control) | 30 | **6.015** | 5.829 | 5.292 | 6.425 | 7.194 | 3.060 | **1337** | 1408 |
| allocator (treatment) | 30 | **5.300** | 5.422 | 4.723 | 6.785 | 7.143 | 2.814 | **1518** | 1534 |

| arm | preadv median | p95 | p99 | worst | >=250ms | >=500ms | >=1000ms |
|---|---:|---:|---:|---:|---:|---:|---:|
| static (control) | 41.99 | 54.25 | 62.36 | 248.8 | 0 | 0 | 0 |
| allocator (treatment) | 95.78 | 115.57 | 119.98 | 388.3 | 18 | 0 | 0 |

Treatment scheduler: rescue-eligible 2 · launches 2 · wins 1 · saved 1.33 ms · amplification median 1.0000 / max 1.0333 · **max physical QD 4** · **min start spacing 4.0022 ms** · idle-no-work 2952 ms total.

**Not a provider artifact** — the allocator is slower *within every provider*:

| provider | static median | allocator median | delta |
|---|---:|---:|---:|
| gcp | 6.058 (n=23) | 5.250 (n=17) | −13.3% |
| oci | 5.293 (n=5) | 5.175 (n=4) | −2.2% |
| unspecified | 6.850 (n=2) | 6.090 (n=8) | −11.1% |

## The four questions

**1. Does the greedy allocator improve throughput/makespan? — No, it is ~12–14% worse.** Median 5.300 vs 6.015 GB/s (−11.9%); wall 1518 vs 1337 ms (+13.5%). Worse within every provider.

**But the allocator itself is not the cost — the 128 MiB block size is.** The decomposition is clean:

| | reads/run | median read ms | read-time × count | ÷ 4 readers | observed wall |
|---|---:|---:|---:|---:|---:|
| static | 120 | 41.99 | 5039 ms | 1260 ms | 1337 ms |
| allocator | 60 | 95.78 | 5747 ms | 1437 ms | 1518 ms |

Reads halved (120→60) while per-read latency rose 2.28×. Since the data only doubled, latency is **super-linear** in block size (2.28× for 2.00× bytes). Net effect: 2.28 / 2.00 = **1.14 → +14% predicted**, vs **+13.5% observed**. The whole throughput deficit is the block-size effect; the scheduler adds nothing measurable.

**2. Does it reduce end-of-file imbalance? — Untested: there was no imbalance to reduce.** `reader_blocks_won` was exactly `[15, 15, 15, 15]` in 21 of 30 runs (±1 otherwise). With symmetric readers the greedy allocator hands out blocks perfectly evenly, so the "fast readers naturally do more" mechanism never engages. This cohort cannot answer the question; it needs a cohort containing a genuine straggler.

**3. Can a next-free QD reader duplicate a stalled read and win at QD4? — Yes, but barely exercised.** Only **2** rescue-eligible blocks occurred across all 30 runs (the cohort was healthy: 18 reads ≥250 ms, none ≥500). Both launched, **1 won, saving 1.33 ms**. Invariants held: physical QD stayed at 4, amplification 1.0000 median / 1.0333 max, and the first-completion-wins / stale-duplicate logic worked (stale duplicates recorded separately, nothing corrupted). The mechanism is functional; the cohort simply had almost no stalls.

**4. Does the allocator introduce a healthy-path regression? — No measurable one.** Per-read latency inflation (2.28×) is fully accounted for by the 2× block size, and the residual throughput difference matches the block-size prediction to within 0.5 points. The only allocator-specific overheads are small: ~98 ms/run of end-of-file idle when fewer than 4 blocks remain, and per-block IPC (60 round-trips/run).

## Caveats

- **Block size differs by design** (control 64 MiB, treatment 128 MiB, as specified). This is a **scheduler + block-size** comparison, not a scheduler-only isolation. The decomposition above separates them analytically but not experimentally.
- Control pool is 30 **witness-engine** runs (static QD4, 64 MiB, no hedge/allocator) — the most recent valid non-Odin static runs available. They carry canary instrumentation the treatment lacks. Frozen file list is in `AB_REPORT.md`.
- 15 odin treatment runs were retained and excluded from the counted 30 (`allocator_runs/*odin*` are flagged in-file via `_is_odin`).
- The cohort was healthy (no read ≥500 ms in either arm), so the rescue path is under-tested: **1 win is not enough to judge rescue value.**
