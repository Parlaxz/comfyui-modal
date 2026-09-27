# Source I/O — Tasks 1–5

Baseline throughout: H100, non-Odin counted only, QD4, 64 MiB, self-service coordination-light
reader path, 4 ms global minimum physical-start spacing, provider+region preserved, exact
full-file coverage required. Odin retained separately in every cohort directory.

---

## Task 1 — Proven memory layout of primary vs rescue destinations

Full detail: `TASK1_MEMORY_LAYOUT.md`. Evidence is runtime addresses from a real rescue event
(`task1_layout/im-01.json`, gcp:us-west), not names.

| thing | process | backing object | base addr | write addr | length | overlaps canonical SHM slot? |
|---|---|---:|---:|---:|---:|---|
| stuck buffered primary dest | reader 2, pid 8 | private `bytearray` on heap | `0x2b5588000010` | base + 0 | 134217728 | No — no payload SHM slot exists |
| O_DIRECT rescue dest | reader 4, pid 10 | anonymous `mmap(-1, …)`, MAP_PRIVATE | `0x2b5590001000` | base (4096-aligned) | 134217728 rounded | No — no payload SHM slot exists |
| canonical / publication SHM slot | — | **does not exist for payload bytes** | — | — | — | n/a |
| shadow / side buffer | reader 4, pid 10 | same anonymous mmap | `0x2b5590001000` | same | 134221824 allocated | No |
| final winner-copy source/dest | — | **no payload copy occurs** | — | — | — | n/a |

All shared memory used by the engine totals **1904 bytes of integers** (`ownership` 60, `winner` 240,
`start_ns` 480, `winner_exit_ns` 480, `attempts` 240, …). **Payload bytes in shared memory: 0.**

The five readers show *identical* virtual addresses because they are all `fork`ed and allocate the
same layout — but pids 6–10 are **separate address spaces**, so identical VAs are distinct physical
memory. Within each process the two destinations are disjoint (`intra_process_overlap` False for all 5).

**Answers**
1. Same memory range? **No** — different process, different mapping.
2. Separate destinations? **Completely separate.**
3. Either read touch the canonical SHM slot before a winner is known? **No payload SHM slot exists.**
4. What copy/publication occurs on a rescue win? **No payload copy at all** — only integers
   (`winner[bid]=id`, `winner_kind=2`, `winner_exit_ns`, `completed+=1`, `ownership=2`).
5. Can a late loser reference/mutate the winning slot? **No** — nothing is shared, and `winner[bid]`
   is only written while it is still `-1`, so the first validated winner is fixed.

**Consequence:** "rescue wins" in this harness means *the rescue returned first*, not *its bytes were
published*. Real publication (canonical SHM slot, winner copy, direct-to-GPU staging) is **not yet
implemented** and must not be assumed.

---

## Task 2 — Source-wall accounting

Full detail: `task2_report/TASK2_WALL_ACCOUNTING.md`. 12 valid non-Odin healthy runs, all amp 1.0,
zero stale/rescue attempts. Telemetry is preallocated shared memory written by slot index — no
per-read logging or JSON.

**Occupancy**

| active physical preadvs | wall ms (mean/run) | % of source wall |
|---:|---:|---:|
| 0 | 0.0 | 0.00% |
| 1 | 10.6 | 0.65% |
| 2 | 14.6 | 0.89% |
| 3 | 107.8 | 6.62% |
| 4 | 1496.0 | 91.84% |

**Identity validated:** `sum(preadv durations) == integral(active concurrency)` with max absolute
error **0.000000 ms** across all 12 runs.

| quantity | ms |
|---|---:|
| source wall | 1629.0 |
| sum preadv service | 6347.2 |
| theoretical lower bound = sum/4 | 1586.8 |
| observed minus theoretical lower bound | **42.2** |

**Residual attribution**

| residual owner | ms | % residual |
|---|---:|---:|
| 4 ms pacing wait | 27.47 | 65.1% |
| worker turnaround | 1.77 | 4.2% |
| publish/lock | 0.63 | 1.5% |
| claim/lock | 0.43 | 1.0% |
| loop back | 0.44 | 1.0% |
| pre-gate dispatch | 0.17 | 0.4% |
| gate->preadv enter | 0.24 | 0.6% |
| post-read bookkeeping | 0.02 | 0.0% |
| **attributed total** | **31.17** | **73.9%** |
| unattributed (drain tail) | 11.02 | 26.1% |

Structural: ramp to QD4 **13.3 ms**, steady state 1582.8 ms, final drain **32.9 ms**,
time at QD<4 132.99 ms, effective concurrency **3.8877**.

**Yes — the wall is explained by raw reads:** `sum preadv / effective concurrency` = 1632.6 ms vs
observed 1629.0 ms. The whole non-`preadv` opportunity is **~42 ms (2.6%)**, dominated by the 4 ms
pacing wait (27 ms), which is a deliberate anti-pathology measure.

---

## Task 3 — Persistent mmap M0 as a tail rescue

Full detail: `task3_report/TASK3_M0_RESCUE.md`. 62 valid non-Odin runs (both stopping conditions met:
≥60 runs **and** 53 primary ≥1 s events). Each primary has its **own paired dormant M0 rescuer**, so
no rescue can queue behind another. Pure M0 only: persistent mapping, no MADV_WILLNEED, no
MAP_POPULATE, no Python slicing, one C-level memcpy, prearmed before timed work.

| primary band | events | M0 ms median | M0 ms max | ms saved median | M0 healthy (<100 ms) |
|---|---:|---:|---:|---:|---|
| 250 ms–1 s | 20 | 114.1 | 614.7 | 5.3 | 9/20 |
| 1–5 s | 4 | 2118.0 | 2131.8 | 7.2 | 0/4 |
| ≥5 s | 49 | 11021.0 | 21550.2 | 1.3 | 0/49 |

For the ≥1 s events:
1. **Entered promptly?** **Yes** — detection latency median **0.54 ms** (max 1.15), entering 0.55 ms
   after the 250 ms mark.
2. **Stayed healthy?** **No** — M0 median **10895.5 ms** on an 11.15 s primary; ≥100 ms in 53/53.
3. **Photo-finish or co-stall?** **Co-stall** — M0 finished a median **1.4 ms** from the primary
   (0.01% of an 11 s read).

**Meaningful escapes: 0 of 53.** Rescue amplification median 1.0000, max physical inflight 8
(4 primaries + 4 paired rescuers), min spacing 4.0001 ms, 0 M0 errors, exact coverage 62/62.
All four ≥1 s events in the first batch came from a single ap-south run.

---

## Task 4 — Optimize M0

**Not executed.** The gate was "primary ≥1000 ms and M0 completes hundreds of ms earlier, not a
0–10 ms photo-finish". Task 3 produced **0** such escapes across 53 events (median saving 1.4 ms on
an 11 s read). Per instruction, the M0-rescue direction is **closed without optimisation**.

---

## Task 5 — Is 4 ms pacing still too aggressive?

Full detail: `task5_report/TASK5_PACING.md`, control manifest `task5_report/CONTROL_MANIFEST.txt`.
Control = the **frozen** 42-file 4.0 ms self-service cohort (not re-run, static controls not used).
Treatments = fresh runs of the identical engine/geometry, interleaved `[5,6,6,5,5,6]`, 42 valid
non-Odin each.

**Pooled physical preadv**

| gap | reads | median | mean | p90 | p95 | p99 | p99.5 | worst |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 4.0 | 5040 | 43.87 | 50.70 | 73.58 | 95.60 | 134.70 | 149.66 | 220.5 |
| 5.0 | 5048 | 44.53 | 52.87 | 71.69 | 86.52 | 173.19 | 209.47 | 2052.0 |
| 6.0 | 5056 | 43.93 | 57.51 | 69.25 | 85.91 | 128.72 | 387.43 | 6134.9 |

**Tail counts / normalized / run-level**

| gap | >=250 | >=500 | >=1s | >=2s | per-1000 >=250 | >=500 | >=1s | runs >=250 | >=500 | >=1s | >=2s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 4.0 | 0 | 0 | 0 | 0 | 0.00 | 0.00 | 0.00 | 0/42 | 0/42 | 0/42 | 0/42 |
| 5.0 | 13 | 10 | 5 | 1 | 2.58 | 1.98 | 0.99 | 3/42 | 2/42 | 2/42 | 1/42 |
| 6.0 | 31 | 20 | 13 | 6 | 6.13 | 3.96 | 2.57 | 3/42 | 2/42 | 2/42 | 1/42 |

**Normal performance**

| gap | n | GB/s median | mean | p10 | p90 | best | worst | wall median | wall mean |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 4.0 | 42 | 5.818 | 5.529 | 3.736 | 6.905 | 7.076 | 2.361 | 1383 | 1566 |
| 5.0 | 42 | 5.476 | 5.366 | 3.537 | 7.090 | 7.620 | 2.336 | 1469 | 1641 |
| 6.0 | 42 | 5.548 | 5.292 | 3.526 | 6.788 | 7.282 | 0.774 | 1450 | 1797 |

| gap | effective concurrency | preadv median | source wall median | **pacing-wait/run median** |
|---|---:|---:|---:|---:|
| 4.0 | 3.8761 | 43.75 | 1383 | **103.8 ms** |
| 5.0 | 3.8673 | 46.14 | 1469 | **138.3 ms** |
| 6.0 | 3.8195 | 43.99 | 1450 | **189.5 ms** |

Relative: 5 vs 4 = −5.9% median GB/s, −3.0% mean, wall +6.3%. 6 vs 4 = −4.6% median, −4.3% mean,
wall +4.9%. 6 vs 5 = +1.3% median, −1.4% mean, wall −1.3% (non-monotonic ⇒ noisy).

**The tails are provider composition, not pacing.** Region-level test:

| region | 4.0 ms | 5.0 ms | 6.0 ms |
|---|---|---|---|
| us-central | 10 runs, 0 tails | 15, 0 | 13, 0 |
| eu-north | 10, 0 | 10, 0 | 10, 0 |
| us-ashburn-1 | 9, 0 | 5, 0 | 4, 0 |
| us-west | 8, 0 | 1, 0 | 1, 0 |

Every overlapping region — including the three largest (66 runs total) — is **perfectly clean in all
three arms**. Every tail event lies in a region present in only one arm (5 ms: `ca`, `asia-south2`;
6 ms: `us-south`, `CANADA-2`).

**Decision**
1. **Does 5 ms materially reduce long tails vs 4 ms?** **No.** In overlapping regions both are clean;
   the pooled difference is host composition.
2. **Does 6 ms reduce them further?** **No.**
3. **Penalty per added millisecond:** ≈ −5% median GB/s and +5–6% wall for +1 ms, and pacing-wait/run
   rises monotonically 103.8 → 138.3 → 189.5 ms. Cost is real and monotonic; benefit is zero.
4. **Clear knee where a small healthy-path loss buys a large tail reduction?** **No knee exists** in
   these cohorts.
5. **Is there evidence 4 ms is still too aggressive?** **No.** 4 ms is the cleanest arm and the
   cheapest. Increasing spacing only adds waiting.

---

## Final conclusions

1. **Primary and rescue write to independent memory.** Separate processes, separate mappings, no
   shared payload bytes, no winner copy. The only shared state is 1904 bytes of integer metadata.
2. **The normal source wall is raw `preadv`.** 1629 ms wall = 6347 ms of preadv ÷ effective
   concurrency 3.888, matching within 3.6 ms. Residual is 42 ms (2.6%).
3. **Non-`preadv` optimisation opportunity: ~42 ms (2.6%)**, of which 27 ms is the 4 ms pacing wait —
   and Task 5 shows that wait is buying nothing measurable, so it should not be increased.
4. **Can persistent mmap M0 escape a real ≥1 s stall?** **No.** 0 meaningful escapes in 53 events;
   M0 detects in 0.54 ms then co-stalls, finishing 1.4 ms from the primary.
5. **How much does it save?** Median **1.4 ms** on ~11 s primaries — not a rescue.
6. **M0-rescue direction closed.** Combined with the earlier O_DIRECT result (which also co-stalled),
   and because both bypass the page cache, the stall is located **below the page cache** in the
   underlying fetch.

No 7 ms follow-up was launched. Raw artifacts preserved in `task1_layout/`, `task2_profile/`,
`task3_m0/`, `task5_pacing/`, `exp1_control_frozen/` plus the per-task report directories.
