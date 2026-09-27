# Launch-Spacing Causal Experiment — Report

H100 source-only, 64 MiB reads, full-file, no primer/sentinels/H2D/CUDA/cache work.
Corpus: 27 fresh H100 runs (9 arms × 3 reps, rotated order) + Part 0 over the existing 108-run corpus.
Raw: `launch_spacing_runs/*.json`, `launch_spacing_runs/screen.log`, `sentinel_runs/launch_spacing_part0.txt`, `sentinel_runs/launch_spacing_gpu.txt`

---

## 1. Existing-corpus launch-spacing analysis (Part 0)

### 1a. The corpus cannot test the hypothesis — this is the key Part 0 finding

**On H100, generation-0 launches are essentially always simultaneous:**

```
gen0 having another gen0 launch within  1 ms: 214/224 = 95.5%   (H100)
gen0 having another gen0 launch within  2 ms: 214/224 = 95.5%
gen0 having another gen0 launch within  4 ms: 214/224 = 95.5%
gen0 having another gen0 launch within 16 ms: 218/224 = 97.3%
```

So in the historical H100 corpus the `<1 ms` bin holds 168 of 176 gen-0 reads and **there is essentially no staggered-gen-0 contrast to exploit**. The staggered launches (1–32 ms) come almost entirely from **RTX** runs, which is a different GPU with a far milder pathology (worst 1470 ms vs 33588 ms).

### 1b. What the corpus does show (H100, gen-0)

| gap_ms | n | ≥250 | ≥500 | ≥1000 | rates |
|---|---|---|---|---|---|
| <1 | 168 | 105 | 75 | 53 | 62.5% / 44.6% / 31.5% |
| 1-2 | 1 | 0 | 0 | 0 | – |
| 32-64 | 2 | 1 | 1 | 0 | – |
| ≥64 | 5 | 4 | 3 | 1 | 80% / 60% / 20% |

H100 gen0–3, and gen4+ (context):

| gap_ms | gen0-3 n | gen0-3 ≥500 | gen4+ n | gen4+ ≥500 |
|---|---|---|---|---|
| <1 | 324 | 26.2% | 917 | 0.3% |
| 1-2 | 53 | 0.0% | 490 | 0.0% |
| 2-4 | 46 | 8.7% | 612 | 0.2% |
| 4-8 | 50 | 2.0% | 843 | 0.1% |
| 8-16 | 58 | 3.4% | 1175 | 0.4% |
| 16-32 | 95 | 11.6% | 987 | 0.3% |
| 32-64 | 79 | 8.9% | 332 | 0.0% |
| ≥64 | 141 | 22.7% | 140 | 13.6% |

**Why these numbers cannot establish causation:** a `≥1 ms` gap in gen0–3 is largely a proxy for *"this read is not part of the opening simultaneous burst"* (and, in the `≥64 ms` bin, *"the previous read was slow"* — pure consequence). The `≥64 ms` bin being sick is expected: its gap **is** the preceding block duration. **Gen4+ is clean at every spacing**, which says the effect is a start-of-run burst phenomenon, not spacing in general.

### 1c. Overlap of sick reads (H100, all reads)

```
sick >=500ms : n=237  mean active_at_enter=4.42  median=5  max=7
healthy <250 : n=12667 mean active_at_enter=3.12 median=3  max=7
```

Sick reads carry *more* overlap — consistent with either hypothesis, so not discriminating.

**Part 0 verdict: inconclusive by construction.** It motivates the experiment and cannot replace it.

---

## 2. QD1 serial oracle

| run | worst preadv | ≥250 | ≥500 | ≥1000 | frac overlap | eff concurrency |
|---|---|---|---|---|---|---|
| ls-qd1-r1 | 48.7 ms | 0 | 0 | 0 | 0.000 | 1.00 |
| ls-qd1-r2 | 59.4 ms | 0 | 0 | 0 | 0.000 | 1.00 |
| ls-qd1-r3 | 48.1 ms | 0 | 0 | 0 | 0.000 | 1.00 |

**QD1 is completely clean.** No pathologically slow `preadv` arises when no two workload reads overlap. Concurrency or temporal interaction is **required**. (Throughput is poor, as expected for an oracle: ~1.8–2.2 GB/s.)

---

## 3. 27-run pacing screen — per run

| run | qd | gap | GB/s | worst ms | ≥250 | ≥500 | ≥1000 | obs min gap | obs med gap | frac ovl | eff conc |
|---|---|---|---|---|---|---|---|---|---|---|---|
| ls-qd1-r1 | 1 | 0 | 1.850 | 49 | 0 | 0 | 0 | 32.99 | 36.00 | 0.000 | 1.00 |
| ls-qd1-r2 | 1 | 0 | 1.832 | 59 | 0 | 0 | 0 | 32.90 | 36.16 | 0.000 | 1.00 |
| ls-qd1-r3 | 1 | 0 | 2.235 | 48 | 0 | 0 | 0 | 25.59 | 29.55 | 0.000 | 1.00 |
| ls-g0-r1 | 4 | 0 | 2.765 | **1581** | 4 | 4 | **4** | 0.01 | 7.62 | 0.983 | 3.91 |
| ls-g0-r2 | 4 | 0 | 5.976 | 163 | 0 | 0 | 0 | 0.02 | 7.65 | 0.992 | 3.87 |
| ls-g0-r3 | 4 | 0 | 5.437 | 213 | 0 | 0 | 0 | 0.01 | 8.21 | 0.992 | 3.90 |
| ls-g1-r1 | 4 | 1 | 4.643 | 111 | 0 | 0 | 0 | 1.00 | 7.54 | 0.983 | 3.72 |
| ls-g1-r2 | 4 | 1 | 4.486 | 147 | 0 | 0 | 0 | 1.05 | 11.38 | 0.917 | 3.37 |
| ls-g1-r3 | 4 | 1 | 3.840 | 151 | 0 | 0 | 0 | 1.05 | 12.11 | 0.983 | 3.74 |
| ls-g2-r1 | 4 | 2 | 4.668 | 129 | 0 | 0 | 0 | 2.02 | 8.62 | 0.975 | 3.70 |
| ls-g2-r2 | 4 | 2 | 4.976 | 167 | 0 | 0 | 0 | 2.06 | 9.80 | 0.992 | 3.67 |
| ls-g2-r3 | 4 | 2 | 4.930 | 137 | 0 | 0 | 0 | 2.07 | 10.68 | 0.983 | 3.76 |
| ls-g4-r1 | 4 | 4 | 6.575 | 148 | 0 | 0 | 0 | 4.01 | 4.96 | 0.983 | 3.56 |
| ls-g4-r2 | 4 | 4 | 6.199 | 98 | 0 | 0 | 0 | 4.04 | 6.59 | 0.983 | 3.59 |
| ls-g4-r3 | 4 | 4 | 5.848 | 85 | 0 | 0 | 0 | 4.00 | 6.09 | 0.983 | 3.52 |
| ls-g8-r1 | 4 | 8 | 5.829 | 105 | 0 | 0 | 0 | 8.03 | 8.99 | 0.992 | 3.53 |
| ls-g8-r2 | 4 | 8 | 3.910 | 681 | 2 | 2 | 0 | 8.00 | 8.98 | 0.992 | 3.10 |
| ls-g8-r3 | 4 | 8 | 4.776 | 104 | 0 | 0 | 0 | 8.04 | 9.06 | 0.975 | 3.57 |
| ls-g16-r1 | 4 | 16 | 3.285 | 409 | 2 | 0 | 0 | 16.09 | 16.71 | 0.975 | 2.35 |
| ls-g16-r2 | 4 | 16 | 3.938 | 91 | 0 | 0 | 0 | 16.01 | 16.30 | 0.975 | 2.09 |
| ls-g16-r3 | 4 | 16 | 3.944 | 83 | 0 | 0 | 0 | 16.03 | 16.26 | 0.958 | 1.97 |
| ls-g32-r1 | 4 | 32 | 2.055 | 60 | 0 | 0 | 0 | 32.00 | 32.77 | 0.175 | 0.95 |
| ls-g32-r2 | 4 | 32 | 2.066 | 94 | 0 | 0 | 0 | 32.00 | 32.27 | 0.958 | 1.18 |
| ls-g32-r3 | 4 | 32 | 1.790 | 698 | 2 | 2 | 0 | 32.05 | 32.46 | 0.950 | 1.30 |
| ls-g64-r1 | 4 | 64 | 1.044 | 48 | 0 | 0 | 0 | 64.01 | 64.59 | 0.000 | 0.48 |
| ls-g64-r2 | 4 | 64 | 1.045 | 49 | 0 | 0 | 0 | 64.00 | 64.46 | 0.000 | 0.51 |
| ls-g64-r3 | 4 | 64 | 0.957 | 885 | 2 | 2 | 0 | 64.01 | 64.47 | 0.025 | 0.68 |

All 27 runs are `NVIDIA H100 80GB HBM3`; no wrong-GPU contamination.

---

## 4. Per-arm summary

| arm | n | med GB/s | min GB/s | worst ms | ≥250 | ≥500 | ≥1000 | obs med gap | frac ovl | eff conc |
|---|---|---|---|---|---|---|---|---|---|---|
| qd1 | 3 | 1.850 | 1.832 | 59 | 0 | 0 | 0 | 36.00 | 0.000 | 1.00 |
| **g0** | 3 | 5.437 | 2.765 | **1581** | **4** | **4** | **4** | 7.65 | 0.992 | 3.90 |
| **g1** | 3 | 4.486 | 3.840 | 151 | **0** | **0** | **0** | 11.38 | 0.983 | 3.72 |
| **g2** | 3 | 4.930 | 4.668 | 167 | **0** | **0** | **0** | 9.80 | 0.983 | 3.70 |
| **g4** | 3 | **6.199** | 5.848 | 148 | **0** | **0** | **0** | 6.09 | 0.983 | 3.56 |
| g8 | 3 | 4.776 | 3.910 | 681 | 2 | 2 | 0 | 8.99 | 0.992 | 3.53 |
| g16 | 3 | 3.938 | 3.285 | 409 | 2 | 0 | 0 | 16.30 | 0.975 | 2.09 |
| g32 | 3 | 2.055 | 1.790 | 698 | 2 | 2 | 0 | 32.46 | 0.950 | 1.18 |
| g64 | 3 | 1.044 | 0.957 | 885 | 2 | 2 | 0 | 64.47 | 0.000 | 0.51 |

### Generation breakdown (all arms)

```
  qd1   | g0 max=59  ge500=0  | g1..g3 all clean
  g0    | g0 max=1581 ge500=4 ge1000=4 | g1 max=117 | g2 max=62 | g3 max=71
  g1    | g0 max=151 ge500=0 | g1 87 | g2 100 | g3 147       ← all clean
  g2    | g0 max=167 ge500=0 | g1 75  | g2 83  | g3 72        ← all clean
  g4    | g0 max=148 ge500=0 | g1 45  | g2 57  | g3 44        ← all clean
  g8    | g0 max=681 ge500=2 | rest clean
  g16   | g0 max=409 ge500=0 | rest clean
  g32   | g0 max=698 ge500=2 | rest clean
  g64   | g0 max=885 ge500=2 | rest clean
```

**Every `≥500 ms` read in the entire screen is a generation-0 read.** Later generations are clean in every arm, at every spacing — consistent with Part 0.

---

## 5. First-four-launch table

The decisive contrast:

```
ls-g0-r1 (gap 0)   :: #0w3 t=0.0  lat=1400 act=0 | #1w0 t=0.6 gap=0.64 lat=1459 act=1
                      | #2w1 t=0.7 gap=0.06 lat=1581 act=2 | #3w2 t=0.7 gap=0.03 lat=1512 act=3
ls-g1-r1 (gap 1)   :: #0w3 t=0.0  lat=50  act=0 | #1w0 t=1.4 gap=1.44 lat=97   act=1
                      | #2w2 t=49.4 gap=47.99 lat=105 act=2 | #3w0 t=98.9 gap=49.49 lat=48 act=1
ls-g2-r3 (gap 2)   :: #0w3 t=0.0  lat=46 | #1w2 t=2.1 gap=2.07 lat=137 | ...
ls-g4-r3 (gap 4)   :: #0w3 t=0.0  lat=40 | #1w0 t=4.4 gap=4.39 lat=76  | ...
```

**In `ls-g0-r1` all four gen-0 reads launched within 0.7 ms and all four took 1400–1581 ms.** In `ls-g1-r1` the first *pair* was separated by only **1.44 ms** and both were clean (50, 97 ms).

**The collision window is therefore sub-millisecond to ~1 ms.**

---

## 6. Actual gap validation (requested vs observed)

The pacer's floor is exact; the median drifts above target because the wait loop uses `time.sleep` in ≤1 ms steps and gVisor's sleep granularity overshoots.

| arm | requested | observed min | observed median | verdict |
|---|---|---|---|---|
| g0 | 0 | 0.01–0.02 | 7.6–8.2 | gate traversed, no enforced gap ✔ |
| g1 | 1 | **1.00–1.05** | 7.5–12.1 | floor exact ✔ |
| g2 | 2 | **2.02–2.07** | 8.6–10.7 | floor exact ✔ |
| g4 | 4 | **4.00–4.04** | 5.0–6.6 | floor exact, tightest median ✔ |
| g8 | 8 | **8.00–8.04** | 9.0 | floor exact ✔ |
| g16 | 16 | **16.01–16.09** | 16.3–16.7 | tightly controlled ✔ |
| g32 | 32 | **32.00–32.05** | 32.3–32.8 | tightly controlled ✔ |
| g64 | 64 | **64.00–64.01** | 64.5 | tightly controlled ✔ |

**The configured gap is not the causal variable — the observed floor is.** The floor hits the request exactly for every arm.

*(One artefact worth recording: at gap ≥32 the gate occasionally stalls a worker for ~700 ms rather than admitting it at the next slot — visible as `#2w0 t=832.9` in `ls-g64-r3` after `#1w2 t=64.6`. The observed median gap is still 64.5 ms so the arm is valid, but the fine-grained wait is coarse.)*

---

## 7. Causal verdict

**SUPPORTS THE LAUNCH-COLLISION HYPOTHESIS — with a very sharp, sub-millisecond threshold — and material overlap is preserved at the clean spacings.**

Reasoning:

1. **QD1 is clean** (0/3 runs, 0 reads ≥250 ms, zero overlap). Simple serialized-read fighting is weakened; a concurrency/temporal interaction is required.
2. **The gap-0 control is catastrophic**: `ls-g0-r1` produced four `≥1000 ms` reads, one on each worker, all launched within 0.7 ms. This reproduces the historical gen-0 signature exactly.
3. **The `≥1000 ms` class is eliminated at every gap ≥1 ms**: 4 occurrences at gap 0, **0 occurrences anywhere else**. This is the cleanest separation in the data.
4. **Gaps 1, 2 and 4 ms produced zero reads ≥250 ms across 9 runs** while retaining **98% overlap and ~3.6–3.7 effective concurrency** (control: 3.90). This is the "Result E" shape — a threshold with overlap intact.
5. **The threshold sits between ~0.6 ms and ~1.4 ms** (ls-g0-r1's 0.64 ms pair both sick vs ls-g1-r1's 1.44 ms pair both clean).

**Honest counter-evidence I am not burying:**

- **Only 1 of 3 runs was sick in each of g0, g8, g32 and g64.** At run granularity, n=3 gives 1/3 vs 0/3 — **not statistically distinguishable**. The read-level signal (`≥1000 ms`: 4 vs 0) is much stronger than the run-level signal.
- **Arms g8, g32 and g64 each showed 2 gen-0 reads ≥500 ms.** Those cannot be collision events: at g64 `frac_ovl = 0.000`, i.e. fully serialized, yet one run still produced 885 and 820 ms reads. Those look like the **sporadic baseline** rate we already know exists, not a spacing effect — but I cannot prove that from n=3.
- **The g16 arm showed 2 reads ≥250 ms** (worst 409) with eff_conc 2.09 — its own mild anomaly.
- The **gap-0 arms show only 1/3 sick runs here**, whereas the historical H100 gen-0 rate was far higher. The screen under-sampled the pathology; gap 0 is not a strong positive control at n=3.

**Net: the hypothesis is supported on the strength of the `≥1000 ms` separation and the 0/9 clean result at 1–4 ms with overlap preserved, but n=3 makes this a screen, not proof.**

---

## 8. Smallest clean spacing

**1 ms is the smallest spacing that was fully clean** across all three reps (0 reads ≥250 ms, worst 151 ms), with overlap preserved (frac_ovl 0.983, eff_conc 3.72).

**4 ms is the recommended spacing** if one wants margin: it was equally clean (worst 148 ms), had the **highest median throughput of any arm (6.199 GB/s)**, the tightest observed median gap (6.09 ms), and `frac_ovl` 0.983 / eff_conc 3.56.

**This is NOT production-proven.** Any non-zero gap ≥1 ms clearing the catastrophic class across 3 runs is a screen result.

---

## 9. Did overlap survive at that spacing?

**Yes — and this is the crux of the whole exercise.**

| arm | frac entered with another read active | effective concurrency | vs control |
|---|---|---|---|
| g0 (control) | 0.992 | 3.90 | 100% |
| g1 | 0.983 | 3.72 | **95%** |
| g2 | 0.983 | 3.70 | **95%** |
| g4 | 0.983 | 3.56 | **91%** |

At 1–4 ms spacing the workers still overlap almost always (~98% of reads enter with another active) and retain **91–95% of the control's effective concurrency**, while the catastrophic `≥1000 ms` class disappears.

**This is not QD1.** QD1 shows `frac_ovl = 0.000`, `eff_conc = 1.00` and ~1.8–2.2 GB/s. The paced arms show `eff_conc ≈ 3.6–3.7` and 3.8–6.6 GB/s — roughly **2–3× QD1 throughput**.

---

## 10. Recommended next step

**Run the confirmation: 10 fresh H100 runs at gap 0 vs 10 at gap 4 ms** — same geometry (64 MiB, full-file, source-only, no primer/sentinels).

This is warranted because the screen exposes a clear threshold with overlap intact, but n=3 cannot separate a 1/3 run-level rate from 0/3.

Details for the confirmation:
- **Gap 4 ms**, not 1 ms — 4 ms was equally clean, fastest, and gives margin above the observed sub-millisecond collision window.
- Keep the gap-0 control in the comparison rather than relying on the historical corpus, since this screen's gap-0 arm was only 1/3 sick.
- Report the same read-level counters (`≥250/500/1000`) as primary and run-level rate as secondary.
- If the 20-run confirmation holds, the pacing gate is a **cheap, in-process, single-variable change** that preserves QD4 overlap — which is a very different outcome from serializing I/O.

**I have not launched it**, per your instruction to stop and report first.
