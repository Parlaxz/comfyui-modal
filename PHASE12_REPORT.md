# Phase 1 (pacing 0/2/4 ms) + Phase 2 (deferred munmap) — report

Geometry LOCKED for both phases: **64 MiB / QD4 / 4 reader processes / fresh-window mmap**
(`mmap` exact window -> native memcpy -> `munmap`), MAP_POPULATE removed, pure CPU source I/O,
H100 host (GPU never touched), same `qwen_3_4b.safetensors`, same self-service scheduler,
workspace Testing 5 (`ws_c1487d319820`). Raw artifacts: `pace_runs/` (90 slots), `du_runs/`
(40 slots). Reports: `phase12_report/PHASE12.md` (tables), this file (answers).

**Counting rule (unchanged from the geometry matrix):** per ARM, include regions with **>=3 runs
in that arm**; drop regions with <3 runs; **no US-only filter**; Odin excluded but retained; a
slow run is **never** removed. Targets: 15 counted/arm (Phase 1), 20 counted (Phase 2).

**Interleave (Phase 1):** 30 rounds of 3 arms, each round a different permutation, seed
`20261003`. Verified: each arm exactly 30 launches, every round a full permutation, mean slot
positions 45.4/45.5/45.7.

---

## CONFIRM — the two CARRY optimizations (not re-benchmarked, code-audited)

Both historical CARRY optimizations are **PRESENT** in the mmap harness; nothing had to be
restored.

| CARRY item | status | evidence |
|---|---|---|
| Readers eager/alive before request timing | **PRESENT** | `_mlc_child` does prep -> `ready_count += 1` -> spins on `go` (`source_race_oracle.py:7810-7812`); the parent waits for all `qd` readers ready then releases `go` (`8069`, `8083`). The measured wall is `last_exit - first_enter` where `first_enter` is the first memcpy (`8129-8131`), so timing starts only after readers are up and past prep. |
| Model FD persistent/reused per reader | **PRESENT** | `fd = os.open(file_path, os.O_RDONLY)` once per reader at `7770`, before prep; the whole consumption loop reuses `fd` in `_LIBC.mmap(..., fd, offset)` (`7885`); closed once in `finally` (`7960-7961`). Never reopened per block. |

Also confirmed: `_alloc_gate` (`3644-3655`) returns immediately when `gap_ns == 0`
(`elapsed >= 0` always true), so 0 ms removes **only** the intentional spacing floor — the mutex
remains, nothing else changes.

---

## PHASE 1 — pacing 0 / 2 / 4 ms

| arm | launches | counted | regions counted |
|---|---:|---:|---|
| P0 (0 ms) | 30 | 15 | eu-west 5, asia-northeast1 3, europe-west9 3, CANADA-2 4 |
| P2 (2 ms) | 30 | 15 | CANADA-2 5, uk 5, europe-west2 3, ca 2 |
| P4 (4 ms) | 30 | 15 | CANADA-2 4, us-west 2, asia-northeast1 3, europe-west9 2, ca 3, eu-west 1 |

### Whole-run

| arm | med | mean | p10 | p90 | best | worst | wall med | SD | CV | MAD | p90-p10 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| P0 | 5.592 | 5.442 | 4.397 | 6.897 | 7.192 | 2.344 | 1439 | 1.1815 | 0.2171 | 0.8933 | 2.499 |
| P2 | 6.179 | 5.431 | 2.194 | 7.307 | 7.970 | 2.097 | 1302 | 2.0487 | 0.3772 | 1.5819 | 5.114 |
| P4 | **6.287** | **5.965** | 4.317 | 6.963 | 7.363 | **3.649** | 1280 | 1.0491 | **0.1759** | **0.7738** | 2.646 |

### Operation distribution

| arm | ops | med | p90 | p95 | p99 | p99.5 | worst | >=100 | >=150 | >=250 | >=500 | >=1s | >=2s | per1000 | per TiB | affected |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| P0 | 1800 | 45.2 | 63.7 | 71.2 | 125.0 | 294.4 | 1945.3 | 36 | 17 | 11 | 7 | 2 | 0 | 6.1 | 100.2 | 2/15 (13%) |
| P2 | 1800 | 39.8 | 126.2 | 134.4 | 162.3 | 194.1 | 218.3 | 420 | 29 | 0 | 0 | 0 | 0 | 0.0 | 0.0 | 0/15 (0%) |
| P4 | 1800 | 41.9 | 67.6 | 74.6 | 90.6 | 102.9 | 151.3 | 10 | 1 | 0 | 0 | 0 | 0 | 0.0 | 0.0 | 0/15 (0%) |

### Normalized tails — BOTH definitions, never mixed

| arm | (1) pooled worst / pooled median | (2) max per-run [worst / own median] | p95/med | p99/med |
|---|---:|---:|---:|---:|
| P0 | 43.03 | 65.01 | 1.58 | 2.77 |
| P2 | 5.49 | 3.76 | 3.38 | 4.08 |
| P4 | **3.61** | **2.45** | 1.78 | 2.16 |

*(1) and (2) are different quantities and are reported separately. (1) can be inflated by a
single bad op anywhere in the pooled set; (2) captures the worst single run's internal spread.*

### Execution

| arm | eff conc | max conc | finish spread ms | map_ms | memcpy_ms | unmap_ms | op_wall_ms | min spacing | median spacing |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| P0 | 3.966 | 4 | 1395 | 0.058 | 43.1 | 1.94 | 45.2 | 0.008 | 0.030 |
| P2 | 3.934 | 4 | 1266 | 0.057 | 37.5 | 2.31 | 39.8 | 2.010 | 2.041 |
| P4 | 3.907 | 4 | 1240 | 0.060 | 39.6 | 2.37 | 41.9 | 4.010 | 4.045 |

**Max QD = 4 in every arm** (as required). Achieved spacing matches the configured floor exactly.

### Per provider:region (n>=3)

| arm | provider:region | n | med GB/s | CV | MAD | p10 | p90 | affected |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| P0 | GCP:asia-northeast1 | 3 | 5.665 | 0.1401 | 0.6568 | 5.310 | 6.886 | 0 |
| P0 | GCP:eu-west | 5 | 5.592 | 0.1259 | 0.5414 | 5.075 | 6.552 | 1 |
| P0 | GCP:europe-west9 | 3 | 4.652 | 0.0483 | 0.1656 | 4.312 | 4.710 | 0 |
| P0 | UNSPECIFIED:CANADA-2 | 4 | 6.160 | 0.3264 | 1.1196 | 3.468 | 6.547 | 1 |
| P2 | GCP:europe-west2 | 3 | 2.451 | 0.5875 | 1.6692 | 2.168 | 6.174 | 0 |
| P2 | GCP:uk | 5 | 6.000 | 0.4394 | 1.7397 | 2.194 | 6.621 | 0 |
| P2 | UNSPECIFIED:CANADA-2 | 5 | 6.791 | 0.0672 | 0.3393 | 6.232 | 7.186 | 0 |
| P4 | GCP:asia-northeast1 | 3 | 5.784 | 0.0545 | 0.2220 | 5.284 | 5.817 | 0 |
| P4 | UNSPECIFIED:CANADA-2 | 4 | 6.504 | 0.0257 | 0.1479 | 6.331 | 6.690 | 0 |
| P4 | UNSPECIFIED:ca | 3 | 6.692 | 0.0384 | 0.2081 | 6.528 | 7.028 | 0 |

### Pathological operations (>=250 ms), with provider:region

| arm | run | provider:region | offset | len | op ms | historical hit |
|---|---|---|---:|---:|---:|---|
| P0 | im-03 | GCP:eu-west | 6039797760 | 67108864 | 259.3 | [6039797760] |
| P0 | im-43 | UNSPECIFIED:CANADA-2 | 2013265920 | 67108864 | 730.9 | [2013265920] |
| P0 | im-43 | UNSPECIFIED:CANADA-2 | 4026531840 | 67108864 | 1945.3 | no |
| P0 | im-43 | UNSPECIFIED:CANADA-2 | 6039797760 | 67108864 | 1891.9 | [6039797760] |
| P0 | im-43 | UNSPECIFIED:CANADA-2 | 67108864 | 67108864 | 823.8 | no |
| P0 | im-43 | UNSPECIFIED:CANADA-2 | 2080374784 | 67108864 | 646.6 | no |
| P0 | im-43 | UNSPECIFIED:CANADA-2 | 671088640 | 67108864 | 741.7 | no |
| P0 | im-43 | UNSPECIFIED:CANADA-2 | 6106906624 | 67108864 | 952.8 | no |
| P0 | im-43 | UNSPECIFIED:CANADA-2 | 4496293888 | 67108864 | 379.6 | no |
| P0 | im-43 | UNSPECIFIED:CANADA-2 | 4831838208 | 67108864 | 299.1 | no |
| P0 | im-43 | UNSPECIFIED:CANADA-2 | 7851737088 | 67108864 | 294.4 | no |

All 11 >=250 ms operations in Phase 1 belong to **two runs**: P0 im-03 (one op) and P0 im-43
(eleven ops spread across the whole file). P2 and P4 had **zero**. This is the slow-host-period
signature (contiguous across the file), not bad offsets.

---

## PHASE 2 — deferred munmap

`mmap` -> memcpy -> enqueue retired mapping -> continue; a bounded in-process reaper **thread**
(max 2 retired mappings per reader) performs the `munmap`. Never persistent-segmented: every
block is a fresh exact mapping, retired only after its memcpy has fully returned.

launches=39, counted=20, excluded=19 (incl. 1 Odin). Counted regions: uk 5, us-central 3, ca 2,
europe-west9 4, CANADA-2 2, eu-west 2, asia-northeast1 2.

### Dual clock

| metric | median | mean | min | max |
|---|---:|---:|---:|---:|
| source-ready wall ms | 1424.0 | 1759.6 | 1178.8 | 3186.2 |
| fully-drained wall ms | 1426.1 | 1761.9 | 1180.2 | 3189.0 |
| source-ready GB/s | 5.650 | 5.057 | 2.525 | 6.825 |
| fully-drained GB/s | 5.642 | 5.049 | 2.523 | 6.817 |
| **final drain penalty ms** | **2.24** | 2.30 | 1.39 | 3.10 |

### Reaper telemetry (summed over counted runs unless noted)

| metric | value |
|---|---:|
| queue_full_events (total) | **0** |
| max_queue_depth (max over runs) | **1** |
| avg_queue_depth (mean of per-run avgs) | 1.000 |
| reaper_queue_wait_ms_total | **0.00** |
| munmap_reaper_wall_ms_total | 5402.8 |
| munmaps_completed_total | 2400 |
| munmaps_completed_during_source_work | 2376 |
| munmaps_remaining_at_source_completion | 24 |
| live_mapping_peak (max) | 1 |
| **mapping_leaks_after_drain** | **0** |
| map_errors | 0 |
| unmap_errors | 0 |

### Whole-run + operation distribution

- n=20, med **5.642**, mean 5.049, p10 2.987, p90 6.633, best 6.817, worst 2.523, wall med 1426
- SD 1.4009, CV 0.2774, MAD 1.1189, p90-p10 3.646
- ops 2400, med 46.5, p95 108.0, p99 142.3, worst 2303.4
- >=100 188, >=150 19, >=250 7, >=500 5, >=1s 3, >=2s 1, affected 1/20 (5%)
- tails: (1) pooled worst/pooled med **49.54**; (2) max per-run worst/own med **71.88**
- eff conc 3.876, max conc 4, finish spread 1378, map 0.174, memcpy 46.1, unmap 0.00,
  retire_wait 0.055, op_wall 46.5, spacing 4.002

---

## Matched comparison — Phase 2 vs Phase 1 P4 control

The counting cap selects by filename order, so the capped-set comparison truncates P4's later runs
in shared regions and is misleading. The fair comparison uses **all valid non-odin runs** per
region, restricted to regions with n>=3 on **both** sides.

| provider:region | P4 n | P4 med | DU n | DU med | delta |
|---|---:|---:|---:|---:|---:|
| GCP:asia-northeast1 | 5 | 5.382 | 8 | 5.724 | **+6.4%** |
| GCP:eu-west | 3 | 6.084 | 3 | 5.509 | −9.4% |
| GCP:europe-west9 | 4 | 5.955 | 4 | 5.708 | −4.2% |
| UNSPECIFIED:CANADA-2 | 5 | 6.492 | 6 | 6.681 | **+2.9%** |
| UNSPECIFIED:ca | 3 | 6.692 | 4 | 6.672 | −0.3% |

Matched-restricted pooled: P4 **6.331** (n=20) vs DU **5.853** (n=25) -> **−7.5%**.

**Placement overlap is sufficient** (5 shared regions with n>=3 both sides; P4 matched fraction
0.87), so per the control instruction **no additional interleaved 4 ms synchronous controls were
added** — the P4 cohort supplies the matched evidence.

**Mechanism ceiling:** in the synchronous control, `munmap` is 2.294 ms of a 43.6 ms source-path
op — only **5.3%**. Even a perfect deferral can recover at most ~5%, and the concurrent reaper's
contention offsets it.

---

## Answers

### PACING

1. **How much throughput does 0 ms gain/lose vs 2 and 4?** 0 ms **loses**. Median: P0 5.592 vs
   P2 6.179 (**+10.5%**) vs P4 6.287 (**+12.4%**). Mean: P0 5.442 vs P2 5.431 (flat) vs P4 5.965
   (**+9.6%**). So 0 ms costs ~10–12% of median throughput relative to 2/4 ms.
2. **How does each affect whole-run variance?** P4 is best (CV 0.1759, MAD 0.7738, spread 2.646);
   P0 is intermediate (CV 0.2171, MAD 0.8933, spread 2.499); **P2 is worst** (CV 0.3772, MAD
   1.5819, spread 5.114) — driven by its GCP:uk (CV 0.4394) and GCP:europe-west2 (CV 0.5875,
   med 2.451) draws, i.e. region composition, not pacing.
3. **How does each affect operation tails?** P0 has by far the worst tail (worst 1945.3 ms,
   11 ops >=250 ms, 7 >=500 ms, 2 >=1 s, 13% of runs affected). **P2 and P4 both have zero
   >=250 ms operations and 0% affected runs.** But P2's mid-tail is heavier than P4's
   (p90 126.2 vs 67.6, p95 134.4 vs 74.6, p99 162.3 vs 90.6).
4. **Does 4 ms actually suppress tails?** **Yes** — P4 is the cleanest arm on every tail measure:
   0 ops >=250 ms, 0% affected, best normalized tails ((1) 3.61, (2) 2.45), best p99/med (2.16).
5. **Is 2 ms a useful middle ground?** **Not supported by this evidence.** P2 has the worst CV
   (0.3772), worst MAD (1.5819), worst spread (5.114) and a heavier p90–p99 than P4, despite
   having 0 ops >=250 ms. Its variance is region-driven, so the arm itself is not discredited —
   but 2 ms shows no advantage over 4 ms here.
6. **Is 0 ms stable enough to consider?** On this evidence, **no**: it has the lowest median
   (5.592), the worst tail severity ((1) 43.03, (2) 65.01) and 13% affected runs. Its >=250 ms
   ops trace to one slow CANADA-2 host period (im-43, 11 ops spread across the file), which is a
   placement event rather than a pacing effect — but the arm still carries the most tail risk.
7. **Are differences consistent within provider:region?** **Only partly.** CANADA-2 appears in all
   three arms: P0 6.160 (n=4), P2 6.791 (n=5), P4 6.504 (n=4) — P2 highest there. asia-northeast1
   appears in P0 (5.665, n=3) and P4 (5.784, n=3) — near-equal. eu-west appears in P0 (5.592, n=5)
   and P4 (6.084, n=1). The three arms drew **different region mixes**, so cross-arm per-region
   overlap is thin (only CANADA-2 has n>=3 in all three) and the direction is **not consistent**.

### DEFERRED MUNMAP

8. **Does removing munmap from the critical path improve source-ready wall?** **No consistent
   improvement.** DU source-ready median 5.650 GB/s vs P4 6.287 (pooled) / 6.331 (matched
   restricted). Matched per-region deltas are **mixed** (+6.4% asia-northeast1, +2.9% CANADA-2,
   −0.3% ca, −4.2% europe-west9, −9.4% eu-west), which is consistent with noise around zero.
9. **By how much?** Matched-restricted pooled: **−7.5%** (slightly slower, not faster). The
   ceiling for any gain was **5.3%** (munmap's share of the source-path op), so there was very
   little to recover even before reaper contention.
10. **Does the reaper keep up continuously?** **Yes.** 2376 of 2400 munmaps completed during
    active source work; only 24 remained at source completion; the queue never exceeded depth 1.
11. **How often does the bounded queue backpressure source workers?** **Never** — 0 queue-full
    events and 0.00 ms of total reaper queue wait. The cap of 2 was never reached.
12. **What is the fully-drained cost?** **2.24 ms median** (mean 2.30, max 3.10) on a ~1424 ms
    wall — about **0.16%**.
13. **Is the improvement real overlap, or merely moving cleanup after the source timer?**
    Cleanup **is** genuinely overlapped (only ~2 ms of unmapping is left for the drain), so it is
    not merely deferred past the timer. But because there is **no net source-ready gain**, there
    is no improvement to attribute — the reaper's concurrent work offsets the removed inline cost.
14. **Does deferred munmap change variance or tails?** **Yes, slightly worse.** DU CV 0.2774 vs P4
    0.1759; DU affected 1/20 (5%) vs P4 0/15 (0%); DU worst op 2303.4 ms vs P4 151.3 ms. The DU
    tail is one run (im-11, CANADA-2) whose 7 ops >=250 ms are spread across the file — the same
    slow-host signature as P0's im-43.
15. **Is it safe/clean enough to carry?** **Mechanically yes**: 0 mapping leaks after drain,
    0 map errors, 0 unmap errors, 2400/2400 munmaps completed, bounded queue enforced (max depth
    1 vs cap 2), drain penalty ~2 ms. **But it shows no performance benefit**, so carrying it
    would add a thread and complexity for nothing measured here.

### Historical ~6.5 GB/s M2 cohort

| cohort | n | median | p10 | worst |
|---|---:|---:|---:|---:|
| Historical M2 (`mmap_source`, fresh-window) | 49 | **6.439** | 5.119 | 1.306 |
| Historical P (`selfservice_allocator`) | 52 | 5.904 | 4.580 | 3.594 |
| Today P4 sync (matched-restricted) | 20 | **6.331** | 5.217 | 4.875 |
| Today DU (matched-restricted) | 25 | 5.853 | 5.343 | 2.523 |

Historical M2 beat historical P by **8.3%** on matched regions (6.498 vs 5.959). **Today's P4
sync matched-restricted median (6.331) is within 1.7% of historical M2 (6.439)** — so there is
**no code regression** in the fresh-window path. The differences are attributable to
**provider:region / placement**: historical M2 was dominated by `us-west` (20/49) and `us-east`
(9/49), while today's P4 drew CANADA-2/ca/asia-northeast1/europe-west9, and the DU cohort drew an
even heavier slow-region share (7 `uk` runs).

## Honest limitations

- Phase-1 arms drew **different region mixes**; only CANADA-2 has n>=3 in all three arms, so
  cross-arm per-region evidence is thin and pacing differences are partly composition.
- Phase-2 DU vs P4 matched evidence is mixed-direction; the pooled −7.5% is **not** evidence of a
  code regression (per the standing instruction not to infer one from a pooled median).
- n=15 (Phase 1) and n=20 (Phase 2) counted; per-region sub-cells are n=1–8.
- The DU cohort contains one catastrophic CANADA-2 run; it is retained in all reported statistics.
- `>=250 ms` is an absolute threshold; the relative measures are reported alongside.
- No MAP_SHARED, CPU-affinity or other optimization was started.
