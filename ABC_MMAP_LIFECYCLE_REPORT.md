# A/B/C — why does M2 work? Three mmap life-cycle architectures

One experiment. Everything else frozen: pure CPU source only, H100 host for placement
comparability (GPU never touched), 4 processes, QD4, 64 MiB logical blocks, 4 ms global
source-operation spacing, same `qwen_3_4b.safetensors`, same scheduler, same native memcpy
consumer and destination, exact full-file coverage. No preadv, no toucher, no M1, no O_DIRECT,
no CUDA/H2D, no new block size / QD / pacing.

MAP_POPULATE was **removed from all three arms**. Sanity check first (same-window interleaved,
`--populate-pattern`): pooled medians **7.265 GB/s with** vs **7.293 GB/s without** — 0.4% apart,
consistent with the Phase-0 proof that it is inert. Removed permanently.

Counting rule: US only; singleton US regions excluded; excluded runs retained; Odin excluded
but preserved. Raw runs: `abc_lifecycle/`. Report: `abc_report/ABC_LIFECYCLE.md`.

| arm | counted n | valid runs | note |
|---|---:|---:|---|
| A WHOLE (persistent whole-file) | 8 | 29 | as specified |
| B SEGMENTED-PERSISTENT | **7** | 22 | **one short of the specified 8** |
| C FRESH-WINDOW (current M2) | 8 | 28 | as specified |

B is one short because two top-up batches landed its slots in non-US regions; I stopped rather
than spend 18 more containers chasing a single sample. This is a stated deviation.

## Main

| arm | n | GB/s med | mean | p10 | p90 | best | worst | wall med | wall mean |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| A WHOLE | 8 | 5.657 | 5.400 | 3.859 | 6.926 | 7.007 | 3.630 | 1423 | 1577 |
| B SEGMENTED-PERSISTENT | 7 | 4.469 | 4.956 | 3.859 | 6.395 | 7.154 | 3.429 | 1755 | 1681 |
| C FRESH-WINDOW | 8 | 5.535 | 5.610 | 5.079 | 6.429 | 6.517 | 4.832 | 1453 | 1447 |

## Variance

| arm | SD | CV | MAD | p90-p10 |
|---|---:|---:|---:|---:|
| A WHOLE | 1.2327 | 0.2283 | 1.0687 | 3.0666 |
| B SEGMENTED-PERSISTENT | 1.1580 | 0.2336 | 0.9109 | 2.5360 |
| **C FRESH-WINDOW** | **0.5483** | **0.0977** | **0.4254** | **1.3496** |

Per provider:region (n≥2):

| arm | provider:region | n | SD | CV | MAD | p90-p10 |
|---|---|---:|---:|---:|---:|---:|
| A | GCP:us-west | 3 | 1.1234 | 0.1949 | 0.8869 | 2.1286 |
| A | UNSPECIFIED:us-central | 3 | 0.9587 | 0.2147 | 0.7260 | 1.7423 |
| B | GCP:us-east | 4 | 0.9824 | 0.1726 | 0.8288 | 2.0687 |
| B | UNSPECIFIED:us-central | 3 | 0.3953 | 0.0994 | 0.3074 | 0.7378 |
| C | GCP:us-east | 5 | 0.5180 | 0.0943 | 0.3844 | 1.0805 |
| C | UNSPECIFIED:us-central | 3 | 0.5444 | 0.0939 | 0.4395 | 1.0549 |

## Operation tails

| arm | op median | p95 | p99 | worst | ≥250 | ≥500 | ≥1s | ≥2s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| A WHOLE | 44.63 | 97.66 | 142.84 | 199.0 | **0** | 0 | 0 | 0 |
| B SEGMENTED-PERSISTENT | 50.74 | 86.19 | 131.97 | 378.7 | 1 | 0 | 0 | 0 |
| C FRESH-WINDOW | 44.39 | 61.07 | 102.15 | 534.2 | 4 | 1 | 0 | 0 |

## Life-cycle costs (means over counted runs)

| arm | prep/map ms | consume wall | cleanup ms | first-use inclusive wall | peak mappings | live maps | map bytes | map errs | unmap errs |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| A WHOLE | 1.26 | 1577 | 70.49 | 1649 | 1.0 | 4.0 | 32179928192 | 0 | 0 |
| B SEGMENTED-PERSISTENT | 2.15 | 1681 | 60.11 | 1743 | 30.0 | 120.0 | 8044982272 | 0 | 0 |
| C FRESH-WINDOW | 0.01 | 1447 | 0.00 | **1447** | 0.0 | 0.0 | 0 | 0 | 0 |

Both numbers are shown for A and B, as required: `prep/map` is the cost of creating those
mappings **before** consumption, and `first-use inclusive wall` = prep + consume + cleanup, i.e.
what the run costs if the mappings must actually be created for it. **Creating the mappings is
nearly free** (1.26 ms for one whole-file map per reader; 2.15 ms for ~30 windows per reader).
Cleanup is 60–70 ms.

## Every pathological operation (≥250 ms)

| arm | run | provider:region | abs offset | length | op ms |
|---|---|---|---:|---:|---:|
| B | im-15 | GCP:us-east | 6039797760 | 59027232 | 378.7 |
| C | im-16 | GCP:us-east | 2013265920 | 67108864 | 534.2 |
| C | im-26 | GCP:us-east | 6039797760 | 59027232 | 268.4 |
| C | im-66 | GCP:us-east | 6039797760 | 59027232 | 302.1 |
| C | im-74 | GCP:us-east | 4160749568 | 67108864 | 283.6 |

All five ≥250 ms operations sit in **GCP:us-east**. A (whole) produced none.

## Recurrence at the historically slow offsets

| arm | watched-offset ops | of which ≥250 ms | offsets hit |
|---|---:|---:|---|
| A WHOLE | 24 | 0 | none |
| B SEGMENTED-PERSISTENT | 21 | 1 | 6039797760 |
| C FRESH-WINDOW | 24 | 3 | 6039797760 ×2, 2013265920 ×1 |

Recurrence **continues** at `6039797760` (and once each at `2013265920` and `4160749568`). Not
claimed to be permanently bad — recorded only.

## Matched-region comparison (the only fair throughput comparison)

| region | arms present | A whole | B segmented | C fresh |
|---|---|---|---|---|
| **us-central** | A, B, C | n=4, med **4.732**, wall 1747 | n=3, med **4.145**, wall 1908 | n=3, med **5.685**, wall 1415 |
| us-east | B, C | n=1 | n=4, med 5.573 | n=5, med 5.523 |

## Correctness / guards

| arm | exact coverage | amp=1.0 | maxQD=4 | min spacing ≥4 ms | worker errors | map/unmap errors |
|---|---|---|---|---|---|---|
| A | 8/8 | 8/8 | 8/8 | 8/8 | 0 | 0/0 |
| B | 7/7 | 7/7 | 7/7 | 7/7 | 0 | 0/0 |
| C | 8/8 | 8/8 | 8/8 | 8/8 | 0 | 0/0 |

No SIGBUS, no crashes, no silent respawns, no offsets beyond EOF (final partial window handled
by clipping the copy length to the logical block, never touching past EOF).

---

## The main question

The four hypotheses and what the evidence actually supports:

- **B ≈ C > A** (segmentation / smaller independent mappings important) — **not supported.**
  B is *worst* in matched us-central (4.145 vs A 4.732 and C 5.685) and merely ties C in us-east
  (5.573 vs 5.523). Segmentation provides no throughput benefit.
- **C > B ≈ A** (fresh mapping lifecycle important) — **partially supported, and the best fit.**
  C is above both A and B in matched us-central, and at least equal in us-east.
- **B > C > A** — **not supported**; B is never best.
- **A ≈ B ≈ C** (previous differences were not a stable life-cycle effect) — **not supported on
  consistency**: C's CV is 0.098 against A 0.228 and B 0.234, and its p90−p10 spread is 1.35
  against 3.07 and 2.54. That gap is far outside noise for these sample sizes.

**What the evidence supports, stated plainly:**

1. **Mapping creation is essentially free** (1–2 ms), so "persistent mappings avoid mapping cost"
   is not a meaningful advantage. B's ~30 windows per reader cost 2.15 ms to create.
2. **C (fresh-window) is the most consistent by a wide margin** and is equal-or-better on
   throughput in every matched region. This is the strongest single finding.
3. **A (whole) has the cleanest tails** — zero operations ≥250 ms — where B had 1 and C had 4
   (one ≥500 ms). So the consistency advantage of C comes with a modestly heavier mid-tail.
4. **B (segmented-persistent) is dominated**: it is not faster than A or C in any matched region,
   carries 120 live mappings, and offers no tail benefit. On this evidence segmentation is not
   the mechanism.

**No overall winner is declared.** C wins throughput-consistency; A wins tails; B is dominated.
Choosing between A and C is Ahmed's tradeoff, not mine.

## NEW: arm B carries a ~125 s per-run start-up penalty (reproduced twice)

While re-running this experiment on **Testing 5** (Testing 4 hit its billing-cycle spend limit), the
per-slot cadence exposed something the measured phases hid. Median wall-clock cost per slot:

| lifecycle | `abc_lifecycle` (Testing 4, H100) | `abc_t5` (Testing 5, CPU-only) |
|---|---:|---:|
| whole | 5.1 s | 8.3 s |
| **segmented** | **125.1 s** | **129.5 s** |
| fresh | 5.4 s | 11.2 s |

The slow gap is **always the transition into a segmented run**. Attribution check
(gap-before vs gap-after per arm):

| dataset | arm | gap BEFORE | gap AFTER |
|---|---|---:|---:|
| `abc_lifecycle` | segmented | **125.1 s** | 5.7 s |
| `abc_t5` | segmented | **129.5 s** | 10.2 s |
| `abc_t5` | whole | 8.3 s | 127.5 s |
| `abc_t5` | fresh | 11.2 s | 126.8 s |

In `abc_t5` the 127.5 s "after whole" and 126.8 s "after fresh" are exactly the whole→segmented and
fresh→segmented transitions in the `[whole,segmented,fresh,fresh,segmented,whole]` schedule. So the
cost belongs to the **segmented run's own start-up**, not to teardown of whatever preceded it.

It is **not** in any measured phase: source wall for segmented runs is normal (1.6–5.2 s),
`prep_map` is 2.15 ms and `cleanup_unmap` is 67–80 ms. The penalty is therefore incurred *before*
the engine's own timing begins — consistent with container start-up for processes that will hold
~7.7 GB of file mappings each (≈31 GB of VMA across 4 readers).

**This is a decisive practical argument against B, independent of throughput.** It reproduces
across two workspaces and two placement classes, so it is a property of the architecture, not of
one host pool. (Mechanism not further investigated; recorded as an observation.)

## Testing 5 cross-check (CPU-only placement class)

Testing 4 exhausted its spend limit mid-task, so the cohort was re-run on Testing 5 via a
**CPU-only wrapper** (identical engine dispatch, no `gpu=` argument — these source engines never
touch the GPU). Observed GPU is `''`, confirming no GPU was allocated.

**Placement caveat:** absolute throughput is much lower on CPU-only containers — pooled median
**3.323 GB/s** vs 5.5–6.5 GB/s on H100 hosts — so these numbers are **not** comparable to the
H100 cohorts. The A/B/C comparison remains internally valid because all three arms share this
class. Partial coverage reached (24 slots): counted A=5, B=4, C=7 — **not** the specified 8 each.
The complete answer to the A/B/C question therefore rests on the Testing-4 cohort above.



- **B is n=7, not the specified 8** (stated above).
- Matched-region cells are small (n=3–5). The direction is consistent, but the magnitudes are
  not tightly estimated.
- All five ≥250 ms operations in this cohort were in GCP:us-east, so the tail difference between
  A and C is partly a region-exposure difference rather than purely a life-cycle effect.
- No follow-up sweep was started (no block-size, QD, pacing, MAP_SHARED, or other mmap flags).
