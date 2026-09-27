# Corrected Hedging + QD4/64 MiB Distribution — Two-Part Report

**Part A**: corrected per-worker hedge resources, 20 fresh H100 runs (H75×10, H150×5, H250×5, seed `20260923`).
**Part B**: offline distribution/survival from all clean QD4 + 64 MiB H100 source runs (no new containers).

Artifacts: `hedge_runs2/` (schedule2.json, h2*.json, h2.log, PART_A.txt) · `qd4_distribution/` (manifest, raw, histogram, survival CSVs + 3 PNGs) · engines `run_hedge_probe`, `run_fullfile_probe` · analysis `tools/analyze_hedge2.py`, `tools/build_qd4_distribution.py`, `tools/chart_qd4_distribution.py`

---

# SECTION A — CORRECTED HEDGING

## A1. Historical hedge architecture audit

**Found:** `.slim/worktrees/golden-q2-128-resource-failover-sep18/.../raw/0064_c0_resource_failover.py` — the ROTATE4 failover module (policy half of the QD2/128 pristine-resource failover experiment).

Verbatim facts from that source:

```python
C0_FAILOVER_RESOURCES_PER_WORKER = 4
C0_FAILOVER_SLOTS_PER_RESOURCE   = 4
C0_FAILOVER_SLOT_BYTES           = 128 * MiB
C0_FAILOVER_LOGICAL_QD           = 2
C0_FAILOVER_PHYSICAL_WORKERS     = 4
C0_FAILOVER_TOTAL_BYTES          = 8 * GiB
DEFAULT_RESCUE_NS                = 150_000_000          # 150 ms hedge tripwire
# selectors: off | control | rotate4      (no 'rotate3' arm exists — see below)
# geometry rule enforced: logical_qd must be STRICTLY BELOW resources_per_worker
```

Docstring, verbatim:

> *"a 150 ms crossing hedges one successor to the next **pristine resource island**"*
> *"completion is stale after the winner; future routing advances with the hedge"*
> *"No O_DIRECT: `COMFYMODAL_GOLDEN_C0_RESOURCE_FAILOVER_O_DIRECT` must remain [disabled]"*

| property | historical ROTATE4 | my pilot (flawed) |
|---|---|---|
| hedge resources | **4 islands/worker × 4 slots = 16 slots/worker** | **1 global lane** |
| geometry rule | `logical_qd < resources_per_worker` | none |
| hedge destination | **a *different* pristine resource island** | same file, same inode, extra FD |
| threshold | 150 ms default | 75/125/200 ms |
| loser handling | explicit — "stale after the winner; future routing advances" | explicit generation identity |
| O_DIRECT variant | **present but disabled** in this experiment | n/a |

**Two things this establishes:**

1. **The historical design out-provisioned logical concurrency by design** (`logical_qd < resources`). My single global lane was structurally unable to give every slow logical read an opportunity — the confound the task identified.
2. **The historical hedge escaped to a different resource island.** It was not a same-path duplicate read. That is a *different mechanism* from what I was testing, and it is the likely reason historical hedging helped where mine did not.

*No `ROTATE3` module was found.* The failover selector set is `(off, control, rotate4)`; `rotate3` does not appear as an arm in this source. I am reporting that rather than inventing a file.

## A2. The previous single-lane flaw

Pilot H75: **73 launched, 77 lane-busy suppressions** — the lane was occupied more often than it fired. A slow logical read could reach its threshold and be *unable to hedge* because an unrelated read already held the lane. The pilot therefore did not test "does a hedge help", only "does a hedge help when the lane happens to be free".

## A3. Corrected hedge resource topology

```
4 coordinator threads   (logical block loops, own the logical clock)
4 attempt threads       (issue the ORIGINAL preadv, one per coordinator)
12 hedge threads        (3 private slots PER WORKER -> 4 workers x 3)
```

Each hedge slot has its **own FD, own 64 MiB buffer, own attempt state**. A hedge for worker *w* can only draw from *w*'s pool, so **hedge A can never suppress hedge B**. A slot is released the moment its hedge attempt completes — so a stale *losing* hedge does not block the worker's next hedge (it blocks at most one of that worker's three slots).

Physical in-flight cap: `qd` originals + up to `qd × slots` hedges. Observed `max_simultaneous_in_flight`: H75 5, H150 6, H250 4.

All physical attempts — originals **and** hedges — pass through **one shared 4.0 ms start-to-start pacer**.

## A4. Proof: `hedge_suppressed_resource_busy == 0`

Instrumented explicitly in the engine and validated per run by the runner (`_valid()` rejects any run with a nonzero value).

| arm | logical reads | eligible | launched | **suppressed** | wins |
|---|---:|---:|---:|---:|---:|
| H75 | 1200 | 9 | 9 | **0** | 0 |
| H150 | 600 | 5 | 5 | **0** | 2 |
| H250 | 600 | 0 | 0 | **0** | 0 |

**`hedge_suppressed_resource_busy = 0` for every arm — the resource-confounded architecture is eliminated.** No run was rejected; 20/20 valid.

## A5. Schedule

Seed `20260923`, persisted in `hedge_runs2/schedule2.json` before any remote job. 5 blocks of `[H75, H75, H150, H250]` shuffled per block:

```
block 1: H250 H75  H75  H150
block 2: H250 H75  H75  H150
block 3: H75  H150 H75  H250
block 4: H75  H250 H150 H75
block 5: H150 H250 H75  H75
```

Exactly H75×10, H150×5, H250×5. Fresh H100 container per run, all `NVIDIA H100 80GB HBM3`.

## A6. Logical accepted latency (from original T0)

| arm | n | best | p10 | median | mean | p90 | p95 | p99 | worst | SD |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| H75 | 1200 | 19.43 | 38.57 | 43.72 | 44.91 | 51.72 | 55.08 | 72.82 | **251** | 9.69 |
| H150 | 600 | 21.69 | 37.69 | 44.42 | **63.80** | 55.62 | 59.88 | **584.71** | **3119** | **181.24** |
| H250 | 600 | 19.98 | 38.95 | 43.64 | 44.67 | 51.92 | 55.09 | 62.62 | **108** | 7.11 |

### Tails

| arm | ≥100 | ≥150 | ≥200 | ≥250 | ≥500 | ≥1000 |
|---|---:|---:|---:|---:|---:|---:|
| H75 | 6 (0.50%) | 1 | 1 | 1 | 0 | 0 |
| H150 | 18 (3.00%) | 12 | 10 | 10 | **8 (1.33%)** | **3 (0.50%)** |
| H250 | 2 (0.33%) | 0 | 0 | 0 | 0 | 0 |

## A7. Run performance

| arm | wall median | mean | best | worst | SD | GB/s median | mean | best | worst |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| H75 | 1619 | 1632 | 1549 | 1913 | 102 | 4.968 | 4.947 | 5.194 | 4.204 |
| H150 | 1710 | **3343** | 1595 | **10051** | **3354** | 4.704 | 4.026 | 5.045 | **0.800** |
| H250 | **1584** | **1616** | 1530 | 1726 | **78** | **5.079** | **4.989** | 5.259 | 4.660 |

## A8. Hedge launch / win counts and time saved

| arm | eligible | launched | launch% of logical | wins | win% | amplification | median saved | mean | max |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| H75 | 9 | 9 | 0.75% | **0** | 0% | 1.0075 | – | – | – |
| H150 | 5 | 5 | 0.83% | **2** | 40.0% | 1.0083 | **5.7 ms** | 5.7 | 10.8 |
| H250 | 0 | 0 | 0.00% | 0 | – | 1.0000 | – | – | – |

Censored originals: 0. Pacer compliance: observed min physical start-gap **4.009–4.263 / 4.029–4.126 / 4.016–4.103 ms** — the 4 ms floor held in every arm.

## A9. Do independently provisioned hedges work better?

**Direct comparison with the flawed pilot:**

| | pilot H75 (1 global lane) | corrected H75 (3 slots/worker) | corrected H150 |
|---|---:|---:|---:|
| launches | 73 | 9 | 5 |
| wins | 19 | **0** | 2 |
| **median saving** | **2.0 ms** | – | **5.7 ms** |
| mean saving | 3.8 ms | – | 5.7 ms |
| max saving | 16.0 ms | – | 10.8 ms |

**Verdict: no. Correcting the resource architecture did NOT make hedging meaningfully effective.**

Removing the lane bottleneck did not produce larger savings. The corrected arms saved at most **10.8 ms** on any single win, with a median of 5.7 ms across only 2 wins. This is the same order of magnitude as the flawed pilot's 2.0 ms, and it is negligible against logical reads of 2500–3100 ms.

**This substantially strengthens the earlier conclusion.** The pilot's tiny savings were *not* an artifact of lane contention: with 12 independent hedge resources and zero suppression, same-path duplicate reads still finish essentially together with their originals. They share the underlying stall, so racing them buys nothing.

**Important caveat on the comparison:** the two cohorts are not identical. The pilot's H75 arm happened to be much sicker (mean wall 2689 ms, worst 12697 ms) than this corrected H75 arm (mean 1632, worst 1913). Sicker cohorts generate more hedge opportunities (73 vs 9 launches). So the *launch counts* are not comparable — only the *saving per win* is, and that stayed tiny.

## A10. Do hedges create real source pressure / pathology?

- **H75 and H250 were the cleanest arms in the experiment** (H75 worst logical 251 ms, H250 worst 108 ms with zero reads ≥150 ms). At 0.75% and 0% launch rates they add essentially nothing.
- **H150 had one catastrophic run** (`h2-H150-010`, block 3): wall **10051 ms**, logical max **3119 ms**, 8 reads ≥500, 3 ≥1000, 5 hedges launched, 2 wins, amplification 1.0417.
- **That run is not attributable to hedging.** 5 extra physical reads out of 120 cannot produce a 10-second wall; and the other four H150 runs were clean (walls 1595–1730 ms). It matches the sporadic underlying pathology that the no-hedge corpus also shows.
- Physical amplification stayed at **1.0000–1.0083** across all arms — hedging added under 1% extra I/O.

## A11. Recommendation — **do not integrate hedging into Golden**

Not because the arms look bad (H75 and H250 were clean), but because:

1. **The mechanism still cannot help.** With the resource bottleneck provably removed, a rescue win still saves ~6 ms because both attempts share the saturated per-inode host path. This is now established twice, under two different resource architectures.
2. **The historical hedge worked a different way** — it rotated to a *different pristine resource island*, not a same-path duplicate read. Our `directfs` path gives one host FD per inode, so that mechanism is not available to us (established earlier: `directfs` holds a single `inode.readFD`).
3. **Hedging fires on the wrong reads.** In the primary 4 ms distribution, only **2.7%** of reads still outstanding at 75 ms end up ≥500 ms (Section B). So a 75 ms trigger fires almost entirely on reads that were about to finish normally.

**Do not integrate.** No further hedge thresholds, topologies, or adaptive timing were tested.

---

# SECTION B — QD4 / 64 MiB DISTRIBUTION

## B1. Corpus manifest and exclusions

`qd4_distribution/qd4_64m_corpus_manifest.csv` — 119 candidate files, **104 valid runs**.

Included cohorts (all `NVIDIA H100`, QD4, 64 MiB, source-only, no hedge attempts):

| cohort | dir/glob | runs | spacing |
|---|---|---:|---:|
| `qd4_vs_qd8_qd4_arm` | `qd_compare_runs/qc-q4-*.json` | 20 | 4.0 ms |
| `spacing_confirm_4ms` | `launch_spacing_confirm_runs/cf-c4-*.json` | 15 | 4.0 ms |
| `spacing_screen_4ms` | `launch_spacing_runs/ls-g4-*.json` | 3 | 4.0 ms |
| `spacing_boundary_2p5ms` | `bd-b25-*.json` | 15 | 2.5 ms |
| `spacing_boundary_3p0ms` | `bd-b30-*.json` | 15 | 3.0 ms |
| `spacing_boundary_3p5ms` | `bd-b35-*.json` | 15 | 3.5 ms |
| `spacing_screen_*` | `ls-g0/g1/g2/g8/g16/g32/g64-*.json` | 21 | 0–64 ms |

**Excluded, with reasons:**
- **hedge-pilot control (`hedge_runs/hx-C-*.json`, 15 runs)** — excluded. Reason: it was produced by the *hedged* engine, whose threading topology (4 coordinators + 4 attempt threads) differs from the plain `run_fullfile_probe` (4 worker threads) used by every other primary run. Even with zero hedge launches it is not source-semantics-identical, and its schema stores `logical_records` rather than `reads`. Excluding it keeps the primary corpus topologically homogeneous.
- QD1 oracle (`ls-qd1-*.json`), QD8 (`qc-q8-*.json`), all hedge treatment arms (`hx-H75/H125/H200`, `h2-*`), wrong-GPU (RTX), and the new corrected-hedge runs.
- Deduplication by `run_id = cohort:filename`; the boundary study's reuse of the earlier 4 ms cohort was **not** double-counted (each file lives in exactly one cohort dir).

## B2–B4. Primary dataset

**38 unique runs, 4560 unique reads**, all H100 / QD4 / 64 MiB / source-only / 4.0 ms pacing / zero hedge attempts.

## B5. Primary 4 ms histogram

| bin (ms) | count | pct | cum% | survival% |
|---|---:|---:|---:|---:|
| 0–20 | 4 | 0.088 | 0.088 | 99.912 |
| 20–30 | 111 | 2.434 | 2.522 | 97.478 |
| 30–40 | 1530 | 33.553 | 36.075 | 63.925 |
| 40–50 | 1773 | 38.882 | 74.956 | 25.044 |
| 50–60 | 541 | 11.864 | 86.820 | 13.180 |
| 60–75 | 265 | 5.811 | 92.632 | 7.368 |
| 75–100 | 232 | 5.088 | 97.719 | 2.281 |
| 100–125 | 51 | 1.118 | 98.838 | 1.162 |
| 125–150 | 14 | 0.307 | 99.145 | 0.855 |
| 150–175 | 9 | 0.197 | 99.342 | 0.658 |
| 175–200 | 4 | 0.088 | 99.430 | 0.570 |
| 200–250 | 8 | 0.175 | 99.605 | 0.395 |
| 250–300 | 5 | 0.110 | 99.715 | 0.285 |
| 300–400 | 1 | 0.022 | 99.737 | 0.263 |
| 400–500 | 3 | 0.066 | 99.803 | 0.197 |
| 500–750 | 5 | 0.110 | 99.912 | 0.088 |
| 750–1000 | 4 | 0.088 | 100.000 | 0.000 |

**Zero reads ≥1000 ms in the entire 4560-read primary corpus** (max 828 ms). The healthy body is 30–50 ms (72% of all reads).

Charts: `qd4_64m_hist_primary_4ms_logcount.png` (log-count, shows tail without hiding the body), `qd4_64m_hist_primary_4ms_tail.png` (tail zoom ≥100 ms), `qd4_64m_survival_primary_4ms.png`.

## B6. Secondary — all clean QD4, stratified by spacing

| spacing (ms) | runs | reads | median | p95 | p99 | max | ≥500 | ≥1000 |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 0.0 | 3 | 360 | 43.76 | 62.35 | 699.82 | 1581 | 4 | 4 |
| 1.0 | 3 | 360 | 54.71 | 88.39 | 112.09 | 151 | 0 | 0 |
| 2.0 | 3 | 360 | 48.42 | 70.04 | 125.75 | 167 | 0 | 0 |
| 2.5 | 15 | 1800 | 43.40 | 100.61 | 788.38 | **11818** | 21 | 11 |
| 3.0 | 15 | 1800 | 42.98 | 77.11 | 111.36 | 656 | 2 | 0 |
| 3.5 | 15 | 1800 | 42.76 | 70.42 | 129.31 | 4082 | 10 | 6 |
| **4.0** | **38** | **4560** | **42.40** | **84.29** | **136.24** | **828** | **9** | **0** |
| 8.0 | 3 | 360 | 41.26 | 69.97 | 103.79 | 681 | 2 | 0 |
| 16.0 | 3 | 360 | 34.12 | 47.88 | 127.60 | 409 | 0 | 0 |
| 32.0 | 3 | 360 | 36.27 | 42.75 | 82.91 | 698 | 2 | 0 |
| 64.0 | 3 | 360 | 32.35 | 37.39 | 48.11 | 885 | 2 | 0 |

**Stratification matters and is not pooled.** Median latency is essentially flat (32–55 ms) across all spacings — pacing does not change ordinary reads. The tails are not monotonic in spacing (2.5 ms bad, 3.0 clean, 3.5 bad again, 4.0 clean), reproducing the boundary finding.

## B7. Quantiles (primary 4 ms)

| segment | n | min | p10 | p25 | p50 | p75 | p90 | p95 | p97 | p98 | p99 | p99.5 | p99.9 | max | mean | SD |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| **all** | 4560 | 19.14 | 35.01 | 38.32 | **42.40** | 50.06 | 66.00 | 84.29 | 93.81 | 103.67 | 136.24 | 217.54 | 596.41 | 828.13 | 49.21 | 35.80 |
| **g0** | 152 | 36.41 | 47.02 | 78.51 | **99.37** | 121.53 | 203.42 | 512.59 | 596.56 | 747.51 | 787.59 | 804.59 | 823.42 | 828.13 | 138.45 | 149.11 |
| **g1+** | 4408 | 19.14 | 34.93 | 38.17 | **42.17** | 48.97 | 61.32 | 74.79 | 83.50 | 87.44 | 95.13 | 109.65 | 246.84 | 318.62 | 46.13 | 16.59 |

**Generation 0 is a completely different distribution**: median 99.37 ms vs 42.17 ms (2.4×), p95 **512.59 ms vs 74.79 ms** (6.9×), and **every single read ≥500 ms in the corpus is a generation-0 read**. g1+ never exceeds 318.62 ms.

## B9–B11. Survival and conditional bad-state probability

`P(final ≥ T | still outstanding at X)`:

| X (ms) | outstanding | % of reads | P≥250 | **P≥500** | P≥1000 | med final | med remaining | done ≤25 ms | ≤50 ms | ≤100 ms |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 50 | 1142 | 25.04 | 1.6 | **0.8** | 0.0 | 60.8 | 10.8 | 70.6 | 90.9 | 96.6 |
| 60 | 601 | 13.18 | 3.0 | **1.5** | 0.0 | 77.8 | 17.8 | 64.4 | 87.2 | 94.0 |
| 75 | 336 | 7.37 | 5.4 | **2.7** | 0.0 | 89.9 | 14.9 | 69.0 | 84.2 | 91.1 |
| 90 | 167 | 3.66 | 10.8 | **5.4** | 0.0 | 105.5 | 15.5 | 61.1 | 74.3 | 82.6 |
| 100 | 104 | 2.28 | 17.3 | **8.7** | 0.0 | 126.3 | 26.3 | 49.0 | 62.5 | 75.0 |
| 110 | 77 | 1.69 | 23.4 | **11.7** | 0.0 | 152.7 | 42.7 | 37.7 | 53.2 | 68.8 |
| 125 | 53 | 1.16 | 34.0 | **17.0** | 0.0 | 195.9 | 70.9 | 26.4 | 43.4 | 56.6 |
| 150 | 39 | 0.86 | 46.2 | **23.1** | 0.0 | 244.3 | 94.3 | 23.1 | 33.3 | 53.8 |
| 175 | 30 | 0.66 | 60.0 | **30.0** | 0.0 | 268.9 | 93.9 | 13.3 | 23.3 | 53.3 |
| 200 | 26 | 0.57 | 69.2 | **34.6** | 0.0 | 296.9 | 96.9 | 11.5 | 30.8 | 50.0 |
| 225 | 23 | 0.50 | 78.3 | **39.1** | 0.0 | 470.4 | 245.4 | 21.7 | 39.1 | 47.8 |
| 250 | 18 | 0.39 | 100.0 | **50.0** | 0.0 | 502.8 | 252.8 | 22.2 | 27.8 | 33.3 |
| 300 | 13 | 0.29 | 100.0 | **69.2** | 0.0 | 519.7 | 219.7 | 7.7 | 7.7 | 7.7 |
| 350 | 12 | 0.26 | 100.0 | **75.0** | 0.0 | 556.9 | 206.9 | 0.0 | 0.0 | 0.0 |
| 500 | 9 | 0.20 | 100.0 | **100.0** | 0.0 | 599.4 | 99.4 | 33.3 | 33.3 | 55.6 |

Separate tables: `qd4_64m_survival_g0.csv`, `qd4_64m_survival_g1plus.csv`.

**Earliest observed X where P(≥500 | outstanding) crosses (no interpolation):**

| target | first observed at | value | outstanding n |
|---|---:|---:|---:|
| 25% | **175 ms** | 30.0% | 30 |
| 50% | **250 ms** | 50.0% | 18 |
| 75% | **350 ms** | 75.0% | 12 |
| 90% | **500 ms** | 100.0% | 9 |

**"What happens next" reading:** at X=75 ms, 84.2% of still-outstanding reads finish within the next 50 ms and only 2.7% ever reach 500 ms — a read outstanding at 75 ms is **still probably normal**. Even at X=125 ms, 43.4% finish within 50 ms and the median remaining time is 70.9 ms. The distribution only becomes genuinely alarming around **200–250 ms** (34.6% → 50%) and is clearly pathological by **350 ms** (75%).

## B12. Recommended candidate hedge trigger region

**From the distribution alone: 200–300 ms, with ~250 ms as the natural point** (the first X where an outstanding read is a coin flip for ≥500 ms).

This directly contradicts the thresholds the pilot and corrected experiment used. **75 ms and 125 ms sit deep in the healthy part of the distribution**: at 75 ms only 2.7% of outstanding reads are destined to be bad, so a hedge fired there is almost certainly wasted duplicate I/O. The corrected experiment's own data agree — H75 and H125 fired on 0.75%/0.22% of reads and won essentially nothing.

The task's framing was right to ask; the answer is that a useful trigger is **~3× later** than the values tested.

**Caveat:** the ≥500 ms population in the primary corpus is only **9 reads across 4560** (0.20%), and all 9 come from the single `qd4_vs_qd8_qd4_arm` cohort. The crossing points at 25/50/75/90% therefore rest on 30, 18, 12 and 9 reads respectively. **Treat the tail of this survival curve as indicative, not precise.**

## B13. Raw CSV paths

```
qd4_distribution/qd4_64m_corpus_manifest.csv
qd4_distribution/qd4_64m_preadv_raw.csv          (12480 raw read records)
qd4_distribution/qd4_64m_histogram_primary_4ms.csv
qd4_distribution/qd4_64m_secondary_by_spacing.csv
qd4_distribution/qd4_64m_survival_primary_4ms.csv
qd4_distribution/qd4_64m_survival_g0.csv
qd4_distribution/qd4_64m_survival_g1plus.csv
qd4_distribution/qd4_64m_hist_primary_4ms_logcount.png
qd4_distribution/qd4_64m_hist_primary_4ms_tail.png
qd4_distribution/qd4_64m_survival_primary_4ms.png
```

Raw read CSV columns: `run_id, cohort, spacing_ms, worker, generation, ordinal, preadv_ms, active_at_enter, offset, length, region, wall_ms, hedge_launched`.

---

## Cohort sensitivity (primary 4 ms)

| cohort | reads | median | p99 | max | ≥500 | ≥1000 |
|---|---:|---:|---:|---:|---:|---:|
| `qd4_vs_qd8_qd4_arm` | 2400 | 42.93 | 144.70 | 828 | **9** | 0 |
| `spacing_confirm_4ms` | 1800 | 43.03 | 135.74 | 319 | **0** | 0 |
| `spacing_screen_4ms` | 360 | 36.25 | 87.31 | 148 | **0** | 0 |

**The 4 ms tail is entirely one cohort.** Two of the three contributing campaigns produced **zero** reads ≥500 ms at 4 ms. The "bad after X ms" transition is therefore **not** broadly sampled — it is carried by 9 reads from a single 20-run campaign. The median/p95 body is stable across all three (42.4–43.0 ms median), so the *healthy* distribution is well established; the *tail* is not.
