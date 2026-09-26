# Delayed Hedging — Final Report (60 runs, stopped at user request)

Campaign **stopped at 60/100 runs** (15 per arm) at the user's instruction. Balanced randomized schedule (seed `20260922`), fresh H100 per run, all `NVIDIA H100 80GB HBM3`.

Config: QD4 logical, 64 MiB, full-file, global 4.0 ms start-to-start pacer on **all** physical attempts (originals + rescues), single bounded rescue lane, source-only.
Raw: `hedge_runs/hx-*.json`, `hedge.log`, `FINAL_60.txt`; engine `run_hedge_probe`; analysis `tools/analyze_hedge_interim.py`.

---

## 1. Final results (15 runs per arm)

| metric | C (no hedge) | H75 | H125 | H200 |
|---|---:|---:|---:|---:|
| runs | 15 | 15 | 15 | 15 |
| logical median | 45.8 | 45.0 | 46.6 | **44.0** |
| logical mean | 59.0 | 58.5 | **53.1** | 53.6 |
| logical p95 | 118.2 | 98.0 | **81.6** | 78.5 |
| logical p99 | 162.1 | 123.3 | **105.8** | 114.0 |
| logical worst | 2609 | **3144** | 2537 | **3736** |
| reads ≥500 | **9** | **10** | **5** | 6 |
| reads ≥1000 | 5 | **6** | **1** | 5 |
| runs ≥500 | 3 | 2 | **1** | **1** |
| runs ≥1000 | 1 | **2** | 1 | 1 |
| median wall ms | 1839 | 1808 | 1795 | **1694** |
| mean wall ms | 2405 | **2689** | **2051** | 2263 |
| worst wall ms | 7564 | **12697** | 5021 | 9093 |
| median GB/s | 4.374 | 4.450 | 4.482 | **4.750** |
| mean GB/s | 3.951 | 4.001 | 4.248 | **4.384** |
| hedges launched | 0 | **77** | 4 | 2 |
| rescue wins | 0 | 19 | 0 | 0 |
| amplification | 1.0000 | 1.0428 | 1.0022 | 1.0011 |

---

## 2. ⚠ Correction: my interim headline was overturned by 2 more runs per arm

At 13 runs/arm I reported **"control is the only arm with zero `≥1000 ms` reads"** (control worst 934 ms). At 15 runs/arm that is **false**:

| cutpoint | C worst | C ≥1000 | C runs ≥1000 | H125 ≥1000 |
|---|---:|---:|---:|---:|
| 13 runs/arm | 934 ms | **0** | 0 | 1 |
| **15 runs/arm** | **2609 ms** | **5** | **1** | 1 |

Control picked up a sick run in its 14th/15th observation and went from the cleanest tail to **5 reads ≥1000 ms**. The tail ranking between control and H125 reversed.

**This is the single most important caveat in this report:** the per-arm tail counts at n=15 are driven by **1–2 runs per arm** (`runs ≥1000` is 1 / 2 / 1 / 1). They are **not** stable, and no arm-to-arm tail difference here should be treated as real.

---

## 3. What IS stable across both cutpoints

### 3a. Rescue economics — the decisive finding, identical at 13 and 15 runs

| arm | logical | eligible | launched | lane busy | wins | win rate | launched % | median time saved | mean | max |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| H75 | 1800 | 156 | **77** | **79** | 19 | 24.7% | 4.28% | **2.0 ms** | 3.8 ms | 16.0 ms |
| H125 | 1800 | 6 | 4 | 2 | **0** | 0% | 0.22% | – | – | – |
| H200 | 1800 | 2 | 2 | 0 | **0** | 0% | 0.11% | – | – | – |

**Even when a rescue wins, it saves a median of 2.0 ms — against logical reads of 2500–3700 ms.** Unchanged from the interim cutpoint. Hedging buys rounding error.

### 3b. H75 is harmful — also stable

- **77 launches, lane busy 79 times** — the single rescue lane was occupied *more often than it fired*. Hedge demand is queued behind itself.
- **Worst wall 12,697 ms** — the campaign's only five-figure run (`hx-H75-030`).
- **Highest mean wall (2689 ms)** and **most reads ≥1000 (6)**.
- Fires on **4.28%** of logical reads. 75 ms sits *inside* the healthy p95 (~98–118 ms), so it fires on ordinary reads, not stragglers.

### 3c. The healthy distribution is untouched

Logical medians are 44.0–46.6 ms across all four arms. **Hedging cannot change the healthy distribution** — only the tail, and on the tail it does not help.

---

## 4. Why hedging cannot work here

The mechanism is now well-supported by two independent experiments:

1. **The read path is bandwidth-saturated at QD4.** The QD4/QD8 experiment established this directly: QD4 delivers ~4.8 GB/s and QD8 *lost* 17% throughput while doubling per-read latency.
2. **A rescue is a 64 MiB read on the same file, through the same saturated path, while the original is still in flight.** The two attempts contend for the same bandwidth. When the original is merely *jammed*, the rescue is jammed too, and they finish together — hence the **2 ms** median saving.
3. The rescue can only win when the original is genuinely *stuck*, and even then it must queue on the same path.

**Hedging addresses request-level lateness. The pathology is path-level unavailability.** Adding a second request to a jammed path adds load, not service.

This is consistent with the earlier static audits: `directfs` gives the Sentry one host FD per inode, `preadv2` is stateless across offsets, and the stall lives at or below `hostfd.Preadv2` on a shared per-inode resource. **There is no second path to race on.**

---

## 5. Direct answers

1. **Does hedging improve average full-file time?** **No.** Best mean wall is H125 (2051 ms) vs control (2405 ms), but H125 launched 4 hedges in 1800 reads — that difference is run noise, not hedging. No hedge arm shows a mechanism-backed improvement.
2. **Best median full-file time?** **H200 (1694 ms)**, then H125 (1795), H75 (1808), C (1839). Driven by which runs landed, not by hedging.
3. **Best mean GB/s?** **H200 (4.384)**, then H125 (4.248), H75 (4.001), C (3.951).
4. **Best logical p95?** **H200 (78.5 ms)**, then H125 (81.6).
5. **Best logical p99?** **H125 (105.8)**, then H200 (114.0).
6. **Lowest logical worst read?** **H125 (2537 ms)** — but control is 2609, i.e. effectively tied, and both are far above the earlier QD4@4ms benchmark (828 ms).
7. **Logical ≥500 per arm?** C 9, H75 10, H125 5, H200 6.
8. **Logical ≥1000 per arm?** C 5, H75 6, H125 **1**, H200 5 — **all driven by 1–2 runs per arm; not interpretable.**
9. **Runs containing tails?** ≥500: C 3, H75 2, H125 1, H200 1. ≥1000: C 1, H75 2, H125 1, H200 1.
10. **How often does each delay fire?** H75 4.28% of logical reads, H125 0.22%, H200 0.11%.
11. **How often does the rescue win?** H75 24.7% (19/77); H125 0/4; H200 0/2.
12. **Physical amplification?** H75 1.0428×, H125 1.0022×, H200 1.0011×.
13. **Wall time actually saved when a rescue wins?** **Median 2.0 ms, mean 3.8 ms, max 16.0 ms.** Negligible.
14. **Does 75 ms fire too often and hurt healthy throughput?** **Yes.** 4.28% of reads, lane saturated (79 busy), worst mean wall, the 12.7 s run.
15. **Is 125 ms the best balance?** **Cannot be concluded.** It has the best p99 and mean wall, but it fired 4 times and won 0 — it is functionally the control arm, so its numbers are noise.
16. **Is 200 ms too late?** With 2 launches it cannot be doing anything. Its best-in-class median wall/GB/s are not attributable to hedging, and its worst read (3736 ms) is the campaign's worst.
17. **Does hedging cause additional correlated sickness?** **Supported for H75** (heavy firing, saturated lane, worst mean wall and worst wall). Not attributable for H125/H200 (2–4 launches). The formal hedge-vs-other-worker correlation analysis was not run — the campaign was stopped first.
18. **Best real throughput/tail tradeoff?** **None of the hedge arms beats control on mechanism.** H200 has the best throughput but the worst single read; H125 has the best p99 but is functionally control.
19. **Carry hedging into Golden?** **No.**
20. **If yes, which delay?** **None.**

---

## 6. Recommendation

**Do not carry delayed hedging into Golden.**

The rejection does not rest on the arm-to-arm tail comparison — that is too noisy at n=15 to carry weight. It rests on two stable facts:

1. **A rescue win saves a median of 2 ms** while costing a full duplicate 64 MiB physical read. The hedge is economically pointless even when it succeeds.
2. **The path is bandwidth-saturated and per-inode-shared**, so a rescue cannot obtain service the original could not — it only adds contention. H75 demonstrates the predictable consequence: +12% mean wall, the campaign's only 12.7 s run, and a rescue lane that is busy more often than it fires.

**If hedging is revisited**, the only variant that could plausibly help would avoid duplicating load on the same saturated path — a rescue on a genuinely different path, or a much smaller unit of rescue work. The earlier audits showed we cannot obtain an independent host path for the same inode, so this is not currently available.

---

## 7. Known limitations of this dataset

- **60/100 runs** (15/arm) — stopped early, so the planned 25/arm is not met.
- **Tail counts are not interpretable at this n.** `runs ≥1000` is 1–2 per arm, and the control arm's ranking flipped between 13 and 15 runs.
- **Logical reads within a run are clustered**, not ~1800 independent replicates. With 15 runs/arm, the run is the experimental unit.
- The **formal hedge/other-worker correlation analysis** and the **first-four-launch traces** were not produced, because the campaign was stopped before final analysis.
- **One remote run may have been abandoned**: the local driver was killed while `hx-C-061` was in flight, so that container's result was not saved. No other runs are in flight — the local process is confirmed stopped (0 remaining).
