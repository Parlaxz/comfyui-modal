# Delayed Hedging — Interim Report (52 / 100 runs)

**This is an interim report at 13 completed runs per arm.** The campaign is still running (52/100 done). Numbers may move, but the direction is clear and the mechanism is already identifiable.

Config: QD4, 64 MiB, full-file, global 4.0 ms launch pacer, source-only, fresh H100 per run.
Arms: `C` (control, hedge code path with delay=0), `H75`, `H125`, `H200`.
Raw: `hedge_runs/hx-*.json`, `hedge.log`, `INTERIM.txt`; engine `run_hedge_probe`; schedule seed `20260922`.

---

## 1. Headline — hedging is not helping, and H75 is actively harmful

| metric | C (no hedge) | H75 | H125 | H200 |
|---|---:|---:|---:|---:|
| runs | 13 | 13 | 13 | 13 |
| logical median | 45.9 | 45.1 | 46.8 | **44.1** |
| logical mean | 55.5 | 60.4 | **53.8** | 54.9 |
| logical p95 | 118.6 | 100.9 | **82.1** | 84.7 |
| logical p99 | 137.4 | 124.1 | **106.1** | 116.6 |
| **logical worst** | **934** | **3144** | **2537** | **3736** |
| reads ≥500 | 2 | **10** | 5 | 6 |
| **reads ≥1000** | **0** | **6** | 1 | **5** |
| runs ≥500 | 2 | 2 | 1 | 1 |
| runs ≥1000 | **0** | 2 | 1 | 1 |
| **median wall ms** | 1734 | 1822 | 1795 | **1694** |
| **mean wall ms** | **2041** | **2839** | 2093 | 2351 |
| **worst wall ms** | **2979** | **12697** | 5021 | 9093 |
| median GB/s | 4.640 | 4.416 | 4.482 | **4.750** |
| mean GB/s | 4.164 | 3.897 | 4.197 | **4.326** |
| hedges launched | 0 | **73** | 3 | 2 |
| rescue wins | 0 | 19 | 0 | 0 |
| amplification | 1.000 | 1.047 | 1.002 | 1.001 |

**The control is the only arm with zero `≥1000 ms` logical reads, and it has the best worst-case (934 ms) and the best mean wall (2041 ms).**

**Every hedged arm has worse `≥1000 ms` counts than control: 6 / 1 / 5 versus 0.**

---

## 2. The decisive number: rescue wins save ~2 ms

| arm | launched | wins | win rate | lane busy | launched % of logical | median time saved | mean | max |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| H75 | 73 | 19 | 26.0% | 77 | 4.68% | **2.0 ms** | 3.8 ms | 16.0 ms |
| H125 | 3 | 0 | 0% | 2 | 0.19% | – | – | – |
| H200 | 2 | 0 | 0% | 0 | 0.13% | – | – | – |

**Even when the rescue wins, it saves a median of 2 ms — against logical reads of 2500+ ms.** The hedge is not rescuing anything meaningful; it is buying rounding error.

### Why this happens, mechanistically

This is the key insight and it is now well-supported:

1. **The path is bandwidth-saturated at QD4.** The QD4/QD8 experiment established this directly: QD4 already delivers ~4.8 GB/s, and pushing to QD8 *reduced* throughput 17% while doubling per-read latency. The host read path cannot absorb more concurrent work.
2. **A rescue read is 64 MiB on the same file, through the same saturated path, while the original is still in flight.** The two attempts contend for the same bandwidth. If the original is *slow*, the rescue is slow too — roughly equally.
3. **Therefore the rescue can only win when the original is truly *stuck*, and it cannot win by much when both are merely jammed.** That is exactly what the data show: a 26% win rate at H75, saving ~2 ms.

**Hedging does not address this failure mode.** The sickness is not a request that needs a second attempt; it is a path that has stopped serving. Racing a second request into a jammed path adds load without adding service.

---

## 3. H75 is worse than doing nothing

H75 fired 73 rescues in 13 runs (4.68% of logical reads) and the **lane was busy 77 times** — more often than it fired. The single rescue lane is saturated, so hedge demand is being serialized and queued behind itself.

Consequences visible in the data:

- **Mean wall 2839 ms vs control 2041 ms (+39%)** and vs H125 2093 / H200 2351. H75 has the worst mean wall of all four arms.
- **Worst wall 12,697 ms** — the only 12.7-second run in the campaign, versus control's 2979 ms. Runs `hx-H75-030` (wall 12697, 9 reads ≥500, 5 ≥1000, logical max 3144) and `hx-H75-049` (35 hedges, 12 wins, amp 1.292, wall 3226).
- **10 reads ≥500 and 6 ≥1000** — the worst of any arm.

**75 ms sits inside the healthy p95 (~70–120 ms), so it fires on ordinary reads, not just stragglers.** That is precisely the "fires too often, adds unnecessary duplicate traffic" branch flagged in the task spec — now observed.

---

## 4. H125 and H200 barely fire, so they barely change anything

- **H125**: 3 launches in 1560 logical reads (0.19%). 5 reads ≥500, 1 ≥1000, worst 2537 ms. It does have the **best logical p95/p99** (82.1 / 106.1) — mildly better than control (118.6 / 137.4) — but its worst case (2537 ms) is **2.7× worse than control's 934 ms**, and it has a `≥1000` run that control does not.
- **H200**: 2 launches (0.13%). **Best median wall (1694 ms) and best GB/s (4.750 / 4.326)** — but 5 reads ≥1000 and worst 3736 ms.

At these rates the arms are effectively **control plus rare duplicate reads**, so the observed tails are likely the underlying pathology rather than hedge-induced — but that also means **hedging is not doing anything useful**.

---

## 5. Do hedges create additional sickness?

**Interim answer: H75 yes; H125/H200 inconclusive.**

- **H75**: with 73 launches and a saturated rescue lane (77 busy), it adds sustained extra 64 MiB traffic. Its mean wall rose 39% and it owns the 12.7 s run. The correlated-sickness concern is supported.
- **H125/H200**: 3 and 2 launches respectively — far too few to attribute their tails to hedging. Their `≥1000` events most likely reflect the underlying pathology that control also experiences (control's own worst is 934 ms; the historical QD4@4ms worst across 35 runs was 828 ms).

I have **not** run the formal "is a hedge launch temporally associated with another worker going ≥250/≥500/≥1000" analysis across the full 100 runs yet.

---

## 6. Direct answers (interim)

1. **Does hedging improve average full-file time?** **No.** Control 2041 ms is better than every hedge arm (H75 2839, H125 2093, H200 2351).
2. **Best median full-file time?** **H200 (1694 ms)** — narrowly ahead of control (1734).
3. **Best mean GB/s?** **H200 (4.326)** — ahead of control (4.164). But it carries 5 reads ≥1000 that control does not.
4. **Best logical p95?** **H125 (82.1 ms)**, then H200 (84.7) — both better than control (118.6).
5. **Best logical p99?** **H125 (106.1)** vs control (137.4).
6. **Lowest logical worst read?** **Control (934 ms)** — every hedge arm is 2.7–4× worse (H75 3144, H125 2537, H200 3736).
7. **Logical ≥500 per arm?** C 2, H75 10, H125 5, H200 6.
8. **Logical ≥1000 per arm?** **C 0**, H75 6, H125 1, H200 5.
9. **Runs containing tails?** ≥500: C 2, H75 2, H125 1, H200 1. ≥1000: **C 0**, H75 2, H125 1, H200 1.
10. **How often does each delay fire?** H75 4.68% of logical reads, H125 0.19%, H200 0.13%.
11. **How often does the rescue win?** H75 26.0% (19/73); H125 0%; H200 0%.
12. **Physical amplification?** H75 1.047×, H125 1.002×, H200 1.001×.
13. **How much wall time does a win actually save?** **Median 2.0 ms, mean 3.8 ms, max 16.0 ms.** Negligible.
14. **Does 75 ms fire too often and hurt healthy throughput?** **Yes.** 4.68% of reads, saturated lane, +39% mean wall, the campaign's only 12.7 s run.
15. **Is 125 ms the best balance?** **Not on this data.** It has the best p95/p99 but the worst-case logical read is 2537 ms against control's 934, and it fired only 3 times — it is not doing meaningful work.
16. **Is 200 ms too late to materially improve the wall?** It has the best median wall and GB/s of any arm, but with only 2 launches it cannot be the hedge doing that; its tails (worst 3736 ms) are unchanged pathology.
17. **Does hedging cause additional correlated sickness?** **Supported for H75** (heavy firing, saturated lane, +39% mean wall, 12.7 s run). Not attributable for H125/H200 at 2–3 launches.
18. **Best real throughput/tail tradeoff?** **Neither hedge arm beats control on tails.** If forced to rank, H200 has the best throughput but a worse worst-case; **control has the only zero-`≥1000` record**.
19. **Carry hedging into Golden?** **No — not on this evidence.**
20. **If yes, which delay?** **None yet.** No hedge arm demonstrates a real improvement.

---

## 7. Recommendation

**Do not carry hedging forward as designed.**

The rationale is not merely that the arms look bad — it is that the mechanism cannot work here:

- The path is **bandwidth-saturated at QD4**, so a duplicate read competes with the read it is meant to rescue. When both are jammed, both finish together: median saving **2 ms**.
- The rescue can only help against a *stuck* request, and even then it must queue on the same path.
- **75 ms fires on ordinary reads** (inside the healthy p95) and measurably degrades the arm.
- Hedging addresses request-level lateness; the pathology is path-level unavailability.

**If hedging is to be revisited**, the only version that could plausibly help is one that does **not** duplicate load on the same saturated path — i.e. a rescue on a *different* path or a much smaller rescue unit of work. Both are outside this experiment's scope, and the earlier audits showed we cannot get an independent path for the same inode.

---

## 8. Status and caveats

- **52/100 runs complete (13 per arm).** The campaign is still running; I have not stopped it.
- Tail counts are driven by a handful of runs (H75's 6 `≥1000` reads come largely from one 12.7 s run). With 13 runs/arm the run-level comparisons are **underpowered**; logical reads within a run are clustered and are **not** ~1560 independent replicates.
- The `<500 ms` distribution is essentially identical across all four arms (medians 44.1–46.8 ms), which is the expected result: **hedging cannot change the healthy distribution**, only the tail — and on the tail it is currently making things worse, not better.
- The formal "do hedge launches correlate with other workers going sick" analysis and the full first-four-launch traces are deferred to the complete 100-run analysis.

**Not run:** threshold tuning, adaptive hedging, multiple rescue lanes, QD8, block-size changes, Golden integration.
