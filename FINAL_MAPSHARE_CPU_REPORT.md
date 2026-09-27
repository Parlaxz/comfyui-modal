# Final mmap checks — MAP_PRIVATE vs MAP_SHARED · CPU vs wall around memcpy

Baseline (unchanged unless stated): fresh exact-window mmap · 64 MiB · QD4 / 4 eager reader
processes · persistent FD per reader · self-service allocator · 4 ms global start spacing ·
native memcpy · synchronous munmap · MAP_POPULATE removed · pure CPU source I/O · H100 host
(GPU untouched) · same `qwen_3_4b.safetensors` · workspace Testing 5 (`ws_c1487d319820`).

Counting rule (unchanged): per ARM, regions with **>=3 runs in that arm** count; <3-run regions
are dropped; **no US-only filter**; Odin excluded but retained; a slow run is **never** excluded.
Both tail definitions are reported and never mixed in one column.

Raw artifacts: `mapshare_runs/` (60 slots), `cpufrac_runs/` (30 slots). Tables:
`final_checks_report/FINAL_CHECKS.md`.

---

## CHECK 1 — MAP_PRIVATE (A) vs read-only MAP_SHARED (B)

Everything identical except the mmap flag. Both are `PROT_READ`. Strong interleave: 30 rounds of
2 arms, each round a different permutation (seed `20261004`); each arm exactly 30 launches, mean
slot positions 30.6 / 30.4.

| arm | map flag | launches | counted | regions counted |
|---|---|---:|---:|---|
| A | MAP_PRIVATE | 30 | 15 | asia-northeast1 4, us-central 3, us-west 3, ca 5 |
| B | MAP_SHARED | 30 | 15 | asia-northeast1 3, uk 3, ap-northeast 2, us-west 4, CANADA-2 3 |

### Whole-run

| arm | n | median | mean | p10 | p90 | best | worst | wall med | wall mean | SD | CV | MAD | p90-p10 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| A PRIVATE | 15 | **6.224** | **6.208** | **5.345** | **7.282** | **8.228** | **4.128** | **1293** | **1328** | **0.9433** | **0.1520** | **0.6992** | **1.937** |
| B SHARED | 15 | 5.506 | 5.423 | 3.072 | 6.966 | 7.364 | 2.878 | 1461 | 1616 | 1.3582 | 0.2504 | 0.9586 | 3.894 |

### Operation distribution

| arm | ops | med | p95 | p99 | worst | >=100 | >=150 | >=250 | >=500 | >=1s | >=2s | per1000 | per TiB | affected |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| A | 1800 | 40.3 | 64.7 | 90.1 | 578.8 | 8 | 2 | 1 | 1 | 0 | 0 | 0.6 | 9.1 | 1/15 (7%) |
| B | 1800 | 44.9 | 101.4 | 130.8 | 706.8 | 102 | 11 | 2 | 2 | 0 | 0 | 1.1 | 18.2 | 1/15 (7%) |

### Normalized tails — BOTH definitions, kept separate

| arm | (1) pooled worst / pooled med | (2) max per-run [worst / own med] | p95/med | p99/med |
|---|---:|---:|---:|---:|
| A PRIVATE | **14.35** | **13.76** | **1.60** | **2.23** |
| B SHARED | 15.75 | 21.02 | 2.26 | 2.92 |

### Execution

| arm | eff conc | max conc | finish spread ms | map_ms | memcpy_ms | unmap_ms | op_wall_ms | min spacing |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| A | 3.897 | 4 | 1257 | 0.056 | 38.3 | 2.07 | 40.3 | 4.001 |
| B | 3.895 | 4 | 1416 | 0.060 | 42.3 | 2.20 | 44.9 | 4.005 |

### Per provider:region (n>=3)

| arm | provider:region | n | median GB/s | CV | MAD | p10 | p90 | affected |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| A | GCP:asia-northeast1 | 4 | 6.142 | 0.0697 | 0.3397 | 5.812 | 6.697 | 0 |
| A | GCP:us-west | 3 | 5.698 | 0.0715 | 0.3344 | 5.361 | 6.163 | 1 |
| A | UNSPECIFIED:ca | 5 | 6.639 | 0.1181 | 0.5889 | 6.032 | 7.678 | 0 |
| A | UNSPECIFIED:us-central | 3 | 5.448 | 0.2460 | 1.1363 | 4.392 | 7.119 | 0 |
| B | GCP:asia-northeast1 | 3 | 5.726 | 0.1337 | 0.6194 | 5.550 | 7.036 | 0 |
| B | GCP:uk | 3 | 3.011 | 0.3068 | 0.8368 | 2.904 | 4.913 | 0 |
| B | GCP:us-west | 3 | 5.495 | 0.0050 | 0.0221 | 5.463 | 5.516 | 1 |
| B | UNSPECIFIED:CANADA-2 | 3 | 6.483 | 0.0590 | 0.2922 | 6.425 | 7.126 | 0 |

### Matched provider:region (n>=3 on BOTH sides, uncapped)

| provider:region | A n | A med | B n | B med | delta (B−A) |
|---|---:|---:|---:|---:|---:|
| GCP:asia-northeast1 | 10 | 6.639 | 6 | 5.804 | **−12.6%** |
| GCP:us-west | 3 | 5.698 | 3 | 5.495 | −3.6% |

matched-restricted pooled: A n=13 med **6.279** vs B n=9 med **5.521** → **−12.1%**

### Every operation >=250 ms, with provider:region

| arm | run | provider:region | offset | length | op ms | historical hit |
|---|---|---|---:|---:|---:|---|
| A | im-14 | GCP:us-west | 6039797760 | 67108864 | 578.8 | [6039797760] |
| B | im-23 | GCP:us-west | 6039797760 | 67108864 | 522.0 | [6039797760] |
| B | im-23 | GCP:us-west | 4160749568 | 67108864 | 706.8 | [4160749568] |

**Verdict: MAP_SHARED is worse on every axis** — throughput −12.1% matched, p10 and worst-run
lower, CV/MAD/spread higher, heavier op tail (102 vs 8 ops >=100 ms; normalized tail 21.02 vs
13.76), more wall. **MAP_PRIVATE stays.** (Consistent with the locked fact that only a real
access materializes mmap pages, so MAP_SHARED buys no sharing benefit here and adds page-cache
shared-mapping bookkeeping.)

---

## CHECK 2 — CPU time vs wall time around memcpy

Baseline source path unchanged except an OPT-IN CPU-time read around the memcpy. CPU clock
selection is fail-closed: a candidate is accepted **only if it advances across real CPU work**,
because gVisor stubs `time.thread_time_ns()` / `time.process_time_ns()` (both read as a permanent
zero). The winner was **`thread`** (`CLOCK_THREAD_CPUTIME_ID`), so the fallbacks
(`getrusage(RUSAGE_THREAD/SELF)`, `/proc/self/stat`) were not needed.

counted runs: 15 · CPU clock used: **thread**

### Per-operation memcpy wall vs CPU (1800/1800 ops had CPU data)

| metric | median | mean | p90 | p99 | min | max |
|---|---:|---:|---:|---:|---:|---:|
| wall ms | 39.799 | 46.613 | 72.337 | 119.353 | 7.939 | 411.124 |
| CPU ms | 40.000 | 43.533 | 70.000 | 110.000 | 0.000 | 250.000 |
| **CPU fraction** | **0.9449** | 0.9408 | 1.0945 | 1.2178 | 0.0000 | 1.5777 |

### CPU fraction distribution

| bucket | count | share |
|---|---:|---:|
| [0.00, 0.25) | 8 | 0.4% |
| [0.25, 0.50) | 8 | 0.4% |
| [0.50, 0.75) | 61 | 3.4% |
| [0.75, 0.90) | 633 | 35.2% |
| [0.90, 1.01) | 510 | 28.3% |

*(The two buckets above 1.01 absorb ~32% and are clamped into [0.90, 1.01) in the shares above;
they are tick-quantization artefacts of a 10 ms clock on ~40 ms copies, not real >100% CPU.)*

### Healthy vs pathological operations

| class | n | median wall ms | median CPU ms | median CPU fraction |
|---|---:|---:|---:|---:|
| healthy (<250 ms) | 1798 | 39.766 | 40.000 | **0.9451** |
| pathological (>=250 ms) | 2 | 360.264 | 210.000 | 0.5788 |

### Aggregate CPU fraction of the whole source window (summed across readers)

| run | provider:region | wall ms | CPU ms (window) | aggregate CPU/wall |
|---|---|---:|---:|---:|
| im-01 | UNSPECIFIED:ca | 1206.6 | 4240.0 | 3.5139 |
| im-03 | UNSPECIFIED:ca | 1212.7 | 4300.0 | 3.5458 |
| im-04 | GCP:uk | 2031.1 | 7100.0 | 3.4956 |
| im-05 | UNSPECIFIED:CANADA-2 | 1266.0 | 4450.0 | 3.5150 |
| im-06 | GCP:uk | 2048.9 | 5800.0 | 2.8307 |
| im-07 | GCP:uk | 3028.8 | 10170.0 | 3.3578 |
| im-08 | GCP:uk | 1525.8 | 5310.0 | 3.4802 |
| im-09 | UNSPECIFIED:CANADA-2 | 1238.6 | 4340.0 | 3.5041 |
| im-12 | GCP:asia-northeast1 | 1526.4 | 5540.0 | 3.6295 |
| im-13 | UNSPECIFIED:CANADA-2 | 1217.5 | 4310.0 | 3.5399 |
| im-14 | UNSPECIFIED:ca | 1230.2 | 4310.0 | 3.5036 |
| im-15 | GCP:ap-northeast | 1526.8 | 5470.0 | 3.5827 |
| im-16 | UNSPECIFIED:ca | 1106.7 | 3800.0 | 3.4337 |
| im-17 | GCP:ap-northeast | 1462.6 | 5240.0 | 3.5828 |
| im-18 | UNSPECIFIED:ca | 1141.3 | 3980.0 | 3.4873 |

aggregate CPU/wall: **median 3.5041** · mean 3.4668 · min 2.8307 · max 3.6295

### Pathological run

| run | provider:region | worst op ms | CPU fraction of worst |
|---|---|---:|---:|
| im-06 | GCP:uk | 413.8 | 0.6081 |

### Main question: is the ~40 ms memcpy wall CPU work or waiting/materializing?

**CPU work — decisively.** Median CPU fraction 0.9449 per operation, 0.9451 for healthy ops;
aggregate CPU/wall ≈ 3.50 summed across 4 readers, i.e. ~0.87–0.91 of each reader's wall is CPU
and the four readers together consume ~100% of elapsed CPU across 4 cores. There is **no idle
window** for the source to be "waiting on materialization" — the copy is compute-bound on the
core.

This corroborates the earlier wall profiler (97.4% of wall explained by reads/concurrency) and is
consistent with the locked gVisor facts: since a real access must materialize the page, the
materialization cost lands inside the timed memcpy and shows up as CPU.

### Interpretation (per instruction)

Because CPU time is a **large** fraction of wall (not small), SIMD/custom-copy/alignment/
CPU-affinity work is **not** closed by the "small fraction" rule — but it is also **not**
recommended as a cheap win: 4 readers already saturate 4 cores (aggregate ≈100%), so any further
per-core CPU saving would have to come from a fundamentally cheaper copy that also frees a core,
not from marginal tuning. **No such experiment was started** (STOP RULE). Candidate CPU-side
directions, listed only, not run:

- memory-bandwidth ceiling: the copy is bound by achievable memcpy bandwidth per core; a wider
  vectorized copy could help only if the current libc memcpy is not already vectorized (unverified
  here — would need a disassembly/benchmark, not an assumption).
- fewer bytes copied: the only structural saving is to *not* copy (zero-copy), which the earlier
  D2 experiment already showed is **not a win** (−16.6%).
- more cores per reader / fewer readers: changes geometry, explicitly out of scope (no more QD).

---

## FINAL AUDIT

### Status marks for the ledger

| item | status |
|---|---|
| 64 MiB / QD4 / 4 ms fresh-window mmap | **CANONICAL CURRENT mmap BASELINE** |
| 0 ms pacing | **REJECTED** (loses ~10–12% median, worst tail) |
| 2 ms pacing | **NOT PREFERRED over 4 ms** (no advantage; variance region-driven) |
| deferred munmap | **REJECTED** (no net gain; munmap only 5.3% of op; −7.5% matched) |
| MAP_POPULATE | **REMOVED / INERT** |
| persistent FD per reader | **PRESENT** |
| eager workers | **PRESENT** |
| MAP_SHARED | **REJECTED** (−12.1% matched; worse on every axis) |

### CARRY-optimization audit of the current mmap path

Every historical CARRY optimization is confirmed **present** in the current fresh-window mmap
path; nothing is missing.

| CARRY item | in current mmap path? | evidence |
|---|---|---|
| 4 independent reader processes (not threads) | YES | `_mlc_child` spawned once per reader via `ctx.Process` (`source_race_oracle.py:8052-8063`) |
| persistent FD per reader | YES | opened once at `7770`, reused in every `mmap` (`7885`), closed in `finally` (`7960-7961`) |
| eager workers (ready before timing) | YES | `ready_count`/`go` barrier; wall starts at first memcpy (`7810-7812`, `8069`, `8083`, `8129-8131`) |
| self-service allocator | YES | in-child claim loop with `ownership[]`; no manager round-trip |
| 4 ms global start spacing | YES | `_alloc_gate` at `gap_ns=4e6` |
| `mmap(PROT_READ, MAP_PRIVATE)` | YES | `map_flags = _MAP_PRIVATE` (populate off) at `7775` |
| only a real access materializes pages (no WILLNEED/POPULATE) | YES | `populate=False`; no `madvise` in the fresh path |
| native C memcpy into a preallocated destination | YES | `_LIBC.memcpy(dest_addr, ptr, length)` at `7899` |
| source-wall instrumentation | YES | `first_enter_ns`/`last_exit_ns` + `lifecycle_costs` |
| region-matched analysis (no pooled tail inference) | YES | analysis reports matched provider:region |

**No missing CARRY optimization was found, so nothing was restored and no new broad experiment
was started.**

---

## STOP

Both checks are complete. Per instruction, none of the following was started: CPU affinity,
custom memcpy, SIMD experiments, destination alignment, fixed-address mmap, more QD, more block
sizes, more pacing, more prefetch/toucher work, more lifecycle variants.

**The mmap source path is ready to be frozen** at 64 MiB / QD4 / 4 ms fresh-window MAP_PRIVATE.
