# THREADS vs PROCESSES — provider-pinned replication (AWS + GCP, no odin)

**Question:** same as before — at identical QD4 / 64 MiB / 4.0 ms geometry, do four independent one-reader processes beat four reader threads in one process?

**Answer: no — the replication reverses the earlier result. Processes came out 15.7% *slower* on the median. Combined with run 1, the honest conclusion is that there is no stable process-vs-thread throughput advantage on this path; the earlier +36% was a region-lottery artifact.**

- Schedule seed `20260926`, 10 paired rounds, positional balance 5/5, **provider pinning only** (`cloud="aws"` ×5 rounds, `cloud="gcp"` ×5 rounds, **region left completely free**).
- 20/20 runs accepted as valid H100. Fresh single-use container per run.
- Artifacts: `worker_model_runs_provider/{ANALYSIS.txt, per_run_metrics.csv, pooled_reads.csv, schedule.json, wm-*.json}`

---

## 1. What was pinned, and what was not

`cloud` was pinned per round. **No region was pinned or constrained** — Modal chose the region freely within the provider. Observed regions: `uk`, `us-east`, `us-west`, `us-west4`, `asia-northeast1`, `ap-northeast` (AWS and GCP only; **odin never appeared**).

Preflight confirmed both providers schedule and the pin takes effect:
```
[pf] aws:  -> provider='aws' region='eu-north'  OK
[pf] gcp:  -> provider='gcp' region='us-central' OK
```

### Modal API facts established along the way

- **`cloud` takes exactly one value.** It is declared `Optional[str]` at every declaration site and sent to the backend as a single string (`cloud_provider_str=cloud if cloud else ""`). Valid values: `aws`, `gcp`, `oci`, `auto`. **There is no "aws or gcp" form.** Only `region` accepts a sequence (`Optional[Union[str, Sequence[str]]]`).
- **You cannot exclude odin in one call**, because the only multi-provider option is `cloud="auto"` — which is exactly what admits odin. Removing odin requires separate calls, one provider each.
- Pinning is available per-invocation via `Function.with_options(cloud=..., region=...)`; no redeploy needed.
- Modal reports the provider as the proto enum name (`CLOUD_PROVIDER_AWS`), not `aws`.

**Correction to the previous report's region table.** The real provider map from run 1's own data was:

| region | actual provider | count |
|---|---|---:|
| odin | UNSPECIFIED (Modal's own) | 8 |
| eu-north | UNSPECIFIED | 3 |
| denver | UNSPECIFIED | 1 |
| us-central | **Azure** | 2 |
| us-east | **GCP** | 2 |
| ap-northeast | **GCP** | 1 |
| us-chicago-1 | OCI | 2 |
| us-ashburn-1 | OCI | 1 |

My earlier report labelled `us-east`/`eu-north`/`ap-northeast` as "AWS". They were not. Region slugs are **not** a reliable proxy for provider.

## 2. Headline table (provider-pinned)

| metric | 4 threads / 1 process | 4 processes / 1 reader each |
|---|---:|---:|
| runs | 10 | 10 |
| median GB/s | **4.693** | **3.956** |
| mean GB/s | 4.484 | 4.175 |
| best GB/s | 5.430 | 6.015 |
| worst GB/s | 3.011 | 1.616 |
| GB/s SD | 0.874 | 1.268 |
| median source wall ms | 1714 | 2036 |
| mean source wall ms | 1875 | 2206 |
| best source wall ms | 1482 | 1338 |
| worst source wall ms | 2672 | 4978 |
| pooled preadv median ms | 48.75 | 54.64 |
| pooled preadv mean ms | 57.38 | 71.17 |
| preadv p95 ms | 96.15 | 96.30 |
| preadv p99 ms | 122.29 | 114.51 |
| worst preadv ms | 484.2 | 3701.3 |
| reads ≥250 | 4 | 4 |
| reads ≥500 | **0** | **4** |
| reads ≥1000 | **0** | **4** |
| runs ≥500 | **0** | 1 |
| runs ≥1000 | **0** | 1 |
| effective concurrency | 3.660 | 3.857 |
| overlap | 0.9775 | 0.9875 |
| max active | 4 | 4 |

**PROCESS median GB/s delta: −0.737 (−15.7%)**
**PROCESS mean GB/s delta: −0.309 (−6.9%)**

## 3. Paired analysis

| round | cloud | threads GB/s | processes GB/s | delta | delta % | tWall | pWall | wall delta |
|---:|---|---:|---:|---:|---:|---:|---:|---:|
| 1 | aws | 4.737 | 4.102 | −0.634 | −13.4% | 1698 | 1961 | +263 |
| 2 | gcp | 5.272 | 5.572 | +0.300 | +5.7% | 1526 | 1444 | −82 |
| 3 | aws | 3.486 | 3.689 | +0.203 | +5.8% | 2308 | 2181 | −127 |
| 4 | gcp | 5.359 | 1.616 | −3.743 | −69.8% | 1501 | 4978 | +3477 |
| 5 | gcp | 4.281 | 5.436 | +1.155 | +27.0% | 1879 | 1480 | −399 |
| 6 | gcp | 5.304 | 6.015 | +0.711 | +13.4% | 1517 | 1338 | −179 |
| 7 | aws | 3.011 | 4.847 | +1.836 | +61.0% | 2672 | 1660 | −1012 |
| 8 | gcp | 5.430 | 2.917 | −2.513 | −46.3% | 1482 | 2758 | +1277 |
| 9 | aws | 3.307 | 3.811 | +0.504 | +15.2% | 2433 | 2111 | −322 |
| 10 | aws | 4.650 | 3.746 | −0.903 | −19.4% | 1730 | 2147 | +417 |

- median paired GB/s delta **+0.251 (+5.8%)**
- mean paired GB/s delta **−0.309 (−2.1%)**
- median paired wall delta **−104 ms**
- **pairs PROCESS > THREAD: 6/10** · threads > process: 4/10
- paired bootstrap 95% interval on the median delta: **[−1.574, +0.830] GB/s** — straddles zero

Note the internal contradiction: the *median of the paired deltas* is positive (+5.8%) while the *difference of the medians* is negative (−15.7%). That is what happens when one outlier (round 4) moves the pooled median without moving most pairs.

## 4. The two replications disagree — this is the actual finding

| | run 1 (unpinned, odin-heavy) | run 2 (AWS+GCP pinned) |
|---|---:|---:|
| threads median GB/s | 4.718 | 4.693 |
| processes median GB/s | 6.431 | 3.956 |
| **process median delta** | **+36.3%** | **−15.7%** |
| threads mean GB/s | 4.572 | 4.484 |
| processes mean GB/s | 5.930 | 4.175 |
| **process mean delta** | **+29.7%** | **−6.9%** |
| paired rounds favouring processes | 7/10 | 6/10 |
| reads ≥500 (threads / processes) | 5 / 0 | 0 / 4 |
| reads ≥1000 (threads / processes) | 2 / 0 | 0 / 4 |
| bootstrap 95% CI on median delta | [−0.576, +3.475] | [−1.574, +0.830] |

**The sign flips.** The thread arm is remarkably stable across replications (4.718 → 4.693 median); the process arm swings wildly (6.431 → 3.956). The process arm's median is therefore far more sensitive to which region/instance it draws — not evidence that processes are better or worse.

Excluding every run containing a read ≥500 ms does not rescue it:

| clean-subset (no read ≥500 ms) | threads | processes | delta |
|---|---:|---:|---:|
| run 1 | 5.385 (n=8) | 6.431 (n=10) | +19.4% |
| run 2 | 4.693 (n=10) | 4.102 (n=9) | **−12.6%** |

Even with catastrophic runs removed, run 1 favours processes by 19% and run 2 favours threads by 13%. **A stable treatment effect cannot flip sign like that.**

## 5. Region dominates the arm

Provider-pinned regions (region deliberately free):

| region | arm | n | GB/s values | median |
|---|---|---:|---|---:|
| uk | threads | 3 | 3.01, 3.49, 4.74 | 3.486 |
| uk | processes | 2 | 3.69, 4.10 | 3.896 |
| us-east | threads | 2 | 3.31, 4.65 | 3.978 |
| us-east | processes | 3 | 3.75, 3.81, 4.85 | 3.811 |
| us-west | threads | 3 | 5.27, 5.30, 5.36 | 5.304 |
| us-west | processes | 1 | 5.57 | 5.572 |
| us-west4 | threads | 2 | 4.28, 5.43 | 4.855 |
| asia-northeast1 | processes | 3 | 1.62, 5.44, 6.01 | 5.436 |
| ap-northeast | processes | 1 | 2.92 | 2.917 |

Within-arm region spread (uk ~3.5 → us-west ~5.3, and `asia-northeast1` spanning 1.62–6.01) **exceeds the arm effect by a wide margin.** Region is the dominant variable; the worker model is second-order at best.

## 6. The pathology is not arm-specific

Across both replications the multi-second stall appeared in **whichever arm drew the bad instance**:

- run 1: threads hit it twice (round 4 `ap-northeast` 2869 ms; round 8 `eu-north` 3787 ms). Processes: zero.
- run 2: processes hit it once (round 4 `gcp:asia-northeast1` 3701 ms, with 4 reads ≥500 and 4 ≥1000). Threads: zero.

Both arms are susceptible. This experiment provides **no** evidence that process isolation suppresses the stall; run 1 suggested it and run 2 refuted it. The single most defensible statement remains the one from run 1's mechanism section: process ownership did **not** change unit read latency (run 2 confirms: pooled median 48.75 vs 54.64 ms, and process p95 is a dead heat at 96.30 vs 96.15 ms).

## 7. Direct answers

1. **THREADS median GB/s:** 4.693
2. **PROCESSES median GB/s:** 3.956
3. **Absolute / percentage median improvement:** **−0.737 GB/s, −15.7%** (processes *slower*)
4. **Mean GB/s:** threads 4.484 · processes 4.175 (−6.9%)
5. **Paired rounds favouring PROCESSES:** 6 of 10 — but the median paired delta is +5.8% while the median difference is −15.7%, i.e. the pairs are near-symmetric and one outlier moves the pooled median.
6. **Did ordinary median preadv latency improve?** No — 48.75 → 54.64 ms, processes *worse* by 5.89 ms. This now agrees with run 1's finding that unit latency is unchanged/not improved.
7. **Did mean/p95/p99 improve?** Mean worse (+13.79 ms), p95 dead even (+0.15 ms), p99 marginally better (−7.79 ms). No real improvement.
8. **Did tail frequency improve?** **No — it reversed.** run 1: threads 5 reads ≥500 / processes 0. run 2: threads 0 / processes 4. The tail is a lottery, not an arm property.
9. **Did effective concurrency change despite identical QD4?** Slightly, 3.660 → 3.857 — and as established in run 1, concurrency is `busy/span`, so a stall in one arm depresses its own ratio. Not an independent gain.
10. **Did worker completion balance improve?** Yes, mildly: median spread 118.9 → 65.2 ms. But the process arm's worst worker read was 3701 ms vs threads' 484 ms, so balance came at the cost of a far worse worst case.
11. **Was the 4 ms global floor obeyed identically?** Yes — min claim gap 4.0008 ms (threads) vs 4.0006 ms (processes), one global clock in both arms, all 20 runs.
12. **Large enough to explain the old ~22–25% process advantage?** **No.** The replication produced −15.7%, and the two clean-subset estimates (+19.4% / −12.6%) disagree in sign. The historical 22–25% advantage **does not reproduce** on this real-file QD4/64 MiB/4 ms path.
13. **Did PROCESSES reach the 6–7 GB/s median target?** **No.** Median 3.956; the target is not met. Processes' *best* run reached 6.015 (and run 1 saw 7.17 in odin), but the median is well short.
14. **Is the process architecture worth carrying into the real Golden loader?** **Not on this evidence.** The earlier recommendation was already conditional on region control; with odin removed the advantage vanished and reversed. Process isolation costs a fork per worker and adds a shared-pacer mechanism, and buys no demonstrated throughput. It should not be carried forward without a fundamentally different design that also controls region.
15. **What mechanism is supported, and what remains unknown?**
    - **Supported:** unit `preadv` latency is unchanged by the worker model (both replications agree). The sporadic multi-second stall is **not** arm-specific — it strikes whichever arm draws the affected instance/region. Region is the dominant determinant of full-file throughput.
    - **Unknown:** what makes a region/instance bad. `asia-northeast1` produced both 6.01 and 1.62 GB/s; `eu-north` produced both 6.44 and 1.35. The stall is a per-instance or per-window lottery whose trigger is not identified by either experiment.
    - **Now clearly established:** provider pinning removes odin but does **not** remove the region lottery, because region cannot be pinned to a single value across both arms without triggering capacity failures (see below).

## 8. Discarded attempt: region pinning (recorded for audit)

I first pinned **region** as well as provider, to make each pair region-matched. That was over-reach beyond the instruction and it failed on capacity:

- `aws:eu-north` **never scheduled an H100** — round 2 hung >55 minutes.
- `aws:ap-northeast` timed out on 3 consecutive attempts (round 6, 240 s each).
- Rounds 1–5 did complete (region-pinned to `aws:us-east` / `gcp:us-central`) and are preserved at `worker_model_runs_pinned/` along with the timeout evidence (`*-invalid*.json`). They are **not** mixed into the provider-pinned corpus above, because they are a different treatment.

The runner now uses bounded `spawn()` + `FunctionCall.get(timeout=...)` with `cancel()` on expiry, so an unschedulable region fails fast instead of hanging — that change is retained.

**Conclusion on design:** provider pinning is feasible; region pinning is not reliable, because Modal's H100 capacity is thin in most individual regions. Since region cannot be controlled without capacity failures, the region lottery is currently **unavoidable** on this path, and any A/B comparison of this shape will remain region-confounded at n=10.

## 9. Stop condition

Exactly 10 THREADS + 10 PROCESSES provider-pinned runs, plus the discarded region-pinned attempt. No QD changes, no block-size changes, no work stealing, no multi-file, no 2×2 split.
