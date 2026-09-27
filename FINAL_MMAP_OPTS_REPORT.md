# Final mmap optimizations — CPU affinity · fixed-VA window replacement

Baseline (unchanged): fresh exact-window mmap · MAP_PRIVATE · 64 MiB · QD4 / 4 eager reader
processes · persistent FD per reader · self-service allocator · 4 ms global spacing · native
libc memcpy · synchronous munmap · MAP_POPULATE removed · pure CPU source I/O · H100 host
(GPU untouched) · same `qwen_3_4b.safetensors` · workspace Testing 5 (`ws_c1487d319820`).

Geometry, pacing, QD, copy implementation and scheduler were **not** changed in either
experiment. Both are A/B, strongly interleaved (30 rounds of 2 arms, each round a different
permutation), 15 counted per arm. Counting rule unchanged: per ARM, regions with >=3 runs in
that arm count; <3-run regions dropped; no US-only filter; Odin excluded but retained; a slow
run is never excluded. Both tail definitions are reported separately and never mixed.

Raw artifacts: `aff_runs/` (60 slots), `fva_runs/` (60 slots). Tables: `aff_fva_report/AFF_FVA.md`.

**Balance note (disclosed):** single-slot smokes had written `im-01.json` with the treatment
arm, and the cohort cached it, giving 29/31. Slot 1 was re-run with the correct arm, so both
cohorts are now exactly balanced (EXP1 30/30; EXP2 29/30 + 1 Odin).

---

## EXPERIMENT 1 — CPU AFFINITY

A = current behaviour (no explicit reader affinity). B = each of the 4 reader processes pinned
to a different allowed CPU. Parent not pinned; process count unchanged.

### Affinity audit (measured, in-container)

| item | result |
|---|---|
| `sched_getaffinity` present | **True** |
| allowed CPU set | **28 logical CPUs** (0–27) |
| `sched_setaffinity` | **succeeds** — reader 0→CPU0, 1→CPU1, 2→CPU2, 3→CPU3; `set_ok=True`; observed `after` = `[0]`,`[1]`,`[2]`,`[3]`; errno None |
| physical-core topology (`/sys/.../topology`) | **NOT readable under this deployed gVisor** (`available=False`) |
| **LIMITATION** | the four CPUs are distinct allowed **logical** CPUs; whether they are distinct physical cores is **unverified**. Per instruction, logical CPUs were used and the limitation is stated. |

### Results

| arm | n | median | mean | p10 | p90 | best | worst | wall med | SD | CV | MAD | p90-p10 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| A none | 15 | 5.550 | 4.823 | 2.613 | 5.852 | 6.224 | 2.053 | 1450 | 1.3682 | 0.2837 | 0.9352 | 3.239 |
| B pinned | 15 | 5.534 | 5.800 | 5.122 | 6.864 | 7.002 | 4.904 | 1454 | 0.6784 | **0.1170** | **0.5492** | **1.742** |

Matched-restricted (n>=3 both sides, uncapped): A n=14 med 5.574 mean 5.239 p10 2.943 worst
2.002 · B n=20 med 5.482 mean 5.578 p10 4.869 worst 4.063 → **median delta −1.7%**.

### Operation tails — pooled vs matched region

| scope | arm | ops | med | p95 | p99 | worst | >=100 ms | >=150 | >=250 |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| all regions | A | 3600 | 47.1 | 126.4 | 159.9 | 272.2 | **528 (14.7%)** | 51 | 2 |
| all regions | B | 3600 | 46.2 | 97.6 | 124.6 | 547.1 | **169 (4.7%)** | 17 | 6 |
| **asia-northeast1 only** | A | 1200 | 46.4 | 57.1 | 89.1 | 107.6 | **5 (0.4%)** | 0 | 0 |
| **asia-northeast1 only** | B | 1680 | 45.5 | 57.7 | 101.2 | 270.8 | **20 (1.2%)** | 5 | 2 |

**The pooled tail "improvement" reverses on the matched region.** In asia-northeast1 — the only
region with adequate n on both sides — arm B is *worse* on every tail measure. The pooled
528→169 reduction is therefore attributable to **region composition** (arm A's counted set
contains europe-west2, median 3.000 GB/s; arm B's contains ca, median 6.848 GB/s), not to the
affinity mechanism.

---

## EXPERIMENT 2 — FIXED-VA WINDOW REPLACEMENT

A = normal `mmap` → memcpy → `munmap`. B = one reader-owned 64 MiB VA slot (anonymous PROT_NONE
reservation) with each file window `MAP_FIXED` into that same slot, so replacement removes the
previous mapping; one final `munmap` at the end. Every replacement is asserted `== slot_base`.

### Safety / telemetry (arm B, 15 counted runs)

| metric | value |
|---|---:|
| replacements | **1800** |
| replacement errors | **0** |
| address mismatches (asserted == slot_base) | **0** |
| slots page-aligned | **60 / 60** |
| distinct slot bases (one per reader) | 15 |
| peak live mappings | **1** |
| final live mappings | **0** |
| **slots leaked after cleanup** (real `/proc/self/maps` check) | **0 / 60** |
| worker errors / barrier errors | 0 / 0 |
| coverage exact / amplification | 120/120 / 1.0 |

MAP_FIXED was **never** used outside the owned reservation: the reservation is created first,
the base is asserted page-aligned, and every replacement address is asserted equal to it.

### Cost decomposition (median per operation) — the decisive result

| arm | mmap/replacement ms | memcpy ms | explicit munmap ms | op_wall ms |
|---|---:|---:|---:|---:|
| A mmap/munmap | 0.0596 | 44.3 | **2.2209** | 46.9 |
| B fixed-VA | **2.2367** | 43.7 | **0.0000** | 46.3 |

The explicit munmap disappears (2.2209 → 0.0000 ms) but the replacement mmap grows by almost
exactly the same amount (0.0596 → 2.2367 ms). **The munmap cost was relocated into `MAP_FIXED`,
not removed.** Net `op_wall` is unchanged within noise (46.9 → 46.3 ms, −1.3%).

### Source-ready vs fully-cleaned wall

| arm | source-ready med ms | fully-cleaned med ms | final cleanup med ms |
|---|---:|---:|---:|
| A | 1489.2 | 1489.2 | 0.00 |
| B | 1433.2 | 1436.3 | **3.12** |

Arm B moves the cleanup to a single 3.12 ms end-of-run drain (instead of 120 per-op munmaps).

### Results

| arm | n | median | mean | p10 | p90 | best | worst | wall med | SD | CV | MAD | p90-p10 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| A | 15 | 5.382 | 4.827 | 2.495 | 6.351 | 6.797 | 2.313 | 1495 | 1.5019 | 0.3111 | 1.1835 | 3.855 |
| B | 15 | 5.613 | 5.142 | 2.837 | 6.649 | 6.920 | 2.438 | 1433 | 1.4809 | 0.2880 | 1.1386 | 3.812 |

Matched-restricted: A n=17 med 5.359 mean 4.957 p10 2.502 worst 2.313 · B n=20 med 5.633 mean
5.167 p10 2.728 worst 2.438 → **median delta +5.1%** (but `op_wall` is unchanged, so this is not
mechanism-attributable).

Op tails (all regions): A 402 ops >=100 ms (11.6%) · B 294 (8.2%); >=250 ms 0 in both.
Matched region asia-northeast1: A 11 ops >=100 ms (1.3%), worst 207.6 · B **0 (0.0%)**, worst 98.5.

---

## ANSWERS

### CPU AFFINITY

1. **Supported?** **Yes.** `sched_getaffinity`/`sched_setaffinity` both work; 28 logical CPUs
   allowed; each reader pinned to a distinct CPU (0,1,2,3) with the pin observed afterwards.
   Physical-core topology is **not** exposed by this gVisor, so distinct *logical* CPUs were
   used — that limitation is real and stated.
2. **Faster/slower?** **Neither.** Median is unchanged: pooled 5.550 → 5.534 (−0.3%);
   matched-restricted −1.7%. Mean rises (+20%) only because arm A's counted set contains a slow
   region that arm B's does not.
3. **Variance better/worse?** Pooled variance is much better (CV 0.2837 → 0.1170, MAD 0.9352 →
   0.5492, p90−p10 3.239 → 1.742), and matched-restricted p10 improves (2.943 → 4.869). But the
   pooled part is **region-composition confounded**; the matched-restricted variance gain is the
   only mechanism-attributable piece.
4. **Tails better/worse?** **Worse on the matched region.** In asia-northeast1, arm B has more
   ops >=100 ms (20 vs 5, 1.2% vs 0.4%), more >=150 ms (5 vs 0), more >=250 ms (2 vs 0) and a
   worse worst op (270.8 vs 107.6 ms). The pooled tail improvement is composition.
5. **Worth carrying?** **Not on this evidence.** No throughput gain, and the only
   mechanism-attributable tail evidence (the matched region) is slightly *worse*. The matched
   variance/low-end gain is real but small and does not offset an unimproved (slightly worse)
   tail. **Do not carry** — and note the tradeoff is Ahmed's to weigh if low-end stability
   matters more than the matched-region tail.

### FIXED VA

6. **Safe/supported?** **Yes, and fully verified.** MAP_FIXED honoured the owned slot in all 60
   runs (0 errors, 0 address mismatches), 60/60 slots page-aligned, peak 1 live mapping, and
   **0/60 slots leaked after cleanup** (a real `/proc/self/maps` scan, not an assertion).
   0 worker errors, 0 barrier errors, coverage exact 120/120, amplification 1.0.
7. **How much explicit munmap cost disappeared?** The explicit munmap went **2.2209 → 0.0000 ms**
   per op, but the replacement mmap grew **0.0596 → 2.2367 ms**. So ~2.18 ms of the 2.22 ms was
   **relocated into MAP_FIXED**, not eliminated; net saving ≈ **0.04 ms/op (~0.1%)**.
8. **Source-ready speed delta?** Pooled wall median 1489.2 → 1433.2 ms (−3.8%); matched-restricted
   median +5.1%. Because `op_wall` is unchanged, **this is not mechanism-attributable** — it is
   placement/composition.
9. **Fully-cleaned speed delta?** Arm B's fully-cleaned wall = source-ready + **3.12 ms** final
   drain. Fully-cleaned medians: 1489.2 (A) → 1436.3 (B), −3.6% pooled — same composition caveat.
10. **Variance/tail delta?** Pooled slightly better (CV 0.3111 → 0.2880; ops >=100 ms 402 → 294).
    On the matched region asia-northeast1, arm B is cleaner (0 vs 11 ops >=100 ms; worst 98.5 vs
    207.6 ms) — but n=7 per side and `op_wall` is equal, so this is not established as a
    mechanism effect.
11. **Preserve fresh-window behaviour?** **Yes.** Each block still maps a fresh exact 64 MiB file
    window (PROT_READ, MAP_PRIVATE); MAP_FIXED merely replaces the previous window at the owned
    address. It is **not** persistent-segmented; peak live mappings 1; coverage exact 120/120.
    The fresh-window consistency benefit is preserved.
12. **Worth carrying?** **No clean benefit.** The mechanism is cost-neutral: the munmap cost is
    relocated into the replacement rather than removed, so `op_wall` is unchanged. It is safe and
    it does preserve fresh-window semantics, but it buys nothing measurable.

---

## Conclusion

**Neither optimization produces a clean benefit.**

- **CPU affinity:** median throughput unchanged; the pooled variance/tail improvement is region
  composition; on the one adequately-matched region the op tail is slightly *worse*.
- **Fixed-VA replacement:** safe and verified, preserves fresh-window semantics, but the explicit
  munmap cost is **relocated into `MAP_FIXED`, not removed** — `op_wall` is unchanged.

**The mmap source optimization program is effectively exhausted. Freeze the baseline** at
64 MiB / QD4 / 4 ms / fresh-window / MAP_PRIVATE. No further source optimization was started.
